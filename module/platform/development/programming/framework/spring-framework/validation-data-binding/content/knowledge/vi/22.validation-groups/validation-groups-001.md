# Default group và khai báo nhóm bằng interface

> **Phạm vi:** Nhóm kiểm tra (*validation groups*) của Jakarta Bean Validation, đặc biệt là nhóm `Default`, marker interface để biểu diễn quy tắc tạo/cập nhật, cách gán constraint vào nhóm và chọn nhóm lúc chạy. Bài cũng liên hệ với Spring MVC `@Valid`/`@Validated`, nhóm kế thừa, kiểm tra lồng nhau và những nhầm lẫn phổ biến. Ví dụ độc lập có thể chạy bằng Java 17+ và Maven.

## 1. Vì sao Bean Validation cần nhóm kiểm tra?

Cùng một đối tượng dữ liệu có thể xuất hiện trong nhiều kịch bản. Ví dụ với một tài khoản:

- **Tạo mới:** cần tên và mã mời; chưa có ID từ hệ thống.
- **Cập nhật:** cần ID nhưng không phải nhập lại mã mời.
- **Kiểm tra chung:** một số thuộc tính luôn có quy tắc cơ bản, bất kể thao tác.

Nếu chạy mọi constraint trong mọi lần validate thì request tạo mới có thể bị báo thiếu ID, còn request sửa bị báo thiếu mã mời. *Validation group* cho phép lựa chọn tập constraint cần áp dụng cho một thao tác, mà không phải viết lại logic validator.

```text
                          CustomerRequest
                (constraint mang metadata nhóm)
                             │
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
          Default          OnCreate         OnUpdate
      quy tắc cơ bản    quy tắc tạo      quy tắc sửa
             │               │                │
             └───────────────┴────────────────┘
                             │
            Validator.validate(bean, groups...)
                             │
                   ConstraintViolation(s)
```

Tên nhóm không tự liên kết với HTTP method, Java class hay quyền của người dùng: **caller** phải chọn group phù hợp khi gọi Bean Validation. Mặc định không có nghĩa “tất cả nhóm”.

## 2. Nhóm `Default` là gì?

Jakarta Validation định nghĩa interface chuẩn:

```java
jakarta.validation.groups.Default
```

Nếu một constraint **không ghi thuộc tính `groups`**, constraint đó thuộc `Default`. Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

public class ProfileInput {
    @NotBlank
    private String name;

    @NotNull(groups = Default.class)
    private Long ownerId;
}
```

Hai field trên cùng thuộc nhóm `Default`. Viết `groups = Default.class` là cách khai báo tường minh điều vốn là mặc định. Đoạn ví dụ chỉ minh họa annotation; không phải một chương trình Java có `main`.

Với bean thông thường không tùy biến trình tự nhóm mặc định, hai lệnh sau kiểm tra cùng nhóm:

```java
validator.validate(profile);
validator.validate(profile, Default.class);
```

Trong API `Validator.validate(T object, Class<?>... groups)`, khi **không truyền group**, nhóm mặc định được dùng. Điều này **không** kích hoạt tất cả các constraint có nhóm `Create`, `Update`, `Admin`,...

Ngược lại, constraint được viết:

```java
@NotBlank(groups = OnCreate.class)
private String invitationCode;
```

chỉ thuộc `OnCreate`, **không tự động còn thuộc `Default`**. Giá trị mặc định của thuộc tính `groups` trong định nghĩa annotation là mảng rỗng; khi bạn khai báo nhóm tùy chỉnh, bạn đã thay thế lựa chọn mặc định bằng danh sách vừa khai báo.

### 2.1. Bảng hành vi

| Constraint được gắn | `validate(bean)` | `validate(bean, Default.class)` | `validate(bean, OnCreate.class)` |
| --- | --- | --- | --- |
| `@NotBlank String name` | Có | Có | Không, nếu `OnCreate` không kế thừa `Default` |
| `@NotNull(groups = Default.class) Long ownerId` | Có | Có | Không, nếu không có quan hệ nhóm |
| `@NotBlank(groups = OnCreate.class) String invitationCode` | Không | Không | Có |
| `@Positive(groups = {Default.class, OnCreate.class}) int quota` | Có | Có | Có |

**Lưu ý phạm vi:** Bảng mô tả nhóm độc lập thông thường. Group inheritance, `@GroupSequence` và `@ConvertGroup` có thể mở rộng/thay đổi tập constraint thực sự được kiểm tra; chúng phải được khai báo có chủ đích.

## 3. Tạo validation group bằng interface đánh dấu

Nhóm tùy chỉnh thường là **marker interface**: interface rỗng, không đòi hỏi implementation và không chứa nghiệp vụ.

```java
public interface OnCreate {
}

