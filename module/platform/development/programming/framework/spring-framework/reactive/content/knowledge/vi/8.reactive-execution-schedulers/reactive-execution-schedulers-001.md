# Reactor không tự tạo luồng mới cho mọi Mono hoặc Flux

## 1. Ý tưởng cần nắm

Trong **Spring WebFlux**, `Mono<T>` biểu diễn một kết quả có **0 hoặc 1 phần tử**, còn `Flux<T>` biểu diễn **0 đến nhiều phần tử**. Hai kiểu này mô tả **luồng tín hiệu và cách xử lý bất đồng bộ**, nhưng **không đồng nghĩa với việc Reactor tạo một thread Java mới cho mỗi `Mono`, mỗi `Flux` hoặc mỗi request**.

Một chuỗi operator đơn giản có thể chạy **đồng bộ hoàn toàn trên chính thread gọi `subscribe()`**. Thread chỉ thay đổi khi có nguồn bất đồng bộ, toán tử dùng scheduler, hoặc người lập trình chỉ định chuyển ngữ cảnh bằng các cơ chế như `subscribeOn` và `publishOn`.

Điều này quan trọng vì nhầm lẫn giữa *publisher*, *subscription*, *thread* và *scheduler* dẫn tới những lỗi phổ biến: cho rằng `Mono.fromCallable` tự chạy trên worker, chặn event-loop bằng `Thread.sleep` hoặc JDBC, tạo một scheduler cho mỗi request, hay giả định mọi phần của pipeline đều chạy cùng một thread.

**Bốn khái niệm cần phân biệt:**

| Khái niệm | Ý nghĩa | Có đồng nghĩa với một thread mới không? |
| --- | --- | --- |
| `Mono<T>`, `Flux<T>` | Publisher mô tả nguồn và chuỗi xử lý tín hiệu | **Không** |
| Subscription | Một lần subscriber đăng ký vào publisher; khởi động luồng xử lý khi có demand | **Không** |
| Java thread | Luồng thực thi mã Java tại một thời điểm | Một publisher có thể chạy trên thread hiện có hoặc chuyển qua nhiều thread |
| Reactor `Scheduler` | Cơ chế bố trí công việc trên execution context (thread hiện tại, thread pool, v.v.) | Không nhất thiết tạo thread riêng cho từng publisher |

Một `Flux` có thể phát một triệu phần tử **tuần tự trên một thread**, còn một `Mono` duy nhất có thể trải qua **nhiều thread** vì các bước I/O hoặc `publishOn`. Số lượng phần tử và số lượng thread là hai đại lượng khác nhau.

## 2. Pipeline được khai báo trước, thực thi khi có subscription

Hầu hết operator Reactor là **lazy**: chúng mô tả chuỗi biến đổi, và phần xử lý dữ liệu bắt đầu khi có subscriber. Tuy nhiên, không phải **mọi biểu thức khi dựng publisher** đều lazy; đối số đưa cho `Mono.just(...)` được tính theo quy tắc Java tại thời điểm gọi phương thức.

Ví dụ:

~~~java
// Đoạn minh họa, cần reactor-core và import Mono.
Mono<Integer> numbers = Mono.just(3)
    .map(n -> n * 2)
    .filter(n -> n > 0);

// Chưa có onNext để xử lý ở các operator phía trên.
// Khi subscribe, nguồn just phát 3, map thành 6, filter giữ lại 6:
numbers.subscribe(System.out::println);
~~~

Nếu gọi `subscribe()` từ thread `main`, với `Mono.just` và các operator đồng bộ này, `map`, `filter` và consumer thường thực thi **trên chính thread `main`**. Reactor không khởi chạy `new Thread(...)` cho từng bước.

Các lệnh sau dễ bị hiểu sai:

~~~java
Mono<String> a = Mono.fromCallable(() -> blockingRead());
Mono<String> b = Mono.just(blockingRead());
~~~

Đây là đoạn minh họa với phương thức `blockingRead()` giả định:

- Với `a`, lời gọi `blockingRead()` được **hoãn đến lúc subscription**; nhưng nếu không có `subscribeOn` hay scheduler khác, nó vẫn có thể **chặn ngay thread đang subscribe**.
- Với `b`, Java gọi `blockingRead()` **ngay lúc xây dựng `Mono.just(...)`**, trước cả khi có subscriber.
- Cả hai đều **không tự tạo thread mới** chỉ vì kết quả được bọc trong `Mono`.

