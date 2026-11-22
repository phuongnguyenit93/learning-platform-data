# Ảnh hưởng tương thích khi chuyển annotation thường thành annotation lặp trong Java

## 1. Bài toán: thay đổi nhỏ trong định nghĩa, tác động lớn tới bên đọc metadata

Một annotation **không lặp** (non-repeatable annotation) chỉ được xuất hiện một lần ở cùng một ngữ cảnh khai báo hoặc sử dụng kiểu. Từ Java 8, `@Repeatable` cho phép viết nhiều annotation cùng kiểu lên một phần tử, nhưng Java cần một **containing annotation type** (thường gọi là *container*) để chứa các lần xuất hiện ấy.

Ví dụ ban đầu, API chỉ cho mỗi class mang một vai trò:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Role {
    String value();
}
~~~

Các lớp dùng API phiên bản cũ:

~~~java
@Role("reader")
class ReaderService {
}
~~~

Sau một thời gian, yêu cầu thay đổi: cùng một service có thể mang cả `"reader"` và `"writer"`. Tác giả thư viện muốn biến `Role` thành repeatable annotation.

Thay đổi điển hình:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
public @interface Role {
    String value();
}
~~~

Thêm annotation container:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Roles {
    Role[] value();
}
~~~

Cả hai snippet là **định nghĩa tệp riêng `Role.java` và `Roles.java` của cùng package**, không phải một chương trình một tệp. Từ đó có thể sử dụng:

~~~java
@Role("reader")
@Role("writer")
class ReaderWriterService {
}
~~~

Câu hỏi quan trọng khi phát hành thư viện là: **mã client cũ có còn biên dịch và liên kết được không; các bộ xử lý annotation cũ có còn đọc đúng dữ liệu không?**

Cần tách ba lớp tương thích:

1. **Source compatibility**: mã nguồn đã dùng annotation trước đây có còn biên dịch được khi dùng phiên bản API mới?
2. **Binary compatibility**: những tệp `.class` client đã biên dịch trước đây có còn liên kết với định nghĩa annotation mới?
3. **Behavioral compatibility**: processor, framework hoặc mã reflection có còn trả về/kết luận giống trước?

Theo hợp đồng của `java.lang.reflect.AnnotatedElement` trong Java SE 17, việc chuyển một annotation type `T` sang repeatable **tương thích source và binary với cách dùng `T` và container `TC` cũ** khi việc chuyển đổi được thực hiện đúng quy tắc. **Nhưng không thể suy ra rằng mọi kết quả reflection và hành vi ứng dụng giữ nguyên**.

## 2. Compiler biểu diễn một annotation và nhiều annotation ra sao?

Có hai trường hợp cần xem riêng.

**Một lần xuất hiện**:

~~~java
@Role("reader")
class SingleRole {
}
~~~

Với Java 17, việc chỉ có một `@Role` thông thường tiếp tục được lưu như **một annotation `Role` trực tiếp**. Chỉ vì `Role` được bổ sung `@Repeatable` không có nghĩa compiler bắt buộc gói một lần dùng duy nhất vào `Roles`.

**Nhiều lần xuất hiện tại cùng vị trí**:

~~~java
@Role("reader")
@Role("writer")
class MultipleRoles {
}
~~~

Đối với hai annotation cùng kiểu như trên, compiler xử lý chúng tương đương với một container ngầm định:

~~~java
@Roles({@Role("reader"), @Role("writer")})
class MultipleRoles {
}
~~~

Hai đoạn khai báo `MultipleRoles` ở trên là **hai lựa chọn thay thế**, không đặt đồng thời trong cùng tệp. Container có phần tử `value()` trả về `Role[]`; thứ tự các role trong mảng tương ứng với thứ tự annotation từ trái sang phải trong source.

Hệ quả: khi mã chỉ đọc **annotation trực tiếp**, `MultipleRoles` có thể hiện lên như một annotation kiểu `Roles`, còn các `Role` nằm bên trong nó. Khi dùng API chuyên nhận repeatable annotation, Java sẽ **mở container** để trả về từng `Role`.

