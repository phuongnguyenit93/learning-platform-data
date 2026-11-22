# AfterSaveCallback và metadata sau khi lưu

Trong Spring Data Elasticsearch, một thao tác save thường không chỉ là gửi document lên Elasticsearch. Ứng dụng có thể cần thực hiện thêm công việc sau khi thao tác ghi hoàn tất: ghi log, đo thời gian, cập nhật trạng thái xử lý, phát tín hiệu cho một thành phần khác hoặc đọc metadata mà tầng persistence đã nhận được. Spring Data cung cấp entity callback để đặt logic tại những thời điểm xác định trong vòng đời lưu entity.

AfterSaveCallback là callback được gọi sau khi entity đã được lưu thông qua luồng persistence có hỗ trợ callback. Nó nhận entity và IndexCoordinates, rồi trả về entity. Callback này hữu ích khi cần quan sát kết quả ở tầng ứng dụng sau thao tác save.

Điều cần hiểu rõ là AfterSaveCallback không phải một hook để thay đổi source đã được lưu. Khi callback chạy, thao tác ghi đã diễn ra. Nếu callback sửa một field thông thường của entity rồi trả entity đó về, thay đổi trong bộ nhớ không tự động được ghi lại vào Elasticsearch. Muốn chuẩn bị dữ liệu trước khi ghi, hãy dùng BeforeConvertCallback hoặc BeforeSaveCallback. Muốn tự động gán thời điểm tạo/cập nhật, hãy dùng auditing.

## 1. Entity callback trong Spring Data Elasticsearch

Entity callback là điểm mở rộng được Spring Data gọi trong một giai đoạn của vòng đời persistence. Thay vì để service tự gọi một hàm phụ trước hoặc sau mỗi thao tác, ứng dụng có thể đăng ký callback và để Spring Data gọi đúng thời điểm.

Trong Spring Data Elasticsearch, các callback thường gặp gồm:

| Callback | Thời điểm | Mục đích thường dùng |
|---|---|---|
| BeforeConvertCallback | Trước khi entity được chuyển thành Document | Chuẩn bị hoặc chuẩn hóa entity trước conversion |
| AfterConvertCallback | Sau khi Document được chuyển thành entity | Bổ sung xử lý sau khi đọc và convert |
| BeforeSaveCallback | Trước khi Document được gửi để lưu | Điều chỉnh entity hoặc Document trước khi ghi |
| AfterSaveCallback | Sau khi thao tác save hoàn tất | Quan sát entity sau save, ghi log hoặc thực hiện xử lý hậu lưu |

Tên và chữ ký chính xác cần đối chiếu với phiên bản Spring Data Elasticsearch đang dùng. Trong các phiên bản hiện đại, callback imperative thường dùng generic type của entity và nhận IndexCoordinates.

Callback giúp tách logic theo lifecycle khỏi service nghiệp vụ. Tuy nhiên, không nên chuyển mọi công việc phụ vào callback. Callback vẫn nằm trong đường thực thi của persistence và có thể ảnh hưởng đến thời gian cũng như kết quả mà caller nhận được.

## 2. AfterSaveCallback làm gì?

AfterSaveCallback biểu diễn một hành động sau khi entity được lưu. Dạng chữ ký thường dùng trong Spring Data Elasticsearch là:

    public interface AfterSaveCallback<T> extends EntityCallback<T> {
        T onAfterSave(T entity, IndexCoordinates index);
    }

Callback nhận:

- entity: entity vừa được lưu.
- index: IndexCoordinates đại diện cho index target được sử dụng trong thao tác.

Callback trả về entity. Spring Data dùng callback chain để truyền kết quả giữa các callback cùng loại và trả kết quả persistence theo API tương ứng.

Một implementation đơn giản:

    @Component
    public class ProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        private static final Logger log =
            LoggerFactory.getLogger(ProductAfterSaveCallback.class);

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            log.info(
                "Saved product id={} to index={}",
                entity.getId(),
                index.getIndexName()
            );

            return entity;
        }
    }

Callback này ghi nhận ID và index sau khi save. Nó không cần được gọi thủ công từ ProductService nếu Spring Data đã nhận diện callback trong application context và thao tác save đi qua template/repository có hỗ trợ entity callbacks.

## 3. Vòng đời lưu entity và vị trí của AfterSaveCallback

Một luồng save điển hình có thể được hình dung như sau:

    Service gọi repository.save(entity)
                  |
                  v
    Spring Data nhận entity
                  |
                  v
    BeforeConvertCallback
                  |
                  v
    Chuyển entity thành Document
                  |
                  v
    BeforeSaveCallback
                  |
                  v
    Gửi index/update request đến Elasticsearch
                  |
                  v
    Nhận response của thao tác ghi
                  |
                  v
    Cập nhật metadata persistence mà mapping hỗ trợ
                  |
                  v
    AfterSaveCallback
                  |
                  v
    Trả entity/kết quả cho caller

