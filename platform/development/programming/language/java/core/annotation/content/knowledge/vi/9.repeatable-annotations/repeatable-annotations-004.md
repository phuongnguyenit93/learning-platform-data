# Ràng buộc Target, Retention, Documented và Inherited của kiểu chứa annotation lặp

Một annotation trong Java có thể xuất hiện nhiều lần trên cùng một khai báo khi annotation type đó được đánh dấu bằng `@Repeatable`. Tuy nhiên, chỉ khai báo `@Repeatable(Container.class)` chưa đủ. **Kiểu chứa (containing annotation type, thường gọi là container)** phải tương thích với annotation được lặp (base/repeatable annotation) theo những quy tắc về `@Target`, `@Retention`, `@Documented` và `@Inherited`.

Nếu vi phạm, lỗi có thể xuất hiện **ngay tại lúc khai báo annotation** hoặc **khi sử dụng lặp lại ở một vị trí cụ thể**. Ngay cả khi code biên dịch thành công, chọn metadata không nhất quán có thể dẫn đến kết quả bất ngờ khi reflection đọc các annotation hoặc khi sinh Javadoc.

Bài này tập trung vào **hợp đồng giữa annotation lặp và kiểu chứa của nó**, cùng cách kiểm tra thực tế với Java 17 trở lên.

## 1. Hai kiểu tham gia một annotation lặp

Ví dụ một annotation `@Role` có thể lặp trên cùng một lớp:

~~~java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}

@Role("reader")
@Role("writer")
class AccountService {}
~~~

Ở đây:

- `Role` là **base annotation type**: annotation người viết source muốn lặp lại.
- `Roles` là **containing annotation type**: chứa mảng các `Role` qua element `Role[] value()`.
- Khi có nhiều `@Role` tại cùng một vị trí, Java xử lý chúng như một **container annotation ngầm định** có `value` chứa các base annotations theo thứ tự nguồn.
- `@Repeatable(Roles.class)` phải chỉ đúng kiểu chứa. Tên `Roles` chỉ là quy ước dễ đọc; Java không tự suy ra container từ việc thêm chữ “s”.

Hai khai báo trên sử dụng retention mặc định `CLASS`; ví dụ chỉ để minh họa cú pháp, chưa thiết kế cho reflection runtime.

### Điều kiện nền tảng của container

