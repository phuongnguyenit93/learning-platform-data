# @Valid và ý nghĩa kích hoạt kiểm tra lan truyền (cascaded validation) trong Spring

## 1. Mục tiêu học tập và vấn đề thực tế

Giả sử một API nhận đơn hàng bao gồm mã đơn, địa chỉ giao hàng và nhiều dòng sản phẩm. Kiểu dữ liệu không phẳng:

```text
CreateOrderRequest
├── code: String
├── shippingAddress: Address
│   ├── receiverName: String
│   └── city: String
└── lines: List<LineItem>
    ├── [0] sku: String, quantity: int
    └── [1] sku: String, quantity: int
```

Nếu chỉ đặt `@NotBlank` trên `Address.city`, việc kiểm tra đối tượng `CreateOrderRequest` **không mặc nhiên đi vào** `shippingAddress`. Tương tự, các ràng buộc bên trong từng `LineItem` không tự chạy khi chỉ kiểm tra đối tượng cha. Muốn trình xác thực (Bean Validation provider) đi từ đối tượng cha đến các đối tượng liên quan, ta đánh dấu **cạnh nối của đồ thị** bằng `@Valid`.

Kết thúc bài này, người học cần giải thích được:

1. `@Valid` có ý nghĩa gì và khác các constraint như `@NotNull`, `@NotBlank`, `@Positive` như thế nào.
2. Điều kiện để việc kiểm tra bắt đầu: có lời gọi `Validator.validate(...)` hoặc một integration của Spring kích hoạt validation.
3. Cách `@Valid` lan truyền sang object con, collection, container element và nhiều cấp, bao gồm trường hợp `null`.
4. Cách `@Valid` trên `@RequestBody`/`@ModelAttribute` trong Spring MVC tác động đến dữ liệu request, lỗi và phản hồi HTTP.
5. Phân biệt `@Valid`, `@Validated`, validation groups, method validation; tránh nhầm với JPA cascade.
6. Cách kiểm chứng bằng Java 17+, Hibernate Validator, JUnit và Spring MockMvc.

**Ngữ cảnh phiên bản:** Các ví dụ sử dụng `jakarta.validation.*` (Jakarta Bean Validation 3.x), Spring Framework 6+ và Spring Boot 3.x. Dự án Spring Boot 2.x dùng namespace cũ `javax.validation.*`; không trộn hai namespace trong một module.

## 2. @Valid thực sự làm gì?

`jakarta.validation.Valid` đánh dấu một tham chiếu/đường đi cho **cascaded validation**, thường được dịch là *kiểm tra lan truyền* hoặc *xác thực đệ quy*. Khi provider đang xác thực bean cha, nó đi qua phần tử được đánh dấu và kiểm tra các constraint trên bean con. Nếu bean con lại có một thuộc tính `@Valid` khác, việc duyệt tiếp tục nhiều cấp.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

class Address {
    @NotBlank
    String city;
}

