# Đánh giá thời gian khởi động cùng mức sử dụng bộ nhớ thực tế khi khởi tạo lười Spring Boot

## 1. Mục tiêu: kiểm chứng lazy initialization bằng phép đo, không bằng cảm giác

Trong Spring Boot, **lazy initialization** cho phép trì hoãn việc tạo một số bean cho đến khi bean thật sự được yêu cầu. Với các singleton bean thông thường, cách khởi tạo mặc định là eager: container tạo nhiều bean ngay trong quá trình refresh `ApplicationContext`. Khi bật lazy, một phần việc này có thể chuyển sang lần sử dụng đầu tiên. Điều đó thường giúp **rút ngắn một số mốc startup**, nhưng không tự động làm toàn bộ ứng dụng nhanh hơn hoặc giảm mức sử dụng bộ nhớ sau khi tất cả chức năng đã được sử dụng.

Một đánh giá đúng phải trả lời riêng ít nhất bốn câu hỏi:

1. **Thời gian khởi động:** thời gian từ khi process bắt đầu đến `ApplicationReadyEvent` và đến khi readiness probe thực sự trả về khỏe thay đổi bao nhiêu?
2. **Độ trễ lần sử dụng đầu:** request/job đầu tiên phải khởi tạo bean deferred chậm thêm bao nhiêu, có vượt SLA không?
3. **Bộ nhớ thực tế:** RSS/container memory và JVM heap used tại mốc ready, sau lần sử dụng đầu, và khi hệ thống chạy ổn định thay đổi như thế nào?
4. **Rủi ro vận hành:** lỗi cấu hình trước đây được phát hiện khi khởi động có bị đẩy sang request đầu tiên không; probe/traffic/warm-up có phù hợp không?

**Không kết luận hiệu quả chỉ từ log “Started ... in ... seconds” hay kích thước `-Xmx`.** Thời gian ready, cold request, warm request và memory footprint ở các thời điểm khác nhau là những đại lượng khác nhau.

### Ba giả thuyết nên kiểm định

- H1: `spring.main.lazy-initialization=true` có thể giảm thời gian khởi động đến mốc ready cho cùng một artifact và cấu hình.
- H2: một số lần gọi API đầu tiên tăng latency vì bean/metadata phải được tạo khi request đến.
- H3: memory tại ready có thể thấp hơn, nhưng sau khi toàn bộ đường nghiệp vụ được warm-up, chênh lệch có thể thu hẹp hoặc biến mất; lazy không bảo đảm giảm peak memory.

Kết quả là **đặc thù từng ứng dụng**, phụ thuộc dependency graph, auto-configuration, web framework, tài nguyên khởi tạo, GC, JVM, CPU, traffic và các bean thực sự được gọi. Mọi con số benchmark cần thu từ máy thật chứ không phải số giả định.

## 2. Cơ chế eager và lazy: công việc được chuyển sang đâu?

Một `ApplicationContext` thường khởi tạo singleton không lazy trong quá trình refresh. Với bean lazy, container lưu bean definition và chỉ tạo bean khi có yêu cầu thực sự. Có thể bật lazy toàn cục:

~~~properties
spring.main.lazy-initialization=true
~~~

Hoặc YAML:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Theo mặc định, tùy chọn này là `false`. Cũng có thể cấu hình bằng Java:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setLazyInitialization(true);
app.run(args);
~~~

Đoạn Java là **snippet**, cần class `MyApplication` thích hợp. Không trộn ba cách cấu hình nếu không biết chính xác property source nào quyết định giá trị cuối cùng.

### Đồ thị khởi tạo

~~~mermaid
flowchart TD
  A["SpringApplication.run"] --> B["Tạo ApplicationContext"]
  B --> C["Đăng ký và xử lý BeanDefinition"]
  C --> D{"Bean có eager hoặc bị dependency yêu cầu?"}
  D -->|"Có"| E["Tạo bean trong startup"]
  D -->|"Không"| F["Để lại bean definition, chưa tạo instance"]
  E --> G["ApplicationReadyEvent"]
  F --> G
  G --> H["Request / job đầu tiên"]
  H --> I{"Cần bean deferred?"}
  I -->|"Có"| J["Tạo bean lần đầu, inject, init callback, proxy"]
  I -->|"Không"| K["Dùng các bean đã sẵn sàng"]
  J --> L["Xử lý nghiệp vụ"]
  K --> L
~~~

**Lazy không bảo đảm mọi bean đều chưa được khởi tạo.** Bean lazy được một singleton eager yêu cầu qua constructor trực tiếp có thể vẫn được tạo trong startup để thỏa dependency. Các factory, infrastructure beans, web mappings, BeanFactoryPostProcessor và những thành phần cần thiết khác cũng có thể phải được chuẩn bị sớm.

### Tại sao startup nhanh hơn nhưng request đầu chậm hơn?

Nếu tạo một bean cần 300 ms:
- **Eager:** 300 ms được tính vào startup trước khi ready; request sau đó có thể dùng ngay.
- **Lazy:** 300 ms có thể không xuất hiện trong startup; request đầu tiên chạm bean phải trả chi phí đó.

Đây là **mô hình giải thích**, không phải một số liệu đo được của ứng dụng. Bean cũng có thể tạo dependency chain, kích hoạt class loading, mở pool hoặc compile proxy; do đó chi phí không nhất thiết chỉ nằm ở constructor của một class.

### Lazy làm phát hiện lỗi muộn

Spring Boot tài liệu hóa cảnh báo quan trọng: nếu bean bị cấu hình sai nhưng chưa được tạo, startup có thể vẫn thành công; exception chỉ xuất hiện ở lần sử dụng đầu tiên. Vì vậy một ứng dụng “ready” nhanh hơn chưa chắc đáng triển khai hơn nếu first-hit failure hoặc rollback risk tăng.

