# Representing Empty Collections, Absent Links, and Optional Relationships

In Spring Data REST and Spring HATEOAS, a HAL response can describe collections, navigation links, and relationships between resources. Three situations are easily confused: a collection that exists with zero elements, a link relation that does not appear in a response, and a relationship in the data model that is optional. Understanding each case accurately helps clients handle responses properly without guessing resource state.

## 1. HAL Represents Resources and Links

HAL (Hypertext Application Language) is a JSON format used to represent resources alongside related links. Two key areas are:

- _links contains link relations and href addresses for client navigation.
- _embedded contains resources embedded directly in the current representation.

Example of a collection resource with a link to itself and embedded products:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/products"
    }
  },
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "_links": {
          "self": {
            "href": "/api/products/1"
          }
        }
      }
    ]
  }
}
~~~

Here, products is the relation of the embedded collection. Each element in turn has its own self link. Clients can read the embedded data directly from the response or follow links to retrieve other resources.

Not every response needs to have _embedded. A resource may only provide links in _links; the client follows href to fetch detailed content when needed. Therefore, not seeing a relation in _embedded does not automatically mean that the relationship does not exist. Check both _links and the resource structure according to the API contract.

## 2. An Empty Collection Is Still a Valid Resource

An empty collection means the collection endpoint exists and is reachable, but currently no elements satisfy the query. For example, GET /api/products can return a collection with zero products.

An illustrative HAL representation:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/products"
    }
  },
  "_embedded": {
    "products": []
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Depending on how the representation is constructed and serializer configuration, an empty embedded relation may be represented as an empty array or omitted from _embedded. If _embedded.products is absent, check the endpoint contract and pagination metadata; do not assume that the collection endpoint does not exist.

When an API returns a PagedModel or a representation with pagination info, totalElements equal to 0 indicates there are no elements in the current result for that query. totalPages can also be 0. The self link can still appear to identify the collection being accessed. The next or prev links are typically absent when there is no next or previous page.

Distinguish three outcomes:

| Situation | Meaning |
|---|---|
| GET collection succeeds with 0 elements | The collection exists; the current result is empty. |
| GET collection succeeds with elements | The collection exists; matching data is present. |
| No link relation pointing to the collection in another resource | The current resource does not advertise that link; you cannot yet conclude whether the target collection is empty or non-existent. |

An empty collection is not an error. Clients should usually display a "no data yet" or "no matching results found" state instead of showing a connection error.

## 3. Creating an Empty CollectionModel with Spring HATEOAS

When building an API manually with Spring HATEOAS, use CollectionModel to represent a collection of resources. A CollectionModel can still contain links even when its list of elements is empty.

Example creating an empty collection while keeping the self link:

~~~java
CollectionModel<EntityModel<Product>> result = CollectionModel.empty();

result.add(
    linkTo(methodOn(ProductController.class).all())
        .withSelfRel()
);

return result;
~~~

For a non-empty collection, each element can be wrapped in an EntityModel and assembled into a collection model:

~~~java
List<EntityModel<Product>> items = products.stream()
    .map(product -> EntityModel.of(
        product,
        linkTo(methodOn(ProductController.class).one(product.getId()))
            .withSelfRel()
    ))
    .toList();

return CollectionModel.of(
    items,
    linkTo(methodOn(ProductController.class).all()).withSelfRel()
);
~~~

Both branches return the same CollectionModel type. Clients do not need to handle a separate data type just because a collection is empty. If an endpoint needs pagination metadata, use an appropriate paged representation and provide the total elements, page count, and corresponding navigation links.

## 4. What Does an Absent Link Relation Mean?

In HAL, a link relation is advertised only when it is present in _links. Example:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "items": {
      "href": "/api/orders/42/items"
    }
  }
}
~~~

The response above has self and items. If there is no payment relation, the client cannot find _links.payment in this document.

An absent link means the current representation does not advertise that relation. It does not by itself prove that:

- The target resource does not exist.
- The target collection is empty.
- The server has no corresponding endpoint.
- The client was denied access.

A link may be absent because the relationship does not apply to this resource, the current business state does not allow the action, the endpoint is not advertised in the representation, or access policy does not provide the link to that client. The exact meaning must be determined by the API contract.

Do not create dummy links with null href, empty strings, or the value "null". If a relation is not provided, omit the link relation completely from _links. This representation lets clients clearly distinguish a navigable link from an unadvertised relation.

## 5. Optional Relationships in the Data Model

An optional relationship is a relationship that may or may not have a linked object. For example, an order may not yet have an assigned customer; an employee may not have a direct manager; an article may not yet have a cover image.

At the Java layer, a single-valued relationship can be represented using Optional or a nullable property depending on the project's model and conventions. Example:

~~~java
public class Order {
    private Customer customer;

    public Optional<Customer> getCustomer() {
        return Optional.ofNullable(customer);
    }
}
~~~

If customer has a value, the API can provide a link to the customer resource. If not, a custom representation can omit the customer relation.

Example building an EntityModel conditionally:

~~~java
EntityModel<Order> model = EntityModel.of(order);

model.add(
    linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel()
);

order.getCustomer().ifPresent(customer ->
    model.add(
        linkTo(methodOn(CustomerController.class).one(customer.getId()))
            .withRel("customer")
    )
);

return model;
~~~

When the order has a customer, HAL may contain:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  }
}
~~~

When there is no customer, the custom representation in the example above returns only the self link. The client checks for the existence of _links.customer before navigating.

Note: Spring Data REST can automatically generate association links based on repository and association mappings, independently of whether the current property has a value. Therefore, do not assume that a null association always makes the link disappear in framework-generated responses. Inspect the actual endpoint representation and association exposure configuration. If the contract requires advertising the link only when the relationship has a target object, build a conditional representation or customize exposure accordingly.

## 6. Distinguishing Links and Embedded Resources for Optional Relationships

A relationship can be represented by a link, by embedded data, or by both. These two parts serve different purposes:

- _links.customer provides the address to navigate to the customer.
- _embedded.customer contains the customer data embedded in the current response.

Example with link only:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  }
}
~~~

The client knows the customer relationship is accessible but needs to call href to retrieve the customer's content.

Example with both link and embedded resource:

~~~json
{
  "_links": {
    "self": {
      "href": "/api/orders/42"
    },
    "customer": {
      "href": "/api/customers/7"
    }
  },
  "_embedded": {
    "customer": {
      "name": "An Nguyen",
      "email": "an@example.test",
      "_links": {
        "self": {
          "href": "/api/customers/7"
        }
      }
    }
  }
}
~~~

If embedded data is absent, the client can still follow the link if the link exists. Conversely, a representation might embed data without providing a separate link under a specific contract. Therefore, check the exact data location committed by the API.

## 7. How Should Clients Handle These Cases?

Clients should read HAL relations safely when properties may be absent. JavaScript example:

~~~javascript
const response = await fetch("/api/orders/42");
const order = await response.json();

const customerLink = order._links?.customer;

if (customerLink?.href) {
    const customerResponse = await fetch(customerLink.href);
    const customer = await customerResponse.json();
    renderCustomer(customer);
} else {
    renderNoCustomer();
}
~~~

For embedded collections, you can default the list to an empty array when the relation does not appear:

~~~javascript
const products = response._embedded?.products ?? [];

if (products.length === 0) {
    renderEmptyState();
} else {
    renderProducts(products);
}
~~~

For paged collections, read page metadata if provided by the endpoint:

~~~javascript
const totalElements = response.page?.totalElements ?? products.length;

if (totalElements === 0) {
    renderEmptyState();
}
~~~

Do not use the same UI state for both "empty collection" and "missing link". An empty collection indicates the collection was reached and has no elements; an absent link indicates the current representation does not advertise a navigation path. When more details are needed, the client can access the root endpoint or use another link provided by the API.

## 8. Useful Design Rules

- Return an empty collection when a collection endpoint is valid but the query yields no results; do not return null in place of a list.
- Keep the self link on resources or collections so clients can identify the current representation.
- Provide a link relation only when the relationship or action is advertised under the API contract.
- For optional relationships, clearly decide whether the link always exists as an association endpoint or only appears when a linked object is present.
- Do not use a null href or empty string to represent a non-existent link.
- Use _embedded for embedded data and _links for navigation; do not infer relationship state from only one of the two sections.
- For paged collections, provide consistent metadata so clients recognize empty results and navigate pages.
- Document conditional relationships so clients know when a link may appear.

## 9. Testing HAL Responses

When testing an endpoint, test all three states instead of only testing the case with data:

1. Call the collection when multiple elements exist and observe _embedded, _links, and pagination metadata.
2. Call the same collection when no matching elements exist; verify the response is still a valid collection and shows zero total elements if page metadata is present.
3. Read a resource that has an assigned optional relationship and verify the link relation or embedded resource according to the contract.
4. Read a resource without the optional relationship and observe how the API represents the association.
5. Test a relation not advertised in the current state; the client must handle the missing key in _links.
6. With Spring Data REST, check whether auto-generated association links always appear or are conditional based on configuration and mappings.

Keep the three concepts separate: an empty collection is the result of a set with zero elements; an absent link is a representation not advertising a navigation relation; an optional relationship is the state of an association in the data model. HAL and Spring HATEOAS allow representing these states clearly so clients can navigate and display them appropriately.
