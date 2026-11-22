# Kiến thức nền và trình tự học annotation trong Java Core

Annotation trong Java là cách gắn **metadata (siêu dữ liệu)** có cấu trúc vào mã nguồn. Muốn hiểu những annotation trong Spring, JPA hay thư viện kiểm thử, trước tiên cần biết annotation của ngôn ngữ Java tồn tại đến giai đoạn nào, ai đọc nó và cơ chế nào thực sự tạo ra hành vi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích annotation là metadata, không phải logic tự chạy.
- Đọc annotation có sẵn và tự khai báo annotation bằng `@interface`.
- Phân biệt `@Target`, `@Retention`, `SOURCE`, `CLASS`, `RUNTIME`.
- Tạo một chương trình Java 17+ đọc annotation bằng Reflection.
- Phân biệt kiểm tra của compiler, annotation processor và xử lý lúc runtime.
- Tự xác định trình tự học để sau này đọc annotation của framework có cơ sở.

## 2. Annotation là gì?

Ví dụ quen thuộc:

~~~java
@Override
public String toString() {
    return "Hello";
}
~~~

`@Override` thông báo với **trình biên dịch** rằng phương thức phải ghi đè/triển khai một phương thức phù hợp. Nếu chữ ký sai, `javac` báo lỗi. Bản thân `@Override` không chứa đoạn logic kiểm tra và không tự gọi `toString()`.

Nên đặt bốn câu hỏi khi gặp bất kỳ annotation nào: **gắn vào đâu → lưu đến khi nào → ai đọc → thành phần đọc thực hiện điều gì?**

| Thành phần | Thời điểm | Điều có thể làm |
| --- | --- | --- |
| Java compiler | Khi biên dịch | Kiểm tra `@Override`, xử lý cảnh báo deprecation, áp dụng `@SuppressWarnings` |
| Annotation processor | Khi biên dịch | Kiểm tra ràng buộc, phát sinh mã hoặc tài nguyên |
| Ứng dụng/thư viện dùng Reflection | Khi chạy | Đọc annotation có retention `RUNTIME`, rồi thực hiện logic riêng |
| Công cụ đọc bytecode | Sau biên dịch | Phân tích thông tin annotation trong file `.class` |

**Một annotation không tự thực thi logic.** Nếu tự tạo `@Log` rồi gắn lên method, log không xuất hiện trừ khi bạn xây dựng hoặc sử dụng một bộ xử lý hiểu annotation đó. Annotation khác comment ở chỗ nó có cú pháp/kiểu được kiểm tra và có thể được các công cụ xử lý; nó cũng không thay thế method, interface hay thuật toán.

## 3. Cú pháp và annotation có sẵn

Một số cách dùng:

~~~java
@Override
@Deprecated(since = "17")
@SuppressWarnings({"rawtypes", "unchecked"})
~~~

Ví dụ trên là ba annotation đặt độc lập để minh họa cú pháp, không phải một khai báo Java hoàn chỉnh. Cú pháp `@Name` không có đối số; `@Name(element = value)` truyền một phần tử; phần tử tên `value` có thể viết ngắn thành `@Name(value)` khi phù hợp.

Các annotation nền tảng:

- `@Override`: compiler kiểm tra việc ghi đè/triển khai phương thức.
- `@Deprecated`: đánh dấu API không còn được khuyến khích dùng, nhưng không tự chặn lời gọi.
- `@SuppressWarnings`: yêu cầu compiler bỏ qua những nhóm cảnh báo được hỗ trợ trong phạm vi chỉ định; không sửa lỗi gốc.
- `@FunctionalInterface`: yêu cầu compiler kiểm tra interface đáp ứng hợp đồng functional interface.

Đây là annotation thuộc Java Core. Annotation của Spring/JPA có thể có cú pháp giống hệt nhưng hành vi phụ thuộc mã thư viện/framework xử lý chúng.

## 4. Tự định nghĩa annotation với `@interface`

~~~java
@interface LessonInfo {
    String author();                // Bắt buộc khi sử dụng.
    int level() default 1;         // Có giá trị mặc định.
    String[] topics() default {};  // Phần tử mảng.
}
~~~

