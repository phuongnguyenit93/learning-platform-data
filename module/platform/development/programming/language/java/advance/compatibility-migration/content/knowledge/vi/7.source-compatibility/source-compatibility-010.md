# Mã được sinh tự động và giả định về cú pháp hoặc cấu trúc AST

Trong một dự án Java, không phải mọi file `.java` đều được viết bằng tay. Nhiều file được tạo bởi annotation processor, plugin build, công cụ đọc OpenAPI/schema, công cụ mapping, ORM metamodel, template engine hoặc trình biến đổi cây cú pháp (AST). Chúng là một phần của quá trình biên dịch và có thể quyết định ứng dụng có còn tương thích khi nâng Java hay không.

Khi JDK hoặc framework đổi phiên bản, mã nghiệp vụ có thể vẫn hợp lệ nhưng **generator không hiểu cú pháp mới**, **processor phụ thuộc vào nội bộ compiler bị lỗi**, hoặc **mã sinh ra tham chiếu API không có ở runtime đích**. Một số lỗi xuất hiện ngay khi build; một số khác nguy hiểm hơn vì generated code vẫn biên dịch nhưng sai mapping, thiếu trường dữ liệu hoặc thay đổi hành vi.

Bài này tập trung vào cách các công cụ sinh mã phụ thuộc vào cú pháp Java và cấu trúc AST, vì sao các giả định đó có thể bị phá vỡ trong Java Compatibility Migration, và cách xác minh đầu vào, mã sinh ra, compiler và hành vi thực tế.

## 1. Generated source nằm ở đâu trong build?

Một luồng build điển hình có thể gồm:

~~~text
Java source viết tay             Schema, OpenAPI, .proto, template
         |                                    |
         |                                    v
         |                           Generator task
         |                                    |
         |                            Generated .java
         |                                    |
         +-------------------+----------------+
                             |
                             v
                         Java compiler
                             |
                       Annotation processor
                             |
                   Generated source/resource
                             |
                       Vòng compile tiếp theo
                             |
                         Bytecode .class
                             |
                       Đóng gói artifact
                             |
                         JVM/runtime
~~~

Không phải dự án nào cũng có đủ các giai đoạn này và thứ tự còn tùy tool. Có công cụ chạy hoàn toàn trước compiler; có annotation processor chạy trong nhiều vòng xử lý; có công cụ thay đổi AST ngay khi `javac` đang phân tích mã; có công cụ thao tác trực tiếp trên bytecode sau biên dịch.

| Nhóm công cụ | Nguồn đầu vào | Kết quả | Rủi ro tương thích |
|---|---|---|---|
| OpenAPI, protobuf, schema generator | Contract, schema | DTO, client, stub | Cú pháp/API output vượt target |
| Annotation processor | Annotation và symbol model | Source, resource | Processor không chạy hoặc không hiểu type mới |
| Mapper generator | Model và mapping config | Mapper implementation | Sai getter, constructor, record component |
| ORM metamodel, QueryDSL | Entity, annotation | Type-safe query classes | Namespace annotation, type model thay đổi |
| Template/code scaffolding | Template, metadata | Java source | Hard-code import, tên package, API |
| Source parser/analyzer | Java source | AST và báo cáo | Grammar mới không được parse |
| AST transformer | AST/compiler API | Source/AST thay đổi | Node shape và compiler internals thay đổi |
| Bytecode generator | Class file hoặc metadata | Class/bytecode | Không hiểu class-file version mới |

Muốn chẩn đoán migration, trước tiên phải biết file được tạo từ đâu, vào giai đoạn nào và công cụ nào sở hữu nó. Sửa tay file generated thường không bền vì nó sẽ bị ghi đè trong lần sinh mã tiếp theo.

## 2. Các giả định ẩn trong công cụ sinh mã

Generator thường mang những giả định kỹ thuật không được khai báo rõ:

- Mọi model đều là `class` thông thường, có field, getter `getX()` và setter `setX(...)`.
- Có thể tạo đối tượng bằng constructor rỗng, sau đó gán từng thuộc tính.
- Annotation luôn nằm trên field hoặc method với vị trí cố định.
- Mọi `switch` đều là statement có `case` và `break` như Java cũ.
- Danh sách AST node type của parser không thay đổi qua các release.
- Tên kiểu trong source có thể xác định bằng so sánh chuỗi, không cần symbol resolution.
- Thứ tự field, method và constructor trong AST phản ánh đúng ý nghĩa nghiệp vụ.
- `com.sun.tools.javac.*` có cùng class/field/method ở JDK mới.
- JDK build mới có thể dùng để sinh mọi cú pháp và API cho target Java cũ.
- Annotation processor sẽ luôn được tự phát hiện và chạy mặc định.

