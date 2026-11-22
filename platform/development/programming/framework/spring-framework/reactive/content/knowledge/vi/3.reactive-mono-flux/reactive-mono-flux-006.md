# Toán tử trả về Publisher mới và yêu cầu nối đúng chuỗi trong Mono/Flux

## 1. Ý tưởng cốt lõi

Trong Project Reactor, mỗi lần gọi toán tử như `map`, `filter`, `flatMap`, `doOnNext`, `onErrorResume`, `timeout` hay `publishOn` trên `Mono`/`Flux`, thông thường ta nhận **một Publisher mới mô tả pipeline có thêm bước xử lý**. Toán tử **không sửa tại chỗ** đối tượng nguồn đã có.

Vì vậy, muốn một bước xử lý có hiệu lực, phải **nối toán tử vào chuỗi đang dùng**, **gán kết quả vào biến** hoặc **return kết quả đó**. Gọi toán tử rồi bỏ kết quả có nghĩa là đã tạo một Publisher trung gian nhưng không đưa nó vào đường thực thi mong muốn.

```java
Flux<Integer> source = Flux.just(1, 2, 3);

// Tạo Publisher mới, rồi bỏ kết quả: không thay đổi source.
source.map(n -> n * 10);

// Vẫn nhận 1, 2, 3:
source.subscribe(System.out::println);
```

Cách đúng:

```java
Flux<Integer> source = Flux.just(1, 2, 3);
Flux<Integer> transformed = source.map(n -> n * 10);

// Nhận 10, 20, 30 từ transformed:
transformed.subscribe(System.out::println);
```

Đây là hai đoạn mã **minh họa đặt trong ngữ cảnh Java có Reactor**, không phải hai file biên dịch độc lập. Ví dụ runnable đầy đủ nằm ở phần 5.

**Ghi nhớ:** `source.map(...)` tạo *kết quả mới*; `source` vẫn là pipeline gốc. Điều này cũng đúng khi method nhận tên là `doOn...` hay `onError...`: nếu Publisher trả về không được sử dụng, bước mới không nằm trong pipeline đã subscribe.

## 2. Publisher mới được hình thành như thế nào?

Hãy hình dung Publisher là một **mô tả về cách phát dữ liệu**. Mỗi toán tử gắn thêm một khâu vào mô tả đó:

```text
source = Flux.range(1, 5)
    |
    | .filter(n -> n % 2 == 0)
    v
filtered (Publisher mới)
    |
    | .map(n -> n * 10)
    v
mapped (Publisher mới)
    |
    | .doOnNext(System.out::println)
    v
observed (Publisher mới)
    |
    | subscribe() bởi nơi tiêu thụ
    v
20, 40
```

Có thể viết dưới dạng một chuỗi:

```java
Flux<Integer> result = Flux.range(1, 5)
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .doOnNext(n -> System.out.println("quan sát: " + n));
```

Hoặc viết tách dòng mà vẫn nối đúng:

```java
Flux<Integer> source = Flux.range(1, 5);
Flux<Integer> even = source.filter(n -> n % 2 == 0);
Flux<Integer> tens = even.map(n -> n * 10);
Flux<Integer> result = tens.doOnNext(System.out::println);
```

Hai cách trên mô tả tương đương về dữ liệu đầu ra. Nếu cần thay đổi biến cùng tên, có thể gán lại:

```java
Flux<Integer> result = Flux.range(1, 5);
result = result.filter(n -> n % 2 == 0);
result = result.map(n -> n * 10);
```

Điều quan trọng là **giữ và dùng Publisher cuối cùng**, không phải biến tên gì hay có bao nhiêu dòng code.

### Assembly và subscription là hai thời điểm khác nhau

Phần lớn thao tác `map`, `filter`, `flatMap` thiết lập hành vi trong giai đoạn **assembly** (lắp chuỗi); callback xử lý dữ liệu thường chỉ được gọi khi có subscription và các tín hiệu đi qua toán tử. Với Publisher **cold** như `Flux.range`, mỗi subscription thường thực thi lại quá trình phát của nguồn.

```text
ASSEMBLY:     Flux.range -> filter -> map -> result
SUBSCRIPTION: Subscriber -> result -> map -> filter -> source
TÍN HIỆU:     source -> filter -> map -> Subscriber
```

