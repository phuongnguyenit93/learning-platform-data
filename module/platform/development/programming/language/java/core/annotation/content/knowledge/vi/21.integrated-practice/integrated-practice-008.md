# Bảng tổng kết lựa chọn annotation và câu hỏi tự đánh giá

## 1. Mục tiêu và cách sử dụng

Bài thực hành tổng hợp này giúp bạn **quyết định dùng annotation nào, đặt ở đâu, giữ lại đến giai đoạn nào và ai thực sự đọc nó**, sau đó tự kiểm tra khả năng lý giải quyết định ấy. Phạm vi là Java core annotation trên Java 17 trở lên: annotation có sẵn trong Java, annotation tự định nghĩa, meta-annotation, reflection và annotation processing ở mức lựa chọn công cụ. Không cần framework bên ngoài.

Sau khi học, bạn nên tự trả lời được bốn câu:

1. **Ai tiêu thụ metadata?** Java compiler, annotation processor, công cụ đọc class file hay chương trình đang chạy?
2. **Metadata xuất hiện ở đâu?** Khai báo class, method, field, constructor, parameter, record component, type parameter hay vị trí sử dụng kiểu?
3. **Cần giữ metadata bao lâu?** Chỉ source, trong .class, hay phải nhìn thấy từ runtime reflection?
4. **Một annotation đã đủ chưa?** Có cần lập tài liệu API, kế thừa trên lớp con, lặp nhiều lần, hay cần chính chương trình viết logic xử lý?

**Nguyên tắc:** Annotation chủ yếu mô tả metadata. Việc một annotation thật sự tạo ra kiểm tra, sinh mã hoặc thay đổi hành vi tùy thuộc compiler, processor, runtime/framework hoặc code của bạn có chủ động xử lý nó hay không. Thêm một annotation tự định nghĩa lên method **không** tự thực thi validation, dependency injection, logging hay transaction.

## 2. Bảng tổng kết nhanh: chọn annotation có sẵn

| Nhu cầu | Annotation phù hợp | Phạm vi/ý nghĩa | Lưu ý lựa chọn |
| --- | --- | --- | --- |
| Kiểm tra method thực sự override hoặc implement method cấp trên | **@Override** | Compiler kiểm tra khai báo method | Không mang ý nghĩa để runtime tự gọi method |
| Đánh dấu API đã lỗi thời hoặc không nên tiếp tục dùng | **@Deprecated** | Compiler/công cụ hiển thị cảnh báo; API có thể thêm **since**, **forRemoval** | Cần giải thích thay thế trong Javadoc; không tự chặn lời gọi |
| Giảm cảnh báo compiler đã được xem xét | **@SuppressWarnings** | Trên khai báo phù hợp, ví dụ **"unchecked"** hoặc **"deprecation"** | Giới hạn phạm vi nhỏ nhất; không chữa nguyên nhân gây warning |
| Xác nhận interface được thiết kế làm functional interface | **@FunctionalInterface** | Compiler bảo đảm có đúng một abstract method theo quy tắc functional interface | Không bắt buộc mới dùng được lambda |
| Cam kết method/constructor varargs không thực hiện thao tác mất an toàn theo hợp đồng của annotation | **@SafeVarargs** | Giảm cảnh báo liên quan heap pollution khi đủ điều kiện sử dụng | Chỉ dùng khi triển khai thật sự an toàn; áp dụng được cho static/final method, constructor, và private instance method từ Java 9 |
| Cho compiler/processor hoặc công cụ build một tín hiệu nghiệp vụ riêng | **@YourCustomAnnotation** | Do bạn khai báo và viết bên tiêu thụ | Xác định rõ @Retention, @Target, quy tắc xử lý |

**Nhận xét:** @Override, @SuppressWarnings, @Deprecated, @FunctionalInterface và @SafeVarargs là các annotation tiêu chuẩn với ý nghĩa được Java định nghĩa. Tự đặt tên **@OverrideLike** không tạo ra kiểm tra override tương tự; muốn có kiểm tra riêng phải xây processor hoặc công cụ phân tích.

## 3. Bảng quyết định cho annotation tự định nghĩa

### 3.1. Chọn @Retention theo nơi annotation được đọc

