# SimpleAsyncTaskExecutor: mỗi tác vụ một luồng, không tái sử dụng luồng

**SimpleAsyncTaskExecutor** là một triển khai của **TaskExecutor** trong Spring Framework. Khi nhận một tác vụ, nó khởi chạy tác vụ đó trên **một thread mới**. Nó **không duy trì pool các worker để tái sử dụng thread** cho tác vụ kế tiếp. Đây là đặc tính quyết định khi chọn bộ thực thi: cách gửi tác vụ rất đơn giản, nhưng chi phí tạo luồng và mức đồng thời có thể lớn nếu có nhiều lời gọi.

Bài học thuộc chủ đề **Spring Framework - concurrency**, nhóm **Chọn bộ thực thi**. Trọng tâm là hiểu chính xác cơ chế thread-per-task của SimpleAsyncTaskExecutor, giới hạn đồng thời, tác động vận hành, cách dùng với **@Async**, khác biệt với **ThreadPoolTaskExecutor**, và lựa chọn **virtual threads trên JDK 21+** khi phù hợp.

## 1. TaskExecutor là hợp đồng; không đồng nghĩa với thread pool

Spring định nghĩa **TaskExecutor** để chạy một **Runnable**. Vì giao diện này mở rộng hợp đồng **java.util.concurrent.Executor**, lời gọi cốt lõi là:

~~~java
void execute(Runnable task);
~~~

Điểm quan trọng: giao diện nói **gửi tác vụ để thực thi**, chứ không quy định phải có pool. Hai implementation có thể nhận cùng Runnable nhưng điều phối hoàn toàn khác:

| Bộ thực thi | Nơi tác vụ chạy | Tái sử dụng thread? |
| --- | --- | --- |
| **SyncTaskExecutor** | Trực tiếp trên thread gọi execute | Không tạo worker mới |
| **SimpleAsyncTaskExecutor** | Thread mới cho mỗi lần thực thi | **Không** |
| **ThreadPoolTaskExecutor** | Những worker thuộc một thread pool | **Có**, theo cấu hình pool |
| **ConcurrentTaskExecutor** | Ủy quyền cho một java.util.concurrent.Executor khác | Phụ thuộc executor được bọc |

Vì vậy, tên **Async** diễn tả việc tác vụ có thể chạy tách khỏi caller; nó **không bảo đảm** việc thực thi được giới hạn, xếp hàng, quản trị vòng đời giống một thread pool.

## 2. Cơ chế thread-per-task diễn ra thế nào?

Ở cấu hình mặc định dùng platform threads, với mỗi lần gọi **execute(task)**, SimpleAsyncTaskExecutor tạo một Thread mới và chạy task bên trong. Khi Runnable kết thúc, thread đó kết thúc. Lần execute tiếp theo sẽ dùng **một thread khác**, kể cả nếu task trước đã hoàn thành.

~~~text
Thread gọi / HTTP request
  |
  +-- execute(task A) --> tạo thread A --> chạy A --> thread A kết thúc
  |
  +-- execute(task B) --> tạo thread B --> chạy B --> thread B kết thúc
  |
  +-- execute(task C) --> tạo thread C --> chạy C --> thread C kết thúc

Không có vòng lặp worker rảnh -> lấy task tiếp theo từ hàng đợi pool.
~~~

Ba hệ quả thực tế:

1. **Thread identity của hai tác vụ không được tái sử dụng.** Nếu hai task lần lượt chạy, chúng vẫn dùng hai thread khác nhau. Đừng suy luận chỉ từ tiền tố tên thread; phải kiểm tra object thread hoặc hành vi của executor.
2. **Mặc định không có giới hạn số task đang chạy đồng thời** do SimpleAsyncTaskExecutor đặt ra. Khả năng tạo platform thread thực tế vẫn bị giới hạn bởi bộ nhớ, hệ điều hành và tài nguyên của tiến trình.
3. **Không có task queue kiểu ThreadPoolExecutor.** Tác vụ không được gửi vào hàng đợi để một worker đang rảnh xử lý sau; nếu kích hoạt giới hạn đồng thời, hành vi chờ được thực hiện ở phía **submitter** theo cơ chế throttling, như phần dưới.

Tạo một thread platform mới không phải thao tác miễn phí: cần stack và cấu trúc quản lý của JVM/OS, dẫn tới chi phí khởi tạo, chuyển ngữ cảnh và bộ nhớ. Với nhiều công việc rất ngắn, tổng chi phí luồng có thể lớn hơn chi phí của chính task. Với tác vụ I/O chặn lâu, việc tạo nhiều platform threads có thể tăng mức sử dụng bộ nhớ dù CPU không bận tương ứng.

