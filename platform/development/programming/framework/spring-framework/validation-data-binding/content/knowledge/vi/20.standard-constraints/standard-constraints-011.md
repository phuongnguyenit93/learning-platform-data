# Ngữ nghĩa null và nhu cầu kết hợp nhiều constraint trong Bean Validation

## 1. Vì sao hiểu null là điều kiện tiên quyết?

Khi xây dựng form đăng ký, API tạo đơn hàng hoặc cấu hình nghiệp vụ, một trường dữ liệu thường phải đáp ứng **nhiều điều kiện độc lập**. Ví dụ tên người dùng phải được cung cấp, không toàn khoảng trắng, có từ 3 đến 12 ký tự; tuổi phải có và không nhỏ hơn 18; danh sách nhãn phải có 1–3 phần tử và từng nhãn không được rỗng.

Vấn đề dễ gây lỗi nhất là nhiều constraint Jakarta Bean Validation **cố ý xem `null` là hợp lệ**, vì chúng chỉ kiểm tra một tính chất của **giá trị đã tồn tại**. Ví dụ `@Size(min = 3)` không đồng nghĩa “bắt buộc nhập ít nhất ba ký tự”: nó từ chối chuỗi không null có độ dài 0, 1, 2 nhưng **không từ chối null**. Để quy định trường bắt buộc, cần kết hợp constraint hiện diện phù hợp như `@NotNull`, `@NotEmpty` hoặc `@NotBlank`.

Bài học tập trung vào ba kỹ năng:

1. Đọc đúng ngữ nghĩa của `null`, chuỗi rỗng, chuỗi trắng, collection rỗng và phần tử null.
2. Xếp chồng nhiều constraint độc lập mà không tự suy ra thứ tự thực thi hoặc chỉ có một thông báo lỗi.
3. Chọn giữa **nhiều annotation đặt trực tiếp**, **composed constraint tái sử dụng** và **class-level constraint** khi có điều kiện liên quan nhiều thuộc tính.

Phần hướng dẫn dùng **Jakarta Bean Validation 3.0** (`jakarta.validation.*`), tương thích với dòng Spring Framework 6/Spring Boot 3. Trong dự án Spring 5/Boot 2 cũ, namespace lịch sử có thể là `javax.validation.*`; cần đồng bộ với provider và phiên bản framework.

## 2. Null, “không có dữ liệu”, rỗng và trắng không giống nhau

Trước khi chọn annotation, hãy phân biệt tình trạng của dữ liệu:

| Trạng thái | Ví dụ Java | Ý nghĩa |
| --- | --- | --- |
| Tham chiếu null | `String name = null;` | Không có đối tượng String để kiểm tra nội dung. |
| Chuỗi rỗng | `String name = "";` | Có đối tượng String, độ dài bằng 0. |
| Chuỗi trắng | `String name = "   ";` | Có đối tượng String; chiều dài 3, không chứa chữ có nghĩa theo quy tắc `@NotBlank`. |
| Chuỗi hợp lệ về hình thức | `String name = "Minh";` | Có dữ liệu để áp các quy tắc độ dài và nội dung. |
| Collection null | `List<String> tags = null;` | Danh sách không hiện diện. |
| Collection rỗng | `List<String> tags = List.of();` | Danh sách có mặt nhưng không có phần tử. |
| Collection có phần tử null | `new ArrayList<>(Arrays.asList((String) null))` | Danh sách có một phần tử, giá trị phần tử null. |
| Object con null | `Address address = null;` | Không có bean con để chạy cascade, trừ khi khai báo constraint hiện diện riêng. |

Ở biên HTTP còn có khái niệm **field không được gửi**. JSON không có property, JSON có `"name": null`, JSON có `"name": ""` có thể đi qua deserializer/binding khác nhau. Bean Validation chỉ làm việc trên đối tượng/giá trị ở thời điểm nó được gọi. Vì thế cần xác định quy tắc binding trước khi nghĩ một constraint sẽ phân biệt được mọi trường hợp “thiếu” và “gửi null”.

Ví dụ DTO lưu vào `String` thông thường: field JSON bị bỏ qua có thể để thuộc tính ở null; field JSON khai báo null cũng có thể dẫn đến null. Sau khi bind, `@NotNull` trên property chỉ biết **giá trị Java là null**, không biết client đã gửi property hay chưa. Nếu nghiệp vụ cần phân biệt “vắng mặt” với “đã gửi null” (như PATCH), phải có mô hình input hoặc cơ chế binding theo dõi sự hiện diện.

## 3. Quy tắc của các constraint chuẩn khi giá trị là null

Đừng dùng suy luận “mọi constraint đều bỏ qua null”. **Phải đọc hợp đồng từng annotation.** Nhiều constraint tập trung vào nội dung nên cho phép null, nhưng các constraint về sự hiện diện thì không.

| Constraint chuẩn | `null` có hợp lệ? | Loại kiểm tra chính | Ghi chú |
| --- | --- | --- | --- |
| `@Null` | Có | Bắt buộc giá trị phải null | Mọi giá trị khác null đều vi phạm. |
| `@NotNull` | **Không** | Bắt buộc có giá trị | Không kiểm tra chuỗi rỗng hoặc List rỗng. |
| `@NotEmpty` | **Không** | Chuỗi/mảng/Collection/Map khác null và không rỗng | Chuỗi toàn khoảng trắng vẫn có thể đạt. |
| `@NotBlank` | **Không** | `CharSequence` có ký tự không phải whitespace | Dành cho văn bản, không đặt trực tiếp lên List/Map. |
| `@Size(min, max)` | Có | Độ dài String, mảng, số phần tử Collection, số entry Map | Hai biên được tính là hợp lệ. |
| `@Pattern(regexp)` | Có | Chuỗi khớp regex | Null hợp lệ; chuỗi rỗng phụ thuộc regex. |
| `@Email` | Có | Hình thức email | Chi tiết “địa chỉ hợp lệ” do provider xác định. |
| `@Min` / `@Max` | Có | So sánh ngưỡng số | Không biến mất dữ liệu thành giá trị 0. |
| `@Positive` / `@Negative` | Có | Dấu của giá trị số | Null vẫn hợp lệ. |
| `@Past` / `@Future` | Có | Quan hệ với thời điểm tham chiếu | Null vẫn hợp lệ. |
| `@AssertTrue` / `@AssertFalse` | Có | Giá trị boolean tương ứng | Với `Boolean` wrapper, null hợp lệ. |