Theo Java Language Specification (JLS) `9.6.3, `Roles` muốn là kiểu chứa hợp lệ của `Role` thì:

1. Phải có element **`Role[] value()`** với kiểu trả về chính xác.
2. Mọi element khác ngoài `value()`, nếu có, **phải khai báo default**.
3. Retention của container phải **ít nhất dài bằng** retention của base annotation.
4. Container chỉ được áp dụng tại những vị trí mà base annotation cũng áp dụng, với các quy tắc tương đương đặc biệt dành cho `TYPE`, `ANNOTATION_TYPE` và `TYPE_PARAMETER`.
5. Nếu base có `@Documented`, container cũng phải có `@Documented`.
6. Nếu base có `@Inherited`, container cũng phải có `@Inherited`.

Các điều kiện trên được kiểm tra khi compiler xác định container có hợp lệ cho `@Repeatable` hay không. Chúng khác với yêu cầu rằng **ở chỗ sử dụng lặp thật sự**, cả base và container đều phải phù hợp với vị trí đó.

## 2. @Target: kiểu chứa được hẹp hơn, nhưng không được rộng tùy ý

`@Target` quyết định annotation được gắn ở những vị trí nào (`ElementType`), như `TYPE`, `METHOD`, `FIELD`, `PARAMETER` hay `TYPE_USE`.

Quy tắc cốt lõi là:

> Container phải chỉ hỗ trợ những ngữ cảnh mà base annotation cũng hỗ trợ. Container có thể **hẹp hơn** base; điều đó giới hạn **nơi được phép lặp** base annotation.

Ví dụ hợp lệ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@Target(ElementType.TYPE)
@interface Flags {
    Flag[] value();
}
~~~

`Flag` dùng được trên class hoặc method. `Flags` chỉ dùng được trên class. Vì vậy:

~~~java
@Flag("a")
@Flag("b")
class OrderService {
    @Flag("single")
    void process() {}

    // Hai @Flag trên cùng method sẽ lỗi vì
    // container Flags không áp dụng ở METHOD.
}
~~~

Trong ví dụ này, việc **dùng một `@Flag` trên method là hợp lệ**. Nhưng nếu đặt **hai `@Flag` trên method**, compiler phải tạo container ngầm định `@Flags` ở đó; `Flags` lại không có target `METHOD`, nên việc lặp tại method bị từ chối.

Đây là khác biệt quan trọng giữa:

- **Base áp dụng được tại nơi đó hay không?**
- **Base có thể được lặp tại nơi đó hay không?** Muốn lặp, **cả base lẫn container** phải áp dụng được tại chỗ đó.

### Khi khai báo Target khiến container sai từ đầu

Ví dụ cố ý sai (không đưa vào chương trình chạy):

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Repeatable(Wrappers.class)
@interface Mark {}

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Wrappers {
    Mark[] value();
}
~~~

`Mark` chỉ áp dụng cho `TYPE` nhưng `Wrappers` lại áp dụng cả `METHOD`. Đây là **container không hợp lệ**, vì container rộng hơn base ở `METHOD`. Không phải đợi đến lúc ghi hai `@Mark` trên method mới báo lỗi; định nghĩa `@Repeatable(Wrappers.class)` đã vi phạm hợp đồng.

### Chú ý các trường hợp TYPE, ANNOTATION_TYPE, TYPE_USE và TYPE_PARAMETER

Đặc tả không so sánh tập `ElementType` bằng một phép so sánh chuỗi hoặc tập hợp đơn giản. `TYPE` và `TYPE_USE` đều có thể bao phủ **khai báo kiểu**, `TYPE` cũng bao phủ khai báo annotation interface; tương tự `TYPE_USE` có thể bao phủ khai báo type parameter.

Cụ thể, khi container có:

- `ANNOTATION_TYPE`: base có thể có `ANNOTATION_TYPE`, `TYPE` hoặc `TYPE_USE`.
- `TYPE`: base có thể có `TYPE` hoặc `TYPE_USE`.
- `TYPE_PARAMETER`: base có thể có `TYPE_PARAMETER` hoặc `TYPE_USE`.

Đó là ba ngoại lệ so với yêu cầu cùng một enum constant. Ví dụ **base `@Target(TYPE)` và container `@Target(ANNOTATION_TYPE)` là hợp lệ**: việc lặp base có thể diễn ra trên khai báo annotation interface, nhưng không trên lớp Java thông thường.

Nếu base có `@Target(TYPE_USE)` và container có `@Target(TYPE)`, có thể xét sự tương thích theo quy tắc `TYPE_USE` bao phủ khai báo kiểu, nhưng **đừng suy ngược rằng `TYPE` cho phép sử dụng annotation tại mọi type-use context** như generic type argument. Muốn dùng lặp trong `List<@Mark String>`, container phải phù hợp với chính type context đó.

### Không khai báo @Target thì sao?

Nếu cả hai không khai báo `@Target`, chúng có thể xuất hiện/lặp ở các **declaration contexts** được ngôn ngữ cho phép, nhưng không tự động trở thành type-use annotations.

Nếu base không khai báo `@Target` còn container có `@Target`, việc lặp chỉ thực hiện được ở **giao của những vị trí hợp lệ**, thường bị thu hẹp bởi container. Nếu base có `@Target` cụ thể, container phải được thiết kế trong giới hạn vị trí của base theo quy tắc JLS.

Trong thư viện, nên khai báo `@Target` rõ ràng cho **cả hai kiểu** để phạm vi sử dụng dễ hiểu và ít tạo cơ hội gắn sai.

## 3. @Retention: container phải sống ít nhất lâu bằng base

`@Retention` xác định metadata được giữ tới giai đoạn nào:

| RetentionPolicy | Ý nghĩa |
| --- | --- |
| `SOURCE` | Chỉ trong source, không lưu annotation này trong class file |
| `CLASS` | Lưu trong class file, không bảo đảm truy cập qua reflection runtime |
| `RUNTIME` | Lưu trong class file và có thể truy cập bằng runtime reflection |

Khi không khai báo `@Retention`, mặc định là **`CLASS`**.

Thứ tự thời gian lưu giữ xét theo `SOURCE < CLASS < RUNTIME`. JLS yêu cầu:

**Retention(container) ≥ Retention(base).**

| Base | Container | Container hợp lệ theo retention? |
| --- | --- | --- |
| SOURCE | SOURCE | Có |
| SOURCE | CLASS | Có |
| SOURCE | RUNTIME | Có |
| CLASS | SOURCE | Không |
| CLASS | CLASS | Có |
| CLASS | RUNTIME | Có |
| RUNTIME | SOURCE | Không |
| RUNTIME | CLASS | Không |
| RUNTIME | RUNTIME | Có |

Cần hiểu rằng một hàng “Có” chỉ thỏa **điều kiện retention**; còn phải thỏa các điều kiện container khác như `value()`, `@Target`, `@Documented`, `@Inherited`.

### Ví dụ sai: base RUNTIME, container CLASS

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {}

@Retention(RetentionPolicy.CLASS)
@interface Tags {
    Tag[] value();
}
~~~

Đây là ví dụ **cố ý không biên dịch**: `Tag` muốn giữ đến runtime, nhưng `Tags` chỉ có retention `CLASS`. Khi lặp `@Tag`, compiler cần container ngầm định để biểu diễn các giá trị; nếu container bị loại khỏi metadata runtime, thông tin không thể được phản chiếu nhất quán. Java ngăn thiết kế đó ngay ở định nghĩa annotation.

### Tại sao thường chọn cùng retention?

Dù `SOURCE` base và `RUNTIME` container có thể thỏa quy tắc JLS, cách thiết kế chênh lệch dễ gây khó hiểu khi công cụ đọc các biểu diễn trực tiếp/container của annotations. Với một API annotation mới, lựa chọn **cùng `@Retention` cho cả base và container** thường rõ ràng nhất.

Nếu framework cần gọi `getAnnotationsByType(...)` tại runtime, cả base và container nên có `@Retention(RUNTIME)`. Đặt annotation ở vị trí hợp lệ không bảo đảm Java reflection nhìn thấy khi retention chỉ là SOURCE hoặc CLASS.

## 4. @Documented: nếu base có, container cũng phải có

`@Documented` là meta-annotation ảnh hưởng đến việc đưa các annotation vào tài liệu API sinh bởi Javadoc.

Quy tắc **một chiều** của JLS:

- **Base có `@Documented` ⇒ container bắt buộc có `@Documented`.**
- Container có `@Documented`, base không có: **vẫn hợp lệ theo quy tắc container**.

Ví dụ được thiết kế đúng:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.Repeatable;

@Documented
@Repeatable(Policies.class)
@interface Policy {
    String value();
}

@Documented
@interface Policies {
    Policy[] value();
}
~~~

Khi lặp `@Policy`, compiler biểu diễn bằng container. Giữ `@Documented` trên container giúp hệ thống tài liệu có thông tin rằng container đại diện cho annotations cần được tài liệu hóa. Nếu thiếu `@Documented` trên container trong khi base có, `@Repeatable` khai báo container **không hợp lệ tại compile time**.

Ví dụ cố ý sai:

~~~java
@java.lang.annotation.Documented
@java.lang.annotation.Repeatable(Labels.class)
@interface Label {}

@interface Labels {
    Label[] value();
}
// LỖI: base @Documented nhưng container thiếu @Documented.
~~~

Việc container có `@Documented` **không tự động làm toàn bộ nghiệp vụ annotation xuất hiện như một bảng riêng trong mọi bộ sinh tài liệu**. Javadoc chỉ đọc/tổ chức metadata theo quy tắc của công cụ; hiển thị cuối cùng còn phụ thuộc vị trí annotation và cách công cụ render.

Trong thực tế, cách dễ bảo trì là gắn `@Documented` cho cả hai hoặc không gắn cho cả hai, trừ khi có lý do API rõ ràng để chúng khác nhau.

## 5. @Inherited: nếu base kế thừa, container cũng phải kế thừa

`@Inherited` áp dụng cho truy vấn annotations của **class** trong quan hệ superclass/subclass. Nó **không tự làm annotation trên method, field hoặc interface được kế thừa theo nghĩa reflection của `@Inherited`**.

Quy tắc **một chiều** tương tự:

- **Base có `@Inherited` ⇒ container bắt buộc có `@Inherited`.**
- Container có `@Inherited` còn base không có: **không bị quy tắc container này cấm**, nhưng phải đánh giá kỹ ý nghĩa mong muốn.

Ví dụ hợp lệ:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;

@Inherited
@Repeatable(Features.class)
@interface Feature {
    String value();
}

@Inherited
@interface Features {
    Feature[] value();
}
~~~

Nếu base có `@Inherited` nhưng container thiếu `@Inherited`, compiler báo lỗi ngay tại định nghĩa của annotation lặp. Lý do: khi hai base annotations được gộp thành một container, metadata kế thừa cũng cần có đường đi tương thích.

Tuy nhiên, `@Inherited` không có nghĩa là JVM nhân bản các annotations từ superclass vào class file subclass. Nó là quy tắc truy vấn qua reflection khi annotation type đánh dấu inheritable, ví dụ `Class.getAnnotationsByType(...)`. `getDeclaredAnnotationsByType(...)` chỉ xem annotations được khai báo trực tiếp và không đi lên superclass.

### Giới hạn quan trọng

- Chỉ **class-to-subclass**, không áp dụng như vậy cho interface-to-implementing-class.
- Không tự truyền annotation từ một method của superclass sang overriding method trong subclass.
- Một subclass khai báo trực tiếp annotations cùng loại có thể **che** inherited annotations khi truy vấn `getAnnotationsByType`; kết quả không phải luôn là phép nối vô điều kiện giữa annotations của cha và con.
- `@Inherited` không thay đổi `@Target` và không biến các vị trí không hợp lệ thành hợp lệ.
- Muốn đọc annotations khi chạy, vẫn cần retention thích hợp; `@Inherited` một mình không làm SOURCE/CLASS annotation hiện diện trong runtime reflection.

## 6. Ví dụ Java 17 hoàn chỉnh: cả bốn meta-annotation nhất quán

Giả sử API cho phép gắn nhiều nhãn `@Tag` lên class hoặc method; muốn các nhãn được tài liệu hóa, giữ đến runtime và cho phép subclass kế thừa nhãn class.

Lưu file **RepeatableContainerDemo.java**:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
    String category() default "general";
}

@Tag("core")
@Tag("report")
class BaseHandler {
    @Tag("audit")
    @Tag("latency")
    void handle() {}
}

class DerivedHandler extends BaseHandler {
    @Override
    void handle() {}
}

@Tag("child")
class TaggedChild extends BaseHandler {}

public class RepeatableContainerDemo {
    static String labels(Tag[] tags) {
        return Arrays.stream(tags).map(Tag::value)
                .collect(Collectors.joining(","));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("base=" + labels(
                BaseHandler.class.getDeclaredAnnotationsByType(Tag.class)));
        System.out.println("container=" +
                (BaseHandler.class.getDeclaredAnnotation(Tags.class) != null));
        System.out.println("directSingle=" +
                (BaseHandler.class.getDeclaredAnnotation(Tag.class) != null));
        System.out.println("derivedDeclared=" +
                DerivedHandler.class.getDeclaredAnnotationsByType(Tag.class).length);
        System.out.println("derivedInherited=" + labels(
                DerivedHandler.class.getAnnotationsByType(Tag.class)));
        System.out.println("childOwn=" + labels(
                TaggedChild.class.getAnnotationsByType(Tag.class)));
        System.out.println("overriddenMethod=" +
                DerivedHandler.class.getDeclaredMethod("handle")
                        .getAnnotationsByType(Tag.class).length);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 RepeatableContainerDemo.java
java RepeatableContainerDemo
~~~

**Stdout chính xác (đã biên dịch và chạy bằng JDK 21 với `--release 17`):**

~~~text
base=core,report
container=true
directSingle=false
derivedDeclared=0
derivedInherited=core,report
childOwn=child
overriddenMethod=0
~~~

**Đọc kết quả theo từng cơ chế:**

1. `@Target({TYPE, METHOD})` trên **cả hai** kiểu cho phép lặp `Tag` trên class `BaseHandler` và method `handle`. Không loại nào rộng hơn loại còn lại.
2. `@Retention(RUNTIME)` trên cả base và container làm metadata có thể đọc qua reflection. Hai `@Tag` gắn trực tiếp cùng vị trí được biểu diễn như một `@Tags` container: vì vậy `container=true`, còn `directSingle=false`.
3. `getDeclaredAnnotationsByType(Tag.class)` hiểu cấu trúc container và trả hai giá trị `core`, `report` theo thứ tự khai báo: `base=core,report`.
4. `DerivedHandler` không khai báo `Tag` trực tiếp, nên `derivedDeclared=0`; nhưng cả hai kiểu có `@Inherited` nên truy vấn `getAnnotationsByType(Tag.class)` tìm qua superclass và thu được `derivedInherited=core,report`.
5. `TaggedChild` có một `@Tag("child")` trực tiếp, nên kết quả `childOwn=child`, không tự cộng thêm `core,report` từ cha.
6. Overriding method `DerivedHandler.handle()` **không kế thừa `@Tag` từ method cha**. Kết quả `overriddenMethod=0` mặc dù base và container có `@Inherited`.
7. `@Documented` không có dòng stdout, vì tác dụng của nó liên quan đến sinh tài liệu API, không phải một hàm runtime làm thay đổi nhãn.

Ở đây `Tags.category()` có `default "general"`. Nếu xóa default trong khi vẫn giữ element ngoài `value()`, container sẽ không hợp lệ theo JLS `9.6.3.

