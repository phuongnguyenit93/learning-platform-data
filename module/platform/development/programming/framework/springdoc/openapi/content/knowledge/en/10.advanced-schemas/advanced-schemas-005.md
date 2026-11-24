# Recursive Relationships, Circular References, and Tree Models

Many APIs represent hierarchical data such as product categories, directories, organization charts, permission groups, or nested comment threads. These structures usually have parent-child relationships and can nest across multiple levels. In Java, they are typically modeled by a class with a property referencing its own type or referencing another type in a cycle. In OpenAPI, the corresponding schema uses **`$ref`** to refer back to the defined component.

With **springdoc-openapi**, recursive schemas can be generated from Java DTOs and represented using references inside **`components.schemas`**. However, two concepts must be distinguished:

- **Schema recursion:** a data structure can nest across multiple levels following the same rule.
- **Runtime object circular references:** Java objects point back to each other, causing serializers to loop infinitely if unhandled.

A valid recursive schema does not mean a JSON response is allowed to contain object cycles. JSON is a finite tree structure; to transmit cyclic graph relationships, the API needs conventions that represent links via IDs or explicit references.

## 1. Recursion in Data Models

A data type is recursive when one of its properties can hold a value of the same type, directly or through a collection. For example, a category can contain subcategories:

~~~java
import java.util.List;

public record CategoryNode(
    String id,
    String name,
    List<CategoryNode> children
) {}
~~~

Each **CategoryNode** has a list of **children**, and every element in that list is also a **CategoryNode**. Consequently, a category can have children, grandchildren, and deeper levels without defining a separate Java class for each level.

Example of finite JSON data:

~~~json
{
  "id": "root",
  "name": "Devices",
  "children": [
    {
      "id": "laptop",
      "name": "Laptop",
      "children": [
        {
          "id": "gaming",
          "name": "Gaming laptop",
          "children": []
        }
      ]
    }
  ]
}
~~~

Each branch can keep nesting. The data remains valid JSON because any concrete tree terminates; recursion only describes the capability for variable-depth structure.

Common scenarios using recursive models:

| Domain | Relationship | Example |
| --- | --- | --- |
| Categories | One node has multiple child nodes | Product categories and subcategories |
| Directories | One folder contains other folders | Storage directory tree |
| Comments | One comment has multiple replies | Discussion threads |
| Organization | One unit manages subordinate units | Departments and teams |
| Menus | One item has sub-items | Multi-level navigation menus |

Before designing a schema, determine whether the data is genuinely a tree, a forest of multiple trees, or a graph with shared relationships and cycles. The appropriate representation differs for each.

## 2. Representing Recursive Schemas with $ref

In OpenAPI, you can define a schema in **`components.schemas`**, then reference that same schema from a child property.

Example schema for `CategoryNode`:

~~~yaml
components:
  schemas:
    CategoryNode:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: string
        name:
          type: string
        children:
          type: array
          items:
            $ref: '#/components/schemas/CategoryNode'
~~~

The property **`children.items.$ref`** points back to **`CategoryNode`**. This reference allows the schema to describe arbitrary depth without duplicating definitions at every level.

A response using the schema:

~~~yaml
paths:
  /api/categories/tree:
    get:
      summary: Get category tree
      responses:
        '200':
          description: Category tree
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CategoryNode'
~~~

The **`$ref`** reference is a schema reuse mechanism in the OpenAPI document. It is not special syntax inside the JSON response. Clients receive ordinary nested JSON; OpenAPI-reading tools follow the reference to understand the structure.

A component can reference itself or reference another component to form a reference chain. OpenAPI permits recursive schema references. What matters is that every reference points to an existing component and the resulting structure describes finite data emitted by the server.

## 3. How Springdoc Infers Recursive Schemas from DTOs

Springdoc analyzes return types, DTOs, Jackson annotations, and OpenAPI annotations to build schemas. For a self-referencing DTO like **CategoryNode**, springdoc can generate a component schema and use **`$ref`** for the property of the same type.

