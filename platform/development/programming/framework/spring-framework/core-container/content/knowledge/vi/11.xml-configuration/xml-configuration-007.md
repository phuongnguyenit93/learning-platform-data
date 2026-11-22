# Autowiring XML theo tên, theo kiểu và giới hạn của cơ chế trong Spring Framework

## 1. Khi không muốn viết mọi `<property ref="..."/>` bằng tay

Spring Core Container quản lý các đối tượng (beans) và quan hệ phụ thuộc của chúng. Với XML bean definitions, cách rõ ràng nhất để nối hai bean là khai báo tường minh:

```xml
<bean id="inventoryRepository" class="demo.InventoryRepository"/>

<bean id="inventoryService" class="demo.InventoryService">
    <property name="repository" ref="inventoryRepository"/>
</bean>
```

Đây là **XML minh họa**; muốn dùng thực tế, `InventoryService` phải có setter `setRepository(...)` phù hợp và hai class phải tồn tại trên runtime classpath.

Spring cũng cho phép **XML autowiring**: trên một `<bean>` definition, đặt thuộc tính `autowire` để BeanFactory tìm collaborator theo tên property, theo kiểu property hoặc theo constructor. Ví dụ:

```xml
<bean id="repository" class="demo.InventoryRepository"/>

<bean id="inventoryService"
      class="demo.InventoryService"
      autowire="byName"/>
```

Khi object `inventoryService` có writable JavaBean property `repository` (ví dụ `setRepository(...)`), Spring có thể tìm bean có tên chính xác `repository` rồi gọi setter. Không cần viết `<property name="repository" ref="repository"/>` trên bean này.

Nhưng autowiring **không có nghĩa Spring chọn đại một bean phù hợp**, cũng không mặc nhiên thay thế những nguyên tắc về bean name, type, scope hoặc lifecycle. Autowiring XML có các giới hạn rõ: scalar values không được tự đoán, nhiều ứng viên có thể gây lỗi, một số property bị bỏ qua nếu không có ứng viên và quan hệ phụ thuộc trở nên ít tường minh hơn.

Sau bài này, người học có thể:

1. Phân biệt `autowire="no"`, `"byName"`, `"byType"` và `"constructor"`.
2. Hiểu chuẩn JavaBean property name và cách Spring tìm bean theo name/type.
3. Nhận diện missing candidate, ambiguous candidate, primary candidate và reference bị loại khỏi autowiring.
4. Sử dụng `autowire-candidate="false"`, `primary="true"`, `default-autowire-candidates` đúng nghĩa.
5. Biết vì sao `<property>`/`<constructor-arg>` tường minh được ưu tiên.
6. Hiểu collection/array/map autowiring và giới hạn của scalar properties.
7. Phân biệt XML autowiring với annotation `@Autowired` và JavaConfig.
8. Chạy demo Java 17+ / Spring Framework 6.2 có stdout kiểm chứng tên, kiểu, explicit ref và candidate filtering.
9. Biết kiểm tra cấu hình, thiết kế dependency rõ ràng và tránh lỗi runtime.

## 2. Bốn chế độ chính của XML autowiring

Trong Spring Framework 6.2, thuộc tính `autowire` của phần tử `<bean>` chấp nhận bốn mode chính:

| XML mode | Cách tìm dependency | Khi không có bean phù hợp | Khi nhiều bean phù hợp |
| --- | --- | --- | --- |
| `no` | Không tự wire; cần `ref`/`constructor-arg` hoặc cơ chế khác | Property không tự được cấp | Không có lookup tự động cho property ấy |
| `byName` | Tìm bean có **tên trùng tên JavaBean property** | Property không được set bởi byName | Không lấy ngẫu nhiên theo type; name match quyết định |
| `byType` | Tìm bean theo **kiểu của writable property** | Với dependency đơn, có thể bỏ qua setter | Nếu không có một ứng viên thắng, lỗi ambiguity |
| `constructor` | Giải quyết các **tham số constructor** tương tự by-type resolution | Constructor bắt buộc không resolve được thường làm tạo bean thất bại | Không có ứng viên thắng cho dependency đơn thì thất bại |

Chế độ mặc định của `<bean>` là **`no`**. Spring không yêu cầu mọi XML bean tự động được wire.

Ví dụ cú pháp:

```xml
<bean id="manual" class="demo.Service" autowire="no"/>
<bean id="named" class="demo.Service" autowire="byName"/>
<bean id="typed" class="demo.Service" autowire="byType"/>
<bean id="constructed" class="demo.ConstructorService"
      autowire="constructor"/>
```

Đây là những bean definitions **minh họa**; các class chỉ là tên giả định. Trên mỗi bean definition, `autowire` biểu thị **phương pháp Spring tìm dependency**, không khai báo rằng chính bean ấy đã trở thành một dependency bắt buộc của bean khác.

### 2.1. `autowire="no"` không cấm injection

`no` nghĩa là **không tự tìm collaborator bằng cơ chế XML autowiring**. Bạn vẫn có thể cấu hình:

```xml
<bean id="service" class="demo.Service" autowire="no">
    <property name="repository" ref="repository"/>
</bean>
```

hoặc cấp constructor arguments. Đồng thời, một bean có `autowire="no"` vẫn có thể nhận annotation-based injection nếu Spring đã bật các post-processors liên quan và class mang annotations phù hợp.

Không gộp `autowire="no"` với `autowire-candidate="false"`. Thuộc tính thứ nhất nói **bean này có tự nối dependencies của nó bằng XML không**; thuộc tính thứ hai nói **bean này có được chọn làm ứng viên để inject cho bean khác theo type không**.

### 2.2. Autowiring được cấu hình theo từng bean

`<bean id="a" ... autowire="byType"/>` chỉ yêu cầu BeanFactory xem xét dependency của **bean a** theo byType; nó không ép mọi bean còn lại chuyển sang byType.

Có thể dùng `default-autowire="byType"` trên root `<beans>` nếu muốn đặt mặc định cho các bean definitions không chỉ định riêng:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-autowire="byType">
    <bean id="a" class="demo.A"/>
    <bean id="b" class="demo.B" autowire="no"/>
</beans>
```

Đây là **XML minh họa**, không cần dùng cấu hình này trong bài demo chính. Mặc định cấp root giúp giảm lặp nhưng có thể làm dependency graph khó đọc và gây wiring ngoài ý muốn khi dự án lớn lên. Tài liệu Spring khuyến khích sự tường minh ở các hệ thống lớn.

## 3. `byName`: bean name phải trùng JavaBean property name

Với Java class:

```java
package demo;

public final class InvoiceService {
    private InvoiceRepository repository;

    public void setRepository(InvoiceRepository repository) {
        this.repository = repository;
    }

    public InvoiceRepository getRepository() {
        return repository;
    }
}
```

Spring nhìn nhận một **writable property tên `repository`** bởi method `setRepository(...)`. Nếu XML khai báo:

```xml
<bean id="repository" class="demo.InvoiceRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

thì Spring tìm bean có tên đúng `repository` và thực hiện setter injection. Đó là ý nghĩa của “theo tên”.

**Lưu ý:** hai fragment ở đây mô tả một class giả định `InvoiceRepository`; chúng chưa tạo thành một project compile độc lập cho đến khi class ấy được định nghĩa.

### 3.1. Tên JavaBean property không nhất thiết là tên field

Với:

```java
private Repository primaryStore;

public void setRepository(Repository value) {
    this.primaryStore = value;
}
```

thì tên property vẫn là `repository` vì method tên `setRepository`. XML `autowire="byName"` tìm bean `repository`, không tìm bean `primaryStore` chỉ vì field có tên như vậy.

Nếu đổi setter thành `setPrimaryStore(...)` thì property name là `primaryStore`. Bean naming convention vì vậy có tác động trực tiếp đến XML byName wiring.

