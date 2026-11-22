# Kế thừa nhóm kiểm tra (Group Inheritance) trong Jakarta Bean Validation và Spring

## 1. Bản chất: một group con bao gồm các constraint của group cha

Trong Jakarta Bean Validation, **validation group** là một interface Java dùng để lựa chọn tập ràng buộc sẽ được kiểm tra khi gọi `jakarta.validation.Validator.validate(...)` hoặc tại các điểm tích hợp của Spring như `@Validated(...)`. Một constraint có thể thuộc `Default` hoặc một/nhiều nhóm do ứng dụng định nghĩa.

**Kế thừa nhóm kiểm tra (group inheritance)** có nghĩa là: nếu interface group `Child` **`extends Parent`**, khi yêu cầu validate nhóm `Child`, provider cũng đánh giá các constraint thuộc `Parent`. Group con là một **tập mở rộng** của group cha; chiều kế thừa không đảo ngược.

```java
public interface BasicChecks {}
public interface BusinessChecks extends BasicChecks {}
```

Với:

```java
@NotBlank(groups = BasicChecks.class)
private String name;

@Positive(groups = BusinessChecks.class)
private Integer quantity;
```

thì:

- `validator.validate(bean, BasicChecks.class)` chọn constraint trên `name`, **không** tự thêm constraint của `BusinessChecks`.
- `validator.validate(bean, BusinessChecks.class)` chọn cả `name` (kế thừa `BasicChecks`) và `quantity` (khai báo trực tiếp thuộc `BusinessChecks`).
- `validator.validate(bean)` mặc định chọn `jakarta.validation.groups.Default`; không mặc nhiên chọn `BasicChecks` hay `BusinessChecks` nếu chúng không liên quan tới `Default` qua quan hệ nhóm hoặc quy tắc khác.

Các interface group không cần có method, field hay annotation đặc biệt; **Java interface inheritance** chính là cú pháp mà Jakarta Validation dùng để diễn đạt quan hệ giữa các tập constraint.

> **Nhớ nhanh:** validate group con = kiểm tra constraint của chính group con **và** tất cả group cha (trực tiếp, gián tiếp); validate group cha không tự chạy constraint chỉ có ở group con.

## 2. Phân biệt group, constraint và lượt validation

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| Constraint | Mô tả quy tắc dữ liệu | `@NotBlank`, `@Positive`, `@Email` |
| Group | Gắn nhãn tập constraint | `BasicChecks.class` |
| Group inheritance | Mở rộng tập constraint qua interface `extends` | `FullChecks extends BasicChecks` |
| Target group | Group người gọi muốn kiểm tra | `validator.validate(bean, FullChecks.class)` |
| Default group | Nhóm khi annotation hoặc lời gọi không chỉ rõ group | `jakarta.validation.groups.Default` |
| Group sequence | Quy định **thứ tự** và dừng ở nhóm đầu có vi phạm | `@GroupSequence({Default.class, FullChecks.class})` |
| Cascaded validation | Kiểm tra object con qua `@Valid` | `@Valid Address address` |
| Group conversion | Đổi group khi đi qua đường cascade | `@ConvertGroup(from=..., to=...)` |

Một annotation constraint có thuộc tính `groups` kiểu `Class<?>[]`:

```java
@NotBlank(groups = BasicChecks.class)
private String username;

@NotNull(groups = {BasicChecks.class, CreateChecks.class})
private String email;
```

Một constraint có thể thuộc **nhiều group**. Nếu yêu cầu nhiều nhóm cùng lúc, cùng một khai báo constraint không cần bị báo lỗi hai lần trong một lượt validation; provider có cơ chế tránh đánh giá lặp cùng constraint/path theo hợp đồng của đặc tả.

**Có metadata không đồng nghĩa đã chạy validation**: phải gọi `Validator.validate(...)`, Spring `SmartValidator` hoặc một integration point MVC/service được cấu hình. Interface group không phải đối tượng được tạo bằng `new`; nó là metadata nhóm được provider chọn tại thời điểm thực thi.

## 3. Kế thừa đơn, kế thừa nhiều nhóm và kế thừa bắc cầu

### Một cha

```java
public interface Basic {}
public interface Submit extends Basic {}
```

`Submit` bao gồm constraint của `Submit` và `Basic`.

### Nhiều cha

```java
public interface IdentityChecks {}
public interface PaymentChecks {}
public interface PurchaseChecks extends IdentityChecks, PaymentChecks {}
```

`PurchaseChecks` là tập hợp của ba nhóm: `IdentityChecks`, `PaymentChecks` và chính `PurchaseChecks`. Nếu một constraint được khai báo `groups = {IdentityChecks.class, PaymentChecks.class}`, nó có thể phù hợp qua hai nhánh nhưng không nên được tính thành hai vi phạm giống nhau chỉ vì có hai đường kế thừa.

### Bắc cầu

```java
public interface Basic {}
public interface Shipping extends Basic {}
public interface Checkout extends Shipping {}
```

Khi validate `Checkout`, provider áp dụng constraint của `Checkout`, `Shipping`, `Basic`. Đây là **quan hệ transitive** của interface inheritance, không cần khai báo lại mỗi group ở lớp cháu.