Controller example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.media.Content;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CategoryController {

    private final CategoryService categoryService;

    CategoryController(CategoryService categoryService) {
        this.categoryService = categoryService;
    }

    @Operation(
        summary = "Get category tree",
        description = "Returns a root node along with nested subcategories."
    )
    @ApiResponse(
        responseCode = "200",
        description = "Category tree",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = CategoryNode.class)
        )
    )
    @GetMapping("/api/categories/tree")
    CategoryNode getTree() {
        return categoryService.loadTree();
    }
}
~~~

DTO:

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "CategoryNode", description = "A node in the category tree")
public record CategoryNode(
    @Schema(description = "Category ID", example = "laptop")
    String id,

    @Schema(description = "Category name", example = "Laptop")
    String name,

    @Schema(description = "Subcategories")
    List<CategoryNode> children
) {}
~~~

With this structure, springdoc typically generates one **`CategoryNode`** component and sets **`children.items`** to reference that component. The **`@Schema(implementation = CategoryNode.class)`** annotation on the response clarifies the root schema type; there is no need to repeat definitions for each level.

Do not try to declare separate Java classes such as **CategoryLevel1**, **CategoryLevel2**, and **CategoryLevel3** just to represent depth. That approach artificially restricts the structure and makes schemas hard to maintain when business rules allow deeper trees.

## 4. Direct, Indirect, and Multi-Component References

Recursion does not have to be a single class referencing itself. Two or more types can reference each other.

For example, an employee has a manager who is another employee, and a list of direct reports:

~~~java
import java.util.List;

public record EmployeeView(
    String id,
    String name,
    EmployeeView manager,
    List<EmployeeView> reports
) {}
~~~

The schema looks like:

~~~yaml
components:
  schemas:
    EmployeeView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        manager:
          $ref: '#/components/schemas/EmployeeView'
        reports:
          type: array
          items:
            $ref: '#/components/schemas/EmployeeView'
~~~

When two different types reference each other, such as **DepartmentView** containing **EmployeeView** and **EmployeeView** containing **DepartmentView**, OpenAPI can represent them as two components:

~~~yaml
components:
  schemas:
    DepartmentView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        manager:
          $ref: '#/components/schemas/EmployeeView'

    EmployeeView:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        department:
          $ref: '#/components/schemas/DepartmentView'
~~~

This is a circular reference between schema definitions. OpenAPI processing tools must support recursive references to render documentation or generate clients. When working with tools that have limitations on circular schemas, you may need flatter DTOs or ID-based relationships.

## 5. Distinguishing Trees, Graphs, and Object Circular References

A tree has these characteristics:

- There is one root node per tree.
- Each child node has one parent within that tree.
- There are no cycles.
- There is a unique path from the root node to each node.

A graph can have multiple relationships between nodes, nodes referenced by multiple others, or cycles. For example, an employee can join multiple projects; a project has multiple members. This is a many-to-many relationship, not necessarily a tree.

Important distinction:

| Concept | Structure | Commonly suitable representation |
| --- | --- | --- |
| Recursive schema | One type can nest across multiple levels | Self-referencing component via **`$ref`** |
| JSON tree | Finite nested data | Nested objects and arrays |
| Cyclic object graph | Java objects pointing back or in cycles | DTOs with IDs, explicit references, or identity mechanisms |
| Graph with edges | Multiple nodes and connecting relationships | Lists of `nodes` and `edges` using IDs |

Example of a Java object with a circular reference:

~~~java
class Category {
    public String id;
    public Category parent;
    public List<Category> children;
}
~~~

If **`parent.children`** contains the child object and **`child.parent`** points back to the parent object, the in-memory object graph has a cycle. Jackson, serializing by traversing properties, can walk from parent to child and back to parent repeatedly. The result can be a maximum nesting depth error or cycle error instead of finite JSON.

A self-referencing OpenAPI schema does not create a runtime cycle. Infinite loops arise from the actual object graph and serialization rules.

## 6. Designing Tree DTOs to Avoid JSON Cycles

