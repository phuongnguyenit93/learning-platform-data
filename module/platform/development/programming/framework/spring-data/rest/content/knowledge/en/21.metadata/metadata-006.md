# Adding Descriptions to Resources, Properties, and Queries with @Description in Spring Data REST

## Objectives

After this lesson, you will be able to:

- Explain the role of descriptive metadata in a hypermedia-driven REST API.
- Use `@Description` to describe domain types and exposed properties.
- Configure descriptions for collection resources and item resources using `@RepositoryRestResource`.
- Describe exported query methods using `@RestResource`.
- Inspect ALPS metadata to verify that descriptions are published to clients.
- Distinguish metadata descriptions from JSON data, validation, and standalone API documentation.

## 1. Why Are Metadata Descriptions Needed?

Spring Data REST automatically publishes repositories as REST resources. A client can follow HAL links to discover collections, items, associations, and search resources. However, resource names or property names do not always fully explain business meaning.

For example, a client sees the `people` resource and the properties `firstName`, `lastName`, `status`. The names help identify the structure, yet leave questions unanswered:

- What objects does the `people` collection contain?
- Does the item resource represent a person or an internal record?
- Which business states does the `status` property represent?
- Does the `by-last-name` query perform an exact match or a partial match?
- What parameters does a query method accept, and what does the result represent?

Spring Data REST provides ALPS (Application-Level Profile Semantics) metadata to describe resource transitions and descriptors. The `@Description` annotation allows placing textual explanations into this metadata.

Metadata descriptions help clients understand the contract and discover the API. They do not alter persisted data, create new endpoints, change HTTP methods, or automatically validate requests.

## 2. What Is @Description?

Annotation to import:

    import org.springframework.data.rest.core.annotation.Description;

Characteristics of `@Description`:

- Can be placed on a type, field, or method.
- Retained at runtime so Spring Data REST can read it when generating metadata.
- Accepts a `String` `value`, which is the textual description.
- The `value` can also be a lookup key in a resource bundle to support internationalization.

Example:

    @Description("A person registered in the address book.")
    public class Person {
        // ...
    }

On a property:

    @Description("The person's given name.")
    private String firstName;

Descriptions should explain the meaning of the resource or property in business terms. Avoid simply repeating the field name, writing overly generic text, or exposing internal implementation details unhelpful to clients.

## 3. Describing Domain Types and Properties

Suppose an application has a `Person` entity with properties `id`, `firstName`, `lastName`, and `status`.

    import jakarta.persistence.Entity;
    import jakarta.persistence.Id;

    import org.springframework.data.rest.core.annotation.Description;

    @Entity
    @Description("A person that can be discovered and managed through the people API.")
    public class Person {

        @Id
        @Description("Stable identifier assigned to this person.")
        private Long id;

        @Description("The person's given name.")
        private String firstName;

        @Description("The person's family name.")
        private String lastName;

        @Description("The person's current business status.")
        private String status;

        protected Person() {
        }

        // Constructors and accessors
    }

The description on the type explains the overall meaning of the representation. Descriptions on each field explain the meaning of the corresponding descriptors in the representation metadata.

If the entity uses JPA property access, you can place `@Description` on the getter instead of the field:

    @Description("The person's family name.")
    public String getLastName() {
        return lastName;
    }

Choose the annotation placement that matches how the domain model declares properties. There is no need to place the same description on both the field and the getter if they represent the same property; duplication makes configuration harder to maintain.

A description does not automatically expose a private property in JSON. Whether a property is serialized still depends on mappings, Jackson, projections, and Spring Data REST exposure configuration.

## 4. Describing Collection Resources and Item Resources

An exported repository typically has two main resource types:

- Collection resource: represents the set of `Person` instances, e.g., `/people`.
- Item resource: represents a single specific `Person`, e.g., `/people/42`.

Use `@RepositoryRestResource` to set separate descriptions for these two resource types:

    import org.springframework.data.repository.CrudRepository;
    import org.springframework.data.rest.core.annotation.Description;
    import org.springframework.data.rest.core.annotation.RepositoryRestResource;

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        collectionResourceDescription =
            @Description("The collection of people available through this API."),
        itemResourceRel = "person",
        itemResourceDescription =
            @Description("A single person and the information exposed for that person.")
    )
    public interface PersonRepository
            extends CrudRepository<Person, Long> {
    }

Attributes to distinguish:

| Attribute | Meaning |
|---|---|
| path | Path of the exported collection resource |
| collectionResourceRel | Relation name used for links to the collection |
| collectionResourceDescription | Description of the collection resource |
| itemResourceRel | Relation name used for links to a single item |
| itemResourceDescription | Description of the item resource |
| exported | Controls whether the repository is exported |

