# Tránh tạo trùng tệp, xử lý FilerException và ghi nhận phần tử nguồn trong Java annotation processor

## 1. Bản chất của vấn đề

Khi xây dựng annotation processor theo JSR 269, chúng ta có thể sinh Java source, class file hoặc resource trong lúc `javac` biên dịch. Đối tượng quản lý các output này là `javax.annotation.processing.Filer`, truy cập bằng `processingEnv.getFiler()`. Việc tạo tệp không đơn thuần là ghi text xuống đĩa: compiler cần biết tệp mới, danh tính kiểu mới, vòng processing có thêm nguồn đầu vào và mối liên hệ với các khai báo gốc.

Quy tắc quan trọng nhất: **trong một invocation của annotation processing, mỗi pathname/type output chỉ được tạo một lần**. Nếu cùng một generated type hoặc đường dẫn được yêu cầu tạo lần nữa trong cùng invocation, Filer có thể ném `FilerException`.

Ví dụ lỗi thường gặp:

~~~text
error: Expected duplicate: Attempt to recreate a file for type demo.generated.SharedHello
1 error
~~~

Hai tình huống phải tách biệt:
- **Trùng ngay trong invocation hiện tại:** hai annotated elements, nhiều round, hoặc hai processor cùng xin tạo một tên; đây là nguyên nhân điển hình của FilerException.
- **Generated file đã tồn tại từ lần build trước:** Filer có thể thay nội dung tệp cũ khi tạo lần đầu trong invocation mới. File cũ trên đĩa **không tự động đồng nghĩa** FilerException, trừ khi bị đưa thành input của compilation hoặc xảy ra xung đột khác.

Java compiler coi các source/class là **input ban đầu** như đã được tạo ở “round 0”, vì thế processor không được tạo trùng type tương ứng input ban đầu. Filer còn có thể báo lỗi tên không hợp lệ hoặc không xác định được target module; không nên chẩn đoán mọi FilerException là “đã gọi hai lần” khi chưa xem message.

## 2. Hợp đồng các API Filer

| API | Công dụng | Lưu ý |
| --- | --- | --- |
| `createSourceFile(name, origins...)` | Tạo Java source cho principal top-level type hoặc package-info | Tên qualified type, có thể được đưa vào processing round tiếp theo sau khi writer được đóng |
| `createClassFile(name, origins...)` | Tạo JVM class file | Dùng binary name; không tạo source và class cho cùng type trong một invocation |
| `createResource(location, pkg, relativeName, origins...)` | Tạo resource trong output location | Resource cũng có quy tắc không tạo trùng pathname và không được tự đưa thành Java source để processing |
| `getResource(location, pkg, relativeName)` | Đọc resource đang có | Không phải thao tác “kiểm tra rồi giữ chỗ”; không dùng để né hợp đồng tạo file |

Một lời gọi tốt:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.AlphaHello",
        alphaTypeElement);
~~~

Đây là trích đoạn **bên trong processor**, trong đó `alphaTypeElement` là `TypeElement` thực tế của `demo.Alpha`. Tham số thứ hai là **originating element**, giúp tooling biết nguồn nào đã dẫn đến output.

Dùng `Writer` và đóng chắc chắn:

~~~java
try (Writer writer = processingEnv.getFiler()
        .createSourceFile(fullName, sourceType)
        .openWriter()) {
    writer.write(javaSource);
}
~~~

Đoạn này minh họa một phần method, giả định các biến và imports phù hợp. `Filer` quản lý file mới; việc đóng `Writer` hoặc `OutputStream` giúp compiler biết nội dung đã hoàn tất để lập round tiếp theo. Đừng dùng `Files.writeString(...)` để tạo generated Java source trực tiếp và mong compiler tự xử lý với cùng metadata.

## 3. Các nguồn tạo trùng phổ biến

### Hai input cùng một tên output

Nếu source có `Alpha` và `Beta` đều được đánh dấu annotation và code chạy:

~~~java
for (Element e : round.getElementsAnnotatedWith(annotation)) {
    processingEnv.getFiler()
            .createSourceFile("demo.generated.SharedHello", e);
}
~~~

