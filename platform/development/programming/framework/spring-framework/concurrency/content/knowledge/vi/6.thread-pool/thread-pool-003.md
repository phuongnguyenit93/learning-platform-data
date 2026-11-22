# queueCapacity và lựa chọn hàng đợi nội bộ trong ThreadPoolTaskExecutor

## 1. Vì sao queueCapacity quan trọng?

Trong Spring Framework, `ThreadPoolTaskExecutor` cho phép đưa `Runnable` vào một nhóm thread thay vì tạo một thread mới thủ công cho mỗi tác vụ. Khi các worker đang bận mà tiếp tục có công việc mới, executor phải quyết định **xếp hàng**, **tạo thêm worker** hay **từ chối tác vụ**.

Thuộc tính `queueCapacity` trực tiếp quyết định loại hàng đợi bên dưới `ThreadPoolTaskExecutor` và ảnh hưởng mạnh đến hành vi đó. Đây không chỉ là một giới hạn bộ nhớ: lựa chọn hàng đợi làm thay đổi thời điểm pool mở rộng từ `corePoolSize` đến `maxPoolSize`, độ trễ trước khi task bắt đầu, nguy cơ tích backlog và thời điểm xuất hiện rejection.

Ví dụ: hai ứng dụng đều cấu hình `corePoolSize=2`, `maxPoolSize=8`, nhưng một ứng dụng đặt `queueCapacity=1000`, ứng dụng kia đặt `queueCapacity=0`. Ứng dụng thứ nhất thường xếp nhiều việc chờ ngay từ lúc có 2 worker bận, còn ứng dụng thứ hai cố bàn giao ngay cho worker rảnh hoặc tạo thêm worker (tối đa 8). Chỉ đổi `queueCapacity` có thể làm biểu đồ số thread và latency hoàn toàn khác nhau.

**Phạm vi bài:** hàng đợi nội bộ dùng cho *task chưa được thực thi* của `ThreadPoolTaskExecutor`, cách nó tương tác với core/max threads và ý nghĩa vận hành trong ứng dụng Spring. Đây không phải queue bền vững như Kafka/RabbitMQ: khi tiến trình chết, những tác vụ chỉ nằm trong bộ nhớ của executor có thể mất.

## 2. queueCapacity chọn loại hàng đợi nào?

Với `ThreadPoolTaskExecutor` trong Spring Framework 6.x, việc chọn hàng đợi về cơ bản tương ứng:

```java
// Mô phỏng logic createQueue(int) của ThreadPoolTaskExecutor:
BlockingQueue<Runnable> queue = queueCapacity > 0
        ? new LinkedBlockingQueue<>(queueCapacity)
        : new SynchronousQueue<>();
```

Đây là đoạn **minh họa logic**, không phải toàn bộ phương thức tạo executor. Ý nghĩa cụ thể:

| `queueCapacity` | Hàng đợi nội bộ | Task có thể nằm chờ trong queue? | Hành vi đáng chú ý |
| --- | --- | --- | --- |
| Số nguyên dương, ví dụ `1`, `50`, `500` | `LinkedBlockingQueue<Runnable>` với dung lượng được chỉ định | Có, tối đa số phần tử cấu hình | Sau khi đủ core threads, task được xếp hàng trước khi mở thêm non-core threads |
| `0` | `SynchronousQueue<Runnable>` | Không; không có ô lưu task | Task phải được bàn giao trực tiếp cho worker sẵn sàng, hoặc pool tạo worker khác nếu còn chỗ |
| Số âm | `SynchronousQueue<Runnable>` | Không | Cũng đi theo nhánh “không có hàng đợi chứa phần tử”; dùng `0` để biểu đạt rõ ý định |
| Không gọi setter | `LinkedBlockingQueue` với `Integer.MAX_VALUE` | Về lý thuyết rất lớn, nhưng RAM là giới hạn thực tế | Có thể tích backlog lớn; `maxPoolSize` thường không được dùng đến vì queue ít khi đầy |