### Một hình dung trực quan

```text
      Basic
        ^
        |
     Shipping        Payment
        ^               ^
        |               |
        +-------+-------+
                |
             Checkout

validate(Basic)     -> Basic
validate(Shipping)  -> Shipping + Basic
validate(Payment)   -> Payment
validate(Checkout)  -> Checkout + Shipping + Basic + Payment
```

Trong ví dụ này, mũi tên hướng về group cha; group nằm dưới **bao gồm** các ràng buộc của group nằm phía trên.

**Không phụ thuộc thứ tự các interface sau `extends`**. `Checkout extends Shipping, Payment` chỉ xác định tập nhóm, **không** có nghĩa các constraint Shipping bắt buộc chạy trước Payment. Để có thứ tự, cần cơ chế `@GroupSequence`.

## 4. `Default` có được kế thừa tự động không?

**Không phải mọi group do bạn định nghĩa đều bao gồm `Default`.** Đây là nhầm lẫn rất phổ biến.

```java
public interface Advanced {}
```

`Advanced` không kế thừa `jakarta.validation.groups.Default`. Nếu DTO có:

```java
@NotBlank
private String title; // Default

@Positive(groups = Advanced.class)
private Integer number; // Advanced
```

thì yêu cầu `validate(bean, Advanced.class)` không tự lấy constraint mặc định trên `title` chỉ vì `Advanced` có tên "advanced".

Nếu muốn một group con **bao gồm Default**, khai báo minh bạch:

```java
import jakarta.validation.groups.Default;

public interface Basic {}
public interface Complete extends Default, Basic {}
```

Khi validate `Complete`, provider chọn constraint thuộc `Complete`, `Default` và `Basic`. Đây là cách đơn giản để mô tả "kiểm tra đầy đủ cả điều kiện mặc định và điều kiện chuyên biệt" mà **không cần** dùng group sequence.

Các quy tắc mặc định cần nhớ:

1. Khi constraint không đặt thuộc tính `groups`, nó thuộc `Default`.
2. Khi `validator.validate(object)` không truyền groups, group được yêu cầu là `Default`.
3. Khi truyền `validator.validate(object, SomeGroup.class)`, chỉ các group được yêu cầu và nhóm cha/kế thừa của chúng được xét, kèm các quy tắc đặc biệt nếu có sequence/cascade.
4. Group `SomeGroup` không tự bao gồm `Default`, trừ khi **extends Default** hoặc logic khai báo khác làm `Default` được chọn.

Đừng nhầm `@NotBlank(groups = Default.class)` với `@NotBlank`: về mặt nhóm, chúng tương đương theo chuẩn. Tuy nhiên, khi một class định nghĩa lại default group sequence, việc kiểm tra group mặc định còn có quy tắc riêng của class đó, được phân biệt ở phần sau.

## 5. Ví dụ chạy được: kiểm chứng kế thừa nhóm với Java 17 và Spring Boot

Chương trình dưới đây chủ động đặt **một constraint sai dữ liệu ở mỗi group** để thấy rõ các tập kết quả. Nó cũng minh họa `Default` có hoặc không nằm trong group con, và phép so sánh với `@GroupSequence`.

Sử dụng Java 17+, Maven và Spring Boot 3.5.8. Spring Boot với `spring-boot-starter-validation` sẽ cấu hình Bean Validation provider tương thích, để `jakarta.validation.Validator` được inject từ Spring context. Các lệnh và kết quả `System.out.println` trong ví dụ không phụ thuộc thứ tự của `Set<ConstraintViolation>` vì mã sẽ sắp xếp property paths.

Cấu trúc:

```text
group-inheritance-demo/
├── pom.xml
└── src/main/java/demo/GroupInheritanceDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>group-inheritance-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/GroupInheritanceDemo.java`

