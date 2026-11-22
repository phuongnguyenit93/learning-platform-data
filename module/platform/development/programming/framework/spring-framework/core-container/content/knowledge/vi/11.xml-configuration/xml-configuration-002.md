# Khai báo bean bằng id, class và alias trong Spring XML

## 1. Vì sao cần hiểu id, class và alias?

Trong Spring Core Container, XML là một cách khai báo **bean definitions** — metadata hướng dẫn container tìm class, tạo object, inject dependency và quản lý scope/lifecycle. Ví dụ:

```xml
<bean id="messageFormatter" class="com.example.MessageFormatter"/>
```

Bốn khái niệm cần phân biệt:

- **`<bean>`**: một bean definition trong XML.
- **`id`**: tên định danh tường minh của bean.
- **`class`**: tên Java class đầy đủ dùng để tạo bean theo cấu hình (hoặc class chứa factory method).
- **`name` / `<alias/>`**: những **tên thay thế** dùng để tìm cùng bean definition, không phải lời yêu cầu tạo thêm bean.

Phân biệt sai dẫn đến lỗi `NoSuchBeanDefinitionException`, `ClassNotFoundException`, phụ thuộc XML không resolve được hoặc vô tình tạo nhiều object khi chỉ muốn nhiều tên.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Viết XML khai báo bean dùng `id` và `class` đúng cách.
2. Hiểu `name` hỗ trợ nhiều bean identifiers và các ký tự phân cách.
3. Đăng ký alias ngoài bean definition bằng `<alias name="..." alias="..."/>`.
4. Tham chiếu bean theo id hoặc alias bằng `ref`; phân biệt `value` và `ref`.
5. Giải thích tại sao alias không làm tăng bean-definition count.
6. Phân biệt **same definition** với **same instance** trong singleton/prototype scopes.
7. Xử lý các trường hợp trùng bean name, sai FQCN, constructor arguments và alias chains.
8. Chạy ví dụ Java 17+ với Spring Framework 6.2.9, XML `beans.xml` và `ClassPathXmlApplicationContext`; dự đoán đúng stdout.

## 2. Bean definition và bean instance là hai tầng

Tập hợp XML định nghĩa **cách** tạo bean. Container chưa nhất thiết tạo object ngay khi XML được parse.

```text
beans.xml
  |
  |  <bean id="formatter"
  |        class="demo.MessageFormatter"/>
  v
XML BeanDefinitionReader
  |
  v
BeanDefinitionRegistry
  |
  | bean name, class, constructor args, scope, lifecycle...
  v
BeanFactory / ApplicationContext
  |
  | Khi cần tạo bean
  v
Java bean instance
```

Ở `singleton` mặc định, nhiều lần tra **cùng bean** trong **cùng context** trả một managed instance. Ở `prototype`, mỗi lần lookup thông thường lại tạo một instance. Alias luôn tham chiếu **bean definition** tương ứng, không tự đổi scope hay số instance cần tạo.

Một Java class có thể được khai báo thành nhiều bean definitions khác nhau. Ngược lại, một bean definition có thể có nhiều names/aliases. Cần xác định mình đang nói về **số definitions**, **số names** hay **số instances**.

## 3. XML beans namespace chuẩn

Một file Spring XML tối thiểu:

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="formatter"
          class="com.example.MessageFormatter"/>

</beans>
```

Phần tử `<beans>` là root của file cấu hình, dùng Spring Beans namespace. `xsi:schemaLocation` khai báo cặp namespace/schema để XML parser hiểu cấu trúc. Các URL thuộc schema, không phải endpoint kinh doanh hay bean names.

`class="com.example.MessageFormatter"` yêu cầu Java class ấy tồn tại trên runtime classpath. Đoạn XML có thể không khởi tạo được nếu class không có constructor phù hợp; phải bổ sung constructor arguments khi cần.

### Khởi động XML context

```java
import org.springframework.context.support.ClassPathXmlApplicationContext;