**Không tái sử dụng luồng** khác với **không chạy song song**. Nếu nhiều task được gửi trong thời gian ngắn, chúng có thể đồng thời tồn tại trên các thread khác nhau. Số tác vụ thực sự chạy trên CPU cùng lúc vẫn phụ thuộc số core, scheduler và trạng thái chặn.

## 3. Ví dụ thực thi thật bằng Java 17 và Spring Core

Ta sẽ quan sát hai task **gửi tuần tự** vào cùng một SimpleAsyncTaskExecutor. Mỗi task ghi lại đối tượng Thread của nó. Kết quả không phụ thuộc cách JVM đặt tên luồng hoặc lập lịch CPU.

Tạo dự án Maven tối thiểu theo cấu trúc:

~~~text
simple-executor-demo/
├── pom.xml
└── src/main/java/example/ExecutorIdentityDemo.java
~~~

**pom.xml** — Spring Core 6.2.12 chạy trên Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>simple-executor-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
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
                    <mainClass>example.ExecutorIdentityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/ExecutorIdentityDemo.java**:

~~~java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

public class ExecutorIdentityDemo {
    public static void main(String[] args) throws InterruptedException {
        try (SimpleAsyncTaskExecutor executor =
                     new SimpleAsyncTaskExecutor("lesson-")) {

            AtomicReference<Thread> first = new AtomicReference<>();
            AtomicReference<Thread> second = new AtomicReference<>();

            CountDownLatch firstStarted = new CountDownLatch(1);
            CountDownLatch secondStarted = new CountDownLatch(1);

            executor.execute(() -> {
                first.set(Thread.currentThread());
                firstStarted.countDown();
            });
            firstStarted.await();

            executor.execute(() -> {
                second.set(Thread.currentThread());
                secondStarted.countDown();
            });
            secondStarted.await();

            System.out.println("Hai task đã chạy: "
                    + (first.get() != null && second.get() != null));
            System.out.println("Tái sử dụng cùng thread: "
                    + (first.get() == second.get()));
        }
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

**Stdout của chương trình** (không tính thông điệp của Maven nếu môi trường có in thêm):

~~~text
Hai task đã chạy: true
Tái sử dụng cùng thread: false
~~~

**Giải thích:**

- **firstStarted** và **secondStarted** bảo đảm main đợi đến khi mỗi task đã lưu tham chiếu Thread; không cần ngủ một khoảng đoán trước.
- Hai lệnh **execute** dùng chung một executor, nhưng mỗi lệnh chạy trên thread mới. Phép so sánh dùng **==** kiểm tra đúng danh tính object Thread.
- **try-with-resources** dùng vì SimpleAsyncTaskExecutor trong phiên bản minh họa hỗ trợ **AutoCloseable**. Mọi task trong ví dụ đã đến điểm báo hiệu trước khi thoát scope; phần quản lý task chưa hoàn tất khi đóng executor sẽ được giải thích riêng.
- Ví dụ dựa vào **Spring Core**; không thể chỉ gọi javac lên file này mà không có thư viện Spring trong classpath. Maven quản lý dependency và biên dịch.

Nếu in **Thread.currentThread().getName()**, bạn có thể thấy các tên kiểu lesson-1, lesson-2. Đó là công cụ quan sát hữu ích, nhưng **không nên khẳng định mọi môi trường đều có cùng số thứ tự tên luồng** hoặc dùng tên làm bằng chứng duy nhất cho thread identity.

## 4. Mặc định không giới hạn đồng thời có nghĩa gì?

Theo API của SimpleAsyncTaskExecutor, giá trị mặc định của concurrency limit là **UNBOUNDED_CONCURRENCY** (giá trị -1). Ở chế độ platform thread, nếu hàng trăm lời gọi gửi task gần như đồng thời, executor có thể tạo hàng trăm thread mới; nếu hàng nghìn tác vụ chặn network, khả năng còn tạo thêm rất nhiều luồng.

Ví dụ suy luận:

~~~text
100 request tới cùng lúc
    |
    +--> mỗi request gọi execute(tác vụ chặn I/O 5 giây)
    |
    +--> có thể tồn tại gần 100 thread task trong quãng chờ đó
    |
    +--> nếu tải tăng mạnh và không kiểm soát:
          thêm stack, context switching, tài nguyên OS
~~~

Đây là sơ đồ đặc tính, **không phải cam kết một số luồng cụ thể**: tốc độ gửi việc, thời lượng task và giới hạn tài nguyên của hệ thống ảnh hưởng đến số thread tồn tại đồng thời.

Đặc biệt, **SimpleAsyncTaskExecutor không cung cấp cơ chế lưu trữ task trong hàng đợi có capacity cấu hình sẵn** như ThreadPoolTaskExecutor. Muốn bảo vệ tài nguyên, bạn phải thiết kế giới hạn đồng thời/tốc độ gửi và chính sách từ chối ở đúng tầng.

## 5. setConcurrencyLimit: giới hạn số tác vụ hoạt động, nhưng không tạo pool

Bạn có thể đặt **setConcurrencyLimit(n)** để tối đa n tác vụ được phép thực thi đồng thời. Ví dụ khai báo trong Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration
public class SimpleExecutorConfig {
    @Bean(destroyMethod = "close")
    public SimpleAsyncTaskExecutor perTaskExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("per-task-");
        executor.setConcurrencyLimit(8);
        executor.setTaskTerminationTimeout(5_000);
        return executor;
    }
}
~~~

Đây là **đoạn cấu hình cho ứng dụng đã có Spring Context**, không phải chương trình javac độc lập. **Giới hạn 8 chỉ là ví dụ**; phải chọn số phù hợp CPU, I/O, tài nguyên downstream và yêu cầu độ trễ. Nếu 8 task đang chạy và có task thứ 9 được gửi tới **execute**, hành vi mặc định là **chặn thread gửi tác vụ** cho tới khi có slot trống rồi tạo một thread mới để chạy task thứ 9.

~~~text
concurrencyLimit = 2

execute(A)  -> thread A chạy ----------- hoàn tất
execute(B)  -> thread B chạy ----- hoàn tất
execute(C)  -> caller phải chờ slot
                        |
                        +-- B xong -> tạo thread C mới -> C chạy

C không dùng lại thread B. Không có worker pool để lấy C từ queue.
~~~

| Cấu hình | Hành vi cốt lõi |
| --- | --- |
| Mặc định (-1) | Không throttle số task đang chạy ở phía executor |
| setConcurrencyLimit(8) | Cho tối đa 8 task đồng thời; task gửi thêm có thể khiến submitter chờ |
| setConcurrencyLimit(1) | Mỗi thời điểm chỉ cho một task hoạt động, nhưng vẫn tạo **thread mới** cho từng task |
| setConcurrencyLimit(0) | Không cho phép bắt đầu task; không phải cấu hình để dùng thông thường |
| setRejectTasksWhenLimitReached(true) | Trên Spring Framework **6.2.6+**, chọn từ chối ngay khi đầy thay vì mặc định chờ submitter |

**Phân biệt backpressure với task queue:** khi submitter bị block trong execute, luồng request web cũng có thể bị block. Điều này có thể gây tăng độ trễ hoặc làm cạn request threads khi hệ thống quá tải. Có thể chọn **từ chối sớm** và trả một phản hồi quá tải rõ ràng nếu phiên bản Spring hỗ trợ, hoặc sử dụng executor có hàng đợi hữu hạn và rejection policy được thiết kế riêng.

Nếu bật **setRejectTasksWhenLimitReached(true)**, Spring ném **TaskRejectedException** cho thao tác gửi không được chấp nhận. Người gọi phải xử lý từ chối; nó không có nghĩa task được lưu để chạy sau. Nếu dùng Spring Framework cũ hơn 6.2.6, không giả định phương thức này có sẵn.

**Quan trọng:** giới hạn ở executor chỉ quản lý số task *đang thực thi qua executor đó*, không giới hạn toàn bộ HTTP requests, DB connections, file descriptors hay lời gọi đến mọi instance ứng dụng. Các tài nguyên downstream vẫn cần giới hạn riêng.

## 6. SimpleAsyncTaskExecutor so với ThreadPoolTaskExecutor

Một quyết định thường gặp trong ứng dụng Spring là chọn giữa **mỗi task một thread** và **pool worker được tái sử dụng**.

| Tiêu chí | SimpleAsyncTaskExecutor | ThreadPoolTaskExecutor |
| --- | --- | --- |
| Luồng cho từng task | Tạo mới, kết thúc sau task | Dùng worker thuộc pool |
| Tái sử dụng thread | Không | Có |
| Chi phí khi nhiều task ngắn | Tăng vì liên tục tạo/hủy thread | Thường hiệu quả hơn nhờ tái sử dụng |
| Điều khiển đồng thời | concurrencyLimit; mặc định không giới hạn | corePoolSize, maxPoolSize, queueCapacity |
| Lưu task chờ trong queue của pool | Không có queue tương đương | Có thể có queue được cấu hình |
| Khi quá tải | Mặc định block submitter với limit; phiên bản mới hỗ trợ reject ngay | Phụ thuộc cấu hình queue, pool và rejection |
| Shutdown/lifecycle | Có API close và tùy chọn chờ task, không tham gia phối hợp lifecycle như pool | Có điều khiển lifecycle/pause/shutdown đa dạng hơn |
| Công việc phù hợp | Dùng có chủ đích cho task-per-thread, số lượng vừa phải, hoặc virtual-thread mode | Phù hợp rộng hơn cho khối lượng lớn và thường xuyên trên platform threads |

Ví dụ một pool có giới hạn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class PoolConfig {
    @Bean("boundedPool")
    public ThreadPoolTaskExecutor boundedPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(40);
        pool.setThreadNamePrefix("pool-");
        return pool;
    }
}
~~~

