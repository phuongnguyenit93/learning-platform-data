# Giới hạn của mock khi xác minh ngữ nghĩa Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu chính xác **mock repository, mock SDK hoặc fake in-memory** chứng minh được điều gì và không chứng minh được điều gì.
2. Nhận diện các ngữ nghĩa Couchbase phải kiểm tra trên **server thật**: document key, bucket/scope/collection, mapping Java–JSON, KV, SQL++, secondary index, CAS, TTL, transaction và sub-document.
3. Tách **unit test orchestration** khỏi **integration/contract test persistence** để tránh cả hai cực đoan: mock mọi thứ hoặc khởi động database cho mọi phép kiểm tra nhỏ.
4. Xây dựng một bộ test thực tế với JUnit 5, Mockito, Spring Data Couchbase, Testcontainers và Couchbase Java SDK.
5. Phát hiện các tình huống test “xanh giả”: `save` trả object theo stub, truy vấn không được biên dịch/thực thi, optimistic locking được giả lập sai, index chưa sẵn sàng và expiry không phản ánh đồng hồ server.
6. Đặt tiêu chí chất lượng cho CI: kiểm tra nhanh ở unit layer, kiểm tra ngữ nghĩa thật ở integration layer và kiểm thử nâng cấp/tải ở môi trường riêng.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_COUCHBASE**, nơi xây dựng tầng dữ liệu bằng document mapping, repository, `CouchbaseTemplate` và SQL++, đồng thời lựa chọn bucket/scope/collection, index, TTL, CAS, giao dịch và API reactive để bảo đảm nhất quán, hiệu năng và khả năng vận hành.

**Luận điểm trung tâm:** mock có thể giúp xác minh *cách code của ta phản ứng trước một hành vi được giả định*, nhưng **không thể tự chứng minh Couchbase thật sẽ có hành vi ấy**.

## 1. Mock thay thế một hợp đồng, không thực thi cơ chế lưu trữ

Giả sử service thực hiện:

~~~java
Product saved = productRepository.save(product);
~~~

Với Mockito, ta có thể viết:

~~~java
when(productRepository.save(any(Product.class)))
    .thenAnswer(invocation -> invocation.getArgument(0));
~~~

Bài test service sẽ nhận đúng `Product` đã đưa vào. Tuy nhiên, trong test này:

- Không có document nào được tạo trong Couchbase.
- Không có JSON được serialize.
- Không có `@Id` được dùng để xác định document key thật.
- Không có scope/collection nào được truy cập.
- Không có CAS do server cấp hoặc kiểm tra.
- Không có TTL, secondary index, Query Service hoặc transaction nào được thực thi.
- Không có bằng chứng rằng repository đang được Spring Data cấu hình đúng.

Nếu `@Field("price_vnd")` bị đổi nhầm thành `@Field("price_vndd")`, test stub ở trên vẫn có thể PASS. Nếu repository trỏ sang collection sai, test vẫn PASS. Nếu Couchbase không có Query Service hoặc index cần thiết, test vẫn PASS.

Đó **không phải lỗi của Mockito**. Mock đang làm đúng việc của nó: thay thế một dependency bằng phản hồi do test viết ra.

~~~mermaid
flowchart TB
    A["Service gọi repository.save()"] --> B{"Kiểu test?"}
    B -->|"Mock"| C["Mockito trả object được stub"]
    B -->|"Integration"| D["Spring Data converter + Couchbase SDK"]
    D --> E["Couchbase Server / Keyspace"]
    E --> F["Key, JSON, CAS, expiry"]
    C --> G["Kiểm tra nhánh logic service"]
    F --> H["Kiểm tra ngữ nghĩa persistence thật"]
~~~

### 1.1. Định nghĩa để tránh nhầm

| Công cụ | Vai trò | Hạn chế cơ bản |
| --- | --- | --- |
| **Mock** | Định nghĩa trước câu trả lời/exception; kiểm tra tương tác | Không chạy implementation thật của dependency |
| **Stub** | Cung cấp phản hồi cố định theo một tình huống | Không xác minh được hành vi store nếu phản hồi chỉ do test dựng |
| **Spy** | Bọc một object thật, theo dõi hoặc chặn một số lời gọi | Vẫn không phải database; có thể làm thay đổi đường gọi |
| **Fake in-memory** | Có implementation đơn giản như `Map<String, Product>` | Ngữ nghĩa khác Couchbase về JSON, CAS, query, TTL, transaction |
| **Converter-focused test** | Chạy mapping framework thật trên dữ liệu mẫu | Chưa chứng minh server/keyspace/index/CAS hoạt động |
| **Integration test Couchbase** | Chạy Spring Data + SDK + Couchbase thật | Chậm hơn; cần hạ tầng, fixtures, cleanup và consistency |
| **Load/resilience test** | Đo khi có nhiều writer, lỗi/độ trễ và dataset lớn | Cần môi trường đại diện; không thay thế test logic nhỏ |

Một fake có thể được lập trình để **bắt chước CAS hoặc TTL**, nhưng test đó chỉ chứng minh *logic fake mà ta đã viết*, không chứng minh API và phiên bản Couchbase thật hành xử tương ứng. Các fake phức tạp rất dễ trở thành một “database thứ hai” khó duy trì.

## 2. Phân tầng theo loại câu hỏi cần trả lời

Không quyết định dùng mock chỉ vì “unit test thường dùng mock”. Hãy hỏi: **bài test cần chứng minh điều gì?**

| Câu hỏi | Test phù hợp | Có bắt buộc Couchbase thật? |
| --- | --- | --- |
| Giá đơn hàng không được âm? | JUnit unit, domain pure function | Không |
| Service phải từ chối cập nhật khi trạng thái CLOSED? | Unit test + fake/mock port | Không |
| Khi repository báo conflict, service chuyển thành HTTP 409? | Mockito stub exception + controller/service test | Không |
| `@Field("price_vnd")` có lưu đúng JSON key? | Mapping/round-trip test và kiểm tra raw JSON | **Có**, nếu muốn xác nhận đường ghi/đọc thật |
| `@Id` có dùng document key thay vì JSON `id`? | KV integration + SDK read body | **Có** |
| `findById` tìm ở scope/collection nào? | Integration với keyspace cụ thể | **Có** |
| `findByExternalCode` tạo SQL++ và dùng index đúng? | Repository/SQL++ integration, `EXPLAIN` | **Có** |
| Hai writer từ CAS cũ có conflict? | Integration với hai snapshot độc lập | **Có** |
| TTL có làm document hết hạn? | Integration với thời gian server và polling | **Có** |
| Transaction đa document có atomicity đúng? | Transaction integration/fault injection | **Có** |
| Retry có giới hạn 3 lần và dừng đúng? | Unit test policy bằng mock | Không; nhưng cần IT để biết exception thật nào xuất hiện |
| API reactive có subscribe và phát lỗi thật? | StepVerifier + repository thực | **Có**, nếu mục tiêu là I/O và lỗi server |
| 10.000 writer có làm hot document? | Load test trên môi trường phù hợp | **Có**, Testcontainers nhỏ có thể chưa đủ đại diện |

