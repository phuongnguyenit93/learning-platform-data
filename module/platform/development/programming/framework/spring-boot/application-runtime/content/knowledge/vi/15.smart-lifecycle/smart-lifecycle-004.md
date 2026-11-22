# isAutoStartup và thành phần cần khởi động tường minh trong SmartLifecycle

Một Spring bean có thể **đã được tạo và tiêm dependency đầy đủ** nhưng **chưa được phép bắt đầu hoạt động**. Ví dụ: một message consumer chỉ được subscribe sau khi người vận hành phê duyệt; một polling job cần đợi cấu hình nghiệp vụ; một worker có thể được bật/tắt theo lệnh; hoặc một kết nối dài hạn không nên mở ngay khi context refresh.

`SmartLifecycle` là hợp đồng vòng đời của Spring Framework dành cho những component có thao tác **start**, **stop**, trạng thái **running** và thứ tự theo **phase**. Điểm quyết định trong bài này là phương thức:

~~~java
boolean isAutoStartup();
~~~

- Trả **`true`**: component đủ điều kiện được Spring tự gọi `start()` trong quá trình **refresh ApplicationContext**, theo cơ chế `LifecycleProcessor`.
- Trả **`false`**: không yêu cầu Spring tự khởi động component đó tại bước refresh; ứng dụng dự kiến gọi **`start()` tường minh** khi đạt điều kiện nghiệp vụ.

**Không nhầm:** `isAutoStartup() == false` **không ngăn Spring tạo bean**, không có nghĩa bean là lazy, không vô hiệu hóa lệnh `start()` của người khác và cũng không khiến ứng dụng mặc nhiên NotReady.

Các ví dụ dùng **Java 17+ và Spring Boot 3.3.x** (Spring Framework 6.1.x). Bản chất API thuộc Spring Framework nên không phụ thuộc việc ứng dụng dùng HTTP server hay chạy batch.

## 1. Hai trạng thái độc lập: bean đã tồn tại và worker đã chạy

Một singleton có thể trải qua các mốc:

~~~text
JVM / SpringApplication.run(...)
   |
   +-- Tạo ApplicationContext
   +-- Đăng ký bean definition
   +-- Tạo bean SmartLifecycle
   |      +-- constructor
   |      +-- dependency injection
   |      +-- @PostConstruct / init callbacks
   |
   +-- Context refresh -> LifecycleProcessor.onRefresh()
   |      |
   |      +-- isAutoStartup() == true:
   |      |      có thể gọi start() theo phase/dependency
   |      |
   |      +-- isAutoStartup() == false:
   |             không tự start vì riêng điều kiện này
   |
   +-- Context hoàn tất refresh
   +-- Spring Boot chạy ApplicationRunner/CommandLineRunner
   +-- ApplicationReadyEvent, run(...) trả về
   |
   +-- Khi điều kiện nghiệp vụ được đáp ứng:
          component.start() được gọi tường minh
~~~

Đây là mô hình khái niệm, không liệt kê mọi sự kiện của Spring Boot. Điều quan trọng là **bean initialization** và **lifecycle start** không phải một hành động.

Ví dụ, một bean có thể có:

~~~java
@PostConstruct
void initializeMetadata() {
    // Kiểm tra cấu hình, chuẩn bị trạng thái nội bộ.
}
~~~

Nhưng nếu `isAutoStartup()` trả `false` thì việc gọi `initializeMetadata()` trong quá trình tạo bean **không đồng nghĩa** một background consumer, polling loop hoặc listener đã chạy. Những công việc vận hành này nên do `start()` đảm nhiệm.

Phương thức `isRunning()` giúp người điều phối hỏi trạng thái **đang chạy theo hợp đồng component**, chứ không có nghĩa `ApplicationContext.isActive()` hay readiness probe phải có cùng giá trị.

## 2. SmartLifecycle mở rộng những hợp đồng nào?

Khai báo cơ bản của Spring Framework:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
    int getPhase();
}
~~~

Đoạn này mô tả hợp đồng, không phải một file Java cần tự biên dịch. `SmartLifecycle` kế thừa:

- `Lifecycle.start()`: yêu cầu component bắt đầu hoạt động.
- `Lifecycle.stop()`: yêu cầu component ngừng hoạt động.
- `Lifecycle.isRunning()`: cho biết component hiện có đang hoạt động hay không.
- `Phased.getPhase()`: cung cấp phase để Spring phối hợp **nhiều component**.
- `SmartLifecycle.isAutoStartup()`: quyết định **có tự start khi context refresh** hay không.
- `SmartLifecycle.stop(Runnable callback)`: hỗ trợ dừng không đồng bộ và thông báo khi đã hoàn tất.

