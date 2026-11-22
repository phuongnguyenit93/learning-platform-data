# Tạo đầu ra ổn định và phối hợp nhiều annotation processor trong Java

## 1. Bài toán: cùng input phải tạo cùng output

Với annotation processing (JSR 269), `javac` có thể nạp nhiều bộ xử lý để kiểm tra khai báo, phát diagnostic và sinh mã Java hoặc tài nguyên. Nếu hai lần build dùng cùng mã nguồn, annotation, cấu hình, JDK và dependency mà processor tạo ra hai file có nội dung khác nhau **không vì lý do nghiệp vụ**, hệ thống rất khó kiểm thử và cache hiệu quả.

Ví dụ, một processor quét các class gắn `@ServiceEntry` và tạo danh sách:

~~~text
demo.AlphaService
demo.ZebraService
~~~

Nếu lần build khác tự ý đảo thứ tự hai dòng, dù đầu vào không thay đổi, nội dung file vẫn khác. Snapshot test báo thay đổi; cache theo hash có thể bị vô hiệu; diff khiến người review khó tìm sửa đổi thật.

**Đầu ra ổn định (deterministic generation)** nghĩa là với cùng bộ đầu vào và quy tắc chuẩn hóa, processor tạo cùng tên file, bytes, thứ tự bản ghi và cấu trúc mã nguồn.

**Phối hợp nhiều processor** nghĩa là một phiên compile có thể có nhiều processor với trách nhiệm khác nhau nhưng không phụ thuộc vào thứ tự chạy ngẫu nhiên, không bỏ sót source được sinh ở round sau và không tranh chấp ghi một file.

Hai mục tiêu có liên hệ chặt chẽ: processor tạo output ổn định phải kiểm soát cả **thứ tự dữ liệu**, **thời điểm ghi** và **quyền sở hữu output**.

## 2. Ba cấp ổn định cần phân biệt

### 2.1. Nội dung file sinh ổn định

Cùng các annotated elements và các cấu hình được công bố, một processor cần sinh đúng cùng text. Các nguồn bất ổn thường gặp:

- Duyệt `HashMap`, `HashSet` hoặc tập `Element` mà không có thứ tự được bảo đảm.
- Chèn timestamp, `UUID.randomUUID()`, random number hay `System.identityHashCode` vào file.
- Dùng absolute path, username hoặc môi trường máy build khi những giá trị đó không phải input nghiệp vụ.
- Để encoding hoặc newline phụ thuộc máy, dùng `Locale.getDefault()` cho nội dung máy đọc được.
- Ghi annotation elements theo một thứ tự tình cờ của Reflection hoặc model API.
- Lấy `toString()` của object làm định dạng canonical dù không có contract ổn định.

Giải pháp là biến input thành **các giá trị chuẩn hóa**, sort theo một khóa có nghĩa, dùng charset/line ending rõ ràng, và không thêm thông tin thay đổi giữa builds nếu nó không thực sự cần thiết.

### 2.2. Tên và đường dẫn file sinh ổn định

Một processor phải quyết định output name từ một khóa bền vững, ví dụ qualified type name: `demo.Alpha` sinh `demo.AlphaGenerated`. Không dùng thứ tự duyệt làm suffix kiểu `Generated1`, `Generated2` nếu thứ tự đó không được chuẩn hóa.

Tên phải tránh va chạm: hai input khác nhau không được cùng yêu cầu `Filer.createSourceFile("demo.SameName")`. Với resource tổng hợp, quy định một processor **duy nhất** sở hữu `META-INF/demo/index.txt`.

### 2.3. Toàn bộ artifact reproducible

File sinh có bytes ổn định **chưa chứng minh** cả build/JAR là reproducible. Tệp `.class`, file lưu trữ, archive entry timestamps/order, classpath, compiler flags và phiên bản dependency cũng ảnh hưởng artifact cuối. Cần thử nghiệm riêng nếu mục tiêu là hai JAR byte-for-byte giống nhau.

## 3. Những API Java liên quan

Phần lớn annotation processors kế thừa `javax.annotation.processing.AbstractProcessor`, có hợp đồng gốc là `javax.annotation.processing.Processor`.

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Phân tích mô hình và tạo output.
    return true;
}
~~~

