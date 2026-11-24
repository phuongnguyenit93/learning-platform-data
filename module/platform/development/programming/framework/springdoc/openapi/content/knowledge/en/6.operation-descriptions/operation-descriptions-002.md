# @Tag at the Controller and Operation Levels

When an API has many endpoints, Swagger UI needs a way to group operations so readers can find the right functionality. OpenAPI uses **tags** for this purpose. springdoc-openapi can derive tag information from annotations on controllers, from shared OpenAPI metadata, and from the list of tags declared on each operation.

The two most common places in Spring Boot are:

- **@Tag** placed on a controller class to describe the functional group associated with the controller.
- **@Operation(tags = {...})** placed on a method to assign a group to a specific operation.

The two annotations have related roles but do not completely replace each other. @Tag describes a Tag Object, including its name and metadata such as description; the tags attribute of @Operation attaches tag names to an operation. Understanding this difference helps keep documentation groups consistent and avoids creating duplicate or undescribed groups.

## 1. What is a Tag in OpenAPI?

In OpenAPI, a tag is a label for categorizing operations. Each operation can reference one or more tag names. Interfaces such as Swagger UI typically use these tags to organize endpoints into expandable or collapsible groups.

An OpenAPI document has two important places related to tags:

1. **Root-level tags**: a list of Tag Objects at the document level, usually containing name, description, and additional documentation links.
2. **Operation tags**: a list of tag names attached to each operation under paths.

Abbreviated example:

~~~yaml
tags:
  - name: Books
    description: Operations for managing books
  - name: Authors
    description: Operations for managing authors

paths:
  /api/books:
    get:
      summary: List books
      tags:
        - Books
      responses:
        "200":
          description: List of books
  /api/authors:
    get:
      summary: List authors
      tags:
        - Authors
      responses:
        "200":
          description: List of authors
~~~

The root-level tags section provides metadata for tools to display group names and descriptions. The tags section inside an operation indicates which group the operation belongs to. Both names must match exactly for the Tag Object's metadata to apply properly.

Names in the root-level tags list should be unique. If two Tag Objects use the same name with different descriptions, documentation tools may not know which metadata is authoritative. Maintain one definition per tag name across the entire document.

An operation can have multiple tags. When it does, some documentation UIs may display the operation in multiple groups. Use multiple tags only when an operation genuinely spans multiple domains; do not add tags just to create extra entry points in the UI.

## 2. Using @Tag at the Controller Level

The **io.swagger.v3.oas.annotations.tags.Tag** annotation is commonly placed on a controller class. springdoc uses this information to describe the group associated with the operations belonging to that controller.

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(
    name = "Books",
    description = "Operations for looking up and managing books"
)
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public List<BookResponse> findAll() {
        // ...
        return List.of();
    }

    @GetMapping("/{bookId}")
    public BookResponse findById(@PathVariable UUID bookId) {
        // ...
        return null;
    }
}
~~~

In this example, the **Books** tag describes the functional group of BookController. The operations discovered from @GetMapping are still produced by Spring MVC; @Tag only adds categorization and descriptive information to the OpenAPI document.

Commonly used attributes of @Tag:

| Attribute | Meaning |
|---|---|
| **name** | Tag name; this is the key used to attach the tag to operations |
| **description** | Explains which functionality the endpoint group serves |
| **externalDocs** | Link to supplementary documentation for the group |
| **extensions** | Custom extension metadata following the OpenAPI x-* convention |

Tag names should be concise, stable, and reflect the business domain or resource. For example, **Books**, **Authors**, and **Orders** are clearer than generic names like **Controller1**, **GET APIs**, or **Misc**.

### A controller should have one primary group

If a controller manages a clear resource or functional domain, a single class-level tag keeps the documentation consistent without repeating descriptions on every method.

~~~java
@Tag(name = "Authors", description = "Look up and manage authors")
@RestController
@RequestMapping("/api/authors")
public class AuthorController {

    @GetMapping
    public List<AuthorResponse> findAll() {
        // ...
        return List.of();
    }

    @PostMapping
    public AuthorResponse create(@RequestBody CreateAuthorRequest request) {
        // ...
        return null;
    }
}
~~~

