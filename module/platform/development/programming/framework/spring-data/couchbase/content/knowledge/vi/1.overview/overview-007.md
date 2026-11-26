# Lựa chọn truy cập đồng bộ hoặc phản ứng trong Spring Data Couchbase

## 1. Mục tiêu bài học

Một ứng dụng Spring có thể làm việc với Couchbase qua API **đồng bộ (synchronous/blocking)** hoặc **phản ứng (reactive/non-blocking)**. Cả hai đều có thể đọc và ghi JSON document, truy cập theo document ID, thực thi truy vấn SQL++ và khai thác các khả năng của Couchbase. Tuy nhiên, chúng khác nhau ở **cách quản lý luồng thực thi, cách biểu diễn kết quả và cách phối hợp nhiều thao tác I/O**.

Bài học thuộc chương **Tổng quan** của module `SPRING_DATA_COUCHBASE`. Sau bài học, bạn có thể:

- Phân biệt lời gọi đồng bộ trả kết quả trực tiếp với API phản ứng trả về `Mono` hoặc `Flux`.
- Hiểu vì sao reactive cải thiện khả năng phục vụ nhiều request I/O đồng thời, nhưng không tự làm một thao tác Couchbase đơn lẻ nhanh hơn.
- Chọn giữa `CouchbaseRepository`, `CouchbaseTemplate` và biến thể reactive; biết khi nào dùng Couchbase Java SDK.
- Viết các service CRUD, truy vấn SQL++ và cập nhật với optimistic locking ở hai phong cách.
- Nhận ra các lỗi blocking trong WebFlux, lạm dụng `subscribe()`, thiếu kiểm soát đồng thời, sai vị trí timeout và retry.
- Đặt lựa chọn API trong thiết kế bucket/scope/collection, index, TTL, CAS, transaction, consistency và vận hành thực tế.

Trong ngữ cảnh này, **“phản ứng” là cách gọi của reactive programming**, không có nghĩa Couchbase tự kích hoạt các hành động nghiệp vụ khi dữ liệu đổi.

## 2. Ví dụ dẫn nhập: cùng một nhu cầu, hai mô hình thực thi

Giả sử hệ thống thương mại điện tử nhận yêu cầu mở giỏ hàng của khách. Document có key metadata `cart::u-123` trong collection `shop.sales.carts`:

~~~json
{
  "customerId": "u-123",
  "currency": "VND",
  "items": [
    { "sku": "A-100", "quantity": 2, "unitPrice": 120000 },
    { "sku": "B-200", "quantity": 1, "unitPrice": 90000 }
  ],
  "status": "ACTIVE"
}
~~~

API đồng bộ có thể gọi `repository.findById("cart::u-123")` rồi nhận `Optional<Cart>`. Trong lúc chờ dữ liệu từ Couchbase, **luồng đang gọi bị chặn** cho đến khi có kết quả hoặc lỗi.

API reactive có thể gọi `reactiveRepository.findById("cart::u-123")` và nhận `Mono<Cart>`. `Mono` biểu diễn một thao tác có thể phát ra **0 hoặc 1 kết quả**, hoặc lỗi; quá trình thực thi I/O được điều phối bất đồng bộ khi có subscription. Luồng gọi có thể tiếp tục phục vụ công việc khác trong lúc chờ.

~~~mermaid
sequenceDiagram
    participant C as HTTP handler
    participant T as Thread thực thi
    participant DB as Couchbase
    Note over C,DB: Đồng bộ
    C->>T: findById(key)
    T->>DB: KV get
    Note over T: Thread chờ kết quả
    DB-->>T: Document / lỗi
    T-->>C: Optional<Cart>
~~~

~~~mermaid
sequenceDiagram
    participant H as WebFlux handler
    participant R as Reactor pipeline
    participant DB as Couchbase
    H->>R: findById(key) -> Mono<Cart>
    R-->>H: Publisher
    Note over R: Subscribe theo request
    R->>DB: KV get bất đồng bộ
    Note over H: Không giữ thread chờ network
    DB-->>R: Document / lỗi
    R-->>H: Tín hiệu onNext/onComplete hoặc onError
~~~

Đây là sơ đồ khái niệm, không mô tả chính xác mọi thread hoặc mỗi callback của SDK. Điểm cốt lõi: **blocking** giữ thread chờ I/O; **non-blocking** biểu diễn công việc bằng tín hiệu và callback để hệ thống điều phối tốt hơn khi số thao tác chờ mạng tăng.

## 3. So sánh synchronous và reactive