Với bean bắt buộc phải kiểm tra trong startup, có thể dùng `@Lazy(false)` trên bean definition phù hợp để giữ khởi tạo sớm ngay cả khi bật lazy toàn cục, hoặc thiết kế một warm-up/validation gate có chủ đích trước readiness. Mọi lựa chọn như vậy đều làm thay đổi kết quả benchmark và phải được ghi lại.

## 3. Phân biệt chính xác các mốc thời gian cần đo

| Chỉ số | Mốc bắt đầu → kết thúc | Ý nghĩa | Cạm bẫy |
| --- | --- | --- | --- |
| `T_process_ready` | Bắt đầu chạy process → readiness probe trả khỏe | Thời gian hệ thống triển khai thực sự thấy instance sẵn sàng | Chịu ảnh hưởng polling interval, HTTP/probe initialization |
| `T_main_ready` | Đầu method `main` → callback `ApplicationReadyEvent` | Thời gian bootstrap bên trong JVM sau khi vào main | Không gồm thời gian JVM khởi tạo trước main; chưa gồm readiness event ngay sau ready |
| `T_first_hit` | Gửi request nghiệp vụ đầu tiên → nhận response | Cold-start latency của một đường dùng bean | Bao gồm network/HTTP, serialization và khởi tạo deferred |
| `T_warm_hit` | Request đã warm → response | Latency khi dependency đã được tạo, JIT/cache có thể đã nóng | Cần đủ request và cùng input |
| `T_workload_ready` | Bắt đầu process → hết warm-up nghiệp vụ định trước | Thời gian đến khả năng phục vụ **toàn bộ tập đường yêu cầu** | Không thể suy từ `ApplicationReadyEvent` một mình |
| `T_startup_variation` | Nhiều process độc lập | Phân bố median/p95 của startup | Một lần chạy thường không đại diện |
| `T_gc_pause` | Khoảng dừng GC trong cùng workload | Đánh giá chi phí GC do heap/allocations | Không được nhầm với toàn bộ startup time |

### Spring Boot StartedEvent khác ReadyEvent

Trong startup thành công điển hình:

~~~mermaid
flowchart LR
  A["JVM/process launch"] --> B["main()"]
  B --> C["ApplicationContext.refresh()"]
  C --> D["ApplicationStartedEvent"]
  D --> E["LivenessState.CORRECT"]
  E --> F["ApplicationRunner / CommandLineRunner"]
  F --> G["ApplicationReadyEvent"]
  G --> H["ReadinessState.ACCEPTING_TRAFFIC"]
  H --> I["Readiness probe / router observes"]
~~~

`ApplicationStartedEvent` phát sau refresh nhưng trước runners. `ApplicationReadyEvent` phát sau runners. Boot công bố readiness `ACCEPTING_TRAFFIC` sau ReadyEvent. Do vậy đo `ApplicationStartedEvent` và gọi đó là thời gian “đã sẵn sàng nhận traffic” có thể sai; đo trong listener `ApplicationReadyEvent` cũng vẫn **hơi sớm** so với việc một hệ thống bên ngoài nhìn thấy readiness probe healthy.

**Khuyến nghị:** lưu ít nhất cả hai số `T_main_ready` và `T_process_ready`. Cả hai hữu ích nếu được định nghĩa nhất quán, nhưng không thay thế nhau.

## 4. Bộ nhớ thực tế: đừng nhầm heap, RSS và giới hạn container

| Thông số | Phản ánh gì | Có phải bộ nhớ thực tế đang resident không? |
| --- | --- | --- |
| `-Xmx` / max heap | Trần heap mà JVM được phép sử dụng | Không: là giới hạn, không phải số byte đã dùng |
| `-Xms` / initial heap | Kích thước heap ban đầu được cấu hình | Không tự đồng nghĩa mọi trang đều resident |
| Heap **used** | Bộ nhớ Java objects đang được tính là sử dụng trong heap | Chỉ là một phần của footprint JVM |
| Heap **committed** | Bộ nhớ JVM đã cam kết dành cho heap | Khác heap used và RSS |
| Non-heap JVM | Metaspace, class metadata, code cache và một số vùng JVM khác | Không phải tất cả đều nằm trong heap |
| Direct/native memory | Direct buffers, thread stacks, native libraries, JVM internals | Có thể tăng RSS dù heap used ổn định |
| Process RSS | Tổng các trang bộ nhớ vật lý resident được quy cho process, bao gồm cả các trang chia sẻ tùy OS | Phù hợp đánh giá footprint process, không tách được độc quyền/shared một cách đơn giản |
| Container memory | Bộ nhớ được cgroup/OS ghi nhận cho container | Có thể gồm page cache và những thành phần khác tùy runtime/cgroup |

**Một bean tạo muộn có thể khiến heap và RSS thấp hơn lúc ready nhưng tăng mạnh ở request đầu tiên.** Vì vậy phải chụp nhiều mốc:

- M0: sau khi JVM/process bắt đầu nhưng trước khi context ready, nếu tooling cho phép;
- M1: **ready, chưa chạm endpoint nghiệp vụ**;
- M2: ngay sau **request đầu tiên** dùng bean deferred;
- M3: sau khi đã warm-up các tuyến nghiệp vụ quan trọng và để GC/traffic ổn định;
- M4: peak trong cửa sổ tải đại diện, bao gồm 10–30 phút hoặc dài hơn nếu workload yêu cầu.

Không có một công thức chung bảo đảm `RSS_lazy < RSS_eager` ở mọi mốc. Thậm chí lazy có thể gây allocation dồn cục, áp lực GC hoặc peak cùng lúc khi traffic đầu tiên đồng thời chạm nhiều bean.

### Về reserved và committed

JVM có thể **reserve** một dải địa chỉ ảo lớn để quản lý heap/class space; con số này không phải số byte physical RAM đang dùng. Nếu dùng Native Memory Tracking, cần phân biệt `reserved` và `committed`; cũng đừng cộng cơ học mọi mục NMT rồi coi là RSS.