| Nhu cầu cụ thể | RetentionPolicy | Còn trong .class sau biên dịch? | Thông thường nhìn thấy qua runtime reflection? |
| --- | --- | --- | --- |
| Chỉ hỗ trợ kiểm tra/sinh mã ở thời điểm đọc source bởi compiler/annotation processor | **SOURCE** | Không | Không |
| Để công cụ phân tích/biến đổi bytecode đọc class file; chương trình không cần reflection | **CLASS** | Có | Không |
| Dùng **getAnnotation**, **getAnnotationsByType**, quét runtime hay cấu hình động | **RUNTIME** | Có | Có, khi đọc đúng phần tử và annotation hợp lệ |

Nếu **không ghi @Retention**, chính sách mặc định là **CLASS**. Đừng lựa chọn theo cảm tính “RUNTIME linh hoạt hơn”; metadata runtime tăng mức phụ thuộc và yêu cầu có logic tiêu thụ. Tuy vậy, nếu mục tiêu thật sự là reflection thì phải dùng **RUNTIME**.

Một annotation với **SOURCE** vẫn có thể được annotation processor xử lý lúc biên dịch. Không nên suy ra rằng *mọi* processor bắt buộc dùng SOURCE: processor có thể xử lý annotation được khai báo với chính sách retention khác khi annotation xuất hiện trong nguồn đầu vào.

### 3.2. Chọn @Target theo nơi gắn annotation

| ElementType | Vị trí thường gặp | Ví dụ ý định |
| --- | --- | --- |
| **TYPE** | Class, interface, enum, annotation type, record declaration | Đánh dấu vai trò một kiểu |
| **ANNOTATION_TYPE** | Khai báo một annotation type | Meta-annotation cho annotation tự định nghĩa |
| **METHOD** | Khai báo method | Metadata vận hành cho method |
| **FIELD** | Khai báo field | Quy tắc xử lý hoặc ánh xạ field |
| **CONSTRUCTOR** | Khai báo constructor | Chọn cách khởi tạo |
| **PARAMETER** | Khai báo tham số | Quy tắc áp cho tham số |
| **LOCAL_VARIABLE** | Khai báo biến cục bộ | Đánh dấu phục vụ compiler/công cụ phân tích; reflection thông thường không cho truy xuất local variables |
| **TYPE_PARAMETER** | Khai báo biến kiểu như **T** trong generic | Metadata gắn với generic type parameter |
| **TYPE_USE** | Chỗ sử dụng kiểu, như **List<@NonNull String>** | Phân tích tính đúng đắn theo vị trí sử dụng kiểu; bản thân annotation không tự kiểm tra null |
| **RECORD_COMPONENT** | Thành phần của record | Gắn metadata trực tiếp lên record component |
| **PACKAGE**, **MODULE** | Khai báo package/module | Mô tả metadata phạm vi package/module |

Ví dụ: nếu chỉ chấp nhận method, viết **@Target(ElementType.METHOD)**; nếu chấp nhận cả class và method, viết **@Target({ElementType.TYPE, ElementType.METHOD})**. Không khai báo @Target sẽ khiến annotation áp dụng rộng lên các ngữ cảnh khai báo thích hợp; một @Target rõ ràng thường giúp compiler ngăn dùng sai vị trí. Không mặc định **TYPE** đồng nghĩa **TYPE_USE**: một annotation dành cho *khai báo lớp* không tự động là annotation dành cho *kiểu của biến hoặc biểu thức*.

### 3.3. Các meta-annotation bổ sung

| Muốn có tính chất | Sử dụng | Điều kiện/giới hạn thiết yếu |
| --- | --- | --- |
| Annotation xuất hiện trong Javadoc của phần tử được chú thích | **@Documented** trên khai báo annotation | Không thay đổi retention hay hành vi runtime |
| Annotation kiểu lớp có thể được tìm thấy trên subclass nhờ cơ chế kế thừa của reflection | **@Inherited** | Chỉ có ý nghĩa với annotation trên **class**; không kế thừa từ interface hay tự chuyển annotation method/field xuống subclass |
| Cho phép cùng một annotation xuất hiện nhiều lần tại cùng vị trí | **@Repeatable(Container.class)** | Container có phần tử **value()** trả về mảng annotation lặp; retention và target của container phải phù hợp |
| Đặt giá trị mặc định cho một element | **default** trong phương thức khai báo element | Có thể bỏ qua element đó khi dùng annotation; default không phải null |
| Chọn form ngắn cho annotation có một element tên **value** | **@Tag("x")** | Tương đương **@Tag(value = "x")** |
| Annotation chỉ đóng vai trò cờ, không có element | Annotation dạng marker | Dùng **@Marker** hoặc **@Marker()** |

