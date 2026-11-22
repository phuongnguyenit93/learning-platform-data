# Annotation processor và phần tử thuộc mô-đun (Java 9+)

## Mục tiêu

**Annotation processing** cho phép công cụ biên dịch Java kiểm tra các khai báo, đọc annotation, báo lỗi/warning và tạo mã nguồn hoặc tài nguyên **ngay trong quá trình biên dịch**. Từ Java 9, mô hình ngôn ngữ được mở rộng để hiểu Java Platform Module System (JPMS): module trở thành một **program element** với metadata, annotation và các directive như `requires`, `exports`, `opens`, `uses` và `provides`.

Bài này hướng dẫn sử dụng các API **hiện còn được hỗ trợ** trong `java.compiler`: `javax.annotation.processing`, `javax.lang.model` và `javax.tools`. Các ví dụ chạy từ Java 17 trở lên, đồng thời giải thích thay đổi quan trọng từ JDK 23: **cần cấu hình annotation processing một cách tường minh**.

Sau bài học, bạn có thể:

- Hiểu vòng đời `Processor`, `ProcessingEnvironment`, `RoundEnvironment` và cách chạy processor bằng `javac` hoặc compiler API nhúng.
- Phân biệt `ModuleElement` (mô hình module lúc biên dịch) với `java.lang.Module` (module lúc runtime).
- Đọc module name, module annotation, các directive và module sở hữu một `TypeElement`.
- Tổ chức processor path đúng cách khi biên dịch module; tránh nhầm `--module-path` với `--processor-module-path`.
- Kiểm chứng ví dụ annotation processor độc lập, biết khi nào `ModuleElement` có thể không tồn tại và cách xử lý nhiều vòng xử lý.
- Sử dụng `Filer` an toàn trong môi trường nhiều module, không ghi đè đầu vào và không tạo trùng một file.

## 1. Annotation processor hoạt động ở thời điểm nào?

Luồng đơn giản:

```text
.java / module-info.java / package-info.java
                |
                v
     javac đọc các khai báo
                |
                v
 Processor được khởi tạo (init)
                |
                v
   process(round 1), Element model
                |
         tạo source nếu cần
                |
                v
   process(round 2, ...) [có thể]
                |
                v
       final round: processingOver=true
                |
                v
       javac tiếp tục biên dịch
       (trừ khi dùng -proc:only)
```

Processor làm việc với **mô hình khai báo** mà compiler cung cấp: `TypeElement`, `ExecutableElement`, `VariableElement`, `PackageElement`, `ModuleElement`, `AnnotationMirror` và `TypeMirror`. Đây là mô hình compile time; **không cần tải class của ứng dụng bằng reflection**.

| Thành phần | Tác dụng |
| --- | --- |
| `Processor` | Giao diện processor; triển khai điển hình kế thừa `AbstractProcessor` |
| `ProcessingEnvironment` | Cấp `Elements`, `Types`, `Filer`, `Messager` và các tùy chọn cho processor |
| `RoundEnvironment` | Cho biết root elements/annotation xuất hiện trong vòng hiện tại, trạng thái lỗi và vòng cuối |
| `Elements` | Tìm module, package, type, annotation values và quan hệ giữa các element |
| `Types` | Kiểm tra kiểu, assignability, subtype và xử lý `TypeMirror` |
| `Filer` | Tạo file mã nguồn/class/resource mới trong vị trí output được compiler quản lý |
| `Messager` | Gửi diagnostic NOTE/WARNING/ERROR gắn với element khi phù hợp |
| `SourceVersion` | Khả năng tương thích với phiên bản ngôn ngữ Java được hỗ trợ |

Điểm khác biệt quan trọng: annotation processor thường được biên dịch và chạy **trong môi trường công cụ**, không phải trong module ứng dụng vừa được biên dịch. Nó có dependencies và processor path riêng.

### 1.1. Các vòng xử lý

`AbstractProcessor.process(Set<? extends TypeElement>, RoundEnvironment)` có thể được gọi nhiều lần:

1. Processor được compiler tìm và khởi tạo một lần trong một lượt chạy.
2. Mỗi round có root elements và tập annotation type thích hợp với round đó.
3. Nếu processor tạo source/class qua `Filer`, compiler có thể tạo round tiếp theo để xử lý file sinh ra.
4. Cuối cùng, processor được gọi với `roundEnv.processingOver() == true`. Ở vòng cuối không nên tiếp tục tạo source để trông chờ vòng mới.
5. `process(...)` trả `true` nghĩa là processor **claim** các annotation mà nó được yêu cầu xử lý; `false` nghĩa không claim chúng. Giá trị này không có nghĩa biên dịch thành công/thất bại.

Trong processor phát sinh mã, phải xử lý trường hợp file đã tạo để không gọi `Filer.createSourceFile` trùng lặp. Với processor chỉ kiểm tra metadata, có thể dùng biến `emitted` để tránh báo cùng thông tin qua nhiều round.

## 2. ModuleElement: module cũng là một phần tử của chương trình

Java 9 bổ sung `javax.lang.model.element.ModuleElement`, biểu diễn **module** trong mô hình khai báo. Các module có thể xuất phát từ `module-info.java`, mô hình của automatic module hoặc unnamed module (tùy môi trường).

| API | Ý nghĩa |
| --- | --- |
| `module.getKind()` | `ElementKind.MODULE` |
| `module.getQualifiedName()` | Tên đầy đủ của named module, ví dụ `demo.module` |
| `module.getSimpleName()` | Tên đơn giản của module theo mô hình element |
| `module.isUnnamed()` | Có phải unnamed module hay không |
| `module.isOpen()` | Có phải `open module` không |
| `module.getDirectives()` | Các module directive đã được mô hình hóa |
| `module.getEnclosedElements()` | Các package nằm trong module |
| `module.getEnclosingElement()` | Trả `null`: module không nằm bên trong element khác |
| `module.getAnnotationMirrors()` | Các annotation có trên khai báo module, khi có |
| `module.asType()` | Pseudo-type biểu diễn module trong mô hình kiểu; không phải class runtime |

Điểm cần phân biệt: `module.getEnclosedElements()` trả các **package**, không phải danh sách trực tiếp tất cả class nằm bên trong module. Để tìm một type cụ thể, dùng `Elements.getTypeElement(module, qualifiedTypeName)`.

### 2.1. Lấy ModuleElement bằng Elements

Trong một processor có `processingEnv`:

```java
Elements elements = processingEnv.getElementUtils();

ModuleElement module = elements.getModuleElement("demo.module");
if (module == null) {
    // Module không có trong môi trường xử lý hiện tại.
    return false;
}

TypeElement service =
        elements.getTypeElement(module, "demo.api.Greeter");
if (service != null) {
    ModuleElement owner = elements.getModuleOf(service);
    // owner chính là module của demo.api.Greeter.
}
```

Đây là **mảnh mã trong phương thức `process`**, cần import `javax.lang.model.util.Elements` và `javax.lang.model.element.*`; không phải chương trình Java độc lập.

Các phương thức module-aware quan trọng trên `Elements` (có từ Java 9):

- `getModuleElement(CharSequence name)`: tìm module theo tên; tên rỗng biểu diễn unnamed module; có thể trả `null`.
- `getAllModuleElements()`: lấy tập module **được biết trong môi trường xử lý hiện tại**; không phải luôn là toàn bộ module có trên ổ đĩa.
- `getModuleOf(Element element)`: lấy module sở hữu một element; có thể trả `null` trong môi trường không có module.
- `getTypeElement(ModuleElement module, CharSequence name)`: tìm type trong module chỉ định, tránh nhầm tên class giống nhau ở các module.
- `getPackageElement(ModuleElement module, CharSequence name)`: tìm package trong module chỉ định.
- `isAutomaticModule(ModuleElement module)`: kiểm tra automatic module qua model utility.

Cần kiểm tra `null` thay vì mặc định mọi processor đều chạy trong named module. Nếu đang biên dịch code ở classpath, mô hình có thể dùng unnamed module; nếu công cụ được cấu hình theo source version không có module, một số API module-aware không áp dụng.

### 2.2. ModuleElement khác java.lang.Module

