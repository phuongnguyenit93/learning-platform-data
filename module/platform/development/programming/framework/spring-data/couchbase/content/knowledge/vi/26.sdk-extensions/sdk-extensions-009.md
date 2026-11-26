# Chuyển kết quả SDK sang mô hình dữ liệu ứng dụng

Trong **Spring Data Couchbase**, Repository và `CouchbaseTemplate` thường che giấu nhiều chi tiết chuyển đổi: entity Java có `@Document`, `@Id`, `@Field`, `@Version`, custom conversion và các quy ước đọc/ghi. Khi mở rộng sang **Couchbase Java SDK trực tiếp**, ứng dụng có nhiều kiểu kết quả khác nhau: `GetResult`, `QueryResult`, `AnalyticsResult`, `SearchResult`, `LookupInResult`, `CounterResult` và các dạng reactive của chúng.

Mỗi kết quả chứa **hình dạng dữ liệu và metadata riêng**. Một document đọc bằng KV khác một row `SELECT`, một nhóm `GROUP BY` không phải entity, còn Search hit chủ yếu là **ID + score + optional stored fields**. Nếu chuyển đổi bằng cách ép kiểu bừa hoặc đưa partial projection vào `repository.save(...)`, ứng dụng có thể mất field, bỏ qua CAS, lộ dữ liệu tenant khác hoặc diễn giải sai số tiền/thời gian.

Bài này thuộc chương **Mở rộng bằng SDK** của module **SPRING_DATA_COUCHBASE**: xây dựng tầng truy cập Couchbase với document mapping, Repository, `CouchbaseTemplate` và SQL++; hiểu bucket/scope/collection, index, TTL, CAS, transaction và reactive API để cân bằng hiệu năng, tính nhất quán và khả năng vận hành.

> **Nguyên tắc:** **SDK result ≠ domain entity ≠ API response.** Hãy xây một lớp adapter/mapper có hợp đồng rõ: đọc raw result, phân loại metadata, chuẩn hóa kiểu dữ liệu, kiểm tra bất biến và quyền truy cập, rồi trả **read model/DTO** có ý nghĩa nghiệp vụ. Chỉ dùng entity đầy đủ cho luồng ghi khi thực sự có đủ dữ liệu và phiên bản phù hợp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **KV document**, **SQL++ row**, **Analytics aggregate**, **Search hit**, **sub-document result** và **counter result**.
2. Đọc `GetResult.contentAsObject()`, `contentAs(Class<T>)` và `cas()`; hiểu ID/CAS không nhất thiết nằm trong JSON body.
3. Đọc `QueryResult.rowsAsObject()`, `rowsAs(Class<T>)`, `rowsAs(TypeRef<T>)` và `metaData()`.
4. Ánh xạ `SELECT` có alias, `SELECT RAW`, nested fields, projection và `GROUP BY` sang DTO phù hợp.
5. Phân biệt SDK `JsonSerializer`/`Transcoder` với Spring Data `CouchbaseConverter`/`@Field`/`@Version`.
6. Xử lý `MISSING`, `NULL`, số JSON, enum lạ, chuỗi ngày/giờ và tiền tệ mà không âm thầm thay đổi ý nghĩa.
7. Ánh xạ `SearchResult` thành hit DTO và quyết định khi nào hydrate current document bằng KV.
8. Ánh xạ `AnalyticsResult` thành báo cáo tổng hợp, không cố gắng biến row thành entity có CAS.
9. Kết hợp mapper với `Flux`/`Mono` mà không blocking event loop hoặc gom vô hạn dữ liệu.
10. Thiết kế lỗi decode/validation, tenant authorization, schema evolution, pagination và integration tests theo hợp đồng.
11. Tách DTO API, domain model, entity persistence và diagnostic metadata để code dễ thay đổi.

## 2. Một nguồn dữ liệu, nhiều hình dạng kết quả

Giả sử collection vận hành:

~~~text
Bucket: shop
Scope: catalog
Collection: products

Key: product::tenant-01::sku-1001
~~~

Body JSON:

~~~json
{
  "tenantId": "tenant-01",
  "type": "product",
  "sku": "sku-1001",
  "name": "Cà phê rang mộc Đà Lạt",
  "priceCents": 145000,
  "currency": "VND",
  "active": true,
  "category": "COFFEE",
  "createdAt": "2026-11-24T02:30:00Z"
}
~~~

Từ dữ liệu này, ứng dụng có thể cần:

- **Entity để chỉnh sửa**: đầy đủ field và CAS/version.
- **Card tìm kiếm**: `id`, `name`, `priceCents`, `currency`, không cần mọi metadata nội bộ.
- **Báo cáo theo category**: một row/category và tổng số sản phẩm.
- **Search hit**: ID, relevance score, highlight, sau đó hydrate nếu cần giá hiện hành.
- **Đáp án cho API public**: chỉ những thuộc tính client được phép xem.

Các mô hình này không nên bị ép thành **một class Product duy nhất**.

## 3. Bản đồ các kiểu kết quả của Java SDK

| Nguồn | Đối tượng SDK | Dữ liệu chính | Metadata cần phân biệt | Đích phù hợp |
| --- | --- | --- | --- | --- |
| KV `get` | `GetResult` | Body một document | `cas()`, expiry nếu request | Entity snapshot, DTO |
| KV replica get | `GetReplicaResult` | Một bản active/replica | `isReplica()`, CAS | Preview có thể cũ |
| SQL++ | `QueryResult` | Danh sách row JSON | `QueryMetaData`, warnings, metrics | DTO/projection |
| Analytics | `AnalyticsResult` | Rows phân tích | `AnalyticsMetaData` | Report DTO |
| Full-Text Search | `SearchResult` | Search hits, score | `SearchMetaData`, partial errors | Search hit DTO |
| Sub-document lookup | `LookupInResult` | Giá trị ở các path | CAS, vị trí spec | Field DTO |
| KV binary counter | `CounterResult` | Số sau mutation | CAS của mutation | Scalar result |
| KV mutation | `MutationResult` | Không phải entity body | CAS, mutation token nếu có | Acknowledgement |

**Không tồn tại một quy tắc chuyển đổi chung** “gọi `contentAsObject()` rồi cast sang entity” cho tất cả các API này.

## 4. Tách bốn tầng mô hình

~~~text
Couchbase Server (source JSON / KV metadata)
          |
          v
Java SDK result (GetResult / QueryResult / SearchResult)
          |
          v
Persistence adapter + mapper (type conversion + validation + auth)
          |
          +----> Persistence snapshot (đủ body + CAS, dùng cho write)
          |
          +----> Application read model (ProductCard, RevenueByCategory)
          |
          +----> Query diagnostics (requestId, elapsed, warnings)
          |
          v
Application service / API response đã lọc trường
~~~

Một kiến trúc rõ ràng có thể có:

~~~java
public record ProductCard(
        String id,
        String name,
        long priceCents,
        String currency) {}

public record ProductForEdit(
        String id,
        String name,
        long priceCents,
        String currency,
        long cas) {}

public record CategorySummary(
        String category,
        long productCount) {}
~~~

Các record là **read/write models của ứng dụng**, không phải một entity `@Document` tự động. Có thể thêm validation ở constructor/factory hoặc domain service. Khi chuyển từ persistence đến API, **có thể cần một lớp DTO khác** nếu public contract khác.

## 5. Đọc KV bằng `GetResult.contentAsObject()`

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.GetResult;

public ProductCard getCard(
        Collection products, String id) {

    GetResult result = products.get(id);
    JsonObject body = result.contentAsObject();

    return new ProductCard(
            id,
            body.getString("name"),
            body.getLong("priceCents"),
            body.getString("currency"));
}
~~~

Đây là ví dụ tối giản và cần validation trước production.

Điểm quan trọng:

- `Collection.get(id)` đọc document theo **đúng bucket/scope/collection**.
- `id` được truyền cho KV get; document key không nhất thiết nằm trong body.
- `GetResult.contentAsObject()` giải mã body JSON object.
- `getLong(...)` trả kiểu wrapper `Long`; nếu thiếu/null, unboxing sang `long` có thể ném `NullPointerException`.
- Nếu body là JSON array, scalar hoặc non-JSON document, `contentAsObject()` không phải decoding phù hợp.
- Các `getString`/`getLong` có semantics JSON, không tự áp dụng annotation `@Field` của entity Java.
- SDK result là **snapshot tại thời điểm get**, không khóa document khỏi bị writer khác sửa sau đó.

Nên tách mapping thành method riêng để unit-test không cần Couchbase.

## 6. Tách mapper thuần khỏi thao tác IO

Một mapper dễ kiểm thử:

~~~java
import com.couchbase.client.java.json.JsonObject;

public final class ProductCardMapper {

    public ProductCard fromJson(
            String id,
            JsonObject body) {

        String name = requireText(body, "name");
        long cents = requireLong(body, "priceCents");
        String currency = requireText(body, "currency");

        if (cents < 0) {
            throw new IllegalArgumentException(
                    "Invalid priceCents");
        }

        return new ProductCard(
                id, name, cents, currency);
    }

    private static String requireText(
            JsonObject body, String field) {

        String value = body.getString(field);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Required field missing: " + field);
        }
        return value;
    }

    private static long requireLong(
            JsonObject body, String field) {

        Long value = body.getLong(field);
        if (value == null) {
            throw new IllegalArgumentException(
                    "Required field missing: " + field);
        }
        return value;
    }
}
~~~

