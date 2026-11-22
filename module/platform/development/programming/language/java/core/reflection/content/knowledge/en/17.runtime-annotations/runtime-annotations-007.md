# Repeatable annotation và container annotation trong Java Reflection

## 1. Vì sao một annotation có thể xuất hiện nhiều lần?

Thông thường, một annotation được gắn một lần lên một thành phần Java. Nhưng có những tình huống cần **nhiều cấu hình cùng loại** trên một class, method, field hoặc một vị trí cho phép khác: nhiều route cho một endpoint, nhiều vai trò truy cập, nhiều lịch chạy, nhiều điều kiện kiểm thử.

Từ Java 8, Java hỗ trợ **repeatable annotation** thông qua meta-annotation `@Repeatable`. Ví dụ:

```java
@Tag("stable")
@Tag("audited")
class OrderService { }
```

Muốn dùng cú pháp này, `Tag` phải được khai báo là repeatable và liên kết với một **container annotation** có phần tử `value()` trả về mảng `Tag[]`. Compiler sẽ xử lý nhiều `@Tag` cùng vị trí theo cơ chế container. Khi đọc metadata bằng Reflection, lập trình viên cần hiểu sự khác nhau giữa **annotation khai báo trong source**, **container được lưu trong class file** và **các API đọc một/multiple annotation**.

Các mục tiêu quan trọng của bài:

1. Khai báo đúng `@Repeatable(Container.class)` và loại container tương ứng.
2. Hiểu việc compiler gom nhiều annotation cùng kiểu vào container.
3. Dùng `getAnnotationsByType` và `getDeclaredAnnotationsByType` để truy vấn **đầy đủ** các annotation lặp lại.
4. Phân biệt `getAnnotation`, `getAnnotations`, `getDeclaredAnnotation`, container annotation và repeatable element.
5. Hiểu `@Retention`, `@Target`, `@Inherited`, thứ tự phần tử và trường hợp không lặp.
6. Tránh các sai sót thường gặp trong framework dùng runtime Reflection.

## 2. Ba thành phần tạo nên repeatable annotation

### 2.1. Annotation lặp được: `@Tag`

Annotation chính mô tả một đơn vị cấu hình. Muốn đọc được ở runtime, dùng `@Retention(RetentionPolicy.RUNTIME)`; muốn cho phép áp dụng lên class và method, dùng `@Target` tương ứng.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}
```

Điểm quyết định là `@Repeatable(Tags.class)`: nó khai báo **`Tags` là kiểu chứa các phần tử `Tag`**. `@Repeatable` là meta-annotation áp dụng trên **khai báo annotation type**, không phải annotation dùng trực tiếp lên `OrderService`.

### 2.2. Container annotation: `@Tags`

Container chứa một mảng annotation chính:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}
```

`value()` phải trả về **`Tag[]` đúng kiểu**. Không thể thay nó bằng `String[]`, `List<Tag>` hay `Object[]`. Phần tử này là cầu nối mà compiler và API Reflection dùng để đóng gói và giải nén các bản `@Tag`.

Một container có thể có các phần tử khác, nhưng những phần tử bổ sung phải có **default value** phù hợp với quy tắc khai báo container của Java. Thiết kế đơn giản, ít bất ngờ nhất là chỉ có `Tag[] value();`.

Chú ý `@Retention` và `@Target` được áp dụng lên **cả hai khai báo**. Container phải đáp ứng các ràng buộc meta-annotation tương thích do Java quy định. Để đọc annotation lặp tại runtime, giữ **cả repeatable type và container type ở `RUNTIME`**. Nếu repeatable type là `@Inherited`, container cũng phải được khai báo `@Inherited`. Nếu repeatable type dùng `@Documented`, container cũng cần `@Documented`.

### 2.3. Cú pháp sử dụng

Sau khi khai báo đúng, chương trình có thể gắn nhiều `@Tag` cùng vị trí:

```java
@Tag("stable")
@Tag("audited")
class OrderService {
    @Tag("read")
    @Tag("cache")
    public void load() { }
}
```

Hai lần gắn `@Tag` là **hai giá trị annotation riêng**, theo thứ tự được khai báo. Source code vẫn trực quan: không cần tự viết container mỗi lần có nhiều bản.

Cách viết container tường minh cũng hợp lệ:

```java
@Tags({
    @Tag("stable"),
    @Tag("audited")
})
class ExplicitOrderService { }
```

Khi dùng `getAnnotationsByType(Tag.class)`, hai cách thể hiện này thường có kết quả như nhau. Tuy nhiên code dùng `getAnnotation(Tag.class)` hoặc duyệt `getDeclaredAnnotations()` có thể nhận kết quả rất khác so với trực giác nếu không hiểu container.

## 3. Compiler làm gì khi annotation được lặp?

Khi compiler gặp:

```java
@Tag("stable")
@Tag("audited")
class OrderService { }
```

Nó xử lý hai annotation `@Tag` theo cơ chế container tương ứng với cấu trúc ý tưởng:

```java
@Tags({
    @Tag("stable"),
    @Tag("audited")
})
class OrderService { }
```

Đây là **mô hình tương đương về cách lưu metadata**, không phải bước chỉnh source file hay yêu cầu lập trình viên gọi constructor container. Trong class file, nhiều `@Tag` cùng vị trí được biểu diễn thông qua `@Tags` theo quy tắc Java.

Do vậy có hai mức nhìn:

| Góc nhìn | Nhìn thấy |
|---|---|
| Source Java | Hai `@Tag` đặt liên tiếp |
| Metadata được chứa | Một container `@Tags` có phần tử `Tag[] value()` gồm hai giá trị |
| `getDeclaredAnnotation(Tags.class)` | Đọc được container nếu nó trực tiếp hiện diện |
| `getDeclaredAnnotationsByType(Tag.class)` | API giải nén và trả lại cả hai `@Tag` |
| `getDeclaredAnnotation(Tag.class)` | Có thể trả `null` vì `@Tag` không trực tiếp hiện diện, chỉ hiện diện gián tiếp qua container |

Cách nhìn này giải thích vì sao mã cũ dùng `getAnnotation(Tag.class)` có thể bắt đầu **không tìm thấy annotation** sau khi annotation đó được làm repeatable và được sử dụng nhiều lần trên cùng một thành phần.

Không nên dựa vào việc tự parse tên annotation trong bytecode khi `AnnotatedElement` đã có các API chuẩn để lấy các giá trị gốc.

## 4. Những quy tắc khai báo container phải tuân thủ

Java không chấp nhận tùy ý một cặp annotation làm repeatable/container. Một số quy tắc then chốt:

| Ràng buộc | Ví dụ phù hợp | Vì sao cần |
|---|---|---|
| Container là một annotation type | `@interface Tags` | Compiler phải nhận diện được kiểu chứa |
| Có phần tử `value()` trả đúng mảng kiểu repeatable | `Tag[] value();` | Chứa các instance `@Tag` |
| Các phần tử container khác (nếu có) đều có default value | `String group() default "";` | Cho phép compiler tạo container hợp lệ khi gặp nhiều `@Tag` |
| Retention của container không ngắn hơn retention của kiểu được lặp | `RUNTIME` / `RUNTIME` | Không làm mất thông tin cần lưu |
| Target của container tương thích với nơi kiểu được lặp có thể xuất hiện | Cùng `TYPE`, `METHOD` trong ví dụ | Container phải hợp lệ tại vị trí compiler đóng gói |
| Nếu repeatable type có `@Inherited`, container cũng có `@Inherited` | Cả hai được đánh dấu | Bảo toàn hành vi kế thừa được hỗ trợ |
| Nếu repeatable type có `@Documented`, container cũng có `@Documented` | Cả hai được đánh dấu | Bảo đảm hợp đồng hiển thị trong tài liệu |

