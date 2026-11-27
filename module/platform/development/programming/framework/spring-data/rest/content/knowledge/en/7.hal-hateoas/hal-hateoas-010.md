# HAL-FORMS and Action Forms When Supported by Version and Media Type

## 1. What Problem Does HAL-FORMS Solve?

Spring Data REST uses hypermedia to help clients discover an API. In the HAL format, a resource typically contains data and links in the _links property. For example, a people collection may provide self, profile, and search links.

HAL tells the client where it can go, but HAL by itself does not fully describe how to perform a state transition. Just by looking at a link, a client usually cannot tell:

- Which HTTP operations are supported on the resource?
- Does the operation use GET, POST, PUT, PATCH, or DELETE?
- Which URI should the payload be sent to?
- Which fields does the payload need, and which ones are required?
- What data types, constraints, or selectable options do the fields have?

HAL-FORMS adds runtime form descriptions. It keeps resource and link representations close to HAL while adding a _templates property to describe the operations the server wants to advertise.

HAL-FORMS is a separate media type, not another name for HAL. The two formats are not interchangeable merely because their structures look similar.

## 2. How Do HAL, HAL-FORMS, and ALPS Differ?

| Format | Media type | Role |
|---|---|---|
| HAL | application/hal+json | Represents resources, embedded resources, and links for navigation |
| HAL-FORMS | application/prs.hal-forms+json | Represents resources, links, and templates describing how to submit operations |
| ALPS | application/alps+json | Describes the semantic profile of resources and state transitions at a conceptual level |

Minimal HAL example:

~~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    },
    "collection": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~~

The client knows the URIs of the item and collection, but has no form describing how to update the item.

The same resource in HAL-FORMS can additionally include templates:

~~~~json
{
  "firstName": "Frodo",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    }
  },
  "_templates": {
    "default": {
      "title": "Update person",
      "method": "put",
      "contentType": "application/json",
      "properties": [
        {
          "name": "firstName",
          "prompt": "First name",
          "required": true,
          "type": "text"
        }
      ]
    },
    "partiallyUpdatePerson": {
      "title": "Partially update person",
      "method": "patch",
      "contentType": "application/merge-patch+json",
      "properties": [
        {
          "name": "firstName",
          "required": false,
          "type": "text"
        }
      ]
    }
  }
}
~~~~

A HAL-FORMS client can read the templates, build an appropriate form, collect values, and send a request using the described method, target, and content type. HAL-FORMS does not generate HTML UI automatically; the client must understand this format and decide how to render the form.

## 3. Content Negotiation: Clients Must Request the Right Media Type

The media type of HAL-FORMS is:

~~~~http
application/prs.hal-forms+json
~~~~

Clients request this representation using the Accept header:

~~~~http
GET /people/1 HTTP/1.1
Host: api.example.com
Accept: application/prs.hal-forms+json
~~~~

If the server and message converters support HAL-FORMS, the response may contain:

~~~~http
HTTP/1.1 200 OK
Content-Type: application/prs.hal-forms+json
~~~~

When a client requests HAL:

~~~~http
GET /people/1 HTTP/1.1
Host: api.example.com
Accept: application/hal+json
~~~~

the server returns a regular HAL representation. Clients should not request HAL-FORMS and assume every response contains _templates; the server can only advertise affordances that have been registered and are permitted to be shown.

Distinguish the two headers when submitting a form:

- **Accept** describes the response format the client wants to receive.
- **Content-Type** describes the payload format the client is sending.

Example of a client sending JSON to create a resource and wanting a HAL-FORMS response:

~~~~http
POST /people
Accept: application/prs.hal-forms+json
Content-Type: application/json

{
  "firstName": "Frodo"
}
~~~~

If there is no compatible converter or configuration for the requested media type, the server may reject content negotiation (commonly 406 Not Acceptable). If the submitted body has a Content-Type not accepted by the endpoint, the request may fail with 415 Unsupported Media Type. Inspect the actual responses and endpoint configuration rather than assuming support merely because a HAL-FORMS dependency is on the classpath.

## 4. Enabling HAL-FORMS Support in Spring HATEOAS

Spring HATEOAS provides support for rendering representation models as HAL-FORMS. Example configuration used in the Spring HATEOAS documentation:

~~~~java
@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL_FORMS)
public class HypermediaConfiguration {
}
~~~~

The corresponding imports live in Spring HATEOAS, including EnableHypermediaSupport and HypermediaType. In a Spring Boot or Spring Data REST application, check the auto-configuration and message converters already registered by your version before adding manual configuration. Avoid registering duplicate converters or hypermedia configurations without checking.

