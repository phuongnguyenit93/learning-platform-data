# Parent context và lifecycle event

Trong Spring Framework, một ứng dụng có thể có nhiều `ApplicationContext` theo quan hệ **parent–child**. Quan hệ này ảnh hưởng đến cách tra cứu bean và, đặc biệt, **đường đi của application event**. Một listener được đăng ký ở parent có thể nhận cả lifecycle event do child phát ra. Nếu listener coi mọi `ContextRefreshedEvent` nó nhận được là sự kiện khởi tạo của chính parent, logic khởi tạo có thể chạy thừa hoặc chạy sai phạm vi.

Bài học này giải thích chính xác Spring chuyển lifecycle event giữa các context như thế nào, cách nhận biết context tạo event, cách kiểm soát listener và cách quản lý vòng đời của cả cây context.

## 1. Parent–child ApplicationContext là gì?

`ApplicationContext` là container quản lý bean và cung cấp các khả năng như publish event, truy cập resource và quản lý lifecycle. Một context có thể khai báo parent bằng `setParent(...)` trên các triển khai cho phép cấu hình, chẳng hạn `AnnotationConfigApplicationContext`.

Ví dụ về cấu trúc phân cấp:

~~~text
Parent ApplicationContext
├── bean: sharedService
├── listener: parentListener
└── Child ApplicationContext
    ├── bean: requestHandler
    └── listener: childListener
~~~

Các điểm quan trọng:

- Child có thể tìm bean từ parent nếu bean đó không có trong container cục bộ và cách tra cứu cho phép. Một bean cùng tên trong child có thể che khuất bean ở parent trong quá trình lookup.
- Parent **không tự thấy bean chỉ tồn tại trong child**. Quan hệ này không làm hai registry bean thành một registry chung.
- Mỗi context có **multicaster** và registry listener riêng. Spring không yêu cầu mọi listener thuộc cùng một context.
- Event do child phát ra được xử lý ở child rồi **truyền lên parent** trong cơ chế `publishEvent(...)` của `AbstractApplicationContext`. Event do parent phát ra **không tự truyền xuống child**.

Hình dung đường đi của event:

~~~text
                    parentListener
                          ▲
                          │ event từ child được chuyển lên
                 [PARENT CONTEXT]
                          ▲
                          │
                    [CHILD CONTEXT]
                          │
                    childListener

Event nguồn CHILD: childListener -> parentListener
Event nguồn PARENT: parentListener
~~~

Đây là **hướng truyền event**, không phải hướng gọi method hay thứ tự tạo bean. Khi có nhiều cấp `grandchild → child → parent`, một event từ grandchild có thể đi tiếp lên các ancestor theo từng cấp.

## 2. Những lifecycle event chuẩn cần phân biệt

Spring cung cấp các loại event kế thừa `ApplicationContextEvent`:

| Event | Nguyên nhân thông thường | Ý nghĩa |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context đã được khởi tạo hoặc `refresh()` thành công | Container đó đã hoàn tất quá trình refresh |
| `ContextStartedEvent` | Gọi `start()` trên context | Context phát tín hiệu start sau khi gọi cơ chế lifecycle tương ứng |
| `ContextStoppedEvent` | Gọi `stop()` trên context | Context phát tín hiệu stop sau khi thực hiện bước lifecycle tương ứng |
| `ContextClosedEvent` | Gọi `close()` hoặc hoàn tất đường shutdown thích hợp | Context đóng và công bố event trước khi kết thúc dọn tài nguyên |

Các sự kiện này khác nhau:

- `refresh()` dựng hoặc làm mới cấu hình container theo khả năng của từng triển khai; nó **không đồng nghĩa** với `start()`. Trong quá trình refresh, Spring có thể tự khởi động các bean `SmartLifecycle` đủ điều kiện; điều đó vẫn không có nghĩa context bắt buộc phát `ContextStartedEvent`.
- `start()` và `stop()` gọi `LifecycleProcessor` để điều phối các bean thực hiện interface `Lifecycle`/`SmartLifecycle`. Chúng không tạo lại container và không tương đương với đóng context.
- `close()` là kết thúc vòng đời context: ngoài event, Spring còn thực hiện stop/destroy bean và đóng bean factory. Sau khi đóng, không dùng lại context như một container đang hoạt động.
- **ContextRefreshedEvent không phải bằng chứng “chỉ chạy một lần trong toàn bộ ứng dụng”**. Có thể có nhiều context trong hierarchy và một số triển khai hỗ trợ refresh nhiều lần.

