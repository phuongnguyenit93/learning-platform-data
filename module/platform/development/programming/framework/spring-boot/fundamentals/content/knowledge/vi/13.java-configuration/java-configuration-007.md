# ImportBeanDefinitionRegistrar và đăng ký định nghĩa nâng cao

Trong Spring, phần lớn bean của ứng dụng được đăng ký bằng component scanning hoặc phương thức `@Bean`. Những cách này đủ cho hầu hết ứng dụng thông thường. Tuy nhiên, có những thư viện hoặc module cần tạo **nhiều bean theo metadata**, theo danh sách module được bật, theo annotation trên lớp cấu hình hoặc theo một tập implementation được phát hiện trước khi ApplicationContext khởi tạo các bean nghiệp vụ.

Ví dụ, một thư viện có thể cung cấp annotation `@EnableConnectors({"orders", "billing"})`. Khi người dùng đặt annotation đó trên lớp cấu hình, thư viện cần đăng ký một bean connector cho mỗi tên được khai báo. Viết một phương thức `@Bean` riêng cho từng connector sẽ không linh hoạt khi số lượng connector được quyết định bởi metadata.

Spring cung cấp **`ImportBeanDefinitionRegistrar`** cho tình huống nâng cao này. Registrar được kết nối với cấu hình thông qua `@Import`, nhận metadata của lớp cấu hình và `BeanDefinitionRegistry`, sau đó đăng ký các **bean definition** bằng code. Nó cho phép xây dựng cấu hình có tính mở rộng mà vẫn để Spring quản lý việc khởi tạo, dependency injection và vòng đời của bean.

## 1. Từ đăng ký bean thông thường đến đăng ký bằng metadata

Một bean trong Spring có thể được đăng ký theo nhiều cách:

- Component scanning phát hiện lớp có stereotype như `@Component`, `@Service`, `@Repository` hoặc `@Controller`.
- Một phương thức `@Bean` trong lớp `@Configuration` trả về instance mà container quản lý.
- `@Import` đưa cấu hình, selector hoặc registrar vào quá trình xử lý cấu hình.
- Các thành phần hạ tầng có thể đăng ký `BeanDefinition` trực tiếp thông qua `BeanDefinitionRegistry`.

Với ứng dụng nhỏ, ví dụ sau thường là đủ:

~~~java
@Configuration
public class BillingConfiguration {

    @Bean
    public BillingService billingService(
            InvoiceRepository repository
    ) {
        return new BillingService(repository);
    }
}
~~~

Spring biết rằng phương thức `billingService` cung cấp một bean. Khi tạo bean, container giải quyết tham số `InvoiceRepository` rồi gọi factory method theo cơ chế quản lý cấu hình.

Nhưng giả sử cần đăng ký một bean cho mỗi connector có tên trong annotation:

~~~java
@EnableConnectors({"orders", "billing", "inventory"})
@Configuration
public class IntegrationConfiguration {
}
~~~

Số lượng bean và tên bean được xác định từ metadata `@EnableConnectors`. Đây là trường hợp phù hợp để registrar tạo các bean definition theo chương trình.

### Phân biệt instance và bean definition

**Bean instance** là đối tượng Java thực tế được sử dụng lúc runtime. **Bean definition** là metadata mô tả cho container biết cách tạo và quản lý đối tượng đó.

Một bean definition có thể chứa thông tin như:

- Class hoặc factory method dùng để tạo bean.
- Constructor argument và property value.
- Scope, lazy initialization, primary/autowire candidate.
- Dependency cần thiết và quan hệ khởi tạo.
- Init method và destroy method.
- Role hoặc metadata bổ sung phục vụ container.

`ImportBeanDefinitionRegistrar` chủ yếu làm việc ở **giai đoạn đăng ký định nghĩa**, không phải tạo instance rồi tự quản lý đối tượng bằng tay. Đây là điểm quan trọng nhất cần nắm.

~~~text
Annotation / Java configuration
              |
              v
      @Import(Registrar.class)
              |
              v
ImportBeanDefinitionRegistrar
              |
              | đọc AnnotationMetadata
              | ghi BeanDefinitionRegistry
              v
       Bean definitions
              |
              v
       BeanFactory / Context
              |
              | resolve dependency
              | instantiate bean
              | apply lifecycle / proxy
              v
         Bean instances
~~~

## 2. ImportBeanDefinitionRegistrar là gì?

`ImportBeanDefinitionRegistrar` là một interface trong package:

~~~java
org.springframework.context.annotation.ImportBeanDefinitionRegistrar
~~~

Interface này cho phép một class tham gia quá trình xử lý `@Import` và đăng ký thêm bean definition vào registry.

Phương thức cốt lõi:

~~~java
void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry
);
~~~

Hai tham số có vai trò khác nhau:

| Tham số | Ý nghĩa |
|---|---|
| `AnnotationMetadata importingClassMetadata` | Metadata của class cấu hình đã import registrar, bao gồm thông tin annotation và thuộc tính annotation |
| `BeanDefinitionRegistry registry` | Registry dùng để đăng ký, kiểm tra và quản lý bean definitions |

Registrar thường không phải một bean nghiệp vụ được component scan như service. Nó được Spring tạo và gọi trong quá trình xử lý cấu hình khi lớp chứa `@Import` được xử lý.

### AnnotationMetadata cung cấp thông tin nào?

`AnnotationMetadata` cho phép đọc annotation trên lớp cấu hình mà không cần tạo instance của lớp đó. Ví dụ:

~~~java
Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableConnectors.class.getName()
        );
~~~

Map có thể chứa các thuộc tính như `value`, `basePackages`, `enabled` hoặc class được khai báo trong annotation. Từ dữ liệu đó, registrar quyết định bean definition nào cần đăng ký.