Trong Spring Framework 6.1, hai mặc định quan trọng:

| Phương thức | Mặc định của SmartLifecycle | Ý nghĩa |
|---|---|---|
| `isAutoStartup()` | `true` | Nếu muốn component chạy thủ công, **phải override trả false**. |
| `getPhase()` | `Integer.MAX_VALUE` | Component SmartLifecycle mặc định thuộc phase rất muộn lúc start và rất sớm lúc stop. |

Để kiểm soát thứ tự vận hành, đừng phụ thuộc ngẫu nhiên vào thứ tự đăng ký bean; hãy khai báo phase và dependency cụ thể.

### So sánh Lifecycle và SmartLifecycle

| Đặc điểm | Chỉ implement `Lifecycle` | Implement `SmartLifecycle` |
|---|---|---|
| Có `start()`, `stop()`, `isRunning()` | Có | Có |
| Tự start khi context refresh | Không theo cơ chế SmartLifecycle auto-start | Có nếu `isAutoStartup() == true` |
| Điều khiển auto-start bằng `isAutoStartup()` | Không có API này | Có |
| Thứ tự phase | Thường được processor xem như phase `0` | Có `getPhase()`, mặc định MAX_VALUE |
| Dừng bất đồng bộ với callback | Không có theo interface này | Có `stop(Runnable)` |

Nếu không cần auto-start và chỉ muốn start thủ công, implement `Lifecycle` cũng có thể phù hợp. Nếu cần phase ordering, callback shutdown hay chế độ auto-start cấu hình được, `SmartLifecycle` đem lại hợp đồng rõ ràng hơn.

## 3. Ví dụ Java 17+ chạy được: một auto worker và một manual worker

Mục tiêu: khi `SpringApplication.run(...)` hoàn tất, **worker tự khởi động** đang chạy nhưng **worker thủ công** chưa chạy. Sau đó main gọi `manual.start()`, quan sát trạng thái rồi dừng worker. Khi context đóng, Spring dừng worker tự khởi động còn chạy.

Ví dụ dùng project console Spring Boot có `spring-boot-starter`, không khởi động HTTP server để kết quả dễ đối chiếu.

Tạo file:

`src/main/java/com/example/lifecycle/ManualSmartLifecycleApplication.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManualSmartLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ManualSmartLifecycleApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            ManagedWorker auto =
                    context.getBean("autoWorker", ManagedWorker.class);
            ManagedWorker manual =
                    context.getBean("manualWorker", ManagedWorker.class);

            System.out.println(
                    "After run: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());

            // Chỉ một worker được bật bằng lệnh tường minh.
            manual.start();
            System.out.println(
                    "After manual.start: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());

            // start() được thiết kế idempotent.
            manual.start();
            System.out.println(
                    "After repeated start: manual=" + manual.isRunning());

            manual.stop();
            System.out.println(
                    "After manual.stop: auto=" + auto.isRunning()
                            + ", manual=" + manual.isRunning());
        }
        // try-with-resources đóng ApplicationContext và stop autoWorker.
    }

    @Bean
    ManagedWorker autoWorker() {
        return new ManagedWorker("auto", true);
    }

    @Bean
    ManagedWorker manualWorker() {
        return new ManagedWorker("manual", false);
    }

    public static final class ManagedWorker implements SmartLifecycle {

        private final String name;
        private final boolean autoStartup;
        private final AtomicBoolean running = new AtomicBoolean();

        public ManagedWorker(String name, boolean autoStartup) {
            this.name = name;
            this.autoStartup = autoStartup;
        }

        @Override
        public boolean isAutoStartup() {
            return autoStartup;
        }

        @Override
        public int getPhase() {
            return 0;
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("start " + name);
                // Ở production: khởi chạy nguồn công việc thật.
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("stop " + name);
                // Ở production: dừng nguồn công việc, thu hồi tài nguyên.
            }
        }

        @Override
        public void stop(Runnable callback) {
            try {
                stop();
            } finally {
                // Phải báo hoàn tất để LifecycleProcessor không chờ vô ích.
                callback.run();
            }
        }
    }
}
~~~

**Lưu ý về class:** `ManagedWorker` là nested static class, không được đánh dấu `@Component`; nó chỉ trở thành Spring bean thông qua đúng hai factory method `@Bean`. Vì vậy không vô tình có worker thứ ba do component scanning.

### Cấu hình chạy bằng Gradle

Nếu cần cấu hình project mới, `build.gradle` tối thiểu:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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

springBoot {
    mainClass = 'com.example.lifecycle.ManualSmartLifecycleApplication'
}
~~~

Chạy từ thư mục project đã có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Với dự án Maven đã dùng Spring Boot Maven plugin, cũng có thể chạy `./mvnw spring-boot:run` khi main class phù hợp được xác định. Vì code dùng Spring Boot/Spring Framework nên không thể biên dịch độc lập bằng `javac ManualSmartLifecycleApplication.java` nếu thiếu các dependency trên classpath.

### Output của chính ví dụ

Bỏ qua banner và log do Spring Boot in ra, các dòng mà **mã Java trên chủ động in** sẽ theo thứ tự:

~~~text
start auto
After run: auto=true, manual=false
start manual
After manual.start: auto=true, manual=true
After repeated start: manual=true
stop manual
After manual.stop: auto=true, manual=false
stop auto
~~~

Giải thích:

1. Khi refresh, `LifecycleProcessor` nhìn thấy `autoWorker.isAutoStartup() == true` nên gọi `start()` của worker đó; dòng `start auto` xuất hiện trước khi `app.run(args)` trả về.
2. `manualWorker.isAutoStartup() == false` nên không được auto-start tại refresh. Bean **đã tồn tại**, nhưng `manual.isRunning() == false`.
3. `manual.start()` là lời gọi Java trực tiếp, bật worker thủ công. Lần gọi thứ hai không in thêm `start manual` vì ví dụ dùng `AtomicBoolean.compareAndSet(...)` bảo đảm start lặp không làm khởi động lại.
4. `manual.stop()` chuyển worker thủ công về trạng thái không chạy.
5. Khi ra khỏi `try-with-resources`, `context.close()` yêu cầu lifecycle processor dừng những component còn hoạt động. `autoWorker` còn chạy nên in `stop auto`; `manualWorker` đã dừng nên không in thêm.

Điểm giới hạn: `AtomicBoolean` chỉ giúp trạng thái của ví dụ đơn giản và thread-safe ở mức chuyển cờ. Trong production, việc thực sự tạo/dừng thread, consumer hoặc connection phải được đồng bộ với trạng thái; **đừng đặt cờ running=true rồi coi mọi khởi động bất đồng bộ đều thành công**.

## 4. isAutoStartup=false không đồng nghĩa bean không được tạo

Đây là nhầm lẫn phổ biến nhất.

| Sự kiện | Với manualWorker trong ví dụ |
|---|---|
| Spring ghi nhận bean definition | Có |
| Spring tạo singleton bean | Có, theo cơ chế singleton non-lazy thông thường |
| Dependency injection, `@PostConstruct`/init method nếu có | Vẫn diễn ra |
| `isAutoStartup()` được hỏi khi context refresh | Có thể được lifecycle processor sử dụng |
| Tự gọi `start()` khi refresh | Không, vì trả `false` |
| Có thể lấy bean qua `getBean(...)` | Có |
| Có thể tự gọi `start()` sau refresh | Có |
| Có thể bị dừng khi context đóng nếu đang chạy | Có |

Vì sao phải phân biệt? Có trường hợp người viết đặt `isAutoStartup=false` nhưng constructor hoặc `@PostConstruct` đã mở connection, subscribe message broker, start timer hoặc tạo thread. Khi ấy component **vẫn gây side effect ngay lúc bean initialization**, dù `start()` chưa bao giờ được gọi.

Thiết kế đúng là:

- **Constructor / bean initialization:** lưu cấu hình, nhận dependency, chuẩn bị các object không hoạt động.
- **`start()`:** mở consumer, bắt đầu polling, đăng ký listener, tạo hoặc kích hoạt workload theo hợp đồng.
- **`stop()` / `stop(Runnable)`:** ngừng nhận việc mới, dừng workload, hoàn tất hoặc hủy những công việc còn lại theo chính sách và thu hồi tài nguyên.
- **`isRunning()`:** phản ánh đúng trạng thái mà caller và lifecycle processor có thể sử dụng.

Đừng cố dùng `@Lazy` thay thế cho `isAutoStartup(false)`. Với `SmartLifecycle`, Spring có thể phải khởi tạo bean trong lúc xử lý lifecycle của context, nên lazy-init flag có **hiệu lực hạn chế**, như Javadoc của framework đã cảnh báo. Hai cấu hình giải quyết hai mục tiêu khác nhau.

## 5. Start thủ công bằng bean.start() hoặc context.start()

Có **hai phạm vi khởi động tường minh** khác nhau:

### Cách A — Khởi động đúng một bean

~~~java
ManagedWorker manual =
        context.getBean("manualWorker", ManagedWorker.class);

if (!manual.isRunning()) {
    manual.start();
}
~~~

Đây là đoạn đặt trong chương trình đã có các biến và class của ví dụ mục 3, không phải file độc lập.

Lợi ích: **chọn chính xác** worker nào được bật; các worker khác không nhất thiết bị tác động. Thích hợp với command có tên, feature switch, công việc đòi phê duyệt hoặc API điều phối nội bộ.

Nhược điểm: gọi trực tiếp `start()` không có nghĩa Spring sắp xếp lại toàn bộ phase của các component liên quan. Code phải bảo đảm dependency đã sẵn sàng, handle exception và tuân thủ nguyên tắc không gọi start đồng thời nhiều lần ngoài ý muốn.

### Cách B — Khởi động toàn bộ context

~~~java
context.start();
~~~

`ConfigurableApplicationContext.start()` ủy quyền cho `LifecycleProcessor` của context để khởi động các bean `Lifecycle` theo quy trình của container. Khi gọi **tường minh** như vậy, processor không chỉ giới hạn ở những `SmartLifecycle` có `isAutoStartup() == true`. Một component có `isAutoStartup() == false` cũng có thể được khởi động.

**Đây là điểm rất dễ bỏ sót:** `isAutoStartup=false` ngăn auto-start trong lúc **refresh**, nhưng không phải “khóa cứng” chống mọi lời gọi `context.start()` sau đó.

So sánh:

| Thao tác | Phạm vi | Có thể làm manual worker chạy? |
|---|---|---|
| `ApplicationContext.refresh()` | Refresh container, có callback auto-start | Không do riêng auto-start flag, nếu `false` |
| `manualWorker.start()` | Chính bean được gọi | **Có** |
| `context.start()` | Lifecycle components trong context | **Có** |
| Lời gọi từ code khác tới `manualWorker.start()` | Chính bean được gọi | **Có** |
| `context.close()` | Shutdown và destroy context | Không dùng để bắt đầu worker |

**Lưu ý quan hệ dependency:** lifecycle processor cũng xét các quan hệ phụ thuộc rõ ràng. Một bean với `isAutoStartup=false` không phải luôn được cô lập tuyệt đối khỏi những dependency chain có component tự khởi động. Nếu cấu hình `depends-on` hoặc một lifecycle bean khác cần worker đó, hãy kiểm chứng thứ tự thực tế và tránh xem boolean này là cơ chế kiểm soát quyền truy cập.

Nếu muốn **bật từng consumer riêng lẻ**, gọi đúng bean `start()` qua một bộ điều phối nội bộ thường chính xác hơn `context.start()`.

## 6. isAutoStartup khác getPhase như thế nào?

Hai phương thức trả lời **hai câu hỏi khác nhau**:

- `isAutoStartup()`: **Có nên tự chạy tại context refresh không?**
- `getPhase()`: **Khi container điều phối start/stop nhiều component, component này nằm ở thứ tự nào?**

Với những lifecycle bean cần start tự động:

~~~text
START (từ phase thấp lên cao):
  phase -100  -> kết nối nền tảng
  phase    0  -> thành phần phụ thuộc
  phase  100  -> consumer tiếp nhận công việc

STOP (từ phase cao xuống thấp):
  phase  100  -> dừng nhận việc mới
  phase    0  -> dừng xử lý
  phase -100  -> đóng kết nối nền tảng
~~~

Đây là **ví dụ thiết kế thứ tự**, không có nghĩa tất cả hệ thống đều bắt buộc dùng các số trên.

Javadoc của Spring Framework cho biết:

- Startup đi từ phase **nhỏ đến lớn**.
- Shutdown đi theo thứ tự **ngược lại**.
- Các component cùng phase không nên dựa vào thứ tự ổn định giữa chúng.
- Quan hệ `depends-on` được khai báo tường minh có thể được ưu tiên hơn phase.
- `SmartLifecycle` mặc định dùng `Integer.MAX_VALUE`, trong khi `Lifecycle` thông thường không triển khai `SmartLifecycle` được coi như phase `0`.

**Quan trọng:** Khi gọi `manualWorker.start()` trực tiếp, việc đặt phase bằng 100 **không khiến container tự khởi động các component phase nhỏ hơn trước lời gọi Java này**. Phase là một phần của cơ chế điều phối container; để chủ động bật một worker riêng lẻ, caller phải bảo đảm các dependency đã sẵn sàng.

Ví dụ mục 3 override `getPhase()` trả `0` để tránh phụ thuộc vào giá trị mặc định cực lớn, chứ không cần dùng phase để xác định output. Khi chỉ có một bean auto-start, không có cạnh tranh thứ tự start giữa các auto worker trong ví dụ.

## 7. Khởi động có điều kiện sau refresh bằng ApplicationRunner

Một mô hình thực tế là: **worker phải được tạo sẵn, nhưng chỉ được chạy khi startup arguments hợp lệ**.

Với Spring Boot, `ApplicationRunner` chạy **sau khi context đã refresh** và trước khi quá trình startup bình thường hoàn tất. Nó có thể đọc `ApplicationArguments` rồi gọi `start()` của worker thủ công.

Ví dụ, thay vì gọi trong `main` như mục 3, bạn có thể bổ sung bean sau **vào class cấu hình Spring**, với các import tương ứng:

~~~java
@Bean
ApplicationRunner enableManualWorker(
        @Qualifier("manualWorker") ManagedWorker worker) {
    return args -> {
        if (args.containsOption("enable-manual-worker")) {
            worker.start();
        }
    };
}
~~~

Cần import `org.springframework.boot.ApplicationRunner` và `org.springframework.beans.factory.annotation.Qualifier`. Đoạn này **là phương án thay thế**, không nằm trong chương trình mục 3, vì thêm nó sẽ thay đổi thời điểm `manualWorker` được start và thay đổi stdout đã mô tả.

Chạy với:

~~~bash
./gradlew bootRun --args='--enable-manual-worker'
~~~

Lúc này chính runner quyết định start worker dựa trên flag. `ApplicationRunner` vẫn được gọi sau refresh; `isAutoStartup() == false` khiến worker không chạy trước khi runner ra quyết định theo cơ chế auto-start thông thường.

Có hai lưu ý:

1. Nếu worker được bật **bởi runner**, lần startup chỉ được coi là bình thường hoàn tất khi runner kết thúc. Nếu runner ném exception thì Boot có thể thất bại trong startup.
2. Nếu yêu cầu là **một người vận hành bật worker lúc bất kỳ trong runtime**, runner không phù hợp vì runner chạy trong chuỗi startup; cần một bộ điều phối nội bộ có bảo vệ, một message command hoặc một giao diện quản trị kiểm soát quyền.

Không nên mở một endpoint công khai `POST /start-worker` cho bất kỳ client nào gọi mà không có xác thực, phân quyền, giới hạn tần suất và audit.

## 8. Bật muộn hơn ApplicationReadyEvent

Đôi khi component không được phép tự start khi refresh, cũng không được bật ngay trong runner, mà chỉ sau một sự kiện nghiệp vụ.

Ví dụ:

- Phải chờ phê duyệt một cấu hình.
- Phải kiểm tra khóa giữ leader trước khi nhận message.
- Phải chờ một quá trình data migration riêng hoàn thành.
- Phải thỏa điều kiện an toàn vận hành hoặc quota.
- Chỉ một node trong cụm được phép chạy một scheduler.

Lúc này hãy dùng logic điều phối **tách khỏi lifecycle callback**:

~~~text
ApplicationContext refresh xong
      |
      v
SmartLifecycle manual: running=false
      |
      v
Điều kiện nghiệp vụ được xác nhận
      |
      v
Bộ điều phối gọi manual.start()
      |
      v
manual.isRunning() == true
      |
      v
Được yêu cầu dừng -> manual.stop()
~~~

Chọn nguồn điều khiển phù hợp với hệ thống: config/state nội bộ, command queue có xác thực, leader election hoặc API quản trị được bảo vệ. Nếu điều kiện có thể thay đổi liên tục, cần quy tắc chống start/stop lặp quá nhanh, ghi nhận trạng thái mong muốn, retry/backoff và kiểm soát chạy đồng thời.

Đừng mặc định `ApplicationReadyEvent` là một công tắc khởi động mọi thứ: đó là sự kiện về startup bình thường của Spring Boot, không phải cơ chế phê duyệt nghiệp vụ. Tương tự, đọc `ApplicationAvailability.ReadinessState.ACCEPTING_TRAFFIC` chỉ cho biết trạng thái readiness hiện tại, **không đảm bảo worker thủ công đã chạy**, trừ khi bạn thiết kế health/readiness contract có xét worker.

## 9. Stop và shutdown callback vẫn rất quan trọng

Một worker chỉ được start thủ công **vẫn cần** hợp đồng stop đúng. Khi context đóng, Spring Framework sử dụng `LifecycleProcessor` để ngừng các lifecycle component còn chạy theo thứ tự phù hợp.

`SmartLifecycle.stop(Runnable callback)` phục vụ trường hợp dừng bất đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    // Yêu cầu worker ngừng nhận việc.
    // Khi đã dừng thật sự và thu hồi tài nguyên:
    callback.run();
}
~~~

Đây là sơ đồ phương thức minh họa, không phải implementation bất đồng bộ hoàn chỉnh. Đừng đặt `callback.run()` ngay sau thao tác **chỉ gửi yêu cầu stop** nếu công việc thực sự vẫn đang chạy và bạn muốn lifecycle processor chờ nó hoàn tất.

Quy tắc:

- **Luôn gọi callback** sau khi dừng hoàn tất. Nếu callback không được gọi, lifecycle processor có thể chờ cho tới timeout của phase, khiến shutdown kéo dài.
- Khi dừng đồng bộ, có thể dùng như ví dụ mục 3: gọi `stop()` rồi `callback.run()` trong `finally`.
- Với dừng bất đồng bộ, callback phải được gọi đúng lúc công việc thực tế đã dừng. Cần xử lý cả đường thất bại hoặc timeout của task shutdown.
- Đừng chỉ override `stop()` mà bỏ qua ý nghĩa của `stop(Runnable)`. Khi lifecycle processor dừng `SmartLifecycle`, nó sử dụng biến thể **nhận callback**.
- Nếu `isRunning() == false`, processor thường không cần gọi stop lên component đó khi đóng context. Đừng dựa vào stop để dọn dẹp thứ bạn đã cấp phát ngay từ constructor dù component chưa từng start.

Một ví dụ bất đồng bộ sử dụng executor do ứng dụng quản lý cần cân nhắc: thread/executor chịu trách nhiệm dừng có thể cũng đang được shutdown theo phase. Nếu không có đường đảm bảo callback, ứng dụng có thể treo khi kết thúc.

### Ví dụ cách viết stop đồng bộ an toàn

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();  // Đồng bộ dừng công việc và cập nhật running.
    } finally {
        callback.run();
    }
}
~~~

Ở ví dụ mục 3, việc dừng chỉ đổi cờ `AtomicBoolean` nên hoàn thành tức thì. Với một message listener hoặc thread pool thật, `stop()` phải thực sự dừng hoặc chờ đủ điều kiện theo chính sách, thay vì chỉ đặt `running=false` rồi bỏ mặc các thread còn làm việc.

## 10. isAutoStartup=false và lazy initialization không giống nhau

Hai cấu hình thường bị nhầm:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

và:

~~~java
@Lazy
@Bean
ManagedWorker manualWorker() {
    return new ManagedWorker("manual", false);
}
~~~

Đoạn thứ hai chỉ là cách khai báo bean thay thế trong cấu hình và cần import `org.springframework.context.annotation.Lazy`; không phải phương án thay thế hoàn toàn cho lời gọi đầu tiên.

| Cơ chế | Điều khiển |
|---|---|
| `@Lazy` | Thời điểm container **khởi tạo đối tượng bean** theo cơ chế lazy initialization. |
| `isAutoStartup()` | Việc lifecycle processor **tự start component khi refresh**. |
| `getPhase()` | Thứ tự start/stop khi container điều phối lifecycle. |
| `isRunning()` | Trạng thái vận hành hiện tại của component. |

Do auto-start/lifecycle discovery, Spring Framework cảnh báo rằng lazy-init flag chỉ có tác dụng hạn chế với bean `SmartLifecycle`. Vì thế nếu mục tiêu là **ngăn thực thi công việc**, điều quan trọng hơn là giữ constructor/initialization **không gây side effect khởi động** và bảo vệ logic trong `start()`.

Nếu chi phí tạo bean cũng quá lớn, cần thiết kế riêng việc tạo tài nguyên nặng khi `start()` hoặc sử dụng một component factory phù hợp; không nên suy đoán `@Lazy` kết hợp `isAutoStartup=false` sẽ chắc chắn khiến object không được tạo.

## 11. Một worker được start thủ công có thể bị start gián tiếp?

Có. Boolean `isAutoStartup=false` chỉ mô tả lựa chọn trong giai đoạn **auto-start của lifecycle processor khi refresh**, không phải ranh giới bảo mật. Một số đường khiến worker có thể vẫn chạy:

- Code khác giữ reference và gọi `worker.start()`.
- Bộ điều phối gọi `context.start()`, khiến processor start các lifecycle bean trong context.
- Một component tự khởi động có quan hệ phụ thuộc lifecycle rõ ràng với worker; việc xử lý dependencies có thể kích hoạt worker như một phần chuỗi start. Cần kiểm tra cấu hình `depends-on` và thứ tự thực tế.
- Một method initialization (constructor, `@PostConstruct` hoặc `@Bean(initMethod=...)`) tự khởi tạo thread/client từ sớm, bỏ qua ý nghĩa của `SmartLifecycle.start()`.
- Một listener/runner do ứng dụng viết tự gọi start mà chưa xét điều kiện quản trị.

Nếu start worker phải được kiểm soát nghiêm ngặt, hãy bảo vệ **điểm gọi start** bằng logic ứng dụng: xác thực quyền, kiểm tra trạng thái mong muốn, xác minh dependency, leader lease và audit. `isAutoStartup=false` chỉ là chính sách mặc định về startup, không phải một khóa an toàn.

## 12. Kiểm thử trạng thái trước và sau khi bật

Khi kiểm thử, đừng chỉ khẳng định bean có trong context. Hãy kiểm tra cả trạng thái running trước và sau thao tác.

Ví dụ unit test đơn giản **không cần Spring container** cho logic tự viết của `ManagedWorker` trong mục 3:

~~~java
ManagedWorker worker = new ManagedWorker("test", false);

assert !worker.isRunning();

worker.start();
assert worker.isRunning();

worker.start(); // Không chạy start lần thứ hai trong ví dụ này.
assert worker.isRunning();

worker.stop();
assert !worker.isRunning();
~~~

Đây là đoạn minh họa trong cùng package hoặc class có quyền truy cập `ManagedWorker` và cần bật JVM assertions bằng `-ea` nếu dùng `assert`. Vì không có container, đoạn này **không kiểm tra isAutoStartup khi context refresh**.

Với một integration test chạy Spring Boot, kiểm chứng bằng các ý tưởng:

1. Context refresh xong, gọi `getBean("manualWorker")`.
2. Xác nhận bean tồn tại nhưng `isRunning() == false`.
3. Xác nhận `autoWorker.isRunning() == true`.
4. Gọi `manualWorker.start()`, xác nhận chuyển thành `true`.
5. Gọi `manualWorker.stop()`, xác nhận chuyển thành `false`.
6. Đóng context, bảo đảm những component vẫn chạy được stop và tài nguyên đã được thu hồi.

Khi cần test `context.start()`, dùng **một test riêng** vì nó có thể start nhiều lifecycle bean chứ không riêng manual worker. Đừng gộp thao tác này vào test cần chứng minh manual worker vẫn đứng yên.

## 13. Sự khác biệt giữa auto-start, readiness và phục vụ traffic

Một Spring Boot application có thể báo readiness là **ACCEPTING_TRAFFIC** trong khi một SmartLifecycle manual component đang **không chạy**. Đây chưa chắc là bug:

- Nếu worker là một tính năng optional, readiness chung có thể vẫn đúng.
- Nếu worker là thành phần bắt buộc cho mọi request, cần thiết kế readiness phản ánh điều kiện đó.
- Nếu worker là một consumer nền chỉ một node trong cụm được phép chạy, việc nhiều Pod có `isRunning=false` hoàn toàn có thể đúng.

Vì vậy không nên ngầm diễn giải `isRunning=false` thành “app chết” hoặc ép liveness probe thất bại. Hãy tách:

| Câu hỏi | Cơ chế phù hợp |
|---|---|
| Spring bean đã được container tạo chưa? | BeanFactory / bean initialization. |
| Worker hiện có đang hoạt động không? | `SmartLifecycle.isRunning()` cộng trạng thái nghiệp vụ thực. |
| Worker có tự start khi refresh không? | `SmartLifecycle.isAutoStartup()`. |
| ApplicationContext còn active không? | `ConfigurableApplicationContext.isActive()`. |
| Instance có nên nhận traffic mới không? | Readiness state/health probe được thiết kế theo yêu cầu. |
| Process có hỏng không thể tự hồi phục không? | Liveness state/health probe, không đơn giản là running của một worker optional. |

Một listener chưa được bật vì chờ leader election **không đồng nghĩa JVM hỏng**. Thực tế, việc không bật nó trước khi giữ leader lease mới là hành vi đúng.

## 14. Lỗi thường gặp và cách tránh

**Lỗi 1 — “isAutoStartup=false nghĩa là Spring không tạo bean”.**

Sai. Với singleton thông thường, constructor, dependency injection và init callback vẫn xảy ra. Chỉ auto-start của `SmartLifecycle` khi refresh bị tắt.

**Lỗi 2 — “SmartLifecycle mặc định không tự chạy”.**

Sai. Trong Spring Framework 6.1, `SmartLifecycle.isAutoStartup()` mặc định trả **true**. Muốn manual start, cần override rõ ràng.

**Lỗi 3 — “Đặt getPhase() rất lớn sẽ làm worker không chạy”.**

Không. Phase quyết định thứ tự khi start/stop, **không thay thế** `isAutoStartup()`. Nếu cần không auto-start, trả `false`.

**Lỗi 4 — “Đã đặt false thì context.start() cũng bỏ qua worker”.**

Sai. `context.start()` là hành động khởi động lifecycle **tường minh trên toàn context**, khác với callback `onRefresh()` chỉ chọn auto-start candidates.

**Lỗi 5 — “start() chỉ được gọi đúng một lần trong đời”.**

Không được bảo đảm. Code có thể start lại sau stop hoặc gọi lặp. Hãy làm `start()` idempotent ở mức cần thiết, đồng bộ đúng, và handle lỗi khởi động.

**Lỗi 6 — “Chỉ cần @Lazy là worker không chạy”.**

Không chắc. SmartLifecycle có cơ chế phát hiện và quản lý lifecycle riêng; `@Lazy` có hiệu quả hạn chế với loại bean này.

**Lỗi 7 — “Một lệnh manual.start() sẽ tự tuân thủ mọi phase”.**

Không. Gọi trực tiếp là lời gọi vào một bean. Caller phải kiểm tra dependency và trạng thái; phase có ý nghĩa khi container điều phối.

**Lỗi 8 — “Chỉ override stop(), không cần quan tâm stop(Runnable)”.**

Dễ gây shutdown không đúng kỳ vọng. LifecycleProcessor dùng biến thể có callback khi dừng SmartLifecycle; callback phải được phát sau khi dừng thực sự hoàn tất.

**Lỗi 9 — “isRunning() chỉ cần trả true sau khi nhận yêu cầu start”.**

Không chính xác nếu nguồn công việc chưa sẵn sàng hoặc start đã thất bại. Hãy thiết kế trạng thái nhất quán giữa start/stop và readiness thực tế của worker.

**Lỗi 10 — “Thấy worker chưa chạy thì liveness phải fail”.**

Không mặc nhiên. Worker có thể đang chờ điều kiện nghiệp vụ, optional hoặc chỉ được chạy trên node leader. Liveness là vấn đề phục hồi của process, không phải cờ start của một component.

## 15. Checklist thiết kế worker manual-start trong production

- Bean được tạo và cấu hình **không tự start** ở constructor hoặc `@PostConstruct`.
- `isAutoStartup()` trả `false` một cách tường minh và có chú thích lý do.
- `start()` kiểm tra điều kiện, idempotent, thread-safe và báo lỗi khi không thể khởi động.
- `isRunning()` phản ánh trạng thái thực, không chỉ yêu cầu start đã được gửi.
- `stop()` chấm dứt nhận việc và thu hồi tài nguyên theo chính sách; `stop(Runnable)` gọi callback sau khi dừng hoàn tất.
- Phân biệt code điều phối **một bean** với `context.start()` khởi động **nhiều bean**.
- Kiểm soát `@DependsOn`, phase và những callback có thể làm worker start gián tiếp.
- Khi khởi động chậm hoặc có phụ thuộc bên ngoài, dùng timeout, retry/backoff, logging và metrics.
- Test trạng thái sau refresh, sau start, sau stop và sau context close.
- Không mở quyền bật/tắt worker qua endpoint công khai không bảo vệ.
- Readiness/liveness phản ánh mục tiêu điều phối ứng dụng, không gắn một-một với cờ `isRunning()` nếu worker là optional.

### Tài liệu tham khảo

- Spring Framework 6.1 — `SmartLifecycle` Javadoc (mặc định, phase, stop callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `Lifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework — Bean lifecycle và `LifecycleProcessor`: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — `SpringApplication`, runners và lifecycle: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Ghi nhớ:** `SmartLifecycle.isAutoStartup() == false` không làm bean biến mất và không cấm việc start. Nó chỉ nói rằng **không tự gọi start khi ApplicationContext refresh** theo cơ chế auto-start thông thường. Một component cần bật theo điều kiện phải có **lệnh start tường minh**, quản lý trạng thái và shutdown đúng; gọi `context.start()` là tác động toàn context, không tương đương chỉ bật một worker.
