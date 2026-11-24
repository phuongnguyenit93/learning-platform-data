# GenericConversionService and Converter Lookup Mechanism in Spring Framework

## 1. Role of GenericConversionService

Spring provides the ConversionService interface to check and perform conversions between Java types. Applications register converters into a registry and then ask the service to convert a value from a source type to a target type.

GenericConversionService in org.springframework.core.convert.support is the general-purpose implementation that manages converters and looks up the appropriate converter. It supports ConversionService and registration via ConverterRegistry. DefaultConversionService adds many common converters; FormattingConversionService combines conversion with formatting.

```java
ConversionService service = new DefaultConversionService();
Integer age = service.convert("28", Integer.class);
Boolean active = service.convert("true", Boolean.class);
```

A newly created GenericConversionService is a general-purpose registry and does not pre-install the full set of default converters like DefaultConversionService.

| Component | Responsibility |
| --- | --- |
| ConversionService | canConvert(...) and convert(...) |
| ConverterRegistry | Registering and removing converters |
| GenericConversionService | Managing registry, lookup, conditions, and cache |
| DefaultConversionService | Providing the default set of converters |

## 2. Core APIs

ConversionService has an overload group using Class and a group using TypeDescriptor:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);

boolean canConvert(TypeDescriptor sourceType, TypeDescriptor targetType);
Object convert(Object source, TypeDescriptor sourceType,
               TypeDescriptor targetType);
```

Class only represents a raw type. TypeDescriptor also carries generic element types, annotations, and property context. When conversion depends on List<Integer>, Map keys/values, or annotations on a field, TypeDescriptor is critical metadata.

ConverterRegistry has the commonly used registration methods:

```java
<S, T> void addConverter(Converter<S, T> converter);
<S, T> void addConverter(Class<S> sourceType, Class<T> targetType,
                         Converter<? super S, ? extends T> converter);
void addConverter(GenericConverter converter);
void addConverterFactory(ConverterFactory<?, ?> factory);
void removeConvertible(Class<?> sourceType, Class<?> targetType);
```

These are abridged signatures illustrating the SPI. canConvert only checks whether a type pair is convertible; it does not guarantee that concrete data will parse successfully.

## 3. Converter Types

| SPI | Usage |
| --- | --- |
| Converter<S,T> | A simple, type-safe source/target pair |
| ConverterFactory<S,R> | One source converting to a family of target types |
| GenericConverter | Multiple pairs or needing TypeDescriptor |
| ConditionalConverter | Candidate is valid only in a specific context |

### Converter<S,T>

```java
public final class StringToOrderStatus
        implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT));
    }
}
```

OrderStatus is an application enum. Spring infers the String → OrderStatus pair from the generic signature when registering the instance. This is usually the best choice for a specific conversion pair.

### ConverterFactory<S,R>

A factory creates converters for a specific target type, useful when a String source can convert to many different enums. The factory receives the target class via getConverter(targetType). Do not use a factory if each target has completely separate logic; individual converters can be easier to read.

### GenericConverter

```java
public interface GenericConverter {
    Set<ConvertiblePair> getConvertibleTypes();
    Object convert(Object source, TypeDescriptor sourceType,
                   TypeDescriptor targetType);
}
```

getConvertibleTypes declares the supported class pairs. convert receives descriptors so it can inspect generic metadata and annotations. ConditionalGenericConverter combines GenericConverter with matches(sourceType, targetType).

Do not use GenericConverter for simple single-pair logic if Converter<S,T> expresses it clearly enough.

## 4. How Is the Registry Organized?

Conceptually, GenericConversionService manages a converter registry and a lookup cache. The registry holds a set of global converters and a map keyed by ConvertiblePair. Each ConvertiblePair can have one or more candidates; the cache maps a source/target TypeDescriptor pair to the selected converter or a not-found marker.

```text
GenericConversionService
├── converters
│   ├── globalConverters
│   └── Map<ConvertiblePair, ConvertersForPair>
│       ├── (String, Integer)
│       └── (String, OrderStatus)
└── converterCache
    ├── (source descriptor, target descriptor) -> converter
    └── (source descriptor, target descriptor) -> NO_MATCH
