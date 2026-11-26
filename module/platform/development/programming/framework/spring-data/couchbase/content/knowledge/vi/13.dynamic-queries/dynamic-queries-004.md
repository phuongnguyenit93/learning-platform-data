# Trường lồng nhau, tập giá trị và điều kiện tùy chọn trong Spring Data Couchbase

## 1. Bài toán: một API tìm kiếm, nhiều cấu trúc JSON

Màn hình tìm kiếm đơn hàng thường cho phép kết hợp những bộ lọc rất khác nhau:

- **Trường lồng nhau:** tìm đơn có `shipping.postal_code = "700000"`.
- **Tập giá trị:** chỉ lấy đơn có `status` nằm trong `["PAID", "SHIPPED"]`.
- **Mảng giá trị đơn giản:** đơn có thẻ `"priority"` trong mảng `tags`.
- **Mảng đối tượng:** đơn có *ít nhất một* dòng hàng mang SKU `"SKU-42"` và số lượng tối thiểu là 2.
- **Điều kiện tùy chọn:** trường nào không được gửi thì không tham gia truy vấn, trong khi phạm vi `tenantId` vẫn luôn bắt buộc.

Trong chương **Truy vấn động** của **SPRING_DATA_COUCHBASE**, ta sẽ chuyển các yêu cầu trên thành truy vấn có cấu trúc, đúng nghĩa và có thể tối ưu. Đây là một phần của việc xây dựng tầng truy cập Couchbase bằng Spring Data với **document mapping**, repository, `CouchbaseTemplate` và **SQL++**; những lựa chọn về bucket/scope/collection, chỉ mục, TTL, CAS, transaction và reactive API sẽ được nhắc đến ở mức cần thiết cho bài toán lọc.

**Sau bài này, bạn có thể:**

1. Phân biệt một **đối tượng JSON lồng nhau** với một **mảng JSON** và chọn đúng cách truy vấn.
2. Hiểu sự khác nhau giữa `IN` trên một trường scalar, tìm phần tử của một mảng và `ANY ... SATISFIES` trên mảng đối tượng.
3. Thiết kế hợp đồng rõ ràng cho `null`, chuỗi rỗng, tập rỗng, `NULL` và `MISSING`.
4. Xây dựng truy vấn động an toàn với các mảnh SQL++ có sẵn, tham số tên, nhóm điều kiện và giới hạn truy xuất.
5. Kiểm chứng tính đúng đắn và lựa chọn chỉ mục, đặc biệt là **array index**.

> **Phiên bản:** Ví dụ sử dụng Java 17+, Spring Data Couchbase hiện đại (5.x/6.x) và Couchbase Java SDK 3.x. Những ví dụ SQL++ ghi rõ đường dẫn JSON lưu trữ; với API sinh câu truy vấn từ entity, cần kiểm tra hành vi ánh xạ tên trường theo phiên bản sử dụng.

## 2. Dữ liệu mẫu và cách ánh xạ document

Giả sử collection `shop.sales.orders` chứa:

```json
{
  "tenant_id": "store-01",
  "order_number": "SO-2026-0042",
  "status": "PAID",
  "created_at_ms": 1792992000000,
  "shipping": {
    "postal_code": "700000",
    "city": "Ho Chi Minh City"
  },
  "tags": ["priority", "mobile"],
  "line_items": [
    {"sku": "SKU-42", "quantity": 2, "unit_price": 150000},
    {"sku": "SKU-99", "quantity": 1, "unit_price": 80000}
  ]
}
```

Cấu trúc trên chứa **ba hình thức dữ liệu**:

| Đường dẫn lưu trữ | Kiểu JSON | Ý nghĩa |
| --- | --- | --- |
| `status` | Chuỗi | Giá trị đơn, dùng `=` hoặc `IN` |
| `shipping.postal_code` | Chuỗi trong object lồng | Truy cập bằng đường dẫn dấu chấm |
| `tags` | Mảng chuỗi | Kiểm tra một phần tử thuộc mảng |
| `line_items` | Mảng object | Kiểm tra điều kiện trên *cùng một phần tử* |
| `created_at_ms` | Số | Mốc thời gian, so sánh theo khoảng |

Một cách biểu diễn entity bằng Spring Data Couchbase:

```java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class OrderDocument {
    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_number")
    private String orderNumber;

    private String status;

    @Field("created_at_ms")
    private Long createdAtMillis;

    @Field("shipping")
    private Shipping shippingAddress;

    private List<String> tags;

    @Field("line_items")
    private List<LineItem> lineItems;

    // Constructors, getters, setters được lược bỏ.
}

class Shipping {
    @Field("postal_code")
    private String postalCode;

    private String city;
}

class LineItem {
    private String sku;
    private Integer quantity;

    @Field("unit_price")
    private Long unitPrice;
}
```