```java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GroupInheritanceDemo {

    // Các group thông thường.
    public interface Basic {}
    public interface Billing {}

    // Kế thừa đồng thời hai group.
    public interface Checkout extends Basic, Billing {}

    // Kế thừa Checkout và Default.
    public interface CompleteCheckout extends Checkout, Default {}

    // Sequence riêng: khác với "extends".
    @GroupSequence({Default.class, Checkout.class})
    public interface OrderedChecks {}

    public static final class Order {
        @NotBlank
        private final String orderId; // Default

        @NotBlank(groups = Basic.class)
        private final String buyerId;

        @NotBlank(groups = Billing.class)
        private final String paymentToken;

        @Positive(groups = Checkout.class)
        private final Integer quantity;

        @Size(min = 3, groups = CompleteCheckout.class)
        private final String coupon;

        public Order(String orderId, String buyerId,
                     String paymentToken, Integer quantity,
                     String coupon) {
            this.orderId = orderId;
            this.buyerId = buyerId;
            this.paymentToken = paymentToken;
            this.quantity = quantity;
            this.coupon = coupon;
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(GroupInheritanceDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(Validator validator) {
        return args -> {
            Order allInvalid =
                    new Order("", "", "", 0, "X");

            show("Default", validator, allInvalid, Default.class);
            show("Basic", validator, allInvalid, Basic.class);
            show("Billing", validator, allInvalid, Billing.class);
            show("Checkout", validator, allInvalid, Checkout.class);
            show("CompleteCheckout", validator, allInvalid,
                    CompleteCheckout.class);

            show("Default + Checkout", validator, allInvalid,
                    Default.class, Checkout.class);

            // Default lỗi => nhóm sau trong sequence bị bỏ qua.
            show("Ordered", validator, allInvalid, OrderedChecks.class);

            // Default đạt, nên sequence mới tiến sang Checkout.
            Order validDefault =
                    new Order("O-01", "", "", 0, "X");
            show("Ordered after Default passes",
                    validator, validDefault, OrderedChecks.class);
        };
    }

    static void show(String label, Validator validator,
                     Order order, Class<?>... groups) {

        Set<ConstraintViolation<Order>> violations =
                validator.validate(order, groups);

        String paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", "));

        System.out.println(label + " (" + violations.size() + "): "
                + (paths.isEmpty() ? "OK" : paths));
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Ngoài log khởi động thông thường của Spring Boot, các dòng do chương trình tự in ra là:

```text
Default (1): orderId
Basic (1): buyerId
Billing (1): paymentToken
Checkout (3): buyerId, paymentToken, quantity
CompleteCheckout (5): buyerId, coupon, orderId, paymentToken, quantity
Default + Checkout (4): buyerId, orderId, paymentToken, quantity
Ordered (1): orderId
Ordered after Default passes (3): buyerId, paymentToken, quantity
```

### Giải thích kết quả, từng dòng

1. **Default (1):** `orderId=""` vi phạm `@NotBlank` không khai báo group, thuộc `Default`. Group `Default` không tự kéo các group chuyên biệt vào.
2. **Basic (1):** `buyerId=""` là constraint duy nhất thuộc `Basic`; `orderId` không thuộc Basic.
3. **Billing (1):** `paymentToken=""` thuộc `Billing`.
4. **Checkout (3):** `Checkout extends Basic, Billing` nên chọn cả `buyerId`, `paymentToken` và `quantity` của chính `Checkout`. Không có `orderId` vì `Checkout` **không extends Default**.
5. **CompleteCheckout (5):** `CompleteCheckout extends Checkout, Default` nên bao gồm cả ba constraint của Checkout, `orderId` của Default, và `coupon` chỉ thuộc chính CompleteCheckout.
6. **Default + Checkout (4):** yêu cầu đồng thời hai group trả tập constraint của Default và Checkout; `coupon` chỉ ở CompleteCheckout không được đưa vào. Thứ tự liệt kê hai group trong lời gọi `validate` không bảo đảm thứ tự thực thi constraint.
7. **Ordered (1):** `@GroupSequence({Default.class, Checkout.class})` chỉ chạy nhóm Checkout nếu Default không có vi phạm. `orderId=""` làm sequence dừng.
8. **Ordered after Default passes (3):** `orderId="O-01"` qua được Default; sequence tiếp tục chạy Checkout và phát hiện ba constraint vi phạm. `coupon` vẫn không được kiểm tra vì nhóm CompleteCheckout không nằm trong sequence.

Trong `Order`, hai thuộc tính `String` rỗng thuộc các group Basic/Billing, `quantity = 0` không đạt `@Positive` và `coupon="X"` không đạt `@Size(min=3)`. Các violation thuộc các property khác nhau và code đã sort path, nên phần stdout do ví dụ in ra có thứ tự xác định. Ví dụ được viết để chạy bằng Spring Boot 3.5.8 và Java 17; nếu chuyển sang Spring Framework thuần, cần tự cấu hình Bean Validation provider/`LocalValidatorFactoryBean` thích hợp.

**Kết luận từ demo:** kế thừa group giải quyết câu hỏi **"cần kiểm tra những điều kiện nào?"**; group sequence giải quyết câu hỏi **"cần kiểm tra các lớp điều kiện theo thứ tự nào?"**.

## 6. Kế thừa nhóm không giống kế thừa class JavaBean

Có **hai** khái niệm kế thừa dễ bị nhầm:

1. **Kế thừa group:** một interface group `Child extends Parent`. Khi validate `Child`, constraint thuộc Parent được chọn.
2. **Kế thừa class/property constraints:** một class Java triển khai interface có constraint hoặc kế thừa superclass mang constraint; các constraint ở cây kiểu đối tượng có thể được Bean Validation xét theo đặc tả.

Ví dụ group inheritance:

```java
interface CommonChecks {}
interface AdminChecks extends CommonChecks {}
```

Đây là quan hệ của **interface đại diện group**, không phải quan hệ type hierarchy của DTO.

Ví dụ JavaBean inheritance:

```java
class BaseProfile {
    @NotBlank
    protected String name;
}