### 3.2. Không có bean trùng tên thì sao?

Giả sử class có setter `setRepository(...)` nhưng registry chỉ chứa bean tên `mainRepository`. Chế độ `byName` không tự nhìn sang kiểu `Repository` rồi lấy `mainRepository` như `byType`. Setter ấy có thể bị bỏ qua, giữ default field value — thường là `null`.

```xml
<bean id="mainRepository" class="demo.InvoiceRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

Kết quả **không** phải lỗi cấu hình chắc chắn ngay tại refresh. Nếu code nghiệp vụ sau đó giả định repository không null, có thể gặp `NullPointerException` muộn. Hãy viết integration test/validation cho dependency quan trọng.

Cách sửa có chủ đích: đổi bean name thành `repository`, thêm alias `<alias name="mainRepository" alias="repository"/>`, hoặc dùng explicit `<property name="repository" ref="mainRepository"/>`.

### 3.3. byName không có nghĩa “tên class gần giống”

Tên property `repository` không được xem như một gợi ý fuzzy matching. Bean `repositoryImpl` hoặc `Repository` khác chữ hoa/thường **không tự được chọn** chỉ vì tên giống. Nếu không bảo đảm naming convention, dùng explicit ref hoặc byType/qualifier phù hợp.

### 3.4. Bean phải tương thích với setter type

Bean name có thể đúng nhưng instance không phù hợp kiểu setter:

```xml
<bean id="repository" class="java.lang.String">
    <constructor-arg value="oops"/>
</bean>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byName"/>
```

Nếu setter muốn `InvoiceRepository`, Spring không thể gán một bean `String` vào property kiểu đó theo cách bình thường. Lúc này có thể có `TypeMismatchException`/`BeanCreationException` hoặc lỗi conversion tương ứng. byName chọn **tên**, nhưng vẫn phải đáp ứng hợp đồng kiểu Java khi gán object.

### 3.5. Bean alias cũng tham gia name lookup

Nếu:

```xml
<bean id="mainRepository" class="demo.InvoiceRepository"/>
<alias name="mainRepository" alias="repository"/>
```

thì bean có thể được lookup bằng `repository`; chế độ byName có thể tận dụng alias đã đăng ký. Alias trỏ tới cùng bean definition, không tạo thêm object chỉ vì có hai tên.

## 4. `byType`: một dependency đơn cần một ứng viên thắng

Với:

```java
public class InvoiceService {
    private Repository store;

    public void setStore(Repository store) {
        this.store = store;
    }
}
```

chế độ `autowire="byType"` sẽ tìm các bean kiểu `Repository` phù hợp với parameter của writable property `store`. Tên property `store` **không cần** trùng bean name.

Ví dụ:

```xml
<bean id="dbRepository" class="demo.DatabaseRepository"/>
<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

Nếu `DatabaseRepository implements Repository` và chỉ có một autowire candidate phù hợp, Spring có thể inject bean `dbRepository` vào `setStore(Repository)` mặc dù tên khác `store`.

### 4.1. Không có candidate

Nếu không có bean kiểu `Repository` phù hợp, Spring XML byType cho property đơn thường **không gọi setter**, thay vì luôn ném exception. Class có thể giữ `store == null`. Đây là điểm khác với `@Autowired` mặc định `required=true` hoặc constructor dependency bắt buộc.

**Hệ quả thiết kế:** với dependency thực sự không thể thiếu, đừng dựa duy nhất vào byType setter rồi bỏ qua test. Constructor injection hoặc khai báo explicit dependency giúp lỗi xuất hiện sớm hơn.

### 4.2. Có đúng một candidate

Nếu bean `dbRepository` là ứng viên phù hợp duy nhất, Spring inject nó. Kiểu có thể là interface/superclass mà implementation implement/extends. Không yêu cầu bean name trùng property name.

### 4.3. Có nhiều candidate

Ví dụ:

```xml
<bean id="primaryRepository" class="demo.DatabaseRepository"/>
<bean id="backupRepository" class="demo.InMemoryRepository"/>

<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

Nếu cả hai implement `Repository` và đều là candidates, Spring không được tùy tiện chọn một. Trong cấu hình không có điều kiện lựa chọn khác, bạn có thể gặp `NoUniqueBeanDefinitionException` hoặc `UnsatisfiedDependencyException`/`BeanCreationException` bọc nguyên nhân liên quan.

Các hướng xử lý:
- Dùng `<property name="store" ref="primaryRepository"/>` để chỉ định chính xác.
- Dùng `primary="true"` để chọn một default trong tình huống phù hợp.
- Đặt `autowire-candidate="false"` trên bean không muốn được dùng trong type-based autowiring.
- Đổi thiết kế từ single dependency sang collection nếu consumer thật sự cần nhiều implementations.
- Với annotation-based injection, `@Qualifier` và các cơ chế refinement khác có thể diễn đạt ngữ nghĩa cụ thể.

### 4.4. `primary="true"` là một ưu tiên lựa chọn

```xml
<bean id="fastRepository"
      class="demo.FastRepository"
      primary="true"/>

<bean id="safeRepository"
      class="demo.SafeRepository"/>

<bean id="invoiceService"
      class="demo.InvoiceService"
      autowire="byType"/>
```

Nếu hai implementations cùng kiểu và bean `fastRepository` là primary candidate thích hợp duy nhất, Spring có thể chọn nó cho dependency đơn byType. Không nên gắn `primary="true"` lên nhiều beans ngang nhau rồi mong ambiguity tự biến mất.

**Primary không phải filter collection:** một injection point kiểu `List<Repository>` có thể nhận nhiều repository candidates kể cả khi một bean primary, bởi request đó là “tập các beans”, không phải “một bean mặc định”.

### 4.5. Property name fallback và sự khác biệt với byName

Cơ chế candidate resolution hiện đại có thể dùng nhiều tín hiệu để phân giải single bean dependency, tùy phiên bản Spring và injection point. Không vì vậy coi `autowire="byType"` đồng nghĩa chính xác `byName`: byType xuất phát từ **kiểu của property**, không phải lookup luôn dựa trên tên property; trong trường hợp nhiều ứng viên, cần thiết kế rõ bằng primary/qualifier/explicit ref.

Đối với bài học thực hành, hãy chủ động test hai bean cùng interface thay vì đặt hy vọng vào chi tiết fallback name/parameter-name của một phiên bản Spring.

## 5. `constructor`: dependency được phân giải trước khi tạo object

Với Java class:

```java
package demo;

public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public PaymentGateway getGateway() {
        return gateway;
    }
}
```

Và XML:

```xml
<bean id="paymentGateway" class="demo.LocalPaymentGateway"/>
<bean id="checkoutService"
      class="demo.CheckoutService"
      autowire="constructor"/>