Đây chỉ là **fragment**, cần class processor và imports thích hợp.

| API | Vai trò |
| --- | --- |
| `Processor` | Hợp đồng `init`, supported annotation types/options/source, `process` và claiming |
| `AbstractProcessor` | Lớp nền thực hiện sẵn một phần hợp đồng và giữ `processingEnv` |
| `ProcessingEnvironment` | Dịch vụ compiler như `getFiler()`, `getMessager()`, `getElementUtils()`, `getTypeUtils()` |
| `RoundEnvironment` | Root elements, annotation occurrences và trạng thái của mỗi processing round |
| `Filer` | Tạo source/class/resource trong vùng output do compiler quản lý |
| `Messager` | Gửi `Diagnostic.Kind.ERROR`, `WARNING`, `NOTE` kèm thông tin vị trí |
| `TypeElement` / `Element` | Mô hình khai báo Java, không phải `Class<?>` runtime |
| `TypeMirror` / `Types` | Biểu diễn kiểu và kiểm tra quan hệ kiểu tại compile-time |

Tại Java 17, những API này thuộc module `java.compiler`, với tên package chuẩn **`javax.annotation.processing`**, không đổi sang `jakarta.annotation.processing`.

`@SupportedAnnotationTypes` xác định annotation type mà processor xử lý; `@SupportedSourceVersion(SourceVersion.RELEASE_17)` công bố hỗ trợ ngôn ngữ Java 17. Hai annotation đó **không tự kích hoạt processor**: compiler vẫn cần nạp nó qua `-processor`, service registration hoặc cấu hình build tool.

### Claiming không phải điều khiển thành công

`process(...)` trả `true` tức processor **claim** các annotation types được giao trong round; `false` nghĩa là không claim chúng, cho processor khác còn cơ hội. Không dùng `return false` để báo lỗi nghiệp vụ. Hãy dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)`.

Nếu hai processor xử lý **cùng annotation type**, việc một processor claim có thể khiến processor khác không còn nhận annotation đó theo cùng cơ chế điều phối. Thiết kế phải có chủ đích; không dựa vào giả định hai processor nhất định được gọi theo thứ tự mong muốn.

## 4. Canonical hóa thứ tự, ký tự và tên

### 4.1. Sort trước khi ghi

`RoundEnvironment.getElementsAnnotatedWith(...)` trả về một tập element, không phải một danh sách với thứ tự output được thiết kế riêng cho bạn.

Đoạn minh họa **bên trong processor**:

~~~java
List<String> names = new ArrayList<>();

for (Element element : roundEnv.getElementsAnnotatedWith(MyMarker.class)) {
    if (element instanceof TypeElement type) {
        names.add(type.getQualifiedName().toString());
    }
}

names.sort(Comparator.naturalOrder());

for (String name : names) {
    writer.write(name);
    writer.write(10); // LF
}
~~~

Fragment cần `MyMarker`, `writer` và imports tương ứng. `TypeElement.getQualifiedName()` tốt hơn `getSimpleName()` khi cần phân biệt class trùng tên ở các package khác nhau. Nếu nghiệp vụ chỉ cần tập tên duy nhất, `TreeSet<String>` có thể kết hợp **sắp xếp và loại trùng**. Nhưng nếu duplicates mang ý nghĩa nghiệp vụ, đừng dùng Set chỉ để xóa chúng.

### 4.2. Định dạng bytes cố định

Chủ động dùng `StandardCharsets.UTF_8` và newline LF:

~~~java
try (Writer writer = new OutputStreamWriter(
        file.openOutputStream(), StandardCharsets.UTF_8)) {
    writer.write("alpha");
    writer.write(10); // ký tự LF
    writer.write("zebra");
    writer.write(10);
}
~~~

Đây là fragment có `FileObject file`. Ghi `10` qua `Writer.write(int)` là cách minh họa rõ output newline LF. Không dùng `System.lineSeparator()` nếu định dạng yêu cầu LF trên mọi máy.

Nếu sinh Java string literal từ giá trị annotation tùy ý, cần **escape** `"`, backslash, ký tự điều khiển và các tình huống Unicode phù hợp; không ghép chuỗi người dùng trực tiếp vào source rồi mong luôn là Java hợp lệ.