For APIs returning hierarchical trees, the simplest and most controllable approach is a unidirectional DTO from parent to child. Do not put a back-reference to the parent object inside each node; if clients need to know the parent, pass **`parentId`**.

~~~java
public record CategoryNodeView(
    String id,
    String parentId,
    String name,
    List<CategoryNodeView> children
) {}
~~~

JSON:

~~~json
{
  "id": "root",
  "parentId": null,
  "name": "Devices",
  "children": [
    {
      "id": "laptop",
      "parentId": "root",
      "name": "Laptop",
      "children": []
    }
  ]
}
~~~

This model has several benefits:

- JSON has a clear tree structure without backward object references.
- Clients know parent-child relationships via **`parentId`** and **`children`**.
- The schema can be described with a single self-referencing component.
- Depth can be capped when constructing the DTO.
- It does not depend on how Jackson handles bidirectional entity relationships.

If the data is a graph with shared relationships or cycles, consider a **`nodes + edges`** model:

~~~json
{
  "nodes": [
    { "id": "a", "name": "A" },
    { "id": "b", "name": "B" },
    { "id": "c", "name": "C" }
  ],
  "edges": [
    { "from": "a", "to": "b" },
    { "from": "b", "to": "c" },
    { "from": "c", "to": "a" }
  ]
}
~~~

With `nodes` and `edges`, each node is defined only once. Relationships are represented by IDs, avoiding repeated nested objects or JSON cycles. This approach fits better when there are multiple paths, many-to-many relationships, or genuine cycles.

## 7. Handling Bidirectional Entities with Jackson

If you must directly serialize an object graph with bidirectional relationships, Jackson provides several mechanisms. Each mechanism produces a different JSON representation; choose according to the API contract.

### @JsonManagedReference and @JsonBackReference

**`@JsonManagedReference`** marks the parent or forward-serialized side. **`@JsonBackReference`** marks the reverse side and is omitted during serialization to avoid looping back.

~~~java
import com.fasterxml.jackson.annotation.JsonBackReference;
import com.fasterxml.jackson.annotation.JsonManagedReference;

class CategoryEntity {

    public String id;

    @JsonBackReference
    public CategoryEntity parent;

    @JsonManagedReference
    public List<CategoryEntity> children;
}
~~~

With this setup, JSON traverses from parent nodes down to `children` without serializing `parent` back from each child. When deserializing, Jackson can restore the corresponding back reference link.

These annotations are useful for a single parent-child pair. If there are multiple bidirectional relationships in the same class, assign appropriate reference names and ensure each managed/back pair has a distinct identifier. Do not treat them as a universal solution for arbitrary graphs.

### @JsonIgnore

If the API does not need the back-reference field, you can exclude it from JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

class CategoryEntity {

    public String id;
    public List<CategoryEntity> children;

    @JsonIgnore
    public CategoryEntity parent;
}
~~~

This is simple, though `parent` will not appear in JSON. If clients need the parent relationship, include **`parentId`** in a DTO instead of dropping it completely.

### @JsonIdentityInfo

**`@JsonIdentityInfo`** lets Jackson identify objects by ID. The first time an object appears, the serializer writes full properties; subsequent references can write only the object ID.

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
class CategoryEntity {
    public String id;
    public CategoryEntity parent;
    public List<CategoryEntity> children;
}
~~~

JSON can then contain a full object on first appearance and an ID value at subsequent reference sites. The JSON shape is no longer always an object with the same schema in every position; a property may be either an object or a scalar ID depending on where the object first appeared.

This can be difficult to describe with a simple OpenAPI schema. If a public contract requires identity semantics, define the reference type explicitly and use a suitable schema such as **`oneOf`** if both object and ID are genuinely permitted. Do not assume springdoc always infers every JSON variant produced by identity serialization accurately.

## 8. Limiting Tree Depth and Size

Recursive schemas allow multi-level structures, yet practical APIs still need limits to prevent oversized responses, overly deep queries, or excessive memory usage.

