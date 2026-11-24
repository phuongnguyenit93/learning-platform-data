# Distinguishing BeanWrapper, BeanUtils, and DTO Mapping Tools in Spring Framework

In a Spring application, a piece of data such as `name` or `age` can appear in many forms: a field on a JavaBean, a value in an HTTP form, an entity attribute, a request DTO, or a response DTO. Three frequently mentioned tool groups are **`BeanWrapper`**, **`BeanUtils`**, and **DTO mappers** (mapping between objects). They may all "read or write properties", yet they solve **three different problems**:

- **`BeanWrapper`** reads/writes properties **by name at runtime**, supporting nested paths and type conversion when appropriately configured.
- **`org.springframework.beans.BeanUtils`** provides static JavaBeans utilities, where `copyProperties(source, target)` **copies compatible properties** from an existing object to another. This is a shallow copy operation based on property names.
- **DTO mappers** define how to transform between data models with different meanings (request → domain/entity, entity → response). They can be written manually or built using **MapStruct**, **ModelMapper**, and similar tools.

Choosing the right tool keeps code clear and avoids two common risks: assuming property copying includes type conversion/validation, or accidentally copying fields that clients are not allowed to change.

## 1. Overview: Shared Focus on Properties, Different Responsibilities

| Criterion | `BeanWrapper` | Spring `BeanUtils` | DTO mapper |
| --- | --- | --- | --- |
| Primary goal | Dynamic property access/mutation by name | Metadata, instantiation, and property copying utilities | Transforming one data model into another |
| API style | Interface with target-bound instance; `BeanWrapperImpl` is the implementation | `static` methods | Methods on a class/service or mapper interface |
| Property selection | Name at runtime, e.g., `"address.city"` | Properties with matching names and compatible types between source/target | Explicitly declared rules or convention configuration |
| Read/write | `getPropertyValue` / `setPropertyValue` | `copyProperties` and JavaBeans utilities | `toEntity`, `toDto`, `updateEntity`... |
| Type conversion | Can use `ConversionService`/property editors | `copyProperties` is not a general type-conversion engine | Mapper may support conversion rules, depending on implementation |
| Nested objects | Can traverse nested paths | Copies matching property references, **not a deep copy** | Can transform deeply or flatten per mapping rules |
| Validation | Does not validate target automatically | Does not validate automatically | Does not validate by default; check at appropriate boundaries/services |
| Field write control | Caller must control accessed properties | Any compatible property may be copied unless excluded | Can explicitly whitelist mapped fields |
| Best suited for | Binding infrastructure, forms, dynamic config, JavaBean tooling | Simple copying between trusted internal beans | API/domain boundaries, business invariants, structurally different DTOs |

Crucially, **automatic capability does not equal automatic permission**. For example, a request having a `role` field does not mean a registration API is allowed to update `UserEntity.role`. Whether using BeanWrapper, BeanUtils, or a mapper, the application must still choose which fields are permitted.

## 2. BeanWrapper: Reading/Writing JavaBean Properties by Name

`org.springframework.beans.BeanWrapper` is an interface in Spring's JavaBeans infrastructure; its common implementation is `BeanWrapperImpl`. It wraps an object and provides property access by name:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(person);

Object current = wrapper.getPropertyValue("name");
wrapper.setPropertyValue("name", "Mai");
Class<?> type = wrapper.getPropertyType("name");
boolean writable = wrapper.isWritableProperty("name");
~~~

This is an **illustrative snippet**, assuming a `person` variable with appropriate JavaBean properties and imports for `BeanWrapper` and `BeanWrapperImpl`. `getPropertyValue` returns `Object`; callers must check/cast to the right type when using it.

### 2.1. "Property" Is Not Entirely Synonymous with "Field"

Given a JavaBean:

