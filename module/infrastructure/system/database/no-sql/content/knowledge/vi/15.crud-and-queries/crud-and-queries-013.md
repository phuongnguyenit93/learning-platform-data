# Ngôn ngữ truy vấn, API và điều kiện an toàn khi nhận đầu vào trong NoSQL

## 1. Vì sao viết đúng cú pháp truy vấn vẫn chưa đủ?

Giả sử hệ thống bán hàng cung cấp endpoint:

```http
GET /api/orders?status=PAID&minTotalVnd=200000&limit=20
```

Người dùng mong muốn danh sách đơn **đã thanh toán**, tổng tiền **từ 200.000 đồng**, giới hạn **20 kết quả**. Nhưng ứng dụng thực tế còn phải giải quyết những câu hỏi khác:

- Người dùng đã đăng nhập thuộc tenant nào và được xem những đơn nào?
- Tham số `status` có được phép là giá trị bất kỳ không?
- Nếu client gửi một **object chứa toán tử NoSQL** thay vì chuỗi thì sao?
- Nếu `limit` là `-1`, `10000000` hoặc chuỗi rất dài, hệ thống xử lý thế nào?
- Nếu client chỉ định tên cột, biểu thức truy vấn hoặc đường đi graph tùy ý, ứng dụng có thực thi không?
- Truy vấn đúng về bảo mật nhưng phải quét hàng triệu document thì có chấp nhận được không?
- Khi dữ liệu vừa ghi vào source mà read model còn trễ, API nên trả gì?

Một truy vấn an toàn phải đáp ứng đồng thời ba mục tiêu:

1. **Đúng ngữ nghĩa:** trả dữ liệu phù hợp với access pattern và điều kiện nghiệp vụ.
2. **Đúng phạm vi quyền:** không cho đầu vào người dùng thay đổi ranh giới tenant, tài nguyên hoặc quyền truy cập.
3. **Có chi phí kiểm soát được:** tránh scan, truy vấn regex, graph traversal hoặc aggregation quá rộng do đầu vào không được giới hạn.

Khác với một số ứng dụng chỉ dùng SQL, hệ sinh thái NoSQL có nhiều cách diễn đạt truy vấn: **lệnh key–value, document query DSL, biểu thức khóa, CQL, Cypher, JSON search DSL và API SDK**. Từng loại có rủi ro riêng, nhưng nguyên tắc nền tảng giống nhau: **không để dữ liệu do client cung cấp trở thành cấu trúc lệnh mà ứng dụng không chủ định cho phép**.

## 2. Nhìn tổng quan các ngôn ngữ và API truy vấn NoSQL

| Hệ dữ liệu | Cách truy vấn tiêu biểu | Đầu vào truy vấn chính | Cơ chế an toàn nên ưu tiên |
|---|---|---|---|
| **Redis** | Lệnh `GET`, `HGET`, `SCAN`, `SINTER`… | Key và các đối số lệnh | Truyền đối số riêng qua client, tạo key từ ID đã kiểm tra và namespace được cấp quyền |
| **MongoDB** | MongoDB Query Language (MQL), aggregation pipeline | BSON filter, operator `$eq`, `$in`, `$gte`… | Tự xây filter bằng driver và allowlist; không nhận thẳng query object từ client |
| **DynamoDB** | API `GetItem`, `Query`, `UpdateItem` và expression | Partition/sort key, expression attribute name/value | Query theo key được thiết kế; dùng placeholder và giới hạn filter/projection |
| **Cassandra** | Cassandra Query Language (CQL) | Câu lệnh CQL, partition/clustering key | Prepared statements và bind values; allowlist identifier/bảng |
| **Neo4j** | Cypher, API driver | Pattern nút–cạnh, `MATCH`, `WHERE` | Tham số hóa giá trị; chỉ chọn từ template/label/type đã cho phép |
| **Elasticsearch/OpenSearch** | JSON Query DSL, Search API | Cấu trúc query, field, filter, sort | Xây DSL phía server; không chuyển nguyên raw DSL hoặc script từ client |

**Tên ngôn ngữ truy vấn khác nhau không đồng nghĩa API tương đương.** Cùng một yêu cầu `status = PAID`:

- MongoDB có thể lọc trực tiếp field nếu có index phù hợp.
- Redis key–value thuần túy thường cần một index do ứng dụng quản lý hoặc một công cụ tìm kiếm bổ sung.
- DynamoDB `FilterExpression` không biến field thành khóa truy cập có hiệu quả như GSI.
- Cassandra thường cần bảng có partition key được tổ chức theo truy vấn.
- Neo4j có thể lọc thuộc tính node sau khi bắt đầu từ một node và duyệt cạnh.

Do đó phải hiểu cả **cú pháp** và **cách hệ lưu trữ truy cập dữ liệu**.

## 3. Tách hai phần: cấu trúc truy vấn và giá trị đầu vào

Một query có thể được nhìn thành:

```text
QUERY = STRUCTURE + VALUES

STRUCTURE:
  collection = orders
  condition = tenantId EQ ? AND status EQ ? AND totalVnd GTE ?
  sort = createdAt DESC, _id DESC
  limit <= 100

VALUES:
  tenantId = "T01"          (từ identity đã xác thực)
  status = "PAID"           (đã qua enum validation)
  minTotalVnd = 200000     (đã qua numeric validation)
```

**Structure** gồm tên collection, field được phép lọc, toán tử so sánh, sort, projection, số hop graph hoặc kiểu aggregation. **Values** là nội dung cụ thể như `PAID`, `200000` hoặc `C007`.

Ứng dụng nên **kiểm soát structure**, rồi truyền **values đã kiểm tra** vào các vị trí dữ liệu. Cách làm này:

1. Giảm khả năng **query/operator injection**.
2. Giữ những query shape mà hệ thống đã dự kiến và có index.
3. Dễ kiểm soát phân quyền và chi phí.
4. Giúp unit test và quan sát các query pattern thực tế.

Đừng hiểu “tham số hóa” là đủ cho mọi thành phần. Nhiều API chỉ tham số hóa **giá trị**, không tham số hóa tự do tên bảng, label, sort field hoặc cấu trúc operator. Những phần động này cần **allowlist** hoặc các template cố định.

## 4. Dữ liệu mẫu và hợp đồng truy vấn

Giả sử collection MongoDB `orders` chứa:

```javascript
db.orders.insertMany([
  {
    _id: "ORD-1001",
    tenantId: "T01",
    customerId: "C007",
    status: "PAID",
    totalVnd: 520000,
    createdAt: ISODate("2026-11-10T08:00:00Z"),
    shipping: { city: "Hà Nội" },
    items: [{ sku: "P10", quantity: 2 }]
  },
  {
    _id: "ORD-1002",
    tenantId: "T01",
    customerId: "C007",
    status: "PENDING",
    totalVnd: 150000,
    createdAt: ISODate("2026-11-11T09:00:00Z"),
    shipping: { city: "Đà Nẵng" },
    items: [{ sku: "P20", quantity: 1 }]
  },
  {
    _id: "ORD-2001",
    tenantId: "T02",
    customerId: "C007",
    status: "PAID",
    totalVnd: 900000,
    createdAt: ISODate("2026-11-12T10:00:00Z"),
    shipping: { city: "Hà Nội" },
    items: [{ sku: "P10", quantity: 4 }]
  }
]);
```

