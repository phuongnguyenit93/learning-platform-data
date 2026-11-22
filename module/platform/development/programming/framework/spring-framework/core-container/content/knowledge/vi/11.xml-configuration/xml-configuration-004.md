# Cấp thuộc tính qua `<property>`, `value` và `ref` trong Spring XML

## 1. Vì sao XML cần phân biệt giá trị và tham chiếu bean?

Trong Spring IoC Container, XML bean definition mô tả cách tạo object, những thuộc tính cần cấu hình và các bean mà object phụ thuộc. Khi dùng JavaBeans-style setter injection, phần tử `<property>` là cách trực tiếp để thiết lập một property sau khi Spring tạo object.

Hai dạng quan trọng nhất:

```xml
<bean id="mailService" class="demo.MailService">
    <property name="senderName" value="System"/>
    <property name="repository" ref="mailRepository"/>
</bean>

<bean id="mailRepository" class="demo.InMemoryMailRepository"/>
```

Đây là **đoạn minh họa**, không chạy độc lập khi chưa có hai Java classes tương ứng. Nó diễn đạt hai hành động khác nhau:

- `value="System"`: đưa **giá trị dạng văn bản** vào property `senderName`, Spring chuyển kiểu khi đích cần kiểu khác `String`.
- `ref="mailRepository"`: tìm **bean đã đăng ký** dưới tên `mailRepository`, rồi đưa **reference đến object đó** vào property `repository`.

Khi `MailService` định nghĩa `setSenderName(String)` và `setRepository(MailRepository)`, Spring có thể gọi hai setters sau khi tạo service. Nếu `mailRepository` là singleton, service được nối tới đúng managed singleton đó, không phải một bản sao được tạo từ chuỗi `"mailRepository"`.

Mục tiêu của bài học:

1. Hiểu cú pháp `<bean>`/`<property>` và hợp đồng JavaBean property.
2. Dùng `value` cho `String`, số, boolean, enum và những kiểu có converter/editor phù hợp.
3. Dùng `ref` để nối các beans, hiểu bean name, alias, scope và khởi tạo dependency.
4. Biết dạng attribute, nested elements `<value/>`, `<ref/>`, `<idref/>`, `<null/>` và inner bean.
5. Cấp collection `<list/>`, `<set/>`, `<map/>`, `<props/>` bằng values và bean references.
6. So sánh `p:property`/`p:property-ref` với cú pháp `<property>` truyền thống.
7. Phân biệt injection lúc tạo bean, property placeholders và Spring Expression Language.
8. Chẩn đoán lỗi setter, type conversion, bean references, schema và vòng phụ thuộc.
9. Chạy ví dụ Java 17+ với Spring Framework 6.2 và XML hoàn chỉnh, xác minh kết quả và identity.

## 2. Đọc một `<property>` từ trong ra ngoài

Cấu hình:

```xml
<bean id="reportService" class="demo.ReportService">
    <property name="title" value="Monthly"/>
</bean>
```

Ý nghĩa mỗi thành phần:

| Thành phần | Diễn giải |
| --- | --- |
| `bean` | Khai báo một bean definition trong Spring XML beans namespace |
| `id="reportService"` | Tên dùng để lookup/`ref` tới bean |
| `class="demo.ReportService"` | Class Spring cần load và tạo instance theo bean definition |
| `property` | Một thuộc tính trên object mới tạo cần được thiết lập |
| `name="title"` | Tên JavaBean property: thông thường tương ứng `setTitle(...)` |
| `value="Monthly"` | Giá trị literal sẽ được chuyển sang kiểu property đích nếu cần |

Cấu hình này gần với thao tác Java:

```java
ReportService service = new ReportService();
service.setTitle("Monthly");
```

Hai đoạn trên chỉ minh họa ý tưởng. Spring thực tế còn quản lý bean definition, scopes, lifecycle callbacks, bean post-processors và proxying phù hợp. **Không** coi XML property injection là một macro đơn giản thay thế mọi cơ chế Spring bằng `new`.

### 2.1. JavaBean property không bắt buộc là public field

Ví dụ class:

```java
package demo;

public class ReportService {
    private String title;

    public void setTitle(String title) {
        this.title = title;
    }

    public String getTitle() {
        return title;
    }
}
```

Setter `setTitle(String)` tạo property writable tên `title`, dù field `title` là `private`. Spring thường thiết lập property thông qua JavaBeans property descriptor / setter. Chỉ có field tên `title` mà không có setter phù hợp **không đủ** cho một `<property name="title">` thông thường.

Không phải cứ field `private` là bất khả thi để inject bằng Spring nói chung: annotation field injection và một số custom binding mechanisms có thể làm khác. Nhưng ở **Spring XML `<property>` setter injection chuẩn**, điều người viết cần kiểm tra đầu tiên là **writable property**.

### 2.2. Phân biệt constructor injection và setter injection

Hai cách có thể cùng tạo quan hệ dependency nhưng khác thời điểm:

```xml
<!-- Constructor injection -->
<bean id="serviceA" class="demo.ServiceA">
    <constructor-arg ref="repository"/>
</bean>

<!-- Setter/property injection -->
<bean id="serviceB" class="demo.ServiceB">
    <property name="repository" ref="repository"/>
</bean>
```

Trong constructor injection, Spring phải resolve argument trước khi gọi constructor `ServiceA`. Với property injection, Spring tạo `ServiceB` trước, rồi điền property `repository` khi populate bean.

**Thiết kế:** dependency cốt lõi mà object không thể hợp lệ nếu thiếu thường phù hợp constructor injection; setter injection thích hợp với cấu hình phụ trợ, dependency có thể thay thế, hoặc lớp thư viện được thiết kế theo JavaBeans setters. Việc chọn cách nào còn phụ thuộc class API thực tế và bean lifecycle, không phải quy tắc “mọi setter đều xấu”.

### 2.3. Spring XML có cần `@Autowired` không?

Không. Bean definitions và property values trong XML có thể được Spring áp dụng mà class hoàn toàn không chứa Spring annotations.

```java
public class Sender {
    private String signature;
    public void setSignature(String signature) {
        this.signature = signature;
    }
}
```

Cùng:

```xml
<bean id="sender" class="demo.Sender">
    <property name="signature" value="Team"/>
</bean>
```

Nếu package/classpath phù hợp, bean được cấu hình bằng XML setter. Annotation processing infrastructure chỉ cần khi ứng dụng **cũng sử dụng** `@Autowired`, `@Value`, `@PostConstruct` và những annotations liên quan. Không cần bật component scan để đăng ký class đã được khai báo tường minh trong XML.

## 3. `value`: truyền một literal rồi chuyển kiểu

Dạng ngắn thường gặp:

```xml
<property name="displayName" value="Catalog"/>
<property name="retryLimit" value="3"/>
<property name="active" value="true"/>
```

Với các setter tương ứng:

```java
public void setDisplayName(String displayName) { ... }
public void setRetryLimit(int retryLimit) { ... }
public void setActive(boolean active) { ... }
```

Đây là các **fragments minh họa**; các Java method bodies `...` đại diện phần triển khai được bỏ qua, không phải một chương trình hoàn chỉnh. Trên bean class thực, Spring đọc `"3"` dưới dạng text và sử dụng type conversion infrastructure để đặt vào `int`, và đọc `"true"` để đặt vào `boolean`.

Không cần khai báo kiểu trong từng attribute `value` nếu Spring có thể suy ra từ writable property và converter/editor tương ứng. Tuy nhiên, một text literal **không phải Java expression** được tính tùy tiện. `value="1+2"` gán chuỗi `1+2` cho `String`; không tự biến thành số 3 chỉ vì nó trông giống phép toán.

### 3.1. Ngữ nghĩa của dấu nháy XML

Ví dụ:

```xml
<property name="name" value="System"/>
```

Dấu nháy ở đây thuộc **cú pháp XML attribute**, không phải một phần của giá trị String được gán vào setter. Setter nhận `System`, không nhận hai ký tự dấu `"` bao quanh.

### 3.2. Chuyển kiểu và lỗi conversion

Một property Java `int retryLimit` nhận `value="3"` thường hoạt động. Nhưng:

```xml
<property name="retryLimit" value="three"/>
```

có thể gây `TypeMismatchException` / `ConversionFailedException` trong chuỗi `BeanCreationException` hoặc exception tương đương khi Spring thiết lập property. **XSD không tự hiểu** rằng `retryLimit` là Java `int` của class đó; việc xác minh giá trị xảy ra ở tầng binding/bean creation.

Các kiểu thường gặp:

| Kiểu property đích | Literal mẫu | Kết quả |
| --- | --- | --- |
| `String` | `value="hello"` | Chuỗi `hello` |
| `int`/`Integer` | `value="42"` | Số nguyên 42 nếu conversion hợp lệ |
| `boolean`/`Boolean` | `value="true"` | Boolean true |
| `long`/`Long` | `value="5000"` | Số nguyên dài |
| `double`/`Double` | `value="2.5"` | Số thực theo converter/editor |
| `Duration`/`Path`/kiểu tùy biến | Chuỗi phụ thuộc conversion service | Chỉ dùng khi có hỗ trợ conversion thích hợp |
| Enum `Mode` | `value="FAST"` | Có thể chuyển sang enum constant FAST bằng cơ chế phù hợp |
| `Class<?>` | `value="java.lang.String"` | Có thể load class khi type converter/editor hỗ trợ |

**Không mặc định mọi kiểu đều tự chuyển được.** Với domain-specific types, có thể cần `ConversionService`, `Converter`, `PropertyEditor` hoặc factory method phù hợp. Hãy kiểm thử trường hợp thật thay vì suy luận chỉ từ literal.

### 3.3. Dạng nested `<value/>`

Thay vì attribute:

```xml
<property name="displayName" value="Catalog"/>
```

có thể dùng sub-element:

```xml
<property name="displayName">
    <value>Catalog</value>
</property>
```

Hai dạng đều biểu đạt literal value. Dạng nested thuận tiện khi muốn dùng XML content, cấu trúc rõ hoặc typing hints thích hợp. Ví dụ:

```xml
<property name="retryLimit">
    <value type="int">3</value>
</property>
```

`type="int"` là gợi ý/khai báo type ở phần tử `<value>` theo schema tương ứng, không phải lý do để đặt string `three` vào một setter int và mong nó tự hợp lệ.

### 3.4. Empty String khác null

Một property kiểu `String`:

```xml
<property name="note" value=""/>
```

nghĩa là truyền **chuỗi rỗng** `""`, còn:

```xml
<property name="note">
    <null/>
</property>
```

nghĩa là truyền **Java `null`**. Hai trạng thái có thể làm ứng dụng khác nhau:

```java
"".isEmpty()      // true
note == null     // true nếu note được set null
```

Các dòng Java chỉ minh họa. Một setter nhận primitive như `int` không thể nhận Java null theo cách bình thường; nullable là vấn đề của wrapper/reference type và contract của property.

### 3.5. XML escaping không phải Spring conversion

Trong XML attribute, ký tự `&` phải viết là `&amp;`; dấu `<` là `&lt;`. Ví dụ:

```xml
<property name="displayName" value="Sales &amp; Operations"/>
```

Spring nhận chuỗi `Sales & Operations` sau khi XML parser xử lý entity. Nếu viết `value="Sales & Operations"`, file có thể không well-formed; lỗi xảy ra **trước** khi setter injection được xét.

## 4. `ref`: đưa vào object của một bean khác

Ví dụ:

```xml
<bean id="repository" class="demo.InMemoryRepository"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="repository"/>
</bean>
```

Với Java API:

```java
public void setRepository(Repository repository) {
    this.repository = repository;
}
```

Đây là các đoạn minh họa; cần class/interface liên quan. `ref="repository"` là **tên bean** đã được đăng ký; Spring resolve tên đó rồi inject reference đến instance phù hợp.

Không được nhầm:

```xml
<property name="repository" value="repository"/>
```

Dòng này biểu diễn literal string `"repository"`. Nó **không** tự tìm bean có tên `repository`. Nếu setter cần `Repository` thì type conversion không mặc định đổi string bean name thành managed dependency đúng như `ref`.

### 4.1. Các bean không cần cùng một XML file

`ref` lookup theo **bean registry/hierarchy**, không phụ thuộc yêu cầu hai bean definitions nằm cạnh nhau trong cùng file. Spring có thể tải nhiều XML resources vào cùng context hoặc dùng parent context; `ref` có thể trỏ bean thuộc cùng container hoặc bean có thể nhìn thấy từ parent.

Ví dụ:

```xml
<import resource="repository-context.xml"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="repository"/>
</bean>
```

Đây là đoạn minh họa phải nằm trong một `<beans>` root hợp lệ. File `repository-context.xml` có thể cung cấp definition `repository`. Spring cần đọc và xử lý cả hai resources phù hợp; chỉ ghi `ref` không tự động tìm kiếm một JAR/file tùy ý.

### 4.2. Bean name và alias

```xml
<bean id="repository" class="demo.InMemoryRepository"/>
<alias name="repository" alias="catalogStore"/>

<bean id="service" class="demo.CatalogService">
    <property name="repository" ref="catalogStore"/>
</bean>
```

Với alias `catalogStore`, `ref` có thể dùng alias của bean; nó vẫn hướng tới cùng definition/managed instance, không tạo một repository mới.

### 4.3. Dạng nested `<ref bean="..."/>`

Hai cách tương đương về ý nghĩa:

```xml
<property name="repository" ref="repository"/>
```

và:

```xml
<property name="repository">
    <ref bean="repository"/>
</property>
```

Dạng thứ hai hữu ích khi muốn viết cấu hình lồng nhau nhất quán với `<list>`, `<map>` hoặc nested bean. Có thể gặp:

```xml
<property name="repository">
    <ref parent="repository"/>
</property>
```

`<ref parent="repository"/>` có ý nghĩa đặc biệt: chọn definition tên `repository` từ **parent BeanFactory/ApplicationContext**, hữu ích khi child context có một bean cùng tên che khuất bean parent. Đây là tình huống nâng cao; không dùng `parent` thay `bean` theo thói quen.

Các XML snippets trên không phải file standalone; cần root `<beans>` và bean definitions thực tế.

### 4.4. Thời điểm resolve reference

Khi Spring tạo bean `service` với một writable property `repository` nhận `ref="repository"`:

1. BeanFactory xác định definition của `service`.
2. Tạo instance `service` theo constructor/factory method phù hợp.
3. Khi populate property, BeanFactory cần một instance `repository`.
4. Nếu dependency chưa được tạo và phải eager-resolve, Spring tạo/chuẩn bị repository theo scope và lifecycle.
5. Spring gọi `setRepository(managedRepository)`.
6. Bean tiếp tục init callbacks/post-processors theo cơ chế Spring.

Vì vậy `ref` là một dependency edge trong bean graph. Một bean được gắn `lazy-init="true"` vẫn có thể được tạo khi có bean eager khác cần nó qua `ref`.

### 4.5. Scope và reference identity

Nếu `repository` là singleton mặc định, mọi consumer được inject đúng bean đó thường chia sẻ reference managed. Nếu repository là prototype, mỗi lần container resolve prototype dependency sẽ tạo instance theo scope; một singleton service đã nhận prototype qua setter **không tự nhận prototype mới ở mỗi lần gọi business method**.

Nếu dependency được AOP proxy/scoped proxy, reference mà service nhận có thể là proxy do BeanFactory cung cấp, không phải raw object trả về từ constructor. `ref` mang semantics của container, khác hẳn tự gọi `new Repository()` trong setter.

### 4.6. Missing reference khác missing setter

Với:

```xml
<property name="repository" ref="doesNotExist"/>
```

Spring có thể báo `NoSuchBeanDefinitionException` trong nguyên nhân `BeanCreationException` / `BeanDefinitionStoreException` tùy giai đoạn. Nhưng nếu bean tồn tại mà class `CatalogService` không có writable property `repository`, đó là loại lỗi **invalid property name** (ví dụ `NotWritablePropertyException`), không phải missing bean.

Cách debug đúng là đọc **root cause** và xác định bean name/property name bị lỗi.

## 5. `<idref>`: truyền bean name dưới dạng chuỗi, không phải instance

Spring có phần tử:

```xml
<property name="repositoryBeanName">
    <idref bean="repository"/>
</property>
```

Ý nghĩa: property `repositoryBeanName` nhận chuỗi `"repository"`, **không** nhận một object `Repository`. Spring có thể xác minh bean name được trỏ tới tồn tại khi xử lý dependency, giúp giảm lỗi typo so với:

```xml
<property name="repositoryBeanName" value="repository"/>
```

Trong ví dụ thứ hai, `value` chỉ cung cấp string mà không diễn đạt một `idref` để validate sự tồn tại của bean name. `idref` hữu ích cho infrastructure nhận **tên bean dưới dạng String**, chẳng hạn khi một thành phần khác sẽ tự dùng tên đó theo contract.

| Cú pháp | Setter nhận gì? | Có resolve object như dependency không? |
| --- | --- | --- |
| `value="repository"` | Chuỗi literal `"repository"` | Không |
| `ref="repository"` | Bean object/proxy dưới tên `repository` | Có |
| `<ref bean="repository"/>` | Bean object/proxy dưới tên `repository` | Có |
| `<idref bean="repository"/>` | String `"repository"`, với kiểm tra tên phù hợp | Không đưa object vào property |
| `<value>repository</value>` | Chuỗi literal `"repository"` | Không |

**Đừng viết `<idref>` chỉ để thay `ref` khi cần inject dependency object.** Tên giống nhau nhưng semantics khác nhau hoàn toàn.

## 6. Cấu hình collection bằng `value`, `ref` và nested elements

Một property không nhất thiết là scalar hoặc một bean duy nhất. Spring XML hỗ trợ `<list>`, `<set>`, `<map>`, `<props>` dưới `<property>`.

### 6.1. `<list>` chứa nhiều values

```xml
<bean id="reportService" class="demo.ReportService">
    <property name="regions">
        <list>
            <value>north</value>
            <value>south</value>
        </list>
    </property>
</bean>
```

Nếu Java setter là `setRegions(List<String>)`, Spring có thể tạo list và truyền vào bean. Thứ tự `north`, `south` có ý nghĩa vì `List` bảo tồn thứ tự phần tử.

Không nhầm với **collection injection by-type** như `@Autowired List<SomeInterface>`: ở đây collection elements được **khai báo tường minh trong XML**, không tự động thu thập mọi bean cùng kiểu chỉ vì property mang kiểu `List`.

### 6.2. `<list>` chứa references tới beans

```xml
<bean id="smsChannel" class="demo.SmsChannel"/>
<bean id="mailChannel" class="demo.MailChannel"/>

<bean id="dispatcher" class="demo.Dispatcher">
    <property name="channels">
        <list>
            <ref bean="smsChannel"/>
            <ref bean="mailChannel"/>
        </list>
    </property>
</bean>
```

Đây là XML minh họa cần các classes `SmsChannel`, `MailChannel`, `Dispatcher` và setter `setChannels(List<...>)` phù hợp. Các list entries là **bean references**, không phải string `"smsChannel"` và `"mailChannel"`.

### 6.3. `<map>`: value hoặc bean reference

```xml
<property name="regionLabels">
    <map>
        <entry key="north" value="N"/>
        <entry key="south" value="S"/>
    </map>
</property>
```

Ở đây map keys/values là những literals. Nếu cần tham chiếu một bean trong map:

```xml
<property name="handlers">
    <map>
        <entry key="main" value-ref="mainHandler"/>
    </map>
</property>
```

`value-ref` trên `<entry>` biểu diễn bean reference. Nó khác `value="mainHandler"`, vốn là string literal. Một số dạng cấu hình cho phép `key-ref` nếu map key cũng là bean object.

### 6.4. `<set>` và `<props>`

```xml
<property name="roles">
    <set>
        <value>reader</value>
        <value>writer</value>
    </set>
</property>

<property name="codes">
    <props>
        <prop key="north">N</prop>
        <prop key="south">S</prop>
    </props>
</property>
```

`<set>` diễn đạt tập phần tử; `<props>` phù hợp Java `Properties` và các giá trị chuỗi. Cả hai là **XML fragments** cần bean class có setter tương ứng.

Đối với map/set, đừng xây nghiệp vụ dựa vào iteration order nếu contract không quy định. Nếu cần thứ tự rõ, dùng `List` hoặc cấu trúc domain có thứ tự.

