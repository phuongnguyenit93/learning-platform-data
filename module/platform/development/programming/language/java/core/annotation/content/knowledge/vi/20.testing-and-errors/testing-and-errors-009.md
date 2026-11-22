# AnnotationFormatError, FilerException và cách khoanh vùng nguyên nhân

## 1. Hai lỗi cùng liên quan annotation nhưng xảy ra ở hai giai đoạn khác nhau

Trong Java, annotation có thể được **đọc từ bytecode khi chạy chương trình** hoặc được **annotation processor xử lý trong lúc biên dịch**. Hai lỗi dưới đây xuất hiện ở hai cơ chế khác nhau:

| Tiêu chí | AnnotationFormatError | FilerException |
| --- | --- | --- |
| Kiểu ngoại lệ | java.lang.annotation.AnnotationFormatError kế thừa Error | javax.annotation.processing.FilerException kế thừa IOException |
| Thời điểm điển hình | JVM/thư viện phản chiếu đọc annotation từ tệp .class | javac hoặc công cụ build đang chạy annotation processor |
| Thành phần phát hiện | Bộ phân tích annotation của Java runtime | Filer do môi trường annotation processing cấp |
| Bản chất | Dữ liệu annotation trong class file không hợp lệ/không thể phân tích đúng định dạng | Processor yêu cầu tạo lại một tệp hoặc tên kiểu mà Filer không cho phép tạo |
| Điểm cần kiểm tra trước | Class file thực tế được nạp, metadata annotation, công cụ sửa bytecode | Tên tệp được tạo, processor nào tạo, vòng xử lý nào, tệp đầu vào |
| Hướng xử lý | Xác định class file hỏng/sai, sửa nguồn tạo hoặc biến đổi bytecode và build lại | Bảo đảm tạo mỗi tên đầu ra tối đa một lần trong một lần processing, phân định quyền tạo tệp |

**Không đồng nhất hai lỗi.** Một lỗi xuất hiện khi reflection đọc annotation chưa đủ để kết luận processor có vấn đề; ngược lại, FilerException không chứng minh bytecode annotation bị hỏng.

## 2. AnnotationFormatError: nguyên nhân và điều kiện phát sinh

### 2.1. Annotation được lưu trong .class như thế nào?

Annotation có chính sách lưu giữ:

- **SOURCE:** dùng tại thời điểm biên dịch và không được giữ để đọc qua reflection lúc chạy.
- **CLASS:** được ghi vào class file nhưng thông thường không xuất hiện qua các API reflection đọc runtime annotation.
- **RUNTIME:** được ghi vào class file và có thể được JVM công bố cho reflection.

Ở cấp class file, annotation nằm trong các thuộc tính như **RuntimeVisibleAnnotations** và **RuntimeInvisibleAnnotations**; annotation trên phương thức, tham số hoặc kiểu sử dụng có vị trí metadata tương ứng. Trình phân tích annotation phải đọc đúng cấu trúc, kiểu giá trị và tham chiếu constant pool. Nếu dữ liệu mã hóa của annotation bị hỏng hoặc sai cấu trúc, Java runtime có thể ném AnnotationFormatError.

Các nguyên nhân thường đáng điều tra:

1. **Tệp .class bị biến đổi sai:** bytecode instrumentation, weaving, obfuscation, shading hoặc công cụ hậu xử lý phát sinh annotation attribute không hợp lệ.
2. **Artifact bị hỏng hoặc ghép không nhất quán:** class file trong JAR khác với phiên bản mong đợi, bị thay thế sai hoặc bị hỏng trong quá trình phát hành.
3. **Công cụ sinh bytecode tự xây dựng metadata sai:** ví dụ dùng ASM hoặc thư viện thao tác class file nhưng viết sai kiểu phần tử hay định dạng annotation.
4. **Class loader nạp một bản khác:** ứng dụng kiểm tra mã nguồn mới nhưng runtime lại nạp class cũ hoặc JAR khác trên classpath.

