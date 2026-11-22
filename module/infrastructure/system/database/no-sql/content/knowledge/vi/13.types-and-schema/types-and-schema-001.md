# Schema ở cấp lưu trữ, cấp ứng dụng và hợp đồng trao đổi dữ liệu

## 1. NoSQL không có schema, hay schema nằm ở nhiều nơi?

Một quan niệm phổ biến là: **“NoSQL là schemaless, nên cứ lưu JSON bất kỳ rồi tính sau.”** Cách hiểu đó chỉ đúng một phần. Nhiều document database không bắt buộc mọi bản ghi trong cùng collection có cấu trúc giống hệt nhau; một key–value store có thể chỉ biết key và dãy byte của value. Nhưng điều đó **không làm biến mất các quy tắc về tên trường, kiểu dữ liệu, định danh, thời gian và hành vi nghiệp vụ**.

Giả sử trong một collection đơn hàng có hai document:

~~~json
{
  "orderId": "O1001",
  "status": "PAID",
  "totalVnd": 450000,
  "createdAt": "2026-11-14T03:00:00Z"
}
~~~

~~~json
{
  "orderId": "O1002",
  "status": "paid",
  "totalVnd": "450.000đ",
  "createdAt": "hôm qua"
}
~~~

Database có thể chấp nhận cả hai nếu không cấu hình validator. Nhưng ứng dụng không thể đơn giản cộng tổng doanh thu, so sánh trạng thái hoặc sắp theo ngày vì cùng một trường đã mang **kiểu và quy ước khác nhau**.

Trong thiết kế NoSQL, nên phân biệt **ba cấp schema**:

1. **Storage schema (schema cấp lưu trữ):** dữ liệu được lưu trong database theo hình dạng, kiểu, khóa, chỉ mục và chính sách nào?
2. **Application/domain schema (schema cấp ứng dụng):** chương trình hiểu thực thể, quy tắc nghiệp vụ và thao tác hợp lệ ra sao?
3. **Data contract (hợp đồng trao đổi dữ liệu):** client, service và consumer thống nhất được gửi/nhận những trường nào, với kiểu và ý nghĩa gì, trong bao lâu?

Ba lớp cùng mô tả một nghiệp vụ nhưng **không cần có cấu trúc giống hệt nhau**. Ví dụ request tạo đơn không được phép chứa số tiền do client tự quyết, trong khi domain Order phải có số tiền đã tính và storage có thể còn lưu metadata của cơ sở dữ liệu.

## 2. Bức tranh tổng thể của ba lớp schema

~~~mermaid
flowchart TD
    C["Client hoặc hệ thống đối tác"] -->|"HTTP JSON / hợp đồng API"| A["DTO + validation tại API boundary"]
    A --> B["Domain / Application service"]
    B --> M["Repository + storage mapper"]
    M --> D[("NoSQL storage")]
    B --> O["Outbox / domain event"]
    O --> E["Event contract / message broker"]
    E --> R["Consumer / read projection"]
    R --> P[("Search / cache / analytics")]
~~~

Một chức năng có thể đi qua nhiều kiểu:

~~~text
Client JSON
   -> CreateOrderRequest
   -> CreateOrderCommand
   -> Domain Order
   -> OrderDocument
   -> BSON trong MongoDB

Domain Order
   -> OrderResponse gửi cho client
   -> OrderCreated event gửi cho consumer
~~~

Ở mỗi mũi tên có thể có **mapping, validation hoặc chuyển kiểu**. Những bước này không chỉ là boilerplate: chúng bảo vệ ranh giới giữa dữ liệu ngoài hệ thống, hành vi nghiệp vụ và cách lưu trữ nội bộ.

### 2.1. Ba câu hỏi không được gộp làm một

| Cấp | Câu hỏi cốt lõi | Ví dụ |
| --- | --- | --- |
| Lưu trữ | Database nhận bản ghi thế nào và truy cập bằng khóa nào? | Collection orders có index (tenantId, orderId) |
| Ứng dụng | Một trạng thái Order hợp lệ nghĩa là gì? | Không cho chuyển CANCELLED thành PAID vô điều kiện |
| Hợp đồng | Client thấy/gửi được những gì? | POST /orders chỉ nhận customerId và items |

Một trường hợp lệ về mặt **JSON Schema** chưa chắc hợp lệ về nghiệp vụ. Một trạng thái hợp lệ trong domain chưa chắc được phép công khai ra API. Một document hợp lệ khi ghi xuống database chưa chắc đã được index để truy vấn hiệu quả.

## 3. Storage schema: cấu trúc dữ liệu mà database thực sự quản lý

**Storage schema** không chỉ là danh sách field. Nó thường gồm:

- Namespace: database, keyspace, collection, table, bucket hoặc quy ước tên key.
- Cấu trúc: document, row, value, node/edge, nested array, map.
- Định danh: primary key, unique key, partition key, sort/clustering key.
- Kiểu lưu: string, number, integer, timestamp, BSON Decimal128, binary...
- Index phục vụ các access pattern.
- Validation và constraint do engine hỗ trợ.
- Retention, TTL, tombstone, version và metadata nội bộ.
- Quy tắc sharding/replication, khi chúng ảnh hưởng đến khóa và truy vấn.

Tùy sản phẩm, storage schema có thể được **khai báo tường minh**, **bị cưỡng chế một phần** hoặc **nằm chủ yếu trong quy ước của ứng dụng**.

### 3.1. Storage schema theo các họ NoSQL

| Họ NoSQL | Điều thường cần thiết kế | Ví dụ |
| --- | --- | --- |
| Key–value | Tên key, cấu trúc value, TTL, serializer, đường lookup phụ | order:T01:O1001 |
| Document | Collection, field, BSON/JSON types, index, validator | orders với mảng lines |
| Wide-column | Keyspace/table, column types, partition/clustering keys | orders_by_customer_day |
| Graph | Node labels, relationship types, properties, index/constraint | Person -PLACED-> Order |
| Search | Field mapping, analyzer, keyword/text, index và sort | title.text, tenantId.keyword |

Không có một storage schema duy nhất dùng chung được cho tất cả. **Khóa và cách truy vấn** là phần rất quan trọng trong thiết kế NoSQL, đôi khi quan trọng hơn việc liệt kê thuộc tính.

## 4. Ví dụ storage schema với MongoDB

Xét một đơn hàng thuộc tenant T01:

~~~javascript
{
  _id: ObjectId("6735cbd8a7d1e9f58b320001"),
  tenantId: "T01",
  orderId: "O1001",
  customerId: "C08",
  status: "PENDING",
  lines: [
    {
      sku: "P10",
      quantity: 2,
      unitPriceVnd: NumberLong("225000")
    }
  ],
  totalVnd: NumberLong("450000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  updatedAt: ISODate("2026-11-14T03:00:00Z"),
  version: NumberLong("1"),
  schemaVersion: 2
}
~~~

Đây là **biểu diễn mongosh/BSON**, không phải JSON thuần. ObjectId, NumberLong và ISODate là các kiểu/biểu thức mà ứng dụng có thể cần ánh xạ khi gửi dữ liệu dưới dạng HTTP JSON.

Những quyết định nằm ở cấp lưu trữ:

- **_id** là ID nội bộ của document; **orderId** là ID nghiệp vụ ổn định.
- **lines** được nhúng vì thường đọc một đơn cùng các dòng hàng.
- **unitPriceVnd** là giá tại thời điểm đặt hàng, không phải giá hiện tại của sản phẩm.
- **tenantId** được lưu để giới hạn truy vấn và kiểm soát phạm vi dữ liệu.
- **version** là phiên bản trạng thái phục vụ cập nhật cạnh tranh; **schemaVersion** nói về hình dạng document.
- **totalVnd** là số nguyên đồng Việt Nam, tránh mơ hồ giữa số thập phân nhị phân và đơn vị tiền.

### 4.1. Chỉ mục cũng là schema

Ví dụ index cho khóa nghiệp vụ:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
~~~

Và index cho màn hình lịch sử đơn:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  orderId: 1
});
~~~

Hai index này phục vụ **hai access pattern khác nhau**: tìm đúng đơn và duyệt lịch sử theo khách/thời gian.

Nếu collection được sharding, cần kiểm tra giới hạn của unique index, shard key và phạm vi bảo đảm trong topology thực tế; không nên mặc định bất kỳ unique index nào cũng giữ tính duy nhất trên mọi cách phân vùng.

### 4.2. Database validator bảo vệ kiểu cơ bản

MongoDB hỗ trợ validation theo dạng **$jsonSchema**. Một ví dụ tối giản khi tạo collection mới:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "orderId",
        "customerId",
        "status",
        "totalVnd",
        "createdAt"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        orderId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        status: {
          enum: ["PENDING", "CONFIRMED", "CANCELLED"]
        },
        totalVnd: { bsonType: "long" },
        createdAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đoạn lệnh minh họa cho **collection mới**. Với collection đang chạy, việc thay đổi validator phải dùng thao tác quản trị thích hợp và xét tới dữ liệu cũ.

Validator giúp chặn một số record thiếu field hoặc sai type, nhưng **không tự biết** totalVnd đã cộng đúng các lines chưa, payment đã được xác nhận chưa, người gọi có quyền với tenant không, hoặc hai thao tác cập nhật đồng thời có vi phạm trạng thái nghiệp vụ không.

## 5. Với key–value hoặc wide-column, storage schema có hình dạng khác

### 5.1. Key–value: quy ước khóa là một phần của schema

~~~text
Key: order:T01:O1001

Value:
  {"schemaVersion":2,"status":"PENDING","totalVnd":450000,...}

Retention:
  đơn hàng chính thức không được tự hết hạn như cache phiên
~~~

Nếu database chỉ nhìn value như một dãy byte, **schema thực tế nằm trong serializer/deserializer và quy ước key**. Phải xác định:

- Cách escape thành phần key để không va chạm.
- Value dùng JSON, MessagePack, Protobuf hay định dạng khác.
- Phiên bản serialization và cách đọc value cũ.
- Hệ có hỗ trợ range/prefix scan không, hay khóa được hash.
- Cần thêm cấu trúc phụ nào để liệt kê đơn của một khách.
- TTL, backup và quy tắc xóa.

Không thể mặc định mọi key có tiền tố order:T01 đều truy vấn được hiệu quả theo tiền tố nếu engine chỉ hỗ trợ lookup chính xác.

### 5.2. Wide-column: khóa quyết định cách nhóm dữ liệu

Ví dụ Cassandra cho một read model:

~~~sql
CREATE TABLE orders_by_customer_day (
    tenant_id text,
    customer_id text,
    order_day date,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, order_day),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Table này phục vụ truy vấn theo **tenant + customer + day**, rồi đọc các đơn mới nhất trước. Đây có thể là một **bản chiếu lịch sử đơn**, không nhất thiết là nguồn transaction chứa toàn bộ dữ liệu order.

Thay một field trong ứng dụng không tự động thay partition key. Nếu cần truy vấn theo status toàn tenant, có thể phải tạo index hoặc table/bản chiếu khác. Với Cassandra, schema CQL và các quy tắc partition/clustering đều là quyết định cấp lưu trữ.

### 5.3. Graph: schema nằm trong nhãn, quan hệ và constraint

Ví dụ:

~~~text
(Customer {customerId: "C08"})
       -[:PLACED]->
(Order {orderId: "O1001", status: "PENDING"})
~~~

Ứng dụng cần thống nhất label, relationship type, hướng quan hệ, ID và constraint. Không có ràng buộc khóa ngoại giống SQL không đồng nghĩa quan hệ có thể bị tạo tùy ý mà không cần quy ước.

## 6. Application schema: cấu trúc và ý nghĩa trong chương trình

**Application schema** mô tả những đối tượng và trạng thái mà mã nguồn có thể hiểu:

- Domain entity/aggregate, value object và enum.
- Command, DTO nội bộ và service input/output.
- Ràng buộc hợp lệ của trạng thái và hành vi.
- Validation của input, business rule và authorization.
- Mapper nối database với domain và domain với API/event.
- Quy tắc mặc định, xử lý legacy và optimistic concurrency.

Điểm quan trọng là **domain object không phải chỉ là một bản sao của document**. Domain có thể có hành vi mà document không biểu diễn trực tiếp; document có thể có metadata vận hành mà domain không cần biết.

### 6.1. Phân biệt CreateOrderRequest, Order và OrderDocument

~~~text
CreateOrderRequest:
  customerId
  items[{sku, quantity}]

Domain Order:
  tenantId, orderId, customerId
  lines[{sku, quantity, unitPriceVnd}]
  totalVnd, currency, status
  createdAt, version, quy tắc chuyển trạng thái

Storage OrderDocument:
  _id, tenantId, orderId, customerId
  lines, totalVnd, status, createdAt
  version, schemaVersion, metadata lưu trữ
~~~

Client chỉ được chọn **sản phẩm và số lượng hợp lệ**. Giá, tổng, tenant và trạng thái ban đầu thuộc trách nhiệm server. Nếu nhận nguyên document từ request rồi ghi xuống database, client có thể thử gửi status=CONFIRMED hoặc totalVnd=0.

### 6.2. Java record minh họa DTO đầu vào

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @NotEmpty List<@Valid LineRequest> items
) {
    public record LineRequest(
        @NotBlank String sku,
        @Min(1) int quantity
    ) {}
}
~~~

Đây là cú pháp Java với Jakarta Bean Validation. Annotation chỉ có hiệu lực khi **validation được kích hoạt** tại boundary thích hợp; việc định nghĩa record không tự kiểm tra mọi lần khởi tạo.

Đầu vào trên không có totalVnd, status hoặc tenantId. Tầng application service phải lấy tenant từ danh tính đã xác thực, đọc giá có thẩm quyền và tính tổng.

### 6.3. Domain model bảo vệ bất biến

Một Order domain có thể có những bất biến:

~~~text
Order:
  lines không rỗng
  mỗi quantity > 0
  mỗi unitPriceVnd >= 0
  totalVnd tính theo snapshot giá, thuế/giảm giá nếu có
  trạng thái ban đầu = PENDING
  chỉ chuyển trạng thái theo state machine hợp lệ
  version tăng khi update thành công
