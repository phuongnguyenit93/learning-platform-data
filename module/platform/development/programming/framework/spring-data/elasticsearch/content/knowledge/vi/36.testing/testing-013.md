# Cách ly index giữa các ca kiểm thử và dọn dữ liệu

Integration test với Spring Data Elasticsearch thường ghi và đọc dữ liệu thật từ một Elasticsearch cluster. Nếu nhiều test dùng chung một index, dữ liệu của test trước có thể ảnh hưởng test sau: kết quả tìm kiếm thừa document, count sai, document cũ bị ghi đè hoặc một test xóa dữ liệu mà test khác đang dùng.

Vấn đề rõ hơn khi test chạy song song trên máy developer hoặc CI. Hai test có thể cùng tạo document có ID giống nhau, cùng xóa index hoặc cùng thay đổi mapping. Kết quả khi đó phụ thuộc lịch chạy thay vì logic đang kiểm thử.

Một cách tổ chức đáng tin cậy là tạo index riêng cho mỗi test case hoặc mỗi test class, ghi dữ liệu qua đúng index đó, refresh khi cần đọc ngay sau khi ghi, rồi xóa index trong teardown. Với Spring Data Elasticsearch, IndexOperations quản lý vòng đời index và IndexCoordinates chỉ định index đích cho các thao tác ElasticsearchOperations.

Nếu test dùng repository có @Document(indexName = "..."), cần chú ý repository thường lấy index từ metadata của entity. Repository method không tự nhận một index ngẫu nhiên cho từng test. Bài này phân biệt rõ hai cách test đó để tránh tưởng rằng chỉ tạo một index mới là repository đã tự chuyển sang index mới.

## 1. Vì sao cần cách ly index giữa các test?

Giả sử hai test cùng dùng index products-test:

~~~text
Test A:
  index product P-1
  assert count = 1

Test B:
  index product P-2
  assert count = 1
~~~

Nếu Test B chạy sau Test A mà không dọn dữ liệu, count có thể bằng 2. Nếu Test A xóa toàn bộ index trong khi Test B đang chạy, Test B có thể gặp lỗi index not found. Nếu cả hai cùng dùng ID P-1, một test có thể ghi đè document của test kia.

Các dạng nhiễm chéo thường gặp:

- **Dữ liệu còn sót:** test trước để lại document khiến assertion của test sau sai.
- **Trùng document ID:** hai test ghi cùng ID và ghi đè nhau.
- **Xóa nhầm:** teardown của test này xóa index hoặc dữ liệu test khác đang dùng.
- **Mapping/settings bị thay đổi:** test thay analyzer, mapping hoặc alias làm thay đổi môi trường của test khác.
- **Refresh không đồng bộ:** test ghi xong rồi search ngay, nhưng document chưa được refresh nên chưa xuất hiện trong kết quả.
- **Chạy song song:** thứ tự tạo, ghi, refresh và xóa index tạo ra race condition.
- **Test thất bại giữa chừng:** index tạm vẫn còn trên cluster và làm các lần chạy sau bị ảnh hưởng.

Index riêng giúp mỗi test có một namespace dữ liệu độc lập. Xóa cả index sau test cũng đưa mapping, settings, alias và document state về trạng thái sạch.

## 2. Các mức độ cách ly

Không phải test nào cũng cần tạo index mới. Chọn mức cách ly theo phạm vi tài nguyên mà test sử dụng.

| Phạm vi | Cách làm | Phù hợp |
| --- | --- | --- |
| Unit test | Mock ElasticsearchOperations hoặc repository | Kiểm thử logic không cần Elasticsearch thật |
| Test method | Index riêng cho mỗi test method | Integration test chạy song song hoặc có mapping/data riêng |
| Test class | Index riêng cho mỗi test class | Các method trong class dùng chung mapping và có thể dọn document giữa các test |
| Test run | Prefix hoặc namespace riêng cho mỗi CI run | Nhiều test class hoặc nhiều worker dùng chung một cluster |
| Test suite dùng cluster riêng | Container/cluster riêng cho cả suite | Cần cách ly cả cluster settings, plugin hoặc security configuration |

Một mô hình phổ biến là dùng một Elasticsearch container cho test suite, nhưng tạo index riêng cho từng test method. Như vậy không cần khởi động cluster cho mỗi test mà dữ liệu vẫn được cách ly.

### 2.1. Unit test không cần index thật

Nếu chỉ kiểm thử service gọi đúng repository method, có thể mock repository. Nếu cần kiểm tra query builder, có thể kiểm tra cấu trúc query hoặc mock ElasticsearchOperations.

Không nên tạo index thật cho mọi unit test vì việc khởi tạo cluster và mapping làm test chậm, đồng thời khiến unit test phụ thuộc hạ tầng.

### 2.2. Integration test cần Elasticsearch thật

Khi cần xác nhận mapping, analyzer, nested query, sorting, aggregation, repository proxy hoặc hành vi Elasticsearch cụ thể, hãy chạy integration test với một Elasticsearch instance thật.

