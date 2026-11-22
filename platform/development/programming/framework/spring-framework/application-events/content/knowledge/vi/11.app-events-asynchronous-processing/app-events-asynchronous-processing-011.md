# Chọn bounded executor cho Spring Application Events

## 1. Bounded executor là gì và vì sao event cần nó?

Mặc định, Spring Framework phân phối application events **đồng bộ**: lời gọi `ApplicationEventPublisher.publishEvent(...)` thường gọi các listener trên chính luồng của bên phát. Khi ứng dụng cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, những listener hỗ trợ async có thể được chạy trên các luồng khác.

Điều này giúp request không phải chờ mỗi listener xử lý xong, nhưng tạo ra vấn đề mới: nếu event đến nhanh hơn khả năng xử lý, số tác vụ đang đợi sẽ tăng. Một executor có quá nhiều luồng có thể làm hệ thống kiệt CPU, bộ nhớ, kết nối cơ sở dữ liệu hoặc socket; một hàng đợi gần như vô hạn có thể làm event chờ hàng phút dù phía phát vẫn nhận phản hồi nhanh.

**Bounded executor** là executor có giới hạn rõ ràng về cả:

- **Số tác vụ thực thi đồng thời**: tối đa bao nhiêu worker thread có thể chạy.
- **Số tác vụ chờ**: tối đa bao nhiêu task được giữ trong queue trước khi xử lý.
- **Chính sách khi đầy**: hệ thống làm gì nếu mọi worker bận và hàng đợi đã đạt giới hạn.

Trong Spring, `ThreadPoolTaskExecutor` là lựa chọn phổ biến vì có thể cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity` và `RejectedExecutionHandler`, đồng thời cung cấp thông tin vận hành như `activeCount` và `queueSize`.

Một giới hạn quan trọng: **mỗi listener phù hợp có thể trở thành một task** khi multicaster sử dụng executor. Một event có ba listener async có thể tạo ba lần giao task. Vì vậy dung lượng executor là **số tác vụ listener**, không đồng nghĩa trực tiếp với số đối tượng event.

## 2. Cơ chế phân phối event và nơi đặt executor

Luồng điển hình:

```text
HTTP request / scheduled job / application service
                    |
                    | publishEvent(new OrderSubmitted(...))
                    v
       SimpleApplicationEventMulticaster
                    |
              chọn listener
                    |
            supportsAsyncExecution?
                 /         \
               Có          Không
                |             |
                v             v
          TaskExecutor    Chạy trực tiếp
                |         trên luồng publish
         +------+------+    
         |             |
     Worker threads  Bounded queue
         ^             |
         +-------------+
                |
         listener xử lý

    Khi worker/queue đã đầy:
    executor áp dụng rejection policy;
    multicaster còn có thể xử lý tình huống
    từ chối theo implementation/version.
```

`SimpleApplicationEventMulticaster` dùng đồng bộ nếu không đặt task executor. Khi cấu hình executor, nó chỉ giao bất đồng bộ những `ApplicationListener` khai báo hỗ trợ async; một ví dụ quan trọng của listener **không hỗ trợ** chuyển sang luồng khác là `TransactionalApplicationListener`.

Không nên đồng nhất “listener đã được xếp hàng” với “event đã được xử lý thành công”. Việc xếp hàng chỉ là bước nhận task vào bộ nhớ tiến trình.

## 3. Ba tham số quyết định hành vi của ThreadPoolTaskExecutor

| Tham số | Ý nghĩa | Câu hỏi cần trả lời |
| --- | --- | --- |
| `corePoolSize` | Số luồng lõi mà pool ưu tiên tạo khi nhận task | Mức song song thường xuyên là bao nhiêu? |
| `maxPoolSize` | Số worker tối đa khi pool cần tăng tải | Hệ thống phụ thuộc chịu được tối đa bao nhiêu thao tác đồng thời? |
| `queueCapacity` | Số task có thể chờ trong queue | Có thể chấp nhận event chờ bao lâu trước khi quá tải? |

Với cấu hình thông thường, `ThreadPoolExecutor` mà `ThreadPoolTaskExecutor` sử dụng có thứ tự nhận việc:

1. Nếu số worker đang chạy thấp hơn `corePoolSize`, tạo thêm worker.
2. Nếu đã đạt core, thử **xếp task vào queue**.
3. Nếu queue đầy và số worker còn dưới `maxPoolSize`, tạo thêm worker.
4. Nếu số worker đã đạt max và queue cũng đầy, gọi chính sách từ chối task.

Ví dụ:

```text
corePoolSize = 2
maxPoolSize  = 4
queueCapacity = 3

