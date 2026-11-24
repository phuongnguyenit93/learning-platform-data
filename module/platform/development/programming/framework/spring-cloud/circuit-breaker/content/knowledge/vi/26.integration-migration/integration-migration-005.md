# Chuyển giữa annotation và factory mà giữ nguyên ranh giới bảo vệ

Trong ứng dụng Spring Cloud CircuitBreaker, một lời gọi dependency có thể được bảo vệ bằng API tường minh của `CircuitBreakerFactory`. Resilience4j cũng cung cấp annotation `@CircuitBreaker` để áp dụng cơ chế qua Spring AOP. Khi chuyển từ annotation sang factory hoặc ngược lại, thay đổi không chỉ là cách viết code: ranh giới được bảo vệ, ID, fallback, thứ tự decorator, khả năng reactive và metric có thể thay đổi theo.

Mục tiêu của việc di trú là giữ nguyên hành vi bảo vệ mà ứng dụng đang dựa vào: lời gọi nào được đo, lỗi nào được tính, lúc nào breaker mở, fallback trả gì và caller nhận kết quả ra sao. Bài này hướng dẫn kiểm kê ranh giới hiện tại, ánh xạ annotation sang factory, giữ cấu hình theo ID, xử lý khác biệt AOP và reactive, rồi chuyển đổi từng bước có thể kiểm chứng.

## 1. Hai cách tích hợp có ranh giới khác nhau

Annotation và factory đều có thể dùng Resilience4j Circuit Breaker, nhưng cách áp dụng khác nhau:

| Tiêu chí | Resilience4j annotation | Spring Cloud CircuitBreaker factory |
|---|---|---|
| Cách kích hoạt | Spring AOP intercept method được gắn annotation | Code gọi trực tiếp `factory.create(id)` rồi bọc lời gọi |
| Nơi thể hiện ranh giới | Method được proxy intercept | Supplier hoặc Publisher truyền vào `run` |
| Cấu hình | Instance name trong annotation liên kết với cấu hình Resilience4j | ID truyền vào `create(id)` liên kết với cấu hình factory/Resilience4j |
| Fallback | Method fallback theo quy ước tên và chữ ký | Function nhận Throwable được truyền trực tiếp vào `run` |
| Phụ thuộc framework | Phụ thuộc Resilience4j Spring AOP integration | Dùng abstraction Spring Cloud CircuitBreaker |
| Khả năng thay implementation | Gắn chặt với annotation Resilience4j | Có thể dùng abstraction Spring Cloud để thay implementation phù hợp |
| Kiểm soát phạm vi | Phụ thuộc method và hành vi proxy | Phạm vi lời gọi nhìn thấy ngay tại nơi gọi factory |

Annotation phù hợp khi một method Spring-managed là đơn vị bảo vệ rõ ràng và nhóm muốn khai báo resilience ngay trên method. Factory phù hợp khi muốn thể hiện chính xác lời gọi nào được bảo vệ, cần chọn ID tại điểm gọi hoặc muốn dùng abstraction của Spring Cloud.

Không có cách nào tự động tốt hơn trong mọi trường hợp. Hãy chọn theo ranh giới nghiệp vụ, mức độ tường minh cần có, loại lời gọi đồng bộ/reactive và chuẩn tích hợp của ứng dụng.

## 2. Kiểm kê hành vi hiện tại trước khi di trú

Trước khi đổi code, ghi lại hành vi của từng annotation đang dùng. Không chỉ ghi tên method; cần biết chính xác phần công việc bên trong method và những decorator khác đang áp dụng.

Checklist kiểm kê:

- Method nào có `@CircuitBreaker`, instance name nào được dùng?
- Method có gọi đúng một dependency hay còn chứa validation, mapping và xử lý nghiệp vụ cục bộ?
- Method có bị gọi nội bộ từ method khác trong cùng bean không?
- Có `fallbackMethod` không, chữ ký và kiểu exception cuối cùng là gì?
- Có `@Retry`, `@TimeLimiter`, `@Bulkhead` hoặc `@RateLimiter` trên cùng method hay ở method gọi nó không?
- Cấu hình instance đang đặt ở profile nào, có customizer hoặc property override không?
- Caller đang nhận exception, response lỗi hay dữ liệu fallback?
- Dashboard đang dùng tên breaker, metric và alert nào?

