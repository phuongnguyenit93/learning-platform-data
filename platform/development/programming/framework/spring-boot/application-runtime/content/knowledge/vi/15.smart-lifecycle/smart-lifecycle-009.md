# Thời hạn dừng từng giai đoạn của DefaultLifecycleProcessor trong Spring Boot

## 1. Vì sao shutdown cần một thời hạn cho từng phase?

Một ứng dụng Spring Boot thường có nhiều thành phần hoạt động lâu dài: HTTP server, consumer đọc message, scheduler, streaming processor, connection pool, worker xử lý tác vụ và những thành phần quản lý kết nối tới hệ thống bên ngoài. Khi ứng dụng dừng, chỉ gọi một lệnh "stop tất cả" là chưa đủ.

Giả sử một message consumer đang sử dụng storage client:

1. Khi khởi động, **storage client phải hoạt động trước**.
2. Sau đó consumer mới có thể nhận và xử lý message.
3. Khi dừng, **consumer phải ngừng nhận việc mới trước**.
4. Storage client cần tiếp tục sống để consumer xử lý nốt việc đang chạy.
5. Cuối cùng mới dừng storage client.

Spring Framework cung cấp **Lifecycle**, **SmartLifecycle** và **DefaultLifecycleProcessor** để tổ chức việc start/stop các thành phần này theo **phase**. Với những thành phần dừng bất đồng bộ, Spring cần biết **đợi tối đa bao lâu** trước khi tiếp tục quá trình shutdown.

**Thời hạn dừng từng giai đoạn (timeout per shutdown phase)** là khoảng thời gian tối đa mà DefaultLifecycleProcessor dành để **chờ nhóm SmartLifecycle beans có cùng giá trị phase gọi callback báo đã dừng**. Nó không phải thời hạn của từng bean riêng lẻ, không phải tổng thời gian bắt buộc của toàn bộ JVM và không phải lệnh cưỡng bức dừng thread khi hết hạn.

Câu ghi nhớ:

> **Phase quyết định thứ tự, stop(Runnable) báo hoàn tất, timeout-per-shutdown-phase giới hạn thời gian chờ của một nhóm phase.**

Đây là chủ đề thuộc **Spring Boot Application Runtime → SmartLifecycle**. Spring Boot cấu hình DefaultLifecycleProcessor trong ApplicationContext và có property giúp người vận hành tùy chỉnh giới hạn thời gian cho các phase khi shutdown.

## 2. Các API tham gia

| Thành phần | Trách nhiệm |
| --- | --- |
| **Lifecycle** | Khai báo start(), stop(), isRunning() cho một component |
| **Phased** | Cung cấp getPhase() để biểu thị thứ tự |
| **SmartLifecycle** | Mở rộng Lifecycle và Phased, có isAutoStartup() và stop(Runnable) |
| **LifecycleProcessor** | Điều phối bắt đầu/dừng các Lifecycle beans trong context |
| **DefaultLifecycleProcessor** | Implementation mặc định của LifecycleProcessor; quản lý nhóm phase và thời gian chờ |
| **ApplicationContext.refresh()** | Làm context hoạt động; kích hoạt auto-start SmartLifecycle khi thích hợp |
| **ApplicationContext.close()** | Bắt đầu context shutdown; lifecycle processor yêu cầu các beans dừng |
| **spring.lifecycle.timeout-per-shutdown-phase** | Property Spring Boot cấu hình giới hạn chờ mặc định cho **mỗi phase** |

Trong Spring Framework 6.2, class đầy đủ là:

~~~java
org.springframework.context.support.DefaultLifecycleProcessor
~~~

Interface liên quan:

~~~java
org.springframework.context.SmartLifecycle
~~~

Một SmartLifecycle triển khai điển hình:

~~~java
public final class WorkerLifecycle implements SmartLifecycle {

    @Override
    public void start() {
        // Bắt đầu nhận và xử lý việc.
    }

    @Override
    public void stop() {
        // Dừng đồng bộ nếu được gọi trực tiếp.
    }

    @Override
    public void stop(Runnable callback) {
        // Yêu cầu dừng; gọi callback.run() sau khi đã dừng thực sự.
    }

    @Override
    public boolean isRunning() {
        return false;
    }

    @Override
    public int getPhase() {
        return 200;
    }
}
~~~

Đoạn trên chỉ **minh họa chữ ký API**, chưa phải chương trình hoạt động thực tế vì chưa có import, trạng thái chạy và cơ chế cleanup. Phần 7 cung cấp một ví dụ Java đầy đủ có thể chạy.

### SmartLifecycle.stop(Runnable) khác Lifecycle.stop() ra sao?

**Lifecycle.stop()** thường đại diện cho việc dừng đồng bộ: khi method trả về, thành phần nên đã thực sự ngừng chạy.

**SmartLifecycle.stop(Runnable callback)** cho phép thực hiện việc dừng bất đồng bộ. LifecycleProcessor gọi method này và chờ **callback.run()** để biết component đã dừng; nó không thể suy ra hoàn tất chỉ từ việc stop(Runnable) trả về.

Javadoc SmartLifecycle nhấn mạnh rằng callback **phải được gọi sau khi shutdown thực sự hoàn thành**, để tránh thời gian chờ thừa hoặc timeout trong shutdown chung.

Nếu code **không gọi callback**, processor có thể chờ đến hết timeout của phase ngay cả khi thành phần đã dừng từ trước.

## 3. Thứ tự phase khi start và stop

Spring Framework dùng giá trị nguyên trả về bởi **SmartLifecycle.getPhase()**.

