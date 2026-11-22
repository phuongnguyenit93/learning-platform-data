# Cú pháp rút gọn với phần tử value trong Java Annotation

## 1. Vì sao có cú pháp rút gọn?

Một annotation trong Java được khai báo bằng từ khóa @interface. Các phương thức không có tham số trong annotation type được gọi là **phần tử (element)**; khi sử dụng annotation, ta gán giá trị cho chúng. Nếu phần tử được đặt tên chính xác là **value**, Java cho phép bỏ phần tên value = trong một trường hợp phổ biến: chỉ cung cấp giá trị cho phần tử này.

Ví dụ, hai cách dùng sau **tương đương về ý nghĩa**:

~~~java
@Label(value = "Java")
class FirstCourse {}

@Label("Java")
class SecondCourse {}
~~~

Trong đó, định nghĩa annotation có thể là:

~~~java
@interface Label {
    String value();
}
~~~

Dòng @Label("Java") được gọi là **single-element annotation** (annotation dạng một phần tử); trình biên dịch hiểu chuỗi "Java" là đối số của phương thức value(). Đây là cú pháp của ngôn ngữ Java, không phải tính năng do một thư viện hay framework tự tạo.

## 2. Quy tắc chính xác để bỏ value =

Cách viết ngắn chỉ hợp lệ nếu đồng thời thỏa mãn các điều kiện:

1. Annotation type khai báo một phần tử có **tên chính xác là value** (Java phân biệt chữ hoa và chữ thường).
2. Trong lần sử dụng đó, ta **chỉ chỉ định giá trị cho phần tử value**. Không trộn cú pháp rút gọn với các cặp tên = giá trị khác trong cùng một annotation.
3. Các phần tử khác, nếu có, phải có giá trị mặc định; nếu còn phần tử bắt buộc không được cấp giá trị, annotation sẽ không biên dịch.
4. Biểu thức truyền vào phải đúng kiểu hợp lệ của phần tử value theo quy tắc annotation trong Java.

Điều cần phân biệt: **Tên value là đặc biệt; nó không bắt buộc phải là phần tử duy nhất được khai báo**. Annotation vẫn có thể có các phần tử khác mang giá trị mặc định.

~~~java
@interface Task {
    String value();
    int priority() default 1;
    boolean active() default true;
}

@Task("compile")
class CompileTask {} // priority = 1, active = true

@Task(value = "deploy", priority = 5, active = false)
class DeployTask {}
~~~

Nếu cần chỉ định thêm priority hoặc active, phải viết các phần tử bằng tên như @Task(value = "deploy", priority = 5). Không thể viết @Task("deploy", priority = 5): Java không cho trộn giá trị không có tên với một cặp phần tử có tên.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo đúng một tệp **Main.java** với toàn bộ nội dung sau. @Retention(RetentionPolicy.RUNTIME) giữ annotation trong lúc chạy để có thể đọc qua reflection. @Target(ElementType.TYPE) giới hạn vị trí gắn annotation vào các kiểu như class.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Lesson {
    String value();
    int order() default 1;
}

@Lesson("Java")
class CoreLesson {}

@Lesson(value = "Spring", order = 2)
class SpringLesson {}

public class Main {
    public static void main(String[] args) {
        show(CoreLesson.class);
        show(SpringLesson.class);
    }

