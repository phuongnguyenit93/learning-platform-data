# Annotation Processing: Xung đột tệp sinh, vòng cuối và tính lặp lại của kết quả

## Mục tiêu

Khi dùng annotation processor để sinh mã trong quá trình biên dịch, chương trình cần tuân thủ hai hợp đồng: **Filer chỉ cho tạo một file/type một lần trong mỗi processing run**, và **source cần biên dịch phải được sinh trước final round**. Để build đáng tin cậy, kết quả còn phải nhất quán khi biên dịch lại cùng đầu vào.

Bài học này giúp bạn:

1. Hiểu **FilerException**: nguyên nhân trùng tên generated type/path, bao gồm xung đột trong một processor, giữa các processor và với source ban đầu.
2. Xác định điều gì được làm trong **RoundEnvironment.processingOver() == true** và phân biệt ý nghĩa của **errorRaised()**.
3. Thiết kế generated source theo từng annotated element và một **resource tổng hợp trong final round**.
4. Biết cách làm kết quả **deterministic**: tên ổn định, sort dữ liệu, không đưa timestamp/UUID hoặc phụ thuộc vào thứ tự duyệt.
5. Thực hiện **hai clean builds độc lập** và đối chiếu byte nội dung bằng SHA-256.
6. Chẩn đoán compiler diagnostics, stale generated files và những lỗi liên quan incremental build.

Các API thuộc **javax.annotation.processing**, **javax.lang.model** và **javax.tools** vẫn được hỗ trợ trên Java hiện đại. Ví dụ dùng **JDK 17+**, không dựa vào cơ chế ngầm hoặc công cụ lỗi thời.

## 1. Một lần xử lý gồm những gì?

Một processor có thể được compiler gọi qua nhiều vòng (**rounds**). Những source mới được sinh ở một vòng có thể trở thành input của vòng sau:

~~~text
Input ban đầu: Alpha.java, Beta.java, Main.java
                 │
                 ▼
             Round 1
             ├── tạo AlphaCard.java
             └── tạo BetaCard.java
                 │
                 ▼
             Round 2
             └── duyệt source vừa sinh, không sinh source tiếp
                 │
                 ▼
             Final round
             └── processingOver() == true
                 └── tạo resource card-names.txt (không cần compile)
                 │
                 ▼
       Compiler tạo các file .class
~~~

Ba loại output cần phân biệt:

| Output | Ví dụ | Khi nào tạo? |
| --- | --- | --- |
| **Generated Java source** | **demo.app.AlphaCard** → **AlphaCard.java** | Một non-final round để compiler có thể phân tích/biên dịch |
| **Generated resource** | **META-INF/demo/card-names.txt** | Có thể tổng hợp trong final round nếu không cần làm compilation unit |
| **Generated classfile** | **AlphaCard.class** | Thường do javac biên dịch generated source; processor không cần tự tạo classfile |

**Không có quy tắc** rằng mỗi SOURCE chỉ tạo đúng một CLASS hoặc mỗi annotated element chỉ được tạo đúng một output. Tên output và quyền sở hữu phải được thiết kế rõ.

## 2. Filer: tạo một lần, không phải ghi đè tùy ý

**processingEnv.getFiler()** cung cấp:

| Phương thức | Tác dụng |
| --- | --- |
| **createSourceFile(qualifiedName, origins...)** | Tạo Java source cho một qualified type name |
| **createClassFile(qualifiedName, origins...)** | Tạo classfile nếu processor thật sự ghi bytecode hợp lệ |
| **createResource(location, packageName, relativeName, origins...)** | Tạo file tài nguyên tại một location/path đã xác định |
| **getResource(location, packageName, relativeName)** | Truy cập resource qua file manager |

Ví dụ:

~~~java
// Mảnh minh họa bên trong AbstractProcessor, không chạy độc lập.
JavaFileObject generated = processingEnv.getFiler()
        .createSourceFile("demo.app.AlphaCard", originatingType);
try (Writer writer = generated.openWriter()) {
    writer.write("package demo.app;\npublic class AlphaCard {}\n");
}
~~~

Compiler/file manager sẽ quyết định thư mục vật lý dựa trên cấu hình, chẳng hạn **-s build/generated**. Tham số **demo.app.AlphaCard** là tên type, **không phải** đường dẫn tới tệp .java.

### 2.1. FilerException có ý nghĩa gì?

