# Định nghĩa trừu tượng và hợp nhất cấu hình kế thừa trong Spring Core Container

## 1. Vấn đề: nhiều bean có chung cấu hình nhưng vẫn phải khác nhau

Trong cấu hình Spring XML, đôi khi nhiều bean có các thông số nền giống nhau: cách khởi tạo, các giá trị property, một số argument hoặc thiết lập vòng đời. Nếu sao chép toàn bộ mỗi `<bean>`, khi sửa một thông số chung rất dễ quên cập nhật một bản.

Spring Core Container hỗ trợ **kế thừa bean definition** (*bean definition inheritance*). Một bean definition con khai báo `parent="tênBeanCha"` để dùng lại metadata của định nghĩa cha, sau đó có thể bổ sung hoặc ghi đè những phần riêng. Một bean definition cha dùng thuần túy làm **mẫu cấu hình** thường được đánh dấu `abstract="true"`.

Điểm cần nhớ ngay từ đầu:

- **Parent bean definition** là **mẫu metadata** dùng để tạo ra các bean definition hoàn chỉnh.
- **Child bean definition** kế thừa và hợp nhất metadata từ cha khi container xử lý cấu hình.
- **Bean instance** của child là một object được tạo theo metadata cuối cùng đã hợp nhất.
- `abstract="true"` trên XML `<bean>` **không** đồng nghĩa class Java của bean phải được khai báo `abstract class`.
- `parent` trong XML **không** có nghĩa `extends` trong Java, và cũng **không** phải thuộc tính `parent ApplicationContext`.

Ví dụ ý tưởng:

~~~xml
<bean id="baseConfig" abstract="true"
      class="demo.AlertConfiguration">
    <property name="prefix" value="BASE"/>
</bean>

<bean id="emailConfig" parent="baseConfig">
    <property name="channel" value="email"/>
</bean>

<bean id="smsConfig" parent="baseConfig">
    <property name="channel" value="sms"/>
</bean>
~~~

Đây là **XML minh họa**, tên class trong đoạn này không thuộc chương trình chạy ở mục 6. Khi bean definition được hợp nhất, cả hai child kế thừa `prefix=BASE` nhưng có `channel` khác nhau. Cha đóng vai trò template, không phải một object nghiệp vụ được inject.

### Mô hình xử lý

~~~text
        parent bean definition
         id=baseTemplate
         abstract=true
         prefix=BASE
         tags=[audit, core]
                  |
          +-------+---------+
          |                 |
          v                 v
   emailConfig child   smsConfig child
   channel=email       channel=sms
   tags merge=true     tags replace
          |                 |
          v                 v
  merged definition   merged definition
          |                 |
          v                 v
  emailConfig object  smsConfig object
~~~

Spring hợp nhất **định nghĩa trước**, rồi sử dụng định nghĩa hiệu lực để tạo instance con. Mỗi child có thể có scope và lifecycle của riêng nó; **không có một instance cha bắt buộc phải được tạo trước**.

## 2. Phân biệt ba loại “kế thừa” hay bị nhầm

| Khái niệm | Quan hệ | Điều được kế thừa/chia sẻ |
| --- | --- | --- |
| **Java class inheritance** | `class Child extends Parent` | Trường/method và quy tắc Java OOP |
| **Spring bean definition inheritance** | `<bean parent="baseTemplate">` | Cấu hình container: constructor args, property values, scope và các metadata thích hợp |
| **ApplicationContext hierarchy** | context con có parent context | Khả năng tìm bean trong context cha và quan hệ container theo cấu hình |

Không được dùng chúng như ba cách viết cùng một việc.

Ví dụ class `EmailConfig` có thể hoàn toàn **không extends** class `BaseConfig` nhưng bean definition của nó vẫn có `parent="baseTemplate"`, miễn class cuối cùng có thể chấp nhận các property/argument được kế thừa. Ngược lại, `class EmailConfig extends BaseConfig` **không tự tạo** quan hệ XML `parent`.

Kế thừa metadata còn có thể xảy ra khi cả cha và con đều dùng **cùng class Java**, tạo ra hai bean với cấu hình khác nhau. Đây chính là cách bài thực hành dùng: hai child đều tạo class `AlertConfig`, không cần viết các Java subclass chỉ để đổi property.

