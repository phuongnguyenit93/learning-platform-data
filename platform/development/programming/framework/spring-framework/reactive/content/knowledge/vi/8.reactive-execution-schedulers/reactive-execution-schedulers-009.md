# Luồng ảo với boundedElastic và điều kiện phiên bản, cấu hình

**Bối cảnh:** Spring Framework – Reactive, nhóm **Luồng thực thi**. Bài này trình bày cách Project Reactor dùng **virtual threads (luồng ảo)** trong `Schedulers.boundedElastic()`, khi nào tính năng khả dụng, cách bật đúng ở JVM hoặc Spring Boot, cách kiểm tra bằng code và các giới hạn cần giữ khi chạy ứng dụng WebFlux.

## 1. Vấn đề: Reactor cần một nơi an toàn để chạy công việc blocking

Spring WebFlux và Project Reactor khuyến khích sử dụng I/O non-blocking. Nhưng trong hệ thống thực tế vẫn có thao tác đồng bộ như:

- Thư viện JDBC/JPA, SDK HTTP đồng bộ, legacy client, đọc file bằng API blocking.
- Một thư viện chờ kết quả, gọi `Thread.sleep(...)` hoặc một API ngoài không hỗ trợ reactive.
- Các bước chuyển tiếp trong quá trình di trú từ kiến trúc imperative sang reactive.

**Không được đặt các thao tác chặn lâu trên Netty event-loop hoặc các thread xử lý non-blocking.** Khi một event-loop bị chặn, những kết nối khác dùng cùng thread cũng phải đợi, khiến latency cao và throughput giảm.

Reactor cung cấp `Schedulers.boundedElastic()` để **đưa công việc blocking ra một scheduler phù hợp, có giới hạn về mức đồng thời và hàng đợi**. Theo cấu hình thông thường, scheduler dùng **platform threads** (luồng Java truyền thống). Với **Java 21+ và Reactor 3.6+**, shared scheduler này có thêm tùy chọn chạy tác vụ trên **virtual threads** khi bật một system property.

Điểm phân biệt quan trọng:

> **Virtual thread giúp giảm chi phí của việc chờ blocking trong nhiều tình huống; nó không biến API blocking thành API non-blocking, và cũng không làm tác vụ CPU tự chạy nhanh hơn.**

Ví dụ, JDBC vẫn gọi một API blocking và vẫn chiếm một connection từ pool. Chuyển lời gọi sang virtual thread có thể giảm chi phí giữ platform thread trong lúc chờ, nhưng không làm database query nhanh hơn hoặc tăng số connection được phép sử dụng.

## 2. Luồng ảo là gì và khác platform thread ở đâu?

**Platform thread** là thread Java truyền thống do JVM ánh xạ tới một luồng hệ điều hành, có chi phí stack và scheduling tương ứng. Với mô hình một platform thread bị chặn cho mỗi tác vụ, nhiều kết nối I/O chờ cùng lúc có thể khiến hệ thống cần nhiều thread và tốn tài nguyên.

**Virtual thread** là thread nhẹ do JVM quản lý, được triển khai ổn định từ **Java 21**. JVM lên lịch nhiều virtual thread lên một nhóm nhỏ hơn các **carrier platform threads**. Khi virtual thread thực hiện một thao tác blocking mà JVM có thể hỗ trợ hiệu quả, nó thường được *unmount* khỏi carrier trong thời gian chờ; carrier có thể chạy virtual thread khác. Khi dữ liệu sẵn sàng, công việc được tiếp tục.

| Tiêu chí | Platform thread | Virtual thread |
| --- | --- | --- |
| Đơn vị logic | Một thread Java truyền thống | Một thread Java nhẹ do JVM quản lý |
| Tài nguyên khi có rất nhiều công việc chờ I/O | Chi phí thread/stack hệ điều hành cao hơn | Thường rẻ hơn khi nhiều tác vụ chờ |
| Công việc CPU-bound | Vẫn bị giới hạn bởi CPU | Vẫn bị giới hạn bởi CPU |
| API blocking | Có thể chặn platform thread | Có thể chạy dạng blocking, JVM tối ưu nhiều trường hợp chờ |
| Điều khiển số DB connection, API rate limit | Phải giới hạn riêng | Vẫn phải giới hạn riêng |
| Thứ tự, transaction, dữ liệu chia sẻ | Không tự an toàn | Không tự an toàn |
| Tương thích thư viện/native code và pinning | Có thể có contention | Cần kiểm tra thêm những đoạn có thể pin carrier |

**Carrier thread** là platform thread mà JVM dùng để thực thi virtual thread ở một thời điểm. Virtual thread không đồng nghĩa với “một core riêng”; hàng nghìn virtual thread cùng chạy phép tính CPU không vượt được số core thực tế.

Virtual thread có thể bị **pinning** trong một số trường hợp, đặc biệt trên một số phiên bản JDK trước các cải tiến của Java 24 khi có blocking trong vùng `synchronized`, code native hoặc những hoạt động không thể unmount. Pinning lâu có thể giữ carrier và làm mất lợi thế của virtual threads. Chi tiết thay đổi theo phiên bản JDK nên cần quan sát runtime thực tế qua JFR, `jcmd` và profiling, thay vì coi mọi câu lệnh blocking đều luôn được unmount.

## 3. Vai trò của `Schedulers.boundedElastic()` trong Reactor