**Lưu ý:** `getAnnotation(Tag.class)` (không có “sByType”) không tự bung toàn bộ các repeatable annotations trong container. Khi cần lấy cả nhóm, ưu tiên `getAnnotationsByType(Tag.class)` hoặc `getDeclaredAnnotationsByType(Tag.class)` tùy yêu cầu kế thừa.

## 7. Lỗi khai báo thường gặp: phân biệt lỗi của container và lỗi nơi dùng

Các đoạn sau là **minh họa cố ý sai, không ghép vào file runnable**. Mỗi đoạn giả định tên annotation được định nghĩa riêng để tránh trùng nhau.

### Lỗi 1: Container value() sai kiểu

~~~java
@java.lang.annotation.Repeatable(Boxes.class)
@interface Box {}

@interface Boxes {
    Object[] value(); // Sai: phải là Box[].
}
~~~

Điều kiện đầu tiên đã sai. Container phải trả **mảng đúng base annotation type**.

### Lỗi 2: Element phụ không có default

~~~java
@java.lang.annotation.Repeatable(Headers.class)
@interface Header {}

@interface Headers {
    Header[] value();
    String owner(); // Sai: element phụ bắt buộc có default.
}
~~~

Compiler không thể tạo container ngầm định đúng hợp đồng khi thiếu giá trị bắt buộc của element phụ. Sửa thành `String owner() default "unknown";` hoặc bỏ element.