`@Field` là cầu nối giữa **tên thuộc tính Java** và **khóa JSON được lưu**. Ví dụ `shippingAddress.postalCode` trong Java tương ứng với `shipping.postal_code` trong SQL++. Không tự giả định rằng tên property Java là đường dẫn SQL++ đúng khi viết câu truy vấn thủ công. `@Id` biểu diễn document key và có thể truy xuất trong SQL++ qua `META(o).id`.

## 3. Trường lồng nhau: điều kiện trên object JSON

Đối với một **object** `shipping`, cách truy vấn thông thường là dùng dấu chấm:

```sql
SELECT META(o).id AS documentId,
       o.order_number AS orderNumber,
       o.shipping.postal_code AS postalCode
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenant_id = $tenantId
  AND o.shipping.postal_code = $postalCode;
```

`$tenantId` và `$postalCode` là tham số truy vấn. Tên field `shipping.postal_code` là identifier SQL++ đã biết trước. Nếu document không có object `shipping` hoặc không có `postal_code`, truy cập đường dẫn đó thường cho giá trị `MISSING`; phép so sánh với chuỗi không trở thành `TRUE` trong `WHERE`.

### 3.1. Nested property khác mảng

```json
{"shipping": {"postal_code": "700000"}}
```

Ở cấu trúc này, `shipping.postal_code` truy cập một giá trị trực tiếp. Nhưng nếu JSON là:

```json
{"addresses": [{"postal_code": "700000"}, {"postal_code": "100000"}]}
```

thì `addresses` là **mảng object**. Không được coi `addresses.postal_code` là phép kiểm tra “có một địa chỉ phù hợp”. Phải dùng toán tử mảng, chẳng hạn:

```sql
WHERE ANY a IN o.addresses
      SATISFIES a.postal_code = $postalCode
      END
```

### 3.2. Trường cha không tồn tại và trường con không tồn tại

```sql
-- Không có object shipping hoặc không có key postal_code:
WHERE o.shipping.postal_code IS MISSING

-- Có khóa postal_code với giá trị JSON null:
WHERE o.shipping.postal_code IS NULL

-- Chỉ muốn các đơn có mã bưu chính chứa một giá trị:
WHERE o.shipping.postal_code IS VALUED
```

Nếu cần phân biệt riêng *object cha* thiếu với *thuộc tính con* thiếu, kiểm tra `o.shipping IS MISSING` và `o.shipping.postal_code IS MISSING` thành hai điều kiện riêng. `NULL`, `MISSING` và chuỗi rỗng là ba trạng thái khác nhau.

## 4. Tập giá trị: phân biệt `IN` và membership trong mảng

### 4.1. Một trường scalar thuộc tập cho phép

Ví dụ chỉ chấp nhận các đơn có trạng thái PAID hoặc SHIPPED:

```sql
WHERE o.status IN ["PAID", "SHIPPED"]
```

Đây là phép kiểm tra **giá trị ở vế trái thuộc mảng ở vế phải**, tương đương về mặt nghiệp vụ với:

```sql
WHERE o.status = "PAID" OR o.status = "SHIPPED"
```

Khi có điều kiện tenant, phải bao phủ nhóm `OR` bằng ngoặc:

```sql
WHERE o.tenant_id = $tenantId
  AND (o.status = "PAID" OR o.status = "SHIPPED")
```

Trong `QueryCriteria` của Spring Data Couchbase, trường không có alias phức tạp có thể biểu diễn bằng:

```java
import org.springframework.data.couchbase.core.query.Query;
import org.springframework.data.couchbase.core.query.QueryCriteria;

Query query = Query.query(
        QueryCriteria.where("status").in("PAID", "SHIPPED"));
```

Để thêm điều kiện phạm vi, ngày và các bộ lọc tùy chọn, tiếp tục dựng query theo các tiêu chí phù hợp. Với đường dẫn `@Field` đã đổi tên hoặc điều kiện mảng phức tạp, phải kiểm tra SQL++ mà API template thực sự sinh ra; phần 7 minh họa SQL++ tường minh bằng SDK để bảo đảm đường dẫn lồng nhau và điều kiện `ANY`.

### 4.2. Tìm một giá trị bên trong mảng chuỗi

Với document có `tags = ["priority", "mobile"]`, yêu cầu **mảng tags chứa thẻ priority** khác với yêu cầu “status thuộc tập trạng thái”.