When new endpoints are added to this controller, the controller's tag group continues to describe the same functional domain. If a controller begins to contain multiple unrelated business domains, consider splitting the controller or assigning separate operation-level tags so readers do not have to search through an overly large group.

## 3. Using @Operation tags at the Method Level

**@Tag** is an annotation that describes tag metadata, while the **tags** attribute of **@Operation** is a list of tag names attached directly to an operation. This is a common way to categorize individual endpoints.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @Operation(
        summary = "Search books",
        operationId = "searchBooks",
        tags = {"Books"}
    )
    @GetMapping("/books")
    public List<BookResponse> searchBooks(@RequestParam String keyword) {
        // ...
        return List.of();
    }

    @Operation(
        summary = "Get list of categories",
        operationId = "listCategories",
        tags = {"Categories"}
    )
    @GetMapping("/categories")
    public List<CategoryResponse> listCategories() {
        // ...
        return List.of();
    }
}
~~~

Both methods belong to the same Java class yet are placed into two different documentation groups. This is useful when controllers are organized around technical processing flows, while the documentation needs grouping by the features clients care about.

The tags attribute accepts an array of tag names, not @Tag annotations. For example, **tags = {"Books", "Search"}** attaches the operation to both names. Descriptive metadata for each name should be declared at the document level or with the appropriate @Tag annotation.

### @Tag is not an annotation attached directly to a method

In swagger-annotations, @Tag is designed to describe tag metadata at the type level (and is used inside certain other annotations). To assign tag names to a method operation, use **@Operation(tags = {...})**. Do not place @Tag on a method by guessing from the annotation name; use the proper attribute of @Operation.

Quick distinction:

| Goal | How to declare |
|---|---|
| Describe a controller's tag | @Tag on the controller class |
| Assign an operation to one or more tags | @Operation(tags = {...}) on the method |
| Declare shared tag metadata for the document | tags on @OpenAPIDefinition or OpenAPI bean |

## 4. Combining Tags at the Controller and Operation Levels

An application can use a controller-level tag as the default group, then supplement tags on operations that require finer categorization. Example:

~~~java
@Tag(
    name = "Books",
    description = "Operations related to books"
)
@RestController
@RequestMapping("/api/books")
public class BookController {

    @Operation(
        summary = "Get book information",
        operationId = "getBook",
        tags = {"Books"}
    )
    @GetMapping("/{bookId}")
    public BookResponse get(@PathVariable UUID bookId) {
        // ...
        return null;
    }

    @Operation(
        summary = "Search books by keyword",
        operationId = "searchBooks",
        tags = {"Books", "Search"}
    )
    @GetMapping("/search")
    public List<BookResponse> search(@RequestParam String keyword) {
        // ...
        return List.of();
    }
}
~~~

The searchBooks operation has two tags in its operation metadata. Documentation tools can display the operation under both groups. Depending on the specific configuration and springdoc version, how tags declared on the controller merge with tags on @Operation can affect the final tags list. Therefore, check the tags section in the generated JSON when combining both annotation levels, especially if you want an operation to appear in only one group.

If the goal is to categorize strictly per operation, consider omitting a default tag at the class level and declaring tags explicitly on the methods. If a controller has one primary group and only a few methods need secondary labels, keep the class-level tag and add operation tags intentionally.

### Additional tags do not change routes

Tag annotations do not alter:

- HTTP methods or path mappings.
- How Spring binds path, query, header, cookie, or request body values.
- Access permissions and authentication mechanisms.
- Status codes or response contents.

If you rename a tag, the endpoint can still be called at the same URL. The change only affects how the operation is grouped and the metadata displayed by documentation tools.

## 5. Declaring Shared Tag Metadata with @OpenAPIDefinition

When you want to manage the tag list in a single configuration location, you can use the **tags** attribute of **@OpenAPIDefinition**. This separates group descriptive metadata from controllers:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Library API",
        version = "v1",
        description = "Library management API"
    ),
    tags = {
        @Tag(
            name = "Books",
            description = "Look up and manage books"
        ),
        @Tag(
            name = "Authors",
            description = "Look up and manage authors"
        ),
        @Tag(
            name = "Categories",
            description = "Manage book categories"
        )
    }
)
public class OpenApiConfiguration {
}
~~~