| `javax.lang.model.element.ModuleElement` | `java.lang.Module` |
| --- | --- |
| Tồn tại trong API compiler/annotation processing (`java.compiler`) | Tồn tại trong API runtime (`java.base`) |
| Mô hình các khai báo và directive đang được compiler xử lý | Mô tả module đã được định nghĩa trong JVM/module layer |
| Dùng `getDirectives`, `getAnnotationMirrors`, `Elements.getModuleOf` | Dùng `Class.getModule`, `Module.getName`, `Module.canRead`… |
| Có thể đại diện một module chưa tạo class file | Gắn với module đang hiện diện lúc runtime |
| Không cần nạp class của source vào JVM | Là đối tượng runtime, có thể kiểm tra readability, exports, opens |

**Không dùng reflection để đọc class ứng dụng đang được biên dịch** trong processor; source đó có thể chưa có file `.class` hoặc tồn tại với phiên bản khác trên processor classpath.

## 3. Các directive trong module-info.java

Ví dụ module declaration:

```java
module inventory.core {
    requires java.logging;
    requires transitive java.sql;
    exports inventory.api;
    opens inventory.model to inventory.mapper;
    uses inventory.spi.Codec;
    provides inventory.spi.Codec with inventory.impl.JsonCodec;
}
```

Đây là **minh họa cú pháp**, chưa phải module độc lập có thể biên dịch vì các package/type/module liên quan phải tồn tại. Một `ModuleElement` có thể cung cấp các `ModuleElement.Directive` với `getKind()`:

| DirectiveKind | Dạng source | API để xem chi tiết |
| --- | --- | --- |
| `REQUIRES` | `requires M;`, `requires transitive M;`, `requires static M;` | `RequiresDirective.getDependency()`, `isTransitive()`, `isStatic()` |
| `EXPORTS` | `exports p;` hoặc `exports p to m;` | `ExportsDirective.getPackage()`, `getTargetModules()` |
| `OPENS` | `opens p;` hoặc `opens p to m;` | `OpensDirective.getPackage()`, `getTargetModules()` |
| `USES` | `uses p.Service;` | `UsesDirective.getService()` |
| `PROVIDES` | `provides p.Service with p.Impl;` | `ProvidesDirective.getService()`, `getImplementations()` |

Chẳng hạn:

```java
for (ModuleElement.Directive directive : module.getDirectives()) {
    switch (directive.getKind()) {
        case REQUIRES -> {
            var req = (ModuleElement.RequiresDirective) directive;
            System.out.println(req.getDependency().getQualifiedName());
        }
        case EXPORTS -> {
            var exp = (ModuleElement.ExportsDirective) directive;
            System.out.println(exp.getPackage().getQualifiedName());
        }
        default -> { /* Các directive khác được xử lý khi cần. */ }
    }
}
```

Đây là snippet dùng khi đã có `module` là một `ModuleElement`. `getTargetModules() == null` đối với export/open **không giới hạn đích**; khi có danh sách target là qualified export/open. Các directive có thể bao gồm thông tin compiler bổ sung (ví dụ một dependency bắt buộc), vì vậy không nên giả định số lượng/danh sách luôn trùng đúng từng dòng tác giả gõ. API `Elements.getOrigin(module, directive)` hỗ trợ phân biệt nguồn gốc khi môi trường cung cấp, nhưng nguồn class file có thể không lưu đủ để khẳng định tất cả directive đều được khai báo tường minh.

Các directive thuộc một **module declaration**, không phải annotation type. Để đọc module annotation sử dụng API annotation model, và để đọc `requires/exports` sử dụng `getDirectives()`.

## 4. Annotation áp dụng cho khai báo module

Java 9 bổ sung `ElementType.MODULE` cho annotation declaration. Ví dụ:

```java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.MODULE)
@Retention(RetentionPolicy.CLASS)
public @interface ModuleLabel {
    String value();
}
```

Annotation này có thể được đặt ở đầu `module-info.java`:

```java
@demo.api.ModuleLabel("core")
module demo.module {
    exports demo.api;
    uses demo.api.Greeter;
    provides demo.api.Greeter with demo.impl.GreeterImpl;
}
```

Giá trị của `@Target(ElementType.MODULE)` nghĩa là annotation này có thể áp dụng lên **khai báo module**, không phải lên mọi class trong module. `RetentionPolicy.CLASS` cho phép annotation đi vào class file phù hợp, nhưng processor đọc annotation ngay từ compiler model; không cần có runtime retention.