~~~java
public class Person {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Spring sees property `name` through its getter/setter. `BeanWrapper` under property access invokes the setter on write. If an object only has `private String name` without suitable accessors, that field is not automatically a writable JavaBean property.

This distinction is critical when code includes:

- Getters that compute values without storing them directly in a field.
- Setters that normalize data or enforce invariants.
- Read-only attributes (getter without setter).
- Internal fields named differently from exposed properties.

When direct field access is explicitly desired, Spring has `DirectFieldAccessor` and `DataBinder.initDirectFieldAccess()` mode. That is a different mechanism; do not use BeanWrapper assuming it can write every private field.

### 2.2. Nested Paths, Collections, and Conversion

For a JavaBean with `Address address`, calls like:

~~~java
wrapper.getPropertyValue("address.city");
wrapper.setPropertyValue("address.city", "Hue");
~~~

can access nested properties. The target must have a matching structure; if `address == null`, access depends on the auto-grow nested paths option and Spring's ability to instantiate the child object. Do not assume the framework can instantiate arbitrary immutable objects or complex collections.

`BeanWrapperImpl` can configure a conversion service:

~~~java
BeanWrapper wrapper = new BeanWrapperImpl(person);
wrapper.setConversionService(new DefaultConversionService());
wrapper.setPropertyValue("age", "26"); // "26" -> Integer
~~~

The example above assumes `person.age` is an `Integer` property with a setter. `DefaultConversionService` provides many basic type conversions; if a string cannot be converted, assignment can throw a conversion/type-mismatch error.

**Key distinction:** `setPropertyValue("age", "26")` can convert a string to a number when a converter is present, whereas `BeanUtils.copyProperties(source, target)` is **not** an equivalent call that automatically converts arbitrary differing types.

### 2.3. Where Does BeanWrapper Sit in Spring Data Binding?

`DataBinder` uses property accessor infrastructure, type conversion, and `BindingResult` to connect input data with an object. Spring MVC can use `WebDataBinder` to bind query/form parameters. In this flow, BeanWrapper is **a low-level component** serving binding, not a controller annotation or JSON decoder.

Diagram:

~~~text
Input data (form/query)
          |
          v
DataBinder / WebDataBinder
          |
          +--> allowedFields, conversion rules
          |
          v
Bean property accessor (BeanWrapper)
          |
          +--> invoke setter or return assignment/conversion error
          v
Target JavaBean
          |
          v
BindingResult / Errors (if errors occur)
~~~

For JSON `@RequestBody`, Spring MVC typically uses `HttpMessageConverter` and Jackson for deserialization; do not infer that every JSON field passes through `BeanWrapperImpl`. These are separate mechanisms.

## 3. Spring BeanUtils: Static Utilities and copyProperties

`org.springframework.beans.BeanUtils` belongs to Spring Beans. It includes many utilities such as inspecting property descriptors, finding matching methods, and instantiating classes when appropriate. The method that most often causes confusion is:

~~~java
BeanUtils.copyProperties(source, target);
~~~

**The order is source first, target second**. This is the reverse of some APIs in other libraries. Imports must be explicit:

~~~java
import org.springframework.beans.BeanUtils;
~~~

Do not confuse it with `org.apache.commons.beanutils.BeanUtils` from Apache Commons BeanUtils: similar name, yet behavior, dependencies, and API signatures differ.

### 3.1. How Does BeanUtils.copyProperties Copy?

Essentially, Spring finds properties with readable getters on source and writable setters on target whose names/types are compatible, and copies **property values** from source to target.

~~~java
BeanUtils.copyProperties(source, target, "id", "role");
~~~

The trailing arguments are a list of **property names to ignore**. There is also an overload taking an editable class to restrict properties to a specific API type. The set of compatible properties depends on JavaBeans/generics metadata supported by that Spring version.

For instance, if both objects have `String displayName` and `Integer age`, those two values are typically copied. If source has `String age` while target has `Integer age`, **do not expect** `copyProperties` to parse strings to numbers automatically; you need explicit conversion or a mapper with rules.

### 3.2. Shallow Copy and Object References

Suppose both source and target have property `Address address`. `copyProperties` copies the reference of `address`; it **does not create an independent Address** and deep-copy the entire graph.

~~~java
BeanUtils.copyProperties(source, target);
boolean sameAddress = source.getAddress() == target.getAddress();
~~~

With a non-null source address and compatible properties, `sameAddress` is `true`. Subsequently modifying `target.getAddress().setCity(...)` also affects the object referenced by source.

This is not a Spring bug: the method is designed for **simple property copying**, without a deep-clone contract. If the DTO must remain independent of the entity, construct new child objects/collections rather than sharing mutable references.

### 3.3. Nulls, Sensitive Fields, and Partial Updates

Suppose a client submits a DTO with only `name` and omits `email`, leaving `email == null` on the DTO object. With `copyProperties`, `null` can still be copied onto the target if properties match; **there is no default "ignore null" policy**.

In HTTP PATCH, you must distinguish "field absent" from "field sent as null". A simple approach using a DTO where both states become `null` **cannot represent that difference**. Solutions include patch DTOs that track presence, JSON Merge Patch, or explicit contract-driven mapping.

For sensitive fields such as `id`, `role`, `createdAt`, `ownerId`, or `status`, this is dangerous:

~~~java
BeanUtils.copyProperties(untrustedRequest, persistentUser);
~~~

If property names and types match, those fields can be overwritten. `BeanUtils.copyProperties(..., "role", "id")` is only a **denylist**; future properties added to the DTO could still be copied unintentionally. Across untrusted boundaries, prefer narrow request DTOs combined with **explicit allowlist mapping**.

### 3.4. What Does BeanUtils Not Do?

- Does not automatically validate `@NotNull`, `@NotBlank`, `@Valid`, or domain rules.
- Does not know which fields belong to the caller's permissions.
- Does not handle entity relationships, persistence cascades, transactions, or lazy loading.
- Has no built-in mapping rules when names differ, such as `fullName -> displayName`, in the basic call.
- Does not turn nested collections/objects into an independent deep copy.
- Does not instantiate target from source in the common `copyProperties` overloads; the caller must supply target.

Whenever one of these behaviors is needed, it is a separate **mapping/validation/business policy** that should be written explicitly for testability.

## 4. DTO Mappers: Meaningful Transformation Between Two Models

A DTO (Data Transfer Object) is a data type used to exchange data across layers/boundaries such as HTTP requests/responses, messages, or service APIs. A DTO does not need to mirror the structure of a persistence entity.

For example, the same user might have:

~~~text
CreateUserRequest:
  displayName, email, password

UserEntity:
  id, displayName, normalizedEmail, passwordHash,
  role, createdAt, version

UserResponse:
  id, displayName, email
~~~

Here, no name-based property copy handles everything adequately:

1. Email in the request may be normalized before saving.
2. Passwords must pass through a password encoder, never written in plaintext.
3. `id`, `role`, and `createdAt` are system-controlled.
4. Responses must not leak the password hash.
5. Entities may contain lazy relationships or complex structures unsuitable for JSON contracts.

**Mapping** decides which fields are selected, what values they transform into, and which fields are excluded. Validation, authorization, and business behavior remain in their appropriate layers; never treat a mapper as an automatic permission or security-encoding layer.

### 4.1. Manual Mappers

For simple rules, writing plain Java is often clear enough:

~~~java
public record UpdateProfileRequest(String displayName, Integer age) {}
public record ProfileResponse(Long id, String displayName, Integer age) {}

public final class ProfileMapper {
    public ProfileResponse toResponse(UserEntity user) {
        return new ProfileResponse(
                user.getId(),
                user.getDisplayName(),
                user.getAge());
    }

