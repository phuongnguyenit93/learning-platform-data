# `single`, `parallel` và `boundedElastic`: chọn luồng thực thi trong Project Reactor

## 1. Mục tiêu và bối cảnh

Trong Spring Framework Reactive và Spring WebFlux, `Flux<T>`/`Mono<T>` mô tả luồng dữ liệu và tín hiệu, nhưng **chỉ dùng kiểu reactive không tự sinh ra thread mới**. Theo mặc định, phần lớn toán tử tiếp tục chạy trên thread đang phát tín hiệu trước đó. Nếu muốn chuyển nơi thực thi, ta có thể sử dụng abstraction `Scheduler` của Project Reactor.

Bài học này tập trung vào ba Scheduler thông dụng:

- `Schedulers.single()` — một thread dùng chung, phù hợp với tác vụ ngắn cần được xếp lần lượt.
- `Schedulers.parallel()` — nhóm worker hữu hạn, hướng đến công việc tính toán nhanh, **không blocking**, có thể xử lý nhiều công việc độc lập trên các thread khác nhau.
- `Schedulers.boundedElastic()` — nhóm worker co giãn có giới hạn, phù hợp khi bắt buộc tích hợp **API đồng bộ có thể chặn thread**, ví dụ thư viện JDBC truyền thống, thao tác file blocking hoặc SDK cũ.

Bạn cần phân biệt **Scheduler**, `publishOn`, `subscribeOn`, `Flux.parallel()` và các câu hỏi thực tế: một pipeline chạy ở thread nào, chuyển thread ở vị trí nào, có thực sự chạy đồng thời không, và khi nào tránh block.

## 2. Scheduler là gì và vì sao Reactor cần nó?

Một `Scheduler` chịu trách nhiệm lên lịch thực thi các tác vụ. Nó đóng vai trò gần với `ExecutorService` nhưng là abstraction riêng của Reactor, còn được dùng cho các thao tác gắn với thời gian, scheduling và kiểm thử virtual time. `Schedulers` là lớp factory cung cấp các lựa chọn phổ biến.

Với đoạn mã sau, việc tạo Publisher không lập tức chuyển công việc sang background:

~~~java
Flux<Integer> numbers = Flux.range(1, 3)
    .map(i -> i * 2);

// Chỉ đến khi đăng ký mới chạy; mặc định thường sử dụng
// thread phát tín hiệu hoặc thread thực hiện subscribe().
numbers.subscribe(System.out::println);
~~~

Nếu không có toán tử chỉ định Scheduler và nguồn không tự quản lý thread, `subscribe` trên thread `main` thường khiến `map` và `onNext` cũng chạy trên `main`. Nhưng không nên phát biểu rằng **mọi** `Flux` luôn chạy trên thread gọi `subscribe`: một số nguồn bất đồng bộ hoặc toán tử (ví dụ `Flux.interval`) tự dùng Scheduler.

Khái niệm quan trọng:

| Khái niệm | Nghĩa |
| --- | --- |
| **Assembly** | Lúc tạo `Flux`/`Mono` và ghép toán tử; phần lớn dữ liệu chưa được phát |
| **Subscription** | Lúc một Subscriber đăng ký; luồng tín hiệu có thể bắt đầu |
| **Worker** | Đối tượng mà Scheduler cấp để thực thi các công việc đã lên lịch |
| **Scheduler** | Cơ chế chọn, sắp xếp worker/thread cho công việc |
| **Thread** | Đơn vị thực thi JVM/OS (hoặc virtual thread trên Java hỗ trợ) |
| **Non-blocking** | Tác vụ không giữ thread chỉ để chờ I/O hoàn tất |
| **Blocking** | Tác vụ giữ thread trong lúc chờ, như `Thread.sleep`, I/O đồng bộ, nhiều thư viện JDBC |

**Scheduler không phải bảo đảm về hiệu năng**. Dời việc chặn thread sang pool riêng có thể bảo vệ event loop, nhưng vẫn tiêu thụ thread, connection, bộ nhớ và có thể làm tăng thời gian chờ.

## 3. `Schedulers.single()`: một thread dùng chung

### 3.1. Đặc tính

`Schedulers.single()` trả về **Scheduler dùng chung** có một thread tái sử dụng cho các caller. Công việc do các subscriber khác nhau đưa vào cùng Scheduler sẽ cạnh tranh trên thread đó và được thực thi tuần tự theo cơ chế lên lịch. `single` thích hợp cho:

- Công việc nhẹ, ngắn, muốn tập trung xử lý trên một thread.
- Chuỗi callback cần tránh chạy đồng thời trên nhiều worker tại đoạn được lập lịch.
- Các thao tác ghi nhận trạng thái đơn giản mà đã có thiết kế tuần tự và thời lượng xử lý ngắn.

~~~java
Mono<String> report = Mono.fromSupplier(() ->
    "thread=" + Thread.currentThread().getName()
).subscribeOn(Schedulers.single());
~~~

Khi đăng ký, `fromSupplier` chạy trên worker `single`; tên thread mặc định thường có tiền tố `single-` (ví dụ `single-1`). **Tên số thứ tự không phải hợp đồng ứng dụng**, không dùng để quyết định nghiệp vụ.

Vì Scheduler này dùng chung **một** thread, nếu một tác vụ chặn thread lâu, những tác vụ khác dùng `single` phải chờ. Vì thế **không** đặt JDBC blocking, `Thread.sleep` dài, `block()` hoặc công việc CPU rất nặng lên `Schedulers.single()`.

### 3.2. Shared `single()` khác `newSingle(...)`

~~~java
Scheduler shared = Schedulers.single();
Scheduler dedicated = Schedulers.newSingle("audit");
~~~

- `Schedulers.single()` là một instance dùng chung do Reactor quản lý, không tạo thread riêng mỗi lần gọi factory.
- `Schedulers.newSingle("audit")` tạo Scheduler độc lập dành cho phạm vi ứng dụng cụ thể. Người tạo **phải quản lý vòng đời** và gọi `dedicated.dispose()` khi không dùng nữa; không tạo mới per request mà quên dispose.
- Sử dụng chung `single()` không tạo sự bảo đảm rằng mọi cập nhật trạng thái ứng dụng đều an toàn. Các thread ngoài Scheduler vẫn có thể truy cập trạng thái; trạng thái dùng chung vẫn cần quy ước đồng bộ hóa/ownership đúng.

## 4. `Schedulers.parallel()`: pool hữu hạn cho tác vụ nhanh, không blocking

### 4.1. Đặc tính

`Schedulers.parallel()` là Scheduler dùng chung với nhóm worker cố định, mặc định số worker dựa trên số processor được JVM báo cáo (thường bằng `Runtime.getRuntime().availableProcessors()`; có thể cấu hình bằng property của Reactor). Nó được tối ưu cho công việc nhanh, có tính tính toán và **không chặn thread**.

~~~java
Mono<Integer> result = Mono.fromSupplier(() -> 12 * 12)
    .subscribeOn(Schedulers.parallel());
~~~

Khi đăng ký, phép tính được lên lịch trên một worker của `parallel`. Nhiều subscription hoặc rail độc lập **có thể** dùng các worker khác nhau, tùy số processor và Scheduler thực tế.

### 4.2. Không phải cứ `publishOn(parallel())` là mọi item song song

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::calculate)
    .subscribe();
~~~

Đây là **đoạn minh họa nằm trong một instance có phương thức `calculate`**, không phải chương trình Java độc lập. Một `publishOn` thường chọn **một worker cho một subscription** và tuần tự đưa tín hiệu downstream qua worker đó. Do đó một chuỗi `map` sau `publishOn(parallel())` **không tự động chia 100 phần tử ra nhiều CPU core**.

Muốn chia dữ liệu thành các rail có khả năng xử lý đồng thời:

~~~java
Flux<Integer> squared = Flux.range(1, 100)
    .parallel(4)                      // Chia thành 4 rail
    .runOn(Schedulers.parallel())     // Lên lịch worker cho mỗi rail
    .map(i -> i * i)
    .sequential();                    // Ghép các rail lại thành Flux
~~~

`parallel(4)` tự nó chỉ tạo `ParallelFlux`, **chưa đủ** để đảm bảo nhiều thread; `runOn` mới gắn Scheduler cho các rail. Và ngay cả khi khai báo 4 rail, số thread thực tế vẫn phụ thuộc worker pool, tài nguyên CPU và tải lúc đó. Các kết quả ghép qua `sequential()` **không nên được giả định có thứ tự đầu vào trong mọi trường hợp xử lý đồng thời** nếu ứng dụng phụ thuộc vào thứ tự; cần thiết kế/kiểm tra lại yêu cầu ordering.

Không được đặt tác vụ I/O đồng bộ dài trong `Schedulers.parallel()`: blocking sẽ chiếm worker CPU và ảnh hưởng các luồng khác.

### 4.3. `parallel()` và `newParallel(...)`