Với bài học cơ bản, **đặt retention và target giống nhau trên cặp annotation** là phương án dễ đọc và tránh sai lệch. Quy tắc ngôn ngữ thực tế cho phép một số quan hệ target không hoàn toàn giống nhau nhưng phải thỏa JLS; đừng suy rằng mọi tập target bất kỳ đều hợp lệ.

### Ví dụ không hợp lệ: sai kiểu mảng

```java
// Sai: container không chứa Tag[] ở value().
// @Repeatable(BadTags.class)
// @interface Tag { String value(); }
// @interface BadTags { String[] value(); }
```

### Ví dụ không hợp lệ: không đủ runtime retention

```java
// Không phù hợp để đọc các giá trị bằng runtime Reflection:
// @Retention(RetentionPolicy.RUNTIME)
// @Repeatable(BadTags.class)
// @interface Tag { String value(); }
//
// @Retention(RetentionPolicy.CLASS)
// @interface BadTags { Tag[] value(); }
```

Hai khối trên chỉ là **phản ví dụ chú thích**, không đưa vào file chương trình chạy. Tùy loại vi phạm, compiler sẽ báo lỗi khai báo repeatable/container.

## 5. Retention của repeatable annotation và container

Khi muốn dùng runtime Reflection, cả repeatable annotation lẫn container phải có retention thích hợp (`RUNTIME` trong các ví dụ này). `@Repeatable` chỉ cho phép **lặp**, không tự đổi retention. Nếu thiếu `@Retention` thì mặc định là `CLASS`, và các API runtime không thấy những annotation đó. Xem bài retention để phân biệt xử lý annotation lúc compile và lúc chạy.

## 6. API Reflection: đọc một annotation hay đọc nhiều annotation?

Các kiểu `Class`, `Method`, `Field`, `Constructor`, `Parameter` và một số thành phần Reflection khác triển khai giao diện `java.lang.reflect.AnnotatedElement`. Các API tiêu biểu:

| API | Loại annotation được xét | Có giải nén container không? | Kế thừa đối với class |
|---|---|---|---|
| `getAnnotation(A.class)` | Annotation *present* kiểu `A` | **Không** tự giải nén `A` từ container | Có theo quy tắc `@Inherited` và khái niệm *present* |
| `getDeclaredAnnotation(A.class)` | Annotation **directly present** kiểu `A` | **Không** | Không |
| `getAnnotationsByType(A.class)` | Annotation **associated** kiểu `A` | **Có** nếu `A` repeatable | Có thể có theo `@Inherited` |
| `getDeclaredAnnotationsByType(A.class)` | Annotation trực tiếp hoặc gián tiếp qua container | **Có** | Không |
| `getAnnotations()` | Các annotation *present* dạng mảng | **Không** tự trải phẳng repeated elements | Có thể có |
| `getDeclaredAnnotations()` | Các annotation trực tiếp dạng mảng | **Không** tự trải phẳng repeated elements | Không |
| `isAnnotationPresent(A.class)` | Tương đương `getAnnotation(A.class) != null` | **Không** | Theo `getAnnotation` |

Bảng dùng các thuật ngữ trong Javadoc `AnnotatedElement` Java 17.

**Quy tắc thực hành:** Nếu annotation type được khai báo `@Repeatable` và mục tiêu là thu thập **tất cả các giá trị**, hãy gọi:

```java
Tag[] tags = element.getAnnotationsByType(Tag.class);
```

hoặc khi chỉ muốn các annotation do chính element khai báo:

```java
Tag[] localTags = element.getDeclaredAnnotationsByType(Tag.class);
```

Ở đây `element` có kiểu `AnnotatedElement` phù hợp. Hai phương thức đều trả **mảng**; không có annotation tương ứng thì mảng **rỗng**, không phải `null`. Khác biệt chính là phương thức không có `Declared` có thể xét kế thừa trong tình huống class + `@Inherited`.

