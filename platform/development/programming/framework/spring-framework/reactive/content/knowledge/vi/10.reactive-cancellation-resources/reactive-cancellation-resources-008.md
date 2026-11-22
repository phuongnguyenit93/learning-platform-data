# Quản lý Scheduler, subscription và tài nguyên tự tạo trong Reactor / Spring WebFlux

## 1. Mục tiêu: quản lý đúng quyền sở hữu và vòng đời

Trong ứng dụng reactive, ngoài dữ liệu còn có **thread/queue của Scheduler**, **Subscription đang hoạt động**, **connection**, **session**, **file**, **listener callback**, **buffer** và tài nguyên do ứng dụng hoặc thư viện ngoài cấp. Một Flux hoặc Mono có thể kết thúc theo ba đường:

- **onComplete:** hoàn thành bình thường.
- **onError:** gặp lỗi.
- **cancel:** Subscriber ngừng quan tâm đến kết quả, chẳng hạn client HTTP ngắt kết nối, take(n) đã đủ dữ liệu hoặc timeout hủy upstream.

**Không được chỉ giải phóng tài nguyên khi thành công.** Nếu cleanup chỉ nằm trong doOnComplete, một yêu cầu thất bại hoặc bị hủy có thể rò connection, thread, registration hoặc tài nguyên bộ nhớ.

Phân biệt ba phạm vi ownership:

| Loại | Người quản lý vòng đời | Thời điểm giải phóng |
| --- | --- | --- |
| **Scheduler riêng** do service/app tạo | Component hoặc Spring context sở hữu Scheduler | Khi component/app dừng và không còn tác vụ cần Scheduler |
| **Subscription do code chủ động subscribe()** | Phần code đã gọi subscribe hoặc một container sở hữu handle | Khi luồng không còn cần tiếp tục; theo shutdown hoặc hủy nghiệp vụ |
| **Resource mở cho một subscription** | Pipeline quản lý qua using/usingWhen hoặc logic tương đương | Sau complete/error/cancel, đúng hợp đồng đồng bộ/bất đồng bộ |

Nếu một Scheduler, client hoặc pool **do framework/shared runtime quản lý**, không tự dispose nó khi kết thúc một request. Ngược lại, nếu ứng dụng tự mở tài nguyên, không trông đợi việc hết scope của biến Java tự động gọi close hoặc dispose.

Quy tắc trung tâm: **tạo ở đúng phạm vi, trao quyền sở hữu rõ ràng, đảm bảo cleanup trên mọi đường kết thúc, và kiểm thử các đường kết thúc khác nhau**.

## 2. Các khái niệm cơ bản

**Scheduler** là abstraction lập lịch tác vụ của Project Reactor. Scheduler có thể dùng thread riêng, pool, event loop hoặc thực thi ngay trên thread hiện tại. Những API như publishOn và subscribeOn phối hợp sử dụng nó.

**Subscription** là hợp đồng Reactive Streams giữa Publisher và Subscriber, cho phép Subscriber dùng **request(n)** và **cancel()**. Đây không phải cùng một đối tượng với Scheduler, cũng không phải tất cả tài nguyên ngoài pipeline.

**Disposable** là một handle có thể gọi **dispose()**. Nhiều lời gọi **subscribe()** trong Reactor trả Disposable để ứng dụng hủy subscription. Một tác vụ được Scheduler.schedule trả về Disposable riêng. Một Scheduler cũng có cơ chế dispose, nhưng **dispose một subscription không có nghĩa phải dispose toàn Scheduler**.

**AutoCloseable/Closeable** là kiểu resource Java có thao tác close. Một API khác có thể chỉ hỗ trợ đóng bằng Publisher (ví dụ Mono<Void> hoặc Publisher<Void>).

**Resource ownership** là câu trả lời cho ba câu hỏi: ai tạo/cấp phát, ai có thể sử dụng, và ai được quyền đóng. Nếu owner không rõ, nguy cơ phổ biến là **quên đóng**, **đóng hai lần**, hoặc **đóng quá sớm khi bên khác còn dùng**.

### Sơ đồ vòng đời

~~~text
Khởi động ứng dụng
   |
   +--> tạo Scheduler/connection pool dùng chung (owner: app)
   |
   +--> HTTP request 1
   |       |
   |       +--> framework subscribe response Publisher
   |       +--> mở resource riêng (nếu cần)
   |       +--> complete/error/cancel -> đóng resource riêng
   |
   +--> tác vụ nền độc lập
   |       |
   |       +--> app tự subscribe -> giữ Disposable
   |       +--> shutdown -> dispose Subscription
   |
Tắt ứng dụng
   |
   +--> ngừng nhận việc mới
   +--> xử lý/hủy subscription nền và chờ cleanup phù hợp
   +--> dispose Scheduler/pool do app sở hữu
~~~