Muốn cô lập một thao tác blocking, cần một quyết định điều phối rõ ràng; phần sau sử dụng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

## 3. Quy tắc mặc định: nguồn đồng bộ chạy trên thread đang subscribe

Với nguồn đồng bộ như `Flux.just`, `Flux.range`, `Mono.just` hoặc `Mono.fromSupplier`, và các operator không chuyển scheduler (`map`, `filter`, `doOnNext`), tín hiệu thường được phát và xử lý **trên thread gọi `subscribe`**.

~~~text
thread gọi subscribe()
    │
    ▼
Flux.range(1, 3)
    │   onNext(1), onNext(2), onNext(3)
    ▼
map(n -> n * 10)
    │   10, 20, 30
    ▼
filter(n -> n >= 20)
    │   20, 30
    ▼
Subscriber.onNext(20), onNext(30), onComplete
    └── Cùng thread nếu không có ranh giới async/scheduler
~~~

`Flux.range(1, 3)` không tạo ba thread; chỉ phát **ba phần tử**. Toán tử `map` cũng không tự biến mỗi phần tử thành một tác vụ độc lập.

Tuy nhiên, không thể phát biểu rằng “**mọi** chuỗi không có `publishOn` đều chạy trên thread subscribe”: một **nguồn đã bất đồng bộ** có thể phát callback trên thread riêng của thư viện ngoài, Reactor Netty hoặc scheduler mặc định. Ví dụ `Flux.interval`, `Mono.delay`, một nguồn `WebClient` hoặc tín hiệu `Mono.fromFuture` có thể hoàn tất trên thread khác. Vì vậy, kết luận đúng là: **Reactor không tự cấp một thread mới cho mỗi Mono/Flux; execution context phụ thuộc vào nguồn, operator và scheduler**.

## 4. `publishOn`: đổi thread xử lý các tín hiệu ở phía sau

`publishOn(scheduler)` đặt một ranh giới để **phát lại các tín hiệu downstream** trên worker của scheduler chỉ định. Các operator trước nó vẫn chạy ở ngữ cảnh upstream hiện tại; operator sau nó thường chạy trên worker đã chọn **cho đến khi một nguồn/operator khác chuyển ngữ cảnh tiếp**.

~~~java
// Ví dụ minh họa, cần import Flux và Schedulers.
Flux.range(1, 3)
    .map(n -> n * 10)                 // Upstream: thread subscribe
    .publishOn(Schedulers.parallel()) // Ranh giới scheduling
    .map(n -> n + 1)                  // Downstream: worker của parallel scheduler
    .subscribe(System.out::println); // Callback theo ngữ cảnh downstream
~~~

`publishOn` **không tạo một thread cho từng phần tử**. Với một subscription theo hợp đồng Reactive Streams, các `onNext` được gửi tuần tự đến subscriber; `publishOn` chọn worker để tuần tự hóa phần tín hiệu downstream. Tên `Schedulers.parallel()` cũng **không có nghĩa** rằng ba phần tử trên tự động chạy đồng thời trên ba core.

Có thể dùng nhiều `publishOn` khi cần nhiều giai đoạn điều phối:

~~~java
// Đoạn minh họa cấu trúc; stageA/stageB cần triển khai.
flux
    .publishOn(Schedulers.parallel())
    .map(this::stageA)
    .publishOn(Schedulers.boundedElastic())
    .map(this::stageB);
~~~

Mỗi `publishOn` có chi phí lập lịch và đệm tín hiệu; không nên thêm tùy tiện cho mọi `map`. Với một tác vụ blocking, thường ưu tiên đặt việc đó ngay trong nguồn `fromCallable` và điều phối bằng `subscribeOn(boundedElastic)`, thay vì để nó vô tình block event loop trước khi gặp `publishOn`.

## 5. `subscribeOn`: điều phối quá trình subscribe và công việc nguồn

`subscribeOn(scheduler)` thay đổi **ngữ cảnh subscription đi về phía nguồn**. Với các nguồn cold đồng bộ như `Mono.fromCallable`, `Mono.fromSupplier`, `Flux.range`, điều này thường quyết định thread chạy công việc nguồn và nhiều operator đồng bộ nối theo sau.

~~~java
// Đoạn minh họa; fetchBlocking() là API blocking giả định.
Mono<String> response = Mono.fromCallable(() -> fetchBlocking())
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::trim);
~~~

