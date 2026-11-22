# Giá trị null, tập hợp lồng nhau và bean nội bộ trong Spring XML

## 1. Bối cảnh và mục tiêu

Spring Core Container cho phép khai báo không chỉ những bean đơn giản dạng `<bean id="..." class="..."/>` mà cả **giá trị null**, **các cấu trúc collection lồng nhau** và **bean được định nghĩa trực tiếp bên trong một property/constructor argument**. Đây là những kỹ thuật hữu ích khi tích hợp thư viện Java cũ, cấu hình các rule sets hoặc nối object graph bằng XML mà không cần thêm Java configuration class.

Ví dụ:

```xml
<bean id="notificationPlan" class="demo.NotificationPlan">
    <constructor-arg index="0"><null/></constructor-arg>
    <constructor-arg index="1">
        <map>
            <entry key="weekday">
                <list>
                    <value>email</value>
                    <value>sms</value>
                </list>
            </entry>
        </map>
    </constructor-arg>
    <constructor-arg index="2">
        <bean class="demo.Contact">
            <constructor-arg value="ops@example.test"/>
        </bean>
    </constructor-arg>
</bean>
```

Đây là snippet **minh họa cấu trúc**, với `NotificationPlan` và `Contact` là hai Java types cần định nghĩa có constructors phù hợp. Một phiên bản hoàn chỉnh, biên dịch/chạy được với Java 17 và Spring Framework 6.2, sẽ xuất hiện ở phần thực hành.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `<null/>` với chuỗi rỗng, chuỗi chữ `"null"`, property không được cấu hình và XML `xsi:nil`.
2. Gán `null` qua `<constructor-arg>`, `<property>`, bên trong `<list>`, `<map>` và những collections phù hợp.
3. Cấu hình `<list>`, `<set>`, `<map>`, `<props>` cùng các phần tử lồng nhau; hiểu `<value>`, `<ref>`, `<bean>`, `<null>`.
4. Giải thích cách Spring dùng generic types như `Map<String, List<String>>` để hỗ trợ chuyển đổi dữ liệu khi inject.
5. Hiểu inner bean: bean định nghĩa ngay bên trong một bean khác, **anonymous**, **không lookup độc lập bằng ID**, được tạo cùng enclosing bean.
6. Phân biệt inner bean với top-level bean + `ref`; hiểu tương tác với scope và lifecycle.
7. Thực hành một XML config hoàn chỉnh với `null`, map chứa list, list chứa list và inner bean.
8. Chẩn đoán lỗi XML liên quan structure/schema, nullability, type conversion, thiếu dependencies và collection merging.

## 2. Ba tầng cần phân biệt

Khi Spring đọc XML, dữ liệu di chuyển qua ba tầng:

```text
XML resource
    |
    +--> <bean>          : bean definition
    +--> <constructor-arg> / <property> : injection point
    +--> <null/> / <list/> / <map/> ... : value metadata
    |
    v
BeanDefinition / PropertyValue / ConstructorArgumentValues
    |
    v
BeanFactory resolve dependencies + convert types
    |
    v
Java object và các trường dữ liệu của nó
```

Ở pha parsing, một phần tử `<list>` không nhất thiết đã là `ArrayList` thực tế; nó có thể được biểu diễn bằng metadata dạng managed collection. Khi bean được tạo, Spring giải quyết các references, inner bean definitions, nested values và chuyển đổi phù hợp với kiểu của constructor parameter/setter.

**Điểm quan trọng:** metadata XML khai báo *giá trị đầu vào của object graph*, chứ không tự thay đổi hợp đồng Java. Nếu constructor Java cấm `null`, XML `<null/>` không làm điều kiện đó hợp lệ.

## 3. <null/>: null Java thật sự

Để truyền giá trị `null` vào constructor:

```xml
<bean id="userProfile" class="com.example.UserProfile">
    <constructor-arg index="0">
        <null/>
    </constructor-arg>
</bean>
```

Giả sử class có constructor `UserProfile(String nickname)`, Spring đưa Java reference `null` vào argument thứ nhất.

### 3.1. Bốn trạng thái rất khác nhau

| XML hoặc tình huống | Ý nghĩa |
| --- | --- |
| `<constructor-arg><null/></constructor-arg>` | Explicit Java `null`. |
| `<constructor-arg value=""/>` | Chuỗi rỗng `""`, không phải null. |
| `<constructor-arg value="null"/>` | Chuỗi có bốn ký tự `n`, `u`, `l`, `l`, trừ khi có conversion/custom logic khác. |
| Không khai báo constructor arg | Không cung cấp value tại vị trí đó; Spring phải chọn constructor và resolve những tham số còn lại theo metadata/hạ tầng. Không đồng nghĩa tự điền null. |

Đối với setter/property injection, “không khai báo `<property>`” có thể giữ nguyên giá trị default do constructor/field initialization thiết lập; “khai báo `<property><null/></property>`” chủ động yêu cầu ghi `null` vào property.

### 3.2. Property setter nhận null

```java
package com.example;

public class MailSettings {
    private String replyTo = "noreply@example.test";

    public void setReplyTo(String replyTo) {
        this.replyTo = replyTo;
    }

    public String getReplyTo() {
        return replyTo;
    }
}
```

Nếu XML không cấu hình `replyTo`, field giữ giá trị mặc định. Nếu dùng:

```xml
<bean id="mailSettings" class="com.example.MailSettings">
    <property name="replyTo"><null/></property>
</bean>
```

Spring gọi setter với `null`. Điều này **khác** với:

```xml
<property name="replyTo" value=""/>
```

vì đoạn sau yêu cầu chuỗi rỗng.

### 3.3. Kiểu primitive không chấp nhận null

```java
public final class RetrySettings {
    public RetrySettings(int attempts) {
    }
}
```

Với constructor `int attempts`, XML `<null/>` không thể tạo một giá trị `int` hợp lệ. Spring có thể ném lỗi tạo bean / mismatch trong lúc resolve constructor arguments. Nếu biểu đạt “không có giá trị” là yêu cầu hợp lệ, cân nhắc `Integer` hoặc một model rõ nghĩa như `Optional` ở lớp Java, rồi cấu hình theo hợp đồng cụ thể.

**Lưu ý về `Optional`:** không coi `<null/>` tự động tương đương `Optional.empty()` cho mọi constructor. Việc chuyển đổi, resolution và cách viết factory/constructor cần được thiết kế rõ ràng.