Hai cách diễn đạt:

```sql
-- Kiểm tra mảng chứa một giá trị.
WHERE ARRAY_CONTAINS(o.tags, $tag)

-- Biểu thức lượng từ, hữu ích khi cần index mảng hoặc điều kiện phức tạp.
WHERE ANY t IN o.tags SATISFIES t = $tag END
```

Ở đây `$tag` là một **chuỗi đơn**, còn `o.tags` là **mảng của document**. Với `status IN $statuses`, phía bên phải `$statuses` lại là **mảng đầu vào** dùng để lọc một field scalar. Nhầm hai hướng này sẽ tạo logic không đúng.

| Nhu cầu | Biểu thức | Ý nghĩa |
| --- | --- | --- |
| Trạng thái đơn nằm trong các trạng thái được chọn | `o.status IN $statuses` | **Scalar** thuộc tập đầu vào |
| Tags của đơn chứa một nhãn yêu cầu | `ARRAY_CONTAINS(o.tags, $tag)` | **Mảng lưu trữ** chứa một giá trị |
| Một phần tử của tags phù hợp điều kiện | `ANY t IN o.tags SATISFIES t = $tag END` | Có ít nhất một phần tử phù hợp |
| Ít nhất một item có SKU và quantity cùng thỏa | `ANY li IN o.line_items SATISFIES ... END` | Kiểm tra đồng thời các trường trên **cùng item** |

### 4.3. Tập đầu vào rỗng phải có hợp đồng rõ

Với `statuses=[]`, không được tự động suy ra rằng client muốn “tất cả trạng thái”. Hai hợp đồng phổ biến:

- **Không truyền** `statuses` (`null` trong DTO): bỏ bộ lọc trạng thái.
- **Truyền mảng rỗng:** hoặc từ chối với lỗi hợp lệ hóa, hoặc cố ý trả danh sách rỗng. Cần chọn và ghi trong hợp đồng API.

Trong ví dụ Java cuối bài, ta chọn **từ chối tập trạng thái rỗng**. Danh sách không rỗng được kiểm tra từng giá trị, giới hạn số lượng và truyền qua named parameter `$statuses`; không ghép các giá trị thành chuỗi SQL++.

## 5. Mảng object: dùng `ANY ... SATISFIES`

Giả sử đơn hàng có:

```json
{
  "line_items": [
    {"sku": "SKU-42", "quantity": 1},
    {"sku": "SKU-99", "quantity": 5}
  ]
}
```

Yêu cầu: *tìm đơn có ít nhất một dòng hàng SKU-42 với số lượng từ 2 trở lên*.

**Truy vấn đúng:**

```sql
WHERE ANY li IN o.line_items
      SATISFIES li.sku = $sku AND li.quantity >= $minQuantity
      END
```

Hai điều kiện `sku` và `quantity` được kiểm tra **trên cùng biến `li`**, tức cùng một phần tử của mảng. Dữ liệu mẫu phía trên **không khớp**: dòng có SKU-42 chỉ có quantity=1; dòng có quantity=5 lại là SKU-99.

**Truy vấn có thể sai nghiệp vụ:**

```sql
WHERE ANY li IN o.line_items SATISFIES li.sku = $sku END
  AND ANY li IN o.line_items SATISFIES li.quantity >= $minQuantity END
```

Hai `ANY` riêng cho phép **hai phần tử khác nhau** đáp ứng mỗi điều kiện; đơn mẫu sẽ bị tính là khớp, dù không có dòng hàng nào vừa đúng SKU vừa đủ số lượng.

### 5.1. `ANY`, `EVERY`, `ANY AND EVERY`

| Biểu thức | Điều kiện đúng | Với mảng rỗng `[]` |
| --- | --- | --- |
| `ANY x IN arr SATISFIES P(x) END` | Có ít nhất một phần tử thỏa `P` | `FALSE` |
| `EVERY x IN arr SATISFIES P(x) END` | Mọi phần tử đều thỏa `P` | `TRUE` |
| `ANY AND EVERY x IN arr SATISFIES P(x) END` | Mảng không rỗng và mọi phần tử đều thỏa `P` | `FALSE` |

Ví dụ muốn mọi dòng hàng có `quantity > 0` **và phải có ít nhất một dòng hàng**:

```sql
WHERE ANY AND EVERY li IN o.line_items
      SATISFIES li.quantity > 0
      END
```

Không dùng `EVERY` đơn lẻ nếu điều kiện nghiệp vụ yêu cầu mảng **không được rỗng**. Với array `NULL` hoặc `MISSING`, các biểu thức có thể tạo kết quả khác `TRUE`; không đánh đồng với mảng rỗng.