Tất cả bốn event đều giữ tham chiếu đến **context phát event**, có thể truy cập bằng:

~~~java
ApplicationContext origin = event.getApplicationContext();
~~~

Đoạn trên giả định `event` thuộc kiểu `ApplicationContextEvent` và đã import `org.springframework.context.ApplicationContext`. Context nguồn **không đổi thành parent** chỉ vì event được truyền lên parent.

## 3. Đường đi của lifecycle event trong hierarchy

Giả sử có đúng hai context: parent `P` và child `C`; mỗi context có một listener ghi log.

### Khi refresh parent

~~~text
parent.refresh()
    -> P phát ContextRefreshedEvent(source=P)
    -> listener của P nhận 1 lần
~~~

Child không tự nhận event từ parent vì Spring không broadcast theo chiều đi xuống.

### Khi refresh child

~~~text
child.refresh()
    -> C phát ContextRefreshedEvent(source=C)
    -> listener của C nhận
    -> AbstractApplicationContext chuyển event lên parent P
    -> listener của P cũng nhận event source=C
~~~

Vì vậy, **parent listener có thể nhận ít nhất hai lần `ContextRefreshedEvent`** trong chuỗi khởi tạo parent rồi child: lần đầu từ parent, lần sau từ child. Đây là hai event hợp lệ của **hai context khác nhau**.

Cơ chế tương tự áp dụng với `ContextStartedEvent`, `ContextStoppedEvent` và `ContextClosedEvent` khi từng context thực sự phát chúng. Không nên suy đoán rằng mọi event mà listener parent nhìn thấy đều mô tả lifecycle của parent.

### Hai khái niệm dễ bị nhầm

- **Listener được đăng ký ở đâu?** Parent có registry listener của parent, child có registry listener của child.
- **Event bắt nguồn từ context nào?** Kiểm tra `event.getApplicationContext()` (và có thể `getId()` để ghi log). Vị trí listener được gọi **không tự xác định** context nguồn.

Nếu cùng một instance listener bị đăng ký thủ công ở **cả child và parent**, event từ child có thể khiến chính instance đó được gọi ở hai registry khác nhau. Việc lọc theo context nguồn giúp phân biệt nguồn, nhưng không tự giải quyết trường hợp một instance được đăng ký trùng ở nhiều multicaster.

## 4. Demo Java 17+ có thể chạy độc lập

Ví dụ chỉ dùng `spring-context`: không cần Spring Boot, servlet hay database. Mỗi context đăng ký một listener `ApplicationListener<ApplicationContextEvent>` để in tên event và context nguồn.

Cấu trúc:

~~~text
context-event-hierarchy/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextHierarchyDemo.java
~~~

Tạo `settings.gradle`:

~~~groovy
rootProject.name = 'context-event-hierarchy'
~~~

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.ContextHierarchyDemo'
}
~~~

Tạo `src/main/java/demo/ContextHierarchyDemo.java`:

~~~java
package demo;

import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ApplicationContextEvent;

public final class ContextHierarchyDemo {

    static final class LifecycleLogger
            implements ApplicationListener<ApplicationContextEvent> {

        private final String registeredAt;

        LifecycleLogger(String registeredAt) {
            this.registeredAt = registeredAt;
        }

        @Override
        public void onApplicationEvent(ApplicationContextEvent event) {
            String name = event.getClass().getSimpleName();
            String origin = event.getApplicationContext().getId();

            System.out.println(
                registeredAt + " <- " + name + " @ " + origin
            );
        }
    }

    public static void main(String[] args) {
        // Đăng ký listener trước khi refresh để thấy lifecycle event.
        try (var parent = new AnnotationConfigApplicationContext()) {
            parent.setId("parent");
            parent.addApplicationListener(
                new LifecycleLogger("P")
            );
            parent.refresh();

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setId("child");
                child.setParent(parent);
                child.addApplicationListener(
                    new LifecycleLogger("C")
                );

                child.refresh();
                child.start();
                child.stop();
            } // child.close(): phát ContextClosedEvent của child
        }     // parent.close(): phát ContextClosedEvent của parent
    }
}
~~~

