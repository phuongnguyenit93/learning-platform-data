# BeanDefinitionRegistryPostProcessor để bổ sung định nghĩa bean trong Spring Framework

## 1. Vì sao cần bổ sung bean definition bằng code?

Spring Core Container thường nhận bean definition từ `@Component`, `@Configuration`/`@Bean`, XML hoặc cơ chế import cấu hình. Với phần lớn ứng dụng, những cơ chế khai báo này đã đủ. Tuy nhiên, các thư viện tích hợp và bộ khung mở rộng đôi khi cần **đăng ký thêm nhiều bean definitions dựa trên metadata** trong lúc Spring đang chuẩn bị container.

Ví dụ, một module có danh sách connector types: `email`, `sms`, `webhook`. Mỗi type cần một bean `ChannelHandler` riêng với constructor argument, bean name, scope và autowiring metadata. Viết hàng chục `@Bean` methods gần giống nhau có thể gây lặp, trong khi tạo object bằng `new` rồi đặt vào một danh sách thường bỏ qua vòng đời đầy đủ của bean do Spring quản lý.

Spring cung cấp extension point:

**`org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor`**

Interface này được dùng để **thêm hoặc điều chỉnh BeanDefinition trong registry sau khi cấu hình chuẩn được nạp, trước giai đoạn BeanFactoryPostProcessor thông thường và trước khi phần lớn application beans được khởi tạo**.

Một điểm cốt lõi:

> **BeanDefinitionRegistryPostProcessor làm việc với *bản mô tả bean*, không phải tạo, chỉnh sửa hoặc gọi method nghiệp vụ trên bean instance.**

Bạn sẽ học:

1. Phân biệt `BeanDefinition`, `BeanDefinitionRegistry`, `BeanFactory` và object instance.
2. Hiểu hai callback `postProcessBeanDefinitionRegistry(...)` và `postProcessBeanFactory(...)`.
3. Đăng ký bean definition động với `BeanDefinitionBuilder` hoặc `RootBeanDefinition`.
4. Chọn cách đăng ký processor qua `@Bean static` hoặc programmatic API.
5. Hiểu thứ tự xử lý post-processors, cấu hình `PriorityOrdered`/`Ordered` và quan hệ với `ConfigurationClassPostProcessor`.
6. Chạy ví dụ Maven + Java 17 + Spring Framework 6.1, quan sát bean definitions mới tạo ra singleton và prototype.
7. Tránh các lỗi trùng tên, gọi `getBean()` quá sớm, cấu hình thiếu metadata, processor chạy sai phase và dynamic registration sau `refresh()`.

## 2. Định nghĩa bean khác với instance bean

**BeanDefinition** là metadata Spring dùng để biết cách tạo và quản lý bean; nó thường mô tả:

- Bean class hoặc factory method.
- Constructor arguments và property values.
- Scope: `singleton`, `prototype` hoặc custom scope phù hợp.
- `lazyInit`, `dependsOn`, `primary`, autowire candidate.
- Các callback initialization/destruction được cấu hình.
- Role, source metadata và những thuộc tính khác.

Một bean definition **không đồng nghĩa** với một Java object đã được khởi tạo.

Ví dụ:

~~~text
BeanDefinition:
  beanName = "emailHandler"
  beanClass = ChannelHandler
  constructorArg[0] = "email"
  scope = singleton
         |
         | Spring instantiate khi cần
         v
ChannelHandler("email") // Java object instance
~~~

Nếu scope là `prototype`, cùng một definition có thể được dùng để tạo nhiều object instances khác nhau. Nếu scope là singleton, một definition trong một BeanFactory thường ứng với một shared bean instance.

### Ba lớp trách nhiệm

| Thành phần | Công việc | Ví dụ API |
| --- | --- | --- |
| `BeanDefinitionRegistry` | Lưu trữ, thêm/xóa/tra cứu **định nghĩa** theo bean name | `registerBeanDefinition(name, definition)` |
| `ConfigurableListableBeanFactory` | Quản lý metadata, truy xuất thông tin toàn factory, phục vụ post-processing | `getBeanDefinition(name)`, `getBeanDefinitionNames()` |
| `BeanFactory`/`ApplicationContext` | Tạo và cung cấp **bean instance** cho ứng dụng | `getBean(name)`, `getBean(Class)` |

Trong `postProcessBeanDefinitionRegistry`, hãy làm việc với registry và bean definition thay vì vội lấy object từ container.

## 3. Hợp đồng `BeanDefinitionRegistryPostProcessor`

Interface thuộc package `org.springframework.beans.factory.support` và **extends `BeanFactoryPostProcessor`**.

Các method chính:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;

public final class DynamicRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {
        // Thêm/sửa bean definitions qua registry.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        // Kiểm tra/chỉnh metadata trên BeanFactory nếu cần.
    }
}
~~~

Đây là một class mẫu **biên dịch được với Spring Beans/Context trên classpath**; nó chưa làm gì cho đến khi được Spring đăng ký hoặc một đoạn mã tự gọi phù hợp. Trong Spring Framework 6.1, việc triển khai cả hai method là cách tương thích rõ ràng vì interface mở rộng `BeanFactoryPostProcessor`.

### Callback thứ nhất: registry phase

`postProcessBeanDefinitionRegistry(BeanDefinitionRegistry registry)` được gọi sau khi những definitions thông thường đã được nạp vào registry, nhưng **trước khi Spring hoàn tất giai đoạn nhận diện các BeanFactoryPostProcessor thông thường**. Nó có thể đăng ký thêm các definitions mà về sau Spring tiếp tục nhận diện và xử lý.

Một số use cases đúng:

- Đăng ký nhiều bean definitions dựa trên file cấu hình đã có sẵn.
- Bổ sung adapters theo plugin metadata.
- Định nghĩa nhiều implementation cùng class với constructor arguments khác nhau.
- Gắn scope, dependency, qualifier và property values cho definitions được tạo động.
- Thêm definition của một `BeanFactoryPostProcessor` khác khi thật sự cần extension pipeline.

### Callback thứ hai: factory phase

Vì interface extends `BeanFactoryPostProcessor`, bạn còn có:

`postProcessBeanFactory(ConfigurableListableBeanFactory beanFactory)`.

Ở bước này, registry processing đã xảy ra và BeanFactory có thể được dùng để xem/sửa metadata còn lại. Tuy nhiên, đây **vẫn là giai đoạn xử lý definitions**, không phải nơi tự tiện tạo các service instances.

**Quan trọng:** Đừng dùng callback thứ hai như một lệnh “chạy tất cả services sau khi context khởi động”. Nếu cần chạy logic nghiệp vụ khi ứng dụng ready, hãy sử dụng lifecycle/startup extension point phù hợp.