Reactor có nhiều scheduler với mục đích khác nhau:

| Scheduler | Mục đích thường gặp |
| --- | --- |
| `Schedulers.immediate()` | Chạy công việc trực tiếp trên thread hiện tại |
| `Schedulers.single()` | Thực thi trên scheduler dùng thread đơn, phù hợp công việc cần serial execution |
| `Schedulers.parallel()` | Thực thi công việc ngắn, tính toán CPU có giới hạn |
| `Schedulers.boundedElastic()` | Chứa những thao tác blocking/legacy I/O cần tách khỏi event-loop |
| Scheduler tự tạo qua `Schedulers.newBoundedElastic(...)` | Scheduler riêng có giới hạn và lifecycle riêng, cấu hình tùy API phiên bản |

`boundedElastic` được gọi là **bounded** vì không tạo số thread hoặc số tác vụ đang chờ vô hạn. Tùy phiên bản/cấu hình, nó giới hạn số backing thread hoặc số virtual thread active và lượng công việc xếp hàng. Khi vượt giới hạn, scheduling có thể bị từ chối (ví dụ `RejectedExecutionException`), thay vì phát sinh tài nguyên vô hạn.

Ở **shared `Schedulers.boundedElastic()`**, có hai kiểu triển khai chính:

1. **ExecutorService-based, platform-thread mode (mặc định):** dùng pool backing platform threads; thread có thể được tái sử dụng và thread rảnh lâu sẽ bị thu hồi.
2. **Thread-per-task, virtual-thread mode (được bật có điều kiện):** từng tác vụ được schedule để chạy trên **virtual thread mới**, không giữ idle virtual-thread pool để tái sử dụng. Các tác vụ trễ/định kỳ vẫn có thành phần scheduling nội bộ, nhưng phần xử lý được chuyển sang virtual thread khi đến thời điểm thực thi.

Một chương trình không tự chuyển tất cả scheduler của Reactor thành virtual threads khi bật tùy chọn này. Nó chọn **kiểu triển khai của shared `boundedElastic()`**. Các đoạn chạy trên Netty event-loop, `parallel()`, `single()`, custom `Executor` hoặc một scheduler khác không mặc nhiên chạy trên virtual threads.

### 3.1. Vì sao vẫn có giới hạn khi virtual thread rất nhẹ?

Virtual thread rẻ hơn platform thread khi chờ, nhưng mỗi tác vụ vẫn có object, stack logic, tài nguyên công việc và khả năng giữ connection/lock. Tạo quá nhiều tác vụ một lúc vẫn có thể:

- Làm tràn database connection pool hoặc giới hạn phía API khác.
- Tăng hàng đợi, heap, GC, timeouts và p99 latency.
- Gây bão retry, contention hoặc làm nghẽn upstream.
- Chiếm CPU nếu tác vụ có khối lượng tính toán lớn.

**Thêm virtual threads không thay cho kiểm soát concurrency và backpressure.** Dùng `flatMap(..., concurrency)`, semaphore/bulkhead, connection pool và giới hạn tốc độ nơi thực sự cần, không chỉ tăng scheduler cap.

## 4. Điều kiện chính xác về phiên bản

Tính năng **virtual-thread implementation của shared Reactor `boundedElastic()`** xuất hiện từ **Reactor Core 3.6.0**.

| Thành phần | Điều kiện | Nếu không đạt |
| --- | --- | --- |
| Java runtime | **JDK/JRE 21 trở lên**, hỗ trợ virtual threads ổn định | Không bật được chế độ virtual-thread này; dùng platform-thread scheduler/chiến lược tương thích |
| Reactor Core | **3.6.0 trở lên**, với API/cấu hình được phiên bản hỗ trợ | Reactor trước 3.6 không có tùy chọn shared `boundedElastic` này |
| Cấu hình Reactor | `reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` **trước khi scheduler được khởi tạo** | Shared `boundedElastic` dùng platform threads theo mặc định |
| Đường chạy code | Công việc phải được schedule lên shared `Schedulers.boundedElastic()` | Công việc ở event-loop hoặc scheduler khác không tự chuyển sang virtual thread |
| JVM thực tế triển khai | Container, IDE, Gradle/Maven hoặc runtime production phải chạy bằng Java 21+ | Có thể compile bằng JDK mới nhưng chạy bằng runtime khác, khiến kỳ vọng sai |

**Không suy luận phiên bản Reactor chỉ từ tên Spring Framework hay Spring Boot.** Spring Boot quản lý version thông qua BOM/dependency management; kiểm tra dependency runtime thực tế. Trong ứng dụng Gradle, dùng công cụ dependency report như `./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath`. Trong Maven, có thể dùng `mvn dependency:tree -Dincludes=io.projectreactor:reactor-core`.

Java 21 là **yêu cầu runtime**; code sample dùng `Thread.currentThread().isVirtual()` cũng cần biên dịch bằng JDK hỗ trợ API đó. Với Java 17, vẫn có thể sử dụng `boundedElastic` kiểu platform-thread để cô lập công việc blocking, nhưng **không dùng được chế độ virtual-thread Reactor theo điều kiện này**.

## 5. Bật virtual threads cho Reactor bằng JVM system property

Tên property **chính xác**, phân biệt chữ hoa/thường:

```properties
reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
```