- Subscription/demand đi ngược từ downstream tới upstream.
- Dữ liệu và tín hiệu kết thúc/lỗi đi từ upstream tới downstream.
- Chỉ những toán tử **nằm trên đường từ Publisher được subscribe về nguồn** mới tham gia quá trình này.
- `subscribe()` bắt đầu một lượt tiêu thụ; trong Spring WebFlux, framework thường là bên thực hiện việc đăng ký sau khi controller trả Publisher.
- Không phải tất cả Publisher đều cold hay lazy ở mọi khía cạnh: hot source, cache, phần khởi tạo và biểu thức truyền vào `just(...)` có ngữ nghĩa riêng (xem phần 8).

“Publisher mới” là khái niệm về **đối tượng và pipeline**; không có nghĩa Reactor luôn sao chép dữ liệu, tạo thread mới hay lập tức tính toàn bộ kết quả.

## 3. Lỗi quan trọng nhất: gọi toán tử nhưng không dùng giá trị trả về

Ví dụ sai:

```java
Flux<Integer> numbers = Flux.range(1, 4);

numbers.filter(n -> n % 2 == 0);  // Kết quả bị bỏ.
numbers.map(n -> n * 10);          // Kết quả bị bỏ.
numbers.doOnNext(n -> log.info("value={}", n)); // Kết quả bị bỏ.

// Đây vẫn là Publisher ban đầu, nhận 1, 2, 3, 4:
return numbers;
```

Đoạn trên minh họa phần thân method trả `Flux<Integer>` có sẵn biến logger `log`. Vì ba Publisher mới đều không được nối hoặc lưu lại, `return numbers` vẫn trả luồng gốc. Dòng `log.info` trong toán tử bị bỏ **sẽ không chạy trong subscription này**.

Cách sửa:

```java
return numbers
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10)
        .doOnNext(n -> log.info("value={}", n));
```

Giả sử `numbers = Flux.range(1, 4)`, dữ liệu đầu ra bây giờ là `20, 40`; logger ghi những phần tử đó khi chúng đi qua pipeline.

**Một tình huống sai khác ở tầng service:**

```java
public Mono<UserDto> loadUser(String id) {
    Mono<User> user = repository.findById(id);

    user.map(this::toDto); // Publisher<Dto> bị bỏ.
    // return user;     // Sai kiểu: Mono<User> không phải Mono<UserDto>.
    // ...
}
```

Cách đúng:

```java
public Mono<UserDto> loadUser(String id) {
    return repository.findById(id).map(this::toDto);
}
```

Đây là **các đoạn trong service đang có** `repository`, `User`, `UserDto` và `toDto`; chúng minh họa việc giữ kiểu và chuỗi Publisher, không tự chạy độc lập. Với nhiều đoạn xử lý, return chính Publisher sau cùng.

## 4. Toán tử nào cũng cần được nối vào chuỗi hợp lệ

| Toán tử | Publisher trả về (điển hình) | Mục đích | Lỗi hay gặp |
|---|---|---|---|
| `Flux.map(f)` / `Mono.map(f)` | `Flux<R>` / `Mono<R>` | Biến đổi giá trị đồng bộ | Bỏ kết quả rồi subscribe nguồn cũ. |
| `Flux.filter(p)` / `Mono.filter(p)` | `Flux<T>` / `Mono<T>` | Chỉ giữ dữ liệu thỏa điều kiện | Tưởng nguồn ban đầu đã bị lọc. |
| `Mono.flatMap(f)` | `Mono<R>` | Kết hợp bước trả `Mono<R>` | Dùng `map` làm phát sinh `Mono<Mono<R>>`. |
| `Flux.flatMap(f)` | `Flux<R>` | Ánh xạ mỗi phần tử thành Publisher, phối hợp các luồng bên trong | Mặc định thứ tự đầu ra luôn như đầu vào. |
| `Flux.concatMap(f)` | `Flux<R>` | Nối từng Publisher trong theo trình tự đầu vào | Dùng `flatMap` khi cần thứ tự nghiêm ngặt. |
| `Mono.flatMapMany(f)` | `Flux<R>` | Một đầu vào Mono dẫn đến nhiều giá trị | Dùng `flatMap` của Mono trong tình huống cần Flux. |
| `doOnNext`, `doOnError`, `doFinally` | Publisher cùng kiểu (điển hình) | Gắn tác vụ quan sát/vòng đời | Tưởng chỉ cần gọi là hook sẽ chạy. |
| `onErrorResume`, `onErrorMap` | Publisher cùng họ | Chuyển lỗi thành dự phòng/lỗi khác | Gọi rồi bỏ kết quả, không có xử lý lỗi. |
| `defaultIfEmpty`, `switchIfEmpty` | Publisher mới | Định nghĩa giá trị/nhánh khi rỗng | Tưởng đã thay đổi đối tượng gốc. |
| `timeout`, `retry`, `publishOn`, `subscribeOn` | Publisher mới | Thêm giới hạn thời gian, thử lại hoặc chính sách thực thi | Gọi độc lập rồi subscribe Publisher cũ. |
| `then()`, `thenReturn(v)`, `then(other)` | `Mono<Void>` / `Mono<V>` / Publisher theo overload | Chờ hoàn thành và chuyển sang bước kế | Không nhận ra phần tử `onNext` trước `then` đã bị bỏ. |