class Order {
    @NotNull
    @Valid
    Address shippingAddress;
}
```

Đây là **fragment minh họa**, chưa phải chương trình Java độc lập. Khi gọi `validator.validate(order)`:

- `@NotNull` trên `shippingAddress` hỏi: tham chiếu có khác `null` hay không?
- `@Valid` trên `shippingAddress` yêu cầu kiểm tra các ràng buộc **bên trong** đối tượng `Address` khi nó tồn tại.
- `@NotBlank` trên `Address.city` mới thực sự phát hiện tên thành phố rỗng hoặc toàn khoảng trắng.
- Nếu bỏ `@Valid` ở `Order.shippingAddress`, constraint `@NotBlank` của `Address.city` không được đi tới trong lượt `validate(order)` thông thường.
- Nếu `shippingAddress == null`, provider **bỏ qua bước cascade**. `@Valid` **không tự yêu cầu non-null**; nhờ có `@NotNull` nên trường hợp vắng địa chỉ vẫn bị đánh dấu lỗi.

Không có constraint `@Valid` mang nghĩa "giá trị phải hợp lệ" một cách độc lập. Nó là chỉ dẫn **đi qua tham chiếu đến bean khác**. Một bean con không có constraint nào sẽ không xuất hiện lỗi chỉ vì được gắn `@Valid`.

### 2.1. @Valid không tự chạy khi gán trường

Ví dụ `order.setShippingAddress(address)` (hoặc tạo một object bằng `new`) chỉ thay trạng thái Java; nó **không kích hoạt** Bean Validation tức thì. Cần có một điểm gọi validation:

- Chủ động gọi `jakarta.validation.Validator.validate(order)`.
- Spring MVC bind một tham số như `@Valid @RequestBody OrderRequest` và dùng Bean Validation provider đã cấu hình.
- Một cơ chế method validation, persistence integration hoặc nền tảng khác **thực sự** gọi provider ở thời điểm phù hợp.

Nói cách khác, `@Valid` là **metadata mô tả đường lan truyền**; provider và điểm tích hợp quyết định **khi nào chạy**. Đặt annotation lên DTO rồi không bao giờ gọi/được gọi validator thì không có kiểm tra nào xảy ra.

### 2.2. @Valid khác @NotNull

| Annotation | Chức năng | Nếu đối tượng con bằng `null` |
| --- | --- | --- |
| `@Valid` | Cascade sang các constraint trong bean con | Bỏ qua cascade, không phát sinh lỗi chỉ từ `@Valid` |
| `@NotNull` | Yêu cầu chính giá trị này khác `null` | Phát sinh lỗi |
| `@NotBlank` | String phải khác null và chứa ký tự không phải whitespace | Phát sinh lỗi với `null`/`""`/`"  "` |
| `@NotEmpty` | String, Collection, Map hoặc Array được hỗ trợ phải không null/không rỗng | Phát sinh lỗi nếu null/rỗng |
| `@Size(min=1)` | Giới hạn kích thước của kiểu được hỗ trợ | `null` thường được coi là hợp lệ; kết hợp `@NotNull` nếu cần |
| `@Positive` | Giá trị số phải lớn hơn 0 | Số 0/âm bị lỗi; `null` thường được coi là hợp lệ |

Một mô hình đặt hàng thường cần `@NotNull @Valid Address shippingAddress` **đồng thời**, và `@NotEmpty List<@Valid LineItem> lines` để yêu cầu danh sách có phần tử, sau đó kiểm tra các phần tử.

## 3. Đồ thị object: mỗi cấp phải có đường @Valid

Xét ba cấp đối tượng:

```java
class Country {
    @NotBlank String isoCode;
}

class Address {
    @NotBlank String city;
    @Valid Country country;
}

class Customer {
    @Valid Address address;
}

class Order {
    @Valid Customer customer;
}
```

Đây là code rút gọn; các annotation trong fragment cần import từ `jakarta.validation.*`. Khi provider thực hiện `validator.validate(order)`, đường duyệt là:

```text
Order [được bắt đầu validate]
  |
  | @Valid trên customer
  v
Customer
  |
  | @Valid trên address
  v
Address
  |  +-- @NotBlank(city) được kiểm tra
  |
  | @Valid trên country
  v
Country
     +-- @NotBlank(isoCode) được kiểm tra
```

Bỏ `@Valid` ở **bất cứ cạnh** nào sẽ cắt đường duyệt từ cha qua cạnh đó. Ví dụ bỏ `@Valid` ở `Customer.address` thì việc gọi `validate(order)` không đi đến `Address.city` hay `Country.isoCode` theo tuyến này, dù chúng có annotation constraint.

Điều này khác hoàn toàn với chuyện từng class con tự chứa `@NotBlank`. Constraint nằm trên bean con vẫn tồn tại và sẽ chạy nếu ta **trực tiếp** gọi `validator.validate(address)`; chỉ có tuyến xuất phát từ `order` bị thiếu.

Bean Validation xây dựng một tập `ConstraintViolation` chứa đường dẫn thuộc tính từ root, ví dụ `customer.address.city` và `customer.address.country.isoCode`. Thứ tự duyệt/trả về vi phạm không nên được coi là một hợp đồng ổn định để hiển thị; khi cần response ổn định, hãy tự sắp xếp theo field/path.

### 3.1. Có vòng tham chiếu thì sao?

Đồ thị nghiệp vụ có thể quay vòng, như `Department.manager.department`. Nhà cung cấp Bean Validation tuân thủ specification phải tránh đệ quy vô hạn: một instance đã xuất hiện trong **đường duyệt hiện tại** không bị đi qua lại theo cùng đường đó. Một instance được tham chiếu từ nhiều nhánh khác nhau vẫn có thể được kiểm tra ở các đường khác. Không cần tự viết bộ phát hiện chu kỳ chỉ để `@Valid` hoạt động.

## 4. @Valid với List, Map, Optional và container element

Trong Jakarta Bean Validation hiện đại, annotation có thể đặt ở **type argument**:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.List;
import java.util.Map;
import java.util.Optional;

class LineItem {
    @NotBlank String sku;
    @Positive int quantity;
}

class Address {
    @NotBlank String city;
}

class Order {
    @NotEmpty
    List<@NotNull @Valid LineItem> lines;

    Map<String, @Valid Address> addressByType;

    Optional<@Valid Address> optionalAddress;
}
```

