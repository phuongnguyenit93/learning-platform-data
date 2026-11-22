# Annotation processor kiểm tra bất biến, sinh mã và tài nguyên

## 1. Tổng quan bài thực hành

Trong một dự án Java lớn, có những quy tắc nên được kiểm tra **ngay lúc biên dịch** thay vì đợi chương trình chạy. Ví dụ: model đã đánh dấu là hợp đồng immutable-style phải có khai báo phù hợp; mỗi hợp đồng cần một `id` đúng quy ước, một `version` hợp lệ; các model hợp lệ phải có source metadata và resource file nhất quán. Khi số lớp tăng lên, kiểm tra thủ công dễ sai, còn kiểm tra bằng runtime reflection quá muộn đối với một số lỗi.

**Annotation processing** giải quyết một phần bài toán: `javac` chạy một `Processor` trên các declarations được biểu diễn bằng `Element`/`TypeMirror`, phát ra compile-time diagnostics và dùng `Filer` tạo thêm Java source hoặc resources. API `javax.annotation.processing` và `javax.lang.model` có từ **Java 6** và vẫn được Java SE 26 duy trì. Chúng thuộc module `java.compiler`, không phải APIs legacy đã bị thay thế.

Bài này xây một processor hoàn chỉnh tên `CheckedModelProcessor` để xử lý `@CheckedModel`:

- **Kiểm tra bất biến cấu trúc:** top-level `public final class`; `id` lowercase kebab-case có 3–32 ký tự; `version > 0`; ít nhất một instance field; mọi instance field `private final`; không cho array fields theo policy minh họa.
- **Kiểm tra hợp đồng:** không để hai model cùng `id` trong **một invocation** của processor.
- **Sinh Java source:** với `PurchaseOrder`, tạo `PurchaseOrderContract.java` chứa `MODEL`, `ID`, `VERSION`, `FIELDS`.
- **Sinh tài nguyên:** tạo `META-INF/contracts/com.example.model.PurchaseOrder.properties` dưới class output.
- **Kiểm thử dương:** biên dịch hai model hợp lệ, compiler tự build generated sources; một chương trình runtime đọc cả generated class và resource, đối chiếu metadata.
- **Kiểm thử âm:** compiler từ chối model sai với mã CM002–CM006, phát hiện ID trùng bằng CM008, kiểm tra `-proc:none` không sinh output.
- **Kiểm thử vòng xử lý:** nhìn thấy ba rounds trên javac: source đầu vào → generated Java sources → final round.

**Lưu ý về “bất biến”:** các quy tắc trên kiểm tra *khai báo tĩnh* chứ **không chứng minh deep immutability**. Một `private final List<String>` vẫn có thể trỏ tới list mutable. Các bất biến như `amountCents >= 0` vẫn phải được kiểm tra bằng constructor/factory và runtime tests. Processor không thực thi các constructor trong thời gian biên dịch.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Định nghĩa annotation với `@Target(TYPE)`, `@Retention(SOURCE)` và members hợp lệ.
2. Implement `AbstractProcessor.process`, `@SupportedAnnotationTypes`, `@SupportedSourceVersion`.
3. Dùng `RoundEnvironment.getElementsAnnotatedWith` để lấy đúng elements qua các rounds.
4. Dùng `TypeElement`, `ElementKind`, `NestingKind`, `Modifier`, `TypeKind` để kiểm tra cấu trúc.
5. Gọi `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)`, khiến javac fail với diagnostics gắn source.
6. Gọi `Filer.createSourceFile` để tạo Java source, `Filer.createResource` để tạo metadata resource.
7. Hiểu vai trò `StandardLocation.CLASS_OUTPUT`, `SOURCE_OUTPUT`, `-d`, `-s` và `originatingElements`.
8. Chặn duplicate file creation xuyên rounds bằng state của processor.
9. Biết Java source mới sẽ được compiler xem ở round sau, resource không trở thành annotated source.
10. Cấu hình `-processor`, `-processorpath` tường minh, nhất là vì **JDK 23+** không còn tự động chạy processors từ classpath khi không có cấu hình phù hợp.
11. Phân biệt `-proc:none`, `-proc:only` và `-proc:full`.
12. Thiết kế positive, negative, duplicate-ID, no-processing và clean-build tests.
13. Hiểu giới hạn compile-time validation, incremental builds, module builds và bảo mật processor dependencies.

~~~text
                 Annotated Java sources
                       |
                 javac / JavaCompiler
                       |
                [processing round 1]
                       |
               CheckedModelProcessor
                   /          \
                  v            v
         Compile-time rule    Valid model
         checks via Elements       |
                 |            +----+----+
            ERROR -> fail     |         |
                         createSource createResource
                              |         |
                    generated-sources/   classes/
                    *Contract.java       META-INF/contracts/
                              |          *.properties
                              v
                       [processing round 2]
                              |
                      generated .java compiles
                              |
                         [final round]
                              |
                         runtime DemoMain
                    imports source + reads resource
~~~

## 2. Các API hiện hành và trách nhiệm

| API | Trách nhiệm |
| --- | --- |
| `@interface CheckedModel` | Gắn compile-time contract metadata vào model |
| `AbstractProcessor` | Base class cho processor implementation |
| `RoundEnvironment` | Elements và trạng thái của một processing round |
| `ProcessingEnvironment` | Cung cấp Messager, Filer, Elements, Types, options |
| `TypeElement` | Biểu diễn class/interface/record declaration |
| `Modifier` / `ElementKind` / `TypeKind` | Kiểm tra từ khai báo và types, không cần Class.forName |
| `Messager` | Đưa diagnostics cho compiler/IDE |
| `Filer.createSourceFile` | Sinh file Java được javac xem ở round sau |
| `Filer.createResource` | Sinh auxiliary resource, không phải Java source |
| `StandardLocation.CLASS_OUTPUT` | Đích resource ở thư mục generated class output |
| `javax.annotation.processing.Generated` | Đánh dấu generated source, API từ Java 9 |
| `javac -processor` | Chỉ đích danh processor được phép chạy |
| `javac -processorpath` | Chỉ định nơi chứa processor classes/dependencies |

### 2.1. Khác runtime reflection

Annotation processing đọc **declarations đang được compiler biên dịch**. Source class có thể chưa được biên dịch thành một `Class<?>` trong JVM chạy processor; đừng dùng `Class.forName("com.example.model.PurchaseOrder")` để kiểm tra fields ở compile time. Dùng `TypeElement.getEnclosedElements()`, `VariableElement.asType()` và `Types`/`Elements`.

