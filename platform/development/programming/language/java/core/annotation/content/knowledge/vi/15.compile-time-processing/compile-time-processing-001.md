# Annotation processing là gì và khác reflection ở đâu trong Java?

**Annotation processing** là cơ chế để một công cụ tham gia vào quá trình **biên dịch Java**, tìm các annotation trên mã nguồn và **kiểm tra, báo lỗi/cảnh báo hoặc sinh thêm tệp mã nguồn và tài nguyên**. Cơ chế tiêu chuẩn thường được gọi là **JSR 269 / Pluggable Annotation Processing API**, với các API trong **javax.annotation.processing** và **javax.lang.model**.

**Reflection** là cơ chế **kiểm tra kiểu, phương thức, trường và annotation của các class trong môi trường chạy**, thông qua các API như **java.lang.Class**, **java.lang.reflect.Method** và **AnnotatedElement.getAnnotation(...)**.

Sự khác biệt cốt lõi không nằm ở hình thức dấu **@**, mà là **thời điểm thực thi và mô hình thông tin mà công cụ đọc**:

- Processor thường chạy **trong quá trình javac biên dịch source**; nhìn thấy cấu trúc chương trình qua **Element**, **TypeMirror**, **AnnotationMirror**.
- Reflection được mã ứng dụng gọi **khi chương trình đang chạy**, sau khi class đã được nạp; nhìn thấy mô hình runtime qua **Class**, **Method**, **Field** và các đối tượng annotation.
- Processor có thể xử lý annotation mang **RetentionPolicy.SOURCE**, vốn không được lưu vào class file để reflection runtime đọc. Reflection thông thường cần annotation mang **RetentionPolicy.RUNTIME**.
- Processor có thể sinh mã nguồn mới để trình biên dịch tiếp tục biên dịch, nhưng **không nên được hiểu như công cụ tùy ý sửa nội dung source gốc hoặc sửa bytecode đã có**. Reflection có thể kiểm tra metadata và thực hiện một số thao tác runtime được Java cho phép, nhưng **không tự sinh source/biên dịch source** chỉ vì đọc được annotation.

## 1. Vì sao Java cần annotation processing?

Annotation bản thân là **metadata**. Ví dụ:

~~~java
@GenerateNumber(42)
class Demo {}
~~~

Annotation không tự khiến Java tạo thêm class, kiểm tra cấu hình hay in ra số 42. Cần có một **thành phần đọc và diễn giải** nó.

Tại lúc biên dịch, annotation processor có thể biến yêu cầu này thành các hành động như:

1. **Kiểm tra mã nguồn**: đảm bảo chỉ một class được gắn annotation, hoặc một phần tử có định dạng đúng; dùng diagnostic để báo lỗi ngay khi chạy **javac**.
2. **Sinh mã nguồn**: tạo class Java phụ trợ từ metadata, ví dụ một class chứa constant hoặc mapper. Java compiler có thể thấy và biên dịch source được sinh trong các vòng xử lý tiếp theo.
3. **Sinh tài nguyên**: thông qua **Filer** nếu định dạng và vị trí ghi cho phép, ví dụ mô tả metadata/tài nguyên phục vụ build.
4. **Phục vụ công cụ phân tích/build**: tạo các cảnh báo, thông tin bổ trợ hoặc kiểm tra quy ước kiến trúc trước khi chạy chương trình.

Các thư viện có thể dùng annotation processing để giảm mã lặp (generated classes), phát hiện lỗi sớm hoặc tạo cấu hình. **Không phải annotation nào trong Java cũng có processor**, và **có annotation không có nghĩa javac sẽ tự chạy processor tương ứng**: trình biên dịch phải được cấu hình để tìm/nạp processor.

## 2. Mô hình compile-time: Processor, Element, TypeMirror

Một annotation processor tuân thủ hợp đồng của interface **javax.annotation.processing.Processor**, thường được triển khai bằng cách kế thừa **AbstractProcessor**:

~~~java
@SupportedAnnotationTypes("demo.GenerateNumber")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class NumberProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Phân tích các phần tử của chương trình.
        return true;
    }
}
~~~