**Không tự động chọn `ArrayBlockingQueue`:** setter `queueCapacity` không làm Spring tạo mảng vòng có dung lượng cố định; queue mặc định cho mọi giá trị dương là `LinkedBlockingQueue`. Hai implementation có đặc điểm cấp phát và hành vi riêng, nên không thể suy từ tên thuộc tính rằng queue nào cũng như nhau.

### 2.1. LinkedBlockingQueue: lưu task để thực hiện sau

Với `queueCapacity > 0`, queue chứa các `Runnable` chưa có worker thực hiện. Khi người gửi task nhanh hơn khả năng xử lý, số task chờ tăng lên cho tới giới hạn capacity.

- Queue có thứ tự FIFO ở phía chờ, nhưng **không bảo đảm thứ tự hoàn tất** khi nhiều worker thực thi đồng thời.
- `queueCapacity=100` nghĩa là tối đa 100 phần tử đang đợi trong queue; **không có nghĩa** pool chỉ nhận tổng cộng 100 task, cũng không có nghĩa tự tạo 100 threads.
- Task đang chạy trên thread **không được tính** vào số phần tử queue.
- Queue chứa tham chiếu tới task và trạng thái nó giữ, có thể kéo theo retention của payload/request objects. Queue lớn tạo nguy cơ dùng bộ nhớ và chờ lâu trước khi chạy.

### 2.2. SynchronousQueue: bàn giao trực tiếp, không lưu trữ

Với `queueCapacity=0`, `SynchronousQueue` là cơ chế *handoff*: task chỉ được đưa vào khi có worker sẵn sàng nhận, hoặc executor phải tạo worker mới nếu pool còn khả năng mở rộng. Nó **không** giữ lại một backlog để lấy ra sau.

Một đặc điểm gây nhầm lẫn: `SynchronousQueue.size()` luôn là 0. Vì thế, biểu đồ “queue size = 0” **không chứng minh** pool không bị quá tải. Hãy xem thêm `activeCount`, `poolSize`, số lần bị từ chối và latency.

Cấu hình `queueCapacity=0` với `maxPoolSize` rất lớn có thể làm nhiều thread được tạo nhanh trong burst traffic. Do đó, khi chọn kiểu handoff, cần đặc biệt chú ý giới hạn max threads, nguồn downstream và chi phí tạo thread.

## 3. Loại queue làm thay đổi thời điểm mở rộng và từ chối

Trong `ThreadPoolExecutor`, khi số worker chưa tới `corePoolSize` thì task thường được giao cho worker mới. Khi đã tới core, executor thử `workQueue.offer(task)`: nếu queue nhận được, task được xếp chờ; nếu không nhận và pool còn dưới `maxPoolSize`, nó thử mở worker khác; cuối cùng mới đến rejection. Khi shutdown, trạng thái pool còn có thể khiến task bị từ chối sớm.

Điểm cần tập trung là **cùng lời gọi `offer` nhưng hai loại queue cho kết quả khác nhau**: `LinkedBlockingQueue` có chỗ lưu task, còn `SynchronousQueue` chỉ nhận khi một worker đang chờ handoff. Bảng tiếp theo phân tích điều này. Thuật toán bốn bước, race và các nhánh shutdown được trình bày đầy đủ ở bài “Thứ tự nhận tác vụ: tạo luồng cơ bản, xếp hàng, mở rộng rồi từ chối”.

## 4. Ví dụ diễn tiến với cùng core và max, chỉ đổi queueCapacity

Giả sử:

- `corePoolSize=2`.
- `maxPoolSize=4`.
- Mỗi task đều chạy lâu, tất cả worker còn bận trong lúc 7 task đến liên tiếp.
- Executor đang trống lúc bắt đầu, không có task nào hoàn tất giữa các lần gửi.

| Task đến | `queueCapacity=2` | `queueCapacity=0` |
| --- | --- | --- |
| T1 | Core worker 1 thực thi | Core worker 1 thực thi |
| T2 | Core worker 2 thực thi | Core worker 2 thực thi |
| T3 | Nằm trong queue (1/2) | Non-core worker 3 thực thi |
| T4 | Nằm trong queue (2/2) | Non-core worker 4 thực thi |
| T5 | Non-core worker 3 thực thi | Từ chối (đã bận 4 workers, không có chỗ queue) |
| T6 | Non-core worker 4 thực thi | Từ chối |
| T7 | Từ chối (4 workers đang bận, queue đã đầy) | Từ chối |