```

Spring chọn constructor thích hợp, phân giải các constructor parameters theo type-based resolution và truyền dependency khi tạo instance. Nếu class có một constructor bắt buộc nhận `PaymentGateway` và không có ứng viên phù hợp, context thường thất bại khi tạo bean.

**Sự khác biệt quan trọng:** byName/byType XML chủ yếu tác động đến **writable setters**; constructor mode tác động **constructor arguments**. Đây không phải cùng một phương thức được viết bằng hai cách gọi.

### 5.1. Constructor injection bảo đảm dependency tại creation time

Nếu `CheckoutService` chỉ có constructor `CheckoutService(PaymentGateway gateway)`, nó không thể được Spring tạo thành công mà không cung cấp gateway. Nhờ vậy dependency bắt buộc rõ trong API Java và lỗi cấu hình xuất hiện lúc container tạo bean.

Setter injection cho một field không được set có thể để null và phát hiện lỗi muộn hơn. Đây là lý do nhiều codebases hiện đại ưu tiên constructor injection cho dependencies thiết yếu, ngay cả khi XML vẫn được dùng làm configuration format.

### 5.2. Nhiều constructors và overloads

Nếu class có nhiều constructors, Spring phải chọn signature tương thích với candidates/metadata. XML `autowire="constructor"` có thể xét nhiều constructor candidates; ambiguity hoặc kiểu không chuyển được có thể dẫn đến lỗi, không phải lúc nào cũng chọn “constructor dài nhất” bất kể khả năng resolve.

Khi có overloaded constructors hoặc các types đơn giản như `String`/`int`, hãy khai báo `<constructor-arg index="..." type="..." value="..."/>` hay `ref` tường minh để tránh lệ thuộc vào thuật toán chọn constructor và parameter name metadata.

### 5.3. Constructor autowiring không tự suy ra literals

Nếu constructor `PaymentClient(String endpoint, int timeout)` thì Spring XML `autowire="constructor"` không tự đoán endpoint/timeout từ bean names hoặc sinh giá trị mặc định. Các scalar đơn giản không thuộc nhóm collaborator beans mà autowiring sẽ tự cấp tùy ý.

Ví dụ:

```xml
<bean id="client" class="demo.PaymentClient"
      autowire="constructor">
    <constructor-arg index="0" value="https://api.example.test"/>
    <constructor-arg index="1" value="2500"/>
</bean>
```

Đây là **minh họa** và cần `demo.PaymentClient` với constructor hợp lệ. Hai literal được cấp bằng explicit constructor arguments; autowiring có thể giải quyết những arguments khác nếu signature còn cần bean dependencies phù hợp.

### 5.4. Constructor injection không phải XML bean-method interception

Khác với JavaConfig `@Bean A a(B b)`, XML constructor autowiring chọn Java constructor trên target bean class. Nó không phụ thuộc `@Configuration(proxyBeanMethods=true)` hoặc CGLIB intercept các method Java cấu hình. BeanFactory vẫn quản lý scope/lifecycle theo định nghĩa XML.

## 6. Giới hạn: Spring không autowire các “simple properties”

Theo Spring Reference, cơ chế XML autowiring không tự cấp những thuộc tính đơn giản như primitive values, `String`, `Class` và mảng các simple types chỉ dựa trên tên/kiểu. Đây là chủ ý thiết kế: các giá trị cấu hình có thể mang nhiều ý nghĩa, Spring không thể suy đoán một default string/số đúng cho business logic.

Giả sử class:

```java
public class MailConfig {
    private String sender;
    private int retries;
    private MailRepository repository;

    public void setSender(String sender) { this.sender = sender; }
    public void setRetries(int retries) { this.retries = retries; }
    public void setRepository(MailRepository repository) {
        this.repository = repository;
    }
}
```

Dù XML viết `autowire="byType"`, Spring có thể tự cấp collaborator `MailRepository` nếu tìm được ứng viên phù hợp, nhưng không tự gán “sender” và “retries” chỉ nhờ nhìn property types.

Cần explicit values:

```xml
<bean id="mailConfig" class="demo.MailConfig"
      autowire="byType">
    <property name="sender" value="no-reply@example.test"/>
    <property name="retries" value="3"/>
</bean>
```

Điều tương tự áp dụng `autowire="byName"`: đừng tạo bean tên `sender` kiểu `String` rồi coi đó là mô hình config value injection ổn định, bởi Spring deliberately tránh tự wiring simple properties theo quy tắc XML autowire.

**Không nhầm:** người dùng vẫn có thể viết `<property name="sender" ref="someStringBean"/>` nếu thiết kế cố ý tham chiếu một bean object kiểu `String`; đây là **explicit ref**, khác với tự tìm bằng XML autowire.

### 6.1. `value` được chuyển kiểu theo setter/constructor

`<property name="retries" value="3"/>` chứa XML string literal. Spring conversion infrastructure chuyển nó thành `int` khi setter cần `int`. Nếu viết `value="three"`, có thể gặp type mismatch. Đó là lỗi conversion, không phải lỗi autowiring candidates.

### 6.2. Có thể có optional setter dependencies

Với setter `setAuditSink(AuditSink sink)`, XML byType có thể bỏ qua setter khi không tìm được bean `AuditSink` phù hợp. Trong code, field default null hoặc một NoOp implementation do constructor cung cấp vẫn giữ nguyên. Nếu đó là một feature optional thật, hãy biểu diễn policy rõ và kiểm thử hai trạng thái có/không provider; đừng biến dependency bắt buộc thành optional chỉ để context startup.

## 7. Explicit wiring luôn thắng autowiring

Ví dụ:

```xml
<bean id="fastGateway" class="demo.FastGateway"/>
<bean id="slowGateway" class="demo.SlowGateway"/>

<bean id="service" class="demo.CheckoutService"
      autowire="byType">
    <property name="gateway" ref="slowGateway"/>
</bean>
```

Nếu class có setter `setGateway(Gateway)`, thì explicit property value đã xác định dependency `slowGateway`; Spring **không ghi đè** nó bằng một lookup byType vì bean được đánh dấu `autowire="byType"`.

Quy tắc tương tự với explicit `<constructor-arg>` khi sử dụng constructor autowiring. Điều này rất quan trọng khi nâng cấp cấu hình XML: bạn có thể bật autowire cho phần lớn collaborators, nhưng giữ explicit wiring với dependency có vai trò đặc biệt.

### 7.1. Tại sao explicit configuration vẫn hữu ích?

- Đọc XML biết service đang dùng bean nào.
- Không bị ngầm đổi implementation khi thêm bean cùng interface.
- Có thể chỉ định một bean bị loại khỏi type-based autowiring.
- Hữu ích trong các vùng yêu cầu kiểm soát chặt như payments, transactions, security.
- Công cụ phân tích cấu hình có metadata quan hệ rõ ràng hơn.

Autowiring không thay thế giá trị của việc **tài liệu hóa dependency graph** trong cấu hình; nó chỉ giảm verbosity khi candidate resolution đơn giản và có quy ước ổn định.

## 8. `autowire-candidate="false"`: loại khỏi chọn theo kiểu, không xóa bean

Một thuộc tính ít được hiểu đúng:

```xml
<bean id="backupStore"
      class="demo.BackupStore"
      autowire-candidate="false"/>
```

Bean vẫn được đăng ký trong container và có thể được lookup bằng tên/type trong các API phù hợp. Nhưng BeanFactory **không coi bean đó là candidate cho type-based autowiring** khi tìm collaborator cho injection point.

Theo Spring Framework Reference 6.2, flag này:

- loại bean khỏi **type-based** autowire candidate resolution, bao gồm annotation injection points như `@Autowired`;
- **không cấm explicit ref theo tên**, ví dụ `<property name="store" ref="backupStore"/>`;
- **không ngăn byName autowiring** nếu property có tên trùng `backupStore`;
- không cấm chính bean `backupStore` tự sử dụng `autowire="byType"` để tìm dependencies của nó.

### 8.1. Bảng phân biệt

Giả sử bean `backupStore` có `autowire-candidate="false"`:

| Cách yêu cầu backupStore | Có thể nhận backupStore? | Giải thích |
| --- | --- | --- |
| `autowire="byType"` cho property kiểu `Store` | Không chọn bean bị loại làm candidate | Type-based resolution bỏ qua |
| `autowire="constructor"` cần `Store` | Không chọn bean bị loại làm candidate | Type-based constructor dependency |
| `autowire="byName"` cho property tên `backupStore` | Có | Name matching không bị flag này chặn |
| `<property name="store" ref="backupStore"/>` | Có | Explicit named reference |
| `context.getBean("backupStore")` | Có | Lookup trực tiếp theo tên vẫn hợp lệ |

**Điểm cần tránh:** không dùng `autowire-candidate=false` với ý định cấm truy cập bean ở mọi nơi. Nó không phải security boundary hay access-control mechanism.

### 8.2. `primary="true"` và flag candidate kết hợp

Nếu `Store A` primary nhưng `autowire-candidate=false`, nó không trở thành ứng viên cho type-based injection chỉ nhờ primary. Type-based resolver trước hết phải xét những candidates đủ điều kiện; ưu tiên primary được áp dụng trong bước lựa chọn thích hợp.

Nếu có hai candidates và một bean primary duy nhất, Spring thường có thể chọn primary. Nếu tất cả candidates của một dependency đều bị loại, byType setter có thể không được set và constructor bắt buộc có thể thất bại.

## 9. `default-autowire-candidates` trên root `<beans>`

Spring XML có thể lọc ứng viên theo **bean name patterns** ở cấp root:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       default-autowire-candidates="*Repository,core*"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository" class="demo.OrderRepository"/>
    <bean id="diagnosticRepository" class="demo.DiagnosticRepository"/>
    <bean id="billingService" class="demo.BillingService"/>
</beans>
```