Testcontainers thường phù hợp vì mỗi CI run có thể khởi động một cluster dùng riêng cho suite rồi tự dừng container sau khi hoàn tất. Cần pin image version tương thích với phiên bản Elasticsearch Java API Client và Spring Data Elasticsearch mà dự án đang dùng.

## 3. Đặt tên index riêng cho test

Index name cần dễ nhận diện, hợp lệ theo quy tắc Elasticsearch và không trùng giữa các test đang chạy.

Một quy ước dễ vận hành:

~~~text
it-<module>-<test-class>-<test-method>-<run-token>
~~~

Ví dụ:

~~~text
it-catalog-productsearch-searchbybrand-a13f92c1
it-catalog-productsearch-emptyresult-7bd421e0
it-order-orderrepository-save-4d90a8b2
~~~

Nên có:

- Prefix cố định như it- để nhận biết index test.
- Tên module hoặc domain để dễ truy vết.
- Tên test class/method đã được chuẩn hóa nếu hữu ích.
- Token ngẫu nhiên để tránh trùng giữa các process, CI job và lần chạy.

### 3.1. Quy tắc tên index

Elasticsearch index name có các giới hạn, trong đó cần nhớ:

- Dùng chữ thường.
- Không chứa khoảng trắng hoặc các ký tự bị cấm như backslash, slash, dấu sao, dấu hỏi, dấu nháy kép, dấu nhỏ hơn/lớn hơn, dấu pipe, dấu phẩy, dấu thăng.
- Không bắt đầu bằng dấu gạch dưới, dấu gạch ngang hoặc dấu cộng.
- Không vượt giới hạn độ dài tên index.
- Nên tránh tên quá dài vì tên test method và token có thể cộng lại.

Đặt prefix it- giúp tên bắt đầu bằng ký tự hợp lệ và phân biệt index test với index ứng dụng.

### 3.2. Tạo token duy nhất

Có thể dùng một phần UUID:

~~~java
import java.util.UUID;

String token = UUID.randomUUID()
    .toString()
    .replace("-", "")
    .substring(0, 8);

String indexName = "it-products-" + token;
~~~

Nếu muốn truy vết test method:

~~~java
String safeMethodName = testMethodName
    .toLowerCase(Locale.ROOT)
    .replaceAll("[^a-z0-9_-]", "-");

String indexName = "it-products-" + safeMethodName + "-" + token;
~~~

Không dùng riêng tên method làm index name vì cùng method có thể chạy trên nhiều module, nhiều fork hoặc nhiều CI job cùng lúc.

### 3.3. Token theo test run

Trong CI, có thể tạo một TEST_RUN_ID ở đầu job và dùng chung prefix cho các index trong job:

~~~text
it-<run-id>-products-<method-token>
~~~

Lợi ích:

- Tìm được toàn bộ index do một CI run tạo.
- Có thể dọn tài nguyên còn sót sau khi job bị hủy.
- Tránh xóa nhầm index từ run khác.
- Phân biệt dữ liệu của các worker chạy song song.

Không đặt token bí mật hoặc thông tin cá nhân vào index name. Tên index có thể xuất hiện trong log, metric và cluster APIs.

## 4. Dùng IndexOperations để tạo và xóa index

Spring Data Elasticsearch cung cấp IndexOperations để quản lý index:

- Tạo index.
- Kiểm tra index có tồn tại.
- Tạo và cập nhật mapping.
- Đọc mapping/settings.
- Refresh index.
- Xóa index.
- Quản lý alias và một số thao tác index-level khác.

Có thể lấy IndexOperations từ ElasticsearchOperations:

~~~java
IndexOperations entityIndexOperations =
    operations.indexOps(Product.class);
~~~

Lệnh trên sử dụng metadata của entity Product, bao gồm index name được khai báo trong @Document.

Nếu cần index động riêng cho test, truyền IndexCoordinates:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of("it-products-a13f92c1");
IndexOperations testIndexOperations = operations.indexOps(coordinates);
~~~

Đây là điểm quan trọng: indexOps(Product.class) lấy index theo entity metadata; indexOps(IndexCoordinates) nhắm tới index được chỉ định tường minh.

### 4.1. Tạo index và mapping

~~~java
IndexOperations entityMetadata = operations.indexOps(Product.class);
Document mapping = entityMetadata.createMapping();

IndexCoordinates coordinates = IndexCoordinates.of(indexName);
IndexOperations testIndex = operations.indexOps(coordinates);

testIndex.create();
testIndex.putMapping(mapping);
~~~

createMapping() lấy mapping từ metadata của Product. putMapping() áp dụng mapping đó vào index test mới.

Nếu entity dùng settings tùy chỉnh, analyzer hoặc ingest pipeline, test cần tạo các cấu hình tương ứng. Không nên giả định tạo index rỗng là đủ để kiểm thử query production.

### 4.2. Kiểm tra tồn tại trước khi xóa

Trong teardown:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of(indexName));

if (indexOperations.exists()) {
    indexOperations.delete();
}
~~~

Kiểm tra exists() giúp cleanup có thể gọi lặp mà không yêu cầu index chắc chắn phải còn tồn tại. Tùy phiên bản client và trạng thái cluster, vẫn cần xử lý exception khi index vừa bị xóa bởi một tiến trình khác.