Đây là dữ liệu thử nghiệm; cả T01 và T02 có khách `C007` nên **customerId không đủ để xác định tenant**.

Hợp đồng API:

```http
GET /api/orders?status=PAID&minTotalVnd=200000&sort=newest&limit=20
Authorization: Bearer <access-token>
```

Các quy tắc:

- Tenant ID được lấy từ **principal đã xác thực**, không lấy từ query string.
- `status` chỉ nhận `PENDING`, `PAID` hoặc `CANCELLED`.
- `minTotalVnd` là số nguyên không âm trong khoảng hệ thống hỗ trợ.
- `sort` chỉ nhận `newest` hoặc `oldest`.
- `limit` là số nguyên từ 1 đến 100; mặc định 20.
- Response chỉ trả những field cần thiết cho màn hình.
- Mọi document phải thỏa **tenantId** và quyền đọc theo chính sách.

Nếu user thuộc T01, truy vấn ví dụ phải trả **ORD-1001**, không trả ORD-2001 dù đơn T02 cũng thỏa status và tổng tiền.

## 5. MongoDB MQL: filter là dữ liệu cấu trúc, không chỉ là chuỗi

MongoDB dùng BSON/JSON-like document để biểu diễn query. Một filter hợp lệ:

```javascript
db.orders.find({
  tenantId: "T01",
  status: "PAID",
  totalVnd: { $gte: 200000 }
});
```

Trong đó:

- `tenantId`, `status`, `totalVnd` là field.
- `$gte` là **toán tử MongoDB** được hệ quản trị diễn giải.
- `"PAID"` và `200000` là **giá trị**.

### 5.1. NoSQL operator injection

Một lỗi thiết kế nghiêm trọng là nhận một object từ HTTP request rồi dùng nguyên object đó như filter:

```javascript
// KHÔNG AN TOÀN nếu request.body là object do client kiểm soát:
const userFilter = request.body.filter;
const orders = await db.collection("orders")
  .find(userFilter)
  .toArray();
```

Client có thể gửi một biểu thức khác hẳn điều kiện UI dự kiến:

```json
{
  "filter": {
    "status": { "$ne": "PAID" }
  }
}
```

Thay vì “tìm đơn có status PAID”, request này yêu cầu **status khác PAID**. Nếu endpoint còn thiếu tenant guard hoặc cho phép nhiều toán tử nguy hiểm khác, phạm vi đọc có thể bị mở rộng ngoài ý định.

Một biến thể lỗi khác:

```javascript
// Sai khi status có thể là object:
const filter = { status: request.body.status };
```

Nếu JSON parser cho phép `status` là object và client gửi `{"status":{"$ne":"PAID"}}`, filter ứng dụng xây ra có thể chứa toán tử thay vì scalar string mong muốn. **Không đủ để nói “tôi đã đặt status vào object, vậy là an toàn”**; vẫn phải kiểm tra kiểu và enum.

### 5.2. Cách làm: chỉ nhận giá trị vô hướng được cho phép

```javascript
const ALLOWED_STATUS = new Set(["PENDING", "PAID", "CANCELLED"]);

function parseStatus(raw) {
  if (typeof raw !== "string" || !ALLOWED_STATUS.has(raw)) {
    throw new Error("Invalid status");
  }
  return raw;
}

const status = parseStatus(request.query.status);
const tenantId = authenticatedPrincipal.tenantId;

const filter = {
  tenantId,
  status
};

const result = await db.collection("orders")
  .find(filter)
  .limit(20)
  .toArray();
```

Ở đây client chỉ có thể chọn **một giá trị hợp lệ của status**. Operator và tên field đã được cố định bởi ứng dụng; tenant đến từ identity. Ví dụ chưa bao gồm việc kiểm tra quyền chi tiết từng đơn, error mapping và kiểm soát request lifecycle.

### 5.3. Xây filter bằng MongoDB Java Driver

Trong Java, nên dùng API biểu thức của driver thay vì ghép chuỗi query JSON:

```java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

// tenantId lấy từ principal; status đã kiểm tra enum;
// minTotalVnd đã được parse thành số nguyên hợp lệ.
Bson filter = and(
    eq("tenantId", tenantId),
    eq("status", status),
    gte("totalVnd", minTotalVnd)
);

MongoCollection<Document> orders = database.getCollection("orders");

orders.find(filter)
    .sort(descending("createdAt", "_id"))
    .limit(20)
    .forEach(order -> {
        // Chỉ xử lý những trường được phép trả về.
    });
```

API `Filters.eq`/`gte` tạo BSON filter đúng kiểu. Tuy nhiên, **driver không tự kiểm tra user có quyền chọn field hay giá trị đó không**. Nếu tên field truyền vào `eq(fieldName, value)` đến trực tiếp từ client mà không qua allowlist, ứng dụng vẫn cho phép truy vấn ngoài ý định.

### 5.4. Không dùng `$where` hoặc mã/script từ đầu vào tùy ý

Một số hệ truy vấn có cú pháp hoặc tính năng thực thi biểu thức/script. Với MongoDB, không nên xây điều kiện `$where` từ nội dung người dùng. Không có lý do để endpoint lọc đơn thông thường cho phép client cung cấp JavaScript predicate hoặc aggregation pipeline tự do.

**Cách an toàn là bỏ hẳn khả năng biểu diễn phép toán không nằm trong tập thao tác nghiệp vụ đã định**, không phải cố “escape” mọi chuỗi để biến thành mã chạy trong database.

## 6. Truy vấn động: allowlist field, toán tử và sort

Một màn hình quản trị có thể hỗ trợ lọc động:

```json
{
  "filters": [
    { "field": "status", "op": "eq", "value": "PAID" },
    { "field": "totalVnd", "op": "gte", "value": 200000 }
  ],
  "sort": "newest",
  "limit": 20
}
```

Đây là **query description do ứng dụng định nghĩa**, không phải MQL/Cypher/CQL raw. Tầng server cần ánh xạ nó sang biểu thức của database bằng bảng cho phép.

Ví dụ:

| Field công khai | Field lưu trữ | Toán tử cho phép | Kiểu giá trị |
|---|---|---|---|
| `status` | `status` | `eq`, `in` | Enum |
| `minTotalVnd` | `totalVnd` | `gte` | Số nguyên không âm |
| `maxTotalVnd` | `totalVnd` | `lte` | Số nguyên không âm |
| `customerId` | `customerId` | `eq` | Mã ID chuẩn hóa |
| `city` | `shipping.city` | `eq` | Chuỗi có độ dài giới hạn |
| `createdFrom` | `createdAt` | `gte` | Thời điểm hợp lệ |
| `createdBefore` | `createdAt` | `lt` | Thời điểm hợp lệ |

Không mở field `tenantId` như một điều kiện tự do để client thay đổi. Tương tự, các trường nội bộ như `fraudScore`, `internalNotes` hoặc `deletedAt` không nên tự động được đọc/lọc chỉ vì chúng xuất hiện trong schema.

### 6.1. Một builder chỉ có những query shape cho phép

Pseudocode:

```text
buildOrderQuery(authenticatedUser, request):
    tenantId = authorization.resolveTenant(authenticatedUser)

    filter = AND(
        EQ("tenantId", tenantId),
        EQ("status", parseAllowedStatus(request.status))
    )

    if request.minTotalVnd is present:
        filter += GTE("totalVnd", parseMoney(request.minTotalVnd))

    if request.city is present:
        filter += EQ("shipping.city", normalizeCity(request.city))

    sort = {
        "newest": [createdAt DESC, _id DESC],
        "oldest": [createdAt ASC, _id ASC]
    }[parseAllowedSort(request.sort)]

    limit = parseBoundedInteger(request.limit, 1, 100, default=20)

    return TrustedQuery(filter, sort, limit, allowedProjection)
```

Mọi tên field và operator được **chọn ở phía server**. Client gửi ý định nghiệp vụ, không gửi code hoặc cấu trúc database tùy ý.

### 6.2. Đặt giới hạn cho số điều kiện

Ngay cả khi từng filter hợp lệ, client vẫn có thể gửi **hàng nghìn điều kiện OR/IN** hoặc độ sâu nesting lớn. API lọc động cần định nghĩa thêm:

- Số filter tối đa, ví dụ 10 điều kiện.
- Số phần tử tối đa trong một danh sách `in`, ví dụ 50 ID.
- Độ sâu AND/OR nếu cho phép nhóm điều kiện.
- Chiều dài tối đa của chuỗi.
- Số field tối đa cho sort và projection.
- Chi phí tối đa hoặc loại aggregation được phép.

Các con số là **ví dụ hợp đồng sản phẩm**, không phải giới hạn mặc định của mọi NoSQL database.

## 7. Regex, wildcard và tìm kiếm văn bản: đầu vào có thể gây tải rất lớn

Một chức năng tìm kiếm theo tên có thể chọn regex:

```javascript
// Có rủi ro nếu userText được đưa vào regex một cách không kiểm soát:
db.products.find({
  name: { $regex: userText, $options: "i" }
});
```

Hai vấn đề khác nhau:

1. **Ngữ nghĩa:** input chứa ký tự như `.`, `*`, `^`, `$`, `[`, `(` có thể được hiểu là **cú pháp regex**, không còn là text literal.
2. **Tài nguyên:** một số pattern phức tạp có thể tiêu tốn CPU, hoặc điều kiện không sử dụng index hiệu quả và buộc quét rất nhiều bản ghi.

Nếu yêu cầu là **tìm một đoạn văn bản literal**, hãy escape đúng ký tự đặc biệt theo regex engine và giới hạn độ dài; không mở chức năng regex tùy ý chỉ bằng việc nhận text người dùng.

Ví dụ JavaScript:

```javascript
function escapeRegexLiteral(value) {
  return [...value]
    .map(ch => "\\^$.*+?()[]{}|".includes(ch) ? "\\" + ch : ch)
    .join("");
}

function buildLiteralPrefixPattern(raw) {
  if (typeof raw !== "string" || raw.length < 1 || raw.length > 60) {
    throw new Error("Invalid search text");
  }
  return "^" + escapeRegexLiteral(raw);
}
```

Đoạn trên minh họa nguyên tắc escape literal; cú pháp regex thực tế còn phụ thuộc engine và cách driver truyền string. Với tìm kiếm văn bản quy mô lớn, **text index/search engine** thường phù hợp hơn regex không giới hạn. Việc escape không thay thế các giới hạn tài nguyên và timeout.

### Đừng biến mọi trường text thành regex

Đối với mã đơn `ORD-1001`, hãy ưu tiên **so khớp chính xác** trên ID có index. Dùng regex kiểu “chứa ký tự” để tìm ID thường làm mất những lợi ích của exact lookup và tạo sự mơ hồ. Regex chỉ hợp lý nếu người dùng thật sự cần tìm theo mẫu và có thiết kế index/giới hạn tương ứng.

## 8. Điều kiện trên mảng và đường dẫn cũng phải do server kiểm soát

Với MongoDB, hai điều kiện trên cùng array-of-objects có thể khớp hai element khác nhau:

```javascript
// Có thể khớp SKU=P10 ở dòng A và quantity>=2 ở dòng B.
db.orders.find({
  "items.sku": "P10",
  "items.quantity": { $gte: 2 }
});
```

Nếu yêu cầu là **cùng một dòng hàng**, phải dùng:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "P10",
      quantity: { $gte: 2 }
    }
  }
});
```

Tương tự, ứng dụng không nên cho client tự gửi đường dẫn `items.$[].secretField` hoặc một path tùy ý vào thao tác update. Dot notation, array filters và update operators là **cấu trúc có sức mạnh biểu đạt**, cần được lựa chọn bởi mã ứng dụng và kiểm tra quyền ở từng trường.

### Trường thiếu, null và giá trị rỗng

Không nên dùng `if (value)` để quyết định có áp filter hay không, vì `0`, `false` và `""` có thể là giá trị được người dùng **cố ý gửi**.

Trong MongoDB:

```javascript
{ couponCode: null }                       // null hoặc missing
{ couponCode: { $exists: false } }         // missing
{ couponCode: { $type: "null" } }           // explicit null
{ couponCode: "" }                         // chuỗi rỗng
```

Hợp đồng API phải quyết định mỗi trạng thái có nghĩa gì; một query builder không nên tự ghép `null`, missing và chuỗi rỗng thành “không lọc” nếu nghiệp vụ cần phân biệt.

## 9. DynamoDB: expression placeholders và giới hạn của filter

Trong DynamoDB, thao tác `Query` nên bắt đầu từ partition key của table hoặc index. Ví dụ thiết kế:

```text
PK = "TENANT#T01#CUSTOMER#C007"
SK = "ORDER#2026-11-10T08:00:00Z#ORD-1001"
```

Một Query API minh họa với định dạng **low-level attribute values**:

```json
{
  "TableName": "Orders",
  "KeyConditionExpression": "#pk = :pk AND begins_with(#sk, :prefix)",
  "FilterExpression": "#status = :paid",
  "ExpressionAttributeNames": {
    "#pk": "PK",
    "#sk": "SK",
    "#status": "status"
  },
  "ExpressionAttributeValues": {
    ":pk": { "S": "TENANT#T01#CUSTOMER#C007" },
    ":prefix": { "S": "ORDER#" },
    ":paid": { "S": "PAID" }
  },
  "Limit": 25
}
```

Các placeholder:

- `#pk`, `#sk`, `#status` tham chiếu **tên thuộc tính** được server chọn.
- `:pk`, `:prefix`, `:paid` là **giá trị thuộc kiểu DynamoDB**.
- `KeyConditionExpression` quyết định đường truy xuất theo key.
- `FilterExpression` lọc **sau khi Query đọc item phù hợp key condition**, không biến status thành một secondary index.

**Tính đúng:** một trang `Query` có thể trả ít item hơn `Limit` sau khi filter, hoặc trả mảng rỗng trong khi vẫn còn `LastEvaluatedKey`. Client phải tiếp tục phân trang theo token khi cần truy xuất đủ kết quả; không được xem một trang rỗng là “không còn dữ liệu”.

**Tính an toàn:** không cho client thay `TableName`, `ExpressionAttributeNames`, `KeyConditionExpression` hoặc dùng `Scan` toàn bảng một cách tự do. Giá trị cũng phải được kiểm tra kiểu và phạm vi, dù được đặt qua placeholder.

### Vì sao parameter không tự bảo vệ ranh giới tenant?

`:pk` có thể được bind an toàn về cú pháp nhưng vẫn sai về quyền nếu lấy từ client:

```text
client đưa :pk = "TENANT#T02#CUSTOMER#C007"
-> request có thể đọc dữ liệu tenant khác nếu không có authorization
```

