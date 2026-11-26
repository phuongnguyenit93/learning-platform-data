# Kiểm soát auto-declare, shouldDeclare và admin chịu trách nhiệm

Trong **Spring AMQP** (tích hợp RabbitMQ theo AMQP 0-9-1), việc tạo **exchange**, **queue** và **binding** có thể được khai báo bằng các bean Spring rồi tự động áp dụng lên RabbitMQ. Cơ chế này giúp môi trường phát triển khởi chạy thuận tiện, nhưng khi một ứng dụng kết nối nhiều broker, nhiều virtual host hoặc dùng chung tài nguyên do dịch vụ khác quản lý, **tự động khai báo không kiểm soát** có thể tạo tài nguyên nhầm chỗ hoặc gây lỗi khi thuộc tính khai báo không khớp.

Bài học thuộc chương **Khai báo tài nguyên**, tập trung vào ba câu hỏi:

1. **Khi nào** Spring AMQP tự khai báo tài nguyên trên broker? Đây là trách nhiệm của **RabbitAdmin** và cơ chế **auto-declare**.
2. **Tài nguyên nào** được phép tự khai báo? Đây là vai trò của **Declarable.shouldDeclare()** và **setShouldDeclare(false)**.
3. **RabbitAdmin nào** có trách nhiệm khai báo tài nguyên đó? Đây là vai trò của **setAdminsThatShouldDeclare(...)** và **RabbitAdmin.setExplicitDeclarationsOnly(true)**.

Các thiết lập này điều khiển **topology** của RabbitMQ. Chúng không thay thế **RabbitTemplate** để gửi message, **@RabbitListener** để nhận message, xác nhận giao nhận, retry, dead-letter hay quyền truy cập mà broker cấp cho từng tài khoản.

## 1. Nhìn đúng vòng đời khai báo tài nguyên

Một bean Java kiểu **Queue** chỉ mô tả queue mong muốn trong **ApplicationContext**; bản thân việc tạo bean không bảo đảm queue đã tồn tại ở RabbitMQ. Để biến mô tả đó thành tài nguyên thực, ứng dụng cần một thành phần quản trị phù hợp, thường là **RabbitAdmin**.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Queue / Exchange / Binding<br/>hoặc Declarables"]
    A --> C["RabbitAdmin"]
    B --> D{"Lọc các khai báo"}
    C --> D
    D -->|"shouldDeclare = false"| X["Bỏ qua tài nguyên"]
    D -->|"Không thuộc admin này<br/>hoặc strict mode không có owner"| Y["Bỏ qua với admin này"]
    D -->|"Thỏa điều kiện"| E["ConnectionFactory<br/>của RabbitAdmin"]
    E --> F[("RabbitMQ broker<br/>vhost tương ứng")]
    F --> G["Exchange, Queue, Binding<br/>được khai báo"]
~~~

Trình tự thường gặp:

1. Spring tạo các bean **Exchange**, **Queue**, **Binding** hoặc nhóm **Declarables**.
2. **RabbitAdmin** lấy các khai báo từ cùng ApplicationContext.
3. Khi một kết nối phù hợp được mở, admin kiểm tra cờ khai báo của từng tài nguyên và admin được chỉ định.
4. Các đối tượng hợp lệ được gửi thành lệnh khai báo đến RabbitMQ qua **ConnectionFactory** mà admin sử dụng.
5. RabbitMQ tạo tài nguyên mới nếu chưa có, hoặc kiểm tra tính tương thích của tài nguyên đã tồn tại.

Với cấu hình phổ biến dùng **CachingConnectionFactory** ở chế độ cache **CHANNEL** và RabbitAdmin bật auto startup, Spring AMQP thực hiện khai báo theo cơ chế *lazy*: thao tác có thể bắt đầu khi kết nối AMQP đầu tiên mở, sau đó có thể thực hiện lại khi kết nối được khôi phục. Vì thế **không nên suy luận chỉ từ việc ApplicationContext đã khởi tạo xong rằng broker đã có đủ queue**.

**Ví dụ:** ứng dụng đăng ký bean **orders.created.queue**, nhưng broker chưa sẵn sàng hoặc chưa hề có kết nối nào được tạo. Bean vẫn tồn tại trong JVM; queue tương ứng chưa chắc xuất hiện trong RabbitMQ Management.

### Phân biệt đối tượng khai báo trong code với tài nguyên broker

| Trong Spring | Trên RabbitMQ | Ý nghĩa |
| --- | --- | --- |
| **new Queue("orders.created")** | Queue **orders.created** | Bean mô tả thuộc tính; RabbitAdmin hoặc thao tác khác phải khai báo lên broker. |
| **new DirectExchange("orders.events")** | Exchange **orders.events** | Exchange trong code chưa tự tạo ra queue hoặc binding. |
| **BindingBuilder.bind(...).to(...)** | Binding giữa exchange và queue | Cần queue/exchange đích tồn tại và được khai báo phù hợp. |
| **new Declarables(exchange, queue, binding)** | Bộ ba tài nguyên được admin duyệt | Là nhóm khai báo để RabbitAdmin phát hiện; không phải lời gọi publish message. |
| **RabbitTemplate.convertAndSend(...)** | Message đi vào exchange | Là gửi message; không thay cho việc quản trị topology. |
| **@RabbitListener(queues = "...")** | Consumer đăng ký lắng nghe queue | Chỉ nêu tên queue cần tiêu thụ; queue phải tồn tại hoặc được khai báo bằng cơ chế thích hợp. |

