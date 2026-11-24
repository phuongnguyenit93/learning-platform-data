# Lỗi phát sinh trước khi tạo Publisher và lỗi phát trên luồng

Trong ứng dụng Spring WebFlux, một phương thức trả về **Mono** hoặc **Flux** có thể gặp lỗi ở hai thời điểm khác nhau: lỗi xảy ra đồng bộ trước khi phương thức tạo và trả về Publisher, hoặc lỗi được phát ra trong quá trình Publisher được subscribe và thực thi. Hai trường hợp này có cách xử lý khác nhau khi tích hợp Spring Cloud CircuitBreaker với Resilience4j.

Circuit Breaker reactive bảo vệ các tín hiệu được phát ra từ Publisher mà nó bọc. Nếu mã nguồn ném ngoại lệ trước khi tạo Publisher và trước khi gọi Circuit Breaker, reactive pipeline chưa tồn tại để nhận lỗi. Ngược lại, nếu lỗi được biểu diễn bằng tín hiệu **onError**, bộ ngắt có thể quan sát kết quả, ghi nhận lỗi theo cấu hình và kích hoạt fallback. Hiểu đúng ranh giới này giúp tránh bỏ sót lỗi, tránh đếm nhầm lỗi nghiệp vụ vào failure rate và giữ cho API reactive luôn trả về Publisher nhất quán.

## 1. Hai thời điểm lỗi khác nhau

Một phương thức reactive không có nghĩa mọi dòng code bên trong đều tự động chạy bất đồng bộ. Các biểu thức Java vẫn được đánh giá ngay khi phương thức được gọi, trừ khi chúng được đặt trong một toán tử trì hoãn như **Mono.defer** hoặc **Mono.fromCallable**.

Xét hai tình huống:

~~~java
Mono<Product> findProduct(String id) {
    Product product = catalogClient.findImmediately(id);
    return Mono.just(product);
}
~~~

Nếu **findImmediately** ném ngoại lệ, ngoại lệ xuất hiện ngay trong lúc gọi **findProduct**. Phương thức chưa trả về một Mono; caller nhận ngoại lệ đồng bộ và không có Publisher để subscribe.

Trong tình huống khác:

~~~java
Mono<Product> findProduct(String id) {
    return Mono.fromCallable(() -> catalogClient.findImmediately(id));
}
~~~

Lời gọi client được trì hoãn đến lúc subscribe. Nếu nó ném ngoại lệ, Reactor chuyển ngoại lệ thành tín hiệu **onError** trên Publisher. Caller nhận được một Mono và có thể xử lý lỗi bằng các toán tử reactive.

| Tình huống | Thời điểm xảy ra | Kết quả quan sát được |
|---|---|---|
| Ném ngoại lệ trước khi tạo Publisher | Ngay khi gọi phương thức Java | Phương thức không trả về Mono/Flux |
| Trả về **Mono.error(exception)** | Khi Publisher được subscribe | Publisher phát tín hiệu onError |
| Ngoại lệ xảy ra trong **Mono.defer** | Khi supplier được gọi lúc subscribe | Reactor chuyển ngoại lệ thành onError |
| Ngoại lệ từ HTTP request khi WebClient thực thi | Trong quá trình subscribe và trao đổi dữ liệu | Publisher phát onError |
| Ngoại lệ trong toán tử **map** | Khi phần tử đi qua toán tử | Publisher phát onError |

Điểm mấu chốt: một ngoại lệ Java chỉ trở thành lỗi của reactive stream khi nó được chuyển thành tín hiệu lỗi của Publisher. Chỉ khai báo kiểu trả về là Mono hoặc Flux chưa đủ để bảo đảm điều đó.

## 2. Lỗi đồng bộ trước khi tạo Publisher

Lỗi trước khi tạo Publisher thường đến từ kiểm tra tham số, truy cập đối tượng null, dựng URI, chuyển đổi dữ liệu ngay trong lúc gọi phương thức hoặc gọi một API có thể ném ngoại lệ đồng bộ.

Ví dụ:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        throw new IllegalArgumentException("id không được để trống");
    }

    return catalogClient.getProduct(id);
}
~~~