Không nên gọi mọi lỗi annotation lúc runtime là AnnotationFormatError. Ví dụ, thiếu phần tử annotation bắt buộc khi đọc có thể dẫn đến **IncompleteAnnotationException**; giá trị không còn tương thích với khai báo annotation có thể gây **AnnotationTypeMismatchException**; hằng enum mất đi có thể dẫn đến **EnumConstantNotPresentException**; kiểu được tham chiếu không tồn tại có thể dẫn đến **TypeNotPresentException**. Các lỗi này có ý nghĩa chẩn đoán riêng.

### 2.2. Ví dụ reflection chạy đúng trong Java 17+

Ví dụ sau là **đường chạy bình thường**, nhằm xác định thời điểm API reflection yêu cầu runtime đọc annotation. Mã Java nguồn hợp lệ này không cố tạo bytecode hỏng để kích hoạt AnnotationFormatError.

Tệp **demo/InspectAnnotations.java**:

~~~java
package demo;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Role {
    String value();
}

@Role("service")
public class InspectAnnotations {
    public static void main(String[] args) {
        Role role = InspectAnnotations.class.getAnnotation(Role.class);
        System.out.println("role=" + role.value());
    }
}
~~~

Biên dịch và chạy khi đang đứng ở thư mục chứa thư mục con **demo**:

~~~bash
javac -d out/classes demo/InspectAnnotations.java
java -cp out/classes demo.InspectAnnotations
~~~

Đầu ra chính xác khi mã và class file còn nguyên vẹn:

~~~text
role=service
~~~

Lời gọi **Class.getAnnotation(Role.class)** là ví dụ về điểm truy cập metadata. Trong chương trình thật, stack trace có thể xuất phát từ các lời gọi như **getDeclaredAnnotations()**, từ framework quét annotation, hoặc từ một lớp Java reflection bên trong. Chỉ riêng việc khai báo annotation trên nguồn Java không tự gây ra AnnotationFormatError.

### 2.3. Khoanh vùng AnnotationFormatError theo chứng cứ

Thực hiện theo thứ tự để tìm **class file thực sự gây lỗi**:

1. **Giữ nguyên stack trace đầy đủ**, kể cả chuỗi **Caused by** nếu có. Xác định thao tác nào đang đọc annotation: quét component, reflection trên class, method, field, parameter hay thư viện mapping.
2. **Xác định class được nạp từ đâu.** Trong mã chẩn đoán, có thể in **SomeClass.class.getProtectionDomain().getCodeSource()** khi CodeSource có mặt; hoặc kiểm tra classpath/module path và nội dung JAR. Đừng mặc định class đến từ thư mục build vừa biên dịch.
3. **Đọc metadata trong đúng artifact gây lỗi** bằng **javap -v -p**. Ví dụ:

~~~bash
javap -classpath app.jar -v -p demo.InspectAnnotations
~~~

Quan sát các thuộc tính **RuntimeVisibleAnnotations**, **RuntimeInvisibleAnnotations**, constant pool và vị trí class/method tương ứng. Nếu javap không phân tích được class file, đó cũng là dấu hiệu cần điều tra; thông báo thực tế phụ thuộc phiên bản JDK và dạng hỏng.

4. **Đối chiếu trước và sau biến đổi bytecode.** Nếu source được javac tạo ra chạy ổn nhưng artifact sau instrumentation/obfuscation lỗi, tạm tắt lần lượt các bước biến đổi để cô lập công cụ gây hỏng. So sánh checksum của các bản .class/JAR.
5. **Build sạch và thử artifact tối thiểu** trong đúng JDK/classpath đang gặp lỗi. Chỉ sau khi đã lưu chứng cứ mới xóa output cũ, cập nhật dependency hoặc phục hồi artifact.
6. **Kiểm tra tương thích thư viện sửa bytecode và định dạng class file.** Nếu tool cũ không hiểu định dạng do bản JDK mới sinh ra, nâng cấp tool hoặc thay cấu hình phù hợp; không sửa ngẫu nhiên annotation ở source để che dấu bytecode sai.

Ví dụ dấu vết khoanh vùng bằng Java (mã minh họa đặt trong nơi có thể tham chiếu **demo.InspectAnnotations**):

