# RUNTIME: lưu annotation trong class file và có thể đọc khi chạy

Khi một annotation type được khai báo với `@Retention(RetentionPolicy.RUNTIME)`, annotation gắn tại những vị trí có thể lưu metadata sẽ được giữ trong file `.class` và có thể được truy vấn lúc chạy qua các API Reflection của Java. Đây là cơ chế nền tảng giúp chương trình hoặc thư viện phát hiện metadata trên class, method, field, constructor, parameter và những đối tượng phản chiếu phù hợp.

Điểm cần hiểu chính xác: **retention `RUNTIME` làm metadata có thể đọc được; nó không tự sinh ra hành vi**. Muốn gọi một method, validate một trường hoặc thiết lập một thành phần dựa theo annotation, vẫn phải có mã thực thi việc đó.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích ý nghĩa chính xác của `RetentionPolicy.RUNTIME` theo vòng đời source → bytecode → runtime.
- Phân biệt `RUNTIME` với `SOURCE` và `CLASS`, bao gồm mặc định khi bỏ `@Retention`.
- Tạo annotation dùng `@Retention(RUNTIME)` và truy vấn trên class, method, field, parameter bằng Reflection.
- Hiểu sự khác nhau giữa `getAnnotation`, `getDeclaredAnnotation`, `getAnnotations` và các API dành cho annotation lặp.
- Nhận biết hạn chế của `@Inherited`, `@Target`, annotation trên khai báo biến cục bộ và type-use annotations.
- Biết cách xem metadata trong class file bằng `javap -v` và giải thích tại sao annotation không tự kích hoạt logic.

## 2. `@Retention(RUNTIME)` có nghĩa là gì?

`@Retention` là **meta-annotation** trong package `java.lang.annotation`: ta đặt nó lên định nghĩa của một annotation type để lựa chọn thời gian giữ lại những annotation thuộc type đó.

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface AuditMarker {
    String value();
}
~~~

Đoạn này là khai báo type minh họa, chưa phải một chương trình hoàn chỉnh. Khi mã sử dụng `@AuditMarker("login")` trên một phần tử phù hợp, compiler giữ metadata vào bytecode, và chương trình có thể truy vấn annotation khi JVM chạy.

Ba giá trị của `RetentionPolicy`:

| Policy | Hiện diện trong source | Thông thường có metadata ở `.class` | Reflection runtime tiêu chuẩn thấy? | Mục đích phổ biến |
| --- | --- | --- | --- | --- |
| `SOURCE` | Có | Không | Không | Kiểm tra/xử lý thông tin lúc biên dịch |
| `CLASS` | Có | Có | Không | Công cụ kiểm tra hoặc biến đổi bytecode |
| `RUNTIME` | Có | Có | Có | Code runtime đọc annotation và quyết định hành vi |

**Nếu annotation type không có `@Retention`, Java mặc định dùng `CLASS`**. Vì vậy, khi muốn kiểm tra bằng `Class.getAnnotation(...)`, đừng quên `@Retention(RetentionPolicy.RUNTIME)`.

Đối với các vị trí khai báo phổ biến như class, field, method hoặc parameter, mô hình trên giúp dự đoán kết quả. Java Language Specification có một ngoại lệ cần biết: annotation trên **khai báo biến cục bộ** và trên **khai báo tham số hình thức của lambda** không được giữ như declaration annotation trong binary, kể cả khi annotation type ghi `RUNTIME`. Cần phân biệt những annotation đó với **type-use annotations** trên kiểu dữ liệu: type annotations có quy tắc lưu giữ riêng và có thể được ghi trong bytecode khi retention phù hợp. Do đó `RUNTIME` không đồng nghĩa “mọi ký hiệu @ ở mọi chỗ đều truy vấn được qua cùng một API”.

## 3. Vòng đời: source → class file → Reflection

~~~text
Mã nguồn .java
    |
    |  @Retention(RUNTIME) trên annotation type
    |  @MyAnnotation(...) tại vị trí hợp lệ
    v
javac biên dịch
    |
    +--> .class có metadata runtime-visible
    |       (ví dụ thuộc tính RuntimeVisibleAnnotations)
    v