### Lỗi 3: Container có Target rộng hơn base

~~~java
@java.lang.annotation.Target(java.lang.annotation.ElementType.METHOD)
@java.lang.annotation.Repeatable(Methods.class)
@interface MethodTag {}

@java.lang.annotation.Target({
    java.lang.annotation.ElementType.METHOD,
    java.lang.annotation.ElementType.FIELD
})
@interface Methods {
    MethodTag[] value();
}
~~~

Base chỉ áp dụng ở METHOD, container có thêm FIELD. Đây là lỗi khai báo container. Sửa bằng cách bỏ FIELD khỏi container, hoặc mở base nếu hợp đồng API thực sự cần FIELD.

### Lỗi 4: Container bị thiếu runtime retention

~~~java
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.RUNTIME)
@java.lang.annotation.Repeatable(Options.class)
@interface Option {}

@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.CLASS)
@interface Options {
    Option[] value();
}
~~~

Base là RUNTIME nhưng container CLASS: **không hợp lệ**, không phải chỉ gây thiếu dữ liệu khi chạy.

### Lỗi 5: Thiếu Documented hoặc Inherited trên container

~~~java
@java.lang.annotation.Documented
@java.lang.annotation.Inherited
@java.lang.annotation.Repeatable(Markers.class)
@interface Marker {}

