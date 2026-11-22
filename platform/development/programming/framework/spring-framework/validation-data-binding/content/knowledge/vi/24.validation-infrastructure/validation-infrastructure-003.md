# TraversableResolver và giới hạn duyệt thuộc tính

## 1. Vấn đề: validation có được phép đọc và đi sâu tới đâu?

Trong Jakarta Bean Validation, khi gọi `Validator#validate(bean)` hoặc khi Spring kích hoạt Bean Validation qua `@Valid`/`@Validated`, provider kiểm tra constraint trên từng thuộc tính của đối tượng. Nếu một thuộc tính được đánh dấu `@Valid`, provider còn có thể tiếp tục kiểm tra đối tượng con (cascaded validation).

Không phải lúc nào việc đọc một thuộc tính hoặc duyệt sâu vào đối tượng con cũng phù hợp. Ví dụ: một entity JPA có quan hệ `LAZY`; đọc quan hệ chưa được nạp có thể khiến ứng dụng thực hiện truy vấn SQL ngoài ý muốn. Hoặc một luồng kiểm tra chỉ muốn đánh giá các constraint trực tiếp trên một thuộc tính nhưng không muốn đi tiếp vào các object liên kết.

`jakarta.validation.TraversableResolver` là hợp đồng hạ tầng để provider quyết định **có được tiếp cận trạng thái của property** và **có được cascade qua property đó**.

Cần phân biệt rõ:

- `ConstraintValidator` kiểm tra *giá trị* và thường trả kết quả hợp lệ/không hợp lệ.
- `@Valid` đánh dấu vị trí cần cascade sang giá trị bên trong.
- `TraversableResolver` quyết định provider *có được kiểm tra/duyệt* vị trí đó hay không.
- Spring `DataBinder`/Jackson chuyển dữ liệu đầu vào thành object; `TraversableResolver` không điều khiển quá trình binding.
- JPA `CascadeType.PERSIST/REMOVE` quản lý thao tác persistence; không đồng nghĩa với Bean Validation `@Valid`.

## 2. Hai quyết định độc lập trong cùng giao diện

Chữ ký API trong Jakarta Validation 3.x:

```java
package jakarta.validation;

import java.lang.annotation.ElementType;

public interface TraversableResolver {
    boolean isReachable(
        Object traversableObject,
        Path.Node traversableProperty,
        Class<?> rootBeanType,
        Path pathToTraversableObject,
        ElementType elementType
    );

    boolean isCascadable(
        Object traversableObject,
        Path.Node traversableProperty,
        Class<?> rootBeanType,
        Path pathToTraversableObject,
        ElementType elementType
    );
}
```

Đây là **chữ ký API để đọc hiểu**, không phải file Java cần tạo; interface đã được cung cấp bởi thư viện Jakarta Validation.

### `isReachable(...)`: có được tiếp cận property?

Provider gọi `isReachable` trước khi cần truy cập property để đánh giá constraint hoặc cascade.

- Trả `true`: property có thể được đọc và đánh giá theo các constraint/`@Valid` hiện có.
- Trả `false`: property **không được truy cập để thực hiện validation**, constraint gắn trực tiếp trên property đó bị bỏ qua và không có cascade qua property đó.

Ví dụ, nếu `@NotNull` đặt trên property nhưng `isReachable` trả `false`, provider không tạo violation `@NotNull` cho property ấy. Điều này chỉ có nghĩa là *chưa kiểm tra*, không có nghĩa dữ liệu đã hợp lệ.

### `isCascadable(...)`: có được đi tiếp qua `@Valid`?

Provider chỉ hỏi `isCascadable` khi property **đã reachable** và là vị trí cần cascade qua `@Valid`. Vì thế, với cùng bộ đối số, `isReachable` được xét trước `isCascadable`.

- Trả `true`: cho phép đi sâu vào object con theo quy tắc Bean Validation.
- Trả `false`: dừng việc cascade ở property đó, **nhưng constraint trực tiếp trên property vẫn được đánh giá** vì property reachable.

