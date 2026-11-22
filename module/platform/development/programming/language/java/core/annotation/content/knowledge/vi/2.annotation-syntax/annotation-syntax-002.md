# Annotation đánh dấu và cú pháp không có phần tử trong Java

## 1. Annotation đánh dấu (marker annotation) là gì?

**Marker annotation** là một kiểu annotation **không khai báo phần tử (annotation element) nào**. Nó dùng sự **có mặt hoặc vắng mặt** của annotation để đánh dấu một khai báo, thay vì mang các tham số riêng như tên, số lượng hay cấu hình.

Khai báo đơn giản nhất:

~~~java
@interface Reviewed {
}
~~~

Ở đây:

- `@interface` tạo **annotation type**, khác với `interface` thông thường.
- `Reviewed` là tên kiểu annotation.
- Cặp ngoặc nhọn `{}` rỗng vì annotation không khai báo phần tử nào, chẳng hạn `String value();` hay `int level();`.
- Tên `Reviewed` không tự đặt ra một hành vi xử lý cụ thể. Mã hoặc công cụ khác phải được viết để nhận biết dấu này nếu cần tạo tác dụng.

Cách dùng điển hình:

~~~java
@Reviewed
class Article {
}
~~~

Ý nghĩa: lớp `Article` **được đánh dấu** là `Reviewed`. Annotation có thể được dùng làm tín hiệu cho compiler, bộ xử lý annotation hoặc framework, nhưng bản thân tên và việc gắn `@Reviewed` không tự thực hiện kiểm tra hoặc thay đổi hành vi chương trình.

Các annotation quen thuộc như `@Override` và `@FunctionalInterface` là ví dụ về kiểu annotation không có phần tử. Compiler có logic riêng để xử lý chúng: `@Override` yêu cầu phương thức override/implement hợp lệ và `@FunctionalInterface` yêu cầu kiểu interface đáp ứng quy tắc functional interface. Một marker annotation **tự định nghĩa** không mặc nhiên được compiler gán cho những quy tắc đó.

## 2. Hai cách viết khi không truyền phần tử: `@Reviewed` và `@Reviewed()`

Với annotation ở trên, **cả hai cú pháp đều hợp lệ** và thể hiện cùng một metadata:

~~~java
@Reviewed
class FirstArticle {
}

@Reviewed()
class SecondArticle {
}
~~~

- `@Reviewed` là dạng **không có cặp ngoặc**, ngắn gọn và thường được ưu tiên cho marker annotation.
- `@Reviewed()` có **cặp ngoặc rỗng**, thể hiện rõ rằng không có cặp `tên = giá trị` nào được cung cấp.
- Không phải khai báo `@interface Reviewed()`. Cặp ngoặc đơn chỉ xuất hiện ở **nơi sử dụng**, như `@Reviewed()`; cấu trúc khai báo vẫn là `@interface Reviewed { }`.

Đây là **cú pháp gắn metadata trên khai báo**, không phải lời gọi hàm `Reviewed()`, không tạo đối tượng theo cách `new` và không gọi một constructor của annotation.

Trong cùng một chương trình, hai lớp được gắn `@Reviewed` và `@Reviewed()` có thể được bộ xử lý xem như đều có dấu `Reviewed`. Không cần giữ nguyên hình thức có/không có ngoặc để phân biệt ý nghĩa.

### Ví dụ về cú pháp sai

Vì `Reviewed` không có phần tử nên các dạng truyền giá trị sau **không hợp lệ**:

~~~java
// Những dòng sau chỉ để minh họa lỗi biên dịch;
// không đặt chúng vào chương trình mẫu có thể chạy.

// @Reviewed("done")
// class InvalidA {}

// @Reviewed(value = "done")
// class InvalidB {}

// @Reviewed(status = true)
// class InvalidC {}
~~~

Ngay cả tên thường gặp `value` cũng không tồn tại nếu kiểu annotation chưa khai báo `value()`. Muốn truyền dữ liệu, phải định nghĩa phần tử phù hợp; lúc đó kiểu annotation không còn là marker annotation thuần túy.