### 2.2. Không phải runtime code generation

`createSourceFile` tạo Java source để **javac compile trong cùng build**, không tạo một class mới bằng `ClassLoader#defineClass` khi ứng dụng chạy. Generated class được package vào application output; runtime class không cần biết processor đã hoạt động thế nào. Resource được đọc bằng classloader trong chương trình.

### 2.3. SOURCE retention là đủ

`@Retention(RetentionPolicy.SOURCE)` làm annotation có mặt cho compile-time processing nhưng không giữ nó trong runtime classfile như retention RUNTIME. Không bật runtime retention chỉ vì processor muốn đọc annotation values. Nếu ứng dụng cũng cần reflection runtime, đó là yêu cầu riêng và cần thay retention theo thiết kế.

### 2.4. Bất biến tĩnh không phải bất biến toàn bộ hệ thống

Một processor có thể xác nhận `private final`, nhưng **không** thể bảo đảm constructor không leak reference, mutable objects không đổi, database uniqueness, access policy hay concurrency correctness. Cần biết giới hạn này khi đặt tên annotation và khi mô tả bảo đảm của nó.

## 3. Contract của bài: quy tắc và lỗi

| Rule | Mô tả | Diagnostic code |
| --- | --- | --- |
| Đúng type | Top-level class, không record/interface/nested | CM001 |
| Class modifiers | `public final` | CM002 |
| Contract ID | Regex `[a-z][a-z0-9-]{2,31}` | CM003 |
| Contract version | Lớn hơn 0 | CM004 |
| Instance fields | `private final` | CM005 |
| Array fields | Cấm theo policy ví dụ | CM006 |
| Có dữ liệu | Ít nhất một instance field | CM007 |
| Unique ID trong compile | Không trùng trong một processor invocation | CM008 |
| Sinh file thất bại | IOException/FilerException | CM009 |

Việc cấm array là một **quyết định policy của bài**, không phải quy định Java rằng mọi array field đều sai. `final` class cũng không tự động là thread-safe. Khi mở rộng processor cho `record` hoặc immutable collections, cần cập nhật contract và tests; không âm thầm bỏ kiểm tra.

## 4. Bố cục file của lab

~~~text
lab/
  src/
    api/com/example/contract/CheckedModel.java
    processor/com/example/processor/CheckedModelProcessor.java
    model/com/example/model/PurchaseOrder.java
    model/com/example/model/CustomerRef.java
    app/com/example/app/DemoMain.java
    invalid/com/example/invalid/InvalidModel.java
    invalid/com/example/invalid/DuplicateContract.java

  processor-classes/
  generated-sources/
  classes/
  invalid-classes/
  invalid-generated/
~~~

`processor-classes` là nơi compile annotation API và processor trước. `generated-sources` được `javac -s` tạo Java files. `classes` chứa compiled model, generated Java classes và generated resource files. Các thư mục thử âm cần cô lập để không giữ lại artifact của run khác.

## 5. File CheckedModel.java

Đặt tại `src/api/com/example/contract/CheckedModel.java`:

~~~java
package com.example.contract;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckedModel {
    String id();
    int version() default 1;
}
~~~

**Giải thích:** annotation member `id` bắt buộc; `version` mặc định 1. `@Target(TYPE)` chỉ giới hạn annotation vào type declarations; processor vẫn kiểm tra `CLASS` và `TOP_LEVEL`. Annotation tự nó không sinh source, không validate fields và không chạy constructor: những nhiệm vụ đó thuộc processor và ứng dụng.

## 6. File CheckedModelProcessor.java

Đặt tại `src/processor/com/example/processor/CheckedModelProcessor.java`:

~~~java
package com.example.processor;

import com.example.contract.CheckedModel;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.NestingKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.TypeKind;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("com.example.contract.CheckedModel")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CheckedModelProcessor extends AbstractProcessor {
    private final Set<String> generated = new HashSet<>();
    private final Map<String, String> idOwners = new HashMap<>();

    private void error(Element element, String code, String message) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR, code + ": " + message, element);
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) return true;
        for (Element element : round.getElementsAnnotatedWith(CheckedModel.class)) {
            if (!(element instanceof TypeElement type)
                    || type.getKind() != ElementKind.CLASS
                    || type.getNestingKind() != NestingKind.TOP_LEVEL) {
                error(element, "CM001", "@CheckedModel requires a top-level class");
                continue;
            }

            boolean valid = true;
            if (!type.getModifiers().contains(Modifier.PUBLIC)
                    || !type.getModifiers().contains(Modifier.FINAL)) {
                error(type, "CM002", "model class must be public final");
                valid = false;
            }

            CheckedModel spec = type.getAnnotation(CheckedModel.class);
            String id = spec.id();
            if (!id.matches("[a-z][a-z0-9-]{2,31}")) {
                error(type, "CM003", "id must be lowercase kebab-case, 3..32 chars");
                valid = false;
            }
            if (spec.version() <= 0) {
                error(type, "CM004", "version must be positive");
                valid = false;
            }

            List<String> fieldNames = new ArrayList<>();
            for (Element field : type.getEnclosedElements()) {
                if (field.getKind() != ElementKind.FIELD
                        || field.getModifiers().contains(Modifier.STATIC)) {
                    continue;
                }
                fieldNames.add(field.getSimpleName().toString());
                if (!field.getModifiers().contains(Modifier.PRIVATE)
                        || !field.getModifiers().contains(Modifier.FINAL)) {
                    error(field, "CM005", "instance fields must be private final");
                    valid = false;
                }
                if (field.asType().getKind() == TypeKind.ARRAY) {
                    error(field, "CM006", "array fields are not allowed in this contract");
                    valid = false;
                }
            }
            if (fieldNames.isEmpty()) {
                error(type, "CM007", "model needs at least one instance field");
                valid = false;
            }
            if (!valid) continue;

            String name = type.getQualifiedName().toString();
            String earlier = idOwners.putIfAbsent(id, name);
            if (earlier != null && !earlier.equals(name)) {
                error(type, "CM008", "duplicate contract id " + id
                        + " already used by " + earlier);
                continue;
            }
            if (!generated.add(name)) continue;
            Collections.sort(fieldNames);
            try {
                writeFiles(type, id, spec.version(), fieldNames);
            } catch (IOException ex) {
                error(type, "CM009", "cannot create generated files: " + ex.getMessage());
            }
        }
        return true;
    }

    private void writeFiles(TypeElement type, String id, int version,
                            List<String> fields) throws IOException {
        String originalName = type.getQualifiedName().toString();
        String pkg = processingEnv.getElementUtils().getPackageOf(type)
                .getQualifiedName().toString();
        String simpleName = type.getSimpleName() + "Contract";
        String generatedName = pkg.isEmpty() ? simpleName : pkg + "." + simpleName;
        String fieldList = String.join(",", fields);

        JavaFileObject javaFile = processingEnv.getFiler()
                .createSourceFile(generatedName, type);
        try (Writer w = javaFile.openWriter()) {
            if (!pkg.isEmpty()) w.write("package " + pkg + ";\n\n");
            w.write("@javax.annotation.processing.Generated("
                    + "\"com.example.processor.CheckedModelProcessor\")\n");
            w.write("public final class " + simpleName + " {\n");
            w.write("    public static final String MODEL = \"" + originalName + "\";\n");
            w.write("    public static final String ID = \"" + id + "\";\n");
            w.write("    public static final int VERSION = " + version + ";\n");
            w.write("    public static final String FIELDS = \"" + fieldList + "\";\n");
            w.write("    private " + simpleName + "() {}\n");
            w.write("}\n");
        }

        var resource = processingEnv.getFiler().createResource(
                StandardLocation.CLASS_OUTPUT, "",
                "META-INF/contracts/" + originalName + ".properties", type);
        try (Writer w = resource.openWriter()) {
            w.write("contract.id=" + id + "\n");
            w.write("contract.version=" + version + "\n");
            w.write("model.class=" + originalName + "\n");
            w.write("fields=" + fieldList + "\n");
        }
    }
}
~~~

