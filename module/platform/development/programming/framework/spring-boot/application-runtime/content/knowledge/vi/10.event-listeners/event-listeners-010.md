# Sự kiện truyền từ context con lên cha và cách lọc đúng context trong Spring Boot

## 1. Vì sao một listener có thể xử lý cùng loại sự kiện nhiều lần?

Một ứng dụng Spring thường chỉ có một `ApplicationContext`. Tuy nhiên, Spring Framework và Spring Boot cho phép xây dựng **cây context**: một context con có `parent`, context cha lại có thể có cha khác. Mỗi context quản lý các bean, listener và nguồn sự kiện của mình.

Khi sự kiện được **publish từ context con**, Spring Framework không chỉ thông báo cho listener trong context con. Theo cơ chế chuẩn của `AbstractApplicationContext`, nó còn chuyển sự kiện **lên context cha và tiếp tục lên các ancestor**. Vì vậy listener đặt ở context cha có thể nhận:

- Sự kiện phát sinh từ **chính context cha**.
- Sự kiện cùng kiểu phát sinh từ **context con**.
- Sự kiện từ **cháu/chắt** ở các cấp sâu hơn, nếu nằm trong nhánh con của nó.

Một listener không phân biệt nguồn có thể thực thi side effect nhiều lần: nạp cache hai lượt, chạy migration lặp, phát một thông báo hai lần, đăng ký resource trùng hoặc báo số liệu không đúng.

Ví dụ điển hình: context cha chứa một listener bắt `ContextRefreshedEvent`. Cha được refresh, listener nhận sự kiện `parent`. Sau đó context con được refresh, Spring chuyển sự kiện `child` lên cha; **listener cha lại được gọi**. Nếu listener dùng logic “mỗi khi thấy ContextRefreshedEvent thì chạy một lần cho hệ thống”, kết quả có thể sai.

**Cách lọc quan trọng nhất đối với sự kiện vòng đời context:** so sánh **identity** của context phát sự kiện với context đang sở hữu listener:

```java
if (event.getApplicationContext() != ownContext) {
    return;
}
```

Ở đây `ownContext` là **chính `ApplicationContext` đã inject vào listener của context đó**, không phải parent lấy ngẫu nhiên, không phải một biến context toàn cục và không phải một tên chuỗi.

Bài học áp dụng cho **Spring Framework 6.1.x và Spring Boot 3.3.x, Java 17+**; phần thực hành dùng các context chuẩn để có thể quan sát rõ cơ chế propagation.

## 2. Hiểu đúng cây ApplicationContext

Một cây context tối thiểu:

```text
                  ROOT / PARENT
                 ApplicationContext
                 listeners: P, P2
                        |
           +------------+-------------+
           |                          |
       CHILD-A                    CHILD-B
   ApplicationContext          ApplicationContext
   listeners: A                listeners: B
           |                          |
       GRANDCHILD                 (không con)
       listeners: G
```

Khi `CHILD-A.publishEvent(event)`:

```text
CHILD-A listeners
       |
       v
PARENT listeners
       |
       v
ROOT listeners (nếu parent còn có cha)
```

Khi `GRANDCHILD.publishEvent(event)`, sự kiện đi từ `GRANDCHILD → CHILD-A → PARENT → ROOT`. Nhưng `CHILD-B` là nhánh **anh em**, không nằm trên đường đi đó, nên **không tự nhận** sự kiện từ `CHILD-A`. Tương tự, khi parent publish, event **không tự lan ngược xuống child**.

Đó là mô hình **phát trong context hiện tại rồi chuyển lên ancestor**, không phải broadcast qua toàn bộ cây theo hai chiều.

### 2.1. “Có thể nhìn thấy bean cha” khác “nhận sự kiện từ cha”

Một context con thường có thể tra cứu bean trong context cha qua cơ chế parent BeanFactory. Điều này **không có nghĩa** listener ở context con tự nhận event phát ra ở cha.

| Quan hệ | Hành vi điển hình |
| --- | --- |
| Con tra cứu bean từ cha | Có thể, nếu bean phù hợp và không bị bean con che khuất. |
| Cha tự tra cứu bean chỉ tồn tại trong con | Không theo lookup thông thường. |
| Event do con publish đến listener của cha | **Có**, theo cơ chế `AbstractApplicationContext` chuẩn. |
| Event do cha publish đến listener của con | **Không tự động**. |
| Event ở con A đến listener của con B (hai con cùng cha) | **Không tự động**; chỉ ancestor nhận. |
| Một listener có mặt ở cả cha và con | Có thể xử lý event nhiều lần theo việc đăng ký và đường propagation. |

Không suy luận propagation từ mối quan hệ dependency injection. Hai cơ chế liên quan đến context hierarchy, nhưng có hướng và luật khác nhau.

## 3. Cơ chế của AbstractApplicationContext.publishEvent

`ApplicationEventPublisher.publishEvent(...)` là điểm bắt đầu. `ApplicationContext` thường implement interface này; bạn có thể publish một `ApplicationEvent` hoặc đối tượng payload thường.

Trong `AbstractApplicationContext`, ý tưởng của luồng xử lý là:

1. Nhận event; nếu là payload thường, có thể bọc thành `PayloadApplicationEvent`.
2. Xác định event type để listener phù hợp được gọi.
3. Gửi event tới `ApplicationEventMulticaster` **của context hiện tại**, hoặc giữ lại nếu đang ở pha khởi tạo chưa thể multicast ngay.
4. Nếu có parent, tiếp tục publish event **vào parent context** theo cơ chế framework hỗ trợ.
5. Lặp lại qua các ancestor khác nếu có.