Annotation element có cú pháp giống method không tham số: `author()`, `level()`, `topics()`. Chúng khai báo **thuộc tính metadata**, không phải body xử lý. `default` cho phép người dùng không cần khai báo phần tử đó; phần tử không có `default` là bắt buộc.

Ví dụ sử dụng:

~~~java
@LessonInfo(author = "Team Java", level = 2, topics = {"core", "metadata"})
class FirstLesson {}
~~~

Kiểu trả về hợp lệ của element: kiểu nguyên thủy, `String`, `Class`, kiểu `enum`, một kiểu annotation, hoặc mảng một chiều của các kiểu trên. Các dạng như `List<String>`, `Map`, đối tượng tùy ý, mảng nhiều chiều, element có tham số/`throws` không hợp lệ. Giá trị phải dùng được tại thời điểm biên dịch; không dùng kết quả gọi method runtime để truyền vào annotation. `null` cũng không phải giá trị hợp lệ cho element.

Nếu annotation định nghĩa element tên `value`, có thể viết:

~~~java
@interface Label {
    String value();
}

@Label("intro")
class Intro {}
~~~

`@Label("intro")` là cách rút gọn của `@Label(value = "intro")`.

## 5. Hai meta-annotation cần học đầu tiên

Meta-annotation là annotation dùng để mô tả một **annotation type** khác.

### 5.1. `@Target` quy định vị trí gắn

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface ReviewTag {
    String value();
}
~~~

`@ReviewTag` được gắn lên khai báo kiểu hoặc phương thức, nhưng không gắn lên field/parameter theo khai báo `@Target` này. Các `ElementType` thường gặp:

| Giá trị | Áp dụng vào |
| --- | --- |
| `TYPE` | Khai báo class, interface, enum, annotation type |
| `METHOD` | Khai báo phương thức |
| `FIELD` | Khai báo trường |
| `PARAMETER` | Tham số phương thức/constructor |
| `CONSTRUCTOR` | Constructor |
| `LOCAL_VARIABLE` | Biến cục bộ |
| `ANNOTATION_TYPE` | Khai báo annotation type |
| `TYPE_PARAMETER` | Tham số kiểu như `<T>` |
| `TYPE_USE` | Vị trí sử dụng một kiểu (kể cả trong một số generic) |

`TYPE` và `TYPE_USE` không đồng nghĩa: khai báo một class khác với chỗ sử dụng một kiểu trong biến, kiểu trả về hay generic. Khi không có `@Target`, annotation dùng được trong các ngữ cảnh khai báo phù hợp, nhưng không nên mặc định nó áp dụng cho mọi vị trí `TYPE_USE`.

### 5.2. `@Retention` quy định tuổi thọ metadata

| Policy | Có trong source | Có trong `.class` | Reflection thông thường lúc chạy đọc được? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không |
| `CLASS` | Có | Có | Không |
| `RUNTIME` | Có | Có | Có |

- `SOURCE`: chỉ cần thông tin trong quá trình xử lý nguồn/biên dịch.
- `CLASS`: lưu vào bytecode để công cụ đọc `.class` có thể xử lý, nhưng không hiện qua Reflection tiêu chuẩn.
- `RUNTIME`: giữ metadata để truy vấn bằng Reflection lúc chạy.

**Mặc định, annotation không khai báo `@Retention` sẽ có policy `CLASS`.** Ghi trong mã nguồn không có nghĩa `getAnnotation(...)` tìm được lúc runtime.

Ví dụ:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface AuditLabel {
    String value();
}
~~~

Các meta-annotation học tiếp khi cần: `@Documented` đưa annotation vào Javadoc; `@Inherited` hỗ trợ truy vấn annotation của superclass trên **class declaration** theo quy tắc Java, không tự kế thừa annotation gắn ở method/field/interface; `@Repeatable` cho phép dùng cùng annotation nhiều lần tại một vị trí với container annotation phù hợp.

## 6. Ví dụ Java 17+ chạy được: annotation và Reflection

Tạo file **`AnnotationTour.java`** dưới đây. Tất cả khai báo nằm trong cùng một file; chỉ `AnnotationTour` là public.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface LessonInfo {
    String author();
    int level() default 1;
    String[] topics() default {};
}

