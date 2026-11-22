# Giới hạn bảo đảm thứ tự giữa các thành phần cùng phase trong SmartLifecycle

## Mục tiêu học tập

Trong Spring Framework và Spring Boot, `SmartLifecycle` giúp các thành phần có trạng thái *start/stop* tham gia vòng đời của `ApplicationContext`. Mỗi thành phần có thể trả về một số nguyên từ `getPhase()` để Spring điều phối **theo nhóm phase**. Tuy nhiên, việc cùng trả về một phase **không thiết lập một thứ tự chạy cố định giữa các thành phần đó**.

Đây là điểm đặc biệt quan trọng với các hệ thống có connection, message consumer, scheduler, worker, listener hoặc tiến trình xử lý dữ liệu: nếu consumer cần một kết nối đã hoạt động, bạn không thể chỉ đặt cả hai cùng phase rồi mong Bean A luôn được start trước Bean B.

Sau bài học, bạn sẽ:

1. Hiểu chính xác thứ tự giữa **các phase khác nhau** và giới hạn đối với **những bean cùng phase**.
2. Phân biệt thời điểm **tạo bean**, **gọi `start()`**, **hoàn tất khởi động nghiệp vụ** và **gọi `stop(Runnable)`**.
3. Hiểu vì sao `@Order`, thứ tự khai báo `@Bean`, component scanning và tên bean không thay thế được hợp đồng lifecycle.
4. Biết sử dụng `@DependsOn` để thiết lập ràng buộc bắt buộc giữa hai thành phần, kể cả khi chúng cùng phase.
5. Viết được `SmartLifecycle` với `getPhase()`, `isAutoStartup()`, `start()`, `isRunning()`, `stop()` và `stop(Runnable)` đúng vòng đời.
6. Chạy một dự án Java 17+ / Spring Boot 3.3.13 chứng minh **quy tắc trước–sau được bảo đảm** mà không kiểm thử thứ tự ngẫu nhiên trong cùng phase.
7. Thiết kế startup/shutdown an toàn cho các tài nguyên thực tế, hiểu giới hạn của async start/stop, timeout và readiness.

**Bối cảnh:** Spring Boot Application Runtime → SmartLifecycle. Giải thích API theo Spring Framework **6.1.x** và Spring Boot **3.3.x**. Những phiên bản Spring Framework mới hơn có thêm tùy chọn triển khai như concurrent startup theo phase; đừng mặc định chúng có trong 6.1.

## 1. SmartLifecycle có nhiệm vụ gì?