Khi Java bổ sung cú pháp hoặc framework chuyển cách biểu diễn model, những giả định này có thể trở nên sai. Hai tình huống cần phân biệt:

1. **Lỗi rõ ràng:** Parser ném exception, processor bị lỗi, generated code không compile.
2. **Lỗi âm thầm:** Generator bỏ sót field hoặc node không nhận ra, sinh code vẫn compile nhưng hành vi hoặc dữ liệu sai.

Trong migration, cần kiểm tra cả hai. Kết quả generator chạy thành công chỉ chứng minh nó đã tạo output theo logic hiện có, không chứng minh output phản ánh chính xác source đầu vào.

## 3. Cú pháp Java mới có thể thay đổi cấu trúc AST

AST (Abstract Syntax Tree) là cấu trúc cây biểu diễn các thành phần cú pháp: type declaration, method, expression, statement, annotation, pattern và các node khác.

Ví dụ:

~~~java
int total = price * quantity;
~~~

Có thể được biểu diễn khái niệm như:

~~~text
VariableDeclaration: total
├── Type: int
└── MultiplyExpression
    ├── Identifier: price
    └── Identifier: quantity
~~~

Hình dạng AST cụ thể phụ thuộc parser, compiler version và giai đoạn xử lý (parse, symbol attribution, lowering). Không có bảo đảm mọi thư viện dùng cùng loại node hoặc cùng quan hệ cha-con.

### 3.1. Record khác JavaBean thông thường

~~~java
public record Customer(String id, String email) {
}
~~~

Record có component và accessor mặc định `id()`, `email()`; nó không tự có `getId()`, `getEmail()` hoặc setter. Generator dựa vào JavaBean có thể bỏ sót những property này.

Một analyzer dựa trên parser bên ngoài có thể viết:

~~~java
unit.findAll(ClassOrInterfaceDeclaration.class)
    .forEach(this::collectProperties);
~~~

Tùy thư viện AST, record có loại node riêng, chẳng hạn `RecordDeclaration`. Analyzer chỉ tìm `ClassOrInterfaceDeclaration` có thể hoàn toàn bỏ qua record, dù parser đã phân tích file thành công.

Cách sửa cần xuất phát từ hợp đồng generator: record có được hỗ trợ hay không, lấy component nào, có cho phép tạo immutable output và dùng constructor nào. Chỉ đổi một phép cast không giải quyết được khác biệt về model.

### 3.2. Sealed type thay đổi giả định về kế thừa

~~~java
public sealed interface PaymentResult
        permits Approved, Rejected {
}

public record Approved(String receiptId) implements PaymentResult {
}

public record Rejected(String reason) implements PaymentResult {
}
~~~

Generator tạo serializer, mapper hoặc visitor phải hiểu type hierarchy và những subtype được cho phép. Nếu nó chỉ hỗ trợ `class extends class`, nó có thể bỏ qua các record implements interface. Nếu generator xem mọi subtype như class có constructor rỗng, output cũng có thể sai.

Thông tin `permits` hữu ích nhưng không thay thế việc phân tích type model và kiểu runtime. Generator phải xác định rõ có hỗ trợ sealed hierarchy và những trường hợp subtype nào.

### 3.3. Switch expression và pattern matching

~~~java
static String describe(Object value) {
    return switch (value) {
        case Integer n -> "number: " + n;
        case String s -> "text: " + s;
        case null -> "null";
        default -> "other";
    };
}
~~~

Một parser chỉ biết `switch` statement và `case` hằng số có thể báo lỗi khi gặp pattern case hoặc arrow rule. Một rewriter có thể parse được nhưng sinh lại code với cấu trúc sai, bỏ mất `yield` hoặc hiểu sai phạm vi biến pattern.

Cần kiểm tra khả năng xử lý cú pháp theo source level, không suy ra rằng hỗ trợ Java 17 tức tự động hỗ trợ mọi tính năng Java mới.

