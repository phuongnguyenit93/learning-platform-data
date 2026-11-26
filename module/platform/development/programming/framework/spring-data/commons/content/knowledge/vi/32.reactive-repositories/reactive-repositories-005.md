# Thời điểm thực thi khi subscription bắt đầu

Khi gọi một repository reactive, giá trị nhận được thường là `Mono<T>` hoặc `Flux<T>`, không phải kết quả truy vấn đã sẵn có. Với các publisher lạnh do repository reactive thông dụng cung cấp, thao tác truy cập dữ liệu được kích hoạt khi có subscription, rồi tiến triển theo giao thức reactive và cách driver triển khai.

Điều này khác với việc nói rằng mọi dòng Java đều chờ đến subscription. Đối số phương thức, constructor, việc kiểm tra đầu vào và mã viết trực tiếp trong một phương thức vẫn có thể chạy ngay lúc tạo pipeline.

Bài học thuộc chương **Repository reactive** của module **SPRING_DATA_COMMONS**. Trọng tâm là vòng đời thực thi của abstraction repository và CRUD reactive, cách ghép các thao tác dữ liệu, và những giới hạn cần xét theo store, driver và transaction manager thực tế.

## 1. Bốn mốc cần phân biệt

Xét:

```java
Mono<Product> result = products.findById("p-01");
```

Không nên diễn giải rằng dòng trên đã trả về một `Product`. Nó trả về một publisher mô tả cách lấy kết quả.

| Mốc | Việc có thể diễn ra |
| --- | --- |
| Gọi phương thức Java | Tính đối số, chạy mã trong phương thức, kiểm tra đầu vào hoặc chọn nhánh |
| Tạo pipeline, còn gọi là assembly | Kết hợp source với các operator và tạo publisher kết quả |
| Subscription | Kết nối subscriber với pipeline, đăng ký subscription và bắt đầu vòng đời source |
| Truy cập dữ liệu và phát tín hiệu | Driver thực hiện công việc theo triển khai; phát dữ liệu, hoàn tất hoặc báo lỗi |

Với repository reactive dùng publisher lạnh, chỉ giữ một biến `Mono` chưa đủ để hoàn thành thao tác đọc hoặc ghi. Tuy nhiên, thời điểm chính xác driver lấy connection, gửi câu lệnh hoặc nhận phản hồi phụ thuộc module và driver.

### 1.1. Một ví dụ chỉ tạo pipeline

```java
public Mono<Product> load(String id) {
    System.out.println("Building load pipeline");

    return products.findById(id)
            .doOnNext(product ->
                    System.out.println("Received: " + product.id()));
}
```

Khi gọi:

```java
Mono<Product> pending = load("p-01");
```

dòng `Building load pipeline` chạy ngay vì đó là mã Java trực tiếp trong phương thức. Callback `doOnNext` chỉ chạy khi pipeline được subscribe và thực sự nhận được một phần tử.

Nếu không tìm thấy sản phẩm, `Mono` có thể hoàn tất rỗng; khi đó không có `onNext`, nên callback trên không in thông báo nhận sản phẩm.

### 1.2. Tính lazy có phạm vi

Có thể nói thao tác dữ liệu của một publisher lạnh được hoãn đến subscription. Không nên nói toàn bộ phương thức Java chứa publisher đều lazy.

Ví dụ:

```java
Mono<Product> pending = products.findById(validateAndNormalize(rawId));
```

`validateAndNormalize(rawId)` được gọi trước khi `findById` nhận đối số. Nếu hàm đó ném exception, lỗi có thể xảy ra trước khi có bất kỳ subscription nào.

Ngay cả một phương thức repository cũng có thể phát hiện đầu vào không hợp lệ sớm. Không mặc định mọi lỗi đều được chuyển thành `onError` sau subscription.

## 2. Abstraction của Spring Data Commons và khả năng của store

Một repository cơ bản có thể khai báo:

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, String> {
}
```

Mô hình miền dùng trong các ví dụ:

```java
import org.springframework.data.annotation.Id;

public record Product(@Id String id, String name) {