Đây là **mức kiểm tra tối thiểu**, chưa bảo vệ đầy đủ trước số JSON sai kiểu/rounding; phần sau sẽ dùng validation chặt hơn.

SDK adapter:

~~~java
public ProductCard findCard(
        Collection products,
        String id,
        ProductCardMapper mapper) {

    GetResult result = products.get(id);
    return mapper.fromJson(
            id, result.contentAsObject());
}
~~~

Mapper thuần có thể test với `JsonObject.create()`, giúp phát hiện lỗi field alias, NULL, số và enum mà không phải chạy server.

## 7. `GetResult.contentAs(Class<T>)` và giới hạn của POJO mapping

SDK hỗ trợ:

~~~java
GetResult result = products.get(id);

ProductBody body =
        result.contentAs(ProductBody.class);
~~~

Giả sử:

~~~java
public record ProductBody(
        String tenantId,
        String sku,
        String name,
        Long priceCents,
        String currency,
        Boolean active) {}
~~~

Với serializer tương thích Java record và schema JSON phù hợp, SDK có thể deserialize trực tiếp body thành record/POJO. Điều này giảm code map thủ công.

**Nhưng không suy ra:**

1. ID được tự điền từ document key nếu body không có field `id`.
2. CAS được tự điền vào property có `@Version`.
3. Spring Data `@Field("product_name")` tự đổi JSON field sang property `name`.
4. Spring Data auditing/callback/custom converters đã chạy.
5. Validation domain đã tự được thực thi.
6. Mọi nullable field trở thành hợp lệ khi DTO có kiểu primitive.
7. Serializer của SDK giống chính xác Spring Boot `ObjectMapper` đã cấu hình.

Nếu cần ID và CAS, hãy tạo **wrapper snapshot** từ `GetResult` và key, thay vì cố nhét mọi thứ vào body.

## 8. CAS và document key thuộc metadata, không phải body JSON

`GetResult.cas()` trả token CAS của document ở thời điểm read:

~~~java
public record ProductSnapshot(
        String id,
        ProductBody body,
        long cas) {}

public ProductSnapshot readSnapshot(
        Collection products, String id) {

    GetResult result = products.get(id);

    return new ProductSnapshot(
            id,
            result.contentAs(ProductBody.class),
            result.cas());
}
~~~

Ý nghĩa:

- `id` xác định document trong collection.
- `cas` phục vụ optimistic locking khi muốn write có điều kiện.
- `body` là dữ liệu JSON, có thể là immutable DTO.
- CAS **không** phải đồng hồ timestamp/sequence giữa các documents.
- Khi trả DTO qua API, cân nhắc dùng opaque version/ETag có policy, không lộ nội bộ không cần thiết.

Ví dụ update:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;

products.replace(
        snapshot.id(),
        updatedFullBody,
        replaceOptions().cas(snapshot.cas()));
~~~

Đây là **full-document replace có điều kiện**. Nếu body chỉ là projection thiếu field, không dùng nó làm `updatedFullBody` vì sẽ mất dữ liệu không có trong DTO.

## 9. TTL metadata chỉ sẵn khi yêu cầu đúng

SDK `GetResult` có khả năng trả `expiryTime()`, nhưng thông tin expiry **không tự xuất hiện trong mọi `get`**.

~~~java
import static com.couchbase.client.java.kv.GetOptions.getOptions;

GetResult result = products.get(
        id,
        getOptions().withExpiry(true));

Optional<Instant> expiresAt =
        result.expiryTime();
~~~

Các chi tiết:

- `withExpiry(true)` yêu cầu trả expiry metadata khi hỗ trợ.
- `Optional.empty()` cần được xử lý theo ngữ nghĩa của SDK và expiry hiện tại; không coi thiếu metadata là ngày 1970 hoặc thời điểm hiện hành.
- TTL không phải một field JSON bắt buộc có tên `expiresAt`.
- Đọc expiry rồi write lại phải cân nhắc `preserveExpiry`/mutation option nếu nghiệp vụ cần giữ thời hạn.
- Nếu document hết hạn/xóa giữa GET và WRITE, CAS/version và error handling vẫn cần thiết.

Trong nhiều use case card hiển thị, không cần đọc TTL; chỉ lấy metadata nếu ứng dụng dùng nó.

## 10. SDK serializer/transcoder khác Spring Data converter

Có **hai tầng** cần phân biệt:

| Tầng | Thành phần | Công việc |
| --- | --- | --- |
| Couchbase Java SDK | `Transcoder`, `JsonSerializer` | Chuyển bytes/JSON thành kiểu Java hoặc ngược lại |
| Spring Data Couchbase | `CouchbaseConverter`, mapping context, custom conversions | Mapping entity, annotation, ID/CAS, lifecycle qua Spring Data |
| Ứng dụng | Mapper/assembler/domain factory | Validation, authorization, business representation |
| HTTP/API | JSON serializer của Web framework | Chuyển API DTO thành JSON response |

SDK mặc định dùng `JsonTranscoder` và serializer JSON; việc cấu hình một Jackson `ObjectMapper` phù hợp sẽ hỗ trợ POJO/record. Nhưng **điều này không chứng minh SDK dùng chung mọi conversion rule** với Spring Data.

Ví dụ entity:

~~~java
@Document
@Scope("catalog")
@Collection("products")
public class ProductEntity {

    @Id
    private String id;

    @Version
    private Long version;

    @Field("product_name")
    private String name;

    private String tenantId;
}
~~~

Nếu JSON body thực tế chứa `product_name`, SDK raw:

~~~java
String storedName =
        result.contentAsObject()
                .getString("product_name");
~~~

**Không** mặc định:

~~~java
String wrong =
        result.contentAsObject().getString("name");
~~~

Nếu cần tái sử dụng conversion của Spring Data, hãy sử dụng các API mapping chính thức theo phiên bản hoặc giữ đường Repository/Template; **đừng tự đoán** chữ ký `MappingCouchbaseConverter.read(...)` hay lẫn lộn `ObjectMapper` với domain conversion.

## 11. Đường SDK direct trong Spring-managed ứng dụng

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import org.springframework.stereotype.Component;

@Component
public final class ProductSdkReadAdapter {

    private final Collection products;
    private final ProductCardMapper mapper;

    public ProductSdkReadAdapter(
            Cluster cluster,
            ProductCardMapper mapper) {

        this.products = cluster.bucket("shop")
                .scope("catalog")
                .collection("products");

        this.mapper = mapper;
    }

    public ProductCard getCard(String id) {
        GetResult result = products.get(id);
        return mapper.fromJson(
                id, result.contentAsObject());
    }
}
~~~

`Cluster` do Spring Boot/Spring Data hoặc configuration của ứng dụng quản lý. Không gọi `Cluster.connect(...)` trong mỗi request và không `disconnect()` trong adapter.

Sử dụng collection handle đúng **bucket/scope/collection**. Cùng chuỗi document key ở collection khác vẫn là document khác; một mapper đúng field nhưng đọc nhầm collection vẫn cho kết quả sai hoặc lộ dữ liệu.

`ProductCardMapper` trong ví dụ cần được khai báo thành Spring bean (ví dụ `@Component`) hoặc tạo qua configuration, vì constructor adapter yêu cầu inject nó.

## 12. SQL++ result shape: `SELECT` không giống KV document body

Truy vấn:

~~~sql
SELECT META(p).id AS id,
       p.name AS name,
       p.priceCents AS priceCents,
       p.currency AS currency
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId
  AND p.active = TRUE
ORDER BY p.name ASC, META(p).id ASC
LIMIT $limit;
~~~

Một SQL++ result row:

~~~json
{
  "id": "product::tenant-01::sku-1001",
  "name": "Cà phê rang mộc Đà Lạt",
  "priceCents": 145000,
  "currency": "VND"
}
~~~

SDK:

~~~java
QueryResult result =
        cluster.query(statement, queryOptions()
                .parameters(params)
                .readonly(true));

List<JsonObject> rows = result.rowsAsObject();
~~~

Đây là **các rows được dựng bởi query**, không phải body nguyên bản từ KV get. `META(p).id AS id` là một **projection tường minh** để mang document key vào row. Nó không tự mang CAS trừ khi query và mapping có yêu cầu tương ứng.

Không giả định alias `id` tồn tại chỉ vì document nguồn có ID.

## 13. Alias SQL++ là hợp đồng của mapper

Nếu query viết:

~~~sql
SELECT p.name AS displayName,
       p.priceCents AS amount
FROM `shop`.`catalog`.`products` AS p
LIMIT 10;
~~~

thì result shape là:

~~~json
{
  "displayName": "Cà phê rang mộc Đà Lạt",
  "amount": 145000
}
~~~

Code đọc:

~~~java
String label = row.getString("displayName");
Long amount = row.getLong("amount");
~~~

Không đọc:

~~~java
String wrong = row.getString("name");
~~~

Vì field đó không có trong projection dù source document có `name`.

Nên đặt alias ổn định để mapper không bị ảnh hưởng khi nguồn JSON đổi field. Khi đổi alias, cập nhật **SQL++ statement, mapper, DTO contract và integration tests** cùng lúc.