Đây là mô hình lifecycle khái quát. Thứ tự chi tiết giữa việc cập nhật ID, version hoặc metadata khác và callback có thể phụ thuộc phiên bản Spring Data, kiểu thao tác và API được sử dụng. Nếu logic callback phụ thuộc vào một metadata cụ thể, hãy xác nhận bằng integration test với phiên bản thực tế.

Điểm cốt lõi không thay đổi: AfterSaveCallback chạy sau giai đoạn lưu. Nó thích hợp để quan sát kết quả của thao tác save và thực hiện công việc hậu lưu nhẹ.

## 4. Đăng ký AfterSaveCallback

Trong ứng dụng Spring Boot, callback thường được khai báo thành bean để Spring Data có thể tìm thấy:

    @Component
    public class ProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            // Xử lý sau khi save thành công.
            return entity;
        }
    }

Nếu dùng cấu hình Java:

    @Configuration
    public class ElasticsearchCallbackConfiguration {

        @Bean
        ProductAfterSaveCallback productAfterSaveCallback() {
            return new ProductAfterSaveCallback();
        }
    }

Thông thường không cần tự gọi callback từ repository hoặc service. Spring Data quản lý việc thực thi callback thông qua entity callback infrastructure.

Nếu ứng dụng tự tạo ElasticsearchOperations hoặc template thay vì dùng cấu hình Spring Boot thông thường, cần xác nhận template đó được gắn EntityCallbacks phù hợp. Một bean callback tồn tại trong context không có nghĩa mọi template tự tạo đều chắc chắn sử dụng nó.

Không đăng ký cùng một callback nhiều lần trong cùng callback chain. Nếu cùng logic được đăng ký ở nhiều nơi, một lần save có thể tạo side effect lặp.

## 5. AfterSaveCallback với entity có ID

Một entity có thể có ID do ứng dụng cấp hoặc để Elasticsearch tạo khi index. Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
        private Double price;
    }

Nếu ứng dụng đã gán ID:

    Product product = new Product();
    product.setId("p-100");
    product.setName("Keyboard K8");

    Product saved = productRepository.save(product);

Callback có thể ghi nhận ID của entity sau save:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        log.info("Saved id={}", entity.getId());
        return entity;
    }

Nếu ID được Elasticsearch sinh ra, Spring Data có thể đưa ID trả về vào thuộc tính được đánh dấu @Id và trả entity đã có ID theo semantics của API save. Thời điểm chính xác mà ID được gán so với callback cần được xác nhận trên phiên bản đang dùng nếu callback phụ thuộc vào ID sinh tự động.

Không nên tự tạo ID mới trong AfterSaveCallback rồi kỳ vọng document đã được ghi dưới ID đó. Nếu cần ID do ứng dụng kiểm soát, hãy tạo ID trước khi save. Nếu cần dùng ID do Elasticsearch sinh, hãy dùng ID từ entity/kết quả save sau khi persistence hoàn tất.

## 6. Metadata sau khi lưu gồm những gì?

Metadata là thông tin mô tả thao tác persistence hoặc trạng thái lưu trữ, không nhất thiết là field nghiệp vụ trong source document.

Một số thông tin thường được quan tâm:

| Metadata | Ý nghĩa |
|---|---|
| ID | Định danh document trong index |
| Version | Version dùng cho optimistic locking/versioning nếu entity và API hỗ trợ |
| Sequence number | Số thứ tự thao tác ghi trên shard, có thể dùng trong concurrency control |
| Primary term | Epoch/term của primary shard, kết hợp sequence number trong optimistic concurrency |
| IndexCoordinates | Index target mà thao tác sử dụng ở tầng Spring Data |
| Result | Kết quả thao tác như created hoặc updated trong response cấp Elasticsearch |
| Shard information | Thông tin shard copy đã xử lý thao tác |
| Refresh information | Thông tin liên quan refresh nếu response/API cung cấp |

AfterSaveCallback chỉ nhận entity và IndexCoordinates trong chữ ký callback thông thường. Nó không trực tiếp nhận toàn bộ IndexResponse hoặc BulkResponse. Vì vậy, chỉ những metadata đã được Spring Data ánh xạ vào entity hoặc có sẵn từ tham số callback mới có thể được đọc trực tiếp ở đây.

Nếu cần các trường response cấp thấp như result, shard details, forced refresh hoặc sequence number/primary term mà callback không expose, cần dùng API persistence/client phù hợp hoặc một adapter riêng giữ lại response.

## 7. ID và metadata không đồng nghĩa với field trong _source

ID thường được lưu ở metadata document (_id), không phải một field source thông thường. Spring Data ánh xạ ID vào thuộc tính có @Id.

Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
    }