Ví dụ với `@NotNull @Valid Address deliveryAddress`: khi `isReachable=true` và `isCascadable=false`, trường `deliveryAddress=null` vẫn vi phạm `@NotNull`; nếu `deliveryAddress` là object không null, các constraint bên trong `Address` không được kiểm tra qua đường cascade này.

| Kết quả resolver | Constraint trực tiếp trên property | Cascade qua `@Valid` |
| --- | --- | --- |
| `isReachable=false` | Bỏ qua | Bỏ qua, không cần gọi `isCascadable` |
| `isReachable=true`, không có `@Valid` | Có thể kiểm tra | Không có cascade |
| `isReachable=true`, `isCascadable=false` | Có thể kiểm tra | Không |
| `isReachable=true`, `isCascadable=true` | Có thể kiểm tra | Có, khi giá trị/metadata cho phép |

Bảng mô tả **quyền truy cập của validation provider**, không khẳng định provider nhất thiết gọi resolver đúng một lần cho mỗi field. Engine có thể cache hoặc tối ưu số lượt gọi.

## 3. Đọc đúng năm tham số

Hai phương thức có cùng năm tham số:

| Tham số | Diễn giải |
| --- | --- |
| `traversableObject` | Object đang *sở hữu* property. Có thể là `null` khi kiểm tra qua `validateValue(...)`. |
| `traversableProperty` | `Path.Node` biểu diễn property sắp xét; `getName()` thường trả tên như `"deliveryAddress"`. |
| `rootBeanType` | Class gốc được validate; với executable validation là class khai báo method/constructor được validate. |
| `pathToTraversableObject` | Đường từ gốc đến object sở hữu property, **chưa cộng thêm property** đang xét. |
| `elementType` | `ElementType.FIELD` hoặc `ElementType.METHOD` cho vị trí constraint được khai báo. |

Khi owner là chính object gốc, đường đi tới owner là đường root (node đầu có tên `null` theo đặc tả). Với object lồng sâu, đường dẫn giúp phân biệt hai property trùng tên nhưng xuất hiện ở các nhánh khác nhau. Nếu dùng `traversableProperty.getName()` để định nghĩa chính sách, nên kiểm tra cả loại owner hoặc ngữ cảnh, thay vì chặn tất cả property cùng tên trên mọi class.

Có hai phạm vi cần lưu ý:

1. Các object gốc được chuyển trực tiếp vào `validate(...)` không bị loại khỏi validation bằng bộ lọc property này.
2. Giá trị tham số method/constructor và return value ở cấp trực tiếp cũng không đi qua resolver; **những property bên trong object được cascade từ các giá trị ấy** vẫn chịu kiểm tra reachability/cascadability.

Đừng dereference `traversableObject` khi nó có thể `null`. Đừng nhầm `pathToTraversableObject` với `ConstraintViolation#getPropertyPath()`: một cái là ngữ cảnh của callback, một cái là đường dẫn tới lỗi đã được ghi nhận.

## 4. Luồng đánh giá property

Giả sử object có cấu trúc:

```text
Checkout
├── customerName: @NotBlank
├── internalCode: @NotBlank            ← có thể chặn reachability
└── deliveryAddress: @NotNull @Valid  ← có thể chặn cascade
    └── street: @NotBlank
```

Với mỗi property cần xử lý, provider có thể thực hiện theo thứ tự logic:

1. Hỏi `isReachable`. Nếu `false`, dừng validation đối với property và nhánh cascade bắt đầu từ property đó.
2. Nếu reachable, xử lý các constraint trực tiếp trong nhóm validation đang chạy.
3. Nếu property có `@Valid` và có thể cascade, hỏi `isCascadable`.
4. Nếu `isCascadable=true`, kiểm tra object/nhánh con theo hợp đồng Bean Validation.