## 2. Mặc định auto-declare hoạt động thế nào?

**RabbitAdmin** triển khai giao diện **AmqpAdmin**. Nó có thể khai báo tự động các bean **Declarable** trong cùng ApplicationContext và cũng cung cấp API thao tác chủ động như **declareExchange**, **declareQueue**, **declareBinding**, **deleteQueue**.

Trong nhiều dự án Spring Boot sử dụng tích hợp RabbitMQ AMQP 0-9-1, auto-configuration tạo **AmqpAdmin/RabbitAdmin** khi có đủ điều kiện. Thuộc tính Boot **spring.rabbitmq.dynamic** thường có giá trị mặc định **true** và kiểm soát việc Boot tự tạo **AmqpAdmin**. Nếu cấu hình riêng các admin hoặc connection factory, cần kiểm tra bean thực tế trong context thay vì giả định Boot luôn tạo đúng một admin.

Ví dụ một ứng dụng có các bean:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class BasicTopology {

    @Bean
    DirectExchange orderExchange() {
        return new DirectExchange("demo.orders.events", true, false);
    }

    @Bean
    Queue orderQueue() {
        return QueueBuilder.durable("demo.orders.email").build();
    }

    @Bean
    Binding orderBinding(Queue orderQueue, DirectExchange orderExchange) {
        return BindingBuilder.bind(orderQueue)
                .to(orderExchange)
                .with("order.created");
    }
}
~~~

Nếu ApplicationContext có một **RabbitAdmin** hoạt động và ứng dụng mở kết nối thành công, ba bean có thể được dùng để tạo exchange, queue và binding trên broker. Ví dụ dùng tên tham số bean **orderQueue** và **orderExchange** để Spring phân giải; trong ứng dụng có nhiều Queue/Exchange, nên sử dụng **@Qualifier** nhằm tránh chọn nhầm bean.

### Những nút điều khiển dễ bị nhầm

| Thiết lập | Áp dụng lên | Mục đích |
| --- | --- | --- |
| **spring.rabbitmq.dynamic=false** | Spring Boot auto-configuration | Không tự tạo **AmqpAdmin** theo cơ chế Boot tương ứng; không cấm bạn tạo admin thủ công. |
| **RabbitAdmin.setAutoStartup(false)** | Một RabbitAdmin | Không đăng ký cơ chế khai báo tự động của admin đó khi kết nối mở; có thể chủ động gọi **initialize()** hoặc dùng admin theo cơ chế khác. |
| **queue.setShouldDeclare(false)** | Một Queue | Loại queue này khỏi **auto-declaration** bởi các admin. |
| **exchange.setShouldDeclare(false)** | Một Exchange | Tương tự cho exchange. |
| **binding.setShouldDeclare(false)** | Một Binding | Tương tự cho binding. |
| **setAdminsThatShouldDeclare(admin)** | Từng tài nguyên Declarable | Chọn một hoặc nhiều admin được phép tự khai báo tài nguyên. |
| **admin.setExplicitDeclarationsOnly(true)** | Một RabbitAdmin | Admin này chỉ xử lý các tài nguyên **chỉ định đích danh** admin đó. |
| **container.setAutoDeclare(false)** | Listener container | Tắt hành vi **listener container** chủ động nhờ admin khai báo lại tài nguyên khi phát hiện queue bị thiếu lúc bắt đầu. |

**Chú ý:** cờ **autoStartup** của **RabbitAdmin** và cờ **autoDeclare** của **message listener container** là **hai cơ chế khác nhau**. Việc tắt một cơ chế không tự động làm mọi cơ chế còn lại ngừng tạo queue.

## 3. shouldDeclare: loại từng tài nguyên khỏi vòng khai báo tự động

Các loại **Queue**, **Exchange** và **Binding** có triển khai **Declarable**. Giao diện cung cấp **shouldDeclare()** để RabbitAdmin quyết định có nên khai báo tự động đối tượng hay không. Các lớp triển khai thông dụng có phương thức **setShouldDeclare(boolean)**.

Mặc định:

~~~text
shouldDeclare() == true
~~~

Nếu muốn ứng dụng **tham chiếu nhưng không sở hữu việc tạo** queue do một dịch vụ khác hoặc quy trình triển khai quản lý:

~~~java
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExternallyManagedQueueConfig {

    @Bean
    Queue partnerOrdersQueue() {
        Queue queue = QueueBuilder.durable("partner.orders.inbound").build();
        queue.setShouldDeclare(false);
        return queue;
    }
}
~~~

Ý nghĩa thực tế:

- **partnerOrdersQueue** vẫn là bean có thể được inject, tham chiếu bằng tên hoặc dùng khi cấu hình listener.
- RabbitAdmin sẽ **không tự tạo** queue này khi quét các bean khai báo.
- **setShouldDeclare(false)** **không xóa** queue nếu nó đã tồn tại trên broker.
- **setShouldDeclare(false)** **không cấp quyền** cho user AMQP và **không cấm** code khác gọi trực tiếp API quản trị hoặc hệ thống khác tạo queue.
- Nếu queue chưa được tạo bởi bên chịu trách nhiệm, listener trỏ tới tên queue đó có thể gặp lỗi khi cố tiêu thụ.