JVM tải class khi cần
    |
    +--> mã runtime dùng Reflection trên đúng phần tử
             |
             +--> Class / Method / Field / Parameter / ...
             +--> getAnnotation(MyAnnotation.class)
                       |
                       +--> đối tượng annotation để đọc các element
                       +--> ứng dụng tự quyết định hành vi tiếp theo
~~~

Trong file class, các annotation dùng `RUNTIME` thường được biểu diễn bằng những thuộc tính như `RuntimeVisibleAnnotations`; annotation trên tham số có `RuntimeVisibleParameterAnnotations`; annotation trên vị trí sử dụng kiểu có `RuntimeVisibleTypeAnnotations`. Các annotation `CLASS` có thể nằm trong thuộc tính `RuntimeInvisibleAnnotations` hay biến thể tương ứng, nhưng tên "Invisible" ở đây nói về **Reflection runtime**, không có nghĩa công cụ bytecode không thể đọc được.

JVM hoặc Reflection **không tự động quét toàn bộ classpath và xử lý mọi annotation**. Ứng dụng phải có sẵn cách tìm class/member cần kiểm tra và chủ động gọi API hoặc dùng thư viện/framework thực hiện việc đó.

`RUNTIME` cũng không tự thay đổi bytecode phương thức được đánh dấu, không chèn lời gọi log, không khởi tạo object, không tạo dependency injection hay transaction. Những hành vi đó, nếu có, đến từ code khác.

## 4. Khai báo annotation RUNTIME đúng cách

Một annotation đọc được trên class và method có thể định nghĩa như sau:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface EndpointInfo {
    String value();
    int version() default 1;
}
~~~

Ý nghĩa từng phần:

- `@Retention(RetentionPolicy.RUNTIME)`: annotation được lưu để truy vấn khi chạy.
- `@Target({TYPE, METHOD})`: cho phép sử dụng trên khai báo kiểu và method. `@Target` giới hạn vị trí, còn `@Retention` giới hạn vòng đời; chúng giải quyết hai câu hỏi khác nhau.
- `String value()`: element bắt buộc, ví dụ `@EndpointInfo("orders")`.
- `int version() default 1`: element có mặc định. Nếu nơi sử dụng không cung cấp `version`, khi đọc nhận `1`.

Không có quy định bắt buộc phải dùng `@Target` để có retention `RUNTIME`, nhưng khai báo target rõ ràng giúp compiler báo lỗi sớm nếu annotation được gắn sai chỗ. `@Target(TYPE)` cũng không đồng nhất với `@Target(TYPE_USE)`; annotation ở nơi sử dụng một kiểu có thể phải truy vấn qua `AnnotatedType` thay vì `Class.getAnnotation`.

## 5. Ví dụ Java 17+ chạy độc lập: so sánh RUNTIME, CLASS và SOURCE

Tạo file **`RuntimeRetentionDemo.java`** với toàn bộ nội dung dưới đây (không khai báo `package`). Các annotation type và class phụ đều không `public`; chỉ có một class public khớp tên file.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.FIELD,
    ElementType.PARAMETER
})
@interface RuntimeTag {
    String value();
    int level() default 1;
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassTag {}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceTag {}

@RuntimeTag(value = "service", level = 2)
@ClassTag
@SourceTag
class ExampleService {
    @RuntimeTag("action")
    public String process(@RuntimeTag("input") String value) {
        return value;
    }

    @RuntimeTag("id")
    private int id;
}

public class RuntimeRetentionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<ExampleService> type = ExampleService.class;
        RuntimeTag onType =
                type.getDeclaredAnnotation(RuntimeTag.class);
        Method method =
                type.getDeclaredMethod("process", String.class);

        System.out.println("type=" +
                onType.value() + ":" + onType.level());
        System.out.println("method=" +
                method.getAnnotation(RuntimeTag.class).value() + ":" +
                method.getAnnotation(RuntimeTag.class).level());
        System.out.println("field=" +
                type.getDeclaredField("id")
                    .getAnnotation(RuntimeTag.class).value());
        System.out.println("parameter=" +
                method.getParameters()[0]
                      .getAnnotation(RuntimeTag.class).value());

        System.out.println("runtime-visible=" +
                type.isAnnotationPresent(RuntimeTag.class));
        System.out.println("class-visible=" +
                type.isAnnotationPresent(ClassTag.class));
        System.out.println("source-visible=" +
                type.isAnnotationPresent(SourceTag.class));
    }
}
~~~

