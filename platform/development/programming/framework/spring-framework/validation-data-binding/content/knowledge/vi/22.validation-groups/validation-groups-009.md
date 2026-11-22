# @ConvertGroup khi kiểm tra lan truyền trong Jakarta Bean Validation và Spring Framework

## 1. Vấn đề: bean cha và bean con không nhất thiết dùng cùng một nhóm

Trong một hệ thống Spring, lớp `OrderRequest` có thể chứa `Address` hoặc `Customer`. Khi gửi yêu cầu tạo đơn hàng, ta muốn kiểm tra một nhóm constraint ở **đối tượng cha**, nhưng đối tượng con có thể là thành phần tái sử dụng với bộ nhóm riêng. Nếu chỉ truyền một nhóm xuyên suốt object graph, những ràng buộc cần thiết trên bean con có thể bị bỏ qua.

Ví dụ yêu cầu:

- `OrderRequest` được validate theo nhóm mặc định `Default` khi client submit.
- `OrderRequest.orderCode` có `@NotBlank` ở nhóm `Default`.
- `Address.city` có `@NotBlank` ở nhóm `Default`, chỉ dùng cho một dạng kiểm tra thông thường.
- `Address.street` lại có `@NotBlank(groups = DeliveryChecks.class)`, dành cho giao hàng.
- Khi kiểm tra `OrderRequest`, ta muốn **giữ Default ở cha**, nhưng **dùng DeliveryChecks ở Address**.

Giải pháp đúng của Jakarta Bean Validation là **`@Valid` kết hợp `@ConvertGroup` tại điểm lan truyền (cascade point)**:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class OrderRequest {
    @NotBlank
    private String orderCode;

    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    private Address shippingAddress;
}
```

Đây là đoạn minh họa trong project có khai báo `Address`, `DeliveryChecks` và import `@NotBlank`. Khi gọi `validator.validate(order)`, root bean vẫn kiểm tra constraint thuộc `Default`; **chỉ khi đi theo thuộc tính `shippingAddress`**, nhóm được chuyển thành `DeliveryChecks` rồi áp dụng lên bean `Address`. Nhóm không bị đổi toàn cục.

**Ghi nhớ sớm:** `@Valid` quyết định **có đi sâu vào đối tượng liên quan hay không**; `@ConvertGroup` quyết định **dùng nhóm nào khi đi qua cạnh đó**. Không có cascade thì không có group conversion.

Bài này dùng namespace **`jakarta.validation.*`** của Jakarta Validation 3.x, phù hợp với Spring Framework 6 / Spring Boot 3. Các ví dụ ứng dụng Java 17+. Tránh trộn `javax.validation.*` từ các stack cũ với Jakarta API/provider hiện đại.

## 2. Ôn lại group và @Valid trước khi chuyển nhóm

Một **validation group** là một marker interface dùng để phân loại constraint:

```java
public interface DeliveryChecks {}
public interface BillingChecks {}
```

Đặt group cho một constraint:

```java
class Address {
    @NotBlank
    String city; // Default nếu không khai báo groups.

    @NotBlank(groups = DeliveryChecks.class)
    String street;
}
```

Để validate một bean, `jakarta.validation.Validator` nhận nhóm thông qua varargs:

```java
validator.validate(address);                       // Default
validator.validate(address, Default.class);        // Default tường minh
validator.validate(address, DeliveryChecks.class); // DeliveryChecks
```

Khi không truyền nhóm, Jakarta Validation dùng `jakarta.validation.groups.Default`. Khi chỉ truyền `DeliveryChecks.class`, không được mặc định các constraint chỉ thuộc `Default` cũng sẽ chạy, trừ khi các quy tắc group inheritance/sequence hoặc metadata tương ứng khiến chúng được chọn.

### 2.1. Lan truyền mà không chuyển nhóm

Nếu object cha có property:

```java
@Valid
private Address shippingAddress;
```

thì khi `validator.validate(parent, Default.class)`, Bean Validation sẽ kiểm tra constraint ở cha theo `Default`, rồi **lan truyền Default** sang `shippingAddress`. Khi đó `Address.city` được kiểm tra, còn `Address.street` chỉ thuộc `DeliveryChecks` không tự chạy.

Nếu `shippingAddress == null`, `@Valid` không tạo lỗi vì null; nó không thực hiện cascade vào object không tồn tại. Khi field bắt buộc có đối tượng con, đặt thêm `@NotNull` trên chính property theo nhóm phù hợp.

### 2.2. Có @ConvertGroup tại cạnh cascade

Nếu đổi thành:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
private Address shippingAddress;
```

thì nhóm `Default` đi ra từ cha **được ánh xạ thành `DeliveryChecks` trên cạnh này**. `Address.street` được kiểm tra; constraint chỉ thuộc `Default` như `Address.city` không tự động chạy trong lần cascade đó.

Bảng phân biệt với `Address(city="", street="")`:

| Gọi từ root | Cấu hình quan hệ | Nhóm thực sự đến Address | Constraint con được chọn |
| --- | --- | --- | --- |
| `validate(root)` | `@Valid` | `Default` | `city` |
| `validate(root)` | `@Valid @ConvertGroup(Default → DeliveryChecks)` | `DeliveryChecks` | `street` |
| `validate(root, DeliveryChecks.class)` | Chỉ `@Valid` | `DeliveryChecks` | `street` |
| `validate(root, DeliveryChecks.class)` | Convert **chỉ** từ Default | `DeliveryChecks` giữ nguyên | `street` |
| `validate(root, BillingChecks.class)` | Convert **chỉ** từ Default | `BillingChecks` giữ nguyên | Các rule thuộc BillingChecks nếu có |

Điều kiện chuyển nhóm là **khớp giá trị `from` của nhóm đang đi qua điểm cascade**. Nếu không có quy tắc phù hợp, nhóm được lan truyền nguyên trạng.

## 3. Cú pháp và hợp đồng chính xác của @ConvertGroup

Annotation thuộc package:

```java
import jakarta.validation.groups.ConvertGroup;
```

Cú pháp tổng quát:

```java
@Valid
@ConvertGroup(from = SourceGroup.class, to = TargetGroup.class)
private RelatedBean related;
```

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `@Valid` | Đánh dấu cascade sang bean con |
| `@ConvertGroup` | Quy tắc đổi nhóm tại đúng điểm cascade |
| `from` | Nhóm đầu vào cần ánh xạ, mặc định `Default.class` nếu bỏ qua |
| `to` | Nhóm được gửi tới bean con; bắt buộc khai báo |
| `@ConvertGroup.List` | Container annotation cho nhiều luật chuyển nhóm trên cùng điểm, có thể dùng dạng repeatable khi Java/provider hỗ trợ |
| `Default.class` | Marker interface `jakarta.validation.groups.Default`, không phải “mọi nhóm” |

Viết gọn khi nhóm nguồn là Default:

```java
@Valid
@ConvertGroup(to = DeliveryChecks.class)
private Address shippingAddress;
```

Tương đương về nhóm nguồn với `from = Default.class`. Đây là **mặc định của riêng thuộc tính `from`**, không có nghĩa `to` được tự chọn.

### 3.1. Điều kiện bắt buộc và lỗi khai báo

- `@ConvertGroup` chỉ hợp lệ ở điểm **có `@Valid` tại chính phần tử/tuyến cascade phù hợp**. Dùng `@ConvertGroup` đơn lẻ, không có `@Valid`, là khai báo không hợp lệ; provider có thể ném `ConstraintDeclarationException` khi đọc metadata hoặc thực thi validation.
- Không được khai báo **hai luật có cùng giá trị `from` trên cùng một cascade point**. Ví dụ cả `Default → A` và `Default → B` ở cùng một điểm là mâu thuẫn và dẫn đến `ConstraintDeclarationException`.
- `from` **không được là một interface được định nghĩa là group sequence**. `to` **có thể** là group sequence hợp lệ.
- Không áp dụng `@ConvertGroup` ở một vị trí bất kỳ trong project rồi kỳ vọng nó đổi nhóm cho mọi association. **Vị trí đặt annotation chính là phạm vi tác dụng.**
- Trên các cấu trúc có inheritance/overridden methods, Jakarta Validation có các ràng buộc riêng đối với việc thêm group conversion ở parameter/return value để giữ hợp đồng thừa kế. Đừng thay đổi khai báo method mà bỏ qua kiểm thử metadata.

**Ví dụ sai:**

```java
// Sai: không có @Valid cùng điểm.
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address shippingAddress;
```

**Ví dụ đúng:**

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address shippingAddress;
```

`@ConvertGroup` **không phải constraint** như `@NotBlank`: nó không tự đánh giá một giá trị hợp lệ hay không, mà chỉ thay đổi **nhóm được yêu cầu** trong một lần cascade đã tồn tại.

### 3.2. Nhiều nhóm nguồn trên một cạnh

Có thể khai báo chuyển nhóm khác nhau cho các nhóm đầu vào khác nhau:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
@ConvertGroup(from = StrictOrder.class, to = StrictAddress.class)
Address shippingAddress;
```

Mỗi luật có **nguồn `from` khác nhau**. Khi chỉ có Default đi qua, áp dụng luật đầu; khi StrictOrder đi qua, áp dụng luật sau; khi nhóm khác đi qua, giữ nguyên. Không được gắn cùng một nguồn với hai đích khác nhau.

Dạng container:

```java
@Valid
@ConvertGroup.List({
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class),
    @ConvertGroup(from = StrictOrder.class, to = StrictAddress.class)
})
Address shippingAddress;
```

Các ví dụ cần có định nghĩa interface `StrictOrder`, `StrictAddress` và class `Address` trong project. Đừng gộp nhiều group chỉ vì có thể; mapping nên phản ánh đúng nghiệp vụ của quan hệ cha–con.

## 4. Thứ tự áp dụng: chỉ một phép chuyển trên mỗi cạnh

Một câu hỏi thường gặp: nếu có hai luật `A → B` và `B → C` trên cùng thuộc tính, khi đi vào với `A`, có tự động chuyển tiếp thành `C` hay không? **Không.**

Ví dụ:

```java
@Valid
@ConvertGroup(from = A.class, to = B.class)
@ConvertGroup(from = B.class, to = C.class)
RelatedBean child;
```