Khi **id** không hợp lệ, phương thức ném **IllegalArgumentException** ngay lập tức. Caller không nhận được Mono để gọi **onErrorResume**, **doOnError** hoặc subscribe. Nếu lỗi này xảy ra trước lời gọi **ReactiveCircuitBreaker.run**, fallback của Circuit Breaker cũng không thể xử lý nó.

Trong API reactive, nên biểu diễn lỗi đầu vào bằng một Publisher lỗi:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(
            new IllegalArgumentException("id không được để trống")
        );
    }

    return catalogClient.getProduct(id);
}
~~~

Phương thức luôn trả về Mono. Với đầu vào không hợp lệ, Mono phát **onError** khi được subscribe. Tuy nhiên, nếu kiểm tra này nằm trước Circuit Breaker, lỗi đầu vào không đi qua bộ ngắt và không làm tăng failure rate của dịch vụ Catalog.

Đây thường là cách phân chia hợp lý: lỗi xác thực request thuộc trách nhiệm của ứng dụng gọi; Circuit Breaker chỉ đo lường thao tác phụ thuộc mà nó được giao bảo vệ. Không nên để một request sai dữ liệu làm bộ ngắt hiểu nhầm rằng dịch vụ Catalog đang gặp sự cố.

## 3. Dùng Mono.error để biểu diễn lỗi trong reactive pipeline

**Mono.error** tạo một Publisher kết thúc bằng tín hiệu onError. Nó hữu ích khi một điều kiện đã được phát hiện đồng bộ nhưng ứng dụng muốn giữ hợp đồng trả về reactive.

Ví dụ:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(new InvalidProductIdException(id));
    }

    return catalogClient.getProduct(id);
}
~~~

Lỗi được phát ra khi có subscription, chứ không bị ném ra ngoài phương thức như một ngoại lệ đồng bộ. Các thành phần ở phía sau có thể dùng toán tử reactive để xử lý:

~~~java
return getProduct(id)
    .onErrorResume(
        InvalidProductIdException.class,
        error -> Mono.just(Product.unavailable(id))
    );
~~~

**Mono.error** không tự quyết định lỗi có được Circuit Breaker ghi nhận hay không. Vị trí Publisher lỗi nằm so với **ReactiveCircuitBreaker.run** mới quyết định bộ ngắt có quan sát lỗi đó hay không. Nếu Mono.error được truyền vào Publisher mà Circuit Breaker bảo vệ, lỗi có thể được ghi nhận theo cấu hình exception của Resilience4j. Nếu lỗi được trả về trước khi gọi bộ ngắt, nó nằm ngoài phạm vi đo lường của bộ ngắt.

Vì vậy, hãy phân biệt hai mục tiêu: chuyển lỗi thành tín hiệu reactive để giữ API nhất quán và đưa lỗi vào phạm vi Circuit Breaker để đánh giá sức khỏe dependency. Không phải mọi lỗi reactive đều nên được tính là lỗi của dịch vụ phụ thuộc.

## 4. Dùng Mono.defer để bắt ngoại lệ khi tạo Publisher nguồn

Một số client hoặc hàm hỗ trợ có thể ném ngoại lệ ngay khi phương thức được gọi để tạo Publisher. Nếu lời gọi đó nằm trực tiếp trong tham số của **run**, ngoại lệ có thể xảy ra trước khi Circuit Breaker nhận được Publisher:

~~~java
return reactiveCircuitBreakerFactory.create("catalog").run(
    catalogClient.getProduct(id),
    error -> fallback(id, error)
);
~~~

Java phải đánh giá **catalogClient.getProduct(id)** trước khi gọi **run**. Nếu phương thức client ném ngoại lệ đồng bộ trong lúc dựng Publisher, lời gọi **run** chưa được thực hiện và fallback không có cơ hội nhận lỗi đó.

Đặt thao tác tạo Publisher bên trong **Mono.defer** để trì hoãn việc gọi client đến lúc subscribe:

~~~java
Mono<Product> getProduct(String id) {
    return reactiveCircuitBreakerFactory.create("catalog").run(
        Mono.defer(() -> catalogClient.getProduct(id)),
        error -> fallback(id, error)
    );
}
~~~