~~~

Không phải mọi quy tắc đó đều kiểm tra được bằng JSON Schema. Chẳng hạn xác nhận thanh toán cần kết quả từ nguồn thanh toán có thẩm quyền; cập nhật tồn kho cần cơ chế transaction/conditional write; một số bất biến nằm **xuyên nhiều bản ghi hoặc dịch vụ**.

### 6.4. Value object làm rõ ý nghĩa dữ liệu

~~~java
public record OrderId(String value) {
    public OrderId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("orderId is required");
        }
    }
}

public record MoneyVnd(long amount) {
    public MoneyVnd {
        if (amount < 0) {
            throw new IllegalArgumentException("negative amount");
        }
    }
}
~~~

**MoneyVnd** thể hiện đơn vị là đồng Việt Nam, giúp tránh trộn nhầm với USD hoặc số thực. Với ứng dụng đa tiền tệ, nên dùng value object có currency, amount và chính sách minor units/rounding rõ ràng.

### 6.5. Cập nhật đồng thời phải dựa trên bảo đảm thật

Hai request đọc Order version 5, sau đó một request xác nhận và một request hủy. Chỉ kiểm tra trong memory không đủ ngăn cả hai cùng ghi.

~~~text
UPDATE Order
SET status = CONFIRMED, version = 6
WHERE orderId = O1001
  AND version = 5
  AND status = PENDING
~~~

Đây là **pseudocode** mô tả compare-and-set/optimistic concurrency, không phải câu lệnh chung cho mọi NoSQL. Phải dùng thao tác ghi có điều kiện hoặc transaction mà engine cam kết thực hiện atomic trong phạm vi tương ứng.

## 7. Data contract: cấu trúc được cam kết tại ranh giới hệ thống

**Data contract** là thỏa thuận giữa producer và consumer về nội dung trao đổi qua:

- HTTP API REST hoặc GraphQL.
- gRPC hay RPC khác.
- Event qua message broker.
- File batch CSV/JSON/Parquet.
- CDC feed, dữ liệu lake hoặc integration API.

Hợp đồng tốt không chỉ ghi tên field mà nêu cả:

| Nội dung contract | Ví dụ |
| --- | --- |
| Trường và kiểu | orderId là string, totalVnd là int64 |
| Bắt buộc/tùy chọn | orderId required, note optional |
| Ý nghĩa và đơn vị | totalVnd là số tiền bằng VND, không phải USD |
| Date-time | createdAt là một instant dạng ISO 8601 UTC |
| Enum | status chấp nhận giá trị nào; xử lý giá trị lạ ra sao |
| Version | Những thay đổi nào compatible, deprecation bao lâu |
| Lỗi | HTTP 400/409/404 và cấu trúc lỗi |
| Retry/idempotency | Có được gửi lại request cùng ID không? |
| Tính nhất quán | Response xác nhận nguồn hay chỉ queue đã nhận? |
| Quyền | Field nào được cung cấp cho vai trò nào |

**Dùng cùng tên field không bảo đảm cùng ý nghĩa.** Field price=100 có thể là VND, cent USD hoặc đã bao gồm thuế. Hợp đồng phải nói rõ đơn vị và quy tắc.

## 8. Ví dụ hợp đồng API khác document lưu trữ

Một HTTP response có thể là:

~~~json
{
  "orderId": "O1001",
  "customerId": "C08",
  "status": "PENDING",
  "items": [
    {
      "sku": "P10",
      "quantity": 2,
      "unitPriceVnd": 225000
    }
  ],
  "totalVnd": 450000,
  "currency": "VND",
  "createdAt": "2026-11-14T03:00:00Z"
}
~~~

Response này **không trả** MongoDB _id, tenantId nội bộ, storage schemaVersion, migrationMarker hay field vận hành không cần thiết. Nếu API cần công khai tenantId, đó phải là quyết định thiết kế có chủ đích, không phải hệ quả của việc serialize toàn bộ document.

Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Order detail
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
components:
  schemas:
    OrderResponse:
      type: object
      required: [orderId, status, totalVnd, currency, createdAt]
      properties:
        orderId:
          type: string
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        totalVnd:
          type: integer
          format: int64
          minimum: 0
        currency:
          type: string
          const: VND
        createdAt:
          type: string
          format: date-time
~~~

Đây là một phần hợp đồng minh họa, không phải đặc tả API hoàn chỉnh. API thật cần định nghĩa items, authentication, lỗi, visibility, response khi chưa có đơn và các điều kiện liên quan. Khả năng xử lý keyword JSON Schema/OpenAPI cần được kiểm tra với phiên bản generator/validator đang sử dụng.

### 8.1. Vì sao không cho DTO phụ thuộc trực tiếp vào database?

Giả sử database đổi **customerId** thành **customerKey** để phù hợp một index mới. Nếu response serialize nguyên persistence entity, thay đổi nội bộ có thể khiến client không còn thấy customerId.

Nếu có mapper:

~~~text
Storage:
  customerKey = "C08"

Mapper:
  customerId = storage.customerKey

HTTP API:
  customerId = "C08"
~~~

API có thể giữ ổn định trong khi storage tiến hóa. Tương tự, API có thể thêm field mới mà không bắt buộc mọi collection đều lưu trường đó nếu nó tính được an toàn từ domain.

## 9. Một luồng tạo đơn qua cả ba cấp schema

### Bước 1 — Client gửi request

~~~json
{
  "customerId": "C08",
  "items": [
    {"sku": "P10", "quantity": 2}
  ]
}
~~~

### Bước 2 — Application tạo Order

~~~text
1. Xác thực danh tính và lấy tenantId có thẩm quyền.
2. Validate customerId, SKU, quantity và quyền mua.
3. Đọc giá và thông tin sản phẩm có thẩm quyền.
4. Tạo snapshot dòng hàng và totalVnd.
5. Đặt trạng thái PENDING, cấp orderId.
6. Lưu bằng transaction/ghi điều kiện phù hợp.
7. Tạo response theo hợp đồng HTTP.
8. Phát event tin cậy nếu các hệ khác cần biết.
~~~

### Bước 3 — Storage nhận OrderDocument

~~~text
_id, tenantId, orderId, customerId
lines, totalVnd, currency, status
createdAt, updatedAt
version, schemaVersion
~~~

### Bước 4 — HTTP response trả dữ liệu công khai

~~~text
orderId, customerId, items
totalVnd, currency, status, createdAt
~~~

### Bước 5 — Event thông báo qua contract riêng

~~~json
{
  "eventId": "EVT-1001",
  "eventType": "OrderCreated",
  "eventSchemaVersion": 1,
  "aggregateId": "O1001",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-14T03:00:00Z",
  "payload": {
    "orderId": "O1001",
    "customerId": "C08"
  }
}
~~~

Một event **OrderCreated** chỉ có nghĩa đơn đã được tạo theo hợp đồng, không đồng nghĩa **OrderPaid** hay **OrderConfirmed**. Consumer phải hiểu sự kiện tương ứng với trạng thái nghiệp vụ nào.