**javax.annotation.processing.FilerException** là subclass của **IOException**, biểu thị một thao tác tạo file vi phạm điều kiện Filer. Các trường hợp điển hình:

- Cùng một processor gọi **createSourceFile("demo.app.AlphaCard")** hai lần trong **một lần processing**.
- Hai processor cùng cố tạo **demo.app.AlphaCard** trong một compilation.
- Processor cố tạo source/class tương ứng với **initial input** của compiler. Các input này được xem là thuộc **round 0**.
- Processor cố tạo source và class file cho cùng một type name trái với hợp đồng Filer.
- Hai lần **createResource** có cùng location, package và relative path.
- Qualified name hoặc đường dẫn bất hợp lệ.

**Quan trọng:** Một file output tồn tại từ build trước không đồng nghĩa việc tạo lại trong build mới luôn là FilerException. Filer cho phép lần tạo đầu trong **processing run mới** quản lý/thay nội dung output cũ theo contract; điều bị cấm là tạo **cùng file thêm lần nữa trong cùng run**, hoặc đụng các initial inputs/định danh không được phép.

### 2.2. Lỗi tạo output bên trong vòng lặp

Ví dụ **sai về thiết kế**:

~~~java
// Mảnh mô tả lỗi logic; không phải chương trình biên dịch độc lập.
for (Element element : round.getElementsAnnotatedWith(GenerateCard.class)) {
    processingEnv.getFiler().createSourceFile("demo.app.SharedCard", element);
}
~~~

Nếu có Alpha và Beta, cả hai cùng yêu cầu Filer tạo **SharedCard**. Lần thứ hai sẽ xung đột. Việc “nội dung định tạo giống nhau” không làm thao tác hợp lệ.

Một kiểu sai khác là gọi createSourceFile một lần **mỗi round**, kể cả final round, dùng cùng tên. Vì processor có thể được gọi nhiều lần, code phải kiểm tra **round.processingOver()** và quản lý các tên đã tạo.

### 2.3. Chiến lược ownership

Để tránh xung đột:

1. Tính generated qualified name **ổn định** từ package và tên type nguồn.
2. Dùng **Set<String>** theo processor instance để kiểm tra một generated name không bị yêu cầu hai lần.
3. Truyền **originating Element** vào Filer khi có thể.
4. Khi gặp FilerException, báo **Diagnostic.Kind.ERROR** gắn với source element và tên output.
5. Nếu hai processor thực sự cùng sở hữu một artifact, thay đổi thiết kế đăng ký/ownership; không nuốt lỗi và không đổi tên ngẫu nhiên để né xung đột.

Set nội bộ **không thay thế** kiểm tra của Filer: xung đột với processor khác hay initial input vẫn có thể xảy ra.

## 3. Final round: processingOver() và errorRaised()

**RoundEnvironment** cho phép processor biết bối cảnh vòng hiện tại:

| API | Diễn giải |
| --- | --- |
| **processingOver()** | True nếu các type được tạo trong vòng hiện tại sẽ không trải qua vòng annotation processing tiếp theo |
| **errorRaised()** | True nếu một lỗi được báo trong **round trước**, không phải tổng kết mọi lỗi trong cả lần compile |
| **getElementsAnnotatedWith(...)** | Lấy khai báo có annotation phù hợp trong round hiện tại |
| **getRootElements()** | Lấy các root elements của round hiện tại |

Với processor đã được gọi ở round trước, compiler có thể gọi tiếp ở vòng sau và final round ngay cả khi **annotations** rỗng. Không được giả định mỗi **process(...)** đều có element mới.

### 3.1. Source sinh ở final round có dùng được ngay không?

Không nên dựa vào việc tạo một Java source **ở final round** rồi để source gốc tham chiếu type đó. Final round không cung cấp thêm một vòng xử lý tiếp theo cho generated type; compile pipeline cũng không đảm bảo dùng generated source ở thời điểm đó như source sinh đúng lúc.

**Quy tắc:** Nếu cần compiler biên dịch và type-check source mới trong cùng task, hãy sinh nó ở **non-final round**. Dùng final round cho việc tổng kết không cần thêm Java compilation unit, ví dụ resource metadata.

Ví dụ lifecycle đúng:

~~~java
// Mảnh minh họa, generatePerType và writeIndex là helper của ứng dụng.
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment round) {
    if (round.processingOver()) {
        if (!round.errorRaised()) {
            writeIndex();
        }
        return true;
    }

    for (Element type : round.getElementsAnnotatedWith(GenerateCard.class)) {
        generatePerType(type);
    }
    return true;
}
~~~