Several things to verify in your dependency tree:

- Which Spring Data release train version the Spring Boot version manages.
- Whether the Spring Data REST and Spring HATEOAS versions are compatible with each other.
- Whether Spring HATEOAS includes the corresponding HAL-FORMS module/converter.
- Whether MVC message converters accept application/prs.hal-forms+json.
- Whether the endpoint actually returns Content-Type HAL-FORMS when the client sends the corresponding Accept header.

Do not arbitrarily upgrade Spring HATEOAS alone alongside the Spring Boot BOM. Use the dependency management of the Spring Boot or Spring Data BOM to keep modules on the same release train, unless the project has a clear reason and has tested compatibility.

## 5. Affordances as the Source for Form Generation

HAL-FORMS templates are generated from affordances. An affordance describes an operation that can be performed in relation to a resource or link, typically derived from a Spring MVC/WebFlux controller method.

Metadata from the target method can provide:

- URI and HTTP method.
- Input payload type.
- Media types accepted by the method.
- Payload properties.
- Validation constraints and display metadata for each property.

Example of a controller with full update and partial update operations:

~~~~java
@RestController
class PersonController {

    @PutMapping(path = "/people/{id}", consumes = "application/json")
    Person update(
            @PathVariable Long id,
            @Valid @RequestBody PersonInput input) {
        // update resource
        return ...;
    }

    @PatchMapping(
            path = "/people/{id}",
            consumes = "application/merge-patch+json")
    Person partiallyUpdate(
            @PathVariable Long id,
            @RequestBody PersonPatch input) {
        // partial update
        return ...;
    }
}
~~~~

A representation model can attach the affordances of both methods to the person's self link. When rendered as HAL-FORMS, the affordances become two templates, such as default for PUT and partiallyUpdate for PATCH.

Example resulting structure:

~~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/1"
    }
  },
  "_templates": {
    "default": {
      "method": "put",
      "contentType": "application/json",
      "properties": [
        { "name": "firstName", "required": true },
        { "name": "lastName", "required": true }
      ]
    },
    "partiallyUpdate": {
      "method": "patch",
      "contentType": "application/merge-patch+json",
      "properties": [
        { "name": "firstName", "required": false },
        { "name": "lastName", "required": false }
      ]
    }
  }
}
~~~~

If there is only one template, the template name is usually default. When multiple operations exist, templates can carry affordance names so clients can distinguish them.

## 6. Attaching Affordances to Spring Data REST Resources

Spring Data REST publishes repository resources, but having collection/item endpoints does not mean all operations automatically get HAL-FORMS templates.

Spring Data REST and Spring HATEOAS integration documentation starting with Spring Data Pascal describes rendering affordances as HAL-FORMS. However, integration examples also show that forms do not automatically appear for every repository operation. The application must explicitly attach affordances to the links it wants to advertise.

One approach is using a RepresentationModelProcessor to enrich a root resource link with an affordance. The example below attaches an order creation operation to the orders link:

~~~~java
@Component
class RootResourceModelProcessor
        implements RepresentationModelProcessor<RepositoryLinksResource> {

    @Override
    public RepositoryLinksResource process(RepositoryLinksResource model) {

        var affordance = afford(
            methodOn(OrderController.class)
                .placeOrder(null, null, null)
        );

        return model.mapLink(
            LinkRelation.of("orders"),
            link -> link.andAffordance(affordance)
        );
    }
}
~~~~

Controller accepting the payload for the creation operation:

~~~~java
@BasePathAwareController
class OrderController {

    @PostMapping(path = "/orders", consumes = "application/json")
    ResponseEntity<?> placeOrder(
            @Valid @RequestBody OrderInput input,
            Errors errors) {
        // validate and execute order creation logic
        return ...;
    }
}
~~~~

In this example, the affordance references the placeOrder method. Spring HATEOAS uses the mapping and payload type to build the operation description. When a client requests HAL-FORMS at the root resource, the template can be attached to the orders link, with its target pointing to the order creation endpoint.

Points to note:

- RepresentationModelProcessor only enriches representations; it does not create new endpoints.
- The referenced method must actually exist and be routed by Spring MVC/Spring Data REST.
- The input DTO determines which fields are described in the form.
- If a link only appears in a certain state, add the affordance conditionally based on that state.
- Check the imports and RepositoryLinksResource type against your project's Spring Data REST version.

When business logic does not fit pure CRUD, a custom controller and DTO are often a good way to describe the operation's exact payload. For example, placing an order might require a list of product URIs and a delivery location, rather than letting clients submit the entire internal entity.

## 7. Template and Field Metadata

HAL-FORMS describes metadata at two levels.