public interface OnUpdate {
}
```

Nếu là hai interface `public` cấp cao nhất như trên, mỗi interface cần file Java tương ứng (`OnCreate.java`, `OnUpdate.java`). Để tập trung nhóm, dự án thường dùng một lớp chứa interface lồng nhau:

**`ValidationGroups.java`**

```java
package demo;

public final class ValidationGroups {
    private ValidationGroups() {
    }

    public interface OnCreate {
    }

    public interface OnUpdate {
    }
}
```

Dùng trong constraint:

```java
import jakarta.validation.constraints.NotNull;

@NotNull(groups = ValidationGroups.OnUpdate.class)
private Long id;
```

Đoạn này là field minh họa bên trong DTO. Dùng `ValidationGroups.OnUpdate.class` — **Class literal**, không truyền một chuỗi `"OnUpdate"`, không `new` interface và không cần Spring bean cho mỗi group.

### 3.1. Một constraint có thể tham gia nhiều nhóm

```java
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.Default;

@Positive(groups = {
    Default.class,
    ValidationGroups.OnCreate.class,
    ValidationGroups.OnUpdate.class
})
private Integer quota;
```

Một constraint như trên chạy khi yêu cầu bất kỳ nhóm nào đã liệt kê. Cũng có thể chỉ ghi `OnCreate.class` và `OnUpdate.class` mà không có `Default.class` nếu yêu cầu nghiệp vụ mong như vậy.

Không gắn cùng một annotation nhiều lần chỉ để mô tả nhiều nhóm nếu có thể đưa các nhóm vào **một thuộc tính `groups`**; làm thế giúp tránh trùng ràng buộc và giữ mô hình rõ ràng.

## 4. Chọn nhóm khi gọi `Validator`

Các cách gọi cơ bản:

```java
validator.validate(bean); // Default
validator.validate(bean, Default.class); // Default tường minh
validator.validate(bean, ValidationGroups.OnCreate.class);
validator.validate(bean, ValidationGroups.OnUpdate.class);
validator.validate(bean,
        Default.class, ValidationGroups.OnCreate.class);
