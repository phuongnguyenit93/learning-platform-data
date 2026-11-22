# Refresh tường minh hoặc chờ điều kiện thay vì dùng thời gian ngủ cố định

Khi kiểm thử ứng dụng dùng Spring Data Elasticsearch, một thao tác ghi thành công chưa chắc làm document xuất hiện ngay trong kết quả search. Elasticsearch là hệ thống near real-time: indexing cập nhật dữ liệu nội bộ, còn search chỉ nhìn thấy thay đổi sau khi shard được refresh. Vì vậy, test gọi save rồi search ngay có thể nhận danh sách rỗng dù document đã được ghi thành công.

Một cách thường thấy là gọi Thread.sleep(1000) sau khi lưu dữ liệu. Cách này không đồng bộ với trạng thái thật của Elasticsearch: máy nhanh thì test chờ thừa, máy chậm thì vẫn có thể thất bại. Test nên đồng bộ bằng refresh tường minh khi cần search visibility ngay, dùng refresh policy WAIT_UNTIL khi muốn request chờ lần refresh kế tiếp, hoặc polling một điều kiện có timeout khi công việc hoàn tất bất đồng bộ.

Bài học này giải thích refresh và near-real-time search, phân biệt GET theo ID với search, cách refresh đúng index trong Spring Data Elasticsearch, cách chọn RefreshPolicy, cách dùng Awaitility để chờ điều kiện, cách áp dụng cho reactive test và cách tránh các test chập chờn do timing.

## 1. Vì sao save xong nhưng search chưa thấy document?

Elasticsearch tách thao tác ghi document và khả năng nhìn thấy document qua search. Khi một index request thành công, document đã được chấp nhận và cập nhật vào cấu trúc dữ liệu nội bộ của shard. Searcher hiện tại chưa nhất thiết nhìn thấy segment mới ngay lập tức.

Refresh tạo searcher mới để các thay đổi đã được index trở nên khả dụng cho search. Vì vậy, Elasticsearch thường được mô tả là near real-time thay vì real-time đối với search.

Luồng ghi và search:

~~~text
Test / Application
       |
       | save(document)
       v
Elasticsearch primary shard
       |
       | indexing operation succeeds
       v
Document is indexed internally
       |
       | refresh has not happened yet
       v
Current searcher may still be stale
       |
       | scheduled or explicit refresh
       v
New searcher sees the document
       |
       v
Search returns the document
~~~

Điều này không có nghĩa thao tác save bị thất bại. Nó chỉ có nghĩa search visibility chưa được cập nhật.

### 1.1. Refresh khác với flush

Refresh và flush là hai thao tác khác nhau:

| Thao tác | Mục đích |
|---|---|
| Refresh | Làm thay đổi đã index khả dụng cho search bằng cách tạo searcher mới |
| Flush | Đẩy dữ liệu trong translog và tạo Lucene commit mới theo cơ chế durability của Elasticsearch |

Trong test cần search thấy document sau khi ghi, refresh mới là thao tác liên quan. Không gọi flush chỉ để giải quyết vấn đề search visibility.

### 1.2. Refresh không phải transaction

Refresh không biến nhiều thao tác ghi thành transaction. Nó chỉ điều khiển thời điểm search có thể nhìn thấy các thay đổi đã được index. Nếu một bulk request có item thất bại, refresh không rollback hoặc sửa lỗi item đó.

## 2. Phân biệt realtime GET và near-real-time search

Một điểm rất quan trọng trong test là GET theo ID và search có semantics khác nhau:

| Cách đọc | Tính chất | Có cần refresh để thấy lần ghi mới không? |
|---|---|---|
| GET document theo ID | Realtime mặc định | Thường không |
| Search theo field/query | Near real-time | Có thể cần chờ refresh |
| Count qua search/query | Dựa trên search visibility | Có thể cần chờ refresh |

Ví dụ ghi rồi đọc trực tiếp theo ID:

~~~java
Product saved = operations.save(
        new Product("p-100", "Keyboard"),
        IndexCoordinates.of("products"));

Product loaded = operations.get(
        saved.getId(),
        Product.class,
        IndexCoordinates.of("products"));
~~~

GET theo ID mặc định là realtime, vì vậy thường có thể đọc document vừa ghi mà không cần refresh index.

Ngược lại, search theo tên:

~~~java
SearchHits<Product> hits = operations.search(
        new CriteriaQuery(Criteria.where("name").is("Keyboard")),
        Product.class,
        IndexCoordinates.of("products"));
~~~

Search có thể chưa nhìn thấy document nếu refresh chưa diễn ra.

Không thêm refresh vào mọi test chỉ vì test có thao tác save. Hãy xác định test đang kiểm tra GET, search, count hay một pipeline bất đồng bộ.

## 3. Refresh interval mặc định

Elasticsearch thường refresh index đang được search theo chu kỳ mặc định khoảng một giây. Đây là lý do một test với Thread.sleep(1000) đôi khi có vẻ hoạt động. Nhưng chu kỳ refresh là cấu hình vận hành, không phải một đồng hồ đồng bộ dành riêng cho test.

