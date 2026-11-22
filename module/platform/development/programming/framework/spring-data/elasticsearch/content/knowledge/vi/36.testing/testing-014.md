# Không giả định rollback giao dịch sẽ dọn tài liệu Elasticsearch

Trong ứng dụng Spring, một service có thể cập nhật database và đồng thời ghi document vào Elasticsearch. Nếu service được đánh dấu @Transactional, nhiều người dễ nghĩ rằng khi một bước thất bại thì cả database lẫn Elasticsearch đều được rollback. Giả định này thường sai.

Spring transaction chỉ điều phối những tài nguyên được transaction manager tương ứng quản lý. Một JDBC transaction có thể rollback thay đổi trong database, nhưng lời gọi Elasticsearch qua HTTP/REST client thường là một thao tác độc lập. Khi Elasticsearch đã nhận và lưu document, việc database rollback không tự xóa document đó.

Điều này đặc biệt dễ gây nhầm trong integration test. Một test có @Transactional thường được Spring TestContext rollback database sau khi test kết thúc. Document đã được ghi vào Elasticsearch vẫn có thể tồn tại và ảnh hưởng đến test tiếp theo.

Bài học cần nhớ:

- Rollback database không đồng nghĩa rollback Elasticsearch.
- @Transactional không tạo transaction phân tán giữa relational database và Elasticsearch.
- Bulk request cũng không phải transaction nguyên tử cho nhiều document.
- Nếu cần đồng bộ hai hệ thống, phải thiết kế consistency, retry và compensation rõ ràng.
- Test phải dọn dữ liệu Elasticsearch riêng, bằng ID hoặc index được cô lập.

## 1. Transaction trong Spring quản lý tài nguyên nào?

Annotation @Transactional đánh dấu một ranh giới giao dịch ở tầng Spring. Khi method được gọi qua transaction proxy, Spring chọn transaction manager phù hợp để bắt đầu, commit hoặc rollback giao dịch.

Ví dụ với database:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Transactional
        public Product create(Product product) {
            return repository.save(product);
        }
    }

Nếu repository dùng JPA/JDBC và transaction manager quản lý connection database, thao tác save tham gia transaction đó. Nếu method ném RuntimeException trước khi commit, database transaction có thể rollback theo rollback rules của Spring.

Transaction manager không tự động tìm mọi lời gọi mạng được thực hiện bên trong method. Một HTTP request, file write, gửi email hoặc thao tác Elasticsearch không tự trở thành tài nguyên transactional chỉ vì nó được gọi từ một method có @Transactional.

Ví dụ:

    @Transactional
    public Product create(Product product) {
        ProductEntity saved = databaseRepository.save(
            ProductEntity.from(product)
        );

        operations.save(product);

        return Product.from(saved);
    }

Trong ví dụ này:

1. Database repository tham gia transaction database đang mở.
2. operations.save gửi request đến Elasticsearch.
3. Elasticsearch xử lý request độc lập và có thể lưu document.
4. Nếu method thất bại sau bước 2, Spring có thể rollback database.
5. Document Elasticsearch đã ghi không tự bị xóa.

@Transactional xác định ranh giới cho transaction manager đang được chọn; nó không biến mọi side effect bên trong method thành một transaction duy nhất.

## 2. Elasticsearch không tham gia JDBC transaction thông thường

Spring Data Elasticsearch giao tiếp với Elasticsearch thông qua client và transport HTTP. Request index, update hoặc delete được gửi đến cluster và được Elasticsearch xử lý theo API của nó.

Một JDBC transaction manager không có khả năng rollback request HTTP đã được Elasticsearch xác nhận. Elasticsearch cũng không tham gia transaction coordinator của database theo cách tạo ra atomic commit chung cho cả hai hệ thống.

Không có transaction chung như sau trong cách tích hợp thông thường:

    BEGIN
      UPDATE relational_database
      INDEX elasticsearch_document
    COMMIT BOTH

Nếu database rollback, Elasticsearch không tự nhận một lệnh rollback. Nếu Elasticsearch đã index document, thay đổi đó vẫn tồn tại cho đến khi có thao tác ghi/xóa khác.

Ngay cả khi ứng dụng khai báo nhiều transaction manager hoặc gọi nhiều repository trong cùng service, điều đó cũng không tự tạo atomic transaction xuyên qua database và Elasticsearch. Muốn phối hợp nhiều hệ thống cần một kiến trúc phân tán có cơ chế recovery, chứ không chỉ thêm annotation.

## 3. Timeline: database rollback nhưng Elasticsearch vẫn còn document

Giả sử service tạo sản phẩm:

    @Transactional
    public void create(Product product) {
        databaseRepository.save(ProductEntity.from(product));
        elasticsearchOperations.save(product);
        throw new IllegalStateException("later step failed");
    }

Timeline:

    Database transaction       Elasticsearch
    --------------------       -------------
    BEGIN
    INSERT product
                               INDEX product
                               ACK success
    Exception
    ROLLBACK
                               Document vẫn tồn tại

Kết quả:

| Hệ thống | Trạng thái cuối |
|---|---|
| Database | Không có product vì transaction rollback |
| Elasticsearch | Có thể vẫn có document product |

Search index lúc này chứa dữ liệu không còn tồn tại trong source database. Đây là orphan document hoặc stale projection.

Nếu test tiếp theo search theo product ID, nó có thể tìm thấy document do test trước để lại. Test có thể thất bại dù code của test hiện tại đúng.

## 4. Chiều ngược lại cũng có thể xảy ra

Nếu ứng dụng ghi Elasticsearch trước rồi ghi database:

    @Transactional
    public void create(Product product) {
        elasticsearchOperations.save(product);
        databaseRepository.save(ProductEntity.from(product));
    }

Nếu database ghi lỗi hoặc transaction rollback sau đó, Elasticsearch có thể giữ document trong khi database không có record tương ứng.

Nếu ứng dụng ghi database trước rồi ghi Elasticsearch, cũng có rủi ro:

- Database commit thành công nhưng Elasticsearch request thất bại.
- Database commit thành công nhưng ứng dụng chết trước khi gửi request.
- Elasticsearch timeout và ứng dụng không biết request đã được xử lý hay chưa.