    public Product withName(String newName) {
        return new Product(id, newName);
    }
}
```

Ví dụ giả định dữ liệu đọc đã tồn tại và `Product` được ánh xạ phù hợp với store đã chọn. Cấu hình repository, collection/table, driver và quy tắc nhận diện entity mới cần được bổ sung trong dự án thực hành.

`ReactiveCrudRepository` cung cấp hợp đồng dùng chung cho các thao tác như:

```java
Mono<Product> findById(String id);
Flux<Product> findAll();
Mono<Product> save(Product product);
Mono<Void> deleteById(String id);
```

Các chữ ký trên minh họa những kiểu trả về khi thay thế generic bằng `Product` và `String`; interface thực tế có khai báo generic và các overload tương ứng.

Spring Data Commons không tự biến một driver blocking thành non-blocking. Cần một store module và driver hỗ trợ reactive, chẳng hạn cách tích hợp reactive phù hợp cho MongoDB hoặc R2DBC.

Việc đổi kiểu trả về của một lời gọi JPA thành `Mono` không làm JDBC/JPA tự trở thành truy cập dữ liệu non-blocking.

### 2.1. Publisher lạnh là giả định cần được hiểu đúng

Với publisher lạnh, mỗi subscription bắt đầu một lần thực thi theo source. Đây là mô hình thông dụng của các thao tác truy cập dữ liệu reactive được dùng trong bài.

Tuy nhiên, kiểu `Mono` hoặc `Flux` tự nó chưa chứng minh một source là lạnh. Một repository fragment có thể trả về publisher đã `cache`, được chia sẻ hoặc được tạo từ một nguồn khác.

Khi viết thành phần mở rộng repository, cần công bố rõ hợp đồng: dữ liệu được lấy lại cho mỗi subscriber, được phát lại từ cache hay đến từ một luồng đã hoạt động.

## 3. Subscription, demand và tín hiệu

Một tương tác có thể được hình dung:

```text
Tạo pipeline
     |
     | subscribe
     v
Subscriber nhận onSubscribe(subscription)
     |
     | request(n)
     v
Source có thể phát onNext theo demand
     |
     +--> onComplete
     |
     +--> onError
```

Đây là mô hình tín hiệu, không phải sơ đồ cam kết thứ tự của từng câu lệnh mạng hoặc từng lần lấy connection.

### 3.1. Subscription khác với yêu cầu số phần tử

`subscribe` thiết lập quan hệ với subscriber. `request(n)` thể hiện nhu cầu nhận dữ liệu.

Các overload tiện dụng như `subscribe(value -> ...)` thường yêu cầu dữ liệu theo cách không giới hạn số phần tử. Một subscriber tùy biến có thể điều khiển demand tường minh.

Không suy ra rằng có subscription là mọi kết quả đã được đọc hết. Cũng không suy ra rằng demand bằng không bảo đảm driver chưa lấy connection hay chưa gửi bất kỳ lệnh nào. Reactive Streams điều khiển việc phát dữ liệu theo demand; mức độ hoãn công việc bên trong còn phụ thuộc source và driver.

Tín hiệu kết thúc như `onComplete` hoặc `onError` không phải phần tử dữ liệu và có thể xuất hiện mà không cần một yêu cầu nhận phần tử dương trước đó.

### 3.2. Mono và Flux có cardinality khác nhau

| Kiểu | Số phần tử thành công | Ví dụ repository |
| --- | --- | --- |
| `Mono<Product>` | Không hoặc một | `findById`, `save` |
| `Flux<Product>` | Không đến nhiều | `findAll` |
| `Mono<Void>` | Không phát giá trị nghiệp vụ | `deleteById` |

Một `Mono<Product>` hoàn tất rỗng vẫn là một lần subscription và một kết quả hợp lệ cho truy vấn không tìm thấy dữ liệu. Không có `onNext` không đồng nghĩa pipeline chưa chạy.

Với `Mono<Void>`, không dùng `doOnNext` để chứng minh thao tác đã hoàn tất:

```java
products.deleteById(id)
        .doOnNext(ignored -> System.out.println("Deleted"));
```

Publisher này không có phần tử để truyền cho callback. Nếu cần tiếp tục sau khi source hoàn tất thành công, dùng operator dựa trên completion:

```java
Mono<String> result = products.deleteById(id)
        .thenReturn("Delete operation completed");
```

Kết quả trên diễn đạt completion của thao tác, không tự chứng minh rằng trước đó chắc chắn tồn tại một bản ghi hoặc transaction ngoài đã commit.

### 3.3. Quan sát các mốc bằng operator

```java
Mono<Product> operation = products.findById("p-01")
        .doOnSubscribe(subscription ->
                System.out.println("Subscribed"))
        .doOnRequest(amount ->
                System.out.println("Requested: " + amount))
        .doOnNext(product ->
                System.out.println("Value: " + product.id()))
        .doOnError(error ->
                System.out.println("Error: " + error.getClass().getSimpleName()))
        .doFinally(signal ->
                System.out.println("Finished with: " + signal));