Refresh interval có thể thay đổi theo index:

~~~http
GET products/_settings?filter_path=*.settings.index.refresh_interval
~~~

Ví dụ cấu hình:

~~~http
PUT products/_settings
{
  "index": {
    "refresh_interval": "2s"
  }
}
~~~

Nếu refresh interval được đặt thành -1, Elasticsearch không tự động refresh theo chu kỳ. Search có thể không nhìn thấy document mới cho tới khi có explicit refresh hoặc một thao tác refresh phù hợp khác.

Trong test, không nên dựa vào giá trị refresh interval hiện tại của cluster. Test cần chủ động điều khiển điểm đồng bộ hoặc chờ đúng điều kiện.

## 4. Cách không nên dùng: Thread.sleep cố định

Ví dụ dễ gặp:

~~~java
repository.save(product);
Thread.sleep(1000);

assertThat(repository.findByName("Keyboard")).hasSize(1);
~~~

Cách này có các vấn đề:

- Không biết refresh đã xảy ra hay chưa.
- Máy chạy nhanh phải chờ đủ một giây dù dữ liệu đã hiển thị sau vài millisecond.
- CI runner hoặc cluster tải cao có thể cần lâu hơn một giây.
- Tăng thời gian của toàn bộ test suite.
- Làm test phụ thuộc timing và dễ chập chờn.
- Nếu một consumer hoặc worker chưa xử lý event, ngủ một giây cũng không chứng minh công việc đã hoàn tất.

Tăng thời gian ngủ lên 3 hoặc 5 giây chỉ làm test chậm hơn và vẫn không tạo ra bảo đảm đồng bộ.

### 4.1. Sleep không chứng minh điều kiện nghiệp vụ

Giả sử test gửi message vào broker, consumer nhận message, transform dữ liệu rồi index document:

~~~text
Test publishes event
        |
        v
Broker queue
        |
        v
Consumer receives event
        |
        v
Transforms document
        |
        v
Indexes into Elasticsearch
        |
        v
Refresh makes document searchable
~~~

Thread.sleep(1000) không chứng minh consumer đã nhận message, indexing đã thành công hay refresh đã xảy ra. Test cần chờ điều kiện quan sát được, ví dụ document xuất hiện trong search.

## 5. Cách 1: refresh tường minh trong integration test

Khi test cần kiểm tra search ngay sau khi ghi fixture, cách đơn giản và xác định là gọi refresh trên đúng index trước khi search.

Spring Data Elasticsearch cung cấp IndexOperations:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Hoặc chỉ rõ index:

~~~java
operations.indexOps(IndexCoordinates.of("products")).refresh();
~~~

Ví dụ test imperative:

~~~java
@Autowired
ElasticsearchOperations operations;

@Autowired
ProductRepository repository;

@Test
void findsProductImmediatelyAfterRefresh() {
    repository.save(new Product("p-100", "Keyboard"));

    operations.indexOps(Product.class).refresh();

    assertThat(repository.findByName("Keyboard"))
            .hasSize(1);
}
~~~

Test ghi document, refresh index rồi kiểm tra qua query method. Không cần đợi một khoảng thời gian ước lượng.

### 5.1. Refresh sau khi chuẩn bị fixture

Nếu một test tạo nhiều document:

~~~java
@BeforeEach
void setUp() {
    repository.saveAll(List.of(
            new Product("p-100", "Keyboard"),
            new Product("p-101", "Mouse"),
            new Product("p-102", "Monitor")));

    operations.indexOps(Product.class).refresh();
}
~~~

Mọi test trong lớp có thể search fixture ngay sau khi setup hoàn tất.

### 5.2. Chỉ refresh index liên quan

Ưu tiên:

~~~java
operations.indexOps(IndexCoordinates.of("products")).refresh();
~~~

thay vì refresh toàn bộ cluster:

~~~http
POST /_refresh
~~~

Refresh toàn cluster có thể ảnh hưởng nhiều index và làm test phụ thuộc vào dữ liệu của suite khác. Refresh đúng index giảm tác động và làm phạm vi test rõ ràng hơn.

Nếu repository dùng alias, hãy xác định alias có trỏ tới index đích nào và refresh đúng tập index cần kiểm tra. Trong test isolation, một index riêng cho test thường dễ kiểm soát hơn alias dùng chung.

### 5.3. Dọn dữ liệu cũng cần refresh nếu test sau dùng search

Nếu test xóa fixture rồi test tiếp theo tìm bằng search, thao tác delete cũng có thể chưa hiển thị ngay với searcher hiện tại.

Ví dụ:

~~~java
@AfterEach
void cleanUp() {
    repository.deleteAll();
    operations.indexOps(Product.class).refresh();
}
~~~

Với suite lớn, tốt hơn là tạo index riêng theo test class hoặc test run rồi xóa index sau khi hoàn tất. Nếu dùng chung index, cần kiểm soát dữ liệu và refresh trong cả setup lẫn cleanup.