```text
child.publishEvent(event)
         |
         +--> child.applicationEventMulticaster
         |           |
         |           +--> listener ở child
         |
         +--> parent.publishEvent(event)
                     |
                     +--> parent.applicationEventMulticaster
                     |           |
                     |           +--> listener ở parent
                     |
                     +--> grandparent.publishEvent(event)
                                   |
                                   +--> listener ở grandparent
```

Đối với một `ApplicationEvent` đã được tạo, **thông tin nguồn trong event không được tự đổi thành context cha** chỉ vì nó đang được chuyển lên. Vì thế listener cha có thể nhận `ContextRefreshedEvent` mà `event.getApplicationContext()` **vẫn trả về child**.

### 3.1. Luật quan trọng: propagation theo đường phát, không phải theo class listener

Listener ở cha có nhận event hay không còn phụ thuộc:

- Event có được publish qua context con/chuỗi ancestor phù hợp không?
- Listener đã được đăng ký tại context cha chưa?
- Listener có hỗ trợ **kiểu event** được phát không?
- Có `@EventListener(condition=...)`, filter, `@Order` hoặc cơ chế multicaster tùy chỉnh không?
- Listener là đồng bộ hay bất đồng bộ, có error handler/transaction binding hay không?

**Không phải** hễ định nghĩa class listener ở module chung thì event sẽ đến. Phải xét context chứa bean listener thực tế, event type và đường publish.

### 3.2. Đây không phải cơ chế bảo đảm delivery liên tiến trình

Spring application events là cơ chế **in-process**. Parent và child trong ví dụ cùng một tiến trình JVM. Chúng không tự publish qua Kafka, RabbitMQ, HTTP, Kubernetes hoặc giữa hai pod. Khi cần truyền event liên dịch vụ, phải dùng messaging/API/hệ thống phân tán riêng với hợp đồng retry, idempotence và delivery thích hợp.

## 4. Vì sao Spring Boot cảnh báo về việc nhận nhiều event?

Tài liệu Spring Boot nói rõ rằng event ở child context được publish tới listeners trong các ancestor. Khi một ứng dụng dùng **hierarchy của `SpringApplication`**, listener ở cha có thể nhận nhiều event **cùng loại**.

Ví dụ:

```text
Parent SpringApplication hoàn tất refresh
     |
     +--> ContextRefreshedEvent(parent) --> ParentListener

Child SpringApplication hoàn tất refresh
     |
     +--> ContextRefreshedEvent(child)  --> ChildListener
                                |
                                +----> ParentListener
```

Listener cha **không nhất thiết bị đăng ký hai lần**. Nó có thể chỉ được đăng ký một lần nhưng vẫn xử lý **hai event khác nhau**: một event cho parent, một event cho child. Đây là nguyên nhân phổ biến khiến người lập trình tưởng có lỗi duplicate registration.

Hãy phân biệt rõ:

- **Nhiều event hợp lệ:** parent refresh và child refresh mỗi cái phát một event riêng.
- **Một event được nhiều listener xử lý:** event con chạy qua child rồi ancestor listeners.
- **Một logic nhận event nhiều lần:** có thể do listener xuất hiện ở nhiều context, hoặc một listener ở cha nhận event từ nhiều context.
- **Một listener bị đăng ký trùng trong cùng context:** tình huống khác, phải kiểm tra cấu hình đăng ký.

Không thể dựa vào số lần log một mình để kết luận nguyên nhân; cần log **event context identity** và **listener owner context identity**.

## 5. Chọn đối tượng nào làm “nguồn sự kiện”?

Đây là trọng tâm của việc lọc.

### 5.1. Sự kiện kế thừa ApplicationContextEvent

Các sự kiện vòng đời của Spring Framework như:

- `ContextRefreshedEvent`
- `ContextStartedEvent`
- `ContextStoppedEvent`
- `ContextClosedEvent`

đều thuộc họ `ApplicationContextEvent` và có:

```java
ApplicationContext origin = event.getApplicationContext();
```

Giá trị này cho biết **context mà sự kiện mô tả**, ví dụ context vừa refresh hoặc context đang đóng. Với sự kiện được truyền từ child lên parent, nó vẫn là child.

**Lọc đúng:**

```java
if (event.getApplicationContext() != ownContext) {
    return;
}
```

Dùng `!=`/`==` để so sánh **chính object context**. Không so sánh tên class (cả hai có thể là `AnnotationConfigApplicationContext`), không chỉ so sánh `getId()` (ID có thể được đặt trùng) và không chỉ kiểm tra parent có tồn tại hay không.

### 5.2. Một số sự kiện của Spring Boot

Nhiều sự kiện sau khi context tồn tại có API `getApplicationContext()`, ví dụ `ApplicationStartedEvent` và `ApplicationReadyEvent`. Với các event đó, có thể cân nhắc lọc theo **context mà event cung cấp**, phù hợp với contract của từng event.

Tuy nhiên, các sự kiện Boot rất sớm như `ApplicationStartingEvent`/`ApplicationEnvironmentPreparedEvent` xảy ra khi application context chưa sẵn sàng, nên không thể dùng một công thức `getApplicationContext()` cho **mọi** event Boot. Listener của event rất sớm cũng phải được đăng ký trước khi bean container được tạo.

### 5.3. Sự kiện nghiệp vụ do bạn tự định nghĩa

Một `ApplicationEvent` tùy chỉnh có thể đặt `getSource()` là entity ID, một service, một chuỗi hoặc chính publisher; Spring **không tự cấp một trường `getApplicationContext()` cho tất cả custom event**.

Ví dụ:

```java
public final class PaymentSubmittedEvent extends ApplicationEvent {
    private final ApplicationContext originContext;
    private final String paymentId;

    public PaymentSubmittedEvent(ApplicationContext originContext,
                                 String paymentId) {
        super(originContext);
        this.originContext = originContext;
        this.paymentId = paymentId;
    }

    public ApplicationContext originContext() {
        return originContext;
    }

    public String paymentId() {
        return paymentId;
    }
}
```