### 4.3. Xóa index hay xóa document?

Nếu test cần một môi trường hoàn toàn mới, xóa index rồi tạo lại thường sạch hơn xóa từng document:

- Mapping được tạo lại.
- Settings được đặt lại.
- Alias test được loại bỏ cùng index.
- Không còn document hoặc metadata từ test trước.

Nếu test class cần dùng chung index để tiết kiệm thời gian, có thể xóa document theo ID hoặc dùng delete-by-query với điều kiện test-specific. Khi đó mapping/settings vẫn được giữ lại và test phải bảo đảm không còn dữ liệu liên quan trước khi bắt đầu.

## 5. Ví dụ integration test với index riêng cho từng test method

Ví dụ dưới đây dùng ElasticsearchOperations để chỉ định index đích trực tiếp. Mỗi test method có index riêng nên các test có thể chạy song song mà không ghi đè dữ liệu của nhau.

~~~java
import java.util.Locale;
import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInfo;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@SpringBootTest
class ProductIndexIntegrationTest {

    @Autowired
    private ElasticsearchOperations operations;

    private String indexName;
    private IndexCoordinates coordinates;

    @BeforeEach
    void createTestIndex(TestInfo testInfo) {
        String method = testInfo.getTestMethod()
            .map(methodInfo -> methodInfo.getName())
            .orElse("unknown");

        String safeMethod = method
            .toLowerCase(Locale.ROOT)
            .replaceAll("[^a-z0-9_-]", "-");

        String token = UUID.randomUUID()
            .toString()
            .replace("-", "")
            .substring(0, 8);

        indexName = "it-products-" + safeMethod + "-" + token;
        coordinates = IndexCoordinates.of(indexName);

        IndexOperations entityMetadata = operations.indexOps(Product.class);
        IndexOperations testIndex = operations.indexOps(coordinates);

        testIndex.create();
        testIndex.putMapping(entityMetadata.createMapping());
    }

    @AfterEach
    void deleteTestIndex() {
        if (coordinates == null) {
            return;
        }

        IndexOperations testIndex = operations.indexOps(coordinates);
        if (testIndex.exists()) {
            testIndex.delete();
        }
    }
}
~~~

Đây là khung integration test. Các test method trong class sử dụng coordinates khi lưu và tìm kiếm. Không gọi repository method mặc định nếu repository đang lấy index cố định từ @Document.

### 5.1. Ghi và đọc trên cùng index

~~~java
Product product = new Product();
product.setId("P-100");
product.setName("Mechanical Keyboard");

operations.save(product, coordinates);

operations.indexOps(coordinates).refresh();

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("name")
        .query("mechanical keyboard")
    ))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class, coordinates);
~~~

Tham số IndexCoordinates trong save và search bảo đảm hai thao tác nhắm cùng index test. Nếu chỉ truyền entity class, Spring Data có thể sử dụng index name trong @Document.

### 5.2. Không chia sẻ field index giữa các test chạy song song

Ví dụ trên dùng field instance. JUnit Jupiter mặc định tạo test instance mới cho mỗi test method, nên mỗi instance có indexName và coordinates riêng.

Nếu class dùng @TestInstance(PER_CLASS), hoặc chuyển index name sang static field, các test method chạy song song có thể ghi đè giá trị coordinates của nhau. Trong trường hợp đó, hãy tạo context index theo từng test invocation hoặc không chạy song song các method dùng chung field.

## 6. Repository có @Document indexName cố định

Repository Spring Data Elasticsearch thường lấy index từ mapping metadata của entity:

~~~java
@Document(indexName = "products")
public class Product {
    // ...
}
~~~

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Các lời gọi như productRepository.save(product) và productRepository.findById(id) sử dụng index gắn với entity metadata. Repository method thông thường không nhận thêm IndexCoordinates cho từng lần gọi.

Vì vậy, tạo index it-products-<uuid> rồi gọi repository.save không tự động ghi vào index đó. Repository vẫn có thể ghi vào products theo metadata.

### 6.1. Ba lựa chọn để test repository

**Lựa chọn A: index riêng cho mỗi test class.**

- Entity test có index name riêng hoặc cấu hình index name qua cơ chế property/SpEL mà phiên bản dự án hỗ trợ.
- Mỗi test class có context/index riêng.
- Các method trong class dọn document hoặc reset index state giữa các lần chạy.
- Các class khác nhau dùng index name khác nhau để có thể chạy song song.

**Lựa chọn B: test repository qua entity test riêng.**

- Tạo một entity test có mapping tương ứng nhưng @Document(indexName = "...") dành riêng cho test.
- Tạo repository cho entity đó.
- Dùng index cố định cho test class và xóa index trong teardown.

Lựa chọn này rõ ràng nhưng cần tránh trùng lặp mapping model nếu entity production thay đổi.

**Lựa chọn C: dùng ElasticsearchOperations với IndexCoordinates.**

- Dùng repository cho các hành vi cần kiểm thử thông qua repository proxy.
- Dùng operations cho các test cần index riêng theo từng method.
- Không giả định repository proxy tự đổi index theo coordinates truyền ở nơi khác.

### 6.2. Property hoặc SpEL trong @Document