### 6.1. @SupportedAnnotationTypes

`@SupportedAnnotationTypes("com.example.contract.CheckedModel")` phải dùng tên annotation fully qualified. Không nên khai báo `"*"` rồi claim toàn bộ annotations một cách vô ý: processor universal có thể ngăn processor khác nhận annotations. Trong bài processor chỉ xử lý đúng `@CheckedModel`.

### 6.2. @SupportedSourceVersion

`@SupportedSourceVersion(SourceVersion.RELEASE_17)` cho biết processor hỗ trợ source model ở target Java 17. Bài luôn compile app `--release 17`, dù test chạy bằng OpenJDK 24. Muốn biên dịch Java source mới ở JDK 26, cần kiểm tra processor với `ElementKind`/grammar mới và cập nhật supported source version tương ứng.

### 6.3. Diagnostic.Kind.ERROR

`processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ..., element)` báo lỗi cho javac/IDE, khiến compiler exit nonzero. Với invalid source, nó có thể báo **nhiều mã lỗi** để người viết sửa một lượt. Không dùng `System.out.println` thay compiler diagnostic; standard output không làm compiler tự fail.

### 6.4. Vì sao không dùng Class.forName?

Một annotated type vừa được gửi cho compiler có thể chưa được viết thành classfile. `TypeElement`/`Element.getModifiers`/`TypeMirror.getKind` mô tả declaration mà không cần load hay khởi tạo model. Reflection trong processor còn có nguy cơ đọc nhầm class cùng tên phiên bản cũ từ build classpath.

### 6.5. processed Set và idOwners Map

`generated` lưu fully-qualified types đã xử lý để không gọi `Filer.createSourceFile` lặp lại ở rounds sau. `idOwners` phát hiện ID trùng trong **cùng một compiler/processor invocation**. Map **không** tự có thông tin của modules đã build ở invocation khác, nên không được coi là uniqueness registry toàn hệ thống. Nếu build incremental chỉ truyền một source, duplicate ID có thể không được kiểm tra ở phạm vi project; thiết kế aggregator/registry riêng khi cần.

### 6.6. Sorting deterministic

`Collections.sort(fieldNames)` làm `FIELDS` và resource có thứ tự ổn định, ví dụ `amountCents,orderId` bất kể trình tự elements. Generated code không thêm timestamps hoặc random tokens, nên dễ tái tạo và dễ kiểm tra diff. ID regex giới hạn ký tự ASCII để không gặp rủi ro Java-string/Properties-escaping trong fixture. Nếu annotation cho phép arbitrary text, phải escape theo đúng syntax Java/properties hoặc dùng generator chuẩn.

### 6.7. createSourceFile và createResource

`Filer.createSourceFile(generatedName,type)` tạo source ở `SOURCE_OUTPUT` (thường là `-s`), và close Writer làm compiler nhận diện source mới cho round tiếp theo. `createResource(StandardLocation.CLASS_OUTPUT, "", relativePath, type)` tạo resource ở class output `-d`. Resource **không trở thành Java source** và không có annotation-processing round chỉ vì tồn tại.

`type` truyền vào hai methods là **originating element**, một hint quan trọng để build tools biết output phụ thuộc source nào. Tuy nhiên hint này **không tự bảo đảm** mọi incremental tool nhận diện processor là isolating: còn phụ thuộc Gradle/Maven/plugin conventions.

### 6.8. Không tạo Java source trong final round

`round.processingOver()==true` báo final round. Source được tạo lúc này sẽ không đi qua một annotation-processing round tiếp; do đó processor `return true` mà không sinh files. Với output tổng hợp phải có chiến lược rõ; bài chọn **per-model source/resource** được tạo ngay khi thấy annotated element, tránh phụ thuộc final-round source generation.

### 6.9. Tránh FilerException

Trong một processor run, một pathname chỉ được tạo theo ràng buộc của Filer. Gọi `createSourceFile` hai lần cùng FQN hoặc cố ghi output đè initial input có thể ném `FilerException`. Không fallback sang `Files.write` để ghi thẳng vào source tree hoặc output folder: làm vậy phá tracking của compiler/incremental tools. Báo lỗi CM009, fail build, clean intermediate output và sửa quy tắc naming.

### 6.10. Failure không rollback tất cả files tự động

Nếu source đã tạo thành công nhưng createResource thất bại, intermediate generated source có thể vẫn nằm trong output. Vì `Messager` đã báo ERROR, compilation phải được coi là thất bại; pipeline không được publish các generated artifacts từ failed run. Dùng clean output directory hoặc build isolation để không lẫn stale files với lượt chạy kế.

### 6.11. @Generated là annotation hiện đại

`@javax.annotation.processing.Generated` (Java 9+) đánh dấu source do tool tạo, có SOURCE retention; nó không tự tạo processor service registration hay thay đổi runtime behavior. Trong bài, generated Java có marker để developer/IDE biết file do processor sở hữu. Không cho developer tự sửa generated file làm source-of-truth vì lần build sau sẽ sinh lại.

## 7. File PurchaseOrder.java (model hợp lệ)

~~~java
package com.example.model;