    public void applyAllowedChanges(
            UpdateProfileRequest request, UserEntity target) {
        target.setDisplayName(request.displayName().strip());
        target.setAge(request.age());
    }
}
~~~

This snippet **illustrates a mapping API**, assuming `UserEntity` and its corresponding getters/setters exist. It is not a standalone runnable file. It intentionally writes only `displayName` and `age`; `role`, `id`, and `ownerId` remain untouched. Check that `displayName` is non-null/valid before calling `strip()` to avoid `NullPointerException`.

When a DTO has only a few fields, explicit code is both readable and supportive of custom domain rules. Adding a mapping library is not mandatory for a small transformation.

### 4.2. MapStruct: Compile-Time Mapper Generation

**MapStruct** is an annotation processor that generates Java implementations for mapper interfaces at compile time. You can declare mappings with differing names and ignore entity properties:

~~~java
@Mapper(componentModel = "spring")
public interface UserMapper {

    @Mapping(target = "id", ignore = true)
    @Mapping(target = "role", ignore = true)
    @Mapping(target = "normalizedEmail", source = "email")
    UserEntity toEntity(CreateUserRequest request);
}
~~~

This is an **illustrative snippet**, requiring dependencies `org.mapstruct:mapstruct` and processor `org.mapstruct:mapstruct-processor`, imports `org.mapstruct.Mapper` and `org.mapstruct.Mapping`, plus the corresponding model types. `componentModel = "spring"` makes the generated implementation a Spring-managed bean.

Strengths: Java methods are strongly typed, and many property-name/type mismatches surface at compile time rather than only at runtime. You can use `@MappingTarget` to update existing objects and configure null behaviors/collection policies.

Still, **generated mapping code does not mean safety has been verified**. Automatic name-based mapping can populate unintended fields if DTOs/targets evolve. For client-driven updates, use `@BeanMapping(ignoreByDefault = true)` to map strictly selected fields:

~~~java
@Mapper(componentModel = "spring")
public interface SafeProfileMapper {
    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "displayName", source = "displayName")
    @Mapping(target = "age", source = "age")
    void update(UpdateProfileRequest source,
                @MappingTarget UserEntity target);
}
~~~