try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext("beans.xml")) {
    Object bean = context.getBean("formatter");
}
```

Spring tìm `beans.xml` trên classpath. Trong Gradle project chuẩn, đặt file ở `src/main/resources/beans.xml` để nó được đưa vào runtime classpath. `try-with-resources` đóng context sau khi sử dụng và kích hoạt destruction callbacks cho những beans/loại scope được quản lý thích hợp.

## 4. id: tên chính của bean

```xml
<bean id="orderService" class="com.example.OrderService"/>
```

`orderService` là bean name, **không phải Java class name**. Nếu đăng ký thành công, có thể tra:

```java
Object service = context.getBean("orderService");
```

`id` cung cấp **một tên**. Convention nên dùng lower camel case: `orderService`, `customerRepository`, `paymentGateway`. Đặt tên theo chức năng/contract thay vì theo một implementation có thể thay trong tương lai.

### id và class có nhất thiết giống nhau?

Không:

```xml
<bean id="billingGateway"
      class="com.example.adapters.CardPaymentGateway"/>
```

Bean name là `billingGateway`, Java type do `class` khai báo là `CardPaymentGateway`. Consumer có thể tiếp tục tham chiếu id `billingGateway` ngay khi đổi implementation sang một class khác có contract tương thích.

### id có cần duy nhất?

Bean name phải được quản lý không xung đột trong container. Việc hai XML files cùng khai báo `id="billingGateway"` có thể gây bean-definition overriding hoặc lỗi tùy cấu hình và môi trường. **Không dựa vào thứ tự nạp XML để âm thầm chọn một definition**.

Trong Spring XML hiện đại, `id` là kiểu `xsd:string`, không còn các ràng buộc cũ của XML `xsd:ID`. Nhưng đó không phải lý do để đặt dấu phân cách hoặc ký tự khó đọc một cách tùy tiện. Tên ổn định, rõ ràng giúp giảm lỗi trong `ref` và monitoring.

## 5. class: nguồn tạo Java object

`class` trong phần lớn XML bean declarations là **fully qualified class name**:

```xml
<bean id="paymentClient"
      class="com.example.integration.PaymentClient"/>
```

Class phải có trên classpath. Khi dùng constructor-based instantiation, Spring chọn và gọi constructor thích hợp. Với class chỉ có constructor nhận `String endpoint`, phải cung cấp argument:

```xml
<bean id="paymentClient"
      class="com.example.integration.PaymentClient">
    <constructor-arg value="https://api.example.test"/>
</bean>
```

Đây là snippet minh họa, cần có class `PaymentClient` với constructor phù hợp. Endpoint chỉ là chuỗi ví dụ; trong production, URL/credential thường đến từ configuration/secret manager, không hard-code nhạy cảm trong source.

### Những lỗi liên quan class

- Thiếu tên package hoặc đánh sai FQCN.
- Class nằm trong JAR chưa có trên runtime classpath.
- Class là interface/abstract nhưng khai báo như bean sẽ instantiate bằng constructor.
- Constructor tham số bắt buộc nhưng không có `<constructor-arg>`.
- Constructor overload không được phân biệt rõ type/index/name.
- Class có dependency khác chưa được resolve.
- Module Java hạn chế truy cập reflection tới constructor cần dùng.

### Một class, nhiều bean definitions

```xml
<bean id="clientA" class="com.example.Client"/>
<bean id="clientB" class="com.example.Client"/>
```

Hai dòng này tạo **hai bean definitions**, có thể dẫn tới hai singleton instances độc lập. Không gọi chúng là aliases. Chỉ dùng hai definitions nếu cần hai cấu hình/ownership/scope khác nhau.

### Trường hợp class là factory class

```xml
<bean id="client"
      class="com.example.ClientFactory"
      factory-method="create"/>
```

Nếu `ClientFactory.create()` là static factory method hợp lệ, Spring có thể gọi nó để lấy target bean. Lúc đó `class` mô tả **factory class**, không nhất thiết là runtime class của object cuối cùng. Cũng có instance factory methods qua `factory-bean`/`factory-method` và interface `FactoryBean<T>`.

Vì vậy, công thức “`class` luôn bằng `context.getBean(name).getClass()`” không chính xác trong mọi tình huống, đặc biệt khi có factory/proxy.

## 6. name: nhiều định danh trên cùng <bean>

`name` là thuộc tính XML hỗ trợ một hoặc nhiều tên:

```xml
<bean id="formatter"
      name="textFormatter, preferredFormatter"
      class="com.example.MessageFormatter"/>
```

Trong đó:

- `formatter` là id.
- `textFormatter` và `preferredFormatter` là những aliases hợp lệ.
- Chúng **không** tạo thêm `MessageFormatter` object hay `BeanDefinition`.

Spring chấp nhận nhiều tên trong `name` được phân cách bằng **dấu phẩy**, **dấu chấm phẩy** hoặc **khoảng trắng**. Ví dụ:

```xml
<bean id="formatter"
      name="textFormatter; preferredFormatter backupFormatter"
      class="com.example.MessageFormatter"/>
