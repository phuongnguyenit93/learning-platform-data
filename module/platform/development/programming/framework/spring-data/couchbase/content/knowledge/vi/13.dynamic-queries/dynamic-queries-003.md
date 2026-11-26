# Ánh xạ tên thuộc tính Java sang tên trường lưu trữ

## 1. Vì sao ánh xạ tên trường quan trọng với truy vấn động?

Trong ứng dụng Spring, nhà phát triển thường đặt thuộc tính Java theo **camelCase**, chẳng hạn `customerCode`, `createdAtMillis` hoặc `shippingAddress.postalCode`. Trong Couchbase, document JSON có thể dùng **snake_case**, chẳng hạn `customer_code`, `created_at_ms` và `shipping.postal_code`. Hai cách đặt tên không nhất thiết trùng nhau.

Với repository có phương thức cố định, việc ánh xạ thường do Spring Data đảm nhiệm. Tuy nhiên, khi người dùng gửi một khóa bộ lọc tùy chọn như `sortBy=createdAtMillis` hoặc `field=customerCode`, mã nguồn phải hiểu chính xác thuộc tính Java đó tương ứng với **đường dẫn nào trong JSON lưu trữ**. Nếu không, truy vấn SQL++ có thể chạy thành công nhưng trả về danh sách rỗng, sắp xếp theo một trường `MISSING` hoặc mở ra rủi ro nối identifier không kiểm soát.

Bài này thuộc chương **Truy vấn động** của **SPRING_DATA_COUCHBASE**. Nó kết nối kiến thức **document mapping**, **repository**, **CouchbaseTemplate** và **SQL++** để xây dựng tầng truy cập Couchbase có thể mở rộng. Việc ánh xạ đúng tên trường cũng ảnh hưởng trực tiếp đến **chỉ mục**, sắp xếp, hiệu năng, tính nhất quán, quyền truy cập và API reactive.

Sau bài học, bạn có thể:

1. Dùng `@Field` để ánh xạ tên thuộc tính Java sang khóa JSON khác tên.
2. Phân biệt tên **property Java**, tên **trường lưu trữ** và **document key** của Couchbase.
3. Viết đường dẫn SQL++ chính xác cho thuộc tính lồng nhau và cho ID document.
4. Tạo bảng ánh xạ được kiểm soát khi một API cho phép lọc/sắp xếp theo tên thuộc tính truyền từ client.
5. Kiểm chứng ánh xạ qua JSON thực, repository, template, SQL++ và kế hoạch chỉ mục.

> **Phạm vi phiên bản:** Các ví dụ dùng cách tổ chức Spring Data Couchbase hiện đại (5.x/6.x), Couchbase Java SDK và Java 17+. Tên package và khả năng tự ánh xạ đường dẫn trong từng API cần được đối chiếu theo phiên bản thực tế. Phân biệt rõ những truy vấn do Spring Data dựng từ metadata entity với SQL++ viết thủ công.

## 2. Ba lớp tên thường bị nhầm

Giả sử API nhận `customerCode`, Java entity có `private String customerCode`, còn document Couchbase lưu `"customer_code"`.

| Lớp | Ví dụ | Ai sử dụng? |
| --- | --- | --- |
| **Tên public của bộ lọc** | `customerCode` | Client, DTO, API tìm kiếm |
| **Tên thuộc tính Java** | `OrderDocument.customerCode` | Java code, Spring Data mapping, tên phương thức repository |
| **Tên trường JSON lưu trữ** | `customer_code` | SQL++, Query Service, secondary index, document JSON |

Chúng có thể giống nhau nhưng không phải lúc nào cũng vậy. **Đổi tên property trong Java không tự đổi tên khóa JSON đã được ghi**, và **đổi `@Field` không tự di trú document cũ**.

Ví dụ entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class OrderDocument {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("customer_code")
    private String customerCode;

    @Field("status")
    private String status;

    @Field("created_at_ms")
    private Long createdAtMillis;

    @Field("shipping")
    private ShippingAddress shippingAddress;

    // Constructors, getters và setters được lược bỏ.
}