## 10. Chuyển kiểu giữa BSON, Java và JSON

| Ý nghĩa | Storage | Java application | JSON contract |
| --- | --- | --- | --- |
| ID nghiệp vụ | string / text / encoded key | String, OrderId | string |
| ID nội bộ MongoDB | ObjectId | ObjectId hoặc wrapper tại repository | Thường không công khai |
| Thời điểm tuyệt đối | BSON Date / timestamp | Instant | string ISO 8601 UTC |
| Ngày lịch | date hoặc string có quy tắc | LocalDate | string format date |
| Tiền VND | BSON int64 / CQL bigint | long, MoneyVnd | integer int64 hoặc string đã quy định |
| Tiền có phần lẻ | Decimal128/decimal hay integer minor units | BigDecimal + Currency | decimal string hoặc format theo contract |
| Trạng thái | string | enum/state machine | string enum |
| Dòng hàng | array/list | List<OrderLine> | JSON array |
| Version | integer/long | long | number hoặc string theo contract |
| Vắng mặt | absent/null | nullable/Optional/tri-state | optional, null, empty cần phân biệt |

### 10.1. Tiền không nên dùng floating-point tùy tiện

Số thực nhị phân như double không biểu diễn chính xác mọi số thập phân. Khi cộng trừ tiền, cần định nghĩa đơn vị và độ chính xác:

- Với VND, có thể dùng số nguyên **số đồng** nếu miền giá trị đáp ứng.
- Với tiền tệ có phần lẻ, có thể dùng integer minor units hoặc decimal chính xác.
- Mỗi phép tính phải tuân quy tắc rounding và currency.

Field **amount=100** mà không ghi đơn vị là một nguồn gây lỗi hợp đồng rất lớn.

### 10.2. Kiểu số lớn qua JavaScript

Java long có thể chứa số nguyên vượt miền chính xác của JavaScript Number. Nếu contract gửi int64 dạng JSON number, consumer JavaScript cần được thiết kế để xử lý miền giá trị thực tế. Đối với giá trị có thể vượt **Number.MAX_SAFE_INTEGER**, có thể chọn biểu diễn **string** với format rõ ràng.

Không nên lúc thì gửi number, lúc thì gửi string chỉ vì giá trị lớn hơn một ngưỡng; đổi kiểu là thay đổi schema và cần được thông báo.

### 10.3. Timestamp phải có ý nghĩa thời gian

Hai chuỗi:

~~~text
2026-11-14T10:00:00+07:00
2026-11-14T03:00:00Z
~~~

biểu diễn cùng một **instant**. Nhưng **2026-11-14 10:00** không có timezone thì mơ hồ. Hãy xác định rõ:

- Instant hay local date/local datetime?
- Có cho phép offset hay bắt buộc UTC?
- Độ chính xác milliseconds/microseconds?
- Cách deserialize và compare?

Không dùng thời gian hiển thị theo ngôn ngữ người dùng làm khóa sort/range nếu chưa chuẩn hóa.

### 10.4. Missing, null và empty không bắt buộc giống nhau

~~~json
{}
~~~

~~~json
{"note": null}
~~~

~~~json
{"note": ""}
~~~

Trong một PATCH API, có thể quy định:

- **Missing:** không thay đổi note.
- **Null:** xóa giá trị note.
- **Empty string:** gán note rỗng hoặc trả lỗi validation.

Nếu framework deserialize missing và null thành cùng một giá trị Java, cần cơ chế riêng để giữ khác biệt khi contract yêu cầu.

### 10.5. Enum mới cũng có thể là breaking change

Một client cũ hiểu **PENDING / CONFIRMED / CANCELLED**. Server thêm **ON_HOLD**. JSON vẫn là string, nhưng code client dùng enum đóng có thể lỗi khi gặp ON_HOLD.

Phải quyết định: enum được coi là mở với nhánh **UNKNOWN**, hay thêm giá trị cần version API/điều phối rollout. Không đánh đồng tương thích về kiểu JSON với tương thích nghiệp vụ.

## 11. Schema-on-write và schema-on-read

**Schema-on-write** kiểm tra hoặc chuẩn hóa cấu trúc tại thời điểm ghi. **Schema-on-read** diễn giải hình dạng khi đọc, có thể dựa vào version hoặc shape của record.

~~~text
Schema-on-write:
  input -> validate + normalize -> persist

Schema-on-read:
  input -> persist
  reader -> detect version/shape -> map to domain
~~~

Hai chiến lược này không hoàn toàn loại trừ nhau:

- MongoDB cho phép document linh hoạt nhưng có thể bật schema validator.
- Cassandra có schema cột tường minh, nhưng ứng dụng vẫn phải hiểu ngữ nghĩa và cách chuyển dữ liệu cũ.
- Một dữ liệu JSON cũ có thể được upcast khi đọc dù bản mới đã được validate khi ghi.
- Một event log có schema registry nhưng consumer vẫn phải xử lý version cũ trong retention window.

**Schema-on-read không đồng nghĩa mỗi reader được tự diễn giải theo ý riêng.** Contract về ý nghĩa và đơn vị vẫn cần nhất quán.

## 12. Schema evolution: vì sao thay đổi nhỏ có thể ảnh hưởng lớn?

Khi hệ thống vận hành, có thể đồng thời tồn tại:

~~~text
Document v1: hàng triệu bản ghi cũ
Document v2: bản ghi mới được tạo
Service A: code cũ vẫn đang chạy
Service B: code mới đã triển khai
Event v1: còn trong queue hoặc archive
Search index: đang reindex dở
Mobile client: chưa nâng phiên bản API
~~~

**Schema evolution** là thay đổi định nghĩa cấu trúc hoặc hợp đồng. **Data migration** là biến đổi dữ liệu đã lưu để tương thích với định nghĩa mới. Hai việc liên quan nhưng không phải một:

- Thêm field optional vào model có thể không cần sửa ngay mọi document cũ.
- Biến field string thành cấu trúc object có thể cần mapper/backfill.
- Đổi partition key có thể cần tạo bảng/index mới và chuyển cách đọc/ghi.
- Đổi ý nghĩa của cùng một field có thể gây sai báo cáo mà không sinh lỗi parse nào.

Vì vậy, phải xem thay đổi từ cả **writer, reader, record cũ, record mới và bản chiếu liên quan**.

## 13. Backward, forward và full compatibility

Với một producer ghi dữ liệu và consumer đọc dữ liệu:

- **Backward compatibility:** reader mới có thể đọc dữ liệu do writer cũ tạo.
- **Forward compatibility:** reader cũ có thể đọc dữ liệu do writer mới tạo.
- **Full compatibility:** hai chiều đều được đáp ứng trong phạm vi đã quy định.

Các registry có thể dùng định nghĩa chi tiết về version trước hoặc mọi version lịch sử; phải kiểm tra chính sách và ngữ nghĩa công cụ cụ thể.

### 13.1. Thêm một trường optional

Payload v1:

~~~json
{"orderId": "O1001", "status": "PENDING"}
~~~

Payload v2:

~~~json
{
  "orderId": "O1001",
  "status": "PENDING",
  "note": "Giao giờ hành chính"
}
~~~

Reader mới thường đọc được v1 nếu note là optional và có quy tắc xử lý khi vắng. Reader cũ **có thể** đọc v2 nếu nó chấp nhận unknown fields. Nhưng nếu nó cấm property không khai báo, thêm note vẫn gây lỗi.

Vì thế **“thêm optional field luôn an toàn”** không đúng nếu chưa xác định hành vi consumer.

### 13.2. Đổi kiểu gây lỗi đọc/ghi

Từ:

~~~json
{"totalVnd": 450000}
~~~

sang:

~~~json
{"totalVnd": "450000"}
~~~

là thay đổi contract dù hai giá trị nhìn có vẻ giống nhau. Consumer parse số nguyên hoặc tính toán có thể hỏng. Có thể cần một field mới, mapper hỗ trợ hai dạng hoặc version rõ ràng.

### 13.3. Đổi tên field không phải thay nhãn đơn giản

Đổi **customerId** thành **buyerId** có thể ảnh hưởng query/index, serializer, event, batch, API và client. Nếu ngữ nghĩa vẫn như cũ, có thể dùng alias khi đọc, duy trì field cũ một thời gian và backfill sau.

### 13.4. Đổi ý nghĩa nhưng giữ kiểu còn nguy hiểm hơn

Field **totalVnd** ban đầu là giá hàng trước phí vận chuyển, sau đó được dùng làm tổng tiền phải trả đã cộng thuế/phí. Dù schema vẫn là integer, consumer báo cáo có thể tính sai.

Nếu ý nghĩa thay đổi lớn, nên cân nhắc field mới như **payableAmountVnd** và tài liệu version thay vì âm thầm tái sử dụng tên cũ.

## 14. Expand – migrate – contract: một quy trình thay schema an toàn hơn

Ví dụ document cũ:

~~~json
{
  "orderId": "O1001",
  "addressText": "12 Đường A, Quận B"
}
~~~

Thiết kế muốn chuyển sang:

~~~json
{
  "orderId": "O1001",
  "shippingAddress": {
    "line1": "12 Đường A",
    "district": "Quận B",
    "countryCode": "VN"
  }
}
~~~

Không nên xóa ngay **addressText** khi một phần dữ liệu và client cũ vẫn dùng nó.

### 14.1. Expand: reader hiểu cả hai

~~~text
if shippingAddress exists:
    parse shippingAddress
else if addressText exists:
    map legacy addressText into a compatible domain representation
else:
    apply missing-value policy or report bad data
~~~

Nếu địa chỉ dạng chuỗi không thể tách chắc chắn thành line1/district, không nên suy đoán. Có thể giữ **rawText** hoặc yêu cầu bổ sung thông tin.

### 14.2. Migrate: writer mới và backfill dữ liệu cũ

1. Triển khai writer mới theo cấu trúc v2.
2. Nếu còn reader cũ, cân nhắc duy trì output/field cũ một thời gian.
3. Backfill dữ liệu theo batch nhỏ có checkpoint và giới hạn tải.
4. Ghi có điều kiện để tránh ghi đè cập nhật mới của người dùng.
5. Theo dõi version, tỷ lệ chuyển đổi và các trường hợp không thể tự chuyển.

Pseudo-code:

~~~text
for each order with old schema:
    read order and revision
    map old data if conversion is safe
    write new shape IF revision has not changed
    on conflict: reload or retry
    checkpoint success/failure
~~~

### 14.3. Contract: ngừng field cũ sau khi đã bảo đảm tương thích

Chỉ bỏ logic đọc/ghi cũ khi:

- Writer cũ đã ngừng.
- Reader/consumer cần thiết đã hiểu v2.
- Data migration đạt tiêu chí hoàn tất.
- Queue, batch, backup và các hệ lâu không truy cập có phương án đọc dữ liệu cũ.
- Có giám sát và rollback/runbook phù hợp.

Việc siết DB validator thành required v2 trước khi dữ liệu cũ được xử lý có thể làm những cập nhật hợp lệ trên document legacy thất bại.

### 14.4. Dual-write không miễn phí

Nếu ghi cả cấu trúc cũ và mới ở hai nơi:

~~~text
write v1 -> success
write v2 -> timeout
~~~

hai bản có thể lệch. Nếu cùng một document và được sửa trong một thao tác atomic, rủi ro khác với ghi ở hai hệ riêng. Khi dual-write qua nhiều hệ, cần transaction/outbox, idempotency và đối soát.

Không phải thay đổi nào cũng cần dual-write; **dual-read và một writer chuẩn** có thể đơn giản hơn.

## 15. Phiên bản nào nên tăng khi schema thay đổi?

Một hệ có nhiều loại version:

| Loại version | Ví dụ | Mục đích |
| --- | --- | --- |
| Storage schema | schemaVersion = 2 | Cách deserialize document |
| Domain aggregate revision | version = 43 | Thứ tự update và chống lost update |
| API contract | /v1/orders | Tương thích với client |
| Event schema | eventSchemaVersion = 3 | Cách giải mã message |
| Event identity | eventId = EVT-1001 | Chống xử lý trùng |
| Deployment | release 2026.11 | Phiên bản phần mềm |

Các giá trị này **không cần bằng nhau hoặc tăng cùng lúc**. Một Order có thể được sửa 43 lần trong khi storage schema vẫn là v2. Một thay đổi index thuần túy có thể không ảnh hưởng API/event schema.

### 15.1. Có cần schemaVersion trên từng record?

Các lựa chọn:

- **Field schemaVersion:** hữu ích khi document cũ/mới cùng tồn tại.
- **Phát hiện qua shape:** có thể dùng với chuyển đổi đơn giản, nhưng dễ mơ hồ khi field optional.
- **Phiên bản theo collection/index:** thuận lợi khi toàn bộ tập dữ liệu đã được migration, nhưng phức tạp khi rolling upgrade.

Nếu dùng schemaVersion, cần nêu giá trị mặc định cho record thiếu field, những phiên bản được hỗ trợ và hành vi khi thấy version tương lai.

### 15.2. Upcaster: chuyển dữ liệu cũ khi đọc

~~~text
Stored v1 -> v1-to-v2 mapper -> Domain v2
Stored v2 ------------------> Domain v2
~~~

Reader có thể đọc dữ liệu cũ mà không phải cập nhật ngay từng document. Nhưng upcasting chỉ an toàn nếu có đủ thông tin để chuyển. Nếu v1 thiếu currency và có thể từng ghi nhiều loại tiền, không được mặc định mọi số tiền cũ đều là VND.

Upcaster cũng cần được giữ đủ lâu để đọc backup/archive chứa schema cũ.

## 16. Schema hợp đồng của sự kiện và thông điệp

Event thường được lưu trong broker/log để consumer xử lý trễ hoặc phát lại. Vì vậy code mới phải có khả năng đọc payload được tạo bởi **những phiên bản cũ**.

Một ví dụ:

~~~json
{
  "eventId": "EVT-2001",
  "eventType": "OrderConfirmed",
  "eventSchemaVersion": 1,
  "aggregateId": "O1001",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-14T03:05:00Z",
  "payload": {
    "orderId": "O1001",
    "totalVnd": 450000
  }
}
~~~

**OrderConfirmed** là sự kiện đã xảy ra theo ngữ nghĩa producer. Nó khác command **ConfirmOrder**, vốn chỉ là yêu cầu có thể thất bại.

Một consumer không nên cần biết MongoDB dùng ObjectId hoặc table nguồn đã đổi tên. Contract event chỉ chứa các field cần thiết, có version và thông tin idempotency.

### 16.1. Consumer có thể xử lý message trùng và đảo thứ tự

Trong một pipeline bất đồng bộ, cùng event có thể được giao lại:

~~~text
Order version 7 -> consumer nhận
Consumer cập nhật projection thành công
Consumer crash trước khi xác nhận đã xử lý
Broker gửi lại event version 7
~~~

Consumer phải idempotent theo **eventId**, **aggregateVersion** hoặc một cơ chế phù hợp. Nếu full-state event version 8 đến trước version 7, projection không nên bị ghi đè bằng trạng thái cũ.

Nhưng nếu event chỉ là delta “cộng thêm 1”, không thể mặc định bỏ các event version trung gian; phải xử lý đủ, đúng một lần theo semantics mong muốn hoặc dùng phép gộp phù hợp.

### 16.2. Avro, Protobuf, JSON Schema, OpenAPI, AsyncAPI

| Công nghệ | Vai trò |
| --- | --- |
| JSON Schema | Mô tả/validate dữ liệu JSON, quy tắc required, type và format |
| Avro | Dữ liệu schema-driven, hỗ trợ reader/writer schema resolution |
| Protocol Buffers | Định nghĩa message bằng field number, serialization gọn |
| OpenAPI | Mô tả HTTP API, request/response và schema liên quan |
| AsyncAPI | Mô tả message/interaction bất đồng bộ theo phiên bản công cụ |

Một **schema registry** có thể quản lý phiên bản và kiểm tra compatibility theo rule kỹ thuật. Nhưng registry không biết việc đổi nghĩa totalVnd từ “trước phí” sang “sau phí” là thay đổi sai nếu type vẫn là số.

### 16.3. Protobuf field number cần được bảo toàn

~~~protobuf
syntax = "proto3";

message OrderConfirmed {
  string event_id = 1;
  string order_id = 2;
  int64 total_vnd = 3;
  string confirmed_at = 4;
}
~~~

Khi bỏ một field, **không tái sử dụng tag cũ cho ý nghĩa khác**:

~~~protobuf
message OrderConfirmedV2 {
  string event_id = 1;
  string order_id = 2;
  reserved 3;
  string confirmed_at = 4;
  string currency = 5;
}
~~~

Ví dụ chỉ nhằm mô tả reserve tag, không có nghĩa mọi thay đổi đều cần tên message mới. Ngoài field number, phải xét default/presence semantics của proto3 và khả năng consumer cũ đọc payload mới. Với scalar thông thường, cần dùng cơ chế **optional** hoặc **oneof** thích hợp nếu business cần phân biệt “không có trường” với “giá trị mặc định”.

## 17. Nhiều phiên bản chạy cùng lúc: compatibility matrix

Trong rolling deployment, producer v1/v2 và consumer v1/v2 có thể đồng thời tồn tại:

| Producer | Consumer | Câu hỏi |
| --- | --- | --- |
| V1 | V1 | Hành vi hiện tại có ổn không? |
| V1 | V2 | Consumer mới đọc dữ liệu cũ thế nào? |
| V2 | V1 | Consumer cũ xử lý field/enum mới thế nào? |
| V2 | V2 | Chức năng mục tiêu có đúng không? |

Với storage schema, có thể thay producer bằng **writer** và consumer bằng **reader**. Với API, phải xác định chiều giao tiếp: khi server trả response thì server là producer; khi client gửi request thì client là producer.

### 17.1. Contract test cần cả dữ liệu lịch sử

Các trường hợp nên xuất hiện trong bộ test:

- Deserialize bản ghi/event v1 bằng code reader v2.
- Đọc payload v2 bằng consumer v1 trong phạm vi contract.
- Optional/missing/null/empty.
- Enum mới hoặc unknown field.
- Số nguyên lớn, decimal, timestamp/timezone và Unicode.
- ID có định dạng hợp lệ nhưng thuộc tenant khác.
- Message trùng, đảo thứ tự và bị xóa.
- Lỗi API và idempotency.

Contract test phát hiện phụ thuộc giữa các bên; nó **không thay** kiểm tra business invariant, migration dữ liệu thực hoặc khả năng khôi phục của database.

## 18. Những đặc điểm NoSQL dễ làm schema bị lệch

### 18.1. Schema drift trong document linh hoạt

Ba writer có thể ghi cùng một field createdAt:

~~~json
{"createdAt": "2026-11-14T03:00:00Z"}
~~~

~~~json
{"createdAt": 1794625200000}
~~~

~~~json
{"createdAt": {"seconds": 1794625200}}
~~~

Khi format không thống nhất, range/sort và mapper sang Java Instant có thể lỗi hoặc trả kết quả không như mong muốn. Cần chuẩn hóa tại boundary, thống nhất serialization và theo dõi dữ liệu sai kiểu.

### 18.2. Denormalization tạo nhiều storage schema cho cùng thực thể

~~~text
orders_by_id:
    orderId -> full order

orders_by_customer_day:
    tenant/customer/day -> summary + createdAt

search_orders:
    text/keyword fields + permissions
~~~

Ba bản chiếu phục vụ ba kiểu đọc; chúng **không cần cùng hình dạng**. Tuy nhiên, phải xác định nguồn authoritative, đường cập nhật, replay và reconciliation. Nếu ghi từng nơi độc lập mà không có hợp đồng cập nhật, các bản chiếu có thể lệch vô hạn.

### 18.3. Dynamic mapping có thể làm số field tăng không kiểm soát

Một search engine/document index tự tạo mapping cho field mới có thể bị **mapping explosion** nếu payload chứa hàng nghìn tên thuộc tính động do người dùng tạo:

~~~json
{
  "attributes": {
    "field_0001": "A",
    "field_0002": "B",
    "field_0003": "C"
  }
}
~~~

Khi số field tăng cao, metadata và chi phí index/cluster có thể trở thành vấn đề. Nên giới hạn số/tên field động, chọn kiểu mapping hoặc mô hình attributes thích hợp, thay vì mặc định mọi JSON đều có thể index tùy ý.

### 18.4. Đổi kiểu ảnh hưởng cả truy vấn

Nếu **totalVnd** được lưu là string:

~~~text
"100", "20", "3"
~~~

thứ tự từ điển khác thứ tự số. Đổi sang integer không chỉ sửa parser mà còn đổi semantics sort/range và index. Cần migration cả storage, query và contract.

### 18.5. Thay đổi partition key không chỉ là rename

Nếu thiết kế cũ:

~~~text
PK = tenantId + orderId
~~~

thiết kế mới muốn:

~~~text
PK = tenantId + customerId + orderDay
SK = createdAt + orderId
~~~