```

Dòng này có ba tên thay thế của bean `formatter`. Nên chọn dấu phẩy hoặc cách trình bày rõ ràng nhất cho đội ngũ, tránh alias list dài không cần thiết.

### Chỉ dùng name, không có id

```xml
<bean name="reportService, legacyReportService"
      class="com.example.ReportService"/>
```

Spring có thể lấy tên chính và aliases từ `name`. Không bắt buộc vừa có `id` vừa có `name`. Tuy nhiên nếu một bean có vai trò công khai trong hệ thống, đặt id tường minh thường dễ đọc hơn.

### Không có id lẫn name

```xml
<bean class="com.example.Helper"/>
```

Container có thể **tự sinh bean name**. Điều đó hợp lệ cho một số cấu hình, nhưng không nên xây integration contract giữa nhiều module dựa trên tên tự sinh: khó nhớ và có thể phụ thuộc metadata/nạp cấu hình. Nếu dùng `ref` hay lookup theo string name, định danh explicit là lựa chọn dễ bảo trì.

## 7. <alias/>: đặt tên ngoài nơi định nghĩa bean

Một XML file khác có thể khai báo:

```xml
<alias name="formatter" alias="externalFormatter"/>
```

Ý nghĩa hai thuộc tính trong phần tử này **khác ý nghĩa `name` trong phần tử `<bean>`**:

- `name="formatter"` là **tên bean đích đang muốn đặt alias**.
- `alias="externalFormatter"` là **tên thay thế được đăng ký**.

Sau khi hai phần tử được nạp vào cùng context:

```xml
<bean id="formatter" class="com.example.MessageFormatter"/>
<alias name="formatter" alias="externalFormatter"/>
```

`context.getBean("externalFormatter")` resolve tới **cùng bean definition** với `context.getBean("formatter")`.

### Alias không phải bean mới

```text
Tên chính: "formatter" ----------------------+
                                              |
Alias từ name: "textFormatter" ---------------+--> BeanDefinition formatter
                                              |         |
Alias từ <alias>: "externalFormatter" --------+         v
                                                     target bean
```

Các tên là những khóa khác nhau để lookup một registration. Alias không phải alias class, Java inheritance, wrapper, proxy, HTTP redirect hoặc copy bean.

### Khi nào <alias/> có giá trị hơn name?

Khi bean ở module A nhưng module B muốn gọi bằng tên riêng **mà không sửa file XML của module A**.

**`core-beans.xml`:**

```xml
<bean id="coreFormatter" class="com.example.Formatter"/>
```

**`report-aliases.xml`:**

```xml
<alias name="coreFormatter" alias="reportFormatter"/>
```

Nạp **cả hai** vào cùng `ApplicationContext` thì report code có thể dùng `reportFormatter`. Snippets này giả định `Formatter` có constructor no-arg phù hợp; trong ví dụ đầy đủ sau, class thực tế có constructor cần tham số và XML sẽ cung cấp.

### Alias chain và cycle

```xml
<bean id="mainClient" class="com.example.Client"/>
<alias name="mainClient" alias="oldClient"/>
<alias name="oldClient" alias="reportClient"/>
```

Spring alias registry có thể resolve alias chain theo canonical name. Nhưng alias nhiều tầng làm việc debug phức tạp; alias cycles hoặc xung đột có thể bị từ chối. Tốt hơn nên có một canonical name và aliases trực tiếp với mục đích rõ ràng.

## 8. Ví dụ hoàn chỉnh Java 17+ với Spring Framework 6.2.9

Demo dùng XML `beans.xml` thuần. Có:

- Một bean `MessageFormatter` được đăng ký bằng `id="formatter"`.
- Hai aliases được khai báo qua `name`.
- Một alias được đăng ký bằng `<alias/>`.
- Một `GreetingClient` constructor-inject formatter **qua alias**.
- Một chương trình Java kiểm tra số definitions, aliases, reference identity và kết quả greeting.

Không cần `@ComponentScan`, Spring Boot hay web server.

### 8.1. Cấu trúc

```text
xml-bean-naming-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── MessageFormatter.java
        │       ├── GreetingClient.java
        │       └── XmlBeanNamingDemo.java
        └── resources/
            └── beans.xml