### 6.5. Type conversion trong generic collections

Nếu setter nhận `List<Integer>`, Spring có thể chuyển các `<value>1</value>`, `<value>2</value>` sang Integer nhờ generic type information và conversion infrastructure phù hợp.

```xml
<property name="levels">
    <list value-type="java.lang.Integer">
        <value>1</value>
        <value>2</value>
    </list>
</property>
```

`value-type` trong `<list>` giúp chỉ rõ intended element type theo Spring XML schema. Nhưng nếu class thiếu setter hoặc converter không hỗ trợ kiểu tùy biến, việc khai báo generic/`value-type` không tự sửa được mọi lỗi runtime.

### 6.6. Collection merging là một chủ đề khác

Khi dùng **parent-child bean definitions** qua `parent="..."` trong XML, Spring cho phép một số collection metadata từ child merge với parent nếu `merge="true"` được cấu hình đúng. Đây là **merging bean definition values**, không giống Java `List.addAll` chạy tùy lúc.

Đừng viết `merge="true"` tùy tiện rồi mong merge các collections của hai singleton beans khác nhau. Cần hiểu parent/child bean definition relationship và quy tắc từng collection type.

## 7. Inner bean: tạo collaborator dùng riêng trong một property

Đôi khi collaborator không cần tên độc lập trong registry:

```xml
<bean id="service" class="demo.CatalogService">
    <property name="formatter">
        <bean class="demo.SimpleFormatter">
            <property name="prefix" value="SVC: "/>
        </bean>
    </property>
</bean>
```

Spring xử lý `<bean>` lồng trong `<property>` như một **inner bean**. Đặc trưng:

- Thường không có bean name công khai để lookup độc lập từ `ApplicationContext`.
- Instance có mối quan hệ vòng đời/ownership với bean chứa theo semantics của inner bean.
- Không dùng inner bean khi nhiều consumers cần chia sẻ cùng một managed singleton named bean.
- Nếu chỉ có một consumer và collaborator hoàn toàn nội bộ, cấu hình này có thể ngắn gọn.

Một inner bean không đồng nghĩa **mọi lần gọi service method đều tạo mới formatter**. Bean construction vẫn diễn ra khi Spring xây bean chứa và populate property, không phải tự động mỗi business method call.

### 7.1. Inner bean khác `ref`

Hai kiểu nối khác nhau:

```xml
<!-- Tham chiếu bean named, có thể chia sẻ. -->
<property name="formatter" ref="sharedFormatter"/>
```

và:

```xml
<!-- Định nghĩa object riêng bên trong consumer. -->
<property name="formatter">
    <bean class="demo.SimpleFormatter"/>
</property>
```

Dạng đầu lấy managed reference của bean `sharedFormatter`. Dạng thứ hai tạo một inner bean definition, không tự tạo một top-level bean `sharedFormatter`.

### 7.2. Inner bean và scopes

Tài liệu Spring mô tả inner bean thường dùng cùng lifecycle context với bean chứa; ngay cả khi bạn chỉ định một scope khác ở inner definition, hãy hiểu các quy tắc thực tế của Spring trước khi dựa vào đó. Với dependency cần tái sử dụng, hoặc scope không tầm thường (request/session), named beans và scoped proxies có thể rõ ràng hơn.

## 8. `p` namespace: cú pháp gọn của `<property>`

Với Spring XML, bạn có thể chọn dạng rõ ràng:

```xml
<bean id="service" class="demo.CatalogService">
    <property name="label" value="Catalog"/>
    <property name="repository" ref="repository"/>
</bean>
```

Hoặc dùng `p` namespace:

```xml
<bean id="service" class="demo.CatalogService"
      p:label="Catalog"
      p:repository-ref="repository"/>
```

Cần khai báo ở root `<beans>`:

```xml
xmlns:p="http://www.springframework.org/schema/p"
```

**`p` namespace không có XSD riêng**. Nó được hỗ trợ trực tiếp bởi Spring bean XML parser; không cần tự bịa `spring-p.xsd` trong `xsi:schemaLocation`.

### 8.1. Quy tắc value và ref

| Dạng đầy đủ | Dạng `p` |
| --- | --- |
| `<property name="title" value="Hello"/>` | `p:title="Hello"` |
| `<property name="repository" ref="repository"/>` | `p:repository-ref="repository"` |
| `<property name="enabled" value="true"/>` | `p:enabled="true"` |
| `<property name="timeout" value="30"/>` | `p:timeout="30"` |

`p:repository="repository"` **không** tương đương với `p:repository-ref="repository"` nếu property cần object Repository. Hậu tố `-ref` chính là dấu hiệu yêu cầu container lookup bean.

### 8.2. Hạn chế của shorthand

`p` tiện cho scalar properties và references ngắn. Với list/map/inner beans hoặc cấu hình dài, nested `<property>` dễ đọc hơn.

Một tên JavaBean property tự kết thúc bằng `Ref` (ví dụ `accountRef`) có thể gây nhầm với quy ước hậu tố `-ref` trong p namespace, vì vậy XML dạng đầy đủ đáng tin cậy hơn khi đặt tên phức tạp. Đừng trộn quá nhiều styles trong cùng một file nếu team khó bảo trì.

## 9. Property placeholders `${...}` và SpEL `#{...}`

Đây là hai cơ chế mở rộng áp dụng cho giá trị, nhưng không nên nhầm với `ref`.

### 9.1. `value` chứa placeholder

```xml
<property name="endpointUrl" value="${client.endpoint}"/>
```

Nếu application cài đặt một `PropertySourcesPlaceholderConfigurer` hoặc cấu hình môi trường tương ứng, `${client.endpoint}` có thể được resolve từ properties sources thành chuỗi thực.

Trong môi trường Spring Framework thuần dùng XML, bạn có thể cấu hình:

```xml
<context:property-placeholder location="classpath:client.properties"/>
```

Cần khai báo `xmlns:context`, mapping XSD đúng và file `client.properties` ở classpath; context namespace handler hỗ trợ cơ chế đó. Khi placeholder không được resolve và không có fallback policy phù hợp, application có thể thất bại lúc xử lý/tạo bean.

**Không nhầm:** `value="${client.repository}"` cung cấp một giá trị chuỗi từ properties, không tự động biến nó thành bean reference, trừ khi bạn dùng thêm một cơ chế biểu thức/lookup có chủ đích.

### 9.2. SpEL bên trong value

```xml
<property name="region" value="#{'north'.toUpperCase()}"/>
```

Trong môi trường `ApplicationContext` có bean expression resolver thích hợp, Spring có thể đánh giá SpEL ở vị trí giá trị và trả `NORTH`. Đây là ví dụ minh họa cú pháp; SpEL không giống literal `value="north"`.

SpEL cũng có thể biểu diễn bean references, ví dụ `value="#{@repository}"` trong môi trường hỗ trợ expression resolver. Tuy nhiên, khi mục đích là inject một bean named đơn giản, `ref="repository"` rõ ràng hơn, có contract bean dependency trực tiếp và dễ debug.