## 6. Cách 2: dùng RefreshPolicy.IMMEDIATE

RefreshPolicy.IMMEDIATE yêu cầu Elasticsearch refresh ngay sau thao tác ghi để thay đổi trở nên search-visible trước khi request hoàn tất.

Spring Data Elasticsearch dùng RefreshPolicy trong các API hỗ trợ refresh policy, chẳng hạn BulkOptions:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.IMMEDIATE)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

Sau khi bulkIndex trả về thành công, test có thể search các document đã được ghi bởi request đó.

### 6.1. Khi nào IMMEDIATE phù hợp?

IMMEDIATE phù hợp khi:

- Test cần xác minh semantics của request có refresh ngay.
- Một thao tác ghi đơn lẻ phải được search-visible trước khi response trả về theo yêu cầu cụ thể.
- Test không thể đặt explicit refresh ở tầng fixture vì đang kiểm tra chính refresh policy.

Trong test thông thường, explicit refresh sau khi chuẩn bị dữ liệu thường đơn giản hơn việc bật IMMEDIATE cho mọi request.

### 6.2. Vì sao không bật IMMEDIATE trong production cho mọi request?

Refresh tạo searcher mới và có chi phí CPU, I/O, segment management. Refresh sau từng request có thể tạo nhiều segment nhỏ, làm tăng chi phí merge và giảm throughput indexing.

Không dùng IMMEDIATE mặc định cho mọi write chỉ để search thấy dữ liệu ngay. Chọn policy dựa trên yêu cầu visibility và tải hệ thống.

## 7. Cách 3: dùng RefreshPolicy.WAIT_UNTIL

WAIT_UNTIL yêu cầu request ghi chờ lần refresh kế tiếp làm cho thay đổi của request trở nên search-visible. Elasticsearch không cần ép refresh ngay tại thời điểm request hoàn tất; nó chờ refresh theo lịch hoặc một refresh khác.

Ví dụ bulk:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

Khi request trả về, các thay đổi thuộc request đã được refresh và có thể search được.

### 7.1. WAIT_UNTIL khác IMMEDIATE

| Policy | Hành vi | Chi phí/độ trễ |
|---|---|---|
| NONE | Không yêu cầu refresh riêng | Thường tốt nhất cho throughput |
| IMMEDIATE | Ép refresh ngay | Có thể tăng chi phí refresh |
| WAIT_UNTIL | Chờ lần refresh kế tiếp | Thường tránh refresh thừa, nhưng request có thể chờ |

WAIT_UNTIL hữu ích khi caller cần search visibility trước khi tiếp tục nhưng không cần ép refresh ngay lập tức.

### 7.2. WAIT_UNTIL có thể chờ lâu

Nếu index tắt automatic refresh bằng refresh_interval = -1 và không có thao tác refresh khác, request WAIT_UNTIL có thể chờ cho tới khi được refresh hoặc timeout. Khi dùng policy này, bảo đảm index có refresh schedule hoặc có cơ chế explicit refresh.

Test nên có timeout ở cấp test framework để không treo vô hạn nếu cấu hình index sai.

### 7.3. WAIT_UNTIL trong BulkOptions không đồng nghĩa mọi write đều tự chờ

Refresh policy chỉ áp dụng cho request được cấu hình bằng options đó. Một thao tác save riêng lẻ hoặc một client khác không tự thừa hưởng policy của BulkOptions. Đừng giả định việc cấu hình BulkOptions trong một helper ảnh hưởng mọi thao tác của test suite.

## 8. Chọn chiến lược phù hợp cho từng loại test

| Mục tiêu test | Cách đồng bộ nên dùng |
|---|---|
| Kiểm tra GET theo ID sau save | Đọc trực tiếp; thường không cần refresh |
| Ghi fixture rồi search ngay | Explicit refresh sau setup |
| Kiểm tra request bulk có refresh semantics | IMMEDIATE hoặc WAIT_UNTIL theo yêu cầu |
| Kiểm tra search visibility sau một write | Explicit refresh hoặc WAIT_UNTIL |
| Kiểm tra consumer/event pipeline bất đồng bộ | Poll điều kiện search-visible với timeout |
| Kiểm tra eventual consistency | Poll cho đến khi điều kiện đúng hoặc timeout |
| Test unit chỉ mock repository | Không cần refresh Elasticsearch |

Không nên dùng một helper sleep chung cho mọi test. Chọn đồng bộ theo hành vi mà test đang xác minh.

## 9. Chờ điều kiện với Awaitility

Awaitility là thư viện giúp test chờ một điều kiện bất đồng bộ theo kiểu khai báo. Thay vì đoán cần ngủ bao lâu, test mô tả trạng thái mong muốn và thời gian tối đa cho phép.

Dependency Gradle:

~~~kotlin
testImplementation("org.awaitility:awaitility:4.2.2")
~~~

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.2.2</version>
    <scope>test</scope>
