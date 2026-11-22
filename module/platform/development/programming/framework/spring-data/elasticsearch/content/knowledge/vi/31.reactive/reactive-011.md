# Tránh block và thao tác chặn trong luồng xử lý

Trong ứng dụng Spring Data Elasticsearch sử dụng Reactive, mục tiêu là giữ cho luồng xử lý không bị giữ lại để chờ I/O. Khi một request đang chờ Elasticsearch, database, HTTP service hoặc file system, thread có thể tiếp tục phục vụ công việc khác thay vì đứng yên chờ kết quả. Điều này giúp ứng dụng tận dụng thread hiệu quả hơn, đặc biệt khi có nhiều request đồng thời.

Một lời gọi reactive không tự động bảo đảm toàn bộ chuỗi xử lý đều non-blocking. Nếu trong một Reactor pipeline có gọi repository đồng bộ, dùng block(), gọi Future.get(), chạy Thread.sleep() hoặc thực hiện I/O chặn, thread đang chạy pipeline vẫn bị giữ lại. Trong WebFlux, thread đó có thể là event-loop thread đang phục vụ nhiều kết nối.

Bài này tập trung vào cách nhận diện và loại bỏ thao tác blocking trong luồng reactive của Spring Data Elasticsearch. Nội dung gồm thread model của Reactor, API reactive của Spring Data, cách kết hợp Mono/Flux, cách cô lập thư viện blocking khi chưa thể thay thế, backpressure, context propagation, lỗi, cancellation và kiểm thử.

## 1. Blocking và non-blocking khác nhau thế nào?

Một thao tác **blocking** giữ thread hiện tại cho đến khi thao tác hoàn tất hoặc timeout. Ví dụ:

~~~java
Product product = blockingRepository.findById(id).orElse(null);
~~~

Nếu repository này là repository đồng bộ, lời gọi sẽ chờ Elasticsearch trả kết quả. Thread gọi không thể tiếp tục thực hiện công việc khác trong thời gian chờ.

Một thao tác **non-blocking** trả về một publisher đại diện cho kết quả sẽ đến sau:

~~~java
Mono<Product> product = reactiveRepository.findById(id);
~~~

Lời gọi trên trả về Mono. Khi subscriber yêu cầu dữ liệu, reactive client thực hiện I/O theo cơ chế bất đồng bộ. Thread không cần đứng chờ response trong lúc mạng đang xử lý.

~~~text
Blocking:
Thread A ---- gửi request ---- chờ response -------- tiếp tục
                              (thread bị giữ)

Non-blocking:
Thread A ---- đăng ký request ---- tiếp tục việc khác
                    |
                    +---- response đến sau ---- callback xử lý
~~~

Non-blocking không có nghĩa request hoàn tất ngay lập tức. Elasticsearch vẫn cần thời gian xử lý, nhưng thread không phải chờ theo cách blocking.

## 2. Vì sao blocking nguy hiểm trong WebFlux?

WebFlux thường chạy trên mô hình event loop. Một số ít thread có thể xử lý nhiều kết nối bằng cách luân phiên xử lý sự kiện sẵn sàng. Khi một event-loop thread bị block, các công việc khác được giao cho thread đó cũng phải chờ.

Ví dụ không nên:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> getProduct(@PathVariable String id) {
    Product product = blockingRepository.findById(id).orElse(null);
    return Mono.justOrEmpty(product);
}
~~~

Controller trả Mono nhưng phần truy vấn đã chạy đồng bộ trước khi Mono được tạo. Trong lúc repository chờ Elasticsearch, thread xử lý request bị block.

Hậu quả có thể gồm:

- Nhiều request chậm cùng lúc dù cluster Elasticsearch vẫn còn khả năng xử lý.
- Event loop thiếu thread sẵn sàng nhận công việc mới.
- Latency tăng đột biến khi tải đồng thời tăng.
- Timeout ở gateway hoặc client.
- Endpoint không liên quan cũng có thể chậm vì dùng chung event loop.
- Thread pool bị cạn nếu blocking diễn ra trên pool có kích thước nhỏ.

Một endpoint trả về Mono không đồng nghĩa endpoint đó đã non-blocking. Phải xem mọi thao tác bên trong pipeline và các hàm được gọi từ pipeline.

## 3. Reactive không tự động làm mọi đoạn code trở thành non-blocking

Reactor cung cấp hai kiểu publisher phổ biến:

- **Mono<T>**: phát ra tối đa một giá trị hoặc hoàn tất mà không có giá trị.
- **Flux<T>**: phát ra từ không đến nhiều giá trị.

Publisher mô tả một chuỗi xử lý. Nó không tự chuyển một hàm blocking thành non-blocking.

Ví dụ sai:

~~~java
Mono<Product> product = Mono.just(
        blockingRepository.findById(id).orElse(null)
);
~~~

Lời gọi blockingRepository được thực hiện ngay khi đánh giá đối số của Mono.just. Publisher chỉ được tạo sau khi thao tác blocking đã chạy xong.

Một ví dụ khác:

~~~java
Mono<Product> product = reactiveRepository.findById(id)
        .map(item -> blockingPricingService.loadPrice(item.getSku()));
~~~

Phần truy vấn Elasticsearch có thể non-blocking, nhưng blockingPricingService vẫn giữ thread đang chạy callback map.

Mọi hàm đồng bộ được gọi trong pipeline vẫn chạy đồng bộ trên thread thực thi pipeline, trừ khi được chuyển sang scheduler phù hợp hoặc thay bằng API bất đồng bộ.

## 4. Dùng ReactiveElasticsearchOperations thay cho API đồng bộ

Spring Data Elasticsearch có các abstraction đồng bộ và reactive riêng:

| API | Kiểu kết quả điển hình | Cách hoạt động |
|---|---|---|
| ElasticsearchOperations | Entity, SearchHits, List hoặc kết quả đồng bộ | Chờ thao tác hoàn tất |
| ReactiveElasticsearchOperations | Mono hoặc Flux | Trả publisher |
| ElasticsearchRepository | Optional, List, Page hoặc entity | Repository đồng bộ |
| ReactiveElasticsearchRepository | Mono hoặc Flux | Repository reactive |

Nếu luồng xử lý của ứng dụng là reactive, hãy dùng reactive repository hoặc ReactiveElasticsearchOperations cho các thao tác Elasticsearch.

Ví dụ service:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> save(Product product) {
        return operations.save(product);
    }

    public Flux<Product> search(Query query) {
        return operations.search(query, Product.class)
                .map(SearchHit::getContent);
    }
}
~~~

Ví dụ thể hiện cách trả publisher cho tầng gọi. Service không chờ kết quả bằng block() và cũng không tự subscribe.

Tên package và overload của ReactiveElasticsearchOperations có thể thay đổi theo phiên bản Spring Data Elasticsearch. Hãy kiểm tra API đúng với dependency của dự án. Điểm cốt lõi là dùng phương thức reactive trả Mono/Flux thay vì gọi phương thức đồng bộ rồi bọc kết quả vào publisher.

## 5. Dùng ReactiveElasticsearchRepository

Với repository, chọn interface reactive:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByStatus(String status);
}
~~~

Các phương thức trả publisher:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> findById(String id) {
        return repository.findById(id);
    }

    public Flux<Product> findActiveProducts() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Product> save(Product product) {
        return repository.save(product);
    }
}
~~~

Không nên inject cả repository đồng bộ lẫn reactive vào cùng một service rồi gọi lẫn lộn. Tên bean và kiểu interface có thể khiến code nhìn tương tự, nhưng semantics thực thi khác nhau.

Nếu một use case cần gọi nhiều hệ thống, hãy dùng API reactive tương ứng cho từng hệ thống. Chuyển Elasticsearch sang reactive nhưng vẫn gọi JPA đồng bộ hoặc RestTemplate trong cùng pipeline thì toàn luồng chưa non-blocking.

## 6. Không gọi block(), blockFirst() hoặc blockLast() trong pipeline

Các phương thức sau yêu cầu thread hiện tại chờ publisher:

- **block()**: chờ Mono phát giá trị hoặc hoàn tất.
- **blockFirst()**: chờ phần tử đầu tiên của Flux.
- **blockLast()**: chờ Flux hoàn tất và lấy phần tử cuối.

Ví dụ không nên dùng trong service reactive:

~~~java
public Mono<Product> findProduct(String id) {
    Product product = repository.findById(id).block();
    return Mono.justOrEmpty(product);
}
~~~

Cách đúng là trả publisher:

~~~java
public Mono<Product> findProduct(String id) {
    return repository.findById(id);
}
~~~

Nếu cần biến đổi kết quả, dùng operator:

~~~java
public Mono<ProductView> findProductView(String id) {
    return repository.findById(id)
            .map(ProductView::from);
}
~~~

Không gọi block trong controller WebFlux, service reactive, callback map/flatMap/doOnNext, event listener đang chạy trên reactive thread hoặc publisher khác đang được compose.

Có thể có ranh giới imperative cần lấy kết quả đồng bộ, chẳng hạn chương trình command-line, một đoạn kiểm thử hoặc adapter được thiết kế rõ ràng để gọi từ code imperative. Khi đó block nên nằm ở mép ngoài cùng của luồng, có timeout hợp lý và không chạy trên event-loop thread. Trong ứng dụng WebFlux, controller không phải nơi thích hợp để block.

## 7. Không tự subscribe() trong service

Một lỗi phổ biến là service tự gọi subscribe:

~~~java
public void save(Product product) {
    repository.save(product)
            .subscribe();
}
~~~

Cách này tạo một subscription riêng rồi trả về ngay. Caller không nhận được publisher để biết thao tác đã hoàn tất, kết hợp thao tác với công việc khác, xử lý lỗi theo luồng chung, hủy thao tác khi request bị cancel hoặc kiểm soát thứ tự.

Hãy trả publisher:

~~~java
public Mono<Product> save(Product product) {
    return repository.save(product);
}
~~~

Trong WebFlux, framework subscribe vào publisher controller trả về. Trong scheduled process hoặc command-line application, một entry point có thể cần tạo subscription rõ ràng và quản lý lifecycle, lỗi và shutdown. Đó là ranh giới ứng dụng; không phải lý do để mỗi service tự subscribe.

Tránh fire-and-forget trong service. Nếu một công việc nền cần chạy độc lập với request, hãy đưa nó vào scheduler, queue hoặc job processor có quản lý vòng đời và khả năng quan sát.

## 8. Dùng map và flatMap đúng mục đích

Trong Reactor:

- **map** dùng cho phép biến đổi đồng bộ từ T sang R.
- **flatMap** dùng khi phép biến đổi trả về một Publisher khác.
- **concatMap** xử lý từng phần tử tuần tự, giữ thứ tự.
- **flatMapSequential** cho phép thực hiện bất đồng bộ nhưng phát kết quả theo thứ tự nguồn.

Ví dụ biến đổi đồng bộ:

~~~java
Mono<ProductView> view = repository.findById(id)
        .map(ProductView::from);
~~~

Ví dụ cần gọi thêm một reactive service:

~~~java
Mono<ProductDetails> details = repository.findById(id)
        .flatMap(product ->
                inventoryService.findBySku(product.getSku())
                        .map(inventory ->
                                ProductDetails.from(product, inventory)
                        )
        );
~~~

Không dùng map rồi trả Mono lồng nhau:

~~~java
Mono<Mono<Inventory>> wrong = repository.findById(id)
        .map(product ->
                inventoryService.findBySku(product.getSku())
        );
~~~

Kiểu kết quả trở thành Mono<Mono<Inventory>>. Dùng flatMap để ghép hai publisher thành một chuỗi.

