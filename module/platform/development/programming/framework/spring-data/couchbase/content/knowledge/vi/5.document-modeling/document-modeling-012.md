# Tài liệu cũ, trường mới và khả năng đọc dữ liệu không đồng nhất trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao trong **cùng một collection Couchbase** có thể đồng thời tồn tại nhiều phiên bản JSON khác nhau.
2. Phân biệt khả năng **đọc dữ liệu cũ bằng mã mới** với khả năng **đọc dữ liệu mới bằng mã cũ** khi triển khai nhiều phiên bản ứng dụng.
3. Nhận diện các kiểu thay đổi schema: thêm field, đổi tên, đổi kiểu, thay cấu trúc lồng nhau, đổi type alias, đổi document key và tách collection.
4. Thiết kế **reader tương thích**, quy tắc mặc định có căn cứ, DTO chuẩn hóa, constructor an toàn và custom converter khi cần.
5. Thực hiện quy trình **expand → migrate → contract** có kiểm soát, không làm mất dữ liệu trong giai đoạn ứng dụng cũ và mới chạy song song.
6. Viết SQL++ phát hiện document cũ, dữ liệu sai kiểu, field `MISSING`/`NULL` và thống kê tiến độ migration.
7. Xử lý các hệ quả với **CAS, TTL, index, repository, CouchbaseTemplate, transaction và reactive API**.
8. Lập ma trận kiểm thử và tiêu chí cutover để thay đổi mô hình document mà không phá vỡ việc đọc dữ liệu hiện hữu.

Bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase qua Spring Data document mapping, repository, `CouchbaseTemplate` và SQL++. Việc Couchbase cho phép JSON linh hoạt mang lại khả năng thay đổi schema từng bước, nhưng **không có nghĩa Spring Data tự chuyển mọi document cũ thành entity mới đúng nghiệp vụ**.

## 1. Vấn đề cốt lõi: code mới không đồng nghĩa dữ liệu đã mới

Giả sử ứng dụng bán hàng lưu Product dưới key `product::coffee250` trong collection `shop.catalog.products`.

**Phiên bản V1**, trước khi có quy ước đặt tên mới:

~~~json
{
  "name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "active": true
}
~~~

**Phiên bản V2**, sau khi bổ sung currency, schema version và đổi tên field:

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "currency": "VND",
  "active": true,
  "schema_version": 2
}
~~~

Trong thời gian triển khai, collection có thể chứa đồng thời:

| Nhóm document | Field tên sản phẩm | `currency` | `schema_version` |
| --- | --- | --- | --- |
| V1 gốc | `name` | MISSING | MISSING |
| V1 có version | `name` | MISSING | `1` |
| Đang chuyển đổi | Cả `name` và `display_name` | Có thể đã có | `1` hoặc `2`, tùy quy trình |
| V2 chuẩn | `display_name` | `"VND"` | `2` |
| Dữ liệu lỗi | Thiếu tên hoặc sai kiểu | `null`, số, v.v. | Giá trị không hợp lệ |

Bảng này cho thấy schema không thể suy ra **chỉ từ ngày triển khai**. Dữ liệu từ import, SDK khác, retry, job cũ hoặc bản sao lưu có thể tạo thêm biến thể.

Một số ứng dụng tiếp tục đọc bình thường trong nhiều tháng vì các field cũ chưa bị truy cập. Khi deploy class mới có constructor yêu cầu `displayName != null`, lỗi mới xuất hiện: **đây là vấn đề tương thích dữ liệu, không phải chỉ là lỗi constructor**.

~~~mermaid
flowchart TD
    A["Collection Product"] --> V1["V1: name, price_vnd"]
    A --> P["Chuyển tiếp: name + display_name"]
    A --> V2["V2: display_name, currency, schema_version"]
    V1 --> R["Reader tương thích"]
    P --> R
    V2 --> R
    R --> M["ProductView chuẩn hóa cho miền nghiệp vụ"]
~~~

### 1.1. Schema của JSON và schema của Java là hai hợp đồng khác nhau

Couchbase không ép mọi document cùng collection có một tập field cố định. Trong Java, entity và constructor lại có kiểu cụ thể:

~~~java
@Field("display_name")
private String displayName;
~~~

Annotation trên chỉ nói: **nếu ánh xạ property này, tên JSON được dùng là `display_name`**. Nó **không tự đọc cả `name` và `display_name`**, cũng không tự chuyển hàng triệu document cũ sang schema mới.

Tương tự, thêm:

~~~java
@Field("currency")
private String currency;
~~~

không tự ghi `"VND"` vào tài liệu cũ. Một property Java có `null` còn có thể tương ứng với **JSON field MISSING hoặc JSON literal `null`**, nên cần chính sách rõ ràng trước khi chọn default.

## 2. Hai chiều tương thích phải được kiểm tra riêng

Không nên nói chung chung “thay đổi này backward compatible” khi không chỉ rõ ai đang đọc dữ liệu nào.

| Tình huống | Câu hỏi kiểm thử | Ý nghĩa |
| --- | --- | --- |
| **Reader mới → document cũ** | V2 code có đọc được Product V1 không? | Tương thích đọc dữ liệu lịch sử |
| **Reader cũ → document mới** | V1 code có đọc được Product V2 không? | Tương thích khi rolling deploy/rollback |
| **Writer mới → reader cũ** | Field mới có làm V1 code lỗi hoặc đọc sai không? | An toàn trong thời gian hai phiên bản chạy |
| **Writer cũ → reader mới** | V1 writer vẫn ghi `name`, V2 reader có xử lý không? | An toàn trước khi loại writer cũ |
| **Reader mới → dữ liệu lỗi** | `currency:null` hoặc `price_vnd:"150000"` thì sao? | Phát hiện lỗi thay vì ép kiểu tùy tiện |

**Một thay đổi thêm field thường ít rủi ro hơn việc xóa/đổi tên field** nếu reader cũ chấp nhận field lạ. Nhưng điều đó còn phụ thuộc constructor, converter, tính năng polymorphism và việc reader cũ có ghi lại toàn bộ document hay không.

Cảnh báo quan trọng: **reader cũ đọc được field mới không có nghĩa writer cũ bảo toàn field mới**. Một ứng dụng cũ có thể đọc JSON chứa `currency` vào class không khai báo property này rồi gọi `save` toàn bộ entity; khi đó field lạ có nguy cơ bị loại khỏi document. Đây là một lý do phải kiểm thử *read–modify–write*, không chỉ kiểm thử đọc.

## 3. Phân loại các thay đổi schema theo rủi ro

| Thay đổi | Ví dụ | Rủi ro chủ yếu | Cách triển khai khuyến nghị |
| --- | --- | --- | --- |
| Thêm field optional | `tags: []` | Reader cũ bỏ qua hoặc writer cũ xóa field | Đọc tương thích, kiểm thử round-trip |
| Thêm field bắt buộc | `currency` | V1 thiếu, constructor V2 từ chối | Có default hợp lệ hoặc migration trước |
| Đổi tên | `name` → `display_name` | Query, index, mapper cũ không thấy tên mới | Đọc cả hai trong giai đoạn chuyển tiếp |
| Đổi kiểu | `price_vnd` string → number | Converter lỗi/ép sai | Validate và migration có kiểm soát |
| Đổi cấu trúc | `address` string → object | Mapping class khác hoàn toàn | Converter/DTO hoặc field mới song song |
| Thay enum | `PENDING` → `AWAITING_REVIEW` | Reader cũ không hiểu giá trị mới | Mở rộng reader trước khi writer phát ra giá trị mới |
| Đổi `_class` / alias | FQCN → `@TypeAlias("product")` | Mapper không resolve type cũ | Đăng ký kiểu cũ, migration riêng |
| Đổi key | `coffee250` → `product::coffee250` | KV/reference không tìm được | Copy document + chuyển reference |
| Tách collection | `shop.catalog.products` → nơi khác | Repository trỏ sai keyspace | Đường đọc tương thích, migration có cutover |
| Thay TTL | Product không TTL → hết hạn | Dữ liệu lịch sử biến mất | Review retention, backup và expiry |