Đây là quy trình tư duy, không phải thứ tự cứng cho mọi framework. Nếu một cleanup Publisher còn cần Scheduler chạy, **không được dispose Scheduler trước khi cleanup đã được điều phối đúng cách**.

## 3. Scheduler có sẵn và Scheduler tự tạo

### 3.1. Các Scheduler được Reactor quản lý

~~~java
Schedulers.parallel();
Schedulers.boundedElastic();
Schedulers.single();
Schedulers.immediate();
~~~

Những lời gọi này được dùng để lựa chọn môi trường thực thi phù hợp:

- **parallel():** dành cho công việc CPU không blocking; có lượng worker hữu hạn. Một publishOn(parallel()) đơn lẻ không tự chia mỗi phần tử ra một thread.
- **boundedElastic():** hữu ích để cô lập công việc blocking bắt buộc dùng; có giới hạn số thread/queue, không biến API blocking thành non-blocking.
- **single():** Scheduler chia sẻ với một thread; tác vụ nặng có thể làm nghẽn phần việc khác.
- **immediate():** không đổi sang pool chuyên dụng.

Không viết mã như sau trong mỗi request:

~~~java
return service.load()
        .publishOn(Schedulers.parallel())
        .doFinally(signal -> Schedulers.parallel().dispose());
~~~

Đây là **ví dụ sai về ownership**: Scheduler được dùng chung ở cấp runtime; một request không có quyền tắt nó thay các request khác.

### 3.2. Tạo Scheduler riêng

~~~java
Scheduler worker = Schedulers.newSingle("custom-stage");
try {
    String result = Mono.just("hello")
            .publishOn(worker)
            .map(String::toUpperCase)
            .block(); // Chỉ ở chương trình console.
    System.out.println(result);
} finally {
    worker.dispose();
}
~~~

Đây là đoạn minh họa Java với import Reactor. Scheduler tạo bởi **newSingle** là tài nguyên riêng và cần được dispose. **try/finally** phù hợp ở đây vì chương trình console dùng block() để chờ kết quả đã hoàn tất.

Nhưng **không** áp dụng mẫu finally đó vào phương thức trả Mono lazy:

~~~java
Mono<String> wrong() {
    Scheduler worker = Schedulers.newSingle("temporary");
    try {
        return Mono.just("hello")
                .publishOn(worker)
                .map(String::toUpperCase);
    } finally {
        worker.dispose(); // Đóng trước khi người gọi subscribe.
    }
}
~~~

Đây là **ví dụ sai có chủ đích**. Mono chưa chạy khi phương thức return; finally đã đóng Scheduler. Khi framework subscribe sau đó, công việc có thể bị từ chối lập lịch.

Giải pháp: giữ Scheduler ở phạm vi component/bean **đủ lâu**, hoặc nếu thật sự cần Scheduler riêng cho từng subscription thì mở và đóng bằng **using/usingWhen** gắn với subscription.

### 3.3. Scheduler do Spring quản lý

Trong một ứng dụng Spring Boot đã cấu hình dependency Spring và Reactor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
class SchedulerConfiguration {
    @Bean(destroyMethod = "dispose")
    Scheduler legacyScheduler() {
        return Schedulers.newBoundedElastic(
                8,       // số backing thread tối đa
                1000,    // số task queued tối đa trên mỗi backing thread
                "legacy-io"
        );
    }
}
~~~

Đây là **cấu hình minh họa**, không phải ứng dụng Spring Boot standalone. Spring context sở hữu bean và gọi dispose khi bean bị hủy theo lifecycle. Nhiều service có thể inject cùng Scheduler; **không service nào tự dispose bean sau từng request**.

Khi buộc tích hợp thư viện blocking:

~~~java
Mono<Result> load(String id) {
    return Mono.fromCallable(() -> blockingClient.load(id))
            .subscribeOn(legacyScheduler);
}
~~~

Đoạn này giả định có kiểu Result, blockingClient và Scheduler bean. Nguồn blocking nằm trong **fromCallable** và được subscribeOn điều phối sang Scheduler phù hợp. Dù vậy, hàm blocking vẫn chiếm thread trong lúc thực thi; cần giới hạn concurrency, timeout, CPU và queue.

**Cảnh báo:** Tạo một **newBoundedElastic** riêng trong mỗi lời gọi service có thể gây nổ số lượng thread/queue; quản lý nó như bean hoặc tài nguyên component là lựa chọn phổ biến hơn.

### 3.4. Scheduler.Worker và từng tác vụ

Khi ứng dụng dùng API schedule mức thấp:

~~~java
Scheduler own = Schedulers.newSingle("task-runner");
Scheduler.Worker worker = own.createWorker();
Disposable task = worker.schedule(() -> performTask());

task.dispose();   // Hủy task nếu còn có thể.
worker.dispose(); // Không dùng Worker nữa.
own.dispose();    // Không dùng Scheduler tự tạo nữa.
~~~