### Đo từ bên trong JVM

Có thể quan sát heap used qua MXBean:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

MemoryUsage usage = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage();

long heapUsedBytes = usage.getUsed();
long heapCommittedBytes = usage.getCommitted();
long heapMaxBytes = usage.getMax();
~~~

Đoạn này là snippet đặt trong một method Java, không phải file độc lập. Heap used có thể dao động do GC; số đọc ở một thời điểm không chứng minh một bean đã giải phóng hay gây rò rỉ.

## 5. Thiết kế thí nghiệm A/B công bằng

Để so sánh lazy/eager, hai lần chạy **chỉ khác một biến chủ đích**: `spring.main.lazy-initialization=false` so với `true`. Giữ nguyên:

1. **Artifact:** cùng một JAR và dependencies, không build lại giữa hai chế độ.
2. **JDK/JVM:** cùng vendor, phiên bản Java, flags `-Xms`, `-Xmx`, GC, CPU architecture.
3. **Môi trường:** cùng máy/container limit, số CPU, mức tải background, port/network path.
4. **Cấu hình:** cùng active profiles, external config, logging, database URL, feature flags, secret source.
5. **Workload:** cùng thứ tự URL/HTTP method, kích thước payload, concurrent clients, số lần warm-up và thời gian quan sát.
6. **Cache/JIT:** chạy nhiều process độc lập, xen kẽ hoặc ngẫu nhiên thứ tự A/B; ghi rõ cold filesystem cache hay warm filesystem cache.
7. **Probe:** cùng readiness path/interval, không dùng mốc “listening port” thay cho readiness nếu startup còn tasks.
8. **Quan sát:** cùng cách đo RSS, heap used, latency, percentiles và lỗi, tránh thêm profiler chỉ ở một nhóm.
9. **Tính hợp lệ:** cả hai chế độ đều phải trả kết quả nghiệp vụ đúng; một mode nhanh hơn do bỏ sót khởi tạo bị lỗi **không phải chiến thắng**.
10. **Độ lặp:** chạy tối thiểu nhiều lần độc lập cho mỗi mode (ví dụ 10–20 lượt), trình bày median, khoảng biến thiên và nếu đủ mẫu thì p95.

### Chú ý về CPU và môi trường container

Trong môi trường có CPU quota thấp, việc tạo bean và JIT có thể chịu ảnh hưởng throttling. Cùng một JAR chạy trên laptop nhiều core và pod giới hạn 1 CPU có thể cho kết quả rất khác. Ghi lại `cpu.max`/CPU quota, memory limit, version JVM, GC và số process khác trên node. Không so kết quả môi trường staging với một pod production có workload khác rồi kết luận do lazy.

### Thứ tự chạy

Không nên chạy tất cả eager trước rồi tất cả lazy sau: filesystem cache, background load và nhiệt độ CPU có thể thiên lệch kết quả. Một cách đơn giản là chạy tuần tự **E–L–L–E** nhiều vòng, mỗi lượt là process mới, chờ process trước thoát hoàn toàn rồi mới bắt đầu lượt sau.

Nếu so trong cùng process bằng cách bật/tắt property sau `ApplicationContext.refresh()`, so sánh **không hợp lệ**: lazy initialization được quyết định trong giai đoạn tạo context và bean definitions; chuyển một property runtime không tự “chưa tạo” lại những bean đã có.

## 6. Ví dụ Spring Boot 3.5.x, Java 17+ để đo cả startup và first-hit

Dự án minh họa dùng Spring Boot 3.5.16, Java 17+, Maven, Spring Web và Actuator. Nó có một bean `HeavyCatalog` tốn bộ nhớ và thêm **một khoảng trễ nhân tạo 250 ms** chỉ để tạo hiện tượng dễ quan sát trong phòng học. **Đừng dùng con số này làm benchmark production:** khi đo ứng dụng thật, thay bean giả bằng bean thật và bỏ `Thread.sleep`.

Cấu trúc:

~~~text
lazy-benchmark/
├── pom.xml
└── src/main/
    ├── java/com/example/benchmark/
    │   ├── LazyBenchmarkApplication.java
    │   ├── HeavyCatalog.java
    │   └── WorkController.java
    └── resources/
        └── application.yaml
~~~

### 6.1 File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lazy-benchmark</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

### 6.2 File src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: lazy-benchmark
  main:
    banner-mode: "off"
    # lazy-initialization không đặt cố định: CLI quyết định từng lượt.

server:
  port: 8081

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Đoạn `management.endpoint.health.probes.enabled=true` cho phép dùng readiness endpoint trong thí nghiệm web có Actuator. Port `8081` có thể override bằng `--server.port=...`. Không cần expose toàn bộ các endpoint Actuator công khai chỉ để đo ready.

### 6.3 File src/main/java/com/example/benchmark/LazyBenchmarkApplication.java

~~~java
package com.example.benchmark;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

@SpringBootApplication
public class LazyBenchmarkApplication {

    public static void main(String[] args) {
        long mainStartNanos = System.nanoTime();

        SpringApplication app =
                new SpringApplication(LazyBenchmarkApplication.class);

        // Listener đăng ký trước run; hoạt động dù global lazy=true.
        app.addListeners((ApplicationListener<ApplicationReadyEvent>) event -> {
            long elapsed = System.nanoTime() - mainStartNanos;
            System.out.println("MAIN_TO_READY_MS="
                    + TimeUnit.NANOSECONDS.toMillis(elapsed));
        });

        app.run(args);
    }
}
~~~

**Vì sao dùng `System.nanoTime()`?** Nó phù hợp đo **duration trong cùng JVM**, không phải timestamp lịch. Giá trị `MAIN_TO_READY_MS` không bao gồm phần JVM launcher trước khi `main` bắt đầu và không đo thời gian kubelet nhận probe. Để đo từ bên ngoài process đến readiness, dùng script ở mục 7.

