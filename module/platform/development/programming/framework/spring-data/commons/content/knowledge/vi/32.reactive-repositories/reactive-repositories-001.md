# Reactive Streams, Publisher, Mono và Flux

## Mục tiêu và phạm vi

Repository reactive của Spring Data biểu diễn kết quả truy cập dữ liệu bằng các publisher thay vì trả ngay entity, collection hoặc giá trị đếm. Để dùng đúng abstraction này, cần hiểu giao thức Reactive Streams và hai kiểu thường gặp của Project Reactor: `Mono<T>` và `Flux<T>`.

Spring Data Commons cung cấp những hợp đồng như `ReactiveCrudRepository`. Module store và driver tương ứng mới quyết định việc truy cập dữ liệu được thực hiện như thế nào. Một kiểu trả về `Mono` không tự chứng minh rằng toàn bộ đường thực thi là non-blocking.

Sau bài học, bạn cần phân biệt được:

- `Publisher`, `Subscriber` và `Subscription` trong giao thức Reactive Streams.
- Kết quả không có phần tử, có một phần tử, có nhiều phần tử và kết quả lỗi.
- Việc xây dựng pipeline với việc thực thi pipeline qua subscription.
- Backpressure ở mức tín hiệu với giới hạn truy vấn, phân trang và giới hạn tài nguyên.
- Việc kết hợp thao tác repository với việc tự gọi `subscribe()` hoặc `block()`.

Ví dụ repository cụ thể trong bài dùng Spring Data R2DBC. Các khái niệm Reactor áp dụng rộng hơn, nhưng mapping, query, transaction và tính năng repository phải phù hợp với từng store.

## 1. Từ giá trị trả về đến chuỗi tín hiệu

Với một API đồng bộ, bên gọi thường chờ thao tác hoàn tất để nhận kết quả:

```java
Product product = repository.findById(id);
```

Đoạn trên chỉ minh họa hình thức gọi đồng bộ, không phải chữ ký chuẩn của `CrudRepository.findById`, vốn trả `Optional<T>`.

Với API reactive:

```java
Mono<Product> result = repository.findById(id);
```

`result` không phải một `Product`. Nó là publisher mô tả cách cung cấp kết quả khi được thực thi theo giao thức.

Một lần truy vấn có thể tạo ra các tín hiệu:

```text
Tìm thấy:
    onNext(product) -> onComplete

Không tìm thấy:
    onComplete

Truy vấn lỗi:
    onError(exception)
```

Với một truy vấn nhiều kết quả:

```text
onNext(product1)
    -> onNext(product2)
    -> ...
    -> onComplete
```

Chuỗi cũng có thể phát một số phần tử rồi lỗi, hoặc có thể là nguồn không hữu hạn. Không phải publisher nào cũng chắc chắn hoàn tất.

Điểm thay đổi quan trọng là bên gọi phải làm việc với cả **dữ liệu, sự vắng mặt, lỗi và thời điểm hoàn tất**, thay vì chỉ làm việc với một giá trị Java có sẵn.

## 2. Reactive Streams định nghĩa giao thức trao đổi

Reactive Streams là đặc tả cho việc truyền các phần tử giữa các thành phần theo cơ chế có điều phối nhu cầu. Trong hệ sinh thái Reactor và Spring Data, các interface cơ bản thường dùng thuộc package `org.reactivestreams`.

| Interface | Vai trò |
|---|---|
| `Publisher<T>` | Nguồn cung cấp chuỗi tín hiệu |
| `Subscriber<T>` | Bên nhận các phần tử và tín hiệu kết thúc |
| `Subscription` | Kênh để bên nhận yêu cầu thêm phần tử hoặc hủy |
| `Processor<T, R>` | Vừa là subscriber đầu vào, vừa là publisher đầu ra |

Các chữ ký cốt lõi có thể hình dung như sau:

```java
interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T item);
    void onError(Throwable error);
    void onComplete();
}

interface Subscription {
    void request(long n);
    void cancel();
}
```

Đây là phần trích lược để giải thích giao thức. Khi viết ứng dụng, import các interface thật thay vì tự định nghĩa lại chúng.

Chuỗi tương tác điển hình:

```text
Subscriber                         Publisher
    |                                  |
    |--------- subscribe ------------->|
    |<-------- onSubscribe ------------|
    |                                  |
    |--------- request(2) ------------>|
    |<-------- onNext(A) --------------|
    |<-------- onNext(B) --------------|
    |                                  |
    |--------- request(1) ------------>|
    |<-------- onNext(C) --------------|
    |<-------- onComplete -------------|
```

Một số quy tắc quan trọng:

- `onSubscribe` cung cấp subscription trước các tín hiệu dữ liệu.
- Publisher không được phát số lượng `onNext` vượt nhu cầu còn lại đã được yêu cầu.
- `request(n)` dùng số dương; các yêu cầu được cộng dồn theo quy tắc của giao thức.
- `onError` và `onComplete` là tín hiệu kết thúc loại trừ nhau.
- Sau tín hiệu kết thúc, chuỗi không tiếp tục phát dữ liệu.
- Tín hiệu hoàn tất hoặc lỗi không cần phải chờ một yêu cầu phần tử mới.
- `cancel()` yêu cầu dừng; không nên kỳ vọng sau đó luôn có `onComplete`.

Reactive Streams quy định giao thức, không tự cung cấp một database driver, một pool kết nối hay một transaction manager. Nó cũng không phải một lời hứa rằng publisher bất kỳ không chứa mã blocking.

Java còn có các interface tương tự dưới `java.util.concurrent.Flow`. Chúng là các kiểu khác với `org.reactivestreams`; không trộn import chỉ vì tên phương thức giống nhau.

## 3. Backpressure: bên nhận điều phối nhu cầu

Backpressure cho phép subscriber báo rằng nó sẵn sàng nhận thêm bao nhiêu phần tử, thay vì để nguồn đẩy vô hạn vào bộ nhớ của bên nhận.

Ví dụ khái niệm:

```text
Bên nhận xử lý chậm
    -> chỉ request một lượng nhỏ
    -> nguồn tuân thủ không phát quá nhu cầu còn lại
    -> bên nhận xử lý xong rồi request tiếp
```

Có thể quan sát demand bằng một subscriber minh họa:

```java
import org.reactivestreams.Subscription;

import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {

    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println(value);
        request(1);
    }
});
```

Đoạn trên dùng nguồn số trong bộ nhớ để minh họa giao thức; nó không chứng minh hành vi đọc dữ liệu của một driver. Trong ứng dụng WebFlux, thông thường framework là thành phần điều khiển subscription ở biên HTTP, không cần viết subscriber thủ công trong service.

### Backpressure không đồng nghĩa giới hạn truy vấn

Demand nhỏ không bảo đảm database chỉ thực hiện đúng chừng đó công việc. Driver có thể dùng batch, prefetch hoặc bộ đệm; database còn có chi phí thực thi truy vấn riêng.

Cần phân biệt:

| Cơ chế | Câu hỏi được giải quyết |
|---|---|
| `request(n)` | Downstream đang sẵn sàng nhận thêm bao nhiêu phần tử? |
| `limitRate(...)` | Nhu cầu được chia thành các đợt upstream như thế nào? |
| Giới hạn trong query | Store cần trả tối đa bao nhiêu kết quả theo truy vấn? |
| Phân trang | Lấy phần nào của một tập kết quả theo thứ tự xác định? |
| Giới hạn concurrency | Có bao nhiêu tác vụ con được thực hiện đồng thời? |
| Pool kết nối | Có bao nhiêu kết nối được sử dụng theo cấu hình? |

`take(10)` không tự trở thành một câu SQL có `LIMIT 10`. Nó giới hạn phần tử được nhận ở mức pipeline và có thể dẫn tới hủy upstream, nhưng mức công việc đã thực hiện còn phụ thuộc nguồn.

Tương tự, buffering không phải lúc nào cũng là cách giải quyết một nguồn nhanh hơn bên nhận. Bộ đệm không giới hạn có thể chuyển vấn đề thành áp lực bộ nhớ.

## 4. Publisher là hợp đồng; Mono và Flux là kiểu Reactor

`Publisher<T>` chỉ mô tả khả năng subscribe. Project Reactor cung cấp API phong phú để tạo và kết hợp publisher.