Kết quả tại thời điểm T7 được gửi:

- **Capacity 2:** 4 task đang chạy, 2 task chờ, một task bị từ chối.
- **Capacity 0:** 4 task đang chạy, không task nào được giữ trong queue, ba task bị từ chối.

Bảng là mô phỏng với điều kiện các task chưa hoàn tất. Trong runtime thực, worker có thể xong sớm và nhận task khác; những con số quan sát được sẽ khác. Cốt lõi không phải “queue 0 nhanh hơn” mà là **queue 0 ưu tiên mở thread/nhận hoặc từ chối ngay, queue dương có thêm không gian chờ trước khi mở rộng**.

## 5. Thực nghiệm chạy được bằng Java 21 + Spring Framework

Chương trình sau cố ý giữ các worker ở một `CountDownLatch` để tái hiện đúng tình huống queue đầy, không dựa vào `Thread.sleep()` và timing may rủi. Nó tạo hai `ThreadPoolTaskExecutor` lần lượt có capacity 1 và capacity 0, giữ nguyên `corePoolSize=1` và `maxPoolSize=2`.

**Cấu trúc dự án:**

```text
queue-capacity-demo/
├── pom.xml
└── src/main/java/example/QueueCapacityDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>queue-capacity-demo</artifactId>
  <version>1.0-SNAPSHOT</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>example.QueueCapacityDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/example/QueueCapacityDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class QueueCapacityDemo {
    public static void main(String[] args) throws InterruptedException {
        demonstrate(1);
        demonstrate(0);
    }

    private static void demonstrate(int capacity) throws InterruptedException {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(capacity);
        pool.setThreadNamePrefix("demo-");
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(5);
        pool.afterPropertiesSet();

        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch bothStarted = new CountDownLatch(2);
        CountDownLatch queuedDone = new CountDownLatch(1);

        Runnable holdWorker = () -> {
            firstStarted.countDown();
            bothStarted.countDown();
            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(holdWorker);
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First worker did not start");
            }

            if (capacity > 0) {
                pool.execute(queuedDone::countDown);
            }
            pool.execute(holdWorker);

            if (!bothStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Second worker did not start");
            }

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (TaskRejectedException ex) {
                rejected = true;
            }

            System.out.printf(
                    "capacity=%d queue=%s pool=%d waiting=%d rejected=%b%n",
                    capacity,
                    pool.getThreadPoolExecutor().getQueue().getClass().getSimpleName(),
                    pool.getPoolSize(),
                    pool.getQueueSize(),
                    rejected);

            release.countDown();
            if (capacity > 0 && !queuedDone.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Queued task was not executed");
            }
        } finally {
            release.countDown();
            pool.shutdown();
        }
    }
}
```

**Biên dịch và chạy** trong thư mục dự án:

```bash
mvn -q -DskipTests compile exec:java
```

**Output kiểm chứng:**

```text
capacity=1 queue=LinkedBlockingQueue pool=2 waiting=1 rejected=true
capacity=0 queue=SynchronousQueue pool=2 waiting=0 rejected=true
```

Chương trình biên dịch với `maven.compiler.release=21`, đã được chạy kiểm chứng trên JDK có hỗ trợ Java 21. Ý nghĩa hai dòng:

1. Với capacity 1: task đầu đang giữ core worker; task thứ hai nằm trong `LinkedBlockingQueue`; task thứ ba làm pool tăng lên 2 workers; task tiếp theo bị từ chối.
2. Với capacity 0: task đầu đang giữ core worker; task thứ hai làm pool tăng lên 2 workers; task tiếp theo bị từ chối ngay vì `SynchronousQueue` không thể chứa backlog.

`firstStarted` và `bothStarted` bảo đảm worker đã thực sự chạy trước khi đo. `release` giải phóng worker; `queuedDone` bảo đảm task từng nằm trong queue đã được xử lý. Đoạn `finally` bảo đảm thả latch và shutdown pool, hạn chế thread bị treo nếu kiểm tra thất bại.