Document source có thể chỉ chứa name, trong khi ID được lưu ở metadata của Elasticsearch.

Điều này quan trọng khi viết callback:

- entity.getId() lấy ID được Spring Data ánh xạ.
- IndexCoordinates cho biết target index ở tầng Spring Data.
- Không nên giả định ID cũng xuất hiện trong JSON source.
- Không nên ghi metadata response vào source trừ khi đó là dữ liệu nghiệp vụ có chủ đích.

Nếu cần lưu một mã nghiệp vụ trong source để query hoặc aggregation, hãy khai báo field riêng như productCode. Không dùng @Id như một cách thay thế cho mọi field định danh nghiệp vụ.

## 8. @Version và optimistic locking

Spring Data Elasticsearch hỗ trợ version metadata thông qua @Version trong những phiên bản tương ứng. Version có thể được dùng để phát hiện một thao tác update dựa trên trạng thái cũ của document.

Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Version
        private Long version;

        private String name;
        private Double price;
    }

Khi entity được lưu, Spring Data/Elasticsearch có thể quản lý version theo cơ chế được cấu hình. Version mới có thể được phản ánh vào entity được trả về.

AfterSaveCallback có thể quan sát version nếu version đã được cập nhật vào entity trước khi callback được gọi:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        log.info(
            "Saved id={} version={}",
            entity.getId(),
            entity.getVersion()
        );

        return entity;
    }

Không tự tăng version trong AfterSaveCallback. Version là metadata do persistence engine quản lý. Thay đổi version thủ công có thể làm lệch trạng thái giữa entity trong bộ nhớ và Elasticsearch.

### Version không phải refresh

Versioning và refresh giải quyết hai vấn đề khác nhau:

- Versioning giúp kiểm soát xung đột khi nhiều writer cập nhật cùng document.
- Refresh quyết định khi nào thay đổi có thể được tìm thấy qua search.

Một document có version mới vẫn có thể chưa xuất hiện trong search nếu shard chưa refresh. Ngược lại, document đã searchable không có nghĩa update tiếp theo không thể gặp version conflict.

## 9. Sequence number và primary term

Elasticsearch dùng sequence number và primary term trong optimistic concurrency control. Khi một thao tác ghi thành công, shard có thể trả về các metadata này để client dùng cho thao tác tiếp theo với điều kiện concurrency.

Khái niệm:

- Sequence number xác định thứ tự thao tác trên shard.
- Primary term thay đổi khi primary shard được thay thế trong các tình huống failover/election.
- Cặp sequence number và primary term giúp Elasticsearch xác định thao tác update có dựa trên phiên bản shard state mà client mong đợi hay không.

Một low-level response có thể cung cấp seq_no và primary_term. Tuy nhiên, không nên mặc định AfterSaveCallback luôn có thể đọc trực tiếp hai giá trị này từ entity. Khả năng ánh xạ và annotation hỗ trợ phụ thuộc phiên bản Spring Data Elasticsearch.

Nếu ứng dụng cần sử dụng concurrency token:

1. Kiểm tra Spring Data version có hỗ trợ ánh xạ metadata tương ứng hay không.
2. Xác định thao tác save trả metadata nào.
3. Kiểm tra callback được gọi sau khi metadata được gán hay chưa.
4. Nếu cần response chi tiết, dùng Elasticsearch Java API Client trực tiếp hoặc một adapter trả cả entity và response metadata.
5. Không tự suy ra sequence number từ version hoặc ID.

Không nhầm @Version với seq_no/primary_term. Đây là các cơ chế metadata khác nhau, và semantics cụ thể cần theo API được sử dụng.

## 10. AfterSaveCallback không nhận IndexResponse

Một điểm quan trọng của callback là chữ ký thường chỉ có entity và IndexCoordinates:

    Product onAfterSave(Product entity, IndexCoordinates index)

Nó không có tham số IndexResponse. Vì vậy, callback không thể trực tiếp đọc mọi trường trong response Elasticsearch nếu Spring Data không đưa chúng vào entity.

Ví dụ, nếu cần biết thao tác được Elasticsearch báo là created hay updated, callback thông thường không có một response.result() để gọi.

Nếu use case cần chi tiết response:

- Dùng Elasticsearch Java API Client để gọi index API và nhận IndexResponse.
- Tạo service adapter trả về một kiểu kết quả riêng gồm entity, ID, version và response metadata cần thiết.
- Giữ response trong tầng persistence rồi phát sự kiện ứng dụng với dữ liệu đã chọn.

Không nên dùng reflection hoặc truy cập internal state của template để lấy response không được public API expose. Cách đó phụ thuộc implementation và dễ hỏng khi nâng cấp.

## 11. Ví dụ callback ghi log metadata sau save