class AdminProfile extends BaseProfile {
    @NotBlank(groups = AdminChecks.class)
    private String department;
}
```

Khi validate một `AdminProfile` với `Default`, constraint `name` từ superclass được xét theo quy tắc kế thừa constraint của object. Khi validate với `AdminChecks` mà không extends `Default`, constraint `name` chỉ thuộc Default **không tự được chọn**, dù field này có trong superclass.

Khi validate `AdminChecks`, nếu group ấy `extends CommonChecks` thì các constraint thuộc CommonChecks cũng được chọn; đó là **quan hệ group** độc lập với JavaBean class inheritance. Không suy từ `class AdminProfile extends BaseProfile` rằng `AdminChecks` tự kế thừa Default hoặc bất cứ group nào.

Phạm vi thay đổi constraints trên các **getter override** hoặc **method parameter/return constraints** có quy tắc riêng trong Jakarta Validation để bảo vệ hợp đồng kế thừa method; không nên áp dụng quy tắc đơn giản của field-group sang mọi dạng method validation.

## 7. Implicit grouping: interface chứa constraint cũng đại diện một group

Jakarta Validation có cơ chế **implicit grouping** ngoài việc ghi tường minh `groups = ...`. Một constraint khai báo trên interface `Z` và thuộc group `Default` (do bỏ `groups` hoặc ghi rõ `Default`) cũng thuộc **group có tên chính interface `Z`**.

Ví dụ:

```java
public interface NameView {
    @NotBlank
    String getDisplayName();
}

public class Person implements NameView {
    private final String displayName;

    public Person(String displayName) {
        this.displayName = displayName;
    }

    @Override
    public String getDisplayName() {
        return displayName;
    }
}
```

Đây là **đoạn khai báo minh họa**, khi đưa vào source, tách public types thành file tương ứng và import `@NotBlank`. Với `Person("")`:

- `validator.validate(person)` sẽ thấy `@NotBlank` trên getter của interface do Bean Validation có quy tắc xem xét constraints từ interface.
- `validator.validate(person, NameView.class)` cũng có thể thấy ràng buộc ấy nhờ implicit grouping, dù annotation trên getter **không viết** `groups = NameView.class`.
- Nếu interface `DetailedNameView extends NameView`, việc validate `DetailedNameView.class` có thể chọn constraint của `NameView` vì group kế thừa interface.

**Đừng kết luận mọi `class Person implements NameView` đều tự có một nhóm mới** chỉ vì interface bất kỳ. Điều quan trọng là **constraint được khai báo trên interface** và thuộc `Default` của interface; cách tính group Z theo đặc tả mới tạo implicit group.

Implicit grouping đặc biệt có ích khi một interface biểu diễn một góc nhìn/role của dữ liệu và muốn kiểm tra phần state tương ứng, mà không phải gắn group lên từng constraint.

## 8. Kế thừa group khác với `@GroupSequence`

### Group inheritance: gom điều kiện, không đảm bảo thứ tự

```java
public interface Identity {}
public interface Payment {}
public interface Complete extends Identity, Payment {}
```

`validate(order, Complete.class)` yêu cầu constraint của Identity, Payment và Complete. **Không có hợp đồng "Identity trước Payment"**. Nếu cả hai fail, chúng đều có thể được báo lỗi trong cùng lượt kiểm tra.

### Group sequence: xác định thứ tự, có điều kiện dừng

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

public interface Payment {}

@GroupSequence({Default.class, Payment.class})
public interface OrderedPaymentChecks {}
```

Khi `validate(order, OrderedPaymentChecks.class)`:

1. Chạy `Default`.
2. Nếu Default có ít nhất một violation, **bỏ qua** `Payment`.
3. Chỉ khi Default đạt mới chạy Payment.

**Các quy tắc an toàn:**

- Interface mang `@GroupSequence` nên **không đồng thời extends nhóm khác**. Đặc tả khuyến nghị group sequence interface không có superinterface.
- Không dùng trực tiếp sequence interface làm `groups = OrderedPaymentChecks.class` trên constraint; nó đại diện cho **trình tự**, không phải group gắn vào constraint.
- Tránh vòng tham chiếu giữa các sequence, kể cả vòng sinh gián tiếp qua group inheritance; khi được thực thi có thể ném `GroupDefinitionException`.
- Nếu một constraint xuất hiện trong nhiều group của sequence, provider tránh kiểm tra lặp cùng constraint.
- Kế thừa group không phải cách thay thế cho `@GroupSequence` và không tạo short-circuit.

### Định nghĩa lại `Default` ở cấp class là một việc khác nữa

```java
@GroupSequence({Invoice.class, InvoiceExtraChecks.class})
public class Invoice {
    @NotNull
    private String number;

    public interface InvoiceExtraChecks {}
}
```

Đây là **class minh họa**, cần import `GroupSequence` và `NotNull`. Khi đặt `@GroupSequence` lên **class** để định nghĩa lại Default của class đó, sequence phải **chứa chính `Invoice.class`**, **không đặt `Default.class` thay cho `Invoice.class`**; nếu không cấu hình có thể ném `GroupDefinitionException`. Quy tắc định nghĩa lại Default của class này **không tự thay đổi Default group cho tất cả object lồng nhau**: từng bean được validate theo group propagation/cascade riêng.

Đừng nhầm ba cơ chế:

| Cơ chế | Viết ở đâu? | Tác dụng |
| --- | --- | --- |
| `extends` | Interface group | Gộp constraint của group cha vào group con |
| `@GroupSequence` trên interface | Interface độc lập | Thứ tự và short-circuit |
| `@GroupSequence` trên class | JavaBean class | Định nghĩa lại Default sequence của riêng class |

## 9. Group inheritance và đối tượng lồng nhau có `@Valid`

Một lượt validation với group được yêu cầu có thể được **cascade** sang object con:

```java
public class OrderForm {
    @NotBlank(groups = Basic.class)
    private String orderCode;

    @Valid
    private DeliveryAddress address;
}

public class DeliveryAddress {
    @NotBlank(groups = Basic.class)
    private String city;

    @NotBlank(groups = Billing.class)
    private String contactEmail;
}
```

Hai class trên là **mô hình minh họa**, cần import `jakarta.validation.Valid`, `NotBlank` và định nghĩa các interface group. Giả sử `Checkout extends Basic, Billing`:

- Khi gọi `validator.validate(order, Checkout.class)`, constraint thuộc `Basic` trên `orderCode` được chọn.
- `@Valid` đánh dấu cascade; provider tiếp tục đánh giá object `DeliveryAddress` với các group được truyền theo quy tắc Jakarta Validation.
- Vì Checkout bao gồm Basic và Billing, cả `city` và `contactEmail` có thể được đánh giá trong object con.
- Nếu thiếu `@Valid` trên `address`, provider **không tự đi sâu** vào DeliveryAddress chỉ vì group Checkout kế thừa hai nhóm.
- Nếu `address == null`, việc cascade không tạo lỗi bắt buộc có địa chỉ; cần `@NotNull` nếu muốn bắt buộc.

Một group chỉ quyết định **tập constraint**, còn `@Valid` quyết định **đường đi trong graph**. Với nested collection như `List<@Valid DeliveryAddress>`, provider cần value extractor cho container; List là loại container đã được hỗ trợ chuẩn.

### Đổi group khi cascade: `@ConvertGroup`

Có lúc nhóm ở parent và child mang ý nghĩa nghiệp vụ khác nhau. Khi đó có thể dùng:

```java
@Valid
@ConvertGroup(from = Checkout.class, to = Billing.class)
private DeliveryAddress address;
```

Đây là **field minh họa**, cần import `jakarta.validation.groups.ConvertGroup`. Khi group được truyền tới đường cascade này khớp `Checkout` theo quy tắc group conversion của đặc tả, child được kiểm tra với `Billing`; quan hệ group inheritance đã khai báo trên child vẫn có hiệu lực đối với group thực sự được áp dụng.

Lưu ý có một chi tiết nâng cao: Jakarta Validation mở rộng **group sequence trước khi áp dụng group conversion**. Quy tắc `from` tương ứng với group tại bước cascade sau khi đã khai triển sequence, không nhất thiết là đúng chuỗi group ban đầu được truyền vào `validate`. Không tự cho rằng conversion là phép thay toàn bộ cây group hay tự áp dụng đệ quy nhiều lần; một quy tắc conversion được áp dụng một lần trên cùng một cạnh cascade.

Không gắn `@ConvertGroup` khi không có `@Valid` ở vị trí phù hợp; đó là khai báo không hợp lệ. Chỉ dùng group conversion khi có lý do tái sử dụng object graph mà không muốn để group của parent lan nguyên vẹn sang child.

## 10. Spring Framework: `@Validated` dùng group con như thế nào?

Spring Framework sử dụng Jakarta Bean Validation qua `LocalValidatorFactoryBean` (được cấu hình tự động trong nhiều ứng dụng Spring Boot có validation provider). Các interface group vẫn là **interface Java bình thường** và được truyền trực tiếp cho provider.

### Dùng trực tiếp Jakarta `Validator`

```java
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(order, Checkout.class);
```

Đây là **đoạn minh họa**, cần `order` là `OrderForm`, `validator` là `jakarta.validation.Validator`, các import tương ứng. Provider tự mở rộng các group cha của Checkout; Spring không yêu cầu đăng ký từng group interface bằng bean riêng.

### Spring `SmartValidator` và validation hints

```java
BindingResult errors =
        new BeanPropertyBindingResult(order, "order");

smartValidator.validate(order, errors, Checkout.class);
```

Đây là đoạn minh họa cần các biến/import. `org.springframework.validation.SmartValidator` cho phép truyền validation hints, thường được `LocalValidatorFactoryBean`/adapter chuyển thành Jakarta groups. `Errors`/`BindingResult` chứa `FieldError`/`ObjectError` khi constraint sai. Khi chỉ gọi `org.springframework.validation.Validator.validate(target, errors)` (giao diện không có hints), cơ chế thông thường dùng Default.

### Spring MVC REST hoặc form

Trong một controller Spring MVC:

```java
@PostMapping("/orders")
public ResponseEntity<?> createOrder(
        @Validated(Checkout.class)
        @RequestBody CreateOrderRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(e -> e.getField() + ": "
                                + e.getDefaultMessage())
                        .toList());
    }
    return ResponseEntity.ok().build();
}
```