## 3. Chương trình Java 17: hai cách viết có cùng kết quả

Tạo duy nhất tệp **`MarkerSyntaxDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Reviewed {
}

@Reviewed
class FirstArticle {
}

@Reviewed()
class SecondArticle {
}

class DraftArticle {
}

public class MarkerSyntaxDemo {
    public static void main(String[] args) {
        show("FirstArticle", FirstArticle.class);
        show("SecondArticle", SecondArticle.class);
        show("DraftArticle", DraftArticle.class);
    }

    private static void show(String name, Class<?> type) {
        boolean marked = type.isAnnotationPresent(Reviewed.class);
        System.out.println(name + ": " + marked);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac MarkerSyntaxDemo.java
java MarkerSyntaxDemo
~~~

**Stdout chính xác:**

~~~text
FirstArticle: true
SecondArticle: true
DraftArticle: false
~~~

Giải thích:

1. `FirstArticle` có `@Reviewed`, nên `isAnnotationPresent(Reviewed.class)` trả `true`.
2. `SecondArticle` có `@Reviewed()`, nên cũng trả `true`: cặp ngoặc rỗng không tạo ra trạng thái khác.
3. `DraftArticle` không được đánh dấu, nên trả `false`.
4. Chính phương thức `show(...)` **chủ động gọi reflection** để đọc annotation và in kết quả. Nếu không có mã đọc này, việc gắn `@Reviewed` sẽ không tự in ra màn hình.

Ví dụ dùng `@Retention(RetentionPolicy.RUNTIME)` vì muốn đọc metadata bằng reflection ở runtime. Nếu chuyển thành `RetentionPolicy.SOURCE` rồi biên dịch lại, ba dòng sẽ đều là `false` khi dùng API reflection trên class đã biên dịch. Việc annotation đã được gắn hợp lệ ở mã nguồn là vấn đề khác với việc runtime có thể truy xuất metadata.

### Vai trò của hai meta-annotation

- `@Target(ElementType.TYPE)` chỉ cho phép đánh dấu các **khai báo kiểu** phù hợp, như class, interface, enum, record hoặc annotation type. Đặt `@Reviewed` trực tiếp lên một field hay method sẽ bị compiler từ chối với cấu hình này.
- `@Retention(RetentionPolicy.RUNTIME)` giữ metadata đến thời điểm chạy và cho phép các API reflection tương ứng truy xuất nó. Nếu không khai báo `@Retention`, mặc định là `RetentionPolicy.CLASS`, không đọc trực tiếp bằng `Class.isAnnotationPresent(...)` tại runtime.

Hai meta-annotation này **cấu hình vị trí và thời gian lưu dấu**, không phải các phần tử do kiểu `Reviewed` khai báo. Vì vậy `Reviewed` vẫn là marker annotation dù trên định nghĩa của nó có `@Target` và `@Retention`.

## 4. Phải phân biệt “kiểu marker” với “dạng dùng không có tham số”

Đây là chỗ rất dễ nhầm trong Java:

> **Annotation type không có phần tử** chắc chắn là marker annotation. Nhưng **cú pháp `@Name` không có dấu ngoặc và tham số** vẫn có thể hợp lệ với một kiểu annotation *có phần tử*, miễn tất cả các phần tử của nó đã có giá trị mặc định.

Ví dụ:

~~~java
@interface FeatureFlag {
    boolean enabled() default true;
    String owner() default "team-a";
}

@FeatureFlag
class FeatureA {
}

@FeatureFlag()
class FeatureB {
}

@FeatureFlag(enabled = false)
class FeatureC {
}
~~~

Ba lần dùng đều hợp lệ:

- `@FeatureFlag`: không ghi phần tử nào, nên `enabled = true` và `owner = "team-a"` được lấy từ các `default`.
- `@FeatureFlag()`: cũng dùng cả hai giá trị mặc định.
- `@FeatureFlag(enabled = false)`: ghi đè một phần tử, phần tử `owner` vẫn nhận giá trị mặc định.

Dù có thể dùng `@FeatureFlag` mà không truyền gì, `FeatureFlag` **không phải một marker annotation type** vì nó có khai báo hai phần tử `enabled()` và `owner()`.

Ngược lại, với phần tử bắt buộc:

~~~java
@interface Route {
    String path();
}

// Không hợp lệ nếu dùng @Route hoặc @Route()
// vì thiếu phần tử path bắt buộc.

@Route(path = "/home")
class HomeRoute {
}
~~~

`@Route` và `@Route()` không thể thay cho `@Route(path = "...")` bởi `path()` không có giá trị `default`.

Bảng đối chiếu:

| Kiểu annotation | Có phần tử khai báo? | Dùng `@Name` được không? | Dùng `@Name()` được không? |
| --- | --- | --- | --- |
| `@interface Marker {}` | Không | Có | Có |
| `@interface Optional { int level() default 1; }` | Có, tất cả có mặc định | Có | Có |
| `@interface Required { int level(); }` | Có phần tử bắt buộc | Không | Không |

Cú pháp tại nơi sử dụng **không đủ** để kết luận một kiểu annotation có thực sự là marker hay không; hãy kiểm tra định nghĩa `@interface` để biết số phần tử khai báo.

## 5. Phân biệt với cú pháp một phần tử `value()`

Java cho phép viết ngắn gọn khi phần tử mang tên đặc biệt `value()`:

~~~java
@interface Label {
    String value();
}

@Label("core")
class TopicA {
}

@Label(value = "core")
class TopicB {
}
~~~

`@Label("core")` và `@Label(value = "core")` cung cấp cùng giá trị cho phần tử `value`. Đây là **cú pháp annotation một phần tử**, hoàn toàn khác với `@Reviewed` (không có phần tử nào). Vì `Label.value()` là bắt buộc, chỉ viết `@Label` hoặc `@Label()` sẽ lỗi biên dịch.

Điểm cần nhớ: tên `value` có ý nghĩa về **cú pháp rút gọn** của Java. Nó không biến một annotation có phần tử thành marker annotation. Nếu `value()` có `default`, ta còn có thể bỏ qua phần tử khi dùng, nhưng kiểu annotation đó vẫn khai báo phần tử.

## 6. Khi nào nên thiết kế marker annotation?

Chọn marker khi phần thông tin cần truyền về bản chất chỉ là **có/không** và không yêu cầu dữ liệu cấu hình bổ sung. Ví dụ trong một công cụ nội bộ, `@Reviewed` có thể nghĩa là một loại tài liệu đã đi qua quy trình duyệt. Bộ xử lý sẽ dùng sự hiện diện của dấu này để quyết định kiểm tra hoặc báo cáo phù hợp.

Một lựa chọn khác là dùng phần tử boolean:

~~~java
@interface ReviewedOption {
    boolean enabled() default true;
}
~~~

Cách này hợp lý khi thật sự cần các trạng thái hoặc khả năng cấu hình khác nhau, ví dụ `@ReviewedOption(enabled = false)`. Nếu chỉ cần đánh dấu đơn giản, `@interface Reviewed {}` gọn và rõ nghĩa hơn.

**Trước khi chọn marker**, cần xác định:

- **Dấu sẽ đặt ở đâu?** Khai báo `@Target` phù hợp nếu muốn hạn chế cách sử dụng.
- **Dấu phải còn ở giai đoạn nào?** Chọn `SOURCE`, `CLASS` hay `RUNTIME` tùy cách công cụ dự kiến đọc metadata.
- **Ai sẽ xử lý dấu?** Một processor khi biên dịch, một framework, hoặc mã reflection/đăng ký riêng.
- **Có thực sự chỉ cần sự hiện diện?** Nếu phải mang đường dẫn, tên, độ ưu tiên hay cấu hình, hãy cân nhắc thêm phần tử thay vì tạo nhiều marker khó quản lý.

Marker annotation không tự phát ra lỗi/cảnh báo nghiệp vụ hay thay đổi chương trình. `@Override` có tác dụng ngay lúc biên dịch vì Java compiler được định nghĩa sẵn để hiểu annotation đó. Với annotation tự tạo, tác dụng ngoài những kiểm tra cú pháp/target cơ bản phụ thuộc vào **bộ xử lý hoặc mã tiêu thụ metadata**.

## 7. Lỗi thường gặp và cách nhận diện

**Nhầm 1: “Cứ dùng `@X` là kiểu `X` không có phần tử.”** Chưa chắc. `@X` vẫn dùng được khi `X` có phần tử nhưng tất cả đều có `default`. Kiểm tra phần thân định nghĩa `@interface X`.

**Nhầm 2: “`@X()` gọi constructor.”** Sai. Đây là dạng annotation với danh sách cặp `tên = giá trị` rỗng, không phải lời gọi constructor/method trong Java.

**Nhầm 3: “Marker vẫn truyền tham số qua `value` được.”** Sai. Nếu không khai báo `value()` thì `@X("text")` và `@X(value = "text")` đều không hợp lệ.

**Nhầm 4: “Có `@Retention(RUNTIME)` thì dấu tự làm công việc.”** Sai. `RUNTIME` chỉ quyết định metadata có thể được truy xuất khi chạy; cần mã xử lý để dùng thông tin đó.

**Nhầm 5: “Không có `@Target` thì có thể dùng marker ở mọi chỗ không hạn chế.”** Không nên giả định vậy. Java có các vị trí cú pháp khác nhau như declaration, type-use và type parameter; quy tắc áp dụng của annotation có hoặc không có `@Target` không phải là giấy phép gắn ở mọi biểu thức tùy ý. Hãy cấu hình target rõ ràng theo ý định.

**Nhầm 6: “Thêm `@Target` hoặc `@Retention` làm annotation trở thành loại có phần tử.”** Sai. Đây là meta-annotation gắn trên **khai báo annotation type**; chỉ các phương thức phần tử khai báo trong thân `@interface X` mới quyết định `X` có phần tử hay không.

## 8. Tự luyện tập

1. Định nghĩa `@interface Verified {}` rồi gắn lần lượt `@Verified` và `@Verified()` cho hai class. Hai cách sử dụng có khác nhau về ý nghĩa không?
2. Đổi `Reviewed` thành `@interface Reviewed { String by() default "QA"; }`. Có thể tiếp tục dùng `@Reviewed` không? `Reviewed` còn là marker annotation type không?
3. Thêm `String by();` vào kiểu `Reviewed` mà **không thêm** `default`. Những chỗ đang dùng `@Reviewed` và `@Reviewed()` xảy ra chuyện gì khi biên dịch?
4. Đổi retention trong `MarkerSyntaxDemo.java` thành `SOURCE`, chạy lại ví dụ. Vì sao reflection trả `false` dù mã nguồn vẫn có annotation?
5. Trong một dự án cần tự động kiểm tra class được gắn `@Verified`, hãy chỉ ra hai phần độc lập: khai báo dấu `@Verified` và nơi mã xử lý thực sự kiểm tra sự hiện diện của dấu.

**Đáp án định hướng:** (1) Không khác nghĩa; (2) còn dùng được do mặc định nhưng không còn là marker type; (3) lỗi thiếu phần tử bắt buộc `by`; (4) `SOURCE` không giữ metadata để runtime reflection đọc; (5) định nghĩa `@interface` cung cấp metadata, processor/framework/reflection phải chủ động xử lý.

Khi đọc code Java, hãy tách hai câu hỏi: **annotation type có khai báo phần tử hay không?** và **lần sử dụng này có truyền phần tử hay không?** Sự phân biệt đó giúp đọc chính xác cả marker annotation thuần túy lẫn các annotation có tham số mặc định.