Một callback có thể ghi log ID, index và version:

    @Component
    public class ProductSavedLogCallback
            implements AfterSaveCallback<Product> {

        private static final Logger log =
            LoggerFactory.getLogger(ProductSavedLogCallback.class);

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            log.info(
                "Product persisted: id={}, version={}, index={}",
                entity.getId(),
                entity.getVersion(),
                index.getIndexName()
            );

            return entity;
        }
    }

Callback này phù hợp với log kỹ thuật nhẹ. Không ghi toàn bộ entity nếu source chứa thông tin nhạy cảm hoặc payload lớn.

Nếu log cần dùng cho audit nghiệp vụ, cần phân biệt log kỹ thuật của thao tác Elasticsearch với audit trail có yêu cầu bền vững, truy vết actor và transaction. Một callback log đơn giản không tự tạo ra một hệ thống audit đáng tin cậy.

## 12. Ghi metric sau khi save

AfterSaveCallback có thể là nơi ghi metric cho các thao tác save:

    @Component
    public class ProductSaveMetricsCallback
            implements AfterSaveCallback<Product> {

        private final MeterRegistry meterRegistry;

        public ProductSaveMetricsCallback(
                MeterRegistry meterRegistry) {
            this.meterRegistry = meterRegistry;
        }

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            meterRegistry.counter(
                "search.document.saved",
                "entity",
                "product",
                "index",
                index.getIndexName()
            ).increment();

            return entity;
        }
    }

Metric có thể giúp quan sát số lần save theo loại entity hoặc index. Hãy tránh dùng ID document hoặc giá trị có cardinality cao làm metric tag, vì điều đó có thể tạo quá nhiều time series.

Nếu cần đo latency của toàn bộ thao tác persistence, callback AfterSave chỉ đánh dấu điểm kết thúc gần cuối lifecycle. Cần đo cả thời gian trước khi save bắt đầu ở service hoặc instrumentation của client để có duration đầy đủ.

## 13. Gửi sự kiện sau khi lưu

Một số ứng dụng muốn phát sự kiện khi document đã được lưu:

    public record ProductSavedEvent(
        String productId,
        String indexName
    ) {}

Callback:

    @Component
    public class ProductSavedEventCallback
            implements AfterSaveCallback<Product> {

        private final ApplicationEventPublisher publisher;

        public ProductSavedEventCallback(
                ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            publisher.publishEvent(
                new ProductSavedEvent(
                    entity.getId(),
                    index.getIndexName()
                )
            );

            return entity;
        }
    }

Sự kiện trong ví dụ là application event nội bộ. Việc publish event không tự bảo đảm consumer đã xử lý xong, và cũng không tạo transaction phân tán giữa Elasticsearch với message broker.

Nếu cần bảo đảm event không bị mất khi process dừng ngay sau write, hãy thiết kế outbox hoặc cơ chế delivery bền vững ở nguồn dữ liệu giao dịch. AfterSaveCallback không phải durable message queue.

## 14. Side effect lỗi sau khi document đã được ghi

Callback chạy sau thao tác save. Nếu callback thực hiện một side effect rồi ném exception, có thể xảy ra tình huống:

1. Elasticsearch đã lưu document thành công.
2. AfterSaveCallback bắt đầu.
3. Gọi hệ thống ngoài thất bại.
4. Exception truyền ngược về caller.
5. Caller nhận lỗi và có thể nghĩ toàn bộ save thất bại.

Đây là rủi ro quan trọng. Một lỗi callback không nhất thiết rollback được thao tác Elasticsearch đã hoàn tất.

Ví dụ:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        remoteAuditService.send(entity);
        return entity;
    }

Nếu remoteAuditService thất bại, caller có thể nhận exception dù document đã tồn tại. Nếu caller retry toàn bộ save, thao tác có thể chạy lần nữa và side effect có thể bị lặp.

Để giảm rủi ro:

- Giữ callback ngắn và ít lỗi.
- Không gọi hệ thống ngoài có latency cao nếu không thật sự cần.
- Thiết kế side effect idempotent.
- Ghi log lỗi rõ ràng.
- Nếu side effect không được phép mất, dùng outbox hoặc job/event delivery bền vững.
- Xác định rõ API caller có thể nhận exception sau khi write đã thành công hay không.

Không được giả định callback sau save có thể rollback Elasticsearch write giống transaction của relational database.

## 15. Không dùng AfterSaveCallback để sửa dữ liệu cần lưu

Giả sử muốn tạo slug sau khi lưu:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        entity.setSlug(toSlug(entity.getName()));
        return entity;
    }

Slug thay đổi trên object trong bộ nhớ, nhưng thao tác index đã hoàn tất trước callback. Không có một write thứ hai tự động để lưu slug.

Nếu slug phải nằm trong document, hãy tính trước khi chuyển đổi:

    @Component
    public class ProductBeforeConvertCallback
            implements BeforeConvertCallback<Product> {

        @Override
        public Product onBeforeConvert(
                Product entity,
                IndexCoordinates index) {

            entity.setSlug(toSlug(entity.getName()));
            return entity;
        }
    }