- **Start:** phase **nhỏ trước**, phase **lớn sau**.
- **Stop:** phase **lớn trước**, phase **nhỏ sau**.
- **Giá trị âm** thường thích hợp cho hạ tầng cần sống sớm và được dừng muộn.
- **Giá trị dương** thường thích hợp cho thành phần phụ thuộc vào hạ tầng: start muộn, stop sớm.
- SmartLifecycle mặc định có **getPhase() = Integer.MAX_VALUE**, nên nếu không override, nó thường start rất muộn và stop rất sớm.
- Một bean **Lifecycle** thông thường không implements SmartLifecycle/Phased được DefaultLifecycleProcessor gán phase mặc định **0**.

Ví dụ:

| Component | Phase | Lúc start | Lúc stop |
| --- | ---: | --- | --- |
| Storage client | -100 | 1 | 4 |
| Internal registry | 0 | 2 | 3 |
| Message consumer | 100 | 3 | 2 |
| Request intake | 200 | 4 | 1 |

~~~text
START:
phase -100 -> phase 0 -> phase 100 -> phase 200

STOP:
phase 200 -> phase 100 -> phase 0 -> phase -100
~~~

Với nhóm bean cùng phase, không nên dựa vào một thứ tự cố định không được tài liệu bảo đảm. Nếu component A phải dừng trước B, hãy thiết kế dependency/phase rõ ràng và kiểm thử.

**Quan hệ depends-on được Spring tôn trọng** ngay cả khi thứ tự phụ thuộc xung đột với phase dự kiến. Một component cần dependency còn sống khi chính nó đang stop nên phải khai báo phụ thuộc phù hợp; không thể coi getPhase là cơ chế dependency management đầy đủ.

### @Order không thay thế getPhase()

**@Order** thường dùng để sắp xếp một số danh sách components, filters hoặc runners theo contract tương ứng. Nó **không phải** cách khai báo thứ tự vòng đời SmartLifecycle. Để quyết định phase, override **getPhase()** hoặc cung cấp implementation của **Phased** theo API.

## 4. Thời hạn dừng của từng phase được áp dụng ra sao?

Trong quá trình đóng context, DefaultLifecycleProcessor nhóm Lifecycle beans theo phase. Tại một nhóm:

1. Processor chọn phase có thứ tự dừng ưu tiên cao hơn.
2. Với SmartLifecycle đang chạy, nó gọi **stop(Runnable)** và theo dõi các callback báo hoàn tất.
3. Những bean cùng phase có thể tiến hành cleanup **bất đồng bộ trong cùng một khoảng thời gian chờ**.
4. Processor đợi nhóm đó tối đa bằng **timeout của phase**.
5. Khi tất cả callbacks cần thiết đã được gọi, processor có thể tiếp tục ngay, không cần đợi đủ timeout.
6. Nếu hết timeout mà vẫn có callbacks chưa được gọi, processor có thể ghi cảnh báo và tiếp tục sang các phase tiếp theo.

Ví dụ có ba phase:

~~~text
timeout-per-shutdown-phase = 5 giây

Phase 200: receiver-A và receiver-B
  stop(receiver-A) mất 1 giây
  stop(receiver-B) mất 4 giây
  -> đợi nhóm phase 200 khoảng 4 giây, không phải 1 + 4
  -> phase 100 bắt đầu sau khi nhóm 200 hoàn thành

Phase 100: scheduler
  stop() hoàn tất sau 2 giây
  -> đợi khoảng 2 giây

Phase 0: infrastructure
  stop() hoàn tất sau 1 giây
  -> đợi khoảng 1 giây

Thời gian đợi liên quan đến các nhóm ≈ 4 + 2 + 1 = 7 giây
~~~

Đây là **ví dụ khái niệm** cho các stop callbacks được thực hiện bất đồng bộ, không phải kết quả đo thực tế. Phần mềm có thêm overhead, callbacks khác, destroy methods, GC, hệ điều hành và điều kiện dependency.

Nếu phase 200 có **10 beans**, timeout 5 giây vẫn là **ngân sách chờ của cả nhóm phase 200**, không phải 10 × 5 giây.

### Một phase dừng lỗi hoặc vượt timeout thì sao?

Với async stop đúng contract, hết timeout không nhất thiết ép hoạt động cleanup đang chạy phải kết thúc. Processor có thể đi tiếp để không treo mãi ở cùng phase. Hậu quả nguy hiểm: bean ở phase thấp hơn có thể bị dừng, trong khi bean ở phase cao hơn **vẫn đang cleanup và còn cần sử dụng nó**.

Vì vậy, timeout phải **đủ dài để tài nguyên dừng an toàn**, còn implementation phải phát callback **đúng lúc**. Đừng dùng timeout thật ngắn để che việc callback bị quên hay một consumer không có cơ chế dừng nhận message.

## 5. Phân biệt các loại thời gian cần cấu hình

| Khái niệm | Nó giới hạn điều gì? | Có giống timeout per phase không? |
| --- | --- | --- |
| **Timeout per shutdown phase** | Thời gian chờ callback của một nhóm SmartLifecycle có cùng phase | Chính là chủ đề bài |
| **Timeout cho một phase cụ thể** | Override riêng cho phase đã chọn | Cùng cơ chế, nhưng ưu tiên cấu hình riêng |
| **Timeout graceful HTTP shutdown** | Thời gian web server xử lý request đang chạy trong shutdown phase | Có liên hệ; có thể dùng budget của một SmartLifecycle phase |
| **Timeout chờ executor ngừng** | Đợi các task đang chạy theo cấu hình executor | Một cơ chế lifecycle khác, cần phối hợp |
| **Timeout kết nối mạng** | Chờ network connect/read/write | Không được thay thế bởi lifecycle timeout |
| **Kubernetes terminationGracePeriodSeconds** | Ngân sách tổng để container kết thúc lịch sự trước khi bị force-kill | Bao ngoài, không đồng nhất |
| **preStop hook duration** | Thời gian hook thực thi trước khi process shutdown | Cũng tiêu tốn shutdown grace budget |
| **JVM shutdown hook** | Cơ chế JVM gọi callback khi process shutdown | Không có nghĩa JVM chờ đúng timeout của một phase duy nhất |