| Kiểu | Số phần tử dữ liệu | Kết thúc bình thường |
|---|---|---|
| `Mono<T>` | Không hoặc một | Sau không hoặc một `onNext` |
| `Flux<T>` | Không đến nhiều, có thể không hữu hạn | Khi nguồn kết thúc |
| `Mono<Void>` | Không có giá trị dữ liệu | Chỉ thể hiện hoàn tất thành công |

Cả `Mono` và `Flux` đều có thể kết thúc bằng lỗi. Cardinality không mô tả việc truy vấn thành công hay thất bại.

Các nguồn đơn giản:

```java
Mono<String> one = Mono.just("Spring Data");
Mono<String> none = Mono.empty();
Mono<String> failed = Mono.error(
        new IllegalStateException("Data source is unavailable")
);

Flux<Integer> many = Flux.just(1, 2, 3);
Flux<Integer> noItems = Flux.empty();
```

Reactor không phát `null` như một phần tử dữ liệu hợp lệ.

```java
String nullableName = null;

Mono<String> name = Mono.justOrEmpty(nullableName);
```

Trong ví dụ này, `name` hoàn tất rỗng. Không dùng `Mono.just(null)`, không trả `null` thay cho một `Mono` và không để hàm `map` trả `null` để biểu diễn không tìm thấy.

### Mono<Void> không có onNext

Một thao tác xóa có thể trả `Mono<Void>`:

```java
Mono<Void> deletion = repository.deleteById(id);
```

Nó cho biết thao tác hoàn tất hay lỗi, không cung cấp một `Boolean`, entity đã xóa hoặc số hàng bị ảnh hưởng.

Vì không có phần tử, `doOnNext` không phải nơi quan sát thành công của `Mono<Void>`. Nếu cần bước tiếp theo khi hoàn tất, dùng một phép kết hợp như `then(...)` hoặc `thenReturn(...)`.

Không suy từ completion rằng chắc chắn một entity đã tồn tại trước khi xóa. Semantics khi không có dữ liệu phải được đối chiếu với hợp đồng API và store.

## 5. Xây dựng pipeline khác với thực thi pipeline

Các publisher truy cập dữ liệu reactive thường được thiết kế để trì hoãn đường thực thi đến lúc subscription.

```java
Mono<Product> pending = repository.findById(10L);
```

Chỉ giữ biến `pending` không có nghĩa ứng dụng đã nhận được sản phẩm. Các operator tiếp theo xây dựng một mô tả xử lý:

```java
Mono<String> productName = repository.findById(10L)
        .map(Product::name);
```

Thành phần sử dụng cuối cùng mới subscribe để thực hiện pipeline. Trong WebFlux, controller có thể trả publisher cho framework. Trong kiểm thử Reactor, `StepVerifier` có thể là bên subscribe.

### Không phải mọi việc đặt cạnh Mono đều được trì hoãn

Java vẫn đánh giá đối số trước khi gọi phương thức:

```java
Mono<Product> wrong = Mono.just(blockingDao.findById(id));
```

Lời gọi `blockingDao.findById(id)` đã chạy trước khi `Mono.just` được tạo. Đổi kiểu biến sang `Mono<Product>` không thay đổi sự thật đó.

Tương tự:

```java
Mono<UUID> captured = Mono.just(UUID.randomUUID());
Mono<UUID> generatedPerSubscription =
        Mono.fromSupplier(UUID::randomUUID);
```

`captured` giữ UUID đã tạo lúc xây dựng nguồn. Nguồn thứ hai gọi supplier khi được subscribe.

Nếu cần trì hoãn cả việc tạo publisher:

```java
Mono<Product> deferred = Mono.defer(
        () -> repository.findById(id)
);
```

`defer` hữu ích khi nguồn phải được tạo theo ngữ cảnh hoặc trạng thái ở thời điểm subscription. Không cần bọc mọi repository call bằng `defer` một cách máy móc.

## 6. Cold, hot và việc subscribe nhiều lần

Nhiều publisher truy vấn dữ liệu là cold: mỗi subscription có thể bắt đầu một lần thực hiện nguồn riêng.

```java
Mono<Product> query = repository.findById(10L);
```

Nếu pipeline này được subscribe hai lần, không mặc định rằng lần thứ hai dùng lại kết quả từ lần đầu. Nó có thể thực hiện thêm một truy vấn.