```

**Truyền nhiều nhóm** yêu cầu provider kiểm tra các nhóm được chọn; không có cam kết rằng group ở đầu danh sách luôn được xử lý xong trước group phía sau. Trình tự có chủ đích là chủ đề của `@GroupSequence`.

`Validator.validate(...)` trả về `Set<ConstraintViolation<T>>`. Một Set không có thứ tự ổn định theo contract; khi in hoặc so sánh trong test, sắp xếp những thuộc tính cần thiết. `getMessage()` có thể bị ảnh hưởng bởi locale; nên dùng `getPropertyPath()` và loại annotation khi cần assertion mang tính kỹ thuật.

### 4.1. Ví dụ độc lập Java 17+ chạy được

Ví dụ sau chứng minh rằng Default và OnCreate/OnUpdate **không mặc nhiên gộp với nhau**, rằng một constraint có thể có hai group và rằng một group có thể kế thừa group khác.

Cấu trúc dự án:

```text
bean-validation-groups/
├── pom.xml
└── src/main/java/demo/ValidationGroupsDemo.java
```

**`pom.xml`**: dùng Spring Boot starter làm nguồn API Jakarta Validation và Hibernate Validator; chương trình Java `main` không khởi tạo Spring application context.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>bean-validation-groups</artifactId>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ValidationGroupsDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.groups.Default;

import java.util.List;
import java.util.Set;

public class ValidationGroupsDemo {
    public interface OnCreate {
    }

    public interface OnUpdate {
    }

    // Review kế thừa OnCreate. Khi validate Review,
    // constraint thuộc OnCreate cũng được xét.
    public interface Review extends OnCreate {
    }

    static final class Customer {
        @NotBlank
        private final String name; // nhóm Default

        @NotNull(groups = OnCreate.class)
        private final String invitationCode;

        @NotNull(groups = OnUpdate.class)
        private final Long id;

        @Positive(groups = {OnCreate.class, OnUpdate.class})
        private final int quota;

        Customer(String name, String invitationCode,
                 Long id, int quota) {
            this.name = name;
            this.invitationCode = invitationCode;
            this.id = id;
            this.quota = quota;
        }
    }

    public static void main(String[] args) {
        Customer invalid = new Customer("", null, null, 0);
        Customer valid = new Customer("Lan", "INV-01", 7L, 2);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            show(validator, "implicitDefault", invalid);
            show(validator, "explicitDefault", invalid,
                    Default.class);
            show(validator, "create", invalid,
                    OnCreate.class);
            show(validator, "update", invalid,
                    OnUpdate.class);
            show(validator, "defaultPlusCreate", invalid,
                    Default.class, OnCreate.class);
            show(validator, "reviewInherited", invalid,
                    Review.class);
            show(validator, "validAll", valid,
                    Default.class, OnCreate.class, OnUpdate.class);
        }
    }

    private static void show(Validator validator, String label,
                             Customer bean, Class<?>... groups) {
        Set<ConstraintViolation<Customer>> violations =
                validator.validate(bean, groups);

        List<String> fields = violations.stream()
                .map(v -> v.getPropertyPath().toString() + ":"
                        + v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName())
                .sorted()
                .toList();

        System.out.println(label + " -> " + fields);
    }
}
```

Chạy trong thư mục chứa `pom.xml`, cần Maven và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidationGroupsDemo
```

**Các dòng do chương trình in ra** (không bao gồm log phụ của Maven/provider):

```text
implicitDefault -> [name:NotBlank]
explicitDefault -> [name:NotBlank]
create -> [invitationCode:NotNull, quota:Positive]
update -> [id:NotNull, quota:Positive]
defaultPlusCreate -> [invitationCode:NotNull, name:NotBlank, quota:Positive]
reviewInherited -> [invitationCode:NotNull, quota:Positive]
validAll -> []
```

Vì `Customer invalid` có `name=""`, `invitationCode=null`, `id=null` và `quota=0`:

1. Không truyền group đồng nghĩa kiểm tra `Default` → chỉ `name:NotBlank`.
2. Truyền `OnCreate.class` → kiểm tra `invitationCode` và `quota`; **không tự kiểm tra `name`**.
3. Truyền `OnUpdate.class` → kiểm tra `id` và `quota`.
4. Truyền đồng thời `Default.class` và `OnCreate.class` → có cả lỗi của hai nhóm.
5. `Review extends OnCreate` → kế thừa constraint của `OnCreate`, không tự bao gồm `Default`.
6. `Customer valid` hợp lệ trong tất cả ba nhóm.

Chương trình không in text message (có thể được dịch) và đã sort theo tên field/constraint để không phụ thuộc thứ tự `Set`. Factory do chương trình tạo được đóng bằng `try-with-resources`; `Validator` lấy từ factory được dùng lại trong cùng vòng đời.

### 4.2. Bài tập nhỏ: thêm `Default` vào nhóm tạo

Thử thay annotation trên `name` trong `Customer` thành:

```java
@NotBlank(groups = {Default.class, OnCreate.class, OnUpdate.class})
private final String name;
```

Sau thay đổi, kiểm tra `OnCreate` hoặc `OnUpdate` cũng phát hiện `name` rỗng. Nếu thay bằng `groups = OnCreate.class` **mà bỏ `Default.class`**, `name` không còn được kiểm tra ở `Default` nữa. Đây là cách kiểm chứng quan hệ giữa danh sách `groups` và nhóm mặc định.

## 5. Kế thừa validation group bằng `extends`

Giống các interface Java khác, marker interface có thể kế thừa:

```java
public interface BasicChecks {
}