Đây là đoạn minh họa, performTask do ứng dụng định nghĩa. Có thể có ba cấp quyền sở hữu: task, worker và scheduler. Hủy task không có nghĩa phải hủy Scheduler dùng chung. **Nếu task đang chạy, dispose không cam kết chặn lập tức thao tác đã bắt đầu hoặc rollback side effect**.

## 4. Subscription do ai sở hữu?

### 4.1. subscribe() thủ công cần giữ Disposable

~~~java
Disposable sub = Flux.interval(java.time.Duration.ofSeconds(1))
        .subscribe(
                tick -> log.info("tick={}", tick),
                error -> log.error("poll failed", error)
        );

// Khi component không còn muốn nhận sự kiện:
sub.dispose();
~~~

Đây là đoạn service minh họa đã có log. **Flux.interval** có thể phát vô hạn; nếu subscribe() rồi bỏ handle, stream nền có thể tiếp tục chạy và giữ tham chiếu không mong muốn.

Người tự subscribe phải trả lời: ai gọi dispose? Nếu lỗi kết thúc, ai ghi nhận? Có cần khởi động lại không? Nếu component shutdown trong lúc callbacks đang chạy, bên ngoài có thể còn một số tín hiệu đã in-flight.

Một số Disposable có **isDisposed()**, nhưng không được coi true/false của mọi implementation là chứng cứ một request mạng hay transaction remote đã dừng hoàn toàn. Trạng thái hủy subscription và trạng thái nghiệp vụ bên ngoài khác nhau.

### 4.2. Spring WebFlux controller thường không tự subscribe

Cách đúng:

~~~java
@GetMapping("/events")
public Flux<EventDto> events() {
    return eventService.stream().map(EventDto::from);
}
~~~

Controller **trả Publisher**, framework subscribe và điều phối response/cancellation.

Cách sai:

~~~java
@GetMapping("/events")
public Flux<EventDto> events() {
    eventService.stream().subscribe(this::sendElsewhere);
    return Flux.empty();
}
~~~

Mã trên tạo một tác vụ rời với vòng đời HTTP response; client hủy response không nhất thiết hủy subscription do controller tự tạo. Lỗi và tài nguyên không được quản lý qua cùng đường response. Nếu có yêu cầu tạo background worker, hãy dùng service có **lifecycle, Disposable và chính sách shutdown** riêng.

### 4.3. Một subscription có thể kết thúc theo nhiều nguyên nhân

Ví dụ:

~~~java
Flux<Integer> source = Flux.range(1, 100)
        .doFinally(signal -> logger.info("source ended: {}", signal))
        .take(2);
~~~

Đây là đoạn minh họa. **take(2)** nhận hai giá trị rồi cancel upstream; doFinally **trước take** có thể quan sát **SignalType.CANCEL**. Nhưng Subscriber phía sau take nhận **onComplete** thành công sau hai phần tử. Đó là hai ranh giới khác nhau, không mâu thuẫn.

## 5. doFinally, doOnCancel và các callback vòng đời

| Operator | Kích hoạt khi | Phạm vi |
| --- | --- | --- |
| **doOnSubscribe** | Có subscription mới | Bắt đầu timer, tracing |
| **doOnNext** | Có phần tử | Quan sát dữ liệu, không phải cleanup cuối |
| **doOnComplete** | Flux hoàn thành | Chỉ hoàn thành, không error/cancel |
| **doOnError** | Có onError | Chỉ nhánh lỗi |
| **doOnCancel** | Có hủy subscription | Chỉ nhánh cancel |
| **doOnTerminate** | onComplete hoặc onError | Không bao gồm cancel |
| **doFinally** | onComplete, onError hoặc cancel | Nhận **SignalType.ON_COMPLETE/ON_ERROR/CANCEL** |

**doFinally** hữu ích để đếm và phân loại kết quả cuối:

~~~java
return client.fetch(id)
        .doFinally(signal -> {
            activeRequests.decrementAndGet();
            metrics.record(signal);
        });
~~~

Nhưng cần phân biệt **quan sát** với **cleanup bắt buộc**:

- doFinally được gọi theo quy tắc về vị trí/tín hiệu của Reactor; với complete/error, callback có thể chạy **sau khi downstream đã thấy terminal**. Một phép kiểm tra biến ngay sau block() có thể không luôn thấy side effect callback nếu lịch thực thi khác nhau.
- doFinally **không làm một Publisher cleanup tự động được subscribe và chờ**. Không viết doFinally(signal -> closeAsync().subscribe()) rồi giả định cleanup sẽ hoàn tất trước response.
- Lỗi từ hành động cleanup trong callback có thể khó phối hợp với lỗi gốc. Dùng **using/usingWhen** nếu resource phải được quản lý như một phần của contract Publisher.
- Vị trí callback trước/sau take, timeout, retry có thể làm loại tín hiệu được quan sát khác nhau.

Nếu cần cleanup đồng bộ theo một subscription, dùng **using**. Nếu close/commit/rollback trả Publisher, dùng **usingWhen**.