```

### 8.2. Gradle setup

**`settings.gradle`**

```groovy
rootProject.name = 'xml-bean-naming-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.XmlBeanNamingDemo'
}
```

`spring-context` có những dependency transitive cần thiết cho `ClassPathXmlApplicationContext`, XML BeanDefinitionReader và bean container. Với Java 17+ và Gradle tương thích toolchains, chương trình có thể được compile/run mà không cài Spring Boot.

### 8.3. MessageFormatter

**`src/main/java/demo/MessageFormatter.java`**

```java
package demo;

import java.util.Objects;

public final class MessageFormatter {
    private final String prefix;

    public MessageFormatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String format(String name) {
        return prefix + ", " + name + "!";
    }
}
```

Đây là POJO bình thường không có Spring annotation. Class có constructor nhận `String`, nên XML phải cấp constructor argument.

### 8.4. GreetingClient

**`src/main/java/demo/GreetingClient.java`**

```java
package demo;

import java.util.Objects;

public final class GreetingClient {
    private final MessageFormatter formatter;

    public GreetingClient(MessageFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter);
    }

    public MessageFormatter formatter() {
        return formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

`GreetingClient` chỉ biết dependency Java `MessageFormatter`. Nó không biết bean đó được gọi là `formatter` hay `externalFormatter` trong XML.

### 8.5. XML declarations

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- One bean definition, multiple lookup names. -->
    <bean id="formatter"
          name="textFormatter, preferredFormatter"
          class="demo.MessageFormatter">
        <constructor-arg value="Xin chào"/>
    </bean>

    <!-- Adds a name, NOT another bean definition. -->
    <alias name="formatter" alias="externalFormatter"/>

    <!-- Uses an alias to inject the same managed dependency. -->
    <bean id="greetingClient" class="demo.GreetingClient">
        <constructor-arg ref="externalFormatter"/>
    </bean>

</beans>
```

Có đúng hai `<bean>` elements: `formatter` và `greetingClient`. `name` và `<alias/>` chỉ bổ sung tên cho `formatter`.

### 8.6. Main class

**`src/main/java/demo/XmlBeanNamingDemo.java`**

```java
package demo;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlBeanNamingDemo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            MessageFormatter primary =
                    context.getBean("formatter", MessageFormatter.class);
            MessageFormatter viaName =
                    context.getBean("textFormatter", MessageFormatter.class);
            MessageFormatter viaSecondName =
                    context.getBean("preferredFormatter", MessageFormatter.class);
            MessageFormatter viaAlias =
                    context.getBean("externalFormatter", MessageFormatter.class);

            Set<String> aliases = new HashSet<>(
                    Arrays.asList(context.getAliases("formatter"))
            );

            GreetingClient client =
                    context.getBean("greetingClient", GreetingClient.class);

            System.out.println("bean-definitions="
                    + context.getBeanDefinitionCount());
            System.out.println("id-exists="
                    + context.containsBean("formatter"));
            System.out.println("alias-exists="
                    + context.containsBean("externalFormatter"));

            System.out.println("name-alias-registered="
                    + aliases.contains("textFormatter"));
            System.out.println("second-name-alias-registered="
                    + aliases.contains("preferredFormatter"));
            System.out.println("alias-element-registered="
                    + aliases.contains("externalFormatter"));

            System.out.println("all-names-same-instance="
                    + (primary == viaName
                    && primary == viaSecondName
                    && primary == viaAlias));

            System.out.println("alias-is-definition="
                    + context.containsBeanDefinition("externalFormatter"));
            System.out.println("client-uses-managed-bean="
                    + (client.formatter() == primary));
            System.out.println("greeting=" + client.greet("Spring"));
        }
    }
}
```

### 8.7. Chạy

Từ thư mục `xml-bean-naming-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

Chạy `javac XmlBeanNamingDemo.java` riêng không đủ vì phải compile ba Java files và có Spring dependencies trên classpath. Gradle sẽ đưa cả source và `src/main/resources/beans.xml` vào runtime classpath.

### 8.8. Stdout chương trình

```text
bean-definitions=2
id-exists=true
alias-exists=true
name-alias-registered=true
second-name-alias-registered=true
alias-element-registered=true
all-names-same-instance=true
alias-is-definition=false
client-uses-managed-bean=true
greeting=Xin chào, Spring!
```

Các log của Gradle hoặc logging framework, nếu có, không thuộc mười dòng được in bởi `System.out.println`.

### 8.9. Phân tích kết quả

**`bean-definitions=2`:** Chỉ có hai bean definitions, vì `<alias/>` không đăng ký thêm một definition.