Khi downstream subscribe, lệnh fetch blocking sẽ chạy trên worker của `boundedElastic`, không chiếm event-loop mà request ban đầu đang đi qua. Nếu không có ranh giới bất đồng bộ hay `publishOn` bổ sung, `map(String::trim)` cũng thường chạy ở worker đó.

**Hai quy tắc vị trí cần phân biệt:**

- `publishOn`: **vị trí trong pipeline quyết định** những operator nào nằm phía sau ranh giới chuyển thread.
- `subscribeOn`: ảnh hưởng đến quá trình subscription đi về nguồn **dù nằm ở đâu trong chuỗi**, nhưng nên đặt ngay sau nguồn cho dễ hiểu. Với nhiều `subscribeOn`, lời gọi **gần nguồn nhất** thường là lời gọi có hiệu lực chính để lập lịch subscription tới nguồn; thêm nhiều cái có thể tạo các lần chuyển thread không cần thiết.
- `publishOn` đặt sau `subscribeOn` vẫn có thể đổi thread của các toán tử phía sau nó. Một `subscribeOn` **không khóa vĩnh viễn** toàn bộ pipeline vào một thread.

So sánh bằng ký hiệu:

~~~text
Flux nguồn đồng bộ ── map(A) ── publishOn(S1) ── map(B) ── Subscriber
    thread nguồn          |          worker S1           worker S1

Flux nguồn đồng bộ ── subscribeOn(S1) ── map(A) ── Subscriber
         worker S1                 worker S1             worker S1
~~~

Sơ đồ là đường đi điển hình của nguồn đồng bộ. Với một nguồn có scheduler/nhiều callback riêng, phải dựa trên thực tế của nguồn chứ không suy luận rằng `subscribeOn` sẽ “kéo” mọi callback bất đồng bộ sang một worker duy nhất.

## 6. Các Scheduler dùng thường gặp

Reactor dùng abstraction `Scheduler` để tổ chức execution context. Nhiều scheduler có thể **chia sẻ hoặc tái sử dụng thread**, và không đồng nhất với việc gọi `new Thread` cho từng subscription.

| Scheduler | Đặc tính | Khi nào phù hợp |
| --- | --- | --- |
| `Schedulers.immediate()` | Chạy công việc **trực tiếp trên thread hiện tại** | Khi không cần đổi thread |
| `Schedulers.single()` | Scheduler dùng chung với một worker/thread đơn | Công việc cần một luồng thực thi tuần tự; hiểu rõ tác động chia sẻ |
| `Schedulers.newSingle("name")` | Tạo scheduler một thread do mình quản lý | Cần tài nguyên riêng có vòng đời rõ; **dispose** khi kết thúc |
| `Schedulers.parallel()` | Pool worker số lượng hữu hạn, chủ yếu theo số CPU | Các đoạn xử lý **CPU-bound ngắn**, không blocking |
| `Schedulers.boundedElastic()` | Nguồn worker có giới hạn, thiết kế để chứa tác vụ **blocking** cần cách ly | JDBC/SDK blocking, thao tác file hoặc legacy API đồng bộ khi chưa có lựa chọn non-blocking |
| `Schedulers.fromExecutorService(executor)` | Dùng executor do ứng dụng quản lý | Khi tích hợp cơ chế thread pool có sẵn và quản trị lifecycle |

`boundedElastic` có giới hạn số thread và hàng đợi, không phải tài nguyên vô tận. Nếu workload blocking quá lớn, nó vẫn có thể đầy, tăng latency hoặc gây cạn tài nguyên. Chọn `parallel` cho một thao tác blocking lâu sẽ chiếm worker ít ỏi vốn dành cho công việc CPU và dễ làm chậm các pipeline khác.

**Không nên tạo `Schedulers.newSingle(...)` hoặc `newParallel(...)` cho từng HTTP request**. Việc tạo scheduler tùy ý tiêu hao thread/resource. Các scheduler dùng chung thông qua `Schedulers.parallel()` và `Schedulers.boundedElastic()` thường là lựa chọn mặc định hợp lý; scheduler tự tạo phải có vòng đời ứng dụng và cleanup tương ứng.

