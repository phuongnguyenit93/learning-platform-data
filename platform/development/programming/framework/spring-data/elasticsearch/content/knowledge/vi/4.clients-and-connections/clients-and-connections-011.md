# Phân biệt client đồng bộ và client reactive

Khi ứng dụng Java gọi Elasticsearch, request có thể được thực hiện theo cách đồng bộ hoặc reactive. Khác biệt cốt lõi nằm ở cách ứng dụng chờ kết quả và sử dụng tài nguyên trong lúc chờ I/O.

- **Client đồng bộ (synchronous client):** lời gọi chỉ trả quyền điều khiển cho chương trình khi thao tác đã hoàn tất hoặc phát sinh lỗi. Thread gọi thường bị giữ trong thời gian chờ phản hồi từ Elasticsearch.
- **Client reactive:** biểu diễn kết quả bằng các kiểu publisher như Mono và Flux. Lời gọi tạo ra một pipeline mô tả thao tác; công việc I/O được thực thi theo cơ chế reactive khi publisher được subscribe. Thread không cần bị giữ chỉ để chờ phản hồi mạng.

Trong Spring Data Elasticsearch, hai hướng này được thể hiện qua các API tương ứng:

- Hướng đồng bộ: ElasticsearchClient, ElasticsearchOperations, ElasticsearchTemplate và ElasticsearchRepository.
- Hướng reactive: reactive client integration, ReactiveElasticsearchOperations, ReactiveElasticsearchTemplate và ReactiveElasticsearchRepository.

Chọn đúng hướng giúp ứng dụng phù hợp với mô hình xử lý request của Spring MVC hoặc Spring WebFlux, đồng thời tránh vô tình đưa thao tác blocking vào một luồng xử lý được thiết kế non-blocking.

## 1. Đồng bộ và reactive khác nhau ở đâu?

Giả sử service cần tìm sản phẩm trong Elasticsearch. Cả hai cách đều gửi cùng một loại yêu cầu đến server và nhận dữ liệu tương tự. Điểm khác là thread của ứng dụng làm gì trong lúc chờ response.

### Cách đồng bộ

    Product product = repository.findById(id)
        .orElseThrow();

Khi gọi findById, thread thực hiện lời gọi chờ kết quả. Nếu Elasticsearch cần 100 ms để phản hồi, thread có thể bị giữ trong khoảng thời gian đó. Sau khi kết quả về, chương trình tiếp tục chạy câu lệnh tiếp theo.

Đây là mô hình dễ đọc và dễ theo dõi:

    Thread A
       |
       v
    Gửi request đến Elasticsearch
       |
       v
    Chờ response (thread bị giữ)
       |
       v
    Nhận response
       |
       v
    Xử lý kết quả

### Cách reactive

    Mono<Product> productMono = repository.findById(id);

Lời gọi trên trả về một Mono<Product>. Mono là một publisher có thể phát ra tối đa một phần tử hoặc kết thúc mà không có phần tử, hoặc phát ra lỗi. Việc tạo publisher chưa có nghĩa là kết quả đã được lấy về.

Khi pipeline được subscribe, reactive client thực hiện thao tác I/O và phát kết quả khi response sẵn sàng:

    Request
       |
       v
    Tạo reactive pipeline
       |
       v
    Subscribe
       |
       v
    Gửi request bằng I/O non-blocking
       |
       v
    Nhận tín hiệu khi response sẵn sàng
       |
       v
    Xử lý và phát dữ liệu

Thread không cần nằm chờ response mạng. Trong thời gian chờ, runtime có thể dùng thread đó để xử lý công việc khác. Khi có dữ liệu, pipeline tiếp tục theo cơ chế lập lịch của Reactor và các thành phần tham gia.

Reactive không có nghĩa là mọi đoạn code luôn chạy trên một thread khác hoặc tự động chạy song song. Nó mô tả cách biểu diễn và phối hợp các tín hiệu bất đồng bộ; thread thực thi phụ thuộc scheduler, client và operator được sử dụng.

## 2. Client đồng bộ trong Spring Data Elasticsearch

Ở hướng đồng bộ, ứng dụng thường làm việc với các abstraction sau:

- ElasticsearchRepository cho thao tác repository.
- ElasticsearchOperations và ElasticsearchTemplate cho thao tác linh hoạt hơn repository.
- ElasticsearchClient khi cần gọi trực tiếp Elasticsearch Java API Client.

Ví dụ repository:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

Service có thể gọi repository theo cách tuần tự:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public List<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

