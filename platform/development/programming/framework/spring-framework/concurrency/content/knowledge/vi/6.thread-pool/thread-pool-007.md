# keepAliveSeconds và allowCoreThreadTimeOut trong ThreadPoolTaskExecutor

## 1. Mục tiêu học tập

Khi xử lý nhiều công việc bất đồng bộ trong ứng dụng Spring, một nhóm luồng (**thread pool**) giúp tái sử dụng worker threads thay vì tạo thread nền tảng mới cho mọi tác vụ. Hai tham số quan trọng quyết định điều gì xảy ra **sau khi lưu lượng giảm** là `keepAliveSeconds` và `allowCoreThreadTimeOut`.

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của `ThreadPoolTaskExecutor.setKeepAliveSeconds(int)` và `setAllowCoreThreadTimeOut(boolean)`.
- Phân biệt **core threads** và **non-core threads**, cấu hình “duy trì core threads” với “cho cả core threads được thu hồi”.
- Dự đoán tương tác giữa `corePoolSize`, `maxPoolSize`, `queueCapacity` và keep-alive khi pool tăng/giảm quy mô.
- Cấu hình đúng một `ThreadPoolTaskExecutor` trong Spring, biết khi nào cần giữ worker nóng để giảm độ trễ và khi nào nên tiết kiệm tài nguyên lúc nhàn rỗi.
- Tránh các lỗi như đặt keep-alive bằng 0 khi bật core timeout, nhầm idle timeout với thời hạn chạy task, hoặc tưởng `maxPoolSize` luôn điều khiển số worker ngay khi tải tăng.
- Quan sát pool bằng thông số runtime và kiểm tra được hành vi qua ví dụ Java 17+.

**Phạm vi:** Bài này tập trung vào `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` của Spring Framework, vốn quản lý một `java.util.concurrent.ThreadPoolExecutor` của JDK. Các nhận xét về thời gian chờ áp dụng cho **platform thread pools** kiểu này. Không áp đặt chúng lên mọi triển khai `TaskExecutor` hoặc executor tạo **virtual thread cho mỗi task**.

## 2. Hai tham số là gì?

### 2.1. `keepAliveSeconds` — thời gian một worker được phép chờ việc

~~~java
executor.setKeepAliveSeconds(30);
~~~

Đoạn mã trên chỉ minh họa một lời gọi setter trên `ThreadPoolTaskExecutor` đã có. Giá trị `30` nghĩa là **30 giây nhàn rỗi** được dùng làm thời hạn giữ worker đủ điều kiện bị thu hồi; không phải thời gian tối đa để chạy một task. Khi một worker kết thúc tác vụ và không lấy được tác vụ mới trong thời hạn này, pool có thể cho worker đó kết thúc.

**Mặc định của Spring `ThreadPoolTaskExecutor` là 60 giây.** Theo quy tắc mặc định của `ThreadPoolExecutor`, keep-alive chỉ áp dụng cho các worker **vượt quá** `corePoolSize`. Như vậy, nếu `corePoolSize = 2`, `maxPoolSize = 6` và pool tạm tăng lên 5 workers, các worker dư trên mức core có thể kết thúc sau thời gian nhàn rỗi; các core workers không tự kết thúc chỉ vì không có việc khi chưa bật core timeout.

Thời hạn keep-alive chỉ bắt đầu có ý nghĩa khi **worker đang chờ công việc**, không phải từ lúc ứng dụng khởi động, từ lúc worker được tạo hay từ lúc task bắt đầu chạy. Một task đang xử lý 5 phút **không bị ngắt** vì `keepAliveSeconds = 30`.

### 2.2. `allowCoreThreadTimeOut` — core workers có được tự kết thúc không?

~~~java
executor.setAllowCoreThreadTimeOut(true);
~~~

Mặc định là **`false`**. Khi `false`, một core worker đã được tạo thường tiếp tục tồn tại dù đang nhàn rỗi. Khi `true`, **core workers cũng chịu cùng keep-alive policy như non-core workers**. Vì vậy, nếu không có tác vụ trong một khoảng thời gian đủ dài, số worker thực tế có thể giảm về **0**, dù cấu hình `corePoolSize` vẫn lớn hơn 0. Khi có task mới, executor tạo worker trở lại theo nhu cầu.