- `List<@Valid LineItem>`: provider đi vào từng phần tử `LineItem` để áp dụng các constraint của phần tử.
- `List<@NotNull @Valid LineItem>`: còn yêu cầu phần tử không được null. `@Valid` đơn thuần sẽ bỏ qua phần tử null.
- `@NotEmpty` trên danh sách: yêu cầu bản thân danh sách có ít nhất một phần tử, nhưng **không** thay cho kiểm tra các trường bên trong từng phần tử.
- `Map<String, @Valid Address>`: yêu cầu kiểm tra các `Address` ở **value**; không tự ràng buộc key. Có thể đặt annotation trên type argument của key nếu cần và provider có extractor phù hợp.
- `Optional<@Valid Address>`: kiểm tra bean khi `Optional` có giá trị; không biến `Optional.empty()` thành lỗi bắt buộc. Nếu muốn bắt buộc, thiết kế constraint phù hợp với model/hợp đồng.

Với container lồng nhau như `List<List<@Valid LineItem>>`, đặt `@Valid` ở type argument của lớp chứa giá trị cần cascade. Không cần làm phẳng dữ liệu để kiểm tra.

**Không đặt đồng thời `@Valid` trên một container và trên type argument tương ứng chỉ để "chắc chắn hơn"**, ví dụ tránh `@Valid List<@Valid LineItem>`. Jakarta Bean Validation specification hướng dẫn chọn **một vị trí cascade** cho cùng đường đi để tránh kiểm tra phần tử hai lần.

Một lỗi hay gặp là chỉ viết `@Valid List<LineItem>` trên **tham số trực tiếp của controller** và nghĩ toàn bộ xử lý HTTP sẽ tương đương với việc có một command object. Cơ chế Spring MVC cho các method argument kiểu collection có điều kiện riêng. Với request có nhiều phần tử, dùng một DTO bao bọc `OrderRequest` với `List<@Valid LineItem>` thường dễ thiết kế, kiểm thử và báo lỗi hơn.

## 5. Ví dụ thực thi Java 17+: quan sát cascade thực tế

Để nhìn thấy việc có/bỏ `@Valid` thay đổi kết quả thế nào, ta tạo một chương trình dùng **Jakarta Bean Validation và Hibernate Validator**. Khác với ví dụ Java thuần, annotation/specification cần thư viện provider ở runtime; chỉ chạy `javac` không có classpath thì không đủ.

Tạo cấu trúc thư mục:

```text
cascade-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── CascadeValidationDemo.java
```

### 5.1. pom.xml (Maven, Java 17)

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cascade-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Bản cấu hình này dùng phiên bản thư viện cố định để ví dụ có thể tái hiện. Trong dự án Spring Boot thực tế, nên để BOM/dependency management của Boot chọn phiên bản tương thích thay vì thêm bản này một cách máy móc.

### 5.2. CascadeValidationDemo.java

```java
package example;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public final class CascadeValidationDemo {

    public record Address(@NotBlank String city) {}

    public record LineItem(
            @NotBlank String sku,
            @Positive int quantity) {}

    public record OrderRequest(
            @NotBlank String code,
            @NotNull @Valid Address address,
            @NotEmpty List<@Valid LineItem> lines) {}

    // Có constraint trên address nhưng KHÔNG có @Valid.
    public record OrderWithoutCascade(@NotNull Address address) {}

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            OrderRequest invalid = new OrderRequest(
                    "ORD-7",
                    new Address(" "),
                    List.of(
                            new LineItem("", 2),
                            new LineItem("BOOK", 1)));

            Set<ConstraintViolation<OrderRequest>> failures =
                    validator.validate(invalid);

            boolean hasAddressError = failures.stream().anyMatch(
                    v -> v.getPropertyPath()
                            .toString().equals("address.city"));

            boolean hasLineError = failures.stream().anyMatch(
                    v -> v.getPropertyPath()
                            .toString().endsWith(".sku"));

            System.out.println("violations=" + failures.size());
            System.out.println("addressError=" + hasAddressError);
            System.out.println("lineError=" + hasLineError);

            OrderWithoutCascade withoutCascade =
                    new OrderWithoutCascade(new Address(" "));

            System.out.println("withoutCascade="
                    + validator.validate(withoutCascade).size());

            OrderRequest missingAddress = new OrderRequest(
                    "ORD-8", null, List.of(new LineItem("BOOK", 1)));

            System.out.println("nullAddress="
                    + validator.validate(missingAddress).size());
        }
    }
}
```