class ShippingAddress {
    @Field("postal_code")
    private String postalCode;

    @Field("city_name")
    private String cityName;

    // Constructors, getters và setters được lược bỏ.
}
```

Document được ghi vào collection có thể trông như sau:

```json
{
  "tenant_id": "store-01",
  "customer_code": "VIP-008",
  "status": "PAID",
  "created_at_ms": 1792992000000,
  "shipping": {
    "postal_code": "700000",
    "city_name": "Ho Chi Minh City"
  },
  "_class": "com.example.orders.OrderDocument"
}
```

Ở đây:

- `@Field("customer_code")` chỉ định tên khóa JSON cho thuộc tính `customerCode`.
- `@Field("shipping")` đặt tên đối tượng JSON lồng bên ngoài; `@Field("postal_code")` đặt tên khóa bên trong.
- `status` được gắn `@Field("status")` cho dễ nhìn; khi không có tên tùy chỉnh, mapping mặc định thường lấy tên property.
- `_class` là trường phân biệt loại entity thường xuất hiện khi Spring Data Couchbase ghi document. Giá trị thực có thể khác nếu ứng dụng cấu hình type alias hoặc type key; không nên tự gắn giá trị này cứng vào SQL++.
- **Không có thuộc tính `id` trong JSON minh họa**: `@Id` biểu diễn **document key** do Couchbase quản lý. Nếu ứng dụng có khóa JSON `id` riêng, phải định nghĩa đó là một field khác và không nhầm với document key.

## 3. Cách ánh xạ được dùng trong các lớp truy cập dữ liệu

### 3.1. Lưu và đọc document qua Spring Data

Spring Data Couchbase sử dụng metadata từ entity và `@Field` khi chuyển **entity Java ↔ document JSON**. Khi gọi phương thức repository hoặc template để lưu, tên field đã khai báo được dùng cho document. Khi đọc, converter ánh xạ từ khóa JSON về thuộc tính Java tương ứng.

```java
OrderDocument order = repository.findById("order::2026::001")
        .orElseThrow();

String customer = order.getCustomerCode(); // Thuộc tính Java.
```

`repository.findById(...)` truy xuất document theo **document key**, không tìm theo một biểu thức SQL++ `WHERE o.id = ...`. Khi dùng API truy vấn SQL++, document key được lấy bằng hàm metadata `META(o).id`.

### 3.2. Derived query dựa trên tên property Java

Với repository, tên phương thức được phân tích theo **thuộc tính Java**:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndCustomerCode(
            String tenantId, String customerCode);

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
```

`findByTenantIdAndCustomerCode` tham chiếu tới hai property `tenantId` và `customerCode`, **không** viết thành `findByTenant_idAndCustomer_code`. Spring Data dựa vào mapping metadata để tạo truy vấn. Cần có index SQL++ phù hợp cho các derived query dựa trên secondary index.

Khi tên property Java có các thành phần lồng nhau, cú pháp derived query có quy tắc phân giải đường dẫn riêng; kiểm thử cách diễn dịch trong phiên bản sử dụng, nhất là khi các tên property gần giống nhau.

### 3.3. SQL++ viết thủ công dùng tên field lưu trữ

SQL++ truy cập **key JSON thực tế**. Vì vậy:

```sql
SELECT META(o).id AS documentId,
       o.`customer_code` AS customerCode,
       o.`created_at_ms` AS createdAtMillis
FROM `shop`.`sales`.`orders` AS o
WHERE o.`tenant_id` = $tenantId
  AND o.`customer_code` = $customerCode
ORDER BY o.`created_at_ms` DESC
LIMIT 20;
```

Nếu viết `o.customerCode` trong SQL++ nhưng document chỉ có `customer_code`, biểu thức `o.customerCode` thường cho `MISSING`; so sánh trong `WHERE` không trở thành `TRUE`. **Converter của Spring Data không tự sửa đoạn SQL++ thủ công** do bạn gửi trực tiếp cho Couchbase SDK.

Ví dụ đường dẫn lồng nhau:

```sql
-- Java: order.shippingAddress.postalCode
-- JSON: shipping.postal_code
WHERE o.`shipping`.`postal_code` = $postalCode
```

