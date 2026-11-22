# onErrorMap để chuyển đổi lỗi kỹ thuật thành lỗi nghiệp vụ

## 1. Bài toán: vì sao cần đổi loại lỗi?

Trong ứng dụng Spring WebFlux, một service có thể nhận **IOException** khi đọc dữ liệu, **DataAccessException** khi database gặp vấn đề, **WebClientRequestException** khi kết nối đối tác thất bại, hay **TimeoutException** từ một lời gọi có giới hạn thời gian. Những exception này mô tả chi tiết **kỹ thuật** của hạ tầng. Trong khi đó, tầng nghiệp vụ và API thường cần diễn đạt ý nghĩa ổn định, chẳng hạn **CatalogUnavailableException** (kho sản phẩm tạm không sẵn sàng), **PaymentProviderUnavailableException** (không kết nối được dịch vụ thanh toán) hay **ProductNotFoundException** (sản phẩm không tồn tại).

**onErrorMap** trong Project Reactor cho phép biến một tín hiệu **onError(technicalException)** thành **onError(domainException)** mà không thay đổi dữ liệu thành công của Mono/Flux.

~~~text
Publisher kỹ thuật
  |
  +-- onNext(value) ---------------> giữ nguyên value
  |
  +-- onComplete() ----------------> giữ nguyên complete
  |
  +-- onError(IOException) --------> onErrorMap
                                         |
                                  tạo domain error
                                         |
                                         v
                               onError(CatalogUnavailableException)
                                         |
                                         v
                             service / controller / error handler
~~~

**Nội dung cốt lõi:** onErrorMap **đổi Throwable chứ không phục hồi thành công**. Lỗi vẫn kết thúc subscription. Operator này không tự chạy retry, không bổ sung thread hay scheduler, không tự trả HTTP 404/503 và không khiến nguồn phát tiếp những phần tử sau lỗi.

Ví dụ ý tưởng:

~~~java
Mono<Product> result = repository.findById(id)
    .onErrorMap(DataAccessResourceFailureException.class,
        cause -> new CatalogUnavailableException(
            "Catalog temporarily unavailable", cause));
~~~

Đây là **đoạn minh họa** trong một service: Product, repository, id và CatalogUnavailableException phải được định nghĩa, đồng thời cần các import thích hợp. Nếu repository phát DataAccessResourceFailureException thì kết quả là lỗi domain; nếu repository trả Mono.empty(), onErrorMap **không chạy**, bởi không có onError.

## 2. Reactive Streams: lỗi là tín hiệu kết thúc

Publisher/Subscriber trao đổi ba loại tín hiệu chính:

- **onNext(T):** có một phần tử thành công.
- **onComplete():** nguồn hoàn tất bình thường.
- **onError(Throwable):** nguồn kết thúc bằng lỗi.

onComplete và onError là **hai cách kết thúc thay thế nhau** của một subscription. Sau khi phát onError, nguồn không được tiếp tục gửi onNext cho subscription đó.

~~~text
Flux:
onNext("A") -> onNext("B") -> onError(IOException)
                                |
                            onErrorMap
                                |
onNext("A") -> onNext("B") -> onError(CatalogUnavailableException)
~~~

Hai giá trị A và B đã phát vẫn được giữ. Không có giá trị C tiếp theo. Điều này khác cơ chế **bắt exception trong vòng lặp Java** để bỏ qua một phần tử rồi tiếp tục vòng lặp.

Với Mono có giá trị hoặc Mono.empty(), mapper lỗi không được gọi vì nguồn không phát onError. Với Flux có lỗi sau nhiều giá trị, mapper được gọi khi lỗi đi qua vị trí operator đó.

## 3. Ba overload của onErrorMap

Cả **Mono<T>** và **Flux<T>** đều hỗ trợ những biến thể quan trọng sau:

~~~java
// Chuyển tất cả lỗi:
onErrorMap(Function<? super Throwable, ? extends Throwable> mapper)

// Chỉ chuyển lỗi thuộc một loại phù hợp:
<E extends Throwable> onErrorMap(
    Class<E> type,
    Function<? super E, ? extends Throwable> mapper)

// Chuyển lỗi nếu một predicate khớp:
onErrorMap(
    Predicate<? super Throwable> predicate,
    Function<? super Throwable, ? extends Throwable> mapper)
~~~

Đây là **mô tả chữ ký tham số**, không phải khai báo Java đầy đủ; kiểu trả về sẽ là cùng loại Publisher được gọi, Mono<T> hoặc Flux<T>.