đây là thay đổi **đường truy cập**. Có thể cần tạo table/index mới, backfill, dual-read/write có kiểm soát rồi chuyển traffic. Không nên kỳ vọng chỉ sửa annotation trong Java sẽ tự chuyển dữ liệu và phân phối tải.

### 18.6. TTL, retention và deletion thuộc quy ước schema

Một document giỏ hàng nháp có thể có TTL; một đơn đã thanh toán có yêu cầu lưu giữ khác. Nếu gắn TTL nhầm vào data source of truth, dữ liệu có thể biến mất đúng theo cấu hình.

Khi đổi schema hoặc xóa record, cần kiểm soát backup, tombstone, event cũ, bản chiếu tìm kiếm và dữ liệu nhạy cảm. Không nên chỉ xóa bản ghi trong một collection rồi cho rằng toàn hệ đã xóa.

## 19. Validation và authorization nên thực hiện ở lớp nào?

~~~mermaid
flowchart TD
    A["Untrusted request"] --> B["Parse và contract validation"]
    B --> C["Authentication / Authorization"]
    C --> D["Domain rules và state transition"]
    D --> E["Atomic conditional write / DB constraints"]
    E --> F[("Persist")]
~~~

Mỗi lớp làm nhiệm vụ khác nhau:

**Contract validation:** kiểm tra kiểu, required, min/max, length, định dạng và các field được phép. Ví dụ quantity phải lớn hơn 0.

**Authorization:** xác định người dùng được đặt đơn cho customer/tenant nào. Một tenantId đúng kiểu không có nghĩa người gọi có quyền.

**Domain validation:** xác định giá, tổng tiền, trạng thái, giới hạn nghiệp vụ và sự phối hợp với các aggregate khác.

**Storage enforcement:** dùng unique index, validator, transaction/conditional update để ngăn ghi sai khi có concurrency hoặc writer khác.

Một lỗi API có thể trả:

~~~json
{
  "code": "VALIDATION_ERROR",
  "message": "Invalid order request",
  "details": [
    {
      "field": "items[0].quantity",
      "reason": "must be at least 1"
    }
  ]
}
~~~

Hợp đồng lỗi cũng cần nhất quán, tránh trả stack trace hoặc dữ liệu nội bộ nhạy cảm cho client.

## 20. Triển khai schema migration trên hệ đang có tải

Trước migration, cần kiểm kê toàn bộ reader/writer:

- HTTP services và mobile clients.
- Background jobs và scripts.
- Event consumers, CDC connector.
- Search indexers, cache builders, analytics.
- Các công cụ admin, import/export.
- Backup và bản lưu trữ có thể cần restore về sau.

Một kế hoạch thực tế cho thay đổi field có thể là:

1. **Định nghĩa contract mới:** type, semantics, compatibility, owner.
2. **Triển khai reader chấp nhận cả cũ/mới:** tránh lỗi khi thấy dữ liệu legacy.
3. **Bổ sung telemetry:** biết bao nhiêu document/event cũ chưa được chuyển.
4. **Chuyển writer:** ghi shape mới; có thể duy trì shape cũ tạm khi cần.
5. **Backfill theo batch:** checkpoint, rate limit, điều kiện version để tránh lost update.
6. **Chuyển index/query:** không bỏ đường đọc cũ trước khi dữ liệu mới đã sẵn sàng.
7. **Đối soát:** số record, version, invariant và bản chiếu.
8. **Ngừng writer cũ:** chỉ sau khi mọi producer đã được kiểm soát.
9. **Gỡ field cũ/siết validator:** sau retention và migration.
10. **Giữ khả năng restore:** backup cũ có thể chứa schema cũ mà code mới vẫn cần đọc.

### 20.1. Rollback có thể thất bại nếu code cũ không đọc được dữ liệu mới

Nếu writer v2 đã ghi document mới rồi rollback code về v1, v1 có thể không parse được v2. Vì vậy, cần kế hoạch rollback **có khả năng đọc hai version**, hoặc một cách chuyển ngược dữ liệu nếu thực sự có thể và được xác minh.

Không phải mọi migration đều đảo ngược được, nhất là khi đã xóa thông tin hoặc thay đổi nghĩa field. Backup không thay thế kế hoạch tương thích, vì restore có thể kéo lùi những ghi hợp lệ.

### 20.2. Đo tiến độ thay vì đoán đã xong

Các metric gợi ý:

~~~text
number_of_documents_by_schemaVersion
deserialization_error_count
unknown_enum_count
old_client_version_usage
event_consumer_lag
dead_letter_event_count
backfill_conflict_and_retry_rate
projection_version_drift
reindex_completion
~~~

Nếu còn 0,1% document legacy, cần biết chúng nằm ở đâu, có được đọc không và phương án xử lý, thay vì xóa converter ngay vì “hầu hết đã chuyển”.

## 21. Quản trị hợp đồng và dữ liệu nhạy cảm

Khi nhiều nhóm cùng sản xuất và tiêu thụ dữ liệu, một schema nên có:

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| Owner | Ai chịu trách nhiệm thay đổi contract? |
| Canonical definition | File schema hoặc OpenAPI/AsyncAPI ở đâu? |
| Version policy | Khi nào đổi major/minor hoặc event schema version? |
| Compatibility rule | Thay đổi nào được phép khi consumer cũ vẫn hoạt động? |
| Consumers | Có những service, job, client nào? |
| Quality | Ai chịu trách nhiệm dữ liệu thiếu/sai kiểu? |
| Deprecation | Khi nào ngừng field hoặc endpoint cũ? |
| Privacy | Field nào là PII, ai có quyền nhận? |
| Retention | Dữ liệu tồn tại bao lâu trong DB, event log, backup, index? |
| Recovery | Đọc lại backup/event cũ bằng phiên bản code nào? |

Ví dụ email khách hàng có thể cần ở domain để gửi thông báo, nhưng **không cần đưa vào mọi bản chiếu tìm kiếm** hoặc mọi event. Dùng response DTO và event contract riêng giúp thực hiện **data minimization**.

Tuy nhiên, bỏ customerEmail khỏi response không tự xóa dữ liệu đã nằm trong log, backup hay cache. Phải có chính sách retention và xóa nhất quán với yêu cầu vận hành và bảo mật.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| “Schemaless” nghĩa là không cần quy ước | Cùng field lưu nhiều type và ý nghĩa | Định nghĩa schema ở cả ba cấp |
| Trả trực tiếp persistence entity qua API | Lộ metadata/PII, API phụ thuộc DB | Response DTO, mapper |
| Dùng request body quyết định tenant, total, status | Client có thể điều khiển dữ liệu không có thẩm quyền | Server xác thực, tính và validate |
| Chỉ validate tại API | Job/consumer khác vẫn có thể ghi sai | Các writer và DB constraint phù hợp |
| Chỉ validate tại DB | Không bảo vệ authorization và domain invariants | Validation phân tầng |
| Đổi number thành string âm thầm | Parse và sort/range sai | Version/field mới hoặc dual-read |
| Dùng timestamp string tùy ý | Lọc ngày và timezone sai | Kiểu time/UTC rõ |
| Không phân biệt missing với null | PATCH có thể xóa nhầm | Contract và parser tri-state |
| Thêm required field ngay | Dữ liệu legacy không đọc/ghi được | Expand–migrate–contract |
| Thêm giá trị enum rồi cho là an toàn | Client cũ có thể lỗi | Compatibility test và unknown strategy |
| Dùng một version cho mọi thứ | Nhầm phiên bản state với format | Version riêng theo mục đích |
| Reuse protobuf field number cũ | Message bị diễn giải sai | Reserve field number |
| Backfill ghi đè mù | Mất cập nhật mới | Conditional write theo revision |
| Duy trì nhiều projection không đối soát | Hệ có nhiều bản sai lệch | Replay, idempotency, reconciliation |
| Tự tạo vô hạn dynamic fields | Mapping/index phình to | Kiểm soát field/mapping |
| Rollback code cũ không đọc được v2 | Sự cố triển khai kéo dài | Kế hoạch rollback tương thích |