import com.example.contract.CheckedModel;

@CheckedModel(id = "purchase-order", version = 2)
public final class PurchaseOrder {
    private final String orderId;
    private final long amountCents;

    public PurchaseOrder(String orderId, long amountCents) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId required");
        }
        if (amountCents < 0) {
            throw new IllegalArgumentException("amountCents must be >= 0");
        }
        this.orderId = orderId;
        this.amountCents = amountCents;
    }

    public String orderId() { return orderId; }
    public long amountCents() { return amountCents; }
}
~~~

Đây là model vượt compile-time rules: `public final`; ID hợp lệ, version dương, hai instance fields `private final`, không có array. Constructor thực hiện **runtime validation**, nên không thể quy toàn bộ correctness cho annotation processor.

## 8. File CustomerRef.java (model thứ hai)

~~~java
package com.example.model;

import com.example.contract.CheckedModel;

@CheckedModel(id = "customer-ref", version = 1)
public final class CustomerRef {
    private final String customerId;

    public CustomerRef(String customerId) {
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("customerId required");
        }
        this.customerId = customerId;
    }

    public String customerId() { return customerId; }
}
~~~

Model này cho phép kiểm thử processor sinh **hai cặp output độc lập** trong cùng compilation. `customer-ref` khác `purchase-order`, nên không bị CM008. Model có một field, version dương và constructor validation riêng.

## 9. Generated Java và generated resource

### 9.1. Kết quả PurchaseOrderContract.java

`generated-sources/com/example/model/PurchaseOrderContract.java` được processor tạo; **không viết file này bằng tay**:

~~~java
package com.example.model;

@javax.annotation.processing.Generated("com.example.processor.CheckedModelProcessor")
public final class PurchaseOrderContract {
    public static final String MODEL = "com.example.model.PurchaseOrder";
    public static final String ID = "purchase-order";
    public static final int VERSION = 2;
    public static final String FIELDS = "amountCents,orderId";
    private PurchaseOrderContract() {}
}
~~~

Compiler sẽ biên dịch source này thành `classes/com/example/model/PurchaseOrderContract.class`. Những static final constants có thể được inline khi compilation; nếu cần metadata thay đổi động ở runtime, hãy dùng một interface/protocol phù hợp thay vì hằng build-time.

### 9.2. Kết quả resource

`classes/META-INF/contracts/com.example.model.PurchaseOrder.properties`:

~~~properties
contract.id=purchase-order
contract.version=2
model.class=com.example.model.PurchaseOrder
fields=amountCents,orderId
~~~