### 9.3. Placeholder và bean reference thay đổi ý nghĩa cấu hình

| Cú pháp | Nguồn quyết định giá trị |
| --- | --- |
| `value="hello"` | Literal do XML cung cấp |
| `value="${app.label}"` | Property placeholder được resolver xử lý nếu cấu hình |
| `value="#{1 + 2}"` | SpEL expression được đánh giá nếu context hỗ trợ |
| `ref="repository"` | BeanFactory resolve bean name |
| `<idref bean="repository"/>` | String bean name có xác minh hợp lệ |

Một hệ thống có thể kết hợp placeholder với ref khi tên dependency đến từ cấu hình, nhưng lúc đó cần kiểm soát chặt chẽ tính hợp lệ và thời điểm resolve; không giả định mọi trường hợp `${...}` đều giống injection từ `@Autowired`.

## 10. Thứ tự khởi tạo, vòng đời và optional properties

### 10.1. Bean được tạo trước khi setter được gọi

Đối với setter injection thông thường:

```text
BeanDefinition được chọn
           |
           v
Constructor/factory method tạo instance
           |
           v
BeanFactory resolve property values / refs
           |
           v
Gọi các writable setters tương ứng
           |
           v
Aware callbacks, BeanPostProcessors, init callbacks
           |
           v
Managed bean sẵn sàng
```

Thứ tự chính xác của infrastructure callbacks/processor hooks có thể phức tạp hơn sơ đồ, nhưng **property population diễn ra trước các bước initialization tiêu chuẩn**. Vì vậy, nếu class cần property để hoạt động, không nên sử dụng nó trong constructor trước khi Spring gọi setter.

### 10.2. Setter không được khai báo thì sao?

Nếu XML không có `<property name="..." .../>`, Spring sẽ **không tự gán property đó** chỉ vì class có setter, trừ khi autowire/annotation/processor khác có nhiệm vụ làm vậy. Java field giữ giá trị mặc định (`null`, 0, false) hoặc giá trị do constructor/field initializer đặt.

Một dependency bắt buộc bị bỏ quên trong setter injection có thể không làm context fail ngay mà chỉ gây `NullPointerException` khi business method được gọi. Đó là lý do constructor injection thường thích hợp cho dependency không thể thiếu; với setter injection, cần validate state trong init method/`@PostConstruct` hoặc test context.

### 10.3. Constructor vs setter cycles

Một vòng phụ thuộc constructor A→B→A thường không thể resolve bằng cách tạo object thông thường. Setter-based cycles giữa singletons **có thể** được Spring xử lý trong một số cấu hình nhờ early references, nhưng không nên dựa vào đó làm thiết kế mặc định; đặc biệt khi có AOP proxies, scope khác và framework settings, vòng phụ thuộc vẫn có thể thất bại hoặc tạo object chưa hoàn tất lifecycle.

**Khuyến nghị:** refactor graph, tách responsibilities hoặc dùng dependency abstraction có chiều rõ, thay vì cố chuyển constructor injection sang setters chỉ để che vòng A↔B.

### 10.4. Property được gán một lần khi tạo bean, không phải cấu hình live

Thông thường `<property name="timeout" value="30"/>` đặt giá trị khi Spring tạo bean. Sau khi context đã refresh, sửa file XML trên ổ đĩa **không** tự động gọi lại setter hoặc thay đổi managed singleton. Nếu cần hot reload/dynamic configuration, phải thiết kế cơ chế refresh/lookup hoặc source of truth runtime riêng.

### 10.5. `@Autowired` và XML property có thể cùng tồn tại

Một class có thể được đăng ký bằng XML đồng thời chứa annotation injection, nếu context có post-processor hạ tầng cần thiết. Nhưng nếu cùng một dependency được set qua XML và annotation, thứ tự/ưu tiên giữa các injection mechanisms có thể gây bất ngờ. Hãy chọn **một nguồn cấu hình chịu trách nhiệm** cho từng property nếu có thể, và kiểm thử khi chuyển dần từ XML sang annotations.

## 11. Ví dụ Java 17+ hoàn chỉnh: literal value, ref, list/map, idref, null và p namespace

Dự án sử dụng Spring Framework 6.2.19, Gradle, Java 17. Không cần Spring Boot hoặc server. Tất cả domain classes là **plain Java classes**, không gắn `@Component` hay `@Autowired`.

Kết quả cần quan sát:

- String `prefix`, int `retryLimit`, boolean `enabled` nhận qua literal `value`.
- Object `CatalogRepository` và `DeliveryChannel` được nhận qua `ref`, cùng managed singletons.
- `tags` nhận một `List<String>`; `routes` nhận `Map<String,String>`.
- `repositoryName` nhận string của bean id bằng `<idref>`.
- `memo` nhận Java `null` qua `<null/>`.
- Bean `backupNotifier` dùng shorthand `p:repo-ref`, `p:prefix` và `p:enabled`.
- Chương trình kiểm tra cả kết quả nghiệp vụ và **reference identity** để phân biệt value/ref.

### 11.1. Cấu trúc dự án

```text
spring-xml-properties-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── CatalogRepository.java
        │       ├── DeliveryChannel.java
        │       ├── NotificationService.java
        │       └── Application.java
        └── resources/
            └── application-context.xml
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-xml-properties-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.Application'
}
```

Chạy bằng JDK 17+ và bản Gradle hỗ trợ JDK đang dùng. `spring-context` kéo theo Spring Beans/Core cần để đọc XML, resolve dependency và quản lý `ApplicationContext`.

### 11.2. `CatalogRepository.java`

`src/main/java/demo/CatalogRepository.java`:

```java
package demo;

public final class CatalogRepository {
    public String find(String id) {
        return "order-" + id;
    }
}
```

Class này không chứa annotation Spring. Có constructor no-argument ngầm định và được tạo bởi XML `<bean id="catalogRepository" .../>`.

### 11.3. `DeliveryChannel.java`

`src/main/java/demo/DeliveryChannel.java`:

```java
package demo;

public final class DeliveryChannel {
    private final String name;

    public DeliveryChannel(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

`DeliveryChannel` được khai báo với constructor argument bằng XML; `NotificationService` nhận nó bằng **property ref**. Hai cách injection có thể kết hợp trong cùng cấu hình nếu domain API thực sự cần.

### 11.4. `NotificationService.java`

`src/main/java/demo/NotificationService.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

public final class NotificationService {

    private CatalogRepository repo;
    private DeliveryChannel channel;
    private String prefix = "";
    private int retryLimit;
    private boolean enabled;
    private List<String> tags = List.of();
    private Map<String, String> routes = Map.of();
    private String repositoryName;
    private String memo;

    public void setRepo(CatalogRepository repo) {
        this.repo = repo;
    }