Đừng nhầm **timeout per phase** với **một đồng hồ đếm ngược toàn JVM**. Ví dụ bốn phase có timeout tối đa 5 giây mỗi phase có thể tạo ra tổng thời gian chờ gần 20 giây, **cộng thêm** phần cleanup khác. Nhưng thực tế có thể ngắn hơn nếu callbacks báo hoàn tất sớm.

Đặc biệt, nếu implementation **stop(Runnable) chạy blocking lâu ngay trên thread gọi** thay vì nhanh chóng khởi động shutdown bất đồng bộ rồi trả về, phase timeout **không có nghĩa tự động interrupt** method blocking đó. Cần xử lý timeout riêng ở I/O và thiết kế stop có thể tiến triển khi dependency không phản hồi.

## 6. Giá trị mặc định và cách chỉnh trong Spring Boot 3.5

### 6.1. Property phổ biến

Spring Boot 3.5 hỗ trợ:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Giá trị là một **Duration**. Các hậu tố thông dụng gồm **ms**, **s** và **m** theo contract binding của Spring Boot. Ví dụ:

~~~properties
# Cho mỗi phase tối đa 500 milliseconds:
spring.lifecycle.timeout-per-shutdown-phase=500ms
~~~

Hoặc khi cần dành nhiều thời gian cho in-flight requests:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=45s
~~~

Property này ảnh hưởng **mặc định cho các nhóm phase** do lifecycle processor được Spring Boot tự cấu hình. Nó không mặc định biến toàn bộ shutdown thành một deadline tuyệt đối 45 giây.

### 6.2. Đừng nhầm giá trị mặc định giữa Framework và Boot

Tài liệu phiên bản rất quan trọng:

- **Spring Framework 6.2 DefaultLifecycleProcessor JavaDoc** ghi timeout per phase nội bộ mặc định **10.000 ms (10 giây)** khi không có cấu hình khác.
- **Spring Boot 3.5 Common Application Properties** ghi default của **spring.lifecycle.timeout-per-shutdown-phase** là **30 giây**. Boot tự cấu hình lifecycle processor để áp dụng property này.

Bởi vậy không suy luận một ứng dụng Boot 3.5 mặc định đợi 10 giây/phase chỉ vì bạn đọc trực tiếp JavaDoc của Spring Framework. Với Boot 3.5 dùng auto-configuration thông thường, **mốc mặc định đáng tham khảo là 30 giây/phase**.

Nếu dự án cung cấp custom **lifecycleProcessor** bean, loại bỏ/đổi auto-configuration hoặc sử dụng version khác, giá trị hiệu lực cần được xác nhận theo thực tế. Không khẳng định mọi ứng dụng Spring bất kể cấu hình đều có cùng default.

### 6.3. Cấu hình riêng cho từng phase bằng API Framework 6.2

Nếu một phase cần ngân sách khác hẳn những phase còn lại, Spring Framework 6.2 có API:

~~~java
DefaultLifecycleProcessor processor =
        new DefaultLifecycleProcessor();

processor.setTimeoutPerShutdownPhase(5_000L);
processor.setTimeoutForShutdownPhase(200, 15_000L);
~~~

Đây là **mảnh code minh họa**, không phải chương trình chạy độc lập; cần import **org.springframework.context.support.DefaultLifecycleProcessor** và phải cung cấp processor này cho context thích hợp.

Ý nghĩa:

- Các phase không được override: dùng 5.000 ms.
- **Phase 200:** dùng 15.000 ms.
- Cấu hình riêng có thể được gán cho nhiều phase bằng **setTimeoutsForShutdownPhases(Map<Integer, Long>)**.

API **setTimeoutForShutdownPhase** và **setTimeoutsForShutdownPhases** được bổ sung từ Spring Framework **6.2**. Đừng dùng nguyên code đó trên Spring Framework 6.1 hoặc một phiên bản chưa có API.

Có thể thay lifecycle processor thông qua bean tên chính xác **lifecycleProcessor**:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class PhaseTimeoutPolicy {

    @Bean(name = "lifecycleProcessor")
    DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor =
                new DefaultLifecycleProcessor();

        processor.setTimeoutPerShutdownPhase(5_000L);
        processor.setTimeoutForShutdownPhase(200, 15_000L);
        return processor;
    }
}
~~~

Đây là một **class cấu hình Java hoàn chỉnh**; nếu thêm vào project Spring Boot 3.5 đúng package được component scan, nó cung cấp custom lifecycle processor và thay thế cấu hình processor mặc định khi bean name phù hợp.

**Lưu ý cấu hình:** Khi đã định nghĩa custom lifecycleProcessor, không giả định property **spring.lifecycle.timeout-per-shutdown-phase** tiếp tục được Spring Boot áp dụng lên custom bean. Hãy tự cấu hình processor trong code này hoặc kiểm tra auto-configuration/conditional thực tế. Hai cách cấu hình ở trên là **hai phương án thay thế**, không phải mặc định tự động cộng dồn.

**Lưu ý nâng cấp:** Đừng tự thay DefaultLifecycleProcessor bằng bean có behavior khác nếu chỉ cần một timeout dùng chung. Property của Boot thường là cách ngắn và ít rủi ro hơn.

## 7. Ví dụ runnable Java 17+: nhìn thấy phase, callback và thời gian chờ

Ví dụ Spring Boot 3.5.x dưới đây minh họa:

1. Hai thành phần SmartLifecycle ở phase **100** và **200**.
2. Phase 100 start **trước** phase 200.
3. Khi đóng context, phase 200 stop **trước** phase 100.
4. Mỗi stop(Runnable) khởi tạo thread cleanup nhỏ rồi trả về; DefaultLifecycleProcessor chờ callback.
5. Khi timeout lớn hơn thời gian cleanup, context close chỉ hoàn tất sau cả hai callbacks.
6. Không cần chạy web server; ví dụ non-web giúp quan sát rõ lifecycle.

### 7.1. Tạo project

Dùng Spring Initializr: **Maven**, **Java 17 trở lên**, **Spring Boot 3.5.x**, group **com.example**, artifact **lifecycle-demo**, package **com.example.demo**. Chọn **Spring Boot Starter**; không cần Spring Web.

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=lifecycle-demo
spring.main.web-application-type=none

# Timeout tối đa cho MỖI phase, đủ lớn cho demo:
spring.lifecycle.timeout-per-shutdown-phase=2s
~~~

Không cần đặt server.port vì đây là ứng dụng non-web. Nếu dự án dùng classpath có starter khác, property web-application-type=none vẫn yêu cầu Boot chạy kiểu non-web.

### 7.2. File Java đầy đủ

Tạo **src/main/java/com/example/demo/PhaseTimeoutDemoApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PhaseTimeoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PhaseTimeoutDemoApplication.class);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("RUN_RETURNED active="
                    + context.isActive());
        }

        System.out.println("CONTEXT_CLOSED");
    }

    @Bean
    SmartLifecycle storage() {
        return new DemoLifecycle("storage", 100, 250);
    }

    @Bean
    SmartLifecycle consumer() {
        return new DemoLifecycle("consumer", 200, 350);
    }

    static final class DemoLifecycle implements SmartLifecycle {

        private final String name;
        private final int phase;
        private final long cleanupMillis;
        private volatile boolean running;

        DemoLifecycle(String name, int phase, long cleanupMillis) {
            this.name = name;
            this.phase = phase;
            this.cleanupMillis = cleanupMillis;
        }

        @Override
        public void start() {
            running = true;
            System.out.println("START " + name
                    + " phase=" + phase);
        }

        @Override
        public void stop() {
            // Đường dừng đồng bộ nếu ai đó gọi trực tiếp Lifecycle.stop().
            running = false;
        }

        @Override
        public void stop(Runnable callback) {
            System.out.println("STOP_REQUEST " + name
                    + " phase=" + phase);

            // Không chặn thread gọi stop: dừng mô phỏng bất đồng bộ.
            Thread worker = new Thread(() -> {
                try {
                    Thread.sleep(cleanupMillis);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    // Demo không quản lý resource thật:
                    // đặt trạng thái dừng rồi báo hoàn thành.
                    running = false;

                    System.out.println("STOP_DONE " + name
                            + " phase=" + phase);
                    callback.run();
                }
            }, "shutdown-" + name);

            worker.start();
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return phase;
        }
    }
}
~~~

**Đây là chương trình Java hoàn chỉnh khi đặt trong dự án Spring Boot Maven đúng dependencies.** Tên file đúng với public class, package đúng cấu trúc và tất cả phương thức trừu tượng của SmartLifecycle/Lifecycle đã được triển khai. **isAutoStartup()** dùng default true của SmartLifecycle.

Mã dùng **Thread.sleep** chỉ để giả lập cleanup có giới hạn; không phải hướng dẫn triển khai một message consumer production bằng cách sleep trong shutdown. Trong hệ thống thật, worker phải chấm dứt nhận việc mới, quản lý in-flight tasks và giải phóng tài nguyên thật sự **trước khi gọi callback**.

### 7.3. Chạy chương trình

Trong thư mục dự án có Maven Wrapper:

~~~bash
# Linux/macOS:
./mvnw spring-boot:run

# Windows PowerShell/cmd:
# .\mvnw.cmd spring-boot:run
~~~

Với cấu hình bình thường, các dòng **do code ví dụ tự in**, theo thứ tự:

~~~text
START storage phase=100
START consumer phase=200
RUN_RETURNED active=true
STOP_REQUEST consumer phase=200
STOP_DONE consumer phase=200
STOP_REQUEST storage phase=100
STOP_DONE storage phase=100
CONTEXT_CLOSED
~~~

Spring Boot/Maven cũng có thể in logs khác xen giữa. Đoạn trên chỉ liệt kê các dòng của demo. Mức 250/350 milliseconds là thời gian sleep dự kiến, không phải lời hứa về đồng hồ chính xác ở mọi hệ điều hành.

**Vì sao thứ tự như vậy?**

- Khi refresh, DefaultLifecycleProcessor nhìn thấy hai SmartLifecycle auto-start beans. **storage phase=100** được start trước **consumer phase=200**.
- Sau khi các startup hooks chạy xong, SpringApplication.run trả về, main in **RUN_RETURNED**.
- Rời khối **try-with-resources** làm **ConfigurableApplicationContext.close()** được gọi.
- Shutdown đi từ phase 200 xuống phase 100. Consumer dừng trước; callback của consumer báo xong mới chuyển sang storage.
- Timeout 2 giây đủ cho cleanup 350ms và 250ms nên không cần chờ hết timeout.
- Sau context close hoàn tất, chương trình in **CONTEXT_CLOSED**.

### 7.4. Kiểm tra hiểu lầm về timeout

Chạy lại demo với giá trị timeout thấp hơn thời gian cleanup:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--spring.lifecycle.timeout-per-shutdown-phase=100ms
~~~

Nếu dùng Windows/PowerShell, cú pháp truyền Maven arguments cần phù hợp shell; có thể thay trực tiếp property trong application.properties khi học.

Tình huống này **cố ý tạo một phase timeout quá ngắn**:

- Consumer cần giả lập 350ms, nhưng phase được chờ tối đa 100ms.
- Processor có thể hết thời gian trước khi consumer gọi callback.
- Nó có thể tiếp tục yêu cầu dừng storage dù consumer còn đang cleanup.
- Worker threads vẫn có thể chạy sau khi processor không còn chờ chúng.
- Thứ tự **STOP_DONE** có thể thay đổi/đan xen, không nên đưa một khối stdout cố định cho trường hợp này.
- Có thể quan sát log cảnh báo về việc không dừng hết bean trong timeout của phase.

**Đây là bài thử hành vi timeout**, không phải cấu hình đề xuất cho production. Một timeout 100ms không đủ cho các consumer/connection drains thực tế.

Nếu trong ví dụ timeout thấp mà process vẫn còn sống thêm một khoảng thời gian, điều đó cũng không bất thường: các thread cleanup đã được tạo vẫn tồn tại. **Hết thời gian chờ của DefaultLifecycleProcessor không tương đương Java Thread.interrupt hoặc đóng tài nguyên cưỡng bức**.

## 8. Nhiều bean trong cùng một phase

Giả sử có ba component:

~~~text
phase=200:
  consumer-A -> callback sau 700ms
  consumer-B -> callback sau 1500ms

phase=100:
  storage    -> callback sau 300ms
~~~

Nếu timeout mặc định mỗi phase = 2 giây:

- Với phase 200, processor phải chờ **các callbacks thuộc nhóm**. Nếu chúng thật sự dừng bất đồng bộ song song, nhóm này hoàn tất khoảng 1500ms, không phải 700 + 1500ms.
- Sau đó mới yêu cầu dừng phase 100 và chờ khoảng 300ms.
- Tổng thời gian chờ liên quan đến hai nhóm khoảng 1800ms, chưa kể phần khác.

Nếu consumer-B không gọi callback:

- Với phase 200, processor chỉ có thể biết group chưa hoàn tất, dù consumer-A đã xong.
- Sau tối đa 2 giây, nó có thể cảnh báo rồi tiếp tục phase 100.
- Việc B có thực sự ngừng xử lý message hay không phụ thuộc implementation của B, không được timeout tự giải quyết.

### Tại sao không cấp timeout cho từng bean?

Thời gian chờ là của **nhóm cùng phase**, vì DefaultLifecycleProcessor cần bảo đảm một nhóm dependencies được dừng trước khi đi tới phase tiếp theo. Nếu mỗi bean có ngân sách riêng và chờ tuần tự, thứ tự/độ trễ sẽ khác và thời gian shutdown có thể tăng quá mức.

Nếu một bean rất chậm mà những bean còn lại cần dừng sớm, cân nhắc:

- Tách bean chậm sang phase có **ngân sách riêng**.
- Tối ưu cleanup, batching, cancellation và giới hạn in-flight tasks.
- Dùng **setTimeoutForShutdownPhase(...)** khi thật sự cần.
- Thiết kế lại dependency: ngừng nhận việc trước, drain ngắn, sau đó đóng storage.
- Tránh tăng timeout toàn ứng dụng chỉ vì một component dừng không kiểm soát.

## 9. setTimeoutForShutdownPhase và cấu hình chi tiết theo nhóm

Spring Framework 6.2 hỗ trợ:

~~~java
processor.setTimeoutForShutdownPhase(200, 15_000L);
processor.setTimeoutForShutdownPhase(100, 5_000L);
~~~

Hai phase có ngân sách riêng:

| Phase | Ví dụ component | Timeout |
| ---: | --- | ---: |
| 200 | Message consumers | 15 giây |
| 100 | Stateful storage clients | 5 giây |
| Các phase khác | Default policy | Ví dụ 3 hoặc 5 giây theo cấu hình |

Có thể dùng một map:

~~~java
processor.setTimeoutsForShutdownPhases(
        java.util.Map.of(200, 15_000L, 100, 5_000L));
~~~

Đây là **mảnh code minh họa** bên trong nơi có biến processor kiểu DefaultLifecycleProcessor. API riêng phase có từ Spring Framework 6.2; kiểm tra compatibility khi nâng/hạ phiên bản.

**Không nhầm với setConcurrentStartupForPhase(...)** trong Spring Framework 6.2.6+: method kia liên quan tùy chọn **start đồng thời** cho một số phase, không phải timeout dành cho stop callbacks. Cùng nhắc đến phase và timeout nhưng lifecycle phase khác và semantics khác.

Một vấn đề cần để ý: **Spring Boot property** áp dụng một Duration mặc định cho mọi phase. Khi muốn override chỉ một số phase mà vẫn dùng chính sách Boot, nên cân nhắc custom lifecycleProcessor hoặc một phương thức cấu hình lifecycle processor có kiểm soát; không viết một property tưởng tượng như **spring.lifecycle.timeout-phase-200** vì Spring Boot 3.5 không có property chuẩn đó.

## 10. Graceful HTTP shutdown có liên quan gì?

Spring Boot 3.5 hỗ trợ graceful shutdown cho embedded web servers và **bật graceful shutdown theo mặc định** ở những server được hỗ trợ. Trong quá trình đóng ApplicationContext, web server graceful shutdown tham gia vào các phase dừng của SmartLifecycle.

Tài liệu Spring Boot 3.5 mô tả graceful web shutdown diễn ra ở **phase dừng sớm nhất** của các SmartLifecycle components. Lúc này server cố gắng không nhận thêm request mới và cho phép những request đã nhận hoàn thành trong giới hạn được cấu hình.

Ví dụ:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Property này cũng có thể là ngân sách chờ cho phase mà graceful web shutdown đang thực hiện, nên **không chỉ liên quan tới bean do ứng dụng tự viết**.

Cần phân biệt:

- **Từ chối request mới:** có thể thực hiện ở tầng network hoặc phản hồi HTTP khác nhau theo loại web server.
- **In-flight requests:** được phép hoàn tất trong giới hạn graceful shutdown.
- **ApplicationContext lifecycle:** các SmartLifecycle beans được dừng theo phase.
- **Tài nguyên sâu hơn:** thread pools, messaging clients, caches, database pools còn có lifecycle riêng.