| Overload | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| **onErrorMap(mapper)** | Áp dụng cho mọi Throwable tới operator | Dùng khi ranh giới thực sự cần chuẩn hóa tất cả lỗi; dễ bọc nhầm lỗi đã phân loại |
| **onErrorMap(Class, mapper)** | Chỉ lỗi thuộc kiểu được chỉ định, kể cả subclass phù hợp | Ưu tiên khi nhóm lỗi hạ tầng đã được xác định rõ |
| **onErrorMap(predicate, mapper)** | Chỉ lỗi thỏa điều kiện | Dùng khi cần xét type, mã lỗi hoặc thuộc tính đáng tin cậy |

Nếu lỗi không khớp Class hoặc predicate, operator **để lỗi gốc đi tiếp**. Nếu khớp, mapper được gọi **đồng bộ** để tạo một Throwable mới.

### 3.1. Lọc theo kiểu lỗi

~~~java
Mono<String> result = Mono.<String>error(
        new java.io.IOException("connection failed"))
    .onErrorMap(java.io.IOException.class,
        cause -> new StorageUnavailableException(
            "Storage cannot be reached", cause));
~~~

Đoạn ví dụ cần class StorageUnavailableException. Kết quả khi subscribe là **onError(StorageUnavailableException)**, không phải String.

### 3.2. Dùng predicate

~~~java
Mono<String> result = Mono.<String>error(
        new java.io.IOException("timed out"))
    .onErrorMap(
        error -> error instanceof java.io.IOException
                 && error.getMessage() != null
                 && error.getMessage().contains("timed out"),
        cause -> new PartnerTimeoutException(
            "Partner did not answer", cause));
~~~

Mẫu trên minh họa cú pháp predicate; PartnerTimeoutException cần được định nghĩa. Trong production, nên chọn **exception type, error code, HTTP status hoặc trường dữ liệu ổn định**. Chỉ kiểm tra chuỗi message như ví dụ có thể giòn, vì thông điệp của driver hoặc nhà cung cấp thay đổi theo phiên bản.

### 3.3. Tránh lạm dụng mapper áp dụng mọi Throwable

~~~java
Mono<String> result = networkCall()
    .onErrorMap(error ->
        new PartnerUnavailableException(
            "Partner unavailable", error));
~~~

Đây là đoạn minh họa. Nếu networkCall có thể phát cả lỗi validation, permission hoặc NullPointerException do bug, mã này biến **tất cả** thành “partner unavailable”. Lỗi cần được phân loại trước; thường nên dùng overload Class dành cho lỗi kỹ thuật cụ thể.

## 4. Giữ nguyên cause để có thể chẩn đoán

Domain exception cho người gọi một **ý nghĩa ổn định**, còn exception gốc cung cấp **nguyên nhân kỹ thuật** cho vận hành. Một mẫu class:

~~~java
public final class CatalogUnavailableException extends RuntimeException {
    public CatalogUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Khi map:

~~~java
Mono<Catalog> catalog = repository.getCatalog()
    .onErrorMap(DataAccessResourceFailureException.class,
        cause -> new CatalogUnavailableException(
            "Catalog storage is temporarily unavailable", cause));
~~~

Đây là đoạn minh họa cần repository, Catalog và import Spring DAO. Chuỗi lỗi có thể thành:

~~~text
CatalogUnavailableException
  message: "Catalog storage is temporarily unavailable"
  cause:
    DataAccessResourceFailureException
      cause:
        lỗi network / database driver thực tế (nếu có)
~~~

**Không trả toàn bộ cause chain hoặc stack trace cho HTTP client.** Message từ driver có thể chứa SQL, hostname, thông tin xác thực hoặc dữ liệu nội bộ. Tầng HTTP nên trả **mã lỗi hợp đồng** và mô tả an toàn; hệ thống log/tracing nội bộ giữ thông tin cần thiết với chính sách redaction.

Nếu mapper chỉ tạo new CatalogUnavailableException("unavailable") và bỏ cause, việc tìm nguyên nhân ở production khó hơn đáng kể. Nên định nghĩa constructor nhận Throwable cho lỗi có nguồn gốc từ hạ tầng.

## 5. Phân biệt “không có kết quả” với “không thể lấy kết quả”

Giả sử một repository có chữ ký:

~~~java
Mono<Product> findById(String id);
~~~

Có ít nhất ba tình huống:

| Tín hiệu repository | Ý nghĩa có thể có | Cách xử lý |
| --- | --- | --- |
| **onNext(Product) rồi onComplete** | Tìm được sản phẩm | Trả Product cho service |
| **onComplete, không onNext** | Không có bản ghi tương ứng | Dùng switchIfEmpty nếu hợp đồng yêu cầu NotFound |
| **onError(DataAccess...)** | Có lỗi truy cập dữ liệu | Dùng onErrorMap sang lỗi unavailable phù hợp |

Ví dụ:

~~~java
Mono<Product> result = repository.findById(id)
    .onErrorMap(DataAccessResourceFailureException.class,
        e -> new CatalogUnavailableException(
            "Catalog storage unavailable", e))
    .switchIfEmpty(Mono.error(
        new ProductNotFoundException(id)));
~~~

Đoạn trên cần các kiểu ứng dụng. **Mono.empty() không phát onError**, nên onErrorMap không biến rỗng thành “not found”. Ngược lại, lỗi không kết nối được database **không phải** bằng chứng một product không tồn tại; không nên map thành ProductNotFoundException chỉ để trả 404.

Quy tắc này đặc biệt quan trọng trong API thương mại: trả 404 khi storage đang lỗi có thể khiến client xóa cache hoặc hiểu nhầm tài nguyên đã bị xóa.

## 6. onErrorMap khác onErrorResume, onErrorReturn, doOnError

| Operator | Sau onError xảy ra điều gì? | Trường hợp |
| --- | --- | --- |
| **onErrorMap** | Thay Throwable bằng Throwable khác, vẫn kết thúc bằng lỗi | Chuẩn hóa lỗi technical -> domain |
| **onErrorResume** | Subscribe vào một Publisher fallback, có thể phát dữ liệu/rỗng/lỗi khác | Khôi phục dữ liệu, fallback có điều kiện |
| **onErrorReturn** | Phát một giá trị fallback rồi hoàn tất | Giá trị mặc định đơn giản |
| **doOnError** | Thực hiện side effect, thông thường giữ lỗi nguyên | Log, metric, tracing |
| **onErrorComplete** | Chuyển lỗi được chọn thành hoàn tất bình thường | Chỉ khi được phép bỏ qua lỗi |
| **retry / retryWhen** | Resubscribe vào nguồn theo chính sách | Lỗi tạm thời có thể lặp lại an toàn |
| **map** | Chuyển phần tử thành công onNext | Biến đổi dữ liệu, không xử lý onError |

Ví dụ ý tưởng:

~~~java
Mono<String> source =
    Mono.error(new java.io.IOException("offline"));

Mono<String> mapped = source.onErrorMap(
    java.io.IOException.class,
    error -> new StorageUnavailableException(
        "Storage unavailable", error));
// mapped vẫn kết thúc bằng onError(StorageUnavailableException).

Mono<String> resumed = source.onErrorResume(
    java.io.IOException.class,
    error -> Mono.just("cached"));
// resumed phát "cached", rồi complete.

Mono<String> defaulted = source.onErrorReturn("default");
// defaulted phát "default", rồi complete.

Mono<String> observed = source.doOnError(
    error -> System.out.println("cause=" +
        error.getClass().getSimpleName()));
// observed vẫn báo IOException.
~~~

Ví dụ chưa độc lập vì StorageUnavailableException chưa được định nghĩa trong đoạn. **onErrorMap không dùng để trả dữ liệu dự phòng**; muốn fallback cần chọn một operator có semantics phục hồi.

Trong Flux, **onErrorResume** thay thế phần cuối của một stream đã lỗi. Nó không tự động quay lại nguồn cũ để xử lý các item phía sau lỗi. Để phục hồi **theo từng item**, hãy đặt xử lý lỗi ở bên trong inner Publisher được tạo từ concatMap/flatMap, không chỉ ở bên ngoài cả stream.

## 7. Chương trình Java 17+ hoàn chỉnh có kết quả cụ thể

Ví dụ sau kiểm chứng bốn trường hợp: thành công không gọi mapper; lỗi IOException chuyển thành CatalogUnavailableException và giữ cause; lỗi khác loại truyền nguyên; Flux có giá trị trước lỗi và fallback sau lỗi. Không cần database hay HTTP server để chạy.

Yêu cầu **JDK 17+**, **Maven 3.9+**:

~~~text
reactor-error-mapping/
  pom.xml
  src/main/java/example/OnErrorMapDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-error-mapping</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.17</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/OnErrorMapDemo.java**

~~~java
package example;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Signal;

public final class OnErrorMapDemo {
    static final class CatalogUnavailableException extends RuntimeException {
        CatalogUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        AtomicInteger mapperCalls = new AtomicInteger();