### 4.3. Một output chỉ có một owner

`Filer` không phải shared mutable file system cho phép processor cuối cùng ghi đè. Nếu hai processor đều muốn tạo `META-INF/demo/index.txt`, có thể xảy ra `FilerException` hoặc diagnostic lỗi. Giải pháp là giao cho một **aggregator processor** viết file ấy; các producer đóng góp metadata qua mô hình compiler hoặc mỗi producer ghi resource riêng theo namespace của mình.

## 5. Phối hợp bằng processing rounds, không bằng thứ tự thực thi

Mô hình JSR 269 cho phép source do processor tạo ở một round được compiler nhận trong **round kế tiếp**.

~~~text
Round đầu:
    @Seed trên Alpha và Zebra
             |
             v
    ProducerProcessor tạo AlphaGenerated và ZebraGenerated
             |
             v
Round kế:
    @GeneratedItem trên các class mới
             |
             v
    IndexProcessor thu qualified names
             |
             v
Final round:
    IndexProcessor ghi resource đã sort, không sinh thêm Java source
             |
             v
Ứng dụng đọc index.txt khi chạy
~~~

Đây là giao thức phối hợp có **ranh giới rõ giữa các rounds**. Không cần khẳng định processor B chạy ngay sau A trong cùng round. B đọc các annotated elements từ `RoundEnvironment` của compiler, thay vì mở một file A có thể vẫn đang ghi.

Khi cần tổng hợp đầu ra trên **nhiều rounds**, aggregator nên tích lũy state trong vòng đời processor và hoàn tất vào giai đoạn phù hợp. **Final round** (`processingOver() == true`) phù hợp để hoàn tất một **resource** không cần compiler xử lý tiếp, nhưng **không phải lúc tạo Java source mới rồi trông chờ compiler chạy thêm round**.

## 6. Demo Java 17: hai processor hợp tác tạo resource ổn định

Ví dụ hoàn chỉnh gồm năm tệp ban đầu, sử dụng JDK 17+, không cần thư viện bên thứ ba.

~~~text
src/
  demo/
    Seed.java
    GeneratedItem.java
    ProducerProcessor.java
    IndexProcessor.java
    Demo.java
~~~

Mục tiêu: `ProducerProcessor` sinh source cho hai class đầu vào; `IndexProcessor` nhận các class mới qua round kế tiếp và tạo file `META-INF/demo/index.txt`. File được sắp xếp theo qualified name, không phụ thuộc thứ tự khai báo trong source.

### 6.1. `src/demo/Seed.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface Seed {
}
~~~

`@Seed` được processor A nhận tại compile-time. `SOURCE` là đủ; runtime không cần đọc annotation này.

### 6.2. `src/demo/GeneratedItem.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GeneratedItem {
}
~~~

Annotation trung gian cho B phát hiện Java source do A sinh. Đây là **tín hiệu giữa hai processors qua model source của compiler**, không phải sự kiện runtime.

### 6.3. `src/demo/ProducerProcessor.java`

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Seed")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ProducerProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        List<TypeElement> inputs = new ArrayList<>();

        for (Element element : roundEnv.getElementsAnnotatedWith(Seed.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind()
                            != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Seed requires a top-level class",
                        element);
                continue;
            }
            inputs.add((TypeElement) element);
        }

        inputs.sort(Comparator.comparing(
                type -> type.getQualifiedName().toString()));

        for (TypeElement type : inputs) {
            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();

            if (pkg.isEmpty()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@Seed requires a named package",
                        type);
                continue;
            }

            String simple = type.getSimpleName().toString();
            String generated = simple + "Generated";
            String name = pkg + "." + generated;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(name, type);

                try (Writer writer = new OutputStreamWriter(
                        source.openOutputStream(), StandardCharsets.UTF_8)) {
                    writer.write("package " + pkg + ";");
                    writer.write(10);
                    writer.write("@demo.GeneratedItem");
                    writer.write(10);
                    writer.write("public final class " + generated + " {");
                    writer.write(10);
                    writer.write("    private " + generated + "() {}");
                    writer.write(10);
                    writer.write("}");
                    writer.write(10);
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + name + ": " + error.getMessage(),
                        type);
            }
        }
        return true;
    }
}
~~~