</dependency>
~~~

Ví dụ chờ document xuất hiện trong search:

~~~java
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

@Test
void waitsUntilProductBecomesSearchable() {
    eventPublisher.publishEvent(
            new ProductCreatedEvent("p-100", "Keyboard"));

    await()
            .alias("product becomes searchable")
            .atMost(Duration.ofSeconds(10))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() ->
                    assertThat(repository.findByName("Keyboard"))
                            .extracting(Product::getId)
                            .contains("p-100"));
}
~~~

Awaitility thực hiện assertion nhiều lần cho tới khi thành công hoặc hết timeout. Test không phải tự tính thời điểm consumer chạy xong hay refresh diễn ra.

### 9.1. until và untilAsserted

Hai kiểu chờ phổ biến:

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> repository.existsById("p-100"));
~~~

~~~java
await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
                assertThat(repository.findByName("Keyboard"))
                        .isNotEmpty());
~~~

until chờ một điều kiện boolean trở thành true. untilAsserted chạy assertion và lặp lại khi assertion chưa đạt.

Chọn untilAsserted khi muốn kiểm tra cả nội dung, số lượng hoặc trạng thái document. Chọn until khi điều kiện có thể biểu diễn gọn bằng boolean.

### 9.2. Chờ số lượng document

Ví dụ một consumer tạo nhiều document:

~~~java
await()
        .alias("all imported products are searchable")
        .atMost(Duration.ofSeconds(15))
        .pollInterval(Duration.ofMillis(200))
        .untilAsserted(() ->
                assertThat(repository.findByImportId("batch-42"))
                        .hasSize(100));
~~~

Điều kiện chỉ thành công khi đủ 100 document xuất hiện trong search. Nếu chỉ chờ isNotEmpty(), test có thể kết thúc ngay khi mới có document đầu tiên dù pipeline chưa xử lý xong batch.

### 9.3. Chờ một trạng thái cụ thể

Nếu document được cập nhật qua nhiều trạng thái:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            Product product = repository.findById("p-100")
                    .orElseThrow();
            assertThat(product.getStatus()).isEqualTo("INDEXED");
        });
~~~

Nếu điều kiện yêu cầu search visibility, hãy dùng query method/search thay cho GET by ID. GET realtime có thể nhìn thấy document trước khi searcher được refresh, do đó không kiểm tra đúng điều kiện search-visible.

## 10. Chờ một pipeline bất đồng bộ hoàn tất

Với message broker, event listener hoặc background worker, điều kiện cần chờ thường là trạng thái cuối trong Elasticsearch.

Ví dụ:

~~~java
@Test
void indexesProductAfterReceivingEvent() {
    eventPublisher.publishEvent(
            new ProductImportedEvent("p-100", "Keyboard"));

    await()
            .atMost(Duration.ofSeconds(15))
            .pollInterval(Duration.ofMillis(100))
            .untilAsserted(() -> {
                List<Product> results =
                        repository.findByExternalId("p-100");

                assertThat(results).hasSize(1);
                assertThat(results.getFirst().getName())
                        .isEqualTo("Keyboard");
            });
}
~~~

Điều kiện này bao gồm toàn bộ pipeline: event được xử lý, document được ghi và search visibility được cập nhật.

Nếu pipeline phát ra completion signal đáng tin cậy, có thể chờ signal đó rồi refresh index trước khi search. Nếu test đang kiểm tra eventual consistency từ góc nhìn người đọc, poll query search là chính xác hơn.

### 10.1. Không poll một điều kiện không liên quan

Chờ event queue rỗng chưa chắc chứng minh document đã searchable: consumer có thể ack message trước khi refresh. Ngược lại, search có thể thấy document trước khi toàn bộ batch hoàn tất.

Điều kiện chờ phải khớp với điều mà test muốn bảo đảm:

- Muốn biết consumer đã nhận event: chờ consumer acknowledgement/observable state.
- Muốn biết document đã ghi theo ID: GET theo ID.
- Muốn biết document đã search-visible: query search.
- Muốn biết toàn batch hoàn tất: kiểm tra tổng số hoặc completion record của batch.

## 11. Chờ condition phải có timeout và polling interval

Một wait không có timeout có thể treo test suite vô hạn. Mỗi điều kiện chờ nên có:

- Timeout tối đa.
- Poll interval hợp lý.
- Mô tả điều kiện bằng alias để dễ đọc khi fail.
- Assertion đủ mạnh để chứng minh trạng thái cuối.
- Thông tin chẩn đoán khi timeout.

Ví dụ:

~~~java
await()
        .alias("projection batch batch-42 reaches 100 products")
        .atMost(Duration.ofSeconds(20))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() ->
                assertThat(repository.findByImportId("batch-42"))
                        .hasSize(100));
~~~

Không poll mỗi 1 millisecond. Poll quá dày tạo tải search không cần thiết và có thể ảnh hưởng cluster mà test đang kiểm tra.