Bảng này dựa trên hợp đồng **constraint chuẩn** của Jakarta Bean Validation 3.0. Annotation do ứng dụng hoặc thư viện khác định nghĩa có thể xử lý null khác; cần đọc `ConstraintValidator.isValid(...)`/Javadoc. Ngay cả khi annotation chuẩn cho phép null, các bước **binding, deserialization, gọi method hoặc cấu trúc type** vẫn có thể không cho phép dữ liệu thiếu trước khi validation bắt đầu.

**Ví dụ quan trọng:**

~~~java
@Size(min = 3, max = 12)
private String name;
~~~

Giá trị `null` đạt `@Size`, nhưng `""` (độ dài 0) và `"ab"` (độ dài 2) không đạt. Với:

~~~java
@Email
private String email;
~~~

Giá trị null đạt theo hợp đồng `@Email`; để yêu cầu email phải có mặt, hãy kết hợp constraint bắt buộc. Không mặc định một pattern email nào cũng có thể kiểm tra mọi trường hợp địa chỉ email trong thực tế, bởi chính chuẩn để provider quyết định chi tiết cú pháp hợp lệ.

## 4. So sánh trực tiếp @NotNull, @NotEmpty, @NotBlank và @Size

### 4.1. Với String

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` | `@Size(min=2)` |
| --- | --- | --- | --- | --- |
| `null` | Sai | Sai | Sai | Đạt |
| `""` | Đạt | Sai | Sai | Sai |
| `" "` | Đạt | Đạt | Sai | Sai |
| `"  "` | Đạt | Đạt | Sai | Đạt |
| `"ab"` | Đạt | Đạt | Đạt | Đạt |
| `"abcdef"` | Đạt | Đạt | Đạt | Đạt, nếu không giới hạn max |

`@NotEmpty` kiểm tra chuỗi có độ dài khác 0; nó không coi toàn khoảng trắng là rỗng. `@NotBlank` kiểm tra chuỗi khác null và có ít nhất một ký tự không phải whitespace. `@Size` chỉ xem độ dài và không tự `strip()`.

### 4.2. Với List hoặc Map

~~~java
@NotNull
@Size(min = 1, max = 5)
private List<String> members;
~~~

Diễn giải:

- `null` bị `@NotNull` từ chối, dù riêng `@Size` xem null hợp lệ.
- `List.of()` bị `@Size(min=1)` từ chối.
- List 1–5 phần tử đạt điều kiện số lượng.
- Một phần tử null vẫn được **đếm là một phần tử**. Hai annotation trên không kiểm tra nội dung từng String.

Nếu chủ đích là khác null và không rỗng, có thể dùng:

~~~java
@NotEmpty
@Size(max = 5)
private List<String> members;
~~~

Nhờ `@NotEmpty`, không cần thêm `@NotNull` chỉ để cấm null. Không nên dùng `@NotBlank` trực tiếp trên `List` vì nó không hỗ trợ kiểu Collection theo chuẩn.

### 4.3. @Null có ý nghĩa riêng

`@Null` không phải viết tắt của “cho phép null”; nó yêu cầu **giá trị phải null**. Ví dụ một trường server quản lý mà client chưa được tự cung cấp:

~~~java
@Null(message = "id must not be supplied on create")
private Long id;
~~~

Cần import `jakarta.validation.constraints.Null`. Giá trị null hợp lệ; giá trị 123 không hợp lệ. Với DTO cập nhật, có thể muốn `id` khác null bằng `@NotNull` trong một nhóm khác. Không nên đặt `@Null` và `@NotNull` đồng thời trong **cùng nhóm** trên một field rồi mong có một giá trị thỏa cả hai: chúng mâu thuẫn logic. Muốn dùng chung lớp cho create/update, phải thiết kế nhóm validation khác nhau hoặc dùng DTO riêng.

## 5. Khi nào phải kết hợp nhiều constraint?

Mỗi annotation trả lời một câu hỏi hẹp. Một trường bắt buộc và có chất lượng dữ liệu thường cần hơn một câu hỏi:

| Yêu cầu nghiệp vụ | Khai báo gợi ý | Vì sao |
| --- | --- | --- |
| Tên phải có chữ, từ 3 đến 40 đơn vị UTF-16 | `@NotBlank @Size(min=3,max=40)` | Bắt buộc nội dung và kiểm tra độ dài. |
| Mã sản phẩm bắt buộc, dài 4–8 và chỉ chữ hoa/chữ số | `@NotBlank @Size(min=4,max=8) @Pattern(regexp="[A-Z0-9]+")` | Presence, length, format là ba quy tắc. |
| Email bắt buộc, không trắng, tối đa 254 ký tự | `@NotBlank @Email @Size(max=254)` | Cần presence, định dạng và giới hạn độ dài. Con số max là quyết định nghiệp vụ/giao thức. |
| Tuổi phải có và tối thiểu 18 | `@NotNull @Min(18) Integer age` | `@Min` một mình chấp nhận null. |
| Danh sách bắt buộc có 1–3 nhãn, mỗi nhãn không trắng | `@NotEmpty @Size(max=3) List<@NotBlank String> labels` | Hai cấp: collection và phần tử. |
| Địa chỉ bắt buộc có và được validate sâu | `@NotNull @Valid Address address` | `@Valid` chỉ cascade khi có bean con. |
| Trường chỉ được hệ thống điền khi tạo | `@Null Long id` | Khách hàng không được gửi ID đã có giá trị. |

Khi các yêu cầu **độc lập**, việc đặt nhiều constraint ngay trên field là cách rõ ràng nhất. Không cần tạo annotation tùy biến cho mọi bộ đôi `@NotNull @Min`. Chỉ cân nhắc composed constraint khi cùng một hợp đồng được dùng nhiều nơi, cần tên thống nhất hoặc cần ánh xạ thông báo lỗi tập trung.

### Ví dụ String theo từng bước

1. `@Size(min=3,max=12)`: có giá trị thì phải đúng độ dài; null được chấp nhận.
2. `@NotNull @Size(min=3,max=12)`: bắt buộc khác null; nhưng `""` và `"  "` vẫn cần xét theo độ dài, không đảm bảo có chữ.
3. `@NotBlank @Size(min=3,max=12)`: bắt buộc có nội dung không chỉ whitespace và đủ độ dài.
4. Thêm `@Pattern(regexp="[A-Za-z0-9_]+")` nếu cần giới hạn ký tự; chú ý quy tắc này cố ý chỉ cho phép ASCII. Tên người Việt có dấu sẽ không khớp regex này.

Lưu ý: **Nhiều constraint không phải một chuỗi xử lý có thứ tự như if/else.** Provider có thể kiểm tra các constraint của cùng group theo thứ tự không xác định; với một giá trị, có thể phát sinh nhiều `ConstraintViolation` đồng thời.

## 6. Validation không tự chuẩn hóa, sửa hoặc tạo dữ liệu

Annotation chỉ mô tả điều kiện; chúng không mặc định thay đổi giá trị.

~~~java
@NotBlank
@Size(min = 3, max = 12)
private String username;
~~~

Nếu username là `"  An  "`, nó có 6 đơn vị UTF-16 và không toàn khoảng trắng; hai constraint đều đạt, dù phần còn lại sau `strip()` là `"An"` có độ dài 2. Nếu muốn đánh giá sau khi trim, phải chuẩn hóa tại boundary được xác định rõ rồi validate kết quả, hoặc viết constraint dựa trên nghiệp vụ đó. Không tự trim password, mã ký, hoặc dữ liệu mà khoảng trắng có ý nghĩa.

Tương tự:

- `@NotNull` không tự tạo instance khi đối tượng con null.
- `@NotEmpty` không tự thêm phần tử vào danh sách.
- `@Size(max=5)` không xóa phần tử thứ sáu.
- `@Email` không tự sửa tên miền.
- `@Min(18)` không tự nâng giá trị 16 lên 18.
- `@Valid` không tự tạo bean con để cascade.

Với dữ liệu HTTP, **hàm chuyển đổi kiểu hoặc deserializer** có thể biến String thành Integer, chuỗi ngày thành `LocalDate`, hoặc giá trị thiếu thành trạng thái Java khác trước validation. Hãy test toàn bộ pipeline, không chỉ nhìn annotation.

## 7. @Valid và null ở object lồng nhau

`@Valid` yêu cầu Bean Validation đi vào các constraint của đối tượng được tham chiếu; theo chuẩn, **null reference được bỏ qua khi cascade**.

~~~java
class CustomerForm {
    @Valid
    Address address;
}

class Address {
    @NotBlank
    String city;
}
~~~

Trong ví dụ này, `address == null` không tự tạo vi phạm từ `Address.city`. Không có đối tượng `Address` để validate. Nếu địa chỉ bắt buộc:

~~~java
class CustomerForm {
    @NotNull(message = "address is required")
    @Valid
    Address address;
}
~~~

Khi `address == null`, `@NotNull` từ chối và `@Valid` bỏ qua. Khi `address != null` nhưng `address.city == ""`, Bean Validation cascade đến `Address.city`, `@NotBlank` từ chối và đường dẫn vi phạm thường là `address.city`.

Đây là quy tắc rất quan trọng trong API object graph: **bắt buộc có object** và **đối tượng đã có phải hợp lệ** là hai yêu cầu riêng. Nếu ứng dụng cho phép address vắng mặt, chỉ dùng `@Valid` có thể là chính sách đúng; đừng luôn ghép `@NotNull` nếu không có yêu cầu nghiệp vụ.

### List và Map có nhiều mức null

~~~java
@NotEmpty
@Size(max = 5)
private List<@NotBlank String> tags;
~~~

- Danh sách null: `@NotEmpty` thất bại.
- Danh sách rỗng: `@NotEmpty` thất bại.
- Danh sách bốn phần tử hợp lệ: đạt cả hai constraint ở cấp List.
- Danh sách bốn phần tử, một String null: cấp List vẫn đạt; `@NotBlank` ở phần tử null thất bại.
- Danh sách sáu phần tử, có một String trắng: `@Size(max=5)` thất bại và constraint phần tử có thể cũng thất bại.

Với bean con:

~~~java
@NotEmpty
private List<@NotNull @Valid Address> addresses;
~~~

Ràng buộc phần tử `@NotNull` cấm phần tử null, còn `@Valid` kiểm tra thuộc tính của từng Address **khác null**. Cần xác định rõ List null, List rỗng và item null là ba tình huống khác nhau.

Với Map:

~~~java
@NotEmpty
private Map<@NotBlank String, @NotNull @Valid Address> contacts;
~~~

Map phải có entry, key phải không trắng, value phải không null, value khác null được cascade. `@NotEmpty` chỉ đếm Map, không tự xét key/value. Đường dẫn vi phạm có thể chứa Map key hoặc node container element; khi dùng `getPropertyPath()`, đừng mặc định nó chỉ có tên field đơn giản.

## 8. Xếp chồng constraint: độc lập, không đảm bảo “chạy cái nào trước”

Ví dụ:

~~~java
@NotBlank(message = "name is required")
@Size(min = 3, max = 12,
      message = "name must have 3..12 characters")
private String name;
~~~

Khi `name = ""`:

- `@NotBlank` thất bại vì giá trị rỗng.
- `@Size(min=3)` cũng thất bại vì độ dài 0.
- `Validator.validate(bean)` có thể trả **hai `ConstraintViolation`** cho cùng property `name`.

Khi `name = null`:

- `@NotBlank` thất bại.
- `@Size` đạt theo hợp đồng cho phép null.
- Có thể chỉ nhận một vi phạm từ cặp constraint này, nếu không có ràng buộc nào khác trên property.

Khi `name = "ab"`:

- `@NotBlank` đạt.
- `@Size(min=3)` thất bại.

Tập kết quả là `Set<ConstraintViolation<T>>`, không bảo đảm thứ tự. Đừng viết logic kiểu “lấy violation đầu tiên là lỗi bắt buộc” hoặc “nếu `@NotBlank` sai thì `@Size` không chạy” khi chưa cấu hình một cơ chế thứ tự rõ ràng.

### Nhiều lỗi trên cùng field có lợi hay hại?

Mỗi lỗi chứa metadata riêng, hữu ích cho test và chẩn đoán. Tuy nhiên UI thường chỉ muốn **một thông điệp ưu tiên** cho mỗi field (chẳng hạn “Vui lòng nhập tên” khi tên rỗng, thay vì hai thông báo liên tiếp). Bạn có thể:

1. Giữ đầy đủ tập vi phạm ở backend và sắp xếp/ưu tiên khi hiển thị.
2. Dùng group sequence khi nghiệp vụ yêu cầu validate theo giai đoạn.
3. Định nghĩa **composed constraint** với `@ReportAsSingleViolation` khi một hợp đồng thống nhất cần báo một lỗi tổng hợp.

Đây là ba cơ chế khác nhau; không nên chọn group sequence chỉ để thay một chiến lược hiển thị lỗi đơn giản.

## 9. Ví dụ runnable Java 17: null, nhiều constraint và lỗi lồng nhau

Ví dụ này chạy **Java 17 + Maven**, sử dụng **Jakarta Bean Validation 3.0** với provider **Hibernate Validator 8.0.6.Final**. Ta triển khai một constraint tổng hợp `@RequiredCode` ở mục kế tiếp, rồi thử dữ liệu có nhiều lỗi, dữ liệu null và dữ liệu hợp lệ.

Cấu trúc:

~~~text
null-constraint-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── RequiredCode.java
    │   └── NullCompositionDemo.java
    └── test/java/demo/
        └── NullCompositionDemoTest.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>null-constraint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.6.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`hibernate-validator` cung cấp provider thực thi; API Jakarta đi kèm qua dependency. `expressly` cung cấp Jakarta Expression Language cho message interpolation trong ứng dụng Java SE độc lập. Với Spring Boot có dependency management và starter validation, cách quản lý dependency khác và thường không cần pin các version như ví dụ.

### 9.1. Tệp RequiredCode.java

~~~java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import jakarta.validation.ReportAsSingleViolation;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

@NotBlank
@Size(min = 4, max = 8)
@Pattern(regexp = "[A-Z][A-Z0-9]*")
@Constraint(validatedBy = {})
@ReportAsSingleViolation
@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Documented
public @interface RequiredCode {
    String message() default
        "code must contain 4..8 uppercase letters/digits and start with a letter";

    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Hợp đồng `@RequiredCode`:

- Giá trị phải không null, không rỗng, không chỉ trắng nhờ `@NotBlank`.
- Giá trị phải dài 4–8 đơn vị UTF-16 nhờ `@Size`.
- Giá trị phải bắt đầu bằng chữ hoa `A–Z`, sau đó chỉ có chữ hoa hoặc số nhờ `@Pattern`.
- `@ReportAsSingleViolation` yêu cầu báo **một violation tổng hợp** thay cho các violation riêng của annotation thành phần nếu bất kỳ thành phần nào thất bại.
- `@Constraint(validatedBy = {})` cho thấy annotation này **không có validator riêng**, mà chỉ được cấu thành từ ba constraint khác.

Ta cố ý tách ba quy tắc dù một regex chặt có thể gộp độ dài: mỗi constraint giữ đúng một trách nhiệm, đồng thời minh họa cách composition hoạt động. Đây là một policy dành cho mã ASCII; không nên áp đặt regex này cho tên người dùng tiếng Việt.

### 9.2. Tệp NullCompositionDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class NullCompositionDemo {

    static final class Address {
        @NotBlank(message = "city is required")
        private final String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Registration {
        @NotBlank(message = "name is required")
        @Size(min = 3, max = 12,
              message = "name must have 3..12 characters")
        private final String name;

        @NotNull(message = "age is required")
        @Min(value = 18,
             message = "age must be at least 18")
        private final Integer age;

        @NotNull(message = "labels are required")
        @Size(min = 1, max = 3,
              message = "labels count must be 1..3")
        private final List<
            @NotBlank(message = "label must not be blank")
            String> labels;

        @NotNull(message = "address is required")
        @Valid
        private final Address address;

        @RequiredCode
        private final String code;

        Registration(String name, Integer age,
                     List<String> labels, Address address,
                     String code) {
            this.name = name;
            this.age = age;
            this.labels = labels;
            this.address = address;
            this.code = code;
        }
    }

    static Registration validRegistration() {
        return new Registration(
            "Minh", 20, List.of("java"),
            new Address("Ha Noi"), "A123");
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            Registration invalid = new Registration(
                "", null,
                List.of("", "java", "spring", "api"),
                new Address(" "), "a9");

            Set<ConstraintViolation<Registration>> errors =
                validator.validate(invalid);

            System.out.println("invalid=" + errors.size());
            errors.stream()
                .map(ConstraintViolation::getMessage)
                .sorted()
                .forEach(System.out::println);

            Registration allNull =
                new Registration(null, null, null, null, null);
            System.out.println(
                "allNull=" + validator.validate(allNull).size());

            System.out.println(
                "valid=" +
                validator.validate(validRegistration()).size());
        }
    }
}
~~~

Lệnh chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NullCompositionDemo
~~~

Stdout do code Java tạo ra, không tính log phụ của Maven/provider:

~~~text
invalid=7
age is required
city is required
code must contain 4..8 uppercase letters/digits and start with a letter
label must not be blank
labels count must be 1..3
name is required
name must have 3..12 characters
allNull=5
valid=0
~~~

**Tại sao `invalid=7`?**

1. `name=""` vi phạm `@NotBlank` và `@Size(min=3)`: **2 lỗi độc lập**, cùng property name.
2. `age=null` vi phạm `@NotNull`; `@Min(18)` **chấp nhận null**: **1 lỗi**.
3. `labels` có 4 phần tử nên vi phạm `@Size(max=3)`; phần tử đầu là `""` nên vi phạm `@NotBlank` trên phần tử: **2 lỗi**.
4. `address` khác null nên `@Valid` cascade; `address.city=" "` vi phạm `@NotBlank`: **1 lỗi**.
5. `code="a9"` sai đồng thời độ dài và pattern, nhưng `@RequiredCode` có `@ReportAsSingleViolation` nên chỉ trả **1 lỗi** cho mã.

Tổng: `2 + 1 + 2 + 1 + 1 = 7`. Đầu ra đã sắp xếp `getMessage()` vì Set không cam kết thứ tự. Đường dẫn của lỗi phần tử List do provider xác định, nên ví dụ tránh phụ thuộc biểu diễn String của `Path` trong stdout.

**Tại sao `allNull=5`?**

- `name`: `@NotBlank` từ chối null, `@Size` chấp nhận → 1.
- `age`: `@NotNull` từ chối null, `@Min` chấp nhận → 1.
- `labels`: `@NotNull` từ chối null, `@Size` chấp nhận; không có List để kiểm tra phần tử → 1.
- `address`: `@NotNull` từ chối null, `@Valid` không cascade → 1.
- `code`: `@RequiredCode` từ chối null nhờ `@NotBlank`, nhưng báo một lỗi tổng hợp → 1.

Tổng **5**. `valid=0` xác nhận đủ tất cả điều kiện được áp dụng. Kết quả không phải một quy tắc ngầm “null luôn sai”; lỗi xuất hiện vì ta **chủ động khai báo** ràng buộc hiện diện.

## 10. Kiểm thử null, lỗi trùng field và composed constraint

Tệp `src/test/java/demo/NullCompositionDemoTest.java`:

~~~java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NullCompositionDemoTest {

    @Test
    void samePropertyCanHaveTwoIndependentViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "", 20, List.of("java"),
                new NullCompositionDemo.Address("Ha Noi"), "A123");

            var errors = validator.validate(form);

            assertEquals(2, errors.size());
            assertEquals(
                Set.of("name is required",
                       "name must have 3..12 characters"),
                errors.stream()
                    .map(ConstraintViolation::getMessage)
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void composedCodeConstraintReportsOneViolation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "Minh", 20, List.of("java"),
                new NullCompositionDemo.Address("Ha Noi"), "a9");

            var errors = validator.validate(form);

            assertEquals(1, errors.size());
            var error = errors.iterator().next();
            assertEquals("code", error.getPropertyPath().toString());
            assertEquals(
                "code must contain 4..8 uppercase letters/digits "
                    + "and start with a letter",
                error.getMessage());
        }
    }

    @Test
    void allNullFailsOnlyPresenceConditions() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                null, null, null, null, null);

            var errors = validator.validate(form);

            assertEquals(5, errors.size());
            assertEquals(
                Set.of("name", "age", "labels", "address", "code"),
                errors.stream()
                    .map(v -> v.getPropertyPath().toString())
                    .collect(Collectors.toSet()));
        }
    }

    @Test
    void nestedAndContainerViolationsBothAppear() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var form = new NullCompositionDemo.Registration(
                "", null,
                List.of("", "java", "spring", "api"),
                new NullCompositionDemo.Address(" "), "a9");

            var errors = validator.validate(form);

            assertEquals(7, errors.size());
            assertTrue(errors.stream()
                .anyMatch(v ->
                    v.getPropertyPath().toString()
                        .equals("address.city")));
            assertTrue(errors.stream()
                .anyMatch(v -> v.getMessage()
                    .equals("label must not be blank")));
        }
    }

    @Test
    void validInputHasNoViolation() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            assertTrue(validator.validate(
                NullCompositionDemo.validRegistration()).isEmpty());
        }
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

Với các dependency của dự án mẫu, kỳ vọng **5 test thành công**, không có test thất bại. Test chủ động so sánh tập thông báo/path thay vì vị trí phần tử thứ nhất vì `Set` không có thứ tự xác định. Các test trong tài liệu được rà soát về cú pháp và logic; ở môi trường khác vẫn cần chạy `mvn test` để xác nhận classpath/provider.

Nếu cần kiểm tra một thuộc tính giả lập trước khi tạo object, có thể dùng `validator.validateValue(Registration.class, "name", null)`; kết quả sẽ tuân thủ các annotation trên field name nhưng không có root bean instance. `validateProperty(...)` và `validateValue(...)` không thực thi cascade `@Valid` theo chuẩn; muốn xem cả graph hãy dùng `validate(bean)`.

## 11. Composed constraint là gì và khác xếp chồng ra sao?

Có **hai cách** dùng nhiều quy tắc cho cùng một giá trị:

**Cách A — khai báo trực tiếp từng constraint ở nơi dùng:**

~~~java
@NotBlank
@Size(min = 4, max = 8)
@Pattern(regexp = "[A-Z][A-Z0-9]*")
private String code;
~~~

Mỗi constraint có metadata/message riêng và có thể tạo violation riêng. Thích hợp khi bộ quy tắc chỉ xuất hiện ở một vài nơi hoặc muốn hiển thị từng nguyên nhân cụ thể.

**Cách B — định nghĩa annotation tổng hợp:**

~~~java
@RequiredCode
private String code;
~~~

`@RequiredCode` trong ví dụ runnable có `@NotBlank`, `@Size` và `@Pattern` được khai báo **trên định nghĩa annotation**. Điều kiện mặc định của composed constraint theo Jakarta là **AND**: các thành phần phải cùng đạt. Có thể thêm `@ReportAsSingleViolation` để trả một lỗi tổng hợp thay cho nhiều lỗi thành phần.

**Lưu ý chính xác:**

- Composed constraint **không tự làm thay đổi quy tắc null** của constraint thành phần. `@RequiredCode` từ chối null vì nó **bao gồm `@NotBlank`**. Một composite chỉ gồm `@Size` và `@Pattern` sẽ tiếp tục chấp nhận null.
- `@ReportAsSingleViolation` chỉ điều khiển **cách báo lỗi** của composed constraint (và có thể dừng đánh giá khi phát hiện thành phần đầu tiên sai); nó không biến `null` thành lỗi nếu không có thành phần nào từ chối null.
- Khi không có `@ReportAsSingleViolation`, các constraint thành phần có thể tạo violation riêng; đừng giả định luôn chỉ một thông báo.
- Composed constraint có thể dùng validator riêng cùng các thành phần, nhưng cần tránh chồng quy tắc gây khó hiểu. Với mẫu chỉ dùng composition thuần, `@Constraint(validatedBy = {})` là đúng.
- `groups` và `payload` của các composing constraints tuân theo định nghĩa group/payload ở annotation tổng hợp theo chuẩn. Không coi chúng là những nhãn tự do không liên quan.

Một composed constraint nên mang **tên nghiệp vụ có nghĩa** như `@RequiredCode`, `@ValidSku` hoặc `@StrongPassword`, thay vì tạo tên chung chung mà không nói rõ hợp đồng.

### Khi nào tránh @ReportAsSingleViolation?

Nếu UI cần phân biệt “thiếu mã”, “quá ngắn” và “sai pattern”, báo một lỗi tổng hợp có thể làm giảm thông tin. Khi đó khai báo nhiều constraint trực tiếp hoặc giữ báo lỗi thành phần trong composite. Nếu API cần một thông điệp ổn định cho “mã không hợp lệ”, `@ReportAsSingleViolation` có thể phù hợp.

Đừng dùng composed constraint chỉ để che lỗi cấu hình hoặc vì không muốn đọc `Set<ConstraintViolation<?>>`. Chọn nó khi **một khái niệm nghiệp vụ** thật sự gồm nhiều điều kiện có thể tái sử dụng.

## 12. Group validation: một trường có thể bắt buộc ở bước này và tùy chọn ở bước khác

Nhiều form có các thao tác **create**, **update**, **draft** khác nhau. Trong bản nháp, địa chỉ có thể null; khi phát hành đơn, địa chỉ trở thành bắt buộc. Có thể dùng nhóm validation.

Ví dụ minh họa:

~~~java
interface Create {}
interface Update {}

class Command {
    @Null(groups = Create.class)
    @NotNull(groups = Update.class)
    Long id;

    @NotBlank(groups = {Create.class, Update.class})
    String name;
}
~~~

Đoạn này cần imports `jakarta.validation.constraints.Null`, `NotNull`, `NotBlank`. Khi `id=null`, kiểm tra nhóm Create cho phép id nhưng nhóm Update từ chối. Khi `id=123L`, kết quả ngược lại với riêng ràng buộc id. Có thể gọi:

~~~java
validator.validate(command, Create.class);
validator.validate(command, Update.class);
~~~

Đây là đoạn minh họa dùng biến `validator`, `command`. Cần hiểu:

- Không truyền group thì `validate(bean)` dùng nhóm mặc định `Default`.
- Truyền `Create.class` riêng **không tự động** cộng thêm mọi constraint thuộc `Default`.
- Nếu muốn kiểm tra đồng thời nhiều group có thể truyền nhiều lớp group, nhưng thứ tự đánh giá không được bảo đảm nếu không dùng sequence.
- `@GroupSequence` có thể định nghĩa trình tự nhóm; khi nhóm trước có vi phạm, nhóm sau trong sequence sẽ không được đánh giá theo quy tắc. Đây là cơ chế về **phạm vi và thứ tự validation**, không chỉ trình bày UI.
- Trong Spring có `@Validated(Group.class)` để yêu cầu group cụ thể ở những điểm tích hợp phù hợp. `@Valid` đơn thuần không tự chọn group tùy biến.

Khi yêu cầu create/update khác nhau quá nhiều, **hai DTO riêng** thường rõ hơn so với một DTO có hàng loạt group chồng chéo. Không dùng group để che việc API yêu cầu hai hợp đồng dữ liệu khác nhau.

## 13. Sự khác biệt giữa “constraint kết hợp” và “kiểm tra liên quan nhiều field”

Xếp chồng `@NotBlank @Size @Pattern` đủ cho điều kiện **trên một giá trị**. Nhưng một số luật nghiệp vụ phụ thuộc hai hoặc nhiều field:

- `startDate <= endDate`.
- Nếu `deliveryMethod = "SHIP"` thì `shippingAddress` bắt buộc.
- Nếu `paymentType = "CARD"` thì `cardToken` bắt buộc.
- Tổng `minQuantity` không được lớn hơn `maxQuantity`.

Không thể diễn đạt đầy đủ các quan hệ này bằng cách chỉ đặt `@NotNull` hoặc `@Size` ở một field mà không xem field khác. Cân nhắc **class-level constraint** với `ConstraintValidator<CustomAnnotation, BeanType>`, hoặc validation ở tầng nghiệp vụ. Ví dụ minh họa logic:

~~~java
boolean isValidBooking(Booking booking) {
    if (booking == null) {
        return true; // Chính sách nếu constraint này chấp nhận null.
    }
    if (booking.startDate() == null ||
        booking.endDate() == null) {
        return true; // Dành null cho @NotNull riêng nếu bắt buộc.
    }
    return !booking.startDate().isAfter(booking.endDate());
}
~~~

Đây là **pseudocode dạng method minh họa**, cần lớp/record `Booking` và phương thức truy cập tồn tại; nó chưa phải một implementation độc lập của `ConstraintValidator`. Trong class-level validator thật, phải chọn cách trả violation và `ConstraintValidatorContext`. Nếu muốn lỗi gắn vào `endDate` thay vì lỗi cấp object, có thể tạo property node qua `buildConstraintViolationWithTemplate(...).addPropertyNode("endDate")...`.

**Tại sao return true khi có null?** Đây là một chiến lược thường dùng để tách validation: constraint quan hệ chỉ chạy khi đủ hai giá trị, còn constraint bắt buộc riêng xử lý null. Nó **không phải luật bắt buộc** cho mọi custom validator. Nếu điều kiện nghiệp vụ quy định thiếu một trong hai field là vi phạm chính của class-level constraint, có thể trả false; phải diễn đạt rõ hợp đồng và test.

## 14. Spring MVC và Spring Boot: nhiều annotation chạy khi nào?

Đặt annotation trên DTO chỉ có hiệu lực khi có Bean Validation provider và validation được **kích hoạt** tại boundary.

Trong ứng dụng Spring Boot 3 có quản lý dependency, thường dùng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Đoạn XML này là dependency để thêm vào dự án Boot; phiên bản được quản lý bởi parent/BOM Boot, không phải phiên bản độc lập ở mục 9.

Ví dụ DTO:

~~~java
public class SignupRequest {
    @NotBlank
    @Size(min = 3, max = 12)
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    @NotEmpty
    @Size(max = 3)
    private List<@NotBlank String> labels;

    // Getters/setters hoặc cơ chế binding phù hợp.
}
~~~

Đây là **đoạn DTO minh họa**, cần imports tương ứng. Controller:

~~~java
@PostMapping("/signup")
public ResponseEntity<Void> signup(
        @Valid @RequestBody SignupRequest request) {
    // Xử lý khi request đã qua validation.
    return ResponseEntity.noContent().build();
}
~~~

Đây là **đoạn controller minh họa**, cần imports Spring Web MVC và DTO trong cùng ứng dụng. Với Spring MVC thông thường, `@Valid @RequestBody` kiểm tra object; lỗi validation đối số có thể đưa đến `MethodArgumentNotValidException` nếu không có `Errors`/`BindingResult` ngay sau tham số và không có method validation cấp method thay thế.

Khi có constraint trực tiếp trên tham số method (như `@Min` trên `@RequestParam Integer page`), Spring MVC 6.1+ có built-in method validation, có thể ném `HandlerMethodValidationException`. Với service method qua `@Validated` và AOP, mặc định có thể nhận `jakarta.validation.ConstraintViolationException` nếu method validation thực sự hoạt động qua proxy. **Không bắt một loại exception duy nhất rồi kết luận đã bao phủ mọi lỗi Bean Validation trong Spring.**

### Điểm đặc biệt của null trong HTTP binding

- `@RequestBody(required = true)` có cơ chế yêu cầu body ở Spring MVC; khi thiếu body, lỗi có thể xảy ra **trước Bean Validation**.
- `@RequestParam(required = true)` cũng có quy tắc hiện diện riêng.
- JSON body có `"name": null` khác với toàn bộ request body không có. Sau binding, `@NotBlank` sẽ từ chối field name null.
- Nếu JSON không có `age` và DTO để `Integer age = null`, `@NotNull` xử lý trạng thái đó. Nhưng nếu dùng primitive `int`, không thể biểu diễn null bằng field; kết quả deserialization/binding cần được kiểm tra. Ưu tiên wrapper ở biên khi cần phát hiện thiếu giá trị.
- Lỗi chuyển đổi kiểu, ví dụ chuỗi chữ vào trường số, có thể xảy ra trước `@Min` hoặc `@NotNull`. Spring có cơ chế errors riêng; đừng kỳ vọng mọi lỗi format đều tạo `ConstraintViolation`.

### Nhiều lỗi trên một field khi trả API

Nếu `name=""`, một request có thể tạo vi phạm cho cả `@NotBlank` và `@Size`. Thiết kế response:

~~~json
{
  "errors": [
    {"field": "name", "code": "REQUIRED", "message": "Vui lòng nhập tên"},
    {"field": "name", "code": "SIZE", "message": "Tên phải dài 3-12 ký tự"}
  ]
}
~~~

Đây là ví dụ **dạng dữ liệu**, không phải kết quả HTTP tự động của Spring. Nếu muốn chỉ một lỗi cho mỗi field, API cần quy tắc ưu tiên hiển thị; backend vẫn có thể giữ đầy đủ `BindingResult`/`ConstraintViolation` để phục vụ kiểm thử và log an toàn. `getMessage()` có thể được địa phương hóa; mã lỗi như `REQUIRED` nên do API chủ động quy định thay vì gắn chặt vào chuỗi thông điệp provider.

## 15. Khi nào kết hợp constraint làm mất thông tin?

Sử dụng nhiều constraint có ba rủi ro cần cân nhắc:

1. **Thông điệp trùng lặp:** `@NotBlank` và `@Size(min=3)` cùng sai khi chuỗi rỗng. Có thể hiển thị một thông báo ưu tiên; không cần bỏ constraint chỉ vì UI muốn một lỗi.
2. **Điều kiện mâu thuẫn:** `@Null` và `@NotNull` trong một group không có giá trị chung thỏa mãn; `@Size(min=10,max=5)` là metadata sai; một `@Pattern` có thể mâu thuẫn với giới hạn độ dài. Kiểm tra logic kết hợp ngay từ lúc thiết kế.
3. **Bỏ sót null do chọn sai annotation:** `@Size(min=1)` chỉ từ chối List rỗng nhưng chấp nhận List null, `@Min(18)` chỉ kiểm tra Integer hiện diện, `@Valid` không bắt buộc có bean con. Cần ghi rõ yêu cầu “optional hay required” cho từng field.

Thêm vào đó, nhiều constraint có thể tác động đến hiệu suất (ví dụ kiểm tra dữ liệu lớn, gọi remote service trong custom validator). Validator nên chủ yếu kiểm tra dữ liệu cục bộ và không gây hiệu ứng phụ; quy tắc đòi hỏi I/O hoặc race-sensitive business state thường cần được xác minh lại ở tầng nghiệp vụ. Không dựa vào thứ tự thực thi giữa các annotation để tránh lỗi logic.

## 16. Exception, fail-fast và group sequence ảnh hưởng kết quả thế nào?

`Validator.validate(bean)` **trả tập `Set<ConstraintViolation<T>>`**. Nó không tự ném `ConstraintViolationException` chỉ vì một field sai. Exception này có thể do ứng dụng tự ném hoặc cơ chế method validation/integration tạo ra.

~~~java
Set<ConstraintViolation<MyForm>> errors =
    validator.validate(form);
if (!errors.isEmpty()) {
    throw new ConstraintViolationException(
        "Invalid form", errors);
}
~~~

Đây là đoạn minh họa yêu cầu `MyForm`, `validator` và imports `jakarta.validation.*`, không phải chương trình độc lập. Không áp logic xử lý input sai tương tự cho mọi `ValidationException`: provider configuration/constraint declaration sai có thể là lỗi lập trình, cần được phân loại riêng.

Một số trường hợp khiến kết quả không có đầy đủ mọi violation:

- **Chỉ validate group được yêu cầu.** Với `validate(bean, Create.class)`, group Default không được tự cộng vào trừ khi có định nghĩa quan hệ phù hợp.
- **Group sequence dừng tại group lỗi.** Nếu một group có vi phạm, nhóm sau trong sequence không được kiểm tra theo quy tắc.
- **Hibernate Validator có tùy chọn fail-fast**, không phải contract portable của mọi provider. Khi bật, provider có thể dừng sớm sau vi phạm được phát hiện; không được giả định trình tự chọn “vi phạm đầu tiên”.
- **`@ReportAsSingleViolation`** thay thế nhiều thông điệp của constraint thành phần bằng một thông điệp tổng hợp và có thể dừng khi gặp thành phần sai.
- **`@Valid` không đi qua null object** hoặc null collection, nên không thể phát hiện lỗi sâu của giá trị không hiện diện.
- **`validateProperty(...)`/`validateValue(...)` không cascade** nên tập có thể khác `validate(bean)`.

Vì vậy đừng diễn giải `errors.isEmpty()` là “mọi dữ liệu nghiệp vụ, mọi group, mọi tầng đều hợp lệ” trong mọi tình huống. Nó cho biết **không có violation trong phạm vi validation đã thực sự chạy**.

## 17. Các lỗi thường gặp và hướng khắc phục

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ đặt `@Size(min=1)` rồi tưởng trường bắt buộc | Null vẫn đạt. | Dùng `@NotNull`, `@NotEmpty` hoặc `@NotBlank` theo kiểu/ý nghĩa. |
| Chỉ đặt `@Email` rồi tưởng email bắt buộc | Null được xem hợp lệ. | Kết hợp constraint hiện diện khi email required. |
| Dùng `@NotNull` để cấm chuỗi trống | `""` khác null nên vẫn đạt. | Dùng `@NotBlank` cho văn bản có nghĩa. |
| Dùng `@NotEmpty` để cấm chuỗi toàn trắng | `"   "` khác rỗng nên có thể đạt. | Dùng `@NotBlank`. |
| Dùng `@NotBlank` lên `List` hoặc `Map` | Không có validator chuẩn cho kiểu đó. | Dùng `@NotEmpty` hoặc `@Size` cho container. |
| Gắn `@Valid` rồi nghĩ object con là bắt buộc | Cascade bỏ qua null. | Thêm `@NotNull` nếu thực sự bắt buộc. |
| Dùng `@Size(max=3) List<...>` để cấm phần tử null | Chỉ đếm số phần tử. | Dùng `List<@NotNull Element>` hoặc constraint phù hợp phần tử. |
| Viết thứ tự annotation rồi nghĩ đó là thứ tự kiểm tra | Provider không cam kết thứ tự cùng group. | Dùng group sequence đúng mục đích hoặc ưu tiên lỗi ở UI. |
| Chỉ lấy `violations.iterator().next()` | Set không có thứ tự xác định. | Sort hoặc xử lý toàn bộ tập. |
| Dùng `@ReportAsSingleViolation` khi cần hiển thị nguyên nhân riêng | Mất chi tiết lỗi của các composing constraint. | Cân nhắc báo lỗi riêng hoặc giữ metadata ở tầng khác. |
| Nghĩ composite `@Pattern @Size` tự từ chối null | Cả hai có thể chấp nhận null. | Thêm `@NotNull`/`@NotBlank` khi required. |
| Ghép `@Null` và `@NotNull` trong cùng group | Không có giá trị thỏa cả hai. | Tách nhóm create/update hoặc DTO riêng. |
| Tin `@Min(18)` đã cấm Integer null | `@Min` cho phép null. | Thêm `@NotNull`. |
| Tin `@RequestBody @Valid` và lỗi binding đều là một loại exception | Spring có nhiều đường lỗi và conversion trước validation. | Test cả `MethodArgumentNotValidException`, method validation và lỗi chuyển kiểu. |
| Dùng primitive `int` để phân biệt field không gửi với số 0 | Primitive không biểu diễn null. | Dùng wrapper hoặc model hiện diện rõ ràng. |
| Log hoặc trả `getInvalidValue()` thẳng lên client | Có thể lộ thông tin nhạy cảm. | Chỉ dùng field/code/message đã được kiểm soát. |
| Đọc message hiển thị như mã lỗi cố định | Message phụ thuộc locale/interpolator. | Định nghĩa mã lỗi ổn định riêng. |
| Giới hạn string bằng `@Size` rồi nghĩ đã giới hạn byte HTTP/DB | Java String length không bằng byte length. | Tách validation logic khỏi giới hạn request/storage. |

## 18. Checklist thiết kế và tự kiểm tra

Trước khi giao một request DTO hoặc domain object, hãy trả lời:

1. Field này **có được vắng mặt** không? Nếu không, dùng constraint hiện diện phù hợp.
2. Giá trị `null`, `""`, `"   "`, List rỗng, Map rỗng có ý nghĩa khác nhau không?
3. Nếu là String, cần kiểm tra **nội dung**, **độ dài**, **pattern** và **chuẩn hóa** ở mức nào?
4. Nếu là số, dùng wrapper để phát hiện thiếu dữ liệu hay primitive với mặc định có chủ đích?
5. Nếu là Collection/Map, cần bắt buộc container có mặt và kiểm tra từng phần tử/key/value riêng không?
6. Nếu là bean con, `@Valid` có cần ghép `@NotNull` không?
7. Các constraint được đặt đúng **group** và có cần group sequence thật sự không?
8. Có nên trả nhiều violation chi tiết hay một violation tổng hợp? Nếu một, nên xử lý ở UI hay định nghĩa composed annotation?
9. API có phân biệt lỗi binding/chuyển kiểu với lỗi Bean Validation không?
10. Test đã có null, thiếu property, rỗng, trắng, sát min/max, phần tử null, object con null, nhiều lỗi cùng field chưa?
11. Có test khi dùng `@Validated(Group.class)` trong Spring để bảo đảm đúng nhóm?
12. Khi truyền thông điệp cho client, đã tách mã lỗi ổn định và loại bỏ giá trị nhạy cảm chưa?

**Câu hỏi ôn tập**

1. `@Size(min=3) String name` có từ chối `name=null` không?
2. `@Email String email` có làm email bắt buộc không?
3. `@NotEmpty` và `@NotBlank` khác nhau thế nào khi giá trị là `"   "`?
4. `@Valid Address address` có chạy `Address.city` nếu `address=null` không?
5. `@NotEmpty List<@NotBlank String> labels` bảo đảm điều gì ở hai cấp?
6. Tại sao `@NotBlank` và `@Size(min=3)` có thể trả hai violation với `""`?
7. `@ReportAsSingleViolation` có tự biến một composite chỉ gồm `@Pattern` và `@Size` thành required field không?
8. Một field có thể `@Null` khi tạo và `@NotNull` khi cập nhật bằng cách nào?
9. Vì sao không thể dùng thứ tự duyệt `Set<ConstraintViolation<T>>` làm thứ tự ưu tiên UI?

**Đáp án:** (1) Không; (2) Không; (3) cả hai từ chối null/rỗng nhưng `@NotBlank` còn từ chối toàn whitespace; (4) Không, cascade bỏ qua null; (5) List có mặt và không rỗng, từng String không trắng; (6) hai constraint độc lập cùng thất bại; (7) Không, cần một thành phần từ chối null như `@NotBlank`; (8) tách group Create/Update hoặc DTO riêng; (9) vì Set không cam kết thứ tự.

## 19. Tài liệu tham khảo chính thức

- Jakarta Bean Validation 3.0 — Specification (định nghĩa constraint chuẩn, null, composition và graph validation): https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `NotNull`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotNull.html
- Jakarta Bean Validation 3.0 API — `NotEmpty`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotEmpty.html
- Jakarta Bean Validation 3.0 API — `NotBlank`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/NotBlank.html
- Jakarta Bean Validation 3.0 API — `Size`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/constraints/Size.html
- Jakarta Bean Validation 3.0 API — `ReportAsSingleViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ReportAsSingleViolation.html
- Hibernate Validator 8.0 — Reference Guide (composition, container elements, fail-fast, groups): https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Bean Validation Integration: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
