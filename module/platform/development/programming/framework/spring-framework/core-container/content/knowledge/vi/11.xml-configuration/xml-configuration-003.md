# Cấp tham số qua constructor-arg trong Spring XML Core Container

## 1. Mục tiêu bài học

Trong Spring Framework, **constructor injection** là hình thức Dependency Injection (DI) mà container tạo object bằng cách gọi constructor với các tham số đã được phân giải. Khi cấu hình bean bằng XML, phần tử **`<constructor-arg>`** mô tả những giá trị hoặc references cần truyền vào constructor (và trong các trường hợp factory method, mô tả các tham số factory tương ứng).

Ví dụ đơn giản:

```xml
<bean id="catalogRepository"
      class="demo.CatalogRepositoryImpl"/>

<bean id="catalogService"
      class="demo.CatalogService">
    <constructor-arg ref="catalogRepository"/>
    <constructor-arg value="CATALOG"/>
</bean>
```

Đây là **ví dụ minh họa**, yêu cầu `demo.CatalogRepositoryImpl` và `demo.CatalogService` được định nghĩa với constructors tương thích. Spring không chỉ “chèn XML vào Java”; nó đọc bean definitions, giải quyết dependency rồi gọi constructor thích hợp để tạo bean.

Bài này giúp bạn:

1. Hiểu khác biệt giữa `<constructor-arg ref="..."/>` và `<constructor-arg value="..."/>`.
2. Biết Spring chọn constructor và ánh xạ arguments theo **vị trí**, **kiểu** hoặc **tên tham số**.
3. Sử dụng `index` (bắt đầu từ 0), `type` và `name` để loại bỏ nhập nhằng.
4. Hiểu điều kiện sử dụng `name` với Java 17: compiler option `-parameters` hoặc annotation JDK `@ConstructorProperties`.
5. Dùng dạng nested `<ref>`, `<value>`, `<null/>`, `<list>`, `<map>` và inner bean khi cần.
6. Biết shortcut **`c:` namespace** và sự khác biệt giữa `c:_0-ref` với `c:name-ref`.
7. Phân biệt constructor injection, setter/property injection và XML constructor autowiring.
8. Hiểu cách Spring chuyển chuỗi XML thành `int`, `long`, `boolean`, enum hoặc loại dữ liệu có conversion phù hợp.
9. Nhận biết overloaded constructors, null ambiguity, missing bean, cycles và những lỗi khởi tạo thường gặp.
10. Chạy ví dụ đầy đủ với **Java 17 + Spring Framework 6.2.x**; xác nhận dependency identity và stdout.
11. Thiết kế XML dễ đọc khi kết hợp với cấu hình Java, import XML, scope và lifecycle.
12. Biết cách kiểm thử, debug và chuyển sang Java-based configuration mà vẫn giữ nguyên hợp đồng dependency.

**Ý chính:** `<constructor-arg>` biểu diễn **hợp đồng khởi tạo bean**. Nó không phải setter, không phải tên biến Java, cũng không phải lệnh tự gọi constructor ngay khi file XML được đọc.

## 2. Constructor injection diễn ra như thế nào?

Ví dụ Java:

```java
package example;

public final class ShippingService {
    private final ShippingRepository repository;

    public ShippingService(ShippingRepository repository) {
        this.repository = repository;
    }

    public String dispatch(String trackingCode) {
        return repository.saveTracking(trackingCode);
    }
}
```

Đoạn này chưa độc lập: cần định nghĩa interface `ShippingRepository` với method `saveTracking`. Class `ShippingService` tự tuyên bố **bắt buộc cần repository** ngay ở constructor. Nó không gọi `new ShippingRepositoryImpl()` bên trong, cũng không tìm BeanFactory bằng chuỗi tên.

Khai báo XML:

```xml
<bean id="shippingRepository"
      class="example.InMemoryShippingRepository"/>

<bean id="shippingService"
      class="example.ShippingService">
    <constructor-arg ref="shippingRepository"/>
</bean>
```

Trong một `ApplicationContext` đọc XML này, Spring thực hiện về mặt khái niệm:

```text
Đọc XML <bean id="shippingService">
                  |
                  v
BeanDefinition shippingService
  beanClass = example.ShippingService
  constructorArgs = [ref(shippingRepository)]
                  |
                  v
BeanFactory cần tạo shippingService
                  |
                  v
Resolve bean shippingRepository
                  |
                  v
Chọn constructor phù hợp
                  |
                  v
new ShippingService(managedRepository)
                  |
                  v
Apply bean initialization/post-processors
                  |
                  v
Managed bean shippingService
```

Nếu `shippingRepository` là singleton mặc định, instance được truyền vào `ShippingService` là đối tượng do **cùng BeanFactory** quản lý. Constructor dependency graph còn định hướng thứ tự khởi tạo cần thiết: để xây service, Spring phải phân giải repository trước.

### Vì sao constructor injection thường được ưu tiên?

- Dependency bắt buộc **hiển thị ngay trên API của class**.
- Cho phép các field `final`; object có trạng thái hợp lệ sớm hơn.
- Fail-fast khi thiếu collaborator thay vì tạo bean nửa hoàn chỉnh.
- Unit test có thể gọi constructor với fake/stub mà không phải mở Spring.
- Giảm khả năng setter bị quên gọi.
- Làm đồ thị phụ thuộc dễ phân tích và phát hiện vòng hơn.

Constructor injection không bảo đảm mọi thứ tự động đúng. Nếu hai constructors yêu cầu nhau, Spring sẽ không thể hoàn tất; hoặc nếu overloaded constructors/values không rõ, XML cần disambiguation.

## 3. Cú pháp chuẩn của <constructor-arg>

Một cấu hình XML Spring thông dụng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="backend" class="example.MemoryBackend"/>

    <bean id="gateway" class="example.Gateway">
        <constructor-arg ref="backend"/>
        <constructor-arg value="production"/>
    </bean>

</beans>
```

Hai dạng thuộc tính phổ biến:

| Cú pháp | Spring nhận được gì? | Ví dụ |
| --- | --- | --- |
| `ref="beanName"` | Reference đến **bean khác** trong container | `<constructor-arg ref="backend"/>` |
| `value="text"` | **Chuỗi ký tự**, được convert sang type constructor parameter | `<constructor-arg value="15"/>` |
| `index="0"` | Vị trí parameter trong constructor, **0-based** | `<constructor-arg index="0" ref="backend"/>` |
| `type="int"` | Gợi ý kiểu parameter để chọn constructor/match | `<constructor-arg type="int" value="15"/>` |
| `name="timeout"` | Match theo tên Java constructor parameter | `<constructor-arg name="timeout" value="15"/>` |

Ví dụ `Gateway`, `MemoryBackend` là các kiểu minh họa, chưa thuộc project chạy đầy đủ bên dưới.

Bên trong một `<constructor-arg>` cũng có thể sử dụng các **sub-elements**:

```xml
<bean id="gateway" class="example.Gateway">
    <constructor-arg>
        <ref bean="backend"/>
    </constructor-arg>
    <constructor-arg>
        <value>production</value>
    </constructor-arg>
</bean>
```

Ở đây `<ref bean="backend"/>` tương đương về ý định với `ref="backend"`. `<value>production</value>` tương đương với chuỗi literal. Dạng nested hữu ích khi cần collection, inner bean hoặc cấu trúc giá trị dài.

**Không viết cả `ref` và `value` trên cùng `<constructor-arg>`** để đại diện cùng parameter. Mỗi argument cần một giá trị/bean reference có nghĩa rõ ràng.

## 4. Phân biệt ref và value — lỗi quan trọng nhất

Giả sử class:

```java
public final class EngineController {
    private final Engine engine;

    public EngineController(Engine engine) {
        this.engine = engine;
    }
}
```

Đây là minh họa, cần kiểu `Engine`. Cấu hình đúng:

```xml
<bean id="engine" class="example.Engine"/>
<bean id="controller" class="example.EngineController">
    <constructor-arg ref="engine"/>
</bean>
```

Container tìm bean **mang tên `engine`**, rồi truyền object vào constructor. Nếu thay:

```xml
<constructor-arg value="engine"/>
```

Spring nhận **chuỗi `"engine"`**, không phải bean. Nó sẽ thử convert chuỗi sang type parameter. Với kiểu `Engine` không có converter phù hợp, bean creation thất bại; trong vài dự án custom converters, chuỗi có thể được convert với nghĩa khác ngoài dự định.

Ngược lại, khi constructor cần `String endpoint`, XML nên dùng `value="https://example.test"`. Đừng dùng `ref="https://example.test"` nếu không hề có bean name ấy.

### Dạng nested <ref>

```xml
<constructor-arg>
    <ref bean="engine"/>