### 6.4 File src/main/java/com/example/benchmark/HeavyCatalog.java

~~~java
package com.example.benchmark;

import java.util.Arrays;

import org.springframework.stereotype.Component;

@Component
public class HeavyCatalog {
    private final byte[] payload = new byte[24 * 1024 * 1024];

    public HeavyCatalog() {
        Arrays.fill(payload, (byte) 7);

        // Chỉ để minh họa chi phí khởi tạo; KHÔNG dùng sleep
        // trong benchmark production.
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", e);
        }

        System.out.println("HEAVY_BEAN_CREATED");
    }

    public String status() {
        return payload[0] == 7 ? "warm" : "invalid";
    }
}
~~~

Bean này giữ một mảng khoảng **24 MiB** trong heap và thực hiện một thao tác fill để các trang bộ nhớ được chạm tới. `Thread.sleep(250)` cho thấy chi phí khởi tạo **có thể** chuyển từ startup sang first request. Sleep không phải CPU workload thực; vì vậy không nên diễn giải benchmark này thành kết quả tương ứng cho một bean database/cache thật.

### 6.5 File src/main/java/com/example/benchmark/WorkController.java

~~~java
package com.example.benchmark;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WorkController {
    private final ObjectProvider<HeavyCatalog> catalogProvider;

    public WorkController(ObjectProvider<HeavyCatalog> catalogProvider) {
        this.catalogProvider = catalogProvider;
    }

    @GetMapping("/status")
    public String status() {
        return "OK";
    }

    @GetMapping("/work")
    public String work() {
        return catalogProvider.getObject().status();
    }
}
~~~

**Chi tiết thiết kế quyết định tính đúng của thí nghiệm:** controller inject `ObjectProvider<HeavyCatalog>`, không inject trực tiếp `HeavyCatalog` qua constructor. Provider **không bắt buộc tạo target ngay khi controller được tạo**. Điều đó giúp chế độ lazy có cơ hội trì hoãn tạo `HeavyCatalog` đến lúc endpoint `/work` gọi `getObject()`.

Với eager mặc định, bean `HeavyCatalog` non-lazy vẫn được pre-instantiate khi context refresh, ngay cả khi controller giữ provider. Khi global lazy=true, bean này không bị một eager dependency trực tiếp buộc tạo sớm, nên thông thường lần gọi `/work` đầu mới tạo nó.

Nếu thay provider bằng:

~~~java
public WorkController(HeavyCatalog catalog) {
    // ...
}
~~~

và controller vẫn eager, dependency có thể kéo `HeavyCatalog` vào startup. Vì thế **luôn kiểm tra log `HEAVY_BEAN_CREATED`** để xác minh bean thực sự được tạo ở phase nào, thay vì tin tuyệt đối vào một cờ cấu hình.

### 6.6 Build và chạy hai chế độ

~~~bash
mvn -q -DskipTests package

# Chế độ A: eager, mặc định của Spring Boot
java -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=false \
  --server.port=8081
~~~

Ở terminal khác, sau khi ứng dụng ready:

~~~bash
curl -i http://127.0.0.1:8081/actuator/health/readiness
curl -fsS http://127.0.0.1:8081/status
curl -fsS http://127.0.0.1:8081/work
~~~

Khi cả hai endpoint hoạt động đúng, hai dòng output response body của business routes tương ứng là:

~~~text
OK
warm
~~~

Dòng `MAIN_TO_READY_MS=...` có số thay đổi theo máy, và `HEAVY_BEAN_CREATED` xuất hiện vào pha startup của chế độ eager. Không có một con số milliseconds cố định nào được bảo đảm.

Dừng hoàn toàn process rồi chạy mode B:

~~~bash
java -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true \
  --server.port=8081
~~~

Ở mode B, trước khi gọi `/work`, chỉ gọi readiness và `/status`; kiểm tra trong log xem `HEAVY_BEAN_CREATED` đã xuất hiện chưa. Trong cấu hình demo bình thường, log này chưa xuất hiện. Gọi `/work` lần đầu mới thấy log; các lần tiếp theo dùng lại singleton.