**Không nhầm với DI:** `parent="baseTemplate"` không truyền bean cha vào constructor của bean con. Nếu một service cần collaborator thật, hãy dùng `<constructor-arg ref="..."/>`, `<property ref="..."/>` hoặc constructor injection tương ứng.

## 3. Khai báo parent bean definition trừu tượng

### 3.1. Ý nghĩa của `abstract="true"`

~~~xml
<bean id="baseTemplate"
      class="demo.AlertConfig"
      abstract="true">
    <property name="prefix" value="BASE"/>
</bean>
~~~

Ở đây `baseTemplate` là một **bean definition trừu tượng**, dùng làm template. Container giữ metadata của nó, nhưng không cho phép tra cứu đối tượng cha như một bean có thể khởi tạo:

~~~java
context.getBean("baseTemplate"); // Không hợp lệ đối với abstract bean definition.
~~~

Dòng trên là minh họa; nó có thể ném `BeanIsAbstractException`. Đây không phải một `null` hay một instance được tạo rỗng để dùng tạm. Khi Spring pre-instantiate singleton trong quá trình `ApplicationContext.refresh()`, **abstract bean definitions không được tạo như singleton thông thường**.

Nếu chỉ muốn template mà **không** đặt `abstract="true"`, container có thể cố gắng khởi tạo bean cha như một bean thông thường, đặc biệt khi đó là singleton non-lazy. Nếu template thiếu các property/argument thiết yếu, khởi tạo sẽ thất bại; nếu có thể khởi tạo thì lại có thêm một instance không mong muốn.

### 3.2. Parent có thể không có class

~~~xml
<bean id="commonDefaults" abstract="true">
    <property name="prefix" value="BASE"/>
    <property name="channel" value="general"/>
</bean>

<bean id="childConfig"
      parent="commonDefaults"
      class="demo.AlertConfig"/>
~~~

Đoạn XML minh họa một template chỉ mang metadata, **không chỉ định `class`**. Trong trường hợp đó **bắt buộc khai báo parent là abstract**, bởi parent tự thân không đủ thông tin để được tạo. Child chỉ định class phù hợp để cung cấp cách dựng instance.

Nếu parent đã có class, child có thể **kế thừa class ấy** mà không khai báo lại `class`. Child cũng có thể chỉ định class khác, nhưng class mới phải hỗ trợ những property/constructor arguments mà metadata cuối cùng yêu cầu.

**Abstract bean definition khác abstract Java class.** Một Java `abstract class` không thể được khởi tạo trực tiếp; XML `abstract="true"` quyết định một **bean definition** chỉ được dùng làm template, kể cả khi bean class Java là concrete.

### 3.3. Có thể dùng cha không abstract không?

Về mặt cơ chế, một bean definition bình thường cũng có thể là parent. Tuy nhiên nếu mục tiêu của nó **chỉ** là mẫu chung, nên đánh dấu abstract để tránh container tạo một singleton parent không cần thiết. Khi class cha có side effect khởi tạo, việc quên đánh dấu abstract có thể gây kết nối, đọc file hoặc lỗi khởi động không mong muốn.

Không tự ý chuyển một bean nghiệp vụ thực sự đang được dùng thành abstract: mọi chỗ `getBean("parent")` hoặc `ref` đến bean ấy sẽ không còn hoạt động.

## 4. Spring hợp nhất những phần metadata nào?

Một child declaration được container **hợp nhất** với định nghĩa cha. Không nên hình dung đơn giản là copy XML nguyên văn.

### 4.1. Những phần child thường kế thừa hoặc ghi đè

Các phần quan trọng có thể được kế thừa từ parent, sau đó child có thể bổ sung/ghi đè:

- **Bean class**: nếu child không chỉ định, có thể lấy class từ parent.
- **Constructor argument values**: child có thể kế thừa những giá trị định nghĩa ở cha, hoặc định nghĩa thêm/ghi đè phù hợp với chỉ số, tên và cách Spring giải quyết argument.
- **Property values**: property chưa khai báo ở child được giữ từ parent; nếu child định nghĩa lại cùng property, giá trị child thường có ưu tiên.
- **Method override metadata** ở bean definition và một số thiết lập phù hợp khác.
- **Scope**: child có thể kế thừa scope nếu không chỉ định; nếu chỉ định `scope` khác thì child dùng scope mới.
- **Lifecycle/factory settings**: phương thức khởi tạo/hủy hoặc factory method có thể được khai báo ở child để ghi đè metadata tương ứng.

Spring có các quy tắc riêng cho metadata luôn lấy từ child definition, ví dụ cấu hình `depends-on`, autowire mode, lazy initialization và các thiết lập khác tùy loại bean definition. **Không tự suy diễn rằng mọi thuộc tính XML đều được inherit/merge bằng một quy tắc giống nhau.** Đặc biệt, hãy kiểm tra lại khi trộn `lazy-init` hoặc `depends-on` với parent-child.

### 4.2. Cấu hình property đơn giản: kế thừa và ghi đè

~~~xml
<bean id="parentTemplate"
      abstract="true"
      class="demo.AlertConfig">
    <property name="prefix" value="BASE"/>
    <property name="channel" value="general"/>
</bean>

<bean id="emailConfig" parent="parentTemplate">
    <property name="channel" value="email"/>
</bean>
~~~

Bean `emailConfig` sau merge có `prefix=BASE` từ cha nhưng `channel=email` từ con. Child không tạo một object cha rồi sửa trực tiếp object đó; container xây dựng **metadata cuối** cho bean con.

### 4.3. Constructor arguments cần nhất quán

Với XML như:

~~~xml
<bean id="baseClient" abstract="true"
      class="demo.Client">
    <constructor-arg index="0" value="localhost"/>
</bean>

<bean id="remoteClient" parent="baseClient">
    <constructor-arg index="1" value="443"/>
</bean>
~~~

Đây là **ví dụ minh họa**, giả định class `demo.Client` có constructor tương ứng. Child kế thừa argument index 0, thêm argument index 1, nên constructor phù hợp phải chấp nhận cả hai. Khi parent/child khai báo argument theo type/name/index khác nhau, cần kiểm tra chính xác cách argument được hợp nhất và lựa chọn overload; không nên trông chờ Spring tự hiểu ý nghiệp vụ nếu constructor mơ hồ.

### 4.4. Bảng cách hiểu metadata

| Thuộc tính | Cách diễn giải an toàn |
| --- | --- |
| `class` | Child có thể dùng class cha hoặc thay class phù hợp |
| `constructor-arg` | Kế thừa/bổ sung/ghi đè argument theo thông tin định danh phù hợp |
| `property` | Giá trị property cha còn hiệu lực nếu child không ghi đè |
| `scope` | Có thể kế thừa scope hoặc đặt scope khác ở child |
| `init-method` / `destroy-method` | Có thể ghi đè cấu hình lifecycle phù hợp |
| `abstract` | Parent dùng làm template không được instantiable; child concrete cần hoàn chỉnh |
| `depends-on`, `lazy-init`, `autowire` | Không mặc định coi là kế thừa như property; tuân quy tắc metadata bean definition của Spring |
| `<list>`/`<set>`/`<map>`/`<props>` | Nếu cùng property được khai báo lại, muốn merge collection cần cấu hình `merge="true"` **ở child** |

## 5. Collection merging: phần khác biệt cần học riêng

### 5.1. Mặc định: thay thế, không tự ghép

Giả sử parent định nghĩa:

~~~xml
<property name="tags">
    <list>
        <value>audit</value>
        <value>core</value>
    </list>
</property>
~~~

Child cũng khai báo property `tags`:

~~~xml
<property name="tags">
    <list>
        <value>sms</value>
    </list>
</property>
~~~

Nếu không bật merge ở child, định nghĩa list mới **ghi đè** list cũ: child nhận `[sms]`, không phải `[audit, core, sms]`.

**Lưu ý:** nếu child **không khai báo lại** property `tags`, nó đơn giản **kế thừa nguyên property từ cha**; đó không phải hành vi merge hai collection.

### 5.2. Bật `merge="true"` ở collection của child

