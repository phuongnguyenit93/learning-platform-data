# Annotation processor trong modular compilation

## 1. Annotation processing trong quy trình biên dịch module

Annotation processor là chương trình chạy trong quá trình biên dịch Java để đọc annotation, phân tích cấu trúc source code và có thể sinh thêm source file hoặc resource. Ví dụ thường gặp là processor tạo mapper, builder, metadata, registry hoặc mã hỗ trợ dependency injection.

Khi chuyển một dự án sang Java Platform Module System (JPMS), processor vẫn dùng API chuẩn trong \`javax.annotation.processing\` và \`javax.lang.model\`. Điểm thay đổi quan trọng là cách compiler tìm và nạp processor:

- Processor nằm trên classpath của compiler thường được tìm qua \`--processor-path\` và file service \`META-INF/services/javax.annotation.processing.Processor\`.
- Processor là một named module có thể được tìm qua \`--processor-module-path\`; module descriptor đăng ký service bằng \`provides javax.annotation.processing.Processor with ...\`.
- Các module của ứng dụng được biên dịch vẫn được tìm qua \`--module-path\` hoặc module source path. Processor path và module path phục vụ hai mục đích khác nhau.

Processor thường chỉ là dependency của build. Ứng dụng sử dụng annotation và source được sinh ra có thể không cần module processor khi chạy production.

## 2. Tách annotation API, processor và ứng dụng thành các module

Ví dụ này sử dụng ba module:

| Module | Trách nhiệm |
| --- | --- |
| \`com.acme.annotations\` | Khai báo annotation được dùng trong source của ứng dụng. |
| \`com.acme.processor\` | Đọc annotation và sinh Java source trong lúc compile. |
| \`com.acme.app\` | Sử dụng annotation và gọi class do processor tạo ra. |

Cấu trúc thư mục:

~~~text
src/
  com.acme.annotations/
    module-info.java
    com/acme/annotations/GenerateGreeting.java
  com.acme.processor/
    module-info.java
    com/acme/processor/GreetingProcessor.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
~~~

Tên thư mục module khớp với tên module trong \`module-info.java\`. Khi dùng \`--module-source-path\`, javac có thể tìm nhiều module theo cấu trúc này.

### 2.1. Module annotation

File \`src/com.acme.annotations/module-info.java\`:

~~~java
module com.acme.annotations {
    exports com.acme.annotations;
}
~~~

Annotation được export để module processor và module ứng dụng có thể tham chiếu:

~~~java
package com.acme.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

\`RetentionPolicy.SOURCE\` có nghĩa annotation chỉ cần tồn tại trong source lúc compile. Nó không cần xuất hiện trong bytecode của ứng dụng. Vì vậy, module ứng dụng có thể khai báo dependency annotation bằng \`requires static\` nếu annotation chỉ phục vụ biên dịch.

### 2.2. Module annotation processor

File \`src/com.acme.processor/module-info.java\`:

~~~java
module com.acme.processor {
    requires java.compiler;
    requires com.acme.annotations;

    provides javax.annotation.processing.Processor
            with com.acme.processor.GreetingProcessor;
}
~~~

\`java.compiler\` chứa API như \`Processor\`, \`AbstractProcessor\`, \`RoundEnvironment\`, \`Filer\`, \`Element\` và \`TypeElement\`. Processor cần \`requires java.compiler\` để sử dụng các API đó.

Chỉ thị \`provides\` đăng ký implementation với service \`javax.annotation.processing.Processor\`. Khi javac tìm processor trên processor module path, nó có thể khám phá lớp này qua service binding của JPMS.

Package chứa processor không cần \`exports\` chỉ để javac nạp provider đã được khai báo bằng \`provides\`. Hãy export package riêng nếu module khác cần gọi public API của processor trực tiếp.

### 2.3. Module ứng dụng

File \`src/com.acme.app/module-info.java\`:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Ứng dụng chỉ cần annotation trong giai đoạn compile. \`requires static\` yêu cầu module annotation có mặt khi biên dịch nhưng cho phép module đó vắng mặt ở runtime. Module ứng dụng không cần khai báo \`requires com.acme.processor\`, vì processor được chạy bởi compiler chứ không phải bởi ứng dụng.

Source sử dụng annotation:

~~~java
package com.acme.app;

import com.acme.annotations.GenerateGreeting;

@GenerateGreeting
public class Main {
    public static void main(String[] args) {
        System.out.println(MainGenerated.message());
    }
}
~~~

\`MainGenerated\` là class sẽ được tạo trong quá trình annotation processing. Compiler sẽ xử lý source được sinh ra ở các vòng tiếp theo và biên dịch nó cùng module ứng dụng.

## 3. Viết processor bằng API chuẩn

Processor kế thừa \`AbstractProcessor\`, khai báo annotation cần xử lý và phiên bản source Java mà nó hỗ trợ.

~~~java
package com.acme.processor;

import com.acme.annotations.GenerateGreeting;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;

@SupportedAnnotationTypes("com.acme.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_21)
public final class GreetingProcessor extends AbstractProcessor {

    private final Set<String> generatedNames = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return false;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();

            String simpleName = type.getSimpleName() + "Generated";
            String qualifiedName = packageName.isEmpty()
                    ? simpleName
                    : packageName + "." + simpleName;

            if (!generatedNames.add(qualifiedName)) {
                continue;
            }

            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile(qualifiedName, type)
                    .openWriter()) {

                if (!packageName.isEmpty()) {
                    writer.write("package " + packageName + ";\\n\\n");
                }

                writer.write("public final class " + simpleName + " {\\n");
                writer.write("    private " + simpleName + "() {}\\n");
                writer.write("    public static String message() {\\n");
                writer.write("        return \\"Generated during compilation\\";\\n");
                writer.write("    }\\n");
                writer.write("}\\n");

            } catch (FilerException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Generated source already exists: " + qualifiedName,
                        element);
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": "
                                + exception.getMessage(),
                        element);
            }
        }

        return true;
    }
}
~~~

Một số điểm cần hiểu trong ví dụ:

- \`@SupportedAnnotationTypes\` chỉ định annotation processor quan tâm. Có thể dùng wildcard, nhưng khai báo tên cụ thể giúp compiler biết processor xử lý loại annotation nào.
- \`@SupportedSourceVersion\` khai báo phiên bản source được hỗ trợ. Ví dụ này nhắm tới Java 21.
- \`RoundEnvironment\` đại diện cho một vòng xử lý. Source được sinh ra có thể tạo thêm vòng xử lý tiếp theo.
- \`Elements\` và \`Types\` trong \`processingEnv\` cho phép phân tích mô hình ngôn ngữ Java mà không cần nạp class ứng dụng bằng reflection.
- \`Filer\` tạo source hoặc resource trong output của compiler. Truyền phần tử gốc \`type\` vào \`createSourceFile\` giúp compiler và build tool biết source được sinh ra từ phần tử nào.
- Processor ghi diagnostic qua \`Messager\`; dùng \`Diagnostic.Kind.ERROR\` để làm compilation thất bại khi không thể tạo source cần thiết.
- Tập \`generatedNames\` ngăn processor cố tạo cùng một source nhiều lần trong một compilation.

Processor không cần mở package của ứng dụng bằng \`opens\` để đọc annotation và cấu trúc source. Hãy ưu tiên API mô hình \`Element\`, \`TypeMirror\`, \`Elements\` và \`Types\`. Source code được sinh ra vẫn phải tuân thủ quy tắc truy cập module khi compiler biên dịch nó.

## 4. Biên dịch processor và ứng dụng bằng javac

Nên biên dịch module annotation trước, sau đó biên dịch processor, cuối cùng mới compile module ứng dụng có sử dụng processor. Thứ tự này làm rõ dependency giữa các module.

Các lệnh sau minh họa trên shell Unix/macOS/Linux với JDK 21. Trên Windows, thay dấu phân cách module path \`:\` bằng \`;\`.

### 4.1. Biên dịch module annotation

~~~bash
mkdir -p build/mods

javac --release 21 \\
  --module-source-path src \\
  -d build/mods \\
  -m com.acme.annotations
~~~

Sau lệnh này, module đã biên dịch nằm trong \`build/mods/com.acme.annotations\`.

### 4.2. Biên dịch module processor

~~~bash
mkdir -p build/processor-mods

javac --release 21 \\
  --module-path build/mods \\
  --module-source-path src \\
  -d build/processor-mods \\
  -m com.acme.processor
~~~

Ở bước này, javac tìm module annotation thông qua \`--module-path\`. Output processor là một exploded module trong \`build/processor-mods/com.acme.processor\`. Có thể đóng gói thư mục module đó thành modular JAR nếu quy trình build yêu cầu.

### 4.3. Biên dịch module ứng dụng và chạy processor

~~~bash
mkdir -p build/app-mods build/generated

javac --release 21 \\
  --module-path build/mods \\
  --processor-module-path build/processor-mods:build/mods \\
  -proc:full \\
  --module-source-path src \\
  -d build/app-mods \\
  -s build/generated \\
  -m com.acme.app
~~~

Ý nghĩa các tùy chọn:

| Tùy chọn | Vai trò |
| --- | --- |
| \`--module-path\` | Tìm các module mà source ứng dụng cần, ở đây có \`com.acme.annotations\`. |
| \`--processor-module-path\` | Tìm các named module cung cấp annotation processor. Đường dẫn ví dụ cũng chứa module annotation mà processor phụ thuộc. |
| \`-proc:full\` | Yêu cầu javac thực hiện annotation processing và compilation. |
| \`--module-source-path\` | Chỉ định gốc source tree chứa các module. |
| \`-d\` | Thư mục output cho class đã biên dịch. |
| \`-s\` | Thư mục output cho source được processor sinh ra. |
| \`-m\` | Chỉ định module cần biên dịch trong source tree. |

Trong lệnh trên, \`build/processor-mods:build/mods\` dùng dấu \`:\` để ghép hai vị trí module trên Unix-like OS. Trên Windows, dùng \`build/processor-mods;build/mods\`.

Khi compilation hoàn tất, có thể xem source được sinh ra trong \`build/generated\` và class đã biên dịch trong \`build/app-mods\`. Với module source path, output thường được phân vùng theo tên module, ví dụ \`build/generated/com.acme.app\` và \`build/app-mods/com.acme.app\`.

\`-s\` chỉ định nơi lưu source sinh ra; \`-d\` chỉ định nơi lưu bytecode. Nếu chỉ nhìn output \`-d\`, có thể bỏ sót bằng chứng processor đã tạo source nào.

## 5. Phân biệt processor module path và processor classpath

Hai cách đăng ký processor không thể thay thế tùy tiện cho nhau.

### 5.1. Processor là named module

Một modular processor JAR có \`module-info.class\` với khai báo:

~~~java
module com.acme.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
            with com.acme.processor.GreetingProcessor;
}
~~~

Đặt modular JAR hoặc exploded module trên:

~~~bash
javac --processor-module-path processors \\
     --module-path app-dependencies \\
     ...
~~~

Javac khám phá processor qua service declaration trong module descriptor. Các module mà processor phụ thuộc cũng phải có thể được resolve từ các module path phù hợp.

### 5.2. Processor chạy trên classpath của compiler

Nếu processor được dùng như thư viện classpath, có thể đăng ký bằng resource:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung:

~~~text
com.acme.processor.GreetingProcessor
~~~

Sau đó dùng:

~~~bash
javac \\
  --processor-path processors.jar \\
  --module-path app-dependencies \\
  -proc:full \\
  ...
~~~

Trong chế độ này, processor được nạp theo cơ chế classpath. Nếu JAR có \`module-info.class\` nhưng lại được đặt trên \`--processor-path\`, đừng giả định javac sẽ dùng chỉ thị \`provides\` của descriptor; hãy cung cấp service resource hoặc chỉ định processor tường minh.

Có thể chọn processor cụ thể bằng:

~~~bash
javac -processor com.acme.processor.GreetingProcessor ...
~~~

Đây là tên lớp đầy đủ của processor, không phải tên module. Cách chọn tường minh hữu ích khi processor path chứa nhiều processor và chỉ một số processor được phép chạy trong compilation đó.

Một modular processor JAR có thể đóng gói cả \`module-info.class\` và \`META-INF/services\` nếu cần hỗ trợ cả hai chế độ. Tuy nhiên, hãy kiểm tra đúng chế độ mà build tool thực sự truyền cho javac.

## 6. Các chế độ annotation processing

Javac cung cấp ba chế độ chính:

- \`-proc:none\`: không chạy annotation processor; compiler chỉ biên dịch source. Dùng khi cần xác định lỗi có liên quan đến processor hay không.
- \`-proc:only\`: chạy annotation processing nhưng không thực hiện compilation thông thường sau đó. Phù hợp với pipeline chỉ muốn sinh source/resource.
- \`-proc:full\`: chạy annotation processing và compilation trong cùng lần gọi.

Khi build modular, nên cấu hình rõ processor path và chế độ processing thay vì phụ thuộc vào việc javac tự quét một classpath rộng. Hành vi tự động phát hiện processor đã thay đổi giữa các phiên bản JDK; cấu hình tường minh giúp build dễ tái lập hơn khi nâng cấp JDK hoặc build tool.

Nếu compilation đột nhiên không sinh source sau khi nâng JDK, hãy kiểm tra compiler arguments thực tế: \`--processor-path\`, \`--processor-module-path\`, \`-processor\` và \`-proc\`. Đừng vội kết luận module descriptor bị hỏng khi processor đơn giản là chưa được kích hoạt.

## 7. Annotation processor và module boundaries

Annotation processing diễn ra trong JVM của compiler. Nó không làm cho processor trở thành dependency runtime của ứng dụng.

Một số ranh giới quan trọng:

1. **Annotation module:** source ứng dụng phải đọc được module chứa annotation. Nếu annotation chỉ có retention SOURCE và không được dùng ở runtime, \`requires static\` thường phù hợp.
2. **Processor module:** processor cần đọc \`java.compiler\` và module annotation mà nó tham chiếu. Consumer không cần \`requires\` processor module.
3. **Generated source:** source được sinh ra thuộc module đang compile theo ngữ cảnh và originating element mà processor cung cấp. Generated code phải tuân thủ \`exports\`, \`requires\` và các quy tắc truy cập thông thường.
4. **Reflection:** processor nên dùng compile-time model API. JPMS không tự động mở package nội bộ của ứng dụng cho processor reflection.
5. **Runtime image:** nếu processor chỉ chạy lúc build, không đưa processor module vào runtime image chỉ vì ứng dụng đã sử dụng nó khi compile. Chỉ annotation module hoặc thư viện liên quan mới cần có mặt runtime nếu bytecode và descriptor ứng dụng thực sự phụ thuộc vào chúng.

Đặc biệt, \`Filer.createSourceFile\` nên nhận originating element:

~~~java
processingEnv.getFiler().createSourceFile(
        "com.acme.app.MainGenerated",
        originatingType
);
~~~

Điều này giúp compiler gắn file được sinh với phần tử nguồn phù hợp. Trong compilation nhiều module, không tạo source bằng cách đoán một package trùng tên rồi bỏ qua module sở hữu nó.

## 8. Dùng annotation processor trong Gradle hoặc Maven

Các build tool có thể cấu hình processor path riêng. Điều cần xác nhận trong dự án modular là compiler cuối cùng nhận đúng loại đường dẫn:

- Classpath processor phải được truyền qua \`--processor-path\` hoặc \`-processorpath\`.
- Modular processor phải được truyền qua \`--processor-module-path\`.
- Các module mà source ứng dụng cần vẫn phải có trên module path.
- Processor module và dependency của nó phải resolve được khi compiler khởi chạy.

Gradle Java plugin thường dùng configuration \`annotationProcessor\` cho processor path dạng classpath. Không nên giả định chỉ cần thêm một modular JAR vào configuration đó là javac sẽ tự dùng \`--processor-module-path\`. Nếu dự án yêu cầu processor module path, cấu hình compiler arguments tương ứng và kiểm tra command line thực tế bằng log build.

Tương tự, với Maven Compiler Plugin, hãy kiểm tra cấu hình annotation processor và compiler arguments mà plugin tạo ra. Tên cấu hình trong build tool không tự quyết định processor đang được nạp như named module hay classpath library.

Giữ processor ở cấu hình dependency dành cho compile. Tránh đưa nó vào runtime dependencies của ứng dụng nếu không có chức năng runtime riêng cần dùng chính thư viện đó.

## 9. Lỗi thường gặp khi modular compilation

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Processor không được gọi | Sai đường dẫn hoặc chưa bật processing | Xem command line; kiểm tra \`--processor-module-path\`, \`--processor-path\`, \`-processor\`, \`-proc\`. |
| Không tìm thấy Processor provider | Module descriptor thiếu \`provides\` hoặc classpath thiếu service file | Kiểm tra \`jar --describe-module\` hoặc \`jar --list\` và nội dung \`META-INF/services\`. |
| \`java.compiler\` không đọc được | Processor module thiếu \`requires java.compiler\` | Bổ sung dependency module trong descriptor của processor. |
| Không resolve được module annotation | Annotation module thiếu trên module path dùng để compile hoặc resolve processor | Kiểm tra \`--module-path\` và \`--processor-module-path\` cùng dependency graph. |
| Annotation không được nhận diện | Sai tên annotation trong \`@SupportedAnnotationTypes\`, package không export hoặc app không đọc module annotation | Kiểm tra tên đầy đủ, \`exports\` và \`requires\` của app. |
| Source được sinh nhưng app không thấy class | Generated source không nằm trong output compilation hoặc không được gắn đúng module | Kiểm tra \`-s\`, \`-d\` và originating elements truyền cho Filer. |
| \`FilerException\` báo file đã tồn tại | Processor tạo cùng qualified name nhiều lần hoặc file đã được tạo từ nguồn khác | Theo dõi tên đã sinh, tránh tạo trùng qua các processing round. |
| Compile chạy được nhưng runtime thiếu module annotation | Descriptor app dùng \`requires\` bắt buộc trong khi annotation chỉ cần ở compile time | Cân nhắc \`requires static\` nếu annotation có SOURCE retention và không cần runtime. |
| Chạy trên JDK này nhưng cảnh báo hoặc không chạy trên JDK khác | Hành vi discovery processor hoặc source version thay đổi | Cấu hình processor path tường minh, chọn \`-proc\` và đặt source version phù hợp. |

## 10. Quy trình chẩn đoán

Khi annotation processor không hoạt động trong modular compilation, kiểm tra theo thứ tự:

1. Xác nhận source module có annotation và module descriptor khai báo đúng dependency.
2. Xác nhận processor module biên dịch được, đọc được \`java.compiler\` và có \`provides javax.annotation.processing.Processor\`.
3. Xem lệnh javac thực tế để biết processor được đặt trên \`--processor-module-path\` hay \`--processor-path\`.
4. Xác nhận processor module cùng các dependency của nó có thể được resolve từ đường dẫn đã cấu hình.
5. Bật rõ annotation processing bằng \`-proc:full\` hoặc chọn processor bằng \`-processor\`.
6. Kiểm tra source được sinh trong thư mục \`-s\`, class được biên dịch trong \`-d\`, và lỗi được ghi qua \`Messager\`.
7. Nếu source sinh ra không được ứng dụng nhìn thấy, kiểm tra originating element và module sở hữu generated source.
8. Cuối cùng, xác nhận runtime application không vô tình phụ thuộc vào processor module chỉ được dùng ở build time.

Tách riêng module annotation, processor và module ứng dụng giúp kiểm soát dependency rõ ràng. Khi cấu hình đúng, javac có thể nạp processor như một named module, xử lý annotation trong các module nguồn và biên dịch source được sinh ra trong cùng modular compilation.