### 3.4. null và validation

Annotation như `@NotNull` thuộc validation stack khi có provider và cơ chế validation phù hợp; nó không tự ngăn XML parser đọc `<null/>`. Constructor tự kiểm tra `Objects.requireNonNull(...)` sẽ ném exception khi Spring tạo bean, trừ khi có conversion/cấu hình khác.

Vì vậy, trước khi cố đưa `null` vào object, hãy kiểm tra:

- Java parameter/field có nullable về mặt hợp đồng không?
- Có default được thiết lập trong constructor không?
- Có logic fallback nếu null không?
- Có validation/lifecycle callback kiểm tra non-null không?
- Error nên phát hiện ngay lúc startup hay runtime?

## 4. null trong collections

Spring collection elements có thể chứa `<null/>`:

```xml
<property name="fallbacks">
    <list>
        <value>primary</value>
        <null/>
        <value>secondary</value>
    </list>
</property>
```

Ví dụ này đặt trong `<bean>` có property `fallbacks` tương ứng. Nếu Java nhận `List<String>`, phần tử giữa thường là Java `null`. Một số Java APIs không hỗ trợ null trong collection, do đó việc XML chấp nhận cú pháp không có nghĩa consumer chấp nhận semantics.

Một map value null có thể khai báo:

```xml
<property name="thresholds">
    <map>
        <entry key="low" value="10"/>
        <entry key="unknown">
            <null/>
        </entry>
    </map>
</property>
```

Ví dụ yêu cầu setter/constructor nhận một map với value type nullable thích hợp, chẳng hạn `Map<String, Integer>`. `unknown` tồn tại như **một map key với value null**, khác việc map không có key đó. Khi xử lý, dùng `containsKey("unknown")` để phân biệt hai trường hợp.

### null trong XML không phải xsi:nil mặc định

Không nên lấy cú pháp của JAXB/XML Schema nillable elements rồi áp máy móc vào Spring Bean XML. Với Spring `beans` namespace, cách rõ ràng để cung cấp null tại value position là `<null/>`.

## 5. Các phần tử collection cơ bản

Spring XML có thể gán values cho Java collections qua:

| Phần tử | Java contract thường gặp | Đặc điểm |
| --- | --- | --- |
| `<list>` | `List<T>` | Có thứ tự; cho phép trùng phần tử. |
| `<set>` | `Set<T>` | Không chứa phần tử trùng theo equality semantics; không nên dựa vào thứ tự nếu không có hợp đồng riêng. |
| `<map>` | `Map<K,V>` | Các cặp key-value; key duy nhất. |
| `<props>` | `java.util.Properties` | Các property keys/values chủ yếu dưới dạng String. |
| `<array>` | Mảng Java | Hữu ích khi API yêu cầu array; cũng có thể dùng `<list>` và để Spring chuyển đổi khi tương thích. |

**Chú ý:** các kiểu collection có thể được Spring tạo bằng internal managed metadata trong khi parse và được chuyển thành implementation thích hợp cho injection; đừng viết logic phụ thuộc concrete implementation như `LinkedHashMap` chỉ vì quan sát thấy như vậy trong một lần chạy.

### 5.1. List

```xml
<property name="servers">
    <list>
        <value>primary.example.test</value>
        <value>backup.example.test</value>
        <value>backup.example.test</value>
    </list>
</property>
```

Java property dạng `List<String>` nhận các phần tử theo thứ tự; hai chuỗi trùng nhau vẫn có thể tồn tại.

### 5.2. Set

```xml
<property name="regions">
    <set>
        <value>ap-southeast-1</value>
        <value>eu-west-1</value>
    </set>
</property>
```

Nếu Java property là `Set<String>`, nghiệp vụ không nên dựa vào vị trí `get(0)` (vì Set không có index). Khi in log/test, sort nếu cần output ổn định.

### 5.3. Map

```xml
<property name="timeouts">
    <map>
        <entry key="connect" value="500"/>
        <entry key="read" value="2000"/>
    </map>
</property>
```

Nếu setter nhận `Map<String,Integer>`, conversion service/type conversion infrastructure có thể chuyển các chuỗi `500`, `2000` thành `Integer`. Nếu loại numeric sai, Spring báo lỗi khi tạo/inject bean.

### 5.4. Properties

```xml
<property name="mailSettings">
    <props>
        <prop key="mail.host">smtp.example.test</prop>
        <prop key="mail.protocol">smtp</prop>
    </props>
</property>
```

`<props>` gắn với `java.util.Properties`. Khi cần dữ liệu có nested objects hoặc non-string values, dùng `<map>` thay vì ép mọi thứ thành Properties.

### 5.5. Các phần tử có thể nằm trong collection

Bên trong list/set/map value, Spring XML hỗ trợ các cấu trúc như:

- `<value>`: giá trị literal; conversion khi inject theo target type.
- `<ref bean="..."/>`: tham chiếu một top-level bean/alias đã đăng ký.
- `<bean class="...">`: tạo **inner bean** tại vị trí phần tử.
- `<null/>`: Java null.
- `<list>`, `<set>`, `<map>`, `<props>`: nested collection.
- `<idref bean="..."/>`: một **String bean name** được kiểm tra tồn tại, không phải object reference.

Cần phân biệt `<idref/>` với `<ref/>`: cái trước tạo string identifier, cái sau resolve object bean.

## 6. Tập hợp lồng nhau: List trong Map, Map trong List

Một ứng dụng định tuyến thông báo có thể yêu cầu:

```java
Map<String, List<String>> channelsByDay;
```

XML:

```xml
<property name="channelsByDay">
    <map>
        <entry key="weekday">
            <list>
                <value>email</value>
                <value>sms</value>
            </list>
        </entry>
        <entry key="weekend">
            <list>
                <value>push</value>
            </list>
        </entry>
    </map>
</property>
```

Ở đây, hai `<list>` nằm trong hai `<entry>` của `<map>`. Đây là **collection of collections**, không phải hai bean definitions. Spring tạo/resolve nested values rồi chuyển sang target type `Map<String,List<String>>`.

### 6.1. List chứa List

```xml
<property name="stages">
    <list>
        <list>
            <value>validate</value>
            <value>build</value>
        </list>
        <list>
            <value>deploy</value>
        </list>
    </list>
</property>
```