## 4. So sánh ba extension point thường bị nhầm

| Extension point | Nó xử lý gì? | Khi nào? | Dùng khi |
| --- | --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Registry và các definitions; có thể **thêm định nghĩa mới** | Rất sớm trong refresh, trước ordinary bean instantiation | Plugin infrastructure cần dynamic definitions |
| `BeanFactoryPostProcessor` | Metadata của các bean definitions đã tồn tại | Trước tạo các application beans thông thường | Chỉnh property values, cấu hình hoặc metadata |
| `BeanPostProcessor` | Bean **instance** trước/sau initialization | Khi từng bean được tạo | Inject thêm capability, validate instance, wrap proxy hoặc intercept lifecycle |

Hình dung:

~~~text
Scan @Component / parse @Configuration / đọc XML
                     |
                     v
        BeanDefinitionRegistry
                     |
                     v
BeanDefinitionRegistryPostProcessor
  + register bean definitions mới
  + điều chỉnh definitions đã có
                     |
                     v
          BeanFactoryPostProcessor
  + xử lý metadata / placeholders
                     |
                     v
      Spring tạo application bean instances
                     |
                     v
        BeanPostProcessor
  + beforeInitialization(instance, name)
  + afterInitialization(instance, name)
                     |
                     v
             Bean sẵn sàng
~~~

Đây là sơ đồ đơn giản hóa; Spring có các vòng phát hiện/invoke processors để xử lý definitions và processors mới đăng ký, cùng thứ tự `PriorityOrdered`/`Ordered`. Nhưng ranh giới **metadata vs instance** luôn là kiến thức quan trọng.

### Tình huống A: cần tạo một bean mới từ metadata

Chọn `BeanDefinitionRegistryPostProcessor` để gọi `registry.registerBeanDefinition(...)`.

### Tình huống B: cần đổi URL property của definition đã có

`BeanFactoryPostProcessor` thường đủ; có thể lấy definition và sửa `MutablePropertyValues` khi chưa tạo bean.

### Tình huống C: muốn bọc mỗi bean được tạo bằng proxy

`BeanPostProcessor` (hoặc hạ tầng AOP tương ứng) đúng hơn, bởi bạn xử lý bean **instance**.

Không dùng `BeanDefinitionRegistryPostProcessor` để thao tác state runtime như start/stop worker hoặc gọi HTTP API khi startup.

## 5. API `BeanDefinitionRegistry` cần biết

Những method thực tế quan trọng:

~~~java
registry.registerBeanDefinition("emailHandler", beanDefinition);

boolean present = registry.containsBeanDefinition("emailHandler");

BeanDefinition existing = registry.getBeanDefinition("emailHandler");

registry.removeBeanDefinition("obsoleteHandler");

String[] names = registry.getBeanDefinitionNames();
~~~

Đây là các câu lệnh minh họa bên trong callback có biến `registry` kiểu `BeanDefinitionRegistry` và biến `beanDefinition` được tạo trước. Chúng **không** tạo instance ngay khi gọi.

**`registerBeanDefinition`** thêm metadata dưới một tên.

**`containsBeanDefinition`** kiểm tra tên đã có tại chính registry đó.

**`getBeanDefinition`** trả metadata có thể điều chỉnh trong giai đoạn được phép.

**`removeBeanDefinition`** chỉ nên dùng khi bạn hoàn toàn hiểu ownership của definition, nhất là với bean do Spring/framework khác khai báo. Xóa một definition không phải thao tác thay thế cho destruction của một singleton instance đã tồn tại.

**`getBeanDefinitionNames`** dùng để khảo sát registry, nhưng không nên scan và chỉnh tùy tiện toàn bộ definitions theo tên giống nhau mà thiếu tiêu chí chặt chẽ.

### Trùng bean name

Nếu bạn gọi:

~~~java
registry.registerBeanDefinition("auditHandler", definition);
~~~

trong lúc tên `auditHandler` đã tồn tại, kết quả phụ thuộc cấu hình cho phép overriding và trạng thái BeanDefinitionRegistry. Đừng dựa vào silent overwrite. Nên kiểm tra:

~~~java
if (registry.containsBeanDefinition("auditHandler")) {
    throw new IllegalStateException(
        "Duplicate bean definition: auditHandler");
}
registry.registerBeanDefinition("auditHandler", definition);
~~~

Đây là đoạn minh họa thuộc một callback, cần biến `definition`. Fail fast thường an toàn hơn âm thầm thay bean của ứng dụng hoặc extension khác.

## 6. Tạo định nghĩa bằng `BeanDefinitionBuilder`

`BeanDefinitionBuilder` nằm trong `org.springframework.beans.factory.support`. Nó giúp tạo BeanDefinition programmatically mà không cần XML.

Ví dụ một class đơn giản:

~~~java
public final class ChannelHandler {
    private final String channel;

    public ChannelHandler(String channel) {
        this.channel = channel;
    }

    public String send(String message) {
        return channel + ":" + message;
    }
}
~~~

Và trong registrar:

~~~java
BeanDefinition definition =
    BeanDefinitionBuilder
        .genericBeanDefinition(ChannelHandler.class)
        .addConstructorArgValue("email")
        .setScope(BeanDefinition.SCOPE_SINGLETON)
        .getBeanDefinition();

registry.registerBeanDefinition("emailHandler", definition);
~~~

Đoạn registrar cần import `BeanDefinition` (package `org.springframework.beans.factory.config`), `BeanDefinitionBuilder` và kiểu `BeanDefinitionRegistry`. Constructor argument `"email"` được container dùng khi sau này tạo `ChannelHandler`.

`BeanDefinitionBuilder` có các method cấu hình thông dụng:

- `genericBeanDefinition(MyClass.class)` chọn bean class.
- `addConstructorArgValue(value)` truyền constructor value.
- `addPropertyValue(name, value)` gán bean property khi có setter/phương thức phù hợp.
- `setScope(BeanDefinition.SCOPE_SINGLETON)` hoặc `SCOPE_PROTOTYPE` chọn scope.
- `setLazyInit(true)` cho biết bean có thể khởi tạo lazy.
- `setPrimary(true)` đánh dấu bean chính khi autowire theo type.
- `addDependsOn(beanName)` mô tả dependency ordering qua bean definitions khi thích hợp.
- `getBeanDefinition()` trả metadata để register.

Các method này cấu hình **metadata**, không tương đương gọi constructor trực tiếp.

### Khi nào dùng `RootBeanDefinition`?