**Định hướng thực tế:** càng gần quyết định lưu trữ, càng phải có ít nhất một test chạy qua đúng implementation và server. Mock vẫn rất có ích ở các lớp **ngoài ranh giới persistence**.

## 3. Ví dụ Product xuyên suốt bài học

Giả sử ứng dụng bán hàng lưu Product ở bucket `shop`, scope `catalog`, collection `products`; để ví dụ test đầu tiên dễ tự chứa, entity Java bên dưới dùng **default scope/collection của bucket test**. Phần kiểm thử named collection sẽ được trình bày riêng, không suy từ test trên default collection.

~~~java
package com.example.shop.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Product {

    @Id
    private String id;

    @Version
    private Long cas;

    @Field("display_name")
    private String displayName;

    @Field("price_vnd")
    private long priceVnd;

    protected Product() {
        // Spring Data materialization.
    }

    public Product(String id, String displayName, long priceVnd) {
        if (id == null || id.isBlank()
                || displayName == null || displayName.isBlank()
                || priceVnd < 0) {
            throw new IllegalArgumentException("Product không hợp lệ");
        }
        this.id = id;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public String getId() { return id; }
    public Long getCas() { return cas; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = newName;
    }

    public void changePrice(long newPrice) {
        if (newPrice < 0) {
            throw new IllegalArgumentException("Giá không thể âm");
        }
        this.priceVnd = newPrice;
    }
}
~~~

Repository:

~~~java
package com.example.shop.catalog;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    List<Product> findByDisplayName(String displayName);
}
~~~

Một service nghiệp vụ:

~~~java
package com.example.shop.catalog;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ProductRepository products;

    public CatalogService(ProductRepository products) {
        this.products = products;
    }

    public Product rename(String id, String newName) {
        Product current = products.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Product không có"));
        current.rename(newName);
        return products.save(current);
    }
}
~~~

Các ví dụ sau dùng ba định danh khác nhau khi cần: **document key** `product::coffee250`, **JSON field** `display_name` và **CAS metadata**. Không đánh đồng ba thứ chỉ vì chúng đều có thể ảnh hưởng quá trình đọc/ghi entity.

## 4. Mock test hữu ích: xác minh orchestration của service

Ví dụ JUnit 5 + Mockito, không có Spring context:

~~~java
package com.example.shop.catalog;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class CatalogServiceTest {

    @Test
    void renamesAndSavesProduct() {
        ProductRepository repository = mock(ProductRepository.class);
        CatalogService service = new CatalogService(repository);

        Product product = new Product(
            "product::coffee250", "Tên cũ", 150000);

        when(repository.findById("product::coffee250"))
            .thenReturn(Optional.of(product));

        when(repository.save(any(Product.class)))
            .thenAnswer(call -> call.getArgument(0));

        Product result = service.rename(
            "product::coffee250", "Cà phê mới");

        assertEquals("Cà phê mới", result.getDisplayName());
        verify(repository).findById("product::coffee250");
        verify(repository).save(product);
        verifyNoMoreInteractions(repository);
    }

    @Test
    void doesNotSaveIfProductIsMissing() {
        ProductRepository repository = mock(ProductRepository.class);
        CatalogService service = new CatalogService(repository);

        when(repository.findById("product::missing"))
            .thenReturn(Optional.empty());

        assertThrows(IllegalArgumentException.class,
            () -> service.rename("product::missing", "Tên khác"));

        verify(repository, never()).save(any(Product.class));
    }
}
~~~

**Những kết luận hợp lệ** sau khi PASS:

- Service gọi `findById` với key được truyền vào.
- Service sửa tên object và gọi `save` đúng một lần trong kịch bản đã stub.
- Nếu `findById` trả empty, service báo lỗi và không ghi.

**Những kết luận không hợp lệ**:

- Product đã được lưu vào Couchbase.
- `@Field("display_name")` đã hoạt động.
- `findById` đã tìm đúng collection.
- `save` bảo vệ CAS, TTL hoặc chống ghi đè.
- Query `findByDisplayName` có index hoặc phát sinh SQL++ đúng.

Một test có thể PASS ngay cả khi bạn đổi `@Field("display_name")` thành `@Field("wrong_name")`, bởi đường mock không đi qua converter.

### 4.1. Đừng kiểm tra implementation quá chặt khi không cần

Trong unit test, `verify(repository).save(product)` có thể hữu ích. Nhưng nếu service được refactor để dùng một port nghiệp vụ khác hoặc phương thức tạo bản sao bất biến, test tương tác quá chi tiết có thể vỡ dù hành vi nghiệp vụ không đổi.

Nên ưu tiên kiểm tra:

1. Kết quả miền và exception mà caller nhìn thấy.
2. Những tương tác **mang ý nghĩa nghiệp vụ** như không ghi khi validation thất bại.
3. Số lần gọi khi nó quan trọng với idempotency, retry hoặc side effects.

Không biến `verifyNoMoreInteractions` thành tiêu chuẩn mặc định cho toàn bộ hệ thống. Mock giỏi kiểm tra một **giao ước được kiểm soát**, không thay kiểm thử hành vi hệ thống.

## 5. Sai lệch mapping: mock cho kết quả xanh dù JSON không đúng

Giả sử một developer vô tình sửa:

~~~java
@Field("display_nmae") // Gõ sai, tên JSON thật phải là display_name.
private String displayName;
~~~

Bài unit test dùng mock vẫn có thể cho kết quả mong đợi vì nó chỉ thao tác Java object.

Trong Couchbase thật, document có thể được ghi thành:

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "display_nmae": "Cà phê mới",
  "price_vnd": 150000
}
~~~

Client SQL++ hoặc ứng dụng khác chờ `display_name` sẽ không đọc được trường mong muốn. Nếu cả `save` và `findById` đều dùng **cùng mapping sai**, một test round-trip đơn thuần vẫn có thể PASS. Do đó nên kiểm tra **cả raw JSON body bằng SDK**:

~~~java
Product saved = repository.save(
    new Product(key, "Cà phê hạt", 150000));

var sdkResult = cluster.bucket("shop_test")
    .defaultCollection()
    .get(saved.getId());

var raw = sdkResult.contentAsObject();
assertEquals("Cà phê hạt", raw.getString("display_name"));
assertFalse(raw.containsKey("display_nmae"));
assertEquals(150000L, raw.getLong("price_vnd"));
~~~

Đây là test mapping với **bằng chứng độc lập**: Spring Data tạo JSON, SDK đọc body gốc. Nếu import dữ liệu có nguồn SDK/legacy, kiểm tra chiều ngược lại:

~~~java
collection.insert(key, JsonObject.create()
    .put("display_name", "Tên từ hệ thống ngoài")
    .put("price_vnd", 150000L));