Chạy ở thư mục `cascade-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.CascadeValidationDemo
```

Các dòng được in bởi `System.out.println` (provider/build tool có thể phát log riêng):

```text
violations=2
addressError=true
lineError=true
withoutCascade=0
nullAddress=1
```

Giải thích từng kết quả:

- `violations=2`: `address.city` chỉ chứa khoảng trắng, `lines[0].sku` rỗng; cả hai bị `@NotBlank` từ chối. `LineItem.quantity` hợp lệ và `lines` không rỗng.
- `addressError=true` và `lineError=true`: đường dẫn từ root cho thấy provider đã **đi vào object con**. Với Hibernate Validator, path phần tử list thường là `lines[0].sku`.
- `withoutCascade=0`: `address` của `OrderWithoutCascade` khác null nên `@NotNull` pass; do **thiếu `@Valid`**, constraint trên `Address.city` không được chạy từ root này.
- `nullAddress=1`: object `address` bị null; `@Valid` bỏ qua cascade, nhưng `@NotNull` báo thiếu giá trị. Những trường khác đều hợp lệ.

`ValidatorFactory` có thể dùng chung theo cấu hình ứng dụng; `Validator` thường được chia sẻ và gọi nhiều lần. Ví dụ CLI tạo factory một lần và đóng lúc kết thúc. Trong Spring Boot, thông thường framework quản lý validator bean giúp tránh tự tạo factory mỗi request.

## 6. Kích hoạt @Valid tại điểm vào Spring MVC

Ví dụ thực tế sau dùng Spring Boot 3.x, Spring Web MVC và Bean Validation provider. Với Maven được quản lý bởi Spring Boot, các dependency cần thiết là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Đây là **fragment dependency cho một ứng dụng Spring Boot đã có `pom.xml`/BOM**, không phải một `pom.xml` độc lập. Lớp DTO và controller dưới đây thuộc dự án Boot đã có entrypoint Spring Boot và component scan phù hợp.

### 6.1. Các DTO cho HTTP request

**File `src/main/java/com/example/orders/Address.java`:**

```java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String receiverName,
        @NotBlank String city) {}
```

**File `src/main/java/com/example/orders/LineItem.java`:**

```java
package com.example.orders;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record LineItem(
        @NotBlank String sku,
        @Positive int quantity) {}
```

**File `src/main/java/com/example/orders/CreateOrderRequest.java`:**

```java
package com.example.orders;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String code,
        @NotNull @Valid Address shippingAddress,
        @NotEmpty List<@NotNull @Valid LineItem> lines) {}
```

Chú ý hai vị trí:

- `@NotNull @Valid Address shippingAddress`: vừa yêu cầu có địa chỉ, vừa kiểm tra `receiverName`/`city` trong địa chỉ.
- `@NotEmpty List<@NotNull @Valid LineItem> lines`: yêu cầu có dòng hàng, mỗi dòng không null, và kiểm tra `sku`/`quantity` ở từng dòng. Không đặt `@Valid` thêm một lần lên chính field `lines` nếu đã cascade ở type argument `LineItem`.

### 6.2. Controller để kích hoạt validation

**File `src/main/java/com/example/orders/OrderController.java`:**

```java
package com.example.orders;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @PostMapping("/orders")
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateOrderRequest request) {

        // Trong ứng dụng thật: chuyển sang service sau khi validate.
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

Giải thích hai vị trí `@Valid` khác nhau:

1. **`@Valid` tại tham số controller**: là điểm yêu cầu Spring MVC xác thực `CreateOrderRequest` sau khi body được Jackson deserialize. Nếu thiếu nó (và không có cấu hình/validation khác làm điều tương tự), MVC không mặc nhiên duyệt constraint trong DTO.
2. **`@Valid` tại `CreateOrderRequest.shippingAddress` hoặc ở type argument `LineItem`**: định nghĩa những nhánh mà provider phải đi vào **sau khi việc validate root đã bắt đầu**.

Vì vậy, nhiều ứng dụng cần `@Valid` ở **cả điểm vào request** và **các association nằm sâu trong DTO**, nhưng hai annotation đảm nhiệm **hai nhiệm vụ khác nhau**.

### 6.3. Request hợp lệ và request sai

Request hợp lệ:

```http
POST /orders
Content-Type: application/json

