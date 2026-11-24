# Placing Metadata on Interfaces, Base Classes, and Overridden Methods

In a Spring Boot application, controllers can be structured using interfaces, abstract base classes, and concrete implementation classes. This structure helps share HTTP contracts across multiple controllers or separate API declarations from business logic. With **springdoc-openapi**, metadata such as summary, description, tags, operationId, parameters, and responses can be declared at different positions in the type hierarchy.

The issue to watch out for is that Java and Spring do not look up annotations in quite the same way. Annotations on overridden methods are not automatically inherited under standard Java rules. Spring and springdoc have mechanisms to search for annotations on interfaces or parent methods in certain cases, yet the result depends on annotation type, declaration location, and library version. Therefore, place metadata intentionally and verify the OpenAPI specification after the application starts.

## 1. Types of Metadata That Can Be Placed on Controllers

An OpenAPI operation typically needs the following categories of information:

| Metadata | Commonly Used Annotation | Scope |
| --- | --- | --- |
| API group name and description | **@Tag** | Controller, interface, or operation |
| Operation summary and description | **@Operation** | Endpoint method |
| Operation identifier | **operationId** in **@Operation** | Per operation; must be unique in the document |
| Parameters | **@Parameter**, **@Parameters** | Method parameters |
| Request body | OpenAPI **@RequestBody**, **@Content** | Operation |
| Responses | **@ApiResponse**, **@ApiResponses** | Operation or shared response groups |
| Schema | **@Schema** | DTO, field, parameter, or return type |
| Hide endpoint or component | **@Hidden** | Controller, method, or supported component |

Springdoc reads these annotations alongside Spring MVC or WebFlux mappings to create operations. Mappings such as **@GetMapping**, **@PostMapping**, and **@RequestMapping** determine the path and HTTP method; OpenAPI annotations add semantic meaning and contract details.

You can organize following these principles:

- Interfaces describe shared contracts implemented by controllers.
- Base classes hold behavior or metadata genuinely shared across child controllers.
- Overridden methods describe specific details when a controller needs to change an operation's content or semantics.
- Concrete controller classes define the Spring bean, tags, and mappings at the scope fitting the design.

There is no need to repeat all annotations across every layer. Duplication increases the risk of summaries, responses, or parameters drifting out of sync between declaration sites.

## 2. Distinguishing Annotation Inheritance in Java from Springdoc Scanning

### Java rules to remember

Java annotations have retention and target policies determining where they can be placed and when they can be read. Annotations intended to be read at runtime typically need **@Retention(RetentionPolicy.RUNTIME)**.

The **@Inherited** annotation only affects class-level annotations when a subclass extends a superclass. It does not make annotations on an interface automatically appear on implementing classes, nor does it make annotations on a parent method automatically appear on overridden methods.

Example:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ApiArea {
    String value();
}

@ApiArea("Orders")
class BaseController {}

class OrderController extends BaseController {}
~~~

In the example, Java reflection can find **@ApiArea** on the subclass because the annotation is marked **@Inherited** and the relationship is class inheritance. If **@ApiArea** is placed on an interface and **OrderController implements OrderApi**, the **@Inherited** rule does not apply.

Similarly, annotations on a superclass method are not automatically copied by Java onto an overriding method:

~~~java
class BaseController {
    @Operation(summary = "Read resource")
    public ResourceView findById(UUID id) {
        throw new UnsupportedOperationException();
    }
}

class ResourceController extends BaseController {
    @Override
    public ResourceView findById(UUID id) {
        return service.findById(id);
    }
}
~~~

The **ResourceController.findById** method does not automatically inherit the **@Operation** annotation just because of **@Override**. That is a Java rule; springdoc's ability to look up metadata on parent methods is a separate processing step.

### Where can Springdoc find metadata?

Springdoc supports reading many OpenAPI annotations on controller interfaces and methods declared on interfaces. This is useful when an interface represents the API contract while the implementation class holds only business logic. Spring Framework also has merged-annotation lookup mechanisms across certain types and methods in a hierarchy.

However, do not assume every annotation merges automatically from every location. For example:

- **@Operation** on an interface method can be read by springdoc for the endpoint implementing the interface in supported versions.
- **@Parameter** and other OpenAPI annotations on interface parameters should be verified in the generated specification.
- Metadata on superclass or abstract methods may be found when springdoc resolves inherited methods; an overriding method with its own annotation can alter the outcome.
- **@Tag** on an interface, superclass, and concrete controller may produce different tags on the operation. Do not assume tags are concatenated or overridden in a desired way.
- Spring mappings and OpenAPI metadata are two distinct layers of information. An endpoint can be mapped properly by Spring while descriptive annotations are still missing from OpenAPI.