Hai thứ tự đều có failure window. Đổi thứ tự thao tác không giải quyết được việc thiếu transaction atomic giữa hai hệ thống.

## 5. Bốn tình huống dual-write cần phân biệt

| Tình huống | Database | Elasticsearch | Hệ quả |
|---|---|---|---|
| DB ghi thành công, ES ghi thành công | Commit | Đã index | Trạng thái mong muốn |
| ES ghi thành công, DB rollback | Rollback | Đã index | Orphan document |
| DB commit, ES ghi thất bại | Commit | Chưa cập nhật | Search projection bị thiếu/cũ |
| ES timeout, DB commit hoặc rollback | Có thể commit/rollback | Kết quả không rõ ở client | Cần đối soát hoặc retry idempotent |

Tình huống timeout đặc biệt khó: client không nhận response không có nghĩa server chưa thực hiện thao tác. Elasticsearch có thể đã index document rồi connection bị ngắt trước khi response đến.

Vì vậy, không nên coi exception từ Elasticsearch client là bằng chứng chắc chắn rằng document chưa được ghi.

## 6. Bulk API không phải transaction

Bulk API gom nhiều thao tác index, create, update hoặc delete trong một request. Nó giúp giảm overhead và tăng throughput, nhưng không cung cấp transaction atomic cho toàn bộ items.

Một bulk response có thể chứa item thành công và item thất bại:

    {
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-1",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-2",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        }
      ]
    }

Trong ví dụ, p-1 có thể đã được index thành công dù p-2 thất bại. Ứng dụng không thể yêu cầu bulk request rollback p-1 chỉ vì p-2 không hợp lệ.

Nếu một item trong bulk lỗi, phải kiểm tra response từng item và quyết định retry, sửa dữ liệu hoặc đưa vào DLQ. Không giả định bulk có hành vi giống một transaction SQL gồm nhiều câu lệnh.

## 7. Refresh không phải rollback hoặc commit transaction

Elasticsearch là near-real-time search engine. Một document đã được ghi có thể chưa xuất hiện trong search cho đến khi shard refresh.

Phân biệt:

- Write acknowledgement: Elasticsearch đã xử lý thao tác và trả response theo semantics request.
- Durability: cơ chế translog, replication và flush bảo vệ dữ liệu.
- Search visibility: document đã được refresh để search có thể nhìn thấy hay chưa.
- Database transaction: giao dịch do database transaction manager quản lý.

Refresh không commit hoặc rollback database. Gọi refresh cũng không làm cho một document được ghi trước đó trở thành một phần của transaction SQL.

Khi test, nếu search chưa thấy document ngay sau save, nguyên nhân có thể là refresh chưa diễn ra. Điều đó khác với việc database rollback hoặc Elasticsearch write thất bại. Có thể dùng realtime GET theo ID để kiểm tra document đã tồn tại hay chưa, hoặc refresh tường minh trong test khi cần xác nhận search visibility.

## 8. @Transactional trong integration test có thể để lại document

Spring TestContext thường rollback transaction của test sau khi method kết thúc nếu test được đánh dấu @Transactional và không yêu cầu commit.

Ví dụ:

    @SpringBootTest
    @Transactional
    class ProductServiceIntegrationTest {

        @Autowired
        ProductService productService;

        @Autowired
        ProductRepository productRepository;

        @Test
        void createsProduct() {
            productService.create(productFixture());

            assertThat(productRepository.findAll())
                .hasSize(1);
        }
    }

Sau test, database transaction có thể bị rollback. Nhưng nếu productService.create đã gọi Elasticsearch, document có thể vẫn còn trong index.

Điều này xảy ra dù test framework báo transaction đã rollback thành công. Spring chỉ rollback tài nguyên mà transaction manager quản lý; nó không tự xóa document Elasticsearch.

### Test tiếp theo bị ảnh hưởng

Giả sử test thứ nhất ghi p-100 vào Elasticsearch rồi database rollback. Test thứ hai dùng cùng ID p-100 hoặc query rộng:

    SearchHits<Product> hits =
        operations.search(query, Product.class);

Test thứ hai có thể thấy dữ liệu từ test thứ nhất. Nếu test chạy song song, kết quả càng khó dự đoán.

## 9. @DataJpaTest cũng không dọn Elasticsearch

@DataJpaTest thường cấu hình JPA slice test và transaction rollback sau mỗi test. Nếu test import một service hoặc tự gọi Elasticsearch client để ghi document, Elasticsearch vẫn là hệ thống bên ngoài transaction JPA.

Không nên suy luận rằng vì database được rollback tự động nên mọi dữ liệu test liên quan cũng được rollback.

Nếu test dùng cả JPA và Elasticsearch:

- Xác định transaction manager nào đang quản lý test transaction.
- Xác định thao tác nào đi qua transaction đó.
- Ghi lại ID/index Elasticsearch được tạo.
- Dọn Elasticsearch độc lập sau test.
- Kiểm tra search visibility bằng refresh nếu assertion dùng search.

## 10. Vì sao @DirtiesContext không xóa dữ liệu Elasticsearch?

@DirtiesContext yêu cầu Spring TestContext loại bỏ hoặc tạo lại ApplicationContext theo phạm vi cấu hình. Nó không đồng nghĩa xóa dữ liệu trong Elasticsearch cluster.

Elasticsearch thường chạy ở process/container/service riêng. Xóa Spring context không xóa index hoặc document trên cluster.

Tương tự:

- Restart Spring Boot không tự xóa index.
- Tạo lại repository bean không xóa document.
- Rollback transaction database không xóa document.
- Xóa entity trong database không tự xóa projection nếu không có cơ chế đồng bộ.

Muốn dọn dữ liệu, test phải gọi API delete hoặc xóa index test riêng.

## 11. Dọn document Elasticsearch trong test

Một cách đơn giản là lưu lại ID được tạo và xóa chúng sau test:

    @AfterEach
    void cleanElasticsearch() {
        for (String id : createdProductIds) {
            operations.delete(id, Product.class);
        }

        operations.indexOps(Product.class).refresh();
        createdProductIds.clear();
    }

Ví dụ dùng API imperative thường gặp. Chữ ký delete và refresh phụ thuộc Spring Data Elasticsearch version. Có thể dùng Elasticsearch Java API Client nếu cần kiểm soát trực tiếp.

