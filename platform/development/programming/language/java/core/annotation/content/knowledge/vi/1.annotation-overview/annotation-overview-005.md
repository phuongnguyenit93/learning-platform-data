# Vì sao annotation tùy chỉnh cần bộ xử lý để tạo tác dụng?

> **Ý chính:** Annotation tùy chỉnh chỉ gắn **metadata (thông tin mô tả)** lên khai báo hoặc kiểu dữ liệu mà Java cho phép. Bản thân annotation không chứa cơ chế tự chạy lệnh, chặn lời gọi, kiểm tra nghiệp vụ hay sinh mã. Muốn metadata làm thay đổi kết quả, phải có một thành phần **đọc nó, diễn giải nó và thực hiện hành động** ở một thời điểm xác định: lúc biên dịch, lúc khởi động ứng dụng hoặc lúc chạy.

## 1. Phân biệt “khai báo ý định” với “thực thi hành vi”

Giả sử ta viết:

~~~java
@Audit
public void transferMoney() {
    // Thực hiện chuyển tiền
}
~~~

Đọc tên annotation, ta *mong muốn* phương thức được ghi nhật ký. Tuy nhiên Java không tự hiểu `@Audit` nghĩa là phải ghi những gì, ghi khi nào, gửi tới đâu hay xử lý lỗi ra sao. Nếu `@Audit` do ta tự tạo và không có mã nào đọc nó, `transferMoney()` vẫn chỉ chạy phần thân phương thức như bình thường. Annotation không tự thêm `try/finally`, gọi logger hay can thiệp vào bytecode.

Một khai báo tùy chỉnh chỉ xác định **cấu trúc metadata**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audit {
    String action() default "unknown";
}
~~~

- `@interface Audit`: định nghĩa một kiểu annotation và phần tử `action` có kiểu `String`.
- `@Target(METHOD)`: compiler kiểm tra annotation này chỉ được đặt ở phương thức.
- `@Retention(RUNTIME)`: metadata được giữ tới runtime để các API như reflection có thể đọc.
- `default "unknown"`: cung cấp giá trị mặc định; nó không định nghĩa hành động ghi log.

Ngay cả với `@Retention(RUNTIME)`, JVM cũng không tự gọi một “hàm của annotation” khi phương thức được thực thi. Annotation cũng không có phương thức `before()` hay `after()` theo nghĩa callback; các phần tử annotation chỉ trả về giá trị metadata.

### Annotation tích hợp sẵn là trường hợp khác

Ví dụ `@Override` được **Java compiler** nhận biết và dùng để kiểm tra một phương thức có thực sự override hay không; `@FunctionalInterface` cũng được compiler kiểm tra. `@Deprecated` có thể dẫn đến cảnh báo tại nơi sử dụng; `@SuppressWarnings` hướng dẫn compiler hoặc công cụ liên quan xử lý cảnh báo. Tác dụng đó có được vì **công cụ đã được lập trình để hiểu chúng**, chứ không phải vì mọi annotation đều tự có năng lực điều khiển chương trình. Tự định nghĩa `@MyOverride` với tên tương tự không khiến `javac` áp dụng quy tắc của `@Override`.

## 2. “Bộ xử lý annotation” có thể nằm ở nhiều giai đoạn

| Giai đoạn | Thành phần đọc annotation | Có thể tạo tác dụng gì? | Ví dụ |
| --- | --- | --- | --- |
| **Biên dịch** | Annotation processor theo chuẩn JSR 269, chạy qua `javac` | Kiểm tra cấu trúc mã nguồn, báo lỗi/cảnh báo, tạo source hoặc resource mới | MapStruct sinh mã mapper; processor tùy chỉnh kiểm tra quy ước |
| **Khởi động / cấu hình runtime** | Framework quét class, method, field và metadata | Đăng ký thành phần, tạo metadata ánh xạ, thiết lập interceptor/proxy | Spring phát hiện `@Component`, `@RequestMapping` |
| **Khi ứng dụng đang chạy** | Reflection, framework, interceptor, proxy hoặc mã nghiệp vụ do ta viết | Đọc giá trị annotation và quyết định có thực hiện hành động nào | Bean Validation chạy validator; interceptor ghi log |
| **Build / bytecode tooling** | Công cụ đọc class file hoặc biến đổi bytecode | Phân tích hoặc biến đổi artifact tùy công cụ | Công cụ instrument hay phân tích class file |