Đây là nguyên nhân chính khiến việc chuyển từ non-repeatable sang repeatable có thể tác động đến **bộ đọc metadata** mà không gây lỗi biên dịch.

## 3. Ví dụ Java 17 chạy được: so sánh API reflection cũ và mới

Tạo một tệp duy nhất **`RepeatableCompatibilityDemo.java`**:

~~~java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

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
class OneRole {
}

@Role("reader")
@Role("writer")
class TwoRoles {
}

@Roles({@Role("admin"), @Role("auditor")})
class ExplicitContainer {
}

public class RepeatableCompatibilityDemo {
    public static void main(String[] args) {
        inspect("one", OneRole.class);
        inspect("two", TwoRoles.class);
        inspect("explicit", ExplicitContainer.class);
    }

    private static void inspect(String label, Class<?> type) {
        Role direct = type.getAnnotation(Role.class);

        String[] values = Arrays.stream(type.getAnnotationsByType(Role.class))
                .map(Role::value)
                .toArray(String[]::new);

        Annotation[] raw = type.getDeclaredAnnotations();
        String[] rawTypes = Arrays.stream(raw)
                .map(a -> a.annotationType().getSimpleName())
                .toArray(String[]::new);

        System.out.println(label
                + ": direct=" + (direct == null ? "null" : direct.value())
                + ", byType=" + Arrays.toString(values)
                + ", container=" + (type.getDeclaredAnnotation(Roles.class) != null)
                + ", declaredTypes=" + Arrays.toString(rawTypes));
    }
}
~~~

Chạy với JDK 17+ trong thư mục chứa tệp:

~~~bash
javac RepeatableCompatibilityDemo.java
java RepeatableCompatibilityDemo
~~~

**Stdout chính xác**:

~~~text
one: direct=reader, byType=[reader], container=false, declaredTypes=[Role]
two: direct=null, byType=[reader, writer], container=true, declaredTypes=[Roles]
explicit: direct=null, byType=[admin, auditor], container=true, declaredTypes=[Roles]
~~~

Giải thích:

- **`OneRole`**: chỉ có một `@Role`, nên `getAnnotation(Role.class)` trả về đối tượng tương ứng. `getAnnotationsByType(Role.class)` cũng trả về mảng gồm một phần tử.
- **`TwoRoles`**: hai annotation cùng loại được container `Roles` đại diện. `getAnnotation(Role.class)` trả `null` vì không có `Role` trực tiếp; `getAnnotationsByType(Role.class)` mở container và trả về cả hai.
- **`ExplicitContainer`**: sử dụng trực tiếp `@Roles(...)` cũng được API `getAnnotationsByType(Role.class)` mở thành hai phần tử. Còn `getAnnotation(Role.class)` vẫn trả `null`.
- **`getDeclaredAnnotations()`** trả những annotation xuất hiện trực tiếp ở mức class file/reflection. Trong hai trường hợp chứa nhiều `Role`, phần tử trực tiếp là container `Roles`, vì thế mã chỉ tìm `Role` trong mảng này sẽ bỏ sót metadata cần xử lý.

Mã mẫu có `@Retention(RUNTIME)` trên cả `Role` và `Roles`. Nếu không lưu metadata tại runtime, ta không thể dùng ví dụ reflection như trên để chứng minh sự khác nhau.

### Chú ý về bản chất của ví dụ

Đây là một chương trình **đã dùng API sau chuyển đổi**, nhằm minh họa sự khác nhau giữa nơi có một annotation và nơi có nhiều annotation. Nó **không tự chứng minh** việc một tệp `.class` cũ có thể liên kết với một phiên bản thư viện mới: muốn kiểm tra binary compatibility bằng thực nghiệm cần biên dịch client với phiên bản cũ, giữ nguyên bytecode client, rồi chạy cùng thư viện mới.