Điều này đặc biệt quan trọng với thao tác ghi:

```text
Một publisher lưu dữ liệu
    -> subscription thứ nhất: thực hiện một lần ghi
    -> subscription thứ hai: có thể thực hiện lại đường ghi
```

Một nguồn hot có thể phát dữ liệu theo một vòng đời chia sẻ, không chờ từng subscriber bắt đầu lại từ đầu. Các operator như chia sẻ hoặc cache còn làm thay đổi hành vi subscription.

Vì vậy:

- Không coi mọi `Publisher` là một truy vấn cold giống nhau.
- Không thêm `cache()` chỉ để tránh truy vấn lặp mà chưa xác định thời hạn và dữ liệu có thể cũ.
- Không tự subscribe trong service rồi lại trả cùng publisher cho controller.
- Không dùng việc retry như một phép “thử lại giá trị”; retry có thể subscribe lại và lặp tác dụng phụ.

Publisher là mô tả nguồn tín hiệu, không phải một biến đã chứa sẵn kết quả cuối cùng.

## 7. Hợp đồng ReactiveCrudRepository trong Spring Data Commons

Interface thường dùng:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
```

Một số dạng kết quả cơ bản:

| Thao tác | Kiểu kết quả điển hình | Ý nghĩa |
|---|---|---|
| `findById(id)` | `Mono<T>` | Không hoặc một entity |
| `findAll()` | `Flux<T>` | Chuỗi entity |
| `save(entity)` | `Mono<S>` | Entity sau thao tác lưu |
| `saveAll(...)` | `Flux<S>` | Các entity sau khi lưu |
| `count()` | `Mono<Long>` | Một giá trị đếm khi truy vấn hoàn tất |
| `existsById(id)` | `Mono<Boolean>` | Một giá trị thể hiện kết quả kiểm tra |
| `deleteById(id)` | `Mono<Void>` | Tín hiệu hoàn tất hoặc lỗi |

Một `Mono<Boolean>` phát `false` khác với `Mono.empty()`: trường hợp đầu có một giá trị dữ liệu, trường hợp sau không có giá trị.

Một `Flux<T>` rỗng cũng khác với lỗi truy vấn. “Không có bản ghi phù hợp” thường là kết quả hợp lệ; mất kết nối database là lỗi.

Các hợp đồng chung không quyết định mọi khả năng của store. Cần xác minh riêng:

- Driver và module có hỗ trợ repository reactive hay không.
- Cú pháp derived query, query annotation và kiểu projection được hỗ trợ.
- Khả năng sắp xếp, giới hạn kết quả và phân trang.
- Mapping, conversion, optimistic locking và transaction.

Spring Data JPA sử dụng JPA/JDBC đồng bộ, không trở thành repository non-blocking chỉ bằng cách đổi chữ ký sang `Mono` hoặc `Flux`. R2DBC và module MongoDB reactive là các hướng tích hợp có hạ tầng reactive tương ứng.

## 8. Ví dụ R2DBC: entity, repository và DTO

Ví dụ dùng một bảng `product`. Database cần schema và chiến lược cấp ID phù hợp; định nghĩa record không tự tạo bảng.

```java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price,
        boolean active
) {
}
```

Repository:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByActiveTrue();
}
```

Derived query ở đây biểu diễn điều kiện trên thuộc tính `active`. Khả năng hiểu tên method và chuyển nó thành query thuộc module R2DBC.

DTO:

```java
import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price
) {

    public static ProductView from(Product product) {
        return new ProductView(
                product.id(),
                product.name(),
                product.price()
        );
    }
}
```

Mỗi kiểu public được hiểu là một đơn vị mã nguồn riêng. Ứng dụng còn cần dependency, connection factory và cấu hình repository phù hợp với R2DBC; Commons một mình không cung cấp database connection.

Nếu chuyển sang MongoDB reactive, cần mapping document và cấu hình của MongoDB. Các ý tưởng về `Mono` và `Flux` vẫn dùng được, nhưng annotation mapping của ví dụ không tự chuyển thành mapping MongoDB.

## 9. map, flatMap và flatMapMany

### 9.1. map biến một giá trị thành giá trị khác

```java
Mono<ProductView> view = repository.findById(id)
        .map(ProductView::from);
```