public interface DetailedChecks extends BasicChecks {
}
```

Khi gọi `validate(bean, DetailedChecks.class)`, provider xem xét constraint ở `DetailedChecks` **và** `BasicChecks`. Ngược lại, yêu cầu `BasicChecks.class` không lấy các constraint chỉ thuộc `DetailedChecks`.

| Group chọn khi validate | Constraint thuộc `BasicChecks` | Constraint thuộc `DetailedChecks` |
| --- | --- | --- |
| `BasicChecks.class` | Có | Không |
| `DetailedChecks.class` | Có, qua kế thừa | Có |

Điểm này cũng cho phép một nhóm tự định nghĩa **kế thừa `Default`** nếu ứng dụng thực sự muốn gồm các constraint mặc định:

```java
import jakarta.validation.groups.Default;

public interface OnCreateIncludingDefault extends Default {
}
```

Khi chọn `OnCreateIncludingDefault.class`, các ràng buộc thuộc `Default` cũng được đưa vào cùng quá trình kiểm tra. Nhưng **không phải mọi interface nhóm đều tự extends Default**. Việc chọn đúng nhóm và mô hình kế thừa phải được xác định từ contract của ứng dụng.

**Kế thừa không đồng nghĩa thứ tự.** Nó giúp tính cả nhóm cha, không đảm bảo constraint của nhóm cha luôn hoàn thành trước nhóm con; nếu cần thứ tự dừng sớm, dùng `@GroupSequence`.

## 6. Phân biệt `@Valid` và `@Validated` trong Spring MVC

Spring Framework tích hợp Jakarta Bean Validation thông qua các lớp adapter như `LocalValidatorFactoryBean`. Với Spring Boot 3.x có `spring-boot-starter-validation`, bạn thường không phải bootstrap factory thủ công trong controller.

Hai annotation thường gặp:

- `jakarta.validation.Valid` (chuẩn Jakarta) dùng để biểu thị cascade và được Spring MVC hỗ trợ để kích hoạt validation argument; khi không có hướng dẫn nhóm khác, **nhóm `Default`** là lựa chọn thông thường.
- `org.springframework.validation.annotation.Validated` (của Spring) cho phép **chọn nhóm**: `@Validated(ValidationGroups.OnCreate.class)` hoặc `@Validated({A.class, B.class})`.

### 6.1. Các lớp minh họa trong Spring Boot Web MVC

Đoạn code sau cần project Spring Boot 3 có Spring Web MVC, starter-validation và các file tương ứng. Đây là ví dụ tích hợp, **không phải** chương trình `main` độc lập ở phần 4.

**`ValidationGroups.java`**:

```java
package demo;

public final class ValidationGroups {
    private ValidationGroups() {
    }

    public interface OnCreate {}
    public interface OnUpdate {}
}
```

**`CustomerRequest.java`**:

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.Default;

public record CustomerRequest(
    @NotBlank(groups = {
        Default.class,
        ValidationGroups.OnCreate.class,
        ValidationGroups.OnUpdate.class
    })
    String name,

    @NotBlank(groups = ValidationGroups.OnCreate.class)
    String invitationCode,

    @NotNull(groups = ValidationGroups.OnUpdate.class)
    Long id
) {
}
```

