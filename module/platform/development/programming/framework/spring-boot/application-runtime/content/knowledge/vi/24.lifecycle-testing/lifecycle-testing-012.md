# Dùng timeout và tín hiệu hoàn thành thay cho chờ cố định trong kiểm thử bất đồng bộ

## 1. Vấn đề: bài test chạy xanh trên máy cá nhân nhưng đỏ ngẫu nhiên trong CI

Trong Java và Spring Boot, nhiều công việc **không kết thúc ngay trên thread gọi**: phương thức **@Async**, một task trong **ExecutorService**, callback của **CompletableFuture**, **@Scheduled**, request MVC asynchronous, listener nhận sự kiện và **SmartLifecycle.stop(Runnable)** đều có thể hoàn tất ở thời điểm khác.

Một cách kiểm thử tưởng như đơn giản là:

~~~java
service.startAsyncJob();
Thread.sleep(1000);
assertEquals("DONE", repository.findStatus());
~~~

Đây là **đoạn minh họa anti-pattern**, không phải chương trình độc lập; các object và method cần được khai báo trong dự án. Test này có ít nhất ba vấn đề:

1. Nếu job hoàn thành trong 20 ms, test vẫn mất thêm gần 980 ms để đợi vô ích.
2. Nếu CI chậm, JVM đang GC, executor quá tải hoặc remote I/O chậm hơn một giây, test thất bại mặc dù logic có thể đúng.
3. Nếu job không chạy, test chỉ báo kết quả cuối sai, không cho biết task đã **bắt đầu**, đang **chờ điều kiện**, đã **bị lỗi** hay chưa từng được submit.

**Nguyên tắc:** đừng đoán lúc công việc kết thúc bằng một số mili-giây cố định. Hãy chờ **một tín hiệu hoặc điều kiện có ý nghĩa**, nhưng **mọi lần chờ trong test phải có deadline** để không treo vô hạn.

~~~text
Cách mong manh:
@Test thread -> submit work -> sleep(1000) -> assert
                               |
                          đoán thời gian

Cách có kiểm soát:
@Test thread -> submit work
                 |
                 +-- worker báo STARTED
                 +-- test chờ STARTED (timeout)
                 +-- test kiểm tra trạng thái trung gian
                 +-- test phát RELEASE
                 +-- worker báo COMPLETED / Future trả kết quả
                 +-- test chờ COMPLETED (timeout)
                 +-- assert kết quả và cleanup
~~~

Bài viết theo **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1 và JUnit Jupiter 5**. Mục tiêu không phải thay mọi dạng chờ bằng một công cụ duy nhất, mà là chọn đúng công cụ cho **hợp đồng hoàn thành** cần kiểm chứng, bao gồm các tình huống startup, shutdown và cancellation.

## 2. Phân biệt bốn loại thời điểm trong một bài test bất đồng bộ

Một task không phải chỉ có hai trạng thái “chưa xong” và “đã xong”. Tối thiểu nên phân biệt:

| Mốc | Ý nghĩa | Tín hiệu hữu ích |
| --- | --- | --- |
| **SUBMITTED** | Task đã được đặt vào executor/queue | Return của submit hoặc API tương ứng |
| **STARTED** | Code task thực sự đi vào đoạn nghiệp vụ | CountDownLatch, observer hoặc callback được kiểm soát |
| **COMPLETED** | Task đã kết thúc, thành công hoặc thất bại | Future/CompletionStage, CountDownLatch trong finally |
| **CLEANED_UP** | Tài nguyên đã được đóng/destroy, không còn phục vụ | @PreDestroy, SmartLifecycle callback, trạng thái close |

**SUBMITTED không đồng nghĩa STARTED** nếu executor có queue. **STARTED không đồng nghĩa COMPLETED** nếu task đang chờ I/O hoặc latch. **COMPLETED không đồng nghĩa CLEANED_UP** nếu executor/context còn sống.

Ví dụ test muốn chứng minh **ApplicationContext chờ component dừng xong** không thể chỉ chờ signal “đã yêu cầu stop”; cần thêm signal **callback.stop đã chạy** và Future của **context.close()** thực sự hoàn tất.

### 2.1. Vì sao test dựa vào thời gian luôn có race?

~~~text
CI khỏe:
0 ms: submit
5 ms: task done
1000 ms: test assert -> PASS

CI quá tải:
0 ms: submit
1000 ms: test assert -> FAIL
1400 ms: task done

Tăng sleep lên 3000 ms?
- Chậm hơn mọi lần test
- Không bảo đảm khi CI còn chậm hơn
- Che mất thứ tự sự kiện thực tế
~~~

Vấn đề không phải chọn sai 1000 ms mà là **test dùng thời gian trôi qua thay cho bằng chứng task đã đạt mốc cần kiểm tra**.

### 2.2. Có được dùng thời gian trong test không?

Có. **Timeout** là điều kiện thất bại có giới hạn, không phải **thời gian ngủ cố định trước assertion**. Khác nhau:

- **Thread.sleep(1000):** luôn chờ khoảng một giây, không quan tâm sự kiện đã xảy ra chưa.
- **latch.await(1, SECONDS):** trả về ngay khi count về 0, hoặc false nếu hết hạn.
- **future.get(1, SECONDS):** trả về ngay khi task kết thúc, hoặc ném TimeoutException nếu hết hạn.
- **condition-await atMost(1s):** kiểm tra đến khi điều kiện đúng, có giới hạn.

Các giá trị timeout phải phản ánh **ngân sách kiểm thử hợp lý**, không được coi là bảo đảm phần cứng/scheduler hoàn tất đúng một số mili-giây.

## 3. Công cụ Java thường dùng: chọn theo hợp đồng

| Công cụ | Khi nào nên dùng | Kết quả khi quá hạn |
| --- | --- | --- |
| **CountDownLatch.await(timeout, unit)** | Chờ một hoặc nhiều event có tín hiệu rõ | Trả **false** |
| **Future.get(timeout, unit)** | Chờ task hoàn tất và lấy kết quả/lỗi | Ném **TimeoutException** |
| **CompletableFuture.get(timeout, unit)** | Chờ completion stage có kết quả | Ném **TimeoutException** |
| **CompletableFuture.join()** | Lấy kết quả khi chắc chắn đã complete | Không nhận timeout trực tiếp; có thể chờ vô hạn |
| **Semaphore.tryAcquire(timeout, unit)** | Chờ quyền truy cập/handoff | Trả false |
| **BlockingQueue.poll(timeout, unit)** | Chờ message/event gửi qua queue | Trả null |
| **Condition.await(timeout, unit)** | Chờ state predicate có lock | Trả trạng thái deadline |
| **Thread.join(millis)** | Chờ thread tự tạo kết thúc | Trả sau timeout hoặc khi thread chết; phải kiểm tra isAlive |
| **Awaitility await().atMost(...)** | Chờ một điều kiện cuối cùng/eventually assertion | Assertion timeout từ thư viện |
| **JUnit @Timeout** | Giới hạn thời gian tổng của test | Test bị đánh dấu thất bại khi vượt deadline |

Không có công cụ nào tự động biến một API async thành API có transaction, retry hoặc durability. Chúng chỉ giúp **test quan sát completion theo điều kiện rõ ràng**.

### 3.1. CountDownLatch: một tín hiệu một lần

~~~java
CountDownLatch done = new CountDownLatch(1);
worker.runAsync(done::countDown);

assertTrue(done.await(2, TimeUnit.SECONDS));
~~~

Đây là snippet, giả định worker nhận callback. Với **CountDownLatch(1)**, mỗi lần **countDown()** sẽ làm bộ đếm về 0 và mở cho các thread đang await. **await(timeout)** có thể trả ngay nếu signal đã được phát trước khi test bắt đầu chờ, nên không mất event như một thông báo chỉ tồn tại tại một thời điểm.

Một latch **không reset** sau khi về 0. Nếu cần chu kỳ nhiều vòng hoặc reusable gate, dùng **Phaser**, **CyclicBarrier** hoặc tạo latch mới cho từng lần test/task.

### 3.2. Future: completion đi kèm kết quả và exception

~~~java
Future<String> result = executor.submit(() -> "ready");
assertEquals("ready", result.get(2, TimeUnit.SECONDS));
~~~