**errorRaised()** phản ánh lỗi được báo trong previous round. Nó hữu ích để không tạo metadata tổng hợp khi processing đã có lỗi trước đó, nhưng **không phải** dấu hiệu compiler cuối cùng chắc chắn thành công. Nếu cần quyết định phát hành artifact, hãy dùng **javac exit code** hoặc **CompilationTask.call()** và toàn bộ diagnostics.

### 3.2. Thu thập qua nhiều vòng

Một processor có thể lưu dữ liệu trong field của instance rồi dùng chúng ở final round:

~~~java
// Mảnh minh họa.
private final SortedSet<String> processedNames = new TreeSet<>();
private boolean indexWritten;

@Override
public boolean process(Set<? extends TypeElement> a, RoundEnvironment round) {
    if (round.processingOver()) {
        if (!indexWritten && !processedNames.isEmpty() && !round.errorRaised()) {
            // Sinh một resource từ processedNames đã sắp xếp.
            // Sau khi ghi thành công: indexWritten = true.
        }
        return true;
    }

    // Thu thập tên của annotated elements trong round này.
    return true;
}
~~~

Tại final round, **processingOver() == true**. Với bài học, dùng **SortedSet** ngăn kết quả phụ thuộc vào thứ tự mà Set các elements được compiler trả về. Không dùng static global state: một lần build mới phải bắt đầu với trạng thái mới.

## 4. Tính lặp lại của kết quả: định nghĩa đúng

Một processor có tính **deterministic** khi cùng source, cùng dependencies, cùng processor version và cấu hình toolchain liên quan cho ra cùng nội dung generated artifacts.

~~~text
Nguồn + annotation + dependencies + processor version
       + compiler options + môi trường có ý nghĩa
                             │
                             ▼
                  Generated files ổn định
~~~

Các yếu tố thường phá vỡ tính lặp lại:

| Nguyên nhân | Ảnh hưởng | Cách giải quyết |
| --- | --- | --- |
| Duyệt **HashSet/HashMap** rồi ghi trực tiếp | Thứ tự các dòng có thể thay đổi | Sắp xếp theo tên đầy đủ trước khi ghi |
| **Instant.now()**, timestamp, số ngẫu nhiên, UUID | Output khác dù source không đổi | Không đưa dữ liệu ngẫu nhiên vào generated content |
| Đường dẫn tuyệt đối của workspace | Build trên máy khác tạo text khác | Dùng tên tương đối/định danh ổn định |
| Charset hoặc định dạng theo locale mặc định | Nội dung/hashes khác giữa hệ điều hành | Chỉ định UTF-8 và quy tắc format phù hợp |
| Tên generated class phụ thuộc thứ tự elements | Cấu trúc mã thay đổi | Dùng package + qualified/simple name của source |
| Thứ tự thực thi của nhiều processors | Output phụ thuộc lịch chạy không được đảm bảo | Phân tách ownership, tránh phụ thuộc vào thứ tự |
| State static còn lưu từ compilation trước | Resource chứa dữ liệu stale | State theo processor instance/lần compile |
| File cũ trong build directory | Compile thành công giả do type generated đã có | Clean build hoặc quản lý incremental output đúng |
| Writer/OutputStream không đóng đúng | File output thiếu dữ liệu | Dùng try-with-resources và kiểm tra lỗi I/O |

**Reproducible generated source/resource** không tự động có nghĩa mọi **.class** sẽ giống hệt giữa các phiên bản JDK hoặc bộ options khác nhau. Khi kiểm thử, phải nói rõ bạn so sánh cấp độ nào: generated text, resource bytes, classfiles hay toàn bộ packaged artifact.

## 5. Ví dụ Java 17+ chạy được: source ở non-final và resource ở final

Ví dụ có năm source files tự viết. Hai class **Alpha** và **Beta** được gắn annotation; processor tạo **AlphaCard.java** và **BetaCard.java** trong vòng đầu. Khi final round tới, nó tạo resource **META-INF/demo/card-names.txt** chứa tên của hai annotated types theo thứ tự cố định. Ứng dụng Main gọi generated classes và đọc resource này.

### 5.1. Cấu trúc