Chạy từ thư mục chứa file bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RuntimeRetentionDemo.java
java RuntimeRetentionDemo
~~~

**Stdout chính xác:**

~~~text
type=service:2
method=action:1
field=id
parameter=input
runtime-visible=true
class-visible=false
source-visible=false
~~~

### Giải thích kết quả

1. Class `ExampleService` có `@RuntimeTag(value = "service", level = 2)`. `getDeclaredAnnotation(RuntimeTag.class)` tìm thấy metadata được khai báo **trực tiếp** trên class, nên dòng đầu là `type=service:2`.
2. Method `process(String)` có `@RuntimeTag("action")`. Vì không ghi `level`, element này nhận mặc định `1`; vì thế kết quả `method=action:1`.
3. Trường `id` được khai báo `private`. `getDeclaredField("id")` vẫn lấy được metadata về khai báo field mà không cần đọc hay thay đổi **giá trị** private field; kết quả `field=id`. Việc truy cập nội dung private field là vấn đề khác và có thể bị kiểm soát.
4. Tham số method có `@RuntimeTag("input")`. `method.getParameters()[0].getAnnotation(...)` trả annotation trên tham số đầu tiên, nên có `parameter=input`. Không cần tùy chọn `-parameters` chỉ để đọc parameter annotations; `-parameters` chủ yếu giữ tên tham số nguồn cho Reflection.
5. `isAnnotationPresent(RuntimeTag.class)` là `true` trên class vì metadata runtime-visible có sẵn.
6. `ClassTag` có retention `CLASS`: annotation có thể xuất hiện trong bytecode nhưng Reflection runtime không thấy, nên `class-visible=false`.
7. `SourceTag` có retention `SOURCE`: annotation không được giữ trong class file theo chính sách này, nên `source-visible=false`.

Đoạn ví dụ **không gọi** `new ExampleService().process(...)`. Việc đọc metadata trên method không làm method được thực thi.

## 6. Tự kiểm tra class file bằng `javap -v`

Sau khi biên dịch ví dụ trên, chạy:

~~~bash
javap -v ExampleService
~~~

Khi duyệt phần metadata của class, bạn sẽ gặp những nhóm như:

~~~text
RuntimeVisibleAnnotations:
  ...
    RuntimeTag(...)
RuntimeInvisibleAnnotations:
  ...
    ClassTag
~~~

Đoạn trên **minh họa cấu trúc những nhóm liên quan**, không phải bản chép đầy đủ output `javap -v` (các chỉ số constant pool, layout, số dòng và ký pháp phụ thuộc compiler).

Để kiểm chứng đầy đủ:

- Tìm `RuntimeVisibleAnnotations` ở class, field và method gắn `@RuntimeTag`.
- Tìm `RuntimeVisibleParameterAnnotations` trên method `process` để thấy annotation gắn vào tham số `String value`.
- Tìm `RuntimeInvisibleAnnotations` cho `ClassTag` ở class.
- Xác nhận không có annotation usage `SourceTag` trong metadata được lưu của `ExampleService.class`.

Đừng nhầm việc `ClassTag` xuất hiện trong constant pool hoặc đoạn text của tool với việc có thể đọc qua `Class.getAnnotation`. Khả năng Reflection thấy metadata phụ thuộc chính sách retention và cách metadata được lưu, không phụ thuộc đơn thuần vào việc tên type có xuất hiện đâu đó trong kết quả dịch ngược.

Muốn quan sát `TYPE_USE` annotations, cần khai báo annotation có `@Target(TYPE_USE)` và tra cứu qua API Reflection phù hợp như `Field.getAnnotatedType()` hoặc `Method.getAnnotatedReturnType()`. Đó là vị trí lưu và cách đọc riêng, không tự đồng nhất với annotation khai báo trên field/method.

## 7. Chọn đúng Reflection API

Với `RUNTIME`, điều kiện cần là annotation **thực sự được gắn ở vị trí mà API đang kiểm tra**. Một annotation trên class không mặc nhiên xuất hiện khi truy vấn method của class đó.

