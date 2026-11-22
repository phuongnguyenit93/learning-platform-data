# ContextRefreshedEvent trong vòng đời Spring ApplicationContext

## 1. ContextRefreshedEvent là gì?

`ContextRefreshedEvent` là sự kiện thuộc `org.springframework.context.event`, được Spring Framework phát khi một `ApplicationContext` đã **hoàn tất thao tác khởi tạo hoặc refresh thành công**. Đây là một trong các sự kiện vòng đời chuẩn của Spring, giúp thành phần trong cùng ứng dụng phản ứng sau giai đoạn thiết lập container.

Ví dụ: Sau khi Spring hoàn tất đăng ký các bean, xử lý cấu hình, khởi tạo các singleton không lazy và chuẩn bị hệ thống quản lý vòng đời, ứng dụng có thể cập nhật cache nội bộ hoặc ghi nhận rằng một context cụ thể đã refresh xong.

Điểm cần phân biệt: `ContextRefreshedEvent` là **tín hiệu của Spring container**, không mặc định là tín hiệu mọi dịch vụ bên ngoài đã sẵn sàng hoặc toàn bộ quy trình khởi động của Spring Boot đã hoàn tất. Với Spring Boot, còn có `ApplicationStartedEvent` và `ApplicationReadyEvent` ở các mốc riêng.

`ContextRefreshedEvent` kế thừa `ApplicationContextEvent`; có thể lấy context nguồn bằng `event.getApplicationContext()`. Nó không chứa thông tin "bean nào vừa thay đổi" hay "cấu hình nào vừa cập nhật". Không dùng nó như thông báo thay đổi cho từng bean.

## 2. Event được phát ở giai đoạn nào?

Với một `AbstractApplicationContext` điển hình, lời gọi `refresh()` thực hiện nhiều bước nội bộ. Chỉ cần nắm các mốc quan trọng:

```text
Tạo / đăng ký ApplicationContext
            |
            v
refresh()
  - chuẩn bị BeanFactory và các BeanPostProcessor
  - tạo những singleton non-lazy, tiêm dependency
  - gọi init/@PostConstruct trên các bean liên quan
  - thiết lập LifecycleProcessor; khởi động SmartLifecycle
            |
            v
publishEvent(new ContextRefreshedEvent(this))
            |
            v
Các listener được dispatch
            |
            v
refresh() hoàn tất nếu không có lỗi
```

Spring phát sự kiện trong giai đoạn hoàn tất refresh (`finishRefresh()`). Ở chế độ multicaster mặc định, listener chạy **đồng bộ** ngay trong quá trình phát event. Listener quá chậm hoặc ném exception có thể khiến `refresh()`/khởi động bị chậm hoặc thất bại, tùy cơ chế xử lý lỗi được cấu hình.

Sự kiện **không đồng nghĩa** với:

- Mỗi lần một bean được khởi tạo; bean lazy vẫn có thể được tạo muộn sau khi event đã phát.
- Mỗi lần giá trị thuộc tính thay đổi; thay đổi file cấu hình không tự động khiến event xuất hiện.
- Mọi ứng dụng đều hỗ trợ gọi `refresh()` lặp lại trên cùng context: điều đó phụ thuộc loại `ApplicationContext`.
- Toàn bộ `CommandLineRunner`, `ApplicationRunner` và các bước startup tiếp theo của Spring Boot đã chạy xong.

### So sánh với những sự kiện vòng đời gần nhau