Java target `List<List<String>>` có hai phần tử: list thứ nhất chứa `validate` và `build`; list thứ hai chứa `deploy`. Phân biệt với một list phẳng có ba strings.

### 6.2. Map trong Map

```xml
<property name="routes">
    <map>
        <entry key="internal">
            <map>
                <entry key="primary" value="host-internal"/>
            </map>
        </entry>
        <entry key="external">
            <map>
                <entry key="primary" value="host-public"/>
            </map>
        </entry>
    </map>
</property>
```

Một Java property kiểu `Map<String,Map<String,String>>` có thể nhận cấu trúc này. Nếu nhiều cấp lồng sâu, hãy cân nhắc một class cấu hình có tên/validation thay vì XML lồng nhiều tầng khó bảo trì.

### 6.3. Bean trong collection

```xml
<property name="handlers">
    <list>
        <bean class="com.example.EmailHandler"/>
        <ref bean="sharedSmsHandler"/>
    </list>
</property>
```

Phần tử đầu là **inner bean definition**, phần tử sau là **reference đến một bean khác đã được container đăng ký**. Nếu `handlers` nhận `List<Handler>`, cả hai cùng phải là implementation hợp lệ. Không được suy ra mỗi phần tử trong list luôn là managed top-level bean với tên tra cứu độc lập.

### 6.4. Nested value không phải nested bean trong mọi trường hợp

`<map><entry><list>...</list></entry></map>` tạo nested *collection values* chứ không có bean definition riêng cho mỗi list. `<bean>` đặt bên trong `<property>` hoặc `<constructor-arg>` mới là **inner bean**. Đừng gọi mọi phần tử XML lồng nhau là bean.

## 7. Map entry: value, value-ref và phần tử con

Hai cách này có ý nghĩa khác nhau:

```xml
<entry key="clientName" value="httpClient"/>
```

lưu **literal** chuỗi `httpClient`.

```xml
<entry key="clientObject" value-ref="httpClient"/>
```

lookup bean có tên `httpClient` để dùng **object reference** làm value.

Dạng lồng tương đương với value-ref:

```xml
<entry key="clientObject">
    <ref bean="httpClient"/>
</entry>
```

Với `key-ref`, key cũng có thể là một bean reference; dùng khi kiểu key thực sự là object thay vì String. Nếu cấu hình chỉ cần String keys, `key="..."` đơn giản và rõ nghĩa hơn.

### Cặp null value trong Map

```xml
<entry key="disabled">
    <null/>
</entry>
```

Khác với việc bỏ hẳn `disabled` khỏi map. Nếu business logic dùng `get("disabled") == null`, hai trường hợp vẫn cần phân biệt bằng `containsKey` khi cần.

### Map có key trùng nhau

Một map về bản chất chỉ giữ một value cho mỗi key theo equality. Việc khai báo XML lặp key có thể gây behavior ghi đè/validation tùy parser và dữ liệu. Không dựa vào thứ tự entries làm chính sách override; đặt key duy nhất hoặc merge collections theo quy tắc rõ.

## 8. Generic types và chuyển đổi phần tử

Spring tận dụng generic type information trên constructor/setter nếu Java metadata cho phép:

```java
public final class RetryPolicy {
    private final Map<String, Integer> attempts;

    public RetryPolicy(Map<String, Integer> attempts) {
        this.attempts = attempts;
    }
}
```

Một XML config:

```xml
<bean id="retryPolicy" class="com.example.RetryPolicy">
    <constructor-arg>
        <map>
            <entry key="read" value="3"/>
            <entry key="write" value="5"/>
        </map>
    </constructor-arg>
</bean>
```

Có thể chuyển các string values thành Integer nhờ target constructor signature `Map<String,Integer>`. Đây là khả năng type conversion được tài liệu Spring mô tả cho strongly typed collections. Nếu chuỗi là `"many"`, Integer conversion không hợp lệ và việc tạo bean có thể lỗi.

### Các rủi ro thường gặp

- Java dùng raw type `Map` hoặc `List` nên type metadata không rõ.
- Nested list có lẫn String và bean object dù target là `List<String>`.
- Code giả định keys luôn là String khi XML khai báo `key-ref`.
- Converter tùy chỉnh không được đăng ký hoặc kết quả conversion không như mong đợi.
- Java field là `Map<String,List<Integer>>` nhưng XML chứa giá trị chữ không parse được.
- Consumer thay đổi collection sau injection mà không rõ ownership/thread safety.

**Khuyến nghị:** ưu tiên types cụ thể trên constructor/setter, validates inputs sớm, và test bean creation với các cấu trúc lồng nhau.

## 9. Inner bean là gì?

Một bean nằm trực tiếp trong `<property>` hoặc `<constructor-arg>` của bean khác:

```xml
<bean id="mailDispatcher" class="com.example.MailDispatcher">
    <constructor-arg>
        <bean class="com.example.DeliveryContact">
            <constructor-arg value="ops@example.test"/>
        </bean>
    </constructor-arg>
</bean>
```

là **inner bean**. Nó phù hợp khi collaborator:

- chỉ thuộc về bean bao ngoài;
- không cần tên bean public;
- không cần reuse độc lập từ nhiều consumers;
- có lifecycle gắn với việc tạo bean bao ngoài;
- làm object graph dễ nhìn khi cấu hình nhỏ.

Theo tài liệu Spring, inner bean là **anonymous**; dù bạn điền `id`/`name`, container không dùng chúng như định danh lookup độc lập. `scope` khai báo trên inner bean cũng bị bỏ qua để bảo đảm inner bean được tạo cùng enclosing bean.

### 9.1. Vì sao không cần id?

```xml
<bean id="dispatcher" class="com.example.Dispatcher">
    <property name="contact">
        <bean class="com.example.Contact"/>
    </property>
</bean>
```

Đây là một inner bean được tạo để inject vào `dispatcher.contact`. Nó không xuất hiện như top-level bean tên `contact` chỉ vì property có tên đó.

### 9.2. Nếu inner bean có id?

```xml
<bean id="dispatcher" class="com.example.Dispatcher">
    <property name="contact">
        <bean id="embeddedContact" class="com.example.Contact"/>
    </property>
</bean>
```

Trong Spring XML, `embeddedContact` **không trở thành một tên public dùng `getBean("embeddedContact")`**. Inner bean vẫn được xử lý như bean định nghĩa nội bộ, không được đăng ký thành top-level lookup name.