~~~java
Class<?> target = demo.InspectAnnotations.class;
var source = target.getProtectionDomain().getCodeSource();
System.out.println(source == null ? "<unknown code source>" : source.getLocation());
target.getDeclaredAnnotations(); // một điểm có thể kích hoạt phân tích metadata
~~~

Đoạn này **không phải chương trình độc lập**; kết quả dòng in phụ thuộc nơi class thực tế được nạp. Nếu ứng dụng dùng nhiều class loader, cần xác minh cả class loader và module.

Vì AnnotationFormatError là **Error**, xử lý chuẩn là sửa dữ liệu class file hoặc công cụ tạo ra nó. Chỉ bắt lỗi tại ranh giới công cụ chẩn đoán nếu cần ghi chứng cứ; không nuốt Error rồi để ứng dụng chạy tiếp như thể metadata hợp lệ.

## 3. FilerException: nguyên nhân và quy tắc tạo tệp

### 3.1. Filer hoạt động trong annotation processing

Annotation processor chạy trong javac qua API **javax.annotation.processing**. Môi trường **ProcessingEnvironment** cung cấp **Filer**, một đối tượng dùng để tạo source, class và resource:

- **createSourceFile(qualifiedName, originatingElements...)**: xin tạo tệp mã nguồn Java theo tên kiểu.
- **createClassFile(qualifiedName, originatingElements...)**: xin tạo class file.
- **createResource(location, packageName, relativeName, originatingElements...)**: xin tạo tài nguyên tại vị trí và đường dẫn được chỉ định.

Một lần xử lý annotation có thể gồm **nhiều round**. Khi một processor tạo mã nguồn mới, javac có thể đưa mã nguồn đó vào round kế tiếp. Trong cùng một lần annotation processing, Filer giữ sổ các tên/tệp đã tạo; tạo lại cùng một tên hoặc cố tạo một kiểu nằm trong tập input ban đầu có thể ném **FilerException**. Các processor khác nhau cũng có thể va chạm nếu cùng phát sinh một tên.

Lưu ý quan trọng: **một file đã tồn tại từ build trước không đồng nghĩa chắc chắn sẽ có FilerException**. Đặc trưng quyết định là trạng thái tạo tệp trong **lần chạy xử lý hiện tại**, quy định của Filer và các tên input. Xóa thư mục generated có thể hữu ích khi điều tra build bẩn, nhưng không chữa được lệnh **createSourceFile** lặp ngay trong một lượt compile.

### 3.2. Ví dụ tối thiểu cố ý tạo FilerException

Có thể chạy ví dụ dưới đây trên **JDK 17 trở lên**. Đây là lỗi **có chủ đích**: processor tạo cùng một tên nguồn hai lần. Ba file đặt trong thư mục **demo**.

Tệp **demo/GenerateMarker.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateMarker {
}
~~~

Tệp **demo/App.java**:

~~~java
package demo;

@GenerateMarker
public class App {
    public static void main(String[] args) {
        System.out.println("App started");
    }
}
~~~

Tệp **demo/DuplicateProcessor.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class DuplicateProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {
            String name = "demo.GeneratedApp";
            try {
                JavaFileObject file =
                        processingEnv.getFiler().createSourceFile(name, element);
                try (Writer writer = file.openWriter()) {
                    writer.write("package demo;\n"
                            + "public class GeneratedApp {}\n");
                }

                // Cố ý sai: tên này đã được tạo trong cùng lần processing.
                processingEnv.getFiler().createSourceFile(name, element);
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Duplicate output: " + ex.getClass().getSimpleName(),
                        element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "I/O: " + ex.getMessage(), element);
            }
        }
        return true;
    }
}
~~~

Tạo sẵn ba thư mục output **out/processor**, **out/classes**, **out/generated**, rồi chạy từ thư mục cha của **demo**:

~~~bash
javac -proc:none -d out/processor demo/GenerateMarker.java demo/DuplicateProcessor.java
javac -cp out/processor -processorpath out/processor -processor demo.DuplicateProcessor -s out/generated -d out/classes demo/App.java
~~~

