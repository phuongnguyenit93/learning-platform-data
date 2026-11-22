# `ReactiveAdapterRegistry` và các kiểu reactive được Spring hỗ trợ

## 1. Vấn đề mà registry giải quyết

Trong ứng dụng Spring WebFlux, một controller hoặc một API client có thể trả về dữ liệu bất đồng bộ từ nhiều thư viện khác nhau. Project Reactor cung cấp `Mono<T>` và `Flux<T>`, nhưng hệ sinh thái Java còn có `CompletableFuture<T>`, JDK `Flow.Publisher<T>`, Reactive Streams `Publisher<T>`, RxJava và Kotlin Coroutines.

Nếu mỗi thành phần Spring phải tự viết nhánh xử lý cho từng thư viện, code sẽ phức tạp và khó mở rộng. **`ReactiveAdapterRegistry`** trong package `org.springframework.core` giải quyết việc đó bằng cách lưu các adapter chuyển đổi giữa một kiểu async/reactive cụ thể và chuẩn Reactive Streams `Publisher`.

Spring có thể dùng registry để nhận biết kiểu reactive mà một API trả về, chuyển kiểu đó sang `Publisher` để xử lý trong pipeline nội bộ, rồi khi cần có thể chuyển ngược lại kiểu gốc.

```text
Mono<T> ----------------------┐
Flux<T> ----------------------┤
CompletableFuture<T> ---------┤
JDK Flow.Publisher<T> --------┤
RxJava type ------------------┼── ReactiveAdapterRegistry
Kotlin Deferred<T> -----------┤             |
Mutiny Uni / Multi -----------┘             |
                                            v
                                 Reactive Streams Publisher<T>
                                            |
                              Spring WebFlux / Spring APIs
```

Registry là **bộ tra cứu và chuyển đổi kiểu**, không phải scheduler, thread pool, event loop, HTTP server hay bộ xử lý dữ liệu. Nó không tự làm một hàm blocking trở thành non-blocking, không tạo thread và không tự khởi chạy một `Publisher` chỉ vì adapter tồn tại.

## 2. Các khái niệm và ba lớp API

Ba lớp thường làm việc cùng nhau:

| Thành phần | Vai trò |
|---|---|
| `ReactiveAdapterRegistry` | Đăng ký, tìm kiếm và quản lý adapter theo kiểu Java |
| `ReactiveAdapter` | Thực hiện chuyển đổi từ kiểu cụ thể sang `Publisher` và ngược lại |
| `ReactiveTypeDescriptor` | Mô tả số lượng giá trị, khả năng rỗng và việc nguồn có deferred hay không |

### 2.1. `ReactiveAdapterRegistry`

API quan trọng:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

ReactiveAdapter adapter = registry.getAdapter(Mono.class);
ReactiveAdapter bySource =
        registry.getAdapter(null, someAsyncObject);

boolean hasAdapters = registry.hasAdapters();
ReactiveAdapterRegistry shared =
        ReactiveAdapterRegistry.getSharedInstance();
```

- `new ReactiveAdapterRegistry()` tạo registry và tự đăng ký những adapter mặc định có thể dùng trên classpath hiện tại.
- `getAdapter(Class<?>)` tìm adapter theo kiểu reactive. Nếu không có adapter phù hợp, kết quả là `null`.
- `getAdapter(Class<?>, Object)` cho phép cung cấp kiểu hoặc instance nguồn thực tế để tra cứu. Khi truyền `source`, Spring có thể dùng kiểu runtime của đối tượng.
- `hasAdapters()` cho biết registry có adapter hay không.
- `getSharedInstance()` trả về registry mặc định dùng chung, được khởi tạo lười khi cần.

Javadoc khuyến nghị truyền một registry đã cấu hình và có vòng đời dài khi cần tùy chỉnh. `getSharedInstance()` phù hợp như một fallback cho nơi cần registry mặc định; không nên giả định việc sửa một registry tự tạo sẽ tự động thay đổi mọi registry khác trong ứng dụng.

### 2.2. `ReactiveAdapter`

Một adapter cung cấp hai chiều chuyển đổi:

```text
Kiểu async/reactive cụ thể
          |
          | adapter.toPublisher(source)
          v