Đoạn trên là **class minh họa trong một project Spring**, cần import `ApplicationEvent` và `ApplicationContext`, đặt vào file cùng tên hoặc một class lồng phù hợp. Nó thêm metadata `originContext` **theo thiết kế của ứng dụng**. Event kiểu này có thể được lọc bằng `event.originContext() == ownContext`, nhưng **không nên bê nguyên quy tắc đó sang mọi kiểu event khác**.

**Cẩn trọng:** dùng một tham chiếu `ApplicationContext` trực tiếp trong domain event chỉ phù hợp với ví dụ in-process/diagnostic. Với hệ thống messaging thật, hãy mang một **context/component identifier** hoặc tenant/aggregate ID có ý nghĩa nghiệp vụ, không serialize nguyên `ApplicationContext`.

### 5.4. Không dựa tùy tiện vào getSource() của payload event

Khi publish một object không kế thừa `ApplicationEvent`, Spring có thể bọc nó trong `PayloadApplicationEvent`. `source` của wrapper là chi tiết liên quan đến context tạo wrapper; khi event đi qua cơ chế propagation, wrapper có thể được tạo ở các mức khác nhau. Vì thế để xác định **nguồn nghiệp vụ**, nên đặt metadata rõ ràng trong payload, thay vì giả định `event.getSource()` của mọi wrapper luôn là nơi ban đầu đã publish.

## 6. Cách lọc đúng context trong một listener Spring bean

Trong một bean được quản lý bởi context, bạn có thể nhận `ApplicationContext` thông qua constructor injection hoặc `ApplicationContextAware`.

**Ví dụ dùng constructor injection:**

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OwnContextRefreshListener {

    private final ApplicationContext ownContext;

    public OwnContextRefreshListener(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("My context refreshed: " + ownContext.getId());
    }
}
```

Đây là **class Java hoàn chỉnh** khi project có Spring context, component scan bao phủ package. Khi bean nằm trong parent context, nó được inject **parent context**; khi bean nằm trong child context, nó được inject **child context** tương ứng.

Khi child refresh, listener ở parent có thể được gọi, nhưng điều kiện `event.getApplicationContext() != ownContext` khiến nó **bỏ qua** sự kiện của child. Với event của chính parent, điều kiện đúng và listener xử lý.

### 6.1. Dùng ApplicationContextAware

Nếu muốn thể hiện rõ hook của Spring:

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OwnContextCloseListener implements ApplicationContextAware {

    private ApplicationContext ownContext;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.ownContext = context;
    }

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        System.out.println("Closing own context: " + ownContext.getId());
    }
}
```

Đây là **file class độc lập** đặt cùng package. Spring gọi `setApplicationContext` khi bean được tạo, trước event đóng thông thường. Logic lọc tránh một listener của parent chạy cleanup chỉ vì **child** đang đóng.

Không tự gọi `setApplicationContext(...)` trong business code; đây là callback do container quản lý.

### 6.2. Có nên dùng @EventListener(condition=...)?

`@EventListener(condition=...)` hỗ trợ SpEL để lọc theo payload/thuộc tính. Tuy nhiên, để so sánh **context identity** với context được inject, một guard Java là cách thường dễ đọc, type-safe và dễ unit test hơn:

```java
@EventListener
public void onRefreshed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    // Hành động dành riêng cho context này.
}
```

Đây là method minh họa trong một bean đã có field `ownContext`. Không cần tạo một biểu thức SpEL phức tạp chỉ để thay thế một phép so sánh object.

## 7. Ví dụ chạy được: một parent, một child, hai loại listener

Để kiểm chứng hiện tượng, ta dùng **Spring Framework contexts** trực tiếp: `AnnotationConfigApplicationContext`. Chúng vẫn thuộc thư viện được `spring-boot-starter` kéo vào, vì vậy chạy được trong một project **Spring Boot 3.3.x + Java 17+**.

Ví dụ không gọi `SpringApplication.run(...)`, bởi mục tiêu là quan sát cơ chế **Spring Framework event hierarchy** mà không trộn thêm event Bootstrap hay auto-configuration của Boot. Sự kiện vẫn đi theo đúng quy tắc mà Boot sử dụng khi dựng parent/child contexts.

**File đầy đủ:** `src/main/java/com/example/hierarchy/ContextPropagationDemo.java`