~~~text
annotation-conflicts/
└── src/
    └── demo/
        ├── annotations/GenerateCard.java
        ├── processor/CardProcessor.java
        └── app/
            ├── Alpha.java
            ├── Beta.java
            └── Main.java
~~~

### 5.2. Annotation: src/demo/annotations/GenerateCard.java

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateCard {}
~~~

**RetentionPolicy.SOURCE** phù hợp vì annotation được processor đọc lúc biên dịch, không yêu cầu lưu annotation ở runtime.

### 5.3. Processor: src/demo/processor/CardProcessor.java

~~~java
package demo.processor;

import demo.annotations.GenerateCard;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import java.util.SortedSet;
import java.util.TreeSet;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.NestingKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.annotations.GenerateCard")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
@SupportedOptions("demo.forceCollision")
public final class CardProcessor extends AbstractProcessor {
    private final Set<String> generated = new HashSet<>();
    private final SortedSet<String> annotatedNames = new TreeSet<>();
    private boolean indexCreated;

    public CardProcessor() {}

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            if (!round.errorRaised() && !indexCreated && !annotatedNames.isEmpty()) {
                try {
                    FileObject file = processingEnv.getFiler().createResource(
                            StandardLocation.CLASS_OUTPUT, "",
                            "META-INF/demo/card-names.txt");
                    try (Writer writer = file.openWriter()) {
                        for (String name : annotatedNames) {
                            writer.write(name);
                            writer.write("\n");
                        }
                    }
                    indexCreated = true;
                } catch (IOException e) {
                    error("Cannot write card index: " + e.getMessage(), null);
                }
            }
            return true;
        }

        for (Element element : round.getElementsAnnotatedWith(GenerateCard.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || ((TypeElement) element).getNestingKind()
                    != NestingKind.TOP_LEVEL) {
                error("@GenerateCard requires a top-level class", element);
                continue;
            }
            TypeElement type = (TypeElement) element;
            String simple = type.getSimpleName().toString();
            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String generatedSimple = simple + "Card";
            String generatedName = pkg.isEmpty()
                    ? generatedSimple : pkg + "." + generatedSimple;

            if (!generated.add(generatedName)) {
                error("Duplicate generated type: " + generatedName, element);
                continue;
            }
            try {
                JavaFileObject source =
                        processingEnv.getFiler().createSourceFile(generatedName, type);
                try (Writer writer = source.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n\n");
                    }
                    writer.write("public final class " + generatedSimple + " {\n");
                    writer.write("    private " + generatedSimple + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"card:" + simple + "\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
                annotatedNames.add(type.getQualifiedName().toString());

                if ("true".equals(processingEnv.getOptions()
                        .get("demo.forceCollision"))) {
                    try {
                        processingEnv.getFiler().createSourceFile(generatedName, type);
                        error("Expected collision was not detected", element);
                    } catch (FilerException expected) {
                        error("Duplicate generated type: " + generatedName, element);
                    }
                }
            } catch (FilerException e) {
                error("Filer collision for " + generatedName + ": "
                        + e.getMessage(), element);
            } catch (IOException e) {
                error("Cannot generate " + generatedName + ": "
                        + e.getMessage(), element);
            }
        }
        return true;
    }

    private void error(String message, Element element) {
        if (element == null) {
            processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, message);
        } else {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, message, element);
        }
    }
}
~~~

**Ý nghĩa của các quyết định:**

- **generated** là Set tên output của processor instance, tránh lặp ngay trong code. **Filer** vẫn từ chối xung đột với output của processor khác.
- **annotatedNames** là **TreeSet**: tên được sắp xếp trước khi ghi resource.
- **processingOver()** tách việc tạo source khỏi việc tổng hợp resource.
- **indexCreated** phòng tạo resource quá một lần; cờ chỉ bật sau khi Writer hoàn tất.
- **errorRaised()** giúp không tạo resource khi round trước đã báo lỗi; không thay thế exit code của javac.
- **@SupportedOptions("demo.forceCollision")** cho phép chạy một **negative test** cố tình gọi Filer lần hai. Không bật tùy chọn này trong build thành công hay production.
- Mã generator chèn tên đơn giản của class vào Java string literal. Với input Alpha/Beta đây là trường hợp đã kiểm thử; một generator xử lý dữ liệu bất kỳ phải escape Java string literal, kiểm tra tên hợp lệ và giới hạn kích thước input/output.

### 5.4. Hai input types

**src/demo/app/Alpha.java**