Trong một processor, `module.getAnnotationMirrors()` trả về các `AnnotationMirror` đang được mô hình hóa. Để nhận diện một annotation cụ thể, nên so sánh tên qualified của `AnnotationMirror.getAnnotationType().asElement()` hoặc tra `TypeElement`; dùng `Elements.getElementValuesWithDefaults(...)` để đọc giá trị kể cả default. Hạn chế dùng `module.getAnnotation(ModuleLabel.class)` nếu annotation type của ứng dụng không có trên classpath của processor.

`RoundEnvironment.getRootElements()` có thể chứa `ModuleElement` khi compiler xử lý `module-info.java`, bên cạnh các `TypeElement` và `PackageElement`. Không tự giả định root elements **luôn chỉ có class** hoặc luôn chứa **tất cả module** nhìn thấy trên module path.

## 5. Ví dụ hoàn chỉnh Java 17+: annotation processor đọc thông tin module

Ví dụ này đã được chạy bằng `javac` trên OpenJDK 24 với `--release 17`. Nó tổ chức **processor riêng với source module**: processor được biên dịch vào classpath của công cụ, còn module `demo.module` là đầu vào được biên dịch. Processor đọc tên module, annotation, `exports`, `uses`, `provides` và module sở hữu type `Greeter`.

Cấu trúc file trước khi chạy:

```text
module-audit/
├── tools/
│   └── demo/tools/ModuleAuditProcessor.java
├── src/
│   └── demo.module/
│       ├── module-info.java
│       ├── demo/api/ModuleLabel.java
│       ├── demo/api/Greeter.java
│       └── demo/impl/GreeterImpl.java
└── out/
    ├── processor/
    └── modules/
```

### 5.1. Module annotation — src/demo.module/demo/api/ModuleLabel.java

```java
package demo.api;

import java.lang.annotation.Target;
import java.lang.annotation.Retention;
import java.lang.annotation.ElementType;
import java.lang.annotation.RetentionPolicy;

@Target(ElementType.MODULE)
@Retention(RetentionPolicy.CLASS)
public @interface ModuleLabel {
    String value();
}
```

### 5.2. API/service — src/demo.module/demo/api/Greeter.java

```java
package demo.api;

public interface Greeter {
    String hello();
}
```

### 5.3. Service implementation — src/demo.module/demo/impl/GreeterImpl.java

```java
package demo.impl;

public final class GreeterImpl implements demo.api.Greeter {
    @Override
    public String hello() {
        return "Hello";
    }
}
```

### 5.4. Module declaration — src/demo.module/module-info.java

```java
@demo.api.ModuleLabel("core")
module demo.module {
    exports demo.api;
    uses demo.api.Greeter;
    provides demo.api.Greeter with demo.impl.GreeterImpl;
}
```

### 5.5. Processor — tools/demo/tools/ModuleAuditProcessor.java

```java
package demo.tools;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.ModuleElement;
import javax.lang.model.element.TypeElement;

@SupportedAnnotationTypes("*")
public final class ModuleAuditProcessor extends AbstractProcessor {
    private boolean emitted;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        if (round.processingOver() || emitted) {
            return false;
        }

        ModuleElement module = processingEnv.getElementUtils()
                .getModuleElement("demo.module");
        if (module == null) {
            return false;
        }
        emitted = true;

        System.out.println("module=" + module.getQualifiedName());
        System.out.println("kind=" + module.getKind());
        System.out.println("unnamed=" + module.isUnnamed());
        System.out.println("annotations="
                + module.getAnnotationMirrors().size());

        for (ModuleElement.Directive directive : module.getDirectives()) {
            switch (directive.getKind()) {
                case EXPORTS -> System.out.println("exports=" +
                        ((ModuleElement.ExportsDirective) directive)
                                .getPackage().getQualifiedName());

                case USES -> System.out.println("uses=" +
                        ((ModuleElement.UsesDirective) directive)
                                .getService().getQualifiedName());

                case PROVIDES -> System.out.println("provides=" +
                        ((ModuleElement.ProvidesDirective) directive)
                                .getService().getQualifiedName());

                default -> { }
            }
        }

        TypeElement type = processingEnv.getElementUtils()
                .getTypeElement(module, "demo.api.Greeter");
        if (type != null) {
            System.out.println("type-module="
                    + processingEnv.getElementUtils()
                            .getModuleOf(type).getQualifiedName());
        }
        return false;
    }
}
```