Chạy bằng Java 17+ và Gradle:

~~~bash
gradle run --quiet
# Hoặc dùng Gradle Wrapper sẵn có: ./gradlew run --quiet
# Trên Windows: gradlew.bat run --quiet
~~~

Với các listener đăng ký như trên và multicaster mặc định chạy đồng bộ, các dòng do `System.out.println` phát ra theo thứ tự:

~~~text
P <- ContextRefreshedEvent @ parent
C <- ContextRefreshedEvent @ child
P <- ContextRefreshedEvent @ child
C <- ContextStartedEvent @ child
P <- ContextStartedEvent @ child
C <- ContextStoppedEvent @ child
P <- ContextStoppedEvent @ child
C <- ContextClosedEvent @ child
P <- ContextClosedEvent @ child
P <- ContextClosedEvent @ parent
~~~

Giải thích đầu ra:

1. Parent được refresh trước nên **chỉ P** nhận event nguồn `parent`.
2. Child refresh sau đó: **C** nhận event nguồn `child`; cùng event này được chuyển lên parent, **P** cũng nhận. Đây là nguyên nhân thường khiến parent thấy nhiều `ContextRefreshedEvent`.
3. `child.start()` và `child.stop()` tạo event có nguồn `child`. Mỗi event được xử lý ở child rồi ở parent.
4. Khi kết thúc khối try bên trong, `child.close()` tạo `ContextClosedEvent` của child; P cũng thấy event đó.
5. Khi kết thúc khối try bên ngoài, `parent.close()` tạo `ContextClosedEvent` của parent. Không có thêm listener nào thuộc child nhận event này.

**Quan sát quan trọng:** dòng `P <- ContextClosedEvent @ child` không có nghĩa parent đã đóng; nó chỉ cho biết **listener của parent nhận tin child đã đóng**. Parent tiếp tục hoạt động cho tới khi chính parent được đóng.

Dữ liệu demo chỉ chứa listener và cơ chế container, nên không có bean nghiệp vụ làm thay đổi log. Nếu cấu hình multicaster riêng với executor hoặc listener bất đồng bộ, thứ tự chạy callback có thể khác. Ví dụ này dùng mặc định đồng bộ để dễ quan sát.

## 5. Làm sao để listener chỉ phản ứng với lifecycle của context sở hữu nó?

Trong thực tế, một listener của parent có thể muốn khởi tạo cache hoặc scheduler **chỉ khi parent refresh**, không phải khi bất kỳ child nào refresh.

Cách kiểm tra đáng tin cậy nhất là so sánh **chính đối tượng context**, không đếm số lần event:

~~~java
// Đoạn minh họa: đặt listener bên trong bean do parent quản lý.
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class ParentInitializationHandler implements ApplicationContextAware {

    private ApplicationContext owningContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owningContext = context;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owningContext) {
            return; // Event của child: parent nhận qua propagation.
        }

        // Khởi tạo tài nguyên gắn với chính owningContext ở đây.
        System.out.println("own context refreshed");
    }
}
~~~

Đoạn code này minh họa một **Spring component** cần được đặt trong context cần quản lý (ví dụ parent) và quét component; nó không phải file chạy độc lập. `ApplicationContextAware` giúp bean biết container thực sự quản lý nó. Khi event đến, so sánh tham chiếu bằng `!=` hoặc `==`.

Một biến thể không dùng `ApplicationContextAware` là inject context vào constructor của listener rồi kiểm tra `event.getApplicationContext() == injectedContext`; điều kiện cần là đối tượng được inject đúng context sở hữu listener.

### Vì sao không chỉ so sánh tên class hoặc dựa vào số lần chạy?

- Hai context có thể cùng là `AnnotationConfigApplicationContext` nhưng đại diện hai container khác nhau.
- ID như `"parent"` và `"child"` có ích cho log, nhưng so sánh object tránh phụ thuộc quy ước đặt ID. Nếu dùng ID thì phải bảo đảm ID được cấu hình duy nhất theo hệ thống.
- Dùng `boolean initialized` để bỏ qua event thứ hai có thể che lỗi triển khai, bỏ sót refresh hợp lệ hoặc phụ thuộc thứ tự khởi động.
- Lọc theo event class (`ContextRefreshedEvent`) vẫn chưa đủ: parent và child đều phát **cùng một class event**.