```

This is a conceptual internal model to explain lookup. Fields and classes such as converters, ConvertersForPair, ConverterCacheKey, converterCache, and NO_MATCH are not public APIs for applications to manipulate directly.

## 5. Converter Lookup Flow

When calling service.convert("42", Integer.class), the general flow is:

1. Validate the target type and determine source/target TypeDescriptors.
2. Handle a null source according to dedicated rules.
3. Create a cache key from the source and target descriptors.
4. Check the cache. If a converter is found, use it; if NO_MATCH is found, we know the previous lookup found none.
5. On a cache miss, the registry searches for a converter by traversing the source and target class/interface hierarchies.
6. Conditional candidates must pass matches(sourceType, targetType).
7. If no candidate is found, consider default converters.
8. Store the lookup result in the cache.
9. Invoke the selected converter or throw an exception if no conversion path exists.

```text
convert(source, sourceType, targetType)
             |
             v
       create cache key
             |
             v
         cache hit? ---- yes ----> use result
             |
             no
             v
     registry.find(source, target)
             |
             v
      traverse source/target hierarchy
             |
             v
       find candidates by pair
             |
             v
    ConditionalConverter.matches?
             |
       match -> select converter
       no match -> next candidate
             |
             v
      no candidate?
             |
             v
       default converter/no-op
             |
             v
         cache result
             |
             v
        perform conversion
```

The default converter can be a no-op if source is assignable to target. In that case Spring returns the source object as-is. If no converter exists and source is not assignable to target, conversion is unavailable.

The hierarchy traversal order is an implementation detail. Do not build business rules relying on an internal priority order; declare specific converters and explicit conditions instead.

## 6. Hierarchy-Based Lookup

A converter registered for a supertype can be used with a compatible source subclass. For example, a BaseCode → String converter can be a candidate for a SpecialCode source if SpecialCode extends BaseCode. The target hierarchy also participates in finding candidate pairs.

```java
class BaseCode {
    private final String value;
    BaseCode(String value) { this.value = value; }
    public String value() { return value; }
}
class SpecialCode extends BaseCode {
    SpecialCode(String value) { super(value); }
}
```

The registry tries candidate source/target pairs. Generic checks and conditional matches can still eliminate a candidate even when raw classes have an inheritance relationship. Do not assume a converter for Object is always preferred.

## 7. ConditionalConverter

ConditionalConverter has the method:

```java
boolean matches(TypeDescriptor sourceType, TypeDescriptor targetType);
```

It allows the same class pair to apply only in a specific context, such as when a target field carries a particular annotation. A ConditionalGenericConverter can check targetType.getAnnotation(MyAnnotation.class) and return true/false.

matches is only a candidate-selection step, not conversion. This method should be lightweight, deterministic, and free of side effects, because the lookup may be cached.

## 8. TypeDescriptor and Generic Metadata

TypeDescriptor can represent property types, generic element types of arrays/collections/maps, annotations, and property context.

For example, List<String> and List<Integer> both have raw class List.class, but different element types. When metadata is complete and an element converter exists, Spring can convert each item. If you only call convert(source, List.class), the target generic Integer is not expressed. A Java generic cast after conversion does not supply runtime metadata to Spring.

When generic conversion is needed, use the TypeDescriptor overload with descriptors obtained from the appropriate field, method parameter, or property. Inspect the source and target descriptors before concluding that a converter can handle the collection.

## 9. Converter Cache and NO_MATCH

The cache key contains the source TypeDescriptor and target TypeDescriptor. The cache value can be the selected converter or the NO_MATCH sentinel when lookup finds no candidate.

- First String → OrderStatus: cache miss, locate converter, store converter.
- Next call with same descriptors: cache hit, reuse stored converter.
- First unsupported Input → Target: cache miss, store NO_MATCH.
- Next call: cache hit on NO_MATCH, avoiding repeated lookup.

The cache stores converter lookup results, not converted values. Every new input still runs the converter. When adding or removing converters, the current implementation invalidates the cache so subsequent lookups reflect the updated registry. Do not use reflection to access or clear the internal cache; use the add/remove APIs.

## 10. No-op Conversion, Null, and Errors

If there is no specific converter but source is assignable to target, GenericConversionService can return the source object. For example, StringBuilder to CharSequence can preserve the exact same reference.

```java
GenericConversionService service = new GenericConversionService();
StringBuilder source = new StringBuilder("hello");
CharSequence target = service.convert(source, CharSequence.class);
System.out.println(target == source);
```

Stdout:

```text
true
```

For null, reference target types usually receive null; an Optional target may receive Optional.empty under default behavior. Primitives such as int cannot hold null, so conversion will fail. Do not assume all custom converters share identical null behavior.

| Exception | Meaning |
| --- | --- |
| ConverterNotFoundException | No converter found; source is not assignable |
| ConversionFailedException | A converter was selected, but converting the concrete value failed |

If there is no String → Integer converter, the error may be ConverterNotFoundException. If a converter exists and calls Integer.valueOf("abc"), lookup succeeds but parsing fails and may be represented by ConversionFailedException wrapping NumberFormatException. Inspect the cause to find the root reason.

## 11. Java 17+ Demo: Registering and Looking Up Converters

This example uses Spring Framework 6.2.x, Java 17+, and Maven. Create pom.xml with the spring-core dependency version 6.2.12:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core</artifactId>
    <version>6.2.12</version>
</dependency>
```