Từ “processor” trong câu hỏi nên hiểu **rộng** là *consumer/handler của metadata*. Riêng `javax.annotation.processing.Processor` là API **chỉ cho giai đoạn biên dịch**. Một ứng dụng có thể dùng reflection để xử lý annotation tại runtime mà không viết bất kỳ `AbstractProcessor` nào.

Luồng ý tưởng:

~~~text
Khai báo @MyAnnotation trên phần tử Java
                |
                v
       Annotation / metadata
                |
        Có ai đọc nó không?
         /             \
       Không            Có
        |                |
        v                v
Không phát sinh       Đọc giá trị + áp
hành vi bổ sung       dụng một quy tắc
                         |
                         v
                   Tác dụng quan sát được
~~~

Java có thể kiểm tra cú pháp, kiểu phần tử và vị trí gắn annotation mà không cần processor riêng. Những kiểm tra cơ bản này **không tương đương** với việc thực hiện nghiệp vụ mà tác giả annotation mong muốn.

## 3. Ví dụ runtime: annotation không chạy cho đến khi có mã đọc nó

Tạo tệp **`AnnotationDemo.java`** dưới đây. Tất cả các kiểu đều ở default package, nên có thể biên dịch độc lập với Java 17+.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Label {
    String value();
}

class Worker {
    @Label("Quan trọng")
    void run() {
        System.out.println("Worker.run()");
    }
}

public class AnnotationDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Worker worker = new Worker();

        // Gọi phương thức thông thường: JVM không tự in nhãn.
        worker.run();

        // Đây mới là mã chủ động xử lý metadata.
        Method method = Worker.class.getDeclaredMethod("run");
        Label label = method.getAnnotation(Label.class);
        if (label != null) {
            System.out.println("Nhãn: " + label.value());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AnnotationDemo.java
java AnnotationDemo
~~~

Kết quả chuẩn:

~~~text
Worker.run()
Nhãn: Quan trọng
~~~

Hãy nhìn vào hai thời điểm:

1. `worker.run()` in đúng một dòng `Worker.run()`, bất kể có `@Label` hay không.
2. Sau đó **chính mã trong `main`** lấy `Method`, gọi `getAnnotation(Label.class)` và dùng `label.value()` để in dòng thứ hai.

Nếu bỏ khối reflection, phương thức vẫn chạy và không có dòng `Nhãn: Quan trọng`. Nếu đổi `@Retention(RUNTIME)` thành `@Retention(CLASS)` rồi biên dịch lại, lời gọi `getAnnotation(Label.class)` trả về `null`, nên chỉ còn dòng `Worker.run()`. Trường hợp `CLASS` vẫn có thể được công cụ đọc class file xử lý; chỉ **runtime reflection theo API trên** không nhìn thấy annotation đó.

### Ai tìm được các phần tử đã gắn annotation?

Trong ví dụ, ta biết sẵn `Worker.class` và tên `run`. Với nhiều class, ứng dụng cần cơ chế tìm các class cần xét (đăng ký thủ công, danh sách class, hoặc thư viện/framework quét classpath), sau đó mới dùng reflection đọc annotation. `@Retention(RUNTIME)` chỉ giúp metadata có mặt khi đọc; nó **không tự quét toàn bộ dự án**.

Nếu muốn `@Audit` tự động ghi log quanh những lần gọi phương thức trong ứng dụng, phải có mã bao quanh lời gọi, interceptor, proxy, hoặc cơ chế instrument/bytecode phù hợp. Chỉ viết một vòng lặp reflection lúc khởi động chưa đủ để chặn các lời gọi đến phương thức.

## 4. Ví dụ compile-time: processor đọc annotation trong quá trình `javac`

Đôi khi ta muốn kiểm tra mã hoặc sinh mã **trước khi chạy ứng dụng**. Java hỗ trợ annotation processing theo JSR 269 qua `javax.annotation.processing`. Ví dụ sau dùng một processor đơn giản để phát ra compiler note, minh họa rõ rằng hành vi nằm trong *processor*.

Tạo ba tệp trong cùng thư mục.

**Tệp `DemoTag.java`:**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface DemoTag {
    String value();
}
~~~

**Tệp `TagProcessor.java`:**

~~~java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("DemoTag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TagProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (Element element : roundEnv.getElementsAnnotatedWith(DemoTag.class)) {
            DemoTag tag = element.getAnnotation(DemoTag.class);
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Tag: " + element.getSimpleName() + " -> " + tag.value(),
                    element);
        }
        return true;
    }
}
~~~

