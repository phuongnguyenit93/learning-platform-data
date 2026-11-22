# Constraint metadata API và ConstraintDescriptor trong Jakarta Validation và Spring Framework

Khi chạy Bean Validation, ta thường thấy `@NotBlank`, `@Size` hay một custom constraint, sau đó gọi `Validator.validate(bean)` để lấy các lỗi. Nhưng thư viện, framework và công cụ còn cần trả lời các câu hỏi **trước khi có một đối tượng để kiểm tra**:

- Lớp `OrderForm` có thuộc tính nào được gắn constraint?
- Thuộc tính `code` có những ràng buộc nào, gồm `min`/`max`, thông báo gốc và validation groups ra sao?
- Một thuộc tính chỉ có `@Valid` có được coi là điểm cần xét không?
- Constraint nằm trên field, getter, tham số phương thức, giá trị trả về hay phần tử của `List`?
- Một constraint được ghép từ nhiều constraint con gồm những thành phần nào?

**Constraint metadata API** của Jakarta Validation cung cấp những câu trả lời này bằng các *descriptor* do validation provider tạo ra từ cấu hình constraint hiệu lực. `ConstraintDescriptor` mô tả **một khai báo ràng buộc cụ thể**; nó không chứa lỗi phát sinh trên một dữ liệu đầu vào.

Bài này sử dụng API `jakarta.validation` của Spring Framework 6 / Spring Boot 3 và Java 17+. Cần phân biệt rõ việc **đọc metadata** với **thực thi kiểm tra**:

~~~text
                        jakarta.validation.Validator
                                   |
                  +----------------+----------------+
                  |                                 |
        getConstraintsForClass(...)               validate(bean)
                  |                                 |
              BeanDescriptor               Set<ConstraintViolation<T>>
                  |                                 |
        PropertyDescriptor, ...            dữ liệu nào vi phạm?
                  |
          ConstraintDescriptor
                  |
   annotation, attributes, groups,
   message template, composition...
                  |
     constraint nào ĐƯỢC KHAI BÁO?
~~~

Metadata giúp công cụ hiểu quy tắc mà không cần chạy `isValid`. Ngược lại, gọi `validate` mới kiểm tra một giá trị thực tế và tạo `ConstraintViolation`.

## 1. Điểm vào: `Validator.getConstraintsForClass`

API chuẩn nằm trong `jakarta.validation.Validator`:

~~~java
import jakarta.validation.Validator;
import jakarta.validation.metadata.BeanDescriptor;

BeanDescriptor beanDescriptor =
    validator.getConstraintsForClass(OrderForm.class);
~~~

Đây là đoạn mã minh họa **bên trong một component đã có biến `validator`**. `getConstraintsForClass(Class<?>)` trả về `BeanDescriptor` mô tả metadata của lớp; không cần `new OrderForm(...)`. Nó không validate dữ liệu và không trả về `Set<ConstraintViolation<?>>`.

`BeanDescriptor` tồn tại cả khi lớp không có constraint. Điểm đáng chú ý:

- `beanDescriptor.isBeanConstrained()` hỏi lớp hoặc thuộc tính của nó có constraint/cascade hay không; **không tính riêng constraint trên method/constructor**.
- `beanDescriptor.hasConstraints()`, kế thừa từ `ElementDescriptor`, chỉ phản ánh constraint gắn lên **chính đối tượng ở cấp class**; nó không đồng nghĩa toàn bộ các property đều không có constraint.
- `beanDescriptor.getConstraintDescriptors()` là các constraint gắn trực tiếp lên **cấp class**, không tự gộp tất cả constraint trên field.
- `beanDescriptor.getConstrainedProperties()` trả các property có ràng buộc hoặc được đánh dấu cascading.
- `beanDescriptor.getConstraintsForProperty("code")` đi tới một property cụ thể; có thể trả `null` nếu property không tồn tại, hoặc không có constraint/cascade.

Ví dụ, lớp chỉ có `@NotBlank private String code;` thường có `isBeanConstrained() == true`, nhưng `beanDescriptor.hasConstraints() == false` và `beanDescriptor.getConstraintDescriptors().isEmpty() == true`, bởi vì constraint nằm trên **property**, không phải annotation trên class.

## 2. Cây descriptor: mỗi mức có trách nhiệm riêng

Các interface chính nằm trong package `jakarta.validation.metadata`.

| API | Đối tượng được mô tả | API đáng chú ý |
|---|---|---|
| `ElementDescriptor` | Nút chung: class, property, parameter, return value... | `hasConstraints()`, `getConstraintDescriptors()`, `getElementClass()`, `findConstraints()` |
| `BeanDescriptor` | Một Java Bean | `getConstrainedProperties()`, `getConstraintsForProperty()`, `getConstraintsForMethod()`, `getConstrainedMethods()` |
| `PropertyDescriptor` | Property đã có constraint/cascade, gồm field/getter | `getPropertyName()`, `isCascaded()`, `getConstrainedContainerElementTypes()` |
| `MethodDescriptor` | Phương thức có constraint trên parameter/return value hoặc cascade | `getParameterDescriptors()`, `getReturnValueDescriptor()`, `getCrossParameterDescriptor()` |
| `ConstructorDescriptor` | Constructor có các vị trí kiểm tra tương ứng | `getParameterDescriptors()`, `getReturnValueDescriptor()` |
| `ParameterDescriptor` | Một tham số executable | `getIndex()`, `getName()`, `getConstraintDescriptors()` |
| `ReturnValueDescriptor` | Giá trị trả về của method/constructor | `getConstraintDescriptors()`, `isCascaded()` |
| `ContainerElementTypeDescriptor` | Type argument được validate, như `String` trong `List<@NotBlank String>` | `getContainerClass()`, `getTypeArgumentIndex()`, `getConstraintDescriptors()` |
| `ConstraintDescriptor<T>` | **Một constraint declaration** | `getAnnotation()`, `getAttributes()`, `getGroups()`, `getComposingConstraints()` |

