# Parent-child context nhận event ngoài dự kiến trong Spring Framework

## 1. Hiện tượng: listener ở parent chạy dù event được phát từ child

Trong ứng dụng có **nhiều Spring ApplicationContext được tổ chức theo quan hệ parent–child**, một tình huống chẩn đoán sự cố điển hình là:

- Một service nằm trong **child context** publish event.
- Listener ở **child context** xử lý đúng như dự kiến.
- Nhưng listener ở **parent context** cũng nhận event, dù người viết chỉ nghĩ event thuộc phạm vi child.
- Với các event vòng đời như **ContextRefreshedEvent**, một listener trong parent có thể được gọi nhiều lần vì parent và child đều có vòng đời khởi tạo riêng.
- Nếu cả parent và child cùng đăng ký handler thực hiện một side effect, ta có thể thấy hai dòng log, hai lần tăng metric hoặc hai lần gửi thông báo cho một hành động nghiệp vụ.

Đây **không nhất thiết là lỗi Spring hay event được publish hai lần ở application code**. Theo cơ chế **ApplicationContext event propagation**, event phát từ child context được chuyển tiếp **lên các ancestor contexts**. Mỗi context có hệ thống listener của chính nó; vì vậy parent listener có thể quan sát event do child phát.

Sơ đồ:

~~~text
            ROOT / PARENT APPLICATION CONTEXT
            +---------------------------------+
            | parent listeners                |
            | @EventListener on(MyEvent)      |
            +----------------^----------------+
                             |
                   event bubbles UP
                             |
            CHILD APPLICATION CONTEXT
            +---------------------------------+
            | publisher.publishEvent(MyEvent) |
            | child listeners                 |
            | @EventListener on(MyEvent)      |
            +---------------------------------+
~~~

**Chiều mặc định cần nhớ:** **child → parent → grandparent**; không có cơ chế **parent → child** hoặc **child A → child B** tự động chỉ vì chúng thuộc cùng một hierarchy.

**Mục tiêu bài học** thuộc phần **Chẩn đoán sự cố**: xác định event đến từ context nào, vì sao cùng loại event có thể được xử lý nhiều lần, phân biệt event lifecycle và POJO payload, viết chương trình tái hiện Java 17+, và lựa chọn cách xử lý đúng thay vì chỉ “tắt listener cho đỡ log”.

## 2. ApplicationContext hierarchy hoạt động như thế nào?

### 2.1. Parent–child không phải chỉ là cách đặt tên bean

Một **ApplicationContext hierarchy** là quan hệ thực giữa các context. Child có thể truy cập nhiều bean, property hoặc resource của parent tùy cơ chế lookup; parent **không** mặc nhiên nhìn thấy bean riêng của child. Hai context vẫn là **hai đơn vị lifecycle, listener registry và configuration** khác nhau.

Ví dụ:

~~~text
RootContext (parent)
  +-- commonService
  +-- parentEventListener
  |
  +-- WebContext (child)
       +-- controller
       +-- childEventListener
~~~

Một bean được tạo trong parent và inject **ApplicationEventPublisher** thường được gắn với **publisher của parent context**. Ngược lại, một bean trong child thường dùng publisher của child. Vì thế “request đến từ child” **không đủ** để kết luận event được publish bằng child publisher: phải xem **bean thực sự thực hiện publish nằm trong context nào**, và publisher nào đã được inject.

Đừng nhầm **bean visibility** với **event propagation**:

| Khía cạnh | Hướng mặc định |
| --- | --- |
| Child tra cứu bean của parent | Có thể truy cập theo bean lookup phù hợp |
| Parent tra cứu bean chỉ tồn tại trong child | Không tự động |
| Event publish qua **child context** | Child listeners nhận, sau đó event chuyển lên ancestor |
| Event publish qua **parent context** | Parent listeners nhận; không tự broadcast xuống child |
| Event publish qua sibling child A | A và ancestor nhận; sibling B không tự nhận |
| Listener thuộc parent nhưng được inject vào child | Vẫn là bean parent và thường phụ thuộc publisher parent nếu nó tự publish |

**Quan trọng:** Mỗi context có thể có **ApplicationEventMulticaster** riêng. Việc parent nhận event của child không có nghĩa mọi listener được gom vào một registry toàn cục; Spring chuyển tiếp publication qua hierarchy.

### 2.2. Luồng Spring publish event

Với các context thông dụng kế thừa **AbstractApplicationContext**, quá trình publish có thể hiểu như sau:

1. Một object được gửi tới **ApplicationEventPublisher.publishEvent(Object)**.
2. Context hiện tại chuyển object thành **ApplicationEvent** thích hợp nếu cần.
3. Context dispatch cho các listener đăng ký trong context đó bằng **ApplicationEventMulticaster**.
4. Nếu có parent, event gốc cũng được publish vào parent context.
5. Parent lại dispatch cho listener của nó và chuyển tiếp lên grandparent nếu có.

Mô hình:

~~~text
child.publishEvent(event)
   |
   +--> child.multicaster -> child local listeners
   |
   +--> parent.publishEvent(event)
          |
          +--> parent.multicaster -> parent local listeners
          |
          +--> grandparent.publishEvent(event)
                 |
                 +--> grandparent listeners
~~~