`Schedulers.parallel()` là pool dùng chung. `Schedulers.newParallel("compute", 4)` tạo pool riêng tối đa 4 worker cho một subsystem nếu thật sự cần tách tài nguyên; phải `dispose()` pool tự tạo khi kết thúc vòng đời. Thêm thread tùy tiện không làm máy có thêm CPU core; nếu công việc thuần CPU đã dùng hết core, tăng concurrency có thể chỉ thêm chuyển ngữ cảnh.

## 5. `Schedulers.boundedElastic()`: xử lý phần blocking một cách có giới hạn

### 5.1. Khi nào sử dụng?

`boundedElastic` phục vụ tác vụ tương đối dài, đặc biệt **API không có lựa chọn reactive/non-blocking**:

- Thư viện JDBC hoặc SDK legacy đồng bộ.
- Đọc file bằng API blocking khi không có giải pháp asynchronous phù hợp.
- Gọi mã đồng bộ được cung cấp bởi một thư viện bên ngoài.
- Thực hiện công việc chờ I/O mà chưa thể thay thế bằng driver/reactive client.

Cách ghép chuẩn là **bọc lời gọi blocking để nó thực sự chỉ chạy lúc subscribe**, rồi dùng `subscribeOn(Schedulers.boundedElastic())`:

~~~java
Mono<Customer> customerMono = Mono
    .fromCallable(() -> legacyJdbcRepository.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **đoạn minh họa trong ứng dụng có `Customer`, `legacyJdbcRepository` và `customerId`**, không phải chương trình độc lập. `fromCallable` trì hoãn gọi repository đến lúc có subscription; `subscribeOn` chuyển **công việc nguồn** sang pool boundedElastic.

**Sai mẫu phổ biến**:

~~~java
Mono<Customer> wrong = Mono
    .just(legacyJdbcRepository.findById(customerId))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Tại đây Java gọi `findById` **ngay khi xây dựng Publisher**, trước khi Scheduler có cơ hội dời công việc. Nếu dòng này chạy trên event loop thì vẫn có thể block event loop. Hãy dùng `fromCallable` hoặc `defer` đúng lúc.

### 5.2. Vì sao gọi là bounded + elastic?

Với implementation platform-thread thông thường, `boundedElastic` mở/reuse worker threads linh hoạt trong **giới hạn**. Theo mặc định trong Reactor 3.x hiện hành:

- Trần số backing thread thường là `10 × số processor` khả dụng; có thể thay đổi bằng `reactor.schedulers.defaultBoundedElasticSize`.
- Khi các thread đang bận, công việc được xếp chờ; mặc định giới hạn queue là khoảng **100.000 tác vụ cho mỗi backing thread**, không phải một cam kết queue vô hạn. Có thể cấu hình bằng `reactor.schedulers.defaultBoundedElasticQueueSize`.
- Worker thread nhàn rỗi của implementation platform-thread có thể được thu hồi sau khoảng 60 giây.
- Nếu vượt giới hạn lập lịch, Reactor có thể từ chối thêm task (`RejectedExecutionException` hoặc lỗi lập lịch tương ứng).

Những mặc định này là **chi tiết cấu hình và implementation**, không nên hard-code thành kỳ vọng nghiệp vụ. Khi chạy thực tế, tra phiên bản Reactor, JVM, số processor và property đã đặt.

Lưu ý quan trọng: `boundedElastic` **không biến JDBC thành giao tiếp non-blocking**. Thread vẫn bị chặn trong lúc truy vấn; Scheduler chỉ cách ly việc chặn khỏi các thread cần duy trì phản hồi nhanh. Connection pool và giới hạn database vẫn là ràng buộc độc lập. Nếu đã dùng R2DBC hay `WebClient` non-blocking, đừng bọc chúng vào boundedElastic chỉ vì chúng trả `Mono`.

### 5.3. Java 21 virtual threads là chế độ **tùy chọn**

Từ Reactor 3.6.0, ứng dụng chạy **Java 21+** có thể bật một implementation của shared `boundedElastic` dùng **virtual thread mới cho mỗi task**, qua JVM system property:

~~~text
-Dreactor.schedulers.defaultBoundedElasticOnVirtualThreads=true
~~~

Chế độ này chỉ có hiệu lực khi môi trường và cấu hình hỗ trợ, mặc định không được bật; không áp dụng cho chương trình Java 17 ở phần thực hành. Virtual threads giúp giảm chi phí giữ platform thread cho nhiều tác vụ blocking, nhưng **không xóa giới hạn concurrency, queue, I/O, số kết nối hay deadline**. Với chế độ virtual thread, không có idle platform-thread pool kiểu truyền thống của boundedElastic; mỗi task được chạy trên một virtual thread mới theo cơ chế giới hạn của implementation.

### 5.4. `boundedElastic()` cũng là shared Scheduler

`Schedulers.boundedElastic()` trả về Scheduler dùng chung do Reactor quản lý. Có thể tạo Scheduler chuyên dụng nếu có yêu cầu cách ly tài nguyên và trần riêng:

~~~java
Scheduler legacyPool = Schedulers.newBoundedElastic(
    8,       // Số backing thread tối đa
    100,     // Số task đợi tối đa trên mỗi backing thread
    "legacy" // Tiền tố tên thread
);
// Sử dụng legacyPool cho các nguồn cần cách ly.
// Khi ứng dụng dừng: legacyPool.dispose().
~~~

Chỉ tạo pool riêng khi có lý do vận hành rõ ràng; tạo nhiều pool lớn có thể làm mất mục đích kiểm soát tổng số thread.

## 6. Bảng quyết định: chọn loại Scheduler nào?

| Câu hỏi | `single()` | `parallel()` | `boundedElastic()` |
| --- | --- | --- | --- |
| Số thread | Một thread **dùng chung** | Pool cố định, khoảng số CPU core theo mặc định | Co giãn có trần thread và queue |
| Công việc phù hợp | Ngắn, cần xử lý tập trung/tuần tự | Tính toán nhanh, không blocking | Tích hợp blocking I/O/legacy |
| Có nên gọi `Thread.sleep`, `block()`, JDBC blocking? | **Không** | **Không** | Có thể dùng khi cần, nhưng vẫn tốn tài nguyên |
| Nhiều subscription có thể chia thread? | Không, chung một thread | Có | Có, tới giới hạn |
| Có bảo đảm các item trong một Flux tự chạy đồng thời? | Không | Không, cần thiết kế rail/flatMap phù hợp | Không |
| Rủi ro khi quá tải | Một task chậm làm mọi task khác chờ | CPU worker bị chiếm; latency tăng | Trần thread/queue, độ trễ hoặc từ chối task |
| Cách tạo mới | `newSingle(name)` | `newParallel(name, n)` | `newBoundedElastic(cap, queueCap, name)` |

**Nguyên tắc thực hành:** ưu tiên pipeline thật sự non-blocking; chỉ chuyển thread khi có lý do. Nếu bắt buộc dùng blocking API, cô lập lời gọi đó vào boundedElastic; không cố “chữa” bằng single/parallel.

## 7. `subscribeOn` và `publishOn`: Scheduler áp dụng ở đoạn nào?

Ba Scheduler ở trên là **nơi chạy công việc**. Hai toán tử quan trọng chọn cách kết nối nơi chạy đó với pipeline.

### 7.1. `subscribeOn(scheduler)`: dịch chuyển hoạt động subscription và nguồn

~~~java
Mono<String> source = Mono.fromCallable(() -> {
    return "source thread=" + Thread.currentThread().getName();
}).subscribeOn(Schedulers.boundedElastic());
~~~

Với nguồn kiểu `fromCallable`, lời gọi nguồn được thực hiện trên Scheduler được chọn, phù hợp để chuyển blocking API. Thường đặt `subscribeOn` gần nguồn để người đọc thấy rõ phần cần chạy ở đâu. Nó ảnh hưởng luồng đăng ký ngược về nguồn và tác vụ phát tín hiệu của nguồn, khác với `publishOn`.

Sự có mặt của `subscribeOn` **không tạo nhiều lần subscribe** và không đổi một nguồn thành hot Publisher. Nếu thêm nhiều `subscribeOn` trong cùng chuỗi, chỉ một vị trí hiệu quả trực tiếp điều khiển subscription về source và có thể phát sinh chuyển thread thừa; tránh xếp nhiều `subscribeOn` không cần thiết.

### 7.2. `publishOn(scheduler)`: đổi nơi xử lý các tín hiệu downstream

~~~java
Flux.range(1, 3)
    .doOnNext(i -> logThread("before", i))
    .publishOn(Schedulers.parallel())
    .doOnNext(i -> logThread("after", i));
~~~

`logThread` là hàm minh họa do ứng dụng tự định nghĩa. Trước `publishOn`, các hook chạy theo context cũ; sau đó các hook downstream được chuyển sang worker của `parallel()`, đến khi gặp boundary khác.

Một `publishOn` giữ các tín hiệu `onNext` đến **một Subscriber** theo thứ tự tuần tự theo yêu cầu Reactive Streams. `publishOn(parallel())` không mang ý nghĩa “mỗi `onNext` một thread”. Nó thường có hàng đợi/prefetch nội bộ, vì vậy phải xem cả backpressure và bộ nhớ khi pipeline có tốc độ sản xuất/tiêu thụ khác nhau.

### 7.3. Kết hợp hai boundary

~~~text
subscribe() ở thread caller
        |
        v
Mono.fromCallable(...) -- subscribeOn(boundedElastic)
        |                   (nguồn chạy ở boundedElastic)
        v
map(...)                 -- xử lý ở boundedElastic
        |
        v
publishOn(parallel)
        |                   (chuyển tín hiệu xuống worker parallel)
        v
map(...)                 -- xử lý ở parallel
        |
        v
subscriber               -- nhận tín hiệu downstream
~~~

Ví dụ:

~~~java
Mono<String> pipeline = Mono.fromCallable(() -> {
        String raw = blockingLegacyCall(); // Trên boundedElastic
        return raw;
    })
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim)
    .publishOn(Schedulers.parallel())
    .map(String::toUpperCase);
