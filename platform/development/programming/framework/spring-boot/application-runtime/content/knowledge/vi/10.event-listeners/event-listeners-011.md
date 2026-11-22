# Tránh đăng ký trùng listener và tạo tác dụng phụ lặp lại trong Spring Boot

**Chủ đề:** Spring Boot Application Runtime → Listener. Bài học hướng dẫn xác định và xử lý tình trạng một sự kiện được nhiều listener cùng thực thi tác dụng phụ, hoặc cùng một thao tác nghiệp vụ bị phát lại. Cần hiểu đúng ba việc **đăng ký listener**, **phân phối event** và **tính idempotent của tác dụng phụ**. Ví dụ thực hành dùng **Java 17+**, **Spring Boot 3.5.x**, Spring MVC và Maven.

## 1. Mục tiêu

Học xong, bạn phải có khả năng:

1. Liệt kê các cách đăng ký `ApplicationListener` và `@EventListener` trong Spring Boot.
2. Phân biệt **một event có hai listener** với **hai event được phát cho một listener**.
3. Phân biệt **cùng một listener object được thêm hai lần** với **hai listener instances cùng class**.
4. Tìm ra nguyên nhân nhận event lặp do `@Component`, `@Bean`, `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)`, `META-INF/spring.factories`, hoặc parent/child context.
5. Tạo lab có một bean listener mặc định và một listener được thêm bằng API tùy chọn; kiểm chứng số lần callback qua HTTP.
6. Chặn một tác dụng phụ mô phỏng trong **một ApplicationContext** bằng shared singleton và `AtomicBoolean.compareAndSet`, đồng thời giải thích tại sao không đủ an toàn cho transaction thật.
7. Chọn đúng cơ chế khử trùng bền vững cho event có ID ổn định, nhiều replica, retry và lỗi partial.
8. Biết `@Order`, `@Async` và `@TransactionalEventListener` có vai trò riêng, **không** tự bảo đảm exactly-once.

**Quy tắc cốt lõi:** loại bỏ đăng ký thừa để có **một owner nghiệp vụ**, rồi thiết kế tác dụng phụ có thể chịu được **at-least-once delivery** nếu có retry, restart hoặc đa instance. Không dựa vào số lần log xuất hiện để kết luận dữ liệu đã bị thay đổi mấy lần.

## 2. Vì sao tác dụng phụ dễ bị lặp?

Giả sử ứng dụng phát `ApplicationReadyEvent` một lần sau startup. Hai listener cùng nhận event và cùng gọi hàm gửi yêu cầu tới hệ thống ngoài:

~~~text
ApplicationReadyEvent (1 event)
     |
     +---- ListenerBean ----------> sendNotification()
     |
     +---- ListenerFromApi -------> sendNotification()
                                  hai tác dụng phụ có thể phát sinh
~~~

Đó là **duplicate handling do nhiều registrations**. Ngược lại:

~~~text
Publisher publish(event-123) ------> Listener
Publisher retry(event-123) --------> Listener
                                      cùng business event nhận hai lần
~~~

Đó là **duplicate delivery do publisher/retry**, ngay cả khi chỉ có một listener duy nhất.

Còn trường hợp mỗi context có một sự kiện hợp lệ:

~~~text
parent ApplicationContext -- ContextRefreshedEvent(parent)
child ApplicationContext  -- ContextRefreshedEvent(child)
                             |
                             +-- forwarded đến parent listeners
~~~

Một parent listener có thể nhận cả event của parent lẫn event từ child. Đây là đặc điểm propagation, không nhất thiết là đăng ký lỗi.

### 2.1. Tác dụng phụ có độ rủi ro khác nhau

| Tác dụng phụ | Nếu thực hiện hai lần | Phản ứng phù hợp |
|---|---|---|
| Log “ready” | Log nhiễu, metric sai | Sửa registration và log metadata |
| Tạo cache từ dữ liệu bất biến | Có thể lãng phí CPU, chồng thread | Một owner, idempotent rebuild |
| Mở consumer/scheduler | Hai worker cùng tiêu thụ công việc | Lifecycle owner, start/stop có kiểm soát |
| Gửi email/SMS | Gửi trùng cho người dùng | Event ID + inbox/outbox/idempotency |
| Ghi audit | Duplicates hoặc báo cáo sai | Unique business key, quy tắc audit |
| Thanh toán/cấp quyền | Double charge hoặc quyền bị ghi lặp | Idempotency key ở hệ thống đích và durable dedupe |