Mỗi thay đổi cần đi kèm **hợp đồng đọc/ghi** và **kiểm thử dữ liệu thực**. Không gom toàn bộ vào một migration lớn nếu có thể tách rủi ro theo giai đoạn.

## 4. MISSING, NULL, giá trị mặc định và dữ liệu sai kiểu

Xét bốn document:

~~~json
{"name":"A","price_vnd":100000}
~~~

~~~json
{"name":"B","price_vnd":100000,"currency":null}
~~~

~~~json
{"name":"C","price_vnd":100000,"currency":"VND"}
~~~

~~~json
{"name":"D","price_vnd":"100000","currency":"VND"}
~~~

Chúng không tương đương:

- A: `currency` **MISSING**.
- B: `currency` có mặt nhưng **NULL**.
- C: `currency` hợp lệ.
- D: `price_vnd` tồn tại nhưng **sai kiểu** nếu contract yêu cầu JSON number.

Trong SQL++ của Couchbase:

| Điều kiện | MISSING | NULL | Giá trị hợp lệ |
| --- | :---: | :---: | :---: |
| `x IS MISSING` | TRUE | FALSE | FALSE |
| `x IS NULL` | FALSE | TRUE | FALSE |
| `x IS VALUED` | FALSE | FALSE | TRUE |
| `x IS NOT MISSING` | FALSE | TRUE | TRUE |
| `x IS NOT NULL` | TRUE | FALSE | TRUE |

Dễ nhầm nhất: **`IS NOT NULL` vẫn đúng với MISSING**. Nếu muốn field vừa tồn tại vừa khác null, dùng `IS VALUED`.

Hai hàm quan trọng:

~~~sql
IFMISSING(p.currency, "VND")
IFMISSINGORNULL(p.currency, "VND")
~~~

- `IFMISSING` chỉ thay khi field **không tồn tại**; giữ nguyên `null`.
- `IFMISSINGORNULL` thay cả **MISSING lẫn NULL**.
- Cả hai không tự nhận biết dữ liệu sai kiểu (`currency: 123`).

**Quy tắc nghiệp vụ của ví dụ:** toàn bộ Product V1 được biết chắc định giá bằng VND. Vì vậy, có thể suy `"VND"` nếu document **được xác nhận thuộc V1 và currency MISSING**. Nếu document V2 có `currency:null`, đó là dữ liệu lỗi cần điều tra; không được âm thầm biến thành VND.

### 4.1. Mặc định ở đâu?

| Cấp áp dụng | Ví dụ | Có thay JSON gốc không? |
| --- | --- | --- |
| Truy vấn/DTO đọc | `IFMISSING(currency, "VND")` | Không |
| Domain normalizer | Reader V1 thiếu currency → `"VND"` | Không |
| Factory tạo entity mới | `Product.create(...)` gán currency | Chỉ cho document mới nếu được lưu |
| Data migration | `UPDATE ... SET currency="VND"` | Có |

Không được nhìn API trả `"currency":"VND"` rồi kết luận tất cả document dưới Couchbase đã có field này. Nếu default chỉ nằm ở Java, query SQL++ theo `currency` có thể không thấy các document cũ.

## 5. Giới hạn của @Field, constructor và record

### 5.1. @Field không đọc hai tên JSON tự động

Ví dụ entity V2:

~~~java
import org.springframework.data.couchbase.core.mapping.Field;

@Field("display_name")
private String displayName;
~~~

Spring Data dùng `display_name` cho property này, nhưng document chỉ có `name` không cung cấp giá trị tương ứng. Các cách giải quyết:

1. **Tạm ánh xạ cả hai field** bằng hai property riêng để đọc dữ liệu chuyển tiếp.
2. **Đọc JSON gốc**, kiểm tra field presence và chuyển qua DTO chuẩn hóa.
3. **Custom reading converter**, nếu vấn đề đủ phức tạp và API mapping hỗ trợ cơ chế đó.
4. **Migration trước** khi chuyển entity sang chỉ dùng field mới.

Không nên thêm `@Field("display_name")` rồi mặc định đọc V1 vẫn thành công. Cũng không nên dùng một property với hai tên JSON tùy ý nếu mapping framework chưa có cơ chế tường minh.

### 5.2. Constructor có validation có thể làm document cũ không đọc được

~~~java
public record ProductRecord(
    String id,
    String displayName,
    String currency
) {
    public ProductRecord {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Tên bắt buộc");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency bắt buộc");
        }
    }
}
~~~

Trong một record dùng làm entity, canonical constructor cũng tham gia materialization. Nếu mapper không tìm được `display_name` hoặc `currency`, constructor có thể ném lỗi. Không nên sửa bằng cách tự gán:

~~~java
currency = currency == null ? "VND" : currency;
~~~

nếu chưa biết `null` đến từ **field thiếu**, **field có JSON null** hay **schema V2 bị lỗi**. Khi các trạng thái mang ý nghĩa khác nhau, Java wrapper hoặc constructor đơn giản có thể đã làm mất thông tin cần thiết.

### 5.3. Primitive cũng làm mất trạng thái

~~~java
private boolean active;
private int stockQuantity;
~~~

Java primitive luôn có giá trị; `false` hoặc `0` không chứng minh JSON cũ đã lưu chính xác những giá trị đó. Nếu “chưa biết” khác với “không” hoặc “hết hàng”, dùng `Boolean`/`Integer` hoặc mô hình miền tường minh, rồi kiểm chứng converter khi field MISSING/NULL.

`Optional<T>` không tự tạo đủ ba trạng thái MISSING/NULL/VALUE trong persistence; sự khác biệt quan trọng cần được xử lý **trước khi bị thu hẹp xuống một giá trị Java null**.

## 6. Spring Data Couchbase entity đọc tạm hai schema

Giả sử mục tiêu chỉ là **tương thích đọc** trong quá trình chuyển đổi. Một entity tạm có thể khai báo cả field cũ lẫn field mới:

~~~java
package com.example.shop.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long cas;

    // V1 dùng "name", V2 dùng "display_name".
    @Field("name")
    private String legacyName;

    @Field("display_name")
    private String displayName;

    @Field("price_vnd")
    private Long priceVnd;

    @Field
    private Boolean active;

    @Field
    private String currency;

    @Field("schema_version")
    private Integer schemaVersion;

    protected ProductDocument() {}

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getLegacyName() { return legacyName; }
    public String getDisplayName() { return displayName; }
    public Long getPriceVnd() { return priceVnd; }
    public String getCurrency() { return currency; }
    public Integer getSchemaVersion() { return schemaVersion; }
    public Boolean getActive() { return active; }
}
~~~

`@Id` là **document key**, `@Version` là CAS do Couchbase quản lý. Chúng không phải `schema_version`. `@Scope`/`@Collection` chọn nơi lưu entity; bucket `shop` được cấu hình trong kết nối.

Cả `legacyName` và `displayName` được ánh xạ thành **hai field JSON khác nhau**. Đó là cách có chủ đích để nhận cả schema V1/V2 mà không yêu cầu đổi document key.

### 6.1. Repository và DTO chuẩn hóa

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {
}
~~~

Lớp trả về cho business/API có schema thống nhất:

~~~java
package com.example.shop.catalog;

public record ProductView(
    String documentKey,
    String displayName,
    long priceVnd,
    String currency,
    boolean active
) {}
~~~

Service đọc dữ liệu đã ánh xạ và chuẩn hóa **trong phạm vi có thể**:

~~~java
import java.util.Objects;

public ProductView toView(ProductDocument document) {
    Objects.requireNonNull(document, "document");

    int schema = document.getSchemaVersion() == null
        ? 1 : document.getSchemaVersion();

    if (schema != 1 && schema != 2) {
        throw new IllegalStateException("Schema version chưa hỗ trợ");
    }

    String name = document.getDisplayName();
    if (name == null && schema == 1) {
        name = document.getLegacyName();
    }
    if (name == null || name.isBlank()) {
        throw new IllegalStateException("Tên Product không hợp lệ");
    }

    Long price = document.getPriceVnd();
    if (price == null || price < 0) {
        throw new IllegalStateException("Giá không hợp lệ");
    }

    String currency = document.getCurrency();
    if (currency == null && schema == 1) {
        // Chỉ hợp lệ nếu mọi Product V1 chắc chắn định giá VND.
        currency = "VND";
    }
    if (!"VND".equals(currency)) {
        throw new IllegalStateException("Currency chưa hỗ trợ");
    }

    Boolean active = document.getActive();
    if (active == null) {
        throw new IllegalStateException("Thiếu trạng thái active");
    }

    return new ProductView(
        document.getId(), name, price, currency, active
    );
}
~~~

Ví dụ này dùng `ProductDocument` làm **mô hình đọc tạm** và `ProductView` là mô hình chuẩn hóa. Nó hữu ích nếu dữ liệu đã được rà soát và `null` Java đủ cho chính sách nghiệp vụ.

**Giới hạn rõ ràng:** khi `getCurrency() == null`, entity không còn biết chắc JSON đã **MISSING** hay **NULL**. Nếu nghiệp vụ cần từ chối `currency:null` kể cả trên V1, ví dụ trên **chưa đủ an toàn**; phải đọc JSON gốc hoặc dùng converter giữ được thông tin field presence. Tương tự, `schemaVersion == null` không tự chứng minh JSON `schema_version` MISSING — có thể nó được lưu với JSON null.

**Không tái sử dụng read model chuyển tiếp một cách vô điều kiện để `save` lại toàn bộ document.** Việc serialize lại có thể ghi/xóa các field cũ/mới khác nhau tùy converter. Với read model chỉ dùng cho truy vấn, nên tách luồng ghi sang entity/SDK API có hợp đồng rõ ràng và kiểm thử round-trip không mất field lạ.

## 7. Đọc JSON gốc khi phải phân biệt chính xác tình trạng legacy

Couchbase Java SDK cho phép lấy body trước khi Spring Data materialize:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

Collection products = cluster.bucket("shop")
    .scope("catalog")
    .collection("products");

String key = "product::coffee250";
GetResult result = products.get(key);
JsonObject body = result.contentAsObject();

boolean hasSchemaVersion = body.containsKey("schema_version");
boolean hasCurrency = body.containsKey("currency");

Object rawCurrency = hasCurrency ? body.get("currency") : null;

if (!hasCurrency) {
    // MISSING: JSON không có key currency.
} else if (rawCurrency == null) {
    // NULL: key currency có tồn tại nhưng JSON value = null.
} else if (rawCurrency instanceof String currencyCode) {
    // VALUE: còn phải validate whitelist currency hợp lệ.
}

long cas = result.cas(); // Metadata, không nằm trong JSON body.
~~~

Một cách đọc tương thích mạnh hơn là **phân loại schema theo cả version và field presence**, rồi chuyển từng dạng hợp lệ thành một DTO thống nhất. Đoạn code Java 17+ sau cố ý từ chối những trạng thái không được quy định.

### 7.1. ProductView và normalizer có validation

~~~java
import java.math.BigDecimal;
import com.couchbase.client.java.json.JsonObject;

public final class LegacyProductNormalizer {

    private LegacyProductNormalizer() {}

    public static ProductView normalize(String key, JsonObject json) {
        int version;

        if (!json.containsKey("schema_version")) {
            version = 1; // Quy ước: V1 chưa từng lưu version.
        } else {
            Object rawVersion = json.get("schema_version");
            if (!(rawVersion instanceof Number number)) {
                throw new IllegalArgumentException(
                    "schema_version phải là số nguyên");
            }
            try {
                // Không chấp nhận 1.5 bị Number.intValue() cắt thành 1.
                version = new BigDecimal(number.toString()).intValueExact();
            } catch (ArithmeticException | NumberFormatException ex) {
                throw new IllegalArgumentException(
                    "schema_version không phải số nguyên hợp lệ", ex);
            }
            if (version != 1 && version != 2) {
                throw new IllegalArgumentException(
                    "schema_version chưa được hỗ trợ");
            }
        }

        String displayName;
        if (json.containsKey("display_name")) {
            // Không fallback nếu V2 có key nhưng giá trị NULL/sai kiểu.
            displayName = requiredString(json, "display_name");
        } else if (version == 1) {
            displayName = requiredString(json, "name");
        } else {
            throw new IllegalArgumentException(
                "Product V2 thiếu display_name");
        }

        long priceVnd = requiredNonNegativeLong(json, "price_vnd");
        boolean active = requiredBoolean(json, "active");

        String currency;
        if (json.containsKey("currency")) {
            currency = requiredString(json, "currency");
        } else if (version == 1) {
            currency = "VND"; // Chỉ khi hợp đồng V1 đã được xác minh.
        } else {
            throw new IllegalArgumentException("Product V2 thiếu currency");
        }

        if (!"VND".equals(currency)) {
            throw new IllegalArgumentException("Currency chưa hỗ trợ");
        }

        return new ProductView(
            key, displayName, priceVnd, currency, active
        );
    }

    private static String requiredString(JsonObject doc, String field) {
        Object value = doc.get(field);
        if (!(value instanceof String s) || s.isBlank()) {
            throw new IllegalArgumentException(
                field + " phải là chuỗi không rỗng");
        }
        return s;
    }

    private static boolean requiredBoolean(JsonObject doc, String field) {
        Object value = doc.get(field);
        if (!(value instanceof Boolean flag)) {
            throw new IllegalArgumentException(
                field + " phải là boolean");
        }
        return flag;
    }

    private static long requiredNonNegativeLong(
            JsonObject doc, String field) {
        Object value = doc.get(field);
        if (!(value instanceof Number n)) {
            throw new IllegalArgumentException(
                field + " phải là số");
        }

        long result;
        try {
            result = new BigDecimal(n.toString()).longValueExact();
        } catch (ArithmeticException | NumberFormatException ex) {
            throw new IllegalArgumentException(
                field + " phải là số nguyên trong giới hạn long", ex);
        }

        if (result < 0) {
            throw new IllegalArgumentException(field + " không thể âm");
        }
        return result;
    }
}
~~~

Mục đích của normalizer:

- V1 không có `schema_version` được nhận diện theo **hợp đồng dữ liệu cũ**, không theo suy đoán tên Java.
- Field `display_name` **có mặt nhưng NULL** là lỗi, không tự fallback sang `name`.
- V1 thiếu `currency` được mặc định VND có điều kiện; V2 thiếu/null là lỗi.
- Giá string `"150000"` không được ép âm thầm thành số; giá fractional hoặc tràn `long` cũng bị từ chối.
- Chỉ sau khi validation mới trả `ProductView` thống nhất.

