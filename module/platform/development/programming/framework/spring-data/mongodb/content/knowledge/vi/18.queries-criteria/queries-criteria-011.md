# Xây bộ lọc tùy chọn và kiểm soát trường do người dùng lựa chọn trong Query và Criteria

## 1. Vấn đề: một API tìm kiếm, nhiều tổ hợp điều kiện

Trong ứng dụng **Spring Data MongoDB**, nhu cầu tìm kiếm ít khi chỉ có một bộ điều kiện cố định. Màn hình đơn hàng có thể cho người dùng lựa chọn trạng thái, khách hàng, khoảng tiền, khoảng ngày tạo, nhãn, từ khóa, thứ tự sắp xếp và những cột muốn hiển thị. Các điều kiện được chọn ở mỗi request là khác nhau, nhưng API vẫn phải **đúng về logic, an toàn với đầu vào không tin cậy và chạy được với dữ liệu lớn**.

Ví dụ:

```text
GET /orders?status=PAID&minTotalCents=10000&from=2026-01-01T00:00:00Z
           &sortBy=createdAt&direction=desc&page=0&size=20
```

Request khác chỉ lọc theo khách hàng:

```text
GET /orders?customerId=C-01&page=0&size=20
```

Nếu viết một repository method cho mỗi tổ hợp, số method có thể tăng rất nhanh. `MongoTemplate` với `Query` và `Criteria` cho phép **xây truy vấn động có kiểm soát**, bằng cách chỉ đưa những điều kiện thực sự được cung cấp vào query.

Bài học thuộc chương **Query và Criteria** của module `SPRING_DATA_MONGODB` tập trung vào hai kỹ năng:

1. **Xây bộ lọc tùy chọn:** không nhầm tham số vắng mặt với `false`, `0` hoặc một chuỗi rỗng; kết hợp đúng các điều kiện `AND`, `OR`, range, array và tìm kiếm văn bản.
2. **Kiểm soát trường do người dùng lựa chọn:** chỉ cho phép tìm, sort hoặc project theo những trường đã được liệt kê; không ghép thẳng tên field, toán tử MongoDB hoặc câu truy vấn BSON do client gửi.

Ngoài việc đọc, ghi và ánh xạ document bằng `MongoTemplate`/repository, cách dựng query còn tác động tới **index, pagination, transaction, bảo mật nhiều tenant, integration test và khả năng chẩn đoán truy vấn chậm**.

## 2. Mô hình dữ liệu dùng trong bài

### 2.1. Document MongoDB mẫu

Sử dụng collection `orders` trong một database thử nghiệm, với quy ước số tiền theo **đơn vị nhỏ nhất (cents)** và thời điểm ở UTC:

```javascript
db.orders.insertMany([
  {
    _id: "O-101",
    tenant_id: "T-A",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(15500),
    buyer_name: "An",
    tags: ["vip", "online"],
    archived: false,
    created_at: ISODate("2026-01-05T10:00:00Z")
  },
  {
    _id: "O-102",
    tenant_id: "T-A",
    customer_id: "C-02",
    status: "NEW",
    total_cents: NumberLong(6500),
    buyer_name: "Lan Anh",
    tags: ["online"],
    archived: false,
    created_at: ISODate("2026-01-06T10:00:00Z")
  },
  {
    _id: "O-103",
    tenant_id: "T-A",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(21000),
    buyer_name: "ANNA",
    tags: ["vip", "retail"],
    archived: true,
    created_at: ISODate("2026-01-08T10:00:00Z")
  },
  {
    _id: "O-201",
    tenant_id: "T-B",
    customer_id: "C-01",
    status: "PAID",
    total_cents: NumberLong(99000),
    buyer_name: "An",
    tags: ["vip"],
    archived: false,
    created_at: ISODate("2026-01-09T10:00:00Z")
  }
]);
```

`O-201` cố ý thuộc tenant `T-B` và có cùng `customer_id = "C-01"` với đơn của tenant `T-A`. Việc này giúp kiểm tra một lỗi nghiêm trọng: **không được để điều kiện tùy chọn làm rơi điều kiện tenant bắt buộc**.

### 2.2. Entity và mapping theo property Java

Mỗi class Java trong bài được đặt trong file thích hợp. Ví dụ entity:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "orders")
public class Order {
    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("customer_id")
    private String customerId;

    private String status;

    @Field("total_cents")
    private long totalCents;

    @Field("buyer_name")
    private String buyerName;

    private List<String> tags;
    private boolean archived;

    @Field("created_at")
    private Instant createdAt;

    protected Order() {}

