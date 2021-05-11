import inspect

import regex
from discord.ext import commands


# TODO: Improve when discordpy v2.0 releases with the run_conversion function
def regex_arguments(pattern):
    def decorator(function):
        async def wrapper(self, ctx, *, args: str):
            match = regex.match(pattern, args.strip())
            if match is None:
                raise commands.UserInputError()
            arg_groups = [self, ctx] + list(match.groups())
            arg_converted = []
            signature = inspect.signature(function)
            for parameter, argument in zip(signature.parameters.values(), arg_groups):
                if parameter.annotation == inspect.Parameter.empty:
                    arg_converted.append(argument)
                elif isinstance(parameter.annotation, commands.Converter):
                    # Converter object
                    arg_converted.append(
                        await parameter.annotation.convert(ctx, argument),
                    )
                elif inspect.isclass(parameter.annotation) and issubclass(
                    parameter.annotation,
                    commands.Converter,
                ):
                    # Converter class
                    arg_converted.append(
                        await parameter.annotation().convert(ctx, argument),
                    )
                elif inspect.iscoroutine(parameter.annotation):
                    arg_converted.append(await parameter.annotation(argument))
                elif callable(parameter.annotation):
                    arg_converted.append(parameter.annotation(argument))
                else:
                    raise commands.UserInputError()
            await function(*arg_converted)

        return wrapper

    return decorator