Khi subscribe, supplier của **Mono.defer** được thực thi. Nếu **catalogClient.getProduct(id)** ném ngoại lệ đồng bộ, Reactor chuyển ngoại lệ thành tín hiệu onError. Publisher đã được truyền qua Circuit Breaker, vì vậy bộ ngắt có thể quan sát lỗi và áp dụng fallback theo cấu hình.

**Mono.defer** đặc biệt hữu ích khi:

- Phương thức tạo Publisher có thể ném ngoại lệ đồng bộ.
- Cần trì hoãn việc tạo request cho đến khi có subscription.
- Cần tạo Publisher mới cho mỗi lần subscribe.
- Muốn đưa lỗi trong giai đoạn dựng Publisher nguồn vào reactive pipeline được bảo vệ.

Lưu ý: **Mono.defer** chỉ trì hoãn thời điểm gọi supplier và chuyển ngoại lệ thành tín hiệu reactive. Nó không biến một API blocking thành non-blocking. Nếu supplier gọi một client đồng bộ, thao tác đó vẫn chặn thread đang subscribe.

## 5. Đặt validation ngoài Circuit Breaker, đặt lời gọi dependency bên trong

Một service reactive thường cần vừa kiểm tra request vừa bảo vệ lời gọi đến dịch vụ phụ thuộc. Có thể tổ chức ranh giới như sau:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class CatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductMapper productMapper;
    private final ProductCache productCache;

    CatalogService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductMapper productMapper,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productMapper = productMapper;
        this.productCache = productCache;
    }

    Mono<Product> getProduct(String id) {
        if (id == null || id.isBlank()) {
            return Mono.error(
                new InvalidProductIdException(id)
            );
        }

        return circuitBreakerFactory.create("catalog").run(
            Mono.defer(() -> catalogClient.getProduct(id))
                .map(productMapper::toDomain),
            error -> fallback(id, error)
        );
    }

    private Mono<Product> fallback(String id, Throwable error) {
        if (error instanceof CallNotPermittedException) {
            log.warn("Circuit Breaker catalog từ chối lời gọi, id={}", id);
        } else {
            log.warn("Không lấy được sản phẩm từ Catalog, id={}", id, error);
        }

        return productCache.findById(id)
            .switchIfEmpty(Mono.error(
                new CatalogUnavailableException(id, error)
            ));
    }
}
~~~

Ví dụ phân chia trách nhiệm thành ba phần:

1. **Validation:** kiểm tra ID trước khi tạo Circuit Breaker. Đầu vào không hợp lệ được trả thành Mono.error và không được tính là lỗi dependency.
2. **Publisher nguồn:** **Mono.defer** trì hoãn việc gọi client. Ngoại lệ đồng bộ phát sinh trong quá trình tạo Publisher được chuyển thành onError.
3. **Fallback:** nhận lỗi từ Circuit Breaker và trả về dữ liệu cache hoặc một lỗi nghiệp vụ phù hợp.

Phép **map** trong ví dụ nằm bên trong Publisher được bảo vệ. Nếu mapper ném ngoại lệ khi xử lý response, lỗi đó cũng phát thành onError và có thể được Circuit Breaker ghi nhận. Đây là lựa chọn phù hợp nếu response không thể ánh xạ cho thấy hợp đồng của dịch vụ Catalog không đáp ứng yêu cầu.

Nếu lỗi mapper là lỗi lập trình nội bộ và không nên ảnh hưởng đến đánh giá sức khỏe Catalog, hãy đặt mapping sau khi Circuit Breaker hoàn tất. Khi đó bộ ngắt chỉ đo lường lời gọi client; lỗi mapping được xử lý ở tầng ứng dụng.

## 6. Phân biệt lỗi phát trên luồng với lỗi đã được phục hồi

Reactive Streams truyền lỗi qua tín hiệu **onError**. Một toán tử có thể quan sát lỗi, chuyển đổi lỗi hoặc phục hồi bằng một Publisher khác.