Đừng giả định chỉ có event framework mới bị trùng. Với broker, client retry hoặc nhiều replica, lỗi thường nằm ngoài Spring event bus.

## 3. Những đường đăng ký listener cần kiểm tra

| Đăng ký | Cách dùng | Khi nào phù hợp | Rủi ro chồng |
|---|---|---|---|
| Bean implement `ApplicationListener<E>` | `@Component class X implements ApplicationListener<E>` | Listener cần DI và context đã sẵn sàng | App còn thêm `new X()` từ API |
| Method `@EventListener` | `@EventListener void on(E event)` trên bean | Event runtime/late startup | Có method khác xử lý cùng side effect |
| `@Bean` listener | Factory method trả `ApplicationListener<E>` | Listener tạo có cấu hình | Cùng logic được tạo từ component scan |
| `SpringApplication.addListeners(...)` | `app.addListeners(new X())` | Early events trước khi bean tồn tại | Thêm một instance có chức năng giống bean |
| `SpringApplicationBuilder.listeners(...)` | Builder gắn listener | Project có builder/context hierarchy | Listener gắn nhiều context |
| `META-INF/spring.factories` | Key interface và FQCN implementation | Thư viện auto-registration | App còn tự tạo listener đó |
| Context hierarchy | Child event được forward lên parent | Parent quan sát nhiều child | Parent xử lý event của child ngoài ý muốn |

**Lưu ý:** Một số event rất sớm như `ApplicationStartingEvent` xảy ra trước khi `ApplicationContext` được tạo. Không thể dựa vào `@EventListener` trong bean bình thường để nhận chúng; dùng API hoặc factories. Với `ApplicationReadyEvent`, context đã refresh nên bean listener là cách đơn giản, dễ quản lý.

Không thêm cả `@Component` lẫn `addListeners(new ...)` chỉ vì muốn “chắc chắn event được nhận”. Nếu cần hai listeners cho hai mục tiêu khác nhau (ví dụ một ghi telemetry, một cập nhật cache), điều đó hợp lệ; chỉ tránh hai nơi cùng sở hữu một side effect không idempotent.

### 3.1. Có phải add cùng object hai lần thì nhất định chạy hai lần?

**Không thể kết luận như vậy.** Một số tập listener nội bộ dùng tập hợp và loại trùng theo equality của **cùng một object**. Nhưng nếu code gọi `new MyListener()` hai lần, mỗi lần là một instance khác nhau, kết quả equality và registration có thể khác. Đặc biệt, một instance do Spring quản lý và một instance được tạo thủ công thường là **hai object khác nhau**.

Điều tra cần ghi cả **class name, bean name/instance identity và context**. Không dùng tên class đơn lẻ làm bằng chứng hai callback xuất phát từ cùng object.

## 4. Dự án lab: đếm callback và hiệu ứng mô phỏng

Tạo project từ Spring Initializr:

- Maven, Java 17, Spring Boot 3.5.x.
- Group `com.example`, Artifact `listener-repeat-lab`, Package `com.example.listenerrepeat`.
- Dependency **Spring Web**, packaging **JAR**.
- Giữ nguyên `pom.xml` và Maven Wrapper được tạo.

Cấu trúc:

~~~text
listener-repeat-lab/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/listenerrepeat/
    ListenerRepeatApplication.java
    ReadyEffect.java
    BeanReadyListener.java
    ApiReadyListener.java
    CountController.java
  src/main/resources/application.properties
~~~

Đây là các file Java độc lập trong **cùng một Maven project**, không phải những file tự chạy bằng `javac` không có Spring dependencies. Mọi public class phải đặt vào file trùng tên.

### 4.1. Main: bật registration thứ hai bằng JVM system property