Nếu nhóm đi vào cạnh là `A`, kết quả chuyển của **cạnh đó** là `B`, không phải `C`. Conversion **không lặp đến khi không còn rule**; quy tắc khớp được áp dụng một lần tại điểm cascade. Khi nhóm đầu vào là `B`, chuyển thành `C`.

Đây không phải quy tắc “lấy nhóm sau cùng” và không phụ thuộc thứ tự annotation. Việc chỉ chuyển một lần tránh việc các luật trên cùng cạnh vô tình thay đổi hợp đồng nhóm nhiều lần.

### 4.1. Tuy nhiên có thể chuyển tiếp ở cạnh sâu hơn

Một tình huống khác:

```text
Order --(@Valid, Default → DeliveryChecks)--> Address
      Address --(@Valid, DeliveryChecks → WarehouseChecks)--> Warehouse
```

Khi validate `Order` bằng `Default`:

1. Constraint ở `Order` được kiểm tra theo `Default`.
2. Đi qua `Order.address`, nhóm được đổi thành `DeliveryChecks`.
3. Constraint ở `Address` được kiểm tra theo `DeliveryChecks`.
4. Đi qua **một cạnh cascade khác** là `Address.warehouse`, nhóm `DeliveryChecks` lại được chuyển thành `WarehouseChecks`.
5. Constraint ở `Warehouse` được kiểm tra theo `WarehouseChecks`.

Điều này **không mâu thuẫn** với quy tắc “không đệ quy”: mỗi cạnh có đúng một phép chuyển, nhưng object graph có thể có nhiều cạnh và mỗi cạnh áp dụng luật riêng của mình.

**Phân biệt:** chuỗi `A → B → C` trên **cùng một cạnh** không chạy nối nhau; `A → B` trên cạnh cha–con rồi `B → C` trên **cạnh con–cháu** là tuyến cascade hợp lệ.

### 4.2. Nhóm không được đổi tại root

Một annotation `@ConvertGroup` trên `address` **không biến toàn bộ lời gọi** `validator.validate(order)` thành `validator.validate(order, DeliveryChecks.class)`. Root vẫn nhận `Default`, và các property khác của root không bị ảnh hưởng. Nhóm chỉ thay đổi khi đi qua cạnh cascade có khai báo tương ứng.

Không dùng `@ConvertGroup` như cách “ghi đè toàn cục” group trong Spring. Muốn chọn nhóm root, truyền trực tiếp vào `Validator` hoặc dùng `@Validated(Group.class)` ở vị trí Spring hỗ trợ.

## 5. Ví dụ Java 17+ chạy độc lập: so sánh có và không có conversion

Phần này dùng Jakarta Validation 3.x và Hibernate Validator 8.x làm provider. Chương trình không cần Spring MVC để chứng minh cơ chế chuẩn, gồm ba lớp:

- `Warehouse`: có `label` thuộc `Default` và `code` thuộc `WarehouseChecks`.
- `Address`: có `city` thuộc `Default`, `street` thuộc `DeliveryChecks` và quan hệ `warehouse` có `DeliveryChecks → WarehouseChecks`.
- `PlainOrder`: chỉ có `@Valid` trên `address`.
- `ConvertedOrder`: có `@Valid @ConvertGroup(Default → DeliveryChecks)` trên `address`.

Kết quả cho thấy constraint tại **hai cấp con** khác nhau được chọn theo group đi qua các cạnh.

### 5.1. Tạo pom.xml

Tạo `pom.xml` trong thư mục làm việc:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>convert-group-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

Dependency `hibernate-validator` mang theo Jakarta Validation API và các dependency transitive. Để chạy CLI mà không cài thêm Jakarta Expression Language, ví dụ dùng `ParameterMessageInterpolator` của Hibernate Validator. Đây là **API riêng của provider**; ứng dụng cần hỗ trợ EL trong message template thì phải cấu hình EL phù hợp.