```java
package com.example.hierarchy;

import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;

public class ContextPropagationDemo {

    public static void main(String[] args) {
        AnnotationConfigApplicationContext parent =
                new AnnotationConfigApplicationContext();
        parent.setId("parent");

        // Listener 1: parent muốn ghi lại mọi context refresh thuộc nhánh.
        parent.addApplicationListener(
                new RefreshTrace("PARENT_ALL", parent, false));

        // Listener 2: parent chỉ muốn xử lý refresh của chính nó.
        parent.addApplicationListener(
                new RefreshTrace("PARENT_OWN", parent, true));

        // Listener nghiệp vụ: parent nhận cả event từ child.
        parent.addApplicationListener(
                new OrderTrace("PARENT_ALL", parent, false));

        parent.refresh();

        AnnotationConfigApplicationContext child =
                new AnnotationConfigApplicationContext();
        child.setId("child");
        child.setParent(parent);

        // Listener con chỉ xử lý refresh của chính child.
        child.addApplicationListener(
                new RefreshTrace("CHILD_OWN", child, true));

        // Listener con chỉ xử lý event nghiệp vụ của chính child.
        child.addApplicationListener(
                new OrderTrace("CHILD_OWN", child, true));

        try {
            child.refresh();

            child.publishEvent(new OrderPlaced(child, "A-42"));
            parent.publishEvent(new OrderPlaced(parent, "P-1"));
        } finally {
            child.close();
            parent.close();
        }
    }

    static final class RefreshTrace
            implements ApplicationListener<ContextRefreshedEvent> {

        private final String label;
        private final ApplicationContext owner;
        private final boolean ownOnly;

        RefreshTrace(String label, ApplicationContext owner,
                     boolean ownOnly) {
            this.label = label;
            this.owner = owner;
            this.ownOnly = ownOnly;
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            ApplicationContext origin = event.getApplicationContext();
            if (ownOnly && origin != owner) {
                return;
            }
            System.out.println(label + " refresh origin=" + origin.getId());
        }
    }

    static final class OrderPlaced extends ApplicationEvent {

        private final ApplicationContext originContext;
        private final String orderId;

        OrderPlaced(ApplicationContext originContext, String orderId) {
            super(originContext);
            this.originContext = originContext;
            this.orderId = orderId;
        }

        ApplicationContext originContext() {
            return originContext;
        }

        String orderId() {
            return orderId;
        }
    }

    static final class OrderTrace
            implements ApplicationListener<OrderPlaced> {

        private final String label;
        private final ApplicationContext owner;
        private final boolean ownOnly;

        OrderTrace(String label, ApplicationContext owner, boolean ownOnly) {
            this.label = label;
            this.owner = owner;
            this.ownOnly = ownOnly;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            ApplicationContext origin = event.originContext();
            if (ownOnly && origin != owner) {
                return;
            }
            System.out.println(label + " order origin=" + origin.getId()
                    + " id=" + event.orderId());
        }
    }
}
```

### 7.1. Các chi tiết khiến ví dụ đúng

- `parent.refresh()` chạy trước, nên parent có multicaster và có thể nhận event của child sau đó.
- `child.setParent(parent)` được gọi **trước `child.refresh()`**, định nghĩa đường propagation.
- Hai class `RefreshTrace` và `OrderTrace` implements `ApplicationListener` với **generic event type cụ thể**, để Spring phân loại chính xác sự kiện được xử lý. Tránh đăng ký lambda raw listener không rõ event type rồi cast bừa.
- `ownOnly` là chính sách business của listener, **không phải** tính năng tự động của framework. Nếu đặt `false`, parent xử lý event của descendant; nếu đặt `true`, nó chỉ xử lý event có origin trùng context sở hữu.
- `OrderPlaced` có `originContext()` rõ ràng; không dựa vào một quy tắc ngầm rằng mọi custom event đều mang origin.
- `finally` đóng **child trước parent**, hợp lý với dependency hierarchy. `close` còn phát `ContextClosedEvent` nhưng ví dụ không có listener cho kiểu event này nên các dòng kết quả dưới đây không chứa log đóng.
- Trong chương trình này, parent và child đều là `AnnotationConfigApplicationContext`, nên so sánh **class** của context không phân biệt được nguồn; so sánh **object identity** mới chính xác.

### 7.2. Cấu hình chạy

Trong một dự án đã khai báo Spring Boot plugin 3.3.x và Java 17+, dependency đủ cho Spring context:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Đoạn này là **phần dependencies** của `build.gradle`; nếu dùng Maven, thêm starter tương đương trong `pom.xml`. Project cần có Gradle Wrapper hoặc môi trường Gradle phù hợp.

Để chỉ định main class mà tác vụ `bootRun` sử dụng, cấu hình trong `build.gradle`:

```groovy
springBoot {
    mainClass = 'com.example.hierarchy.ContextPropagationDemo'
}
```

Sau đó chạy:

```bash
./gradlew bootRun
```

Trên Windows CMD dùng `gradlew.bat bootRun`; PowerShell dùng `.\gradlew.bat bootRun`. Khi cần thử thuần Java mà không áp dụng Boot plugin, có thể dùng Gradle `application` plugin và main class tương ứng.

### 7.3. Kết quả của chương trình

Khi dùng `SimpleApplicationEventMulticaster` mặc định (xử lý đồng bộ) và chỉ các listener của ví dụ được đăng ký, các dòng tự in được kỳ vọng là:

```text
PARENT_ALL refresh origin=parent
PARENT_OWN refresh origin=parent
CHILD_OWN refresh origin=child
PARENT_ALL refresh origin=child
CHILD_OWN order origin=child id=A-42
PARENT_ALL order origin=child id=A-42
PARENT_ALL order origin=parent id=P-1
```

Dòng quan trọng nhất là:

```text
PARENT_ALL refresh origin=child
```

Nó chứng minh **listener thuộc parent nhận `ContextRefreshedEvent` do child phát**. Listener `PARENT_OWN` **không** in cho sự kiện refresh của child bởi vì guard `origin != owner` đã bỏ qua nó.

Sự kiện nghiệp vụ `OrderPlaced(child, "A-42")` được child xử lý trước rồi đến parent trong mô hình đồng bộ, nhưng `OrderPlaced(parent, "P-1")` **không** được chuyển xuống child. Vì vậy không có dòng `CHILD_OWN order origin=parent`.

**Giới hạn của stdout:** các dòng trên là log do code mẫu tự in. Khi thay bằng custom multicaster bất đồng bộ, thêm listeners, hoặc đổi topology, không dựa vào thứ tự log toàn cục như một bảo đảm giao dịch. Ý nghĩa nguồn và điều kiện lọc vẫn phải được kiểm tra theo event contract.

## 8. Cách dựng hierarchy trong Spring Boot thực tế

Nếu ứng dụng thật dùng `SpringApplication` thay vì tự tạo context, Spring Boot cung cấp `SpringApplicationBuilder`:

```java
new SpringApplicationBuilder(ParentConfig.class)
        .child(ChildConfig.class)
        .run(args);
```

Đây là **snippet trong method main**, giả định `ParentConfig` và `ChildConfig` là các class cấu hình Spring có thật, cần import `org.springframework.boot.builder.SpringApplicationBuilder`. Khi hai cấu hình muốn chạy như non-web applications, hãy thiết kế `WebApplicationType.NONE` và dependency phù hợp cho từng context.

Một hệ thống có thể có:

- Parent chứa cấu hình/bean chung: audit, registry, metrics, shared service.
- Child chứa logic API, tenant, plugin hoặc workstream riêng.
- Listener ở parent giám sát event thuộc nhiều child.
- Listener chuyên trách của từng child chỉ xử lý event của chính nó.

Spring Boot **không bắt buộc** mọi ứng dụng microservice phải dùng context hierarchy; đa số service có một context duy nhất. Chỉ tạo hierarchy khi có nhu cầu tách lifecycle/bean scope thực sự và đã cân nhắc chi phí phức tạp.

### 8.1. Context hierarchy không giống module Maven/Gradle

Nhiều module trong một project build không tự tạo nhiều `ApplicationContext`. Nếu tất cả code cuối cùng vào cùng một `SpringApplication`, vẫn có thể chỉ có một context.

Ngược lại, một JVM/test có thể tạo nhiều context dù source code nằm trong cùng một module. Kiểm tra `context.getParent()` và context identity thực tế, không suy luận từ số lượng module hoặc package.

## 9. Dùng @EventListener với parent-child đúng cách

`@EventListener` trong một bean hoạt động theo event multicaster của context sở hữu bean. Nó không tự giới hạn event từ chính context đó. Ví dụ listener parent:

```java
@Component
public class CacheWarmupListener {

    private final ApplicationContext ownContext;
    private final CacheService cacheService;

    public CacheWarmupListener(ApplicationContext ownContext,
                               CacheService cacheService) {
        this.ownContext = ownContext;
        this.cacheService = cacheService;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return;
        }
        cacheService.loadOnceForContext();
    }
}
```

Đây là **snippet minh họa** trong một project có `CacheService` và import `@Component`, `@EventListener`, `ApplicationContext`, `ContextRefreshedEvent`. Không phải chương trình độc lập nếu chưa có `CacheService`.

Không có guard, bean parent có thể chạy `loadOnceForContext()` mỗi lần child refresh. Khi có guard, nó chỉ làm việc của chính parent. Với việc nạp dữ liệu lớn hoặc cần kết thúc trước `ApplicationReadyEvent`, xem xét `ApplicationRunner` và readiness thay vì dùng event refresh làm công việc nghiệp vụ nặng.

### 9.1. Có thể chỉ cần giám sát mọi child?

Có. Không phải listener parent nào cũng phải loại event child. Ví dụ audit/telemetry thuộc parent có thể **cố ý** quan sát tất cả descendants:

```java
@EventListener
void observe(ContextRefreshedEvent event) {
    System.out.println("Refreshed context: "
            + event.getApplicationContext().getId());
}
```

Đây là method minh họa trong một bean parent. Điều kiện `event.getApplicationContext() != ownContext` chỉ phù hợp khi yêu cầu là **own-only**. Nếu yêu cầu là **aggregate monitoring**, đừng lọc mất các sự kiện con có giá trị.

Tốt nhất đặt tên/policy rõ: `ownContextOnly`, `allDescendants`, hoặc `allowedContexts` thay vì âm thầm bỏ một số event.

## 10. ContextClosedEvent: lỗi duplicate cleanup nguy hiểm hơn duplicate log

Tình huống thực tế: một listener parent nhận `ContextClosedEvent` của child, rồi vô tình đóng kết nối/database chung mà parent và các child khác đang sử dụng.

Ví dụ nguy hiểm:

```java
@EventListener
void onClosed(ContextClosedEvent event) {
    sharedResource.close();
}
```

Đây là snippet trong bean parent giả định `sharedResource` là đối tượng có method `close()`. Khi **bất kỳ child nào đóng**, listener parent có thể được gọi; điều đó không đồng nghĩa parent đang đóng.

Cách lọc nếu resource thuộc parent:

```java
@EventListener
void onClosed(ContextClosedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    sharedResource.close();
}
```

Tuy nhiên, nếu `sharedResource` là một **Spring-managed bean**, chính destroy method/`@PreDestroy`/`DisposableBean` hoặc `SmartLifecycle` thường là chỗ **đúng hơn** để quản lý shutdown thay vì đóng thủ công trong event listener. Tránh vừa đóng bằng listener, vừa để container destroy cùng resource một lần nữa.

### 10.1. Đóng đúng thứ tự

Khi parent sở hữu dependency dùng chung, thông thường dừng/đóng **child trước parent**. Đóng parent trước trong khi child còn hoạt động có thể khiến child tiếp tục sử dụng bean/tài nguyên đã bị parent hủy.

Cơ chế parent/child không phải một hệ thống orchestration toàn năng bảo đảm mọi tài nguyên được đóng theo thứ tự mong muốn. Khi bạn tự tạo nhiều context, hãy sở hữu trình tự lifecycle rõ ràng.

## 11. Khi nào không cần lọc hoặc cần lọc khác?

### 11.1. Muốn đếm mọi lượt child refresh

Listener cha có thể cố ý lưu metric cho mọi `ContextRefreshedEvent` của cả cây. Khi đó, chính event context là một **nhãn** của metric, không phải lý do bỏ qua. Dùng ID/nhãn ổn định phù hợp với hệ thống đo, tránh tạo cardinality vô hạn từ ID ngẫu nhiên.