Hàm trong `map` nhận `Product` và trả `ProductView`. Nó phù hợp với chuyển đổi giá trị nhanh, không blocking.

Nếu nguồn rỗng, hàm chuyển đổi không được gọi. Nếu nguồn lỗi, lỗi được truyền tiếp trừ khi có xử lý phù hợp.

### 9.2. flatMap nối một thao tác trả publisher

Giả sử cần đọc sản phẩm rồi lưu một giá mới:

```java
Mono<Product> updated = repository.findById(id)
        .flatMap(existing -> repository.save(
                new Product(
                        existing.id(),
                        existing.name(),
                        newPrice,
                        existing.active()
                )
        ));
```

Hàm truyền vào `flatMap` trả `Mono<Product>`. Operator kết hợp thao tác đó vào cùng pipeline.

Nếu dùng `map` cho cùng hàm:

```java
Mono<Mono<Product>> nested = repository.findById(id)
        .map(existing -> repository.save(
                new Product(
                        existing.id(),
                        existing.name(),
                        newPrice,
                        existing.active()
                )
        ));
```

kết quả là publisher lồng publisher. Phát ra một `Mono` bên trong không đồng nghĩa thao tác lưu bên trong đã được kết hợp và thực thi đúng như mong muốn.

Đường đọc rồi lưu còn cần chính sách cạnh tranh và transaction nếu nghiệp vụ yêu cầu. `flatMap` kết hợp tín hiệu; nó không tự tạo khóa hay chống mất cập nhật.

### 9.3. flatMapMany chuyển từ một giá trị sang nhiều giá trị

Nếu một `Mono<Customer>` cần dẫn tới một truy vấn trả nhiều đơn hàng, kết quả thích hợp là `Flux<Order>`:

```java
Flux<Order> orders = customerRepository.findById(customerId)
        .flatMapMany(customer ->
                orderRepository.findByCustomerId(customer.id()));
```

Đoạn này chỉ minh họa hình dạng kết hợp, giả định các repository và kiểu miền đã được định nghĩa.

Với một `Flux`, `flatMap` có thể kết hợp nhiều publisher con đồng thời và xen kẽ kết quả. Nếu cần xử lý tuần tự theo thứ tự nguồn, `concatMap` là một lựa chọn cần hiểu. Không mặc định `flatMap` bảo toàn thứ tự hoàn tất.

Giới hạn concurrency của `flatMap` cũng cần phù hợp với tài nguyên store. Non-blocking không có nghĩa có thể gửi số lượng truy vấn đồng thời không giới hạn.

## 10. Service trả pipeline hoàn chỉnh

Ví dụ sau kết hợp đọc, xử lý không tìm thấy và cập nhật:

```java
import java.math.BigDecimal;
import java.util.NoSuchElementException;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductView> find(long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new NoSuchElementException(
                                "Product not found: " + id
                        )
                ))
                .map(ProductView::from);
    }

    public Flux<ProductView> findActive() {
        return repository.findByActiveTrue()
                .map(ProductView::from);
    }

    public Mono<ProductView> changePrice(
            long id,
            BigDecimal newPrice
    ) {
        if (newPrice == null || newPrice.signum() < 0) {
            return Mono.error(new IllegalArgumentException(
                    "Price must be non-negative"
            ));
        }

        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new NoSuchElementException(
                                "Product not found: " + id
                        )
                ))
                .flatMap(existing -> repository.save(
                        new Product(
                                existing.id(),
                                existing.name(),
                                newPrice,
                                existing.active()
                        )
                ))
                .map(ProductView::from);
    }
}
```

Service không tự gọi `subscribe()`. Bên gọi nhận một pipeline chứa cả thao tác chính, lỗi và kết quả.