### 11.1. Chọn timeout dựa trên hợp đồng test

Timeout phải phản ánh SLA hoặc thời gian tối đa hợp lý của pipeline trong môi trường test. Một consumer chạy local có thể hoàn thành nhanh, nhưng CI runner và Elasticsearch container có thể chậm hơn.

Không tăng timeout quá lớn chỉ để che lỗi pipeline. Nếu một test thường xuyên cần gần hết timeout, hãy điều tra throughput, queue, refresh interval hoặc race condition.

### 11.2. Timeout không phải thời gian ngủ

Timeout là giới hạn trên. Polling dừng ngay khi điều kiện đúng. Nếu dữ liệu xuất hiện sau 80 ms, test kết thúc sau khoảng thời gian đó, không phải chờ hết 10 giây.

## 12. Kết hợp explicit refresh và Awaitility

Hai cách này giải quyết các vấn đề khác nhau:

- Explicit refresh đồng bộ search visibility cho những thao tác ghi đã hoàn tất.
- Awaitility chờ một điều kiện bất đồng bộ có thể cần nhiều bước hoặc nhiều lần retry.

Ví dụ chuẩn bị fixture bằng saveAll:

~~~java
@BeforeEach
void prepareProducts() {
    repository.saveAll(testProducts);
    operations.indexOps(Product.class).refresh();
}
~~~

Sau đó test search trực tiếp:

~~~java
@Test
void filtersProductsByCategory() {
    List<Product> results = repository.findByCategory("accessories");

    assertThat(results).hasSize(3);
}
~~~

Với consumer bất đồng bộ:

~~~java
@Test
void eventuallyIndexesImportedProduct() {
    eventPublisher.publishEvent(
            new ProductImportedEvent("p-200", "Monitor"));

    await()
            .atMost(Duration.ofSeconds(10))
            .untilAsserted(() ->
                    assertThat(repository.findByExternalId("p-200"))
                            .hasSize(1));
}
~~~

Không gọi explicit refresh ngay sau khi publish event nếu consumer chưa ghi xong; refresh sớm không làm event được xử lý nhanh hơn. Polling điều kiện cuối phù hợp hơn cho pipeline này.

## 13. Refresh trong test reactive

Reactive Spring Data Elasticsearch cung cấp reactive index operations. Trong test, có thể nối refresh publisher trước query publisher:

~~~java
Mono<Void> refresh = reactiveOperations
        .indexOps(Product.class)
        .refresh();

Flux<Product> searchableProducts = refresh
        .thenMany(repository.findByCategory("accessories"));

StepVerifier.create(searchableProducts)
        .expectNextCount(3)
        .verifyComplete();
~~~

Điểm quan trọng là dùng thenMany để query chỉ bắt đầu sau khi refresh hoàn tất. Nếu chỉ tạo hai publisher riêng biệt mà không nối chúng, thứ tự thực thi không được bảo đảm.

### 13.1. Không subscribe riêng để refresh

Tránh:

~~~java
reactiveOperations.indexOps(Product.class).refresh().subscribe();

return repository.findByCategory("accessories");
~~~

Refresh và search chạy trong hai subscription độc lập. Search có thể chạy trước refresh.

Hãy composition:

~~~java
return reactiveOperations.indexOps(Product.class)
        .refresh()
        .thenMany(repository.findByCategory("accessories"));
~~~

### 13.2. Dùng StepVerifier với timeout

~~~java
StepVerifier.create(
        reactiveOperations.indexOps(Product.class)
                .refresh()
                .thenMany(repository.findByCategory("accessories")))
        .expectNextCount(3)
        .verify(Duration.ofSeconds(5));
~~~

Timeout của StepVerifier ngăn test chờ vô hạn nếu publisher không hoàn tất. Timeout này khác với polling: nó giới hạn thời gian chờ một publisher, không tự lặp lại search để đợi điều kiện eventual consistency.

### 13.3. Poll reactive condition khi pipeline bất đồng bộ

Nếu test cần đợi event consumer cập nhật search index, có thể dùng Awaitility để thử lại một assertion dựa trên publisher. Test thread có thể chờ publisher trong mỗi lần thử; không đưa block vào code ứng dụng:

~~~java
await()
        .atMost(Duration.ofSeconds(10))
        .pollInterval(Duration.ofMillis(150))
        .untilAsserted(() ->
                StepVerifier.create(
                                repository.findByExternalId("p-200").take(1))
                        .expectNextCount(1)
                        .verifyComplete());
~~~

Mỗi lần Awaitility chạy assertion, StepVerifier subscribe một lần vào query reactive. Khi chưa có hit, assertion thất bại và Awaitility thử lại tới timeout.

## 14. Refresh policy cho bulk indexing

Bulk request có thể cấu hình refresh policy. Trong Spring Data Elasticsearch:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products"));
~~~

Nếu test đang kiểm tra rằng bulk request chỉ trả về sau khi dữ liệu search-visible, WAIT_UNTIL là lựa chọn phù hợp.