Danh sách là những trường hợp thông dụng, không phải hợp đồng “mọi overload luôn trả đúng cùng kiểu”; hãy đọc chữ ký cụ thể. Ví dụ `Flux.next()` trả `Mono<T>`, `Mono.flux()` trả `Flux<T>`, `Flux.collectList()` trả `Mono<List<T>>`. Điều xuyên suốt là phải **dùng giá trị trả về thực tế** để không đánh mất bước xử lý.

### `map` và `flatMap` khác nhau ở kiểu trả về của callback

Khi hàm biến đổi trả **giá trị thường**, dùng `map`:

```java
Mono<String> result = Mono.just("java")
        .map(String::toUpperCase);  // Mono<String>, giá trị "JAVA"
```

Khi hàm biến đổi trả **Publisher**, dùng `flatMap` để không lồng `Mono`:

```java
Mono<String> nested = Mono.just("java")
        .map(value -> Mono.just(value.toUpperCase()))
        .map(inner -> "inner publisher=" + inner.getClass().getSimpleName());
```

Đoạn `nested` trên cố ý minh họa rằng `map` nhìn `Mono` nội bộ như một **giá trị thông thường**, không tự subscribe và lấy kết quả bên trong. Với nghiệp vụ thực tế:

```java
Mono<String> result = Mono.just("java")
        .flatMap(value -> Mono.just(value.toUpperCase()));
```

`flatMap` nhận kết quả Publisher từ callback và phối hợp đăng ký vào Publisher đó. Không dùng `.subscribe()` bên trong `map` để “lấy giá trị”; đó là tạo một subscription tách rời khỏi luồng cha, khiến việc chờ kết quả, chuyển lỗi và hủy khó kiểm soát.

### Thứ tự toán tử thay đổi kết quả

```java
Flux<Integer> first = Flux.range(1, 4)
        .filter(n -> n > 2)
        .map(n -> n * 10); // 30, 40

Flux<Integer> second = Flux.range(1, 4)
        .map(n -> n * 10)
        .filter(n -> n > 2); // 10, 20, 30, 40
```

Toán tử được ghép **theo đúng thứ tự viết** và xử lý dữ liệu theo ngữ nghĩa của mỗi bước. Vì vậy nối đúng chuỗi mới là điều kiện cần; còn phải chọn đúng vị trí toán tử để có hành vi nghiệp vụ mong muốn.

## 5. Ví dụ Java 17+ chạy được: sai, đúng, và thời điểm thực thi

Ví dụ này chạy độc lập với **JDK 17+ và Maven**, không cần Spring Boot. Dùng `Flux.range` đồng bộ để stdout chính xác và dễ đối chiếu.

Cấu trúc dự án:

```text
reactor-chain/
├── pom.xml
└── src/main/java/example/ChainDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-chain</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.ChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/ChainDemo.java`:

```java
package example;

import reactor.core.publisher.Flux;

public class ChainDemo {
    public static void main(String[] args) {
        Flux<Integer> source = Flux.range(1, 4);

        System.out.println("A - bo qua publisher moi:");
        source.map(n -> n * 10);         // Sai: bo ket qua.
        source.filter(n -> n % 2 == 0);  // Sai: bo ket qua.
        source.subscribe(n -> System.out.println("raw=" + n));

        System.out.println("B - noi dung chuoi:");
        Flux<Integer> result = source
                .filter(n -> n % 2 == 0)
                .map(n -> n * 10)
                .doOnNext(n -> System.out.println("peek=" + n));

        result.subscribe(n -> System.out.println("out=" + n));

        System.out.println("C - assembly va subscription:");
        Flux<Integer> lazy = source.map(n -> {
            System.out.println("map=" + n);
            return n + 100;
        });

        System.out.println("da tao pipeline");
        lazy.take(2).subscribe(n -> System.out.println("got=" + n));
    }
}
```

Chạy trong thư mục `reactor-chain`:

```bash
mvn -q compile exec:java
```

Stdout của **chương trình** (bỏ qua thông báo do Maven/plugin có thể in ra ngoài):

```text
A - bo qua publisher moi:
raw=1
raw=2
raw=3
raw=4
B - noi dung chuoi:
peek=20
out=20
peek=40
out=40
C - assembly va subscription:
da tao pipeline
map=1
got=101
map=2
got=102
```

**Giải thích chính xác:**

1. **A:** `map` và `filter` đều tạo Publisher mới nhưng bị bỏ, nên `source.subscribe(...)` vẫn nhận `1, 2, 3, 4`.
2. **B:** `result` chứa chuỗi `filter → map → doOnNext`; phần tử chẵn được biến thành `20`, `40`. `peek` in ngay trước khi phần tử đi đến callback của `subscribe`, nên mỗi `peek=` xuất hiện trước `out=` tương ứng.
3. **C:** Lời gọi `source.map(...)` chỉ xây pipeline; không in `map=` tại thời điểm đó. Sau khi in `da tao pipeline`, `subscribe` của `lazy.take(2)` kích hoạt hai lần gọi callback map, rồi `take(2)` kết thúc lượt tiêu thụ. Trong ví dụ dùng nguồn cold đồng bộ, chỉ hai phần tử đầu được xử lý.

Nếu sửa B thành `source.filter(...); source.map(...); result = source;`, kết quả quay về `1, 2, 3, 4`. Nếu không subscribe ở C, không có `map=` hay `got=`; chỉ có dòng `da tao pipeline`.

## 6. Nối đúng chuỗi khi code được tách thành nhiều method

### Cách 1: Return Publisher sau cùng

Ví dụ phần thân một service có `repository.findById` trả `Mono<User>` và `saveAudit` trả `Mono<Void>`:

```java
Mono<UserDto> findUser(String id) {
    return repository.findById(id)
            .filter(User::isActive)
            .flatMap(user ->
                    saveAudit(user)
                            .thenReturn(toDto(user))
            );
}
```

Đoạn trên **cần các type/service thật từ ứng dụng**, không phải chương trình độc lập. `thenReturn(toDto(user))` chỉ phát DTO khi bước lưu audit hoàn thành thành công; nếu `saveAudit` báo lỗi, lỗi theo cùng pipeline. `toDto(user)` là phép tính Java thực hiện khi xây Publisher nội bộ của nhánh `flatMap`; nếu việc tính DTO có side effect đáng kể, cân nhắc đưa nó vào callback lazy thích hợp, ví dụ `.then(Mono.fromSupplier(() -> toDto(user)))`.

### Cách 2: Dùng biến trung gian, gán lại đúng chỗ

```java
Flux<String> names = Flux.just("An", "Binh", "Chi");
names = names.filter(name -> name.length() >= 3);
names = names.map(String::toUpperCase);

return names;
```

`names` là **tham chiếu Java** có thể trỏ đến Publisher mới. Việc gán lại biến không phải thao tác thay đổi nội dung `Flux` gốc.

### Cách 3: Tránh subscribe lồng trong service

Cách sai, giả sử `auditService.write(user)` trả `Mono<Void>`:

```java
return userRepository.findById(id)
        .map(user -> {
            auditService.write(user).subscribe(); // Subscription tach roi.
            return user;
        });
```

Lỗi: bước audit được chạy dưới một subscription khác. Pipeline bên ngoài có thể hoàn tất trước audit; lỗi của audit không tự động chuyển đến subscriber bên ngoài; hủy outer không bảo đảm hủy tác vụ audit này.

Cách đúng khi kết quả phải **đợi audit**:

```java
return userRepository.findById(id)
        .flatMap(user ->
                auditService.write(user)
                        .thenReturn(user)
        );
```

Như vậy tác vụ audit là một phần của luồng được trả về và framework/caller có thể quan sát vòng đời chung.

## 7. Tại ranh giới ứng dụng Spring WebFlux

Trong controller Spring WebFlux, **return Publisher cuối cùng** để framework có thể subscribe và điều khiển vòng đời HTTP:

```java
@RestController
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    Mono<ProductDto> find(@PathVariable String id) {
        return service.findById(id)
                .filter(Product::isEnabled)
                .map(ProductDto::from)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }
}
```