Đây là XML minh họa; patterns `*Repository` và `core*` mô tả **bean names đủ điều kiện** đối với các definitions không chỉ định `autowire-candidate` riêng. Nó không ngầm quét package hoặc tạo beans mới.

**Lưu ý chính sách:** theo tài liệu Spring, một `autowire-candidate` được chỉ định **tường minh** trên chính `<bean>` có ưu tiên so với patterns mặc định. Nếu muốn cố định một bean bị loại, dùng `autowire-candidate="false"` trực tiếp trên bean definition.

`default-autowire-candidates` khác `default-autowire`:
- `default-autowire` chỉ chế độ **nối dependencies cho beans**.
- `default-autowire-candidates` chỉ nhóm beans **được xét làm type-based candidates**.

Chúng là hai hướng của một mối quan hệ DI, không phải hai cách viết thay thế nhau.

## 10. Collection, array và `Map<String,T>` trong byType/constructor mode

XML `byType` và `constructor` không chỉ biết chọn một object. Khi injection point là array/typed collection, Spring có thể tập hợp **nhiều beans cùng kiểu**:

```java
public void setHandlers(List<Handler> handlers) {
    this.handlers = handlers;
}
```

hoặc:

```java
public void setHandlers(Handler[] handlers) {
    this.handlers = handlers;
}
```

Nếu context có các `Handler` candidates phù hợp, Spring có thể inject toàn bộ vào collection/mảng. Với `Map<String, Handler>`, keys là **bean names** và values là các `Handler` instances tương ứng.

Ví dụ XML:

```xml
<bean id="emailHandler" class="demo.EmailHandler"/>
<bean id="smsHandler" class="demo.SmsHandler"/>

<bean id="pipeline" class="demo.Pipeline"
      autowire="byType"/>
```

Giả sử `Pipeline` có setter `setHandlers(List<Handler>)`, nó có thể nhận cả hai handlers khi types/generics đúng và candidates không bị lọc. Tên property không cần là `emailHandler` hay `smsHandler`.

### 10.1. Collection cần dependency element type rõ ràng

Một raw `List` hoặc raw `Map` thiếu generic type information khiến Spring khó biết beans loại nào cần tập hợp. Để tránh injection không chắc chắn, dùng `List<Handler>` hoặc `Map<String, Handler>` trong Java API.

### 10.2. Primary không bỏ bớt thành viên collection

Nếu `emailHandler` có `primary="true"`, collection `List<Handler>` vẫn có thể chứa cả email và sms; primary chủ yếu hữu ích để **chọn một dependency đơn** giữa nhiều candidates.

### 10.3. autowire-candidate filtering có hiệu lực với collection

Nếu `smsHandler` bị đánh dấu `autowire-candidate="false"`, một collection được **autowired theo type** sẽ không thu thập nó làm candidate, ngay cả khi bean vẫn tồn tại trong context. Ngược lại, một explicit `<list><ref bean="smsHandler"/></list>` vẫn có thể chứa nó.

### 10.4. Không có phần tử và các ngoại lệ

Đừng áp dụng một câu “mọi collection tự nhận list rỗng” cho mọi injection mechanism. XML setter byType, annotation constructor injection và Spring framework version có thể có quy tắc required/optional khác nhau. Nếu nghiệp vụ chấp nhận rỗng, hãy khai báo rõ contract, đặt default collection, hoặc cấp collection tường minh trong XML rồi kiểm thử hành vi thực.

### 10.5. Thứ tự list

Với collection injection, thứ tự có thể chịu ảnh hưởng `Ordered`, `@Order`, `@Priority` hoặc comparator phù hợp. Đừng dựa vào thứ tự ngẫu nhiên của component scanning hoặc bean registration để triển khai pipeline có yêu cầu thứ tự nghiệp vụ; khi thứ tự là hợp đồng, khai báo/tạo assertions rõ.

## 11. XML autowiring khác gì với `@Autowired` và `@Resource`?

Có ba lớp khái niệm cần tách:

1. **XML autowiring**: thuộc tính `autowire` trên XML `<bean>` hướng dẫn BeanFactory chọn setters/constructors theo mode `byName`/`byType`/`constructor`.
2. **`@Autowired`**: annotation-based injection, được xử lý bởi annotation infrastructure như `AutowiredAnnotationBeanPostProcessor`, có lựa chọn candidate và required semantics riêng.
3. **`@Resource`**: annotation (Jakarta) với semantics name-oriented trong các tình huống phù hợp; cần infrastructure xử lý annotation.

Các cơ chế có thể cùng tồn tại trong một context, nhưng không nên coi chúng **đồng nghĩa hoàn toàn**.

| Chủ đề | XML `autowire="byName"` | XML `autowire="byType"` | Annotation `@Autowired` |
| --- | --- | --- | --- |
| Điểm khai báo | `<bean>` definition | `<bean>` definition | Java field/constructor/method/parameter phù hợp |
| Căn cứ đầu tiên | JavaBean property name | Property type | Type-based dependency resolution |
| Thiếu ứng viên cho setter đơn | Có thể bỏ qua setter | Có thể bỏ qua setter | Mặc định `required=true` thường báo lỗi |
| Nhiều ứng viên cùng type | Name match chi phối | Cần ứng viên thắng | Qualifier/primary/name fallback và quy tắc resolver |
| Cần Spring annotations trên domain class? | Không | Không | Có |
| Cần annotation processing infrastructure? | Không cho XML autowiring thuần | Không cho XML autowiring thuần | Có |
| Dùng scalar type tự động | Không tùy tiện | Không tùy tiện | Các simple types thường cần explicit `@Value`/config mechanisms |

### 11.1. Bật `<context:annotation-config/>` có tác động gì?

Nếu một XML file có `<context:annotation-config/>` và namespace `context` được khai báo đúng, Spring sẽ đăng ký hạ tầng để xử lý các annotations trên **managed beans đã được đăng ký**. Nó không tự biến mọi class trên classpath thành bean; cần bean definitions hoặc component scanning.

Ngược lại, **XML `autowire="byType"` không bắt buộc cần `<context:annotation-config/>`**. Demo bài này không dùng annotation injection trên domain classes.

### 11.2. Cơ chế nào nên dùng trong code mới?

Constructor injection thường dễ hiểu hơn cho required dependencies. Với Java 17+ và JavaConfig, có thể dùng một constructor rõ, bean definitions từ `@Component`/`@Bean` và inject theo type/qualifier. Nếu đang bảo trì legacy Spring XML, biết autowire modes giúp đọc/di trú hệ thống chính xác; không nhất thiết phải chuyển toàn bộ XML sang annotations chỉ vì muốn giảm số dòng.