**Không tự đặt phase tùy tiện** cho các component cần tiếp tục phục vụ web requests khi server đang drain, nếu có thể khiến dependency bị đóng trước request hoàn tất. Luôn kiểm tra phase của các thành phần hạ tầng quan trọng, hiểu depends-on và kiểm tra toàn bộ shutdown path trên web server dùng thực tế.

### Với server khác nhau, cách ngừng request mới có thể khác

Spring Boot 3.5 Reference chỉ rõ graceful shutdown behavior phụ thuộc embedded web server. Một số server ngừng nhận kết nối mới ở tầng network, server khác có thể trả HTTP response đặc biệt. Đừng viết test cứng rằng mọi request mới phải trả đúng HTTP 503 sau SIGTERM; đôi khi connection bị từ chối thay vì nhận response.

Graceful shutdown không tự bảo đảm **zero downtime**. Cần phối hợp readiness, load balancer drain, connection reuse, Kubernetes termination budget, retries phù hợp và số lượng replicas còn sẵn sàng.

## 11. Quan hệ với Kubernetes terminationGracePeriodSeconds

Một Deployment có thể khai báo:

~~~yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 75
      containers:
        - name: app
          image: example/lifecycle-demo:1.0.0
~~~

Đây là **fragment** của Pod template, không phải Deployment manifest hoàn chỉnh; image là giá trị minh họa, phải thay bằng image thực tế.

Khi Pod bị terminate:

1. Kubernetes bắt đầu ngân sách termination grace.
2. preStop hook (nếu có) có thể chạy và **tiêu tốn cùng ngân sách này**.
3. Kubernetes gửi tín hiệu dừng cho tiến trình theo cơ chế runtime tương ứng.
4. JVM/Spring Boot chạy shutdown hook và đóng ApplicationContext.
5. DefaultLifecycleProcessor yêu cầu dừng các SmartLifecycle phases.
6. Bean destroy callbacks, executor cleanup, web server close và các tài nguyên khác cần thời gian.
7. Khi hết termination grace, kubelet/runtime có thể buộc dừng container nếu nó vẫn chưa kết thúc.

### Ước lượng ngân sách tổng

Nếu dự án có:

~~~text
phase 300: tối đa 20s
phase 200: tối đa 15s
phase 100: tối đa 10s
phase   0: tối đa 5s
--------------------------------
Tổng ngân sách chờ phase ~50s
PreStop hook: 5s
Bean destruction/overhead: thêm thời gian
~~~

thì **terminationGracePeriodSeconds=30** sẽ là lựa chọn rủi ro vì kubelet có thể buộc kill container trước khi Spring kịp hoàn thành những phase dừng đúng thiết kế.

Không tính tổng này như một phép cộng cứng cho mọi ứng dụng: nhiều callbacks kết thúc trước timeout, có phase không có bean, và một số công việc xảy ra đồng thời. Nhưng một **upper-bound planning estimate** có cơ sở sẽ hữu ích hơn chọn ngẫu nhiên một giá trị.

Với demo ở phần 7, vì app là **non-web chạy ngắn hạn** và main tự đóng context sau run, không cần Kubernetes hay grace period để quan sát phase timeout.

### Readiness và shutdown

Trong triển khai có load balancer, nên chuyển readiness sang **REFUSING_TRAFFIC** khi chuẩn bị shutdown để routing giảm request mới. Nhưng readiness probe có chu kỳ và độ trễ cập nhật endpoints; nó không bảo đảm request mới dừng **ngay lập tức**. Kết hợp readiness và graceful web shutdown thay vì chỉ tăng lifecycle timeout.

## 12. Mối quan hệ với @PreDestroy và các cleanup callbacks

Một bean có thể có nhiều cleanup hooks:

- **SmartLifecycle.stop(Runnable)**: đóng vai trò trong **ordered lifecycle stop** với cơ chế callback và timeout phase.
- **DisposableBean.destroy()**: destroy callback sau các bước dừng lifecycle thông thường.
- **@PreDestroy**: callback hủy bean.
- **Custom destroy-method**: phương thức cleanup được khai báo tại bean definition.
- **Executor/ConnectionPool shutdown hooks**: cơ chế riêng của từng thư viện.

Trong shutdown bình thường, Spring thường xử lý **lifecycle stop trước khi thực hiện general bean destruction**. Vì thế nếu dừng SmartLifecycle quá nhanh hoặc báo callback trước khi thực sự xong, một dependency có thể bị destroy trong lúc thread khác vẫn đang sử dụng nó.

**Timeout per phase không thay thế timeout của @PreDestroy hay một network close vô hạn.** Nếu @PreDestroy thực hiện blocking call 60 giây, việc lifecycle timeout 5 giây không có nghĩa Spring sẽ tự interrupt @PreDestroy sau 5 giây.

Cũng không bảo đảm mọi lỗi startup đều gọi đủ các lifecycle stop hooks: khi refresh thất bại, một số beans có thể bị destroy theo đường xử lý lỗi trước khi chúng từng được start. Implement cleanup cần idempotent, chịu được trường hợp resource chỉ khởi tạo một phần và không ném exception khi đã dừng.

### Dừng theo hai pha nghiệp vụ

Một số service cần hai bước:

~~~text
1. Quiesce: ngừng nhận message/request mới.
2. Drain: đợi các tác vụ đang xử lý kết thúc, có deadline.
3. Close: giải phóng kết nối, thread, consumer.
4. Signal: callback.run() báo đã dừng.
~~~

