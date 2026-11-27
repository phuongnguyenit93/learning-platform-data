# Method Naming and Contract Readability

In gRPC, a method name is part of the **public contract** between client and server. A clear name helps readers infer the business domain, recognize the data direction, and understand the type of result the call provides before opening the Java implementation. Conversely, generic names such as **Process**, **Handle**, or **DoRequest** force consumers to read server code just to know what the call actually does.

With **Spring gRPC**, the contract is declared in **.proto** files; service and method names also participate in generating the RPC path, descriptors, and Java stub APIs. Naming must therefore be consistent from the start and treated as an API design decision.

## 1. Reading a Method from Name to Contract

A gRPC declaration typically looks like:

~~~proto
rpc GetProduct(GetProductRequest) returns (GetProductResponse);
~~~

Readers can immediately understand three parts:

- **GetProduct**: the business action the client is requesting.
- **GetProductRequest**: the data the client must supply.
- **GetProductResponse**: the data the server returns on success.

The method name tells *what work is done*; request and response types tell *what data is needed and what result is returned*. The **stream** keyword indicates one side may send multiple messages within the same RPC. All three elements must be consistent so the contract is self-explanatory.

For example, the two declarations below have different cardinalities despite similar method names:

~~~proto
rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
rpc WatchOrderUpdates(WatchOrderUpdatesRequest)
    returns (stream OrderUpdate);
~~~

**ListOrders** returns one response, typically containing a page of items. **WatchOrderUpdates** returns a stream of events over time. Readers do not have to guess cardinality from the name; the return type in .proto specifies it precisely.

## 2. Naming Conventions for Services, Methods, and Messages

Follow consistent Protobuf conventions:

| Component | Convention | Example |
| --- | --- | --- |
| Package | lowercase, hierarchical by domain and version | **acme.inventory.v1** |
| Service | PascalCase, domain/capability name | **InventoryService** |
| RPC method | PascalCase, verb + object or clear action | **GetProduct**, **ReserveStock** |
| Request/response message | PascalCase, tied to method or business concept | **ReserveStockRequest**, **Reservation** |
| Field | lower_snake_case | **product_id**, **requested_quantity** |
| Enum type | PascalCase | **ReservationStatus** |
| Enum value | UPPER_SNAKE_CASE, prefixed with enum name when appropriate | **RESERVATION_STATUS_CONFIRMED** |

A service name should reflect a **capability boundary**. **InventoryService** is much clearer than **CommonService** or **GrpcService**, because consumers immediately know the service is responsible for inventory. One service can hold multiple related RPCs in the same domain; avoid lumping unrelated operations into one service simply because they share infrastructure.

Method names should start with a verb expressing the action:

- **GetProduct**: read a single product by identifier.
- **CreateOrder**: create an order.
- **CancelOrder**: cancel an order.
- **ListOrders**: list orders with filtering and pagination.
- **WatchOrderUpdates**: subscribe to updates.
- **UploadReadings**: send multiple measurement records.
- **SynchronizeInventory**: synchronize data bidirectionally.

Avoid purely technical names such as **Call**, **Execute**, **ProcessData**, or **SendMessage** when they fail to convey business intent.

## 3. Naming by Semantics, Not Just CRUD Operations

CRUD is a useful starting point, but not every RPC is CRUD. Names should answer **what the client wants to achieve**:

| Vague Name | Clearer Name | Reason |
| --- | --- | --- |
| **Process** | **CalculateShippingFee** | States the business outcome clearly |
| **GetData** | **GetCustomerProfile** | Specifies the kind of data |
| **Update** | **ChangeDeliveryAddress** | States what is being changed |
| **Send** | **UploadReadings** | Clarifies what data is sent up |
| **Stream** | **WatchOrderUpdates** | Clarifies what the client observes |
| **DoAction** | **ApprovePayment** | Specifies the action and target object |

Do not stuff every detail into the name. **GetProductByIdAndWarehouseCode** is usually unnecessarily verbose if the request already contains **product_id** and **warehouse_id**. The method name states the intent; the request message describes the parameters.

### Choosing Verbs with Stable Meaning

- Use **Get** to query a single resource or specific result.
- Use **List** for a filterable/paginated collection returned in a single response.
- Use **Watch** or **Subscribe** when the client registers to receive updates over time.
- Use **Create** when creating a new resource; use **Update** when changing existing state/resources.
- Use **Delete** or **Remove** consistently according to domain semantics; do not alternate between the two for the same behavior.
- Use **Upload** when the client sends data up to the server; use **Download** when the client receives data from the server, while still declaring cardinality explicitly in .proto.