Điều kiện bắt buộc của JDK khi bật core timeout: **`keepAliveTime > 0`**. Nếu bật `ThreadPoolExecutor.allowCoreThreadTimeOut(true)` trong khi keep-alive bằng 0, JDK ném `IllegalArgumentException`. Khi dùng Spring, hãy cấu hình keep-alive dương trước khi khởi tạo executor nếu định bật cờ này.

### 2.3. Bảng phân biệt nhanh

| Cấu hình | Core workers khi nhàn rỗi | Workers vượt core khi nhàn rỗi | Khi có việc trở lại |
| --- | --- | --- | --- |
| `keepAliveSeconds=60`, `allowCoreThreadTimeOut=false` (mặc định) | Được giữ lại sau khi đã tạo | Được thu hồi sau thời gian chờ xấp xỉ 60 giây | Tái sử dụng core còn sống hoặc tạo thêm khi cần |
| `keepAliveSeconds=10`, `allowCoreThreadTimeOut=false` | Vẫn được giữ | Được thu hồi nhanh hơn sau khoảng 10 giây nhàn rỗi | Core còn sống xử lý các đợt việc mới |
| `keepAliveSeconds=10`, `allowCoreThreadTimeOut=true` | Cũng được thu hồi khi đủ nhàn rỗi | Được thu hồi | Pool có thể từ 0 workers tạo lại các worker |
| `keepAliveSeconds=0`, `allowCoreThreadTimeOut=true` | **Không hợp lệ** | — | JDK không cho bật core timeout với keep-alive bằng 0 |

Các mốc trên là **quy tắc chờ tối đa cho idle worker**, không phải đồng hồ bảo đảm thu hồi chính xác ở giây thứ 10 hoặc 60. Lập lịch hệ điều hành, công việc đến trong lúc chờ và trạng thái pool ảnh hưởng thời điểm quan sát. Cần phân biệt **`getCorePoolSize()` (cấu hình)** với **`getPoolSize()` (số worker thực tế tại thời điểm đọc)**.

## 3. Cơ chế của ThreadPoolExecutor: tạo worker, đưa vào queue, rồi mới mở rộng

Hai cấu hình timeout chỉ có thể hiểu chính xác khi đặt cạnh các thuộc tính khác của `ThreadPoolTaskExecutor`:

- `corePoolSize`: số worker cơ sở mục tiêu; mặc định Spring là **1**.
- `maxPoolSize`: giới hạn số worker tối đa; mặc định là **`Integer.MAX_VALUE`**.
- `queueCapacity`: số tác vụ có thể nằm trong hàng đợi; mặc định là **`Integer.MAX_VALUE`**.
- `keepAliveSeconds`: thời hạn nhàn rỗi để worker đủ điều kiện kết thúc; mặc định **60**.
- `allowCoreThreadTimeOut`: core workers có dùng keep-alive hay không; mặc định **false**.

Với `ThreadPoolTaskExecutor`, `queueCapacity > 0` tạo `LinkedBlockingQueue` có giới hạn tương ứng; `queueCapacity <= 0` dùng `SynchronousQueue` (hàng đợi trao tay, không có chỗ lưu task chờ).

### 3.1. Trình tự khi task đến

Khi gọi `execute` hoặc `submit`:

1. Nếu số worker hiện có **chưa đến `corePoolSize`**, executor ưu tiên tạo worker để chạy task mới.
2. Khi đã có ít nhất core workers, executor ưu tiên **đưa task vào queue**.
3. Chỉ khi **không thể đưa vào queue** và số worker chưa tới `maxPoolSize`, nó tạo thêm non-core worker.
4. Nếu worker đã tới max và queue không nhận thêm task, tác vụ bị **từ chối** theo `RejectedExecutionHandler`.

Sơ đồ:

~~~text
Task mới
   |
   +-- workers < corePoolSize? -- Có --> tạo core worker
   |                              
   +-- Không --> queue còn chỗ? --- Có --> xếp hàng chờ
                    |
                    +-- Không --> workers < maxPoolSize? -- Có --> thêm worker
                                                |
                                                +-- Không --> từ chối task
~~~

**Hệ quả rất quan trọng:** `maxPoolSize` thường **không làm pool tăng** chỉ vì core workers đang bận, nếu `queueCapacity` còn chỗ. Với queue gần như vô hạn, executor thường chỉ cần chạy ở mức core và tiếp tục xếp hàng. Khi đó các non-core workers ít khi được tạo, nên việc chỉnh `keepAliveSeconds` cho non-core có thể gần như không tạo khác biệt quan sát được.

### 3.2. Ví dụ lý thuyết với queue hữu hạn

Giả sử cấu hình:

~~~java
executor.setCorePoolSize(1);
executor.setMaxPoolSize(3);
executor.setQueueCapacity(1);
executor.setKeepAliveSeconds(5);
executor.setAllowCoreThreadTimeOut(false);
~~~

Đây là cấu hình minh họa, chưa phải chương trình độc lập. Giả sử các task chạy đủ lâu để không có task nào hoàn tất trước khi nộp task thứ năm:

| Task nộp | Điều pool làm | Số worker / số task chờ, ở trạng thái giả định này |
| --- | --- | --- |
| Task 1 | Tạo core worker | 1 worker / 0 chờ |
| Task 2 | Đưa vào queue | 1 worker / 1 chờ |
| Task 3 | Queue đầy, tạo worker thứ 2 | 2 workers / 1 chờ |
| Task 4 | Queue vẫn đầy, tạo worker thứ 3 | 3 workers / 1 chờ |
| Task 5 | Max đạt 3 và queue đầy, áp dụng rejection policy | 3 workers / 1 chờ |

Khi tất cả hoàn tất và pool nhàn rỗi, với `allowCoreThreadTimeOut=false`, hai workers vượt core có thể được thu hồi sau thời gian nhàn rỗi tương ứng; **1 core worker** vẫn có thể ở lại. Nếu bật `true` với keep-alive dương, core worker cuối cùng cũng có thể bị thu hồi.

Bảng trên là một **lịch trình giả định có task bị giữ lại**, không phải khẳng định các lần submit thông thường luôn tạo đúng số worker đó: task thực tế có thể hoàn thành giữa hai lần nộp.

### 3.3. Tại sao “cho core timeout” vẫn hữu ích khi queue > 0?

Theo Javadoc Spring, bật `allowCoreThreadTimeOut` giúp pool **tăng khi có nhu cầu và giảm lúc rảnh** ngay cả với queue có dung lượng dương. Lý do: các core workers bình thường vốn được giữ lại vĩnh viễn khi nhàn rỗi, còn cờ này cho phép chúng được thu hồi.

Tuy nhiên, cờ này **không đảo trình tự nhận task**: pool vẫn ưu tiên queue khi đã có core workers và queue chưa đầy. Nếu muốn tăng mạnh số worker khi có burst, phải xem `queueCapacity`, tốc độ task đến và `maxPoolSize` cùng nhau.

## 4. Ví dụ Spring hoàn chỉnh: cấu hình và kiểm tra chính sách

Ví dụ sau là chương trình Java chạy độc lập, dùng **JDK 17+**, Maven và **Spring Framework 6.1.3**. Nó khởi tạo `ThreadPoolTaskExecutor` thủ công, đọc chính sách thực sự trên `ThreadPoolExecutor` bên trong rồi xử lý một task trả kết quả.

Cấu trúc:

~~~text
keepalive-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── KeepAliveDemo.java
~~~

### 4.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>keepalive-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                <configuration>
                    <mainClass>demo.KeepAliveDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dùng dependency `spring-context` đủ cho lớp `ThreadPoolTaskExecutor` trong ví dụ này. Trong ứng dụng Spring Boot thực tế, nên giữ phiên bản Spring Framework do BOM/parent của dự án quản lý, tránh tự ghim một bản khác chỉ vì đoạn minh họa.