**Lưu ý @Inherited:** **Child.class.getAnnotation(Tag.class)** có thể thấy annotation của superclass nếu Tag có @Inherited. Ngược lại, **getDeclaredAnnotation(Tag.class)** chỉ xét annotation khai báo trực tiếp trên Child; annotation trên interface hoặc method cấp trên không tự xuất hiện vì @Inherited.

**Lưu ý @Repeatable:** Một annotation được lặp có thể được chứa gián tiếp trong container ở class file. Để đọc mọi giá trị lặp, thường chọn **getAnnotationsByType(Repeated.class)** thay vì tự giả định **getAnnotation(Repeated.class)** trả đủ mọi giá trị.

### 3.4. Kiểu element hợp lệ và giới hạn

Mỗi element của annotation là một phương thức **không tham số**, với kiểu trả về thuộc nhóm sau: primitive, String, Class hoặc Class được parameterize phù hợp, enum, annotation, hoặc **mảng một chiều** của những kiểu này. Giá trị cung cấp phải đáp ứng quy tắc compile-time constant phù hợp với kiểu (ví dụ primitive/String), class literal, enum constant hoặc annotation value.

Không khai báo element kiểu **List<String>**, **Map**, kiểu đối tượng tùy ý, mảng nhiều chiều; không dùng **null** làm giá trị hoặc default. Nếu thuộc tính tùy chọn, hãy chọn default có ý nghĩa và xử lý rõ giá trị đó trong consumer. Với thành phần kiểu **Class<?>**, cú pháp dùng trong annotation thường là **SomeType.class**, không phải một đối tượng tạo bằng **new**.

Ví dụ khai báo hợp lệ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceInfo {
    String name();
    int priority() default 0;
    Class<?> implementation() default Object.class;
    String[] tags() default {};
}
~~~

Ví dụ sử dụng: **@ServiceInfo(name = "catalog", priority = 2, tags = {"api", "core"})** trên một class. Nếu thiếu **name**, trình biên dịch báo lỗi vì element bắt buộc chưa được cung cấp.

## 4. Luồng quyết định sáu bước trước khi viết annotation

1. **Mô tả yêu cầu bằng động từ:** “compiler cảnh báo”, “processor sinh source”, “runtime quét method” hoặc “công cụ bytecode đọc metadata”. Nếu mục tiêu đạt được bằng annotation chuẩn thì ưu tiên annotation chuẩn.
2. **Xác định người đọc thật sự.** Nếu chưa có processor/reflection consumer thì custom annotation chỉ là dữ liệu; viết consumer hoặc bỏ annotation thừa.
3. **Chọn retention theo nơi tiêu thụ:** SOURCE cho thông tin chỉ phục vụ compile; CLASS cho phân tích class file; RUNTIME cho Java reflection/runtime scanning.
4. **Giới hạn target:** ví dụ METHOD cho kiểm tra method, TYPE_USE cho kiểm tra vị trí sử dụng kiểu, RECORD_COMPONENT cho cấu phần record.
5. **Xác định hình thái dữ liệu:** marker nếu chỉ cần cờ; có element nếu cần tham số; default cho trường tùy chọn; @Repeatable nếu thật sự muốn nhiều bản trên một phần tử.
6. **Kiểm tra hành vi đọc, tính đúng đắn và tiến hóa API:** @Inherited có cần và có áp dụng không, @Documented có cần không, element đổi tên/default ảnh hưởng gì, processor có tạo file trùng không, runtime có tìm đúng annotation không.

Câu hỏi đánh giá quyết định cuối cùng: **“Nếu bỏ annotation đi, bộ phận nào của chương trình sẽ phát hiện hoặc thay đổi hành vi?”** Nếu câu trả lời không chỉ ra consumer cụ thể, cần xem lại động cơ thêm annotation.

## 5. Ví dụ Java 17+: runtime, repeatable, inherited và SOURCE

Ví dụ hoàn chỉnh bên dưới minh họa ba quyết định song song:

- **ModuleTag** có @Retention(RUNTIME), @Target(TYPE), @Inherited: metadata runtime trên class cha được reflection thấy ở class con.
- **Rule** là annotation METHOD lặp lại được, container **Rules** có retention/target tương thích.
- **ReviewAtCompile** có @Retention(SOURCE): compiler có thể đọc ở source nhưng reflection runtime không thấy.