### 5.2. Tệp ConvertGroupDemo.java

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class ConvertGroupDemo {

    public interface DeliveryChecks {}
    public interface WarehouseChecks {}

    public static final class Warehouse {
        @NotBlank
        private final String label;

        @NotBlank(groups = WarehouseChecks.class)
        private final String code;

        public Warehouse(String label, String code) {
            this.label = label;
            this.code = code;
        }
    }

    public static final class Address {
        @NotBlank
        private final String city;

        @NotBlank(groups = DeliveryChecks.class)
        private final String street;

        @Valid
        @ConvertGroup(
                from = DeliveryChecks.class,
                to = WarehouseChecks.class)
        private final Warehouse warehouse;

        public Address(String city, String street, Warehouse warehouse) {
            this.city = city;
            this.street = street;
            this.warehouse = warehouse;
        }
    }

    public static final class PlainOrder {
        @NotBlank
        private final String orderCode;

        @Valid
        private final Address address;

        public PlainOrder(String orderCode, Address address) {
            this.orderCode = orderCode;
            this.address = address;
        }
    }

    public static final class ConvertedOrder {
        @NotBlank
        private final String orderCode;

        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = DeliveryChecks.class)
        private final Address address;

        public ConvertedOrder(String orderCode, Address address) {
            this.orderCode = orderCode;
            this.address = address;
        }
    }

    private static void print(
            String name, Set<? extends ConstraintViolation<?>> errors) {
        List<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(name + " -> " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Address badAddress = new Address(
                    "", "", new Warehouse("", ""));

            PlainOrder plain = new PlainOrder("", badAddress);
            ConvertedOrder converted =
                    new ConvertedOrder("", badAddress);

            print("plain Default", validator.validate(plain));
            print("converted Default", validator.validate(converted));
            print("converted DeliveryChecks",
                    validator.validate(converted, DeliveryChecks.class));

            print("converted property address",
                    validator.validateProperty(converted, "address"));
            print("converted candidate address",
                    validator.validateValue(
                            ConvertedOrder.class, "address", badAddress));

            ConvertedOrder missing =
                    new ConvertedOrder("ORD-1", null);
            print("converted null address",
                    validator.validate(missing));

            ConvertedOrder valid = new ConvertedOrder(
                    "ORD-2",
                    new Address("Hanoi", "1 Main St",
                            new Warehouse("Main", "WH-001")));
            print("converted valid", validator.validate(valid));
        }
    }
}
```

Chương trình chỉ in đường dẫn vi phạm đã sắp xếp, không in thông báo đã dịch theo locale. Nhờ vậy kết quả không phụ thuộc thứ tự duyệt `Set<ConstraintViolation<?>>` hoặc ngôn ngữ của provider.

### 5.3. Lệnh chạy

Yêu cầu **JDK 17+** và **Maven**. Đặt `pom.xml` và `ConvertGroupDemo.java` trong cùng thư mục.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ConvertGroupDemo.java
java -cp ".:$CP" ConvertGroupDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ConvertGroupDemo.java
java -cp ".;$cp" ConvertGroupDemo
```

**Stdout kỳ vọng** khi chạy với bộ dependency được nêu (bỏ qua log khởi động provider nếu có):

```text
plain Default -> [address.city, address.warehouse.label, orderCode]
converted Default -> [address.street, address.warehouse.code, orderCode]
converted DeliveryChecks -> [address.street, address.warehouse.code]
converted property address -> []
converted candidate address -> []
converted null address -> [address]
converted valid -> []
```

### 5.4. Giải thích chính xác từng dòng

1. **`plain Default`:** root `orderCode=""` sai `@NotBlank`. Vì quan hệ `PlainOrder.address` chỉ có `@Valid`, `Default` đi xuống `Address` nên `city=""` sai. Khi tiếp tục xuống `Warehouse`, quy tắc chuyển nhóm ở `Address.warehouse` chỉ khớp `DeliveryChecks`, nên `Default` giữ nguyên và `Warehouse.label=""` sai. Tổng ba đường dẫn.
2. **`converted Default`:** root `orderCode=""` vẫn sai `@NotBlank`. Trên cạnh `ConvertedOrder.address`, `Default` chuyển thành `DeliveryChecks` nên `Address.street=""` sai, `city` chỉ thuộc Default không chạy trong nhánh này. Tại cạnh `Address.warehouse`, `DeliveryChecks` chuyển thành `WarehouseChecks`, nên `Warehouse.code=""` sai. Tổng ba đường dẫn, nhưng **hai đường dẫn ở bean con khác hẳn**.
3. **`converted DeliveryChecks`:** root `orderCode` chỉ thuộc Default không chạy. Conversion ở cạnh root chỉ có `Default → DeliveryChecks` nên nhóm đầu vào DeliveryChecks giữ nguyên; `Address.street` bị kiểm tra. Cạnh kế tiếp đổi DeliveryChecks thành WarehouseChecks và kiểm tra `Warehouse.code`.
4. **`converted property address`:** `validateProperty` chỉ kiểm tra constraint trực tiếp tại property `address`, ở đây `@NotNull` đạt vì address không null. Nó **không cascade** nên không nhìn thấy lỗi ở `street` hay `Warehouse.code`.
5. **`converted candidate address`:** `validateValue` cũng **không cascade**, chỉ kiểm tra candidate khác null theo `@NotNull`; trả tập rỗng.
6. **`converted null address`:** `@NotNull` trên property `address` thuộc Default phát hiện null. `@Valid` bỏ qua null; conversion không thể làm xuất hiện object con.
7. **`converted valid`:** root không blank, địa chỉ có street hợp lệ theo DeliveryChecks và Warehouse có code hợp lệ theo WarehouseChecks. Không có violation theo tuyến này.

Kết quả quan trọng: **`@ConvertGroup` đổi nhóm ở lúc cascade**, không đổi nhóm ở root, không tự chạy nested validation khi gọi API property/value và không thay thế constraint cấm `null`.

## 6. @ConvertGroup và @Validated trong Spring MVC

Spring hỗ trợ cả hai cơ chế nhưng chúng có trách nhiệm khác nhau:

- `@Validated(Group.class)` của Spring chọn **nhóm để bắt đầu validation** cho đối tượng đầu vào trong ngữ cảnh controller/service được hỗ trợ.
- `@Valid` của Jakarta kích hoạt validation trên object và **cascade** vào bean con ở vị trí được gắn.
- `@ConvertGroup` của Jakarta quyết định **chuyển nhóm khi cascade qua một property hoặc type argument cụ thể**.
- `jakarta.validation.Validator.validate(bean, groups...)` cho phép tự gọi validation cùng hành vi group/cascade mà không cần HTTP request.