When using inheritance structures, treat the JSON generated at **/v3/api-docs** as the final result to verify. Do not rely solely on code compiling or endpoints executing.

## 3. Placing the Contract on a Controller Interface

Placing metadata on an interface works well when multiple implementations share a contract or when keeping API declarations separate from business logic. Spring MVC supports declaring mappings on controller interfaces; the implementation class is a bean annotated with **@RestController**.

Example interface describing an orders API:

~~~java
import java.util.UUID;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;

@Tag(
    name = "Orders",
    description = "Look up and manage orders"
)
@RequestMapping("/api/orders")
public interface OrderApi {

    @Operation(
        operationId = "getOrderById",
        summary = "Get order information",
        description = "Returns details of an order by identifier."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Order found",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Order not found"
        )
    })
    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    OrderView getById(
        @Parameter(
            name = "id",
            description = "Order identifier",
            required = true,
            in = ParameterIn.PATH,
            example = "2f3c8e5d-8e7b-4a90-ae11-4a1c1f0d2b33"
        )
        @PathVariable("id") UUID id
    );
}
~~~

The implementation class provides the logic:

~~~java
@RestController
@RequiredArgsConstructor
public class OrderController implements OrderApi {

    private final OrderService orderService;

    @Override
    public OrderView getById(UUID id) {
        return orderService.findById(id);
    }
}
~~~

In this example:

- **@RequestMapping** on the interface sets the URL prefix for the contract.
- **@GetMapping** on the interface method declares the method, path, and media type.
- **@Tag** groups the operation under Orders.
- **@Operation** provides operationId, summary, and description.
- **@ApiResponses** describes meaningful responses.
- **@Parameter** describes the path parameter.
- The implementation class does not duplicate mappings or OpenAPI metadata.

In Springdoc versions supporting interface annotations, the generated document picks up this information for the implemented endpoint. Verify that the **GET /api/orders/{id}** operation has the expected tag, summary, parameter, and responses.

If annotations on an interface are not recognized in your project's setup or version, you can move the necessary metadata onto the concrete controller method. Before doing so, verify whether Spring actually resolves the endpoint mapping from the interface; mapping and OpenAPI metadata issues must be diagnosed separately.

### Do not declare duplicate mappings in two places

When choosing an interface as the contract, keep related mappings on the interface and let the implementation class focus on logic. Avoid placing a **@GetMapping** on the interface and another mapping on the implementation intending to add paths. Mappings in multiple locations can produce unexpected results or prevent Spring from resolving a unique mapping.

If the project requires mappings on the implementation, you can move both mappings and OpenAPI metadata to that method. What matters is keeping one clear source of declaration and verifying the final path/method.

## 4. Using a Base Class to Share Operations

A base class fits when multiple child controllers genuinely share a common behavior or endpoint. For instance, multiple resource groups might expose a status or version endpoint. A public mapped method on the base class can be discovered by Spring MVC as an inherited method of the child controller.

Example:

~~~java
public abstract class BaseStatusController {

    @Operation(
        operationId = "getServiceStatus",
        summary = "Get service status",
        description = "Returns the operational status of the component."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Service status",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = StatusView.class)
        )
    )
    @GetMapping(
        value = "/status",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public StatusView status() {
        return currentStatus();
    }

    protected abstract StatusView currentStatus();
}
~~~

A concrete controller inherits the endpoint:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
public class OrderController extends BaseStatusController {

    @Override
    protected StatusView currentStatus() {
        return new StatusView("UP", "orders");
    }
}
~~~

Spring MVC can treat the inherited public method as a handler method on the concrete controller. Springdoc can read **@Operation** and **@ApiResponse** placed on that inherited method. The expected result is the **GET /api/orders/status** operation documented in OpenAPI.

A base class should not become a dumping ground for every annotation merely for reuse. Only lift metadata to the superclass when its content holds true for every subclass. If each controller has a different response or meaning, declare it on the respective controller or interface.

### Watch out for operationId when reusing methods

**operationId** must be unique within an OpenAPI document. If the same base class method is inherited by multiple controllers, springdoc may generate multiple operations from the same metadata. A static operationId placed on the base class can cause duplicates.

You can address this by:

- Avoiding a shared operationId on the base class when multiple controllers inherit the endpoint.
- Setting distinct operationIds on concrete methods or interfaces when needed.
- Splitting documentation groups if the APIs genuinely belong to separate contracts and are not published together.
- Checking all **paths** and operationIds after generating OpenAPI to detect collisions.