| Tiêu chí | Đồng bộ | Reactive |
| --- | --- | --- |
| Phong cách gọi | Gọi rồi chờ hoàn thành | Tạo pipeline, thực thi khi có subscription |
| Kiểu kết quả | Entity, `Optional<T>`, `List<T>`, exception | `Mono<T>`, `Flux<T>`, tín hiệu hoàn tất/lỗi |
| Cách chờ mạng | Thread gọi thường bị chặn | Không cần giữ thread chờ I/O theo cách blocking |
| Ghép nhiều thao tác | Lệnh tuần tự, vòng lặp, future riêng | `map`, `flatMap`, `zip`, `concatMap`, v.v. |
| Xử lý lỗi | `try/catch` ở điểm gọi | `onErrorResume`, `onErrorMap`, `retryWhen`, error signal |
| Kiểm soát đồng thời | Thread pool, queue, timeout | Scheduler, concurrency operators, backpressure, timeout |
| Độ dễ đọc với CRUD đơn giản | Thường trực quan | Cần hiểu lifecycle và các operator |
| Hợp với Spring MVC truyền thống | Rất thường gặp | Có thể tích hợp, nhưng cần cân nhắc lợi ích |
| Hợp với WebFlux xuyên suốt | Chỉ khi cô lập blocking đúng chỗ | Phù hợp với mô hình non-blocking |
| Thay đổi query/index Couchbase | Không | Không |
| CAS, TTL, transaction, consistency | Phải thiết kế | Vẫn phải thiết kế |

**Không nên chọn reactive chỉ vì tin rằng nó làm `findById` nhanh hơn.** Lợi ích thường đến từ hiệu quả sử dụng thread khi có nhiều I/O đang chờ đồng thời, giúp hệ thống giữ khả năng phục vụ dưới tải phù hợp. Nếu nút thắt là CPU của Query Service, chỉ mục thiếu, hot document hoặc băng thông mạng, đổi kiểu trả về thành `Mono` không giải quyết được nguyên nhân.

## 4. Spring Data Couchbase có những API tương ứng nào?

| Tầng truy cập | API đồng bộ | API reactive |
| --- | --- | --- |
| Repository | `CouchbaseRepository<T, ID>` | `ReactiveCouchbaseRepository<T, ID>` |
| Template | `CouchbaseTemplate` | `ReactiveCouchbaseTemplate` |
| Java SDK | SDK synchronous API | SDK reactive/async API |
| Một document | `Optional<T>` hoặc entity | `Mono<T>` |
| Nhiều document | `List<T>` hoặc một kết quả tuần tự | `Flux<T>` |

Repository tiện cho CRUD và derived query; Template giúp lập trình các thao tác và truy vấn trên entity linh hoạt hơn; SDK trực tiếp thích hợp khi cần KV options, sub-document operation, Search Service hoặc chức năng SDK chuyên biệt. **Sự khác biệt giữa đồng bộ và reactive tồn tại ở cả ba tầng**; đừng nhầm “dùng Template” với “dùng reactive”.

Một luồng điển hình:

~~~mermaid
flowchart TD
    S["Application Service"] --> A{"Chọn mô hình"}
    A -->|Đồng bộ| R["CouchbaseRepository / CouchbaseTemplate"]
    A -->|Reactive| RR["ReactiveCouchbaseRepository / ReactiveCouchbaseTemplate"]
    S --> SDKD["SDK trực tiếp nếu cần"]
    R --> SDK["Couchbase Java SDK"]
    RR --> SDK
    SDKD --> SDK
    SDK --> CB[("Couchbase cluster")]
    CB --> KV["KV theo document ID"]
    CB --> Q["SQL++ qua query/index"]
~~~

Repository, Template và SDK có thể dùng cùng Couchbase cluster. Điều kiện để đọc cùng một document là **trỏ đúng bucket, scope, collection và document ID**, đồng thời tương thích quy tắc mapping. Thay đổi phong cách API không làm document chuyển sang kho dữ liệu khác.

## 5. Chuẩn bị entity và cấu hình ví dụ

Giả sử ứng dụng đã cấu hình bucket `shop` và có collection `sales.carts`. JSON body của Cart được ánh xạ thành POJO Java:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Cart {
    @Id
    private String id;

    @Field
    private String customerId;

    @Field
    private String status;

    @Field
    private List<CartItem> items;

    @Version
    private Long version;

    public Cart() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public List<CartItem> getItems() { return items; }
    public void setItems(List<CartItem> items) { this.items = items; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public static class CartItem {
        private String sku;
        private int quantity;
        private long unitPrice;

        public CartItem() {}

        public String getSku() { return sku; }
        public void setSku(String sku) { this.sku = sku; }

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public long getUnitPrice() { return unitPrice; }
        public void setUnitPrice(long unitPrice) {
            this.unitPrice = unitPrice;
        }
    }
}
~~~

- `@Document` và `@Field` tham gia object–document mapping.
- `@Id` biểu diễn **document key metadata**, không cần tự thêm field `id` vào body.
- `@Version` tích hợp optimistic locking qua **CAS** của Couchbase. Nó không tự mở transaction nhiều document.
- Nếu muốn sử dụng `sales.carts` thay vì `_default._default`, cần cấu hình scope/collection mapping tương thích với phiên bản Spring Data. Cấu hình chỉ có bucket name là chưa đủ để tự chọn collection này.

Dependency và cấu hình phải khớp phiên bản Spring Boot đang dùng. Ví dụ Gradle cho ứng dụng truy cập đồng bộ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Với ứng dụng ưu tiên repository reactive, có thể sử dụng starter reactive tương ứng nếu có trong phiên bản Spring Boot đang dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase-reactive'
}
~~~