### 6.1. DTO Spring MVC minh họa

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public class OrderInput {
    @NotBlank
    private String code;

    @NotNull
    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    private DeliveryAddress address;

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public DeliveryAddress getAddress() { return address; }
    public void setAddress(DeliveryAddress address) {
        this.address = address;
    }
}

interface DeliveryChecks {}

class DeliveryAddress {
    @NotBlank(groups = DeliveryChecks.class)
    private String street;

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }
}
```

Đây là **mã minh họa tích hợp**; trong ứng dụng thật đặt các kiểu ở tệp/package thích hợp, có dependency Jackson/binding và Bean Validation provider. Để tránh trùng tên, `DeliveryChecks` trong đoạn MVC là interface của project riêng, không phải một class nằm trong chương trình độc lập `ConvertGroupDemo` ở mục 5.

Với JSON:

```json
{
  "code": "ORD-1",
  "address": {
    "street": ""
  }
}
```

`@NotBlank` trên `DeliveryAddress.street` ở nhóm DeliveryChecks sẽ được xét khi root `OrderInput` được validate ở Default, nhờ `@Valid + @ConvertGroup` tại property `address`.

### 6.2. Controller chọn nhóm ban đầu

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody OrderInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ":" + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

Đây là method minh họa bên trong `@RestController`, cần import Spring MVC/`ResponseEntity`/`BindingResult` và model tương ứng. Khi validation đối tượng đầu vào được kích hoạt với nhóm mặc định, conversion ở `address` sẽ chọn nhóm DeliveryChecks cho bean con. `BindingResult` đặt ngay sau parameter tương ứng trong các chữ ký Spring hỗ trợ để đọc lỗi.

Nếu cần nhóm ban đầu riêng:

```java
@Validated(Create.class) @RequestBody OrderInput input
```

thì **root nhận Create**, không phải Default. Với `@ConvertGroup(from=Default.class, to=DeliveryChecks.class)`, không có chuyển đổi **nếu nhóm đang đi qua là Create**. Có thể:

- Định nghĩa `@ConvertGroup(from = Create.class, to = DeliveryChecks.class)` tại đúng cascade point;
- Hoặc chọn cùng lúc các nhóm cần thiết bằng `@Validated({Default.class, Create.class})` nếu hợp đồng yêu cầu, đồng thời hiểu tác động của từng nhóm;
- Hoặc thiết kế DTO riêng để tránh phức tạp.

Không suy luận “có `@ConvertGroup` thì nhóm nào đến cũng thành DeliveryChecks”. **Chỉ `from` khớp mới đổi nhóm.**

### 6.3. Khi đặt @Validated trên service

Spring service có thể dùng `@Validated` ở mức class để kích hoạt **proxy-based method validation** khi provider/`MethodValidationPostProcessor` được cấu hình. Đây là cách chọn nhóm hoặc điểm kích hoạt method validation, không phải cơ chế thay thế `@ConvertGroup` trong object graph.

Ví dụ minh họa:

```java
@Service
@Validated
public class OrderService {
    public void submit(@Valid OrderInput input) {
        // Logic nghiệp vụ chỉ chạy sau validation nếu interceptor hoạt động.
    }
}
```

Việc method này thực sự được kiểm tra phụ thuộc bean do Spring quản lý, hạ tầng method validation và lời gọi có đi qua proxy hay không. **Self-invocation** như `this.submit(input)` có thể bỏ qua proxy. Với Spring MVC 6.1+, controller còn có built-in method validation; tránh tùy tiện đặt `@Validated` ở class controller nếu muốn theo đường built-in. Luôn kiểm thử hành vi trên phiên bản Spring thực tế.

### 6.4. Lỗi binding không phải lỗi group conversion

JSON sai cú pháp, không thể deserialize một số/enum, hoặc binder không tạo được bean con sẽ gây lỗi ở **tầng HTTP conversion/binding** trước hoặc ngoài phạm vi Bean Validation. `@ConvertGroup` không có nhiệm vụ chuyển kiểu dữ liệu hay khởi tạo object liên kết.

Ví dụ JSON `{"address": null}`: nếu DTO gắn `@NotNull`, sẽ có lỗi nullability; `@ConvertGroup` không tạo ra `DeliveryAddress` để kiểm tra `street`. Với `{"address": {}}`, DTO có address tồn tại và `street=null` nên `@NotBlank(groups=DeliveryChecks.class)` có thể báo vi phạm theo tuyến cascade.

Trong production cần phân biệt JSON parse error, binding error, field violation, object-level violation và nghiệp vụ không hợp lệ để trả response phù hợp.

## 7. @ConvertGroup với List, Set, Map và phần tử container

Sau Jakarta Bean Validation 2.0, container element constraints/cascade có thể được đặt tại **type argument**. `@ConvertGroup` hỗ trợ `TYPE_USE` và có thể đi cùng `@Valid` ở vị trí phần tử muốn cascade.

### 7.1. Danh sách các bean con

Giả sử một đơn hàng có danh sách địa chỉ giao hàng:

```java
class BatchOrder {
    @NotEmpty
    List<
        @NotNull
        @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    > shippingAddresses;
}
```

Đọc từ ngoài vào trong:

1. `@NotEmpty`: **container List** phải khác null và không rỗng.
2. `@NotNull` ở type argument: **mỗi Address** khác null.
3. `@Valid` trên type argument: cascade vào từng Address hiện có.
4. `@ConvertGroup` trên **cùng type argument có `@Valid`**: đổi Default thành DeliveryChecks khi đi vào từng Address.

`@ConvertGroup` không tự áp dụng `@NotNull` cho các phần tử, không làm List phải có phần tử, và không kiểm tra các constraint trên chính List. Chúng là các trách nhiệm riêng biệt.

### 7.2. Map có key và value khác nhau

`Map<Key, Value>` có hai type arguments; có thể đặt annotation khác nhau cho key và value:

```java
class WarehouseRequest {
    @NotEmpty
    Map<
        @NotBlank String,
        @NotNull @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    > addressesByLabel;
}
```

- `@NotEmpty` kiểm tra chính Map.
- `@NotBlank` kiểm tra key (ví dụ `"home"`, `"office"`).
- `@NotNull` kiểm tra mỗi value khác null.
- `@Valid @ConvertGroup` chuyển nhóm khi cascade vào từng value Address.

Với `Map<@Valid @ConvertGroup(...) SomeKey, @Valid @ConvertGroup(...) SomeValue>`, key và value đều có thể được cascade theo quy tắc khác nhau nếu loại key cũng là bean cần validate. Đừng đặt conversion trên container ngoài với hy vọng nó tự đổi group cho một type argument tùy ý; cần chọn đúng điểm cascade và hiểu extractor.

### 7.3. Container lồng nhiều tầng

Một kiểu như `Map<String, List<Address>>` có **hai cấp container**. Ví dụ khai báo:

```java
Map<
    String,
    List<
        @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    >
