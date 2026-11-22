# Phân biệt kế thừa định nghĩa bean với kế thừa lớp Java

## 1. Hai loại “kế thừa” ở hai tầng khác nhau

Trong Spring Core Container, cụm **kế thừa định nghĩa bean** (*bean definition inheritance*) nói đến việc **một bean definition con kế thừa metadata cấu hình từ một bean definition cha**. Đây là cơ chế **tái sử dụng cấu hình của IoC container**: property values, constructor arguments và một số thiết lập khởi tạo có thể được kế thừa rồi bổ sung hoặc ghi đè.

Ngược lại, **kế thừa lớp Java** là quan hệ kiểu được compiler hiểu từ cú pháp `extends` (hoặc quan hệ `implements` với interface). Nó quyết định khả năng tái sử dụng thành viên, subtype và gán tham chiếu theo hệ thống kiểu Java. **Spring không tạo quan hệ `extends` chỉ vì XML có `parent="..."`.**

| Tiêu chí | Kế thừa bean definition | Kế thừa lớp Java |
| --- | --- | --- |
| Thứ được kế thừa | **Metadata** để Spring tạo/cấu hình bean | Thành viên/hành vi và **quan hệ subtype** của kiểu Java |
| Khai báo thường gặp | XML `<bean parent="template">...` hoặc BeanDefinition parent name | `class Child extends Parent` |
| Ai xử lý? | **Spring IoC container** khi merge definitions | **Compiler/JVM** theo ngôn ngữ Java |
| Có cần quan hệ `extends` giữa hai bean classes? | **Không** | Có `extends` cho kế thừa class |
| Có bắt buộc parent definition tạo ra một object? | Không; parent có thể là template `abstract="true"` | Java superclass không nhất thiết được khởi tạo riêng, nhưng constructor superclass tham gia quá trình dựng subclass |
| Có làm bean con chia sẻ object với bean cha? | **Không**; kế thừa cấu hình khác với inject/share instance | Hai instances vẫn có danh tính độc lập, dù thuộc lớp trong cùng cây kiểu |
| Tên “parent” có ý nghĩa gì? | **Bean name** của một definition khác | **Java superclass** được xác định bằng tên kiểu |

**Hai quan hệ độc lập có thể xuất hiện đồng thời, tách rời hoặc không xuất hiện:** Một bean class con của Java có thể được đăng ký bằng bean definition không có `parent`; và hai classes **không liên quan bằng `extends`** có thể cùng kế thừa property metadata từ một parent bean definition.

Mục tiêu bài này: đọc đúng XML `parent`/`abstract`, quan sát cấu hình đã merge, phân biệt việc `getBean` tạo **object** với `getBeanDefinition` trả **metadata**, rồi tự kiểm chứng một Java subclass không kế thừa bean definition.

## 2. Kế thừa bean definition hoạt động như một mẫu cấu hình

Một definition chứa thông tin để container tạo và thiết lập bean. Trong Spring XML, bạn có thể đặt các property dùng chung trong một **template bean definition**:

~~~xml
<bean id="sharedTemplate" abstract="true">
    <property name="endpoint" value="https://api.example.invalid/v1"/>
    <property name="retries" value="3"/>
</bean>
~~~

Đây là **định nghĩa cấu hình**, không phải object Java `SharedTemplate`. Nó cố ý không khai báo `class` và được đánh dấu `abstract="true"`, vì chỉ dùng làm nguồn metadata cho các bean definitions con.

Hai child definitions tham chiếu bằng `parent="sharedTemplate"`:

~~~xml
<bean id="emailSettings" parent="sharedTemplate"
      class="demo.EmailSettings">
    <property name="sender" value="learn@example.invalid"/>
</bean>

<bean id="smsSettings" parent="sharedTemplate"
      class="demo.SmsSettings">
    <property name="retries" value="5"/>
    <property name="provider" value="ExampleSMS"/>
</bean>
~~~

Spring hiểu:

- `emailSettings` nhận `endpoint` và `retries=3` từ template, thêm `sender`.
- `smsSettings` nhận cùng `endpoint`, nhưng **ghi đè `retries` thành 5**, thêm `provider`.
- Class `EmailSettings` và `SmsSettings` **có thể hoàn toàn không có quan hệ kế thừa Java**, miễn mỗi class hỗ trợ các property được áp dụng cho mình.
- Khi container tạo bean con, nó xử lý **merged bean definition**. Parent không trở thành một dependency/object được tiêm vào con.

Điểm khác với mô hình Java: `parent="sharedTemplate"` trỏ đến **tên bean definition**, không trỏ đến `class` hay Java superclass. Bạn có thể giữ nguyên Java classes mà đổi parent/template metadata, và ngược lại.

### Vì sao phải `abstract="true"`?

Một parent definition dùng **chỉ làm mẫu** cần được đánh dấu trừu tượng. Khi parent **không có class**, `abstract="true"` là bắt buộc để nó không bị container xem như bean cần tạo. Ngay cả khi template có `class`, vẫn nên đặt `abstract="true"` nếu bạn **không định cho container tạo instance của parent**.

Với template abstract:
- Container **giữ metadata** để children tham chiếu;
- `containsBeanDefinition("sharedTemplate")` có thể trả `true`;
- **không** thể lấy template như một bean instance bằng `getBean("sharedTemplate")`;
- template không được pre-instantiate như singleton thông thường;
- `abstract="true"` **không tự tạo** một Java `abstract class`.

Trái lại, `abstract class Base` trong Java là ràng buộc của ngôn ngữ; object phải thuộc một concrete subclass. Hai loại `abstract` nằm ở **hai tầng nghĩa khác nhau**.

## 3. Java class inheritance: không cần Spring, không cần parent bean definition

Xem Java thuần:

~~~java
class EmailSettings {
    private int retries;

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }
}

class UrgentEmailSettings extends EmailSettings {
    private String priority;

    public String getPriority() {
        return priority;
    }

    public void setPriority(String priority) {
        this.priority = priority;
    }
}
~~~

`UrgentEmailSettings extends EmailSettings` nghĩa là một `UrgentEmailSettings` **cũng là** một `EmailSettings` theo hệ thống kiểu. Nó kế thừa các member có thể kế thừa, như `getRetries()`/`setRetries()`. Nếu có một object `UrgentEmailSettings`, biểu thức `urgent instanceof EmailSettings` đúng.

Không có XML `parent` nào trong ví dụ Java trên. Spring **không cần** bean definition inheritance để tạo instance của một Java subclass:

~~~xml
<bean id="urgentEmail" class="demo.UrgentEmailSettings">
    <property name="retries" value="2"/>
    <property name="priority" value="HIGH"/>
</bean>
~~~

Nó là một bean definition **độc lập**, dùng trực tiếp class là subclass Java. Property `retries` được thiết lập nhờ method Java kế thừa. Khi đọc raw metadata, `getParentName()` của `urgentEmail` sẽ là `null`.

**Hai phản ví dụ giúp tránh nhầm lẫn:**

- `emailSettings` và `smsSettings` cùng parent **metadata** nhưng `EmailSettings` không extends `SmsSettings` và ngược lại.
- `urgentEmail` dùng Java class `UrgentEmailSettings extends EmailSettings`, nhưng definition của nó **không** có `parent` metadata.

Quan hệ kế thừa Java vẫn tuân theo access control, constructor, override/overload và luật đa hình của Java. Không vì Spring sử dụng reflection hoặc injection mà các luật ấy thay đổi.

## 4. Cái gì được merge, cái gì được override?

Theo Spring Framework, child definition có thể kế thừa **các giá trị constructor arguments, bean properties, method overrides** từ parent và ghi đè/bổ sung chúng. Một số container settings như scope, init method, destroy method hoặc static factory method, khi khai báo rõ ở child, **thay thế** giá trị tương ứng của parent.