| Sự kiện / callback | Thời điểm hoặc ý nghĩa |
| --- | --- |
| `@PostConstruct` | Sau khi một bean được tiêm dependency và khởi tạo; gắn với **bean**, không với toàn bộ context |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Sau khi các singleton non-lazy thông thường đã được tạo |
| `ContextRefreshedEvent` | Context khởi tạo/refresh xong theo vòng đời Spring |
| `ContextStartedEvent` | Khi gọi `start()` trên context và Spring gửi sự kiện start; **không** phải mặc định mỗi lần khởi động ứng dụng |
| `ContextStoppedEvent` | Khi gọi `stop()` trên context |
| `ContextClosedEvent` | Khi context đang đóng bằng `close()` hoặc cơ chế shutdown tương ứng |
| `ApplicationReadyEvent` (Spring Boot) | Spring Boot đã chạy các runner và sắp kết thúc quy trình khởi động; phù hợp hơn khi cần biết Boot sẵn sàng phục vụ |

Lưu ý: Spring Boot còn có nhiều event khác trong suốt startup. Hai nhóm `Context...Event` của Spring Framework và `Application...Event` của Spring Boot có mục đích và thứ tự khác nhau.

## 3. Hai cách đăng ký listener

### Cách 1: @EventListener

Đặt phương thức có tham số `ContextRefreshedEvent` trong một bean do Spring quản lý:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshLogger {

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        System.out.println("Context refreshed: "
                + event.getApplicationContext().getId());
    }
}
```

Đây là **một lớp để đưa vào ứng dụng Spring sẵn có**. Spring tìm phương thức `@EventListener` và gọi nó khi event có kiểu tương thích được phát. Không cần tự gọi `onRefreshed(...)`.

### Cách 2: ApplicationListener<ContextRefreshedEvent>

Dùng interface khi muốn biểu diễn listener thành một đối tượng có giao diện rõ ràng:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshAudit
        implements ApplicationListener<ContextRefreshedEvent> {

    @Override
    public void onApplicationEvent(ContextRefreshedEvent event) {
        System.out.println("Refreshed context id="
                + event.getApplicationContext().getId());
    }
}
```

Hai đoạn trên minh họa **hai lựa chọn độc lập**. Nếu đưa **cả hai** vào cùng ứng dụng, cả hai listener đều nhận event và đều in log. Không cần đăng ký cùng một tác vụ bằng cả hai cách nếu chỉ muốn nó chạy một lần.

Với `@EventListener`, bean phải được Spring quản lý và cấu hình annotation event listener phải được xử lý. Với Spring Boot và phần lớn cấu hình Spring hiện đại dùng `@Configuration`/component scan, hạ tầng đó đã được thiết lập.

## 4. Ví dụ Java 17+ chạy được chỉ với Spring Framework

Ví dụ này tạo một context bằng `AnnotationConfigApplicationContext`, đặt tên định danh ổn định, đăng ký listener qua `@Bean`, gọi `refresh()` và cuối cùng đóng context. Không cần khởi động web server.

### Cấu trúc project

```text
context-refresh-demo/
├── pom.xml
└── src/main/java/example/lifecycle/ContextRefreshDemo.java
```

### pom.xml

Sử dụng JDK 17+, Maven 3.9+ và Spring Framework 6.2.x trong ví dụ sau (phiên bản cố định để kết quả có thể tái lập):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-refresh-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### ContextRefreshDemo.java

```java
package example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class ContextRefreshDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.setId("demo-context");
            context.register(DemoConfig.class);

            // Khởi tạo bean và phát ContextRefreshedEvent.
            context.refresh();

            System.out.println("ACTIVE: " + context.isActive());
        }
        // try-with-resources gọi close(), dẫn đến ContextClosedEvent.
    }

    @Configuration(proxyBeanMethods = false)
    static class DemoConfig {
        @Bean
        ContextHooks contextHooks() {
            return new ContextHooks();
        }
    }

    static class ContextHooks {

        @EventListener
        public void onRefresh(ContextRefreshedEvent event) {
            String id = event.getApplicationContext().getId();
            System.out.println("REFRESHED: " + id);
        }

        @EventListener
        public void onClose(ContextClosedEvent event) {
            String id = event.getApplicationContext().getId();
            System.out.println("CLOSED: " + id);
        }
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.lifecycle.ContextRefreshDemo
```