**`CustomerController.java`**:

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    @PostMapping("/customers")
    public ResponseEntity<Void> create(
            @Validated(ValidationGroups.OnCreate.class)
            @RequestBody CustomerRequest request) {
        return ResponseEntity.noContent().build();
    }

    @PutMapping("/customers")
    public ResponseEntity<Void> update(
            @Validated(ValidationGroups.OnUpdate.class)
            @RequestBody CustomerRequest request) {
        return ResponseEntity.noContent().build();
    }
}
```

| Request sau khi deserialize thành DTO | Group chạy | Kết quả theo constraint |
| --- | --- | --- |
| Tạo mới, `name=""` | `OnCreate` | Vi phạm `@NotBlank` của `name` |
| Tạo mới, `invitationCode=""` | `OnCreate` | Vi phạm `@NotBlank` của mã mời |
| Tạo mới, `id=null` | `OnCreate` | Không vi phạm `id` (vì `id` thuộc `OnUpdate`) |
| Cập nhật, `id=null` | `OnUpdate` | Vi phạm `@NotNull` của `id` |
| Cập nhật, `invitationCode=null` | `OnUpdate` | Không vi phạm mã mời (vì chỉ thuộc `OnCreate`) |
| Cập nhật, `name=""` | `OnUpdate` | Vi phạm `@NotBlank` của `name` |

Đặt `name` vào cả ba nhóm để nó được kiểm tra ở tạo, sửa và default. Nếu chỉ đặt `@NotBlank` không có `groups`, thì `@Validated(OnCreate.class)` **không mặc nhiên** kiểm tra tên, trừ khi nhóm được thiết kế kế thừa `Default` hoặc được truyền cùng với `Default.class`.

Trong Spring MVC thông thường, lỗi `@Validated @RequestBody` được chuyển thành lỗi validation/HTTP 400 nếu không có xử lý `BindingResult` tương ứng. Nhưng **JSON sai cú pháp, thiếu dữ liệu trong chế độ strict deserialization hoặc chuyển kiểu thất bại** có thể bị Jackson/message converter xử lý *trước khi* Bean Validation chạy. Không nên suy mọi HTTP 400 đều là một `ConstraintViolation`.

### 6.2. Vì sao `@Valid` đôi khi “không bắt lỗi”?

Nếu controller dùng:

```java
public ResponseEntity<Void> create(
        @Valid @RequestBody CustomerRequest request) {
    // ...
}
```

và không có cách chọn nhóm khác, Spring kiểm tra `Default`. Lúc này `name` chạy, nhưng `invitationCode` chỉ thuộc `OnCreate` **không được kiểm tra**. Đây là bug thường thấy khi DTO đã gắn `groups=OnCreate.class` nhưng endpoint chỉ dùng `@Valid`.

Giải pháp là chọn group rõ ràng bằng `@Validated(OnCreate.class)` (hoặc marker nhóm đầy đủ) và viết test request xác nhận constraint cần thiết thực sự chạy. Đừng coi việc annotation có mặt là bằng chứng nó đã thực thi.

### 6.3. Method validation khác validation của request body

Spring cũng dùng `@Validated` trên bean/service để hỗ trợ method validation qua AOP/interceptor với constraint trên tham số và giá trị trả về. Đường chạy đó khác với argument validation của Spring MVC. Chẳng hạn *self-invocation* từ method này đến method khác trên cùng một object có thể không đi qua proxy. Luôn kiểm thử đúng cơ chế/entry point thực tế thay vì suy rằng `@Validated` ở một vị trí bất kỳ sẽ áp dụng cho mọi lời gọi.

## 7. Group trong kiểm tra lồng nhau (`@Valid` và `@ConvertGroup`)

Group được chọn ở bean gốc có thể **truyền sang bean con** khi provider cascade qua `@Valid`:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderRequest {
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String street; // Default

    @NotNull(groups = ValidationGroups.OnCreate.class)
    private String deliveryCode; // OnCreate
}
```

Đây là hai class minh họa; khi tạo file Java thực tế, mỗi `public` class cần nằm trong file cùng tên. Nếu gọi `validate(order, OnCreate.class)`:

- Nếu `address` khác null, validation cascade tới `Address` bằng nhóm `OnCreate`.
- `deliveryCode` được xét; `street` chỉ thuộc `Default` nên không tự chạy.
- `@Valid` **không tự cấm null**: nếu không cho phép `address=null`, thêm `@NotNull` thuộc nhóm cần thiết.

Nếu muốn đổi nhóm **chỉ trên một cạnh cascade**, Jakarta Validation có `@ConvertGroup`:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public class CheckoutRequest {
    @Valid
    @ConvertGroup(
        from = Default.class,
        to = ValidationGroups.OnCreate.class
    )
    private Address address;
}
```

Khi đang kiểm tra `Default` và đi xuống `address` qua `@Valid`, nhóm tại nhánh đó được chuyển sang `OnCreate`. Không dùng `@ConvertGroup` thay cho việc chọn group đúng tại controller hoặc gọi `validate`; conversion chỉ có ý nghĩa trên điểm cascade phù hợp.

Tương tự, constraint trong container cũng tuân theo group:

```java
Map<
    @NotBlank(groups = ValidationGroups.OnCreate.class) String,
    @Valid Address> addresses;