Lệnh thứ nhất thành công. Lệnh thứ hai **dự kiến thất bại**; phần cốt lõi của diagnostic chứa:

~~~text
Duplicate output: FilerException
~~~

Dòng vị trí, số lượng lỗi và lời giải thích thêm có thể khác theo javac/JDK. Không có stdout từ **java demo.App** cho trường hợp biên dịch thất bại. Kết luận chính xác là **lệnh createSourceFile thứ hai trong cùng một lượt gây ra FilerException**, dù lần thứ nhất đã đóng Writer đúng cách.

Trên Windows, có thể tạo thư mục bằng PowerShell **New-Item -ItemType Directory -Force**; trên shell Unix dùng **mkdir -p**. Hai lệnh **javac** ở trên không phụ thuộc ký tự phân cách classpath vì mỗi đường dẫn chỉ chứa một entry.

### 3.3. Sửa processor: tên đầu ra ổn định và chỉ ghi một lần

Thay **demo/DuplicateProcessor.java** bằng bản **demo/SafeProcessor.java** dưới đây (giữ **GenerateMarker.java** và **App.java**). Mỗi lớp được đánh dấu nhận một tên được suy ra từ tên lớp; tập **generatedNames** giúp phòng trường hợp processor gặp lại cùng tên trong các round.

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class SafeProcessor extends AbstractProcessor {
    private final Set<String> generatedNames = new HashSet<>();

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {
            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String name = "demo.Generated" + type.getSimpleName();
            if (!generatedNames.add(name)) {
                continue; // Đã tạo hoặc đã quyết định tạo tên này.
            }

            try {
                JavaFileObject file =
                        processingEnv.getFiler().createSourceFile(name, type);
                try (Writer writer = file.openWriter()) {
                    writer.write("package demo;\n"
                            + "public class Generated" + type.getSimpleName()
                            + " {}\n");
                }
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Tên đầu ra bị trùng: " + name + " - " + ex.getMessage(),
                        type);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không tạo được " + name + ": " + ex.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

Biên dịch processor được sửa, rồi biên dịch ứng dụng:

~~~bash
javac -proc:none -d out/processor demo/GenerateMarker.java demo/SafeProcessor.java
javac -cp out/processor -processorpath out/processor -processor demo.SafeProcessor -s out/generated -d out/classes demo/App.java
java -cp out/classes demo.App
~~~

Đầu ra chính xác của lệnh **java**:

~~~text
App started
~~~

Tệp sinh ra là **out/generated/demo/GeneratedApp.java** và class tương ứng được biên dịch trong **out/classes**. Nếu cần chạy lại ví dụ từ đầu để loại bỏ dấu vết thử nghiệm, hãy lưu các log cần thiết rồi xây dựng trong thư mục output mới hoặc làm sạch đúng thư mục output thử nghiệm.

**Giới hạn của cách sửa:** Set ở đây chỉ ngăn chính **SafeProcessor** tạo lặp tên. Nó không giải quyết va chạm với processor khác, với tên kiểu đang là input, hoặc trường hợp nhiều lớp ở package khác nhau có cùng simple name nhưng cùng ánh xạ tới **demo.GeneratedX**. Trong hệ thống thật, cần thiết kế ánh xạ tên từ qualified name hoặc khóa định danh thích hợp, công khai quy tắc ai sở hữu từng output và tránh tạo đè cùng đường dẫn từ nhiều processor.

### 3.4. Các trường hợp FilerException thường gặp

| Tình huống | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Cùng một processor gọi createSourceFile hai lần cho cùng tên | Log cùng qualified name xuất hiện hai lần trong một compile | Theo dõi tên đã tạo; chỉ gọi tạo một lần |
| Processor được chạy qua nhiều round và tạo lại tên cũ | Lần sau cùng tên nhưng round khác | Kiểm tra roundEnv, log round và tên; tránh viết lại |
| Hai processor sinh cùng một kiểu hoặc resource | Cùng đường dẫn, hai processor/trigger | Phân định quyền sở hữu output, cấu hình processor, đổi tên hợp lệ |
| Processor cố tạo source trùng với kiểu đầu vào | Tên sinh giống tên file đang được javac biên dịch | Không generate lên source input, đổi tên output |
| Tên đầu ra được tạo từ simple name không đủ duy nhất | Hai input khác nhau quy về một GeneratedX | Dùng tên đầy đủ hoặc thuật toán ánh xạ bảo đảm uniqueness |
| Incremental build tái chạy công đoạn và gây chồng chéo | Chỉ lỗi với cấu hình build hoặc processor cụ thể | Phân biệt lỗi trùng trong một invocation với stale output; xem processor path, generated-source roots, cache và lịch sử lần chạy |

**originatingElements** truyền vào createSourceFile giúp công cụ incremental processing biết output gắn với input nào, nhưng **không phải** khóa ngăn trùng tự động. Không đổi tên file bằng số ngẫu nhiên để lẩn tránh FilerException: làm vậy khiến output mất tính tái lập và dễ tăng file rác.

## 4. Quy trình khoanh vùng nhanh khi chỉ có log lỗi

### Bước 1: Xác định giai đoạn

- Lỗi ở lệnh **javac**, Maven compile, Gradle compileJava hoặc kapt/ksp tương ứng? Tìm **FilerException** trước và phân tích processor. Đừng vội kết luận source annotation có cấu trúc sai.
- Lỗi khi JVM đang chạy test/app, thường đi cùng **java.lang.reflect** hoặc logic framework quét annotation? Tìm **AnnotationFormatError** và truy vết class file runtime.
- Nếu cả hai lỗi có mặt trong chuỗi build/test, xử lý lần lượt theo giai đoạn và artifact; chưa đủ chứng cứ để khẳng định cùng một nguyên nhân.

### Bước 2: Thu hẹp phạm vi bằng các lệnh có mục tiêu

Với **FilerException**, chạy lại lệnh compile có bật thông tin vòng xử lý (JDK hỗ trợ các tùy chọn này):

~~~bash
javac -XprintRounds -XprintProcessorInfo -cp out/processor -processorpath out/processor -processor demo.DuplicateProcessor -s out/generated -d out/classes demo/App.java
~~~

Đọc tên processor được kích hoạt, annotation nhận được và vòng processing. Hai tùy chọn trên **không in tự động từng createSourceFile**; thêm log **processor class / round / output qualified name / originating element** ngay trước thao tác tạo. Trong dự án Gradle/Maven, áp các compiler args vào task compile thực tế; đừng giả định lệnh javac mẫu chính là lệnh mà build tool dùng.

Với **AnnotationFormatError**, sử dụng **javap -v -p** trên bản class/JAR đang được runtime nạp, rồi so sánh với bản compile gốc. Có thể tạm cô lập một plugin weave/transform, rút gọn classpath hoặc dựng test reflection nhỏ tái hiện lỗi.

### Bước 3: Dựng bảng chứng cứ trước khi sửa

Ghi ngắn gọn mỗi lần tái hiện:

| Trường cần ghi | AnnotationFormatError | FilerException |
| --- | --- | --- |
| Giai đoạn | JVM/test startup/reflection | javac/processor round |
| Đối tượng chính | Class, method, annotation, nguồn JAR | Qualified name/path output, processor |
| Phiên bản liên quan | JDK runtime, JAR, bytecode transformer | JDK compiler, build tool, processor |
| So sánh hữu ích | Class gốc với class sau biến đổi | Tên output trong round trước và round hiện tại |
| Tiêu chí xác nhận sửa | Reflection trên đúng artifact không còn lỗi | Compile cùng input/processor path không còn trùng và output sinh đúng |

### Bước 4: Sửa đúng nguyên nhân và xác nhận hồi quy

- Với bytecode annotation sai: phục hồi hoặc tạo lại artifact hợp lệ; sửa công cụ biến đổi/sinh bytecode; chạy lại test phản chiếu annotation trên artifact phát hành.
- Với FilerException: định nghĩa tên output có thể dự đoán; đảm bảo tối đa một lần tạo trong một processing invocation; kiểm tra nguồn input và processor cạnh tranh; chạy thử từ output sạch và cả incremental build nếu dự án có cơ chế đó.
- Không xử lý bằng cách **catch rồi bỏ qua** FilerException: compile có thể báo thành công nhưng file sinh thiếu hoặc nội dung đã cũ. Hãy phát diagnostic rõ ràng bằng **Messager** hoặc cho build thất bại có thông tin.

## 5. Những ngộ nhận cần tránh

1. **“AnnotationFormatError là lỗi cú pháp annotation trong Java source.”** Sai: lỗi cú pháp, sai @Target, sai kiểu element thường đã được javac báo lúc biên dịch; AnnotationFormatError nói về phân tích metadata trong class file.
2. **“Chỉ cần xóa thư mục build là chữa mọi FilerException.”** Sai: hai lời gọi tạo cùng tên trong một compile vẫn va chạm kể cả output ban đầu rỗng.
3. **“Trùng tệp trên đĩa luôn gây FilerException.”** Sai: phải xem contract và trạng thái của Filer trong lần processing hiện tại, cùng tập source/class input.
4. **“@Retention(SOURCE) có thể truy xuất qua reflection giống RUNTIME.”** Sai: SOURCE không được giữ để reflection runtime trả về.
5. **“Cứ gặp FilerException thì đổi tên file bằng timestamp.”** Sai: cách này phá tính xác định, gây tích lũy artifact và có thể che giấu hai processor cùng sở hữu output.
6. **“Set chống trùng là đủ cho mọi build.”** Sai: cần cả uniqueness giữa các input, ownership giữa các processor và cấu hình build/incremental phù hợp.
7. **“Bắt AnnotationFormatError và chạy tiếp là ổn.”** Không an toàn: lỗi thường báo metadata class file cần sửa; khôi phục ở ranh giới chẩn đoán không thay thế việc xử lý nguyên nhân.

## 6. Tự kiểm tra

**Câu 1.** Processor gọi createSourceFile cho một tên trong round 1 rồi gọi lại cùng tên ở round 2. Cần tìm lỗi nào trước?  
**Đáp án:** FilerException. Kiểm tra việc tạo trùng tên xuyên round trong cùng lượt annotation processing.

**Câu 2.** Một framework chỉ gặp lỗi khi gọi getDeclaredAnnotations trên một class đã qua obfuscation; bản .class trước obfuscation đọc bình thường. Bước kiểm tra nào có giá trị nhất?  
**Đáp án:** Xác định artifact/JAR thực tế được nạp, dùng javap -v -p đối chiếu annotation attributes của hai bản, rồi kiểm tra công cụ obfuscation.

**Câu 3.** Chuyển @Retention(SOURCE) sang RUNTIME có tự sửa bytecode annotation bị mã hóa sai không?  
**Đáp án:** Không. Retention quyết định lưu giữ và khả năng reflection truy cập; bytecode malformed phải được sửa ở pipeline biên dịch/biến đổi/phát hành.

**Câu 4.** Vì sao processor vẫn có thể bị FilerException sau khi đã dùng Set ghi nhớ tên nó tạo?  
**Đáp án:** Tên đó có thể trùng với source đầu vào, output của processor khác, hoặc quy tắc ánh xạ tên giữa các phần tử không duy nhất. Set chỉ bao phủ các lời gọi mà chính processor theo dõi.

**Câu 5.** Có nên bỏ qua FilerException để cho Gradle báo compile thành công?  
**Đáp án:** Không. Chẩn đoán rõ tên output và nguyên nhân, sửa việc tạo trùng rồi xác nhận output sinh đúng; nuốt lỗi có thể để lại class/source cũ hoặc thiếu.

## 7. Ghi nhớ để áp dụng

**AnnotationFormatError → khoanh vùng class file, annotation metadata, classpath/class loader và công cụ biến đổi bytecode. FilerException → khoanh vùng processor, round, tên file/tên kiểu đầu ra, input ban đầu và lời gọi Filer bị lặp.** Đọc stack trace cùng artifact thực tế, tái hiện trên môi trường tối thiểu và xác nhận sửa bằng việc chạy lại chính giai đoạn đã từng thất bại.
