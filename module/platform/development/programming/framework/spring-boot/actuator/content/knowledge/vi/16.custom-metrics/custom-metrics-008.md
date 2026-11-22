# Đóng gói phép đo dùng chung bằng MeterBinder

## 1. Từ các lệnh đăng ký rải rác đến một bộ phép đo

Một hệ thống xử lý ảnh có hai hàng đợi: tạo ảnh thu nhỏ và lập chỉ mục tìm kiếm. Với mỗi hàng đợi, người vận hành cần biết:

- Có bao nhiêu tác vụ đang chờ?
- Còn bao nhiêu chỗ để nhận thêm tác vụ?

Nếu mỗi dịch vụ tự viết các lệnh đăng ký, chúng có thể dùng tên khác nhau cho cùng một đại lượng, thiếu nhãn phân biệt hàng đợi hoặc chỉ đăng ký một nửa bộ phép đo. Khi mở thêm một ứng dụng, cả quy ước lẫn mã đăng ký lại bị sao chép.

**MeterBinder là một hợp đồng Micrometer để đóng gói việc đăng ký một nhóm phép đo vào một MeterRegistry.** Nó phù hợp khi một thành phần có nhiều phép đo liên quan hoặc khi cùng cách đo được dùng cho nhiều đối tượng, nhiều ứng dụng.

Đóng gói ở đây gồm cả quy ước: tên phép đo, loại phép đo, ý nghĩa số liệu, tập nhãn và cách đọc trạng thái. Một binder tốt giúp các ứng dụng dùng cùng một ngôn ngữ giám sát.

Trong bài này, ta xây dựng một binder có thể dùng cho nhiều hàng đợi có giới hạn sức chứa, chạy thử bằng Micrometer thuần Java, rồi khai báo nó thành bean để Spring Boot Actuator tích hợp.

## 2. MeterBinder nằm ở đâu trong hệ thống metrics?

Hợp đồng cốt lõi có dạng:

```java
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
```

Đây là trích đoạn mô tả giao diện; khi viết mã, import `io.micrometer.core.instrument.binder.MeterBinder` từ Micrometer, không tự tạo một giao diện cùng tên.

`bindTo` nhận registry đích và đăng ký các phép đo vào đó. Từ đây, cần phân biệt bốn trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Đối tượng nghiệp vụ được quan sát | Chứa trạng thái hoặc cung cấp số liệu cần đo |
| MeterBinder | Mô tả và đăng ký một bộ phép đo cho đối tượng đó |
| MeterRegistry | Quản lý các phép đo đã đăng ký |
| Registry xuất số liệu và hệ thống giám sát | Đưa số liệu ra ngoài, lưu trữ, truy vấn hoặc cảnh báo tùy cấu hình |

Luồng khái niệm:

```text
Hàng đợi được ứng dụng sử dụng
            |
            v
WorkQueueMetrics giữ tham chiếu và quy ước bộ phép đo
            |
            | bindTo(registry)
            v
MeterRegistry có các Gauge đọc hàng đợi
            |
            v
Đọc tại chỗ hoặc xuất qua cơ chế giám sát đã cấu hình
```

Binder **không phải một loại phép đo mới**. Bên trong nó có thể đăng ký Gauge, Counter, Timer hoặc các loại phù hợp khác.

Trước khi viết binder riêng, kiểm tra xem công nghệ đang dùng đã có phép đo tích hợp sẵn hay chưa. Boot có thể cấu hình sẵn metrics cho JVM, máy chủ web hoặc các thư viện được hỗ trợ. Đăng ký thêm cùng một bộ số liệu mà không kiểm tra định danh có thể tạo xung đột hoặc hai cách đo gây nhầm lẫn.

