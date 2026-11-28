# Annotation dựng sẵn, retention và target

Trong Java 27, **annotation** là metadata có cấu trúc được gắn vào khai báo chương trình hoặc vị trí sử dụng kiểu dữ liệu. Chúng giúp trình biên dịch, công cụ phân tích, bộ xử lý annotation và thư viện có thể nhận biết những thông tin bổ sung mà không phải thay đổi chữ ký phương thức hay cấu trúc lớp.

Ví dụ quen thuộc:

~~~java
class Parent {
    public String label() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    public String label() {
        return "Child";
    }
}
~~~

**@Override** nói với trình biên dịch rằng **Child.label()** phải thực sự ghi đè hoặc triển khai một phương thức hợp lệ. Nếu tên hoặc chữ ký bị viết sai, trình biên dịch báo lỗi thay vì âm thầm xem đó là phương thức mới.

Hai khái niệm chi phối việc thiết kế annotation là:

- **Retention:** metadata còn được giữ tới giai đoạn nào — chỉ trong mã nguồn, trong tệp lớp đã biên dịch, hay còn truy cập được qua reflection khi chạy?
- **Target:** annotation được phép đặt lên những thành phần nào — lớp, phương thức, field, tham số, record component hay vị trí sử dụng kiểu?

Hiểu hai khái niệm này giúp tránh những nhầm lẫn như “cứ gắn annotation là chương trình tự kiểm tra dữ liệu” hoặc “annotation đã có trong mã nguồn thì reflection chắc chắn đọc được”.

Bài viết tập trung vào API và cú pháp annotation còn áp dụng trong Java 27, tránh dùng những mô hình đã lỗi thời làm khuyến nghị phát triển mới.

## 1. Annotation là metadata, không phải lời gọi phương thức

Annotation có dạng:

~~~java
@Override
public String toString() {
    return "Sample";
}
~~~

Hoặc có các phần tử dữ liệu:

~~~java
@Deprecated(since = "2.0", forRemoval = false)
public void oldEntryPoint() {
    // Chỉ minh họa cách đánh dấu API đang được thay thế.
}
~~~

Thông tin bên trong annotation được khai báo theo một **annotation type**. Cú pháp **@Name** tại nơi sử dụng là một **annotation instance** ở cấp ngôn ngữ, không phải hành động gọi một constructor thông thường.

Annotation có thể được một hệ thống sử dụng theo nhiều cách:

1. **Trình biên dịch** kiểm tra một số annotation dựng sẵn, ví dụ **@Override**.
2. **Annotation processor** đọc metadata trong quá trình biên dịch để kiểm tra hoặc sinh mã nguồn.
3. **Công cụ** đọc metadata trong tệp **.class** theo mục đích của công cụ.
4. **Reflection** truy cập annotation có retention thích hợp khi chương trình chạy.
5. **Framework** diễn giải annotation và quyết định hành vi như đăng ký handler hoặc cấu hình dữ liệu.

Tự gắn một annotation do ứng dụng định nghĩa **không tự tạo ra quy tắc nghiệp vụ hay tác dụng phụ**. Phải có trình biên dịch, processor, framework hoặc mã ứng dụng đọc và thực thi hợp đồng đó.

### Phân biệt annotation với comment

Comment thông thường chủ yếu phục vụ người đọc mã. Annotation có cấu trúc và kiểu được kiểm tra theo quy tắc Java, nên công cụ có thể xử lý một cách đáng tin cậy hơn.

~~~java
// Important method.
public void calculate() {}
~~~

Comment trên không có ý nghĩa bắt buộc đối với trình biên dịch. Ngược lại:

~~~java
@Deprecated(since = "2.0")
public void calculate() {}
~~~

**@Deprecated** có ý nghĩa chuẩn đối với các công cụ Java và những nơi sử dụng method, dù không làm method tự động ngừng hoạt động.

## 2. Những annotation dựng sẵn thường dùng

Java cung cấp các annotation chuẩn phù hợp với nhiều nhu cầu biên dịch và thiết kế API.

| Annotation | Package | Ý nghĩa phổ biến |
|---|---|---|
| **@Override** | **java.lang** | Kiểm tra ý định ghi đè hoặc triển khai phương thức |
| **@Deprecated** | **java.lang** | Đánh dấu API không còn được khuyến nghị sử dụng |
| **@SuppressWarnings** | **java.lang** | Yêu cầu bỏ qua nhóm cảnh báo compiler được chỉ định trong phạm vi áp dụng |
| **@SafeVarargs** | **java.lang** | Cam kết một khai báo varargs đủ điều kiện không thực hiện thao tác không an toàn với đối số varargs |
| **@FunctionalInterface** | **java.lang** | Kiểm tra interface đáp ứng hợp đồng functional interface |
| **@Serial** | **java.io** | Kiểm tra ý định khai báo một số thành viên liên quan Java Object Serialization khi bảo trì mã sử dụng cơ chế này |
| **@Native** | **java.lang.annotation** | Đánh dấu hằng field có thể được tham chiếu từ mã native theo hợp đồng công cụ |

Bài này ưu tiên năm annotation đầu vì chúng được dùng rộng rãi trong mã Java hiện đại. **@Serial** vẫn là annotation hợp lệ khi bảo trì hệ thống đã sử dụng Java Object Serialization; tuy nhiên, không nên hiểu việc có annotation đó là khuyến nghị chọn serialization native của Java cho một thiết kế dữ liệu mới. **@Native** có phạm vi sử dụng chuyên biệt hơn.