| Thuộc tính/metadata | Hành vi cơ bản khi parent/child definitions | Cần thận trọng |
| --- | --- | --- |
| Bean class | Nếu child không chỉ định class, có thể dùng class từ parent; child có thể chỉ định class khác | Class thực phải chấp nhận các property/constructor args đã merge |
| Property values | Kế thừa tên/property từ parent; child có thể ghi đè cùng property và thêm property mới | Nếu setter/type không tương thích, bean creation có thể lỗi |
| Constructor arguments | Có thể được kế thừa, thêm hoặc override theo cơ chế merge | Xác định index/type/name rõ khi nhiều overload |
| Method overrides | Có thể được merge từ parent | Phụ thuộc kiểu và method thực tế |
| Scope | Có thể được kế thừa hoặc ghi đè theo cấu hình | `prototype` không có nghĩa subclass Java |
| Initialization/destroy method | Các settings được child khai báo có thể override parent | Chỉ có ý nghĩa khi method tồn tại trên class thực |
| Static factory method setting | Child có thể thay thế setting của parent | Cần đúng factory/class và chữ ký |
| Một số flags khác | Không phải **mọi cờ** của parent đều tự thừa hưởng: lazy-init, autowire mode, depends-on và các thiết lập khác có quy tắc riêng | Đọc documentation/API theo phiên bản, đừng suy diễn “copy nguyên toàn bộ” |

**Điểm mấu chốt:** Container **không thực thi constructor của một “parent bean object” rồi biến nó thành child object**. Nó giải quyết metadata để biết cách tạo một object cụ thể theo bean definition con. Với parent chỉ là template abstract, **không tồn tại parent instance** để bị “kế thừa”.

**Lưu ý scope và lifecycle:** Một child definition vẫn là một registration có tên và scope riêng. Nếu child dùng singleton, container thường cấp một instance theo **child bean definition trong một context**. Nếu hai child definitions cùng thừa hưởng parent template, điều đó **không** buộc chúng chia sẻ object.

### Raw bean definition và merged bean definition

Spring có hai góc nhìn:

- `getBeanDefinition("smsSettings")`: xem **metadata được đăng ký cục bộ** cho bean con, thường có `parentName="sharedTemplate"` và property `retries=5`, nhưng **không có** property `endpoint` ở chính declaration của child.
- `getMergedBeanDefinition("smsSettings")`: xem **metadata sau khi Spring kết hợp** parent+child. Lúc này property `endpoint` từ template **có mặt** và `retries` phản ánh giá trị override của child.

Các API này phục vụ **debug container configuration**, không phải cách thường dùng trong business service. Business code nên nhận dependency qua constructor/`@Bean` parameters và làm việc với object thực.

## 5. Một dự án Java 17 + Maven quan sát cả hai loại inheritance

Bài chạy trên **Spring Framework 7.0.9**, dùng JDK **17+**, Maven **3.9+**. Chúng ta cố ý dùng **Spring XML** vì nó thể hiện `parent` và `abstract` trực quan. Spring XML vẫn là lựa chọn cấu hình hợp lệ trong Framework; nó **không** bắt buộc dùng Spring Boot và không có HTTP server ở đây.

Cấu trúc dự án:

~~~text
bean-inheritance-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── BeanInheritanceDemo.java
        │       ├── EmailSettings.java
        │       ├── SmsSettings.java
        │       └── UrgentEmailSettings.java
        └── resources/
            └── beans.xml
~~~