Cơ chế:

1. `@SupportedAnnotationTypes("demo.Seed")` giúp A chỉ xử lý loại metadata được giao.
2. Processor kiểm tra **top-level class** trước khi tạo tên để tránh trường hợp nested type không được hỗ trợ bởi quy tắc đơn giản của demo.
3. Danh sách `TypeElement` được sort theo qualified name.
4. `getElementUtils().getPackageOf(type)` lấy package từ mô hình Java tại compile-time.
5. `Filer.createSourceFile(name, type)` tạo đúng một source theo qualified name; `type` là *originating element* cung cấp nguồn gốc cho toolchain.
6. Mã source tạo ra có annotation `@demo.GeneratedItem` để B tiếp nhận ở round sau.
7. Writer được đóng bằng try-with-resources và dùng UTF-8, LF cố định.
8. Lỗi tạo file được báo bằng `Messager`, không cố retry hoặc overwrite.

Với demo, đầu vào là các class `Alpha` và `Zebra`, nên hai tên sinh ra là `demo.AlphaGenerated` và `demo.ZebraGenerated`. Nếu class `AlphaGenerated` đã tồn tại từ source khác hoặc processor khác sở hữu cùng tên, tạo file mới sẽ xung đột; đó là lỗi cần sửa ở chính sách đặt tên.

### 6.4. `src/demo/IndexProcessor.java`

~~~java
package demo;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GeneratedItem")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class IndexProcessor extends AbstractProcessor {
    private final SortedSet<String> names = new TreeSet<>();
    private boolean written;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (!roundEnv.processingOver()) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(GeneratedItem.class)) {
                if (element.getKind() == ElementKind.CLASS) {
                    TypeElement type = (TypeElement) element;
                    names.add(type.getQualifiedName().toString());
                }
            }
            return true;
        }

        if (!written && !roundEnv.errorRaised()) {
            written = true;
            try {
                FileObject file = processingEnv.getFiler().createResource(
                        StandardLocation.CLASS_OUTPUT,
                        "",
                        "META-INF/demo/index.txt");

                try (Writer writer = new OutputStreamWriter(
                        file.openOutputStream(), StandardCharsets.UTF_8)) {
                    for (String name : names) {
                        writer.write(name);
                        writer.write(10);
                    }
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate index: " + error.getMessage());
            }
        }

        return true;
    }
}
~~~

`IndexProcessor` thực hiện **aggregating**:

- Chỉ hỗ trợ `@GeneratedItem`, nên không tranh claim `@Seed` với A.
- Tích lũy tên qua **nhiều rounds** trong `TreeSet` để có thứ tự và tránh thêm một qualified name nhiều lần.
- Chỉ tạo **resource** khi `processingOver()`; resource không cần Java compiler biên dịch tiếp.
- `written` ngăn logic bị gọi ghi hai lần nếu implementation sau này mở rộng.
- `errorRaised()` được dùng làm chính sách bỏ qua index ở final round khi compilation đã có diagnostic lỗi từ trước.
- B **không** tìm kiếm tệp A vừa tạo bằng cách đọc thư mục build. Nó sử dụng annotation source qua `RoundEnvironment`.

Lưu ý: dùng `TreeSet` ở đây đúng vì index lưu **tên class duy nhất**. Nếu nghiệp vụ cần lưu nhiều bản ghi khác nhau có cùng tên, phải định nghĩa khóa và cơ chế giải quyết xung đột chứ không mặc nhiên loại trùng.

### 6.5. `src/demo/Demo.java`

~~~java
package demo;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

@Seed
class Zebra {
}

@Seed
class Alpha {
}