### 3.4. Text block và xử lý chuỗi

~~~java
String payload = """
    {
      "kind": "record",
      "example": "class Customer {}"
    }
    """;
~~~

Các từ `class`, `record` và dấu ngoặc trong text block không phải cấu trúc Java. Công cụ dùng regex để tách class, method hay đếm ngoặc có thể nhầm nội dung chuỗi thành source code. Generic lồng nhau, annotation nhiều dòng, comment và Unicode escape cũng gây lỗi tương tự.

Nếu công cụ cần hiểu cấu trúc chương trình, hãy dùng parser hỗ trợ grammar tương ứng. Regex phù hợp cho biến đổi văn bản đơn giản với giới hạn rõ, không thể thay thế parser Java đầy đủ.

## 4. Những giả định AST dễ bị phá vỡ khi nâng JDK

Ngoài cú pháp mới, cấu trúc AST có thể khác giữa các phiên bản compiler và các thư viện parser.

| Giả định | Vì sao có thể sai | Hệ quả |
|---|---|---|
| Chỉ có class/interface/enum declaration | Java bổ sung record và construct mới | Bỏ sót model |
| Mỗi field là một property | Record component, annotation và computed property | Mapping thiếu trường |
| Constructor luôn có dạng cũ | Record canonical constructor, compact constructor | Sinh lời gọi constructor sai |
| Mọi switch node đều cùng cấu trúc | Switch expression, pattern cases | Rewrite sai control flow |
| Tên kiểu trong source đủ để xác định type | Import, generic, nested type, overload | Chọn sai kiểu hoặc method |
| AST node luôn nằm cùng vị trí | Parser/compiler thay đổi biểu diễn | Visitor truy cập sai |
| Compiler internal API ổn định | JDK thay class/field hoặc quyền truy cập | Linkage/access error |

Cũng cần phân biệt AST trước và sau type attribution: cùng cú pháp `List<String>`, biểu diễn ký hiệu sau resolution có thể chứa `java.util.List<java.lang.String>`. Công cụ chỉ so sánh tên đơn giản có nguy cơ nhận nhầm class trùng tên, generic type hoặc overload.

Khi cần đánh giá quan hệ kiểu, nên sử dụng type/symbol model thay vì suy luận từ chuỗi source nếu API công cụ cho phép.

## 5. Public annotation processing API và compiler internals

Java cung cấp các API để viết annotation processor:

- `javax.annotation.processing`: processor, round, Filer, Messager.
- `javax.lang.model.element`: type, package, method, field và các element.
- `javax.lang.model.type`: TypeMirror và quan hệ kiểu.
- `javax.lang.model.util`: utilities cho elements/types.
- `javax.tools`: đối tượng file và công cụ compiler.
- `com.sun.source.tree`, `com.sun.source.util`: API cây source dành cho mục đích phân tích khi môi trường phù hợp.

Processor chuẩn thường có thể tạo source qua `Filer` và kiểm tra kiểu qua `Elements`/`Types` mà không cần chỉnh cây nội bộ của javac.

Một số công cụ khác, nhất là công cụ biến đổi AST ở compile time, truy cập vào `com.sun.tools.javac.tree.JCTree` hoặc các class nội bộ khác. Những API này không phải giao diện ổn định cho mã ứng dụng. Nâng JDK có thể dẫn tới:

- `NoSuchFieldError` hoặc `NoSuchMethodError` do nội bộ compiler đổi.
- `IllegalAccessError` hay `InaccessibleObjectException` vì ranh giới module.
- `ClassCastException` khi AST node không còn dạng công cụ dự đoán.
- Lỗi chỉ xảy ra khi processor/plugin được nạp, dù source Java hợp lệ.

Một số hệ thống dùng `--add-exports` hoặc `--add-opens` để giải quyết quyền truy cập trong ngắn hạn. Biện pháp này không sửa AST model đã thay đổi, không bảo đảm field/method nội bộ còn tồn tại và có thể làm quy trình build phụ thuộc thêm vào JVM flags khó bảo trì. Nên ưu tiên nâng phiên bản tool tương thích JDK hoặc chuyển sang API được hỗ trợ khi có thể.

## 6. Annotation processor và các vòng sinh mã