Provider có thể tối ưu hóa hoặc thay đổi thứ tự xử lý giữa các property; thứ tự trên là quan hệ phụ thuộc giữa reachability, constraint và cascaded validation, không phải thứ tự event callback cần dựa vào để viết nghiệp vụ.

## 5. Ví dụ Java 17 chạy độc lập

Ví dụ bên dưới dùng Jakarta Validation với Hibernate Validator để chứng minh:

- Một property *unreachable* sẽ không tạo lỗi từ constraint gắn trên chính nó.
- Một property *non-cascadable* vẫn được kiểm tra constraint trực tiếp, nhưng không kiểm tra object con.

Tạo hai file:

```text
traversal-example/
├── pom.xml
└── src/main/java/demo/validation/TraversalExample.java
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>traversal-example</artifactId>
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
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

**`TraversalExample.java`**

```java
package demo.validation;

import jakarta.validation.Configuration;
import jakarta.validation.Path;
import jakarta.validation.TraversableResolver;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.lang.annotation.ElementType;
import java.util.List;

public final class TraversalExample {

    static final class Address {
        @NotBlank
        private final String street;

        Address(String street) {
            this.street = street;
        }
    }

    static final class Checkout {
        @NotBlank
        private final String customerName;

        @NotBlank
        private final String internalCode;

        @NotNull
        @Valid
        private final Address deliveryAddress;

        Checkout(String customerName, String internalCode, Address address) {
            this.customerName = customerName;
            this.internalCode = internalCode;
            this.deliveryAddress = address;
        }
    }

    // Chính sách bất biến; ủy quyền các property còn lại cho resolver mặc định.
    static final class LimitedResolver implements TraversableResolver {
        private final TraversableResolver delegate;

        LimitedResolver(TraversableResolver delegate) {
            this.delegate = delegate;
        }

        @Override
        public boolean isReachable(
                Object traversableObject, Path.Node traversableProperty,
                Class<?> rootBeanType, Path pathToTraversableObject,
                ElementType elementType) {

            if (traversableObject instanceof Checkout
                    && "internalCode".equals(traversableProperty.getName())) {
                return false;
            }
            return delegate.isReachable(
                traversableObject, traversableProperty, rootBeanType,
                pathToTraversableObject, elementType);
        }

        @Override
        public boolean isCascadable(
                Object traversableObject, Path.Node traversableProperty,
                Class<?> rootBeanType, Path pathToTraversableObject,
                ElementType elementType) {

            if (traversableObject instanceof Checkout
                    && "deliveryAddress".equals(traversableProperty.getName())) {
                return false;
            }
            return delegate.isCascadable(
                traversableObject, traversableProperty, rootBeanType,
                pathToTraversableObject, elementType);
        }
    }

    private static void show(String label, Validator validator, Checkout item) {
        List<String> errors = validator.validate(item).stream()
            .map(v -> v.getPropertyPath() + ":" +
                v.getConstraintDescriptor().getAnnotation()
                    .annotationType().getSimpleName())
            .sorted()
            .toList();

        System.out.println(label + " => " +
            (errors.isEmpty() ? "OK" : String.join(", ", errors)));
    }

    public static void main(String[] args) {
        Checkout nestedInvalid = new Checkout("", "", new Address(""));
        Checkout missingAddress = new Checkout("", "", null);

        try (ValidatorFactory normal = Validation.buildDefaultValidatorFactory()) {
            Configuration<?> config = Validation.byDefaultProvider().configure();

            TraversableResolver defaultResolver =
                config.getDefaultTraversableResolver();

            try (ValidatorFactory limited = config
                    .traversableResolver(new LimitedResolver(defaultResolver))
                    .buildValidatorFactory()) {

                show("normal(nested)", normal.getValidator(), nestedInvalid);
                show("limited(nested)", limited.getValidator(), nestedInvalid);
                show("limited(null)", limited.getValidator(), missingAddress);
            }
        }
    }
}
```

Lệnh chạy tại thư mục chứa `pom.xml` với Java 17+ và Maven:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.validation.TraversalExample
```