## 23. Bài tập thực hành

### Bài 1: Phân loại schema

Các thành phần:

~~~text
A. Unique index (tenantId, orderId)
B. Java Order.version
C. OpenAPI OrderResponse.totalVnd: int64
D. Rule CANCELLED không được CONFIRMED tùy tiện
E. MongoDB validator yêu cầu createdAt là Date
F. Event OrderConfirmed có eventSchemaVersion=2
~~~

**Câu hỏi:** Thành phần nào thuộc storage, application và contract?

**Gợi ý:** A và E chủ yếu là storage. B và D thuộc application/domain. C và F thuộc contract. Cùng một ràng buộc có thể được mô tả ở nhiều lớp nhưng trách nhiệm thực thi khác nhau.

### Bài 2: Request chứa field không có thẩm quyền

Client gửi:

~~~json
{
  "customerId": "C08",
  "items": [{"sku": "P10", "quantity": 2}],
  "status": "CONFIRMED",
  "totalVnd": 0,
  "tenantId": "T99"
}
~~~

**Câu hỏi:** JSON hợp lệ có đồng nghĩa request hợp lệ?

**Gợi ý:** Không. Server phải xác thực tenant/quyền, lấy giá từ nguồn có thẩm quyền, tính tổng và quyết định trạng thái. Contract đầu vào chỉ nên cho phép client điều khiển những trường phù hợp.

### Bài 3: Thêm trường optional

V1 chỉ có orderId và status. V2 thêm note optional. Reader mới đọc dữ liệu cũ được không? Reader cũ đọc dữ liệu mới được không?

**Gợi ý:** Reader mới cần có quy tắc thiếu note; reader cũ chỉ đọc được nếu chấp nhận unknown fields và không có giả định khác. Optional không bảo đảm tự động tương thích với mọi consumer.

### Bài 4: Phân biệt version

~~~text
schemaVersion = 2
aggregateVersion = 17
eventSchemaVersion = 3
~~~

**Câu hỏi:** Vì sao không cần ba số bằng nhau?

**Gợi ý:** Chúng lần lượt nói về cấu trúc lưu trữ, thứ tự cập nhật trạng thái và phiên bản message contract.

### Bài 5: Backfill khi có update đồng thời

Job đọc order revision 5 và đang chuyển addressText sang shippingAddress. Người dùng vừa cập nhật địa chỉ khiến order thành revision 6.

**Câu hỏi:** Nếu job viết lại document cũ sẽ ra sao? Cách phòng tránh?

**Gợi ý:** Ghi đè mù có thể làm mất địa chỉ mới. Cần update có điều kiện revision, phát hiện conflict, đọc lại và retry an toàn.

### Bài 6: Missing và null trong PATCH

~~~json
{}
~~~

~~~json
{"note": null}
~~~

~~~json
{"note": ""}
~~~

**Câu hỏi:** Nên xử lý ba trường hợp giống nhau không?

**Gợi ý:** Không bắt buộc. Ví dụ missing là giữ nguyên; null là xóa; empty string là đặt chuỗi rỗng hoặc trả lỗi. Contract phải định nghĩa rõ và parser phải giữ được khác biệt.

### Bài 7: Event cũ trong queue

Consumer OrderConfirmed v2 vừa được deploy, nhưng broker còn nhiều message v1. Có thể bỏ reader v1 ngay không?

**Gợi ý:** Không nếu vẫn cần replay/tiêu thụ message cũ. Consumer cần backward compatibility hoặc upcaster trong thời gian retention tương ứng.

### Bài 8: Chọn kiểu tiền và thời gian

~~~json
{
  "price": 0.1,
  "currency": "USD",
  "createdAt": "14/11/2026 10:00"
}
~~~

**Câu hỏi:** Rủi ro khi dữ liệu chạy qua Java, JavaScript và các timezone?

**Gợi ý:** Float có sai số biểu diễn; số tiền thiếu đơn vị nhỏ nhất/rounding; ngày giờ thiếu timezone và có thể mơ hồ thứ tự ngày–tháng. Dùng decimal/minor units và instant/offset chuẩn hóa.

### Bài 9: Đổi khóa truy cập NoSQL

Hệ chỉ lưu order theo orderId. Nay cần lấy 20 đơn mới nhất của một customer.

**Câu hỏi:** Thêm customerId vào JSON là đủ chưa?

**Gợi ý:** Chưa chắc. Cần index hoặc bảng/bản chiếu theo (tenantId, customerId, createdAt), kế hoạch backfill, đồng bộ và phân trang.

### Bài 10: Data minimization

Storage chứa _id, tenantId, customerEmail và metadata migrate. API công khai chỉ cần orderId, status và totalVnd.

**Câu hỏi:** Có nên serialize nguyên storage document không?

**Gợi ý:** Không. Dùng response DTO có kiểm soát, authorization phù hợp; tránh phát PII và metadata nội bộ tới consumer không cần thiết.

## 24. Kết luận

**NoSQL không xóa bỏ schema; nó làm rõ nhu cầu quản lý schema ở nhiều ranh giới.** Storage schema quyết định cách dữ liệu được lưu, định danh, lập chỉ mục và truy xuất. Application schema chứa ý nghĩa, kiểu domain và bất biến nghiệp vụ. Data contract định nghĩa những gì các hệ bên ngoài được phép gửi, nhận và kỳ vọng ổn định.

Một BSON document không cần giống hoàn toàn Java domain object; Java domain object cũng không cần trùng HTTP response hay event message. Tách ba cấp schema giúp bảo vệ quyền, giảm phụ thuộc vào database, thay đổi cấu trúc có kiểm soát và tránh lộ dữ liệu nội bộ.

Khi schema tiến hóa, phải xét **document cũ/mới, writer/reader cũ/mới, khóa và index, sự kiện còn tồn đọng, kiểu số/thời gian, enum, null/missing và ngữ nghĩa nghiệp vụ**. Mapper, validator, version độc lập, contract test và quy trình **expand–migrate–contract** là những công cụ quan trọng để hệ NoSQL thay đổi mà không ép mọi thành phần triển khai đồng thời hoặc âm thầm làm sai dữ liệu.