</constructor-arg>
```

Tương đương về hợp đồng reference với `<constructor-arg ref="engine"/>`. Bean được tham chiếu có thể được định nghĩa ở file XML khác nhưng **cùng ApplicationContext**, hoặc trong parent context theo semantics của `<ref>`.

### Dạng nested <idref> khác <ref>

```xml
<constructor-arg>
    <idref bean="engine"/>
</constructor-arg>
```

`<idref>` truyền **bean name dạng String** đã được kiểm tra tồn tại, chứ không truyền object bean. Phù hợp cho một component thực sự cần **tên của bean** như một giá trị cấu hình. Nếu constructor cần `Engine` object, dùng `<ref>`.

### Dạng <null/>

```xml
<constructor-arg>
    <null/>
</constructor-arg>
```

`<null/>` truyền Java `null`. Chỉ dùng khi API cho phép null rõ ràng. `null` làm overload resolution phức tạp hơn nếu có nhiều constructors với reference types tương thích; hãy dùng `index`/`type` hoặc thiết kế constructor rõ ràng. Không dùng null để che dependency bắt buộc bị thiếu.

## 5. Matching tham số khi không có index/type/name

Nếu constructor có các tham số **khác type và không nhập nhằng**, có thể dùng thứ tự khai báo:

```java
// Minh họa:
public ShipmentPlanner(RouteRepository routeRepository,
                       RateProvider rateProvider) {
}
```

```xml
<bean id="planner" class="example.ShipmentPlanner">
    <constructor-arg ref="routeRepository"/>
    <constructor-arg ref="rateProvider"/>
</bean>
```

Spring có thể dùng type metadata của references để chọn tham số phù hợp. Trong tình huống không nhập nhằng, danh sách arguments theo thứ tự được truyền tới constructor tương ứng.

Vấn đề xuất hiện khi **nhiều tham số cùng type** hoặc khi các giá trị đều là text từ XML. Xem class sau:

```java
public final class ReportOptions {
    private final int maxRows;
    private final String title;

    public ReportOptions(int maxRows, String title) {
        this.maxRows = maxRows;
        this.title = title;
    }
}
```

Hai XML values:

```xml
<bean id="options" class="example.ReportOptions">
    <constructor-arg value="100"/>
    <constructor-arg value="Daily"/>
</bean>
```

có thể được Spring chuyển kiểu dựa trên constructor không nhập nhằng. Nhưng khi có overload `ReportOptions(String, int)` hoặc hai arguments đều là chuỗi số, quyết định có thể khó hiểu, phụ thuộc conversion và candidate matching. **Đừng dựa vào heuristics nếu thiết kế đã có ambiguity**; chỉ rõ `index`, `type` hoặc `name`.

## 6. index: ánh xạ trực tiếp theo vị trí bắt đầu từ 0

`index` giúp Spring biết argument tương ứng với parameter vị trí nào:

```java
public ReportOptions(int maxRows, String title) {
    // ...
}
```

```xml
<bean id="options" class="example.ReportOptions">
    <constructor-arg index="1" value="Daily"/>
    <constructor-arg index="0" value="100"/>
</bean>
```

Dù hai thẻ xuất hiện theo thứ tự 1 rồi 0, Spring map vào:

```text
constructor:
   [0] int maxRows       <- "100" -> 100
   [1] String title      <- "Daily"
```

Các quy tắc:

- Index **0-based**, giống array indices trong Java.
- `index="0"` là parameter đầu tiên, `index="1"` là thứ hai.
- Hai `<constructor-arg index="0">` cùng định nghĩa một vị trí là lỗi metadata cấu hình hoặc sinh conflict; không dùng để ghi đè có chủ đích.
- Index nằm ngoài constructor signature phù hợp sẽ gây lỗi resolution/bean creation.
- Index không phụ thuộc việc compiler còn giữ parameter names, nên bền khi chưa bật `-parameters`.
- Index vẫn là **hợp đồng theo vị trí**. Nếu developer đổi thứ tự parameters cùng type trong Java, XML có thể không phát hiện lỗi compile nhưng hành vi thay đổi.

### Khi nào nên dùng index?

- Hai arguments có cùng kiểu `String`.
- Constructor nhận `String id, String region`, nơi thứ tự quan trọng.
- Không thể giữ metadata tên parameter ở runtime.
- Dùng c-namespace positional syntax `c:_0` hoặc `c:_0-ref`.
- Cần chọn rõ arg của overloaded constructors.

Ví dụ thứ tự thẻ không quan trọng khi `index` explicit, nhưng để dễ review, thường viết theo thứ tự 0→1→2.

## 7. type: giúp phân giải kiểu tham số

`type` mô tả kiểu parameter muốn Spring match, đặc biệt hữu ích khi literal values không tự tiết lộ type.

```java
public final class CalculationSettings {
    public CalculationSettings(int attempts, String label) {
        // ...
    }
}
```

```xml
<bean id="calculationSettings" class="example.CalculationSettings">
    <constructor-arg type="int" value="3"/>
    <constructor-arg type="java.lang.String" value="gold"/>
</bean>
```

Các tên primitive Java như `int`, `long`, `boolean` được dùng trực tiếp; các reference types có thể dùng fully qualified name như `java.lang.String`. Spring chuyển `value="3"` sang `int` khi chọn/invoke constructor.

### type không giống “kiểu object mới”

`type="java.lang.String"` **không khai báo một bean String độc lập**. Nó chỉ cung cấp gợi ý về signature parameter của constructor cần gọi. Object bean được tạo vẫn thuộc class nêu trong `<bean class="...">`.

### Kiểu số dễ gây nhầm

Giả sử class overload:

```java
// Minh họa, không đặt cùng ví dụ runnable.
public Limits(int max, long delayMillis) {
}
public Limits(long max, int delayMillis) {
}
```

XML:

```xml
<constructor-arg value="5"/>
<constructor-arg value="1000"/>
```

chứa hai chuỗi số, nên không biểu diễn rõ overload nào được mong đợi. Sử dụng `index` kết hợp `type` (hoặc tốt hơn là thiết kế một constructor không nhập nhằng) để Spring có thêm thông tin.

### type và ref kết hợp

Bạn có thể chỉ rõ type bên cạnh `ref` nếu nó giúp làm rõ overload. Dù vậy, với bean reference mà Spring đã biết kiểu bean, thường **không cần** lặp type. Metadata thừa làm XML dài và dễ sai sau refactor interface/implementation.

## 8. name: ánh xạ theo tên constructor parameter

Thay vì vị trí, XML có thể viết:

```java
public final class RetrySettings {
    public RetrySettings(int maxAttempts, long delayMillis) {
    }
}
```

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg name="delayMillis" value="1500"/>
    <constructor-arg name="maxAttempts" value="3"/>
</bean>
```

Tên `delayMillis`/`maxAttempts` phải khớp metadata parameter names mà Spring nhìn thấy. Điểm khác với `index`: source XML tự thể hiện **ý nghĩa** của argument và không lệ thuộc thứ tự viết thẻ. Nhưng **Java parameter names không được bảo toàn ở mọi bản build theo mặc định**.

### 8.1. Biên dịch với -parameters

Từ Java 8 trở đi, `javac -parameters` giữ tên parameters trong bytecode để reflection/Spring có thể đọc. Với Java 17:

```bash
javac -parameters RetrySettings.java
```

Nếu dùng Maven, khai báo trong `maven-compiler-plugin`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

Ví dụ runnable ở mục 13 dùng cấu hình Maven này; nhờ đó `<constructor-arg name="maxAttempts">` hoạt động theo metadata rõ ràng.

### 8.2. @ConstructorProperties khi không dùng -parameters

Spring cũng nhận tên constructor arguments được khai báo bằng **`@ConstructorProperties`** từ JDK:

```java
import java.beans.ConstructorProperties;

public final class RetrySettings {
    private final int maxAttempts;
    private final long delayMillis;

    @ConstructorProperties({"maxAttempts", "delayMillis"})
    public RetrySettings(int maxAttempts, long delayMillis) {
        this.maxAttempts = maxAttempts;
        this.delayMillis = delayMillis;
    }
}
```

Annotation phải phản ánh **đúng thứ tự constructor parameters**. Nó khác `@Autowired`: không yêu cầu Spring code trong domain class, vì `@ConstructorProperties` thuộc `java.beans`.

### 8.3. Nếu metadata names không có?

XML `name="maxAttempts"` có thể không match constructor đúng như mong đợi và bean creation thất bại. Giải pháp là:

- Bật `-parameters` (khuyến nghị trong build Java hiện đại khi sử dụng parameter-name metadata).
- Dùng `@ConstructorProperties` nếu cần giữ contract rõ trong mã.
- Hoặc dùng `index` thay cho `name` nếu không quản lý được compiler settings.

Không sửa lỗi bằng cách đổi `name` bừa cho tới khi khởi động được; cần biết tên runtime thật sự và các overload liên quan.

### 8.4. Khác nhau giữa XML name và bean id