Các dòng do chương trình in, không bao gồm log phụ từ Maven/provider nếu môi trường bật log:

```text
normal(nested) => customerName:NotBlank, deliveryAddress.street:NotBlank, internalCode:NotBlank
limited(nested) => customerName:NotBlank
limited(null) => customerName:NotBlank, deliveryAddress:NotNull
```

**Giải thích:**

- `normal(nested)`: ở ví dụ không có JPA, resolver mặc định cho phép đọc mọi property và cascade; cả `customerName`, `internalCode` và `Address.street` đều rỗng nên vi phạm `@NotBlank`.
- `limited(nested)`: `internalCode` bị chặn ở `isReachable` nên `@NotBlank` của nó không chạy. `deliveryAddress` reachable, khác `null` nên thỏa `@NotNull`, nhưng không cascade nên `street` không bị kiểm tra. Chỉ `customerName` vi phạm.
- `limited(null)`: `deliveryAddress` reachable nên `@NotNull` vẫn báo lỗi, dù cascade bị chặn. Đây chính là khác biệt cốt lõi giữa hai phương thức.

Chương trình dùng tên annotation và sắp xếp kết quả để tránh phụ thuộc thứ tự `Set<ConstraintViolation<?>>` và ngôn ngữ thông báo lỗi. `ValidatorFactory` được đóng bằng try-with-resources sau khi sử dụng.

**Vì sao có `defaultResolver`?** Resolver mặc định có thể chứa chính sách JPA để tránh đọc thuộc tính chưa nạp. Nếu viết custom resolver chỉ `return true` cho những property còn lại, ta có thể vô tình loại bỏ chính sách đó. Ủy quyền tới `Configuration#getDefaultTraversableResolver()` giúp giữ nguyên hành vi provider ở phần không tùy biến.

## 6. Liên hệ với JPA và quan hệ lazy

Một ví dụ tích hợp JPA (đoạn mã minh họa, cần entity mapping/cấu hình ứng dụng mới chạy được):

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    @NotNull
    @Valid
    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
```

Khi `customer` chưa được nạp, việc đọc trực tiếp quan hệ có thể khiến ORM truy vấn DB. Theo mặc định của đặc tả Jakarta Validation khi có Jakarta Persistence, property được xem là reachable nếu persistence provider xác nhận property đã được loaded. Một cơ chế thường dùng là:

```java
// Minh họa JPA-aware reachability, không phải class hoàn chỉnh:
return traversableObject == null
    || jakarta.persistence.Persistence.getPersistenceUtil()
        .isLoaded(traversableObject, traversableProperty.getName());
```

Nhiều provider đã tự tích hợp hành vi này khi dùng JPA. Vì vậy, **không cần tự viết resolver chỉ để chặn lazy loading khi mặc định đã đáp ứng yêu cầu**. Nếu phải tự viết resolver để thêm chính sách, nên ủy quyền tới default resolver như ví dụ.

Những hệ quả cần biết:

- Property bị đánh dấu unreachable không được đánh giá constraint trực tiếp; ngay cả `@NotNull` trên property đó cũng không phát sinh violation ở lượt kiểm tra ấy.
- Nếu property đã được nạp, provider có thể đánh giá nó và cascade bình thường tùy annotation/group.
- “Chưa loaded” khác “giá trị bằng `null`”. Tránh gọi getter/đọc collection lazy trong chính `isReachable`.
- Resolver chỉ kiểm soát **quá trình Bean Validation**. Mapper, serializer, debugger, logger hoặc code nghiệp vụ vẫn có thể đọc property và kích hoạt truy vấn.
- `@Valid` không phải `CascadeType.PERSIST` hay `CascadeType.REMOVE`. Một bên điều khiển validation; bên kia điều khiển thao tác ORM.

Nếu nghiệp vụ cần đảm bảo toàn bộ đồ thị hợp lệ, hãy nạp đúng dữ liệu cần thiết trong transaction hợp lý hoặc validate DTO rõ ràng. Không nên lấy việc “không có violation” trên entity với nhiều quan hệ chưa nạp làm bằng chứng tất cả quan hệ đều hợp lệ.

## 7. Giới hạn duyệt theo tên, đường dẫn và độ sâu

Resolver có thể ra quyết định theo:

- **Loại owner:** `traversableObject instanceof Checkout` để tránh ảnh hưởng class khác.
- **Tên property:** `traversableProperty.getName()`.
- **Kiểu gốc:** `rootBeanType` giúp phân biệt điểm khởi phát validation.
- **Đường đi:** `pathToTraversableObject` giúp nhận biết nhánh lồng nhau.
- **Vị trí khai báo:** `elementType` phân biệt field với getter constraint.

Khi muốn hạn chế đi quá sâu nhưng vẫn giữ constraint của property hiện tại, chọn điều khiển **`isCascadable`**. Ví dụ minh họa bên trong phương thức đó, với `delegate` là resolver mặc định:

```java
long propertyNodes = 0;
for (Path.Node node : pathToTraversableObject) {
    if (node.getKind() == jakarta.validation.ElementKind.PROPERTY) {
        propertyNodes++;
    }
}