    public void setChannel(DeliveryChannel channel) {
        this.channel = channel;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public void setRetryLimit(int retryLimit) {
        this.retryLimit = retryLimit;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }

    public void setRoutes(Map<String, String> routes) {
        this.routes = routes;
    }

    public void setRepositoryName(String repositoryName) {
        this.repositoryName = repositoryName;
    }

    public void setMemo(String memo) {
        this.memo = memo;
    }

    public CatalogRepository getRepo() {
        return repo;
    }

    public DeliveryChannel getChannel() {
        return channel;
    }

    public String getPrefix() {
        return prefix;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public String getRepositoryName() {
        return repositoryName;
    }

    public List<String> getTags() {
        return tags;
    }

    public String notifyFor(String orderId) {
        if (!enabled) {
            return "disabled";
        }

        return prefix + repo.find(orderId)
                + " via " + channel.name()
                + " retries=" + retryLimit
                + " tags=" + tags
                + " north=" + routes.get("north")
                + " memo=" + (memo == null ? "none" : memo);
    }
}
```

Các setters là writable JavaBean properties. `notifyFor` cố ý không dùng Spring API: nó minh họa domain object chỉ nhận dependency đã được container cấp từ XML.

### 11.5. `application-context.xml`

`src/main/resources/application-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:p="http://www.springframework.org/schema/p"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalogRepository" class="demo.CatalogRepository"/>

    <bean id="emailChannel" class="demo.DeliveryChannel">
        <constructor-arg value="email"/>
    </bean>

    <bean id="notifier" class="demo.NotificationService">
        <property name="repo" ref="catalogRepository"/>

        <property name="channel">
            <ref bean="emailChannel"/>
        </property>

        <property name="prefix" value="INFO: "/>
        <property name="retryLimit" value="3"/>

        <property name="enabled">
            <value>true</value>
        </property>

        <property name="tags">
            <list>
                <value>ops</value>
                <value>mail</value>
            </list>
        </property>

        <property name="routes">
            <map>
                <entry key="north" value="N"/>
                <entry key="south" value="S"/>
            </map>
        </property>

        <property name="repositoryName">
            <idref bean="catalogRepository"/>
        </property>

        <property name="memo">
            <null/>
        </property>
    </bean>

    <bean id="backupNotifier"
          class="demo.NotificationService"
          p:repo-ref="catalogRepository"
          p:channel-ref="emailChannel"
          p:prefix="WARN: "
          p:retryLimit="1"
          p:enabled="false"/>
</beans>
```

**Vì sao không có XSD mapping cho `p`?** `p` là shorthand namespace do Spring core xử lý, không có file `spring-p.xsd` riêng. XML root khai `xmlns:p` nhưng `xsi:schemaLocation` chỉ cần cặp beans namespace và `spring-beans.xsd`.

**Vì sao `<idref bean="catalogRepository"/>` không nhận object repository?** Nó cấp **bean name string** vào `setRepositoryName(String)`. Ngược lại, `<property name="repo" ref="catalogRepository"/>` cấp một managed `CatalogRepository` vào `setRepo(...)`.

**Vì sao `<null/>` không giống `value=""`?** `setMemo(null)` sẽ khiến code in `memo=none`. Nếu đổi thành empty string, code in `memo=`; đó là khác biệt về dữ liệu.

### 11.6. `Application.java` và kết quả đầu ra

`src/main/java/demo/Application.java`:

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class Application {

    public static void main(String[] args) {
        try (var context =
                new ClassPathXmlApplicationContext(
                        "application-context.xml")) {

            CatalogRepository repository =
                    context.getBean("catalogRepository",
                            CatalogRepository.class);
            DeliveryChannel channel =
                    context.getBean("emailChannel",
                            DeliveryChannel.class);
            NotificationService notifier =
                    context.getBean("notifier",
                            NotificationService.class);
            NotificationService backup =
                    context.getBean("backupNotifier",
                            NotificationService.class);

            System.out.println("message = " +
                    notifier.notifyFor("42"));
            System.out.println("sameRepo = " +
                    (repository == notifier.getRepo()));
            System.out.println("sameChannel = " +
                    (channel == notifier.getChannel()));
            System.out.println("repositoryName = " +
                    notifier.getRepositoryName());
            System.out.println("enabled = " +
                    notifier.isEnabled());
            System.out.println("backupEnabled = " +
                    backup.isEnabled());
            System.out.println("backupPrefix = [" +
                    backup.getPrefix() + "]");
            System.out.println("backupSameRepo = " +
                    (repository == backup.getRepo()));
            System.out.println("tags = " +
                    notifier.getTags());
        }
    }
}
```

Chương trình tạo Spring application context, load bean definitions từ XML trong classpath và gọi các managed beans sau khi context được refresh. Nó không tự `new NotificationService()` ở main.

### 11.7. Chạy Gradle

Tại root `spring-xml-properties-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper:

```bash
./gradlew run --quiet
```

Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Stdout do `System.out.println` của chương trình tạo:

```text
message = INFO: order-42 via email retries=3 tags=[ops, mail] north=N memo=none
sameRepo = true
sameChannel = true
repositoryName = catalogRepository
enabled = true
backupEnabled = false
backupPrefix = [WARN: ]
backupSameRepo = true
tags = [ops, mail]
```

Gradle hoặc Spring logging có thể in thêm dòng ngoài những câu lệnh `System.out.println`. Kết quả trên mô tả output nghiệp vụ xác định cho source + XML đã cung cấp.

### 11.8. Giải thích kết quả

**`message`:** literal `prefix="INFO: "`, `retryLimit="3"` được Spring chuyển sang int, nested `<value>true</value>` được chuyển sang boolean, bean references tới repository/channel được cấp đúng, `tags` là list theo thứ tự khai báo, `routes.get("north")` là `N`, memo do `<null/>` nên hiển thị `none`.

**`sameRepo = true`:** `notifier` giữ managed singleton `catalogRepository` do `ref` cung cấp; không giữ chuỗi bean name.

**`sameChannel = true`:** nested `<ref bean="emailChannel"/>` giống về ngữ nghĩa object reference với `ref="emailChannel"` trong property. Nó không tạo thêm channel instance.

**`repositoryName = catalogRepository`:** đây là chuỗi nhờ `<idref>`, không phải object CatalogRepository. Khi dùng bean name làm dữ liệu hạ tầng, `idref` biểu đạt mục đích rõ hơn literal string.

**`backupEnabled = false` và `backupPrefix = [WARN: ]`:** `p:enabled="false"` và `p:prefix="WARN: "` là dạng ngắn của literal properties; dấu ngoặc vuông trong stdout cho phép nhìn rõ khoảng trắng cuối prefix.

**`backupSameRepo = true`:** `p:repo-ref="catalogRepository"` cũng cấp reference managed bean, tương đương dạng `<property name="repo" ref="catalogRepository"/>`.

**`tags = [ops, mail]`:** XML list đã được gán vào property và giữ thứ tự. Không cần component scanning hoặc annotation injection trong ba domain classes.

## 12. Chẩn đoán lỗi thường gặp

### 12.1. Sai tên property

XML:

```xml
<property name="retry" value="3"/>
```

trong khi class chỉ có `setRetryLimit(int)`. Spring có thể ném `NotWritablePropertyException` (thường được bọc trong `BeanCreationException`). Cách sửa là xác định **JavaBeans property name**, không phải đoán từ tên field hoặc tự bịa một thuộc tính XML.

### 12.2. Sai kiểu literal

XML:

```xml
<property name="retryLimit" value="many"/>
```

setter yêu cầu `int`, nên conversion thất bại. Đừng đổi setter sang `String` chỉ để startup thành công nếu domain thực sự cần số; sửa cấu hình/validations và test biến thể lỗi.

### 12.3. `value` thay vì `ref`

XML:

```xml
<property name="repo" value="catalogRepository"/>
```

trong khi setter cần `CatalogRepository`. Spring nhận một literal String rồi cố convert sang kiểu đích; thông thường nó không tự lookup bean. Sửa thành `ref="catalogRepository"`.

### 12.4. Sai bean name trong `ref`

XML:

```xml
<property name="repo" ref="catalogRepositorry"/>
```

Tên bị typo, nên BeanFactory không resolve được bean. Kiểm tra `id`/`name`/`alias` của bean đã khai báo, các XML files được import, profiles active và bean definitions sau khi parse.

### 12.5. Setter sai visibility/signature

Nếu class có method `void setRepo(CatalogRepository x)` nhưng không public trong một bối cảnh JavaBeans introspection thông thường, hoặc chỉ có `getRepo()`, property có thể không writable bằng standard setter binding. Sửa contract API phù hợp, hoặc chuyển sang constructor injection nếu dependency bắt buộc.

### 12.6. Lẫn `ref` với `idref`

`idref` truyền String bean name, không truyền instance. Nếu setter là `setRepo(CatalogRepository)`, `<idref bean="catalogRepository"/>` không đúng semantic. Hãy dùng `<ref bean="catalogRepository"/>`.

### 12.7. Literal chứa placeholder nhưng chưa có resolver

`value="${app.repo}"` có thể không được xử lý nếu cấu hình placeholder resolution thiếu hoặc property không được cung cấp. Khi dùng Spring XML thuần, kiểm tra `context:property-placeholder` hoặc `PropertySourcesPlaceholderConfigurer`, đường dẫn file properties, và các property sources có hiệu lực.

### 12.8. Collection entries dùng sai value/ref

`<entry key="main" value="mainChannel"/>` tạo String. Nếu setter đòi `Map<String, Channel>`, nên dùng `value-ref="mainChannel"` để đưa object bean vào map.

### 12.9. Vòng phụ thuộc và object chưa sẵn sàng

Setter cycles đôi lúc được Spring cho phép với singleton early references nhưng có thể tạo coupling và side effects khó kiểm soát. Đừng dựa vào việc “Spring startup được” để khẳng định bean graph hợp lý; kiểm thử trạng thái sau initialization và refactor vòng khi có thể.

### 12.10. Bean có nhưng setter không chạy

Một trong các nguyên nhân: bean class được tạo qua source khác, XML resource không được load, property thuộc bean definition khác cùng tên, profile bỏ qua XML block, hoặc bean vẫn lazy chưa instantiated. Kiểm tra context đang load file nào và các bean definitions thực tế, không chỉ nhìn một XML snippet.

### 12.11. Tưởng p-namespace thiếu schema

Khi IDE gạch đỏ `p:repo-ref`, hãy kiểm tra `xmlns:p="http://www.springframework.org/schema/p"` và tên property đúng. Không thêm `spring-p.xsd`: namespace `p` được Spring xử lý như shortcut XML, không có XSD riêng.

### 12.12. XML escape bị sai

`value="A & B"` không well-formed. Sửa `value="A &amp; B"`. Đây là lỗi XML parsing, không phải lỗi setter hoặc converter.

## 13. Bảng đối chiếu nhanh: chọn cú pháp nào?

| Nhu cầu | Cú pháp XML đề nghị | Setter tương ứng |
| --- | --- | --- |
| Cấp tên hiển thị | `<property name="name" value="Demo"/>` | `setName(String)` |
| Cấp số lần retry | `<property name="retryLimit" value="3"/>` | `setRetryLimit(int)` |
| Cấp boolean | `<property name="enabled" value="true"/>` | `setEnabled(boolean)` |
| Inject repository bean | `<property name="repo" ref="repo"/>` | `setRepo(Repository)` |
| Inject theo nested ref | `<property name="repo"><ref bean="repo"/></property>` | `setRepo(Repository)` |
| Truyền bean name String | `<property name="targetName"><idref bean="repo"/></property>` | `setTargetName(String)` |
| Truyền Java null | `<property name="memo"><null/></property>` | `setMemo(String)` |
| Truyền list literals | `<property name="tags"><list>...</list></property>` | `setTags(List<String>)` |
| Truyền map literals | `<property name="routes"><map>...</map></property>` | `setRoutes(Map<...>)` |
| Dùng p value shorthand | `p:name="Demo"` | `setName(String)` |
| Dùng p ref shorthand | `p:repo-ref="repo"` | `setRepo(Repository)` |
| Truyền property external | `value="${app.name}"` | `setName(String)` sau placeholder resolution |
| Tạo inner collaborator | `<property name="formatter"><bean .../></property>` | `setFormatter(Formatter)` |

Không chọn syntax chỉ để rút ngắn số dòng. Với property nhiều yếu tố hoặc dữ liệu cấu trúc, nested `<property>` có thể giúp code review chính xác hơn p namespace.

## 14. Bài tập kèm đáp án

### Bài 1 — Một literal không phải bean reference

Có bean `<bean id="store" class="demo.Store"/>` và service setter `setStore(Store)`. Viết:

```xml
<property name="store" value="store"/>
```

có đúng không?

**Đáp án:** Không theo ý định inject bean. `value` là literal String. Cần `ref="store"` hoặc nested `<ref bean="store"/>`.

### Bài 2 — Bean reference có tạo object khác?

Hai services đều `<property name="repo" ref="repository"/>` và `repository` mặc định singleton. Có chắc mỗi service nhận hai instances Repository khác nhau không?

**Đáp án:** Không. Thông thường cả hai nhận cùng managed singleton reference trong một container, trừ khi scope/proxy/config thay đổi semantics.

### Bài 3 — Setter thuộc tính tên gì?

Class có `setTimeoutSeconds(int seconds)` và field `timeout`. Nên dùng `name="timeout"` hay `name="timeoutSeconds"`?

**Đáp án:** `timeoutSeconds` theo JavaBeans setter naming, nếu không có một writable `timeout` property riêng.

### Bài 4 — Literal boolean

Setter `setEnabled(boolean)` và XML `value="false"`. Method nhận gì?

**Đáp án:** Java boolean `false` sau conversion, không phải String literal `"false"`.

### Bài 5 — Empty string và null

So sánh `<property name="memo" value=""/>` với nested `<null/>`. Chúng có tương đương không?

**Đáp án:** Không. Một cái là empty String, cái kia là null. Logic validation/serialization có thể phân biệt.

### Bài 6 — Ref nested và attribute

Hai XML:

```xml
<property name="repo" ref="repository"/>
```

```xml
<property name="repo">
    <ref bean="repository"/>
</property>
```

khác nhau về object được inject không?

**Đáp án:** Trong bối cảnh lookup cùng bean name, chúng cùng diễn đạt một managed bean reference.

### Bài 7 — `idref` dùng khi nào?

Infrastructure class có setter `setTargetBeanName(String)` và phải chứa tên bean `worker` để dùng sau. Nên dùng `ref` hay `idref`?

**Đáp án:** `<idref bean="worker"/>` khi muốn truyền String bean name và kiểm tra sự tồn tại; không truyền object `worker` như `ref`.

### Bài 8 — Map entry reference

Một setter nhận `Map<String, EmailSender>`, bean `emailSender` đã được đăng ký. XML `<entry key="default" value="emailSender"/>` có đúng không?

**Đáp án:** Không nếu cần EmailSender object. Dùng `<entry key="default" value-ref="emailSender"/>`.

### Bài 9 — p namespace

Để `p:repo-ref="repository"` hoạt động, cần khai báo namespace gì? Có cần XSD riêng không?

**Đáp án:** `xmlns:p="http://www.springframework.org/schema/p"`, không cần `spring-p.xsd`.

### Bài 10 — No setter

Class có field private `name` nhưng không có `setName`, XML cố đặt `<property name="name" value="A"/>`. Kết quả?

**Đáp án:** Standard property binding có thể fail vì property không writable. Cần thêm setter hợp lệ hoặc dùng constructor/factory injection.

### Bài 11 — Property reference và lazy

Bean `repository` được đánh dấu `lazy-init="true"`, còn bean `service` non-lazy có `ref="repository"` bắt buộc. Repository có được bảo đảm chưa khởi tạo khi context refresh xong không?

**Đáp án:** Không. Dependency của eager service có thể khiến repository lazy phải được tạo để inject.

### Bài 12 — Thay XML sau refresh

App đã tạo singleton service và set `retryLimit=3`. Bạn sửa XML thành `retryLimit=8` lúc app đang chạy. Giá trị service có tự cập nhật không?

**Đáp án:** Không. XML property injection mặc định xảy ra trong bean creation, không phải live reload.

### Bài 13 — Vòng setter injection

Hai singleton A và B đặt `property ref` lẫn nhau. Có nên xem đây là thiết kế sạch chỉ vì một vài phiên bản/configuration của Spring giải quyết được?

**Đáp án:** Không. Nó tạo coupling và nguy cơ lifecycle/proxy; nên refactor dependency graph có chiều rõ.

### Bài 14 — Property placeholder

`<property name="url" value="${api.url}"/>` có luôn tự resolve trong mọi BeanFactory thuần không?

**Đáp án:** Không. Cần placeholder processing/environment phù hợp. Kiểm tra `PropertySourcesPlaceholderConfigurer` hoặc namespace property-placeholder.

### Bài 15 — Identity trong demo

Vì sao output `sameRepo = true` và `backupSameRepo = true`?

**Đáp án:** Cả XML `ref` truyền thống lẫn `p:repo-ref` đều dùng BeanFactory để lấy **cùng singleton** `catalogRepository`, không tạo bản copy từ tên chuỗi.

### Bài 16 — Dấu cách cuối literal

Trong demo, `p:prefix="WARN: "` có một space sau dấu hai chấm. Vì sao output hiển thị `backupPrefix = [WARN: ]`?

**Đáp án:** Getter trả String có dấu cách cuối theo literal, và cặp ngoặc vuông của println làm khoảng trắng nhìn thấy rõ. Đây là nội dung thật của property, không phải một newline tách từ XML.

## 15. Checklist trước khi merge XML property configuration

- File XML có root `<beans>`, đúng default namespace và schemaLocation không?
- `bean id`/`alias` có nhất quán với các `ref`/`idref` không?
- Mọi `<property name="...">` có **writable JavaBean property** chính xác không?
- `value` được dùng cho literal/converted scalar; `ref` cho managed object, `idref` cho bean name String?
- Các kiểu `int`, `boolean`, enum, collection element đã có conversion hợp lệ?
- Có phân biệt `value=""` với `<null/>` và đã kiểm tra nullable contract?
- Với list/map, đã sử dụng `<ref>` hoặc `value-ref` thay vì literal bean name khi cần object?
- Có đang dùng `p` shorthand và đã khai `xmlns:p`, không thêm XSD giả?
- Có tạo inner bean khi nên dùng named/shared bean hoặc ngược lại không?
- Bean references có ảnh hưởng scope/lazy/lifecycle như mong đợi không?
- Có property bắt buộc nhưng class vẫn cho phép null dẫn đến runtime exception muộn không?
- Property placeholders/SpEL có được cấu hình/resolved đúng môi trường không?
- Đã kiểm tra với `ClassPathXmlApplicationContext`, lookup beans và assertion identity/behavior?
- Mọi lỗi được phân loại đúng: XML parse, XSD, writable property, type mismatch, missing bean hay circular reference?
- Khi chuyển từ XML sang JavaConfig, đã tránh cấu hình cùng một dependency hai lần không?

## 16. Tổng kết

**`<property name="x" value="..."/>`** cấp một giá trị literal, Spring chuyển sang kiểu phù hợp với writable property khi có converter/editor. **`<property name="x" ref="someBean"/>`** cấp reference đến bean `someBean` do container quản lý. Dạng `<ref bean="..."/>` tương đương với `ref` attribute; **`<idref bean="..."/>`** lại cấp **tên bean dưới dạng String**.

Setter injection xảy ra trong quá trình tạo bean, sau construction và trước các initialization callbacks tiêu chuẩn. Bean references tuân theo scope/lifecycle/proxy semantics của BeanFactory. `<list>`, `<map>`, `<set>`, `<props>` hỗ trợ dữ liệu có cấu trúc, `<null/>` khác empty String và inner beans phục vụ collaborator chỉ dùng trong một phạm vi cấu hình. `p` namespace là shorthand dễ đọc cho một số scalar/ref properties, nhưng không có XSD riêng và không thay thế mọi nested cấu trúc.

Khi một ứng dụng cần dependency object, hãy chọn **`ref` thay vì `value`**; khi chỉ muốn lưu tên bean để dùng như dữ liệu cấu hình, cân nhắc **`idref`**. Tách rõ hai ý nghĩa này giúp tránh phần lớn lỗi Spring XML setter injection.

### Tài liệu chính thức

- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Bean Overview](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html).
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — PropertySourcesPlaceholderConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/PropertySourcesPlaceholderConfigurer.html).