**Lưu ý:** các lệnh nối dòng bằng dấu `\` dành cho Bash/Unix. Với Windows PowerShell/cmd, dùng lệnh `java -jar ...` trên một dòng hoặc cú pháp nối dòng riêng.

### 6.7 Kỳ vọng kết quả theo phase, không bịa số liệu

| Quan sát | Eager `false` | Lazy `true` |
| --- | --- | --- |
| Bean nặng tạo lúc refresh | Thường có | Thường chưa |
| `HEAVY_BEAN_CREATED` trước ready | Có trong demo | Không trong demo |
| `MAIN_TO_READY_MS` | Bao gồm tạo bean nặng | Có thể không bao gồm |
| Request `/work` đầu | Dùng bean đã tạo | Có thể trả chi phí tạo bean 24 MiB + sleep 250 ms |
| Request `/work` sau | Không tạo lại singleton | Không tạo lại singleton |
| RSS tại ready | Có thể cao hơn | Có thể thấp hơn |
| RSS sau khi dùng `/work` | Có mảng 24 MiB | Cũng có mảng 24 MiB |
| Peak/latency ở tải đồng thời | Phải đo | Phải đo, có thể dồn chi phí cold init |

Các từ “có thể” trong bảng là cố ý. Không hứa chênh lệch RSS đúng 24 MiB hoặc startup nhanh hơn đúng 250 ms: JVM heap allocation, GC, page residency, lazy web initialization, scheduling và probe đều làm kết quả khác mô hình đơn giản.

## 7. Script đo A/B trên Linux bằng Bash, curl và ps

Bên dưới là script **có thể chạy** trong môi trường Linux có Java 17+, Maven, `curl`, GNU `date`, `ps` và Bash. Nó đo một process mới, đợi readiness thật, lấy RSS tại ready, gọi `/work` lần đầu và lần hai, rồi lấy RSS sau request.

**File `measure-one.sh`**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: bash measure-one.sh true|false PORT" >&2
  exit 2
fi

mode="$1"
port="$2"

if [[ "$mode" != "true" && "$mode" != "false" ]]; then
  echo "First argument must be true or false" >&2
  exit 2
fi

jar="target/lazy-benchmark-0.0.1-SNAPSHOT.jar"
log="run-$mode-$port.log"

# Linux/GNU date: nanoseconds since epoch.
start_ns=$(date +%s%N)

java -Xms64m -Xmx256m \
  -jar "$jar" \
  "--spring.main.lazy-initialization=$mode" \
  "--server.port=$port" \
  >"$log" 2>&1 &
pid=$!

cleanup() {
  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0

# 400 lượt * 0.05s: giới hạn kiểm tra khoảng 20s
# chưa bao gồm thời gian mỗi request curl.
for ((i=0; i<400; i++)); do
  if curl -fsS -o /dev/null \
       "http://127.0.0.1:$port/actuator/health/readiness" \
       2>/dev/null; then
    ready=1
    break
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    echo "Process exited before readiness. Inspect $log" >&2
    exit 1
  fi

  sleep 0.05
done

if [[ "$ready" -ne 1 ]]; then
  echo "Readiness timeout. Inspect $log" >&2
  exit 1
fi

ready_ns=$(date +%s%N)
external_ready_ms=$(( (ready_ns - start_ns) / 1000000 ))

rss_ready_kib=$(ps -o rss= -p "$pid" | tr -d ' ')

first_hit_s=$(curl -fsS -o /dev/null \
  -w '%{time_total}' "http://127.0.0.1:$port/work")

second_hit_s=$(curl -fsS -o /dev/null \
  -w '%{time_total}' "http://127.0.0.1:$port/work")

rss_after_work_kib=$(ps -o rss= -p "$pid" | tr -d ' ')

printf 'mode=%s ready_ms=%s rss_ready_kib=%s first_s=%s second_s=%s rss_after_kib=%s\n' \
  "$mode" "$external_ready_ms" "$rss_ready_kib" \
  "$first_hit_s" "$second_hit_s" "$rss_after_work_kib"

# Hai dòng này là tín hiệu quan sát, không phải các số cố định.
grep -E 'MAIN_TO_READY_MS=|HEAVY_BEAN_CREATED' "$log" || true
~~~

**Lưu ý về script:**

- Một lượt = một process mới, tránh so eager và lazy trong cùng JVM.
- Script đặt mốc `start_ns` **trước khi gọi Java process**, nên khác `MAIN_TO_READY_MS` bên trong JVM.
- Kiểm tra readiness bằng status HTTP thành công; nếu endpoint trả lỗi hoặc chưa kết nối được, vòng lặp tiếp tục. Lưu ý mỗi lần poll có chi phí riêng và bản thân health endpoint có thể cần khởi tạo các bean web lazy.
- `ps -o rss=` trả RSS theo **KiB** trên hệ thống Linux thông thường; không coi đó là MB mà chưa đổi đơn vị.
- `curl -w '%{time_total}'` trả giây (có phần thập phân), bao gồm chi phí thiết lập kết nối/HTTP client và server; với localhost giúp giảm nhưng không triệt tiêu nhiễu.
- Script tạo log ở thư mục làm việc và xóa process khi kết thúc, không tự xóa log để có thể đối chiếu.
- Đo **ngay sau** request đầu chưa phải steady-state; để đo M3/M4 cần thêm thời gian warm-up, request load và lấy mẫu theo chu kỳ.

Sau khi build JAR, chạy các lượt theo thứ tự xen kẽ:

~~~bash
bash measure-one.sh false 18081
bash measure-one.sh true 18081
bash measure-one.sh true 18081
bash measure-one.sh false 18081
~~~

Lặp thêm nhiều vòng trên máy ít nhiễu. Vì script dừng process của mỗi lượt trước khi kết thúc, có thể dùng lại port `18081` nếu nó đã được giải phóng. Nếu port chưa giải phóng, script sẽ timeout và cần kiểm tra process cũ; không khởi động hai lần đo trên cùng port cùng lúc.

Đối với số liệu thật, copy những dòng `mode=...` vào CSV/table và phân tích median, min/max và phân phối. **Không dùng riêng lượt đầu tiên** để ra quyết định.

### Mẫu bảng ghi số liệu

| Run | Mode | Main→Ready (ms) | External→Readiness (ms) | RSS ready (MiB) | First `/work` (ms) | Warm p95 (ms) | RSS post-warm (MiB) | GC/Errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | eager | đo | đo | đo | đo | đo | đo | ghi |
| 2 | lazy | đo | đo | đo | đo | đo | đo | ghi |
| 3 | lazy | đo | đo | đo | đo | đo | đo | ghi |
| 4 | eager | đo | đo | đo | đo | đo | đo | ghi |

**Công thức:**

~~~text
startup_reduction_pct =
    100 * (median_ready_eager - median_ready_lazy)
        / median_ready_eager

rss_ready_delta_mib =
    median_rss_lazy_ready_mib - median_rss_eager_ready_mib

cold_penalty_ms =
    median_first_hit_lazy_ms - median_first_hit_eager_ms
~~~

Mọi mẫu số phải khác 0, cùng định nghĩa thời gian và cùng môi trường. Giá trị âm của `startup_reduction_pct` có nghĩa mode lazy chậm hơn trong bộ dữ liệu đó, không phải lỗi công thức.

Để đo p95/p99 warm latency có ý nghĩa, cần **nhiều request** và công cụ load test phù hợp như k6, wrk, Gatling hoặc JMeter; hai request trong script minh họa không đủ để tính percentiles đáng tin.

## 8. Quan sát JVM bằng jcmd, GC và Native Memory Tracking

### jcmd GC.heap_info

Trên máy có JDK tương thích và quyền attach vào process Java:

~~~bash
jcmd "$pid" GC.heap_info
~~~

`$pid` là PID JVM đang chạy, ví dụ lấy từ script hoặc `jps -l`. Lệnh có thể hiển thị các số liệu heap/GC phù hợp JVM/collector. Cách diễn giải khác nhau giữa G1, Parallel, ZGC và các JVM khác; đừng viết parser phụ thuộc một kiểu output mà không ràng buộc collector/version.

### Native Memory Tracking

Để xem thêm các vùng bộ nhớ **ngoài heap**, có thể bật NMT khi **khởi động process**:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -Xms64m -Xmx256m \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

Sau đó chạy trong terminal khác:

~~~bash
jcmd PID VM.native_memory summary
jcmd PID VM.native_memory baseline
# Sau một pha warm-up:
jcmd PID VM.native_memory summary.diff
~~~

Thay `PID` bằng số process thật. Tùy OS/JVM và quyền người dùng, attach có thể bị vô hiệu hóa. NMT ghi nhận các allocation nội bộ HotSpot như Java Heap, Class, Thread, Code, GC và các hạng mục native khác. **NMT không bao phủ toàn bộ allocation của native code ngoài JVM**, và bản thân NMT có overhead; Oracle nêu mức ảnh hưởng hiệu năng đáng kể khi bật theo mức theo dõi. Do đó **không bật NMT cho chỉ một nhánh A/B rồi so startup time**: nếu cần NMT, bật cùng một cấu hình cho cả hai hoặc tách thành phiên đo chẩn đoán.

**Diễn giải đúng:** NMT `reserved` không phải RSS; `committed` không tự bằng heap used. Quan sát NMT cạnh RSS và Java heap metrics để biết chi phí deferred nằm ở allocation Java, class loading, threads hay vùng native.

### GC và allocation

Với Java 17 HotSpot, có thể bật unified logging để quan sát GC:

~~~bash
java -Xms64m -Xmx256m -Xlog:gc*:file=gc.log:time,uptime,level,tags \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

Khi so sánh, giữ cấu hình logging giống nhau ở hai mode. Phân biệt **GC count, pause time, allocation rate và heap live set**. Một ứng dụng tạo ít object lúc startup có thể tạo chúng ồ ạt lúc first traffic; kết quả peak pause/latency có thể kém dù ready nhanh.

### Java Flight Recorder và ApplicationStartup

Spring Framework có `ApplicationStartup` và các `StartupStep` để profile bean/context initialization. Với Spring Boot 3.5.x, có thể cấu hình:

~~~java
SpringApplication app =
        new SpringApplication(LazyBenchmarkApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

Đây là **phương án thay thế** cho đoạn khởi tạo `SpringApplication` trong file main ở mục 6, phải import `org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup`. Nếu muốn giữ `MAIN_TO_READY_MS`, thêm `setApplicationStartup(...)` vào `app` đã có trước `run`, thay vì tạo hai SpringApplication riêng.

Khi có Actuator, endpoint `/actuator/startup` có thể đưa ra các startup steps từ `BufferingApplicationStartup` nếu được cấu hình và được expose. Ví dụ cấu hình **chỉ trên môi trường benchmark được bảo vệ**:

~~~properties
management.endpoints.web.exposure.include=health,startup
~~~

Không vô tình expose thông tin startup/actuator trên public Internet; áp dụng authentication, authorization và network policy phù hợp. Snapshot startup từ endpoint mô tả steps khi context khởi tạo; **nó không đo first-hit của bean deferred nếu các steps đó xảy ra sau startup ngoài vùng ghi nhận**. Để phân tích cả deferred initialization và JVM allocations, có thể dùng JDK Flight Recorder và/hoặc profiler ở khoảng sau first request.

Một cách bổ sung là thay implementation bằng `FlightRecorderApplicationStartup` rồi chạy JFR:

~~~bash
java -XX:StartFlightRecording=filename=lazy-startup.jfr,duration=30s \
  -jar target/lazy-benchmark-0.0.1-SNAPSHOT.jar \
  --spring.main.lazy-initialization=true
~~~

Cần cấu hình `FlightRecorderApplicationStartup` vào `SpringApplication` thì JFR mới ghi được các startup steps tương ứng của Spring; cờ `StartFlightRecording` một mình chỉ bật JFR cho các event JVM được cấu hình. Không dùng profiler làm phép đo baseline nếu profiler gây overhead không đối xứng giữa hai chế độ.

## 9. Đánh giá first-hit latency và tải đồng thời

Một lỗi đánh giá thường gặp là kết luận “lazy tốt hơn vì startup nhanh hơn 20%” mà không đo request đầu tiên hoặc burst traffic ngay sau deploy.

### First-hit không phải warm latency

Phân biệt:
- **Cold process:** JVM mới khởi động, bean/context/class loading có thể chưa đầy đủ.
- **First functional request:** request đầu tới một đường nghiệp vụ nhất định, có thể kéo thêm dependency chain chưa được tạo.
- **Warm requests:** những request sau khi bean, connection pool, JIT và cache đã được khởi tạo ở mức đại diện.
- **Concurrent cold burst:** nhiều request đầu cùng cần một lazy singleton hoặc nhiều bean khác nhau; có thể gây contention và các tail latency cao.

`HeavyCatalog` trong demo là singleton nên chỉ có một instance, nhưng yêu cầu đồng thời vẫn có thể phải chờ quá trình khởi tạo bean lần đầu. Không lấy `T_first_hit` của một client tuần tự thay cho p99 trong burst đa client.

### Đánh giá chức năng nào cần warm trước traffic?

Hãy lập danh sách các đường nghiệp vụ **critical path**, ví dụ:
- health/readiness endpoint;
- login/session validation;
- thao tác đọc/ghi cơ sở dữ liệu chủ lực;
- các endpoint phục vụ tỉ lệ lớn traffic;
- consumer nhận message và scheduler;
- mã xác thực, serialization hoặc remote client có khởi tạo đặc biệt.

Chạy warm-up có kiểm soát trước khi mở route, nhưng phải hiểu **warm-up chính là chuyển một phần chi phí về trước readiness**. Nó có thể là lựa chọn đúng nếu mục tiêu ưu tiên là p95/p99 ổn định hơn là thời gian ready ngắn nhất.

### Không dùng request warm-up làm thay đổi dữ liệu thật

Một endpoint gọi để warm có thể ghi DB, phát event hoặc kích hoạt job, gây side effects. Dùng endpoint idempotent/an toàn, môi trường thử nghiệm hoặc một API warm-up nội bộ với quyền truy cập giới hạn. Không tùy tiện gọi endpoint nghiệp vụ có tác dụng phụ trên production chỉ để đo hiệu năng.

## 10. Các sai lệch dễ làm kết quả vô nghĩa

### Chỉ đo một lượt

JIT, filesystem cache, GC, CPU scheduling và class loading thay đổi theo lượt. Một lượt không cho biết phân bố. Chạy nhiều process xen kẽ, lưu log và điều kiện máy.

### So RSS lazy ở ready với RSS eager sau khi đã xử lý traffic

Đó là hai điểm tải khác nhau. So đúng pha M1 với M1, M3 với M3. Nếu lazy chỉ chưa tạo bean, RSS sớm thấp là **chi phí bị hoãn**, không phải đã biến mất.

### Nhầm -Xmx thấp với sử dụng RAM thấp

`-Xmx` là trần Java heap. Đặt `-Xmx256m` không có nghĩa process chỉ dùng 256 MiB RSS; ngoài heap còn metaspace, thread stacks, code cache, direct buffers và các phần OS/runtime khác.

### Tính latency từ logging không cùng mốc

Một bản log `Started ... in ...` có thể đo theo logic của Spring và không bao gồm chờ readiness probe bên ngoài. Dùng đồng hồ monotonic bên trong và external stopwatch riêng, luôn ghi rõ mốc bắt đầu/kết thúc.

### Quên rằng lazy có thể kéo bean lỗi sang runtime

Trong eager mode, cấu hình sai của một bean thiết yếu có thể fail startup. Trong lazy mode, lần đầu một endpoint chạm bean mới fail với exception. Trước khi triển khai, đưa startup validation bắt buộc vào một đường eager/warm-up phù hợp hoặc dùng `@Lazy(false)` cho bean không được phép phát hiện lỗi trễ.

### Đo memory bằng tổng reserved của NMT

Địa chỉ ảo reserved không đồng nghĩa RAM resident. Dùng RSS/container memory, heap used và committed để hiểu nhiều lớp chi phí, không gộp sai đơn vị.

### Bỏ qua warm-up và GC

Sau lần đầu gọi endpoint, heap used có thể tạm cao do object ngắn hạn chưa được collect. Chụp cùng loại mốc và quan sát qua nhiều chu kỳ GC, không kích hoạt full GC tùy ý chỉ để có con số “đẹp” (vì thay đổi điều kiện phép đo).

### Thay đổi nhiều cấu hình cùng lúc

Nếu bật lazy đồng thời đổi `-Xmx`, GC, logging và thread pool, không biết yếu tố nào gây kết quả. Chia thí nghiệm thành hai pha: (1) cô lập ảnh hưởng lazy, (2) sau đó mới tune JVM hoặc application policies một cách riêng.

### Dùng startup readiness làm đại diện throughput

Một process đến trạng thái ready nhanh không đồng nghĩa throughput tốt hơn. Đo thêm request rate, error rate, p50/p95/p99, CPU, GC, RSS peak và hoạt động của các upstream dependency dưới tải chuẩn.

## 11. Kiến trúc triển khai: bật toàn cục, bật chọn lọc hay không bật?

| Cách làm | Lợi ích tiềm năng | Hạn chế | Khi nên cân nhắc |
| --- | --- | --- | --- |
| Eager mặc định | Phát hiện sớm lỗi cấu hình/DI; first-hit ổn định hơn | Startup có thể chậm và RSS ready cao | Hệ thống có yêu cầu correctness/latency chặt |
| Global lazy `true` | Có thể giảm thời gian ready và RSS tại mốc sớm | Lỗi và chi phí khởi tạo bị đẩy sang runtime | Service nhiều bean ít dùng, cold-hit có thể chịu được |
| `@Lazy` chọn lọc | Hoãn riêng bean hiếm dùng, dễ định mức rủi ro | Cần hiểu dependency graph; eager dependency có thể kéo bean | Một vài bean nặng, không thuộc đường nóng |
| Global lazy + `@Lazy(false)` cho bean quan trọng | Giữ một số validation/critical path eager | Startup tiết kiệm ít hơn global lazy toàn phần | Cần phân loại rõ bean thiết yếu |
| Lazy + warm-up trước readiness | Có thể tránh cold-hit cho đường chính | Warm-up trả chi phí về startup, cần kiểm soát side effects | SLA first request quan trọng |
| Tối ưu bean thật (I/O, scans, classpath, pools) | Có thể cải thiện cả startup và runtime | Cần profiling/engineering effort | Chỉ rõ chi phí từ JFR/ApplicationStartup |

**Lựa chọn cuối cùng phải dựa trên mục tiêu triển khai**, không phải một cấu hình được gọi là tối ưu trong mọi trường hợp.

### Khi cần rollback

Nếu lazy làm tăng cold-hit p99 hoặc runtime errors, phải có cách rollback property về `false`, restart theo chính sách phù hợp, và kiểm tra readiness của instance mới. Vì đây là tùy chọn startup, thay đổi property trong một context đã refresh không tự tái tạo bean graph theo mode mới.

## 12. Báo cáo benchmark nên trông thế nào?

Một báo cáo đủ để quyết định cần có:

**Thông tin môi trường:** commit/artifact hash, Spring Boot version, JDK vendor/version, JVM flags, active profile, CPU quota, memory limit, machine type, OS, số replica, workload spec.

**Số liệu startup:** median/p95 của `T_main_ready` và `T_process_ready` từ nhiều lần chạy độc lập. Ghi rõ cách bắt sự kiện, vòng polling và độ phân giải đo.

**Số liệu latency:** first-hit cho các critical endpoints; warm latency p50/p95/p99 dưới concurrency đại diện, error rate và timeout.

**Bộ nhớ:** RSS tại ready, sau warm-up và peak; JVM heap used/committed, direct/native khi có; memory limit và OOM events.

**Độ tin cậy:** exception trong startup, lỗi chỉ xuất hiện ở request đầu, probe failures và trạng thái rollout.

**Kết luận:** chi phí/được lợi có đủ lớn và ổn định để đáp ứng SLO không; có cần `@Lazy(false)`, warm-up hay chỉ lazy chọn lọc không.

Mẫu kết luận (không điền số khi chưa đo):

~~~text
Artifact: <commit / digest>
JDK / Boot / GC / CPU quota: <recorded configuration>
Comparison: eager(false) vs lazy(true), same JAR and workload
Independent runs per variant: <N>
Median main-to-ready: eager <ms>; lazy <ms>
Median external readiness: eager <ms>; lazy <ms>
First-hit p95 /work: eager <ms>; lazy <ms>
Warm p95 /work: eager <ms>; lazy <ms>
RSS ready: eager <MiB>; lazy <MiB>
RSS after warm-up: eager <MiB>; lazy <MiB>
Peak container memory: eager <MiB>; lazy <MiB>
Startup errors / first-hit errors: <counts>
Decision: <enable / selective / keep eager>
Reason: <SLOs, risks, representative evidence>
~~~

Các dấu ngoặc nhọn ở đây là **nhãn trường của mẫu báo cáo**, không phải số liệu thực. Khi báo cáo một hệ thống thật, điền bằng dữ liệu đo có thể kiểm chứng.

## 13. Câu hỏi tự kiểm tra

**1. Bật lazy=true có bảo đảm tất cả bean đều được tạo sau ready không?**  
Không. Các bean infrastructure, bean được yêu cầu bởi dependency eager, và nhiều bean phục vụ startup vẫn có thể được tạo sớm.

**2. Tại sao ready nhanh hơn nhưng first request có thể chậm hơn?**  
Vì bean, proxy, class loading và tài nguyên được tạo ở lần dùng đầu thay vì trong startup.

**3. Nếu RSS lazy tại ready thấp hơn 30 MiB, có thể kết luận tiết kiệm 30 MiB trong suốt đời ứng dụng không?**  
Không. Cần đo sau khi workload đã dùng các bean deferred và tại peak; RSS không chỉ là heap.

**4. `-Xmx` là phép đo RAM resident phải không?**  
Không. Nó là giới hạn tối đa của Java heap, không phải RSS.

**5. Vì sao không chỉ dùng thời gian `ApplicationStartedEvent`?**  
Vì event này phát trước runners và readiness accepting; có thể chưa sẵn sàng nhận traffic.

**6. Muốn đo từ lúc tiến trình được gọi đến lúc readiness probe khỏe, nên dùng đồng hồ ở đâu?**  
Từ bên ngoài JVM, bắt đầu trước lệnh Java, dừng khi probe thành công, ghi rõ polling/HTTP overhead.

**7. Trong ví dụ, vì sao controller dùng `ObjectProvider<HeavyCatalog>`?**  
Để controller không buộc resolve target ngay khi được tạo; lần `getObject()` ở `/work` là nơi bean deferred có thể được yêu cầu.

**8. Nếu dùng `@Lazy(false)` trong global lazy, điều gì xảy ra?**  
Bean được đánh dấu có thể được giữ eager để khởi tạo/validate sớm; phải kiểm tra dependency graph thật.

**9. Có nên bật NMT chỉ trên nhánh lazy rồi so startup với eager không?**  
Không. NMT có overhead và làm mất tính tương đương A/B.

**10. Vì sao cần đo heap used, RSS và container memory riêng?**  
Chúng đo các lớp khác nhau; JVM có chi phí non-heap/native và container có cách accounting riêng.

**11. Khi lazy che một misconfigured bean tới request đầu tiên, nên xử lý thế nào?**  
Giữ validation/bean thiết yếu eager hoặc warm-up có kiểm soát trước nhận traffic; không coi startup success là bằng chứng chức năng đúng.

**12. Muốn quyết định bật lazy trong production, cần thêm số liệu nào ngoài startup median?**  
First-hit p95/p99, warm latency, errors, RSS/heap post-warm, peak memory, GC và behavior readiness/rollout.

## 14. Tài liệu chính thức để đối chiếu

- [Spring Boot 3.5 — SpringApplication: Lazy Initialization](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): property, API enable/disable và cảnh báo startup/memory/late errors.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): bean creation theo yêu cầu, lazy singleton và quan hệ với dependency eager.
- [Spring Boot 3.5 — Application Startup Tracking](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `ApplicationStartup`, `BufferingApplicationStartup` và JFR.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): health/readiness endpoints và startup endpoint.
- [Spring Boot — Actuator Startup REST API](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html): snapshot/drain startup steps.
- [Oracle JDK 17 — jcmd Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.native_memory` và JVM diagnostics.
- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): phạm vi NMT, reserved/committed và overhead.
- [Oracle JDK 17 — java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xms`, `-Xmx` và JVM diagnostic flags.

**Kết luận kỹ thuật:** đánh giá lazy initialization không phải cuộc thi đo một con số startup. Chỉ nên bật lazy khi mức giảm thời gian ready/bộ nhớ **được đo ở đúng pha** có giá trị hơn chi phí cold-hit và rủi ro lỗi muộn, đồng thời vẫn đáp ứng latency, availability và memory SLO trong tải đại diện.