**Không viết:** “Đặt ID cho inner bean rồi dùng `ref` từ bean khác”. Nếu nhiều consumers cần reuse cùng collaborator, hãy dùng **top-level bean + `ref`**.

### 9.3. Scope của inner bean

Tài liệu Spring ghi rõ inner beans **always anonymous and always created with the outer bean**, và `scope` trên inner bean bị bỏ qua.

Điều này có nghĩa:

- Outer **singleton** được dựng một lần → inner collaborator thường được tạo khi dựng outer và được giữ trong outer.
- Outer **prototype** được tạo qua nhiều lookups → mỗi outer instance thông thường có inner collaborator được tạo cùng nó.
- Việc gắn `scope="singleton"` hay `scope="prototype"` lên inner bean không tạo ra một public scoped bean độc lập.

Một vài scope tùy chỉnh có thể có tương tác destruction callbacks đặc biệt; không nên khẳng định mọi inner bean trên mọi custom scope luôn có hành vi hủy hoàn toàn giống top-level bean. Thiết kế resource ownership và kiểm thử lifecycle cụ thể.

## 10. Inner bean và top-level ref: so sánh

| Tiêu chí | Inner bean | Top-level bean + ref |
| --- | --- | --- |
| Vị trí | `<bean>` lồng trong property/constructor arg | `<bean id="...">` trực tiếp dưới `<beans>` |
| Tên public | Không có | Có `id`/`name`/aliases |
| Lookup độc lập | Không | Có |
| Có thể chia sẻ giữa nhiều consumers | Không thông qua cùng một public bean definition | Có nếu scope và wiring phù hợp |
| Scope | Gắn với tạo outer bean; scope flag nội bộ bị bỏ qua | Tuân scope của chính bean definition |
| Cấu hình cùng owner | Rõ nếu collaborator chỉ dùng một nơi | Rõ nếu collaborator là tài nguyên dùng chung |
| Test riêng theo bean name | Không | Có |
| Lifecycle | Tạo khi outer được tạo; lưu ý custom destruction edge cases | BeanFactory quản lý độc lập theo scope |

### Top-level bean phù hợp khi nào?

```xml
<bean id="sharedContact" class="com.example.Contact">
    <constructor-arg value="shared@example.test"/>
</bean>

<bean id="dispatcherA" class="com.example.Dispatcher">
    <constructor-arg ref="sharedContact"/>
</bean>

<bean id="dispatcherB" class="com.example.Dispatcher">
    <constructor-arg ref="sharedContact"/>
</bean>
```

Hai consumers có thể nhận cùng singleton `sharedContact`. Nếu thay `ref` bằng inner `<bean>` riêng trong từng consumer, đó là hai collaborator definitions nội bộ khác nhau.

### Inner bean phù hợp khi nào?

Một formatter nhỏ gắn với đúng một parser, hoặc local strategy gắn với đúng một service và không cần tái sử dụng có thể là inner bean. Nhưng nếu object giữ database connection pool, thread executor, client có lifecycle phức tạp hoặc được dùng chung bởi nhiều modules, top-level bean có owner rõ thường tốt hơn.

## 11. Ví dụ chạy được Java 17+: null, Map<List>, List<List>, inner bean

Ví dụ sau **không cần Spring Boot**, không dùng annotation configuration, không kết nối mạng/database. Nó dùng **Spring Framework 6.2.9** và **ClassPathXmlApplicationContext**.

Ta định nghĩa:

- `ReleasePlan`: nhận nullable `String note`; `Map<String,List<String>> channels`; `List<List<String>> stages`; `Contact contact`.
- `Contact`: class Java bình thường, chứa email.
- Bean `releasePlan` dùng XML constructor arguments và một inner `Contact`.
- Bean `sharedContact` là top-level để so sánh với inner bean.
- Main in các kiểm tra có stdout xác định.

### 11.1. Cấu trúc dự án

```text
spring-xml-values-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Contact.java
        │       ├── ReleasePlan.java
        │       └── XmlValuesDemo.java
        └── resources/
            └── beans.xml
```

Có ba public top-level Java classes, file name đúng tên class. XML ở `src/main/resources/beans.xml` để Gradle đưa lên classpath.

### 11.2. Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'spring-xml-values-demo'
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
    mainClass = 'demo.XmlValuesDemo'
}
```

Spring Context kéo theo Spring Beans/Core và các dependencies cần thiết. Java 17+ tương thích Spring Framework 6.2. Đây là **một project độc lập**, không cần wrapper nếu hệ thống đã có Gradle; nếu có wrapper, dùng lệnh wrapper tương ứng.

### 11.3. Contact.java

**`src/main/java/demo/Contact.java`**

```java
package demo;

import java.util.Objects;

public final class Contact {
    private final String email;

    public Contact(String email) {
        this.email = Objects.requireNonNull(email);
    }

    public String email() {
        return email;
    }
}
```

Constructor yêu cầu email non-null. XML cung cấp một chuỗi hợp lệ.

### 11.4. ReleasePlan.java

**`src/main/java/demo/ReleasePlan.java`**

```java
package demo;

import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class ReleasePlan {
    private final String note;
    private final Map<String, List<String>> channels;
    private final List<List<String>> stages;
    private final Contact contact;

    public ReleasePlan(
            String note,
            Map<String, List<String>> channels,
            List<List<String>> stages,
            Contact contact) {
        this.note = note; // có thể null theo hợp đồng ví dụ
        this.channels = Objects.requireNonNull(channels);
        this.stages = Objects.requireNonNull(stages);
        this.contact = Objects.requireNonNull(contact);
    }

    public String note() {
        return note;
    }

    public Map<String, List<String>> channels() {
        return channels;
    }

    public List<List<String>> stages() {
        return stages;
    }

    public Contact contact() {
        return contact;
    }
}
```

Đây là cấu trúc immutable về **references** (các fields final). Nó **không bảo đảm collections bất biến sâu**, vì Map/List được truyền vào có thể còn mutable. Với production, có thể tạo defensive copies và nested immutable copies khi cần, nhưng điều đó không thay đổi khả năng inject của XML.

### 11.5. beans.xml đầy đủ

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Một top-level Contact có thể lookup theo tên. -->
    <bean id="sharedContact" class="demo.Contact">
        <constructor-arg value="shared@example.test"/>
    </bean>

    <bean id="releasePlan" class="demo.ReleasePlan">

        <!-- Constructor arg #0: Java null, không phải chuỗi "null". -->
        <constructor-arg index="0">
            <null/>
        </constructor-arg>

        <!-- Constructor arg #1: Map<String, List<String>>. -->
        <constructor-arg index="1">
            <map>
                <entry key="weekday">
                    <list>
                        <value>email</value>
                        <value>sms</value>
                    </list>
                </entry>
                <entry key="weekend">
                    <list>
                        <value>push</value>
                    </list>
                </entry>
            </map>
        </constructor-arg>

        <!-- Constructor arg #2: List<List<String>>. -->
        <constructor-arg index="2">
            <list>
                <list>
                    <value>validate</value>
                    <value>build</value>
                </list>
                <list>
                    <value>deploy</value>
                </list>
            </list>
        </constructor-arg>

        <!-- Constructor arg #3: bean nội bộ không lookup bằng ID. -->
        <constructor-arg index="3">
            <bean id="embeddedContact" class="demo.Contact">
                <constructor-arg value="ops@example.test"/>
            </bean>
        </constructor-arg>

    </bean>
</beans>
```