Một số cấu hình Spring Data Elasticsearch cho phép index name được resolve từ property hoặc SpEL expression. Có thể dùng cơ chế này để mỗi test context có một index name riêng.

Tuy nhiên:

- Cú pháp và thời điểm resolve phụ thuộc phiên bản.
- Repository metadata có thể được giữ trong ApplicationContext đã cache.
- Thay đổi property sau khi context đã tạo không nhất thiết làm repository đổi index.
- Hai test dùng chung context không thể an toàn thay đổi một property global theo từng method.

Nếu chọn cách này, tạo context/index theo phạm vi test class hoặc test run, kiểm tra index thực tế mà repository sử dụng và tránh thay đổi property dùng chung khi test chạy song song. Không dựa vào @DirtiesContext như một cơ chế cách ly dữ liệu chính; nó chỉ yêu cầu Spring loại context khỏi cache và có thể làm suite chậm đáng kể.

## 7. Dọn index trong lifecycle của JUnit

JUnit Jupiter cung cấp lifecycle hooks:

- @BeforeEach: tạo index và mapping trước mỗi test method.
- @AfterEach: xóa index sau mỗi test method.
- @BeforeAll: tạo tài nguyên dùng chung cho cả class.
- @AfterAll: dọn tài nguyên dùng chung sau class.

### 7.1. Dùng BeforeEach và AfterEach

Đây là mẫu dễ hiểu nhất khi mỗi method có index riêng:

~~~java
@BeforeEach
void setUp() {
    createUniqueIndex();
}

@AfterEach
void tearDown() {
    deleteCurrentIndexIfExists();
}
~~~

JUnit chạy @AfterEach sau test method kể cả khi test method thất bại. Tuy nhiên, nếu quá trình tạo index trong @BeforeEach thất bại giữa chừng, cleanup cần kiểm tra index đã được tạo hay chưa.

### 7.2. Gán coordinates trước khi tạo index

~~~java
indexName = createIndexName();
coordinates = IndexCoordinates.of(indexName);

IndexOperations indexOperations = operations.indexOps(coordinates);
indexOperations.create();
~~~

Nếu create hoặc putMapping thất bại sau khi index đã được tạo, @AfterEach vẫn có đủ thông tin để thử xóa index.

### 7.3. Cleanup phải an toàn khi gọi nhiều lần

~~~java
void deleteIndexIfExists(IndexCoordinates coordinates) {
    IndexOperations indexOperations = operations.indexOps(coordinates);
    if (indexOperations.exists()) {
        indexOperations.delete();
    }
}
~~~

Không nên coi index not found là lỗi nghiêm trọng nếu index đã được xóa bởi một cleanup trước đó. Ngược lại, không nuốt mọi exception từ cleanup vì lỗi quyền hoặc cluster outage có thể khiến index test tồn tại lâu dài.

### 7.4. Không che mất lỗi của test

Nếu test method đã thất bại và teardown cũng thất bại, cần giữ lại cả hai thông tin. JUnit thường báo lỗi teardown như một lifecycle failure; logger có thể ghi thêm index name để dễ dọn thủ công.

Trong hệ thống test lớn, có thể viết một JUnit extension chịu trách nhiệm tạo và xóa index. Extension cần gắn index name vào test invocation context, không dùng một static field chung cho nhiều test chạy song song.

## 8. Dọn document khi phải dùng chung index

Có trường hợp test cần kiểm tra repository đang trỏ tới một index cố định hoặc việc tạo index mới quá tốn thời gian. Khi đó có thể giữ index cho test class và xóa document trước/sau mỗi method.

Ví dụ dùng delete-by-query:

~~~java
Query deleteAll = Query.findAll();

operations.delete(
    deleteAll,
    Product.class,
    coordinates
);

operations.indexOps(coordinates).refresh();
~~~

Tên method và kiểu Query cần đối chiếu phiên bản Spring Data Elasticsearch. Đối với delete-by-query trên dữ liệu lớn, đây là thao tác có chi phí và có thể có semantics riêng về refresh/conflicts.

### 8.1. Xóa theo testRunId

Nếu index được chia sẻ bởi nhiều test nhưng mỗi document có field testRunId, có thể xóa đúng dữ liệu của test:

~~~json
{
  "query": {
    "term": {
      "testRunId": "run-a13f92c1"
    }
  }
}
~~~

Điều kiện cleanup phải dùng ID test được tạo từ harness, không lấy tùy tiện từ input của test. Sau delete-by-query, refresh index trước khi test khác đọc dữ liệu.

### 8.2. Vì sao xóa index thường sạch hơn?

Delete-by-query chỉ xóa document khớp query. Mapping, settings, aliases và index-level metadata vẫn tồn tại. Nếu test đã thay đổi mapping hoặc settings, xóa document không đưa index về trạng thái ban đầu.

Nếu cần test mapping migration, analyzer hoặc index settings, tạo index riêng rồi xóa toàn bộ index thường an toàn hơn.

### 8.3. Tránh delete-by-query toàn index production

Không dùng query match_all hoặc thao tác xóa rộng trên một index có thể chứa dữ liệu ngoài test. Nếu phải dùng shared index, hãy bảo đảm:

- Cluster là test-only.
- Index name có prefix test.
- Mỗi document có testRunId riêng.
- Cleanup luôn có điều kiện theo testRunId.
- Test không có quyền kết nối đến production cluster.

## 9. Refresh sau khi ghi

Elasticsearch là search engine near-real-time. Một document được index thành công không nhất thiết xuất hiện ngay trong search request kế tiếp.

Ví dụ:

~~~java
operations.save(product, coordinates);

SearchHits<Product> hits =
    operations.search(query, Product.class, coordinates);
~~~

Search có thể chưa thấy document nếu refresh chưa xảy ra.

### 9.1. Refresh tường minh trong test

Sau khi ghi xong batch:

~~~java
operations.indexOps(coordinates).refresh();
~~~

Sau đó mới thực hiện search hoặc aggregation cần thấy dữ liệu vừa ghi.

Refresh trong test giúp kết quả xác định hơn. Không nên gọi refresh sau từng document trong một batch lớn vì sẽ làm test chậm và không phản ánh cách ứng dụng production thường vận hành.

### 9.2. Refresh policy

Một số write API hỗ trợ refresh policy như wait_for. Có thể dùng khi cần đợi thay đổi có thể search được, nhưng hãy hiểu chi phí và semantics của API cụ thể.

Trong integration test, một lần refresh sau khi hoàn tất toàn bộ ghi thường đơn giản và rõ ràng hơn.

### 9.3. Reactive operations

Với ReactiveElasticsearchOperations, phải subscribe/await việc ghi và refresh hoàn tất trước khi chạy search. Không tạo publisher rồi bỏ qua mà cho rằng thao tác đã được thực thi.

Ví dụ khái niệm:

~~~java
reactiveOperations.save(product, coordinates)
    .then(reactiveOperations.indexOps(coordinates).refresh())
    .thenMany(reactiveOperations.search(query, Product.class, coordinates))
    .collectList()
    .block();
~~~

Đoạn minh họa cần điều chỉnh theo kiểu trả về thực tế của refresh() trong phiên bản Spring Data đang dùng. Trong test, có thể block ở ranh giới test method để đợi kết quả; không block tùy tiện bên trong production reactive pipeline.

## 10. Cách ly test chạy song song

Chạy song song giúp giảm thời gian CI nhưng chỉ an toàn nếu các test không chia sẻ mutable resources.

### 10.1. Mỗi test method có index riêng

~~~text
Test worker 1 -> it-products-testA-uuid1
Test worker 2 -> it-products-testB-uuid2
Test worker 3 -> it-orders-testC-uuid3
~~~

Các worker có thể dùng chung Elasticsearch cluster nhưng không ghi/xóa cùng index.

### 10.2. Không dùng tên index cố định trong test song song

Tên như products-test hoặc test-index dễ gây xung đột nếu nhiều test class hoặc nhiều build process dùng chung cluster.

Ngay cả khi mỗi test đều gọi delete trước khi tạo, hai test có thể xen kẽ:

~~~text
Worker A: exists? no
Worker B: exists? no
Worker A: create index
Worker B: create index -> resource already exists
Worker A: write documents
Worker B: delete index
Worker A: search -> index missing
~~~

Tên duy nhất tránh race ở cấp index.

### 10.3. Không dùng static mutable index name

Không dùng một static field được thay đổi bởi mọi test invocation. Một test có thể ghi đè giá trị trong lúc test khác đang sử dụng. Dùng state theo test instance hoặc extension context riêng.

### 10.4. Parallel test class và Spring context cache

Spring TestContext có thể tái sử dụng ApplicationContext giữa các test class để tăng tốc. Điều đó không có nghĩa dữ liệu Elasticsearch được tự động cách ly.

Các bean như ElasticsearchOperations có thể được dùng chung trong context; index vật lý vẫn là tài nguyên cluster. Vì vậy, cách ly index phải được thực hiện rõ ràng theo test scope.

Nếu repository dùng index name cố định trong entity metadata, hai test class dùng chung context có thể cùng ghi vào một index. Dùng tên riêng theo class/context hoặc serialize nhóm test đó.

## 11. Dùng Testcontainers cho Elasticsearch integration tests

Testcontainers có thể khởi động Elasticsearch trong container cho một test suite. Điều này giúp test không phụ thuộc cluster developer đang chạy hoặc một môi trường chia sẻ.

Một cấu hình khái niệm:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:<pinned-version>"
            )
        );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            elasticsearch::getHttpHostAddress
        );
    }
}
~~~

Đây là cấu trúc minh họa. Package, constructor và cấu hình security của ElasticsearchContainer phụ thuộc phiên bản Testcontainers. Hãy pin image version tương thích với Elasticsearch client của dự án, thay vì dùng tag latest.

### 11.1. Container theo suite, index theo method

Khởi động container cho mỗi test method có thể rất tốn thời gian. Một lựa chọn cân bằng:

- Một container cho test class hoặc suite.
- Một index riêng cho mỗi test method.
- Dọn index trong @AfterEach.
- Dừng container sau khi suite hoàn tất.