Cũng không dùng flatMap chỉ để chạy một phép tính đơn giản. Nếu hàm chỉ trả về một giá trị đồng bộ, map thường dễ đọc hơn.

## 9. Kết hợp nhiều thao tác reactive mà không block

Nếu hai thao tác độc lập, có thể chạy và kết hợp chúng bằng zip:

~~~java
Mono<Product> productMono = repository.findById(id);
Mono<Inventory> inventoryMono = inventoryService.findByProductId(id);

return Mono.zip(productMono, inventoryMono)
        .map(tuple ->
                ProductDetails.from(tuple.getT1(), tuple.getT2())
        );
~~~

Mono.zip chờ các publisher thành phần phát giá trị rồi kết hợp chúng. Các nguồn có thể tiến hành độc lập, thay vì gọi một nguồn, block lấy kết quả rồi mới gọi nguồn còn lại.

Nếu chỉ cần chờ nhiều thao tác hoàn tất mà không cần kết quả, có thể dùng Mono.when:

~~~java
return Mono.when(
        auditService.recordViewed(productId),
        metricsService.incrementProductView(productId)
).then();
~~~

Cần lưu ý lỗi của một nguồn có thể ảnh hưởng đến publisher kết hợp. Nếu một tác vụ phụ có thể thất bại mà không nên làm hỏng use case chính, hãy xử lý lỗi riêng và xác định chính sách fallback rõ ràng.

Không dùng zip cho các publisher không phát giá trị khi cần lấy kết quả từ chúng. Mono<Void> thường phù hợp với when/then hơn là zip để lấy tuple.

## 10. Chuyển đổi thư viện blocking bằng boundedElastic

Trong thực tế, có thể ứng dụng còn phụ thuộc vào thư viện đồng bộ chưa có API reactive. Khi chưa thể thay thế, hãy cô lập thao tác blocking trên **Schedulers.boundedElastic()**.

Ví dụ:

~~~java
public Mono<LegacyPrice> loadLegacyPrice(String sku) {
    return Mono.fromCallable(() ->
                    blockingPricingClient.loadPrice(sku)
            )
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Giải thích:

- Mono.fromCallable trì hoãn việc gọi hàm cho đến khi có subscription.
- subscribeOn chuyển subscription và thao tác nguồn sang scheduler được chỉ định.
- boundedElastic dành cho tác vụ có thể block và có giới hạn tài nguyên.

Kết hợp với Elasticsearch reactive:

~~~java
public Mono<ProductDetails> findDetails(String id) {
    return repository.findById(id)
            .flatMap(product ->
                    loadLegacyPrice(product.getSku())
                            .map(price ->
                                    ProductDetails.from(product, price)
                            )
            );
}
~~~

Trong luồng này, truy vấn Elasticsearch dùng reactive API; lời gọi legacy blocking được chuyển sang boundedElastic. Khi hàm legacy đang chờ, event-loop thread không bị giữ lại.

boundedElastic không biến thư viện blocking thành non-blocking. Nó chỉ cô lập thread bị chặn khỏi event loop và giới hạn số thread/queue theo cấu hình scheduler.

## 11. Vì sao phải dùng fromCallable thay vì Mono.just?

Hai đoạn code này khác nhau:

~~~java
Mono<Price> wrong = Mono.just(blockingClient.loadPrice(sku));
~~~

~~~java
Mono<Price> right = Mono.fromCallable(
        () -> blockingClient.loadPrice(sku)
).subscribeOn(Schedulers.boundedElastic());
~~~

Ở đoạn đầu, hàm blocking chạy ngay khi tạo Mono, trước cả khi subscribe. subscribeOn không thể di chuyển một thao tác đã chạy xong sang scheduler khác.

Ở đoạn thứ hai, hàm được gọi khi publisher được subscribe và có thể chạy trên boundedElastic.

Nếu cần tạo publisher dựa trên dữ liệu thay đổi theo từng subscription, có thể dùng Mono.defer:

~~~java
Mono<Price> price = Mono.defer(() ->
        Mono.fromCallable(() -> blockingClient.loadPrice(sku))
).subscribeOn(Schedulers.boundedElastic());
~~~

Không bọc một publisher reactive có sẵn trong fromCallable chỉ để đưa nó sang boundedElastic. Với nguồn reactive thật sự, hãy compose trực tiếp.

## 12. Chọn scheduler phù hợp

Reactor có một số scheduler phổ biến:

| Scheduler | Mục đích | Ví dụ |
|---|---|---|
| Schedulers.parallel() | Tính toán CPU-bound ngắn, không blocking | Biến đổi dữ liệu, tính điểm |
| Schedulers.boundedElastic() | Tác vụ blocking có giới hạn | JDBC, thư viện đồng bộ, file I/O blocking |
| Schedulers.single() | Một thread tuần tự | Công việc cần thứ tự trên một worker |
| Schedulers.immediate() | Thực thi ngay trên thread hiện tại | Trường hợp đặc biệt, không phải cách tránh block |
| Scheduler mặc định của WebFlux/Reactor Netty | Xử lý I/O và callback event loop | Network I/O non-blocking |

Không dùng boundedElastic cho mọi thao tác chỉ vì nó có vẻ an toàn. Làm vậy có thể tạo thêm thread và queue không cần thiết, che giấu việc API vốn đã reactive.

Không dùng parallel cho JDBC, Thread.sleep hoặc HTTP client blocking. parallel được thiết kế cho công việc CPU-bound, không phải để giữ thread trong lúc chờ I/O.

Nếu một thư viện blocking có tải hoặc thời gian chờ khó kiểm soát, có thể tạo bounded elastic scheduler riêng với giới hạn cụ thể:

~~~java
Scheduler legacyScheduler =
        Schedulers.newBoundedElastic(
                8,
                500,
                "legacy-pricing"
        );
~~~

Sau đó dùng:

~~~java
Mono.fromCallable(() -> legacyClient.fetch(sku))
        .subscribeOn(legacyScheduler);
~~~

Scheduler tự tạo cần được dispose khi ứng dụng shutdown, ví dụ qua bean lifecycle hoặc @PreDestroy. Không tạo scheduler mới cho từng request vì sẽ làm mất khả năng kiểm soát tài nguyên.

## 13. Hiểu subscribeOn và publishOn

Hai operator này đều có thể thay đổi thread thực thi nhưng có phạm vi khác nhau.

- **subscribeOn** ảnh hưởng đến quá trình subscribe vào nguồn và thường được dùng để chuyển thao tác nguồn blocking sang scheduler khác.
- **publishOn** chuyển các operator phía sau nó sang scheduler được chỉ định.

Ví dụ:

~~~java
Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toView);
~~~