Nếu muốn xử lý **cả parent và child**, không dùng điều kiện lọc này; thay vào đó phân loại rõ `event.getApplicationContext()` và bảo đảm thao tác có tính lặp an toàn (*idempotent*) khi cần.

## 6. Quan hệ bean visibility khác với propagation của event

Từ child, có thể tra cứu bean của parent:

~~~java
// Minh họa trong mã có parent và child đã khởi tạo:
SharedService service = child.getBean(SharedService.class);
~~~

Điều này không có nghĩa event trong parent sẽ được gửi tới listener trong child. Bean lookup và event routing là **hai cơ chế khác nhau**.

Trong Spring MVC với cấu hình nhiều context, ứng dụng có thể có root context cho service chung và child context cho từng `DispatcherServlet`. Một `ContextRefreshedEvent` của child có thể tới listener ở root. Các ứng dụng Spring Boot đơn giản có thể chỉ dùng một context; không nên mặc định mọi ứng dụng đều có root–child hierarchy.

Một tình huống khác là ứng dụng tạo nhiều child cùng parent:

~~~text
          ROOT context
          /          \
      CHILD A       CHILD B
~~~

- Event phát từ A có thể đến listener của A và root; **không tự chuyển ngang sang B**.
- Event phát từ B có thể đến listener của B và root; **không tự chuyển ngang sang A**.
- Root listener có thể quan sát event từ cả A và B. Phân biệt nguồn bằng `getApplicationContext()` khi cần.

Đây là điểm quan trọng khi một root context tổng hợp log, metric hoặc thực hiện thao tác cấp ứng dụng.

## 7. Start, stop và close có tự lan theo quan hệ parent–child không?

**Event propagation không đồng nghĩa lifecycle orchestration.** Khi gọi `child.start()`:

- Spring chạy cơ chế `LifecycleProcessor` của **child**, điều phối bean lifecycle trong child.
- Child công bố `ContextStartedEvent`; parent listener có thể nhận event vì event đi lên.
- Sự kiện đi lên **không có nghĩa** Spring vừa gọi `parent.start()` hoặc khởi động lại các bean lifecycle của parent.

Tương tự với `child.stop()` và `child.close()`. Parent quan sát event của child mà không tự bị stop hoặc close theo.

Khi tạo hierarchy bằng code, nên **khởi tạo parent trước child và đóng child trước parent** như demo. Quan hệ tham chiếu parent trong `ApplicationContext` tự thân không phải hợp đồng quản lý toàn bộ tiến trình shutdown mọi descendant. Nếu một framework/container ngoài quản lý cả hai, tuân theo vòng đời framework đó; nếu tự dựng context, chủ động quản lý từng context.

Không nên cố `refresh()` một `GenericApplicationContext` đã refresh/đóng để phát lại event: khả năng refresh nhiều lần tùy loại context. Nếu cần chạy công việc sau mọi lần startup, hãy chọn lifecycle API phù hợp và thiết kế idempotent.

## 8. Chọn đúng hook cho mục tiêu nghiệp vụ

| Mục tiêu | Hook nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Khởi tạo trạng thái riêng của một bean | Constructor / `InitializingBean` / `@PostConstruct` | Không cần quan sát mọi context; chạy theo lifecycle bean |
| Chạy sau khi context hoàn tất refresh | `ContextRefreshedEvent` + lọc theo context | Parent có thể thấy event child; listener phải biết nguồn |
| Phối hợp start/stop tài nguyên | `Lifecycle` / `SmartLifecycle` | Do `LifecycleProcessor` quản lý; có phase và điều phối start/stop |
| Thu dọn khi container đóng | `@PreDestroy` / `DisposableBean` | Cleanup theo bean; không phụ thuộc việc nhận event từ child |
| Quan sát trạng thái đóng của nhiều context | `ContextClosedEvent` ở root listener | Dùng nguồn event để phân biệt context nào đóng |
| Chạy sau khi app Spring Boot sẵn sàng phục vụ | Các application event cấp Boot, ví dụ `ApplicationReadyEvent` | Thuộc Spring Boot, không đồng nghĩa `ContextRefreshedEvent` của Spring Framework |