Ví dụ với một ứng dụng đóng gói JAR và JVM Java 21+:

```bash
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true -jar app.jar
```

Với runtime dùng Docker/Kubernetes, có thể chuyển tham số tương đương qua JVM startup args hoặc `JAVA_TOOL_OPTIONS`; phải bảo đảm property đến **JVM chạy ứng dụng**, không chỉ đến tiến trình build tool.

**Đặt property trước lần khởi tạo đầu tiên của Reactor scheduler.** Reactor đọc cấu hình từ system property khi khởi tạo những thành phần liên quan; shared scheduler cũng có lifecycle/caching riêng. Đặt `System.setProperty(...)` muộn sau khi một thư viện đã gọi `Schedulers.boundedElastic()` không bảo đảm chuyển một instance đã tạo từ platform threads sang virtual threads.

Vì vậy, cách ổn định là đặt cờ `-D...=true` lúc **khởi động JVM** rồi restart ứng dụng. Với các test cần so sánh hai chế độ, chạy **hai JVM process độc lập**, mỗi process với cấu hình ngay từ đầu; tránh thử bật/tắt property trong cùng process đã khởi tạo scheduler.

### 5.1. Các property giới hạn boundedElastic

Cùng với việc chọn kiểu thread, Reactor cung cấp cấu hình giới hạn cho shared boundedElastic:

```properties
reactor.schedulers.defaultBoundedElasticSize=80
reactor.schedulers.defaultBoundedElasticQueueSize=1000
```

Đây là **ví dụ giá trị để minh họa**, không phải khuyến nghị mặc định cho production. Tài liệu Reactor mô tả:

- `reactor.schedulers.defaultBoundedElasticSize`: giới hạn số thread active/backing tasks ở shared scheduler; mặc định thường dựa trên **10 × số CPU khả dụng**.
- `reactor.schedulers.defaultBoundedElasticQueueSize`: giới hạn công việc được chờ trong nội bộ, mặc định ở các phiên bản được tham chiếu là **100.000 tác vụ bổ sung trên mỗi backing thread/cấu trúc giới hạn tương ứng**.
- Khi vượt giới hạn, scheduling có thể bị từ chối. Kích thước queue rất lớn có thể biến tải đột biến thành **latency hàng đợi** kéo dài thay vì giải quyết nút thắt.

Các giá trị nên xác định bằng tải thực tế: số request đang chờ I/O, connection pool, độ dài mỗi tác vụ, thời gian chờ, tỷ lệ timeout và ngân sách bộ nhớ. **Không tự động tăng cả hai giới hạn lên mức cực lớn chỉ vì virtual thread nhẹ.** Giá trị mặc định hoặc chi tiết cách phân phối queue có thể đổi theo phiên bản; tra Javadoc `Schedulers` tương ứng với artifact đang chạy.

### 5.2. Cờ Reactor áp dụng cho scheduler nào?

Cờ `reactor.schedulers.defaultBoundedElasticOnVirtualThreads` được tài liệu hóa cho **shared `Schedulers.boundedElastic()`**. Không mặc định suy ra rằng một scheduler custom tạo qua `Schedulers.newBoundedElastic(...)`, executor tự viết, `Schedulers.parallel()` hoặc các thread của Netty cũng dùng virtual threads. API tạo custom scheduler có thể khác nhau theo Reactor version; kiểm tra Javadoc của overload đang sử dụng.

Nếu ứng dụng đã khai báo custom `Schedulers.Factory`, custom scheduler, Spring `Executor` hoặc thay đổi lifecycle global scheduler, hãy kiểm tra kết quả runtime. Tên method tương tự không bảo đảm cùng cấu hình.

## 6. Spring Boot: phân biệt property của Spring với property của Reactor

Spring Boot hỗ trợ:

```properties
spring.threads.virtual.enabled=true
```

Khi chạy **Java 21+**, property này hướng các executor/scheduler **do Spring Boot quản lý** sang virtual threads ở những nơi được Boot hỗ trợ. Nó cũng liên quan đến cấu hình Reactor trong các phiên bản Spring Boot có `ReactorEnvironmentPostProcessor`: Boot có thể **đặt Reactor system property** để shared `boundedElastic()` chạy virtual threads ngay trong quá trình khởi động.

Vì vậy, có **hai đường cấu hình thực tế**:

1. **Ứng dụng Reactor độc lập hoặc cần cấu hình tường minh:** đặt trực tiếp `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` trước khi JVM khởi tạo scheduler.
2. **Ứng dụng Spring Boot phiên bản có tích hợp:** đặt `spring.threads.virtual.enabled=true` và xác nhận bản Boot đang chạy cấu hình Reactor đúng như mong muốn. Boot 3.2+ có `ReactorEnvironmentPostProcessor` thực hiện việc đặt property Reactor khi Java đạt điều kiện.

Ví dụ `src/main/resources/application.properties` trong dự án Spring Boot tương thích:

```properties
spring.threads.virtual.enabled=true
```

**Chú ý:** `spring.threads.virtual.enabled` và `reactor.schedulers.defaultBoundedElasticOnVirtualThreads` **không phải cùng một key**. Key thứ nhất do Spring Boot xử lý, key thứ hai do Reactor xử lý. Với ứng dụng **không chạy qua SpringApplication**, chỉ đặt key Spring trong một file properties không tự cấu hình Reactor.