### Vì sao `getAnnotation(Tag.class)` có thể trả `null`?

Với **hai** `@Tag` đặt liên tiếp, compiler thường lưu một `@Tags` container. Khi đó `Tag` chỉ **indirectly present** chứ không **directly present** trên element. `getAnnotation(Tag.class)` không “nhìn xuyên” container, nên trên chính element đó có thể trả `null`, dù `getAnnotationsByType(Tag.class)` vẫn trả hai phần tử.

Ngược lại, với **một** `@Tag("one")` đơn lẻ, `Tag` thường được lưu trực tiếp và `getAnnotation(Tag.class)` có thể trả annotation đó. Đây là khác biệt quan trọng giữa **một lần** và **nhiều lần** gắn cùng annotation type.

## 7. Vì sao kết quả `getAnnotation` khác `getAnnotationsByType`?

Trong thuật ngữ `AnnotatedElement`, `@Tag` đơn lẻ có thể **directly present**, còn nhiều `@Tag` được gói trong một `@Tags` container khiến chúng **indirectly present**. `getAnnotation(Tag.class)` xét *present*, không tự trải phẳng container; `getAnnotationsByType(Tag.class)` xét *associated*, bao gồm annotation trực tiếp, gián tiếp và fallback kế thừa hợp lệ.

Thử ba trạng thái: không có tag, chỉ một `@Tag`, và hai `@Tag`. Với hai tag, `getAnnotation(Tag.class)` có thể `null` dù `getAnnotationsByType(Tag.class).length == 2`. Khác biệt giữa hai biến thể `ByType` và cách xử lý `@Inherited` được minh họa riêng trong bài kế tiếp.

## 8. Container annotation khi truy vấn trực tiếp

Container vẫn là một annotation type độc lập. Có thể truy cập nó bằng Reflection:

```java
Tags container = OrderService.class.getDeclaredAnnotation(Tags.class);

if (container != null) {
    for (Tag tag : container.value()) {
        System.out.println(tag.value());
    }
}
```

Đoạn trên giả định khai báo `OrderService` có hai `@Tag` và các annotation type tương ứng, không phải chương trình có `main` độc lập.

Đây là cách giải nén thủ công. Trong phần lớn trường hợp, `getDeclaredAnnotationsByType(Tag.class)` hoặc `getAnnotationsByType(Tag.class)` ngắn gọn và đúng hợp đồng hơn. Ưu điểm của API by-type:

- Hoạt động cả khi chỉ có **một `@Tag` trực tiếp**, không tồn tại container.
- Hoạt động khi có **nhiều `@Tag` gián tiếp qua container**.
- Hoạt động khi người dùng khai báo **`@Tags({ ... })` tường minh**.
- Tuân thủ cách sắp xếp các annotation repeatable mà `AnnotatedElement` quy định.
- Với `getAnnotationsByType`, xét kế thừa đúng quy tắc cho class được chú thích bằng `@Inherited`.

**Đừng tự assume container luôn có mặt.** Nếu element chỉ có một annotation gốc, việc đọc `getDeclaredAnnotation(Tags.class)` thường trả `null`. Nên xem container là cơ chế lưu giữ, không phải API duy nhất để truy vấn mọi trường hợp.

## 9. Thứ tự các repeatable annotations có ý nghĩa

Với:

```java
@Tag("first")
@Tag("second")
@Tag("third")
class Example { }
```

`getDeclaredAnnotationsByType(Tag.class)` trả các annotation theo thứ tự `first`, `second`, `third` tương ứng. Khi đọc từ container, thứ tự dựa vào thứ tự phần tử trong `value()`. Java `AnnotatedElement` quy định thứ tự như thể các phần tử gián tiếp được đặt ở vị trí của container tương ứng.