Trong:

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg name="maxAttempts" value="3"/>
</bean>
```

`retrySettings` là **tên bean trong container**; `maxAttempts` là **tên parameter bên trong Java constructor**. Một bên phục vụ lookup bean, bên kia phục vụ argument matching. Không hoán đổi.

## 9. index, type và name nên chọn cách nào?

| Tình huống | Lựa chọn hữu ích | Giới hạn |
| --- | --- | --- |
| Các dependencies khác type, ít nguy cơ nhầm | `<constructor-arg ref="..."/>` theo thứ tự | Phải giữ đủ arguments |
| Hai `String` có ngữ nghĩa khác nhau | `index` hoặc `name` | Index phụ thuộc vị trí; name phụ thuộc metadata |
| Literal số cho overloaded constructors | `type`, kết hợp `index` khi cần | Metadata dài hơn; vẫn phải có overload hợp lệ |
| Muốn XML tự mô tả semantic của arguments | `name` | Cần `-parameters`/`@ConstructorProperties` |
| Không quản lý được compiler flags | `index` | Refactor thứ tự Java constructor dễ gây regression |
| Một argument là Spring bean khác | `ref` | Bean referenced phải tồn tại và type tương thích |
| Một argument là literal | `value` | Spring cần convert; định dạng phải hợp lệ |
| Một argument là list/map | Nested `<list>`/`<map>` | Generic conversion/ordering cần kiểm chứng |
| Giá trị intentionally null | Nested `<null/>` | Dễ nhập nhằng với overloaded reference parameters |

**Thực hành tốt:** Với những constructor phức tạp, lựa chọn tối ưu thường là **giảm overload ambiguity ở phía Java**, rồi dùng XML đủ tường minh cho người đọc. Không nên biến XML thành mê cung index/type để bù cho một API constructor khó hiểu.

## 10. Constructor overloads và thuật toán lựa chọn

Trong Java, một class có thể có nhiều constructors:

```java
// Minh họa API có overload.
public final class EndpointClient {
    public EndpointClient(String url) { /* ... */ }
    public EndpointClient(String url, int timeoutMillis) { /* ... */ }
    public EndpointClient(URI uri, int timeoutMillis) { /* ... */ }
}
```

Ở đây cần import `java.net.URI`. Với XML:

```xml
<bean id="endpointClient" class="example.EndpointClient">
    <constructor-arg value="https://example.test"/>
    <constructor-arg value="1000"/>
</bean>
```

Spring sẽ xem xét số lượng arguments, types, conversion và metadata available để tìm constructor phù hợp. Bạn không nên giả định rằng “constructor khai báo trước” hoặc “constructor dài nhất” luôn được chọn bất kể metadata.

### Làm rõ overload bằng index/type

```xml
<bean id="endpointClient" class="example.EndpointClient">
    <constructor-arg index="0"
                     type="java.lang.String"
                     value="https://example.test"/>
    <constructor-arg index="1"
                     type="int"
                     value="1000"/>
</bean>
```

Nhờ đó ý định chọn signature `EndpointClient(String, int)` rõ hơn. Nếu khai báo type không khớp bất kỳ overload hợp lệ nào, Spring sẽ báo lỗi; metadata không ép JVM chạy một constructor không tồn tại.

### Thiết kế API phù hợp DI

Nếu bạn sở hữu source class, hãy cân nhắc:

- Một constructor chính với các dependencies bắt buộc.
- Group những primitive/string settings thành một **immutable settings object** nếu nhiều tham số cùng type.
- Dùng builder hoặc static factory có tên khi nhiều cấu hình object tạo ra có ý nghĩa rất khác.
- Giữ legacy overloads chỉ khi cần tương thích và test đúng signature được Spring chọn.

**Tách lựa chọn implementation khỏi cấu hình primitive:** Thay vì một class có hàng chục overloads, có thể đưa `EndpointSettings` làm một bean riêng, rồi truyền settings đó bằng `ref` vào constructor client.

## 11. Truyền nhiều bean references và kết hợp với value

Một bean có thể cần cả collaborator object và literal:

```java
// Minh họa:
public final class NotificationService {
    public NotificationService(MessageGateway gateway,
                               String sender,
                               int retries) {
    }
}
```

XML:

```xml
<bean id="gateway" class="example.DefaultMessageGateway"/>

<bean id="notificationService" class="example.NotificationService">
    <constructor-arg index="0" ref="gateway"/>
    <constructor-arg index="1" value="no-reply"/>
    <constructor-arg index="2" value="3"/>
</bean>
```

Spring giải quyết `gateway` thành bean tương thích `MessageGateway`, còn `no-reply` và `3` là literal values; converter biến `"3"` thành `int`.

### Phân biệt vòng đời và dependency identity

Một reference bằng `ref` là request lấy bean managed. Nếu bean referenced mặc định singleton, Spring thường truyền **cùng instance** tới mọi consumer phù hợp trong cùng ApplicationContext.

Nếu bạn viết:

```java
NotificationService service =
        new NotificationService(new DefaultMessageGateway(), "no-reply", 3);
```

ngoài container, bạn tự xây object khác với managed singleton. Đó là Java construction bình thường, không kiểm chứng XML DI.

### Thiếu bean reference

Nếu `ref="gateway"` không có bean/alias cùng tên được phân giải, Spring thường ném lỗi dependency resolution hoặc bean creation. Đừng đổi `ref` thành `value` chỉ để XML parse qua; điều đó đổi hẳn ý nghĩa dữ liệu.

## 12. Truyền collections, inner bean và property-like values

Không phải constructor parameters luôn là scalar hay bean đơn.

### 12.1. List<String>

Giả sử Java constructor:

```java
// Minh họa:
public AllowedRegions(java.util.List<String> regions) {
}
```

XML:

```xml
<bean id="allowedRegions" class="example.AllowedRegions">
    <constructor-arg>
        <list>
            <value>ap-southeast-1</value>
            <value>eu-west-1</value>
            <value>us-east-1</value>
        </list>
    </constructor-arg>
</bean>
```

Spring cung cấp collection khi tạo bean; generic metadata `List<String>` có thể giúp conversion của phần tử theo type. Với `List<Handler>`, thường dùng `<ref bean="..."/>` trong `<list>`.

### 12.2. Map<String, Integer>

```java
// Minh họa:
public ThrottleLimits(java.util.Map<String, Integer> perRegion) {
}
```

```xml
<bean id="throttleLimits" class="example.ThrottleLimits">
    <constructor-arg>
        <map>
            <entry key="ap-southeast-1" value="10"/>
            <entry key="eu-west-1" value="20"/>
        </map>
    </constructor-arg>
</bean>
```

Spring có thể chuyển các chuỗi `10`, `20` thành `Integer` nhờ generic type metadata của constructor. Đây là một bean `ThrottleLimits` chứa map, không có nghĩa Spring đăng ký thêm các bean có tên `ap-southeast-1`.

### 12.3. Inner bean

```xml
<bean id="filterService" class="example.FilterService">
    <constructor-arg>
        <bean class="example.DefaultFilterPolicy">
            <constructor-arg value="strict"/>
        </bean>
    </constructor-arg>
</bean>
```

`DefaultFilterPolicy` là một **inner bean definition** được tạo riêng cho bean ngoài; không cần `id` và không được lấy độc lập bằng `getBean("defaultFilterPolicy")`. Inner bean thường có vòng đời gắn với bean ngoài, không phải một singleton công khai có thể dùng ở nhiều nơi.

Khi nhiều consumers cần cùng một policy bean, tốt hơn là đăng ký **bean có tên riêng** và dùng `ref` thay vì sao chép inner bean.

### 12.4. Null và literal rỗng là khác nhau

```xml
<constructor-arg>
    <null/>
</constructor-arg>
```

truyền `null`, trong khi:

```xml
<constructor-arg value=""/>
```

truyền chuỗi rỗng `""` (hoặc giá trị convert phù hợp). Không coi hai trường hợp là tương đương. Với input bắt buộc, nên validate trong constructor thay vì dùng `null` như một giá trị im lặng.

## 13. Ví dụ chạy hoàn chỉnh: Java 17 + Spring Framework 6.2

Ví dụ không dùng Spring Boot, database hoặc external API. Chúng ta sẽ khai báo toàn bộ các bean bằng XML để thấy rõ `constructor-arg`, nhưng Java classes vẫn là POJO độc lập với Spring.

Ví dụ kiểm chứng:

- `ref` và `index`: `CatalogService` nhận đúng singleton `Catalog`.
- `value`: truyền prefix `SKU-` vào constructor.
- `name`: `RetrySettings` nhận `maxAttempts` và `delayMillis` từ XML; Maven bật `-parameters`.
- `type`: `AuditLabel` nhận `String` và `int`.
- `c:` namespace: `Reporter` nhận bean bằng `c:_0-ref` và literal bằng `c:_1`.
- Spring thực hiện conversion `String -> int/long` đúng.
- Scope singleton: tra cứu repository qua service và trực tiếp từ context cho cùng reference.

### 13.1. Cấu trúc dự án

```text
xml-constructor-args/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlConstructorArgsDemo.java
        └── resources/
            └── beans.xml