Đây là **một project hoàn chỉnh**: mọi source Java phải nằm dưới `src/main/java` đúng package, còn XML dưới `src/main/resources` để Maven đưa `beans.xml` lên runtime classpath.

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-inheritance-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanInheritanceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` mang theo các Spring artifacts nền để chạy `ClassPathXmlApplicationContext` và bean factory. Maven Compiler Plugin dùng `javac` với `--release 17`, Exec Plugin chạy class `main` với đầy đủ dependency classpath. Không cần `spring-boot-starter` hoặc `@SpringBootApplication`.

### 5.2. `src/main/resources/beans.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Chỉ chứa metadata dùng chung; không được tạo bean instance. -->
    <bean id="sharedTemplate" abstract="true">
        <property name="endpoint" value="https://api.example.invalid/v1"/>
        <property name="retries" value="3"/>
    </bean>

    <!-- Không cần extends nhau trong Java để kế thừa metadata. -->
    <bean id="emailSettings" parent="sharedTemplate"
          class="demo.EmailSettings">
        <property name="sender" value="learn@example.invalid"/>
    </bean>

    <bean id="smsSettings" parent="sharedTemplate"
          class="demo.SmsSettings">
        <property name="retries" value="5"/>
        <property name="provider" value="ExampleSMS"/>
    </bean>

    <!-- Có Java extends, nhưng KHÔNG có parent bean definition. -->
    <bean id="urgentEmail" class="demo.UrgentEmailSettings">
        <property name="endpoint" value="https://urgent.example.invalid/v1"/>
        <property name="retries" value="2"/>
        <property name="sender" value="urgent@example.invalid"/>
        <property name="priority" value="HIGH"/>
    </bean>
</beans>
~~~

**Cách đọc:**
- Template `sharedTemplate` không có `class`, vì **child cung cấp class cụ thể**. Nó phải `abstract="true"`.
- Hai bean definitions `emailSettings` và `smsSettings` đều nói `parent="sharedTemplate"`: chúng chia sẻ **metadata**, không phải class Java hoặc object.
- `smsSettings` thay `retries=3` thành `5` trong metadata con.
- `urgentEmail` dùng Java subclass nhưng cố ý không có `parent="..."`. Mọi property trong example được khai báo **trực tiếp** cho bean này.

**Chú ý URL:** Domain `.invalid` là địa chỉ minh họa, không có HTTP request nào được thực hiện. Property `endpoint` chỉ lưu chuỗi ký tự để kiểm tra việc kế thừa/override.

### 5.3. `src/main/java/demo/EmailSettings.java`

~~~java
package demo;

public class EmailSettings {
    private String endpoint;
    private int retries;
    private String sender;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }

    public String getSender() {
        return sender;
    }

    public void setSender(String sender) {
        this.sender = sender;
    }
}
~~~

### 5.4. `src/main/java/demo/SmsSettings.java`

~~~java
package demo;

public class SmsSettings {
    private String endpoint;
    private int retries;
    private String provider;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }
}
~~~

`SmsSettings` **không extends** `EmailSettings`; hai class chỉ cùng có một số setter/property tương thích với mẫu metadata. Đó chính là bằng chứng bean definition inheritance không tạo một cây kiểu Java.

### 5.5. `src/main/java/demo/UrgentEmailSettings.java`

~~~java
package demo;

public class UrgentEmailSettings extends EmailSettings {
    private String priority;

    public String getPriority() {
        return priority;
    }

    public void setPriority(String priority) {
        this.priority = priority;
    }
}
~~~

Class này kế thừa các setter `setEndpoint`, `setRetries`, `setSender` từ `EmailSettings` bằng **Java `extends`**, và có thêm property `priority`. Nó không cần `parent` ở XML để các setter Java ấy hoạt động.

### 5.6. `src/main/java/demo/BeanInheritanceDemo.java`