Đây là **method minh họa**, cần DTO, interface Checkout và các import Spring/Jakarta. Spring MVC có thể dùng `@Validated(Checkout.class)` để yêu cầu validate object với Checkout; provider sẽ mở rộng nhóm cha theo `extends`. `BindingResult` được đặt ngay sau object cần validate ở chữ ký hỗ trợ.

Nếu thay `@Validated(Checkout.class)` bằng `@Valid`:

- `@Valid` thông thường yêu cầu kiểm tra **Default group** (không truyền Checkout một cách ngầm định).
- Các constraint chỉ thuộc Basic/Billing/Checkout có thể không chạy nếu Default không gồm chúng qua quy tắc cấu hình đặc biệt.
- Kế thừa group không thay việc **chọn đúng group ở entry point**.

Không nhầm với constraint đặt trực tiếp trên tham số handler method như `@Min`/`@NotBlank`: trong Spring MVC mới, method validation có cơ chế riêng và có thể tạo loại exception khác với validation của DTO. Việc chọn `@Validated` ở cấp tham số và cấp class phải tuân quy tắc của phiên bản Spring đang dùng.

### Spring service method validation

```java
@Service
@Validated(Checkout.class)
public class OrderService {
    public void submit(@Valid OrderForm form) {
        // ...
    }
}
```

Đây là **class minh họa**, cần import Spring/Jakarta. Khi bean được quản lý qua Spring và method-validation interceptor thực sự được kích hoạt, nhóm Checkout ở `@Validated` có thể được áp dụng cho lượt method validation/cascade phù hợp. **Không nên** nghĩ annotation này chạy khi tự `new OrderService()` hoặc khi self-invocation bỏ qua AOP proxy. Hãy xác nhận cấu hình `MethodValidationPostProcessor`/Spring Boot và test bằng Spring-managed bean.

Một điểm khác thường gặp: `@Validated` trên class của MVC controller có thể dùng AOP method validation đời cũ, trong khi Spring MVC hiện đại có cơ chế tích hợp riêng. Không thêm class-level `@Validated` cho mọi controller nếu chỉ cần bind/validate DTO với group ở tham số.

## 11. Tình huống thực tế: tạo mới, cập nhật, thanh toán

Giả sử có ba giai đoạn:

- **Basic:** xác minh user có mã định danh/giỏ hàng.
- **Billing:** xác minh thông tin thanh toán.
- **Checkout:** cần cả Basic và Billing, cộng thêm điều kiện của bước checkout.
- **FullSubmission:** thêm các constraint Default dùng chung toàn ứng dụng.

Định nghĩa:

```java
public interface Basic {}
public interface Billing {}
public interface Checkout extends Basic, Billing {}
public interface FullSubmission extends Checkout, Default {}
```

Ứng dụng có thể sử dụng:

```java
validator.validate(order, Basic.class);          // Chỉ Basic
validator.validate(order, Billing.class);        // Chỉ Billing
validator.validate(order, Checkout.class);       // Basic + Billing + Checkout
validator.validate(order, FullSubmission.class); // Cả Default
```

**Lựa chọn kỹ thuật:**

- Nếu yêu cầu *kiểm tra tất cả các nhóm* và trả lỗi cùng lượt, kế thừa group phù hợp.
- Nếu yêu cầu *kiểm tra field cơ bản trước, chỉ chạy kiểm tra đắt tiền sau khi bước đầu đạt*, dùng group sequence.
- Nếu yêu cầu *chuyển group khi validate object con* do child có nhóm riêng, dùng `@ConvertGroup` trên cạnh cascade.
- Nếu chỉ có vài trường hợp tạo/cập nhật, đôi khi hai group `OnCreate`/`OnUpdate` với nhóm cha `Common` là đủ; không tạo cây interface phức tạp vô ích.

Lưu ý **không đưa truy cập DB tốn kém trực tiếp vào mọi custom `ConstraintValidator`** mà chưa xem xét mục đích, caching, I/O, transaction và performance. Group inheritance không bảo đảm thứ tự hoặc bỏ qua constraint đắt tiền khi constraint khác thất bại; group sequence mới cung cấp cơ chế short-circuit theo nhóm.

## 12. Những lỗi phổ biến

