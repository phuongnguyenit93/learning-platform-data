# Vấn đề nhiều giá trị trên cùng một vị trí: vì sao Java cần annotation lặp?

Một annotation thường mô tả **một tập metadata** gắn vào khai báo Java. Tuy nhiên, có những trường hợp **cùng một khai báo** cần nhiều giá trị độc lập cho **cùng một loại annotation**: một phương thức có nhiều lịch chạy, một class được gán nhiều nhãn, hoặc một endpoint có nhiều quy tắc truy cập. Đây là vấn đề dẫn đến cơ chế **repeatable annotation**, được Java hỗ trợ từ Java 8.

Cần phân biệt hai nhu cầu:

1. **Một annotation chứa nhiều giá trị của một element kiểu mảng**, ví dụ `@Labels({"public", "internal"})`.
2. **Nhiều lần xuất hiện của cùng một loại annotation tại cùng vị trí**, ví dụ `@Label("public")` và `@Label("internal")` cùng đứng trước một class.

Hai cách này có thể biểu diễn những thông tin tương tự trong trường hợp đơn giản, nhưng chúng có **cấu trúc dữ liệu và quy tắc khai báo khác nhau**.

## 1. “Cùng một vị trí” là gì?

Vị trí ở đây là một **declaration hoặc type-use** được Java cho phép đánh dấu bằng annotation: class, method, field, constructor, parameter, v.v. Tập vị trí hợp lệ còn phụ thuộc `@Target` của từng kiểu annotation.

Ví dụ một class cần hai vai trò:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

Cả hai annotation đều nhằm vào **cùng khai báo `ReportService`**, đều có kiểu `Role`, nhưng giá trị khác nhau. Đây là yêu cầu thường gặp khi cùng một đối tượng được gắn nhiều quy tắc độc lập.

Nếu `Role` chỉ được khai báo như annotation thông thường, **không có `@Repeatable`**, thì hai dòng `@Role(...)` đặt trực tiếp trên cùng class **không biên dịch được**. Giá trị khác nhau không tự khiến Java cho phép dùng lại cùng một kiểu annotation.

Ví dụ tối giản **sai** (chỉ để thấy vấn đề):

```java
@interface Role {
    String value();
}

@Role("reader")
@Role("writer") // Lỗi: Role không phải repeatable annotation
class ReportService {
}
```

Annotation khác loại có thể cùng tồn tại trên một class, ví dụ `@Deprecated` đi cùng `@SuppressWarnings`. Giới hạn đang xét là **lặp lại cùng một loại annotation**, không phải số lượng annotation nói chung.

## 2. Vì sao nhu cầu nhiều giá trị xuất hiện?

Một khai báo đôi khi có nhiều thông tin cùng loại nhưng mỗi thông tin phải đứng độc lập:

| Bối cảnh | Một khai báo | Các giá trị cần mô tả |
| --- | --- | --- |
| Phân quyền | Class dịch vụ | Vai trò `reader`, `writer` |
| Lịch chạy | Một phương thức | Lịch ngày thường và lịch cuối tuần |
| Quy tắc kiểm tra | Một field | Kiểm tra độ dài và kiểm tra mẫu ký tự |
| Định tuyến | Một phương thức | Nhiều nhãn hoặc nhiều cấu hình định tuyến |
| Ánh xạ | Một class | Nhiều cách ánh xạ hoặc chuyển đổi |

Đây là **những tình huống mô hình hóa**; không có nghĩa JDK tự thực hiện phân quyền, lập lịch hay định tuyến nếu có annotation. Mã của framework hoặc ứng dụng phải đọc metadata và áp dụng hành vi tương ứng.

Sự khác biệt giữa một giá trị và nhiều giá trị ảnh hưởng đến cách thiết kế annotation: có nên dùng mảng, tạo container hay làm cho annotation có thể lặp?

## 3. Cách thứ nhất: một annotation chứa mảng

Nếu cần chứa nhiều **giá trị đồng nhất** cho một thuộc tính, element kiểu mảng là một lựa chọn gọn:

```java
@interface Roles {
    String[] value();
}

@Roles({"reader", "writer"})
class ReportService {
}
```

Đây là **một** annotation `@Roles` có element `value()` kiểu `String[]` chứa hai chuỗi. Cú pháp hợp lệ trong Java, kể cả khi kiểu `Roles` không có `@Repeatable`.

Để biểu diễn cùng ý bằng tên element đầy đủ, có thể viết:

```java
@Roles(value = {"reader", "writer"})
class AnotherService {
}
```

Ưu điểm của mảng:

- Dễ khai báo khi mọi giá trị cùng kiểu và cùng ý nghĩa.
- Không cần một kiểu annotation riêng cho từng phần tử.
- Người đọc thấy ngay đây là một tập chuỗi cùng thuộc tính.

Giới hạn của mảng: nếu **mỗi lần áp dụng** mang nhiều metadata đi kèm, một mảng chuỗi không thể hiện tốt từng bộ dữ liệu. Ví dụ một vai trò có `name`, `scope` và `priority`: `{"reader", "writer"}` không cho biết scope nào đi với role nào.

Có thể khắc phục bằng **mảng annotation lồng nhau**, nhưng cú pháp khi dùng dài hơn:

```java
@interface RoleSpec {
    String name();
    String scope();
}

@interface RoleSpecs {
    RoleSpec[] value();
}

@RoleSpecs({
    @RoleSpec(name = "reader", scope = "/reports"),
    @RoleSpec(name = "writer", scope = "/drafts")
})
class CompositeRoleService {
}
```

Đoạn trên chỉ minh họa **một container chứa mảng các annotation `RoleSpec`**. `RoleSpec` **chưa** được khai báo `@Repeatable`, nên không thể thay đoạn trên bằng hai `@RoleSpec` trực tiếp trên class nếu giữ nguyên các khai báo đó.

## 4. Cách thứ hai: đặt trực tiếp nhiều annotation cùng loại

Từ Java 8, Java cho phép khai báo một loại annotation **có thể lặp** (*repeatable*) bằng `@Repeatable`. Khi đó người viết code có thể biểu diễn mỗi giá trị qua một annotation riêng:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

Điểm lợi là cấu trúc **mỗi lần áp dụng một annotation**; mỗi lần mang một bộ thuộc tính như `name`, `scope`, `priority`. Người đọc dễ thêm/bớt một quy tắc mà không sửa một mảng lớn.

Tuy nhiên, `@Repeatable` **không tự hoạt động nếu chưa khai báo container phù hợp**. Để kiểu `Role` có thể lặp, Java yêu cầu một **annotation chứa** (*containing annotation*) có element `value()` trả về **mảng `Role[]`**.