    private static void show(Class<?> type) {
        Lesson lesson = type.getAnnotation(Lesson.class);
        System.out.println(
                type.getSimpleName() + ": "
                        + lesson.value() + ", order=" + lesson.order());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Đầu ra chính xác:

~~~text
CoreLesson: Java, order=1
SpringLesson: Spring, order=2
~~~

Ở @Lesson("Java"), trình biên dịch gắn chuỗi cho value(); order() lấy mặc định 1. Ở @Lesson(value = "Spring", order = 2), hai phần tử được chỉ định tường minh. Khi gọi lesson.value() qua reflection, cả hai trường hợp đều được truy xuất giống nhau. **Cú pháp ngắn và dài không tạo ra hai kiểu annotation khác nhau, cũng không làm thay đổi dữ liệu được gắn vào annotation.**

Lưu ý: đoạn chương trình dùng reflection vì annotation được giữ ở RUNTIME. Cú pháp rút gọn vẫn hoạt động với annotation có retention SOURCE hoặc CLASS; việc dùng value không phụ thuộc vào reflection.

## 4. Phần tử value thuộc kiểu mảng

Cú pháp ngắn cũng áp dụng khi value() trả về một mảng. Với phần tử có kiểu mảng, Java còn cho phép bỏ cặp ngoặc nhọn quanh **một giá trị đơn** trong ngữ cảnh gán giá trị cho phần tử annotation.

~~~java
@interface Tags {
    String[] value();
}

@Tags(value = {"java", "core"})
class ExplicitTags {}

@Tags({"java", "core"})
class ShortTags {}

@Tags("java")
class SingleTag {}
~~~

Giải thích:

- @Tags(value = {"java", "core"}) ghi tên phần tử đầy đủ.
- @Tags({"java", "core"}) lược bỏ value =, nhưng vẫn truyền một mảng gồm hai chuỗi.
- @Tags("java") lược bỏ cả value = và cặp ngoặc nhọn của mảng một phần tử. Giá trị của value() **vẫn có kiểu String[]**, với một phần tử là "java".
- Nếu muốn một mảng rỗng, viết @Tags({}); không thể suy ra mảng rỗng từ @Tags() trừ khi value() có mặc định phù hợp.

Hai hình thức thường gặp trong Java chuẩn cũng dựa trên quy tắc này:

~~~java
@SuppressWarnings("unchecked")
@SuppressWarnings({"unchecked", "deprecation"})
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
~~~

Đây là **các ví dụ cú pháp riêng lẻ**, không phải bốn annotation cần gắn liên tiếp vào cùng một khai báo. @SuppressWarnings có phần tử value() kiểu String[]; @Target có phần tử value() kiểu ElementType[]; @Retention có phần tử value() kiểu RetentionPolicy.

## 5. Có thể bỏ cả ngoặc đơn khi nào?

Cần phân biệt **bỏ value =** với **bỏ ngoặc và đối số**. Nếu value() là phần tử bắt buộc, phải cấp giá trị: @Label("Java") hoặc @Label(value = "Java"). Viết @Label hay @Label() khi value() không có default sẽ gây lỗi biên dịch.

Ngược lại, nếu tất cả phần tử có default, có thể không cấp đối số:

~~~java
@interface Status {
    String value() default "draft";
    boolean visible() default true;
}

@Status
class DraftOne {}

@Status()
class DraftTwo {}

@Status("published")
class Published {}
~~~

@Status và @Status() đều sử dụng value = "draft" và visible = true. @Status("published") chỉ thay value, còn visible giữ mặc định. Phần tử mang tên value **không đồng nghĩa** với khai báo default: default là giá trị được ghi sau từ khóa default ngay trong @interface.

Một annotation không có phần tử, ví dụ @Override, thường được dùng ở dạng marker @Override. Marker annotation và single-element annotation khác nhau về khai báo cũng như cách cung cấp giá trị.

## 6. Các trường hợp sai thường gặp

### 6.1. Phần tử không có tên value

~~~java
@interface Category {
    String name();
}

@Category(name = "backend")
class ValidCategory {}

// KHÔNG HỢP LỆ: Category không khai báo value()
@Category("backend")
class InvalidCategory {}
~~~

Trình biên dịch không đoán "name" là phần tử ngầm định. Chỉ tên value mới được hưởng cú pháp rút gọn.

### 6.2. Có thêm phần tử bắt buộc chưa cung cấp

~~~java
@interface Audit {
    String value();
    String author();
}

// KHÔNG HỢP LỆ: thiếu author() bắt buộc
@Audit("login")
class InvalidAudit {}

// HỢP LỆ: cung cấp đủ các phần tử
@Audit(value = "login", author = "team")
class ValidAudit {}
~~~

Mặc dù Audit có value(), @Audit("login") vẫn sai vì author() không có giá trị mặc định.

### 6.3. Trộn dạng ngắn với dạng có tên

~~~java
@interface Endpoint {
    String value();
    boolean secured() default true;
}

// KHÔNG HỢP LỆ
@Endpoint("/health", secured = false)
class InvalidEndpoint {}

// HỢP LỆ
@Endpoint(value = "/health", secured = false)
class ValidEndpoint {}
~~~

Khi cần ghi nhiều cặp name = value, luôn viết rõ phần tử value.

### 6.4. Nhầm kiểu dữ liệu hoặc truyền biểu thức không hợp lệ

~~~java
@interface Retry {
    int value();
}

@Retry(3)
class ValidRetry {}

// KHÔNG HỢP LỆ: value() đòi hỏi int, không phải String
@Retry("three")
class InvalidRetry {}
~~~

Giá trị annotation phải tuân thủ các kiểu phần tử được Java cho phép (kiểu nguyên thủy, String, Class, enum, annotation hoặc mảng một chiều của các kiểu này) và quy tắc biểu thức tương ứng. Ví dụ, đối số kiểu String hoặc int phải là biểu thức hằng ở thời điểm biên dịch; không thể truyền tùy ý kết quả của một lời gọi phương thức lúc chạy.

### 6.5. Nghĩ value() mặc nhiên tồn tại

~~~java
@interface EmptyMarker {}

// HỢP LỆ: marker annotation
@EmptyMarker
class PlainMarker {}

// KHÔNG HỢP LỆ: không có phần tử value()
@EmptyMarker("hello")
class InvalidMarker {}
~~~

Java chỉ cho phép viết @X(value = ...) hoặc @X(...) khi annotation type thực sự khai báo phần tử value() thích hợp. Từ khóa @interface không tự sinh value().

**Lưu ý khi thử lỗi:** Các khối ví dụ có chú thích "KHÔNG HỢP LỆ" cố ý minh họa mã sai và không được biên dịch nguyên khối. Chương trình hoàn chỉnh có thể chạy ở mục 3.

## 7. Cách đọc nhanh một annotation khi gặp trong dự án

Khi thấy @Something("text") trong code, hãy kiểm tra khai báo @interface Something (hoặc tài liệu API) theo trình tự:

1. Tìm phương thức value(), xem kiểu trả về là gì: String, Class<?>, enum, mảng, v.v.
2. Xem các phần tử khác có default hay không. Nếu không có default, đoạn sử dụng phải cung cấp các phần tử bắt buộc bằng tên.
3. Đối chiếu @Something("text") với @Something(value = "text") để hiểu giá trị đã gắn.
4. Nếu người viết chỉ định thêm một phần tử khác, chuyển sang dạng @Something(value = ..., other = ...).
5. Nếu value() là mảng, kiểm tra @Something("one") đang đại diện cho mảng một phần tử hay @Something({"one", "two"}) chứa nhiều phần tử.

Chẳng hạn, @SuppressWarnings("unchecked") không truyền cho một phần tử tên warning. Nó truyền chuỗi "unchecked" vào value() kiểu String[] của @SuppressWarnings; trình biên dịch chấp nhận dạng ngắn cho mảng một phần tử.

## 8. Ghi nhớ

- **@X("a") tương đương @X(value = "a")** nếu X khai báo value() và các yêu cầu khác của annotation đều được đáp ứng.
- Tên phần tử phải là **value** đúng chính tả; số phần tử khai báo có thể nhiều hơn một nếu các phần tử không được chỉ định đều có default.
- Khi cần cung cấp nhiều phần tử trong cùng một annotation, dùng **dạng có tên**: @X(value = "a", flag = true).
- Với value() trả về mảng, @X("a") có thể chỉ mảng một phần tử và @X({"a", "b"}) chỉ mảng nhiều phần tử.
- Giá trị default, thời điểm retention và vị trí target là các khái niệm độc lập với việc rút gọn cú pháp.