## 6. Flux.using và Mono.using: tài nguyên đồng bộ theo subscription

Một resource được tạo riêng khi subscribe, dùng trong pipeline, rồi được giải phóng trên complete/error/cancel:

~~~text
Subscription
   |
   +--> resourceSupplier() tạo resource
   +--> resourceClosure(resource) tạo Publisher dùng resource
   |
   +--> complete -----+
   +--> error --------+--> resourceCleanup(resource)
   +--> cancel -------+
~~~

Cú pháp:

~~~java
Flux<String> lines = Flux.using(
        () -> openResource(),
        resource -> readResource(resource),
        resource -> closeResource(resource)
);
~~~

Đây là đoạn minh họa với API ứng dụng do người học định nghĩa. **Flux.using** dành cho resource có cleanup đồng bộ; overload có tham số **eager** cho phép điều chỉnh thời điểm disposer liên quan tới tín hiệu kết thúc. Nếu disposer ném lỗi, cần hiểu tác động của eager và xử lý ngoại lệ đúng hợp đồng.

**Không mở resource eager rồi trả lại nó ở mọi lần subscribe**:

~~~java
Connection shared = openConnection();
Flux<Row> bad = Flux.using(
        () -> shared,
        conn -> query(conn),
        conn -> close(conn)
);
~~~

Đây là ví dụ sai nếu nhiều subscription có thể tới hoặc nếu khai báo publisher mà không bao giờ subscribe. Resource mở ngay, có thể không được dùng/đóng và bị nhiều Subscriber chia sẻ.

Nếu resource mở đồng bộ, đặt lời gọi mở trong Supplier:

~~~java
Flux<Row> good = Flux.using(
        () -> openConnection(),
        conn -> query(conn),
        conn -> close(conn)
);
~~~

Hai đoạn này là minh họa API đồng bộ có Row, Connection và phương thức ứng dụng. Đối với DB reactive có mở/đóng bằng Publisher, dùng **usingWhen**, hoặc cơ chế Spring transaction/resource management tương ứng.

## 7. Mono.usingWhen và Flux.usingWhen: resource bất đồng bộ

Nhiều tài nguyên có API async như **openSession(): Mono<Session>** và **closeSession(Session): Mono<Void>**. Dùng **usingWhen** để Reactor quản lý Publisher cleanup:

~~~java
Mono<Result> result = Mono.usingWhen(
        client.openSession(),               // Publisher<Session>
        session -> client.execute(session), // Mono<Result>
        session -> client.close(session)    // Publisher<?> cleanup
);
~~~

Đây là đoạn minh họa với client, Session, Result của ứng dụng. Các thao tác cần resource hoạt động phải nằm trong **resourceClosure**. Nếu resource được dùng ở downstream **sau usingWhen**, lúc đó nó có thể đã bị đóng.

### Ba nhánh cleanup riêng

~~~java
Mono<Result> operation = Mono.usingWhen(
        client.openSession(),
        session -> client.execute(session),
        session -> client.commitAndClose(session),
        (session, error) -> client.rollbackAndClose(session),
        session -> client.cancelAndClose(session)
);
~~~

Đây là code kiến trúc minh họa với các phương thức trả Publisher của client giả định:

- **asyncComplete** chạy khi resourceClosure hoàn tất thành công.
- **asyncError** nhận resource và lỗi của resourceClosure để rollback/close theo hợp đồng.
- **asyncCancel** được gọi khi subscription bị hủy.

Không tự commit/rollback connection đã thuộc **Spring TransactionalOperator hoặc một transaction manager** quản lý; chọn một owner của transaction.

### Mono.usingWhen chờ cleanup trước khi phát kết quả cuối

Với Mono.usingWhen, **kết quả thành công được phối hợp với Publisher cleanup**. Khi cleanup lỗi, Mono có thể phát **onError** thay vì một giá trị dự kiến, và kết quả đó có thể bị bỏ. Điều này quan trọng cho thao tác mà chỉ được công bố thành công sau commit/close.

Với Flux.usingWhen, nhiều **onNext** có thể đã được giao trong khi tài nguyên còn mở; lỗi cleanup không thể thu hồi những onNext Subscriber đã thấy. **usingWhen không phải tự động exactly-once hay transaction phân tán.**

Các trường hợp cần tính:

- Resource Supplier hoàn tất rỗng/ lỗi trước khi cấp resource: không có resource đã cấp để cleanup theo cơ chế đó.
- Operation lỗi: cleanup nhánh lỗi phải được xét, không giấu mất lỗi gốc.
- Subscriber cancel: cleanup nhánh cancel cần được khởi chạy nhưng có thể còn thực thi **sau khi lời gọi dispose() trả về** nếu là bất đồng bộ.
- Cleanup Publisher lỗi: cần ghi nhận cleanup failure, không tự giả định một kết quả thành công.
- Resource dùng chung ngoài usingWhen: có thể bị đóng trong khi một bên khác đang cần.