        Mono<String> healthy = Mono.fromSupplier(() -> "available")
            .onErrorMap(IOException.class, error -> {
                mapperCalls.incrementAndGet();
                return new CatalogUnavailableException("Catalog unavailable", error);
            });

        System.out.println("healthy=" + healthy.block());
        System.out.println("mapperCalls=" + mapperCalls.get());

        Mono<String> technical = Mono.fromCallable(() -> {
            throw new IOException("connection refused");
        });

        Mono<String> domain = technical.onErrorMap(
            IOException.class,
            error -> new CatalogUnavailableException(
                "Catalog service unavailable", error));

        Signal<String> signal = domain.materialize().block();
        Throwable mapped = signal.getThrowable();

        System.out.println("mapped.type=" + mapped.getClass().getSimpleName());
        System.out.println("mapped.message=" + mapped.getMessage());
        System.out.println("mapped.cause=" +
                mapped.getCause().getClass().getSimpleName());
        System.out.println("mapped.causeMessage=" +
                mapped.getCause().getMessage());

        Throwable unmatched = Mono.<String>error(
                new IllegalArgumentException("bad input"))
            .onErrorMap(IOException.class,
                error -> new CatalogUnavailableException("Storage failure", error))
            .materialize()
            .block()
            .getThrowable();

        System.out.println("unmatched.type=" +
                unmatched.getClass().getSimpleName());

        Flux<String> stream = Flux.concat(
                Flux.just("first"),
                Flux.<String>error(new IOException("stream read failed")),
                Flux.just("never"))
            .onErrorMap(IOException.class,
                error -> new CatalogUnavailableException("Read failed", error))
            .onErrorResume(CatalogUnavailableException.class,
                error -> Flux.just("fallback"));

        System.out.println("stream=" + stream.collectList().block());
    }
}
~~~

Lệnh chạy từ thư mục dự án:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.OnErrorMapDemo
~~~

**Các dòng do chương trình in:**

~~~text
healthy=available
mapperCalls=0
mapped.type=CatalogUnavailableException
mapped.message=Catalog service unavailable
mapped.cause=IOException
mapped.causeMessage=connection refused
unmatched.type=IllegalArgumentException
stream=[first, fallback]
~~~

Giải thích:

1. **healthy** chỉ phát giá trị, vì vậy mapper không chạy và counter bằng 0.
2. **Mono.fromCallable** biến checked IOException phát sinh trong Callable thành tín hiệu onError ở thời điểm subscription.
3. **onErrorMap(IOException.class, ...)** đổi exception sang CatalogUnavailableException nhưng giữ nguyên IOException ở **getCause()**.
4. **materialize()** biến terminal signal thành đối tượng Signal cho mục đích quan sát trong ví dụ CLI. Không cần materialize chỉ để xử lý lỗi trong ứng dụng thật.
5. IllegalArgumentException không thuộc IOException nên đi qua operator giữ nguyên.
6. Với Flux.concat, giá trị "first" đã phát; IOException chấm dứt nguồn, onErrorMap đổi lỗi, onErrorResume phát "fallback". Giá trị "never" không được phát.

Chương trình tạo IOException có chủ đích để stdout có thể dự đoán chính xác. Nó không giả định lỗi network ngoài đời luôn có message “connection refused”.

## 8. Lỗi trước khi tạo Mono có được onErrorMap bắt không?

Chưa chắc. Xem code:

~~~java
Mono<String> source = Mono.just(blockingOrThrow())
    .onErrorMap(e -> new StorageUnavailableException("failed", e));
~~~

Java đánh giá **blockingOrThrow() trước** khi gọi Mono.just. Nếu hàm ném exception ngay, Mono **chưa được tạo**, nên không có pipeline để onErrorMap xử lý.

Đưa lời gọi vào factory lazy:

~~~java
Mono<String> source = Mono.fromCallable(() -> blockingOrThrow())
    .onErrorMap(java.io.IOException.class,
        e -> new StorageUnavailableException("failed", e));
~~~

Hai đoạn là **mã minh họa** vì cần khai báo blockingOrThrow và StorageUnavailableException. Với fromCallable, lỗi ném khi subscribe được chuyển thành onError rồi đi qua onErrorMap.

**Lưu ý WebFlux:** từ “lazy” không có nghĩa “non-blocking”. Nếu blockingOrThrow thực sự chặn thread bằng JDBC hoặc file I/O đồng bộ, hãy sử dụng driver/API non-blocking khi thích hợp, hoặc cô lập blocking trên Scheduler phù hợp (ví dụ boundedElastic) có giới hạn tài nguyên.

## 9. Spring WebFlux: từ domain exception sang HTTP response

**Domain exception không tự biến thành HTTP status.** Để client nhận phản hồi 503 khi catalog không sẵn sàng, cần một **HTTP boundary** xử lý CatalogUnavailableException. Có thể dùng @RestControllerAdvice, @ExceptionHandler, ResponseStatusException hoặc cơ chế ErrorResponse/ProblemDetail.

### 9.1. Service chỉ hiểu nghiệp vụ

~~~java
@Service
public class CatalogService {
    private final CatalogRepository repository;