@interface Markers {
    Marker[] value();
    // Sai: container chưa có cả @Documented và @Inherited.
}
~~~

Mỗi ràng buộc một chiều đều áp dụng: chỉ thêm một trong hai vẫn chưa đủ nếu base có cả hai.

### Lỗi 6: Định nghĩa hợp lệ nhưng dùng lặp sai nơi

~~~java
@java.lang.annotation.Target({
    java.lang.annotation.ElementType.TYPE,
    java.lang.annotation.ElementType.METHOD
})
@java.lang.annotation.Repeatable(Checks.class)
@interface Check {}

@java.lang.annotation.Target(java.lang.annotation.ElementType.TYPE)
@interface Checks {
    Check[] value();
}

class Processor {
    @Check
    void workOnce() {} // Đúng: một annotation trên method.

    // @Check @Check
    // void workTwice() {} // Sai: cần container tại METHOD.
}
~~~

Ở đây **hai định nghĩa hợp lệ** nhưng vị trí lặp **không hợp lệ**. Cách xử lý phụ thuộc ý đồ: bổ sung `METHOD` cho `Checks` nếu muốn lặp tại method, hoặc chỉ cho dùng một `@Check` tại vị trí đó.

### Lỗi 7: Trộn container tường minh và base lặp

~~~java
// CỐ Ý SAI: đặt nhiều base annotations cùng container tường minh.
//
// @Tag("a")
// @Tag("b")
// @Tags({@Tag("c")})
// class Mixed {}
~~~