Phương thức findBooks trả về List<Product>. Khi phương thức trả về, thao tác repository đã hoàn tất và service có thể sử dụng danh sách kết quả ngay.

Nếu gọi Elasticsearch Java API Client trực tiếp, mã đồng bộ có dạng:

    SearchResponse<Product> response = elasticsearchClient.search(
        request -> request
            .index("products")
            .query(query -> query
                .match(match -> match
                    .field("name")
                    .query("coffee")
                )
            ),
        Product.class
    );

Lời gọi search thực hiện đồng bộ và có thể phát sinh IOException. Thread gọi chờ kết quả HTTP và việc giải tuần tự hóa response hoàn tất. Đây là cách sử dụng phù hợp với luồng xử lý đồng bộ.

### Đặc điểm của hướng đồng bộ

- Luồng điều khiển dễ đọc: gọi phương thức, nhận kết quả, xử lý tiếp.
- Phù hợp với ứng dụng Spring MVC/Servlet và các tác vụ batch hoặc command-line vốn tổ chức theo kiểu đồng bộ.
- Dễ tích hợp với thư viện blocking khác.
- Thread bị giữ trong lúc chờ I/O, vì vậy số lượng thread và connection cần được quản lý phù hợp với tải.
- Có thể đơn giản hóa xử lý lỗi vì exception xuất hiện trực tiếp tại lời gọi.

Đồng bộ không đồng nghĩa với chậm trong mọi tình huống. Với tải vừa phải, thao tác ngắn và mô hình ứng dụng truyền thống, cách đồng bộ thường dễ vận hành và dễ bảo trì.

## 3. Reactive client và các API reactive của Spring Data Elasticsearch

Spring Data Elasticsearch cung cấp API reactive để ứng dụng phối hợp với Reactor. Các abstraction thường gặp gồm:

- ReactiveElasticsearchRepository: repository có phương thức trả về Mono hoặc Flux.
- ReactiveElasticsearchOperations: API thao tác dữ liệu reactive.
- ReactiveElasticsearchTemplate: implementation của reactive operations.
- Reactive client integration: tầng client thực hiện request theo cơ chế reactive mà phiên bản Spring Data Elasticsearch hỗ trợ.

Reactive repository sử dụng cùng ý tưởng repository nhưng kiểu kết quả khác:

    public interface ProductReactiveRepository
            extends ReactiveElasticsearchRepository<Product, String> {

        Flux<Product> findByCategory(String category);
    }