## 4. Tương thích source: mã nguồn cũ thường không cần sửa

Giả sử client đã viết:

~~~java
@Role("reader")
class ExistingClient {
}
~~~

Sau khi `Role` được khai báo repeatable, đoạn mã này vẫn hợp lệ và biên dịch được. Các chương trình sử dụng kiểu `Role` như trước không phải sửa cú pháp chỉ vì thêm `@Repeatable(Roles.class)`.

Một lợi ích của quá trình chuyển đổi là **không cần ép tất cả client đang dùng một annotation sang cú pháp container**. Client có thể tiếp tục dùng `@Role("reader")`, trong khi client cần nhiều role mới dùng:

~~~java
@Role("reader")
@Role("writer")
class MultiRoleClient {
}
~~~

Mã nguồn chứa nhiều annotation cùng kiểu **trước khi `Role` repeatable** sẽ không hợp lệ nếu viết trực tiếp hai `@Role` trên cùng phần tử. Việc thêm `@Repeatable` **mở rộng** cú pháp đó tại các vị trí mà cả `Role` và container được phép áp dụng.

Tuy nhiên, khẳng định tương thích source ở đây chỉ dành cho **việc chuyển trạng thái repeatable đúng quy tắc**. Nếu đồng thời **đổi tên `Role`**, xóa phần tử `value()`, đổi kiểu trả về của phần tử, thay đổi target/retention không tương thích hoặc thay API khác, đó là các thay đổi riêng cần đánh giá độc lập.

## 5. Tương thích binary: không bắt buộc biên dịch lại mọi client

Một tệp `.class` trước đây mang một `@Role("reader")` có metadata mô tả lần sử dụng trực tiếp của `Role`. Khi thư viện bổ sung `@Repeatable(Roles.class)`, **bytecode client cũ không tự viết lại thành container**. Nó vẫn mô tả một `Role` trực tiếp và có thể liên kết với định nghĩa `Role` mới theo quy tắc tương thích được Java API công bố.

Tương tự, nếu `Roles` đã từng tồn tại như một annotation bình thường có phần tử `Role[] value()`, những class file dùng `Roles` có thể tiếp tục liên kết sau khi `Roles` được chỉ định là container chính thức cho `Role`.

Bổ sung annotation container như **một kiểu mới** là một trường hợp phổ biến khác. Khi đó, client cũ vốn chưa biết đến `Roles` vẫn có thể tiếp tục dùng `Role` như trước, còn client mới biên dịch từ source có hai `@Role` phụ thuộc thêm vào `Roles` tại runtime nếu retention của container là `RUNTIME`.

Cần hiểu chính xác câu “binary compatible”:

- Nó nói rằng các binary được biên dịch từ cách dùng hợp lệ cũ **có thể liên kết** với kiểu annotation mới theo cam kết được nêu trong Java SE 17.
- Nó **không đảm bảo** mọi thư viện scanning/reflection, bytecode transformer hoặc framework bên ngoài sẽ diễn giải tập annotation giống trước.
- Nó cũng **không cho phép bỏ container khỏi runtime** khi những class đã biên dịch mới thực sự chứa metadata `Roles`. Thiếu kiểu container hoặc đổi định nghĩa container không phù hợp có thể làm việc đọc metadata bị lỗi hoặc không nhận diện được.

Do vậy kiểm thử binary nên giữ lại artifact client cũ trong bộ test, không chỉ recompile toàn bộ project rồi tuyên bố mọi thứ tương thích.

## 6. Tương thích hành vi: thay đổi ở Reflection là điểm rủi ro lớn nhất

`AnnotatedElement` phân biệt annotation **directly present** (trực tiếp) và **indirectly present** (nằm trong container). Nó cũng có các khái niệm **present** và **associated** để xử lý quy tắc kế thừa annotation trên class.