### 11.2. Chỉ muốn nhận một child cụ thể

Không chỉ so sánh với owner; cần predicate hợp yêu cầu:

```java
if (event.getApplicationContext() != targetChildContext) {
    return;
}
```

Đoạn này hợp lệ nếu bạn thật sự giữ tham chiếu tới `targetChildContext`. Nếu child có thể được tạo lại, tham chiếu identity sẽ thay đổi; thiết kế cách phát hiện/đăng ký child mới thay vì giữ reference cũ mãi mãi.

### 11.3. Muốn phân biệt tenant/workspace trong custom event

Không dùng object identity của context để thay thế tenant ID trong domain logic. Một context có thể phục vụ nhiều tenant, hoặc nhiều context có thể cùng xử lý một tenant qua thời gian. Hãy đặt `tenantId`, `aggregateId`, `requestId` hay `correlationId` vào event và lọc theo ý nghĩa **nghiệp vụ**.

### 11.4. Muốn xử lý event tại child nhưng không muốn parent biết

Spring Framework hierarchy mặc định **không có thao tác “stopPropagation()” trong ApplicationEvent** giống DOM event. Nếu đây là ràng buộc thật, cân nhắc tách publisher/event bus chuyên biệt, không tạo parent-child cho những phạm vi cần cô lập, hoặc thiết kế event/listener filter ở parent. Đừng trông đợi một cờ bí mật trong `@EventListener` sẽ tự chặn đường event lên ancestor.

## 12. @Order và @Async có giải quyết được duplicate event không?

**Không.**

`@Order` thay đổi thứ tự ưu tiên giữa listener phù hợp trong phạm vi xử lý của multicaster; nó **không thay đổi origin** của event và không tự bảo đảm listener chỉ thấy event của own context.

`@Async` khiến handler có thể chạy bất đồng bộ khi đã cấu hình hỗ trợ. Nó cũng **không ngăn event đi lên parent**. Thậm chí khi có nhiều context và executor, thứ tự log có thể khó đoán hơn; việc xử lý idempotent và lọc đúng origin càng quan trọng.

Ví dụ:

```java
@EventListener
@Order(10)
public void onRefreshed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != ownContext) {
        return;
    }
    // Logic đúng cho context hiện tại.
}
```

Đây là method minh họa trong bean có field `ownContext`, cần import `@EventListener`/`@Order`. Thứ tự có thể có giá trị, nhưng **guard mới là điều kiện loại event của descendant**.

### 12.1. Exception và error handler

Theo mặc định, Spring `SimpleApplicationEventMulticaster` xử lý đồng bộ. Exception từ listener không được xử lý có thể lan lên nơi publish event và ảnh hưởng startup/shutdown hoặc request đang phát event.

Nếu bạn thay multicaster bằng cơ chế async/error handler, hành vi báo lỗi và thứ tự xử lý sẽ khác. Tuy nhiên, dù sync hay async, **việc duplicate do propagation vẫn là trách nhiệm thiết kế listener của bạn**.

## 13. Phân biệt các cách đăng ký listener

Một listener có thể được đưa vào context bằng:

- `@Component` + implement `ApplicationListener<EventType>`.
- `@Component` chứa method `@EventListener`.
- `@Bean` trả về `ApplicationListener<?>` hoặc bean có method `@EventListener`.
- `ConfigurableApplicationContext.addApplicationListener(...)` trước refresh.
- `SpringApplication.addListeners(...)` trước `run(...)`, phù hợp các early Boot events.
- `META-INF/spring.factories` cho một số listener của thư viện cần được Boot nạp sớm.

**Quan trọng:** đăng ký listener ở **một context** không có nghĩa bean listener đó tự được copy sang child. Parent listener nhận child event vì **propagation**, không phải Spring “nhân bản bean listener sang mọi context”.

### 13.1. Phân biệt đăng ký nhiều lần với event đến nhiều nơi

Nếu listener tạo ra log lặp, hãy kiểm tra hai trục riêng:

1. **Topology:** event được publish ở context nào, có parent nào, đi qua các context nào?
2. **Registration:** bean/listener được đăng ký mấy lần tại mỗi context? `@ComponentScan` có quét trùng package? `addListeners` và `spring.factories` có cùng class không?

Chỉ khi tách hai câu hỏi này mới xác định đúng nguyên nhân và sửa tối thiểu.

## 14. Một cách log giúp chẩn đoán đúng nguồn

Không nên chỉ log:

```text
ContextRefreshedEvent received
ContextRefreshedEvent received
```

Hai dòng này không cho biết có hai contexts hay hai registrations.

Nên log thông tin không nhạy cảm về:

```text
listenerOwner=parent eventContext=parent type=ContextRefreshedEvent
listenerOwner=parent eventContext=child  type=ContextRefreshedEvent
```

Trong handler:

```java
@EventListener
void trace(ContextRefreshedEvent event) {
    System.out.println("listenerOwner=" + ownContext.getId()
            + " eventContext=" + event.getApplicationContext().getId()
            + " type=" + event.getClass().getSimpleName());
}
```

Method trên là snippet bên trong bean đã có `ownContext`. ID chỉ là metadata giúp quan sát, **không thay thế** phép so sánh object identity trong guard.

Nếu log cần tương quan giữa nhiều lần restart/deploy, thêm instance ID/startup ID phù hợp; không log token, secret hoặc toàn bộ `Environment`.