### 5.2. Membership lồng sâu

Nếu mỗi `line_item` còn chứa mảng `discount_codes`:

```sql
WHERE ANY li IN o.line_items
      SATISFIES li.sku = $sku
         AND ARRAY_CONTAINS(li.discount_codes, $code)
      END
```

Truy vấn bảo đảm cả SKU và mã giảm giá thuộc **cùng một dòng hàng**. Khi truy vấn sâu hơn nhiều cấp, cần kiểm tra cấu trúc JSON thực và đo chi phí truy vấn.

## 6. Thiết kế điều kiện tùy chọn

Hãy phân biệt **trạng thái tham số của API** với **trạng thái giá trị JSON**:

| Tình huống | Cách hiểu đã chọn trong ví dụ | Hành động |
| --- | --- | --- |
| `postalCode == null` | Người dùng không yêu cầu lọc theo mã bưu chính | Không thêm `WHERE` liên quan |
| `postalCode == "  "` | Chuỗi chỉ gồm khoảng trắng được xem như chưa lọc | Không thêm điều kiện |
| `statuses == null` | Không lọc trạng thái | Bỏ `IN` |
| `statuses.isEmpty()` | Đầu vào không hợp lệ theo hợp đồng bài này | Trả lỗi xác thực |
| `minQuantity == 0` | Có truyền số 0, nhưng nghiệp vụ yêu cầu số lượng từ 1 | Trả lỗi |
| Field JSON là `null` | Key tồn tại với giá trị `NULL` | Dùng `IS NULL` khi thật sự muốn tìm |
| Field JSON không tồn tại | Key `MISSING` | Dùng `IS MISSING` khi thật sự muốn tìm |
| `tags == []` trong document | Mảng có mặt nhưng không có phần tử | `ANY` không tìm được phần tử phù hợp |

**Quy tắc:** khi bộ lọc là tùy chọn, kiểm tra xem **tham số đầu vào có được cung cấp hợp lệ hay không** trước khi tạo điều kiện. Không viết `field = NULL` để diễn đạt “bỏ qua bộ lọc”.

### 6.1. Hai phong cách dựng truy vấn động

**Thêm điều kiện khi cần:** chỉ nối một đoạn `AND ...` nếu tham số hiện diện. Đây là cách dùng trong ví dụ Java ở phần 7:

```sql
WHERE o.tenant_id = $tenantId
  AND o.status IN $statuses
  AND o.shipping.postal_code = $postalCode
```

Nếu `postalCode` không có, bỏ **toàn bộ** điều kiện cuối. Ưu điểm là câu query ít điều kiện dư thừa, giúp dễ đọc và dễ lập index hơn.

**Một câu query cố định có điều kiện vô hiệu hóa:**

```sql
WHERE o.tenant_id = $tenantId
  AND ($postalCode IS NULL OR o.shipping.postal_code = $postalCode)
```

Cách này có thể thuận tiện cho một số API, nhưng phải chấp nhận semantics `NULL` đã quy định và xem lại khả năng tối ưu index của nhánh `OR`. Với nhiều điều kiện tùy chọn, query cố định dễ trở nên khó tối ưu và khó phân biệt giữa “không lọc” với “muốn tìm JSON `NULL`”.

### 6.2. Điều kiện bắt buộc phải nằm ngoài các nhóm tùy chọn

```sql
-- Đúng: tenant bao phủ cả hai nhánh.
WHERE o.tenant_id = $tenantId
  AND (
      o.status IN $statuses
      OR ANY t IN o.tags SATISFIES t = $tag END
  )
```

Nếu chuyển `o.tenant_id = $tenantId` vào một nhánh `OR` duy nhất, các document của tenant khác có thể vượt qua nhánh còn lại. Khi API cho phép tổ hợp `AND`/`OR` tùy chọn, luôn xây một nhóm **điều kiện phân quyền chung** ở ngoài cùng.

## 7. Ví dụ hoàn chỉnh: dựng bộ lọc tùy chọn bằng SQL++ tham số hóa

Ta dùng Spring Data Couchbase để lưu/đọc entity thông thường; với **điều kiện mảng có lượng từ `ANY` và nhiều alias `@Field`**, ví dụ dưới chọn Couchbase Java SDK để chủ động ghi đúng đường dẫn JSON và cấu trúc ngoặc. Kết quả SDK là `JsonObject`, không tự chạy qua Spring Data entity converter.

### 7.1. DTO bộ lọc