**`id-exists=true`:** `formatter` được đăng ký từ `id`.

**`alias-exists=true`:** `externalFormatter` đã được registry biết là alias.

**`name-alias-registered=true` và `second-name-alias-registered=true`:** `textFormatter` và `preferredFormatter` là những tên từ `name`.

**`alias-element-registered=true`:** `<alias name="formatter" alias="externalFormatter"/>` tạo thêm alias bên ngoài bean definition.

**`all-names-same-instance=true`:** Scope là singleton mặc định; lookup qua cả bốn tên trả cùng object.

**`alias-is-definition=false`:** `containsBeanDefinition("externalFormatter")` không thấy definition mang tên alias. Khác với `containsBean("externalFormatter")` trả true do alias resolution.

**`client-uses-managed-bean=true`:** `<constructor-arg ref="externalFormatter"/>` cấp managed instance cho `GreetingClient`. Alias không cản constructor injection.

**`greeting=Xin chào, Spring!`:** Giá trị `Xin chào` đến từ XML constructor argument; Java method nối với `Spring` rồi thêm dấu chấm than.

## 9. Tên thay thế không đồng nghĩa instance thay thế

Một bean có thể được gọi bằng nhiều aliases nhưng vẫn chỉ có **một definition**:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="legacyClient"/>
<alias name="primaryClient" alias="reportClient"/>
```

Sơ đồ:

```text
"primaryClient" ------+
"legacyClient" -------+--> bean definition: primaryClient
"reportClient" -------+                  |
                                         v
                              singleton instance (nếu singleton)
```

Ngược lại:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<bean id="legacyClient" class="com.example.Client"/>
<bean id="reportClient" class="com.example.Client"/>
```

là **ba bean definitions** và có thể tạo ba managed singleton instances. Đừng copy bean definitions chỉ để giữ tên cũ khi điều cần là alias.

## 10. Alias và scope: singleton so với prototype

Với singleton:

```xml
<bean id="client"
      name="clientAlias"
      class="com.example.Client"
      scope="singleton"/>
```

hai lần gọi `getBean("client")` và `getBean("clientAlias")` trong cùng context thường trả một instance.

Với prototype:

```xml
<bean id="requestBuilder"
      name="builderAlias"
      class="com.example.RequestBuilder"
      scope="prototype"/>

<alias name="requestBuilder" alias="externalBuilder"/>
```

Tất cả names chỉ tới **một prototype definition**; nhưng mỗi lần lookup thông thường tạo prototype mới. Vì vậy:

```java
Object first = context.getBean("requestBuilder");
Object second = context.getBean("externalBuilder");
System.out.println(first == second);  // thông thường false
```

Aliases không “ép singleton” và không giữ reference tới object đã tạo. Chúng chỉ giải quyết tên trước khi BeanFactory áp dụng scope của target definition.

### Prototype được inject vào singleton

Nếu singleton service nhận một prototype bean thông qua `ref` trong constructor, instance prototype đó được tạo khi singleton được dựng và reference ấy thường được giữ suốt vòng đời singleton. Nó không tự thay bằng prototype mới mỗi lần service method chạy. Nếu muốn lookup prototype động, hãy dùng `ObjectProvider<T>`/`Provider<T>` hoặc cơ chế thích hợp, không phụ thuộc alias.

## 11. Tham chiếu qua ref: name và value rất khác nhau

### Constructor injection

```xml
<bean id="repository" class="com.example.Repository"/>
<alias name="repository" alias="primaryRepository"/>

<bean id="service" class="com.example.Service">
    <constructor-arg ref="primaryRepository"/>
</bean>
```

`Service` phải có constructor phù hợp nhận `Repository`. Spring resolve alias `primaryRepository` và đưa bean object vào constructor.

### Dạng lồng <ref/>

```xml
<bean id="service" class="com.example.Service">
    <constructor-arg>
        <ref bean="primaryRepository"/>
    </constructor-arg>
</bean>
```

Có hiệu ứng lookup tương đương trong use case trên.

### Property/setter injection

```xml
<bean id="service" class="com.example.Service">
    <property name="repository" ref="primaryRepository"/>
</bean>
```

Ở đây `name="repository"` là tên **JavaBean property** tương ứng setter của `Service`; `ref="primaryRepository"` là tên bean dependency. Không nhầm `property@name` với `bean@name`.

### Dùng value khi muốn literal