Nếu dùng **SimpleApplicationEventMulticaster** đồng bộ mặc định, callback child thường chạy trước khi publication được chuyển lên parent. Với **@Async** hoặc custom executor, **thứ tự hoàn thành** và **thread thực thi** có thể khác; không được dùng thứ tự log làm hợp đồng nghiệp vụ xuyên nhiều context.

Cơ chế này là **in-process**, không tự là message broker, queue bền vững hoặc distributed event bus.

## 3. Vì sao listener có thể nhận event “ngoài dự kiến”?

### 3.1. Một event từ child đến cả child và parent

Nếu cả hai context có listener cùng nhận **OrderConfirmed**, mỗi listener có thể được gọi một lần cho event được publish qua child. Từ góc nhìn nghiệp vụ, nếu hai listener cùng gọi một notification service, kết quả có thể giống “bị xử lý trùng”.

Đó là **hai subscription hợp lệ ở hai context**, không nhất thiết cùng một listener bị Spring gọi hai lần trong một registry.

### 3.2. Hai context tự phát event lifecycle cùng loại

Khi **parent.refresh()** và **child.refresh()**, mỗi context có thể phát **ContextRefreshedEvent** của chính mình. Parent listener có thể nhận:

- **ContextRefreshedEvent** có source là **parent context**.
- **ContextRefreshedEvent** có source là **child context**, được forward lên parent.

Do đó một listener ở parent lắng nghe **ContextRefreshedEvent** có thể chạy **hai lần với hai nguồn khác nhau**. Điều tương tự cần chú ý khi shutdown/close với **ContextClosedEvent**.

Đặc biệt với Spring Boot dùng **SpringApplicationBuilder** tạo hierarchy, reference documentation cũng cảnh báo rằng listener có thể nhận nhiều event cùng loại trong một hierarchy.

### 3.3. Cấu hình hoặc component scan tạo bean listener ở nhiều context

Nếu parent và child đều quét cùng package, cùng class **@Component** có thể được tạo thành **hai bean instances riêng**, mỗi instance đăng ký listener vào context của nó. Event từ child sẽ đi qua cả hai registry. Lúc này ngoài event propagation còn có **duplicate registration ở mức kiến trúc**.

Đừng kết luận rằng listener instance bị tạo hai lần nếu chưa kiểm tra. Cần phân biệt:

- **Một bean parent** nhận event do child forward.
- **Một bean trong parent và một bean trong child** cùng xử lý.
- **Hai registration trong cùng context** do cấu hình trùng.
- **Ứng dụng thực sự publish hai event** trong cùng use case.
- **Broker redelivery hoặc retry** (nếu event từ messaging infrastructure).

Năm tình huống này có cách khắc phục khác nhau.

### 3.4. Dùng listener quá rộng

Các listener như **ApplicationListener<ApplicationEvent>** hoặc method nhận **ApplicationEvent** có thể bắt nhiều event của framework: **ContextRefreshedEvent**, **ContextClosedEvent**, **ContextStartedEvent** và các event custom kế thừa **ApplicationEvent**. Trong hierarchy, số lần gọi còn tăng vì forwarding.

Một listener có mục tiêu gửi email khi đơn được xác nhận nên nhận **OrderConfirmed**, không nên nhận mọi **ApplicationEvent** rồi cố đoán business type từ **toString()** hoặc log.

## 4. Xác định context nguồn: khác biệt quan trọng giữa hai kiểu event

Đây là phần dễ mắc lỗi nhất khi debug.

### 4.1. ApplicationContextEvent có API nhận diện context gốc

Với các event vòng đời kế thừa **ApplicationContextEvent**, chẳng hạn **ContextRefreshedEvent** hoặc **ContextClosedEvent**, dùng:

~~~java
ApplicationContext origin = event.getApplicationContext();
~~~

Đây là API của Spring, trả context gắn với lifecycle event đó. Một parent listener có thể so sánh **origin** với context đang sở hữu listener để biết sự kiện là của **chính parent** hay của **descendant**.

Ví dụ:

~~~java
@Component
public final class LocalLifecycleListener
        implements ApplicationContextAware {

    private ApplicationContext owner;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.owner = context;
    }

    @EventListener
    public void on(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != owner) {
            // Đây là refresh event từ descendant; bỏ qua.
            return;
        }
        // Chỉ xử lý khi chính context chứa listener được refresh.
    }
}
~~~

Đây là **snippet**, cần các Spring imports và component scanning hoặc bean registration phù hợp. Dùng so sánh **identity (== hoặc !=)** cho object **ApplicationContext** khi cần xác định đúng instance; không chỉ so sánh tên class hoặc displayName.

### 4.2. Custom ApplicationEvent có thể lưu context vào source

Nếu tự tạo lớp con của **ApplicationEvent**, bạn có thể thiết kế contract để **source** chính là publishing context:

~~~java
public final class ContextSignal extends ApplicationEvent {
    private final String eventId;

    public ContextSignal(ApplicationContext source, String eventId) {
        super(source);
        this.eventId = eventId;
    }

    public ApplicationContext originContext() {
        return (ApplicationContext) getSource();
    }

    public String eventId() {
        return eventId;
    }
}
~~~

Đây là **class minh họa**; chỉ dùng phép ép kiểu trên khi **constructor buộc source là ApplicationContext**. Trong API Spring nói chung, **ApplicationEvent.getSource()** là **Object**, không mặc nhiên là ApplicationContext. Một custom event khác có thể dùng order, service hoặc entity làm source.