Cũng không kết luận mọi request WebFlux được xử lý trên virtual thread khi bật property: WebFlux thường sử dụng Netty event-loop để chạy non-blocking I/O. Chỉ những đoạn thực sự được chuyển tới boundedElastic (hoặc executor khác được cấu hình dùng virtual threads) mới sử dụng chúng theo thiết kế.

**Thứ tự khởi tạo:** Nếu một thư viện gọi `Schedulers.boundedElastic()` quá sớm, trước khi Spring Boot xử lý environment, kết quả có thể không như kỳ vọng. Hãy kiểm tra trong JVM thật. Tránh tạo scheduler global ở static initializer của class khởi động khi chưa chắc cấu hình đã được áp dụng.

### 6.1. Lưu ý với các công việc được Spring Boot tự cấu hình

Khi bật `spring.threads.virtual.enabled=true`, một số bean `AsyncTaskExecutor` hoặc scheduling do Boot tạo có thể thay đổi sang executor dùng virtual threads. Tác động này **rộng hơn** riêng `boundedElastic` và có thể làm các thông số cấu hình pool thread truyền thống không còn ý nghĩa cho những executor dùng virtual threads.

Virtual threads là daemon threads. Nếu ứng dụng chủ yếu dựa vào các tác vụ scheduler để giữ JVM sống, cần xét quy tắc kết thúc JVM; tài liệu Spring Boot có đề cập `spring.main.keep-alive=true` trong những trường hợp phù hợp. Một ứng dụng web đang có server giữ JVM sống thường có đặc điểm khác công cụ chỉ chạy scheduled jobs, nên kiểm tra lifecycle cụ thể.

## 7. Ví dụ Java 21 chạy được: chứng minh boundedElastic có dùng virtual thread

Ví dụ sau là **class Java hoàn chỉnh**, không phụ thuộc Spring. Nó dùng Reactor để schedule `Mono.fromCallable(...)` sang shared `boundedElastic` và kiểm tra trực tiếp bằng `Thread.currentThread().isVirtual()`.

Tệp `src/main/java/demo/VirtualBoundedElasticDemo.java`:

```java
package demo;

import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class VirtualBoundedElasticDemo {
    public static void main(String[] args) {
        Boolean virtual = Mono.fromCallable(() ->
                        Thread.currentThread().isVirtual())
                .subscribeOn(Schedulers.boundedElastic())
                .block(Duration.ofSeconds(5));

        System.out.println("boundedElastic isVirtual=" + virtual);
    }
}
```

Điều kiện biên dịch/chạy: **JDK 21+**, `reactor-core 3.6+` và `org.reactivestreams:reactive-streams` tương thích trong classpath. Trong ứng dụng Spring Boot có starter WebFlux phù hợp, các dependency Reactor thường được quản lý sẵn. Để chạy thủ công, đặt các JAR phù hợp vào `lib/` rồi chạy:

```bash
# Linux/macOS (tại thư mục dự án)
mkdir -p out
javac -cp "lib/*" -d out src/main/java/demo/VirtualBoundedElasticDemo.java

# Chế độ mặc định: platform threads
java -cp "out:lib/*" demo.VirtualBoundedElasticDemo

# Virtual-thread mode: bật trước khi khởi tạo Reactor
java -Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true \
     -cp "out:lib/*" demo.VirtualBoundedElasticDemo
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out
javac -cp "lib/*" -d out src/main/java/demo/VirtualBoundedElasticDemo.java

java -cp "out;lib/*" demo.VirtualBoundedElasticDemo

java "-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true" `
    -cp "out;lib/*" demo.VirtualBoundedElasticDemo
```

**Stdout chính xác theo hai lượt chạy trong điều kiện nêu trên:**

Không bật property:

```text
boundedElastic isVirtual=false
```

Bật property trên Reactor 3.6+, Java 21+:

```text
boundedElastic isVirtual=true
```

**Giải thích:**

1. `Mono.fromCallable(...)` trì hoãn việc kiểm tra thread cho tới lúc publisher được kích hoạt.
2. `subscribeOn(Schedulers.boundedElastic())` chuyển quá trình subscribe/upstream callable sang scheduler. Vì vậy `isVirtual()` kiểm tra **thread chạy công việc**, không phải main thread.
3. `block(Duration.ofSeconds(5))` là cầu nối có chặn trong một chương trình dòng lệnh có hàm `main`, được dùng ở đây để lấy kết quả và in theo thứ tự xác định. **Không dùng `block()` bên trong WebFlux event-loop**.
4. Hai lệnh Java là hai process khác nhau, cho phép kiểm tra chế độ platform và virtual độc lập; không phụ thuộc vào việc reset scheduler toàn cục.
5. Cần chắc chắn không có property khác từ môi trường (như `JAVA_TOOL_OPTIONS` hoặc cấu hình khởi động IDE) tự bật virtual thread ở lượt chạy “mặc định”.

Kết quả `true` chứng minh **tác vụ được schedule trên boundedElastic** đang chạy trong virtual thread; nó **không chứng minh** tất cả luồng ứng dụng, Netty hoặc mọi publisher trong pipeline đã dùng virtual threads.

## 8. Kết hợp với code blocking: dùng `fromCallable` + `subscribeOn`

Một service legacy có API đồng bộ có thể được bridge tạm thời:

Tệp `src/main/java/demo/LegacyLookupService.java` trong một dự án Spring Boot/WebFlux có `spring-boot-starter-webflux`:

```java
package demo;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class LegacyLookupService {

    public Mono<String> lookup(String key) {
        return Mono.fromCallable(() -> legacyLookup(key))
                .subscribeOn(Schedulers.boundedElastic());
    }

    private String legacyLookup(String key)
            throws InterruptedException {
        // Đại diện cho lời gọi blocking của thư viện legacy.
        Thread.sleep(50);
        return "value-for-" + key;
    }
}
```

Trong một controller WebFlux, return publisher do service tạo:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class LegacyLookupController {
    private final LegacyLookupService service;

    public LegacyLookupController(LegacyLookupService service) {
        this.service = service;
    }

    @GetMapping("/lookup/{key}")
    public Mono<String> lookup(@PathVariable String key) {
        return service.lookup(key);
    }
}
```