## 14. `SELECT p`, `SELECT RAW p` và projection phẳng

Ba dạng SQL++ có thể khác JSON result shape:

~~~sql
-- Object có trường "p", bên trong là document body.
SELECT p
FROM `shop`.`catalog`.`products` AS p
LIMIT 1;
~~~

~~~json
{
  "p": {
    "tenantId": "tenant-01",
    "name": "Cà phê rang mộc Đà Lạt"
  }
}
~~~

~~~sql
-- Raw body, không có lớp wrapper "p".
SELECT RAW p
FROM `shop`.`catalog`.`products` AS p
LIMIT 1;
~~~

~~~json
{
  "tenantId": "tenant-01",
  "name": "Cà phê rang mộc Đà Lạt"
}
~~~

~~~sql
-- Projection phẳng với alias riêng.
SELECT META(p).id AS id,
       p.name AS name
FROM `shop`.`catalog`.`products` AS p
LIMIT 1;
~~~

~~~json
{
  "id": "product::tenant-01::sku-1001",
  "name": "Cà phê rang mộc Đà Lạt"
}
~~~

Với `SELECT p`, mapper cần lấy `row.getObject("p")`. Với `SELECT RAW p`, mapper đọc trực tiếp `row.getString("name")`. Với projection phẳng, đọc các aliases đã định nghĩa.

**Đừng đổi giữa ba câu query rồi chỉ giữ nguyên code mapper**, vì đó là thay đổi contract dữ liệu.

## 15. `SELECT RAW` scalar không phải `JsonObject`

Ví dụ:

~~~sql
SELECT RAW COUNT(1)
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId;
~~~

Kết quả là một **giá trị số** (scalar), không phải row `{"count": ...}`. SDK hỗ trợ deserialize rows sang kiểu tương ứng:

~~~java
QueryResult result = cluster.query(
        countStatement,
        queryOptions().parameters(params));

List<Long> totals = result.rowsAs(Long.class);

long count = totals.isEmpty() ? 0L : totals.get(0);
~~~

Câu `COUNT(1)` không có `GROUP BY` thường trả một row; trong production, nên assert shape/row count theo contract thay vì ngầm coi kết quả rỗng là 0 trong mọi trường hợp lỗi.

Nếu muốn một object row rõ alias:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId;
~~~

~~~java
Long count = result.rowsAsObject()
        .get(0).getLong("total");
~~~

Hai cách có hình dạng khác nhau; chọn một cách và test chính xác.

## 16. `GROUP BY` tạo aggregate DTO, không tạo entity

~~~sql
SELECT p.category AS category,
       COUNT(1) AS productCount
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId
GROUP BY p.category
ORDER BY productCount DESC, category ASC;
~~~

Ví dụ rows:

~~~json
[
  { "category": "COFFEE", "productCount": 82 },
  { "category": "TEA", "productCount": 31 }
]
~~~

Mapper:

~~~java
public record CategorySummary(
        String category,
        long productCount) {}

List<CategorySummary> summaries =
        result.rowsAsObject().stream()
                .map(row -> new CategorySummary(
                        row.getString("category"),
                        row.getLong("productCount")))
                .toList();
~~~

Mỗi row là **một nhóm**, không phải một document nguồn. Nhóm không có một ID/CAS duy nhất để `repository.save(...)` trở lại Product entity.

`QueryMetaData.metrics().resultCount()` (nếu được bật) là số result rows của query, **không phải tổng số documents góp vào các nhóm**. Nếu cần tổng số sản phẩm, đọc alias `productCount` hoặc query count phù hợp.

## 17. `MISSING` và `NULL` không nên bị gộp âm thầm

JSON và SQL++ có các trạng thái khác nhau:

- Field **vắng** trong object/`MISSING`.
- Field có mặt với **JSON `null`**.
- Field có giá trị hợp lệ (kể cả `0`, `false` hoặc chuỗi rỗng).
- Field có kiểu không hợp lệ, ví dụ `"145000"` là string thay vì number.

Với SDK `JsonObject`:

~~~java
boolean exists = row.containsKey("discountCents");
Object raw = row.get("discountCents");
~~~

| `containsKey` | `get` | Ý nghĩa |
| --- | --- | --- |
| false | null | Field vắng |
| true | null hoặc biểu diễn JSON-null tùy đường giải mã | Có field JSON null; kiểm tra theo SDK/serializer đang dùng |
| true | Number | Có giá trị số |
| true | String | Có chuỗi, không tự là tiền |

Với SDK có hằng `JsonValue.NULL`/`JsonNull`, hãy kiểm tra kiểu giá trị thực tế sau decode, không chỉ dựa trên `raw == null` để kết luận field vắng hay null. Chính `containsKey` giúp phân biệt việc **có tên field** với **không có tên field**.

**Không** viết:

~~~java
long discount = row.getLong("discountCents") == null
        ? 0L
        : row.getLong("discountCents");
~~~

nếu 0, missing và null có ý nghĩa khác nhau. Đó là **quyết định domain**: chỉ default 0 khi schema/contract quy định vắng field đồng nghĩa không có giảm giá.

Nếu muốn biết “không biết mức giảm”, dùng `Long` nullable hoặc một value object với trạng thái riêng; tránh dùng primitive `long` để nuốt thiếu dữ liệu.

## 18. Thẩm định kiểu số: `getLong` có thể chuyển đổi mất chính xác

SDK `JsonObject.getLong(...)` trả kiểu `Long` và có thể chuyển đổi từ một số numeric JSON khác; tài liệu lưu ý một số chuyển đổi có thể **truncation/rounding**.

Ví dụ nguy hiểm:

~~~json
{
  "priceCents": 145000.75
}
~~~

Nếu bạn đọc thành `long` mà không kiểm tra schema, một giá trị không hợp lệ về đơn vị cents có thể bị làm tròn/cắt.

Đối với tiền/quota/billing, cần xác nhận:

1. JSON source lưu **số nguyên** khi field contract là cents.
2. Giá trị nằm trong `Long.MIN_VALUE...Long.MAX_VALUE` và miền nghiệp vụ.
3. Không có fractional part hoặc NaN/Infinity.
4. Không chấp nhận numeric string chỉ bằng ép kiểu ngầm.
5. Không trộn field cents với decimal currency amount.
6. Không cộng/sum vượt miền số mà không phát hiện.

Một mapper chặt hơn có thể kiểm tra kiểu số trong quá trình validation trước khi dùng `getLong`.

## 19. Tiền tệ: tách đơn vị lưu và định dạng hiển thị

Ví dụ entity lưu:

~~~json
{
  "priceCents": 145000,
  "currency": "VND"
}
~~~

Tên `priceCents` trong ví dụ là **đơn vị số nguyên do hệ thống định nghĩa**; không suy rằng mọi đồng tiền đều có 2 decimal places.

Một value object:

~~~java
public record Money(
        long minorUnits,
        String currency) {

    public Money {
        if (minorUnits < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Missing currency");
        }
    }
}
~~~

DTO:

~~~java
public record ProductPrice(
        String productId,
        Money amount) {}
~~~

Nếu muốn chuyển minor units thành `BigDecimal` để hiển thị, phải lấy **currency exponent** theo chính sách đã thống nhất (VND có cách diễn giải khác USD). Không luôn dùng `BigDecimal.valueOf(cents, 2)` cho mọi currency.

Khi có SQL++ `SUM`/Analytics aggregation, hãy validate kiểu/overflow và **group theo currency hoặc quy đổi theo tỷ giá có provenance**; không lấy tổng nhiều currency rồi gọi là doanh thu chuẩn.

## 20. Ngày và timezone: lưu trữ khác cách hiển thị

JSON:

~~~json
{
  "createdAt": "2026-11-24T02:30:00Z"
}
~~~

Nếu contract lưu chuỗi ISO-8601 UTC, mapper:

~~~java
import java.time.Instant;
import java.time.format.DateTimeParseException;

public Instant requireInstant(
        JsonObject row, String field) {

    String value = row.getString(field);
    if (value == null) {
        throw new IllegalArgumentException(
                "Missing timestamp: " + field);
    }

    try {
        return Instant.parse(value);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Invalid timestamp: " + field, ex);
    }
}
~~~

Những bẫy:

- Không dùng timezone mặc định của pod để diễn giải một local date không có offset.
- `Instant` thể hiện mốc thời gian tuyệt đối, không chứa timezone hiển thị của user.
- Nếu source lưu epoch millis, phải chuyển theo **đúng đơn vị**, không nhầm seconds/milliseconds.
- `createdAt`, `updatedAt` có thể mang schema từ hệ thống cũ; version hóa khi thay format.
- Dữ liệu ngày dùng cho group theo ngày phải quy định timezone.
- Khi reactive stream lớn, parsing timestamp là CPU work ở client; đo hiệu năng nhưng không đánh đổi validation.

## 21. Enum lạ và schema tiến hóa

Giả sử `category` lưu `COFFEE`/`TEA`, nhưng tương lai bổ sung `MATCHA`.

Nguy hiểm:

~~~java
Category category = Category.valueOf(
        row.getString("category"));
~~~

Một enum lạ có thể ném `IllegalArgumentException`, làm thất bại cả stream nếu không xử lý theo policy.

Các chiến lược:

1. **Fail fast**: khi một field domain phải nằm trong một tập được khóa (ví dụ trạng thái giao dịch).
2. **UNKNOWN fallback**: hợp lý cho analytics/UI preview nếu hợp đồng cho phép.
3. **Raw value giữ nguyên**: dùng string ở read model để client tương thích forward.
4. **Versioned enum**: mapping theo `schemaVersion` của document.
5. **Quarantine** các document sai schema trong batch import, có cảnh báo chất lượng dữ liệu.

**Không cho unknown status của thanh toán mặc định thành `PAID` hay `ACTIVE`.** Việc default chỉ hợp lệ khi đã được domain định nghĩa.

## 22. Nested JSON và mảng: đừng mất shape

Document:

~~~json
{
  "name": "Cà phê rang mộc",
  "seller": {
    "id": "seller-10",
    "displayName": "Nông trại A"
  },
  "tags": ["arabica", "da-lat"]
}
~~~

`JsonObject` có:

~~~java
JsonObject seller = body.getObject("seller");
JsonArray tags = body.getArray("tags");
~~~

Một DTO:

~~~java
public record SellerView(
        String id, String displayName) {}

public record ProductDetail(
        String name,
        SellerView seller,
        List<String> tags) {}
~~~

Khi map:

- Kiểm tra `seller` có tồn tại và đúng object không.
- Với `tags`, kiểm tra từng phần tử là string (không chỉ cast cả `JsonArray` sang `List<String>` mà chưa xác minh).
- Tránh expose toàn bộ nested object nếu nó chứa trường nội bộ.
- Mảng lớn cần giới hạn response/heap.
- Mối quan hệ bằng foreign key document ID **không tự được hydrate** bởi SDK `contentAsObject()`.
- Nếu dùng SQL++ `UNNEST`, một document có thể sinh nhiều result rows; đừng nhầm row count với document count.

Mappers của ứng dụng giúp xác định rõ shape mong muốn và xử lý schema thiếu thành lỗi có thể chẩn đoán.

## 23. Map trực tiếp SQL++ row bằng `rowsAs(Class<T>)`

Nếu tên alias và property Java khớp, SDK có thể deserialize trực tiếp:

~~~java
public record ProductCard(
        String id,
        String name,
        long priceCents,
        String currency) {}
~~~

~~~sql
SELECT META(p).id AS id,
       p.name AS name,
       p.priceCents AS priceCents,
       p.currency AS currency
FROM `shop`.`catalog`.`products` AS p
WHERE p.tenantId = $tenantId
  AND p.active = TRUE
LIMIT $limit;
~~~

~~~java
List<ProductCard> cards =
        result.rowsAs(ProductCard.class);
~~~

Ưu điểm: ít boilerplate, tên trường tường minh, phù hợp DTO nhỏ có schema ổn định.

Nhưng phải thẩm định:

1. SDK `JsonSerializer` có hỗ trợ Java records/constructor/annotations đang dùng không?
2. Alias `id`, `name`, `priceCents`, `currency` có khớp property Java không?
3. Field thiếu/null với primitive `long` xử lý ra sao?
4. Có dữ liệu numeric ngoài range/decimal fraction không?
5. Constructor của DTO có validate invariant không, hay serializer có thể tạo instance không hợp lệ?
6. Các field bổ sung/trường không biết được serializer xử lý thế nào?
7. Conversion từ `Date`/`Instant`/enum được cấu hình ở SDK, không giả định trùng Spring converter.

`rowsAs(Class<T>)` giúp **deserialize**, không chứng nhận **hợp lệ nghiệp vụ**. Với dữ liệu tài chính/bảo mật, mapping thủ công có validate có thể an toàn và dễ kiểm thử hơn.

## 24. Dùng `TypeRef<T>` khi Java generic type quan trọng

SDK hỗ trợ `TypeRef` cho generic targets:

~~~java
import com.couchbase.client.java.codec.TypeRef;
import java.util.Map;

List<Map<String, Object>> rows = result.rowsAs(
        new TypeRef<Map<String, Object>>() {});
~~~

Lưu ý `rowsAs` luôn trả **một List các rows**; trong ví dụ, `TypeRef<Map<String,Object>>` là **kiểu của từng row**, không phải `TypeRef<List<Map<...>>>` của toàn response.

Tương tự với KV JSON array:

~~~java
GetResult result = collection.get(id);

List<String> tags = result.contentAs(
        new TypeRef<List<String>>() {});
~~~

Ví dụ thứ hai chỉ đúng khi **toàn bộ KV body** là một JSON array of strings. Nếu body là object `{"tags":[...]}`, phải chọn DTO object hoặc đọc `contentAsObject().getArray("tags")`.

Không dùng raw generic `Map` rồi ép kiểu sâu không kiểm tra; Java type erasure và JSON numeric representation dễ tạo `ClassCastException` muộn hơn ở business layer.

## 25. SQL++ joins, `SELECT` objects và kết quả lồng nhau

Truy vấn liên kết Product và Seller có thể trả:

~~~sql
SELECT META(p).id AS productId,
       p.name AS productName,
       s.name AS sellerName
FROM `shop`.`catalog`.`products` AS p
LEFT JOIN `shop`.`catalog`.`sellers` AS s
  ON KEYS p.sellerId
WHERE p.tenantId = $tenantId
LIMIT 20;
~~~

Kết quả có thể là:

~~~json
{
  "productId": "product::tenant-01::sku-1001",
  "productName": "Cà phê rang mộc",
  "sellerName": "Nông trại A"
}
~~~

Một mapper:

~~~java
public record ProductWithSeller(
        String productId,
        String productName,
        String sellerName) {}

ProductWithSeller convert(JsonObject row) {
    return new ProductWithSeller(
            row.getString("productId"),
            row.getString("productName"),
            row.getString("sellerName"));
}
~~~

Với `LEFT JOIN`, `sellerName` có thể `MISSING` hoặc null nếu không có Seller tương ứng. Quyết định hiển thị `"Chưa xác định"` hay lỗi tùy nghiệp vụ; không ép DTO này thành entity Product hoặc Seller rồi save.

Mỗi JOIN có thể nhân số rows nếu join key không duy nhất; việc map một row thành một DTO không tự sửa sai cardinality, duplicate, missing hoặc quyền tenant phía Seller. Áp predicate tenant/authorization trên **mọi nguồn**.

## 26. Search hit: ID và score không phải entity

Search Service trả `SearchResult` gồm các hit (`SearchRow`). Một hit có:

- `id()`: document key được index.
- `score()`: điểm liên quan của query.
- `index()`: tên Search index.
- `fieldsAs(JsonObject.class)`: các stored fields được yêu cầu.
- `fragments()`: highlights nếu có.
- Metadata riêng `SearchMetaData`, có thể có partial errors.

Ví dụ:

~~~java
import com.couchbase.client.java.search.SearchResult;
import com.couchbase.client.java.search.result.SearchRow;
import com.couchbase.client.java.json.JsonObject;

public record ProductSearchHit(
        String id,
        double score,
        String name) {}

public List<ProductSearchHit> mapHits(
        SearchResult result) {

    if (!result.metaData().errors().isEmpty()) {
        throw new IllegalStateException(
                "Search results may be incomplete");
    }

    return result.rows().stream()
            .map(hit -> {
                JsonObject fields =
                        hit.fieldsAs(JsonObject.class);

                return new ProductSearchHit(
                        hit.id(),
                        hit.score(),
                        fields.getString("name"));
            })
            .toList();
}
~~~

**Tiền đề:** Search query đã yêu cầu `fields("name")` và Search index mapping đã bật **store** cho trường name. Nếu không, `fieldsAs(...)` không tự truy vấn KV để lấy `name`.

Điểm `score` có thể đổi giữa query/index state. Không dùng nó làm CAS, timestamp, số thứ tự cố định hay business priority tuyệt đối. `fragments()` dùng để trình bày, không dùng làm body để ghi trở lại.

## 27. Search stored fields cần được xem là dữ liệu có thể cũ

Một Search hit có `priceCents=145000` trong stored fields, nhưng Product nguồn có thể vừa được đổi giá thành 150000 và Search index chưa ingest mutation.

Với UI preview có thể stale, việc dùng stored fields tiết kiệm KV gets. Nhưng nếu hiển thị **giá checkout**, phải kiểm tra giá hiện hành ở đường dữ liệu nghiệp vụ tại bước chốt.

Hai chiến lược:

| Chiến lược | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Chỉ dùng stored fields từ Search | Ít network KV gets, response nhanh | Có thể stale, field phải được store |
| Search để lấy IDs rồi KV hydrate | Có thể xác minh body/authorization hiện hành | N+1 KV gets, có race giữa hai bước |
| Search + chỉ hydrate một số fields quan trọng | Cân bằng chi phí | Mapping phức tạp, contract rõ field nào authoritative |

Không coi Search hit trả về đầy đủ `ProductEntity` chỉ vì index có `name`, `price` và `category`. Một Search index không mang mọi annotation, CAS và lifecycle của Spring Data.

## 28. Hydration từ Search IDs sang DTO hiện hành

Luồng:

~~~text
Search query -> [ProductHit(id, score), ...]
                   |
                   +-- KV get(id) / Repository findById(id)
                   |
                   +-- Check active, tenant, document type
                   |
                   +-- Map ProductCard + attach score
                   |
                   v
              Search response
~~~

Một record:

~~~java
public record RankedProductCard(
        String id,
        String name,
        long priceCents,
        String currency,
        double score) {}
~~~

Hydration đồng bộ **giới hạn số hits**:

~~~java
public List<RankedProductCard> hydrateHits(
        Collection products,
        SearchResult search,
        ProductCardMapper mapper) {

    List<RankedProductCard> cards = new ArrayList<>();

    for (SearchRow hit : search.rows()) {
        GetResult current = products.get(hit.id());
        ProductCard card = mapper.fromJson(
                hit.id(), current.contentAsObject());

        cards.add(new RankedProductCard(
                card.id(),
                card.name(),
                card.priceCents(),
                card.currency(),
                hit.score()));
    }

    return cards;
}
~~~

Đây là ví dụ **shape mapping**, chưa xử lý đủ:

- Hit đã bị xóa/TTL hết hạn → `DocumentNotFoundException`.
- Product vừa chuyển `active=false` hoặc đổi tenant/schema → phải re-check.
- Search index có nhiều collections → `hit.id()` không đủ để biết cần hydrate collection nào.
- Mỗi hit thêm một KV get → N+1 reads, cần bounded concurrency nếu nhiều hits.
- Nếu các KV gets thất bại, API phải quy định partial results hay fail; không tùy tiện bỏ lỗi.
- Không tin index score/ID như một proof authorization.

Với async hydration, chú ý **bảo toàn thứ tự relevance** bằng `flatMapSequential`/`concatMap` nếu UI yêu cầu; `flatMap` có thể đảo thứ tự theo completion.

## 29. Analytics rows là kết quả phân tích, không phải entity

Analytics SDK:

~~~java
import com.couchbase.client.java.analytics.AnalyticsResult;

AnalyticsResult result = cluster.analyticsQuery(
        """
        SELECT o.channel AS channel,
               COUNT(*) AS orderCount,
               SUM(o.totalCents) AS revenueCents
        FROM `shop`.sales.orders AS o
        WHERE o.tenantId = $tenantId
          AND o.status = "PAID"
        GROUP BY o.channel
        ORDER BY revenueCents DESC, channel ASC
        """,
        analyticsOptions().parameters(
                JsonObject.create()
                        .put("tenantId", tenantId)));
~~~

Mapper:

~~~java
public record ChannelRevenue(
        String channel,
        long orderCount,
        long revenueCents) {}

List<ChannelRevenue> reports =
        result.rowsAsObject().stream()
                .map(row -> new ChannelRevenue(
                        row.getString("channel"),
                        row.getLong("orderCount"),
                        row.getLong("revenueCents")))
                .toList();
~~~

Một `ChannelRevenue` là **một nhóm** trong Analytical query, không có ID/CAS chung của các Order nguồn. `AnalyticsMetaData` mô tả truy vấn, không biến row aggregate thành entity có thể `save`.

Cũng có `AnalyticsResult.rowsAs(ChannelRevenue.class)` khi serializer/schema tương thích. Nhưng vẫn cần kiểm tra currency, số lớn, NULL/MISSING, loại nhóm và quyền tenant.

**Analytics ingestion có thể trễ** so với Data Service. Mapping sang DTO không làm dữ liệu tức thời mới lên, và `AnalyticsScanConsistency` không tạo snapshot bất biến xuyên nhiều báo cáo theo mặc định.

## 30. Sub-document `lookupIn` trả từng path theo thứ tự spec

Couchbase sub-document lookup đọc một phần JSON document, ví dụ chỉ cần tên và trạng thái:

~~~java
import com.couchbase.client.java.kv.LookupInResult;
import com.couchbase.client.java.kv.LookupInSpec;
import java.util.List;

LookupInResult result = products.lookupIn(
        id,
        List.of(
                LookupInSpec.get("name"),
                LookupInSpec.get("active")));

String name = result.contentAs(0, String.class);
Boolean active = result.contentAs(1, Boolean.class);
long cas = result.cas();
~~~

Lưu ý:

1. Index `0` và `1` là vị trí **spec trong request**, không phải tên field.
2. `LookupInResult` không tự tạo entity Product đầy đủ.
3. Nếu path thiếu, phải xét semantics của `LookupInResult.exists(index)` hoặc lỗi path theo SDK/version.
4. `result.cas()` là CAS của document tại thời điểm lookup, không phải một CAS trên từng field.
5. Có thể dùng sub-document lookup để giảm payload nhưng không áp dụng trực tiếp Spring converter/annotation.
6. Không dùng kết quả hai field làm full body của `repository.save(...)`.

Sub-document mutation (`mutateIn`) cũng có result theo spec index, nhưng đó là **kết quả mutation** với semantics riêng; không hoán đổi với `LookupInResult`.

## 31. KV counter và binary result là scalar, không phải JSON object

Ví dụ:

~~~java
import static com.couchbase.client.java.kv.IncrementOptions.incrementOptions;

long after = counters.binary()
        .increment(
                "visits::tenant-01::2026-11-25",
                incrementOptions().initial(1).delta(1))
        .content();
~~~

`CounterResult.content()` là giá trị số **sau mutation**. Full-document KV counter có dạng non-JSON theo semantics Couchbase; không gọi `contentAsObject()` hay map nó vào entity JSON có `@Document`.

Cần nhớ:

- Full-document counter dùng miền **unsigned 64-bit** theo server.
- Java `long` signed có thể hiển thị giá trị lớn như số âm.
- Khi cần biểu diễn unsigned, dùng `Long.toUnsignedString(raw)` và policy range phù hợp.
- Decrement KV full-document chặn tại 0, khác JSON sub-document counter signed.
- Counter một key nguyên tử không đảm bảo event đúng một lần khi timeout/retry.
- Một scalar counter không có tenant/createdAt/metadata fields trong body JSON.

Một DTO phù hợp:

~~~java
public record VisitCount(
        String counterKey,
        String unsignedValue) {}
~~~

`unsignedValue` là biểu diễn decimal string khi domain cần giữ trọn unsigned range; trong ứng dụng giới hạn dưới `Long.MAX_VALUE`, có thể chọn `long` với validation rõ.

## 32. Metadata result không nên trộn vào DTO nghiệp vụ một cách vô thức

Với SQL++:

~~~java
QueryResult result = cluster.query(statement, options);

var rows = result.rowsAsObject();
var metadata = result.metaData();
~~~

`QueryMetaData` có `requestId`, `clientContextId`, `status`, `warnings`, `metrics()` và profiling tùy options.

Các thuộc tính đó phục vụ:

- Quan sát latency/throughput của query.
- Truy vết request trong logs.
- Phân tích index/query plan.
- Phân loại warning/errors.
- Đối chiếu thông tin consistency/trace.

Chúng **không thuộc ProductCard hoặc ChannelRevenue**. Một thiết kế có thể trả:

~~~java
public record QueryEnvelope<T>(
        List<T> items,
        String requestId,
        int warningCount) {}
~~~

Nhưng chỉ expose metadata ra controller/API nếu hợp đồng yêu cầu. Public API thường nên trả DTO business và một subset metadata an toàn (ví dụ pagination), còn requestId và diagnostic đặt vào logs/traces nội bộ.

Khi SDK error/timeout, có thể **không có `QueryMetaData` thành công**; xử lý exception/ErrorContext riêng, không giả định luôn có envelope.

## 33. Phân trang: `items`, `hasNext` và `total` khác nhau

Một Search/SQL++ data query với `LIMIT 21` để phục vụ pageSize=20 có thể trả 21 rows. Mapper:

~~~java
public record SliceWindow<T>(
        List<T> items,
        boolean hasNext) {}

public <T> SliceWindow<T> toSlice(
        List<T> fetched,
        int pageSize) {

    if (pageSize < 1) {
        throw new IllegalArgumentException("Invalid size");
    }

    boolean hasNext = fetched.size() > pageSize;
    List<T> content = fetched.subList(
            0, Math.min(pageSize, fetched.size()));

    return new SliceWindow<>(
            List.copyOf(content), hasNext);
}
~~~

**Tiền đề**: query thực sự yêu cầu `LIMIT pageSize+1` và OFFSET/keyset tính đúng theo `pageSize` ban đầu. `hasNext` chỉ phản ánh **lần đọc hiện tại**, không tạo snapshot giữa nhiều trang.

Nếu cần tổng số item theo filter, thường phải chạy `COUNT` riêng. `QueryMetrics.resultCount()` chỉ là số rows query trả, không phải total. Với `GROUP BY`, tổng cho `Page<AggregateDto>` là số nhóm, không phải số documents nguồn.

Đừng dựng `PageImpl<>(items, pageable, result.metaData().metrics().resultCount())` như thể resultCount là total source documents.

## 34. Khi nào nên trả `Optional` hoặc outcome riêng?

Một DAO có thể gặp:

1. Document key thực sự không tồn tại.
2. Document tồn tại nhưng thiếu field tùy chọn.
3. Document tồn tại với field JSON null.
4. Document có field sai kiểu.
5. SDK không đọc được do network/permission.
6. Query trả 0 rows hợp lệ.
7. Search trả hits nhưng có partial errors.
8. Analytics index chưa ingest source mutation.

Không nên biểu diễn tất cả bằng `Optional.empty()`.