## 12. Ví dụ chạy được với Java 17+ và Spring Framework 6.2

Ví dụ này cố ý **không dùng `@Autowired` hoặc `@ComponentScan`** để phân lập hành vi XML autowiring. Mọi beans được khai báo trong một XML file.

Ta sẽ chứng minh:

- `byName` nhận bean `backupStore` theo đúng tên JavaBean property, **ngay cả khi** backup bị `autowire-candidate="false"`.
- `byType` nhận bean `mainStore` theo interface `Store` vì backup bị loại khỏi type-based candidate resolution.
- `constructor` nhận `mainStore` trước khi constructor chạy.
- Explicit `<property ref="backupStore"/>` override autowiring và vẫn trỏ được tới backup.
- `byType` có thể inject `List<Store>` từ các eligible candidates.
- Simple property `caption` phải được khai báo bằng `value`; một optional `AuditPort` không có matching bean vẫn để null.

Mỗi bean trong example dùng singleton scope mặc định.

### 12.1. Cấu trúc dự án

```text
xml-autowiring-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlAutowiringDemo.java
        └── resources/
            └── autowire-context.xml
```

File `settings.gradle`:

```groovy
rootProject.name = 'xml-autowiring-demo'
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
    mainClass = 'demo.XmlAutowiringDemo'
}
```

Dùng JDK 17+ và bản Gradle tương thích. `spring-context` kéo theo `spring-beans`/`spring-core`; không cần Spring Boot, server hay database. Example chọn một file Java có các **public static nested classes** để tránh quá nhiều files, nên tên class dùng trong XML sẽ chứa ký tự `$` theo Java binary naming rules.

### 12.2. Mã Java hoàn chỉnh

Tạo `src/main/java/demo/XmlAutowiringDemo.java`:

```java
package demo;

import java.util.List;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class XmlAutowiringDemo {

    public interface Store {
        String label();
    }

    public record MainStore() implements Store {
        @Override
        public String label() {
            return "main";
        }
    }

    public record BackupStore() implements Store {
        @Override
        public String label() {
            return "backup";
        }
    }

    public interface AuditPort {
        String audit();
    }

    public static class ByNameConsumer {
        private Store backupStore;

        public void setBackupStore(Store backupStore) {
            this.backupStore = backupStore;
        }

        public Store getBackupStore() {
            return backupStore;
        }
    }

    public static class ByTypeConsumer {
        private Store selected;

        public void setSelected(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class ConstructorConsumer {
        private final Store selected;

        public ConstructorConsumer(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class ExplicitConsumer {
        private Store selected;

        public void setSelected(Store selected) {
            this.selected = selected;
        }

        public Store getSelected() {
            return selected;
        }
    }

    public static class FleetConsumer {
        private List<Store> stores = List.of();

        public void setStores(List<Store> stores) {
            this.stores = stores;
        }

        public List<Store> getStores() {
            return stores;
        }
    }

    public static class SettingsConsumer {
        private String caption = "unset";
        private AuditPort auditPort;

        public void setCaption(String caption) {
            this.caption = caption;
        }

        public void setAuditPort(AuditPort auditPort) {
            this.auditPort = auditPort;
        }

        public String getCaption() {
            return caption;
        }

        public AuditPort getAuditPort() {
            return auditPort;
        }
    }

    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext(
                "autowire-context.xml")) {

            Store main = context.getBean("mainStore", Store.class);
            Store backup = context.getBean("backupStore", Store.class);

            ByNameConsumer byName =
                    context.getBean(ByNameConsumer.class);
            ByTypeConsumer byType =
                    context.getBean(ByTypeConsumer.class);
            ConstructorConsumer constructor =
                    context.getBean(ConstructorConsumer.class);
            ExplicitConsumer explicit =
                    context.getBean(ExplicitConsumer.class);
            FleetConsumer fleet =
                    context.getBean(FleetConsumer.class);
            SettingsConsumer settings =
                    context.getBean(SettingsConsumer.class);

            System.out.println("byName = " +
                    byName.getBackupStore().label());
            System.out.println("byType = " +
                    byType.getSelected().label());
            System.out.println("constructor = " +
                    constructor.getSelected().label());
            System.out.println("explicit = " +
                    explicit.getSelected().label());
            System.out.println("byNameSameBackup = " +
                    (byName.getBackupStore() == backup));
            System.out.println("byTypeSameMain = " +
                    (byType.getSelected() == main));
            System.out.println("explicitSameBackup = " +
                    (explicit.getSelected() == backup));
            System.out.println("fleet = " +
                    fleet.getStores().stream()
                         .map(Store::label).toList());
            System.out.println("caption = " +
                    settings.getCaption());
            System.out.println("missingAudit = " +
                    (settings.getAuditPort() == null));
        }
    }
}
```

Mã Java trên có đúng một top-level public class. Hai records `MainStore`/`BackupStore` là nested types implement interface `Store`; chúng có no-arg canonical constructors vì records không khai báo components. Những consumer classes có setter hoặc constructor tương ứng để BeanFactory thực hiện đúng mode.

### 12.3. XML bean definitions đầy đủ

Tạo `src/main/resources/autowire-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="mainStore"
          class="demo.XmlAutowiringDemo$MainStore"/>

    <bean id="backupStore"
          class="demo.XmlAutowiringDemo$BackupStore"
          autowire-candidate="false"/>

    <bean id="byName"
          class="demo.XmlAutowiringDemo$ByNameConsumer"
          autowire="byName"/>

    <bean id="byType"
          class="demo.XmlAutowiringDemo$ByTypeConsumer"
          autowire="byType"/>

    <bean id="constructor"
          class="demo.XmlAutowiringDemo$ConstructorConsumer"
          autowire="constructor"/>

    <bean id="explicit"
          class="demo.XmlAutowiringDemo$ExplicitConsumer"
          autowire="byType">
        <property name="selected" ref="backupStore"/>
    </bean>

    <bean id="fleet"
          class="demo.XmlAutowiringDemo$FleetConsumer"
          autowire="byType"/>

    <bean id="settings"
          class="demo.XmlAutowiringDemo$SettingsConsumer"
          autowire="byType">
        <property name="caption" value="XML-configured"/>
    </bean>
</beans>
```

Lưu ý các tên class có `$`: đó là **Java binary names của nested classes**, không phải lỗi đánh máy. Nếu refactor thành top-level classes, tên XML phải thay bằng tên fully qualified mới.

### 12.4. Lệnh chạy và stdout

Trong thư mục dự án:

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

**Các dòng do chương trình in ra:**

```text
byName = backup
byType = main
constructor = main
explicit = backup
byNameSameBackup = true
byTypeSameMain = true
explicitSameBackup = true
fleet = [main]
caption = XML-configured
missingAudit = true
```

Đây là stdout nghiệp vụ từ `System.out.println`. Tùy cấu hình Gradle/logging, môi trường có thể in thêm messages không thuộc các dòng trên.

### 12.5. Phân tích từng kết quả

**`byName = backup`:** `ByNameConsumer` có writable property `backupStore` thông qua `setBackupStore(Store)`, nên byName tìm đúng bean tên `backupStore`. Thuộc tính `autowire-candidate="false"` không ngăn name-based wiring, theo Spring documentation.

**`byType = main`:** `ByTypeConsumer` cần một `Store` trong setter `setSelected(Store)`. `mainStore` là eligible candidate; `backupStore` bị loại khỏi type-based autowiring, nên Spring chọn main.

**`constructor = main`:** `ConstructorConsumer(Store selected)` nhận Store từ constructor autowiring. Dù backup vẫn tồn tại trong registry, nó không phải candidate kiểu Store cho injection point này.

**`explicit = backup`:** `ExplicitConsumer` được đặt `autowire="byType"` nhưng XML đồng thời khai báo `<property name="selected" ref="backupStore"/>`. Explicit ref có ưu tiên; dù backup excluded from type-based autowiring, vẫn lookup theo tên và inject thành công.