Hoặc dùng BeforeSaveCallback nếu cần điều chỉnh Document sau khi entity đã được convert.

Phân biệt:

- BeforeConvertCallback: thay đổi entity trước conversion.
- BeforeSaveCallback: thay đổi entity hoặc Document trước khi ghi, theo chữ ký phiên bản.
- AfterSaveCallback: xử lý sau khi write hoàn tất.

Nếu callback AfterSave trả về một entity đã thay đổi, caller có thể nhận object khác với source đang lưu. Điều đó dễ gây nhầm lẫn và nên tránh trừ khi có chủ đích rõ ràng.

## 16. AfterSaveCallback và Auditing

Spring Data Auditing dùng các annotation như:

- @CreatedDate
- @LastModifiedDate
- @CreatedBy
- @LastModifiedBy

Auditing thường được thực hiện trước khi entity được chuyển thành document để giá trị audit được ghi vào source cùng lần save.

Ví dụ:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @CreatedDate
        private Instant createdAt;

        @LastModifiedDate
        private Instant updatedAt;
    }

Kích hoạt auditing trong cấu hình:

    @Configuration
    @EnableElasticsearchAuditing
    public class ElasticsearchAuditingConfiguration {
    }

Nếu cần actor hiện tại cho CreatedBy hoặc LastModifiedBy, ứng dụng có thể cấu hình AuditorAware theo cơ chế Spring Data Auditing.

Auditing và AfterSaveCallback có vai trò khác nhau:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Gán createdAt trước khi lưu | Auditing / BeforeConvertCallback |
| Cập nhật updatedAt trước khi lưu | Auditing / BeforeConvertCallback |
| Gán người tạo hoặc người sửa | Auditing với AuditorAware |
| Ghi log sau thao tác save | AfterSaveCallback |
| Đếm số thao tác save | AfterSaveCallback |
| Phát event sau save | AfterSaveCallback, với chính sách delivery phù hợp |
| Thêm field vào source trước khi ghi | BeforeConvertCallback hoặc BeforeSaveCallback |

Không dùng AfterSaveCallback để gán @CreatedDate hoặc @LastModifiedDate nếu muốn những giá trị đó nằm trong document vừa được lưu. Khi callback chạy, source đã được gửi.

## 17. Callback ordering

Ứng dụng có thể có nhiều callback cùng loại. Spring Data hỗ trợ thứ tự callback thông qua cơ chế ordering của Spring, ví dụ @Order hoặc Ordered, tùy callback infrastructure và phiên bản.

Ví dụ:

    @Component
    @Order(100)
    public class FirstProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {
            return entity;
        }
    }

    @Component
    @Order(200)
    public class SecondProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {
            return entity;
        }
    }

Giá trị order thấp hơn thường có độ ưu tiên thực thi trước theo quy tắc ordering của Spring. Hãy xác nhận semantics của callback chain trong phiên bản dự án và không dựa vào thứ tự bean discovery ngẫu nhiên.

Nếu callback thứ hai phụ thuộc vào dữ liệu do callback thứ nhất thay đổi trong bộ nhớ, thứ tự phải được cấu hình rõ. Tuy nhiên, tránh dùng callback chain để tạo một pipeline nghiệp vụ phức tạp. Nếu các bước cần phối hợp chặt chẽ, service orchestration thường dễ hiểu và kiểm thử hơn.

## 18. Callback áp dụng cho thao tác nào?

AfterSaveCallback gắn với lifecycle save được thực hiện qua các thành phần Spring Data có tích hợp entity callbacks. Không nên mặc định nó chạy cho mọi thao tác có thể ghi vào Elasticsearch.

Hãy phân biệt:

- repository.save(entity)
- ElasticsearchOperations.save(entity)
- saveAll
- bulkIndex với danh sách IndexQuery
- bulkUpdate
- bulkDelete
- gọi Elasticsearch Java API Client trực tiếp
- gọi REST API từ một HTTP client khác

Các API trên có thể đi qua những đường thực thi khác nhau. Bulk method làm việc với query/request objects và có thể không gọi cùng callback chain của save từng entity. Gọi Java API Client trực tiếp cũng không tự đi qua Spring Data entity callback infrastructure.

Nếu callback là một phần bắt buộc của logic, hãy kiểm tra từng API ghi thực tế bằng integration test. Không dựa vào tên method hoặc giả định rằng tất cả thao tác index đều gọi AfterSaveCallback.

Nếu cần logic áp dụng cho cả save đơn lẻ và bulk, có thể đặt phần dùng chung ở service hoặc component riêng rồi gọi tường minh từ từng đường ghi, hoặc thiết kế một lớp persistence adapter thống nhất.