Đây là **đoạn cấu hình Spring** để so sánh, không phải kết quả của một phép thử hiệu năng. Khi `ThreadPoolTaskExecutor` được tạo như một Spring bean, container tự gọi `initialize()` trong lifecycle; gọi thủ công ở đây có thể khởi tạo pool hai lần và không cần thiết. Với ThreadPoolTaskExecutor, hàng đợi ảnh hưởng đến thời điểm pool tạo thêm worker trên core size. Không thể chỉ nhìn maxPoolSize mà kết luận luôn có 8 worker cho mọi tải.

**Tài nguyên không giống năng lực xử lý:** dùng nhiều threads hơn số core không làm tính toán CPU-bound nhanh lên vô hạn. Với I/O-bound, thêm concurrency có thể giúp che thời gian chờ, nhưng phải cân bằng connection pool, rate limit và timeout.

## 7. Tùy chọn virtual threads trên Java 21+

Từ Spring Framework **6.1**, SimpleAsyncTaskExecutor có khả năng dùng **virtual threads của JDK 21** qua:

~~~java
SimpleAsyncTaskExecutor executor =
        new SimpleAsyncTaskExecutor("virtual-task-");
executor.setVirtualThreads(true);
~~~

Đây là **đoạn mã cấu hình cho JDK 21+ và Spring Framework phiên bản hỗ trợ**. Nếu dùng Java 17, không bật tùy chọn này.