Đoạn controller này minh họa API và **phải đặt trong dự án Spring WebFlux** có các type `ProductService`, `Product`, `ProductDto` phù hợp, cùng imports `@RestController`, `@GetMapping`, `@PathVariable`, `Mono`, `ResponseStatusException`, `HttpStatus`. `filter` có thể làm Mono rỗng, `switchIfEmpty` chuyển trường hợp không có kết quả thành lỗi 404. Cả ba toán tử đều được nối vào Publisher được return, nên được áp dụng khi framework subscribe.

Cách sai:

```java
Mono<Product> product = service.findById(id);
product.filter(Product::isEnabled); // Da bo Publisher moi.
return product;                      // Tra ve ban goc, khong loc.
```

Không nên gọi `subscribe()` trong controller chỉ để “bắt đầu” và rồi return Publisher khác hoặc `void`. Ở boundary HTTP, WebFlux thường subscribe Publisher do controller trả về; việc tự subscribe có thể gây subscription thứ hai, request lặp lại, mất liên kết đến xử lý lỗi hoặc hủy khi client ngắt. Với mục đích tích hợp service, thường chỉ cần **trả** chuỗi Publisher đã ghép đầy đủ.

## 8. Ba sắc thái quan trọng để tránh hiểu sai

### 8.1. Toán tử mới không đồng nghĩa toàn bộ biểu thức đều lazy

`map` nhận một hàm và thường chỉ gọi hàm khi nhận dữ liệu, nhưng **tham số Java được tính trước khi gọi method**:

```java
Mono<String> eager = Mono.just(loadValue());
```

Trong đoạn trên, `loadValue()` được gọi ngay khi xây biểu thức `Mono.just(...)`, trước khi subscribe. Muốn trì hoãn việc gọi nguồn dữ liệu đến mỗi subscription:

```java
Mono<String> deferred = Mono.fromSupplier(() -> loadValue());
```

Hai đoạn này là minh họa khi `loadValue()` trả `String` không null. Nếu `loadValue()` có thể trả null, cần thiết kế rõ cách biểu diễn rỗng, chẳng hạn `Mono.fromCallable(...)` có thể hoàn thành rỗng với kết quả null, hoặc dùng Optional/kiểm tra phù hợp. Đừng khẳng định mọi thao tác xây Publisher đều hoàn toàn không thực thi gì.

### 8.2. Hot Publisher, cache và chia sẻ có cách phát khác

Một cold pipeline như `Flux.range` thường thực thi lại cho từng subscriber. Nguồn hot có thể đã phát trước khi subscriber xuất hiện. Các toán tử như `cache()`, `share()` hoặc `publish()` thay đổi cách sử dụng nguồn và chia sẻ tín hiệu. Dù vậy, **cú pháp vẫn giữ nguyên**: mỗi toán tử trả về một Publisher, phải giữ Publisher đó nếu muốn sử dụng cách chia sẻ mới.

```java
Flux<Integer> shared = source.share(); // Phải subscribe "shared".
```

Gọi `source.share();` rồi tiếp tục subscribe `source` sẽ không biến `source` thành luồng shared.

### 8.3. Nối chuỗi khác với đảm bảo thứ tự, thread và backpressure

Trong Reactive Streams, Publisher được subscribe cần tuân thủ cơ chế yêu cầu dữ liệu; các toán tử nằm trong chuỗi mới có cơ hội điều phối demand và cancel. Nhưng không thể suy luận chỉ vì chuỗi được nối đúng thì sẽ có thread riêng, thứ tự luôn giữ nguyên hoặc không có buffer.

- `map` biến đổi từng phần tử, thường giữ thứ tự đã nhận.
- `flatMap` kết hợp nhiều Publisher bên trong và có thể xen kẽ kết quả; `concatMap` phù hợp hơn nếu bắt buộc giữ thứ tự.
- `publishOn` hoặc `subscribeOn` thay đổi ngữ cảnh lập lịch theo quy tắc Reactor; gọi toán tử rồi bỏ Publisher trả về sẽ không đưa chính sách đó vào subscription đang dùng.
- `doOnNext` quan sát tín hiệu; không phải toán tử dùng để thay đổi kiểu/giá trị. Muốn biến đổi giá trị, dùng `map`.
- `doOnError` quan sát lỗi chứ không xử lý lỗi; `onErrorResume` mới thiết lập nhánh dự phòng. Cả hai vẫn phải nối vào Publisher sẽ tiêu thụ.

## 9. Cách nhận diện và sửa lỗi trong code review