```

### 13.2. Tạo pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-constructor-args</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.3. Java source đầy đủ

Tạo `src/main/java/demo/XmlConstructorArgsDemo.java`:

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class XmlConstructorArgsDemo {

    public interface Catalog {
        String find(String sku);
    }

    public static final class MemoryCatalog implements Catalog {
        public MemoryCatalog() {
        }

        @Override
        public String find(String sku) {
            return switch (sku) {
                case "BK-7" -> "Java book";
                case "MUG-2" -> "Coffee mug";
                default -> "Unknown item";
            };
        }
    }

    public static final class CatalogService {
        private final Catalog catalog;
        private final String prefix;

        public CatalogService(Catalog catalog, String prefix) {
            this.catalog = catalog;
            this.prefix = prefix;
        }

        public String describe(String sku) {
            return prefix + catalog.find(sku);
        }

        public Catalog catalog() {
            return catalog;
        }
    }

    public static final class RetrySettings {
        private final int maxAttempts;
        private final long delayMillis;

        public RetrySettings(int maxAttempts, long delayMillis) {
            this.maxAttempts = maxAttempts;
            this.delayMillis = delayMillis;
        }

        public String describe() {
            return "attempts=" + maxAttempts
                    + ",delayMillis=" + delayMillis;
        }
    }

    public static final class AuditLabel {
        private final String name;
        private final int level;

        public AuditLabel(String name, int level) {
            this.name = name;
            this.level = level;
        }

        public String describe() {
            return name + "#" + level;
        }
    }

    public static final class Reporter {
        private final CatalogService service;
        private final String label;

        public Reporter(CatalogService service, String label) {
            this.service = service;
            this.label = label;
        }

        public String line(String sku) {
            return label + service.describe(sku);
        }

        public CatalogService service() {
            return service;
        }
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
            Catalog catalog = context.getBean(Catalog.class);
            CatalogService service = context.getBean(CatalogService.class);
            RetrySettings retry = context.getBean(RetrySettings.class);
            AuditLabel audit = context.getBean(AuditLabel.class);
            Reporter reporter = context.getBean(Reporter.class);

            System.out.println("service=" + service.describe("BK-7"));
            System.out.println("retry=" + retry.describe());
            System.out.println("audit=" + audit.describe());
            System.out.println("report=" + reporter.line("MUG-2"));
            System.out.println("sameCatalog=" +
                    (catalog == service.catalog()));
            System.out.println("sameService=" +
                    (service == reporter.service()));
        }
    }
}
```

Lưu ý về Java types: Tất cả classes mà XML trực tiếp instantiate đều là **`public static` nested classes** có public constructors. Nhờ vậy Spring không cần tạo một instance `XmlConstructorArgsDemo` bên ngoài. Trong XML, tên binary class của chúng dùng dấu `$`, ví dụ `demo.XmlConstructorArgsDemo$MemoryCatalog`.

### 13.4. Spring XML đầy đủ

Tạo `src/main/resources/beans.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:c="http://www.springframework.org/schema/c"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Bean với public no-arg constructor. -->
    <bean id="catalog"
          class="demo.XmlConstructorArgsDemo$MemoryCatalog"/>

    <!-- Explicit position: constructor CatalogService(Catalog, String). -->
    <bean id="catalogService"
          class="demo.XmlConstructorArgsDemo$CatalogService">
        <constructor-arg index="0" ref="catalog"/>
        <constructor-arg index="1" value="SKU-"/>
    </bean>

    <!-- Name matching: Maven compiler bật -parameters. -->
    <bean id="retrySettings"
          class="demo.XmlConstructorArgsDemo$RetrySettings">
        <constructor-arg name="delayMillis" value="1500"/>
        <constructor-arg name="maxAttempts" value="3"/>
    </bean>

    <!-- Explicit type matching cho các giá trị đơn giản. -->
    <bean id="auditLabel"
          class="demo.XmlConstructorArgsDemo$AuditLabel">
        <constructor-arg type="java.lang.String" value="AUDIT"/>
        <constructor-arg type="int" value="7"/>
    </bean>

    <!-- c-namespace positional shortcut, _0 là tham số đầu tiên. -->
    <bean id="reporter"
          class="demo.XmlConstructorArgsDemo$Reporter"
          c:_0-ref="catalogService"
          c:_1="REPORT:"/>
</beans>
```

XML khai báo năm beans chính: `catalog`, `catalogService`, `retrySettings`, `auditLabel`, `reporter`. Không có `@ComponentScan`; trong ví dụ Spring tạo chúng vì `ClassPathXmlApplicationContext` đọc `beans.xml`.

### 13.5. Chạy

Yêu cầu JDK 17+ và Maven. Từ thư mục có `pom.xml`:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.XmlConstructorArgsDemo
```

Output **do ứng dụng tự in**, không tính log Maven/Spring phụ thuộc môi trường:

```text
service=SKU-Java book
retry=attempts=3,delayMillis=1500
audit=AUDIT#7
report=REPORT:SKU-Coffee mug
sameCatalog=true
sameService=true
```

### 13.6. Giải thích từng dòng

**`service=SKU-Java book`:** XML `catalogService` có `index="0" ref="catalog"` nên Spring truyền managed `MemoryCatalog` vào constructor `CatalogService(Catalog, String)`. `index="1" value="SKU-"` truyền prefix literal. Method `describe("BK-7")` tạo `SKU-Java book`.

**`retry=attempts=3,delayMillis=1500`:** Thẻ `name="delayMillis"` đứng trước trong XML, nhưng Spring map đúng tên parameter nhờ `-parameters`. Chuỗi `"1500"` được chuyển thành `long`; `"3"` chuyển thành `int`. Vì thế thứ tự khai báo thẻ trong XML **không làm đổi ý nghĩa** khi `name` được xác định rõ.

**`audit=AUDIT#7`:** `type="java.lang.String"` và `type="int"` giúp Spring match signature `AuditLabel(String, int)`; literal `7` chuyển sang `int`.

**`report=REPORT:SKU-Coffee mug`:** Dạng `c:_0-ref="catalogService"` truyền bean `CatalogService` đã được Spring quản lý, còn `c:_1="REPORT:"` truyền chuỗi. Reporter dùng service để tra `MUG-2`, trả `Coffee mug`.

**`sameCatalog=true`:** `CatalogService` giữ đúng `Catalog` singleton do `context.getBean(Catalog.class)` cung cấp. Không có object repository mới được tạo bằng `new` trong consumer.

**`sameService=true`:** `Reporter` giữ đúng singleton `catalogService`, vì `c:_0-ref` biểu diễn bean reference chứ không phải chuỗi. Vì vậy hai cách lấy service (trực tiếp từ context và thông qua reporter) trả cùng reference trong một ApplicationContext.

### 13.7. Vì sao constructor có thể nhận interface?

`CatalogService` khai báo constructor nhận `Catalog` interface. XML cung cấp bean `MemoryCatalog` implement `Catalog`. Spring phân giải reference theo tên `catalog` và xác minh object tương thích với type parameter. Đó là DI dựa trên abstraction; consumer không cần biết class implementation đã được khai báo ở đâu.

### 13.8. Thử thay đổi có kiểm soát

1. Đổi `value="SKU-"` thành `value="ITEM-"`. Output `service` và `report` cùng đổi prefix; không cần biên dịch lại Java.
2. Đổi thứ tự hai thẻ `name` của `retrySettings`. Với `-parameters` đúng, output không thay.
3. Xóa `<parameters>true</parameters>` rồi clean compile. Đoạn `name` có thể không resolve như mong đợi khi metadata tên không còn; sửa bằng `index` hoặc `@ConstructorProperties`.
4. Đổi `c:_0-ref="catalogService"` thành `c:_0="catalogService"`. Bây giờ Spring nhận chuỗi, không phải managed bean; sẽ lỗi type conversion hoặc constructor resolution.
5. Đổi `index="0" ref="catalog"` thành `ref="missingCatalog"`. Spring báo lỗi vì dependency không tồn tại.
6. Thay `delayMillis` bằng chuỗi không chuyển được sang long. Context startup sẽ thất bại với conversion/bean creation exception.
7. Đổi `reporter` từ singleton sang `scope="prototype"` và lấy hai lần để quan sát instance identity, nhưng nhớ rằng service referenced vẫn là singleton nếu scope service không thay.

## 14. c-namespace: rút gọn constructor arguments

Spring hỗ trợ namespace `c:` để thay cấu trúc `<constructor-arg>` bằng XML attributes.

Dạng đầy đủ:

```xml
<bean id="reporter" class="example.Reporter">
    <constructor-arg index="0" ref="catalogService"/>
    <constructor-arg index="1" value="REPORT:"/>
</bean>
```

Dạng `c:` tương đương về ý định:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="catalogService"
      c:_1="REPORT:"/>