```xml
<constructor-arg value="primaryRepository"/>
```

sẽ cung cấp **chuỗi** `primaryRepository`, không lookup bean. Nếu constructor nhận `Repository`, câu lệnh này có thể tạo lỗi conversion/constructor matching. Đổi thành `ref` khi yêu cầu object dependency.

## 12. Đăng ký aliases giữa nhiều XML files

Một dự án legacy có thể muốn module A định nghĩa bean còn module B cấp tên riêng:

**`shared.xml`**

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="sharedFormatter"
          class="com.example.MessageFormatter"/>
</beans>
```

**`reporting.xml`**

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <alias name="sharedFormatter" alias="reportFormatter"/>
</beans>
```

Hai snippets chỉ minh họa phân tách sources; class `MessageFormatter` cần constructor phù hợp trong dự án thực. Nạp cả hai files vào **cùng context**, ví dụ:

```java
try (ClassPathXmlApplicationContext context =
         new ClassPathXmlApplicationContext(
                 "shared.xml", "reporting.xml")) {
    Object formatter = context.getBean("reportFormatter");
}
```

Đừng tạo hai `ClassPathXmlApplicationContext` độc lập rồi mong aliases từ context này tự được biết ở context kia.

### XML import

Một file root cũng có thể nạp XML con:

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <import resource="shared.xml"/>
    <alias name="sharedFormatter" alias="reportFormatter"/>
</beans>
```

Trong dự án thật, có thể bổ sung namespace/schemaLocation đầy đủ như demo chính. Ý nghĩa: bean definitions và aliases được nạp vào cùng registry.

### Java configuration kết hợp XML

Nếu Java `@Configuration` làm composition root, có thể dùng Spring `@ImportResource("classpath:shared.xml")`. Điều này nhập XML metadata vào cùng context, **không** tạo XML context thứ hai. Aliases trong XML vẫn hoạt động theo bean registry tương ứng.

## 13. XML names so với Java @Bean names

| Cơ chế | Ý nghĩa |
| --- | --- |
| `<bean id="client" class="..."/>` | XML bean definition tên `client`. |
| `<bean id="client" name="legacyClient" class="..."/>` | XML bean tên `client` và alias `legacyClient`. |
| `<alias name="client" alias="externalClient"/>` | Thêm alias ngoài phần tử bean. |
| `@Bean("client")` | Java configuration method cung cấp bean tên `client`. |
| `@Bean({"client", "legacyClient"})` | Java bean với tên chính và alias. |
| `@Component("client")` | Component có tên explicit khi được scan. |

Spring quản lý bean names và aliases ở registry; **nguồn khai báo** khác nhau không nhất thiết tạo bean type khác. Nhưng cùng một tên có thể bị đăng ký qua nhiều nguồn và xung đột.

Không được nghĩ rằng vì một bean có alias trong XML nên Java `@Bean` cùng tên sẽ tự hợp nhất với XML bean đó. Nếu hai nguồn đăng ký **hai definitions**, Spring áp quy tắc name conflicts/overriding. Đặt owner rõ ràng cho mỗi bean.

## 14. API kiểm tra bean và alias khi debug

### getBean(name)

```java
Object target = context.getBean("externalFormatter");
```

Lookup bean name hoặc alias. Với singleton thông thường, alias trả cùng instance với canonical name.

### getBean(name, type)

```java
MessageFormatter target =
        context.getBean("externalFormatter", MessageFormatter.class);
```

Tra bằng tên/alias, đồng thời yêu cầu type phù hợp. Nếu bean không tồn tại có thể gặp `NoSuchBeanDefinitionException`; nếu type sai có thể gặp `BeanNotOfRequiredTypeException`.

### containsBean(name)

```java
boolean present = context.containsBean("externalFormatter");
```

Kiểm tra name/alias có thể resolve tới bean.

### containsBeanDefinition(name)

```java
boolean ownDefinition =
        context.containsBeanDefinition("externalFormatter");