    public CatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    public Mono<Product> findProduct(String id) {
        return repository.findById(id)
            .onErrorMap(DataAccessResourceFailureException.class,
                cause -> new CatalogUnavailableException(
                    "Catalog temporarily unavailable", cause))
            .switchIfEmpty(Mono.error(new ProductNotFoundException(id)));
    }
}
~~~

Đây là **mã minh họa trong project Spring Boot WebFlux**, chưa thể chạy độc lập vì còn cần Product, CatalogRepository, hai domain exception và imports. Điểm quan trọng là **phân biệt lỗi truy cập database với kết quả rỗng**:

- Có Product thì phát Product.
- Không tìm thấy và repository hoàn tất rỗng thì switchIfEmpty phát ProductNotFoundException.
- Lỗi DataAccessResourceFailureException thì onErrorMap phát CatalogUnavailableException.
- Lỗi khác không khớp thì truyền tiếp nguyên loại, trừ khi operator khác xử lý.

### 9.2. Controller advice chọn status và body

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DomainErrorAdvice {
    @ExceptionHandler(CatalogUnavailableException.class)
    public ResponseEntity<ProblemDetail> unavailable(
            CatalogUnavailableException error) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog temporarily unavailable");
        problem.setTitle("Catalog is unavailable");

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }
}
~~~

Class này hoạt động trong một Spring WebFlux project khi CatalogUnavailableException có mặt và được import, component scanning tìm thấy advice. ProblemDetail cho phép tạo response body chuẩn hóa; ResponseEntity đặt status 503 một cách tường minh. Cần một handler riêng cho ProductNotFoundException nếu API yêu cầu HTTP 404.

Không trả nguyên exception kỹ thuật hay stack trace ra JSON. Có thể bổ sung **error code công khai** và correlation ID khi policy cho phép, giữ cause trong log nội bộ.

### 9.3. ResponseStatusException ở controller boundary

~~~java
Mono<Product> response = catalogService.findProduct(id)
    .onErrorMap(CatalogUnavailableException.class,
        cause -> new ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog temporarily unavailable", cause));
~~~

Đây là đoạn minh họa controller có service và type liên quan. ResponseStatusException gắn lỗi với HTTP status, nhưng service/domain core không nên phụ thuộc vào HTTP nếu nó còn phục vụ message consumer, batch hoặc CLI. Dùng advice là lựa chọn thuận tiện khi cần chính sách lỗi tập trung.

**Trường hợp Flux streaming:** nếu WebFlux đã ghi HTTP headers và một số phần response body, sau đó Flux mới phát onError, không phải lúc nào framework có thể thay response đã commit thành 503 với body ProblemDetail đầy đủ. onErrorMap không quay ngược bytes đã gửi. Với streaming, cần thiết kế protocol/contract lỗi và điểm commit phù hợp.

## 10. Cách phân loại lỗi khi dùng WebClient

Khi gọi API bên ngoài, các lỗi không nên bị đánh đồng:

| Loại | Ví dụ | Điều nên xem xét |
| --- | --- | --- |
| **WebClientRequestException** | Không thể tạo kết nối, vấn đề network | Có thể cần PartnerUnavailableException, chú ý nguyên nhân |
| **WebClientResponseException** | Server trả HTTP status lỗi qua retrieve mặc định | Kiểm tra status: 404, 401, 403, 429, 5xx có ý nghĩa khác nhau |
| **TimeoutException** | Timeout phát ra từ operator hoặc tầng khác | Phân loại dựa trên vị trí timeout và loại lỗi thực tế |
| **Domain exception đã được tạo** | PartnerRejectedException, OrderConflictException | Không bọc lại thành “unavailable” nếu đã có nghĩa đúng |

Ví dụ một adapter:

~~~java
Mono<PartnerPayload> payload = webClient.get()
    .uri("/partner/{id}", partnerId)
    .retrieve()
    .bodyToMono(PartnerPayload.class)
    .onErrorMap(WebClientRequestException.class,
        cause -> new PartnerUnavailableException(
            "Cannot reach partner", cause));
~~~

Đây là đoạn minh họa, cần định nghĩa WebClient, PartnerPayload, PartnerUnavailableException và partnerId. Đối với lỗi trả về HTTP 404, 429 hay 5xx, có thể phân loại qua **onStatus** khi retrieve hoặc predicate trên WebClientResponseException, dựa vào **status code**. Không tự coi mọi 4xx/5xx đều là lỗi tạm thời có thể retry; 401/403 thường là vấn đề quyền, 429 có thể liên quan quota và Retry-After, 404 có thể là resource không tồn tại theo hợp đồng.

## 11. Thứ tự operator ảnh hưởng kết quả

Xét hai chuỗi sau, giả sử source là Mono<String> phát IOException:

~~~java
Mono<String> first = source
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException("Storage down", e))
    .onErrorResume(CatalogUnavailableException.class,
        e -> Mono.just("cached"));