Nếu dùng WebFlux, controller có thể trả publisher:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/active")
    public Flux<ProductView> active() {
        return service.findActive();
    }
}
```

Framework quản lý subscription để xử lý response. Cách ánh xạ lỗi nghiệp vụ sang mã HTTP cần được thiết kế ở lớp web; kiểu exception trong service không tự xác định một hợp đồng HTTP hoàn chỉnh.

Khi lưu một entity bất biến như record, dùng entity mà `save` phát ra. Store có thể trả một instance mới chứa ID hoặc metadata vừa được gán; không mặc định instance đầu vào đã tự thay đổi.

## 11. Phân biệt rỗng, lỗi và hoàn tất không có giá trị

Ba trạng thái này có mục đích khác nhau:

| Trạng thái | Ví dụ | Cách xử lý điển hình |
|---|---|---|
| Không tìm thấy giá trị | `findById` hoàn tất rỗng | `switchIfEmpty`, `defaultIfEmpty` hoặc giữ rỗng |
| Lỗi | Driver phát `onError` | Truyền lỗi, ánh xạ lỗi hoặc phục hồi có chủ đích |
| Thành công không có dữ liệu | `Mono<Void>` hoàn tất | `then`, `thenReturn` hoặc chỉ chờ hoàn tất |

### 11.1. switchIfEmpty không phải xử lý mọi lỗi

```java
repository.findById(id)
        .switchIfEmpty(Mono.error(
                new NoSuchElementException("Product not found")
        ));
```

Đoạn trên chuyển kết quả rỗng thành lỗi nghiệp vụ. Nó không biến lỗi kết nối thành “không tìm thấy”.

Không nên dùng một fallback quá rộng như:

```java
repository.findById(id)
        .onErrorResume(error -> Mono.empty());
```

nếu việc đó khiến mọi lỗi database bị che thành kết quả không có dữ liệu. Chỉ phục hồi những loại lỗi mà nghiệp vụ thực sự cho phép.

### 11.2. then nối theo tín hiệu hoàn tất

```java
Mono<String> result = repository.deleteById(id)
        .thenReturn("Deletion operation completed");