Annotation processor được compiler gọi qua những processing round. Processor có thể đọc annotation, tạo file source và để compiler phân tích file mới trong những round tiếp theo.

Ví dụ annotation đầu vào:

~~~java
package example;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
~~~

Một processor có thể nhận annotation trên class `Customer` rồi phát ra `CustomerGenerated.java`. Ví dụ rút gọn:

~~~java
@SupportedAnnotationTypes("example.AutoGreeting")
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(AutoGreeting.class)) {
            if (!(element instanceof TypeElement type)) {
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String name = type.getSimpleName() + "Generated";
            String qualified = packageName.isEmpty()
                    ? name : packageName + "." + name;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualified, type);

                try (Writer out = source.openWriter()) {
                    if (!packageName.isEmpty()) {
                        out.write("package " + packageName + ";\n");
                    }
                    out.write("public final class " + name + " {\n");
                    out.write("  public static String message() {\n");
                    out.write("    return \"Hello\";\n");
                    out.write("  }\n");
                    out.write("}\n");
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot generate: " + error,
                    element
                );
            }
        }
        return false;
    }
}
~~~

Để dùng ví dụ, cần các import tương ứng từ `java.io`, `java.util`, `javax.annotation.processing`, `javax.lang.model`, `javax.tools` và đăng ký processor qua cơ chế plugin/service provider phù hợp. Ví dụ được rút gọn để tập trung vào cách sinh mã; chính implementation processor cũng phải được biên dịch bằng source level mà compiler JDK chạy processor hỗ trợ.

Khi migration cần quan sát:

- Processor có được khai báo và kích hoạt thực sự hay không.
- Annotation và element kind có được nhận đúng không.
- Processor có hỗ trợ source level mới không.
- Processor có tạo lại cùng file trong nhiều round dẫn đến `FilerException` không.
- File generated có được compile ở đúng target release không.
- Lỗi được báo qua `Messager` hay bị nuốt để build tiếp tục với output thiếu.
- Có file generated cũ còn sót sau khi processor không chạy không.

Không nên coi việc không có lỗi biên dịch là bằng chứng processor đã chạy: nếu ứng dụng không tham chiếu ngay tới generated class, thiếu output có thể chỉ xuất hiện ở bước khác.

## 7. Ví dụ mapper: từ JavaBean sang record

Một model cũ:

~~~java
public final class OrderDto {
    private String code;