Dùng IMMEDIATE nếu test cần kiểm tra force refresh behavior:

~~~java
BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.IMMEDIATE)
        .build();
~~~

Dùng NONE nếu test chỉ kiểm tra indexing response hoặc đọc trực tiếp theo ID và không cần search visibility ngay.

### 14.1. Bulk partial failure vẫn phải được kiểm tra

Refresh policy không bảo đảm mọi item bulk đều thành công. Test cần kiểm tra kết quả từng item hoặc exception tương ứng. Nếu một item mapping error, refresh không biến item đó thành document hợp lệ.

### 14.2. Không dùng WAIT_UNTIL như một thay thế cho consumer completion

WAIT_UNTIL chỉ áp dụng cho request ghi đang chờ refresh. Nó không chờ các message khác trong broker, không chờ job khác ghi thêm document và không đảm bảo batch bên ngoài đã hoàn tất.

Nếu cần đợi toàn bộ pipeline, poll trạng thái cuối hoặc chờ completion signal phù hợp.

## 15. Refresh trong Elasticsearch REST API

Elasticsearch cung cấp Refresh API:

~~~http
POST products/_refresh
~~~

Hoặc refresh tất cả index:

~~~http
POST /_refresh
~~~

Trong ứng dụng Spring Data, thường ưu tiên IndexOperations.refresh() vì nó giữ logic test ở abstraction đang sử dụng và chọn index theo domain/index coordinates.

Index, update và bulk REST API cũng hỗ trợ query parameter refresh với các giá trị:

| Giá trị | Ý nghĩa |
|---|---|
| false hoặc bỏ qua | Không yêu cầu refresh |
| true | Refresh ngay các shard liên quan |
| wait_for | Chờ lần refresh kế tiếp |

true tương ứng với hành vi immediate refresh; wait_for tương ứng với chờ refresh. Tên enum ở Spring Data là RefreshPolicy.IMMEDIATE, RefreshPolicy.WAIT_UNTIL và RefreshPolicy.NONE.

## 16. Thiết lập index trong integration test

Test nên kiểm soát index và mapping để tránh phụ thuộc môi trường developer hoặc cluster dùng chung.

Ví dụ:

~~~java
@BeforeEach
void createIndexIfNeeded() {
    IndexOperations indexOps = operations.indexOps(Product.class);

    if (!indexOps.exists()) {
        indexOps.createWithMapping();
    }
}
~~~

Nếu test cần trạng thái rỗng:

~~~java
@BeforeEach
void resetIndex() {
    IndexOperations indexOps = operations.indexOps(Product.class);

    if (indexOps.exists()) {
        indexOps.delete();
    }

    indexOps.createWithMapping();
}
~~~

Việc delete/recreate index phù hợp với index test riêng. Không thực hiện trên index production hoặc index dùng chung với dữ liệu ngoài test.

Sau khi tạo fixture, refresh một lần:

~~~java
repository.saveAll(products);
operations.indexOps(Product.class).refresh();
~~~

Một lần refresh sau batch fixture thường hiệu quả hơn refresh sau từng entity.

## 17. Testcontainers và refresh

Testcontainers giúp integration test chạy với Elasticsearch thật trong container. Dù container khởi động thành công, test vẫn phải xử lý semantics refresh của Elasticsearch.

Một test có thể:

1. Khởi động Elasticsearch container.
2. Cấu hình Spring Data client trỏ tới mapped port.
3. Tạo index và mapping.
4. Ghi fixture.
5. Refresh index.
6. Thực hiện search assertion.
7. Dọn index hoặc document sau test.

Testcontainers giải quyết tính nhất quán của môi trường test; explicit refresh giải quyết search visibility. Hai việc này bổ sung cho nhau.

Không nên thêm sleep sau khi container start để đoán Elasticsearch đã sẵn sàng. Dùng wait strategy/health check của Testcontainers hoặc kiểm tra endpoint cluster health trước khi chạy test.

## 18. Chờ Elasticsearch sẵn sàng khác với chờ document searchable

Có hai điều kiện thường bị nhầm:

1. Elasticsearch service đã sẵn sàng nhận request.
2. Một document cụ thể đã xuất hiện trong search result.

Để chờ service sẵn sàng, dùng health check hoặc Testcontainers wait strategy:

~~~java
static ElasticsearchContainer elasticsearch =
        new ElasticsearchContainer("docker.elastic.co/elasticsearch/elasticsearch:8.17.0");
~~~

Testcontainers có thể chờ HTTP endpoint trả response phù hợp trước khi báo container ready. Version image phải tương thích với Spring Data Elasticsearch và Java client đang dùng.

Để chờ document searchable, dùng refresh hoặc poll query cụ thể. Health check cluster không chứng minh document đã được ghi.

## 19. Thiết kế helper dùng chung cho test

Nếu nhiều test cần explicit refresh, tạo helper nhỏ:

~~~java
public final class ElasticsearchTestSupport {

    private final ElasticsearchOperations operations;

