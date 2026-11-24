# Events with Generic Types in Spring

Generic events allow a single event type to represent different data types. For example, the same EntityCreatedEvent family can carry either Person or Organization. Listeners can declare the specific type they care about, allowing Spring to route events based on both the event class and the generic parameter.

The key detail to handle is that Java uses type erasure: generic parameters are usually not fully preserved on an instance at runtime. Spring provides ResolvableType to represent generic types and ResolvableTypeProvider so an event can supply its own type metadata. When metadata is declared properly, listeners can receive the right generic variant without manually checking instanceof or writing multiple conditional branches.

## 1. Why Are Generic Events Needed?

Suppose an application has two data types, Person and Organization. When an entity is created, different modules may want to react:

- The profile module handles when a Person is created.
- The organization module handles when an Organization is created.
- The audit module records every created entity.

If you create separate PersonCreatedEvent and OrganizationCreatedEvent classes, each event has its own class and listener. That approach is clear and fits well when the two events have different semantics.

If the two events genuinely express the same action and differ only in payload type, they can be modeled using one generic class:

- EntityCreatedEvent<Person>
- EntityCreatedEvent<Organization>

This reduces the number of event classes and makes it clear that both are variants of the same contract. A specific listener can declare EntityCreatedEvent<Person>, while a general listener can handle any EntityCreatedEvent.

Do not use generics solely to reduce class count. If PersonCreated and OrganizationCreated have significantly different business rules, data, or lifecycles, two separate events can be easier to read and safer.

## 2. Java's Type Erasure Problem

At compile time, the compiler knows the type T in EntityCreatedEvent<T>. Therefore, the following statement can infer T as Person:

~~~java
Person person = new Person(10L, "An");
EntityCreatedEvent<Person> event =
    new EntityCreatedEvent<>(this, person);
~~~

However, at runtime, Java does not create two separate classes for EntityCreatedEvent<Person> and EntityCreatedEvent<Organization>. Both instances have the same runtime class EntityCreatedEvent. Calling getClass() only reveals the raw class, which is not enough to confirm whether the original generic parameter was Person or Organization.

This means that if Spring only sees the raw event class, it lacks sufficient information to distinguish listeners that differ only in their generic parameter. For example, listeners for EntityCreatedEvent<Person> and EntityCreatedEvent<Organization> may not be filtered as expected if the event does not provide generic metadata.

To solve this, the event needs to supply its full type at runtime.

## 3. ResolvableType and ResolvableTypeProvider

Spring uses ResolvableType to represent a Java type, including generic parameters. ResolvableType can represent raw types, type parameters, nested types, and assignability relationships between types.

Some useful APIs:

- ResolvableType.forClass(MyEvent.class): creates a descriptor for a class.
- ResolvableType.forClassWithGenerics(...): creates a descriptor for a class along with its generic parameters.
- ResolvableType.forInstance(object): infers a type descriptor from an instance.
- getGeneric(): accesses generic parameters.
- resolve(): retrieves the corresponding Java class when resolvable.

ResolvableTypeProvider is an interface that allows an object to supply its own ResolvableType. For a generic event, the event implements this interface and returns the event class together with the actual payload type.

Spring can use this metadata to match the event type against the parameter type of an @EventListener method. A listener declaring EntityCreatedEvent<Person> will match an event carrying Person; a listener declaring EntityCreatedEvent<Organization> will match the Organization variant.

## 4. Creating a Generic Event

The example below uses an event class extending ApplicationEvent and implementing ResolvableTypeProvider. This keeps the event as an explicit ApplicationEvent while supplying generic metadata to Spring.

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public final class EntityCreatedEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T entity;

    public EntityCreatedEvent(Object source, T entity) {
        super(source);
        this.entity = entity;
    }

    public T getEntity() {
        return entity;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
            getClass(),
            ResolvableType.forInstance(entity)
        );
    }
}
~~~

The getResolvableType() method is the crucial part:

1. ResolvableType.forInstance(entity) obtains the runtime type of the payload.
2. ResolvableType.forClassWithGenerics(...) combines the payload type with the event class.
3. Spring receives metadata like EntityCreatedEvent<Person> instead of only EntityCreatedEvent.

Example payloads can be Java records:

~~~java
public record Person(Long id, String name) {}

public record Organization(Long id, String name) {}
~~~

If the payload is Person, the event metadata will describe EntityCreatedEvent<Person>. If the payload is Organization, the metadata will describe EntityCreatedEvent<Organization>.

Do not pass a null payload when relying on instance-based type inference. A null value provides no runtime class to infer the generic parameter; in that case, explicit type metadata must be passed.

## 5. Registering Listeners by Generic Parameter

A listener can declare the exact event variant it handles:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PersonCreatedListener {

    @EventListener
    public void handle(EntityCreatedEvent<Person> event) {
        Person person = event.getEntity();
        System.out.println("Created person: " + person.name());
    }
}
~~~

Another listener can accept only Organization:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrganizationCreatedListener {

    @EventListener
    public void handle(EntityCreatedEvent<Organization> event) {
        Organization organization = event.getEntity();
        System.out.println("Created organization: " + organization.name());
    }
}
~~~

When the event has a complete ResolvableType, Spring can distinguish the two listener methods by their generic parameter. There is no need to write a single listener and check event.getEntity() instanceof Person and instanceof Organization.

You can have a general listener if one behavior applies to every payload:

~~~java
@Component
public class EntityAuditListener {

    @EventListener
    public void handle(EntityCreatedEvent<?> event) {
        Object entity = event.getEntity();
        System.out.println("An entity was created: " + entity);
    }
}
~~~

Use a wildcard when the listener genuinely does not need to know the concrete type. If the listener needs to work with Person or Organization APIs, declare the concrete generic parameter so the compiler assists with type checking.

## 6. Publishing Generic Events

The publisher uses ApplicationEventPublisher just as with regular events:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class EntityService {

    private final ApplicationEventPublisher publisher;

    public EntityService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createPerson(Person person) {
        // Persist person or complete creation logic here.
        publisher.publishEvent(
            new EntityCreatedEvent<>(this, person)
        );
    }

    public void createOrganization(Organization organization) {
        // Persist organization or complete creation logic here.
        publisher.publishEvent(
            new EntityCreatedEvent<>(this, organization)
        );
    }
}
~~~

The diamond operator <> lets Java infer the generic parameter from the constructor argument. The publisher does not need to know which listener will receive the event. Listener selection relies on the type metadata resolved by Spring.

The example above focuses on the event mechanism. In a real application, Person and Organization must be declared in the project, and data persistence must follow the application's transactions and business rules.

## 7. When the Payload Has Nested Generic Types

Using ResolvableType.forInstance(entity) works when the parameter T can be inferred from the payload's runtime class, such as Person or Organization.

However, if the payload is List<Order>, the runtime class usually only indicates ArrayList or List. Due to type erasure, the instance itself does not tell you that the elements inside are Order. ResolvableType.forInstance(orders) cannot fully recover List<Order> from a regular list object alone.

In this case, pass an explicit ResolvableType. For example, a type descriptor for List<Order> can be created as follows:

~~~java
ResolvableType orderListType =
    ResolvableType.forClassWithGenerics(List.class, Order.class);
~~~

The event can store the payloadType metadata passed to its constructor:

~~~java
public final class GenericPayloadEvent<T>
        extends ApplicationEvent
        implements ResolvableTypeProvider {

    private final T payload;
    private final ResolvableType payloadType;

    public GenericPayloadEvent(
            Object source,
            T payload,
            ResolvableType payloadType) {
        super(source);
        this.payload = payload;
        this.payloadType = payloadType;
    }

    public T getPayload() {
        return payload;
    }

    @Override
    public ResolvableType getResolvableType() {
        return ResolvableType.forClassWithGenerics(
            getClass(),
            payloadType
        );
    }
}
~~~

