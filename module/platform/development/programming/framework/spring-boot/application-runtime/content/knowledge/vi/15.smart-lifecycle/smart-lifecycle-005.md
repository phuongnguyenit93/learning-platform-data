# SmartLifecycle.getPhase và thứ tự khởi động từ phase thấp đến cao

## 1. Hiểu vấn đề

Một ứng dụng Spring Boot thường có nhiều thành phần có vòng đời dài: kết nối đến dịch vụ nền, bộ xử lý, consumer nhận message, scheduler hoặc adapter nhận yêu cầu. Chúng có thể phụ thuộc nhau: hạ tầng phải hoạt động trước worker, worker phải được chuẩn bị trước consumer; khi dừng thì phải ngừng nhận việc mới trước khi tắt worker và hạ tầng.

**SmartLifecycle.getPhase()** của Spring Framework giúp mô tả **thứ tự start/stop giữa các lifecycle bean trong cùng một ApplicationContext**.

Quy tắc cốt lõi:

- **Khởi động:** phase **thấp được start trước**, phase cao được start sau.
- **Dừng:** phase **cao được stop trước**, phase thấp được stop sau.
- **Cùng phase:** không có hợp đồng bảo đảm thứ tự giữa các bean.
- **Quan hệ depends-on rõ ràng:** được ưu tiên hơn thứ tự phase nếu hai thứ xung đột.

Ví dụ ba thành phần:

| Thành phần | getPhase() | Start | Stop |
| --- | ---: | --- | --- |
| Infrastructure | -100 | Đầu tiên | Cuối cùng |
| Worker | 0 | Thứ hai | Thứ hai |
| Consumer | 100 | Cuối cùng | Đầu tiên |

Việc dùng phase tạo ra một quy trình dễ hiểu: **mở hạ tầng → mở worker → nhận việc**; khi shutdown **ngừng nhận việc → dừng worker → đóng hạ tầng**.

**Không nên hiểu phase là độ trễ thời gian.** getPhase() trả về số nguyên dùng để sắp nhóm, không phải số mili-giây chờ hoặc priority của CPU.

## 2. SmartLifecycle cung cấp những gì?

Spring Framework có hai interface nền tảng:

- **Lifecycle** cung cấp start(), stop() và isRunning().
- **Phased** cung cấp getPhase().

**SmartLifecycle extends Lifecycle, Phased** và thêm isAutoStartup(), stop(Runnable callback). Nhìn theo cấu trúc:

~~~text
Lifecycle:
  start()
  stop()
  isRunning()

Phased:
  getPhase()

SmartLifecycle extends Lifecycle, Phased:
  isAutoStartup()
  stop(Runnable callback)
~~~

Ý nghĩa từng method:

| Method | Trách nhiệm |
| --- | --- |
| start() | Đưa component vào trạng thái hoạt động phù hợp |
| stop() | Dừng hoạt động theo hợp đồng Lifecycle |
| isRunning() | Phản ánh component đang chạy hay không |
| getPhase() | Đưa ra thứ tự tương đối khi start/stop |
| isAutoStartup() | Cho phép tự động start khi context refresh |
| stop(Runnable callback) | Dừng và báo cho lifecycle processor khi việc dừng hoàn tất |

SmartLifecycle là cơ chế **quản lý vòng đời của component trong Spring container**, không phải distributed lock hoặc bộ quản lý tiến trình trên Kubernetes. Mỗi ApplicationContext sắp xếp những bean riêng nó; hai Pod có hai container riêng và không có một thứ tự toàn cluster chỉ nhờ getPhase().

## 3. getPhase() chấp nhận giá trị nào?

getPhase() trả về **int**, trong phạm vi **Integer.MIN_VALUE đến Integer.MAX_VALUE**. Có thể dùng số âm, 0, số dương hoặc các khoảng cách không liên tiếp.

~~~text
phase -1000 -> start rất sớm trong nhóm tương đối
phase  -100 -> start sau -1000
phase     0 -> start sau -100
phase   100 -> start sau 0
phase  1000 -> start sau 100
~~~

Khi dừng, thứ tự đảo chiều:

~~~text
phase  1000 -> stop trước
phase   100 -> stop tiếp
phase     0 -> stop tiếp
phase  -100 -> stop tiếp
phase -1000 -> stop sau cùng
~~~

Nên chọn dải giá trị nhất quán, có tài liệu nội bộ nếu có nhiều component. Không cần lạm dụng Integer.MIN_VALUE hoặc Integer.MAX_VALUE cho mọi bean, vì framework có thể có lifecycle phase riêng và default phase của SmartLifecycle đã rất cao.