Create src/main/java/demo/GenericConversionDemo.java:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.GenericConversionService;

public class GenericConversionDemo {
    enum OrderStatus { NEW, PAID, SHIPPED }

    public static void main(String[] args) {
        GenericConversionService service =
                new GenericConversionService();

        System.out.println("before=" + service.canConvert(
                String.class, OrderStatus.class));

        service.addConverter(new Converter<String, OrderStatus>() {
            @Override
            public OrderStatus convert(String source) {
                return OrderStatus.valueOf(
                        source.trim().toUpperCase(Locale.ROOT));
            }
        });

        System.out.println("after=" + service.canConvert(
                String.class, OrderStatus.class));

        OrderStatus status =
                service.convert(" paid ", OrderStatus.class);
        System.out.println("status=" + status);

        StringBuilder source = new StringBuilder("hello");
        CharSequence same =
                service.convert(source, CharSequence.class);
        System.out.println("sameReference=" + (source == same));

        try {
            service.convert("10", Integer.class);
        } catch (RuntimeException ex) {
            System.out.println("missing="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Run in the project directory:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.GenericConversionDemo
```

Stdout produced by main:

```text
before=false
after=true
status=PAID
sameReference=true
missing=ConverterNotFoundException
```

An empty service has no String → OrderStatus converter yet, so before=false. After addConverter, the registry has the matching pair. The string " paid " becomes enum PAID. StringBuilder is assignable to CharSequence, so no-op preserves the same reference. The empty service has no String → Integer converter, so the last case illustrates converter not found.

If using DefaultConversionService, the last line would no longer fail with a missing converter because the default service includes String → Integer conversion.

## 12. GenericConverter and Collection Conversion

GenericConverter can declare multiple ConvertiblePairs and use TypeDescriptor to distinguish targets. For example, a converter for String → CustomerId and String → InvoiceId can declare both pairs in getConvertibleTypes(). Inside convert, inspect targetType.getObjectType() to construct the right target type. CustomerId and InvoiceId are domain classes defined by the application.

For List<String> → List<Integer>, the descriptor provides the element type so the framework selects a converter for each element. For Map, metadata can describe both key and value types. If descriptors lack generic information, conversion may fail to pick the desired converter or only see the raw container type.

Do not blindly cast the result to List<Integer> without supplying a target descriptor. Type erasure means a cast does not convert elements automatically.

## 13. Registration and Removal

| API | Effect |
| --- | --- |
| addConverter(Converter) | Register a converter using generic type info |
| addConverter(Class, Class, Converter) | Register an explicit pair |
| addConverter(GenericConverter) | Register multi-pair/context-aware converter |
| addConverterFactory(ConverterFactory) | Register a factory |
| removeConvertible(source, target) | Remove converters for a pair |

Multiple conditional candidates can share the same pair; the registry evaluates matching conditions. Avoid multiple converters on overlapping pairs without clear rules. Write tests for each TypeDescriptor and candidate. Do not rely on registration order as a business rule.

Typically, converters are registered at application startup and the configured ConversionService is shared. Avoid mutating the registry per request, which causes conversion semantics to vary across requests.

## 14. GenericConversionService, DefaultConversionService, and MVC

| Implementation | Purpose |
| --- | --- |
| GenericConversionService | General-purpose registry |
| DefaultConversionService | Default converter suite |
| FormattingConversionService | Conversion combined with Formatter |
| DefaultFormattingConversionService | Formatting service with defaults |

Spring MVC allows registering converters via WebMvcConfigurer.addFormatters:

```java
@Configuration
public class WebConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatus());
    }
}
```

This is an MVC configuration class requiring the corresponding imports and converter class. Registering a converter into a local GenericConversionService instance does not cause MVC to automatically use that instance; it must be added to the application context's FormatterRegistry/ConversionService.

JSON @RequestBody is normally deserialized by an HttpMessageConverter such as Jackson. ConversionService does not replace all Jackson mapping; custom JSON formats may require configuring Jackson serializers/deserializers or a Jackson module.

## 15. Common Errors and How to Debug

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ConverterNotFoundException | Missing converter and source is not assignable | Check source/target pair |
| ConversionFailedException | Converter exists, but parsing failed | Inspect cause and input |
| canConvert=false | Registry lacks converter or condition did not match | Check registration/descriptor |
| canConvert=true yet convert fails | Specific input data is malformed | Check converter logic |
| Converter does not run in MVC | Registered on a different service instance | Use the right FormatterRegistry |
| Generic elements are not converted | Missing target element descriptor | Provide full TypeDescriptor |
| String→Integer fails on empty service | No default converters registered | Use DefaultConversionService or add converter |
| Null into primitive | Primitives cannot hold null | Use wrapper or handle null |
| New converter is not chosen | Another candidate or conditional mismatch | Debug matches and hierarchy |
| JSON ignores MVC converter | Jackson HttpMessageConverter handles the body | Configure Jackson |

Debugging procedure:
1. Identify the runtime source class and target type.
2. Check canConvert using the right overload.
3. Verify the converter is in the right registry/service instance.
4. Set breakpoints in Converter.convert and ConditionalConverter.matches.
5. Inspect source/target hierarchies, TypeDescriptor, and generic info.
6. Distinguish missing converter from conversion failure.
7. In MVC, verify the WebMvcConfigurer/FormatterRegistry of the actual context.

Do not rely on internal classes like ConverterAdapter/ConverterCacheKey in application code; they are helpful when reading framework source code, not an extension API.

## 16. Performance and Thread Safety

ConversionService is designed to be configured and shared. Application-written converters should be stateless or thread-safe. Lookup caching reduces repeated hierarchy traversal, but conversion still executes for every input value.

- Do not store request-specific mutable state in converters.
- Avoid I/O or database queries inside converters.
- Do not register competing converters without clear conditions.
- Register converter configuration at startup.
- Test valid values, malformed values, null, generic types, and source subclasses.
- Do not use conversion as business validation or authorization.

If conversion depends on locale, consider Formatter. If it depends on annotation/property context, consider GenericConverter with ConditionalConverter. If there is only a single simple pair, Converter<S,T> is easier to maintain.

## 17. Checklist and Summary

1. Choose the right SPI: Converter, ConverterFactory, or GenericConverter.
2. Declare sufficiently specific source/target pairs.
3. Use TypeDescriptor when generic/annotation context matters.
4. Use ConditionalConverter when selection depends on metadata.
5. Register into the exact ConversionService used by the framework.
6. Distinguish converter not found, conversion failed, null, and no-op.
7. Remember the cache stores converters/NO_MATCH, not output values.
8. Test hierarchy, collections, null, error paths, and MVC integration.

GenericConversionService manages the registry, looks up converters by source/target TypeDescriptor, evaluates candidates, and caches lookups. On a cache miss, the registry traverses hierarchies and evaluates conditional matches; if no converter exists, a source assignable to target can use a no-op. DefaultConversionService supplies default converters, while MVC uses the registry wired into the application context.

## References

- [Spring Framework 6.2 — Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/core/validation/convert.html)
- [GenericConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html)
- [ConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [ConverterRegistry API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html)
- [GenericConverter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/GenericConverter.html)
- [ConditionalConverter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/converter/ConditionalConverter.html)
- [TypeDescriptor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/TypeDescriptor.html)
- [DefaultConversionService API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html)