```

Đoạn khai báo vẫn chỉ tạo pipeline. Các callback quan sát chạy theo tín hiệu khi publisher được sử dụng.

Không đọc một dòng `Subscribed` như bằng chứng rằng SQL đã gửi hoặc document đã được lưu. Nó cho biết subscription đã đi qua điểm quan sát đó trong pipeline.

## 4. Ai thực sự subscribe?

### 4.1. Spring WebFlux thường quản lý subscription ở biên HTTP

Controller có thể trả nguyên publisher:

```java
@GetMapping("/products/{id}")
public Mono<Product> find(@PathVariable String id) {
    return products.findById(id);
}
```

Ví dụ dùng annotation của Spring Web và giả định controller được cấu hình trong ứng dụng WebFlux. Trong luồng xử lý HTTP, framework sử dụng publisher trả về và điều phối subscription cùng việc ghi response.

Controller không cần gọi `subscribe()` chỉ để bắt đầu truy vấn. Việc trả publisher cho framework giữ được đường truyền lỗi, cancellation và context của request.

### 4.2. Tạo pipeline rồi bỏ đi không tạo công việc nền

Ví dụ sai trong service:

```java
public Mono<Void> remove(String id) {
    products.deleteById(id);
    return Mono.empty();
}
```

Publisher xóa bị bỏ đi. Publisher trả về chỉ hoàn tất rỗng và không ghép với thao tác xóa.

Dạng đúng là:

```java
public Mono<Void> remove(String id) {
    return products.deleteById(id);
}
```

Đối với publisher lạnh thông thường, thao tác xóa sẽ tham gia lần subscription của caller vào kết quả trả về.

### 4.3. Một số API khác cũng tạo subscription

| Thao tác | Ý nghĩa liên quan đến subscription |
| --- | --- |
| Gọi `subscribe(...)` | Tạo một subscription trực tiếp |
| Gọi `block()` trên Mono | Subscribe và chặn luồng chờ kết quả |
| Gọi `toFuture()` trên Mono | Subscribe để nối kết quả sang future |
| Trả publisher cho WebFlux | Framework quản lý việc sử dụng publisher ở biên HTTP |
| Chạy verification bằng StepVerifier | Công cụ kiểm tra subscribe để quan sát tín hiệu |
| Gọi `map`, `flatMap`, `collectList` | Thông thường chỉ tạo pipeline mới; chưa phải subscription |

Không đặt thêm `block()` để log kết quả rồi tiếp tục trả lại publisher lạnh đó. Việc framework subscribe sau đó có thể tạo thêm một lần truy cập dữ liệu.

## 5. Ghép thao tác để subscription đi đúng đường

### 5.1. `map` biến đổi giá trị, không tự làm phẳng publisher lồng nhau

Xét:

```java
Mono<Mono<Product>> nested = products.findById(id)
        .map(product -> products.save(product.withName(newName)));
```

Callback của `map` trả về một `Mono<Product>`, nên kết quả bên ngoài là `Mono<Mono<Product>>`.

Khi subscribe publisher bên ngoài, ta có thể chỉ nhận được publisher bên trong như một giá trị. `map` không tự subscribe publisher đó để thực hiện lưu.

Để kết quả của thao tác lưu tham gia cùng chuỗi, dùng `flatMap`:

```java
Mono<Product> renamed = products.findById(id)
        .flatMap(product -> products.save(product.withName(newName)));
```

Ở đây, khi source phát một sản phẩm, `flatMap` dùng publisher lưu làm một phần của pipeline. Không cần tự gọi `subscribe()` trong callback.

Nếu truy vấn hoàn tất rỗng, callback `flatMap` không được gọi và không có thao tác lưu. Khi yêu cầu nghiệp vụ cần báo lỗi, khai báo rõ:

```java
public Mono<Product> rename(String id, String newName) {
    return products.findById(id)
            .switchIfEmpty(Mono.error(new IllegalArgumentException(
                    "Product not found: " + id
            )))
            .flatMap(product ->
                    products.save(product.withName(newName)));
}
```

Ví dụ cập nhật một sản phẩm đã tồn tại. Việc xử lý concurrent update cần cơ chế version hoặc concurrency phù hợp của store, không được giải quyết chỉ bằng `flatMap`.

### 5.2. `doOnNext` dành cho quan sát, không ghép một thao tác reactive mới

Ví dụ dễ bỏ sót thao tác ghi:

```java
Mono<Product> result = products.findById(id)
        .doOnNext(product ->
                products.save(product.withName(newName)));
```

`doOnNext` nhận một callback quan sát. Giá trị publisher do `save` trả về bị bỏ đi; nó không trở thành một bước được chờ trong chuỗi.

Thay bằng `flatMap` khi thao tác sau phụ thuộc phần tử trước. Không sửa bằng cách gọi `subscribe()` bên trong `doOnNext`, vì như vậy sẽ tạo một nhánh subscription độc lập.

### 5.3. `then` ghép theo completion

Nếu thao tác đầu trả về `Mono<Void>` hoặc ta chỉ quan tâm việc nó hoàn tất:

```java
Mono<Product> result = products.deleteById(oldId)
        .then(products.findById(replacementId));
```

Ý nghĩa là đợi thao tác xóa hoàn tất thành công rồi subscribe bước đọc. Nếu bước xóa báo lỗi, bước sau không được thực hiện theo chuỗi thành công này.

Cần phân biệt: phương thức `products.findById(replacementId)` trong ví dụ được gọi khi Java tạo đối số cho `then`. Tuy nhiên, với publisher repository lạnh thông thường, công việc đọc được kích hoạt ở lần subscription vào bước đó sau completion của bước đầu.

Nếu cả việc gọi factory tạo publisher cũng cần được hoãn:

```java
Mono<Product> result = products.deleteById(oldId)
        .then(Mono.defer(() -> products.findById(replacementId)));