Đặt toàn bộ mã trong một tệp **AnnotationChoiceLab.java** ở thư mục làm việc:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Inherited
@interface ModuleTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@Repeatable(Rules.class)
@interface Rule {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Rules {
    Rule[] value();
}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@interface ReviewAtCompile {
}

@ModuleTag("core")
class ParentService {
}

class ChildService extends ParentService {
    @Rule("notBlank")
    @Rule("maxLength")
    @ReviewAtCompile
    public void execute() {
    }
}

public class AnnotationChoiceLab {
    public static void main(String[] args) throws NoSuchMethodException {
        ModuleTag tag = ChildService.class.getAnnotation(ModuleTag.class);
        Method method = ChildService.class.getDeclaredMethod("execute");
        Rule[] rules = method.getAnnotationsByType(Rule.class);

        System.out.println("module=" + tag.value());
        System.out.println("declaredModule=" +
                (ChildService.class.getDeclaredAnnotation(ModuleTag.class) != null));
        System.out.println("ruleCount=" + rules.length);
        System.out.println("rule0=" + rules[0].value());
        System.out.println("rule1=" + rules[1].value());
        System.out.println("reviewVisible=" +
                method.isAnnotationPresent(ReviewAtCompile.class));
    }
}
~~~

Biên dịch/chạy trên **Java 17+** từ thư mục chứa tệp:

~~~bash
javac -d out AnnotationChoiceLab.java
java -cp out AnnotationChoiceLab
~~~

Stdout chính xác:

~~~text
module=core
declaredModule=false
ruleCount=2
rule0=notBlank
rule1=maxLength
reviewVisible=false
~~~

**Giải thích kết quả:**

- **module=core**: runtime tìm được ModuleTag kế thừa từ ParentService nhờ **@Inherited**.
- **declaredModule=false**: ChildService không tự khai báo ModuleTag.
- **ruleCount=2**, **rule0**, **rule1**: hai Rule trên một method được đọc thành hai annotation theo thứ tự khai báo bằng **getAnnotationsByType**.
- **reviewVisible=false**: @Retention(SOURCE) không để lại annotation cho runtime reflection.
- **Quan trọng:** Không có logic thực thi notBlank hoặc maxLength trong ví dụ này. Hai chuỗi trên chỉ là metadata; muốn validation thật, bạn phải viết code đọc Rule và áp dụng quy tắc.

Để quan sát chi tiết class file:

~~~bash
javap -v -p -classpath out ChildService
~~~

Bạn có thể thấy **RuntimeVisibleAnnotations** hoặc container do compiler mã hóa; kết quả trình bày chi tiết phụ thuộc phiên bản JDK. **ReviewAtCompile** không có trong class file vì có retention SOURCE. Lưu ý một số JVM/compiler có thể trình bày tên container khác với dạng mà reflection trả về qua **getAnnotationsByType**.

Nếu cần minh họa target cho record, ví dụ riêng dưới đây chỉ minh họa cú pháp khai báo, không kèm consumer:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DisplayName {
    String value();
}

record Customer(@DisplayName("Customer ID") String id) {
}
~~~

Trong ứng dụng thật, đọc annotation trên **RecordComponent** bằng reflection nếu annotation có target và retention tương ứng, hoặc qua công cụ biên dịch. Record component khác một field thông thường ở mức API phản chiếu và khái niệm khai báo.

## 6. Bảng lựa chọn theo tình huống thực tế

| Tình huống | Lựa chọn gợi ý | Vì sao? | Sai lầm dễ gặp |
| --- | --- | --- | --- |
| Muốn javac phát hiện viết nhầm tên method override | @Override | Compiler tự biết luật override | Tự tạo annotation rồi mong javac hiểu |
| Interface dùng cho lambda, muốn compiler ràng buộc số abstract method | @FunctionalInterface | Kiểm tra hợp đồng SAM | Nghĩ annotation là điều kiện bắt buộc để viết lambda |
| API cũ cần cảnh báo người dùng | @Deprecated, Javadoc về API thay thế | Đánh dấu vòng đời API | Nghĩ Java cấm gọi method deprecated |
| Suppress một warning unchecked đã được kiểm toán | @SuppressWarnings("unchecked") tại phạm vi nhỏ | Compiler hiểu cảnh báo cụ thể | Suppress cả class để che lỗi khác |
| Annotation processor sinh mã từ class đánh dấu | Custom @Target(TYPE), thường SOURCE và processor | Compiler/processor đọc khi biên dịch | Quên viết và đăng ký processor |
| Công cụ ngoài runtime đọc annotation attributes trong .class | Custom CLASS có @Target phù hợp | Giữ metadata ở bytecode | Dùng SOURCE rồi tìm trong JAR |
| Chương trình lúc chạy chọn handler từ annotation method | Custom RUNTIME + METHOD + reflection consumer | Runtime cần truy xuất metadata method | Dùng CLASS rồi mong getAnnotation tìm ra |
| Muốn annotation có mặt trong Javadoc của phần tử | @Documented trên annotation type | Javadoc hiển thị metadata | Nhầm @Documented với @Retention(RUNTIME) |
| Lớp con được tra cứu annotation class cha bằng Class.getAnnotation | @Inherited với TYPE và RUNTIME | Reflection có quy tắc kế thừa annotation trên class | Mong annotation từ interface hoặc method cũng tự kế thừa |
| Một method khai báo nhiều quy tắc cùng kiểu | @Repeatable với container và getAnnotationsByType | Cho phép nhiều lần dùng trên một phần tử | Quên container/retention/target phù hợp |
| Phân tích kiểu trong List<@NonNull String> | @Target(TYPE_USE) và tool hiểu annotation | Metadata gắn đúng vị trí type use | Nghĩ annotation tự thêm kiểm tra null |
| Metadata nằm trên thành phần record | @Target(RECORD_COMPONENT), retention theo consumer | Xác định đúng declaration context | Nhầm record component với mọi field cùng tên |
| Tham số cấu hình annotation có giá trị mặc định | Element với **default** | Giảm bắt buộc nhập giá trị | Dùng null hoặc kiểu List làm element |
| Build báo **FilerException** | Kiểm tra tên file tạo, processor và các round | Thường liên quan yêu cầu tạo output trùng hoặc không hợp lệ | Đổi tên bằng timestamp để né va chạm |
| Runtime báo **AnnotationFormatError** | Kiểm tra class/JAR đang nạp, metadata bytecode và công cụ transform | Liên quan phân tích dữ liệu annotation trong class file | Sửa ngẫu nhiên @Target hoặc xóa source khi chưa xác minh artifact |

Bảng trên đưa ra **quyết định ban đầu**. Mỗi dự án còn phải cân nhắc nơi đặt processor, class loader, module boundary và hợp đồng riêng của thư viện tiêu thụ.

## 7. Bài tập thực hành tổng hợp

### Bài tập A — Thiết kế annotation theo yêu cầu

Một công cụ lúc biên dịch đọc annotation trên class **@GenerateDto**, lấy hậu tố tên class mặc định là "Dto" rồi tạo source mới. Không có chức năng runtime reflection.

**Hãy chọn** retention, target, element/default, và chỉ rõ ai xử lý. Sau đó cho biết vì sao không cần RUNTIME.

Gợi ý để tự làm trước khi đọc đáp án: tên hậu tố là String hợp lệ cho annotation element; tính đúng của tên file sinh ra phụ thuộc quy tắc Filer.

### Bài tập B — Khai báo lặp nhiều điều kiện

Một method có hai quy tắc tên **"nonEmpty"** và **"maxLength"**. Runtime cần đọc cả hai bằng reflection và thực thi validation tương ứng.

**Hãy liệt kê** retention, target, repeatable/container, API reflection sẽ dùng; thêm một câu giải thích annotation tự thân đã đủ để validation chạy hay chưa.

### Bài tập C — Đọc annotation trên subclass

Có **@Flag** đặt trên interface **BaseApi** và class **Impl implements BaseApi**. Flag khai báo @Inherited, @Retention(RUNTIME), @Target(TYPE). **Impl.class.getAnnotation(Flag.class)** có tự trả Flag đó không? Nếu chuyển Flag từ interface sang superclass trực tiếp của Impl thì sao?

### Bài tập D — Xác định lỗi giai đoạn

Pipeline: javac chạy processor sinh source, sau đó một bytecode tool sửa class; unit test bắt đầu quét annotation và ném **AnnotationFormatError**. Đội ngũ đề nghị xóa generated source và tắt processor.

**Hãy đề xuất** chuỗi kiểm tra có bằng chứng để tìm lỗi thực sự. Nếu thay vào đó javac báo **FilerException**, bạn sẽ đổi điểm điều tra đầu tiên ra sao?

## 8. Bộ câu hỏi tự đánh giá (tự trả lời trước khi mở đáp án)

### Phần 1 — Trắc nghiệm

**Câu 1.** Một custom annotation chỉ được đọc qua reflection khi ứng dụng đã khởi động. Retention nào cần có?

A. SOURCE · B. CLASS · C. RUNTIME · D. Bất kỳ retention nào.

**Câu 2.** Nếu không khai báo @Retention cho annotation tự định nghĩa, retention mặc định là gì?

A. SOURCE · B. CLASS · C. RUNTIME · D. Không có annotation nào được biên dịch.

**Câu 3.** Muốn khai báo annotation chỉ hợp lệ trên method, cần:

A. @Target(METHOD) · B. @Retention(METHOD) · C. @Documented · D. @Inherited.

**Câu 4.** Phát biểu nào đúng về @Inherited?

A. Tự chuyển annotation từ interface sang mọi implementation.  
B. Tự chuyển annotation từ method cha sang method override.  
C. Cho phép Class API tìm annotation phù hợp từ superclass trên class con theo quy tắc kế thừa.  
D. Bắt buộc mọi subclass phải ghi lại annotation.

**Câu 5.** Để dùng cùng một @Rule nhiều lần trên một method, lựa chọn phù hợp nhất là:

A. @SuppressWarnings · B. @Repeatable và container tương ứng · C. @SafeVarargs · D. @Override.

**Câu 6.** Annotation SOURCE có thể được annotation processor đọc trong lúc xử lý mã nguồn không?

A. Không bao giờ · B. Có · C. Chỉ khi có @Inherited · D. Chỉ khi có @Documented.

**Câu 7.** Muốn gắn annotation vào chỗ dùng kiểu **List<@Checked String>**, target chính là:

A. FIELD · B. PARAMETER · C. TYPE · D. TYPE_USE.

**Câu 8.** Annotation nào cung cấp kiểm tra compile-time với method dự định override?

A. @Override · B. @Deprecated · C. @Documented · D. @Repeatable.

**Câu 9.** Cặp nào đúng về lỗi?

A. FilerException luôn là lỗi runtime reflection; AnnotationFormatError luôn là lỗi javac.  
B. FilerException liên quan Filer trong annotation processing; AnnotationFormatError liên quan định dạng metadata annotation khi runtime phân tích.  
C. Cả hai đều chỉ do thiếu @Target.  
D. Cả hai đều được sửa hoàn toàn bằng @Retention(RUNTIME).

**Câu 10.** Annotation định nghĩa **String name(); int level() default 1;**. Cách dùng nào hợp lệ trên một class đúng target?

A. @Label() khi chưa có name.  
B. @Label(name = "demo") và dùng level mặc định.  
C. @Label(name = null).  
D. @Label(name = new String("demo")).

### Phần 2 — Đúng/sai, giải thích một câu

**Câu 11.** “Chỉ cần viết @Audit trên method là Java tự động log mọi lần gọi method.”

**Câu 12.** “@Documented làm annotation được giữ lại cho reflection runtime.”

**Câu 13.** “Một annotation có retention CLASS có thể tồn tại trong .class dù Class.getAnnotation không trả về nó.”

**Câu 14.** “@FunctionalInterface là điều kiện bắt buộc để interface có thể dùng lambda.”

**Câu 15.** “Suppress toàn bộ warning ở cấp class luôn tốt hơn suppress một biểu thức/method cụ thể.”

**Câu 16.** “@Repeatable biến việc đọc nhiều annotation bằng getAnnotationsByType trở thành cách tiếp cận hữu ích.”

**Câu 17.** “Annotation element có thể trả về một đối tượng Map<String, String> để lưu cấu hình tùy ý.”

**Câu 18.** “Một processor tránh tạo lặp cùng tên trong chính nó thì chắc chắn không thể gặp FilerException.”

### Phần 3 — Trả lời ngắn và dự đoán

**Câu 19.** Vì sao kết quả ví dụ ở mục 5 có **declaredModule=false** nhưng **module=core**?

**Câu 20.** Vì sao **reviewVisible=false** mặc dù @ReviewAtCompile được ghi rõ trên method trong source?

**Câu 21.** Với hai @Rule trên method, nên dùng API reflection nào để lấy đủ cả hai và vì sao?

**Câu 22.** Nêu ba câu hỏi chẩn đoán đầu tiên khi thấy FilerException ở build.

**Câu 23.** Nêu ba bằng chứng đầu tiên cần thu thập khi gặp AnnotationFormatError sau một bước bytecode instrumentation.

**Câu 24.** Thiết kế **@EndpointPermission("admin")** được runtime kiểm tra trên method: viết retention, target, element cần thiết; chỉ rõ logic nào còn phải tự viết.

## 9. Đáp án có giải thích

### Đáp án bài tập tình huống

**A.** Chọn custom annotation có **@Target(TYPE)**, **@Retention(SOURCE)**; khai báo **String suffix() default "Dto";**. Processor trong javac đọc annotation rồi tạo source theo qualified name ổn định. Không có runtime consumer nên không cần lưu vào bytecode để reflection; SOURCE đủ cho nhu cầu compile-time. Processor phải tránh tên output trùng qua round và với processor khác.

**B.** Chọn @Retention(RUNTIME), @Target(METHOD) trên @Rule và container; đặt **@Repeatable(Rules.class)**, khai báo **Rule[] value()** trong @Rules, retention/target container tương thích. Reflection đọc **method.getAnnotationsByType(Rule.class)**. Cần riêng code kiểm tra nonEmpty/maxLength; annotation chỉ mô tả quy tắc.

**C.** **Không**. @Inherited không giúp class nhận annotation từ interface do interface khai báo. Khi Flag được đặt trên superclass class thật và áp dụng đúng TYPE/RUNTIME/@Inherited, **Impl.class.getAnnotation(Flag.class)** có thể trả annotation kế thừa, miễn Impl không có annotation cùng kiểu trực tiếp thay thế cơ chế tìm kiếm.

**D.** Giữ stack trace và artifact; xác định class/JAR thực nạp, chạy **javap -v -p** để xem annotation attributes, so sánh class trước/sau bytecode tool, thử tắt riêng bước transform và chạy lại test reflection. Không mặc định processor là thủ phạm. Nếu lỗi là **FilerException** ngay tại javac, bắt đầu từ **tên đầu ra, processor nào tạo, round nào và file/source đầu vào nào trùng**; ghi log trước mỗi createSourceFile/createResource.

### Đáp án trắc nghiệm

| Câu | Đáp án | Lý do |
| --- | --- | --- |
| 1 | **C** | Runtime reflection đòi RUNTIME retention. |
| 2 | **B** | Mặc định là CLASS, không phải RUNTIME. |
| 3 | **A** | @Target xác định vị trí hợp lệ. |
| 4 | **C** | @Inherited ảnh hưởng tra cứu annotation kiểu class qua superclass. |
| 5 | **B** | @Repeatable cùng container cho phép dùng lặp trên một phần tử. |
| 6 | **B** | Processor xử lý annotation xuất hiện trong source. |
| 7 | **D** | TYPE_USE dành cho vị trí sử dụng kiểu. |
| 8 | **A** | @Override do javac kiểm tra. |
| 9 | **B** | Hai lỗi thuộc hai giai đoạn/cơ chế khác nhau. |
| 10 | **B** | name bắt buộc, level có default; null/new String không hợp lệ ở annotation value. |

### Đáp án đúng/sai

| Câu | Kết quả | Giải thích |
| --- | --- | --- |
| 11 | **Sai** | Phải có code/processor/framework đọc @Audit và thực hiện logging. |
| 12 | **Sai** | @Documented phục vụ tài liệu; @Retention(RUNTIME) phục vụ runtime reflection. |
| 13 | **Đúng** | CLASS được lưu ở class file nhưng không phải runtime-visible annotation cho reflection. |
| 14 | **Sai** | Functional interface hợp lệ vẫn dùng lambda được khi không có @FunctionalInterface. |
| 15 | **Sai** | Giới hạn suppress tại điểm nhỏ nhất và giải quyết warning gốc khi có thể. |
| 16 | **Đúng** | getAnnotationsByType hỗ trợ đọc trực tiếp hoặc gián tiếp qua container. |
| 17 | **Sai** | Map không thuộc loại return type hợp lệ của annotation element. |
| 18 | **Sai** | Còn có va chạm với input ban đầu, processor khác hoặc đường dẫn tài nguyên; Set nội bộ không bảo đảm toàn hệ thống. |

### Gợi ý đáp án trả lời ngắn

**19.** **getAnnotation** theo quy tắc @Inherited có thể tìm ModuleTag ở superclass ParentService, còn **getDeclaredAnnotation** chỉ xét lớp ChildService có khai báo trực tiếp hay không.

**20.** ReviewAtCompile có retention **SOURCE**, nên metadata không được giữ cho reflection runtime.

**21.** Dùng **getAnnotationsByType(Rule.class)**; API này trả các annotation hiện diện trực tiếp và những annotation lặp được chứa gián tiếp trong container theo quy tắc repeatable.

**22.** (1) Qualified name/path nào đang được tạo? (2) Processor nào đã gọi Filer và ở round nào? (3) Tên ấy có thuộc source/class input hoặc đã được tạo bởi processor nào khác trong cùng invocation không?

**23.** (1) Stack trace tại API reflection nào? (2) Runtime nạp class từ JAR/path nào? (3) Annotation attributes trong class file trước và sau instrumentation khác nhau ở đâu?

**24.** Khai báo ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface EndpointPermission {
    String value();
}
~~~

Khi dùng **@EndpointPermission("admin")** trên method, chương trình/framework còn phải tìm annotation runtime, lấy **value()**, xác định quyền của caller và **thật sự từ chối** lời gọi nếu quyền không phù hợp. Không có bước xử lý này, @EndpointPermission chỉ là nhãn metadata và **không cung cấp bảo mật**.

## 10. Tự chấm và chuẩn hoàn thành

Mỗi câu từ **1–24** đúng được **1 điểm**; tổng **24 điểm**. Với câu 19–24, chỉ tính đúng nếu câu trả lời nêu được **nguyên nhân/cơ chế** chứ không chỉ lặp lại từ khóa.

| Số câu đúng | Mức tự đánh giá | Hành động nên làm |
| --- | --- | --- |
| **21–24** | Vững | Tự thiết kế annotation có retention/target/consumer và test cả compile-time lẫn runtime |
| **17–20** | Khá | Ôn phần trả lời sai; thực hành lại repeatable, inherited và reflection |
| **12–16** | Cần củng cố | Viết lại bảng retention/target, chạy ví dụ mục 5, giải thích từng dòng stdout |
| **0–11** | Cần học lại nền tảng | Phân biệt compiler, processor, class file, reflection trước khi tiếp tục |

Để xác nhận đã nắm vững, hãy thử thay đổi một điều mỗi lần trong ví dụ mục 5: bỏ @Inherited, đổi Rule sang CLASS retention rồi sửa container tương thích, hoặc đổi @Target(METHOD) thành @Target(TYPE). **Dự đoán kết quả trước**, sau đó biên dịch/chạy và giải thích kết quả thật. Một lỗi compile-time do target sai khác bản chất với việc runtime không thấy annotation do retention.

## 11. Checklist lựa chọn annotation cho dự án Java

- [ ] Đã diễn đạt rõ ai đọc annotation và đọc vào giai đoạn nào.
- [ ] Đã cân nhắc annotation Java chuẩn trước khi tự tạo.
- [ ] Đã chọn @Retention dựa trên SOURCE/CLASS/RUNTIME.
- [ ] Đã giới hạn @Target theo đúng phần tử hoặc type-use cần áp dụng.
- [ ] Element có tên/kiểu hợp lệ; default rõ ràng và tránh cấu hình không cần thiết.
- [ ] Chỉ dùng @Documented, @Inherited, @Repeatable khi tính chất đó thực sự cần.
- [ ] Nếu lặp annotation, container và API đọc đã được thiết kế/kiểm tra.
- [ ] Nếu dùng reflection, test trên class file đã biên dịch và artifact chạy thật.
- [ ] Nếu dùng processor, log và kiểm soát tên output giữa các round/processor.
- [ ] Nếu annotation ảnh hưởng đến xác thực, validation, transaction hoặc logging, có consumer/test chứng minh hành vi cụ thể.
- [ ] Đã tự trả lời được các tình huống và giải thích vì sao các lựa chọn thay thế sai.

**Quy tắc ghi nhớ:** *Chọn annotation theo mục đích; @Target cho vị trí; @Retention cho vòng đời; meta-annotation cho tính chất bổ sung; consumer quyết định hành vi*. Một thiết kế tốt giúp compiler từ chối chỗ dùng sai, cho phép bên đọc truy cập đúng metadata và có bài kiểm tra xác nhận kết quả thực.