The name **List** does not implicitly mean server streaming. A unary **ListProducts** can return **repeated Product** or a page of results. If results must be emitted incrementally over time, declare a response stream and choose a semantically accurate name like **Watch...** or **Stream...**.

## 4. Request and Response Messages Must Be Self-Describing

Generic **Request** and **Response** names may work in tiny examples, but in real contracts they should be tied to the method:

~~~proto
rpc ReserveStock(ReserveStockRequest)
    returns (ReserveStockResponse);

message ReserveStockRequest {
  string product_id = 1;
  int32 requested_quantity = 2;
  string idempotency_key = 3;
}

message ReserveStockResponse {
  string reservation_id = 1;
  int32 reserved_quantity = 2;
}
~~~

Readers can immediately recognize the inputs are product, quantity, and idempotency key; the result is reservation ID and reserved quantity. If **Request** and **Response** are used for every method, IDEs and logs end up with many identically named types with different meanings, harming readability and searchability.

### When Should Shared Messages Be Used?

Share a message only when methods genuinely share **the same semantics and data lifecycle**, such as **PageRequest** or **Money**. Do not reuse messages solely to save lines in .proto. Two requests might both contain **id**, yet one is a query and the other an update command; they may need different validation, permissions, and compatibility rules.

For streaming, message names should clarify what each element represents:

~~~proto
rpc UploadReadings(stream ReadingChunk)
    returns (UploadReport);

rpc WatchOrderUpdates(WatchOrderUpdatesRequest)
    returns (stream OrderUpdate);

rpc SynchronizeInventory(stream InventoryChange)
    returns (stream SyncResult);
~~~

**ReadingChunk**, **OrderUpdate**, and **InventoryChange** describe the payload of each message. Avoid naming every streaming message **Data**, because readers cannot tell whether each element is a chunk, event, command, or result.

## 5. Reading a Complete Contract Through an Example

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;

service InventoryService {
  // Read information for a single product.
  rpc GetProduct(GetProductRequest) returns (Product);

  // List a page of products.
  rpc ListProducts(ListProductsRequest) returns (ListProductsResponse);

  // Watch inventory changes.
  rpc WatchStock(WatchStockRequest) returns (stream StockUpdate);

  // Send multiple changes and receive an aggregated report.
  rpc UploadStockChanges(stream StockChange)
      returns (UploadStockReport);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int64 available_quantity = 3;
}

message ListProductsRequest {
  int32 page_size = 1;
  string page_token = 2;
}

message ListProductsResponse {
  repeated Product products = 1;
  string next_page_token = 2;
}

message WatchStockRequest {
  string warehouse_id = 1;
}

message StockUpdate {
  string product_id = 1;
  int64 available_quantity = 2;
  int64 version = 3;
}

message StockChange {
  string product_id = 1;
  int64 delta = 2;
  string change_id = 3;
}

message UploadStockReport {
  int64 accepted_count = 1;
  int64 rejected_count = 2;
}
~~~

Reading from top to bottom, the contract communicates:

1. **Package acme.inventory.v1** defines the namespace and API version.
2. **InventoryService** owns inventory capabilities.
3. **GetProduct** and **ListProducts** are unary; **ListProductsResponse** has **repeated Product**, yet remains a single response message.
4. **WatchStock** is server streaming because the response has **stream**; the client sends one subscription condition and receives **StockUpdate** messages over time.
5. **UploadStockChanges** is client streaming; the client sends multiple changes and receives one final **UploadStockReport**.

Names and message types work together to explain the data flow. Readers do not have to inspect the Java implementation to know which method takes multiple messages.

## 6. Method Names Affect the RPC Path and Java Code

Method names do not appear solely in documentation. With the package and service in the example above, the RPC path for **GetProduct** is:

~~~text
/acme.inventory.v1.InventoryService/GetProduct
~~~

The package, service, and method names together define the **full method name**. Client and server must agree on this name to route calls. Changing the package or renaming a service/method after release alters the RPC path and prevents older clients from reaching the old endpoint.

Generated Java code typically converts PascalCase RPC names into lowerCamelCase methods on stubs:

| Name in .proto | Typical Java Method Name |
| --- | --- |
| **GetProduct** | **getProduct(...)** |
| **ListProducts** | **listProducts(...)** |
| **WatchStock** | **watchStock(...)** |
| **UploadStockChanges** | **uploadStockChanges(...)** |