Các dòng do chương trình chủ động in ra theo thứ tự (nếu Maven/Spring phát thêm log riêng, chúng không thuộc phần output này):

```text
REFRESHED: demo-context
ACTIVE: true
CLOSED: demo-context
```

**Giải thích vì sao output có thứ tự này:**

1. `new AnnotationConfigApplicationContext()` tạo context **chưa refresh**; ta có thời gian đặt `id` và đăng ký `DemoConfig`.
2. `context.refresh()` dựng các bean, bao gồm `ContextHooks`; cuối giai đoạn này Spring phát `ContextRefreshedEvent` và gọi `onRefresh(...)` trước khi `refresh()` trả về.
3. Lệnh `context.isActive()` được thực hiện sau refresh nên trả về `true`.
4. Khi ra khỏi `try`, `close()` phát `ContextClosedEvent`; `onClose(...)` in dòng cuối.

Chương trình cố tình chỉ gọi `refresh()` **một lần**. Không gọi lại trên `AnnotationConfigApplicationContext` vì nó dựa trên `GenericApplicationContext`, vốn không hỗ trợ refresh lần hai trên cùng instance.

## 5. Ứng dụng thực tế: nên và không nên làm gì ở listener?

Nên cân nhắc `ContextRefreshedEvent` khi một thành phần cần biết rằng **context cụ thể** đã được refresh, chẳng hạn:

- Khởi tạo một cache nhẹ dựa trên các bean đã đăng ký trong context.
- Tổng hợp thông tin cấu hình/runtime đã có sẵn để log hoặc phục vụ chẩn đoán.
- Thực hiện kiểm tra trạng thái container ở mức nhẹ, rõ ràng và có chủ đích.
- Kích hoạt thao tác nội bộ được thiết kế chạy lại an toàn khi context refresh, với điều kiện thao tác không phụ thuộc vào mốc sẵn sàng của Spring Boot.

Không nên dùng listener này để tự động chạy công việc nặng hoặc bắt buộc chỉ một lần toàn hệ thống, ví dụ migration có tác dụng không đảo ngược, thanh toán, gửi email chiến dịch hoặc nạp lượng lớn dữ liệu không kiểm soát. Nếu công việc cần chạy sau khi ứng dụng Spring Boot hoàn tất các runner và sẵn sàng phục vụ, xem xét `ApplicationReadyEvent`. Nếu cần chạy một lần khi bean đã được tiêm phụ thuộc, có thể dùng cơ chế khởi tạo bean thay vì lắng nghe toàn context.

### Giữ phương thức listener mỏng

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    // Ví dụ về cách ủy quyền, không phải chương trình độc lập.
    startupDiagnostics.recordContext(event.getApplicationContext());
}
```

Nội dung trên là **đoạn phương thức minh họa**, giả sử đã có bean `startupDiagnostics` được inject. Cách này gom logic chuyên môn và xử lý lỗi vào một service có thể kiểm thử.

Ở chế độ dispatch mặc định, listener dài sẽ kéo dài thời gian refresh. `@Async` có thể chuyển xử lý ra executor nếu bật `@EnableAsync` và cấu hình phù hợp, nhưng lúc đó kết quả bất đồng bộ không còn là một phần đồng bộ của `refresh()`; cần xử lý lỗi và vòng đời executor riêng. Đừng thêm `@Async` chỉ để che giấu bước khởi tạo quá lớn.

## 6. Tránh xử lý trùng trong hệ thống có parent/child context

Spring có thể tổ chức nhiều `ApplicationContext` theo cây cha–con, ví dụ context gốc và context riêng của một thành phần web. **Event được phát trong context con có thể được chuyển tiếp lên context cha.** Vì vậy, listener trong context cha có thể nhận:

- `ContextRefreshedEvent` phát từ chính context cha.
- `ContextRefreshedEvent` được phát từ một context con rồi chuyển tiếp lên cha.

Nếu không kiểm tra nguồn, logic có thể được kích hoạt nhiều lần khi nhiều context được tạo/refresh. Chỉ lọc bằng kiểu `ContextRefreshedEvent` là chưa đủ để bảo đảm event đến từ context hiện tại.

Khi listener chỉ được phép xử lý refresh của context đang chứa chính bean đó, hãy so sánh **đối tượng context**:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

public class OwnContextRefreshListener {
    private final ApplicationContext ownContext;

    public OwnContextRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Bỏ qua event từ context con khác.
        }

        System.out.println("Own context refreshed");
    }
}
```