~~~java
package demo.app;

import demo.annotations.GenerateCard;

@GenerateCard
public final class Alpha {}
~~~

**src/demo/app/Beta.java**

~~~java
package demo.app;

import demo.annotations.GenerateCard;

@GenerateCard
public final class Beta {}
~~~

Một source cho mỗi annotated top-level class; tên generated khác nhau nhờ quy tắc **OriginalSimpleName + "Card"**:

~~~text
demo.app.Alpha → demo.app.AlphaCard
demo.app.Beta  → demo.app.BetaCard
~~~

### 5.5. Consumer: src/demo/app/Main.java

~~~java
package demo.app;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(AlphaCard.message());
        System.out.println(BetaCard.message());

        try (InputStream in = Main.class.getClassLoader().getResourceAsStream(
                "META-INF/demo/card-names.txt")) {
            if (in == null) {
                throw new IllegalStateException("Index resource is missing");
            }
            System.out.print(
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
~~~

Main tham chiếu **AlphaCard** và **BetaCard** trước khi các source đó xuất hiện trên đĩa. Compiler giải quyết chúng nhờ processor sinh source trong round thích hợp. Nếu không chạy processor trên một clean build, hai class này sẽ không được tạo.

### 5.6. Lệnh build và chạy trên Bash/Linux/macOS

Chạy trong thư mục **annotation-conflicts**:

~~~bash
mkdir -p build/processor build/one/classes build/one/generated

javac -encoding UTF-8 --release 17 \
  -d build/processor \
  src/demo/annotations/GenerateCard.java \
  src/demo/processor/CardProcessor.java

javac -encoding UTF-8 --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.CardProcessor \
  -s build/one/generated \
  -d build/one/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Main.java

java -cp "build/one/classes:build/processor" demo.app.Main
~~~

**Stdout chính xác của lệnh java:**

~~~text
card:Alpha
card:Beta
demo.app.Alpha
demo.app.Beta
~~~

Trên Windows PowerShell, tạo directory bằng **New-Item -ItemType Directory -Force**, viết các lệnh javac một dòng hoặc dùng cú pháp nối dòng riêng của PowerShell, và thay **:** bằng **;** trong runtime classpath:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/one/classes,build/one/generated | Out-Null
javac -encoding UTF-8 --release 17 -d build/processor src/demo/annotations/GenerateCard.java src/demo/processor/CardProcessor.java
javac -encoding UTF-8 --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.CardProcessor -s build/one/generated -d build/one/classes src/demo/app/Alpha.java src/demo/app/Beta.java src/demo/app/Main.java
java -cp "build/one/classes;build/processor" demo.app.Main
~~~

Stdout vẫn là bốn dòng trên. **javac** không bắt buộc in gì khi biên dịch thành công.

### 5.7. Output quan trọng

~~~text
build/
├── processor/
│   └── demo/
│       ├── annotations/GenerateCard.class
│       └── processor/CardProcessor.class
└── one/
    ├── generated/
    │   └── demo/app/
    │       ├── AlphaCard.java
    │       └── BetaCard.java
    └── classes/
        ├── demo/app/
        │   ├── Alpha.class
        │   ├── Beta.class
        │   ├── Main.class
        │   ├── AlphaCard.class
        │   └── BetaCard.class
        └── META-INF/demo/card-names.txt
~~~

**-s** nhận Java source sinh bởi processor, **-d** nhận classfiles và resource tại **CLASS_OUTPUT**. **-processorpath** để javac chạy processor, còn **-cp** để source ứng dụng giải quyết annotation type. Chúng không mặc nhiên thay thế nhau.

Resource **card-names.txt** có đúng nội dung sau, mỗi tên kết thúc bằng newline:

~~~text
demo.app.Alpha
demo.app.Beta
~~~

**Xác minh thực tế:** OpenJDK 24.0.2 với **--release 17** tạo đủ hai .java, hai generated .class và manifest; chương trình in đúng bốn dòng stdout.

## 6. Quan sát rounds và final round

Biên dịch lại với **-XprintRounds** (có thể dùng output directory riêng để tránh stale file):

~~~bash
javac -encoding UTF-8 --release 17 \
  -XprintRounds \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.CardProcessor \
  -s build/one/generated \
  -d build/one/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Main.java
~~~

Trên OpenJDK 24, chẩn đoán rounds của ví dụ:

~~~text
Round 1:
    input files: {demo.app.Alpha, demo.app.Beta, demo.app.Main}
    annotations: [demo.annotations.GenerateCard]
    last round: false
Round 2:
    input files: {demo.app.AlphaCard, demo.app.BetaCard}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Đây là output chẩn đoán của javac, **không phải stdout của Main**; căn lề, thứ tự và số vòng có thể thay đổi khi đầu vào/JDK khác. Không dựa vào “luôn có round 3” để viết processor.

Ở **Round 1**, processor thấy annotation và tạo hai source. **Round 2** không tạo source mới. **Round 3** có **processingOver() == true**, processor viết resource tổng hợp, không tạo Java source mới.

## 7. Negative test: xung đột Filer phải làm build thất bại

Cờ **-Ademo.forceCollision=true** của processor chỉ phục vụ bài test. Nó cố tạo cùng một **generated qualified name** lần thứ hai ngay trong processing run hiện tại, rồi báo **Diagnostic.Kind.ERROR** khi Filer phát hiện lỗi.

Tạo output riêng:

~~~bash
mkdir -p build/conflict/classes build/conflict/generated

javac -encoding UTF-8 --release 17 \
  -Ademo.forceCollision=true \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.CardProcessor \
  -s build/conflict/generated \
  -d build/conflict/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Main.java
~~~

Trong PowerShell, đặt đối số **"-Ademo.forceCollision=true"** trong dấu nháy để truyền nguyên vẹn cho javac.

**Kỳ vọng:** javac trả exit code khác 0. Diagnostics chứa một thông điệp như:

~~~text
Duplicate generated type: demo.app.AlphaCard
~~~

Có thể còn lỗi tương tự cho **BetaCard**; số dòng và cách hiển thị phụ thuộc JDK, vì vậy không so khớp toàn bộ stderr chính xác. Một test Java 17+ riêng đã xác minh trên OpenJDK 24 rằng cố tạo cùng source qualified name lần hai ném **FilerException** và khiến javac kết thúc với exit code 1 khi processor báo ERROR.

**Không dùng artifacts của một build đã thất bại để phát hành:** generated .java có thể đã được tạo một phần trước khi lỗi được báo.

Phân biệt:

- **Tạo lại cùng file trong cùng processing run:** lỗi Filer.
- **Tạo output trùng initial source input:** lỗi Filer hoặc lỗi compiler do duplicate type.
- **Một clean build độc lập tạo lại cùng output:** được phép theo contract, nếu ownership và input hợp lệ.

Không sửa lỗi bằng cách đặt tên ngẫu nhiên cho generated source; đó là cách phá vỡ tính lặp lại, không giải quyết thiết kế.

## 8. Kiểm tra reproducibility: hai clean builds

Ở trên output đã ở **build/one**. Hãy biên dịch một lần thứ hai trong thư mục mới, giữ nguyên processor, source, dependencies, JDK và options:

~~~bash
mkdir -p build/two/classes build/two/generated

javac -encoding UTF-8 --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.processor.CardProcessor \
  -s build/two/generated \
  -d build/two/classes \
  src/demo/app/Alpha.java \
  src/demo/app/Beta.java \
  src/demo/app/Main.java
~~~

Trên Bash/Linux/macOS, so sánh đúng những file processor sinh:

~~~bash
cmp build/one/generated/demo/app/AlphaCard.java \
    build/two/generated/demo/app/AlphaCard.java

cmp build/one/generated/demo/app/BetaCard.java \
    build/two/generated/demo/app/BetaCard.java

cmp build/one/classes/META-INF/demo/card-names.txt \
    build/two/classes/META-INF/demo/card-names.txt
~~~

**Kỳ vọng:** các lệnh **cmp** không in gì và trả exit code 0. Trên Windows, dùng **Get-FileHash -Algorithm SHA256** cho từng file tương ứng rồi so sánh thuộc tính **Hash**.

Trong kiểm thử bằng OpenJDK 24.0.2, cả hai generated .java và resource tổng hợp đều có **hash SHA-256 trùng nhau giữa hai build độc lập**, không cần phụ thuộc vào thứ tự Set của compiler.

Để kiểm thử chặt hơn trong CI:

1. So sánh **tập đường dẫn output** lẫn nội dung, không chỉ một file.
2. Test thay đổi một annotation input, thêm/xóa một type và quan sát resource được cập nhật.
3. Chạy clean build trong output root riêng, tránh nhận nhầm .class/.java cũ.
4. So sánh cùng toolchain và cùng compiler options; nếu cần hỗ trợ nhiều JDK, định nghĩa kỳ vọng riêng cho mỗi toolchain.
5. Không dùng timestamps hoặc đường dẫn workspace làm dữ liệu không cần thiết trong output.
6. Không kết luận .class chắc chắn giống byte giữa mọi JDK chỉ từ việc generated .java giống nhau.

## 9. Khi input đến từ nhiều rounds hoặc nhiều processors

Ví dụ xử lý từng annotated type độc lập, nên generated source có thể được tạo ngay khi thấy element. **Resource aggregate** được viết ở cuối sau khi đã thu thập tên.

Nhưng có trường hợp processor A tạo source mang annotation mà processor B quan tâm ở round sau. Khi đó:

- Nếu B tạo **mỗi source riêng** theo từng type được thấy, mỗi non-final round vẫn tạo được outputs cần thiết.
- Nếu B muốn tạo **một Java registry class duy nhất chứa tất cả annotated types cuối cùng**, nó không thể chỉ đợi final round rồi sinh class để dùng ngay trong cùng compilation. Final round quá muộn cho việc có thêm vòng xử lý.
- Cách khả thi là thiết kế contract một **non-final round có dữ liệu đầy đủ** nếu pipeline thực sự bảo đảm điều đó, hoặc tách thành **hai compilation stages**, hoặc dùng resource tổng hợp được viết cuối processing.
- Không giả định thứ tự chạy giữa nhiều processors là hợp đồng bảo đảm của ngôn ngữ; cần xác lập ownership và dependency rõ.
- Khi dùng incremental build, phân biệt generated artifacts **isolating** (phụ thuộc riêng một source) và **aggregating** (phụ thuộc nhiều sources). Originating elements có giá trị nhưng không tự bảo đảm công cụ build phân loại/cleanup đúng.

## 10. Những lỗi phổ biến cần chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| **FilerException: Attempt to recreate a file for type ...** | Tạo cùng type/path lần hai hoặc đụng một input | Tra qualified name, các createSourceFile/createResource, rounds và processors khác |
| Processor không chạy | Thiếu kích hoạt tường minh, processor path sai | **-processor**, **-processorpath**, **@SupportedAnnotationTypes**, **-XprintRounds** |
| Generated source có nhưng không compile | Sinh quá muộn, dùng **-proc:only** hoặc source lỗi | Final round, diagnostics, **-s**, **-d** |
| Manifest resource thiếu | Không có annotated input, final round lỗi hoặc location sai | **processingOver()**, **errorRaised()**, **CLASS_OUTPUT** |
| Manifest còn tên class đã xóa | Build dùng output cũ hoặc incremental tracking thiếu | Clean build, output ownership và cleanup |
| Generated text đổi giữa builds | Set iteration, timestamp, random, charset, locale | Sort, hash file, loại dữ liệu phụ thuộc môi trường |
| Output bị trùng chỉ trong CI | Cấu hình nhiều processor/JAR khác máy local | Danh sách processor, module/classpath và build profile |
| **errorRaised()==false** nhưng javac fail | Chỉ biết lỗi được báo ở previous round, không phải toàn task | Kiểm tra compiler exit code và mọi diagnostics |
| **ClassNotFoundException** lúc chạy | Runtime classpath khác compile classpath | Kiểm tra các .class được biên dịch và **java -cp** |
| Lỗi trùng xuất hiện sau lần build mới | Source input đã trở thành type có tên generated hoặc build config sai | Kiểm tra initial input, build output và đường dẫn compiler |

Một quy trình chẩn đoán có thứ tự: đọc lỗi đầu tiên, xác định **qualified generated name**, bật **-XprintRounds** và nếu cần **-XprintProcessorInfo**, tìm tất cả chỗ tạo cùng output, kiểm tra dữ liệu đã có từ initial inputs, sau đó clean build và xác nhận lệnh javac thành công.

Mẫu báo lỗi trong processor:

~~~java
// Mảnh minh họa: biến generatedName và element phải được cung cấp.
try {
    processingEnv.getFiler().createSourceFile(generatedName, element);
} catch (FilerException collision) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Generated type collision: " + generatedName
                    + " (" + collision.getMessage() + ")",
            element);
} catch (IOException failure) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Cannot generate " + generatedName + ": " + failure.getMessage(),
            element);
}
~~~

