# Generated sources và module-info

## 1. Mục tiêu

Trong một dự án Java modular, mã nguồn không nhất thiết chỉ đến từ những file được viết trực tiếp. Annotation processor có thể sinh thêm class, interface hoặc resource trong lúc biên dịch. Các build tool cũng có thể tạo source từ schema, metadata, OpenAPI, protobuf hoặc cấu hình.

Khi đưa generated sources vào một named module, cần hiểu rõ ba phần:

- **Nguồn được sinh ra**: file Java nào được tạo, thuộc package và module nào, nằm ở thư mục output nào.
- **Module descriptor**: module-info.java khai báo dependency, package được export/open và service usage/provider như thế nào.
- **Cấu hình compiler**: javac tìm source, processor, module và ghi generated source/class ở đâu.

Generated source được biên dịch như source thông thường trong module đích. Nó không tự sửa module-info.java và cũng không tự thêm các chỉ thị requires, exports, opens, uses hoặc provides. Descriptor vẫn phải mô tả đúng module sau khi các source được sinh ra.

Bài này dùng Java 21 làm mốc cho cú pháp và tùy chọn javac.

## 2. Generated source trong annotation processing

Annotation processing là quá trình compiler gọi các processor để đọc annotation và tạo thêm source, class hoặc resource.

Một processor triển khai **javax.annotation.processing.Processor**. Trong thực tế, thường kế thừa **AbstractProcessor**:

~~~java
@SupportedAnnotationTypes("com.acme.codegen.GenerateDto")
@SupportedSourceVersion(SourceVersion.RELEASE_21)
public final class DtoProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateDto.class)) {
            // Đọc metadata của element và tạo source nếu cần.
        }

        return true;
    }
}
~~~

Để tạo một Java source file, processor sử dụng **Filer.createSourceFile**:

~~~java
JavaFileObject sourceFile =
        processingEnv.getFiler().createSourceFile(
                "com.acme.generated.CustomerDto",
                originatingElement);

try (Writer writer = sourceFile.openWriter()) {
    writer.write("""
            package com.acme.generated;

            public record CustomerDto(String id, String name) {}
            """);
}
~~~

Tên truyền vào createSourceFile là tên nhị phân của type cần tạo. Với package có tên, tên type phải đầy đủ. Có thể truyền originating elements để công cụ build hiểu file được sinh ra từ những phần source nào; thông tin này hữu ích cho incremental compilation.

Một processor không nên ghi đè source do người dùng viết hoặc source đã được tạo trong cùng lượt xử lý. Nếu cùng một đường dẫn được tạo nhiều lần, Filer có thể ném **FilerException**. Processor cần kiểm soát tên file, điều kiện sinh file và các round để không tạo trùng.

### Các vòng xử lý

javac chạy annotation processing theo nhiều round:

1. Compiler phân tích source ban đầu và tìm annotation phù hợp.
2. Processor được gọi với các root elements của round hiện tại.
3. Nếu processor tạo source mới, các source đó được đưa vào round tiếp theo.
4. Các processor có thể xử lý annotation trên những source mới.
5. Quá trình lặp lại cho đến khi không còn source mới được tạo.
6. Processor được gọi thêm một lần cuối để hoàn tất công việc.
7. Nếu không dùng chế độ chỉ xử lý annotation, javac biên dịch source ban đầu cùng các source được tạo.

Vì vậy, source do processor sinh ra trong cùng invocation thường không cần một lệnh javac riêng để biên dịch. Compiler nhận chúng ở các round tiếp theo và đưa vào compilation cuối cùng.

Không nên viết processor sinh một file mới vô điều kiện ở mọi round. Cách đó có thể tạo vòng lặp hoặc lỗi trùng file. Processor cần xác định annotation đầu vào, kiểm tra round cuối bằng **RoundEnvironment.processingOver()** khi thích hợp và chỉ sinh file khi thực sự cần.

## 3. Phân biệt module-info.java với generated source

**module-info.java** là module declaration compilation unit, thường nằm ở root source directory của module:

~~~text
src/
  com.acme.api/
    module-info.java
    com/
      acme/
        api/
          Customer.java
  com.acme.app/
    module-info.java
    com/
      acme/
        app/
          Main.java
~~~

Khi biên dịch, javac tạo **module-info.class** cùng các class khác trong output của module.

Một module descriptor có thể chứa các loại directive sau:

~~~java
module com.acme.app {
    requires com.acme.api;

    exports com.acme.app.api;