Nguồn blocking được chạy trên boundedElastic. map sau đó tiếp tục trên luồng downstream hiện tại theo scheduler chain.

Ví dụ chuyển phép tính CPU sang parallel:

~~~java
return repository.findById(id)
        .publishOn(Schedulers.parallel())
        .map(this::calculateExpensiveScore);
~~~

Kết quả từ Elasticsearch được chuyển qua publishOn, sau đó phép tính CPU chạy trên parallel scheduler.

Nếu cần chạy một hàm blocking riêng ở giữa pipeline, có thể bọc chính hàm đó bằng fromCallable và subscribeOn boundedElastic, thay vì chuyển toàn bộ phần còn lại của chuỗi sang boundedElastic.

Đừng thêm publishOn hoặc subscribeOn theo kiểu thử ngẫu nhiên. Hãy xác định đoạn code nào đang block hoặc tiêu tốn CPU, rồi chọn scheduler tại đúng ranh giới.

## 14. Không dùng Thread.sleep trong reactive chain

Thread.sleep giữ thread hiện tại trong suốt khoảng thời gian chờ. Trong reactive pipeline, điều này có thể chặn event loop.

Ví dụ sai:

~~~java
return repository.findById(id)
        .map(product -> {
            Thread.sleep(1000);
            return product;
        });
~~~

Nếu muốn trì hoãn một giây, dùng Mono.delay:

~~~java
return Mono.delay(Duration.ofSeconds(1))
        .then(repository.findById(id));
~~~

Mono.delay tạo một publisher phát tín hiệu sau khoảng thời gian được chỉ định mà không cần giữ một thread ngủ trong suốt thời gian đó.

Nếu đang viết retry, hãy dùng retryWhen với backoff thay vì tự viết vòng lặp sleep.

## 15. Không gọi Future.get() hoặc CompletableFuture.join()

Future.get() và CompletableFuture.join() chờ kết quả đồng bộ. Chúng có thể block thread đang chạy pipeline.

Ví dụ sai:

~~~java
return repository.findById(id)
        .map(product -> {
            Price price = priceFuture.join();
            return ProductView.from(product, price);
        });
~~~

Nếu nguồn trả CompletableFuture, có thể chuyển thành publisher:

~~~java
Mono<Price> priceMono = Mono.fromFuture(
        () -> priceClient.fetchAsync(sku)
);
~~~

Sau đó kết hợp:

~~~java
return repository.findById(id)
        .flatMap(product ->
                Mono.fromFuture(
                        () -> priceClient.fetchAsync(product.getSku())
                ).map(price -> ProductView.from(product, price))
        );
~~~

Cách này chỉ phù hợp nếu API Future thực sự bất đồng bộ. Nếu phương thức tạo Future tự block trước khi trả về, cần cô lập chính lời gọi tạo Future hoặc dùng API khác.

Không gọi get()/join() chỉ để lấy kết quả của publisher. Hãy giữ kết quả dưới dạng Mono/Flux cho đến ranh giới imperative.

## 16. Tránh dùng API HTTP đồng bộ trong reactive pipeline

RestTemplate và các HTTP client đồng bộ giữ thread trong lúc chờ response. Nếu service reactive cần gọi HTTP, ưu tiên WebClient:

~~~java
public Mono<Price> findPrice(String sku) {
    return webClient.get()
            .uri("/prices/{sku}", sku)
            .retrieve()
            .bodyToMono(Price.class);
}
~~~

Sau đó compose trực tiếp:

~~~java
return repository.findById(id)
        .flatMap(product ->
                priceClient.findPrice(product.getSku())
                        .map(price ->
                                ProductDetails.from(product, price)
                        )
        );
~~~

Không gọi block trên Mono do WebClient trả về. Đoạn block này biến lời gọi WebClient non-blocking thành một thao tác chờ đồng bộ.

Nếu chưa thể thay RestTemplate, cô lập nó bằng fromCallable và boundedElastic. Kế hoạch dài hạn nên thay dần các client blocking ở những luồng có yêu cầu concurrency cao.

## 17. JDBC/JPA cũng là blocking

Spring Data JPA và JDBC thông thường là các API đồng bộ. Việc đặt chúng trong một service trả Mono không làm truy vấn database trở thành reactive.

Ví dụ không nên:

~~~java
return reactiveProductRepository.findById(id)
        .map(product -> jpaRepository.findBySku(product.getSku()));
~~~

Nếu chưa thể chuyển database sang R2DBC hoặc API reactive phù hợp, cô lập truy vấn JPA:

~~~java
Mono<LegacyRecord> legacyRecord =
        Mono.fromCallable(() ->
                jpaRepository.findBySku(sku)
        )
        .subscribeOn(Schedulers.boundedElastic());
~~~

Kết hợp với publisher Elasticsearch:

~~~java
return reactiveProductRepository.findById(id)
        .flatMap(product ->
                Mono.fromCallable(() ->
                        jpaRepository.findBySku(product.getSku())
                )
                .subscribeOn(Schedulers.boundedElastic())
                .map(record ->
                        ProductDetails.from(product, record)
                )
        );
