# Thiết kế annotation có chủ đích: @Target, @Retention, @Documented, @Inherited và @Repeatable

Java cho phép định nghĩa annotation bằng `@interface`, nhưng một annotation được thiết kế tốt không chỉ có tên và vài phần tử dữ liệu. Người tạo API phải quyết định **nơi được gắn**, **thời điểm metadata còn tồn tại**, **có xuất hiện trong tài liệu công khai**, **có được tra cứu qua superclass**, và **có được khai báo nhiều lần trên cùng phần tử hay không**.

Năm meta-annotation chuẩn trong chủ đề này có trách nhiệm khác nhau:

| Meta-annotation | Câu hỏi thiết kế | Ví dụ |
| --- | --- | --- |
| `@Target` | Annotation được viết **ở đâu**? | `@Target(ElementType.METHOD)` |
| `@Retention` | Metadata tồn tại **đến giai đoạn nào**? | `@Retention(RetentionPolicy.RUNTIME)` |
| `@Documented` | Annotation có là một phần của **hợp đồng tài liệu API**? | `@Documented` |
| `@Inherited` | Khi tra cứu trên class con, có được **tìm trên superclass**? | `@Inherited` |
| `@Repeatable` | Có thể dùng **nhiều annotation cùng kiểu** trên một phần tử? | `@Repeatable(Tags.class)` |

Các annotation này mô tả **quy tắc của một annotation type**; chúng không tự thực hiện kiểm tra dữ liệu, ghi log, phân quyền, retry hoặc sinh code ứng dụng. Hành vi nghiệp vụ chỉ phát sinh khi compiler, annotation processor, công cụ phân tích hoặc framework thực sự đọc và diễn giải metadata.

## 1. Quy trình lựa chọn từ yêu cầu, không phải bật đủ năm cờ

Một nguyên tắc thực tế là chỉ bật những cơ chế có ý nghĩa rõ ràng đối với người dùng annotation:

1. Xác định **consumer**: annotation processor lúc biên dịch, công cụ phân tích bytecode, runtime reflection hay framework.
2. Xác định **loại phần tử** consumer có thể xử lý: class, method, field, constructor, parameter, type use hoặc annotation khác.
3. Chọn retention **ngắn nhất nhưng đủ dùng**, tránh giữ lại metadata runtime không cần thiết.
4. Quyết định việc xuất hiện trong **Javadoc của API được annotate** có hữu ích hay không.
5. Nếu annotation đánh dấu class, quyết định subclass **nên kế thừa cấu hình hay phải khai báo lại**.
6. Nếu một phần tử cần nhiều giá trị cùng loại, cân nhắc repeatable annotation và **thiết kế container** tương thích.
7. Viết tài liệu cho element, default và quy tắc xung đột; kiểm thử cả compiler và reflection.

Không có cấu hình “bật tất cả là tốt nhất”. Ví dụ `@Documented` có thể hợp lý cho `@PublicApi`, nhưng không cần thiết cho annotation chỉ dành cho annotation processor nội bộ; `@Inherited` có thể đúng cho cấu hình class, nhưng không thích hợp nếu cấu hình phải xác định riêng ở từng subtype.

## 2. @Target — giới hạn nơi annotation được dùng

`java.lang.annotation.Target` nhận các hằng `ElementType`. Với annotation chuyên kiểm tra phương thức:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface Timed {
    String category() default "default";
}
```

`@Timed` chỉ được gắn vào **khai báo method**. Nó không được gắn lên field hoặc constructor, không được đặt tại **lời gọi method** và không tự cho phép annotate kiểu `String` trong `List<String>`.

Muốn cho phép nhiều vị trí, dùng một tập các giá trị:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audited {}
```

Đoạn này giả sử đã import `ElementType` và `Target`. Nó cho phép dùng `@Audited` trên khai báo class/interface và method theo những ngữ cảnh tương ứng.

Một số mục tiêu thường gặp:

| ElementType | Ví dụ nơi áp dụng |
| --- | --- |
| `TYPE` | Class, interface, enum hoặc khai báo annotation type |
| `FIELD` | Field của class, bao gồm enum constant |
| `METHOD` | Khai báo method |
| `CONSTRUCTOR` | Khai báo constructor |
| `PARAMETER` | Khai báo formal parameter |
| `ANNOTATION_TYPE` | Khai báo một annotation type |
| `TYPE_PARAMETER` | Khai báo type parameter `T` |
| `TYPE_USE` | Lần sử dụng kiểu, ví dụ `List<@Check String>` |
| `RECORD_COMPONENT` | Record component của record |

**Không trộn mục tiêu khai báo và kiểu sử dụng.** Với `List<@Check String>`, annotation cần cho phép `TYPE_USE`. Với `@Check private String code;`, vị trí có thể liên quan tới field declaration và/hoặc type use tùy `@Target` và quy tắc applicability; phải thiết kế target theo ý định consumer.

### Nếu bỏ @Target

Một annotation type không khai báo `@Target` có thể được dùng trong các **declaration contexts** thích hợp theo JLS. Nó **không tự trở thành** annotation dùng được ở mọi `TYPE_USE`. Đây không phải cách nên dùng để “để dành linh hoạt”: nếu chỉ consumer hỗ trợ method, hãy khai báo `@Target(METHOD)` để compiler sớm từ chối chỗ gắn sai.

Một sai lầm phổ biến là dùng `@Target({FIELD, METHOD, PARAMETER, TYPE_USE})` cho mọi annotation mà không có consumer xử lý từng vị trí. Điều đó tạo hợp đồng lỏng và hành vi khó giải thích. Hãy ưu tiên tập mục tiêu nhỏ, rõ ràng, có kiểm thử.

## 3. @Retention — quyết định vòng đời metadata

`java.lang.annotation.Retention` nhận một trong ba `RetentionPolicy`:

| Giá trị | Trình biên dịch và class file | Reflection runtime |
| --- | --- | --- |
| `SOURCE` | Có ở mã nguồn; không lưu dưới các annotation attributes của class file | Không đọc được |
| `CLASS` | Giữ trong class file, thường ở các `RuntimeInvisible...Annotations` attributes thích hợp | Không đọc qua reflection chuẩn |
| `RUNTIME` | Giữ trong class file ở các `RuntimeVisible...Annotations` attributes thích hợp | Có thể đọc qua API reflection phù hợp |

Nếu **không khai báo `@Retention`**, retention mặc định là `CLASS`. Đây là nguồn lỗi phổ biến khi code viết `getAnnotation(...)` nhưng nhận `null`.

Ví dụ annotation chỉ phục vụ annotation processor:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}
```

Đây là đoạn minh họa cần import `Retention`, `RetentionPolicy`, `Target` và `ElementType`. Nếu build chỉ cần processor đọc annotation từ mô hình nguồn, `SOURCE` thường phù hợp. Không cần giữ cấu hình đó đến runtime.

Ví dụ annotation phục vụ reflection:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Endpoint {
    String path();
}
```

Consumer có thể lấy `Method` và đọc `getAnnotation(Endpoint.class)`. Tuy nhiên, **`RUNTIME` không khiến annotation tự kích hoạt router**. Framework vẫn phải quét method, đọc `path()` và đăng ký route.

### Retention không phải target

Hai quyết định độc lập:

- `@Target(METHOD)`: annotation được **gắn ở khai báo method**.
- `@Retention(RUNTIME)`: annotation đó có thể được **đọc lúc chạy**.

Một annotation có target đúng nhưng retention `CLASS` sẽ không xuất hiện qua reflection runtime thông thường. Một annotation có retention `RUNTIME` nhưng đặt ở vị trí target không cho phép thì **lỗi biên dịch**, không có chuyện retention hợp thức hóa vị trí sử dụng.

## 4. @Documented — công bố annotation trong hợp đồng Javadoc

`java.lang.annotation.Documented` đánh dấu rằng **sự xuất hiện của annotation trên phần tử API** là nội dung mà công cụ như `javadoc` cần đưa vào tài liệu phù hợp.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** API được giới thiệu công khai và có hợp đồng ổn định. */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface PublicApi {
    /** @return phiên bản API bắt đầu hỗ trợ */
    String since();
}