    uses com.acme.api.CustomerFactory;
}
~~~

Generated class vẫn thuộc module đang biên dịch. Ví dụ processor tạo **com.acme.generated.CustomerDto** trong module com.acme.app thì class đó nằm trong module com.acme.app sau khi compile. Module system không tạo một module mới chỉ vì source được sinh ra.

Tuy nhiên, sự xuất hiện của package hoặc type mới không tự thay đổi descriptor:

- Nếu module khác cần truy cập public type được sinh ra, package chứa type đó phải được export phù hợp.
- Nếu generated code tham chiếu type trong module khác, module hiện tại phải đọc module đó và module đích phải export package cần thiết.
- Nếu generated code gọi một service qua ServiceLoader, module chứa code sử dụng cần khai báo uses cho service type.
- Nếu module cung cấp service là một provider, descriptor của module provider cần khai báo provides.
- Nếu generated code dùng reflection sâu vào package của module khác, cần xem xét opens phù hợp.

Generated source là nội dung của module; module-info.java vẫn quyết định ranh giới và quan hệ của module.

### Processor có tự sinh module-info.java không?

API **Filer.createSourceFile** tạo source cho type hoặc package-info, không phải một API chuyên dụng để tạo module descriptor. Annotation processor có thể đọc module element và các annotation trên module declaration, nhưng không nên dựa vào processor thông thường để tự viết hoặc sửa module-info.java.

Hãy giữ module-info.java như một source input có chủ đích trong dự án. Nếu build cần tạo descriptor cho một artifact hoặc biến thể đóng gói, thực hiện ở một bước build riêng, có output và thứ tự compile rõ ràng. Không ghi đè module descriptor đang được javac dùng trong cùng lượt xử lý.

## 4. Vị trí generated sources: -s và -d

Hai tùy chọn javac có mục đích khác nhau:

| Tùy chọn | Ý nghĩa |
|---|---|
| -s directory | Thư mục chứa source do annotation processor tạo |
| -d directory | Thư mục chứa class file được biên dịch |

Ví dụ:

~~~text
javac
  -processorpath processors/processor.jar
  -s build/generated/sources
  -d build/classes
  -classpath libs/annotations.jar
  src/com/acme/app/Main.java
~~~

Sau khi chạy:

- Source gốc nằm trong src.
- Generated source được ghi dưới build/generated/sources.
- Class file của source gốc và generated source nằm dưới build/classes.

Với source trong package com.acme.generated, generated file thường có đường dẫn:

~~~text
build/generated/sources/
  com/
    acme/
      generated/
        CustomerDto.java
~~~

Nếu biên dịch nhiều module trong cùng một invocation, source output và class output được tổ chức theo module hierarchy. Ví dụ:

~~~text
build/generated/sources/
  com.acme.api/
    com/acme/api/generated/ApiMetadata.java
  com.acme.app/
    com/acme/app/generated/CustomerDto.java
~~~

Việc tách hai thư mục này giúp IDE, build tool và incremental compiler phân biệt source được quản lý với source do processor sinh ra. Không nên sửa trực tiếp generated file vì lần build tiếp theo có thể tạo lại file và ghi đè thay đổi.

## 5. Cấu hình annotation processor: processor path và module path

Có hai môi trường khác nhau trong quá trình javac chạy:

1. **Compilation environment** chứa source đang biên dịch, dependency modules và classpath/module path của ứng dụng.
2. **Runtime environment của javac** là môi trường mà annotation processor được nạp và thực thi.

Vì vậy, đường dẫn tìm processor không đồng nghĩa với module path của ứng dụng.

### Processor không phải named module

Nếu processor được đóng gói thành JAR thông thường, có thể dùng **--processor-path** hoặc **-processorpath**:

~~~text
javac
  --module-path mods
  --processor-path processors/processor.jar
  -s build/generated
  -d build/classes
  -m com.acme.app
~~~

Nếu cần chỉ rõ processor class, dùng **-processor**:

~~~text
-processor com.acme.processor.DtoProcessor
~~~

### Processor là named module

Nếu processor được đóng gói thành named module, dùng **--processor-module-path**:

~~~text
javac
  --module-path mods
  --processor-module-path processor-modules
  -s build/generated
  -d build/classes
  -m com.acme.app
~~~

Module descriptor của processor cần công khai processor qua service provider declaration:

~~~java
module com.acme.dto.processor {
    requires java.compiler;

    provides javax.annotation.processing.Processor
        with com.acme.processor.DtoProcessor;
}
~~~