thì iteration đầu có thể thành công, iteration thứ hai tạo lại đúng tên. Đặt `createSourceFile` **bên trong vòng lặp** chỉ đúng khi **mỗi iteration có tên riêng**. Nếu output là file tổng hợp, phải tính toàn bộ dữ liệu trước và gọi Filer **một lần**.

### Trùng giữa các processing round

Processor có thể chạy nhiều round trong một invocation. Một source được tạo ở round 1 có thể được cung cấp làm root của round 2. Nếu processor gọi tạo lại cùng tên, vẫn là invocation cũ: Filer từ chối.

### Hai processor cùng sở hữu type

Processor A và B đều tạo `demo.Generated`. Mỗi processor có thể giữ một `Set<String>` riêng và tưởng chưa có gì trùng, nhưng **Filer chung của compiler** phát hiện xung đột. Cần một quy tắc ownership: chỉ một processor tạo mỗi output; không dựa vào thứ tự đăng ký processor.

### Đụng source ban đầu

Nếu `demo.Generated.java` đã được truyền trực tiếp là input của `javac` rồi processor cũng tạo `demo.Generated`, đó là va chạm round 0. Lỗi này hay xảy ra khi generated-source directory của lần build trước được thêm nhầm vào source set chính.

### Collisions do đơn giản hóa tên

Nếu `sales.User` và `hr.User` cùng sinh `demo.generated.UserAdapter`, tên simple `User` không đủ duy nhất. Tên output phải phản ánh package và enclosing type cần thiết; có thể sinh trong package gốc hoặc dùng một quy ước chuyển qualified name ổn định. Không dùng timestamp, random number hoặc thứ tự duyệt để né lỗi.

### Trùng resource hoặc class/source

`createResource` cũng không cho mở tạo cùng pathname nhiều lần trong invocation. `createSourceFile` và `createClassFile` cho cùng type cũng có thể xung đột dù đích ghi là những loại file khác nhau. Không xem resource file như một “cửa hậu” để sinh nhiều lần một Java type.

## 4. Chiến lược thiết kế an toàn

Một processor nên thực hiện theo trình tự:

1. **Xác định danh tính mỗi input:** tên package/module/type đầy đủ; tránh lấy mỗi simple name trong project lớn.
2. **Ánh xạ input → output có tính quyết định:** cùng nguồn logic phải cho cùng tên output và nội dung hợp lệ.
3. **Chọn mô hình generation:** một output cho một element (*isolating*) hay một output tổng hợp từ nhiều elements (*aggregating*).
4. **Kiểm tra conflicts trước khi mở writer:** lưu danh sách output dự kiến hoặc `Set<String>` đã reserve cho processor hiện tại.
5. **Chỉ tạo một lần trong cùng invocation**, kể cả khi có nhiều round; không cố tạo Java source trong final round.
6. **Truyền originating elements phù hợp** vào `createSourceFile`, `createClassFile` hoặc `createResource`.
7. **Đóng stream** và phát `Diagnostic.Kind.ERROR` nếu xung đột hoặc I/O thất bại.
8. **Không retry cùng tên sau FilerException**; sửa generation logic hoặc ownership.
9. **Không sửa file nguồn/generate bằng thao tác filesystem trực tiếp** để qua mặt Filer.
10. **Test clean + incremental** và test thay đổi/xóa input để phát hiện stale outputs.

Một `Set<String>` ngăn nhiều lần tạo do **chính processor đó**. Nó không thay thế Filer, không kiểm soát processor khác và không giải quyết lỗi module hoặc tên không hợp lệ.

## 5. Ví dụ Java 17 chạy được: tạo một file cho mỗi class nguồn

Bài thực hành dùng:
- Annotation `demo.GenerateHello`.
- Processor `ap.HelloProcessor`.
- Hai class `demo.Alpha` và `demo.Beta`.
- `demo.App` dùng generated types `demo.generated.AlphaHello` và `demo.generated.BetaHello`.

Cấu trúc nguồn:

~~~text
project/
  api/demo/GenerateHello.java
  processor/ap/HelloProcessor.java
  src/demo/Alpha.java
  src/demo/Beta.java
  src/demo/App.java
~~~

### 5.1. Tệp api/demo/GenerateHello.java

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {}
~~~

`RetentionPolicy.SOURCE` không cản processor quan sát annotation lúc compile; nó chỉ nói annotation không nhất thiết được ghi vào class file để dùng ở runtime.

### 5.2. Tệp processor/ap/HelloProcessor.java

~~~java
package ap;

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

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    private final Set<String> reservedNames = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) return true;

        TypeElement annotation = processingEnv.getElementUtils()
                .getTypeElement("demo.GenerateHello");
        if (annotation == null) return false;

        for (Element e : round.getElementsAnnotatedWith(annotation)) {
            if (!(e instanceof TypeElement type)) continue;

            String shortName = type.getSimpleName() + "Hello";
            String fullName = "demo.generated." + shortName;

            if (!reservedNames.add(fullName)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Duplicate generated type: " + fullName, e);
                continue;
            }

            try (Writer out = processingEnv.getFiler()
                    .createSourceFile(fullName, type).openWriter()) {
                out.write("package demo.generated; public final class " + shortName
                        + " { public static String text() { return \""
                        + type.getSimpleName() + "\"; } }");
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Filer name conflict: " + ex.getMessage(), e);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot write generated source: " + ex, e);
            }
        }
        return true;
    }
}
~~~

Điểm cần hiểu:
- `reservedNames` giữ các tên mà **instance processor này đã dự định tạo** trong invocation hiện tại.
- `fullName` có tên package `demo.generated` và class name xác định. Bài mẫu chỉ có top-level classes `Alpha`, `Beta` trong package `demo` với simple name khác nhau. Trong production nhiều package/nested types, phải đổi quy tắc này để tránh collisions.
- `createSourceFile(fullName, type)` truyền originating element chính xác.
- `try-with-resources` đóng writer; không cần tự thao tác thư mục generated.
- `catch (FilerException)` trước `catch (IOException)` vì FilerException kế thừa IOException.
- `Messager.printMessage(..., e)` định vị diagnostic tại **source element**, khác vai trò originating element với Filer.
- `return true` có nghĩa **claim annotation**, không đồng nghĩa processing thành công. Error diagnostic vẫn làm compile thất bại.
- Phép nối source string literal ở đây được kiểm thử với hai tên `Alpha`/`Beta`; với dữ liệu input tùy ý, generator cần escape Java string literal và xét tính hợp lệ của identifiers.

### 5.3. Tệp src/demo/Alpha.java

~~~java
package demo;

@GenerateHello
public final class Alpha {}
~~~

### 5.4. Tệp src/demo/Beta.java

~~~java
package demo;

@GenerateHello
public final class Beta {}
~~~

### 5.5. Tệp src/demo/App.java

~~~java
package demo;

import demo.generated.AlphaHello;
import demo.generated.BetaHello;

public final class App {
    public static void main(String[] args) {
        System.out.println(AlphaHello.text() + "/" + BetaHello.text());
    }
}
~~~

Hai generated classes chưa tồn tại trong source viết tay nhưng sẽ được compiler xử lý ở cùng invocation có processor.

## 6. Biên dịch và quan sát các round

Dùng JDK 17 trở lên, chạy trong thư mục `project` ở Bash:

~~~bash
mkdir -p api-classes processor-classes classes generated

javac --release 17 -encoding UTF-8 \
  -d api-classes api/demo/GenerateHello.java

javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/HelloProcessor.java

javac --release 17 -encoding UTF-8 \
  -cp api-classes \
  -processorpath processor-classes \
  -processor ap.HelloProcessor \
  -XprintRounds -s generated -d classes \
  src/demo/Alpha.java src/demo/Beta.java src/demo/App.java

java -cp classes demo.App
~~~