Ưu điểm:

- Chỉ xóa dữ liệu thuộc test hiện tại.
- Không ảnh hưởng document của test khác.
- Có thể dùng chung index test nếu ID được namespace.

Nhược điểm:

- Phải ghi nhận mọi ID đã tạo.
- Nếu test chết trước cleanup, document có thể còn lại.
- Nếu thao tác ghi timeout, ID vẫn cần được cleanup vì server có thể đã xử lý.

Cleanup nên nằm trong finally hoặc lifecycle hook phù hợp để được gọi ngay cả khi assertion hoặc thao tác test thất bại.

## 12. Dùng ID riêng cho từng test

Không dùng ID cố định trong test chạy trên cùng một index dùng chung, trừ khi có lý do rõ ràng và cleanup chắc chắn.

Ví dụ:

    String testRunId = UUID.randomUUID().toString();
    String productId = "test-" + testRunId;

    Product product = new Product();
    product.setId(productId);
    product.setName("Test Keyboard");

    operations.save(product);
    createdProductIds.add(productId);

ID riêng giúp:

- Tránh ghi đè dữ liệu của test khác.
- Giảm xung đột khi chạy parallel.
- Dễ xác định document thuộc test run nào.
- Cleanup chính xác.

Nếu hệ thống dùng tenantId, có thể gắn testRunId vào một field metadata hoặc tenant test riêng để query cleanup.

Không dùng một ID cố định như test-product cho mọi test trong một index dùng chung. Test có thể ghi đè hoặc xóa dữ liệu do test khác tạo.

## 13. Dùng index riêng cho test hoặc test suite

Một lựa chọn mạnh hơn là tạo index có tên duy nhất cho mỗi test run:

    String indexName =
        "products-test-" + UUID.randomUUID().toString().replace("-", "");

    IndexOperations indexOps =
        operations.indexOps(IndexCoordinates.of(indexName));

    indexOps.create();
    indexOps.putMapping();

Sau test:

    indexOps.delete();

Ví dụ trên chỉ minh họa cách cô lập index; mapping và API create phụ thuộc cấu hình Spring Data. Nếu dùng entity annotations, có thể tạo index từ entity metadata hoặc khai báo mapping riêng.

Ưu điểm:

- Cleanup toàn bộ dữ liệu test bằng cách xóa index.
- Tránh ảnh hưởng dữ liệu từ test khác.
- Có thể kiểm thử mapping/index settings độc lập.

Nhược điểm:

- Tạo/xóa index có overhead.
- Có thể làm test suite chậm nếu mỗi test tạo index.
- Cần quản lý alias và index name động.
- Không phải mọi repository đều dễ cấu hình index động.

Có thể dùng một index cho một test class hoặc một test run thay vì mỗi method, miễn là dữ liệu được namespace và cleanup rõ ràng.

## 14. Không xóa toàn bộ index dùng chung sau mỗi test

Một cách cleanup nguy hiểm:

    operations.indexOps(Product.class).delete();

Nếu nhiều test hoặc developer cùng dùng index products, lệnh này xóa dữ liệu của tất cả.

Chỉ xóa index khi test sở hữu index đó và không có consumer khác dùng chung. Với index dùng chung, xóa theo ID hoặc testRunId filter.

Nếu dùng delete-by-query, query phải giới hạn đúng namespace test:

    POST products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-123"
        }
      }
    }

Không chạy match_all delete trên index dùng chung. Một lỗi filter có thể xóa dữ liệu không thuộc test.

## 15. Cleanup phải tính đến write timeout

Nếu Elasticsearch client timeout, test có thể không biết request đã ghi document hay chưa. Nếu chỉ thêm ID vào cleanup list sau khi save trả về thành công, một document được ghi nhưng response timeout có thể bị bỏ sót.

Có thể ghi nhận ID trước khi gửi:

    String id = "test-" + UUID.randomUUID();
    createdProductIds.add(id);

    Product product = new Product(id, "Test Product");
    operations.save(product);

Nếu request thất bại trước khi đến server, cleanup delete ID không tồn tại thường vẫn có thể xử lý an toàn theo API. Nếu request đã được xử lý nhưng response mất, cleanup vẫn biết ID để xóa.

Với bulk, hãy ghi nhận toàn bộ ID dự kiến trước khi gửi batch. Sau khi nhận response, có thể bổ sung trạng thái item, nhưng cleanup không nên chỉ dựa vào danh sách item thành công mà client nhận được.

## 16. Dùng testRunId để cleanup theo nhóm

Với test suite lớn, lưu testRunId trong document test:

    {
      "id": "p-100",
      "name": "Test Product",
      "testRunId": "run-abc123"
    }

Cleanup:

    DELETE products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-abc123"
        }
      }
    }

Sau delete-by-query, nếu assertion tiếp theo dựa trên search, cần refresh theo chính sách phù hợp để thay đổi delete có thể nhìn thấy.

Field testRunId nên được mapping là keyword. Không dùng text analyzer cho field định danh dùng term query.

Nếu testRunId không được phép tồn tại trong production schema, dùng index test riêng hoặc một field metadata chỉ có trong mapping test. Đừng thêm field test vào document production chỉ để thuận tiện cleanup.

## 17. Test transaction rollback một cách tường minh

Nếu mục tiêu test là chứng minh database rollback không dọn Elasticsearch, hãy viết test nêu rõ cả hai trạng thái.

Ví dụ khái quát:

    @SpringBootTest
    class DualWriteRollbackTest {

        @Autowired
        ProductService service;

        @Autowired
        ProductRepository databaseRepository;

        @Autowired
        ElasticsearchOperations operations;

        @Test
        void databaseRollbackDoesNotUndoElasticsearchWrite() {
            String id = "rollback-" + UUID.randomUUID();

            assertThatThrownBy(() ->
                service.createThenFail(productWithId(id))
            ).isInstanceOf(IllegalStateException.class);

            assertThat(databaseRepository.findById(id))
                .isEmpty();

            Product indexed = operations.get(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );

            assertThat(indexed).isNotNull();
        }
    }

Đây là ví dụ minh họa transaction boundary. Cần bảo đảm method service thực sự đi qua Spring transaction proxy và test không tự mở một transaction bao quanh toàn bộ method theo cách làm thay đổi tình huống đang kiểm tra.