```

Đây là khác biệt giữa **hoãn subscription vào publisher** và **hoãn luôn lời gọi tạo publisher**.

## 6. `defer`, giá trị được chụp sớm và công việc blocking

### 6.1. `Mono.just` nhận một giá trị đã được tính

```java
Mono<Product> result = Mono.just(loadFromBlockingClient(id));
```

`loadFromBlockingClient(id)` chạy trước khi `Mono.just` được gọi. Nếu phương thức này truy cập dữ liệu theo kiểu blocking, tác vụ đó đã chạy trong giai đoạn assembly.

Đổi kiểu trả về thành `Mono` không đảo ngược việc thực thi đã xảy ra.

Tương tự:

```java
Instant createdAt = clock.instant();
Mono<Instant> time = Mono.just(createdAt);
```

`time` giữ một giá trị được lấy khi tạo pipeline. Các subscriber sau có thể nhận cùng giá trị đó.

### 6.2. `Mono.defer` gọi factory theo subscription

```java
Mono<Product> result = Mono.defer(() -> {
    System.out.println("Creating source for this subscription");
    return products.findById(id);
});
```

Factory được gọi cho từng subscription. Nó hữu ích khi cần:

- Chọn source dựa trên trạng thái tại thời điểm thực thi.
- Tạo dữ liệu theo từng lần gọi thực sự.
- Tránh chạy mã tạo publisher hoặc mã kiểm tra quá sớm.
- Tạo lại một đối tượng mutable thay vì dùng chung giữa nhiều subscriber.

Nếu factory tự làm một thao tác blocking trước khi trả publisher, thao tác đó vẫn blocking trên luồng thực thi factory. `defer` hoãn thời điểm, không biến thuật toán blocking thành non-blocking.

### 6.3. Fallback có thể cần một factory lazy

```java
Mono<Product> result = products.findById(id)
        .switchIfEmpty(Mono.defer(() -> loadFallback(id)));
```

`loadFallback` là phương thức ứng dụng trả về `Mono<Product>`. Với `defer`, nó chỉ được gọi khi nhánh fallback được subscribe sau khi source chính hoàn tất rỗng.

Nếu viết:

```java
.switchIfEmpty(loadFallback(id))
```

Java gọi `loadFallback(id)` để tạo đối số ngay khi assembly. Nếu phương thức đó chỉ tạo một publisher lạnh thì I/O vẫn có thể chưa chạy, nhưng mọi mã Java trực tiếp trong phương thức đã có thể chạy.

Không dùng `defer` theo thói quen ở mọi chỗ. Hãy dùng khi hợp đồng yêu cầu lấy giá trị hoặc tạo source tại thời điểm subscription.

### 6.4. `fromCallable` hoãn lời gọi nhưng không tự đổi luồng

```java
Mono<Product> result = Mono.fromCallable(() ->
        loadFromBlockingClient(id));
```

Callable được gọi khi source được subscribe, nhưng không mặc nhiên được chuyển sang một luồng dành cho blocking I/O.

Nếu bắt buộc phải tích hợp một API blocking cũ, cần một adapter và scheduler phù hợp, thường được thiết kế tại ranh giới tích hợp. Đây là trường hợp khác với việc sử dụng một repository và driver reactive thực sự.

Không bọc mọi lời gọi reactive repository bằng `fromCallable`, vì chính repository đã trả publisher để ghép vào chuỗi.

## 7. Nhiều subscription có thể tạo nhiều lần truy cập dữ liệu

### 7.1. Tái sử dụng biến không đồng nghĩa tái sử dụng kết quả

```java
Mono<Product> lookup = products.findById("p-01");

lookup.subscribe(product -> System.out.println("A: " + product.id()));
lookup.subscribe(product -> System.out.println("B: " + product.id()));
```

Với source lạnh thông thường, đây là hai subscription và có thể là hai lần thực thi truy vấn. Không có bảo đảm rằng cả hai nhìn thấy cùng một snapshot dữ liệu nếu dữ liệu thay đổi ở giữa.

Tương tự, tạo một biến publisher ghi rồi subscribe hai lần có thể kích hoạt hai lần ghi:

```java
Mono<Product> write = products.save(product);