Có **hai top-level `<bean>` declarations**: `sharedContact` và `releasePlan`. Phần tử `<bean id="embeddedContact">` nằm **bên trong** constructor argument nên là anonymous inner bean; Spring không đăng ký nó thành top-level bean có thể lookup theo ID `embeddedContact`.

### 11.6. Main class

**`src/main/java/demo/XmlValuesDemo.java`**

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlValuesDemo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("beans.xml")) {

            ReleasePlan plan =
                    context.getBean("releasePlan", ReleasePlan.class);
            Contact shared =
                    context.getBean("sharedContact", Contact.class);

            System.out.println("note-null="
                    + (plan.note() == null));

            System.out.println("weekday-channels="
                    + String.join(",", plan.channels().get("weekday")));

            System.out.println("weekend-channels="
                    + String.join(",", plan.channels().get("weekend")));

            System.out.println("stages-count="
                    + plan.stages().size());

            System.out.println("stage-order="
                    + plan.stages().get(0).get(1) + ">"
                    + plan.stages().get(1).get(0));

            System.out.println("inner-email="
                    + plan.contact().email());

            System.out.println("inner-lookup-visible="
                    + context.containsBean("embeddedContact"));

            System.out.println("inner-is-shared="
                    + (plan.contact() == shared));

            System.out.println("release-plan-singleton="
                    + (plan == context.getBean(ReleasePlan.class)));

            System.out.println("top-level-definitions="
                    + context.getBeanDefinitionCount());
        }
    }
}
```

### 11.7. Biên dịch và chạy

Từ thư mục `spring-xml-values-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Trên Windows, thay bằng `gradlew.bat run --quiet`. Không thể biên dịch riêng `XmlValuesDemo.java` bằng `javac` mà không cung cấp Spring libraries vào compile classpath và biên dịch các source files khác; Gradle xử lý cả classpath lẫn resource copying.

### 11.8. Stdout từ chương trình

```text
note-null=true
weekday-channels=email,sms
weekend-channels=push
stages-count=2
stage-order=build>deploy
inner-email=ops@example.test
inner-lookup-visible=false
inner-is-shared=false
release-plan-singleton=true
top-level-definitions=2
```

Đây là các dòng do những lệnh `System.out.println` trong ví dụ tạo ra. Các log khác của Gradle hoặc runtime không thuộc nội dung này.

### 11.9. Diễn giải output

- **`note-null=true`:** constructor argument 0 nhận Java `null` vì XML dùng `<null/>`.
- **`weekday-channels=email,sms`:** key `weekday` chứa list hai phần tử đúng thứ tự.
- **`weekend-channels=push`:** key `weekend` chứa list một phần tử.
- **`stages-count=2`:** outer list có hai inner lists.
- **`stage-order=build>deploy`:** list thứ nhất `[validate, build]` và list thứ hai `[deploy]`, nên lấy index 1 của list 0 là `build`, index 0 của list 1 là `deploy`.
- **`inner-email=ops@example.test`:** Spring tạo inner `Contact` với constructor argument của nó.
- **`inner-lookup-visible=false`:** tên `embeddedContact` đặt trên inner bean không trở thành một top-level bean ID có thể lookup.
- **`inner-is-shared=false`:** top-level `sharedContact` và inner collaborator là hai object khác nhau.
- **`release-plan-singleton=true`:** bean `releasePlan` dùng default scope singleton và được lookup hai lần trong cùng context.
- **`top-level-definitions=2`:** context XML thuần có đúng hai top-level beans; inner bean không xuất hiện như một top-level bean definition.

**Điểm kiểm chứng quan trọng:** bean nội bộ có thể được Spring instantiate và inject hợp lệ **dù nó không được công bố làm bean name độc lập**.

## 12. Inner bean kết hợp với nested collection

Inner beans không chỉ xuất hiện trực tiếp dưới một `<property>`/`<constructor-arg>`; chúng còn có thể nằm trong collection được dùng làm property/argument.

Ví dụ danh sách policies:

```xml
<bean id="policyEngine" class="com.example.PolicyEngine">
    <constructor-arg>
        <list>
            <bean class="com.example.MinValuePolicy">
                <constructor-arg value="10"/>
            </bean>
            <bean class="com.example.MaxValuePolicy">
                <constructor-arg value="100"/>
            </bean>
        </list>
    </constructor-arg>
</bean>
```

Đây là snippet kiến trúc minh họa, cần các class thật và constructor nhận `List<Policy>` phù hợp. Mỗi `<bean>` bên trong list là inner bean; các policies không có tên top-level để consumers khác lookup độc lập.

Nếu một policy cần được dùng chung bởi nhiều engines, nên định nghĩa top-level policy bean:

```xml
<bean id="sharedPolicy" class="com.example.SharedPolicy"/>

<bean id="policyEngine" class="com.example.PolicyEngine">
    <constructor-arg>
        <list>
            <ref bean="sharedPolicy"/>
        </list>
    </constructor-arg>
</bean>
```

`<ref>` giữ liên kết tới registered bean theo scope của nó; `<bean>` lồng tại điểm sử dụng tạo một inner definition.

### Khi nào nested collection quá sâu?

Nếu XML có nhiều tầng `<map>` và `<list>` đến mức không còn đọc được validation rules, cân nhắc:

- class settings có tên rõ thay vì map of maps;
- Java configuration factory method trả một typed object;
- configuration properties mapping/binding theo stack đang dùng;
- tách XML resource theo boundary;
- tests kiểm tra structure và các invariants nghiệp vụ.

Nested collection hữu ích cho dữ liệu có cấu trúc, không nên biến thành một ngôn ngữ lập trình phức tạp trong XML.

## 13. Collection merging trong XML bean inheritance

Spring XML hỗ trợ **merging** của các collections tương thích khi sử dụng parent/child bean definitions.

Ví dụ property `rules` là `List<String>`:

```xml
<bean id="basePolicy"
      abstract="true"
      class="com.example.RuleConfig">
    <property name="rules">
        <list>
            <value>audit</value>
            <value>validate</value>
        </list>
    </property>
</bean>

<bean id="prodPolicy" parent="basePolicy">
    <property name="rules">
        <list merge="true">
            <value>enforce</value>
        </list>
    </property>
</bean>
```

Đây là snippet cần `RuleConfig` public class có setter `setRules(List<String>)` hoặc property tương thích. `basePolicy` được khai báo abstract để làm template definition; `prodPolicy` thừa hưởng metadata và merge list.

Với `merge="true"` trên **child list**, danh sách sau merge theo thứ tự:

```text
audit
validate
enforce
```

Điểm quan trọng: merge phải được bật **trên collection con** thuộc bean definition kế thừa. Gắn merge flag vào parent list không có tác dụng mong đợi. Không thể merge collection khác loại, ví dụ parent là `<map>` mà child là `<list>`.

### Map, Set và Props merging

- **List:** giữ các phần tử parent trước, rồi nối các phần tử child.
- **Map:** child keys có thể override parent keys.
- **Set:** hợp nhất các phần tử theo set semantics.
- **Properties:** child entries có thể override keys của parent.

Đừng thiết kế logic phụ thuộc vào iteration order của `Map`, `Set` hoặc `Properties` nếu không có contract đảm bảo. Collection merging là cơ chế metadata inheritance, không phải Spring tự merge bất kỳ hai collections được inject từ các beans độc lập.

### Không nhầm merge với nested collection

`<list><list>...</list></list>` là **list lồng trong list**. `<list merge="true">` trong bean child kế thừa **gộp metadata collection của parent và child**. Đây là hai mục đích riêng, có thể xuất hiện cùng nhau nhưng không tự đồng nghĩa.

## 14. Null trong Map và cách phân biệt key vắng mặt

Ví dụ một map cấu hình:

```xml
<property name="featureLimits">
    <map>
        <entry key="basic" value="10"/>
        <entry key="premium">
            <null/>
        </entry>
    </map>
</property>
```

Java code:

```java
Map<String, Integer> limits = settings.getFeatureLimits();

boolean premiumExplicitlyPresent =
        limits.containsKey("premium"); // true

Integer premium = limits.get("premium"); // null
Integer trial = limits.get("trial");     // null
```

Đoạn này là minh họa, giả định `settings` có accessor trả `Map<String,Integer>`. Hai lần `get()` đều trả null, nhưng trường hợp `premium` là key có mặt và value null, trong khi `trial` là key vắng mặt. Nếu app dùng null để diễn đạt “không giới hạn”, hãy viết validation và comments rõ.

**Không cố ép Java primitive `int` chứa null.** Với map value type là `Integer`, null có thể là hợp lệ theo hợp đồng.

## 15. Null và empty collections

Cùng một property `recipients` có ít nhất ba trạng thái:

**Không được cấu hình:**

```xml
<bean id="mailer" class="com.example.Mailer"/>
```

Java property có thể giữ default do constructor/field khởi tạo; không phải Spring tự suy luận empty list.

**Được cấu hình null:**

```xml
<bean id="mailer" class="com.example.Mailer">
    <property name="recipients"><null/></property>
</bean>
```

Setter nhận Java null nếu type phù hợp.

**Được cấu hình empty list:**

```xml
<bean id="mailer" class="com.example.Mailer">
    <property name="recipients"><list/></property>
</bean>
```

Setter nhận một list trống thay vì null. Điều này thường tốt hơn nếu consumer định duyệt trực tiếp recipients, nhưng phải tuân hợp đồng class.

**Nhầm lẫn thực tế:** `<list/>` không phải `<null/>`; empty object collection không phải absence. Trong unit/integration tests nên assert đúng trạng thái mà nghiệp vụ cần.

## 16. Tên bean, alias và inner bean

### 16.1. Top-level id và alias

```xml
<bean id="supportContact" class="com.example.Contact"/>
<alias name="supportContact" alias="emergencyContact"/>
```

Đây là top-level bean definition với một alias. Cả hai names có thể được dùng qua `<ref bean="..."/>` trong cùng context.

### 16.2. Inner bean không xuất hiện như alias

```xml
<bean id="releasePlan" class="com.example.ReleasePlan">
    <property name="contact">
        <bean id="localContact" class="com.example.Contact"/>
    </property>
</bean>
```

`localContact` không trở thành public alias/top-level definition chỉ vì có id attribute. Không thể kỳ vọng `context.getBean("localContact")` hoạt động. Nếu dùng chung, hãy chuyển nó ra top-level.

### 16.3. XML resources và context boundary

Nạp hai XML resources vào một `ClassPathXmlApplicationContext` thì top-level bean definitions/aliases có thể tham chiếu nhau theo registry của context. Inner bean vẫn gắn với enclosing definition.

Tạo hai context độc lập không làm inner bean của context A trở nên visible tại context B. Khái niệm parent-child context cũng không biến một inner bean thành bean lookup công khai.

## 17. Lifecycle và tài nguyên của inner bean

### 17.1. Inner bean có được tạo vào thời điểm parse XML không?

Không mặc định. Parser tạo/ghi metadata. Inner bean instance được tạo khi outer bean được resolve/khởi tạo theo dependency graph; với outer singleton eager, điều này thường xảy ra trong `refresh()`.

### 17.2. Scope attribute trên inner bean có quyết định lookup không?

Không. Scope flag của inner bean bị Spring bỏ qua: inner bean được tạo **cùng outer bean**. Một inner bean không có bean name công khai để lấy qua `getBean()` nhiều lần, nên không có semantics lookup độc lập như top-level prototype.

### 17.3. Còn initialization/destruction callbacks?