Trong hệ thống thật, cần đặt normalizer ở biên persistence, kiểm thử với SDK/JSON codec đúng phiên bản, bảo vệ bộ nhớ/độ sâu JSON và không log toàn bộ payload có dữ liệu cá nhân. Có thể đưa tài liệu lỗi vào **quarantine queue** để xử lý thay vì làm hỏng mọi request.

### 7.2. Vì sao không chỉ gọi repository?

Repository phù hợp khi schema đã ổn định hoặc khi read model hai field đủ để quyết định. Khi cần phân biệt **MISSING so với NULL**, một property Java `String` không đủ thông tin. Có thể dùng một **custom reading converter** để chuyển raw representation trước khi dựng entity, hoặc một **SDK adapter** như ví dụ trên.

Spring Data có cơ chế đăng ký `@ReadingConverter`/`@WritingConverter`, nhưng kiểu đầu vào, cách đăng ký `CustomConversions` và khả năng chuyển **toàn document** phụ thuộc phiên bản Spring Data Couchbase. Không tự giả định một converter `String -> String` sẽ giải quyết đổi tên field JSON; cần thiết kế converter phù hợp với nguồn dữ liệu mà converter thực sự nhận và test trên bản dependency đang chạy.

## 8. SQL++ khảo sát nhiều schema trong cùng collection

Trước migration, phải biết **đã có những dạng JSON nào**, tỷ lệ bao nhiêu và dữ liệu nào sai kiểu. Đừng bắt đầu bằng UPDATE.

### 8.1. Đếm schema version

~~~sql
SELECT IFMISSING(p.schema_version, -1) AS storedVersion,
       COUNT(1) AS total
FROM `shop`.`catalog`.`products` AS p
GROUP BY IFMISSING(p.schema_version, -1);
~~~

Ở đây `-1` chỉ là **sentinel trong báo cáo** cho MISSING. Document có `schema_version:null` được giữ NULL riêng; không dùng `IFMISSINGORNULL` nếu muốn thống kê chính xác.

Dữ liệu sai như `schema_version:"2"` phải được báo cáo riêng; không mặc định chuỗi "2" là số 2.

### 8.2. Đếm tên cũ, tên mới và xung đột

~~~sql
SELECT
    COUNT(1) AS total,
    COUNT(1) FILTER (WHERE p.name IS VALUED) AS hasLegacyName,
    COUNT(1) FILTER (WHERE p.display_name IS VALUED) AS hasNewName
FROM `shop`.`catalog`.`products` AS p;
~~~