Trong thực tế, không cần thêm cả hai starter nếu stack đã cung cấp mọi thành phần cần thiết. Ví dụ cấu hình connection cho bucket:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Đây là dữ liệu cấu hình minh họa; hãy cấp credentials qua secret/environment của môi trường chạy. Cluster, bucket, scope/collection và quyền tài khoản phải được thiết lập. Không tạo kết nối Couchbase mới cho từng request; dùng bean/client được ứng dụng quản lý và tái sử dụng.

## 6. Cách viết đồng bộ: Repository và Service

Định nghĩa một repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CartRepository
        extends CouchbaseRepository<Cart, String> {

    List<Cart> findByStatus(String status);
}
~~~

Service đồng bộ:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class CartService {
    private final CartRepository carts;

    public CartService(CartRepository carts) {
        this.carts = carts;
    }

    public Optional<Cart> getCart(String customerId) {
        return carts.findById("cart::" + customerId);
    }

    public Cart saveCart(Cart cart) {
        return carts.save(cart);
    }

    public List<Cart> activeCarts() {
        return carts.findByStatus("ACTIVE");
    }
}
~~~

`getCart` trả `Optional<Cart>` sau khi lời gọi I/O hoàn thành. `saveCart` trả entity đã lưu hoặc ném exception. `activeCarts` trả cả danh sách theo điều kiện.

**Sự khác biệt về đường dữ liệu:**

- `findById("cart::u-123")` biết key chính xác → thường là truy cập KV.
- `findByStatus("ACTIVE")` lọc field JSON → thường sinh SQL++ và cần secondary index phù hợp.

Ví dụ index SQL++ cho collection `shop.sales.carts`:

~~~sql
CREATE INDEX ix_carts_status
ON `shop`.`sales`.`carts`(status);
~~~

Index được chọn theo truy vấn thật; nếu Spring Data thêm discriminator type hoặc có thêm các điều kiện khác, index cần được kiểm tra bằng `EXPLAIN`. Không vì dùng Repository mà Couchbase tự tạo index tối ưu.

### 6.1. Khi nào đồng bộ là lựa chọn hợp lý?

- Ứng dụng đang dùng Spring MVC và mô hình request-per-thread thông thường.
- Phần lớn thao tác đơn giản, tải vừa phải; đội ngũ ưu tiên logic tuần tự dễ đọc và debug.
- Hệ thống dùng nhiều thư viện blocking khác, nên một pipeline reactive sẽ phải chuyển đổi liên tục.
- Số lượng kết nối và thread được sizing tốt; dữ liệu truy cập đã có key/index phù hợp.

**Đồng bộ không có nghĩa kém chất lượng**. Nó là lựa chọn đúng khi mô hình hoạt động đáp ứng yêu cầu độ trễ, throughput, mức dùng tài nguyên và khả năng bảo trì.

## 7. Cách viết reactive: Repository và pipeline Reactor

Repository reactive:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import reactor.core.publisher.Flux;

public interface ReactiveCartRepository
        extends ReactiveCouchbaseRepository<Cart, String> {

    Flux<Cart> findByStatus(String status);
}
~~~

Service reactive:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCartService {
    private final ReactiveCartRepository carts;

    public ReactiveCartService(ReactiveCartRepository carts) {
        this.carts = carts;
    }

    public Mono<Cart> getCart(String customerId) {
        return carts.findById("cart::" + customerId);
    }

    public Mono<Cart> saveCart(Cart cart) {
        return carts.save(cart);
    }

    public Flux<Cart> activeCarts() {
        return carts.findByStatus("ACTIVE");
    }
}
~~~

Các kiểu dữ liệu biểu đạt **hợp đồng kết quả**:

| Kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Mono<Cart>` | Có thể có 0 hoặc 1 cart, hoặc lỗi | Đọc theo ID, save một entity |
| `Flux<Cart>` | Luồng 0..n cart, hoặc lỗi | Truy vấn nhiều cart |
| `Mono<Void>` | Quan tâm hoàn tất hoặc lỗi, không cần giá trị | Xóa document |
| `Mono<List<Cart>>` | Gom một luồng hữu hạn thành list | Khi API thật sự cần danh sách nhỏ, có giới hạn |

Ở reactive Repository, việc trả `Mono` không tự “ghi vào database ngay” khi hàm trả về. Theo mô hình Publisher của Reactor, chuỗi xử lý được kích hoạt bởi **subscription**; với WebFlux, framework thường subscribe cho kết quả do handler trả về. Không tự gọi `subscribe()` trong service chỉ để khởi động và bỏ qua kết quả vì rất dễ đánh mất lỗi, lifecycle request và khả năng kiểm soát transaction.

### 7.1. Reactive Controller không cần gọi `block()`

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/carts")
public class CartController {
    private final ReactiveCartService service;

    public CartController(ReactiveCartService service) {
        this.service = service;
    }

    @GetMapping("/{customerId}")
    public Mono<Cart> get(@PathVariable String customerId) {
        return service.getCart(customerId)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Cart not found")));
    }
}
~~~

Framework nhận `Mono<Cart>` và chịu trách nhiệm subscription, mã hóa HTTP response và truyền lỗi theo pipeline. Cần áp dụng xác thực, phân quyền và validation input ở tầng phù hợp. Một document ID suy ra từ customerId không tự bảo đảm người gọi được xem giỏ của khách hàng đó.

### 7.2. `map` khác `flatMap`

~~~java
Mono<Cart> cartMono = carts.findById("cart::u-123");

// Chỉ đổi giá trị trong bộ nhớ, không làm thao tác Couchbase mới:
Mono<String> status = cartMono.map(Cart::getStatus);

// Kết hợp thao tác Couchbase thứ hai phải dùng flatMap:
Mono<Cart> saved = carts.findById("cart::u-123")
        .flatMap(cart -> {
            cart.setStatus("CHECKOUT");
            return carts.save(cart);
        });
~~~

`map` dùng cho biến đổi đồng bộ một giá trị. Khi lambda trả về `Mono` của một I/O tiếp theo, dùng `flatMap` để nối pipeline. Dùng `map(cart -> carts.save(cart))` sẽ tạo `Mono<Mono<Cart>>`, không tự làm công việc lưu theo cách mong muốn.

**Không có dirty checking kiểu JPA.** Dù đồng bộ hay reactive, đổi một field Java object không tự cập nhật Couchbase. Phải gọi `save` hoặc operation ghi rõ ràng.

## 8. Trường hợp cần nhiều request Couchbase: phối hợp thay vì chặn

Giả sử trang tổng quan của khách hàng cần đồng thời đọc hồ sơ và giỏ hàng theo ID; hai document độc lập và đều có key.

Ví dụ một service có hai reactive repository:

~~~java
import reactor.core.publisher.Mono;

public Mono<CustomerDashboard> loadDashboard(
        String customerId) {

    Mono<Customer> profile = profiles.findById(
            "customer::" + customerId);
    Mono<Cart> cart = carts.findById(
            "cart::" + customerId);

    return Mono.zip(profile, cart)
            .map(tuple -> new CustomerDashboard(
                    tuple.getT1(), tuple.getT2()));
}
~~~

Ví dụ giả định `profiles`, `carts` đã được inject và `CustomerDashboard` là DTO nhận hai entity. `Mono.zip` có thể điều phối subscription tới hai Publisher, cho phép chúng tiến hành đồng thời thay vì bắt buộc chờ xong hồ sơ mới bắt đầu đọc giỏ. **Nếu một nguồn hoàn tất rỗng**, `zip` có thể hoàn tất không phát ra dashboard; phải quyết định mặc định giỏ rỗng hoặc trả lỗi tùy nghiệp vụ.

Trong service đồng bộ, cách trực quan thường là:

~~~java
Customer profile = profiles.findById(profileId).orElseThrow();
Cart cart = carts.findById(cartId).orElseThrow();
return new CustomerDashboard(profile, cart);
~~~

Hai câu này chạy tuần tự trên thread gọi, trừ khi ứng dụng chủ động bổ sung cơ chế song song khác. Reactive giúp biểu đạt pipeline bất đồng bộ, nhưng không đảm bảo mỗi truy vấn riêng lẻ giảm latency. Nếu cần chặn tuần tự vì ràng buộc nghiệp vụ, dùng `flatMap`/`concatMap` phù hợp thay vì song song hóa mù quáng.

## 9. Backpressure, giới hạn đồng thời và phân trang

**Backpressure** trong Reactive Streams cho phép downstream thể hiện mức nhu cầu tiêu thụ dữ liệu. Tuy vậy, không nên suy rằng một truy vấn SQL++ bị đánh `Flux` sẽ khiến Couchbase Server chỉ tạo từng hàng khi client yêu cầu. Hành vi phân trang, prefetch, buffering và khả năng hủy truy vấn phụ thuộc client, driver và API thực tế.

Ví dụ sau khi có danh sách ID, cần đọc từng document:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

public Flux<Cart> loadCarts(List<String> cartIds) {
    return Flux.fromIterable(cartIds)
            .flatMap(
                    id -> carts.findById(id),
                    8 // giới hạn tối đa số inner Publisher đang hoạt động
            );
}
~~~

Tham số `8` minh họa giới hạn concurrency; giá trị thực cần đo theo connection pool, khả năng đáp ứng của Couchbase, kích thước document và tải đồng thời. `flatMap` có thể trả kết quả **không theo thứ tự đầu vào**. Nếu phải giữ thứ tự, cân nhắc `flatMapSequential` hoặc `concatMap`, với đánh đổi về tốc độ/độ đồng thời.

Những nguyên tắc quan trọng:

- Dùng `LIMIT`/phân trang hợp lý cho truy vấn SQL++ ngay từ nguồn; không nạp hàng trăm nghìn document rồi mới lọc tại Java.
- `collectList()` gom toàn bộ dữ liệu về bộ nhớ. Chỉ dùng khi biết luồng hữu hạn và số phần tử đủ nhỏ.
- Đặt giới hạn kết quả và mức đồng thời cho tác vụ tải dữ liệu hàng loạt.
- Nếu kết quả đến từ Search Service, phải cân nhắc giữ ranking và loại bỏ document đã xóa trong thời gian hydrate.
- Quan sát query plan, độ trễ Index/Query Service và heap usage, thay vì chỉ kiểm tra số thread.

## 10. Những lỗi khi trộn blocking và reactive

### 10.1. `Mono.just(blockingCall())` vẫn chặn

**Sai:**

~~~java
Mono<Cart> getCart(String id) {
    return Mono.just(syncRepository.findById(id).orElseThrow());
}
~~~

Lệnh `findById` chạy **ngay trong lúc xây `Mono.just`**, làm thread bị chặn. Nó không biến operation thành non-blocking.

**Một giải pháp chuyển tiếp khi chưa thay được API blocking** là hoãn gọi và chạy trên scheduler dành cho blocking:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Cart> getCartWithLegacyClient(String id) {
    return Mono.fromCallable(
            () -> syncRepository.findById(id).orElseThrow()
    ).subscribeOn(Schedulers.boundedElastic());
}
~~~

Cách này giúp tránh block event-loop, nhưng **vẫn tiêu tốn thread để chờ I/O** và sử dụng bounded scheduler có giới hạn. Khi xây pipeline WebFlux lâu dài, nên dùng reactive repository/SDK thay vì biến mọi thao tác blocking thành task scheduler.

### 10.2. `block()` phá pipeline

**Sai trong một handler WebFlux:**

~~~java
Cart cart = reactiveRepository.findById(id).block();
return cart;
~~~

`block()` chờ kết quả và có thể làm tắc luồng xử lý request hoặc gây lỗi trên thread không cho phép blocking. Thay vào đó, trả `Mono<Cart>` cho WebFlux hoặc compose bằng các operator.

### 10.3. Không tự subscribe trong service

**Sai:**

~~~java
public void updateStatus(Cart cart) {
    carts.save(cart).subscribe();
}
~~~

Method trả trước khi thao tác được xác nhận; lỗi có thể bị bỏ qua và việc hủy request/transaction không còn được điều phối thống nhất. **Đúng hơn**, trả `Mono<Cart>` hoặc `Mono<Void>`, để tầng gọi quyết định kết hợp và subscribe.

### 10.4. Chọn sai `Mono` và `Flux`

Tìm khách hàng theo email có thể trả **nhiều document** nếu dữ liệu chưa bảo đảm uniqueness. Khai báo `Mono<Customer>` chỉ phù hợp khi hợp đồng dữ liệu chắc chắn 0..1 kết quả. Với query nhiều kết quả, dùng `Flux<Customer>` hoặc trả trang dữ liệu có giới hạn.

### 10.5. Retry mà không làm mới dữ liệu

Khi xảy ra CAS conflict, gọi retry trực tiếp trên cùng `save(cart)` với phiên bản cũ thường chỉ lặp lại xung đột. Cần **đọc lại**, áp dụng lại thay đổi nghiệp vụ trên version mới rồi retry có giới hạn, tránh lặp tác dụng phụ.

## 11. CAS và optimistic locking ở hai phong cách

Giả sử hai tab trình duyệt cùng thêm sản phẩm vào giỏ:

~~~text
T0: Tab A đọc cart, CAS=C1
T1: Tab B đọc cart, CAS=C1
T2: Tab A thêm SKU-X, save -> thành công, CAS=C2
T3: Tab B thêm SKU-Y trên dữ liệu cũ, save với C1 -> conflict
~~~

Couchbase quản lý CAS cho document. Spring Data có thể dùng `@Version` để phát hiện khi document đã thay đổi. Đây là cơ chế quan trọng vì reactive thường làm **nhiều request I/O đồng thời**, nhưng đồng bộ cũng có race condition tương tự.

Service reactive cập nhật có chủ đích:

~~~java
import reactor.core.publisher.Mono;

public Mono<Cart> markCheckout(String customerId) {
    return carts.findById("cart::" + customerId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Cart not found")))
            .flatMap(cart -> {
                cart.setStatus("CHECKOUT");
                return carts.save(cart);
            });
}
~~~

Khi `save` gặp optimistic locking failure, error signal phải được xử lý theo hợp đồng API: trả HTTP 409, yêu cầu refresh hoặc thử lại có giới hạn. Có thể dùng `Mono.defer` để tạo **mỗi lần retry là một lần đọc và áp dụng lại mutation**, thay vì retry thao tác ghi trên entity cũ. Tuy nhiên, chỉ retry an toàn khi nghiệp vụ idempotent và không lặp lại thanh toán, trừ tiền hay phát thông báo.

Với SDK, có thể dùng option CAS trong `replace` hoặc sub-document operation. Việc sử dụng SDK reactive không tự bỏ qua yêu cầu bảo vệ CAS, TTL hay durability.

## 12. SQL++, secondary index và nhất quán truy vấn

Nếu đã biết key `cart::u-123`, cả Repository đồng bộ và reactive có thể đi qua KV mà **không cần secondary index**. Nếu cần “tất cả giỏ ACTIVE cập nhật trong 24 giờ”, cần truy vấn theo field, thường qua SQL++ và một index phù hợp.

Ví dụ SQL++ (minh họa, không phải SQL++ Spring Data chắc chắn sinh):

~~~sql
SELECT META(c).id AS documentId,
       c.customerId, c.status, c.updatedAt
FROM `shop`.`sales`.`carts` AS c
WHERE c.status = "ACTIVE"
  AND c.updatedAt >= $fromTime
ORDER BY c.updatedAt DESC
LIMIT 50;
~~~

Index khởi đầu có thể là:

~~~sql
CREATE INDEX ix_carts_status_updated
ON `shop`.`sales`.`carts`(status, updatedAt DESC);
~~~

Trường `updatedAt` ở đây là dữ liệu nghiệp vụ **do ứng dụng phải ghi** nếu muốn truy vấn theo nó; Couchbase không tự thêm field này vào mọi JSON. Thiết kế index thực tế cần xem `EXPLAIN`, query được sinh ra, điều kiện discriminator và độ chọn lọc.

**Reactive không thay đổi cơ chế cập nhật secondary index.** Sau khi ghi qua KV, query SQL++ với scan consistency mặc định có thể tạm thời chưa thấy document mới. Khi cần read-your-writes ở query, nghiên cứu tùy chọn như `request_plus` hoặc consistency theo mutation state/token nếu API và phiên bản hỗ trợ, rồi đo ảnh hưởng độ trễ. Điều tương tự áp dụng với truy vấn Search Service khi Search index được cập nhật độc lập: nó không trở nên đồng bộ chỉ vì client trả về `Flux`.

## 13. Timeout, hủy, xử lý lỗi và quan sát

Trong code đồng bộ, các thao tác Couchbase thường hoàn tất bằng kết quả hoặc ném exception. Trong reactive, lỗi đi qua **`onError`**; timeout và cancellation cũng phải được xử lý xuyên suốt pipeline.

Ví dụ giới hạn thời gian ở ranh giới service:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<Cart> getCartWithTimeout(String id) {
    return carts.findById(id)
            .timeout(Duration.ofSeconds(2));
}
~~~

`timeout` làm Publisher phát lỗi nếu không có tín hiệu theo thời hạn. Tuy nhiên, không nên mặc định việc hủy Publisher bảo đảm truy vấn đang chạy ở server bị dừng tức thì; **timeout cấp SDK/request**, cancel propagation và chính sách retry của ứng dụng phải được xem xét cùng nhau.

Xử lý lỗi theo nhóm cụ thể:

- Document không tồn tại: biến thành 404 hoặc một giá trị vắng mặt đúng hợp đồng; `Mono.empty()` không nhất thiết là lỗi.
- CAS conflict: có thể trả 409 hoặc retry có kiểm soát sau khi đọc lại.
- Timeout/kết nối lỗi: áp dụng policy retry có giới hạn và backoff khi thao tác an toàn.
- Lỗi query/index: kiểm tra index, quyền, cú pháp SQL++ và query plan; không biến mọi lỗi thành danh sách rỗng.
- Lỗi xác thực/phân quyền: báo lỗi đúng và không log credential hay dữ liệu nhạy cảm.

**Không nên gọi `onErrorResume(e -> Mono.empty())` cho mọi lỗi.** Cách đó có thể che mất lỗi hệ thống và trả kết quả “không có dữ liệu” giả.

Chỉ số vận hành nên có:

| Chỉ số | Giúp trả lời |
| --- | --- |
| Request rate, p50/p95/p99 latency | Hệ thống có đáp ứng SLA dưới tải không? |
| Active requests, số thread/scheduler queue | Đang chờ blocking hay có bão hòa scheduler không? |
| KV latency và timeout | Data Service hoặc mạng có vấn đề? |
| SQL++ query latency, index scan/fetch | Index có thực sự phục vụ truy vấn? |
| CAS conflict rate | Document nào bị cập nhật cạnh tranh? |
| Error rate và retry count | Chính sách retry có khuếch đại tải? |
| CPU/heap/GC và cluster resource | Nút thắt ở ứng dụng hay Couchbase? |

## 14. TTL, durability và transaction không phụ thuộc reactive

### 14.1. TTL

TTL/expiry là metadata cho phép document tự hết hạn, phù hợp session, mã tạm hoặc giỏ khách vãng lai theo quy tắc sản phẩm. Chỉ thêm field JSON `expiresAt` không tự biến field đó thành expiry thực tế. Với cả API đồng bộ và reactive, cần hiểu option expiry, việc cập nhật có giữ hạn cũ hay thay và chính sách theo version SDK/Spring Data.

### 14.2. Durability

Durability liên quan mức xác nhận ghi bền khi mutation thành công. Chọn theo mức rủi ro và yêu cầu nghiệp vụ, không phụ thuộc method trả entity ngay hay trả `Mono<Entity>`. Mức durability cao hơn có thể tăng độ trễ và ảnh hưởng throughput.

### 14.3. Transaction

Một lệnh `save` trên một document khác với giao dịch đa document. Nếu tạo đơn hàng và trừ tồn kho cùng lúc, cần giao dịch hoặc workflow bù trừ phù hợp. Couchbase có API transaction trong các phiên bản hỗ trợ, nhưng **không tự suy từ việc một service reactive có `@Transactional` rằng mọi `Mono`/`Flux` đều nằm trong cùng transaction**. Phải kiểm tra transaction manager, cách đặt transaction boundary và khả năng tích hợp của bộ Spring Data/SDK/Server đang sử dụng.

### 14.4. CAS và reactive concurrency

Reactive tạo điều kiện phát sinh nhiều I/O đồng thời; nó không làm mọi cập nhật trở nên serializable. Số lượng consumer, concurrency của `flatMap` và optimistic locking phải được thiết kế cùng domain invariant. Với giỏ hàng đang được sửa liên tục, hiệu năng có thể bị hạn chế bởi **một document nóng**, chứ không phải bởi số thread.

## 15. Hướng dẫn ra quyết định

Chọn từ **workload và kiến trúc hiện tại**, thay vì chọn từ tên công nghệ.

~~~mermaid
flowchart TD
    A{"Ứng dụng đang dùng mô hình nào?"}
    A -->|Spring MVC, phần lớn dependencies blocking| B["Ưu tiên API đồng bộ"]
    A -->|WebFlux hoặc pipeline I/O non-blocking| C{"Các dependency chính có reactive API?"}
    C -->|Có| D["Ưu tiên Reactive Repository/Template/SDK"]
    C -->|Chưa đủ| E["Cô lập blocking tạm thời; cân nhắc migration"]
    B --> F["Đo latency/throughput/thread usage"]
    D --> F
    E --> F
    F --> G{"Nút thắt chủ yếu?"}
    G -->|Index / SQL++ / Couchbase Server| H["Tối ưu query, index và cluster"]
    G -->|Quá nhiều thread chờ I/O| I["Xem xét pipeline reactive"]
    G -->|CAS conflict / hot key| J["Xem lại aggregate và concurrency"]
~~~

### 15.1. Ma trận lựa chọn cho các trường hợp thực tế

| Trường hợp | Gợi ý | Lý do |
| --- | --- | --- |
| Ứng dụng CRUD nội bộ, vài chục request/giây, Spring MVC | Đồng bộ Repository | Đơn giản, đủ nhu cầu nếu đáp ứng số liệu |
| API WebFlux phục vụ rất nhiều request độc lập có I/O mạng | Reactive Repository/Template | Tận dụng non-blocking khi chờ Couchbase |
| Batch đồng bộ đang tích hợp nhiều JDBC/SDK blocking | Đồng bộ hoặc chạy song song có kiểm soát | Tránh chuyển cả pipeline phức tạp chỉ vì một dependency |
| API đọc hồ sơ và giỏ hàng cùng lúc | Reactive với `Mono.zip` nếu stack phù hợp | Ghép các I/O độc lập dễ đọc |
| Truy vấn SQL++ chậm do thiếu index | Thiết kế index/query plan | Đổi sang reactive không khắc phục |
| Lưu giỏ có xung đột CAS thường xuyên | Thiết kế aggregate và retry có điều kiện | Mô hình concurrency quan trọng hơn loại API |
| Search + lấy chi tiết 100 kết quả | Reactive có giới hạn đồng thời/phân trang | Tránh tạo 100 request KV đồng thời không kiểm soát |
| Service đòi hỏi transaction nhiều document | Xác nhận hỗ trợ transaction ở phiên bản đang dùng | Đảm bảo semantics trước khi chọn phong cách gọi |

**Câu hỏi cần trả lời trước khi quyết định:**

1. Hệ thống có thật sự thiếu thread do đang chờ I/O không?
2. Các thành phần chính (HTTP, database, message broker) có API non-blocking xuyên suốt không?
3. Query thực tế đi KV hay SQL++? Index đã phù hợp chưa?
4. Số lượng kết quả tối đa và mức đồng thời cần kiểm soát là bao nhiêu?
5. Những mutation nào cần CAS, TTL, durability hoặc transaction?
6. Đội ngũ có khả năng debug operator chains, cancellation, timeout và lỗi reactive không?
7. Kết quả load test nào cho thấy lựa chọn đáp ứng tốt hơn trên tải đại diện?

## 16. Bài tập áp dụng

Một ứng dụng học trực tuyến dùng Couchbase lưu hồ sơ, tiến độ học và phiên truy cập. Hệ thống có bốn tình huống:

1. **API MVC tải tiến độ theo cặp (studentId, courseId).** Đã biết document key, mức tải thấp.
2. **API WebFlux tải đồng thời hồ sơ và 5 khóa học gần nhất.** Có truy vấn theo field cần index.
3. **Bộ xử lý nền cập nhật tiến độ bài học từ nhiều thiết bị.** Một document có thể bị cập nhật cạnh tranh.
4. **Session tạm hết hạn sau 15 phút.** Người dùng không được dùng session quá hạn.

Hãy lựa chọn API và cơ chế cho từng tình huống.

| Tình huống | Gợi ý giải pháp | Điểm cần xác minh |
| --- | --- | --- |
| 1 | Đồng bộ Repository `findById` theo key đã quy ước | Không cần reactive nếu chưa có vấn đề thread |
| 2 | Reactive Repository/Template, ghép `zip`/`flatMap` và query có phân trang | Index, bảo toàn lỗi/empty, giới hạn đồng thời |
| 3 | `@Version`/CAS, đọc lại và retry có giới hạn | Không làm mất cập nhật, giữ invariant “tiến độ không lùi” |
| 4 | TTL/expiry thật sự trên document session | Hành vi khi cập nhật và tính đúng đắn xác thực session |

### Câu hỏi tự kiểm tra

**1.** `Mono<Cart>` có nghĩa `findById` chạy nhanh hơn `Optional<Cart>` không?

*Không. Mono mô tả mô hình kết quả bất đồng bộ; hiệu năng còn phụ thuộc I/O, index, tải và runtime.*

**2.** Vì sao `Mono.just(syncRepository.findById(id))` không non-blocking?

*Bởi lời gọi đồng bộ được thực thi trước khi Mono được tạo.*

**3.** Có nên gọi `subscribe()` trong service để “chắc chắn lưu” không?

*Thông thường không. Trả Publisher về tầng điều phối, để framework hoặc boundary phù hợp subscribe và xử lý lỗi.*

**4.** `flatMap` có giữ nguyên thứ tự kết quả khi nhiều inner Publisher chạy đồng thời không?

*Không bảo đảm. Nếu cần thứ tự, cân nhắc `flatMapSequential`/`concatMap` và chấp nhận đánh đổi.*

**5.** Khi `@Version` báo conflict, retry lại cùng `save` với entity cũ đã đủ chưa?

*Chưa. Cần đọc lại trạng thái mới, áp dụng lại thay đổi một cách an toàn và giới hạn số lần thử.*

**6.** API reactive có làm secondary index cập nhật ngay khi `save` hoàn tất không?

*Không. Tính nhất quán truy vấn SQL++/Search phải được thiết kế riêng.*

## 17. Kết luận

**Đồng bộ và reactive là hai cách tổ chức việc chờ và phối hợp I/O với Couchbase**, không phải hai kiểu database khác nhau. Với CRUD theo ID trong Spring MVC hoặc service có tải vừa phải, `CouchbaseRepository` đồng bộ thường đơn giản và phù hợp. Trong WebFlux hay ứng dụng có rất nhiều I/O đồng thời, `ReactiveCouchbaseRepository`, `ReactiveCouchbaseTemplate` và SDK reactive giúp xây dựng pipeline non-blocking, quản lý kết quả qua `Mono`/`Flux` và kiểm soát concurrency.

Dù chọn cách nào, tầng truy cập Spring Data Couchbase vẫn phải thiết kế đúng **bucket/scope/collection, document ID, index SQL++, CAS, TTL, transaction, consistency, timeout và quyền truy cập**. Quyết định tốt nhất dựa trên workload và số liệu vận hành: reactive giúp sử dụng thread hiệu quả hơn khi chờ mạng, còn index, thiết kế document và bất biến nghiệp vụ mới quyết định liệu dữ liệu được truy cập nhanh và chính xác hay không.