Ví dụ method hiện tại:

~~~java
@Service
public class CatalogService {
    private final CatalogClient catalogClient;

    public CatalogService(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "catalog-read",
        fallbackMethod = "findFallback"
    )
    public Product findProduct(String id) {
        return catalogClient.fetchProduct(id);
    }

    private Product findFallback(String id, Throwable cause) {
        return Product.unavailable(id);
    }
}
~~~

Trong ví dụ này, ranh giới annotation là toàn bộ method `findProduct`. Nếu method chỉ gọi CatalogClient thì ranh giới khá rõ. Nếu method còn làm validation, truy vấn database khác hoặc mapping phức tạp, mọi exception trong phần đó có thể bị xem như lỗi của `catalog-read`. Khi chuyển sang factory, hãy quyết định rõ chỉ bọc lời gọi Catalog hay bọc cả pipeline.

## 3. Giữ nguyên ID và cấu hình Resilience4j

ID là một phần quan trọng của ranh giới. Annotation `name = "catalog-read"` và factory `create("catalog-read")` cần dùng cùng ID nếu mục tiêu là giữ chính sách cấu hình tương ứng.

Ví dụ cấu hình instance:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Các tham số này quyết định cách breaker quan sát lời gọi. Khi di trú, hãy giữ nguyên ít nhất:

- Sliding window type và size.
- Minimum number of calls.
- Failure rate và slow call thresholds.
- Slow call duration threshold.
- Wait duration ở OPEN.
- Số lời gọi được phép ở HALF_OPEN.
- Danh sách exception được record hoặc ignore.
- Chính sách automatic transition nếu đang bật.

Không đổi ID chỉ để code mới chạy được. Nếu ID thay đổi, cấu hình instance, metric, dashboard và alert có thể không còn khớp. Tuy nhiên, cũng không giả định annotation và factory chắc chắn dùng cùng một registry hoặc cùng một object CircuitBreaker ở runtime chỉ vì tên ID giống nhau. Tích hợp và cấu hình registry phụ thuộc starter và phiên bản. Hãy kiểm tra bean registry, instance thực tế và metric sau khi chuyển.

Nếu cần chạy hai cách song song để canary, tránh bọc cùng một invocation bằng cả annotation và factory. Nếu cả hai cùng dùng một ID trong một registry chung, trạng thái và event có thể bị chia sẻ hoặc tương tác theo cách không mong muốn; nếu dùng hai ID riêng, chúng lại có hai cửa sổ và state độc lập. Hãy chọn cách so sánh không tạo double wrapping và không nhân đôi traffic tới dependency.

## 4. Chuyển từ annotation sang CircuitBreakerFactory

Factory làm ranh giới bảo vệ hiện rõ tại nơi gọi. Ví dụ tương đương với method ở phần trước:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String id) {
        return circuitBreakerFactory.create("catalog-read").run(
            () -> catalogClient.fetchProduct(id),
            cause -> findFallback(id, cause)
        );
    }

    private Product findFallback(String id, Throwable cause) {
        return Product.unavailable(id);
    }
}
~~~

Cấu trúc chuyển đổi:

| Annotation cũ | Factory mới |
|---|---|
| `@CircuitBreaker(name = "catalog-read")` | `circuitBreakerFactory.create("catalog-read")` |
| Thân method được AOP intercept | Supplier truyền vào `run` |
| `fallbackMethod = "findFallback"` | Function `cause -> findFallback(id, cause)` |
| Cấu hình instance `catalog-read` | Giữ ID và cấu hình instance `catalog-read` |

Điểm cần kiểm tra là Supplier chỉ chứa lời gọi dependency dự kiến được bảo vệ. Nếu muốn bảo vệ cả một chuỗi thao tác, hãy quyết định điều đó có chủ ý. Tránh vô tình đưa validation, mapping hoặc một dependency thứ hai vào cùng Supplier vì chúng có thể làm sai failure rate của Catalog.