Ứng dụng phải **tạo PK từ principal và ID đã xác thực/kiểm tra**, đồng thời giới hạn IAM và quyền truy cập nơi có thể theo kiến trúc. Parameterization chống biến giá trị thành biểu thức lệnh; nó không tự cấp hoặc kiểm tra quyền nghiệp vụ.

## 10. Cassandra CQL: prepared statements và khóa phân vùng

Một bảng Cassandra ví dụ:

```sql
CREATE TABLE orders_by_customer (
    tenant_id text,
    customer_id text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY ((tenant_id, customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Một câu truy vấn dùng **bind markers**:

```sql
SELECT order_id, status, total_vnd, created_at
FROM orders_by_customer
WHERE tenant_id = ?
  AND customer_id = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT ?;
```

Khi driver chuẩn bị statement, dữ liệu thực được bind vào vị trí giá trị. Ví dụ Java với DataStax Java Driver 4.x (cú pháp minh họa cho driver tương ứng):

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.time.Instant;

String cql = """
    SELECT order_id, status, total_vnd, created_at
    FROM orders_by_customer
    WHERE tenant_id = ?
      AND customer_id = ?
      AND created_at >= ?
      AND created_at < ?
    LIMIT ?
    """;

PreparedStatement prepared = session.prepare(cql);
BoundStatement bound = prepared.bind(
    trustedTenantId,
    validatedCustomerId,
    Instant.parse("2026-11-01T00:00:00Z"),
    Instant.parse("2026-12-01T00:00:00Z"),
    20
);

session.execute(bound);
```

Ví dụ dùng Java có text block (Java 15+) và driver phù hợp. Các binding phải đúng kiểu Cassandra của schema. Nếu driver/phiên bản có giới hạn parameter ở vị trí `LIMIT`, cần điều chỉnh template theo API thực tế, **không thay bằng nối số do client gửi trực tiếp chưa kiểm tra**.

### Không tham số hóa identifier tùy ý

Trong CQL, tên bảng và cột không nên được ghép từ request:

```java
// KHÔNG AN TOÀN nếu tableName do client điều khiển:
String cql = "SELECT * FROM " + tableName + " WHERE tenant_id = ?";
```

Prepared statements chủ yếu bind **giá trị**, không có nghĩa client có thể chọn mọi identifier bằng bind marker. Nếu phải chọn nhiều bảng, dùng ánh xạ cố định từ **mã lựa chọn nghiệp vụ** sang template CQL đã định nghĩa.

### An toàn còn là thiết kế partition key

CQL query có parameter đúng vẫn có thể rất tốn tài nguyên nếu không có partition key hoặc yêu cầu lọc rộng bằng `ALLOW FILTERING`. Với truy vấn “liệt kê mọi đơn PAID theo tháng của một tenant”, bảng theo khách có thể không phù hợp; nên thiết kế **bảng phục vụ access pattern** hoặc cơ chế index phù hợp.

**Prepared statement không sửa được mô hình dữ liệu chọn sai partition.**

## 11. Neo4j Cypher: parameter cho giá trị, template cho cấu trúc mẫu

Cypher diễn đạt truy vấn graph bằng các mẫu nút/cạnh:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.tenantId = $tenantId
  AND c.customerId = $customerId
  AND o.tenantId = $tenantId
  AND o.status = $status
RETURN o.orderId AS orderId, o.status AS status
ORDER BY o.orderId
LIMIT $limit;
```

Giá trị `$tenantId`, `$customerId`, `$status`, `$limit` là parameters được driver truyền riêng. Với Java, ví dụ:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.Values;

String cypher = """
    MATCH (c:Customer)-[:PLACED]->(o:Order)
    WHERE c.tenantId = $tenantId
      AND c.customerId = $customerId
      AND o.tenantId = $tenantId
      AND o.status = $status
    RETURN o.orderId AS orderId
    ORDER BY o.orderId
    LIMIT $limit
    """;

try (Session session = driver.session()) {
    var result = session.run(
        cypher,
        Values.parameters(
            "tenantId", trustedTenantId,
            "customerId", validatedCustomerId,
            "status", "PAID",
            "limit", 20
        )
    );
    result.list();
}
```

Đây là cú pháp Java driver phổ biến để minh họa bind parameters; ứng dụng production còn cần quản lý database được chọn, timeout, transaction, quyền và kết quả.

### Tại sao không nối thẳng input vào Cypher?

```java
// KHÔNG AN TOÀN:
String cypher = "MATCH (c:Customer {customerId: '" 
    + requestCustomerId
    + "'}) RETURN c";
```

Input ở đây được đặt **bên trong source code của query**. Các ký tự đặc biệt có thể làm thay đổi cách parser hiểu câu lệnh hoặc tạo lỗi, trong khi tham số hóa giữ giá trị là dữ liệu.

### Label, relationship type và độ sâu traversal

Client có thể muốn chọn “quan hệ cần duyệt”. Đừng tự nối:

```text
MATCH (a)-[:<clientRelationshipType>*1..<clientDepth>]->(b)
```

Một số phiên bản Cypher có hỗ trợ cú pháp dynamic label/type, nhưng khả năng dùng parameter, đặc tính index và cách tối ưu phụ thuộc phiên bản. Cách an toàn, dễ dự đoán là **cho client chọn một enum nghiệp vụ**, rồi dùng một trong các query template đã được server duyệt:

```text
relationMode = "PURCHASES"
  -> MATCH (c:Customer)-[:PLACED]->(o:Order) ...

relationMode = "MEMBERSHIP"
  -> MATCH (u:User)-[:MEMBER_OF]->(t:Team) ...
```

Với traversal biến độ dài, phải giới hạn:

- Node bắt đầu có ID đã xác thực/được phép.
- Relationship type cho phép.
- Số hop tối đa.
- Số kết quả trả về.
- Fan-out và query timeout.

Một graph query tham số hóa hoàn hảo về cú pháp vẫn có thể gây tốn tài nguyên nếu client được phép chọn độ sâu vô hạn.

## 12. Redis: command arguments an toàn và key namespace

Redis khác document/graph database ở chỗ thao tác thường là **lệnh trên key**. Ví dụ:

```redis
HSET order:T01:ORD-1001 status PAID totalVnd 520000
HGET order:T01:ORD-1001 status
HGETALL order:T01:ORD-1001
```

Ứng dụng nên dùng Redis client truyền **tên command và các đối số riêng biệt**, không tạo một chuỗi shell/terminal rồi thực thi dựa trên input. Một ví dụ Java với API cấp cao giả định:

```java
String tenantId = authenticatedPrincipal.tenantId();
String orderId = parseOrderId(requestedOrderId);
String key = "order:" + encodeKeySegment(tenantId)
           + ":" + encodeKeySegment(orderId);

// Pseudocode: dùng client Redis tương ứng.
String status = redisClient.hget(key, "status");
```

Ở đây `encodeKeySegment` là **hàm do ứng dụng định nghĩa** để bảo đảm ID không chứa dấu phân cách hoặc ký tự gây nhập nhằng namespace; không phải API tiêu chuẩn của Redis.

### Key injection và lẫn tenant

Nếu ứng dụng dùng một quy ước key như `order:<tenant>:<orderId>` nhưng cho client tùy ý cung cấp tenant hoặc ID chứa dấu phân cách không được chuẩn hóa, việc hình thành key có thể trỏ sang tài nguyên khác ý định. Cần:

- Lấy tenant từ principal tin cậy.
- Kiểm tra ID theo định dạng đã định.
- Áp namespace nhất quán.
- Hạn chế lệnh/ACL của tài khoản kết nối Redis theo nhu cầu.
- Không để client chọn tùy ý tên command, key pattern hoặc Lua script.

### `KEYS` và `SCAN`

Một cách lọc “tìm tất cả key bắt đầu bằng prefix” nghe có vẻ đơn giản:

```redis
KEYS order:*
```

Nhưng `KEYS` quét không gian key và có thể gây ảnh hưởng tới khả năng đáp ứng khi tập dữ liệu lớn. `SCAN` giúp duyệt theo từng đợt, nhưng **không biến thao tác duyệt key thành một secondary index** và không tự bảo đảm snapshot nhất quán khi dữ liệu thay đổi.

Nếu hệ thống thường xuyên tìm đơn theo `status` hoặc `customerId`, nên xây cấu trúc truy cập riêng (set/sorted set/index) hoặc chọn datastore có khả năng query phù hợp. Đồng thời phải duy trì tính nhất quán giữa dữ liệu chính và index nghiệp vụ.

## 13. JSON search DSL: không nhận nguyên một query engine từ client

Một công cụ tìm kiếm như Elasticsearch/OpenSearch có API JSON query DSL. Ví dụ:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "T01" } },
        { "term": { "status": "PAID" } },
        { "range": { "totalVnd": { "gte": 200000 } } }
      ]
    }
  },
  "sort": [{ "createdAt": { "order": "desc" } }],
  "size": 20
}
```

Đây là một DSL có cấu trúc mạnh; client có thể diễn đạt nested bool, wildcard, aggregation, script, query string và nhiều kiểu truy vấn khác tùy sản phẩm. Nếu endpoint chỉ cần tìm đơn theo status và khoảng giá, không nên nhận **nguyên raw DSL** từ người dùng rồi gửi thẳng tới search engine.

Rủi ro bao gồm:

- Bỏ filter tenant/ACL.
- Chọn field nhạy cảm hoặc index khác.
- Sử dụng wildcard/regex/script tốn tài nguyên.
- Yêu cầu aggregation hoặc sort trên tập dữ liệu rất lớn.
- Thay đổi cấu trúc bool khiến filter quyền chỉ áp dụng cho một nhánh.

**Giải pháp:** xây JSON DSL từ những field/toán tử được server cho phép, áp filter quyền ở cấp chung, giới hạn `size`/sort/aggregation, kiểm tra query cost và dùng role/index permission tương ứng. Việc truyền JSON đúng cú pháp không tự làm truy vấn an toàn.

### Phân biệt search text và ngôn ngữ truy vấn

Trường `queryText` trong UI thường là **văn bản người dùng muốn tìm**, không phải một câu query string với toán tử. Nếu dùng một ngôn ngữ như query_string, các ký tự đặc biệt có thể được diễn giải là toán tử. Với nhu cầu tìm text thông thường, dùng những API full-text thích hợp và cấu hình cách xử lý input thay vì mở cú pháp truy vấn hoàn chỉnh tùy ý.

## 14. Validation: kiểm tra kiểu, phạm vi và ý nghĩa

Validation nên diễn ra trước khi xây query. Với API ở mục 4:

| Tham số | Ví dụ hợp lệ | Đầu vào không nên nhận | Kiểm tra |
|---|---|---|---|
| `status` | `PAID` | Object `{"$ne":"PAID"}`, enum lạ | String thuộc allowlist |
| `minTotalVnd` | `200000` | `-10`, `NaN`, số vượt phạm vi | Số nguyên không âm, giới hạn |
| `limit` | `20` | `0`, `-1`, `1000000` | Số nguyên 1–100 |
| `sort` | `newest` | `internalScore`, object query | Enum `newest/oldest` |
| `customerId` | `C007` | Object, chuỗi quá dài | Kiểu string, format, length |
| `city` | `Hà Nội` | Regex/script được gửi như object | String literal được chuẩn hóa |
| `createdFrom` | ISO 8601 timestamp | Ngày không tồn tại, timezone mơ hồ | Parse strict, quy tắc timezone |

### 14.1. Không để ép kiểu tạo giá trị bất ngờ

Trong JavaScript:

```javascript
function parseLimit(raw) {
  if (raw === undefined) return 20;

  if (typeof raw !== "string" || !/^[0-9]+$/.test(raw)) {
    throw new Error("limit must be a decimal integer");
  }

  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1 || value > 100) {
    throw new Error("limit out of range");
  }
  return value;
}
```

Với HTTP query string parser, cần xác định hành vi khi client gửi **nhiều tham số cùng tên**, chẳng hạn `limit=20&limit=1000`. Một framework có thể trả string, array hoặc giá trị cuối; API nên quy định rõ và **từ chối cấu trúc không mong đợi**.

### 14.2. Timezone và khoảng ngày

Nếu lọc “tất cả đơn trong tháng 11 theo giờ Việt Nam”, đừng tự áp UTC midnight vào chuỗi ngày địa phương mà không chuyển đổi. Hãy xác định timezone nghiệp vụ rồi tính ranh giới:

\[
\text{createdAt} \ge \text{start}
\quad \land \quad
\text{createdAt} < \text{nextStart}
\]

Khoảng nửa mở giúp tránh phụ thuộc vào độ phân giải mili giây/cuối ngày. Mọi hệ đọc và lưu phải thống nhất loại timestamp và đơn vị.

### 14.3. Chuẩn hóa string phải có lý do

Trim, lowercase, Unicode normalization, collation và so sánh không phân biệt dấu/chữ hoa có thể thay đổi nghĩa tìm kiếm. Với **mã định danh**, nên dùng quy tắc chuẩn hóa ID rõ ràng; với **tên người**, không nên tự gộp những chuỗi khác nhau nếu nghiệp vụ yêu cầu chính xác.

**Validation là kiểm tra ý nghĩa của giá trị, không chỉ việc nó có thể parse thành một giá trị nào đó.**

## 15. API contract: giới hạn bề mặt truy vấn mà client được thấy

Hai phong cách API:

### API theo tác vụ nghiệp vụ

```http
GET /api/orders/{orderId}
GET /api/customers/{customerId}/orders?status=PAID&cursor=...&limit=20
GET /api/orders/summary?month=2026-11
```

Đường API rõ ràng giúp backend chủ động chọn key/index/query shape và chính sách quyền. Đây thường là lựa chọn dễ kiểm soát cho sản phẩm.

### Generic query API

```http
POST /api/query
Content-Type: application/json