~~~

`blockingLegacyCall` là phương thức minh họa, không có trong chương trình độc lập. `publishOn(parallel)` không khiến source blocking chuyển sang parallel; nó chỉ đổi vị trí chạy *các toán tử sau nó*. **Đặt `publishOn(parallel())` rồi để một `map` phía sau thực hiện blocking I/O là sai mục tiêu.**

### 7.4. `publishOn` khác `flatMap` có `subscribeOn` ở mỗi nguồn con

~~~java
Flux<Integer> results = Flux.range(1, 5)
    .flatMap(i ->
        Mono.fromCallable(() -> blockingService(i))
            .subscribeOn(Schedulers.boundedElastic()),
        3 // Số nguồn con có thể được đăng ký đồng thời tối đa
    );
~~~

Đây là đoạn minh họa với `blockingService` do ứng dụng cung cấp. Cấu trúc này có thể cho phép tối đa 3 thao tác blocking độc lập đang được xử lý cùng lúc (theo semantics concurrency của `flatMap` và hành vi nguồn), thay vì chỉ thay đổi một worker cho toàn bộ chuỗi. Kết quả của `flatMap` có thể **không giữ nguyên thứ tự đầu vào**; nếu cần thứ tự, cân nhắc `flatMapSequential` hoặc `concatMap` tùy yêu cầu và thông lượng.