Điều này quan trọng nếu annotation diễn tả một **pipeline có thứ tự**, danh sách bộ lọc, các rule đánh giá theo thứ tự hoặc các điểm cấu hình lặp. Tuy nhiên, thứ tự annotation không mặc nhiên biến thành quy tắc thứ tự nghiệp vụ: framework cần tuyên bố rõ **có dùng thứ tự nguồn hay không**.

Nếu thứ tự làm thay đổi logic, hãy kiểm thử nó. Không tự sắp xếp các `@Tag` theo alphabet trừ khi đặc tả framework yêu cầu, bởi như vậy có thể thay đổi ý nghĩa của cấu hình được khai báo.

## 10. `@Inherited` kết hợp với repeatable annotation

Để một `@Tag` repeatable được kế thừa khi tra cứu trên **class**, đánh dấu `@Inherited` trên **cả `Tag` và container `Tags`**, cùng retention/target hợp lệ. Với `@Tag("a") @Tag("b")` trên `Parent` và `Child extends Parent` không có tag riêng, `Child.class.getAnnotationsByType(Tag.class)` trả `[a,b]`, còn `getDeclaredAnnotationsByType(Tag.class)` trả mảng rỗng.

```java
@Inherited @Repeatable(Tags.class) @Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tag { String value(); }

@Inherited @Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags { Tag[] value(); }
```

Nếu `Child` khai báo `@Tag("local")`, `getAnnotationsByType(Tag.class)` ưu tiên `[local]`: cơ chế inheritance là fallback, không tự cộng mọi giá trị từ superclass. Nếu muốn merge nhiều tầng hoặc quét interface/method override, framework phải tự làm. Ví dụ chạy ở mục 13 chứng minh các nhánh này.

## 11. Repeatable annotation có thể đặt ở những phần tử nào?

Vị trí hợp lệ vẫn do `@Target` của cả annotation và container quyết định: `TYPE` (class), `METHOD` (method), `FIELD`, `CONSTRUCTOR`, `PARAMETER` hoặc `TYPE_USE`. Để đọc lặp trên method, lấy đúng đối tượng `Method` rồi gọi `method.getDeclaredAnnotationsByType(Tag.class)`; với type-use, lấy đúng `AnnotatedType` trước khi gọi API.

```java
Method method = SomeClass.class.getDeclaredMethod("load");
Tag[] tags = method.getDeclaredAnnotationsByType(Tag.class);
```

Đây là fragment cần class/phương thức và import `Method` hợp lệ. `@Inherited` không làm annotation trên method override tự di truyền. AnnotatedElement và vị trí TYPE_USE được giải thích kỹ ở bài đầu của chương.

## 12. Cách thiết kế API xử lý repeatable annotation

Trong một annotation scanner hoặc framework, nên thực hiện theo thứ tự:

1. **Làm rõ element:** Class, method, field, constructor, parameter hay type use? Chọn `AnnotatedElement` tương ứng.
2. **Kiểm tra retention:** Annotation cần đọc ở runtime phải có `RUNTIME` phù hợp.
3. **Dùng by-type API:** `getDeclaredAnnotationsByType` để lấy annotation của chính declaration; `getAnnotationsByType` khi chủ đích muốn xét inheritance trên class.
4. **Không phụ thuộc vào container là null/non-null:** Một annotation trực tiếp và nhiều annotation gián tiếp có cách lưu khác nhau.
5. **Giữ nguyên thứ tự:** Nếu cấu hình dùng thứ tự, xử lý theo mảng do API trả về.
6. **Định nghĩa quy tắc trùng lặp:** Hai tag có cùng giá trị có được chấp nhận không? Java cho phép các annotation repeatable có nội dung trùng; framework phải quy định có gộp hay báo lỗi.
7. **Không nhầm @Inherited với merge:** Nếu muốn lấy cả lớp con lẫn lớp cha, tự duyệt hierarchy và nêu chính sách.
8. **Phân biệt annotation gốc và container:** Khi hỗ trợ metadata introspection, có thể cần khảo sát container riêng, nhưng xử lý business annotations nên ưu tiên by-type API.
9. **Cẩn thận với meta-annotations:** Nếu muốn scanner quét annotation trên chính một annotation type, cần logic riêng (ví dụ xử lý stereotype/composed annotations); `@Repeatable` tự nó không cung cấp cơ chế “recursive meta-annotation scanning”.