**Vì sao code này đúng với processor module-aware?**

- `@SupportedAnnotationTypes("*")` cho phép processor nhận tất cả annotation types trong phạm vi công cụ. Trong sản phẩm thật, ưu tiên danh sách annotation cụ thể để giảm tương tác ngoài ý muốn.
- `getSupportedSourceVersion()` trả `SourceVersion.latestSupported()` để ví dụ không cảnh báo vì một annotation `@SupportedSourceVersion(RELEASE_9)` bị giữ nguyên khi chạy JDK mới. Đây là lựa chọn cho ví dụ đọc API chung; processor sản xuất phải kiểm thử và công bố các source versions thực sự hỗ trợ.
- `round.processingOver()` và biến `emitted` ngăn in trùng ở round cuối hoặc các round sau.
- `getModuleElement("demo.module")` lấy module **trong môi trường biên dịch**. `getTypeElement(module, "...")` tìm type trong chính module đó.
- `getDirectives()` có thể có `requires java.base`/directive khác do công cụ mô hình hóa; ví dụ chỉ in ba directive đã chọn để kết quả minh bạch.
- `getAnnotationMirrors()` đếm annotation hiện diện trên khai báo module; số `1` trong ví dụ này đến từ `@ModuleLabel("core")`.

### 5.6. Biên dịch và chạy processor

Mở terminal tại thư mục `module-audit`. Tạo sẵn hai thư mục `out/processor` và `out/modules` nếu chưa có. Trên Bash:

```sh
mkdir -p out/processor out/modules
```

Trên PowerShell, thao tác tương đương là `New-Item -ItemType Directory -Force -Path out/processor,out/modules`.

Biên dịch processor:

```sh
javac --release 17 -d out/processor tools/demo/tools/ModuleAuditProcessor.java
```

Chạy annotation processing cho module:

```sh
javac --release 17 -proc:only --module-source-path src -processorpath out/processor -processor demo.tools.ModuleAuditProcessor -d out/modules -m demo.module
```

Đầu ra chính xác đã kiểm chứng với OpenJDK 24:

```text
module=demo.module
kind=MODULE
unnamed=false
annotations=1
exports=demo.api
uses=demo.api.Greeter
provides=demo.api.Greeter
type-module=demo.module
```

`-proc:only` khiến `javac` chạy processor nhưng **không tiếp tục biên dịch class file ứng dụng**. Dùng để học, xác minh hoặc chạy riêng tác vụ sinh mã. Nếu muốn biên dịch module ra class, chạy một lệnh biên dịch bình thường và cấu hình processor tường minh (hoặc biên dịch riêng sau khi đã tạo mã nguồn cần thiết). Ví dụ:

```sh
javac --release 17 --module-source-path src -d out/modules -m demo.module
```

Ở lệnh thứ ba này không có `-processor` và không yêu cầu chạy processor; nó chỉ biên dịch các source vào `out/modules`. Để kiểm chứng annotation processing trong build thật, cấu hình processor rõ ràng, không chỉ trông chờ tự động dò trên classpath.

**Lưu ý về stdout:** ví dụ cố ý dùng `System.out.println` để kết quả dễ đối chiếu. Processor sản xuất nên dùng `processingEnv.getMessager().printMessage(Diagnostic.Kind.NOTE/WARNING/ERROR, ...)` để compiler/build tool quản lý diagnostics và liên kết với element. Cách hiển thị prefix và thứ tự của diagnostic sẽ phụ thuộc compiler/build tool.

## 6. Kích hoạt processor rõ ràng trên JDK hiện đại

Một thay đổi quan trọng: **từ JDK 23, `javac` không còn mặc định tự chạy annotation processor chỉ vì tìm thấy processor trên classpath mà không có lựa chọn processing tường minh**. Điều này giúp giảm việc vô tình thực thi mã nằm trong dependencies khi build.

Những lựa chọn hiện hành:

| Tùy chọn `javac` | Công dụng |
| --- | --- |
| `-processor demo.tools.ModuleAuditProcessor` | Chọn đúng processor sẽ chạy bằng tên class |
| `-processorpath path` hoặc `--processor-path path` | Đường dẫn classpath chứa processor và dependencies |
| `--processor-module-path path` | Đường dẫn module dùng để khám phá processor đóng gói thành named modules |
| `-proc:only` | Chỉ chạy processing, không tiếp tục biên dịch |
| `-proc:none` | Tắt annotation processing |
| `-proc:full` | Chạy processing và compilation (các JDK có hỗ trợ lựa chọn này) |
| `-XprintRounds` / `-XprintProcessorInfo` | In thông tin vòng xử lý và các processor, hữu ích để debug |

Lệnh ví dụ đã dùng cả `-processorpath` và `-processor` nên **không phụ thuộc vào cơ chế tự phát hiện ngầm**, hoạt động trên JDK 17 và JDK mới.

**Classpath processor và named-module processor:**

- Processor trên classpath: compile vào JAR/thư mục riêng, cung cấp `META-INF/services/javax.annotation.processing.Processor` nếu muốn service discovery, hoặc gọi tường minh qua `-processor` như ví dụ.
- Processor là **named module**: module processor cần `requires java.compiler;` và `provides javax.annotation.processing.Processor with your.ProcessorClass;`, đồng thời đặt đúng trên `--processor-module-path` để discovery theo module.
- `--module-path` chủ yếu dành cho **module dependencies của source đang được biên dịch**; nó không thay thế `--processor-module-path` hay `-processorpath`. `--module-source-path` lại dùng để tổ chức **nguồn** của các module được biên dịch.
- Công cụ build như Gradle/Maven/IDE có cơ chế cấu hình annotation processors riêng. Cần bảo đảm processor path được khai báo chính xác cho compilation task, nhất là sau nâng JDK.

Không tự thêm processor JAR chưa tin cậy vào processor path: annotation processor thực thi mã Java ở build time, có quyền hạn của tiến trình xây dựng. Nên dùng dependencies đã được rà soát, khóa phiên bản và chạy build trong môi trường giới hạn phù hợp.

## 7. Truy xuất module và annotation khi biên dịch nhiều module

Trong multi-module compilation, có thể có nhiều package/type cùng tên thuộc các module khác nhau; vì vậy:

```java
ModuleElement one =
        processingEnv.getElementUtils().getModuleElement("billing.api");
ModuleElement two =
        processingEnv.getElementUtils().getModuleElement("reporting.api");

TypeElement typeInBilling = one == null ? null
        : processingEnv.getElementUtils()
                .getTypeElement(one, "example.api.Result");

TypeElement typeInReporting = two == null ? null
        : processingEnv.getElementUtils()
                .getTypeElement(two, "example.api.Result");
```

Đây là **mảnh mã minh họa**, các tên module/type giả định phải tồn tại trong môi trường compile. `getTypeElement(module, name)` cho phép định vị chính xác type theo module; `Elements.getTypeElement(name)` không có module có thể không xác định duy nhất và trả `null`.

Khi nhận element từ `round.getRootElements()` hoặc `round.getElementsAnnotatedWith(type)`, kiểm tra `element.getKind() == ElementKind.MODULE` trước khi ép kiểu thành `ModuleElement`. Module annotation có thể nằm trong `module-info.java` và xuất hiện ở root, trong khi một số module chỉ truy vấn được qua `getModuleElement`.

Khi xử lý `requires`, `exports` và `opens`, hãy phân biệt **mô hình directive compile time** với việc JVM thực sự cho đọc module hoặc mở package lúc runtime. `exports` liên quan truy cập public types; `opens` liên quan deep reflection. Chỉ nhìn `getDirectives()` trong một compilation không cho biết đầy đủ các tùy chọn runtime như `--add-opens` được truyền lúc chạy.

## 8. Sinh source file đúng module bằng Filer

`ProcessingEnvironment.getFiler()` cho phép processor tạo một source, class hoặc resource do compiler quản lý. Trong môi trường module, `Filer.createSourceFile` hỗ trợ **tiền tố tên module và dấu `/`**:

```java
JavaFileObject generated = processingEnv.getFiler()
        .createSourceFile(
                "demo.module/demo.generated.Generated",
                module);

try (Writer out = generated.openWriter()) {
    out.write("""
            package demo.generated;
            public final class Generated {
                public static String value() { return "generated"; }
            }
            """);
}
```