```

Kiểm tra definition **trực tiếp** mang name ấy trong registry hiện tại. Với alias thông thường, kết quả là false dù `containsBean` trả true. Trong parent-child hierarchy, hai methods còn khác nhau về phạm vi lookup.

### getAliases(name)

```java
String[] aliases = context.getAliases("formatter");
```

Có thể liệt kê các tên thay thế của canonical bean. Không dựa vào thứ tự phần tử của mảng để làm hợp đồng; nếu cần output ổn định trong test, sort.

### getBeanDefinitionNames và getBeanDefinitionCount

```java
String[] names = context.getBeanDefinitionNames();
int count = context.getBeanDefinitionCount();
```

Chúng quan sát **bean definitions**, không coi aliases là definitions mới. Trong demo thuần XML có đúng hai top-level `<bean>` nên count là 2.

## 15. Lỗi thường gặp

### Lỗi 1 — Đổi nhầm vị trí id và class

```xml
<bean id="demo.MessageFormatter" class="formatter"/>
```

Bean name và Java class name bị lẫn. Sửa `class` thành FQCN thật, `id` thành tên logic.

### Lỗi 2 — Dùng hai definitions khi chỉ muốn hai names

Hai `<bean>` với class giống nhau có thể tạo hai instances. Nếu thực sự chỉ muốn tên cũ cùng tên mới, dùng `<alias/>` hoặc `name`.

### Lỗi 3 — Alias conflict

Đặt alias `reportService` trong khi một bean khác đã có name `reportService` gây ambiguity/conflict. Rà soát names của toàn context, gồm XML imports, Java config và scanned beans.

### Lỗi 4 — Alias trỏ tới target không hiện diện

Một file aliases được load nhưng bean target không được nạp hoặc bị profile/conditional loại bỏ. Alias không tự tạo definition target. Kiểm tra các nguồn được nạp và actual bean registration.

### Lỗi 5 — Trùng bean definition name

Hai XML files cùng khai báo `id="client"` có thể gây lỗi hoặc overriding tùy cấu hình. Không coi thứ tự files là API ổn định để quyết định implementation.

### Lỗi 6 — Sai ref

`<constructor-arg ref="externalFormater"/>` sai chính tả so với `externalFormatter` làm Spring không resolve dependency. Có thể bắt lỗi ngay bằng integration test tạo context.

### Lỗi 7 — Dùng value thay ref

`value="client"` là literal, `ref="client"` mới lấy bean. Phân biệt theo kiểu tham số Java.

### Lỗi 8 — Constructor không khớp

Nếu class chỉ có constructor `MessageFormatter(String)`, XML `<bean class="demo.MessageFormatter"/>` không đủ thông tin để tạo instance. Khai báo `<constructor-arg value="..."/>`.

### Lỗi 9 — Sai fully qualified class name

Package/class name trong XML khác file Java, hoặc JAR không nằm trên classpath. Xác nhận build output/runtime classpath.

### Lỗi 10 — Tưởng alias thay bean scope

Alias không biến prototype thành singleton và không kéo dài vòng đời. Hai lookup prototype từ hai aliases có thể tạo hai objects khác nhau.

### Lỗi 11 — Nghĩ không có id thì bean không tồn tại

XML có thể dùng `name` hoặc tên sinh tự động. Tuy nhiên với bean cần dùng qua `ref`, định danh explicit giúp code dễ hiểu hơn.

### Lỗi 12 — Tưởng getAliases trả danh sách bean definitions

Aliases là names thay thế, không phải registrations độc lập. Dùng `getBeanDefinitionNames` để xem definitions, `getAliases` để xem names.

### Lỗi 13 — Dùng alias để che hai tài nguyên khác nhau

Nếu `readDatabase` và `writeDatabase` có connection pools khác nhau, đừng tạo alias khiến chúng cùng trỏ một pool chỉ để tránh cấu hình thêm bean. Alias chỉ đúng khi hai tên thật sự đại diện **cùng dependency**.

### Lỗi 14 — Nạp alias trong context độc lập

Một alias tồn tại trong context A không làm context B tự tìm được bean. Cấu hình composition/parent-child đúng ý định; không tự xây context thứ hai trong factory method.

### Lỗi 15 — Nhầm FactoryBean với alias

Tiền tố `&` trong lookup `&factoryName` dùng để yêu cầu **FactoryBean instance** thay vì product, không phải alias thông thường.

### Lỗi 16 — Dùng names mang dữ liệu nhạy cảm

Bean names thường xuất hiện trong logs, error messages và monitoring. Không đặt API tokens, password hoặc credentials làm id/alias.

## 16. Kiểm thử XML definitions và naming

Kiểm thử bean names không chỉ bằng string lookup mà còn bằng identity và số definitions.

- Kiểm tra `containsBean("formatter")` và `containsBean("externalFormatter")`.
- Kiểm tra aliases đều xuất hiện trong `getAliases("formatter")`.
- Kiểm tra `getBeanDefinitionCount()` không tăng chỉ vì thêm `<alias/>`.
- Với singleton, so reference bằng `==` giữa lookup id và alias.
- Với prototype, assert hai lookup là hai instances hợp lệ theo scope, không ép identity.
- Kiểm tra constructor injection qua `ref` bằng behavior của consumer.
- Test context thất bại khi thiếu target bean hoặc class để phát hiện lỗi XML sớm.

### Tình huống test migration

Khi đổi bean name `oldClient` thành `primaryClient`, có thể giữ:

```xml
<bean id="primaryClient" class="com.example.Client"/>
<alias name="primaryClient" alias="oldClient"/>
```

Trong integration test, kiểm tra cả hai names resolve và cùng managed bean (khi singleton). Khi xóa alias cũ, test nên chỉ fail ở những module vẫn dùng tên cũ, giúp lộ dependency cần migrate.

## 17. Bài tập tự luyện

**Bài 1.** Cho XML:

```xml
<bean id="primary" name="secondary,tertiary"
      class="demo.Client"/>