```

Phải khai báo namespace trong root `<beans>`:

```xml
xmlns:c="http://www.springframework.org/schema/c"
```

`c:` là shortcut của Spring, **không cần một XSD riêng cho c-namespace**. Dù vậy, file XML vẫn cần `beans` namespace/schema hợp lệ.

### 14.1. c:name và c:name-ref

Khi parameter names có sẵn:

```java
public Reporter(CatalogService service, String label) {
}
```

có thể viết:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:service-ref="catalogService"
      c:label="REPORT:"/>
```

Trong đó:

- `c:service-ref` biểu diễn **reference tới bean** cho constructor parameter tên `service`.
- `c:label` biểu diễn **literal string** cho parameter tên `label`.
- Tên `service` và `label` phải match metadata parameter names; chú ý `-parameters` hoặc cách khai báo metadata tương đương.

### 14.2. c:_0 và c:_0-ref

Khi không có parameter names, hoặc muốn mapping theo vị trí:

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="catalogService"
      c:_1="REPORT:"/>
```

Dấu gạch dưới `_` là bắt buộc trong ký hiệu theo index vì tên XML attribute không được bắt đầu bằng chữ số. Vị trí đầu tiên là `_0`, không phải `_1`.

### 14.3. So sánh khi chọn cách viết

| Đặc tính | `<constructor-arg>` | `c:` namespace |
| --- | --- | --- |
| Tên tham số | `name="service"` | `c:service-ref="..."` |
| Vị trí | `index="0"` | `c:_0-ref="..."` |
| Tham chiếu bean | `ref="bean"` | Hậu tố `-ref` |
| Literal | `value="text"` | Không có hậu tố `-ref` |
| Inner bean / list / map dài | Dùng nested XML | Không linh hoạt như nested form |
| Dễ đọc khi có nhiều config strings ngắn | Tùy nhóm | Có thể gọn hơn |
| Dễ phân biệt reference với literal | Rất rõ ràng | Cần chú ý hậu tố `-ref` |

Nếu codebase đã thống nhất với `<constructor-arg>`, đừng trộn cả hai styles trong một file chỉ để rút ngắn vài ký tự. Sự thống nhất quan trọng hơn việc mỗi bean dùng cú pháp ngắn nhất.

### 14.4. Sự khác biệt với p-namespace

`p:` áp dụng cho **properties/setters**, không phải constructor arguments. Ví dụ:

```xml
<bean id="client" class="example.Client"
      p:timeout="1000"/>
```

đòi class có property setter (hoặc property injection tương thích); nó không tự gọi constructor `Client(int timeout)`. Muốn truyền constructor parameter, dùng `<constructor-arg>` hoặc `c:`.

## 15. Constructor injection so với setter injection

Constructor-based DI:

```java
public final class PricingService {
    private final TaxPolicy taxPolicy;

    public PricingService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }
}
```

```xml
<bean id="pricingService" class="example.PricingService">
    <constructor-arg ref="taxPolicy"/>
</bean>
```

Setter-based DI:

```java
public class PricingService {
    private TaxPolicy taxPolicy;

    public void setTaxPolicy(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }
}
```

```xml
<bean id="pricingService" class="example.PricingService">
    <property name="taxPolicy" ref="taxPolicy"/>
</bean>
```

Hai class snippets ở đây là **hai phiên bản thiết kế thay thế**, không đặt cùng tên trong cùng một Java file. Chúng không phải ví dụ runnable độc lập.

| Tiêu chí | Constructor injection | Setter/property injection |
| --- | --- | --- |
| Dependency bắt buộc | Diễn đạt rõ trong constructor | Có thể bị thiếu nếu không validate |
| Field `final` | Dễ hỗ trợ | Thường không phù hợp khi setter phải thay field sau constructor |
| Kiểm tra tính hợp lệ ngay khi tạo | Dễ | Có thể cần init callback |
| Unit test không Spring | Chỉ gọi constructor | Phải gọi setters |
| Optional configuration | Có thể dùng overload/settings | Setter đôi khi thuận tiện |
| Vòng constructor A↔B | Thường không giải quyết được | Một số vòng setter có thể được early references xử lý, nhưng nên refactor |
| XML syntax | `<constructor-arg>` | `<property>` hoặc `p:` |

Đối với dependencies không thể thiếu, Spring documentation thường khuyên constructor injection. Với những thuộc tính tùy chọn của legacy JavaBeans, setter injection có thể hợp lý. Không cần ép mọi thứ vào một kiểu DI; cần giữ invariant và dễ kiểm thử.

## 16. XML autowire="constructor" khác explicit constructor-arg

XML hỗ trợ constructor autowiring:

```xml
<bean id="processor"
      class="example.Processor"
      autowire="constructor"/>
```

Spring cố giải các constructor parameters bằng **beans có kiểu phù hợp** trong container. Nếu có đúng một bean thỏa type, nó có thể được inject tự động.

So sánh:

```xml
<bean id="processor" class="example.Processor">
    <constructor-arg ref="primaryRepository"/>
</bean>
```

Với explicit `ref`, XML công bố ngay instance nào được chọn. Còn `autowire="constructor"` yêu cầu container suy ra dependency theo type từ các candidates.

### Lợi và rủi ro của autowire constructor

Ưu điểm:

- Giảm lặp lại nhiều `<constructor-arg ref="..."/>`.
- Có thể phù hợp nếu constructors rõ và beans duy nhất theo type.

Rủi ro:

- Nếu không có bean phù hợp, khởi tạo có thể thất bại.
- Nếu có nhiều beans cùng kiểu mà không có cách chọn rõ, xảy ra ambiguity.
- Không tự autowire `String` và primitive values như một collaborator bean từ những literal config numbers; loại này nên được truyền explicit.
- Một thay đổi ở module khác thêm bean cùng interface có thể làm wiring cũ lỗi.
- Quan hệ phụ thuộc kém hiển thị trong XML, gây khó bảo trì code legacy.

**Quan trọng:** Explicit `<constructor-arg>` settings được ưu tiên hơn tự autowire cho những arguments đã khai báo. Nếu application có API phức tạp, explicit constructor args thường dễ review và debug hơn.

## 17. Constructor-arg với static factory method và instance factory method

Spring XML có thể tạo bean bằng **constructor** hoặc **factory method**. Trong trường hợp factory method, `<constructor-arg>` cũng có thể biểu diễn arguments mà Spring truyền cho factory method (dù tên phần tử vẫn là `constructor-arg`).

### 17.1. Static factory method

Java minh họa:

```java
public final class ClientFactory {
    private ClientFactory() {
    }

    public static ApiClient create(String endpoint, int timeoutMillis) {
        return new ApiClient(endpoint, timeoutMillis);
    }
}
```

XML:

```xml
<bean id="apiClient"
      class="example.ClientFactory"
      factory-method="create">
    <constructor-arg index="0" value="https://example.test"/>
    <constructor-arg index="1" value="1000"/>
</bean>
```

Ở đây Spring **không gọi `new ClientFactory(...)`**. Nó invoke static method `ClientFactory.create(String, int)`. Hai `<constructor-arg>` được dùng làm **factory method arguments**.

### 17.2. Instance factory method

Java minh họa:

```java
public final class ClientFactory {
    public ApiClient create(String region) {
        return new ApiClient(region);
    }
}
```

XML:

```xml
<bean id="clientFactory" class="example.ClientFactory"/>

<bean id="apiClient"
      factory-bean="clientFactory"
      factory-method="create">
    <constructor-arg value="ap-southeast-1"/>
</bean>
```

Bean `clientFactory` tồn tại như một managed factory object, còn `apiClient` là bean được tạo bằng instance method `create`. Những mã này là **minh họa riêng**, yêu cầu các class API tương ứng; không trộn hai phiên bản `ClientFactory` cùng tên vào một file.

**Đừng nhầm:** `factory-bean` trỏ tới bean factory object; `factory-method` là tên method; `<constructor-arg>` là argument. Đây không giống interface `FactoryBean<T>` của Spring, vốn có hợp đồng product vs factory bean riêng.

## 18. Type conversion và placeholders trong constructor-arg

XML `value="..."` bắt đầu là chuỗi. Khi tạo bean, Spring dựa vào metadata type target và conversion infrastructure để chuyển thành `int`, `long`, `boolean`, enum và các kiểu khác nếu có converter phù hợp.

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg index="0" value="3"/>
    <constructor-arg index="1" value="1500"/>
</bean>
```

Nếu signature là `RetrySettings(int, long)`, hai literals được chuyển sang numeric types.

### Chuyển đổi thất bại

```xml
<constructor-arg index="0" value="three"/>
```

không tự chuyển thành `int 3`; nếu không có custom converter, Spring sẽ báo type mismatch/conversion/bean creation error. Không che lỗi này bằng việc biến mọi constructor parameter thành `String` rồi parse bất kỳ lúc nào trong business method.