## 8. Ví dụ Java 17+ chạy được: quản lý cả ba loại tài nguyên

Chương trình dùng Reactor Core để minh họa:

1. Scheduler riêng xử lý map phía sau publishOn và được dispose ở cuối.
2. Subscription của Flux.never được dispose, doFinally nhận CANCEL.
3. Flux.using tự close resource khi take(2) hủy upstream.
4. Mono.usingWhen phối hợp Publisher cleanup rồi mới trả kết quả.

Cấu trúc:

~~~text
reactor-resource-lifecycle/
├── pom.xml
└── src/main/java/ResourceLifecycleDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-resource-lifecycle</artifactId>
    <version>1.0.0</version>
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
                    <mainClass>ResourceLifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/ResourceLifecycleDemo.java**:

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ResourceLifecycleDemo {
    static final class CounterResource implements AutoCloseable {
        private final AtomicInteger closed;

        CounterResource(AtomicInteger closed) {
            this.closed = closed;
        }

        int twice(int number) {
            return number * 2;
        }

        @Override
        public void close() {
            closed.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        Scheduler worker = Schedulers.newSingle("lesson-worker");
        try {
            String stage = Mono.just("A")
                    .publishOn(worker)
                    .map(value -> Thread.currentThread()
                            .getName()
                            .startsWith("lesson-worker-")
                            ? "on-worker" : "unexpected-thread")
                    .block();
            System.out.println("scheduler stage = " + stage);

            List<String> cancellation = new CopyOnWriteArrayList<>();
            Disposable subscription = Flux.<Integer>never()
                    .doFinally(signal -> cancellation.add(signal.name()))
                    .subscribe();
            subscription.dispose();
            System.out.println("cancel signal = " + cancellation);

            AtomicInteger closeCount = new AtomicInteger();
            List<Integer> values = Flux.using(
                    () -> new CounterResource(closeCount),
                    resource -> Flux.range(1, 3)
                            .map(resource::twice),
                    CounterResource::close
            )
            .take(2)
            .collectList()
            .block();

            System.out.println("using values = " + values
                    + ", closed = " + closeCount.get());

            AtomicInteger asyncCloseCount = new AtomicInteger();
            String outcome = Mono.usingWhen(
                    Mono.fromSupplier(
                            () -> new CounterResource(asyncCloseCount)),
                    resource -> Mono.just("DONE"),
                    resource -> Mono.fromRunnable(resource::close)
            ).block();

            System.out.println("usingWhen = " + outcome
                    + ", closed = " + asyncCloseCount.get());
        } finally {
            worker.dispose();
        }

        System.out.println("scheduler disposed = " + worker.isDisposed());
    }
}
~~~

Yêu cầu **JDK 17+** và Maven. Chạy từ thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

**Stdout do chương trình in ra:**

~~~text
scheduler stage = on-worker
cancel signal = [CANCEL]
using values = [2, 4], closed = 1
usingWhen = DONE, closed = 1
scheduler disposed = true
~~~

Giải thích:

- **publishOn(worker)** làm map chạy trên worker của Scheduler được tạo với tên riêng; kiểm tra prefix cho kết quả on-worker.
- **Flux.never()** không có terminal tự nhiên. **dispose()** của subscription làm doFinally nhận **CANCEL**; demo đồng bộ hóa đơn giản vì Flux.never không xếp lịch phát trên thread khác.
- **take(2)** nhận hai số 1,2 sau nhân đôi thành 2,4 rồi hủy upstream. **Flux.using** close CounterResource **một lần**.
- **Mono.usingWhen** thực hiện **Mono.fromRunnable(resource::close)** như Publisher cleanup. Với Mono.usingWhen, giá trị DONE được giao sau cleanup; tại lúc block() trả về, counter đã tăng.
- **finally** dispose Scheduler riêng. Gọi isDisposed() cho scheduler này cho kết quả true.

**Vì sao ví dụ dùng block()?** Nó chỉ dùng ở ranh giới ứng dụng console để in kết quả của các nguồn hữu hạn. **Không dùng block() trên event loop trong WebFlux controller**. Không dựa vào Thread.sleep hoặc thứ tự in xen kẽ từ các thread để kiểm thử tài nguyên.

## 9. Gom các subscription nền với Disposables.composite()

Nếu một component chủ động subscribe nhiều nguồn **không thuộc HTTP response**, có thể giữ một **Disposable.Composite**:

~~~java
import reactor.core.Disposable;
import reactor.core.Disposables;

Disposable.Composite active = Disposables.composite();

active.add(sensorFlux.subscribe(
        event -> process(event),
        error -> log.error("sensor failed", error)
));

active.add(refreshFlux.subscribe(
        event -> refresh(event),
        error -> log.error("refresh failed", error)
));

// Khi component dừng:
active.dispose();
~~~

Đây là đoạn minh họa với sensorFlux, refreshFlux, process, refresh và log do ứng dụng cung cấp. Composite sở hữu các Disposable đã được thêm; dispose container sẽ hủy chúng. Nếu **add** sau khi container đã disposed, handle mới sẽ bị disposed thay vì làm container “sống lại”. Muốn một vòng chạy mới sau restart, tạo một composite mới.

**remove(d)** lấy handle ra khỏi composite nhưng không hủy handle; lúc đó caller phải nhận ownership và dispose đúng lúc. Không xóa khỏi composite rồi làm mất tham chiếu.

Không cần Disposables.composite() cho Publisher do Spring WebFlux framework tự subscribe khi xử lý response. Đây là công cụ cho những luồng **ứng dụng chủ động khởi chạy**.

## 10. Gỡ đăng ký callback ngoại vi

Một hệ thống ngoài Reactor có thể trả handle sau khi đăng ký listener. Khi chuyển callback thành Flux:

~~~java
Flux<Event> events = Flux.create(sink -> {
    ListenerRegistration registration =
            externalSource.registerListener(
                    value -> sink.next(value),
                    error -> sink.error(error)
            );

    sink.onDispose(() -> registration.unregister());
});
~~~

Đây là đoạn kiến trúc minh họa: Event, ListenerRegistration, externalSource là API giả định. **FluxSink.onDispose** đăng ký cleanup cho vòng đời sink, bao gồm kết thúc và cancellation; **onCancel** chỉ nhắm nhánh hủy.

Cần lưu ý:

- Mỗi subscription thường cần listener/registration riêng, trừ khi bạn cố ý thiết kế hot/shared source.
- API unregister có thể không chặn một callback đã in-flight, nên cần kiểm tra tính an toàn thread.
- Nếu unregistration là **async**, một Runnable onDispose không tự đợi nó hoàn tất; phải phối hợp cleanup theo hợp đồng phù hợp.
- Nếu nguồn push không hỗ trợ request(n), cần chính sách buffer/drop/error/backpressure riêng ở ranh giới adapter.
- Tránh giữ tham chiếu đến controller/service bị hủy trong listener không được unregister.

## 11. Hủy không đồng nghĩa dừng thao tác remote

~~~text
Client hủy Subscription
    |
    +--> Reactor yêu cầu downstream/upstream ngừng tín hiệu
    |
    +--> Client adapter có thể hủy future hoặc HTTP request
    |
    +--> Công việc phía server/SDK có thể vẫn đang chạy
    |
    +--> Side effect đã commit không tự rollback
~~~

**Cancellation là một phần của giao thức reactive**, nhưng tác động đến connection, RPC, database transaction hay SDK phụ thuộc vào tích hợp thật.

- **CompletableFuture.cancel()** có thể đánh dấu Future hủy, không bảo đảm task đã bắt đầu trên Executor dừng.
- **WebClient/Netty** có thể ngừng nhận/đóng request khi subscription bị hủy, nhưng không thể chứng minh server chưa thực hiện thao tác.
- **Timeout** thường hủy upstream nhưng không bảo đảm rollback.
- **Idempotency key**, API kiểm tra trạng thái và transaction manager giải quyết những yêu cầu giao nhận/khôi phục khác với Reactor cancellation.

Với resource được nhiều subscription chia sẻ, một subscriber hủy không nên tự đóng nguồn chung. Cần refCount/sharing, owner và hợp đồng close rõ ràng.

## 12. Bộ đệm, discard và tài nguyên cần release

Nếu một Flux chứa đối tượng như **DataBuffer/ByteBuf** do ứng dụng thực sự sở hữu, việc filter, take, cancel hoặc queue overflow có thể khiến một số phần tử bị loại trước khi tới Subscriber. **GC không nhất thiết thay thế thao tác release đối với pooled/reference-counted resource**.

Reactor có **doOnDiscard** cho các operator hỗ trợ discard:

~~~java
Flux<MyBuffer> result = source
        .filter(MyBuffer::shouldKeep)
        .doOnDiscard(MyBuffer.class, MyBuffer::release);
~~~

Đây là đoạn minh họa với MyBuffer/source do ứng dụng định nghĩa. Không phải operator nào cũng hỗ trợ discard. Hãy đọc ghi chú **Discard Support** của operator và kiểm tra ai đang sở hữu buffer:

- Chỉ release những object mà **ứng dụng phải release**.
- Không **double-release** object đã được framework/codec quản lý.
- Nếu Spring WebFlux xử lý DataBuffer thủ công, xem API **DataBufferUtils.release(...)** và các quy tắc của data buffer implementation.
- Khi có prefetch trong publishOn hoặc các operator async, cancellation có thể tạo phần tử tồn trong queue; cần xác định đường discard tương ứng.
- Không lạm dụng doOnDiscard như công cụ cleanup cho Scheduler hoặc connection chính: hai việc khác nhau.

## 13. Resource và transaction trong Spring WebFlux

### Resource thuộc request/subscription

~~~java
@GetMapping("/reports/{id}")
public Mono<Report> report(@PathVariable String id) {
    return Mono.usingWhen(
            sessionClient.openSession(),
            session -> sessionClient.readReport(session, id),
            session -> sessionClient.closeSession(session)
    );
}
~~~

Đây là ví dụ controller trong dự án đã có Report/sessionClient. Resource được mở cho subscription phục vụ request và đóng theo hợp đồng usingWhen. Lưu ý **client ngắt kết nối** có thể làm HTTP subscription bị hủy; nên có nhánh cleanup khi cancel.

Nếu dùng **R2DBC transaction manager** của Spring, thông thường nên để **TransactionalOperator** hoặc cơ chế transaction reactive tương ứng sở hữu commit/rollback; không tự thêm một usingWhen có commit song song khi framework đã quản lý cùng transaction.

### Resource thuộc ứng dụng

Connection pool, WebClient với resource tùy chỉnh, Scheduler riêng, background subscriptions có thể sống lâu hơn một request. Nên quản lý qua bean/lifecycle của Spring:

- **@Bean(destroyMethod = "dispose")** nếu resource có dispose() phù hợp.
- **@PreDestroy**, **DisposableBean** hoặc **SmartLifecycle** khi cần nhiều bước shutdown.
- Ngừng nguồn mới, dừng background subscriptions, điều phối cleanup và sau đó đóng Scheduler/connection pool theo dependency.
- Với cleanup Publisher, **chỉ tạo Mono rồi bỏ qua không có nghĩa cleanup đã chạy**: cần được subscribe/điều phối ở cơ chế shutdown đã thiết kế, có deadline và ghi nhận lỗi.
- Không dispose các thành phần chia sẻ của Reactor Netty chỉ vì một HTTP request kết thúc.

### Resource cleanup lỗi

Một thao tác cleanup có thể ném exception hoặc phát onError. Chính sách xử lý tùy loại tài nguyên và nghiệp vụ:

- Với **Mono.usingWhen**, cleanup lỗi có thể khiến kết quả chính chuyển thành onError thay vì phát success.
- Với **Flux.usingWhen**, các onNext trước đó không thể thu hồi.
- Nếu cả operation và cleanup đều lỗi, cần giữ thông tin root cause/cleanup cause để chẩn đoán.
- Không im lặng **onErrorResume(Mono.empty())** cho mọi lỗi cleanup quan trọng; có thể khiến lỗi commit/close bị che giấu.

## 14. Kiểm thử cả complete, error, cancel

Chỉ test happy path không đủ chứng minh đúng vòng đời tài nguyên. Với **reactor-test / StepVerifier** và một fake resource có **AtomicInteger closeCount**, kiểm tra:

1. **onComplete:** resource mở đúng một lần theo subscription, close đúng một lần.
2. **onError:** cleanup vẫn chạy; downstream thấy lỗi đúng hợp đồng.
3. **cancel:** take(1), thenCancel() hoặc dispose làm cleanup chạy.
4. **Không subscribe:** resourceSupplier chưa được gọi với nguồn deferred.
5. **Subscribe hai lần:** mỗi subscription nhận resource riêng, không dùng lại object đã đóng.
6. **Acquire lỗi/rỗng:** không cleanup một resource chưa từng được tạo.
7. **Async cleanup chậm/lỗi:** response chờ hoặc nhận lỗi theo semantics của usingWhen.
8. **Shutdown sớm:** không dispose Scheduler trước khi cleanup Publisher cần worker đó.
9. **Callback resource:** listener được unregister và không giữ reference sau cancel.
10. **Thread/pool:** không tích lũy Scheduler hoặc task sau nhiều lần tạo/dừng component.

Đoạn test minh họa (cần reactor-test và CounterResource đã định nghĩa trong chương trình):

~~~java
AtomicInteger closeCount = new AtomicInteger();

Flux<Integer> values = Flux.using(
        () -> new CounterResource(closeCount),
        r -> Flux.just(1, 2, 3),
        CounterResource::close
);

StepVerifier.create(values)
        .expectNext(1, 2, 3)
        .verifyComplete();

if (closeCount.get() != 1) {
    throw new AssertionError("Resource must close once");
}
~~~

Với cancellation, có thể dùng **StepVerifier.thenCancel()**, nhưng với cleanup bất đồng bộ cần quan sát thêm một tín hiệu xác nhận completion thay vì đọc counter tức thì. Tránh test dựa vào Thread.sleep tùy ý và log xen kẽ nhiều thread.

### Giám sát production

Nên quan sát **số subscription nền**, số resource mở/chưa đóng, số kết thúc theo ON_COMPLETE/ON_ERROR/CANCEL, **Scheduler queued/rejected tasks**, số connection/session, thời gian cleanup, cleanup error và resource còn tồn tại sau shutdown. Với metric, tránh dùng resource ID/request ID làm label không giới hạn vì gây cardinality lớn.

## 15. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| newSingle/newBoundedElastic trong từng request | Tốn thread/queue, dễ leak | Reuse Scheduler theo component/app, dispose khi shutdown |
| Dispose Scheduler chia sẻ ở doFinally | Làm hỏng subscription khác | Owner của Scheduler mới được phép dispose |
| finally đóng Scheduler trước khi Mono lazy được subscribe | Rejected scheduling, pipeline thất bại | Bean lifecycle hoặc using gắn subscription |
| subscribe() trong controller mà bỏ Disposable | Công việc tách HTTP, không bị hủy đúng lúc | Trả Mono/Flux cho framework |
| Chỉ cleanup trong doOnComplete | Leak khi error/cancel | using/usingWhen hoặc callback bao phủ đủ đường |
| doFinally(signal -> closeAsync().subscribe()) | Cleanup fire-and-forget, lỗi không được phối hợp | usingWhen với cleanup Publisher |
| Chia sẻ mutable resource qua nhiều subscription | Dùng resource đã đóng, race | Tạo resource mới theo subscription |
| Cho rằng dispose() rollback tác vụ remote | Retry có thể lặp side effect | Idempotency, transaction và kiểm tra trạng thái |
| Không giữ handle listener/Subscription nền | Callback hoặc interval chạy mãi | onDispose, Composite và lifecycle |
| Quên release buffer trên discard | Rò pooled memory | Ownership rõ, DataBufferUtils/doOnDiscard đúng hợp đồng |
| Đóng Scheduler trước async cleanup lúc shutdown | Cleanup có thể bị từ chối lập lịch | Điều phối cleanup trước khi tắt Scheduler liên quan |
| Chỉ kiểm tra isDisposed() để xác nhận remote task xong | Kết luận sai trạng thái thực thi | Dùng metric, kết quả remote và hợp đồng nghiệp vụ |

## 16. Chọn công cụ theo nhu cầu

| Nhu cầu | Công cụ |
| --- | --- |
| Dùng Scheduler chung cho CPU/legacy blocking | Scheduler Reactor quản lý hoặc Spring bean |
| Scheduler được ứng dụng tự tạo | dispose() trong lifecycle owner, không theo request |
| Task scheduled thủ công | Giữ Disposable từ schedule() |
| Subscription nền do ứng dụng tự subscribe | Giữ Disposable; dùng Disposables.composite() nếu cần |
| HTTP controller trả Publisher | **Không tự subscribe**; framework quản lý |
| Cần metric cho mọi loại kết thúc | **doFinally(SignalType)** |
| Chỉ cần callback khi cancel | **doOnCancel** |
| Resource đồng bộ, một instance cho mỗi subscription | **Flux.using / Mono.using** |
| Resource cần close/commit/rollback bất đồng bộ | **Flux.usingWhen / Mono.usingWhen** |
| Cleanup khác nhau khi complete/error/cancel | overload usingWhen có ba nhánh |
| Listener cần unregister khi stream ngừng | Flux.create + sink.onDispose hoặc using |
| Pooled buffer cần release khi discard | doOnDiscard + ownership/API giải phóng đúng loại |
| Shutdown nhiều tài nguyên phụ thuộc nhau | Lifecycle Spring có thứ tự stop/await/dispose |

## 17. Kết luận

Quản lý tài nguyên trong Reactor cần tách rõ **Scheduler**, **Subscription** và **resource gắn với từng subscription**. Scheduler tự tạo là tài nguyên phạm vi component/ứng dụng; không được tắt Scheduler dùng chung sau mỗi request. Disposable trả về từ subscribe() cần owner và điểm hủy nếu ứng dụng chủ động subscribe, còn trong Spring WebFlux hãy để framework quản lý subscription của response.

**doFinally** quan sát complete/error/cancel, nhưng không tự chờ cleanup bất đồng bộ. **using** quản lý resource đóng đồng bộ và **usingWhen** phối hợp resource có cleanup Publisher; cả hai giúp tránh mất cleanup khi error/cancel. **Cancellation không có nghĩa mọi tác vụ remote đã dừng hoặc rollback**: phải xem hợp đồng SDK, connection và nghiệp vụ.

Thiết kế tốt phải trả lời được: **Ai mở tài nguyên? Ai được quyền đóng? Đóng khi complete, error, cancel thế nào? Có cần chờ Publisher cleanup không? Khi shutdown có còn công việc cần Scheduler không?** Sau đó dùng StepVerifier/fake resource và metric để xác minh thực tế.

**Tài liệu chính thức:**
- [Reactor Reference — doFinally và using](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
- [Mono API — usingWhen, cancellation và cleanup](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Flux API — using, usingWhen, doOnDiscard](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Scheduler API](https://projectreactor.io/docs/core/release/api/reactor/core/scheduler/Scheduler.html)
- [Disposable.Composite API](https://projectreactor.io/docs/core/release/api/reactor/core/Disposable.Composite.html)