~~~java
package demo;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class BeanInheritanceDemo {
    private BeanInheritanceDemo() {
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
            var factory = context.getBeanFactory();

            BeanDefinition template =
                    factory.getBeanDefinition("sharedTemplate");
            BeanDefinition emailDefinition =
                    factory.getBeanDefinition("emailSettings");
            BeanDefinition smsDefinition =
                    factory.getBeanDefinition("smsSettings");
            BeanDefinition smsMerged =
                    factory.getMergedBeanDefinition("smsSettings");
            BeanDefinition urgentDefinition =
                    factory.getBeanDefinition("urgentEmail");

            EmailSettings email =
                    context.getBean("emailSettings", EmailSettings.class);
            SmsSettings sms =
                    context.getBean("smsSettings", SmsSettings.class);
            UrgentEmailSettings urgent =
                    context.getBean("urgentEmail", UrgentEmailSettings.class);

            System.out.println("template.registered="
                    + context.containsBeanDefinition("sharedTemplate"));
            System.out.println("template.abstract=" + template.isAbstract());
            System.out.println("email.parent=" + emailDefinition.getParentName());
            System.out.println("sms.parent=" + smsDefinition.getParentName());
            System.out.println("sms.raw.hasEndpoint="
                    + (smsDefinition.getPropertyValues()
                            .getPropertyValue("endpoint") != null));
            System.out.println("sms.merged.hasEndpoint="
                    + (smsMerged.getPropertyValues()
                            .getPropertyValue("endpoint") != null));

            System.out.println("email.endpoint=" + email.getEndpoint());
            System.out.println("email.retries=" + email.getRetries());
            System.out.println("email.sender=" + email.getSender());
            System.out.println("sms.endpoint=" + sms.getEndpoint());
            System.out.println("sms.retries=" + sms.getRetries());
            System.out.println("sms.provider=" + sms.getProvider());

            System.out.println("emailSms.javaInheritance="
                    + EmailSettings.class.isAssignableFrom(SmsSettings.class));
            System.out.println("urgent.javaExtendsEmail="
                    + (urgent instanceof EmailSettings));
            System.out.println("urgent.definitionParent="
                    + (urgentDefinition.getParentName() != null));
            System.out.println("urgent.priority=" + urgent.getPriority());
        }
    }
}
~~~

API liên quan:
- `getBeanDefinition("smsSettings")` lấy **raw definition** có `parentName`, nơi `endpoint` không được khai báo tại child.
- `getMergedBeanDefinition("smsSettings")` cung cấp **merged definition**, có property `endpoint` từ parent template.
- `getBean(...)` lấy **Java object thực** đã được khởi tạo/cấu hình.
- `EmailSettings.class.isAssignableFrom(SmsSettings.class)` kiểm tra subtype **trong Java**; kết quả khác hoàn toàn với quan hệ parent metadata.
- `urgent instanceof EmailSettings` đúng nhờ **Java extends**, trong khi raw bean definition của `urgentEmail` không có parent.

Đây là ví dụ cố ý quan sát API bean factory để giảng dạy. Khi viết code nghiệp vụ thông thường, tránh rải việc đọc `BeanDefinition` hoặc `getBean()` khắp services; ưu tiên dependency injection và cấu hình rõ ràng.

## 6. Chạy Maven và đối chiếu stdout

Chạy trong thư mục `bean-inheritance-demo` chứa `pom.xml`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

Các lệnh `java -version`/`mvn -version` hiển thị thông tin phụ thuộc máy; **không có stdout chuẩn cố định**. Lệnh Maven cuối biên dịch Java bằng `javac` qua Compiler Plugin và chạy main class với thư viện Spring trên classpath.

**16 dòng stdout do chương trình in** (không tính thông báo Maven/logging backend):

~~~text
template.registered=true
template.abstract=true
email.parent=sharedTemplate
sms.parent=sharedTemplate
sms.raw.hasEndpoint=false
sms.merged.hasEndpoint=true
email.endpoint=https://api.example.invalid/v1
email.retries=3
email.sender=learn@example.invalid
sms.endpoint=https://api.example.invalid/v1
sms.retries=5
sms.provider=ExampleSMS
emailSms.javaInheritance=false
urgent.javaExtendsEmail=true
urgent.definitionParent=false
urgent.priority=HIGH
~~~

### Đọc bằng chứng theo nhóm

1. `template.registered=true`, `template.abstract=true`: template tồn tại như metadata; không phải bean object để lấy bằng `getBean("sharedTemplate")`.
2. `email.parent` và `sms.parent`: cả hai definitions chỉ tới **cùng một parent name**.
3. `sms.raw.hasEndpoint=false` nhưng `sms.merged.hasEndpoint=true`: property `endpoint` được **merge từ template**, dù XML child không khai báo lại.
4. Email nhận `retries=3`, SMS nhận `retries=5`: **cùng kế thừa metadata nhưng override độc lập**.
5. `emailSms.javaInheritance=false`: `EmailSettings` và `SmsSettings` không có quan hệ class inheritance mặc dù definitions có cùng parent.
6. `urgent.javaExtendsEmail=true` cùng `urgent.definitionParent=false`: Java inheritance tồn tại **mà không** cần bean definition inheritance.