Nếu drain vượt deadline, hệ thống cần chính sách rõ ràng: hủy việc có kiểm soát, checkpoint/requeue message chưa xử lý, ghi trạng thái phục hồi hoặc chấp nhận phát lại theo idempotency. **Không gọi callback rồi âm thầm để worker tiếp tục xử lý như cũ**.

## 13. Anti-pattern: callback quên, callback quá sớm và stop blocking

### 13.1. Quên callback

~~~java
@Override
public void stop(Runnable callback) {
    stopConsumerAsync();
    // Không có callback.run(): sai contract.
}
~~~

Đây là **mảnh phản ví dụ**, giả sử stopConsumerAsync() đã được định nghĩa. DefaultLifecycleProcessor không thể nhận biết quá trình dừng đã hoàn tất và có thể chờ hết phase timeout.

### 13.2. Gọi callback quá sớm

~~~java
@Override
public void stop(Runnable callback) {
    stopConsumerAsync();
    callback.run(); // Sai nếu cleanup còn tiếp diễn.
}
~~~

Mảnh phản ví dụ này tạo tín hiệu **đã dừng** trong khi resource còn hoạt động. Spring có thể chuyển sang phase sau và đóng dependency mà consumer vẫn dùng.

### 13.3. Blocking ngay trong stop(Runnable)

~~~java
@Override
public void stop(Runnable callback) {
    waitForNetworkForever(); // Có thể chặn thread shutdown.
    callback.run();
}
~~~

Nếu method bị kẹt trong **waitForNetworkForever**, timeout của latch/chờ callback ở DefaultLifecycleProcessor không chắc có thể giải thoát thread đang mắc kẹt. Phải thiết kế timeout của I/O, bounded waits và cancellation riêng.

### 13.4. Dừng theo thứ tự sai

~~~text
Storage phase=200
Consumer phase=100

STOP: Storage trước Consumer -> consumer mất dependency.
~~~

Nếu consumer cần storage khi flush, phase này có thể gây mất message hoặc lỗi cleanup. Thiết kế lại thành **Consumer phase cao hơn Storage** hoặc khai báo phụ thuộc rõ ràng.

### 13.5. Thay timeout để che lỗi thiết kế

Đặt timeout từ 30 giây lên 10 phút có thể giảm số lần cảnh báo nhưng làm deploy/rolling update chậm và dễ vượt termination budget. Cần quan sát root cause: thread không thoát, network retry vô hạn, callback quên, nhiều job chưa checkpoint hoặc deadlock.

## 14. Đo thời gian shutdown đúng cách

Khi kiểm thử shutdown, ghi lại các mốc:

~~~text
T0  : Context bắt đầu close / SIGTERM
T1  : STOP_REQUEST phase lớn nhất
T2  : STOP_DONE cuối cùng của phase đó
T3  : STOP_REQUEST phase tiếp theo
T4  : STOP_DONE phase tiếp theo
T5  : Các destroy callbacks kết thúc
T6  : Process thực sự exit
~~~

Metrics và logs nên chứa **bean name**, **phase**, **elapsedMillis**, **timeout budget**, **số việc còn lại** và **kết quả cleanup**. Không log dữ liệu nhạy cảm hoặc toàn bộ message payloads.

### Kiểm thử có chủ đích

| Tình huống | Cần quan sát |
| --- | --- |
| Các callbacks hoàn tất trước deadline | Phase tiếp theo bắt đầu ngay khi nhóm trước đã xong |
| Hai beans cùng phase, một bean chậm | Ngân sách phase là của nhóm, không cộng theo bean |
| Một bean không gọi callback | Cảnh báo/timeout rồi chuyển phase, không coi đó là thành công |
| Một bean stop blocking vô hạn | Timeout phase không tự giải phóng thread bị chặn |
| Timeout quá ngắn | Cleanup của phase trước có thể chồng với phase sau |
| @PreDestroy chậm | Tổng shutdown có thể vượt tổng thời gian chờ phase |
| Multiple replicas terminate đồng thời | Grace budget/traffic drain và shutdown dependency vẫn hoạt động |
| JVM bị SIGKILL | Không thể tin rằng mọi callback sẽ được gọi |
| Bean không bao giờ start | stop() cần an toàn nếu chưa running |
| Context refresh thất bại | Hủy tài nguyên đã tạo một phần không dựa vào happy path |

### Log warning nên được hiểu thế nào?

Một warning timeout có nghĩa **processor đã không nhận đủ tín hiệu hoàn tất** trong thời gian được cấp cho phase. Nó không chứng minh chính xác resource đã ngừng hay chưa. Cần kiểm tra callback, thread dumps, active tasks, queue lag, pool statistics và các system metrics liên quan.

## 15. Phân biệt SmartLifecycle với executor shutdown

Một executor như **ThreadPoolTaskExecutor** có cấu hình riêng liên quan tới việc có nhận task mới khi context đóng, có đợi task hiện tại kết thúc hay không và đợi bao lâu. Tùy version Spring Boot/Spring Framework, các property về task execution shutdown có thể tồn tại **bên cạnh** lifecycle timeout.

Vì vậy:

- **DefaultLifecycleProcessor** quản lý thứ tự stop của các Lifecycle/SmartLifecycle beans.
- **Executor** có thể quản lý số worker threads, hàng đợi và shutdown policy riêng.
- **Database client / messaging library** có thể có timeout network, flush hoặc close riêng.
- **Kubernetes** quản lý deadline của container termination.

Một cấu hình **spring.lifecycle.timeout-per-shutdown-phase=30s** không đủ để chứng minh mọi executor task kết thúc sau đúng 30 giây. Xác định chính xác từng bean tham gia lifecycle phase hay destroy path nào và đặt những deadline tương thích với nhau.

Nếu consumer sử dụng executor, hãy đảm bảo thứ tự: ngừng nhận mới → đợi in-flight trong deadline → đóng executor/storage theo dependency. Không tắt executor trước khi consumer hoàn thành phần cần thiết.