### Property placeholders

`<constructor-arg>` có thể dùng placeholders:

```xml
<bean id="retrySettings" class="example.RetrySettings">
    <constructor-arg index="0" value="${retry.maxAttempts}"/>
    <constructor-arg index="1" value="${retry.delayMillis}"/>
</bean>
```

Bạn cần một cơ chế giải quyết placeholder tương ứng, ví dụ `<context:property-placeholder location="classpath:app.properties"/>`, `PropertySourcesPlaceholderConfigurer`, hoặc hạ tầng cấu hình của ứng dụng.

File `app.properties` minh họa:

```properties
retry.maxAttempts=3
retry.delayMillis=1500
```

Placeholder thay giá trị vào metadata; Spring sau đó mới dùng conversion để tạo tham số thực của constructor. **Không đồng nghĩa** bản thân `<constructor-arg>` sẽ tự mở/đọc file properties nếu chưa có processor.

### Khi cần kiểu đặc thù

Với `Duration`, `URI` hoặc custom value object, cần xác nhận conversion service / property editor / constructor contract. Không giả định mọi chuỗi đều tự chuyển thành mọi Java class tùy ý. Nếu cấu hình phức tạp, một **settings bean có factory method** sẽ rõ và dễ test hơn parsing rải rác.

## 19. Bean scope, lifecycle và identity

XML constructor arguments tham chiếu managed beans, nhưng behavior cụ thể còn phụ thuộc **scope của bean**.

### Singleton dependency

```xml
<bean id="repo" class="example.MemoryRepo"/>

<bean id="serviceA" class="example.ServiceA">
    <constructor-arg ref="repo"/>
</bean>

<bean id="serviceB" class="example.ServiceB">
    <constructor-arg ref="repo"/>
</bean>
```

Nếu cả hai services được tạo trong cùng một BeanFactory, `repo` mặc định là singleton nên hai constructors thường nhận **cùng repo reference**.

### Prototype dependency được inject một lần vào singleton

```xml
<bean id="worker" class="example.Worker" scope="prototype"/>

<bean id="scheduler" class="example.Scheduler">
    <constructor-arg ref="worker"/>
</bean>
```

Nếu `scheduler` là singleton, Spring phân giải prototype `worker` tại lúc tạo scheduler, rồi scheduler giữ reference đó. Việc gọi method của scheduler sau này không tự inject worker mới mỗi lần.

Muốn lấy prototype theo từng job, dùng `ObjectProvider<Worker>` hoặc factory chuyên dụng, đừng trông chờ chỉ khai báo `scope="prototype"` sẽ làm object được thay thế liên tục.

### Lifecycle của collaborator

Một `ref` tới bean có `init-method` hoặc `destroy-method` cho phép Spring quản lý lifecycle theo definition. Nếu tự viết `new MemoryRepo()` bên trong constructor của service, object phụ đó **không tự nhận** Spring lifecycle từ bean `repo`.

### Inner bean khác shared named bean

Như mục 12, inner bean gắn với outer bean và không dùng như singleton được chia sẻ trên toàn context. Nếu cần reuse hoặc quản lý lifecycle độc lập, định nghĩa bean name riêng và truyền bằng `ref`.

## 20. Phụ thuộc vòng: lỗi cần sửa ở đồ thị, không chỉ đổi XML

Constructor injection phơi bày dependency cycle sớm. Xem:

```java
public final class ServiceA {
    public ServiceA(ServiceB b) {
    }
}

public final class ServiceB {
    public ServiceB(ServiceA a) {
    }
}
```

XML:

```xml
<bean id="serviceA" class="example.ServiceA">
    <constructor-arg ref="serviceB"/>
</bean>

<bean id="serviceB" class="example.ServiceB">
    <constructor-arg ref="serviceA"/>
</bean>
```

Đồ thị:

```text
serviceA --> serviceB --> serviceA
```

BeanFactory cần B để xây A, nhưng phải có A để xây B. Đây là **constructor cycle** thường bất khả giải. Có thể thấy `BeanCurrentlyInCreationException` ở root cause, được bọc trong bean creation/dependency exceptions.

### Cách sửa đáng ưu tiên

- Tách phần trách nhiệm chung thành `SharedPolicy` hoặc `DomainRule` để hai services cùng phụ thuộc nó.
- Đưa orchestration vào một bean thứ ba đứng trên hai services, thay vì services gọi lẫn nhau.
- Nếu một phía chỉ cần thông báo sự kiện, cân nhắc application events với hợp đồng consistency/idempotency rõ.
- Nếu dependency thật sự phải lazy, xét provider/proxy **có chủ đích**, nhưng đừng dùng để che vòng kiến trúc.

### Có giúp nếu đổi sang setter injection?

Một số vòng setter/field injection có thể được Spring xử lý bằng cơ chế **early singleton references** nếu được cho phép, nhưng điều này có thể dẫn đến object chưa hoàn toàn khởi tạo, tương tác phức tạp với AOP/proxy và khó kiểm thử. Không xem nó là lựa chọn thiết kế mặc định.

### @DependsOn không giải quyết cycle

`@DependsOn` chỉ biểu diễn thứ tự khởi tạo, không thay object bắt buộc. Nếu A depends on B và B depends on A, bạn tạo thêm vòng ordering; không sửa vòng bằng cách thêm `depends-on="..."` hoặc đảo thứ tự các thẻ `<bean>` trong XML.

## 21. Dùng @ImportResource khi chuyển XML sang Java config

Một ứng dụng Java-centric có thể giữ XML chứa `constructor-arg`:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:beans.xml")
public class RootConfig {
    // Các @Bean khác có thể khai báo ở đây.
}
```

Đây là **đoạn minh họa**; cần import `org.springframework.context.annotation.Configuration` và `ImportResource`. Khi root được Spring register vào `AnnotationConfigApplicationContext`, XML definitions được nhập vào **cùng container**. Những `ref` references có thể trỏ tới beans từ Java `@Bean` nếu bean names phù hợp.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-service.xml")
class RootConfig {
    @Bean("reportRepository")
    ReportRepository reportRepository() {
        return new InMemoryReportRepository();
    }
}
```

XML:

```xml
<bean id="reportService" class="example.ReportService">
    <constructor-arg ref="reportRepository"/>
</bean>
```

Spring tìm bean `reportRepository` do Java khai báo rồi truyền vào constructor `ReportService` từ XML. Không cần tạo context thứ hai và cũng không cần viết thêm một factory method để duplicate repo.

### Khi chuyển constructor-arg sang @Bean parameters

XML:

```xml
<bean id="catalogService" class="example.CatalogService">
    <constructor-arg ref="catalog"/>
    <constructor-arg value="SKU-"/>
</bean>
```

Java config tương đương về ý định:

```java
@Bean("catalogService")
CatalogService catalogService(Catalog catalog) {
    return new CatalogService(catalog, "SKU-");
}
```

Spring inject `Catalog` vào parameter của factory method; Java code truyền literal tới constructor. Đảm bảo **không còn bean definition XML cùng tên** nếu đã chuyển qua Java để tránh trùng tên/overriding ngoài ý định.

### Giữ hợp đồng khi migration

Nếu XML có constructor index/type/name, nên kiểm tra rằng Java factory mới vẫn truyền đúng ý nghĩa arguments, đặc biệt khi có nhiều `String` hoặc enum settings. Đừng nghĩ code compile thành công là đủ: migration có thể làm đổi default values, profiles hoặc lifecycle mà compiler không nhìn thấy.

## 22. Debug lỗi constructor-arg theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `BeanCreationException` nói không tìm được constructor phù hợp | Số lượng/type arguments không match constructor | Kiểm tra signature thực, `index`/`type`/`name` và class package |
| `UnsatisfiedDependencyException` | Ref đến bean thiếu hoặc dependency chain khởi tạo lỗi | Kiểm tra bean definitions và root cause |
| `NoSuchBeanDefinitionException` | `ref="..."` trỏ tên bean không tồn tại | Sửa bean id/alias; import config đúng |
| `BeanCurrentlyInCreationException` | Constructor cycle hoặc early bean creation | Vẽ đồ thị dependencies, tách trách nhiệm |
| `BeanNotOfRequiredTypeException` | Ref tồn tại nhưng type không tương thích hoặc proxy expose interface khác | Điều chỉnh interface/bean type |
| `TypeMismatchException`/conversion error | `value` không thể chuyển sang parameter type | Sửa literal, type, converter |
| `constructor-arg name` không match | Build thiếu `-parameters` hoặc `@ConstructorProperties` không đúng | Bật metadata hoặc dùng `index` |
| Constructor overloaded bị chọn sai/ambiguous | Nhiều candidates nhận string/number literals | Dùng `type`/`index` hoặc sửa API để rõ |
| Hai Strings bị đảo nhau | Không đánh dấu index/name | Đặt `index="0"/"1"` hoặc `name` có metadata |
| Index vượt giới hạn | `index` ngoài số parameters hợp lệ | Kiểm tra constructor argument count |
| Duplicate index | Hai thẻ cùng vị trí | Loại duplicate, một value cho mỗi parameter |
| `c:_0-ref` bị thay bằng `c:_0` | Chuỗi literal thay cho bean ref | Thêm hậu tố `-ref` |
| XML c-namespace không nhận | Thiếu `xmlns:c` | Khai báo c namespace tại `<beans>` |
| Không thấy bean class | Sai fully qualified class name/JAR thiếu | Sửa dependency và classpath |
| Nested class trong XML không instantiate | Dùng dấu chấm thay `$` hoặc thiếu public/static | Dùng binary class name và constructor hợp lệ |
| Output đổi sau refactor parameter order | Dùng `index` nhưng constructor đổi thứ tự | Update XML cùng refactor hoặc dùng name metadata |
| App chạy trên IDE nhưng lỗi sau packaging | XML không nằm ở runtime resources classpath | Kiểm tra `src/main/resources` và JAR |
| Bean tạo sớm bất ngờ | Singleton eager hoặc collaborator bắt buộc | Xem lazy/scope/dependency graph |
| Missing placeholder | Property processor/source chưa khai báo | Kiểm tra Environment và configurer |
| Wrong singleton/prototype behavior | Nhầm `ref` với inner bean hoặc scope | Kiểm tra bean definitions và lifecycle |