**Ba dòng `Same... = true`:** identity `==` chứng minh cùng những managed singleton references, không phải copy object mới từ tên/kiểu. Bean scopes mặc định singleton và mỗi context chỉ có một `MainStore`, một `BackupStore`.

**`fleet = [main]`:** setter `setStores(List<Store>)` nhận các Store candidates phù hợp. Vì backup bị loại khỏi type-based candidate selection, list có một phần tử main. Không liên quan tới property name `stores`.

**`caption = XML-configured`:** property đơn giản kiểu `String` được cấp bằng explicit `<property value="..."/>`, không phải byType tự tìm String bean.

**`missingAudit = true`:** không có bean `AuditPort`, nên byType setter dành cho optional-looking property `auditPort` không được gọi; field vẫn null. Nếu ứng dụng thật không chấp nhận null, cần sửa contract và wiring cho chắc chắn.

### 12.6. Biến thể 1: hai candidates và ambiguity

Thay XML `backupStore` để bỏ `autowire-candidate="false"`, rồi giữ `byType` và `constructor` như cũ:

```xml
<bean id="mainStore"
      class="demo.XmlAutowiringDemo$MainStore"/>
<bean id="backupStore"
      class="demo.XmlAutowiringDemo$BackupStore"/>
<bean id="byType"
      class="demo.XmlAutowiringDemo$ByTypeConsumer"
      autowire="byType"/>
```

Đây là **fragment cho bài thử** (không phải file hoàn chỉnh). Trong tình huống hai eligible beans cùng `Store` mà không có lựa chọn thắng, tạo `byType` có thể thất bại với ambiguity. Tình huống này nên được chạy trong **XML test riêng**, không sửa trực tiếp demo chính nếu muốn giữ stdout ở mục 12.4.

### 12.7. Biến thể 2: đặt primary

Nếu cả hai Store được phép làm candidates, bạn có thể:

```xml
<bean id="mainStore"
      class="demo.XmlAutowiringDemo$MainStore"
      primary="true"/>

<bean id="backupStore"
      class="demo.XmlAutowiringDemo$BackupStore"/>
```

Trong dependency đơn theo type, Spring có thể chọn `mainStore` là primary duy nhất. Tuy nhiên, nếu cần collection `List<Store>`, thông thường cả hai candidates vẫn là phần tử của collection (primary không lọc backup ra khỏi list).

### 12.8. Biến thể 3: byName thiếu tên tương ứng

Đổi bean `backupStore` thành `spareStore` nhưng giữ setter `setBackupStore(Store)`. Khi không có alias `backupStore` và không có explicit property, byName không tìm thấy tên tương ứng nên field có thể giữ null. Ngược lại, byType không quan tâm tên `spareStore` nếu kiểu và candidate status đúng.

### 12.9. Biến thể 4: explicit wiring vẫn hoạt động

Giữ `autowire-candidate="false"` của backup, nhưng trong một bean khác khai báo `<property name="selected" ref="backupStore"/>`. Reference đó vẫn hợp lệ, vì flag không hủy quyền lookup trực tiếp theo tên.

### 12.10. Biến thể 5: loại cả mainStore

Đặt thêm `autowire-candidate="false"` lên `mainStore`. Lúc này byType setter `selected` có thể không được cấp, nhưng `constructor` cần Store bắt buộc có thể làm context fail khi Spring cố tạo bean. Thử nghiệm này giúp thấy khác biệt về required semantics giữa setter byType và constructor.

## 13. Lỗi thường gặp và cách xử lý

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Setter byName không chạy | Không có bean name trùng property name | Kiểm tra setter và `id`/`alias`; dùng explicit ref nếu cần |
| byType gặp hai implementations | Nhiều eligible candidates và không có một ứng viên thắng | `primary`, candidate filtering, qualifier/explicit ref |
| Constructor fails khi dependency thiếu | Constructor argument bắt buộc không resolve được | Đăng ký bean phù hợp hoặc explicit constructor-arg |
| Bean bị excluded mà byName vẫn nhận | `autowire-candidate=false` chỉ ảnh hưởng type-based selection | Đây là behavior thiết kế; cần kiểm soát byName riêng |
| Explicit ref vẫn lấy bean excluded | Explicit named reference không bị flag chặn | Đây là behavior hợp lệ, không phải lỗi |
| `value="3"` không tự inject bằng byType | Scalar simple property không thuộc XML autowiring | Dùng `<property value>`/`<constructor-arg value>` |
| `NotWritablePropertyException` | Không có setter JavaBean đúng tên/signature | Kiểm tra property descriptor/setter visibility |
| `TypeMismatchException` | Bean/giá trị không phù hợp setter type | Kiểm tra class/interface và converters |
| `NoUniqueBeanDefinitionException` | Resolver không chọn được single candidate | Loại ambiguity có chủ đích |
| `NoSuchBeanDefinitionException` | Dependency bean chưa đăng ký/đã bị lọc | Kiểm tra imports, profiles, conditions, XML resources |
| Autowiring không làm field private được set | XML setter mode không giống annotation field injection | Tạo setter/constructor injection phù hợp |
| Cùng một property vừa explicit vừa autowire | Explicit metadata có ưu tiên | Xác định một nơi cấu hình chịu trách nhiệm |
| Collection bỏ mất implementation | Bean đó bị loại bởi `autowire-candidate`/patterns | Kiểm tra candidate flags |
| Đổi XML sau context refresh không cập nhật bean | Autowiring xảy ra lúc bean creation | Cần reload/rebuild hoặc cơ chế runtime config riêng |
| Property type là raw `List` | Spring không biết rõ element type | Dùng `List<Interface>` hoặc explicit collection |
| byName phụ thuộc tên setter, không phụ thuộc field | JavaBeans property naming | Kiểm tra `setXxx` và introspection |
| Mọi bean đều autowired ngoài ý muốn | `default-autowire` ở root không được quản lý | Giữ default `no` hoặc review scope cấu hình |
| Bean có `autowire="no"` vẫn được inject vào bean khác | Không cấm nó làm candidate | Nếu cần loại by-type selection, dùng `autowire-candidate=false` |
| Bean primary vẫn bị excluded | Không là candidate trước bước primary preference | Đừng dùng primary để vượt flag excluded |
| Spring AOP proxy và raw bean khác identity | Container có post-processors/proxying | So sánh references theo lifecycle/proxy policy phù hợp |

### 13.1. Phân loại lỗi theo giai đoạn

Lỗi Spring XML có thể xảy ra ở ba giai đoạn lớn:

1. **XML parse/XSD:** sai `autowire` attribute, sai namespace URI, thẻ không đóng, XSD không resolve.
2. **Bean definition / candidate resolution:** không có candidates, nhiều candidates, property không writable, constructor không phân giải được.
3. **Bean creation / business runtime:** constructor ném exception, setter logic lỗi, field null vì optional autowire bị bỏ qua, bean chạy vào method sử dụng dependency chưa có.

Đừng nhìn thấy `BeanCreationException` là lập tức kết luận “Spring không đọc XML”. Nó có thể đã đọc XML rất tốt, nhưng không thể giải quyết dependency hoặc class logic bị lỗi sau đó.

### 13.2. Kỹ thuật debug

**Bước 1:** Kiểm tra application context thực sự load file `autowire-context.xml` nào. Nhiều file cùng tên trên classpath có thể gây nhầm.

**Bước 2:** Xem bean name và implementation type đang tồn tại. `context.getBeanNamesForType(Store.class)` có thể giúp thấy beans theo type, nhưng lưu ý **truy vấn type names không đồng nhất với lựa chọn autowire candidates**: một excluded bean có thể vẫn tồn tại và được liệt kê.