Đây chỉ là mảnh xử lý ngoại lệ, **không phải chương trình độc lập**: code thực tế phải ghi nội dung vào JavaFileObject và đóng Writer.

## 11. Công cụ biên dịch hiện hành và an toàn

Trong ví dụ, processor được chọn **tường minh** qua **-processor demo.processor.CardProcessor**. **-processorpath** dùng để nạp processor và dependencies thực thi của nó; **-cp** dùng cho compiler phân giải annotation type và các lớp của source ứng dụng; **-s** và **-d** là hai output roots khác nhau.

Các option còn đang được hỗ trợ: **-processor**, **-processorpath**, **--processor-module-path**, **-proc:full**, **-proc:only**, **-proc:none**, **-XprintRounds**, **-XprintProcessorInfo**. Trên các JDK hiện đại, không nên dựa vào việc một processor JAR tình cờ có trên classpath sẽ tự kích hoạt annotation processing. Nếu dùng service discovery chuẩn, đóng gói **META-INF/services/javax.annotation.processing.Processor** và cấu hình processor discovery rõ ràng.

Processor là **code thực thi trong môi trường build**. Nó có thể truy cập những tài nguyên mà process javac/build tool được cấp quyền. Do đó phải kiểm soát nguồn processor dependencies, quyền CI, network access, thông tin nhạy cảm trong diagnostics và giới hạn tài nguyên. **FilerException không phải cơ chế bảo mật**.