Nếu bạn cần kiểm soát trực tiếp:

~~~java
RootBeanDefinition bd =
    new RootBeanDefinition(ChannelHandler.class);
bd.getConstructorArgumentValues()
    .addGenericArgumentValue("sms");
bd.setScope(BeanDefinition.SCOPE_PROTOTYPE);
registry.registerBeanDefinition("smsHandler", bd);
~~~

Đây là đoạn minh họa cần imports phù hợp. `RootBeanDefinition` phù hợp với code framework cấp thấp; `BeanDefinitionBuilder` thường dễ đọc hơn trong hướng dẫn và các trường hợp đăng ký đơn giản.

## 7. Ví dụ hoàn chỉnh: đăng ký handler singleton và task prototype động

Đây là chương trình **chạy độc lập bằng Maven + Java 17 + Spring Context 6.1.13**.

Một `BeanDefinitionRegistryPostProcessor` sẽ đăng ký ba bean definitions **trong lúc refresh**:

1. `emailHandler`: `ChannelHandler("email")`, singleton.
2. `smsHandler`: `ChannelHandler("sms")`, singleton.
3. `taskState`: `TaskState`, prototype.

Ứng dụng sau đó lấy bean như những Spring beans thông thường và quan sát singleton/prototype.

### 7.1. Cấu trúc thư mục

~~~text
registry-post-processor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── registry/
                        └── RegistryDemo.java
~~~

### 7.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>registry-post-processor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.registry.RegistryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. File `src/main/java/com/example/registry/RegistryDemo.java`

~~~java
package com.example.registry;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class RegistryDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ChannelHandler email =
                context.getBean("emailHandler", ChannelHandler.class);
            ChannelHandler sms =
                context.getBean("smsHandler", ChannelHandler.class);

            System.out.println("email=" + email.send("hello"));
            System.out.println("sms=" + sms.send("hello"));

            ChannelHandler emailAgain =
                context.getBean("emailHandler", ChannelHandler.class);
            System.out.println("singleton reused=" + (email == emailAgain));

            TaskState first = context.getBean("taskState", TaskState.class);
            TaskState second = context.getBean("taskState", TaskState.class);

            System.out.println("prototype reused=" + (first == second));
            System.out.println("taskState isPrototype="
                    + context.isPrototype("taskState"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public static BeanDefinitionRegistryPostProcessor channelRegistrar() {
            return new ChannelRegistrar();
        }
    }

    public static class ChannelRegistrar
            implements BeanDefinitionRegistryPostProcessor {

        @Override
        public void postProcessBeanDefinitionRegistry(
                BeanDefinitionRegistry registry) throws BeansException {

            registerChannel(registry, "emailHandler", "email");
            registerChannel(registry, "smsHandler", "sms");

            BeanDefinition stateDefinition = BeanDefinitionBuilder
                .genericBeanDefinition(TaskState.class)
                .setScope(BeanDefinition.SCOPE_PROTOTYPE)
                .getBeanDefinition();

            registerUnique(registry, "taskState", stateDefinition);

            System.out.println("registry: three definitions added");
        }

        private void registerChannel(
                BeanDefinitionRegistry registry,
                String name,
                String channel) {

            BeanDefinition definition = BeanDefinitionBuilder
                .genericBeanDefinition(ChannelHandler.class)
                .addConstructorArgValue(channel)
                .setScope(BeanDefinition.SCOPE_SINGLETON)
                .getBeanDefinition();

            registerUnique(registry, name, definition);
        }

        private void registerUnique(
                BeanDefinitionRegistry registry,
                String name,
                BeanDefinition definition) {

            if (registry.containsBeanDefinition(name)) {
                throw new IllegalStateException(
                    "Duplicate bean definition: " + name);
            }

            registry.registerBeanDefinition(name, definition);
        }

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory)
                throws BeansException {

            System.out.println("factory: email definition available="
                    + beanFactory.containsBeanDefinition("emailHandler"));
        }
    }

    public static class ChannelHandler {
        private final String channel;

        public ChannelHandler(String channel) {
            this.channel = channel;
        }

        public String send(String message) {
            return channel + ":" + message;
        }
    }

    public static class TaskState {
        // Mỗi lookup prototype nhận một instance Java độc lập.
    }
}
~~~

Chương trình đặt các class phụ vào cùng file dưới dạng `static` nested class. `ChannelRegistrar` được đăng ký qua một `static @Bean` method; nó chỉ đăng ký **definitions**, không gọi `new ChannelHandler(...)` trong registry callback. Sau refresh, Spring khởi tạo hai singleton handlers theo nhu cầu/context lifecycle; `TaskState` prototype được tạo khi gọi `getBean("taskState")`.

### 7.4. Lệnh chạy

Cần JDK 17 trở lên và Maven 3.9.x. Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Output **do chương trình tự in**:

~~~text
registry: three definitions added
factory: email definition available=true
email=email:hello
sms=sms:hello
singleton reused=true
prototype reused=false
taskState isPrototype=true
~~~

Các plugin Maven hoặc logging framework có thể ghi thông tin khác; bảy dòng trên là output của các lệnh `System.out.println` trong mã ví dụ.

### 7.5. Phân tích từng dòng

**`registry: three definitions added`:** callback `postProcessBeanDefinitionRegistry` đã đăng ký metadata ba bean.

**`factory: email definition available=true`:** callback `postProcessBeanFactory` nhìn thấy definition từ bước registry. Đây là bằng chứng thứ tự hợp lý: bổ sung metadata trước khi xử lý BeanFactory.

**`email=email:hello`** và **`sms=sms:hello`:** Spring sử dụng constructor arguments đã được gán trong BeanDefinitionBuilder để tạo hai objects cùng class nhưng có cấu hình khác nhau.

**`singleton reused=true`:** `emailHandler` là singleton, nên hai lần lookup theo tên trả cùng reference.

**`prototype reused=false`:** `taskState` là prototype, nên hai lần lookup trả hai object khác nhau.

**`taskState isPrototype=true`:** BeanFactory nhận metadata scope vừa đăng ký.

Không có lời gọi `getBean()` nào trong registrar callback. Điều đó giúp Spring hoàn thành phase xử lý definitions và post-processors trước khi business beans được dùng.

## 8. Vì sao `@Bean` đăng ký post-processor nên là `static`?

Trong cấu hình Java:

~~~java
@Configuration
class AppConfig {
    @Bean
    static BeanDefinitionRegistryPostProcessor registrar() {
        return new ChannelRegistrar();
    }
}
~~~

đây là ví dụ minh họa trong class cấu hình có `ChannelRegistrar` được định nghĩa.

