# Rà soát annotation processor cùng công cụ xây dựng

## 1. Mục tiêu và phạm vi

Annotation processor là chương trình chạy trong lúc biên dịch Java để đọc annotation, kiểm tra mã nguồn và có thể sinh thêm mã nguồn hoặc tài nguyên. Rà soát processor cùng công cụ xây dựng nhằm bảo đảm:

- Chỉ những processor cần thiết mới được chạy và chúng đến từ dependency đáng tin cậy.
- Processor tương thích với JDK, phiên bản ngôn ngữ, hệ module và build tool của dự án.
- Mã được sinh ra ổn định, có thể kiểm tra, không phụ thuộc thứ tự chạy ngẫu nhiên.
- Build có thể tái lập trên máy lập trình viên và CI, đồng thời tận dụng được incremental compilation khi processor hỗ trợ.
- Dependency của processor không vô tình trở thành dependency lúc chạy ứng dụng.

Bối cảnh Java 9 vẫn có giá trị ở hệ module JPMS và tùy chọn `--processor-module-path`. Tuy nhiên, dự án thực tế nên chọn một JDK còn được hỗ trợ, ghim phiên bản build tool và đặt `--release` theo mức Java mà sản phẩm cần hỗ trợ. Các ví dụ dưới đây dùng Java 17 để minh họa một baseline hiện đại; hãy thay bằng release đã được dự án phê duyệt.

## 2. Annotation processing hoạt động như thế nào?

Annotation processing chuẩn được định nghĩa bởi JSR 269. API nằm trong module `java.compiler`, với các kiểu thường dùng như `Processor`, `AbstractProcessor`, `RoundEnvironment`, `Filer`, `Messager` và `javax.lang.model.*`.

Một lượt biên dịch có thể có nhiều processing round:

1. Compiler phân tích source và tìm các annotation mà processor quan tâm.
2. Processor nhận tập annotation cùng `RoundEnvironment`, sau đó kiểm tra element qua Language Model API.
3. Processor có thể báo lỗi/cảnh báo bằng `Messager`, hoặc sinh source/resource bằng `Filer`.
4. Source vừa sinh được đưa vào round tiếp theo. Quá trình tiếp tục cho đến khi không còn source mới hoặc đã đến round cuối.
5. Compiler biên dịch source ban đầu cùng source được sinh trong quá trình đó.

Processor thường kế thừa `AbstractProcessor` và khai báo annotation, source version, option mà nó hỗ trợ. Phương thức `process(...)` trả về `true` khi processor nhận xử lý các annotation đã khai báo; trả về `false` cho phép processor khác cũng xử lý chúng. Không nên dựa vào thứ tự processor để tạo kết quả đúng.

Một processor tốt cần:

- Chỉ xử lý đúng annotation và element mà nó hỗ trợ.
- Dùng `Filer` để tạo file, truyền originating element khi có thể để build tool theo dõi quan hệ đầu vào/đầu ra.
- Không ghi đè file đã được tạo trong cùng compilation; xử lý lỗi trùng tên một cách rõ ràng.
- Sinh kết quả xác định từ cùng đầu vào, không phụ thuộc thời gian, thứ tự file, máy chạy hay biến môi trường không được khai báo.
- Dùng `Messager` với mức `ERROR`, `WARNING` hoặc `NOTE` để thông báo có vị trí và ngữ cảnh.
- Khai báo source version và các option `-Akey=value` mà nó thực sự hỗ trợ.

### Cơ chế tìm và bật processor

Với processor nằm trên classpath, cơ chế service provider dùng file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

File chứa tên đầy đủ của từng lớp processor, mỗi tên trên một dòng. Với processor được đóng gói thành named module, module descriptor có thể khai báo service provider:

~~~java
module demo.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with demo.processor.GenerateMarkerProcessor;
}
~~~

Các tùy chọn compiler liên quan:

| Tùy chọn | Công dụng |
| --- | --- |
| `--processor-path` hoặc `-processorpath` | Đường dẫn classpath chứa processor và dependency của processor |
| `--processor-module-path` | Module path dành cho processor dạng module |
| `-processor` | Chỉ định rõ tên lớp processor cần chạy |
| `-Akey=value` | Truyền option riêng cho processor |
| `-s <dir>` | Thư mục chứa source được sinh |
| `-proc:only` | Chạy annotation processing mà không thực hiện biên dịch thông thường |
| `-proc:none` | Tắt annotation processing |
| `-proc:full` | Thực hiện annotation processing và biên dịch |