Với ví dụ có source context rõ, event object được chuyển tiếp lên parent mà vẫn mang ngữ nghĩa **originContext** đã được xác định. Không dùng identity của event thay cho **business event ID** khi cần chống xử lý trùng ở mức nghiệp vụ.

### 4.3. POJO/record event: không dựa vào PayloadApplicationEvent.getSource() để đoán nguồn ban đầu

Spring hỗ trợ phát trực tiếp object thuần Java, ví dụ:

~~~java
public record OrderConfirmed(String orderId, String originContextId) {}
~~~

Khi publish POJO bằng **publishEvent(Object)**, context có thể tạo **PayloadApplicationEvent** để bọc payload. **AbstractApplicationContext** có cơ chế forward **original object** sang parent; ở parent, POJO có thể được **bọc lại bằng PayloadApplicationEvent mới** với **source là chính parent context**.

Do vậy:

- **PayloadApplicationEvent.getSource()** tại parent không phải lúc nào cũng cho biết **child context ban đầu**.
- **PayloadApplicationEvent.getPayload()** vẫn là event object/giá trị nghiệp vụ phù hợp, nhưng metadata source của wrapper là chi tiết của bước dispatch.
- Nếu cần phân biệt origin ở parent khi xử lý **POJO**, hãy đặt **originContextId** (hoặc metadata context/correlation) trong **payload/event envelope** ngay tại application/infrastructure boundary.
- Không nên bắt domain event thuần Java phụ thuộc trực tiếp Spring chỉ để có source context; mapper/adapter có thể bổ sung metadata kỹ thuật.
- **originContextId** trong payload chỉ dùng để route/filter/log theo hợp đồng ứng dụng, không tự trở thành bằng chứng ủy quyền hay một khóa bảo mật đáng tin khi payload đến từ bên ngoài.

Điều này quan trọng vì một lời khuyên chung kiểu “mọi event đều gọi getSource() và so với context hiện tại” là **không chính xác với POJO events** qua nhiều context.

### 4.4. Bảng nhận diện origin

| Event type | Nguồn nên kiểm tra | Ghi chú |
| --- | --- | --- |
| **ContextRefreshedEvent** | **getApplicationContext()** | Chính context đã refresh |
| **ContextClosedEvent** | **getApplicationContext()** | Chính context phát close event |
| Custom **ApplicationEvent** có contract source context | **getSource()** hoặc accessor type-safe | Chỉ tin khi constructor/event contract đảm bảo |
| **POJO/record** publish qua **publishEvent(Object)** | Metadata **originContextId** trong payload/envelope | Không suy luận nguồn gốc từ wrapper source ở ancestor |
| **SpringApplicationEvent** | API có sẵn và ngữ cảnh Boot lifecycle tương ứng | Kiểm tra version/type; không ép mọi Boot event theo một cách |
| Event đến từ broker | Producer/consumer headers và tracing metadata | Không phải propagation của Spring ApplicationContext hierarchy |

## 5. Demo hoàn chỉnh Java 17+: child event đi lên parent, không đi xuống

Dự án **Spring Framework 6.2.9** thuần, **JDK 17+**, **Gradle 8.x**, không cần Spring Boot, database hoặc message broker. Mục tiêu: nhìn thấy rõ listener nào xử lý khi publish từ child và parent, và kiểm tra origin bằng **ApplicationContext identity**.

Cấu trúc:

~~~text
context-event-hierarchy-demo/
  build.gradle
  src/main/java/demo/ContextEventHierarchyDemo.java
~~~

### 5.1. File build.gradle

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

application {
    mainClass = 'demo.ContextEventHierarchyDemo'
}
~~~

### 5.2. File src/main/java/demo/ContextEventHierarchyDemo.java