/** Dịch vụ của thư viện. */
@PublicApi(since = "1.0")
class LibraryService {}
```

Đây là khai báo hợp lệ, không chứa `main`. Với `@Documented`, Javadoc của `LibraryService` có thể thể hiện annotation `@PublicApi(since = "1.0")` như một phần hợp đồng công khai.

**Phân biệt ba khái niệm:**

- Chú thích `/** ... */` viết **Javadoc giải thích annotation type và element**.
- `@Documented` quyết định **sự có mặt/giá trị annotation tại nơi sử dụng** có được xem như phần hợp đồng tài liệu.
- `@Retention` quyết định **lưu metadata**, không quyết định mức độ hữu ích của nội dung Javadoc.

`@Documented` **không tự ghi log**, không ép framework tôn trọng annotation và không có tác dụng kế thừa superclass. Một annotation chỉ phục vụ build nội bộ có thể không cần `@Documented`. Ngược lại, các annotation ảnh hưởng tới người sử dụng thư viện, compatibility hoặc contract thường đáng được thể hiện trong Javadoc.

## 5. @Inherited — tìm annotation qua superclass của class

`java.lang.annotation.Inherited` khiến một kiểu annotation khi được truy vấn trên **class declaration** có thể được tìm trên superclass nếu class hiện tại không khai báo trực tiếp loại annotation ấy.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Policy {
    String value();
}

@Policy("base")
class Base {}

class Child extends Base {}
```

Trong runtime reflection:

```java
// Với các khai báo từ ví dụ ở trên:
Child.class.getAnnotation(Policy.class).value(); // "base"
Child.class.getDeclaredAnnotation(Policy.class); // null
```

Hai biểu thức trên là minh họa kết quả khi đặt trong một method. `getAnnotation()` có thể thấy annotation **present** theo quy tắc `@Inherited`. `getDeclaredAnnotation()` chỉ nhận annotation **khai báo trực tiếp** trên `Child`.

**Giới hạn không được bỏ qua:**

- `@Inherited` chỉ có ý nghĩa kế thừa chuẩn khi tra cứu annotation trên **class**, dọc chuỗi **superclass**.
- Nó không tự tra cứu annotation trên **interface** mà class `implements`.
- Nó không làm annotation gắn trên **method bị override**, field bị che, constructor hoặc parameter tự xuất hiện trên phần tử tương ứng của subclass.
- Khi subclass khai báo annotation cùng kiểu, giá trị trực tiếp trên subclass được dùng theo quy tắc tra cứu thay vì tự gộp với superclass.
- Nếu annotation cần được đọc bằng reflection lúc chạy, phải có `@Retention(RUNTIME)`. Có `@Inherited` nhưng retention `CLASS` không làm reflection bỗng đọc được.

**Câu hỏi thiết kế:** Bạn muốn class con **mặc nhiên dùng cấu hình của class cha** hay mỗi class phải xác nhận cấu hình của chính nó? Với chính sách bảo mật hoặc giao dịch, việc kế thừa ngầm có thể không phù hợp nếu không được kiểm soát rõ. Nếu muốn bắt buộc khai báo lại, không dùng `@Inherited`.

## 6. @Repeatable — cho phép nhiều annotation cùng kiểu