```java
import java.util.Set;

// Java 17+
public record OrderFilter(
        String postalCode,
        Set<String> statuses,
        String tag,
        String sku,
        Integer minItemQuantity,
        Long createdFromInclusive,
        Long createdBeforeExclusive
) {}
```

Trong hợp đồng này:

- `postalCode`, `tag`, `sku` có thể vắng mặt.
- `statuses` là một tập trạng thái **được phép**, không phải chuỗi SQL++.
- `minItemQuantity` có thể đi kèm `sku` hoặc đứng riêng: khi đứng riêng, lọc “có ít nhất một dòng hàng với số lượng từ N”.
- `createdFromInclusive` và `createdBeforeExclusive` là epoch milliseconds, khoảng **[từ, trước)**.
- `tenantId` **không nằm trong DTO** vì phải lấy từ ngữ cảnh đã xác thực.

### 7.2. Service dựng câu query

```java
import java.util.List;
import java.util.Objects;
import java.util.Set;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonArray;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;

public final class DynamicOrderSearch {
    private static final Set<String> ALLOWED_STATUSES =
            Set.of("NEW", "PAID", "SHIPPED", "CANCELLED");

    private final Cluster cluster;

    public DynamicOrderSearch(Cluster cluster) {
        this.cluster = cluster;
    }

    public List<JsonObject> search(
            String trustedTenantId, OrderFilter filter, int limit) {

        Objects.requireNonNull(filter, "filter");

        if (!hasText(trustedTenantId)) {
            throw new IllegalArgumentException("Thiếu tenant đã xác thực");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải trong [1, 100]");
        }
        if (filter.createdFromInclusive() != null
                && filter.createdBeforeExclusive() != null
                && filter.createdFromInclusive()
                        >= filter.createdBeforeExclusive()) {
            throw new IllegalArgumentException("Khoảng thời gian không hợp lệ");
        }

        StringBuilder sql = new StringBuilder("""
            SELECT META(o).id AS documentId,
                   o.order_number AS orderNumber,
                   o.status, o.shipping, o.tags, o.line_items
            FROM `shop`.`sales`.`orders` AS o
            WHERE o.tenant_id = $tenantId
            """);

        JsonObject params = JsonObject.create()
                .put("tenantId", trustedTenantId)
                .put("limit", limit);

        // Scalar status thuộc danh sách các trạng thái đầu vào.
        if (filter.statuses() != null) {
            if (filter.statuses().isEmpty()
                    || filter.statuses().size() > ALLOWED_STATUSES.size()) {
                throw new IllegalArgumentException("Tập trạng thái không hợp lệ");
            }
            JsonArray allowed = JsonArray.create();
            for (String status : filter.statuses()) {
                if (status == null || !ALLOWED_STATUSES.contains(status)) {
                    throw new IllegalArgumentException("Trạng thái không hợp lệ");
                }
                allowed.add(status);
            }
            sql.append(" AND o.status IN $statuses");
            params.put("statuses", allowed);
        }

        // Trường lồng nhau dạng object.
        if (hasText(filter.postalCode())) {
            sql.append(" AND o.shipping.postal_code = $postalCode");
            params.put("postalCode", filter.postalCode().trim());
        }

        // Mảng chuỗi: ít nhất một tag đúng bằng giá trị cần tìm.
        if (hasText(filter.tag())) {
            sql.append(
                    " AND ANY t IN o.tags SATISFIES t = $tag END");
            params.put("tag", filter.tag().trim());
        }

        // Mảng object: SKU và số lượng cùng nằm trên một line_item.
        if (hasText(filter.sku()) || filter.minItemQuantity() != null) {
            StringBuilder itemCondition = new StringBuilder();

            if (hasText(filter.sku())) {
                itemCondition.append("li.sku = $sku");
                params.put("sku", filter.sku().trim());
            }

            if (filter.minItemQuantity() != null) {
                if (filter.minItemQuantity() < 1) {
                    throw new IllegalArgumentException("minItemQuantity phải >= 1");
                }
                if (itemCondition.length() > 0) {
                    itemCondition.append(" AND ");
                }
                itemCondition.append("li.quantity >= $minQuantity");
                params.put("minQuantity", filter.minItemQuantity());
            }

            sql.append(" AND ANY li IN o.line_items SATISFIES ")
                    .append(itemCondition)
                    .append(" END");
        }

        if (filter.createdFromInclusive() != null) {
            sql.append(" AND o.created_at_ms >= $createdFrom");
            params.put("createdFrom", filter.createdFromInclusive());
        }
        if (filter.createdBeforeExclusive() != null) {
            sql.append(" AND o.created_at_ms < $createdBefore");
            params.put("createdBefore", filter.createdBeforeExclusive());
        }

        // Tên trường sắp xếp được cố định trong code.
        sql.append(" ORDER BY o.created_at_ms DESC, META(o).id DESC");
        sql.append(" LIMIT $limit");

        return cluster.query(
                sql.toString(),
                QueryOptions.queryOptions().parameters(params)
        ).rowsAsObject();
    }

    private static boolean hasText(String text) {
        return text != null && !text.isBlank();
    }
}
```