~~~java
package demo;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ContextEventHierarchyDemo {

    public static final class TaggedEvent extends ApplicationEvent {
        private final String id;

        public TaggedEvent(ApplicationContext origin, String id) {
            super(origin);
            this.id = id;
        }

        public String id() {
            return id;
        }

        public ApplicationContext origin() {
            return (ApplicationContext) getSource();
        }
    }

    public static final class ParentHandler
            implements ApplicationContextAware {

        private ApplicationContext owner;

        @Override
        public void setApplicationContext(ApplicationContext context) {
            this.owner = context;
        }

        @EventListener
        public void on(TaggedEvent event) {
            String location = (event.origin() == owner)
                    ? "local"
                    : "forwarded";
            System.out.println("parent: " + location + " " + event.id());
        }
    }

    public static final class ChildHandler {

        @EventListener
        public void on(TaggedEvent event) {
            System.out.println("child: " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ParentConfig {
        @Bean
        ParentHandler parentHandler() {
            return new ParentHandler();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChildConfig {
        @Bean
        ChildHandler childHandler() {
            return new ChildHandler();
        }
    }

    public static void main(String[] args) {
        try (var parent =
                     new AnnotationConfigApplicationContext(
                             ParentConfig.class)) {

            try (var child = new AnnotationConfigApplicationContext()) {
                child.setParent(parent);
                child.register(ChildConfig.class);
                child.refresh();

                System.out.println("publish: child");
                child.publishEvent(new TaggedEvent(child, "C1"));

                System.out.println("publish: parent");
                parent.publishEvent(new TaggedEvent(parent, "P1"));
            }
        }
    }
}
~~~

Chạy trong thư mục **context-event-hierarchy-demo**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chương trình tự in ra** với multicaster đồng bộ mặc định:

~~~text
publish: child
child: C1
parent: forwarded C1
publish: parent
parent: local P1
~~~

### 5.3. Giải thích từng dòng

1. Parent được tạo trước từ **ParentConfig**; nó đăng ký **ParentHandler**.
2. Child được tạo bằng constructor trống, sau đó gọi **child.setParent(parent)** **trước khi** **child.refresh()**. Child đăng ký **ChildHandler** trong **ChildConfig**.
3. **child.publishEvent(TaggedEvent(child, "C1"))** được xử lý trước bởi listener local trong child: **child: C1**.
4. Event tiếp tục được chuyển lên parent. **ParentHandler** có **owner** là parent nhưng **event.origin()** là child, nên in **parent: forwarded C1**.
5. **parent.publishEvent(TaggedEvent(parent, "P1"))** chỉ được dispatch trong parent và các ancestor của nó (không có ancestor trong demo). ParentHandler thấy origin == owner, in **parent: local P1**.
6. ChildHandler **không** in **child: P1** vì event từ parent **không tự truyền xuống child**.
7. Khi đóng child rồi parent, Spring còn có event lifecycle nội bộ, nhưng các listener của demo chỉ nhận **TaggedEvent**, nên không thêm dòng log.

**Chú ý mã nguồn:** Ở đây **TaggedEvent** cố ý có constructor nhận **ApplicationContext** làm source để phép ép kiểu trong **origin()** hợp lệ. Bạn không được áp dụng phép ép này cho mọi loại ApplicationEvent. Phần demo cũng không cấu hình @Async hay custom executor; do đó stdout được giải thích theo dispatch đồng bộ.

## 6. Cách sửa 1: filter lifecycle event theo owning context

Một listener thực hiện khởi tạo cache, đăng ký metrics hoặc hook lifecycle nên thường chỉ phản ứng với **refresh của chính context chứa nó**.

Giải pháp:

~~~java
@Component
public final class RefreshOncePerContext
        implements ApplicationContextAware {

    private ApplicationContext ownContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.ownContext = context;
    }

    @EventListener
    public void on(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        // Chỉ xử lý ContextRefreshedEvent do ownContext phát.
    }
}
~~~

Đây là snippet Spring Framework, cần imports. Lưu ý:

- So sánh **event.getApplicationContext()** với context của bean listener, không chỉ so sánh class hoặc context ID có thể bị cấu hình giống nhau.
- Đây là **local-context filter**, không ngăn event được forward lên parent. Nó chỉ quyết định **handler có thực hiện side effect hay không**.
- Nếu cùng một context có thể **refresh lại nhiều lần** (tùy loại context), filter này vẫn cho phép xử lý mỗi lần refresh của context đó. Nếu nghiệp vụ thực sự cần **only-once**, phải có điều kiện/idempotency riêng.
- Với **ContextClosedEvent**, áp dụng cùng nguyên tắc; nhưng quan sát lifecycle shutdown cần để ý các bean/service có thể đang bị hủy.
- Khi test, tạo parent và child thật, kiểm tra listener parent chỉ xử lý parent-origin event và bỏ qua child-origin event.

**Không dùng @Order để sửa lỗi này.** @Order chỉ ảnh hưởng thứ tự dispatch giữa listeners trong một ngữ cảnh, không chặn việc forwarding từ child lên parent.

## 7. Cách sửa 2: ràng buộc rõ phạm vi POJO/domain event

Với event dạng record:

~~~java
public record OrderConfirmed(
        String orderId,
        String eventId,
        String originContextId) {}
~~~

Một parent listener có thể kiểm tra **originContextId** trước khi thực hiện side effect, chẳng hạn chỉ xử lý event được publish bởi root-context application service:

~~~java
@EventListener
public void on(OrderConfirmed event) {
    if (!rootContext.getId().equals(event.originContextId())) {
        return;
    }
    // Xử lý domain event đúng phạm vi đã chọn.
}
~~~

Hai đoạn trên là snippets; để dùng thật cần Spring bean và một tham chiếu **rootContext** được xác định ở vòng infrastructure. Domain không nhất thiết phải biết Spring: metadata **originContextId** có thể nằm trong integration envelope thay vì record domain.

Nếu một service có nhiều contexts cùng tham gia xử lý nghiệp vụ, lựa chọn tốt hơn có thể là **một publisher/application service thống nhất** chịu trách nhiệm phát sự kiện cho nghiệp vụ đó, và listener được đặt đúng context cần nhận. Tránh dựa vào context ID như một business ID khi nhiệm vụ yêu cầu **exactly once**.

### Đặt listener ở context nào?

Một số quy tắc thực dụng:

- Listener phục vụ **riêng một web module**: đăng ký trong child context của module.
- Listener phục vụ **toàn ứng dụng**: có thể đăng ký ở parent, nhưng phải hiểu rằng nó sẽ thấy event từ descendants.
- Listener global nhưng chỉ nên xử lý **parent-origin lifecycle events**: dùng filter theo context source.
- Listener xử lý external side effect quan trọng: vừa scope/filter đúng, vừa cần **idempotency** và transaction/durable messaging phù hợp.
- Nhiều module con dùng chung service: cân nhắc phát event qua một boundary rõ thay vì để nhiều layer publish cùng sự thật nghiệp vụ.

Đừng tự đổi hierarchy hoặc chặn forwarding bằng custom AbstractApplicationContext subclass chỉ để tránh hai dòng log, vì có thể làm mất các event mà subsystem khác cần quan sát. Ưu tiên chỉnh **listener ownership, event type và filtering** trước.

## 8. Cách sửa 3: tránh duplicate registration do quét bean

Nếu hai context dùng **@ComponentScan** quét chồng nhau, cùng class listener có thể được instantiate trong cả hai context. Một sự kiện publish ở child đi qua cả hai đăng ký.

Hướng điều tra:

1. Kiểm tra các **@ComponentScan** ở parent và child; xác định package boundaries.
2. Kiểm tra **@Import**, **@Bean**, auto-configuration hoặc cấu hình thủ công đăng ký cùng loại listener.
3. Kiểm tra listener bean nằm trong context nào, **không chỉ tồn tại trong ApplicationContext.getBean(...)**: child có thể tra bean của parent qua hierarchy.
4. Kiểm tra scope singleton nghĩa là **singleton trong một BeanFactory/context**, không phải singleton trên toàn hierarchy.
5. Kiểm tra một listener có thể vừa được khai báo bean vừa được thêm qua **ApplicationContext.addApplicationListener(...)** theo cấu hình không.
6. Sau khi xác định registration trùng ngoài ý muốn, thu hẹp scanning/imports để mỗi listener có owner rõ ràng.

**Đừng xóa một listener chỉ vì cùng class xuất hiện ở nhiều nơi** nếu ứng dụng thật sự cần hai handlers cho hai module độc lập. Quyết định dựa trên scope nghiệp vụ, không dựa trên số lượng log.

### Phân biệt local bean với inherited bean

Với **ConfigurableListableBeanFactory/BeanFactory** và các API tương ứng, có thể kiểm tra local bean definitions hoặc local registration. Một lời gọi **child.getBean(ParentHandler.class)** có thể tìm được bean của parent vì child được phép fallback lookup lên parent. Do đó **getBean() thành công không chứng minh bean được đăng ký local trong child**.

Khi debug danh sách beans, xem **context ID**, **bean definition owner**, local bean factory và instance identity. Tránh dựa vào một danh sách **getBeanNamesForType(...)** có thể dùng tùy tham số và implementation rồi suy luận rằng đó là tất cả beans trong cả hierarchy.

## 9. Cách sửa 4: đừng xử lý business side effect hai lần

Ngay cả khi hai context đều nhận event đúng theo thiết kế, một business side effect **không nên được thực hiện hai lần** nếu hợp đồng chỉ cho phép một lần.

Ví dụ lỗi:

~~~text
child.listener(OrderPaid) -> gửi hóa đơn email
parent.listener(OrderPaid) -> gửi hóa đơn email
Kết quả: một hành động trả tiền có thể tạo hai email.
~~~

Hướng xử lý:

- Quy định một owner cho side effect bắt buộc, ví dụ notification adapter chỉ được đăng ký ở một context.
- Nếu các listeners độc lập thật, mỗi listener phải có **consumer name/side effect purpose** rõ, không vô tình cùng gọi một handler.
- Đưa **eventId** hoặc business operation ID vào event để thực hiện deduplication phù hợp tại consumer.
- Với xử lý bền vững qua broker/outbox, implement **idempotency key** và lưu dấu đã xử lý, không dùng một biến boolean static trong JVM làm đảm bảo duy nhất.
- Xác định transaction timing: một **@EventListener** đồng bộ có thể chạy trước commit; dùng **@TransactionalEventListener(phase=AFTER_COMMIT)** hoặc **outbox** khi thật sự cần. **AFTER_COMMIT không giải quyết việc parent và child cùng nhận event**; nó chỉ thay đổi phase xử lý khi có transaction phù hợp.
- Tách event business khỏi event lifecycle. Không gắn side effect business vào **ContextRefreshedEvent** nếu đó không phải sự thật nghiệp vụ.

Nếu listener ở parent phải nhận event từ cả parent và children để làm analytics, đừng filter hết child-origin events. Thay vào đó, đưa **origin metadata** vào metric/log và định nghĩa rõ aggregation để tránh đếm nhầm.

## 10. Cách log để tìm đường đi event

Khi thấy handler chạy ngoài dự kiến, cần ghi đủ thông tin để phân biệt **publication**, **propagation** và **registration**.

Các trường nên log:

| Trường | Mục đích |
| --- | --- |
| **eventType** | Loại event mà listener đang xử lý |
| **eventId / businessKey** | Phân biệt một business event với hai event riêng |
| **listenerName / beanName** | Xác định handler nào thực sự chạy |
| **listenerContextId** | Context sở hữu bean listener |
| **parentContextId** | Context cha của owner nếu có |
| **originContextId** | Context đã phát event, lấy theo event contract |
| **traceId / correlationId** | Liên kết request và các xử lý bất đồng bộ |
| **threadName** | Phát hiện executor/async và tránh suy luận từ thứ tự log |
| **phase** | immediate, BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, ... |
| **result** | success/failure/skipped và lý do filter |

Ví dụ với **ContextRefreshedEvent**:

~~~java
@EventListener
public void on(ContextRefreshedEvent event) {
    String originId = event.getApplicationContext().getId();
    String listenerId = ownerContext.getId();
    String parentId = ownerContext.getParent() == null
            ? "none"
            : ownerContext.getParent().getId();

    log.info(
            "event=ContextRefreshedEvent owner={} parent={} origin={}",
            listenerId, parentId, originId);
}
~~~

Đây là snippet cần **ownerContext**, **log** và imports. Một lần refresh parent + child có thể tạo:

~~~text
event=ContextRefreshedEvent owner=root parent=none origin=root
event=ContextRefreshedEvent owner=root parent=none origin=web-child
~~~

Dòng thứ hai minh họa **parent listener nhìn thấy event của child**, không phải parent đã refresh lần hai.

**Chú ý:** Đối với POJO event, không điền **originContextId** bằng **PayloadApplicationEvent.getSource()** ở parent rồi suy luận context nguồn, vì wrapper có thể được tạo lại ở parent. Hãy lấy origin metadata do ứng dụng kiểm soát, hoặc từ custom ApplicationEvent có contract rõ.

### Không chỉ đếm log

Một event có thể tạo nhiều log lines bên trong một listener; log có thể bị lặp bởi appender hoặc hệ thu thập log. Để tìm duplicate processing, cần kiểm tra **event ID**, **listener bean identity/context**, và **side-effect identity**, không chỉ tổng số dòng log.

## 11. Các event framework có thể gây nhiễu kết quả

### 11.1. ContextRefreshedEvent

Parent refresh trước, child refresh sau: parent listener có thể thấy **hai event cùng loại nhưng khác origin**. Không nên dùng một listener kiểu “when any context refreshed, initialize global cache” mà không xét source, bởi global cache có thể bị khởi tạo lại.

### 11.2. ContextClosedEvent

Đóng child có thể phát **ContextClosedEvent** rồi chuyển lên parent. Khi parent sau đó cũng đóng, parent listener có thể thấy event của cả child lẫn chính parent. Nếu listener đang dọn một resource dùng chung, hãy tránh cleanup sớm khi **child** đóng nếu resource thuộc parent; ngược lại, resource thuộc child không nên được quản lý bởi parent listener.

### 11.3. Spring Boot application events

Trong hierarchy dùng **SpringApplicationBuilder**, mỗi **SpringApplication** có thể phát các event khởi động/vòng đời riêng, và cơ chế Spring Framework còn forward những event đã đi qua child context tới ancestor. Vì vậy cùng loại Spring Boot application event có thể xuất hiện nhiều lần trong parent listener.

**Không áp một giả định duy nhất cho tất cả Spring Boot events**: một số được phát trước khi context tạo hoặc refresh, có API/source khác **ApplicationContextEvent**. Với các event có context accessor, so sánh theo API của type; với các event khởi động sớm, xem thời điểm registration của listener, version và cách Boot phát event.

### 11.4. ContextHierarchy trong Spring Test

Spring TestContext có hỗ trợ **@ContextHierarchy** để xây dựng context hierarchy phục vụ integration tests. Nếu test context được cache, dirty hoặc reload giữa tests, các lifecycle events cũng có thể xuất hiện ngoài kịch bản tối giản.

Khi kiểm thử lỗi event propagation, dùng **ApplicationContext objects** rõ ràng hoặc test hierarchy được định nghĩa chính xác; nếu test phụ thuộc số lần lifecycle events, phải kiểm soát việc context được refresh/close và Spring TestContext caching.

## 12. @EventListener condition, @Order và @Async có sửa được không?

### @EventListener(condition = "...")

Condition dựa trên SpEL có thể giúp filter event theo payload hoặc metadata. Tuy nhiên với **context origin**, dùng Java **if** rõ ràng trong listener thường dễ đọc, dễ test, và tránh phụ thuộc cách wrapper tạo source ở từng context. Condition là **lọc xử lý**, không thay đổi đường forwarding.

### @Order

**@Order** sắp xếp listener priority **trong một event multicaster/đường dispatch phù hợp**. Nó không biến child event thành local-only và không tự làm side effects chỉ xảy ra một lần. Nếu parent và child đều đăng ký listener, đặt cùng hay khác @Order không phải cách giải quyết bản chất.

### @Async

**@Async** đưa listener qua thread pool, có thể làm log parent và child xuất hiện theo thứ tự khác, khiến suy luận “ai nhận trước” từ stdout khó chính xác. Nó không chặn propagation và không tự bảo đảm event được xử lý. Trace context/MDC phải được propagate đúng khi cần.

### @TransactionalEventListener

Annotation này ràng buộc event với transaction outcome, **không phải context origin**. Nó còn yêu cầu transaction synchronization tương thích; mặc định listener ngoài transaction không chạy (**fallbackExecution=false**). Một parent listener có thể nhận event do child forward, nhưng việc callback có chạy hay không còn phụ thuộc **transaction thực sự active lúc event được publish và thread/phase**.

**Kết luận:** Những annotation nói trên giải quyết các mối quan tâm khác nhau; để sửa event “ngoài dự kiến” cần xác định chính xác **origin**, **listener owner**, **publish path** và **side-effect owner** trước.

## 13. Kiểm thử để tái hiện và ngăn tái phát

### 13.1. Ma trận tích hợp

| Hành động | Child handler | Parent handler | Giải thích |
| --- | --- | --- | --- |
| Publish **TaggedEvent** qua child | Được gọi | Được gọi | Upward propagation |
| Publish **TaggedEvent** qua parent | Không tự gọi | Được gọi | Không tự downward propagation |
| Refresh parent rồi child | Nếu listener chỉ nhận TaggedEvent: không | Không | Type filter tránh lifecycle noise |
| Parent listener nghe **ContextRefreshedEvent** | Không liên quan | Có thể nhận của parent và child | Cùng event type, khác origin |
| Publish POJO qua child | Listener của child theo payload type | Listener của parent theo payload type | Không suy origin từ PayloadApplicationEvent wrapper |
| Publish child với parent listener filter local-only | Child xử lý bình thường | Parent bỏ qua child-origin side effect | Event vẫn được forward, nhưng handler filter |

### 13.2. Test bằng recorder, không chỉ System.out

Trong integration test nên thay **System.out.println** bằng fake recorder:

~~~java
public final class EventRecorder {
    private final List<String> calls = new CopyOnWriteArrayList<>();

    public void record(String value) {
        calls.add(value);
    }

    public List<String> snapshot() {
        return List.copyOf(calls);
    }
}
~~~

Đây là **snippet** cần imports **java.util.List** và **java.util.concurrent.CopyOnWriteArrayList**. Cho parent/child handlers inject recorder, rồi publish event và assert:

~~~text
child.publish(E1)
expect: ["child:E1", "parent:forwarded:E1"]

parent.publish(E2)
expect: ["parent:local:E2"]

parent listener có local-only filter:
child.publish(E3)
expect: ["child:E3"] ở danh sách side effects
~~~

Đây là **kỳ vọng test**, không phải stdout của class recorder. Khi có executor/@Async, dùng **CountDownLatch** hoặc Awaitility để đợi handler hoàn thành; không dựa vào **Thread.sleep(...)** cố định.

Nếu test dành cho custom **ApplicationEvent** source context, assert **event.origin() == child** tại parent. Nếu test dành cho POJO event, assert **event.originContextId()** được giữ trong payload; test không nên dựa vào source của wrapper.

### 13.3. Test duplicate registration

Tạo parent và child config có thể đăng ký listener cùng loại, xác minh:

- Mỗi context có bao nhiêu **local handler beans**.
- Với một event publish qua child, những handler nào được gọi.
- Nếu hai handlers cùng thực hiện một action, **action count** có đúng theo hợp đồng không.
- Sau khi thu hẹp component scan, parent/child ownership có đúng không.
- Khi retry/redelivery thật, idempotency bảo vệ side effect dù event được xử lý nhiều lần.

Một assertion “handler đã được gọi” không đủ để xác định nguồn trùng. Cần lưu **(eventId, listenerContextId, listenerName)** để thấy chính xác nơi duplication xảy ra.

### 13.4. Test refresh/close

Nếu service dùng lifecycle events:

1. Parent refresh, child refresh.
2. Parent lifecycle listener nhận events có **origin** lần lượt là parent và child nếu phù hợp.
3. Local-only filter chỉ thực hiện tác vụ khi **origin == owner**.
4. Child close rồi parent close, xác nhận không cleanup resource dùng chung hai lần.
5. Nếu có multiple hierarchy levels, thêm grandchild và kiểm tra event từ grandchild đi qua child rồi parent.

## 14. Quy trình điều tra từng bước tại production

Giả sử log cho thấy event **OrderConfirmed** xử lý hai lần. Thay vì thêm một **synchronized** toàn cục để “chặn cho nhanh”, thực hiện:

**Bước 1 — Xác nhận có thật sự một publish hay nhiều publish.** Ở publisher, log event ID, business ID, context ID, thread và correlation ID. Nếu cùng business operation tạo hai event IDs, lỗi có thể nằm ở application logic hoặc retry upstream.

**Bước 2 — Vẽ hierarchy thật.** Từ context hiện tại, đọc **getParent()** để nhận diện root/child và ID. Không đoán rằng Actuator hoặc một servlet luôn tạo child context; cấu trúc tùy ứng dụng và cấu hình.

**Bước 3 — Xác định context chứa publisher bean.** Bean trong parent có thể dùng parent publisher ngay cả khi được gọi bởi controller thuộc child. Kiểm tra container sở hữu bean và nơi inject ApplicationEventPublisher.

**Bước 4 — Xác định listener registration.** Parent, child, cả hai, hay hai instances trong cùng context? Kiểm tra ComponentScan, @Bean, @Import, addApplicationListener và phạm vi auto-config.

**Bước 5 — Xác định loại event và cách lấy origin.** Với ContextRefreshedEvent dùng getApplicationContext; với custom ApplicationEvent xem contract source; với POJO thêm origin metadata riêng.

**Bước 6 — Kiểm tra async.** Nếu logs đảo thứ tự, xác minh multicaster có task executor, @Async và ThreadLocal/MDC trace context. Đừng nhầm late arrival với duplicate arrival.

**Bước 7 — Kiểm tra transaction và side effect.** Event có thể được publish trước commit rồi transaction rollback. Nếu listener thực hiện side effect ngoại vi, cần policy after-commit/outbox; scope filter không giải quyết lost/duplicate delivery.

**Bước 8 — Sửa đúng ranh giới.** Chỉ một listener sở hữu side effect, filter origin nếu phù hợp, thu hẹp scan hoặc đưa event đến một boundary có owner rõ.

**Bước 9 — Viết integration test.** Test child publication, parent publication, lifecycle origin, duplicate registrations và idempotency.

**Bước 10 — Quan sát sau triển khai.** Theo dõi số lượng event theo **originContextId** và **listenerContextId**, kiểm tra lại dashboards, traces, số lần thực hiện side effect thật.

## 15. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách giải quyết |
| --- | --- | --- |
| Cho rằng Spring events chỉ ở context đã publish | Parent listener bất ngờ xử lý child events | Hiểu cơ chế **child → ancestors** |
| Cho rằng parent publish event thì child cũng nhận | Child listener không chạy | Publish qua đúng context/boundary hoặc thiết kế bus phù hợp |
| Parent nghe ContextRefreshedEvent mà không lọc source | Khởi tạo/dọn dẹp hai lần | So sánh **event.getApplicationContext()** với owning context |
| Parent/child cùng @ComponentScan listener | Hai bean instances cùng side effect | Thu hẹp scan và xác định ownership |
| Dùng getBean() trên child để kết luận bean local | Nhầm bean inherited với bean của child | Kiểm tra local bean definitions/owner |
| Coi mọi ApplicationEvent.getSource() là ApplicationContext | ClassCastException hoặc filter sai | Chỉ dùng theo contract source của loại event |
| Lấy PayloadApplicationEvent.getSource() để suy context gốc | Parent wrapper có source parent | Truyền **originContextId** trong payload/envelope |
| Dùng @Order để ngăn event đi lên parent | Không có tác dụng tới propagation | Filter hoặc tổ chức listener đúng context |
| Dùng @Async để “chặn trùng” | Đổi thứ tự/tiến trình, vẫn có xử lý lặp | Sửa owner, thêm idempotency |
| Tin rằng một listener method chạy hai lần chắc chắn là một event | Có thể hai lifecycle events riêng | Log eventId, originContextId, context owner |
| Dùng ContextRefreshedEvent để gửi email nghiệp vụ | Gửi email khi deploy/refresh | Dùng domain event đúng ý nghĩa |
| Dùng @TransactionalEventListener mà nghĩ tự local-only | Parent vẫn nhận event, phase là vấn đề khác | Kết hợp scope filter với transaction semantics |
| Dùng event source/context ID làm authentication | Có thể tin metadata không đáng tin | Authorization riêng, không dùng metadata kỹ thuật làm quyền |
| Chặn trùng bằng static Set không bền vững | Restart/race làm side effect lặp | Dùng idempotency store/eventId khi side effect quan trọng |
| Không test hierarchy thật | Unit test một context vẫn xanh | Integration tests với parent và child thực |

## 16. Checklist trước khi kết luận đã khắc phục

- **Parent và child có quan hệ getParent() thật không?**
- **Event được publish qua context nào? Bean publisher nằm ở context nào?**
- **Listener nằm trong parent, child hay cả hai? Có duplicate registration không?**
- **Event là ApplicationContextEvent, custom ApplicationEvent hay POJO payload?**
- **Origin context có được xác định bằng API/contract phù hợp không?**
- **Nếu POJO event, origin metadata có nằm trong payload/envelope thay vì đoán từ wrapper source không?**
- **Một child event có được forward lên parent như thiết kế không?**
- **Một parent event có bị nhầm tưởng sẽ tự xuống child không?**
- **Event lifecycle cùng loại từ parent/child có bị đếm thành một event trùng không?**
- **Listener thực hiện side effect có đúng một owner hoặc idempotency không?**
- **Nếu có async, thứ tự log và trace context có được kiểm chứng không?**
- **Nếu cần after-commit, transaction phase và durable delivery có được thiết kế riêng không?**
- **Đã có integration test cho child-origin, parent-origin, close/refresh và sibling không nhận tự động chưa?**

**Kết luận:** Với **Spring ApplicationContext hierarchy**, event công bố ở **child** sẽ đi **lên parent/ancestors**, khiến parent listener có thể nhận event ngoài dự kiến. Đồng thời mỗi context có lifecycle events riêng nên listener nghe **ContextRefreshedEvent/ContextClosedEvent** có thể thấy nhiều event cùng loại. Chẩn đoán đúng bằng **context owner + event origin + event ID + listener registration**. Dùng **getApplicationContext()** cho lifecycle event, contract source rõ cho custom ApplicationEvent, còn **POJO event** cần metadata origin riêng; sau đó filter scope, chỉnh bean scanning và bảo vệ side effects bằng idempotency khi cần. Đừng dùng @Order, @Async hoặc suy đoán từ số dòng log để thay thế việc xác định đường propagation.

### Tài liệu chính thức

- Spring Boot Reference — *Application Events and Listeners* (cảnh báo event propagation trong hierarchy): https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Reference — *Additional Capabilities of ApplicationContext / Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Javadoc 6.2.9 — *AbstractApplicationContext*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Framework Javadoc 6.2.9 — *ApplicationContextEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html
- Spring Framework Javadoc 6.2.9 — *PayloadApplicationEvent*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