Quy tắc này áp dụng cho `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY` và đặc biệt là định nghĩa **secondary index**.

### 3.4. Khi dùng `CouchbaseTemplate` và `QueryCriteria`

Spring Data Couchbase cung cấp `Query`/`QueryCriteria` để tạo bộ lọc động và `CouchbaseTemplate` để thực thi truy vấn theo entity:

```java
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.couchbase.core.query.QueryCriteria;

// Tên "status" trùng giữa Java property và JSON nên không mơ hồ.
Query query = Query.query(
        QueryCriteria.where("status").is("PAID"));

List<OrderDocument> orders = template
        .findByQuery(OrderDocument.class)
        .matching(query)
        .all();
```

**Điểm quan trọng với field có `@Field` alias:** việc API truy vấn nhận **tên property Java** hay **tên field lưu trữ**, và bước ánh xạ diễn ra tại đâu, cần được xác minh bằng SQL++ cuối cùng được phát sinh từ đúng phiên bản Spring Data Couchbase và bằng kiểm thử tích hợp. Đừng mặc định chuỗi truyền vào `QueryCriteria.where("customerCode")` luôn được biến thành `customer_code`, cũng đừng vội gắn mọi string path thành `customer_code` khi chưa kiểm tra cơ chế query mapper của API đang dùng.

Một cách tránh mơ hồ cho các bộ lọc **thực sự động từ chuỗi client** là giữ bảng ánh xạ tường minh giữa tên public và biểu thức field JSON đã xác nhận, rồi xây SQL++ với identifier từ whitelist và bind giá trị như phần tiếp theo.

## 4. Đường dẫn lồng nhau, collection và metadata

| Java | JSON lưu trữ | Biểu thức SQL++ |
| --- | --- | --- |
| `customerCode` | `customer_code` | `o.customer_code` |
| `createdAtMillis` | `created_at_ms` | `o.created_at_ms` |
| `shippingAddress` | `shipping` | `o.shipping` |
| `shippingAddress.postalCode` | `shipping.postal_code` | `o.shipping.postal_code` |
| `shippingAddress.cityName` | `shipping.city_name` | `o.shipping.city_name` |
| `id` có `@Id` | Document key, không phải JSON field | `META(o).id` |

> Các tên trong bảng đều không cần trích dẫn đặc biệt. Với tên cần escape, SQL++ dùng dấu nháy ngược (backtick); ví dụ dưới đây là đường dẫn có trích dẫn tường minh:

```sql
o.`shipping`.`postal_code`
```

Nếu field lưu trữ là chuỗi chứa dấu chấm, ví dụ document có khóa **`"shipping.postal_code"` ở mức gốc**, cần phân biệt nó với cấu trúc **`"shipping": { "postal_code": ... }`**. SQL++ sử dụng đường dẫn/escaping khác nhau. Hãy kiểm tra document thực thay vì suy diễn từ tên Java.

Khi dữ liệu lồng nằm trong **mảng** (`lineItems[*].sku`), cú pháp truy vấn không đơn giản là nối dấu chấm với `[*]`; SQL++ thường dùng các biểu thức `ANY ... IN ... SATISFIES ... END`, hoặc `UNNEST` tùy bài toán. Index cũng có thể cần cấu trúc array index tương ứng.

**Bucket / scope / collection** xác định *nơi* truy vấn đọc document; `@Field` xác định *tên khóa bên trong document*. Không dùng `@Field` để thay đổi keyspace. Ví dụ keyspace `shop.sales.orders` trỏ tới bucket `shop`, scope `sales`, collection `orders`; các tên này phải khớp cấu hình thực tế.

## 5. Tạo bảng ánh xạ an toàn cho bộ lọc động

Giả sử endpoint nhận:

```text
GET /orders?field=customerCode&value=VIP-008&from=1792800000000&limit=20
```

Nếu lấy trực tiếp `field` và nối vào `WHERE`, người dùng có thể gửi một identifier không tồn tại hoặc chuỗi bất kỳ. **Bind parameter bảo vệ giá trị, không thay thế việc kiểm soát identifier**. Cách thực tế là định nghĩa một ánh xạ cố định từ tên public đã cho phép sang đường dẫn SQL++ được khai báo trong code.