Đây là cách thích hợp khi một dịch vụ có nhu cầu **sử dụng tài nguyên có sẵn** nhưng chỉ có một hệ thống quản lý topology.

### Mỗi thành phần có cờ riêng

Giả sử queue và exchange đều do hệ thống bên ngoài tạo, nhưng code vẫn khai báo một binding:

~~~java
Queue queue = QueueBuilder.durable("partner.orders.inbound").build();
DirectExchange exchange = new DirectExchange("partner.orders.events");
Binding binding = BindingBuilder.bind(queue)
        .to(exchange)
        .with("order.created");

queue.setShouldDeclare(false);
exchange.setShouldDeclare(false);
// binding vẫn có shouldDeclare=true nếu không chỉnh!
~~~

RabbitAdmin có thể **vẫn cố khai báo binding** dù hai đối tượng còn lại bị bỏ qua. Điều này chỉ thành công nếu exchange và queue thực sự đã tồn tại và quyền trên broker cho phép tạo binding. Nếu toàn bộ topology do bên ngoài quản lý, cần xem xét:

~~~java
binding.setShouldDeclare(false);
~~~

**Quy tắc:** kiểm soát đầy đủ **Exchange + Queue + Binding**. Đặt cờ trên queue **không tự lan truyền** sang binding hay exchange liên quan.

## 4. Chọn admin được phép khai báo bằng setAdminsThatShouldDeclare

Khi có nhiều **RabbitAdmin** trong cùng ApplicationContext, các admin có thể sử dụng **ConnectionFactory** khác nhau, hướng tới các broker hoặc virtual host khác nhau.

Nếu không chỉ định danh sách admin chịu trách nhiệm, mặc định **mọi RabbitAdmin** được phép xem xét khai báo những tài nguyên có **shouldDeclare=true**, miễn là admin hoạt động và không đặt **explicitDeclarationsOnly=true**. Với nhiều broker, điều này có thể khiến queue của nghiệp vụ A xuất hiện nhầm trên broker B.

Để phân quyền sở hữu ngay trong topology:

~~~java
Queue queue = QueueBuilder.durable("billing.orders.inbound").build();
queue.setAdminsThatShouldDeclare(billingAdmin);

DirectExchange exchange = new DirectExchange("billing.orders.events");
exchange.setAdminsThatShouldDeclare(billingAdmin);

Binding binding = BindingBuilder.bind(queue)
        .to(exchange)
        .with("order.created");
binding.setAdminsThatShouldDeclare(billingAdmin);
~~~

Ở ví dụ này, **billingAdmin** là bean **RabbitAdmin** đã có sẵn. Khi tự động quét các Declarable, chỉ admin được chỉ định mới xử lý những khai báo này. Nếu cần hai admin cùng chịu trách nhiệm cho cùng một định nghĩa, có thể truyền cả hai:

~~~java
queue.setAdminsThatShouldDeclare(billingAdmin, backupBillingAdmin);
~~~

Việc này có ý nghĩa khi hai admin thực sự cần khai báo tài nguyên tại những đích khác nhau; nó **không sao chép message từ broker này sang broker kia**. Tự động khai báo queue giống tên trên hai broker chỉ tạo **hai queue độc lập**, không thiết lập replication/federation.

### Quan hệ giữa tên bean và tên tài nguyên

Bạn có thể có bean **@Bean("billingQueue")** quản lý queue thực tên **billing.orders.inbound**. Hai tên này có vai trò khác nhau:

- **Tên bean Spring:** dùng để inject, tham chiếu bằng **@Qualifier** hoặc xác định đối tượng trong ApplicationContext.
- **Tên RabbitMQ queue:** dùng trong lệnh declare và khi listener/publisher thực sự giao tiếp với broker.
- **Admin chịu trách nhiệm:** là một hoặc nhiều bean RabbitAdmin mà declarable liên kết qua **setAdminsThatShouldDeclare**.

Đừng suy luận RabbitAdmin sẽ tự biết ai là chủ tài nguyên chỉ vì bean và queue đặt tên có cùng tiền tố.

## 5. explicitDeclarationsOnly: mặc định không nhận tài nguyên “không ai sở hữu”