Một service có thể trả publisher trực tiếp:

    @Service
    public class ProductReactiveService {

        private final ProductReactiveRepository repository;

        public ProductReactiveService(ProductReactiveRepository repository) {
            this.repository = repository;
        }

        public Flux<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

findBooks không trả về danh sách đã được tải ngay lập tức. Nó trả về Flux<Product>, mô tả một luồng có thể phát ra nhiều sản phẩm khi được subscribe.

Với truy vấn linh hoạt hơn repository, có thể sử dụng ReactiveElasticsearchOperations:

    Flux<SearchHit<Product>> searchHits =
        reactiveElasticsearchOperations.search(query, Product.class);

API cụ thể và kiểu kết quả của từng phương thức cần theo phiên bản Spring Data Elasticsearch đang dùng. Ý tưởng quan trọng là thao tác được giữ trong reactive pipeline và kết quả được biểu diễn bằng publisher, thay vì chờ trực tiếp trong lời gọi.

### Mono và Flux

Reactor cung cấp hai kiểu publisher thường gặp:

| Kiểu | Số phần tử phát ra | Ví dụ |
|---|---:|---|
| Mono<T> | 0 hoặc 1 | Tìm một sản phẩm theo id, lưu một document |
| Flux<T> | 0 đến nhiều | Tìm danh sách sản phẩm, đọc nhiều search hit |

Publisher có thể kết thúc bình thường, kết thúc mà không có phần tử hoặc kết thúc bằng lỗi. Vì vậy, reactive code cần xử lý cả dữ liệu, tín hiệu hoàn tất và tín hiệu lỗi.

Ví dụ kết hợp dữ liệu:

    Mono<Product> productMono =
        repository.findById(id);

    Mono<ProductView> viewMono =
        productMono.map(product ->
            new ProductView(product.getId(), product.getName())
        );

map biến đổi phần tử được phát ra khi dữ liệu đến. Nó không cần lấy Product ra khỏi publisher để xử lý ngay tại thời điểm xây dựng pipeline.

## 4. Reactive không phải chỉ là bọc client đồng bộ trong Mono

Đây là điểm cần phân biệt rõ. Nếu gọi một phương thức blocking rồi đặt kết quả vào Mono, thao tác I/O vẫn blocking. Kiểu trả về Mono tự nó không làm cho lời gọi mạng trở thành non-blocking.

Ví dụ không phù hợp trong một pipeline reactive:

    Mono<Product> productMono = Mono.just(
        blockingRepository.findById(id).orElseThrow()
    );

Lệnh findById được thực thi trước khi Mono.just được tạo. Thread hiện tại vẫn phải chờ kết quả. Mono chỉ bọc một giá trị đã có.

Một ví dụ khác cũng không tạo ra I/O non-blocking:

    Mono.fromCallable(() -> blockingRepository.findById(id));

Publisher này trì hoãn thời điểm gọi phương thức đến khi subscribe, nhưng nếu không chuyển công việc sang scheduler phù hợp thì lời gọi blocking vẫn chạy trên thread thực hiện subscription.

Nếu buộc phải tích hợp một lời gọi blocking vào reactive pipeline trong giai đoạn chuyển đổi, có thể cô lập nó trên boundedElastic:

    Mono.fromCallable(() ->
            blockingRepository.findById(id).orElseThrow()
        )
        .subscribeOn(Schedulers.boundedElastic());

Cách này giúp tránh chặn event-loop thread của WebFlux, nhưng thao tác bên dưới vẫn blocking và vẫn tiêu thụ một worker thread trong lúc chờ. Đây là biện pháp tích hợp tạm thời cho thư viện blocking, không phải thay thế cho reactive client thực sự.

Không nên gọi blocking client trực tiếp trên event-loop thread. Một lời gọi chậm có thể giữ event loop, khiến nhiều request khác phải chờ và làm giảm khả năng phục vụ đồng thời của ứng dụng.

## 5. Async client, reactive client và synchronous client

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Loại | Cách nhận kết quả | Thread gọi có phải chờ? | Tích hợp với Reactor |
|---|---|---|---|
| Synchronous | Trả kết quả trực tiếp hoặc ném exception | Thường có | Cần adapter nếu muốn đưa vào pipeline |
| Asynchronous | Callback hoặc Future/CompletableFuture | Không phải chờ kết quả theo kiểu blocking | Có thể chuyển đổi sang Mono/Flux |
| Reactive | Publisher như Mono/Flux | Không giữ thread chỉ để chờ I/O nếu client thực sự non-blocking | Tích hợp trực tiếp với Reactor |

Elasticsearch Java API Client có API đồng bộ ElasticsearchClient và API bất đồng bộ ElasticsearchAsyncClient. API async thường biểu diễn kết quả bằng CompletableFuture. CompletableFuture không tự có semantics backpressure của Reactive Streams.

Trong khi đó, Spring Data reactive APIs dùng các publisher như Mono và Flux để phối hợp thao tác dữ liệu trong hệ sinh thái Reactor. Một client async có thể được chuyển thành Mono bằng Mono.fromFuture, nhưng điều đó không tự tạo ra backpressure ở tầng HTTP và cũng không biến một client blocking thành non-blocking.

Khi đọc tài liệu hoặc chọn dependency, cần xác định chính xác đang nói đến ElasticsearchClient, ElasticsearchAsyncClient hay reactive client integration của Spring Data. Không nên gọi chung cả ba là reactive client.

## 6. Backpressure và xử lý luồng dữ liệu

Reactive Streams có khái niệm backpressure: subscriber có thể điều tiết số lượng phần tử mà mình sẵn sàng nhận. Điều này hữu ích khi một luồng dữ liệu có nhiều phần tử và tốc độ sản xuất có thể vượt quá tốc độ xử lý.

Ví dụ, một Flux có thể được xử lý theo từng phần:

    repository.findByCategory("book")
        .map(this::toProductView)
        .filter(ProductView::isAvailable)
        .take(100);

Các operator mô tả cách xử lý phần tử khi chúng được phát ra. take(100) giới hạn số phần tử mà pipeline cần tiếp nhận.

Tuy nhiên, không nên hiểu backpressure của Reactor là mọi tầng bên dưới đều truyền ngược áp lực trực tiếp đến Elasticsearch server. Elasticsearch có thể xử lý một search request và tạo response theo cách riêng; client, HTTP transport và cách Spring Data phát kết quả quyết định mức độ dữ liệu được buffer hoặc phát dần. Backpressure là cơ chế phối hợp giữa publisher và subscriber, còn khả năng điều tiết ở tầng mạng/server phụ thuộc implementation.

Với kết quả rất lớn, cần thiết kế thêm pagination, search_after, giới hạn kích thước trang hoặc cơ chế cuộn phù hợp. Không nên giả định Flux tự động làm cho một truy vấn không giới hạn trở nên ít tốn bộ nhớ.

## 7. Xử lý lỗi và vòng đời pipeline

Trong mã đồng bộ, lỗi thường được biểu diễn bằng exception ngay tại vị trí gọi:

    try {
        Product product = repository.findById(id)
            .orElseThrow();
        return product;
    } catch (RuntimeException ex) {
        // Handle or propagate the error
        throw ex;
    }

Trong reactive pipeline, lỗi là một tín hiệu terminal. Có thể xử lý bằng các operator như onErrorMap, onErrorResume hoặc doOnError:

    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)
        ))
        .onErrorMap(
            ElasticsearchException.class,
            ex -> new ProductSearchException(ex)
        );