Một số toán tử/sources tự chọn scheduler mặc định: chẳng hạn `Flux.interval(Duration)` và `Mono.delay(Duration)` sử dụng scheduler định thời của Reactor (mặc định là `Schedulers.parallel()` trong các API phổ biến). Đây là một **nguồn có yếu tố bất đồng bộ**, chứ không phải bằng chứng rằng mọi `Flux` đều tự có thread mới.

## 7. Ví dụ Java 17+ có thể chạy, output xác định

Ví dụ dưới đây làm rõ ba trường hợp: pipeline đồng bộ mặc định, `publishOn` chuyển downstream, và `subscribeOn` chuyển công việc nguồn. Để tránh lệ thuộc tên thread mà Maven gán cho `main`, chương trình ghi **`caller`** nếu đang ở đúng thread ban đầu, ngược lại ghi **`worker`**. Nó chỉ dùng một scheduler `newSingle` riêng cho demo, nên không tạo thread mới cho mỗi `Mono`.

Cấu trúc thư mục:

~~~text
reactor-thread-demo/
├── pom.xml
└── src/main/java/ReactorThreadDemo.java
~~~

File `pom.xml` (Reactor Core 3.8.8, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-thread-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/ReactorThreadDemo.java`:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ReactorThreadDemo {
    private static Thread callerThread;

    private static void where(String stage) {
        String kind = Thread.currentThread() == callerThread
                ? "caller"
                : "worker";
        System.out.println(stage + " @ " + kind);
    }

    public static void main(String[] args) {
        callerThread = Thread.currentThread();

        // A. Không có scheduler: map và consumer chạy ở caller.
        Mono.just(2)
            .map(n -> {
                where("sync map");
                return n * 3;
            })
            .doOnNext(n -> where("sync onNext"))
            .block();

        Scheduler worker = Schedulers.newSingle("lesson");
        try {
            // B. Nguồn đồng bộ ở caller; downstream qua publishOn ở worker.
            Mono.fromSupplier(() -> {
                    where("source before publishOn");
                    return 10;
                })
                .publishOn(worker)
                .doOnNext(n -> where("after publishOn"))
                .block();

            // C. subscribeOn chuyển subscription và nguồn sang worker.
            Mono.fromSupplier(() -> {
                    where("source with subscribeOn");
                    return 20;
                })
                .subscribeOn(worker)
                .doOnNext(n -> where("after subscribeOn"))
                .block();
        } finally {
            worker.dispose();
        }
    }
}
~~~

Chạy từ thư mục `reactor-thread-demo` với Maven và JDK 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ReactorThreadDemo
~~~

**Output do chương trình in** (có thể xuất hiện thêm dòng Maven theo cấu hình môi trường):

~~~text
sync map @ caller
sync onNext @ caller
source before publishOn @ caller
after publishOn @ worker
source with subscribeOn @ worker
after subscribeOn @ worker
~~~

Giải thích:

1. Ở nhánh A, `Mono.just` + `map` + `doOnNext` không có scheduler: **thread gọi `block()`/subscribe** xử lý toàn bộ dữ liệu đồng bộ.
2. Ở nhánh B, `Mono.fromSupplier` phát giá trị trên **caller**, sau đó `publishOn(worker)` chuyển phần downstream sang một worker. Nguồn **không bị chuyển về worker** chỉ vì phía sau có `publishOn`.
3. Ở nhánh C, `subscribeOn(worker)` đặt việc subscribe và thực thi nguồn đồng bộ lên worker. `doOnNext` không gặp ranh giới khác nên cũng chạy trên worker.
4. `block()` ở đây chỉ được dùng trong **ứng dụng console** để đợi demo hoàn tất và giúp output có thứ tự. Trong ứng dụng Spring WebFlux, không `block()` trên event-loop.

Thread thực tế được Reactor quản lý và có tên nội bộ; nhãn `caller/worker` giúp chứng minh vị trí tương đối. Dòng `worker.dispose()` giải phóng scheduler riêng do demo tạo.

## 8. Phân biệt bất đồng bộ, non-blocking và chạy song song

Các thuật ngữ này dễ bị đánh đồng:

- **Bất đồng bộ (asynchronous):** kết quả có thể đến sau, từ callback/event loop/scheduler khác; caller không nhất thiết đợi trực tiếp.
- **Không chặn (non-blocking):** công việc có thể tạm nhường thread trong lúc chờ I/O và tiếp tục khi có tín hiệu, tránh giữ thread chỉ để ngủ/chờ.
- **Đồng thời (concurrent):** nhiều công việc có thể tồn tại và tiến triển xen kẽ, không nhất thiết cùng lúc trên nhiều CPU.
- **Song song (parallel):** nhiều phần công việc thật sự thực hiện đồng thời trên nhiều đơn vị xử lý.
- **Reactive:** mô hình Publisher/Subscriber với tín hiệu và quản lý nhu cầu `request(n)`; **không mặc định bảo đảm** ba thuộc tính còn lại cho mọi đoạn mã.

Ví dụ `Flux.range(1, 100)` là reactive nhưng thường chạy đồng bộ. `Flux.interval(...)` có sự kiện theo thời gian và scheduler. `WebClient` thường dùng I/O bất đồng bộ; khi chờ mạng, event-loop có thể quản lý thêm nhiều kết nối. `map(this::expensiveCpuWork)` vẫn chiếm CPU trên thread đang xử lý signal; chỉ đổi type sang `Flux` không làm thuật toán nhanh hơn.

Ngay cả đoạn sau:

~~~java
Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuWork);
~~~

cũng **không tự trải 100 phần tử ra nhiều core**. Với một subscription, `publishOn` chuyển downstream sang một worker và gửi `onNext` tuần tự. Nếu có workload CPU độc lập thực sự đáng phân phối, Reactor có `parallel().runOn(Schedulers.parallel()).map(...).sequential()` hoặc cách kết hợp `flatMap` với những inner publisher được lập lịch; mỗi cách có overhead và ảnh hưởng thứ tự kết quả, nên chỉ chọn sau khi đo lường.

`flatMap` cũng không có nghĩa “tự tạo thread”: nó cho phép **nhiều inner publisher đang hoạt động đồng thời**, nhưng việc có thread thực thi nào phụ thuộc các nguồn inner và scheduler mà chúng dùng. `concatMap` duy trì xử lý theo thứ tự tuần tự, trong khi `flatMap` có thể làm thứ tự kết quả khác thứ tự nguồn.

## 9. Trên Spring WebFlux, event-loop đến từ đâu?

Khi chạy trên stack **Spring WebFlux + Reactor Netty**, server có một nhóm **event-loop thread** để tiếp nhận kết nối và xử lý I/O. Một event-loop có thể phục vụ nhiều request/kết nối khi phần lớn thời gian request đang **chờ I/O non-blocking**. Nhận một request WebFlux không đồng nghĩa server tạo một thread riêng để chạy tất cả `Mono` hoặc `Flux` của request đó.

Dòng chảy khái quát:

~~~text
HTTP client
    │
    ▼
Reactor Netty event loop
    │
    ▼
WebFlux handler / controller trả Mono hoặc Flux
    │
    ├── Các operator đồng bộ chạy trên thread phát signal
    │   (có thể là event loop hiện tại)
    │
    ├── WebClient / R2DBC non-blocking chờ I/O
    │       └── Tín hiệu kết quả tới từ event loop / driver
    │
    └── subscribeOn / publishOn (nếu cấu hình)
            └── Chuyển một phần công việc sang Scheduler worker
    │
    ▼
WebFlux ghi HTTP response khi có dữ liệu
~~~

Một hệ quả quan trọng: **đừng chặn event-loop** bằng `Thread.sleep`, chờ lock lâu, JDBC blocking, đọc file đồng bộ lớn, gọi HTTP đồng bộ hoặc `Mono.block()` trong đường xử lý request. Chỉ vài thao tác blocking có thể làm chậm nhiều request khác vì event-loop thread được chia sẻ.

Cũng không được mặc định rằng mỗi operator trong một request sẽ nhìn thấy cùng một `Thread.currentThread()` hoặc có thể truy cập `ThreadLocal` như trong servlet xử lý đồng bộ. Khi chuyển thread, context gắn với thread có thể không đi theo. Với context nghiệp vụ xuyên suốt chuỗi reactive, sử dụng **Reactor Context** và cơ chế propagation của framework, không phụ thuộc duy nhất vào `ThreadLocal`.

## 10. Tích hợp API blocking đúng cách

Nếu bắt buộc dùng một thư viện đồng bộ trong một service reactive, bọc lời gọi bằng `fromCallable` để trì hoãn đến lúc subscribe, sau đó dùng `subscribeOn(Schedulers.boundedElastic())` để cách ly thread event-loop:

~~~java
// Đoạn minh họa trong service; legacyClient và Result được triển khai ở dự án.
Mono<Result> loadLegacy(String id) {
    return Mono.fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là **cô lập blocking I/O sang pool thích hợp**, không phải “biến thư viện blocking thành API non-blocking”. Worker `boundedElastic` vẫn bị chiếm trong thời gian chờ lời gọi; thread và hàng đợi có giới hạn. Cần giới hạn concurrency, timeout, connection pool và quan sát metrics để tránh bão hòa.

So sánh với anti-pattern:

~~~java
// Sai: fetch chạy ngay tại lúc tạo Mono.just, có thể trên event-loop.
Mono<Result> wrong = Mono.just(legacyClient.fetch(id));

// Sai khi gọi trên event-loop: Mono.fromCallable không tự đổi thread.
Mono<Result> alsoWrong = Mono.fromCallable(() -> legacyClient.fetch(id));

// Phù hợp hơn nếu không có client reactive:
Mono<Result> adapted = Mono.fromCallable(() -> legacyClient.fetch(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Các đoạn này minh họa khái niệm, không phải tệp Java chạy độc lập. `Mono.fromCallable` là lazy, nhưng **lazy ≠ chạy trên thread khác**. Việc gắn `subscribeOn` đảm bảo nguồn cold đồng bộ được lập lịch trên scheduler đã chọn khi có subscription.

Với một API vốn có non-blocking thực sự như `WebClient` hoặc repository R2DBC, không cần mặc định bọc nó vào `boundedElastic`. Hãy để API bất đồng bộ phát signal theo cơ chế của nó; chỉ chuyển scheduler khi có nhu cầu thật (blocking adapter, tách giai đoạn CPU, v.v.).

## 11. Những trường hợp cần quan sát thực tế

| Hiện tượng | Kết luận đúng | Cách kiểm tra / sửa |
| --- | --- | --- |
| `Mono.just(1).map(...)` chạy trên `main` | Bình thường: nguồn và operator đồng bộ dùng thread subscribe | Thêm `doOnNext` log thread |
| `Mono.fromCallable(blockingCall)` làm request WebFlux chậm | `fromCallable` không tự có worker | Dùng `subscribeOn(boundedElastic)`, giới hạn tải |
| Sau `publishOn(parallel)`, nhiều `map` vẫn dùng một worker | `publishOn` chuyển downstream nhưng không phân chia mỗi item sang một thread | Chỉ dùng parallelization khi thật sự cần |
| `Flux.interval` phát trên thread khác mà không gọi `publishOn` | Nguồn tự có scheduler định thời | Kiểm tra tài liệu và cấu hình scheduler của nguồn |
| `subscribe()` trả về trước khi có `onNext` | Nguồn/callback bất đồng bộ nên công việc còn tiếp diễn | Trả publisher cho WebFlux; trong demo console có thể chờ bằng test/latch/`block` |
| Có nhiều request, số thread ít hơn số request | Event-loop non-blocking dùng thread chia sẻ | Theo dõi event-loop latency, I/O, CPU và pool |
| Tự tạo scheduler ở mỗi request | Phình thread/resource, khó cleanup | Dùng scheduler chia sẻ hoặc quản lý vòng đời riêng |
| `ThreadLocal` bị mất sau ranh giới async | Operator không nhất thiết chạy cùng thread | Dùng Reactor Context hoặc context propagation thích hợp |

Để quan sát, có thể tạm thêm `doOnSubscribe(s -> ...)`, `doOnNext(v -> ...)`, `doOnError`, `doFinally` hoặc `log()`. Nhớ rằng `doOnSubscribe` cho biết nơi subscription được quan sát, chưa chắc cùng thread với **mọi** lần `onNext` về sau. Có thể xuất hiện nhiều ranh giới async trong cùng pipeline.

## 12. Các lỗi hiểu sai thường gặp

1. **“Mỗi `Mono` là một thread.”** Sai. `Mono` là publisher 0..1; thread phụ thuộc nguồn và scheduling.
2. **“Mỗi `Flux` có một thread; mỗi phần tử Flux thêm một thread.”** Sai. Một `Flux.range` lớn có thể phát toàn bộ giá trị đồng bộ trên caller.
3. **“`subscribe()` luôn tạo background task.”** Sai. Với nguồn đồng bộ, `subscribe()` có thể chạy consumer và hoàn tất ngay trước khi trả về. Với nguồn async, tín hiệu có thể đến muộn.
4. **“`fromCallable` là non-blocking.”** Sai. Nó trì hoãn thực thi; lời gọi vẫn có thể blocking và cần scheduler phù hợp nếu nằm trong WebFlux.
5. **“`publishOn` luôn thay đổi thread của source.”** Sai. Nó chuyển **downstream signals** từ vị trí đặt toán tử.
6. **“`subscribeOn` chỉ tác động từ chỗ được viết trở xuống.”** Sai. Nó chủ yếu tác động quá trình subscribe đi về source; vị trí cú pháp không giống `publishOn`.
7. **“Chỉ cần `Schedulers.parallel()` là mọi phép tính tự chia nhiều core.”** Sai. Một `publishOn(parallel())` trên một subscription không tự parallel hóa các phần tử.
8. **“Reactor non-blocking có thể gọi JDBC/HTTP sync trong event-loop.”** Sai ở mặt hiệu năng: mã đó vẫn chặn thread chia sẻ và làm giảm throughput.
9. **“Đổi thread không ảnh hưởng state.”** Sai khi dùng mutable shared state hoặc `ThreadLocal`. Phải xác định ranh giới thread và cách chia sẻ/truyền context.
10. **“Thread pool nào cũng vô hạn.”** Sai. `boundedElastic` và `parallel` có giới hạn; tải cao có thể gây xếp hàng, tăng latency hoặc từ chối.
11. **“Càng nhiều lần chuyển scheduler càng nhanh.”** Sai. Scheduling cũng tốn chi phí và có thể làm pipeline chậm hơn, phức tạp hơn.
12. **“Một request phải luôn chạy trên một thread từ đầu đến cuối.”** Sai với WebFlux: event-loop, callback từ client reactive và `publishOn/subscribeOn` có thể tạo nhiều execution context hợp lệ.

## 13. Tự kiểm tra

**Câu 1.** `Mono.just(5).map(n -> n + 1).subscribe(...)` có tạo worker mới mặc định không? **Không.** Nếu nguồn và operator đồng bộ, chúng thường chạy trên thread gọi subscribe.

**Câu 2.** `Mono.fromCallable(() -> jdbcQuery())` có an toàn để đặt trực tiếp trên event-loop không? **Không.** `jdbcQuery()` vẫn blocking khi subscription thực thi. Nên dùng `subscribeOn(Schedulers.boundedElastic())`, hoặc chuyển sang driver non-blocking phù hợp.

**Câu 3.** `publishOn(Schedulers.parallel())` ở giữa pipeline ảnh hưởng đoạn nào? **Chủ yếu đoạn downstream sau publishOn** cho đến ranh giới scheduling khác.

**Câu 4.** `subscribeOn(Schedulers.boundedElastic())` có ý nghĩa gì với nguồn `fromCallable`? **Lập lịch subscription và công việc nguồn đồng bộ trên scheduler worker**, tránh giữ caller trong khi callable chờ.

**Câu 5.** `Flux.interval(Duration.ofSeconds(1))` có thể phát từ thread khác mà không có `publishOn` không? **Có.** Đó là nguồn có scheduler định thời riêng, mặc định dùng cơ chế Reactor quy định.

**Câu 6.** Số request WebFlux bằng số thread Netty có đúng không? **Không.** Event-loop thread phục vụ nhiều kết nối/request trong mô hình non-blocking, nhưng cần tránh blocking và theo dõi điểm nghẽn.

**Câu 7.** Có nên tạo `Schedulers.newSingle` bên trong controller mỗi request? **Không nên.** Dùng scheduler chia sẻ hoặc một instance được quản lý vòng đời và dispose đúng cách.

**Điểm nhớ cuối:** Reactive mô tả **cách xử lý tín hiệu và điều phối công việc**, không cấp một thread riêng cho mỗi `Mono`/`Flux`. Nguồn đồng bộ thường dùng **thread subscribe**; `publishOn` chuyển **xử lý downstream**, `subscribeOn` chuyển **subscription/source**, một số nguồn I/O/timer vốn đã bất đồng bộ. Trong Spring WebFlux, cần giữ **event-loop không bị blocking** và chỉ sử dụng Scheduler khi có lý do kỹ thuật cụ thể.

**Tài liệu chính thức:** [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html), [Project Reactor — Reactor Core Reference](https://projectreactor.io/docs/core/release/reference/index.html).