## 16. Câu hỏi và bài tập củng cố

**Câu 1.** Có 5 SmartLifecycle beans cùng phase=200. Timeout per phase=10s. Có phải Spring dành tối đa 50s chờ cả nhóm không?

**Câu 2.** Hai beans A phase=300 và B phase=100. A cần B khi shutdown. Spring sẽ yêu cầu bean nào dừng trước? Khi startup, bean nào start trước?

**Câu 3.** Vì sao một implementation gọi callback.run() ngay sau khi bắt đầu việc dừng bất đồng bộ là sai?

**Câu 4.** Một bean đã dừng thực tế nhưng quên gọi callback. Processor có thể phản ứng ra sao?

**Câu 5.** Nếu cấu hình Spring Boot 3.5 không đặt property timeout, giá trị mặc định trong Boot Common Application Properties là bao nhiêu? Vì sao không nên nhầm với default JavaDoc của Framework 6.2?

**Câu 6.** Khi cần phase 200 chờ 15s và các phase còn lại chỉ 5s, dùng API nào?

**Câu 7.** Nếu stop(Runnable) gọi API mạng không timeout và block vô hạn, chỉ giảm timeout per phase có giải quyết được không?

**Câu 8.** Một Pod Kubernetes có terminationGracePeriodSeconds=25 nhưng các phase cộng ngân sách lên gần 50s. Rủi ro nào xảy ra?

**Câu 9.** Khi graceful HTTP shutdown, tại sao không được dừng connection pool trước khi các in-flight requests sử dụng nó đã hoàn tất?

**Câu 10.** Vì sao @Order không phải cách đúng để điều chỉnh stop order của SmartLifecycle?

### Đáp án gợi ý

1. Không; timeout là **của cả phase**, các callbacks có thể thực hiện bất đồng bộ cùng ngân sách.
2. Start B trước A, stop A trước B theo phase.
3. Spring tưởng cleanup đã xong và có thể stop dependencies quá sớm.
4. Chờ hết timeout phase, ghi warning và tiếp tục dừng các nhóm khác.
5. Boot 3.5 dùng **30 giây/phase** theo property default; raw Framework 6.2 DefaultLifecycleProcessor JavaDoc nêu 10 giây.
6. **setTimeoutPerShutdownPhase(5_000L)** và **setTimeoutForShutdownPhase(200, 15_000L)** trên processor tùy biến.
7. Không; phải thiết kế bounded I/O và callback đúng contract.
8. Pod có thể bị force-kill khi chưa xong cleanup; cần phối hợp timeout và grace budget.
9. Dependency pool bị đóng khi request chưa xong có thể gây lỗi hoặc mất việc.
10. **getPhase()** và depends-on mới liên quan lifecycle ordering.

## 17. Checklist triển khai và tóm tắt

- [ ] Xác định những bean nào thực sự implement SmartLifecycle.
- [ ] Hiểu **start phase tăng dần, stop phase giảm dần**.
- [ ] Đặt phase dựa trên **dependency sống/dừng**, không chỉ cho đẹp.
- [ ] Với async stop, chỉ gọi callback.run() **sau cleanup**.
- [ ] Không để stop(Runnable) block vô hạn hoặc gọi network thiếu timeout.
- [ ] Hiểu timeout là **của nhóm phase**, không phải mỗi bean.
- [ ] Không nhầm Spring Boot 3.5 default 30s với raw Framework 6.2 default 10s.
- [ ] Dùng **spring.lifecycle.timeout-per-shutdown-phase** nếu cần một mức chung.
- [ ] Chỉ override **setTimeoutForShutdownPhase** khi một phase thực sự cần ngân sách riêng.
- [ ] Cẩn thận khi cung cấp custom bean **lifecycleProcessor** để không bỏ qua auto-configuration.
- [ ] Không quên liên hệ graceful HTTP shutdown, executors, @PreDestroy và connection pools.
- [ ] Tổng shutdown time được xét cùng **terminationGracePeriodSeconds** và preStop.
- [ ] Kiểm thử nhánh timeout, quên callback, I/O lỗi và restart trong staging.
- [ ] Có logs/metrics để đo thời gian từ stop request tới callback hoàn thành.

**Tổng kết:** DefaultLifecycleProcessor giúp Spring dừng các SmartLifecycle components theo thứ tự phase. Mỗi nhóm cùng phase được cấp một **ngân sách chờ riêng** cho các callback dừng. Nếu callbacks hoàn thành sớm, Spring chuyển tiếp ngay; nếu quá hạn, Spring không tự cưỡng bức mọi threads và tài nguyên dừng, nên ứng dụng phải tự đảm bảo stop contract và cleanup deadline. Thiết kế đúng cần phối hợp **phase, callback, timeout**, các dependency liên quan và ngân sách termination của nền tảng.

### Tài liệu chính thức

1. Spring Framework 6.2 JavaDoc — DefaultLifecycleProcessor, timeout per phase và per-phase overrides: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
2. Spring Framework 6.2 JavaDoc — SmartLifecycle, stop(Runnable), default phase và automatic startup: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/context/SmartLifecycle.html
3. Spring Framework 6.2 — Customizing the Nature of a Bean, lifecycle startup/shutdown phases: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
4. Spring Boot 3.5 — Common Application Properties, spring.lifecycle.timeout-per-shutdown-phase: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
5. Spring Boot 3.5 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
6. Kubernetes — Pod termination behavior: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination

Ví dụ runnable được thiết kế cho **Java 17+ / Spring Boot 3.5.x / Spring Framework 6.2.x**. Các phiên bản khác có thể thay đổi giá trị mặc định, API per-phase override và behavior graceful shutdown; đối chiếu JavaDoc đúng phiên bản trước khi áp dụng vào hệ thống production.