Product actual = repository.findById(key).orElseThrow();
assertEquals("Tên từ hệ thống ngoài", actual.getDisplayName());
~~~

Khi ứng dụng sử dụng type hint `_class` hoặc subtype, JSON fixture phải phản ánh đúng hợp đồng type mapping. Không nhầm thất bại thiếu type hint với thất bại do field name.

### 5.1. Mock không phát hiện sai scope/collection

Giả sử Product production được đặt tại `shop.catalog.products`, nhưng entity test hoặc config lại dùng default collection. Mock `findById(key)` vẫn trả Product vì nó **không biết keyspace**.

Test thật phải tạo scope/collection tương ứng và kiểm tra hai trường hợp:

- Document cùng key ở **đúng** collection được tìm thấy.
- Document có **cùng chuỗi key** nhưng ở collection khác **không bị đọc nhầm**.

`bucket + scope + collection + document key` mới xác định vị trí thực. Tiền tố `product::` không tự chọn collection, và JSON field `id` không thay thế document key.

### 5.2. Constructor, record và dữ liệu cũ

Một mock có thể trả trực tiếp entity đã khởi tạo, bỏ qua quá trình Spring Data gọi constructor hoặc canonical constructor. Nó không bắt được trường hợp document V1 thiếu field V2, JSON null, sai kiểu, `@TypeAlias` đã đổi hoặc constructor bất biến không nhận được CAS.

Cần fixture thực:

| Dữ liệu | Mock entity mặc định | Test raw JSON → Spring Data |
| --- | --- | --- |
| Field `currency` MISSING | Có thể tự gán `"VND"` trong test | Kiểm chứng reader có thực sự gán đúng theo schema |
| `currency:null` | Dễ gộp với MISSING | Phát hiện khác biệt nếu business cần |
| `price_vnd:"150000"` | Developer cho `150000L` sẵn | Kiểm tra converter xử lý string/số |
| Type hint FQCN cũ | Không có bước resolve type | Bắt lỗi subtype/class refactor |
| `@Id` không nằm trong body | Test object có `id` | Kiểm tra metadata key thực |

Những trường hợp này là **contract tests** giữa dữ liệu lưu trữ và mapper, không thể được khẳng định chỉ từ object dựng trong Java.

### 5.3. Mock CouchbaseTemplate cũng không vượt được ranh giới đó

Khi ứng dụng dùng `CouchbaseTemplate` thay repository, chẳng hạn `template.findById(Product.class).one(key)`, một mock trả sẵn Product vẫn chỉ chứng minh service gọi đúng fluent API theo giả định của test. Nó **không chứng minh** template thật đã phân giải đúng entity metadata, collection, document key, converter hoặc CAS. Nếu code production dùng template, hãy viết ít nhất một integration test thực thi **chính đường template đó**, rồi kiểm tra kết quả bằng SDK và một fixture JSON độc lập. Không thay thế đường template bằng repository trong test rồi coi hai đường đã được kiểm chứng giống nhau.

## 6. KV semantics: insert, replace, upsert và race condition

Couchbase SDK có các thao tác với ngữ nghĩa khác nhau:

| SDK operation | Khái niệm | Một mock có kiểm chứng được server không? |
| --- | --- | --- |
| `insert(key, value)` | Chỉ tạo mới, lỗi nếu key đã tồn tại | Không |
| `upsert(key, value)` | Tạo mới hoặc ghi thay giá trị ở key đó | Không |
| `replace(key, value)` | Thay document phải đang tồn tại; có thể dùng CAS | Không |
| `remove(key)` | Xóa document theo key, có thể có CAS | Không |
| `get(key)` | Đọc KV theo key | Không |
| `lookupIn/mutateIn` | Truy cập hoặc cập nhật một phần document | Không |

Test SDK thật cho `insert`:

~~~java
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

Collection products = cluster.bucket("shop_test")
    .defaultCollection();

String key = "product::insert-test";

products.insert(key,
    JsonObject.create().put("display_name", "Bản đầu"));

assertThrows(DocumentExistsException.class,
    () -> products.insert(key,
        JsonObject.create().put("display_name", "Bản thứ hai")));

assertEquals("Bản đầu",
    products.get(key).contentAsObject().getString("display_name"));
~~~

Nhớ cleanup theo key test hoặc dùng key duy nhất. Nếu muốn test `upsert`, hãy kiểm tra **sau thao tác** body đã thay đổi; không dùng mock `upsert` trả thành công để suy ra overwrite xảy ra đúng.

### 6.1. Check-then-insert không nguyên tử

Sai lầm thường gặp:

~~~java
if (!repository.existsById(key)) {
    repository.save(product);
}
~~~

Một mock có thể được sắp xếp trả `false` cho `existsById`, sau đó cho `save` thành công. Nhưng giữa hai lời gọi, request khác có thể ghi cùng key.

Với yêu cầu “chỉ một document cho một ID nghiệp vụ”, ưu tiên **insert-only operation nguyên tử ở server** và xử lý lỗi duplicate. Nếu cần chống trùng theo một field body không phải key, secondary index thông thường không tự bảo đảm unique; cần thiết kế key/claim document hoặc một cơ chế tương đương.

Ngữ nghĩa race condition phải được thử bằng nhiều thao tác thật hoặc kiểm chứng hợp đồng insert của SDK, không dùng lịch trả lời do mock định sẵn rồi tuyên bố đã chứng minh concurrency.

## 7. SQL++: mock không có Query Service, parser hay optimizer

Một repository có thể khai báo:

~~~java
List<Product> findByDisplayName(String displayName);
~~~

hoặc:

~~~java
@Query("SELECT p.* FROM `shop_test`._default._default p WHERE p.display_name = $1")
List<Product> findMatchingName(String name);
~~~

Cách dùng `@Query` cụ thể cần tuân theo quy tắc projection/metadata của Spring Data Couchbase trên phiên bản đang chạy; câu trên chỉ minh họa nhu cầu kiểm thử.

Mock có thể trả `List.of(product)` với bất kỳ giá trị đầu vào nào. Nó không kiểm tra:

- SQL++ có **đúng cú pháp** không.
- Keyspace và alias trong query có tồn tại không.
- Query có mang type-filter của Spring Data hay không.
- `@Field` có trỏ đúng field body không.
- Có index phù hợp hoặc Query Service/Index Service sẵn sàng không.
- `MISSING` khác `NULL` như thế nào.
- Query có trả đủ ID/type metadata để materialize entity không.
- Planner có dùng index mong muốn và độ trễ có đáp ứng SLO không.

### 7.1. Test SQL++ thực với index

Ví dụ index theo tên:

~~~sql
CREATE INDEX ix_products_display_name
ON `shop_test`.`_default`.`_default`(display_name);
~~~

Khi test:

1. Tạo index từ setup/migration đã kiểm soát.
2. **Chờ index ONLINE/sẵn sàng** bằng trạng thái và timeout, không chỉ sleep cứng.
3. Chèn Product có `display_name` đúng và một Product không khớp.
4. Chạy query/repository thực và xác nhận kết quả.
5. Dùng `EXPLAIN` nếu mục tiêu còn bao gồm chọn index/hiệu năng.

Ví dụ SDK Query cho phép kiểm tra scan consistency:

~~~java
import static com.couchbase.client.java.query.QueryOptions.queryOptions;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;

var results = cluster.query(
    """
    SELECT META(p).id AS documentKey, p.display_name AS displayName
    FROM `shop_test`.`_default`.`_default` AS p
    WHERE p.display_name = $name
    """,
    queryOptions()
        .parameters(JsonObject.create().put("name", "Cà phê hạt"))
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS)
);
~~~

`REQUEST_PLUS` yêu cầu Query Service chờ index bắt kịp theo mức nhất quán đó, đổi lại có thể tăng latency. Một unit test `when(repo.findByDisplayName(...)).thenReturn(...)` không thể chứng minh query thực sẽ thấy mutation vừa ghi trong chế độ scan consistency đang dùng.

### 7.2. MISSING, NULL và index coverage

Mock trả một Java object có `discount = null` không đủ để kiểm tra ba JSON này:

~~~json
{}
~~~

~~~json
{"discount": null}
~~~

~~~json
{"discount": 0}
~~~

Trong SQL++, `discount IS MISSING`, `IS NULL`, `IS VALUED` có ngữ nghĩa riêng. Một secondary index trên field dẫn đầu bị MISSING có thể không chứa các document thiếu field nếu không có tùy chọn/phương án phù hợp. Vì vậy, cần fixture JSON thật + query thật và kiểm tra `EXPLAIN`.

Đừng dùng kết quả mock để khẳng định câu `WHERE discount IS NOT NULL` loại được MISSING; theo SQL++ của Couchbase, `IS NOT NULL` có thể vẫn đúng với MISSING. Dùng `IS VALUED` khi cần loại cả hai.

## 8. CAS / @Version: mock không tự tạo xung đột thật

`@Version` của Spring Data Couchbase liên hệ với **CAS metadata** của document, không phải field `version` đơn thuần trong body JSON. Sau một mutation, server cấp CAS mới; lần ghi với CAS cũ có thể bị từ chối.

Tình huống:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Couchbase
    participant B as Request B
    A->>DB: GET key
    B->>DB: GET key
    DB-->>A: Snapshot CAS=V1
    DB-->>B: Snapshot CAS=V1
    A->>DB: SAVE với CAS=V1
    DB-->>A: Thành công, CAS=V2
    B->>DB: SAVE với CAS=V1
    DB-->>B: CAS mismatch/conflict
~~~

Trong Mockito, bạn có thể viết:

~~~java
when(repository.save(any(Product.class)))
    .thenThrow(new OptimisticLockingFailureException("CAS conflict"));
~~~

Test đó hữu ích để xác minh service **bắt exception và báo lỗi đúng**. Nhưng nó không chứng minh:

- Product có `@Version` đúng.
- CAS được Spring Data nạp từ document metadata.
- Ghi thứ nhất có làm CAS thay đổi không.
- Ghi thứ hai từ snapshot cũ thực sự bị server từ chối.
- `save` có vô tình dùng upsert không kiểm tra CAS hay không.

### 8.1. Test CAS với hai snapshot độc lập

Với Testcontainers/Couchbase thật:

~~~java
@Test
void staleSaveMustNotOverwriteNewerValue() {
    String key = "product::cas::" + UUID.randomUUID();

    try {
        repository.save(new Product(key, "Tên đầu", 100000));

        Product first = repository.findById(key).orElseThrow();
        Product second = repository.findById(key).orElseThrow();

        first.changePrice(120000);
        repository.save(first);

        second.rename("Tên từ snapshot cũ");

        assertThrows(
            org.springframework.dao.OptimisticLockingFailureException.class,
            () -> repository.save(second)
        );

        Product stored = repository.findById(key).orElseThrow();
        assertEquals(120000, stored.getPriceVnd());
    } finally {
        repository.deleteById(key);
    }
}
~~~

**Điều kiện:** test repository thực sự dùng `@Version`, kết nối tới cùng document trong server và đọc **hai instance độc lập**. Với immutable entity/record, phải dùng bản sao tương ứng và kiểm chứng metadata sau `save`. CAS là token opaque: **không viết test yêu cầu CAS tăng đúng 1**.

Một test xung đột phải xác minh **dữ liệu cuối cùng không bị mất cập nhật**, chứ không chỉ một exception được ném ra.

### 8.2. Fake CAS tự viết vẫn không đủ

Một fake `Map<Key, (Value,Version)>` có thể tăng version mỗi lần `save` và từ chối phiên bản cũ. Nó giúp test **retry policy**, nhưng:

- CAS của Couchbase không phải bộ đếm do Java tùy ý tăng.
- API SDK có thể trả kiểu exception và retryability khác.
- `save` của Spring Data có thể dùng cơ chế phát hiện entity mới khác giả định của fake.
- Mutation SQL++ hoặc sub-document bên ngoài có thể thay CAS theo con đường mock chưa mô hình hóa.

Tối thiểu phải có một test end-to-end qua đúng repository hoặc SDK adapter production.

## 9. TTL/expiry: mock không điều khiển đồng hồ server

Couchbase TTL là metadata thuộc **document**, không phải một field JSON `expiresAt` tự động. Test đơn vị của service có thể xác minh chính sách “Cart được tạo với TTL 30 phút” bằng cách kiểm tra tham số được truyền, nhưng không thể xác minh document thật hết hạn.

Ví dụ test bằng SDK:

~~~java
import static com.couchbase.client.java.kv.InsertOptions.insertOptions;
import java.time.Duration;

String key = "cart::ttl::" + UUID.randomUUID();

collection.insert(
    key,
    JsonObject.create().put("customer_id", "customer::u100"),
    insertOptions().expiry(Duration.ofSeconds(3))
);

// Ban đầu tài liệu tồn tại.
assertTrue(collection.exists(key).exists());

// Với Awaitility (dependency test riêng), poll tới khi hết hạn.
await().atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(250))
    .until(() -> !collection.exists(key).exists());
~~~

Chú ý khi thiết kế test:

- Sử dụng document riêng, TTL ngắn và **polling có timeout**, không kỳ vọng hết hạn đúng một thời điểm tới mili-giây.
- Không dùng `Clock.fixed` hoặc Reactor virtual time để “tua nhanh” thời gian của Couchbase Server.
- Kiểm tra `maxTTL` của bucket/collection và mutation options thực tế.
- Kiểm tra đường đọc có chế độ **touch-on-read** hay mutation có preserve expiry không.
- Test riêng khi cần xác nhận document sau cập nhật **giữ nguyên** hoặc **được làm mới** expiry theo policy.