write.subscribe();
write.subscribe();
```

Kết quả cụ thể phụ thuộc entity state, ID, version, phép insert/update và store. Không suy ra rằng `save` lặp lại luôn an toàn hoặc luôn chỉ tạo một bản ghi.

### 7.2. Đừng tự subscribe rồi trả cùng pipeline cho caller

Ví dụ không phù hợp trong service phục vụ request:

```java
public Mono<Product> rename(String id, String name) {
    Mono<Product> result = products.findById(id)
            .flatMap(product -> products.save(product.withName(name)));

    result.subscribe();
    return result;
}
```

Lần `subscribe` trong service đã mở một nhánh thực thi. Khi WebFlux hoặc caller dùng publisher trả về, có thể xuất hiện nhánh thứ hai.

Ngoài việc lặp thao tác, nhánh tự subscribe có thể tách lỗi, cancellation và transaction context khỏi lời gọi chính.

Dạng phù hợp là tạo chuỗi và trả nó:

```java
public Mono<Product> rename(String id, String name) {
    return products.findById(id)
            .flatMap(product -> products.save(product.withName(name)));
}
```

Một thành phần ở biên hệ thống vẫn có thể quản lý subscription tường minh, nhưng khi đó nó phải sở hữu cả vòng đời, lỗi và việc hủy. Đó là trách nhiệm cụ thể, không phải một bước cần thêm vào mọi service.

### 7.3. `retry` là một nguồn resubscription

```java
Mono<Product> operation = products.findById(id)
        .flatMap(product -> products.save(product.withName(newName)))
        .retry(2);
```

`retry(2)` cho phép tối đa hai lần subscribe lại sau lỗi, ngoài lần đầu tiên. Phần source nằm trước `retry` có thể được thực thi nhiều lần.

Không mặc định rằng nhận `onError` chứng minh store chưa ghi gì. Ví dụ, lỗi có thể xảy ra khi nhận phản hồi, hoặc sau thao tác ghi ở một bước downstream khác. Retry có thể làm lặp một hiệu ứng đã xảy ra.

Cần xác định:

- Lỗi nào có thể retry.
- Toàn bộ use case hay chỉ một đoạn được subscribe lại.
- Mỗi lần thử có transaction riêng đúng mong đợi không.
- Thao tác có idempotent hoặc có cơ chế chống trùng không.
- Entity và optimistic version có cần được tải lại không.

`repeat` cũng có thể tạo subscription mới nhưng dựa trên completion thành công, nên không được nhầm nó với retry khi lỗi.

### 7.4. Cache thay đổi hợp đồng thực thi

```java
Mono<Product> sharedResult = products.findById(id).cache();
```

`cache` trên Mono có thể làm kết quả hoặc tín hiệu kết thúc của một lần thực thi được phát lại cho các subscriber sau. Với dạng không cấu hình thời hạn, cần xét cả việc giữ tín hiệu rỗng hoặc lỗi.

Đây là thay đổi có chủ đích đối với vòng đời source, không phải cách sửa tự động cho mọi subscription lặp.

Trước khi cache, cần xem:

- Có chấp nhận dữ liệu cũ không?
- Khóa có bao quát tenant, người dùng và tham số không?
- Một lỗi có bị giữ lâu hơn mong muốn không?
- Cache sống trong phạm vi một request, một instance hay lâu hơn?

Cache trong bộ nhớ không cung cấp idempotency bền vững giữa các lần khởi động hoặc giữa nhiều instance ứng dụng.

## 8. Subscription không đồng nghĩa tạo thread mới

Một pipeline không mặc nhiên có một thread riêng cho mỗi subscription.

- Một source đồng bộ có thể phát tín hiệu ngay trên luồng gọi `subscribe`.
- Driver reactive có thể nhận kết quả qua event loop hoặc cơ chế I/O riêng.
- Scheduler operator thay đổi ranh giới thực thi theo hợp đồng của nó.

`subscribeOn` không phải lệnh khởi chạy ngay khi khai báo operator. Publisher vẫn cần được subscribe. `publishOn` cũng không tự tạo một subscriber và không làm một lời gọi blocking đã chạy ở assembly trở nên lazy.

Khi quan sát log, việc dòng sau xuất hiện trên thread khác chưa chứng minh có transaction khác, một lần query mới hoặc một subscriber khác. Cần quan sát đúng cả tín hiệu và context.

Trong các đường reactive, tránh dùng `block()` trên event loop chỉ để làm mã trông tuần tự. Hãy ghép dependency bằng operator và để thành phần ở biên quản lý subscription.

## 9. Transaction reactive cũng cần một chuỗi được thực thi

### 9.1. Transaction bao quanh công việc trong pipeline

Với một store và `ReactiveTransactionManager` phù hợp, có thể dùng `TransactionalOperator` để đặt ranh giới giao dịch:

```java
public Mono<Product> renameInTransaction(String id, String newName) {
    Mono<Product> work = products.findById(id)
            .switchIfEmpty(Mono.error(new IllegalArgumentException(
                    "Product not found: " + id
            )))
            .flatMap(product ->
                    products.save(product.withName(newName)));

    return transactions.transactional(work);
}
```

Trong ví dụ, `transactions` là một `TransactionalOperator` được tạo từ reactive transaction manager của tài nguyên cần dùng. Toàn bộ thao tác đọc và ghi được ghép trong `work`.

Đối với pipeline được operator quản lý, transaction được thiết lập trong giai đoạn thực thi của subscription. Chỉ tạo và trả về publisher chưa đủ để hoàn thành transaction.

Cũng có thể dùng khai báo `@Transactional` với hạ tầng reactive tương thích. Cần lựa chọn đúng transaction manager và gọi qua cơ chế proxy phù hợp; annotation không làm một store thiếu hỗ trợ transaction có được khả năng đó.

### 9.2. Tự subscribe bên trong có thể tách công việc khỏi transaction

Ví dụ không phù hợp:

```java
Mono<Void> work = Mono.fromRunnable(() -> {
    products.save(product).subscribe();
});