Đoạn trên chỉ minh họa bộ khung; cần các import thích hợp mới là source Java biên dịch độc lập. Ví dụ hoàn chỉnh nằm ở phần sau.

Các khái niệm chính:

| Thành phần | Vai trò |
| --- | --- |
| **Processor** | Hợp đồng cho công cụ tham gia annotation processing |
| **AbstractProcessor** | Lớp cơ sở giúp triển khai Processor và cung cấp processing environment |
| **@SupportedAnnotationTypes** | Khai báo tên các kiểu annotation mà processor hỗ trợ; có thể khai báo bằng **getSupportedAnnotationTypes()** |
| **@SupportedSourceVersion** | Khai báo phiên bản ngôn ngữ nguồn processor hỗ trợ |
| **ProcessingEnvironment** | Điểm truy cập tiện ích như **Messager**, **Filer**, **Elements**, **Types**, options |
| **RoundEnvironment** | Thông tin về vòng xử lý hiện tại, các phần tử được annotate, trạng thái vòng cuối |
| **Element / TypeElement** | Biểu diễn khai báo chương trình (class, method, field, package, …) trong mô hình của compiler |
| **TypeMirror** | Biểu diễn **kiểu Java** trong mô hình compiler, khác với **java.lang.Class** |
| **AnnotationMirror** | Biểu diễn annotation trên một phần tử theo mô hình compiler |
| **Messager** | Phát thông báo **NOTE**, **WARNING**, **ERROR** qua trình biên dịch |
| **Filer** | Tạo tệp nguồn Java, class file hoặc resource theo quy tắc annotation processing |

**Element không phải java.lang.reflect.AnnotatedElement.** Tên tương tự nhưng đối tượng thuộc hai mô hình và hai giai đoạn khác nhau. **TypeElement** giúp làm việc với khai báo class/interface qua compiler, còn **Class<?>** trong reflection đại diện cho class đã được nạp ở runtime.

Processor không cần chạy thử method của class được xử lý và thông thường **không nên nạp class ứng dụng chỉ để phân tích nó**. Nó dùng thông tin tên, kiểu và annotation từ mô hình của javac.

## 3. Chương trình minh họa annotation processing bằng Java 17+

Ta sẽ tạo một annotation **@GenerateNumber(42)** có retention **SOURCE**, một processor đọc số 42 và sinh tệp **demo.generated.NumberInfo**. Class ứng dụng sử dụng class vừa được sinh ngay trong cùng lượt biên dịch.

Cấu trúc ba tệp **tự viết**:

~~~text
project/
├── src/
│   └── demo/
│       ├── GenerateNumber.java
│       └── App.java
└── processor/
    └── demo/
        └── NumberProcessor.java
~~~

Sau lệnh biên dịch, sẽ có các thư mục **processor-out**, **generated-src**, **out**. Không cần tạo các tệp sinh thủ công.

### Bước 1 — Khai báo annotation

Tệp **src/demo/GenerateNumber.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateNumber {
    int value();
}
~~~

**@Target(TYPE)** nghĩa là chỉ dùng trên khai báo kiểu thích hợp như class. **@Retention(SOURCE)** bảo đảm annotation có mặt trong quá trình xử lý source, nhưng không được giữ trong class file để mã runtime có thể đọc bằng reflection.

Phần tử **value()** nhận một số nguyên. Cú pháp **@GenerateNumber(42)** là viết tắt của **@GenerateNumber(value = 42)**.

### Bước 2 — Viết processor

Tệp **processor/demo/NumberProcessor.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateNumber")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class NumberProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        Set<? extends Element> annotated =
                roundEnv.getElementsAnnotatedWith(GenerateNumber.class);

        if (annotated.isEmpty()) {
            return true;
        }

        if (annotated.size() != 1) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Exactly one class must use @GenerateNumber");
            return true;
        }

        Element element = annotated.iterator().next();
        int number = element.getAnnotation(GenerateNumber.class).value();

        try {
            JavaFileObject file = processingEnv.getFiler()
                    .createSourceFile(
                            "demo.generated.NumberInfo", element);

            try (Writer writer = file.openWriter()) {
                writer.write("package demo.generated;\n");
                writer.write("public final class NumberInfo {\n");
                writer.write("  private NumberInfo() {}\n");
                writer.write(
                        "  public static final int VALUE = "
                        + number + ";\n");
                writer.write("}\n");
            }

            generated = true;
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Generated NumberInfo from @GenerateNumber",
                    element);

        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate NumberInfo: " + ex.getMessage(),
                    element);
        }

        return true;
    }
}
~~~