Nếu nhiều test class dùng chung static container, cần bảo đảm lifecycle container không kết thúc trước khi class khác dùng xong. Có thể dùng singleton container pattern hoặc cơ chế quản lý container phù hợp phiên bản Testcontainers.

### 11.2. Đồng bộ version

Spring Data Elasticsearch, Elasticsearch Java API Client và server phải tương thích. Khi nâng server version, cập nhật dependency client và kiểm thử integration suite.

Không nên dùng một Elasticsearch version rất khác production nếu test phụ thuộc mapping behavior, query DSL hoặc API version cụ thể.

## 12. Bảo vệ môi trường ngoài test

Cleanup là thao tác phá hủy dữ liệu. Cấu hình test phải bảo đảm chỉ kết nối đến cluster test.

Nên:

- Dùng profile riêng như test.
- Dùng URI do Testcontainers cung cấp hoặc một test cluster riêng.
- Dùng credential chỉ có quyền trên test cluster/index.
- Kiểm tra host/URI khi khởi tạo integration test.
- Dùng prefix index riêng như it-.
- Không để test tự động dùng production URI khi thiếu biến môi trường.

Ví dụ kiểm tra cấu hình:

~~~java
String uri = environment.getProperty("spring.elasticsearch.uris");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException(
        "Elasticsearch test URI must be configured"
    );
}

if (uri.contains("prod")) {
    throw new IllegalStateException(
        "Integration tests must not connect to production"
    );
}
~~~

Đây chỉ là guard minh họa; kiểm tra chuỗi prod không phải một ranh giới bảo mật đầy đủ. Cách tốt hơn là test chỉ nhận endpoint từ container/test environment và credential không có quyền trên production.

Không viết cleanup kiểu xóa mọi index hoặc mọi alias trong cluster. Một lỗi cấu hình endpoint có thể biến cleanup thành xóa dữ liệu ngoài ý muốn.

## 13. Dọn index còn sót sau khi process bị dừng

@AfterEach không thể chạy nếu JVM bị kill, máy bị tắt hoặc CI job bị hủy đột ngột. Vì vậy, có thể còn index test sau một lần chạy thất bại.

### 13.1. Prefix riêng

Dùng prefix cố định để có thể nhận diện:

~~~text
it-products-...
it-orders-...
~~~

Không dùng prefix quá rộng như test- nếu cluster còn chứa index của một nhóm ứng dụng khác.

### 13.2. Cleanup theo test run

Gắn run ID vào mọi index:

~~~text
it-run-20261113-8f2a-products-...
it-run-20261113-8f2a-orders-...
~~~

Sau suite, cleanup chỉ xóa index có prefix đúng run ID đó. Nếu job bị hủy, một job dọn dẹp định kỳ trên test cluster có thể xóa các index thuộc run đã quá hạn.

### 13.3. Dọn theo tuổi và namespace

Cleanup định kỳ cần:

1. Chỉ chạy trên cluster test.
2. Chỉ chọn index có prefix test được quy định.
3. Kiểm tra run ID hoặc tuổi index.
4. Không xóa index thuộc run đang hoạt động.
5. Ghi log danh sách index sẽ xóa.
6. Xóa theo danh sách tên cụ thể đã kiểm tra.

Không dùng wildcard delete trên một cluster không được cách ly. Với tài nguyên test, một container riêng có thể là cơ chế cleanup tốt nhất: dừng container sẽ loại bỏ toàn bộ index trong container.

## 14. Alias và template trong test

Một số integration test cần kiểm tra alias, index template hoặc rollover. Khi đó index isolation cần bao gồm cả alias và template liên quan.

### 14.1. Alias riêng cho test

Nếu test tạo alias:

~~~text
it-products-<token>       physical index
it-products-read-<token>  read alias
it-products-write-<token> write alias
~~~

Không dùng alias dùng chung như products-read trong cluster mà nhiều test cùng truy cập. Một test chuyển alias có thể làm test khác đọc nhầm index.

Xóa physical index test thường xóa các alias gắn với index đó. Nếu alias được gắn vào nhiều index hoặc được quản lý độc lập, hãy xóa alias test tường minh trước khi dọn.

### 14.2. Index template

Nếu production dùng index template, test cần xác nhận template được áp dụng cho tên index test. Pattern template nên bao phủ prefix test hoặc có template riêng dành cho test.

Tránh thay đổi template dùng chung trong test song song. Template là cluster-level resource, không chỉ thuộc một index. Nếu test cần kiểm tra thay đổi template, dùng cluster/container riêng hoặc serialize test đó.

### 14.3. Rollover test

Rollover cần alias và index generation. Mỗi test nên có write alias và index prefix riêng để thao tác rollover không ảnh hưởng test khác.

Sau test, xóa tất cả index generation và alias thuộc namespace của test. Chỉ xóa index hiện tại có thể để lại các generation cũ.

## 15. Kiểm thử mapping và settings

Nếu mục tiêu test là mapping:

1. Tạo index riêng.
2. Tạo mapping từ entity hoặc mapping JSON cần kiểm thử.
3. Đọc mapping thực tế từ Elasticsearch.
4. Assert field type, analyzer, nested/object và multi-fields.
5. Xóa index sau test.