return transactions.transactional(work);
```

`work` chỉ mô tả việc gọi `subscribe()` cho một nhánh khác. Nó không chờ completion của thao tác lưu như một phần tử phụ thuộc trong cùng chuỗi.

Kết quả là transaction của chuỗi ngoài có thể kết thúc mà không bao trùm thao tác ghi như tác giả mong đợi. Lỗi và cancellation của nhánh trong cũng không tự trở thành lỗi và cancellation của nhánh ngoài.

Dạng ghép phù hợp:

```java
return transactions.transactional(products.save(product)).then();
```

Publisher lưu tham gia trực tiếp ranh giới được quản lý và caller subscribe vào kết quả cuối.

### 9.3. `onNext` chưa phải bằng chứng commit

Trong một pipeline nhiều bước, repository có thể phát một giá trị trước khi transaction bao ngoài kết thúc. Một `doOnNext` đặt bên trong transaction chỉ quan sát được dữ liệu đi qua vị trí đó.

Không gửi tác động ngoài không thể thu hồi chỉ vì `save` đã phát một entity rồi suy ra transaction chắc chắn commit. Cần xem ranh giới giao dịch, vị trí operator và cơ chế xử lý sau commit phù hợp.

Khi có `retry`, vị trí của nó so với ranh giới transaction ảnh hưởng phần nào được thực thi lại. Nếu yêu cầu mỗi lần thử là một transaction mới, phải thiết kế và kiểm chứng điều đó; không mặc định mọi vị trí đặt `retry` đều tương đương.

### 9.4. Metadata theo subscriber cần một context phù hợp

Transaction reactive và các metadata như tenant hoặc correlation ID thường cần được truyền qua context của pipeline. Không mặc định một `ThreadLocal` được đọc khi assembly sẽ đúng cho mọi subscriber hoặc còn tồn tại khi driver trả dữ liệu.

Nếu cần dữ liệu tại thời điểm subscription, có thể dùng các cơ chế như Reactor Context và `deferContextual` theo thiết kế của ứng dụng. Nguồn tenant hoặc principal vẫn phải được xác thực; việc đưa một giá trị vào context không tự tạo quyền truy cập.

Điều này đặc biệt quan trọng khi cache hoặc chia sẻ publisher. Một publisher phụ thuộc context của subscriber không nên bị biến thành kết quả dùng chung giữa nhiều người dùng mà không có hợp đồng rõ ràng.

## 10. Demand, backpressure và cancellation

### 10.1. Demand không phải `LIMIT` của ngôn ngữ truy vấn

Subscriber yêu cầu một phần tử không có nghĩa cơ sở dữ liệu chắc chắn chỉ thực hiện công việc tương ứng đúng một hàng.

Driver có thể dùng batch, cursor, fetch size hoặc buffer riêng. Backpressure điều khiển luồng dữ liệu giữa các thành phần reactive, còn hiệu quả truy vấn phụ thuộc cả điều kiện, index và cơ chế của store.

Nếu cần giới hạn kết quả ở kho dữ liệu, dùng cơ chế query hoặc API được module hỗ trợ. Không thay thế việc đó chỉ bằng kỳ vọng về số lần `request`.

Tương tự, `collectList()` gom các phần tử vào bộ nhớ khi pipeline chạy. Nó không tự phân trang và chưa khởi chạy truy vấn ngay lúc được gọi.

### 10.2. Cancellation là một tín hiệu riêng

Một subscription có thể bị hủy khi:

- Client ngắt kết nối.
- Một operator timeout hoặc chỉ cần một phần kết quả.
- Caller chủ động dispose subscription.
- Một nhánh trong chuỗi không còn được cần đến.

Cancellation có thể khiến source ngừng phát dữ liệu, hủy cursor hoặc giải phóng tài nguyên theo khả năng của driver. Tuy nhiên, nó không phải bằng chứng rằng mọi lệnh đã gửi xuống kho dữ liệu đều chưa chạy.

Đặc biệt, với thao tác ghi:

- Lệnh có thể đã tới server.
- Dữ liệu có thể đã commit ngoài một transaction có thể rollback.
- Việc client không nhận kết quả không chứng minh thao tác chưa xảy ra.

Nếu có transaction reactive đang được quản lý, hạ tầng xử lý kết thúc hoặc rollback theo hợp đồng của nó. Không dùng cancellation như một cơ chế hoàn tác phổ quát cho mọi tác động đã thực hiện.

### 10.3. Giới hạn một Flux không bảo đảm công việc phía store giống nhau

```java
Flux<Product> first = products.findAll().take(1);
```

Sau phần tử đầu tiên, `take(1)` có thể hủy upstream vì đã đủ kết quả. Đây là hành vi của pipeline, không phải một cam kết chung rằng câu truy vấn của mọi store đã được viết lại thành một phép tìm giới hạn một bản ghi.

Nếu bài toán cần một phần tử có thứ tự cụ thể, phải khai báo điều kiện, thứ tự và giới hạn phù hợp với module. Đừng dựa vào phần tử đầu tiên tình cờ nhận được từ `findAll()`.

### 10.4. Completion, error và cancel cần được quan sát riêng

`doFinally` giúp quan sát lý do kết thúc, bao gồm cả cancel. Không ghi một thông báo chung như `Saved successfully` trong callback này mà không kiểm tra tín hiệu.

Một chuỗi kết thúc vì hủy hoặc lỗi có ý nghĩa khác với chuỗi hoàn tất thành công. Ngay cả completion thành công của một publisher con cũng phải được diễn giải đúng trong ranh giới transaction ngoài.

## 11. Kiểm chứng bằng một bài thực hành có kiểm soát

Các ví dụ kiểm tra dưới đây là nội dung để người học triển khai trong dự án. Cần có store reactive thật hoặc một test double phù hợp; chúng không phải kết quả đã chạy của tài liệu này.

### 11.1. Kiểm tra factory được gọi tại subscription

Giả sử repository đã có sản phẩm `p-01`:

```java
AtomicInteger sourceFactories = new AtomicInteger();