Đây là cơ chế quan trọng cho annotation kiểu “enable”: người dùng khai báo ý định ở lớp cấu hình; registrar đọc ý định và tạo các thành phần cần thiết.

### BeanDefinitionRegistry làm gì?

`BeanDefinitionRegistry` là abstraction cho phép đăng ký và tra cứu bean definition theo tên. Một số thao tác thường gặp:

~~~java
registry.containsBeanDefinition("ordersConnector");
registry.registerBeanDefinition("ordersConnector", beanDefinition);
registry.removeBeanDefinition("ordersConnector");
~~~

Trong registrar thông thường, ta chủ yếu dùng `containsBeanDefinition` và `registerBeanDefinition`. Không nên xóa hoặc thay thế bean definition khác nếu không có lý do rõ ràng và hiểu tác động đến cấu hình toàn ứng dụng.

## 3. Registrar được kích hoạt qua @Import

Cách dùng phổ biến là tạo một annotation cấu hình tổng hợp, sau đó dùng `@Import` để đưa registrar vào quá trình xử lý.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ConnectorRegistrar.class)
public @interface EnableConnectors {
    String[] value() default {};
}
~~~

Annotation `@EnableConnectors` cho phép người dùng bật module và cung cấp tên connector. Khi đặt annotation trên một lớp cấu hình:

~~~java
@Configuration
@EnableConnectors({"orders", "billing"})
public class IntegrationConfiguration {
}
~~~

Spring sẽ xử lý `@Import(ConnectorRegistrar.class)` và gọi registrar trong quá trình xử lý cấu hình. Registrar có thể đọc thuộc tính `value` từ `AnnotationMetadata` rồi đăng ký bean definition tương ứng.

Một lớp được import bằng `@Import` có thể là:

1. Một lớp cấu hình chứa bean definitions.
2. Một implementation của `ImportSelector` để chọn class cấu hình cần import.
3. Một implementation của `ImportBeanDefinitionRegistrar` để đăng ký bean definitions bằng code.

Ba cơ chế này có liên quan nhưng khác vai trò:

| Cơ chế | Mục đích |
|---|---|
| `@Import(SomeConfiguration.class)` | Đưa một lớp cấu hình vào context |
| `ImportSelector` | Chọn một hoặc nhiều class cấu hình để import |
| `ImportBeanDefinitionRegistrar` | Đăng ký bean definitions tùy chỉnh trực tiếp vào registry |

Nếu chỉ cần import một cấu hình cố định, `@Import` với class cấu hình là đơn giản nhất. Nếu cần chọn cấu hình dựa trên metadata, `ImportSelector` có thể phù hợp. Nếu cần tạo bean definitions theo dữ liệu, `ImportBeanDefinitionRegistrar` là công cụ chuyên biệt.

## 4. Ví dụ hoàn chỉnh: đăng ký connector từ annotation

Xây dựng một ví dụ Spring Boot có thể đăng ký một bean `NamedConnector` cho mỗi tên trong `@EnableConnectors`.

### 4.1. Định nghĩa đối tượng được đăng ký

~~~java
package com.example.integration;

public class NamedConnector {
    private final String connectorName;

    public NamedConnector(String connectorName) {
        this.connectorName = connectorName;
    }

    public String connectorName() {
        return connectorName;
    }

    public String send(String payload) {
        return "[" + connectorName + "] " + payload;
    }
}
~~~

`NamedConnector` là class Java bình thường. Nó không cần `@Component` vì registrar sẽ đăng ký bean definition trực tiếp cho class này.

### 4.2. Tạo annotation bật connector

~~~java
package com.example.integration;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ConnectorRegistrar.class)
public @interface EnableConnectors {
    String[] value() default {};
}
~~~

Các điểm đáng chú ý:

- `@Target(ElementType.TYPE)` cho phép đặt annotation trên class/interface.
- `@Retention(RetentionPolicy.RUNTIME)` giữ metadata ở runtime để Spring có thể đọc.
- `@Import` kết nối annotation với registrar.
- `value` là danh sách tên connector người dùng muốn đăng ký.

### 4.3. Cài đặt registrar

~~~java
package com.example.integration;

import java.util.Map;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionStoreException;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class ConnectorRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry
    ) {
        Map<String, Object> attributes =
                importingClassMetadata.getAnnotationAttributes(
                        EnableConnectors.class.getName()
                );

        if (attributes == null) {
            return;
        }

        String[] connectorNames = (String[]) attributes.get("value");

        for (String connectorName : connectorNames) {
            String beanName = connectorName + "Connector";

            if (registry.isBeanNameInUse(beanName)) {
                throw new BeanDefinitionStoreException(
                        "Bean name already in use: " + beanName
                );
            }

            var beanDefinition =
                    BeanDefinitionBuilder
                            .genericBeanDefinition(NamedConnector.class)
                            .addConstructorArgValue(connectorName)
                            .getBeanDefinition();

            registry.registerBeanDefinition(beanName, beanDefinition);
        }
    }
}
~~~

Giải thích:

1. `getAnnotationAttributes` đọc thuộc tính của annotation trên lớp cấu hình import registrar.
2. Nếu annotation không có trong metadata, registrar không có dữ liệu để xử lý và kết thúc.
3. Với mỗi connector name, code tạo một bean name ổn định.
4. `isBeanNameInUse` kiểm tra tên đã được dùng làm bean definition hoặc alias chưa.
5. `BeanDefinitionBuilder` tạo metadata cho `NamedConnector` và thêm constructor argument.
6. `registerBeanDefinition` đăng ký metadata vào registry.

Registrar không gọi `new NamedConnector(...)`. Nó mô tả cho Spring cách tạo bean; Spring sẽ tạo instance khi container cần khởi tạo bean theo scope và lifecycle.