### 5.1. Whitelist tên Java → đường dẫn JSON

```java
import java.util.Arrays;

public enum OrderFilterField {
    CUSTOMER_CODE("customerCode", "o.`customer_code`"),
    STATUS("status", "o.`status`"),
    SHIPPING_POSTAL_CODE(
            "shippingAddress.postalCode",
            "o.`shipping`.`postal_code`");

    private final String publicName;
    private final String sqlPath;

    OrderFilterField(String publicName, String sqlPath) {
        this.publicName = publicName;
        this.sqlPath = sqlPath;
    }

    public String sqlPath() {
        return sqlPath;
    }

    public static OrderFilterField fromPublicName(String name) {
        return Arrays.stream(values())
                .filter(field -> field.publicName.equals(name))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException("Trường lọc không được hỗ trợ"));
    }
}
```

Ở đây public API vẫn dùng tên dễ hiểu theo property Java; chỉ những trường trong enum mới có thể đi vào SQL++. Mỗi biểu thức `sqlPath` là **hằng số do lập trình viên viết**, không lấy từ request.

### 5.2. Sinh SQL++ cho trường lọc và bind giá trị

```java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;

import java.util.List;

public class DynamicOrderLookup {
    private final Cluster cluster;

    public DynamicOrderLookup(Cluster cluster) {
        this.cluster = cluster;
    }

    public List<JsonObject> search(
            String trustedTenantId,
            String requestedField,
            String requestedValue,
            Long createdFromInclusive,
            int limit) {

        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenantId đã xác thực");
        }
        if (requestedValue == null || requestedValue.isBlank()) {
            throw new IllegalArgumentException("Thiếu giá trị lọc");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải trong [1, 100]");
        }

        // Đầu vào từ client chỉ được tra cứu trong whitelist.
        OrderFilterField field =
                OrderFilterField.fromPublicName(requestedField);

        StringBuilder sql = new StringBuilder("""
                SELECT META(o).id AS documentId,
                       o.`customer_code` AS customerCode,
                       o.`status` AS status,
                       o.`created_at_ms` AS createdAtMillis
                FROM `shop`.`sales`.`orders` AS o
                WHERE o.`tenant_id` = $tenantId
                """);

        // field.sqlPath() là hằng số do enum kiểm soát.
        sql.append(" AND ").append(field.sqlPath()).append(" = $filterValue");

        JsonObject parameters = JsonObject.create()
                .put("tenantId", trustedTenantId)
                .put("filterValue", requestedValue)
                .put("limit", limit);

        if (createdFromInclusive != null) {
            sql.append(" AND o.`created_at_ms` >= $createdFrom");
            parameters.put("createdFrom", createdFromInclusive);
        }

        // Có dấu cách đầu chuỗi để tách khỏi mệnh đề WHERE phía trước.
        sql.append(" ORDER BY o.`created_at_ms` DESC, META(o).id DESC");
        sql.append(" LIMIT $limit");

        return cluster.query(
                sql.toString(),
                QueryOptions.queryOptions().parameters(parameters)
        ).rowsAsObject();
    }
}
```

**Đọc kỹ ví dụ:**

- `trustedTenantId` đến từ hệ thống xác thực, không phải một `tenantId` tùy ý do client tự điền. Điều kiện tenant luôn có mặt.
- `requestedField` được chuyển thành enum có danh sách cố định. Không có trường hợp `sql.append(requestedField)`.
- `requestedValue`, `trustedTenantId`, mốc thời gian và giới hạn đều được bind qua `JsonObject` và `QueryOptions`.
- Bộ lọc bằng dấu `=` giả định các trường whitelist trên lưu **chuỗi**. Nếu cho phép lọc số hoặc thời gian, cần mở rộng từng kiểu dữ liệu và toán tử hợp lệ, không ép mọi đầu vào thành chuỗi.
- Chương trình dùng trực tiếp Java SDK nên trả kết quả dạng `JsonObject`, không tự động tạo `OrderDocument` theo converter của Spring Data. Với tầng API nhận entity, cần mapping kết quả riêng hoặc dùng API Spring Data phù hợp.
- Đây là ví dụ một trường chọn động; khi có nhiều bộ lọc, hãy tạo các điều kiện con từ whitelist và dùng `AND`/`OR` có ngoặc tường minh theo hợp đồng API.