### Template attributes

| Attribute | Meaning |
|---|---|
| title | Human-friendly title for the operation |
| method | HTTP method used when submitting, such as post, put, patch, or delete |
| target | URI receiving the request; only needs rendering when different from the link the affordance is attached to |
| contentType | Media type of the request body accepted by the server |
| properties | List of fields the client sends in the payload |

### Property attributes

| Attribute | Meaning |
|---|---|
| name | Property name in the payload |
| prompt | Prompt label for the user |
| placeholder | Example or formatting hint for the value |
| type | Suggested input type, such as text, number, date, email |
| required | Whether the field is required |
| readOnly | Read-only field, not editable in the form |
| regex | Validation pattern for the value |
| min / max | Numeric value bounds or range limits |
| minLength / maxLength | String length bounds |
| options | Valid choices, either inline or fetched from another resource |

Spring HATEOAS can infer part of this metadata from the payload type, accessors, and validation annotations. Example:

~~~~java
public class PersonInput {

    @NotBlank
    @Size(max = 80)
    private String firstName;

    @Email
    private String email;

    @Pattern(regexp = "[0-9]{10}")
    private String phoneNumber;

    @NotNull
    private LocalDate birthDate;
}
~~~~

Annotations such as NotNull, Pattern, Size, Min, and Max can contribute to describing required, regex, min/max, or maxLength in the template. Java types and input type configuration can also be translated into appropriate types for clients.

This metadata assists UI generation and client-side input checks. The server must still validate payloads upon receiving requests. Never treat required or regex fields in HAL-FORMS as a security boundary.

## 8. Configuring Options for Fields

A field may need to restrict selectable values, such as shippingMethod or location. HAL-FORMS supports two ways of describing options.

**Inline options** fit small, rarely changing sets of values:

~~~~java
@Configuration
class HalFormsOptionsConfiguration {

    @Bean
    HalFormsConfiguration halFormsConfiguration() {
        return new HalFormsConfiguration()
            .withOptions(
                OrderInput.class,
                "shippingMethod",
                metadata -> HalFormsOptions.inline("Standard", "Express")
            );
    }
}
~~~~

Clients can render a dropdown or select control with the declared choices.

**Remote options** fit dynamic, long, or data-dependent lists:

~~~~java
HalFormsOptions.remote(
    Link.of("/shipping-methods{?q}").withRel("options")
)
~~~~

The template can provide a URI template so the client fetches the list of choices when needed. The options resource typically returns scalar values or value/prompt pairs to separate the submitted value from the display label.

When using remote options, verify:

- Whether the options URI is accessible to the client under current authentication.
- Whether paging or filtering is available when the list is large.
- Whether the value matches the format accepted by the endpoint.
- Whether the server re-validates the choice upon submission.

## 9. Localizing title, prompt, and placeholder

Display values such as title, prompt, and placeholder can be internationalized using the resource bundle used by Spring HATEOAS (by default configurable via the rest-messages bundle).

Example:

~~~~properties
_templates.default.title=Create person
_templates.updatePerson.title=Update person
firstName._prompt=First name
firstName._placeholder=Enter your first name
email._prompt=Email address
~~~~

You can use generic keys, class-name-prefixed keys, or fully qualified class-name keys to avoid property collisions across payload types. When multiple templates exist, the specific affordance name identifies the corresponding title.

Choose prompts that are clear for API users while keeping field names aligned with the payload accepted by the endpoint. Clients can display prompts instead of exposing technical property names.

## 10. Distinguishing HAL-FORMS Forms from HAL Explorer

HAL-FORMS is a hypermedia representation format. HAL Explorer is a client application that can read such representations and generate an API exploration UI.

HAL Explorer can:

- Follow HAL links and URI templates.
- Display available HTTP operations.
- Use Spring Data REST profile/JSON Schema metadata to generate input fields for some HAL responses.
- Read _templates from HAL-FORMS to display forms and described constraints.
- Display options and validation metadata provided by templates.

Do not confuse HAL Explorer building a form from Spring profile/JSON Schema with the server returning HAL-FORMS. Those are two different sources of metadata:

- HAL + Spring Data REST profile/JSON Schema: the client can infer payload structure from metadata.
- HAL-FORMS: the server sends operation templates directly via _templates.

HAL Explorer is useful during API development and testing. In production applications, the client may be a web frontend, a mobile app, or another service, as long as the client understands HAL-FORMS.

## 11. Testing HAL-FORMS in an Application

Test step by step to isolate whether an issue lies in dependencies, content negotiation, or affordances.

### Step 1 — Verify default HAL

~~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/
~~~~