This snippet assumes the classes/records exist and imports `org.mapstruct.BeanMapping`, `Mapping`, `MappingTarget`, and `Mapper`. Mapping rules must still account for nulls: in PATCH, calling `update(...)` may write `null` unless configured otherwise.

MapStruct does not handle business transactions, resource ownership, or password hashing on its own. Those steps belong in well-designed services/assemblers.

### 4.3. ModelMapper: Runtime Rule-Based Mapping

**ModelMapper** typically infers mappings from property names and structures at runtime; type maps or custom rules can be configured:

~~~java
ModelMapper mapper = new ModelMapper();
ProfileResponse response =
        mapper.map(entity, ProfileResponse.class);
~~~

This is only an **API illustration**; it requires dependency `org.modelmapper:modelmapper`, import `org.modelmapper.ModelMapper`, and appropriate model types. Support for constructing targets such as records, immutable objects, or classes without no-arg constructors depends on library configuration/support; do not assume this snippet works for every immutable DTO.

Its advantage is fast setup for convention-based mappings. Conversely, be cautious of implicit mappings, similar-looking names, nested structures, and errors that appear only at runtime. When using a runtime mapper in sensitive flows, thoroughly test which fields are read and written rather than relying blindly on conventions.

### 4.4. Which Tool Should You Choose?

| Situation | Appropriate choice | Why |
| --- | --- | --- |
| Reading property values whose names come from metadata | `BeanWrapper` | Dynamic access and JavaBeans metadata |
| Binding property names, converting String to Integer | `DataBinder`/`BeanWrapper` + conversion service | Built-in conversion and error reporting |
| Copying a few compatible properties between internal beans | `BeanUtils.copyProperties` when targets are trusted | Concise, minimal rules |
| Request DTO → entity with sensitive id/role/ownerId | Explicit allowlist-based mapper | Strict control over writable fields |
| Complex entity → response DTO, renames/nested/flattening | Manual mapper or MapStruct | Intentional mapping with tests |
| Many DTO/entity pairs, wanting compile-time checks | MapStruct | Implementations generated at compile time |
| Prototyping, runtime convention-based mapping | ModelMapper (if suitable) | Less boilerplate, requires strict testing |
| Accessing properties when object is a flexible Map | Map-specific access / validator | Map keys are not automatically JavaBean properties |
| Only checking `@NotBlank` or `@Min` | Jakarta Bean Validation | None of the three tools above replace validation |