### 5.3. Nếu cho chọn cột sắp xếp

Không cho phép client tự nối chuỗi `ORDER BY`. Phân biệt *tên public* và *biểu thức lưu trữ* như khi lọc:

```java
String sortExpression = switch (requestedSort) {
    case "createdAtMillis" -> "o.`created_at_ms`";
    case "customerCode"   -> "o.`customer_code`";
    default -> throw new IllegalArgumentException("Cột sắp xếp không hợp lệ");
};
```

Sau đó chọn hướng `ASC`/`DESC` từ danh sách cố định, thêm khóa phụ ổn định như `META(o).id`, và đặt giới hạn `LIMIT` phù hợp. **Tên trường và từ khóa SQL++ không được bảo vệ bằng bind parameter theo cách giống dữ liệu so sánh.**

## 6. Ánh xạ tên field và secondary index

Index SQL++ được khai báo trên **đường dẫn lưu trữ thực tế**, không lấy tên property Java. Ví dụ:

```sql
-- Dùng tên field JSON, không dùng customerCode hay createdAtMillis.
CREATE INDEX ix_orders_tenant_customer_date
ON `shop`.`sales`.`orders`(
    tenant_id, customer_code, created_at_ms
);

CREATE INDEX ix_orders_tenant_status_date
ON `shop`.`sales`.`orders`(
    tenant_id, status, created_at_ms
);
```

Ví dụ tương ứng:

```sql
EXPLAIN SELECT META(o).id AS documentId,
               o.`customer_code` AS customerCode
FROM `shop`.`sales`.`orders` AS o
WHERE o.`tenant_id` = "store-01"
  AND o.`customer_code` = "VIP-008"
ORDER BY o.`created_at_ms` DESC
LIMIT 20;
```

Trong thực tế, index cần phù hợp kiểu truy vấn và tỷ lệ chọn lọc. Nếu phần lớn request chỉ lọc tenant + thời gian thì có thể cần thêm index bắt đầu bằng `tenant_id, created_at_ms`; không mặc định index của ví dụ đủ cho mọi bộ lọc. Dùng `EXPLAIN` để xem điều kiện nào được đẩy xuống index, có bước sắp xếp không, có phải đọc nhiều document hay không.

**Vì sao tên sai gây vấn đề hiệu năng?** Nếu index dùng `customerCode` nhưng document thực lưu `customer_code`, key index có thể bị coi là thiếu trên nhiều document; truy vấn với tên đúng sẽ không sử dụng index như mong đợi. Vì thế mọi thay đổi `@Field` liên quan đến schema cần đi cùng đánh giá và cập nhật chỉ mục.

## 7. Những bẫy thường gặp

### 7.1. `MISSING` khác `NULL`

Nếu document không chứa `customerCode` nhưng chỉ có `customer_code`, SQL++:

```sql
WHERE o.customerCode = "VIP-008"
```

thường không trả kết quả vì `o.customerCode` là `MISSING`, không phải vì giá trị khác `VIP-008`.

| Trường hợp JSON | Kiểm tra SQL++ |
| --- | --- |
| `"customer_code": "VIP-008"` | `o.customer_code = "VIP-008"` |
| `"customer_code": null` | `o.customer_code IS NULL` |
| Không có khóa `customer_code` | `o.customer_code IS MISSING` |
| `"customer_code": ""` | `o.customer_code = ""` |

Trường hợp DTO bỏ trống bộ lọc là một khái niệm khác: nó có nghĩa là **không tạo điều kiện WHERE tương ứng** nếu nghiệp vụ cho phép.

### 7.2. `@Id` và tên `id` trong JSON

`@Id private String id` được map với **key của document**. Nếu muốn lọc theo ID bằng SQL++, dùng:

```sql
WHERE META(o).id = $documentId
```

Nếu đã biết chính xác document key, ưu tiên `repository.findById(key)` hoặc SDK KV vì không cần Query Service và index SQL++. Với trường `orderNumber` nằm trong JSON, `WHERE o.order_number = ...` là chuyện khác với `META(o).id`.

### 7.3. Đổi `@Field` khi đã có dữ liệu

Giả sử trước đây `customerCode` được lưu thành `customer_code`, sau đó đổi thành `buyer_code`. Annotation mới **không tự đổi** các document cũ. Có thể phát sinh dữ liệu hai schema: document cũ chứa `customer_code`, document mới chứa `buyer_code`.

Cần có kế hoạch migration:

1. Xác định số lượng document đang dùng tên cũ và mới trong từng collection.
2. Lên chiến lược backfill hoặc đọc tương thích trong giai đoạn chuyển tiếp.
3. Cập nhật `@Field`, truy vấn SQL++, index, kiểm thử và bộ lọc public cùng một kế hoạch triển khai.
4. Với lưu lượng ghi liên tục, xem xét thứ tự triển khai để không tạo khoảng thời gian ứng dụng không đọc được dữ liệu.
5. Sau migration, xác minh thống kê và kế hoạch `EXPLAIN` trước khi gỡ khả năng tương thích cũ.

Không nên dùng `COALESCE(o.buyer_code, o.customer_code)` như giải pháp tối ưu mặc định: cách viết này có thể ảnh hưởng khả năng sử dụng index và phải được kiểm tra bằng kế hoạch truy vấn.

### 7.4. Field được đổi tên, JSON key khác kiểu hoặc lồng theo mảng

Tránh giả định `@Field("postal_code")` có nghĩa tất cả document đều chứa string: dữ liệu lịch sử có thể thiếu key hoặc dùng kiểu khác. Với nested array, một đường dẫn đơn giản không thay thế được toán tử mảng của SQL++; cần thiết kế riêng logic lọc và index mảng.

### 7.5. `@Version`, CAS và dữ liệu metadata

Ứng dụng có thể dùng `@Version` để quản lý CAS cho optimistic locking. CAS là metadata phục vụ cập nhật có điều kiện, không nên giả định nó là một khóa JSON thông thường tên `version`. Phân biệt việc truy vấn theo field lưu trữ với việc kiểm tra phiên bản khi cập nhật để tránh kết luận sai về dữ liệu và tính nhất quán.

### 7.6. Giao dịch, TTL và API reactive

TTL có thể khiến document hết hạn trong khi người dùng đang phân trang. Giao dịch và mức scan consistency ảnh hưởng dữ liệu quan sát được khi chạy truy vấn. `ReactiveCouchbaseTemplate` vẫn tuân theo mapping entity và các quy tắc tên field trong đường truy vấn tương ứng; chuyển từ blocking sang reactive **không tự sửa** sai tên trường. Với luồng vừa ghi vừa tìm qua SQL++, cần hiểu rằng index có thể chưa cập nhật tức thì theo mức nhất quán mặc định.

## 8. Kiểm thử ánh xạ từ Java tới Couchbase

Kiểm thử chỉ dùng mock converter thường không phát hiện sai tên index hoặc câu SQL++. Một bộ kiểm thử tích hợp tối thiểu nên:

1. **Ghi document bằng repository/template**, sau đó đọc JSON thực từ Couchbase để xác nhận `customer_code`, `created_at_ms`, `shipping.postal_code` tồn tại đúng vị trí và kiểu.
2. **Đọc lại qua `findById`**, xác nhận `customerCode`, `createdAtMillis`, `shippingAddress.postalCode` được khôi phục đúng và ID chính là document key.
3. **Chạy derived query**, ví dụ `findByTenantIdAndCustomerCode`, để kiểm chứng metadata của repository cùng với index thực.
4. **Chạy truy vấn SQL++ thủ công** bằng tên JSON và xác minh kết quả; thử cố ý dùng `customerCode` để quan sát lỗi `MISSING` nếu document chỉ có `customer_code`.
5. **Thử endpoint lọc động** bằng từng tên public cho phép; tên không nằm trong whitelist phải bị từ chối, không trở thành một đoạn SQL++.
6. **Thử ít nhất hai tenant** có cùng customer code, bảo đảm phạm vi truy cập bắt buộc luôn được áp dụng.
7. **Thử dữ liệu thiếu, null và dữ liệu lịch sử**, kiểm chứng hành vi theo hợp đồng API.
8. **Kiểm tra `EXPLAIN`** với các trường lưu trữ thực và số lượng dữ liệu gần thực tế.