### 4.4. Sử dụng annotation trong ứng dụng

~~~java
package com.example.integration;

import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConnectors({"orders", "billing", "inventory"})
public class IntegrationConfiguration {
}
~~~

Sau khi ApplicationContext được khởi tạo, các bean có thể được truy cập theo kiểu:

~~~java
NamedConnector orders =
        applicationContext.getBean(
                "ordersConnector",
                NamedConnector.class
        );

NamedConnector billing =
        applicationContext.getBean(
                "billingConnector",
                NamedConnector.class
        );
~~~

Kết quả:

~~~java
orders.send("Order created");
// [orders] Order created

billing.send("Invoice generated");
// [billing] Invoice generated
~~~

Đoạn lookup ở đây chỉ dùng để minh họa kiểm tra bean đã được đăng ký. Trong service nghiệp vụ, nếu cần dùng các connector, nên inject tập hợp bean hoặc một registry có kiểu thay vì gọi `ApplicationContext.getBean` rải rác.

### 4.5. Sử dụng nhiều bean cùng kiểu

Vì registrar tạo nhiều bean `NamedConnector`, inject một `NamedConnector` đơn lẻ mà không có quy tắc chọn sẽ gây ambiguity. Có thể inject danh sách:

~~~java
@Service
public class ConnectorDispatcher {
    private final Map<String, NamedConnector> connectors;

    public ConnectorDispatcher(
            Map<String, NamedConnector> connectors
    ) {
        this.connectors = Map.copyOf(connectors);
    }

    public String send(String connectorName, String payload) {
        NamedConnector connector =
                connectors.get(connectorName + "Connector");

        if (connector == null) {
            throw new IllegalArgumentException(
                    "Unknown connector: " + connectorName
            );
        }

        return connector.send(payload);
    }
}
~~~

Ở ví dụ này, Spring cung cấp các bean theo kiểu `NamedConnector` dưới dạng map có key là bean name. Dispatcher sử dụng một tập bean đã được container lắp ghép; nó không cần giữ ApplicationContext.

Trong ứng dụng thực tế, nên cân nhắc một interface như `Connector` và một resolver có kiểu miền thay vì ghép tên bean từ chuỗi tùy ý. Bean name là chi tiết cấu hình; tên connector trong nghiệp vụ nên có quy tắc chuyển đổi rõ ràng.

## 5. Tạo BeanDefinition bằng BeanDefinitionBuilder

`BeanDefinitionBuilder` giúp tạo metadata mà không phải thao tác trực tiếp với nhiều setter. Nó có thể cấu hình class, constructor argument, property, scope, lazy initialization và các thuộc tính khác.

Ví dụ:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addConstructorArgValue("csv")
                .setScope(BeanDefinition.SCOPE_SINGLETON)
                .setLazyInit(true)
                .getBeanDefinition();
~~~

Một số thao tác thường gặp:

| Phương thức | Tác dụng |
|---|---|
| `genericBeanDefinition(Class<?>)` | Bắt đầu tạo bean definition từ class |
| `addConstructorArgValue(value)` | Thêm constructor argument |
| `addPropertyValue(name, value)` | Thiết lập property value |
| `setScope(scope)` | Đặt bean scope |
| `setLazyInit(true)` | Đánh dấu khởi tạo lazy |
| `setPrimary(true)` | Ưu tiên bean trong một số tình huống autowiring |
| `setAutowireCandidate(false)` | Không xem bean là ứng viên autowiring thông thường |
| `getBeanDefinition()` | Lấy BeanDefinition đã xây dựng |

Tên và khả năng cụ thể của builder phụ thuộc phiên bản Spring Framework, nhưng các thao tác trên là những API phổ biến.

### Constructor argument và property value

Có thể cung cấp dependency hoặc giá trị cấu hình theo constructor:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addConstructorArgReference("reportRepository")
                .addConstructorArgValue("csv")
                .getBeanDefinition();
~~~

`addConstructorArgReference` tham chiếu một bean khác theo tên. Khi container tạo bean, nó giải quyết reference đó theo bean definition tương ứng.

Hoặc cấu hình property:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ReportExporter.class)
                .addPropertyValue("format", "csv")
                .getBeanDefinition();
~~~

Cách dùng property đòi hỏi class có setter/property phù hợp và việc khởi tạo cho phép Spring gán giá trị. Với class mới, constructor injection thường thể hiện dependency bắt buộc rõ hơn.

### Đăng ký trực tiếp bằng RootBeanDefinition

Không bắt buộc dùng builder. Có thể tạo `RootBeanDefinition`:

~~~java
RootBeanDefinition definition =
        new RootBeanDefinition(ReportExporter.class);

definition.getConstructorArgumentValues()
        .addIndexedArgumentValue(0, "csv");

definition.setLazyInit(true);
definition.setScope(BeanDefinition.SCOPE_SINGLETON);

registry.registerBeanDefinition("csvReportExporter", definition);
~~~

Cách này cho phép thao tác trực tiếp metadata. Builder thường gọn và dễ đọc hơn cho trường hợp đơn giản; RootBeanDefinition hữu ích khi cần cấu hình nhiều chi tiết.

## 6. BeanDefinition chứa những thông tin nâng cao nào?

Một bean definition không chỉ ghi tên class. Nó có thể mô tả cách Spring tạo, kết nối và quản lý bean.

### Scope

~~~java
definition.setScope(BeanDefinition.SCOPE_PROTOTYPE);
~~~

Bean definition có thể dùng scope singleton, prototype hoặc scope web đã được đăng ký. Scope phải phù hợp với context và vòng đời dữ liệu; registrar không tự tạo ra một web scope nếu ứng dụng không có hạ tầng tương ứng.