Đây là **hai class đặt trong một dự án Spring Boot đang chạy**, không phải hai file có `main` độc lập. Với các class này và ứng dụng Boot đã cấu hình đúng, gọi `curl http://localhost:8080/lookup/abc` sẽ nhận body `value-for-abc` nếu server chạy cổng 8080; việc dùng virtual thread hay platform thread phụ thuộc cấu hình boundedElastic runtime như đã trình bày.

### 8.1. Vì sao phải dùng `fromCallable`?

Sai:

```java
return Mono.just(legacyLookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

**Đoạn trên là minh họa lỗi**, không phải method độc lập: nó cần xử lý checked exception và định nghĩa `legacyLookup` tương ứng. Java đánh giá `legacyLookup(key)` **trước khi gọi `Mono.just(...)`**. Vì thế lời gọi blocking xảy ra ngay tại chỗ dựng publisher, có thể chính trên event-loop. `subscribeOn` xuất hiện sau đó không quay ngược thời gian để di chuyển một lời gọi đã chạy.

Đúng:

```java
return Mono.fromCallable(() -> legacyLookup(key))
        .subscribeOn(Schedulers.boundedElastic());
```

Lambda của `fromCallable` chỉ được thực thi khi có subscription; `subscribeOn` định tuyến tác vụ upstream sang boundedElastic.

### 8.2. `subscribeOn` và `publishOn` không có cùng ý nghĩa

- `subscribeOn(scheduler)` ảnh hưởng nơi quá trình subscription và các bước xử lý upstream được thực thi. Với nguồn blocking được đặt trong `fromCallable`, nó là cách điển hình để đưa blocking source sang boundedElastic.
- `publishOn(scheduler)` chuyển **việc xử lý tín hiệu downstream sau vị trí đặt operator** sang scheduler. Phù hợp nếu một đoạn xử lý tín hiệu cụ thể phải dùng executor khác.
- Cả hai **không tự biến** một HTTP client synchronous thành non-blocking; chúng chỉ ảnh hưởng thread thực thi.
- Scheduler được chọn tại **mỗi điểm đặt**. Một pipeline có thể đổi thread nhiều lần; không giả định một request WebFlux luôn ở cùng một thread hoặc luôn dùng virtual thread.

Ví dụ:

```java
Flux<Integer> values = Flux.range(1, 3)
        .publishOn(Schedulers.boundedElastic())
        .map(value -> expensiveBlockingTransform(value));