Mock `Clock` phù hợp để kiểm thử ngày khuyến mại hoặc hạn sử dụng nghiệp vụ, nhưng đó là **hai đồng hồ và hai hợp đồng khác nhau**: business time trong ứng dụng và expiry ở store.

## 10. Sub-document: mock không chứng minh tính nguyên tử theo path

Couchbase Java SDK hỗ trợ `lookupIn` và `mutateIn` để thao tác với một phần JSON document.

Ví dụ:

~~~java
import static com.couchbase.client.java.kv.MutateInSpec.upsert;

collection.mutateIn(
    "product::coffee250",
    List.of(
        upsert("inventory.available", 12),
        upsert("inventory.last_reason", "RESTOCK")
    )
);
~~~

Một mock `collection.mutateIn` chỉ xác minh code đã tạo `MutateInSpec`; nó không chứng minh:

- Đường dẫn `inventory.available` có hợp lệ với document thật không.
- Nếu parent `inventory` thiếu hoặc sai kiểu, operation sẽ thành công hay lỗi.
- Nhiều sub-document specs trong cùng một `mutateIn` được áp dụng nguyên tử ở cấp document.
- CAS document có thay đổi và bản entity Spring Data đã đọc trước đó có bị stale không.
- Đường dẫn index có thấy thay đổi hay không.
- Mảng/field có tăng quá lớn, vượt giới hạn document hay không.

Một test tích hợp tốt tạo document thật, chạy `mutateIn` với **một spec lỗi có chủ đích**, rồi đọc lại body để kiểm chứng không có cập nhật nửa vời. Sau đó thử một mutation hợp lệ và so CAS trước/sau.

Đừng dùng `arrayAppend` nhiều lần trên một `List` giả rồi khẳng định ứng dụng có thể nhúng một lịch sử sự kiện vô hạn. Sub-document giảm lượng payload trao đổi nhưng **không bỏ giới hạn kích thước document** hoặc giải quyết hot document.

## 11. Transaction và durability: hai loại bảo đảm không thể stub ra

### 11.1. Transaction: nhiều document phải nhất quán

Một workflow đặt hàng có thể phải:

1. Tạo Order `RESERVED`.
2. Trừ lượng tồn trong Inventory.
3. Ghi claim/idempotency key.

Với một fake map, `save(order)` và `save(inventory)` lần lượt cập nhật in-memory objects. Một test đặt `when(saveInventory).thenThrow(...)` rồi kiểm tra service gọi `rollback()` chỉ chứng minh service **đã gọi method mang tên rollback**, không chứng minh Couchbase đã rollback các mutation.

Test transaction thật cần:

- Dùng đúng Couchbase Transactions SDK hoặc Spring-managed transaction **đã được cấu hình và được phiên bản hỗ trợ**.
- Tạo vài document test ở trạng thái biết trước.
- Chủ động gây lỗi tại một bước được kiểm soát **trong workflow**, không tạo lỗi mạng ngẫu nhiên.
- Quan sát trạng thái sau abort/commit theo đúng cơ chế transaction.
- Xác minh **không có trạng thái nghiệp vụ nửa vời**; nếu dùng saga, xác minh compensation và retry/idempotency.
- Thử hai transaction cạnh tranh trên Inventory để kiểm tra invariant không âm.

**Không giả định `@Transactional` tự hoạt động với mọi configuration Spring Data Couchbase** như JPA. Khả năng giao dịch và propagation cần kiểm tra qua API và server thật.

### 11.2. Durability: phản hồi mock không chứng minh dữ liệu đã được bảo vệ

Couchbase hỗ trợ các mức durability như `MAJORITY`, `MAJORITY_AND_PERSIST_TO_ACTIVE`, `PERSIST_TO_MAJORITY` tùy thao tác/phiên bản/topology. Mức yêu cầu ảnh hưởng thời điểm server xác nhận mutation.

Nếu mock SDK trả một `MutationResult`, không có bằng chứng:

- Cluster có đủ replicas/quorum cho mức durability đã yêu cầu.
- Một node lỗi có khiến mutation timeout hoặc ambiguous result không.
- Retry có gây duplicate side effects không.
- Durability level được truyền đến server đúng như cấu hình production không.

Các tình huống failure/ambiguous result cần test chuyên biệt với cluster/topology có kiểm soát; một container đơn lẻ không mô phỏng đầy đủ môi trường có replica hoặc failover.

## 12. Reactive: Mono.just không chứng minh có I/O thật

Một mock reactive repository thường dùng:

~~~java
when(repository.findById(key))
    .thenReturn(Mono.just(product));
~~~

Khi dùng `StepVerifier`:

~~~java
StepVerifier.create(service.findProduct(key))
    .expectNext(product)
    .verifyComplete();
~~~

Điều đó xác minh pipeline của service **kết nối publisher do mock cung cấp**. Nó **không kiểm tra** kết nối Couchbase, backpressure ở query result, timeouts, serialization, cancellation hoặc conflict từ server thật.

Test reactive integration:

~~~java
String key = "product::reactive::" + UUID.randomUUID();

StepVerifier.create(
    reactiveRepository
        .save(new Product(key, "Cà phê", 100000))
        .flatMap(saved -> reactiveRepository.findById(saved.getId()))
)
    .assertNext(actual -> {
        assertEquals(key, actual.getId());
        assertEquals("Cà phê", actual.getDisplayName());
    })
    .verifyComplete();

StepVerifier.create(reactiveRepository.deleteById(key))
    .verifyComplete();
~~~

Điểm cần nhớ:

- Publisher thường **chưa thực hiện I/O khi chỉ được tạo**; test phải subscribe.
- Cleanup reactive cũng cần subscribe/verify.
- Với CAS conflict, kiểm tra `onError` thực tế; test không nên `onErrorResume` mọi exception rồi coi như PASS.
- Reactor virtual time giúp test `delay`/`timeout` **trong pipeline**, không tua nhanh TTL của Couchbase.
- Lỗi network/SDK thường được phát ra bất đồng bộ; chỉ test mock `Mono.error(...)` không chứng minh server sẽ phát ra đúng kiểu lỗi trong tình huống thực.

Unit test với mock reactive **vẫn rất hữu ích** cho nhánh xử lý lỗi, retry budget và mapping domain status; chỉ cần nêu rõ phạm vi của nó.

## 13. Mô hình test tối thiểu: unit + mapping + integration + resilience

Một chiến lược cân bằng:

~~~mermaid
flowchart TB
    U["Unit tests: domain + service\nMock/fake hợp lý"]
    M["Mapping contract: Spring Data JSON\nSDK đọc/ghi chéo"]
    I["Couchbase integration\nKV, index, CAS, TTL, query, transaction"]
    R["Resilience/performance\nFailover, durability, tải đồng thời"]
    U --> M --> I --> R
~~~

Không nên bỏ tầng unit vì test tích hợp “toàn diện hơn”: unit cho phản hồi nhanh, dễ xác định bug. Không nên bỏ tầng integration vì unit PASS: ngữ nghĩa Couchbase nằm ở phía sau boundary.