| Dấu hiệu | Cách kiểm tra / sửa |
|---|---|
| Một dòng kết thúc ở `.map(...)`, `.filter(...)`, `.doOnNext(...)` mà kết quả không được gán/return/dùng làm tham số | Kiểm tra Publisher trả về đi đâu. Nếu bị bỏ, nối vào chuỗi cuối cùng. |
| Sau `.onErrorResume(...)` vẫn xảy ra lỗi như chưa thêm fallback | Đảm bảo đang subscribe/return chính Publisher có `onErrorResume`, và fallback xử lý đúng loại lỗi. |
| Debug `doOnNext` không chạy dù Publisher gốc có dữ liệu | Kiểm tra `doOnNext` có nằm trên Publisher được subscribe, có demand và không bị `filter` loại hết không. |
| Gọi `.subscribe()` trong một `.map(...)` hoặc service WebFlux | Xem có thể đưa tác vụ vào `.flatMap(...)`, `.then(...)` và return Publisher chung không. |
| `Mono<Mono<T>>` hoặc `Flux<Mono<T>>` xuất hiện ngoài ý muốn | Callback trả Publisher: cân nhắc `flatMap` hoặc `concatMap` phù hợp. |
| `.then()` làm mất dữ liệu | Đây là ngữ nghĩa chủ động bỏ giá trị của upstream; dùng `thenReturn`, `flatMap` hay operator khác nếu cần giữ dữ liệu. |
| Toán tử xử lý đúng nhưng không có output | Kiểm tra Publisher có được subscribe tại boundary phù hợp hay không; nếu chưa có subscriber, cold pipeline thường chưa phát. |
| Chạy lại request/API ngoài ý muốn | Xem có nhiều subscription vào cold source, `subscribe()` lồng hoặc subscribe thủ công; cân nhắc cấu trúc lại chuỗi và yêu cầu cache/chia sẻ khi có căn cứ. |

### Quy trình tư duy ngắn khi đọc pipeline

1. **Xác định nguồn:** `Mono`/`Flux` xuất phát từ đâu?
2. **Theo dõi Publisher trả về:** mỗi toán tử mới nối tiếp vào biến/biểu thức nào, có bị bỏ không?
3. **Kiểm tra kiểu:** `map` cho giá trị thường; `flatMap`/`concatMap` cho callback trả Publisher; toán tử có đổi `Flux` thành `Mono` không?
4. **Kiểm tra thứ tự:** toán tử lọc, biến đổi, thay lỗi, xử lý rỗng có ở vị trí đúng không?
5. **Xác định boundary:** ai thực hiện subscription? WebFlux thường làm việc đó sau khi controller return; ứng dụng command-line có thể tự `subscribe()` hoặc `block()` ở ranh giới ngoài.
6. **Xác định hành vi khi lỗi/hủy:** các tác vụ bất đồng bộ liên quan có thuộc cùng pipeline không?

## 10. Bài tập tự kiểm tra

Cho đoạn mã:

```java
Flux<Integer> p = Flux.just(2, 3, 4);
p.map(n -> n + 1);
p.filter(n -> n % 2 == 0);
p.subscribe(System.out::println);
```

**Câu hỏi 1:** Dữ liệu được in ra là gì? Vì sao?

**Đáp án:** `2`, `3`, `4` (mỗi số một dòng), vì kết quả trả về từ `map` và `filter` đều bị bỏ.

**Câu hỏi 2:** Viết lại để cộng 1 rồi chỉ giữ số chẵn.

```java
Flux<Integer> p = Flux.just(2, 3, 4)
        .map(n -> n + 1)
        .filter(n -> n % 2 == 0);
p.subscribe(System.out::println);
```

**Đáp án stdout:** Chỉ `4`, vì lần lượt biến `2,3,4` thành `3,4,5`, sau đó lọc còn `4`.

**Câu hỏi 3:** Nếu thay `filter` thành `doOnNext(System.out::println)` thì có tạo ra Publisher mới không? Có cần nối kết quả không?

**Đáp án:** Có. `doOnNext` cũng trả Publisher mới; nếu bỏ Publisher mới thì callback quan sát không tham gia chuỗi được subscribe. `doOnNext` chỉ quan sát giá trị, không biến đổi chúng.

**Kết luận học tập:** Mỗi toán tử của Mono/Flux tạo ra một mắt xích Publisher mới. Hãy **nối, gán hoặc return** kết quả đó và **đăng ký ở boundary thích hợp**. Việc nắm rõ Publisher nào thực sự được tiêu thụ sẽ giúp tránh phần lớn lỗi “đã gọi toán tử nhưng không có tác dụng” trong ứng dụng Reactor và Spring WebFlux.