onErrorMap chuyển loại lỗi; onErrorResume có thể cung cấp một publisher thay thế; doOnError phù hợp cho tác vụ quan sát như ghi log. Không nên dùng doOnError để thay thế xử lý lỗi vì operator này không tự phục hồi pipeline.

Một reactive pipeline cũng có thể bị hủy khi subscriber cancel. Client và transport có thể sử dụng tín hiệu hủy để dừng hoặc giải phóng một phần công việc đang thực hiện, tùy implementation. Không nên giả định mọi thao tác đã gửi đến Elasticsearch đều có thể bị thu hồi hoặc server chắc chắn dừng xử lý ngay khi subscriber cancel.

### Không tự subscribe trong service

Thông thường service nên trả Mono hoặc Flux cho tầng gọi tiếp theo:

    public Mono<Product> findProduct(String id) {
        return repository.findById(id);
    }

Không nên gọi subscribe bên trong service chỉ để khởi động công việc rồi trả về void:

    repository.findById(id).subscribe(product -> {
        // Process product
    });

Cách này tách pipeline khỏi người gọi. Lỗi có thể không được chuyển về tầng controller, việc hủy request không còn điều khiển được thao tác, và ứng dụng khó phối hợp thứ tự thực thi. Hãy để framework hoặc tầng biên phù hợp thực hiện subscription.

## 8. Chọn client theo mô hình ứng dụng

### Ứng dụng Spring MVC/Servlet

Spring MVC thường xử lý request bằng mô hình Servlet với thread phục vụ request. Dùng ElasticsearchRepository, ElasticsearchOperations hoặc ElasticsearchClient đồng bộ là lựa chọn tự nhiên nếu toàn bộ luồng nghiệp vụ đang dùng blocking I/O.

Mô hình này đơn giản và dễ tích hợp với các thư viện JDBC, file I/O hoặc SDK blocking khác. Cần cấu hình thread pool, connection pool và timeout phù hợp với tải.

### Ứng dụng Spring WebFlux

Spring WebFlux được thiết kế để xử lý I/O theo hướng non-blocking. Nếu request đi qua WebFlux và các tầng dữ liệu đều hỗ trợ reactive, nên dùng ReactiveElasticsearchRepository hoặc ReactiveElasticsearchOperations.

Controller có thể trả trực tiếp publisher:

    @RestController
    @RequestMapping("/products")
    public class ProductController {

        private final ProductReactiveRepository repository;

        public ProductController(ProductReactiveRepository repository) {
            this.repository = repository;
        }

        @GetMapping("/{id}")
        public Mono<Product> findById(@PathVariable String id) {
            return repository.findById(id);
        }

        @GetMapping
        public Flux<Product> findByCategory(
                @RequestParam String category) {
            return repository.findByCategory(category);
        }
    }

Framework quản lý subscription và ghi kết quả ra HTTP response. Controller không cần tự block để lấy Product hoặc tự subscribe vào repository.

### Batch và tác vụ nền

Một tác vụ batch chạy tuần tự có thể dùng client đồng bộ nếu cách đó dễ hiểu và đáp ứng yêu cầu. Nếu batch xử lý lượng lớn request độc lập, có thể cân nhắc async hoặc reactive để kiểm soát concurrency, nhưng cần giới hạn số request đồng thời và xử lý retry, lỗi từng phần, backpressure.

Reactive không tự động làm một batch nhanh hơn. Nếu Elasticsearch đã là nút thắt, gửi nhiều request đồng thời hơn có thể làm cluster quá tải thay vì cải thiện throughput.