Trước Java 8, một annotation thường chỉ xuất hiện một lần cho mỗi phần tử. `@Repeatable` cho phép biểu đạt nhiều giá trị cùng kiểu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Repeatable(Tags.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("api")
@Tag("stable")
class Component {}
```

Đây là mã hợp lệ. `Tags` là **container annotation type** của `Tag`, có element `Tag[] value()`. Compiler có thể biểu diễn nhiều `@Tag` thông qua container.

Dùng `getAnnotationsByType(Tag.class)` để lấy **các giá trị cùng kiểu**, kể cả khi chúng nằm trong container:

```java
Tag[] all = Component.class.getAnnotationsByType(Tag.class);
System.out.println(all.length); // 2
```

Đoạn này minh họa API, cần đặt trong method hợp lệ. Trong ví dụ có hai giá trị tương ứng `"api"` và `"stable"`.

### Điều kiện bắt buộc của container

JLS §9.6.3 quy định container `TC` của annotation lặp `T` phải đáp ứng một số điều kiện chặt chẽ:

1. Có element `value()` trả về **`T[]`**, không phải `Object[]`, `String[]` hoặc kiểu mảng bất kỳ.
2. Mọi element khác ngoài `value()` (nếu có) đều **có default**.
3. Retention của container **ít nhất bằng** retention của annotation lặp: `SOURCE ≤ CLASS ≤ RUNTIME`.
4. Các `@Target` phải **tương thích** theo quy tắc JLS; container không được thu hẹp một vị trí lặp hợp lệ. Một số trường hợp `TYPE`, `TYPE_USE` và `TYPE_PARAMETER` có quy tắc tương thích riêng.
5. Nếu annotation lặp có `@Documented`, container **cũng phải có** `@Documented`.
6. Nếu annotation lặp có `@Inherited`, container **cũng phải có** `@Inherited`.

Không nhất thiết mọi metadata phải giống hệt hai bên theo cả chiều ngược lại. Ví dụ JLS cho phép container có `@Documented` trong khi annotation lặp không có; nhưng chiều annotation lặp có `@Documented` mà container thiếu thì **lỗi**.

### Hai ví dụ cấu hình sai

```java
// CỐ Ý SAI: container.value() trả về loại mảng không đúng.
@Repeatable(BadContainer.class)
@interface BadTag {}

@interface BadContainer {
    String[] value();
}
```

```java
// CỐ Ý SAI: @Repeatable annotation được giữ tới RUNTIME,
// nhưng container chỉ giữ tới CLASS.
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(ShortLivedTags.class)
@interface LongLivedTag {}

@Retention(RetentionPolicy.CLASS)
@interface ShortLivedTags {
    LongLivedTag[] value();
}
```

Hai đoạn trên là **ví dụ cố ý không biên dịch**, cho thấy lỗi do điều kiện container, không phải do `@Repeatable` không được hỗ trợ.

### Dùng reflection đúng với repeatable annotation

Sự khác nhau giữa API rất quan trọng:

- `getAnnotation(Tag.class)` tìm một `Tag` **present**; nó **không tự giải nén mọi annotation trong container**.
- `getDeclaredAnnotation(Tag.class)` chỉ xét `Tag` được khai báo trực tiếp theo khái niệm **directly present**.
- `getAnnotationsByType(Tag.class)` trả tất cả `Tag` **associated**, bao gồm các giá trị có mặt gián tiếp trong container và quy tắc kế thừa khi thích hợp.
- `getDeclaredAnnotationsByType(Tag.class)` đọc trực tiếp hoặc gián tiếp qua container **tại phần tử hiện tại**, không tìm superclass.

Với một annotation lặp, nếu API cần danh sách, ưu tiên `getAnnotationsByType()` hoặc `getDeclaredAnnotationsByType()` thay vì trông đợi `getAnnotation()` trả về nhiều phần tử.

## 7. Kết hợp @Documented + @Inherited + @Repeatable đúng cách

Khi annotation được lặp, lại phải **xuất hiện trong Javadoc** và **được tìm qua superclass**, khai báo metadata phù hợp trên cả annotation lặp và container.

Đây là tình huống rất dễ làm sai: viết `@Inherited` và `@Documented` trên annotation lặp nhưng quên hai meta-annotation tương ứng ở container sẽ gây lỗi biên dịch.

### Ví dụ Java 17 hoàn chỉnh và đã chạy kiểm chứng

Tạo đúng một tệp `PolicyDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

/**
 * Một nhãn mô tả phạm vi áp dụng của dịch vụ.
 *
 * @since 1.0
 */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    /** @return tên nhãn do ứng dụng cung cấp */
    String value();
}

/** Container cho nhiều nhãn trên cùng một class. */
@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    /** @return các nhãn đang gắn trên class */
    Label[] value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {}

@Label("audit")
@Label("metrics")
class BaseService {
    @Trace
    public void run() {}
}