| Dấu hiệu | Nguyên nhân dễ gặp | Cách xử lý |
| --- | --- | --- |
| `validate(bean, Checkout.class)` không kiểm tra `@NotBlank` không có `groups` | Checkout không extends Default | Dùng `Checkout extends Default, ...` khi muốn bao gồm Default |
| Validate Basic mà thiếu constraint Billing | Basic không kế thừa Billing | Yêu cầu Checkout hoặc Billing; quan hệ một chiều |
| Group con chạy nhưng không theo thứ tự mong muốn | `extends` chỉ định tập, không chỉ định thứ tự | Dùng `@GroupSequence` |
| `@Validated(Checkout.class)` không có tác dụng trong unit test gọi `new Controller()` | Không đi qua Spring MVC/proxy/validator | Test đúng infrastructure hoặc gọi Validator trực tiếp |
| Annotation ở object con không chạy | Thiếu `@Valid` | Thêm cascade marker trên đúng đường |
| Group child không được áp vào nested object như kỳ vọng | Có group conversion hoặc Default redefinition | Kiểm tra `@ConvertGroup`, sequence, group propagation |
| `@NotBlank(groups=OnCreate.class)` bị bỏ qua khi gọi `validate(bean)` | Mặc định chỉ chọn `Default` | Truyền OnCreate hoặc thiết kế group con kế thừa Default hợp lý |
| Một constraint khai báo ở hai group xuất hiện hai lần trong source code | Gắn annotation lặp không cần thiết | Dùng `groups = {A.class, B.class}` hoặc nhóm con chung |
| `GroupDefinitionException` khi chạy sequence | Vòng trong inheritance/sequence hoặc default redefinition sai | Loại vòng, xác nhận class `@GroupSequence` chứa class tương ứng |
| Nhầm `javax.validation.*` với `jakarta.validation.*` | Dependency thuộc hai thế hệ | Với Framework 6+/Boot 3+, thống nhất Jakarta namespace |
| Service có `@Validated` nhưng call nội bộ không bị chặn | Self-invocation bỏ qua proxy | Dùng boundary bean khác hoặc validation explicit |
| Dựa vào thứ tự violation của `Set` | API không bảo đảm thứ tự | Assert bằng tập property path hoặc sort trước khi in |

**Phân biệt group inheritance và class inheritance** trước khi sửa code: nếu bean kế thừa field constraint từ superclass nhưng gọi nhóm không phù hợp, lỗi nằm ở **chọn group**, không phải provider không đọc được lớp cha.

## 13. Kiểm thử kế thừa nhóm đúng cách

Để tránh hiểu sai logic, hãy tạo một bean mà mỗi nhóm có **một field vi phạm riêng**, sau đó kiểm tra tập đường dẫn vi phạm:

1. `validate(bean, Basic.class)`: chỉ field của Basic.
2. `validate(bean, Billing.class)`: chỉ field của Billing.
3. `validate(bean, Checkout.class)`: field của Basic, Billing và Checkout.
4. `validate(bean, Default.class)`: chỉ field Default (trừ khi class có default-group redefinition hoặc quy tắc khác).
5. `validate(bean, CompleteCheckout.class)`: thêm Default và ràng buộc chỉ thuộc CompleteCheckout.
6. `validate(bean, Default.class, Checkout.class)`: kết hợp tập group, không dựa vào thứ tự.
7. `validate(bean, OrderedChecks.class)`: xác nhận nếu Default sai thì Checkout không chạy.
8. `@Validated(Checkout.class)` trong Spring MVC: gửi request và kiểm tra field errors thuộc group cha.
9. `@Valid` nested: kiểm tra object con có/không có và group được truyền qua cascade.
10. Group conversion: test rõ property child thuộc group nào sau khi conversion, nhất là với sequence.

Ví dụ test JUnit 5 (đây là **method minh họa** với `Order` và `Validator` đã khai báo ở ví dụ chính):

```java
@Test
void checkoutInheritsBothParentGroups() {
    Order order = new Order("", "", "", 0, "X");

    Set<String> paths = validator.validate(order, Checkout.class)
            .stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());

    assertEquals(Set.of("buyerId", "paymentToken", "quantity"),
                 paths);
}
```

Cần `org.junit.jupiter.api.Test` và `Assertions.assertEquals` (static import), `java.util.Set` và `Collectors`; `validator` nên được inject từ Spring context/được khởi tạo từ provider tương thích. Đây là test về **group inheritance**, không phải test MVC. Với kiểm thử MVC, sử dụng `MockMvc` để bảo đảm controller thực sự yêu cầu group đã định.

**Không assert thứ tự ConstraintViolation**: `Validator.validate(...)` trả Set, không phải danh sách có thứ tự bắt buộc. Kiểm tra theo property path, constraint descriptor hoặc nhóm expectation thay vì lấy phần tử đầu tiên.

## 14. Các trường hợp nâng cao cần lưu ý

### Interface kế thừa `Default` và group sequence đặt trên class

Ví dụ `Complete extends Default` chỉ là **mở rộng tập constraint**, không tự làm Default của một JavaBean định nghĩa lại. Nếu class có `@GroupSequence`, việc áp dụng Default khi validate class đó tuân sequence riêng của class; đừng xem “group con extends Default” là biến đổi toàn bộ vòng đời validation của mọi object.

### Group interface có thể là hợp đồng role

Một interface vừa định nghĩa getter được constraint vừa đại diện implicit group. Kế thừa interface này trong group khác có thể dẫn đến tập constraint không chỉ từ `groups=...` ghi tường minh mà còn từ implicit group. Khi kết quả nhiều hơn dự kiến, hãy kiểm tra **constraint trên getter của interface** và metadata qua `validator.getConstraintsForClass(...)`.

### Group sequence và vòng phụ thuộc

Một sequence có thể chứa group đã được kế thừa ở group khác; không có nghĩa mọi cách pha trộn đều hợp lệ. Đặc tả cấm vòng trực tiếp/gián tiếp giữa group sequence, kể cả vòng qua inheritance. Khi gặp `GroupDefinitionException`, kiểm tra đồ thị phụ thuộc group/sequence, không chỉ một annotation tại nơi exception xuất hiện.