Operations still need matching tag names attached via @Tag on the controller or @Operation(tags = {...}) on the method. Declaring tags at the document level provides shared descriptions; it does not automatically create endpoints or assign all operations into groups.

If the project already declares OpenAPI via a bean, you can define Tag Objects using swagger-models:

~~~java
@Bean
public OpenAPI libraryApi() {
    return new OpenAPI()
        .info(new Info()
            .title("Library API")
            .version("v1"))
        .tags(List.of(
            new io.swagger.v3.oas.models.tags.Tag()
                .name("Books")
                .description("Look up and manage books"),
            new io.swagger.v3.oas.models.tags.Tag()
                .name("Authors")
                .description("Look up and manage authors")
        ));
}
~~~

In the bean example, the fully qualified name **io.swagger.v3.oas.models.tags.Tag** is used to distinguish the Tag model from the **io.swagger.v3.oas.annotations.tags.Tag** annotation. Choose one primary place to manage tag metadata to avoid duplicate, hard-to-maintain definitions.

## 6. Naming and Organization Rules for Tags

A good set of tags helps integrators find endpoints quickly while still reflecting the business structure. You can apply the following principles:

| Principle | Recommended Example | Reason |
|---|---|---|
| Name by resource or business domain | Books, Orders, Payments | Readers immediately recognize the functional group |
| Keep casing consistent across all operations | Always use Books, do not mix Book and books | Prevents generating multiple near-duplicate groups |
| Use short, specific descriptions | Manage books and publication details | Readers understand the group's scope |
| Avoid overly broad tags | Avoid Common, Other, Misc | Broad groups make documentation hard to search |
| Do not create tags by HTTP method | Avoid GET, POST, DELETE | Clients usually search by resource or business domain |
| Use multiple tags selectively | Books and Search when appropriate | Supports multiple perspectives without useless group duplication |

Tag names are matched as strings in the document. Treat differences in casing or whitespace as different names, and standardize on one convention. Do not rename tags arbitrarily between releases if clients rely on the document structure or SDK generation workflows based on group names.

### Tag ordering in the UI

OpenAPI allows declaring a list of tags at the document level. The order of this list may be used by tools to display groups. If ordering is an important requirement, declare tags in the desired order in a centralized configuration location and verify Swagger UI after generating the document.

Do not rely on method declaration order in controllers to dictate group order. Display order also depends on the UI tool, configuration, and version in use.

## 7. Complete Example: Multiple Controllers, Clear Documentation Groups

Suppose a library system has three domains: books, authors, and loans. Each controller describes its primary group using @Tag:

~~~java
@Tag(name = "Books", description = "Look up and manage books")
@RestController
@RequestMapping("/api/books")
class BookController {

    @Operation(
        summary = "List books",
        operationId = "listBooks"
    )
    @GetMapping
    List<BookResponse> list() {
        return List.of();
    }

    @Operation(
        summary = "Search books by title",
        operationId = "searchBooks",
        tags = {"Books", "Search"}
    )
    @GetMapping("/search")
    List<BookResponse> search(@RequestParam String title) {
        return List.of();
    }
}

@Tag(name = "Authors", description = "Look up and manage authors")
@RestController
@RequestMapping("/api/authors")
class AuthorController {

    @Operation(
        summary = "List authors",
        operationId = "listAuthors"
    )
    @GetMapping
    List<AuthorResponse> list() {
        return List.of();
    }
}

@Tag(name = "Loans", description = "Manage book borrowing and return transactions")
@RestController
@RequestMapping("/api/loans")
class LoanController {

    @Operation(
        summary = "Create loan transaction",
        operationId = "createLoan"
    )
    @PostMapping
    LoanResponse create(@RequestBody CreateLoanRequest request) {
        return null;
    }
}
~~~

Expected organizational outcome:

| Tag | Operations |
|---|---|
| Books | listBooks, searchBooks |
| Search | searchBooks if the operation is additionally tagged with this |
| Authors | listAuthors |
| Loans | createLoan |

In Swagger UI, users can look under the Books group for book operations, Authors for author operations, and Loans for borrowing and returning workflows. The searchBooks operation may appear under both Books and Search depending on how the UI handles multiple tags.