## 12. Bài tập và checklist

### Bài tập tự luyện

1. Tạo class **Gamma** có **@GenerateCard**; chạy lại và kiểm tra **GammaCard.java**, manifest có ba tên Alpha/Beta/Gamma đúng thứ tự.
2. Sửa naming logic để cả Alpha và Beta đều muốn tạo **demo.app.SharedCard**. Quan sát FilerException và trình bày cách thiết kế owner đúng.
3. Thử tạo Java source trong **processingOver()==true**, quan sát compiler diagnostics và giải thích vì sao không nên để source ban đầu phụ thuộc generated type đó.
4. Bỏ **TreeSet**, ghi theo thứ tự duyệt HashSet. So sánh nhiều builds và giải thích vì sao thứ tự đó không được bảo đảm dù có lần trùng kết quả.
5. Gỡ annotation của Alpha, clean build lại và kiểm tra resource không còn tên Alpha; so sánh với lần không dọn generated outputs.
6. Viết automation test gồm: build chuẩn thành công, build test cố tình trùng file thất bại, hai clean builds có cùng tập generated files và cùng hashes.

### Checklist trước khi phát hành processor

- [ ] Mỗi generated type/path có owner duy nhất và tên ổn định.
- [ ] Không tạo cùng file hai lần trong một processing run.
- [ ] Không ghi đè source/class input ban đầu của compiler.
- [ ] Source cần compile được sinh trong non-final rounds.
- [ ] Final round dùng để tổng kết không yêu cầu source mới được xử lý tiếp.
- [ ] Hiểu **errorRaised()** là lỗi từ round trước, không thay cho kết quả toàn compile.
- [ ] Ghi resource đã sắp xếp, không dùng timestamp/random/path máy không cần thiết.
- [ ] Bắt **FilerException** và báo ERROR có tên output và source Element.
- [ ] Đóng tất cả Writer/OutputStream, không bỏ qua IOException.
- [ ] Test thêm/xóa annotated input, kiểm tra stale output và incremental behavior.
- [ ] Test hai clean builds cùng toolchain, so sánh tập file và nội dung.
- [ ] Kiểm soát processor path, JDK/version, options và quyền thực thi.

## Kết luận

Một processor ổn định cần phối hợp ba quy tắc:

**Filer tạo mỗi output một lần trong một processing run → sinh Java source đủ sớm ở non-final rounds → tạo output theo tên và thứ tự xác định, kiểm chứng bằng các clean builds độc lập.**

**FilerException** báo lỗi thiết kế ownership hoặc danh tính file; **processingOver()** chỉ ra final round; **errorRaised()** cho biết lỗi ở round trước. Khi kiểm thử, dùng compiler diagnostics và kết quả javac/CompilationTask thay vì suy luận từ sự tồn tại của một file output.

**Tài liệu JDK chính thức:**

- [Filer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [FilerException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/FilerException.html)
- [RoundEnvironment — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Processor — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html)
- [javac — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)