Classpath/module path của processor là đường dẫn cho mã chạy trong compiler; chúng không đồng nghĩa với module path hoặc runtime classpath của ứng dụng.

**Thay đổi cần nhớ từ JDK 23:** không dựa vào việc compiler tự quét processor trên classpath như một hành vi mặc định. Hãy khai báo processor tường minh qua processor path/module path, tên processor hoặc chế độ xử lý phù hợp. Cấu hình build rõ ràng giúp build có hành vi nhất quán giữa các JDK và tránh chạy processor ngoài dự kiến.

## 3. Quy trình rà soát processor

### 3.1. Lập danh sách processor thực sự được chạy

Kiểm tra cả cấu hình build và dependency graph. Với mỗi processor, ghi nhận:

- Tên lớp processor, artifact và phiên bản.
- Annotation mà processor xử lý.
- Module hoặc source set áp dụng: main, test, generated source hay module con.
- Dependency phụ thuộc của chính processor.
- Thư mục và loại file được sinh.
- Ai chịu trách nhiệm cập nhật phiên bản và xử lý lỗi khi processor không tương thích.

Không suy luận processor đang chạy chỉ từ việc dự án có annotation trong source. Hãy xem cấu hình compiler thực tế và log của build. Một dependency có tên gợi ý annotation chưa chắc là processor; ngược lại, một thư viện có thể mang theo processor qua service provider.

### 3.2. Kiểm tra nguồn gốc và rủi ro bảo mật

Processor là mã thực thi trong tiến trình build. Khi được chạy, nó có thể đọc file, biến môi trường và thông tin có quyền truy cập của tài khoản build; một processor không đáng tin có thể gây rủi ro như bất kỳ plugin hoặc dependency thực thi nào.

Cần kiểm tra:

- Artifact đến từ repository được tổ chức tin cậy, đúng group/artifact và phiên bản.
- Phiên bản được ghim; không dùng dynamic version hoặc lấy dependency tùy ý từ repository không kiểm soát.
- License, lịch sử phát hành, mức độ bảo trì và hỗ trợ JDK đang dùng.
- Báo cáo lỗ hổng và dependency bắc cầu của processor.
- Build có tải mã hoặc thực hiện tác vụ ngoài phạm vi cần thiết hay không.
- Processor có ghi file ngoài thư mục build, truy cập mạng hoặc đọc secret trong CI hay không.

Ưu tiên dependency verification, dependency locking và repository policy của build tool khi dự án đã áp dụng. Không đưa credential vào option processor hoặc log build. Chỉ cấp cho CI quyền cần thiết để biên dịch.

### 3.3. Kiểm tra tương thích JDK và module

Đối chiếu ít nhất bốn phiên bản: JDK chạy build, release đích của source, phiên bản processor và phiên bản Maven/Gradle cùng compiler plugin.

- Dùng JDK toolchain hoặc cấu hình tương đương để mọi môi trường build cùng một JDK.
- Dùng `--release` hoặc thuộc tính `release` của build tool để giới hạn cả cú pháp và API nền tảng được phép dùng. Chỉ đặt `source`/ `target` riêng không cung cấp cùng mức kiểm tra API.
- Xác nhận processor không phụ thuộc API nội bộ của compiler hoặc chi tiết triển khai riêng của một JDK.
- Nếu processor là named module, kiểm tra `requires java.compiler`, khai báo `provides` và dùng processor module path.
- Nếu processor ở classpath, kiểm tra service descriptor và processor path.
- Với dự án có `module-info.java`, xác nhận annotation API và dependency của ứng dụng được khai báo đúng; không đưa processor vào runtime module của ứng dụng nếu không có nhu cầu thực tế.

Một số công cụ dùng annotation nhưng không chỉ dựa trên JSR 269. Ví dụ, công cụ có tích hợp sâu với compiler cần được rà soát riêng về hỗ trợ JDK và build tool. Không kết luận rằng mọi thư viện có annotation đều hoạt động như một processor chuẩn.

### 3.4. Kiểm tra chất lượng mã được sinh

Mở thư mục generated source sau một clean build và kiểm tra:

- File được sinh đúng package, tên lớp, visibility, import và kiểu dữ liệu.
- Source sinh ra biên dịch được với release đích.
- Không có file trùng tên hoặc hai processor cùng ghi một output.
- Nội dung không chứa đường dẫn máy cá nhân, timestamp, giá trị ngẫu nhiên hoặc thông tin bí mật.
- Output chỉ nằm trong thư mục build đã cấu hình.
- Lỗi đầu vào được báo tại annotation/element liên quan, thay vì chỉ ném stack trace khó hiểu.
- Source được sinh không được đưa nhầm vào source set đầu vào lần nữa gây lặp hoặc xung đột.

Thông thường, generated source nên được tạo lại trong build và không cần commit vào repository. Chỉ lưu generated source khi quy ước của dự án yêu cầu rõ ràng và có quy trình kiểm tra tính đồng bộ.

## 4. Ví dụ processor tối giản trên Java 17

Ví dụ sau tạo một lớp có hậu tố `Generated` cho mỗi lớp được đánh dấu bằng `@GenerateMarker`. Đây là ví dụ minh họa API JSR 269; trong dự án thật cần bổ sung kiểm tra tên, xử lý lỗi và test cho các trường hợp biên.

Annotation:

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

Processor:

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

@SupportedAnnotationTypes("demo.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GenerateMarkerProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {
            if (!(element instanceof TypeElement type)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateMarker chỉ áp dụng cho type",
                        element);
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String generatedName = type.getSimpleName() + "Generated";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try (Writer out = processingEnv.getFiler()
                    .createSourceFile(qualifiedName, type).openWriter()) {
                if (!packageName.isEmpty()) {
                    out.write("package " + packageName + ";\n\n");
                }
                out.write("public final class " + generatedName + " {}\n");
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không tạo được " + qualifiedName + ": " + ex,
                        element);
            }
        }

        return true;
    }
}
~~~

Lớp đầu vào:

~~~java
package demo;

@GenerateMarker
public class Customer {
}
~~~

Biên dịch processor trước, sau đó dùng thư mục class của processor làm cả classpath cho annotation API lẫn processor path. Các thư mục output phải tồn tại trước khi chạy lệnh:

~~~bash
mkdir -p build/processor-classes build/classes build/generated
javac --release 17 -d build/processor-classes src/processor/java/demo/GenerateMarker.java src/processor/java/demo/GenerateMarkerProcessor.java
javac --release 17 -classpath build/processor-classes --processor-path build/processor-classes -processor demo.GenerateMarkerProcessor -s build/generated -d build/classes src/app/java/demo/Customer.java
~~~

Kết quả được sinh tại `build/generated/demo/CustomerGenerated.java`:

~~~java
package demo;

public final class CustomerGenerated {}
~~~

Compiler cũng biên dịch source được sinh và đặt class tương ứng trong `build/classes`. Do lệnh chỉ định rõ `--processor-path` và `-processor`, cách chạy này không phụ thuộc vào việc tự dò processor trên classpath. Trong ví dụ dùng thư mục class thay cho JAR nên không cần service descriptor; khi đóng gói processor thành JAR để tự động discovery, cần thêm file `META-INF/services/javax.annotation.processing.Processor` hoặc khai báo `provides` trong module descriptor.

## 5. Cấu hình với Maven

Với Maven, dependency annotation API và processor nên được khai báo riêng. Ví dụ dùng MapStruct:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>1.6.3</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>1.6.3</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Điểm cần rà soát:

- `mapstruct` là API mà source và mã được sinh sử dụng; `mapstruct-processor` là công cụ chạy lúc compile.
- `annotationProcessorPaths` xác định rõ processor path. Khai báo từng processor cần dùng và cả phiên bản của nó.
- Nếu dự án có nhiều processor, thêm từng entry và kiểm tra chúng có xung đột output hay không.
- Nếu muốn giới hạn processor được chạy, cấu hình danh sách processor class mà compiler plugin hỗ trợ.
- Đặt compiler plugin ở phiên bản tương thích với JDK đang dùng; không phụ thuộc phiên bản plugin mặc định có thể thay đổi theo môi trường.
- Kiểm tra cả compile của main source và test source nếu test cũng dùng annotation processor.

Maven Compiler Plugin thường đặt generated source trong `target/generated-sources/annotations`. Hãy kiểm tra thư mục thực tế và cấu hình source root do plugin quản lý thay vì tự thêm cùng một thư mục nhiều lần.

## 6. Cấu hình với Gradle