Ví dụ ma trận kiểm thử:

| Đầu vào API | Trường JSON phải được truy vấn | Kết quả mong đợi |
| --- | --- | --- |
| `field=customerCode` | `customer_code` | Đơn đúng mã khách hàng và tenant |
| `field=status` | `status` | Đơn có trạng thái tương ứng |
| `field=shippingAddress.postalCode` | `shipping.postal_code` | Đơn đúng mã bưu chính lồng |
| `field=createdAtMillis` | Không nằm trong enum bộ lọc `=` ở ví dụ | Bị từ chối; thời gian được lọc qua tham số riêng |
| `field=tenantId` | Không có quyền chọn động | Bị từ chối; tenant là điều kiện bắt buộc |
| `field=unknown` | Không có ánh xạ | Lỗi xác thực bộ lọc |

## 9. Bài tập thực hành

**Bài 1 — Đọc mapping**

Cho entity:

```java
@Document
class ProductDocument {
    @Id String id;
    @Field("sku_code") String sku;
    @Field("unit_price") long unitPrice;
    @Field("attributes") ProductAttributes attributes;
}

class ProductAttributes {
    @Field("brand_name") String brandName;
}
```

Hãy viết đường dẫn SQL++ cho `sku`, `unitPrice`, `attributes.brandName` và `id`.

**Đáp án gợi ý:** `p.sku_code`, `p.unit_price`, `p.attributes.brand_name`, `META(p).id`.

**Bài 2 — Bắt lỗi truy vấn**

```sql
SELECT o.customerCode
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.customerCode = $customerCode;
```

Với entity và JSON ở phần 2, hãy sửa cả ba vị trí field lưu trữ. **Đáp án:** `o.customer_code`, `o.tenant_id`, `o.customer_code`. Nếu muốn tên kết quả thành `customerCode`, dùng `AS customerCode`.

**Bài 3 — Mở rộng bộ lọc động:** Thêm bộ lọc `status` hoặc `shippingAddress.postalCode` vào enum whitelist; giải thích vì sao không dùng trực tiếp tên trường client trong `ORDER BY`. Viết kiểm thử một tenant đúng và một tenant khác có cùng giá trị.

**Bài 4 — Migration:** Đổi JSON field `created_at_ms` thành `created_at_epoch`. Liệt kê các vị trí phải cập nhật: annotation, query, index, dữ liệu cũ, test và hợp đồng API; xác định phương án triển khai an toàn.

## 10. Ghi nhớ và tài liệu tham khảo

Tên thuộc tính Java mô tả **mô hình ứng dụng**; `@Field` gắn nó với **cấu trúc JSON lưu trữ**; SQL++ truy cập **key JSON thực tế**. `@Id` là document key, được truy vấn qua `META(alias).id` khi cần SQL++. Trong truy vấn động, hãy dùng bảng ánh xạ từ khóa API sang identifier hợp lệ, bind toàn bộ giá trị, và kiểm chứng kết quả bằng document thật cùng `EXPLAIN`.

Nguồn tra cứu:

- [Spring Data Couchbase — Object Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/object-mapping.html).
- [Spring Data Couchbase — Repository query methods](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html).
- [Spring Data Couchbase — Template API](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html).
- [Spring Data Couchbase — `QueryCriteria` API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/QueryCriteria.html).
- [Couchbase Server — SQL++ SELECT overview](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectintro.html).
- [Couchbase Server — Indexes](https://docs.couchbase.com/server/current/indexes/indexing-overview.html).