File `ListenerRepeatApplication.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ListenerRepeatApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ListenerRepeatApplication.class);

        if (Boolean.getBoolean("lab.extra-listener")) {
            app.addListeners(new ApiReadyListener());
        }

        app.run(args);
    }
}
~~~

Không có `-Dlab.extra-listener=true` thì chỉ bean listener thông thường được đăng ký trong project. Khi bật, `SpringApplication.addListeners(...)` tạo một **registration thứ hai** cho cùng loại `ApplicationReadyEvent`.

`Boolean.getBoolean(...)` đọc **Java system property**, không phải `application.properties`. Khi chạy JAR, phải viết `-Dlab.extra-listener=true` **trước `-jar`**. Nếu đặt sau tên JAR, `SpringApplication` có thể thấy một application argument, nhưng JVM `Boolean.getBoolean(...)` sẽ không coi đó là system property.

### 4.2. Shared singleton giữ hai bộ đếm

File `ReadyEffect.java`:

~~~java
package com.example.listenerrepeat;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ReadyEffect {

    private final AtomicInteger attempts = new AtomicInteger();
    private final AtomicInteger effects = new AtomicInteger();
    private final AtomicBoolean once = new AtomicBoolean();

    public void handle(String source) {
        int attempt = attempts.incrementAndGet();
        boolean executed = once.compareAndSet(false, true);

        if (executed) {
            // Tac dung phu demo: chi tang counter in-memory.
            effects.incrementAndGet();
        }

        System.out.println("LAB_READY source=" + source
                + " attempt=" + attempt
                + " effectExecuted=" + executed);
    }

    public Counts counts() {
        return new Counts(attempts.get(), effects.get());
    }

    public record Counts(int attempts, int effects) {
    }
}
~~~

Có hai khái niệm tách riêng:

- `attempts` tăng **mỗi lần** một listener gọi `handle`.
- `effects` chỉ tăng nếu `once.compareAndSet(false, true)` thành công.

Hai listener được nối tới **cùng bean singleton `ReadyEffect`**, vì thế CAS cùng quan sát một cờ và chỉ một thread thành công trong một process/context. Chương trình sử dụng counter in-memory để tránh gọi dịch vụ ngoài, đủ để nhìn thấy nguy cơ và giới hạn.

**Không đưa trực tiếp mô hình này vào thanh toán, email hay dữ liệu quan trọng.** Cờ được set trước hiệu ứng; nếu hiệu ứng thật thất bại hoặc process chết, trạng thái có thể không phản ánh kết quả. Một replica khác có cờ riêng. `AtomicBoolean` chỉ minh họa tránh lặp **trong một JVM object**, không phải exactly-once.

### 4.3. Listener là bean dùng @EventListener

File `BeanReadyListener.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class BeanReadyListener {

    private final ReadyEffect effect;

    public BeanReadyListener(ReadyEffect effect) {
        this.effect = effect;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        effect.handle("bean");
    }
}
~~~

Đây là owner mặc định duy nhất cho tác dụng phụ mô phỏng. `@EventListener` chỉ được phát hiện vì class là Spring-managed bean. Nếu còn tạo một listener từ `new BeanReadyListener(...)` bên ngoài Spring và đăng ký thủ công, bạn đã thêm một đường xử lý khác.

### 4.4. Listener đăng ký bằng API