**Bước 3:** Kiểm tra property name từ `setXxx` và kiểu parameter. Với `byName`, tên rất quan trọng; với `byType`, type và eligible candidates quan trọng.

**Bước 4:** Kiểm tra `primary`, `autowire-candidate`, `default-autowire-candidates` và những `<property ref>` explicit.

**Bước 5:** Nếu dependency bắt buộc, hãy viết một integration test assert rằng field/constructor dependency không null và đúng implementation — thay vì chỉ nhìn context refresh không lỗi.

**Bước 6:** Xem root cause của stack trace. Ambiguity, missing bean, missing setter, bad type conversion và cycle là những nguyên nhân khác nhau.

### 13.3. Bean name và type tự định nghĩa khác nhau

Một bean XML có thể được đặt tên `legacyJdbcStore` và class implement `Store`. Nếu setter tên `setStore`:

- byName tìm `store`, không tự tìm `legacyJdbcStore`;
- byType có thể chọn `legacyJdbcStore` nếu là candidate theo `Store`.

Một thay đổi bean name có thể phá byName nhưng không phá byType; thay đổi implementation type có thể phá byType nhưng không phá name matching (sau đó có thể vấp type compatibility). Đây là trade-off cần cân nhắc khi chọn mode.

## 14. Hạn chế thiết kế và chiến lược dùng thực tế

### 14.1. Giảm cấu hình có đánh đổi

Autowiring làm XML ngắn hơn, nhưng quan hệ giữa beans không còn xuất hiện tường minh ở nơi đọc config. Người review phải biết setter/constructor API và cả registry candidates mới suy luận được dependency thực.

Khi project phát triển thêm một bean cùng interface, một byType dependency từng unique có thể trở thành ambiguous hoặc chọn implementation khác do primary/candidate changes. Với hệ thống cần behavior dự đoán cao, cấu hình explicit giúp giảm bất ngờ.

### 14.2. Không trộn mode tùy tiện

Một module dùng explicit `ref`, module khác dùng byName, module thứ ba dùng byType là hợp lệ về mặt Spring, nhưng không có coding conventions rõ thì dễ gây nhầm. Có thể chọn:

- Constructor injection cho dependencies không thể thiếu.
- Explicit XML references cho collaborators có nhiều implementations.
- byType cho các utility beans có candidate duy nhất và ranh giới đã được test.
- byName khi naming convention cố định/ổn định.
- Explicit values/config properties cho strings, numbers và secrets.

Đây là gợi ý, không phải luật bắt buộc. Ưu tiên tính minh bạch và integration tests.

### 14.3. Type-based injection không phải an ninh

`autowire-candidate=false` giúp lọc dependency resolution; nó không ngăn một bean khác chủ động lấy object bằng `context.getBean("backupStore")`, cũng không ngăn bean được khai báo explicit `ref`. Nếu đối tượng nhạy cảm, cần kiểm soát quyền/cấu trúc module, không chỉ candidate flags.

### 14.4. Cần phân biệt startup với runtime

Một dependency setter được Spring inject khi bean được tạo. Nếu bạn đăng ký thêm một bean `Store` sau khi context đã refresh, singleton `ByTypeConsumer` không tự chọn lại candidate hay gọi lại setter. Muốn runtime routing, thiết kế một abstraction/provider/factory riêng, không dùng XML autowiring như một bộ định tuyến động.

### 14.5. Không dùng XML autowiring làm lời giải cho circular dependencies

Setter cycles đôi khi có thể được Spring giải quyết trong một số singleton configurations, nhưng chúng mang rủi ro lifecycle, proxy, state partially initialized. Constructor cycles thường không thể giải quyết bằng autowiring thông thường. Hãy refactor dependency graph có chiều rõ ràng, dùng events hoặc chia service responsibilities.

### 14.6. Không đồng nhất candidate selection giữa Spring versions

Spring có những cải tiến thuật toán resolve nhiều ứng viên qua các phiên bản (ví dụ Spring 6.2 xử lý thêm trường hợp qualifier/name/priority). Cần kiểm tra **phiên bản framework thực tế** thay vì dựa vào một blog dùng Spring 2.x. Tài liệu bài này đối chiếu Spring Framework 6.2.19; các hành vi cụ thể vẫn nên có integration tests trong dự án của bạn.

## 15. Kiểm thử XML autowiring có chủ đích

### 15.1. Happy-path identity tests

Đối với demo ở mục 12, có thể bổ sung assertions:

```java
if (byName.getBackupStore() != backup) {
    throw new AssertionError("byName did not select backup");
}

if (byType.getSelected() != main) {
    throw new AssertionError("byType did not select main");
}

if (explicit.getSelected() != backup) {
    throw new AssertionError("Explicit ref was not honored");
}

if (fleet.getStores().size() != 1) {
    throw new AssertionError("Expected one eligible Store");
}
```

Đây là **trích đoạn test** dùng các biến đã khai báo trong `XmlAutowiringDemo.main`. Test giúp bảo vệ assumptions về type/name/candidate status khi XML được chỉnh sửa.

### 15.2. Negative test cho ambiguity

Có thể dùng một XML fixture riêng chứa hai eligible `Store` beans và một `ByTypeConsumer`. Khi chạy:

```java
try (var context = new ClassPathXmlApplicationContext(
        "ambiguous-context.xml")) {
    throw new AssertionError("Expected ambiguity");
} catch (org.springframework.beans.BeansException expected) {
    System.out.println("Ambiguous configuration rejected");
}
```

Đây là **trích đoạn test**, không phải phần `main` của demo; cần resource `ambiguous-context.xml` riêng. Trong test nghiêm túc, kiểm tra đúng type/root cause của exception để không lầm một lỗi XML parse với lỗi ambiguity. Không nên chỉ catch mọi exception rồi coi test đạt.

### 15.3. Missing dependency test

Với `byType` setter, nếu không có `Store`, test nên kiểm tra getter còn null theo contract; với constructor dependency bắt buộc, test nên kỳ vọng failure. Phân biệt kết quả hai modes là trọng tâm.

### 15.4. Test candidate exclusion

Với bean `backupStore` excluded:
- `context.containsBean("backupStore")` phải đúng.
- `context.getBean("backupStore", Store.class)` vẫn hoạt động.
- byName property `backupStore` nhận object đó.
- byType dependency Store nhận main.
- explicit ref tới backup vẫn hoạt động.

Nếu cả năm assertions cùng đạt, bạn đã kiểm tra đúng sự khác nhau giữa **tồn tại trong registry** và **đủ điều kiện để autowire theo type**.

## 16. Bài tập có lời giải

### Bài 1 — byName dùng tên gì?

Class có field `primaryRepository` và setter `setRepository(Repository)`. XML bật `autowire="byName"`. Spring tìm bean tên nào?

**Đáp án:** `repository`, theo writable JavaBean property name. Field name không trực tiếp điều khiển byName.

### Bài 2 — byType có cần bean name giống setter?

Setter `setStore(Store)`, registry có một bean `jdbcMain` implement `Store`. XML `autowire="byType"` có thể inject nó không?

**Đáp án:** Có, khi đó là eligible candidate duy nhất/phù hợp. Tên `jdbcMain` không cần trùng `store`.

### Bài 3 — byName không có bean name tương ứng

Setter `setNotifier(Notifier)`, XML chỉ có bean tên `smsNotifier`. Với `byName`, setter có chắc được gọi không?

**Đáp án:** Không. Không có bean tên `notifier` thì byName có thể bỏ qua property; dùng alias/explicit ref hoặc đổi mode khi hợp lý.

### Bài 4 — byType có hai candidates

Có hai eligible `PaymentGateway` beans và không có ứng viên thắng rõ. Điều gì có thể xảy ra?