Dù có `concurrency=3`, số việc thực sự chạy song song vẫn chịu giới hạn worker, connection pool, tài nguyên và scheduler. Không gán một số concurrency lớn chỉ để hy vọng tăng throughput.

## 8. Ví dụ Java 17+ độc lập và stdout ổn định

Ví dụ này dùng **Reactor Core 3.8.8** và Java 17. Ta quan sát **loại thread bằng tên prefix** thay vì in số thứ tự thread. Các shared Scheduler mặc định của Reactor đặt prefix như `single-`, `parallel-` và `boundedElastic-`; kiểm tra prefix giúp đầu ra không phụ thuộc chỉ số worker của từng máy. Các test sử dụng `block()` **chỉ từ thread gọi `main`** để đợi hoàn tất, không gọi blocking Reactor API trong worker `single`/`parallel`.

Cấu trúc:

~~~text
reactor-schedulers-demo/
├── pom.xml
└── src/main/java/example/SchedulerChoicesDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-schedulers-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SchedulerChoicesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/SchedulerChoicesDemo.java`**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class SchedulerChoicesDemo {

    private static boolean onThreadPrefix(String prefix) {
        return Thread.currentThread().getName().startsWith(prefix);
    }

    public static void main(String[] args) {
        // Chỉ cần một thread dùng chung để chạy supplier.
        Boolean single = Mono
            .fromSupplier(() -> onThreadPrefix("single-"))
            .subscribeOn(Schedulers.single())
            .block();
        System.out.println("single worker=" + single);

        // Tác vụ tính toán ngắn trên pool parallel.
        Boolean parallel = Mono
            .fromSupplier(() -> onThreadPrefix("parallel-"))
            .subscribeOn(Schedulers.parallel())
            .block();
        System.out.println("parallel worker=" + parallel);

        // Giả lập lời gọi đồng bộ chờ I/O bằng Thread.sleep.
        // Callable được lên lịch trên boundedElastic.
        Boolean elastic = Mono
            .fromCallable(() -> {
                Thread.sleep(20);
                return onThreadPrefix("boundedElastic-");
            })
            .subscribeOn(Schedulers.boundedElastic())
            .block();
        System.out.println("boundedElastic worker=" + elastic);

        // subscribeOn tác động tới source, publishOn chuyển downstream.
        String boundary = Mono
            .fromSupplier(() ->
                "source single=" + onThreadPrefix("single-"))
            .subscribeOn(Schedulers.single())
            .publishOn(Schedulers.parallel())
            .map(value ->
                value + ", downstream parallel=" + onThreadPrefix("parallel-"))
            .block();
        System.out.println(boundary);

        // Chia rail cho xử lý tính toán độc lập.
        // Chỉ in số phần tử vì lịch chạy/ordering có thể thay đổi.
        Long count = Flux.range(1, 6)
            .parallel(2)
            .runOn(Schedulers.parallel())
            .map(i -> i * i)
            .sequential()
            .count()
            .block();
        System.out.println("computed count=" + count);
    }
}
~~~

Từ thư mục `reactor-schedulers-demo`, chạy:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến với các shared Scheduler mặc định, chưa cấu hình tên thread hoặc thay Scheduler factory:**

~~~text
single worker=true
parallel worker=true
boundedElastic worker=true
source single=true, downstream parallel=true
computed count=6
~~~

Giải thích:

1. `Mono.fromSupplier` ở ca 1 chỉ thực thi khi được subscribe, và `subscribeOn(single)` đặt nó lên worker `single`.
2. `Mono.fromSupplier` ở ca 2 được đưa lên worker `parallel`. Điều này chưa chứng minh nhiều item xử lý song song; nó chỉ chứng minh vị trí thực thi công việc.
3. Ca 3 sử dụng `Mono.fromCallable`, có thể ném checked exception, nên viết `Thread.sleep` hợp lệ mà không cần `try/catch` thủ công. Trong ứng dụng thật, `Thread.sleep` chỉ là mô phỏng cho công việc blocking, không phải cách thực hiện non-blocking I/O.
4. `subscribeOn(single)` điều khiển nơi source phát, còn `publishOn(parallel)` đổi thread xử lý `map` phía sau.
5. `parallel(2).runOn(parallel).sequential()` xử lý 6 item qua hai rail. Ta chỉ in số phần tử đầu ra để không phụ thuộc timing và thứ tự lịch chạy. Một máy chỉ có một processor được cấp phát có thể chưa cho ra lợi ích chạy đồng thời dù yêu cầu hai rail.

**Giới hạn của ví dụ:** Prefix thread là dấu hiệu quan sát trong cấu hình mặc định, không phải API ổn định để điều khiển nghiệp vụ. `block()` dùng trong hàm `main` phục vụ demo; không đưa kiểu chờ này vào thread WebFlux event loop.

## 9. Lỗi blocking trên `single` và `parallel`

Reactor đánh dấu các thread mặc định của `Schedulers.single()` và `Schedulers.parallel()` là **non-blocking only**. Gọi các API Reactor chặn như `block()`, `blockFirst()`, `blockLast()` hoặc iterator blocking `toIterable()/toStream()` trên các thread đó có thể ném `IllegalStateException` với thông điệp liên quan “blocking is not supported”.

Đoạn sau là **ví dụ phản diện**, không được chạy như cách xử lý đúng:

~~~java
Mono.just("outer")
    .publishOn(Schedulers.parallel())
    .map(value -> Mono.just("inner").block()) // SAI
    .subscribe();
~~~

`map` chạy trên worker `parallel` và cố gọi `block()` bên trong. Điều đó xung đột với chính sách thread non-blocking. Nếu muốn kết hợp hai `Mono`, dùng `flatMap`/`zip`:

~~~java
Mono<String> correct = Mono.just("outer")
    .publishOn(Schedulers.parallel())
    .flatMap(value ->
        Mono.just("inner").map(inner -> value + "-" + inner));
~~~

Cần phân biệt **blocking do Reactor chủ động phát hiện** (`block()` trên NonBlocking thread) với **blocking của API ngoài** (JDBC, `Thread.sleep`). Các API ngoài có thể không ném lỗi ngay dù làm tắc nghẽn worker. Vì vậy “không thấy exception” không phải bằng chứng đã non-blocking.

## 10. Tích hợp với Spring WebFlux

### 10.1. Bảo vệ event loop khi buộc phải dùng thư viện legacy

Với ứng dụng WebFlux chạy trên Reactor Netty, nhiều callback của HTTP được thực thi trên các thread event loop. Không được thực hiện I/O blocking lâu trên đó. Khi thiếu driver reactive, có thể đóng gói lời gọi đồng bộ trong `fromCallable` và `subscribeOn(boundedElastic)`:

~~~java
@Service
public class CustomerService {
    private final LegacyCustomerClient legacyClient;

    public CustomerService(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    public Mono<Customer> load(String id) {
        return Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đây là **đoạn minh họa trong ứng dụng Spring**: `LegacyCustomerClient` và `Customer` là class nghiệp vụ giả định cần có implementation. Nếu `findById` trả về `null`, `Mono.fromCallable` hoàn tất rỗng; downstream cần quyết định có trả 404 bằng `switchIfEmpty` hay không.

Một controller WebFlux nên **trả về Publisher** để framework đăng ký và xử lý lifecycle:

~~~java
@GetMapping("/customers/{id}")
public Mono<Customer> getCustomer(@PathVariable String id) {
    return service.load(id);
}
~~~

Không tự `subscribe()` trong handler để “kích hoạt” công việc rồi trả response độc lập, vì điều đó tách quản lý lỗi, cancellation và thời điểm hoàn tất khỏi HTTP. Đây cũng không phải lý do để đặt `Schedulers.boundedElastic()` cho mọi endpoint.

### 10.2. Khi đã có API non-blocking thì giữ non-blocking

~~~java
Mono<Customer> customer =
    reactiveRepository.findById(id)
        .map(this::enrich);
~~~

Nếu repository và `enrich` không blocking, thêm `subscribeOn(boundedElastic)` thường không đem lại ích lợi, chỉ tăng scheduling/queue/context switch. `WebClient`, R2DBC và các driver non-blocking có mô hình scheduling riêng; không làm chúng “reactive hơn” bằng cách chuyển vô tội vạ.

Với mã xử lý CPU độc lập, có thể cân nhắc `Schedulers.parallel()` hoặc chia rail, nhưng cần xác định throughput, CPU, thứ tự dữ liệu và giới hạn concurrency bằng đo đạc thực tế.

### 10.3. ThreadLocal, transaction và context không phải một thứ

Chuyển thread bằng `subscribeOn`/`publishOn` có thể khiến `ThreadLocal` truyền thống, MDC logging, security context hoặc transaction đồng bộ không còn hiện diện ở nơi bạn tưởng. Reactor có `Context` gắn với subscription và cơ chế context propagation (tùy tích hợp) để truyền ngữ cảnh. Không tự chia sẻ một transaction/thread-bound resource qua nhiều worker chỉ vì Publisher cùng được xây từ một method.

Trong Spring reactive, transaction management reactive sử dụng context của subscription; đồng bộ JDBC/transaction dùng ThreadLocal cần thiết kế riêng. Nếu bài toán cần transaction xuyên nhiều thao tác, Scheduler không thể thay thế chính sách transaction.

## 11. Quá tải, cancellation và tài nguyên

Một Scheduler có thể nhận nhiều tác vụ chờ; điều đó **không miễn trừ backpressure** hoặc chính sách hạn chế concurrency. Một số nguyên tắc:

1. **Giới hạn đồng thời**: `flatMap(..., concurrency)`, connection pool, thread cap và queue cap cần được chọn theo tài nguyên thực; không tăng chúng đồng loạt.
2. **Giám sát latency/queue**: boundedElastic có trần, tác vụ có thể phải đợi lâu; nếu queue cạn, scheduler có thể từ chối. Quan sát các chỉ số tương ứng bằng Micrometer/Reactor khi tích hợp.
3. **Timeout/cancel**: `timeout` hoặc cancellation downstream không đảm bảo tự ngắt mọi blocking API đang chạy. Lời gọi legacy cần hỗ trợ timeout/interrupt hoặc cơ chế hủy phù hợp. `doFinally` có thể quan sát `CANCEL`, `ON_ERROR`, `ON_COMPLETE`.
4. **Tránh block lồng nhau**: Nếu dùng một worker để chờ kết quả của công việc cần chính worker đó thực hiện, có thể tạo deadlock/starvation, dù Scheduler cho phép blocking.
5. **Quản lý lifecycle**: các shared Scheduler `single()/parallel()/boundedElastic()` do Reactor quản lý; với `newSingle`/`newParallel`/`newBoundedElastic`, chủ sở hữu phải `dispose()` vào đúng giai đoạn ứng dụng dừng. Không tạo pool mới cho mỗi HTTP request.
6. **Không dựa vào tên thread** để lưu state, đo concurrency hoặc tạo correlation ID. Thread có thể được tái sử dụng và task có thể đổi worker qua nhiều async boundary.

## 12. Bài tập kiểm tra nhanh

1. `Flux.range(1, 10).publishOn(Schedulers.parallel()).map(...)` có đảm bảo 10 phần tử chạy trên 10 thread không? **Không**. Một `publishOn` thường dùng một worker cho luồng tín hiệu của subscriber đó. Muốn chia rails, dùng `parallel().runOn(...)` hoặc fan-out có kiểm soát.
2. Cần gọi JDBC đồng bộ mà không block HTTP event loop, dùng scheduler nào? **`boundedElastic()`**, với `Mono.fromCallable(() -> jdbcCall()).subscribeOn(...)`.
3. `Mono.just(blockingCall()).subscribeOn(Schedulers.boundedElastic())` có dời `blockingCall` sang boundedElastic không? **Không**: Java đánh giá lời gọi ngay khi assembly.
4. `Schedulers.single()` có tạo một thread mới cho mỗi lần gọi không? **Không**, đây là Scheduler chung. Muốn scheduler độc lập, tạo `newSingle(...)` và quản lý vòng đời.
5. `Schedulers.parallel()` có tối ưu để giữ thread chờ JDBC hoặc `Thread.sleep` không? **Không**, nó dành cho tác vụ nhanh, không blocking.
6. Vì sao `block()` trong `map` chạy trên `parallel()` có thể gây `IllegalStateException`? Vì thread này được đánh dấu `NonBlocking`, Reactor ngăn gọi API blocking trên đó.
7. `boundedElastic` có được phép chạy vô số thread và task chờ không? **Không**, giới hạn thread/queue có thể dẫn đến hàng đợi và lỗi khi quá tải.
8. Nếu đã dùng WebClient non-blocking, có cần bọc mọi cuộc gọi vào `boundedElastic()` không? **Không**. Chỉ dời khi có công việc blocking thực sự.
9. Để xử lý 4 phần tử bằng nhiều rail, `parallel(4)` đủ chưa? **Chưa**, cần gắn `runOn(Schedulers.parallel())` hoặc nguồn có tính scheduling thích hợp, và vẫn tùy tài nguyên thực tế.
10. Lỗi liên quan `ThreadLocal` sau `publishOn` có thể xử lý đơn giản bằng cách giữ trạng thái ứng dụng trên đúng một thread không? **Không nên**. Hãy dùng mô hình context propagation/`Reactor Context` và chính sách quản lý dữ liệu rõ ràng.
11. Nếu muốn downstream chạy trên parallel nhưng phần gọi legacy JDBC vẫn ở boundedElastic, đặt Scheduler ở đâu? **`subscribeOn(boundedElastic)` gần `fromCallable(jdbcCall)` và `publishOn(parallel)` sau phần blocking**.
12. Có thể thay thế thiết kế timeout/connection pool bằng cách tăng thread cap của boundedElastic không? **Không**; chặn thread và giới hạn hạ tầng phải được giải quyết ở từng tầng.

## 13. Tổng kết lựa chọn và tài liệu chính thức

- `Schedulers.single()`: một thread chung cho công việc ngắn, tập trung; không đặt blocking lâu.
- `Schedulers.parallel()`: pool hữu hạn tối ưu công việc tính toán nhanh/non-blocking; **không tự song song hóa item** chỉ nhờ `publishOn`.
- `Schedulers.boundedElastic()`: môi trường có trần để cách ly công việc blocking không thể tránh; không biến legacy I/O thành non-blocking.
- `subscribeOn` dời subscription và nguồn; `publishOn` dời phần xử lý downstream; cả hai tạo context theo cách khác nhau.
- Dùng `Flux.parallel().runOn(...)` hay `flatMap` có concurrency khi thực sự cần xử lý nhiều phần việc độc lập; đo hiệu năng và bảo toàn ordering nếu nghiệp vụ yêu cầu.

Tài liệu tra cứu:

1. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): các Scheduler, `publishOn`, `subscribeOn`, Java 21 virtual-thread boundedElastic.
2. [Project Reactor API — Schedulers](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Schedulers.html): factory, cấu hình mặc định và quy tắc tạo Scheduler dùng chung/độc lập.
3. [Project Reactor Reference — Parallelizing Work with ParallelFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-parallelizing-parralelflux.html): `parallel`, `runOn`, `sequential`.
4. [Project Reactor Reference — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): `fromCallable` và `subscribeOn(boundedElastic)`.
5. [Project Reactor API — Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) và [Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): ngữ nghĩa Publisher và tác động của các toán tử lên thread.