### Quy trình debug có thứ tự

1. Xác minh file XML đã được `ApplicationContext` đọc và bean name được đăng ký.
2. Xác minh `class="..."` có tồn tại, là kiểu phù hợp và Spring có thể instantiate.
3. Đọc tất cả constructors của class; kiểm tra số arguments và overloads.
4. Đọc `<constructor-arg>` có khai báo `index`, `type`, `name` hay không; không tự giả định Spring chọn theo thứ tự thẻ trong mọi tình huống.
5. Xác minh `ref` trỏ đúng bean name và type; đừng nhầm với `value`.
6. Với `name`, xác minh Maven/Javac có `-parameters` hoặc `@ConstructorProperties`.
7. Với literal, xem conversion có thể thành công với type được yêu cầu không.
8. Kiểm tra scope/proxy và xem consumer cần singleton hay prototype.
9. Nếu có cycle, vẽ đồ thị constructor dependencies thay vì thêm `@DependsOn`/`@Lazy` vô tội vạ.
10. Test bằng ApplicationContext thật; xem root cause thay vì chỉ wrapper message.

## 23. Kiểm thử và kiểm tra an toàn khi cấu hình XML

### 23.1. Test bằng ApplicationContext

Một chương trình nhỏ có thể khởi tạo context rồi assert:

```java
// Đoạn bổ sung đặt bên trong main khi biến context còn mở.
Catalog catalog = context.getBean(Catalog.class);
CatalogService service = context.getBean(CatalogService.class);

if (catalog != service.catalog()) {
    throw new AssertionError("Expected same managed Catalog singleton");
}
if (!"SKU-Java book".equals(service.describe("BK-7"))) {
    throw new AssertionError("Wrong constructor arguments");
}
```

Đây là **đoạn mở rộng** của file `XmlConstructorArgsDemo.java`, không phải chương trình độc lập.

### 23.2. Kiểm tra XML bindings theo name

Với `RetrySettings`, thử đảo hai thẻ `name` (không thay value) rồi so sánh output. Test này chứng minh `name` mapping không phụ thuộc thứ tự khi metadata đúng.

Tương tự, với `index`, đảo thứ tự các XML tags nhưng giữ nguyên `index="0"/"1"`. Kết quả phải giống ban đầu, bởi parameter positions được khai báo tường minh.

### 23.3. Negative tests

Tạo context test riêng cho từng lỗi:

- Bean ref không tồn tại.
- Primitive conversion sai.
- Duplicate index.
- Overloaded constructors không rõ.
- Vòng A→B→A.
- XML c-namespace thiếu prefix declaration.
- Constructor name mapping thiếu metadata.
- Inner bean được tra cứu như named bean.

**Không sửa file cấu hình production để thử lỗi**. Dùng bản sao test resources hoặc embedded test configurations rồi assert context startup fail với nguyên nhân phù hợp. Thông báo exception đầy đủ có thể đổi theo Spring version; test nên kiểm tra loại lỗi/nguyên nhân quan trọng thay vì toàn bộ stack trace string.

### 23.4. Unit test không cần Spring

Nếu business class chỉ phụ thuộc interface:

```java
Catalog fake = sku -> "Fake item";
CatalogService service = new CatalogService(fake, "TEST-");

if (!"TEST-Fake item".equals(service.describe("anything"))) {
    throw new AssertionError("Unexpected service output");
}
```

Đây là đoạn trong phạm vi class demo có các kiểu `Catalog`/`CatalogService` sẵn. Nó không cần XML/BeanFactory vì unit test kiểm tra business logic; integration test mới cần xác nhận cấu hình `<constructor-arg>`.

### 23.5. Tránh mở context nhiều lần hoặc quên đóng

Trong Spring Framework thuần:

```java
try (var context = new ClassPathXmlApplicationContext("beans.xml")) {
    // Tra cứu và kiểm tra bean.
}
```

`try-with-resources` bảo đảm `close()` trên context. Nếu bean giữ file/socket/pool, Spring sẽ gọi destroy callbacks theo bean scope/lifecycle phù hợp. Một test mở nhiều contexts có thể tạo nhiều singleton sets độc lập; không nhầm “singleton” là một instance trên toàn JVM.

## 24. Những hiểu lầm phổ biến

### “ref và value đều chỉ là text nên như nhau”

Sai. Cả hai được viết thành XML attribute strings, nhưng Spring diễn giải `ref` như **bean reference** và `value` như **literal cần convert**. Chọn sai thay đổi toàn bộ dependency graph.

### “index bắt đầu từ 1 cho dễ hiểu”

Sai. `index` bắt đầu từ **0**. Với signature `Client(String, int)`, `index="0"` là `String`, `index="1"` là `int`.

### “name luôn hoạt động vì source Java có tên tham số”

Sai. Compiler không bắt buộc đưa parameter names vào runtime metadata nếu không cấu hình `-parameters`; có thể thay bằng JDK `@ConstructorProperties` hoặc dùng `index`.

### “type=int tạo một bean kiểu int”

Sai. `type` chỉ hỗ trợ constructor argument matching. `<bean class="...">` quyết định class/object bean chính.

### “Đổi thứ tự <constructor-arg> không bao giờ quan trọng”

Sai nếu bạn không khai báo index/name/type và Spring phải dựa vào thứ tự để map arguments. Khi `index` hoặc `name` rõ ràng, thứ tự trình bày các thẻ có thể ít ảnh hưởng hơn; tuy nhiên, XML cần được test sau refactor.

### “<constructor-arg> chỉ dùng cho new Class(...)”

Không hoàn toàn. Spring dùng cấu trúc argument metadata này cả cho **static/instance factory methods** khi bean được định nghĩa qua `factory-method` hoặc `factory-bean`.

### “Constructor injection làm Spring tự tạo interface”

Không. Spring cần một bean definition hoặc factory cung cấp implementation tương thích với interface. XML `<constructor-arg ref="catalog"/>` phải trỏ đúng bean có thể được instantiate.

### “Một prototype ref trong singleton sẽ thay instance mỗi request”

Sai. Constructor được gọi khi singleton được tạo; prototype dependency lúc đó được phân giải một lần cho constructor call. Muốn lấy prototype liên tục cần dynamic lookup factory/provider đúng nghĩa.

### “Có cycle thì đổi hết sang setter injection”

Không nên. Một số vòng setter có thể qua được với early references, nhưng mô hình vẫn coupling và có nguy cơ incomplete state. Constructor cycle nên được sửa bằng dependency inversion/coordinator.

### “c:_0-ref và c:_0 khác nhau chỉ ở tên attribute”

Sai về semantics. Hậu tố `-ref` chỉ **bean reference**; không có nó là **literal**. Hai cách có thể trùng kiểu XML string nhưng hoàn toàn khác kiểu giá trị Spring truyền vào constructor.

### “@ImportResource là một context khác”

Sai. Khi Java config import XML trong cùng ApplicationContext, bean definitions từ XML và `@Bean` được quản lý bởi cùng BeanFactory; không cần tạo `ClassPathXmlApplicationContext` bên trong một `@Bean`.

## 25. Bài tập có đáp án định hướng

### Bài 1 — Hai tham số cùng String

Constructor:

```java
public UserLabel(String firstName, String lastName) { }
```

Hãy viết XML không phụ thuộc thứ tự thẻ.

**Đáp án:**

```xml
<bean id="userLabel" class="example.UserLabel">
    <constructor-arg index="1" value="Nguyen"/>
    <constructor-arg index="0" value="An"/>
</bean>
```