**Tệp `Example.java`:**

~~~java
@DemoTag("demo")
public class Example {
    public static void main(String[] args) {
        System.out.println("Example chạy bình thường");
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac DemoTag.java TagProcessor.java
javac -cp . -processor TagProcessor Example.java
java Example
~~~

Khi biên dịch `Example.java`, compiler sẽ hiển thị **note chứa nội dung** `Tag: Example -> demo` (vị trí, tiền tố và cách định dạng chẩn đoán có thể khác theo môi trường). Khi chạy chương trình, stdout chính xác là:

~~~text
Example chạy bình thường
~~~

**Điểm cần quan sát:** Nội dung `Tag: Example -> demo` là chẩn đoán từ **lần biên dịch**, không phải kết quả do JVM tự xử lý `@DemoTag`. `DemoTag` có `RetentionPolicy.SOURCE`, nên cũng không cần xuất hiện ở runtime để processor biên dịch đọc được.

Cơ chế processor theo ví dụ:

1. `javac` nhận processor nhờ tùy chọn `-processor TagProcessor`.
2. `@SupportedAnnotationTypes` cho biết processor quan tâm tới kiểu `DemoTag`.
3. `process(...)` được gọi qua các vòng xử lý (round); `RoundEnvironment` cung cấp các phần tử đã đánh dấu.
4. `process` đọc phần tử và metadata, rồi gọi `Messager` để gửi chẩn đoán.
5. Sau biên dịch, chương trình `Example` thực thi hoàn toàn độc lập với việc in chẩn đoán của processor.

Ở dự án thực tế, processor thường được đóng gói vào dependency riêng, được khai báo trên **annotation processor path** hoặc đăng ký với công cụ build. Các processor như MapStruct còn có thể dùng `Filer` để tạo tệp Java mới trong những round tiếp theo. API JSR 269 chuẩn chủ yếu phục vụ **phân tích, kiểm tra và sinh tệp mới**; nó không tự cho phép thay phần thân tùy ý của một phương thức đã có. Các thư viện can thiệp sâu vào AST/compiler như Lombok có cơ chế riêng ngoài phạm vi annotation processor thuần.

**Ghi chú về phiên bản JDK:** Không nên dựa vào việc processor “tình cờ” được phát hiện từ classpath. Cấu hình processor một cách tường minh bằng `-processor`, `-processorpath` hoặc cấu hình build tương ứng; các JDK/công cụ build có khác biệt về chế độ tự tìm và chạy processor. Ví dụ dùng `-processor` nên không phụ thuộc vào mặc định đó.

## 5. Retention và Target quyết định điều gì?

| Khai báo | Metadata tồn tại đến đâu? | Bộ xử lý phù hợp |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Chỉ trong mã nguồn / giai đoạn compiler xử lý; không được lưu trong class file | Annotation processor ở compile-time |
| `RetentionPolicy.CLASS` | Lưu trong class file; mặc định runtime reflection không truy xuất trực tiếp | Công cụ đọc/biến đổi class file |
| `RetentionPolicy.RUNTIME` | Lưu trong class file và có thể truy xuất qua reflection tại runtime | Reflection, framework runtime, hoặc công cụ class file |

Nếu không khai báo `@Retention`, mặc định là `CLASS`. `@Target` chỉ quy định những vị trí gắn hợp lệ (ví dụ `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `ANNOTATION_TYPE`, `TYPE_USE`). Một annotation dùng đúng target và retention **vẫn chưa có nghiệp vụ** nếu không có consumer hiểu nó.

Đặc biệt, runtime reflection thấy annotation không đồng nghĩa framework của ta sẽ áp dụng nó. Framework phải tìm đúng class/method, đọc đúng loại annotation và có logic xử lý tương ứng. Ngược lại, một processor compile-time vẫn đọc được annotation `SOURCE` mà runtime không thấy.

## 6. Liên hệ Spring, validation và thư viện quen thuộc

**Spring `@Component`:** Spring container có cơ chế đăng ký bean thông qua cấu hình và component scanning. Annotation đánh dấu lớp là ứng viên; khi ta tạo object bằng `new` mà không đưa vào container, chỉ thêm `@Component` không khiến object đó tự được quản lý.

**Spring `@Transactional`:** Infrastructure quản lý transaction (thường dùng proxy cho lời gọi qua Spring bean) kiểm tra metadata và mở/đóng transaction theo cấu hình. Tự tạo instance bằng `new` hoặc tự gọi một phương thức khác trên cùng instance (self-invocation trong chế độ proxy thường gặp) có thể không đi qua interceptor. Annotation tự nó không bắt đầu transaction. Cơ chế cụ thể còn phụ thuộc proxy/AspectJ và cấu hình dự án.

**Bean Validation `@NotNull`:** Constraint có tác dụng khi có provider/validator thực thi, ví dụ một lời gọi `Validator.validate(object)` hoặc integration kích hoạt validation khi xử lý request. Tự gắn constraint trên field không khiến mọi phép gán giá trị trong Java tự bị chặn. Nếu tạo custom constraint, thường cần annotation constraint, `ConstraintValidator`, cấu hình hợp lệ và điểm kích hoạt validation.

**MapStruct `@Mapper`:** Annotation processor tạo lớp implementation lúc build; runtime sử dụng lớp đã được biên dịch. Nếu processor không được chạy, ta không có mã sinh tương ứng, dù kiểu interface và annotation có thể vẫn hợp lệ về mặt cú pháp.

Những ví dụ này có chung công thức:

~~~text
Annotation (khai báo metadata)
    + Thành phần phát hiện/đọc
    + Quy tắc xử lý
    + Thời điểm kích hoạt
    = Hành vi quan sát được
~~~

## 7. Khi tự thiết kế annotation, cần quyết định gì?

Hãy lần lượt trả lời bốn câu hỏi trước khi tạo một annotation mới:

1. **Đánh dấu cái gì?** Xác định phần tử Java được phép gắn bằng `@Target`, các thuộc tính bắt buộc/tùy chọn và giá trị mặc định.
2. **Ai sẽ đọc nó?** Chọn compile-time `Processor`, mã reflection trực tiếp, framework tích hợp, proxy/interceptor hay công cụ class file.
3. **Đọc lúc nào?** Khi biên dịch, khi container khởi tạo, khi validate hoặc trước/sau mỗi lời gọi? Chọn `@Retention` phù hợp.
4. **Điều gì xảy ra khi thiếu processor hoặc cấu hình?** Có báo lỗi build, thiếu generated class, bỏ qua một xử lý tùy chọn hay phát hiện lỗi lúc chạy? Thiết kế thông báo lỗi và kiểm thử hành vi.

Ví dụ, nếu mục tiêu là “mọi phương thức được gắn `@Audit` đều phải được ghi nhật ký khi gọi”, chỉ khai báo `@Audit` là chưa đủ. Cần chọn cơ chế bao quanh lời gọi; đăng ký nó vào lifecycle thích hợp; đọc metadata của phương thức; ghi log theo chính sách; kiểm tra cả trường hợp gọi qua proxy lẫn gọi trực tiếp. Nếu không kiểm soát được toàn bộ đường gọi, không nên khẳng định audit luôn được áp dụng.

Việc dùng annotation phù hợp khi muốn cấu hình khai báo dùng lặp lại trên nhiều phần tử, và đã có một bộ xử lý tập trung rõ ràng. Với hành động chỉ cần gọi ở một nơi, một lời gọi phương thức thông thường đôi khi minh bạch và dễ kiểm thử hơn.

## 8. Những nhầm lẫn phổ biến

- **“Có `@Retention(RUNTIME)` là annotation tự hoạt động.”** Sai: đó chỉ là điều kiện để reflection thấy metadata, không phải bộ xử lý.
- **“Mọi annotation đều do `AbstractProcessor` xử lý.”** Sai: `AbstractProcessor` dành cho compile-time; Spring và nhiều framework có cơ chế runtime riêng.
- **“`@Target` và `@Retention` định nghĩa nghiệp vụ.”** Sai: chúng chỉ xác định nơi được gắn và thời gian lưu metadata.
- **“Khai báo dependency chứa annotation là đủ.”** Sai trong trường hợp cần processor: phải cấu hình cách kích hoạt processor hoặc hạ tầng runtime tương ứng; đôi khi annotation API và processor nằm trong hai dependency khác nhau.
- **“Processor compile-time sẽ chạy lại lúc ứng dụng thực thi.”** Sai: mã sinh/diagnostic xuất hiện lúc biên dịch; muốn xử lý runtime cần thành phần runtime riêng.
- **“Reflection tìm thấy annotation đồng nghĩa mọi lời gọi đều bị intercept.”** Sai: reflection chỉ đọc; intercept cần cơ chế thực thi bao quanh đường gọi.

## 9. Tự kiểm tra mức hiểu

**Câu 1.** Tạo `@TrackTime` có `@Retention(RUNTIME)` và gắn lên 10 phương thức. Chưa có đoạn mã đọc nó. Có tự xuất hiện log thời gian không?

**Đáp:** Không. Metadata có thể đọc được, nhưng chưa có interceptor/proxy hoặc mã khác tính thời gian và ghi log.

**Câu 2.** Annotation chỉ cần phục vụ quy tắc “class đặt tên sai phải báo lỗi khi compile” thì nên xử lý lúc nào?

**Đáp:** Lúc biên dịch bằng annotation processor; `SOURCE` thường đã đủ nếu không cần metadata sau biên dịch.

**Câu 3.** Vì sao một annotation runtime dùng `RetentionPolicy.CLASS` có thể không được Spring hoặc reflection đọc thấy?

**Đáp:** Reflection chuẩn không lộ trực tiếp annotation `CLASS`. Để xử lý metadata như vậy cần công cụ đọc class file phù hợp, hoặc dùng `RUNTIME` khi tích hợp yêu cầu reflection (lưu ý một số framework có trình đọc metadata riêng).

**Câu 4.** Điều gì khiến `@Transactional` có tác dụng khi Spring quản lý phương thức?

**Đáp:** Infrastructure transaction đã được cấu hình, tìm metadata và thực thi transaction advice qua cơ chế hỗ trợ (thường là proxy); annotation chỉ cung cấp khai báo.

**Bài tập nhỏ:** Dùng `AnnotationDemo.java` ở phần 3, xóa đúng phần reflection rồi chạy lại; so sánh stdout. Sau đó khôi phục và đổi retention từ `RUNTIME` thành `CLASS`. Hãy giải thích từng kết quả bằng ba yếu tố: **metadata đang tồn tại ở đâu, ai đọc nó, và hành động nào do code thực hiện**.