Một utility tối giản dùng được với nhiều kiểu element:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.AnnotatedElement;

public final class AnnotationReaders {
    private AnnotationReaders() { }

    public static <A extends Annotation> A[] locallyDeclared(
            AnnotatedElement element, Class<A> annotationType) {
        return element.getDeclaredAnnotationsByType(annotationType);
    }
}
```

Đây là lớp tiện ích độc lập có thể biên dịch, nhưng không có `main` riêng. Nó cố ý dùng `Declared` để tránh suy diễn annotation từ superclass. Khi muốn inheritance của `Class` có `@Inherited`, có thể chọn `getAnnotationsByType`, nhưng nên đặt tên helper khác để contract rõ ràng.

## 13. Chương trình Java 17+ chạy được: container, method và inheritance

Ví dụ chạy độc lập này chứng minh:

- Compiler đóng gói hai `@Tag` vào `@Tags`.
- `getDeclaredAnnotation(Tag.class)` có thể trả `null` dù có hai tag.
- `getDeclaredAnnotationsByType`/`getAnnotationsByType` giải nén được cả hai giá trị.
- `@Inherited` cho phép class con đọc tag từ superclass nếu class con không có tag riêng.
- Class con có tag riêng sẽ **không** tự cộng dồn tag từ superclass.
- Container khai báo tường minh cũng được by-type API xử lý.
- Truy vấn annotation trên method làm việc tương tự mà không cần giả định inheritance của method.

### 13.1. Mã nguồn

Lưu toàn bộ nội dung sau vào **`RepeatableDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class RepeatableDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Inherited
    @Repeatable(Tags.class)
    @interface Tag { String value(); }

    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    @Inherited
    @interface Tags { Tag[] value(); }

    @Tag("stable") @Tag("audited")
    static class Base {
        @Tag("read") @Tag("cache")
        public void run() { }
    }

    static class Child extends Base { }

    @Tag("local")
    static class Local extends Base { }

    @Tags({@Tag("manual-a"), @Tag("manual-b")})
    static class Explicit { }

    static String values(Tag[] tags) {
        return Arrays.stream(tags).map(Tag::value)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base byType: "
                + values(Base.class.getAnnotationsByType(Tag.class)));
        System.out.println("base direct single: "
                + (Base.class.getDeclaredAnnotation(Tag.class) != null));
        System.out.println("base container: "
                + (Base.class.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("base declared count: "
                + Base.class.getDeclaredAnnotations().length);
        System.out.println("child byType: "
                + values(Child.class.getAnnotationsByType(Tag.class)));
        System.out.println("child declared byType: "
                + Child.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("local byType: "
                + values(Local.class.getAnnotationsByType(Tag.class)));
        System.out.println("explicit byType: "
                + values(Explicit.class.getAnnotationsByType(Tag.class)));

        Method method = Base.class.getDeclaredMethod("run");
        System.out.println("method byType: "
                + values(method.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("method container: "
                + (method.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("method direct single: "
                + (method.getDeclaredAnnotation(Tag.class) != null));
    }
}
```

### 13.2. Biên dịch và chạy

Dùng Java Development Kit 17 hoặc phiên bản tương thích mới hơn:

```bash
javac --release 17 RepeatableDemo.java
java RepeatableDemo
```

Chương trình đã được biên dịch với `javac --release 17` và chạy thực tế. Kết quả:

```text
base byType: [stable, audited]
base direct single: false
base container: true
base declared count: 1
child byType: [stable, audited]
child declared byType: 0
local byType: [local]
explicit byType: [manual-a, manual-b]
method byType: [read, cache]
method container: true
method direct single: false
```

### 13.3. Diễn giải đầu ra

**`base byType`:** `Base` có hai `@Tag`, nên `getAnnotationsByType(Tag.class)` trả đủ hai giá trị theo thứ tự khai báo.

**`base direct single: false`:** Mặc dù `Base` có hai cấu hình tag, `getDeclaredAnnotation(Tag.class)` không tìm được `@Tag` trực tiếp vì các giá trị nằm gián tiếp trong container.

**`base container: true` và `base declared count: 1`:** Compiler biểu diễn hai `@Tag` qua một `@Tags` container trực tiếp. Vì `Base` không có annotation trực tiếp nào khác ngoài container đó, `getDeclaredAnnotations().length` là `1`.

**`child byType` và `child declared byType`:** `Child` không khai báo `@Tag`; nhờ `@Inherited` trên cặp annotation, `getAnnotationsByType(Tag.class)` lấy được hai tag từ `Base`. `getDeclaredAnnotationsByType` trả mảng rỗng vì chính `Child` không khai báo tag nào.

**`local byType: [local]`:** `Local` có một tag riêng; `getAnnotationsByType` chọn tag local, không cộng thêm `stable` hoặc `audited` từ `Base`.

**`explicit byType`:** Container viết tường minh `@Tags({ ... })` cũng được Reflection giải nén thành hai `@Tag`.

**`method byType`:** `Base.run` có hai `@Tag` khai báo trên method; `getDeclaredAnnotationsByType` đọc đúng hai giá trị, `getDeclaredAnnotation(Tags.class)` đọc được container và `getDeclaredAnnotation(Tag.class)` không có giá trị trực tiếp.

### 13.4. Một thay đổi nhỏ để tự thử

Đổi dòng `@Tag("stable") @Tag("audited")` trước `Base` thành chỉ `@Tag("stable")`, sau đó biên dịch lại. Khi chỉ có **một annotation trực tiếp**, `Base.class.getDeclaredAnnotation(Tag.class) != null` thường sẽ là `true`; `getDeclaredAnnotation(Tags.class) != null` là `false`; `getAnnotationsByType(Tag.class)` vẫn trả mảng chứa một phần tử.

Thử nghiệm đó cho thấy vì sao **API by-type là lựa chọn ổn định** cho thư viện có thể nhận 0, 1 hoặc nhiều cấu hình lặp.

## 14. Các lỗi thường gặp trong dự án

| Lỗi | Nguyên nhân | Cách đúng |
|---|---|---|
| Gắn hai `@Tag` nhưng quên `@Repeatable` | Compiler không biết container hợp lệ | Thêm `@Repeatable(Tags.class)` vào kiểu `Tag` |
| Container khai báo `String[] value()` | Không đúng `Tag[]` | Khai báo `Tag[] value();` |
| Chỉ gắn `RUNTIME` trên `Tag` | Container không có retention tương thích | Gắn `@Retention(RUNTIME)` cho cả hai |
| `Tag` có `@Inherited` nhưng container thiếu | Vi phạm ràng buộc meta-annotation | Gắn `@Inherited` cho container |
| Dùng `getAnnotation(Tag.class)` để lấy nhiều tag | Phương thức không giải nén container | Dùng `getAnnotationsByType(Tag.class)` |
| Duyệt `getDeclaredAnnotations()` rồi cast trực tiếp thành `Tag` | Thường phần tử thực tế là container `Tags` | Dùng by-type hoặc kiểm tra `annotation.annotationType()` |
| Dùng `getDeclaredAnnotation(Tags.class)` và cho rằng luôn tồn tại | Chỉ một `@Tag` có thể lưu trực tiếp | Truy vấn `Tag` bằng by-type API |
| Nghĩ `getDeclaredAnnotationsByType` tự kế thừa | `Declared` chỉ lấy local annotations | Cân nhắc `getAnnotationsByType` trên class với `@Inherited` |
| Nghĩ tag trên subclass tự cộng tag từ parent | API associated inheritance là fallback | Muốn merge thì duyệt hierarchy và định nghĩa chính sách |
| Mong `@Inherited` ảnh hưởng annotation của method | Cơ chế áp dụng cho class inheritance | Tự quét overridden methods nếu cần |
| Dùng `@Target(TYPE)` rồi gắn lên field | Annotation không được phép ở vị trí đó | Chọn target phù hợp |
| Nhầm `RUNTIME` là bắt buộc cho compile-time processor | Annotation processing có thể diễn ra khi compile | Chọn retention theo nhu cầu, dùng RUNTIME cho runtime Reflection |
| Dựa vào thứ tự của danh sách mọi annotation type | Không phải contract thứ tự xử lý nghiệp vụ | Chỉ dùng thứ tự repeatables theo API khi đặc tả cần; tự thiết kế thứ tự cho metadata khác |
| Sử dụng container như một “mảng mutable” được chỉnh trong runtime | Annotation metadata không phải nơi cập nhật cấu hình đang chạy | Xử lý giá trị đọc được, không cố sửa annotation proxy/class metadata |

Một lưu ý bảo trì: khi **nâng cấp một annotation vốn không repeatable thành repeatable**, source code cũ dùng một annotation có thể vẫn hoạt động, nhưng thêm bản lặp thứ hai làm cách biểu diễn Reflection chuyển sang container. Mọi scanner cũ chỉ sử dụng `getAnnotation` hoặc `getDeclaredAnnotations` có thể phải được cập nhật.

## 15. Câu hỏi tự kiểm tra

1. Tại sao Java cần `@Repeatable(Tags.class)` dù source có thể viết hai `@Tag` trên một class?
2. Container phải có phần tử `value()` trả về kiểu gì?
3. Khi hai `@Tag` được lặp trên một class, `getDeclaredAnnotation(Tag.class)` và `getDeclaredAnnotationsByType(Tag.class)` có thể trả kết quả khác nhau ra sao?
4. Vì sao annotation phải có `@Retention(RUNTIME)` nếu framework muốn đọc qua Reflection khi chương trình đang chạy?
5. Sự khác nhau giữa `getAnnotationsByType` và `getDeclaredAnnotationsByType` khi có `@Inherited`?
6. Nếu subclass khai báo một `@Tag("local")`, Reflection có tự động trả thêm các `@Tag` của superclass không?
7. `@Inherited` có giúp method override tự kế thừa annotation của method bị override không?
8. Khi nào cần dùng `@Target({TYPE, METHOD})` trên cả repeatable type và container?
9. Nếu một method có hai `@Tag` nhưng chương trình chỉ thấy một `@Tags` qua `getDeclaredAnnotations()`, đây có phải lỗi compiler không?
10. Để đọc cấu hình repeatable ổn định với 0/1/n annotation, nên gọi API nào?
11. Khi nào khai báo `@Tags({@Tag("A"), @Tag("B")})` tường minh có cùng hiệu quả đọc by-type với hai `@Tag` liên tiếp?
12. Với framework cần gộp annotation trên class con và nhiều superclass, vì sao phải tự thiết kế logic merge?

**Ghi nhớ:** `@Repeatable(Container.class)` cho phép **nhiều annotation cùng kiểu trên một element**; container chứa chúng trong mảng `value()`. Muốn đọc tất cả các giá trị đúng cách bằng Java Reflection, ưu tiên `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType`. Hãy xem xét riêng retention, target và inheritance; đừng nhầm annotation gián tiếp trong container với annotation hiện diện trực tiếp.

Tài liệu chính thức Java 17: [`Repeatable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html), [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html), [`Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html), [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html), [JLS `9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3) và [JLS `9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5).