**Giải thích code:**

1. **@SupportedAnnotationTypes("demo.GenerateNumber")** cho biết processor hỗ trợ kiểu annotation tên đầy đủ **demo.GenerateNumber**.
2. **@SupportedSourceVersion(RELEASE_17)** khai báo phiên bản nguồn được processor hỗ trợ. Đây là khả năng của processor, không phải chỉ thị thay thế cho mọi tùy chọn phiên bản javac.
3. **roundEnv.getElementsAnnotatedWith(GenerateNumber.class)** lấy các **Element** được gắn annotation ở vòng hiện tại. Đó là mô hình compiler; không cần nạp class của App.
4. **element.getAnnotation(GenerateNumber.class)** là API của **javax.lang.model.element.Element**. Cú pháp giống reflection nhưng đối tượng **element** không phải Class/Method/Field của runtime. API này cung cấp cách đọc annotation trong compiler model; dùng **AnnotationMirror** là lựa chọn thường gặp cho processor tổng quát hoặc khi cần thao tác metadata phức tạp hơn.
5. Ví dụ cố ý yêu cầu có **đúng một** đối tượng được gắn GenerateNumber trong compilation này; nhiều hơn thì Messager phát lỗi **ERROR**, khiến biên dịch không thành công.
6. **Filer.createSourceFile(...)** tạo Java source mới có tên chuẩn **demo.generated.NumberInfo**. Gọi **openWriter()** để viết nội dung; compiler sẽ thấy source mới ở các vòng tiếp theo.
7. Biến **generated** giúp processor không cố tạo lại cùng tệp trong nhiều vòng. **Filer** không cho cùng một processor tạo cùng một path lặp lại trong một lần xử lý.
8. **return true** báo rằng processor này đã *claim* các annotation type nó hỗ trợ trong vòng hiện tại; nó **không** có nghĩa chương trình đã chạy hoặc class vừa sinh đã được gọi.

**Lưu ý thực tế:** Ví dụ dùng một số nguyên để sinh Java literal nên không cần escaping chuỗi. Nếu sinh code từ giá trị String tùy ý do người dùng nhập, phải escape đúng cú pháp Java và tránh sinh mã không hợp lệ. Trong ứng dụng thực, cần kiểm tra đủ loại Element và xử lý tốt nhiều compilation units.

### Bước 3 — Viết class ứng dụng

Tệp **src/demo/App.java**:

~~~java
package demo;

import demo.generated.NumberInfo;

@GenerateNumber(42)
public class App {
    public static void main(String[] args) {
        System.out.println("Generated value=" + NumberInfo.VALUE);
    }
}
~~~

**App** tham chiếu **NumberInfo** dù tệp **NumberInfo.java** chưa tồn tại trước khi compile. Đây là mục tiêu của thí nghiệm: processor tạo nó trong quá trình javac xử lý App.java.

### Bước 4 — Biên dịch theo đúng hai pha

Trước hết, từ thư mục **project**, tạo các thư mục đầu ra. Ví dụ với **PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force processor-out,generated-src,out | Out-Null
~~~

Trên bash/macOS/Linux có thể dùng:

~~~bash
mkdir -p processor-out generated-src out
~~~

Sau đó chạy các lệnh **javac/java** giống nhau trên hai môi trường.

**Pha A: biên dịch annotation type và chính processor, tạm tắt processing khi build processor.**

~~~bash
javac --release 17 -proc:none -d processor-out src/demo/GenerateNumber.java processor/demo/NumberProcessor.java
~~~

Lệnh này tạo **processor-out/demo/GenerateNumber.class** và **processor-out/demo/NumberProcessor.class**. Không dùng processor để sinh chính nó trong bước này. Cờ **-proc:none** tắt annotation processing của lượt javac hiện tại.