**Đáp án:** Ambiguous dependency; Spring có thể ném exception khi tạo bean. Không chọn ngẫu nhiên theo thứ tự XML.

### Bài 5 — primary

Hai `Store` candidates, một bean có `primary="true"` duy nhất. Với dependency đơn kiểu `Store`, Spring có thể chọn bean nào?

**Đáp án:** Bean primary nếu hợp lệ trong tập candidates; primary không làm bean khác biến mất khỏi registry.

### Bài 6 — candidate false

Bean `backupStore` có `autowire-candidate="false"`. Một property byName tên `backupStore` có thể vẫn được inject không?

**Đáp án:** Có. Flag này giới hạn type-based autowiring, không chặn byName match.

### Bài 7 — explicit ref tới excluded bean

`backupStore` bị loại khỏi type-based autowiring. `<property name="store" ref="backupStore"/>` có còn hợp lệ không?

**Đáp án:** Có. Explicit reference theo tên không bị candidate flag vô hiệu hóa.

### Bài 8 — simple property

Bean `Settings` có `setTimeout(int)`. Root XML đặt `default-autowire="byType"`. Timeout có tự nhận giá trị 3000 không?

**Đáp án:** Không. Simple property không được tự suy đoán. Cần explicit `<property name="timeout" value="3000"/>` hoặc cơ chế config rõ ràng.

### Bài 9 — constructor dependency thiếu

`CheckoutService(Store store)` chỉ có một constructor, XML dùng `autowire="constructor"` nhưng không có Store bean. Context có chắc tạo service với store null không?

**Đáp án:** Không. Constructor dependency bắt buộc không resolve được thường khiến bean creation thất bại.

### Bài 10 — explicit property và autowire

Bean `service` vừa có `autowire="byType"` vừa có `<property name="gateway" ref="backupGateway"/>`. Khi Spring tạo bean, có được tự thay backup bằng primary Gateway khác không?

**Đáp án:** Không. Explicit property setting override autowiring cho property đó.

### Bài 11 — List<Handler>

Có ba eligible bean `Handler`. Injection point là `List<Handler>` qua byType. Có nhất thiết chỉ chọn một `@Primary` không?

**Đáp án:** Không. Collection có thể chứa cả ba eligible handlers; primary không lọc collection.

### Bài 12 — Map<String,Handler>

Vì sao Spring dùng `String` keys trong autowired map?

**Đáp án:** Keys biểu diễn **bean names**, values là các handler bean references. Cần generic types rõ để resolver biết element type.

### Bài 13 — Candidate false có hủy bean không?

Bạn gọi `context.getBean("backupStore")` trên excluded backup bean. Có bắt buộc lỗi `NoSuchBeanDefinitionException` không?

**Đáp án:** Không. Bean definition vẫn tồn tại; flag không phải cơ chế xóa bean hay security control.

### Bài 14 — default-autowire-candidates

Root `<beans default-autowire-candidates="*Repository">` có nghĩa chỉ những bean có tên kết thúc `Repository` mới được đăng ký trong context không?

**Đáp án:** Không. Nó giới hạn **candidate selection** theo pattern cho type-based autowiring, không chặn registration của bean khác.

### Bài 15 — annotation và XML

Một bean `autowire="no"` nhưng class có `@Autowired` và infrastructure xử lý annotation đã bật. Có thể được annotation injection không?

**Đáp án:** Có. `autowire=no` tắt XML autowire mode, không tự cấm annotation BeanPostProcessor.

### Bài 16 — thời điểm cấp bean

Bạn thay XML file lúc ứng dụng đã refresh context và đang giữ singleton `service`. Setter `setStore` có tự được chạy lại không?

**Đáp án:** Không. Autowiring thông thường diễn ra trong quá trình bean creation/population; muốn reload phải có cơ chế riêng.

### Bài 17 — scope prototype

Một singleton Service nhận một prototype Store vào setter khi nó được tạo. Mỗi lần `service.find()` có tự nhận Store mới không?

**Đáp án:** Không. Service giữ reference đã inject; muốn lookup mới theo mỗi lần dùng, cần provider/factory phù hợp.

### Bài 18 — vì sao ưu tiên constructor injection?

Một Service không thể chạy đúng nếu thiếu Repository, nhưng setter byType có thể để repository null khi thiếu candidate. Cách cải thiện?

**Đáp án:** Khai báo dependency qua constructor bắt buộc, hoặc explicit XML reference và kiểm thử/init validation. Điều quan trọng là contract “repository bắt buộc” được bảo đảm trước khi service sử dụng.

## 17. Checklist áp dụng vào dự án thật

- Bean cần autowire đang dùng đúng `autowire` mode chưa?
- Với `byName`, đã xác nhận JavaBeans property name và bean `id`/`alias` chính xác chưa?
- Với `byType`, đã xác nhận số lượng eligible candidates, types, `primary` và candidate flags chưa?
- Với `constructor`, đã xem constructor signatures, arguments scalar và overloads chưa?
- Simple `String`/`int`/`boolean` properties có explicit values không?
- Những dependency đặc biệt cần một implementation cụ thể đã dùng `ref`/`constructor-arg` tường minh chưa?
- Có bean nào `autowire-candidate=false` nhưng vẫn được byName/explicit ref lấy theo thiết kế không?
- `default-autowire` và `default-autowire-candidates` có bị nhầm không?
- Với collection injection, generic element type và tập eligible beans có đúng không?
- Bean mới được thêm có làm một byType dependency trước đó trở thành ambiguous không?
- Một setter dependency bắt buộc bị thiếu có thể khiến field null muộn không?
- Test context có assert bean identity, implementation type và behavior chưa?
- Nếu XML có `<context:annotation-config/>`, có hiểu annotation injection khác XML autowiring không?
- Scopes/proxies/lazy/circular references có làm khác đi thời điểm resolve dependency không?
- Khi debug, đã đọc root cause thay vì gộp mọi exception thành “XML lỗi” chưa?

## 18. Kết luận

**Autowiring XML** cho phép BeanFactory tìm collaborators từ bean registry thay vì yêu cầu tất cả `<property ref="..."/>` xuất hiện tường minh. `byName` khớp **JavaBean property name với bean name**. `byType` khớp **property type với autowire candidate beans**. `constructor` giải quyết **constructor arguments theo type-based dependency resolution**. `no` là mặc định và không cấm explicit DI.

Giới hạn lớn nhất: **simple properties không được tự đoán**; missing byType setter candidate có thể để property trống; nhiều eligible beans cho dependency đơn có thể gây ambiguity; và wiring ngầm làm dependency graph khó nhìn hơn. Spring cung cấp `primary`, `autowire-candidate` và `default-autowire-candidates` để tinh chỉnh selection, nhưng **explicit ref luôn giúp chỉ ra dependency cụ thể**.

Một quy tắc rất đáng nhớ: **`autowire-candidate="false"` không xóa bean, không chặn byName và không chặn explicit ref**; nó chủ yếu loại bean khỏi type-based autowiring. Bài demo kiểm chứng đồng thời cả ba đường resolve đó.

Trong code mới, constructor injection cho dependencies bắt buộc và cấu hình tường minh cho những lựa chọn nghiệp vụ quan trọng thường cho kết quả dễ bảo trì hơn. Khi duy trì hệ thống Spring XML, hiểu chính xác từng autowire mode sẽ giúp tránh những lỗi chỉ xuất hiện khi có thêm một bean cùng interface, khi thay bean name hoặc khi thay candidate-selection rules.

### Tài liệu chính thức

- [Spring Framework 6.2 — Autowiring Collaborators](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html).
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html).
- [Spring Framework 6.2 — Using `@Autowired`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired.html).
- [Spring Framework 6.2 — Spring Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).
- [Spring Framework 6.2 — Fine-tuning Annotation-based Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html).