```

`thenReturn` phát chuỗi sau khi upstream hoàn tất thành công. Nếu upstream lỗi, lỗi vẫn được truyền tiếp.

Nó cũng bỏ qua dữ liệu upstream nếu có. Vì thế, đừng dùng `thenReturn` khi cần giá trị entity sau khi lưu; hãy dùng `map` trên kết quả `save`.

### 11.3. zip cần phần tử từ các nguồn dữ liệu

Khi kết hợp hai `Mono` bằng `zip`, mỗi nguồn cần cung cấp phần tử để tạo kết quả kết hợp. Nếu một nguồn hoàn tất rỗng, không có đủ giá trị để gọi hàm kết hợp.

Điều này dễ gây nhầm khi dùng `Mono<Void>` với `zip`: hoàn tất thành công không đồng nghĩa phát ra một giá trị `Void`.

Nếu mục tiêu là chờ các thao tác hoàn tất mà không cần ghép dữ liệu, chọn operator có semantics hoàn tất phù hợp thay vì cố ghép các phần tử không tồn tại.

### 11.4. Operator quan sát không thay đổi ý nghĩa nguồn

`doOnNext` và `doOnError` thường dùng để quan sát, không thay thế `map`, `flatMap` hay một cơ chế phục hồi lỗi.

Với `Mono`, `doOnSuccess` còn có thể nhận `null` khi nguồn hoàn tất rỗng. Đây là giá trị tham số callback quan sát, không phải một phần tử `null` được phát qua `onNext`.

## 12. Non-blocking, scheduler và mã legacy

Reactive không đồng nghĩa mỗi thao tác có một thread mới. Một driver non-blocking có thể tiếp tục công việc khi có tín hiệu I/O, thay vì giữ một thread chờ kết quả cho từng request.

Tuy nhiên, nếu gọi JDBC, JPA hoặc một thư viện blocking ngay trong operator:

```java
source.map(value -> blockingClient.call(value));
```

thread đang chạy operator vẫn bị chặn trong lời gọi đó.

### 12.1. block() là một ranh giới đồng bộ

`block()` subscribe rồi chờ kết quả trên thread gọi nó. Nếu đặt trong service reactive hoặc event loop, nó phá vỡ cách phối hợp non-blocking và có thể bị từ chối trên những thread không cho phép blocking.

Không dùng `block()` để “lấy entity ra khỏi Mono” rồi tiếp tục xử lý trong một endpoint reactive. Hãy kết hợp bằng operator.

Một ứng dụng đồng bộ hoặc công cụ dòng lệnh có thể chọn một ranh giới chờ có chủ đích. Điều đó cần được phân biệt với việc chặn tùy tiện bên trong pipeline của server.

### 12.2. Bọc mã blocking khi phải tích hợp tạm thời

Khi cần gọi một API legacy blocking, một mẫu cầu nối thường gặp là:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Product> legacyResult = Mono
        .fromCallable(() -> blockingDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Ví dụ giả định DAO trả `Product` hoặc `null`; `fromCallable` hoàn tất rỗng nếu callable trả `null`.

Hai phần có nhiệm vụ riêng:

- `fromCallable` trì hoãn việc gọi DAO đến subscription.
- `subscribeOn` bố trí việc thực thi nguồn đó trên scheduler phù hợp cho công việc blocking.

Cầu nối vẫn sử dụng thread trong thời gian DAO chờ. Nó không biến JDBC thành driver non-blocking, không loại bỏ giới hạn kết nối và không làm JPA trở thành `ReactiveCrudRepository`.

Thêm `publishOn` phía sau một lời gọi blocking đã thực hiện ngay lúc xây dựng pipeline không thể quay ngược thời gian để di chuyển lời gọi đó sang thread khác.

## 13. subscribe(), retry và transaction phải có ranh giới rõ ràng

### 13.1. Không tách subscription trong service

Cách dễ sai:

```java
public Mono<Void> delete(long id) {
    repository.deleteById(id).subscribe();
    return Mono.empty();
}
```

Publisher được trả về không còn biểu diễn thao tác xóa. Bên gọi có thể thấy hoàn tất trước khi xóa xong; lỗi, cancellation và transaction context cũng không còn được phối hợp như một chuỗi thống nhất.

Cách phù hợp với service reactive:

```java
public Mono<Void> delete(long id) {
    return repository.deleteById(id);
}
```

Ứng dụng vẫn cần một biên subscribe cuối cùng, nhưng biên đó nên thuộc thành phần điều khiển vòng đời như framework, chương trình chạy tác vụ hoặc công cụ kiểm thử.

### 13.2. retry thực hiện lại nguồn

`retry` thường hoạt động bằng cách subscribe lại khi nguồn lỗi. Với truy vấn đọc, đó có thể là một lần truy vấn mới. Với thao tác ghi hoặc gọi dịch vụ ngoài, đó có thể là một lần thực hiện tác dụng phụ mới.

Chỉ retry theo những lỗi, giới hạn và chính sách idempotency phù hợp. Reactive không tự bảo đảm thao tác ghi được thực hiện đúng một lần.

### 13.3. Transaction reactive phụ thuộc hạ tầng phù hợp

Có `Mono` hoặc `Flux` không tự tạo transaction. Transaction reactive cần transaction manager và cơ chế tích hợp thích hợp với store.

Với hạ tầng transaction reactive của Spring, ngữ cảnh transaction đi theo reactive execution context, không nên được hiểu như một transaction đồng bộ chỉ gắn với thread gọi method.

Việc tự tạo subscription ở giữa pipeline có thể tách thao tác ra khỏi ngữ cảnh mà ứng dụng muốn dùng. Thay đổi scheduler cũng không phải cơ chế tự chuyển một transaction JPA đồng bộ thành transaction R2DBC.

## 14. Streaming không thay thế phân trang và sắp xếp

Một `Flux<Product>` mô tả chuỗi sản phẩm. Nó không tự mang metadata như tổng số phần tử, số trang hoặc tổng số trang.

Cần thiết kế riêng khi API cần:

- Giới hạn số kết quả.
- Một thứ tự ổn định.
- Offset hoặc cursor.
- Tổng số phần tử.
- Chính sách nhất quán giữa truy vấn dữ liệu và truy vấn đếm.

Nếu store hỗ trợ tham số `Pageable` hoặc `Sort` cho một dạng query reactive, phải dùng theo hợp đồng của module. Không sao chép mọi chữ ký repository đồng bộ rồi mặc định các kiểu `Page`, `Slice` và publisher đều kết hợp được như nhau.

`collectList()` có thể chuyển một `Flux<Product>` thành `Mono<List<Product>>`, nhưng nó gom toàn bộ phần tử đến khi nguồn hoàn tất. Điều đó:

- Dùng bộ nhớ theo kích thước kết quả.
- Trì hoãn việc cung cấp list cuối cùng đến khi thu thập xong.
- Không cho ra list hoàn chỉnh với nguồn không bao giờ kết thúc.
- Không tạo metadata phân trang.

Nếu chỉ cần tổng số bản ghi, một truy vấn đếm của repository có thể phù hợp hơn việc tải toàn bộ entity rồi đếm trong ứng dụng.

## 15. Kiểm tra pipeline và điều tra lỗi

Reactor Test cung cấp `StepVerifier` để subscribe và xác minh tín hiệu trong kiểm thử.

Ví dụ không cần database:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(
        Mono.just("Spring").map(String::length)
)
        .expectNext(6)
        .verifyComplete();
```