### Group conversion khi qua nested collection

Với `List<@Valid Address>` hoặc `Map<Key, @Valid Value>`, group propagation/cascading áp dụng qua value extractors. `@ConvertGroup` trên phần tử container được hỗ trợ ở vị trí hợp lệ; việc dùng `@Valid`/`@ConvertGroup` sai chỗ có thể gây `ConstraintDeclarationException`. Sử dụng type-use annotations rõ ràng và test đường dẫn vi phạm ở nested object.

### Method validation và kế thừa method

Thêm constraint lên parameter ở một override method có thể vi phạm quy tắc Liskov substitution của Bean Validation, ngay cả khi class đã sử dụng đúng group inheritance. Các quy định về overriding methods khác với cách group interface `extends`. Nếu có lỗi `ConstraintDeclarationException` ở service interface/implementation, xem đặc tả **Method constraints in inheritance hierarchies** trước khi đổi group.

## 15. Câu hỏi tự kiểm tra

**1. `interface Advanced extends Basic {}`, gọi `validate(bean, Advanced.class)` có chọn constraint Basic không?**  
Có. Advanced kế thừa toàn bộ constraint thuộc Basic và các group cha của Basic.

**2. Gọi `validate(bean, Basic.class)` có tự chạy constraint chỉ thuộc Advanced không?**  
Không. Quan hệ inheritance là một chiều từ group con đến group cha.

**3. `interface CreateChecks {}` có tự bao gồm constraint `@NotBlank` không ghi groups không?**  
Không; những constraint đó thuộc Default. Muốn bao gồm Default thì thiết kế group inheritance rõ ràng hoặc yêu cầu cả hai group.

**4. `interface CreateChecks extends Default {}` có giống `@GroupSequence({Default.class, CreateChecks.class})` không?**  
Không. `extends Default` chọn tập constraint; `@GroupSequence` tạo thứ tự và dừng khi nhóm trước có vi phạm.

**5. Có thể kế thừa nhiều group không?**  
Có: `interface Checkout extends Identity, Billing {}`, theo đúng cú pháp Java interface đa kế thừa.

**6. Kế thừa group có làm Bean Validation tự đi vào object con không?**  
Không. Việc duyệt object graph cần `@Valid`; nhóm chỉ quyết định những constraint nào được chọn tại các object đã được đưa vào lượt validation.

**7. Khi `@Validated(Checkout.class)` trên Spring MVC argument, Spring có cần ta đăng ký từng interface group làm bean không?**  
Không. Jakarta Bean Validation dùng interface class metadata; Spring truyền group được yêu cầu cho provider. Tuy nhiên cần validator provider và MVC integration đang hoạt động.

**8. Nếu class tự `new` rồi gọi setter, mọi constraint của group cha có chạy tức thì không?**  
Không. Cần một lượt validate được gọi hoặc một framework entry point kích hoạt đúng cách.

**9. Nếu group `Checkout` có `extends Default` thì có nghĩa Default luôn kiểm tra các constraint chỉ thuộc Checkout không?**  
Không. Validate Default vẫn là chiều ngược lại: chỉ chạy constraint thuộc Default theo quy tắc nhóm/default sequence tương ứng.

**10. Tại sao nên test bằng tập property path chứ không theo thứ tự?**  
Thứ tự duyệt constraint/violation của group không được bảo đảm; Set không có thứ tự contract để chương trình dựa vào.

## 16. Tóm tắt

Kế thừa nhóm kiểm tra là một mô hình **tái sử dụng tập constraint theo interface inheritance**: group con bao gồm nhóm cha, hỗ trợ đa kế thừa và bắc cầu, nhưng **không quy định thứ tự thực thi**. `Default` chỉ được đưa vào khi thực sự được chọn (chẳng hạn `Child extends Default`); `@GroupSequence` là một cơ chế khác để xếp thứ tự và short-circuit. Trong Spring, `@Validated(Group.class)` hoặc `SmartValidator` chỉ định nhóm mà provider sẽ mở rộng, còn `@Valid` quyết định việc cascade qua object graph.

Hãy luôn tự hỏi: **"Tôi đang chọn tập constraint, sắp xếp thứ tự, hay chuyển nhóm khi cascade?"** Ba mục đích này tương ứng với **`extends`, `@GroupSequence` và `@ConvertGroup`**.

## Tài liệu tham khảo chính thức

- Jakarta Validation 3.1 — mục `5.4.1 Group inheritance`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `5.4.2 Group sequence`, `5.4.3 Redefining Default`, `5.4.4 Implicit grouping`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `5.4.5 Group conversion` và `5.4.6 Formal group definitions`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — package `jakarta.validation.groups` và `Default`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/package-summary.html
- Jakarta Validation API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/Validator.html
- Hibernate Validator Reference Guide — Chapter 5 Grouping constraints: https://docs.jboss.org/hibernate/validator/9.0/reference/en-US/html_single/#chapter-groups
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework API — `@Validated`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework API — `SmartValidator`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/SmartValidator.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