> groups;
```

Khi validator có value extractor phù hợp, nó đi qua Map, List rồi cascade từng Address và chuyển nhóm ở type argument đã đánh dấu. Nếu cần List không rỗng hoặc Address không null, thêm `@NotEmpty`/`@NotNull` đúng vị trí.

Bên cạnh các extractor chuẩn, custom container `Box<T>` có thể cần một `ValueExtractor` tương ứng để Bean Validation biết cách lấy phần tử. `@ConvertGroup` không tự cung cấp extractor; nó chỉ hoạt động **sau khi hệ thống đã xác định một tuyến cascade hợp lệ**.

### 7.4. Cảnh báo về kiểu khai báo hỗn hợp

Với một số kiểu collection, có thể gặp cú pháp cũ:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
List<Address> addresses;
```

và cú pháp type-use:

```java
List<
    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    Address
> addresses;
```

Hai cách có thể dẫn tới cascade qua container theo quy tắc tương ứng; với cấu trúc generic lồng nhau, type-use thường giúp diễn đạt chính xác đối tượng nhận nhóm. **Không nên khai báo `@Valid` dư thừa vừa trên container vừa trên cùng tuyến type argument**, vì dễ gây rắc rối về metadata/cascade. Dùng một phong cách nhất quán, kiểm thử provider thực tế và ưu tiên đặt rule đúng điểm.

## 8. Group sequence, Default và conversion: thứ tự không đơn giản là varargs

Group conversion có liên hệ với `@GroupSequence` nhưng là **cơ chế khác**.

- `@GroupSequence` định nghĩa **thứ tự kiểm tra các group** và có thể dừng các group phía sau khi nhóm trước thất bại.
- `@ConvertGroup` định nghĩa **đổi group khi cascade qua một điểm**.
- Truyền `validator.validate(bean, Default.class, DeliveryChecks.class)` **không** tạo ra thứ tự; không có bảo đảm Default được chạy trước nếu không dùng sequence.