Test cũng phải cleanup document trong finally/afterEach. Nếu assertion dừng trước cleanup, dữ liệu test vẫn có thể còn lại.

## 18. Test @Transactional mặc định rollback và dữ liệu Elasticsearch

Một test method có @Transactional thường chạy trong transaction do Spring TestContext mở và rollback sau khi test kết thúc.

Ví dụ:

    @SpringBootTest
    @Transactional
    class ProductIntegrationTest {

        @Test
        void saveProduct() {
            databaseRepository.save(entity);
            operations.save(product);
        }
    }

Sau khi method kết thúc:

- Database có thể rollback.
- Elasticsearch document vẫn có thể tồn tại.

Nếu test cần kiểm tra behavior sau commit, transaction mặc định rollback không phù hợp. Dùng @Commit, @Rollback(false) hoặc TestTransaction để điều khiển commit rõ ràng; đồng thời dọn dữ liệu ngoài database.

Đừng thay @Rollback(false) một cách tùy tiện trong test suite. Commit dữ liệu database thật có thể làm test phụ thuộc nhau và để lại trạng thái lâu dài.

## 19. Kiểm thử AFTER_COMMIT listener

Spring cung cấp @TransactionalEventListener để xử lý event theo phase của transaction:

    @Component
    public class ProductIndexListener {

        private final ElasticsearchOperations operations;

        public ProductIndexListener(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
        )
        public void onProductChanged(ProductChanged event) {
            operations.save(event.product());
        }
    }

Listener chỉ được xử lý sau khi transaction database commit thành công theo cấu hình mặc định của transactional event listener. Nếu transaction rollback, listener phase AFTER_COMMIT không được gọi.

Điều này tránh ghi Elasticsearch trước khi database commit trong luồng dùng event listener. Tuy nhiên, nó chưa bảo đảm event delivery bền vững.

Nếu process dừng sau khi database commit nhưng trước khi listener thực hiện hoặc trước khi Elasticsearch ghi xong, event trong bộ nhớ có thể bị mất. @TransactionalEventListener không thay thế outbox.

Nếu listener chạy bất đồng bộ bằng @Async, cần xử lý thêm exception, retry, shutdown và observability. Caller đã commit database không thể nhận một rollback database chỉ vì tác vụ async ghi Elasticsearch thất bại.

## 20. Test listener AFTER_COMMIT cần commit thật

Một test có @Transactional mặc định rollback có thể không kích hoạt listener AFTER_COMMIT:

    @SpringBootTest
    @Transactional
    class ProductIndexListenerTest {

        @Test
        void publishesIndexAfterCommit() {
            applicationEventPublisher.publishEvent(event);
        }
    }

Nếu transaction test bị rollback ở cuối method, phase AFTER_COMMIT không xảy ra. Test có thể kết thúc mà listener chưa chạy, dù test không báo lỗi.

Để kiểm tra after-commit behavior:

- Dùng @Commit cho test method phù hợp.
- Hoặc dùng TestTransaction.flagForCommit() rồi TestTransaction.end().
- Đảm bảo listener hoàn tất trước assertion nếu listener bất đồng bộ.
- Cleanup database và Elasticsearch sau test.

Với listener async, dùng Awaitility hoặc một cơ chế chờ có timeout rõ ràng để đợi điều kiện cuối. Tránh Thread.sleep cố định vì thời gian thực thi có thể thay đổi theo tải.

## 21. AFTER_COMMIT vẫn có cửa sổ mất event

Timeline:

    Database transaction
       |
       +--> UPDATE product
       |
       +--> COMMIT thành công
                 |
                 v
           AFTER_COMMIT listener
                 |
                 +--> process crash trước publish
                 |
                 +--> Elasticsearch request thất bại

Database đã commit, nhưng Elasticsearch chưa được cập nhật. Nếu event chỉ tồn tại trong bộ nhớ, hệ thống có thể không còn cách biết cần retry.

AFTER_COMMIT phù hợp với side effect không cần delivery bền vững hoặc khi có một cơ chế recovery khác. Với đồng bộ quan trọng, nên dùng outbox hoặc CDC.

## 22. Outbox pattern

Outbox pattern ghi thay đổi nghiệp vụ và event cần phát vào cùng một database transaction.

Ví dụ:

    @Transactional
    public void updateProduct(ProductCommand command) {
        ProductEntity product =
            productRepository.findById(command.id())
                .orElseThrow();

        product.changePrice(command.price());
        productRepository.save(product);

        outboxRepository.save(
            OutboxEvent.productChanged(product)
        );
    }

Hai thao tác database cùng tham gia một transaction:

    BEGIN
      UPDATE product
      INSERT outbox_event
    COMMIT

Nếu transaction rollback, cả product update và outbox row rollback. Nếu commit, publisher có thể đọc outbox và gửi event sau đó.

Publisher có thể chạy định kỳ hoặc dùng CDC để phát event. Khi publish thành công, record outbox được đánh dấu sent hoặc được quản lý bằng offset tương ứng.

Outbox giảm nguy cơ database đã commit nhưng event bị mất. Nó không tạo transaction atomic giữa database và Elasticsearch; consumer vẫn phải retry và idempotent.

## 23. Consumer outbox phải chịu duplicate

Publisher có thể gửi event đến broker thành công rồi process chết trước khi đánh dấu outbox row đã gửi. Khi chạy lại, publisher có thể gửi event lần nữa.

Vì vậy, consumer nên:

- Nhận eventId ổn định.
- Dùng document ID xác định.
- Kiểm tra source version.
- Ghi projection theo trạng thái mong muốn.
- Có thể xử lý cùng event nhiều lần mà không tạo side effect sai.

Ví dụ event:

    {
      "eventId": "evt-123",
      "aggregateId": "p-100",
      "aggregateVersion": 42,
      "eventType": "ProductUpdated",
      "payload": {
        "name": "Keyboard K8",
        "price": 120
      }
    }

Nếu document Elasticsearch đã ở version 42, consumer có thể bỏ qua duplicate event. Nếu index ở version 40, consumer có thể cập nhật lên version 42.

## 24. Saga và compensation

Khi không thể dùng một transaction atomic xuyên nhiều hệ thống, một quy trình có thể dùng saga: mỗi bước là một thao tác độc lập và có hành động bù trừ nếu quy trình thất bại.