Message classes remain PascalCase, such as **GetProductRequest** and **UploadStockReport**. **java_package** controls the package of generated Java code; it does not replace the Protobuf namespace used in the full method name.

Therefore, treat RPC names as part of the published API. If renaming is necessary, consider keeping the old method during a transition period, publishing the new method, updating clients, and removing the old method only according to your compatibility policy.

## 7. Rules for Readable and Evolvable Contracts

### Use Consistent Terminology

If one part of the business uses **CancelOrder**, do not introduce **AbortOrder** or **StopOrder** for the same meaning in another service without a clear distinction. Consistent vocabulary helps consumers learn the API quickly and locate methods easily.

### Name the Business Unit Explicitly

**UpdateStatus** is too vague if the system tracks order, payment, and delivery statuses. **UpdateOrderStatus** specifies the target. If a method updates multiple aspects of a resource, **UpdateOrder** may be better, provided the request and description clarify its scope.

### Avoid Embedding Implementation Details

Do not name methods after internal technologies such as **CallRedis**, **ExecuteSql**, or **SendKafka**. The contract should describe the behavior the client is permitted to request; the server should be able to swap databases or message brokers without forcing clients to rename methods.

### Use Comments for Conditions Not Captured in the Name

The name **ReserveStock** alone does not clarify whether reservations expire or whether partial quantities are allowed. Use Protobuf comments and field descriptions to document rules, units, limits, and possible errors. Do not turn method names into long descriptive sentences.

### Keep Field Numbers Stable

Renaming a method affects the full method path; renaming a field can affect source code and JSON mapping; changing a field number can break wire compatibility. When removing fields, mark deprecated numbers and names with **reserved**. Never reuse an old field number for a different meaning.

## 8. Hard-to-Read Names and How to Improve Them

| Hard-to-Read Contract | Issue | Improved Version |
| --- | --- | --- |
| **Process(Request) returns (Response)** | Unclear what is being processed | **CalculateInvoice(InvoiceRequest) returns (Invoice)** |
| **GetAll(Empty) returns (stream Data)** | Unclear data type, conditions, and stream meaning | **WatchOrderUpdates(WatchOrderUpdatesRequest) returns (stream OrderUpdate)** if it is an event stream |
| **Send(stream Data) returns (Result)** | Unclear what is uploaded and what is aggregated | **UploadReadings(stream Reading) returns (UploadReport)** |
| **Update(UpdateRequest) returns (UpdateResponse)** | Messages do not indicate the resource | **UpdateCustomerAddress(UpdateCustomerAddressRequest) returns (Customer)** |
| **DoSync(stream A) returns (stream B)** | Unclear target objects and results | **SynchronizeInventory(stream InventoryChange) returns (stream SyncResult)** |

Longer names are not automatically better. A good name is **concise enough, specific, consistent, and semantically accurate**. Let messages and comments express input/output details instead of cramming everything into the method name.

## 9. Contract Review Checklist

Before putting a .proto file into use, review these questions:

- Does the service name accurately reflect its domain/capability ownership?
- Does the method name use a clear verb and state the business behavior accurately?
- Are request/response messages specifically named, self-describing, and free of semantically inappropriate reuse?
- Can readers tell what kind of data each message carries?
- Is the **stream** keyword placed on the right side(s) for the requirement?
- Is a **repeated** field being confused with streaming messages?
- Does the package have an appropriate namespace and version?
- Do comments explain conditions, units, limits, or special rules?
- Would any rename alter the full method path or break existing clients?
- Are field numbers stable and removed fields marked as reserved?

## 10. Summary and Self-Check

A readable contract clearly conveys three layers of information: the **service** indicates capability, the **method** indicates action, and the **request/response messages** indicate incoming and outgoing data. The **stream** keyword defines the cardinality of each direction; a method name cannot substitute for that declaration.

Self-check:

1. Why can **ListProducts** be unary even when the response contains a **repeated Product** field?
2. What do the name **UploadReadings** combined with **stream Reading** suggest about data direction?
3. Why can renaming **InventoryService.GetProduct** impact already-released clients?
4. When should you use shared messages, and when should you create method-specific **Request/Response** messages?
5. If someone sees only the name **Process**, what information are they missing to understand the contract?

Good naming does not replace schema design, but it makes schemas self-explanatory and lowers integration costs. In Spring gRPC, clear contracts make generated Java code easier to read, help clients pick the right stubs, and allow teams to collaborate without guessing method intent.