**Những quyết định trong ví dụ:**

1. `WHERE o.tenant_id = $tenantId` luôn xuất hiện, kể cả khi toàn bộ bộ lọc tùy chọn đều rỗng. `tenantId` chỉ lấy từ ngữ cảnh tin cậy.
2. Các đoạn SQL++ được nối thêm đều là **chuỗi hằng do lập trình viên viết**. Giá trị `sku`, `tag`, trạng thái và thời gian được bind bằng named parameters.
3. Danh sách trạng thái được kiểm tra hợp lệ trước khi đưa vào `JsonArray`. Đầu vào `statuses=[]` sẽ được từ chối; `statuses=null` nghĩa là không lọc.
4. `ANY li ... SATISFIES` chỉ được thêm **một lần** khi có SKU hoặc số lượng; vì vậy hai điều kiện luôn áp dụng trên cùng một phần tử.
5. Có `LIMIT` giới hạn 100 bản ghi và thứ tự phụ bằng `META(o).id`. Nếu cần phân trang nhiều trang, có thể bổ sung `OFFSET` hoặc thiết kế cursor; phải kiểm tra nhất quán thứ tự và chi phí.
6. Ví dụ dùng SDK trực tiếp, vì vậy phải ánh xạ kết quả về DTO nếu API cần một kiểu Java riêng. Với thao tác CRUD theo document key, repository hoặc `CouchbaseTemplate` vẫn là lựa chọn phù hợp.

### 7.3. Câu SQL++ được tạo ra

Giả sử gọi service với `statuses = {"PAID", "SHIPPED"}`, `postalCode = "700000"`, `tag = "priority"`, `sku = "SKU-42"`, `minItemQuantity = 2`. Logic truy vấn sau khi dựng tương đương:

```sql
SELECT META(o).id AS documentId,
       o.order_number AS orderNumber,
       o.status, o.shipping, o.tags, o.line_items
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenant_id = $tenantId
  AND o.status IN $statuses
  AND o.shipping.postal_code = $postalCode
  AND ANY t IN o.tags SATISFIES t = $tag END
  AND ANY li IN o.line_items
      SATISFIES li.sku = $sku AND li.quantity >= $minQuantity
      END
ORDER BY o.created_at_ms DESC, META(o).id DESC
LIMIT $limit;
```

Để kiểm tra cả dấu ngoặc và tham số thực tế, cần chạy thử với dữ liệu có cùng tên SKU trên nhiều dòng và dữ liệu thuộc ít nhất hai tenant. Kết quả tìm kiếm không chỉ phụ thuộc câu `WHERE`; chỉ mục SQL++, trạng thái document và mức nhất quán truy vấn cũng quyết định dữ liệu quan sát được.

## 8. Index cho trường lồng nhau và mảng

Secondary index phải chỉ rõ **tên field JSON đã lưu**, không phải tên thuộc tính Java trong DTO:

```sql
-- Khi thường lọc tenant + status + thời gian.
CREATE INDEX ix_orders_tenant_status_created
ON `shop`.`sales`.`orders`(
    tenant_id, status, created_at_ms
);

-- Khi thường lọc tenant + mã bưu chính + thời gian.
CREATE INDEX ix_orders_tenant_postal_created
ON `shop`.`sales`.`orders`(
    tenant_id, shipping.postal_code, created_at_ms
);
```

Với `ANY` trên mảng, cân nhắc **array index** nếu truy vấn đủ thường xuyên và có lượng dữ liệu lớn:

```sql
-- Index phần tử của mảng tags.
CREATE INDEX ix_orders_tenant_tags
ON `shop`.`sales`.`orders`(
    tenant_id,
    DISTINCT ARRAY t FOR t IN tags END
);

-- Index SKU từ từng object trong mảng line_items.
CREATE INDEX ix_orders_tenant_item_sku
ON `shop`.`sales`.`orders`(
    tenant_id,
    DISTINCT ARRAY li.sku FOR li IN line_items END
);
```