Reactive Streams Publisher
          |
          | adapter.fromPublisher(publisher)
          v
Kiểu async/reactive cụ thể
```

Các phương thức thường dùng:

```java
Publisher<?> publisher = adapter.toPublisher(source);

Object originalStyle = adapter.fromPublisher(publisher);

ReactiveTypeDescriptor descriptor = adapter.getDescriptor();

Class<?> type = adapter.getReactiveType();
boolean multiValue = adapter.isMultiValue();
boolean noValue = adapter.isNoValue();
boolean supportsEmpty = adapter.supportsEmpty();
```

- `toPublisher(source)` chuyển instance của kiểu đã đăng ký sang Reactive Streams `Publisher`.
- `fromPublisher(publisher)` chuyển một Publisher sang kiểu reactive đích của adapter.
- `getDescriptor()` trả về mô tả kiểu.
- `getReactiveType()` trả về class được adapter hỗ trợ.
- `isMultiValue()`, `isNoValue()` và `supportsEmpty()` là các shortcut đọc thuộc tính trong descriptor.

Không được coi `fromPublisher` là phép chuyển đổi luôn giữ được mọi đặc tính của nguồn. Ví dụ, nếu kiểu đích chỉ chứa tối đa một giá trị thì việc chuyển một `Flux` có nhiều phần tử phải có chính sách rõ ràng ở adapter; một adapter single-value có thể chỉ nhận một giá trị đầu tiên hoặc từ chối cách dùng không phù hợp. Hãy giữ đúng semantics của kiểu nguồn và kiểu đích.

### 2.3. `ReactiveTypeDescriptor`

Descriptor mô tả hợp đồng phát dữ liệu của kiểu reactive. Các factory method quan trọng:

| Factory | Ý nghĩa | Ví dụ phù hợp |
|---|---|---|
| `multiValue(type, emptySupplier)` | Có thể phát 0..N giá trị | Kiểu stream như `Flux<T>` |
| `singleOptionalValue(type, emptySupplier)` | Có thể phát 0..1 giá trị | Kiểu promise có thể hoàn tất rỗng |
| `singleRequiredValue(type)` | Phải phát đúng một giá trị để hoàn tất | Kiểu single bắt buộc có kết quả |
| `noValue(type, emptySupplier)` | Chỉ có complete/error, không phát giá trị | Kiểu completion-only |
| `nonDeferredAsyncValue(type, emptySupplier)` | Kiểu async single-value được kích hoạt trước/độc lập với subscription | `CompletableFuture<T>` |

Các thuộc tính:

- `isMultiValue()`: kiểu có thể phát nhiều hơn một giá trị, phù hợp với cách biểu diễn như `Flux`.
- `isNoValue()`: kiểu không phát giá trị, chỉ có complete/error.
- `supportsEmpty()`: kiểu có thể hoàn tất mà không phát phần tử.
- `isDeferred()`: cho biết công việc có được trì hoãn đến khi consumer subscribe/đăng ký hay đã bắt đầu độc lập.
- `getEmptyValue()`: tạo instance biểu diễn trạng thái rỗng nếu descriptor hỗ trợ empty.

**Chọn descriptor đúng rất quan trọng.** Nếu khai báo một kiểu có thể rỗng thành `singleRequiredValue`, adapter sẽ mô tả sai hợp đồng. Nếu một `CompletableFuture` được tạo và bắt đầu chạy ngay, không mô tả nó như nguồn deferred chỉ vì ta chuyển nó sang `Publisher` sau đó.

## 3. Những kiểu reactive mặc định được hỗ trợ

Các adapter mặc định được đăng ký **phụ thuộc classpath và phiên bản Spring Framework**. Với Spring Framework 6.1.x, Javadoc của `ReactiveAdapterRegistry` mô tả các nhóm sau:

| Thư viện / kiểu | Nhóm adapter | Điều kiện hoặc ghi chú |
|---|---|---|
| Project Reactor | `Mono`, `Flux` và các adapter liên quan | Reactor có trên classpath |
| `CompletableFuture` | Single-value async | Được đăng ký cùng tích hợp Reactor |
| JDK `Flow.Publisher` | Adapter giữa JDK Flow và Reactive Streams | Có tích hợp Reactor; nếu không có Reactor, Spring có bridge đơn giản cho `Flow.Publisher` |
| RxJava 3 | Các kiểu reactive RxJava 3 được hỗ trợ | RxJava 3 có trên classpath |
| Kotlin Coroutines `Deferred` | Single-value async, bridge qua Reactor | Có các dependency coroutine/reactor tương ứng |
| SmallRye Mutiny | Mutiny 1.x và 2.x trong Spring 6.1.x | Có Mutiny trên classpath |

Spring 5.3.11 trở đi đã deprecate hỗ trợ RxJava 1.x và 2.x để ưu tiên RxJava 3. Khi bắt đầu dự án mới, hãy chọn RxJava 3 nếu cần tích hợp RxJava.

### 3.1. Phân biệt JDK `Flow.Publisher` và Kotlin `Flow`

Hai tên rất dễ gây nhầm:

- `java.util.concurrent.Flow.Publisher<T>` là interface của JDK, xuất hiện từ Java 9 và có hợp đồng publisher/subscriber riêng trong package `java.util.concurrent.Flow`.
- `kotlinx.coroutines.flow.Flow<T>` là kiểu stream của Kotlin Coroutines. Nó có API `collect` và cơ chế suspension/backpressure dựa trên coroutine.

Javadoc `ReactiveAdapterRegistry` 6.1.x liệt kê rõ JDK `Flow.Publisher` bridge. Spring cũng hỗ trợ Kotlin Coroutines `Flow` trong các tích hợp Kotlin/WebFlux khi có dependency cần thiết, nhưng đó là **Kotlin coroutine integration theo phiên bản và thành phần Spring**; không đồng nhất nó với JDK `Flow.Publisher`, và không mặc định rằng mọi API Java đều nhận hai kiểu này như nhau.

Với Kotlin Coroutines, các dependency thường cần có:

```kotlin
dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-reactor")
}
```

Spring hỗ trợ `Deferred` và `Flow` trong controller WebFlux khi cấu hình coroutine phù hợp. Việc chọn phiên bản coroutine cần tương thích với phiên bản Spring/Kotlin của dự án.

### 3.2. `CompletableFuture` không có backpressure như `Flux`

`CompletableFuture<T>` biểu diễn một kết quả async đơn lẻ. Nó không phải stream nhiều phần tử và không có giao thức `request(n)` như Reactive Streams. Adapter giúp Spring làm việc với nó qua abstraction Publisher, nhưng **không thể tự tạo backpressure cho một future đã bắt đầu**.

Tương tự, các thư viện reactive khác nhau có semantics riêng. RxJava `Flowable` hỗ trợ backpressure, trong khi `Observable` không có giao thức demand tương tự. Việc chuyển đổi phải tuân theo cách adapter/library xử lý chênh lệch đó; không nên giả định mọi kiểu sau khi adapter đều có đặc tính giống hệt `Flux`.

## 4. Registry được Spring dùng ở đâu?

`ReactiveAdapterRegistry` là hạ tầng dùng chung trong nhiều API Spring. Một số vị trí tiêu biểu:

### 4.1. WebFlux annotated controllers

Spring WebFlux có thể nhận kiểu reactive từ controller method và chuyển chúng vào cơ chế xử lý response. Ví dụ:

```java
@RestController
class PersonController {