`BeanDefinitionRegistryPostProcessor` và `BeanFactoryPostProcessor` được Spring sử dụng **rất sớm**. Nếu method `@Bean` trả post-processor là **instance method** của `@Configuration` class, Spring có thể phải khởi tạo cấu hình class quá sớm để gọi method đó. Việc đó có thể ảnh hưởng khả năng xử lý annotation/injection/post-processing đầy đủ của configuration class.

Do vậy, tài liệu Spring khuyến nghị:

> Với `@Bean` methods trả về `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor`, khai báo method là `static` để container gọi mà không cần instantiate configuration class trước thời điểm thích hợp.

Ví dụ hoàn chỉnh đã dùng `public static` ở `AppConfig.channelRegistrar()` vì lý do này.

### Return type của `@Bean` cũng quan trọng

Nên khai báo return type phản ánh **post-processor contract**:

~~~java
@Bean
public static BeanDefinitionRegistryPostProcessor registrar() {
    return new ChannelRegistrar();
}
~~~

Thay vì trả `Object` hoặc một interface quá chung khiến Spring không thể dễ dàng xác định loại bean từ metadata trước khi khởi tạo. Việc Spring nhận diện đúng loại processor ở giai đoạn sớm là quan trọng.

Không gọi `new ChannelRegistrar().postProcessBeanDefinitionRegistry(...)` từ code nghiệp vụ hoặc `main` trong một context đang chạy. Hãy để lifecycle của context tự phát hiện và invoke processor.

## 9. Đăng ký processor theo chương trình, không dùng `@Bean`

Ngoài việc đăng ký processor như một bean, có thể chủ động thêm processor **trước refresh** thông qua `ConfigurableApplicationContext.addBeanFactoryPostProcessor(...)`.

Ví dụ:

~~~java
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext();

context.register(AppConfig.class);
context.addBeanFactoryPostProcessor(new ChannelRegistrar());
context.refresh();
~~~

Đây là code minh họa. Nếu `AppConfig` vẫn chứa `@Bean channelRegistrar()` như ví dụ hoàn chỉnh, đoạn trên sẽ đăng ký thêm một registrar **lần thứ hai**, gây trùng bean names. Hãy chọn **một trong hai** cách đăng ký.

Cách programmatic phù hợp cho bootstrap infrastructure cần nhận một tập cấu hình trước khi context refresh hoặc được nhúng trong một framework.

**Điểm khác biệt về ordering:** Post-processors được thêm programmatically không nhất thiết tuân theo thứ tự `PriorityOrdered`/`Ordered` như các processor được Spring phát hiện từ bean definitions; Spring xử lý chúng theo hợp đồng đăng ký programmatic. Không nên trộn nhiều cơ chế đăng ký mà dựa vào suy đoán thứ tự.

## 10. `BeanDefinitionRegistryPostProcessor` liên hệ với `ConfigurationClassPostProcessor`

Spring có infrastructure class `ConfigurationClassPostProcessor` cũng implements `BeanDefinitionRegistryPostProcessor`. Nó xử lý những khái niệm Java configuration như `@Configuration`, `@ComponentScan`, `@Import` và `@Bean`.

Đây là lý do việc đăng ký một custom registrar bằng `static @Bean` có thể hoạt động: configuration infrastructure xử lý cấu hình, nhận diện bean definition của registrar, rồi Spring tiếp tục chạy các registry post-processors theo quy trình phát hiện.

**Không nên dựa vào giả định tất cả registry post-processors đều chỉ có một lượt duy nhất.** Spring có thể chạy các vòng phát hiện thêm post-processors được đăng ký bởi các processors trước đó.

Sơ đồ ý tưởng:

~~~text
Context refresh
    |
    v
ConfigurationClassPostProcessor xử lý Java config
    |
    v
Custom registry post-processors được phát hiện
    |
    +-- Bổ sung định nghĩa application beans
    |
    +-- Có thể bổ sung definition của processor khác
    |
    v
Các post-processors cần xử lý tiếp được phát hiện/invoke
    |
    v
BeanFactoryPostProcessor callbacks
    |
    v
BeanPostProcessor registration / singleton instantiation
~~~

Thứ tự thực tế có thêm nhóm priority/ordered và một số internal processors. Không buộc code dynamic registrar phụ thuộc vào chi tiết không được hợp đồng Spring đảm bảo.

## 11. `PriorityOrdered`, `Ordered` và thứ tự xử lý

Khi ApplicationContext tự phát hiện nhiều `BeanDefinitionRegistryPostProcessor` beans, Spring xem xét `PriorityOrdered`, tiếp đến `Ordered`, rồi các processor còn lại theo quy trình của framework.

Ví dụ một custom registrar:

~~~java
import org.springframework.core.Ordered;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;

public final class OrderedRegistrar
        implements BeanDefinitionRegistryPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE;
    }

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        // ...
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // ...
    }
}
~~~

Đây là class skeleton minh họa; cần imports BeanDefinitionRegistry và ConfigurableListableBeanFactory. Nó thể hiện callback methods được implement và khả năng công bố order.

**Đừng nhầm:**

- `PriorityOrdered` là một nhóm ưu tiên cao hơn `Ordered`, không chỉ là số nhỏ hơn.
- `Ordered` đặt order giữa các processors trong quá trình framework auto-detect.
- Quan hệ phụ thuộc của metadata và việc processors có tạo definitions mới đôi khi ảnh hưởng các vòng phát hiện.
- Programmatically added post-processors có contract ordering riêng.
- Số order không thay đổi bản chất metadata phase và không làm “bean instance đã sẵn sàng”.

Đừng cố ép custom registrar chạy trước `ConfigurationClassPostProcessor` chỉ bằng một số âm tùy ý rồi dựa vào @Bean metadata chưa được parse. Hãy thiết kế dựa trên contracts và kiểm thử toàn bộ context.

## 12. Định nghĩa động có được inject như bean bình thường không?

Có, miễn là definition có đủ metadata và được đăng ký đúng phase.

Giả sử registry bổ sung `emailHandler` kiểu `ChannelHandler`. Một service có thể nhận trực tiếp một bean cụ thể theo tên:

~~~java
@Service
public final class NotificationService {
    private final ChannelHandler handler;

    public NotificationService(
            @Qualifier("emailHandler") ChannelHandler handler) {
        this.handler = handler;
    }

    public String notify(String message) {
        return handler.send(message);
    }
}
~~~

Đoạn này là class minh họa, cần import `Service`, `Qualifier` và có `ChannelHandler` từ ví dụ ở mục 7. Spring resolve qualifier trong quá trình tạo service như với bất cứ bean definition nào khác.