| Tình huống | Biểu diễn ứng dụng phù hợp |
| --- | --- |
| KV not found, endpoint cho phép thiếu | `Optional<ProductCard>` hoặc domain NotFound |
| Optional field thiếu/null | Nullable field / explicit field state theo policy |
| Schema sai | Mapping/validation exception, quarantine |
| SDK timeout/permission | Technical failure được phân loại |
| Query 0 rows | List rỗng hợp lệ |
| Search partial errors | Partial result có nhãn hoặc fail theo completeness contract |
| Analytics stale | Freshness/asOf policy riêng, không giả 404 |

Khi map batch read, dùng per-key outcomes thay vì nuốt toàn bộ `DocumentNotFoundException` và mọi lỗi khác thành `Mono.empty()`.

## 35. Reactive mapping: `Flux` đúng nơi, không `block()`

Với Spring WebFlux:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.query.ReactiveQueryResult;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Flux;

public Flux<ProductCard> streamCards(
        Cluster cluster,
        String statement,
        JsonObject params,
        ProductCardMapper mapper) {

    return cluster.reactive()
            .query(
                    statement,
                    queryOptions()
                            .parameters(params)
                            .readonly(true))
            .flatMapMany(ReactiveQueryResult::rowsAsObject)
            .map(row -> mapper.fromJson(
                    row.getString("id"), row));
}
~~~

Yêu cầu:

- Câu `statement` đã có **`LIMIT` hoặc phạm vi tập dữ liệu có kiểm soát** khi API trả danh sách.
- `mapper.fromJson` là hàm đồng bộ nhẹ, không gọi `block()` hoặc network bên trong.
- Nếu mapper ném validation exception, stream phát `onError`; caller phải có policy rõ.
- Reactive không biến SQL++ thành transaction/snapshot.
- Không `collectList()` hàng triệu rows.
- Nếu cần client-facing API list nhỏ, `collectList()` có thể hợp lý sau server-side limit.
- Không gọi `subscribe()` trong service rồi trả response trước khi kết quả tới.

### Metadata của reactive query

`ReactiveQueryResult.metaData()` trả `Mono<QueryMetaData>`. Metadata thường chỉ sẵn sàng **sau khi rows được tiêu thụ**. Nếu cần cả rows lẫn metadata cho một response nhỏ, consume rows trước, sau đó mới lấy metadata, không ép metadata phải có trước.

## 36. Reactive hydration nhiều Search hits cần giữ thứ tự

Nếu Search trả hits theo relevance:

~~~text
A(score=3.9), B(score=3.2), C(score=2.4)
~~~

và bạn dùng:

~~~java
Flux.fromIterable(hits)
        .flatMap(hit -> getCurrentCard(hit.id()), 16);
~~~

KV GET có thể trả B, C trước A; UI sẽ mất relevance order.

Sử dụng:

~~~java
Flux<RankedProductCard> ordered =
        Flux.fromIterable(hits)
                .flatMapSequential(
                        hit -> getCurrentCard(hit.id())
                                .map(card -> new RankedProductCard(
                                        card.id(), card.name(),
                                        card.priceCents(),
                                        card.currency(), hit.score())),
                        16);
~~~

`getCurrentCard(...)` là **helper ứng dụng** trả `Mono<ProductCard>`, không phải phương thức SDK tự có.

Lưu ý:

- `flatMapSequential` bảo toàn **thứ tự kết quả**, không tạo snapshot của các KV reads.
- Khi một ID đã bị xóa, cần chính sách bỏ qua hoặc lỗi có ghi nhận; không để 404 làm cả stream sai ngữ nghĩa nếu UI cho phép partial.
- Khi một Product khác tenant hoặc inactive, phải fail closed hoặc loại khỏi API theo contract.
- Nếu Search index có nhiều collections, định tuyến hydrate theo keyspace đáng tin, không chỉ ID.
- Giới hạn concurrency và số hits; một page 20 hits không nên tự bắn hàng nghìn requests.
- Không lấy stale Search field làm source-of-truth cho giá hoặc quyền.

## 37. Mapper không được vượt ranh giới quyền truy cập

Ví dụ SDK trả body:

~~~json
{
  "tenantId": "tenant-01",
  "name": "Cà phê",
  "priceCents": 145000,
  "costPriceCents": 90000,
  "internalNotes": "Nhà cung cấp hợp đồng riêng"
}
~~~

DTO public chỉ nên chứa:

~~~java
public record PublicProduct(
        String id,
        String name,
        long priceCents) {}
~~~

Nếu trả `JsonObject` thẳng từ controller, client có thể nhìn thấy `costPriceCents`/`internalNotes` dù SQL++/SDK đọc thành công.

Quy tắc:

1. Tenant lấy từ authenticated context, không tin `tenantId` trong request.
2. Query phải lọc tenant, và get theo ID cũng phải authorize.
3. Mapper chuyển sang **allowlisted fields**, không serialize raw body.
4. Không dùng `row.toMap()` rồi trả toàn bộ map nếu chưa lọc.
5. Không expose Search highlights/stored fields của tenant khác.
6. Không trộn diagnostic metadata, PII và sensitive errors vào DTO public.
7. Không cho user tự chọn field names/sort expressions mà không có allowlist.
8. Nếu app dùng một SDK account có quyền rộng, business authorization vẫn bắt buộc.
9. Test cả trường hợp key nằm đúng định dạng nhưng thuộc tenant khác.

**Chuyển đổi dữ liệu là một điểm thực thi bảo mật**, không chỉ là thao tác kỹ thuật.

## 38. Schema evolution và versioned mapper

Dữ liệu JSON có thể có:

~~~json
{
  "schemaVersion": 1,
  "product_name": "Cà phê",
  "priceCents": 145000
}
~~~

hoặc:

~~~json
{
  "schemaVersion": 2,
  "name": "Cà phê",
  "priceCents": 145000,
  "currency": "VND"
}
~~~

Nếu ứng dụng hỗ trợ cả hai:

~~~java
public ProductCard mapVersioned(
        String id,
        JsonObject row) {

    Integer version = row.getInt("schemaVersion");

    if (version == null || version == 1) {
        return mapV1(id, row);
    }
    if (version == 2) {
        return mapV2(id, row);
    }
    throw new IllegalArgumentException(
            "Unsupported product schemaVersion");
}
~~~

`mapV1`/`mapV2` là **mappers ứng dụng** phải được hiện thực và kiểm thử, không phải SDK API.

Đừng rải fallback như `getString("name") != null ? ... : getString("product_name")` khắp code; điều đó có thể vô tình coi field null hợp lệ là thiếu, hoặc che migration chưa hoàn tất.

Ưu tiên một nơi sở hữu translation theo version, test fixtures có đủ versions và kế hoạch loại bỏ support cũ. Khi thay field JSON của Spring Data `@Field`, cập nhật cả SDK raw mapper.

## 39. Khi nào chọn converter tùy chỉnh thay mapper thủ công?

Có hai hướng chính:

**A. Mapper tường minh ở adapter**

Phù hợp khi:

- Result chỉ có vài field/aliases.
- DTO khác entity.
- Cần validation nghiêm ngặt cho tiền/ngày/trạng thái.
- Cần versioning/schema evolution.
- Một service đọc cả KV, SQL++ và Search hits với shapes khác nhau.
- Cần kiểm soát tuyệt đối field expose và lỗi từng item.

**B. `JsonSerializer`/`Transcoder` tùy chỉnh của SDK**

Phù hợp khi:

- Có quy ước serialization JSON chung cho rất nhiều DTO/POJO.
- Cần hỗ trợ Java time/custom modules hoặc JSON library khác.
- Có yêu cầu non-JSON document hay raw bytes.
- Đã đo performance và xác định serialization là bottleneck.
- Team có khả năng quản lý serializer ở toàn cluster/environment.

Một custom SDK serializer **vẫn không tự thay thế Spring Data entity mapping** và các callbacks. Đừng viết serializer riêng chỉ để bỏ qua validation ở adapter; serializer giải quyết bytes/objects, còn **ý nghĩa domain** nằm ở lớp ứng dụng.

## 40. Non-JSON documents và `RawJsonTranscoder`

Couchbase có thể lưu non-JSON string/binary. SDK cho phép custom transcoders:

~~~java
import com.couchbase.client.java.codec.RawJsonTranscoder;

GetResult result = collection.get(
        id,
        getOptions()
                .transcoder(RawJsonTranscoder.INSTANCE));

String json = result.contentAs(String.class);
~~~

`RawJsonTranscoder` trong ví dụ yêu cầu dữ liệu được lưu theo **JSON common flag** và trả raw JSON; bạn phải giải mã/validate chuỗi theo serializer phù hợp nếu cần DTO.

Với raw binary:

~~~java
import com.couchbase.client.java.codec.RawBinaryTranscoder;

GetResult result = collection.get(
        id,
        getOptions()
                .transcoder(RawBinaryTranscoder.INSTANCE));

byte[] bytes = result.contentAs(byte[].class);
~~~

Không gọi `contentAsObject()` trên binary data rồi kỳ vọng một JSON object. SQL++, Search và Analytics chủ yếu làm việc với JSON data, không biến raw binary documents thành fields searchable/queryable mặc định.

**Không chọn RawJsonTranscoder để “tăng tốc” mọi entity** khi chưa biết chuẩn flags, serializer và mapping của hệ thống. Sai transcoder có thể làm application decode sai hoặc vô tình thay định dạng khi ghi.