**Pha B: biên dịch App và yêu cầu javac gọi processor.**

~~~bash
javac --release 17 -cp processor-out -processorpath processor-out -processor demo.NumberProcessor -s generated-src -d out src/demo/App.java
~~~

Các cờ quan trọng:

- **-cp processor-out**: đặt annotation type **demo.GenerateNumber** trên classpath khi biên dịch App.
- **-processorpath processor-out**: nơi javac tìm class cần thiết để nạp processor và các dependency của nó.
- **-processor demo.NumberProcessor**: yêu cầu rõ ràng phải chạy processor có tên này; không phụ thuộc vào cơ chế autodiscovery.
- **-s generated-src**: nơi ghi các Java source được sinh.
- **-d out**: nơi ghi các class file được biên dịch.
- **--release 17**: biên dịch theo mức API và ngôn ngữ Java 17 phù hợp ví dụ.

Sau Pha B, tệp nguồn sinh sẽ là **generated-src/demo/generated/NumberInfo.java**:

~~~java
package demo.generated;
public final class NumberInfo {
  private NumberInfo() {}
  public static final int VALUE = 42;
}
~~~

**javac** còn biên dịch source sinh này thành class trong **out**. Pha xử lý có thể tạo thông báo **NOTE** trên luồng diagnostic của javac; đó không phải stdout từ chương trình App.

Chạy ứng dụng:

~~~bash
java -cp out demo.App
~~~

**Stdout của lệnh java:**

~~~text
Generated value=42
~~~

Ứng dụng không cần nạp annotation GenerateNumber để in số 42. Mã nguồn do processor tạo đã được biên dịch thành class **NumberInfo**, và chương trình đọc constant từ class đó. Vì annotation khai báo retention **SOURCE**, **App.class** không chứa bản annotation có thể truy xuất bằng runtime reflection.

**Nếu tắt processor ở Pha B** mà chưa có class **demo.generated.NumberInfo** trên classpath, javac không thể phân giải import **demo.generated.NumberInfo** trong App. Điều này chứng minh processor đã tham gia tạo input mới cho compiler.

## 4. Một ví dụ reflection riêng để đối chiếu

Reflection làm việc với class đã được biên dịch/nạp và annotation được lưu ở runtime. Tạo một tệp khác **src/demo/ReflectionDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeLabel {
    String value();
}

@RuntimeLabel("active")
class ActiveService {
}

class PlainService {
}

public class ReflectionDemo {
    public static void main(String[] args) {
        printLabel(ActiveService.class);
        printLabel(PlainService.class);
    }

    private static void printLabel(Class<?> type) {
        RuntimeLabel label =
                type.getAnnotation(RuntimeLabel.class);

        String value = label == null ? "<none>" : label.value();

        System.out.println(type.getSimpleName() + ": " + value);
    }
}
~~~

Đây là ví dụ độc lập với processor ở phần trước. Biên dịch và chạy trực tiếp bằng javac, **không cần NumberProcessor**:

~~~bash
javac --release 17 -proc:none -d out src/demo/ReflectionDemo.java
java -cp out demo.ReflectionDemo
~~~

**Stdout:**

~~~text
ActiveService: active
PlainService: <none>
~~~

Ở đây:

- **@Retention(RUNTIME)** cho phép getAnnotation đọc RuntimeLabel trên **ActiveService**.
- **PlainService** không gắn annotation nên **getAnnotation(...)** trả null, và chương trình xử lý trường hợp đó một cách an toàn.
- **Class<?>** đại diện cho kiểu được nạp; **getAnnotation(...)** đọc annotation metadata tương ứng theo quy tắc runtime.
- Không có Java source mới nào được sinh nhờ hai lời gọi reflection này; xử lý bằng reflection là logic của chương trình đang chạy.

Annotation **RuntimeLabel** trong ví dụ có thể được compiler nhìn thấy ở thời điểm biên dịch, nhưng **không có processor được đăng ký để xử lý nó**. Ngược lại, **GenerateNumber** dùng SOURCE retention vẫn đủ cho processor đọc ở compile time, trong khi không đủ cho reflection runtime.