### 4.2. `src/main/java/demo/KeepAliveDemo.java`

~~~java
package demo;

import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class KeepAliveDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(2);
        executor.setKeepAliveSeconds(3);           // timeout nhàn rỗi: 3 giây
        executor.setAllowCoreThreadTimeOut(true);   // core workers cũng có thể hết hạn
        executor.setThreadNamePrefix("lesson-");
        executor.initialize();

        try {
            System.out.println("core=" + executor.getCorePoolSize());
            System.out.println("max=" + executor.getMaxPoolSize());
            System.out.println("keepAliveSeconds="
                    + executor.getKeepAliveSeconds());
            System.out.println("coreTimeout="
                    + executor.getThreadPoolExecutor()
                              .allowsCoreThreadTimeOut());
            System.out.println("effectiveKeepAliveSeconds="
                    + executor.getThreadPoolExecutor()
                              .getKeepAliveTime(TimeUnit.SECONDS));

            Future<Integer> answer = executor.submit(() -> 21 * 2);
            System.out.println("answer=" + answer.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy trong thư mục `keepalive-demo`:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do chương trình in ra (không tính log riêng của Maven nếu có):

~~~text
core=2
max=4
keepAliveSeconds=3
coreTimeout=true
effectiveKeepAliveSeconds=3
answer=42
~~~

**Diễn giải:** `initialize()` tạo executor nội bộ với các thuộc tính được cung cấp. Gọi `getThreadPoolExecutor()` sau khi khởi tạo giúp xem **chính sách thực sự của JDK**: `allowsCoreThreadTimeOut()` trả `true` và `getKeepAliveTime(...)` là 3 giây. `submit` và `Future.get()` xác nhận pool nhận và xử lý task. Ví dụ cố tình **không in số worker tức thời** vì con số ấy phụ thuộc lịch chạy và thời điểm quan sát, không có stdout cố định đáng tin cậy.

Khi tự tạo executor ngoài Spring container như trên, ứng dụng phải chủ động quản lý lifecycle. Lệnh `shutdown()` là thao tác kết thúc pool, **khác hoàn toàn** với keep-alive tự thu hồi idle workers trong khi pool vẫn có thể nhận task mới.

## 5. Thí nghiệm quan sát việc thu hồi worker, không suy luận bằng sleep ngắn

Bạn có thể kiểm tra thời gian sống của worker bằng Java thuần trước khi đem nguyên tắc vào Spring. Đoạn dưới dùng `ThreadPoolExecutor` của JDK, bảo đảm task đã hoàn tất rồi mới quan sát. Nó **không phụ thuộc Spring** và chỉ dùng JDK 17+.

Lưu thành `CoreTimeoutExperiment.java`:

~~~java
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class CoreTimeoutExperiment {

    public static void main(String[] args) throws Exception {
        observe(false);
        observe(true);
    }

    private static void observe(boolean allowCoreTimeout)
            throws Exception {

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 1, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>()
        );
        pool.allowCoreThreadTimeOut(allowCoreTimeout);

        try {
            pool.submit(() -> 42).get(); // chờ task kết thúc
            System.out.println("coreTimeout=" + allowCoreTimeout);
            System.out.println("poolSizeAfterTask=" + pool.getPoolSize());

            // Chờ hơn keepAlive 1 giây để quan sát.
            // Không dùng kết quả này làm assertion cố định.
            Thread.sleep(1500);
            System.out.println("poolSizeAfterIdle=" + pool.getPoolSize());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CoreTimeoutExperiment.java
java CoreTimeoutExperiment
~~~

**Một kết quả thường quan sát được** trên máy ít tải là:

~~~text
coreTimeout=false
poolSizeAfterTask=1
poolSizeAfterIdle=1
coreTimeout=true
poolSizeAfterTask=1
poolSizeAfterIdle=0
~~~

Đây là **ví dụ kết quả quan sát**, không phải stdout bất biến. Một worker có thể chưa bị thu hồi tại đúng thời điểm `Thread.sleep(1500)` kết thúc nếu máy bận, bị tạm dừng lâu hoặc việc lập lịch khác dự kiến. Mục đích là đối chiếu **xu hướng**: khi giữ core, worker tồn tại; khi cho core timeout, nó có thể biến mất. Tránh viết test thành công/thất bại chỉ dựa trên một lần đọc `getPoolSize()` sau `sleep()` ngắn. Với kiểm thử tự động, dùng polling có deadline phù hợp và không giả định thời điểm hủy chính xác từng mili giây.

Chú ý: phép thử chọn `corePoolSize=maxPoolSize=1` để loại bỏ non-core workers; do đó sự khác biệt quan sát được đến **từ cờ core timeout**.

## 6. Cấu hình khi Spring quản lý bean

Trong ứng dụng dùng component scanning và cấu hình Spring, nên tạo **một bean dùng chung** thay vì tạo pool mới cho mỗi request.

Ví dụ cấu hình trong `WorkerPoolConfig.java` (class tích hợp vào ứng dụng Spring hiện có; không phải project độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class WorkerPoolConfig {

    @Bean("workerTaskExecutor")
    public ThreadPoolTaskExecutor workerTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);
        executor.setAllowCoreThreadTimeOut(true);
        executor.setThreadNamePrefix("worker-");
        return executor;
    }
}
~~~

Khi bean do Spring quản lý, container phụ trách khởi tạo và đóng executor theo vòng đời bean. Đoạn cấu hình **không tự khiến mọi `@Async` trong ứng dụng dùng bean này**: nếu có nhiều executor, cần chọn đúng tên/`@Qualifier` hoặc cấu hình executor dùng cho asynchronous method invocation.

Ví dụ chọn executor theo tên khi ứng dụng đã bật async processing:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {

    @Async("workerTaskExecutor")
    public void notifyLater(String message) {
        System.out.println(message);
    }
}
~~~

Đoạn service minh họa tích hợp, không phải một chương trình độc lập. `@Async` làm việc qua proxy khi cấu hình async được bật; lệnh gọi nội bộ trong cùng instance có thể không qua proxy nên không chuyển sang worker pool như mong đợi. Nếu muốn nộp trực tiếp, inject `ThreadPoolTaskExecutor`/`AsyncTaskExecutor` tương ứng rồi gọi `execute` hoặc `submit`.

### Khi nào cờ này không có tác dụng?

- `SimpleAsyncTaskExecutor` không phải `ThreadPoolTaskExecutor` dùng pool tái sử dụng worker; đừng áp dụng quy tắc giữ/thu hồi core workers cho nó.
- Executor virtual-thread-per-task trong Java 21+ không có cùng cấu trúc core/max workers để chỉnh bằng hai setter này. Các carrier threads của JVM cũng không được điều khiển thông qua `ThreadPoolTaskExecutor.setKeepAliveSeconds`.
- Một `@Async` method dùng executor khác bean vừa cấu hình sẽ không chịu các thông số của bean đó.

Vì vậy, trước khi phân tích hiệu quả của `allowCoreThreadTimeOut`, hãy xác minh **executor nào thực sự đang chạy task**.

## 7. Cân nhắc hiệu năng: giảm tài nguyên hay giảm độ trễ khởi động?

Chọn `allowCoreThreadTimeOut` dựa vào hình dạng tải.

| Workload / mục tiêu | Gợi ý ban đầu | Lý do và đánh đổi |
| --- | --- | --- |
| Traffic liên tục, các task ngắn đến đều | `false`, giữ một lượng core workers hợp lý | Workers đã có sẵn, tránh chi phí tạo lại thread thường xuyên |
| Job ít khi chạy, thỉnh thoảng bùng tải | `true` với keep-alive dương vừa phải | Khi nhàn rỗi lâu có thể giảm worker về 0, đổi lại lần task mới cần tạo thread |
| Nhiều đợt burst cách nhau vài giây | Không đặt keep-alive quá nhỏ, thử `false` hoặc khoảng thời gian dài hơn | Tránh chu kỳ tạo/hủy worker liên tục (thread churn) |
| Task blocking I/O, nhiều request song song | Đo pool size, queue wait, max, downstream capacity | Keep-alive chỉ kiểm soát worker **lúc nhàn rỗi**, không giải quyết task đang block |
| Cần bảo vệ bộ nhớ khi không hoạt động | Thử `true` nhưng giới hạn core/max/queue theo tải | Tài nguyên giảm lúc rảnh nhưng không bảo đảm giảm peak usage |

**Không có một keep-alive tối ưu cho mọi dịch vụ.** Cấu hình tốt phụ thuộc độ dài task, tần suất đến, độ nhạy latency, khả năng scale, giới hạn CPU/memory và chi phí tạo thread. Tăng thời gian giữ workers thường giảm thread churn nhưng dùng thêm tài nguyên khi traffic thấp; giảm thời gian giữ workers tiết kiệm tài nguyên lúc rảnh nhưng có thể tăng độ trễ khởi động khi traffic quay lại.

### Những số liệu nên theo dõi

- **`poolSize`:** tổng worker thực đang tồn tại ở thời điểm đo; khác với `corePoolSize` cấu hình.
- **`activeCount`:** số worker đang thực thi task, thường là số liệu gần đúng.
- **`queue.size()`:** số task đang đợi; queue dài tăng nguy cơ latency cao.
- **`completedTaskCount` và throughput:** số task hoàn tất, dùng để thấy khả năng phục vụ.
- **Rejection count, task duration, queue waiting time, p95/p99 latency, CPU và memory:** phản ánh tác động lên hệ thống thực.

Với `ThreadPoolTaskExecutor` có thể đọc một số thông số:

~~~java
// Fragment trong ứng dụng đã có biến executor kiểu ThreadPoolTaskExecutor.
int workers = executor.getPoolSize();
int running = executor.getActiveCount();
int waiting = executor.getThreadPoolExecutor().getQueue().size();
boolean coreTimeout =
        executor.getThreadPoolExecutor().allowsCoreThreadTimeOut();
~~~

Các phép đọc này là **snapshot**, có thể thay đổi ngay sau đó; thích hợp monitoring/diagnostics, không phải cơ chế điều phối task. Không viết logic nghiệp vụ “nếu queue đang bằng 0 thì chắc chắn task tiếp theo sẽ chạy ngay”.

### Thay đổi cấu hình khi chương trình đang chạy

Javadoc Spring cho biết `setKeepAliveSeconds(...)` hỗ trợ điều chỉnh tại runtime, chẳng hạn qua JMX. Tuy nhiên khi thay đổi cấu hình của một pool đang hoạt động, cần kiểm tra tính hợp lệ với `allowCoreThreadTimeOut`: không thể đổi thời gian giữ worker về 0 khi core timeout đang được bật. Các thay đổi `corePoolSize`/`maxPoolSize` cũng có thể ảnh hưởng số worker được giữ hoặc thu hồi.

Nếu phải chỉnh tại runtime, nên quản lý thay đổi qua một cơ chế cấu hình được kiểm soát và có khả năng quan sát; không coi việc sửa một file properties là chắc chắn cập nhật ngay một bean đã khởi tạo. Những setter cấu trúc như `queueCapacity` chủ yếu tác động lúc tạo queue; không mặc định coi chúng là cấu hình động của queue đã tồn tại.

## 8. Các hiểu lầm thường gặp

1. **“`keepAliveSeconds=30` buộc mọi task kết thúc sau 30 giây.”** Sai. Đó là thời hạn **worker rảnh chờ task**, không phải deadline của task. Timeout nghiệp vụ, HTTP và DB phải cấu hình riêng.
2. **“`corePoolSize=4` nghĩa là luôn có 4 threads ngay khi bean tạo xong.”** Sai. Mặc định core workers được tạo khi có task; muốn khởi tạo trước có `setPrestartAllCoreThreads(true)`. Ngay cả khi prestart, bật core timeout vẫn cho phép chúng bị thu hồi khi rảnh.
3. **“`allowCoreThreadTimeOut=true` làm pool không còn corePoolSize.”** Sai. Thuộc tính core vẫn được dùng khi nhận task và quyết định quy tắc mở rộng; chỉ việc giữ core workers lúc nhàn rỗi thay đổi.
4. **“`maxPoolSize=100` chắc chắn sẽ có 100 workers khi tải tăng.”** Sai. Pool ưu tiên queue sau khi đạt core; queue không đầy thì có thể không tạo non-core workers.
5. **“`keepAliveSeconds=0` cùng core timeout true làm giải phóng tức thì.”** Sai. JDK **từ chối** trạng thái core timeout true với keep-alive bằng 0.
6. **“Worker kết thúc do keep-alive là task bị hủy.”** Sai. Chỉ worker đang **nhàn rỗi** mới đủ điều kiện thu hồi; task đang chạy không bị dừng bởi cài đặt này.
7. **“Bật core timeout là cơ chế shutdown service.”** Sai. Pool vẫn hoạt động và có thể tạo lại worker cho task mới; shutdown là một lifecycle action riêng.
8. **“ThreadPoolTaskExecutor và mọi Spring TaskExecutor có cùng thuộc tính.”** Sai. Các implementation khác nhau có mô hình quản lý thread khác nhau.
9. **“Chỉ cần thử `Thread.sleep(500)` rồi so `getPoolSize()` là chứng minh đúng/sai tuyệt đối.”** Sai. Trạng thái động phụ thuộc scheduling; cần quan sát đủ khoảng thời gian và dùng kiểm tra chịu được độ trễ.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Pool có `corePoolSize=3`, `maxPoolSize=8`, `keepAliveSeconds=20` và `allowCoreThreadTimeOut=false`. Khi traffic dừng, các workers được thu hồi thế nào?  
**Trả lời:** Những worker vượt core có thể hết hạn sau khoảng 20 giây nhàn rỗi. Các core workers đã tạo được giữ lại khi không có việc.

**Câu 2.** Với cùng cấu hình nhưng đặt `allowCoreThreadTimeOut=true`, số worker cuối cùng có thể là bao nhiêu?  
**Trả lời:** Có thể giảm về **0** nếu tất cả workers nhàn rỗi đủ lâu; `corePoolSize=3` vẫn giữ nguyên là tham số cấu hình để phục vụ task đến sau.

**Câu 3.** Pool `corePoolSize=2`, `maxPoolSize=20`, `queueCapacity=Integer.MAX_VALUE` có nhất thiết mở rộng đến 20 workers lúc tải cao?  
**Trả lời:** Không. Khi đã có 2 core workers, task mới thường được đưa vào queue gần như vô hạn, nên pool thường không phải tạo thêm workers vượt core.

**Câu 4.** Bật `allowCoreThreadTimeOut=true` trong khi `keepAliveSeconds=0` có hợp lệ không?  
**Trả lời:** Không. JDK yêu cầu keep-alive dương để core threads được phép timeout.

**Câu 5.** Một tác vụ đang gọi HTTP lâu hơn thời gian keep-alive có bị ngắt không?  
**Trả lời:** Không do keep-alive. Worker đang bận thực thi task; cần timeout của HTTP client hoặc nghiệp vụ riêng.

**Câu 6.** Vì sao bật core timeout giúp giảm tài nguyên lúc traffic thấp nhưng có thể tăng latency của request đầu tiên sau thời gian rảnh?  
**Trả lời:** Pool có thể đã thu hồi tất cả workers và phải tạo thread mới khi task kế tiếp đến.

## 10. Tài liệu tham khảo chính thức

- [Spring Framework 6.2.14 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setKeepAliveSeconds`, `setAllowCoreThreadTimeOut`, `corePoolSize`, `maxPoolSize`, `queueCapacity` và mặc định.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): API tương ứng phiên bản chạy trong ví dụ Maven.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): quy tắc tăng worker/queue, idle keep-alive, core timeout, rejection và giám sát.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): các TaskExecutor implementation, cấu hình và lựa chọn executor cho asynchronous processing.