## 19. AfterSaveCallback và thao tác delete

AfterSaveCallback dành cho thao tác save. Nó không phải callback sau delete.

Nếu cần logic sau khi xóa, hãy xem callback lifecycle tương ứng của phiên bản Spring Data Elasticsearch, chẳng hạn callback sau delete nếu API đang dùng cung cấp. Nếu cần xử lý nghiệp vụ khi xóa, service layer có thể điều phối rõ ràng:

    productRepository.deleteById(id);
    eventPublisher.publishEvent(
        new ProductDeletedEvent(id)
    );

Đoạn code này cần được thiết kế với cùng lưu ý về side effect và tính bền vững. Nếu delete thành công nhưng publish event thất bại, dữ liệu đã bị xóa và event có thể bị mất.

Không dùng AfterSaveCallback để xử lý xóa chỉ vì tên callback nghe như callback chung cho mọi persistence operation.

## 20. Callback imperative và reactive

Spring Data Elasticsearch có cả API imperative và reactive. Callback dùng trong luồng imperative không nên được giả định có thể sử dụng nguyên trạng trong reactive template.

Ở reactive stack, Spring Data có cơ chế reactive entity callback tương ứng trong những phiên bản hỗ trợ. Callback có thể trả về Publisher/Mono thay vì giá trị entity đồng bộ, và phải được compose vào reactive chain.

Ví dụ minh họa ý tưởng:

    @Component
    public class ReactiveProductAfterSaveCallback
            implements ReactiveAfterSaveCallback<Product> {

        @Override
        public Publisher<Product> onAfterSave(
                Product entity,
                IndexCoordinates index) {

            return Mono.just(entity);
        }
    }

Tên interface, package và chữ ký reactive cần xác nhận theo phiên bản Spring Data Elasticsearch thực tế. Ví dụ trên mô tả dạng reactive callback; không trộn ReactiveAfterSaveCallback với AfterSaveCallback imperative.

Trong reactive callback:

- Không gọi block() để chờ một tác vụ I/O.
- Không thực hiện side effect đồng bộ lâu trên event loop.
- Trả Publisher/Mono và compose lỗi theo reactive semantics.
- Giữ callback stateless và thread-safe.
- Không subscribe độc lập bên trong callback nếu muốn side effect thuộc cùng lifecycle.

Nếu callback gọi một service reactive, hãy compose publisher đó rồi trả entity sau khi side effect hoàn tất theo yêu cầu. Nếu chỉ ghi metric nhanh, có thể thực hiện thao tác đồng bộ rất nhẹ tùy thread model.

## 21. Xử lý metadata bằng service adapter

Khi cần metadata chi tiết hơn callback cung cấp, có thể xây dựng một adapter trả về kết quả persistence riêng:

    public record ProductSaveResult(
        Product product,
        String id,
        Long version,
        String indexName
    ) {}

Service:

    public ProductSaveResult save(Product product) {
        Product saved = operations.save(product);

        return new ProductSaveResult(
            saved,
            saved.getId(),
            saved.getVersion(),
            IndexCoordinates.of("products").getIndexName()
        );
    }

Ví dụ này chỉ trả metadata mà entity và service đã có. Nếu cần response cấp thấp như result, shard info, sequence number hoặc primary term, adapter phải dùng API trả về các trường đó và ánh xạ chúng rõ ràng.

Không nên ép AfterSaveCallback làm nhiệm vụ của response adapter. Callback có mục đích lifecycle; adapter có mục đích định nghĩa contract kết quả cho caller.

## 22. Lưu metadata vào document hay giữ ngoài document?

Không phải metadata nào cũng nên ghi vào source.

Ví dụ:

| Thông tin | Thường nên lưu ở đâu? | Lý do |
|---|---|---|
| productId nghiệp vụ | Source field nếu cần query/aggregation; đồng thời có thể là _id | Là dữ liệu domain |
| createdAt | Source field | Là metadata nghiệp vụ cần tìm kiếm hoặc hiển thị |
| updatedAt | Source field | Là dữ liệu nghiệp vụ/audit |
| Elasticsearch version | Persistence metadata/entity mapping | Dùng cho concurrency |
| Sequence number/primary term | Persistence metadata hoặc response adapter | Dùng cho concurrency control |
| Shard response details | Response/log/metrics | Thường không phải dữ liệu nghiệp vụ |
| IndexCoordinates | Context của thao tác | Không nhất thiết là source field |
| Request latency | Metrics/observability | Không nên ghi lại trong document vừa index |

Nếu muốn lưu một field như indexedAt trong source, hãy xác định thời điểm trước khi gửi request và dùng callback trước save hoặc service. Không thể ghi chính xác thời điểm hoàn tất server-side vào cùng document bằng AfterSaveCallback mà không thực hiện một write bổ sung.