## 5. Bảng so sánh annotation processing và reflection

| Tiêu chí | Annotation processing (JSR 269) | Reflection |
| --- | --- | --- |
| **Thời điểm điển hình** | Trong quá trình javac biên dịch | Khi chương trình chạy và class được nạp |
| **Mục đích** | Kiểm tra source, tạo diagnostic, sinh thêm source/resource | Kiểm tra metadata/runtime type và thực hiện logic xử lý runtime |
| **API chính** | **javax.annotation.processing**, **javax.lang.model** | **java.lang.Class**, **java.lang.reflect**, **java.lang.annotation** |
| **Đại diện khai báo class** | **TypeElement** | **Class<?>** |
| **Đại diện kiểu** | **TypeMirror** | **Class**, **Type**, **AnnotatedType** tùy ngữ cảnh |
| **Đọc annotation** | **Element.getAnnotation()**, **getAnnotationMirrors()**, **RoundEnvironment** | **AnnotatedElement.getAnnotation()**, **getAnnotationsByType()** |
| **Retention tối thiểu để nhìn thấy** | **SOURCE** đủ trong lúc processing source | **RUNTIME** để dùng Java reflection thông thường |
| **Có thể sinh Java source khi javac chạy?** | Có, thông qua **Filer** | Không phải chức năng của API reflection |
| **Tạo lỗi compile-time?** | Có, dùng **Messager** với **ERROR** | Không tự tham gia biên dịch trước đó |
| **Phụ thuộc class ứng dụng đã nạp?** | Không, làm việc chủ yếu trên compiler model | Có, làm việc trên class/member trong runtime |
| **Hệ quả thực tế** | Lỗi bị phát hiện sớm, code sinh sẵn | Có thể quyết định xử lý dựa trên annotation tại runtime |

Bảng mô tả **cách sử dụng tiêu chuẩn**. Vẫn có những chương trình chạy processor thông qua **JavaCompiler API** hoặc công cụ build khác, và reflection có thể được sử dụng trong tool build. Sự phân biệt quan trọng là **mô hình compiler và JSR 269** so với **mô hình đối tượng runtime của reflection**, chứ không phải chỉ dựa vào “công cụ nào chạy bằng process nào”.

## 6. RetentionPolicy: SOURCE, CLASS và RUNTIME

**@Retention** quyết định annotation được giữ lại tới mức nào.

~~~java
@Retention(RetentionPolicy.SOURCE)
@interface CompileOnly {}

@Retention(RetentionPolicy.CLASS)
@interface InClassFile {}

@Retention(RetentionPolicy.RUNTIME)
@interface AtRuntime {}
~~~

Dùng đúng import **java.lang.annotation.Retention** và **RetentionPolicy**.

| Retention | Annotation processor trong lúc biên dịch source | Lưu trong class file | Reflection runtime thông thường |
| --- | --- | --- | --- |
| **SOURCE** | Có thể thấy | Không | Không |
| **CLASS** | Có thể thấy | Có | Không |
| **RUNTIME** | Có thể thấy | Có | Có |

**CLASS là retention mặc định** nếu khai báo annotation type không có **@Retention**.

Điểm cốt lõi: **SOURCE là đủ cho annotation processing**, còn **RUNTIME cần thiết cho reflection runtime**. Tuy vậy, việc khai báo RUNTIME **không tự động gọi reflection**, và việc khai báo SOURCE **không tự động khởi động processor**. Đó là hai chính sách độc lập: cách giữ metadata và cách chương trình/công cụ tiêu thụ metadata.

Không phải mọi annotation processor đều chỉ xử lý annotation SOURCE; nó cũng có thể xử lý annotation CLASS/RUNTIME đang xuất hiện trên source trong lượt biên dịch.

## 7. Các vòng annotation processing (processing rounds)

Annotation processing thường chạy theo **nhiều vòng**:

1. **Vòng đầu**: compiler cung cấp những source đầu vào ban đầu; processor được gọi với **RoundEnvironment**.
2. **Processor kiểm tra và có thể sinh source/class mới** bằng **Filer**.
3. **Vòng tiếp theo**: những đầu vào mới được sinh hợp lệ có thể trở thành đối tượng để compiler và các processor tiếp tục phân tích.
4. **Vòng cuối**: **roundEnv.processingOver()** cho biết processing đã kết thúc; không nên cố sinh thêm source mong đợi được xử lý tiếp sau vòng cuối.

Ví dụ **NumberProcessor** dùng điều kiện:

~~~java
if (roundEnv.processingOver() || generated) {
    return true;
}
~~~

để không tạo lặp **NumberInfo** trên những vòng khác nhau. Nếu processor cố gọi **createSourceFile("demo.generated.NumberInfo")** hai lần cho cùng path trong một lần xử lý, **Filer** có thể báo lỗi **FilerException**.

Một processor được gọi theo các annotation type đã được khai báo hỗ trợ; **process(...)** nhận tập **TypeElement** đại diện cho annotation types của vòng đó. Tham số **RoundEnvironment** còn cho phép tìm các element được annotate, ví dụ **getElementsAnnotatedWith(...)**.

**return true** khi hoàn tất xử lý có nghĩa processor *claim* những annotation types trong lượt gọi, làm chúng không tiếp tục được gửi cho một số processor kế tiếp theo quy tắc API. **return false** không có nghĩa “biên dịch thất bại”; nó có nghĩa processor **không claim** các annotation types đó. Lỗi biên dịch được báo bằng **Messager** kiểu **ERROR** hoặc phát sinh từ lỗi nguồn/công cụ.

Processor không nên phụ thuộc vào thứ tự tìm các element trong một **Set**, và không nên giả định nó chỉ chạy đúng một lần. Với nhiều loại annotation, nhiều class và nhiều processor, quy trình có thể phức tạp hơn ví dụ một class.

## 8. Tìm và đăng ký processor với javac

Có nhiều cách cấu hình processor:

**Cách tường minh** dùng **-processor demo.NumberProcessor** như thí nghiệm. Đây là lựa chọn tốt để minh họa, vì nó không phụ thuộc vào processor discovery mặc định của từng phiên bản javac.

Trong dự án thư viện, processor thường được đóng gói thành JAR riêng với **Service Provider configuration**:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung tệp service có thể là tên đầy đủ của class triển khai:

~~~text
demo.NumberProcessor
~~~

Khi javac được cấu hình cho phép khám phá processor qua service loader và processor path, service descriptor giúp tìm provider mà không phải liệt kê từng class bằng **-processor**. Các phiên bản JDK mới có thể thay đổi hành vi mặc định về tự động chạy processor; với build tái lập, nên cấu hình rõ processor, processor path và toolchain.

Các hệ thống như **Maven** và **Gradle** có cơ chế khai báo dependency và processor path riêng, thường nên tách dependency cần có để **biên dịch source** với dependency chứa **processor được thực thi trong giai đoạn build**. Một processor thường là **phụ thuộc build-time**, không nhất thiết phải nằm trên runtime classpath của ứng dụng.

Đừng chỉ thêm processor JAR vào dependency chung rồi mặc định cho rằng processor chắc chắn chạy. Hãy xác minh các tùy chọn, cấu hình build và tệp được sinh.

## 9. Processor có thể và không thể làm gì?

**Có thể:**

- Phát hiện class/method/field được gắn annotation ở compile time.
- Kiểm tra kiểu, chữ ký, modifier và cấu trúc metadata theo **javax.lang.model**.
- Phát cảnh báo hoặc lỗi bằng **Messager**.
- Sinh source Java mới và một số resource phục vụ build thông qua **Filer**.
- Phối hợp với compiler để source mới được xem xét trong processing rounds và biên dịch.

**Không nên coi nó là:**