`collectionResourceDescription` and `itemResourceDescription` take a `@Description` annotation, not a plain `String`. Thus, the syntax uses `@Description("...")` inside the `@RepositoryRestResource` configuration.

The collection description should explain the set and its purpose. The item description should explain a single resource. Avoid using the same generic sentence for both if their meanings differ.

## 5. Describing Exported Query Methods

Spring Data REST can export query methods as query method resources under the `search` resource. For example, a repository with a `findByLastName` method:

    import java.util.List;

    import org.springframework.data.repository.query.Param;
    import org.springframework.data.rest.core.annotation.Description;
    import org.springframework.data.rest.core.annotation.RestResource;

    public interface PersonRepository
            extends CrudRepository<Person, Long> {

        @RestResource(
            path = "by-last-name",
            rel = "by-last-name",
            description =
                @Description("Find people whose family name matches the supplied name.")
        )
        List<Person> findByLastName(@Param("name") String lastName);
    }

With the collection path `people` and query path `by-last-name`, the query method resource has the illustrative path:

    GET /people/search/by-last-name?name=Nguyen

In this example:

- `path` changes the path segment of the query method resource.
- `rel` determines the link relation used when generating links.
- `description` provides the description for the query resource in metadata.
- `@Param("name")` specifies the query parameter name the client sends.

`@Description` does not export query methods on behalf of Spring Data repositories. The query method must still be recognized by Spring Data and permitted for export by Spring Data REST. If the method is hidden via `exported = false` or the repository is not exported, adding a description cannot make the endpoint reappear.

The query description should clearly state the search criteria and the meaning of the results. If the query matches the last name exactly, state “matches the supplied name”; if the query searches by prefix or substring, the description must accurately reflect the actual behavior.

## 6. Where Is ALPS Metadata Published?

Spring Data REST provides ALPS metadata for exported repositories. Clients typically find the `profile` link inside a resource's HAL response.

Typical discovery flow:

1. Call `GET` on the application's root resource.
2. Follow the link to the collection resource, such as `/people`.
3. Read the returned `profile` link.
4. Access the profile URI to view metadata descriptions.
5. Optionally send `Accept: application/alps+json` to request the ALPS representation.

Example:

    curl -i -H "Accept: application/alps+json"       http://localhost:8080/profile/people

ALPS describes the repository's representations and transitions. A descriptor can contain `doc` with `value` holding the description text and `format` set to `TEXT`. Abridged example:

    {
      "alps": {
        "version": "1.0",
        "descriptor": [
          {
            "id": "person-representation",
            "doc": {
              "value": "A person that can be discovered and managed through the people API.",
              "format": "TEXT"
            },
            "descriptor": [
              {
                "name": "firstName",
                "doc": {
                  "value": "The person's given name.",
                  "format": "TEXT"
                },
                "type": "SEMANTIC"
              }
            ]
          }
        ]
      }
    }

This is an illustrative structural example. Actual metadata includes additional descriptors, transitions, relationships, and properties discovered by Spring Data REST from the domain model and repository.

ALPS differs from standard HAL responses:

| Aspect | HAL representation | ALPS metadata |
|---|---|---|
| Purpose | Returns resource data and links | Describes API semantics and transitions |
| Primary content | Data, `_links`, embedded resources | Descriptors, `doc`, `type`, transitions |
| Usage | Client reads or manipulates resources | Client discovers the contract and understands resource meaning |
| `@Description` text | Not added as a business field in entity JSON | Can appear in `doc.value` of the corresponding descriptor |

Do not look for `@Description` text in the entity JSON body and conclude the annotation isn't working. Inspect the repository's profile/ALPS metadata instead.

## 7. Using Resource Bundles for Multilingual Descriptions

`@Description.value` can be a key in a resource bundle. This avoids hard-coding display text in annotations when the application needs multiple locales.

For example, a domain type can use a key:

    @Description("person.resource.description")
    public class Person {
        // ...
    }

Text can be provided in the resource bundle configured by the application, such as `rest-messages.properties`:

    person.resource.description=A person registered in the address book.
    person.firstName.description=The person's given name.
    person.lastName.description=The person's family name.

Spring MVC supports locales and resource bundles. Configure the `MessageSource`/resource bundle appropriately for your application version and setup, then verify metadata with the target locale.

Another configuration approach documented by Spring Data REST is using keys prefixed with `rest.description` in `rest-messages.properties`:

    rest.description.person=A collection of people
    rest.description.person.id=Identifier used to address a person
    rest.description.person.firstName=The person's given name
    rest.description.person.lastName=The person's family name

These keys can supply descriptions for representations and properties in ALPS. If the project already has a resource bundle convention, follow that convention to avoid two duplicate sources of descriptions.

Only use resource bundles when text needs to be managed outside source code or when supporting multiple locales. For a small, single-language application, inline `@Description` values are usually simpler.