Khi đã có nhiều `@Tag` cùng vị trí, compiler sẽ cần container ngầm định. Không thể đồng thời đặt một `@Tags` tường minh tại đó. Quy tắc này thuộc **JLS `9.7.5**, khác với tính hợp lệ của định nghĩa container ở `9.6.3.

## 8. Kiểm tra mục tiêu triển khai qua reflection và Javadoc

Khi phát triển library/framework dùng repeatable annotations, hãy chia QA thành những câu hỏi khác nhau:

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Có được định nghĩa như container hợp lệ? | Biên dịch định nghĩa base/container; kiểm tra `value()`, default và bốn meta-annotations |
| Có thể lặp tại class, method hay field đang quan tâm? | Biên dịch một ví dụ **hai annotation tại đúng vị trí sử dụng** |
| Runtime lấy được tất cả giá trị lặp? | Dùng `getAnnotationsByType` và `getDeclaredAnnotationsByType` |
| Kế thừa trên subclass đúng kỳ vọng? | So sánh truy vấn trên class cha/con, cùng một trường hợp con có annotation trực tiếp |
| Javadoc hiển thị metadata phù hợp? | Sinh tài liệu với `javadoc` cho API thực tế nếu `@Documented` là yêu cầu |
| Có chấp nhận tương thích giữa phiên bản? | Kiểm thử compiler/JDK và dữ liệu metadata khi thay `@Target`, retention hoặc container type |

Không nên chỉ nhìn `@Repeatable(Container.class)` và kết luận annotation sẽ lặp được ở mọi vị trí hay tự được thừa kế.

### Lưu ý khi thay đổi một annotation API đã phát hành

- **Thu hẹp `@Target` của container** có thể khiến source đang lặp hợp lệ trước đó không còn biên dịch.
- **Thay `@Retention`** ảnh hưởng khả năng tìm thấy metadata qua class file/runtime reflection; thay đổi cần được phối hợp với consumer.
- **Bỏ `@Documented` hoặc `@Inherited` trên container** khi base vẫn giữ có thể làm **chính định nghĩa annotation không còn hợp lệ**.
- **Đổi tên hoặc kiểu container** cần kiểm tra mã và công cụ đọc các annotation đã biên dịch trước đó; metadata trong class file không tự được viết lại bởi việc sửa source thư viện.
- **Đổi element phụ không có default** có thể làm container mất tính hợp lệ dù khai báo `value()` đúng.