Các descriptor liên quan cascading và container còn triển khai các hợp đồng `CascadableDescriptor` và `ContainerDescriptor`. Bởi vậy phải kiểm tra đúng cấp: `PropertyDescriptor.getConstraintDescriptors()` có thể rỗng khi property chỉ có `@Valid`, nhưng `isCascaded()` vẫn là `true`; constraint trên **type argument** được tìm ở `ContainerElementTypeDescriptor`.

Mô hình điều hướng:

~~~text
BeanDescriptor<OrderForm>
├─ PropertyDescriptor("code")
│  ├─ ConstraintDescriptor<NotBlank>
│  ├─ ConstraintDescriptor<Size>
│  └─ ConstraintDescriptor<Pattern>
├─ PropertyDescriptor("customer")
│  └─ isCascaded() = true  (@Valid)
├─ PropertyDescriptor("tags")
│  └─ ContainerElementTypeDescriptor(List argument #0: String)
│     └─ ConstraintDescriptor<NotBlank>
└─ MethodDescriptor("submit", String.class)
   └─ ParameterDescriptor(index=0)
      └─ ConstraintDescriptor<NotBlank>
~~~

Cây này **không phải** AST source code. Provider tính đến khai báo hợp lệ trên các kiểu cha, cách tổ hợp constraint và các nguồn mapping của chính Jakarta Validation.

## 3. `ConstraintDescriptor` thực sự chứa gì?

`ConstraintDescriptor<T extends Annotation>` mô tả **một lần áp dụng annotation** lên một phần tử, bao gồm thuộc tính của lần áp dụng đó. Với `@Size(min=4, max=12)`, descriptor chứa `min=4` và `max=12`; đó không nhất thiết là giá trị mặc định trong định nghĩa annotation.

| Phương thức | Giá trị/ý nghĩa | Điều cần tránh |
|---|---|---|
| `getAnnotation()` | Instance annotation (hoặc biểu diễn annotation tương ứng) | Đừng đồng nhất với kết quả reflection trực tiếp trên field |
| `getAttributes()` | `Map<String,Object>` của các phần tử annotation như `min`, `max`, `regexp`, `message`, `groups` | Giá trị giữ kiểu Java; `min` là `Integer`, không phải chuỗi JSON |
| `getMessageTemplate()` | Thông báo **chưa nội suy**, ví dụ `{jakarta.validation.constraints.Size.message}` | Không phải thông báo đã thay biến/ngôn ngữ của một vi phạm thực |
| `getGroups()` | `Set<Class<?>>` các nhóm áp dụng | Constraint không khai báo nhóm tường minh thuộc `Default` |
| `getPayload()` | Tập lớp payload được khai báo | Payload không phải một validation group |
| `getConstraintValidatorClasses()` | Các lớp validator được khai báo cho constraint | Với một số built-in constraint, danh sách có thể rỗng; **không** suy ra constraint không kiểm tra được |
| `getComposingConstraints()` | Các descriptor của constraint con trong một constraint tổ hợp | Đây là quan hệ composition, không phải danh sách vi phạm |
| `isReportAsSingleViolation()` | Có `@ReportAsSingleViolation` cho constraint tổ hợp hay không | Không làm biến mất metadata của constraint con |
| `getValidationAppliesTo()` | `ConstraintTarget` nếu annotation có `validationAppliesTo`, hoặc `null` | Không dùng để suy đoán vị trí Java `@Target` |
| `getValueUnwrapping()` | Chính sách unwrapping do payload liên quan xác định | Khác với cascade `@Valid` |
| `unwrap(Type.class)` | Truy cập extension của provider nếu hỗ trợ | Không portable; có thể ném `ValidationException` |

Ví dụ đọc các thuộc tính của `@Size`:

~~~java
ConstraintDescriptor<?> sizeDescriptor =
    codeDescriptor.getConstraintDescriptors().stream()
        .filter(d -> d.getAnnotation()
            .annotationType() == Size.class)
        .findFirst()
        .orElseThrow();

int min = (Integer) sizeDescriptor.getAttributes().get("min");
int max = (Integer) sizeDescriptor.getAttributes().get("max");

System.out.println(min + ".." + max); // 4..12
~~~

Đoạn này **đặt trong ngữ cảnh** đã có `PropertyDescriptor codeDescriptor` của ví dụ hoàn chỉnh ở phần 5 và import `jakarta.validation.metadata.ConstraintDescriptor`, `jakarta.validation.constraints.Size`. Sử dụng `getAttributes()` đặc biệt hữu ích cho schema generator, form builder và documentation tooling, vì phải lấy cấu hình **đang có hiệu lực**, kể cả các thuộc tính đã bị override trong constraint composition.

Thông báo của `ConstraintDescriptor.getMessageTemplate()` là metadata cấu hình. `ConstraintViolation.getMessage()` mới là thông báo đã nội suy cho vi phạm cụ thể, có thể chịu ảnh hưởng từ `MessageInterpolator` và locale. Phân biệt hai API để không hiển thị nguyên key `{...}` cho người dùng cuối.

## 4. `ElementDescriptor.findConstraints()` và phạm vi tra cứu

Từ một `PropertyDescriptor` (hoặc descriptor khác kế thừa `ElementDescriptor`), có thể tạo một `ConstraintFinder` để lọc metadata:

~~~java
var defaults = codeDescriptor.findConstraints()
    .unorderedAndMatchingGroups(
        jakarta.validation.groups.Default.class)
    .getConstraintDescriptors();

var fieldConstraints = codeDescriptor.findConstraints()
    .declaredOn(java.lang.annotation.ElementType.FIELD)
    .getConstraintDescriptors();
~~~

Ba bộ lọc quan trọng:

- `unorderedAndMatchingGroups(G1.class, G2.class, ...)`: chỉ lấy constraint áp dụng cho các group yêu cầu, tính đến kế thừa nhóm và group sequence theo quy tắc metadata. **Không** mô phỏng thứ tự thực thi group sequence hoặc điều kiện dừng khi một group thất bại.
- `declaredOn(ElementType.FIELD, ElementType.METHOD, ...)`: chọn vị trí *khai báo* (ví dụ field so với getter), không phải chọn loại dữ liệu.
- `lookingAt(Scope.LOCAL_ELEMENT)` hoặc `lookingAt(Scope.HIERARCHY)`: chỉ lấy constraint khai báo cục bộ hoặc xét cả hierarchy. Phạm vi mặc định là hierarchy.

Lưu ý: `ConstraintFinder` là đối tượng **có trạng thái khi áp dụng filter** và **không thread-safe**; tạo một finder mới cho mỗi truy vấn độc lập. Không gọi `findConstraints()` một lần rồi cộng dồn bộ lọc cho các câu hỏi khác nhau mà không chủ ý. Tập `ConstraintDescriptor` trả về là tập không có thứ tự bảo đảm; sort theo annotation name/attribute trước khi in hoặc dùng trong test snapshot.

## 5. Ví dụ hoàn chỉnh trong Spring Boot: in cây metadata

Ví dụ có thể chạy trong **project Spring Boot 3.x + Java 17+** đã cài validation starter. Toàn bộ Java code dưới đây đặt trong một file:

`src/main/java/com/example/metadata/MetadataDemoApplication.java`

Các lớp mô hình đặt dạng `static` lồng bên trong class application để project demo chỉ cần **một file Java**, không cần controller/database. Component Spring nhận `jakarta.validation.Validator` được auto-configuration cung cấp.

Trong `build.gradle` của project Spring Boot dùng dependency management phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Nếu tạo project mới, có thể dùng Spring Initializr với Java 17+, Gradle và dependency **Validation**. Với project đã có Spring Boot plugin, chạy `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Không dùng `javac` thuần với classpath JDK vì code import Spring và Jakarta Validation.

### 5.1. Mã nguồn đầy đủ

~~~java
package com.example.metadata;

import jakarta.validation.Valid;
import jakarta.validation.Validator;
import jakarta.validation.groups.Default;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import jakarta.validation.metadata.BeanDescriptor;
import jakarta.validation.metadata.ConstraintDescriptor;
import jakarta.validation.metadata.PropertyDescriptor;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MetadataDemoApplication implements CommandLineRunner {

    private final Validator validator;

    public MetadataDemoApplication(Validator validator) {
        this.validator = validator;
    }

    public static void main(String[] args) {
        SpringApplication.run(MetadataDemoApplication.class, args);
    }

    public interface Strict {}

    public static class Customer {
        @NotBlank
        private final String name;

        public Customer(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static class OrderForm {
        @NotBlank
        @Size(min = 4, max = 12)
        @Pattern(
            regexp = "ORD-[A-Z0-9]+",
            groups = Strict.class
        )
        private final String code;

        @Valid
        private final Customer customer;

        private final List<@NotBlank String> tags;

        public OrderForm(
                String code,
                Customer customer,
                List<String> tags) {
            this.code = code;
            this.customer = customer;
            this.tags = tags;
        }

        public String getCode() {
            return code;
        }

        public Customer getCustomer() {
            return customer;
        }

        public List<String> getTags() {
            return tags;
        }

        public void submit(@NotBlank String requestId) {
            // Chỉ dùng để minh họa metadata tham số method.
        }
    }

    @Override
    public void run(String... args) {
        BeanDescriptor bean =
            validator.getConstraintsForClass(OrderForm.class);

        PropertyDescriptor code =
            bean.getConstraintsForProperty("code");

        ConstraintDescriptor<?> size =
            code.getConstraintDescriptors().stream()
                .filter(d ->
                    d.getAnnotation().annotationType()
                        == Size.class)
                .findFirst()
                .orElseThrow();

        int defaultCount = code.findConstraints()
            .unorderedAndMatchingGroups(Default.class)
            .getConstraintDescriptors().size();

        int strictCount = code.findConstraints()
            .unorderedAndMatchingGroups(Strict.class)
            .getConstraintDescriptors().size();

        PropertyDescriptor customer =
            bean.getConstraintsForProperty("customer");

        PropertyDescriptor tags =
            bean.getConstraintsForProperty("tags");

        int tagConstraintCount = tags
            .getConstrainedContainerElementTypes().stream()
            .mapToInt(d -> d.getConstraintDescriptors().size())
            .sum();

        var submit = bean.getConstraintsForMethod(
            "submit", String.class);

        var invalid = new OrderForm(
            "",
            new Customer(""),
            List.of("")
        );

        System.out.println(
            "Bean constrained: " + bean.isBeanConstrained());
        System.out.println(
            "Class-level constraints: "
                + bean.getConstraintDescriptors().size());
        System.out.println(
            "Code constraints: "
                + code.getConstraintDescriptors().size());
        System.out.println(
            "Size min/max: "
                + size.getAttributes().get("min") + "/"
                + size.getAttributes().get("max"));
        System.out.println(
            "Size template: " + size.getMessageTemplate());
        System.out.println(
            "Code Default group: " + defaultCount);
        System.out.println(
            "Code Strict group: " + strictCount);
        System.out.println(
            "Customer cascaded: " + customer.isCascaded());
        System.out.println(
            "Tag element constraints: " + tagConstraintCount);
        System.out.println(
            "Submit parameter constraints: "
                + submit.getParameterDescriptors().get(0)
                    .getConstraintDescriptors().size());
        System.out.println(
            "Default violations: "
                + validator.validate(invalid).size());
        System.out.println(
            "Strict violations: "
                + validator.validate(invalid, Strict.class).size());
    }
}
~~~

### 5.2. Kết quả quan sát

Chạy bằng wrapper:

~~~bash
./gradlew bootRun
~~~

Ngoài log khởi động Spring Boot, các dòng do `CommandLineRunner` in ra là:

~~~text
Bean constrained: true
Class-level constraints: 0
Code constraints: 3
Size min/max: 4/12
Size template: {jakarta.validation.constraints.Size.message}
Code Default group: 2
Code Strict group: 1
Customer cascaded: true
Tag element constraints: 1
Submit parameter constraints: 1
Default violations: 4
Strict violations: 1
~~~

Giải thích:

1. `OrderForm` có validation trên property nên `isBeanConstrained()` là `true`. Không có constraint **cấp class** nên kết quả `Class-level constraints: 0`.
2. `code` có ba khai báo: `@NotBlank`, `@Size` và `@Pattern`. Thuộc tính `min`/`max` của `@Size` được truy xuất trực tiếp, không cần lấy object từ form.
3. `Default` chọn `@NotBlank` và `@Size`; `Strict` chỉ chọn `@Pattern`. Interface `Strict` trong ví dụ không kế thừa group nào khác.
4. `customer` dùng `@Valid` cho cascade, vì vậy `isCascaded()` trả `true` dù property đó không có constraint trực tiếp.
5. `tags` có constraint ở **type argument** `String` của `List`, không nằm ở `List` nói chung.
6. `submit` có một `@NotBlank` trên tham số đầu tiên. Việc tìm thấy method metadata **không** có nghĩa một lời gọi Java thông thường tự được method validation.
7. Dữ liệu mẫu rỗng vi phạm `@NotBlank` và `@Size` của `code`, `@NotBlank` của `customer.name` qua cascade, `@NotBlank` của phần tử `tags[0]`: tổng cộng **4 vi phạm trong Default**.
8. Khi chỉ gọi group `Strict`, `code` vi phạm `@Pattern`: **1 vi phạm**. Constraint `Default` không mặc nhiên được áp dụng đồng thời với `Strict`.

Có thể dùng `gradlew.bat bootRun` trên Windows. Chương trình là một ứng dụng Spring Boot; các dòng số liệu trên chỉ là output của demo, không phải toàn bộ stdout của Spring Boot.

**Chú ý phạm vi của ví dụ:** code đặt constraint ở field, đọc metadata qua provider của Spring, và gọi `jakarta.validation.Validator` trực tiếp. Nó không cần HTTP endpoint, không sử dụng `@Validated` cho method, và không cần tự viết custom `ConstraintValidator` để giải thích `ConstraintDescriptor`.

## 6. Đọc property metadata đúng cách

### 6.1. Liệt kê mọi property được giới hạn

~~~java
var propertyNames = bean.getConstrainedProperties().stream()
    .map(PropertyDescriptor::getPropertyName)
    .sorted()
    .toList();

System.out.println(propertyNames);
~~~

Với `OrderForm` trong ví dụ, danh sách theo thứ tự từ vựng có các tên `code`, `customer` và `tags`. Lưu ý một property được liệt kê vì **constraint**, **cascade**, hoặc **container element constraint**; không bắt buộc `property.getConstraintDescriptors()` là non-empty.

Đối với property không có constraint/cascade, `bean.getConstraintsForProperty("missing")` trả `null`. Đừng gọi chuỗi `getConstraintsForProperty(...).getConstraintDescriptors()` mà không kiểm tra null khi tên property lấy từ input không tin cậy.

### 6.2. Field và getter cùng tham gia một property

Nếu `@NotBlank` đặt trên field `name` còn `@Size` đặt trên getter `getName()`, metadata của logical property `name` có thể chứa cả hai constraint. Dùng:

~~~java
var fieldRules = code.findConstraints()
    .declaredOn(java.lang.annotation.ElementType.FIELD)
    .getConstraintDescriptors();
~~~

`declaredOn(FIELD)` lọc **nơi khai báo**, không làm `code` thành một field descriptor độc lập. Đây là lý do metadata API phù hợp hơn việc chỉ gọi `OrderForm.class.getDeclaredField("code").getAnnotations()`. Reflection thuần không tự tổng hợp cùng cách provider tổng hợp field, getter, inheritance và XML constraint mappings.

Tránh khai báo cùng một quy tắc ở cả field và getter chỉ để “chắc chắn” — nhà cung cấp Bean Validation có thể coi đó là hai constraint declarations và báo lỗi trùng.

### 6.3. Cascading không phải constraint trực tiếp

~~~java
PropertyDescriptor customer =
    bean.getConstraintsForProperty("customer");

System.out.println(customer.isCascaded()); // true
System.out.println(customer.hasConstraints()); // false
~~~

Giải thích: `@Valid` yêu cầu provider đi vào bean `Customer` khi validation chạy, nhưng `@Valid` tự nó không là một `ConstraintDescriptor` thuộc property. Để biết những constraint trên `Customer.name`, hãy hỏi metadata của lớp `Customer`:

~~~java
BeanDescriptor customerBean =
    validator.getConstraintsForClass(Customer.class);

var nameRules = customerBean
    .getConstraintsForProperty("name")
    .getConstraintDescriptors();
~~~

Metadata API cũng cung cấp `getGroupConversions()` trên những descriptor hỗ trợ cascade để quan sát chuyển nhóm đã khai báo bằng `@ConvertGroup`. Khi xuất tài liệu, nhớ tách “cascade/group conversion” khỏi “constraint trực tiếp” để không bỏ qua hoặc nhân đôi logic.

### 6.4. Constraint trên phần tử container

Cho thuộc tính:

~~~java
private List<@NotBlank String> tags;
~~~

`@NotBlank` gắn lên **phần tử chuỗi** vì annotation hỗ trợ `TYPE_USE`. Đọc:

~~~java
PropertyDescriptor tags =
    bean.getConstraintsForProperty("tags");

for (var element :
        tags.getConstrainedContainerElementTypes()) {
    System.out.println(
        element.getContainerClass().getSimpleName());
    System.out.println(element.getTypeArgumentIndex());
    System.out.println(element.getConstraintDescriptors().size());
}
~~~

Kết quả của phần tử type argument nói trên là:

~~~text
List
0
1
~~~

Chỉ số `0` là vị trí type argument đầu tiên của `List<E>`, không phải chỉ số của phần tử dữ liệu ở runtime. Với nested container, ví dụ `List<Map<String, @NotBlank String>>`, descriptor container element có thể **lồng nhau**: gọi `getConstrainedContainerElementTypes()` đệ quy khi xây cây metadata.

`ContainerElementTypeDescriptor` còn có `isCascaded()` nếu element tương ứng gắn `@Valid`; không nhầm với một constraint như `@NotNull` hay `@NotBlank`.

## 7. Metadata cho phương thức và constructor

`BeanDescriptor` cho phép nhìn vào ràng buộc của **executables** mà không gọi phương thức/constructor đó:

~~~java
var method = bean.getConstraintsForMethod(
    "submit", String.class);

var parameter = method.getParameterDescriptors().get(0);

System.out.println(parameter.getIndex()); // 0
System.out.println(
    parameter.getConstraintDescriptors().size()); // 1
~~~

Đối với phương thức, tham số và giá trị trả về:

- `getConstraintsForMethod("name", ParamType.class, ...)` yêu cầu **tên và chữ ký tham số thực tế**; method không có constraint/cascade phù hợp có thể trả `null`.
- `MethodDescriptor.getParameterDescriptors()` trả descriptor cho từng tham số; `getIndex()` là chỉ số tham số, không phải số thứ tự validation group.
- `MethodDescriptor.getReturnValueDescriptor()` mô tả constraint/cascade áp dụng lên giá trị trả về.
- `getCrossParameterDescriptor()` mô tả constraint kiểm tra **tương quan giữa nhiều tham số** của cùng executable, khác với một constraint trên từng parameter.
- `getConstrainedMethods(MethodType.GETTER, MethodType.NON_GETTER)` hỗ trợ liệt kê phương thức theo loại.
- `getConstraintsForConstructor(ParamType.class, ...)` và `getConstrainedConstructors()` dùng cách tương tự cho constructor.

`BeanDescriptor.isBeanConstrained()` không xét riêng method/constructor constraint. Một lớp có duy nhất `void submit(@NotNull String code)` có thể trả `false` với `isBeanConstrained()` nhưng vẫn có `MethodDescriptor` được giới hạn. Nếu xây dashboard kiểm tra “lớp có validation không?”, cần duyệt thêm executables.

**Metadata != intercept method call:** phát hiện `@NotBlank` trên tham số chỉ chứng minh khai báo tồn tại. Để Spring tự validate một lời gọi method, phải có cơ chế method validation tương ứng (ví dụ Spring `@Validated` và cấu hình AOP khi áp dụng). Lời gọi tự thân trong cùng bean có thể bypass proxy. Kiểm tra trực tiếp bằng `ExecutableValidator` là một đường khác với interception.

## 8. Groups, hierarchy và ý nghĩa của bộ lọc

Constraint khai báo không có `groups` tường minh được áp dụng cho `Default`. Với:

~~~java
@NotBlank
@Size(min = 4, max = 12)
@Pattern(
    regexp = "ORD-[A-Z0-9]+",
    groups = Strict.class)
private String code;
~~~

truy vấn metadata:

~~~java
int strictCount = code.findConstraints()
    .unorderedAndMatchingGroups(Strict.class)
    .getConstraintDescriptors()
    .size(); // 1
~~~

Nó không tương đương `validator.validate(bean, Strict.class)` vì:

1. Truy vấn metadata chỉ chọn *khai báo* đáp ứng filter, **không đánh giá bean**.
2. Thực thi validation còn phụ thuộc giá trị, cascade, group conversion, group sequence và các quy tắc chọn validator.
3. Bộ lọc `unorderedAndMatchingGroups(...)` theo hợp đồng API không đảm bảo thứ tự group sequence; không dùng thứ tự các descriptor để suy ra “quy tắc nào chạy trước”.

`Scope.LOCAL_ELEMENT` và `Scope.HIERARCHY` khác nhau khi lớp con kế thừa khai báo từ lớp cha. Mặc định finder xem xét hierarchy; nếu cần mô tả “constraint do riêng class hiện tại khai báo”, áp dụng scope cục bộ. Không dùng `getDeclaredAnnotations()` để thay thế hoàn toàn vì nguồn constraint có thể đến từ các khai báo mapping khác reflection thuần.

## 9. Constraint composition và `getComposingConstraints()`

Một custom constraint có thể **ghép** nhiều constraint có sẵn. Ví dụ định nghĩa minh họa:

~~~java
@jakarta.validation.constraints.NotBlank
@jakarta.validation.constraints.Size(min = 4, max = 12)
@jakarta.validation.Constraint(validatedBy = {})
@jakarta.validation.ReportAsSingleViolation
@java.lang.annotation.Target({
    java.lang.annotation.ElementType.FIELD,
    java.lang.annotation.ElementType.METHOD,
    java.lang.annotation.ElementType.PARAMETER,
    java.lang.annotation.ElementType.ANNOTATION_TYPE
})
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.RUNTIME)
public @interface StrongCode {
    String message() default "Mã không hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends jakarta.validation.Payload>[] payload()
        default {};
}
~~~

Đây là **định nghĩa annotation rút gọn minh họa**, cần đặt vào file `StrongCode.java`, ở package phù hợp. Các annotation `@NotBlank` và `@Size` đặt **trên annotation định nghĩa** là các composing constraints; `@Constraint(validatedBy = {})` không khai báo validator riêng, do composition thực hiện việc kiểm tra.

Nếu `@StrongCode` được áp trên field và có một `ConstraintDescriptor` tương ứng:

~~~java
ConstraintDescriptor<?> strong = /* descriptor của @StrongCode */;

System.out.println(
    strong.getComposingConstraints().size()); // 2
System.out.println(
    strong.isReportAsSingleViolation()); // true
~~~

Hai descriptor con cho biết `@NotBlank` và `@Size` cùng tham gia. `@ReportAsSingleViolation` khiến việc báo lỗi có thể được gom thành **một vi phạm của constraint tổng hợp** theo quy tắc Jakarta Validation; metadata composing vẫn còn đủ để công cụ phân tích. Trong metadata của composing constraints, các thuộc tính bị override qua `@OverridesAttribute` cũng phải được phản ánh đúng bởi `getAttributes()` và `getAnnotation()`.

Với custom constraint tự triển khai `ConstraintValidator<StrongCode, String>` thay vì chỉ composition, `getConstraintValidatorClasses()` thể hiện các validator được chỉ định bởi annotation. Tuy nhiên, đừng suy ra số lần thực thi `isValid` từ số lượng lớp trong metadata: provider sẽ chọn validator theo kiểu dữ liệu/target và có thể cache instance.

### Repeatable constraint

Nếu áp dụng cùng một loại constraint nhiều lần (ví dụ hai `@Pattern` với quy tắc khác nhau bằng container `@Pattern.List`), mỗi khai báo biểu diễn một ràng buộc riêng. Metadata provider được kỳ vọng trình bày các constraint được chứa theo cơ chế multi-valued constraint annotation, thay vì yêu cầu công cụ tự giải mã mọi container `List` qua reflection. Khả năng viết cú pháp lặp trực tiếp còn phụ thuộc annotation có `@Repeatable` hợp lệ hay không.

Khác biệt dễ nhầm:

- **Composition:** một constraint **bao gồm** các constraint con; đọc `getComposingConstraints()`.
- **Repeatable:** nhiều **khai báo cùng loại** trên một vị trí; đọc tập các `ConstraintDescriptor` áp dụng tại vị trí đó.
- **Cascade:** `@Valid` đi vào object/element khác; đọc `isCascaded()`.
- **Groups:** chọn tập constraint theo mục đích validate; đọc `getGroups()` hoặc dùng `ConstraintFinder`.

## 10. Kết nối với Spring Framework và ứng dụng thực

Trong Spring Boot có `spring-boot-starter-validation`, thường có bean `LocalValidatorFactoryBean` tích hợp Jakarta Validation provider. Khi inject `jakarta.validation.Validator`, chính object này cung cấp `getConstraintsForClass`, còn Spring cung cấp hệ thống bean/configuration và điểm kích hoạt validation. API metadata chuẩn **không** nằm trong `org.springframework.validation.Errors` hay `BindingResult`.

| Việc cần làm | API phù hợp |
|---|---|
| Khám phá constraint khi chưa có dữ liệu | `Validator.getConstraintsForClass(...)` + descriptors |
| Kiểm tra một bean đang có dữ liệu | `Validator.validate(bean)` |
| Xác thực thuộc tính đã có trên bean | `Validator.validateProperty(bean, "field")` |
| Xác thực một giá trị giả định trước khi tạo bean | `Validator.validateValue(MyType.class, "field", value)` |
| Xác thực tham số/return value executable bằng API | `Validator.forExecutables()` |
| Trình bày lỗi sau Spring MVC binding | `BindingResult` / exception handling phù hợp |
| Xem constraint gây ra một vi phạm cụ thể | `ConstraintViolation.getConstraintDescriptor()` |

### Từ `ConstraintViolation` quay lại metadata

Một vi phạm có thể chứa descriptor của constraint khiến nó thất bại:

~~~java
var violations = validator.validate(invalid);

var sizeViolation = violations.stream()
    .filter(v -> v.getConstraintDescriptor()
        .getAnnotation().annotationType() == Size.class)
    .findFirst()
    .orElseThrow();

System.out.println(
    sizeViolation.getConstraintDescriptor()
        .getAttributes().get("min")); // 4

System.out.println(
    sizeViolation.getPropertyPath()); // code
~~~

Đoạn này nằm trong `run(...)` của ví dụ hoàn chỉnh, sau khi khai báo biến `invalid`, và cần `import jakarta.validation.constraints.Size;` đã có trong file. Nó minh họa cầu nối giữa **metadata tĩnh** và **vi phạm trên giá trị thực**: descriptor có các thuộc tính `@Size`, còn `ConstraintViolation` bổ sung đường dẫn lỗi, giá trị, thông báo sau nội suy, root bean v.v.

Một form/schema generator nên dùng metadata API để nhận diện ràng buộc chuẩn, nhưng **không thể tự suy ra đầy đủ mọi quy tắc nghiệp vụ của custom `ConstraintValidator`** từ tên annotation. Ví dụ `@RegisteredInDatabase` có thể cần truy vấn DB và ngữ cảnh hiện hành; metadata chỉ cho biết khai báo/thuộc tính, không biến nó thành schema tĩnh hoàn chỉnh.

### Mã hóa metadata cho UI hoặc API docs

Ứng dụng có thể dựng JSON tài liệu từ `ConstraintDescriptor`, ví dụ với `@Size(min=4,max=12)`:

~~~json
{
  "property": "code",
  "constraint": "Size",
  "attributes": { "min": 4, "max": 12 },
  "groups": ["Default"]
}
~~~

Đây là **minh họa mô hình xuất**, không phải output trực tiếp của Jakarta Validation API. Khi tự serialize descriptor, cần xử lý các kiểu đặc biệt (`Class`, `Class[]`, enum, annotation, nested descriptors), lọc metadata không phù hợp để công bố ra ngoài, và xử lý cycle/đệ quy composition nếu công cụ duyệt cây.

Đừng dùng output tĩnh của metadata làm bằng chứng một request sẽ hợp lệ. `validate` còn phụ thuộc dữ liệu, provider, group/cascade và quy tắc trong validator.

## 11. Bất biến, cache và các giới hạn quan trọng

- **Descriptor là metadata chỉ đọc.** Jakarta Validation mô tả các object descriptor liên quan là immutable; không dùng `getAttributes().put(...)` để “sửa” constraint. Muốn thay quy tắc, sửa declaration/mapping hoặc cấu hình provider rồi khởi tạo lại metadata tương ứng.
- **Metadata không phải kết quả chạy `isValid`.** Một descriptor tồn tại ngay cả khi không có bean; lỗi chỉ phát sinh khi có giá trị không hợp lệ và chạy validation.
- **Provider có thể cache metadata.** Thực hành tốt là sử dụng `Validator`/`ValidatorFactory` được Spring quản lý thay vì tự bootstrap và đóng một factory mỗi request.
- **Nguồn metadata rộng hơn reflection trực tiếp.** Bao gồm khai báo trên field/getter, phần thừa kế, thành phần container, group/cascade và mapping ngoài annotation khi provider hỗ trợ. Đừng mặc định `getDeclaredAnnotations` phản ánh đầy đủ.
- **Tập hợp không có thứ tự ổn định.** `getConstraintDescriptors()`, `getConstrainedProperties()` và các descriptor sets có thể được duyệt theo thứ tự khác nhau. Khi xuất báo cáo hoặc viết test snapshot, tự sắp xếp theo tiêu chí rõ ràng.
- **Phần mở rộng theo provider không portable.** `unwrap(...)` dành cho capability đặc thù; một công cụ muốn tương thích nhiều provider nên ưu tiên API `jakarta.validation.metadata` chuẩn.
- **Không suy ra SQL, regex hay HTML attributes một cách máy móc.** Một annotation custom có thể biểu đạt kiểm tra phức tạp; metadata chỉ công bố các tham số đã khai báo chứ không mô phỏng thuật toán của `isValid`.
- **Không xây logic bảo mật chỉ từ metadata.** Phải thực thi validation phía server; constraint metadata hiển thị ra client là gợi ý UX, không phải rào chắn an ninh.

## 12. Lỗi phổ biến và chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `bean.hasConstraints()` trả `false` dù có `@NotBlank` field | Đang hỏi constraint **cấp class**, không phải property | Xem `isBeanConstrained()`, `getConstrainedProperties()` và property descriptor |
| `getConstraintsForProperty("code")` trả `null` | Sai tên property, property không có constraint/cascade hoặc mapping không được provider tải | Kiểm tra tên JavaBean/property và validator đang sử dụng |
| `getConstraintDescriptors()` rỗng trên property `@Valid` | Cascade không là constraint trực tiếp | Xem `isCascaded()` và metadata kiểu bean được tham chiếu |
| Không nhìn thấy `@NotBlank` trên `List<@NotBlank String>` | Constraint ở **type argument**, không phải trên property trực tiếp | Duyệt `getConstrainedContainerElementTypes()` |
| Metadata đọc khác annotation qua Java reflection | Constraint đến từ getter, inheritance, composition hoặc external mapping | Đọc qua Jakarta provider hiệu lực thay vì chỉ reflection |
| Thiếu `@Pattern` khi lọc `Default` | Constraint khai báo `groups = Strict.class` | Đọc `getGroups()` và truy vấn đúng group |
| Kết quả thay đổi thứ tự | `Set` descriptor không bảo đảm iteration order | Sort theo annotation type/attributes khi hiển thị |
| `getMessageTemplate()` hiện `{...}` | Đây là template chưa nội suy | Dùng `ConstraintViolation.getMessage()` cho thông báo vi phạm thực |
| `getConstraintValidatorClasses()` rỗng với constraint dựng sẵn | Built-in provider có thể cung cấp validator qua cơ chế nội bộ | Không coi danh sách rỗng là thiếu validation |
| `getConstraintsForMethod(...)` trả `null` | Sai chữ ký overload hoặc method không có executable constraint/cascade | Cung cấp chính xác tên và kiểu tham số, kiểm tra annotation |
| Method descriptor có constraint nhưng gọi method không báo lỗi | Metadata không tự thiết lập interception | Cấu hình method validation hoặc gọi `ExecutableValidator` |
| Chuyển annotation sang `javax.validation.*` nhưng Boot 3 không thấy | Không khớp namespace giữa `javax` và `jakarta` | Thống nhất namespace theo Spring 6/Boot 3 và provider |
| Số vi phạm khác số descriptor | Một số constraint không thất bại; cascade/group/sequence và composition ảnh hưởng kết quả | Phân biệt khai báo với evaluation, xem `ConstraintViolation` thực |
| Gọi `findConstraints()` rồi tái sử dụng finder qua thread | `ConstraintFinder` không thread-safe và filter có tính tích lũy | Mỗi truy vấn tạo finder mới, lưu kết quả immutable nếu cần |
| Việc đọc metadata gây lỗi cấu hình | Provider phát hiện constraint/mapping không hợp lệ lúc tạo metadata | Kiểm tra exception và sửa cấu hình constraint nguồn |

## 13. Checklist và bài tập tự kiểm tra

**Checklist khi xây một công cụ đọc constraint:**

1. Lấy `jakarta.validation.Validator` đang dùng thật trong Spring context.
2. Vào `BeanDescriptor` bằng `getConstraintsForClass`; kiểm tra cả class constraints, properties và executable constraints nếu phạm vi công cụ yêu cầu.
3. Với mỗi property, đọc đồng thời `getConstraintDescriptors()`, `isCascaded()` và `getConstrainedContainerElementTypes()`; không bỏ qua nested type argument.
4. Với mỗi `ConstraintDescriptor`, xem annotation type, attributes, message template, groups, payload, composition và chính sách báo lỗi khi liên quan.
5. Chỉ dùng `ConstraintFinder` khi cần filter theo group, source element hoặc hierarchy; tạo finder mới cho mỗi truy vấn.
6. Sắp xếp kết quả trước khi export/test và phân biệt khai báo constraint với vi phạm thực tế.
7. Dùng `ConstraintViolation.getConstraintDescriptor()` khi muốn liên hệ quy tắc đã khai báo với một lỗi runtime.
8. Kiểm thử metadata dưới đúng Spring/Jakarta provider và cấu hình thật của ứng dụng.

**Bài tập 1 — Thêm group:** Gắn `groups = Strict.class` cho `@Size` trên `code`, chạy lại metadata demo. Dự đoán `Default` còn một descriptor (`@NotBlank`), `Strict` có hai (`@Pattern`, `@Size`); chạy validation cho mẫu rỗng và so sánh số vi phạm tương ứng.

**Bài tập 2 — Bỏ cascade:** Bỏ `@Valid` khỏi `customer`. Dự đoán `isCascaded()` thay đổi và số vi phạm `Default` không còn tính `Customer.name`. Nếu property `customer` không có constraint khác, `getConstraintsForProperty("customer")` có thể trả `null`: hãy xử lý trường hợp này an toàn.

**Bài tập 3 — Thay đổi vị trí:** Đưa `@Size` từ field `code` sang getter `getCode()`. Hỏi `getConstraintDescriptors()` của property `code` và `findConstraints().declaredOn(ElementType.FIELD)`; giải thích tại sao hai tập khác nhau mà constraint trên logical property vẫn có hiệu lực.

**Bài tập 4 — Nested element:** Thay `List<@NotBlank String> tags` thành `List<List<@NotBlank String>> tags`. Viết hàm duyệt đệ quy `ContainerElementTypeDescriptor.getConstrainedContainerElementTypes()` để chỉ ra constraint nằm ở lớp container sâu hơn.

**Bài tập 5 — Composition:** Thêm `@StrongCode` vào một property mới. Dùng `getComposingConstraints()` và `isReportAsSingleViolation()` để giải thích sự khác biệt giữa cấu trúc metadata và số lượng violation khi thực thi.

**Ghi nhớ:** `Validator.getConstraintsForClass` mở kho metadata, `BeanDescriptor` dẫn tới vị trí khai báo, `ConstraintDescriptor` mô tả **một quy tắc với tham số hiệu lực**, còn `ConstraintViolation` mô tả **một lần áp dụng quy tắc thất bại trên dữ liệu cụ thể**. Đọc đúng cấp descriptor là nền tảng để viết công cụ tài liệu hóa, kiểm thử và tích hợp validation trong Spring.

## Tài liệu tham khảo chính thức

- [Jakarta Validation 3.1 — Specification, mục Constraint metadata request APIs](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html#constraintmetadata)
- [Jakarta Validation API — package jakarta.validation.metadata](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/package-summary.html)
- [Jakarta Validation API — BeanDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/BeanDescriptor.html)
- [Jakarta Validation API — ConstraintDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ConstraintDescriptor.html)
- [Jakarta Validation API — ElementDescriptor.ConstraintFinder](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ElementDescriptor.ConstraintFinder.html)
- [Jakarta Validation API — ContainerElementTypeDescriptor](https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/metadata/ContainerElementTypeDescriptor.html)
- [Spring Framework — Java Bean Validation integration](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