Ví dụ:

1. Ghi product vào database.
2. Ghi document vào Elasticsearch.
3. Gửi event đến hệ thống khác.

Nếu bước 3 thất bại, quy trình có thể retry hoặc chạy compensation tùy nghiệp vụ.

Compensation không phải rollback nguyên tử. Nó là một thao tác mới nhằm đưa hệ thống về trạng thái chấp nhận được.

Nếu cần xóa document Elasticsearch sau khi database transaction thất bại, có thể gọi delete như một compensation. Nhưng delete cũng có thể timeout, fail hoặc chạy sai thứ tự với một event mới hơn.

Do đó, compensation cần:

- Có ID và version để xác định đúng document.
- Idempotent hoặc có thể retry.
- Không xóa nhầm trạng thái mới hơn.
- Ghi nhận trạng thái compensation.
- Có reconciliation nếu compensation không hoàn tất.

## 25. Không dùng delete như rollback tuyệt đối

Giả sử Elasticsearch đã index version 10. Sau đó database rollback và ứng dụng gửi delete theo ID. Trong lúc đó, một request khác có thể đã ghi version 11 hợp lệ.

Nếu delete không có điều kiện version, compensation có thể xóa document version 11.

Vì vậy, compensation cần biết document nào thuộc thao tác đang bù trừ. Có thể dùng external version, sequence number/primary term hoặc một marker operation tùy API và thiết kế.

Không xóa theo ID một cách mù quáng nếu cùng ID có thể được cập nhật bởi request khác.

## 26. Optimistic concurrency không phải transaction phân tán

Elasticsearch hỗ trợ optimistic concurrency control qua version hoặc cặp if_seq_no/if_primary_term ở những API phù hợp.

Các cơ chế này giúp phát hiện document đã thay đổi giữa lúc đọc và ghi. Chúng không tạo transaction chung với database.

Ví dụ:

- Database transaction rollback không làm sequence number Elasticsearch quay lại.
- Elasticsearch version tăng không được database transaction tự rollback.
- Conflict khi update document cần được xử lý riêng.

Dùng concurrency control để ngăn ghi đè dữ liệu mới bằng dữ liệu cũ, không dùng nó như bằng chứng rằng hai hệ thống đã commit/rollback cùng nhau.

## 27. Transaction manager và nhiều data store

Một ứng dụng có thể có nhiều transaction manager, ví dụ một cho JPA và một cho reactive database hoặc resource khác. @Transactional có thể chọn transaction manager bằng qualifier phù hợp.

Tuy nhiên, chọn một transaction manager không tự phối hợp các transaction còn lại thành atomic commit.

Ngay cả khi dùng cơ chế phối hợp nhiều transaction manager, cần kiểm tra chính xác resource nào hỗ trợ enlistment, prepare/commit/rollback và failure recovery. Elasticsearch REST operations thông thường không tham gia XA/JTA transaction với relational database.

Không giả định rằng:

    @Transactional("transactionManager")

hoặc việc khai báo thêm transaction manager sẽ làm Elasticsearch write rollback cùng JPA.

Hãy xem transaction boundary của từng resource và thiết kế eventual consistency/compensation cho phần không thể enlist.

## 28. Rollback rules của @Transactional

Spring mặc định thường rollback transaction khi method ném RuntimeException hoặc Error. Checked exception mặc định không nhất thiết kích hoạt rollback, trừ khi cấu hình rollbackFor tương ứng.

Ví dụ:

    @Transactional(rollbackFor = IOException.class)
    public void process() throws IOException {
        databaseRepository.save(entity);
        elasticsearchOperations.save(document);
        throw new IOException("failed");
    }

rollbackFor có thể làm database transaction rollback khi IOException xảy ra. Nó vẫn không xóa document đã ghi vào Elasticsearch.

Rollback rules chỉ quyết định transaction manager xử lý transaction mà nó quản lý như thế nào. Chúng không thêm khả năng rollback cho side effect bên ngoài.

## 29. Tự gọi method có @Transactional

Spring transaction thường được áp dụng qua proxy. Nếu một method trong cùng bean gọi trực tiếp method khác có @Transactional, lời gọi nội bộ có thể không đi qua proxy và transaction annotation bên trong không được áp dụng như mong đợi.

Điều này có thể khiến test hoặc service hiểu sai transaction boundary. Tuy nhiên, kể cả khi @Transactional được áp dụng đúng, Elasticsearch HTTP write vẫn không tự rollback cùng database.

Khi kiểm thử transaction:

- Gọi service qua Spring bean/proxy.
- Tránh self-invocation nếu đang dựa vào propagation.
- Kiểm tra transaction thực sự active khi cần.
- Xác định transaction manager được chọn.
- Không suy ra Elasticsearch tham gia transaction từ việc database rollback thành công.

## 30. Test dữ liệu tồn tại sau rollback

Một integration test có thể mô tả rõ failure mode:

    @Service
    public class ProductService {

        private final ProductRepository databaseRepository;
        private final ElasticsearchOperations operations;

        @Transactional
        public void saveThenFail(ProductEntity entity) {
            databaseRepository.save(entity);

            Product document = Product.from(entity);
            operations.save(document);

            throw new IllegalStateException("force rollback");
        }
    }

Test:

    @Test
    void rollbackOnlyAffectsDatabase() {
        String id = "rollback-" + UUID.randomUUID();

        assertThatThrownBy(() ->
            service.saveThenFail(productEntity(id))
        ).isInstanceOf(IllegalStateException.class);

        assertThat(databaseRepository.findById(id)).isEmpty();

        Product document = operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );

        assertThat(document).isNotNull();
    }

Đây là ví dụ minh họa. Cần bảo đảm method service thực sự đi qua Spring transaction proxy và test không tự mở một transaction bao quanh toàn bộ method theo cách làm thay đổi tình huống đang kiểm tra.

Test cũng phải cleanup document trong finally/afterEach. Nếu assertion dừng trước cleanup, dữ liệu test vẫn có thể còn lại.

## 31. Test không nên phụ thuộc vào thứ tự chạy

Một test chỉ pass khi chạy riêng nhưng fail khi chạy cả suite thường có thể đang dùng chung dữ liệu hoặc index state.