Đây là **mảnh minh họa thêm vào processor**, cần import `javax.tools.JavaFileObject` và `java.io.Writer`, đồng thời `module` là `ModuleElement` tìm được. Nó **không nằm trong processor `ModuleAuditProcessor` đã chạy ở mục 5** nên không xuất hiện trong output của ví dụ chính.

Giải thích:

1. `"demo.module/demo.generated.Generated"` chỉ rõ đích là module `demo.module`, class `demo.generated.Generated`. Khi không có tiền tố module và compiler không suy ra được module duy nhất, `Filer` có thể ném `FilerException`.
2. Tham số `module` là **originating element** giúp build tooling hiểu source sinh ra gắn với đơn vị input nào. Với class/package, cũng truyền originating elements phù hợp.
3. Một file cùng đường dẫn chỉ được tạo **một lần trong một lượt processing**. Tạo lại ở round sau sẽ ném `FilerException`. Không tạo file có cùng tên với source input đã tồn tại, không tìm cách ghi đè `module-info.java`.
4. Nội dung file tạo qua `Filer` trở thành đầu vào cho round tiếp theo khi writer/stream được đóng. `-proc:only` không tạo class cuối cùng; muốn chạy class được sinh ra phải có compilation phù hợp.
5. Trong multi-module processing, đặt module prefix rõ ràng hoặc xác minh module inference. Tạo source vào package không tên trong named module là không hợp lệ.

Với resource, `Filer.createResource(location, moduleAndPkg, relativeName, ...)` cũng hỗ trợ module prefix trong tham số `moduleAndPkg`, ví dụ `"demo.module/demo.generated"`. Đây là một trường hợp khác với việc đưa tên module vào tên file nguồn.

## 9. Khi nào nên dùng embedded compiler API?