```

Đây là đoạn minh họa với `expensiveBlockingTransform(...)` do ứng dụng định nghĩa. Nếu hàm transform blocking, `publishOn` có thể cô lập đoạn downstream đó khỏi luồng trước, nhưng với pipeline lớn cần xem chi phí chuyển thread, kích thước prefetch và giới hạn tác vụ. Trong nhiều trường hợp nguồn legacy tốt hơn nên được cô lập bằng `fromCallable(...).subscribeOn(...)`.

### 8.3. Virtual thread không tự làm giao dịch blocking thành reactive

JPA/JDBC vẫn sử dụng transaction và connection đồng bộ, có thể dựa vào `ThreadLocal` của Spring. Chỉ bọc một `JpaRepository` vào publisher không biến transaction thành reactive transaction. Cần giữ **ranh giới transaction imperative** bên trong công việc chạy trên một thread phù hợp; đừng giả định `@Transactional` reactive tự bao phủ một chuỗi `Mono` đã chuyển qua nhiều scheduler.

Khi một transaction đòi hỏi nhiều lệnh ghi JDBC có tính nguyên tử, hãy để một phương thức service imperative có transaction riêng thực hiện toàn bộ thao tác, rồi gọi nó qua boundary `fromCallable` phù hợp, hoặc chọn kiến trúc MVC/virtual threads nếu phần lớn hệ thống vẫn blocking. Việc trộn JPA với WebFlux cần đánh giá rõ transaction, connection pool, error propagation và cancellation.

## 9. Điều gì thực sự thay đổi khi bật virtual-thread boundedElastic?

Hãy tách **kiểu thread thực thi tác vụ** khỏi **ngữ nghĩa publisher**:

| Vấn đề | Platform-thread boundedElastic | Virtual-thread boundedElastic |
| --- | --- | --- |
| Cách chạy task | Backing platform threads, có thể tái dùng | Thread ảo mới cho từng scheduled task theo triển khai Reactor |
| API `Mono/Flux`, `subscribeOn`, `publishOn` | Không đổi | Không đổi |
| Trạng thái blocking của JDBC/SDK đồng bộ | Vẫn blocking | Vẫn blocking, nhưng nhiều thao tác chờ có thể dùng platform carriers hiệu quả hơn |
| Giới hạn đồng thời/queue của scheduler | Có | Có |
| Bảo đảm ordering của tín hiệu Reactive Streams | Theo operator/nguồn | Theo operator/nguồn, không tự thay đổi |
| Backpressure | Theo subscription và operator | Không được virtual thread tự bổ sung |
| Tốc độ truy vấn DB | Phụ thuộc DB, pool, query | Vẫn phụ thuộc DB, pool, query |
| Tác vụ CPU-bound | Không tự nhanh hơn | Không tự nhanh hơn |
| ThreadLocal/log context | Cần thiết kế theo request/runtime | Vẫn cần thiết kế, không tự propagate across scheduler boundaries |

Trong Reactor, **cancellation** sẽ gửi tín hiệu tới subscription; nhưng không thể khẳng định mọi legacy blocking call đang chạy trên virtual thread đều lập tức dừng, đặc biệt khi driver/library không đáp ứng interruption hoặc đã gửi tác vụ đến hệ thống ngoài. Với các công việc có side effect như thanh toán, ghi đơn hàng, gọi API tạo resource, phải có timeout, idempotency và quy tắc nhất quán riêng.

**Đừng tăng `flatMap` concurrency quá mức** chỉ vì virtual threads có chi phí nhỏ. Mỗi inner vẫn có thể giữ một DB connection hoặc chờ một dịch vụ giới hạn tài nguyên. Nếu 10.000 tác vụ đồng thời nhưng DB pool chỉ 30, hệ thống có thể chỉ chuyển nút thắt thành hàng đợi dài hơn.

## 10. Kiểm chứng cấu hình đúng trong ứng dụng chạy thật

Chỉ có cấu hình trong file hoặc câu lệnh launch chưa chứng minh scheduler đã hoạt động như mong muốn. Một kiểm chứng hợp lý gồm các bước sau:

1. **Xác định JVM** bằng `java -version` ở môi trường chạy ứng dụng (không chỉ máy phát triển). Với container, kiểm tra phiên bản Java **bên trong image**.
2. **Xác định Reactor Core runtime** qua dependency report (Gradle/Maven) và BOM đang áp dụng; điều kiện là **3.6+**.
3. **Xác định cách bật property**: trực tiếp qua JVM `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`, hoặc qua Spring Boot integration phù hợp với `spring.threads.virtual.enabled=true`.
4. **Khởi động mới process**, không dựa vào `System.setProperty` sau lần đầu tham chiếu Reactor scheduler.
5. **Kiểm tra ngay trong công việc schedule trên shared `boundedElastic`** bằng `Thread.currentThread().isVirtual()` như ví dụ Java 21.
6. **Đo tải và resource**, gồm throughput kèm error rate, p50/p95/p99, số tác vụ đang chờ, scheduler rejections, heap, CPU, DB connection pool và thời gian chờ upstream.
7. **Kiểm tra cancellation, timeout và tracing**; xác nhận legacy client và transaction có hành vi đúng khi request bị ngắt, timeout hoặc retry.

Cần so sánh trên **cùng workload và cùng giới hạn downstream** giữa platform-thread mode và virtual-thread mode. Benchmark chỉ tạo hàng trăm nghìn virtual threads ngủ mà không đi qua DB, connection pool và logic nghiệp vụ có thể gây hiểu nhầm rằng production sẽ đạt thông lượng tương tự.

### 10.1. Test cấu hình dựa trên `isVirtual()`

Nếu ứng dụng đã có JUnit Jupiter và `reactor-test`, một test có thể xác nhận hành vi khi **process được khởi động sẵn với virtual mode**:

Tệp `src/test/java/demo/VirtualBoundedElasticTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class VirtualBoundedElasticTest {

    @Test
    void boundedElasticUsesVirtualThreadWhenConfigured() {
        Mono<Boolean> onVirtualThread =
                Mono.fromCallable(() ->
                        Thread.currentThread().isVirtual())
                    .subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(onVirtualThread)
                .expectNext(true)
                .verifyComplete();
    }
}
```

**Điều kiện test:** chạy JVM test bằng JDK 21+, Reactor Core 3.6+, và đặt `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` **ngay khi khởi động test JVM**. Cần `reactor-test` trên test classpath. Nếu chạy test trong process mặc định chưa bật mode, kỳ vọng `true` sẽ thất bại — đây là cách test phát hiện cấu hình sai, **không phải test phải tự bật property khi scheduler đã được sử dụng**.

Trong Gradle, có thể đặt JVM args cho tác vụ test chuyên biệt; khi dùng `./gradlew test`, cờ `-D...` gán cho JVM của Gradle daemon **không mặc định đồng nghĩa** nó được chuyển tới mọi forked test worker. Cần thiết lập `systemProperty`/`jvmArgs` cho test task nếu muốn test JVM chạy với đúng flag. Tương tự cần xác minh config của Maven Surefire/Failsafe.

Nếu test nhiều môi trường (Java 17, Java 21 mode off, Java 21 mode on), nên có các test process độc lập và kỳ vọng tương ứng; đừng viết một test bắt buộc `true` nhưng rồi chạy trên Java 17.

## 11. Những vấn đề vận hành và hiệu năng cần chú ý

### 11.1. Không tăng tốc cho công việc CPU-bound

Virtual threads tập trung cải thiện khả năng duy trì số lượng lớn **tác vụ chờ**. Nếu request làm hash, mã hóa, nén hoặc tính toán CPU lâu, số virtual threads nhiều không giúp vượt giới hạn CPU. Hãy tối ưu thuật toán, giảm số tác vụ tính toán đồng thời hoặc dùng tài nguyên tính toán phù hợp.

### 11.2. Pinning, native call và locking

Một thao tác blocking có thể khiến virtual thread vẫn giữ carrier (*pin*) trong một số trường hợp. Tùy JDK và thư viện, điều này có thể gặp khi blocking xảy ra trong đoạn `synchronized` hoặc đi qua API native không hỗ trợ cơ chế unmount hiệu quả. **JDK 24 trở lên có các cải tiến đáng kể về monitor pinning**, nên không áp dụng nguyên xi mọi cảnh báo hiệu năng của Java 21 cho mọi JDK mới.

Khi hiệu năng kém bất thường, dùng Java Flight Recorder và các công cụ JVM tương thích để tìm pinning, contention và blocked tasks. Hãy tối ưu nguyên nhân thực tế chứ không suy luận từ tên scheduler.

### 11.3. Context propagation không tự biến mất

Spring Security context, log MDC, tracing span hoặc các giá trị gắn với `ThreadLocal` có thể bị mất khi Reactor chuyển thread nếu không có cơ chế truyền ngữ cảnh tương ứng. Virtual thread có ThreadLocal riêng, nhưng điều đó **không có nghĩa** context của Netty event-loop tự được copy sang virtual thread mới.

Trong pipeline reactive, dùng **Reactor Context** và cơ chế context propagation được Spring/Reactor hỗ trợ theo phiên bản. Với legacy library cần ThreadLocal, phải kiểm tra adapter/bridge thực tế, không tự truyền mutable request state qua biến static.

### 11.4. Quan sát tài nguyên ở đúng lớp

Mức sử dụng platform threads có thể giảm nhưng bottleneck vẫn nằm ở một trong các điểm sau:

- JDBC connection pool hết connection và tạo hàng đợi chờ.
- Dịch vụ upstream có giới hạn QPS/concurrency hoặc API rate limit.
- Khối lượng CPU trên carrier và tác vụ downstream cao.
- Scheduler `boundedElastic` đã đạt cap hoặc queue limit và bắt đầu bị từ chối.
- Lock contention, native call, pinning hoặc memory retention.
- Retry và timeout khiến số tác vụ in-flight tăng hơn dự kiến.

**Kết quả đáng đo** là SLA thực tế: p95/p99 latency, throughput với cùng tỷ lệ lỗi, memory/GC, CPU, số connection và khả năng phục hồi sau spike. Không dùng riêng số lượng virtual threads để kết luận cấu hình tốt hơn.

## 12. Phân biệt ba câu nói dễ gây hiểu sai

**“Bật virtual threads là chuyển WebFlux sang thread-per-request.”** Không đúng. WebFlux vẫn dùng event-loop và pipeline bất đồng bộ nơi thích hợp. Chỉ những phần sử dụng scheduler/executor được cấu hình dùng virtual threads mới chạy như vậy.

**“Chạy `boundedElastic()` trên virtual threads làm JDBC thành reactive.”** Không đúng. JDBC vẫn blocking, vẫn cần connection, transaction và giới hạn truy vấn; chỉ nơi chờ blocking được thực thi bằng một loại Java thread khác.

**“Virtual threads không giới hạn, nên bỏ qua pool, queue và backpressure.”** Không đúng. BoundedElastic tiếp tục có cap/queue; database, CPU, memory và dịch vụ ngoài vẫn có giới hạn.

Một mô hình phối hợp hữu ích:

```text
                  Spring WebFlux request
                           |
                    Non-blocking chain
                           |
           [legacy blocking call vẫn cần dùng]
                           |
              Mono.fromCallable(() -> call())
                           |
              subscribeOn(boundedElastic)
                           |
     +---------------------+-----------------------+
     |                                             |
  Flag false                                  Flag true
  Java tương thích                            Java 21+, Reactor 3.6+
     |                                             |
  Platform thread                              Virtual thread
     |                                             |
     +---------------------+-----------------------+
                           |
               Trả kết quả Mono tới WebFlux
                           |
                  Response / error / cancel