### Lazy initialization

~~~java
definition.setLazyInit(true);
~~~

Bean lazy có thể được tạo khi có yêu cầu thay vì khởi tạo eager cùng các singleton thông thường. Lazy initialization thay đổi thời điểm tạo instance; nó không làm dependency trở thành tùy chọn.

### Primary và autowire candidate

~~~java
definition.setPrimary(true);
definition.setAutowireCandidate(true);
~~~

`primary` đánh dấu bean ưu tiên khi có nhiều ứng viên cùng kiểu cho injection point. `autowireCandidate` quyết định bean có tham gia lựa chọn autowiring thông thường hay không. Hai thuộc tính này ảnh hưởng việc giải quyết dependency, nên cần được đặt có chủ đích.

### Init và destroy method

~~~java
definition.setInitMethodName("initialize");
definition.setDestroyMethodName("close");
~~~

Registrar có thể khai báo callback lifecycle cho bean definition. Các phương thức phải tồn tại và có signature phù hợp; lỗi cấu hình có thể chỉ xuất hiện khi container khởi tạo hoặc hủy bean.

### Depends-on

~~~java
definition.setDependsOn("sharedClient");
~~~

`dependsOn` thể hiện bean cần bean khác được khởi tạo trước; trong quá trình hủy, quan hệ phụ thuộc cũng có thể ảnh hưởng thứ tự cleanup. Tuy nhiên, nếu bean thực sự cần dùng một dependency để hoạt động, khai báo constructor/property reference thường thể hiện quan hệ rõ hơn `dependsOn`.

### Role và description

~~~java
definition.setRole(BeanDefinition.ROLE_INFRASTRUCTURE);
definition.setDescription("Infrastructure bean registered by connector registrar");
~~~

Role có thể mô tả bean thuộc ứng dụng, hỗ trợ hay hạ tầng. Đây là metadata giúp công cụ và người đọc hiểu vai trò bean; nó không thay thế cơ chế bảo mật hoặc kiểm soát quyền truy cập.

## 7. Đọc metadata của annotation để đăng ký có điều kiện

Registrar thường được dùng cùng annotation kiểu enable. Annotation có thể chứa thuộc tính quyết định có đăng ký bean hay không.

Ví dụ:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditRegistrar.class)
public @interface EnableAudit {
    boolean enabled() default true;
    String topic() default "audit-events";
}
~~~

Registrar đọc thuộc tính:

~~~java
public class AuditRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry
    ) {
        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        EnableAudit.class.getName()
                );

        if (attributes == null) {
            return;
        }

        boolean enabled = (boolean) attributes.get("enabled");
        if (!enabled) {
            return;
        }

        String topic = (String) attributes.get("topic");

        BeanDefinition definition =
                BeanDefinitionBuilder
                        .genericBeanDefinition(AuditPublisher.class)
                        .addConstructorArgValue(topic)
                        .getBeanDefinition();

        registry.registerBeanDefinition("auditPublisher", definition);
    }
}
~~~

Nếu `enabled` là false, registrar không đăng ký `AuditPublisher`. Nếu true, nó tạo bean definition với constructor argument lấy từ metadata.

Tuy nhiên, nếu yêu cầu chỉ đơn giản là bật/tắt bean theo property môi trường như `app.audit.enabled`, `@ConditionalOnProperty` trên một cấu hình hoặc bean có thể rõ ràng hơn. Registrar phù hợp khi quyết định đăng ký phụ thuộc vào metadata của annotation hoặc cần sinh nhiều definition có cấu trúc.

### Annotation có class attribute

Annotation có thể nhận class làm thuộc tính:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AdapterRegistrar.class)
public @interface EnableAdapter {
    Class<?> implementation();
}
~~~

Registrar có thể đọc class attribute từ metadata và sử dụng nó làm bean class nếu class hợp lệ:

~~~java
Map<String, Object> attributes =
        metadata.getAnnotationAttributes(
                EnableAdapter.class.getName()
        );

Class<?> implementation =
        (Class<?>) attributes.get("implementation");

BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(implementation)
                .getBeanDefinition();
~~~

Trong một số ngữ cảnh xử lý metadata, class attribute có thể được yêu cầu dưới dạng tên class để tránh resolve sớm. Nếu dùng chế độ trả class value dưới dạng chuỗi, cần xử lý và tải class bằng classloader phù hợp. Không nên cast tùy tiện khi chưa biết kiểu giá trị được trả về.

Ngoài ra, cần kiểm tra class có implement interface mong đợi, có thể khởi tạo và có constructor phù hợp. Annotation cho phép người dùng chỉ định class không có nghĩa mọi class đều là implementation hợp lệ.

## 8. Đăng ký bean theo danh sách class hoặc module

Một trường hợp nâng cao là người dùng truyền danh sách implementation trong annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(HandlerRegistrar.class)
public @interface EnableHandlers {
    Class<? extends EventHandler>[] value();
}
~~~

Người dùng khai báo:

~~~java
@Configuration
@EnableHandlers({
        OrderCreatedHandler.class,
        InvoicePaidHandler.class
})
public class EventConfiguration {
}
~~~

Registrar có thể lấy mảng class và tạo bean definition cho từng loại. Trong thực tế, cần chọn bean name ổn định, xử lý tên trùng và kiểm tra kiểu. Ví dụ khái niệm:

~~~java
for (Class<?> handlerClass : handlerClasses) {
    if (!EventHandler.class.isAssignableFrom(handlerClass)) {
        throw new IllegalArgumentException(
                "Handler must implement EventHandler"
        );
    }

    BeanDefinition definition =
            BeanDefinitionBuilder
                    .genericBeanDefinition(handlerClass)
                    .getBeanDefinition();

    registry.registerBeanDefinition(
            generateBeanName(handlerClass),
            definition
    );
}
~~~