Khung khai báo:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}
```

Ở đây:

- `Role` là **annotation muốn lặp**.
- `Roles` là **container annotation** lưu tập các `Role`.
- `@Repeatable(Roles.class)` liên kết hai loại annotation.
- Element `Roles.value()` có kiểu chính xác `Role[]`, nhờ vậy Java có thể biểu diễn các lần `@Role` chung một vị trí.

Khi dùng hai lần `@Role`, mã nguồn vẫn hiển thị hai annotation độc lập, còn compiler xử lý biểu diễn tương ứng qua container theo quy tắc của ngôn ngữ. Một số chi tiết phụ thuộc retention và target, sẽ được kiểm tra ở ví dụ hoàn chỉnh bên dưới.

## 5. Ví dụ Java 17+ chạy được: hai vai trò trên cùng class

Tạo **một file `RepeatableProblemDemo.java`** chứa toàn bộ mã:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("writer")
class ReportService {
}

public class RepeatableProblemDemo {
    public static void main(String[] args) {
        Role[] roles = ReportService.class.getAnnotationsByType(Role.class);

        System.out.println("count=" + roles.length);
        for (Role role : roles) {
            System.out.println("role=" + role.value());
        }

        boolean hasContainer =
                ReportService.class.getAnnotation(Roles.class) != null;
        System.out.println("container=" + hasContainer);
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp với JDK 17 trở lên:

```bash
javac -encoding UTF-8 RepeatableProblemDemo.java
java RepeatableProblemDemo
```

**Kết quả stdout:**

```text
count=2
role=reader
role=writer
container=true
```

Giải thích từng bước:

1. `@Repeatable(Roles.class)` cho phép viết cùng một annotation `@Role` nhiều lần trên **một class**.
2. `@Target(ElementType.TYPE)` ở hai kiểu annotation giới hạn việc đặt chúng trên khai báo kiểu như `class ReportService`.
3. Cả hai khai báo đều dùng `@Retention(RUNTIME)` để việc đọc metadata qua reflection trong ví dụ hoạt động. Nếu annotation chỉ có retention `SOURCE`, reflection runtime sẽ không đọc được chúng.
4. `getAnnotationsByType(Role.class)` đọc được các annotation `Role` ở dạng trực tiếp hoặc thông qua container, nhờ đó nhận hai giá trị `reader` và `writer`.
5. `getAnnotation(Roles.class)` cho thấy container hiện diện trên class khi có hai lần sử dụng `@Role`. Kết quả `true` không có nghĩa một generator được gọi hay một hệ thống phân quyền được kích hoạt.

Từ ví dụ này có thể thấy: **vấn đề không phải lưu được hai chuỗi hay không** (mảng đã làm được), mà là Java cần hỗ trợ **nhiều lần áp dụng cùng một loại annotation lên một khai báo** mà vẫn có mô hình metadata nhất quán.

## 6. Container và cách viết tường minh

Với các kiểu `Role` và `Roles` đã khai báo, cách viết gắn container trực tiếp cũng hợp lệ:

```java
@Roles({
    @Role("reader"),
    @Role("writer")
})
class ExplicitContainerService {
}
```

Nội dung logic về hai role tương tự ví dụ gắn hai `@Role`, nhưng cú pháp nguồn khác nhau:

| Cách viết | Đặc điểm |
| --- | --- |
| `@Role("reader")` rồi `@Role("writer")` | Gọn, tập trung từng quy tắc; cần `Role` có `@Repeatable(Roles.class)`. |
| `@Roles({@Role("reader"), @Role("writer")})` | Ghi trực tiếp container chứa `Role[]`. |
| `@Roles({"reader", "writer"})` ở mục 3 | Một mô hình **khác**: `Roles.value()` là `String[]`, không phải `Role[]`. |

Java 7 và các phiên bản trước chưa có cú pháp hỗ trợ repeatable annotation như Java 8, vì thế cách tạo một annotation container chứa mảng annotation là một phương án để mô hình hóa nhiều thông tin cùng loại.

Lưu ý **không lẫn hai định nghĩa `Roles`** ở hai phần ví dụ: mục 3 định nghĩa `String[] value()`; từ mục 4 trở đi, `Roles` được định nghĩa lại cho một minh họa độc lập với **`Role[] value()`**. Chúng không được chép nguyên xi vào cùng một file/package như hai kiểu cùng tên.

## 7. Một annotation mang nhiều thuộc tính: vì sao lặp có ích?

Giả sử mỗi quyền cần cả `name` và `scope`. Định nghĩa annotation lặp:

```java
import java.lang.annotation.Repeatable;

@Repeatable(AccessRules.class)
@interface AccessRule {
    String name();
    String scope();
}