When publishing the event, pass both the data and the metadata:

~~~java
ResolvableType orderListType =
    ResolvableType.forClassWithGenerics(List.class, Order.class);

publisher.publishEvent(
    new GenericPayloadEvent<>(
        this,
        orders,
        orderListType
    )
);
~~~

As a result, the event type is described as GenericPayloadEvent<List<Order>>. A listener can declare GenericPayloadEvent<List<Order>> if it needs to receive payloads with this exact structure.

Explicit metadata is also useful when the payload can be null or when the declared business type matters more than the runtime implementation class. Ensure the metadata accurately reflects the passed-in payload.

## 8. Generic Events and SpEL Conditions Are Two Different Mechanisms

Generic types distinguish event data types at the contract level. For example, EntityCreatedEvent<Person> and EntityCreatedEvent<Organization> represent two distinct payload types.

Conversely, the condition attribute of @EventListener uses a SpEL expression to filter by the event's values or state:

~~~java
@EventListener(condition = "#event.entity.id() > 100")
public void handleLargeId(EntityCreatedEvent<Person> event) {
    // Handle only Person with id greater than 100.
}
~~~

Both mechanisms can be combined:

- The EntityCreatedEvent<Person> parameter restricts the listener to the Person variant.
- condition further filters by Person values, such as ID or status.

Do not use condition to replace generic types when the condition is actually distinguishing payload types. Declaring the type in the method signature is more readable and enables compiler type checking.

## 9. Design and Usage Considerations

**Do not confuse compile-time types with runtime types.** Java can infer EntityCreatedEvent<Person> at compile time, but the instance does not automatically retain all generic parameters. If Spring needs to route by those parameters, the event must supply metadata.

**Do not rely solely on getClass().** getClass() returns the object's runtime class. For a generic class, it does not reveal T. Use ResolvableTypeProvider to provide both the event class and the generic parameter.

**Pay attention to runtime payload types.** ResolvableType.forInstance(entity) infers the object's actual class. If the business logic needs to express a specific interface, supertype, or nested generic type, consider passing an explicit ResolvableType to avoid metadata differing from your design intent.

**Do not assume generics are covariant.** In Java, types like List<Dog> and List<Animal> are not automatically substitutable for each other. When declaring a listener, use the generic parameter that matches the event contract exactly and verify the desired type-matching behavior.

**Keep payload and metadata consistent.** If an event declares payloadType as List<Order> but the actual payload contains another kind of data, listeners may misinterpret the data. Type metadata does not replace input validation.

**Avoid using generic methods to build runtime filters.** An @EventListener method with an unresolved type parameter T generally does not help Spring distinguish specific payload types. When routing by Person or Organization is needed, declare listeners with concrete generic types.

**Do not confuse generic routing with async or transactions.** ResolvableType only assists with event type recognition. It does not decide whether listeners run synchronously or asynchronously, does not alter commit timing, and does not provide delivery guarantees. Those requirements must be configured separately.

## 10. How to Verify Generic Events Work Correctly

When testing in a Spring application, create two listeners with different parameter types and publish both event variants:

1. Publish EntityCreatedEvent<Person> and confirm PersonCreatedListener is invoked.
2. Confirm OrganizationCreatedListener does not handle the Person event.
3. Publish EntityCreatedEvent<Organization> and confirm the opposite result.
4. Confirm a listener using EntityCreatedEvent<?> receives both variants if that is the desired behavior.
5. If the payload has nested generics, verify ResolvableType is constructed from explicit metadata.

If both specific listeners receive every event, check whether the event's getResolvableType() returns the proper generic parameter. If neither listener is called, check the method signature, the published event type, and whether the metadata matches the type declared by the listener.

**Key takeaway:** generic events help reuse a single event contract across multiple payload types. Java type erasure requires events to supply runtime metadata; Spring uses ResolvableType and ResolvableTypeProvider to match that metadata with the listener's generic parameter.