Task 1, 2      -> có thể kích hoạt 2 core workers
Task 3, 4, 5   -> vào queue (khi workers còn bận)
Task 6, 7      -> pool có thể tăng lên worker thứ 3, 4
Task 8         -> bị quá tải nếu 4 worker vẫn bận và queue đầy
```

Đây là **mô hình minh họa cho một thời điểm bão hòa**, khi task trước chưa hoàn thành. Nếu worker xử lý xong trong lúc task mới đến, kết quả sẽ khác.

Với `ThreadPoolTaskExecutor`, `queueCapacity > 0` dùng `LinkedBlockingQueue` có giới hạn bằng cấu hình. `queueCapacity = 0` dùng `SynchronousQueue`, tức không có vùng chờ theo kiểu queue thông thường; pool phải giao việc trực tiếp hoặc tạo worker trong giới hạn max. Dung lượng queue thường được chọn dựa trên giới hạn độ trễ, không nên chọn chỉ vì có nhiều RAM.

**Bẫy cấu hình mặc định:** Trong dòng Spring Framework 6.2, `ThreadPoolTaskExecutor` mặc định `corePoolSize = 1`, `maxPoolSize = Integer.MAX_VALUE` và `queueCapacity = Integer.MAX_VALUE`. Vì queue gần như vô hạn, pool thường chỉ dùng một core worker và tích lũy backlog; đặt riêng `maxPoolSize` mà không giới hạn queue có thể không đạt hiệu quả tăng song song mong muốn.

## 4. Cấu hình một bounded executor dành riêng cho application events

Ví dụ Spring Configuration:

```java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class EventExecutorConfig {

    @Bean("applicationEventExecutor")
    public ThreadPoolTaskExecutor applicationEventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setThreadNamePrefix("app-events-");

        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean(name =
            AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    public SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("applicationEventExecutor")
            ThreadPoolTaskExecutor executor) {

        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
```

Đây là **đoạn cấu hình sử dụng trong một ứng dụng có Spring Context**, chưa phải chương trình độc lập. Spring khởi tạo và quản lý lifecycle của `ThreadPoolTaskExecutor` do `@Bean` trả về. Bean multicaster phải có tên chuẩn `applicationEventMulticaster` để `ApplicationContext` sử dụng nó.

Các giá trị `4 / 8 / 100` chỉ là **ví dụ cú pháp**, không phải cấu hình tối ưu cho mọi hệ thống. Với listener gọi dịch vụ ngoài chậm, cả tám worker có thể cùng chờ I/O; với listener CPU-bound, tám luồng trên máy hai CPU có thể gây tranh chấp đáng kể. Để chọn số thực tế cần đo lưu lượng, thời gian xử lý, downstream và giới hạn độ trễ.

`AbortPolicy` là chính sách từ chối của pool khi đã bão hòa. Khi gọi trực tiếp `ThreadPoolTaskExecutor.execute(...)`, Spring thường báo `TaskRejectedException`. **Không được mặc định suy ra rằng `publishEvent(...)` luôn ném chính exception đó**: multicaster là một lớp gọi trung gian; hành vi khi `executor.execute` bị từ chối phụ thuộc vào triển khai và phiên bản Spring, có phiên bản có đường xử lý chạy listener trên luồng caller khi executor từ chối. Phải kiểm chứng bằng integration test với đúng phiên bản đang triển khai. Khi cần bảo đảm event bị từ chối **trước khi publish**, hãy thực hiện admission control ở phía phát hoặc dùng một hệ thống giao nhận có hợp đồng nhận/từ chối rõ ràng.

## 5. Ví dụ Java 17 chạy được: event chạy trên executor có giới hạn

Ví dụ dưới đây dùng **Java 17+, Maven và Spring Framework 6.2.12**. Nó có hai chế độ:

- **Mặc định:** phát hai event và chứng minh listener xử lý trên worker thread của executor.
- **`pressure`:** thử riêng cơ chế đầy hàng đợi của chính `ThreadPoolTaskExecutor`. Chế độ này gọi trực tiếp `execute(...)` để tách hành vi pool khỏi hành vi fallback có thể khác nhau của multicaster.

Cấu trúc thư mục:

```text
bounded-spring-events/
├── pom.xml
└── src/main/java/demo/BoundedEventDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bounded-spring-events</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.BoundedEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/BoundedEventDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class BoundedEventDemo {

    public record TaskCreated(String id) {}

    public static class TaskListener {
        private final CountDownLatch finished = new CountDownLatch(2);

        @EventListener
        public void onTask(TaskCreated event) {
            if (!Thread.currentThread().getName()
                    .startsWith("app-events-")) {
                throw new IllegalStateException(
                        "Unexpected executor thread");
            }
            System.out.println("HANDLED " + event.id());
            finished.countDown();
        }

        public boolean awaitBoth() throws InterruptedException {
            return finished.await(5, TimeUnit.SECONDS);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean("eventExecutor")
        public ThreadPoolTaskExecutor eventExecutor() {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("app-events-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            return executor;
        }

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster(
                @Qualifier("eventExecutor")
                ThreadPoolTaskExecutor executor) {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(executor);
            return multicaster;
        }

        @Bean
        public TaskListener taskListener() {
            return new TaskListener();
        }
    }

    private static void springEventExample() throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            TaskListener listener = context.getBean(TaskListener.class);

            context.publishEvent(new TaskCreated("E1"));
            context.publishEvent(new TaskCreated("E2"));

            if (!listener.awaitBoth()) {
                throw new IllegalStateException("Listener timed out");
            }
        }
    }

    private static void executorPressureExample()
            throws InterruptedException {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("pressure-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.initialize();

        var firstStarted = new CountDownLatch(1);
        var unblockFirst = new CountDownLatch(1);
        var twoFinished = new CountDownLatch(2);

        try {
            executor.execute(() -> {
                firstStarted.countDown();
                try {
                    unblockFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
                System.out.println("FINISHED 1");
                twoFinished.countDown();
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }

            // Task 1 đang chạy, task 2 vào queue có capacity = 1.
            executor.execute(() -> {
                System.out.println("FINISHED 2");
                twoFinished.countDown();
            });

            // Pool đã có một worker bận và một task đang chờ.
            try {
                executor.execute(() ->
                        System.out.println("UNEXPECTED 3"));
                throw new IllegalStateException(
                        "Task 3 should have been rejected");
            } catch (TaskRejectedException expected) {
                System.out.println("REJECTED 3");
            }
        } finally {
            unblockFirst.countDown();
        }

        try {
            if (!twoFinished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Tasks did not finish");
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        if (args.length > 0 && "pressure".equals(args[0])) {
            executorPressureExample();
        } else {
            springEventExample();
        }
    }
}
```

Để chạy chế độ event:

```bash
mvn -q compile exec:java
```

Các dòng ứng dụng in ra:

```text
HANDLED E1
HANDLED E2
```

Ở đây `corePoolSize = maxPoolSize = 1`, một worker xử lý hai event theo thứ tự task nhận trong queue. Mỗi task xác nhận tên thread bắt đầu bằng `app-events-`; nếu listener chạy nhầm trên luồng caller, ví dụ sẽ không in được hai dòng thành công và phép chờ sẽ báo lỗi. Không cần `@EnableAsync` vì đây là executor do multicaster sử dụng, không phải `@Async`.

Để chạy chế độ kiểm tra bão hòa:

```bash
mvn -q compile exec:java -Dexec.args=pressure
```

Các dòng ứng dụng in ra:

```text
REJECTED 3
FINISHED 1
FINISHED 2
```

Lý do: task 1 giữ worker bằng `CountDownLatch`, task 2 nằm trong queue dung lượng 1, task 3 bị `AbortPolicy` từ chối. Spring `ThreadPoolTaskExecutor.execute` báo `TaskRejectedException`; sau khi phép thử kết thúc, latch mở để task 1 và 2 hoàn thành. Ví dụ không dùng `Thread.sleep(...)` nên không phụ thuộc suy đoán về lịch chạy luồng.

**Ranh giới của ví dụ:** chế độ `pressure` thử **executor trực tiếp**. Nó không khẳng định rằng một lời gọi `ApplicationEventPublisher.publishEvent` bị từ chối sẽ luôn ném exception hay luôn bỏ event. Với event thực tế, phải test đúng `SimpleApplicationEventMulticaster` và phiên bản Spring, gồm trường hợp queue đầy, ứng dụng đang shutdown và listener không hỗ trợ async.

## 6. Hiểu chính xác các chính sách từ chối

JDK `ThreadPoolExecutor` có các chính sách chính sau:

| Chính sách | Khi queue và worker đều đầy | Ảnh hưởng đến event |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException`; Spring TaskExecutor có thể bọc thành `TaskRejectedException` | Tạo tín hiệu quá tải rõ tại cấp executor; hành vi cuối qua multicaster cần test |
| `CallerRunsPolicy` | Nếu executor chưa shutdown, chạy task ngay trên thread gọi `execute` | Tạo backpressure bằng cách làm chậm publisher, nhưng có thể kéo dài HTTP request và thay đổi thread context |
| `DiscardPolicy` | Bỏ task mà không báo lỗi | Nguy cơ mất event âm thầm; hiếm khi phù hợp với xử lý quan trọng |
| `DiscardOldestPolicy` | Loại task chờ đầu queue rồi thử đưa task mới vào | Có thể làm mất sự kiện cũ và phá thứ tự nghiệp vụ |

Một mẫu `CallerRunsPolicy`:

```java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
```

Đoạn trên chỉ minh họa một lựa chọn thay thế cho `AbortPolicy`. Nó không phải lựa chọn mặc định cho mọi loại event. Nếu publisher đang giữ một lock hoặc ở trong transaction, việc bất ngờ chạy listener trên luồng caller có thể tạo độ trễ lớn, chiếm kết nối giao dịch hoặc dẫn đến deadlock nếu listener chờ tài nguyên đang bị caller giữ.

**Điểm đặc biệt của multicaster:** Executor và multicaster là hai tầng chính sách khác nhau. Khi một executor từ chối, cách `SimpleApplicationEventMulticaster` xử lý exception có thể thay đổi theo phiên bản: có triển khai sử dụng đường fallback gọi listener tại chỗ. Khi đó bounded pool vẫn giới hạn **số worker/queue**, nhưng không nhất thiết giới hạn tổng lượng công việc đang chạy nếu nhiều publisher bị buộc chạy listener đồng bộ. Vì vậy “dùng `AbortPolicy`” chưa đủ để tuyên bố hệ thống sẽ fail-fast hoặc drop event dưới tải.

Để có giới hạn đầu vào có thể chứng minh được, cân nhắc một cơ chế admission control ở **trước** `publishEvent` hoặc một queue/broker có khả năng trả lời rõ rằng công việc đã được nhận hay bị từ chối. Không nên che mất sự cố overload bằng cách chỉ thêm log.

## 7. Chọn kích thước pool và queue từ đo lường

Cấu hình hợp lý phụ thuộc loại công việc và mức độ trễ được phép.

### 7.1. Phân biệt CPU-bound và I/O-bound

- **CPU-bound** (serialize lớn, nén, tính toán): số worker quá cao gây context switching và tranh CPU; bắt đầu thử gần số lõi CPU khả dụng rồi benchmark.
- **I/O-bound** (gọi HTTP, JDBC, email): worker thường chờ I/O; có thể cần nhiều luồng hơn CPU core, nhưng số luồng phải phù hợp với connection pool, rate limit của dịch vụ ngoài và timeout.
- **Mixed workload**: nếu listener nhẹ và nặng dùng chung executor, task nặng có thể chiếm hết worker. Cân nhắc pool riêng hoặc đổi đường xử lý event theo nhu cầu nghiệp vụ.

### 7.2. Ước lượng concurrency

Khi tải tương đối ổn định, số tác vụ **đang thực thi** cần thiết để phục vụ lưu lượng trung bình có thể ước lượng từ:

```text
concurrentWorkers ≈ tasksPerSecond × averageExecutionSeconds
```

Ví dụ có **80 lượt gọi listener/giây** và mỗi lần xử lý trung bình **50 ms**:

```text
80 × 0.050 = 4 worker bận trung bình
```

Đây là ước lượng cho khối lượng **đang phục vụ**, chưa bao gồm biến động, percentiles, nghẽn downstream, GC pause, spike traffic hoặc thời gian đợi trong queue. Không dùng “80 event/s” thay “80 listener task/s” khi một event kích hoạt nhiều listener.

Hãy benchmark với tải thật và đặt headroom phù hợp; nếu dịch vụ phía sau chỉ cho phép 10 connection đồng thời, không có lợi khi tạo 200 listener thread cùng tranh 10 connection đó.

### 7.3. Queue không phải bộ đệm vô hạn

Nếu pool có 8 worker và mỗi task giữ worker trung bình 100 ms, thông lượng lý tưởng xấp xỉ 80 task/s khi không có cạnh tranh khác. Nếu queue dài 160 task, chỉ riêng thời gian tiêu thụ backlog đã có thể vào khoảng **2 giây** trong điều kiện lý tưởng ấy. Yêu cầu “xử lý event trong 200 ms” sẽ không tương thích với queue quá dài.

Một queue đủ lớn để hấp thụ burst ngắn là hữu ích, nhưng queue quá lớn có thể biến một sự cố quá tải dễ phát hiện thành độ trễ âm thầm kéo dài. Định kích thước theo **giới hạn thời gian chờ được phép** và thử tải burst, không dựa đơn thuần vào số request trung bình.

### 7.4. Mẫu bắt đầu có kiểm chứng

Không có “bộ thông số tốt nhất” cố định. Một quy trình đơn giản:

1. Đo số **listener tasks/s** ở tải bình thường và các đợt peak.
2. Đo latency p50/p95/p99 của từng listener, tỷ lệ lỗi và mức dùng downstream.
3. Đặt `maxPoolSize` từ giới hạn tài nguyên thực tế; đặt `corePoolSize` cho tải bình thường.
4. Đặt queue nhỏ đủ hấp thụ một burst có thời hạn nhưng không làm vi phạm latency budget.
5. Chọn rõ chính sách khi đầy; tạo test tái hiện quá tải.
6. Quan sát `activeCount`, `poolSize`, `queueSize`, số task bị từ chối/fallback, thời gian chờ queue và tuổi task.
7. Điều chỉnh sau kiểm thử tải thực tế; đừng chỉ tăng kích thước pool/queue để che dấu hiệu quá tải.

## 8. Tác động của @Async và @TransactionalEventListener

### 8.1. Multicaster executor khác với @Async

Có hai cách phổ biến để listener làm việc bất đồng bộ:

**Cách A: Đặt executor vào multicaster.** Các listener hỗ trợ async dispatch qua executor đó:

```java
multicaster.setTaskExecutor(applicationEventExecutor);
```

**Cách B: Dùng @Async ở listener và chỉ định executor.**

```java
@Async("applicationEventExecutor")
@EventListener
public void onOrderSubmitted(OrderSubmitted event) {
    // Xử lý bất đồng bộ nhờ proxy @Async.
}
```

Đoạn B giả định có `@EnableAsync`, bean executor mang tên tương ứng và kiểu `OrderSubmitted` trong ứng dụng.

Với cách B, có thể chọn executor theo từng listener; với cách A, một executor của multicaster thường phục vụ nhiều listener khác nhau. Tránh tự động bật **cả hai cơ chế** mà không hiểu đường đi: việc phân phối qua multicaster và proxy `@Async` có thể tạo hai tầng scheduling, khiến việc tính tải, truyền context và quan sát lỗi khó hơn.

Lỗi xảy ra trong phần thân `@Async void` thường thuộc đường xử lý exception của async proxy; không nên kỳ vọng một `ErrorHandler` gắn trên multicaster luôn nhìn thấy nó.

### 8.2. Transactional listener không mặc nhiên sang pool

`@TransactionalEventListener` gắn việc thực thi với các phase transaction như `AFTER_COMMIT`. Trong Spring hiện đại, adapter transactional listener không hỗ trợ việc chuyển trực tiếp sang executor của multicaster như listener thông thường, vì nó cần gắn callback với transaction context ở thread phát event.

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderSubmitted event) {
    // Callback thực hiện theo phase transaction.
}
```

Đây là đoạn minh họa trong Spring bean. Việc đặt `setTaskExecutor(...)` không tự biến mọi callback `AFTER_COMMIT` thành task trong bounded pool. Nếu muốn làm phần việc nặng sau commit, hãy thiết kế bước enqueue/dispatch được quản lý riêng, kèm chính sách lưu bền vững nếu không được phép mất tác vụ.

### 8.3. Thread context không tự đi theo

Task async thường không tự giữ:

- Transaction đang chạy ở thread publisher.
- MDC/logging context và trace/span context.
- SecurityContext hay request-scoped dữ liệu dùng ThreadLocal.
- Các giả định thứ tự giữa nhiều listener.

Khi cần correlation ID, ưu tiên đưa ID vào payload bất biến. Có thể dùng `TaskDecorator` hoặc Micrometer Context Propagation cho context được hỗ trợ, nhưng không giả định có thể sao chép an toàn transaction hiện hành sang worker thread.

## 9. Backpressure ở đâu mới có ý nghĩa?

**Bounded executor chỉ giới hạn tài nguyên của pool**, chưa chắc giới hạn tốc độ nguồn phát event. Nếu producer vẫn gửi đều 5.000 event/s trong khi listener xử lý được 100 task/s, chính sách quá tải bắt buộc phải có tác dụng ở một nơi nào đó.

Các tầng lựa chọn:

| Tầng | Có thể kiểm soát | Giới hạn |
| --- | --- | --- |
| Admission control trước `publishEvent` | Số yêu cầu được phép phát; trả lỗi/quyết định trì hoãn trước khi công bố | Cần thiết kế tính công bằng, timeout, cách giải phóng quota và phản hồi caller |
| Bounded executor | Thread, queue, độ chờ trong tiến trình | Không tự bền vững, xử lý rejection qua multicaster có thể thay đổi |
| Rate limit ở nguồn | Tốc độ event vào hệ thống | Khó kiểm soát mọi publisher nếu có nhiều luồng/instance |
| Message broker/queue bền vững | Lưu tạm, phân phối độc lập, retry theo chính sách | Thêm độ phức tạp vận hành, cần idempotency và xử lý trùng |
| Transactional outbox | Gắn sự kiện ra ngoài với commit dữ liệu nguồn | Cần tiến trình relay, monitoring và consumer idempotency |

Ví dụ, một event chỉ phục vụ thống kê có thể chấp nhận bỏ một số lần cập nhật nếu số liệu có đường xây dựng lại. Một event kích hoạt hoàn tiền hoặc tạo hóa đơn bắt buộc cần xử lý nhất quán hơn; chỉ dựa vào queue trong RAM là không đủ.

**Chọn policy theo tính chất dữ liệu**. Không áp đặt `DiscardPolicy` hay `CallerRunsPolicy` cho tất cả listener vì một phương án tiện triển khai.

## 10. Giám sát và vận hành bounded executor

Các số liệu tối thiểu nên theo dõi gồm:

- **Pool size / active threads:** `ThreadPoolTaskExecutor.getPoolSize()` và `getActiveCount()` để thấy pool có đang bị sử dụng hết.
- **Queue occupancy:** `getQueueSize()`, so với `getQueueCapacity()` để phát hiện backlog tăng.
- **Task execution latency:** thời gian chạy thực tế của listener (p50/p95/p99).
- **Queue wait latency:** khoảng từ lúc nộp task đến lúc worker bắt đầu thực thi.
- **Rejection / caller-runs / fallback:** số lần executor hết sức chứa, ai xử lý và thời gian phía publisher bị ảnh hưởng.
- **Error rate:** exception của listener, timeout downstream, số lần retry và kết quả cuối.
- **Task age / backlog drain time:** tuổi của task lâu nhất trong queue; tránh chỉ nhìn queueSize vì queue nhỏ vẫn có thể chứa task rất chậm.
- **Shutdown behaviour:** công việc còn trong queue được hoàn tất hay dừng khi tiến trình đóng.

Có thể đặt `ThreadPoolTaskExecutor` thành bean để Spring/Micrometer instrumentation nhận diện, nhưng việc phơi metric thực tế còn phụ thuộc hệ thống quan sát và cấu hình ứng dụng. Tự đo error, rejection và queue wait nơi cần thiết; chỉ nhìn CPU trung bình không phát hiện được tail latency.

Về shutdown, xác định chính sách: có chờ task trong queue không, chờ tối đa bao lâu, có muốn nhận task mới sau tín hiệu đóng hay không. `ThreadPoolTaskExecutor` có các tùy chọn lifecycle như `setWaitForTasksToCompleteOnShutdown(...)` và `setAwaitTerminationSeconds(...)`; mỗi giá trị cần kiểm thử dưới tải. Cấu hình shutdown không thay thế lưu trữ bền vững nếu tiến trình bị kill đột ngột.

## 11. Kiểm thử quá tải và các giới hạn cần xác minh

| Kịch bản | Điều phải kiểm tra |
| --- | --- |
| Dưới ngưỡng | Các listener chạy trên worker thread, có hoàn tất đúng, không backlog kéo dài |
| Đúng ngưỡng queue | Pool ưu tiên queue trước khi mở thêm worker lên `maxPoolSize` theo quy tắc triển khai |
| Pool + queue đều đầy | Chính sách rejection thực tế của executor **và** cách multicaster phản ứng |
| Nhiều listener cho một event | Số task và mức tăng queue, không đếm nhầm một event = một task |
| Listener rất chậm | Tail latency, tuổi task trong queue, downstream connection pool |
| Listener ném lỗi | Lỗi có được quan sát, caller có bị ảnh hưởng, task khác có tiếp tục không |
| Async proxy @Async | Đúng executor và đúng đường exception handling |
| @TransactionalEventListener | Đúng phase transaction; không giả định multicaster executor thay đổi thread |
| Shutdown khi backlog còn | Công việc hoàn tất, bị hủy hoặc fallback như thiết kế |
| Hai loại event tranh tài nguyên | Event ít quan trọng có chiếm hết pool của event quan trọng không |
| Producer phát đồng thời | Race lúc queue đầy; throughput và mức backpressure thực tế |
| Hệ thống restart | Có mất event/task nằm trong bộ nhớ không; có cần cơ chế lưu bền vững không |

**Không kiểm thử overload bằng cách chỉ cho chạy vài event rất nhanh.** Cần giữ worker bận có kiểm soát (như `CountDownLatch` trong ví dụ), lấp đầy queue và quan sát chính xác kết quả. Không dùng `Thread.sleep(...)` đơn độc rồi coi kết quả timing là ổn định.

## 12. Những lỗi cấu hình thường gặp

1. **Chỉ đặt `maxPoolSize` nhưng để queue gần như vô hạn:** pool ít khi mở rộng vượt core, backlog âm thầm tăng.
2. **Đặt `queueCapacity = 0` nhưng `maxPoolSize` quá cao:** có thể tạo bùng nổ thread và làm downstream cạn tài nguyên.
3. **Đặt queue hàng chục nghìn task để “tránh lỗi”:** latency trở nên khó dự đoán, chiếm RAM và khiến shutdown dài.
4. **Mặc định cho rằng `publishEvent` trả về là listener đã xử lý xong:** async chỉ có nghĩa task đã được lên lịch hoặc đường gọi đã đi qua.
5. **Tưởng `AbortPolicy` chắc chắn khiến publisher nhận lỗi:** multicaster có thể can thiệp vào rejection; test theo phiên bản và đường gọi.
6. **Dùng `CallerRunsPolicy` trong transaction dài:** listener có thể bất ngờ chạy tại caller, giữ lock/connection lâu hơn.
7. **Chạy listener xử lý nghiệp vụ quan trọng trên queue in-memory:** process crash có thể mất task chưa chạy.
8. **Dùng chung một pool cho tất cả loại event:** listener chậm có thể làm những event quan trọng bị chờ.
9. **Chồng executor multicaster và `@Async` tùy tiện:** tăng số lớp queue, khó tìm nơi gây trễ và nơi mất context.
10. **Cho rằng mọi listener hỗ trợ async:** transactional listeners có đường lifecycle đặc biệt.
11. **Không ghi nhận task bị từ chối:** số liệu HTTP vẫn xanh nhưng các xử lý phụ có thể không hoàn tất.
12. **Không tính số listener trên mỗi event:** capacity được định theo events/s thay vì tasks/s nên thiếu tài nguyên.
13. **Không có timeout cho I/O trong listener:** một worker có thể bị giữ rất lâu, khiến queue bị lấp đầy.
14. **Không kiểm thử khi shutdown:** event đến muộn có thể chạy khác với khi hệ thống khỏe mạnh.

## 13. Checklist lựa chọn trước khi triển khai

- Sự kiện này có được phép mất khi tiến trình lỗi, hay phải ghi nhận bền vững?
- Có bao nhiêu listener phù hợp cho mỗi event? Tốc độ **listener tasks/s** là bao nhiêu?
- Mỗi listener chủ yếu dùng CPU hay chờ I/O? Downstream chịu được bao nhiêu kết nối đồng thời?
- Mức trễ xử lý tối đa được phép là bao nhiêu? Queue có giúp hấp thụ burst ngắn mà vẫn đáp ứng SLA không?
- `corePoolSize`, `maxPoolSize` và `queueCapacity` đều đã có giới hạn thực tế chưa?
- Khi executor đầy, publisher chờ, fail, chạy listener trực tiếp hay chuyển sang hàng đợi bền vững? Đã test đúng Spring version chưa?
- Có phân biệt executor multicaster với `@Async` không?
- Có transaction callback nào không được chuyển sang pool không?
- Có metric cho queue wait, active threads, rejection và tuổi task không?
- Đã thử tải peak, shutdown và restart chưa?

**Nguyên tắc áp dụng:** Cấu hình bounded executor là bước bắt buộc để kiểm soát worker và backlog trong xử lý event bất đồng bộ. Nhưng giới hạn pool không tự tạo ra giao thức backpressure hoàn chỉnh hoặc bảo đảm giao hàng. Hãy chọn kích thước dựa trên thời gian xử lý, độ trễ cho phép, downstream capacity và đặc biệt là **hành vi khi đầy** đã được kiểm chứng.

## Tài liệu tham khảo

- [Spring Framework — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html)
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Observability Support](https://springframework.org/spring-framework/reference/6.2/integration/observability.html)