Ví dụ lỗi thường gặp:

~~~java
@EventListener(ContextRefreshedEvent.class)
public void warmUpCache(ContextRefreshedEvent event) {
    // Nếu bean ở parent, đoạn này có thể chạy với event của child.
    warmUpEverything();
}
~~~

Hãy bổ sung điều kiện `"event.getApplicationContext() == owningContext"` nếu cache chỉ thuộc một context. Đoạn minh họa trên cần các method, import và bean xung quanh; không phải chương trình độc lập.

## 9. Các lỗi phổ biến và cách kiểm tra

**Lỗi 1: Parent listener xử lý hai lần sau startup.** Kiểm tra log `event.getClass().getSimpleName()` và `event.getApplicationContext().getId()`. Nếu một lần nguồn parent, một lần nguồn child thì đây là propagation hợp lệ; thêm lọc theo context sở hữu nếu chỉ muốn một nguồn.

**Lỗi 2: Chờ child listener nhận event parent.** Spring mặc định phát event theo chiều lên. Muốn thông báo child, chủ động phát event vào child context hoặc xây kênh điều phối rõ ràng. Không dựa vào bean visibility.

**Lỗi 3: Nhầm “parent nhận ContextClosedEvent” thành “parent đã shutdown”.** Kiểm tra `getApplicationContext()`: event có thể xuất phát từ child, còn parent vẫn đang chạy.

**Lỗi 4: Đăng ký một instance listener ở cả hai multicaster.** Điều tra địa điểm đăng ký listener và tránh thêm cùng instance không chủ ý. Khi cần, tách listener theo context hoặc bảo đảm xử lý idempotent; lọc nguồn một mình có thể chưa giải quyết lời gọi lặp nếu cùng instance hiện diện ở cả hai registry.

**Lỗi 5: Dùng `ContextRefreshedEvent` thay `SmartLifecycle` cho công việc cần stop/start.** Phân biệt thời điểm refresh, start, stop và close. Không dùng sự kiện refresh để giả lập đầy đủ cơ chế lifecycle của bean.

**Lỗi 6: Viết test phụ thuộc vào log hoặc thứ tự bất đồng bộ.** Nếu cần kiểm tra routing, đăng ký listener thu event vào collection thread-safe, tạo parent và child theo thứ tự rõ ràng, và assert **event class + context nguồn**. Chỉ khẳng định thứ tự dispatch khi cấu hình multicaster đồng bộ đã biết.

### Checklist kiểm thử ngắn

1. Refresh parent và xác nhận parent listener nhận đúng `ContextRefreshedEvent(source=parent)`.
2. Refresh child và xác nhận child listener nhận event source=child; parent cũng nhận event source=child.
3. Gọi `child.start()`, `child.stop()` rồi `child.close()`, xác nhận parent quan sát được sự kiện của child nhưng các sự kiện giữ nguyên context nguồn.
4. Đóng parent sau cùng, xác nhận listener child không tự nhận event đóng parent.
5. Nếu thêm listener chỉ dành cho parent, kiểm thử điều kiện `event.getApplicationContext() == owningContext` bằng cả hai nguồn.

## 10. Tóm tắt cơ chế

~~~text
Quan hệ parent–child:
  Bean lookup: child -> parent (khi cần)
  Event propagation: child -> parent
  Event parent -> child: không tự động

Lifecycle event:
  ContextRefreshedEvent : refresh hoàn tất
  ContextStartedEvent   : start
  ContextStoppedEvent   : stop
  ContextClosedEvent    : close

Listener ở parent nhận event của child:
  getApplicationContext() == child
  -> parent quan sát event của child; parent chưa chắc đổi trạng thái

Chỉ xử lý lifecycle của chính context:
  event.getApplicationContext() == owningContext
~~~

## Tài liệu tham khảo

- [Spring Framework 6.2 — Additional Capabilities of the ApplicationContext](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [AbstractApplicationContext — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [ApplicationContextEvent — Spring Framework Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [Spring Framework source — AbstractApplicationContext.publishEvent()](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)