@interface AccessRules {
    AccessRule[] value();
}
```

Khi dùng:

```java
@AccessRule(name = "reader", scope = "/reports")
@AccessRule(name = "writer", scope = "/drafts")
class ReportEndpoint {
}
```

Mỗi annotation biểu diễn **một cặp dữ liệu liên quan**, giảm nguy cơ ghép lệch nếu người viết mã phải duy trì hai mảng song song như `names = {"reader", "writer"}` và `scopes = {"/reports", "/drafts"}`.

Đây là đoạn mã **minh họa khai báo và sử dụng**, không phải chương trình độc lập với `main`; muốn đọc bằng reflection phải thêm retention phù hợp cho cả annotation lặp lẫn container. `AccessRule` không phải cơ chế kiểm tra quyền thực sự: hệ thống phải tự diễn giải metadata và thực hiện kiểm soát truy cập.

## 8. Những ràng buộc cần nhớ khi lặp annotation

Các khai báo `@Repeatable` phải tuân thủ hợp đồng giữa annotation lặp và container:

- **Container có `value()` là mảng của đúng kiểu annotation lặp**, ví dụ `Role[] value()`. Không thể khai báo `String[] value()` cho container của `Role`.
- Container có thể có các element khác, nhưng nếu có thì chúng cần được khai báo với giá trị mặc định để Java có thể tạo biểu diễn container khi lặp.
- **Retention tương thích:** container không được giữ ngắn hơn annotation lặp. Nếu `Role` là `RUNTIME` mà `Roles` chỉ có retention `SOURCE`, compiler sẽ từ chối khai báo lặp không hợp lệ.
- **Target tương thích:** container phải cho phép những vị trí mà annotation lặp được phép dùng; các trường hợp `TYPE_USE`, `TYPE_PARAMETER`, `ANNOTATION_TYPE` có các quy tắc tương thích chi tiết theo Java Language Specification.
- Nếu annotation lặp có `@Documented` hoặc `@Inherited`, container cũng phải đáp ứng những ràng buộc tương ứng theo quy tắc của Java.
- Cần suy nghĩ đến phần metadata và API đọc nó khi thay đổi một annotation đã được sử dụng trong thư viện, vì mã cũ có thể tìm annotation bằng một API reflection khác.

Để dễ kiểm chứng, ví dụ `Role` và `Roles` đặt **cùng `@Target(TYPE)` và cùng `@Retention(RUNTIME)`**. Cặp khai báo đó hợp lệ và đủ cho nhu cầu đánh dấu class.

### Reflection: đọc một lần hay nhiều lần?

Với annotation **được dùng nhiều lần** như `@Role("reader") @Role("writer")`, nên dùng:

```java
Role[] roles = ReportService.class.getAnnotationsByType(Role.class);
```

Nếu gọi:

```java
Role one = ReportService.class.getAnnotation(Role.class);
```

trên class có **hai `Role` được lặp qua container** như ví dụ, kết quả sẽ là `null` vì `getAnnotation` chỉ tìm annotation kiểu `Role` hiện diện trực tiếp hoặc theo cơ chế kế thừa hỗ trợ, trong khi hai `Role` đang được biểu diễn qua container `Roles`. `getAnnotationsByType` bổ sung cách nhìn xuyên qua container cho annotation có thể lặp.

Nếu class chỉ có **một** `@Role("reader")`, compiler có thể giữ một annotation `Role` trực tiếp và `getAnnotation(Role.class)` có thể trả về giá trị đó. Do vậy, code xử lý muốn hỗ trợ cả một và nhiều lần áp dụng nên chọn `getAnnotationsByType`.

Với các ví dụ không dùng kế thừa, `getDeclaredAnnotationsByType(Role.class)` cũng trả về những lần áp dụng `Role` được khai báo trên chính class. Tìm theo kế thừa giữa superclass và subclass còn phụ thuộc `@Inherited` và quy tắc reflection; không nên giả định annotation nào cũng tự kế thừa.

## 9. Tránh nhầm: nhiều element trong một annotation khác với annotation lặp

Ví dụ sau cũng có **nhiều giá trị**, nhưng không phải annotation lặp:

```java
@interface RequestConfig {
    String path();
    String method() default "GET";
    int timeoutMs() default 1000;
}