~~~

Ở đây onErrorMap đổi lỗi sang CatalogUnavailableException, rồi onErrorResume **khớp lỗi mới** và phát "cached".

~~~java
Mono<String> second = source
    .onErrorResume(CatalogUnavailableException.class,
        e -> Mono.just("cached"))
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException("Storage down", e));
~~~

Ở đây onErrorResume nhận IOException trước khi được map, nên **không khớp**, onErrorMap ở phía sau mới đổi loại; kết quả vẫn là onError(CatalogUnavailableException), không có cached.

Hai đoạn cần các class/application variables tương ứng nên là ví dụ minh họa. Thứ tự quan trọng tương tự với retryWhen:

~~~text
source -> onErrorMap(IOException -> DomainException) -> retryWhen(filter IOException)
                         |
                 retry thấy DomainException,
                 filter IOException có thể không khớp
~~~

Nếu đặt retry trước mapping, phải lưu ý **retry exhaustion**: RetrySpec có thể báo lỗi wrapper khi cạn retry, khiến onErrorMap(IOException.class, ...) sau đó không còn khớp lỗi gốc. Thiết kế chính sách retry phải test cả nguồn lỗi ngay, retry thành công, retry hết số lần và lỗi không được retry; đôi khi cần cấu hình cách phát lỗi cuối.

Retry tạo **subscription mới** đến phần nguồn được retry, có thể làm lại network call hoặc side effect. Không retry thao tác thanh toán, gửi email hoặc ghi dữ liệu một cách tự động nếu chưa có cơ chế idempotency và deadline.

## 12. Phục hồi lỗi riêng cho từng phần tử

Với Flux nhiều phần tử, đặt một handler lỗi **bên ngoài cả pipeline** và trả fallback không có nghĩa tiếp tục tất cả input phía sau lỗi.

~~~java
Flux<String> result = Flux.just("ok", "bad", "later")
    .concatMap(value -> callOne(value))
    .onErrorResume(CatalogUnavailableException.class,
        e -> Flux.just("fallback"));
~~~

Nếu callOne("bad") phát lỗi terminal, nguồn bên ngoài có thể dừng trước khi xử lý "later". Nếu nghiệp vụ cần **bỏ qua/phục hồi mỗi bản ghi** nhưng vẫn tiếp tục những bản ghi sau, đặt recovery tại inner Publisher:

~~~java
Flux<String> result = Flux.just("ok", "bad", "later")
    .concatMap(value ->
        callOne(value).onErrorResume(
            CatalogUnavailableException.class,
            e -> Mono.just("failed:" + value)));
~~~

Hai ví dụ là **đoạn minh họa**, callOne(String) phải là phương thức trả Mono<String>. Ở mẫu thứ hai, lỗi từng inner có thể được phục hồi thành giá trị và concatMap còn cơ hội xử lý "later". Nếu inner phát lỗi khác không được bắt, toàn luồng vẫn có thể kết thúc.

**onErrorMap chỉ đổi lỗi**; việc “tiếp tục từng phần tử” là một quyết định thiết kế khác, không thể giải quyết chỉ bằng đổi Throwable terminal.

## 13. Phân loại lỗi nghiệp vụ để chọn HTTP status

Một ví dụ bảng hợp đồng cho API catalog/order:

| Tình huống | Domain exception | HTTP status gợi ý | Giải thích |
| --- | --- | --- | --- |
| Không có product theo ID | ProductNotFoundException | 404 | Resource không tồn tại |
| Không thể truy cập kho dữ liệu | CatalogUnavailableException | 503 | Dependency tạm không sẵn sàng |
| Request không hợp lệ | InvalidQueryException | 400 | Client cần sửa dữ liệu |
| Không đủ quyền | PermissionDeniedException | 403 | Không được phép |
| Trạng thái order xung đột | OrderStateConflictException | 409 | Quy tắc nghiệp vụ ngăn thao tác |
| Bug/exception không dự đoán | Unexpected server error | 500 | Không được che thành 404 hoặc 400 |

Đây là bảng **định hướng**, cần căn cứ hợp đồng API cụ thể. Một exception nghiệp vụ không nhất thiết có tên class trùng với mã lỗi công khai; có thể dùng code ổn định như CATALOG_UNAVAILABLE hoặc PRODUCT_NOT_FOUND.

Không nên map **IOException của database** thành ProductNotFoundException. Khi không thể truy cập dữ liệu, service **không biết** product có tồn tại hay không.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ onErrorMap trả dữ liệu dự phòng | Stream vẫn lỗi | Dùng onErrorResume hoặc onErrorReturn |
| Map tất cả Throwable thành “unavailable” | Che bug, lỗi quyền, lỗi validation | Chọn Class/predicate đủ hẹp |
| Bỏ cause của technical exception | Mất dấu nguyên nhân gốc | new DomainException(message, cause) |
| Trả toàn bộ cause/stack trace lên HTTP | Có thể lộ SQL, token, hostname | Trả public code/detail an toàn; log nội bộ |
| Nghĩ Mono.empty là lỗi để map | Mapper không chạy | Dùng switchIfEmpty khi cần not found |
| Mong Flux chạy tiếp sau onErrorMap | Lỗi vẫn là terminal | Phục hồi inner Publisher khi cần per-item |
| Map domain exception lần hai thành lỗi khác | Mất phân loại chính xác | Map tại ranh giới technical, dùng filter |
| Đổi database timeout thành 404 | Client tưởng dữ liệu không có | Phân biệt missing/unavailable |
| Đặt onErrorResume trước onErrorMap rồi mong bắt type mới | Handler không khớp | Sắp thứ tự operator theo luồng tín hiệu |
| Retry sau mapping với filter chỉ nhận technical error | Filter có thể bỏ lỡ domain error | Thiết kế thứ tự và xử lý retry exhausted |
| Gọi hàm throw trước Mono.just | Lỗi xảy ra trước pipeline | Dùng fromCallable hoặc defer đúng chỗ |
| Mapper trả null hoặc ném lỗi khác ngoài ý muốn | Mất semantics dự kiến | Trả Throwable hợp lệ và có test |
| Log cùng một lỗi ở quá nhiều layer | Log trùng và khó điều tra | Chọn tầng log chính, giữ correlation ID |
| Dùng onErrorMap để chọn 503 mà không cấu hình HTTP handler | Không có ánh xạ status mong muốn | Dùng @ExceptionHandler hoặc ResponseStatusException |

Tránh biến những lỗi fatal hoặc lỗi do hỏng trạng thái chương trình thành lỗi nghiệp vụ có thể bỏ qua. Mục tiêu là giữ **phân loại lỗi thực tế**, không phải che toàn bộ sự cố dưới một thông điệp chung.

## 15. Kiểm thử đúng cả tín hiệu và nguyên nhân

Các nhánh nên được kiểm chứng:

1. Nguồn thành công: không gọi mapper, giữ nguyên giá trị.
2. Nguồn lỗi đúng loại: downstream nhận đúng domain exception.
3. Chuỗi cause: getCause() trỏ tới Throwable gốc.
4. Lỗi không khớp: giữ nguyên exception gốc.
5. Mono.empty: mapper không chạy; nếu có switchIfEmpty thì xử lý rỗng riêng.
6. Flux phát một số phần tử rồi lỗi: các giá trị trước lỗi vẫn đến downstream, sau đó kết thúc.
7. Recovery và retry: kiểm tra từng thứ tự operator và retry exhaustion.
8. HTTP boundary: xác nhận status/body đúng và không lộ dữ liệu hạ tầng.

Với **reactor-test**, có thể dùng StepVerifier:

~~~java
IOException original = new IOException("disconnected");