## 15. Các lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm tra/sửa |
| --- | --- | --- |
| Listener parent in hai dòng ContextRefreshedEvent | Parent và child đều refresh, event child được truyền lên cha | In `event.getApplicationContext().getId()`, lọc `!= ownContext` nếu chỉ xử lý own event |
| Một child listener nhận event của parent mà không có publish thủ công | Có thể topology/registration khác dự kiến hoặc event được republish | Kiểm tra nơi publish, parent chain và bean listener thực tế; cơ chế mặc định không truyền xuống child |
| Listener ở con A nhận event của con B | Có thể cả hai dùng chung listener ngoài context hoặc có custom bridge | Kiểm tra multicaster và event bus; siblings không tự nhận event của nhau |
| Logic cleanup parent chạy khi child đóng | Parent nghe `ContextClosedEvent(child)` | Lọc event context trước side effect; dùng bean destroy cho tài nguyên parent |
| So sánh tên context vẫn sai | Hai context có cùng class/name/id | So sánh `event.getApplicationContext() == ownContext` |
| `getSource()` là object nghiệp vụ, không phải context | Custom event tự định nghĩa source | Định nghĩa `originContext`/`publisherId` rõ ràng |
| Custom payload không có method getApplicationContext() | Payload không phải `ApplicationContextEvent` | Mang origin trong payload hoặc lọc theo type/metadata của event |
| Trùng log dù đã lọc own context | Listener có thể được đăng ký lặp trong cùng context | Kiểm tra `@ComponentScan`, `@Bean`, `addListeners`, `spring.factories` |
| Lọc origin nhưng callback vẫn chạy nhiều lần | Guard chỉ bỏ event ngoại lai, không cung cấp exactly-once | Dùng idempotence hoặc khóa nghiệp vụ khi có side effect |
| @Order không hết duplicate | @Order chỉ sắp thứ tự callback | Dùng guard phù hợp và kiểm tra topology |
| @Async khiến thứ tự log thay đổi | Executor chạy callback bất đồng bộ | Đừng dùng thứ tự log để suy luận nguồn; logging có context metadata |
| Startup thất bại khi child refresh | Parent listener ném exception trong callback từ child | Kiểm tra stack trace handler, hạn chế side effect, xác định failure policy |
| Test đếm event khác số lượng test | TestContext caching, @DirtiesContext tạo context mới, hierarchy | Quan sát context identity, scope của test và cache |
| Muốn event chỉ ở child nhưng parent vẫn nhận | Propagation là default của hierarchy | Thiết kế bridge riêng hoặc filter ở parent |
| Spring Boot listener nhận nhiều loại ApplicationReadyEvent | Nhiều SpringApplication trong hierarchy | Dựa vào `event.getApplicationContext()` và owner theo contract event |
| Dùng filter context để phân biệt tenant | Context không nhất thiết là tenant | Thêm tenantId trong domain event |

## 16. Test cơ chế propagation và logic lọc

Ngoài log thủ công, integration test nên xác nhận **số lần được gọi và origin thực tế**.

Ý tưởng:

1. Tạo parent, đăng ký listener nhận `ContextRefreshedEvent` và tăng counter riêng cho `parent` và `child`.
2. Refresh parent một lần: counter `parent-origin` phải tăng.
3. Tạo child, `setParent(parent)`, refresh child: counter `child-origin` phải tăng tại parent listener.
4. Kiểm tra listener **own-only** của parent không tăng ở lần refresh child.
5. Publish event nghiệp vụ từ child: child và parent listener phù hợp đều nhận; sibling không tự nhận.
6. Publish từ parent: parent listener nhận; child listener không tự nhận.
7. Đóng child rồi parent: nếu theo dõi `ContextClosedEvent`, đảm bảo listener parent không cleanup sai vào thời điểm đóng child.

Ví dụ assert bằng Java để kiểm tra origin của refresh event:

```java
AtomicInteger parentOwnRefreshes = new AtomicInteger();
AtomicInteger parentObservedChildRefreshes = new AtomicInteger();

// Đăng ký listener typed cho ContextRefreshedEvent trong parent.
if (event.getApplicationContext() == parent) {
    parentOwnRefreshes.incrementAndGet();
} else if (event.getApplicationContext() == child) {
    parentObservedChildRefreshes.incrementAndGet();
}
```

Đây là **snippet minh họa trong test/listener**, không phải một file chạy độc lập; cần import `AtomicInteger`, các biến `parent`/`child`/`event` phải có trong scope và listener được đăng ký ở đúng context trước refresh.

### 16.1. Context caching và test lifecycle

`@SpringBootTest` có thể tái dùng cùng context nhờ TestContext cache. Vì vậy một `ContextRefreshedEvent` không nhất thiết phát trước **mỗi** test method. Khi dùng `@DirtiesContext`, context có thể bị đóng và tạo lại, làm số lần event thay đổi. Không xây kiểm thử dựa vào “một test method = một lần refresh” nếu chưa kiểm soát cấu hình cache/hierarchy.

## 17. Vận hành khi có nhiều child contexts

Khi parent dùng chung database pool, metrics, message listener hoặc cache:

- **Định nghĩa ownership:** tài nguyên thuộc parent hay thuộc mỗi child? Không đóng tài nguyên chung khi một child kết thúc.
- **Phân ranh sự kiện:** event nào có ý nghĩa hệ thống, event nào chỉ liên quan một child?
- **Ghi nhận origin:** lifecycle event dùng `getApplicationContext()`; domain event nên có metadata xuất xứ/nghiệp vụ rõ ràng.
- **Chọn side-effect policy:** own-only, tất cả descendants, hay chỉ những child được cho phép.
- **Bảo đảm idempotence:** filtering không ngăn nhiều event hợp lệ hoặc retry của logic nghiệp vụ.
- **Bảo đảm an toàn đồng thời:** mỗi context có thể dùng multicaster/executor riêng; counter/cache không được giả định luôn xử lý tuần tự.
- **Shutdown có trật tự:** ưu tiên stop/close child trước parent khi parent giữ dependency mà child dùng.
- **Metrics và logs:** tránh cardinality cao; ghi context ID/role, instance ID và correlation ID cần thiết.
- **Đối chiếu readiness:** context refresh của child không đồng nghĩa toàn ứng dụng đã ready; Boot còn runner và availability state.