Ở đây gọi `afterPropertiesSet()` vì ta tự tạo executor ngoài Spring container. Khi khai báo `ThreadPoolTaskExecutor` là bean do Spring quản lý, container gọi callback khởi tạo tương ứng; thông thường không cần gọi thủ công.

Nếu loại bỏ cơ chế giữ worker bằng latch, số `poolSize` và `waiting` có thể thay đổi theo lịch chạy; đó là hành vi bình thường của hệ thống đồng thời, không phải lỗi của queue.

## 6. Kết hợp queueCapacity với corePoolSize và maxPoolSize

Ba tham số tạo thành một chính sách tiếp nhận công việc, không nên tối ưu riêng lẻ.

### 6.1. corePoolSize

Đây là ngưỡng worker lõi: khi có ít hơn `corePoolSize` worker, pool ưu tiên tạo worker trước khi xếp task vào queue. Mặc định `ThreadPoolTaskExecutor` có core size 1.

Điều đó **không có nghĩa** các core threads luôn được tạo sẵn ngay khi khởi tạo; theo cấu hình thông thường, thread được tạo khi có task, trừ khi có cấu hình chủ động prestart.

### 6.2. maxPoolSize

Đây là giới hạn tổng worker của pool. Khi queue có thể tiếp tục nhận task, pool thường không mở rộng vượt core chỉ vì có backlog. Khi queue đầy hoặc không thể handoff, pool mới cố tăng đến max.

Ví dụ đặt `core=2, max=100, queueCapacity=10000` vẫn có thể chỉ duy trì hai worker trong thời gian dài, trong khi hàng nghìn task xếp hàng. `max=100` không có nghĩa có ngay 100 worker để xử lý backlog.

### 6.3. keepAliveSeconds và allowCoreThreadTimeOut

Worker vượt core có thể rút lui sau thời gian nhàn rỗi `keepAliveSeconds` (mặc định thường là 60 giây). Nếu bật `allowCoreThreadTimeOut`, core workers cũng có thể hết hạn khi nhàn rỗi theo quy tắc của `ThreadPoolExecutor`. Chúng ảnh hưởng đến cách pool co lại, **không thay đổi loại hàng đợi** đã chọn bởi `queueCapacity`.

### 6.4. Đổi queueCapacity khi chương trình đang chạy

Hàng đợi được tạo trong giai đoạn khởi tạo executor. Việc chỉ gọi `setQueueCapacity(...)` lên một executor **đã khởi tạo** không tự thay thế queue hiện hữu hay di chuyển các task đang chờ. Hãy coi lựa chọn dung lượng/loại queue là cấu hình lúc tạo pool; nếu muốn thay đổi, cần một kế hoạch tái tạo/reconfigure executor an toàn phù hợp với lifecycle.

Không suy rằng mọi setter trong `ThreadPoolTaskExecutor` đều được hỗ trợ cập nhật runtime như nhau. `corePoolSize` và `maxPoolSize` có hỗ trợ thay đổi động trên executor bên dưới, còn lựa chọn hàng đợi được chốt khi khởi tạo.

## 7. Cấu hình trong Spring application

Một cấu hình dùng hàng đợi có giới hạn và đặt tên bean rõ ràng:

```java
// Fragment trong lớp @Configuration của ứng dụng Spring.
@Bean("businessExecutor")
public ThreadPoolTaskExecutor businessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("business-");
    return executor;
}
```

Đây là **fragment** cần import `org.springframework.context.annotation.Bean` và `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` trong một class cấu hình Spring. Các con số 4/8/100 chỉ minh họa, không phải preset phù hợp mọi hệ thống. Bean phải được tạo và quản lý bởi Spring để callback khởi tạo và shutdown diễn ra đúng lifecycle.

Nếu dùng `@Async`, cần cấu hình kích hoạt xử lý async (trong Spring Framework thuần thường là `@EnableAsync`) rồi chỉ định executor:

```java
// Fragment trong Spring-managed service, lời gọi qua proxy @Async.
@Async("businessExecutor")
public void processAsync(String id) {
    // Công việc nền.
}
```

`@Async` đưa phương thức vào executor tương ứng khi lời gọi đi qua Spring proxy; lời gọi `this.processAsync(...)` trong cùng bean thường không áp dụng async theo proxy mặc định. Hơn nữa, `@Async` **không loại bỏ queue**, vì task vẫn được gửi đến executor và chịu cùng giới hạn/saturation.

Với Spring Boot có auto-configured task executor, property `spring.task.execution.pool.queue-capacity` có thể được dùng theo cấu hình Boot tương ứng, ví dụ:

```properties
spring.task.execution.pool.core-size=4
spring.task.execution.pool.max-size=8
spring.task.execution.pool.queue-capacity=100
```

Phạm vi của các property phụ thuộc vào executor mà Boot thực sự tự cấu hình. Nếu ứng dụng tự định nghĩa `@Bean ThreadPoolTaskExecutor` như trên, không nên mặc định rằng các property này sẽ tự áp vào bean tùy chỉnh; cần cấu hình qua builder hoặc setter thích hợp và kiểm tra trạng thái thực tế sau khởi tạo.

## 8. Nên chọn queueCapacity bao nhiêu?

Không có một giá trị chung phù hợp mọi ứng dụng. Hãy bắt đầu từ tính chất task, yêu cầu latency, giới hạn downstream và khả năng chịu backlog.

| Lựa chọn | Ưu điểm | Chi phí/rủi ro | Tình huống cân nhắc |
| --- | --- | --- | --- |
| `queueCapacity=0` | Không tích task chờ, thấy saturation sớm, pool có thể tăng worker nhanh tới max | Burst tạo thêm threads; rejection ngay khi tất cả workers bận; có thể gây tải dồn xuống DB/API | Muốn handoff trực tiếp, quản lý nghiêm `maxPoolSize` và giới hạn nguồn |
| Queue dương nhỏ, ví dụ 10–100 | Hấp thụ burst ngắn; làm rõ giới hạn backlog | Vẫn có queue latency và rejection; cần sizing theo load | Tác vụ ngắn-vừa, cần giới hạn bộ nhớ/độ trễ |
| Queue dương lớn | Ít rejection trong burst, không cần mở thread thêm sớm | Chờ lâu, memory retention, che giấu quá tải, maxPoolSize khó phát huy | Chỉ khi backlog lớn thực sự chấp nhận được và có giám sát |
| Mặc định `Integer.MAX_VALUE` | Thuận tiện cho thử nghiệm hoặc tải rất thấp | Rủi ro backlog tăng không kiểm soát trong tải dai dẳng, có thể làm cạn RAM | Không nên coi là backpressure an toàn cho production |

### 8.1. Đặt giới hạn bằng một ngân sách chờ

Giả sử các task đang được xử lý với throughput ổn định khoảng 40 task/s, và mục tiêu phần thời gian **nằm trong queue** không quá 0,5 giây ở điều kiện tải quan tâm. Suy luận đơn giản gợi ý chỉ muốn khoảng `40 × 0,5 = 20` task chờ ở mức đó.

Đây là phép ước lượng dùng để suy nghĩ, **không phải công thức bảo đảm**: service time có phân phối, burst traffic, task dài/ngắn khác nhau, multi-thread scheduling và downstream saturation làm latency thực tế thay đổi. Đo p95/p99 queue wait và rejection trong load test để xác nhận. Nếu tốc độ gửi task thường xuyên lớn hơn tốc độ xử lý, **bất kỳ queue hữu hạn nào cũng sẽ đầy theo thời gian**.

### 8.2. CPU-bound khác I/O-bound