| API reflection | Với một `@Role` trực tiếp | Với hai `@Role` được chứa trong `@Roles` |
| --- | --- | --- |
| `getAnnotation(Role.class)` | Trả `Role` | Thường `null` nếu không có `Role` trực tiếp hoặc được kế thừa theo quy tắc |
| `getDeclaredAnnotation(Role.class)` | Trả `Role` | `null` |
| `isAnnotationPresent(Role.class)` | `true` | `false` trong ví dụ không kế thừa |
| `getAnnotations()` / `getDeclaredAnnotations()` | Chứa `Role` | Chứa `Roles` |
| `getAnnotationsByType(Role.class)` | Một phần tử | Hai phần tử |
| `getDeclaredAnnotationsByType(Role.class)` | Một phần tử | Hai phần tử |

Bảng xét **class không có vấn đề `@Inherited`**, như ví dụ `OneRole` và `TwoRoles` đã chạy. Với annotation `@Inherited` và quan hệ superclass/subclass, cần áp dụng thêm quy tắc kế thừa của API; không nên dùng các dòng trong bảng làm kết luận cho mọi trường hợp.

Chính sách xử lý metadata của consumer có thể thay đổi rất lớn:

~~~java
Role role = type.getAnnotation(Role.class);
if (role != null) {
    register(role.value());
}
~~~

Đoạn trên là **fragment giả định đang ở trong một hàm có biến `Class<?> type` và hàm `register(String)`**. Nó hợp lý khi annotation không lặp và được gắn một lần. Khi một class có hai `@Role`, `getAnnotation(Role.class)` có thể trả `null`, dẫn tới **bỏ qua mọi role**.

Để hỗ trợ nhiều `Role`, consumer cần đổi logic:

~~~java
for (Role role : type.getAnnotationsByType(Role.class)) {
    register(role.value());
}
~~~

Đây cũng là fragment cần hàm `register` trong ứng dụng thực tế. Với class chỉ có một `@Role`, vòng lặp chạy một lần; với class có hai `@Role`, vòng lặp chạy hai lần. Đây là thay đổi ở **logic của consumer**, không phải tự động có được khi thư viện chỉ thêm `@Repeatable`.

Một vấn đề nghiệp vụ tiếp theo: nếu nhiều `Role` có thể được khai báo, mã xử lý phải nói rõ cần **hợp nhất**, **ưu tiên**, **loại bỏ trùng**, **từ chối xung đột**, hay **giữ nguyên thứ tự**. Java bảo toàn thứ tự các annotation trong container theo thứ tự source, nhưng Java không biết ứng dụng muốn xử lý trùng/xung đột như thế nào.

## 7. Container đã tồn tại từ trước: kết quả có thể đổi dù client không recompile

Trước khi `Role` thành repeatable, một dự án có thể đã có annotation `Roles` nhận mảng:

~~~java
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Roles({@Role("reader"), @Role("writer")})
class OldStyleMultiple {
}
~~~

Đây là **fragment minh họa phiên bản cũ**, chưa thêm import và retention để runtime reflection hoạt động. Nếu cả `Role` và `Roles` có retention `RUNTIME`, giả sử `OldStyleMultiple.class` được biên dịch **trước** khi có `@Repeatable`, thì:

- `getAnnotation(Roles.class)` nhìn thấy container `Roles`.
- `getAnnotation(Role.class)` không nhìn thấy một `Role` trực tiếp.
- `getAnnotationsByType(Role.class)` chưa coi `Roles` là container chính thức của một repeatable `Role`, vì `Role` chưa có `@Repeatable(Roles.class)`; kết quả có thể là mảng rỗng.

Sau khi chỉ cập nhật **định nghĩa của `Role`** để trở thành `@Repeatable(Roles.class)` hợp lệ, runtime reflection nay biết `Roles` là container của `Role`. Khi đọc lại **chính class file `OldStyleMultiple` không thay đổi**, `getAnnotationsByType(Role.class)` có thể trả về hai role nằm trong container.