## 5. Runnable Java 17+ Example: Direct Comparison

This example uses **Spring Framework 6.1.x**, without requiring an HTTP server, database, or Spring Boot. We create a profile JavaBean with a nested property, use BeanWrapper to assign values, BeanUtils to copy, and then manually map to a response DTO.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'spring-property-mapping-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-beans:6.1.15'
    implementation 'org.springframework:spring-core:6.1.15'
}

application {
    mainClass = 'example.PropertyMappingDemo'
}
~~~

Create file `src/main/java/example/PropertyMappingDemo.java`:

~~~java
package example;

import org.springframework.beans.BeanUtils;
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.core.convert.support.DefaultConversionService;

public class PropertyMappingDemo {

    public static class Address {
        private String city;

        public Address() {}

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class Profile {
        private String displayName;
        private Integer age;
        private String role;
        private Address address = new Address();

        public Profile() {}

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public record ProfileResponse(
            String displayName,
            Integer age,
            String city) {}

    public static ProfileResponse toResponse(Profile source) {
        return new ProfileResponse(
                source.getDisplayName().strip(),
                source.getAge(),
                source.getAddress().getCity());
    }

    public static void main(String[] args) {
        Profile source = new Profile();
        source.setRole("ADMIN");

        // BeanWrapper: dynamic property read/write and type conversion.
        BeanWrapper wrapper = new BeanWrapperImpl(source);
        wrapper.setConversionService(new DefaultConversionService());
        wrapper.setPropertyValue("displayName", "Mai");
        wrapper.setPropertyValue("age", "26");
        wrapper.setPropertyValue("address.city", "Hue");

        System.out.println("wrapper: "
                + wrapper.getPropertyValue("displayName")
                + "/" + source.getAge()
                + "/" + source.getAddress().getCity());

        // BeanUtils: copy compatible properties.
        Profile copied = new Profile();
        BeanUtils.copyProperties(source, copied);

        System.out.println("copied: "
                + copied.getDisplayName() + "/" + copied.getAge());
        System.out.println("copied-role: " + copied.getRole());
        System.out.println("same-address: "
                + (source.getAddress() == copied.getAddress()));

        // Manual mapper: intentionally create only a public response DTO.
        ProfileResponse dto = toResponse(source);
        System.out.println("dto: " + dto);

        // Because BeanUtils performs a shallow copy, editing copied's nested
        // object also changes the object referenced by source.
        copied.getAddress().setCity("Da Nang");
        System.out.println("source-city-after-copy-edit: "
                + source.getAddress().getCity());
        System.out.println("dto-city-still: " + dto.city());
    }
}
~~~

Run in the project directory containing the Gradle Wrapper:

~~~bash
./gradlew run
~~~

If you have no wrapper but Gradle is installed, you can use `gradle run`. On Windows with a wrapper, use `.\gradlew.bat run` in PowerShell.

**Expected stdout from the program** (omitting Gradle's messages):

~~~text
wrapper: Mai/26/Hue
copied: Mai/26
copied-role: ADMIN
same-address: true
dto: ProfileResponse[displayName=Mai, age=26, city=Hue]
source-city-after-copy-edit: Da Nang
dto-city-still: Hue
~~~

Explanation of each result:

1. `BeanWrapper.setPropertyValue("age", "26")` uses `DefaultConversionService` to convert from a string to `Integer`; path `"address.city"` reaches the existing nested JavaBean.
2. `BeanUtils.copyProperties` transfers `displayName` and `age` from source to copied because their names/types match.
3. `role="ADMIN"` is also copied, illustrating why unrestricted copying should not be applied to entities when the source is an untrusted request.
4. `same-address: true` proves the `Address` object was not cloned; source and copied share the reference.
5. `ProfileResponse` contains only `displayName`, `age`, and `city`. The `role` field is absent from the DTO, and the nested address is extracted as an independent `String city`.
6. Modifying `copied.address.city` changes the value seen from source, whereas the String already placed into the DTO does not change automatically. If a response DTO holds a mutable Address, a separate deep-copy decision is needed.

The example intentionally works strictly with JavaBeans for consistent illustration. It does not perform HTTP binding, JSON serialization, or Jakarta Bean Validation.

## 6. From Example to REST API Design in Spring

Suppose a profile update endpoint accepts:

~~~java
public record UpdateProfileRequest(
        String displayName,
        Integer age) {}
~~~

A controlled update usually follows these steps:

~~~text
HTTP request
     |
     v
Deserialize request DTO (Jackson for JSON)
     |
     v
Validation (@Valid and configured validator)
     |
     v
Authorization (does caller have permission to edit profile?)
     |
     v
Service loads existing entity in transaction
     |
     v
Explicit mapper updates permitted fields
     |
     v
Service checks business invariants then saves
     |
     v
Mapper builds response DTO, returning only fields permitted to be public
~~~

With Spring MVC receiving form data, the binder infrastructure can use BeanWrapper and `ConversionService`. With Spring MVC receiving JSON `@RequestBody`, Jackson deserializes the object; using BeanWrapper in form binding does not mean JSON goes through BeanUtils by default.

A hypothetical controller/service might look like:

~~~java
@PutMapping("/profiles/{id}")
public ProfileResponse update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateProfileRequest request) {

    ProfileEntity current = profileService.findForUpdate(id);
    authorizationService.assertCanEdit(current);

    profileMapper.applyAllowedChanges(request, current);
    profileService.save(current);

    return profileMapper.toResponse(current);
}
~~~

This is **architectural illustration code**, assuming classes/services/annotation imports and transaction handling are already in place. Do not run it as a standalone class. For partial updates (PATCH), `applyAllowedChanges` needs clear policies on absent fields, `null`, and replace semantics.

Avoid binding requests directly onto persistence entities because writable properties on a JavaBean/entity **are not necessarily** fields belonging to the API contract. `setAllowedFields(...)` helps restrict fields in WebDataBinder for form data, while explicit DTOs/mapping protect boundaries even when data arrives from JSON, message queues, or internal tests/services.

## 7. Easily Misunderstood Technical Differences

### 7.1. BeanWrapper Differs from BeanUtils Even When Both Manipulate Properties

`BeanWrapper` works when property names are known only at runtime:

~~~java
String property = "displayName";
Object value = wrapper.getPropertyValue(property);
~~~

`BeanUtils.copyProperties` does not provide "copy a single property chosen by an arbitrary dynamic path" with the same semantics; it primarily iterates over compatible properties by class metadata. If code only needs `source.getDisplayName()`, direct Java access is usually clearer than BeanWrapper.

### 7.2. BeanUtils "Copying Successfully" Does Not Prove Everything Was Copied

If a property on source has no compatible property on target, Spring can skip that property without treating it as an error for the whole copy. Therefore unit tests should assert **the fields that must be mapped** and **the fields that must not be mapped**. When schemas evolve, new fields might be skipped or unintentionally copied depending on names/types.

### 7.3. Records, Immutable Classes, and Constructor Mapping

A Java `record` has no mutable setters for BeanWrapper to assign components arbitrarily. Nor should you assume `BeanUtils.copyProperties(source, targetRecord)` performs constructor mapping. For immutable DTOs, prefer construction via canonical constructors, factory methods, builders, or mappers that support constructor mapping appropriately.

MapStruct can generate code creating targets via constructors/builders if the model is supported and properly configured. Specific usage should be verified by inspecting generated source and compile tests rather than relying on annotation names alone.

### 7.4. Nulls, Collections, and Lazy Associations

The three tools do not share the same null policies:

- BeanWrapper can assign `null` to a reference property if the property permits it.
- BeanUtils can copy `null` and copy collection/object references without deep cloning.
- Mappers can be configured for skip-null/replace/merge; policies depend on the mapper and create/update scenario.

When mapping from a JPA entity, reading lazy associations can trigger unexpected queries or lazy initialization errors if the session is closed. Avoid letting reflective mapping traverse the entire object graph accidentally. Choose projections, fetch plans, and response DTOs tailored to each endpoint.

### 7.5. Property Access and Security

A public setter does not mean clients are allowed to invoke that setter through an API. If a request can control property names, restrict the set of readable/writable properties (allowlist) before calling `setPropertyValue(...)`. Never let clients freely submit `"role"`, `"class"`, or nested paths to steer internal state. Use explicit DTOs and framework binding policies at every entry point accepting untrusted input.

## 8. Testing and Tool-Selection Criteria

A solid test suite should focus on **the intended contract**, not merely verify that no exception is thrown.

| Test group | What to prove |
| --- | --- |
| BeanWrapper property access | Reads/writes right getters/setters, nested paths, checks readable/writable properties |
| BeanWrapper conversion | `"26"` → `Integer(26)`; malformed values produce proper errors |
| BeanUtils copy | Compatible properties are copied; no expectation of automatic conversion |
| BeanUtils shallow copy | Mutable nested objects/collections may share references |
| BeanUtils null handling | `null` can overwrite target on matching properties |
| DTO mapper create/update | Strictly allowlisted fields are mapped |
| Security | `role`, `ownerId`, `id`, and metadata are not modified by requests |
| Mapper compile/runtime | Renames, nested mapping, null policy, and immutable DTOs are tested |
| HTTP binding | JSON/form data flows through the right mechanism and returns proper errors |
| Persistence | Invariants, transactions, and concurrent writes are protected in service/database layers |

You can unit-test manual mappers by creating a source, mapping it, and asserting both exposed fields and excluded fields. With MapStruct, running compilation and asserting generated behavior catches schema drift. With ModelMapper, test concrete source/target pairs at runtime; never treat a "maps without throwing" test as proof that mapping is safe.

**Quick selection rules:**

- When the problem is **reading/writing properties by name**, choose `BeanWrapper`.
- When the problem is **simple copying between trusted internal JavaBeans**, `BeanUtils.copyProperties` can be used.
- When the problem is **defining a data-transfer contract between DTOs and domain/entities**, choose **explicit mapping**, handwritten or using tools like MapStruct.
- When the problem is **validating data**, use validation; for **permissions**, use authorization; for **protecting storage integrity**, use domain rules and database constraints.

## 9. Self-Check Questions

1. `BeanWrapper.setPropertyValue("age", "26")` can succeed even though `age` is `Integer`. Why is `BeanUtils.copyProperties` not considered a replacement for type conversion?
2. If `source.address == target.address` after `copyProperties`, what happens when modifying `target.address.city`?
3. Why does ignoring `role` via `BeanUtils`'s ignore list still require review when models change?
4. When a request DTO and entity have different property names, what advantage does a mapper have over automatic copying?
5. In Spring MVC, how does form binding differ from `@RequestBody` JSON deserialization?
6. When a DTO uses a record or immutable class, why can traditional JavaBean property assignment be unsuitable?
7. In HTTP PATCH, how does "field omitted" differ from "field sent as `null`"?
8. When MapStruct generates a mapper, what must still be tested regarding security, nulls, and nested mapping?

**Conclusion:** `BeanWrapper` is a tool for **accessing and converting property values at runtime**; `BeanUtils` is a set of **JavaBeans utilities and shallow property copying**; DTO mappers are where you **intentionally describe how data transforms between models**. Using each tool at the right layer, keeping data contracts explicit, and updating only permitted fields will make Spring applications easier to maintain and safer.

### References

- Spring Framework — JavaBeans `BeanWrapper`: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework API — `BeanWrapper`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanWrapper.html
- Spring Framework API — `BeanUtils`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanUtils.html
- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- MapStruct — Reference Guide: https://mapstruct.org/documentation/stable/reference/html/
- ModelMapper — User Manual: https://modelmapper.org/user-manual/