<alias name="primary" alias="legacy"/>
```

Có bao nhiêu bean definitions? Bao nhiêu tên lookup?

**Đáp án:** Một definition, bốn tên: `primary`, `secondary`, `tertiary`, `legacy`.

**Bài 2.** Nếu tạo thêm:

```xml
<bean id="another" class="demo.Client"/>
```

Có phải `another` là alias của `primary` không?

**Đáp án:** Không. Đây là definition thứ hai dù cùng Java class.

**Bài 3.** `<alias name="primary" alias="legacy"/>` làm constructor của bean primary chạy thêm lần nữa không?

**Đáp án:** Không. Alias chỉ đăng ký tên thay thế.

**Bài 4.** Với prototype, `getBean("primary") == getBean("legacy")` luôn true không?

**Đáp án:** Không. Mỗi lookup prototype thông thường tạo instance mới.

**Bài 5.** XML có `<constructor-arg value="legacy"/>`, constructor yêu cầu `Client`. Có đúng không?

**Đáp án:** Không. Phải dùng `ref="legacy"` để lookup bean object.

**Bài 6.** `<property name="client" ref="legacy"/>`: hai `name` có cùng nghĩa không?

**Đáp án:** Không. `property@name` chọn JavaBean property; bean `id`/`alias` đặt tên dependency được `ref` resolve.

**Bài 7.** Spring có thể tạo bean khi không khai báo `id` và `name` không?

**Đáp án:** Có thể tự sinh tên trong một số tình huống. Nhưng tên explicit được khuyến nghị cho bean cần tham chiếu công khai.

**Bài 8.** Tại sao `containsBean("legacy")` có thể true nhưng `containsBeanDefinition("legacy")` false?

**Đáp án:** Vì legacy chỉ là alias, không có definition trực tiếp mang tên ấy.

**Bài 9.** `class` luôn là runtime class của bean từ factory method không?

**Đáp án:** Không. Nếu dùng factory-method/FactoryBean/proxy, declared class có thể là factory class hoặc runtime bean type khác.

**Bài 10.** Có nên đặt alias cho tên `readClient` trỏ tới bean `writeClient` nếu hai clients có policies khác nhau?

**Đáp án:** Không, trừ khi đó thực sự là cùng resource/contract. Alias không phù hợp để đánh đồng hai dependencies cần tách biệt.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — Bean Overview và Naming Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): ý nghĩa `id`, `name`, aliases, `class` và naming conventions.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies.html): `value`, `ref`, constructors, properties.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton và prototype.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): đặt tên và aliases cho Java configuration để đối chiếu.
- [Spring Framework 6.2 API — ClassPathXmlApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html): tạo context từ classpath XML.
- [Spring Framework 6.2 API — BeanFactory](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/BeanFactory.html): lookup theo name/type và `getAliases`.
- [Spring Framework 6.2 API — AliasRegistry](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/AliasRegistry.html): alias registration và canonical name.

**Ghi nhớ:** `id` là tên định danh, `class` mô tả Java type/factory để tạo bean, còn `name` và `<alias/>` cung cấp tên tra cứu thay thế. **Một alias không tạo bean definition hoặc object mới**; số object thật sự do scope và lifecycle quyết định. Khi cấu hình XML lớn lên, hãy giữ một canonical name rõ ràng, chỉ thêm aliases có mục đích và kiểm thử lookup/identity trước khi đổi tên beans.