Đây là trường hợp rất đáng chú ý: **source và binary của client không đổi**, nhưng kết quả của **một phương thức reflection** lại đổi do metadata về repeatability của annotation type đã thay đổi.

Các phương thức không tự mở container như `getAnnotation(Role.class)` và `getAnnotation(Roles.class)` không đổi kết quả chỉ vì `Roles` được chỉ định làm container. Chính nhóm API `get[Declared]AnnotationsByType` thay đổi cách nhìn khi biết repeatable mapping.

Nếu framework cũ đã tự mở `Roles.value()`, sau khi thêm `@Repeatable` phải tránh **mở container hai lần** hoặc cộng kết quả từ hai đường đọc một cách không kiểm soát.

## 8. Vì sao container cần thiết kế đúng chuẩn?

Không phải annotation nào chứa `Role[]` cũng tự động được compiler chấp nhận làm container. `@Repeatable(Roles.class)` phải tham chiếu một **containing annotation type** hợp lệ theo JLS §9.6.3.

Những điều kiện bắt buộc cần kiểm tra:

1. `Roles` khai báo `Role[] value();` với **kiểu phần tử và mảng chính xác**. `Object[]`, `String[]`, hoặc `Role value()` đều không phù hợp.
2. Nếu `Roles` có phần tử khác `value()`, các phần tử đó đều phải có `default`, để compiler có thể tạo container ngầm định.
3. Retention của `Roles` phải **ít nhất dài bằng retention của `Role`**. Ví dụ `Role` có `RUNTIME` thì `Roles` cũng phải `RUNTIME`; `Role` có `SOURCE` thì container có thể giữ lâu hơn.
4. Phạm vi `@Target` của container không được rộng hơn phạm vi áp dụng của annotation gốc theo các quy tắc đặc biệt của JLS. Container có thể hẹp hơn, khiến việc lặp chỉ hợp lệ ở một số target.
5. Nếu `Role` được đánh dấu `@Documented`, thì `Roles` cũng phải có `@Documented`.
6. Nếu `Role` được đánh dấu `@Inherited`, thì `Roles` cũng phải có `@Inherited`.

Hai chiều cuối **không hoàn toàn đối xứng**: container được phép có `@Documented` hoặc `@Inherited` kể cả khi annotation gốc không có. Tuy nhiên, để tránh bất ngờ về cách trình bày tài liệu hoặc kế thừa metadata, nên thiết kế các chính sách này có chủ đích.

### Ví dụ container không hợp lệ

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@interface Roles {
    Role[] value();
}
~~~

Đoạn trên là **ví dụ lỗi biên dịch có chủ đích**: `Role` được giữ tới `RUNTIME`, trong khi `Roles` chỉ tới `CLASS`. Java không chấp nhận cấu hình container có retention ngắn hơn annotation gốc.

Một lỗi khác:

~~~java
// Không hợp lệ nếu Roles.value() trả Object[]:
// @interface Roles {
//     Object[] value();
// }
~~~

Không thể dùng container bất kỳ có mảng `Object[]` rồi mong `getAnnotationsByType(Role.class)` hiểu đó là `Role[]`.

### Target của container có thể ảnh hưởng khả năng mở rộng

Ví dụ `Role` ban đầu được phép trên `TYPE` và `METHOD`, nhưng `Roles` chỉ có `@Target(TYPE)`. Việc **gắn một `@Role` trên method** có thể vẫn hợp lệ; tuy nhiên **gắn hai `@Role` lên method** không hợp lệ vì compiler không thể đặt container ngầm định lên target đó. Vậy thêm repeatable không nhất thiết có nghĩa annotation được lặp ở mọi chỗ nó có thể xuất hiện đơn lẻ.

Khi chuyển đổi, hãy kiểm tra cả **những nơi sử dụng cũ** và **những nơi dự kiến cho phép lặp mới**, đặc biệt với `TYPE_USE`, `TYPE_PARAMETER`, record component hoặc các target có quy tắc giao thoa.