Trong PowerShell/cmd, có thể đặt mỗi lệnh `javac` trên một dòng thay vì nối dòng bằng dấu `\` của Bash. Ví dụ đã được kiểm thử với `javac 24.0.2 --release 17`, kết quả compile **exit code 0**. Các round chính:

~~~text
Round 1:
    input files: {demo.Alpha, demo.Beta, demo.App}
    annotations: [demo.GenerateHello]
    last round: false
Round 2:
    input files: {demo.generated.AlphaHello, demo.generated.BetaHello}
    annotations: []
    last round: false
Round 3:
    input files: {}
    annotations: []
    last round: true
~~~

Thụt lề và thứ tự thông tin có thể khác theo compiler. Round 2 nhìn thấy các source sinh ở round 1 sau khi writers đóng. Round cuối `processingOver()` là `true`, không phải cơ hội để tạo một source và mong có round sau.

**Stdout chính xác:**

~~~text
Alpha/Beta
~~~

Các output quan trọng:

~~~text
generated/demo/generated/AlphaHello.java
generated/demo/generated/BetaHello.java
classes/demo/Alpha.class
classes/demo/Beta.class
classes/demo/App.class
classes/demo/generated/AlphaHello.class
classes/demo/generated/BetaHello.class
~~~

Ở đây `-s generated` là output **source**, `-d classes` là output **bytecode**. Annotation API chỉ cần ở compile classpath cho source `@GenerateHello`; do có SOURCE retention và app không dùng annotation ở runtime, app mẫu chạy được với `-cp classes`.

## 7. Thí nghiệm âm tính: tạo trùng một tên

Tạo thêm file `processor/ap/BadProcessor.java`, được viết cố ý **sai** để thấy FilerException:

~~~java
package ap;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class BadProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver() || annotations.isEmpty()) return true;

        for (var ignored : round.getRootElements()) {
            try (Writer out = processingEnv.getFiler()
                    .createSourceFile("demo.generated.SharedHello").openWriter()) {
                out.write("package demo.generated; public class SharedHello {}");
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Expected duplicate: " + ex.getMessage());
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.toString());
            }
        }
        return true;
    }
}
~~~

Nó xin tạo `demo.generated.SharedHello` nhiều lần trong một round. Chỉ biên dịch `Alpha` và `Beta` ở thử nghiệm âm tính; `App` phụ thuộc các tên generated khác không được BadProcessor tạo.

~~~bash
mkdir -p bad-classes bad-generated

javac --release 17 -encoding UTF-8 \
  -d processor-classes processor/ap/BadProcessor.java

javac --release 17 -encoding UTF-8 \
  -cp api-classes \
  -processorpath processor-classes \
  -processor ap.BadProcessor \
  -s bad-generated -d bad-classes \
  src/demo/Alpha.java src/demo/Beta.java
~~~

Trong phép thử trên JDK 24 sử dụng `--release 17`, diagnostic xác định:

~~~text
error: Expected duplicate: Attempt to recreate a file for type demo.generated.SharedHello
1 error
~~~

Build trả **exit code 1**. Dù file `SharedHello.java` có thể đã được ghi bởi lần tạo đầu, output từ lần compile lỗi không được xem là artifact hợp lệ để đưa vào sản phẩm.

Nếu thật sự muốn **một class tổng hợp**, phải gom dữ liệu từ các annotated elements và gọi `createSourceFile` một lần với originating elements thích hợp. Nếu muốn **mỗi source một class**, đặt tên khác nhau như `AlphaHello` và `BetaHello`.

## 8. Ghi nhận originating elements là gì?

Các phương thức tạo file của Filer có tham số `Element... originatingElements`. Đây là **những khai báo source gây ra việc tạo output**; ví dụ:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.AlphaHello",
        alphaTypeElement);
~~~

Thông tin này là **hint cho hạ tầng build**. Một build tool hỗ trợ incremental annotation processing có thể liên kết generated output với source đã tạo nó. Khi nguồn đổi hoặc bị xóa, build tool biết phạm vi tái biên dịch và những output cần dọn.

Không được nhầm:
- **Originating element:** `TypeElement`, `PackageElement` hoặc `ModuleElement` có liên quan; dùng cho dependency tracking.
- **Diagnostic element:** phần tử truyền tới `Messager.printMessage(..., element)`, dùng để hiển thị lỗi đúng vị trí.
- **`@Generated` annotation:** metadata có thể được generator chủ động ghi vào source; **không được tự động chèn** bởi việc truyền originating element.
- **Tên file:** một chuỗi qualified name mà Filer dùng định danh output; không thay thế originating element.

Ví dụ một output tổng hợp phụ thuộc vào hai kiểu:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.generated.Registry",
        alphaTypeElement,
        betaTypeElement);
~~~

Đoạn trên chỉ minh họa chữ ký API bên trong processor, chưa phải chương trình độc lập. Nó cho biết cả hai inputs góp phần tạo output. **Không khai báo sai một origin** chỉ để làm build chạy nhanh.

Không truyền originating elements không nhất thiết gây compiler error, nhưng có thể khiến incremental build phải rebuild phạm vi rộng hơn hoặc thiếu thông tin xác định quan hệ output–input. Trên hệ thống không incremental, hint này có thể không được sử dụng.

## 9. Isolating và aggregating: áp dụng đúng với Gradle

Gradle hỗ trợ incremental annotation processing với các processor tuân thủ hợp đồng riêng. Hai loại thường gặp:

| Loại | Cách tính output | Ví dụ |
| --- | --- | --- |
| **Isolating** | Mỗi output phụ thuộc một element phù hợp | `Alpha` → `AlphaHello`; `Beta` → `BetaHello` |
| **Aggregating** | Output phụ thuộc tập nhiều elements | Tổng hợp nhiều `@Service` thành một `ServiceRegistry` |

Với processor isolating, Gradle yêu cầu từng output sinh qua Filer **có đúng một originating element** và processor tuân thủ các điều kiện incremental khác. Nếu truyền 0 hoặc nhiều elements, Gradle có thể phải biên dịch lại rộng hơn. Với aggregating, một output có thể phụ thuộc nhiều khai báo; không thể gán một origin tùy ý rồi tuyên bố output isolating.

Processor JAR có thể đăng ký incremental category trong:

~~~text
META-INF/gradle/incremental.annotation.processors
~~~

Ví dụ nội dung:

~~~text
ap.HelloProcessor,isolating
~~~

**Chỉ đăng ký như vậy nếu implementation thực tế thỏa các quy tắc isolating của phiên bản Gradle đang dùng**. Bài mẫu hạn chế input ở `demo.Alpha`, `demo.Beta`; nếu áp dụng cho nhiều package/nested types, trước hết phải sửa naming policy để mỗi source hợp lệ có output riêng và không kiểm tra kiểu khác theo cách vi phạm isolating.

Hợp đồng incremental còn liên quan đến cách processor truy cập các elements, cách tạo outputs, dữ liệu không ổn định và dependency metadata. Không dùng metadata để đánh lừa build: có thể tạo artifact stale mà clean build vẫn chạy đúng.

## 10. Xử lý lỗi trong processor: catch đúng và báo đủ ngữ cảnh

`FilerException` **kế thừa `IOException`**, nên phải bắt riêng trước:

~~~java
try (Writer out = processingEnv.getFiler()
        .createSourceFile(fullName, origin).openWriter()) {
    out.write(generatedSource);
} catch (FilerException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "Conflicting output " + fullName + ": " + ex.getMessage(),
            origin);
} catch (IOException ex) {
    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.ERROR,
            "I/O generating " + fullName + ": " + ex.getMessage(),
            origin);
}
~~~

Đây là một **trích đoạn processor**, giả định `fullName`, `origin`, `generatedSource` đã tồn tại. Cả lỗi ở `openWriter`, `write` hoặc `close` đều cần được điều tra. Thông báo nên có tên output và origin, không chỉ stack trace vô nghĩa.

Không nên:
- Bắt `FilerException` rồi bỏ qua và giả vờ generation thành công.
- Xóa file rồi retry cùng tên trong cùng invocation.
- Tự đặt tên output ngẫu nhiên để né va chạm.
- Ghi đè generated Java source bằng `java.nio.file.Files` mà không thông qua Filer.
- Nâng xung đột bắt buộc thành warning nếu thiếu class sẽ làm build sai.
- Gom mọi exception thành “duplicate” khi thực tế là permission, module hoặc lỗi I/O.

**Phát `Diagnostic.Kind.ERROR`** là lựa chọn phù hợp khi output bắt buộc không được tạo đúng. Lỗi có vị trí tại source element giúp người dùng biết khai báo nào gây xung đột. Với xung đột giữa processors, cũng cần xem processor path/service descriptors và nguồn sở hữu generated names.

## 11. Vòng đời nhiều round và trạng thái processor

Một processor có thể nhận nhiều lời gọi `process` cho các rounds trong **cùng invocation**. Nên phân biệt:
- `RoundEnvironment.processingOver() == false`: còn đang trong quá trình processing; các generated sources đóng writer có thể tạo rounds sau.
- `processingOver() == true`: final round; **không dựa vào việc tạo source ở đây** để compiler chạy thêm một round.
- `RoundEnvironment.errorRaised()`: có error được nêu ở round trước; processor có thể dùng để điều chỉnh xử lý, không phải dấu hiệu duy nhất xác định lỗi.
- `return true` của `process`: processor claim những annotation type trong round đó; **không phải** boolean báo mọi file đã tạo thành công.

`Set<String> reservedNames` trong processor ví dụ tồn tại qua các rounds của **một lần compile**. Không giữ danh sách file “đã tạo” trong static cache xuyên các lần build một cách tùy tiện: compiler daemon, incremental build và JDK toolchains có thể khiến trạng thái bị dùng sai.

Tránh generation đệ quy không có điều kiện dừng. Nếu generated source cũng mang annotation mà processor đang xử lý, round tiếp theo có thể tạo thêm source và kéo dài không cần thiết. Quy tắc đặt tên và trạng thái generation cần được thiết kế để luôn kết thúc.

## 12. Sinh một registry chung đúng cách

Nếu mục tiêu là một file `Registry` từ nhiều annotated classes, hãy chọn mô hình **aggregating**:

1. Thu thập thông tin các annotated types và các originating elements tương ứng.
2. Sắp xếp tên theo thứ tự ổn định để output có tính tái lập.
3. Chọn một thời điểm khi đã có đủ dữ liệu và processing **chưa ở final round**.
4. **Gọi Filer đúng một lần** cho `Registry`, truyền các origins thực sự liên quan.
5. Đóng writer và để compiler nhận file đã sinh.
6. Đăng ký metadata aggregating với build tool khi implementation thỏa hợp đồng.

Pseudocode minh họa phần thu thập, không phải toàn bộ source có thể chạy độc lập:

~~~java
Map<String, TypeElement> contributors = new TreeMap<>();
for (Element e : round.getElementsAnnotatedWith(serviceAnnotation)) {
    if (e instanceof TypeElement type) {
        contributors.put(type.getQualifiedName().toString(), type);
    }
}

// Sau khi có đủ inputs và trước final round:
// Element[] origins = contributors.values().toArray(new Element[0]);
// JavaFileObject file = filer.createSourceFile("demo.generated.Registry", origins);
// try (Writer out = file.openWriter()) { ... }
~~~

Nếu processor khác có thể sinh thêm các annotated types ở rounds sau, phải thiết kế thời điểm “đã đủ input” cẩn thận. Không được tạo lại `Registry` ở mỗi round; Filer sẽ từ chối. Với các pipeline phức tạp, tách generation từng type và bước aggregation thành task riêng có thể dễ bảo trì hơn.

Tương tự, một service descriptor `META-INF/services/...` là **một resource**. Đừng tạo resource đó một lần cho mỗi annotated class; hãy tổng hợp provider names rồi ghi một file với thứ tự ổn định.

## 13. Output cũ và incremental build

Một vòng kiểm chứng tốt gồm các bước:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Clean compile | Mỗi output được tạo một lần, đúng tên và đúng contents |
| Build lại không sửa input | Không xuất hiện FilerException do logic round, không xuất bản file cũ sai |
| Sửa `Alpha.java` | Output liên quan được cập nhật đúng; không phụ thuộc thứ tự elements |
| Xóa `Alpha.java` | Output `AlphaHello` được build tool dọn đúng khi incremental support thực thi |
| Thêm `Gamma.java` | Có output mới, không va chạm generated names hiện hữu |
| Hai type trùng simple name | Naming policy phân biệt đầy đủ, hoặc báo duplicate một cách rõ ràng |
| Hai processors tạo cùng name | Build thất bại với thông báo xác định ai sở hữu output |
| Generated source có lỗi cú pháp | Compiler báo lỗi, không phát hành artifact thiếu hoặc stale |

**Lưu ý:** việc một generated file cũ vẫn tồn tại sau compile lỗi không chứng minh invocation hiện tại thành công. Hãy kiểm tra exit code và clean build, không chỉ nhìn một tệp trong output directory.

Nếu generated source bị **thêm nhầm vào tập input Java ban đầu** và đồng thời processor vẫn tạo nó, lỗi sẽ khác việc file chỉ còn trên đĩa từ build cũ. Sửa source set/compile task để build tool quản lý output, không commit bản generated vào nơi source chính mà processor cũng tạo trùng.

## 14. Với Java modules và tên output

Trong môi trường JPMS, Filer có thể phải xác định **module đích** của source được sinh. Một số cấu hình module-aware cho phép tên được tiền tố bằng module:

~~~java
processingEnv.getFiler().createSourceFile(
        "demo.module/demo.generated.AlphaHello",
        sourceType);
~~~

Đây là **trích đoạn cho môi trường module-aware**, chỉ hợp lệ nếu target module thực sự tồn tại và compiler hỗ trợ ghi output cho module đó. Không dùng nguyên mẫu trong ứng dụng classpath thông thường không có module này.

`FilerException` có thể báo module không xác định hoặc target module không writable ngay cả khi chưa hề tạo trùng filename. Kiểm tra module path, module descriptor, `-s`, `-d` và tên module; `Set<String>` không sửa được những lỗi đó.

Đường dẫn **nạp processor** (ví dụ `--processor-module-path`) không đồng nghĩa module của **generated class**. Hãy phân biệt processor module, application module và target module của Filer.

## 15. Maven, Gradle và quyền sở hữu output

### Maven

Maven Compiler Plugin thường quản lý generated Java sources trong thư mục như `target/generated-sources/annotations`. Đường dẫn phụ thuộc plugin và cấu hình cụ thể. Các tình huống cần kiểm tra:
- Có nhiều compiler executions cùng tạo một tên output không?
- Generated sources có bị include thành source ban đầu trong cùng invocation gây round-0 collision không?
- Processor artifact hoặc phiên bản plugin có bị khai báo trùng không?
- Source and output directories có bị dùng chung giữa modules không?

Dùng `mvn clean compile` để kiểm tra baseline sạch, sau đó sửa cấu hình plugin/source paths theo cơ chế build thay vì xóa file vào giữa một processing run. Với code generator cần incremental tracking, phải xem khả năng hỗ trợ của plugin/compiler và dữ liệu origins.

### Gradle

Ví dụ một đoạn Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'example:annotation-api:1.0'
    annotationProcessor 'example:processor:1.0'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}
~~~

Các tọa độ `example:...` là **minh họa**, không phải artifact được xác nhận tồn tại. `annotationProcessor` thiết lập dependency path để chạy processor; `compileOnly` phù hợp khi annotation API chỉ cần cho compile. Generated source phải được JavaCompile task quản lý.

Chạy `./gradlew clean compileJava` (Windows: `gradlew.bat clean compileJava`) để tạo baseline, rồi thử build incremental sau sửa/xóa source. Nếu chỉ clean build đúng nhưng incremental build sai, tập trung kiểm tra origins, metadata isolating/aggregating và quyền sở hữu output; không đánh dấu processor isolating khi dữ liệu sinh phụ thuộc nhiều unrelated elements.

## 16. Quy trình chẩn đoán FilerException có thứ tự

1. Đọc **toàn bộ message**: tên type/file, module, location, nguyên nhân cụ thể.
2. Ghi compiler JDK và **danh sách processor thực tế** được load trong invocation.
3. Kiểm tra flags `-processorpath`, `--processor-module-path`, `-s`, `-d`, source paths và modules.
4. Bật `-XprintRounds` / `-XprintProcessorInfo` để biết thứ tự round và processors được gọi.
5. Ghi tên **output trước mỗi lần gọi Filer**, cùng originating type và round, giúp định vị lần thứ hai.
6. Xác minh có xung đột từ **cùng loop, round trước, processor khác hay input round 0**.
7. Kiểm tra scheme tên: package, nested classes, module và collisions do simple names.
8. Phân biệt `FilerException` với `IOException` khác; kiểm tra module targets, permissions và path validity.
9. Xác minh writer được đóng và processing không phát source trong final round.
10. Kiểm tra originating elements và quy tắc incremental của build tool.
11. Build sạch để tách lỗi logic khỏi output stale; sau đó test incremental.
12. Sửa nguyên nhân và chạy lại end-to-end, không suppress hoặc retry xung đột.

## 17. Câu hỏi tự kiểm tra

**1.** Trong cùng round, hai annotated classes cùng gọi `createSourceFile("demo.Generated")`. Điều gì xảy ra ở lần hai?  
**Đáp án:** Có thể bị `FilerException` vì cùng output đã được tạo trong invocation.

**2.** Tệp generated từ lần build trước tồn tại trên đĩa. Lần build mới tạo lại tên đó có chắc lỗi không?  
**Đáp án:** Không. Cần phân biệt file cũ, input round 0 và việc tạo lặp trong invocation mới.

**3.** Vì sao dùng `createSourceFile(fullName, type)` thay vì chỉ `createSourceFile(fullName)`?  
**Đáp án:** Truyền originating element để tooling liên kết output với nguồn gây ra output.

**4.** Một file registry phụ thuộc 20 source types có được đánh dấu isolating với một origin bất kỳ không?  
**Đáp án:** Không. Nó là bài toán aggregating và cần khai báo tracking theo đúng quan hệ thật.

**5.** Có thể catch `IOException` trước `FilerException` không?  
**Đáp án:** Không. `FilerException` là subclass của `IOException`; catch subclass sau superclass không thể đạt đến.

**6.** Processor có `Set<String>` nhưng vẫn gặp duplicate, nên kiểm tra gì?  
**Đáp án:** Processor khác, source input round 0, resource/source/class collision, module/path validity.

**7.** `createResource` có cho phép ghi một service descriptor lặp lại nhiều lần không?  
**Đáp án:** Không được giả định; Filer theo dõi pathname của resource trong invocation.

**8.** `@Generated` và originating element có giống nhau không?  
**Đáp án:** Không. Annotation có thể nằm trong source sinh ra; originating element là metadata hint truyền vào Filer.

**9.** Có nên tạo source ở round cuối và mong có round tiếp theo không?  
**Đáp án:** Không. `processingOver()==true` chỉ processing sắp kết thúc.

**10.** Nếu báo lỗi target module không writable thì có phải chắc chắn hai lời gọi tạo trùng?  
**Đáp án:** Không. Cần kiểm tra module/output configuration của compiler.

## 18. Tài liệu chuẩn

- [Java SE 17 Filer API: creation rules, originating elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [Java SE 17 FilerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/FilerException.html)
- [Java SE 17 RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Gradle Java plugin: incremental annotation processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Oracle javac command (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)

**Kết luận:** Một processor đáng tin phải kiểm soát **tên output**, **thời điểm tạo** và **nguồn tạo ra output**. Dùng Filer để sinh tệp, kiểm tra duplicate trong processor, tôn trọng FilerException giữa các processors/rounds, truyền originating elements đúng và kiểm tra clean/incremental builds. Tránh nuốt lỗi hoặc sửa generated files thủ công chỉ để một lần compile qua.