```

Ví dụ Map ở trên cần các import/DTO tương ứng để biên dịch. Constraint trên key chỉ chạy khi nhóm `OnCreate` được chọn; `@Valid` trên value quyết định có kiểm tra constraint trong bean `Address` hay không, với quy tắc truyền group hiện hành.

## 8. `@GroupSequence` để quy định thứ tự, khác với marker interface đơn thuần

Khi gọi:

```java
validator.validate(bean, Default.class, OnCreate.class);
```

provider chọn cả hai nhóm, nhưng **không có cam kết thứ tự đánh giá**. Nếu muốn kiểm tra nhóm cơ bản trước, chỉ đi tiếp khi nhóm trước hợp lệ, có thể định nghĩa một **group sequence**:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({Default.class, ValidationGroups.OnCreate.class})
public interface CompleteCreate {
}
```

Đoạn trên là định nghĩa interface trong file `CompleteCreate.java`, với `ValidationGroups` đã tồn tại. Khi gọi:

```java
validator.validate(bean, CompleteCreate.class);
```

provider kiểm tra `Default` trước; nếu có vi phạm, sequence không tiếp tục `OnCreate`. Nếu không có lỗi ở bước đầu, mới kiểm tra `OnCreate`.

**Không nhầm hai cách dùng `@GroupSequence`:** Khi định nghĩa lại *default group sequence của chính một class* bằng annotation trên class, sequence phải chứa **chính class đó**, không thể tùy ý chỉ ghi `Default.class` thay tên class. Vi phạm có thể dẫn đến `GroupDefinitionException`. Đây là cơ chế nâng cao; cho các nhu cầu tạo/sửa đơn giản, khai báo marker interface và chọn nhóm đúng thường dễ bảo trì hơn.

## 9. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách giải quyết |
| --- | --- | --- |
| Nghĩ `Default` nghĩa là tất cả constraint | Ràng buộc chỉ thuộc nhóm tùy chỉnh không chạy | Chọn nhóm đúng hoặc liệt kê `Default.class` cùng nhóm tùy chỉnh |
| Viết `groups=OnCreate.class` rồi nghĩ còn thuộc Default | Constraint không tự tham gia Default | Ghi rõ nhiều group nếu cần |
| Chỉ dùng `@Valid` ở POST nhưng DTO dùng `OnCreate` | Constraint tạo mới bị bỏ qua | Dùng `@Validated(OnCreate.class)` |
| Chỉ dùng `@Validated(OnCreate.class)` nhưng constraint name chỉ thuộc Default | Rule chung bị bỏ sót | Đưa name vào OnCreate hoặc thiết kế nhóm kế thừa/sequence |
| Khai báo interface marker có logic/phương thức không cần thiết | Mô hình nhóm khó hiểu | Interface rỗng có tên đúng nghiệp vụ |
| Truyền chuỗi `"Create"` thay vì `Create.class` | Không theo API group | Dùng `Class<?>` literal |
| Cho `Child extends Parent` nhưng nghĩ `validate(Parent.class)` chạy cả Child | Hiểu ngược quan hệ kế thừa | Chọn nhóm con mới nhận constraint của nhóm cha |
| Truyền hai nhóm để ép thứ tự | Thứ tự không được bảo đảm | Dùng `@GroupSequence` |
| Đặt group sequence sai khi redefine default của class | Lỗi định nghĩa nhóm | Class phải xuất hiện trong sequence của class đó |
| Quên `@Valid` cho bean con | Rule bên trong bean con không cascade | Thêm `@Valid` đúng property/container element |
| Có `@Valid` và nghĩ mọi nhóm của bean con đều chạy | Nhóm hiện hành được truyền, không mặc định là tất cả | Kiểm tra nhóm truyền và `@ConvertGroup` nếu cần |
| Dùng `@ConvertGroup` mà thiếu `@Valid` | Chuyển nhóm ở điểm không cascade là không hợp lệ | Gắn conversion đúng cạnh cascade |
| Không có provider Jakarta Validation | Annotation có thể tồn tại nhưng không thực thi như mong đợi | Thêm `spring-boot-starter-validation`/provider tương thích |
| Dùng `javax.validation.*` với Spring Boot 3 | Không đúng namespace Jakarta | Dùng `jakarta.validation.*` |
| Assert thứ tự của violations hoặc toàn bộ message | Test dễ phụ thuộc locale/provider | Sort hoặc so sánh tập constraint/path |