Đây là **một lớp minh họa**, cần đăng ký thành bean và inject context chứa nó. So sánh danh tính `!=` phù hợp với mục tiêu "chỉ đúng instance này"; so sánh `getId()` bằng chuỗi có thể nhầm khi các context được đặt trùng ID.

Spring Boot không mặc định mọi ứng dụng đều có nhiều context; hãy kiểm tra kiến trúc thực tế trước khi cho rằng mọi listener đều chạy hai lần.

## 7. Refresh nhiều lần, startup nhiều lần và tính idempotent

Không nên hiểu `ContextRefreshedEvent` là "event chỉ xuất hiện một lần trong toàn bộ vòng đời hệ thống". Có nhiều tình huống:

1. Ứng dụng tạo một context mới: mỗi context được refresh sẽ có event của riêng nó.
2. Một số implementation thuộc nhóm **refreshable context** hỗ trợ refresh lặp lại, có thể phát event lần nữa.
3. Các context cha/con có event của chúng; propagation có thể khiến một listener quan sát nhiều event.
4. Test suite có thể tạo/hủy nhiều context độc lập.
5. Trong Spring Boot, restart ứng dụng tạo vòng đời mới, kể cả khi startup code không thay đổi.

Trái lại, các context thuộc nhóm `GenericApplicationContext` (bao gồm `AnnotationConfigApplicationContext`) không cho phép gọi `refresh()` lần hai trên cùng instance sau lần đầu. Không tạo ví dụ "refresh lại một lần nữa" bằng class này.

Nếu listener thực hiện một hành động mà chạy hai lần là nguy hiểm, hãy xác định rõ phạm vi yêu cầu:

- **Một lần cho mỗi context instance:** chọn nơi lưu trạng thái gắn với context, kiểm tra nguồn event và bảo đảm thao tác có thể hoàn tất an toàn.
- **Một lần cho mỗi lần refresh:** thiết kế thao tác cho phép lặp, tránh thêm record/cấu hình trùng.
- **Một lần toàn bộ hệ thống kể cả restart hay nhiều instance:** cần lưu trạng thái bền vững, khóa phân tán hoặc cơ chế idempotency nghiệp vụ; biến `boolean` trong bean không đủ.

Một cờ `AtomicBoolean` chỉ bảo vệ **instance bean cụ thể**. Nếu refresh tạo lại bean, hoặc ứng dụng có nhiều instance, cờ đó không bảo đảm tính một lần ở cấp hệ thống.

## 8. ContextRefreshedEvent và Spring Boot: đừng nhầm với ApplicationReadyEvent

Trong Spring Boot, event của Spring Framework vẫn được phát khi context refresh. Tuy nhiên, vòng đời startup còn bước chạy các `ApplicationRunner` và `CommandLineRunner` sau refresh. Khái quát:

```text
Spring Boot chuẩn bị và refresh ApplicationContext
       |
       +--> ContextRefreshedEvent
       |
       +--> ApplicationStartedEvent
       |
       +--> ApplicationRunner / CommandLineRunner
       |
       +--> ApplicationReadyEvent
```

Thứ tự này mô tả luồng startup thông thường của Spring Boot; những listener được cấu hình bất đồng bộ có thể hoàn thành ở thời điểm khác. Vì vậy:

- Dùng `ContextRefreshedEvent` khi quan tâm đến trạng thái **container đã refresh**.
- Dùng `ApplicationReadyEvent` khi muốn phản ứng ở mốc **Boot startup đã hoàn tất các runner**.
- Nếu cần điều khiển chính xác trạng thái nhận traffic của ứng dụng, dùng cơ chế readiness/availability của Boot thay vì dựa vào log của một listener.
- Nếu xử lý event của Spring Boot rất sớm, phải xét khả năng `ApplicationContext` chưa sẵn sàng; không áp logic đó ngược lên `ContextRefreshedEvent`.

Việc listener nhận `ContextRefreshedEvent` không có nghĩa mọi service bên ngoài như database, broker hoặc cổng remote đều đang hoạt động tốt. Với những dependency có thể mất kết nối sau startup, phải có health check và cơ chế phục hồi riêng.

## 9. Đồng bộ, lỗi và trách nhiệm của listener

Mặc định `SimpleApplicationEventMulticaster` dispatch event bằng lời gọi trên luồng phát sự kiện. Hệ quả là:

- Một listener có thể làm chậm `refresh()` hoặc chặn startup khi đang truy cập mạng/DB.
- Runtime exception từ listener đồng bộ có thể lan ngược về nơi publish; trong quá trình refresh, điều này có thể khiến khởi động thất bại.
- Nếu cấu hình executor hoặc gắn `@Async`, cần phân biệt lỗi **submit** và lỗi khi task đã bắt đầu chạy; lỗi bất đồng bộ thường không lan trực tiếp ngược về lời gọi `refresh()`.
- Không giả định thứ tự hoàn thành listener chạy async, kể cả khi có `@Order` để sắp thứ tự dispatch.
- Listener chạy trong giai đoạn vòng đời phải được thiết kế để không phụ thuộc vào một callback startup diễn ra **sau** refresh.

Khi cần xử lý khối lượng công việc lớn sau startup, hãy tách thành một job/service có khả năng theo dõi tiến độ, timeout, retry và dừng có kiểm soát. Event nên là **tín hiệu khởi động công việc**, không trở thành nơi nhồi toàn bộ xử lý hoặc giả lập một hệ thống job queue.

## 10. Kiểm thử đúng hành vi

### Kiểm thử không cần Spring Boot

Ví dụ chính ở mục 4 đã chứng minh ba mốc: phát refresh, context active và phát close. Khi kiểm thử chuyên nghiệp, không nên phụ thuộc hoàn toàn vào `System.out`; thay bằng một service ghi nhận các lần callback để assert:

| Tình huống | Kỳ vọng |
| --- | --- |
| Tạo context nhưng chưa gọi `refresh()` | Chưa có `ContextRefreshedEvent` do context đó phát |
| Gọi `refresh()` thành công | Listener của context nhận đúng một event cho thao tác refresh đó, nếu không có đường truyền event khác |
| Gọi `close()` sau refresh | Có `ContextClosedEvent`; không tự tạo `ContextRefreshedEvent` mới |
| Listener đặt trong context cha; refresh context con | Listener cha có thể nhận event của context con |
| Listener kiểm tra `event.getApplicationContext() != ownContext` | Bỏ qua event của context khác |
| Gọi refresh lại trên `AnnotationConfigApplicationContext` | Không được hỗ trợ; không dùng thao tác này làm bài test refresh lặp |
| Listener xử lý chậm ở chế độ đồng bộ | Tổng thời gian refresh có thể tăng |
| Khởi động Spring Boot và chạy runner | `ContextRefreshedEvent` đến trước mốc `ApplicationReadyEvent` trong startup thường |

Nên kiểm thử tối thiểu: listener nhận event đúng kiểu; filter theo context nguồn; nhánh xử lý thành công; lỗi từ dependency; và việc khởi tạo lại context không tạo tác dụng phụ trùng. Nếu cần kiểm thử idempotency ở cấp đa instance, phải sử dụng storage/lock thật hoặc một mô phỏng phù hợp.