~~~xml
<property name="tags">
    <list merge="true">
        <value>mail</value>
    </list>
</property>
~~~

Khi parent có `[audit, core]` và child có `[mail]` với `merge="true"`, Spring tạo kết quả `[audit, core, mail]`. **Thứ tự List được giữ**, parent elements xuất hiện trước child elements.

Với `<set>`, `<map>` và `<props>`, Spring cũng hỗ trợ merge cùng loại:

- **List**: nối các phần tử parent trước, child sau; vị trí có ý nghĩa.
- **Set**: hợp nhất phần tử theo semantics Set, loại trùng theo equality; không nên dựa vào thứ tự không được hứa.
- **Map**: hợp nhất các entry; khi cùng key, giá trị child ghi đè giá trị parent.
- **Properties (`<props>`)**: như map key–value string; key ở child ghi đè key trùng từ parent.

Ví dụ:

~~~xml
<property name="routes">
    <props merge="true">
        <prop key="support">support-new@demo.test</prop>
        <prop key="sales">sales@demo.test</prop>
    </props>
</property>
~~~

Nếu parent có `support=support-old@demo.test` và `ops=ops@demo.test`, child sẽ có ba key: `ops` kế thừa, `support` ghi đè, `sales` được thêm.

### 5.3. Các giới hạn quan trọng

1. `merge="true"` phải đặt trên **phần tử collection ở định nghĩa con**. Đặt ở parent không có ý nghĩa “tự merge mọi child” mong muốn.
2. Hai collection cần thuộc **kiểu tương thích** để merge; không thể trộn `<map>` với `<list>` rồi kỳ vọng Spring chuyển đổi tùy ý.
3. Merge không áp dụng chung cho mọi property scalar. Với `<value>email</value>`, child đơn giản ghi đè giá trị scalar cha.
4. Đừng gọi đây là “deep merge tổng quát mọi object”. Spring áp dụng merge theo cơ chế managed collection metadata của bean definition.
5. Không trông chờ thứ tự duyệt `Properties`, `Map` hoặc `Set` giống một List. Nếu stdout cần xác định, **lấy từng key cụ thể**, không in nguyên map.
6. Merge theo parent-child bean definitions có tác dụng tại lúc container dựng metadata/instance, không phải thuật toán đồng bộ danh sách runtime giữa hai object.

Ví dụ runnable sau minh họa **cả replacement của List lẫn merging List/Properties** trong cùng một context.

## 6. Ví dụ Java 17 + Spring Framework 6.2: parent abstract, child và merge thực tế

Ví dụ chạy bằng **XML bean definitions**, vì `parent`, `abstract` và `merge` được thể hiện trực tiếp bằng cú pháp XML của Spring. Trong dự án Java configuration hiện đại, `@Configuration`/`@Bean` thường biểu đạt composition hoặc dùng chung factory khác; không nên giả định có một annotation `@Bean(parent="...")` tương đương.

### 6.1. Cấu trúc thư mục

Yêu cầu JDK 17+, Maven và quyền tải dependency Maven lần đầu:

~~~text
bean-inheritance-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── TemplateInheritanceDemo.java
        └── resources/
            └── beans.xml
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>bean-inheritance-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.TemplateInheritanceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File Java đầy đủ

Lưu `src/main/java/demo/TemplateInheritanceDemo.java`:

~~~java
package demo;