~~~

boundedElastic có giới hạn. Nếu lưu lượng tăng cao, hàng đợi blocking task cũng có thể tăng và tạo latency. Theo dõi scheduler và cân nhắc chuyển sang database reactive nếu use case cần khả năng mở rộng end-to-end.

## 18. File I/O và xử lý dữ liệu nặng

Một số thao tác file như Files.readString, Files.writeString hoặc InputStream.read là blocking. Không gọi chúng trực tiếp trong map hoặc doOnNext của pipeline đang chạy trên event loop.

Ví dụ cô lập thao tác đọc file:

~~~java
Mono<String> content = Mono.fromCallable(
        () -> Files.readString(path)
).subscribeOn(Schedulers.boundedElastic());
~~~

Nếu framework hoặc thư viện cung cấp API file reactive/asynchronous, có thể dùng API đó để tránh thread chờ I/O.

Cũng cần phân biệt I/O blocking với tính toán CPU:

- Đọc file đồng bộ: boundedElastic hoặc API file asynchronous.
- Parse một JSON rất lớn hoặc tính toán tốn CPU: cân nhắc parallel hoặc worker CPU riêng.
- Gọi HTTP đồng bộ: boundedElastic hoặc thay bằng WebClient.
- Chờ database đồng bộ: boundedElastic hoặc chuyển sang R2DBC.

Không chuyển mọi công việc nặng sang boundedElastic. CPU-bound task chiếm thread lâu cũng có thể làm scheduler dành cho blocking bị bão hòa.

## 19. Backpressure và xử lý Flux có kiểm soát

**Backpressure** là cơ chế để subscriber điều khiển lượng dữ liệu mà nó sẵn sàng nhận. Nó giúp tránh việc producer phát dữ liệu nhanh hơn khả năng downstream xử lý.

Ví dụ xử lý tuần tự:

~~~java
return productRepository.findByStatus("ACTIVE")
        .concatMap(product ->
                enrichmentService.enrich(product)
        );
~~~

concatMap xử lý publisher của từng phần tử theo thứ tự, không tạo nhiều tác vụ đồng thời không giới hạn.

Nếu muốn xử lý song song với mức concurrency cụ thể:

~~~java
return productRepository.findByStatus("ACTIVE")
        .flatMap(
                product -> enrichmentService.enrich(product),
                8
        );
~~~

Con số 8 chỉ là ví dụ. Chọn concurrency theo khả năng Elasticsearch, dịch vụ phụ trợ, connection pool và giới hạn downstream.

Nếu dùng flatMap mà không đặt concurrency phù hợp, một luồng nhiều phần tử có thể tạo quá nhiều công việc cùng lúc. Backpressure không thay thế việc thiết kế giới hạn concurrency cho từng dependency.

### limitRate không phải pagination của Elasticsearch

Có thể dùng limitRate để điều tiết demand ở phía Reactor:

~~~java
return productRepository.findByStatus("ACTIVE")
        .limitRate(64);
~~~

Tuy nhiên, limitRate không tự bảo đảm Elasticsearch chỉ đọc một trang gồm 64 tài liệu hoặc tự tạo search_after. Cách fetch dữ liệu từ cluster phụ thuộc implementation của reactive API và query đang dùng.

Với dữ liệu lớn, hãy chọn chiến lược pagination/scroll/search_after phù hợp với API Spring Data Elasticsearch đang dùng. Không gọi collectList trên hàng triệu kết quả nếu ứng dụng chỉ cần xử lý tuần tự từng document.

## 20. Tránh collectList không cần thiết

collectList gom toàn bộ phần tử của Flux vào một List rồi chỉ phát ra khi nguồn hoàn tất.

Ví dụ:

~~~java
Mono<List<Product>> allProducts =
        productRepository.findByStatus("ACTIVE")
                .collectList();
~~~

Cách này hợp lý khi tập dữ liệu nhỏ và use case thực sự cần toàn bộ danh sách. Nhưng với tập dữ liệu lớn, nó có thể giữ nhiều object trong heap, tăng thời gian trước khi phần tử đầu tiên được xử lý, tăng áp lực GC và tạo nguy cơ OutOfMemoryError.

Nếu chỉ cần biến đổi và ghi từng phần tử, có thể compose trực tiếp:

~~~java
return productRepository.findByStatus("ACTIVE")
        .flatMap(product ->
                exportService.write(product)
        )
        .then();
~~~

Nếu cần batch, gom theo nhóm có giới hạn:

~~~java
return productRepository.findByStatus("ACTIVE")
        .buffer(100)
        .concatMap(batch ->
                bulkWriter.write(batch)
        )
        .then();
~~~

buffer(100) tạo các nhóm tối đa 100 phần tử. Cần cân nhắc trường hợp batch cuối cùng có ít hơn 100 item và xử lý lỗi từng phần tử nếu bulk có partial success.

## 21. Không chặn thread bằng synchronized hoặc lock

Các đoạn code dùng synchronized, ReentrantLock.lock() hoặc semaphore acquire() có thể giữ thread chờ. Trong reactive chain, tránh các khóa blocking nếu không thực sự cần.

Ví dụ:

~~~java
return repository.findById(id)
        .map(product -> {
            synchronized (sharedState) {
                sharedState.update(product);
            }
            return product;
        });
~~~

Nếu critical section rất ngắn, đồng bộ có thể vẫn cần thiết trong một số thiết kế, nhưng nó vẫn giữ thread trong lúc chờ khóa. Khi có contention, event loop có thể bị ảnh hưởng.

Cân nhắc:

- Thiết kế immutable state.
- Dùng cấu trúc dữ liệu concurrent phù hợp.
- Dùng reactive serialization như concatMap khi cần tuần tự hóa thao tác.
- Dùng một scheduler/actor chuyên trách cho state cần cập nhật tuần tự.
- Tránh giữ lock trong lúc thực hiện network I/O.