Do not rely on auto-generated Java method names as stable operationIds across method renames or code refactorings.

## 5. Metadata on Overridden Methods

When a subclass overrides a base class method or implements an interface method, you may need to update summary, description, responses, or tags for that specific endpoint.

Example of a base class providing default behavior and metadata:

~~~java
public abstract class BaseResourceController {

    @Operation(
        summary = "Get resource",
        description = "Returns a resource by identifier."
    )
    public abstract ResourceView findById(UUID id);
}
~~~

The order controller overrides the method and adds a specific mapping:

~~~java
@RestController
@RequestMapping("/api/orders")
@Tag(name = "Orders")
public class OrderController extends BaseResourceController {

    @Override
    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Get order by ID",
        description = "Only returns orders within the current user's scope."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Order found",
            content = @Content(
                mediaType = MediaType.APPLICATION_JSON_VALUE,
                schema = @Schema(implementation = OrderView.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Order does not exist or is inaccessible"
        )
    })
    public OrderView findById(@PathVariable UUID id) {
        return orderService.findVisibleById(id);
    }
}
~~~

In this example, **@Operation** on the overridden method is the specific metadata for the order endpoint. When an overriding method has its own annotation, treat the metadata on the implementing method as the intentional source of truth. Do not assume springdoc merges individual attributes from **@Operation** on the parent class with **@Operation** on the child class into one combined annotation.

If you want to reuse default metadata from the parent method, you can omit re-declaring OpenAPI annotations on the overriding method and verify whether your springdoc version finds the annotation on the overridden method. If results are inconsistent or confusing for maintainers, declaring full metadata on the concrete method is clearer.

### When should metadata be overridden?

| Component | Keep Shared Metadata When | Override on Concrete Method When |
| --- | --- | --- |
| Summary | Action name is identical across endpoints | Endpoint has a specific purpose |
| Description | Business rules are identical | Scope, preconditions, or permissions differ |
| Response | Same status codes and schemas | Schemas or error branches differ |
| Parameter | Same meaning and constraints | Name, type, or conditions differ |
| Tag | Same API group | Endpoint belongs to a different documentation group |
| OperationId | Only one operation uses it | Multiple operations inherit or implement separately |

When overriding, inspect the entire operation after generating docs. An annotation on a child method can alter summary, tags, or responses without automatically retaining values declared elsewhere.

## 6. Combining Interfaces and Base Classes

A design can use an interface for the API contract and a base class for shared implementation. For instance, the interface defines the endpoint, the base class provides shared logic, and concrete controllers complete the behavior:

~~~java
@Tag(name = "Documents", description = "Document management")
@RequestMapping("/api/documents")
public interface DocumentApi {

    @Operation(
        operationId = "getDocument",
        summary = "Get document information"
    )
    @GetMapping("/{id}")
    DocumentView getDocument(
        @Parameter(description = "Document ID", required = true)
        @PathVariable("id") UUID id
    );
}
~~~

Base class implementing query behavior:

~~~java
public abstract class AbstractDocumentController implements DocumentApi {

    protected abstract DocumentService documentService();

    @Override
    public DocumentView getDocument(UUID id) {
        return documentService().findById(id);
    }
}
~~~

Concrete controller registering the bean:

~~~java
@RestController
public class InternalDocumentController extends AbstractDocumentController {

    private final DocumentService service;

    public InternalDocumentController(DocumentService service) {
        this.service = service;
    }

    @Override
    protected DocumentService documentService() {
        return service;
    }
}
~~~

This design works when Spring MVC picks up the mapping from the interface and the implementing method resolves properly. However, if multiple classes implement **DocumentApi**, each class could create identical operations or duplicate mappings. Decide clearly which class is the registered controller and which APIs are published.

Do not create multiple classes implementing the same controller interface in the same application just to reuse metadata when endpoints share the same method and path. Instead, consider using the interface as the contract for a single controller, or separating APIs with distinct URLs and document groups.

## 7. Metadata on Parameters and Inherited DTOs

Annotations on parameters also require intentional handling. Java does not automatically inherit parameter annotations from an interface or parent method onto an overriding method. If parameters are described on an interface, verify OpenAPI captures the name, location, required flag, description, and example.

Example:

~~~java
@Operation(summary = "Search orders")
@GetMapping
List<OrderView> search(
    @Parameter(
        name = "status",
        description = "Order status",
        example = "PENDING"
    )
    @RequestParam(required = false) String status
);
~~~