Mono<String> mapped = Mono.<String>error(original)
    .onErrorMap(IOException.class,
        e -> new CatalogUnavailableException(
            "Catalog unavailable", e));

StepVerifier.create(mapped)
    .expectErrorMatches(error ->
        error instanceof CatalogUnavailableException
        && error.getCause() == original
        && "Catalog unavailable".equals(error.getMessage()))
    .verify();
~~~

Đây là **đoạn test minh họa**, cần dependency **io.projectreactor:reactor-test** tương thích với reactor-core, import IOException, Mono, StepVerifier và class CatalogUnavailableException; chạy trong JUnit test method. Không phải class độc lập. Với WebFlux, WebTestClient giúp kiểm tra mapping từ domain exception sang HTTP 404/503 và ProblemDetail ở controller/advice.

## 16. Câu hỏi tự kiểm tra

**1.** Một Mono phát giá trị rồi complete; onErrorMap có gọi mapper không?

**Không.** Mapper chỉ hoạt động khi có tín hiệu onError phù hợp.

**2.** Repository trả Mono.empty() cho ID không tồn tại. Dùng onErrorMap(IOException.class, ...) để trả 404 được không?

**Không.** Empty là complete rỗng, không phải onError. Dùng switchIfEmpty(Mono.error(...)) và ánh xạ domain NotFound sang 404 tại HTTP boundary.

**3.** Khi IOException được map thành CatalogUnavailableException, original exception nên nằm ở đâu?

Trong **cause** của exception mới, để nội bộ còn khả năng chẩn đoán.

**4.** onErrorMap có biến lỗi thành giá trị "cached" không?

**Không.** Dùng onErrorResume với Mono.just("cached") khi fallback là chính sách hợp lệ.

**5.** Một Flux phát A, B rồi lỗi. onErrorMap có tự phát tiếp C của nguồn cũ không?

**Không.** Lỗi terminal kết thúc subscription đó. Nếu cần xử lý từng phần tử độc lập, thiết kế recovery trong inner Publisher.

**6.** Mapping theo IOException.class có làm thay đổi IllegalArgumentException không?

**Không**, trừ khi lỗi thực tế là subclass tương thích của kiểu đã chỉ định (trường hợp thông thường của IllegalArgumentException thì không).

**7.** Tạo CatalogUnavailableException trong service có tự động làm HTTP trả 503 không?

**Không.** Cần ánh xạ tại HTTP boundary bằng advice, ResponseStatusException hoặc cơ chế tương đương.

**8.** Vì sao không nên map mọi Throwable thành PartnerUnavailableException?

Vì có thể che cả bug, lỗi xác thực, validation và lỗi domain đã có nghĩa chính xác.

**9.** Khi có retryWhen sau onErrorMap, điều gì có thể xảy ra với filter chỉ nhận IOException?

Filter có thể nhận domain exception mới nên không khớp. Nếu đặt retry trước mapping, cũng phải xử lý wrapper của exhausted retries.

**10.** Vì sao không nên trả message/stack trace driver qua response?

Vì có nguy cơ lộ thông tin nội bộ/nhạy cảm. API chỉ nên trả mã lỗi và mô tả an toàn, giữ chẩn đoán ở hệ thống log được bảo vệ.

## 17. Tài liệu tham khảo

- [Project Reactor 3.6.17: Mono.onErrorMap](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html) — ba overload và ý nghĩa biến đổi tín hiệu lỗi.
- [Project Reactor 3.6.17: Flux API](https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Flux.html) — onErrorMap trên Flux.
- [Project Reactor Reference Guide: Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html) — so sánh error mapping, fallback và retry.
- [Spring WebFlux exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html) — @ExceptionHandler và @ControllerAdvice.
- [Spring WebFlux error responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html) — ProblemDetail và ErrorResponse.
- [Spring ResponseStatusException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ResponseStatusException.html) — exception mang HTTP status.

**Ghi nhớ:** **onErrorMap đồng bộ thay một tín hiệu onError chứa lỗi kỹ thuật bằng onError chứa lỗi nghiệp vụ**, giúp service có hợp đồng rõ ràng và ít phụ thuộc hạ tầng. Nó **không tạo dữ liệu fallback, không tự retry, không tiếp tục nguồn sau lỗi và không tự quyết định HTTP status**. Chọn lọc lỗi đúng phạm vi, giữ cause, phân biệt lỗi nguồn rỗng với lỗi kỹ thuật, kiểm tra thứ tự operator và dùng HTTP handler riêng để trả thông tin an toàn cho client.