    @GetMapping("/person")
    Mono<Person> one() {
        return Mono.just(new Person(1, "An"));
    }

    @GetMapping(value = "/people", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Person> many() {
        return Flux.just(
                new Person(1, "An"),
                new Person(2, "Binh")
        );
    }
}
```

Các kiểu Reactor được WebFlux hỗ trợ trực tiếp. Với kiểu reactive từ thư viện khác, registry cho phép framework tìm adapter để chuẩn hóa cách tiêu thụ Publisher. Sau đó `HttpMessageWriter`/codec chịu trách nhiệm serialize dữ liệu thành HTTP response.

Adapter **không serialize JSON** và cũng không quyết định media type. Nó chỉ giúp framework nhận biết và chuyển kiểu async/reactive về abstraction phù hợp.

### 4.2. WebClient request body

`WebClient` có API nhận một producer có thể là Publisher hoặc kiểu async khác được registry hỗ trợ. Ví dụ `BodyInserters.fromProducer(...)` có thể thích nghi producer sang Publisher trước khi ghi request body.

```java
Mono<Void> result = webClient.post()
        .uri("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .body(personPublisher, Person.class)
        .retrieve()
        .bodyToMono(Void.class);
```

Với kiểu producer không phải Publisher nhưng có adapter, API body phù hợp có thể sử dụng `ReactiveAdapterRegistry` để chuyển đổi. Nếu đã có một object cụ thể trong bộ nhớ và không phải async source, dùng `bodyValue(object)` sẽ rõ ý định hơn.

### 4.3. Các hạ tầng Spring khác

Registry còn được sử dụng bởi những thành phần xử lý method return value, messaging và các integration reactive. Khi một framework component nhận một kiểu async chưa biết, nó có thể hỏi registry xem có adapter tương ứng không.

Điều đó giúp nhiều API Spring dùng chung một cơ chế nhận biết kiểu reactive thay vì viết lại bộ chuyển đổi cho từng thư viện.

## 5. Ví dụ kiểm tra các adapter mặc định

Chương trình Java 17+ sau tạo registry mặc định và kiểm tra một số kiểu. Nó cần `spring-core` và `reactor-core` trên classpath.

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Flow;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.core.ReactiveAdapterRegistry;

public final class Main {
    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        System.out.println(
                "Mono adapter: "
                        + (registry.getAdapter(Mono.class) != null)
        );

        System.out.println(
                "Flux adapter: "
                        + (registry.getAdapter(Flux.class) != null)
        );

        System.out.println(
                "CompletableFuture adapter: "
                        + (registry.getAdapter(CompletableFuture.class) != null)
        );

        System.out.println(
                "JDK Flow.Publisher adapter: "
                        + (registry.getAdapter(Flow.Publisher.class) != null)
        );
    }
}
```

Cấu trúc Maven:

```text
reactive-adapter-defaults/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-adapter-defaults</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.1.11</version>
        </dependency>
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
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Từ thư mục dự án, chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Stdout kỳ vọng với đúng hai dependency trên:

```text
Mono adapter: true
Flux adapter: true
CompletableFuture adapter: true
JDK Flow.Publisher adapter: true
```

Kết quả này kiểm tra classpath đang có Reactor nên registry đăng ký các adapter tương ứng. Nếu bỏ Reactor khỏi classpath, không được mặc định mong đợi cùng kết quả cho mọi kiểu; Javadoc Spring 6.1.x mô tả bridge JDK `Flow.Publisher` đơn giản khi Reactor không hiện diện.

## 6. Tự đăng ký kiểu reactive tùy chỉnh

Nếu thư viện nội bộ có một kiểu async riêng, Spring không tự hiểu kiểu đó chỉ vì nó chứa `CompletableFuture` hoặc một Publisher bên trong. Ta có thể đăng ký adapter bằng `registerReactiveType(...)`.

Giả sử có kiểu `AsyncValue<T>` của ứng dụng, bọc một `CompletableFuture<T>`:

```java
final class AsyncValue<T> {
    private final CompletableFuture<T> future;

    private AsyncValue(CompletableFuture<T> future) {
        this.future = future;
    }

    static <T> AsyncValue<T> from(CompletableFuture<T> future) {
        return new AsyncValue<>(future);
    }

    static AsyncValue<?> empty() {
        return new AsyncValue<>(
                CompletableFuture.completedFuture(null)
        );
    }

    CompletableFuture<T> future() {
        return future;
    }
}
```

Vì future bắt đầu độc lập với việc subscriber gọi `request`, descriptor thích hợp là `nonDeferredAsyncValue`. Adapter hai chiều:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();

registry.registerReactiveType(
        ReactiveTypeDescriptor.nonDeferredAsyncValue(
                AsyncValue.class,
                AsyncValue::empty
        ),
        source -> Mono.fromCompletionStage(
                ((AsyncValue<?>) source).future()
        ),
        publisher -> AsyncValue.from(
                Mono.from(publisher).toFuture()
        )
);
```

Giải thích:

1. `ReactiveTypeDescriptor.nonDeferredAsyncValue(...)` khai báo `AsyncValue` là kiểu async đơn giá trị, có thể rỗng và không deferred.
2. Hàm `toAdapter` nhận object `AsyncValue`, lấy `CompletableFuture` và chuyển thành `Mono` bằng `Mono.fromCompletionStage`.
3. Hàm `fromAdapter` nhận một Publisher và chuyển về `AsyncValue` bằng `Mono.from(publisher).toFuture()`.
4. `Mono.from(publisher)` phù hợp với descriptor single-value: lấy tối đa một giá trị hoặc hoàn tất rỗng.
5. Nếu future hoàn tất exceptional, lỗi được giữ như lỗi async; nếu future hoàn tất `null`, nó biểu diễn trạng thái không có giá trị theo cách `Mono` xử lý completion stage.

Đây là ví dụ adapter cho **kiểu single-value**. Không dùng cùng descriptor nếu `AsyncValue` thực tế có thể phát nhiều giá trị.

### 6.1. Chương trình hoàn chỉnh cho adapter tùy chỉnh

```java
package demo;

import java.util.concurrent.CompletableFuture;

import org.springframework.core.ReactiveAdapter;
import org.springframework.core.ReactiveAdapterRegistry;
import org.springframework.core.ReactiveTypeDescriptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class Main {

    static final class AsyncValue<T> {
        private final CompletableFuture<T> future;

        private AsyncValue(CompletableFuture<T> future) {
            this.future = future;
        }

        static <T> AsyncValue<T> from(CompletableFuture<T> future) {
            return new AsyncValue<>(future);
        }

        static AsyncValue<?> empty() {
            return new AsyncValue<>(
                    CompletableFuture.completedFuture(null)
            );
        }

        CompletableFuture<T> future() {
            return future;
        }
    }

    public static void main(String[] args) {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        registry.registerReactiveType(
                ReactiveTypeDescriptor.nonDeferredAsyncValue(
                        AsyncValue.class,
                        AsyncValue::empty
                ),
                source -> Mono.fromCompletionStage(
                        ((AsyncValue<?>) source).future()
                ),
                publisher -> AsyncValue.from(
                        Mono.from(publisher).toFuture()
                )
        );

        ReactiveAdapter adapter =
                registry.getAdapter(AsyncValue.class);

        System.out.println("Custom adapter: " + (adapter != null));

        AsyncValue<String> input = AsyncValue.from(
                CompletableFuture.completedFuture("hello")
        );

        Object value = Mono.from(adapter.toPublisher(input)).block();
        System.out.println("toPublisher: " + value);

        AsyncValue<?> output = (AsyncValue<?>) adapter.fromPublisher(
                Flux.just("world")
        );

        System.out.println("fromPublisher: " + output.future().join());
    }
}
```

Đặt code trong cùng file `src/main/java/demo/Main.java` của dự án Maven:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-adapter-custom</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.1.11</version>
        </dependency>
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
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy:

```bash
mvn -q compile exec:java
```

Stdout:

```text
Custom adapter: true
toPublisher: hello
fromPublisher: world
```

`block()` và `join()` trong chương trình này chỉ phục vụ việc in kết quả trong console demo. Không gọi chúng trong controller WebFlux hoặc trong một reactive pipeline đang xử lý request; hãy trả Publisher cho framework tiêu thụ.

## 7. `registerReactiveType` và `registerReactiveTypeOverride`

Hai phương thức đăng ký khác nhau ở thứ tự ưu tiên:

| Phương thức | Hành vi |
|---|---|
| `registerReactiveType(...)` | Đăng ký adapter sau các adapter hiện có; phù hợp khi bổ sung một kiểu mới |
| `registerReactiveTypeOverride(...)` | Đăng ký adapter ở đầu danh sách để override adapter hiện có cho kiểu tương ứng |

Ví dụ:

```java
registry.registerReactiveType(
        descriptor,
        source -> toPublisher(source),
        publisher -> fromPublisher(publisher)
);
```

Nếu cần thay đổi cách một kiểu đã có được chuyển đổi, có thể dùng:

```java
registry.registerReactiveTypeOverride(
        descriptor,
        source -> customToPublisher(source),
        publisher -> customFromPublisher(publisher)
);
```

Override cần thận trọng. Các adapter đã đăng ký cho kiểu cụ thể vẫn có thể được xét trước một adapter mới chỉ khớp qua quan hệ assignability. Nếu muốn thay đổi mọi kiểu con, cần đăng ký adapter cho từng kiểu cụ thể liên quan thay vì chỉ trông chờ vào match theo superclass/interface.

Không dùng override để sửa hành vi toàn ứng dụng nếu chưa xác định mọi thành phần đang dùng registry đó.

## 8. Dùng registry tùy chỉnh trong Spring WebFlux

Một registry tự tạo chỉ ảnh hưởng đến code được truyền chính instance đó. Đoạn sau **không tự làm controller của Spring Boot nhận kiểu mới** nếu WebFlux vẫn đang dùng registry mặc định:

```java
ReactiveAdapterRegistry registry = new ReactiveAdapterRegistry();
registry.registerReactiveType(...);
```

Muốn Spring WebFlux dùng adapter tùy chỉnh, registry cần được đưa vào hạ tầng WebFlux xử lý return value. Trong cấu hình Java dựa trên `WebFluxConfigurationSupport`, bean `webFluxAdapterRegistry()` là điểm cấu hình chung được dùng bởi các result handler như `RequestMappingHandlerAdapter`, `ResponseBodyResultHandler` và `ResponseEntityResultHandler`.

Ví dụ về hướng cấu hình:

```java
@Configuration
class CustomWebFluxConfiguration extends WebFluxConfigurationSupport {

    @Override
    @Bean
    public ReactiveAdapterRegistry webFluxAdapterRegistry() {
        ReactiveAdapterRegistry registry =
                new ReactiveAdapterRegistry();

        // Đăng ký adapter custom tại đây.
        registerApplicationAdapters(registry);

        return registry;
    }
}
```

`registerApplicationAdapters` là hàm do ứng dụng định nghĩa; đoạn trên minh họa điểm mở rộng, không phải chương trình độc lập. Nếu ứng dụng dùng Spring Boot auto-configuration hoặc `@EnableWebFlux`, hãy tích hợp theo mô hình cấu hình hiện tại của dự án và bảo đảm result handler thực sự nhận cùng registry đã tùy chỉnh. Tránh khai báo một registry bean riêng không được WebFlux sử dụng.

Khi thay thế cấu hình WebFlux mặc định, cần hiểu các bean cấu hình khác cũng thuộc `WebFluxConfigurationSupport`; không tạo thêm một cấu hình độc lập làm mất những tùy chỉnh codec, filter, exception handler hoặc content negotiation hiện có.

## 9. Những điều adapter không làm

`ReactiveAdapterRegistry` giúp chuyển kiểu, nhưng không thể xóa các khác biệt nền tảng giữa thư viện:

- **Không tự tạo non-blocking I/O.** Nếu `CompletableFuture` được tạo từ một lời gọi blocking trên event-loop, việc chuyển nó sang Publisher không sửa được thời điểm blocking đã xảy ra.
- **Không tự tạo backpressure.** Một future đơn giá trị không có `request(n)`. Một kiểu Observable không hỗ trợ demand không tự trở thành stream có backpressure đầy đủ sau khi chuyển đổi.
- **Không tự tạo scheduler.** Việc chọn thread/scheduler phụ thuộc nguồn và operator.
- **Không tự xử lý lỗi nghiệp vụ.** Exception trong nguồn vẫn cần được chuyển tiếp hoặc phục hồi bằng các operator như `onErrorResume`.
- **Không serialize body HTTP.** `HttpMessageWriter` và codec đảm nhiệm chuyển object thành JSON, text hoặc byte stream.
- **Không bảo đảm giữ mọi semantics riêng của thư viện.** Cancellation, laziness, empty value, error và concurrency có thể khác nhau giữa các kiểu.
- **Không thay thế kiểu dữ liệu rõ ràng.** Nếu API chỉ cần trả `Mono<T>`/`Flux<T>`, dùng Reactor trực tiếp thường đơn giản và nhất quán hơn việc tạo một abstraction reactive riêng.

Một adapter tốt cần bảo toàn những gì kiểu nguồn có thể biểu đạt, hoặc ghi rõ chính sách khi không thể bảo toàn.

## 10. Lỗi thường gặp khi sử dụng

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| `getAdapter(type)` trả `null` nhưng vẫn gọi method | `NullPointerException` | Kiểm tra adapter tồn tại; bổ sung dependency hoặc đăng ký adapter |
| Nghĩ mọi thư viện đều tự được hỗ trợ | Runtime không tìm được adapter | Kiểm tra Javadoc theo phiên bản và classpath thực tế |
| Nhầm JDK `Flow.Publisher` với Kotlin `Flow` | Chọn sai dependency hoặc adapter | Phân biệt package và integration |
| Khai báo sai descriptor | Spring hiểu sai single/multi/empty/no-value | Chọn đúng factory trong `ReactiveTypeDescriptor` |
| Mô tả `CompletableFuture` là deferred | Sai semantics: future thường đã bắt đầu trước subscribe | Dùng `nonDeferredAsyncValue` |
| Chuyển một Publisher nhiều giá trị sang kiểu single-value | Có thể mất phần tử hoặc lỗi do semantics không tương thích | Dùng descriptor multi-value hoặc thay đổi API đích |
| Chỉ đăng ký vào registry cục bộ | WebFlux vẫn dùng registry khác | Truyền registry vào đúng hạ tầng/result handler |
| Dùng `registerReactiveTypeOverride` không kiểm soát | Thay đổi adapter mà code khác đang dựa vào | Chỉ override khi đã xác định kiểu và phạm vi ảnh hưởng |
| Bọc lệnh blocking trong `CompletableFuture` rồi nghĩ đã reactive | Event loop có thể vẫn bị chặn ở nơi tạo future | Đưa blocking call sang scheduler phù hợp trước khi tạo async result |
| Tạo registry mới mỗi request | Chi phí không cần thiết, cấu hình không nhất quán | Tạo registry lâu dài theo application context |
| Gọi `.block()` trong controller | Chặn thread và phá flow reactive | Trả Publisher cho WebFlux quản lý |
| Nghĩ adapter xử lý JSON | Không có codec tương ứng hoặc response sai định dạng | Cấu hình `HttpMessageReader`/`HttpMessageWriter` riêng nếu cần |

## 11. Cách kiểm tra trong dự án thực tế

Khi một kiểu reactive không hoạt động trong controller hoặc WebClient, kiểm tra theo trình tự:

1. Xác định **class runtime chính xác** của kiểu trả về. Ví dụ `CompletableFuture`, `Single`, `Flowable`, `Deferred` hay một wrapper nội bộ.
2. Xác nhận dependency chứa kiểu đó có trên runtime classpath, không chỉ compile classpath.
3. Xác định phiên bản Spring Framework và đọc Javadoc tương ứng; danh sách adapter mặc định có thể thay đổi theo phiên bản.
4. Lấy đúng registry đang được component Spring sử dụng, không tạo một registry khác rồi chỉ kiểm tra nó.
5. Gọi `getAdapter(returnType)` và xử lý trường hợp trả `null`.
6. Kiểm tra descriptor: multi-value, single-value, empty, no-value và deferred.
7. Kiểm thử cả giá trị bình thường, empty, error, cancellation và trường hợp nhiều giá trị.
8. Với adapter custom, kiểm tra cả hai chiều `toPublisher` và `fromPublisher`.
9. Với WebFlux, kiểm tra response handler và codec có xử lý kiểu phần tử sau khi adaptation hay không.
10. Đo hành vi blocking, concurrency và cancellation của thư viện gốc; registry không thay thế kiểm thử vận hành.

Một đoạn diagnostic đơn giản:

```java
ReactiveAdapter adapter = registry.getAdapter(MyAsyncType.class);

if (adapter == null) {
    throw new IllegalStateException(
            "No reactive adapter for MyAsyncType"
    );
}

ReactiveTypeDescriptor descriptor = adapter.getDescriptor();

System.out.println("multiValue = " + descriptor.isMultiValue());
System.out.println("noValue = " + descriptor.isNoValue());
System.out.println("supportsEmpty = " + descriptor.supportsEmpty());
System.out.println("deferred = " + descriptor.isDeferred());
```

Đây là mã diagnostic cần thay `MyAsyncType` bằng class thực tế. Tránh in toàn bộ object hoặc payload nhạy cảm trong log.

## 12. Bài tập tự kiểm tra

**Câu 1.** `ReactiveAdapterRegistry` có nhiệm vụ chính là gì?

**Đáp án:** Tra cứu và chuyển đổi giữa các kiểu async/reactive cụ thể với Reactive Streams `Publisher`.

**Câu 2.** `getAdapter(UnknownType.class)` có thể trả về gì nếu registry không hỗ trợ kiểu đó?

**Đáp án:** `null`. Caller cần xử lý rõ trường hợp không có adapter.

**Câu 3.** `ReactiveAdapter.toPublisher` và `fromPublisher` khác nhau thế nào?

**Đáp án:** `toPublisher` chuyển kiểu cụ thể thành Publisher; `fromPublisher` chuyển Publisher thành kiểu mà adapter đại diện.

**Câu 4.** Descriptor nào phù hợp với một stream có thể phát 0..N giá trị?

**Đáp án:** `ReactiveTypeDescriptor.multiValue(...)`.

**Câu 5.** Descriptor nào phù hợp với `CompletableFuture` đã bắt đầu chạy độc lập với subscription và có thể hoàn tất không có giá trị?

**Đáp án:** `ReactiveTypeDescriptor.nonDeferredAsyncValue(...)`.

**Câu 6.** JDK `Flow.Publisher` có phải Kotlin `kotlinx.coroutines.flow.Flow` không?

**Đáp án:** Không. Chúng thuộc hai package, hợp đồng và hệ sinh thái khác nhau. Spring có tích hợp cho cả các dạng phù hợp theo phiên bản, nhưng phải cấu hình dependency/API đúng.

**Câu 7.** Nếu đã gọi `registerReactiveType` trên một registry tự tạo, WebFlux có tự nhận kiểu mới không?

**Đáp án:** Không nhất thiết. Registry đó phải được đưa vào hạ tầng WebFlux/result handler đang xử lý controller return value.

**Câu 8.** Adapter có làm một `CompletableFuture` blocking trở thành non-blocking không?

**Đáp án:** Không. Nó chỉ chuyển kiểu. Blocking đã xảy ra trước đó vẫn là blocking; phải chọn execution context phù hợp cho lời gọi gốc.

## 13. Quy tắc áp dụng

- Dùng `ReactiveAdapterRegistry` khi Spring cần làm việc với nhiều kiểu async/reactive khác nhau qua Reactive Streams.
- Kiểm tra adapter theo **phiên bản Spring và runtime classpath**, không dựa vào danh sách chung trên Internet.
- Dùng `ReactiveAdapter` để chuyển hai chiều và `ReactiveTypeDescriptor` để mô tả đúng semantics.
- Chọn đúng single/multi/no-value, empty và deferred.
- Đăng ký kiểu custom bằng `registerReactiveType`; dùng override chỉ khi cần thay adapter đã có.
- Tạo registry có vòng đời dài và đưa nó vào đúng thành phần Spring sử dụng.
- Phân biệt JDK `Flow.Publisher` với Kotlin `Flow`.
- Không kỳ vọng adapter tạo scheduler, backpressure, non-blocking I/O hoặc serialization.

**Ghi nhớ:** `ReactiveAdapterRegistry` giúp Spring nhận biết và chuyển đổi các kiểu async/reactive về Reactive Streams `Publisher`. Chất lượng tích hợp phụ thuộc vào việc chọn đúng adapter, mô tả chính xác semantics của kiểu nguồn và bảo đảm đúng registry được sử dụng tại nơi Spring xử lý kết quả.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework 6.1.11 — ReactiveAdapterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveAdapterRegistry.html)
- [Spring Framework 6.1.11 — ReactiveAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveAdapter.html)
- [Spring Framework 6.1.11 — ReactiveTypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/ReactiveTypeDescriptor.html)
- [Spring Framework — WebFlux annotated controller return values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework — Kotlin Coroutines](https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html)
- [Spring Framework 6.1 — WebFluxConfigurationSupport Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurationSupport.html)
- [Spring Framework 6.1 — BodyInserters Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html)