Processor module thường cần **requires java.compiler** để truy cập API annotation processing và language model.

Không đặt processor JAR vào --module-path của ứng dụng chỉ để javac tìm processor. Hãy cấu hình processor path riêng. Ngược lại, dependency mà source ứng dụng tham chiếu phải nằm trên classpath hoặc module path phù hợp với cách ứng dụng được biên dịch.

### Tắt hoặc giới hạn annotation processing

Các chế độ chính:

- **-proc:none**: không chạy annotation processor; compiler chỉ biên dịch source.
- **-proc:only**: chỉ chạy annotation processing, không thực hiện compilation cuối cùng.
- **-proc:full**: thực hiện annotation processing và compilation.

Khi cần xem processor có tạo đúng file hay không mà chưa muốn kiểm tra class output, -proc:only có thể hữu ích. Tuy nhiên, vì không có bước compile cuối, lệnh thành công không chứng minh generated source hợp lệ về mặt Java hoặc module access. Cần có bước compile riêng để xác nhận.

Từ JDK 21, có thể truyền cấu hình riêng cho processor bằng **-Akey=value**. Ví dụ:

~~~text
-Acom.acme.dto.package=com.acme.app.generated
~~~

Processor tự định nghĩa và đọc option này qua **ProcessingEnvironment.getOptions()**. javac không tự hiểu ý nghĩa của key.

## 6. Biên dịch nhiều module với --module-source-path

Khi biên dịch nhiều named modules trong cùng một invocation, dùng **--module-source-path** để chỉ nơi chứa source của từng module.

Ví dụ cấu trúc:

~~~text
src/
  com.acme.api/
    module-info.java
    com/acme/api/Customer.java
  com.acme.app/
    module-info.java
    com/acme/app/Main.java
~~~

Module com.acme.app:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Lệnh biên dịch:

~~~text
javac
  --module-source-path "src/*"
  --module-path mods
  --processor-path processors/processor.jar
  -s build/generated
  -d build/classes
  -m com.acme.api,com.acme.app
~~~

Ở đây:

- **src/** là module source hierarchy.
- **src/com.acme.api/** là source root của module com.acme.api.
- **src/com.acme.app/** là source root của module com.acme.app.
- **-m** chọn các module được biên dịch.
- **-s** đặt generated source vào output hierarchy theo module.
- **-d** đặt class file vào output hierarchy theo module.

Nếu chỉ biên dịch một module, có thể dùng source path tương ứng. Khi biên dịch nhiều module, javac yêu cầu module source path để xác định module ownership và tổ chức output.

### Generated source cần thuộc module nào?

Khi processor đang xử lý nhiều module, compiler phải xác định generated type thuộc module đích nào. Có thể chỉ rõ module trong tên file đưa cho Filer bằng cú pháp:

~~~java
filer.createSourceFile(
        "com.acme.app/com.acme.app.generated.CustomerDto",
        originatingElement);
~~~

Phần trước dấu slash là module name; phần sau là tên type. Cách này hữu ích khi processor có thể sinh source cho nhiều module trong cùng một compilation.

Nếu không chỉ rõ module, javac có thể suy luận module từ compilation context và originating elements. Khi không thể suy luận, **--default-module-for-created-files** cho phép chỉ định module mặc định cho các file do processor tạo:

~~~text
--default-module-for-created-files com.acme.app
~~~

Đây là fallback cho generated files chưa có module prefix và không xác định được module đích. Không nên đặt mặc định tùy tiện khi processor phục vụ nhiều module, vì source có thể bị gán vào sai module. Ưu tiên module prefix hoặc originating elements chính xác khi có thể.

Một source file trong named module phải thuộc một package có tên. Tạo type trong unnamed package của named module không được hỗ trợ.

## 7. Module descriptor và generated code

Giả sử processor sinh class:

~~~java
package com.acme.app.generated;

public final class CustomerRegistry {
    public static int size() {
        return 0;
    }
}
~~~

Class này thuộc module đang được compiler gán cho generated source. Nếu chỉ module hiện tại sử dụng class, package không nhất thiết phải export.

Nếu một module khác cần truy cập class public, module descriptor phải có:

~~~java
module com.acme.app {
    exports com.acme.app.generated;
}
~~~

Chỉ thị exports không tự sinh từ package xuất hiện sau annotation processing. Nếu generated API là một phần của public contract, hãy khai báo package đó rõ ràng trong module-info.java.

### Generated code tham chiếu module khác

Ví dụ processor tạo source có dòng:

~~~java
import com.acme.api.Customer;
~~~

Nếu Customer nằm trong named module com.acme.api, module đích của generated source phải đọc com.acme.api:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Processor path không tự tạo readability cho module đang compile. Nếu source sinh ra tham chiếu API trong module khác, module đích vẫn cần dependency module tương ứng.

Nếu annotation chỉ cần trong quá trình compile và không cần ở runtime, có thể cân nhắc **requires static**:

~~~java
module com.acme.app {
    requires static com.acme.annotations;
}
~~~

Chỉ dùng requires static khi dependency thực sự chỉ cần ở compile time hoặc khi có thể thiếu ở runtime theo thiết kế. Nếu generated bytecode cần type của module đó khi chạy, dependency runtime vẫn phải được đảm bảo.

## 8. Annotation trên module-info.java

Module declaration cũng có thể mang annotation có target MODULE:

~~~java
@Target(ElementType.MODULE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateModuleRegistry {
}
~~~

Sử dụng annotation trong module-info.java:

~~~java
@GenerateModuleRegistry
module com.acme.app {
    requires com.acme.api;
}
~~~

Processor có thể nhận module element trong root elements và đọc annotation trên module declaration. Từ metadata đó, processor có thể sinh các class hỗ trợ trong module.

Ví dụ, processor có thể tạo:

~~~java
package com.acme.app.generated;

public final class ModuleRegistry {
    private ModuleRegistry() {}

    public static String moduleName() {
        return "com.acme.app";
    }
}
~~~

Điều này không có nghĩa processor tự sửa module-info.java. Module descriptor ban đầu vẫn là source input; processor chỉ sinh source bổ sung theo thông tin nó đọc được.

Khi xử lý annotation trên module, cần chú ý module element là một root element riêng. Processor không nên giả định rằng module element tự động bao gồm toàn bộ package và type như một element cha thông thường. Hãy dùng language model API để truy vấn module, package và type đúng cách.

## 9. Generated sources với Maven và Gradle

Build tool thường cấu hình annotation processing thay cho việc gọi javac trực tiếp.

### Maven

Maven Compiler Plugin có thể cấu hình processor path riêng và generated source output. Ví dụ cấu hình khái niệm:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <generatedSourcesDirectory>
      target/generated-sources/annotations
    </generatedSourcesDirectory>
    <annotationProcessorPaths>
      <path>
        <groupId>com.acme</groupId>
        <artifactId>dto-processor</artifactId>
        <version>1.0.0</version>
      </path>
    </annotationProcessorPaths>
  </configuration>
</plugin>
~~~

Với dự án modular, module-info.java vẫn nằm trong source set của module. Processor được cấu hình riêng trong compiler plugin. Cấu hình chính xác phụ thuộc phiên bản Maven Compiler Plugin và cách project khai báo dependency.

### Gradle

Gradle Java plugin phân biệt annotation processor dependency bằng configuration **annotationProcessor**:

~~~groovy
dependencies {
    implementation(project(":codec-api"))
    annotationProcessor("com.acme:dto-processor:1.0.0")
}
~~~

Nếu processor được sử dụng trong test source set, có thể cần cấu hình annotationProcessor tương ứng cho test.

Generated source output thường nằm trong thư mục build do Gradle quản lý. Không thêm generated source directory vào source set hai lần nếu plugin đã tự đăng ký output. Cũng không khai báo processor như implementation runtime dependency chỉ vì compiler cần chạy processor.

### Quy tắc tổ chức output

- Để generated source dưới build directory hoặc thư mục output do build tool quản lý.
- Không sửa trực tiếp file đã sinh.
- Không commit generated source trừ khi dự án có quy ước rõ ràng yêu cầu làm vậy.
- Đảm bảo clean build có thể tạo lại đầy đủ source.
- Đảm bảo module descriptor được đưa vào đúng source set và compile cùng module.
- Giữ processor dependency trong cấu hình annotation processor riêng khi build tool hỗ trợ.

## 10. Lỗi thường gặp và cách xử lý

### Generated source nằm sai module

Nguyên nhân có thể là processor không chỉ rõ module prefix hoặc compiler không suy luận được module đích.

Cách xử lý:

- Truyền originating elements phù hợp cho Filer.
- Dùng module-qualified name dạng module/name khi processor biết chính xác target module.
- Chỉ định --default-module-for-created-files khi có một module mặc định hợp lý.
- Kiểm tra đường dẫn generated source dưới -s.

### Package generated không được export

Generated class có public modifier nhưng module khác vẫn không truy cập được. Public trong Java language không tự vượt qua ranh giới module.

Cách xử lý: thêm exports cho package cần công khai trong module-info.java. Nếu chỉ code nội bộ của module sử dụng, không cần export package đó.

### Processor không được tìm thấy

Nguyên nhân thường là đặt processor trên --module-path thay vì --processor-path hoặc --processor-module-path, thiếu service registration, hoặc cấu hình build tool chưa đúng.

Cách xử lý:

- Processor dạng classpath JAR: kiểm tra --processor-path.
- Processor dạng named module: kiểm tra --processor-module-path và provides javax.annotation.processing.Processor.
- Dùng -processor khi cần chọn processor class rõ ràng.
- Kiểm tra log compiler và phiên bản JDK đang chạy.

### Generated source tham chiếu dependency chưa được requires

Processor path không tự tạo readability cho module đang compile. Nếu source sinh ra tham chiếu API trong module khác, module đích vẫn cần dependency module tương ứng.

Cách xử lý: khai báo requires hoặc requires static phù hợp trong module-info.java, rồi kiểm tra dependency trên module path.

### Source được tạo nhưng không compile

Có thể compiler đang chạy -proc:only, source output không được đưa vào compilation sau đó, hoặc generated code có lỗi Java/module access.

Cách xử lý: xác nhận chế độ -proc, kiểm tra generated file trong -s, sau đó compile source đó trong cùng module với module descriptor và dependency đúng.

### Processor tạo trùng source qua nhiều round

Filer không cho phép cùng một source file được tạo nhiều lần trong cùng compilation. Processor phải tránh tạo lại cùng tên ở round sau và không sinh source vô điều kiện.

Cách xử lý: chỉ sinh source khi phát hiện input phù hợp, theo dõi các type đã tạo trong lượt xử lý và xử lý round cuối đúng cách.

## 11. Quy trình kiểm tra một dự án modular có generated source

1. Xác định module source root và vị trí module-info.java.
2. Tìm annotation processor và xác định processor là classpath JAR hay named module.
3. Xác định processor dependency được cấu hình riêng khỏi dependency của ứng dụng.
4. Chạy compile với thư mục generated source riêng bằng -s.
5. Với nhiều module, dùng --module-source-path và kiểm tra module hierarchy trong generated output.
6. Nếu processor tạo source cho nhiều module, xác định cách Filer gán target module.
7. Kiểm tra generated source tham chiếu module nào và module descriptor có requires phù hợp không.
8. Kiểm tra package generated có cần export hoặc open không.
9. Kiểm tra service usage/provider có cần uses/provides rõ ràng trong descriptor không.
10. Chạy clean build để chứng minh generated source có thể tái tạo.
11. Chạy test trên module path để xác nhận module descriptor và generated classes hoạt động cùng nhau.

## 12. Checklist khi review generated sources và module-info

- module-info.java có nằm ở root source của đúng module không?
- Generated source có được ghi vào thư mục output riêng không?
- -s và -d có đang bị nhầm mục đích không?
- Processor có nằm trên đúng processor path không?
- Processor dependency có bị đưa nhầm vào runtime dependency của ứng dụng không?
- Nếu compile nhiều module, đã dùng --module-source-path chưa?
- Generated source đã được gán đúng module chưa?
- Có cần module prefix hoặc --default-module-for-created-files không?
- Các dependency được generated source tham chiếu đã có requires phù hợp chưa?
- Package generated có cần export hoặc open cho module khác không?
- Service usage/provider có được khai báo bằng uses/provides khi cần không?
- Clean build có tái tạo được source và class output không?
- Build có vô tình compile generated source hai lần không?
- Có đang cố để annotation processor tự sửa module-info.java không?

**Ghi nhớ:** Generated source là source code thuộc một module đã được xác định trong compilation. Processor tạo type và resource; module-info.java định nghĩa dependency và ranh giới của module. Hãy quản lý hai phần này như hai đầu vào có quan hệ rõ ràng: generated code phải được gán đúng module và descriptor phải khai báo đúng những gì code đó cần.

## Tài liệu tham khảo

- Oracle Java SE 21 — The javac Command, mục Annotation Processing, -s, --module-source-path, --processor-path và --processor-module-path: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- Oracle Java SE 21 API — Filer: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Filer.html
- Oracle Java SE 21 API — Processor: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Oracle Java SE 21 API — RoundEnvironment: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Java Language Specification, Java SE 21 — Module Declarations: https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html