## 9. `@Inherited`: nguồn gây khác biệt khi annotation lặp xuất hiện trên superclass

`@Inherited` chỉ điều khiển một số hình thức tra cứu annotation **trên class**, không khiến metadata tự lan sang mọi method hoặc interface.

Nếu một annotation `Role` được đánh dấu `@Inherited`, thì container `Roles` cũng phải `@Inherited`. Khi đọc class con qua `getAnnotationsByType(Role.class)`, Java có thể trả về các `Role` kế thừa từ superclass nếu class con không có `Role` trực tiếp hoặc gián tiếp gắn trên chính nó.

Nếu class con **có một `@Role` riêng**, thì kết quả thường là role tại class con, không tự động hợp nhất với mọi role kế thừa từ superclass. Vì vậy migrate sang repeatable cần xác định rõ ý nghĩa của chính sách kế thừa: **thay thế bộ role của cha hay gộp cả hai?** API reflection chuẩn cung cấp semantics nhất định; việc muốn gộp kết quả theo một chính sách khác cần logic riêng.

Quan trọng: `getAnnotation(Role.class)` và `getAnnotationsByType(Role.class)` dùng những khái niệm presence/association khác nhau. Đừng kết luận chỉ bằng câu “`Role` có `@Inherited` nên mọi scanner tự hoạt động”, nhất là khi các role trên superclass đã được đóng gói thành `Roles`.

## 10. `@Documented` và annotation processors: phạm vi ảnh hưởng rộng hơn runtime

**Javadoc:** Nếu annotation gốc `Role` được đánh dấu `@Documented`, container cũng phải `@Documented`. Điều này đảm bảo JLS không cho cấu hình container bỏ rơi cam kết về việc công bố annotation gốc. Tuy nhiên cách trình bày annotation trên HTML vẫn do công cụ Javadoc xử lý; nên xem tài liệu sinh ra sau khi migrate.

**Annotation processor compile-time:** Những processor đọc cấu trúc annotation tại biên dịch có thể nhìn một annotation container khi các annotation cùng kiểu được lặp. Nếu processor chỉ tìm một kiểu `Role` hoặc tự truy cập danh sách annotation mirrors và giả định không có container, việc sinh mã hoặc kiểm tra có thể bỏ sót nhóm repeatable. Mã dùng `javax.lang.model.element.AnnotationMirror` và `RoundEnvironment` cần kiểm thử với cả một annotation, nhiều annotation, và explicit container. Không được giả định API compile-time tự hành xử **giống hệt** `AnnotatedElement.getAnnotationsByType` ở runtime; chúng là hai mô hình khác nhau.

**Framework:** Các framework có API đọc annotation riêng, có thể đã xử lý container hoặc meta-annotation theo cách của chúng. Khi nâng cấp thư viện annotation, hãy xác nhận contract của phiên bản framework đang dùng thay vì giả định việc thêm `@Repeatable` tự sửa tất cả đường đọc metadata.

## 11. Tình huống tương thích cần kiểm thử trước khi phát hành

| Tình huống | Kỳ vọng quan trọng | Cần kiểm tra |
| --- | --- | --- |
| Client cũ có một `@Role` | Vẫn dùng được; nếu retention `RUNTIME`, đọc trực tiếp vẫn nhận được | Compile source cũ với thư viện mới; chạy class cũ với thư viện mới |
| Client mới có một `@Role` | Metadata thường vẫn là `Role` trực tiếp | `getAnnotation` và `getAnnotationsByType` |
| Client mới có nhiều `@Role` | Container đại diện các giá trị | `getDeclaredAnnotations`, `getAnnotationsByType` |
| Client cũ có `@Roles(...)` tường minh | Có thể vẫn liên kết, nhưng API by-type có thể mở container sau khi migrate | Reflection trước/sau đổi `@Repeatable` |
| Consumer dùng `getAnnotation(Role.class)` | Có nguy cơ bỏ qua phần tử khi annotation lặp | Chuyển sang `getAnnotationsByType` khi nghiệp vụ cho phép nhiều |
| Consumer dùng `getDeclaredAnnotations()` | Có thể nhìn thấy `Roles` thay vì `Role` | Xác định container và thứ tự xử lý |
| Có `@Inherited` | Class con có thể trả kết quả khác theo presence/association | Test superclass và subclass |
| Có `@Documented` | Container phải nhất quán, Javadoc phải đúng | Biên dịch + kiểm tra HTML |
| Annotation processor / framework riêng | Có thể chưa hiểu repeatable/container | Integration test đúng đường đọc metadata |