Ví dụ định nghĩa sequence:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface AllChecks {}
```

Khi yêu cầu `AllChecks`, Bean Validation xem xét nhóm thành phần theo thứ tự đã khai báo. **Group conversion được áp dụng trên nhóm sau khi group sequence được mở rộng**; `from` không thể trực tiếp trỏ tới `AllChecks` nếu `AllChecks` là group sequence.

`to` có thể trỏ tới sequence hợp lệ và sẽ được mở rộng trước khi validate bean con theo quy tắc của Jakarta Validation. Vì vậy khi debug một rule tưởng không khớp, cần kiểm tra nhóm **thực sự đang đi qua cascade sau sequence expansion**, không chỉ tên interface mà API caller truyền vào.

### 8.1. Default group sequence redefinition

Nếu một class dùng `@GroupSequence` để **định nghĩa lại Default của chính class đó**, có quy tắc cục bộ riêng; không nên giả định toàn bộ cấu hình Default ở root sẽ được truyền nguyên xi xuống bean con. Group conversion và group sequence có thể tương tác theo metadata của từng lớp.

Khi dùng cả hai cơ chế, viết integration test cho **toàn object graph**, bao gồm thứ tự và kết quả của nhóm ở bean cha/con. Không sửa `@ConvertGroup.from` theo tên sequence bằng suy đoán.

## 9. Phạm vi API: validate khác validateProperty và validateValue

`jakarta.validation.Validator` có ba phương thức quen thuộc:

```java
validator.validate(order, Default.class);
validator.validateProperty(order, "address", Default.class);
validator.validateValue(Order.class, "address", new Address(), Default.class);
```

Đoạn trên minh họa API; class `Order` và constructor `Address()` chỉ là ví dụ khái niệm, không phải code độc lập của mục 5.

**Khác biệt quyết định:**

| API | Cascade @Valid | Áp dụng @ConvertGroup | Kiểm tra constraint trực tiếp trên property |
| --- | --- | --- | --- |
| `validate(object, groups...)` | Có, khi được đánh dấu | Có, khi qua điểm cascade phù hợp | Có |
| `validateProperty(object, propertyName, groups...)` | **Không** | **Không** | Có, trên property được chọn |
| `validateValue(beanType, propertyName, candidate, groups...)` | **Không** | **Không** | Có, theo metadata property cho candidate |

Khi cần kiểm tra rule ở `Address.street` theo nhóm đích, dùng `validate(root, ...)` với cascade hoặc validate trực tiếp bean `Address` bằng nhóm mong muốn. Không kết luận “conversion không hoạt động” chỉ vì `validateProperty(root,"address")` trả tập rỗng: API này không đi sâu vào bean con.

`@ConvertGroup` cũng không phải một cách thay đổi group cho **constraint trực tiếp trên property tại root**. Nếu `@NotNull(groups=Default.class)` nằm trên `Order.address`, nó được quyết định bởi nhóm root đang được validate, không bị đổi sang nhóm đích chỉ vì có conversion ở cạnh đi xuống.

## 10. Validation lỗi và lỗi cấu hình khác nhau thế nào?

Với một DTO hợp lệ về metadata nhưng dữ liệu sai:

```java
Set<ConstraintViolation<OrderRequest>> violations =
        validator.validate(order);