{
  "code": "ORD-7",
  "shippingAddress": {
    "receiverName": "An",
    "city": "Ha Noi"
  },
  "lines": [
    { "sku": "BOOK-1", "quantity": 2 }
  ]
}
```

Với controller trên, kết quả mong đợi là **HTTP 201 Created, body rỗng**. Ví dụ này chỉ biểu diễn hành vi khi validation thành công; nó chưa lưu đơn hàng.

Request vi phạm nhiều cấp:

```http
POST /orders
Content-Type: application/json

{
  "code": "ORD-7",
  "shippingAddress": {
    "receiverName": "An",
    "city": " "
  },
  "lines": [
    { "sku": "", "quantity": 0 }
  ]
}
```

Kết quả mong đợi: Spring MVC từ chối request, thường là **HTTP 400 Bad Request**. Các lỗi có thể mang property path `shippingAddress.city`, `lines[0].sku` và `lines[0].quantity`.

Nếu request chỉ có `"shippingAddress": null`, lỗi `@NotNull` của field cha xuất hiện, còn constraints trong Address **không được kiểm tra** vì đối tượng con không tồn tại.

Nếu danh sách `lines` là `[]` hoặc `null`, `@NotEmpty` đánh dấu lỗi; không có phần tử nào để cascade. Với một phần tử `null`, `@NotNull` đặt ở type argument đánh dấu lỗi tại phần tử đó.

**Hình thức response JSON lỗi không cố định**: phụ thuộc Spring Boot/Spring Framework version, cấu hình Problem Details và `@ControllerAdvice`. Chỉ suy ra status và nội dung `BindingResult`/exception từ cấu hình đã biết, không hardcode một error JSON chung cho mọi ứng dụng.

## 7. Spring MVC báo lỗi ở đâu?

### 7.1. Binding, validation và handler

Luồng phổ biến với `@RequestBody`:

```text
JSON request
    |
    v
Jackson deserialize -> CreateOrderRequest
    |
    v
Spring MVC yêu cầu validation do @Valid trên tham số
    |
    v
Bean Validation provider kiểm tra constraint ở root
    |
    +--> theo @Valid shippingAddress -> Address
    |
    +--> theo @Valid LineItem -> từng LineItem
    |
    v
  Có violation?
     |                    |
    Không                 Có
     |                    |
 gọi controller     thông thường HTTP 400