**Điểm không thay đổi:** vẫn là mô hình **một virtual thread mới cho mỗi tác vụ**, không có pool tái sử dụng virtual threads. Điều thay đổi là chi phí mỗi luồng: virtual threads được JVM quản lý nhẹ hơn platform threads đối với nhiều tác vụ chặn I/O theo mô hình hỗ trợ. Nói “một thread cho mỗi task” không đồng nghĩa “mỗi task chiếm một platform thread suốt vòng đời” khi chạy chế độ virtual.

**Điểm cần giữ giới hạn:**

- Virtual thread nhẹ **không làm DB connection, RAM, file descriptor hoặc external API quota trở nên vô hạn**.
- Với CPU-bound, số core vẫn là giới hạn thực thi song song.
- Nếu task giữ khóa, blocking không hỗ trợ hoặc gặp tình huống pinning/mounting đặc thù, lợi ích có thể thấp hơn kỳ vọng; cần đo đạc trên runtime thực tế.
- Có thể vẫn cần **setConcurrencyLimit** hoặc semaphore để bảo vệ tài nguyên downstream. Virtual thread tự nó không phải rate limiter.
- Không thể sử dụng platform thread pool sizing như một công thức áp thẳng cho virtual-thread-per-task. Quyết định phải dựa vào loại tải và các tài nguyên thực sự bị giữ.

**Ví dụ định hướng lựa chọn:** một ứng dụng Java 21 có hàng nghìn tác vụ I/O độc lập ngắn hoặc vừa có thể cân nhắc virtual threads; một hệ thống có CPU nặng nên kiểm soát mức thực thi theo CPU thay vì tăng số task chạy vô hạn.

## 8. Sử dụng cụ thể với @Async trong Spring

**@Async** đánh dấu phương thức có thể được Spring gọi qua một executor thay vì chạy hoàn toàn trên thread của caller. Bạn có thể chọn executor có tên để tránh phụ thuộc vào cấu hình mặc định của ứng dụng.