Ví dụ:

~~~java
IndexOperations indexOperations =
    operations.indexOps(coordinates);

indexOperations.create();
indexOperations.putMapping(
    operations.indexOps(Product.class).createMapping()
);

Document actualMapping = indexOperations.getMapping();
~~~

Nếu test analyzer hoặc settings, cần áp dụng settings trước khi tạo index khi API yêu cầu. Một số cấu hình analyzer chỉ có thể thiết lập khi tạo index; không thể thêm tùy tiện sau khi index đã tồn tại.

Dùng index riêng bảo đảm test mapping không làm thay đổi index dùng bởi test khác.

## 16. Bulk test data và cleanup

Khi test cần nhiều document, dùng bulk insert thay vì gửi từng request:

~~~java
BulkOperations bulk = operations.bulkOps(
    BulkMode.BULK,
    Product.class,
    coordinates
);

bulk.insert(products);
bulk.execute();

operations.indexOps(coordinates).refresh();
~~~

Sau khi test kết thúc, xóa index một lần thay vì delete từng document. Nếu test cần xác minh hành vi delete document, hãy thực hiện assertion trước khi teardown xóa index.

Bulk response có thể có item-level failure dù request HTTP thành công. Với dữ liệu test lớn, hãy kiểm tra kết quả bulk theo API/version đang dùng và không giả định execute thành công đồng nghĩa mọi item đã được index.

### 16.1. Dữ liệu test xác định

Tạo fixture có ID và giá trị ổn định trong phạm vi index test:

~~~java
List<Product> products = List.of(
    product("P-100", "Keyboard", "BRAND-A"),
    product("P-101", "Mouse", "BRAND-B"),
    product("P-102", "Monitor", "BRAND-A")
);
~~~

Index riêng giúp có thể dùng ID ngắn, dễ đọc mà không sợ đụng ID ở test khác. Nếu dữ liệu được ghi vào một index dùng chung, ID nên có testRunId hoặc namespace riêng.

### 16.2. Không dựa vào thứ tự trả về mặc định

Khi search nhiều document, không giả định kết quả luôn theo thứ tự insert. Nếu test cần thứ tự, khai báo sort rõ ràng và có tie-breaker ổn định.

## 17. Xử lý test thất bại và retry

Một test có thể thất bại trước khi teardown hoàn tất. Hãy thiết kế cleanup để:

- Có index name ngay sau khi bắt đầu setup.
- Có thể kiểm tra index tồn tại.
- Xóa đúng một index của test invocation.
- Ghi log index name nếu xóa thất bại.
- Không xóa index khác theo wildcard.

Nếu cleanup thất bại do cluster tạm thời không sẵn sàng, log lại index name để job cleanup sau xử lý. Không lặp vô hạn trong @AfterEach vì điều đó có thể làm suite treo.

Khi test được retry bởi CI, mỗi lần retry nên có run token mới hoặc index token mới. Không tái sử dụng index từ lần chạy lỗi trừ khi mục tiêu test là kiểm tra khả năng resume.

## 18. Một JUnit extension quản lý index

Khi nhiều test class cần cùng quy trình tạo mapping, có thể đóng gói lifecycle vào một JUnit extension.

Một extension nên:

- Tạo index name theo test invocation.
- Lưu IndexCoordinates trong ExtensionContext.Store.
- Tạo index và mapping trước test.
- Cung cấp coordinates cho test thông qua parameter resolver hoặc một fixture object.
- Xóa index sau test.
- Không dùng static mutable field để giữ index hiện tại.

Ví dụ khái niệm:

~~~java
public record TestIndex(IndexCoordinates coordinates) {}
~~~

Test nhận fixture:

~~~java
@Test
void shouldSearchWithinItsOwnIndex(TestIndex testIndex) {
    // Ghi và đọc bằng testIndex.coordinates().
}
~~~

Chi tiết ParameterResolver, BeforeEachCallback và AfterEachCallback phụ thuộc cách extension được đăng ký. Extension hữu ích khi nhiều test cần cùng một setup; với một test class nhỏ, @BeforeEach và @AfterEach thường dễ đọc hơn.

## 19. Những lỗi thường gặp

**Dùng một index cố định cho toàn bộ suite.** Dữ liệu và cleanup của test này có thể ảnh hưởng test khác. Tạo index riêng theo test hoặc test class.

**Tạo index ngẫu nhiên nhưng vẫn gọi repository mặc định.** Repository vẫn có thể dùng index name trong @Document. Dùng IndexCoordinates qua operations hoặc cấu hình repository metadata cho đúng test scope.

**Dùng tên index chỉ dựa trên test method.** Nhiều CI fork hoặc build run có thể dùng cùng tên. Thêm token duy nhất.

**Dùng static field cho index hiện tại.** Parallel tests có thể ghi đè coordinates. Giữ state theo test invocation.

**Chỉ xóa document mà quên mapping/settings.** Test mapping sau đó có thể chạy trên index đã bị thay đổi. Xóa và tạo lại index nếu cần trạng thái hoàn toàn sạch.

**Không refresh trước khi search.** Document vừa ghi có thể chưa searchable. Refresh một lần sau khi ghi xong fixture.