    public Order(String id, String tenantId, String customerId,
                 String status, long totalCents, String buyerName,
                 List<String> tags, boolean archived, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.status = status;
        this.totalCents = totalCents;
        this.buyerName = buyerName;
        this.tags = tags;
        this.archived = archived;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerId() { return customerId; }
    public String getStatus() { return status; }
    public long getTotalCents() { return totalCents; }
    public String getBuyerName() { return buyerName; }
    public List<String> getTags() { return tags; }
    public boolean isArchived() { return archived; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Trong code dùng `MongoTemplate.find(query, Order.class)`, các field `tenantId`, `customerId`, `totalCents`, `buyerName` và `createdAt` là **property Java**. Spring Data dựa vào `@Field` để tạo truy vấn trên BSON `tenant_id`, `customer_id`, `total_cents`, `buyer_name` và `created_at`.

Với raw `MongoCollection<Document>` hoặc `mongosh`, phải sử dụng **tên BSON thực tế**. Việc phân biệt hai lớp tên là quan trọng khi người dùng được chọn các cột sort hoặc filter.

## 3. Thiết kế hợp đồng tìm kiếm trước khi dựng Criteria

### 3.1. Request DTO gồm những điều kiện được phép

Một record chỉ chứa các tùy chọn mà sản phẩm hỗ trợ:

```java
import java.time.Instant;
import java.util.List;

public record OrderSearchRequest(
    String status,
    String customerId,
    Long minTotalCents,
    Long maxTotalCents,
    Instant createdFrom,
    Instant createdUntil,
    Boolean archived,
    String buyerNameContains,
    List<String> anyTags
) {}
```

Ý nghĩa của từng giá trị:

| Giá trị request | Ngữ nghĩa khi có giá trị | Khi không cung cấp |
|---|---|---|
| `status` | Bằng một trạng thái được cho phép | Không lọc theo status |
| `customerId` | Bằng mã khách hàng | Không lọc theo customer |
| `minTotalCents` | `totalCents >= min` | Không có cận dưới |
| `maxTotalCents` | `totalCents <= max` | Không có cận trên |
| `createdFrom` | `createdAt >= createdFrom` | Không có cận dưới ngày |
| `createdUntil` | `createdAt < createdUntil` | Không có cận trên ngày |
| `archived` | Bằng `true` **hoặc** `false` | Không lọc archived |
| `buyerNameContains` | Chứa chuỗi literal, không phân biệt case | Không tìm theo tên |
| `anyTags` | Mảng có **ít nhất một** tag được chọn | Không lọc theo tag |

**Điểm dễ sai:** vì `archived` là `Boolean` (wrapper) nên phân biệt được ba trạng thái: `true`, `false` và `null`. Nếu dùng primitive `boolean` trong request DTO, khi không cung cấp có thể bị đồng nhất với `false`. Tương tự, `Long minTotalCents = 0L` là **một điều kiện hợp lệ**, không phải “không có điều kiện”.

### 3.2. Có ba cấp độ kiểm soát input

1. **Đúng kiểu:** framework parse ngày, số, boolean; từ chối input không đúng định dạng.
2. **Đúng ngữ nghĩa:** số tiền không âm, `min <= max`, khoảng ngày hợp lệ, độ dài từ khóa hợp lý, số tag có giới hạn.
3. **Đúng quyền:** tenant lấy từ security context tin cậy, không lấy từ field người dùng tự nhập để tự xác định phạm vi dữ liệu.

Nếu API nhận `status` dưới dạng String, cần kiểm tra nó thuộc tập giá trị được phép (ví dụ `NEW`, `PAID`, `CANCELLED`) hoặc dùng enum có chính sách parse rõ ràng. Không biến các chuỗi tùy ý thành field MongoDB hay biến một cấu trúc JSON do client gửi thành đối tượng `Criteria`.

### 3.3. Phân biệt null, chuỗi rỗng, danh sách rỗng

```text
status = null              → bỏ qua điều kiện status
status = ""                → tùy hợp đồng: bỏ qua hoặc trả 400, KHÔNG mặc định equals ""
archived = false           → thêm điều kiện archived = false
minTotalCents = 0          → thêm total_cents >= 0
anyTags = null             → bỏ qua lọc tag
anyTags = []               → tùy hợp đồng: bỏ qua hoặc trả 400
anyTags = ["vip", "online"] → dùng $in nếu yêu cầu "bất kỳ tag nào"
```

Trong bài, chọn chính sách: **chuỗi rỗng sau trim và danh sách tag rỗng được xem là không có filter**; giá trị không rỗng nhưng sai định dạng sẽ bị từ chối. Sản phẩm khác có thể chọn trả HTTP 400 cho chuỗi rỗng để không vô tình chạy truy vấn quá rộng; cần công bố và kiểm thử chính sách đó.

## 4. Xây Criteria từng phần, không ghép chuỗi BSON

### 4.1. Mẫu thiết kế: tập các điều kiện AND

Ví dụ sau tạo một `Query` bất biến về *ý định logic*: mỗi filter hợp lệ thêm một `Criteria` vào danh sách. Điều kiện tenant **luôn xuất hiện**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class OrderCriteriaBuilder {
    private static final Set<String> ALLOWED_STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    private OrderCriteriaBuilder() {}

    public static Query build(
            OrderSearchRequest input, String trustedTenantId) {

        if (input == null
                || trustedTenantId == null
                || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException("Missing search context");
        }

        validate(input);

        List<Criteria> andParts = new ArrayList<>();
        andParts.add(
            Criteria.where("tenantId").is(trustedTenantId));

        if (hasText(input.status())) {
            andParts.add(Criteria.where("status")
                .is(input.status().trim()));
        }
        if (hasText(input.customerId())) {
            andParts.add(Criteria.where("customerId")
                .is(input.customerId().trim()));
        }
        if (input.minTotalCents() != null) {
            andParts.add(Criteria.where("totalCents")
                .gte(input.minTotalCents()));
        }
        if (input.maxTotalCents() != null) {
            andParts.add(Criteria.where("totalCents")
                .lte(input.maxTotalCents()));
        }
        if (input.createdFrom() != null) {
            andParts.add(Criteria.where("createdAt")
                .gte(input.createdFrom()));
        }
        if (input.createdUntil() != null) {
            andParts.add(Criteria.where("createdAt")
                .lt(input.createdUntil()));
        }
        if (input.archived() != null) {
            andParts.add(Criteria.where("archived")
                .is(input.archived()));
        }
        if (hasText(input.buyerNameContains())) {
            Pattern literal = Pattern.compile(
                Pattern.quote(input.buyerNameContains().trim()),
                Pattern.CASE_INSENSITIVE);
            andParts.add(Criteria.where("buyerName").regex(literal));
        }
        if (input.anyTags() != null && !input.anyTags().isEmpty()) {
            andParts.add(Criteria.where("tags")
                .in(input.anyTags()));
        }

        Criteria combined = new Criteria().andOperator(
            andParts.toArray(new Criteria[0]));
        return Query.query(combined);
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private static void validate(OrderSearchRequest input) {
        if (hasText(input.status())
                && !ALLOWED_STATUSES.contains(input.status().trim())) {
            throw new IllegalArgumentException("Invalid status");
        }
        if (input.customerId() != null
                && input.customerId().length() > 80) {
            throw new IllegalArgumentException("Customer ID too long");
        }
        if (input.buyerNameContains() != null
                && input.buyerNameContains().length() > 80) {
            throw new IllegalArgumentException("Search text too long");
        }
        if ((input.minTotalCents() != null
                && input.minTotalCents() < 0)
                || (input.maxTotalCents() != null
                && input.maxTotalCents() < 0)) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (input.minTotalCents() != null
                && input.maxTotalCents() != null
                && input.minTotalCents() > input.maxTotalCents()) {
            throw new IllegalArgumentException("Invalid amount range");
        }
        if (input.createdFrom() != null
                && input.createdUntil() != null
                && !input.createdFrom().isBefore(input.createdUntil())) {
            throw new IllegalArgumentException("Invalid time range");
        }
        if (input.anyTags() != null) {
            if (input.anyTags().size() > 20
                    || input.anyTags().stream().anyMatch(
                        tag -> tag == null || tag.isBlank()
                            || tag.length() > 40)) {
                throw new IllegalArgumentException("Invalid tags");
            }
        }
    }
}
```

Đây là một ví dụ **logic dựng bộ lọc**, chưa phải toàn bộ controller, validation framework hay chính sách authorization. `trustedTenantId` phải do ứng dụng lấy từ nguồn đã xác thực; không bind trực tiếp từ query parameter. Hàm `validate` minh họa các ràng buộc; production cần thêm quy tắc theo nghiệp vụ và endpoint.

Trong câu query cuối, mọi điều kiện đều kết hợp bằng `$and`, bao gồm điều kiện tenant. Không có chuyện một filter `OR` do client thêm vào tự ý vượt ra ngoài phạm vi tenant.

### 4.2. Tại sao dùng List<Criteria> thay vì thêm nhiều điều kiện cùng key?

Giả sử người dùng nhập cả cận dưới và cận trên. Cách diễn đạt logic là:

```javascript
{
  $and: [
    { tenant_id: "T-A" },
    { total_cents: { $gte: NumberLong(10000) } },
    { total_cents: { $lte: NumberLong(20000) } }
  ]
}
```

MongoDB cũng hỗ trợ gộp các toán tử trên cùng một key:

```javascript
{
  tenant_id: "T-A",
  total_cents: {
    $gte: NumberLong(10000),
    $lte: NumberLong(20000)
  }
}
```

Hai hình thức tương đương về ngữ nghĩa trong tình huống này. Nhưng **không nên gọi `Query.addCriteria(...)` hai lần trên cùng key** nếu cách ghép tạo xung đột cấu trúc query, vì Spring Data có thể báo lỗi khi thêm điều kiện cùng khóa BSON. `List<Criteria>` và `andOperator(...)` là một cách đơn giản để lắp các filter độc lập, kể cả khi nhiều điều kiện dùng chung property.

Nếu đã biết chắc các điều kiện của một property, bạn cũng có thể tạo một `Criteria.where("totalCents").gte(min).lte(max)` khi cả hai cận tồn tại. Không có một lựa chọn luôn tối ưu; cần ưu tiên tính dễ kiểm tra của logic và query BSON cuối.

### 4.3. Ví dụ thực thi với MongoTemplate

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {
    private final MongoTemplate template;

    public OrderSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> search(
            OrderSearchRequest request, String trustedTenantId) {
        Query query = OrderCriteriaBuilder.build(
            request, trustedTenantId);
        return template.find(query, Order.class);
    }
}
```

Đây là ví dụ ngắn để minh họa cách đưa `Query` vào `MongoTemplate`. Ở API public, phải thêm **limit, sort và pagination** ở mục sau; không nên cho request tùy ý trả toàn bộ collection.

### 4.4. Đọc đúng ý nghĩa của truy vấn đã được ánh xạ

Với `status = "PAID"`, `minTotalCents = 10000`, `archived = false`, tenant tin cậy `T-A`, query tương đương:

```javascript
db.orders.find({
  $and: [
    { tenant_id: "T-A" },
    { status: "PAID" },
    { total_cents: { $gte: NumberLong(10000) } },
    { archived: false }
  ]
});
// Chỉ trả O-101 trong bộ dữ liệu mẫu.
```

`O-103` có `archived: true` nên bị loại; `O-201` thuộc tenant `T-B` nên bị loại bất kể có `status: "PAID"` và tổng tiền cao hơn.

**Lưu ý về `Query.getQueryObject()`:** đối tượng query được dựng bằng property Java; khi được ánh xạ theo `Order.class` để thực thi, tên field có thể đổi theo `@Field`. Đừng nhìn `query.getQueryObject().toJson()` rồi kết luận đó luôn là BSON cuối cùng mà driver gửi, nhất là khi có mapping/ID converters đặc biệt.

## 5. Kiểm soát field do người dùng lựa chọn

Một số UI muốn cho người dùng chọn: “lọc theo **mã khách hàng**, **trạng thái** hoặc **đã lưu trữ**”. Đây là tình huống khác với request DTO có các property định trước, bởi **tên field là một giá trị input**.

Không viết:

```java
// Anti-pattern: đường dẫn field đến từ request mà chưa kiểm soát.
String field = request.getParameter("field");
String value = request.getParameter("value");
Query query = Query.query(Criteria.where(field).is(value));
```

Một client có thể chọn field nội bộ, đường dẫn nested không được phép hoặc những tên bắt đầu bằng ký hiệu đặc biệt. Ngay cả khi giá trị được bind an toàn, **field path vẫn quyết định ý nghĩa query**. Cần dùng allowlist: chỉ cho phép danh sách tên public đã định nghĩa trong server, rồi chuyển chúng thành **property Java cố định**.

### 5.1. Mô hình lựa chọn field có kiểu

```java
public record SelectedFieldFilter(
    String field,   // "customer", "status", "archived"
    String value
) {}
```

Tạo mapper từ tên public sang tiêu chí **đúng kiểu**, không ghép bất kỳ field path từ client:

```java
import java.util.Set;
import org.springframework.data.mongodb.core.query.Criteria;

public final class SelectedFieldCriteria {
    private static final Set<String> STATUSES =
        Set.of("NEW", "PAID", "CANCELLED");

    private SelectedFieldCriteria() {}

    public static Criteria create(SelectedFieldFilter filter) {
        if (filter == null) {
            return null;
        }
        if (filter.field() == null || filter.value() == null) {
            throw new IllegalArgumentException("Missing filter field/value");
        }

        String value = filter.value().trim();
        return switch (filter.field()) {
            case "customer" -> {
                if (value.isEmpty() || value.length() > 80) {
                    throw new IllegalArgumentException("Invalid customer");
                }
                yield Criteria.where("customerId").is(value);
            }
            case "status" -> {
                if (!STATUSES.contains(value)) {
                    throw new IllegalArgumentException("Invalid status");
                }
                yield Criteria.where("status").is(value);
            }
            case "archived" -> {
                if (!value.equals("true") && !value.equals("false")) {
                    throw new IllegalArgumentException("Invalid boolean");
                }
                yield Criteria.where("archived")
                    .is(Boolean.parseBoolean(value));
            }
            default -> throw new IllegalArgumentException(
                "Field is not allowed");
        };
    }
}
```

Ở đây public field `"customer"` được đổi thành property Java `customerId`; Spring Data sau đó ánh xạ sang BSON `customer_id` khi query với `Order.class`. Các field như `tenantId` và `internalNote` **không được phép lọc tùy ý** chỉ vì chúng có mặt trong entity.

### 5.2. Ghép filter đã chọn vào query cơ sở

```java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query base = OrderCriteriaBuilder.build(
    input, authenticatedTenantId);

Criteria selected = SelectedFieldCriteria.create(selectedField);
if (selected != null) {
    base.addCriteria(selected);
}

List<Order> results = mongoTemplate.find(base, Order.class);
```

Ví dụ trên có hai tiền đề:

1. `input`, `authenticatedTenantId` và `selectedField` đã được cung cấp/kiểm soát ở tầng service; không dùng một giá trị tenant do request tự gắn.
2. `OrderCriteriaBuilder.build(...)` dùng top-level `$and`; criteria được thêm tiếp có **key cấp cao khác `$and`**, nên tất cả điều kiện vẫn được kết hợp theo phép AND. Nếu thay đổi cách dựng query, phải xem lại việc thêm các điều kiện vào cùng key.

Với **nhiều bộ lọc do người dùng chọn**, tốt hơn là lắp toàn bộ chúng vào **một danh sách `Criteria` duy nhất ngay từ đầu** thay vì thêm tùy ý vào một `Query` đã hoàn thành. Cần giới hạn số filter, từ chối lặp field trái phép và quy định khi hai điều kiện trên cùng một field mâu thuẫn nhau.

### 5.3. Vì sao không cho người dùng gửi toán tử MongoDB?

Một API không nên nhận raw object:

```json
{
  "field": "status",
  "operator": "$ne",
  "value": "CANCELLED"
}
```

rồi ghép trực tiếp thành BSON query mà không kiểm tra. Người dùng có thể đưa toán tử ngoài phạm vi chức năng hoặc gây truy vấn rất rộng. Nếu sản phẩm thật sự yêu cầu chọn toán tử, hãy định nghĩa một tập toán tử nghiệp vụ riêng như `EQ`, `GTE`, `LTE`, `IN`, mỗi field chỉ hỗ trợ những toán tử phù hợp kiểu dữ liệu.

| Public field | Đường dẫn property được phép | Toán tử có thể cho phép | Kiểu giá trị |
|---|---|---|---|
| `customer` | `customerId` | `EQ` | String không rỗng |
| `status` | `status` | `EQ`, `IN` có giới hạn | Enum trạng thái |
| `archived` | `archived` | `EQ` | Boolean |
| `total` | `totalCents` | `GTE`, `LTE`, `BETWEEN` | Long không âm |
| `created` | `createdAt` | `FROM`, `UNTIL` | Instant |
| `buyerName` | `buyerName` | `CONTAINS_LITERAL` | String đã giới hạn chiều dài |

Không biến toán tử API thành chuỗi `"$" + input`. Ánh xạ từng tổ hợp field/operator bằng `switch` hoặc một **bảng chiến lược được khai báo trong code**. Các tổ hợp không hỗ trợ phải bị từ chối rõ ràng, không âm thầm bỏ qua rồi chạy query rộng hơn.

### 5.4. Không đủ nếu chỉ chặn các ký tự nguy hiểm

Một validator tên field kiểu “không được chứa dấu `$` hay dấu `.`” không giải quyết bài toán. Tên `internalNotes` không có ký tự đặc biệt nhưng vẫn có thể là field nhạy cảm; tên `shipment.address.city` có dấu chấm nhưng có thể hợp lệ nếu sản phẩm đã cho phép một nested property cụ thể.

**Allowlist theo ý nghĩa nghiệp vụ** là cách đáng tin cậy hơn kiểm tra ký tự:

```text
Client field key: "customer"
    ↓
Allowlist của server
    ↓
Java property: customerId
    ↓
Spring mapping (@Field)
    ↓
BSON field: customer_id
```

Nếu có nested property, hãy khai báo chính xác một khóa public cố định, ví dụ `"shippingCity" -> "shippingAddress.city"`, sau khi kiểm tra entity thực tế có đường dẫn đó. Không cho client tự nối `shippingAddress.` với một property tùy ý.

## 6. Kết hợp điều kiện AND/OR mà không bỏ qua tenant

### 6.1. OR đúng phạm vi truy cập

Nhu cầu: tìm các đơn **thuộc tenant T-A**, đồng thời status là `NEW` **hoặc** `PAID`. Cấu trúc đúng là:

```javascript
{
  $and: [
    { tenant_id: "T-A" },
    {
      $or: [
        { status: "NEW" },
        { status: "PAID" }
      ]
    }
  ]
}
```

Spring Data Criteria:

```java
Criteria visibleToTenant =
    Criteria.where("tenantId").is(authenticatedTenantId);

Criteria allowedStatuses = new Criteria().orOperator(
    Criteria.where("status").is("NEW"),
    Criteria.where("status").is("PAID")
);

Query q = Query.query(
    new Criteria().andOperator(
        visibleToTenant, allowedStatuses));

List<Order> matches = mongoTemplate.find(q, Order.class);
```

Đối với tenant `T-A` trong dữ liệu mẫu, điều kiện này có thể trả `O-101`, `O-102`, `O-103` (tùy các bộ lọc bổ sung). `O-201` của tenant `T-B` không được phép xuất hiện.

### 6.2. Sai lầm: tenant chỉ nằm trong một nhánh OR

```javascript
// Anti-pattern nếu mục tiêu là giới hạn mọi kết quả trong T-A:
{
  $or: [
    { tenant_id: "T-A", status: "PAID" },
    { status: "NEW" }
  ]
}
```

Nhánh thứ hai không có điều kiện tenant và có thể trả đơn `NEW` của bất kỳ tenant nào. Quy tắc an toàn: **đặt điều kiện bắt buộc ở ngoài phần OR tùy chọn**, hoặc lặp nó đúng trong mọi nhánh nếu có lý do đặc biệt và đã kiểm chứng.

### 6.3. OR từ danh sách trạng thái có thể đơn giản hóa thành IN

Nếu nhiều giá trị đều so sánh equality trên cùng property:

```java
Criteria.where("status").in(List.of("NEW", "PAID"))
```

thường gọn hơn:

```java
new Criteria().orOperator(
    Criteria.where("status").is("NEW"),
    Criteria.where("status").is("PAID"))
```

Khi cho phép nhiều trạng thái qua API, xác minh từng giá trị thuộc enum/tập trạng thái được phép và giới hạn độ dài danh sách. Với danh sách rỗng, cần quy định rõ “không lọc” hay “không có kết quả”; hai cách diễn giải khác nhau và không nên phụ thuộc ngẫu nhiên vào `$in: []`.

### 6.4. AND/OR với các điều kiện tùy chọn

Để biểu diễn:

> Tenant T-A, số tiền ít nhất 10.000 cents, và (status = PAID **hoặc** status = NEW).

Có thể tạo:

```java
List<Criteria> all = new ArrayList<>();
all.add(Criteria.where("tenantId").is(authenticatedTenantId));
all.add(Criteria.where("totalCents").gte(10_000L));
all.add(new Criteria().orOperator(
    Criteria.where("status").is("PAID"),
    Criteria.where("status").is("NEW")
));

Query query = Query.query(
    new Criteria().andOperator(
        all.toArray(new Criteria[0])));
```

Với **bộ lọc tùy chọn**, chỉ thêm `orOperator(...)` khi có ít nhất một nhánh hợp lệ. Không tạo một nhóm OR rỗng rồi kỳ vọng Spring Data và MongoDB tự hiểu đó là “không lọc”. Nên có helper tạo danh sách nhánh, validate và tránh duplicate.

## 7. Range, thời gian và danh sách: quyết định chính xác ngữ nghĩa

### 7.1. Giá trị 0, cận bao gồm và cận loại trừ

Đối với `totalCents`:

```java
Criteria.where("totalCents").gte(0L);
Criteria.where("totalCents").lte(10_000L);
```

`gte` và `lte` đều bao gồm biên. Nếu muốn `[0, 10000)`, dùng `gte(0).lt(10000)`. Không chuyển sang `double` chỉ để so sánh số nguyên cents; xác nhận kiểu BSON và business unit thống nhất.

Với khoảng thời gian, mô hình **nửa mở** thường rõ ràng hơn:

```text
createdFrom  = 2026-01-01T00:00:00Z (bao gồm)
createdUntil = 2026-02-01T00:00:00Z (loại trừ)

2026-01-31T23:59:59.999Z → thuộc khoảng
2026-02-01T00:00:00Z     → không thuộc khoảng
```

Không cần tạo giá trị “23:59:59.999999...” cho cuối ngày. Tuy nhiên, khi user chọn ngày theo múi giờ của họ, controller phải chuyển **đầu ngày theo múi giờ được quy định** thành `Instant` UTC phù hợp. Không âm thầm giả định múi giờ hệ điều hành hoặc mặc định mọi request ở UTC nếu sản phẩm dùng ngày địa phương.

### 7.2. Tìm array: any và all là hai yêu cầu khác nhau

Với `tags: ["vip", "online"]`:

```java
// Có ít nhất một tag được chọn.
Criteria.where("tags").in(List.of("vip", "retail"));

// Phải có tất cả tag được chọn.
Criteria.where("tags").all(List.of("vip", "retail"));
```

Ở dữ liệu mẫu, điều kiện any có thể khớp `O-101` và `O-103` trong tenant `T-A`, còn điều kiện all trên hai tag này chỉ khớp `O-103`. Đây không phải khác biệt về cú pháp nhỏ: nó là khác biệt nghiệp vụ cần thể hiện rõ trong API.

Nếu tìm theo document trong một array object, `Criteria.elemMatch(...)` hữu ích khi cần nhiều điều kiện trên **cùng một phần tử array**. Không dùng hai đường dẫn dot notation rời rạc rồi giả định MongoDB luôn ràng buộc chúng vào một phần tử duy nhất.

### 7.3. Missing, null và false

```javascript
{ archived: false }                 // Tìm giá trị false
{ archived: { $exists: false } }    // Tìm document thiếu field
{ archived: null }                  // Có thể khớp null hoặc thiếu field
```

Ba điều kiện không tương đương. Nếu dữ liệu legacy có document thiếu `archived` nhưng business rule coi chúng là “chưa lưu trữ”, phải xác định cách xử lý schema/migration hoặc điều kiện query có chủ đích. Một `Boolean archived` trong request chỉ điều khiển việc có thêm filter; nó không tự giải quyết sự khác nhau giữa BSON null và missing.

Nếu business yêu cầu phân biệt đủ ba trạng thái `false`, `true` và missing, nên thiết kế riêng một enum trạng thái lọc thay vì overload ý nghĩa của `Boolean null` ở request.

## 8. Tìm chuỗi literal và giới hạn regex

Tìm `buyerName` chứa từ khóa có thể dùng `Criteria.where("buyerName").regex(...)`, nhưng cần phân biệt **chuỗi literal** và **regex do người dùng tự viết**.

### 8.1. Pattern.quote bảo vệ ý nghĩa literal

```java
String keyword = "A.B";
Pattern safe = Pattern.compile(
    Pattern.quote(keyword),
    Pattern.CASE_INSENSITIVE
);

Criteria byBuyerName = Criteria.where("buyerName")
    .regex(safe);
```

`Pattern.quote("A.B")` làm dấu chấm được hiểu như ký tự `.` thật, không trở thành wildcard regex. Trái lại:

```java
// Không dùng khi input đến từ ô tìm kiếm literal thông thường:
Pattern unsafe = Pattern.compile(userText);
```

Nếu `userText = ".*"`, một regex như vậy có thể khớp hầu hết các chuỗi và khiến truy vấn cực rộng. Trong ví dụ builder ở mục 4, `buyerNameContains` được giới hạn 80 ký tự và luôn đi qua `Pattern.quote(...)`.

**Không đánh đồng regex injection với BSON operator injection:** `Pattern.quote` bảo đảm tham số được dùng như literal bên trong regex; allowlist field/operator đảm bảo query chỉ dùng những thuộc tính và toán tử đã cho phép. Cả hai lớp bảo vệ đều cần thiết ở các API có input linh hoạt.

### 8.2. Tác động của regex tới index

MongoDB có thể tận dụng index B-tree trong một số trường hợp regex **case-sensitive, có prefix literal và anchor đầu chuỗi**, ví dụ `/^An/`. Regex chứa chuỗi ở bất kỳ vị trí nào, hoặc có `i` để ignore case, thường khó tận dụng hiệu quả index kiểu này. Một index case-insensitive dựa trên collation không tự động làm `$regex` case-insensitive trở nên index-friendly.

Nếu sản phẩm cần autocomplete quy mô lớn, xem xét:

- Prefix search trên field canonical đã chuẩn hóa, có index phù hợp.
- Giới hạn độ dài input, debounce, số request đồng thời và kích thước trang.
- Tách **tên hiển thị gốc** khỏi **khóa tìm kiếm chuẩn hóa** nếu yêu cầu bỏ case/dấu.
- MongoDB Search/Atlas Search hoặc hệ thống tìm kiếm phù hợp nếu cần full-text, fuzzy search, tokenization, wildcard phức tạp.

Không tăng `maxPoolSize` một cách máy móc khi query substring đang quét nhiều document; tối ưu cần tập trung vào kiểu tìm kiếm và index.

### 8.3. Không cho lựa chọn field regex tự do

Một API nhận `field = "buyerName"` và `value = "A.B"` vẫn phải qua allowlist:

```java
// Field duy nhất được hỗ trợ cho tìm literal trong ví dụ này:
if (!"buyerName".equals(publicField)) {
    throw new IllegalArgumentException("Not searchable as text");
}
Criteria safeText = Criteria.where("buyerName").regex(
    Pattern.compile(Pattern.quote(text),
        Pattern.CASE_INSENSITIVE));
```

Không nên cho người dùng chọn một field bất kỳ trong entity rồi gửi `$regex` lên trường đó: kiểu BSON có thể không phải String, dữ liệu có thể nhạy cảm và hiệu năng trên mỗi field khác nhau.

## 9. Sort, phân trang và giới hạn kết quả theo field được phép

Tương tự việc lọc, giá trị `sortBy` và `direction` từ client không được đưa trực tiếp vào truy vấn nếu chưa kiểm tra. Một số property có thể mang thông tin nội bộ, không có index hoặc không được định nghĩa để sắp xếp.

### 9.1. Allowlists riêng cho sort

```java
import java.util.Locale;
import java.util.Map;
import org.springframework.data.domain.Sort;

public final class SafeOrderSort {
    private static final Map<String, String> SORT_FIELDS = Map.of(
        "createdAt", "createdAt",
        "total", "totalCents",
        "customer", "customerId"
    );

    private SafeOrderSort() {}

    public static Sort fromRequest(String publicField, String direction) {
        String requested = (publicField == null || publicField.isBlank())
            ? "createdAt" : publicField;
        String property = SORT_FIELDS.get(requested);
        if (property == null) {
            throw new IllegalArgumentException("Sort field is not allowed");
        }

        String order = (direction == null || direction.isBlank())
            ? "desc" : direction.toLowerCase(Locale.ROOT);

        Sort.Direction sortDirection = switch (order) {
            case "asc" -> Sort.Direction.ASC;
            case "desc" -> Sort.Direction.DESC;
            default -> throw new IllegalArgumentException(
                "Sort direction must be asc or desc");
        };

        return Sort.by(sortDirection, property)
            .and(Sort.by(Sort.Direction.ASC, "id"));
    }
}
```

Public key `"total"` được ánh xạ sang Java `totalCents` rồi sang BSON `total_cents`. Public key `"customer"` tương tự trở thành `customer_id`. Tập sort được phép **độc lập** với tập filter: một field có thể phù hợp để lọc equality nhưng không phù hợp cho sort vì thiếu index hoặc cần bảo mật.

Thêm `id` làm tie-breaker giúp các document có cùng `createdAt` hoặc `totalCents` có thứ tự ổn định hơn khi phân trang. Tuy vậy, khi dữ liệu đang được ghi/xóa đồng thời, phân trang kiểu offset vẫn có thể trùng/bỏ sót item giữa các request; nếu cần consistency mạnh hoặc phân trang sâu, xem xét keyset/range pagination.

### 9.2. Pageable an toàn thay vì tùy ý skip/limit

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

public final class SafeOrderPage {
    private SafeOrderPage() {}

    public static Pageable fromRequest(
            int page, int size, String sortBy, String direction) {
        if (page < 0 || page > 1_000 || size < 1 || size > 100) {
            throw new IllegalArgumentException("Invalid page/size");
        }
        long offset = (long) page * size;
        if (offset > 10_000L) {
            throw new IllegalArgumentException("Offset is too large");
        }

        return PageRequest.of(page, size,
            SafeOrderSort.fromRequest(sortBy, direction));
    }
}
```

Các con số 100, 1.000 và 10.000 là **giới hạn ví dụ**, không phải default hay giới hạn MongoDB. Hãy đặt mức tối đa từ SLA, UX và benchmark hệ thống. Kiểm soát offset ở tầng API có thể tránh một số truy vấn bỏ qua quá nhiều kết quả; với dữ liệu rất lớn, cần chiến lược pagination khác.

### 9.3. Cùng một filter cho content và count

```java
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.core.query.Query;

public Page<Order> searchPaged(
        OrderSearchRequest request,
        String trustedTenantId,
        int pageIndex,
        int pageSize,
        String sortBy,
        String direction) {

    Pageable pageable = SafeOrderPage.fromRequest(
        pageIndex, pageSize, sortBy, direction);

    Query contentQuery =
        OrderCriteriaBuilder.build(request, trustedTenantId);
    contentQuery.with(pageable);

    List<Order> content =
        mongoTemplate.find(contentQuery, Order.class);

    // Tạo Query mới với cùng bộ lọc, nhưng không mang skip/limit.
    Query countQuery =
        OrderCriteriaBuilder.build(request, trustedTenantId);
    long total = mongoTemplate.count(countQuery, Order.class);

    return new PageImpl<>(content, pageable, total);
}
```

Đây là phương thức minh họa thuộc một service có `mongoTemplate` đã được inject. Không tính count trên query đã mang skip/limit rồi kỳ vọng luôn có tổng số bản ghi không phân trang. `Page` có tổng số phần tử nhưng thêm chi phí count, đôi khi đáng kể với filter phức tạp. Nếu UI chỉ cần biết còn trang kế tiếp, cân nhắc mô hình `Slice` với giới hạn hợp lý.

**Cực kỳ quan trọng:** count và content phải dùng **cùng điều kiện tenant và cùng bộ lọc**. Nếu bổ sung `SelectedFieldFilter` ở query lấy content nhưng quên thêm ở count, `totalElements` sẽ không phản ánh tập kết quả đang hiển thị. Với code production, nên gom logic tạo tập `Criteria` vào một factory duy nhất được dùng bởi cả hai đường.

### 9.4. Không lấy số dòng không giới hạn

```java
// Không thích hợp cho endpoint tìm kiếm tự do trên collection lớn:
List<Order> all = mongoTemplate.find(query, Order.class);
```

Một query không có `limit` có thể tạo lượng dữ liệu lớn qua mạng, tăng pressure lên heap/GC và MongoDB cursor. Đặt limit/page size ở tầng service, kèm rate limit nếu API public. Không dựa vào việc một UI hiện chỉ hiển thị 20 dòng để mặc định rằng server chỉ truy vấn 20 document.

## 10. Người dùng được chọn cột đầu ra: projection phải có allowlist

Một số UI cho phép chọn các cột:

```json
{
  "columns": ["orderId", "customer", "status", "total"]
}
```

Đó là nhu cầu **projection**, khác với chọn field để filter hoặc sort. Nếu client được gửi tên cột tùy ý vào `query.fields().include(...)`, API có thể vô tình phơi bày những field nội bộ như `internalNote`, `riskScore` hoặc `tenantId`, ngay cả khi chúng không được dự định xuất hiện trong response.

### 10.1. Xác định cột công khai và property Java

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.data.mongodb.core.query.Query;

public final class SafeOrderColumns {
    private static final Map<String, String> ALLOWED = Map.of(
        "orderId", "id",
        "customer", "customerId",
        "status", "status",
        "total", "totalCents",
        "created", "createdAt"
    );

    private static final List<String> DEFAULT =
        List.of("orderId", "customer", "status", "total");

    private SafeOrderColumns() {}

    public static List<String> normalize(List<String> requested) {
        List<String> source = (requested == null || requested.isEmpty())
            ? DEFAULT : requested;
        if (source.size() > ALLOWED.size()) {
            throw new IllegalArgumentException("Too many columns");
        }

        Set<String> unique = new LinkedHashSet<>();
        for (String column : source) {
            if (column == null || !ALLOWED.containsKey(column)
                    || !unique.add(column)) {
                throw new IllegalArgumentException(
                    "Unknown or duplicate column");
            }
        }
        return List.copyOf(unique);
    }

    public static void apply(Query query, List<String> normalized) {
        if (normalized == null || normalized.isEmpty()) {
            throw new IllegalArgumentException("No columns selected");
        }
        for (String column : normalized) {
            String property = ALLOWED.get(column);
            if (property == null) {
                throw new IllegalArgumentException("Column not allowed");
            }
            query.fields().include(property);
        }

        // MongoDB mặc định trả _id khi dùng inclusion projection.
        if (!normalized.contains("orderId")) {
            query.fields().exclude("id");
        }
    }
}
```

`SafeOrderColumns` chỉ nhận public keys cố định, tránh đưa `"$where"`, các field nội bộ hoặc property path bất kỳ từ client tới MongoDB. `query.fields().include("customerId")` vẫn là **property Java** vì thao tác tiếp theo dùng `mongoTemplate.find(query, Order.class)`; Spring Data ánh xạ thành BSON `customer_id`.

Với MongoDB find projection, `_id` mặc định được giữ khi include các field khác, nên trong ví dụ dùng `exclude("id")` nếu người dùng không yêu cầu cột `orderId`. Quy tắc inclusion/exclusion thông thường **không cho phép trộn tùy ý**, nhưng loại trừ `_id` là ngoại lệ hợp lệ.

### 10.2. Tránh ghi lại entity được đọc bằng projection

```java
Query q = OrderCriteriaBuilder.build(
    input, authenticatedTenantId);

List<String> selectedColumns =
    SafeOrderColumns.normalize(requestedColumns);
SafeOrderColumns.apply(q, selectedColumns);
q.with(SafeOrderPage.fromRequest(0, 20, "createdAt", "desc"));

List<Order> partialOrders =
    mongoTemplate.find(q, Order.class);
```

`partialOrders` là các entity **chỉ được đọc một phần**. Những property không được project có thể mang giá trị null/default trong Java. **Không gọi `mongoTemplate.save(partialOrders.get(0))`** để cập nhật trạng thái hay giao dịch: việc lưu lại object thiếu field có thể thay thế thông tin chưa tải.

Trong API, nên **chuyển dữ liệu đã đọc sang DTO chỉ đọc** và chỉ trả các giá trị đã được phép. Việc chọn cột để **truy xuất** và việc chọn cột để **serialize response** đều phải được kiểm soát; không trả thẳng mọi property có trong entity.

### 10.3. Ánh xạ cột công khai vào response

Ví dụ helper tạo map kết quả có thứ tự theo yêu cầu đã chuẩn hóa:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class OrderRowMapper {
    private OrderRowMapper() {}

    public static Map<String, Object> toPublicRow(
            Order order, List<String> selectedColumns) {
        Map<String, Object> row = new LinkedHashMap<>();
        for (String column : selectedColumns) {
            switch (column) {
                case "orderId" -> row.put(column, order.getId());
                case "customer" -> row.put(column, order.getCustomerId());
                case "status" -> row.put(column, order.getStatus());
                case "total" -> row.put(column, order.getTotalCents());
                case "created" -> row.put(column, order.getCreatedAt());
                default -> throw new IllegalArgumentException(
                    "Unapproved output column");
            }
        }
        return row;
    }
}
```

Không truyền `selectedColumns` chưa validate tới helper này. Một API typed DTO cố định thường đơn giản và dễ bảo trì hơn dynamic map; map chỉ hợp lý khi sản phẩm thực sự cần các cột thay đổi theo request. Với thông tin nhạy cảm, ngoài allowlist cần chính sách authorization cho từng loại dữ liệu hoặc role.

### 10.4. Projection không phải authorization

Một `@Field` hoặc `query.fields().include(...)` không tự ngăn người dùng truy cập tài nguyên trái quyền nếu query thiếu tenant filter. Ngược lại, truy vấn đã lọc đúng tenant nhưng trả mọi field của entity vẫn có thể lộ dữ liệu không được phép hiển thị. Phải thực thi đồng thời:

```text
Identity và quyền: xác định tenant, role tin cậy
      ↓
Filter bắt buộc: giới hạn document được phép đọc
      ↓
Allowlist fields: giới hạn dữ liệu được phép trả
      ↓
Pagination/Sort: giới hạn khối lượng và thứ tự kết quả
      ↓
DTO/response serialization: hợp đồng API công khai
```

Đặc biệt, nếu dùng raw `Document` hoặc aggregation có tính toán, phải kiểm tra alias output và tên BSON vật lý, không mặc định mọi stage đều tự áp dụng mapper của entity giống `MongoTemplate.find(..., Order.class)`.

## 11. Kiểm soát toán tử nâng cao và độ phức tạp của truy vấn

### 11.1. Thiết kế giới hạn tài nguyên như một phần của input contract

Ngoài danh sách field và toán tử, nên áp dụng:

| Giới hạn | Ví dụ chính sách | Lý do |
|---|---|---|
| Số filter | Tối đa 10 điều kiện public | Tránh query tree quá phức tạp |
| Số giá trị trong `IN` | Tối đa 20–50 | Tránh truy vấn rất rộng/nhiều giá trị |
| Độ dài từ khóa | Tối đa 80 ký tự | Giảm rủi ro regex chậm và đầu vào bất thường |
| Số nhánh `OR` | Tối đa 10 | Hạn chế độ phức tạp của truy vấn |
| Page size | Tối đa 100 | Giới hạn dữ liệu trả về |
| Offset | Giới hạn hoặc dùng keyset | Tránh `skip` sâu |
| Sort fields | Allowlist có index/benchmark | Tránh sort tùy ý trên dữ liệu lớn |
| Time span | Tối đa theo SLA, ví dụ 90 ngày với API thường | Ngăn một request quét nhiều năm dữ liệu |

Các con số là gợi ý để thảo luận sản phẩm, **không phải giới hạn cố định của MongoDB hay Spring Data**. Quy định thực tế phải dựa vào workload, index, khả năng database và SLA.

### 11.2. Không chấp nhận pipeline hoặc BSON tùy ý từ client

Không đưa raw JSON như:

```json
{
  "query": {
    "$expr": { "$gt": ["$total_cents", 0] }
  }
}
```

thẳng tới `BasicQuery` hoặc raw driver chỉ vì “API hỗ trợ lọc linh hoạt”. Các toán tử như `$expr`, `$regex`, `$where`, `$lookup` hoặc cấu trúc aggregation phức tạp cần được **chọn bởi logic phía server**, kiểm tra quyền và ngân sách tài nguyên. Không có phép kiểm tra ký tự nào biến một pipeline do người dùng toàn quyền điều khiển thành query an toàn.

`BasicQuery` cho phép viết BSON/JSON query tường minh trong Spring Data, nhưng phù hợp khi **lập trình viên kiểm soát cấu trúc query**. Với input nghiệp vụ, `Criteria` và allowlist giúp diễn đạt ranh giới dễ review hơn.

### 11.3. Tách lỗi input và lỗi database

Với API HTTP:

- Field không nằm trong allowlist, operator sai, giá trị ngày/số không hợp lệ: **400 Bad Request** theo chính sách API.
- Người dùng không có quyền xem dữ liệu/tenant: **403 Forbidden** hoặc cơ chế phản hồi phù hợp chính sách bảo mật; không dựa vào việc query rỗng để coi đã phân quyền.
- Query hết timeout, network lỗi hoặc MongoDB không đáp ứng: xử lý như lỗi hạ tầng; không báo “không tìm thấy” khi truy vấn thực sự thất bại.

Không in raw token, URI chứa password, dữ liệu nhạy cảm hoặc toàn bộ query có PII vào log production. Với việc theo dõi hiệu năng, ghi tên endpoint, số filter, tên field đã allowlist, latency và trạng thái lỗi là đủ trong nhiều trường hợp.

## 12. Index và kiểm tra hiệu năng cho bộ lọc tùy chọn

Một query builder có thể tạo hàng chục tổ hợp khác nhau, nhưng không thể tạo index riêng cho **mọi tổ hợp field**. Cần bắt đầu từ workload thực: các filter phổ biến, sort phổ biến, phân bố tenant, tần suất sử dụng và giới hạn latency.

### 12.1. Index compound cho những tổ hợp quan trọng

Nếu đa số truy vấn lọc theo `tenant_id`, `status`, sau đó sort theo `created_at` mới nhất, có thể thử:

```javascript
db.orders.createIndex(
  { tenant_id: 1, status: 1, created_at: -1, _id: 1 },
  { name: "ix_tenant_status_created" }
);
```

Tương ứng với:

```javascript
db.orders.find({
  tenant_id: "T-A",
  status: "PAID"
}).sort({ created_at: -1, _id: 1 }).limit(20);
```

**Thứ tự trong index có ý nghĩa.** Với filter equality trên `tenant_id` và `status`, MongoDB có cơ hội sử dụng phần còn lại cho sort. Nhưng nếu request **không chọn status**, compound index này không nhất thiết phục vụ sort theo `created_at` hiệu quả vì còn một field `status` nằm trước. Có thể cần thêm index cho kiểu query phổ biến không có status:

```javascript
db.orders.createIndex(
  { tenant_id: 1, created_at: -1, _id: 1 },
  { name: "ix_tenant_created" }
);
```

Không triển khai tất cả các index ví dụ một cách máy móc. Mỗi index có chi phí storage, bộ nhớ, cập nhật và maintenance. Chọn index dựa trên số liệu thực tế và đo tác dụng với các query quan trọng.

### 12.2. Các điều kiện range và sort

Khi filter số tiền:

```javascript
db.orders.find({
  tenant_id: "T-A",
  total_cents: { $gte: NumberLong(10000) }
}).sort({ total_cents: -1 }).limit(20);
```

có thể xem xét:

```javascript
db.orders.createIndex(
  { tenant_id: 1, total_cents: -1, _id: 1 },
  { name: "ix_tenant_total" }
);
```

Một query đồng thời có **range trên total**, **range trên thời gian** và **sort theo customer** khó được tối ưu như ba query equality đơn giản. Đừng chỉ cộng tất cả field vào một index dài rồi tin rằng MongoDB sẽ dùng được chúng hiệu quả ở mọi trường hợp.

### 12.3. explain trên từng tổ hợp đại diện

Chạy trong `mongosh`:

```javascript
db.orders.find({
  tenant_id: "T-A",
  status: "PAID"
}).sort({ created_at: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.orders.find({
  tenant_id: "T-A",
  total_cents: { $gte: NumberLong(10000) }
}).sort({ total_cents: -1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.orders.find({
  tenant_id: "T-A",
  buyer_name: /an/i
}).limit(20).explain("executionStats");
```

So sánh các chỉ số:

| Dấu hiệu | Ý nghĩa cần điều tra |
|---|---|
| `IXSCAN` | MongoDB có dùng index, nhưng có thể vẫn quét nhiều keys |
| `COLLSCAN` | MongoDB quét collection; có thể hợp lý khi dữ liệu quá ít |
| `totalKeysExamined` | Số index keys đã xem xét |
| `totalDocsExamined` | Số document đã xem xét |
| `nReturned` | Số document thực tế trả về |
| Sort stage tốn thời gian | Index không phục vụ sort, hoặc tập dữ liệu quá lớn |
| Latency cao với regex | Điều kiện substring/case-insensitive có thể phải quét rộng |

Với bốn document mẫu, MongoDB hoàn toàn có thể chọn `COLLSCAN` vì dữ liệu quá nhỏ; không kết luận từ một kế hoạch test bé rằng index vô dụng. Đo thêm với dữ liệu có phân bố và cardinality gần production, nhiều lượt benchmark và tải thực.

### 12.4. Count và pagination cũng cần đo

Một trang 20 kết quả có thể lấy nhanh nhưng count của **tất cả kết quả khớp filter** vẫn tốn tài nguyên. Với filter regex hoặc range rộng, `Page` có thể gây thêm tải đáng kể so với chỉ trả một trang. Cân nhắc chỉ đếm khi UX thật sự yêu cầu, caching số liệu khi phù hợp, hoặc sử dụng `Slice`/has-next.

Sort theo field do người dùng lựa chọn cần dựa vào tập field đã review về index và hiệu năng. Có những field public **không nên nằm trong SORT_FIELDS** vì phân bố dữ liệu và index không hỗ trợ, mặc dù UI có thể hiển thị chúng.

## 13. Kiểm thử tích hợp Query/Criteria với MongoDB thật

### 13.1. Những hợp đồng cần test

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Không chọn filter tùy chọn, tenant = `T-A` | Chỉ thấy `O-101`, `O-102`, `O-103` |
| Tenant = `T-A`, `status = PAID` | Chỉ thấy `O-101`, `O-103` |
| Tenant = `T-A`, `archived = false` | Chỉ thấy `O-101`, `O-102` |
| Tenant = `T-A`, `status = PAID`, `archived = false` | Chỉ thấy `O-101` |
| Tenant = `T-A`, `minTotalCents = 0` | Có cả ba đơn; điều kiện số 0 không bị bỏ qua |
| Tenant = `T-A`, `minTotalCents = 10000` | Chỉ thấy `O-101`, `O-103` |
| Tenant = `T-A`, `anyTags = ["retail"]` | Chỉ thấy `O-103` |
| Tenant = `T-A`, khoảng ngày từ 06/01 đến trước 08/01 UTC | Chỉ thấy `O-102` |
| Tìm theo `customerId = C-01`, tenant = `T-A` | Không trả `O-201` của tenant `T-B` |
| SelectedFieldFilter có field `"tenantId"` | Bị từ chối vì không nằm trong allowlist |
| Sort theo field lạ | Bị từ chối trước khi gọi MongoDB |
| Chọn output column không có trong allowlist | Bị từ chối, không lộ dữ liệu |
| page size quá lớn hoặc offset quá sâu | Bị từ chối theo chính sách |
| Chuỗi literal chứa regex metacharacter | Được hiểu như text literal, không như regex tự do |

### 13.2. Ví dụ JUnit 5 + Spring Data MongoDB test

Đoạn minh họa sau giả định môi trường `@DataMongoTest` đã kết nối tới MongoDB integration test được cô lập, không dùng chung với dữ liệu thật. Chỉ trong database test đó, seed dữ liệu:

```java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderCriteriaBuilderTest {
    @Autowired
    MongoTemplate template;

    @BeforeEach
    void seed() {
        // Chỉ trên database test cô lập.
        template.getCollection("orders").deleteMany(
            new org.bson.Document());
        template.insertAll(List.of(
            order("O-101", "T-A", "C-01", "PAID",
                15500L, "An", List.of("vip", "online"), false,
                "2026-01-05T10:00:00Z"),
            order("O-102", "T-A", "C-02", "NEW",
                6500L, "Lan Anh", List.of("online"), false,
                "2026-01-06T10:00:00Z"),
            order("O-103", "T-A", "C-01", "PAID",
                21000L, "ANNA", List.of("vip", "retail"), true,
                "2026-01-08T10:00:00Z"),
            order("O-201", "T-B", "C-01", "PAID",
                99000L, "An", List.of("vip"), false,
                "2026-01-09T10:00:00Z")
        ));
    }

    private static Order order(
            String id, String tenant, String customer, String status,
            long total, String name, List<String> tags,
            boolean archived, String at) {
        return new Order(id, tenant, customer, status, total, name,
            tags, archived, Instant.parse(at));
    }

    private static OrderSearchRequest request(
            String status, Long min, Boolean archived) {
        return new OrderSearchRequest(
            status, null, min, null,
            null, null, archived, null, null);
    }

    @Test
    void tenantFilterIsAlwaysApplied() {
        var q = OrderCriteriaBuilder.build(
            request(null, null, null), "T-A");

        assertThat(template.find(q, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-102", "O-103");
    }

    @Test
    void falseIsAnActualFilterValue() {
        var q = OrderCriteriaBuilder.build(
            request("PAID", null, false), "T-A");

        assertThat(template.find(q, Order.class))
            .extracting(Order::getId)
            .containsExactly("O-101");
    }

    @Test
    void zeroAndPositiveRangeAreNotDropped() {
        var zero = OrderCriteriaBuilder.build(
            request(null, 0L, null), "T-A");
        assertThat(template.find(zero, Order.class)).hasSize(3);

        var threshold = OrderCriteriaBuilder.build(
            request(null, 10000L, null), "T-A");
        assertThat(template.find(threshold, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-103");
    }

    @Test
    void selectableFieldMustBeOnAllowlist() {
        assertThatThrownBy(() -> SelectedFieldCriteria.create(
            new SelectedFieldFilter("tenantId", "T-B")))
            .isInstanceOf(IllegalArgumentException.class);

        var query = OrderCriteriaBuilder.build(
            request(null, null, null), "T-A");
        query.addCriteria(SelectedFieldCriteria.create(
            new SelectedFieldFilter("customer", "C-01")));

        assertThat(template.find(query, Order.class))
            .extracting(Order::getId)
            .containsExactlyInAnyOrder("O-101", "O-103");
    }

    @Test
    void sortAndProjectionRejectUnknownFields() {
        assertThatThrownBy(() ->
            SafeOrderSort.fromRequest("internalNote", "desc"))
            .isInstanceOf(IllegalArgumentException.class);

        assertThatThrownBy(() ->
            SafeOrderColumns.normalize(
                List.of("orderId", "secretToken")))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Các test minh họa behavior của query builder và mapping thực tế, không phải chỉ test object `Criteria` tự tạo. Nếu dự án đã dùng phiên bản Spring Boot mới hơn, tên package `@DataMongoTest`/dependency có thể khác; điều chỉnh theo phiên bản đang triển khai. Không chạy `deleteMany(new Document())` trên database phát triển dùng chung hoặc production vì lệnh xóa toàn bộ collection.

### 13.3. Kiểm thử projection và phân trang

Thêm test:

```java
Query q = OrderCriteriaBuilder.build(
    request(null, null, null), "T-A");

List<String> columns = SafeOrderColumns.normalize(
    List.of("customer", "total"));
SafeOrderColumns.apply(q, columns);
q.with(SafeOrderPage.fromRequest(
    0, 2, "createdAt", "desc"));

List<Order> partial = template.find(q, Order.class);
assertThat(partial).hasSize(2);

for (Order order : partial) {
    var publicRow = OrderRowMapper.toPublicRow(order, columns);
    assertThat(publicRow.keySet())
        .containsExactly("customer", "total");
}
```

Đoạn test này giả định được đặt trong class test ở mục 13.2 và dùng lại helper `request(...)`. Cần kiểm tra thêm raw command/projection hoặc một test `org.bson.Document` riêng để xác minh không trả field BSON ngoài danh sách dự kiến, kể cả `_id` nếu API đã loại trừ.

Đối với sorting ổn định, tạo nhiều document cùng `created_at` rồi kiểm tra tie-breaker `_id`. Với pagination, thêm ca test count và content dùng **cùng filter**, input size vượt giới hạn, page âm và offset sâu. Đừng chỉ test page đầu trên tập dữ liệu ba bản ghi.

### 13.4. Test lỗi đầu vào và bảo mật

Tối thiểu phải có các ca:

- `minTotalCents > maxTotalCents` và khoảng ngày đảo chiều.
- `archived = false`, `minTotalCents = 0` và các string blank.
- Danh sách tag lớn hơn giới hạn hoặc chứa null/blank.
- Giá trị trạng thái không thuộc tập cho phép.
- Tên field nội bộ hoặc không tồn tại, sort direction ngoài `asc`/`desc`.
- Từ khóa chứa `.`, `*`, `[` và chuỗi dài.
- Query có nhánh `OR` nhưng vẫn giữ tenant bắt buộc.
- Người dùng `T-A` cố tìm `O-201` hoặc `C-01` của `T-B` mà không được phép đọc.

Test bảo mật phải kiểm tra **dữ liệu thực sự trả về**, không chỉ kiểm tra một phương thức validation riêng. Đây cũng là lý do một integration test MongoDB thật có giá trị hơn mock `MongoTemplate.find(...)` trong bài toán nhiều tenant.

## 14. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chọn `archived=false` nhưng query không lọc | Dùng `if (Boolean.TRUE.equals(...))` hoặc primitive boolean | Kiểm tra `input.archived() != null` |
| `minTotalCents=0` bị bỏ qua | Dùng kiểm tra `> 0` thay cho `!= null` | Phân biệt vắng mặt và giá trị 0 |
| Thêm hai criteria cùng field bị lỗi | Ghép top-level query trùng key hoặc cấu trúc Criteria sai | Gộp range hoặc dùng `andOperator` |
| Kết quả chứa document của tenant khác | Điều kiện tenant bị bỏ quên, hoặc chỉ có trong một nhánh OR | Đặt tenant bắt buộc ở ngoài OR, kiểm thử nhiều tenant |
| Tìm được bằng mongosh nhưng không bằng template | Dùng sai property Java/BSON hoặc kiểu `_id` | Xem `@Field`, QueryMapper và raw document |
| Truy vấn theo field do user chọn trả dữ liệu nhạy cảm | Không có allowlist/authorization | Mapping public key → property được server duyệt |
| `sortBy` bất kỳ làm response chậm | Sort không index, field có cardinality/kiểu không phù hợp | Allowlist sort, index và benchmark |
| `buyerNameContains = ".*"` khớp tất cả | Dùng regex raw, không quote literal | Dùng `Pattern.quote` |
| Query mất kết quả khi chọn projection | Không include field cần cho DTO hoặc loại `_id` | Kiểm tra field list và hợp đồng DTO |
| `save` làm mất field sau đọc projection | Entity partial được dùng để ghi thay thế | Dùng DTO chỉ đọc hoặc atomic update riêng |
| `Page.totalElements` sai so với content | Count thiếu filter hoặc dùng query có paging sai | Dùng cùng query factory, không mang skip/limit vào count |
| Query range ngày lệch một ngày | Dùng local timezone không thống nhất | Chuyển khoảng ngày theo timezone nghiệp vụ sang UTC |
| Regex chậm dù có index collation | `$regex` không collation-aware như equality/sort | Thiết kế field canonical, prefix hoặc search index |
| Tìm tag sai ý nghĩa | Nhầm `$in` (any) với `$all` (all) | Nêu rõ hợp đồng API và test |

### 14.1. Quy trình điều tra có thể lặp lại

1. Chụp lại **request đã chuẩn hóa** và tenant/role từ security context, tránh lưu PII trong log.
2. Xác minh danh sách filter được thêm: điều kiện nào vắng mặt, điều kiện nào bằng `false` hoặc `0`?
3. Kiểm tra public field đã được ánh xạ sang property Java hợp lệ, và `@Field` đổi đúng tên BSON.
4. Chạy query tương đương trong `mongosh` trên đúng database/collection với dữ liệu mẫu hoặc dữ liệu test.
5. Dùng `explain("executionStats")` và so sánh filter, sort, index, scan, count, page size.
6. Viết regression test cho input gây lỗi: thêm optional filter, sort lạ, tenant khác, dữ liệu null/missing.

Đừng phản ứng bằng cách tăng pool, kéo dài timeout hoặc bỏ điều kiện bắt buộc chỉ để query có kết quả. Lỗi logic, mapping, index và network cần được phân biệt trước khi sửa.

## 15. Bài thực hành: API tìm kiếm đơn hàng có lựa chọn cột

**Bối cảnh:** quản trị viên tenant muốn xem danh sách đơn hàng và được chọn filter theo trạng thái, khoảng tiền, ngày tạo, khách hàng, nhãn hoặc keyword; họ cũng có thể chọn cột public và thứ tự sort. Tất cả dữ liệu phải bị ràng buộc bởi tenant đã xác thực.

1. **Dựng dữ liệu:** tạo bốn document ở mục 2, xác nhận `O-201` thuộc tenant khác.
2. **Khai báo DTO:** tạo `OrderSearchRequest` và thống nhất ngữ nghĩa null/empty, Boolean, số 0, khoảng ngày nửa mở.
3. **Dựng Query:** triển khai `OrderCriteriaBuilder.build(input, trustedTenantId)`, thêm optional filter theo danh sách `Criteria`.
4. **Kiểm soát field tùy chọn:** cho phép user chọn duy nhất `customer`/`status`/`archived` cho equality, từ chối tên khác.
5. **AND/OR:** thêm tìm các đơn `NEW` hoặc `PAID`, vẫn bắt buộc tenant; chứng minh không bao giờ trả `O-201` khi đang đăng nhập tenant `T-A`.
6. **Input an toàn:** thử `buyerNameContains = ".*"`, String rất dài, status sai, range tiền đảo; ghi nhận hành vi theo chính sách.
7. **Sort/page:** dùng `SafeOrderSort` và `SafeOrderPage`, đặt giới hạn page size và offset. Sort theo `createdAt` và tie-breaker `id`.
8. **Projection:** tạo allowlist cột công khai, chỉ trả `orderId`/`customer`/`status`/`total`/`created` theo lựa chọn.
9. **Count:** dùng cùng query factory cho content và count, xác minh `Page.totalElements` theo đúng filter.
10. **Index:** thử index `{ tenant_id: 1, status: 1, created_at: -1, _id: 1 }`; benchmark khi có/không có status, khi dùng regex và khi sort theo total.
11. **Integration tests:** xác minh `false`, `0`, null, `$in`, quyền tenant, output cột public và các tham số bị từ chối.
12. **Giải thích lựa chọn:** nêu vì sao `MongoTemplate/Criteria` phù hợp hơn việc viết hàng chục derived repository methods cho mọi tổ hợp bộ lọc.

**Đạt yêu cầu** khi người học chứng minh được:

- Không có filter tùy chọn vẫn **giữ filter tenant**.
- Các giá trị `0` và `false` được giữ đúng.
- Chỉ những **field/operator được phép** mới được sinh ra trong query và response.
- Query cho `AND`, `OR`, range, array, regex literal đúng ngữ nghĩa.
- Phân trang và sort có giới hạn, count dùng cùng bộ lọc.
- Mapping Java property ↔ BSON đúng, và hiệu năng được đánh giá bằng `explain` chứ không bằng phỏng đoán.

## 16. Tóm tắt nguyên tắc

| Câu hỏi | Lựa chọn nên áp dụng |
|---|---|
| Có nhiều filter tùy chọn? | Gom các `Criteria` có mặt thành một `Query` bằng `andOperator` hoặc chiến lược tương đương |
| Cần giữ `false` và `0`? | Dùng wrapper `Boolean`/`Long` và kiểm tra `!= null` |
| Người dùng chọn field để lọc? | Public field key → allowlist → Java property cố định → Spring BSON mapping |
| Người dùng chọn toán tử? | Enum/bảng toán tử nghiệp vụ được server định nghĩa, không nhận BSON raw |
| Có nhánh OR? | Đặt tenant/authorization filter **ngoài OR** |
| Tìm chuỗi do người dùng nhập? | `Pattern.quote` khi muốn literal; validate length và cân nhắc search index |
| Có khoảng ngày? | Thống nhất timezone, dùng `[from, until)` |
| Có danh sách tag? | Quy định rõ `$in` = any, `$all` = all |
| Người dùng chọn sort? | Allowlist sort + direction validation + tie-breaker + index |
| Người dùng chọn cột output? | Allowlist projection + DTO/read-only response; không save partial entity |
| API có pagination? | Size/offset giới hạn, count cùng filter và đánh giá chi phí `Page` |
| Query chậm? | Đọc `explain("executionStats")` và index đúng với workload |

**Kết luận:** Một bộ lọc động tốt không phải bộ lọc chấp nhận mọi cấu trúc input. Nó là **một hợp đồng có giới hạn** giữa request và MongoDB: chỉ thêm điều kiện hợp lệ, luôn giữ điều kiện truy cập bắt buộc, chỉ dùng trường/toán tử được server cho phép, giới hạn tài nguyên và kiểm chứng kết quả bằng dữ liệu thực. Đây là nền tảng để các lớp `MongoTemplate`, repository tùy biến, aggregation và API tìm kiếm phát triển an toàn khi nhu cầu truy vấn tăng lên.

**Tài liệu tham khảo theo phiên bản dự án:** [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html), [Spring Data MongoDB — Criteria](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html), [MongoDB — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/), [MongoDB — Query and Sort Indexing](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/sort-order/) và [MongoDB — $regex](https://www.mongodb.com/docs/manual/reference/operator/query/regex/). Khi triển khai, đối chiếu API và behavior với phiên bản Spring Data MongoDB, Spring Boot và Java Driver thực tế của dự án.