Kiểm tra kết quả rỗng:

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();
```

Kiểm tra demand trên một nguồn đơn giản:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.range(1, 3), 0)
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();
```

Các ví dụ trên xác minh tín hiệu Reactor, không chứng minh mapping hoặc khả năng non-blocking của driver.

Với repository thật, cần dựng dữ liệu và application context phù hợp để kiểm tra thêm:

| Kịch bản | Điều cần quan sát |
|---|---|
| Tìm ID tồn tại | Một entity rồi hoàn tất |
| Tìm ID không tồn tại | Hoàn tất rỗng theo hợp đồng truy vấn |
| Query không có kết quả | `Flux` rỗng, không bị coi là lỗi |
| Store phát lỗi | Lỗi được truyền và ánh xạ có chủ đích |
| Lưu entity có ID được store cấp | Sử dụng đúng entity phát ra từ `save` |
| Thao tác trả `Mono<Void>` | Kiểm tra completion, không chờ một phần tử |
| Transaction gồm nhiều bước | Commit/rollback theo hạ tầng reactive đã cấu hình |

Những dấu hiệu thường gặp khi điều tra:

| Hiện tượng | Câu hỏi cần kiểm tra |
|---|---|
| Không thấy truy vấn chạy | Publisher đã được subscribe chưa, có bị bỏ đi không? |
| Truy vấn chạy hai lần | Có nhiều subscription, retry hoặc nguồn cold được dùng lại không? |
| Không đi vào `map` | Nguồn có hoàn tất rỗng hoặc lỗi trước đó không? |
| Lưu không chạy sau khi đọc | Có dùng `map` tạo publisher lồng thay vì `flatMap` không? |
| `Mono<Void>` không chạy `doOnNext` | Có đang nhầm completion với một phần tử dữ liệu không? |
| Bộ nhớ tăng khi trả nhiều kết quả | Có `collectList`, buffering hoặc concurrency không phù hợp không? |
| Server chậm dù dùng `Mono` | Có thao tác blocking hoặc pool kết nối bị giới hạn không? |
| Lỗi database biến thành “không có dữ liệu” | Có fallback quá rộng đang nuốt lỗi không? |
| Metadata phân trang bị thiếu | Có đang kỳ vọng `Flux` tự mang thông tin trang không? |

## 16. Bài thực hành

Với một store có hỗ trợ reactive repository, xây dựng chức năng đọc và sửa giá sản phẩm:

1. Khai báo repository trả `Mono` cho một kết quả và `Flux` cho nhiều kết quả.
2. Tạo pipeline đọc một sản phẩm rồi chuyển sang DTO bằng `map`.
3. Xử lý ID không tồn tại bằng một chính sách rõ ràng.
4. Nối thao tác đọc và lưu bằng `flatMap`.
5. Trả publisher từ service lên biên thực thi, không tự subscribe ở giữa.
6. Kiểm tra kết quả rỗng, kết quả có dữ liệu, lỗi và completion của `Mono<Void>`.
7. Quan sát số lần truy vấn khi một nguồn được subscribe nhiều lần.
8. Giải thích vì sao giới hạn demand không tự thay thế phân trang, và vì sao bọc JPA bằng `Mono` chưa tạo ra truy cập dữ liệu non-blocking.

Điểm cần giải thích được là: **Reactive Streams quy định cách trao đổi tín hiệu và nhu cầu; Publisher là hợp đồng nguồn; Mono và Flux biểu diễn cardinality và cung cấp operator; Spring Data ghép các hợp đồng đó với khả năng thực tế của từng store**.