Nếu task ném exception, **Future.get(...)** ném **ExecutionException**, trong đó **getCause()** thường là lỗi của task. Nếu hết hạn, ném **TimeoutException** nhưng **task không tự bị hủy** chỉ vì người gọi đã hết thời gian chờ.

### 3.3. CompletableFuture: completion có thể thành công hoặc lỗi

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "ready");

assertEquals("ready", future.get(2, TimeUnit.SECONDS));
~~~

Trong ví dụ này, get(timeout) giúp test không treo vô hạn. **join()** không có overload nhận Duration/timeout trong Java 17, nên chỉ dùng khi đã có bằng chứng future complete hoặc đặt deadline bên ngoài một cách phù hợp.

**CompletableFuture.orTimeout(...)** và **completeOnTimeout(...)** thay đổi trạng thái/giá trị completion của chính stage được cấu hình; không đồng nghĩa underlying I/O hoặc computation đã bị hủy. Khi test, thường dễ hiểu hơn nếu dùng **get(timeout)** mà không làm thay đổi đối tượng đang kiểm thử.

## 4. Demo Java 17 chạy độc lập: STARTED → RELEASE → COMPLETED

Tạo file **SignalInsteadOfSleep.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class SignalInsteadOfSleep {

    public static void main(String[] args) throws Exception {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();

                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new TimeoutException(
                            "Worker never received release signal");
                }

                return "READY";
            });

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("Worker did not start");
            }

            if (future.isDone()) {
                throw new AssertionError(
                        "Worker finished before release");
            }

            release.countDown();

            String value = future.get(2, TimeUnit.SECONDS);
            System.out.println(value);
        } finally {
            release.countDown();
            executor.shutdownNow();
            if (!executor.awaitTermination(
                    2, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac SignalInsteadOfSleep.java
java SignalInsteadOfSleep
~~~

**Stdout của chương trình khi hoàn tất thành công:**

~~~text
READY
~~~

Đây là ví dụ có đầy đủ imports, class và main, không phụ thuộc Spring. Ba thao tác đồng bộ chủ chốt:

1. **started.await(2s)** bảo đảm worker đã bước vào callable, thay vì dự đoán qua sleep.
2. **future.isDone()** ngay sau started là false vì worker đang đợi **release**, trừ khi deadline bên trong worker đã hết; nếu trường hợp đó xảy ra thì test báo lỗi rõ.
3. **release.countDown()** mở gate; **future.get(2s)** đợi chính completion và lấy kết quả.

Khối **finally** phát release một lần nữa để không bỏ lại worker bị block nếu assertion trước đó lỗi; **CountDownLatch.countDown()** là idempotent sau khi count bằng 0. Sau đó executor được yêu cầu shutdown và chờ trong giới hạn.

### 4.1. Vì sao worker vẫn có timeout bên trong?

Chờ của **test** và chờ của **worker** là hai deadline khác nhau. Nếu test lỗi giữa chừng hoặc thread test bị interrupt, worker vẫn không nên chờ vô hạn trên latch. Deadline nội bộ năm giây là **hàng rào dự phòng** của fixture, không phải một sleep.

### 4.2. Tại sao không dùng một boolean thường?

Một biến:

~~~java
boolean completed = false;
~~~

được viết từ worker và đọc từ test ở thread khác có thể gặp vấn đề visibility. **CountDownLatch**, **Future**, **AtomicBoolean**, **volatile** và primitives đồng bộ có các quan hệ memory visibility phù hợp.

Chỉ chuyển sang:

~~~java
volatile boolean completed;
~~~

và poll bằng while loop không tự giải quyết được CPU spinning hoặc timeout. Với event một lần, latch/Future thường diễn đạt hợp đồng rõ ràng hơn.

### 4.3. happens-before quan trọng hơn timestamp

Khi một worker gọi **CountDownLatch.countDown()**, các hành động trước countDown có quan hệ **happens-before** với các hành động sau khi một thread khác **await** thành công trên latch đó.

Do vậy:

~~~java
result = "DONE";
done.countDown();
~~~

và sau khi **done.await(...)** thành công, test đọc result theo đúng quan hệ đồng bộ. **Thread.sleep(...)** không tự thiết lập quan hệ happens-before như vậy; chỉ đợi qua thời gian không phải bảo đảm visibility.

## 5. Dùng @Async trong Spring Boot: đừng kiểm tra bằng sleep

Đối với Spring Boot, một method:

~~~java
@Async
public CompletableFuture<String> generateReport(String id) {
    return CompletableFuture.completedFuture("report:" + id);
}
~~~

là snippet cần bean Spring, **@EnableAsync** và **lời gọi đi qua Spring proxy**. Khi gọi từ một bean khác, invocation có thể chạy trên executor thread và caller nhận CompletableFuture để chờ completion.

**Cẩn trọng self-invocation:** nếu một method trong cùng object gọi **this.generateReport(...)**, mặc định proxy-based @Async không intercept call nội bộ, nên việc test bằng Thread.sleep có thể che lỗi method không async thật. Test phải gọi qua một **Spring-injected bean/proxy**.

Nếu method trả **void**, caller không có Future để quan sát exception/completion trực tiếp. Khi có thể, hãy trả một **CompletableFuture** hoặc thiết kế một event/callback rõ ràng để kiểm thử.

### 5.1. Mô hình test ổn định

Test không nên chờ “khoảng một giây để @Async xong”. Thay vào đó:

- Fake dependency có **entered latch** để báo method async đã vào thực sự.
- Fake dependency có **release latch** để giữ công việc ở một điểm có chủ đích.
- Test chờ entered với timeout.
- Test xác nhận Future chưa hoàn tất khi dependency chưa được release.
- Test phát release.
- Test lấy kết quả bằng **future.get(timeout)**.
- Test luôn release trong finally để tránh làm rò worker thread.

Đây là một kiểm thử ordering, không phải một bài benchmark.

## 6. Ví dụ Spring Boot 3.3 + JUnit 5 hoàn chỉnh

Dự án sau dùng Spring Boot không có web server, tập trung kiểm tra **@Async**, với fake gateway được điều khiển bằng hai latch. Các lớp và file đều có thể được biên dịch trong một Maven project Java 17+.

### 6.1. Cấu trúc

~~~text
async-lifecycle-test-demo/
  pom.xml
  src/main/java/com/example/lifecycle/AsyncLifecycleDemo.java
  src/test/java/com/example/lifecycle/AsyncReportTest.java
  src/test/java/com/example/lifecycle/SmartLifecycleStopTest.java
  src/test/java/com/example/lifecycle/ContextCloseSignalTest.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>async-lifecycle-test-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot starter test cung cấp **JUnit Jupiter** và những integration cần thiết cho **@SpringBootTest**. Ví dụ cố ý **không thêm spring-boot-starter-web**, vì HTTP server không cần thiết khi test một service async và context lifecycle.

### 6.3. AsyncLifecycleDemo.java

Tạo **src/main/java/com/example/lifecycle/AsyncLifecycleDemo.java**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableAsync
public class AsyncLifecycleDemo {

    public static void main(String[] args) {
        SpringApplication.run(AsyncLifecycleDemo.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class AsyncConfiguration {

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("report-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(3);
        return executor;
    }
}

interface ReportGateway {
    String fetch(String id);
}

@Component
class DefaultReportGateway implements ReportGateway {

    @Override
    public String fetch(String id) {
        return "report:" + id;
    }
}

@Service
class ReportService {

    private final ReportGateway gateway;

    ReportService(ReportGateway gateway) {
        this.gateway = gateway;
    }

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String value = gateway.fetch(id);
        return CompletableFuture.completedFuture(value);
    }
}
~~~

**Giải thích:**

- **@EnableAsync** kích hoạt xử lý @Async qua Spring infrastructure.
- **@Async("reportExecutor")** chọn đúng bean ThreadPoolTaskExecutor có tên đã khai báo.
- **ReportService** phải được gọi qua bean Spring (proxy), không gọi trực tiếp trên instance được tạo bằng new.
- **ReportGateway** là dependency có thể thay bằng fake trong test.
- Method trả **CompletableFuture** giúp caller kiểm tra completion và exception.
- ThreadPoolTaskExecutor được Spring quản lý; cấu hình shutdown chờ task đang chạy trong thời gian có hạn. Trong production, timeout/queue policy phải dựa trên workload; demo sử dụng giá trị nhỏ để dễ quan sát.
- Vì chỉ có một public top-level class, tên file đúng **AsyncLifecycleDemo.java**. Các class còn lại có package visibility trong cùng package.

**Chi tiết về @Async trả CompletableFuture:** implementation có thể trả một CompletableFuture đã completed bên trong executor thread; proxy async trả cho caller một stage đại diện cho việc task được thực thi. **Không được kết luận caller Future đã complete chỉ vì method body dùng completedFuture**; phần method body phải thực sự chạy trước.

### 6.4. AsyncReportTest.java: kiểm soát mốc vào và hoàn tất

Tạo **src/test/java/com/example/lifecycle/AsyncReportTest.java**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = {
                AsyncLifecycleDemo.class,
                AsyncReportTest.GatewayTestConfiguration.class
        },
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class AsyncReportTest {

    @Autowired
    private ReportService reportService;

    @Autowired
    private ControlledGateway gateway;

    @Test
    @Timeout(
            value = 10,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void waitsForActualCompletionInsteadOfSleeping()
            throws Exception {

        CompletableFuture<String> future =
                reportService.generate("42");

        try {
            assertTrue(
                    gateway.entered.await(2, TimeUnit.SECONDS),
                    "Async service never reached gateway");

            assertFalse(
                    future.isDone(),
                    "Future must wait while gateway is blocked");

            gateway.release.countDown();

            assertEquals(
                    "report:42",
                    future.get(3, TimeUnit.SECONDS));
        } finally {
            gateway.release.countDown();
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class GatewayTestConfiguration {

        @Bean
        @Primary
        ControlledGateway controlledGateway() {
            return new ControlledGateway();
        }
    }

    static final class ControlledGateway
            implements ReportGateway {

        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public String fetch(String id) {
            entered.countDown();

            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Test gateway was not released");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Gateway interrupted", ex);
            }

            return "report:" + id;
        }
    }
}
~~~

Đây là một **@SpringBootTest** thực sự:

1. Spring khởi tạo application context.
2. **@Primary ControlledGateway** được ưu tiên hơn DefaultReportGateway.
3. Test gọi **ReportService qua Spring proxy**, kích hoạt executor.
4. Fake báo **entered** khi async worker vào gateway.fetch.
5. Worker đợi **release**, nên Future chưa được hoàn thành.
6. Test assert trạng thái trung gian **không cần sleep**.
7. Test phát release, lấy kết quả bằng **Future.get(3s)**.
8. finally luôn mở gate để giảm nguy cơ test treo nếu assertion bị lỗi.

**Tín hiệu entered được phát trước await**, nên sau khi test nhận entered thành công và chưa release, **future.isDone()** không thể trở thành true do hoàn tất bình thường. Nếu worker đã tự timeout, điều đó cũng là một lỗi và cần deadline phù hợp trong fixture.

### 6.5. Chạy bài kiểm thử

~~~bash
java -version
mvn test
~~~

Khi các assertion thành công, Maven Surefire báo **BUILD SUCCESS**. Không có stdout cố định từ code ứng dụng trong test vì bộ test không in nội dung ra console; đừng phụ thuộc tên thread hoặc thứ tự logs của Spring.

### 6.6. Vì sao fake gateway tốt hơn sleep 1 giây?

Fake có quyền điều khiển **đúng điểm đang cần quan sát** trong dependency. Điều này giúp:

- Chứng minh @Async đã bắt đầu chạy.
- Chứng minh caller có thể quan sát trạng thái chưa hoàn tất.
- Hoàn tất task bằng release rõ ràng.
- Không phụ thuộc tốc độ scheduling.
- Có message riêng nếu không đạt mốc trong timeout.
- Không gọi remote API thật hoặc chạm database thật chỉ để test timing.

Đối với integration test, có thể thay fake bằng local HTTP stub hoặc Testcontainers, nhưng vẫn nên chờ một tín hiệu health/readiness thay cho một sleep cố định sau khi container start.

## 7. Kiểm thử shutdown bất đồng bộ của SmartLifecycle

**SmartLifecycle** trong Spring Framework hỗ trợ thành phần khởi động/dừng theo lifecycle. Method đặc biệt:

~~~java
void stop(Runnable callback);
~~~

cho phép component báo dừng **bất đồng bộ**. Theo tài liệu Spring Framework 6.1, implementation **phải gọi callback.run() sau khi việc stop thật sự hoàn tất**; nếu quên, LifecycleProcessor có thể đợi đến hết shutdown phase timeout.

Đây là một bài toán kiểm thử tốt cho ba tín hiệu:

- **stopRequested:** framework đã gọi stop(Runnable).
- **allowStop:** test cho phép công việc dừng hoàn tất.
- **stopCallbackFinished:** callback đã chạy.

Test còn cần xác minh **ApplicationContext.close() chưa hoàn tất trước khi callback stop được phát**, và sau release thì Future của close kết thúc.

### 7.1. SmartLifecycleStopTest.java

Tạo **src/test/java/com/example/lifecycle/SmartLifecycleStopTest.java**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SmartLifecycleStopTest {

    @Test
    @Timeout(
            value = 12,
            unit = TimeUnit.SECONDS,
            threadMode = Timeout.ThreadMode.SAME_THREAD)
    void contextCloseWaitsForStopCallback() throws Exception {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        ExecutorService closeCaller =
                Executors.newSingleThreadExecutor();

        ControlledStop component = null;

        try {
            context.registerBean(
                    ControlledStop.class,
                    ControlledStop::new);
            context.refresh();

            component = context.getBean(ControlledStop.class);
            assertTrue(component.isRunning());

            Future<?> closeFuture =
                    closeCaller.submit(context::close);

            assertTrue(
                    component.stopRequested.await(
                            2, TimeUnit.SECONDS),
                    "stop(Runnable) was not called");

            assertFalse(
                    closeFuture.isDone(),
                    "Context closed before stop was released");

            component.allowStop.countDown();

            closeFuture.get(4, TimeUnit.SECONDS);

            assertTrue(
                    component.stopCallbackFinished.await(
                            1, TimeUnit.SECONDS));

            assertFalse(component.isRunning());
            assertFalse(component.waitTimedOut.get());
        } finally {
            if (component != null) {
                component.allowStop.countDown();
            }
            context.close();
            closeCaller.shutdownNow();
            closeCaller.awaitTermination(2, TimeUnit.SECONDS);
        }
    }

    static final class ControlledStop
            implements SmartLifecycle {

        final CountDownLatch stopRequested =
                new CountDownLatch(1);
        final CountDownLatch allowStop =
                new CountDownLatch(1);
        final CountDownLatch stopCallbackFinished =
                new CountDownLatch(1);
        final AtomicBoolean waitTimedOut =
                new AtomicBoolean(false);

        private volatile boolean running;

        @Override
        public void start() {
            running = true;
        }

        @Override
        public void stop(Runnable callback) {
            stopRequested.countDown();

            Thread finisher = new Thread(() -> {
                try {
                    if (!allowStop.await(
                            6, TimeUnit.SECONDS)) {
                        waitTimedOut.set(true);
                    }
                } catch (InterruptedException ex) {
                    waitTimedOut.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    running = false;
                    try {
                        callback.run();
                    } finally {
                        stopCallbackFinished.countDown();
                    }
                }
            }, "controlled-stop-fixture");

            finisher.setDaemon(true);
            finisher.start();
        }

        @Override
        public void stop() {
            running = false;
            allowStop.countDown();
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 0;
        }
    }
}
~~~

**Giải thích logic test:**

- **AnnotationConfigApplicationContext** là Spring context thật, không cần Spring Boot embedded server.
- **registerBean(ControlledStop.class, ControlledStop::new)** tạo bean được context quản lý.
- **context.refresh()** auto-start SmartLifecycle bean (mặc định **isAutoStartup()=true**).
- **closeCaller.submit(context::close)** đóng context trên một thread khác, vì test cần tiếp tục điều khiển gate.
- **stopRequested.await(2s)** xác nhận framework đã gọi method stop với callback.
- Khi **allowStop** chưa được phát, stop fixture đang đợi; do đó **closeFuture.isDone()** phải false.
- Sau release, fixture gọi **callback.run()** trong finally, báo **stopCallbackFinished** và đặt running=false.
- **closeFuture.get(4s)** kiểm chứng context.close() đã hoàn tất, không chỉ có event stopRequested.
- finally giải phóng gate và executor nếu test assertion thất bại. Fixture có timeout nội bộ để không giữ worker sống vô hạn.

**Lưu ý production:** thread trong ControlledStop là **test fixture** cố ý chờ một gate do test điều khiển. Một SmartLifecycle production cần tự dừng resource thật, báo callback khi tài nguyên đã dừng, không đợi test gate; có state machine, timeout và idempotency rõ.

### 7.2. Vì sao gọi callback.run() rất quan trọng?

Spring Framework LifecycleProcessor dùng callback để biết phase có thể tiếp tục. Nếu callback bị bỏ quên:

- Context shutdown có thể chờ đến timeout phase.
- Test có thể đỏ do timeout mặc dù resource thực sự đã dừng.
- Khi DevTools restart, lần restart có thể chậm hoặc treo.
- Khi process nhận SIGTERM, ngân sách dừng có thể bị tiêu hao.

Trong Java code test, **callback.run() nằm trong finally** để không bị bỏ qua sau một InterruptedException. Trong production, không nên đánh dấu stop thành công nếu component vẫn đang chạy; thiết kế trạng thái lỗi cần có semantics rõ.

### 7.3. Đừng lấy stopRequested làm bằng chứng shutdown hoàn tất

Một test:

~~~java
assertTrue(stopRequested.await(2, TimeUnit.SECONDS));
~~~

chỉ cho biết **stop đã bắt đầu**. Nó không khẳng định:

- Worker thread đã kết thúc.
- Resource đã được close.
- Callback đã chạy.
- ApplicationContext.close() trả về.

Để assert completion, dùng Future của lệnh close hoặc một **stopCompleted** signal được phát ở mốc chính xác.

## 8. Kiểm tra ContextClosedEvent và @PreDestroy bằng tín hiệu

Ngoài SmartLifecycle, có thể dùng latch để kiểm tra hai mốc:

1. **ContextClosedEvent** được phát khi context đóng.
2. **@PreDestroy** được gọi trong destruction của managed bean.

### 8.1. ContextCloseSignalTest.java

Tạo **src/test/java/com/example/lifecycle/ContextCloseSignalTest.java**:

~~~java
package com.example.lifecycle;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.annotation.PreDestroy;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextClosedEvent;

import static org.junit.jupiter.api.Assertions.assertTrue;

class ContextCloseSignalTest {

    @Test
    void closeEmitsEventAndDestroysBean() throws Exception {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try {
            context.registerBean(
                    CloseSignals.class,
                    CloseSignals::new);
            context.refresh();

            CloseSignals signals =
                    context.getBean(CloseSignals.class);

            context.close();

            assertTrue(signals.closing.await(
                    1, TimeUnit.SECONDS));
            assertTrue(signals.destroyed.await(
                    1, TimeUnit.SECONDS));
        } finally {
            context.close();
        }
    }

    static final class CloseSignals
            implements ApplicationListener<ContextClosedEvent> {

        final CountDownLatch closing =
                new CountDownLatch(1);
        final CountDownLatch destroyed =
                new CountDownLatch(1);

        @Override
        public void onApplicationEvent(ContextClosedEvent event) {
            closing.countDown();
        }

        @PreDestroy
        void destroy() {
            destroyed.countDown();
        }
    }
}
~~~

Code dùng **AnnotationConfigApplicationContext**, có annotation processors của Spring và **jakarta.annotation.PreDestroy**. Khi context đóng theo đường bình thường, callback được gọi cho bean được quản lý.

**Giới hạn:** test này không mô phỏng SIGKILL hoặc JVM crash, và không đo chính xác thời lượng shutdown. Nó chứng minh cơ chế Spring lifecycle. Đừng khẳng định @PreDestroy được gọi trong mọi failure path, chẳng hạn bean khởi tạo dở dang chưa được đăng ký đầy đủ.

### 8.2. Vì sao gọi close hai lần trong test?

Lần đầu là đối tượng của assertion. Trong **finally**, gọi close lần nữa bảo đảm cleanup trong trường hợp assertion hoặc setup lỗi. Context close bình thường được thiết kế để xử lý trường hợp đã đóng, nhưng cách viết này không phải lời khuyên gọi close lặp lại trong business code.

Nếu test có nhiều external resources, mỗi resource vẫn cần chính sách cleanup phù hợp ngoài context.

## 9. @Scheduled: chờ tick thật, không chờ một chu kỳ bằng sleep

Một bài test không ổn định:

~~~java
Thread.sleep(500);
assertTrue(jobCounter.get() > 0);
~~~

Những điều nó không chứng minh:

- Bean có được đăng ký với **@EnableScheduling** hay chưa.
- Tick có thực sự chạy hay chỉ tình cờ có state từ test trước.
- Task có ném exception hay bị scheduler trì hoãn.
- 500 ms có đủ trên CI không.

Một fixture có **CountDownLatch ticked** được countDown bên trong method được **@Scheduled** gọi sẽ rõ hơn:

~~~java
@Component
class ScheduledTickProbe {

    final CountDownLatch ticked = new CountDownLatch(1);

    @Scheduled(fixedDelay = 100)
    public void tick() {
        ticked.countDown();
    }
}
~~~

Đây là **snippet** cần imports, bean trong context có **@EnableScheduling** và scheduler được cấu hình. Test tương ứng:

~~~java
assertTrue(
        probe.ticked.await(3, TimeUnit.SECONDS),
        "Scheduled task never executed");
~~~

**Tín hiệu này kiểm chứng task đã chạy ít nhất một lần**. Nó không chứng minh fixedDelay chính xác bằng 100 ms hoặc test được mọi tương tác concurrency.

Nếu cần kiểm tra số lần chạy, dùng **CountDownLatch(N)**, blocking queue thu event hoặc observer có sequence. Đừng dùng nhiều lần sleep để tính số tick trong một khoảng ngắn rồi gán đó là kiểm thử chính xác về scheduling.

### 9.1. Về fixedRate và fixedDelay

- **fixedRate** lên lịch theo nhịp có chủ đích, nhưng actual execution có thể chậm khi máy bận.
- **fixedDelay** tính khoảng delay sau lần execution trước hoàn tất.
- **cron** phụ thuộc clock, timezone, lịch và semantics scheduler.

Không giả định scheduler là một real-time clock. Với logic theo ngày/giờ, tách tính lịch khỏi actual scheduling và dùng **Clock.fixed(...)** khi kiểm thử thời gian nghiệp vụ.

### 9.2. Đừng để job cũ ảnh hưởng test mới

Với **@SpringBootTest**, ApplicationContext có thể được cache giữa các test. Một singleton latch hoặc counter có thể đã được kích hoạt bởi test trước.

Chọn:

- Fixture mới cho mỗi test khi có thể.
- Clear/reset state bằng API thread-safe có kiểm soát.
- **@DirtiesContext** khi cần context mới và chấp nhận chi phí.
- Không chạy song song các test chia sẻ scheduler/fixture mà không có isolation.

Không dùng static latch cho tất cả test methods rồi kỳ vọng nó tự reset.

## 10. Startup event: chờ ApplicationReadyEvent đúng cách

Đối với Spring Boot, có những mốc khác nhau:

~~~text
SpringApplication.run()
     |
     +-- Environment prepared
     +-- ApplicationContext refresh
     +-- ApplicationStartedEvent
     +-- ApplicationRunner / CommandLineRunner
     +-- ApplicationReadyEvent
            |
            v
      Ứng dụng ready theo luồng startup thông thường
~~~

Nếu test cần chắc chắn các runners đã hoàn tất, có thể quan sát **ApplicationReadyEvent** bằng listener đăng ký **trước khi khởi động application**.

Không đăng ký listener **sau khi ApplicationReadyEvent đã phát** rồi chờ latch: sự kiện trong Spring mặc định không phải một replay log. Một listener tạo sau mốc event có thể đợi đến timeout dù ứng dụng đã sẵn sàng.

### 10.1. Ví dụ ngắn cho startup event

~~~java
CountDownLatch ready = new CountDownLatch(1);

SpringApplication app =
        new SpringApplication(MyApplication.class);
app.addListeners(
        (ApplicationListener<ApplicationReadyEvent>) event ->
                ready.countDown());

ConfigurableApplicationContext context =
        app.run(args);

try {
    assertTrue(ready.await(2, TimeUnit.SECONDS));
} finally {
    context.close();
}
~~~

Đây là **snippet tích hợp**, cần imports cho SpringApplication, ApplicationListener, ApplicationReadyEvent, ConfigurableApplicationContext, CountDownLatch, TimeUnit, assertTrue và định nghĩa MyApplication/args. Listener được đăng ký **trước app.run**. Vì **run() thành công thường đã phát ReadyEvent**, latch giữ sự kiện và await có thể trả về ngay.

Đối với **@SpringBootTest**, context thường được dựng xong trước khi test method chạy. Nếu chỉ cần bean đã sẵn sàng để được inject, đừng tự tạo một listener sau startup và mong nó nhận ReadyEvent cũ; kiểm tra trực tiếp trạng thái/bean hoặc gắn listener test vào bootstrap phù hợp.

### 10.2. Ready không đồng nghĩa mọi background task đã hoàn tất

**ApplicationReadyEvent** cho biết startup phase thành công, không bảo đảm:

- Mọi @Scheduled task đã chạy.
- Mọi @Async task được submit bởi runner đã kết thúc.
- Remote services sẽ luôn online.
- Message consumers đã nhận mọi message chờ trong broker.
- HTTP client đã xử lý tất cả retries.

Nếu cần một công việc cụ thể hoàn tất sau Ready, dùng **completion signal dành riêng cho công việc đó**.

## 11. HTTP asynchronous với Spring MVC và MockMvc

Spring MVC hỗ trợ handler trả **Callable**, **DeferredResult**, hoặc CompletableFuture. Test MockMvc cần phân biệt:

- **Request đã bắt đầu chế độ async**.
- **Kết quả async đã hoàn tất**.
- **Async dispatch đã tạo HTTP response cuối cùng**.

Ví dụ pattern kiểm thử:

~~~java
MvcResult pending = mockMvc.perform(
        get("/async/report"))
        .andExpect(request().asyncStarted())
        .andReturn();

pending.getAsyncResult(3000);

mockMvc.perform(asyncDispatch(pending))
        .andExpect(status().isOk())
        .andExpect(content().string("done"));
~~~

**Đây là snippet dành cho một Spring MVC test đã thiết lập MockMvc, endpoint /async/report và static imports** của MockMvcRequestBuilders/ResultMatchers. Nó không phải source file hoàn chỉnh của dự án console ở mục 6; nếu chạy độc lập cần thêm **spring-boot-starter-web** và controller.

**getAsyncResult(3000)** giúp đợi kết quả tối đa khoảng ba giây thay vì Thread.sleep. Sau completion, **asyncDispatch(...)** kiểm tra response cuối. Không dùng response ngay sau andExpect(asyncStarted) như response HTTP đã hoàn tất.

### 11.1. Không gọi MVC async là @Async theo nghĩa hoàn toàn giống nhau

Spring MVC async processing và **@Async** service methods có thể dùng executor và completion model khác nhau. Chúng cùng cần chờ completion nhưng test phải quan sát đúng tầng:

- Service async: **Future/CompletableFuture** từ service.
- MVC async: **async result và dispatch**.
- WebFlux/Reactor: **Publisher/StepVerifier** hoặc cách chờ reactive phù hợp.
- Streaming/SSE: **event completion/cancellation semantics**; stream vô hạn không có “tự hoàn tất” theo deadline thông thường.

Không ép mọi loại async vào một latch duy nhất khi framework đã cung cấp completion API chuẩn.

## 12. Awaitility khi điều kiện chỉ có thể quan sát bằng polling

Đôi khi code production không expose Future hoặc event callback. Ví dụ: một background consumer cập nhật trạng thái ở database, test chỉ có thể đọc trạng thái cuối cùng.

Trong trường hợp này, **Awaitility** cung cấp eventual assertion có timeout và polling:

~~~java
await()
        .atMost(5, TimeUnit.SECONDS)
        .pollInterval(50, TimeUnit.MILLISECONDS)
        .untilAsserted(() ->
                assertEquals("DONE", statusRepository.find(id)));
~~~

Đây là snippet cần thư viện **Awaitility**, imports phù hợp, repository và id đã được tạo. Nếu dự án chưa có Awaitility, có thể thêm test dependency:

~~~xml
<dependency>
    <groupId>org.awaitility</groupId>
    <artifactId>awaitility</artifactId>
    <version>4.2.2</version>
    <scope>test</scope>
</dependency>
~~~

Trong dự án lớn, dùng BOM/version đã được quản lý và tương thích; ví dụ trên ghi một version cụ thể cho Maven demo.

**Điểm khác Thread.sleep:** Awaitility sẽ dừng sớm khi điều kiện đúng, thay vì luôn chờ cố định. Timeout là giới hạn tối đa của vòng kiểm tra.

### 12.1. Polling có phải luôn tốt?

Không. Nếu bạn kiểm soát code/fixture và có thể phát signal **CountDownLatch/CompletionStage**, event-based wait thường:

- Ít độ trễ hơn.
- Ít gây tải lên database/HTTP service.
- Truy vết sự kiện rõ hơn.
- Hạn chế race với state được reset giữa các lần poll.

Polling phù hợp khi **hệ thống chỉ cung cấp observable state**, không có callback đáng tin. Hãy chọn poll interval và atMost có giới hạn.

### 12.2. Có thể poll vào dữ liệu không thread-safe không?

Không nên. Đọc một field thường xuyên không tạo memory synchronization. Nếu trạng thái do một thread khác ghi, dùng Atomic/volatile/lock hoặc đọc một hệ thống lưu trữ có consistency contract phù hợp.

Một test polling đúng về thời gian vẫn có thể sai về visibility nếu state không được publish thread-safe.

## 13. Mockito verify(timeout): dùng đúng tình huống

Mockito có verification timeout:

~~~java
verify(mockListener, timeout(2000).times(1))
        .onCompleted("42");
~~~

Đây là snippet cần mockListener và static imports Mockito. Nó có thể hữu ích khi code gọi callback trên mock và không trả Future. Tuy nhiên:

- Nó kiểm tra **interaction xảy ra**, không tự kiểm tra side effects khác.
- **timeout(...)** và **after(...)** có semantics khác nhau; đừng coi hai cách là tương đương.
- Lời gọi có thể xuất hiện nhưng job nghiệp vụ chưa commit xong.
- Negative assertions như “không bao giờ có callback” trên cửa sổ thời gian hữu hạn không chứng minh sự kiện sẽ không bao giờ xảy ra.

Nếu có thể dùng **Future.get(timeout)** hoặc **CountDownLatch** gắn với mốc completion thật, chúng thường thể hiện contract rõ hơn.

## 14. JUnit @Timeout và assertTimeoutPreemptively

### 14.1. Hai tầng deadline nên cùng tồn tại

Đối với một async test:

- **Local wait timeout:** latch.await(2s), future.get(3s). Nó cho biết chính xác mốc nào chưa hoàn tất.
- **Whole-test watchdog:** **@Timeout(10s)**. Nó ngăn một bug khác làm test treo vô hạn ngoài các điểm đang await.

Ví dụ:

~~~java
@Test
@Timeout(10)
void completedWithinDeadline() throws Exception {
    assertEquals("DONE", future.get(3, TimeUnit.SECONDS));
}
~~~

Đây là snippet test có future được khởi tạo trước đó. @Timeout mặc định dùng **seconds** nếu không khai báo unit. Bài test đầy đủ vẫn cần cleanup resource riêng.

**Không chỉ đặt @Timeout(30) quanh một test có Thread.sleep(1000) rồi coi đã sửa flakiness.** Deadline tổng ngăn treo, nhưng không tạo synchronization với sự kiện.

### 14.2. assertTimeout khác assertTimeoutPreemptively

JUnit có:

~~~java
assertTimeout(
        Duration.ofSeconds(3),
        () -> operation());
~~~

và:

~~~java
assertTimeoutPreemptively(
        Duration.ofSeconds(3),
        () -> operation());
~~~

Đây là snippets, giả định có operation() và static imports. Khác biệt quan trọng:

- **assertTimeout** chạy code trên thread hiện tại và kiểm tra thời gian; nó **không cưỡng bức dừng ngay code bị treo** chỉ vì deadline đã qua.
- **assertTimeoutPreemptively** chạy executable trên thread khác để có thể báo timeout sớm, nhưng **đổi thread context** và việc interrupt không nhất thiết dừng underlying task.

### 14.3. Nguy cơ với Spring @Transactional và ThreadLocal

Spring test-managed transactions thường bind trạng thái transaction qua **ThreadLocal** của test thread.

Nếu dùng assertTimeoutPreemptively quanh một thao tác database trong test @Transactional:

- Code trong executable chạy trên **thread khác**.
- Thread khác không mang cùng transaction context như test thread.
- Thao tác có thể **commit thật** thay vì được rollback theo test transaction.
- Test có thể nhìn như pass nhưng để lại dữ liệu.

JUnit 5 documentation cảnh báo riêng về **preemptive timeouts và transactional test**.

**Khuyến nghị:** với Spring transactional test, ưu tiên **Future.get(timeout)** hoặc **CountDownLatch.await(timeout)**; dùng **@Timeout(..., threadMode=SAME_THREAD)** để bảo toàn thread-sensitive context khi phù hợp. Nếu phải dùng separate thread, thiết kế transaction/data cleanup rõ và không giả định rollback tự động đi qua thread boundary.

### 14.4. @Timeout không tự cancel mọi hoạt động phía sau

Khi một test bị timeout:

- JUnit có thể interrupt test thread theo thread mode.
- Future/worker khác có thể vẫn đang chạy.
- HTTP call có thể không tự dừng nếu không hỗ trợ interrupt/cancellation.
- Spring context cache có thể giữ scheduler cho test kế tiếp.

Cần **finally** để release latches, cancel tasks khi API hỗ trợ, dừng executor và đóng tài nguyên theo quyền sở hữu.

## 15. Timeout của test khác timeout của business logic

Một hệ thống thường có nhiều deadline:

~~~text
Test await timeout             : 2 giây
Fake worker gate timeout       : 5 giây
Business API timeout           : 10 giây
HTTP client connect timeout    : 1 giây
Whole-test watchdog           : 12 giây
CI process/build timeout       : vài phút
~~~

Các con số minh họa, không phải cấu hình tối ưu. Quan trọng là **deadline có mục đích rõ**.

Ví dụ, nếu test chờ task hoàn tất với timeout 3s, nhưng code production có timeout 30s cho external API thật, test có thể không phù hợp để kiểm tra timeout production. Trong unit test, fake/stub nên điều khiển completion; timeout production cần được kiểm tra với clock/fake/network test riêng.

**Timeout test phải đủ rộng để tránh false failure khi CI scheduling chậm, nhưng hữu hạn để báo lỗi trong thời gian hợp lý.** Không cần chờ đúng bằng ngưỡng production trong mọi unit test.

### 15.1. Đo latency không giống kiểm tra completion

Nếu mục tiêu là performance, cần benchmark/profiling có warm-up và thống kê, không dùng test assert “phải chạy xong trong 20 ms” trên một shared CI runner.

Bài test correctness nên xác minh **eventually completed before một ngân sách test hợp lý**. Bài benchmark lại đo distribution/throughput/percentiles riêng.

### 15.2. Dùng Deadline chung khi có nhiều bước chờ

Nếu test có ba await tuần tự, mỗi bước timeout 10s, tổng có thể chờ tới 30s. Đôi khi muốn một **deadline chung**:

~~~java
long deadline = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(5);

long remaining = deadline - System.nanoTime();
if (remaining <= 0
        || !started.await(remaining, TimeUnit.NANOSECONDS)) {
    throw new AssertionError("Start deadline exceeded");
}
~~~

Đây là snippet. Khi có nhiều mốc, tính lại remaining từ **System.nanoTime()** trước mỗi await. Dùng **nanoTime** cho đo duration/timeout vì nó là nguồn thời gian monotonic thích hợp, không dùng **System.currentTimeMillis()** với rủi ro wall-clock thay đổi.

Cần lưu ý overflow khi cộng với deadline rất lớn; với khoảng ngắn vài giây trong test, phép tính trên phù hợp.

## 16. Xử lý failure trong worker cho đúng

### 16.1. Không để latch success được phát quá sớm

Đoạn sai:

~~~java
done.countDown();
repository.save(entity);
~~~

Nếu test đợi done rồi đọc repository, nó có thể chạy **trước khi save hoàn tất**. Signal được đặt sai mốc.

Đúng hơn:

~~~java
repository.save(entity);
done.countDown();
~~~

Đây là snippets minh họa. Nếu save là asynchronous và trả Future, cần đợi **commit/completion** thực sự rồi mới phát done. Nếu giao dịch chỉ commit sau method return, countDown bên trong method vẫn có thể **đến trước transaction commit**; khi đó nên dùng transaction synchronization hoặc một completion signal phản ánh đúng mốc commit.

**Đặt signal đúng mốc quan trọng hơn dùng loại latch nào.**

### 16.2. Cần phát completion cả khi thất bại

Nếu test chỉ có done latch và worker ném exception trước countDown, test đợi đến timeout nhưng không biết root cause.

Một pattern:

~~~java
CompletableFuture<String> completion =
        new CompletableFuture<>();

executor.execute(() -> {
    try {
        String result = performWork();
        completion.complete(result);
    } catch (Throwable ex) {
        completion.completeExceptionally(ex);
    }
});
~~~

Đây là snippet cần executor, performWork và imports. CompletableFuture truyền được cả success và failure; test có thể dùng **get(timeout)** rồi quan sát **ExecutionException.getCause()**.

Với latch, có thể dùng **finally** để phát done và lưu exception trong một **AtomicReference<Throwable>**, sau đó assertion kiểm tra cả trạng thái và lỗi. Không chỉ await rồi tuyên bố success.

### 16.3. Future.get timeout không tự ngắt worker

Nếu:

~~~java
future.get(2, TimeUnit.SECONDS);
~~~

ném TimeoutException, task có thể vẫn đang chạy. Với Future từ ExecutorService, có thể thử **future.cancel(true)** trong cleanup nếu task hỗ trợ interruption.

**Riêng CompletableFuture.cancel(true)** không được coi là một cơ chế chắc chắn interrupt underlying operation; completion cancellation và thread cancellation là hai khái niệm khác nhau. Chỉ dùng cancellation policy phù hợp với API/thư viện cụ thể.

### 16.4. Giữ interrupt flag

Một task chờ latch nên xử lý:

~~~java
try {
    gate.await();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Interrupted", ex);
}
~~~

Nếu task nhận interrupt trong shutdown và bạn nuốt lỗi, nó có thể tiếp tục chạy hoặc báo trạng thái không chính xác. Hãy giữ interrupt flag hoặc propagate theo hợp đồng của method.

Test cũng cần hiểu rằng **await(timeout)** có thể ném InterruptedException, không chỉ trả false.

## 17. Negative assertions và race conditions

Kiểm thử “event phải xảy ra” có thể chờ một latch. Nhưng “event tuyệt đối không bao giờ xảy ra” là phát biểu mạnh hơn nhiều: không thể chứng minh vô hạn chỉ bằng chờ 100 ms.

Ví dụ:

~~~java
assertFalse(done.await(100, TimeUnit.MILLISECONDS));
~~~

chỉ chứng minh **done chưa được phát trong một cửa sổ 100 ms**. Nó không chứng minh event sẽ không xảy ra sau đó.

### 17.1. Thay kiểm thử phủ định theo đồng hồ bằng gate

Với một task cố ý đợi **release**, test biết worker chưa được release và có thể assert Future chưa hoàn tất:

~~~java
assertTrue(started.await(2, TimeUnit.SECONDS));
assertFalse(future.isDone());
release.countDown();
assertEquals("DONE", future.get(3, TimeUnit.SECONDS));
~~~

Sự vắng mặt của completion ở mốc này được hỗ trợ bởi **causal control** trong fixture, không chỉ bởi “đã ngủ 100 ms mà không thấy gì”.

Tuy nhiên, nếu worker có đường khác để hoàn tất hoặc tự timeout, assertion vẫn có thể fail; thiết kế fake cần rõ mọi đường hoàn thành.

### 17.2. Kiểm tra thứ tự nhiều events bằng BlockingQueue

Nếu cần xác minh mốc **STARTED**, **COMMITTED**, **CLOSED**, có thể phát các event vào queue:

~~~java
BlockingQueue<String> events =
        new LinkedBlockingQueue<>();

events.offer("STARTED");
events.offer("COMMITTED");

assertEquals(
        "STARTED",
        events.poll(2, TimeUnit.SECONDS));
assertEquals(
        "COMMITTED",
        events.poll(2, TimeUnit.SECONDS));
~~~

Đây là snippet minh họa cần imports. Trong thực tế, các offer nằm ở những callback nghiệp vụ khác nhau; test không tự phát cả hai như ở snippet này. **BlockingQueue.poll(timeout)** trả null nếu deadline hết, nên assertion cần message phù hợp.

Queue cho phép quan sát **thứ tự events** thay vì chỉ một boolean đã hoàn tất.

## 18. Test isolation: tránh state rò từ bài trước

Các lỗi flakiness còn tới từ fixture dùng chung:

- CountDownLatch đã count về 0 trong test trước.
- Static AtomicInteger không reset giữa tests.
- @SpringBootTest cache cùng ApplicationContext nhiều lần.
- @Scheduled bean vẫn chạy giữa các test methods.
- Một executor từ test trước chưa shutdown.
- @Async job viết vào repository sau khi test kết thúc.
- Test chạy song song dùng cùng port, topic, queue hoặc database rows.

Để giảm rủi ro:

1. **Mỗi test có latch/Future/gate riêng** khi có thể.
2. Với @SpringBootTest, tránh giữ mutable test state lâu trong singleton bean.
3. Dùng **@DirtiesContext** chỉ khi thực sự cần context mới, vì nó tốn thời gian startup.
4. Dùng unique ID cho dữ liệu của mỗi test.
5. Cleanup bằng finally và bounded shutdown.
6. Nếu chạy parallel tests, kiểm tra shared resources và framework synchronization.
7. Không tăng sleep để “ổn định” một race thực.

### 18.1. Test fixture cũng phải có timeout nội bộ

Ngay cả khi test đã dùng await(3s), nếu worker của fixture đợi một gate **không có timeout** mà test bị abort, thread đó có thể sống qua bài tiếp theo. Vì vậy các ví dụ chính dùng cả:

- Timeout khi **test await**.
- Timeout khi **fake worker await**.
- **finally release**.
- Executor shutdown/awaitTermination.

Đó là nhiều lớp bảo vệ khác nhau, không phải sự lặp thừa.

### 18.2. Test cleanup không được che lỗi gốc

Nếu main assertion fail nhưng finally cũng ném lỗi cleanup, bạn có thể chỉ nhìn thấy cleanup exception. Với tài nguyên phức tạp, sử dụng **try-with-resources**, JUnit teardown, hoặc gom suppressed exceptions theo policy thích hợp.

Đừng bỏ cleanup hoàn toàn chỉ vì sợ ảnh hưởng exception. Thread/socket leak làm test kế tiếp bị hỏng và khó debug hơn.

## 19. Java 21 virtual threads có thay đổi nguyên tắc không?

Không. Virtual threads trên Java 21 vẫn cần synchronization và completion signals; chúng không làm **Thread.sleep(1000)** trở thành phép chờ đáng tin.

Có thể dùng **Executors.newVirtualThreadPerTaskExecutor()** và **Future.get(timeout)** tương tự platform executor, nhưng đây là **Java 21+ API**, không biên dịch trong Java 17.

Những khác biệt có thể ảnh hưởng test:

- Virtual thread luôn daemon, có thể không giữ JVM sống khi main kết thúc.
- Không được dựa vào tên thread để xác định công việc đã hoàn tất.
- Virtual thread nhiều hơn có thể làm race hiếm xuất hiện rõ hơn.
- Chờ latch/Future vẫn cần deadline và interrupt semantics.
- Với một ứng dụng nền Spring Boot bật virtual threads, lifetime của JVM cần được quản lý riêng; test unit có non-daemon test runner không chứng minh process production luôn sống.

**Đừng biến nội dung test timeout thành một giả định JVM giữ mọi virtual tasks chạy cho tới kết thúc**. Completion test và process lifetime là hai hợp đồng khác nhau.

## 20. Những điều nên đo trong CI

Để phân biệt flakiness do scheduling và lỗi code:

- Test nào hết hạn và **mốc nào** hết hạn (STARTED, COMPLETED hay CLEANED_UP).
- Timeout thực tế, số lần retry của test (nếu có).
- Stack trace/root cause của worker từ Future/CompletionStage.
- Thread dump khi test treo, executor queue depth hoặc active count.
- Spring ApplicationContext startup/shutdown event markers.
- Số worker threads còn sống sau teardown.
- Thời gian startup context và độ trễ sau submit.
- Các service/container readiness signals nếu test có tích hợp.

Một lỗi chờ started quá hạn có thể nghĩa task chưa được schedule hoặc bean @Async chưa được gọi. Một lỗi future.get quá hạn khi started đã báo có thể nghĩa task đang chờ gate, I/O, deadlock hoặc không phát completion. Thông điệp thất bại nên phân biệt hai trường hợp này.

### 20.1. Không dùng retry toàn bộ test như giải pháp đầu tiên

JUnit repeated test, CI rerun và retry có thể giúp chẩn đoán tính không ổn định, nhưng cũng có thể **che race condition**. Hãy ưu tiên tìm điểm thiếu signal và kiểm soát timeout/state trước. Nếu sau đó cần retry cho một integration dependency không ổn định, policy phải có lý do và metrics rõ.

## 21. Các anti-pattern cần tránh

### 21.1. Thread.sleep cố định rồi đọc state

Sai vì chờ thừa trên máy nhanh và có thể thiếu trên máy chậm. Dùng event signal hoặc eventual assertion có timeout.

### 21.2. CountDownLatch.await() không timeout

Có thể treo mãi nếu task không phát countDown. Dùng await(timeout, unit) và assert kết quả boolean.

### 21.3. Future.join() không deadline khi completion không chắc chắn

Có thể đợi vô hạn. Ưu tiên get(timeout, unit) khi test cần bounded wait.

### 21.4. Phát done signal trước khi side effect hoàn tất

Test có thể đọc dữ liệu trước commit. Đặt signal ở mốc completion thật.

### 21.5. Chỉ countDown khi thành công

Lỗi worker làm test chờ đến timeout mà không biết exception. Dùng CompletableFuture exceptional completion hoặc lưu cause và phát signal trong finally.

### 21.6. Dùng assertTimeoutPreemptively trong test @Transactional

Thread khác có thể làm mất thread-bound transaction context của Spring, gây commit ngoài ý muốn. Cân nhắc @Timeout SAME_THREAD và local bounded waits.

### 21.7. Bỏ cleanup khi assertion lỗi

Để lại worker bị block, socket mở hoặc context cũ. Dùng finally để release/cancel/close trong thời hạn.

### 21.8. Test trực tiếp new AsyncService() rồi nói @Async không hoạt động

Mặc định @Async dựa vào Spring proxy. Test phải dùng bean đã inject hoặc kiểm thử một phần logic thuần riêng.

### 21.9. Đợi ApplicationReadyEvent bằng listener đăng ký sau Ready

Event đã qua không được replay mặc định. Đăng ký listener trước bootstrap hoặc kiểm tra trạng thái hiện tại.

### 21.10. Xem @Scheduled tick là đồng hồ chính xác

Scheduling có thể trễ. Test “đã chạy” bằng signal, test business time bằng Clock/fake clock.

### 21.11. Dùng 10 lần sleep nhỏ để thay một sleep lớn

Polling thủ công có thể giảm thời gian chờ nhưng vẫn cần visibility, deadline và điều kiện đúng. Dùng Awaitility hoặc signal có semantics rõ.

### 21.12. Coi “không xảy ra trong 100 ms” là “không bao giờ xảy ra”

Chỉ chứng minh một khoảng thời gian hữu hạn. Dùng gate/control flow khi có thể.

### 21.13. Tăng timeout cực lớn để hết flakiness

Che deadlock hoặc thiếu signal. Timeout phải hữu hạn và có lý do; xác định mốc gây chờ.

### 21.14. Hủy CompletableFuture rồi tin chắc worker đã ngừng

Cancellation của future không luôn interrupt underlying task. Cần cancellation/termination semantics của executor/I/O thật.

### 21.15. Chạy test song song với một singleton latch dùng chung

State của test khác có thể mở latch. Tạo fixture riêng hoặc isolation rõ.

## 22. Checklist viết test async ổn định

- [ ] Xác định rõ sự kiện cần kiểm tra: STARTED, COMPLETED hay CLEANED_UP.
- [ ] Không dùng Thread.sleep làm bằng chứng công việc đã xong.
- [ ] Nếu có Future, dùng get(timeout) và kiểm tra result/error.
- [ ] Nếu có callback/event, dùng CountDownLatch với await(timeout).
- [ ] Nếu chỉ có observable state, dùng eventual assertion có deadline như Awaitility.
- [ ] Signal được phát đúng mốc nghiệp vụ, không trước commit/flush/close.
- [ ] Worker failure được truyền về test, không chỉ rơi vào log.
- [ ] Mỗi lần chờ có thông báo timeout rõ ràng.
- [ ] Có @Timeout làm giới hạn tổng bên ngoài local waits.
- [ ] Không dùng preemptive timeout bừa trong @Transactional/ThreadLocal-dependent tests.
- [ ] Test giả lập @Async gọi qua Spring proxy.
- [ ] Fake dependency có thể được release trong finally.
- [ ] Executor/connection/context được đóng, chờ trong giới hạn.
- [ ] Fixture mutable không bị chia sẻ qua context cache/test song song ngoài ý muốn.
- [ ] SmartLifecycle.stop(Runnable) gọi callback khi stop xong.
- [ ] Test shutdown chứng minh close Future complete, không chỉ stop được yêu cầu.
- [ ] Test startup không đợi event đã phát trước khi listener đăng ký.
- [ ] Test scheduler quan sát tick thật, không đoán bằng thời gian ngủ.
- [ ] Test MVC async kiểm tra async result và asyncDispatch.
- [ ] Nếu có CI flakiness, ghi lại mốc timeout và root cause thay vì chỉ tăng sleep.
- [ ] Test không để thread/resource chạy nền sau khi kết thúc.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao Thread.sleep(1000) không phải cách kiểm tra async completion đáng tin?

**Đáp án:** Nó chỉ chờ thời gian cố định, không biết task đã bắt đầu hoặc hoàn tất; CI có thể chậm hơn giả định và máy nhanh thì chờ thừa.

**Câu 2.** CountDownLatch.await(2, SECONDS) trả gì khi hết hạn?

**Đáp án:** false; khi nhận đủ countDown thì trả true.

**Câu 3.** Future.get(2, SECONDS) có tự hủy task nếu hết hạn không?

**Đáp án:** Không. Nó ném TimeoutException; task có thể vẫn đang chạy và cần cancellation/cleanup riêng.

**Câu 4.** Vì sao một latch STARTED chưa đủ chứng minh job COMPLETED?

**Đáp án:** Task có thể đang chờ I/O, gate hoặc đã ném lỗi sau mốc started. Cần completion stage hoặc done signal đúng mốc.

**Câu 5.** Chờ một latch có tạo memory visibility tốt hơn Thread.sleep không?

**Đáp án:** Có. CountDownLatch có quan hệ happens-before giữa hành động trước countDown và hành động sau successful await.

**Câu 6.** Nếu @Async method được gọi bằng this.method() trong cùng bean, test có chắc đang kiểm tra async execution qua proxy không?

**Đáp án:** Không. Self-invocation thường bỏ qua Spring AOP proxy. Gọi qua bean được inject.

**Câu 7.** Trong SmartLifecycle, khi nào nên gọi callback của stop(Runnable)?

**Đáp án:** Khi component thực sự đã hoàn tất stop; quên callback có thể làm context shutdown đợi tới timeout phase.

**Câu 8.** Nếu đã nhận ContextClosedEvent, có chắc @PreDestroy xong không?

**Đáp án:** Chưa. ContextClosedEvent báo context đang đóng; destruction là mốc khác, cần quan sát riêng.

**Câu 9.** Khi dùng Spring @Transactional test, assertTimeoutPreemptively có rủi ro gì?

**Đáp án:** Executable chạy trên thread khác, có thể mất ThreadLocal transaction context và commit dữ liệu ngoài ý muốn.

**Câu 10.** Khi nào dùng Awaitility thay cho CountDownLatch?

**Đáp án:** Khi hệ thống chỉ lộ trạng thái cuối có thể quan sát/poll mà không có completion callback đáng tin.

**Câu 11.** Listener được đăng ký sau ApplicationReadyEvent có tự nhận lại event cũ không?

**Đáp án:** Không theo cơ chế event multicaster mặc định. Đăng ký trước startup hoặc kiểm tra trạng thái hiện tại.

**Câu 12.** Tại sao cần release latch trong finally của test?

**Đáp án:** Nếu assertion lỗi sớm, worker không bị block mãi; giảm thread leak, treo context và ảnh hưởng test khác.

**Câu 13.** Có thể chứng minh một event không bao giờ xảy ra bằng await(100ms) trả false không?

**Đáp án:** Không, chỉ chứng minh không xảy ra trong cửa sổ hữu hạn đó.

**Câu 14.** Khi kiểm tra HTTP async với MockMvc, tại sao cần asyncDispatch?

**Đáp án:** Request ở asyncStarted chưa có response cuối; asyncDispatch cho phép kiểm tra status/body sau khi async result hoàn tất.

## 24. Tổng kết

Kiểm thử bất đồng bộ tốt không hỏi **“đợi bao nhiêu mili-giây cho chắc?”** mà hỏi:

1. **Tôi cần xác minh mốc nào?** Task đã bắt đầu, hoàn tất, lỗi hay cleanup?
2. **Mốc đó phát tín hiệu gì?** CountDownLatch, Future/CompletionStage, callback, event, state có thể poll.
3. **Deadline của lần chờ là bao nhiêu?** Mọi await/get và toàn test phải có giới hạn.
4. **Nếu test thất bại giữa chừng, ai release/cancel/close resource?**
5. **Signal có phản ánh completion thật không?** Đừng countDown trước commit hoặc callback stop.

Với **Spring Boot 3.3/Java 17+**, dùng **Future.get(timeout)** cho @Async, **CountDownLatch.await(timeout)** cho startup/shutdown/scheduled signals, **SmartLifecycle.stop(Runnable) callback** để xác minh dừng bất đồng bộ, và **ApplicationContext.close()** khi kiểm thử destruction. Dùng **JUnit @Timeout** làm watchdog tổng, tránh preemptive thread mode khi test phụ thuộc transaction/ThreadLocal.

Những nguyên tắc này làm test nhanh hơn khi công việc hoàn tất sớm, cho lỗi có ý nghĩa khi công việc không chạy và giảm flakiness do khác biệt tốc độ giữa máy dev và CI.

## 25. Tài liệu chính thức

- Java SE 17 — CountDownLatch và happens-before: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Java SE 17 — Future.get(timeout) và cancellation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — CompletableFuture: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Spring Boot 3.3 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Framework 6.1 — SmartLifecycle API và stop callback: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework — Async Execution và Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework/async-requests.html
- JUnit 5 User Guide — Timeouts và Preemptive Timeout Pitfalls: https://docs.junit.org/5.10.3/user-guide/index.html
- Awaitility documentation: https://github.com/awaitility/awaitility