**Giá trị mặc định đặc biệt:**

- SmartLifecycle.DEFAULT_PHASE là **Integer.MAX_VALUE**.
- SmartLifecycle.getPhase() mặc định trả về DEFAULT_PHASE nếu implementation không override.
- SmartLifecycle.isAutoStartup() mặc định trả về **true**.
- Một **Lifecycle thông thường**, nếu không đồng thời implements SmartLifecycle/Phased, được xem là ở **phase 0** khi lifecycle processor sắp xếp nó.

Đây là nguồn nhầm lẫn phổ biến: **SmartLifecycle không override getPhase() không ở phase 0, mà ở Integer.MAX_VALUE**. Do đó nó thường start muộn hơn các SmartLifecycle có phase nhỏ và stop sớm hơn chúng.

Lifecycle bean thông thường không tự được auto-start lúc refresh chỉ vì có phase hiệu dụng 0. Cần phân biệt việc nó tham gia lệnh lifecycle start/stop với cơ chế auto-start đặc biệt của SmartLifecycle.

## 4. Ai gọi start() và vào thời điểm nào?

**DefaultLifecycleProcessor** là thành phần Spring Framework mặc định điều phối vòng đời trong ApplicationContext. Khi context được refresh, lifecycle processor xem các SmartLifecycle có **isAutoStartup() = true**, xác định phase và dependency rồi gọi start() phù hợp.

Trình tự Spring Boot rút gọn:

~~~text
SpringApplication.run(args)
        |
  Tạo ApplicationContext
        |
  Refresh ApplicationContext
        |
  Khởi tạo singleton thông thường
        |
  LifecycleProcessor.onRefresh()
        |
  SmartLifecycle.start() theo phase thấp -> cao
        |
  Hoàn tất refresh
        |
  ApplicationStartedEvent
        |
  ApplicationRunner / CommandLineRunner
        |
  ApplicationReadyEvent
        |
  ReadinessState.ACCEPTING_TRAFFIC
~~~

Điều quan trọng là **SmartLifecycle tự start trong quá trình refresh, thường trước runner**. Không được xem phase cao là tín hiệu rằng consumer sẽ chờ ApplicationRunner hoàn tất. Nếu một Kafka/RabbitMQ listener container có autoStartup=true, nó có thể bắt đầu poll message trước khi runner warm up cache xong.

Nếu consumer phải chờ một công việc startup bắt buộc, cần dùng **isAutoStartup=false**, lifecycle container API, cơ chế pause/resume hoặc gate theo readiness, chứ không chỉ chọn phase cao.

## 5. Thứ tự giữa các bean cùng phase

Giả sử hai SmartLifecycle cùng trả về phase 10. Chúng nằm trong **cùng nhóm phase**. Spring Framework không bảo đảm thứ tự cụ thể giữa chúng.

Không nên phụ thuộc vào:

- Tên bean theo alphabet.
- Thứ tự class trong một tệp source.
- Thứ tự quét component scan.
- Vị trí khai báo @Bean trong class @Configuration.
- Việc quan sát một lần chạy có thứ tự cố định.

Nếu B thật sự cần A đã start, hãy:

1. Đặt A ở phase thấp hơn B khi quan hệ mang tính nhóm.
2. Khai báo phụ thuộc tường minh, chẳng hạn @DependsOn, nếu B phải start sau A.
3. Hoặc dùng một component coordinator gọi các bước theo thứ tự và kiểm tra trạng thái hoàn thành thật.

Phase chỉ quyết định **thứ tự gọi start()**, không tự bảo đảm các thread bất đồng bộ mà start() tạo ra đã làm xong công việc.

## 6. Quan hệ depends-on được ưu tiên hơn phase

Trong Spring, khi **B depends-on A**, A phải được start trước B, và B phải stop trước A. Quan hệ đó vẫn có hiệu lực ngay cả khi giá trị getPhase() đưa ra thứ tự ngược.

Ví dụ chủ ý mâu thuẫn:

~~~text
A: StorageLifecycle    phase = 100
B: ConsumerLifecycle   phase = -100
B depends-on A
~~~

Chỉ nhìn phase, B có số nhỏ hơn và tưởng được start trước. Nhưng do B phụ thuộc A, thứ tự vòng đời thực là:

~~~text
START A
START B

STOP B
STOP A
~~~

Đoạn minh họa cú pháp:

~~~java
@Component("storage")
class StorageLifecycle implements SmartLifecycle {
    // Method getPhase() tra 100.
    // Cac method Lifecycle khac can duoc cai dat.
}