boolean mayGoDeeper = propertyNodes < 2;
return mayGoDeeper && delegate.isCascadable(
    traversableObject, traversableProperty, rootBeanType,
    pathToTraversableObject, elementType);
```

Đây là **một chính sách minh họa để đếm node thuộc tính**, không phải thuật toán giới hạn “hai object” áp dụng đúng cho mọi trường hợp. `Path` có thể chứa method node, parameter node, container-element node hoặc thông tin index/key. Với `List<@Valid T>`, `Map<K, @Valid V>` và các cấu trúc lồng nhau, phải kiểm thử đường đi thực tế và định nghĩa chính xác độ sâu muốn giới hạn.

Đừng dùng `isReachable=false` chỉ để giảm độ sâu nếu vẫn cần kiểm tra constraint trên property hiện tại: cách đó sẽ bỏ qua cả constraint trực tiếp. Tương tự, *ngừng cascade* không ngăn một object được kiểm tra qua đường tham chiếu khác trong cùng graph.

## 8. Tích hợp vào Spring Framework

Trong Spring Framework 6/Spring Boot 3, Bean Validation sử dụng `jakarta.validation`. Spring thường tích hợp provider qua `org.springframework.validation.beanvalidation.LocalValidatorFactoryBean`, nơi có phương thức `setTraversableResolver(...)`:

```java
// Đoạn cấu hình minh họa, không phải một @Configuration độc lập:
LocalValidatorFactoryBean bean = new LocalValidatorFactoryBean();
bean.setTraversableResolver(customResolver);
```

`customResolver` phải là instance của một class triển khai `TraversableResolver`, ví dụ `LimitedResolver` trong phần 5 nếu được tổ chức thành class có thể truy cập trong ứng dụng. Muốn policy thực sự ảnh hưởng tới validation từ Spring MVC, phải bảo đảm bean này được dùng làm validator ở đúng điểm tích hợp. Spring Boot có thể tự cấu hình validator, nên tránh khai báo một factory mới ngoài ý muốn nếu ứng dụng đã có cơ chế tùy biến phù hợp.

Ví dụ controller (đoạn tích hợp, cần các class/import liên quan):

```java
@PostMapping("/checkouts")
public ResponseEntity<Void> create(@Valid @RequestBody CheckoutRequest body) {
    return ResponseEntity.noContent().build();
}
```

Khi Bean Validation được kích hoạt, reachability/cascadability áp dụng cho các property cần đánh giá. Tuy nhiên:

- Binding JSON và chuyển kiểu diễn ra ở tầng khác; lỗi đọc JSON có thể xuất hiện trước khi validation chạy.
- `@Validated` có thể chọn nhóm validation; nó không thay đổi ý nghĩa `isReachable`/`isCascadable`.
- Spring `org.springframework.validation.Validator` với `validate(Object, Errors)` là giao diện riêng; nó không tự dùng hợp đồng `TraversableResolver` cho các kiểm tra thủ công.
- Nếu mục tiêu chỉ là kiểm tra một giá trị, viết constraint/`ConstraintValidator` phù hợp sẽ rõ ràng hơn việc can thiệp vào hạ tầng duyệt property.

## 9. Các ràng buộc vận hành và lỗi phổ biến

Implementation của `TraversableResolver` phải **thread-safe**. Có thể dùng đối tượng stateless hoặc state bất biến như `LimitedResolver`. Không nên dùng biến đếm chung tăng/giảm theo callback để đo độ sâu, vì một instance có thể được tái sử dụng khi validation chạy song song.

Không được dựa vào số lần callback được gọi: Hibernate Validator có thể cache kết quả resolver trong một lượt validation để giảm chi phí, nhất là với JPA. Nếu chính resolver rất nhanh, thay đổi cache là tối ưu hóa riêng cần có đo đạc; thông thường giữ cấu hình mặc định.

Nếu resolver ném exception, provider sẽ bao bọc thành `ValidationException`; đó là lỗi hạ tầng, **không phải** một violation của constraint. Đối với property không cho phép truy cập, trả `false` thay vì ném lỗi. Không gọi getter lazy, thực hiện DB query hoặc thay đổi trạng thái object trong callback.

Các lỗi dễ gặp:

1. Trả `false` từ `isReachable` rồi cho rằng `@NotNull` vẫn chạy.
2. Trả `false` từ `isCascadable` rồi cho rằng mọi constraint trên property đều bị bỏ qua.
3. Bỏ default resolver trong ứng dụng JPA và vô tình đọc property lazy.
4. Chặn dựa vào tên property toàn cục mà không xét loại owner/đường đi.
5. Dereference `traversableObject` trong ngữ cảnh `validateValue` khi tham số này bằng `null`.
6. Nhầm resolver với cơ chế bảo mật/phân quyền hoặc giới hạn truy vấn ở mọi lớp phần mềm.
7. Dùng độ sâu của `Path` như số lượng object mà không tính tới container/executable node.

## 10. Kiểm thử chính sách duyệt

| Test case | Kỳ vọng |
| --- | --- |
| Property `@NotBlank` reachable, giá trị rỗng | Có violation |
| Cùng property bị đánh dấu unreachable | Không đánh giá constraint đó |
| Property `@NotNull @Valid` reachable, non-cascadable và khác null | Không đi vào constraint của object con |
| Cùng property bằng null | Vẫn báo `@NotNull` |
| Property `@Valid` reachable và cascadable | Cho phép validation của object con |
| `validateValue(...)` với owner null | Resolver hoạt động, không NPE |
| JPA entity có quan hệ chưa loaded | Không tự ý làm lộ truy vấn lazy qua validation |
| List/Map và object lồng sâu | Chính sách theo `Path` không chặn sai cấp |
| Nhiều lượt validation song song | Kết quả không bị ảnh hưởng bởi state dùng chung |

**Quy tắc ghi nhớ:** `isReachable` quyết định *có kiểm tra property hay không*; `isCascadable` quyết định *có đi tiếp qua `@Valid` hay không*. Khi chặn một nhánh, cần hiểu rõ các violation nào không còn được phát hiện và kiểm thử quyết định đó ở điểm gọi thực tế.

## Tham khảo

- Jakarta Validation API, `TraversableResolver`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/TraversableResolver.html
- Jakarta Bean Validation 3.0 Specification, phần *Traversable property*: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation `Configuration`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Configuration.html
- Hibernate Validator 8 Reference Guide, *TraversableResolver*: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6 `LocalValidatorFactoryBean` API: https://docs.spring.io/spring-framework/docs/6.0.23/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html