```

Sai kiểu dữ liệu lúc deserialize (ví dụ `quantity: "nonsense"` khi Jackson không chuyển được sang int) có thể phát sinh lỗi **trước khi đến** Bean Validation. `@Valid` không sửa JSON sai kiểu và không phải bộ parser.

### 7.2. Các exception quan trọng

Trong Spring MVC hiện đại:

- Với validation **đối tượng tham số** `@Valid @RequestBody` hoặc `@Valid @ModelAttribute` thông thường, lỗi có thể đi qua `MethodArgumentNotValidException` khi không có `BindingResult`/`Errors` ngay sau tham số.
- Khi method cần **method validation** vì có constraint đặt trực tiếp lên tham số (như `@Min`, `@NotBlank`) hoặc return value, Spring MVC 6.1+ có thể dùng `HandlerMethodValidationException`. Method validation bao gồm cả kiểm tra nested được khai báo bằng `@Valid`.
- `@Valid` **không phải constraint annotation**: chỉ gắn `@Valid` tự nó không buộc Spring MVC phải chuyển sang method validation.
- Với `@ModelAttribute` và `BindingResult`, controller có thể nhận lỗi rồi tự trả giao diện hoặc thông điệp. Đặt `BindingResult` **ngay sau** đối tượng được bind/validate nếu muốn xử lý lỗi trong method; không đặt sau một tham số khác.

Không suy ra mọi loại lỗi validation đều có cùng exception; test đường controller cụ thể, đặc biệt khi có constraints trên method parameter.

### 7.3. Bean Validation so với Spring Validator

Jakarta Bean Validation dùng `jakarta.validation.Validator` và constraint annotations như `@NotBlank`; Spring cũng có giao diện `org.springframework.validation.Validator` và `Errors`. `LocalValidatorFactoryBean` là cầu nối quan trọng để Spring tích hợp Bean Validation provider vào data binding.

Nếu Spring MVC có Bean Validation provider trong classpath và cấu hình chuẩn, MVC có thể đăng ký validator toàn cục. Trong Spring Boot, dependency `spring-boot-starter-validation` là cách phổ biến để cung cấp provider. Chỉ có API annotations mà thiếu provider/configuration phù hợp thì không thể coi các validation đã được chạy đầy đủ.

## 8. Kiểm thử tích hợp bằng MockMvc

Một bộ test cần chứng minh **cả** kích hoạt tại controller lẫn đường cascade vào object lồng nhau. Các file dưới đây giả định những DTO/controller ở mục 6 và một ứng dụng Spring Boot đã được cấu hình đúng.

**File `src/test/java/com/example/orders/OrderControllerTest.java`:**

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectsInvalidNestedFields() throws Exception {
        String json = """
                {
                  "code": "ORD-7",
                  "shippingAddress": {
                    "receiverName": "An",
                    "city": " "
                  },
                  "lines": [
                    { "sku": "", "quantity": 0 }
                  ]
                }
                """;

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isBadRequest())
                .andExpect(result -> {
                    assertTrue(
                            result.getResolvedException()
                                instanceof MethodArgumentNotValidException);
                    var ex = (MethodArgumentNotValidException)
                            result.getResolvedException();
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("shippingAddress.city"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("lines[0].sku"));
                    assertTrue(ex.getBindingResult()
                            .hasFieldErrors("lines[0].quantity"));
                });
    }

    @Test
    void acceptsValidNestedFields() throws Exception {
        String json = """
                {
                  "code": "ORD-8",
                  "shippingAddress": {
                    "receiverName": "An",
                    "city": "Ha Noi"
                  },
                  "lines": [
                    { "sku": "BOOK-1", "quantity": 1 }
                  ]
                }
                """;

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andExpect(status().isCreated());
    }
}
```

`@WebMvcTest` cần dependency test tương thích (thường `spring-boot-starter-test`), và môi trường test phải thực sự có Bean Validation provider. Test này kiểm tra field path từ tầng HTTP thay vì chỉ kiểm tra một annotation có mặt trong source.

Dùng một test khác với `shippingAddress: null` để chứng minh `@NotNull` được áp dụng tại field cha. Dùng thêm `lines: []` để chứng minh `@NotEmpty` hoạt động độc lập với cascade các phần tử. Có thể thử tạm bỏ `@Valid` trên association trong môi trường thực hành để quan sát nested field error biến mất, nhưng không đưa phiên bản thiếu validation vào hệ thống thật.

## 9. Phân biệt @Valid, @Validated và method validation

Hai annotation cùng xuất hiện trong dự án Spring nhưng mục đích khác nhau.

| Tình huống | @Valid (Jakarta) | @Validated (Spring) |
| --- | --- | --- |
| Request DTO `@RequestBody` | Kích hoạt validation root trong MVC, mặc định nhóm `Default` | Cũng hỗ trợ validate và **chọn group** nếu truyền các group |
| Trường object con | Dùng để cascade sâu vào bean con | Không thay thế cơ chế cascade của `@Valid` |
| Container element `List<@Valid Item>` | Có hỗ trợ trong Jakarta Bean Validation | Không dùng `@Validated` để đánh dấu type argument thay `@Valid` |
| Service bean | `@Valid` trên method parameter mô tả cascade **khi method validation được kích hoạt** | `@Validated` ở cấp bean thường dùng để bật AOP method validation trong Spring |
| Chọn nhóm validation | `@Valid` không có tham số group | `@Validated(Create.class)` dùng để chọn group ở điểm vào Spring |

### 9.1. Vì sao @Valid trên service parameter có thể chưa chạy?

```java
import jakarta.validation.Valid;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class OrderService {
    public void submit(@Valid CreateOrderRequest request) {
        // Logic xử lý sau khi method validation thành công.
    }
}
```

Đây là fragment của dự án Spring có method validation infrastructure. Ở các Spring bean thông thường, cơ chế Spring AOP cần được cấu hình/đăng ký; gọi service **qua Spring proxy** thì các constraints trên method argument được kiểm tra. Gọi trực tiếp `new OrderService()` hay self-invocation nội bộ qua `this.submit(...)` có thể bỏ qua proxy. Vì vậy **chỉ có `@Valid` trên một method Java bình thường không tự làm method validation chạy**.