import java.util.List;
import java.util.Properties;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class TemplateInheritanceDemo {
    private TemplateInheritanceDemo() {}

    public static final class AlertConfig {
        private String prefix;
        private String channel;
        private List<String> tags = List.of();
        private Properties routes = new Properties();

        // Constructor công khai cho Spring property injection qua setter.
        public AlertConfig() {}

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }

        public void setChannel(String channel) {
            this.channel = channel;
        }

        public void setTags(List<String> tags) {
            this.tags = tags;
        }

        public void setRoutes(Properties routes) {
            this.routes = routes;
        }

        public String summary() {
            return channel + "|" + prefix + "|" + tags;
        }

        public String route(String key) {
            return routes.getProperty(key);
        }
    }

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            boolean parentAbstract = context.getBeanFactory()
                    .getBeanDefinition("baseTemplate").isAbstract();
            System.out.println("PARENT_ABSTRACT " + parentAbstract);

            AlertConfig email =
                    context.getBean("emailConfig", AlertConfig.class);
            AlertConfig sms =
                    context.getBean("smsConfig", AlertConfig.class);

            System.out.println("EMAIL " + email.summary());
            System.out.println("EMAIL_ROUTES "
                    + email.route("ops") + "|"
                    + email.route("support") + "|"
                    + email.route("sales"));

            System.out.println("SMS " + sms.summary());
            System.out.println("SMS_ROUTES "
                    + sms.route("ops") + "|"
                    + sms.route("support"));

            System.out.println("DIFFERENT " + (email != sms));
        }
    }
}
~~~

`AlertConfig` có các setter public tương ứng các property khai báo trong XML. Class này **không kế thừa class Java nào được định nghĩa trong ví dụ**; chỉ chính bean definitions mới có quan hệ parent–child.

### 6.3. File XML hoàn chỉnh