## 9. Những nguyên tắc khi kết hợp reactive với Elasticsearch

1. **Giữ nhất quán trong một luồng xử lý:** ưu tiên dùng reactive repository/operations xuyên suốt khi ứng dụng đang chạy theo WebFlux.
2. **Không block event loop:** tránh gọi ElasticsearchClient đồng bộ hoặc dùng block() trong request path reactive.
3. **Không tự subscribe ở tầng service:** trả publisher để controller hoặc framework quản lý vòng đời.
4. **Giới hạn concurrency:** không phát hàng nghìn request đến Elasticsearch cùng lúc chỉ vì pipeline hỗ trợ reactive.
5. **Quản lý kết quả lớn:** dùng pagination hoặc chiến lược đọc dữ liệu phù hợp; Flux không loại bỏ giới hạn bộ nhớ của response.
6. **Xử lý lỗi theo tín hiệu:** dùng operator phù hợp để chuyển đổi, phục hồi hoặc quan sát lỗi.
7. **Chọn đúng client:** phân biệt ElasticsearchClient đồng bộ, ElasticsearchAsyncClient và reactive client integration.
8. **Kiểm tra tính tương thích:** dùng dependency và cấu hình theo phiên bản Spring Boot/Spring Data Elasticsearch đang triển khai.

## 10. Các lỗi thường gặp

### Dùng ElasticsearchClient đồng bộ trong WebFlux

Lời gọi có thể giữ event-loop thread trong lúc chờ HTTP response. Nếu cần tích hợp tạm thời, chuyển blocking call sang boundedElastic; về lâu dài, dùng reactive API phù hợp.

### Nghĩ Mono.just làm cho lời gọi trở thành non-blocking

Đối số của Mono.just được tính trước khi Mono được tạo. Nếu đối số là một lời gọi blocking, thread hiện tại đã bị chặn trước đó.

### Dùng fromCallable nhưng không chuyển scheduler

fromCallable trì hoãn lời gọi đến lúc subscribe nhưng không tự chuyển lời gọi sang thread khác. Nếu callable gọi thư viện blocking, cần cô lập bằng scheduler phù hợp.

### Gọi block() trong controller WebFlux

block() buộc thread hiện tại chờ kết quả. Điều này phá vỡ lợi ích non-blocking và có thể gây nghẽn event loop.

### Subscribe bên trong service

Tự subscribe làm pipeline tách khỏi người gọi và khiến việc truyền lỗi, hủy tác vụ, kiểm soát thứ tự khó hơn. Hãy trả publisher cho tầng trên.

### Cho rằng reactive luôn nhanh hơn đồng bộ

Reactive có thể cải thiện khả năng sử dụng thread khi có nhiều thao tác I/O đang chờ, nhưng không làm Elasticsearch xử lý một truy vấn nhanh hơn. Hiệu quả phụ thuộc tải, độ trễ, giới hạn connection, tài nguyên cluster và toàn bộ chuỗi dependency.

### Trộn blocking và reactive mà không xác định ranh giới

Một pipeline có thể chứa cả reactive và blocking code, nhưng cần xác định rõ phần blocking và cô lập nó. Nếu không, event-loop thread có thể bị chặn dù kiểu trả về cuối cùng là Mono hoặc Flux.

## Kết luận

Client đồng bộ trả kết quả trực tiếp và thường giữ thread gọi trong lúc chờ I/O. Client reactive biểu diễn thao tác bằng publisher như Mono và Flux, cho phép phối hợp I/O non-blocking và xử lý tín hiệu dữ liệu, lỗi, hoàn tất hoặc hủy.

Trong Spring Data Elasticsearch, hướng đồng bộ thường dùng ElasticsearchRepository, ElasticsearchOperations và ElasticsearchClient; hướng reactive dùng ReactiveElasticsearchRepository, ReactiveElasticsearchOperations và reactive client integration tương ứng. Việc chọn lựa nên dựa trên mô hình xử lý của ứng dụng: Spring MVC/Servlet thường phù hợp với API đồng bộ, còn Spring WebFlux nên dùng reactive API xuyên suốt để tránh chặn event loop.

Điều quan trọng là hiểu bản chất của lời gọi bên dưới. Bọc một phương thức blocking trong Mono không biến nó thành non-blocking. Khi cần phối hợp với thư viện blocking, phải cô lập phần đó trên scheduler phù hợp; khi xây dựng hệ thống reactive thực sự, hãy dùng reactive client và giữ publisher xuyên suốt luồng xử lý.