    public ElasticsearchTestSupport(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void refreshProducts() {
        operations.indexOps(IndexCoordinates.of("products")).refresh();
    }
}
~~~

Test:

~~~java
repository.saveAll(products);
testSupport.refreshProducts();

assertThat(repository.findByCategory("accessories"))
        .hasSize(3);
~~~

Helper nên có tên thể hiện index được refresh. Tránh một method chung sleepUntilReady() vì nó không mô tả điều kiện thật.

### 19.1. Helper chờ điều kiện

Với pipeline async, có thể đóng gói Awaitility:

~~~java
public final class ElasticsearchAwait {

    public static void untilAsserted(ThrowingRunnable assertion) {
        await()
                .atMost(Duration.ofSeconds(10))
                .pollInterval(Duration.ofMillis(100))
                .untilAsserted(assertion);
    }

    private ElasticsearchAwait() {
    }
}
~~~

Không làm timeout mặc định quá dài hoặc không thể override. Test có pipeline chậm hơn nên truyền timeout rõ ràng thay vì âm thầm tăng thời gian cho mọi test.

## 20. Chẩn đoán test timeout

Nếu explicit refresh xong mà search vẫn không thấy document, vấn đề có thể không còn là refresh:

- Document chưa được ghi thành công.
- Test ghi vào index khác với index mà query tìm kiếm.
- Alias trỏ tới index khác.
- ID hoặc field mapping sai.
- Query không khớp dữ liệu.
- Bulk item bị lỗi.
- Document bị xóa hoặc update bởi test khác.
- Search filter hoặc routing loại document khỏi kết quả.

Nếu Awaitility timeout, nên in thông tin chẩn đoán an toàn:

- Index/alias đang query.
- ID hoặc correlation ID của fixture.
- Số lượng hit hiện tại.
- Trạng thái consumer/job nếu có.
- Bulk failure summary nếu có.
- Cluster health và lỗi kết nối nếu cần.

Không log toàn bộ document chứa dữ liệu nhạy cảm chỉ để chẩn đoán.

## 21. Tránh race condition giữa các test

Các test chạy song song trên cùng một index có thể làm nhau thất bại:

- Test A xóa toàn bộ index trong khi test B đang search.
- Test A refresh sau khi test B mới ghi fixture.
- Test B đếm document nhưng test A cũng ghi dữ liệu.
- Hai test dùng cùng ID và ghi đè nhau.

Giải pháp:

- Dùng index riêng theo test class hoặc test run.
- Dùng ID có namespace test.
- Không dùng deleteAll trên index dùng chung giữa các test chạy song song.
- Dọn dữ liệu theo ID hoặc xóa index test riêng.
- Chỉ refresh index mà test sở hữu.
- Tắt parallel execution nếu test thật sự chia sẻ tài nguyên và chưa được cô lập.

Refresh không giải quyết race condition do dữ liệu test dùng chung. Nó chỉ cập nhật search visibility.

## 22. Chọn poll interval và timeout hợp lý

Poll interval quá ngắn tạo nhiều request search; poll interval quá dài làm test chờ không cần thiết sau khi điều kiện đã đúng.

Ví dụ khởi điểm:

| Loại test | Poll interval minh họa | Timeout minh họa |
|---|---:|---:|
| Một document trong local container | 50–100 ms | 3–5 s |
| Event consumer đơn giản | 100–200 ms | 5–10 s |
| Import batch lớn | 200–500 ms | 15–30 s |
| CI environment chậm | 200–500 ms | Theo SLA test |

Đây là điểm bắt đầu để điều chỉnh theo thời gian thực tế, không phải giá trị bắt buộc. Theo dõi thời gian hoàn thành của pipeline và tỷ lệ timeout trong CI.

Nếu pipeline xử lý hàng nghìn document, tốt hơn là có batch completion signal hoặc trạng thái job thay vì polling một search query nặng với tần suất cao.

## 23. Các lỗi thường gặp

### Gọi save rồi search ngay

Index request có thể thành công nhưng searcher chưa được refresh. Refresh index trước search hoặc chờ WAIT_UNTIL.

### Dùng Thread.sleep(1000)

Sleep không biết refresh đã xảy ra hay chưa. Dùng explicit refresh hoặc condition polling có timeout.

### Refresh toàn cluster

Refresh tất cả index có thể ảnh hưởng test khác. Refresh đúng index hoặc alias test đang sở hữu.

### Refresh trước khi consumer ghi xong

Refresh sớm không xử lý event hoặc làm worker hoàn thành. Chờ điều kiện cuối của pipeline.

### Dùng GET by ID để kiểm tra search visibility

GET realtime có thể trả document trước khi search nhìn thấy. Dùng query search nếu mục tiêu là search visibility.

### Dùng WAIT_UNTIL khi refresh interval bị tắt

Nếu không có scheduled refresh, request có thể chờ tới khi có refresh khác hoặc timeout. Cấu hình refresh rõ ràng trong test.

### Dùng IMMEDIATE cho mọi production write

Refresh quá thường xuyên làm giảm indexing throughput. Dùng policy theo yêu cầu và để NONE cho luồng ghi không cần visibility tức thì.

### Tạo publisher refresh nhưng không nối với search

Trong reactive test, hai publisher riêng biệt không bảo đảm thứ tự. Dùng thenMany hoặc concat để query chạy sau refresh.

### Gọi subscribe trong test setup rồi search

Subscription độc lập có thể chưa hoàn tất trước search. Composition publisher và chờ kết quả bằng StepVerifier.

### Poll điều kiện quá yếu

Chỉ kiểm tra có ít nhất một document có thể kết thúc sớm khi batch chưa hoàn tất. Kiểm tra đúng số lượng hoặc trạng thái cuối.

### Poll không có timeout

Test có thể treo vô hạn. Luôn đặt atMost và mô tả condition bằng alias.

### Poll quá thường xuyên

Tạo tải search không cần thiết. Chọn poll interval hợp lý và giới hạn concurrency.

### Nhầm cluster readiness với document visibility

Health check chỉ chứng minh Elasticsearch sẵn sàng nhận request. Nó không chứng minh event đã được xử lý hoặc document đã searchable.

### Dùng index dùng chung cho test chạy song song

Refresh không ngăn test khác xóa/ghi dữ liệu. Cô lập index và fixture.

## 24. Quy trình kiểm thử đề xuất

Khi viết integration test với Spring Data Elasticsearch:

1. Xác định test cần kiểm tra GET realtime hay search visibility.
2. Dùng Elasticsearch container/cluster có version tương thích.
3. Chờ cluster sẵn sàng bằng health check hoặc Testcontainers wait strategy.
4. Tạo index và mapping dành riêng cho test.
5. Ghi fixture bằng repository hoặc operations.
6. Nếu search ngay sau fixture, gọi IndexOperations.refresh trên đúng index.
7. Nếu kiểm tra refresh policy, cấu hình IMMEDIATE hoặc WAIT_UNTIL cho request tương ứng.
8. Nếu chờ consumer/event pipeline, poll điều kiện search-visible bằng Awaitility.
9. Đặt timeout và poll interval rõ ràng.
10. Kiểm tra số lượng/trạng thái cuối, không chỉ kiểm tra có một hit.
11. Khi test reactive, composition refresh và search bằng thenMany; dùng StepVerifier để chờ publisher.
12. Dọn dữ liệu/index trong phạm vi test và refresh nếu test sau cần search thấy trạng thái đã xóa.
13. Cô lập index khi chạy test song song.
14. Khi timeout, kiểm tra indexing result, index đích, query, mapping và trạng thái pipeline thay vì tăng sleep.

## 25. Tổng kết

Elasticsearch search là near real-time. Một document có thể đã được ghi thành công nhưng chưa xuất hiện trong search cho tới khi shard được refresh. GET theo ID mặc định là realtime nên thường không cần refresh; search và count dựa trên searcher nên có thể cần chờ refresh.

Trong integration test, explicit refresh qua IndexOperations là cách rõ ràng để làm fixture search-visible ngay. Với bulk request, RefreshPolicy.IMMEDIATE ép refresh ngay, WAIT_UNTIL chờ lần refresh kế tiếp và NONE không yêu cầu refresh riêng. Không nên dùng IMMEDIATE cho mọi production write vì refresh có chi phí.

Với pipeline bất đồng bộ, dùng Awaitility để chờ một điều kiện quan sát được như document xuất hiện trong search, đủ số lượng item hoặc đạt trạng thái cuối. Mỗi wait cần timeout và poll interval hợp lý. Với reactive test, nối refresh và search bằng thenMany rồi kiểm tra publisher bằng StepVerifier; không subscribe riêng hoặc block trong code ứng dụng.

Thread.sleep cố định không đồng bộ với trạng thái thật và làm test vừa chậm vừa chập chờn. Chọn explicit refresh, refresh policy hoặc condition polling theo đúng điều mà test muốn chứng minh; cô lập index và fixture để tránh race giữa các test.

## Tài liệu tham khảo

- [Spring Data Elasticsearch – IndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/IndexOperations.html)
- [Spring Data Elasticsearch – ReactiveIndexOperations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/ReactiveIndexOperations.html)
- [Spring Data Elasticsearch – BulkOptions API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/BulkOptions.html)
- [Spring Data Elasticsearch – RefreshPolicy API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/RefreshPolicy.html)
- [Elasticsearch – Near real-time search](https://www.elastic.co/guide/en/elasticsearch/reference/current/near-real-time.html)
- [Elasticsearch – Refresh API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-refresh.html)
- [Elasticsearch – Index API refresh parameter](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html#index-refresh)
- [Awaitility – Usage](https://github.com/awaitility/awaitility/wiki/Usage)
- [Testcontainers – Elasticsearch Module](https://java.testcontainers.org/modules/elasticsearch/)