**Xóa index bằng wildcard rộng.** Có thể xóa dữ liệu ngoài test. Chỉ xóa tên index đã được tạo và xác nhận thuộc namespace test.

**Teardown xóa index dùng chung.** Test chạy song song có thể đang sử dụng index đó. Không chia sẻ index giữa các test invocation.

**Không dọn tài nguyên khi test fail.** Dùng lifecycle teardown và cleanup job theo run ID để xử lý cả process bị kill.

**Dùng @DirtiesContext để thay thế cách ly dữ liệu.** Nó làm mới ApplicationContext nhưng không tự xóa index Elasticsearch. Quản lý index rõ ràng.

**Cho rằng Spring context cache cách ly index.** Context có thể được tái sử dụng trong khi index trên cluster vẫn là shared resource.

**Dùng repository và operations với hai index khác nhau mà không nhận ra.** Repository lấy index từ entity metadata; operations có thể nhận IndexCoordinates tường minh. Kiểm tra đúng đích ghi/đọc.

**Dùng chung alias trong test song song.** Alias là cluster resource. Dùng alias riêng theo test hoặc cluster riêng.

**Thay đổi index template trong test chạy song song.** Template áp dụng theo pattern và có thể ảnh hưởng index khác. Dùng template test riêng hoặc test cluster riêng.

**Không chờ reactive operation hoàn tất.** Publisher chưa được subscribe có thể chưa thực thi. Await kết quả trước khi search và cleanup.

**Dọn index trước khi async bulk hoàn tất.** Request đang chạy có thể thất bại vì index biến mất. Chờ tất cả write task hoàn tất rồi mới xóa.

## 20. Quy trình đề xuất cho integration test

Với một test method cần Elasticsearch thật:

1. Kết nối tới Elasticsearch test cluster hoặc Testcontainers.
2. Tạo index name có prefix test và token duy nhất.
3. Lưu IndexCoordinates vào state của test invocation.
4. Tạo index bằng IndexOperations.
5. Áp dụng mapping/settings cần kiểm thử.
6. Ghi fixture bằng ElasticsearchOperations với coordinates tường minh.
7. Refresh index sau khi hoàn tất ghi.
8. Thực hiện search, aggregation hoặc repository assertion.
9. Chờ mọi tác vụ async/reactive liên quan hoàn tất.
10. Trong teardown, kiểm tra index tồn tại và xóa đúng index đó.
11. Nếu cleanup thất bại, ghi log tên index để job cleanup test xử lý.

Đối với repository integration test, chọn index riêng theo test class/context hoặc cấu hình entity metadata phù hợp. Đừng giả định một repository proxy có thể chuyển index chỉ bằng cách tạo thêm một IndexCoordinates ở test.

## 21. Checklist thiết kế test an toàn

- [ ] Integration test chỉ kết nối tới Elasticsearch test cluster.
- [ ] Index name có prefix test và token duy nhất.
- [ ] Tên index hợp lệ theo Elasticsearch naming rules.
- [ ] Mỗi test invocation có IndexCoordinates riêng nếu chạy song song.
- [ ] Mapping/settings được tạo rõ ràng trước khi ghi.
- [ ] Test dùng cùng coordinates cho create, write, search và delete.
- [ ] Refresh sau khi ghi trước khi search cần dữ liệu mới.
- [ ] Repository test biết rõ index lấy từ @Document metadata.
- [ ] Không chia sẻ static mutable index name giữa các test.
- [ ] Teardown xóa đúng index, có kiểm tra tồn tại.
- [ ] Cleanup không dùng wildcard có thể chạm dữ liệu ngoài test.
- [ ] Alias và template có namespace riêng nếu được kiểm thử.
- [ ] Async/reactive/bulk operations hoàn tất trước cleanup.
- [ ] CI có cách dọn index còn sót khi process bị kill.

## 22. Tài liệu tham khảo

- [Spring Data Elasticsearch - Index Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): quản lý index, mapping, refresh và ElasticsearchOperations.
- [Spring Data Elasticsearch API - IndexOperations](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/IndexOperations.html): API tạo, kiểm tra, refresh và xóa index.
- [Spring Data Elasticsearch API - IndexCoordinates](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/mapping/IndexCoordinates.html): biểu diễn index đích cho các thao tác.
- [Spring Data Elasticsearch - Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): metadata entity và cấu hình @Document.
- [Spring Boot - Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): cấu hình test và quản lý ApplicationContext trong test.
- [JUnit 5 - User Guide](https://junit.org/junit5/docs/current/user-guide/): lifecycle hooks, test instance lifecycle và parallel execution.
- [Testcontainers - Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/): chạy Elasticsearch container cho integration test.
- [Elasticsearch - Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html): refresh và thời điểm document xuất hiện trong search.

Các API overload của Spring Data Elasticsearch, Testcontainers và Elasticsearch client có thể thay đổi theo phiên bản. Hãy kiểm tra Javadoc đúng dependency của dự án. Nguyên tắc quan trọng là dữ liệu test cần có namespace riêng, mọi thao tác phải nhắm đúng index, và cleanup chỉ được xóa tài nguyên do chính test invocation tạo ra.