**RabbitAdmin.setExplicitDeclarationsOnly(true)** là chính sách theo admin: **chỉ khai báo những Declarable đã chỉ định admin đó** bằng **setAdminsThatShouldDeclare(...)**.

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AdminConfig {

    @Bean("billingAdmin")
    RabbitAdmin billingAdmin(
            @Qualifier("billingConnectionFactory") ConnectionFactory connectionFactory) {

        RabbitAdmin admin = new RabbitAdmin(connectionFactory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }
}
~~~

Đoạn này giả định **billingConnectionFactory** được định nghĩa trước với broker/vhost và thông tin xác thực thích hợp.

Với cấu hình trên:

- Tài nguyên có **shouldDeclare=true**, nhưng **không chỉ định admin**, bị **billingAdmin bỏ qua**.
- Tài nguyên gọi **setAdminsThatShouldDeclare(billingAdmin)** và **shouldDeclare=true** sẽ được admin này khai báo tự động khi điều kiện kết nối cho phép.
- Tài nguyên **shouldDeclare=false** vẫn bị bỏ qua, **kể cả** đã gán billingAdmin.
- Nếu trong context còn một admin khác có **explicitDeclarationsOnly=false**, admin kia **vẫn có thể** khai báo các tài nguyên không chỉ định ai. Chỉ đặt strict mode ở một admin không đủ để kiểm soát các admin còn lại.

### Ma trận quyết định

Giả sử có hai RabbitAdmin đều đã kết nối được, **A** và **B**; **A.explicitDeclarationsOnly=true**, **B.explicitDeclarationsOnly=false**. Cả hai bật **autoStartup**, trừ khi nói khác:

| shouldDeclare | adminsThatShouldDeclare | A có tự khai báo? | B có tự khai báo? | Giải thích |
| --- | --- | --- | --- | --- |
| **true** | Không chỉ định | Không | Có | A chỉ nhận tài nguyên gán đích danh; B nhận khai báo không chỉ định. |
| **true** | **A** | Có | Không | Tài nguyên thuộc A. |
| **true** | **B** | Không | Có | Tài nguyên thuộc B. |
| **true** | **A, B** | Có | Có | Cả hai admin được chỉ định. |
| **false** | Không chỉ định | Không | Không | Cờ tại tài nguyên chặn mọi auto-declare. |
| **false** | **A, B** | Không | Không | Gán admin không ghi đè **shouldDeclare=false**. |

Nếu **B.explicitDeclarationsOnly=true** nữa, dòng không chỉ định admin sẽ bị **cả A lẫn B** bỏ qua. Nếu A hay B bật **setAutoStartup(false)**, nó không tự thực hiện vòng khai báo theo connection callback; bảng trên chỉ mô tả **quyền được xem xét**, không bảo đảm thời điểm thực thi.

### Khi nào dùng chế độ strict?

Phù hợp với hệ thống nhiều ứng dụng hoặc nhiều broker, khi bạn muốn mỗi tài nguyên có **chủ sở hữu rõ ràng**. Cách cấu hình này giúp việc review topology dễ dàng hơn: một queue vô tình được thêm vào ApplicationContext nhưng chưa được gán admin sẽ không tự xuất hiện trên broker của những admin ở chế độ strict.

## 6. Ví dụ cấu hình hoàn chỉnh cho một admin chịu trách nhiệm

Ví dụ một ứng dụng nhận sự kiện tạo đơn hàng và sở hữu topology **demo.orders.events → demo.orders.email**. Cùng ứng dụng đó cần biết queue **partner.orders.inbound** nhưng queue này do đối tác tạo trước.

Giả sử Spring Boot đã cấu hình RabbitMQ (host, port, username, password, vhost), cung cấp bean **ConnectionFactory** và thư viện **spring-rabbit** tương thích.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OwnedTopologyConfiguration {

    @Bean("ordersAdmin")
    RabbitAdmin ordersAdmin(ConnectionFactory connectionFactory) {
        RabbitAdmin admin = new RabbitAdmin(connectionFactory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }

    @Bean
    Declarables ownedOrderDeclarations(
            @Qualifier("ordersAdmin") RabbitAdmin ordersAdmin) {

        DirectExchange exchange =
                new DirectExchange("demo.orders.events", true, false);
        Queue queue = QueueBuilder.durable("demo.orders.email").build();
        Binding binding = BindingBuilder.bind(queue)
                .to(exchange)
                .with("order.created");

        exchange.setAdminsThatShouldDeclare(ordersAdmin);
        queue.setAdminsThatShouldDeclare(ordersAdmin);
        binding.setAdminsThatShouldDeclare(ordersAdmin);

        return new Declarables(exchange, queue, binding);
    }

    @Bean
    Queue partnerQueue() {
        Queue external = QueueBuilder.durable("partner.orders.inbound").build();
        external.setShouldDeclare(false);
        return external;
    }
}
~~~

Với Spring Boot, khi đã tự khai báo bean **RabbitAdmin**, auto-configuration thường không tạo một admin mặc định thứ hai nếu điều kiện tạo bean mặc định không còn phù hợp. Tuy vậy, cần **kiểm tra tất cả admin đang tồn tại** trong ApplicationContext nếu dùng thêm cấu hình thư viện hoặc cấu hình tùy chỉnh.

Đường đi mong đợi:

~~~mermaid
flowchart LR
    C["ApplicationContext"] -->|"ownedOrderDeclarations"| A["ordersAdmin<br/>explicitDeclarationsOnly=true"]
    A -->|"declare"| E["demo.orders.events"]
    A -->|"declare"| Q["demo.orders.email"]
    A -->|"declare"| B["Binding: order.created"]
    C -->|"partnerQueue<br/>shouldDeclare=false"| P["Không tự declare<br/>partner.orders.inbound"]
~~~

**Đối chiếu ở RabbitMQ Management** sau khi ứng dụng đã mở kết nối:

| Tài nguyên | Kỳ vọng sau auto-declare |
| --- | --- |
| Exchange **demo.orders.events** | Có, loại direct, durable. |
| Queue **demo.orders.email** | Có, durable. |
| Binding key **order.created** | Có, nối exchange với queue. |
| Queue **partner.orders.inbound** | Không được tạo **bởi ordersAdmin**; nếu đã tồn tại từ trước vẫn còn đó. |

Nếu publish:

~~~java
rabbitTemplate.convertAndSend(
        "demo.orders.events",
        "order.created",
        "O-1001"
);
~~~

Message được route tới **demo.orders.email** khi binding đã tồn tại. Phần publish này **không làm thay đổi** cấu hình admin chịu trách nhiệm hay cờ shouldDeclare.

### Tùy chọn khi cần một queue khác do cùng admin quản lý

Để thêm **demo.orders.audit** vào nhóm tài nguyên thuộc **ordersAdmin**, hãy tạo queue cùng binding tương ứng rồi gán admin cho **cả hai đối tượng** trước khi đưa vào **Declarables**. Không nên chỉ tạo queue rồi bỏ quên binding, hoặc chỉ gán admin cho queue mà quên gán cho exchange và binding.

## 7. Trường hợp nhiều broker: tránh khai báo nhầm đích

Giả sử dịch vụ có hai kết nối độc lập:

- **ordersConnectionFactory** trỏ tới RabbitMQ phục vụ đơn hàng.
- **auditConnectionFactory** trỏ tới RabbitMQ phục vụ hệ thống audit.

Mỗi ConnectionFactory cần được cấu hình riêng với host, port, user và vhost của broker tương ứng. Ví dụ sau tập trung vào điều phối admin; giả định hai bean ConnectionFactory này đã được đăng ký:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MultiBrokerDeclarations {

    @Bean("ordersAdmin")
    RabbitAdmin ordersAdmin(
            @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
        RabbitAdmin admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }

    @Bean("auditAdmin")
    RabbitAdmin auditAdmin(
            @Qualifier("auditConnectionFactory") ConnectionFactory factory) {
        RabbitAdmin admin = new RabbitAdmin(factory);
        admin.setExplicitDeclarationsOnly(true);
        return admin;
    }

    @Bean
    Declarables ordersDeclarations(
            @Qualifier("ordersAdmin") RabbitAdmin admin) {
        DirectExchange exchange =
                new DirectExchange("orders.events", true, false);
        Queue queue = QueueBuilder.durable("orders.notifications").build();
        Binding binding = BindingBuilder.bind(queue)
                .to(exchange).with("order.created");

        exchange.setAdminsThatShouldDeclare(admin);
        queue.setAdminsThatShouldDeclare(admin);
        binding.setAdminsThatShouldDeclare(admin);
        return new Declarables(exchange, queue, binding);
    }

    @Bean
    Declarables auditDeclarations(
            @Qualifier("auditAdmin") RabbitAdmin admin) {
        DirectExchange exchange =
                new DirectExchange("audit.events", true, false);
        Queue queue = QueueBuilder.durable("audit.log").build();
        Binding binding = BindingBuilder.bind(queue)
                .to(exchange).with("audit.recorded");

        exchange.setAdminsThatShouldDeclare(admin);
        queue.setAdminsThatShouldDeclare(admin);
        binding.setAdminsThatShouldDeclare(admin);
        return new Declarables(exchange, queue, binding);
    }
}
~~~

Kỳ vọng:

| Broker/vhost | Admin sở hữu | Tài nguyên xuất hiện sau auto-declare |
| --- | --- | --- |
| Orders | **ordersAdmin** | **orders.events**, **orders.notifications**, binding **order.created** |
| Audit | **auditAdmin** | **audit.events**, **audit.log**, binding **audit.recorded** |

Nếu admin khác kết nối cùng hoặc khác broker mà không có **explicitDeclarationsOnly=true**, cần đảm bảo tài nguyên đều được **chỉ định admin** rõ ràng. Thí dụ trên đã gán admin cho từng exchange, queue và binding nên tránh khai báo chéo trong các vòng auto-declare theo những admin này.

### Đừng quên consumer và publisher cũng phải chọn đúng broker

**setAdminsThatShouldDeclare(ordersAdmin)** chỉ điều khiển **ai khai báo topology**. Nó **không tự chuyển** RabbitTemplate hay @RabbitListener sang ordersConnectionFactory.

- **RabbitTemplate** gửi message thông qua connection factory của chính template.
- **@RabbitListener** dùng listener container factory được chọn (mặc định hoặc thông qua **containerFactory**), mà factory đó cũng phải trỏ tới broker/vhost cần tiêu thụ.
- **RabbitAdmin** quản lý topology qua connection factory được truyền khi khởi tạo.

Nếu admin trỏ tới broker Orders nhưng listener container lại trỏ tới broker Audit, listener vẫn có thể báo **queue not found**, dù queue đã được tạo đúng trên Orders. Khi dựng hệ thống nhiều broker, cần ghép nhất quán **admin + connection factory + RabbitTemplate + listener container factory**.

Việc hai broker cùng có queue/exchange trùng tên cũng **không tạo ra đồng bộ message giữa broker**. Muốn truyền sự kiện giữa broker cần giải pháp tích hợp riêng, không phải chỉ bật auto-declare.

## 8. Ba cách tắt hoặc trì hoãn tự khai báo: chọn đúng lớp

### Cách A: Tắt tạo AmqpAdmin mặc định của Spring Boot

Trong dự án dùng auto-configuration RabbitMQ có hỗ trợ thuộc tính tương ứng:

~~~yaml
spring:
  rabbitmq:
    dynamic: false
~~~

Điều này kiểm soát **việc Boot tự tạo bean AmqpAdmin**. Nếu ApplicationContext có bean **RabbitAdmin tự định nghĩa**, cấu hình trên **không có tác dụng xóa hoặc vô hiệu hóa** bean đó. Các phiên bản Boot và starter có thể khác nhau, vì vậy cần đối chiếu phần auto-configuration của phiên bản đang dùng.

Phù hợp khi topology được quản lý bởi **Terraform, Helm, RabbitMQ definitions, quy trình hạ tầng** hoặc một dịch vụ quản trị riêng và ứng dụng chỉ publish/consume.

### Cách B: Tắt cơ chế auto startup của một admin

~~~java
@Bean
RabbitAdmin deferredAdmin(ConnectionFactory connectionFactory) {
    RabbitAdmin admin = new RabbitAdmin(connectionFactory);
    admin.setAutoStartup(false);
    return admin;
}
~~~

Khi đó admin không tự đăng ký callback khai báo theo vòng mở kết nối thông thường. Có thể thực hiện **initialize()** một cách chủ động khi đã xác định thời điểm phù hợp và có kết nối broker. Không nhầm với **RabbitAdmin.declareQueue(queue)**: đây là lệnh quản trị chủ động, không phải vòng tự động quét bean.

Một listener container có cơ chế tự khai báo lại queue bị thiếu cũng có thể tương tác với RabbitAdmin trong một số cấu hình. Nếu yêu cầu là **tuyệt đối không để ứng dụng tạo topology**, phải rà soát cả admin, listener container và mọi lời gọi quản trị trực tiếp.

### Cách C: Chặn một tài nguyên cụ thể

~~~java
Queue queue = QueueBuilder.durable("external.reports").build();
queue.setShouldDeclare(false);
~~~

Khi ứng dụng sở hữu các queue khác nhưng chỉ có **external.reports** do bên ngoài quản lý, cách này cho phép giữ auto-declare trên phần tài nguyên ứng dụng sở hữu.

### Cách D: Chỉ chấp nhận tài nguyên được gán chủ

~~~java
admin.setExplicitDeclarationsOnly(true);
queue.setAdminsThatShouldDeclare(admin);
~~~

Cách này kiểm soát chặt **mối quan hệ giữa tài nguyên và admin** mà không tắt toàn bộ cơ chế khai báo.

## 9. Phân biệt RabbitAdmin.autoStartup và listener container.autoDeclare

Đây là lỗi suy luận phổ biến: thấy listener tạo lại queue khi khởi động rồi cho rằng **shouldDeclare** hoặc **RabbitAdmin.autoStartup** bị bỏ qua. Thực tế tồn tại nhiều đường kích hoạt liên quan:

| Tình huống | Cơ chế có thể liên quan | Điều cần kiểm tra |
| --- | --- | --- |
| Kết nối AMQP đầu tiên được mở | **RabbitAdmin** tự khai báo các bean Declarable | Có bean admin không, **autoStartup**, **shouldDeclare**, admin sở hữu, cache mode. |
| Broker mất kết nối rồi hoạt động lại | RabbitAdmin có thể khai báo lại topology sau khi kết nối khôi phục | Tài nguyên có cờ durable/auto-delete gì, cấu hình admin còn hợp lệ không. |
| Listener container bắt đầu khi một queue của nó bị thiếu | Listener container có thể nhờ **RabbitAdmin** khai báo lại | **autoDeclare** của container, admin được chỉ định và danh sách queue. |
| Ứng dụng gọi **amqpAdmin.declareQueue(queue)** | Lời gọi quản trị **chủ động** | Ai gọi API, chạy ở thời điểm nào, có quyền tạo queue không. |
| Một dịch vụ khác deploy topology | Công cụ/quy trình bên ngoài Spring | RabbitMQ Management, logs/audit và cấu hình của dịch vụ triển khai. |

Ở listener container, **autoDeclare** thường mặc định là **true**; khi nó phát hiện thiếu queue cần nghe lúc khởi động, nó có thể yêu cầu RabbitAdmin khai báo lại các AMQP object liên quan. Để dùng cơ chế này trong context có **nhiều RabbitAdmin**, listener container cần được chỉ định admin phù hợp theo cách cấu hình của phiên bản Spring AMQP đang dùng. Cơ chế recovery còn phụ thuộc việc queue cần nghe có tồn tại hay không và loại listener container; không nên cho rằng mọi queue thiếu luôn được tạo lại thành công.

**setShouldDeclare(false)** không bảo đảm ứng dụng có thể consume queue chưa tồn tại; nó đơn giản yêu cầu admin **không tự tạo** queue đó. Nếu listener khởi động và broker chưa có queue, hãy đưa topology vào broker trước hoặc thay đổi thứ tự khởi động cho phù hợp.

## 10. Những lỗi thực tế khi kiểm soát khai báo

### Lỗi 1: PRECONDITION_FAILED vì thuộc tính không khớp

Broker đã có queue **orders.jobs** không durable, trong khi code mới khai báo:

~~~java
Queue queue = QueueBuilder.durable("orders.jobs").build();
~~~

RabbitMQ không cho phép khai báo lại cùng tên queue với các thuộc tính không tương đương; nó có thể đóng channel và trả lỗi **PRECONDITION_FAILED**. **shouldDeclare=true** không có nghĩa là được tùy ý cập nhật thuộc tính queue đang có.

Cách xử lý: xác định ai là chủ topology, đối chiếu durable, auto-delete, arguments và queue type. Thiết kế thay đổi phù hợp (ví dụ tạo queue tên mới và chuyển lưu lượng). Không tự động xóa queue đang chứa dữ liệu chỉ để lệnh declare chạy qua.

### Lỗi 2: Đã gán admin cho queue nhưng quên binding

~~~java
queue.setAdminsThatShouldDeclare(ordersAdmin);
// binding và exchange chưa gán admin
~~~

Nếu admin chạy strict mode, queue được khai báo nhưng exchange/binding có thể bị bỏ qua. Khi publisher gửi message, queue không nhận do thiếu đường routing. Chỉ định quyền sở hữu **trên cả ba loại tài nguyên**.

### Lỗi 3: setShouldDeclare(false) rồi tưởng queue sẽ biến mất

Các cờ khai báo chỉ tác động đến lần **auto-declare sau đó**. Chúng không phải công cụ reconcile để xóa tài nguyên cũ; RabbitMQ giữ queue hiện có cho tới khi một quy trình xóa hoặc chính sách vòng đời phù hợp diễn ra.

### Lỗi 4: Tắt RabbitAdmin auto startup nhưng queue vẫn xuất hiện

Có thể queue do admin khác, container recovery hoặc thao tác **declareQueue** trực tiếp tạo ra. Cần kiểm tra **toàn bộ bean RabbitAdmin**, code cấu hình listener container và nguồn tạo topology bên ngoài ứng dụng.

### Lỗi 5: Có hai broker nhưng khai báo nhầm cả hai

Nếu hai admin cùng tự quét bean và không dùng **setAdminsThatShouldDeclare**, cùng một topology có thể bị khai báo trên cả hai broker. Áp dụng **explicitDeclarationsOnly=true** cho từng admin và gán rõ quyền sở hữu cho mỗi tài nguyên.

### Lỗi 6: Dùng ignoreDeclarationExceptions để che lỗi topology

~~~java
admin.setIgnoreDeclarationExceptions(true);
~~~

Thiết lập này có thể cho admin **ghi log lỗi rồi tiếp tục** các khai báo khác, nhưng nó **không sửa** lỗi quyền, cấu hình không tương thích hoặc binding sai. Chỉ dùng khi có lý do rõ ràng và hệ thống có giám sát; khi cần phát hiện topology sai sớm, nên giữ hành vi fail/raise phù hợp.

### Lỗi 7: Kết nối sai virtual host hoặc thiếu quyền

Queue trong **/** và queue cùng tên trong **/orders** là hai đối tượng khác nhau. RabbitAdmin dùng broker/vhost theo **ConnectionFactory** của nó, không theo tên @Bean. Tài khoản AMQP phải có quyền phù hợp để khai báo cấu trúc; **setAdminsThatShouldDeclare** là quyết định ở phía ứng dụng, không phải cơ chế cấp ACL của RabbitMQ.

## 11. Cách kiểm chứng bằng RabbitMQ Management và log

Để xác minh bài thực hành, dùng một RabbitMQ cục bộ và ứng dụng Spring Boot đã kết nối được. Có thể thực hiện tuần tự:

1. Đảm bảo broker chưa có các tài nguyên có tiền tố **demo.orders.** dùng trong ví dụ, hoặc chọn một bộ tên mới để tránh trùng với topology đã tạo từ trước.
2. Chạy cấu hình **OwnedTopologyConfiguration** với **ordersAdmin** strict mode và mở kết nối RabbitMQ qua publisher, listener hoặc API đã cấu hình.
3. Trong RabbitMQ Management, kiểm tra **Exchanges**, **Queues** và **Bindings** để xác nhận ba đối tượng thuộc admin được tạo như dự kiến.
4. Xác nhận **partner.orders.inbound** không bị tạo chỉ vì có bean **partnerQueue** với **shouldDeclare=false**. Nếu queue đã tồn tại, kiểm chứng bằng log hoặc thử ở môi trường mới thay vì suy đoán từ tên queue.
5. Tạm thời bỏ việc chỉ định admin trên một queue thử nghiệm trong một môi trường sạch, vẫn giữ **explicitDeclarationsOnly=true**; kiểm tra queue đó không được tạo qua admin strict.
6. Gán lại admin bằng **setAdminsThatShouldDeclare(ordersAdmin)**; mở/kích hoạt lại kết nối trong điều kiện an toàn hoặc chủ động gọi **ordersAdmin.initialize()** để kiểm tra khai báo.
7. Nếu có hai broker, kiểm tra **mỗi broker riêng** để bảo đảm topology xuất hiện đúng vị trí dự kiến.

Quan sát nên gồm:

| Nguồn kiểm tra | Câu hỏi cần trả lời |
| --- | --- |
| **Spring ApplicationContext / logs** | Có bao nhiêu RabbitAdmin và ConnectionFactory? Admin nào đang hoạt động? |
| **RabbitMQ Management → Exchanges** | Exchange đã được khai báo đúng loại, durable và vhost chưa? |
| **RabbitMQ Management → Queues** | Queue nào được tạo? Có queue ngoài phạm vi bị tạo nhầm không? |
| **RabbitMQ Management → Bindings** | Binding đúng nguồn, đích, routing key chưa? |
| **Broker logs / ứng dụng logs** | Có lỗi NOT_FOUND, ACCESS_REFUSED hay PRECONDITION_FAILED không? |
| **Publisher và consumer** | Sau khi topology hợp lệ, message có đi đúng exchange và đến queue phù hợp không? |

**Không dùng việc message gửi thành công để kết luận topology được khai báo chính xác.** Một exchange có thể tồn tại nhưng binding bị thiếu, khiến message không được route. Publisher confirm cũng không bảo đảm consumer đã xử lý hoàn tất; chất lượng giao nhận cần kiểm tra thêm ack, retry, dead-letter và idempotency theo yêu cầu nghiệp vụ.

## 12. Bài tập tình huống

**Tình huống A:** Có một queue **invoice.inbound** đã được hạ tầng tạo, ứng dụng cần dùng @RabbitListener nhưng không muốn tạo queue này. Bạn cấu hình thế nào?

**Gợi ý:** tạo bean Queue hoặc tham chiếu queue theo tên, dùng **setShouldDeclare(false)** nếu bean tham gia vòng auto-declare; bảo đảm queue được hạ tầng tạo trước khi consumer khởi động.

**Tình huống B:** Ứng dụng có hai admin: **adminA** và **adminB**, cả hai có **explicitDeclarationsOnly=true**. Queue **q1** có **shouldDeclare=true** nhưng không gán admin. Queue **q2** gán **adminA**. Admin nào tạo từng queue?

**Đáp án:** **q1** không được admin nào tự khai báo theo cơ chế quét; **q2** được **adminA** tự khai báo nếu admin đang hoạt động và kết nối thành công.

**Tình huống C:** Queue được gán **adminA**, nhưng **setShouldDeclare(false)**. Chỉ định admin có “bật lại” auto-declare không?

**Đáp án:** Không. **shouldDeclare=false** chặn auto-declare của tài nguyên.

**Tình huống D:** Đã gọi **exchange.setShouldDeclare(false)**, nhưng binding đến exchange đó vẫn được khai báo bởi admin. Có gì cần lưu ý?

**Đáp án:** Cờ không lan truyền giữa các đối tượng. Binding vẫn có thể được admin cố khai báo và thất bại nếu exchange chưa tồn tại. Cần quyết định quyền khai báo cho từng phần topology.

**Tình huống E:** Admin strict mode đã khai báo đúng queue trên broker Orders, nhưng @RabbitListener vẫn báo không tìm thấy queue. Nguyên nhân nào cần kiểm tra trước?

**Đáp án:** Listener container có thể đang sử dụng ConnectionFactory trỏ sang broker/vhost khác; tiếp theo kiểm tra queue name, quyền tài khoản, tình trạng kết nối và cơ chế listener autoDeclare.

## 13. Checklist khi thiết kế topology cho hệ thống thực tế

| Câu hỏi | Quyết định cần ghi rõ |
| --- | --- |
| Ai sở hữu queue, exchange và binding? | Ứng dụng hiện tại, ứng dụng khác hay nền tảng hạ tầng? |
| Broker/vhost nào lưu tài nguyên? | ConnectionFactory của admin tương ứng. |
| Có cho auto-declare hay không? | **shouldDeclare** ở từng Declarable; autoStartup ở RabbitAdmin. |
| Admin nào được quyền tự khai báo? | **setAdminsThatShouldDeclare** cho queue, exchange và binding. |
| Có chặn các khai báo không gán chủ? | **explicitDeclarationsOnly=true** ở các admin cần strict mode. |
| Listener có thể tạo lại queue bị thiếu không? | Kiểm tra **autoDeclare** của listener container và admin được chọn. |
| Nếu khai báo thất bại thì sao? | Xem xét hành vi fail, logs, **ignoreDeclarationExceptions** và giám sát. |
| Khi thay đổi topology có dữ liệu cũ? | Lập kế hoạch migration; auto-declare không tự sửa mọi thuộc tính queue/exchange. |

**Nguyên tắc vận hành:** mô tả topology rõ trong code; chỉ định **một bên chịu trách nhiệm** khai báo cho từng tài nguyên; chọn đúng admin/ConnectionFactory; kiểm tra các tài nguyên thực trên broker trước khi đánh giá luồng RabbitTemplate và @RabbitListener. Đây là nền tảng để triển khai các phần tiếp theo của **Spring AMQP**: routing, publisher confirm, consumer ack, retry, dead-letter, giao dịch và quan sát hệ thống một cách đáng tin cậy.

### Tài liệu tham khảo

- [Spring AMQP – Configuring the Broker (Automatic và Conditional Declaration)](https://docs.spring.io/spring-amqp/reference/amqp/broker-configuration.html)
- [Spring AMQP – Message Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html)
- [Spring Boot – Common Application Properties (spring.rabbitmq.dynamic)](https://docs.spring.io/spring-boot/appendix/application-properties/)