Không giữ synchronized lock qua một đoạn gọi Elasticsearch hoặc HTTP. Thời gian chờ không xác định sẽ làm các request khác chờ theo.

## 22. Error handling và retry trong reactive pipeline

Reactive pipeline biểu diễn lỗi như một terminal signal. Có thể xử lý lỗi bằng onErrorResume, onErrorMap, doOnError hoặc retryWhen.

Ví dụ chuyển lỗi sang exception nghiệp vụ:

~~~java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ProductNotFoundException(id)
        ))
        .onErrorMap(
                ElasticsearchException.class,
                ProductSearchException::new
        );
~~~

Ví dụ retry có backoff cho lỗi tạm thời:

~~~java
return repository.findById(id)
        .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                        .filter(this::isTransientFailure)
        );
~~~

Retry có nghĩa là subscribe lại vào publisher nguồn. Hãy cân nhắc:

- Thao tác có idempotent không?
- Lỗi có thực sự tạm thời không?
- Có giới hạn số lần và tổng thời gian không?
- Retry có làm tăng tải khi cluster đang quá tải không?
- Request trước có thể đã được xử lý nhưng response bị mất không?

Không retry mọi exception. Lỗi mapping, validation hoặc unauthorized thường cần sửa dữ liệu/cấu hình. Retry 429 hoặc một số lỗi 5xx có thể hợp lý với backoff và giới hạn.

Nếu cần ghi log lỗi mà vẫn giữ nguyên signal, có thể dùng doOnError:

~~~java
return repository.findById(id)
        .doOnError(error ->
                log.warn("Unable to load product {}", id, error)
        );
~~~

doOnError là side effect đồng bộ. Không thực hiện I/O blocking trong đó.

## 23. Timeout và cancellation

Có thể đặt timeout cho publisher:

~~~java
return repository.findById(id)
        .timeout(Duration.ofSeconds(3));
~~~

Timeout giúp giới hạn thời gian caller chờ kết quả. Tuy nhiên, timeout ở tầng Reactor không luôn chứng minh Elasticsearch chưa xử lý request. Tùy thời điểm và transport, request có thể đã được gửi hoặc server có thể đã thực hiện thao tác.

Với thao tác ghi, cần xét idempotency và đối chiếu trạng thái nếu timeout làm kết quả không rõ.

Cancellation xảy ra khi subscriber không còn quan tâm đến kết quả, ví dụ browser đóng kết nối hoặc request bị hủy. Reactive chain có thể truyền tín hiệu cancel về upstream để giải phóng tài nguyên hoặc hủy request nếu transport hỗ trợ.

Không nuốt cancellation bằng cách tạo subscription riêng bên trong service. Khi service trả publisher cho controller, framework có thể quản lý cancellation xuyên suốt chuỗi.

Dùng doFinally khi cần quan sát kết thúc theo signal:

~~~java
return repository.findById(id)
        .doFinally(signal ->
                log.debug("Product lookup finished: {}", signal)
        );
~~~

Các signal có thể gồm complete, error hoặc cancel. Không giả định mọi request đều hoàn tất bình thường.

## 24. Context propagation và ThreadLocal

Trong ứng dụng imperative, code thường dựa vào ThreadLocal để lưu request ID, security principal hoặc MDC logging context. Reactive pipeline có thể chuyển giữa nhiều thread, vì vậy ThreadLocal không phải nơi đáng tin cậy để lưu context theo request.

Reactor cung cấp **Context** gắn với subscription. Các tích hợp Spring Security reactive và Micrometer Context Propagation có thể giúp truyền thông tin bảo mật hoặc quan sát qua các bước chuyển thread.

Không nên:

- Đọc user hiện tại từ ThreadLocal tùy ý sau khi pipeline đã chuyển scheduler.
- Lưu request-scoped data vào static mutable field.
- Giả định cùng một thread chạy toàn bộ pipeline.
- Dùng MDC như thể nó tự động đi theo mọi operator trong mọi cấu hình.

Với Spring Security WebFlux, dùng reactive security context APIs phù hợp thay vì dựa vào SecurityContextHolder kiểu imperative. Với trace ID và logging context, bật cơ chế context propagation phù hợp với phiên bản Spring/Reactor đang dùng.

Ví dụ truy cập Reactor Context:

~~~java
Mono<String> currentRequestId =
        Mono.deferContextual(context ->
                Mono.just(context.get("requestId"))
        );
~~~

Context được cung cấp khi subscribe:

~~~java
currentRequestId.contextWrite(context ->
        context.put("requestId", "req-1001")
);
~~~

Context là dữ liệu gắn với subscription, không phải biến global. Tránh đưa dữ liệu lớn hoặc mutable object vào Context.

## 25. Controller WebFlux nên trả Mono/Flux

Controller WebFlux nên trả trực tiếp publisher:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return service.findById(id);
    }

    @GetMapping
    public Flux<Product> findActive() {
        return service.findActiveProducts();
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Mono<Product> body) {
        return body.flatMap(service::save);
    }
}
~~~

WebFlux framework sẽ subscribe và ghi kết quả theo reactive response handling. Không cần gọi subscribe hoặc block trong controller.

Nếu cần biến đổi HTTP status hoặc header theo kết quả, có thể dùng ResponseEntity reactive:

~~~java
public Mono<ResponseEntity<Product>> findById(String id) {
    return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Không trả Mono chứa một publisher khác. Hãy dùng flatMap khi một bước tạo ra publisher tiếp theo.

## 26. Trộn Spring MVC và WebFlux

Một ứng dụng Spring có thể dùng Spring MVC hoặc WebFlux. Cách xử lý publisher và thread model của hai stack khác nhau.

- WebFlux được thiết kế cho reactive request handling.
- Spring MVC có thể hỗ trợ return Mono/Flux thông qua asynchronous request processing, nhưng điều đó không tự biến mọi dependency đồng bộ thành non-blocking.
- Một controller MVC gọi JPA đồng bộ vẫn thực hiện blocking I/O.
- Một service reactive được gọi từ code imperative có thể cần adapter ở ranh giới.

Không chỉ nhìn vào kiểu return Mono để kết luận toàn hệ thống đang chạy non-blocking. Hãy xác định web stack thực tế, server, client và mọi dependency được gọi trong đường request.

Nếu ứng dụng dùng MVC và nhiều dependency blocking, việc chuyển riêng một repository sang reactive có thể làm code phức tạp hơn mà không mang lại lợi ích tương xứng. Chọn reactive end-to-end cho các đường xử lý có lợi thế về concurrency và I/O.

## 27. BlockHound giúp phát hiện thao tác blocking

**BlockHound** là công cụ có thể phát hiện một số lời gọi blocking chạy trên thread được đánh dấu là non-blocking, chẳng hạn Reactor non-blocking thread.

Trong môi trường test, có thể cài đặt BlockHound:

~~~java
import org.junit.jupiter.api.BeforeAll;
import reactor.blockhound.BlockHound;

class ReactiveBlockingTest {

    @BeforeAll
    static void installBlockHound() {
        BlockHound.install();
    }
}
~~~

Nếu pipeline gọi Thread.sleep hoặc một API blocking được BlockHound instrument, test có thể thất bại với lỗi phát hiện blocking operation.

BlockHound không phát hiện mọi dạng blocking trong mọi thư viện. Một số thư viện cần integration hoặc instrumentation bổ sung; cũng có thể có false positive hoặc giới hạn tương thích theo JDK, Reactor và framework version.

Dùng BlockHound như một công cụ hỗ trợ phát hiện, kết hợp với code review và kiểm thử tải. Không coi việc test qua BlockHound là bằng chứng tuyệt đối rằng toàn hệ thống không có blocking.

## 28. Kiểm thử reactive bằng StepVerifier

Không cần block để kiểm thử publisher. Reactor cung cấp **StepVerifier** để xác nhận các signal theo thứ tự.

Ví dụ:

~~~java
@Test
void findsProductById() {
    Mono<Product> result = service.findById("p-1001");

    StepVerifier.create(result)
            .expectNextMatches(product ->
                    "p-1001".equals(product.getId())
            )
            .verifyComplete();
}
~~~

Kiểm tra trường hợp không có dữ liệu:

~~~java
@Test
void completesEmptyWhenProductDoesNotExist() {
    Mono<Product> result = service.findById("missing");

    StepVerifier.create(result)
            .verifyComplete();
}
~~~

Kiểm tra lỗi:

~~~java
@Test
void propagatesNotFoundError() {
    Mono<Product> result = service.findRequired("missing");

    StepVerifier.create(result)
            .expectError(ProductNotFoundException.class)
            .verify();
}
~~~

StepVerifier subscribe vào publisher và kiểm tra tín hiệu. Nó giúp test không cần gọi block trong code nghiệp vụ.

### Kiểm thử scheduler và thời gian

Khi test retry/backoff hoặc delay, có thể dùng virtual time của Reactor để tránh chờ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofHours(1))
)
.thenAwait(Duration.ofHours(1))
.expectNext(0L)
.verifyComplete();
~~~

Publisher cần được tạo bên trong supplier của withVirtualTime để scheduler ảo được áp dụng đúng lúc.

## 29. Kiểm thử integration với Elasticsearch reactive

Unit test và StepVerifier có thể xác nhận composition, nhưng không chứng minh reactive Elasticsearch client hoạt động đúng với cluster.

Integration test nên kiểm tra:

1. Application context khởi tạo được reactive client và ReactiveElasticsearchOperations.
2. Lưu entity bằng reactive repository.
3. Đọc lại entity qua reactive search hoặc findById.
4. Xác nhận mapping và conversion.
5. Kiểm tra lỗi mapping hoặc document không tồn tại.
6. Kiểm tra timeout/cancellation theo khả năng môi trường.
7. Xác nhận không gọi API đồng bộ trên đường reactive quan trọng.
8. Dùng BlockHound nếu môi trường test tương thích.

Khi kiểm tra thời gian thực thi, không nên chỉ đo một request đơn lẻ. Hãy tạo tải đồng thời và theo dõi event-loop thread, scheduler queue, latency và connection pool.

Nếu dùng Testcontainers hoặc cluster test riêng, chọn phiên bản Elasticsearch tương thích với Spring Data Elasticsearch và client của ứng dụng. Không giả định một cluster bất kỳ sẽ tương thích với dependency hiện tại.

## 30. Theo dõi scheduler và event loop

Để phát hiện blocking trong production, cần quan sát nhiều lớp:

- Latency của endpoint.
- Số lượng request đang chờ.
- Thread event loop bận hoặc không phản hồi.
- Số thread và queue của boundedElastic.
- Số task bị reject hoặc chờ lâu.
- Elasticsearch request latency.
- Connection pool usage.
- Timeout, cancellation và error rate.
- CPU, heap và garbage collection.

Nếu latency tăng nhưng Elasticsearch response time ổn định, nguyên nhân có thể nằm ở xử lý phía ứng dụng, thread pool bão hòa hoặc một dependency blocking.

Nếu boundedElastic queue tăng liên tục, có thể lượng blocking work vượt khả năng xử lý hoặc một thư viện đang chờ quá lâu. Không chỉ tăng giới hạn thread để che vấn đề; hãy kiểm tra nguồn blocking, timeout và concurrency.