Nó cũng không tự chạy công việc nghiệp vụ. Đăng ký một Counter trong binder không tự làm Counter tăng khi có request; đăng ký một Timer không tự bao quanh phương thức xử lý. Phải có đường ghi nhận sự kiện/thời gian tương ứng. Với Gauge trong ví dụ này, việc đọc lại trạng thái sẵn có của hàng đợi đã đủ để lấy số liệu hiện tại.

## 3. Chốt hợp đồng của bộ phép đo trước khi viết binder

Ta chọn hai Gauge:

| Tên đăng ký | Nhãn | Ý nghĩa |
| --- | --- | --- |
| `demo.work.queue.depth` | `queue=thumbnail` hoặc `queue=index` | Số tác vụ hiện đang nằm trong hàng đợi |
| `demo.work.queue.remaining` | Cùng khóa nhãn `queue` | Số vị trí còn có thể nhận thêm tác vụ |

Ví dụ `demo.work.queue.depth{queue=thumbnail}=2` nghĩa là có hai tác vụ đang chờ trong hàng đợi tạo ảnh thu nhỏ. Nó không có nghĩa đã xử lý hai tác vụ hay có hai tác vụ đang chạy.

Hai tên cố định biểu đạt hai đại lượng. Giá trị tag phân biệt các hàng đợi. Cách này giúp một bộ biểu đồ có thể lọc hoặc nhóm theo `queue`, thay vì phải biết một tên phép đo riêng cho từng hàng đợi.