    public OrderDto() {}

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
~~~

Generator mapper có thể sinh:

~~~java
public OrderEntity map(OrderDto source) {
    OrderEntity result = new OrderEntity();
    result.setCode(source.getCode());
    return result;
}
~~~

Sau migration, DTO được đổi sang record:

~~~java
public record OrderDto(String code) {
}
~~~

Accessor giờ là `code()`. Record không có setter mặc định hoặc constructor không tham số. Nếu generator vẫn gọi `getCode()`, generated code sẽ lỗi compile. Nếu generator âm thầm bỏ qua property mà nó không nhận ra, code có thể compile và chạy nhưng dữ liệu `code` không được ánh xạ.

Các khác biệt khác cần kiểm tra gồm constructor selection, builder, null value, nested object, generic collection, annotation trên record component và giá trị mặc định. Không chỉ cần processor hỗ trợ cú pháp record; nó phải hỗ trợ semantics của kiểu dữ liệu bất biến.

Với generator dùng annotation trên field/method, hãy kiểm tra vị trí annotation mà công cụ thực sự đọc. Một annotation áp dụng cho record component không mặc nhiên được mọi thư viện diễn giải như annotation gắn trên JavaBean getter cũ.

## 8. Generated source có thể vượt Java target

Một công cụ template có thể sinh:

~~~java
import java.util.List;

public final class ProductCatalog {
    public static List<String> names() {
        return List.of("A", "B");
    }
}
~~~

Nếu ứng dụng cần chạy trên Java 8, `List.of` không tồn tại trong API Java 8. Generator chạy trên JDK 21 có thể phát file bình thường; biên dịch bằng JDK 21 với chỉ `-source 8 -target 8` vẫn có khả năng nhìn thấy API mới. Khi chạy trên Java 8, lời gọi có thể gặp `NoSuchMethodError`.

Cấu hình `javac --release 8` hoặc `options.release = 8` trong Gradle giúp giới hạn Java SE API và phát hiện lời gọi sai ngay ở compile time.

Ngược lại, nếu template sinh `record` trong khi source target là Java 11, generated Java sẽ không hợp lệ với source level đó. Do vậy, generator nên có output target rõ ràng, tách biệt với JDK dùng để chạy chính generator.

## 9. Migration javax sang jakarta trong mã sinh

Khi chuyển framework sang các phiên bản sử dụng Jakarta namespace, source viết tay có thể được đổi từ `javax.persistence.*` sang `jakarta.persistence.*`. Tuy nhiên, một generator cũ vẫn có thể sinh import theo namespace cũ:

~~~java
import javax.persistence.Entity;
import javax.persistence.Id;
~~~

Nếu compile classpath mới chỉ có Jakarta dependency, generated source không biên dịch. Nếu cả hai namespace cùng hiện diện, generated code có thể compile nhưng framework runtime không nhận annotation như mong đợi.

Cần kiểm tra bốn điểm tách biệt: annotation của model đầu vào, phiên bản generator, namespace/API mà generator phát ra và framework/runtime sẽ tiêu thụ output. Tương tự, annotation `javax.annotation.Generated` hay `jakarta.annotation.Generated` chỉ hợp lệ nếu dependency tương ứng nằm trên classpath.

Một cuộc migration hoàn tất ở `src/main/java` chưa chắc đã hoàn tất ở generated sources. Hãy kiểm tra cả thư mục build output.

## 10. Tổ chức generated source trong Gradle và Maven

Đường dẫn nên phân biệt source viết tay với output do build sở hữu:

~~~text
project/
├── src/main/java/                 # Source viết tay
├── src/main/resources/
├── build/generated/sources/       # Output generator
└── build/classes/java/main/       # Bytecode
~~~

Với Gradle Java plugin, annotation processor thường có dependency riêng:

~~~groovy
dependencies {
    implementation project(':annotations')
    annotationProcessor project(':processors')
}
~~~

Khi build chạy bằng JDK mới mà output vẫn phải phù hợp Java 17, có thể dùng:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong cấu hình này, compiler JDK 21 dùng API và ngôn ngữ Java 17 để biên dịch generated source. Processor/plugin vẫn cần tương thích với JDK chạy nó.

Nếu generator là task độc lập, phải khai báo input/output và quan hệ task dependency rõ ràng để compile không chạy trước khi source được tạo. Không chỉ thêm đường dẫn output như một chuỗi tùy ý rồi trông chờ task chạy đúng thứ tự.

Với Maven, generator có thể chạy ở phase `generate-sources`; annotation processor được khai báo qua cấu hình compiler plugin/processor path phù hợp version. Cần kiểm tra source root, phiên bản plugin, `release`, đường dẫn processor và runtime dependency. Không dựa hoàn toàn vào cơ chế auto-discovery processor vì behavior phụ thuộc JDK và compiler plugin.

## 11. Stale output và incremental build

Một nguồn sai lệch khác là file generated được giữ lại qua các lượt build:

- Generator mới không chạy, nhưng class/file generated cũ vẫn còn trong build folder.
- Annotation hoặc schema đã đổi nhưng cache không nhận thấy input thay đổi.
- Class mới đã đổi tên, class cũ vẫn bị đóng gói.
- CI chạy clean còn local dùng incremental build cho kết quả khác.
- Processor không được thiết kế cho incremental annotation processing nhưng build giả định nó có thể cache.

Trong đợt khảo sát migration, nên chạy một clean build có kiểm soát, lưu generated output và đối chiếu các lần chạy trên cùng input. Nếu output chỉ tồn tại nhờ cache cũ, đó không phải bằng chứng generator mới hoạt động.

Generated source phải được chỉnh ở source of truth như annotation, schema, template hoặc processor. Sửa file generated trực tiếp để che lỗi thường sẽ mất khi build lại.

## 12. Phân loại lỗi theo giai đoạn

| Giai đoạn | Biểu hiện | Cần điều tra |
|---|---|---|
| Generator task | Plugin không nạp hoặc ném exception | JDK, plugin version, dependency |
| Parse source | Unexpected token, không hiểu record/switch | Grammar, parser version, source level |
| AST traversal | Visitor bỏ sót node, ClassCastException | Node types, version parser, type model |
| Annotation processing | Không tạo source, FilerException | Processor path, round, Filer usage |
| Compile generated file | Cannot find symbol, API thiếu | Template, import, `--release`, classpath |
| Runtime/linkage | UnsupportedClassVersionError, NoSuchMethodError | Bytecode, JVM target, runtime classpath |
| Business behavior | Trường mapping thiếu, serialization sai | Semantics generator, integration tests |

Một stack trace trỏ tới `com.sun.tools.javac.*` từ processor thường là dấu hiệu phụ thuộc compiler internals. Trong khi đó, lỗi `cannot find symbol` trong generated file thường cần quay lại template hoặc processor đã phát ra file, chứ không nên thêm import thủ công.

Nếu generated code compile nhưng mapper bỏ qua một field, cần kiểm tra dữ liệu đầu ra bằng test hành vi; compiler không thể biết yêu cầu nghiệp vụ của field đó.

## 13. So sánh output trước và sau migration

Diff generated source là bằng chứng hữu ích, đặc biệt khi build sau migration vẫn xanh.

Có thể theo dõi:

- Public class, method, field, constructor.
- Getter, setter, record accessor và builder.
- Import và annotation namespace.
- Nullability, default value, thứ tự xử lý.
- Tên JSON/XML field, date/time format.
- Generated mapper branches và điều kiện.
- Dependency runtime của generated client/stub.
- Class-file version sau compile.

Không phải mọi diff đều làm thay đổi hành vi. Format, tên biến cục bộ hay comment có thể thay đổi mà không gây lỗi. Cần phân biệt diff hình thức với diff API và semantics.

Một quy trình đối chiếu đơn giản:

1. Lưu input schema/source, JDK, compiler flags, plugin versions và generated output cũ.
2. Xóa output build cũ rồi sinh lại từ chính input đó.
3. Nâng JDK hoặc generator theo kế hoạch.
4. Sinh lại output với cùng input nếu có thể.
5. So sánh cấu trúc, API và dữ liệu được ánh xạ.
6. Compile generated code bằng target release.
7. Chạy kiểm thử chức năng ở những luồng dùng generated code.

Nếu vừa đổi schema vừa nâng JDK, nên tách hai biến hoặc ghi rõ những thay đổi đi kèm để tránh quy nguyên nhân nhầm.

## 14. Kiểm thử generator trong migration

### 14.1. Golden-file hoặc snapshot test

Cho generator cùng một input và lưu output mong đợi. So sánh giúp phát hiện thay đổi class, property, annotation và method. Có thể chuẩn hóa timestamp hoặc format không mang ý nghĩa, nhưng không nên che các diff ảnh hưởng API.

### 14.2. Compile test theo release mục tiêu

Biên dịch file generated dưới `--release` mà sản phẩm hỗ trợ. Điều này phát hiện cú pháp và Java SE API vượt target, nhưng không xác minh đầy đủ thư viện bên ngoài.

### 14.3. Input coverage

Một bộ input đại diện có thể gồm class JavaBean, record, sealed type, generic lồng nhau, annotation trên field/method/parameter/record component, nullable field, collection, overload, nested type và tên Unicode. Không phải generator nào cũng cần hỗ trợ tất cả; phải xác định rõ phạm vi hỗ trợ và báo lỗi khi nhận input ngoài phạm vi.

### 14.4. Integration test

Với mapper, kiểm tra kết quả ánh xạ và dữ liệu lưu. Với API client, kiểm tra serialization và contract. Với ORM metamodel, chạy query trên schema đại diện. Với generated DTO, kiểm tra backward/forward compatibility của payload nếu hệ thống có nhiều phiên bản cùng hoạt động.

### 14.5. Chạy trên runtime thực tế

Generated source compile đúng target vẫn cần được đóng gói và chạy với JDK, dependency, application context và dịch vụ mà sản phẩm dùng. AST compatibility là một thành phần của compatibility toàn hệ thống.

## 15. Ma trận migration dành cho generator

| Biến số | Baseline | Candidate |
|---|---|---|
| JDK chạy build | JDK hiện tại | JDK mục tiêu |
| JDK chạy compiler | JDK hiện tại | Toolchain đã chọn |
| Java `release` | Source/API target hiện tại | Target mới hoặc giữ nguyên |
| Generator version | Bản hiện tại | Bản hỗ trợ JDK mục tiêu |
| Parser/AST library | Grammar hiện tại | Grammar hỗ trợ cú pháp mới |
| Input model/schema | Snapshot | Cùng snapshot khi so sánh |
| Generated output | Snapshot cũ | Snapshot mới |
| Compile | Kết quả trước migration | Kết quả sau migration |
| Hành vi | Test baseline | Test đối chiếu |

Ma trận cần lưu PASS, FAIL, NOT RUN hoặc BLOCKED cho từng bước kèm log và artifact. Không dùng “generator đã chạy” làm đại diện cho “generated code đúng và an toàn để triển khai”.

Nếu generator cũ không chạy trên JDK mới, nên xác nhận phiên bản tương thích và cập nhật công cụ; nếu một generator không còn được duy trì, cần cân nhắc thay công cụ hoặc chuyển sang API công khai.

## 16. Hướng xử lý các giả định AST không còn đúng

Có thể chọn biện pháp theo nguyên nhân:

1. **Cập nhật parser và generator** lên phiên bản chính thức hỗ trợ source/JDK mục tiêu.
2. **Dùng type/symbol model** để nhận diện property, method và quan hệ kiểu, thay cho so sánh chuỗi thiếu ngữ cảnh.
3. **Mở rộng visitor** để xử lý record, sealed hierarchy, pattern và node mới mà công cụ cam kết hỗ trợ.
4. **Giảm phụ thuộc `javac` internals**, dùng annotation processing API công khai khi yêu cầu cho phép.
5. **Tách môi trường generator và output target**: JDK chạy tool có thể khác Java release mà generated source cần hỗ trợ.
6. **Xử lý namespace và dependencies** của mã được sinh cùng với dependency runtime.
7. **Thử lại từ clean output** để loại trừ cache hoặc class cũ.
8. **Kiểm tra semantics**, không chỉ khả năng biên dịch: mapping, dữ liệu, serialization và public API.

Việc thêm JVM flag cho compiler internals có thể giúp vượt qua lỗi access cụ thể, nhưng nếu AST node hoặc internal method đã thay đổi thì flag không giải quyết được. Cần ghi rõ đây là workaround tạm thời và có cách loại bỏ.

## 17. Checklist khảo sát thực tế

Trước khi nâng JDK, hãy trả lời các câu hỏi sau:

- Dự án có bao nhiêu nguồn sinh Java hoặc bytecode?
- Công cụ nào thao tác AST hoặc API nội bộ javac?
- Mã sinh được lưu ở đâu và có bị commit hay cache không?
- Generator đang nhắm Java source/API release nào?
- Parser có hiểu record, sealed type, switch expression, pattern matching mà source dùng không?
- Processor có xử lý đủ element kind và annotation position không?
- Có template nào hard-code `javax.*`, `jakarta.*` hoặc API JDK cụ thể không?
- Test có biên dịch generated source bằng target release không?
- Test có xác nhận semantics của mapper, serializer, client, metamodel không?
- Sau clean build, generated output có tái tạo đầy đủ từ input canonical không?
- Kết quả runtime trên JDK mục tiêu có tương ứng với build artifact đã kiểm tra không?

Sau migration, lưu snapshot generated source, log generator, plugin/toolchain versions, compiler configuration, kết quả compile và integration test làm bằng chứng. Với lỗi chưa khắc phục, ghi rõ source, loại AST node hoặc API liên quan thay vì chỉ báo “Java upgrade failed”.

## 18. Nguyên tắc cốt lõi

**Mã được sinh tự động cũng là mã nguồn cần được xác minh.** Công cụ tạo mã phụ thuộc vào grammar, AST, type model, compiler API, Java target và framework. Một thay đổi nhỏ trong cú pháp hoặc cấu trúc model có thể làm generator dừng hoạt động, hoặc sinh ra Java hợp lệ nhưng sai nghiệp vụ.

Do đó, trong Java Advance Compatibility Migration, cần kiểm kê các generator, xác định giả định về source/AST, sinh lại output từ input canonical, biên dịch bằng target Java release và kiểm thử hành vi. Khi cả quá trình đọc source, sinh mã, biên dịch và chạy ứng dụng được xác minh, nhóm mới có cơ sở kết luận hệ thống tương thích với việc nâng cấp Java.