@Component("consumer")
@DependsOn("storage")
class ConsumerLifecycle implements SmartLifecycle {
    // Method getPhase() tra -100.
    // Cac method Lifecycle khac can duoc cai dat.
}
~~~

**Đây là pseudocode cấu trúc**, không phải hai class Java hoàn chỉnh, vì còn thiếu method cần cài đặt và import.

Khi thiết kế thật, nên chọn phase **phù hợp với dependency**, tránh cố tình tạo hai quy tắc trái nhau. Dùng depends-on khi đó là phụ thuộc trực tiếp và quan trọng, thay vì cố suy luận mọi thứ từ số phase.

## 7. getPhase() và @Order giải quyết các bài toán khác nhau

**getPhase()** được lifecycle processor sử dụng để sắp các SmartLifecycle bean.

**@Order/Ordered** thường được dùng để sắp ApplicationRunner, CommandLineRunner hoặc thứ tự một số danh sách/listener trong các ngữ cảnh Spring hỗ trợ.

Ví dụ:

~~~java
@Order(-100)
@Component
class MessageConsumer implements SmartLifecycle {
    @Override
    public int getPhase() {
        return 100;
    }

    // Cac method bat buoc khac.
}
~~~

Đây là **mã minh họa chưa hoàn chỉnh**, chỉ để so sánh hai cơ chế. Khi DefaultLifecycleProcessor điều phối SmartLifecycle, bean này tham gia **phase 100**, không tự chuyển sang phase -100 do annotation @Order.

Các nhầm lẫn cần tránh:

- @Order(-100) trên runner **không làm runner chạy trước ApplicationStartedEvent**; runner vẫn nằm sau refresh.
- @Order trên SmartLifecycle **không thay thế getPhase()**.
- getPhase() **không sắp thứ tự các runner**.
- Một SmartLifecycle phase 100 vẫn có thể start trước tất cả runner, vì lifecycle auto-start diễn ra trong refresh.

## 8. Ví dụ hoàn chỉnh: start thấp đến cao, stop cao đến thấp

Thử một project **Spring Boot 3.3.x, Java 17+** với ba SmartLifecycle bean. Chúng dùng phase -100, 0, 100 và tự in log khi start/stop.

### 8.1. Cấu trúc tệp

~~~text
phase-order-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          PhaseOrderDemo.java
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'phase-order-demo'
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Dự án cần JDK 17+, Gradle tương thích và plugin/dependencies có thể tải được hoặc đã có trong cache.

### 8.2. Tệp Java tự chạy

Đặt toàn bộ vào **src/main/java/demo/PhaseOrderDemo.java**:

~~~java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class PhaseOrderDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(PhaseOrderDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN_AFTER_RUN");
        }
    }

    @Bean
    NamedLifecycle infrastructure() {
        return new NamedLifecycle("INFRA", -100);
    }

    @Bean
    NamedLifecycle worker() {
        return new NamedLifecycle("WORKER", 0);
    }

    @Bean
    NamedLifecycle inputConsumer() {
        return new NamedLifecycle("INPUT", 100);
    }

    @Bean
    ApplicationRunner verifyRunner(
            @Qualifier("infrastructure") NamedLifecycle infrastructure,
            @Qualifier("worker") NamedLifecycle worker,
            @Qualifier("inputConsumer") NamedLifecycle inputConsumer) {
        return args -> {
            boolean allRunning = infrastructure.isRunning()
                    && worker.isRunning()
                    && inputConsumer.isRunning();

            System.out.println("RUNNER_ALL_RUNNING=" + allRunning);

            if (!allRunning) {
                throw new IllegalStateException("Lifecycle not started");
            }
            if (args.containsOption("fail-runner")) {
                throw new IllegalStateException("Demo runner failure");
            }
        };
    }
}

@Component
class StartupSignals {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
    }
}

final class NamedLifecycle implements SmartLifecycle {
    private final String label;
    private final int phase;
    private volatile boolean running;