Cấu hình Spring (giả sử ứng dụng có Spring Context và dependency cho @Async):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean(name = "perTaskExecutor", destroyMethod = "close")
    public SimpleAsyncTaskExecutor perTaskExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("async-task-");
        executor.setConcurrencyLimit(12);
        executor.setTaskTerminationTimeout(5_000);
        return executor;
    }
}
~~~

Service minh họa:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PriceService {
    @Async("perTaskExecutor")
    public CompletableFuture<Integer> calculate(int basePrice) {
        int result = basePrice + 10;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Khi **một bean khác** gọi **priceService.calculate(100)** qua Spring proxy, lời gọi thực thi trên một thread do perTaskExecutor tạo. Caller nhận đối tượng tương lai để đợi hoặc nối các bước, ví dụ:

~~~java
CompletableFuture<Integer> price = priceService.calculate(100);
CompletableFuture<String> text =
        price.thenApply(value -> "Giá: " + value);
String result = text.join();
~~~

Đây là **đoạn minh họa trong một phương thức**, giả sử priceService đã được inject. Khi hoàn tất thành công, **result** có giá trị **"Giá: 110"**. Lệnh **join()** chặn nếu kết quả chưa sẵn sàng; không có bảo đảm tự động rằng caller luôn chạy tiếp mà không chờ.

Tại sao phương thức @Async trả về **completedFuture**? Phần thân phương thức đã được Spring interceptor gọi bất đồng bộ trên executor; nó có thể trả về một future biểu diễn kết quả vừa tính. Spring tạo phương tiện bất đồng bộ cho caller ở ranh giới proxy. Bọc thêm **CompletableFuture.supplyAsync** bên trong phương thức không cần thiết có thể khiến task nhảy thêm sang executor khác và làm phức tạp quản trị.

**Các điểm tích hợp không được nhầm:**

- **@EnableAsync** (hoặc cấu hình tương đương) phải được bật.
- Trong chế độ proxy thông thường, lời gọi **this.calculate(...)** từ cùng bean bỏ qua interceptor; không chắc được chuyển sang thread mới.
- **@Async("perTaskExecutor")** chọn executor tường minh; không giả định mọi ứng dụng Spring Boot đều mặc định dùng SimpleAsyncTaskExecutor. Cách resolve executor phụ thuộc Spring/Boot config và bean hiện có.
- **@Async void** không cho caller một future để lấy ngoại lệ; xem cơ chế **AsyncUncaughtExceptionHandler** nếu cần. Với **Future/CompletableFuture**, caller có thể theo dõi thành công hoặc lỗi.
- Cần tính đến **rejection và blocking ngay tại thời điểm gửi task** nếu concurrency limit đã đạt, dù tên phương thức là @Async.

## 9. Luồng mới và dữ liệu theo thread: cẩn thận với ngữ cảnh

Các giá trị như **MDC logging**, **SecurityContext**, transaction hoặc request attributes thường có liên hệ với thread hiện tại. Một thread mới của SimpleAsyncTaskExecutor **không mặc nhiên được bảo đảm** có đầy đủ những giá trị từ caller theo đúng ý nghĩa request.

Ví dụ một lời gọi HTTP gắn requestId vào log MDC. Nếu task chạy ở thread mới, log trong task có thể mất requestId nếu không có cơ chế chuyển ngữ cảnh. Không nên xử lý bằng cách nhét dữ liệu request vào field singleton để “thread nào cũng đọc được”: như vậy lại gây rò rỉ dữ liệu liên request.

Thay vào đó:

1. **Truyền dữ liệu nghiệp vụ** cần thiết qua tham số hoặc immutable request snapshot.
2. Dùng cơ chế **TaskDecorator** của Spring cho nhu cầu logging/tracing context phù hợp. Wrapper phải sao chép và dọn ngữ cảnh theo phạm vi công việc rõ ràng; đặc biệt không tự ý chuyển toàn bộ ngữ cảnh bảo mật.
3. Nếu cần chuyển **SecurityContext**, sử dụng lớp tích hợp Spring Security phù hợp với mô hình phân quyền và vòng đời task.
4. Không giả định một transaction đang mở ở caller sẽ tự chuyển theo thread; định nghĩa transaction boundary tại nơi thực thi thực tế.

**Không tái sử dụng thread** có thể giảm một kiểu lỗi “thread pool dùng lại thread với ThreadLocal cũ”, nhưng **không giải quyết bài toán context propagation** và không thay cho cleanup đúng cách. Dữ liệu request vẫn phải có owner rõ ràng.

## 10. Quản lý ngoại lệ của task

Với SimpleAsyncTaskExecutor:

- Nếu chạy qua **execute(Runnable)**, exception xảy ra ở task thread; caller đã trả khỏi execute thường không thể bắt exception ấy bằng try/catch bao quanh lời gọi submit sau khi task bắt đầu. Cần logging/error handling phù hợp với môi trường.
- Nếu chạy qua API **submit(Callable/T)** có Future, caller có thể lấy kết quả bằng get() và xử lý ExecutionException. Một Future không biến task thành synchronous; điểm get có thể block.
- Với **@Async trả CompletableFuture**, caller có thể dùng **exceptionally**, **handle**, **whenComplete** để xử lý hoặc quan sát lỗi theo ngữ nghĩa CompletableFuture.
- Nếu cấu hình giới hạn và executor **từ chối tại lúc gửi**, đó là lỗi **submission** chứ không phải lỗi chạy ở worker. Cần phân biệt hai đường lỗi này khi trả response và ghi log.

Ví dụ kết hợp future trong phần service minh họa:

~~~java
CompletableFuture<String> safeText = priceService.calculate(100)
        .thenApply(price -> "Giá: " + price)
        .exceptionally(error -> "Tạm thời không có giá");
~~~

Đây là **đoạn minh họa** về một nhánh phục hồi sau khi future đã được trả. **Nếu việc gọi calculate đã ném lỗi ngay khi submit bị từ chối**, đoạn exceptionally chưa có future để gắn vào; cần xử lý riêng ở nơi gọi. Trên production, fallback chỉ được áp dụng khi nghiệp vụ cho phép, đồng thời lưu lại nguyên nhân.

## 11. Shutdown và vòng đời: không có pool để dọn theo cách của pool

Mỗi task tạo một thread mới và không có tập worker lâu dài để giữ lại. Vì vậy, vòng đời của SimpleAsyncTaskExecutor có những điểm riêng:

- Nó cung cấp **close()** trong các phiên bản Spring hiện đại. **Đóng executor không có nghĩa mọi task đã hoàn tất tự động với thời gian chờ vô hạn**.
- **setTaskTerminationTimeout(milliseconds)** yêu cầu thời gian chờ task kết thúc khi close. Giá trị mặc định là **0**, nghĩa là không chờ. Khi bật timeout dương, executor phải **theo dõi các thread đang hoạt động**, có thêm overhead, đáng cân nhắc khi số task cực lớn.
- Không nên coi SimpleAsyncTaskExecutor là một **pool có lifecycle start/stop phối hợp** tương tự ThreadPoolTaskExecutor. Nó không cung cấp cơ chế tạm dừng/tiếp tục worker pool; các thread đã bàn giao đang chạy không thể quản trị tập trung như worker thuộc pool.
- Một task chạy lâu không phản ứng với interrupt hoặc I/O có thể tiếp tục tồn tại ngay cả khi hệ thống muốn đóng; cần deadline và cơ chế cancellation ở tầng tác vụ/công cụ I/O.

Trong ví dụ cấu hình trước, **@Bean(destroyMethod = "close")** cho Spring gọi close khi bean bị hủy. **setTaskTerminationTimeout(5_000)** là chính sách chờ tối đa 5 giây khi đóng; nó không thay thế timeout của HTTP client hay truy vấn DB.

Nếu cần shutdown được phối hợp chặt với lifecycle ứng dụng, kiểm soát hàng đợi và chính sách từ chối, thông thường **ThreadPoolTaskExecutor** là lựa chọn linh hoạt hơn.

## 12. Chi phí, tải cao và trường hợp không nên chọn

Hãy xét task loại A và B:

**A — hàng nghìn phép tính nhỏ, chạy dưới vài mili giây.** Một SimpleAsyncTaskExecutor trên platform threads tạo luồng mới cho từng phép tính. Chi phí khởi tạo/hủy, lập lịch và context switching có thể chiếm tỷ lệ lớn so với công việc. Pool cố định có giới hạn có thể hợp lý hơn, nhưng phải đo throughput và latency.

**B — nhiều lời gọi I/O có thể chặn vài giây.** Với platform threads, mỗi task có thể giữ một thread trong lúc đợi. Nếu gửi không giới hạn, số thread phình theo tải. Virtual threads trên JDK 21 có thể cải thiện chi phí luồng cho tình huống này, nhưng request concurrency, connection pool và giới hạn dịch vụ đích vẫn có thể cạn.

**C — một số tác vụ ít, độc lập, ngắn hoặc có mục tiêu thử nghiệm rõ.** Mô hình per-task-thread đơn giản và dễ quan sát có thể đủ. Khi thành phần này làm executor cho workload lớn lâu dài, cần đánh giá lại.

### Dấu hiệu nên xem lại cấu hình

- Số threads sống tăng theo lưu lượng, kèm bộ nhớ JVM/OS hoặc native thread pressure tăng.
- Latency ở điểm gửi task tăng vì **setConcurrencyLimit** làm block submitter.
- Nhiều request thread chờ để gửi tác vụ; chờ này không nằm trong thời gian chạy task mà dễ bị bỏ qua khi đo.
- Task bị từ chối hoặc JVM khó tạo thread khi lượng yêu cầu tăng.
- Tác vụ I/O lâu không có timeout khiến thread/tài nguyên tích tụ.
- Không có cơ chế giới hạn tác vụ gọi đến database/external service.
- Việc test chỉ đo throughput trung bình, chưa đo p95/p99 latency, số task active và overload behavior.

**Tối ưu không chỉ là đổi executor.** Cần giảm blocking không cần thiết, dùng batching khi hợp lý, bảo vệ downstream, kiểm soát queue và tổng khối lượng công việc; chọn executor theo CPU-bound/I/O-bound cùng yêu cầu vận hành.

## 13. Kiểm tra và quan sát đúng đặc tính executor

Để kiểm chứng **không tái sử dụng luồng**, ví dụ ở mục 3 đã so sánh **Thread identity** của hai task gửi tuần tự. Có thể mở rộng test:

1. Gửi nhiều task, ghi lại **Thread.currentThread()** và số task bắt đầu/kết thúc.
2. Kiểm tra rằng mỗi task chạy trên thread riêng thay vì kết luận từ thứ tự log hay tên thread.
3. Với concurrency limit N, tạo N tác vụ giữ **CountDownLatch** rồi gửi task thứ N+1 từ **một submitter thread khác**. Kiểm tra caller bị chờ hoặc reject theo cấu hình; sau đó release latch để test không deadlock.
4. Với Spring context, xác nhận bean **@Async("perTaskExecutor")** thật sự được gọi qua proxy; nếu test gọi trực tiếp new Service() thì annotation không được áp dụng.
5. Test failure, overload và shutdown, không chỉ đường thành công.

Tuy nhiên, test song song dựa hoàn toàn vào **Thread.sleep** rất dễ nhiễu do scheduler. Dùng CountDownLatch/Barrier để điều phối; luôn có timeout test để phát hiện treo, và dọn executor trong finally/try-with-resources.

### Các chỉ số hữu ích

| Nhóm đo | Câu hỏi cần trả lời |
| --- | --- |
| Task submitted / started / completed | Có tác vụ nào bị tồn đọng hoặc thất bại? |
| Thời gian execute từ phía submitter | Caller có bị block do concurrencyLimit? |
| Task execution duration | Task chậm vì nghiệp vụ hay I/O? |
| Thread counts / memory | Tải có khiến platform threads tăng nguy hiểm? |
| Rejections / exceptions | Quá tải xảy ra ở submission hay worker? |
| Downstream pool / rate limit | Database, API đích có bị nghẽn trước executor? |

Không nên dựa vào một metric “active threads trong pool” không tồn tại theo kiểu pool worker của SimpleAsyncTaskExecutor. Nếu cần số task đang chạy, có thể ghi nhận bằng instrumentation hoặc wrapper rõ ràng; đừng tự mặc định API này cung cấp mọi metric của ThreadPoolTaskExecutor.

## 14. Những hiểu nhầm quan trọng

**“SimpleAsyncTaskExecutor là một thread pool đơn giản.”** Sai. Nó tạo thread mới cho từng task, không tái sử dụng worker như pool.

**“Không tái sử dụng thread nghĩa là mỗi lần chỉ chạy một tác vụ.”** Sai. Mặc định nhiều tác vụ có thể chạy đồng thời trên nhiều thread mới.

**“Đặt concurrencyLimit(10) thì luôn có sẵn 10 worker.”** Sai. Giới hạn là số task có thể đồng thời hoạt động; executor vẫn tạo thread mới cho mỗi tác vụ và không giữ 10 worker để tái sử dụng.

**“Giới hạn đầy thì tác vụ tiếp theo nằm trong queue.”** Không theo cơ chế queue của pool. Với cấu hình mặc định khi có limit, thread gửi tác vụ bị block cho tới khi có slot. Spring 6.2.6+ còn có tùy chọn từ chối ngay.

**“Gửi task bằng @Async bảo đảm request thread không bao giờ chặn.”** Sai. Dù phần thực thi task được chuyển thread, điểm submit có thể block khi executor throttle, và lời gọi get()/join() sau đó vẫn chặn.

**“Virtual threads là pool mới và không còn giới hạn tài nguyên.”** Sai. Virtual thread vẫn per-task; database connection, memory và throughput dịch vụ ngoài vẫn hữu hạn.

**“Nếu thread của task mới hoàn toàn thì không cần truyền request context.”** Sai. Thread mới càng không thể tự biết dữ liệu nghiệp vụ của caller nếu không truyền qua tham số hoặc context propagation được quản lý.

**“Đóng executor mặc định sẽ đợi tất cả task chạy xong.”** Không nên giả định. Cần đọc chính sách close/termination timeout của phiên bản dùng và lựa chọn rõ ràng.

## 15. Câu hỏi tự kiểm tra

1. **Task A xong trước khi gửi B. SimpleAsyncTaskExecutor có dùng lại thread A cho B không?** Không. B có thread mới.
2. **Nếu cấu hình concurrencyLimit=2 và hai task đang chạy, task thứ ba được submit như thế nào?** Mặc định caller bị chặn cho tới khi có slot; không có queue worker pool.
3. **Muốn nhiều task ngắn tái sử dụng worker, dùng gì?** Xem xét ThreadPoolTaskExecutor với core/max/queue/rejection được cấu hình đúng.
4. **Bật setVirtualThreads(true) trên Java 21 thì có dùng thread pool không?** Không. Vẫn tạo virtual thread mới cho mỗi task.
5. **Nếu @Async không hoạt động do một method trong cùng bean gọi chính mình?** Vì self-invocation bỏ qua Spring proxy trong chế độ proxy thông thường, không phải do SimpleAsyncTaskExecutor không tạo thread.
6. **Exception của task và exception tại lúc submit khác nhau thế nào?** Lỗi task xảy ra sau khi worker bắt đầu; lỗi từ chối tại submission xảy ra ngay ở caller khi không nhận tác vụ.
7. **Giới hạn số task đồng thời có thay thế giới hạn DB connection không?** Không. Cần kiểm soát resource đích và các hành vi retry/timeout riêng.
8. **Làm sao xác nhận hai task không dùng cùng một thread?** Lưu và so sánh object Thread.currentThread() trong các task, thay vì chỉ nhìn log không bảo đảm thứ tự.

## 16. Cách đưa ra lựa chọn

Khi đánh giá SimpleAsyncTaskExecutor, hãy trả lời theo thứ tự:

1. **Tải là CPU-bound hay I/O-bound?** Bao nhiêu task/giây, thời gian p95/p99 mỗi task và điểm chặn chính?
2. **Có cần tái sử dụng platform threads không?** Nếu có nhiều công việc nhỏ lặp lại, pool thường có lợi.
3. **Có thể giới hạn số task active và kiểm soát submission không?** Nếu đặt limit, chấp nhận block caller hay muốn reject sớm?
4. **Java đang chạy phiên bản nào?** JDK 21+ và Spring hỗ trợ virtual threads có thể thay đổi lựa chọn, nhưng không thay đổi giới hạn downstream.
5. **Ai quản lý lifecycle, lỗi và context?** Có yêu cầu shutdown phối hợp, propagation, metrics và chính sách quá tải không?

**Kết luận:** SimpleAsyncTaskExecutor thật sự **tạo một thread mới cho từng tác vụ và không tái sử dụng thread**. Đây là đặc trưng thiết kế cần hiểu trước khi dùng, không phải lỗi của implementation. Nó phù hợp khi mô hình thread-per-task được chọn có chủ đích và mức đồng thời được kiểm soát; với tải platform-thread lớn, ngắn và lặp lại, **ThreadPoolTaskExecutor** thường hợp lý hơn. Trên Java 21+, **virtual threads** là một lựa chọn đáng đánh giá cho workload I/O, nhưng vẫn phải bảo vệ các nguồn lực hữu hạn.

**Tài liệu nên tra cứu:** Spring Framework Reference — *Task Execution and Scheduling*; Javadoc *org.springframework.core.task.SimpleAsyncTaskExecutor* và *org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor*; Java 21 documentation về virtual threads.