To fully describe the name and content of the Search group, add a Tag Object at the document level using @OpenAPIDefinition or an OpenAPI bean. Without supplementary metadata declared, the operation can still carry the Search tag name, but the group description may be absent.

## 8. Reading the Output in OpenAPI JSON

After the application starts, open **/v3/api-docs** to inspect the JSON generated by springdoc. Part of the document may look like:

~~~json
{
  "tags": [
    {
      "name": "Books",
      "description": "Look up and manage books"
    },
    {
      "name": "Search",
      "description": "Search resources"
    }
  ],
  "paths": {
    "/api/books/search": {
      "get": {
        "operationId": "searchBooks",
        "summary": "Search books by title",
        "tags": [
          "Books",
          "Search"
        ],
        "responses": {
          "200": {
            "description": "Success"
          }
        }
      }
    }
  }
}
~~~

Check two parts:

- Does the root-level **tags** array have the right group names and descriptions?
- Does the **paths.*.*.tags** array attach the right tag names to each operation?

If an operation has a tag name but root-level tags does not contain a corresponding Tag Object, the document can still be processed by OpenAPI tools, yet the UI may lack a description or externalDocs for that group. If names do not match, descriptive metadata will not be linked as intended.

You can quickly inspect this with jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '{
  tags: .tags,
  operations: [
    .paths
    | to_entries[]
    | .key as $path
    | .value
    | to_entries[]
    | select(.value.operationId != null)
    | {
        path: $path,
        method: .key,
        operationId: .value.operationId,
        tags: .value.tags
      }
  ]
}'
~~~

If your environment does not have jq, open the JSON directly or use an equivalent OpenAPI inspection tool. The key is verifying the actual output data, because Swagger UI only displays according to the document it receives.

## 9. Common Mistakes

| Symptom | Common Cause | How to Fix |
|---|---|---|
| All endpoints appear under a default group | Operations do not have an appropriate tag yet | Add @Tag on the controller or @Operation(tags = {...}) |
| Two near-identical groups appear | Inconsistent tag names, differing in casing or whitespace | Standardize tag names across the entire API |
| Group has a name but lacks description | Tag Object not declared at document or controller level | Add @Tag or root-level tags |
| One operation appears in multiple groups | Operation has multiple tag names or class and method tags are combined | Check tags in JSON and decide intentionally |
| Placed @Tag on a method and it fails to compile | Annotation does not support method targets | Use @Operation(tags = {...}) |
| Added @Tag but endpoint does not appear | Controller or mapping is not registered by Spring | Check component scan and mappings; tags do not create routes |
| Renaming a group makes documentation hard to find | Tag name changed between releases | Maintain stable names and document any changes |
| Group ordering is not as expected | UI tool uses its own ordering or rules | Check root-level tags and UI configuration |

An important mistake is confusing tags with security. Tags are solely metadata for categorizing documentation. To restrict which users can call an API, you must configure Spring Security, authentication, authorization, and protect documentation endpoints according to deployment requirements.

## 10. Tag Verification Workflow After Configuration

After adding or modifying annotations, perform the following steps:

1. Start the application and confirm the controller is registered by Spring.
2. Open the **/v3/api-docs** endpoint and locate the controller's paths.
3. Check that operations have a tags array and that tag names follow conventions.
4. Check that root-level tags contains Tag Objects with the necessary description or externalDocs.
5. Open Swagger UI to confirm groups and operations render as expected.
6. Check operations with multiple tags to ensure appearing in multiple groups is intentional.
7. If the document is used for SDK generation or CI integration, save a snapshot and review tag changes as part of contract reviews.

For APIs with multiple groups or multiple documents (GroupedOpenApi), inspect each group's documentation endpoint. Tags only organize operations already present in the current document; they do not bring back endpoints excluded by path/package filters.

## Conclusion

Tags help organize operations into functional groups in OpenAPI and Swagger UI. **@Tag** at the controller level provides the group name and description for endpoints belonging to the controller; **@Operation(tags = {...})** attaches one or more tag names to a specific operation. Shared tag metadata can be declared using **@OpenAPIDefinition** or an OpenAPI bean. Keep tag names consistent, separate descriptive metadata from assigning tags to operations, and verify the JSON at **/v3/api-docs** to confirm the document is generated accurately.