- Một cơ chế **tự chạy khi chương trình khởi động**: annotation processor thông thường hoạt động trong build, không phải listener của mọi lệnh **java**.
- Một cách **tự thay đổi bytecode của các class có sẵn**, chèn method vào class gốc bằng API chuẩn JSR 269. Một số công cụ bên ngoài có thể dùng compiler internals hoặc bytecode weaving, nhưng đó không phải chức năng được bảo đảm bởi API annotation processing chuẩn.
- Một bản sao của reflection: processor không được viết để **Class.forName(...)** nhằm phân tích mọi class nguồn chưa được biên dịch; mô hình Element/TypeMirror được thiết kế cho giai đoạn này.
- Một thành phần tự động hiểu ý nghĩa nghiệp vụ của annotation. Cần processor chuyên biệt biết cách diễn giải kiểu annotation mà thư viện định nghĩa.

Một số công cụ dùng annotation ở nhiều giai đoạn: processor sinh metadata/code tại compile time, rồi thư viện đọc một phần metadata ở runtime nếu được lưu. Hai cơ chế có thể bổ trợ nhau; **không phải lựa chọn loại trừ**.

## 10. Cách chọn giữa processing và reflection trong ứng dụng

Nếu nhu cầu là **phát hiện sai cấu hình trước khi build hoàn tất**, xử lý hàng trăm class để tạo registry tĩnh hoặc tạo lớp chuyển đổi dữ liệu từ annotation, processor là ứng viên phù hợp. Lợi ích là phát hiện vấn đề sớm và giảm các thao tác phân tích annotation ở runtime.

Nếu nhu cầu là **đọc annotation trên một class đang được nạp**, quyết định hành vi theo metadata lúc chạy hoặc quét một tập class của ứng dụng trong môi trường runtime, reflection có thể phù hợp hơn.

Ví dụ minh họa:

- **Sinh mapping code theo cấu trúc model:** annotation processing có thể giúp tạo lớp phụ trợ trong build. Trong runtime, ứng dụng gọi lớp đã sinh.
- **Kiểm tra bắt buộc có @Component trên khai báo:** processor có thể báo lỗi compile-time theo quy tắc thư viện.
- **Đọc @Route để xây router khi khởi động:** framework có thể dùng reflection nếu annotation được giữ ở RUNTIME.
- **Sinh code dựa trên @Route trước khi chạy:** framework có thể chọn processor và tạo registry/handler tĩnh thay vì quét class lúc khởi động.

Việc processor tốt hơn reflection về hiệu năng **không phải chân lý tuyệt đối**: phải đánh giá chi phí build, kích thước code sinh, độ linh hoạt cấu hình, yêu cầu plugin và runtime. Reflection không mặc nhiên chậm đến mức không nên dùng; kết quả tùy khối lượng và cách caching.

## 11. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Khai báo **@GenerateNumber** rồi kỳ vọng NumberInfo tự xuất hiện | Chưa chạy processor | Đảm bảo javac được cấu hình nạp đúng processor |
| Chỉ thêm annotation library nhưng quên processor dependency | Annotation type khác processor | Khai báo classpath và processor path phù hợp |
| Chỉ để processor trên classpath nhưng không cấu hình thực thi | Không được bảo đảm auto discovery | Dùng **-processor** hoặc build tool khai báo processor rõ ràng |
| Gọi **Class.forName("demo.App")** trong processor để tìm source đang compile | App có thể chưa được biên dịch thành class tải được | Dùng **TypeElement**, **Elements**, **RoundEnvironment** |
| Đọc **@Retention(SOURCE)** bằng runtime reflection | SOURCE không lưu trong class file | Dùng processing tại compile time; hoặc RUNTIME nếu thật sự cần reflection |
| Sinh cùng một tệp ở nhiều round | Filer không cho tạo cùng path lặp lại | Theo dõi trạng thái sinh tệp và quản lý processing rounds |
| Xem **return true** từ process là “chạy thành công” | Nó biểu thị claim annotation types | Dùng **Messager.ERROR** để báo lỗi thực |
| Cho rằng processor chỉnh class gốc bằng API chuẩn | JSR 269 chủ yếu phân tích và tạo tệp mới | Sinh helper class hoặc dùng công cụ được thiết kế riêng |
| Biên dịch processor và App cùng một lần rồi mong javac tự chạy processor mới | Processor cần được javac nạp trước khi xử lý | Biên dịch processor trước, sau đó biên dịch App với processor path |
| Gọi **getAnnotation(...)** trên null ở runtime | Không phải class nào cũng mang annotation | Kiểm tra null hoặc dùng **isAnnotationPresent** |
| Bỏ **-s** và không biết source sinh nằm ở đâu | Vị trí generated source phụ thuộc cấu hình javac | Dùng **-s generated-src** để dễ kiểm tra |
| Sinh code từ chuỗi tùy ý mà không escape | Dễ tạo Java source không hợp lệ | Escape đúng Java literal và kiểm tra dữ liệu đầu vào |