## 8. Distinguishing @Description from Related Annotations

Annotations in Spring Data REST can appear together while serving distinct roles:

| Annotation | Role |
|---|---|
| `@Description` | Explains the semantics of a resource or property |
| `@RepositoryRestResource` | Configures how a repository is exported, collection/item rels, and descriptions |
| `@RestResource` | Configures path, rel, description, or export state of a resource attached to a repository/method/field |
| `@Param` | Names the query parameter for a query method argument |
| `@Projection` | Defines a custom representation for a domain type |

For example, `@RestResource(path = "by-last-name")` changes the path of the query resource. `@Description` inside the `description` attribute explains what that query does. The two annotations complement each other and do not replace one another.

Similarly, `@Projection` selects which properties are returned in a representation. `@Description` only explains the meaning of a resource/property in metadata; it does not hide or add fields to a projection.

## 9. Testing Metadata Descriptions

Do not just read source code and assume descriptions are published. Verify the metadata actually returned by the application.

### Checking the collection profile

- Start the application with the exported `PersonRepository`.
- Call `GET /people`.
- Verify the response contains a `profile` link.
- Access the profile URI and confirm the collection/item descriptions appear in the corresponding ALPS output.

### Checking property descriptions

- Access the profile metadata for `people`.
- Locate the `person-representation` descriptor.
- Locate the `firstName`, `lastName`, and `status` descriptors.
- Confirm `doc.value` contains the declared text.
- Verify names and descriptions match the actual properties.

### Checking query descriptions

- Call `GET /people/search`.
- Confirm there is a link to the `by-last-name` query resource.
- Call `GET /people/search/by-last-name?name=Nguyen`.
- Verify the query returns the expected results.
- Check the repository's ALPS metadata to verify it has an appropriate description for the query transition/resource.

### Checking multilingual content

If using a resource bundle:

- Send a request with the default locale.
- Send requests with different locales using the application's locale mechanism.
- Verify messages resolve correctly.
- Verify that missing keys fall back gracefully without breaking metadata.

## 10. Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Description not seen in entity JSON | Checking the HAL response instead of ALPS metadata | Follow the `profile` link and read ALPS |
| Collection has a description but item does not | Only `collectionResourceDescription` was configured | Add `itemResourceDescription` |
| Query resource lacks the expected description | Missing `description` on `@RestResource` or query method not exported | Check annotations, method, and metadata |
| Property lacks `doc.value` | Annotation placed on wrong field/getter or property not part of described representation | Check mappings and annotation placement |
| Query path did not change | Used `@Description` without configuring `@RestResource(path = ...)` | Set `path` in `@RestResource` |
| Client cannot find query resource | Query method not exported or repository not exported | Check `exported`, repository, and query method |
| Description displays the raw key | Resource bundle not configured or key does not exist | Check `MessageSource`, file name, and key |
| Description does not match business logic | Text was copied or mismatches actual query behavior | Update description to match the actual contract |

## 11. Checklist for Adding @Description

- [ ] Every resource has a clear description of its purpose.
- [ ] Collection resources and item resources have distinct descriptions when their semantics differ.
- [ ] Domain types and important properties have appropriate descriptions.
- [ ] Query methods accurately describe search criteria and results.
- [ ] `@RestResource` remains responsible for path/rel/export settings; `@Description` only supplies descriptive text.
- [ ] ALPS metadata is not confused with HAL entity representations.
- [ ] Resource bundles are configured properly if using internationalization keys.
- [ ] Inspected profile metadata to confirm the actual output.
- [ ] Descriptions contain no sensitive information or internal details that should not be exposed.
- [ ] Descriptions accurately reflect the current API contract.

## Conclusion

`@Description` enriches Spring Data REST metadata with semantics. Use the annotation on domain types and properties to explain representations; use `collectionResourceDescription` and `itemResourceDescription` on `@RepositoryRestResource` to describe both resource levels; and use `description` on `@RestResource` to explain query resources. After configuring them, inspect the profile/ALPS metadata to confirm clients actually receive the intended content.

Good descriptions make APIs easier to discover and reduce client guesswork from field or endpoint names. They serve as contract metadata documentation and do not replace validation, projections, or data-processing logic.

## References

- Spring Data REST — Metadata and ALPS: https://docs.spring.io/spring-data/rest/reference/metadata.html
- Spring Data REST 5.1 API — Description: https://docs.spring.io/spring-data/rest/docs/5.1.x/api/org/springframework/data/rest/core/annotation/Description.html
- Spring Data REST 5.1 API — RepositoryRestResource: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html
- Spring Data REST 5.0 API — RestResource: https://docs.spring.io/spring-data/rest/reference/5.0/api/java/org/springframework/data/rest/core/annotation/RestResource.html
