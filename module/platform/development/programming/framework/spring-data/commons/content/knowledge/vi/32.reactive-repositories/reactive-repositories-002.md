# ReactiveCrudRepository và ReactiveSortingRepository

## 1. Hai nhu cầu: thao tác dữ liệu và đọc có thứ tự

Một dịch vụ quản lý sản phẩm cần tạo sản phẩm, tìm theo ID, đổi giá, xóa và liệt kê theo giá tăng dần. Ứng dụng dùng một store hỗ trợ truy cập reactive và muốn nối các thao tác dữ liệu vào cùng luồng xử lý, thay vì chờ kết quả bằng lời gọi blocking.

Spring Data Commons cung cấp hai abstraction cần phân biệt:

- `ReactiveCrudRepository<T, ID>` cho các thao tác CRUD với kiểu trả về Reactor.
- `ReactiveSortingRepository<T, ID>` cho việc đọc các entity theo `Sort`.

Bài thuộc chương **Repository reactive** của module **SPRING_DATA_COMMONS**. Trọng tâm là hợp đồng của hai interface, cách kết hợp chúng và cách sử dụng đúng kết quả bất đồng bộ. Mapping, driver, khả năng query và transaction vẫn cần được cấu hình theo module lưu trữ thực tế.

Sau bài học, bạn cần khai báo được repository có cả CRUD và sorting, đọc đúng ý nghĩa `Mono`/`Flux`, ghép thao tác bằng operator và giải thích được vì sao sorting không tự cung cấp phân trang hoặc tính nguyên tử cho nhiều lần ghi.

## 2. Quan hệ giữa hai interface