Lưu `src/main/resources/beans.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Chỉ là template: không tạo baseTemplate instance -->
    <bean id="baseTemplate"
          class="demo.TemplateInheritanceDemo$AlertConfig"
          abstract="true">

        <property name="prefix" value="BASE"/>
        <property name="channel" value="general"/>

        <property name="tags">
            <list>
                <value>audit</value>
                <value>core</value>
            </list>
        </property>

        <property name="routes">
            <props>
                <prop key="ops">ops@demo.test</prop>
                <prop key="support">support-old@demo.test</prop>
            </props>
        </property>
    </bean>

    <!-- Kế thừa class, prefix; override channel;
         merge list tags và Properties routes. -->
    <bean id="emailConfig" parent="baseTemplate">
        <property name="channel" value="email"/>

        <property name="tags">
            <list merge="true">
                <value>mail</value>
            </list>
        </property>

        <property name="routes">
            <props merge="true">
                <prop key="support">support-new@demo.test</prop>
                <prop key="sales">sales@demo.test</prop>
            </props>
        </property>
    </bean>

    <!-- Kế thừa class và routes; override scalar;
         list mới KHÔNG merge nên thay list của cha. -->
    <bean id="smsConfig" parent="baseTemplate">
        <property name="channel" value="sms"/>
        <property name="prefix" value="SHORT"/>
        <property name="tags">
            <list>
                <value>sms</value>
            </list>
        </property>
    </bean>
</beans>
~~~

### 6.4. Lệnh biên dịch, chạy

Mở PowerShell/CMD hoặc terminal Linux/macOS tại thư mục `bean-inheritance-demo`:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

**Stdout do chương trình in theo đúng thứ tự:**

~~~text
PARENT_ABSTRACT true
EMAIL email|BASE|[audit, core, mail]
EMAIL_ROUTES ops@demo.test|support-new@demo.test|sales@demo.test
SMS sms|SHORT|[sms]
SMS_ROUTES ops@demo.test|support-old@demo.test
DIFFERENT true
~~~

Maven và thư viện có thể phát sinh log riêng, đặc biệt khi tải dependency; khối trên chỉ là **stdout từ các lệnh `System.out.println` do chương trình tạo**, không khẳng định toàn bộ terminal luôn chỉ có sáu dòng.

### 6.5. Từng dòng stdout chứng minh điều gì?

1. `PARENT_ABSTRACT true`: metadata của `baseTemplate` có cờ abstract; `getBeanFactory().getBeanDefinition(...)` chỉ kiểm tra metadata, **không tạo instance parent**.
2. `EMAIL email|BASE|[audit, core, mail]`: `emailConfig` ghi đè channel từ `general` thành `email`, kế thừa prefix `BASE` và merge list parent trước child.
3. `EMAIL_ROUTES ...`: key `ops` được kế thừa, key `support` lấy giá trị mới từ child, key `sales` được bổ sung. Code truy cập đúng key nên không phụ thuộc thứ tự duyệt `Properties`.
4. `SMS sms|SHORT|[sms]`: `smsConfig` ghi đè prefix và channel, khai báo list mới **không `merge="true"`**, do đó list cha bị thay.
5. `SMS_ROUTES ...`: child không khai báo property routes, nên kế thừa trực tiếp các giá trị routes của parent, trong đó `support` vẫn là giá trị cũ.
6. `DIFFERENT true`: hai bean con là **hai instance khác nhau**. Cùng sử dụng class `AlertConfig` và một parent template không khiến chúng trở thành cùng một bean.

Đầu ra được thiết kế **không phụ thuộc thứ tự tạo singleton**: không có `println` trong constructor/setter, và cả hai child đều được tra cứu rõ bằng bean name.

### 6.6. Thử biến thể để tự quan sát

- Xóa `merge="true"` ở list của `emailConfig`: list email dự kiến thành `[mail]`.
- Đặt `merge="true"` ở `<props>` của parent nhưng bỏ ở child: không đạt hiệu ứng merge mong muốn; child properties mới thay định nghĩa cũ.
- Bỏ `abstract="true"` ở parent: container có thể tạo thêm bean `baseTemplate` vì class có thể khởi tạo; bạn đã đánh mất vai trò template-only.
- Thử `context.getBean("baseTemplate")` **trong khối try/catch ở bản thực hành**: sẽ thất bại vì đó là abstract definition. Không thêm lệnh này vào ví dụ chính nếu vẫn muốn giữ stdout đúng như đã công bố.
- Đổi `class` của child sang một class khác thiếu `setTags`: metadata vẫn kế thừa `tags` nhưng quá trình set property có thể thất bại. Spring không tự biến class mới thành compatible với cấu hình cũ.

## 7. Định nghĩa chương trình bằng API BeanDefinition

Cấu hình XML là hình thức trực quan. Ở mức API, Spring dùng `BeanDefinition` và các kiểu cài đặt như `ChildBeanDefinition` để biểu diễn quan hệ parent–child trong những trường hợp thích hợp.

Ví dụ minh họa tạo metadata:

~~~java
import org.springframework.beans.factory.support.ChildBeanDefinition;
import org.springframework.beans.factory.support.RootBeanDefinition;

RootBeanDefinition parent =
        new RootBeanDefinition(TemplateInheritanceDemo.AlertConfig.class);
parent.setAbstract(true);
parent.getPropertyValues().add("prefix", "BASE");

ChildBeanDefinition child = new ChildBeanDefinition("baseTemplate");
child.getPropertyValues().add("channel", "email");
~~~

Đoạn này **không độc lập**: muốn chạy cần thêm bean factory/registry để đăng ký `parent` dưới tên `baseTemplate`, đăng ký `child` dưới tên riêng, rồi lấy bean. Nó được đưa ra để giúp nhận ra rằng XML `parent` cuối cùng cũng ánh xạ thành **metadata container**, không phải cây instance objects.

Lưu ý `ChildBeanDefinition` không nên được coi là yêu cầu bắt buộc của mọi cấu hình Java annotation. Khi dùng `@Bean`, developer thường ưu tiên factor shared setup vào factory/helper rõ ràng, thay vì tái tạo nguyên vẹn XML bean-definition inheritance bằng nhiều tầng Java class.

## 8. Dùng khi nào và tránh lạm dụng

**Phù hợp khi:**

- Bảo trì hoặc thiết kế các cấu hình Spring XML có nhiều child bean cùng nhóm thông số chuẩn.
- Một số bean có chung cấu hình rất lớn nhưng chỉ khác vài property hoặc constructor arguments.
- Muốn áp dụng một policy config chung cho nhiều bean implementation tương thích.
- Cần merge danh sách hoặc properties mà các child chỉ bổ sung một phần theo định nghĩa rõ.

**Cân nhắc cách khác khi:**

- Các child khác nhau đến mức template chứa hàng loạt property không áp dụng cho một số class.
- Có nhiều cấp `parent` lồng nhau khiến nguồn gốc của giá trị cuối khó lần vết.
- Cần thay đổi hành vi theo dữ liệu nghiệp vụ runtime — bean definition inheritance là cấu hình startup, không phải strategy selection của từng request.
- Đang dùng Java configuration thuần: có thể khai báo `@Bean` factory chung, helper construction hoặc một class config dùng chung có contract rõ, tránh cố ép cú pháp `parent="..."` của XML vào Java.
- Muốn tái sử dụng *code Java*: dùng composition/kế thừa class khi thật sự hợp lý, đừng dùng bean definition inheritance để giải quyết tất cả bài toán OOP.

Một template tốt nên chứa **thiết lập ổn định có ý nghĩa chung**. Nếu bất kỳ child nào cũng phải ghi đè gần như toàn bộ, template ít còn giá trị và làm giảm tính minh bạch.

## 9. Lỗi phổ biến và cách khắc phục

| Triệu chứng / hiểu nhầm | Giải thích và cách xử lý |
| --- | --- |
| `getBean("baseTemplate")` lỗi | Parent `abstract="true"` chỉ là metadata template, không được instantiable. |
| Quên `abstract="true"` | Parent có class có thể bị tạo thành singleton không mong muốn khi refresh. |
| Parent không có class nhưng không abstract | Definition không đủ cách tạo, cần đánh dấu abstract và child phải hoàn chỉnh. |
| Nghĩ `parent` là Java `extends` | Đó là kế thừa cấu hình, không thay class hierarchy. |
| Nghĩ child giữ tham chiếu tới một parent object | Container hợp nhất metadata; không bắt buộc tạo object cha. |
| Child đổi class rồi lỗi property | Class mới không hỗ trợ setter/constructor được kế thừa. |
| Child khai báo list nhưng mất phần tử parent | Mặc định collection property mới thay list cũ, cần `merge="true"` ở child. |
| Đặt `merge="true"` trên parent | Merge phải được bật ở collection trong child definition. |
| Merge `<list>` với `<map>` | Không cùng loại collection, Spring không thể merge theo ý tưởng đó. |
| Key Properties trùng nhưng không lấy giá trị con | Kiểm tra `merge="true"` ở child và key cụ thể; child có thể đang replace. |
| Lỗi constructor sau merge | Kiểm tra argument indexes/names/type và overload thực tế của bean class. |
| Nghĩ tất cả metadata được kế thừa | `lazy-init`, `depends-on` và những thuộc tính khác có quy tắc riêng; không tự suy diễn. |
| Đổi `abstract` để sửa lỗi thiếu bean | Xác định bean đó là template hay bean nghiệp vụ thật, không xóa ranh giới này tùy tiện. |
| Nhiều tầng parent-child khó debug | Giảm độ sâu, dùng bean names rõ, kiểm tra merged bean definition và viết test cấu hình. |
| Quên khai báo beans.xml ở resources | `ClassPathXmlApplicationContext("beans.xml")` không tìm thấy resource, kiểm tra đường dẫn và classpath. |
| In nguyên Properties rồi lệch stdout | Properties không đảm bảo thứ tự in; lấy theo key khi cần output xác định. |

### Đọc lỗi trong Spring

- `BeanIsAbstractException`: cố lấy một bean definition trừu tượng.
- `BeanDefinitionStoreException` hoặc lỗi bean definition: XML, parent reference hay cấu hình không hợp lệ.
- `BeanCreationException`: tạo bean thất bại, có thể do constructor hoặc setter nhận cấu hình sau merge không hợp lệ.
- `NotWritablePropertyException`: bean class không có setter/property tương ứng với metadata đã khai báo.
- `NoSuchBeanDefinitionException`: tham chiếu sai bean name hoặc lấy bean không được đăng ký.

Hãy đọc **nguyên nhân gốc** trong exception chain và tên bean con đang tạo. Không thêm một `new` bên ngoài container chỉ để né lỗi cấu hình.

## 10. Bài tập tự học (có đáp án)

**Bài 1.** Vì sao `abstract="true"` không đồng nghĩa class Java `abstract`?

**Đáp án:** Cờ abstract áp dụng cho **bean definition của Spring**: parent chỉ làm template, không được lookup như instance. Class Java có thể là concrete, như `AlertConfig` trong chương trình chính.

**Bài 2.** Bean con không có thuộc tính `class` trong XML, vậy nó lấy class nào?

**Đáp án:** Nếu parent cung cấp bean class thì child có thể kế thừa class đó; nếu parent không có class, child cần cung cấp cách tạo phù hợp.

**Bài 3.** Child viết lại `<list>` cho cùng property tags, kết quả có tự nối hai danh sách không?

**Đáp án:** Không. Mặc định child thay property collection cha. Muốn nối dùng `merge="true"` ở list child.

**Bài 4.** List parent `[a,b]` và list child `[c]` với `merge="true"`. Kết quả là gì?

**Đáp án:** `[a,b,c]`, thứ tự phần tử parent được giữ trước child.

**Bài 5.** Parent `support=old`, child `support=new` và `sales=sales` trong `<props merge="true">`. Kết quả ra sao?

**Đáp án:** Key `support` lấy `new`, key `sales` được thêm; những key parent không ghi đè vẫn được giữ.

**Bài 6.** Có thể dùng `<bean parent="baseTemplate">` để tự động gọi phương thức cha Java bằng `super` không?

**Đáp án:** Không. XML parent-child chỉ là metadata; `super` thuộc Java class inheritance và không liên quan trực tiếp.

**Bài 7.** Trong ví dụ, `emailConfig` và `smsConfig` có dùng chung một instance không?

**Đáp án:** Không. Chúng là hai bean definitions độc lập, cùng kế thừa một template metadata và cùng bean class nhưng tạo hai object khác nhau.

**Bài 8.** Nếu hai `ApplicationContext` riêng tải cùng `beans.xml`, các bean singleton có phải cùng instance không?

**Đáp án:** Không theo mặc định. Singleton scope thuộc từng container; cùng XML không có nghĩa chia sẻ object giữa hai context.

**Bài 9.** Nên chuyển toàn bộ ứng dụng Java-config mới sang parent-child XML vì “ít dòng hơn” không?

**Đáp án:** Không nhất thiết. Cần cân nhắc tính minh bạch, khả năng test và cách cấu hình đang dùng. Với Java config, composition/factory methods thường dễ đọc hơn nhiều tầng metadata kế thừa.

## 11. Checklist kiểm tra cấu hình

- [ ] Parent được dùng làm template thì khai báo `abstract="true"`.
- [ ] Khi parent không có class, child phải bổ sung class hoặc cách tạo phù hợp.
- [ ] Phân biệt inheritance của bean definition với Java extends và hierarchy của context.
- [ ] Kiểm tra bean class cuối cùng có các setter/constructor ứng với metadata được kế thừa.
- [ ] Ghi đè scalar property chỉ ở child thật sự cần khác biệt.
- [ ] Với collection, quyết định rõ muốn **replace** hay **merge**.
- [ ] Đặt `merge="true"` trên list/set/map/props của child, không chỉ parent.
- [ ] Không merge những collection type không tương thích.
- [ ] Không dựa vào thứ tự duyệt Map/Properties cho các phép kiểm tra stdout.
- [ ] Không tự suy rằng scope/lazy/depends-on đều inherit giống scalar property.
- [ ] Không lookup trực tiếp một abstract parent bean.
- [ ] Không vô tình đăng ký trùng bean name/class hoặc nhiều cấp parent khó kiểm soát.
- [ ] Đảm bảo tệp XML có trên classpath và cấu hình hợp lệ.
- [ ] Viết integration test cho child merged definitions và các property quan trọng.
- [ ] Tránh sử dụng kế thừa metadata để giấu quy tắc nghiệp vụ runtime.

### Tài liệu Spring chính thức

- [Bean Definition Inheritance](https://docs.spring.io/spring-framework/reference/core/beans/child-bean-definitions.html)
- [Collection Merging](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-properties-detailed.html)
- [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)

**Kết luận:** `abstract="true"` biến bean definition cha thành **mẫu cấu hình không khởi tạo**. Child `parent="..."` kế thừa và ghi đè các metadata phù hợp; với collection, `merge="true"` đặt ở child giúp hợp nhất theo đúng semantics của List, Set, Map hoặc Properties. Đây là kỹ thuật **tái sử dụng cấu hình Spring**, không phải kế thừa code Java hay việc inject một parent object.