Common measures:

- Fetch at most a fixed number of levels via a **`maxDepth`** or **`depth`** parameter.
- Paginate child lists instead of returning an entire large tree in a single response.
- Provide an endpoint to fetch children by **`parentId`** when the tree is very large.
- Cap the maximum number of nodes per request.
- Enforce access control at every branch so unauthorized child data is not leaked.
- Use projection queries to select only needed fields instead of loading the full entity graph.

Example endpoint allowing a depth limit:

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/categories/tree")
CategoryNodeView getTree(
    @RequestParam(defaultValue = "3") @Min(1) @Max(8) int maxDepth
) {
    return categoryService.loadTree(maxDepth);
}
~~~

OpenAPI should document the **`maxDepth`** parameter, its default value, and its bounds:

~~~yaml
parameters:
  - name: maxDepth
    in: query
    required: false
    description: Maximum number of levels from the root node
    schema:
      type: integer
      minimum: 1
      maximum: 8
      default: 3
~~~

Schema limits help clients understand the contract, while the server must still validate and enforce limits at runtime.

## 9. Documenting Recursive Schemas with Annotations

Springdoc can infer self-referencing relationships from Java types. When you need to clarify the component name, description, or collection element type, you can use **`@Schema`** and **`@ArraySchema`**.

~~~java
import java.util.List;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "CategoryNodeView",
    description = "Category node that can contain child nodes of the same type"
)
public record CategoryNodeView(
    @Schema(description = "Node ID", example = "root")
    String id,

    @Schema(description = "Node name", example = "Devices")
    String name,

    @ArraySchema(
        arraySchema = @Schema(description = "List of subcategories"),
        schema = @Schema(implementation = CategoryNodeView.class)
    )
    List<CategoryNodeView> children
) {}
~~~

With a return type that is a list of root nodes:

~~~java
@GetMapping("/api/categories/roots")
List<CategoryNodeView> getRoots() {
    return categoryService.loadRoots();
}
~~~

The response schema is an array whose **`items`** reference **`CategoryNodeView`**. The **`CategoryNodeView`** component itself contains a `children` array referencing the same component.

There is no need to place **`@Schema(implementation = CategoryNodeView.class)`** on every self-referencing property when the Java type is already clear. Add annotations only when you need to control the name, description, examples, or schema type. Afterward, inspect the generated document to avoid accidentally creating duplicate component names or breaking references.

## 10. Circular References Between Schemas and OpenAPI Tools

Schemas can self-reference or form cycles across multiple components. Documentation renderers, client generators, or OpenAPI converters may handle these cases differently.

When encountering errors or incorrect rendering:

1. Verify that OpenAPI JSON defines the component.
2. Check that the target path in every **`$ref`** exists.
3. Verify that the self-referencing component points to the right name and level.
4. Verify that the array schema has **`items`** pointing to the intended component.
5. Check whether the client generator supports recursive models.
6. If a specific tool does not support circular references, consider a flatter DTO or an ID/edges model for that tool.

Example schema check:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
jq '.components.schemas.CategoryNodeView' openapi.json
~~~

The expected result is that the **`children`** property has **`type: array`** and **`items.$ref`** pointing to **`#/components/schemas/CategoryNodeView`**. If springdoc generates an inline schema or uses a different component name, read the actual structure instead of assuming a fixed name.

## 11. Testing Serialization and Documentation

You should test both runtime JSON and OpenAPI. These two tests catch two different classes of bugs.

### Verifying JSON Does Not Loop

Example tree DTO test:

~~~java
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class CategorySerializationTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void serializesFiniteTree() throws Exception {
        CategoryNode node = new CategoryNode(
            "root",
            "Devices",
            List.of(
                new CategoryNode("laptop", "Laptop", List.of())
            )
        );

        String json = objectMapper.writeValueAsString(node);

        assertThat(json).contains("\"id\":\"root\"");
        assertThat(json).contains("\"id\":\"laptop\"");
        assertThat(json).contains("\"children\":[]");
    }
}
~~~