Nếu tạo nhiều beans cùng class và autowire chỉ bằng type:

~~~java
public NotificationService(ChannelHandler handler) { ... }
~~~

Spring có thể báo `NoUniqueBeanDefinitionException` vì `emailHandler` và `smsHandler` đều là `ChannelHandler` và không có lựa chọn duy nhất.

Các phương án:

- Dùng `@Qualifier("emailHandler")` tại injection point.
- Đánh dấu đúng một definition là `primary` nếu thực sự muốn default.
- Inject `List<ChannelHandler>` hoặc `Map<String, ChannelHandler>` khi muốn sử dụng toàn bộ strategies.
- Cung cấp registry abstraction biểu đạt danh sách handlers đã được cấu hình.

Không dựa vào thứ tự registry insertion để tự chọn handler “đầu tiên” khi cần semantics lựa chọn rõ ràng.

## 13. Đăng ký nhiều definitions từ metadata: thiết kế tốt

Một tình huống production là có một danh sách cấu hình:

~~~text
plugins:
  - id: email
    class: ChannelHandler
  - id: sms
    class: ChannelHandler
~~~

Đây là **metadata minh họa**, không phải cú pháp cấu hình Spring Boot ràng buộc vào một thư viện parser nhất định.

Registrar có thể duyệt metadata đã được validate và tạo definitions:

~~~java
for (PluginSpec spec : specs) {
    String name = spec.id() + "Handler";

    BeanDefinition bd = BeanDefinitionBuilder
        .genericBeanDefinition(ChannelHandler.class)
        .addConstructorArgValue(spec.id())
        .getBeanDefinition();

    if (registry.containsBeanDefinition(name)) {
        throw new IllegalStateException(
            "Duplicate plugin bean name: " + name);
    }

    registry.registerBeanDefinition(name, bd);
}
~~~

Đoạn này là mã minh họa, yêu cầu `specs` là collection các record/objects `PluginSpec` với `id()` hợp lệ, imports Spring phù hợp.

**Thiết kế cần có:**