- Với **CPU-bound**, tăng số worker quá số lõi CPU hữu dụng thường làm tăng context switch và cạnh tranh CPU. Queue hữu hạn và chính sách giới hạn đầu vào thường quan trọng hơn “đẻ nhiều threads”.
- Với **I/O-bound**, nhiều worker hơn có thể giữ mức độ đồng thời cao khi một số thread đang chờ mạng/DB. Tuy vậy, quá nhiều task đồng thời có thể làm cạn connection pool hoặc gây timeout ở service khác; cần giới hạn concurrency downstream.
- Với task thời gian rất khác nhau, một queue FIFO chung có thể khiến tác vụ nhỏ nằm sau tác vụ dài. Cân nhắc phân tách executor theo loại việc khi có bằng chứng đo đạc.

## 9. Khi queue đầy: rejection và backpressure

Mặc định, executor bên dưới thường dùng chính sách từ chối kiểu abort. Spring `ThreadPoolTaskExecutor` biểu lộ sự kiện từ chối qua `TaskRejectedException` khi gọi `execute(...)`. Cần phân biệt **task bị từ chối lúc submit** với **task đã được chấp nhận nhưng chạy và ném exception ở worker**.

Một số chính sách có thể cấu hình bằng `setRejectedExecutionHandler(...)`:

- **AbortPolicy:** từ chối bằng exception; caller quyết định báo lỗi, retry giới hạn, hoặc lưu công việc sang cơ chế bền vững.
- **CallerRunsPolicy:** trong điều kiện executor chưa shutdown, caller tự thực thi task nếu pool không nhận, tạo một dạng điều tiết vì caller bị chậm lại. Đừng dùng tùy tiện với request thread nhạy latency, event loop hoặc task có thể block lâu.
- **DiscardPolicy/DiscardOldestPolicy:** có thể làm mất task; chỉ phù hợp khi đã phân tích rõ semantics và chấp nhận mất/loại task. Không dùng ngầm cho công việc nghiệp vụ bắt buộc hoàn thành.

Một `queueCapacity` hữu hạn kết hợp rejection rõ ràng giúp hệ thống **thừa nhận giới hạn năng lực**. Nhưng nếu caller retry liên tục không backoff, hoặc lưu vô hạn vào một queue khác, quá tải chỉ bị dời chỗ.

Nếu nghiệp vụ đòi hỏi việc phải tồn tại qua restart, phải có cơ chế bền vững như transaction outbox hoặc message broker phù hợp; hàng đợi nội bộ của `ThreadPoolTaskExecutor` không cung cấp durability, acknowledgement hay retry bền vững.

## 10. Quan sát đúng trước khi thay queueCapacity

Các chỉ số hữu ích nên đo theo thời gian:

1. **Pool size, active count, core/max:** hiện có bao nhiêu worker và bao nhiêu worker đang bận; lưu ý metric có thể là snapshot thay đổi rất nhanh.
2. **Queue size/capacity:** queue đang giữ bao nhiêu task; với `SynchronousQueue`, size=0 là thuộc tính cấu trúc, không cho biết saturation.
3. **Thời gian chờ vào queue:** tính từ lúc submit đến lúc task bắt đầu chạy. Có thể bọc task ở lớp submit để ghi timestamp; tách queue wait khỏi execution time.
4. **Thời gian thực thi task:** đo thời gian chạy sau khi worker nhận; kết hợp throughput và tỷ lệ chờ/CPU.
5. **Rejection, timeout, error, cancellation:** phản ánh giới hạn nhận việc và độ tin cậy. Không chỉ đo CPU tổng.
6. **Giới hạn downstream:** DB connection pool, HTTP client concurrency, network latency, GC/memory và CPU quota container.

Trong ví dụ Java, `getThreadPoolExecutor().getQueue()` được dùng **chỉ để xác nhận loại queue và quan sát**. Tránh chỉnh sửa thủ công queue, lấy `Runnable` ra ngoài hoặc dựa vào cấu trúc nội bộ trong business service; thao tác đó dễ phá giả định concurrency của executor.

Có thể gắn Micrometer/Actuator cho executor mà ứng dụng quản lý nếu nền tảng hỗ trợ; cần xác minh bean được instrument và dashboard phản ánh đúng pool đang dùng. Không đánh giá một giá trị metric tại duy nhất một thời điểm.

## 11. Lỗi phổ biến