This test confirms the tree DTO serializes into finite JSON. If the DTO uses Jackson annotations or custom serializers, use an `ObjectMapper` configured like the application.

### Verifying OpenAPI Contains the Self-Reference

You can write an integration test fetching **`/v3/api-docs`**, parsing it with Jackson, and inspecting the component:

~~~java
JsonNode openApi = objectMapper.readTree(
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andReturn()
        .getResponse()
        .getContentAsString()
);

JsonNode childrenItems = openApi
    .path("components")
    .path("schemas")
    .path("CategoryNodeView")
    .path("properties")
    .path("children")
    .path("items");

assertThat(childrenItems.path("$ref").asText())
    .isEqualTo("#/components/schemas/CategoryNodeView");
~~~

This snippet assumes the test class already has **`MockMvc`**, **`ObjectMapper`**, and static imports for MockMvc/AssertJ. If the schema is named differently or inlined, adjust the assertion path to match the actual document.

## 12. Common Pitfalls

**Swagger UI shows nested schemas, but the response fails with excessive nesting depth.** Check whether the runtime object graph has back-references. A self-referencing schema is valid, yet bidirectional parent-child objects can create loops when Jackson serializes them. Switch to a unidirectional DTO, use `parentId`, or configure Jackson identity handling properly.

**The schema only displays one level of `children`.** Check whether the collection element type is the recursive type and whether **`items`** references the corresponding component. If different DTOs are used at each level, the schema will not be recursive.

**OpenAPI has a `$ref` pointing to a nonexistent component.** Check component names, **`@Schema(name = ...)`** annotations, and customizers that modified schemas. Every local reference must point to an actual entry in **`components.schemas`**.

**JSON repeats objects or the response is huge.** Inspect the entity graph, lazy relationships, and how the mapper converts entities to DTOs. Apply depth limits, pagination, or on-demand child loading.

**The client generator fails on recursive models.** Identify the limits of your generator. You can publish a flatter DTO or a `nodes`/`edges` model for easier client consumption while keeping the server's internal model.

**`@JsonIdentityInfo` sometimes emits an object and sometimes an ID.** The schema must describe this variation accurately. If clients struggle to handle it, consider designing response DTOs with explicit ID fields and avoiding object identity serialization in public contracts.

## 13. Checklist for Designing Recursive APIs

- [ ] Determine whether the data is a tree, a forest, or a cyclic graph.
- [ ] Use self-referencing DTOs to describe variable-depth trees.
- [ ] Ensure every local **`$ref`** points to a valid component.
- [ ] Distinguish schema circular references from Java object circular references.
- [ ] Avoid returning JPA entities with bidirectional relationships directly without controlling serialization.
- [ ] Choose unidirectional DTOs, `parentId`, or `nodes`/`edges` for complex relationships.
- [ ] If using Jackson identity annotations, verify both JSON shape and the corresponding schema.
- [ ] Bound depth, node count, and query cost.
- [ ] Test actual serialization and OpenAPI JSON.
- [ ] Verify Swagger UI and your client generator's handling of recursive models.

## 14. Conclusion

Recursive schemas allow OpenAPI to describe hierarchical data of variable depth via **`$ref`**. springdoc can infer self-referencing types from Java DTOs and create corresponding components. However, circular references in schemas differ from object graph cycles during Jackson serialization. Choose a tree or graph model suited to the domain, use DTOs with finite JSON structures, control depth, and verify both runtime responses and generated schemas.

## 15. References

- [OpenAPI Specification — Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): Schema Object structure and schema references in OpenAPI.
- [Jackson Annotations — JsonManagedReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html): marks the forward-referenced side in a bidirectional relationship.
- [Jackson Annotations — JsonBackReference](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html): marks the back-reference side during serialization and deserialization.
- [Jackson Annotations — JsonIdentityInfo](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html): represents object identity using IDs.
- [Springdoc OpenAPI documentation](https://springdoc.org/): generating and customizing OpenAPI schemas from Spring Boot applications.