    NamedLifecycle(String label, int phase) {
        this.label = label;
        this.phase = phase;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public synchronized void start() {
        if (!running) {
            running = true;
            System.out.println("START_" + label + " phase=" + phase);
        }
    }

    @Override
    public synchronized void stop() {
        if (running) {
            running = false;
            System.out.println("STOP_" + label + " phase=" + phase);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

Vì sao đây là **ví dụ Java hợp lệ**:

- Chỉ **PhaseOrderDemo** là class public; tên tệp khớp.
- Hai class còn lại là package-private, có thể nằm cùng tệp Java và cùng package demo.
- @Bean tạo ba NamedLifecycle, mỗi bean có tên và phase riêng.
- @Qualifier bảo đảm runner inject đúng ba bean dù chúng cùng một kiểu NamedLifecycle, không phụ thuộc compiler có lưu tên tham số hay không.
- SmartLifecycle được implement đầy đủ: start(), stop(), isRunning(), getPhase(), isAutoStartup(), stop(Runnable).
- WebApplicationType.NONE giúp ứng dụng không mở web server và main chủ động đóng context, quan sát chiều shutdown rõ ràng.

### 8.3. Chạy chương trình

Với Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích:

~~~bash
gradle bootRun
~~~

Các thông điệp **do code tự in** xuất hiện theo thứ tự trong lần chạy thành công:

~~~text
START_INFRA phase=-100
START_WORKER phase=0
START_INPUT phase=100
EVENT_STARTED
RUNNER_ALL_RUNNING=true
EVENT_READY
MAIN_AFTER_RUN
STOP_INPUT phase=100
STOP_WORKER phase=0
STOP_INFRA phase=-100
~~~

Log Spring Boot/Gradle có thể xen giữa, nên không assert toàn bộ console. Trong ví dụ không có quan hệ depends-on xung đột và ba phase khác nhau, các **START** luôn xuất hiện theo phase tăng dần; các **STOP** theo phase giảm dần.

Phân tích:

1. **START_INFRA** chạy đầu tiên vì -100 nhỏ nhất.
2. **START_WORKER** chạy tiếp với phase 0.
3. **START_INPUT** chạy cuối nhóm phase này với 100.
4. **EVENT_STARTED** xuất hiện sau context refresh.
5. Runner chỉ chạy sau đó và nhìn thấy cả ba đang running.
6. **EVENT_READY** xuất hiện khi runner hoàn tất thành công.
7. Main đóng context bằng try-with-resources; shutdown stop Input trước Worker trước Infra.

**Không cần Thread.sleep để sắp thứ tự.** Phase điều phối thứ tự gọi method, không phụ thuộc CPU nhanh/chậm. Nhưng lưu ý: code mẫu dùng start() đồng bộ và đặt running=true ngay trong start(), chứ không nạp dependency bất đồng bộ.

### 8.4. Thử nhánh runner thất bại

Chạy:

~~~bash
./gradlew bootRun --args="--fail-runner"
~~~

Các dòng do chương trình in trước khi exception xảy ra:

~~~text
START_INFRA phase=-100
START_WORKER phase=0
START_INPUT phase=100
EVENT_STARTED
RUNNER_ALL_RUNNING=true
~~~

Runner ném **IllegalStateException("Demo runner failure")**. **EVENT_READY** và **MAIN_AFTER_RUN** không xuất hiện trên đường khởi động thành công. Spring Boot đi vào nhánh xử lý startup failure và đóng context nếu đã được dựng; những lifecycle bean đã chạy thường được stop khi context được đóng. Chi tiết log/cleanup khi lỗi có thể xen kẽ, không nên coi stdout của nhánh lỗi là một chuỗi cố định tuyệt đối.

Thí nghiệm cho thấy: **SmartLifecycle auto-start trước runner**. Nếu một runner sau đó thất bại, điều kiện ready không đạt nhưng các lifecycle component đã có thể mở tài nguyên, vì vậy shutdown đúng là quan trọng.

## 9. isAutoStartup(): bật/tắt start khi refresh

SmartLifecycle có method:

~~~java
@Override
public boolean isAutoStartup() {
    return true;
}
~~~

Trong Spring Framework 6.1, giá trị mặc định của SmartLifecycle là true. Nếu đổi thành **false**:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

thì lifecycle processor không tự gọi start() của component đó trong context refresh theo cơ chế SmartLifecycle auto-startup. Bạn có thể gọi **start() thủ công** ở một điểm được thiết kế hoặc khởi động lifecycle context qua API thích hợp.

Ví dụ consumer cần chờ cache đã preload:

~~~java
@Component
class ConsumerStarter implements ApplicationRunner {
    private final CacheWarmupService warmup;
    private final MessageConsumer consumer;

    ConsumerStarter(CacheWarmupService warmup, MessageConsumer consumer) {
        this.warmup = warmup;
        this.consumer = consumer;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmup.preload();
        consumer.start();
    }
}
~~~

**Đoạn này chỉ minh họa tổ chức code**, chưa chạy độc lập vì CacheWarmupService và MessageConsumer chưa được định nghĩa. Consumer phải có cơ chế start/stop thực sự và autoStartup=false.

Khi **gọi trực tiếp consumer.start()**, bạn đang kích hoạt một component cụ thể, không phải yêu cầu DefaultLifecycleProcessor tự start tất cả các bean khác theo getPhase(). Không đồng nhất phase ordering với một lời gọi thủ công đơn lẻ.

**Đừng dùng phase rất lớn để thay cho autoStartup=false.** Một SmartLifecycle phase Integer.MAX_VALUE vẫn có thể auto-start trong refresh, **trước ApplicationRunner**.

## 10. getPhase() không đợi công việc async mà start() tự tạo

Một component có thể triển khai:

~~~java
@Override
public void start() {
    executor.submit(this::connectToRemoteService);
    running = true;
}
~~~

Đây là mã minh họa, executor, connectToRemoteService và running phải được định nghĩa trong class.

Trong trường hợp đó, start() trả về sau khi **submit task**, nhưng kết nối thật có thể còn đang thiết lập. Một bean phase cao hơn có thể được Spring gọi start() trong khi task của bean phase thấp chưa hoàn thành.

Do đó phải phân biệt:

- **Order lời gọi:** start(A) được gọi trước start(B).
- **Trạng thái thực sự sẵn sàng:** A đã kết nối, khởi tạo dữ liệu hoặc xác minh dependency hay chưa.

Nếu B bắt buộc dùng A, có thể:

1. Để start(A) chờ đồng bộ đến khi A sẵn sàng với timeout.
2. B chỉ start sau khi một tín hiệu ready đáng tin cậy từ A đã hoàn tất.
3. Tách warm up bắt buộc sang runner rồi mới bật consumer có autoStartup=false.
4. Dùng state machine và health/readiness rõ ràng khi công việc không thể chặn startup.

Không dùng **Thread.sleep** làm cơ chế đồng bộ. Việc phase thấp start trước không phải lời hứa mọi tác vụ con của nó đã hoàn tất.

## 11. stop(Runnable callback) và shutdown theo chiều ngược

SmartLifecycle có hai dạng stop:

~~~java
void stop();
void stop(Runnable callback);
~~~

Khi DefaultLifecycleProcessor quản lý shutdown của SmartLifecycle, phương thức **stop(Runnable callback)** quan trọng vì nó cho biết component đã dừng xong và có thể tiếp tục phase sau.

Mẫu dừng đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Ví dụ ở mục 8 dùng pattern này. Callback luôn được gọi sau nỗ lực stop() để không khiến lifecycle processor chờ vô hạn. Một implementation nghiêm túc còn cần báo lỗi và xác nhận trạng thái tài nguyên; callback không được dùng để **tuyên bố dừng thành công khi resource vẫn đang chạy**.

Với shutdown bất đồng bộ, callback phải được gọi **khi công việc đóng thật sự kết thúc**, không ngay khi chỉ mới submit lệnh đóng.

Ví dụ pseudocode:

~~~java
@Override
public void stop(Runnable callback) {
    client.stopAsync().whenComplete((unused, failure) -> {
        try {
            if (failure != null) {
                log.error("Async stop failed", failure);
            }
            running = false;
        } finally {
            callback.run();
        }
    });
}
~~~

Ở đây client, log, running là thành phần giả định, chưa tạo thành một lớp chạy độc lập. Khi triển khai thật phải xử lý cả trường hợp **stopAsync() tự ném exception trước khi trả Future**, bảo đảm callback được báo đúng một lần theo contract và tránh bỏ lại tài nguyên không đóng.

**Thứ tự stop cao → thấp** làm hệ thống có thể dừng consumer trước, để worker xử lý nốt tác vụ đang chạy, sau đó mới đóng connection pool hoặc hạ tầng phase thấp.

### Timeout theo shutdown phase

Spring Boot 3.3 hỗ trợ:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Hoặc YAML:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Đây là **timeout mỗi phase khi đóng**, không phải khoảng thời gian chờ giữa các lần start và không phải giới hạn thời gian của toàn bộ JVM. Nếu component không gọi callback hoặc dừng quá lâu, shutdown có thể phải chờ hết ngân sách phase. Hãy xác định timeout I/O bên trong component và chính sách stop chủ động.

Lưu ý: **kill -9, mất điện hoặc JVM crash** có thể bỏ qua callback shutdown. Không coi graceful shutdown là cơ chế duy nhất bảo vệ dữ liệu hay giải phóng lease bên ngoài.

## 12. Làm thế nào để chọn giá trị phase?

Không có bộ số cố định cho mọi ứng dụng. Bạn có thể thiết kế dải theo tầng để dễ đọc:

| Tầng | Phase ví dụ | Start | Stop |
| --- | ---: | --- | --- |
| Hạ tầng nền phải tồn tại lâu nhất | -200 | Sớm nhất | Muộn nhất |
| Registry hoặc kết nối nền | -100 | Sau hạ tầng | Trước hạ tầng |
| Worker xử lý dữ liệu | 0 | Sau kết nối | Trước kết nối |
| Consumer nhận message | 100 | Sau worker | Trước worker |
| Adapter cấp phát/nhận việc mới | 200 | Sau cùng | Trước tiên |

Đây là **quy ước minh họa**, không phải giá trị Spring Boot bắt buộc. Các thư viện hạ tầng như web server, message listener container hoặc scheduler có thể mang phase riêng; cần xem API/config cụ thể trước khi chọn số cho component tùy chỉnh.

Hướng suy nghĩ tốt hơn việc chọn số ngẫu nhiên:

- **Ai cần tồn tại trước?** Đặt phase thấp hoặc khai báo phụ thuộc rõ.
- **Ai phải ngừng nhận công việc đầu tiên?** Đặt phase cao hơn tài nguyên mà nó dùng.
- **Ai cần chạy xuyên quá trình shutdown để giúp hoàn tất task?** Đặt phase thấp hơn consumer.
- **Có tài nguyên đã được Spring sở hữu lifecycle đúng?** Không cần bọc tất cả bằng một SmartLifecycle tùy chỉnh.
- **Có hai tác vụ chỉ quan hệ nghiệp vụ một lần trước ready?** Dùng runner hoặc coordinator, đừng ép getPhase giải bài toán của runner.

## 13. Khi start() hoặc refresh gặp lỗi

Giả sử:

~~~text
Infrastructure phase -100: start OK
Worker         phase    0: start OK
Consumer       phase  100: start FAILED
~~~

Nếu start() ném exception, context refresh có thể thất bại, SpringApplication không đạt tới runner hoặc ready. Nhưng không nên mặc định rằng mọi callback stop sẽ xảy ra như một lần graceful shutdown bình thường khi **refresh bị gián đoạn**.

Nguyên tắc cleanup:

1. Những tài nguyên đã được container quản lý phải có vòng đời đóng phù hợp.
2. Nếu start() **mở tài nguyên rồi lỗi khi đang khởi tạo**, component phải cleanup ngay trong try/catch hoặc try/finally của chính bước đã cấp phát.
3. Không dùng static initializer hoặc thread tự tạo rồi tin rằng lifecycle processor luôn đóng giúp khi startup sớm thất bại.
4. Exception quan trọng phải lan lên để SpringApplication nhận biết startup failure, thay vì catch rồi đặt running=true giả.
5. Với resource ngoài transaction, cần idempotency và bù trừ khi khởi động lại.

Pseudocode:

~~~java
@Override
public void start() {
    Resource resource = openResource();
    try {
        configure(resource);
        running = true;
    } catch (RuntimeException | Error failure) {
        try {
            resource.close();
        } catch (Exception closeFailure) {
            failure.addSuppressed(closeFailure);
        }
        throw failure;
    }
}
~~~

Resource, openResource và configure là API nghiệp vụ giả định. Ý nghĩa là **tự dọn phần tạo dở**, không chờ @PreDestroy hoặc stop() khi object chưa đạt trạng thái quản lý hoàn chỉnh.

Với lỗi runner xảy ra **sau khi refresh đã hoàn tất**, các SmartLifecycle auto-start có thể đã chạy và sẽ cần shutdown khi Spring Boot xử lý failure. Vì thế phải kiểm thử cả lỗi trong start() lẫn lỗi trong runner.

## 14. SmartLifecycle khác những hook gần nó thế nào?

| Cơ chế | Thời điểm | Dùng để làm gì? |
| --- | --- | --- |
| Constructor | Tạo đối tượng và invariant | Trạng thái cục bộ, kiểm tra dependency đầu vào |
| @PostConstruct/initMethod | Khi bean khởi tạo | Chuẩn bị state của chính bean |
| SmartLifecycle.start() | Trong lifecycle context, thường lúc refresh | Bắt đầu component dài hạn, có phase |
| SmartLifecycle.stop(Runnable) | Khi lifecycle processor đóng/dừng context | Dừng có thứ tự, hỗ trợ async shutdown |
| ApplicationRunner | Sau ApplicationStartedEvent, trước ApplicationReadyEvent | Công việc startup phải hoàn thành trước ready |
| CommandLineRunner | Cùng giai đoạn với ApplicationRunner | Xử lý startup với raw arguments |
| ApplicationStartedEvent | Sau context refresh | Quan sát mốc started |
| ApplicationReadyEvent | Sau runners | Quan sát mốc startup thành công |
| @PreDestroy | Khi bean được destroy | Giải phóng resource theo vòng đời bean |

**SmartLifecycle không tự thay thế các hook này.** Nếu chỉ cần validation property nhanh, constructor/@PostConstruct gọn hơn. Nếu chỉ cần preload cache trước ready, runner dễ hiểu hơn. Nếu consumer hoạt động liên tục và cần start/stop theo phase, SmartLifecycle hoặc listener container đã có của framework phù hợp.

## 15. Quan hệ phase với readiness

Trong chuỗi Spring Boot thông thường:

~~~text
Context refresh
    |
SmartLifecycle auto-start
    |
ApplicationStartedEvent
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
ReadinessState.ACCEPTING_TRAFFIC
~~~

Vì vậy một SmartLifecycle consumer có autoStartup=true có thể nhận message ngay trong quá trình refresh, trong khi readiness HTTP vẫn chưa chấp nhận traffic. Điều này không mâu thuẫn với API: **phase chỉ sắp thứ tự lifecycle**, còn readiness là trạng thái vận hành do Spring Boot công bố về sau.

Nếu hệ thống có yêu cầu “không xử lý message trước warm up”, phải chọn cơ chế phù hợp: autoStartup=false, start từ runner sau warm up, pause/resume hoặc kiểm tra điều kiện trước khi acknowledge. Cần xử lý retry, redelivery và backpressure theo semantics của broker; đừng đơn giản drop message khi chưa ready.

Điểm cần nhớ: **HTTP readiness probe không tự chặn Kafka/RabbitMQ consumer, scheduler hoặc thread tự tạo**. Nếu cần readiness cho nhiều nguồn công việc, thiết kế điều kiện phù hợp với từng nguồn.

## 16. Checklist kiểm thử phase

### 16.1. Thứ tự start

Ghi nhận thứ tự riêng các thông điệp:

~~~text
START_INFRA -> START_WORKER -> START_INPUT
~~~

Không assert log framework xen kẽ; chỉ so sánh những sự kiện do code chủ động ghi.

### 16.2. Thứ tự stop

Đóng context và xác nhận:

~~~text
STOP_INPUT -> STOP_WORKER -> STOP_INFRA
~~~

Kiểm tra callback hoàn tất ở mỗi phase và resource thật đã được đóng.

### 16.3. Hai bean cùng phase

Cho hai SmartLifecycle cùng getPhase()=10 và xác nhận **không viết test đòi thứ tự cố định**. Nếu thực tế cần thứ tự, sửa thiết kế bằng dependency hoặc tách phase.

### 16.4. Depends-on trái phase

B depends-on A nhưng phase B thấp hơn phase A. Xác nhận A vẫn start trước B, B stop trước A. Sau khi hiểu nguyên tắc, nên điều chỉnh phase để dễ đọc hơn.

### 16.5. Auto-start false

Kiểm tra bean không start khi refresh. Sau đó gọi start() từ runner hoặc coordinator; xác nhận isRunning() thay đổi hợp lý.

### 16.6. Async start

Cho start() chỉ submit Future và return; chứng minh phase cao hơn có thể start trước khi Future hoàn thành. Sau đó bổ sung barrier thật, timeout hoặc readiness gate.

### 16.7. Shutdown và failure

Thử stop(Runnable) dừng chậm, timeout phase, lỗi khi start() mở tài nguyên dở, runner thất bại sau refresh, dừng từ Kubernetes/IDE và resource leak. Không giả định kill -9 sẽ chạy callback.

## 17. Những lỗi phổ biến

**1. “Phase cao start trước.”** Sai. Phase thấp start trước.

**2. “Stop cũng thấp tới cao.”** Sai. Stop cao tới thấp.

**3. “Phase là số giây delay.”** Sai. Đó là thứ tự nhóm.

**4. “SmartLifecycle mặc định phase 0.”** Sai. SmartLifecycle.DEFAULT_PHASE = Integer.MAX_VALUE.

**5. “Một Lifecycle bình thường tự auto-start giống SmartLifecycle.”** Không. Cơ chế auto-start khi refresh dành cho SmartLifecycle có isAutoStartup=true.

**6. “@Order trên component thay cho getPhase.”** Sai khi DefaultLifecycleProcessor sắp lifecycle bean.

**7. “Hai bean cùng phase luôn theo tên class.”** Sai. Thứ tự nội bộ không được bảo đảm.

**8. “Depends-on không liên quan thứ tự stop.”** Sai. Dependent stop trước dependency.

**9. “Đặt consumer ở phase thật cao là đủ để chờ runner.”** Sai. Auto-start vẫn xảy ra trong refresh.

**10. “start() return tức là tác vụ async đã hoàn tất.”** Sai nếu chỉ mới submit task.

**11. “stop(Runnable) có thể không gọi callback khi dừng xong.”** Sai. Callback phải báo hoàn tất.

**12. “Chỉ cần callback.run() ngay sau khi gửi lệnh stop async.”** Sai. Callback phải thể hiện tiến trình dừng thực sự đã hoàn thành.

**13. “@Lazy chắc chắn làm SmartLifecycle không được khởi tạo lúc startup.”** Không bảo đảm. Hỗ trợ auto-start hạn chế ý nghĩa của lazy-init.

**14. “getPhase đồng bộ startup của các Pod trong cluster.”** Sai. Phạm vi là ApplicationContext riêng.

**15. “Một lỗi refresh chắc chắn dọn mọi resource giống graceful shutdown.”** Không thể mặc định; resource tạo dở cần cleanup cục bộ.

**16. “Dùng getPhase để sắp runner.”** Sai. Runner dùng @Order/Ordered hoặc coordinator theo nhu cầu.

## 18. Câu hỏi tự kiểm tra

**Câu 1:** A phase -50, B phase 0, C phase 200. Start theo thứ tự nào?  
**Đáp án:** A → B → C.

**Câu 2:** Khi đóng context, thứ tự dừng?  
**Đáp án:** C → B → A.

**Câu 3:** SmartLifecycle không override getPhase có phase mặc định?  
**Đáp án:** Integer.MAX_VALUE trong Spring Framework 6.1.

**Câu 4:** isAutoStartup() mặc định trả về gì?  
**Đáp án:** true.

**Câu 5:** Hai SmartLifecycle cùng phase 0 có bảo đảm chạy theo thứ tự bean name?  
**Đáp án:** Không.

**Câu 6:** B depends-on A nhưng B phase -100 và A phase 100. Bean nào start trước?  
**Đáp án:** A, vì depends-on được ưu tiên.

**Câu 7:** @Order(1) trên ApplicationRunner có làm nó chạy trước SmartLifecycle.start() không?  
**Đáp án:** Không. Runner nằm sau context refresh trong startup bình thường.

**Câu 8:** Consumer cần chờ cache preload trong runner. Đặt getPhase=Integer.MAX_VALUE đã đủ chưa?  
**Đáp án:** Chưa. Dùng autoStartup=false và start có kiểm soát sau warm up, hoặc gate tương đương.

**Câu 9:** Vì sao stop(Runnable) phải gọi callback sau khi dừng?  
**Đáp án:** LifecycleProcessor cần tín hiệu hoàn tất để điều phối shutdown phase.

**Câu 10:** start(A) được gọi trước start(B) có bảo đảm kết nối async do A mở đã sẵn sàng?  
**Đáp án:** Không. Cần một tín hiệu ready thực sự hoặc chờ có timeout.

**Câu 11:** Cấu hình timeout-per-shutdown-phase=20s dùng cho thời gian chờ giữa các lần start?  
**Đáp án:** Không. Nó giới hạn thời gian dừng theo phase.

**Câu 12:** Năm replica Kubernetes có phối hợp getPhase chung không?  
**Đáp án:** Không, mỗi ApplicationContext tự quản lý thứ tự riêng.

**Câu 13:** Nếu start() đã mở connection nhưng ném exception giữa chừng, ai phải cleanup?  
**Đáp án:** Component phải bảo đảm cleanup resource tạo dở tại chỗ; không chỉ trông chờ lifecycle callback.

**Kết luận:** **getPhase() quy định thứ tự SmartLifecycle start từ phase thấp tới cao và stop theo chiều cao tới thấp**. SmartLifecycle auto-start thường diễn ra trong refresh, trước runner; cùng phase không có thứ tự bảo đảm; dependency tường minh được ưu tiên. Khi triển khai hãy đặt phase phù hợp với quan hệ phụ thuộc, kiểm tra readiness thật, thực hiện stop(Runnable) đúng hợp đồng và thử cả startup failure lẫn shutdown.

### Tài liệu tham khảo

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot — Application Events and Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