Lưu ý: `emailSettings` và `smsSettings` có thể được pre-instantiate khi context refresh nếu là singleton không lazy. Đây là **hai registrations riêng**, không có “instance cha” bị chia sẻ. `getBeanDefinition` và `getMergedBeanDefinition` là thao tác trên metadata, không phải truy vấn Java superclass.

## 7. Java `extends` và XML `parent`: các trường hợp thường gặp

| Tình huống | Quan hệ Java `extends`? | Bean definition `parent`? | Kết quả |
| --- | --- | --- | --- |
| `EmailSettings` và `SmsSettings` trong demo | Không | Cùng trỏ đến `sharedTemplate` | Hai classes độc lập, kế thừa chung values cấu hình |
| `UrgentEmailSettings extends EmailSettings`, bean `urgentEmail` | Có | Không | Java subtype; bean definition độc lập |
| Child bean class cùng Java class với template có class | Không cần quan hệ subtype riêng | Có | Có thể tái sử dụng metadata khi class tương thích |
| Child bean class là Java subclass của class template | Có | Có | Có cả hai quan hệ, nhưng là **hai cơ chế khác nhau** |
| Một class có `extends`, không đăng ký Spring bean nào | Có | Không | Java inheritance hoạt động, **không có Spring bean** |
| Một definition child override `class` không chấp nhận parent properties | Không yêu cầu extends | Có, nhưng metadata không phù hợp | Bean creation có thể thất bại vì setter/constructor mismatch |

**Không viết:** “Child bean class bắt buộc extends parent bean class.” Điều kiện đúng là **class dùng để tạo bean con phải tương thích với metadata đã merge**. Nếu template yêu cầu `setEndpoint(String)`, child class cần cách tiếp nhận property `endpoint` phù hợp. Nó có thể làm vậy bằng setter riêng, bằng setter Java kế thừa hoặc cách cấu hình khác được container hỗ trợ.

### Parent bean definition không phải parent `ApplicationContext`

Spring còn có khái niệm **parent application context** trong hệ phân cấp contexts. Đó là **mối quan hệ giữa hai containers**, khác hoàn toàn `parent="sharedTemplate"` trong XML. Đừng thấy từ `parent` rồi suy ra hai cơ chế có cùng cách tra bean hay quản lý scope.

### Bean definition inheritance không đồng nghĩa Java property inheritance

Khi child definition kế thừa một property `retries=3`, nó nhận **giá trị cấu hình** mà container sẽ áp dụng cho object con. Java class của nó **không tự có thêm trường `retries`**: class vẫn phải khai báo/hỗ trợ property ấy. Nếu `SmsSettings` không có `setRetries` hoặc cơ chế binding tương ứng, không thể kỳ vọng XML tạo thêm field vào bytecode.

## 8. Thêm một ví dụ không cần XML để hiểu ranh giới

Kế thừa lớp Java tự hoạt động trong chương trình hoàn toàn không dùng Spring:

~~~java
// File Java độc lập: PureJavaInheritance.java
public class PureJavaInheritance {
    static class BasePolicy {
        int retries() {
            return 3;
        }
    }

    static class UrgentPolicy extends BasePolicy {
        @Override
        int retries() {
            return 5;
        }
    }

    public static void main(String[] args) {
        BasePolicy ordinary = new BasePolicy();
        BasePolicy urgent = new UrgentPolicy();

        System.out.println("ordinary=" + ordinary.retries());
        System.out.println("urgent=" + urgent.retries());
        System.out.println("isSubclass=" + (urgent instanceof BasePolicy));
    }
}
~~~

**Lệnh chạy Java 17+ không cần Maven hay Spring** (đứng tại thư mục chứa file):

~~~bash
javac PureJavaInheritance.java
java PureJavaInheritance
~~~

**Stdout chính xác:**

~~~text
ordinary=3
urgent=5
isSubclass=true
~~~