Constructor nhận `firstName = "An"` và `lastName = "Nguyen"`. Index 0-based.

### Bài 2 — Bean reference

XML:

```xml
<bean id="formatter" class="example.Formatter"/>
<bean id="printer" class="example.Printer">
    <constructor-arg value="formatter"/>
</bean>
```

Nếu `Printer(Formatter)` cần object bean, cần sửa gì?

**Đáp án:** `<constructor-arg ref="formatter"/>`; `value` chỉ truyền chuỗi, không phải instance `Formatter`.

### Bài 3 — Type matching

Constructor `Options(int attempts, String label)`. Viết XML làm rõ target types.

**Đáp án:**

```xml
<bean id="options" class="example.Options">
    <constructor-arg type="int" value="4"/>
    <constructor-arg type="java.lang.String" value="fast"/>
</bean>
```

Spring có type metadata để match đúng signature và convert literal `4` sang int.

### Bài 4 — name và build metadata

Với `RetrySettings(int maxAttempts, long delayMillis)`, XML dùng `name`. Compiler cần gì?

**Đáp án:** Bật `javac -parameters` hoặc đặt `@ConstructorProperties({"maxAttempts","delayMillis"})` trên constructor, hoặc chuyển sang explicit `index` nếu không giữ metadata names.

### Bài 5 — c-namespace

Hãy đổi:

```xml
<bean id="reporter" class="example.Reporter">
    <constructor-arg index="0" ref="service"/>
    <constructor-arg index="1" value="DEBUG:"/>
</bean>
```

thành c-namespace.

**Đáp án:**

```xml
<bean id="reporter"
      class="example.Reporter"
      c:_0-ref="service"
      c:_1="DEBUG:"/>
```

Nhớ khai báo `xmlns:c="http://www.springframework.org/schema/c"` trên root `<beans>`.

### Bài 6 — Tên bean và tên parameter

`<bean id="retry" ...><constructor-arg name="limit" value="3"/></bean>`. Hai chuỗi `retry` và `limit` có vai trò gì?

**Đáp án:** `retry` là bean name trong Spring; `limit` là tên Java constructor parameter. Không dùng tên bean để suy ra parameter index.

### Bài 7 — Inner bean hay shared bean?

Hai services cần cùng một `FilterPolicy` singleton. Nên lặp hai inner `<bean>` definitions hay đặt một named bean?

**Đáp án:** Đặt một named bean `filterPolicy` và dùng `<constructor-arg ref="filterPolicy"/>` ở cả hai services. Inner bean gắn riêng với outer bean; không cho shared container singleton identity như named singleton.

### Bài 8 — Static factory

Một class `ClientFactory` có `public static Client build(String url)`. XML có thể truyền argument bằng `<constructor-arg>` không?

**Đáp án:** Có, khi bean được khai báo `class="...ClientFactory" factory-method="build"`; argument truyền vào **factory method**, không phải constructor của `ClientFactory`.

### Bài 9 — Prototype

Một singleton `Scheduler` nhận `Worker` prototype trong constructor. Scheduler có tự nhận một worker mới sau mỗi lời gọi `run()` không?

**Đáp án:** Không. Prototype được giải quyết khi constructor singleton chạy; Scheduler giữ reference đó. Muốn worker mới từng job, dùng dynamic lookup/factory phù hợp.

### Bài 10 — Placeholder

`<constructor-arg value="${service.timeout}"/>` có tự đọc key từ app.properties không?

**Đáp án:** Không. Cần hạ tầng placeholder/environment configuration, ví dụ property-placeholder processor hoặc cấu hình tương đương. Sau resolve, Spring có thể convert chuỗi thành type constructor parameter.

### Bài 11 — Vòng constructor

`A(B)` và `B(A)` được wiring qua `ref`. Đổi thứ tự `<bean>` có sửa được không?

**Đáp án:** Không. Đồ thị dependency có vòng; phải sửa trách nhiệm/abstraction hoặc orchestration chứ không chỉ đổi thứ tự XML.

### Bài 12 — Dự đoán output

Trong project mục 13, `service.describe("BK-7")` và `reporter.line("MUG-2")` trả gì?

**Đáp án:** `SKU-Java book` và `REPORT:SKU-Coffee mug`. Prefix `SKU-` đến từ `<constructor-arg index="1" value="SKU-"/>`, còn `REPORT:` từ `c:_1="REPORT:"`.

### Bài 13 — Đổi Java signature

Bạn thay `Reporter(CatalogService service, String label)` thành `Reporter(String label, CatalogService service)` nhưng giữ nguyên `c:_0-ref` và `c:_1`. Có an toàn không?

**Đáp án:** Không. Positional mapping giờ đảo type: `c:_0-ref` trỏ service vào parameter `String` và `c:_1` literal string vào parameter `CatalogService`. Cần sửa XML hoặc dùng name-based mapping có metadata tương ứng.

### Bài 14 — Refactor XML sang Java config

XML:

```xml
<bean id="catalogService" class="example.CatalogService">
    <constructor-arg ref="catalog"/>
    <constructor-arg value="SKU-"/>
</bean>
```

Viết Java factory tương đương về wiring.

**Đáp án:**

```java
@Bean("catalogService")
CatalogService catalogService(Catalog catalog) {
    return new CatalogService(catalog, "SKU-");
}
```

Cần đảm bảo Java config được Spring đăng ký và loại bỏ XML definition trùng tên khi chuyển.

## 26. Checklist trước khi đưa XML vào dự án

- [ ] XML `<beans>` root, namespaces/schema và resource path hợp lệ.
- [ ] Bean class tồn tại và có constructor/factory method phù hợp.
- [ ] Mọi dependency bắt buộc được biểu diễn qua `ref` hoặc explicit value phù hợp.
- [ ] `ref` không bị nhầm với literal `value`.
- [ ] `index` (nếu dùng) bắt đầu từ 0 và khớp Java parameter order.
- [ ] `type` đủ rõ khi có overload hoặc multiple primitive/string values.
- [ ] `name` có metadata Java parameter names nhờ `-parameters` hoặc `@ConstructorProperties`.
- [ ] Không có duplicate index/name hoặc arguments bị bỏ sót.
- [ ] Nhiều `String` parameters đã được làm rõ theo semantic.
- [ ] Type conversion của literal values được test trong ApplicationContext.
- [ ] `c:` namespace được khai báo đúng; biết hậu tố `-ref`.
- [ ] Collections/inner beans chỉ được dùng khi phù hợp ownership/lifecycle.
- [ ] Constructor autowiring có ứng viên duy nhất hoặc qualifier rõ.
- [ ] Không có constructor cycles trong dependency graph.
- [ ] Scope singleton/prototype phù hợp cách consumer giữ reference.
- [ ] Không tự tạo Spring context thứ hai để lấy dependency.
- [ ] Khi chuyển XML sang `@Bean`, giữ đúng bean names và dependency semantics.
- [ ] Integration test kiểm tra managed identity, args và output.
- [ ] Context được đóng để cleanup resources theo lifecycle phù hợp.

## Tổng kết

`<constructor-arg>` là công cụ trọng tâm của **constructor-based dependency injection trong Spring XML**. Nó cho phép mô tả rõ các dependencies bắt buộc của một bean mà không yêu cầu class Java tự tạo collaborator.

Ba thuộc tính phân giải quan trọng là:

- **`index`:** vị trí argument **0-based**, không cần metadata tên tham số.
- **`type`:** giúp Spring tìm signature đúng, nhất là với literals và overloaded constructors.
- **`name`:** giúp XML mô tả ý nghĩa parameter; cần `-parameters` hoặc `@ConstructorProperties` để Spring nhận diện tên đáng tin cậy.

Và hai dạng giá trị cơ bản nhất:

- **`ref`:** lấy một **managed bean reference**.
- **`value`:** truyền **literal**, chuyển kiểu theo target parameter.

Có thể dùng **`c:` namespace** làm shortcut, nested `<list>`/`<map>` khi cấu trúc phức tạp, và `<constructor-arg>` cũng áp dụng cho arguments của factory methods. Dù chọn dạng nào, hãy ưu tiên **constructor signatures rõ ràng, dependency graph không có vòng, scope/lifecycle đúng và integration tests**. XML nên làm nổi bật quan hệ phụ thuộc, không che chúng bằng overload hoặc magic conversion khó đoán.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor-based DI, argument type/index/name matching, `-parameters` và `@ConstructorProperties`.
- [Spring Framework 6.2 — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-properties-detailed.html): `ref`, `value`, `idref`, `inner bean`, collections và c-namespace.
- [Spring Framework 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html): `autowire="constructor"`, giới hạn và ambiguity.
- [Spring Framework 6.2 — Bean Definition Basics](https://docs.spring.io/spring-framework/reference/6.2/core/beans/basics.html): bean definitions, XML configuration và container.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype và lifetime semantics.
- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): kết hợp XML với `@ImportResource`.
