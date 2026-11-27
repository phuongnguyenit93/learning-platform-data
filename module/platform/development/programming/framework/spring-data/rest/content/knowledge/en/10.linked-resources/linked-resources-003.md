# GET for To-One and Collection Associations in Spring Data REST

## Objectives

After this lesson, you can:

- Identify an association link inside an entity representation.
- Call a `GET` endpoint to retrieve a single linked object.
- Call a `GET` endpoint to retrieve a list of linked objects.
- Read HAL JSON structures and handle cases where endpoints are not exported.

## 1. Association Resources in Spring Data REST

Spring Data REST automatically generates REST endpoints from exported repositories. When an entity has a property referencing another entity, Spring Data REST can expose an association resource so clients can access that relationship.

Example order model:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

An order has one customer and multiple order lines. The repositories can be exported as follows:

~~~java
@RepositoryRestResource(path = "orders")
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}

@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

@RepositoryRestResource(path = "order-lines")
public interface OrderLineRepository
        extends JpaRepository<OrderLine, Long> {
}
~~~

With default configuration and exported associations, clients can access:

- Single order resource: **GET /orders/42**
- To-one association `customer`: **GET /orders/42/customer**
- Collection association `lines`: **GET /orders/42/lines**

These paths are illustrated based on the repository and property names in the example. Actual paths depend on export configuration and customization annotations.

## 2. Finding Association Links from the Item Resource

Do not construct URLs manually when the server already provides links. First, fetch the item resource:

~~~http
GET /orders/42
Accept: application/hal+json
~~~

The HAL representation may contain links like these:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42"
    },
    "purchaseOrder": {
      "href": "http://localhost:8080/orders/42"
    },
    "customer": {
      "href": "http://localhost:8080/orders/42/customer"
    },
    "lines": {
      "href": "http://localhost:8080/orders/42/lines"
    }
  }
}
~~~

Where:

- **self** points to the item resource itself.
- **customer** points to the to-one association.
- **lines** points to the collection association.

Relation names in **_links** are generated from Spring Data REST metadata. Use the exact **href** returned by the server; do not assume relation names always match the Java class name or always use a fixed path.

## 3. GET a To-One Association

For a single-cardinality property such as **@ManyToOne** or **@OneToOne**, the association endpoint points to one related object.

~~~http
GET /orders/42/customer
Accept: application/hal+json
~~~

Example response:

~~~json
{
  "id": 7,
  "name": "Nguyen An",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "http://localhost:8080/customers/7"
    },
    "customer": {
      "href": "http://localhost:8080/customers/7"
    }
  }
}
~~~

The client receives the representation of the customer linked to order 42. The **self** link of the response typically points to the customer's item resource, allowing the client to continue navigating to that resource or follow other links advertised by the server.

Distinguish between the two URLs:

- **GET /customers/7**: accesses the customer directly by the customer's identifier.
- **GET /orders/42/customer**: accesses the customer via the `customer` association of order 42.

Both URLs can lead to the same object, but the association URL represents navigating from the parent resource to the related resource.

## 4. GET a Collection Association

For a multi-cardinality property such as **@OneToMany** or **@ManyToMany**, the association endpoint returns a collection resource.

~~~http
GET /orders/42/lines
Accept: application/hal+json
~~~

Example HAL response:

~~~json
{
  "_embedded": {
    "orderLines": [
      {
        "id": 100,
        "productName": "Keyboard",
        "quantity": 1,
        "_links": {
          "self": {
            "href": "http://localhost:8080/order-lines/100"
          }
        }
      },
      {
        "id": 101,
        "productName": "Mouse",
        "quantity": 2,
        "_links": {
          "self": {
            "href": "http://localhost:8080/order-lines/101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/orders/42/lines"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 2,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Parts to read:

- **_embedded** contains the items of the collection. The inner key name is typically the relation name of the exported repository.
- Each item can have **_links.self** so the client can directly access the item resource.
- **page** appears when the representation includes pagination information; the values indicate page size, total elements, total pages, and current page index.
- **_links** can provide navigation links such as `self`, `next`, or `previous` depending on the response and configuration.

An empty collection is still a valid result for a collection association. When there are no items, the **_embedded** section may be omitted or contain no elements; handle empty collections gracefully rather than treating them as errors.

If the endpoint supports pagination, use the parameters advertised by the API and prefer following `next`/`previous` links in the response. Do not assume every association endpoint supports every sort or page parameter.

## 5. Comparing To-One and Collection Associations

| Characteristic | To-one association | Collection association |
|---|---|---|
| JPA examples | `@ManyToOne`, `@OneToOne` | `@OneToMany`, `@ManyToMany` |
| Endpoint example | `/orders/42/customer` | `/orders/42/lines` |
| Result | A single entity resource | A collection resource |
| Common HAL structure | Entity properties and `_links` | `_embedded`, `_links`, and possibly `page` |
| How to handle | Read one object or follow its `self` link | Iterate over the list, handle empty collections and pagination |

The key point is that the cardinality of the association determines the response shape the client must handle. Do not process a collection response as a single entity or vice versa.

## 6. Calling the API with curl

You can test the navigation flow with three requests:

~~~bash
# 1. Read the order and locate association links
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42

# 2. Read the customer linked to the order
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42/customer

# 3. Read the list of order lines for the order
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/42/lines
~~~

When testing, compare the **href** from the first request with the URLs called in subsequent requests. If the server returns different URLs due to base path configuration, a reverse proxy, or a custom association path, the client should use the URLs received from the response.

## 7. Customizing the Association Path and Relation

You can change the path and relation name of an association using **@RestResource**:

~~~java
@ManyToOne
@RestResource(path = "buyer", rel = "buyer")
private Customer customer;

@OneToMany(mappedBy = "order")
@RestResource(path = "items", rel = "items")
private List<OrderLine> lines = new ArrayList<>();
~~~

Then the association links can be exposed under the **buyer** and **items** relations, with corresponding paths:

- **/orders/42/buyer**
- **/orders/42/items**

Inspect the actual links in the item resource after changing the configuration. **path** controls the endpoint URL segment; **rel** controls the relation name appearing in HAL.

If an association is annotated with **@RestResource(exported = false)**, Spring Data REST does not export that association as a public endpoint. When a link is missing, check the export configuration of the repository and the association before concluding that relationship data is absent.

## 8. Error Handling and Checklist

- **404 Not Found**: the item resource does not exist or the association URL is not exported/invalid.
- **401 Unauthorized / 403 Forbidden**: the request is unauthenticated or the caller lacks permission to read the resource.
- **406 Not Acceptable**: the media type requested by the client is not supported by the endpoint; try **Accept: application/hal+json** according to the application configuration.
- **Empty collection**: this can be valid data; check **totalElements** if the response includes page metadata.
- **Missing association link**: check whether the repository is exported, whether the association has **exported = false**, and whether `path`/`rel` has been customized.
- **Link points to a different host or base path**: check the base URI configuration, proxy settings, and how the application builds links; do not rewrite URLs by guessing when the server has returned a link.

`GET` only reads resources. A `GET` request to an association endpoint does not add, remove, or modify relationships. Operations that update associations belong to their corresponding write HTTP methods and endpoints.

## 9. Practice Workflow

1. Start the application and determine the Spring Data REST base path.
2. Call **GET /orders/42** with **Accept: application/hal+json**.
3. Locate the relations for the to-one and collection associations in **_links**.
4. Copy the exact **href** of the to-one relation and call `GET`; confirm the response is a single entity resource.
5. Copy the **href** of the collection relation and call `GET`; confirm the response is a collection resource.
6. Test with an order that has no order lines to verify how the client handles an empty collection.
7. If you have configured a custom **path** or **rel**, repeat link discovery to verify that the client still navigates via the response.

## 10. Practice Exercises

Given a **PurchaseOrder** that has one **Customer** and multiple **OrderLine** items:

1. Write two `GET` requests to read the customer and lines through a purchase order.
2. Point out the differences between the two responses in HAL JSON.
3. Explain why clients should read **href** in **_links** instead of constructing URLs manually.
4. Change the `customer` association to path **buyer** and relation **buyer**. Identify the new link from the **GET /orders/42** response.
5. List the troubleshooting steps when the `lines` relation does not appear in **_links**.

**Key takeaway:** the item resource lets clients discover association links; `GET` on a to-one association returns a single resource, while `GET` on a collection association returns a collection resource. Use HAL links as the primary navigation mechanism for clients.