| Nhóm | Tốc độ tương đối | Phạm vi | Khi chạy |
| --- | --- | --- | --- |
| Domain/service unit | Rất nhanh | Invariant, nhánh lỗi, retry policy | Mỗi commit |
| Mapping contract | Trung bình | Java ↔ JSON, `@Field`, constructor, ID/CAS, legacy | PR ảnh hưởng entity/converter; nên có smoke suite mỗi CI |
| Repository/SQL++ integration | Trung bình đến chậm | Keyspace, queries, index, consistency, CAS, expiry | CI trước merge/deploy |
| Transaction/concurrency integration | Chậm hơn, cần setup | Multi-document invariants và xung đột | CI có chọn lọc + nightly |
| Resilience/load | Tốn tài nguyên | Topology, durability, failover, p95/p99 | Pre-release/nightly, môi trường gần production |

**Không cần mỗi test riêng đều chạy đầy đủ cluster**, nhưng bộ kiểm thử tổng thể phải có bằng chứng đủ mạnh cho những tính năng quan trọng ứng dụng dùng.

## 14. Testcontainers: server thật thay vì mock server

Testcontainers có thể khởi động Couchbase Server trong container dành riêng cho test. Kết hợp Spring Boot `@DataCouchbaseTest` giúp chỉ tải tầng dữ liệu. Tuy nhiên:

- `@DataCouchbaseTest` **không tự cung cấp Couchbase Server**; nó cần kết nối tới server/container.
- `@ServiceConnection` đưa connection details tới Spring Boot khi dùng version hỗ trợ, nhưng không tự tạo mọi scope/collection/index nghiệp vụ.
- Testcontainers dùng Docker/container runtime phù hợp, có thể cần cấp nhiều RAM/CPU cho Couchbase.
- Package import và artifacts Testcontainers khác giữa các major versions; nên chọn version qua BOM của dự án và kiểm tra release notes.

Ví dụ hướng Spring Boot 3.x/Testcontainers 1.x dùng **default collection** để tập trung vào việc xác minh mapping và KV:

~~~java
package com.example.shop.catalog;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import com.couchbase.client.java.Cluster;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.couchbase.DataCouchbaseTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

import org.testcontainers.couchbase.BucketDefinition;
import org.testcontainers.couchbase.CouchbaseContainer;
import org.testcontainers.couchbase.CouchbaseService;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataCouchbaseTest(properties =
    "spring.data.couchbase.bucket-name=shop_test")
@Testcontainers
class ProductRepositoryIT {

    @Container
    @ServiceConnection
    static final CouchbaseContainer couchbase =
        new CouchbaseContainer(
            DockerImageName.parse("couchbase/server:community-7.2.5"))
            .withEnabledServices(
                CouchbaseService.KV,
                CouchbaseService.QUERY,
                CouchbaseService.INDEX)
            .withBucket(new BucketDefinition("shop_test"));

    @Autowired ProductRepository repository;
    @Autowired Cluster cluster;

    @Test
    void persistsActualJsonAndDocumentKey() {
        String key = "product::it::" + UUID.randomUUID();

        try {
            Product saved = repository.save(
                new Product(key, "Cà phê Arabica", 150000));

            Product loaded = repository.findById(key).orElseThrow();
            assertEquals("Cà phê Arabica", loaded.getDisplayName());

            var result = cluster.bucket("shop_test")
                .defaultCollection().get(key);
            var json = result.contentAsObject();

            assertEquals("Cà phê Arabica",
                json.getString("display_name"));
            assertEquals(150000L, json.getLong("price_vnd"));
            assertFalse(json.containsKey("id"));
            assertNotEquals(0L, result.cas());
        } finally {
            repository.deleteById(key);
        }
    }
}
~~~

Đây là **mẫu học tập phụ thuộc phiên bản**: image `community-7.2.5`, các import và bucket config chỉ minh họa một tập dependency; cần pin image và artifact được nhóm kiểm chứng hỗ trợ, điều chỉnh theo Spring Boot/Testcontainers đang dùng. Khi dùng named scope/collection, phải bổ sung setup cho chính keyspace đó và gắn `@Scope`/`@Collection` vào entity; bài test default collection này **không chứng minh named collection production đúng**.

Bổ sung các test chuyên biệt:

1. Spring Data ghi → SDK đọc raw JSON, ID, CAS.
2. SDK ghi JSON legacy → Spring Data đọc.
3. Derived method/`@Query` với index ONLINE và consistency.
4. Hai snapshots cùng CAS cập nhật cạnh tranh.
5. TTL hết hạn/preserve expiry.
6. Transaction và sub-document nếu workload có sử dụng.

### 14.1. @DataCouchbaseTest hay @SpringBootTest?

Dùng `@DataCouchbaseTest` khi cần entity converter, template và repository; nó hạn chế beans ngoài data slice. Dùng `@SpringBootTest` khi mục tiêu bao gồm service orchestration, security, messaging hoặc transaction configuration liên quan.

Không đặt `@SpringBootTest` cho mọi phép tính đơn giản. Không khẳng định `@DataCouchbaseTest` test được cả service/controller nếu các bean ấy không nằm trong context. Có thể `@Import` những bean cần thiết một cách tường minh.

### 14.2. Nếu chưa thể dùng Testcontainers

Có thể dùng một Couchbase test cluster do CI quản lý, miễn:

- Hoàn toàn tách biệt production.
- Có bucket/scope/collection dành riêng cho test.
- Dữ liệu setup/cleanup xác định; không `deleteAll` trên collection dùng chung.
- Index/service readiness được kiểm tra.
- Version Server phù hợp mục tiêu tương thích.
- Quyền ghi và credential không dùng chung với production.

Một số unit tests còn có thể dùng converter-focused tests không cần server để bắt lỗi đơn giản. Tuy vậy, chúng chỉ là **bổ sung**, không thay thế toàn bộ integration khi mục tiêu là xác minh ngữ nghĩa Couchbase.

## 15. Thiết kế test double có chủ đích: đừng giả vờ đang chạy Couchbase

Một số quy tắc để mock/fake không đánh lừa người đọc:

- Đặt tên `CatalogServiceUnitTest`, `ProductMappingIT`, `ProductCasIT` rõ ràng.
- Ghi mục tiêu kiểm thử trong tên method: `translatesConflictTo409`, không đặt `couchbaseRejectsStaleWrite` cho một Mockito stub.
- Stub đúng **exception ở boundary** mà code sản phẩm dự kiến xử lý; không tự phát minh exception không bao giờ xuất hiện.
- Tránh `when(save(any())).thenReturn(input)` cho test cần metadata sau save, vì giả định ấy có thể sai với entity bất biến hoặc CAS mới.
- Nếu fake implement một subset (chẳng hạn in-memory Map), tài liệu hóa rõ `NO_CAS`, `NO_TTL`, `NO_QUERY`.
- Dùng **contract test** cho adapter thật để xác nhận mapping từ error SDK/Spring Data sang domain exception.
- Khi ứng dụng thay đổi phiên bản SDK/framework, chạy lại contract tests chứ không chỉ cập nhật mock.