class ChildService extends BaseService {
    @Override
    public void run() {}
}

@Label("local")
class LocalService extends BaseService {}

public class PolicyDemo {
    private static String labels(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Label.class))
                .map(Label::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base=" + labels(BaseService.class));
        System.out.println("child=" + labels(ChildService.class));
        System.out.println("child-declared="
                + ChildService.class.getDeclaredAnnotationsByType(Label.class).length);
        System.out.println("local=" + labels(LocalService.class));

        Method overriding = ChildService.class.getDeclaredMethod("run");
        System.out.println("override-trace="
                + overriding.isAnnotationPresent(Trace.class));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 PolicyDemo.java
java PolicyDemo
```

Stdout **chính xác**, đã được đối chiếu bằng `javac` và `java`:

```text
base=audit,metrics
child=audit,metrics
child-declared=0
local=local
override-trace=false
```

**Diễn giải từng dòng:**

1. `base=audit,metrics`: `BaseService` khai báo trực tiếp hai `@Label`. API `getAnnotationsByType(Label.class)` mở các giá trị trong container.
2. `child=audit,metrics`: `ChildService` không khai báo `@Label` riêng. Vì cả repeated type và container tuân theo quy tắc `@Inherited`, phép tra theo kiểu `getAnnotationsByType` có thể lấy từ superclass.
3. `child-declared=0`: `ChildService` **không trực tiếp** khai báo nhãn nào; `getDeclaredAnnotationsByType` không tra lên cha.
4. `local=local`: `LocalService` khai báo một `@Label("local")` của chính nó; kết quả tra theo type là nhãn của con, **không tự cộng dồn** với hai nhãn `audit` và `metrics` của cha.
5. `override-trace=false`: method `ChildService.run()` override method ở `BaseService`, nhưng không tự mang annotation `@Trace` của method cha. `@Inherited` không phải cơ chế sao chép method annotation.

Mã này dùng `@Documented` để hỗ trợ tài liệu API. Chương trình không gọi `javadoc`, nên không có dòng output riêng nào do `@Documented` tạo ra.

### Sinh thử tài liệu Javadoc

Nếu muốn xem Javadoc cho annotation type và các class được gắn nhãn:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs PolicyDemo.java
```

Cờ `-private` giúp hiển thị cả những kiểu package-private trong demo. Phần hiển thị thực tế phụ thuộc công cụ Javadoc và tùy chọn, nhưng `@Documented` thể hiện chủ đích công khai annotation tại nơi sử dụng.

Lệnh `javadoc` có thể phát warning về tài liệu chưa đầy đủ của các class minh họa; đó là thông báo công cụ, **không** nằm trong stdout đã liệt kê của `java PolicyDemo`.

## 8. Các bộ lựa chọn điển hình theo mục đích

Đây là **mẫu ra quyết định**, không phải công thức buộc mọi dự án phải dùng đúng cấu hình.

| Tình huống | Target | Retention | Documented | Inherited | Repeatable |
| --- | --- | --- | --- | --- | --- |
| Marker để annotation processor sinh adapter cho class | `TYPE` | `SOURCE` | Thường không | Thường không | Chỉ nếu thực sự có nhiều cấu hình |
| Route annotation cho method do framework quét runtime | `METHOD` | `RUNTIME` | Có thể có cho API công khai | Không hữu ích cho method | Thường không, trừ framework hỗ trợ đa route |
| Cấu hình class runtime được dùng chung cho subclass | `TYPE` | `RUNTIME` | Tùy ý nghĩa công khai | Có nếu cần kế thừa ngầm | Chỉ nếu cần nhiều cấu hình |
| Nhãn phân loại class cho tài liệu và tooling | `TYPE` | `RUNTIME` hoặc `CLASS` tùy consumer | Thường có | Tùy chính sách | Có thể có |
| Nullability/type checker cho các type-use | `TYPE_USE` | `CLASS` hoặc `SOURCE` tùy checker | Theo API công khai | Không phải kế thừa class metadata | Theo ngữ nghĩa của checker |
| Metadata có nhiều điều kiện độc lập trên class | `TYPE` | Tùy thời điểm đọc | Nếu công khai | Nếu cấu hình được kế thừa | Có và phải thiết kế container |

**Quy tắc ra quyết định:** Target xuất phát từ **vị trí**, retention từ **giai đoạn consumer**, documented từ **nhu cầu API documentation**, inherited từ **quy tắc subclass**, repeatable từ **số lượng giá trị cần gắn**. Không chọn tất cả chỉ vì framework hiện có hỗ trợ các meta-annotation này.

## 9. Những xung đột thiết kế cần giải quyết bằng hợp đồng rõ ràng

### A. Kế thừa metadata hay buộc subtype định nghĩa lại?

Nếu `@ServicePolicy` ảnh hưởng tới phạm vi bảo mật hoặc giao dịch, một subclass mới có nên tự động nhận chính sách lớp cha? `@Inherited` có thể khiến các công cụ tra cứu `Class.getAnnotation()` tìm thấy cấu hình cũ.

Nếu subtype phải được review chính sách riêng, đừng tự bật `@Inherited`. Có thể yêu cầu khai báo trực tiếp và dùng `getDeclaredAnnotation()` trong validator.

### B. Nhiều annotation hay một annotation có mảng?

Hai cách tiếp cận:

```java
// Cách 1: annotation lặp.
@Tag("audit")
@Tag("metrics")
class ExampleA {}

// Cách 2: annotation có mảng.
// Giả sử @TagList có String[] value().
@TagList({"audit", "metrics"})
class ExampleB {}
```

Đây là **đoạn minh họa** có sử dụng `Tag` hoặc `TagList` được khai báo riêng. Với repeatable, mỗi nhãn là một annotation độc lập có thể có nhiều element; với một annotation chứa mảng, consumer có một danh sách tập trung.

Nên cân nhắc:

- Có cần **nhiều cấu hình có cấu trúc phức tạp**, mỗi cấu hình mang các field riêng? Repeatable thường tự nhiên.
- Chỉ có một danh sách tên đơn giản và rõ ràng? Annotation có `String[]` có thể dễ dùng.
- Có cần đồng bộ retention, target, documented, inherited của cả repeated type và container? Repeatable tạo thêm trách nhiệm tương thích.
- Hệ thống có dùng `getAnnotationsByType()` đúng cách không? Nếu chỉ dùng `getAnnotation()` có thể bỏ qua phần tử nằm trong container.
- Cần quy tắc về thứ tự, trùng lặp, kế thừa và ghi đè như thế nào? Hãy ghi rõ trong Javadoc và test.

### C. Public API annotation hay metadata nội bộ?

Nếu người dùng thư viện cần biết `@StableApi`, `@Documented` là lựa chọn hợp lý. Nếu annotation chỉ kích hoạt code generator nội bộ, việc công khai annotation trên từng trang Javadoc có thể làm nhiễu hợp đồng API.

### D. Retention RUNTIME có thật sự cần thiết?

Không bắt buộc. Một processor compile-time chỉ cần `SOURCE` vẫn có thể đọc annotation. Một bytecode analyzer có thể đọc metadata `CLASS` bằng class-file tooling. Chỉ dùng `RUNTIME` nếu consumer cần reflection/runtime access.

### E. Hệ thống có đang tự diễn giải meta-annotation?

Java reflection chuẩn **không tự biến** một annotation được gắn lên annotation type thành annotation có mặt trực tiếp trên tất cả class dùng nó.

```java
// Với @Target phù hợp và RUNTIME retention:
@PolicyTag
@interface AuditService {}

@AuditService
class Server {}
```

Đây là **khai báo minh họa** cần kiểu `PolicyTag`, `AuditService` thích hợp. Nếu chỉ `AuditService` được gắn trên `Server`, Java reflection không tự cho `Server.class.getAnnotation(PolicyTag.class)` khác `null`. Framework có thể duyệt sâu meta-annotation, nhưng đó là **quy tắc bổ sung của framework**, không phải tác dụng mặc định của `@Documented`, `@Inherited` hay `@Repeatable`.

## 10. Kiểm tra compile-time và runtime cho một annotation type mới

Trước khi công bố annotation, nên có các dạng test sau:

**Test compile-time:**

- Gắn annotation ở những vị trí `@Target` cho phép; biên dịch phải thành công.
- Gắn vào một vị trí sai như field khi chỉ cho `METHOD`; compiler phải từ chối.
- Nếu dùng `@Repeatable`, thử ít nhất hai annotation cùng kiểu; kiểm tra điều kiện container và các meta-annotation bắt buộc.
- Thử một trường hợp **container sai** (khác `value() T[]`, retention quá ngắn hoặc thiếu `@Inherited`/`@Documented` khi repeated type cần) và kiểm tra compiler báo lỗi.

**Test runtime:**

- Reflection tìm được annotation có `RUNTIME` ở đúng vị trí.
- Annotation `SOURCE` hoặc `CLASS` không bị nhầm là annotation reflection runtime.
- Với `@Inherited`, kiểm tra class con không khai báo, class con có khai báo trực tiếp và trường hợp interface.
- Với repeatable, kiểm tra `getAnnotationsByType()` và `getDeclaredAnnotationsByType()`, không chỉ `getAnnotation()`.
- Với method override, xác nhận không tự kế thừa metadata method theo cách không có trong đặc tả.

**Test tài liệu:**

- Tạo Javadoc và xem annotation công khai có được hiển thị phù hợp.
- Mô tả mỗi annotation element và default, đặc biệt quy tắc kế thừa, override và nhiều giá trị.
- Đảm bảo document không hứa hành vi nghiệp vụ mà consumer chưa thực hiện.

## 11. Sai lầm thường gặp

**1. Bật RUNTIME cho mọi annotation.** Retention nên theo nhu cầu consumer, không theo thói quen.

**2. Bỏ Target để “dùng linh hoạt”.** Có thể khiến annotation được đặt ngoài những khai báo consumer thực sự hiểu. Target hẹp giúp compiler kiểm tra sớm.

**3. Dùng @Inherited trên annotation method và chờ override kế thừa.** Cơ chế chuẩn liên quan tra cứu annotation trên **class qua superclass**.

**4. Dùng @Inherited rồi chờ implements interface truyền annotation.** Interface không nằm trong đường tra cứu tự động của `@Inherited`.

**5. Nghĩ @Documented tương đương Javadoc đầy đủ.** Nó không tạo phần giải thích annotation type/element thay người viết.

**6. Nghĩ @Documented làm annotation đọc được lúc chạy.** Việc đó thuộc `@Retention(RUNTIME)`.

**7. Dùng @Repeatable mà container.value() không phải T[].** Đây là lỗi biên dịch do ràng buộc container.

**8. Quên retention/target/@Inherited/@Documented trên container.** JLS yêu cầu container đáp ứng những điều kiện tương thích tương ứng.

**9. Chỉ dùng getAnnotation với annotation lặp.** Nên dùng `getAnnotationsByType()` để lấy cả các giá trị chứa gián tiếp trong container.

**10. Mong annotation lặp ở class con tự cộng dồn toàn bộ class cha.** Java có quy tắc *associated* và kế thừa cụ thể; khi con trực tiếp khai báo annotation cùng kiểu, kết quả không tự merge mọi giá trị của cha.

**11. Xem annotation như logic runtime.** Marker `@Audit` không tự phát log; consumer phải thực hiện hành vi.

**12. Quên kiểm tra contract khi sửa meta-annotation của thư viện.** Đổi `@Target` có thể làm client trước đây hợp lệ không biên dịch; đổi retention có thể làm reflection mất dữ liệu; thêm `@Inherited` có thể thay đổi hành vi subclass; đổi repeated/container có thể phá code đọc annotation.

## 12. Checklist thiết kế trước khi merge

| Câu hỏi | Kiểm chứng mong đợi |
| --- | --- |
| Annotation dành cho consumer nào? | Javadoc ghi rõ processor, runtime framework hoặc công cụ |
| Target đã chính xác chưa? | Chỉ cho phép những vị trí consumer hiểu |
| Retention có đủ nhưng không thừa? | SOURCE/CLASS/RUNTIME theo vòng đời |
| Cần @Documented không? | Hợp đồng API thực sự cần hiển thị annotation |
| Có kế thừa cấu hình không? | Class hierarchy và trường hợp khai báo trực tiếp đã được test |
| Có nhiều giá trị cùng loại không? | Repeatable hoặc mảng theo ngữ nghĩa phù hợp |
| Container repeatable có hợp lệ không? | value() T[], defaults, retention, target, documented, inherited |
| Đọc repeatable đúng API chưa? | getAnnotationsByType/getDeclaredAnnotationsByType |
| Có xung đột subclass không? | Chính sách override/không merge được nêu rõ |
| Mỗi element có tài liệu/default phù hợp? | Giá trị và ràng buộc khớp consumer |
| Có test với javac, java và javadoc? | Tùy phase sử dụng, kết quả rõ ràng |
| Đổi meta-annotation ảnh hưởng client không? | Review compatibility cả compile-time và runtime |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Annotation chỉ dùng trong annotation processor trên class cần mặc định `RUNTIME` không?

**Đáp án:** Không. `@Retention(SOURCE)` thường là đủ; `@Target(TYPE)` rõ phạm vi dùng.

**Câu 2.** `@Documented` và `@Retention(RUNTIME)` có làm cùng việc không?

**Đáp án:** Không. Một cái ảnh hưởng hiển thị annotation trong tài liệu API, một cái quyết định metadata có sẵn cho reflection lúc chạy.

**Câu 3.** Class `Child extends Base` không khai báo annotation `@Policy`, trong khi `Base` có và kiểu `Policy` có `@Inherited`. Hai hàm nào có thể trả kết quả khác nhau?

**Đáp án:** `Child.class.getAnnotation(Policy.class)` có thể nhận từ superclass, còn `getDeclaredAnnotation(Policy.class)` là `null`, giả sử retention là `RUNTIME`.

**Câu 4.** `@Repeatable(Tags.class)` với `Tags.value()` kiểu `String[]` có hợp lệ cho repeated type `Tag` không?

**Đáp án:** Không. Container phải có `Tag[] value()`.

**Câu 5.** Repeated annotation được đánh dấu `@Inherited` và `@Documented`; container chỉ có retention và target. Có đủ chưa?

**Đáp án:** Chưa. Container phải được đánh dấu `@Inherited` và `@Documented` tương ứng theo JLS.

**Câu 6.** Một method override có tự nhận annotation kiểu `@Inherited` của method cha không?

**Đáp án:** Không. Đây không phải cách `@Inherited` hoạt động.

**Câu 7.** `getAnnotationsByType(Label.class)` trên lớp con ghi trực tiếp `@Label("local")` có mặc định trả cả các nhãn của cha không?

**Đáp án:** Không. Với mô hình repeatable và kế thừa chuẩn, annotation associated trên con không tự cộng dồn danh sách từ superclass.

**Câu 8.** Khi thiết kế một annotation `@Tracked` có nhiều nhãn, lúc nào nên dùng repeatable thay cho mảng?

**Đáp án:** Khi mỗi lần áp dụng là một cấu hình độc lập hoặc có nhiều phần tử riêng và công cụ muốn xử lý từng lần gắn. Nếu chỉ là danh sách chuỗi đơn giản, `String[]` có thể thuận tiện hơn.

## Tài liệu chính thức

- [Java Language Specification 17, §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3).
- [JLS 17, §9.6.4.1 — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1).
- [JLS 17, §9.6.4.2 — @Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2).
- [JLS 17, §9.6.4.3 — @Inherited](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3).
- [Java SE 17 API — Documented](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Documented.html).
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).

**Kết luận:** Thiết kế annotation có chủ đích nghĩa là **cho phép đúng vị trí, giữ metadata đúng vòng đời, công bố đúng hợp đồng, kế thừa đúng phạm vi và chỉ lặp khi thật sự cần**. Với `@Repeatable`, đừng quên container và các quy tắc tương thích. Với `@Inherited`, chỉ dựa vào hành vi chuẩn qua superclass khi đó đúng là hợp đồng API mong muốn.