Spring MVC 6.1+ có built-in method validation riêng cho controller, không cần AOP method-validation proxy ở những trường hợp thích hợp. Đừng trộn lẫn quy tắc của service bean với cơ chế xử lý handler method của MVC. Khi chọn built-in method validation của MVC, cần lưu ý annotation `@Validated` ở cấp controller có thể khiến method validation đi qua AOP proxy thay vì cơ chế MVC tích hợp.

### 9.2. Validation groups lan truyền thế nào?

Các constraint không chỉ có loại mà còn có **group**. Nếu không chọn group, provider mặc định kiểm tra `jakarta.validation.groups.Default`. Khi đi qua `@Valid`, group đang xét được truyền xuống bean con **trừ khi** có quy tắc chuyển group.

Ví dụ:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

interface FullCheck {}

class Detail {
    @NotBlank(groups = FullCheck.class)
    String externalCode;
}

class Request {
    @Valid
    @ConvertGroup(from = Default.class, to = FullCheck.class)
    Detail detail;
}
```

Khi xác thực `Request` theo nhóm `Default`, `@ConvertGroup` đổi nhóm cho nhánh `detail` thành `FullCheck`, nên `Detail.externalCode` được kiểm tra. Nếu không có `@ConvertGroup` và chỉ validate `Default`, ràng buộc khai báo **chỉ trong `FullCheck`** sẽ không được chạy.

`@Valid` không tự chuyển tất cả group thành `Default` hoặc `FullCheck`; nó truyền group theo đúng chính sách. Trong Spring MVC, `@Validated(FullCheck.class)` tại parameter là một cách chỉ định nhóm áp dụng cho root. Với các quy tắc phức tạp, test rõ group truyền qua từng nhánh.

## 10. Những việc @Valid không làm

- **Không quyết định dữ liệu đầu vào có hợp lệ về cú pháp JSON hay không.** Jackson/data binder phải tạo được object trước.
- **Không tự đảm bảo object/collection khác null.** Cần `@NotNull`/`@NotEmpty` hoặc constraint tương đương.
- **Không thay cho constraint của bean con.** Một field có `@Valid` nhưng các thuộc tính con không có constraint tương ứng thì không có lỗi để báo.
- **Không tự kiểm tra một nested object chỉ vì class của nó chứa annotation.** Phải có một đường đi `@Valid` từ điểm đang được validate.
- **Không tự mã hóa hay lọc dữ liệu để chống tấn công.** Validation không thay thế authorization, kiểm tra nghiệp vụ, kiểm soát quyền, escaping và prepared SQL.
- **Không giống JPA cascade.** `@Valid` truyền quá trình kiểm tra constraint trong object graph; `CascadeType.PERSIST`, `MERGE`, `REMOVE` của JPA quyết định việc quản lý entity. Một cái không tự bật cái kia.
- **Không phải lời hứa mọi nơi cùng validate.** Controller, service, batch job, message consumer và persistence path có thể khác điểm kích hoạt; kiểm thử riêng những điểm entry thực tế.
- **Không đảm bảo thứ tự lỗi.** Bean Validation trả về tập vi phạm; không dựa vào thứ tự `Set<ConstraintViolation<?>>` để tạo thứ tự hiển thị cố định.

## 11. Ma trận kiểm thử gợi ý

Với DTO `CreateOrderRequest` ở mục 6, dùng ma trận sau để tránh bỏ sót:

| Trường hợp | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Cấu trúc hợp lệ | Address và LineItem đều hợp lệ | Validation pass |
| Root sai | `code = ""` | Lỗi `code` do `@NotBlank` |
| Association null | `shippingAddress = null` | Lỗi `shippingAddress` do `@NotNull` |
| Nested field sai | `shippingAddress.city = " "` | Lỗi `shippingAddress.city` do cascade `@Valid` |
| Container null | `lines = null` | Lỗi `lines` do `@NotEmpty` |
| Container rỗng | `lines = []` | Lỗi `lines` do `@NotEmpty` |
| Item null | `lines = [null]` | Lỗi phần tử do `@NotNull` tại type argument |
| Nested item sai | `lines[0].sku = ""` | Lỗi `lines[0].sku` |
| Số lượng sai | `lines[0].quantity = 0` | Lỗi `lines[0].quantity` |
| Hai phần tử, chỉ một sai | `lines[1].sku = ""` | Lỗi tại phần tử thứ hai, không áp lên phần tử hợp lệ |
| Nhiều cấp nested | Bean con lại có một field `@Valid` | Constraint ở tầng sâu được kiểm tra |
| Thiếu annotation trên association | Bỏ `@Valid` trên nhánh cần thử trong test độc lập | Các constraint sâu trên nhánh ấy không được đi tới |
| Request JSON sai kiểu | `quantity = "abc"` | Lỗi deserialize/binding có thể xuất hiện trước validation |
| Service không qua proxy | Gọi `new Service()` | Không tự chạy method validation chỉ nhờ annotation |

Để test ổn định, assert **tên field/property path, số lượng hoặc nhóm lỗi cần thiết và status HTTP**, tránh assert toàn bộ thông báo tiếng Anh vì validation message có thể thay đổi theo locale/message bundle.

## 12. Lỗi phổ biến và cách khắc phục

1. **Đặt `@NotBlank` trên bean con nhưng quên `@Valid` ở bean cha:** thêm `@Valid` đúng đường tham chiếu; test path từ root.
2. **Có `@Valid` ở bean con nhưng quên `@Valid` tại tham số controller:** thêm `@Valid @RequestBody` hoặc `@Validated` tại điểm vào phù hợp để MVC kích hoạt validation.
3. **Tin rằng `@Valid` cũng yêu cầu trường con bắt buộc:** thêm `@NotNull`, và thêm `@NotEmpty` nếu container không được rỗng.
4. **Chỉ kiểm tra danh sách bằng `@NotEmpty`:** dùng `List<@Valid LineItem>` để kiểm tra mỗi phần tử; thêm `@NotNull` cho từng phần tử nếu cần.
5. **Đặt `@Valid` cả container lẫn type argument:** chọn một vị trí cascade để tránh lặp kiểm tra.
6. **Dùng import `javax.validation.Valid` trong dự án Spring Boot 3+:** đổi sang `jakarta.validation.Valid` và bảo đảm dependency Jakarta tương thích.
7. **Chỉ thêm validation API, thiếu provider runtime:** dùng provider như Hibernate Validator, hoặc starter validation của Spring Boot.
8. **Giả định test controller chắc chắn kiểm tra service method:** method validation cần cơ chế kích hoạt riêng; test service qua Spring proxy hoặc gọi `Validator` phù hợp.
9. **Viết `@Valid` trên collection parameter root rồi trông chờ hành vi như DTO:** kiểm tra điều kiện Spring MVC, cân nhắc command object wrapper để báo lỗi rõ.
10. **Tin rằng `@Valid` và `@Validated` hoàn toàn đồng nghĩa:** `@Validated` còn hỗ trợ validation groups và method validation trong Spring.
11. **Nhầm cascade validation với cascade persistence:** đây là hai cơ chế độc lập.
12. **Chỉ assert HTTP 400:** kiểm tra thêm field path như `shippingAddress.city` và `lines[0].sku` để chứng minh validation thật sự đã lan xuống con.

## 13. Tóm tắt quy tắc triển khai

1. Bắt đầu ở **điểm kích hoạt validation**: `Validator.validate(root)`, `@Valid @RequestBody`, `@Validated` hoặc cơ chế phương thức được cấu hình.
2. Đặt constraint trên **giá trị cần kiểm tra** (`@NotBlank`, `@Positive`...) và đặt `@Valid` trên **đường tham chiếu tới bean con**.
3. Kết hợp `@NotNull`/`@NotEmpty` để xử lý **thiếu object** và **container rỗng**; `@Valid` chỉ cascade khi phần tử tồn tại.
4. Với List/Map/Optional, dùng container element annotations như `List<@Valid LineItem>`; không gắn trùng `@Valid` trên cả container và cùng type argument.
5. Dùng `jakarta.validation.*` cho Spring Boot 3+, xác nhận provider chạy và test cả bean-level lẫn MVC-level.
6. Khi có method constraints/groups, hiểu sự khác nhau giữa `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `@Validated`, và validation qua Spring proxy.
7. Chứng minh bằng test rằng một lỗi **sâu trong object graph** được phát hiện theo đúng path, kể cả khi root có vẻ hợp lệ.

### Tài liệu tham khảo

- [Jakarta Bean Validation 3.0 Specification — Object graph validation và container element cascade](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).
- [Spring Framework — Validation for @RequestMapping methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html).
- [Spring Framework — Configure a Validator for Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html).
- [Spring Framework — Java Bean Validation và Method Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
- [Hibernate Validator 8 Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/).