1. **Nghĩ `queueCapacity=0` là queue dung lượng 0 vẫn xếp được một ít task:** thực tế Spring dùng `SynchronousQueue`, không có backlog lưu trữ.
2. **Cho rằng queue dương chọn `ArrayBlockingQueue`:** mặc định Spring dùng `LinkedBlockingQueue`.
3. **Tăng `maxPoolSize` mà giữ queue vô hạn:** các task vẫn được xếp hàng sau core; pool hiếm khi mở rộng đến max.
4. **Hiểu queueCapacity là tổng số task được nhận:** queue chỉ đếm việc **đang chờ**, không bao gồm task đang chạy trên worker.
5. **Đặt queue quá lớn để tránh lỗi:** có thể thay rejection sớm bằng latency cao và nguy cơ hết memory.
6. **Đặt queue bằng 0 nhưng không giới hạn max:** có thể tạo quá nhiều threads khi burst, gây nghẽn downstream.
7. **Chỉ nhìn `getQueueSize() == 0`:** với `SynchronousQueue`, metric này luôn bằng 0 kể cả khi mọi worker bận.
8. **Thay `setQueueCapacity` sau initialization rồi tưởng queue đổi:** queue đã được tạo; cấu hình lại an toàn yêu cầu lifecycle phù hợp.
9. **Bỏ qua `TaskRejectedException`:** caller có thể báo thành công dù executor không nhận task; phải định nghĩa xử lý quá tải.
10. **Tin rằng queue FIFO bảo đảm hoàn tất FIFO:** với nhiều worker, thứ tự kết thúc phụ thuộc thời gian chạy và scheduling.
11. **Chỉ kiểm thử không tải:** queue capacity, max pool và rejection thường chỉ hiện rõ khi tất cả worker đang bận; cần thử nghiệm có kiểm soát và đo dưới tải đại diện.

## 12. Bài tập tự kiểm tra

**Tình huống A.** Pool có `core=3, max=6, queueCapacity=2`; 3 worker đều bận, không task nào hoàn tất. Ba task mới đến lần lượt. Điều gì xảy ra?

- Task mới thứ nhất và thứ hai vào `LinkedBlockingQueue`.
- Task mới thứ ba khiến pool thử mở worker thứ tư vì queue đầy.
- Pool **không** đợi cho đến khi tạo đủ 6 worker rồi mới xếp queue.

**Tình huống B.** Cùng pool nhưng `queueCapacity=0`. Ba task mới đến khi 3 core workers đang bận thì sao?

- Không có chỗ lưu task trong queue; pool có thể mở thêm workers thứ 4, 5, 6 để chạy ba task mới.
- Nếu cả 6 workers vẫn bận, task tiếp theo không bàn giao được và bị từ chối theo rejection policy.

**Tình huống C.** Ứng dụng có 2 workers, 500 task đang chờ, CPU chỉ 15%. Có nên tăng `queueCapacity` thêm nữa không?

Không thể quyết định chỉ từ CPU thấp. Hãy kiểm tra workers đang chờ I/O/lock, DB connection pool, thời gian queue wait, tốc độ producer/consumer và timeout. Tăng queue không làm task chạy nhanh hơn, chỉ cho phép backlog lớn hơn.

## 13. Những điểm cần nhớ

- `queueCapacity > 0` → Spring tạo `LinkedBlockingQueue` có dung lượng chỉ định.
- `queueCapacity <= 0` → Spring tạo `SynchronousQueue` không chứa backlog.
- Quy tắc nhận việc thông thường: **tạo core worker → thử queue → tăng đến max nếu queue không nhận → reject nếu hết chỗ**.
- Queue lớn có thể tăng độ trễ và giữ bộ nhớ; queue 0 khiến pool mở thread sớm nhưng có thể reject sớm. Cần chọn cùng `corePoolSize`, `maxPoolSize`, mức tải và nguồn downstream.
- Quan sát queue wait, active threads, saturation và rejection; riêng queue size không đủ, đặc biệt với `SynchronousQueue`.
- `ThreadPoolTaskExecutor` là executor trong bộ nhớ, không phải hệ thống hàng đợi bền vững.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java 21 — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Java 21 — SynchronousQueue API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)