### 15.1. Một ví dụ tốt về mock exception

Service chuyển optimistic locking thành lỗi nghiệp vụ:

~~~java
public void updatePrice(String id, long newPrice) {
    Product product = products.findById(id).orElseThrow();
    product.changePrice(newPrice);

    try {
        products.save(product);
    } catch (OptimisticLockingFailureException ex) {
        throw new ProductConflictException(id, ex);
    }
}
~~~

Unit test:

~~~java
@Test
void translatesOptimisticLockToDomainConflict() {
    ProductRepository repository = mock(ProductRepository.class);
    CatalogWriteService service = new CatalogWriteService(repository);

    Product product = new Product("product::a", "A", 100000);
    when(repository.findById("product::a"))
        .thenReturn(Optional.of(product));

    when(repository.save(any(Product.class)))
        .thenThrow(new OptimisticLockingFailureException("stale"));

    assertThrows(ProductConflictException.class,
        () -> service.updatePrice("product::a", 120000));
}
~~~

Kết luận đúng: **service phản ứng đúng nếu nhận exception như vậy**. Muốn chắc repository thật phát ra exception đó khi hai writer cùng sửa, phải chạy **CAS integration test** riêng.

Đoạn test trên là minh họa sau khi dự án có `CatalogWriteService`/`ProductConflictException` tương ứng, không phải code đã được định nghĩa ở ví dụ service trước đó.

## 16. Lỗi mạng, retry và kết quả ghi không rõ ràng

Một service có thể retry khi timeout. Mock rất tốt để kiểm tra “tối đa 3 lần và có backoff”, nhưng mock không cho biết **trước lúc timeout, server đã nhận mutation hay chưa**.

Các tình huống phải cân nhắc:

| Trường hợp | Mock chỉ trả lỗi | Hệ quả cần kiểm tra bằng hệ thống thật |
| --- | --- | --- |
| Timeout trước khi gửi | Không có mutation | Có thể retry nếu operation idempotent |
| Timeout sau khi server ghi thành công | Mock vẫn báo timeout | Retry có thể tạo duplicate hoặc thay đổi CAS |
| Node failover/replica chưa đủ | Stub ném exception | Durability/quorum thực ảnh hưởng kết quả |
| Query index chậm sau mutation | Stub trả list rỗng | Có thể do index lag chứ không phải document thiếu |
| Key vừa bị xóa do TTL | Stub `Optional.empty()` | Cần biết expiry/clock và quyền/keyspace |
| CAS mismatch sau writer khác | Stub conflict | Retry phải đọc lại và tái đánh giá nghiệp vụ |

Lựa chọn key/idempotency token đóng vai trò quan trọng: nếu mỗi lần retry tạo `UUID` mới cho Order, có thể sinh bản ghi trùng. Với operation insert-only, server có thể báo `DocumentExistsException` ở lần retry sau khi lần đầu thực tế đã tạo document; ứng dụng cần phân biệt “đơn đã được tạo bởi chính request này” với collision của request khác.

**Không viết test mong mọi timeout đều an toàn để retry**. Phải phân loại operation idempotent/non-idempotent, thời điểm side effect và đường hồi phục; sau đó dùng fault-injection/topology test ở môi trường riêng cho các tình huống quan trọng.

## 17. Vấn đề key, dữ liệu test và cleanup có thể che kết quả

Ngay cả khi dùng server thật, một bài test cấu hình kém vẫn có thể đưa ra bằng chứng sai:

| Anti-pattern | Tại sao nguy hiểm | Cách tốt hơn |
| --- | --- | --- |
| Mọi test dùng `product::1` | Test song song ghi đè, đọc nhầm fixture | Key riêng với UUID/namespace |
| Kết nối Couchbase trên laptop theo mặc định | Máy khác/CI có dataset khác | Testcontainers hoặc cluster test cố định |
| `deleteAll()` trong collection chung | Xóa dữ liệu fixture của test khác | Cleanup theo key, tách test collection |
| Tạo index rồi sleep 1 giây | Index readiness không xác định | Poll trạng thái/index với timeout |
| Query ngay sau save bằng `NOT_BOUNDED` | Flaky do index lag | Chọn consistency có chủ đích |
| Test TTL đúng 3.000 ms phải biến mất | Đồng hồ/expiry scheduling không chính xác tới ms | Poll tới khi hết hạn trong cửa sổ hợp lý |
| Bắt `Exception.class` rồi coi PASS | Lỗi config/permission cũng được nhận là thành công | Assert đúng exception và kiểm tra state |
| Disable SSL/auth trong test mà prod có quyền khác | Không kiểm tra được RBAC/TLS | Có suite test phù hợp topology bảo mật |
| Dùng Docker container duy nhất để “test failover” | Không có replica/topology tương đương | Môi trường đa node chuyên dụng |
| Skip integration khi Docker thiếu nhưng báo CI xanh | Không có bằng chứng persistence | Gate CI tách rõ và coi skip là không hoàn thành |

Ở mức độ nhạy cảm, đừng ghi raw JSON chứa thông tin cá nhân trong log CI. Một fixture tốt dùng dữ liệu giả, key riêng, có cleanup và ràng buộc chống chạy nhầm production.

## 18. Bài thực hành: mock PASS nhưng reserve stock bị ghi đè

**Bối cảnh:** hệ thống bán hàng có:

~~~text
Inventory document key: inventory::coffee250
JSON body:
{
  "sku": "coffee250",
  "available": 1
}
~~~

Hai request đồng thời mỗi request muốn giữ 1 đơn vị. Service:

1. `findById("inventory::coffee250")`.
2. Nếu `available >= 1`, giảm xuống 0.
3. `save(inventory)`.
4. Tạo Order `RESERVED`.

Một unit test dùng fake `Map` chạy tuần tự có thể PASS cho cả hai request: mỗi lần fake chỉ trả state mà test đã chuẩn bị, không có CAS thật, không có sự cạnh tranh. Nếu service ghi nguyên document không kiểm tra CAS, **cả hai Order có thể được xác nhận dù chỉ có 1 đơn vị tồn**.

### 18.1. Yêu cầu người học

Hãy thiết kế ít nhất bốn bài test:

1. Unit test nghiệp vụ với `available=0` phải từ chối reserve.
2. Unit test với mock kiểm tra service phản ứng đúng khi repository báo optimistic lock conflict.
3. Integration test CAS với **hai snapshots độc lập** của Inventory.
4. Integration/workflow test bảo đảm không có hai Order cùng RESERVED khi chỉ có một đơn vị, theo cơ chế transaction hoặc saga được ứng dụng thực sự dùng.

Thêm hai mở rộng: TTL của reservation và truy vấn SQL++ liệt kê reservation đang ACTIVE.

### 18.2. Đáp án tham khảo — phân tầng