`generateBeanName` là hàm do registrar định nghĩa. Tên bean cần xác định theo quy tắc ổn định và tránh xung đột với bean hiện có. Nếu nhiều module đăng ký cùng một class hoặc cùng logical name, cần quyết định rõ nên từ chối, bỏ qua hay cho phép alias.

Nếu annotation đã khai báo class cụ thể, thường không cần scan toàn classpath để tìm lại implementation. Dùng metadata được cung cấp giúp hành vi rõ ràng và có thể dự đoán.

## 9. Bean name: đặt tên ổn định và xử lý xung đột

Bean name là khóa để registry phân biệt bean definition. Khi registrar tạo nhiều bean, tên nên:

- Ổn định giữa các lần khởi động.
- Có namespace/prefix phản ánh module hoặc chức năng.
- Không phụ thuộc vào thứ tự duyệt collection.
- Không vô tình trùng tên bean do component scan hoặc cấu hình khác đăng ký.
- Có thể được dùng nhất quán trong log và chẩn đoán.

Ví dụ, thay vì tên chung `client`, có thể dùng `ordersConnector` hoặc `billingConnector`.

### Kiểm tra trước khi đăng ký

~~~java
if (registry.isBeanNameInUse(beanName)) {
    throw new BeanDefinitionStoreException(
            "Bean name already in use: " + beanName
    );
}

registry.registerBeanDefinition(beanName, definition);
~~~

`isBeanNameInUse` kiểm tra tên có đang được sử dụng trong registry, bao gồm cả alias theo contract registry. Nếu phát hiện trùng, registrar nên có chính sách rõ ràng.

Không nên mặc định ghi đè bean definition của module khác. Cấu hình override có thể bị tắt hoặc bật tùy ứng dụng và phiên bản; phụ thuộc vào hành vi ghi đè khiến thứ tự import khó dự đoán.

### Dùng BeanNameGenerator khi cần quy tắc chung

Spring có `BeanNameGenerator` để sinh bean name theo một quy ước. Registrar có thể tự xây dựng tên theo module hoặc tận dụng bean name generator được cung cấp qua overload tương ứng ở những phiên bản Spring hỗ trợ.

Khi triển khai registrar cần tương thích nhiều phiên bản Spring, hãy kiểm tra API chính xác của phiên bản mục tiêu. Overload của `registerBeanDefinitions` có tham số `BeanNameGenerator` được bổ sung trong các phiên bản Spring Framework mới hơn; không nên gọi API mới nếu thư viện cần chạy trên nền Spring cũ.

## 10. Registrar có thể sử dụng Environment và ResourceLoader

Một registrar có thể cần đọc cấu hình môi trường hoặc truy cập tài nguyên. `ImportBeanDefinitionRegistrar` hỗ trợ tích hợp với các callback aware mà Spring cung cấp trong quá trình xử lý cấu hình, chẳng hạn `EnvironmentAware`, `ResourceLoaderAware` và `BeanClassLoaderAware`. Cần kiểm tra contract của phiên bản Spring đang dùng nếu triển khai thêm callback cụ thể.

Ví dụ đọc property qua `EnvironmentAware`:

~~~java
public class FeatureRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry
    ) {
        boolean enabled = environment.getProperty(
                "app.feature.enabled",
                Boolean.class,
                false
        );

        if (!enabled) {
            return;
        }

        // Đăng ký bean definition khi feature được bật.
    }
}
~~~

Đây là một lựa chọn khi registrar thực sự cần đọc environment. Tuy nhiên, nếu mục tiêu là bật/tắt một cấu hình đơn giản theo property, Spring Boot cung cấp `@ConditionalOnProperty` thường ngắn gọn hơn.

Tương tự, nếu cần kiểm tra classpath hoặc tài nguyên, hãy dùng abstraction phù hợp và tránh tự thực hiện logic nạp class phức tạp khi Spring đã có cơ chế condition/metadata hỗ trợ.

## 11. Registrar chạy ở giai đoạn nào?

Registrar tham gia trong quá trình xử lý configuration class và `@Import`, trước khi các bean nghiệp vụ thông thường được khởi tạo hoàn chỉnh. Nó có thể bổ sung bean definitions để container sử dụng trong các bước tiếp theo.

Một cách hình dung:

~~~text
Đọc configuration classes
          |
          v
Phân tích @Import
          |
          v
Gọi ImportBeanDefinitionRegistrar
          |
          v
Đăng ký BeanDefinition bổ sung
          |
          v
Hoàn tất đăng ký cấu hình
          |
          v
Tạo bean, resolve dependency,
apply BeanPostProcessor và lifecycle
~~~

Điều này giải thích vì sao registrar nhận `BeanDefinitionRegistry` thay vì cần một instance của bean nghiệp vụ. Nó làm việc khi container còn đang xây dựng mô hình bean.

### Không nên khởi tạo bean nghiệp vụ trực tiếp trong registrar

Cách không nên dùng:

~~~java
registry.registerSingleton(
        "ordersConnector",
        new NamedConnector("orders")
);
~~~

Đoạn này đăng ký một singleton instance đã được tạo sẵn vào registry/factory theo cơ chế singleton registration, không tương đương với việc đăng ký một bean definition đầy đủ. Nó có thể bỏ qua một số bước quản lý bean thông thường như constructor resolution, bean post-processing hoặc lifecycle metadata theo cách mà một bean definition cung cấp.

Thông thường, nên đăng ký:

~~~java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(NamedConnector.class)
                .addConstructorArgValue("orders")
                .getBeanDefinition();