Nguyên nhân:

- Document từ test trước còn lại.
- Test dùng ID cố định và ghi đè nhau.
- Cleanup chỉ chạy khi assertion thành công.
- Test chạy song song cùng index.
- Test dùng tenant hoặc filter quá rộng.
- Async indexing chạy sau khi test đã cleanup.

Giải pháp:

- Dùng ID duy nhất theo test run.
- Dùng index riêng hoặc namespace test.
- Ghi nhận ID trước khi gửi write.
- Cleanup trong finally/afterEach.
- Chờ async worker hoàn tất hoặc hủy worker.
- Không phụ thuộc thứ tự test.

## 32. Cleanup trong finally

Nếu test tạo document trực tiếp, có thể dùng try/finally:

    String id = "test-" + UUID.randomUUID();

    try {
        operations.save(productWithId(id));

        Product found = operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );

        assertThat(found).isNotNull();
    } finally {
        operations.delete(
            id,
            Product.class,
            IndexCoordinates.of("products")
        );
    }

Chữ ký delete/get tùy phiên bản Spring Data. Nếu method cleanup có thể ném exception, hãy ghi nhận lỗi cleanup mà không làm mất nguyên nhân test ban đầu. Có thể dùng test extension hoặc fixture quản lý tài nguyên để tập trung logic cleanup.

Với bulk, lưu toàn bộ ID trước khi gửi và xóa tất cả trong cleanup. Nếu request timeout, vẫn cleanup theo ID đã dự kiến.

## 33. Cleanup bằng @AfterEach

Với test class có nhiều method, có thể lưu danh sách ID được tạo:

    private final Set<String> createdIds =
        ConcurrentHashMap.newKeySet();

    @AfterEach
    void cleanup() {
        for (String id : createdIds) {
            operations.delete(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );
        }

        operations.indexOps(Product.class).refresh();
        createdIds.clear();
    }

ConcurrentHashMap.newKeySet chỉ cần nếu test có thể tạo ID từ nhiều thread. Nếu test hoàn toàn tuần tự, một collection đơn giản có thể đủ.

Nếu test async, đợi worker hoàn tất hoặc hủy worker trước cleanup. Nếu worker tiếp tục ghi sau khi cleanup, document có thể xuất hiện lại.

## 34. Cleanup theo index test riêng

Một test suite có thể tạo index riêng cho class:

    @BeforeAll
    static void createIndex() {
        // Tạo index có tên riêng cho test suite.
    }

    @AfterAll
    static void deleteIndex() {
        // Xóa đúng index do test suite sở hữu.
    }

Đây là cách tốt khi cần kiểm thử mapping, analyzer hoặc settings. Nó cũng tránh dữ liệu của test khác.

Nếu index name được tạo động, cấu hình template/repository cần trỏ đến index đó. Không để repository production hoặc test khác vô tình dùng index test đang bị xóa.

## 35. Cleanup bằng testRunId

Với test suite lớn, lưu testRunId trong document test:

    {
      "id": "p-100",
      "name": "Test Product",
      "testRunId": "run-abc123"
    }

Cleanup:

    DELETE products/_delete_by_query
    {
      "query": {
        "term": {
          "testRunId": "run-abc123"
        }
      }
    }

Sau delete-by-query, nếu assertion tiếp theo dựa trên search, cần refresh theo chính sách phù hợp để thay đổi delete có thể nhìn thấy.

Field testRunId nên được mapping là keyword. Không dùng text analyzer cho field định danh dùng term query.

Nếu testRunId không được phép tồn tại trong production schema, dùng index test riêng hoặc một field metadata chỉ có trong mapping test. Đừng thêm field test vào document production chỉ để thuận tiện cleanup.

## 36. Không xóa toàn bộ index dùng chung

Một cách cleanup nguy hiểm:

    operations.indexOps(Product.class).delete();

Nếu nhiều test hoặc developer cùng dùng index products, lệnh này xóa dữ liệu của tất cả.

Chỉ xóa index khi test sở hữu index đó và không có consumer khác dùng chung. Với index dùng chung, xóa theo ID hoặc testRunId filter.

Không chạy match_all delete trên index dùng chung. Một lỗi filter có thể xóa dữ liệu không thuộc test.

## 37. Cleanup phải tính đến write timeout

Nếu Elasticsearch client timeout, test có thể không biết request đã ghi document hay chưa. Nếu chỉ thêm ID vào cleanup list sau khi save trả về thành công, một document được ghi nhưng response timeout có thể bị bỏ sót.

Có thể ghi nhận ID trước khi gửi:

    String id = "test-" + UUID.randomUUID();
    createdProductIds.add(id);

    Product product = new Product(id, "Test Product");
    operations.save(product);

Nếu request thất bại trước khi đến server, cleanup delete ID không tồn tại thường vẫn có thể xử lý an toàn theo API. Nếu request đã được xử lý nhưng response mất, cleanup vẫn biết ID để xóa.

Với bulk, hãy ghi nhận toàn bộ ID dự kiến trước khi gửi batch. Cleanup không nên chỉ dựa vào danh sách item thành công mà client nhận được.

## 38. Refresh trong cleanup và assertion

Sau khi index document, realtime GET theo ID có thể thấy document ngay, nhưng search có thể cần refresh. Sau khi delete, search cũng có thể tiếp tục thấy document cho đến refresh tiếp theo.

Trong test:

- Nếu assertion dùng GET theo ID, không cần dựa vào search refresh theo cùng cách.
- Nếu assertion dùng search, refresh index sau setup hoặc dùng refresh policy phù hợp.
- Nếu cleanup dùng delete-by-query và test kế tiếp search, refresh sau cleanup khi cần.

Không dùng Thread.sleep một khoảng cố định để chờ refresh. Gọi refresh tường minh trong test làm điều kiện rõ ràng và ít flaky hơn.

Refresh chỉ điều khiển search visibility; nó không rollback document hay transaction.

## 39. Async event listener và cleanup race

Giả sử test phát event và listener @Async ghi Elasticsearch. Test có thể kết thúc, cleanup xóa document, rồi async worker mới chạy và ghi document lại.

Timeline:

    Test publish event
       |
       v
    Async task được xếp hàng
       |
       v
    Test kết thúc và cleanup
       |
       v
    Async task chạy sau cleanup
       |
       v
    Document xuất hiện trở lại