## 23. Không tự động save lại bên trong AfterSaveCallback

Một anti-pattern là gọi repository.save lần nữa từ callback:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        entity.setProcessed(true);
        return repository.save(entity);
    }

Đây có thể tạo vòng lặp:

    save
      -> AfterSaveCallback
          -> repository.save
              -> AfterSaveCallback
                  -> repository.save
                      ...

Ngay cả khi tránh được recursion bằng cờ hoặc điều kiện, việc save lồng nhau có thể tạo nhiều request, race condition và trạng thái khó dự đoán.

Nếu cần ghi một document khác sau khi save, hãy điều phối ở service layer hoặc phát event có consumer riêng. Nếu cần thay đổi chính document trước khi lưu, dùng callback trước save.

## 24. Exception handling và observability

Callback nên có chính sách lỗi rõ ràng:

- Lỗi log/metric không quan trọng có thể được xử lý để không làm hỏng đường ghi, tùy yêu cầu.
- Lỗi nghiệp vụ bắt buộc phải báo cho caller cần được ném ra có chủ đích, đồng thời hiểu rằng document có thể đã được ghi.
- Lỗi gửi event nên có retry/delivery strategy riêng nếu event quan trọng.
- Không bắt mọi exception rồi bỏ qua mà không ghi nhận.

Một ví dụ chỉ ghi log lỗi cho metric phụ:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        try {
            metrics.recordSaved(index.getIndexName());
        } catch (RuntimeException ex) {
            log.warn(
                "Could not record save metric for id={}",
                entity.getId(),
                ex
            );
        }

        return entity;
    }

Đây chỉ phù hợp nếu metric là side effect phụ và việc mất một điểm metric không được coi là lỗi persistence. Nếu metric là một phần bắt buộc của nghiệp vụ, cần thiết kế delivery và retry rõ ràng thay vì nuốt exception.

Log nên có correlation ID hoặc job ID nếu cần truy vết. Tránh đưa toàn bộ source hoặc metadata nhạy cảm vào log.

## 25. Kiểm thử AfterSaveCallback

Nên kiểm tra callback thông qua luồng persistence thật trong integration test nếu logic phụ thuộc metadata hoặc thứ tự lifecycle.

Ví dụ kiểm thử đơn giản:

    @SpringBootTest
    class ProductAfterSaveCallbackTest {

        @Autowired
        ProductRepository repository;

        @Autowired
        ElasticsearchOperations operations;

        @Test
        void callbackRunsAfterSave() {
            Product product = new Product();
            product.setId("p-callback-1");
            product.setName("Keyboard");

            Product saved = repository.save(product);

            assertThat(saved.getId()).isEqualTo("p-callback-1");
        }
    }

Nếu cần xác nhận search visibility, test phải refresh hoặc dùng refresh policy phù hợp. Callback chạy sau save không đồng nghĩa document đã searchable nếu write không yêu cầu refresh.

Nếu callback ghi metric hoặc phát event, có thể inject mock hoặc spy cho dependency và xác nhận callback được gọi đúng một lần qua đường persistence đang kiểm thử.

Những trường hợp nên kiểm tra:

- Entity có ID do ứng dụng cấp.
- Entity dùng ID được sinh tự động nếu use case có hỗ trợ.
- Entity có @Version.
- Callback nhận đúng IndexCoordinates.
- Nhiều callback chạy theo thứ tự mong muốn.
- Callback exception ảnh hưởng caller như thế nào.
- save, saveAll và bulk API có gọi callback hay không trong phiên bản dự án.
- Callback imperative và reactive được đăng ký đúng infrastructure.

Không dùng unit test gọi trực tiếp method onAfterSave làm bằng chứng rằng Spring Data tự đăng ký và gọi callback trong repository flow. Unit test chỉ kiểm tra logic bên trong callback; integration test mới kiểm tra lifecycle wiring.

## 26. Kiểm tra phiên bản Spring Data Elasticsearch

Callback API đã phát triển cùng Spring Data và Elasticsearch client integration. Trước khi triển khai, hãy kiểm tra:

- Package của AfterSaveCallback.
- Chữ ký onAfterSave và kiểu IndexCoordinates.
- Cách đăng ký callback trong application context.
- Cách template nhận EntityCallbacks nếu được tạo thủ công.
- Callback nào được gọi trong repository.save và ElasticsearchOperations.save.
- saveAll và bulk operations có đi qua callback chain hay không.
- Metadata nào đã được gán vào entity tại thời điểm callback.
- Reactive callback contract nếu dùng reactive template.

Không nên trộn ví dụ từ Spring Data Elasticsearch major version cũ với Elasticsearch Java API Client hiện đại. Các package, builder và cách đăng ký callback có thể khác.

Nếu callback cần metadata cụ thể, hãy viết integration test nhỏ trên đúng phiên bản dependency đã resolve thay vì phụ thuộc vào giả định từ một phiên bản khác.