registry.registerBeanDefinition("ordersConnector", definition);
~~~

Container sẽ chịu trách nhiệm tạo instance và áp dụng cơ chế quản lý phù hợp.

## 12. Phân biệt ImportBeanDefinitionRegistrar với BeanDefinitionRegistryPostProcessor

Cả hai đều có thể đăng ký bean definitions, nhưng chúng tham gia ở những điểm khác nhau trong quá trình cấu hình.

`BeanDefinitionRegistryPostProcessor` là một loại `BeanFactoryPostProcessor` có callback làm việc trực tiếp với registry sau khi các bean definitions ban đầu đã được tải, trước khi các bean thông thường được khởi tạo. Nó phù hợp với tác vụ post-process registry ở cấp context.

| Tiêu chí | ImportBeanDefinitionRegistrar | BeanDefinitionRegistryPostProcessor |
|---|---|---|
| Được kích hoạt từ đâu? | Thông qua `@Import` | Đăng ký như một bean post-processor |
| Phạm vi ý định | Gắn với một cấu hình/annotation cụ thể | Xử lý registry của context |
| Metadata đầu vào | Có `AnnotationMetadata` của class import | Có `BeanDefinitionRegistry`; không nhận cùng tham số importing metadata |
| Công dụng điển hình | Annotation kiểu enable tạo bean definitions | Bổ sung/chỉnh registry sau giai đoạn đăng ký ban đầu |
| Vị trí phù hợp | Thư viện cấu hình, module tự bật | Hạ tầng cần xử lý registry ở mức toàn context |

Ví dụ interface post-processor:

~~~java
public interface BeanDefinitionRegistryPostProcessor
        extends BeanFactoryPostProcessor {

    void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry
    ) throws BeansException;
}
~~~

Không nên chọn post-processor chỉ vì nó có tên “registry”. Nếu người dùng bật một tính năng bằng annotation và registrar cần đọc thuộc tính annotation đó, `ImportBeanDefinitionRegistrar` biểu đạt ý định trực tiếp hơn.

### Phân biệt với BeanFactoryPostProcessor

`BeanFactoryPostProcessor` chủ yếu cho phép sửa metadata của bean factory sau khi bean definitions được nạp. `BeanDefinitionRegistryPostProcessor` mở rộng cơ chế này bằng callback sớm hơn để đăng ký thêm bean definitions.

Cả hai đều là infrastructure extension point. Không nên dùng chúng cho logic nghiệp vụ chạy theo request.

## 13. Phân biệt với FactoryBean

Tên `FactoryBean` dễ bị nhầm với registrar, nhưng hai cơ chế giải quyết hai việc khác nhau.

- `ImportBeanDefinitionRegistrar` đăng ký **metadata định nghĩa bean** vào registry.
- `FactoryBean<T>` là một bean đặc biệt mà khi được yêu cầu, Spring lấy object do factory tạo ra làm sản phẩm bean.

Ví dụ khái niệm:

~~~java
public class ClientFactoryBean implements FactoryBean<RemoteClient> {

    @Override
    public RemoteClient getObject() {
        return new RemoteClient();
    }

    @Override
    public Class<?> getObjectType() {
        return RemoteClient.class;
    }
}
~~~

Một `FactoryBean` có thể được đăng ký thông qua bean definition. Khi đó container quản lý factory và cung cấp sản phẩm theo contract của nó. Registrar có thể tạo bean definition cho factory bean hoặc các thành phần khác, nhưng không thay thế vai trò tạo product của `FactoryBean`.

Hãy nhớ:

~~~text
Registrar
   |
   +--> đăng ký BeanDefinition
                  |
                  v
             Spring container
                  |
                  v
          tạo bean / FactoryBean
                  |
                  v
             bean instance
~~~

Dùng registrar khi cần tạo định nghĩa theo metadata; dùng FactoryBean khi cần một factory abstraction chuyên tạo object sản phẩm.

## 14. Khi nào nên dùng ImportBeanDefinitionRegistrar?

Registrar hữu ích khi có một yêu cầu cấu hình mang tính hạ tầng hoặc framework extension, chẳng hạn:

- Annotation `@Enable...` cần đăng ký một nhóm bean theo thuộc tính người dùng khai báo.
- Một thư viện cần tạo bean definition cho mỗi interface được chỉ định.
- Module tích hợp cần đăng ký adapter, proxy hoặc client theo metadata cấu hình.
- Một hệ thống plugin cần đăng ký tập implementation với tên và dependency được xác định trước.
- Một framework nội bộ muốn đóng gói nhiều bean definitions sau một annotation duy nhất.

Ví dụ thư viện có thể cung cấp:

~~~java
@EnableRemoteClients(
        basePackages = "com.example.store.remote"
)
~~~

Registrar có thể dùng package metadata để tìm các interface client và đăng ký proxy/client bean tương ứng. Đây là kiểu chức năng mà các thư viện tích hợp thường cần: người dùng khai báo một annotation; thư viện thực hiện phần đăng ký nâng cao.

Tuy nhiên, registrar là extension point cấp thấp hơn component scan hoặc `@Bean`. Chỉ nên dùng khi cần kiểm soát bean definition theo chương trình. Nếu một bean cố định có thể được mô tả bằng phương thức `@Bean`, hãy dùng cách đơn giản đó.

## 15. Tình huống nâng cao: đăng ký client cho các interface được chỉ định

Một thư viện có thể muốn hỗ trợ annotation:

~~~java
@EnableRemoteClients({
        CustomerClient.class,
        InventoryClient.class
})
@Configuration
public class RemoteClientConfiguration {
}
~~~

Mỗi interface client cần được đăng ký thành một bean proxy. Registrar có thể đọc danh sách class từ metadata, tạo bean definition cho factory/proxy class với constructor argument là interface được chỉ định.