```

Mỗi nhánh có đặc điểm tài nguyên khác nhau, nhưng **giới hạn upstream, quy tắc transaction và error propagation vẫn phải được đảm bảo**.

## 13. Lỗi cấu hình phổ biến và cách khắc phục

| Triệu chứng/nhầm lẫn | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Đã bật flag nhưng `isVirtual()=false` | Java chạy thực tế dưới 21; Reactor dưới 3.6; flag vào nhầm JVM; scheduler khởi tạo quá sớm | Xác định JVM/process, dependency runtime, startup arguments rồi chạy lại từ process mới |
| Đã đặt `spring.threads.virtual.enabled=true` trong ứng dụng Reactor standalone | Không có SpringApplication/Boot để dịch key sang Reactor property | Dùng JVM system property Reactor trực tiếp |
| Thread ở controller vẫn là Netty event-loop | Phần controller chưa được schedule trên boundedElastic; đây thường là hành vi WebFlux bình thường | Kiểm tra bên trong tác vụ `subscribeOn(boundedElastic)` thay vì ở đầu controller |
| Gọi `Mono.just(blockingCall())` rồi `subscribeOn` | Blocking đã chạy khi đánh giá đối số | Chuyển thành `Mono.fromCallable(() -> blockingCall()).subscribeOn(...)` |
| Test qua `./gradlew test -D...` không dùng virtual threads | Property có thể không tới forked test JVM | Cấu hình riêng system property/jvmArgs cho Gradle Test task |
| Hệ thống vẫn chậm khi bật virtual threads | Bottleneck nằm ở DB pool, locks, CPU, queue, pinning, upstream | Đo p95/p99, queue, pool, JFR; giới hạn concurrency và tối ưu thực chất |
| Timeout HTTP nhưng task legacy vẫn chạy | Cancel subscription không luôn hủy công việc blocking phía sau | Thiết kế timeout, interrupt/cancel theo SDK hỗ trợ và idempotency |
| Tăng `boundedElasticSize` làm latency tệ hơn | Tạo nhiều tác vụ cạnh tranh cho ít connection/tài nguyên | Kiểm soát concurrent work và độ dài queue, benchmark lại |
| Dữ liệu log/security context mất sau chuyển thread | ThreadLocal không tự lan qua boundary của Reactor/virtual threads | Dùng Reactor Context và context-propagation tương thích |
| Gọi scheduler custom mà flag không tác dụng | Property áp dụng cho shared `Schedulers.boundedElastic()`, không tự cấu hình mọi custom executor | Kiểm tra chính instance chạy task, API tương ứng và lifecycle |

## 14. Checklist triển khai

1. **Bài toán thật sự có blocking I/O cần cô lập không?** Nếu đã có `WebClient`, R2DBC hay driver non-blocking phù hợp, ưu tiên giữ đường non-blocking đó.
2. **Java runtime và Reactor Core đáp ứng điều kiện chưa?** Java 21+, Reactor 3.6+.
3. **Đã bật đúng property chưa?** JVM `-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true` trước startup, hoặc Spring Boot integration tương thích.
4. **Code đã đưa phần blocking vào lambda trì hoãn chưa?** `fromCallable`/`fromRunnable` với `subscribeOn(boundedElastic)`; tránh blocking trong `Mono.just(...)`.
5. **Kiểm chứng trực tiếp `Thread.isVirtual()` ngay trong task chưa?** Không đo ở main thread hoặc event-loop rồi kết luận sai.
6. **Đã đặt giới hạn concurrency, DB pool, API timeout, scheduler queue chưa?** Virtual thread không tự giới hạn những tầng này.
7. **Đã kiểm tra lifecycle, transaction, security context và cancellation chưa?** Đặc biệt khi dùng legacy SDK/JDBC.
8. **Đã benchmark đúng kiểu tải chưa?** So sánh mode platform và virtual trên hai process, cùng dữ liệu và các giới hạn.
9. **Đã có quan sát pinning, scheduler rejection, p99 latency chưa?** Dùng metrics/JFR phù hợp.
10. **Có thật sự cần WebFlux không?** Nếu toàn bộ nghiệp vụ vẫn imperative và blocking, Spring MVC + virtual threads cũng là lựa chọn cần so sánh; kết luận phải theo nhu cầu vận hành.

## 15. Tài liệu tham khảo

- [Project Reactor Reference – Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): hai kiểu triển khai của `boundedElastic`, Java 21+ và system property bật virtual threads.
- [Project Reactor Schedulers Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): `boundedElastic()`, các cấu hình `DEFAULT_BOUNDED_ELASTIC_*` và những giới hạn liên quan.
- [Spring Boot ReactorEnvironmentPostProcessor (Boot 3.3)](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/reactor/ReactorEnvironmentPostProcessor.html): sự liên kết của `spring.threads.virtual.enabled` với Reactor system property khi Java đạt điều kiện.
- [Spring Boot – Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): phạm vi tác động của cấu hình virtual threads lên executor và scheduling do Boot quản lý.
- [Spring Blog – Reactor Core 3.6.0](https://spring.io/blog/2023/10/31/what-new-is-coming-in-reactor-core-3-6-0/): giới thiệu scheduler thread-per-task dùng virtual threads.

## 16. Ghi nhớ

**Muốn shared `Schedulers.boundedElastic()` dùng virtual threads**, cần **Java 21+**, **Reactor Core 3.6+**, và bật đúng cấu hình **`reactor.schedulers.defaultBoundedElasticOnVirtualThreads=true`** trước khi scheduler được khởi tạo. Trong Spring Boot có tích hợp phù hợp, **`spring.threads.virtual.enabled=true`** có thể thiết lập chế độ đó cùng các executor khác của Boot.

Virtual threads cải thiện cách JVM quản lý nhiều tác vụ blocking I/O, nhưng **không thay đổi contract reactive, không làm JDBC non-blocking và không xóa giới hạn của CPU, connection pool hay upstream**. Luôn đo `Thread.currentThread().isVirtual()` ngay trong task, giữ giới hạn concurrency/queue và kiểm chứng bằng kết quả vận hành thực tế.