Với Gradle Java plugin, dùng configuration chuyên biệt cho processor:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.mapstruct:mapstruct:1.6.3")
    annotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")

    // Chỉ khai báo nếu test source cũng cần processor.
    testAnnotationProcessor("org.mapstruct:mapstruct-processor:1.6.3")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Ý nghĩa:

- `annotationProcessor` dành cho processor của source set main.
- `testAnnotationProcessor` dành cho processor của test source set.
- `implementation` chứa API mà ứng dụng cần trong compile/runtime theo thiết kế của thư viện. Không dùng configuration này chỉ để làm processor được phát hiện.
- Java toolchain chọn JDK chạy compiler; `options.release` đặt mức API/language target. Hai giá trị có thể khác nhau, ví dụ chạy JDK 21 nhưng biên dịch tương thích Java 17.
- Nếu dùng nhiều source set, kiểm tra configuration processor tương ứng cho từng source set.

Gradle thường đặt generated source của main Java trong `build/generated/sources/annotationProcessor/java/main`. Đừng tự thêm output folder này thành input source folder lần thứ hai nếu plugin đã quản lý nó.

### Incremental annotation processing trong Gradle

Gradle có thể tối ưu compile khi processor khai báo đúng loại xử lý trong file:

~~~text
META-INF/gradle/incremental.annotation.processors
~~~

Ví dụ nội dung:

~~~text
com.example.GenerateMarkerProcessor,isolating
~~~

Hai loại thường gặp:

- **Isolating:** output của một element chỉ phụ thuộc element đầu vào đó. Processor phải truyền originating element tương ứng cho `Filer`.
- **Aggregating:** output phụ thuộc tập hợp nhiều element, ví dụ tạo registry tổng hợp từ mọi class có annotation.

Chỉ khai báo processor là incremental khi hành vi thực tế đáp ứng đúng hợp đồng. Khai báo sai có thể khiến output lỗi khi build incremental. Nếu processor không hỗ trợ incremental, Gradle có thể phải biên dịch lại rộng hơn; tính đúng đắn luôn quan trọng hơn tốc độ.

## 7. Rà soát build tool và dependency

Ngoài cấu hình processor, cần kiểm tra toàn bộ chuỗi build:

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| JDK/toolchain | CI và máy lập trình viên dùng JDK đã thống nhất |
| Build wrapper | Dùng Maven Wrapper hoặc Gradle Wrapper với phiên bản được ghim |
| Compiler plugin | Phiên bản hỗ trợ JDK và tùy chọn compiler của dự án |
| Processor path | Chỉ chứa processor cần thiết và dependency đã kiểm soát |
| API dependency | Scope phù hợp với việc source/generated code có dùng API lúc runtime hay không |
| Phiên bản | Không dùng dynamic version; cập nhật có chủ đích và có kiểm tra |
| Generated source | Output nằm trong build directory, được tạo lại từ đầu vào |
| Incremental build | Processor khai báo đúng khả năng incremental; clean build vẫn thành công |
| CI | Build không phụ thuộc file cục bộ hoặc secret không được khai báo |
| Bảo mật | Kiểm tra nguồn, license, lỗ hổng và dependency bắc cầu |

Lệnh kiểm tra hữu ích:

~~~bash
# Maven: xem dependency tree và chạy lại compile/test từ trạng thái sạch
./mvnw dependency:tree
./mvnw clean test

# Gradle: xem processor dependency và chạy compile với log chi tiết
./gradlew dependencies --configuration annotationProcessor
./gradlew dependencyInsight --dependency mapstruct-processor --configuration annotationProcessor
./gradlew clean test --info
~~~

Tên configuration của Gradle phụ thuộc source set; ví dụ trên áp dụng cho main source set của Java plugin. Nếu processor được dùng trong test hoặc source set khác, kiểm tra configuration tương ứng.

Với javac trực tiếp, có thể bật thông tin chẩn đoán khi điều tra:

~~~bash
javac -XprintRounds -XprintProcessorInfo -Xlint:processing --release 17 -classpath build/processor-classes --processor-path build/processor-classes -processor demo.GenerateMarkerProcessor -s build/generated -d build/classes src/app/java/demo/Customer.java
~~~

Các log này giúp xác nhận round, processor nào được gọi và cảnh báo liên quan đến annotation processing. Không bật log quá chi tiết trong mọi build nếu nó làm nhiễu log CI.

## 8. Kiểm thử sau khi cấu hình