| Toán tử | Hành vi | Circuit Breaker phía ngoài quan sát gì? |
|---|---|---|
| **doOnError** | Chỉ quan sát lỗi, không phục hồi | Vẫn nhận onError |
| **onErrorMap** | Chuyển loại ngoại lệ, giữ tín hiệu lỗi | Vẫn nhận onError với ngoại lệ mới |
| **onErrorResume** | Thay lỗi bằng Publisher khác | Có thể nhận onNext/onComplete thành công |
| **onErrorReturn** | Thay lỗi bằng một giá trị dự phòng | Nhận giá trị và hoàn tất bình thường |
| **retry** | Subscribe lại Publisher nguồn theo chính sách | Kết quả cuối cùng được chuyển tới lớp bảo vệ |
| **Mono.error** | Tạo Publisher phát onError | Nhận onError nếu nằm trong phạm vi bảo vệ |

Vị trí đặt **onErrorResume** rất quan trọng. Nếu phục hồi lỗi ngay bên trong Publisher nguồn trước khi đưa vào Circuit Breaker, bộ ngắt có thể chỉ thấy kết quả thành công:

~~~java
Mono<Product> source = Mono.defer(() -> catalogClient.getProduct(id))
    .onErrorResume(error -> productCache.findById(id));

return circuitBreakerFactory.create("catalog").run(
    source,
    error -> Mono.error(error)
);
~~~

Trong ví dụ này, lỗi từ Catalog được xử lý bởi **onErrorResume** trước khi tới Circuit Breaker. Nếu cache trả dữ liệu, Circuit Breaker quan sát một Publisher hoàn tất bình thường và không ghi nhận lỗi ban đầu.

Nếu muốn Circuit Breaker ghi nhận lỗi trước rồi mới chạy fallback, truyền Publisher nguồn chưa phục hồi vào **run** và cung cấp fallback ở tham số thứ hai:

~~~java
Mono<Product> source =
    Mono.defer(() -> catalogClient.getProduct(id));

return circuitBreakerFactory.create("catalog").run(
    source,
    error -> productCache.findById(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, error)
        ))
);
~~~

Với cách này, lỗi nguồn đi qua Circuit Breaker trước khi fallback thay thế kết quả cho caller. Việc fallback trả dữ liệu thành công không xóa đi kết quả lỗi mà bộ ngắt đã quan sát.

## 7. Trường hợp dùng Mono.just và Mono.fromCallable

Một lỗi thường gặp là đặt lời gọi có thể ném ngoại lệ bên trong **Mono.just**:

~~~java
Mono<Product> product =
    Mono.just(catalogClient.findProductImmediately(id));
~~~

Tham số của **Mono.just** được Java tính trước khi gọi phương thức. Vì vậy, nếu **findProductImmediately** ném ngoại lệ, không có Mono nào được tạo.

Với một hàm đồng bộ trả về giá trị, **Mono.fromCallable** trì hoãn lời gọi và chuyển ngoại lệ thành onError:

~~~java
Mono<Product> product =
    Mono.fromCallable(() -> catalogClient.findProductImmediately(id));
~~~

Nếu hàm đồng bộ thực hiện I/O blocking, cần đưa nó sang scheduler phù hợp, chẳng hạn:

~~~java
Mono<Product> product =
    Mono.fromCallable(() -> blockingCatalogClient.findProduct(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Sau đó có thể đặt Publisher này trong Reactive Circuit Breaker nếu cần đo lường thao tác phụ thuộc. Tuy nhiên, khi ứng dụng đã có WebClient hoặc reactive client, nên dùng API non-blocking gốc thay vì chuyển sang blocking rồi đưa lên scheduler chỉ để dùng lại client cũ.

| Cách tạo Publisher | Lời gọi nguồn được thực thi khi nào? | Ngoại lệ đồng bộ từ lời gọi nguồn |
|---|---|---|
| **Mono.just(client.call())** | Ngay khi biểu thức Java được đánh giá | Ném ra ngoài trước khi tạo Mono |
| **Mono.fromCallable(client::call)** | Khi subscribe | Chuyển thành onError |
| **Mono.defer(() -> client.callReactive())** | Khi subscribe | Chuyển thành onError nếu supplier ném ngoại lệ |
| **client.callReactive()** truyền trực tiếp vào run | Thường là lúc dựng Publisher | Có thể ném trước khi run được gọi |

## 8. Lỗi nào nên được Circuit Breaker ghi nhận?

Không phải mọi onError đều biểu thị dịch vụ phụ thuộc không khỏe. Ví dụ:

- **CallNotPermittedException:** bộ ngắt từ chối lời gọi vì đang OPEN hoặc không cấp thêm lượt trong HALF_OPEN. Đây là tín hiệu từ cơ chế bảo vệ, không phải lỗi mới do dịch vụ phụ thuộc trả về.
- **TimeoutException:** lời gọi vượt thời gian cho phép. Có thể được tính là lỗi nếu thuộc chính sách đánh giá sức khỏe.
- **WebClientResponseException:** phản hồi HTTP lỗi từ dịch vụ phụ thuộc. Tùy mã trạng thái và hợp đồng API, có thể ghi nhận hoặc bỏ qua.
- **InvalidProductIdException:** lỗi đầu vào của ứng dụng. Thông thường nên xảy ra ngoài Circuit Breaker.
- **MappingException:** lỗi chuyển đổi response. Nên quyết định có tính vào failure rate dựa trên việc nó phản ánh hợp đồng dependency hay lỗi nội bộ của mapper.
- **CancellationException:** quá trình xử lý bị hủy do caller ngừng quan tâm hoặc timeout ở lớp ngoài. Cần tránh xem mọi cancellation là lỗi dịch vụ.

Resilience4j cho phép cấu hình loại exception được ghi nhận và loại exception bị bỏ qua. Các nhóm exception này cần phản ánh ý nghĩa vận hành của dependency. Nếu một lỗi HTTP 404 có nghĩa là sản phẩm không tồn tại theo nghiệp vụ, có thể không nên làm tăng failure rate. Nếu HTTP 503 thể hiện dịch vụ đang không sẵn sàng, nó thường cần được tính là lỗi.

Cần kiểm tra cấu hình **recordExceptions**, **ignoreExceptions**, **recordFailurePredicate** hoặc cơ chế tương ứng trong phiên bản Resilience4j đang dùng. Đừng chỉ dựa vào tên lớp ngoại lệ; hãy xác định lỗi có cho thấy khả năng phục vụ của dependency bị suy giảm hay không.

## 9. Sơ đồ luồng xử lý

Sơ đồ sau thể hiện cách phân chia lỗi trước khi tạo Publisher và lỗi phát trên Publisher được Circuit Breaker bảo vệ:

~~~mermaid
flowchart TD
    A["Gọi phương thức reactive"] --> B{"Đầu vào hợp lệ?"}
    B -- "Không" --> C["Trả Mono.error"]
    C --> D["Caller nhận onError khi subscribe"]
    B -- "Có" --> E["Tạo Publisher bằng Mono.defer"]
    E --> F["Đưa Publisher vào Reactive Circuit Breaker"]
    F --> G["Subscribe và gọi dependency"]
    G --> H{"Kết quả"}
    H -- "onNext / onComplete" --> I["Circuit Breaker ghi nhận kết quả"]
    H -- "onError" --> J["Circuit Breaker ghi nhận theo exception policy"]
    J --> K["Chạy fallback"]
    K --> L["Trả Publisher dự phòng hoặc onError"]
    I --> M["Caller nhận kết quả"]
    L --> M
~~~

Lỗi đầu vào được biểu diễn bằng Mono.error để API vẫn trả Publisher, nhưng nó nằm ngoài Circuit Breaker. Lỗi khi gọi dependency được đưa vào Publisher nguồn bằng Mono.defer, nên bộ ngắt có thể quan sát tín hiệu lỗi và áp dụng chính sách ghi nhận.

## 10. Những lỗi triển khai thường gặp

1. **Ném ngoại lệ trước khi trả Publisher rồi mong fallback reactive xử lý.** Khi phương thức chưa trả Mono, fallback của Circuit Breaker chưa được gắn vào pipeline.
2. **Dùng Mono.just cho lời gọi có thể ném ngoại lệ.** Java đánh giá lời gọi trước khi Mono.just được tạo; dùng Mono.defer hoặc Mono.fromCallable phù hợp.
3. **Đặt validation sai vị trí.** Lỗi đầu vào không phản ánh sức khỏe dependency; thường nên trả Mono.error trước khi gọi Circuit Breaker.
4. **Dùng Mono.defer nhưng vẫn thực thi I/O blocking trên event loop.** Defer trì hoãn thao tác chứ không chuyển nó thành non-blocking.
5. **Phục hồi lỗi bằng onErrorResume trước Circuit Breaker.** Bộ ngắt có thể chỉ thấy kết quả thành công và không ghi nhận lỗi gốc.
6. **Nhầm onError với ngoại lệ đồng bộ.** Một lỗi đã phát thành onError có thể được xử lý bằng toán tử reactive; một ngoại lệ xảy ra trước khi Publisher tồn tại cần được xử lý ở ranh giới gọi phương thức.
7. **Đưa lỗi nghiệp vụ vào failure rate.** Cần phân loại exception theo semantics của dịch vụ, tránh mở mạch vì các request không hợp lệ hoặc tài nguyên không tồn tại.
8. **Fallback tiếp tục gọi cùng dependency đang lỗi.** Fallback nên dùng cache hoặc nguồn độc lập để không tạo thêm chuỗi lỗi.

## 11. Tình huống thực hành

Một dịch vụ Product API cung cấp phương thức reactive **getProduct(id)**. Phương thức nhận ID từ request, gọi Catalog qua WebClient và ánh xạ response sang Product domain. Khi Catalog lỗi, ứng dụng có thể dùng cache.

Hãy xét bốn tình huống:

| Tình huống | Cách biểu diễn | Circuit Breaker có quan sát không? |
|---|---|---|
| ID rỗng và phương thức ném IllegalArgumentException ngay | Ném đồng bộ trước khi trả Mono | Không; caller nhận exception trực tiếp |
| ID rỗng và phương thức trả Mono.error trước khi gọi Circuit Breaker | Publisher lỗi ở ngoài bộ ngắt | Không |
| Catalog client ném ngoại lệ khi tạo Publisher nhưng được gọi trong Mono.defer bên trong run | Ngoại lệ được chuyển thành onError | Có, theo exception policy |
| Catalog trả lỗi HTTP khi Publisher đang thực thi | Publisher phát onError | Có, theo exception policy |

Một cách triển khai phù hợp:

~~~java
Mono<Product> getProduct(String id) {
    if (id == null || id.isBlank()) {
        return Mono.error(new InvalidProductIdException(id));
    }

    return reactiveCircuitBreakerFactory.create("catalog").run(
        Mono.defer(() -> webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(ProductResponse.class)
        ).map(productMapper::toDomain),
        error -> productCache.findById(id)
            .switchIfEmpty(Mono.error(
                new CatalogUnavailableException(id, error)
            ))
    );
}
~~~

Trong ví dụ, validation nằm ngoài bộ ngắt; WebClient request được tạo trong Mono.defer; lỗi từ HTTP hoặc mapping được phát thành onError trong Publisher được bảo vệ; fallback tra cache khi cần. Khi kiểm thử, hãy quan sát cả phản hồi của caller và metric Circuit Breaker để xác nhận lỗi nào được tính vào failure rate.

Các câu hỏi cần trả lời sau khi thực hành:

- Trường hợp nào khiến phương thức không trả về Publisher?
- Vì sao Mono.error giữ được hợp đồng reactive nhưng không tự động đưa lỗi vào Circuit Breaker?
- Mono.defer thay đổi thời điểm gọi client và cách chuyển ngoại lệ như thế nào?
- Đặt onErrorResume trước hoặc sau Circuit Breaker làm thay đổi metric ra sao?
- Lỗi validation, timeout, lỗi HTTP và CallNotPermittedException nên được phân loại thế nào?

## Kết luận

Lỗi ném ra trước khi tạo Publisher xảy ra đồng bộ và không thể được fallback reactive của Circuit Breaker xử lý nếu bộ ngắt chưa nhận được Publisher. Hãy dùng Mono.error để giữ hợp đồng reactive cho lỗi đầu vào, đặt validation ngoài phạm vi bảo vệ nếu không muốn tính lỗi nghiệp vụ vào failure rate, và dùng Mono.defer hoặc Mono.fromCallable để chuyển ngoại lệ phát sinh khi tạo Publisher nguồn thành tín hiệu onError. Đặt fallback ở đúng phía sau Circuit Breaker để bộ ngắt quan sát lỗi gốc trước khi phục hồi kết quả.