If an implementing method overrides and needs to alter parameter semantics, place annotations on the implementing method's parameters or define a separate contract. Then inspect the **parameters** section of the generated operation.

For inherited DTOs, **@Schema** describes data types and properties. Example:

~~~java
@Schema(description = "Basic resource information")
public abstract class BaseResourceView {

    @Schema(description = "Identifier", example = "RES-100")
    private String id;
}

@Schema(description = "Order information")
public class OrderView extends BaseResourceView {

    @Schema(description = "Order status", example = "CREATED")
    private String status;
}
~~~

Springdoc can typically describe inherited properties in the subtype's schema. If Jackson configuration or schema composition changes how serialization works, check **components.schemas** to ensure actual fields are documented. DTO metadata and operation metadata are two different scopes; annotations on a controller interface do not replace DTO schema descriptions.

## 8. Avoiding Annotation Conflicts and Duplication

Certain situations easily create confusing documentation:

**Declaring @Operation on both interface and implementation.** If both places have differing summaries or responses, the result may depend on the library's annotation resolution order. Pick one place as the primary source or declare completely where overriding is needed.

**Declaring @Tag on both interface and controller.** Check whether the operation gets one tag or multiple tags and whether the tag is created in the document-level **tags** section. If you want an endpoint in multiple groups, declare the tag list explicitly on the operation.

**Declaring @ApiResponse on parent and child classes.** Do not assume responses are concatenated automatically. Compare **responses** and ensure every actual status code to publish has the right schema.

**Using the same operationId across multiple controllers.** Assign distinct operationIds or omit static declarations on shared base classes. A unique operationId helps client generators produce stable method names.

**Placing mappings on both interface and overriding method.** Avoid overlapping mappings. Choose a consistent location for declaring mappings and verify endpoints in both Spring MVC and OpenAPI.

**Using @Hidden in the wrong place.** If an inherited method is hidden or overridden, verify the operation is actually hidden as desired. Do not hide endpoints to mask metadata or mapping errors.

## 9. Verifying Inherited Metadata in OpenAPI

After starting the application, fetch the JSON specification:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the operation under test:

~~~bash
jq '.paths["/api/orders/{id}"].get | {
  operationId,
  tags,
  summary,
  description,
  parameters,
  responses
}' openapi.json
~~~

Inspect the referenced schema:

~~~bash
jq '.components.schemas.OrderView' openapi.json
~~~

If the project uses document groups, call the documentation endpoint for that group. If the app changes the API docs path or uses a context path, adjust the URL to match actual configuration.

A helpful verification checklist:

1. Does the operation appear under the expected path and HTTP method?
2. Do summary, description, and operationId come from the expected declaration site?
3. Does the tag have the right name and description?
4. Do parameters have the right name, location, required flag, schema, and example?
5. Do responses include all status codes and schemas?
6. Do DTO schemas include inherited properties and match JSON names after serialization?
7. Are there no duplicate operationIds or duplicated operations caused by multiple controllers implementing the same contract?
8. Does Swagger UI display the operation properly without errors when loading the spec?

You can add automated tests to read **/v3/api-docs** with Jackson and assert fields such as **operationId**, **summary**, **tags**, and **responses**. This catches regressions when upgrading Springdoc or refactoring controllers causes metadata to stop being recognized.

## 10. Recommendations for Choosing Declaration Locations

| Scenario | Preferred Location | Reason |
| --- | --- | --- |
| Multiple implementations share one API contract | Interface | Metadata stays with the contract implemented by the classes |
| Multiple controllers share identical behavior | Base class | Shared endpoint mappings and metadata can be reused |
| Endpoint has specific semantics or responses | Concrete controller method | Metadata sits closest to the actual behavior |
| Tag for a controller | Controller class or API interface | Defines the documentation group at the proper scope |
| Describing fields and data structures | DTO and DTO properties | Schema is tied to the serialized data type |
| Parameter meaningful only to one endpoint | Endpoint method parameter | Keeps description close to how the endpoint receives data |

No single location suits every project. Choose locations based on contract ownership and real reusability, then inspect the OpenAPI output to ensure metadata is neither missing nor duplicated.

## 11. Conclusion

Interfaces, base classes, and overridden methods can all participate in API documentation with Springdoc, yet Springdoc's annotation lookup mechanism must be distinguished from Java's inheritance rules. Place shared metadata where the contract is owned, override explicitly when endpoints have distinct semantics, and avoid duplicate mappings and operationIds. Finally, inspect the generated OpenAPI specification to verify summaries, tags, parameters, responses, and schemas match the controller clients actually call.