## 5. Chuyển fallback method sang fallback function

Với annotation, Resilience4j tìm method fallback theo tên và chữ ký. Method fallback thường có cùng tham số với method gốc và thêm một tham số exception ở cuối; kiểu trả về cần tương thích với method được bảo vệ.

Với factory, fallback được truyền trực tiếp dưới dạng Function nhận Throwable:

~~~java
return circuitBreakerFactory.create("catalog-read").run(
    () -> catalogClient.fetchProduct(id),
    cause -> {
        if (cause instanceof ProductNotFoundException) {
            throw (ProductNotFoundException) cause;
        }

        return cache.findUsable(id)
            .orElseThrow(() ->
                new CatalogUnavailableException(id, cause));
    }
);
~~~

Khi di trú, không nên chỉ sao chép thân fallback mà bỏ qua cách phân loại exception. Một fallback có thể đang xử lý riêng timeout, lỗi không tìm thấy và lỗi credential. Hãy giữ đúng các nhánh đó.

| Tình huống | Hành vi cần giữ |
|---|---|
| Timeout hoặc connection error | Có thể dùng cache còn hợp lệ hoặc trả lỗi availability |
| Breaker OPEN | Fail fast; fallback theo hợp đồng của caller |
| 404 nghiệp vụ | Trả not found; không biến thành dữ liệu cache không liên quan |
| 401/403 từ dependency | Báo lỗi tích hợp/credential; không che giấu bằng fallback success |
| Ghi dữ liệu timeout | Trả trạng thái chưa xác định hoặc tra soát; không báo thành công giả |
| Fallback không có dữ liệu | Phát lỗi phù hợp hoặc response suy giảm được định nghĩa |

Fallback không nên gọi lại chính dependency đang được bảo vệ. Nếu fallback gọi cache hoặc dịch vụ dự phòng, các nguồn đó cần timeout và giới hạn tài nguyên riêng.

## 6. Chuyển từ factory về annotation

Trong một số trường hợp, ứng dụng có thể muốn gom lời gọi vào một method Spring-managed để giảm code lặp. Khi đó có thể chuyển từ factory về annotation:

~~~java
@Service
public class CatalogGateway {
    private final CatalogClient catalogClient;

    public CatalogGateway(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker(
        name = "catalog-read",
        fallbackMethod = "findFallback"
    )
    public Product findProduct(String id) {
        return catalogClient.fetchProduct(id);
    }

    private Product findFallback(String id, Throwable cause) {
        if (cause instanceof ProductNotFoundException) {
            throw (ProductNotFoundException) cause;
        }
        return Product.unavailable(id);
    }
}
~~~

Để annotation được áp dụng, cần có integration Spring AOP tương ứng và bean phải được Spring quản lý. Gọi method thông qua proxy Spring mới kích hoạt advice. Self-invocation, tức một method trong cùng object gọi trực tiếp method được annotation, thường bỏ qua proxy nên annotation không được áp dụng như mong đợi.

Ví dụ:

~~~java
@Service
public class CatalogService {
    public Product load(String id) {
        // Gọi trực tiếp trong cùng object: không đi qua proxy AOP.
        return findProtected(id);
    }