Để tránh:

- Đợi task hoàn tất trước cleanup.
- Dùng executor test đồng bộ nếu phù hợp.
- Dùng test event listener hoặc latch để xác nhận completion.
- Tắt/kiểm soát consumer trong test không liên quan.
- Dùng index/ID riêng để late write không ảnh hưởng test khác.

Không giả định @AfterEach luôn đồng nghĩa mọi tác vụ async đã kết thúc.

## 40. Test outbox và eventual consistency

Nếu ứng dụng dùng outbox, nên có các test riêng:

1. Khi transaction database commit, business row và outbox row cùng tồn tại.
2. Khi transaction rollback, cả hai đều không tồn tại.
3. Publisher đọc outbox và phát event.
4. Consumer index document thành công.
5. Khi Elasticsearch lỗi, event được retry hoặc giữ trạng thái pending.
6. Khi consumer nhận duplicate, projection không bị sai.
7. Khi event cũ đến sau event mới, version check ngăn dữ liệu lùi.

Không nên kiểm tra toàn bộ flow chỉ bằng một test @Transactional rollback. Tách transaction persistence, publisher, consumer và Elasticsearch integration để biết failure xảy ra ở đâu.

Với eventual consistency, assertion nên chờ một điều kiện có timeout:

    await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            Product indexed = operations.get(
                id,
                Product.class,
                IndexCoordinates.of("products")
            );
            assertThat(indexed).isNotNull();
        });

Đây là ví dụ với Awaitility. Chọn timeout dựa trên test environment và đồng thời có cơ chế refresh nếu assertion dùng search.

## 41. Kiểm thử khi Elasticsearch thất bại

Để kiểm tra recovery, cần mô phỏng các tình huống:

- Elasticsearch không thể kết nối.
- Request timeout.
- HTTP 429 hoặc rejected execution.
- Index không tồn tại.
- Mapping parse error.
- Bulk response partial failure.
- Consumer chết sau khi ghi nhưng trước khi acknowledge.
- Response bị mất dù server đã xử lý write.

Có thể dùng mock client cho unit test phân loại lỗi và Testcontainers/Elasticsearch test instance cho integration test. Một số lỗi như timeout sau khi server đã xử lý cần fault injection hoặc proxy test chuyên biệt.

Test phải xác nhận:

- Database transaction có commit/rollback theo yêu cầu.
- Event/outbox còn khả năng retry.
- DLQ nhận đúng item permanent.
- Retry không tạo duplicate side effect.
- Reconciliation phát hiện document thiếu hoặc thừa.

## 42. Không dùng mock để chứng minh rollback Elasticsearch

Mock ElasticsearchOperations có thể xác nhận service đã gọi save hoặc delete. Nó không chứng minh trạng thái thực tế của Elasticsearch sau rollback.

Muốn xác nhận transaction boundary, cần ít nhất một integration test có Elasticsearch thật hoặc một test environment tương đương:

- Gửi write thực tế.
- Kích hoạt database rollback.
- Đọc lại document từ Elasticsearch.
- Xác nhận document còn hoặc đã được compensation xóa theo thiết kế.
- Cleanup dữ liệu sau test.

Mock hữu ích cho unit test logic orchestration, nhưng không thể chứng minh server-side persistence.

## 43. Testcontainers và môi trường Elasticsearch riêng

Testcontainers có thể khởi chạy Elasticsearch cho integration test và tạo môi trường cô lập hơn so với cluster dùng chung.

Một cách tổ chức:

- Khởi tạo container ở phạm vi test suite.
- Tạo index test riêng cho mỗi class hoặc test run.
- Dùng mapping/settings gần production.
- Ghi lại document ID.
- Cleanup index/document khi kết thúc.
- Đóng container sau khi toàn suite hoàn tất.

Không nên khởi tạo một container mới cho mỗi method nếu chi phí khởi động quá lớn. Cô lập bằng index hoặc namespace thường hiệu quả hơn.

Testcontainers không tự làm Elasticsearch tham gia transaction database. Nó chỉ giúp quản lý lifecycle của môi trường test.

## 44. Database rollback và test data setup

Nếu dữ liệu fixture trong database được tạo trong transaction test và rollback cuối method, một async consumer chạy sau test có thể không đọc được source row.

Ví dụ:

1. Test insert product trong transaction.
2. Test publish event.
3. Consumer async xử lý sau khi test transaction rollback.
4. Consumer đọc database và không thấy product.

Điều này có thể làm test flaky hoặc tạo DLQ record không mong muốn.

Khi test event-driven flow:

- Commit fixture trước khi consumer xử lý nếu consumer cần đọc source.
- Hoặc đưa payload đầy đủ vào event để consumer không phụ thuộc transaction chưa commit.
- Điều khiển consumer và transaction boundary tường minh.
- Dọn fixture database và Elasticsearch riêng.

Không để một test rollback fixture trong khi background worker vẫn đang xử lý nó.

## 45. Spring transaction propagation không sửa được dual-write

Các propagation mode như REQUIRED, REQUIRES_NEW, NESTED hoặc NOT_SUPPORTED điều khiển cách Spring tham gia hoặc tạo transaction cho resource được transaction manager quản lý.

Chúng không làm một request Elasticsearch HTTP trở thành participant của JDBC transaction.

Ví dụ REQUIRES_NEW có thể tạo một database transaction độc lập. Nếu trong method đó gọi Elasticsearch, thao tác Elasticsearch vẫn độc lập. Outer transaction rollback không xóa document đã ghi.

Không dùng propagation để cố tạo cảm giác atomic giữa database và Elasticsearch. Hãy xác định transaction manager và resource cụ thể mà mỗi thao tác sử dụng.

## 46. Transactional outbox so với AFTER_COMMIT event

| Tiêu chí | AFTER_COMMIT application event | Transactional outbox |
|---|---|---|
| Chỉ xử lý sau DB commit | Có | Có, qua publisher đọc outbox |
| Event được lưu bền vững cùng DB transaction | Không mặc định | Có |
| Process crash ngay sau commit | Có thể mất event | Outbox row vẫn còn |
| Duplicate delivery | Có thể tùy async/retry | Có thể, consumer phải idempotent |
| Cần publisher/replay | Tùy thiết kế | Có |
| Độ phức tạp | Thấp hơn | Cao hơn nhưng recovery rõ ràng |