| API | Mục đích | Ghi nhớ |
| --- | --- | --- |
| `element.getAnnotation(Tag.class)` | Lấy một annotation kiểu `Tag` nếu được coi là hiện diện; có thể trả `null` | Khi đọc class, `@Inherited` có thể tác động theo quy tắc riêng |
| `element.getDeclaredAnnotation(Tag.class)` | Chỉ lấy annotation được khai báo trực tiếp trên phần tử | Không tìm qua superclass |
| `element.isAnnotationPresent(Tag.class)` | Kiểm tra có annotation kiểu `Tag` theo quy tắc `getAnnotation` | Trả boolean |
| `element.getAnnotations()` | Trả các annotation hiện diện theo quy tắc API | Trên class có thể bao gồm một số annotation thừa kế |
| `element.getDeclaredAnnotations()` | Chỉ trả annotation trực tiếp | Trả mảng rỗng nếu không có |
| `element.getAnnotationsByType(Tag.class)` | Lấy nhiều annotation, hỗ trợ `@Repeatable` và quy tắc thừa kế phù hợp | Trả mảng, có thể dài 0 |
| `element.getDeclaredAnnotationsByType(Tag.class)` | Lấy annotation lặp được khai báo trực tiếp hoặc gián tiếp qua container | Không tra superclass |

`element` ở đây là đối tượng thực thi `AnnotatedElement`, ví dụ `Class`, `Method`, `Field` hoặc `Parameter`. Dùng `getDeclaredMethod(...)`/`getDeclaredField(...)` khi cần lấy member khai báo trên chính class, kể cả member `private`. Nếu cần giá trị của element sau khi tìm annotation, gọi các method của annotation instance, ví dụ `tag.value()`, `tag.level()`.

Một lưu ý quan trọng về `@Repeatable`: khi một loại annotation có thể lặp, compiler có thể đưa nhiều annotation vào một **container annotation**. `getAnnotationsByType(...)`/`getDeclaredAnnotationsByType(...)` được thiết kế để đọc xuyên qua container. Không nên giả định `getAnnotation(Tag.class)` luôn trả một phần tử khi có nhiều annotation cùng kiểu ở cùng vị trí.

### Xử lý annotation có thể vắng mặt

`getAnnotation(...)` không ném lỗi chỉ vì annotation vắng mặt: nó trả `null`. Ví dụ đúng:

~~~java
RuntimeTag tag = ExampleService.class.getAnnotation(RuntimeTag.class);
if (tag != null) {
    System.out.println(tag.value());
}
~~~

Đây là đoạn minh họa sử dụng các type của chương trình phía trên. Trong mã dùng thư viện, luôn xử lý khả năng thiếu annotation, sai target thực tế, inheritance không được áp dụng hoặc class được biên dịch bằng retention khác dự kiến. Gọi `tag.value()` trên `null` mới khiến chương trình lỗi `NullPointerException`.

## 8. `RUNTIME` không đồng nghĩa annotation được kế thừa

Ví dụ có hai lớp:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Category {
    String value();
}

@Category("base")
class Parent {}

class Child extends Parent {}
~~~

`Child.class.getAnnotation(Category.class)` có thể trả annotation từ `Parent` vì **`Category` có `@Inherited` và được gắn trên khai báo class**. Nhưng `Child.class.getDeclaredAnnotation(Category.class)` trả `null`, do `Child` không khai báo annotation trực tiếp.

Tất cả class đã dùng `@Inherited` cũng cần retention thích hợp nếu muốn Reflection runtime nhìn thấy annotation. **`RUNTIME` một mình không tạo quan hệ thừa kế**.

Giới hạn của `@Inherited`:

- Chỉ tác động khi truy vấn annotation trên **class**, theo chuỗi superclass, và annotation type có `@Inherited`.
- Không tự áp dụng như vậy cho interface mà class triển khai.
- Không tự chuyển annotation trên method/field của lớp cha thành annotation trực tiếp trên method/field của lớp con.
- Các API `getDeclared...` cố ý bỏ qua inherited annotations.

Đây là đoạn minh họa, không nên nối nó với file `RuntimeRetentionDemo.java` để tạo một chương trình duy nhất nếu không điều chỉnh import/tên file cho phù hợp.

## 9. Dùng RUNTIME trong ứng dụng như thế nào?