```

Lời gọi trả các `ConstraintViolation` có thể chứa `getPropertyPath()` như `address.street`. Đường dẫn gắn với bean con **không đồng nghĩa annotation đặt tại bean cha**: rule `@NotBlank` thuộc Address, còn `@ConvertGroup` chỉ quyết định nhóm dùng khi vào Address.

Với annotation sai hợp đồng:

```java
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address address;
```

không có `@Valid`, provider có thể ném **`ConstraintDeclarationException`** thay vì trả `ConstraintViolation`. Đây là lỗi **cấu hình constraint**, không phải dữ liệu user không hợp lệ.

Một số lỗi cấu hình khác:

| Tình huống | Bản chất | Hướng xử lý |
| --- | --- | --- |
| Conversion thiếu `@Valid` | Khai báo không hợp lệ | Đặt `@Valid` cùng cascade point |
| Hai luật cùng `from` khác `to` | Mơ hồ luật ánh xạ | Chỉ giữ một đích cho mỗi nguồn |
| `from` trỏ tới group sequence | Không hợp lệ theo spec | Chuyển nhóm trên nhóm thành phần đã mở rộng |
| Không có value extractor phù hợp cho custom container | Không thể duyệt type argument | Đăng ký `ValueExtractor` hoặc chọn cấu trúc hỗ trợ |
| Bean con null nên không có lỗi nested | Không tồn tại object để cascade | Thêm `@NotNull` tại property nếu bắt buộc |
| `@Validated(Create.class)` nhưng chỉ định conversion từ Default | Nhóm không khớp, không chuyển | Chọn đúng `from=Create.class` hoặc thay nhóm root |
| `@NotBlank` của bean con không chạy | Constraint thuộc nhóm khác với nhóm sau conversion | Đồng bộ metadata nhóm hoặc thêm luật hợp lệ |
| Có constraint trực tiếp ở cha nhưng tưởng được convert | Conversion không thay group của cha | Chọn root group bằng Validator/`@Validated` |
| Group A→B, B→C trên cùng cạnh nhưng không thấy C | Không chaining trên một cạnh | Đặt luật ở cạnh sâu hơn nếu cần |
| Đặt `@Validated` trên nested field để cascade | `@Validated` không thay `@Valid` | Dùng `@Valid + @ConvertGroup` |
| Method validation controller/service không chạy | Không đi qua integration/proxy phù hợp | Kiểm tra Spring MVC/AOP stack, provider và invocation |
| Lỗi binding được xem là lỗi conversion | JSON parser/mapper không tạo được bean | Xử lý lỗi deserialize riêng |

Việc `ConstraintDeclarationException` được phát hiện khi bootstrap metadata hay ở lần validate đầu tiên phụ thuộc provider. Đừng bắt nó như một lỗi field do người dùng nhập để rồi trả thông điệp “dữ liệu không đúng định dạng” thay vì sửa code cấu hình.

## 11. Bẫy Spring và phương án thiết kế an toàn

### 11.1. @ConvertGroup không thay hợp đồng DTO

Khi API Create và Update có các tập field cho phép khác nhau, nhóm validation và group conversion chỉ kiểm tra **giá trị của DTO đã được bind**. Chúng không xác định field nào client được phép gửi, không ngăn mass-assignment, không kiểm tra authorization và không thay uniqueness trong database.

Nếu policy của thao tác rất khác, DTO riêng cho Create/Update đôi khi dễ hiểu hơn một DTO chứa quá nhiều marker group và conversion. Với component tái sử dụng như Address, group conversion vẫn có giá trị để giữ module con không phụ thuộc vào mọi nhóm gọi của module cha.

### 11.2. Kiểm thử hai phía của mỗi cạnh

Với một điểm `Default → DeliveryChecks`, cần test:

1. Root `Default` + child có lỗi Default nhưng **đạt DeliveryChecks**: không báo lỗi child chỉ thuộc Default.
2. Root `Default` + child có lỗi DeliveryChecks: báo lỗi child tương ứng.
3. Root `Create` không khớp `from=Default`: child nhận Create, không tự nhận DeliveryChecks.
4. Child `null`: `@Valid` bỏ qua; `@NotNull` nếu có báo lỗi ở property cha.
5. Group A→B, B→C trên **cùng cạnh**: không bị chuyển liên tiếp tới C.
6. Chuỗi hai cạnh A→B rồi B→C: kiểm tra rule ở bean cháu khi cascade hợp lệ.
7. Container List/Map có phần tử null/empty/nested bean invalid để xác nhận ràng buộc container và conversion khác nhau.
8. Có `@GroupSequence`: xác định nhóm sau expansion và thứ tự/dừng theo sequence.
9. Gọi `validateProperty`/`validateValue`: không nhầm với kiểm tra graph.
10. Spring MVC: request JSON hợp lệ về kiểu nhưng sai rule child, và request sai kiểu bị chặn ở bước binding.

Khi assert `ConstraintViolation`, không phụ thuộc thứ tự của `Set`. So sánh tập `propertyPath` và, khi cần, metadata `ConstraintDescriptor` để tránh lỗi test do message locale khác nhau. Với Map/List, đường dẫn có thể bao gồm key/index; không hard-code cách biểu diễn của mọi provider nếu không cần.

### 11.3. Lưu ý nhóm "ngược chiều" và quan hệ hai chiều

Hai converter `A→B` và `B→A` trên một cạnh không tự tạo vòng lặp conversion, vì mỗi cạnh chỉ chạy một rule. Tuy nhiên **object graph có thể chứa chu trình tham chiếu** (`Order.customer.order`...). Bean Validation có cơ chế chống lặp vô hạn theo đường duyệt/group, nhưng nên mô hình hóa cascade cần thiết và kiểm thử object graph thực để tránh chi phí thừa.

Nếu constraint trên bean con phụ thuộc vào user context hoặc database, đừng nhồi logic nặng/side effect vào custom `ConstraintValidator` chạy mỗi lần cascade. Phần lớn ràng buộc quyền truy cập/trạng thái thuộc service, có thể cần transaction và chiến lược caching riêng.

## 12. Quy trình áp dụng @ConvertGroup

Một hướng triển khai thực tế:

1. **Xác định nhóm dùng để validate bean cha.** Ví dụ `Default` cho request thông thường hoặc `Create` do controller chọn.
2. **Liệt kê constraint của bean con thuộc nhóm nào.** Ví dụ `DeliveryChecks` kiểm tra street, postal code.
3. **Chọn cạnh cần cascade.** Đánh dấu `@Valid` ở property/type argument cụ thể.
4. **Viết luật `from → to` tại chính cạnh đó.** `from` là nhóm thực đi qua cạnh; `to` là nhóm muốn dùng cho bean con.
5. **Đánh dấu nullability độc lập.** Nếu bean con không thể null, thêm `@NotNull` ở property; với collection đặt ràng buộc container và element đúng tầng.
6. **Kiểm thử cả rule trực tiếp của cha lẫn rule của con.** Chứng minh cha vẫn dùng nhóm gốc, con dùng nhóm sau mapping và các nhóm không khớp giữ nguyên.
7. **Nếu có nhiều tầng**, dùng các quy tắc khác nhau ở từng cạnh; không mong chaining các converter trên cùng cạnh.
8. **Nếu có sequence**, kiểm tra nhóm sau sequence expansion và điều kiện dừng; không dùng group sequence làm `from`.
9. **Tích hợp Spring đúng điểm** bằng `@Valid`/`@Validated`/`BindingResult` hoặc `Validator` thủ công; tách lỗi binding và nghiệp vụ.
10. **Kiểm tra metadata khi nâng cấp Jakarta/Hibernate Validator/Spring** vì có thể thay đổi đường validation và loại exception tại controller.

**Chốt ý:** `@ConvertGroup` là phép ánh xạ **nhóm dành cho đối tượng con tại một điểm `@Valid`**, không phải một constraint mới, không đổi nhóm của bean cha, không tự cascade, không tự cấm `null` và không tự biến mọi nhóm thành một nhóm đích. Cách hiểu theo **cạnh trong object graph** giúp tránh nhầm lẫn giữa `@Validated` ở điểm bắt đầu, `@Valid` để lan truyền và `@ConvertGroup` để chọn nhóm nhận ở bean con.

### Tài liệu đối chiếu

- Jakarta Bean Validation 3.0 Specification — Object graph validation, group conversion, group sequences: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.1 Specification — Group conversion (cùng nguyên tắc quy đổi): https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.0 API — `ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/convertgroup
- Hibernate Validator 8 Reference Guide — Group conversion: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — Request body: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