Spring vẫn có thể xử lý nhiều khâu initialization/post-processing đối với inner beans do container tạo. Nhưng không nên coi vòng đời destroy của mọi inner collaborator giống hoàn toàn một singleton top-level độc lập: documentation nêu corner case custom scopes có thể nhận destruction callbacks, nhưng inner beans thông thường gắn scope với outer.

Với tài nguyên có cần `close()`, thread pools, socket, connection pools hay SDK clients, việc dùng **top-level named bean** với init/destroy contract rõ ràng thường dễ quản trị hơn. Đừng assume rằng khai báo inline automagically giải quyết resource ownership.

### 17.4. Nếu outer bean là prototype?

Mỗi yêu cầu outer prototype thường tạo outer instance mới và các inner dependencies của nó. Nếu muốn share cùng collaborator singleton giữa nhiều outer prototypes, dùng top-level singleton + `<ref>` thay vì khai báo inner `<bean>` lặp lại.

## 18. Lỗi phổ biến

### Lỗi 1 — Dùng literal "null" thay cho null

```xml
<constructor-arg value="null"/>
```

là string "null" trong trường hợp điển hình. Nếu muốn Java null, dùng `<constructor-arg><null/></constructor-arg>`.

### Lỗi 2 — Truyền null vào primitive

`int`/`boolean`/`long` không nhận Java null. Nếu optional là hợp lệ, thiết kế wrapper types và validation đúng ý định.

### Lỗi 3 — Dùng <value/> để biểu diễn empty collection

`<value/>` là value metadata, không phải empty list. Dùng `<list/>` nếu muốn một `List` rỗng.

### Lỗi 4 — Nhầm ref với value

`<ref bean="sharedClient"/>` là managed dependency, còn `<value>sharedClient</value>` là chuỗi literal. Điều này áp dụng cả trong nested `<list>`/`<map>`.

### Lỗi 5 — Nested collection không phù hợp Java generic type

Constructor yêu cầu `Map<String,List<Integer>>` nhưng XML chứa words `email`/`sms`, gây conversion failure khi Spring tạo bean.

### Lỗi 6 — Trộn các loại phần tử không có chủ đích

Một `List<String>` chứa `<bean class="..."/>` có thể không chuyển thành String hợp lệ. Nếu list cần heterogeneous objects, thiết kế interface/record rõ hoặc đúng target type.

### Lỗi 7 — Lấy inner bean qua getBean("id")

ID của inner bean bị bỏ qua làm tên lookup độc lập. Chuyển thành top-level `<bean id>` rồi dùng `<ref>` nếu thật sự cần lấy theo tên.

### Lỗi 8 — Cố đặt scope singleton để share inner bean

Scope trên inner bean không được dùng theo cách của top-level bean. Nếu cần share một resource, top-level singleton và `ref` là thiết kế đúng hơn.

### Lỗi 9 — Tưởng inner bean giống nested collection

`<list><list>...</list></list>` chỉ mô tả dữ liệu lồng nhau, không tạo bean definition cho mỗi list. `<bean>` lồng mới là inner bean.

### Lỗi 10 — Dùng inner bean cho tài nguyên cần ownership rõ

Một DB pool/client có shutdown phức tạp nên có top-level configuration/lifecycle thích hợp. Đừng ẩn resource quan trọng trong một constructor argument chỉ vì XML ngắn hơn.

### Lỗi 11 — Đặt collection merge trên parent

Phải đặt `merge="true"` trên child inherited collection. Parent flag không thực hiện việc merge mong muốn.

### Lỗi 12 — Merge khác loại collection

Một parent `<map>` và child `<list merge="true">` không thể merge theo cơ chế collection inheritance.

### Lỗi 13 — Cho rằng Map/Set giữ insertion order như List

List có thứ tự; Map/Set không có ordering guarantee phù hợp cho nghiệp vụ trong abstraction chung. Dùng một cấu trúc có order rõ nếu requirement cần.

### Lỗi 14 — Không phân biệt null value với absent key

`map.get(key)==null` không nói key có tồn tại không. Dùng `containsKey` nếu semantics cần phân biệt.

### Lỗi 15 — Đọc chỉ XML mà không xét Java constructors

XML parse hợp lệ không đảm bảo BeanFactory tạo bean thành công. Java parameter types, constructor overloads, null constraints và validation có thể làm startup lỗi.

### Lỗi 16 — Viết sai namespace/schema hoặc đặt phần tử không đúng cấp

`<null/>`, `<entry>`, `<list>` và `<bean>` phải nằm trong cấu trúc mà Spring Beans XML schema hỗ trợ. Khi parser báo lỗi validation, đối chiếu đúng nesting trước khi sửa Java code.

### Lỗi 17 — Trông chờ cấu hình collection luôn immutable

`final Map` chỉ cố định reference. Nếu cần immutable configuration, defensive copy sâu hoặc immutable records theo thiết kế.

### Lỗi 18 — Lạm dụng quá nhiều lớp XML lồng nhau

Đến khi XML thành map of map of list of map, việc hiểu và test mất nhiều công. Cân nhắc Java configuration hoặc typed properties với schema/validation rõ.

## 19. Cách kiểm thử nhanh

### Kiểm thử null

Sau khi tạo context:

```java
ReleasePlan plan = context.getBean(ReleasePlan.class);
if (plan.note() != null) {
    throw new AssertionError("note must be null");
}
```

Đây là snippet đặt trong project demo với biến `context` phù hợp. Nó kiểm chứng **Java value**, không chỉ rằng XML có `<null/>`.

### Kiểm thử nested collections

```java
if (!plan.channels().get("weekday")
        .equals(java.util.List.of("email", "sms"))) {
    throw new AssertionError("weekday channels");
}

if (!plan.stages().get(0).get(1).equals("build")) {
    throw new AssertionError("stage order");
}
```

Kiểm tra shape ở **nhiều mức nesting**, tránh chỉ assert collection size.

### Kiểm thử inner bean

```java
if (context.containsBean("embeddedContact")) {
    throw new AssertionError("inner bean must not be top-level");
}

if (plan.contact() == context.getBean("sharedContact")) {
    throw new AssertionError("inner should be separate from shared contact");
}
```

Các checks này dựa trên XML của demo. Việc cố tình đặt `id="embeddedContact"` trong inner definition làm rõ ID ấy không trở thành bean name công khai.

### Kiểm thử context startup