{
  "collection": "orders",
  "where": { "...": "..." },
  "sort": { "...": "..." }
}
```

Generic query API có thể hữu ích trong hệ admin/internal analytics được bảo vệ chặt, nhưng **bề mặt tấn công lớn hơn**. Nó cần một ngôn ngữ hạn chế, parser/validator riêng, xác thực quyền từng tập dữ liệu/field, giới hạn chi phí và kiểm soát truy cập ở datastore. Không nên mở một query proxy đầy đủ tới database từ ứng dụng dành cho người dùng thông thường.

### Chọn response projection an toàn

Truy vấn trả cả document rồi lọc field ở frontend là rủi ro lộ thông tin. Hãy chọn field được phép trả tại server:

```javascript
db.orders.find(
  { tenantId: "T01", status: "PAID" },
  {
    _id: 1,
    status: 1,
    totalVnd: 1,
    createdAt: 1
  }
);
```

Projection chỉ hạn chế những field được lấy ra hoặc trả về theo API query; **quyền truy cập phải được bảo vệ ở tầng phù hợp**, và nên hạn chế quyền tài khoản kết nối database nếu có thể.

## 16. Authorization: parameterization không phải phân quyền

Giả sử query đã parameterize:

```cypher
MATCH (o:Order {orderId: $orderId})
RETURN o;
```

Đây là query **an toàn hơn về cấu trúc**, nhưng người dùng T01 vẫn có thể gửi `orderId` thuộc T02 và được trả về nếu ứng dụng không kiểm tra quyền. Đây là một dạng **broken object-level authorization (BOLA/IDOR)**, khác với injection.

Một quy tắc cần bảo vệ:

```text
allowRead(user, order) =
    user.isAuthenticated
    AND order.tenantId == user.tenantId
    AND authorization.canReadOrder(user, order)