Ý tưởng tổng quát:

~~~java
for (Class<?> clientInterface : clientInterfaces) {
    validateClientInterface(clientInterface);

    BeanDefinition definition =
            BeanDefinitionBuilder
                    .genericBeanDefinition(RemoteClientFactoryBean.class)
                    .addConstructorArgValue(clientInterface)
                    .getBeanDefinition();

    registry.registerBeanDefinition(
            beanNameFor(clientInterface),
            definition
    );
}
~~~

`RemoteClientFactoryBean` ở đây là thành phần hạ tầng do thư viện định nghĩa. Nó có thể tạo proxy thực hiện HTTP request khi phương thức interface được gọi. Registrar chỉ đăng ký factory bean definition; logic proxy và network nằm trong factory hoặc adapter.

Cần lưu ý:

- Chỉ nhận interface hợp lệ, không phải class tùy ý.
- Xác định bean name không xung đột.
- Xử lý annotation cấu hình endpoint, timeout hoặc codec.
- Không thực hiện network request trong lúc registrar chạy.
- Để việc tạo connection/client diễn ra ở thời điểm phù hợp với lifecycle.
- Có cách xử lý lỗi cấu hình sớm và thông báo rõ ràng.

Đây là ví dụ về giá trị của registrar: một annotation có thể sinh nhiều bean definition dựa trên metadata thay vì bắt người dùng khai báo từng factory method.

## 16. Kiểm soát trùng lặp và tính idempotent

Registrar có thể được tham gia vào quá trình xử lý cấu hình phức tạp, ví dụ nhiều annotation hoặc module cùng import một registrar. Vì vậy, cần suy nghĩ về tính trùng lặp:

- Registrar có thể được gọi với cùng metadata nhiều lần không?
- Hai cấu hình có thể yêu cầu cùng một bean name không?
- Một bean definition đã được đăng ký bởi cấu hình khác chưa?
- Có nên bỏ qua, báo lỗi hay thay thế khi trùng?

Một chính sách rõ ràng thường tốt hơn để registry tự xử lý việc ghi đè. Ví dụ, nếu bean name phải duy nhất:

~~~java
if (registry.isBeanNameInUse(beanName)) {
    throw new BeanDefinitionStoreException(
            "Duplicate connector name: " + beanName
    );
}
registry.registerBeanDefinition(beanName, definition);
~~~

Nếu cùng một registrar có thể được gọi lặp với cùng cấu hình và muốn idempotent, có thể kiểm tra bean definition hiện có, xác minh nó có đúng class/metadata mong muốn rồi bỏ qua. Không nên chỉ kiểm tra tên và âm thầm bỏ qua mọi trường hợp, vì tên có thể đã được một cấu hình khác sử dụng cho bean không liên quan.

## 17. Điều kiện, profile và registrar

Registrar có thể đọc annotation metadata để quyết định đăng ký, nhưng không nên tự xây dựng lại mọi cơ chế điều kiện của Spring Boot.

Nếu yêu cầu đơn giản là bật bean theo property:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditConfiguration {

    @Bean
    public AuditPublisher auditPublisher() {
        return new AuditPublisher();
    }
}
~~~

Cách này thường dễ đọc hơn registrar tự đọc property và đăng ký definition.

Nếu yêu cầu là chọn bean theo profile:

~~~java
@Bean
@Profile("prod")
public PaymentGateway livePaymentGateway() {
    return new LivePaymentGateway();
}
~~~

`@Profile` thể hiện rõ bean chỉ được cung cấp trong profile tương ứng.

Registrar nên được chọn khi logic đăng ký cần metadata/định nghĩa động, ví dụ tạo N bean theo danh sách trong annotation, đăng ký proxy cho nhiều interface hoặc kết nối module theo một annotation enable. **Đừng dùng registrar để làm phức tạp một cấu hình có thể viết bằng `@Bean` hoặc condition tiêu chuẩn.**

## 18. Kiểm thử registrar

Registrar là code hạ tầng, vì vậy nên kiểm tra hai khía cạnh:

1. Bean definitions có được đăng ký đúng từ metadata hay không?
2. ApplicationContext có thể tạo và cung cấp bean theo định nghĩa đó hay không?

Một cách kiểm tra đơn giản là tạo context nhỏ với cấu hình sử dụng annotation enable:

~~~java
@Configuration
@EnableConnectors({"orders", "billing"})
static class TestConfiguration {
}
~~~

~~~java
@Test
void registersConnectorBeans() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                         TestConfiguration.class
                 )) {

        NamedConnector orders =
                context.getBean(
                        "ordersConnector",
                        NamedConnector.class
                );

        NamedConnector billing =
                context.getBean(
                        "billingConnector",
                        NamedConnector.class
                );

        assertEquals("orders", orders.connectorName());
        assertEquals("billing", billing.connectorName());
    }
}
~~~

Đoạn test giả định các class `EnableConnectors`, `ConnectorRegistrar` và `NamedConnector` đã được định nghĩa như ví dụ trước, cùng các import JUnit/Spring phù hợp.

### Kiểm thử trường hợp rỗng

Nếu annotation không cung cấp connector:

~~~java
@EnableConnectors
@Configuration
static class EmptyConfiguration {
}
~~~

Test nên xác nhận registrar không đăng ký bean connector ngoài dự kiến. Điều này kiểm tra giá trị mặc định của annotation và nhánh xử lý danh sách rỗng.

### Kiểm thử tên bị trùng

Có thể tạo một bean có tên `ordersConnector` bằng cấu hình khác rồi bật registrar yêu cầu tên tương tự. Kết quả nên là lỗi cấu hình có thông báo dễ hiểu, nếu chính sách của registrar là từ chối trùng.