public class Demo {
    public static void main(String[] args) throws Exception {
        String resource = "META-INF/demo/index.txt";

        try (InputStream in =
                Demo.class.getClassLoader().getResourceAsStream(resource)) {
            if (in == null) {
                throw new IllegalStateException("Missing " + resource);
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        }
    }
}
~~~

Chú ý `Zebra` nằm **trước** `Alpha` trong file. Đây là kiểm tra trực quan rằng output cuối không phụ thuộc thứ tự source.

### 6.6. Biên dịch bằng `javac` và chạy bằng `java`

Mở terminal ở **thư mục cha của `src`**. Ví dụ lệnh tạo thư mục với Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/classes, build/generated | Out-Null
~~~

**Bước 1: biên dịch hai annotation types và hai processors.**

~~~bash
javac -encoding UTF-8 -d build/processor src/demo/Seed.java src/demo/GeneratedItem.java src/demo/ProducerProcessor.java src/demo/IndexProcessor.java
~~~

**Bước 2: biên dịch chương trình và kích hoạt cả hai processors.**

~~~bash
javac -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.ProducerProcessor,demo.IndexProcessor -s build/generated -d build/classes src/demo/Demo.java
~~~

Các tham số quan trọng:

- `-cp build/processor`: cho source ứng dụng và source sinh ra nhìn thấy `Seed`, `GeneratedItem`.
- `-processorpath build/processor`: cho compiler tìm được classes của hai processors.
- `-processor demo.ProducerProcessor,demo.IndexProcessor`: kích hoạt processor tường minh, không phụ thuộc auto-discovery.
- `-s build/generated`: thư mục Java source được tạo.
- `-d build/classes`: thư mục class và resource output.

**Kết quả dự kiến của build sạch:**

~~~text
build/generated/demo/AlphaGenerated.java
build/generated/demo/ZebraGenerated.java

build/classes/demo/Demo.class
build/classes/demo/AlphaGenerated.class
build/classes/demo/ZebraGenerated.class
build/classes/META-INF/demo/index.txt
~~~

Resource `build/classes/META-INF/demo/index.txt` chứa hai dòng UTF-8 kết thúc bằng LF:

~~~text
demo.AlphaGenerated
demo.ZebraGenerated
~~~

**Bước 3: chạy chương trình.**

~~~bash
java -cp build/classes demo.Demo
~~~

**Stdout chính xác:**

~~~text
demo.AlphaGenerated
demo.ZebraGenerated
~~~

Những thông báo của `javac` hoặc build tool, nếu có, thuộc giai đoạn compile và không phải stdout của lệnh `java` ở trên.

### 6.7. Tại sao ví dụ không cần thứ tự thực thi cố định của processors?

Ở round đầu, A thấy `@Seed` và sinh hai source mới có `@GeneratedItem`. Khi compiler tiếp nhận source đó trong round sau, B thấy `@GeneratedItem` và thêm qualified names vào tập. Khi final round đến, B viết một index đã sắp xếp. Không cần sử dụng thứ tự chạy trong **cùng round** làm giao thức truyền dữ liệu.

Cách này khác hoàn toàn với việc A ghi một file tạm, B vội mở file đó ngay trong cùng round: hành vi sau dễ phụ thuộc trạng thái flush và không phải mô hình phối hợp portable được JSR 269 khuyến nghị.

## 7. Quyền sở hữu và các dạng xung đột

**Hai processors tạo cùng tên file.** `Filer` không cung cấp cơ chế “ai ghi cuối sẽ thắng”. Có thể nhận `FilerException`, một `IOException`. Cần phân quyền output ngay từ thiết kế.

**Một processor tạo lại file ở round sau.** Nếu mỗi lần `process` đều gọi `createSourceFile("demo.AlphaGenerated")`, lỗi trùng tên sẽ xảy ra. Chỉ tạo khi có input thích hợp và tạo mỗi path đúng một lần.

**Hai processors đều claim cùng annotation type.** Nếu đều xử lý `@Seed` và processor trước trả `true`, processor khác có thể không nhận `@Seed` trong cùng round. Cần đổi mô hình phân công hoặc điều chỉnh claiming có chủ đích.

**Aggregator chỉ xét round đầu.** Nếu B ghi index khi chưa có generated source ở round tiếp theo, index có thể rỗng hoặc thiếu entries. Tích lũy qua các rounds.

**Aggregator tạo Java source trong final round.** Compiler không có cam kết round bình thường tiếp theo để xử lý source vừa tạo. Final round thích hợp hơn cho resource output không yêu cầu biên dịch.

**Processor B quét toàn classpath và gọi đây là toàn bộ project.** `RoundEnvironment.getRootElements()` chỉ chứa roots liên quan tới round; không phải enumeration của mọi class trong dependency jars.

## 8. Deterministic khác incremental

Một processor có thể tạo file **ổn định** khi build sạch nhưng vẫn hoạt động **sai** khi incremental compile xóa một source.

Ví dụ trong demo, nếu xóa `Alpha`, clean build mới nên tạo index chỉ có `demo.ZebraGenerated`. Nhưng nếu build tool không chạy lại processor B hoặc không xóa artifact cũ, file index có thể bị **stale**.

Khái niệm thường gặp:

- **Isolating generator:** một output có nguồn gốc rõ ở một input, ví dụ `AlphaGenerated.java` từ `Alpha`. Truyền `originating element` cho `Filer.createSourceFile` giúp toolchain theo dõi quan hệ.
- **Aggregating generator:** một output phụ thuộc nhiều input, ví dụ một index chứa tất cả class được sinh. Thay đổi hoặc xóa một class đòi hỏi tổng hợp lại toàn bộ index.

Đây là những thuật ngữ của các toolchain hỗ trợ incremental annotation processing, **không phải hai interface riêng trong JSR 269**. Từng build tool có các yêu cầu/metadata bổ sung; demo chưa hứa hỗ trợ incremental builds trong mọi môi trường.

Khi triển khai production, cần xem tài liệu của Gradle, Maven compiler plugin hoặc công cụ build đang dùng để mô tả đúng dependencies, công bố tính incremental nếu được hỗ trợ và kiểm thử cả **add/update/delete input**.

## 9. Kế hoạch kiểm thử đầu ra ổn định

Một bộ test hữu ích gồm:

1. **Clean build hai lần:** xóa toàn bộ thư mục output, compile cùng JDK/options/dependencies, so sánh bytes của `index.txt` hoặc hash SHA-256.
2. **Đảo thứ tự input:** đổi vị trí `Alpha` và `Zebra` trong source. Index vẫn theo thứ tự `demo.AlphaGenerated` rồi `demo.ZebraGenerated`.
3. **Thêm input:** thêm `@Seed class Beta {}`. Clean build phải chứa ba dòng Alpha, Beta, Zebra theo alphabet.
4. **Xóa input:** xóa `Beta`, chạy lại clean build; index phải trở về hai dòng. Với incremental build, kiểm tra artifact cũ cũng bị loại đúng.
5. **Xung đột tên:** tạo sẵn class `AlphaGenerated` trong package `demo`. Compilation phải báo lỗi rõ, không âm thầm overwrite.
6. **Khác máy:** dùng cùng cấu hình nhưng khác OS/locale; kiểm tra UTF-8, newline LF và không ghi đường dẫn máy vào file.
7. **Hai processor:** thêm processor thứ ba vào build để thử trạng thái claim, ownership hoặc generated annotations, không dựa vào thứ tự khai báo `-processor`.

Nếu còn timestamp hoặc UUID trong generated source, hash của nó thay đổi mỗi lần build. Phải tách những thông tin thực sự là input build khỏi dữ liệu không cần thiết.

## 10. Các lỗi thường gặp

**Lỗi 1:** Tin rằng một collection hoặc `getElementsAnnotatedWith` luôn duyệt theo thứ tự source. **Sửa:** chuẩn hóa và sort theo qualified name.

**Lỗi 2:** Dùng `System.currentTimeMillis()` làm phiên bản file sinh. **Sửa:** dùng dữ liệu version được cấu hình, không dùng đồng hồ khi mục tiêu là deterministic.

**Lỗi 3:** Dùng default charset, newline của OS cho định dạng máy đọc. **Sửa:** UTF-8 và LF theo schema thống nhất.

**Lỗi 4:** Cho phép hai processors tạo cùng file. **Sửa:** một owner hoặc tách output path.

**Lỗi 5:** Processor B đợi processor A bằng polling file hệ thống. **Sửa:** sử dụng source/annotation trung gian qua compiler rounds hoặc tách các build tasks có dependency rõ.

**Lỗi 6:** `getRootElements()` được hiểu là toàn bộ project. **Sửa:** hiểu đúng phạm vi một round.

**Lỗi 7:** Ghi resource tổng hợp quá sớm. **Sửa:** tích lũy qua rounds rồi finalize khi dữ liệu đã đủ.

**Lỗi 8:** Tạo Java source mới khi `processingOver()` và trông chờ compiler biên dịch thêm. **Sửa:** tạo Java source trong các round bình thường.

**Lỗi 9:** Nghĩ `process() == false` là báo lỗi. **Sửa:** dùng `Messager` với `Diagnostic.Kind.ERROR`.

**Lỗi 10:** Tự overwrite sau `FilerException`. **Sửa:** giải quyết trùng tên/path và điều kiện sinh, không retry theo kiểu last-writer-wins.

**Lỗi 11:** Nghĩ processor có trong runtime classpath nghĩa là compiler tự chạy nó. **Sửa:** kiểm tra processor path và activation/registration.

**Lỗi 12:** Đồng nhất đầu ra deterministic với incremental correctness hay JAR reproducible. **Sửa:** kiểm thử những thuộc tính này riêng.

## 11. Tự luyện tập

**Câu 1.** Vì sao `TreeSet<String>` hợp lý cho các qualified class names được processor B thu thập?  
**Đáp án:** Vì index cần các tên duy nhất và thứ tự ổn định. Nếu duplicates có nghĩa nghiệp vụ, phải dùng cấu trúc khác.

**Câu 2.** Nếu A sinh một source có `@GeneratedItem`, B nên đọc ở đâu?  
**Đáp án:** Qua `RoundEnvironment` ở processing round tiếp theo, không cần tự mở file trung gian đang ghi.

**Câu 3.** Hai processors cùng gọi `Filer.createResource` cho `META-INF/demo/index.txt` có thể ghi đè nhau không?  
**Đáp án:** Không có hợp đồng last-writer-wins; cần một owner hoặc cơ chế tổng hợp khác.

**Câu 4.** `process(...)` trả `true` có chứng minh output đã đúng và compiler thành công không?  
**Đáp án:** Không. Nó claim annotation types, không phải phiếu chứng nhận không lỗi.

**Câu 5.** Index giống nhau giữa hai clean builds có đủ chứng minh cả JAR hoàn toàn reproducible không?  
**Đáp án:** Không. Cần xét class files, archive metadata, compiler flags, dependency, timestamps và toàn bộ bước build.

**Câu 6.** Tại sao B chờ `processingOver()` mới tạo resource?  
**Đáp án:** Để dữ liệu được tạo trong những rounds sau cũng được tích lũy, tránh bỏ sót. Resource không cần compile tiếp nên phù hợp để finalize ở final round.

**Bài thực hành:** Chạy đủ demo. Thêm `@Seed class Beta {}` vào `Demo.java`, clean build và dự đoán ba dòng đầu ra theo alphabet. Tiếp theo đảo thứ tự định nghĩa các class mà không đổi tên; index phải giữ nguyên. Sau đó xóa `Beta` và kiểm chứng clean build, rồi thử tạo class có tên `AlphaGenerated` để thấy lỗi tranh chấp tên. Hãy giải thích từng trường hợp theo **ordering**, **ownership**, **rounds** và **incremental dependency**.

## 12. Tài liệu chính thức

- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): lifecycle, declaring supported annotations, claiming.
- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): class nền của processor.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): dữ liệu mỗi round và `processingOver()`.
- [Java SE 17 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): các services `Filer`, `Messager`, `Elements`, `Types`.
- [Java SE 17 — `Filer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): tạo files và quy tắc tránh tạo trùng.
- [Java SE 17 — `Messager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): compiler diagnostics.
- [Java SE 17 — `javac`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-encoding`, `-s`, `-d`.

**Ghi nhớ:** Tạo đầu ra ổn định cần **sắp xếp, quy chuẩn hóa dữ liệu/bytes và có quyền sở hữu output rõ ràng**. Khi nhiều processors phối hợp, hãy dùng **compiler processing rounds**, tách trách nhiệm annotation và tổng hợp dữ liệu đúng thời điểm, thay vì dựa vào thứ tự thực thi hay ghi đè file.