@RequestConfig(path = "/reports", method = "POST", timeoutMs = 1500)
class ReportRequest {
}
```

Ở đây có một `@RequestConfig` với **ba element khác tên**. Điều này không cần `@Repeatable`; các cặp tên–giá trị thuộc cùng một annotation instance.

Trường hợp lặp thật sự phải là **nhiều lần dùng cùng tên annotation** trên cùng vị trí:

```java
@Role("reader")
@Role("writer")
class ReportService {
}
```

Trong ví dụ có container hợp lệ, hai lần dùng `Role` có cùng tên kiểu, nhưng mỗi lần có dữ liệu riêng.

| Nhu cầu | Cú pháp tiêu biểu | Mô hình |
| --- | --- | --- |
| Một khai báo có nhiều **thuộc tính khác tên** | `@Config(path = "/x", timeout = 500)` | Một annotation có nhiều element. |
| Một thuộc tính chứa **nhiều chuỗi** | `@Labels({"a", "b"})` | Một annotation có element mảng. |
| Cùng một loại thông tin xuất hiện **nhiều lần độc lập** | `@Role("a")` + `@Role("b")` | Nhiều lần áp dụng cùng một annotation loại repeatable. |

Đây là ba bài toán khác nhau; việc đặt `@Repeatable` chỉ cần thiết cho trường hợp thứ ba.

## 10. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Cách sửa |
| --- | --- |
| Gắn hai `@Role` mà `Role` chưa có `@Repeatable` | Định nghĩa container hợp lệ rồi thêm `@Repeatable(Roles.class)` trên `Role`. |
| Nghĩ cứ khác giá trị thì được lặp cùng annotation | Compiler xét **kiểu annotation**, không chỉ giá trị. |
| Container khai báo `String[] value()` | Với `@Repeatable(Roles.class)` của `Role`, phải là **`Role[] value()`**. |
| Container retention thấp hơn annotation lặp | Chọn retention tương thích; ví dụ cả hai là `RUNTIME`. |
| Dùng `getAnnotation(Role.class)` khi có nhiều `Role` | Dùng `getAnnotationsByType(Role.class)` để nhận các phần tử trong container. |
| Nhầm `@Roles({"a", "b"})` với `@Roles({@Role("a"), @Role("b")})` | Phải xem `value()` của `Roles` là `String[]` hay `Role[]`; đây là hai kiểu định nghĩa khác nhau. |
| Nghĩ annotation lặp tự thực thi nhiều công việc | Annotation chỉ đánh dấu metadata; cần code/framework đọc và xử lý. |
| Đặt một repeatable annotation ở vị trí mà `@Target` không cho phép | Kiểm tra `@Target` của annotation lặp và container. |

## 11. Tự kiểm tra

Xét các khai báo (mỗi ví dụ dùng cùng định nghĩa `Role` và `Roles` ở mục 5):

1. `@Role("reader")` trên class: **Hợp lệ**, một lần áp dụng.
2. `@Role("reader") @Role("writer")` trên cùng class: **Hợp lệ** vì `Role` có `@Repeatable(Roles.class)`.
3. Hai lần `@Role(...)` trên cùng class sau khi bỏ `@Repeatable`: **Không hợp lệ**; dù giá trị khác nhau vẫn là một kiểu annotation xuất hiện hai lần trực tiếp.
4. `@Roles({@Role("reader"), @Role("writer")})`: **Hợp lệ** vì container có `Role[] value()`.
5. `@Role("reader")` gắn lên một field với `@Target(TYPE)` như ví dụ: **Không hợp lệ**; target không cho phép field.
6. Sau khi lặp hai `@Role` trên class, gọi `getAnnotationsByType(Role.class)` thu được mấy phần tử? **Hai**, lần lượt `reader` và `writer` trong ví dụ.

Khi gặp yêu cầu “một vị trí cần nhiều annotation”, hãy làm rõ loại dữ liệu cần biểu diễn: **một danh sách giá trị đơn giản** có thể dùng một annotation với mảng; **nhiều bộ metadata độc lập** thích hợp với annotation repeatable có container. Dù chọn cách nào, vị trí sử dụng phải đúng `@Target`, kiểu giá trị phải hợp lệ với annotation element và ý nghĩa nghiệp vụ cần có bộ xử lý riêng.

Tài liệu tra cứu: [Java Language Specification 21 – mục 9.6 Annotation Interfaces và 9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html); [Java SE 21 API – `java.lang.annotation.Repeatable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html).