Ở đây Java `extends` và **dynamic method dispatch** giải thích toàn bộ kết quả. Không có `ApplicationContext`, `BeanDefinition`, `parent="..."`, XML hay container. Nếu muốn sử dụng `UrgentPolicy` như một Spring bean, bạn **còn phải đăng ký nó** bằng một cơ chế phù hợp.

**Liên hệ hai ví dụ:** Java inheritance chủ yếu phục vụ quan hệ kiểu/hành vi; Spring bean definition inheritance chủ yếu phục vụ tái sử dụng metadata khi tạo một hoặc nhiều bean. Tránh dùng một cơ chế như thể nó tự thực hiện cả hai.

## 9. Những lỗi thường gặp khi cấu hình kế thừa bean definition

| Triệu chứng hoặc suy luận sai | Nguyên nhân/cách hiểu đúng |
| --- | --- |
| `getBean("sharedTemplate")` báo lỗi | Template đã `abstract="true"`, không phải bean để instantiate |
| Quên `abstract="true"` trên template không có class | Context có thể cố xử lý một bean thiếu class/factory, dẫn đến lỗi khi bootstrap |
| Child chỉ định `parent="sharedTemplate"` nhưng tên không tồn tại | Parent bean definition chưa được đăng ký hoặc tên tham chiếu sai |
| Child đổi class nhưng thiếu setter của property kế thừa | Metadata sau merge không tương thích với Java class được tạo |
| Nghĩ `parent="..."` tạo Java `extends` | XML không sửa type hierarchy hay bytecode |
| Nghĩ Java `extends` tự truyền bean properties từ một Spring definition khác | Java kế thừa member, còn Spring metadata cần khai báo/merge riêng |
| Nghĩ hai children cùng parent nên chia sẻ instance | Chúng có bean definitions/scopes riêng |
| Đọc raw `getBeanDefinition` thấy thiếu property rồi kết luận config sai | Kiểm tra **merged definition** hoặc instance; child có thể nhận property từ parent |
| Cho rằng mọi flag như lazy-init đều kế thừa y nguyên | Mỗi nhóm metadata có quy tắc merge/override riêng |
| Dùng `abstract="true"` mà đòi gọi `getBean` trên template | Template abstract được thiết kế để kế thừa, không dùng như một instance |
| Nhầm parent definition với parent context | Một cái là metadata relationship; cái kia là hierarchy giữa IoC containers |
| Lạm dụng inheritance XML nhiều tầng | Cấu hình khó đọc/khó dự đoán override, nên cân nhắc cách biểu đạt đơn giản hơn |

**Khi debug:** kiểm tra tên parent, cách đăng ký XML, `getParentName()`, dữ liệu raw/merged, class thực và setter tương thích, scope/lazy và toàn bộ exception cause. Tránh sửa nhiều thứ cùng lúc hoặc tự bật bean-definition overriding để che lỗi.

### Khi nào nên dùng, khi nào không?

Bean definition inheritance hữu ích khi nhiều beans chia sẻ phần cấu hình **thực sự giống nhau**, đặc biệt ở hệ thống XML có metadata lặp lại. Nhưng nó tạo quan hệ cấu hình ngầm: thay đổi template có thể ảnh hưởng tất cả children, nên cần tài liệu và test.

Với dự án Java configuration hiện đại, có thể tái sử dụng cấu hình bằng factory methods, tham số hóa và component composition thay vì cố ép một mô hình XML inheritance vào mọi chỗ. Các phương thức `@Bean` trong Java configuration **không tự** có `parent` metadata chỉ vì Java config class sử dụng `extends`. Chọn cơ chế rõ ràng nhất cho nhóm và yêu cầu hệ thống.

## 10. Bài tập dự đoán trước khi chạy

Thực hiện từng thay đổi trên bản sao sạch, khôi phục XML/source gốc giữa các bài để so stdout:

1. Đổi `sharedTemplate.retries` từ `3` thành `8`. Dự đoán `email.retries=8` nhưng `sms.retries=5` vẫn giữ override.
2. Thêm property `enabled=true` vào template nhưng **không** thêm setter tương ứng trong `EmailSettings` và `SmsSettings`. Giải thích vì sao bean creation có thể fail thay vì Java classes tự sinh thêm field.
3. Bỏ `parent="sharedTemplate"` của `emailSettings`. Dự đoán `email.endpoint` và `email.retries` nếu chúng không được khai báo riêng (Java defaults).
4. Bỏ `abstract="true"` khỏi template không có class. Quan sát lỗi cấu hình khi context cố xử lý template.
5. Đổi `SmsSettings` thành Java subclass của `EmailSettings` nhưng giữ nguyên XML. Nêu rõ phần nào trong kết quả là thay đổi của Java subtype, phần nào vẫn là metadata merge.
6. Cho `urgentEmail` thêm `parent="sharedTemplate"` và bỏ các property trùng. Dự đoán cả hai cơ chế kế thừa hoạt động đồng thời, nhưng parent XML vẫn không phải Java superclass.
7. Đổi `smsSettings` thành scope `prototype`, gọi `getBean` hai lần; phân biệt **số instance** và metadata template dùng chung.
8. Dùng `getMergedBeanDefinition("smsSettings")` quan sát giá trị `retries` sau override so với raw definition.
9. Tạo một child khác dùng `parent="sharedTemplate"` nhưng class không có `setEndpoint`. Dự đoán exception khi apply inherited property.
10. Đổi `UrgentEmailSettings extends EmailSettings` thành một class không extends nhưng vẫn khai báo setters giống nhau; dự đoán kết quả `instanceof EmailSettings` thay đổi, còn parent metadata của definition (không có) vẫn giữ nguyên.

### Checklist đạt bài

- [ ] Nói được **bean definition inheritance = kế thừa metadata cấu hình**, Java inheritance = kế thừa thành viên/quan hệ subtype.
- [ ] Giải thích được XML `parent`, `abstract="true"`, property override, raw và merged definitions.
- [ ] Chỉ ra vì sao hai classes không `extends` nhau vẫn cùng kế thừa bean template.
- [ ] Chỉ ra một Java subclass có thể làm Spring bean **không có** parent bean definition.
- [ ] Biết parent abstract template **không** được lấy làm bean instance.
- [ ] Biết Spring không tự thêm Java setter/field khi kế thừa property metadata.
- [ ] Phân biệt `getBeanDefinition`, `getMergedBeanDefinition` và `getBean`.
- [ ] Chạy được cả Maven demo Spring (16 dòng stdout) và Java thuần (3 dòng stdout) theo Java 17+.

## 11. Tóm tắt và tài liệu tra cứu

**Một câu phân biệt:** Bean definition inheritance tái sử dụng **“công thức cấu hình”**; Java class inheritance tái sử dụng **“kiểu và hành vi chương trình”**. Chúng có thể kết hợp nhưng **không thay thế nhau**.

- XML `parent="sharedTemplate"` kế thừa property values và các metadata phù hợp để tạo **bean con**.
- `abstract="true"` trên template dành cho definition **không được instantiate riêng**; nó không có nghĩa bean class là Java `abstract class`.
- `class UrgentEmailSettings extends EmailSettings` là quan hệ **Java subtype**, không bắt buộc có parent bean definition.
- Child có thể override giá trị cấu hình mà **không** override một phương thức Java nào; ngược lại, Java override method không tự đổi XML property.
- Dùng `getMergedBeanDefinition` khi cần quan sát metadata sau hợp nhất, thay vì nhầm raw child metadata là cấu hình cuối cùng.

Tài liệu chính thức:
- [Spring Framework – Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html)
- [Spring Framework – Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring Framework – XML-based Metadata](https://docs.spring.io/spring-framework/reference/core/beans/basics.html)
- [Spring – Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html)
- [Spring – Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Java Language Specification – Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Kết luận:** Khi thấy một `parent` trong cấu hình Spring, hãy hỏi đó là **parent bean definition** hay **Java superclass**. Chỉ khi tách đúng hai mối quan hệ, bạn mới dự đoán chính xác cách Spring merge cấu hình, tạo bean, áp dụng setters và phân biệt metadata với object thực.