### Kiểm thử dependency và lifecycle

Đăng ký thành công definition chưa chứng minh instance có thể khởi tạo. Hãy để context tạo bean, xác nhận constructor argument, dependency và lifecycle metadata được áp dụng đúng. Nếu bean có init/destroy method, test cần đóng context và xác nhận cleanup được gọi theo scope phù hợp.

## 19. Lỗi thường gặp khi dùng registrar

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Registrar không chạy | Class registrar chưa được đưa vào qua `@Import` hoặc cấu hình chứa annotation không được xử lý | Kiểm tra cấu hình được đăng ký và annotation enable |
| Không đọc được annotation attributes | Đọc sai annotation type/name hoặc annotation không có trên importing class metadata | Dùng đúng fully qualified annotation name và kiểm tra null |
| Bean definition đăng ký nhưng khởi tạo lỗi | Constructor argument sai, thiếu dependency hoặc class không hợp lệ | Xem `BeanCreationException` và metadata definition |
| `NoUniqueBeanDefinitionException` | Registrar đăng ký nhiều bean cùng kiểu, consumer inject một bean đơn | Dùng qualifier, primary, collection hoặc resolver |
| Bean name conflict | Nhiều cấu hình tạo cùng tên | Đặt namespace, kiểm tra registry và có chính sách trùng |
| Bean bị đăng ký hai lần | Registrar được import qua nhiều cấu hình hoặc còn một nguồn đăng ký khác | Kiểm tra toàn bộ nguồn đăng ký, không chỉ một lần import |
| Bean không nhận được post-processing dự kiến | Đăng ký instance thủ công thay vì definition hoặc sai lifecycle path | Đăng ký BeanDefinition để container quản lý |
| Tài nguyên không được đóng | Thiếu destroy metadata hoặc scope không được container quản lý cleanup | Cấu hình destroy method và xác định quyền sở hữu resource |

### Không nhầm registrar với component scan

Một class registrar không cần được đánh dấu `@Component` để hoạt động nếu nó đã được chỉ định qua `@Import`. Ngược lại, đặt `@Component` lên registrar nhưng không có cơ chế xử lý nó như registrar sẽ không tự động khiến Spring gọi `registerBeanDefinitions`. Nó là một extension point của configuration import.

### Không đăng ký bean definition sau khi context đã khởi tạo tùy tiện

`BeanDefinitionRegistry` được dùng trong giai đoạn đăng ký cấu hình. Việc sửa registry sau khi ứng dụng đã chạy có thể không tương thích với những bean đã được khởi tạo, dependency đã resolve, proxy đã tạo và các cache nội bộ. Nếu cần tạo đối tượng động lúc runtime, dùng factory/registry nghiệp vụ hoặc một cơ chế quản lý plugin có lifecycle rõ ràng thay vì thay đổi bean definitions tùy tiện.

## 20. Quy trình thiết kế một registrar an toàn

Khi cần xây dựng registrar trong thư viện hoặc ứng dụng:

1. **Xác định lý do cần registrar.** Có thật sự cần sinh nhiều bean definition từ metadata không, hay `@Bean`/`@Import` đơn giản đã đủ?
2. **Thiết kế annotation enable.** Thuộc tính nên ngắn, có default rõ ràng và mô tả đúng ý định người dùng.
3. **Xác định nguồn metadata.** Đọc từ `AnnotationMetadata` của lớp import; không khởi tạo lớp cấu hình chỉ để đọc annotation.
4. **Xác thực input.** Kiểm tra tên, class, interface, package hoặc thuộc tính cấu hình trước khi đăng ký.
5. **Đặt bean name ổn định.** Có namespace và chính sách xử lý trùng.
6. **Tạo BeanDefinition.** Cấu hình class, constructor argument, scope, lazy, primary và lifecycle khi cần.
7. **Đăng ký qua registry.** Không tạo instance thủ công nếu muốn Spring quản lý đầy đủ vòng đời.
8. **Để container giải quyết dependency.** Đừng tự gọi ApplicationContext hoặc tạo toàn bộ đồ thị bằng `new` bên trong registrar.
9. **Kiểm thử cả metadata lẫn instance.** Xác nhận definition được đăng ký và bean có thể được khởi tạo.
10. **Giữ logic ở mức hạ tầng.** Registrar không nên chứa quy tắc nghiệp vụ của request hoặc gọi dịch vụ ngoài khi khởi động.

## Kết luận

`ImportBeanDefinitionRegistrar` là extension point cho phép một thư viện hoặc module tham gia vào quá trình xử lý `@Import` và đăng ký bean definitions theo metadata. Nó đặc biệt hữu ích với annotation kiểu enable, module plugin, client proxy hoặc trường hợp cần sinh nhiều bean theo danh sách class/tên do người dùng khai báo.

Registrar làm việc với `AnnotationMetadata` và `BeanDefinitionRegistry`. Nó mô tả cho Spring cách tạo bean thay vì tự tạo instance rồi đưa vào container. Khi chọn công cụ, hãy phân biệt rõ: `@Bean` phù hợp với factory method tường minh; `ImportSelector` chọn cấu hình cần import; `ImportBeanDefinitionRegistrar` đăng ký định nghĩa động; `BeanDefinitionRegistryPostProcessor` xử lý registry ở cấp context; `FactoryBean` tạo sản phẩm bean.

Sử dụng registrar khi bài toán thực sự cần đăng ký nâng cao. Giữ bean name ổn định, kiểm tra xung đột, để container quản lý lifecycle và kiểm thử cả definition lẫn instance. Như vậy, cấu hình Spring Boot có thể mở rộng linh hoạt mà vẫn giữ object graph dễ hiểu và có thể kiểm soát.