Chỉ dùng các giá trị nhãn do cấu hình ứng dụng kiểm soát. Không dùng ID của từng tác vụ, URL tùy ý hoặc tên tệp ảnh làm tag. Số tổ hợp nhãn càng lớn thì càng có nhiều chuỗi số liệu phải quản lý. Xem [quy ước tên và tag của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Bộ phép đo này dành cho hàng đợi có giới hạn sức chứa, chẳng hạn `ArrayBlockingQueue`. Với hàng đợi không có giới hạn thực tế, số `remainingCapacity()` có thể không mang ý nghĩa vận hành mong muốn; không tái sử dụng tên và mô tả một cách máy móc.

## 4. Viết binder độc lập với Spring

Tệp `src/example/binder/WorkQueueMetrics.java`:

```java
package example.binder;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

public final class WorkQueueMetrics implements MeterBinder {

    private final BlockingQueue<?> queue;
    private final Tags tags;

    public WorkQueueMetrics(BlockingQueue<?> queue, String queueName) {
        this.queue = Objects.requireNonNull(queue, "queue");
        String name = Objects.requireNonNull(queueName, "queueName").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("queueName must not be blank");
        }
        this.tags = Tags.of("queue", name);
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Objects.requireNonNull(registry, "registry");

        Gauge.builder("demo.work.queue.depth", this.queue, BlockingQueue::size)
                .tags(this.tags)
                .description("Số tác vụ đang chờ trong hàng đợi")
                .register(registry);

        Gauge.builder("demo.work.queue.remaining",
                        this.queue, BlockingQueue::remainingCapacity)
                .tags(this.tags)
                .description("Số vị trí còn trống trong hàng đợi")
                .register(registry);
    }
}
```

Thiết kế này có một số điểm đáng chú ý.

**Constructor nhận nguồn và cấu hình, chưa đăng ký phép đo.** Vì vậy có thể tạo binder trước khi chọn registry và kiểm tra đầu vào ngay tại nơi cấu hình.

**bindTo chỉ dùng registry được truyền vào.** Không tạo registry riêng và không dùng registry tĩnh toàn cục. Ứng dụng tích hợp quyết định nơi tiếp nhận phép đo.

**Một lần gọi đăng ký cả bộ phép đo.** Tên và tag không bị quyết định rải rác ở các dịch vụ dùng hàng đợi.

Các lệnh đăng ký bên trong không tạo thành một giao dịch tự rollback. Nếu một lệnh sau gặp xung đột loại phép đo hoặc lỗi cấu hình, những phép đo trước đó có thể đã được đăng ký. Vì vậy, kiểm tra đủ cả bộ sau khi tích hợp và không nuốt lỗi đăng ký rồi coi binder đã hoạt động đầy đủ.

**Lớp không phụ thuộc Spring.** Nó có thể nằm trong một thư viện Java dùng chung, được kiểm thử độc lập và được tích hợp bằng Spring hoặc gọi trực tiếp.

**Mỗi binder gắn với một nguồn cụ thể.** Tạo thêm binder cho hàng đợi khác và dùng giá trị `queue` khác. Không thay đổi trường nguồn sau khi đã đăng ký.

### Vì sao giữ hàng đợi trong một trường?

Với dạng Gauge nhận đối tượng và hàm đọc ở trên, Micrometer mặc định giữ tham chiếu yếu đến đối tượng được quan sát. Trường `queue` của binder giữ một tham chiếu mạnh. Trong ứng dụng Spring, bean binder và bean hàng đợi có vòng đời rõ ràng.

Ở chương trình Java thuần, bản thân binder hoặc thành phần nghiệp vụ vẫn phải được giữ sống trong thời gian đo. Chỉ gọi `new WorkQueueMetrics(...).bindTo(registry)` rồi bỏ mọi tham chiếu đến cả binder lẫn nguồn không bảo đảm nguồn còn tồn tại. Hành vi này được giải thích trong [tài liệu Gauge](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

Hàm đọc sử dụng tham số đối tượng mà Micrometer truyền vào qua method reference. Nó không lấy tác vụ khỏi hàng đợi, không gọi mạng và không tạo thêm một biến đếm phải đồng bộ với hàng đợi.

## 5. Chạy thử mà không cần Spring Boot

### 5.1. Chương trình sử dụng hai hàng đợi và hai registry

Tệp `src/example/binder/MeterBinderDemo.java`:

```java
package example.binder;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class MeterBinderDemo {

    public static void main(String[] args) {
        BlockingQueue<String> thumbnailQueue = new ArrayBlockingQueue<>(4);
        BlockingQueue<String> indexQueue = new ArrayBlockingQueue<>(2);

        WorkQueueMetrics thumbnailMetrics =
                new WorkQueueMetrics(thumbnailQueue, "thumbnail");
        WorkQueueMetrics indexMetrics =
                new WorkQueueMetrics(indexQueue, "index");

        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();

        try {
            thumbnailMetrics.bindTo(first);
            indexMetrics.bindTo(first);

            thumbnailQueue.add("image-A");
            thumbnailQueue.add("image-B");

            System.out.println("meters=" + first.getMeters().size());
            System.out.println("thumbnail.depth="
                    + value(first, "demo.work.queue.depth", "thumbnail"));
            System.out.println("thumbnail.remaining="
                    + value(first, "demo.work.queue.remaining", "thumbnail"));
            System.out.println("index.depth="
                    + value(first, "demo.work.queue.depth", "index"));
            System.out.println("index.remaining="
                    + value(first, "demo.work.queue.remaining", "index"));

            thumbnailMetrics.bindTo(first);
            System.out.println("meters-after-rebind=" + first.getMeters().size());

            thumbnailMetrics.bindTo(second);
            System.out.println("second-registry-meters="
                    + second.getMeters().size());

            thumbnailQueue.remove();

            System.out.println("first-registry-thumbnail.depth="
                    + value(first, "demo.work.queue.depth", "thumbnail"));
            System.out.println("second-registry-thumbnail.depth="
                    + value(second, "demo.work.queue.depth", "thumbnail"));
        } finally {
            second.close();
            first.close();
        }
    }

    private static double value(MeterRegistry registry,
                                String name,
                                String queueName) {
        return registry.get(name)
                .tag("queue", queueName)
                .gauge()
                .value();
    }
}
```

Đây là chương trình chạy đầy đủ khi đi cùng lớp ở mục 4. `SimpleMeterRegistry` giúp quan sát các phép đo trong bộ nhớ mà không cần Prometheus hay một máy chủ giám sát.

### 5.2. Dependency và lệnh chạy

Tạo `pom.xml` ở thư mục gốc của thí nghiệm:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-binder-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Ví dụ độc lập này cần JDK 17+ và Maven. Lần đầu tải dependency cần kết nối tới Maven Central. Chạy từ thư mục chứa `pom.xml`.

PowerShell trên Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/binder/WorkQueueMetrics.java src/example/binder/MeterBinderDemo.java
java -cp "out;lib/*" example.binder.MeterBinderDemo
```

Trên Linux/macOS, hai lệnh đầu tương tự, còn lệnh Java dùng dấu `:` để phân cách classpath:

```bash
java -cp "out:lib/*" example.binder.MeterBinderDemo
```

Stdout của chương trình chạy tuần tự:

```text
meters=4
thumbnail.depth=2.0
thumbnail.remaining=2.0
index.depth=0.0
index.remaining=2.0
meters-after-rebind=4
second-registry-meters=2
first-registry-thumbnail.depth=1.0
second-registry-thumbnail.depth=1.0
```

Có bốn phép đo trong registry thứ nhất: hai tên nhân với hai giá trị tag. Registry thứ hai chỉ được gắn binder của hàng đợi `thumbnail`, nên có hai phép đo.

Sau khi lấy một tác vụ ra, cả hai registry đều đọc `1.0` từ cùng hàng đợi. Hai registry không tạo hai hàng đợi và cũng không chia đôi số liệu của nguồn.

Các số đếm trên chỉ đúng cho registry mới tạo trong chương trình, không có bộ lọc hay binder khác. Registry của một ứng dụng Boot thực tế còn có nhiều phép đo được cấu hình tự động.

## 6. Để Spring Boot tự gắn binder

Trong ứng dụng Boot 3.3 có `spring-boot-starter-actuator` và auto-configuration metrics hoạt động, khai báo các binder thành bean. Hãy để dependency management của Boot quản lý phiên bản Micrometer; không áp đặt phiên bản trong thí nghiệm độc lập lên ứng dụng hiện có.

Tệp `QueueMetricsConfiguration.java`, dùng cùng lớp `WorkQueueMetrics` ở mục 4:

```java
package example.binder;

import io.micrometer.core.instrument.binder.MeterBinder;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

@Configuration(proxyBeanMethods = false)
public class QueueMetricsConfiguration {

    @Bean
    public BlockingQueue<String> thumbnailQueue() {
        return new ArrayBlockingQueue<>(100);
    }

    @Bean
    public BlockingQueue<String> indexQueue() {
        return new ArrayBlockingQueue<>(50);
    }

    @Bean
    public MeterBinder thumbnailQueueMetrics(
            @Qualifier("thumbnailQueue") BlockingQueue<String> queue) {
        return new WorkQueueMetrics(queue, "thumbnail");
    }

    @Bean
    public MeterBinder indexQueueMetrics(
            @Qualifier("indexQueue") BlockingQueue<String> queue) {
        return new WorkQueueMetrics(queue, "index");
    }
}
```

Đây là cấu hình tích hợp vào một ứng dụng Boot sẵn có, không phải một lớp `main` độc lập. Package này phải được quét hoặc cấu hình phải được import vào ứng dụng.

Luồng tích hợp là:

1. Spring tạo các bean hàng đợi.
2. Các phương thức `@Bean` tạo binder với đúng nguồn cần đo.
3. Cơ chế metrics auto-configuration của Boot phát hiện các bean `MeterBinder` và gắn chúng vào registry phù hợp do Spring quản lý.
4. Nghiệp vụ dùng các bean hàng đợi đó. Khi số tác vụ thay đổi, Gauge đọc được trạng thái mới.

`@Qualifier` phân biệt hai bean có cùng kiểu. Nếu bỏ nó và không có cơ chế lựa chọn bean phù hợp khác, việc inject nguồn có thể bị mơ hồ hoặc chọn khác với ý định thiết kế.

Theo [tài liệu đăng ký metrics tùy chỉnh của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom), các bean MeterBinder được tự động gắn với registry do Spring quản lý.

**Không thêm một lệnh bindTo thủ công trong @Bean hoặc @PostConstruct khi đã dùng đường tự động này.** Cũng không cần inject `MeterRegistry` vào constructor của binder để thực hiện đăng ký sớm.

Trong chương trình Java thuần ở mục 5, ta tự gọi `bindTo` vì không có Boot điều phối. Chỉ đưa một đối tượng vào Spring container thông thường, khi thiếu auto-configuration metrics hoặc cơ chế gọi binder tương đương, cũng chưa đủ để tự đăng ký phép đo.

### Kiểm tra qua Actuator

Với một ứng dụng đã có web runtime, cổng mặc định 8080 và đường dẫn Actuator mặc định, cấu hình thực hành có thể mở endpoint cần đọc:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Đọc từng phép đo theo tag:

```bash
curl "http://localhost:8080/actuator/metrics/demo.work.queue.depth?tag=queue:thumbnail"
curl "http://localhost:8080/actuator/metrics/demo.work.queue.remaining?tag=queue:thumbnail"
```

Ngay sau khởi động, nếu chưa có tác vụ được đưa vào hàng đợi `thumbnail`, phần `measurements` của hai phản hồi tương ứng cho giá trị `0.0` và `100.0`.

Đây là các giá trị kỳ vọng theo cấu hình và trạng thái đã nêu, không phải kết quả cố định trong mọi lúc chạy. Nếu có xác thực, cổng quản trị hoặc đường dẫn riêng, yêu cầu phải theo cấu hình ứng dụng.

Endpoint `metrics` dùng tên đã đăng ký trong mã. Nếu bỏ tag và có nhiều hàng đợi, các số liệu phù hợp có thể được cộng lại; hãy lọc tag khi kiểm tra một nguồn cụ thể. Xem [hợp đồng metrics endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 7. Phân biệt binder, customizer và filter

Ba cơ chế thường cùng xuất hiện nhưng giải quyết các việc khác nhau:

| Cơ chế | Việc phù hợp |
| --- | --- |
| `MeterBinder` | Đăng ký bộ Gauge của một hàng đợi, một cache hoặc một pool |
| `MeterRegistryCustomizer` | Cấu hình registry, chẳng hạn gắn nhãn môi trường chung |
| `MeterFilter` | Chấp nhận/từ chối hoặc biến đổi định danh, cấu hình của phép đo khi đăng ký |

Trong ví dụ, `queue=thumbnail` mô tả **nguồn được đo**, nên thuộc cấu hình của binder. Nhãn chung như môi trường triển khai có thể thuộc cấu hình registry.

Nếu dùng customizer hoặc filter, thiết lập chúng theo vòng đời Boot hỗ trợ để có tác dụng khi binder đăng ký phép đo. Không dùng binder để âm thầm cấu hình lại cả registry dùng chung.

[Mã MeterRegistryPostProcessor của Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java) cho thấy Boot áp dụng cấu hình registry trước bước gắn binder và có xử lý riêng cho composite registry. Vì vậy, không nên suy đoán rằng mỗi registry con luôn nhận một lần gọi trực tiếp từ ứng dụng.

## 8. Tái sử dụng mà vẫn giữ đúng định danh và vòng đời

### 8.1. Một đối tượng binder có thể được gắn vào nhiều registry

Ví dụ mục 5 chủ động gắn `thumbnailMetrics` vào hai registry. `bindTo` sử dụng tham số nhận được và không cất một registry toàn cục trong binder.

Không thêm cờ toàn đối tượng như:

```java
// Minh họa một thiết kế có lỗi khi cần dùng nhiều registry:
if (bound) {
    return;
}
bound = true;
```

Cờ đó có thể ngăn registry thứ hai nhận phép đo. Nếu một binder thực sự cần theo dõi các lần đăng ký để quản lý tài nguyên, trạng thái phải được thiết kế theo từng registry và phải an toàn đồng thời. Không dùng một cờ để thay cho việc xác định vòng đời.

Binder trong bài chỉ đọc trạng thái, không khởi động luồng nền hay đăng ký listener, nên không cần trạng thái phụ kiểu này.

### 8.2. Đăng ký lặp không phải cơ chế thay nguồn

Trong registry mặc định của thí nghiệm, gọi lại cùng binder với cùng nguồn, tên và tag không tạo thêm các Gauge mới. Đó là lý do `meters-after-rebind` vẫn bằng 4.

Kết quả ấy không có nghĩa có thể tạo một hàng đợi mới, dùng cùng `queue=thumbnail` rồi trông chờ Gauge đổi sang đo nguồn mới. Cùng định danh có thể khiến registry tiếp tục dùng Gauge đã tồn tại.

Hai binder quan sát hai nguồn khác nhau phải có định danh phân biệt. Nếu hai nguồn đều dùng cùng tên và tag, chúng xung đột dù lớp binder hoàn toàn giống nhau và mã vẫn biên dịch.

Các cơ chế lọc/đổi tên cũng có thể làm những định danh ban đầu khác nhau trở nên trùng nhau. Khi chẩn đoán, kiểm tra cả cấu hình registry.

### 8.3. MeterBinder không có hợp đồng unbind tự động

Giao diện này chỉ có phương thức `bindTo`. Nó không quy định rằng khi một đối tượng binder không còn được tham chiếu thì các phép đo sẽ tự được gỡ.

Ví dụ dùng nguồn sống cùng ứng dụng. Khi registry của ứng dụng được đóng, vòng đời tổng thể kết thúc theo cách quản lý của ứng dụng.

Với hàng đợi được tạo/hủy trong lúc chạy, cần thiết kế thành phần quản lý riêng: xác định nơi giữ nguồn, lưu những phép đo đã đăng ký theo từng registry và gỡ đúng phép đo khi thôi quan sát. Nếu có listener hoặc luồng nền phục vụ đo lường, cũng phải dọn chúng theo vòng đời thích hợp. Không đóng registry dùng chung chỉ để dọn một binder.

Không tạo một bean binder cho mỗi request hoặc mỗi tác vụ ngắn hạn. Với nhiều đối tượng tạm thời, thường cần một nguồn thống kê tổng hợp ổn định hơn và một tập nhãn có giới hạn.

### 8.4. Cùng một bộ phép đo cần cùng một ý nghĩa

Khi đưa `WorkQueueMetrics` vào thư viện dùng chung, ứng dụng chỉ cần cung cấp hàng đợi và tên logic; tên phép đo cùng khóa tag được giữ thống nhất.

Nếu sau này đổi `depth` từ “đang chờ” thành “đang chờ cộng đang xử lý” nhưng giữ nguyên tên, biểu đồ và cảnh báo cũ có thể bị hiểu sai. Hãy coi ý nghĩa số liệu là một phần hợp đồng của thư viện.

Với Counter hoặc Timer cần ghi nhận sự kiện, hợp đồng tái sử dụng còn phải chỉ rõ ai gọi `increment` hoặc `record`. Không chỉ đóng gói lệnh tạo đối tượng đo rồi bỏ qua đường ghi nhận.

## 9. Kiểm chứng chất lượng của một binder

Một binder có thể đăng ký thành công nhưng vẫn đo nhầm nguồn. Khi kiểm tra, cần đối chiếu cả cấu trúc lẫn giá trị.

| Điều cần kiểm tra | Cách chứng minh trong ví dụ |
| --- | --- |
| Đủ các phép đo | Mỗi hàng đợi có cả `depth` và `remaining` |
| Đúng tên, loại và nhãn | Tìm đúng Gauge bằng tên và `queue` |
| Đọc trạng thái sống | Thêm/lấy tác vụ rồi đọc lại |
| Các nguồn tách biệt | Thay đổi `thumbnail` không làm hàng đợi `index` đổi |
| Không tăng số mục khi gắn lại cùng nguồn | Đối chiếu `meters-after-rebind` trong registry thử nghiệm |
| Không bỏ qua registry thứ hai | Gắn cùng binder vào registry khác và đọc nguồn |
| Boot tự gắn bean | Kiểm tra trong context có auto-configuration metrics mà không tự gọi `bindTo` |
| Đầu vào hợp lệ | Không chấp nhận nguồn null hoặc tên hàng đợi trắng |

`size()` và `remainingCapacity()` là hai phép đọc riêng biệt. Nếu có luồng khác đang thay đổi hàng đợi, không yêu cầu hai mẫu được lấy ở các thời điểm khác nhau luôn có tổng bằng sức chứa. Chương trình mục 5 chạy tuần tự nên các con số mới khớp chính xác như stdout đã công bố.

Việc dùng cấu trúc dữ liệu an toàn đồng thời cũng không biến cả bộ Gauge thành một ảnh chụp nguyên tử. Nếu nghiệp vụ cần số liệu nhất quán theo một thời điểm, phải thiết kế cơ chế chụp trạng thái phù hợp ngay tại nguồn.

Một số biểu hiện thường gặp:

| Biểu hiện | Kiểm tra |
| --- | --- |
| Có bean binder nhưng không tìm thấy phép đo | Auto-configuration metrics có hoạt động không? Binder có bị filter từ chối không? |
| Phép đo chỉ có trong một registry tự tạo | `bindTo` có bỏ qua tham số và dùng registry khác không? |
| Hai hàng đợi cho cùng số liệu ngoài dự kiến | Có trùng bộ tên/tag hoặc inject nhầm nguồn không? |
| Gauge chuyển thành NaN | Nguồn còn được giữ sống không? Hàm đọc có lỗi không? |
| Registry thứ hai không có bộ phép đo | Có cờ `bound` toàn đối tượng hoặc trạng thái chỉ dành cho registry đầu tiên không? |
| Số chuỗi số liệu tăng theo từng tác vụ | Có đưa định danh tác vụ hay dữ liệu tùy ý vào tag không? |

## 10. Bài thực hành

1. Chạy hai lớp Java ở mục 4–5 và đối chiếu chín dòng stdout.
2. Thêm một tác vụ vào `indexQueue`. Kiểm tra `index.depth=1.0` và `index.remaining=1.0`, trong khi nguồn `thumbnail` giữ trạng thái của nó.
3. Tạo thêm một binder cho hàng đợi `archive` trong registry thử nghiệm. Khi không có filter và dùng tên/tag đúng, tổng số Gauge từ ba hàng đợi là sáu.
4. Trong một thí nghiệm riêng, cố ý dùng cùng giá trị tag cho hai hàng đợi khác nhau. Quan sát nguồn nào được Gauge đọc và giải thích vì sao cần định danh riêng.
5. Tích hợp cấu hình mục 6 vào Boot, xác nhận đủ bốn Gauge mà không thêm lời gọi `bindTo` thủ công. Dùng tag để đọc từng hàng đợi.
6. Trước khi đưa binder vào thư viện dùng chung, viết rõ ý nghĩa từng phép đo, tập nhãn được phép, vòng đời nguồn và cách ứng dụng tích hợp.

Kết quả cần đạt là một bộ phép đo có thể dùng lại với nguồn khác, được đăng ký vào đúng registry và giữ nguyên ý nghĩa số liệu trong các ứng dụng sử dụng nó.