1. Tên bean deterministic, không chứa dữ liệu không tin cậy chưa được kiểm tra.
2. Validate config trước khi đưa vào registry để fail fast.
3. Không dùng \`Class.forName\` với tên class từ nguồn không tin cậy rồi auto-register arbitrary classes.
4. Chọn scope rõ ràng và xem xét thread-safety nếu bean singleton.
5. Không lén override bean name được module khác sở hữu.
6. Không bắt đầu network/DB connection trong registry callback.
7. Nếu metadata đến từ external service, nên nạp nó một cách có kiểm soát trước refresh hoặc dùng cơ chế runtime riêng, không biến refresh thành một loạt remote calls vô hạn.

Khi metadata chỉ là một danh sách cố định vài phần tử, `@Bean` thường đơn giản hơn việc xây cả registrar.

## 14. Thêm bean definitions không đồng nghĩa thêm bean instances

Xem chuỗi hành động:

~~~java
BeanDefinition bd = BeanDefinitionBuilder
    .genericBeanDefinition(ExpensiveClient.class)
    .setLazyInit(true)
    .getBeanDefinition();

registry.registerBeanDefinition("expensiveClient", bd);
~~~

Đây là đoạn minh họa; `ExpensiveClient` là class ứng dụng được định nghĩa riêng và `registry` là callback parameter.

Sau `registerBeanDefinition`, registry đã có metadata nhưng chưa nhất thiết có `ExpensiveClient` object. Bean có thể được tạo sau, khi container xử lý eager singleton hoặc khi có dependency yêu cầu.

Nếu dùng:

~~~java
registry.registerBeanDefinition("expensiveClient", bd);
ExpensiveClient instance = context.getBean(ExpensiveClient.class);
~~~

bạn đã pha trộn registry phase với instance lookup, có thể làm bean được tạo **trước khi tất cả BeanFactoryPostProcessor và BeanPostProcessor áp dụng**. Đây là anti-pattern; đừng làm vậy trong `postProcessBeanDefinitionRegistry`.

Với prototype, metadata có thể tồn tại mà không có target instance nào cho tới khi caller gọi `getBean(...)`.

## 15. Vì sao không nên gọi `getBean()` trong registry callback?

Theo hợp đồng Spring, `BeanFactoryPostProcessor` và registry extension points được thiết kế để làm việc với **bean definitions, không phải các instance bình thường**.

Gọi `getBean()` sớm có thể:

- Tạo singleton trước khi property placeholders/configuration được xử lý đầy đủ.
- Bỏ lỡ một số `BeanPostProcessor` được đăng ký sau đó (ví dụ proxy/AOP).
- Khởi động side effects quá sớm: threads, kết nối network, I/O.
- Làm thay đổi dependency initialization order hoặc gặp circular reference.
- Khiến context chứa một bean thiếu wrapper/infrastructure mà các beans khác được nhận.

Nếu cần đọc cấu hình để quyết định definitions, cân nhắc đưa dữ liệu đó vào constructor của registrar từ nguồn đã chuẩn bị sẵn, đọc metadata không kích hoạt beans khác hoặc dùng một extension phù hợp của Spring Boot nếu dự án thuộc Boot.

Không tạo application service rồi truy xuất service qua BeanFactory chỉ để đọc vài properties khi đăng ký definitions. Tách **bootstrap metadata** khỏi **runtime service behavior**.

## 16. Có cần đăng ký bean definition sau khi context đã refresh không?

`BeanDefinitionRegistryPostProcessor` được định nghĩa cho **giai đoạn khởi tạo BeanFactory** trước các ordinary beans. Nó không được tự invoke lại mỗi khi bạn thêm phần tử vào một danh sách runtime.

Sau `context.refresh()`, một số loại context/registry vẫn có các API programmatic để thêm definitions, nhưng **không được coi đó tương đương chạy lại toàn bộ refresh pipeline**. Các metadata processors, post-processor registration, singleton creation và các dependencies đã resolve có thể không được áp dụng cho entries mới theo đúng giả định ban đầu.

Nếu thật sự cần plugin hot-load runtime:

- Thiết kế runtime registry và lifecycle manager riêng.
- Xác định classloader, dependency, state và cleanup.
- Dùng child context hoặc một container/module riêng nếu cần isolation.
- Quản lý concurrency và ownership khi thay strategies đang được request sử dụng.
- Không dùng BeanDefinitionRegistryPostProcessor như một API runtime “thêm bean bất kỳ lúc nào”.

Đối với metadata biết lúc startup, registry post-processor là lựa chọn phù hợp. Đối với thay đổi liên tục sau startup, thường nên dùng một API quản lý plugin động riêng.

## 17. BeanDefinitionRegistryPostProcessor và BeanPostProcessor khác nhau cả về “bean scope”

Một `BeanDefinitionRegistryPostProcessor` có thể tạo definition:

~~~java
BeanDefinition prototype = BeanDefinitionBuilder
    .genericBeanDefinition(JobState.class)
    .setScope(BeanDefinition.SCOPE_PROTOTYPE)
    .getBeanDefinition();
registry.registerBeanDefinition("jobState", prototype);
~~~

Điều đó chỉ nói **mỗi lần container được yêu cầu cấp `jobState` sẽ dùng prototype scope**. Nó không làm registrar tự trở thành prototype và không tạo `JobState` mới sau mỗi method call của consumer singleton.

Tương tự, `BeanPostProcessor` xử lý bean instance khi nó được tạo, trong khi `BeanDefinitionRegistryPostProcessor` có thể thêm definition chưa có object.

Đừng nhầm method suffix “PostProcessor” để cho rằng cả hai API có cùng thời điểm và tác động.

## 18. Vai trò của `FactoryBean`: một lựa chọn khác ở tầng product

`FactoryBean<T>` là bean đặc biệt expose một **sản phẩm** từ `getObject()`. Nó khác registrar:

| Tình huống | Thường nên chọn |
| --- | --- |
| Cần đăng ký **nhiều bean definitions mới** dựa trên metadata | `BeanDefinitionRegistryPostProcessor` |
| Cần tạo/expose **một loại product** qua factory đặc biệt | `FactoryBean<T>` |
| Chỉ cần tạo một object bình thường qua constructor | `@Bean` factory method |
| Cần thay đổi metadata một bean definition đã có | `BeanFactoryPostProcessor` |
| Cần xử lý/wrap một bean instance | `BeanPostProcessor` |

Một registrar có thể **đăng ký BeanDefinition mà bean class là một FactoryBean** nếu cần expose products đặc biệt. Nhưng đó là cách kết hợp nâng cao; ứng dụng thông thường nên chọn extension point đơn giản nhất thực hiện đúng mục đích.

Đừng nhầm `BeanFactory` (container), `FactoryBean` (factory object) và `BeanDefinitionRegistryPostProcessor` (registry hook).

## 19. Vấn đề `@Configuration` class được tạo quá sớm

Một lỗi khá khó chẩn đoán:

~~~java
@Configuration
class BadConfig {

    @Autowired
    private SomeDependency dependency;

    @Bean
    BeanDefinitionRegistryPostProcessor registrar() {
        return new ChannelRegistrar();
    }
}
~~~

Đây là một **định nghĩa cấu hình có vấn đề**, chưa bao gồm các class và imports cần thiết. Vì `registrar()` là instance method, Spring có thể phải khởi tạo `BadConfig` trước khi một số bean post-processors hoàn tất; tình trạng đó có thể làm annotation processing/injection của class cấu hình không đạt như dự kiến.

Sửa theo hướng:

~~~java
@Configuration(proxyBeanMethods = false)
class GoodConfig {
    @Bean
    static BeanDefinitionRegistryPostProcessor registrar() {
        return new ChannelRegistrar();
    }
}
~~~

Trong nhiều trường hợp, `static @Bean` là lựa chọn rõ ràng và được tài liệu Spring khuyến nghị cho `BeanFactoryPostProcessor`-returning methods.

Nếu registrar thực sự cần dữ liệu ngoài, hãy truyền vào qua constructor/factory method theo cơ chế bootstrap cho phép, nhưng đừng ép khởi tạo sớm cả đồ thị runtime chỉ để lấy config.

## 20. Lỗi sai tên, class và constructor arguments

BeanDefinition metadata phải khớp class đích.

Ví dụ:

~~~java
BeanDefinition bd = BeanDefinitionBuilder
    .genericBeanDefinition(ChannelHandler.class)
    .addConstructorArgValue("email")
    .getBeanDefinition();
~~~

nó hoạt động vì `ChannelHandler(String channel)` có một constructor nhận string. Nếu class đích chỉ có constructor nhận `int`, metadata có thể bị lỗi khi bean được tạo.

Thời điểm lỗi có thể là:

- **Startup:** với eager singleton, container có thể tạo bean khi refresh và báo lỗi ngay.
- **Lần lookup đầu:** với lazy singleton hoặc prototype, lỗi có thể phát sinh sau khi context đã refresh.

Lỗi thường xuất hiện dưới dạng `BeanCreationException`, `UnsatisfiedDependencyException` hoặc thông báo không tìm thấy constructor phù hợp; phải đọc root cause.

Có nhiều constructor overload cùng kiểu convert được? Spring có thể phải resolve và chuyển đổi args; nên tránh metadata mơ hồ, sử dụng indexed constructor arguments hoặc inject collaborators bằng cơ chế rõ ràng.

Nếu constructor cần một Spring-managed bean khác, cân nhắc `addConstructorArgReference("dependencyBeanName")` thay vì truyền một instance tự tạo bằng `new`.

## 21. Bean name và autowiring conflicts

Dynamic registrar dễ tạo nhiều beans cùng type:

~~~text
emailHandler: ChannelHandler
smsHandler: ChannelHandler
webhookHandler: ChannelHandler
~~~

Nếu một service inject:

~~~java
public AlertService(ChannelHandler handler) {
    this.handler = handler;
}
~~~

đây là constructor minh họa trong một class có field `handler`. Với ba beans cùng type, container có thể không biết chọn bean nào và ném `NoUniqueBeanDefinitionException`.

Giải pháp:

~~~java
public AlertService(
        @Qualifier("emailHandler") ChannelHandler handler) {
    this.handler = handler;
}
~~~

hoặc đăng ký metadata `primary` khi một handler thật sự mặc định:

~~~java
BeanDefinition bd = BeanDefinitionBuilder
    .genericBeanDefinition(ChannelHandler.class)
    .addConstructorArgValue("email")
    .setPrimary(true)
    .getBeanDefinition();
~~~

Trong thực tế `setPrimary(true)` có trên builder, nhưng **không đánh dấu nhiều definitions cùng type đều là primary**. Hãy giữ bean names ổn định và dùng qualifier/collection injection khi phù hợp.

## 22. Idempotency, trùng định nghĩa và đăng ký lại

Registrar nên có chính sách rõ ràng nếu có cùng bean name:

- **Fail-fast:** ném exception để bảo vệ metadata.
- **Skip-if-present:** chỉ hợp lý nếu chủ đích cho phép một module khác override cấu hình, có ghi rõ precedence.
- **Replace-existing:** cực kỳ thận trọng vì có thể thay bean definition thuộc framework/ứng dụng và thay đổi behavior khó lường.

Ví dụ fail-fast:

~~~java
if (registry.containsBeanDefinition(beanName)) {
    throw new IllegalStateException("Bean name already used: " + beanName);
}
registry.registerBeanDefinition(beanName, definition);
~~~

Đây là snippet nằm trong registry callback.

Không dùng exception handling như:

~~~java
try {
    registry.registerBeanDefinition(beanName, definition);
} catch (Exception ignored) {
    // Sai: âm thầm bỏ qua lỗi registry.
}
~~~

Nếu registry thay đổi không đầy đủ, ứng dụng có thể khởi động nhưng thiếu beans, rồi lỗi muộn và khó truy nguyên. Khi metadata không hợp lệ hoặc collision xảy ra, fail fast với tên bean rõ ràng thường tốt hơn.

### Refresh và nhiều context

Một class `ChannelRegistrar` có thể được dùng trong nhiều contexts độc lập. Từng context có registry riêng và được đăng ký definitions riêng. Không dùng static mutable set chung để đánh dấu “đã đăng ký” theo JVM, vì nó có thể khiến context thứ hai thiếu beans dù registry của nó đang trống.

Giữ callback **theo registry được truyền vào**.

## 23. Thread-safety và resource ownership

Registry callback thường chạy trong quá trình refresh và là cấu hình hạ tầng, không nên biến thành một background job có trạng thái sống lâu. Trong callback:

- Không bắt đầu thread đọc/ghi registry song song.
- Không mở socket/file rồi bỏ quên cleanup khi refresh thất bại.
- Không đăng ký một bean singleton mang mutable request state mà quên synchronization.
- Không dùng giá trị cấu hình bí mật từ nguồn ngoài rồi in chúng trong exception/log.
- Nếu registrar đăng ký prototype giữ tài nguyên, caller mỗi instance vẫn phải chịu trách nhiệm cleanup như với prototype bình thường.

Bean definitions được bổ sung là đối tượng **được Spring quản lý sau khi hoàn tất registration**. Chúng tuân theo scope và lifecycle tương ứng, nhưng không có nghĩa mọi tài nguyên đã được mở trong registrar callback sẽ tự được Spring đóng.

Nếu cần xử lý I/O, nên làm rõ ownership và startup failure policy trong một component được quản lý lifecycle phù hợp, không đẩy toàn bộ sang registry callback.

## 24. Kiểm thử một registrar có chất lượng

### 24.1. Unit test metadata thuần

Có thể tạo registry độc lập như `DefaultListableBeanFactory` rồi gọi registrar:

~~~java
DefaultListableBeanFactory registry =
    new DefaultListableBeanFactory();

ChannelRegistrar registrar = new ChannelRegistrar();
registrar.postProcessBeanDefinitionRegistry(registry);

BeanDefinition email = registry.getBeanDefinition("emailHandler");

if (!BeanDefinition.SCOPE_SINGLETON.equals(email.getScope())) {
    throw new AssertionError("emailHandler should be singleton");
}

if (!registry.containsBeanDefinition("taskState")) {
    throw new AssertionError("taskState missing");
}
~~~

Đoạn này là snippet test nằm trong dự án ví dụ, cần import `DefaultListableBeanFactory`, `BeanDefinition` và tham chiếu đúng `RegistryDemo.ChannelRegistrar` nếu dùng class nested từ mục 7. Nó chỉ xác minh registry metadata, không phải toàn bộ Spring post-processor pipeline.

### 24.2. Integration test qua ApplicationContext

Ví dụ chương trình `RegistryDemo` đã tạo Spring context thật và kiểm tra cả registry + bean creation.

Một test integration nên xác minh:

1. `context.refresh()` chạy thành công.
2. Dynamic bean names tồn tại.
3. `getBean("emailHandler", ChannelHandler.class)` hoạt động.
4. Constructor arguments chính xác.
5. Scope singleton trả cùng instance.
6. Scope prototype trả independent instances.
7. Collision bean name báo lỗi rõ.
8. Không có eager instantiation phụ thuộc việc `getBean()` trong registrar.
9. Những bean consumers dùng qualifier/collection injection đều resolve đúng.

Nếu registrars chịu ảnh hưởng properties/profiles, test những tổ hợp cấu hình dự kiến thay vì chỉ một happy path.

### 24.3. Không lạm dụng log order làm assertion duy nhất

Một số log của container có thể khác giữa versions. Nên assert trạng thái metadata và object identity qua code; stdout trong mục 7 chỉ minh họa thời điểm registry/factory callbacks.

Nếu thực sự test phase ordering, viết một event recorder thuộc test context và assert những sự kiện cần thiết, tránh phụ thuộc log tự động của Spring.

## 25. Chẩn đoán sự cố thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Bean động không tồn tại sau refresh | Registrar không được đăng ký/được phát hiện, hoặc tên khác | Dùng static `@Bean` đúng return type; kiểm tra processor invocation |
| `postProcessBeanDefinitionRegistry` không chạy | Processor không nằm trong context hoặc đăng ký sau refresh | Đăng ký trước refresh; test context thật |
| Configuration class có dependency null | Non-static `@Bean` tạo BFPP/BDRPP quá sớm | Dùng static method theo khuyến nghị |
| Trùng bean name/override không mong muốn | Nhiều modules đăng ký cùng tên | Tạo namespace, collision policy và fail fast |
| Bean tạo quá sớm, thiếu AOP/proxy | Registrar gọi `getBean()` trong callback | Chỉ thao tác metadata |
| `NoUniqueBeanDefinitionException` | Nhiều dynamic beans cùng type | Qualifier, primary hoặc collection injection |
| Bean instance tạo ra không đúng constructor | BeanDefinition thiếu/sai constructor args | Kiểm tra builder và bean class signatures |
| Prototype không mới trong singleton consumer | Constructor injection resolve một lần | Inject `ObjectProvider<T>` theo mỗi nghiệp vụ |
| Registrar chạy trước/sau không như dự kiến | Ordering semantics không giống giả định | Xem `PriorityOrdered`/`Ordered`, cách đăng ký programmatic |
| Bean có type lookup sai | Thiếu metadata type/bean definition bất thường | Khai báo bean class/factory method rõ |
| Context start chậm | Registrar gọi network/I/O nặng | Chuyển I/O ra lifecycle phù hợp, có timeout |
| Hot reload không kích hoạt registrar lại | BDRPP là refresh-time SPI | Thiết kế runtime registry/hot reload riêng |
| Bean definition mới không được xử lý như kỳ vọng | Đăng ký quá muộn sau giai đoạn processors | Đăng ký khi refresh qua BDRPP |
| Cleanup resource bị bỏ qua | Tạo resource trực tiếp trong post-processor | Tách ownership vào managed bean/lifecycle |

## 26. Khi nào không nên dùng BeanDefinitionRegistryPostProcessor?

Không cần dùng extension point này trong những trường hợp:

- Chỉ tạo một hoặc vài singleton rõ ràng: `@Bean` đủ.
- Chỉ cần quét annotation theo package: `@ComponentScan` đủ.
- Chỉ import một cấu hình/module cố định: `@Import` có thể đơn giản hơn.
- Chỉ điều chỉnh properties của bean đã tồn tại: `BeanFactoryPostProcessor`/typed configuration phù hợp hơn.
- Chỉ wrap/intercept object instances: dùng AOP/`BeanPostProcessor`.
- Chỉ cần chọn một trong nhiều strategies đã đăng ký: inject `Map<String, Strategy>` hoặc danh sách beans.
- Chỉ cần tạo POJO ngắn hạn không có dependency Spring: dùng constructor/factory Java thông thường.
- Chỉ cần add/remove listener/runtime jobs sau startup: thiết kế runtime registry thay vì sửa bean definitions vào thời điểm tùy ý.

Công cụ này mạnh vì chạy rất sớm và thay đổi tập definitions của container. Quyền lực đó tạo ra coupling với cấu trúc Spring và làm startup phức tạp hơn. Hãy chọn nó khi **chính việc bổ sung definitions là yêu cầu thực sự**.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** `BeanDefinitionRegistryPostProcessor` và `BeanPostProcessor` khác nhau cơ bản ở đâu?

**Đáp án:** BDRPP làm việc với BeanDefinitionRegistry/metadata trong phase chuẩn bị BeanFactory, có thể bổ sung definitions mới. BPP làm việc với từng bean instance trước/sau initialization.

**Câu 2.** Method `postProcessBeanDefinitionRegistry` có nên gọi `context.getBean("emailHandler")` ngay sau `registerBeanDefinition` không?

**Đáp án:** Không. Registry phase cần chỉnh metadata, còn gọi getBean có thể khởi tạo bean quá sớm, trước khi các post-processors/infrastructure hoàn tất.

**Câu 3.** Vì sao method `@Bean` trả về BDRPP thường nên là `static`?

**Đáp án:** Vì post-processor được cần ở phase rất sớm; static method giúp Spring gọi method mà không phải instantiate configuration class quá sớm và gây ảnh hưởng annotation/bean post-processing.

**Câu 4.** Sau khi registrar đăng ký `ChannelHandler` với scope prototype, container có tạo một handler mới sau mỗi lần gọi method của một singleton consumer không?

**Đáp án:** Không. Prototype tạo mới theo lần container lookup; singleton constructor injection resolve dependency một lần. Muốn mỗi nghiệp vụ nhận object mới, dùng provider/lookup phù hợp.

**Câu 5.** Registrar đăng ký hai `ChannelHandler` cùng type. Constructor inject `ChannelHandler` không có qualifier có thể lỗi gì?

**Đáp án:** `NoUniqueBeanDefinitionException` nếu không có candidate duy nhất hoặc cơ chế chọn rõ ràng. Có thể dùng `@Qualifier`, một primary hợp lệ hoặc inject collection/map.

**Câu 6.** BDRPP có thể đăng ký bean definition của một `BeanFactoryPostProcessor` khác không?

**Đáp án:** Có. Đây là một lý do BDRPP được chạy trước giai đoạn phát hiện/invoke các BeanFactoryPostProcessor thông thường. Tuy vậy, code cần hiểu đúng processor ordering và không tạo application beans sớm.

**Câu 7.** Nếu chỉ cần tạo một `HttpClient` singleton với cấu hình đơn giản, nên viết registrar hay `@Bean`?

**Đáp án:** Thường nên dùng `@Bean`. BDRPP chỉ có giá trị khi việc tạo thêm nhiều dynamic bean definitions là yêu cầu thực sự của hạ tầng.

**Câu 8.** Có thể dùng BeanDefinitionRegistryPostProcessor để tự động hot-add bean mới mỗi khi nhận HTTP request không?

**Đáp án:** Không đúng mục đích. Processor thuộc giai đoạn refresh/setup của context, không phải API runtime tự động chạy lại theo request. Sử dụng runtime registry/plugin manager khác.

## 28. Tóm tắt cần ghi nhớ

- **BeanDefinition** mô tả cách Spring sẽ tạo bean; `registerBeanDefinition` chưa tạo Java object.
- **BeanDefinitionRegistryPostProcessor** có callback `postProcessBeanDefinitionRegistry` để **thêm/sửa definitions trước ordinary BeanFactoryPostProcessor processing**, đồng thời có `postProcessBeanFactory` do nó extends `BeanFactoryPostProcessor`.
- **BeanDefinitionBuilder** là cách thuận tiện để tạo metadata: class, constructor args, scope, property values và các thuộc tính liên quan.
- **`static @Bean`** được khuyến nghị khi đăng ký post-processor bằng Java configuration, vì processor phải được tạo rất sớm.
- **Không gọi `getBean()` trong registry phase**; tránh premature instantiation.
- **Ưu tiên đặt tên deterministic, chống collision, validate cấu hình và test bằng context thật**.
- **Chọn extension point nhỏ nhất**: `@Bean` cho những object thông thường, `BeanFactoryPostProcessor` cho metadata hiện có, `BeanPostProcessor` cho instances, và BDRPP khi cần thêm definitions mới.
- **Không sử dụng BDRPP như hệ thống runtime hot reload**; registry processing được thiết kế cho pha xây dựng context.

## 29. Tài liệu Spring chính thức

- [`BeanDefinitionRegistryPostProcessor` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html): định nghĩa callback registry và quan hệ với `BeanFactoryPostProcessor`.
- [`BeanFactoryPostProcessor` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html): chỉ thao tác bean definitions, khuyến nghị static `@Bean` khi đăng ký.
- [`BeanDefinitionRegistry` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistry.html): API đăng ký/tra cứu definitions.
- [`BeanDefinitionBuilder` Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionBuilder.html): cấu hình BeanDefinition programmatically.
- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): extension points cho BeanFactoryPostProcessor, BeanPostProcessor, FactoryBean.
- [`ConfigurationClassPostProcessor` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationClassPostProcessor.html): xử lý `@Configuration`/`@Bean` trong registry phase.