Các kiểm tra nên bao gồm **artifact compile cũ**, **artifact compile mới** và **mã consumer cũ**. Chỉ kiểm thử các source vừa được biên dịch lại bằng JDK mới là chưa đủ để chứng minh backward compatibility của bản phát hành.

### Quy trình chuyển đổi thực tế

1. **Kiểm kê consumers**: tìm code đang gọi `getAnnotation`, `isAnnotationPresent`, `getDeclaredAnnotations`, `getAnnotationsByType`, bộ xử lý compile-time hoặc API quét riêng của framework.
2. **Giữ ổn định annotation type**: duy trì tên đầy đủ của `Role`, phần tử `value()`, kiểu phần tử, target/retention và các hợp đồng cũ khi có thể.
3. **Chọn container**: tạo `Roles` mới hoặc dùng loại đang có nếu thực sự đáp ứng chuẩn; xác nhận `value()`, default, retention, target, `@Inherited`, `@Documented`.
4. **Nâng consumer trước khi mở rộng dữ liệu**: sửa đường đọc sang API hỗ trợ repeatable, xác định xử lý trùng, thứ tự và xung đột; kiểm thử với cả annotation đơn và nhiều annotation.
5. **Triển khai/bảo đảm có container tại runtime**: nhất là khi client mới đã biên dịch hai annotation trực tiếp thành một metadata container.
6. **Kiểm thử theo ma trận cũ/mới**: compile source cũ với API mới, chạy binary cũ với API mới và đưa vào class mới có hai annotation. Kiểm tra phản hồi của framework/processor/Javadoc nếu chúng là một phần hợp đồng.
7. **Ghi rõ thay đổi hành vi**: công bố cho người tích hợp API rằng các hàm lấy một annotation trực tiếp có thể không còn nhìn thấy trường hợp lặp.

Thứ tự nâng consumer trước khi cho nhiều annotation xuất hiện rộng rãi giúp giảm nguy cơ các scanner cũ âm thầm bỏ qua metadata.

## 12. Những lỗi hiểu sai phổ biến

**“Từ `@Role` sang `@Repeatable` là breaking change về binary.”** Không nhất thiết; riêng thay đổi thành repeatable hợp lệ được Java mô tả là source/binary compatible. Rủi ro thường nằm ở **hành vi đọc metadata** và những thay đổi API khác đi kèm.

**“`getAnnotation(Role.class)` sẽ trả role đầu tiên nếu có hai role.”** Sai. Với hai `@Role` được đóng gói qua `Roles`, không có `Role` trực tiếp, vì vậy kết quả có thể là `null`; API đúng cho tập giá trị là `getAnnotationsByType(Role.class)`.

**“Một annotation `Role` đơn lẻ cũng chắc chắn biến thành `Roles`.”** Sai. Sử dụng một lần tiếp tục là trực tiếp trong trường hợp thông thường; compiler không cần container cho một lần sử dụng.

**“Tương thích binary nghĩa là mọi kết quả reflection bất biến.”** Sai. Nếu container đã có trước khi `Role` repeatable, `getAnnotationsByType(Role.class)` có thể bắt đầu mở container dù class file cũ giữ nguyên.

**“Có `Role[] value()` là đủ làm container.”** Sai. Còn điều kiện về retention, target, default của các phần tử bổ sung, `@Documented` và `@Inherited`.