Trong Spring Data từ phiên bản 3.0, các sorting repository không còn kế thừa CRUD repository tương ứng. Khi cần cả hai nhóm chức năng, hãy kế thừa cả hai interface. [Spring Data Commons: Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.reactive.ReactiveSortingRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, String>,
                ReactiveSortingRepository<Product, String> {
}
```

`Product` là kiểu entity và `String` là kiểu ID trong thiết kế này. Hai interface cùng mô tả một domain type; không dùng kiểu ID khác nhau ở hai nhánh kế thừa.

Có thể hình dung khả năng được ghép như sau:

```text
Repository<Product, String>
  ├── ReactiveCrudRepository
  │     save, findById, findAll, count, delete...
  └── ReactiveSortingRepository
        findAll(Sort)

ProductRepository kết hợp cả hai nhóm khả năng
```

Nếu chỉ kế thừa `ReactiveSortingRepository`, đừng suy rằng sẽ có sẵn `save` hoặc `deleteById`. Ngược lại, nhóm CRUD không tự bổ sung overload `findAll(Sort)` chỉ vì đã có `findAll()`.

Khi ứng dụng có một base repository generic dùng chung, cần phân biệt nó với repository cụ thể mà framework phải tạo bean. Chỉ tạo lớp abstraction trung gian khi có nhu cầu dùng chung thật sự; bài này dùng một interface cụ thể để giữ đường đi của từng thao tác rõ ràng.

## 3. Mono và Flux diễn đạt số lượng cùng tín hiệu kết thúc

`Mono<T>` biểu diễn tối đa một giá trị; luồng có thể hoàn tất không có giá trị hoặc báo lỗi. `Mono<Void>` biểu diễn công việc không phát payload và được quan sát bằng tín hiệu hoàn tất hoặc lỗi. [Reactor: Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html).

`Flux<T>` có thể phát từ không đến nhiều phần tử rồi kết thúc thành công hoặc báo lỗi. [API Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).

| Kiểu trả về | Cách đọc trong repository |
| --- | --- |
| `Mono<Product>` | Có tối đa một sản phẩm, có thể không tìm thấy |
| `Flux<Product>` | Có thể có nhiều sản phẩm, có thể không có phần tử nào |
| `Mono<Boolean>` | Một kết quả kiểm tra đúng/sai khi thao tác thành công |
| `Mono<Long>` | Một kết quả đếm khi thao tác thành công |
| `Mono<Void>` | Quan sát hoàn tất hoặc lỗi, không chờ một object `Void` |

Với yêu cầu lấy sản phẩm, ba tình huống khác nhau cần được giữ rõ:

```text
Có sản phẩm       -> onNext(product), rồi onComplete
Không có sản phẩm -> onComplete, không có onNext
Truy vấn thất bại -> onError(error)
```

Không đổi mọi lỗi kết nối thành luồng rỗng chỉ để người gọi nhận cùng một kiểu dữ liệu. Trong nghiệp vụ quản lý sản phẩm, không tìm thấy ID và database không truy cập được là hai kết quả có ý nghĩa khác nhau.

Cũng không truyền null vào stream để biểu diễn thiếu dữ liệu. Hãy dùng luồng rỗng hoặc một hợp đồng kết quả rõ ràng ở tầng ứng dụng.

## 4. Các thao tác của ReactiveCrudRepository

Hợp đồng CRUD cung cấp các thao tác với Reactor types và có những overload nhận `Publisher`. Bảng dưới rút gọn chữ ký để tập trung vào cách sử dụng. [API ReactiveCrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/ReactiveCrudRepository.html).

| Nhu cầu | Phương thức tiêu biểu | Kết quả |
| --- | --- | --- |
| Lưu một entity | `save(entity)` | `Mono<S>` |
| Lưu nhiều entity | `saveAll(Iterable<S>)`, `saveAll(Publisher<S>)` | `Flux<S>` |
| Tìm một entity theo ID | `findById(id)` | `Mono<T>` |
| Kiểm tra tồn tại | `existsById(id)` | `Mono<Boolean>` |
| Đọc tất cả | `findAll()` | `Flux<T>` |
| Đọc theo nhiều ID | `findAllById(ids)` | `Flux<T>` |
| Đếm | `count()` | `Mono<Long>` |
| Xóa theo ID | `deleteById(id)` | `Mono<Void>` |
| Xóa một entity | `delete(entity)` | `Mono<Void>` |
| Xóa tập entity được cung cấp | `deleteAll(entities)` | `Mono<Void>` |

Generic `S extends T` trong thao tác lưu giữ kiểu của entity được truyền vào. Với ứng dụng minh họa chỉ có một kiểu `Product`, kết quả thường được sử dụng dưới dạng `Mono<Product>` hoặc `Flux<Product>`.

Kết quả lưu là entity cần được dùng cho thao tác tiếp theo. Entity trả về có thể chứa ID, version hoặc giá trị do hạ tầng điền; với kiểu bất biến, không nên tiếp tục dựa vào instance đầu vào như thể nó đã tự đổi.

Nhóm thao tác nhiều entity không tự xác định cách store tối ưu hóa thành batch, số lần gọi driver hoặc ranh giới transaction. Những quyết định đó cần kiểm tra ở module đang sử dụng.

## 5. ReactiveSortingRepository bổ sung điều gì?

Hợp đồng sorting cung cấp `Flux<T> findAll(Sort sort)`. Tham số không được null; có thể truyền `Sort.unsorted()` nếu không yêu cầu thứ tự. Interface này là một fragment thường được kết hợp với CRUD. [API ReactiveSortingRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/ReactiveSortingRepository.html).

Ví dụ đọc sản phẩm theo giá rồi theo ID:

```java
Sort sort = Sort.by(
        Sort.Order.asc("priceInCents"),
        Sort.Order.asc("id"));

Flux<Product> ordered = repository.findAll(sort);
```

Tên thuộc tính trong `Sort` là tên property của mô hình được module ánh xạ. Khi có tùy biến field hoặc column, hãy để mapping của module giải quyết biểu diễn lưu trữ và kiểm tra query thực tế nếu cần chẩn đoán.

Trong thiết kế này, ID là tiêu chí phụ để hai sản phẩm cùng giá vẫn có thứ tự xác định. Việc chọn khóa phụ là yêu cầu của truy vấn ứng dụng; không suy rằng database tự trả thứ tự ổn định khi chỉ sắp theo một giá trị trùng nhau.

Cần phân biệt hai cách biểu đạt:

```java
// Yêu cầu repository thực hiện truy vấn với thông tin sắp xếp.
Flux<Product> fromRepository = repository.findAll(sort);

// Sắp xếp các phần tử đã được phát ra trong pipeline Reactor.
Flux<Product> inPipeline = repository.findAll()
        .sort(java.util.Comparator.comparingLong(Product::priceInCents));
```

Hai dòng không phải một kế hoạch thực thi tương đương. Với dữ liệu lớn, hãy xem nơi sorting diễn ra, khả năng dùng index và lượng dữ liệu đi qua ứng dụng; đừng chỉ so sánh kiểu trả về `Flux<Product>`.

## 6. Ví dụ tự chứa: sản phẩm và service reactive

Ví dụ dùng Java 17, Spring Data từ thế hệ đã tách sorting khỏi CRUD và Spring Data MongoDB reactive có phiên bản tương thích. Mỗi public type đặt trong tệp Java riêng thuộc cùng package `example.products`; các đoạn mã lược dòng package.

Để chạy ví dụ cần cấu hình database, repository scanning và MongoDB Reactive Streams driver. MongoDB có hạ tầng driver và cấu hình reactive riêng, không thể chỉ thay interface trong một cấu hình blocking rồi coi kết nối đã đổi. [Spring Data MongoDB: Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).

### 6.1. Entity bất biến

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public record Product(
        @Id String id,
        String name,
        long priceInCents,
        @Version Long version) {

    public Product {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name bắt buộc");
        }
        if (priceInCents < 0) {
            throw new IllegalArgumentException("priceInCents không được âm");
        }
    }

    public static Product draft(String name, long priceInCents) {
        return new Product(null, name, priceInCents, null);
    }

    public Product withPrice(long nextPriceInCents) {
        return new Product(id, name, nextPriceInCents, version);
    }
}
```

Bài dùng số nguyên đơn vị nhỏ nhất để biểu diễn giá minh họa. Quy tắc tiền tệ đầy đủ như loại tiền, làm tròn hoặc chuyển đổi nằm ngoài phạm vi repository của ví dụ.

`draft` không tự gán ID hoặc version. `withPrice` giữ lại các giá trị hiện có, để bản sao cập nhật vẫn đại diện đúng sản phẩm và phiên bản được đọc.

### 6.2. Repository kết hợp CRUD và sorting

```java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.data.repository.reactive.ReactiveSortingRepository;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, String>,
                ReactiveSortingRepository<Product, String> {
}
```

Không cần tự viết implementation cho từng phương thức CRUD trong ví dụ. Module reactive thích hợp tạo repository theo mapping và cấu hình của ứng dụng.

### 6.3. Lỗi không tìm thấy do tầng ứng dụng quy định

```java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String productId) {
        super("Không tìm thấy sản phẩm: " + productId);
    }
}
```

Đây là chính sách của service: một thao tác yêu cầu sản phẩm bắt buộc có sẽ chuyển kết quả không tìm thấy thành lỗi riêng. Những truy vấn chỉ kiểm tra tồn tại hoặc tìm tùy chọn có thể giữ hợp đồng khác.

### 6.4. Ghép các thao tác trong cùng publisher

```java
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> create(String name, long priceInCents) {
        return Mono.defer(() ->
                repository.save(Product.draft(name, priceInCents)));
    }

    public Mono<Product> required(String productId) {
        return Mono.defer(() -> {
            if (productId == null || productId.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "productId bắt buộc"));
            }

            return repository.findById(productId)
                    .switchIfEmpty(Mono.error(
                            new ProductNotFoundException(productId)));
        });
    }

    public Mono<Product> changePrice(String productId, long nextPriceInCents) {
        return required(productId)
                .flatMap(product -> repository.save(
                        product.withPrice(nextPriceInCents)));
    }

    public Flux<Product> sortedByPrice() {
        Sort sort = Sort.by(
                Sort.Order.asc("priceInCents"),
                Sort.Order.asc("id"));
        return repository.findAll(sort);
    }

    public Mono<Void> deleteRequired(String productId) {
        return required(productId).flatMap(repository::delete);
    }
}
```

`Mono.defer` đưa việc dựng thao tác vào thời điểm subscription. Trong `create`, nó cũng giữ lỗi kiểm tra đầu vào của factory trong luồng lỗi reactive thay vì thực hiện việc dựng entity ngay khi gọi service.

`changePrice` dùng `flatMap` vì `save` trả một publisher cần được ghép vào luồng. `deleteRequired` quan sát sự tồn tại tại lần đọc trước khi xóa; cặp đọc/xóa này không tự tạo bảo đảm về cạnh tranh hoặc transaction cho toàn bộ nghiệp vụ.

## 7. Assembly, subscription và việc không tách luồng ngoài ý muốn

Một biến kiểu `Mono<Product>` giữ mô tả công việc và hợp đồng tín hiệu, không phải một sản phẩm đã lấy xong. Việc subscribe kích hoạt luồng; hệ thống tích hợp hoặc test có thể đảm nhiệm subscription thay cho service. [Reactor: Creating and Subscribing](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html).

Ví dụ sau chỉ tạo pipeline:

```java
Mono<Product> creation = service.create("Bàn phím", 250000);
```

Không kết luận sản phẩm đã được lưu chỉ vì biến `creation` tồn tại. Trong một tầng xử lý reactive, thường trả publisher cho tầng gọi hoặc framework quản lý thay vì tự subscribe sâu trong service.

Một cách ghép sai:

```java
public Mono<Product> changePriceIncorrectly(String id, long price) {
    required(id).subscribe(product ->
            repository.save(product.withPrice(price)).subscribe());
    return Mono.empty();
}
```

Phương thức trả về không còn đại diện cho tác vụ ghi bên trong. Bên gọi có thể thấy hoàn tất rỗng mà không quan sát được kết quả hoặc lỗi của lần lưu.

Cách `flatMap` trong `ProductService` giữ việc tìm, tạo bản sao và lưu trong một hợp đồng kết quả. Đừng thay nó bằng `map` nếu lambda trả `Mono<Product>` rồi để kết quả trở thành `Mono<Mono<Product>>`.

Với publisher lạnh như mẫu `create` dùng `defer`, nhiều subscription có thể thực hiện nhiều lần tạo. Khi cần retry hoặc chia sẻ kết quả, hãy thiết kế rõ ý nghĩa ghi và khả năng lặp; không mặc định hai subscriber sẽ dùng cùng một lần lưu.

## 8. Luồng rỗng, lỗi và thao tác chỉ có completion

### 8.1. switchIfEmpty dành cho thiếu giá trị

Trong `required`, `switchIfEmpty` chuyển trường hợp không có sản phẩm thành `ProductNotFoundException`. Nó không phải cơ chế đổi lỗi driver thành lỗi không tìm thấy.

Nếu muốn ánh xạ lỗi kỹ thuật sang lỗi ứng dụng, hãy chọn loại lỗi cần xử lý và giữ được nguyên nhân cần thiết. Tránh một `onErrorResume` quá rộng trả `Mono.empty()` khiến lỗi kết nối, xung đột version và không tìm thấy đều có cùng biểu hiện.

### 8.2. Mono<Void> phải được ghép theo completion

Một thao tác xóa không phát entity cho lambda tiếp theo. Nếu cần đếm sau khi xóa hoàn tất thành công, có thể ghép:

```java
Mono<Long> remaining = service.deleteRequired(productId)
        .then(repository.count());
```

`then` chờ phần trước kết thúc thành công rồi chuyển sang publisher sau. Nó không có nghĩa xóa và đếm đã nằm trong cùng một snapshot hoặc transaction. [API Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).

Không dùng `switchIfEmpty` trên một `Mono<Void>` thành công để suy rằng bản ghi xóa không tồn tại. Kiểu này vốn không có payload để phân biệt các trường hợp theo cách đó.

### 8.3. Optimistic locking và cập nhật cạnh tranh

Khi entity có version và store hỗ trợ tương ứng, thao tác lưu hoặc xóa có thể báo `OptimisticLockingFailureException` qua `onError` nếu version không khớp. [API ReactiveCrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/ReactiveCrudRepository.html).

Ví dụ hai request cùng đọc một sản phẩm rồi đổi giá: request sau cần nhận diện xung đột thay vì tự xóa version để ghi đè. Khi retry, có thể cần đọc trạng thái mới và đánh giá lại command; phát lại bản sao mang version cũ không tự giải quyết nguyên nhân lỗi.

## 9. Publisher đầu vào và nhiều entity

Overload nhận publisher không đồng nghĩa mọi phương thức đều tiêu thụ nhiều giá trị theo cùng cách. Chẳng hạn `findById(Publisher<ID>)` dùng giá trị ID đầu tiên, trong khi `findAllById(Publisher<ID>)` phục vụ tìm theo nhiều ID. [API ReactiveCrudRepository](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/reactive/ReactiveCrudRepository.html).

```java
Mono<Product> one = repository.findById(
        reactor.core.publisher.Flux.just("p-1", "p-2"));

Flux<Product> many = repository.findAllById(
        reactor.core.publisher.Flux.just("p-1", "p-2"));
```

Đọc tên và hợp đồng phương thức trước khi chọn overload. Với truy vấn theo nhiều ID, không ghép kết quả và ID đầu vào theo vị trí mà chưa có bảo đảm về thứ tự và các ID không tồn tại.

Tương tự, có thể đưa nhiều bản nháp vào `saveAll`:

```java
Flux<Product> saved = repository.saveAll(
        reactor.core.publisher.Flux.just(
                Product.draft("Chuột", 180000),
                Product.draft("Bàn phím", 250000)));
```

Kết quả là một luồng các sản phẩm đã lưu. Đừng suy ra toàn bộ thao tác là một transaction nguyên tử hoặc một lệnh bulk duy nhất chỉ từ tên `saveAll`.

Nếu một tác vụ cần toàn bộ thay đổi cùng commit hoặc cùng rollback, phải chọn cơ chế transaction phù hợp của store và đảm bảo pipeline tham gia đúng ngữ cảnh reactive. Hợp đồng CRUD dùng chung không thay thế cấu hình đó.

## 10. Sorting, phân trang và backpressure là ba quyết định khác nhau

`findAll(Sort)` mô tả thứ tự, không bổ sung sẵn `findAll(Pageable)` hay `Mono<Page<T>>` vào hai interface của bài. Nếu cần phân trang, phải chọn khả năng query của module hoặc tự xây hợp đồng kết quả rõ ràng.

Ví dụ Spring Data R2DBC cho phép query methods nhận `Pageable` để chuyển offset và sorting vào truy vấn. Đây là khả năng của đường query được module hỗ trợ, không phải một phương thức có sẵn trong `ReactiveSortingRepository`. [Spring Data R2DBC: Query Methods](https://docs.spring.io/spring-data/relational/reference/r2dbc/query-methods.html).

Cần phân biệt:

| Cách làm | Điều nó diễn đạt |
| --- | --- |
| `repository.findAll(sort)` | Yêu cầu thứ tự của kết quả repository |
| `flux.take(20)` | Lấy tối đa một số phần tử ở pipeline và dừng phía sau theo operator |
| Query có limit/offset được store hỗ trợ | Giới hạn phần dữ liệu theo kế hoạch truy vấn |
| `collectList()` | Gom các phần tử thành một danh sách trong ứng dụng |
| Truy vấn count riêng | Lấy một số đếm, không tự đồng bộ với lần đọc danh sách |

Không coi `take(20)` là bằng chứng database chỉ đọc đúng 20 bản ghi hoặc dùng đúng kế hoạch truy vấn mong muốn. Buffer, prefetch, driver và cách store thực hiện query vẫn cần được xét.

Backpressure điều phối nhu cầu dữ liệu trong luồng Reactive Streams; nó không thay thế index, filter hoặc kế hoạch truy vấn. Việc `collectList()` trên một tập dữ liệu không giới hạn cũng có thể làm ứng dụng giữ quá nhiều dữ liệu dù nguồn trả `Flux`.

Nếu cần tổng số và một trang kết quả, hãy mô tả thêm ý nghĩa khi dữ liệu thay đổi giữa hai truy vấn. Ghép hai publisher không tự tạo ảnh chụp nhất quán của database.

## 11. Kiểm thử ví dụ bằng tín hiệu reactive

`StepVerifier` thuộc `reactor-test` giúp mô tả các phần tử mong đợi, completion và lỗi; bước `verify` thực hiện subscription và kiểm tra kịch bản. [Reactor: Testing](https://projectreactor.io/docs/core/release/reference/testing.html).

Các đoạn dưới là ví dụ thực hành, không phải báo cáo đã chạy trên dự án. Chúng giả định repository và service thật được cung cấp bởi môi trường thử nghiệm đã cấu hình; không kèm cấu hình build hoặc database.

### 11.1. Kiểm tra trường hợp không tìm thấy

Trong một store thử nghiệm được bảo đảm không có ID `missing-product`:

```java
import java.time.Duration;
import reactor.test.StepVerifier;

StepVerifier.create(service.required("missing-product"))
        .expectError(ProductNotFoundException.class)
        .verify(Duration.ofSeconds(5));
```

Kiểm tra này quan sát lỗi khi publisher được thực thi. Chỉ gọi `required(...)` rồi kiểm tra object khác null chưa kiểm tra hợp đồng không tìm thấy.

### 11.2. Kiểm tra sorting sau khi lưu dữ liệu mẫu

Đoạn sau yêu cầu collection thử nghiệm ban đầu rỗng và được dùng riêng cho kịch bản. Nó lưu ba giá rồi truy vấn thứ tự tăng dần:

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<List<Long>> prices = repository.saveAll(List.of(
                Product.draft("Mẫu C", 2500),
                Product.draft("Mẫu A", 1200),
                Product.draft("Mẫu B", 1800)))
        .thenMany(repository.findAll(Sort.by("priceInCents", "id")))
        .map(Product::priceInCents)
        .collectList();

StepVerifier.create(prices)
        .expectNext(List.of(1200L, 1800L, 2500L))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
```

Ở đây `collectList()` có phạm vi ba bản ghi đã biết để kiểm tra kết quả, không phải mẫu đọc không giới hạn cho production.

Những tình huống nên thực hành tiếp gồm giá không hợp lệ, cập nhật giữ ID và version, thao tác xóa hoàn tất không có payload, hai sản phẩm trùng giá và xung đột version giữa hai lần đọc/ghi.

## 12. Các quyết định cần giữ nhất quán

Trước khi áp dụng hai interface vào một ứng dụng, hãy trả lời các câu hỏi:

1. Store và driver đang dùng có thực sự hỗ trợ reactive repository không?
2. Repository cần CRUD, sorting hay cả hai, và đã khai báo đủ interface chưa?
3. Mỗi phương thức trả tối đa một giá trị, nhiều giá trị hay chỉ completion?
4. Không tìm thấy dữ liệu được giữ là luồng rỗng hay chuyển thành lỗi nghiệp vụ?
5. Tầng nào thực hiện subscription, và kết quả ghi có được trả về cùng pipeline không?
6. Thứ tự được yêu cầu tại repository hay sau khi dữ liệu đã đi vào ứng dụng?
7. Giới hạn dữ liệu và transaction có được thiết kế theo khả năng của store không?

Việc bọc một lời gọi JPA hoặc JDBC blocking bằng `Mono` không tự biến driver thành reactive. Tên interface và kiểu trả về cần đi cùng hạ tầng thực tế, thay vì chỉ đổi hình thức chữ ký.

Khi giải thích một đoạn code sử dụng `ReactiveCrudRepository` và `ReactiveSortingRepository`, hãy chỉ ra được khả năng của interface, số lượng kết quả, thời điểm thực thi và nơi diễn ra sorting. Đó là nền tảng để tiếp tục học derived queries, phân trang và các khả năng riêng của từng reactive store.