Chủ đề **công cụ nhúng** cũng áp dụng khi ứng dụng Java gọi compiler trực tiếp thay vì chạy binary `javac`. API chuẩn hiện tại:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(null, null, null)) {

    // files là Iterable<? extends JavaFileObject> chứa input sources.
    JavaCompiler.CompilationTask task = compiler.getTask(
            null, manager, null,
            java.util.List.of("--release", "17", "-proc:only"),
            null, files);

    task.setProcessors(java.util.List.of(new ModuleAuditProcessor()));
    boolean ok = task.call();
}
```

Đây là **mảnh minh họa**, chưa phải chương trình độc lập: biến `files` cần được tạo từ `manager.getJavaFileObjectsFromPaths(...)` hay `SimpleJavaFileObject`, và import `javax.tools.*` cùng processor class. Nếu có named module source, compiler task phải được cung cấp **module-aware file manager/configuration** phù hợp, chẳng hạn `--module-source-path` và module output. Trong code tích hợp, kiểm tra `compiler == null` (có thể xảy ra khi runtime không có system compiler), và gọi `task.setProcessors(...)` **trước** `task.call()`.

Ưu điểm: application có thể dùng một `JavaCompiler`, truyền processors cụ thể, thu diagnostics qua `DiagnosticCollector`, quản lý source/output có kiểm soát mà không khởi động process ngoài. Nhưng processor vẫn là code thực thi lúc build; nên tách input/runtime và cấp quyền thích hợp.

**Giới hạn:** `javax.lang.model` mô hình hóa khai báo Java. Nếu công việc đòi hỏi phân tích chi tiết thân method, flow hoặc cú pháp statement/expression, cần AST/compiler Tree API phù hợp (`com.sun.source.*` công khai trong `jdk.compiler`), không suy diễn những thông tin đó từ `TypeElement` hay `ModuleElement`.

## 10. Lỗi thường gặp và xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Processor không chạy trên JDK mới | Chưa cấu hình processing tường minh; từ JDK 23 đổi mặc định | Dùng `-processor` cùng processor path hoặc cấu hình tool tương đương |
| `ClassNotFoundException` khi chạy processor | Processor/dependency không nằm trên processor path | Kiểm tra `-processorpath`/`--processor-module-path` và tên class |
| `getModuleElement(...) == null` | Sai tên, module không có trong compilation environment, hoặc môi trường không có module | Xác minh module source path, module name, current round và input |
| Ép kiểu root element sang `TypeElement` bị lỗi | Root là `ModuleElement` hoặc `PackageElement` | Kiểm tra `getKind()` trước khi cast |
| Type không được tìm thấy | Cùng tên class ở nhiều module hoặc module chưa được nhìn thấy | Dùng `getTypeElement(module, qualifiedName)` và kiểm tra `null` |
| Processor xuất hiện output lặp | `process` được gọi qua nhiều round | Kiểm tra `processingOver()`, theo dõi source đã xử lý |
| `FilerException: Attempt to recreate a file` | Tạo cùng file nhiều lần hoặc trùng source đầu vào | Đảm bảo mỗi tên file chỉ tạo một lần trong một compiler run |
| Không biết đặt source được sinh ra vào module nào | Compilation có nhiều module, không suy luận được đích | Thêm prefix `module/name` ở `createSourceFile` |
| Processor sinh file nhưng không thấy class | Biên dịch đang ở `-proc:only` hoặc thiếu compilation tiếp theo | Biên dịch các source cần thiết sau processing |
| `@Target(MODULE)` không được nhận diện | Annotation hoặc module source chưa vào compilation | Kiểm tra `module-info.java`, source path, target và annotation name |
| Dự án có named module nhưng processor bị đặt nhầm trên module path | Đã trộn đường dẫn processor với module dependencies | Tách processor classpath/module path và application module path |

## 11. Câu hỏi tự kiểm tra

1. Vì sao `ModuleElement` thuộc `java.compiler` nhưng `java.lang.Module` thuộc `java.base`? Trường hợp nào dùng cái nào?
2. Trong processor, làm cách nào nhận biết root là module thay vì class? Vì sao `RoundEnvironment.getRootElements()` không đảm bảo là toàn bộ module?
3. Nếu hai module có type cùng qualified name, làm sao tìm đúng `TypeElement` thuộc module mong muốn?
4. `RequiresDirective` và `ExportsDirective` cho biết những thông tin gì? `getTargetModules() == null` ở unqualified export có nghĩa gì?
5. Sau nâng lên JDK 23+, compiler tìm thấy processor JAR trên classpath nhưng không chạy. Cần cấu hình gì?
6. Tại sao `Filer.createSourceFile("demo.module/demo.generated.Generated", module)` phù hợp hơn tên source không có module prefix trong môi trường nhiều module?
7. Vì sao processor chỉ đọc module metadata vẫn có thể chạy trong `-proc:only` mà ứng dụng chưa có class file?
8. Vì sao `process(...) == false` không nhất thiết là processor báo lỗi? Có cách nào xuất lỗi compiler đúng chuẩn?

## 12. Checklist thực tế

- [ ] Bám theo API công khai `javax.annotation.processing` / `javax.lang.model` / `javax.tools` và source version đã kiểm thử.
- [ ] Xác định processor được chạy tường minh trên JDK/build tool đang sử dụng.
- [ ] Phân biệt processor path với module path của ứng dụng, cấu hình file/module source và output.
- [ ] Đọc `ModuleElement` bằng API phù hợp; xử lý `null`, unnamed/automatic module và các loại root element khác.
- [ ] Dùng `getDirectives()` để duyệt `requires/exports/opens/uses/provides` theo `DirectiveKind`.
- [ ] Với type/package, ưu tiên overload có `ModuleElement` trong môi trường nhiều module.
- [ ] Nếu sinh source, chỉ tạo một lần, dùng module prefix/originating elements đúng cách và kiểm tra các round.
- [ ] Dùng `Messager` cho diagnostics; kiểm thử processor bằng một module source độc lập.
- [ ] Sau nâng JDK, chạy lại kiểm thử processor và rà soát thay đổi `javac` liên quan đến annotation processing.

## Tài liệu chính thức

- [Java SE 25 — ModuleElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ModuleElement.html)
- [Java SE 25 — Elements (các API module-aware)](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/util/Elements.html)
- [Java SE 25 — javax.annotation.processing.Processor](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Processor.html)
- [Java SE 25 — RoundEnvironment](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Java SE 25 — Filer](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [OpenJDK javac tool guide](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md)
- [JDK 23 Release Notes — annotation processing disabled by default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)

Khi triển khai trên JDK hoặc build tool khác, xem tài liệu của **đúng phiên bản compiler đang chạy**, đặc biệt các lựa chọn kích hoạt processor và hỗ trợ module. Không sao chép các mặc định dò processor của JDK cũ vào quy trình build hiện nay.