## 41. Lỗi mapping: không đổi thành danh sách rỗng

Các lỗi có thể xảy ra:

| Tầng | Ví dụ | Xử lý đúng |
| --- | --- | --- |
| KV | `DocumentNotFoundException` | NotFound theo contract |
| KV/SQL++ | Timeout/permission | Technical failure, không giả dữ liệu thiếu |
| SDK decoding | `DecodingFailureException` | Mapping/schema error |
| JSON shape | `SELECT p` nhưng mapper đợi `name` top-level | Sửa SQL++/mapper |
| Numeric | `priceCents` là decimal/overflow | Validation failure |
| Date | Timestamp sai format/timezone | Validation failure |
| Enum | Giá trị mới không hỗ trợ | Version policy hoặc quarantine |
| Search | Hit thiếu stored field | Fix index mapping/hydrate |
| Search | Partial `metaData().errors()` | Có thể incomplete result, policy rõ |
| Analytics | Ingestion lag | Freshness policy, không thay lỗi mapping |
| Security | Row khác tenant | Fail closed/audit |
| Reactive | Mapper throw | Pipeline error, không nuốt bằng `Mono.empty()` chung |

Nguy hiểm:

~~~java
try {
    return result.rowsAsObject().stream()
            .map(mapper::map)
            .toList();
} catch (Exception ignored) {
    return List.of();
}
~~~

Một response rỗng có thể là business result hợp lệ. Nuốt mọi exception khiến lỗi schema/permission thành “không có hàng nào” và rất khó đối soát.

Nếu nghiệp vụ cho phép bỏ qua một số records hỏng (import best-effort), hãy tạo **per-row outcome** gồm source key/row index, error category và quarantine/checkpoint; không âm thầm mất dữ liệu.

## 42. Hiệu năng và memory khi chuyển đổi

`QueryResult.rowsAsObject()`/`rowsAs(...)` của **blocking SDK** trả `List` và có thể materialize nhiều row ở client. Với API giới hạn nhỏ, điều này dễ dùng. Với báo cáo hàng triệu rows:

- Đặt `LIMIT`/paging/batching ở query nếu phù hợp.
- Sử dụng reactive `rowsAsObject()`/`rowsAs(Class<T>)` để stream rows.
- Đừng `collectList()` một stream không giới hạn.
- Mapper phải là pure/lightweight; nếu gọi KV bên trong, cần bounded concurrency.
- Chọn projection nhỏ để tránh decode field không dùng.
- Tránh decode `JsonObject` → map → JSON string → POJO → API JSON nhiều lần nếu không cần.
- Khi chọn direct `rowsAs(Class<T>)`, đo giảm allocation thật thay vì giả định luôn nhanh hơn.
- Dữ liệu tiền/số lớn phải ưu tiên correctness trước micro-optimization.
- Log body JSON lớn dễ tạo PII leakage và tăng tải CPU/IO.

### Kiểm tra location bottleneck

| Thấy chậm ở đâu? | Kiểm tra |
| --- | --- |
| Query server | GSI/index, `EXPLAIN`, metrics, scan consistency |
| JSON decoding | Serializer/mapper CPU, allocations/GC |
| Hydration | Số KV gets, concurrency, not-found rate |
| Reactive stream | Backpressure, slow consumers, cancellation |
| HTTP response | JSON serialization, payload bytes, client network |
| Search | Index lag, Search query scoring/facets/partial errors |
| Analytics | Ingestion lag, query compute, datasets |

Không đổi SDK serializer để sửa một query đang full scan. Không tăng concurrency vô hạn khi bottleneck là hotspot hoặc payload lớn.

## 43. Unit test mapper theo bảng dữ liệu

Với `ProductCardMapper`, viết test cho các fixtures:

| Case | JSON input | Kỳ vọng |
| --- | --- | --- |
| Chuẩn | `name` string, `priceCents` integer, `currency` string | DTO đúng |
| Thiếu name | Không có `name` | Validation error |
| Null name | `"name":null` | Validation error |
| Empty name | `"name":""` | Validation error nếu policy |
| Missing price | Không có `priceCents` | Validation error |
| Fractional price | `"priceCents":10.5` | Bị từ chối, không làm tròn |
| Numeric string | `"priceCents":"100"` | Bị từ chối nếu contract numeric |
| Negative price | `"priceCents":-1` | Bị từ chối |
| Currency unknown | `"currency":"XYZ"` | Xác minh policy |
| Unknown category | `"category":"MATCHA"` | Version/enum policy |
| Invalid date | `"createdAt":"tomorrow"` | Validation error |
| V1/V2 schema | Tên field khác nhau | Dùng versioned mapper |
| Extra sensitive field | `internalNotes` có mặt | Không xuất hiện trong DTO API |

Ví dụ unit test trực tiếp:

~~~java
@Test
void mapsNormalProductCard() {
    JsonObject json = JsonObject.create()
            .put("name", "Cà phê")
            .put("priceCents", 145000L)
            .put("currency", "VND");

    ProductCard card = new ProductCardMapper()
            .fromJson("product::1", json);

    assertEquals("product::1", card.id());
    assertEquals(145000L, card.priceCents());
}
~~~

Các imports JUnit/SDK và declaration classes cần đặt theo cấu trúc code project thực tế. Unit test mapper **không cần Couchbase Server**, nhưng không thay integration test converter/SDK đầy đủ.

## 44. Integration test SDK, Spring Data và JSON schema

Bộ test nên có các ca:

1. **KV**: insert một JSON Product, SDK get → DTO đúng, ID từ key, CAS từ `GetResult`.
2. **Spring Repository**: save entity có `@Field("product_name")`, đọc bằng SDK raw field đúng; đọc lại Repository thấy domain property khớp.
3. **Optimistic locking**: SDK snapshot CAS → writer khác update → replace với CAS cũ phải conflict.
4. **Expiry**: nếu yêu cầu, get `withExpiry(true)`; kiểm tra mapping expiry metadata rõ ràng.
5. **SQL++**: `SELECT` alias object, `SELECT p`, `SELECT RAW p`, `SELECT RAW COUNT` và `GROUP BY` cho đúng shape.
6. **Numeric**: các kiểu JSON integer/decimal/overflow; không để mất precision do unboxing/coercion.
7. **Nested**: optional seller/tags, NULL/MISSING, JSON arrays và unknown enum.
8. **Search**: index có stored field, mapper đọc score/ID; index thiếu stored field có policy hydrate.
9. **Search freshness**: vừa update giá/active, Search stale hit nhưng KV hydration kiểm tra hiện hành.
10. **Analytics**: aggregate DTO và ingestion lag khác Query Service.
11. **Multi-tenant**: key tồn tại ở tenant khác, mapper không rò rỉ dữ liệu.
12. **Reactive**: rows được chuyển sang Flux đúng thứ tự theo contract, lỗi mapper propagate.
13. **Metadata**: Query/Analytics/Search không bị ép cùng một schema metadata.
14. **Wrong keyspace**: cùng ID ở hai collections không bị đọc nhầm.
15. **Error**: timeout/permission không bị convert thành empty DTO.

Test trên Couchbase thật/phiên bản khóa để xác minh SDK serializer và Spring mapping. Không chỉ kiểm thử Java mapper rồi kết luận end-to-end đã đúng.

## 45. Case study: lỗi mất dữ liệu do dùng projection làm entity

Một service có document:

~~~json
{
  "tenantId": "tenant-01",
  "name": "Cà phê",
  "priceCents": 145000,
  "currency": "VND",
  "description": "Rang mộc",
  "inventory": 99
}
~~~

Để tiết kiệm bandwidth, developer query:

~~~sql
SELECT META(p).id AS id,
       p.name AS name,
       p.priceCents AS priceCents
FROM `shop`.`catalog`.`products` AS p
WHERE META(p).id = $id;
~~~

Rồi dựng một `ProductEntity` với ba field và gọi:

~~~java
repository.save(partialEntity);
~~~

**Rủi ro:** những fields `currency`, `description`, `inventory` không nằm trong projection có thể bị mất/ghi đè tùy converter/save semantics. CAS/version cũng có thể thiếu hoặc không khớp.

Thiết kế đúng hơn:

- Dùng projection thành **ProductCard/read-only DTO**, không save.
- Khi cần chỉnh sửa, dùng Repository/Template để đọc entity **đầy đủ** với `@Version`, sau đó update theo domain.
- Hoặc dùng SDK `mutateIn` cho path cụ thể, hoặc CAS replace full body với validation.
- Đảm bảo tenant authorization tại thời điểm mutation.
- Test thay đổi cạnh tranh và các fields không nằm trên UI.

**Bài học:** Tối ưu projection là tối ưu **đường đọc**. Nó không tự trở thành một aggregate/entity hợp lệ để ghi.

## 46. Checklist code review

### Định nghĩa kết quả

- [ ] Phân biệt KV `GetResult`, SQL++ `QueryResult`, Analytics `AnalyticsResult` và Search `SearchResult`.
- [ ] DTO có tên/phạm vi rõ; không ép aggregate/search hit thành entity.
- [ ] ID, CAS, expiry và query diagnostics được lấy từ đúng nguồn metadata.
- [ ] `SELECT` aliases và DTO fields được kiểm thử chung.
- [ ] `SELECT RAW` scalar/object/array được decode theo đúng shape.
- [ ] Mapper định nghĩa null/missing/default rõ, không unbox bừa.
- [ ] Số tiền/decimal/timezone/enum được validate theo domain.
- [ ] Nested JSON và relationship có schema/authorization cụ thể.