@LessonInfo(author = "Team Java", topics = {"metadata", "reflection"})
class Lesson {
    @LessonInfo(author = "Team Java", level = 2)
    public void run() {
        System.out.println("Lesson is running");
    }
}

public class AnnotationTour {
    public static void main(String[] args) throws ReflectiveOperationException {
        LessonInfo onClass = Lesson.class.getAnnotation(LessonInfo.class);
        LessonInfo onMethod = Lesson.class
                .getDeclaredMethod("run")
                .getAnnotation(LessonInfo.class);

        System.out.println(onClass.author());
        System.out.println(onClass.level());
        System.out.println(Arrays.toString(onClass.topics()));
        System.out.println(onMethod.level());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac AnnotationTour.java
java AnnotationTour
~~~

Stdout chính xác:

~~~text
Team Java
1
[metadata, reflection]
2
~~~

Giải thích: annotation của `Lesson` có `author = "Team Java"`, `topics` gồm hai phần tử, còn `level` lấy mặc định `1`. Annotation của `run()` ghi đè `level` thành `2`. `Lesson.class.getAnnotation(...)` đọc trên class; `getDeclaredMethod("run").getAnnotation(...)` đọc trên method. Không có `new Lesson().run()` nên **không xuất hiện** dòng `Lesson is running`. Việc đọc metadata không gọi method đã đánh dấu.

Thử đổi `@Retention(RUNTIME)` thành `@Retention(CLASS)`. Chương trình vẫn biên dịch, nhưng `getAnnotation` trả `null`; đoạn mã này sẽ ném `NullPointerException` khi dùng `onClass.author()`. Khi viết mã thật, nên kiểm tra annotation có hiện diện (ví dụ `isAnnotationPresent(...)` hoặc so sánh với `null`) trước khi đọc element.

## 7. Annotation processing lúc biên dịch khác Reflection lúc chạy

**Compile-time processing:** annotation processor (thường triển khai `javax.annotation.processing.AbstractProcessor`) được compiler gọi khi cấu hình/phát hiện phù hợp. Nó dùng mô hình phần tử của compiler để xác thực, báo lỗi/cảnh báo, sinh source/class/tài nguyên. Processor làm việc khi biên dịch và không cần gọi `main()`. Annotation có retention `RUNTIME` **không phải điều kiện bắt buộc** để processor đọc nó, bởi processor tham gia trong quá trình compiler xử lý mã.

**Runtime Reflection:** mã đang chạy gọi API như `Class.getAnnotation(...)`, `Method.getDeclaredAnnotations()` hoặc `isAnnotationPresent(...)`. Với API Reflection thông thường, annotation phải có retention `RUNTIME` để hiện diện. Nhưng phần quyết định hành động vẫn do chương trình/thư viện viết ra.

~~~text
Mã .java
   |
   +--> javac / annotation processor
   |      kiểm tra; có thể sinh mã, lỗi, tài nguyên
   |
   +--> file .class / JVM class loading
               |
               +--> mã runtime dùng Reflection
                       |
                       +--> đọc annotation RUNTIME
                       +--> quyết định hành vi nếu có bộ xử lý
~~~

Một framework có thể kết hợp Reflection, quét classpath hoặc phân tích bytecode. Ở mức Java Core, điều cần hiểu là ranh giới giữa **metadata** và **thành phần xử lý metadata**.

## 8. Trình tự học đề xuất

| Bước | Học gì? | Tự kiểm chứng |
| --- | --- | --- |
| **1. Nhận diện** | Vai trò metadata, cú pháp `@...`, phân biệt annotation với comment và lời gọi method | Giải thích vì sao `@Override` kiểm tra chữ ký mà không chạy method |
| **2. Built-in** | `@Override`, `@Deprecated`, `@SuppressWarnings`, `@FunctionalInterface` | Cố tình khai báo sai override; xem lỗi compiler; thử functional interface |
| **3. Khai báo** | `@interface`, element bắt buộc, `default`, `value`, kiểu/mảng hợp lệ | Tự viết `@LessonInfo` với vài element |
| **4. Meta-annotation** | `@Target`, `@Retention`; tác động của `TYPE`/`METHOD` và `CLASS`/`RUNTIME` | Đổi target và retention, đối chiếu lỗi compiler và giá trị Reflection |
| **5. Reflection** | `Class`, `Method`, `getAnnotation`, `getDeclaredAnnotation`, `isAnnotationPresent` | Chạy `AnnotationTour.java` và đoán stdout trước khi chạy |
| **6. Mở rộng** | `@Documented`, `@Inherited`, `@Repeatable`, `TYPE_USE` | Thử class con, annotation lặp, phân biệt vị trí khai báo và sử dụng kiểu |
| **7. Processing/framework** | Compile-time processor với runtime processor/Reflection | Vẽ đường đi từ `@Something` tới mã thật sự xử lý |

Chỉ chuyển sang bước tiếp theo khi trả lời được: annotation được gắn **ở đâu**, giữ **đến khi nào**, được **ai đọc** và **việc đọc dẫn đến hành động gì**? Trình tự này giúp tránh học thuộc tên annotation framework mà chưa hiểu điều gì xảy ra.

## 9. Sai lầm phổ biến

1. **Nghĩ annotation tự tạo logic.** `@Log` không ghi log nếu không có bộ xử lý. Tìm nơi framework/ứng dụng thật sự đọc metadata.
2. **Dùng `CLASS` rồi đọc bằng Reflection runtime.** Khi nhận `null`, kiểm tra retention và đúng phần tử class/method/field đang truy vấn.
3. **Gắn annotation sai target.** `@Target(METHOD)` không dùng cho field; `TYPE` không mặc nhiên bao gồm mọi `TYPE_USE`.
4. **Khai báo element sai kiểu.** `List<String>` hay `default null` không hợp lệ. Hãy dùng kiểu/mảng được Java cho phép.
5. **Hiểu sai `@Inherited`.** Nó không có nghĩa method, field, interface annotations tự truyền xuống mọi class con. Dùng `getDeclaredAnnotation` và `getAnnotation` để quan sát khác biệt ở class khi phù hợp.
6. **Nhầm processor với Reflection.** Phân biệt thời điểm biên dịch và lúc chạy rồi mới quyết định retention/API đọc.
7. **Lạm dụng `@SuppressWarnings`.** Chỉ tắt cảnh báo sau khi đã hiểu nguyên nhân; annotation không làm cast sai hoặc logic thiếu an toàn trở nên đúng.

## 10. Bài tập thực hành

1. Tạo class con, cố tình đặt `@Override` lên method viết sai tên, dự đoán và giải thích lỗi từ `javac`.
2. Tạo `@Owner` chỉ dùng cho `TYPE`, với `String value()` bắt buộc và `int priority() default 0`. Thử cả `@Owner("backend")` và dạng đặt tên phần tử.
3. Tạo `@Marker` có retention `RUNTIME` trên một method, đọc bằng Reflection và kiểm tra `null` an toàn. Chuyển sang `CLASS`, so sánh kết quả.
4. Đổi `@Target` rồi gắn thử annotation lên class, method, field, một vị trí `TYPE_USE`. Ghi lại trường hợp biên dịch được/không được.
5. Giả sử một framework cung cấp `@Route("/hello")`. Mô tả những thành phần cần có để HTTP request thực sự gọi được method gắn annotation; xác định ai đọc metadata và ai gọi method.

## 11. Checklist trước khi học annotation framework

- Tôi giải thích được tại sao gắn `@...` không làm mã tự thực thi.
- Tôi phân biệt được compiler, annotation processor và Reflection runtime.
- Tôi biết `@Target` giới hạn vị trí và `@Retention` giới hạn vòng đời; mặc định là `CLASS`.
- Tôi tự viết được annotation type có element bắt buộc, `default` và phần tử mảng.
- Tôi chạy được một ví dụ `RUNTIME` với Reflection, giải thích đúng stdout, xử lý được annotation vắng mặt.
- Tôi biết khi gặp annotation mới phải tìm **bộ xử lý** và quy tắc thực thi thay vì suy diễn hành vi từ tên gọi.

Nắm chắc các điểm trên là nền tảng để tiếp tục nghiên cứu annotation trong Spring, JPA và các thư viện Java khác.