Mono<Product> operation = Mono.defer(() -> {
    sourceFactories.incrementAndGet();
    return products.findById("p-01");
});

assertEquals(0, sourceFactories.get());

StepVerifier.create(operation)
        .expectNextMatches(product -> "p-01".equals(product.id()))
        .expectComplete()
        .verify(Duration.ofSeconds(5));

assertEquals(1, sourceFactories.get());
```

Ví dụ sử dụng `AtomicInteger`, `Duration`, assertion của thư viện test và `reactor.test.StepVerifier`. Dependency và dữ liệu fixture cần được cấu hình trong dự án.

`StepVerifier.create` chuẩn bị kịch bản kiểm tra; lời gọi verification thực hiện việc subscribe và quan sát tín hiệu. Factory trong `defer` chưa chạy khi chỉ tạo biến `operation`.

Nếu verification lần thứ hai cũng dùng `operation`, bộ đếm factory tăng tiếp với source này. Điều đó giúp thấy sự khác nhau giữa một biến publisher và một kết quả đã được tính một lần.

### 11.2. Đếm đúng thứ cần đo

Một bộ đếm trong factory đo số lần factory được gọi. `doOnSubscribe` đo số lần subscription đi qua vị trí đặt operator. Cả hai chưa tự chứng minh số câu lệnh mạng thực tế.

Khi cần kiểm tra I/O, có thể kết hợp quan sát driver, log truy vấn hoặc công cụ đo của store trong môi trường thực hành. Phân biệt những con số sau:

```text
Số lần gọi phương thức repository
Số lần factory tạo source chạy
Số subscription đi qua một điểm operator
Số thao tác truy cập dữ liệu thực tế
Số lần commit thành công
```

Chúng có quan hệ với nhau nhưng không bắt buộc luôn bằng nhau. Cache, retry, transaction, batching và nhiều subscriber có thể làm quan hệ đó thay đổi.

### 11.3. So sánh các tình huống

| Tình huống | Điều cần quan sát |
| --- | --- |
| Tạo Mono rồi không dùng | Không có subscription vào thao tác repository lạnh đó |
| Trả Mono từ controller WebFlux | Framework điều phối subscription khi xử lý kết quả |
| Gọi `subscribe` hai lần trên source lạnh | Có hai lần thực thi source theo hợp đồng của nó |
| Dùng `map` trả về Mono | Có publisher lồng nhau, chưa tự làm phẳng thao tác |
| Dùng `flatMap` | Publisher bên trong được ghép vào chuỗi thực thi |
| Dùng `doOnNext` cho Mono rỗng | Callback không chạy dù source đã hoàn tất |
| Dùng `retry` sau một chuỗi đọc/ghi | Phần upstream có thể được subscribe lại |
| Dùng `cache` | Hành vi subscriber sau có thể dùng tín hiệu đã giữ |
| Hủy sau khi đã gửi thao tác ghi | Không kết luận dữ liệu chưa thay đổi chỉ từ cancellation |
| Đặt transaction operator quanh cả chuỗi | Quan sát transaction cùng với completion và lỗi của công việc được ghép |

Nếu thử thao tác ghi, dùng dữ liệu và chính sách dọn fixture rõ ràng. Không dùng số lượng bản ghi tình cờ còn lại làm bằng chứng duy nhất về số lần subscription.

## 12. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Gọi repository nhưng không thấy dữ liệu thay đổi | Publisher chưa được subscribe hoặc đã bị bỏ đi | Trả hoặc ghép publisher vào chuỗi mà caller sử dụng |
| Controller trả thành công quá sớm | Service trả `Mono.empty()` thay vì thao tác thật | Trả publisher gốc hoặc dùng `then` đúng phụ thuộc |
| Kết quả là một Mono bên trong Mono | Dùng `map` để gọi thao tác trả publisher | Dùng `flatMap` khi cần làm phẳng và chờ kết quả |
| `save` trong `doOnNext` không chạy như mong đợi | Publisher lưu bị bỏ đi | Ghép thao tác bằng operator phù hợp |
| Truy vấn hoặc thao tác ghi chạy hai lần | Tự subscribe, block hoặc có nhiều subscriber | Xác định chủ sở hữu subscription ở biên |
| Thời gian/metadata giữ giá trị cũ | Giá trị được lấy lúc assembly | Dùng factory hoặc context theo subscription khi cần |
| Chỉ nhận completion mà không có log `doOnNext` | Source rỗng hoặc kiểu `Mono<Void>` | Quan sát đúng tín hiệu completion |
| Ghi bị lặp sau lỗi mạng | Retry tạo subscription mới | Thiết kế retry cùng idempotency và transaction |
| Luồng event loop bị chặn | API blocking hoặc `block()` nằm trong đường reactive | Loại bỏ blocking hoặc tạo adapter phù hợp ở ranh giới |
| Không thấy đúng tenant khi đổi luồng | Dựa vào dữ liệu thread-bound hoặc chia sẻ sai publisher | Truyền context và kiểm tra phạm vi cache |
| Có `onNext` nhưng dữ liệu cuối cùng rollback | Transaction ngoài chưa hoàn tất | Quan sát đúng ranh giới commit |

Khi debug, nên gắn correlation ID cho một lần xử lý và ghi rõ mốc assembly, subscription, tín hiệu và transaction. Tránh log toàn bộ entity hoặc thông tin xác thực chỉ để theo dõi pipeline.

## 13. Bài tập tự triển khai

1. Tạo một repository reactive đọc dữ liệu từ store được hỗ trợ; trả `Mono` mà không subscribe và quan sát sự khác nhau giữa log Java trực tiếp với log trong operator.
2. Gọi một pipeline lạnh bằng hai lần verification, rồi giải thích vì sao một biến có thể dẫn tới hai lần thực thi.
3. Viết use case đổi tên sản phẩm bằng `flatMap`; so sánh với phiên bản dùng `map` và phiên bản bỏ `save` trong `doOnNext`.
4. Dùng `Mono.defer` để lấy timestamp theo từng subscription; so sánh với timestamp đã chụp bằng `Mono.just`.
5. Thiết kế một lỗi có thể retry và xác định chính xác phần nào sẽ được subscribe lại, không chỉ thêm `retry` để làm test qua.
6. Đặt transaction reactive quanh chuỗi đọc/ghi; quan sát sự khác nhau giữa phần tử được phát và transaction đã commit.
7. Hủy một truy vấn nhiều phần tử, rồi giải thích vì sao kết luận về cancellation cần xét thêm driver và store.

Với mỗi pipeline, hãy chỉ ra: **ai subscribe, source nào được thực thi, có thể subscribe lại ở đâu, và tín hiệu nào chứng minh điều gì**.

## 14. Điểm cần ghi nhớ

- Repository reactive thường trả một mô tả công việc; publisher lạnh cần subscription để bước vào vòng đời thực thi.
- Mã Java trực tiếp và việc tính đối số vẫn có thể chạy trong giai đoạn assembly.
- Subscription, demand, I/O, `onNext`, completion và commit là những mốc khác nhau.
- Dùng `flatMap` và `then` để ghép thao tác; không bỏ publisher hoặc tự subscribe trong callback để giả lập chuỗi tuần tự.
- `defer` hoãn việc tạo source theo subscription; nó không tự đổi thread hoặc làm blocking I/O trở nên non-blocking.
- Nhiều subscriber, `block`, `retry` và `repeat` có thể tạo thêm lần thực thi.
- Cache thay đổi hợp đồng chia sẻ kết quả và cần được xét cùng dữ liệu cũ, lỗi, tenant và vòng đời.
- Để WebFlux hoặc thành phần ở biên quản lý subscription khi phù hợp; service trả về chuỗi đã ghép.
- Khả năng truy cập dữ liệu, transaction và cancellation cuối cùng phụ thuộc store reactive, driver và cấu hình thực tế.