Spring có interface `Lifecycle` để biểu diễn một thành phần có thể bắt đầu và dừng:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Đây là **chữ ký minh họa**, không phải file phải tự tạo; interface thật ở `org.springframework.context.Lifecycle`.

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`, cung cấp thêm khả năng tự khởi động khi context refresh và callback khi dừng:

~~~java
public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
~~~

Chữ ký trên cũng được rút gọn để học; interface thật nằm trong `org.springframework.context.SmartLifecycle` và các phương thức có default implementation tùy phiên bản.

Một bean `SmartLifecycle` có thể được `DefaultLifecycleProcessor` điều phối:

- Khi application context **refresh**, các bean auto-startup thích hợp được yêu cầu start.
- Khi application context **close**, các bean đang chạy được yêu cầu stop theo quy tắc phase và dependency.
- Khi gọi lifecycle operation tường minh qua `ConfigurableApplicationContext`, processor xử lý các lifecycle beans liên quan theo hợp đồng của nó.

`SmartLifecycle` thường phù hợp với thành phần **giữ tài nguyên hoặc có vòng đời làm việc liên tục**, chẳng hạn client connection manager, event consumer, thread-based worker hoặc receiver. Không nên biến mọi service stateless chỉ có method business thành `SmartLifecycle`.

### Ba điều không được đồng nhất

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Bean initialization | Spring tạo object, inject dependencies, chạy init callbacks | Constructor, `@PostConstruct` |
| Lifecycle startup | Spring gọi `SmartLifecycle.start()` | Bắt đầu nhận thông điệp, mở consumer, start scheduler |
| Business readiness | Thành phần **thực sự sẵn sàng** làm việc theo tiêu chí nghiệp vụ | Kết nối đã handshake, subscription đã active |

Một bean có thể **được tạo rồi** nhưng `isRunning() == false`. Và một bean có thể được đánh dấu running sau khi submit tác vụ chạy nền, trong khi kết nối nghiệp vụ chưa hoàn tất. Phase chỉ điều phối **lời gọi lifecycle**, không tự xác thực tài nguyên ngoài đã sẵn sàng.

## 2. Quy tắc thứ tự giữa các phase khác nhau

Theo hợp đồng `SmartLifecycle.getPhase()`:

- **Khởi động:** giá trị phase **nhỏ trước, lớn sau**.
- **Dừng:** giá trị phase **lớn trước, nhỏ sau**.
- Giá trị phase là `int`; có thể âm, bằng 0 hoặc dương.
- Nếu hai bean có phase khác nhau mà không có ràng buộc dependency mâu thuẫn, thứ tự được thể hiện bằng các nhóm phase.

Ví dụ:

~~~text
             KHỞI ĐỘNG
                  |
     phase -100: connection factory
                  |
      phase   0: message dispatcher
                  |
      phase 100: public consumer
                  |
              Running
                  |
               DỪNG
                  |
      phase 100: public consumer
                  |
      phase   0: message dispatcher
                  |
     phase -100: connection factory
~~~

Ý nghĩa kiến trúc: một thành phần hỗ trợ bên dưới thường start sớm và stop muộn; thành phần tiêu thụ ở trên thường start sau và stop trước. Vì vậy phase tạo một **thứ tự giữa nhóm**, không tự mô tả toàn bộ dependency graph.

### Phân biệt phase mặc định

| Loại bean lifecycle | Phase mặc định thường gặp trong Spring Framework 6.1 |
| --- | --- |
| `SmartLifecycle` nếu không override `getPhase()` | `SmartLifecycle.DEFAULT_PHASE` = `Integer.MAX_VALUE` |
| `Lifecycle` thông thường, không triển khai `Phased` | Được processor xem như phase `0` |
| `SmartLifecycle` override `getPhase()` | Giá trị `int` do ứng dụng chỉ định |

Bean `SmartLifecycle` mặc định thường ở phase rất cao để được auto-start muộn và auto-stop sớm hơn các lifecycle bean phase thấp. Nhưng **đừng giả định giá trị 0 là mặc định của SmartLifecycle**: nó là mặc định được áp dụng cho `Lifecycle` thông thường theo processor.

Với các component của framework, có thể đã có phase riêng. Không chọn giá trị phase cho ứng dụng mà không biết component liên quan có nằm trong cùng `ApplicationContext` và tham gia cùng lifecycle processor không.

## 3. Cùng phase không có thứ tự được bảo đảm

Đây là trọng tâm của bài.

Giả sử ba thành phần độc lập:

~~~text
Bean A → getPhase() = 0
Bean B → getPhase() = 0
Bean C → getPhase() = 0
~~~

Spring bảo đảm chúng thuộc **cùng nhóm phase** so với các nhóm khác, nhưng **không cam kết A, B, C start theo alphabet, thứ tự source code, thứ tự scan hay thứ tự tạo bean**.

Những thứ tự quan sát được đều có thể phù hợp hợp đồng nếu không có dependency:

~~~text
Lần chạy 1: start(A), start(B), start(C)
Lần chạy 2: start(C), start(A), start(B)
Lần chạy 3: start(B), start(C), start(A)
~~~

Đây là **ba kịch bản minh họa hợp lệ**, không phải khẳng định rằng mỗi lần chạy thực tế Spring sẽ ngẫu nhiên đảo thứ tự. Trên một bản cài đặt cụ thể, thứ tự có thể ổn định qua nhiều lần chạy do cấu trúc dữ liệu nội bộ. **Ổn định do tình cờ không biến nó thành cam kết API.**

Tương tự ở shutdown, những bean độc lập cùng phase không được cấp một thứ tự tuyệt đối theo hợp đồng `SmartLifecycle`. Quan hệ phase đảo ngược trên mức **nhóm** không nói “Bean C chắc chắn stop trước B, rồi B trước A” nếu ba bean cùng phase.

### Hợp đồng đúng và suy diễn sai

| Khẳng định | Đánh giá |
| --- | --- |
| Phase `-100` được start trước phase `0`, nếu không có depends-on đảo quan hệ | Đúng |
| Phase `100` được stop trước phase `0`, nếu không có depends-on đảo quan hệ | Đúng |
| Cùng phase thì Spring start theo tên bean A→Z | **Không được bảo đảm** |
| Cùng phase thì Spring start theo thứ tự khai báo `@Bean` | **Không được bảo đảm** |
| Cùng phase thì thứ tự stop luôn đảo chính xác thứ tự start đã thấy trong log | **Không được bảo đảm** |
| Có quan hệ `@DependsOn` tường minh, dependency start trước dependent | Đúng theo hợp đồng |
| Có `@DependsOn`, dependent stop trước dependency | Đúng theo hợp đồng |
| Thêm `@Order(1)` lên bean SmartLifecycle là cách chuẩn đặt thứ tự start | **Không**; sử dụng phase hoặc dependency |
| `start()` được gọi trước nghĩa là tài nguyên ngoài đã operational | Chưa chắc; phụ thuộc implementation `start()` |

### Vì sao cùng phase dễ gây lỗi?

Ví dụ:

- Bean `ConnectionPoolManager` phải kết nối thành công **trước** bean `QueueConsumer` bắt đầu nhận message.
- Cả hai trả `getPhase() == 0`.
- Nếu không mô tả dependency, Spring không có hợp đồng buộc `ConnectionPoolManager.start()` phải được gọi trước `QueueConsumer.start()`.
- Một deployment quan sát thấy chạy đúng nhiều lần vẫn có thể lỗi sau khi nâng phiên bản framework, thêm module, thay đổi cách đăng ký bean hoặc chuyển sang context topology khác.

**Nếu thứ tự là bất biến nghiệp vụ, phải thiết kế một ràng buộc được framework công nhận**; không dựa vào nhật ký một lần chạy.

## 4. @DependsOn: ràng buộc tường minh trong cùng phase

Spring Framework định nghĩa rõ: một quan hệ **depends-on tường minh** được ưu tiên hơn phase ordering. Bean phụ thuộc được **start sau** dependency và **stop trước** dependency.

Ví dụ:

~~~java
@Bean("queueConnection")
SmartLifecycle queueConnection() {
    return new QueueConnectionLifecycle();
}

@Bean("queueConsumer")
@DependsOn("queueConnection")
SmartLifecycle queueConsumer() {
    return new QueueConsumerLifecycle();
}
~~~

Đây là **đoạn minh họa cấu hình**, không phải project đầy đủ: cần định nghĩa các class lifecycle và import `Bean`/`DependsOn`/`SmartLifecycle`. Giả sử cả hai có phase `0`, Spring vẫn có quan hệ:

~~~text
START: queueConnection → queueConsumer
STOP : queueConsumer   → queueConnection
~~~

`@DependsOn("queueConnection")` ở đây dựa trên **tên bean** `queueConnection`, không phải tên Java class. Sai tên bean có thể gây lỗi tạo bean; cần giữ tên rõ và kiểm tra khi refactor.

### Dependency và các nhóm phase không mâu thuẫn thế nào?

Trường hợp tốt nhất là:

~~~text
phase -100: queueConnection
phase    0: queueConsumer, @DependsOn("queueConnection")
~~~

Phase và dependency đều chỉ về một hướng: connection start trước consumer; consumer stop trước connection.

Nếu gán phase ngược nhưng vẫn đặt `@DependsOn`, hợp đồng `SmartLifecycle` nêu **depends-on có ưu tiên so với phase**. Dù vậy đó là thiết kế dễ gây khó đọc; nên chọn phase sao cho phản ánh dependency graph thay vì cố tình để hai cơ chế mâu thuẫn.

### @DependsOn còn ảnh hưởng initialization

`@DependsOn` không chỉ nói về `SmartLifecycle.start()`. Nó cũng thể hiện quan hệ khởi tạo giữa các bean definitions: dependency cần được Spring xử lý trước dependent khi tạo bean. Vì vậy:

- Có thể làm một bean vốn lazy bị yêu cầu sớm.
- Có thể thay đổi thời điểm constructor/`@PostConstruct`.
- Là công cụ tường minh khi cần ràng buộc **khởi tạo và vòng đời**.
- Không nên đặt bừa vào hàng chục bean để cưỡng ép một chuỗi không cần thiết.

**Phân biệt constructor injection và @DependsOn:** constructor injection nêu một dependency thực tế về object để bean có thể xây dựng; `@DependsOn` hữu ích khi có một quan hệ khởi động không biểu diễn tự nhiên bằng constructor parameter, ví dụ một hạ tầng phải start trước nhưng consumer không cần gọi trực tiếp object đó. Nếu có thể làm dependency thực sự rõ ràng qua interface được inject thì thường dễ bảo trì hơn.

## 5. @Order không phải công cụ sắp thứ tự SmartLifecycle

Spring có `@Order`/`Ordered` cho nhiều mục đích: thứ tự các strategy beans trong collection, một số callback, startup runners hoặc aspects. Nhưng **không phải mọi cơ chế dùng `@Order` đều tác động đến lifecycle processor**.

Ví dụ:

~~~java
@Component
@Order(1)
class FirstConsumer implements SmartLifecycle {
    // ...
}

@Component
@Order(2)
class SecondConsumer implements SmartLifecycle {
    // ...
}
~~~

Đây là các class **minh họa một phần**, chưa đủ phương thức để compile độc lập. Không được suy luận từ `@Order(1)` và `@Order(2)` rằng `FirstConsumer.start()` luôn chạy trước `SecondConsumer.start()` nếu cả hai có cùng phase và không có dependency.

**Để điều khiển thứ tự lifecycle:**

- **Quan hệ giữa các nhóm:** override `getPhase()` trả về các số khác nhau.
- **Quan hệ bắt buộc giữa các bean:** mô tả dependency rõ ràng, ví dụ `@DependsOn`.
- **Chuỗi bước có điều kiện/rollback phức tạp:** cân nhắc một component điều phối lifecycle hoặc orchestration service, thay vì nhiều bean ngang hàng dựa vào thứ tự vô tình.

### Tên bean và vị trí @Bean cũng không tạo hợp đồng

Với:

~~~java
@Bean SmartLifecycle alpha() { /* ... */ }
@Bean SmartLifecycle beta()  { /* ... */ }
~~~

Viết `alpha` trước `beta` trong cùng file Java không phải hợp đồng yêu cầu `alpha.start()` phải trước `beta.start()`. Nếu cần chứng minh thứ tự, hãy gắn phase khác nhau hoặc dependency.

### @Priority không giải quyết thay phase

Một số cơ chế Spring cũng tôn trọng `@Priority`. Không nên dùng nó như hợp đồng `SmartLifecycle` khi docs của `SmartLifecycle` đã xác định rõ phase và depends-on. Việc một annotation ảnh hưởng đến **thứ tự injection list** không đồng nghĩa nó ảnh hưởng đến **thứ tự start/stop**.

## 6. isAutoStartup và thời điểm start

`SmartLifecycle.isAutoStartup()` trả về `true` theo mặc định trong Spring Framework 6.1. Khi context refresh, `DefaultLifecycleProcessor` tìm các SmartLifecycle beans và yêu cầu các thành phần thích hợp khởi động.

Nếu một bean trả `false`:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

thì nó không được tự động start trong pha refresh chỉ vì là SmartLifecycle. Nó có thể được start thông qua một thao tác lifecycle tường minh phù hợp. Nếu một thành phần cần luôn sẵn sàng ngay khi Boot đạt ready, hãy xác định chiến lược khởi động của nó rõ ràng thay vì vô tình tắt auto-startup.

**Chú ý:** SmartLifecycle beans thường vẫn được **khởi tạo instance** để lifecycle processor khảo sát và quản lý, kể cả khi một bean definition có lazy-init. Vì vậy `@Lazy` không phải một công cụ đáng tin để trì hoãn mọi SmartLifecycle bean trong runtime. Việc bean được tạo và việc callback `start()` được gọi là hai mốc khác nhau.

### Default phase không phải 0

Mặc định `SmartLifecycle.getPhase()` trả `Integer.MAX_VALUE` (theo `DEFAULT_PHASE`), nên các bean SmartLifecycle không override phase thường thuộc nhóm rất muộn lúc startup và rất sớm lúc shutdown. Nếu muốn đồng nhất một nhóm, **override getPhase() rõ ràng** thay vì ngầm dựa vào 0.

Điều này đặc biệt quan trọng khi bạn có một `Lifecycle` thường (được xem như phase 0) và một `SmartLifecycle` mặc định (phase MAX_VALUE). Chúng không tự nhiên ở cùng phase.

## 7. Ví dụ hoàn chỉnh: kiểm thử quan hệ bắt buộc, không đoán thứ tự cùng phase

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.13** và Gradle. Đây là ứng dụng **non-web**: nó tạo năm bean `SmartLifecycle` và một bean ghi nhận sự kiện, xác minh ràng buộc trong lúc startup, sau đó đóng context để xác minh chiều ngược khi shutdown.

Năm thành phần:

| Bean name | Phase | Dependency tường minh | Ý nghĩa |
| --- | --- | --- | --- |
| `storage` | `-100` | Không | Tài nguyên nền tảng |
| `alpha` | `0` | Không | Worker A |
| `beta` | `0` | `@DependsOn("alpha")` | Worker B, phải chạy sau A |
| `gamma` | `0` | Không | Worker độc lập trong cùng phase |
| `api` | `100` | Không | Thành phần lớp trên |

**Những thứ cần chứng minh:**

1. Start: `storage` trước `alpha`/`beta`/`gamma`, ba bean phase `0` trước `api`.
2. Start: `alpha` trước `beta` nhờ `@DependsOn`.
3. Stop: `api` trước ba bean phase `0`, các bean phase `0` trước `storage`.
4. Stop: `beta` trước `alpha` nhờ quan hệ dependency đảo chiều.
5. **Không kiểm tra `gamma` bắt buộc nằm trước/sau `alpha` hoặc `beta`**: đó chính là giới hạn hợp đồng của cùng phase.

### 7.1. Cấu trúc thư mục

~~~text
smart-lifecycle-phase-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/phase/
    ├── PhaseDemoApplication.java
    ├── DemoLifecycle.java
    └── LifecycleTrace.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'smart-lifecycle-phase-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.phase.PhaseDemoApplication'
}
~~~

Project không cần web starter. Gradle sử dụng phải tương thích Spring Boot 3.3 và JDK 17. Nếu dependency chưa cache thì Gradle cần tải từ Maven Central.

### 7.2. Lớp SmartLifecycle thực hiện start/stop

**`src/main/java/com/example/phase/DemoLifecycle.java`:**

~~~java
package com.example.phase;

import org.springframework.context.SmartLifecycle;

public final class DemoLifecycle implements SmartLifecycle {

    private final String id;
    private final int phase;
    private final LifecycleTrace trace;

    private volatile boolean running;

    public DemoLifecycle(String id, int phase, LifecycleTrace trace) {
        this.id = id;
        this.phase = phase;
        this.trace = trace;
    }

    @Override
    public synchronized void start() {
        if (!running) {
            running = true;
            trace.record("start:" + id);
        }
    }

    @Override
    public synchronized void stop() {
        if (running) {
            running = false;
            trace.record("stop:" + id);
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
            // Báo cho LifecycleProcessor biết stop đã kết thúc.
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
~~~

**Tại sao code này không phụ thuộc thứ tự ngẫu nhiên?**

- `id` và `phase` được truyền tường minh vào constructor.
- `start()` và `stop()` chỉ ghi dấu khi trạng thái thay đổi; các phương thức có thể gọi lại mà không in trùng trong tình huống thông thường.
- `running` là `volatile` để những thread khác nhìn thấy thay đổi trạng thái; `synchronized` bảo vệ cập nhật trong demo. Nó không thay cho thiết kế thread-safe đối với tài nguyên ngoài.
- `stop(Runnable)` gọi `stop()` rồi luôn gọi callback trong `finally`. Vì `stop()` trong demo hoàn tất **đồng bộ**, đây là thời điểm hợp lệ để thông báo lifecycle processor.
- `getPhase()` trả đúng giá trị được cấp, không dựa vào default `Integer.MAX_VALUE`.
- `isAutoStartup() == true` cho phép tự khởi động khi context refresh.

Một dự án thật phải bảo đảm trong `start()`/`stop()` rằng resource tương ứng đã đạt đúng trạng thái trước khi đổi `running`. Ở đây không có network resource, nên việc thay đổi trạng thái là tức thời.

### 7.3. Lớp ghi sự kiện và kiểm tra partial order

**`src/main/java/com/example/phase/LifecycleTrace.java`:**

~~~java
package com.example.phase;

import java.util.ArrayList;
import java.util.List;

public final class LifecycleTrace {

    private final List<String> events = new ArrayList<>();

    public synchronized void record(String event) {
        events.add(event);
    }

    public synchronized void verifyStartup() {
        before("start:storage", "start:alpha");
        before("start:storage", "start:beta");
        before("start:storage", "start:gamma");

        before("start:alpha", "start:beta");

        before("start:alpha", "start:api");
        before("start:beta", "start:api");
        before("start:gamma", "start:api");
    }

    public synchronized void verifyShutdown() {
        before("stop:api", "stop:alpha");
        before("stop:api", "stop:beta");
        before("stop:api", "stop:gamma");

        before("stop:beta", "stop:alpha");

        before("stop:alpha", "stop:storage");
        before("stop:beta", "stop:storage");
        before("stop:gamma", "stop:storage");
    }

    private void before(String first, String second) {
        int i = events.indexOf(first);
        int j = events.indexOf(second);

        if (i < 0 || j < 0 || i >= j) {
            throw new IllegalStateException(
                    "Expected " + first + " before " + second
                    + "; events=" + events);
        }
    }
}
~~~

Hàm `before(...)` so sánh **vị trí hai mốc** trong danh sách, không cần chúng liên tiếp. Nhờ đó:

- Kiểm tra các ràng buộc do phase và depends-on bảo đảm.
- **Không** bắt `gamma` phải chạy trước hoặc sau `alpha`/`beta`.
- Không đòi toàn bộ event trace phải giống một chuỗi cố định.
- Không phụ thuộc thứ tự bean definitions/đường duyệt của processor.
- Khi thiếu một event hoặc có quan hệ trước–sau sai, ném exception với chuỗi event để dễ chẩn đoán.

Vì `LifecycleTrace` là một bean thường, nó có thể được inject vào các `DemoLifecycle`. Trace chỉ lưu string trong memory cho ví dụ; hệ thống thật nên dùng structured logging/metrics thay vì tích lũy events vô hạn.

### 7.4. Định nghĩa bean và phụ thuộc cùng phase

**`src/main/java/com/example/phase/PhaseDemoApplication.java`:**

~~~java
package com.example.phase;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;

@SpringBootApplication
public class PhaseDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PhaseDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        LifecycleTrace trace = null;

        try (ConfigurableApplicationContext context = app.run(args)) {
            trace = context.getBean(LifecycleTrace.class);
            trace.verifyStartup();
            System.out.println("CHECK: STARTUP PASS");
        }

        if (trace == null) {
            throw new IllegalStateException("LifecycleTrace unavailable");
        }

        trace.verifyShutdown();
        System.out.println("CHECK: SHUTDOWN PASS");
    }

    @Bean
    LifecycleTrace lifecycleTrace() {
        return new LifecycleTrace();
    }

    @Bean
    DemoLifecycle storage(LifecycleTrace trace) {
        return new DemoLifecycle("storage", -100, trace);
    }

    @Bean
    DemoLifecycle alpha(LifecycleTrace trace) {
        return new DemoLifecycle("alpha", 0, trace);
    }

    @Bean
    @DependsOn("alpha")
    DemoLifecycle beta(LifecycleTrace trace) {
        return new DemoLifecycle("beta", 0, trace);
    }

    @Bean
    DemoLifecycle gamma(LifecycleTrace trace) {
        return new DemoLifecycle("gamma", 0, trace);
    }

    @Bean
    DemoLifecycle api(LifecycleTrace trace) {
        return new DemoLifecycle("api", 100, trace);
    }
}
~~~

Lưu ý:

- Mỗi factory method `@Bean` tạo đúng một `DemoLifecycle` với bean name từ tên method: `storage`, `alpha`, `beta`, `gamma` và `api`.
- `beta` mang `@DependsOn("alpha")`. Cả hai đều phase `0`, nên không thể giải thích thứ tự `alpha → beta` bằng việc so sánh phase; **dependency** mới là lý do.
- `gamma` cũng phase `0` nhưng không có dependency tới `alpha` hay `beta`. Do đó ví dụ cố ý **không** kiểm tra vị trí tương đối của nó.
- `storage` ở phase `-100`; `api` ở phase `100`. Quan hệ phase bảo đảm các nhóm thấp/higher theo đúng chiều start/stop.
- `LifecycleTrace` là bean thường không triển khai `SmartLifecycle`, nên nó không xuất hiện như một lifecycle member riêng trong các phép kiểm tra.
- `try-with-resources` đóng `ConfigurableApplicationContext` khi hết khối. Nhờ đó processor gọi stop và `verifyShutdown()` có thể kiểm tra. **Không đóng context ngay sau startup trong ứng dụng web chạy dài hạn**; cách viết này chỉ dùng cho CLI demo.

### 7.5. Chạy chương trình

Từ thư mục `smart-lifecycle-phase-demo`:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows. Ví dụ không tự tạo wrapper; cần Gradle cài sẵn hoặc tạo wrapper riêng cho project.

Bỏ qua các dòng của Gradle và Spring Boot, **hai dòng do mã ứng dụng chủ động in ra** là:

~~~text
CHECK: STARTUP PASS
CHECK: SHUTDOWN PASS
~~~

Điều này **không có nghĩa** toàn bộ event trace có thứ tự duy nhất. Ngược lại, chương trình chỉ in thành công khi **mọi quan hệ bắt buộc được kiểm tra** đều đúng, dù thứ tự tương đối của `gamma` so với `alpha`/`beta` có thể khác.

### 7.6. Vì sao đây là kiểm thử tốt hơn so sánh một danh sách log cố định?

Một kiểm thử sai có thể viết:

~~~java
assertEquals(
    List.of("start:storage", "start:alpha", "start:beta",
            "start:gamma", "start:api"),
    actualStartupEvents);
~~~

Đây là **mã test minh họa không độc lập**. Nó cố tình áp đặt `gamma` phải sau `beta`, trong khi cả ba nằm cùng phase và `gamma` không có dependency. Nếu test pass trên máy hôm nay, nó vẫn kiểm tra **hành vi không được API bảo đảm**.

Kiểm thử đúng xác nhận các ràng buộc:

~~~text
start(storage) < start(alpha)
start(storage) < start(beta)
start(storage) < start(gamma)
start(alpha)   < start(beta)       [@DependsOn]
start(alpha)   < start(api)
start(beta)    < start(api)
start(gamma)   < start(api)
~~~

Tương tự shutdown:

~~~text
stop(api)   < stop(alpha)
stop(api)   < stop(beta)
stop(api)   < stop(gamma)
stop(beta)  < stop(alpha)          [@DependsOn]
stop(alpha) < stop(storage)
stop(beta)  < stop(storage)
stop(gamma) < stop(storage)
~~~

Trong hai bảng trên, dấu `<` biểu thị “xảy ra trước” (*happens-before về mặt thứ tự log trong demo*), không phải toán tử so sánh chuỗi Java hay một bảo đảm memory-order tổng quát. Với async stop, cần phân biệt **lúc stop được gọi** và **lúc việc dừng thực sự hoàn tất**.

### 7.7. Ba biến thể để tự thử

**Biến thể 1 — Bỏ @DependsOn ở beta.**

Xóa annotation:

~~~java
@DependsOn("alpha")
~~~

Đây là dòng được **xóa khỏi cấu hình demo**, không phải một class mới. Khi đó `alpha` và `beta` đều phase `0`, không còn quan hệ được khai báo. `verifyStartup()`/`verifyShutdown()` vẫn đòi `alpha → beta` / `beta → alpha`, nên giờ chúng **có thể** fail, hoặc **có thể tình cờ vẫn pass** trên một lượt chạy. Cả hai kết quả đều không khôi phục cam kết API đã mất.

**Biến thể 2 — Đổi phase beta thành 10 và bỏ @DependsOn.**

~~~java
@Bean
DemoLifecycle beta(LifecycleTrace trace) {
    return new DemoLifecycle("beta", 10, trace);
}
~~~

Đây là phương thức thay thế phương thức `beta(...)` gốc. Khi đó phase ordering bảo đảm `alpha` (phase 0) start trước `beta` (phase 10), và `beta` stop trước `alpha`. Nhưng `gamma` vẫn phase 0, nên cũng được start trước `beta`, không còn độc lập cùng phase với beta.

**Biến thể 3 — Đổi gamma thành phase 0 với cùng order annotation.**

Thêm một `@Order` lên `gamma` mà **không** đổi phase và dependency. Đây không phải cách được hợp đồng `SmartLifecycle` xác nhận để buộc `gamma` start trước các peer phase 0. Nếu test có thay đổi kết quả, đó không phải chứng cứ `@Order` là lifecycle ordering API.

## 8. Khi nào cần dùng phase, khi nào cần @DependsOn?

### Dùng phase cho các tầng vận hành

Một hệ thống message processing có các tầng:

~~~text
phase -200: transport / connection resources
phase -100: codec / shared receiver infrastructure
phase    0: consumer workers
phase  100: HTTP adapter cho phép tiếp nhận công việc
~~~

Chọn phase giúp biểu diễn quan hệ **tầng trên/tầng dưới**. Không cần thiết phân biệt từng worker cùng phase nếu chúng độc lập và có thể start/stop theo bất cứ thứ tự nào.

Phase thích hợp khi bạn biết rằng một **loại** thành phần nên start trước loại khác, ngay cả khi các bean không inject trực tiếp vào nhau.

### Dùng @DependsOn cho quan hệ bắt buộc giữa các bean

Ví dụ worker `invoiceConsumer` bắt buộc chỉ start sau `schemaRegistryClient`, nhưng hai thành phần được quản lý cùng group 0 vì lý do vận hành:

~~~java
@Bean
@DependsOn("schemaRegistryClient")
SmartLifecycle invoiceConsumer() {
    return new InvoiceConsumerLifecycle();
}
~~~

Đây là **đoạn minh họa**, cần class và imports phù hợp. Nó đặt ra quan hệ trực tiếp, không yêu cầu đẩy toàn bộ consumer khác sang phase 1.

### Dùng orchestration cho nhiều bước phức tạp

Nếu pipeline phải làm:

1. Xác thực cấu hình.
2. Mở connection.
3. Khôi phục checkpoint.
4. Subscribe topic.
5. Chờ initial partition assignment.
6. Chỉ sau đó mới mở traffic.

Chỉ tăng các số phase có thể chưa đủ vì `start()` có thể bất đồng bộ, có retry hoặc rollback. Một orchestration service/SmartLifecycle điều phối các bước có trạng thái rõ ràng, timeout và readiness riêng thường dễ test hơn so với cố gắng biến mười peer cùng phase thành một chuỗi phụ thuộc rối.

**Mấu chốt:** Phase mô tả **thứ tự nhóm**, dependency mô tả **thứ tự bắt buộc**, còn readiness mô tả **khả năng thật sự làm việc**. Ba thứ không tự thay thế nhau.

## 9. Startup synchronous và asynchronous: điều gì thực sự được bảo đảm?

Trong một `SmartLifecycle` đơn giản, `start()` có thể chỉ khởi động một thread:

~~~java
@Override
public void start() {
    executor.execute(this::connectAndSubscribe);
    running = true;
}
~~~

Đây là **đoạn minh họa không hoàn chỉnh**, giả sử có `executor`, `connectAndSubscribe` và `running`. Nó thể hiện một lỗi thiết kế dễ gặp: `start()` trả về **trước khi** `connectAndSubscribe()` hoàn tất. Lifecycle processor có thể chuyển sang thành phần tiếp theo theo phase/depends-on, nhưng thành phần đầu chưa operational.

Ví dụ:

~~~text
10:00:00.000 start(ConnectionManager) được gọi
10:00:00.001 ConnectionManager submit kết nối async, return
10:00:00.002 start(MessageConsumer) được gọi theo depends-on
10:00:00.250 ConnectionManager hoàn tất connect/handshake
~~~

Những thời gian trên chỉ **minh họa**, không phải số đo hay quy tắc thực tế của Spring. Thứ tự lời gọi start vẫn đúng, nhưng `MessageConsumer` có thể tới quá sớm nếu nó đòi connection phải thật sự sẵn sàng.

### Giải pháp

- Nếu khởi động thành phần bắt buộc phải thành công trước component khác, cho `start()` **đợi điều kiện ready có giới hạn thời gian** rồi mới trả về, hoặc điều phối việc chờ trong một cơ chế khởi động phù hợp.
- Nếu start không thể blocking, cung cấp readiness signal/Future và để dependent component hoặc một orchestrator chỉ kích hoạt khi điều kiện hoàn tất.
- Phân biệt trạng thái “lệnh start đã gửi” với “consumer đã subscribe” hoặc “connection handshake thành công”.
- Đặt timeouts và error handling cho network; không dùng `while(true)` vô hạn khi startup.
- Nếu có lỗi nghiêm trọng, phải quyết định thất bại startup, retry hữu hạn hay vào trạng thái degraded có quan sát được.
- Không dùng một field `boolean running` đặt `true` ngay sau `executor.submit` làm bằng chứng đã sẵn sàng phục vụ.

### Khác biệt phiên bản với startup concurrency

Trong **Spring Framework 6.1**, các group lifecycle được xử lý theo phase và hợp đồng nội bộ của `DefaultLifecycleProcessor`. Các bản **6.2** có thêm tùy chọn cấu hình concurrent startup cho những phase nhất định. Không sao chép API `setConcurrentStartupForPhases(...)` từ 6.2 vào project Boot 3.3/Framework 6.1 mà chưa thay dependency; và ngay cả khi startup concurrent có cấu hình, vẫn không được suy luận thứ tự peer cùng phase là cố định.

## 10. stop(Runnable): một phase có thể phải đợi các thành phần cùng hoàn tất

Ở shutdown, `SmartLifecycle.stop(Runnable callback)` được processor gọi để hỗ trợ **dừng bất đồng bộ**. Callback phải chạy **sau khi** thành phần đã dừng thật sự; processor sử dụng callback để biết tiến trình shutdown của nhóm.

Ví dụ đồng bộ từ project mục 7:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // Hoàn tất trước khi trả về
    }
    finally {
        callback.run();
    }
}
~~~

Cách này hợp lệ khi `stop()` thực sự dừng xong resource. Với shutdown bất đồng bộ, **không** gọi `callback.run()` ngay sau khi submit task nếu tài nguyên vẫn đang được giải phóng.

### Mẫu minh họa async stop

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            closeConnectionsAndWait();
        }
        finally {
            running = false;
            callback.run();
        }
    });
}
~~~

Đây là **đoạn minh họa một phần**, cần `executor`, `closeConnectionsAndWait()`, `running` và cơ chế xử lý trường hợp `executor.execute(...)` bị từ chối. Một triển khai production cần bảo đảm callback luôn được kích hoạt đúng một lần trên các đường thành công/thất bại phù hợp và không che giấu tài nguyên chưa giải phóng.

**Phải phân biệt:** “lời gọi `stop(Runnable)` đã được thực hiện” ≠ “resource stop đã hoàn tất”. Với các bean **cùng phase**, quá trình dừng có thể liên quan nhiều callback/chờ trong cùng nhóm; không được giả định một thứ tự hoàn tất tuyệt đối giữa các peer độc lập.

### Timeout shutdown theo nhóm phase

Trong Spring Framework 6.1, `DefaultLifecycleProcessor` có cấu hình `setTimeoutPerShutdownPhase(long)`; giá trị mặc định theo Javadoc 6.1 là **30.000 ms (30 giây)** cho mỗi nhóm phase. Nếu callback không được gọi đúng lúc, shutdown có thể bị trì hoãn đến timeout thay vì chờ vô hạn.

Một cấu hình minh họa:

~~~java
@Bean(name = "lifecycleProcessor")
DefaultLifecycleProcessor lifecycleProcessor() {
    DefaultLifecycleProcessor processor =
            new DefaultLifecycleProcessor();
    processor.setTimeoutPerShutdownPhase(15_000);
    return processor;
}
~~~

Đây là **đoạn cấu hình bổ sung**, không phải một phần của project mục 7; cần imports `Bean` và `org.springframework.context.support.DefaultLifecycleProcessor`. Đặt bean tên `lifecycleProcessor` có ý nghĩa đặc biệt với `ApplicationContext`; chỉ thay khi bạn hiểu ảnh hưởng tới toàn bộ lifecycle beans của context.

**Không nhầm timeout shutdown của Framework 6.1 với giá trị mặc định hay API mới ở 6.2/7.x.** Cấu hình phiên bản chạy thật phải được kiểm tra trước khi thay đổi.

### @DependsOn trong shutdown

Nếu `beta` depends-on `alpha`, Spring yêu cầu `beta` **dừng trước** `alpha`. Đặc biệt với các bean cùng phase, đây là quan hệ quan trọng để bảo đảm consumer ngừng nhận việc trước khi producer/shared infrastructure được giải phóng.

Nhưng thứ tự **yêu cầu dừng** và **thực sự ngừng mọi background thread** chỉ trùng nhau khi implementation thực hiện đúng contract và callback. Nếu `beta.stop(Runnable)` gọi callback quá sớm, `alpha` có thể được dừng tiếp khi `beta` thực tế vẫn đang xử lý message; đây là **lỗi implementation**, không phải lỗi phase ordering.

## 11. Lifecycle không giống bean destruction hoặc startup runner

Nhiều callback cùng diễn ra trong vòng đời ứng dụng nhưng có contract khác nhau:

| Hook | Khi chạy | Dùng cho |
| --- | --- | --- |
| Constructor / `@Bean` factory method | Khi bean được tạo | Thiết lập state ban đầu |
| `@PostConstruct` | Sau dependency injection của một bean | Init cục bộ |
| `SmartLifecycle.start()` | Khi lifecycle processor start bean | Bắt đầu một thành phần có thể start/stop |
| `SmartLifecycle.stop(Runnable)` | Khi dừng lifecycle bean đang chạy | Dừng và báo hoàn tất cho processor |
| `ApplicationStartedEvent` | Sau Spring context refresh | Quan sát mốc Boot started |
| `ApplicationRunner`/`CommandLineRunner` | Sau refresh, trước Boot ready | Công việc startup cần hoàn tất trước ready |
| `ApplicationReadyEvent` | Sau các runners | Quan sát mốc Boot ready |
| `@PreDestroy` | Khi bean được hủy theo lifecycle thông thường | Giải phóng tài nguyên cuối |

`SmartLifecycle.start()` được gọi trong quá trình **context refresh** đối với auto-start beans; đừng nhầm với `ApplicationRunner` chạy **sau refresh**. Có bean đã chạy `start()` nhưng runner còn đang làm việc nên ứng dụng chưa đạt ready.

Khi đóng context, lifecycle processor yêu cầu stop các lifecycle beans đang chạy và sau đó bean factory thực hiện destruction callbacks theo vòng đời tương ứng. `@PreDestroy` **không thay** cho cơ chế shutdown theo phase, và mặc nhiên không tạo một thứ tự start/stop giữa hai peer cùng phase.

### @Lazy cũng không phải cách bảo đảm thứ tự

`SmartLifecycle` được container tìm và quản lý khi refresh; theo Javadoc, do tính auto-start, lazy-init flag có **rất ít tác dụng** để trì hoãn các bean loại này. Vì vậy:

- `@Lazy` trên SmartLifecycle không có nghĩa bean đó chắc chắn vắng mặt trong startup.
- `@Lazy` không thiết lập thứ tự giữa hai SmartLifecycle bean cùng phase.
- Nếu cần một thành phần không tự start, xét `isAutoStartup()` và quản lý việc start tường minh.
- Nếu cần một thành phần start **sau** thành phần khác, xét `getPhase()` hoặc dependency.

## 12. Thiết kế thực tế: connection, consumer và HTTP gateway

Giả sử một dịch vụ nhận yêu cầu HTTP, đưa message vào hàng đợi và có một background consumer xử lý message.

### Thiết kế rủi ro

~~~text
SmartLifecycle ConnectionManager: phase 0
SmartLifecycle QueueConsumer:      phase 0
SmartLifecycle RequestGateway:     phase 0
~~~

Không có dependency được khai báo. Có thể:

1. Gateway start trước khi queue consumer có khả năng xử lý.
2. Consumer start trước khi connection đã sẵn sàng.
3. Khi shutdown, connection bị dừng trước khi consumer ngừng nhận message.
4. Việc chạy đúng trên một instance không bảo đảm các instance khác trong cluster cũng đúng.

### Thiết kế theo phase

~~~text
ConnectionManager: phase -100
QueueConsumer:      phase    0
RequestGateway:     phase  100

Startup : ConnectionManager → QueueConsumer → RequestGateway
Shutdown: RequestGateway → QueueConsumer → ConnectionManager
~~~

Đây là mô hình tầng hợp lý **nếu tất cả đều thật sự là lifecycle components do cùng processor quản lý**. Cổng HTTP nhúng do Spring Boot/web server quản lý không nhất thiết tuân theo một phase do bạn gán cho một custom wrapper tùy ý; cần xem phase của framework component thực tế, không chỉ đặt tên bean “RequestGateway”.

### Thiết kế thêm @DependsOn khi cần ràng buộc chặt

Nếu `QueueConsumer` bắt buộc sử dụng `ConnectionManager`, đánh dấu dependency tường minh; nếu có nhiều consumer độc lập cùng phase 0 thì không cần bắt chúng xếp hàng theo một thứ tự.

Đối với connection asynchronous, đảm bảo **readiness của connection** được chờ đúng mức trước khi consumer start. Phần này không tự giải quyết chỉ bằng phase.

### Readiness của ứng dụng

Khi `SmartLifecycle.start()` đã được gọi, ứng dụng vẫn có thể chưa ready theo Spring Boot vì còn startup runners. Và khi Boot phát `ApplicationReadyEvent`, một background consumer tự đánh dấu running quá sớm có thể thực tế chưa subscribe. Với hệ thống cần bảo đảm traffic, cần có readiness indicator hoặc startup gate phù hợp.

Đặc biệt, **mở cổng TCP** không đồng nghĩa consumer đã sẵn sàng; nếu request được nhận trước khi pipeline hoạt động, có thể mất message hoặc tăng lỗi tạm thời.

## 13. Testing: kiểm tra một partial order thay vì absolute order

Khi test các phase, hãy phân loại **những quan hệ bắt buộc** và **những quan hệ không được API bảo đảm**.

### Những assertion nên có

Với hai nhóm phase `-100` và `100`, assertion:

~~~text
start(phase -100) trước start(phase 100)
stop(phase 100) trước stop(phase -100)
~~~

Với `@DependsOn("alpha")` trên `beta` cùng phase:

~~~text
start(alpha) trước start(beta)
stop(beta) trước stop(alpha)
~~~

Với `gamma` cùng phase, không có dependency:

~~~text
Không assert start(gamma) trước/sau start(alpha).
Không assert stop(gamma) trước/sau stop(beta).
~~~

### Test có thể “pass mãi” nhưng vẫn sai

Nếu log trên máy lúc nào cũng là:

~~~text
start(alpha)
start(beta)
start(gamma)
~~~

rồi bạn kiểm tra thứ tự đó như một hợp đồng, test rất mong manh. Khi thêm bean, nâng bản Spring hoặc thay một dependency, thứ tự tình cờ có thể đổi. Test nên xác nhận **những điều application correctness yêu cầu**, không xác nhận chi tiết nội bộ mà framework không hứa.

### Không cần cố tạo ngẫu nhiên để chứng minh hợp đồng

Việc gọi ứng dụng một trăm lần mà không thấy thứ tự đổi **không phản bác Javadoc**. “Không có bảo đảm” nghĩa là code không được phụ thuộc vào thứ tự, chứ không có nghĩa framework bắt buộc phải randomize mỗi lần.

### Kiểm tra async shutdown

Với bean stop bất đồng bộ, kiểm thử thêm:

- Callback `stop(Runnable)` được gọi sau khi công việc dừng thật sự kết thúc.
- Callback được gọi đúng một lần theo thiết kế.
- Timeout được xử lý theo phiên bản/framework configuration.
- Không còn message consumer nhận việc sau khi đã thông báo stop hoàn tất.
- Dependency chia sẻ chưa bị đóng khi consumer còn dùng nó.
- Context shutdown không treo vô hạn vì callback bị bỏ quên.

## 14. Những lỗi phổ biến

**1. “Cùng phase nghĩa là thứ tự A, B, C được quyết định theo tên.”** Sai. Javadoc xác nhận peer cùng phase được sắp xếp tùy ý trong cùng nhóm.

**2. “Phase 0 start sau phase 100.”** Sai. Khi khởi động, số nhỏ start trước. Khi dừng thì đảo chiều.

**3. “@Order(1) là thứ tự start của SmartLifecycle.”** Không phải hợp đồng chính thức cho lifecycle. Dùng `getPhase()` hoặc `@DependsOn`.

**4. “@Bean khai báo trước thì start trước.”** Không được bảo đảm. Bean creation order và lifecycle startup order là hai việc khác nhau.

**5. “Trong cùng phase, stop luôn đảo đúng thứ tự start đã quan sát.”** Không có bảo đảm thứ tự peer độc lập; shutdown còn có thể bất đồng bộ theo callback.

**6. “@DependsOn chỉ là chú thích, không ảnh hưởng stop.”** Sai. Quan hệ depends-on tường minh quy định dependent start sau dependency và stop trước dependency.

**7. “Một component implements SmartLifecycle mà không override getPhase sẽ ở phase 0.”** Sai. `SmartLifecycle.DEFAULT_PHASE` là `Integer.MAX_VALUE` trong Spring Framework 6.1.

**8. “isAutoStartup=false ngăn bean được tạo.”** Không. Nó ảnh hưởng auto-start. Việc khởi tạo bean là hợp đồng khác.

**9. “@Lazy làm SmartLifecycle bean không tham gia startup.”** Không đáng tin; processor thường tìm các SmartLifecycle beans để thực hiện auto-start, kể cả khi lazy-init.

**10. “start() được gọi trước nghĩa là kết nối đã sẵn sàng.”** Không hẳn. Nếu `start()` submit async task rồi trả về, dependency kế tiếp có thể khởi động khi resource trước chưa ready.

**11. “Khi stop(Runnable) trả về thì có thể gọi callback ngay dù consumer còn chạy.”** Sai. Callback phải biểu diễn **shutdown đã hoàn tất** của component.

**12. “Không cần callback nếu shutdown xảy ra nhanh.”** Với `SmartLifecycle.stop(Runnable)`, không gọi callback có thể khiến processor phải đợi đến timeout.

**13. “Một bean ở phase thấp nhất luôn là đầu tiên bất kể dependency.”** Không tuyệt đối. Quan hệ depends-on tường minh có thể được ưu tiên hơn phase.

**14. “Cổng web đã bind chứng minh mọi SmartLifecycle và runner đều sẵn sàng.”** Không. Readiness của Boot và trạng thái nghiệp vụ có hợp đồng khác.

**15. “Đánh số phase thật chi tiết là đủ cho mọi quan hệ phức tạp.”** Phase biểu diễn thứ tự nhóm; các bước async, timeout, retry, rollback cần logic điều phối hoặc readiness riêng.

**16. “Nếu test cố định thứ tự same-phase pass, hợp đồng đã được chứng minh.”** Không. Đó có thể chỉ là hành vi của một implementation ở một cấu hình.

**17. “Dùng @PreDestroy sẽ tự đảm bảo consumer dừng trước connection.”** Không nên giả định. Với lifecycle-managed components, dùng phase và dependency để mô tả thứ tự stop.

**18. “Bản Spring Framework nào cũng có API concurrentStartupForPhases.”** Không. Các API cấu hình đó thuộc phiên bản mới hơn 6.1, cần đối chiếu docs đúng dependency.

## 15. Bài thực hành

1. Ba bean `alpha`, `beta`, `gamma` đều trả phase `0`. Tại sao không nên assert thứ tự `alpha, beta, gamma` nếu không khai báo dependency?
2. Hai bean có phase `-10` và `20`. Hãy ghi thứ tự start và stop mong đợi.
3. Một bean `queueConsumer` có `@DependsOn("queueConnection")` và cả hai cùng phase `0`. Thứ tự start/stop nào được bảo đảm?
4. Trong project mục 7, tại sao `verifyStartup()` không kiểm tra `gamma` nằm trước `alpha`?
5. Bỏ `@DependsOn` của `beta` và chạy lại. Nếu vẫn PASS trong nhiều lần, có đủ để tin vào thứ tự đó không?
6. Thay phase `beta` thành `10` và bỏ dependency. Điều gì được quyết định bởi phase? Còn quan hệ `gamma` với `alpha` thế nào?
7. Thêm một `@Order(-100)` lên `gamma` mà giữ phase 0. Bạn có được quyền khẳng định `gamma.start()` luôn chạy đầu nhóm không?
8. Gắn `@DependsOn("storage")` lên `api`. Quan hệ này củng cố hay mâu thuẫn với phase `storage=-100`, `api=100`?
9. Cho một `SmartLifecycle` không override `getPhase()`. Nó có mặc định phase 0 không? Giá trị đúng là gì?
10. Thêm một bean chỉ implements `Lifecycle` thông thường. Processor xem bean đó thuộc phase nào?
11. Đổi `isAutoStartup()` của `gamma` thành `false`. Những phần nào của assertion trong demo phải thay đổi để phù hợp contract?
12. Cho `start()` của `storage` submit một kết nối async rồi return tức thì. Dù `storage` start trước `alpha`, vì sao `alpha` vẫn có thể lỗi? Hãy đề xuất một startup gate.
13. Viết một `stop(Runnable)` bất đồng bộ có callback chỉ sau khi thread/connection đã đóng. Nếu callback không chạy, có hậu quả gì?
14. Trong Spring Framework 6.1, hãy tìm `setTimeoutPerShutdownPhase` và thảo luận ảnh hưởng của giá trị timeout với nhiều peer cùng phase.
15. Với hệ thống có hai consumer độc lập dùng cùng connection pool, bạn có cần một thứ tự giữa hai consumer không? Tại sao phase chung có thể là lựa chọn đúng?
16. Một bean tự mở resources trong `@PostConstruct` và dừng trong `@PreDestroy`. Khi nào nên refactor nó thành `SmartLifecycle` thay vì chỉ giữ init/destroy callbacks?
17. Nếu cần một chuỗi 6 bước startup với retry và rollback, vì sao một orchestration bean có thể dễ test hơn 6 SmartLifecycle beans phụ thuộc chéo?
18. Nêu ba tín hiệu khác nhau: “bean được tạo”, “lifecycle đã start”, “service ready cho traffic”. Tín hiệu nào phase có thể ảnh hưởng trực tiếp?
19. Kiểm tra hai event `ApplicationStartedEvent` và `ApplicationReadyEvent` trong ứng dụng có runner. Vì sao các mốc này khác nhau dù SmartLifecycle đã start trong refresh?
20. Thiết kế unit/integration test chỉ kiểm tra partial order từ phase/depends-on, không dùng số lần chạy lặp lại để “suy ra” một bảo đảm không tồn tại.

## Ghi nhớ

- **Phase nhỏ khởi động trước; phase lớn dừng trước.** Đó là thứ tự **giữa các nhóm phase**.
- **Các bean độc lập cùng phase không có thứ tự start/stop được bảo đảm.** Đừng dựa vào tên bean, thứ tự source code, component scanning hay `@Order`.
- **`@DependsOn` tạo một quan hệ thứ tự tường minh:** dependency start trước dependent; dependent stop trước dependency, kể cả khi cùng phase.
- `SmartLifecycle.DEFAULT_PHASE` trong Spring Framework 6.1 là `Integer.MAX_VALUE`; regular `Lifecycle` không `Phased` thường được xử lý như phase 0.
- `isAutoStartup()` ảnh hưởng việc tự gọi `start()` khi refresh; nó khác bean initialization và khác trạng thái business readiness.
- `start()` trả về không tự có nghĩa tài nguyên bên ngoài sẵn sàng, đặc biệt nếu logic là async. Cần chờ readiness đúng hợp đồng khi có dependency quan trọng.
- Với `stop(Runnable)`, **chỉ gọi callback khi component thực sự dừng xong**. Dừng async và timeout có thể ảnh hưởng thời gian shutdown của cả nhóm.
- Kiểm thử **partial order** được contract bảo đảm, không kiểm thử một chuỗi tuyệt đối cho các peer cùng phase.

### Tài liệu tham khảo

- Spring Framework 6.1 — `SmartLifecycle` Javadoc (phase order, same-phase arbitrary, depends-on precedence, auto-start, callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` Javadoc (phase grouping, dependency order, timeout): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `Phased` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Phased.html
- Spring Framework 6.1 — `DependsOn` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/DependsOn.html
- Spring Framework — Bean Lifecycle Callbacks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Boot 3.3 — SpringApplication Startup and Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