## 12. Bài tập tự kiểm tra

**Bài 1.** Một thư viện cần báo lỗi ngay lúc compile nếu class gắn **@GenerateNumber** nhưng cấu trúc không hợp lệ. Dùng reflection hay annotation processing? **Annotation processing** phù hợp vì có thể kiểm tra **Element** và phát **Diagnostic.Kind.ERROR** trong javac.

**Bài 2.** Một chương trình đang chạy cần đọc **@RuntimeLabel("active")** từ **ActiveService.class**. Dùng API nào? Dùng **ActiveService.class.getAnnotation(RuntimeLabel.class)** và đọc phần tử **value()** sau khi kiểm tra null. Annotation phải có **RUNTIME** retention để truy vấn qua reflection chuẩn.

**Bài 3.** Vì sao annotation **@GenerateNumber** dùng SOURCE vẫn được NumberProcessor đọc? Vì processor xem metadata lúc biên dịch source qua **RoundEnvironment** và mô hình compiler, trước khi retention SOURCE bị loại khỏi class file.

**Bài 4.** Vì sao phải chạy hai lệnh **javac** trong ví dụ? Lệnh đầu tạo binary của processor để compiler có thể nạp và thực thi nó. Lệnh thứ hai biên dịch App với processor đã có, từ đó tạo **NumberInfo**.

**Bài 5.** Khi NumberProcessor tạo ra **NumberInfo.java**, có cần viết lệnh javac riêng biên dịch NumberInfo không? **Thông thường không** trong ví dụ: javac xử lý source sinh trong các vòng biên dịch và tạo class tương ứng. Có thể kiểm tra cả **generated-src/demo/generated/NumberInfo.java** và **out/demo/generated/NumberInfo.class**.

**Bài 6.** **element.getAnnotation(GenerateNumber.class)** trong processor có phải cùng bối cảnh với **App.class.getAnnotation(...)** không? **Không**. Đầu tiên là phương thức của **Element** thuộc compiler model; thứ hai là reflection trên **Class** runtime. Chúng có thể giống tên method nhưng khác giai đoạn và đối tượng.

**Bài 7.** Nếu annotation có **@Retention(RUNTIME)**, có bắt buộc viết processor không? **Không**. Retention xác định việc lưu metadata, không quyết định cách sử dụng nó. Một ứng dụng có thể chỉ dùng reflection mà không chạy bất kỳ processor riêng nào.

## 13. Tài liệu Java chính thức

- **Java SE 17 — javax.annotation.processing:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html — các interface và lớp cho annotation processing.
- **Java SE 17 — AbstractProcessor:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html — lớp cơ sở của processor.
- **Java SE 17 — RoundEnvironment:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — các element được annotate và thông tin processing rounds.
- **Java SE 17 — javax.lang.model:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/package-summary.html — mô hình khai báo/kiểu tại compile time.
- **Java SE 17 — javac options:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html — các tùy chọn **-processor**, **-processorpath**, **-proc**, **-s**, **-d** và **--release**.
- **Java SE 17 — AnnotatedElement:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html — các API đọc annotation qua reflection runtime.
- **Java Language Specification §9.6.4.2 — @Retention:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2 — mức giữ annotation.

**Kết luận:** Annotation processing là công cụ làm việc với **mô hình source và symbol trong quá trình biên dịch**, có thể **kiểm tra và sinh mã** trước khi ứng dụng chạy. Reflection làm việc với **các kiểu/thành viên đã nạp trong runtime** để **đọc và diễn giải metadata**. Chọn cơ chế theo thời điểm và mục đích; đừng coi annotation tự có hành vi chỉ vì xuất hiện trong source.