Nhớ rằng Spring Boot có thể tạo nhiều context cho những mô hình đặc thù, nhưng **không phải tất cả applications đều cần hierarchy**. Một cơ chế thiết kế phức tạp chỉ để dùng chung vài bean có thể khó vận hành hơn việc dùng một context và cấu trúc package/module rõ ràng.

## 18. Câu hỏi tự kiểm tra

**1. Parent có một listener ContextRefreshedEvent; parent và child refresh mỗi bên một lần. Parent listener có thể nhận bao nhiêu sự kiện?**

Thông thường **hai**: một từ parent, một từ child truyền lên. Đây là hai event khác nhau, không nhất thiết do listener bị đăng ký trùng.

**2. Child có tự nhận event do parent.publishEvent(...) không?**

**Không** trong cơ chế propagation mặc định. Hướng đi là nơi publish → parent → ancestor, không phải broadcast xuống child.

**3. Hai child cùng parent có nhận event trực tiếp của nhau không?**

**Không tự động**. Parent có thể nhận cả hai, nhưng không tự forward sang child còn lại.

**4. Dùng getId() so sánh có đủ lọc đúng context không?**

**Không luôn đủ** vì ID có thể trùng hoặc thay đổi. Với sự kiện `ApplicationContextEvent`, so sánh **object identity** của `event.getApplicationContext()` với `ownContext`.

**5. Custom ApplicationEvent có getApplicationContext() như ContextRefreshedEvent không?**

**Không mặc định**. Tùy class event. Với domain event, tự mang `originContext` hoặc metadata tương ứng nếu cần phân biệt nguồn.

**6. @Order giúp parent không nhận child event chứ?**

**Không**. `@Order` chỉ ảnh hưởng thứ tự listener; guard mới lọc event theo origin.

**7. Listener parent xử lý ContextClosedEvent(child) và đóng pool chung. Lỗi ở đâu?**

Nó không kiểm tra origin, nên đóng tài nguyên của parent khi child kết thúc. Dùng guard own context và giao cleanup cho lifecycle owner phù hợp.

**8. Cơ chế event propagation tự gửi qua microservice khác không?**

**Không**. Đây là cơ chế trong một JVM/context hierarchy. Cần messaging hoặc API nếu muốn truyền liên tiến trình.

**9. Nếu muốn parent audit mọi child, có cần guard own-only không?**

**Không**. Parent có thể cố ý nghe descendants; nhưng cần nhận diện đúng origin, loại trùng logic và giới hạn side effects.

## 19. Checklist chốt kiến thức

1. Biết context nào là parent/child; đừng suy luận từ package hay dependency Gradle.
2. Ghi nhớ hướng propagation: **context phát → ancestor**, không tự xuống child hoặc sang sibling.
3. Với `ContextRefreshedEvent`/`ContextClosedEvent` và các `ApplicationContextEvent`, lấy origin bằng `event.getApplicationContext()`.
4. Khi xử lý **chỉ context của mình**, lọc bằng `event.getApplicationContext() == ownContext`.
5. Lấy `ownContext` từ constructor injection hoặc `ApplicationContextAware` trong **bean listener thuộc đúng context**.
6. Với domain event, tự định nghĩa metadata origin và bộ lọc theo hợp đồng nghiệp vụ.
7. Phân biệt event propagation với listener đăng ký trùng và với nhiều event hợp lệ.
8. Đừng kỳ vọng `@Order`/`@Async` làm biến mất propagation.
9. Dùng `ContextClosedEvent` cẩn thận để không destroy resource cha khi context con đóng.
10. Dùng test parent–child để kiểm tra origin, số lượt nhận và logic bỏ qua.
11. Thiết kế xử lý side effect idempotent; context filter không phải exactly-once delivery.
12. Chọn readiness/lifecycle event đúng giai đoạn; context refresh không đồng nghĩa ứng dụng hoàn toàn ready.

## 20. Tóm tắt

```text
CHILD publishEvent(E)
    |
    +--> child listener(s)
    |
    +--> PARENT listener(s)
             |
             +--> ancestor listener(s)

PARENT publishEvent(E)
    |
    +--> parent listener(s)
    X    không tự xuống child

Với ApplicationContextEvent:
    event.getApplicationContext() = context PHÁT SINH event

Guard nếu chỉ xử lý context của mình:
    if (event.getApplicationContext() != ownContext) return;
```

**Quy tắc ngắn gọn:** một listener ở context cha có thể nhận event của các context con; điều đó là **hành vi thiết kế của Spring Framework**. Trước khi tạo side effect, hãy quyết định listener của bạn cần **own-only** hay **all-descendants**. Nếu cần own-only, so sánh context phát sự kiện và context sở hữu listener bằng **object identity**. Nếu là event nghiệp vụ tự định nghĩa, phải có metadata nguồn rõ ràng, không suy đoán từ tên event.

## Tài liệu chính thức

- [Spring Boot 3.3 — SpringApplication: Application Events and Listeners, lọc sự kiện từ child contexts](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplicationBuilder API và context hierarchy](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html)
- [Spring Boot — Build an ApplicationContext Hierarchy](https://docs.spring.io/spring-boot/3.3/how-to/application.html)
- [Spring Framework 6.1 — AbstractApplicationContext: publishEvent và parent propagation](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework — Application events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.1 — ApplicationContextEvent API](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/context/event/ApplicationContextEvent.html)
- [Spring Framework 6.1 — ContextRefreshedEvent API](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html)