Đối với một annotation mới, chọn **giống nhau** về Target, Retention, Documented và Inherited cho base/container thường là cấu hình dễ hiểu và bảo trì. Tuy nhiên, **không bắt buộc mọi đặc điểm đều giống nhau**: đặc tả chủ động cho phép container có Target hẹp hơn và retention dài hơn, cũng như một số khác biệt `@Documented`, `@Inherited` theo một chiều. Khi dùng sự khác biệt đó, nên viết test thực sự tại các vị trí sử dụng dự kiến.

## 9. Quy trình quyết định và tự kiểm tra

Hãy hỏi theo thứ tự:

1. **Base có `@Repeatable` trỏ đúng container chưa?** Container có `Base[] value()` chính xác và element phụ có default không?
2. **Container có vượt quyền nơi sử dụng của base không?** Kiểm tra Target theo JLS `9.6.3, kể cả các ngoại lệ TYPE/TYPE_USE/ANNOTATION_TYPE/TYPE_PARAMETER.
3. **Container có giữ metadata ít nhất lâu bằng base không?** Nếu base RUNTIME, container cũng phải RUNTIME.
4. **Base có `@Documented` hoặc `@Inherited` không?** Nếu có, container phải có annotation tương ứng.
5. **Chỗ sử dụng lặp có hợp lệ cho cả hai loại không?** Định nghĩa container hợp lệ chưa bảo đảm lặp được ở mọi Target của base.
6. **Consumer cần thấy gì?** Chọn đúng reflection API, retention, cơ chế inheritance; kiểm thử cả class và method khi liên quan.

Một số câu hỏi ôn tập:

**(1) Base target TYPE và METHOD; container chỉ TYPE. Có khai báo được không? Có lặp hai lần trên method được không?** Khai báo **hợp lệ**; việc lặp trên method **không hợp lệ** vì container không áp dụng ở METHOD. Một annotation đơn trên method vẫn hợp lệ.

**(2) Base RUNTIME; container không có @Retention. Được không?** **Không**. Container mặc định CLASS, ngắn hơn base RUNTIME.

**(3) Base không có @Documented, container có @Documented. Có bị cấm không?** Không; ràng buộc chỉ yêu cầu chiều **base có thì container cũng phải có**. Tương tự với `@Inherited`.

**(4) Vì sao derived class đọc được hai @Tag từ cha nhưng overriding method không thấy hai @Tag trên method cha?** Vì `@Inherited` chỉ hỗ trợ **class annotations** qua superclass, không kế thừa annotations của method override.

**(5) Nếu một container có thêm element ngoài value(), phải làm gì?** Cung cấp **default value** cho mỗi element phụ, để compiler có thể tạo container ngầm định từ danh sách base annotations.

**(6) Container @Target(ANNOTATION_TYPE), base @Target(TYPE). Khai báo hợp lệ không?** **Hợp lệ**, vì base TYPE bao gồm annotation interface declarations. Nhưng việc lặp base ở class thông thường sẽ bị từ chối nếu container chỉ có ANNOTATION_TYPE.

## 10. Tài liệu chuẩn

- Java Language Specification, Java SE 21, **`9.6.3 Repeatable Annotation Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.3
- **`9.6.4.1 @Target**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.1
- **`9.6.4.2 @Retention**, **`9.6.4.3 @Inherited**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html
- **`9.7.5 Multiple Annotations of the Same Interface**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.5
- JDK 21 API, **Repeatable**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/Repeatable.html

Khi thiết kế annotation lặp, hãy kiểm tra **hai tầng hợp lệ**: container **được khai báo hợp lệ** theo sáu điều kiện của JLS `9.6.3; và **việc lặp tại đúng vị trí sử dụng** hợp lệ theo `9.7.5. Những ràng buộc về `@Target`, `@Retention`, `@Documented` và `@Inherited` bảo đảm kiểu chứa có thể đại diện cho base annotations một cách nhất quán qua biên dịch, tài liệu và reflection.