### Cách đọc event source

Gọi `event.getApplicationContext()` trả về nguồn event là `ApplicationContext`. Không ép kiểu sang `AnnotationConfigApplicationContext`, `WebApplicationContext` hay implementation cụ thể trừ khi use case thực sự cần và đã kiểm tra kiểu. Ưu tiên interface chung; nhờ vậy listener ít phụ thuộc cấu trúc triển khai.

## 11. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Dùng ContextRefreshedEvent thay cho @PostConstruct.** Nếu chỉ cần xây dựng trạng thái bên trong một bean từ dependency của chính nó, hãy dùng cơ chế khởi tạo bean. Chỉ lắng nghe context refresh khi công việc phụ thuộc vào mốc toàn container.

**Lỗi 2 — Cho rằng event chỉ xuất hiện một lần.** Kiểm tra loại context, context hierarchy, test lifecycle và khả năng restart; thiết kế xử lý lặp an toàn.

**Lỗi 3 — Không lọc context nguồn.** Trong hệ thống có cha–con, listener ở context cha có thể xử lý cả event từ con. So sánh identity của `getApplicationContext()` với context đang sở hữu bean.

**Lỗi 4 — Gọi xử lý nặng trực tiếp trong listener.** Với dispatch mặc định, listener đang nằm trên đường startup. Chuyển logic phức tạp vào service phù hợp, đo thời gian, chọn cơ chế async hoặc job riêng khi có nhu cầu rõ ràng.

**Lỗi 5 — Nhầm event với trạng thái sẵn sàng phục vụ.** Trong Boot, `ApplicationReadyEvent` là mốc muộn hơn; readiness/health phản ánh khả năng phục vụ tốt hơn một log startup.

**Lỗi 6 — Đăng ký hai listener cho cùng một công việc.** `ApplicationListener` và `@EventListener` đều hợp lệ; nếu cùng gọi một service mà không có guard, công việc có thể chạy hai lần.

**Lỗi 7 — Tự gọi onRefreshed(event) trong code nghiệp vụ.** Hãy để Spring dispatch sự kiện; nếu cần logic có thể được gọi từ nhiều nơi, tách ra thành method/service độc lập rồi gọi có chủ đích.

**Lỗi 8 — Mặc định mọi bean đã tồn tại.** Bean lazy hoặc prototype có thể chưa được tạo tại thời điểm event xảy ra. "Context refreshed" không đảm bảo mọi bean ở mọi scope đều đã được instantiate.

## 12. Checklist áp dụng

Trước khi dùng `ContextRefreshedEvent`, hãy trả lời:

1. Tôi thật sự cần mốc **container refresh** hay cần mốc bean init / Spring Boot ready?
2. Listener được Spring quản lý và đăng ký đúng cách chưa?
3. Ứng dụng có parent/child context hoặc nhiều context độc lập không?
4. Nếu event đến nhiều lần, tác vụ có idempotent không, và ở cấp độ nào?
5. Logic listener có đủ nhẹ để chạy trên luồng refresh không?
6. Nếu listener lỗi, startup cần thất bại hay có thể tiếp tục? Đã thiết kế đường xử lý chưa?
7. Có integration test cho refresh, close, sự kiện từ context con và trường hợp khởi động lại chưa?

**Điểm cốt lõi:** `ContextRefreshedEvent` là tín hiệu Spring đã hoàn tất **một chu kỳ refresh của một ApplicationContext cụ thể**. Hãy dùng nó cho công việc gắn với vòng đời container, kiểm tra nguồn context khi cần và thiết kế handler an toàn khi event lặp.

## Tài liệu tham khảo

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): sự kiện trong ApplicationContext và event lifecycle.
- [Spring Framework API — ContextRefreshedEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html): lớp event và constructor.
- [Spring Framework API — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): refresh và finishRefresh.
- [Spring Boot — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): thứ tự event khởi động của Boot.