File này ở `CLASS_OUTPUT`, nên nó có thể được đóng vào application JAR cùng các compiled class files. `Properties.load(InputStream)` đọc đúng ASCII properties trong lab. Khi resource chứa Unicode hoặc ký tự `=`, `:`, `\`, newlines, phải áp dụng proper properties encoding/escaping; đừng nối arbitrary annotation text vào file rồi giả định được parse đúng.

### 9.3. Không nhầm resource với processor service file

`META-INF/contracts/...` là quy ước riêng của ứng dụng. `META-INF/services/javax.annotation.processing.Processor` (nếu dùng) là **file service provider configuration** để javac discover processor. Chúng hoàn toàn khác mục đích; custom resource không tự chạy processor, và processor registration không tự tạo runtime business registry.

## 10. File DemoMain.java đọc kết quả thật

~~~java
package com.example.app;

import com.example.model.CustomerRefContract;
import com.example.model.PurchaseOrder;
import com.example.model.PurchaseOrderContract;
import java.io.InputStream;
import java.util.Properties;

public final class DemoMain {
    static void check(boolean okay, String message) {
        if (!okay) throw new AssertionError(message);
    }

    static Properties readResource(String name) throws Exception {
        Properties props = new Properties();
        try (InputStream stream = DemoMain.class.getClassLoader()
                .getResourceAsStream("META-INF/contracts/" + name + ".properties")) {
            check(stream != null, "generated resource missing: " + name);
            props.load(stream);
        }
        return props;
    }

    public static void main(String[] args) throws Exception {
        Class<?> generated = Class.forName("com.example.model.PurchaseOrderContract");
        check(generated != null, "generated class not compiled");
        check("purchase-order".equals(PurchaseOrderContract.ID), "id");
        check(PurchaseOrderContract.VERSION == 2, "version");
        check("com.example.model.PurchaseOrder".equals(PurchaseOrderContract.MODEL), "model");
        check("amountCents,orderId".equals(PurchaseOrderContract.FIELDS), "fields");

        Properties props = readResource("com.example.model.PurchaseOrder");
        check(PurchaseOrderContract.ID.equals(props.getProperty("contract.id")),
                "id mismatch");
        check("2".equals(props.getProperty("contract.version")), "version mismatch");
        check(PurchaseOrderContract.MODEL.equals(props.getProperty("model.class")),
                "model mismatch");
        check(PurchaseOrderContract.FIELDS.equals(props.getProperty("fields")),
                "fields mismatch");

        check("customer-ref".equals(CustomerRefContract.ID), "second id");
        Properties second = readResource("com.example.model.CustomerRef");
        check("customer-ref".equals(second.getProperty("contract.id")),
                "second resource");

        PurchaseOrder order = new PurchaseOrder("PO-1", 1500);
        check("PO-1".equals(order.orderId()) && order.amountCents() == 1500,
                "business behavior");
        boolean invalidRejected = false;
        try {
            new PurchaseOrder("PO-2", -1);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected, "runtime business invariant");

        System.out.println("generated-class-loadable=true");
        System.out.println("metadata-id=" + PurchaseOrderContract.ID);
        System.out.println("metadata-version=" + PurchaseOrderContract.VERSION);
        System.out.println("metadata-model=" + PurchaseOrderContract.MODEL);
        System.out.println("metadata-fields=" + PurchaseOrderContract.FIELDS);
        System.out.println("resource-id=" + props.getProperty("contract.id"));
        System.out.println("resource-version=" + props.getProperty("contract.version"));
        System.out.println("resource-model=" + props.getProperty("model.class"));
        System.out.println("resource-fields=" + props.getProperty("fields"));
        System.out.println("second-generated-model=" + CustomerRefContract.ID);
        System.out.println("second-resource=" + second.getProperty("contract.id"));
        System.out.println("negative-amount-rejected=" + invalidRejected);
        System.out.println("tests=PASS");
    }
}
~~~

**Giải thích:** `Class.forName` kiểm tra generated class đã được compiler tạo và load được; chỉ dùng static final constants có thể bị javac inline, nên kiểm tra này hữu ích. `readResource` kiểm tra CLASS_OUTPUT resource được đóng trên runtime classpath. Các asserts so khớp generated class metadata với resource và kiểm tra runtime constructor invariant. Chúng kiểm tra **hai sản phẩm sinh mã khác nhau**, không chỉ đếm callback của processor.

## 11. Lệnh build và chạy Java 17+ hoàn chỉnh

### 11.1. Compile annotation API và processor trước

Với Bash/Linux/macOS, tại thư mục `lab`:

~~~bash
mkdir -p processor-classes classes generated-sources

javac -encoding UTF-8 --release 17 -proc:none \
  -d processor-classes \
  src/api/com/example/contract/CheckedModel.java \
  src/processor/com/example/processor/CheckedModelProcessor.java
~~~

PowerShell/Windows:

~~~powershell
New-Item -ItemType Directory -Force -Path processor-classes,classes,generated-sources | Out-Null
javac -encoding UTF-8 --release 17 -proc:none -d processor-classes src/api/com/example/contract/CheckedModel.java src/processor/com/example/processor/CheckedModelProcessor.java
~~~

`-proc:none` ở bootstrap tránh compiler tự chạy processor khi đang biên dịch chính processor. Output `processor-classes` có API annotation và compiled processor.

### 11.2. Compile models cùng generated source

Bash:

~~~bash
javac -encoding UTF-8 --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor com.example.processor.CheckedModelProcessor \
  -d classes -s generated-sources -XprintRounds \
  src/model/com/example/model/PurchaseOrder.java \
  src/model/com/example/model/CustomerRef.java \
  src/app/com/example/app/DemoMain.java

java -cp classes:processor-classes com.example.app.DemoMain
~~~

PowerShell:

~~~powershell
javac -encoding UTF-8 --release 17 -cp processor-classes -processorpath processor-classes -processor com.example.processor.CheckedModelProcessor -d classes -s generated-sources -XprintRounds src/model/com/example/model/PurchaseOrder.java src/model/com/example/model/CustomerRef.java src/app/com/example/app/DemoMain.java
java -cp "classes;processor-classes" com.example.app.DemoMain
~~~

Ở Windows, classpath separator là `;`; Linux/macOS dùng `:`. `-cp` để compiler giải quyết annotation types, `-processorpath` để load processor, `-processor` chỉ chọn processor, `-s` là generated Java source, `-d` là compiled classes/resources.

### 11.3. Kết quả rounds trên OpenJDK 24

Bộ kiểm thử đã chạy `-XprintRounds` và quan sát **ba rounds**:

~~~text
Round 1: original PurchaseOrder, CustomerRef, DemoMain; @CheckedModel
Round 2: generated PurchaseOrderContract, CustomerRefContract; @Generated
Round 3: no new input; processingOver=true (final round)
~~~

Đây là bản **tóm tắt** các fields của output compiler, không phải từng ký tự của `-XprintRounds`. Compiler thực tế dùng fully-qualified names, có thể khác thứ tự hoặc số rounds khi thêm processors.

Bộ kiểm thử còn đếm outputs:

~~~text
generated-java-files=2
generated-resources=2
~~~

Hai dòng này là của test harness, **không phải** stdout do javac tự in. Thử nghiệm có hai classes được annotate và mỗi class sinh một source + một resource.

### 11.4. Stdout DemoMain chính xác đã kiểm thử

Chạy thành công trên OpenJDK 24 với `javac --release 17`:

~~~text
generated-class-loadable=true
metadata-id=purchase-order
metadata-version=2
metadata-model=com.example.model.PurchaseOrder
metadata-fields=amountCents,orderId
resource-id=purchase-order
resource-version=2
resource-model=com.example.model.PurchaseOrder
resource-fields=amountCents,orderId
second-generated-model=customer-ref
second-resource=customer-ref
negative-amount-rejected=true
tests=PASS
~~~

**Đọc kết quả:** generated Java class có thể load, ID/version/model/field metadata đúng, resource trong CLASS_OUTPUT đọc được và khớp chính xác, model thứ hai cũng có generated artifacts, constructor chặn số tiền âm. Không có external dependency, database hay network.

## 12. Kiểm thử âm: InvalidModel.java

Một processor chỉ sinh đúng với source hợp lệ nhưng không từ chối source sai thì **chưa kiểm tra bất biến**. Ta cần test compiler fail với diagnostic codes đúng.

Đặt `src/invalid/com/example/invalid/InvalidModel.java`:

~~~java
package com.example.invalid;

import com.example.contract.CheckedModel;

@CheckedModel(id = "Bad ID", version = 0)
public class InvalidModel {
    public String mutableName;
    private final String[] tags = {"x"};
}
~~~

Vi phạm cụ thể:

- Class không final → `CM002`.
- ID chứa chữ hoa/khoảng trắng → `CM003`.
- Version bằng 0 → `CM004`.
- Field `mutableName` không private final → `CM005`.
- Field `tags` là array → `CM006`.

### 12.1. Lệnh compile-negative

Bash:

~~~bash
mkdir -p invalid-classes invalid-generated
javac -encoding UTF-8 --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor com.example.processor.CheckedModelProcessor \
  -d invalid-classes -s invalid-generated \
  src/invalid/com/example/invalid/InvalidModel.java
~~~

Lệnh này **dự kiến trả exit code khác 0**. Không coi stderr của javac là lỗi bất thường của test runner; test phải assert được exit code và mã diagnostics. Đối với PowerShell 5.1 đang đặt `$ErrorActionPreference='Stop'`, một native tool ghi stderr ở compile-negative có thể gây `NativeCommandError` trước khi đọc diagnostics. Hãy tạm xử lý expected stderr bằng `Continue` trong đúng test và khôi phục state sau đó.

### 12.2. Kết quả negative harness đã kiểm thử

~~~text
negative-compile-failed=true
negative-diagnostics=CM002,CM003,CM004,CM005,CM006
invalid-generated-output-absent=true
tests=PASS
~~~

Đây là **normalized stdout của test harness**, không phải nguyên văn javac diagnostics theo file path/line. Test đọc compiler diagnostics và assert các mã CM002–CM006 có mặt, exit code nonzero; sau đó kiểm tra không có generated source/resource của invalid model trong thư mục test cô lập.

### 12.3. Vì sao báo nhiều lỗi một lần?

Processor dùng `valid=false` nhưng tiếp tục kiểm tra tất cả instance fields và annotation values, giúp developer sửa nhiều rule violations sau **một lần compile**. Sau khi phát hiện invalid, processor `continue` trước Filer. Không sinh metadata từ một model đã fail validation.

### 12.4. Build fail không tự rollback mọi output

Nếu có một model hợp lệ và một model invalid trong cùng invocation, source/resource của model hợp lệ **có thể đã được tạo trước khi** javac báo compiler error. File trung gian không có nghĩa build thành công. Pipeline phải **chỉ publish khi javac exit=0** và nên build vào clean/isolated output directories để không dùng stale artifacts.

## 13. Kiểm thử âm: trùng ID

Đặt `DuplicateContract.java`:

~~~java
package com.example.invalid;

import com.example.contract.CheckedModel;

@CheckedModel(id = "purchase-order", version = 1)
public final class DuplicateContract {
    private final String ref = "duplicate";
}
~~~

Biên dịch file này cùng `PurchaseOrder.java` trong **một** javac invocation; cả hai có `id="purchase-order"`. `Map<String,String> idOwners` phát hiện duplicate, báo CM008 và compiler fail.

~~~bash
mkdir -p duplicate-classes duplicate-generated
javac -encoding UTF-8 --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor com.example.processor.CheckedModelProcessor \
  -d duplicate-classes -s duplicate-generated \
  src/model/com/example/model/PurchaseOrder.java \
  src/invalid/com/example/invalid/DuplicateContract.java
~~~

Kết quả test đã được xác minh:

~~~text
duplicate-id-compile-failed=true
duplicate-id-diagnostic=CM008
tests=PASS
~~~

**Giới hạn:** thứ tự processor nhìn thấy hai classes không được bảo đảm, nên không assert câu “ID ban đầu thuộc PurchaseOrder” trong diagnostic; chỉ assert CM008 và nonzero exit. Nếu một model được build ở module/lượt incremental khác, processor Map không nhìn thấy ID của nó. Unique ID xuyên project cần aggregation hoặc registry cấp cao hơn.

## 14. Kiểm thử -proc:none: không có generated artifacts

Với `-proc:none`, compiler chỉ compile annotation-bearing models, **không chạy processor**:

~~~bash
mkdir -p no-proc-classes no-proc-generated
javac -encoding UTF-8 --release 17 -proc:none \
  -cp processor-classes \
  -d no-proc-classes -s no-proc-generated \
  src/model/com/example/model/PurchaseOrder.java \
  src/model/com/example/model/CustomerRef.java
~~~

Bộ test xác nhận:

~~~text
proc-none-generated-output-absent=true
tests=PASS
~~~

Nếu compile cả `DemoMain.java` trong **một output sạch** với `-proc:none`, javac sẽ không tìm thấy `PurchaseOrderContract`/`CustomerRefContract`. Nếu một directory còn stale generated classes từ run trước, compiler có thể vô tình thành công; do đó luôn clean output khi kiểm tra annotation processing configuration.

### 14.1. Phân biệt các -proc modes

| Tùy chọn | Chạy processors? | Compile Java classes? |
| --- | --- | --- |
| `-proc:none` | Không | Có |
| `-proc:only` | Có | Không compile source classes |
| `-proc:full` | Có | Có |
| `-processor FQN` cùng compilation | Có vì processor cấu hình tường minh | Có nếu không dùng proc:only |

Từ **JDK 23**, javac yêu cầu explicit annotation processing configuration thay vì tình cờ quét processors trên classpath. Hãy chỉ định `-processor`/`--processor-path` như lab hoặc cấu hình build tool tương ứng. Không dùng `-proc:full` cộng với classpath chứa processors không được kiểm soát: phiên bản processor nào được chạy vẫn cần xác định.

## 15. Nhiều vòng processing và cách viết an toàn

### 15.1. Round lifecycle

`process` có thể được gọi nhiều lần trên **cùng instance**. `RoundEnvironment.getElementsAnnotatedWith` cho tập elements ở round đó. Khi `Filer` đóng generated Java source, source được compiler đưa vào round kế; final round có `processingOver()==true`. Không tạo source mới trong final round vì không có annotation-processing round tiếp theo cho source đó.

### 15.2. Không duplicate output

Trong cùng compilation run, Filer cấm tạo lặp cùng pathname bằng một create method. `Set generated` chống tạo lại `PurchaseOrderContract` ở vòng sau. Nếu vẫn xảy ra `FilerException`, không ghi đè bằng `FileWriter` bên ngoài Filer; hãy báo lỗi CM009 và sửa naming/round state.

### 15.3. Nhiều processors phối hợp

Một processor khác có thể sinh source chứa `@CheckedModel` ở round 1; `CheckedModelProcessor` có thể thấy nó ở round sau. Việc sinh **một metadata class và resource cho mỗi model** cho phép xử lý từng model qua rounds mà không cần một Java registry tổng hợp được tạo quá sớm. Nếu cần **một** registry tổng hợp mọi generated models, phải thiết kế aggregation cẩn thận và test nhiều rounds/module builds.

### 15.4. errorRaised và processingOver

`round.errorRaised()` nói một lỗi đã được raise ở **round trước**; không thay cho validation của current elements. `round.processingOver()` là điều kiện final round; không được hiểu là toàn compiler run đã publish artifacts thành công.

### 15.5. Source files và resource files không cùng semantics

`Filer.createSourceFile` tạo Java source được compiler/rounds theo dõi; `Filer.createResource` tạo custom auxiliary resource, không tự trở thành Java source và không được compiler compile. Resource có thể được đóng vào final JAR và đọc bởi app classloader; package/output path cần được test, không dựa vào đường dẫn ngẫu nhiên của IDE.

## 16. Build tool integration và bảo mật

### 16.1. Service registration là một lựa chọn khác

Ngoài `-processor FQN`, processor có thể đăng ký dưới file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

với nội dung:

~~~text
com.example.processor.CheckedModelProcessor
~~~

Đây là **service provider configuration của processor JAR**, không phải custom model resource `META-INF/contracts`. Với JDK 23+, vẫn cấu hình annotation processor path/module path hoặc explicit opt-in theo compiler/tool, không giả định ngầm từ runtime classpath.

### 16.2. Maven/Gradle

Trong production, đóng annotation API và processor thành artifacts có phiên bản. Gradle dùng configuration `annotationProcessor`; Maven Compiler Plugin có cấu hình processor/dependencies tương ứng. Test rằng IDE và CI cùng chạy processor đã pin version, generated sources nằm dưới build directory và resources được package. Không để processor code/module tình cờ nằm trong application runtime dependencies khi không cần.

### 16.3. Processor là executable build-time code

Processor chạy bằng JVM của javac, có thể có quyền đọc file, env vars, network tùy môi trường. Chỉ cho phép dependencies đã review/pin, chạy trong CI sandbox thích hợp, không dùng annotation strings từ untrusted sources để xây path/Java code tùy ý. Lý do JDK 23 thay đổi default có liên quan **tránh chạy processor ngầm** từ classpath.

### 16.4. Incremental compilation

Truyền `originatingElements` là thực hành tốt, giúp tool biết output gắn source nào. Nhưng chỉ như vậy chưa đủ để tuyên bố processor hỗ trợ incremental isolating/aggregating theo mọi Gradle/Maven plugin. Tests cần bao gồm thêm/xóa/đổi model, xử lý stale outputs và duplicate IDs giữa nhiều compilation tasks.

### 16.5. Module path

`javax.annotation.processing` nằm trong `java.compiler`. Một named module triển khai processor có thể cần:

~~~java
module com.example.processor {
    requires java.compiler;
    // provides Processor with implementation nếu dùng processor module path.
}
~~~

Đây là **snippet** không phải module-info.java runnable đầy đủ; phải dùng đúng `--processor-module-path` và cung cấp `provides javax.annotation.processing.Processor with com.example.processor.CheckedModelProcessor;` khi dùng kiểu module-service. Lab classpath không cần modules để tập trung vào processor logic.

## 17. Checklist QA và lỗi thường gặp

| Điều kiện | Điều phải quan sát |
| --- | --- |
| Annotation processor compiled trước | `CheckedModelProcessor.class` trong processor path |
| Annotation type có trên compile classpath | Javac hiểu `@CheckedModel` |
| Processor được chọn tường minh | `-processor com.example.processor.CheckedModelProcessor` |
| App compile Java 17 target | `--release 17` |
| Model `public final` | PASS |
| Invalid non-final model | CM002 |
| ID sai format | CM003 |
| Version ≤0 | CM004 |
| Instance field mutable/public | CM005 |
| Array field | CM006 |
| Không có instance fields | CM007 |
| Duplicate ID same invocation | CM008 |
| Duplicate source file creation | FilerException/CM009 |
| Round 1 | Annotated models |
| Round 2 | Generated metadata classes |
| Final round | processingOver=true |
| Generated Java source | Two `*Contract.java` |
| Generated resource | Two `*.properties` |
| Generated classes compiled | Class.forName success |
| Generated resource packaged | getResourceAsStream không null |
| ID/version/model/fields | Metadata source/resource giống nhau |
| Field ordering | Alphabetically sorted |
| Constructor runtime invariant | Negative amount rejected |
| Invalid model compiler exit | Nonzero |
| Invalid generated output | Không có trong test isolation |
| proc:none | Không sinh metadata |
| Clean build | Không phụ thuộc stale artifacts |
| JDK 23+ | Explicit processor configuration |
| IDE build | Generated source directory được nhận diện |
| Module builds | Processor path/module path đúng |
| Security | Trusted/pinned processor dependency |
| Reproducibility | No timestamps/random/unordered output |
| Error messages | Diagnostic.Kind.ERROR có code ổn định |
| Published artifacts | Chỉ sau toàn build PASS |

### 17.1. Những lỗi thiết kế phổ biến

**Chỉ test callback đã chạy:** chưa kiểm tra output thật. Phải test generated class loadable, resource packaged và dữ liệu khớp.

**Sinh Java source vào src/main/java:** gây trộn generated code với handwritten source và tăng rủi ro ghi đè. Dùng Filer và build output directory.

**Xử lý invalid model nhưng vẫn sinh artifact:** làm compile fail nhưng để lại dữ liệu dễ bị publish nhầm. Không generate cho invalid element, và chỉ publish sau complete build PASS.

**Coi public final là deep immutable:** không đúng, đặc biệt với mutable reference fields. Tách contract structure và business/runtime invariants.

**Coi Map ID owners là global:** không đúng với incremental/multi-module builds.

**Cho phép output file ghi lặp:** FilerException hoặc stale artifacts. Quản lý rounds và stable output names.

**Dùng reflection Class.forName trong processor:** compiler model và runtime model khác thời điểm/classloader. Dùng Elements/Types API.

**Quên explicit processor config trên JDK 23+:** build có thể compile annotated sources nhưng không sinh metadata, lỗi chỉ lộ khi app tham chiếu generated types. Cấu hình processor và negative/clean tests.

**Dựa stderr line number vào compiler-specific output:** harness nên kiểm tra mã lỗi CM002–CM008 và exit code, không phụ thuộc absolute temp path.

**Viết resource bằng string concat với dữ liệu bất kỳ:** dễ sai escaping/encoding; lab hạn chế ID ASCII và field names hợp lệ, production cần escaping chuẩn.

**Giả định toàn bộ generated files rollback khi compiler fail:** Filer/compiler không phải transaction filesystem. Cô lập directories, clean và không publish khi exit nonzero.

## 18. Câu hỏi tự đánh giá

**1.** Annotation processor chạy lúc nào? — Trong compilation, không phải khi business application tạo instance.

**2.** Vì sao SOURCE retention đủ? — Compiler thấy annotation trong source; runtime reflection không cần nó.

**3.** Target.TYPE có loại nested classes/records không? — Không; processor kiểm tra ElementKind/NestingKind.

**4.** AbstractProcessor.process trả true là validation pass? — Không, chỉ claim supported annotation types.

**5.** Messager.ERROR có tác dụng gì? — Đưa compiler diagnostic và làm build thất bại.

**6.** createSourceFile khác createResource? — Source tham gia compiler/round kế, resource là auxiliary output.

**7.** Vì sao truyền originating TypeElement? — Gắn source với generated output để tool quản lý dependency.

**8.** Round 2 có generated metadata vì sao? — Đã tạo và close Java Writer trong round 1.

**9.** Final round có sinh Java source mới được dùng ở round sau không? — Không; processingOver=true là vòng cuối.

**10.** CM005 là lỗi gì? — Instance field không private final.

**11.** Version zero gây gì? — CM004, compile fail.

**12.** CM008 bảo đảm ID unique toàn repository? — Không, chỉ scope processor invocation.

**13.** Vì sao sort field names? — Để output deterministic/reproducible.

**14.** Vì sao model vẫn kiểm tra runtime amountCents? — Processor không biết input của constructor.

**15.** Vì sao Class.forName generated class là test hữu ích? — Static final constants có thể inline, cần xác nhận class thật sự tồn tại.

**16.** Nếu resource không có trong JAR? — Runtime getResourceAsStream trả null, cần kiểm tra CLASS_OUTPUT/packaging.

**17.** -proc:none có làm @CheckedModel source mất hiệu lực? — Annotation source vẫn compile được; chỉ processor không chạy.

**18.** -proc:only khác full? — only xử lý annotations, full còn compile class output.

**19.** Từ JDK nào javac thay implicit processor discovery default? — JDK 23.

**20.** Có nên dùng một processor JAR không rõ nguồn gốc trong CI? — Không, processor là code thực thi với quyền build-time.

**21.** FilerException thường do đâu? — Tạo trùng path/FQN hoặc đụng initial inputs trong cùng compilation.

**22.** Một lỗi cuối compilation có thể để lại partial generated files không? — Có, cần clean output và fail publish.

**23.** Java records có dùng được với processor không? — API có thể hỗ trợ, nhưng rule của lab chỉ chấp nhận CLASS; phải mở rộng có tests.

**24.** Có cần third-party library cho ví dụ này không? — Không, toàn bộ dùng Java SE 17+ APIs.

## 19. Bài tập nâng cao

1. Chạy toàn bộ lab trên JDK 17, 21 và 24/26 với `--release 17`; đối chiếu generated artifacts.
2. Thay `id` bằng `"Bad ID"` và quan sát CM003.
3. Thử version âm và đo compiler exit code.
4. Bỏ `final` khỏi model để tái hiện CM002.
5. Tạo class có public mutable field và assert CM005.
6. Tạo class chỉ chứa static fields và assert CM007.
7. Thử array instance field để tái hiện CM006.
8. Thử annotation trên record, enum và nested class; cập nhật policy nếu muốn hỗ trợ.
9. Biên dịch hai classes trùng ID trong một invocation; xác nhận CM008.
10. Biên dịch từng model qua nhiều invocations để thấy giới hạn uniqueness Map.
11. Thêm processor thứ hai sinh annotated source, kiểm tra model ở round tiếp theo được xử lý.
12. Thử tạo cùng generated FQN hai lần trong isolated compile, quan sát FilerException.
13. Chạy `-proc:only`, xác nhận source/resources tạo nhưng app classfiles không compile.
14. Chạy `-proc:none` với clean output; xác nhận generated class không tồn tại.
15. Thực hiện hai clean builds và so byte-level hashes của source/resource.
16. Thay file properties bằng JSON và thêm escaping/reader tương ứng, test roundtrip Unicode.
17. Tạo một immutable-style model dùng `List.copyOf`, phân biệt compile-time check với runtime deep-copy behavior.
18. Tạo generated metadata với method thay vì static final constants, xem tradeoff API compatibility.
19. Tạo service provider file cho processor JAR và cấu hình explicit processor path.
20. Tích hợp với Gradle `annotationProcessor` và test IDE/CI.
21. Test module-based processor discovery qua `--processor-module-path`.
22. Viết một test harness bằng `javax.tools.JavaCompiler` để kiểm tra diagnostics không cần shell.
23. Kiểm tra generated sources khi một module thay đổi/tên type đổi, đảm bảo stale files được loại.
24. Thiết kế registry toàn repo nếu cần unique contract IDs xuyên modules.
25. Review security của processor dependencies/CI secrets/remote network access.
26. Thêm `@SupportedOptions` và một `-Acheckedmodel.strict=true` option, test behavior.
27. Viết producer/consumer contract tests kiểm tra resource schema version trong runtime.
28. Kiểm thử generated Java với reflection để phát hiện unintentional public mutable API.
29. Ghi nhận performance của processor khi hàng nghìn models được annotate.
30. Cập nhật policy cho Java 21/26 sources khi cần, nhưng giữ processor compatibility được kiểm thử thay vì tự nâng version.

## 20. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — javax.annotation.processing](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/package-summary.html): compile-time processing APIs vẫn duy trì.
- [Oracle Java SE 26 — AbstractProcessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): base processor/process contract.
- [Oracle Java SE 26 — Processor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Processor.html): rounds, lifecycle, claim semantics.
- [Oracle Java SE 26 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): Messager/Filer/Elements/Types/options.
- [Oracle Java SE 26 — RoundEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): processingOver/errorRaised/getElementsAnnotatedWith.
- [Oracle Java SE 26 — Filer](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html): createSourceFile/createResource, originating elements và output constraints.
- [Oracle Java SE 26 — FilerException](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/FilerException.html): same-path conflicts.
- [Oracle Java SE 26 — Messager](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Messager.html): compiler diagnostics.
- [Oracle Java SE 26 — Generated](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Generated.html): generated source marker.
- [Oracle Java SE 26 — SupportedAnnotationTypes](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedAnnotationTypes.html): FQN matching.
- [Oracle Java SE 26 — SupportedSourceVersion](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/SupportedSourceVersion.html): compiler source version.
- [Oracle Java SE 26 — TypeElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): source type representation.
- [Oracle Java SE 26 — ElementKind](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): CLASS/FIELD/RECORD kinds.
- [Oracle Java SE 26 — Modifier](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Modifier.html): declaration modifiers.
- [Oracle Java SE 26 — TypeKind](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeKind.html): ARRAY and others.
- [Oracle Java SE 26 — StandardLocation](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardLocation.html): SOURCE_OUTPUT/CLASS_OUTPUT.
- [Oracle Java SE 26 — Diagnostic.Kind](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): ERROR, WARNING, NOTE.
- [Oracle Java SE 26 — javac](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): processor options, -s/-d, rounds, Java target.
- [Oracle JDK 23 Release Notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): explicit annotation-processing policy change.
- [OpenJDK Inside Java — JDK 23 annotation processing](https://inside.java/2024/06/18/quality-heads-up/): recommended explicit configuration.
- [Oracle Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): Java 17 lab API availability.
- [Oracle Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): Java 17 processor contract.

**Ghi nhớ:** Annotation processing giúp biến **bất biến cấu trúc** thành compiler errors và sinh **Java code + resources** có thể kiểm chứng trong cùng build. `Filer.createSourceFile` tạo source được xử lý ở round kế, `Filer.createResource` tạo auxiliary file ở CLASS_OUTPUT. `Messager.ERROR` phải khiến build fail khi source sai, không sinh metadata cho invalid model. Từ **JDK 23**, cần cấu hình annotation processing tường minh. Một processor tốt có deterministic outputs, quản lý round/duplicate paths, ghi originating elements, có positive/negative/disabled tests và không nhầm `private final` với deep immutable. Business runtime invariants vẫn cần constructor/tests và build phải chỉ publish artifacts khi toàn compilation thành công.
