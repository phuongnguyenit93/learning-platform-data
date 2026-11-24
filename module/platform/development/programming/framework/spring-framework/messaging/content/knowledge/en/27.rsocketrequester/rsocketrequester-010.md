# Generic Response Types and ParameterizedTypeReference

## 1. The Problem: Java Generics Undergo Type Erasure

When making RSocket calls with Spring, the client usually knows the data type it wants to receive. For simple types like String, User, or Order, you can pass the Class directly:

~~~java
Mono<User> user = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
~~~

Difficulty arises when the response type has generic parameters, such as List<User>, ApiResponse<User>, or ApiResponse<List<Order>>. Java erases most generic parameter information at runtime (type erasure). Therefore, List<User>.class is not valid Java syntax; List.class only represents the raw List type and does not indicate that the elements inside are User.

If you provide only List.class, the data converter on the receiving side may only know the result is a list without enough type information to convert each element into User. Depending on the codec and data, elements may become Maps or another intermediate type. The same problem occurs with generic wrapper classes like ApiResponse<T>: passing only ApiResponse.class does not convey whether T is User or List<Order>.

## 2. What Is ParameterizedTypeReference?

org.springframework.core.ParameterizedTypeReference<T> is a Spring utility class used to retain full generic type information as a java.lang.reflect.Type. It exploits the generic superclass of an anonymous subclass to capture the type parameter at object creation time.

Common usage pattern:

~~~java
ParameterizedTypeReference<List<User>> userListType =
    new ParameterizedTypeReference<List<User>>() {};

Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(userListType);
~~~

The trailing braces create an anonymous subclass. The List<User> information is declared on that subclass, so Spring can read the parameterized Type via reflection. If you merely try new ParameterizedTypeReference<List<User>>() without an anonymous subclass body, Java does not allow instantiating this abstract class directly.

You can write it inline at the call site:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(new ParameterizedTypeReference<List<User>>() {});
~~~

The type reference object only describes the target type. It does not perform data conversion itself and does not replace codecs. Decoding the payload is still handled by codecs configured in RSocket/Spring; the codec must support the data type and payload format in use.

## 3. Using with RSocketRequester

RSocketRequester provides a fluent API for building requests. After declaring the route and outgoing data, retrieveMono or retrieveFlux specifies the desired response type. For generic types, use the overload accepting ParameterizedTypeReference.

~~~java
Mono<ApiResponse<List<User>>> response = requester
    .route("users.search")
    .data(criteria)
    .retrieveMono(
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
    );
~~~

In this example, the target type is the entire ApiResponse<List<User>> structure. Generic information is preserved at both levels: ApiResponse contains List and List contains User. Passing only ApiResponse.class or List.class loses the required parameter information.

If the endpoint returns a multi-element stream, retrieveFlux also has an overload accepting ParameterizedTypeReference:

~~~java
Flux<ApiResponse<User>> events = requester
    .route("users.events")
    .retrieveFlux(
        new ParameterizedTypeReference<ApiResponse<User>>() {}
    );
~~~

Choose Mono or Flux based on the route's response contract: Mono represents at most one result, while Flux represents a sequence of elements. ParameterizedTypeReference specifies the type of each result; it does not decide cardinality or the RSocket interaction model.

## 4. Complete Example of Nested Generic Types

The following example illustrates generic DTOs and how to call them. This is an API illustration snippet; types User, SearchCriteria, and route users.search need to be defined/supported on the server in a real application.

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

import java.util.List;

record User(Long id, String name) {}

record ApiResponse<T>(
    boolean success,
    T data,
    String message
) {}

record SearchCriteria(String keyword) {}

class UserClient {
    private final RSocketRequester requester;

    UserClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<ApiResponse<List<User>>> search(String keyword) {
        SearchCriteria criteria = new SearchCriteria(keyword);

        return requester
            .route("users.search")
            .data(criteria)
            .retrieveMono(
                new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
            );
    }
}
~~~

The method's return type is Mono<ApiResponse<List<User>>>. The generic type passed to retrieveMono must match the payload structure sent by the server. If the server actually returns ApiResponse<User> or List<User> directly, declare that exact type instead of casting to what the client wishes for.

## 5. Comparing Class<T> and ParameterizedTypeReference<T>

| Need | How to pass type | Example |
|---|---|---|
| Concrete type without generics | Class<T> | User.class |
| String or simple type | Class<T> | String.class |
| List with element type | ParameterizedTypeReference<T> | new ParameterizedTypeReference<List<User>>() {} |
| DTO wrapping a generic type | ParameterizedTypeReference<T> | ApiResponse<User> |
| Nested generics | ParameterizedTypeReference<T> | ApiResponse<List<User>> |

Rule of thumb: use Class<T> when the target type is fully represented by a Class. Use ParameterizedTypeReference<T> when you need to preserve generic parameters at runtime.

## 6. Why Can't You Use List.class and Then Cast?

The following snippet compiles, but does not guarantee that elements were decoded into User:

~~~java
Mono<List> raw = requester
    .route("users.all")
    .retrieveMono(List.class);

Mono<List<User>> users = raw.cast(List.class);
~~~

Casting here only checks/casts the outer List object. It does not turn each element into a User and does not recover lost generic information. Unchecked casts can hide errors until the application accesses an element and encounters ClassCastException or data processing errors.

Declare the full target type right at the decoding boundary:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(new ParameterizedTypeReference<List<User>>() {});
~~~

This gives the codec enough type information to convert the payload, while helping the compiler type-check the rest of the program.

## 7. Reusing Type References

If a generic type is used in multiple places, you can declare a constant to avoid repeating anonymous subclasses:

~~~java
private static final ParameterizedTypeReference<ApiResponse<List<User>>>
    USER_LIST_RESPONSE_TYPE =
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {};

Mono<ApiResponse<List<User>>> search(SearchCriteria criteria) {
    return requester
        .route("users.search")
        .data(criteria)
        .retrieveMono(USER_LIST_RESPONSE_TYPE);
}
~~~

This constant is safe to reuse because ParameterizedTypeReference holds only type information and contains no request state. Each request is still created separately via RSocketRequester.

## 8. Common Errors and How to Check Them

- **Using List.class for List<User>:** element type is lost. Replace with ParameterizedTypeReference<List<User>>.
- **Declaring only the wrapper class:** ApiResponse.class does not represent ApiResponse<User>. Pass the full ApiResponse<User>.
- **Forgetting the anonymous subclass:** use the exact syntax new ParameterizedTypeReference<T>() {} to capture the generic type.
- **Casting after receiving data:** casting does not re-decode the payload. Fix the target type in retrieveMono/retrieveFlux.
- **Client type does not match server payload:** check the route contract, DTOs, JSON/CBOR structure, and codecs on both sides.
- **Assuming ParameterizedTypeReference converts data itself:** it only provides type metadata; codecs perform the encode/decode.
- **Choosing the wrong Mono/Flux:** check the route's response model. Generic type and element count are two separate decisions.

When debugging, check the generic type passed to retrieveMono/retrieveFlux, the actual payload structure, and the configured codecs. You can write integration tests with a real RSocket server/client to verify element types after decoding, especially with nested generic DTOs. Do not check only that the outermost object is a List or ApiResponse.

## 9. Key Takeaways

ParameterizedTypeReference bridges the gap caused by type erasure when Spring needs to know a full generic type at runtime. With RSocketRequester, pass this reference to retrieveMono or retrieveFlux to describe the exact response type such as List<User> or ApiResponse<List<User>>. It provides type information for decoding; codecs and the payload contract between client/server must still be compatible.