## 27. Những lỗi thường gặp

### Dùng AfterSaveCallback để sửa source

Callback chạy sau khi document đã được ghi. Thay đổi entity trong callback không tự được index lại. Dùng BeforeConvertCallback hoặc BeforeSaveCallback nếu field cần nằm trong source.

### Nghĩ callback nhận IndexResponse

Chữ ký AfterSaveCallback thông thường nhận entity và IndexCoordinates. Nếu cần result, shard info hoặc response metadata không được ánh xạ, dùng API/client adapter riêng.

### Nghĩ callback luôn có đầy đủ metadata

ID, version hoặc metadata concurrency chỉ có thể đọc nếu template đã gán chúng vào entity và mapping/version hỗ trợ. Xác minh lifecycle theo phiên bản.

### Nhầm @Version với refresh

Version hỗ trợ optimistic locking. Refresh quyết định search visibility. Hai cơ chế độc lập.

### Dùng callback để ghi audit field

createdAt/updatedAt cần được gán trước khi conversion để đi vào source. Dùng Spring Data Auditing hoặc callback trước save.

### Gọi service ngoài đồng bộ trong callback

Side effect chậm có thể kéo dài request save. Lỗi side effect có thể làm caller nhận exception dù write đã thành công. Dùng idempotency và delivery strategy phù hợp.

### Gọi save lại từ callback

Có thể tạo recursion hoặc nhiều lần ghi. Điều phối ở service hoặc event handler riêng.

### Giả định bulk luôn gọi callback

Bulk API có thể đi qua đường thực thi khác save entity. Kiểm tra từng API trên phiên bản thực tế.

### Không quản lý callback ordering

Nhiều callback cùng loại cần thứ tự rõ ràng nếu có phụ thuộc. Dùng @Order/Ordered khi cần và tránh chain quá phức tạp.

### Nuốt exception không ghi log

Lỗi side effect bị mất dấu và khó điều tra. Quyết định lỗi nào được bỏ qua, lỗi nào phải truyền lên và ghi nhận đầy đủ.

### Xem callback là transaction hook

AfterSaveCallback không tạo transaction rollback cho Elasticsearch. Nếu cần delivery bền vững giữa nhiều hệ thống, dùng outbox hoặc quy trình đồng bộ riêng.

## 28. Quy trình sử dụng AfterSaveCallback

Khi cân nhắc callback sau save, hãy đi theo các bước:

1. Xác định logic thật sự cần chạy sau thao tác save.
2. Nếu logic chỉ chuẩn bị field source, chuyển sang BeforeConvertCallback hoặc BeforeSaveCallback.
3. Nếu logic gán created/updated metadata, dùng auditing.
4. Nếu logic cần quan sát ID/version/index sau save, xác định metadata nào được expose trong entity và callback signature.
5. Nếu cần IndexResponse chi tiết, dùng adapter hoặc Java API Client.
6. Đăng ký callback dưới dạng Spring bean và kiểm tra template đang sử dụng callback infrastructure.
7. Giữ callback nhẹ, stateless và thread-safe.
8. Thiết kế side effect idempotent và hiểu rằng write có thể đã thành công trước khi callback lỗi.
9. Kiểm tra callback ordering nếu có nhiều callback.
10. Kiểm thử riêng save, saveAll, bulk và reactive path nếu ứng dụng dùng chúng.
11. Không dùng callback để save lại chính entity hoặc thay thế transaction/outbox.
12. Đo tác động của callback lên latency của đường ghi.

## Kết luận

AfterSaveCallback là entity callback chạy sau thao tác save trong Spring Data Elasticsearch. Callback imperative thường nhận entity cùng IndexCoordinates và trả entity cho callback chain. Nó phù hợp để ghi log, metric hoặc khởi tạo xử lý hậu lưu nhẹ. Entity có thể đã được cập nhật ID hoặc version tùy lifecycle và phiên bản, nhưng callback không trực tiếp nhận toàn bộ IndexResponse; nếu cần result, shard information hoặc concurrency metadata không được ánh xạ, cần dùng API response hoặc adapter riêng.

Hãy phân biệt metadata persistence với field trong _source. @Version và metadata concurrency phục vụ kiểm soát cập nhật; @CreatedDate và @LastModifiedDate cần được gán trước khi document được gửi, thường qua Spring Data Auditing hoặc callback trước save. AfterSaveCallback không tự lưu những thay đổi entity mà nó tạo ra, không rollback được write đã hoàn tất và không phải transaction/outbox hook. Giữ callback ngắn, idempotent, đăng ký đúng template và kiểm tra hành vi trên phiên bản Spring Data Elasticsearch thực tế để tránh side effect lặp hoặc caller nhận lỗi sau khi document đã được ghi.