### Trường hợp nên dùng DTO riêng thay vì quá nhiều group

Nếu API tạo và cập nhật khác biệt lớn về cấu trúc, một `CreateCustomerRequest` và một `UpdateCustomerRequest` riêng có thể dễ đọc, dễ kiểm thử hơn một DTO phải duy trì hàng chục group. Groups có ích khi **tái sử dụng mô hình là có chủ đích** và sự khác biệt chỉ nằm ở bộ ràng buộc cần kiểm tra.

Group cũng không thay thế quyền truy cập, kiểm tra database hoặc quy tắc nghiệp vụ ở service. Có thể pass Bean Validation mà vẫn không được phép cập nhật bản ghi, hoặc ngược lại.

## 10. Quy trình kiểm thử và checklist

Kiểm tra theo các bước:

1. **Xác định metadata:** constraint không ghi `groups` = `Default`; có ghi nhóm tùy chỉnh thì kiểm tra danh sách thực sự.
2. **Xác định caller:** trực tiếp `Validator.validate(...)`, Spring MVC `@Valid` hay `@Validated(...)`, method validation hoặc job.
3. **Xem quan hệ nhóm:** marker interface có `extends` nhóm cha, `Default` hoặc tham gia `@GroupSequence` không?
4. **Kiểm tra nested bean:** `@Valid` có được đặt ở đường đi xuống đối tượng con? Có `@ConvertGroup` không?
5. **Tách lỗi binding:** dữ liệu đã vào DTO đúng kiểu trước validation hay chưa?
6. **Viết test ma trận:** một object vi phạm chỉ `Default`, một object vi phạm chỉ `OnCreate`, một object vi phạm cả hai, và một object hợp lệ.

Checklist áp dụng:

- [ ] Đã định nghĩa `Default` và group tùy chỉnh theo đúng phạm vi nghiệp vụ?
- [ ] Marker interface không chứa logic không cần thiết?
- [ ] Có test xác minh `validate(bean)` tương đương `validate(bean, Default.class)` trong cấu hình thông thường?
- [ ] Có test xác minh `validate(bean, OnCreate.class)` **không tự cộng Default**?
- [ ] Những constraint chung cho nhiều thao tác đã được gắn đủ nhóm?
- [ ] Kế thừa group được dùng có chủ đích và test đúng chiều?
- [ ] Spring MVC đang dùng `@Validated(Groups.X.class)` nếu cần nhóm X, không chỉ `@Valid`?
- [ ] DTO con có `@Valid` đúng chỗ và test nhóm truyền xuống?
- [ ] Nếu yêu cầu thứ tự, đã dùng `@GroupSequence` thay vì thứ tự tham số?
- [ ] Assertions không phụ thuộc vào thứ tự `Set<ConstraintViolation>` hay text message đã bản địa hóa?

**Kết luận:** `Default` là nhóm chuẩn của constraint không khai báo `groups`, **không phải tập hợp tất cả nhóm**. Group tùy chỉnh được biểu diễn bằng **interface đánh dấu**, gắn vào constraint qua `groups = MyGroup.class` và lựa chọn khi gọi `validate(bean, MyGroup.class)` hoặc dùng `@Validated(MyGroup.class)` trong Spring. Kế thừa/sequence/cascade cần được thiết kế riêng, tránh giả định rằng các nhóm tự động cộng dồn.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 Specification — Groups, Group Inheritance, Group Sequence](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation Default group — Platform 10 API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/groups/default)
- [Hibernate Validator 8 Reference Guide — Grouping Constraints](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