```

### 16.1. Áp điều kiện quyền trong đường truy vấn

Ví dụ MongoDB:

```javascript
const order = await orders.findOne({
  _id: validatedOrderId,
  tenantId: authenticatedPrincipal.tenantId
});
```

Nếu quyền còn phụ thuộc chủ sở hữu hoặc vai trò, thêm điều kiện hoặc kiểm tra tương đương ở nơi có thẩm quyền. Trong các hệ có read model trễ, **metadata quyền có thể chưa cập nhật**; cần thiết kế cách xác minh quyền hiện hành trước khi trả dữ liệu nhạy cảm.

### 16.2. Không để OR làm rơi điều kiện tenant

Sai về quyền:

```javascript
// Nhánh thứ hai không bị giới hạn tenant.
{
  $or: [
    { tenantId: "T01", status: "PAID" },
    { status: "PENDING" }
  ]
}
```

Đúng về ý tưởng:

```javascript
{
  tenantId: "T01",
  $or: [
    { status: "PAID" },
    { status: "PENDING" }
  ]
}
```

Ví dụ dùng tenant T01 cố định để minh họa; implementation phải lấy từ principal. Điều kiện tenant phải được thực thi ở **mọi nhánh** của query, kể cả khi người dùng chọn filter, sort, aggregation hoặc search mode.

### 16.3. Defense in depth

Ngoài query builder:

- Tài khoản database có quyền tối thiểu.
- Phân tách database/collection/index/namespace khi yêu cầu cách ly cao.
- Hạn chế network access và secret của client.
- Kiểm tra quyền tại mọi đường đọc, bao gồm lookup trực tiếp theo ID.
- Không tiết lộ sự tồn tại của ID thuộc tenant khác thông qua thông báo lỗi quá chi tiết.
- Kiểm soát cache, search index và export path.

**Không có một bộ lọc `tenantId` duy nhất có thể thay thế toàn bộ mô hình authorization.**

## 17. Điều kiện an toàn cho thao tác ghi

Query input không chỉ ảnh hưởng `find`, mà còn `update`, `delete` và `upsert`.

### 17.1. Update phải dùng filter nhận diện và điều kiện nghiệp vụ

Nguy hiểm:

```javascript
// KHÔNG AN TOÀN: user cung cấp filter và update bất kỳ.
await orders.updateMany(request.body.filter, request.body.update);
```

Một endpoint sửa trạng thái đơn có thể xác định:

```javascript
const result = await orders.updateOne(
  {
    _id: validatedOrderId,
    tenantId: authenticatedPrincipal.tenantId,
    status: "PENDING",
    version: expectedVersion
  },
  {
    $set: {
      status: "PAID",
      paidAt: new Date()
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount !== 1) {
  // Không tìm thấy, không đủ quyền, trạng thái khác hoặc version xung đột.
  // Chọn response theo hợp đồng API, không suy diễn đã cập nhật thành công.
}
```

Tuy nhiên, ví dụ chỉ minh họa **ghi nguyên tử một document**. Việc chốt thanh toán thực tế còn cần xác thực giao dịch, chống xử lý trùng và phối hợp với các hệ khác; không được cho phép client tự gọi endpoint để gán `PAID` nếu chưa có nghiệp vụ thanh toán hợp lệ.

### 17.2. Chống mass assignment

Nếu API nhận cả object rồi chạy `$set: request.body`, client có thể gửi những trường không được sửa như `tenantId`, `role`, `paidAt`, `adminOnly` hoặc `balance`.

Chỉ ánh xạ **các field được phép thay**:

```javascript
const patch = {};

if (typeof request.body.shippingNote === "string") {
  patch.shippingNote = request.body.shippingNote;
}

// Không đưa tenantId/status/paidAt từ body vào $set.
await orders.updateOne(
  {
    _id: validatedOrderId,
    tenantId: authenticatedPrincipal.tenantId
  },
  { $set: patch }
);
```

Trong ứng dụng thật, cần xử lý patch rỗng, giới hạn chiều dài và việc phân biệt **missing/null/chuỗi rỗng** theo hợp đồng API.

### 17.3. Delete có điều kiện

`deleteMany({})` là một thao tác nguy hiểm nếu query builder có thể tạo filter rỗng từ input. API xóa đơn thường phải dùng định danh và trạng thái được phép, ví dụ:

```javascript
db.orders.deleteOne({
  _id: validatedOrderId,
  tenantId: trustedTenantId,
  status: "DRAFT",
  version: expectedVersion
});
```

Ví dụ dùng trạng thái `DRAFT` làm giả định cho chính sách xóa. Phải kiểm tra `deletedCount`; không tự động fallback thành `deleteMany({})` khi không tìm thấy record.

### 17.4. PUT/PATCH khác replace

Không nên nhầm cập nhật vài field với replace toàn document. Một body thiếu `shipping.city` có thể mang nghĩa “không thay đổi” trong PATCH nhưng có thể khiến field bị bỏ trong full replacement. Đây là vấn đề **ngữ nghĩa API** và tính đúng dữ liệu, không chỉ là an toàn injection.

## 18. Query cost: điều kiện đầu vào phải giới hạn tài nguyên

Một truy vấn hợp lệ về quyền có thể vẫn là **Denial of Service về tài nguyên** nếu client được chọn cấu trúc quá rộng.

### 18.1. Giới hạn pagination

Đặt `limit` tối đa, ví dụ 100. Với dữ liệu lớn, ưu tiên keyset/continuation token thay vì `skip` hoặc offset quá sâu.

```text
GET /api/orders?limit=20&cursor=<opaque-cursor>
```

Cursor nên gắn với filter, sort và phạm vi quyền. Nếu cursor có thể bị sửa để truy xuất tenant khác, cần xác thực/bảo vệ tính toàn vẹn hoặc lưu trạng thái cursor server-side. Không coi một chuỗi base64 đơn thuần là chữ ký bảo mật.

### 18.2. Giới hạn tập giá trị và độ rộng query

Với `$in`/OR, giới hạn số ID/nhánh; với aggregation, giới hạn phạm vi thời gian, số nhóm, dung lượng kết quả và quyền dùng từng thao tác. Đừng mở các chức năng tính toán nặng như script, traversal sâu hoặc phép join khổng lồ trên public endpoint.

### 18.3. Timeout và cancellation

Ở database/driver hỗ trợ, áp **operation timeout**, deadline của request, giới hạn kết nối và hủy truy vấn khi client đã rời. Phải chọn timeout theo SLA và đặc tính truy vấn; timeout không làm truy vấn thiếu index trở thành tối ưu.

### 18.4. Rate limit, quota và concurrency

Đặt giới hạn theo user/tenant/API key cho các query đắt. Một tenant liên tục chạy aggregation nặng không nên chiếm hết tài nguyên của tenant khác. Có thể dùng hàng đợi hoặc endpoint báo cáo bất đồng bộ cho phép tính tổng hợp quy mô lớn.

### 18.5. Index và đường truy cập đúng

- MongoDB: xem `explain("executionStats")` và compound index theo filter/sort.
- DynamoDB: chọn partition/sort key và GSI theo access pattern, không dựa vào FilterExpression để tiết kiệm số item đọc.
- Cassandra: thiết kế table theo partition key, không dùng `ALLOW FILTERING` như giải pháp mặc định.
- Neo4j: tìm node bắt đầu qua ID/index và giới hạn hop/fan-out.
- Redis: lookup theo key, tránh quét không gian key cho truy vấn thường xuyên.

**Input validation là lớp an toàn; query planning và index là lớp hiệu năng. Cần cả hai.**

## 19. Một mẫu endpoint an toàn từ HTTP tới MongoDB

Ví dụ Node.js minh họa toàn bộ đường đi. Giả định middleware trước đó đã xác thực request và cung cấp `req.auth.tenantId`; thông tin quyền được lấy từ server, không tự tin tưởng payload client.

```javascript
const ALLOWED_STATUS = new Set(["PENDING", "PAID", "CANCELLED"]);

function parseEnum(value, options, fallback) {
  if (value === undefined) return fallback;
  if (typeof value !== "string" || !options.has(value)) {
    throw new Error("Invalid enum value");
  }
  return value;
}

function parseIntInRange(value, min, max, fallback) {
  if (value === undefined) return fallback;
  if (typeof value !== "string" || !/^[0-9]+$/.test(value)) {
    throw new Error("Expected unsigned decimal integer");
  }
  const number = Number(value);
  if (!Number.isSafeInteger(number) || number < min || number > max) {
    throw new Error("Integer out of range");
  }
  return number;
}

async function listOrders(req, res) {
  const tenantId = req.auth.tenantId; // Trusted identity context.
  const status = parseEnum(req.query.status, ALLOWED_STATUS, "PAID");
  const minTotalVnd = parseIntInRange(
    req.query.minTotalVnd, 0, 1_000_000_000_000, 0
  );
  const limit = parseIntInRange(req.query.limit, 1, 100, 20);

  const SORT_OPTIONS = {
    newest: { createdAt: -1, _id: -1 },
    oldest: { createdAt: 1, _id: 1 }
  };
  const sortName = req.query.sort ?? "newest";
  if (typeof sortName !== "string"
      || !Object.prototype.hasOwnProperty.call(SORT_OPTIONS, sortName)) {
    throw new Error("Invalid sort");
  }

  const filter = {
    tenantId,
    status,
    totalVnd: { $gte: minTotalVnd }
  };

  const result = await req.app.locals.db.collection("orders")
    .find(filter, {
      projection: {
        _id: 1, status: 1, totalVnd: 1, createdAt: 1
      }
    })
    .sort(SORT_OPTIONS[sortName])
    .limit(limit)
    .maxTimeMS(2000)
    .toArray();

  res.json({ items: result });
}
```

**Ý nghĩa thiết kế:**

1. Bộ parser chỉ chấp nhận scalar string cho query parameters và kiểm tra khoảng.
2. Client không được gửi raw MQL operator/field name/sort object.
3. Tenant được lấy từ principal.
4. Projection giới hạn field đầu ra.
5. Sort chỉ được chọn từ hai cấu trúc cố định.
6. Limit và timeout được giới hạn.

Đây là **ví dụ giáo dục**, chưa phải một route hoàn chỉnh: cần mapping lỗi đầu vào thành HTTP 400, bảo vệ error responses, kiểm tra role/quyền theo đơn, connection management, pagination cursor, rate limiting, request cancellation và monitoring. Khi có các phiên bản thư viện khác nhau, các phương thức cấu hình timeout có thể khác và cần đối chiếu driver đang dùng.

### Điều kiện index tương ứng

Với truy vấn chủ yếu lọc `tenantId`, `status`, sau đó giới hạn khoảng `totalVnd` và sort `createdAt`, cần **đo bằng explain** để chọn index. Không có một compound index bảo đảm tối ưu cho mọi kết hợp filter/range/sort; thứ tự trường trong index có đánh đổi, đặc biệt khi có một điều kiện range.

Ví dụ hai hướng thiết kế để benchmark:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});

db.orders.createIndex({
  tenantId: 1,
  status: 1,
  totalVnd: 1
});
```

Một index nhấn mạnh thứ tự đọc mới nhất, index kia nhấn mạnh lọc khoảng tổng tiền. Có nên giữ cả hai hay không phụ thuộc truy vấn chủ đạo, dữ liệu thật, tần suất ghi và kết quả `explain`; đừng tạo index tràn lan chỉ từ ví dụ.

## 20. Logging và quan sát truy vấn mà không lộ dữ liệu

Khi bảo vệ một query API, cần biết **query shape nào đang được dùng và có gây tải không**, nhưng cũng phải tránh ghi thông tin nhạy cảm.

Một bản ghi quan sát có thể gồm:

```json
{
  "queryName": "ListOrdersByStatus",
  "requestId": "req-1234",
  "filterShape": "tenantId:eq,status:eq,totalVnd:gte",
  "sortMode": "newest",
  "limit": 20,
  "durationMs": 48,
  "resultCount": 12,
  "status": "OK"
}
```

Không nên mặc định log toàn bộ `Authorization` header, thông tin cá nhân, địa chỉ, nội dung tài liệu hoặc raw filter do người dùng gửi. Nếu cần phục vụ điều tra, dùng cơ chế log/audit được phân quyền và retention phù hợp.

### Những tín hiệu nên theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Query latency p50/p95/p99 theo tên endpoint | Độ trễ người dùng |
| Số request bị từ chối do invalid filter | Chất lượng input hoặc hành vi dò quét |
| Số request bị rate limit/timeout | Query cost vượt giới hạn |
| Số document/keys/index entries đọc so với trả | Mức độ hiệu quả của access path |
| Tỷ lệ collection scan / truy vấn nặng | Cơ hội tối ưu index hoặc giới hạn API |
| Số lần lỗi authorization | Phát hiện hành vi ngoài phạm vi |
| Tỷ lệ cursor/pagination lỗi | Hợp đồng cursor không nhất quán |
| Search/read-model lag | Kết quả đọc có thể chưa mới nhất |

Tránh dùng `userId`, `orderId`, query text dài làm **metric label** vì gây cardinality cao; ID chi tiết nên ở audit/log có quyền hạn thích hợp.

## 21. Kiểm thử an toàn query API

Một endpoint chỉ đúng trên “happy path” là chưa đủ. Nên có nhóm kiểm thử đầu vào và tính đúng truy vấn.

### 21.1. Kiểu dữ liệu và toán tử bất ngờ

Các trường hợp cần từ chối hoặc xử lý theo hợp đồng:

```json
{ "status": { "$ne": "PAID" } }
{ "status": ["PAID", "PENDING"] }
{ "limit": "-1" }
{ "limit": "99999999" }
{ "minTotalVnd": "NaN" }
{ "sort": { "$natural": 1 } }
```

Nếu status API được thiết kế nhận một string enum, object và array phải bị từ chối. Nếu muốn cho nhiều trạng thái, tạo một field `statuses` riêng có giới hạn phần tử và enum cho từng giá trị.

### 21.2. Đầu vào nguy hiểm về cấu trúc

Thử gửi raw MongoDB operators, field names nhạy cảm, nhiều nhánh OR, regex phức tạp, projection đọc trường nội bộ, sort chưa được hỗ trợ, graph depth quá lớn hoặc query string có cú pháp đặc biệt. Mục tiêu là bảo đảm **server không biến input đó thành operator/identifier/script tùy ý**.

### 21.3. Phân quyền tenant và object

Một user thuộc T01 cố đọc ID của T02:

```text
GET /api/orders/ORD-2001
authenticated tenant: T01
expected: không trả document T02
```

Kiểm tra không chỉ endpoint danh sách mà còn endpoint theo ID, export, thống kê, search, graph traversal, cache và các route hỗ trợ nội bộ.

### 21.4. Tình huống hiệu năng và dữ liệu lớn

- Trang cuối của kết quả có phân trang và cursor.
- Truy vấn có filter rất ít kết quả.
- Một partition cực lớn, một graph node có nhiều cạnh.
- Nhiều request đồng thời cùng chạy query nặng.
- Query kéo dài vượt timeout; client hủy giữa chừng.
- Index còn đang đồng bộ hoặc read model chậm sau ghi.

### 21.5. Update và delete

- PATCH gửi field bị cấm như `tenantId` hoặc `paidAt`.
- PATCH thiếu field so với gửi `null`/`""`.
- Ghi đồng thời với version cũ; đảm bảo conflict không ghi đè mới.
- Delete filter rỗng; không được rơi về xóa toàn collection.
- Retry request ghi; kiểm tra idempotency và trạng thái nghiệp vụ.

Những kiểm thử này kiểm tra cả **cú pháp an toàn, quyền, tính đúng dữ liệu và giới hạn tài nguyên**, không chỉ một dạng injection.

## 22. Bài tập thực hành

### Bài 1 — Phân loại phần được phép biến đổi

Xét query:

```javascript
{
  tenantId: "T01",
  status: "PAID",
  totalVnd: { $gte: 200000 }
}
```

Hãy phân loại: phần nào là tên trường, phần nào là toán tử, phần nào là giá trị; phần nào do server phải kiểm soát, và tenant ID nên đến từ đâu?

### Bài 2 — Chặn operator injection

Một endpoint dùng `find({status: req.body.status})`. Client gửi:

```json
{ "status": { "$ne": "PAID" } }
```

Giải thích vì sao đây không còn là lọc `status = PAID`. Viết validator chỉ cho phép `PENDING`, `PAID`, `CANCELLED` và từ chối mọi input không phải scalar string.

### Bài 3 — Thiết kế filter builder

API cho phép `status`, `minTotalVnd`, `city` và `sort`. Hãy thiết kế bảng allowlist, kiểu dữ liệu, giới hạn và ánh xạ field tương ứng trong MongoDB. Thêm điều kiện tenant cố định lấy từ principal.

### Bài 4 — Phân biệt key condition và filter

Trong DynamoDB, có 10.000 đơn của một khách trong một partition, chỉ 100 đơn `PAID`. Developer dùng `FilterExpression` để lọc status. Vì sao vẫn phải đọc nhiều item trước filter? Khi nào nên tạo GSI hoặc một bản dữ liệu theo status? Vì sao `Items=[]` không đủ kết luận hết trang?

### Bài 5 — Prepared statement trong CQL

Viết câu CQL tìm các đơn theo `tenant_id`, `customer_id` và một khoảng `created_at` bằng bind markers. Tại sao không được ghép tên bảng từ client dù dùng prepared statement cho giá trị?

### Bài 6 — Cypher và traversal

Cho graph `Customer -PLACED-> Order -HAS_LINE-> OrderLine`. Viết query Cypher tham số hóa để tìm những Order PAID của một Customer trong tenant hiện hành. Giải thích cách giới hạn hop nếu ứng dụng cho phép tìm quan hệ gián tiếp.

### Bài 7 — Regex và text search

Người dùng nhập dấu `.*` vào ô tìm tên sản phẩm. Nếu ứng dụng đưa thẳng vào `$regex`, ý nghĩa truy vấn thay đổi thế nào? Hãy đề xuất tìm literal text với validation và escape, hoặc chuyển sang text search phù hợp.

### Bài 8 — Kiểm thử endpoint theo ID

User T01 gửi `GET /api/orders/ORD-2001`, trong khi đơn thuộc T02. Truy vấn đã dùng parameterized ID nhưng không lọc tenant. Hãy xác định lỗ hổng và sửa cách truy cập.

### Bài 9 — Bảo vệ thao tác xóa

Một API nhận `filter` tùy ý và chạy `deleteMany(filter)`. Hãy đề xuất hợp đồng API xóa đơn nháp theo `orderId`, tenant, status và expectedVersion. Vì sao không được xóa toàn bộ nếu filter không khớp?

### Bài 10 — Ngân sách truy vấn

Thiết kế endpoint tìm kiếm sản phẩm cho phép lọc giá, danh mục và tên. Hãy quy định giới hạn page size, chuỗi tìm kiếm, số category, timeout, rate limit, sort options và xử lý khi client yêu cầu khoảng thời gian quá lớn.

## 23. Tổng kết

NoSQL có nhiều ngôn ngữ và API truy vấn: **MQL** cho document, **lệnh Redis** cho key–value, **DynamoDB expressions** cho key/item, **CQL** cho wide-column, **Cypher** cho graph và **JSON DSL** cho search. Chúng có cách biểu diễn điều kiện, sử dụng index, phân trang và ràng buộc truy vấn khác nhau.

Nguyên tắc chung để nhận đầu vào an toàn là:

1. **Tách query structure khỏi values**: cấu trúc do server định nghĩa, giá trị được validate rồi bind.
2. **Parameterization không thay thế authorization**: tenant, role và quyền từng object phải được thực thi ở mọi đường đọc/ghi.
3. **Allowlist field, toán tử và sort**: không cho client biến raw object, identifier, script hoặc graph pattern thành truy vấn tùy ý.
4. **Giới hạn tài nguyên**: pagination, độ dài input, số filter, số hop, timeout và rate limit.
5. **Thiết kế access pattern phù hợp datastore**: index, partition key, GSI, graph traversal hay index do ứng dụng quản lý.
6. **Bảo vệ cả write path**: update/delete có điều kiện, version guard, chống mass assignment và idempotency.
7. **Đo lường và kiểm thử**: thử dữ liệu không hợp lệ, tenant khác, query quá rộng và trạng thái đọc lỗi thời.

Một truy vấn **đúng cú pháp** chưa chắc **đúng nghiệp vụ**, **đủ quyền** hoặc **có chi phí chấp nhận được**. Thiết kế API an toàn nghĩa là giới hạn chính xác **người dùng được hỏi điều gì**, **database được thực hiện những thao tác nào** và **kết quả nào được phép rời khỏi hệ thống**.