Một tình huống thực tế là cần chọn các method được phép chạy bằng tên lệnh. Ta có thể định nghĩa `@Command("run")` với retention `RUNTIME`, dùng Reflection tìm các method được đánh dấu, đọc giá trị `"run"` rồi đăng ký vào một bảng tra cứu. Bảng tra cứu sau đó điều phối lời gọi khi người dùng thực sự ra lệnh.

Những bước đó được thực hiện bởi **bộ xử lý** do ứng dụng/framework viết; `@Command` chỉ mang tên lệnh. Nếu không có mã quét và đăng ký, annotation không tự tạo command.

Tương tự, hệ sinh thái Java dùng annotation runtime làm một phần của cơ chế validation, dependency injection, mapping hoặc test discovery. Nhưng một framework có thể dùng cả kỹ thuật compile-time, quét bytecode và cơ chế trung gian; không nên mặc định mọi annotation của framework đều được đọc chỉ bằng `getAnnotation(...)`.

**Annotation processor trong `javac` cũng có thể quan sát annotation ở thời điểm biên dịch**, nên retention `RUNTIME` không phải điều kiện bắt buộc để processor chạy. Khi mục tiêu chỉ là xử lý compile-time, `SOURCE` đôi khi là lựa chọn thích hợp hơn.

### Chọn policy theo nhu cầu

- Chỉ cần compiler hoặc annotation processor kiểm tra metadata ở mã nguồn? Cân nhắc `SOURCE`.
- Muốn metadata có mặt trong `.class` cho công cụ hậu xử lý bytecode, không cần Reflection runtime? Cân nhắc `CLASS`.
- Cần chương trình/thư viện đọc metadata trên các phần tử khi JVM chạy? Chọn `RUNTIME` và đặt `@Target` phù hợp.

Chọn retention theo **người sẽ đọc dữ liệu và thời điểm đọc**, không dựa trên tên annotation hay mong muốn tự động hóa. Retention dài hơn cũng không biến annotation thành một cơ chế bảo mật: không thể chỉ dựa vào sự hiện diện của `@Secured` tự định nghĩa để bảo vệ lời gọi nếu không có bộ xử lý thực sự kiểm tra quyền.

## 10. Những trường hợp và lỗi thường gặp

### 10.1. Quên khai báo `@Retention`

~~~java
@interface Marker {
    String value();
}
~~~

`@Marker` sẽ có mặc định `CLASS`. Dù đã gắn trên class và `javac` biên dịch thành công, Reflection runtime tiêu chuẩn sẽ không thấy instance của annotation đó. Muốn đọc khi chạy, bổ sung `@Retention(RetentionPolicy.RUNTIME)` **trên annotation type**, sau đó biên dịch lại các thành phần cần thiết.

### 10.2. Dùng sai phần tử Reflection

Nếu gắn `@RuntimeTag` lên `process(...)` nhưng gọi `ExampleService.class.getAnnotation(RuntimeTag.class)`, kết quả nói về **annotation trên class**, không phải method. Trong ví dụ chính, class cũng có `@RuntimeTag` nên bạn nhận `"service"`, không phải `"action"`. Hãy lấy đúng `Method` rồi mới truy vấn.

### 10.3. Nhầm `getDeclaredAnnotation` với `getAnnotation`

Với annotation `@Inherited` trên superclass, `getAnnotation` ở subclass có thể lấy giá trị kế thừa; `getDeclaredAnnotation` chỉ lấy khai báo trực tiếp, nên có thể là `null`. Dùng API phù hợp với ý định, nhất là khi framework có hành vi kế thừa metadata.

### 10.4. Tưởng `RUNTIME` tự động khiến annotation được xử lý

Nếu chỉ tạo `@Audit` và gắn lên method thì không có log nào được sinh. Bạn cần viết/tích hợp code xử lý audit, và phải xem nó có thực sự tìm method/annotation ấy không.

### 10.5. Tưởng annotation trên một vị trí xuất hiện ở mọi API

Declaration annotations, parameter annotations và type-use annotations có API tra cứu khác nhau. Đặt `@Target(FIELD)` rồi đọc trên `Field.getAnnotatedType()` là khác với đặt `@Target(TYPE_USE)` vào **kiểu** của field. Xác định annotation đang mô tả khai báo hay kiểu sử dụng.

### 10.6. Coi biến cục bộ là ngoại lệ giống field