Nếu phiên bản Query Service đang dùng không hỗ trợ dạng aggregate `FILTER` của câu minh họa, thay bằng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`, hoặc chạy từng câu `SELECT COUNT(1) ... WHERE ...`.

Cách ít phụ thuộc cú pháp hơn:

~~~sql
SELECT META(p).id AS productKey,
       p.name AS oldName,
       p.display_name AS newName
FROM `shop`.`catalog`.`products` AS p
WHERE p.name IS VALUED
  AND p.display_name IS VALUED
  AND p.name != p.display_name
LIMIT 100;
~~~

Các document có **hai tên khác nhau** phải được điều tra; đừng tùy tiện chọn `display_name` rồi xóa `name` nếu writer cũ vẫn có thể cập nhật field này.

### 8.3. Tìm lỗi dữ liệu

~~~sql
SELECT META(p).id AS productKey,
       p.price_vnd,
       p.currency,
       p.schema_version
FROM `shop`.`catalog`.`products` AS p
WHERE (p.price_vnd IS VALUED AND NOT ISNUMBER(p.price_vnd))
   OR (p.currency IS VALUED AND NOT ISSTRING(p.currency))
   OR p.schema_version IS NULL
LIMIT 100;
~~~

`ISNUMBER` và `ISSTRING` kiểm tra **kiểu** trong SQL++. Điều kiện trên chưa kiểm tra mọi lỗi miền (giá âm, currency lạ, version 99, tên rỗng); cần thêm các phép kiểm tra đúng nghiệp vụ.

### 8.4. Query đọc tương thích tạm thời

~~~sql
SELECT META(p).id AS productKey,
       IFMISSING(p.display_name, p.name) AS effectiveName,
       p.price_vnd AS priceVnd,
       CASE
         WHEN (p.schema_version IS MISSING OR p.schema_version = 1)
              AND p.currency IS MISSING
           THEN "VND"
         ELSE p.currency
       END AS effectiveCurrency
FROM `shop`.`catalog`.`products` AS p
WHERE p.active = TRUE
LIMIT 20;
~~~

`IFMISSING` **không che giá trị `NULL`** của `display_name`. Đây là chủ ý để phát hiện dữ liệu lỗi. Kết quả query là **projection đọc**, không tự thành entity Product hợp lệ, không ghi mặc định vào body.

Nếu màn hình danh sách thường xuyên đọc theo tên, nhớ rằng một filter chỉ dùng `display_name` có thể **bỏ lọt Product V1**. Trong giai đoạn chuyển tiếp, thiết kế query/index theo cả hai dạng hoặc đẩy nhanh migration sau khi đã bảo đảm reader tương thích.

## 9. Chỉ mục cho dữ liệu không đồng nhất

Với schema V2, một index ứng viên:

~~~sql
CREATE INDEX ix_products_display_name
ON `shop`.`catalog`.`products`(display_name);
~~~

Tuy nhiên, một index có **leading key là MISSING** thường không bao gồm document thiếu field đó nếu không có cấu hình thích hợp. Product V1 chỉ có `name` có thể không xuất hiện trong index theo `display_name`, nên query hỗn hợp cần phân tích bằng `EXPLAIN`.

Nếu cần một truy vấn trên cả hai tên trong giai đoạn chuyển đổi, cân nhắc **expression index** theo biểu thức đọc tương thích:

~~~sql
CREATE INDEX ix_products_name_compat
ON `shop`.`catalog`.`products`(
    IFMISSING(display_name, name)
);
~~~

Sau đó kiểm tra planner có thực sự chọn index cho query sử dụng cùng biểu thức hay không; nếu không, điều chỉnh query/index theo phiên bản Server và mẫu truy cập.

Để khảo sát những document thiếu field dùng làm leading key, Couchbase có khả năng `INCLUDE MISSING` cho leading index key ở các phiên bản hỗ trợ:

~~~sql
CREATE INDEX ix_products_schema_scan
ON `shop`.`catalog`.`products`(
    schema_version INCLUDE MISSING
);
~~~

Index tạm này chỉ có ý nghĩa nếu kế hoạch `EXPLAIN` và chi phí xây dựng cho thấy nó cần thiết; không tạo hàng loạt index phục vụ migration rồi quên xóa. Với kiểm kê theo ID đã biết, KV không cần secondary index. Với truy vấn hàng triệu document, cần cân nhắc bộ nhớ, scan consistency, quyền truy cập và ảnh hưởng đến writer.

## 10. Quy trình expand → migrate → contract

Một cách vận hành an toàn là **mở rộng khả năng đọc trước khi thay đổi hợp đồng ghi**.

~~~mermaid
flowchart TD
    A["Khảo sát JSON hiện có"] --> B["EXPAND: reader hiểu V1 + V2"]
    B --> C["Triển khai dần và kiểm thử writer cũ/mới"]
    C --> D["MIGRATE: backfill có điều kiện + đối chiếu"]
    D --> E["Chặn writer V1, chỉ tạo dữ liệu V2"]
    E --> F["CONTRACT: loại logic/field cũ"]
    F --> G["Giám sát & rollback phù hợp"]
~~~

### 10.1. Pha 0 — Khảo sát và đóng băng hợp đồng

Trước khi sửa code:

- Liệt kê field cũ/mới, kiểu JSON, ràng buộc, owner và giá trị mặc định nào được nghiệp vụ chấp nhận.
- Thống kê `MISSING`, `NULL`, sai kiểu, khác version và document không có `_class`.
- Kiểm tra tất cả writer: API chính, batch job, CDC connector, import, SDK khác, consumer và ứng dụng phiên bản cũ.
- Kiểm tra index, TTL, keyspace, quyền truy cập, workload đọc/ghi và dữ liệu có chứa thông tin nhạy cảm.
- Chọn migration idempotent và điểm checkpoint, không làm mới metadata ngoài dự định.

**Đừng sửa dữ liệu trong môi trường thật chỉ vì nhìn thấy một vài mẫu JSON.** Hãy đánh giá phân phối dữ liệu, ngoại lệ và nguyên nhân writer cũ vẫn tồn tại.

### 10.2. Pha 1 — EXPAND: phát hành reader tương thích

- Reader mới chấp nhận V1 và V2 hợp lệ.
- Có quy tắc rõ cho document vừa có `name` vừa có `display_name`.
- Dữ liệu `null`/sai kiểu không bị tự ép.
- Writer mới chưa được bật hành vi mà reader cũ không thể hiểu nếu hệ thống đang rolling deploy.
- Kiểm thử read–modify–write của writer cũ để biết nó có làm mất field lạ không.
- Có metric đếm số lần fallback sang V1 và lỗi normalization.

Việc reader mới hỗ trợ V1 **phải hoàn tất trước** khi bắt đầu tạo Product V2 trên mọi tuyến truy cập yêu cầu tính tương thích.

### 10.3. Pha 2 — Ghi song song/ghi mới có điều kiện

Nếu ứng dụng cũ còn chạy, có thể tạm thời ghi cả hai field `name` và `display_name`, nhưng **chỉ khi bảo đảm chúng luôn đồng nhất** và writer cũ không xóa field mới.

Cách làm này tăng gánh nặng nhất quán, nên chỉ là **giai đoạn chuyển tiếp có thời hạn**, không phải thiết kế vĩnh viễn. Nếu không thể đảm bảo dual-write, cân nhắc giữ writer trên schema cũ cho tới khi mọi reader đã nâng cấp, rồi chuyển atomically theo từng nhóm hoặc qua một adapter sở hữu đường ghi.

Trong một update của **cùng Product document**, có thể cập nhật hai field cùng lúc; nhưng nếu hai dịch vụ sửa cùng document ở các thời điểm khác nhau, vẫn cần CAS và chính sách xung đột.

### 10.4. Pha 3 — MIGRATE: chuẩn hóa dữ liệu lưu trữ

Khi reader đã an toàn, chạy backfill thành batch:

1. Chọn phạm vi document theo keyspace và điều kiện version/field.
2. Loại document sai kiểu hoặc có dữ liệu mâu thuẫn sang hàng đợi xử lý.
3. Chỉ cập nhật document thỏa **điều kiện rõ ràng**, không ghi đè field V2 đã tồn tại.
4. Bảo toàn expiry theo chính sách.
5. Ghi checkpoint/log số lượng và trạng thái từng batch; bảo vệ key/PII trong log.
6. Chạy lại một batch phải cho kết quả hợp lệ (idempotent).
7. Đối chiếu số document V1/V2, record lỗi, thông tin nghiệp vụ và retry/collision.

### 10.5. Pha 4 — CONTRACT: ngừng hỗ trợ schema cũ

Chỉ xóa field cũ và code đọc V1 khi:

- Không còn writer V1, kể cả job chạy theo lịch hoặc consumer có backlog.
- Số document V1 còn lại bằng 0 **hoặc** đã có ngoại lệ được phê duyệt.
- Mọi query/index/API đã chuyển sang field mới.
- Rollback ứng dụng cũ không còn là phương án cần giữ, hoặc reader rollback được chuẩn bị để đọc V2.
- Có backup/snapshot và kế hoạch phục hồi phù hợp.

**Contract quá sớm** là nguyên nhân phổ biến khiến rolling deploy thất bại hoặc rollback gây sự cố dù migration đã “chạy thành công”.

## 11. Ví dụ migration SQL++ theo điều kiện

### 11.1. Backfill chỉ document V1 rõ ràng

Câu sau chỉ minh họa cho trường hợp dữ liệu V1 đã được xác nhận là VND và `price_vnd` phải là số không âm.

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
SET p.display_name = p.name,
    p.currency = "VND",
    p.schema_version = 2
WHERE (p.schema_version IS MISSING OR p.schema_version = 1)
  AND p.display_name IS MISSING
  AND p.currency IS MISSING
  AND ISSTRING(p.name)
  AND p.name != ""
  AND ISNUMBER(p.price_vnd)
  AND p.price_vnd >= 0;
~~~

Ý nghĩa điều kiện:

- Không đụng document đã có `display_name` hoặc `currency`, tránh ghi đè thay đổi mới.
- Không đổi document có `currency:null` — đó là dữ liệu cần xử lý riêng.
- Không âm thầm ép string price sang number.
- Đánh dấu version `2` **chỉ trong cùng mutation** đã thêm đủ các field cần thiết.

Câu lệnh chưa xử lý toàn bộ biến thể (ví dụ V1 thiếu `active`, `schema_version:null`, `name:null`, hay JSON có type alias không hợp lệ). Phải kiểm kê những biến thể đó trước khi migration toàn bộ.

### 11.2. Vì sao migration phải idempotent?

Sau lần đầu, document phù hợp có `schema_version=2`, `display_name` và `currency`. Chạy lại câu lệnh trên **không cập nhật lại** document ấy. Đó là điều kiện tốt cho batch được retry sau lỗi mạng hoặc restart.

Tuy nhiên, **idempotent ở mức dữ liệu không tự ngăn race**. Nếu writer cũ vẫn ghi `name` vào cùng document, hoặc writer mới sửa giá khi backfill đang chạy, có thể cần CAS, ownership đường ghi, staging hoặc workflow có checkpoint/đối chiếu.

### 11.3. Loại field cũ chỉ sau cutover

Khi V2 đã là chuẩn và các reader/writer cũ ngừng hoạt động:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
UNSET p.name
WHERE p.schema_version = 2
  AND p.display_name IS VALUED
  AND p.name IS NOT MISSING;
~~~

`UNSET p.name` làm field trở thành **MISSING**; nó khác `SET p.name = NULL`. Với các document có `name` và `display_name` không trùng, nên hòa giải trước khi xóa field cũ.

### 11.4. Cảnh báo quan trọng: SQL++ UPDATE và TTL

Theo tài liệu Couchbase Server, SQL++ `UPDATE` có tham số request-level **`preserve_expiry`**. Khi không chỉ định expiry và tham số này là `false`, expiry có thể được đưa về `0`/mặc định của bucket hoặc collection; nếu là `true`, expiry hiện hữu được bảo toàn.

Vì vậy, **migration có thể vô tình làm sống lâu hơn các document tạm** nếu không xử lý preserve expiry. Hãy cấu hình query options hoặc dùng cú pháp cập nhật metadata phù hợp với phiên bản Server/SDK rồi kiểm chứng bằng document thử nghiệm có TTL ngắn. Đừng suy rằng tất cả đường ghi (KV, sub-document, SQL++) tự bảo toàn TTL giống nhau.

Trong hệ thống có retention pháp lý, expired document phải được xử lý theo chính sách lưu trữ; không “cứu” dữ liệu bằng cách đổi TTL tùy tiện.

## 12. CAS và xung đột với writer đang chạy

Giả sử request A đang sửa Product V1, còn migration B chuyển Product sang V2:

~~~mermaid
sequenceDiagram
    participant A as API writer cũ
    participant DB as Couchbase
    participant B as Migration
    A->>DB: Đọc Product CAS=10
    DB-->>A: V1, name="Cà phê"
    B->>DB: UPDATE thêm display_name, currency, version
    DB-->>B: Thành công, CAS=11
    A->>DB: Save toàn bộ snapshot dựa trên CAS=10
    DB-->>A: Conflict nếu có kiểm tra CAS
~~~

Nếu API dùng `@Version`, CAS có thể giúp **phát hiện** thao tác cũ dựa trên snapshot trước migration. Nếu API không dùng CAS và ghi nguyên document, nó có thể **ghi đè schema V2 bằng V1**, làm mất field mới.

Các phương án:

- **Cập nhật writer trước** hoặc tạm đóng đường ghi cũ.
- Dùng `@Version` và cơ chế retry: **đọc lại → đánh giá lại nghiệp vụ → ghi lại**, không gọi `save` snapshot cũ nhiều lần.
- Với cập nhật rất nhỏ, cân nhắc **sub-document operations** hoặc mutation có điều kiện để tránh ghi lại toàn body; vẫn phải bảo vệ invariant.
- Khi một migration cần nhiều document cùng commit, cân nhắc transaction đa document; nhưng không tạo transaction quá lớn cho hàng triệu document.

Một lệnh `UPDATE` trên mỗi document có tính nguyên tử của mutation document, **không tự bảo đảm mọi API writer trên cluster tuân hợp đồng mới**. CAS, tính idempotent và kế hoạch cutover vẫn là yêu cầu riêng.

## 13. Type discriminator, @TypeAlias và schema_version không giống nhau

Spring Data Couchbase có thể lưu type information như:

~~~json
{
  "_class": "com.example.shop.catalog.ProductDocument",
  "display_name": "Cà phê",
  "schema_version": 2
}
~~~

Các giá trị khác nhau:

| Metadata/field | Mục đích | Có tự migrate schema không? |
| --- | --- | --- |
| Couchbase document key | Định danh document trong collection | Không |
| CAS / `@Version` | Optimistic locking | Không |
| `_class` | Type hint của Spring Data mapping | Không |
| `@TypeAlias("product")` | Đặt tên kiểu tương đối ổn định | Không |
| JSON `schema_version` | Hợp đồng định dạng dữ liệu do ứng dụng quản lý | Không, chỉ mô tả version |
| `created_at` | Thời gian nghiệp vụ/audit | Không |

Đổi package `com.old.Product` → `com.new.Product` có thể làm document cũ chứa `_class` theo tên Java cũ. Thêm `@TypeAlias` cho class mới **không tự cập nhật tất cả giá trị `_class` đã lưu**. Phải chuẩn bị mapping context/converter hiểu alias cũ hoặc migration riêng.

**Không dùng `_class` thay `schema_version`**: cùng một loại Product có thể có nhiều schema JSON theo thời gian. Và `schema_version=2` không bảo đảm `_class` đúng; hai vấn đề phải kiểm tra độc lập.

### 13.1. Document key và collection cũng không tự thay đổi

Nếu đổi `product::coffee250` thành `catalog-product::coffee250`, thao tác sửa field JSON `id` không đổi document key. Phải tạo document ở key mới, chuyển reference và xóa key cũ có kiểm soát.

Nếu đổi từ `shop.catalog.products` sang collection mới, cần tính đến `@Scope`, `@Collection`, quyền truy cập và reader cũ. **Mọi document trong cùng collection có key độc lập với JSON schema**, vì vậy migration chỉ sửa field không giải quyết bài toán di chuyển keyspace.

## 14. Vì sao chỉ kiểm thử findById là chưa đủ?

`findById("product::coffee250")` thường dùng KV theo document key, không cần secondary index. Một entity đọc thành công bằng KV **không chứng minh SQL++ query theo field mới đã đúng**.

Ví dụ:

~~~sql
SELECT META(p).id AS productKey, p.display_name
FROM `shop`.`catalog`.`products` AS p
WHERE p.display_name = $name;
~~~

Product V1 chỉ có `name` có thể không được trả về. Nếu giao diện danh sách dùng query trên, người dùng thấy thiếu sản phẩm dù trang chi tiết theo key vẫn xem được.

Cần kiểm thử ba đường:

1. **KV/read entity:** repository `findById`, template `findById`, SDK `get`.
2. **SQL++ query:** filter, projection, sort, pagination, index, query consistency.
3. **Read–modify–write:** đọc document cũ, cập nhật một field, ghi lại và kiểm tra field không liên quan vẫn được bảo toàn.

Projection SQL++ cũng có thể thiếu metadata ID/CAS/type hint cần cho Spring Data materialize entity đầy đủ. Với query trả ít field, dùng DTO/projection phù hợp thay vì dựng root entity với constructor yêu cầu nhiều field.

### 14.1. Repository query dựa trên tên property Java

Nếu entity có:

~~~java
@Field("display_name")
private String displayName;
~~~

Derived query `findByDisplayName(...)` lọc theo field JSON được mapping. Nó không tự OR thêm field `name` của V1. Nếu cần query tương thích:

- Dùng `@Query` tường minh với biểu thức legacy/new (và index phù hợp);
- Hoặc migration dữ liệu trước khi dùng derived query đơn giản;
- Hoặc read model tách riêng phục vụ danh sách.

`CouchbaseTemplate` cũng không tự đoán hai tên field; nó dùng mapping metadata của entity. Reactive API có cùng yêu cầu về cấu trúc dữ liệu, chỉ khác cách điều phối I/O.

## 15. Rollback và triển khai nhiều phiên bản

Để có rollback an toàn, phải trả lời câu hỏi: **mã cũ sau rollback sẽ gặp những document nào?**

Nếu V2 đã ghi `display_name` nhưng xóa `name`, V1 code chỉ biết `name` có thể không đọc được. Nếu V2 đã chuyển `price_vnd` sang một cấu trúc Money object, V1 code có thể lỗi converter hoặc tính giá sai.

Một trình tự phát hành thực tế:

| Mốc | Reader | Writer | Dữ liệu |
| --- | --- | --- | --- |
| Trước nâng cấp | V1 | V1 | V1 |
| Expand | V1/V2 reader cùng tồn tại | Chủ yếu V1-compatible | V1 và vài dạng chuyển tiếp đã kiểm thử |
| Đổi writer | V2 reader trên mọi tuyến | V2, có cơ chế tương thích cũ nếu cần rollback | V1/V2 |
| Backfill | V2 | V2 | V1 giảm dần |
| Cutover | V2 | V2 | V2 là chuẩn |
| Contract | V2-only | V2-only | Field cũ được loại sau xác nhận |

Không phải hệ thống nào cũng cần dual-write; nếu deploy đồng loạt và tạm ngừng ghi an toàn, quy trình có thể đơn giản hơn. Nhưng nếu có consumer chạy chậm, các job theo lịch hoặc ứng dụng mobile cũ, giai đoạn tương thích có thể dài hơn dự kiến.

### 15.1. Tương thích event/CDC cũng quan trọng

Một job CDC hoặc consumer đẩy dữ liệu sang analytics có thể tiếp tục xuất `name` trong khi API mới chỉ đọc `display_name`. Vì vậy, ngoài repository, hãy kiểm kê:

- Consumer đang deserialize payload JSON;
- Pipeline CDC và index/report;
- Export CSV/JSON và backup restore;
- Batch job chưa nâng version;
- Các service dùng Couchbase Java SDK trực tiếp.

Một schema mới chỉ được xem là ổn định khi **mọi đường ghi/đọc liên quan** đã được kiểm thử, không chỉ service chính.

## 16. Ma trận kiểm thử tính tương thích và migration

Một bộ fixture nên bao gồm **JSON body thật** từ mỗi phiên bản, không chỉ instance Java tạo bằng constructor mới.

| Fixture | Dữ liệu JSON | Kỳ vọng |
| --- | --- | --- |
| V1 thiếu version | `name`, `price_vnd`, không currency/version | Reader nhận V1 theo hợp đồng |
| V1 version=1 | `name`, `schema_version:1` | Reader nhận V1 |
| V2 chuẩn | `display_name`, `currency:"VND"`, version=2 | Reader nhận V2 |
| Chuyển tiếp cùng giá trị | Có `name` và `display_name` giống nhau | Reader chọn nhất quán |
| Chuyển tiếp xung đột | Hai tên khác nhau | Báo lỗi/đưa vào hòa giải |
| V2 thiếu display_name | Chỉ có `name`, version=2 | Không âm thầm fallback |
| V2 currency:null | Key tồn tại, JSON null | Báo lỗi riêng với MISSING |
| Schema version null | `schema_version:null` | Không mặc định là V1 |
| Giá string | `price_vnd:"150000"` | Từ chối hoặc converter được phê duyệt |
| Giá fractional | `price_vnd:150000.5` | Không làm tròn âm thầm |
| Giá âm | `price_vnd:-1` | Báo lỗi miền |
| Version tương lai | `schema_version:3` | Không đoán schema mới |
| Type alias cũ | `_class` tên Java cũ | Đọc được theo chiến lược đã chuẩn bị hoặc báo lỗi rõ |
| Writer cũ save lại V2 | JSON chứa field mới không có trong class cũ | Field mới không bị mất hoặc writer đã bị chặn |
| CAS conflict | Hai writer từ cùng CAS | Không mất update |
| TTL | Document có expiry 60 giây qua migration | Expiry đúng theo hợp đồng |
| SQL++ query | Filter theo tên trong V1/V2 | Không bỏ sót tài liệu do tên field |
| Rollback | Reader cũ chạy sau khi writer V2 hoạt động | Được hỗ trợ có chủ đích hoặc bị chặn theo kế hoạch |

### 16.1. Các cấp độ test

- **Unit test normalizer:** đầu vào raw JSON `MISSING`, `NULL`, value và sai kiểu.
- **Integration test Spring Data:** `findById`, `CouchbaseTemplate`, `save`, mapping constructor và CAS.
- **Integration test SQL++:** `EXPLAIN`, index, projection và read consistency.
- **Load test:** backfill theo batch, p95 latency, mức cập nhật index, heap/GC.
- **Canary test:** deploy subset reader/writer mới, theo dõi fallback/error và rollback diễn tập.
- **Data reconciliation:** số lượng theo schema, checksum/trường quan trọng và danh sách document còn lỗi.

Không chạy migration thật chỉ vì unit test Java đã PASS. Trong môi trường test Couchbase, phải chèn **JSON V1 trực tiếp** để bảo đảm code mới không vô tình dựa vào serializer V2.

### 16.2. Kiểm thử idempotency và độ bao phủ

Sau khi chạy migration hai lần:

1. Product V1 hợp lệ thành V2 đúng một lần về mặt nội dung.
2. Product V2 đã hợp lệ không bị đổi tên/giá.
3. Product `currency:null` không bị biến thành VND.
4. Product V1 lỗi vẫn ở danh sách cần xử lý, không bị gắn `schema_version:2` giả.
5. Không có document bị xóa hoặc đổi key ngoài kế hoạch.
6. TTL/CAS thay đổi theo đúng hợp đồng; nếu một mutation không cần thiết được thực thi, cần xem lại điều kiện WHERE.
7. Mọi reader/query theo đường truy cập chính vẫn có latency chấp nhận được.

## 17. Giám sát: biết khi nào được loại code tương thích cũ

Một migration dài hạn cần quan sát bằng metric, không chỉ thông báo “job chạy xong”.

| Metric | Ý nghĩa |
| --- | --- |
| `products_schema_v1_count` | Số document thực còn ở V1 |
| `products_schema_v2_count` | Số document đã chuẩn hóa |
| `legacy_read_fallback_total` | Reader còn phải fallback `name` bao nhiêu lần |
| `schema_invalid_total` | JSON null, sai kiểu, version lạ hoặc field mâu thuẫn |
| `migration_updated_total` | Số document thực được backfill |
| `migration_skipped_total` | Số document không đủ điều kiện và cần xử lý |
| `cas_conflict_total` | Xung đột với writer đang hoạt động |
| `query_p95_latency` | Hiệu năng truy vấn name/price qua index mới |
| `expiry_regression_total` | Số document expiry khác với chính sách |
| `old_writer_activity` | Writer V1 vẫn còn ghi vào `name` hay không |

Tên metric chỉ là **quy ước minh họa**. Chú ý tính riêng **tỷ lệ** trên mỗi endpoint, dữ liệu theo keyspace/tenant, log đã loại thông tin nhạy cảm và cảnh báo có người chịu trách nhiệm.

Nếu thấy `legacy_read_fallback_total` vẫn tăng sau khi backfill, có thể một writer V1 còn chạy, một collection khác chưa migrate hoặc restore đã đưa dữ liệu cũ quay lại. Không xóa code tương thích cho tới khi xác định nguồn.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| “Thêm `@Field` là đọc được dữ liệu cũ” | Annotation không tự hiểu alias field cũ | Read model hai field, converter hoặc migration |
| “Cứ null thì đặt VND” | MISSING khác NULL; có thể che lỗi dữ liệu V2 | Chỉ áp default theo version và field presence |
| “Primitive int = 0 nghĩa dữ liệu cũ đã có 0” | Java không giữ được trạng thái chưa biết | Wrapper/DTO/raw JSON và validation |
| “Schema version có thể lấy từ CAS” | CAS thay đổi mỗi mutation, không theo định dạng JSON | Lưu field schema version riêng |
| “Đổi `@TypeAlias` là document cũ tự đổi” | `_class` đã lưu không tự migrate | Mapping tương thích hoặc update có kiểm soát |
| “Mã mới đọc được là xong” | Writer cũ có thể xóa field mới khi save | Test read–modify–write |
| “Dùng `SELECT p.*` là có document key” | Key thuộc metadata | Chọn `META(p).id` khi cần |
| “Query name mới sẽ thấy Product V1” | V1 thiếu `display_name` | Query tương thích + index hoặc migration |
| “UPDATE một lần là không có race” | API cũ có thể ghi lại document V1 | Cutover writer, CAS, idempotency, reconciliation |
| “SQL++ UPDATE luôn giữ TTL” | `preserve_expiry` ảnh hưởng expiry | Cấu hình và kiểm chứng trên Server/SDK thực |
| “Migrate mọi document sang version 2 trước” | Field mới có thể vẫn thiếu/sai | Chỉ set version khi dữ liệu đã hợp lệ |
| “Rollback chỉ cần deploy code cũ” | Code cũ có thể không đọc schema V2 | Thiết kế compatibility window và rollback test |
| “Reactive tự xử lý schema cũ” | Reactive không đổi converter/JSON semantics | Dùng cùng normalizer và test mapping |
| “Một global transaction cho backfill triệu document” | Khó kiểm soát tài nguyên, lỗi và rollback | Batch idempotent + checkpoint |
| “Lỗi document bị bỏ qua là không sao” | Mất Product khỏi tìm kiếm và báo cáo | Quarantine, metric và reconciliation |

## 19. Bài thực hành: chuyển đổi hồ sơ khách hàng từ V1 sang V2

**Bối cảnh:** collection `shop.crm.customers` có dữ liệu lịch sử:

V1:

~~~json
{
  "fullName": "Nguyễn Văn A",
  "phone": "0900000000",
  "status": "ACTIVE"
}
~~~

V2 yêu cầu:

~~~json
{
  "full_name": "Nguyễn Văn A",
  "phone_e164": "+84900000000",
  "status": "ACTIVE",
  "schema_version": 2
}
~~~

Ràng buộc:

- Không được tự khẳng định mọi số điện thoại cũ đều là số Việt Nam hợp lệ.
- Nếu `phone:null` hoặc `phone` sai định dạng, cần đưa vào luồng sửa dữ liệu.
- Ứng dụng V1 và V2 có thể cùng chạy trong rolling deploy.
- Customer ID vẫn là document key, không đổi khi chuyển schema.

**Yêu cầu:** đề xuất reader tương thích, migration và kế hoạch xóa field cũ.

### 19.1. Lời giải gợi ý

**Reader:**

- V1 chưa có `schema_version`: lấy `fullName`, `phone`, validate, chuẩn hóa `phone_e164` bằng thư viện/quy tắc đã được chấp thuận.
- V2: chỉ lấy `full_name`, `phone_e164`; field bắt buộc thiếu/null là lỗi.
- Nếu cả `fullName` và `full_name` có mặt nhưng khác nhau, đưa vào reconciliation.
- Đọc qua SDK/raw DTO nếu cần phân biệt missing/null; chỉ dùng entity wrapper khi chính sách cho phép gộp.

**Migration:**

1. Thống kê V1, V2, số điện thoại lỗi và những document vừa có field cũ/mới.
2. Deploy reader có khả năng xử lý cả hai.
3. Ngăn writer V1 ghi đè field mới hoặc đặt cơ chế dual-write có kiểm tra.
4. Backfill `full_name` nếu `fullName` hợp lệ; chuẩn hóa phone qua thư viện có phân loại quốc gia rõ ràng.
5. Chỉ đặt `schema_version=2` khi **tất cả field V2 hợp lệ**.
6. Đối chiếu và xử lý Customer cần sửa tay.
7. Khi reader/writer V1 ngừng hoạt động, mới `UNSET fullName, phone`.
8. Kiểm thử rollback, CAS, TTL nếu có và truy vấn theo tên/số điện thoại.

Đặc biệt, **không dùng một câu SQL++ nối `"+84"` với mọi `phone`**. Điều đó có thể biến số quốc tế hoặc số sai định dạng thành dữ liệu giả.

### 19.2. Bài SQL++ để kiểm kê trước migration

~~~sql
SELECT META(c).id AS customerKey,
       c.fullName AS legacyFullName,
       c.full_name AS currentFullName,
       c.phone AS legacyPhone,
       c.phone_e164 AS currentPhone,
       IFMISSING(c.schema_version, -1) AS storedVersion
FROM `shop`.`crm`.`customers` AS c
WHERE c.schema_version IS MISSING
   OR c.schema_version = 1
LIMIT 100;
~~~

Truy vấn này chỉ **đọc để kiểm kê**, không tự chuẩn hóa số điện thoại. Đối với dữ liệu có thông tin cá nhân, không xuất toàn bộ kết quả vào log hoặc tệp công khai; giới hạn quyền và số dòng đọc.

### 19.3. Câu hỏi tự kiểm tra

1. **Thêm `@Field("full_name")` có tự đọc field V1 `fullName` không?** Không.
2. **`MISSING` và JSON `null` có giống nhau không?** Không; reader cần hợp đồng xử lý riêng.
3. **`@Version` có phải `schema_version` không?** Không; `@Version` gắn với CAS.
4. **Reader V2 đọc được V1 có chứng minh writer V1 không phá V2 không?** Không; cần test read–modify–write.
5. **Tại sao cần expand trước migrate?** Để mọi reader có thể xử lý dữ liệu trong giai đoạn chuyển tiếp.
6. **Khi nào mới có thể xóa field cũ?** Sau khi toàn bộ reader/writer cũ ngừng, dữ liệu đã đối chiếu và rollback được chuẩn bị.
7. **Nếu Product/Customer có TTL, migration UPDATE có chắc bảo toàn không?** Không; phải kiểm tra/cấu hình `preserve_expiry`.
8. **Đổi tên field có tự đổi document key không?** Không.
9. **Nếu query `WHERE full_name = $name` chạy trên dữ liệu V1, điều gì xảy ra?** Có thể bỏ sót tài liệu chỉ chứa `fullName`.
10. **Có nên đổi số điện thoại string lỗi thành số bằng cách ép kiểu tự động không?** Không; phải validate và phân loại trước.
11. **Reactive repository có tự chuẩn hóa các JSON schema không?** Không; dùng mapping/normalizer tương đương.
12. **Có thể dùng một transaction cho toàn bộ migration hàng triệu document không?** Không phù hợp; cần batch, checkpoint, idempotency và đối chiếu.

## 20. Checklist triển khai

- [ ] Liệt kê JSON V1/V2 và các biến thể thực tế trong cùng collection.
- [ ] Phân biệt rõ reader mới đọc cũ và reader cũ đọc mới.
- [ ] Xác nhận field MISSING, NULL, rỗng, sai kiểu và giá trị miền không hợp lệ.
- [ ] Có `schema_version` tường minh nếu thực sự cần; không nhầm với `@Version`/CAS/`_class`.
- [ ] Với rename field, chọn phương án đọc hai field, converter, DTO hoặc migration, không dựa riêng vào `@Field`.
- [ ] Đặt default chỉ khi có bằng chứng từ schema cũ và quy tắc nghiệp vụ.
- [ ] Không sinh ID, timestamp hoặc dữ liệu lịch sử mới trong constructor persistence.
- [ ] Kiểm tra cả `findById`, `CouchbaseTemplate`, SQL++ query và read–modify–write.
- [ ] Thiết kế index/query tạm cho field legacy và V2; đo `EXPLAIN` trước khi thêm index.
- [ ] Trước migration, triển khai reader tương thích và kiểm kê mọi writer cũ.
- [ ] Backfill theo batch có điều kiện, idempotent, checkpoint, reconciliation và rollback.
- [ ] Chỉ tăng `schema_version` khi tất cả field bắt buộc của V2 đã hợp lệ.
- [ ] Bảo vệ CAS, quyền ghi, concurrency và `preserve_expiry` khi UPDATE.
- [ ] Không contract field cũ khi còn reader/writer V1 hoặc có backlog consumer.
- [ ] Có test fixture JSON cũ thật, JSON lỗi, TTL, CAS conflict và rollback.
- [ ] Theo dõi fallback/version distribution và xóa index tạm sau cutover.
- [ ] Giữ số liệu khách hàng/PII trong báo cáo migration theo chính sách bảo mật.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Field`, object mapping, constructor, metadata và cách materialize entity.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): constructor selection, record, property population, immutable data.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD qua KV, derived queries và SQL++.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): bucket/scope/collection và mapping entity.
- [Couchbase Server — SQL++ Conditional Functions for Unknowns](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/condfununknown.html): `IFMISSING`, `IFNULL`, `IFMISSINGORNULL`.
- [Couchbase Server — SQL++ Type Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/typefun.html): `ISNUMBER`, `ISSTRING` và kiểm tra kiểu.
- [Couchbase Server — SQL++ UPDATE](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/update.html): `SET`, `UNSET`, điều kiện UPDATE và `preserve_expiry`.
- [Couchbase Server — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): secondary index, biểu thức index và `INCLUDE MISSING`.
- [Couchbase Java SDK — Key-Value Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): truy cập JSON body, CAS và key document.