## 31. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Cách sửa |
|---|---|---|
| block() trong controller | Chặn event loop | Trả Mono/Flux |
| block() trong service | Phá vỡ composition và cancellation | Trả publisher |
| Mono.just(blockingCall()) | Hàm chạy trước subscription | fromCallable + boundedElastic |
| subscribe() trong service | Tách luồng xử lý khỏi caller | Trả publisher |
| Thread.sleep() | Giữ thread trong lúc chờ | Mono.delay hoặc retry backoff |
| Future.get()/join() | Chờ đồng bộ | Mono.fromFuture |
| RestTemplate trong reactive chain | HTTP blocking | WebClient |
| JPA/JDBC trong map | Database I/O blocking | API reactive hoặc boundedElastic |
| Dùng parallel cho I/O blocking | Giữ CPU worker trong lúc chờ | boundedElastic hoặc client reactive |
| Dùng boundedElastic cho mọi thứ | Tạo queue/thread không cần thiết | Chỉ cô lập đoạn blocking |
| collectList trên tập lớn | Giữ toàn bộ dữ liệu trong heap | Flux processing, buffer giới hạn |
| flatMap không giới hạn hợp lý | Quá nhiều request đồng thời | Đặt concurrency hoặc concatMap |
| ThreadLocal cho request context | Context mất khi đổi thread | Reactor Context và context propagation |
| I/O trong doOnNext | Side effect blocking trên thread hiện tại | Compose publisher bằng flatMap |
| Gọi client đồng bộ trực tiếp | Bỏ qua reactive client | Dùng ReactiveElasticsearchOperations/client |

## 32. Quy trình chuyển một đoạn blocking sang reactive

Khi phát hiện một thao tác blocking, có thể làm theo trình tự:

1. **Tìm điểm block.** Kiểm tra block(), sleep, get(), join(), API đồng bộ và các hàm I/O.
2. **Xác định nguồn blocking.** Elasticsearch sync, JDBC/JPA, HTTP client, file system hay thư viện bên ngoài.
3. **Tìm API reactive/asynchronous tương ứng.** Ví dụ ReactiveElasticsearchOperations, reactive repository, WebClient hoặc R2DBC.
4. **Thay đổi kiểu trả về.** Giữ Mono/Flux xuyên suốt service và controller.
5. **Dùng operator phù hợp.** map cho biến đổi đồng bộ, flatMap cho publisher tiếp theo, concatMap khi cần tuần tự.
6. **Cô lập phần chưa thể thay thế.** fromCallable/fromRunnable kết hợp boundedElastic.
7. **Đặt giới hạn concurrency.** Tránh tạo quá nhiều tác vụ phụ đồng thời.
8. **Thiết kế lỗi và retry.** Chỉ retry lỗi phù hợp, bảo đảm idempotency.
9. **Giữ cancellation và context.** Không subscribe nội bộ và tránh phụ thuộc ThreadLocal.
10. **Kiểm thử.** Dùng StepVerifier, integration test và BlockHound nếu phù hợp.
11. **Đo tải.** Kiểm tra event loop, scheduler, latency và memory khi có concurrency thực tế.

Ví dụ trước và sau:

~~~java
// Blocking
public ProductView getProduct(String id) {
    Product product = blockingRepository.findById(id).orElseThrow();
    Price price = blockingPriceClient.fetch(product.getSku());
    return ProductView.from(product, price);
}
~~~

~~~java
// Reactive
public Mono<ProductView> getProduct(String id) {
    return reactiveRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .flatMap(product ->
                    webClient.get()
                            .uri("/prices/{sku}", product.getSku())
                            .retrieve()
                            .bodyToMono(Price.class)
                            .map(price ->
                                    ProductView.from(product, price)
                            )
            );
}
~~~

Nếu price client chưa có API reactive, có thể tạm thời cô lập:

~~~java
private Mono<Price> fetchPrice(String sku) {
    return Mono.fromCallable(() ->
                    blockingPriceClient.fetch(sku)
            )
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Sau đó dùng fetchPrice trong flatMap và có thể thay implementation bằng WebClient mà không thay đổi hợp đồng service.

## 33. Checklist khi thiết kế reactive flow

- Dùng ReactiveElasticsearchOperations hoặc ReactiveElasticsearchRepository.
- Không gọi ElasticsearchOperations đồng bộ trong reactive chain.
- Không gọi block(), blockFirst() hoặc blockLast() trên event loop.
- Không tự subscribe trong controller hoặc service.
- Không gọi Thread.sleep, Future.get hoặc CompletableFuture.join.
- Dùng WebClient thay cho HTTP client blocking.
- Dùng R2DBC hoặc cô lập JDBC/JPA trên boundedElastic khi cần.
- Dùng fromCallable cho hàm blocking để lời gọi được trì hoãn đến subscription.
- Dùng boundedElastic cho I/O blocking và parallel cho CPU-bound work.
- Không chuyển toàn bộ pipeline sang scheduler khác nếu chỉ một đoạn cần cô lập.
- Dùng map/flatMap/concatMap theo semantics phù hợp.
- Giới hạn concurrency và tránh collectList cho tập dữ liệu lớn.
- Đặt timeout và retry theo chính sách có giới hạn.
- Bảo đảm thao tác ghi an toàn khi retry.
- Không dựa vào ThreadLocal để truyền request context.
- Kiểm thử bằng StepVerifier và integration test.
- Dùng BlockHound khi tương thích để phát hiện blocking call.
- Theo dõi event loop, scheduler queue, latency và timeout.

Một luồng Reactive của Spring Data Elasticsearch chỉ giữ được lợi ích non-blocking khi mọi thao tác I/O trong đường xử lý đều dùng API bất đồng bộ hoặc được cô lập đúng cách. Dùng reactive repository/operations cho Elasticsearch, compose publisher bằng map và flatMap, trả Mono/Flux về caller và tránh block hoặc subscribe nội bộ. Khi phải gọi thư viện đồng bộ, bọc lời gọi bằng fromCallable và chạy trên boundedElastic với giới hạn phù hợp; không dùng parallel để chờ I/O. Kết hợp backpressure, giới hạn concurrency, cancellation, context propagation và kiểm thử sẽ giúp ứng dụng duy trì khả năng phục vụ nhiều request mà không làm nghẽn event loop.