    @CircuitBreaker(name = "catalog-read")
    public Product findProtected(String id) {
        return catalogClient.fetchProduct(id);
    }
}
~~~

Nếu `load` gọi `findProtected` bằng `this.findProtected(...)`, lời gọi không đi qua Spring proxy. Có thể tách method được bảo vệ sang một bean khác hoặc tiếp tục dùng factory tại điểm gọi nếu cần ranh giới tường minh.

## 7. Không bọc cùng lời gọi hai lần

Trong giai đoạn di trú, một lỗi thường gặp là giữ annotation cũ rồi thêm factory quanh cùng lời gọi:

~~~java
@CircuitBreaker(name = "catalog-read")
public Product findProduct(String id) {
    return circuitBreakerFactory.create("catalog-read").run(
        () -> catalogClient.fetchProduct(id)
    );
}
~~~

Đây là double wrapping. Một invocation đi qua hai lớp Circuit Breaker. Hậu quả có thể gồm:

- Hai breaker cùng ghi nhận một lỗi, hoặc một breaker ghi nhận kết quả của breaker còn lại.
- Fallback có thể chạy ở lớp trong rồi kết quả fallback được lớp ngoài xem là success.
- State và metric khó diễn giải, đặc biệt nếu hai lớp dùng ID hoặc registry khác nhau.
- Một breaker OPEN có thể chặn lời gọi trước khi breaker còn lại có cơ hội quan sát.
- Ngưỡng và thời gian mở mạch có thể tạo hành vi khác với trước di trú.

Mỗi ranh giới dependency nên có một cơ chế Circuit Breaker sở hữu rõ ràng. Khi chuyển đổi, bỏ decorator cũ sau khi decorator mới đã được xác minh. Không giữ cả hai chỉ để “tăng bảo vệ”.

## 8. Giữ thứ tự Retry, TimeLimiter và Bulkhead

Một method có thể được bảo vệ bởi nhiều cơ chế Resilience4j. Khi di trú, phải kiểm kê toàn bộ decorator, không chỉ Circuit Breaker.

Ví dụ annotation cũ:

~~~java
@Retry(name = "catalog-read")
@CircuitBreaker(name = "catalog-read")
@TimeLimiter(name = "catalog-read")
public CompletableFuture<Product> findAsync(String id) {
    return catalogClient.fetchAsync(id);
}
~~~

Cấu hình annotation có thể phụ thuộc thứ tự aspect của Resilience4j. Khi chuyển sang factory, không giả định thứ tự decorator tự động giữ nguyên. Factory có cấu hình TimeLimiter riêng và Bulkhead provider riêng; Retry có thể được áp dụng bằng API Resilience4j hoặc một tầng điều phối khác.

Hãy ghi lại thứ tự thực tế hiện tại và xác minh thứ tự mới bằng test. Một thứ tự khác có thể thay đổi:

- Retry có chạy lại toàn bộ invocation hay chỉ một lần gọi bên trong?
- Circuit Breaker đếm từng attempt hay kết quả cuối?
- TimeLimiter có hủy tác vụ khi timeout không?
- Bulkhead slot được giữ trong toàn bộ retry hay chỉ một attempt?
- Fallback chạy trước hay sau khi các decorator khác kết thúc?

Không thêm Retry trong lúc di trú nếu trước đó chưa có. Retry có thể nhân số request tới dependency và làm vượt deadline. Với thao tác ghi, cần idempotency key hoặc cơ chế chống xử lý trùng.

## 9. Phân biệt lời gọi đồng bộ và reactive

Với lời gọi đồng bộ, dùng `CircuitBreakerFactory`:

~~~java
Product product = circuitBreakerFactory.create("catalog-read").run(
    () -> catalogClient.fetchProduct(id),
    cause -> cache.findUsable(id)
        .orElseThrow(() -> new CatalogUnavailableException(id, cause))
);
~~~

Với Reactor, dùng `ReactiveCircuitBreakerFactory` và giữ Publisher trong ranh giới:

~~~java
Mono<Product> remoteCall = Mono.defer(() ->
    webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
);

return reactiveCircuitBreakerFactory.create("catalog-read").run(
    remoteCall,
    cause -> cache.findUsableReactive(id)
        .switchIfEmpty(Mono.error(
            new CatalogUnavailableException(id, cause)))
);
~~~

Không chuyển một lời gọi reactive thành `block()` chỉ để dùng factory đồng bộ. Không gọi `subscribe()` trước khi truyền Publisher vào reactive breaker. Publisher được bảo vệ phải chứa lời gọi mạng thật; nếu lỗi đã được `onErrorResume` thành giá trị trước khi đi vào breaker, breaker có thể chỉ thấy success.

Annotation của Resilience4j cũng có hỗ trợ cho một số kiểu trả về bất đồng bộ/reactive tùy phiên bản và module tích hợp. Trước khi chuyển giữa annotation và factory, hãy xác nhận API hỗ trợ đúng kiểu trả về đang dùng, đặc biệt với `Mono`, `Flux` và `CompletionStage`. Không suy ra rằng ví dụ đồng bộ có thể đổi kiểu trả về mà không đổi semantics cancellation, timeout hoặc fallback.

## 10. Giữ nguyên ranh giới khi method có nhiều bước

Giả sử method hiện tại vừa gọi Catalog, vừa đọc giá từ database nội bộ, vừa chuyển đổi DTO:

~~~java
@CircuitBreaker(name = "catalog-read")
public ProductView getView(String id) {
    Product product = catalogClient.fetchProduct(id);
    Price price = localPriceRepository.findPrice(id);
    return mapper.toView(product, price);
}
~~~

Với annotation, cả ba bước nằm trong method được intercept. Nếu database nội bộ lỗi hoặc mapper ném exception, breaker `catalog-read` có thể ghi nhận failure dù Catalog Service hoạt động bình thường.

Khi chuyển sang factory, có thể thu hẹp ranh giới chỉ quanh lời gọi Catalog:

~~~java
public ProductView getView(String id) {
    Product product = circuitBreakerFactory.create("catalog-read").run(
        () -> catalogClient.fetchProduct(id),
        cause -> cache.findUsable(id)
            .orElseThrow(() -> new CatalogUnavailableException(id, cause))
    );

    Price price = localPriceRepository.findPrice(id);
    return mapper.toView(product, price);
}
~~~

Đây là một thay đổi có chủ đích về ranh giới, không phải chuyển đổi cơ học. Nếu hành vi cũ đã ghi nhận lỗi database và mapping vào breaker, việc thu hẹp ranh giới sẽ thay đổi metric. Hãy ghi rõ thay đổi đó trong kế hoạch migration và kiểm thử riêng.

Nếu cần giữ nguyên phạm vi cũ trong lần chuyển đầu tiên, hãy bọc toàn bộ phần thân method vào Supplier trước; sau đó mới thực hiện một thay đổi ranh giới riêng có kiểm thử và quan sát. Tách hai thay đổi giúp xác định nguyên nhân khi hành vi khác trước.

## 11. Kế hoạch di trú từng bước

Có thể chuyển đổi an toàn theo các giai đoạn sau:

1. **Lập danh sách callsite:** ghi method, annotation, ID, fallback, retry, timeout, bulkhead và kiểu trả về.
2. **Chụp baseline:** ghi failure rate, slow call rate, latency, số lần fallback và state transition trong điều kiện bình thường.
3. **Chuẩn hóa cấu hình:** giữ ID và các tham số Resilience4j; xác nhận profile và customizer đang áp dụng.
4. **Chọn một callsite nhỏ:** ưu tiên một lời gọi có test và ít side effect.
5. **Thay một cơ chế:** bỏ annotation hoặc factory cũ, thêm cách mới, không double-wrap.
6. **Kiểm thử outcome:** success, exception, timeout, slow call, OPEN, HALF_OPEN và fallback.
7. **Canary theo traffic:** so sánh metric và response với baseline, giữ rollback path.
8. **Mở rộng:** chuyển từng nhóm callsite tương đồng, cập nhật dashboard và tài liệu.
9. **Dọn cấu hình cũ:** chỉ xóa bean, dependency hoặc annotation integration không còn dùng sau khi xác nhận không còn callsite.

Không nên chuyển toàn bộ module cùng lúc nếu có nhiều dependency và chính sách khác nhau. Một callsite có thể dùng factory, callsite khác vẫn dùng annotation trong thời gian chuyển tiếp, miễn là mỗi lời gọi chỉ có một Circuit Breaker sở hữu.

## 12. Ma trận kiểm thử trước và sau di trú

| Kịch bản | Điều cần giữ nguyên |
|---|---|
| Dependency trả 200 | Kết quả và latency không thay đổi ngoài overhead nhỏ |
| Dependency trả 404 nghiệp vụ | Caller nhận not found; failure rate xử lý theo cấu hình ignore |
| Dependency trả 503 liên tục | Breaker ghi nhận failure và chuyển OPEN sau ngưỡng |
| Dependency phản hồi chậm | Slow call được ghi nhận theo cùng threshold |
| Breaker OPEN | Lời gọi mới fail fast, không gửi HTTP request tới dependency |
| HALF_OPEN | Chỉ số lời gọi thăm dò và quyết định đóng/mở lại giữ đúng cấu hình |
| Fallback thành công | Cùng dữ liệu và cùng semantics như trước |
| Fallback thất bại | Caller nhận lỗi đúng hợp đồng, không có success giả |
| Retry/TimeLimiter/Bulkhead | Số attempt, deadline, concurrency và cancellation không đổi ngoài chủ đích |
| Reactive cancellation | Hủy subscription không để lại request hoặc tác vụ nền ngoài dự kiến |

Cần kiểm tra cả kết quả ở caller lẫn metric của breaker. Một response giống nhau chưa chứng minh state, failure rate và fallback hoạt động giống nhau.

## 13. Quan sát sau chuyển đổi

Theo dõi các tín hiệu trước và sau migration theo từng ID:

- Số lời gọi thành công, thất bại, slow call và not permitted.
- Failure rate, slow-call rate và state transition.
- Latency p50, p95, p99 của dependency.
- Số lần fallback và tỷ lệ fallback thành công.
- Số HTTP attempt nếu có Retry.
- Số Bulkhead rejection và mức sử dụng thread/queue.
- Tỷ lệ request đầu cuối thành công và lỗi caller nhận được.

Tên metric hoặc tag có thể thay đổi tùy integration và phiên bản. Đừng giả định dashboard cũ vẫn theo dõi đúng instance sau khi thay factory hoặc annotation. Hãy xác nhận ID, registry và meter thực tế, rồi cập nhật alert nếu tên hoặc tag thay đổi.

Trong canary, nếu breaker mới mở thường xuyên hơn, hãy kiểm tra trước ranh giới và exception classification. Có thể Supplier mới đang bao gồm thêm logic cục bộ, hoặc fallback đang phục hồi lỗi trước khi breaker ghi nhận. Đừng vội tăng threshold để làm dashboard giống baseline khi chưa hiểu nguyên nhân.

## 14. Lỗi thường gặp khi chuyển đổi

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Annotation không có tác dụng | Method không đi qua Spring AOP proxy hoặc self-invocation | Tách bean hoặc dùng factory tại điểm gọi |
| Factory không dùng cấu hình cũ | ID trong `create` khác instance name của annotation | Giữ ID hoặc cập nhật cấu hình có chủ đích |
| Breaker ghi nhận nhiều lỗi hơn | Supplier bao gồm mapping hoặc dependency khác | Thu hẹp ranh giới hoặc chấp nhận thay đổi đã được kiểm thử |
| Fallback chạy hai lần | Double wrapping hoặc có nhiều lớp fallback | Chỉ giữ một Circuit Breaker cho mỗi ranh giới |
| Breaker không mở sau lỗi HTTP | Client trả response object hoặc lỗi bị nuốt | Chuẩn hóa exception hoặc dùng `recordResult` |
| Metric bị tách thành hai nhóm | Registry/instance hoặc tên breaker thay đổi | Kiểm tra registry, ID và dashboard |
| Tổng thời gian tăng | Retry hoặc timeout decorator đổi thứ tự | Tính deadline toàn request và kiểm tra số attempt |
| Reactive request bị block | Dùng factory đồng bộ hoặc gọi `block()` | Chuyển sang ReactiveCircuitBreakerFactory và giữ Publisher |

## Kết luận

Di trú giữa Resilience4j annotation và Spring Cloud CircuitBreaker factory cần giữ nguyên ranh giới dependency, ID, exception classification, fallback và thứ tự decorator. Annotation dựa vào Spring AOP nên phụ thuộc proxy và self-invocation; factory làm phạm vi bảo vệ tường minh tại Supplier hoặc Publisher. Hãy kiểm kê hành vi cũ, chuyển từng callsite, tránh double wrapping, kiểm tra đồng bộ/reactive semantics và so sánh metric với baseline. Khi mỗi dependency có một ranh giới bảo vệ rõ ràng và được xác minh bằng test cùng telemetry, ứng dụng có thể đổi cách tích hợp mà vẫn giữ hành vi phục hồi dự kiến.