Một lần build thành công chưa đủ để kết luận processor được cấu hình đúng. Thực hiện các bước sau:

1. Xóa output build và chạy clean build để xác nhận toàn bộ generated source có thể được tái tạo.
2. Kiểm tra log compiler để xác nhận đúng processor và đúng phiên bản đã chạy.
3. Kiểm tra file được sinh, nội dung, package và class output.
4. Biên dịch với JDK toolchain đã chọn và release mục tiêu; nếu dự án hỗ trợ nhiều JDK, chạy ma trận CI cho các JDK đó.
5. Thay đổi một input nhỏ rồi chạy incremental build. Kiểm tra output phụ thuộc được cập nhật và output không liên quan không bị hỏng.
6. Chạy test cho cả mã nguồn viết tay và mã được sinh.
7. Thực hiện build từ checkout sạch trên CI để phát hiện phụ thuộc vào file hoặc cache cục bộ.
8. Nếu nâng phiên bản processor, so sánh generated source trước/sau và kiểm tra thay đổi hành vi, dependency cùng hiệu năng build.

Không dùng `-proc:none` như cách sửa lỗi mặc định. Tùy chọn này tắt processor và có thể làm thiếu lớp được sinh. Chỉ dùng khi module thực sự không cần processing hoặc trong bước kiểm tra có chủ đích.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Annotation có trong source nhưng không sinh code | Processor chưa nằm trong processor path hoặc chưa được bật | Kiểm tra cấu hình Maven/Gradle và log compiler; đặc biệt chú ý hành vi mặc định từ JDK 23 |
| Không tìm thấy annotation khi compile | API dependency chưa nằm trong compile classpath/module path | Khai báo API dependency đúng scope và kiểm tra module descriptor |
| Processor chạy nhưng không nhận annotation | Sai tên annotation, package hoặc `@SupportedAnnotationTypes` | Đối chiếu tên đầy đủ và kiểm tra processor rounds |
| Không tạo được source | Tên output trùng, package không hợp lệ hoặc lỗi I/O | Kiểm tra `Filer`, originating element và diagnostic từ processor |
| Build local chạy, CI lỗi | JDK, wrapper, repository hoặc dependency khác nhau | Dùng wrapper/toolchain, ghim dependency và chạy từ checkout sạch |
| Build incremental sinh output cũ | Metadata incremental sai hoặc processor không theo dõi đầu vào | Kiểm tra loại isolating/aggregating và originating elements; đối chiếu với clean build |
| Lỗi trên JDK mới | Processor dùng API nội bộ hoặc chưa hỗ trợ JDK | Nâng processor/plugin lên bản hỗ trợ; bỏ phụ thuộc vào compiler internals |
| Ứng dụng lỗi lúc runtime | Processor/API bị khai báo nhầm scope hoặc generated code cần API runtime chưa có | Kiểm tra dependency tree và các kiểu mà generated code tham chiếu |

## 10. Checklist nghiệm thu

- [ ] Đã liệt kê mọi processor thực sự chạy trong từng source set.
- [ ] Đã xác minh nguồn, phiên bản, license, bảo trì và dependency bắc cầu.
- [ ] Processor được khai báo tường minh trong build; không phụ thuộc auto-discovery ngoài ý muốn.
- [ ] JDK toolchain, compiler plugin và release đích tương thích.
- [ ] Classpath processor và module path processor được phân biệt đúng.
- [ ] Generated source nằm trong build directory, xác định và biên dịch được.
- [ ] Processor không tạo output trùng, không ghi ra ngoài phạm vi và không làm lộ secret.
- [ ] Incremental metadata đúng với hành vi thực tế; clean build và incremental build đều đạt.
- [ ] Main/test source set có cấu hình processor phù hợp.
- [ ] CI chạy được từ checkout sạch bằng wrapper và toolchain đã ghim.

## Kết luận

Rà soát annotation processor là rà soát một phần mã thực thi trong build pipeline. Cấu hình processor path riêng, ghim dependency, chọn JDK/release rõ ràng, kiểm tra generated source và xác minh cả clean lẫn incremental build sẽ giúp quá trình biên dịch an toàn, dễ tái lập và dễ chẩn đoán. Các API JSR 269 và hỗ trợ module của Java 9 vẫn là nền tảng liên quan; dự án mới nên áp dụng chúng trên JDK và build tool còn được hỗ trợ.