### Spring Data và an toàn ghi

- [ ] SDK serializer khác Spring `CouchbaseConverter` được hiểu đúng.
- [ ] `@Field`, `@Version`, auditing và TTL không bị giả định tự chạy trên raw SDK.
- [ ] Không save partial projection thành entity full document.
- [ ] Khi ghi có điều kiện, dùng CAS/transaction theo invariant.
- [ ] Không return raw `JsonObject` chứa field nội bộ trong API.
- [ ] Tenant authorization được thực thi cho cả query và KV hydration.
- [ ] Error decode/permission không bị nuốt thành empty list.

### Reactive, observability và QA

- [ ] Reactive mapping không block event-loop.
- [ ] Query/stream có server-side limit hoặc batch strategy.
- [ ] Async hydration giữ relevance order khi cần.
- [ ] Search partial errors/freshness được kiểm tra.
- [ ] Analytics ingestion lag không nhầm với lỗi mapping.
- [ ] Metrics không gắn PII/document ID vào high-cardinality labels.
- [ ] Có unit tests cho schema variations và integration tests trên Couchbase thật.
- [ ] Có test tương thích serializer/SDK và Spring Data versions đang dùng.

## 47. Bài tập thực hành

**Phần A — KV mapper**

1. Tạo `shop.catalog.products` và seed ít nhất 10 Product có tên tiếng Việt, tiền VND, currency và createdAt UTC.
2. Tạo `ProductCardMapper` với validation name/price/currency.
3. Dùng Spring-managed `Cluster` và `Collection.get(id)`.
4. Trả `ProductCard`, lấy ID từ document key, không từ body không tồn tại.
5. Tạo `ProductSnapshot` gồm body và CAS; thử replace kèm CAS.
6. Thử document thiếu name/price, field null và price decimal.
7. Đọc expiry metadata với `withExpiry(true)` nếu deployment hỗ trợ.
8. So SDK raw mapping với Spring Data `@Field`/`@Version`.

**Phần B — SQL++ và Analytics**

1. Viết query projection có `META(p).id AS id`.
2. Ánh xạ bằng `rowsAsObject()` và thử `rowsAs(ProductCard.class)`.
3. So `SELECT p`, `SELECT RAW p` và projection phẳng.
4. Dùng `SELECT RAW COUNT(*)`, đọc scalar thay vì JsonObject.
5. Chạy `GROUP BY category`, trả `CategorySummary` không phải entity.
6. Chạy một Analytics aggregate; ghi rõ ingest freshness và report DTO.
7. Xác nhận `QueryMetrics.resultCount` không phải business total.

**Phần C — Search/hydration**

1. Tạo FTS index có stored field name và query 20 hits.
2. Chuyển hit thành `ProductSearchHit(id,score,name)`.
3. Bỏ stored field name, áp dụng policy KV hydrate.
4. Giả lập stale index sau cập nhật active/price; hydrate current body và kiểm tra quyền.
5. Dùng reactive `flatMapSequential` để giữ thứ tự Search relevance.
6. Ghi nhận partial Search errors khi cần kết quả đầy đủ.
7. Không đưa `fragments` HTML trực tiếp vào DOM không sanitize.

**Phần D — Kiểm thử chất lượng và bảo mật**

1. Viết bảng test missing/null/number/enum/timezone.
2. Viết schemaVersion V1/V2 mapper, kiểm thử migration.
3. Dùng một key ở tenant khác và xác minh không bị trả.
4. Kiểm tra DTO public không chứa costPrice/internalNotes.
5. Thử query SQL++ sai alias và quan sát mapping failure.
6. Thử decoder/serializer khác nhau ở SDK và Spring Data.
7. Thử query lớn và quan sát heap/GC với blocking vs reactive.
8. Viết ADR chọn mapper tường minh hay SDK direct DTO mapping cho từng use case.

### Câu hỏi tự kiểm tra

1. KV `GetResult` khác SQL++ `QueryResult` ở những thành phần nào?
2. Vì sao document ID và CAS không nhất thiết nằm trong body JSON?
3. `contentAs(ProductBody.class)` có tự chạy Spring Data `@Field`/`@Version` không?
4. `SELECT p` và `SELECT RAW p` khác JSON shape thế nào?
5. Khi nào dùng `rowsAsObject()` và khi nào `rowsAs(Class<T>)`?
6. `TypeRef<Map<String,Object>>` trong `rowsAs` biểu diễn kiểu gì?
7. Vì sao `SELECT RAW COUNT(1)` không đọc bằng `getLong("total")` trên JsonObject?
8. `MISSING` và `NULL` khác nhau ra sao trong mapper?
9. `getLong` có thể nguy hiểm thế nào nếu JSON số có phần thập phân?
10. Vì sao không nên tự dùng `BigDecimal.valueOf(cents,2)` cho mọi currency?
11. Tại sao timezone của pod không nên là quy tắc phân loại ngày nghiệp vụ?
12. Search `fieldsAs(JsonObject.class)` lấy trường từ đâu?
13. Search hit có chứa CAS của entity để `repository.save` ngay không?
14. Vì sao KV hydrate sau Search cần kiểm tra lại active/tenant/price?
15. Analytics `GROUP BY` tạo một row cho một document hay một nhóm?
16. `LookupInResult.contentAs(index, ...)` đọc từ đâu?
17. `CounterResult.content()` có phải một JSON object không?
18. Reactive `flatMap` hydration có giữ relevance order không?
19. Vì sao `collectList()` trên result lớn gây memory pressure?
20. Lỗi mapping có nên đổi thành list rỗng không?
21. SchemaVersion giúp xử lý migration và unknown fields thế nào?
22. Vì sao partial projection không nên đưa vào `repository.save(...)`?
23. Cần test gì để bảo đảm SDK direct không làm lộ dữ liệu tenant khác?
24. Khi nào nên chọn custom SDK serializer thay mapper ứng dụng?

## 48. Tài liệu chính thức và đối chiếu phiên bản

- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `GetResult`, CAS, expiry và document read.
- [Java SDK API — GetResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/kv/GetResult.html): `contentAsObject`, `contentAs(Class)`, `contentAs(TypeRef)`, `cas` và `expiryTime`.
- [Java SDK API — JsonObject](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/json/JsonObject.html): `getLong`, `getString`, `containsKey`, null và JSON type conversions.
- [Couchbase Java SDK — Transcoders and Non-JSON Documents](https://docs.couchbase.com/java-sdk/current/howtos/transcoders-nonjson.html): `JsonTranscoder`, `JsonSerializer`, `RawJsonTranscoder`, custom Jackson và binary formats.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): `QueryResult`, parameterized query, query options và reactive rows.
- [Java SDK API — QueryResult](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/query/QueryResult.html): `rowsAsObject`, `rowsAs(Class)`, `rowsAs(TypeRef)` và `metaData`.
- [Java SDK API — TypeRef](https://docs.couchbase.com/sdk-api/couchbase-java-client/com/couchbase/client/java/codec/TypeRef.html): generic JSON deserialization.
- [Couchbase Java SDK — Analytics](https://docs.couchbase.com/java-sdk/current/howtos/analytics-using-sdk.html): `AnalyticsResult`, `rowsAs` và Analytics metadata.
- [Couchbase Java SDK — Search](https://docs.couchbase.com/java-sdk/current/howtos/full-text-searching-with-sdk.html): `SearchResult`, `SearchRow`, `fieldsAs`, highlights và partial errors.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): `LookupInResult`, path index và CAS.
- [Couchbase Java SDK — Async and Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): reactive queries, streaming, backpressure và bounded KV fan-out.
- [Spring Data Couchbase — Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): document/entity mapping, metadata và annotations.
- [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): entity reads, optimistic locking và lifecycle.
- [Spring Data Couchbase — Template](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): `CouchbaseTemplate` và mapping khi cần API thấp tầng.

**Lưu ý theo phiên bản:** Ví dụ hướng tới **Couchbase Java SDK 3.x** cùng Spring Data Couchbase tương thích. Tên package/lớp, deserialization behavior, `@Field`/converter, `GetOptions.withExpiry` và `LookupInResult` phụ thuộc dependency/Server đang khóa. Khi đưa vào dự án, hãy xác minh import, JSON schema, serializer, RBAC và integration test trên deployment thực tế. Content QA chuyên môn/biên dịch đầy đủ thuộc giai đoạn kiểm thử sau bước viết bài.

> **Ghi nhớ:** Không chuyển mọi SDK result thành entity. Với KV, giữ **ID và CAS từ metadata**; với SQL++, hiểu **alias và `SELECT RAW` shape**; với Analytics, map **aggregate DTO**; với Search, giữ **hit ID/score** và hydrate khi cần nguồn hiện hành. Phân biệt SDK serialization với Spring Data conversion, validate missing/null/number/timezone, không save partial projection, không lộ field nhạy cảm và không nuốt lỗi mapping. **Một adapter rõ ràng là ranh giới giữ dữ liệu đúng và ứng dụng dễ vận hành.**