Nếu XML chứa null trong non-null constructor, nested value sai type hoặc schema nesting không hợp lệ, integration test tạo `ClassPathXmlApplicationContext("beans.xml")` sẽ giúp phát hiện sớm khi startup.

## 20. Bài tập áp dụng

### Bài 1 — Phân biệt null với empty string

Đổi:

```xml
<constructor-arg index="0"><null/></constructor-arg>
```

thành:

```xml
<constructor-arg index="0" value=""/>
```

Dự đoán: `plan.note() == null` chuyển thành false; `plan.note().isEmpty()` thành true. Giải thích vì sao đây là thay đổi giá trị chứ không phải vấn đề XML parsing.

### Bài 2 — Map chứa list có phần tử null

Thêm:

```xml
<entry key="maintenance">
    <list>
        <value>email</value>
        <null/>
    </list>
</entry>
```

Kiểm tra `plan.channels().get("maintenance").size()==2` và phần tử index 1 là null. Lưu ý `String.join` có semantics riêng với null elements; không dùng output của demo gốc để suy luận trường hợp có phần tử null.

### Bài 3 — Thay inner bằng top-level ref

Đổi constructor arg số 3 của `releasePlan` thành:

```xml
<constructor-arg index="3">
    <ref bean="sharedContact"/>
</constructor-arg>
```

Dự đoán `inner-is-shared` trong demo đổi thành true vì `releasePlan` nhận top-level singleton `sharedContact` thay vì tự tạo inner `Contact`.

### Bài 4 — Thêm tầng Map vào List

Mở rộng Java model để nhận `List<Map<String,String>>`, cấu hình `<list>` gồm nhiều `<map>`. Assert keys/values từng map và giải thích khác với `Map<String,List<String>>` hiện có.

### Bài 5 — Thử collection merging

Tạo parent bean definition abstract với property `List<String> rules`, tạo child với `<list merge="true">`. Verify parent items đứng trước child items. Di chuyển `merge="true"` lên parent và so kết quả để hiểu semantics.

### Bài 6 — Khởi tạo không hợp lệ

Đổi `ReleasePlan` constructor parameter note từ `String` thành primitive `int` nhưng vẫn dùng `<null/>`. Dự đoán bean creation failure và thảo luận cách thiết kế optional numeric value an toàn.

## 21. Câu hỏi ôn tập có đáp án

**Câu 1.** `<null/>` khác `value=""` như thế nào?

**Đáp:** `<null/>` tạo Java null; `value=""` truyền chuỗi rỗng với String target.

**Câu 2.** XML `<map><entry key="x"><list>...</list></entry></map>` phù hợp với type Java nào?

**Đáp:** `Map<String,List<T>>` khi các element types phù hợp và conversion thành công.

**Câu 3.** `<list><list>...</list></list>` có tạo inner beans không?

**Đáp:** Không. Nó tạo nested collections. Inner bean yêu cầu phần tử `<bean>` lồng.

**Câu 4.** Inner bean có thể lấy bằng `getBean("embeddedContact")` nếu nó có id không?

**Đáp:** Không. ID/name của inner bean không trở thành public bean identifier.

**Câu 5.** Scope gắn trên inner bean có điều khiển singleton/prototype lookup độc lập không?

**Đáp:** Không. Inner bean được tạo với enclosing bean và scope flag nội bộ bị bỏ qua.

**Câu 6.** Một top-level bean `sharedContact` được tham chiếu hai lần bằng `ref` khác gì khai báo hai inner beans?

**Đáp:** Nếu sharedContact singleton, hai references thường tới cùng managed instance. Hai inner definitions tách biệt sẽ tạo collaborator instances theo enclosing objects.

**Câu 7.** Merge `<list>` đặt ở đâu?

**Đáp:** Trên child collection trong bean definition kế thừa, không phải parent.

**Câu 8.** Có thể merge parent map và child list không?

**Đáp:** Không. Merge yêu cầu compatible collection types.

**Câu 9.** `<entry key="unknown"><null/></entry>` khác không khai báo key đó không?

**Đáp:** Có. Trong trường hợp thứ nhất `containsKey("unknown")` là true nhưng `get` trả null; trường hợp thứ hai key vắng mặt.

**Câu 10.** Spring có thể dùng Java generic types để chuyển string values thành Integer trong collection không?

**Đáp:** Có khi metadata của injection point rõ và type conversion hỗ trợ. Dữ liệu sai format vẫn gây lỗi.

**Câu 11.** `<ref bean="sharedClient"/>` và `<value>sharedClient</value>` có tương đương không?

**Đáp:** Không. Ref lấy object bean; value là string literal.

**Câu 12.** Nếu outer singleton được tạo một lần, inner bean có nhất thiết được đăng ký như singleton top-level không?

**Đáp:** Không. Inner bean là anonymous definition được tạo khi outer được dựng; nó không có public bean ID độc lập.

**Câu 13.** `final List` có luôn immutable không?

**Đáp:** Không. `final` giữ reference; có thể sửa nội dung list nếu implementation mutable. Dùng defensive copies khi cần.

**Câu 14.** Có nên dùng inner bean cho connection pool shared bởi cả hệ thống không?

**Đáp:** Thường không. Nên có top-level managed resource bean với lifecycle/ownership rõ ràng và inject qua `ref`.

## 22. Tài liệu chính thức

- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html): giải thích `<null/>`, inner beans, collections, nested values, collection merging và strongly typed collections.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): BeanDefinition, bean metadata và scope.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, resource lifecycle.
- [Spring Framework — Dependencies](https://docs.spring.io/spring-framework/reference/core/beans/dependencies.html): constructor/property injection và reference semantics.
- [Spring Framework 6.2 Javadoc — ClassPathXmlApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/support/ClassPathXmlApplicationContext.html): XML context bootstrap.
- [Spring Framework 6.2 Javadoc — BeanDefinition](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html): metadata bean definition.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): chuyển đổi kiểu khi bind/inject values.

**Kết luận:** Spring XML không chỉ mô tả bean names và classes mà còn mô tả **đồ thị giá trị object**. `<null/>` là Java null thực, nested `<list>`/`<map>` biểu diễn collection structures, còn `<bean>` lồng tạo một anonymous collaborator gắn với enclosing bean. Muốn cấu hình đúng, luôn đối chiếu **Java constructor/setter types**, phân biệt **inner bean với top-level ref**, và kiểm thử cả **giá trị, shape collection, scope và lifecycle**.