Một declaration annotation gắn trên khai báo local variable không được lưu vào binary như annotation trên field, kể cả với `RUNTIME`. Không có `LocalVariable` Reflection API để lấy declaration annotations tương tự `Field`. Nếu mục tiêu là metadata của type-use, đây là chủ đề khác và cần dùng API/bytecode tương ứng.

### 10.7. Nhầm với việc giữ tên tham số

`-parameters` giúp Reflection thấy tên tham số Java như `value` thay vì tên tổng hợp. Parameter annotations `RUNTIME` có thể được lấy bằng `Method.getParameters()[i].getAnnotation(...)` ngay cả khi không bật `-parameters`. Hai loại metadata này độc lập.

### 10.8. Suy ra hành vi runtime chỉ từ `javap`

Thấy `RuntimeVisibleAnnotations` trong bytecode chỉ chứng minh metadata được lưu và có thể được Reflection đọc đúng cách. Nó không chứng minh một thư viện đã quét class, đã đăng ký component hay đã áp dụng logic. Cần kiểm tra code điều phối thực sự.

## 11. Bài thực hành tự kiểm chứng

1. **Retention:** Chạy `RuntimeRetentionDemo.java`, sau đó đổi `@Retention(RetentionPolicy.RUNTIME)` của `RuntimeTag` thành `CLASS`. Trước khi chạy hãy dự đoán kết quả; điều chỉnh chương trình để kiểm tra `null` an toàn, tránh gọi `value()` trên annotation vắng mặt.
2. **Bytecode:** Chạy `javap -v ExampleService`. So sánh `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations`, tìm `RuntimeVisibleParameterAnnotations`; giải thích vì sao `SourceTag` không có trong phần annotation usage của class file.
3. **API:** Lấy `Method` tương ứng `process(String)` và kiểm tra `getAnnotation(RuntimeTag.class)`. So sánh với kết quả khi đọc annotation trên `Class`.
4. **Target:** Thu hẹp `@Target` của `RuntimeTag` xuống `METHOD` nhưng vẫn giữ các nơi gắn khác. Quan sát lỗi compiler: retention không thay thế kiểm tra target.
5. **Inheritance:** Tạo `Parent`/`Child` và `@Category` có `@Inherited` như minh họa. So sánh `Child.class.getAnnotation(...)` và `getDeclaredAnnotation(...)`, rồi bỏ `@Inherited` để đối chiếu.
6. **Missing annotation:** Viết một class không có `@RuntimeTag`. Dùng `getAnnotation(...)` cùng điều kiện kiểm tra `null`, xác nhận chương trình không lỗi.
7. **Design:** Thiết kế `@Action(name = "...")` có retention `RUNTIME` cho method. Nêu rõ một lớp xử lý cần làm gì để tìm annotation và thực thi đúng method, cùng các điểm cần kiểm soát về quyền truy cập và lỗi.

Tự đánh giá bằng bốn câu hỏi: **annotation ở đâu**, **có retention gì**, **API nào đọc được**, và **ai thực hiện hành vi sau khi đọc**. Nếu trả lời được cả bốn, bạn đã hiểu vai trò của `RUNTIME` trong Java Core.

## 12. Ghi nhớ

- `@Retention(RetentionPolicy.RUNTIME)` giữ annotation trong class file và cho phép Reflection runtime truy vấn metadata phù hợp.
- Bỏ `@Retention` đồng nghĩa mặc định `CLASS`, thông thường không thể đọc annotation bằng Reflection runtime.
- `@Target` và `@Retention` độc lập: một cái kiểm soát vị trí được gắn, một cái kiểm soát thời gian tồn tại.
- `getAnnotation` có thể trả `null`; `getDeclaredAnnotation` chỉ xét khai báo trực tiếp. `@Inherited` ảnh hưởng đến một số truy vấn trên class, không phải mọi member.
- Declaration annotation trên local variable và lambda formal parameter có ngoại lệ không được lưu trong binary; type-use annotations cần được xem riêng.
- Sự hiện diện của annotation `RUNTIME` không tự thực thi logic. Mã xử lý mới biến metadata thành hành vi của ứng dụng.

### Tham khảo

- [Java Language Specification 17, `9.6.4.2: @Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2).
- [Java SE 17: Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html).
- [Java SE 17: RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).
- [Java SE 17: AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17: Class Reflection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