Confirm that the response has Content-Type application/hal+json and links inside _links.

### Step 2 — Request HAL-FORMS

~~~~bash
curl -i \
  -H "Accept: application/prs.hal-forms+json" \
  http://localhost:8080/
~~~~

Check:

- Is the status code 2xx?
- Is Content-Type exactly application/prs.hal-forms+json?
- Does the body contain _links and _templates?
- Does the template have the expected method, target or target link, contentType, and properties?

### Step 3 — Verify each operation

For each template, send a request using the described method, target, and contentType. Verify that the server actually routes to the corresponding method and enforces validation.

### Step 4 — Verify fallback

Send Accept: application/hal+json again. Clients that do not support HAL-FORMS must still be able to navigate via HAL links if the API provides that representation.

### Step 5 — Verify state and permissions

Affordances should appear only when the operation is actually available. For example, advertise a payment action only when the order is awaiting payment and the current user has permission to pay. The server must still check permissions and state when the request arrives; hiding a template does not replace authorization.

You can write a MockMvc integration test to verify the response media type and the JSONPath of _templates:

~~~~java
mockMvc.perform(get("/people/1")
        .accept("application/prs.hal-forms+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/prs.hal-forms+json")))
    .andExpect(jsonPath("$._templates").exists());
~~~~

If the test does not see _templates, verify whether an affordance is attached to the link, whether the controller method mapping is correct, whether the converter is registered, and whether the HATEOAS version supports this format.

## 12. Common Mistakes

| Symptom | Possible cause | How to check |
|---|---|---|
| Response is always HAL | Client sent HAL Accept, or HAL-FORMS is not configured | Inspect request Accept and response Content-Type |
| 406 Not Acceptable | No converter/handler matches the requested media type | Check Spring HATEOAS version and message converters |
| HAL-FORMS response has no _templates | Resource has no affordances attached or no applicable operations | Check RepresentationModelProcessor and affordances |
| Template exists but fields are missing | Input DTO or payload metadata was not inferred as expected | Check @RequestBody type, accessors, and validation annotations |
| Incorrect required fields | Validation annotations or template type does not reflect the contract | Check @NotNull, @NotBlank, and PUT/PATCH semantics |
| Form submission gets 415 | Submitted Content-Type does not match endpoint consumes | Read contentType in the template and controller mapping |
| Form submission gets 400 | Malformed payload structure or validation failed | Read binding/validation errors from the response |
| Client does not render the form | Client does not support HAL-FORMS or does not read _templates | Try HAL Explorer or a client with a HAL-FORMS parser |

Another major mistake is adding a dependency and expecting every CRUD operation to get a form automatically. The dependency only provides the technical capability; the server still needs affordances attached to resources and converters capable of rendering them.

## 13. Limitations and Design Considerations

- HAL-FORMS describes operations; it does not execute operations on behalf of the client.
- Templates are not HTML forms; the client must render them and send HTTP requests itself.
- Not every resource needs a form. Advertise only transitions appropriate to the business state.
- A form describes input payloads, but it does not replace business documentation, authorization, or server-side validation.
- HAL-FORMS does not automatically represent every CRUD operation. Especially with Spring Data REST, explicitly add affordances when forms are needed for custom operations.
- Do not attach affordances to unrelated links or point to methods that are not publicly routed.
- Keep HAL representations for simple clients; use HAL-FORMS only when clients need operation metadata and can consume the format.
- Verify compatibility for your active release train. Spring HATEOAS and Spring Data REST documentation may describe different versions; do not copy an old example verbatim into every Spring Boot version.

## 14. Conclusion

HAL provides links for clients to discover resources. HAL-FORMS extends representations with _templates to describe the method, target, content type, and fields of an operation. Spring HATEOAS builds those templates from affordances and input payload metadata; Spring Data REST can integrate this mechanism when supported by version and configuration.

To provide action forms in an API, ensure three conditions are met: the server supports the application/prs.hal-forms+json media type, resources have affordances attached for target methods, and clients know how to read _templates. Afterward, clients still send normal requests and the server remains responsible for validating data, business state, and access permissions.

## References

- [Spring HATEOAS Reference — HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/#mediatypes.hal-forms)
- [Spring HATEOAS Reference — Affordances](https://docs.spring.io/spring-hateoas/docs/2.5.1/reference/html/#server.affordances)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference — HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html)
- [Spring RESTBucks in 2021 — Advertising the order creation using HAL-FORMS](https://odrotbohm.github.io/2021/04/Spring-RESTBucks-in-2021/)
- [HAL-FORMS Media Type Specification](https://rwcbook.github.io/hal-forms/)