File `ApiReadyListener.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;

public final class ApiReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        event.getApplicationContext()
                .getBean(ReadyEffect.class)
                .handle("api");
    }
}
~~~

Class này **không có `@Component`** và không khai báo trong factories. Nó chỉ hoạt động khi `main()` gọi `addListeners(new ApiReadyListener())`. Ở thời điểm `ApplicationReadyEvent`, context đã refresh nên ví dụ có thể lấy bean `ReadyEffect` từ context. **Không** làm cách đó ở `ApplicationStartingEvent` hay early events khác vì context chưa tồn tại đầy đủ.

### 4.5. API chỉ đọc counters

File `CountController.java`:

~~~java
package com.example.listenerrepeat;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CountController {

    private final ReadyEffect effect;

    public CountController(ReadyEffect effect) {
        this.effect = effect;
    }

    @GetMapping("/demo/counts")
    public ReadyEffect.Counts counts() {
        return effect.counts();
    }
}
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=listener-repeat-lab
server.address=127.0.0.1
server.port=8080
~~~

Binding `127.0.0.1` chỉ để học thử trên máy cục bộ. Dự án có Spring Web và Jackson sẽ serialize Java record thành JSON.

## 5. Kịch bản A — Chỉ một registration

Linux/macOS:

~~~bash
java -version
./mvnw -version
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
java -version
./mvnw.cmd -version
./mvnw.cmd spring-boot:run
~~~

Chờ ứng dụng startup xong. Vì cờ `lab.extra-listener` mặc định tắt, console có marker:

~~~text
LAB_READY source=bean attempt=1 effectExecuted=true
~~~

Trong terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/demo/counts
~~~

Kỳ vọng HTTP 200 với body tương đương:

~~~json
{"attempts":1,"effects":1}
~~~

Đây là bằng chứng **một callback vào `ReadyEffect` và một hiệu ứng mô phỏng** trong context hiện tại. Không suy từ đó rằng toàn bộ application có đúng một listener framework; Spring Boot có nhiều listeners khác phục vụ các chức năng riêng.

## 6. Kịch bản B — Hai registrations cho cùng ApplicationReadyEvent

Dừng bản chạy cũ rồi build JAR:

~~~bash
./mvnw clean package
java -Dlab.extra-listener=true -jar target/listener-repeat-lab-0.0.1-SNAPSHOT.jar
~~~

Trên Windows thay `./mvnw` bằng `./mvnw.cmd`. Nếu project version khác `0.0.1-SNAPSHOT`, lấy tên thật của JAR trong `target/`.

Log sẽ có **hai marker `LAB_READY`** với source `bean` và `api`. Ví dụ một thứ tự hợp lệ:

~~~text
LAB_READY source=api attempt=1 effectExecuted=true
LAB_READY source=bean attempt=2 effectExecuted=false
~~~

Thứ tự ngược lại cũng hợp lệ. `@Order` không được thiết lập trong lab và không cần thiết để đạt kết quả mong muốn. Gọi:

~~~bash
curl -i http://127.0.0.1:8080/demo/counts
~~~

Kỳ vọng:

~~~json
{"attempts":2,"effects":1}
~~~

**Diễn giải:** có hai callbacks cùng gọi một shared bean, nhưng CAS chỉ cho tăng hiệu ứng một lần. Đây là trường hợp hai listener phù hợp nhận **cùng một ready event**, không phải do Boot tự phát ready hai lần trong một lượt chạy.

Trong bản lab thử riêng, nếu bỏ `if (executed)` và tăng `effects` vô điều kiện, kết quả khi hai listener chạy sẽ là `attempts=2, effects=2`. Đó là lỗi hành vi ta cần ngăn. Không sửa code production chỉ để thử bằng payment, email hoặc external API thực.

Chạy lại **không có** cờ `-Dlab.extra-listener=true` sẽ trở về `attempts=1, effects=1` trên context mới. Số đếm reset sau restart chứng minh cờ trong RAM không phải cơ chế chống lặp dài hạn.

### 6.1. Bảng đối chiếu

| Cấu hình | Số lần callback vào service | Số hiệu ứng mô phỏng | Kết luận |
|---|---:|---:|---|
| Mặc định | 1 | 1 | Một owner |
| Bật system property | 2 | 1 | Hai registrations, guard local |
| Bật property và tăng effects vô điều kiện | 2 | 2 | Side effect bị lặp |

Các số liệu áp dụng khi project chạy **một context, một lần startup thành công và không có code khác cùng gọi `ReadyEffect`**. Test suite, DevTools hoặc application restart tạo thêm lượt lifecycle cần ghi riêng.

## 7. Các anti-pattern thường tạo registration chồng nhau

### 7.1. Một class vừa là @Component vừa được new trong main

~~~java
@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // Neu co side effect, no co the chay nhieu hon mong muon.
    }
}
~~~

Và trong `main()`:

~~~java
app.addListeners(new ReadyListener());
~~~

Đây là **hai đoạn minh họa**; khi biên dịch cần imports và các class thích hợp. `ReadyListener` được Spring scan thành một bean, đồng thời một instance mới được thêm bằng API. Không nên nhầm hai object với một listener duy nhất.

### 7.2. Có spring.factories nhưng vẫn addListeners thủ công

Trong thư viện hoặc application resource:

~~~properties
org.springframework.context.ApplicationListener=com.example.ReadyListener
~~~

Nếu `ReadyListener` cũng được thêm bằng code, có thể có hai instances mang cùng chức năng. Kiểm tra trong runtime classpath vì một dependency JAR cũng có thể chứa `META-INF/spring.factories`; chỉ tìm trong `src/main/resources` của app không đủ.

### 7.3. Một bean nhận cùng event qua hai cơ chế

Ví dụ một class implement `ApplicationListener<MyEvent>` và còn có method `@EventListener` khác gọi cùng logic cho `MyEvent`. Hai đường xử lý khác nhau có thể dẫn tới hai lần side effect dù class chỉ có một instance. Thực hành tốt là chọn một owner method và để listener còn lại chỉ làm việc độc lập (nếu thật sự cần).

### 7.4. Nhiều @EventListener methods cùng side effect

Nếu nhiều method trong các components cùng gửi notification khi có `OrderPaidEvent`, mỗi method có thể là registration hợp lệ theo Spring nhưng **nghiệp vụ vẫn bị lặp**. Chọn một service sở hữu notification và các listeners khác xử lý mục tiêu riêng hoặc delegate qua một idempotent owner chung.

### 7.5. Lẫn event trước và sau context initialization

`ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent` cần listener đăng ký sớm. `ApplicationReadyEvent` là event muộn, có thể xử lý bằng Spring bean. Không tạo hai listener chỉ vì một trong hai lắng nghe early events; phân chia theo event type và nhiệm vụ rõ ràng.

## 8. Context hierarchy: lọc event theo context nguồn

Spring có thể chuyển event từ child context lên parent context. Theo tài liệu Boot, khi dùng nhiều `SpringApplication` theo hierarchy, listener có thể nhận nhiều events cùng type.

Đối với `ContextRefreshedEvent`, một bean chỉ muốn xử lý **chính context của nó** có thể lọc:

~~~java
@Component
public class LocalRefreshListener {

    private final ApplicationContext ownContext;

    public LocalRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }

        System.out.println("LAB_OWN_CONTEXT_REFRESHED");
    }
}
~~~

Đây là **snippet** cần import `ApplicationContext`, `ContextRefreshedEvent`, `EventListener` và `Component`. Phép `!=` so sánh identity của context object; không dựa vào name, PID hoặc một dòng log gần giống nhau. Với `ApplicationReadyEvent`, có thể kiểm `event.getApplicationContext()` tương tự.

Nếu listener được thiết kế cố ý để giám sát mọi context con thì không nên lọc đi; khi đó phải dùng context ID để tách sự kiện hợp lệ và tránh chạy một side effect global không idempotent cho mỗi child.

## 9. Phát event hai lần khác với đăng ký hai lần

Ngay cả khi chỉ giữ một listener, các hệ thống còn có:

- Request retry sau timeout.
- Message broker redelivery vì consumer chưa ack.
- Scheduler/job khởi chạy lại.
- Transaction retry.
- Hai service paths publish cùng ý nghĩa nghiệp vụ.
- DevTools restart hoặc rolling deployments.
- Nhiều replica nhận cùng message do cấu hình consumer group/topic khác mong muốn.

Nếu cùng sự kiện nghiệp vụ có thể được phát lại, listener cần **business event identity ổn định**. Ví dụ Java 17:

~~~java
public record OrderPaidEvent(
        String eventId,
        String orderId,
        long amountInCents) {
}
~~~

Đây là **data type minh họa**, không có trong project lab chính. `eventId` cần giữ nguyên giữa các lần retry của cùng event. Tự tạo `UUID.randomUUID()` **mỗi lần deliver lại** sẽ biến một tác vụ cũ thành ID mới và phá deduplication. Nếu nghiệp vụ cần quyết định theo `orderId` và version, thiết kế idempotency key theo contract nguồn thực tế, không chỉ ngẫu nhiên chọn mỗi event attempt một ID.

### 9.1. In-memory Set: tốt cho demo, chưa đủ production

Mẫu minh họa logic:

~~~java
private final Set<String> observed =
        ConcurrentHashMap.newKeySet();

@EventListener
public void onOrderPaid(OrderPaidEvent event) {
    if (!observed.add(event.eventId())) {
        return;
    }
    process(event);
}
~~~

Đây là **snippet**, cần định nghĩa `process`, `OrderPaidEvent` và các imports/bean thích hợp. Nó có rủi ro:

- Restart xóa danh sách.
- Mỗi replica có Set riêng.
- Nếu `process` thất bại sau khi đã add ID, retry bị chặn dù chưa thành công.
- Nếu hiệu ứng ngoài đã thành công nhưng process ném exception, retry và việc xóa marker có thể lặp side effect.
- Bộ nhớ tăng vô hạn nếu không có retention policy.

Vì thế `ConcurrentHashMap.newKeySet()`, `AtomicBoolean` hoặc synchronized block **không** đảm bảo exactly-once end-to-end.

### 9.2. Durable inbox và unique constraint

Với nghiệp vụ ghi **cùng một database**, có thể dùng bảng đánh dấu event đã được xử lý kèm unique constraint:

~~~sql
CREATE TABLE consumed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction ứng dụng, thử insert event key. Ví dụ cú pháp PostgreSQL:

~~~sql
BEGIN;

INSERT INTO consumed_event(consumer_name, event_id)
VALUES ('order-projector', 'evt-001')
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Ứng dụng kiểm row count của INSERT:
-- 1 hàng: cập nhật bảng nghiệp vụ trong CÙNG transaction.
-- 0 hàng: sự kiện đã được xử lý; bỏ qua tác dụng phụ DB.

COMMIT;
~~~

Đây là **mẫu SQL thiết kế**, không phải lệnh trọn vẹn có thể chạy khi chưa có schema và nghiệp vụ. Constraint làm nhiều replicas cạnh tranh cùng key không thể cùng commit marker mới. Toàn bộ cập nhật DB quan trọng phải nằm trong **cùng transaction** với marker, nếu không vẫn có cửa sổ failure.

Khi tác dụng phụ là **email, payment gateway, message broker hoặc HTTP API ngoài**, DB transaction của bạn không thể atomic với thế giới ngoài. Hãy dùng transactional outbox, inbox, retry có giới hạn, và idempotency key của dịch vụ đích nếu được hỗ trợ. Chính sách exactly-once phải được chứng minh theo contract của các hệ thống tham gia, không thể suy ra từ `@EventListener`.

### 9.3. TransactionalEventListener không chống lặp tự động

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ giúp handler chạy sau khi transaction nguồn commit. Nó **không** khử trùng sự kiện cùng ID, không ngăn nhiều listener cùng đăng ký và không ngăn publisher retry. Theo mặc định nếu không có transaction phù hợp, listener này không được gọi (trừ khi cấu hình fallback).

Nếu cần side effect ngoài hệ thống sau commit, cân nhắc outbox để không mất event khi process chết giữa commit và gửi. Đừng coi `AFTER_COMMIT` đồng nghĩa hiệu ứng đã được thực hiện đúng một lần.

## 10. @Order, @Async và lỗi concurrency

`@Order` có thể đặt thứ tự listener trong kịch bản phù hợp; **không** hủy listener có order thấp hơn và **không** tự loại trùng. Nếu hai listener cùng gửi email, đặt thứ tự 1 và 2 vẫn gửi hai lần.

`@Async` cho phép event xử lý ở thread khác, không dedupe. Hai callbacks có thể thực thi đồng thời:

~~~text
Thread A: read done=false
Thread B: read done=false
Thread A: execute effect
Thread B: execute effect
~~~

Dùng boolean thường với check-then-act có race. `AtomicBoolean.compareAndSet` bảo vệ một hiệu ứng mô phỏng trong **một object** như lab, nhưng không bảo đảm thành công của I/O và không đồng bộ across JVMs.

Exception của async listener không mặc nhiên được ném ngược đến publisher như callback đồng bộ; cần logging, error handler, retry và telemetry. Kết quả trả về từ method `@EventListener` có thể được Spring dùng publish event khác trong cơ chế đồng bộ, nhưng async listener không có cùng semantics return-to-publish. Khi cần publish rõ ràng, dùng `ApplicationEventPublisher`.

## 11. DevTools, tests, restart và multi-instance

Một `ApplicationReadyEvent` thường được phát một lần cho một lượt `SpringApplication.run()` thành công của một application instance đơn giản, không phải “đúng một lần suốt đời deployment”.

- **DevTools:** restart có thể tạo context mới, listener được khởi tạo lại.
- **Tests:** nhiều context trong suite, có thể cache hoặc tạo lại.
- **Parent/child:** mỗi context có lifecycle riêng; child event có thể propagated.
- **Nhiều `SpringApplication`:** cùng JVM có thể chứa hơn một app/context.
- **Rolling deployment:** mỗi replica tự phát event ready. Dùng ready event để chạy migration/send newsletter có thể làm nhiều bản thực hiện cùng tác vụ.
- **Startup thất bại:** một phần side effect có thể xảy ra trước lỗi, sau đó process restart và thử lại.

Muốn một lần **mỗi context**, chọn một bean singleton owner với cơ chế phù hợp vòng đời context. Muốn một lần **mỗi business event**, dùng durable event ID. Muốn một lần **toàn cụm**, dùng một job/migration owner riêng, leader election hoặc distributed coordination theo kiến trúc, không dựa vào ready event của từng replica.

Cờ `static boolean alreadyRan` là giải pháp kém vì classloader, tests, memory visibility, restart và multi-process. Nó còn có nguy cơ chặn tác vụ hợp lệ trong context mới.

## 12. Lọc log và chẩn đoán theo bằng chứng

Để tìm nguyên nhân, ghi log theo mẫu:

~~~text
eventType=ApplicationReadyEvent eventId=... contextId=...
listener=BeanReadyListener bean=beanReadyListener instance=...
attempt=1 effectStarted=true effectSucceeded=true
~~~

`eventId` là ví dụ cho business event tự định nghĩa; `ApplicationReadyEvent` mặc định không có business ID ổn định được thiết kế để dedupe giữa các lần khởi động. Đừng phát sinh ID mới trong listener rồi coi là ID của event gốc. Các trường instance, context, publisher count và event identity phải được thiết kế đúng nguồn.

Một truy vấn tìm mã đơn giản trên hệ Unix:

~~~bash
grep -R -nE 'ApplicationListener|@EventListener|addListeners|spring.factories' src
~~~

Lệnh này chỉ tìm trong `src`, không quét JAR dependencies. Với thư viện, xem `META-INF/spring.factories` ở runtime classpath. `SpringApplication.getListeners()` trả tập listener đã đăng ký ở application instance, nhưng **không phải** danh sách đầy đủ mọi `@EventListener` method hoặc listener bean do context phát hiện sau đó.

### Bảng chẩn đoán

| Triệu chứng | Giả thuyết | Kiểm tra/sửa |
|---|---|---|
| Một event nhưng hai lần xử lý từ bean và API | Registration chồng | Chọn một owner, bỏ listener thừa |
| Hai class names giống nhau nhưng instance khác | `new` ngoài container hoặc factory loader | So bean name/identity và đường khởi tạo |
| Hai event IDs giống nhau | Publisher retry/redelivery | Durable dedupe theo ID ổn định |
| Parent handler nhận event của child | Context hierarchy | So event context với own context |
| Chỉ lặp sau DevTools restart | Context mới | Kiểm tra lifecycle, không dùng static flag |
| Lặp khi scale nhiều replica | Mỗi replica nhận cùng việc | Inbox/unique constraint hoặc cluster owner |
| Dùng `@Async` rồi bị gửi hai email | Race/concurrency | Idempotency key và cơ chế bền vững |
| Guard chặn retry dù effect thất bại | Cờ set quá sớm | Trạng thái xử lý và recovery thật |
| `@Order` đổi mà còn lặp | Order không loại registration | Bỏ owner dư và dedupe |
| `@TransactionalEventListener` nhận hai lần | Event phát lại/handlers nhân đôi | Transaction phase không chống duplicate |
| Thấy hai log mà một effect | Hai callbacks, guard hoạt động local | Xem counter và external state thực |
| App failed startup trước ready | Ready event chưa phát | Dùng đúng event/điểm hook và stack trace |

## 13. Các bài tập thực hành

### Bài tập A — Registration count

1. Chạy app mặc định; ghi marker `LAB_READY source=bean`.
2. Gọi `GET /demo/counts`: `attempts=1, effects=1`.
3. Dừng app, bật `-Dlab.extra-listener=true` và chạy lại JAR.
4. Xác nhận hai nguồn `bean` và `api`; thứ tự không phải kết luận nghiệp vụ.
5. Gọi endpoint: `attempts=2, effects=1`. Giải thích CAS và scope shared singleton.
6. Tắt app rồi khởi động lại; xác nhận counter là của context mới.

### Bài tập B — Khử đăng ký thừa

Trong bản lab có cờ bật, bỏ lời gọi `addListeners(new ApiReadyListener())` hoặc tắt system property rồi chạy lại. Không thay `ReadyEffect`. So log/counters trước–sau để chứng minh nguyên nhân callback hai lần nằm ở registration chồng, không phải do `SpringApplication` mặc định phát hai lần.

### Bài tập C — Event cùng ID được giao lại

Giả lập hai lần publish cùng `OrderPaidEvent("evt-001", "ord-101", 2500)`. Thiết kế một unique key `(consumer_name,event_id)` và chỉ cập nhật DB khi first insert thành công. Thử hai consumer đồng thời, rồi thêm tình huống process crash. Phân biệt **duplicate delivery** và **duplicate registration**.

### Bài tập D — Nhiều context

Với một ví dụ dùng `SpringApplicationBuilder` và parent/child, log `event.getApplicationContext().getId()` cho `ContextRefreshedEvent`. Thêm predicate so đúng own context để tránh xử lý child event khi side effect chỉ dành cho parent. Khi cần quan sát mọi context, dùng correlation ID rõ ràng thay vì lọc hết.

### Bài tập E — Tình huống sau commit

Mô tả một listener `@TransactionalEventListener(AFTER_COMMIT)` nhận cùng event ID từ hai transaction thành công. Giải thích vì sao cả hai callback vẫn có thể được gọi. Đề xuất inbox/outbox/idempotency key thay vì chỉ thay phase.

## 14. Checklist nghiệm thu

- [ ] Phân biệt registration duplication, event duplication và context propagation.
- [ ] Tìm đủ các đường đăng ký listener trong ứng dụng và dependencies.
- [ ] Dựng được project Java 17/Spring Boot 3.5.x với các file Maven hướng dẫn.
- [ ] Kiểm chứng một listener: `attempts=1, effects=1`.
- [ ] Kiểm chứng hai listener: `attempts=2, effects=1`.
- [ ] Giải thích giới hạn của `AtomicBoolean` với multi-process, restart và partial failure.
- [ ] Biết event được publish ở child context có thể đi đến parent listeners.
- [ ] Chỉ ra `@Order` và `@Async` không dedupe.
- [ ] Phân biệt `@TransactionalEventListener(AFTER_COMMIT)` với exactly-once.
- [ ] Thiết kế event ID ổn định, inbox unique key và outbox khi có external I/O.
- [ ] Ghi log/metric tách callback attempts, dedupe decisions và completed side effects.
- [ ] Không triển khai tác dụng phụ global lên mỗi ready event ở mọi replica mà không có owner.

## 15. Tài liệu chính thức

- Spring Boot 3.5 — Application Events and Listeners, propagation của parent/child contexts: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 — SpringApplication API `addListeners`, `getListeners`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html
- Spring Framework 6.2 — Application events và `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound application events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — `ApplicationListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationListener.html

**Kết luận:** Tránh listener gây hiệu ứng lặp đòi hỏi **một nơi sở hữu nghiệp vụ rõ ràng**, **kiểm tra đúng event/context nguồn**, và **idempotency đúng cấp độ chịu lỗi**. Registration sạch ngăn một loại duplicate; durable dedupe ngăn loại duplicate khác. Cả hai đều quan trọng khi ứng dụng được restart, scale hoặc chịu retry.