AFTER_COMMIT phù hợp với side effect đơn giản hoặc khi có cơ chế recovery khác. Outbox phù hợp khi thay đổi nguồn phải được đồng bộ bền vững sang Elasticsearch hoặc broker.

## 47. Khi nào dùng saga/compensation?

Saga phù hợp khi một quy trình nghiệp vụ gồm nhiều bước độc lập và có thể cần hành động bù trừ.

Ví dụ:

    Reserve inventory
         |
         v
    Save order
         |
         v
    Index order search document
         |
         v
    Notify downstream

Nếu bước sau thất bại, không phải lúc nào cũng nên xóa dữ liệu trước đó. Có thể retry bước lỗi, đánh dấu trạng thái pending hoặc chạy compensation theo quy tắc nghiệp vụ.

Với Elasticsearch projection, cách thường phù hợp là giữ database làm source of truth và retry/rebuild projection. Xóa document Elasticsearch để giả lập rollback database có thể không cần thiết và có thể tạo thêm inconsistency.

Compensation phải là thao tác nghiệp vụ có trạng thái và retry, không phải một lệnh delete không kiểm soát.

## 48. Versioning giúp tránh ghi lùi projection

Giả sử event cũ version 5 được retry sau khi event version 7 đã index. Nếu consumer ghi theo ID mà không kiểm tra version, dữ liệu có thể bị ghi lùi.

Có thể lưu sourceVersion trong document:

    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120,
      "sourceVersion": 7
    }

Consumer kiểm tra:

    if (event.sourceVersion() <= indexed.sourceVersion()) {
        return; // duplicate hoặc event cũ
    }

Trong triển khai thực tế, nên dùng external versioning hoặc conditional update phù hợp với Elasticsearch API để tránh race giữa bước đọc version và ghi.

Versioning bảo vệ thứ tự update của document. Nó không tạo transaction chung với database.

## 49. Đối soát để tìm orphan document

Nếu database rollback nhưng Elasticsearch đã ghi, reconciliation có thể phát hiện document chỉ tồn tại trong index.

Một quy trình:

1. Lấy tập ID hoặc snapshot từ database.
2. Duyệt ID trong Elasticsearch theo PIT/search_after hoặc batch.
3. So sánh ID và source version.
4. Phân loại document không còn trong source.
5. Kiểm tra tombstone hoặc trạng thái nghiệp vụ.
6. Xóa hoặc đánh dấu document theo policy.

Không xóa ngay mọi document không tìm thấy trong một lần đọc database nếu snapshot không nhất quán hoặc dữ liệu đang được tạo. Dùng watermark, tombstone hoặc snapshot transaction để tránh xóa nhầm document mới.

Reconciliation là lớp recovery cho sai lệch còn sót, không thay thế event-driven sync.

## 50. Reconciliation và delete policy

Một orphan document có thể xuất hiện do rollback, lỗi đồng bộ, event duplicate hoặc chuyển index. Trước khi xóa, cần xác định:

- ID có còn tồn tại ở source không?
- Source đang ở trạng thái deleted hay transaction chưa commit?
- Document trong index có version mới hơn không?
- Alias có đang trỏ đến index cũ không?
- Có event đang chờ xử lý không?
- Document thuộc tenant/test run nào?

Với dữ liệu nghiệp vụ quan trọng, nên lưu tombstone hoặc event history để xác định chính xác delete. Không dùng một query delete-by-query rộng mà không có điều kiện version/namespace.

## 51. Test không nên dùng shared state không kiểm soát

Một test suite có thể dùng chung:

- Elasticsearch cluster.
- Index name.
- Database schema.
- Broker topic.
- Consumer group.
- Cache.

Nếu không namespace dữ liệu, test có thể đọc hoặc xóa trạng thái do suite khác tạo.

Đặt testRunId vào document/event và dùng index/topic riêng khi cần. Nếu test chạy song song, cleanup phải chỉ nhắm đến dữ liệu của test sở hữu.

Không xóa toàn bộ shared index hoặc topic để sửa một test flaky.

## 52. Quy trình test transaction và Elasticsearch

Một test plan rõ ràng có thể gồm:

1. Test database transaction rollback độc lập.
2. Test Elasticsearch save/get/delete độc lập.
3. Test service dual-write và failure sau ES write.
4. Xác nhận database rollback nhưng document ES vẫn còn.
5. Test AFTER_COMMIT listener chỉ chạy khi commit.
6. Test outbox row cùng commit/rollback với business row.
7. Test publisher và consumer xử lý duplicate.
8. Test partial bulk failure.
9. Test retry và DLQ.
10. Test cleanup sau timeout và exception.
11. Test parallel execution với ID/index riêng.
12. Test reconciliation phát hiện orphan/missing document.

Mỗi test nên xác định rõ transaction manager, transaction boundary, index target, refresh policy và cleanup strategy.

## Kết luận

Rollback giao dịch trong Spring không tự dọn document đã ghi vào Elasticsearch. @Transactional điều phối resource mà transaction manager quản lý; một lời gọi Spring Data Elasticsearch thông thường gửi request HTTP độc lập và không tham gia JDBC transaction. Vì vậy, database có thể rollback trong khi document vẫn còn, hoặc database đã commit trong khi search index chưa được cập nhật. Bulk API cũng không phải transaction atomic và có thể có partial failure.

Trong integration test, @Transactional và @DataJpaTest thường rollback database nhưng không xóa document Elasticsearch. Dùng ID riêng, index test riêng hoặc testRunId, ghi nhận ID trước khi gửi request và cleanup bằng delete/index lifecycle độc lập. Nếu kiểm tra listener AFTER_COMMIT, test phải commit thật; nếu cần delivery bền vững sau commit, dùng outbox hoặc CDC thay vì chỉ dựa vào application event trong bộ nhớ. Khi đồng bộ production, thiết kế idempotency, versioning, retry, DLQ, compensation và reconciliation để xử lý duplicate, timeout và sai lệch. Hãy kiểm tra riêng trạng thái của từng hệ thống sau mỗi failure; đừng coi một database rollback thành công là bằng chứng Elasticsearch đã được rollback.