Bên cạnh đó, Java có các **meta-annotation** thuộc **java.lang.annotation** để cấu hình annotation type, đặc biệt là **@Retention**, **@Target**, **@Documented**, **@Inherited** và **@Repeatable**.

## 3. @Override: kiểm tra hợp đồng ghi đè

**@Override** được đặt trên một khai báo phương thức để yêu cầu trình biên dịch xác minh phương thức thật sự ghi đè một phương thức lớp cha hoặc triển khai phương thức interface theo quy tắc Java.

~~~java
interface Formatter {
    String format(String text);
}

final class UppercaseFormatter implements Formatter {
    @Override
    public String format(String text) {
        return text.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Ở đây, **format(String)** trong **UppercaseFormatter** triển khai phương thức từ **Formatter**.

Nếu viết sai:

~~~java
final class BrokenFormatter implements Formatter {
    // @Override
    // public String formats(String text) { return text; }
    //
    // Lớp này sẽ không biên dịch nếu không triển khai format(String),
    // trừ khi được khai báo abstract.
}
~~~

Với lớp đã có cách triển khai kế thừa và một phương thức mới vô tình viết sai tên, **@Override** còn giúp phát hiện trường hợp dễ bị bỏ qua vì việc thêm phương thức mới vốn vẫn hợp lệ về cú pháp.

### Quy tắc thực hành

- Gắn **@Override** vào phương thức có chủ đích ghi đè.
- Đừng dùng annotation để cố ghi đè **private**, **static** hay **final** method: quy tắc overriding không cho phép những trường hợp đó theo cùng cách.
- **@Override** không thay thế các quy tắc về quyền truy cập, kiểu trả về và checked exception của phương thức ghi đè.

**@Override** phục vụ kiểm tra lúc biên dịch; mã chạy không cần dùng reflection để đọc nó.

## 4. @Deprecated: thông báo API nên được thay thế

**@Deprecated** được sử dụng khi một class, method hoặc thành phần API không còn được khuyến nghị cho mã mới. Nó hỗ trợ cảnh báo tại nơi gọi và có thể được hiển thị trong tài liệu.

~~~java
public final class ReportService {
    public String render(String content) {
        return "Report: " + content;
    }

    /**
     * @deprecated Dùng {@link #render(String)}.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public String createReport(String content) {
        return render(content);
    }
}
~~~

Các phần tử đáng chú ý:

- **since:** chuỗi mô tả phiên bản mà API được đánh dấu deprecated; đây là thông tin tài liệu, không tự thay đổi khả năng tương thích.
- **forRemoval:** **true** nếu chủ sở hữu API dự định loại bỏ phần tử trong một phiên bản tương lai; **false** không thể hiện cam kết loại bỏ.

Ví dụ trên giữ phương thức cũ làm đường chuyển tiếp, đồng thời cung cấp API thay thế. Khi phát triển mã mới, người dùng nên gọi **render(...)**.

**@Deprecated không vô hiệu hóa method và không tự xóa API**. Nó cũng không có nghĩa mọi annotation được giới thiệu từ lâu đều là lỗi thời: bản thân **@Deprecated** vẫn là một công cụ chuẩn hữu ích để tiến hóa API.

### @Deprecated và Javadoc @deprecated

Hai thứ có vai trò bổ sung:

- Annotation **@Deprecated** tạo metadata có thể được trình biên dịch và công cụ nhận diện.
- Thẻ Javadoc **@deprecated** giải thích lý do và gợi ý phương án thay thế cho người đọc.

Đối với API được công khai, nên sử dụng cả hai khi đánh dấu deprecated và có hướng dẫn chuyển đổi rõ ràng.

## 5. @SuppressWarnings: giới hạn phạm vi bỏ cảnh báo

**@SuppressWarnings** cho phép yêu cầu compiler không hiển thị một số nhóm cảnh báo tại một khai báo hoặc phạm vi tương ứng.

Ví dụ thường gặp:

~~~java
@SuppressWarnings("unchecked")
void methodWithReviewedUncheckedOperation() {
    // Chỉ nên suppress khi phép chuyển kiểu đã được chứng minh an toàn.
}
~~~

Một số tên cảnh báo phổ biến được **javac** hỗ trợ gồm:

- **"unchecked"** — thao tác generic chưa thể kiểm tra đầy đủ tại thời điểm biên dịch.
- **"deprecation"** — sử dụng API được đánh dấu deprecated.
- **"removal"** — sử dụng API được đánh dấu dự kiến loại bỏ.
- **"rawtypes"** — sử dụng raw generic type.

Các tên cảnh báo và chi tiết áp dụng có thể tùy compiler hoặc phiên bản. Không nên giả định mọi trình biên dịch đều hiểu mọi chuỗi cảnh báo giống nhau.

### Ưu tiên xử lý nguyên nhân thay vì che cảnh báo

Ví dụ thay vì dùng raw type:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Minh");
String first = names.get(0);
~~~

Mã đã có kiểu chính xác nên không cần **@SuppressWarnings("unchecked")**.

Nếu thực sự có phép ép kiểu unchecked ở một tầng hạ tầng khó tránh, hãy giới hạn annotation vào đúng biến, method hoặc phạm vi nhỏ nhất mà Java cho phép và ghi rõ vì sao thao tác an toàn.

**@SuppressWarnings không làm thao tác nguy hiểm trở nên an toàn**. Nó chỉ tác động tới cảnh báo phù hợp của công cụ biên dịch.

## 6. @SafeVarargs: cam kết an toàn khi dùng varargs generic

Varargs được Java biểu diễn qua một mảng. Khi dùng kiểu generic không có đầy đủ thông tin tại runtime, chẳng hạn **List<String>...**, việc truy cập qua một kiểu mảng rộng hơn có thể dẫn đến **heap pollution**.

**@SafeVarargs** cho biết tác giả đã kiểm tra một method hoặc constructor varargs đủ điều kiện và xác nhận việc dùng tham số varargs là an toàn theo hợp đồng Java.

~~~java
import java.util.ArrayList;
import java.util.List;

final class CollectionsExample {
    private CollectionsExample() {}

    @SafeVarargs
    static <T> List<T> merge(List<? extends T>... sources) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> source : sources) {
            result.addAll(source);
        }

        return List.copyOf(result);
    }
}
~~~

Trong ví dụ:

- Method không ghi giá trị sai kiểu vào mảng **sources**.
- Method không trả mảng **sources** ra ngoài hoặc lưu lại để nơi khác chỉnh sửa.
- Method chỉ đọc từng danh sách, tích lũy kết quả và trả về danh sách không sửa được.
- **List.copyOf(...)** từ chối phần tử null theo hợp đồng của nó.

### Những vị trí có thể dùng @SafeVarargs

Trong Java hiện hành, annotation này chỉ hợp lệ với **constructor có varargs**, hoặc **method có varargs** được khai báo là **static**, **final** hay **private**. Những phương thức instance có thể bị override không đáp ứng điều kiện.

**Không thêm @SafeVarargs để che cảnh báo mà chưa kiểm tra phần thân**. Annotation không thay đổi type erasure hoặc bổ sung kiểm tra kiểu cho mảng khi chạy.

## 7. @FunctionalInterface: xác nhận một hợp đồng hàm

**@FunctionalInterface** yêu cầu interface là một **functional interface** hợp lệ, có đúng một phương thức trừu tượng theo quy tắc của Java.

~~~java
@FunctionalInterface
interface TextCheck {
    boolean test(String text);

    default TextCheck negate() {
        return value -> !test(value);
    }
}
~~~

Sử dụng lambda:

~~~java
TextCheck nonBlank = text -> text != null && !text.isBlank();

System.out.println(nonBlank.test("Java")); // true
System.out.println(nonBlank.test("   "));  // false
~~~

Có một default method không làm interface mất tính chất functional. Những phương thức trừu tượng có cùng chữ ký với phương thức public của **Object** cũng được xét theo quy tắc riêng, không đơn giản chỉ đếm số dòng có từ khóa abstract.

Nếu vô tình thêm một abstract method độc lập thứ hai, compiler sẽ báo lỗi khi interface vẫn được gắn **@FunctionalInterface**.

Annotation không bắt buộc để một interface đủ điều kiện dùng với lambda, nhưng nên sử dụng nếu interface được thiết kế có chủ đích làm functional interface.

## 8. Tự khai báo annotation bằng @interface

Java dùng cú pháp **@interface** để khai báo một annotation type.

Ví dụ:

~~~java
@interface Label {
    String value();
}
~~~

Phương thức **value()** ở đây là một **annotation element**, không phải method xử lý nghiệp vụ thông thường. Khi annotation có duy nhất phần tử bắt buộc tên **value**, có thể sử dụng dạng rút gọn:

~~~java
@Label("public-api")
class PublicApi {}
~~~

Dạng đầy đủ tương đương:

~~~java
@Label(value = "public-api")
class PublicApiAlternative {}
~~~

Annotation type có thể định nghĩa nhiều phần tử với giá trị mặc định:

~~~java
@interface ApiInfo {
    String name();

    int version() default 1;

    String[] tags() default {};
}
~~~

Sử dụng:

~~~java
@ApiInfo(
        name = "payments",
        version = 2,
        tags = {"public", "stable"}
)
class PaymentApi {}
~~~

Nếu không truyền **version** hoặc **tags**, Java áp dụng giá trị mặc định đã khai báo. Nếu không có default, người dùng annotation phải cung cấp phần tử bắt buộc.

### Những kiểu dữ liệu được phép làm annotation element

Các kiểu hợp lệ gồm:

- Các kiểu nguyên thủy như **boolean**, **int**, **long**, **double**.
- **String**.
- **Class** hoặc một dạng parameterized **Class** được phép, ví dụ **Class<?>**.
- Enum type.
- Một annotation type khác.
- Mảng một chiều của các loại phù hợp nêu trên.

Ví dụ:

~~~java
enum Severity {
    INFO, WARNING, ERROR
}

@interface Rule {
    Severity level() default Severity.INFO;

    Class<?> handler() default Object.class;

    String[] labels() default {};
}
~~~

Không thể dùng một **List<String>** làm kiểu của annotation element, không thể dùng **null** làm giá trị phần tử và không thể khai báo một method annotation với tham số tùy ý hoặc **throws** như method ứng dụng thông thường.

Giá trị phần tử phải thuộc những dạng biểu thức annotation được ngôn ngữ cho phép, chẳng hạn hằng số biên dịch cho String/kiểu nguyên thủy, enum constant, class literal, annotation lồng nhau hoặc mảng của các giá trị phù hợp.

## 9. Meta-annotation là gì?

**Meta-annotation** là annotation được gắn trên chính khai báo annotation type để mô tả cách annotation mới được dùng.

Ví dụ:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tracked {
    String value();
}
~~~

Trong ví dụ:

- **@Retention(RetentionPolicy.RUNTIME)** yêu cầu giữ metadata để reflection đọc được ở thời điểm chạy.
- **@Target({ElementType.TYPE, ElementType.METHOD})** giới hạn nơi sử dụng annotation ở khai báo kiểu và method.
- **Tracked.value()** là phần tử dữ liệu mà người sử dụng phải cung cấp.

~~~java
@Tracked("service")
class InventoryService {
    @Tracked("operation")
    public void refresh() {}
}
~~~

Annotation **@Tracked** trong ví dụ chỉ cung cấp metadata; chưa có logic xử lý. Muốn thống kê, ghi log hay thực hiện kiểm tra theo metadata, một processor hoặc đoạn mã reflection cần chủ động đọc và diễn giải nó.

## 10. @Retention và ba mức RetentionPolicy

**@Retention** là meta-annotation xác định annotation còn được giữ tới giai đoạn nào.

| RetentionPolicy | Được giữ ở đâu? | Reflection thông thường đọc được khi chạy? | Ứng dụng thường gặp |
|---|---|---|---|
| **SOURCE** | Có trong mã nguồn, bị loại khỏi tệp lớp theo quy tắc retention | Không | Cảnh báo compiler, kiểm tra mã nguồn, annotation processing |
| **CLASS** | Có thể được lưu trong tệp **.class**, nhưng không giữ như annotation có thể truy cập runtime | Không | Công cụ phân tích hoặc xử lý bytecode |
| **RUNTIME** | Được lưu trong tệp lớp và có thể truy cập bằng cơ chế reflection phù hợp | Có | Framework hoặc ứng dụng đọc metadata lúc chạy |

Điểm quan trọng: **nếu không khai báo @Retention, retention mặc định là CLASS**, không phải RUNTIME.

### SOURCE: chỉ phục vụ giai đoạn biên dịch

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceReview {
    String owner();
}
~~~

Một annotation processor có thể đọc **@SourceReview** khi biên dịch, nhưng **Class.getAnnotation(SourceReview.class)** không dùng được để tìm metadata này khi chạy.

**@Override** và **@SuppressWarnings** là những ví dụ annotation dựng sẵn có ý nghĩa chủ yếu ở cấp biên dịch.

### CLASS: giữ trong tệp lớp, không phải runtime reflection

~~~java
@Retention(RetentionPolicy.CLASS)
@interface BytecodeMarker {
    String value();
}
~~~

Metadata của **@BytecodeMarker** có thể được công cụ làm việc với class file sử dụng theo đặc tính của chúng. Tuy nhiên, đừng mong **getAnnotation(BytecodeMarker.class)** trả về annotation này tại runtime.

Cần phân biệt công cụ phân tích bytecode với API reflection thông thường. Retention CLASS vẫn có ích dù không được reflection expose như RUNTIME.

### RUNTIME: đọc được khi chương trình chạy

~~~java
@Retention(RetentionPolicy.RUNTIME)
@interface Endpoint {
    String path();
}

@Endpoint(path = "/health")
class HealthEndpoint {}
~~~

Sử dụng reflection:

~~~java
Endpoint endpoint = HealthEndpoint.class.getAnnotation(Endpoint.class);

if (endpoint != null) {
    System.out.println(endpoint.path()); // /health
}
~~~

**RUNTIME** không có nghĩa Java tự xử lý endpoint hoặc mở HTTP server. Nó chỉ cung cấp metadata để mã ứng dụng hoặc framework đọc và thực hiện hành vi tương ứng.

### Retention nào phù hợp?

- Chỉ phục vụ compiler hoặc annotation processor: thường cân nhắc **SOURCE**.
- Phục vụ công cụ kiểm tra bytecode, không cần reflection: cân nhắc **CLASS**.
- Thực sự cần đọc qua reflection trong chương trình đang chạy: dùng **RUNTIME**.

Không nên chọn **RUNTIME** chỉ vì nghĩ nó luôn “mạnh hơn”. Nó khiến metadata có thể tồn tại và được đọc ở runtime dù không có nhu cầu thực tế. Thiết kế dựa trên consumer của metadata.

## 11. @Target và các ElementType quan trọng

**@Target** giới hạn những vị trí mà một annotation type có thể xuất hiện. Giá trị của nó là một hoặc nhiều hằng **ElementType**.

| ElementType | Vị trí đại diện |
|---|---|
| **TYPE** | Khai báo class, interface, enum, record hoặc annotation type theo quy tắc áp dụng |
| **FIELD** | Field của class/interface, bao gồm enum constant trong ngữ cảnh phù hợp |
| **METHOD** | Method |
| **PARAMETER** | Tham số hình thức của method hoặc constructor |
| **CONSTRUCTOR** | Constructor |
| **LOCAL_VARIABLE** | Khai báo biến cục bộ |
| **ANNOTATION_TYPE** | Khai báo annotation type |
| **PACKAGE** | Khai báo package |
| **MODULE** | Khai báo module |
| **TYPE_PARAMETER** | Khai báo tham số kiểu, ví dụ **<T>** |
| **TYPE_USE** | Những vị trí dùng kiểu: kiểu tham số hóa, kiểu trả về, cast, generic type argument... |
| **RECORD_COMPONENT** | Khai báo record component |

Ví dụ khai báo target cho method và constructor:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
@interface Audited {}
~~~

Sử dụng hợp lệ:

~~~java
class BillingService {
    @Audited
    BillingService() {}

    @Audited
    void charge() {}
}
~~~

Sử dụng **@Audited** trực tiếp lên một class sẽ không hợp lệ với target đã khai báo.

### Có nên bỏ @Target?

Nếu annotation không khai báo **@Target**, Java cho phép sử dụng nó trong những ngữ cảnh khai báo được ngôn ngữ xác định theo mặc định; điều đó **không có nghĩa** annotation mặc nhiên được áp dụng cho mọi vị trí **TYPE_USE**.

Với một annotation được thiết kế nghiêm túc, nên khai báo **@Target** tường minh để người dùng biết phạm vi sử dụng và để compiler phát hiện chỗ đặt sai.

### Không đặt trùng ElementType

~~~java
// Ví dụ KHÔNG hợp lệ:
// @Target({ElementType.TYPE, ElementType.TYPE})
// @interface InvalidTarget {}
~~~

Các giá trị **ElementType** trong khai báo target không được lặp lại.

## 12. TYPE, TYPE_PARAMETER và TYPE_USE khác nhau thế nào?

Ba mục này dễ bị nhầm vì đều liên quan tới kiểu dữ liệu.

**TYPE** hướng tới *khai báo một kiểu*:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface ServiceType {}

@ServiceType
class TaskService {}
~~~

**TYPE_PARAMETER** hướng tới *khai báo một tham số kiểu*, ví dụ T trong class generic:

~~~java
@Target(ElementType.TYPE_PARAMETER)
@interface TypeParameterNote {}

class Repository<@TypeParameterNote T> {}
~~~

**TYPE_USE** hướng tới *vị trí sử dụng kiểu*, kể cả một type argument:

~~~java
@Target(ElementType.TYPE_USE)
@interface TypeUseNote {}

class Example {
    java.util.List<@TypeUseNote String> names;
}
~~~

Một annotation target **TYPE_USE** có thể áp dụng tại nhiều vị trí không phải khai báo class; còn **TYPE_PARAMETER** biểu diễn rõ ý định gắn lên chính tham số generic.

### TYPE_USE không tự thực thi kiểm tra null

Ví dụ:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface RequiredValue {}

class Customer {
    java.util.List<@RequiredValue String> names;
}
~~~

Annotation **@RequiredValue** không tự ngăn một phần tử null được thêm vào danh sách. Để áp dụng ràng buộc như vậy, ứng dụng phải có trình kiểm tra, công cụ phân tích hoặc mã runtime thực sự hiểu annotation.

Java không cung cấp một annotation dựng sẵn phổ quát khiến mọi vị trí được gắn nhãn tự động trở thành non-null trong quá trình thực thi.

## 13. Annotation dùng với record component

**ElementType.RECORD_COMPONENT** hỗ trợ gắn metadata lên component của record.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface FieldLabel {
    String value();
}

record Employee(
        @FieldLabel("employee_id") long id,
        @FieldLabel("full_name") String name
) {}
~~~

Có thể lấy component qua reflection:

~~~java
for (var component : Employee.class.getRecordComponents()) {
    FieldLabel label = component.getAnnotation(FieldLabel.class);

    if (label != null) {
        System.out.println(component.getName() + " -> " + label.value());
    }
}
~~~

Kết quả:

~~~text
id -> employee_id
name -> full_name
~~~

Record component có những quy tắc về cách một số annotation được lan truyền tới field, accessor hoặc constructor parameter được sinh tự động **nếu target cho phép**. Vì vậy, cần xác định rõ consumer sẽ đọc annotation ở **record component**, field, method hay parameter. Đừng mặc định mọi annotation đều hiện diện tại tất cả những vị trí đó.

Trong ví dụ, annotation chỉ target **RECORD_COMPONENT** nên chúng ta đọc trực tiếp từ **RecordComponent**.

## 14. Đọc annotation bằng reflection

Với annotation có **RetentionPolicy.RUNTIME**, có thể dùng những API như:

- **getAnnotation(AnnotationType.class)**: lấy một annotation phù hợp hoặc **null**.
- **isAnnotationPresent(AnnotationType.class)**: kiểm tra sự hiện diện theo hợp đồng của phần tử.
- **getDeclaredAnnotation(...)**: tìm annotation khai báo trực tiếp trên phần tử tương ứng.
- **getAnnotations()** và **getDeclaredAnnotations()**: lấy các annotation theo quy tắc tương ứng.
- **getAnnotationsByType(...)**: hữu ích khi annotation có thể lặp lại.
- **getAnnotatedType()**, **getAnnotatedReturnType()**, **getAnnotatedParameterTypes()**: truy cập metadata trên vị trí sử dụng kiểu.

Các API này thuộc nhóm reflection, bao gồm **java.lang.reflect.AnnotatedElement** và **AnnotatedType**.

### Ví dụ đọc method annotation

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Permission {
    String value();
}

class DataController {
    @Permission("data:read")
    public void read() {}
}

class ReadAnnotationDemo {
    public static void main(String[] args) throws Exception {
        Method method = DataController.class.getMethod("read");

        Permission permission = method.getAnnotation(Permission.class);

        System.out.println(permission.value()); // data:read
    }
}
~~~

Trong ví dụ, **getMethod("read")** tìm phương thức public tương ứng; nếu không tìm thấy, Java có thể ném **NoSuchMethodException**. Cần kiểm tra **permission != null** nếu method không được bảo đảm mang annotation.

### Declaration annotation và type-use annotation không nhất thiết được đọc cùng đường

Annotation đặt trên chính method, class hoặc field và annotation đặt trên **kiểu được dùng** có thể nằm trong những cấu trúc phản chiếu khác nhau.

Ví dụ:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CheckedType {}

class Example {
    java.util.List<@CheckedType String> values;
}

class InspectTypeUse {
    public static void main(String[] args) throws Exception {
        Field field = Example.class.getDeclaredField("values");

        AnnotatedParameterizedType annotated =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedType element =
                annotated.getAnnotatedActualTypeArguments()[0];

        System.out.println(
                element.isAnnotationPresent(CheckedType.class)); // true
    }
}
~~~

Ở đây, **@CheckedType** nằm trên type argument **String**, không phải annotation trực tiếp của field **values**. Vì vậy dùng **field.getAnnotatedType()** thay vì chỉ **field.getAnnotation(CheckedType.class)**.

**RUNTIME retention chỉ làm metadata có thể truy cập bằng những API phù hợp**, không bảo đảm một phương thức reflection bất kỳ đều tìm thấy annotation ở mọi vị trí.

## 15. @Documented: xuất metadata trong tài liệu API

**@Documented** là meta-annotation cho biết những lần sử dụng annotation type nên được đưa vào tài liệu API do công cụ như Javadoc tạo.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@interface PublicContract {}

@PublicContract
class PublicService {}
~~~

Ý nghĩa của **@Documented** liên quan đến **tài liệu**. Nó không làm annotation có retention RUNTIME và không tự tạo kiểm tra logic.

Nếu muốn annotation vừa được tài liệu hóa vừa đọc qua reflection, cần khai báo thêm retention thích hợp:

~~~java
import java.lang.annotation.*;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface VisibleAtRuntime {}
~~~

Các meta-annotation phục vụ mục tiêu khác nhau, nên không thể dùng **@Documented** thay cho **@Retention** hoặc **@Target**.

## 16. @Inherited: kế thừa annotation trên class

**@Inherited** là meta-annotation cho phép một số annotation gắn lên **class** được reflection xem như kế thừa từ superclass khi truy vấn annotation trên lớp con.

~~~java
import java.lang.annotation.*;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

@Category("service")
class BaseService {}

class ReportService extends BaseService {}
~~~

Đọc:

~~~java
Category category = ReportService.class.getAnnotation(Category.class);

System.out.println(category.value()); // service
~~~

**ReportService** không khai báo **@Category** trực tiếp, nhưng truy vấn qua **getAnnotation(...)** có thể tìm annotation trên superclass nhờ hợp đồng **@Inherited**.

Để kiểm tra có được khai báo trực tiếp hay không:

~~~java
Category direct =
        ReportService.class.getDeclaredAnnotation(Category.class);

System.out.println(direct == null); // true
~~~

### Giới hạn quan trọng

**@Inherited**:

- Chỉ áp dụng cho cơ chế kế thừa annotation trên **class**, không biến annotation trên interface thành annotation tự động kế thừa bởi các lớp triển khai.
- Không khiến annotation trên method hoặc field của superclass tự trở thành annotation trên method hoặc field của lớp con.
- Không thay thế quan hệ kế thừa class thông thường.
- Không có ý nghĩa tìm kiếm runtime nếu annotation không được giữ với retention phù hợp.

Nếu class con khai báo annotation của cùng kiểu, khai báo trực tiếp của class con được ưu tiên khi truy vấn tương ứng.

Vì vậy, chỉ gắn **@Inherited** khi semantics metadata thật sự phải đi theo quan hệ superclass. Với các hợp đồng muốn tổng hợp metadata từ interface hoặc nhiều nguồn khác nhau, cần thuật toán truy vấn riêng.

## 17. @Repeatable: cho phép gắn nhiều annotation cùng kiểu

Trong một số trường hợp, một phần tử cần nhiều metadata cùng loại, ví dụ nhiều vai trò hoặc nhiều quy tắc cấu hình.

**@Repeatable** cho phép dùng cùng một annotation type nhiều lần tại một vị trí. Annotation được lặp cần chỉ định một **container annotation type** có phần tử **value()** là mảng của annotation được chứa.

~~~java
import java.lang.annotation.*;

@Repeatable(Roles.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
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
class FileController {}
~~~

Đọc:

~~~java
for (Role role : FileController.class.getAnnotationsByType(Role.class)) {
    System.out.println(role.value());
}
~~~

Kết quả:

~~~text
reader
writer
~~~

### Vì sao có container annotation?

Trong biểu diễn của annotation lặp, Java sử dụng một annotation container phù hợp để lưu những lần xuất hiện cần chứa chung. **getAnnotationsByType(Role.class)** được thiết kế để trả về các annotation cùng kiểu theo quy tắc truy vấn annotation lặp, bao gồm việc xem xét container.

Không nên chỉ dùng **getAnnotation(Role.class)** rồi giả định nó luôn trả đủ các annotation lặp.

### Các ràng buộc cần thiết

Container phải đáp ứng các điều kiện của ngôn ngữ, gồm:

- Có phần tử **value()** trả về mảng đúng annotation được chứa.
- Retention của container tương thích với retention của annotation lặp.
- Target của container đáp ứng các quy tắc tương thích với target của annotation lặp.
- Các meta-annotation liên quan, chẳng hạn **@Inherited**, cũng cần nhất quán khi thiết kế metadata được kế thừa.

Để dùng với reflection ở runtime, trong ví dụ trên cả **Role** và **Roles** đều chọn **RUNTIME**. Việc thiết kế annotation lặp cho API công khai cần ghi rõ ý nghĩa khi người dùng gắn nhiều giá trị hoặc khi container được khai báo tường minh.

## 18. Annotation processor và runtime reflection

Annotation thường xuất hiện trong hai kiểu kiến trúc khác nhau.

### Xử lý tại thời điểm biên dịch

Một annotation processor được tích hợp với trình biên dịch có thể đọc metadata trong source code và hỗ trợ kiểm tra hoặc sinh mã. Những annotation như **@Generated** trong **javax.annotation.processing** có vai trò ghi dấu nguồn được tạo bởi công cụ. Khi cần metadata cho quá trình biên dịch, retention SOURCE có thể đã đủ.

Ví dụ annotation dành cho công cụ kiểm tra:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}

@GenerateAdapter
interface PaymentApi {}
~~~

Đoạn mã **không tự sinh lớp adapter**. Cần một annotation processor được cấu hình và triển khai để đọc **@GenerateAdapter** và thực hiện công việc.

### Xử lý tại thời điểm chạy

Một framework có thể dùng reflection để đọc annotation RUNTIME:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String value();
}

class Controller {
    @Route("/health")
    public String health() {
        return "OK";
    }
}
~~~

Đây chỉ là metadata. Để hoạt động như HTTP endpoint, một chương trình hoặc framework vẫn phải tìm method mang **@Route**, đăng ký route và gọi method theo giao thức của nó.

### Runtime retention không cấp thêm quyền reflection

Việc một annotation được giữ ở runtime **không tự cấp quyền** truy cập private member, vượt qua ranh giới module hoặc vô hiệu hóa cơ chế kiểm soát truy cập.

Nếu chương trình dùng Java Platform Module System (JPMS), khả năng reflection lên phần tử trong các package của module khác phụ thuộc quy tắc **exports**, **opens** và quyền truy cập tương ứng. Đừng dùng **@Retention(RUNTIME)** như một cách “mở khóa” mọi class.

## 19. Ví dụ tổng hợp chạy độc lập

Chương trình sau kết hợp annotation dựng sẵn, retention, target, record component, type-use annotation, annotation lặp và reflection. Toàn bộ được đặt trong một tệp **AnnotationDemo.java** để dễ thử nghiệm.

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class AnnotationDemo {
    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target({ElementType.TYPE, ElementType.METHOD})
    public @interface Endpoint {
        String path();
        String[] methods() default {"GET"};
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @Repeatable(Roles.class)
    public @interface Role {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Roles {
        Role[] value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface CheckedType {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface DisplayName {
        String value();
    }

    @FunctionalInterface
    public interface Action {
        void execute();
    }

    @Endpoint(path = "/items")
    @Role("reader")
    @Role("writer")
    public static final class ItemApi {
        public List<@CheckedType String> names = List.of("A", "B");

        @Endpoint(path = "/items", methods = {"GET", "POST"})
        public void list() {}

        @Override
        public String toString() {
            return "ItemApi";
        }
    }

    public record Item(@DisplayName("item_id") long id) {}

    public static void main(String[] args) throws Exception {
        Endpoint typeEndpoint =
                ItemApi.class.getAnnotation(Endpoint.class);

        System.out.println(typeEndpoint.path());
        System.out.println(Arrays.toString(typeEndpoint.methods()));

        String[] roles = Arrays.stream(
                        ItemApi.class.getAnnotationsByType(Role.class))
                .map(Role::value)
                .toArray(String[]::new);

        System.out.println(Arrays.toString(roles));

        Method method = ItemApi.class.getDeclaredMethod("list");
        Endpoint methodEndpoint =
                method.getAnnotation(Endpoint.class);

        System.out.println(
                Arrays.toString(methodEndpoint.methods()));

        Field field = ItemApi.class.getDeclaredField("names");
        AnnotatedParameterizedType annotated =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        AnnotatedType stringArgument =
                annotated.getAnnotatedActualTypeArguments()[0];

        System.out.println(
                stringArgument.isAnnotationPresent(CheckedType.class));

        var component = Item.class.getRecordComponents()[0];
        DisplayName displayName =
                component.getAnnotation(DisplayName.class);

        System.out.println(displayName.value());

        Action action = () -> System.out.println("Action executed");
        action.execute();
    }
}
~~~

Kết quả:

~~~text
/items
[GET]
[reader, writer]
[GET, POST]
true
item_id
Action executed
~~~

### Các cơ chế trong chương trình

1. **@Endpoint** có retention RUNTIME và target TYPE/METHOD; reflection đọc được metadata cả ở class và method.
2. **methods() default {"GET"}** làm cho **@Endpoint(path="/items")** hợp lệ mà không cần truyền mảng methods.
3. **@Role** được gắn hai lần nhờ **@Repeatable(Roles.class)**; **getAnnotationsByType(...)** lấy cả hai giá trị.
4. **@CheckedType** được gắn lên type argument **String** của **List**. Metadata được đọc từ **AnnotatedParameterizedType**, không phải annotation trực tiếp của field.
5. **@DisplayName** target RECORD_COMPONENT và được đọc từ **RecordComponent**.
6. **@FunctionalInterface** kiểm tra **Action** có hợp đồng SAM phù hợp với lambda.
7. **@Override** kiểm tra method **toString()** ghi đè một method hợp lệ của **Object**.
8. Dù có nhiều annotation, ứng dụng chỉ thực hiện các hành vi được viết rõ trong **main()**. Metadata không tự tạo API HTTP, phân quyền hay validation.

Khi phát triển một framework thật, nên thiết kế chính sách khi annotation vắng mặt, khi phương thức không truy cập được qua reflection, khi có nhiều annotation trùng hoặc khi class được tải từ module khác.

## 20. Những nhầm lẫn và lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| **getAnnotation(...)** trả null dù annotation có trong source | Annotation dùng SOURCE/CLASS retention hoặc truy vấn sai phần tử | Đặt RUNTIME nếu thật sự cần reflection; kiểm tra đúng đối tượng phản chiếu |
| Annotation không đặt được lên method | **@Target** không có METHOD | Điều chỉnh target theo đúng hợp đồng thiết kế |
| Annotation đặt được lên field nhưng không đọc thấy ở type argument | FIELD và TYPE_USE là hai vị trí khác nhau | Dùng target TYPE_USE và đọc bằng API **AnnotatedType** |
| Đánh dấu **@Required** nhưng null vẫn được truyền vào | Annotation tùy chỉnh không có logic kiểm tra | Có validator hoặc kiểm tra đầu vào thực sự |
| **@Override** báo lỗi | Không ghi đè đúng chữ ký hoặc method không được phép override | Sửa chữ ký và xem lại quy tắc kế thừa |
| **@FunctionalInterface** báo lỗi | Interface không đáp ứng điều kiện một abstract method | Kiểm tra các abstract method độc lập |
| **@SuppressWarnings** không xử lý ClassCastException | Bỏ cảnh báo không sửa lỗi kiểu | Loại bỏ thao tác unchecked nguy hiểm |
| Dùng **@SafeVarargs** để che thao tác gây heap pollution | Annotation chỉ là cam kết, không chứng minh an toàn | Rà soát mảng varargs và bảo vệ tính an toàn kiểu |
| Quên khai báo **@Retention** | Mặc định CLASS, không phải RUNTIME | Khai báo RUNTIME khi reflection là yêu cầu |
| Dùng **@Documented** rồi mong reflection đọc được | @Documented điều khiển xuất tài liệu, không phải retention | Khai báo @Retention phù hợp |
| Mong annotation trên interface tự xuất hiện ở class triển khai | @Inherited không áp dụng theo interface theo cách đó | Truy vấn interface nếu hợp đồng yêu cầu |
| Mong annotation trên method cha tự “kế thừa” khi override | @Inherited chỉ có quy tắc dành cho class annotations | Thiết kế thuật toán tìm annotation trên hierarchy của method |
| Dùng **getAnnotation(...)** cho annotation lặp rồi thiếu giá trị | Chưa xử lý container của @Repeatable | Dùng **getAnnotationsByType(...)** |
| Dùng annotation cho framework mà chưa cấu hình processor/runtime | Annotation không có hiệu ứng tự động | Cài đặt và cấu hình consumer của metadata |
| Framework không đọc được private member | Giới hạn truy cập/JPMS không phụ thuộc retention | Thiết kế API reflection và cấu hình module phù hợp |

## 21. Checklist thiết kế và sử dụng annotation

Trước khi định nghĩa một annotation mới hoặc đưa annotation vào API công khai, hãy kiểm tra:

- Annotation phục vụ trình biên dịch, công cụ xử lý bytecode hay mã runtime?
- Đã chọn **RetentionPolicy.SOURCE**, **CLASS** hoặc **RUNTIME** đúng mục đích chưa?
- Có đang ngầm dựa vào retention mặc định CLASS mà lại cần reflection không?
- Đã khai báo **@Target** đúng các vị trí cần hỗ trợ, kể cả TYPE_USE, TYPE_PARAMETER hoặc RECORD_COMPONENT nếu có không?
- Các phần tử annotation có dùng kiểu dữ liệu được Java cho phép không?
- Những phần tử bắt buộc và giá trị default có rõ ràng với người sử dụng không?
- Có nhầm metadata với validation hoặc hành vi tự động không?
- Nếu cần tài liệu API, có nên dùng **@Documented** không?
- Nếu muốn kế thừa metadata, các giới hạn của **@Inherited** có phù hợp không?
- Nếu có thể lặp annotation, container **@Repeatable** đã có đúng target, retention và phương thức value chưa?
- Nếu dùng runtime reflection, đã đọc đúng declaration annotation hay type-use annotation chưa?
- Với Java module, có bảo đảm consumer đủ quyền truy cập cần thiết không?
- Có dùng **@Override**, **@FunctionalInterface** để compiler phát hiện sai sót hợp đồng không?
- Có tránh lạm dụng **@SuppressWarnings** và **@SafeVarargs** chỉ để che cảnh báo không?
- Có tránh tạo annotation mới khi một kiểu dữ liệu, interface hoặc method rõ ràng đã diễn đạt đủ yêu cầu không?

## Kết luận

**Annotation dựng sẵn** như **@Override**, **@Deprecated**, **@SuppressWarnings**, **@SafeVarargs** và **@FunctionalInterface** cung cấp những hợp đồng với trình biên dịch và công cụ Java. Với annotation tùy chỉnh, **@Retention** quyết định metadata được giữ tới giai đoạn nào; **@Target** xác định nơi đặt annotation hợp lệ. Những meta-annotation khác như **@Documented**, **@Inherited** và **@Repeatable** bổ sung các quy tắc về tài liệu, tìm kiếm metadata theo quan hệ class và lặp annotation.

Trong Java 27, hãy thiết kế annotation theo **người hoặc công cụ sẽ tiêu thụ metadata**, không chỉ theo cú pháp viết **@Name**. RUNTIME retention không tự thực hiện validation, TYPE_USE không tự bảo đảm non-null, và @Inherited không biến mọi quan hệ kế thừa thành một hệ thống truyền metadata tự động. Khi phân biệt rõ **khai báo, lưu giữ, truy xuất và diễn giải annotation**, API trở nên dễ hiểu, ít phụ thuộc vào giả định ngầm và dễ duy trì hơn.