**“Có thể đọc tất cả repeatable annotation bằng `getDeclaredAnnotations()` rồi chỉ lọc tên `Role`.”** Sai. Với nhiều lần dùng, raw annotation có thể là `Roles`; dùng API by-type hoặc xử lý container một cách có chủ đích.

**“Nếu annotation lặp có `@Inherited`, class con luôn tự gộp tất cả giá trị của class cha.”** Sai. API áp dụng quy tắc inheritance/association, không mặc định thực hiện union các role ở mọi cấp.

**“Thêm `@Repeatable` thì framework và processor tự hiểu semantics nghiệp vụ.”** Sai. `@Repeatable` chỉ quy định cú pháp và mapping container; consumer phải quyết định xử lý metadata.

## 13. Tự kiểm tra

**Câu 1.** Một class cũ đã biên dịch có `@Role("reader")`. Nếu chỉ bổ sung `@Repeatable(Roles.class)` hợp lệ vào `Role`, class file có tự chuyển thành `@Roles({@Role("reader")})` không?

**Đáp án:** Không. Metadata của class file cũ không tự thay đổi; repeatability là thuộc tính của annotation type dùng khi compiler xử lý nhiều lần sử dụng và khi API reflection nhận diện container.

**Câu 2.** Vì sao code cũ `clazz.getAnnotation(Role.class)` có thể trả `null` sau khi một class được gắn hai `@Role`?

**Đáp án:** Hai annotation được thể hiện bằng container `Roles` trực tiếp, còn `Role` nằm gián tiếp bên trong. `getAnnotation` không mở container để trả một phần tử bất kỳ.

**Câu 3.** Nên đọc danh sách repeatable `Role` qua API nào?

**Đáp án:** `getAnnotationsByType(Role.class)` khi muốn kể cả các trường hợp inherited theo semantics liên quan; `getDeclaredAnnotationsByType(Role.class)` khi chỉ muốn các giá trị được khai báo trực tiếp hoặc gián tiếp trên chính phần tử.

**Câu 4.** `Role` có retention `RUNTIME`, container `Roles` có retention `CLASS`. Có thể dùng như repeatable hợp lệ không?

**Đáp án:** Không. Container phải có retention tối thiểu bằng annotation gốc.

**Câu 5.** Trước khi `Role` trở thành repeatable, class đã dùng `@Roles({@Role("reader"), @Role("writer")})` và cả hai đều có retention `RUNTIME`. Sau chuyển đổi, điều gì có thể thay đổi ngay cả khi không biên dịch lại class?

**Đáp án:** `getAnnotationsByType(Role.class)` có thể bắt đầu mở `Roles` và trả về cả hai `Role`, vì `Role` lúc này đã chỉ rõ container qua `@Repeatable`.

**Bài thực hành:** Chạy `RepeatableCompatibilityDemo.java` và ghi lại ba kết quả. Sau đó thử thay consumer `getAnnotationsByType(Role.class)` bằng `getAnnotation(Role.class)` trong logic duyệt role. So sánh các trường hợp có một, hai, và container tường minh. Hãy giải thích sự khác biệt bằng ba khái niệm: **directly present**, **indirectly present**, và **containing annotation**.

## 14. Nguồn Java SE 17

- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): mô tả rõ khả năng tương thích source/binary và thay đổi kết quả reflection khi annotation type trở nên repeatable.
- [JLS §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3): điều kiện để một annotation container hợp lệ.
- [JLS §9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5): quy tắc compiler về nhiều annotation cùng kiểu.
- [Java SE 17 — `Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html): API và vai trò của containing annotation type.

Khi chuyển annotation thường thành annotation lặp, việc bảo toàn **kiểu cũ** giúp giữ source và binary tương thích. Việc bảo toàn **hành vi quan sát được** còn phụ thuộc vào tất cả consumer: chúng cần biết đến container, API by-type, quy tắc kế thừa và chính sách xử lý nhiều giá trị.