Đây là **ví dụ thiết kế ban đầu**, không bảo đảm cả truy vấn kết hợp trong phần 7 đều được index tối ưu. Các biểu thức `ANY` trong `WHERE` cần tương thích với expression của array index; khi bổ sung `quantity` vào điều kiện phần tử, có thể cần index khác hoặc thiết kế index gồm cả biểu thức phục vụ truy vấn.

Kiểm tra kế hoạch bằng:

```sql
EXPLAIN SELECT META(o).id
FROM `shop`.`sales`.`orders` AS o
WHERE o.tenant_id = "store-01"
  AND ANY li IN o.line_items
      SATISFIES li.sku = "SKU-42"
      END;
```

Quan sát index được chọn, số document/index entry cần đọc, việc sử dụng array index, Fetch và Sort. Thử từng tổ hợp phổ biến: chỉ tenant, tenant + status, tenant + postal code, tenant + tag, tenant + SKU, và kết hợp tất cả. Một index tốt cho truy vấn lọc trên một nhánh chưa chắc tối ưu khi mọi bộ lọc có mặt.

Index có chi phí dung lượng và cập nhật; tránh tạo tất cả tổ hợp index một cách máy móc. TTL của document có thể làm dữ liệu biến mất giữa hai lượt tìm; các mutation cũng có thể chưa xuất hiện ngay trong chỉ mục SQL++ theo mức scan consistency mặc định. Đối với yêu cầu đọc ngay sau ghi, xem xét scan consistency thích hợp và đánh đổi độ trễ.

## 9. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `shipping.postalCode` khi document lưu `shipping.postal_code` | SQL++ đọc tên JSON, không tự suy tên Java | Kiểm tra `@Field`, JSON thật và đường dẫn SQL++ |
| Dùng `line_items.sku = $sku` như scalar | `line_items` là mảng object | Dùng `ANY li IN ... SATISFIES ... END` |
| Dùng hai `ANY` riêng cho SKU và quantity | Hai điều kiện có thể khớp hai item khác nhau | Ghép cả hai phép so sánh trong **cùng một** `SATISFIES` |
| Nhầm `o.status IN $statuses` với tìm `$tag` trong `o.tags` | Hai hướng membership khác nhau | Phân biệt scalar và array ngay từ hợp đồng dữ liệu |
| Xem `null`, chuỗi rỗng và `[]` là một | Làm thay đổi semantics của API | Quy định rõ cách xử lý từng trạng thái |
| Bỏ điều kiện `tenant_id` khi mọi filter rỗng | Có thể lộ kết quả ngoài tenant | Giữ tenant ở mức điều kiện bắt buộc |
| Nối tên field/giá trị request vào SQL++ | Có thể sinh identifier tùy ý và nguy cơ injection | Whitelist identifier, bind mọi giá trị |
| Dùng `EVERY` để yêu cầu mảng không rỗng | `EVERY` trên mảng rỗng là `TRUE` | Chọn `ANY AND EVERY` nếu đúng nghiệp vụ |
| Tạo index trên tên property Java | Index có thể không phù hợp JSON lưu trữ | Dùng field path thực và `EXPLAIN` |
| Trang sâu với `OFFSET` lớn | Chi phí lớn và kết quả có thể thay đổi giữa các lần đọc | Giới hạn trang, dùng thứ tự ổn định, cân nhắc cursor |

## 10. Kiểm thử tích hợp quan trọng

Để phát hiện lỗi lọc mảng và điều kiện tùy chọn, cần chuẩn bị dữ liệu thật trong Couchbase, ít nhất gồm:

| Đơn | Tenant | Status | Postal | Tags | Line items | Trường hợp |
| --- | --- | --- | --- | --- | --- | --- |
| A | store-01 | PAID | 700000 | `["priority"]` | `[{SKU-42, 2}]` | Khớp mọi bộ lọc |
| B | store-01 | PAID | 700000 | `["priority"]` | `[{SKU-42, 1}, {SKU-99, 5}]` | Không khớp **cùng item** với yêu cầu SKU-42, minQty=2 |
| C | store-01 | NEW | 700000 | `[]` | `[]` | Không khớp tag/SKU |
| D | store-01 | SHIPPED | *missing* | `["priority"]` | `[{SKU-42, 3}]` | Không khớp postal |
| E | store-02 | PAID | 700000 | `["priority"]` | `[{SKU-42, 4}]` | Không được xuất hiện vì sai tenant |

Các ca kiểm thử nên bao gồm:

1. **Không truyền bộ lọc tùy chọn:** chỉ trả đơn trong tenant hiện tại, vẫn chịu `LIMIT`.
2. **Mỗi bộ lọc riêng:** postal, statuses, tag, SKU, minQuantity, thời gian; đối chiếu đúng các document.
3. **Kết hợp nhiều bộ lọc:** tất cả nhánh `AND` cùng thỏa mới được trả về.
4. **Same-element:** bản ghi B bị loại với `SKU-42` và `minQty=2` dù một dòng khác có quantity cao.
5. **Biên thời gian:** `createdFromInclusive` được lấy khi đúng bằng mốc; `createdBeforeExclusive` bị loại khi đúng bằng mốc.
6. **Đầu vào không hợp lệ:** `statuses=[]`, status không cho phép, `minItemQuantity=0`, khoảng thời gian đảo, `limit>100`.
7. **JSON đa trạng thái:** `MISSING`, `NULL`, `[]` và object lồng không có trường con.
8. **Bảo vệ tenant:** bản ghi E không xuất hiện kể cả khi mọi bộ lọc khác khớp.
9. **Index và phân trang:** chạy `EXPLAIN`, đo thời gian trên dữ liệu đại diện và kiểm tra thứ tự ổn định.

Một lưu ý về chức năng `count`: truy vấn đếm phải dùng **chính xác cùng bộ lọc** như truy vấn lấy dữ liệu, nhưng không áp dụng `LIMIT`/`OFFSET` của trang. Trong tình huống dữ liệu bị cập nhật hoặc TTL hết hạn giữa hai truy vấn, `count` và danh sách có thể phản ánh hai thời điểm khác nhau; nếu nghiệp vụ yêu cầu snapshot nhất quán, phải thiết kế giải pháp phù hợp thay vì giả định hai câu query độc lập là một giao dịch.

## 11. Bài tập tự luyện

**Bài 1 — Lựa chọn toán tử.** Viết SQL++ cho ba yêu cầu:

- `status` phải thuộc `["PAID", "SHIPPED"]`.
- `tags` phải chứa chuỗi `"mobile"`.
- Một dòng trong `line_items` phải có SKU `"SKU-42"` và `quantity >= 2`.

**Đáp án tham khảo:**

```sql
WHERE o.status IN ["PAID", "SHIPPED"]
  AND ANY t IN o.tags SATISFIES t = "mobile" END
  AND ANY li IN o.line_items
      SATISFIES li.sku = "SKU-42" AND li.quantity >= 2
      END
```

**Bài 2 — Phát hiện nhầm item.** Cho `line_items = [{sku:"A", quantity:1}, {sku:"B", quantity:9}]`. Giải thích vì sao hai biểu thức `ANY` độc lập có thể báo đơn khớp yêu cầu SKU A, số lượng từ 5; sửa lại bằng một `ANY`.

**Bài 3 — Hợp đồng đầu vào.** Phân tích `statuses=null`, `statuses=[]`, `statuses=["PAID"]`, `tag=" "` và `minItemQuantity=0`. Chỉ ra trường hợp nào bỏ bộ lọc, trường hợp nào hợp lệ, trường hợp nào cần trả lỗi theo ví dụ.

**Bài 4 — Truy vấn “mọi phần tử”.** Viết truy vấn chỉ lấy các đơn có mảng `line_items` **không rỗng** và mọi phần tử đều có `quantity > 0`. Giải thích vì sao không chọn `EVERY` đơn lẻ.

## 12. Ghi nhớ và nguồn tra cứu

**Trường lồng nhau** được đọc theo đường dẫn JSON; **`IN`** kiểm tra giá trị scalar thuộc một tập; **`ANY`** kiểm tra phần tử của mảng; các điều kiện trên cùng phần tử phải nằm trong **cùng một `SATISFIES`**. Với bộ lọc tùy chọn, mỗi trạng thái đầu vào cần semantics rõ ràng trước khi dựng SQL++. Điều kiện phân quyền bắt buộc phải luôn tồn tại và mọi giá trị phải được bind bằng tham số.

Nguồn tài liệu:

- [Spring Data Couchbase — Object Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/object-mapping.html).
- [Spring Data Couchbase — QueryCriteria API](https://docs.spring.io/spring-data/couchbase/reference/api/java/org/springframework/data/couchbase/core/query/QueryCriteria.html).
- [Spring Data Couchbase — Template API](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html).
- [Couchbase SQL++ — Collection Operators (IN, ANY, EVERY)](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/collectionops.html).
- [Couchbase SQL++ — Array Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/arrayfun.html).
- [Couchbase Server — Indexing Arrays](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing-arrays.html).
- [Couchbase Java SDK — Query Operations](https://docs.couchbase.com/java-sdk/current/howtos/n1ql-queries-with-sdk.html).