| Lớp test | Setup | Assertion | Không được kết luận |
| --- | --- | --- | --- |
| Unit domain | Inventory có `available=0` | Thao tác `reserve(1)` bị từ chối | CAS/DB đang hoạt động |
| Service mock | `save` stub conflict | Service báo domain conflict/retry đúng | Server thật chắc chắn báo conflict |
| CAS integration | Hai entity từ cùng document/CAS | Writer thứ hai không ghi đè writer thứ nhất | Multi-document transaction đã atomic |
| Workflow integration | Inventory 1, hai request và Order docs | Tối đa một reservation/order thành công; state còn lại nhất quán | Mọi failover topology được bao phủ |
| TTL integration | Reservation có expiry ngắn | Expiry xảy ra và logic release/cleanup đúng | Đồng hồ fake quyết định TTL |
| SQL++ integration | Nhiều reservation, index phù hợp | Filter/sort đúng theo actual JSON và consistency | Mock query đủ thay thế index/optimizer |

Khi test CAS:

~~~java
Inventory one = inventoryRepository.findById(key).orElseThrow();
Inventory two = inventoryRepository.findById(key).orElseThrow();

// Giả định Inventory.reserve(1) thay đổi state của mỗi instance.
one.reserve(1);
inventoryRepository.save(one);

two.reserve(1);
assertThrows(OptimisticLockingFailureException.class,
    () -> inventoryRepository.save(two));
~~~

Phần mã là **phác thảo** sau khi dự án định nghĩa `Inventory`, `InventoryRepository` và `reserve` có `@Version`. Phải kiểm tra state cuối cùng ở Couchbase và Order tương ứng. Khi test hai request thật, cần điều phối để **cả hai đã đọc snapshot trước khi writer đầu tiên ghi**, thay vì trông chờ race tình cờ xảy ra.

### 18.3. Câu hỏi tự kiểm tra

1. **Mockito trả Product đã stub có chứng minh `@Field` đúng không?** Không; chưa chạy converter.
2. **Mockito trả exception CAS có chứng minh Couchbase phát hiện stale write không?** Không; chỉ kiểm tra service xử lý exception.
3. **Vì sao đọc raw JSON bằng SDK sau khi Spring Data save?** Để kiểm tra contract JSON độc lập với mapping đọc của Spring Data.
4. **`findById` theo key cần secondary index không?** Không; KV thường không cần.
5. **SQL++ query sau save không thấy document ngay có chắc save lỗi không?** Không; index có thể chưa bắt kịp.
6. **Dùng `Thread.sleep(2000)` có chứng minh TTL chính xác không?** Không; cần polling và hợp đồng expiry.
7. **Hai writer thay đổi hai field khác nhau có cùng CAS không?** Có nếu chúng cùng document, dù field khác nhau.
8. **Sub-document mutation có bỏ giới hạn document size không?** Không.
9. **Fake in-memory có thể mô phỏng transaction đầy đủ không?** Có thể bắt chước một phần, nhưng không chứng minh transaction Couchbase thật.
10. **`Mono.just(product)` có gọi Couchbase Server không?** Không, đó chỉ là publisher của giá trị đã có.
11. **Testcontainers một node có đủ test durability khi failover không?** Không, cần topology phù hợp.
12. **Có nên bỏ mock hoàn toàn không?** Không; mock là công cụ tốt cho domain/service orchestration, cần thêm bằng chứng server thật cho persistence.
13. **Nếu CI skip test tích hợp, có thể khẳng định ngữ nghĩa Couchbase đã được kiểm tra không?** Không.
14. **Khi adapter SDK đổi phiên bản, cần làm gì ngoài sửa mock?** Chạy contract/integration test với phiên bản SDK/Server mục tiêu.

## 19. Checklist trước khi đánh dấu tính năng “đã kiểm thử Couchbase”

- [ ] Unit tests xác minh business invariants và các nhánh xử lý lỗi bằng dữ liệu đơn giản.
- [ ] Mock/fake được đặt tên và ghi phạm vi rõ, không tự nhận chứng minh server semantics.
- [ ] Có test với Spring Data converter và kiểm tra raw JSON thật qua SDK.
- [ ] Đã kiểm tra `@Id`, `@Field`, `@Version`, constructor/record và type hints khi có.
- [ ] Đã tạo đúng bucket/scope/collection trong môi trường kiểm thử, không chỉ default collection.
- [ ] Đã test KV insert/upsert/replace/remove theo ngữ nghĩa và lỗi thực tế cần dùng.
- [ ] Có integration test của repository derived query hoặc SQL++ custom query.
- [ ] Có index phù hợp, readiness check và kiểm tra scan consistency/read-after-write.
- [ ] Đã test MISSING, NULL, sai kiểu và dữ liệu lịch sử nếu schema linh hoạt.
- [ ] CAS được test với hai snapshot độc lập, exception đúng và trạng thái cuối không bị ghi đè.
- [ ] TTL được kiểm tra bằng expiry server và polling có timeout; preserve expiry được xem xét khi cập nhật.
- [ ] Transaction được kiểm tra trên nhiều document hoặc workflow bù được xác minh đúng.
- [ ] Sub-document mutation được test path lỗi, atomicity và CAS khi áp dụng.
- [ ] Reactive I/O được subscribe/verified, cleanup cũng chạy thực sự.
- [ ] Retry/durability/ambiguous result có chính sách idempotency và test theo mức độ rủi ro.
- [ ] Test dùng key riêng, cleanup có mục tiêu, không chạm production.
- [ ] CI có dấu hiệu rõ rằng integration tests đã thực sự chạy và PASS, không bị skip âm thầm.
- [ ] Những phép đo performance/failover có môi trường thích hợp, không suy từ mock hoặc một container.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): document mapping, `@Id`, `@Field`, `@Version` và type information.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository, KV theo ID và query methods.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test slices và lựa chọn `@DataCouchbaseTest`/`@SpringBootTest`.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và connection details.
- [Testcontainers for Java — Couchbase](https://java.testcontainers.org/modules/databases/couchbase/): `CouchbaseContainer` và cấu hình service/bucket.
- [Mockito — API Reference](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): stub, verify và mock interactions.
- [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): insert/upsert/replace/remove, CAS và lỗi thao tác KV.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query parameters, scan consistency và index visibility.
- [Couchbase Java SDK — Sub-Document Operations](https://docs.couchbase.com/java-sdk/current/howtos/subdocument-operations.html): lookup/mutate theo path và atomicity.
- [Couchbase Java SDK — Concurrent Document Mutations](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-document-mutations.html): CAS và cạnh tranh ghi; kết hợp tài liệu durable writes của SDK tương ứng khi kiểm thử durability.
- [Couchbase Server — Transactions](https://docs.couchbase.com/server/current/learn/data/transactions.html): nguyên lý giao dịch đa document và các điều kiện cần kiểm thử.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/reference/): test publisher reactive và các giới hạn của virtual time.
