# ModuleElement trong mô hình phần tử ngôn ngữ Java (Java 9+)

Trong các công cụ nhúng, annotation processor, trình phân tích mã nguồn và công cụ kiểm tra quy tắc kiến trúc của Java, ta thường cần **đọc cấu trúc của một module ở thời điểm biên dịch**, thay vì tải class rồi suy luận ở runtime. Từ Java 9, Java Platform Module System (JPMS) giới thiệu `module-info.java` và API **`javax.lang.model.element.ModuleElement`** để biểu diễn một module trong **mô hình phần tử ngôn ngữ** (language model).

`ModuleElement` nằm trong module chuẩn **`java.compiler`** của JDK, mở rộng `Element` và `QualifiedNameable`. Nó cho phép lấy tên module, biết module có phải unnamed/open hay không, xem các package bên trong, và đặc biệt duyệt các directive `requires`, `exports`, `opens`, `uses` và `provides`. Công cụ có thể truy vấn model này từ `ProcessingEnvironment.getElementUtils()` khi xử lý annotation, hoặc từ `JavacTask.getElements()` khi nhúng trình biên dịch `javac`.

Bài này thuộc chủ đề **Công cụ nhúng**. Các API được mô tả là những API còn được hỗ trợ trong Java hiện đại; các ví dụ dùng **Java 17+**, biên dịch và chạy không cần thư viện ngoài. Chúng minh họa hai luồng thực tế: **annotation processor quan sát module khi `javac` biên dịch** và **một ứng dụng Java nhúng compiler để phân tích module**.

## 1. Chọn đúng mô hình: ModuleElement, Module và ModuleDescriptor

Ba API có tên gần nhau nhưng giải quyết bài toán khác nhau:

| Đối tượng | Package/module chứa API | Thời điểm sử dụng | Thông tin nổi bật |
| --- | --- | --- | --- |
| `ModuleElement` | `javax.lang.model.element` / `java.compiler` | Biên dịch, annotation processing, công cụ phân tích ngôn ngữ | Phần tử module, tên, package, các directive dưới dạng những phần tử có cấu trúc |
| `Module` | `java.lang` / `java.base` | Runtime | Module mà class đang thuộc về, khả năng đọc/exports/opens tại runtime |
| `ModuleDescriptor` | `java.lang.module` / `java.base` | Đọc metadata descriptor ở runtime hoặc từ module artifacts | Mô tả module dưới dạng descriptor, các tập requires/exports/opens/uses/provides |

**Không lấy `Class.getModule()` để thay cho `ModuleElement` trong annotation processor.** `Class.getModule()` làm việc với lớp được JVM tải; còn `ModuleElement` mô hình hóa khai báo chương trình mà compiler nhìn thấy, kể cả source đang biên dịch và các module có thể được phân giải từ compiler environment. Công cụ phân tích mã nguồn thường chưa có class được tải để gọi reflection.

Ví dụ cùng một `module-info.java`:

```java
module com.example.widget {
    requires java.logging;
    exports com.example.widget.api;
    opens com.example.widget.impl;
    uses com.example.widget.api.Greeter;
    provides com.example.widget.api.Greeter
            with com.example.widget.impl.SimpleGreeter;
}
```

Tệp này không cần dùng reflection để đọc bằng `ModuleElement`. Compiler cung cấp từng directive ở dạng đối tượng có kiểu, thay vì buộc công cụ tự dùng biểu thức chính quy để phân tích text của `module-info.java`.

## 2. ModuleElement nằm ở đâu trong Language Model?

Hệ `javax.lang.model` mô hình hóa **chương trình Java ở mức ngôn ngữ**, không phải danh sách đối tượng runtime. Các interface quan trọng:

- `Element`: phần tử chương trình tổng quát như module, package, type, method, field; có `getKind()`, `getSimpleName()`, `getEnclosedElements()` và `accept(...)`.
- `ModuleElement`: phần tử có `ElementKind.MODULE`, gồm tên module, package và directive.
- `PackageElement`: package trong một module; `getEnclosedElements()` của package chứa các kiểu top-level thuộc package.
- `TypeElement`: kiểu được khai báo (class, interface, enum, record...); không nên giả định mọi kiểu đều là `CLASS`.
- `ExecutableElement`/`VariableElement`: phương thức, constructor, field, tham số v.v.
- `TypeMirror`: biểu diễn **kiểu** trong hệ thống type của compiler. `ModuleElement.asType()` là một **pseudo-type**, không phải kiểu Java dùng để tạo đối tượng module.
- `Elements` trong `javax.lang.model.util`: tiện ích truy vấn tên, module sở hữu phần tử, package và type.

Sơ đồ liên hệ phổ biến:

```text
ModuleElement: com.example.widget
    │
    ├── getEnclosedElements() ──> PackageElement: com.example.widget.api
    │                                  │
    │                                  └── TypeElement: Greeter, Main
    │
    ├── getEnclosedElements() ──> PackageElement: com.example.widget.impl
    │                                  │
    │                                  └── TypeElement: SimpleGreeter
    │
    └── getDirectives() ────────> Requires / Exports / Opens / Uses / Provides
```

**Điểm quan trọng:** package con không tự động là phần tử con trực tiếp của package cha theo cách duyệt cây thư mục. `ModuleElement.getEnclosedElements()` trả về **các package mà model nhận biết trong module**; `PackageElement.getEnclosedElements()` mới trả về các kiểu top-level. Muốn lấy module của một type, dùng `Elements.getModuleOf(typeElement)`; không suy đoán module từ tiền tố package, vì cùng tên package có thể tồn tại trong những môi trường module khác nhau.

Các phần tử được compiler cung cấp phụ thuộc **ngữ cảnh phân giải và những gì compiler nhìn thấy**. Đừng coi danh sách phần tử của một lần compile là bộ kiểm kê tuyệt đối mọi class trong tất cả JAR/module có trên máy.

## 3. Các phương thức quan trọng của ModuleElement

| API | Giá trị/ý nghĩa | Cách hiểu đúng |
| --- | --- | --- |
| `getKind()` | `ElementKind.MODULE` | Dùng để kiểm tra loại phần tử khi duyệt language model |
| `getQualifiedName()` | `Name` đầy đủ, ví dụ `com.example.widget` | Dùng để hiển thị và định danh; với unnamed module là tên rỗng |
| `getSimpleName()` | Tên cuối, ví dụ `widget` | Không phải định danh duy nhất; với unnamed module là tên rỗng |
| `isUnnamed()` | `true` nếu đại diện unnamed module | Phân biệt mã trên classpath với named module theo cấu hình tool |
| `isOpen()` | `true` nếu module là `open module` | **Không** đồng nghĩa “module có một directive `opens p`” |
| `getEnclosedElements()` | `List<? extends Element>` các package trong module | Lọc `ElementKind.PACKAGE` để có danh sách package |
| `getDirectives()` | Danh sách `ModuleElement.Directive` | Đọc các khai báo module dưới dạng cấu trúc, không parse text |
| `getEnclosingElement()` | `null` | Module là phần tử cấp cao nhất trong mô hình |
| `asType()` | Pseudo-type của module | Không dùng như một `Class<?>` hoặc một type có thể instantiate |
| `accept(ElementVisitor, arg)` | Gọi visitor phù hợp cho phần tử module | Phù hợp khi viết analyzer xử lý nhiều loại `Element` |

**Ví dụ về tên:** `com.example.widget` có `getSimpleName() = "widget"`, không phải `"com.example.widget"`. `isOpen()` chỉ phản ánh khai báo **`open module ...`**, nên trong ví dụ có một directive `opens com.example.widget.impl;` nhưng `isOpen()` vẫn là `false`.

**Unnamed module** có thể được model tạo ra từ mã classpath hoặc môi trường không có khai báo module tường minh; khi `isUnnamed()==true`, đừng kỳ vọng có tệp `module-info.java` hay tên định danh thông thường.

**Automatic module** là một trường hợp khác: nó **có tên module** dù không khai báo `module-info.java` tường minh. Vì vậy “không thấy tệp module-info” không đủ để kết luận module là unnamed. API tiện ích `Elements.isAutomaticModule(module)` có thể hỗ trợ phân loại trong JDK hiện hành; hãy kiểm tra provider/môi trường thực tế.

## 4. Lấy ModuleElement đúng cách

### 4.1. Bên trong annotation processor

Trong `AbstractProcessor.process(...)`, đối tượng `processingEnv` được compiler truyền vào. Có thể tìm module bằng tên:

```java
Elements elements = processingEnv.getElementUtils();
ModuleElement module = elements.getModuleElement("com.example.widget");

if (module != null) {
    System.out.println(module.getQualifiedName());
}
```

Đây là **mảnh code tích hợp**, không phải chương trình chạy độc lập. Nó thuộc lớp `AbstractProcessor` đã được `javac` khởi tạo và có các import:

```java
import javax.lang.model.element.ModuleElement;
import javax.lang.model.util.Elements;
```

Các tiện ích liên quan:

- `elements.getModuleElement("com.example.widget")`: lấy module có tên đó, hoặc `null` nếu không thể tìm thấy trong environment.
- `elements.getModuleOf(element)`: tìm module chứa một `Element`, hữu ích khi analyzer xuất phát từ type/package mà chưa biết module.
- `elements.getTypeElement(module, "com.example.widget.api.Greeter")`: tìm type với ngữ cảnh module xác định, tránh mơ hồ trong môi trường nhiều module.
- `elements.getPackageElement(module, "com.example.widget.api")`: lấy package trong module cần xét.
- `elements.getAllModuleElements()`: lấy các module hiện có trong environment, **không** đồng nghĩa tất cả module trên hệ thống.

Cần xử lý `null` khi module/type không hiện diện. Với processor chạy qua nhiều processing round, chỉ xuất báo cáo một lần nếu mục tiêu là tổng hợp, và dừng ở `roundEnv.processingOver()` khi thích hợp. Không giả định kết quả duyệt các module có thứ tự xác định nếu API trả về collection không cam kết thứ tự.

### 4.2. Bên trong công cụ nhúng JavaCompiler

Trong ứng dụng phân tích source sử dụng compiler của JDK, thường có:

```text
ToolProvider.getSystemJavaCompiler()
            │
            └── JavaCompiler.getTask(...)
                           │ (javac implementation)
                           ▼
                      JavacTask
                           │
                           ├── parse()
                           ├── analyze()
                           └── getElements()
                                 │
                                 └── getModuleElement("...")
```

`ToolProvider.getSystemJavaCompiler()` thuộc `java.compiler`. Nó có thể trả `null` khi runtime image không chứa Java compiler, nên chạy ví dụ bằng **JDK đầy đủ**, không phải giả định mọi runtime đều có compiler.

`com.sun.source.util.JavacTask` là **API công khai của module `jdk.compiler`**, truy cập các chức năng riêng của `javac`: `parse()`, `analyze()`, `getElements()`. Khi phân tích qua công cụ nhúng, cần cấu hình đúng source/module path và hoàn tất bước phân tích thích hợp **trước khi yêu cầu mô hình phần tử**, tránh lỗi truy vấn khi compiler chưa có environment.

Đây không phải interface `javax.lang.model` thay thế `javac`: `ModuleElement` là **dữ liệu mô hình**, còn `JavacTask` là **cổng chạy và điều phối compiler**.

## 5. Mô hình hóa 5 loại directive: không cần tự phân tích chuỗi

`ModuleElement.getDirectives()` trả `List<? extends ModuleElement.Directive>`. Một directive có `getKind()` và có thể được xử lý bằng `DirectiveVisitor`. Với Java 17+, dùng `switch (directive.getKind())` cũng rõ ràng và an toàn nếu ép sang đúng sub-interface tương ứng.

| `DirectiveKind` | Cú pháp trong module-info | Giao diện đại diện | Phương thức quan trọng |
| --- | --- | --- | --- |
| `REQUIRES` | `requires m;`, `requires transitive m;`, `requires static m;` | `RequiresDirective` | `getDependency()` trả `ModuleElement`, `isTransitive()`, `isStatic()` |
| `EXPORTS` | `exports p;`, `exports p to m1,m2;` | `ExportsDirective` | `getPackage()`, `getTargetModules()` |
| `OPENS` | `opens p;`, `opens p to m1,m2;` | `OpensDirective` | `getPackage()`, `getTargetModules()` |
| `USES` | `uses p.Service;` | `UsesDirective` | `getService()` trả `TypeElement` |
| `PROVIDES` | `provides p.Service with p.Impl;` | `ProvidesDirective` | `getService()`, `getImplementations()` |

Một số chi tiết dễ sai:

1. `RequiresDirective.getDependency()` trả về **module được phụ thuộc**, không phải tên package hay `TypeElement`. `isStatic()` nói về dependency cần khi biên dịch nhưng không bắt buộc lúc chạy, **không** phải modifier `static` của Java method.
2. `RequiresDirective.isTransitive()` liên quan đến khả năng đọc module gián tiếp. Không nhầm với việc “công khai tất cả package” trong module dependency.
3. Với `exports p;`/`opens p;` **không định danh module đích**, `getTargetModules() == null`, nghĩa là phạm vi mở/xuất không giới hạn danh sách tên cụ thể. Với dạng `to m1,m2`, nhận danh sách module đích; **đừng gọi `.size()` trước khi kiểm tra null**.
4. `ExportsDirective` đại diện truy cập kiểu public qua JPMS; `OpensDirective` đại diện **quyền reflective access**, không làm package import được trong code ngoài module như `exports`.
5. `UsesDirective.getService()` trả type dịch vụ; `ProvidesDirective.getImplementations()` trả danh sách **type implementation**, không phải instance của service.
6. `module.getDirectives()` có thể chứa directive mặc định/ngầm định do language model biểu diễn. Ví dụ đã kiểm chứng trên `javac 24` có thêm `requires java.base` dù mã nguồn không viết dòng này. **Không mặc định danh sách API bằng số dòng directive trong file source.**
7. `DirectiveVisitor<R,P>` là lựa chọn phù hợp cho code phân tích cần phân nhánh theo kind ở nhiều phiên bản; `directive.accept(visitor, parameter)` gọi nhánh đúng. Không dựa vào biểu diễn chuỗi `toString()` làm định dạng dữ liệu chuẩn.

### 5.1. exports không đồng nghĩa opens

`exports com.example.widget.api;` cho phép module khác **đọc được** dùng các public types của package `api` theo module readability và quy tắc truy cập Java. `opens com.example.widget.impl;` cho phép reflective access vào package `impl` theo điều kiện của JPMS, nhưng **không biến `impl` thành API compile-time**.

**Lưu ý về bảo mật:** trong ví dụ học dưới đây, `opens com.example.widget.impl;` chỉ nhằm cho processor thấy một `OpensDirective`. Trong ứng dụng production, chỉ `opens` các package thực sự cần reflection, và ưu tiên `opens ... to specific.module;` nếu có thể. `ServiceLoader` **không yêu cầu phải opens toàn package implementation** chỉ để dùng `provides ... with ...`. Tránh mở nội bộ không cần thiết.

## 6. Ví dụ đầy đủ: annotation processor đọc ModuleElement

Ví dụ này dựng một named module `com.example.widget` có cả năm loại directive. Ta viết `ModuleInspector` dưới dạng annotation processor riêng trên **processor classpath**, rồi chạy `javac` để in mô hình module. Cuối cùng chạy chương trình dùng `ServiceLoader` để chứng minh module vẫn hoạt động.

Dùng cấu trúc thư mục:

```text
module-element-demo/
├── processor/
│   └── ModuleInspector.java
└── src/
    └── com.example.widget/
        ├── module-info.java
        └── com/example/widget/
            ├── api/
            │   ├── Greeter.java
            │   └── Main.java
            └── impl/
                └── SimpleGreeter.java
```

### 6.1. Nguồn module

Tệp `src/com.example.widget/module-info.java`:

```java
module com.example.widget {
    requires java.logging;
    exports com.example.widget.api;
    opens com.example.widget.impl;
    uses com.example.widget.api.Greeter;
    provides com.example.widget.api.Greeter
            with com.example.widget.impl.SimpleGreeter;
}
```

Ở đây:

- `requires java.logging` cung cấp một directive `REQUIRES` để quan sát; chương trình minh họa không thực sự dùng logging, nên **ở production hãy loại dependency không cần thiết**.
- `exports ...api` xuất package API cho module consumer.
- `opens ...impl` minh họa `OPENS`, không phải cấu hình bảo mật được khuyến nghị cho mọi dịch vụ.
- `uses ...Greeter` cho phép module sử dụng `ServiceLoader` để tìm service.
- `provides ...Greeter with ...SimpleGreeter` đăng ký implementation cho service đó. `SimpleGreeter` nằm trong package không được export, nhưng module system vẫn có cơ chế dịch vụ được công bố theo descriptor.

Tệp `src/com.example.widget/com/example/widget/api/Greeter.java`:

```java
package com.example.widget.api;

/** A small service contract. */
public interface Greeter {
    String greet(String name);
}
```

Tệp `src/com.example.widget/com/example/widget/impl/SimpleGreeter.java`:

```java
package com.example.widget.impl;

import com.example.widget.api.Greeter;

/** Not exported to other modules. */
public final class SimpleGreeter implements Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Tệp `src/com.example.widget/com/example/widget/api/Main.java`:

```java
package com.example.widget.api;

import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Greeter service = ServiceLoader.load(Greeter.class).findFirst().orElseThrow();
        System.out.println(service.greet("Java"));
    }
}
```

Đây là một chương trình chạy được. Nó dùng `ServiceLoader` tìm `Greeter` dựa vào descriptor; `SimpleGreeter` không cần export ra ngoài để đóng vai trò service provider.

### 6.2. Annotation processor quan sát module

Tệp `processor/ModuleInspector.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ModuleElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.Elements;

@SupportedAnnotationTypes("*")
public final class ModuleInspector extends AbstractProcessor {
    private boolean printed;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (printed || round.processingOver()) {
            return false;
        }
        Elements elements = processingEnv.getElementUtils();
        ModuleElement module = elements.getModuleElement("com.example.widget");
        if (module == null) {
            return false;
        }
        printed = true;

        System.out.println("module=" + module.getQualifiedName());
        System.out.println("simple=" + module.getSimpleName());
        System.out.println("kind=" + module.getKind());
        System.out.println("open=" + module.isOpen());
        System.out.println("unnamed=" + module.isUnnamed());

        List<String> packages = module.getEnclosedElements().stream()
                .filter(e -> e.getKind() == ElementKind.PACKAGE)
                .map(Element::toString).sorted().toList();
        System.out.println("packages=" + String.join(",", packages));

        TypeElement greeter =
                elements.getTypeElement(module, "com.example.widget.api.Greeter");
        System.out.println("typeModule=" + elements.getModuleOf(greeter)
                .getQualifiedName());

        List<String> lines = new ArrayList<>();
        for (ModuleElement.Directive directive : module.getDirectives()) {
            switch (directive.getKind()) {
                case REQUIRES -> {
                    var d = (ModuleElement.RequiresDirective) directive;
                    lines.add("requires=" + d.getDependency().getQualifiedName()
                            + "(transitive=" + d.isTransitive()
                            + ",static=" + d.isStatic() + ")");
                }
                case EXPORTS -> {
                    var d = (ModuleElement.ExportsDirective) directive;
                    lines.add("exports=" + d.getPackage().getQualifiedName()
                            + (d.getTargetModules() == null ? "->ALL" : "->SPECIFIC"));
                }
                case OPENS -> {
                    var d = (ModuleElement.OpensDirective) directive;
                    lines.add("opens=" + d.getPackage().getQualifiedName()
                            + (d.getTargetModules() == null ? "->ALL" : "->SPECIFIC"));
                }
                case USES -> {
                    var d = (ModuleElement.UsesDirective) directive;
                    lines.add("uses=" + d.getService().getQualifiedName());
                }
                case PROVIDES -> {
                    var d = (ModuleElement.ProvidesDirective) directive;
                    String implementations = d.getImplementations().stream()
                            .map(x -> x.getQualifiedName().toString())
                            .collect(Collectors.joining(","));
                    lines.add("provides=" + d.getService().getQualifiedName()
                            + "->" + implementations);
                }
            }
        }
        Collections.sort(lines);
        lines.forEach(System.out::println);
        return false; // Không nhận ownership các annotation khác.
    }
}
```

**Giải thích các điểm quan trọng trong processor:**

1. `@SupportedAnnotationTypes("*")` cho phép processor được gọi trong ví dụ ngay cả khi không có annotation nghiệp vụ. Trong một công cụ thực tế, chỉ khai báo những annotation mà processor cần xử lý khi có thể.
2. `SourceVersion.latestSupported()` cho biết processor hỗ trợ source version của compiler đang dùng; ở ví dụ Java 17+ thì cú pháp switch expression-style với `case ... ->` và `Stream.toList()` đều được hỗ trợ.
3. `printed` tránh in lặp qua các round; `round.processingOver()` báo lượt xử lý cuối. Việc trả `false` nghĩa processor **không claim** annotation để ngăn processor khác xử lý.
4. `Elements.getModuleElement(name)` lấy module từ môi trường biên dịch. Trường hợp không tìm thấy trả `null`, không thể suy rằng module khác không tồn tại trên đĩa.
5. `getEnclosedElements()` lọc `ElementKind.PACKAGE` rồi sắp xếp tên để có stdout ổn định trong ví dụ.
6. `getTypeElement(module, name)` rồi `getModuleOf(type)` cho thấy cách **xác định module sở hữu type** dựa trên environment thay vì cắt tiền tố string.
7. `Directive.getKind()` là enum đã định nghĩa; các phép cast sang `RequiresDirective`, `ExportsDirective` ... chỉ thực hiện đúng với từng kind.
8. `getTargetModules()==null` được xử lý rõ cho `exports` và `opens` không có đích cụ thể. `"->ALL"`/`"->SPECIFIC"` chỉ là nhãn do ví dụ tự in, **không phải API output chuẩn của JDK**.
9. Mã sắp xếp danh sách dòng directive trước khi in; kết quả là **bản đọc model** chứ không phải in lại đúng thứ tự dòng trong `module-info.java`.
10. `System.out` ở đây để người học nhìn stdout. Trong processor production, ưu tiên `processingEnv.getMessager().printMessage(...)` với `Diagnostic.Kind.NOTE/WARNING/ERROR` cho các chẩn đoán tương ứng và kiểm soát mức độ ồn của build.

### 6.3. Biên dịch processor, biên dịch module và chạy service

Đứng ở thư mục `module-element-demo` (thư mục chứa `processor` và `src`), dùng ba lệnh:

```bash
javac -encoding UTF-8 -d build-processor processor/ModuleInspector.java
javac -encoding UTF-8 -processorpath build-processor -processor ModuleInspector -d out --module-source-path src --module com.example.widget
java --module-path out --module com.example.widget/com.example.widget.api.Main
```

Ý nghĩa các tùy chọn:

- `-d build-processor`: biên dịch lớp processor ở một thư mục riêng.
- `-processorpath build-processor`: giúp `javac` nạp processor từ **annotation processor path**, không phải tự tìm trong module source.
- `-processor ModuleInspector`: chỉ định processor cần chạy tường minh; không phụ thuộc tình cờ vào cơ chế autodiscovery.
- `-d out --module-source-path src --module com.example.widget`: biên dịch source module từ layout `src/<module-name>/...` và xuất class vào `out`.
- `java --module-path out --module com.example.widget/com.example.widget.api.Main`: chạy main class trong named module vừa biên dịch.

**Stdout của lệnh `javac` thứ hai, đã kiểm chứng trên JDK 24:**

```text
module=com.example.widget
simple=widget
kind=MODULE
open=false
unnamed=false
packages=com.example.widget.api,com.example.widget.impl
typeModule=com.example.widget
exports=com.example.widget.api->ALL
opens=com.example.widget.impl->ALL
provides=com.example.widget.api.Greeter->com.example.widget.impl.SimpleGreeter
requires=java.base(transitive=false,static=false)
requires=java.logging(transitive=false,static=false)
uses=com.example.widget.api.Greeter
```

**Stdout của lệnh `java` thứ ba:**

```text
Xin chào, Java!
```

Dòng `requires=java.base(...)` là điểm đáng chú ý: source chỉ khai báo `requires java.logging`, nhưng `java.base` là module được **mọi named module đọc ngầm định** và có thể được compiler đưa vào danh sách directive của language model. Những công cụ cần phân biệt explicit source và synthetic/mandated construct phải dựa vào API/thông tin compiler phù hợp; riêng `getDirectives()` và `DirectiveKind` không phải trình phân tích cú pháp chứa vị trí/nguồn gốc từng dòng khai báo.

`open=false` hoàn toàn hợp lệ dù có `opens ...impl`: chỉ **`open module ...`** mới làm `isOpen()` thể hiện trạng thái open module. Lệnh chạy chứng minh `provides`/`uses` không chỉ là text: `ServiceLoader` đã tìm được `SimpleGreeter` và tạo lời chào đúng.

Kết quả này đã được kiểm tra với JDK 24. Danh sách module hệ thống được biểu diễn ra sao có thể phụ thuộc compiler/version; riêng logic tên, kind và ý nghĩa API không thay đổi vì không phụ thuộc vào thứ tự `getDirectives()`.

## 7. Ví dụ công cụ nhúng: lấy ModuleElement từ JavacTask

Trong workflow xây dựng IDE plugin, tool phân tích mã nguồn hay linter, ta có thể không muốn tạo annotation processor. Một ứng dụng có thể tự gọi Java compiler của JDK.

Ví dụ này **dùng lại bốn tệp source của module ở phần 6.1**, nhưng tự khởi tạo compiler để lấy model. Lưu thêm tệp `EmbeddedModuleLookup.java` ngay tại thư mục `module-element-demo`:

```java
import com.sun.source.util.JavacTask;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import javax.lang.model.element.ModuleElement;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class EmbeddedModuleLookup {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is required");
        }
        Files.createDirectories(Path.of("embedded-out"));
        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> units = files.getJavaFileObjectsFromPaths(
                    List.of(
                        Path.of("src/com.example.widget/module-info.java"),
                        Path.of("src/com.example.widget/com/example/widget/api/Greeter.java"),
                        Path.of("src/com.example.widget/com/example/widget/api/Main.java"),
                        Path.of("src/com.example.widget/com/example/widget/impl/SimpleGreeter.java")
                    ));
            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null,
                    List.of("--module-source-path", "src", "-d", "embedded-out", "-proc:none"),
                    null, units);
            task.parse();
            task.analyze();
            ModuleElement module =
                    task.getElements().getModuleElement("com.example.widget");
            if (module == null) {
                throw new IllegalStateException("Module not found");
            }
            System.out.println("embeddedModule=" + module.getQualifiedName());
            System.out.println("embeddedKind=" + module.getKind());
            System.out.println("embeddedExports=" + module.getDirectives().stream()
                    .filter(d -> d.getKind()
                            == ModuleElement.DirectiveKind.EXPORTS)
                    .count());
        }
    }
}
```

Biên dịch và chạy từ đúng thư mục dự án:

```bash
javac -encoding UTF-8 EmbeddedModuleLookup.java
java EmbeddedModuleLookup
```

Stdout chính xác khi chạy với mã mẫu trên JDK 24:

```text
embeddedModule=com.example.widget
embeddedKind=MODULE
embeddedExports=1
```

Điểm học tập trong ví dụ:

- `ToolProvider.getSystemJavaCompiler()` chỉ hoạt động nếu runtime có compiler. Khi build native runtime image rút gọn, phải cung cấp module compiler thích hợp hoặc chạy tool với JDK.
- `JavaCompiler.getTask(...)` trả `JavaCompiler.CompilationTask`; code ép sang `JavacTask` vì đang dùng **javac của JDK**. Với compiler provider khác, không nên ép kiểu này nếu không xác định được implementation.
- `StandardJavaFileManager` quản lý source file; được đóng bằng `try-with-resources`.
- `--module-source-path src` và `-d embedded-out` bảo đảm compiler có cấu trúc modular source và output hợp lệ. **Thiếu output directory khi biên dịch named module có thể làm task báo lỗi**.
- `-proc:none` chủ ý vô hiệu hóa annotation processing trong nhánh phân tích nhúng để tránh vô tình chạy processor không mong muốn; phần 6 đã minh họa processor độc lập.
- `task.parse(); task.analyze();` xây dựng ngữ cảnh semantic đủ để `task.getElements().getModuleElement(...)` tìm module. Chỉ tạo task mà chưa thực hiện giai đoạn thích hợp thì model chưa sẵn sàng.
- `module.getDirectives().stream().filter(...EXPORTS).count()` đo số directive exports trong model, khác việc đếm mọi class public.
- Code trên **không cần generate class** để đọc module: nó dùng compiler như một analyzer. Khi build/lint production nên thu thập diagnostics, kiểm soát compiler options và xử lý lỗi phân tích rõ ràng.

Công cụ nhúng có thể kết hợp `JavacTask.getElements()` với `JavacTask.getTypes()`/tree API để kiểm tra liên kết giữa khai báo `module-info.java`, public API và các tham chiếu trong code. Dù dùng compiler task hay processor, **một `ModuleElement` luôn được hiểu trong ngữ cảnh của cùng lần xử lý ngôn ngữ**, không phải một đối tượng độc lập tồn tại mãi sau khi compiler kết thúc.

## 8. Mở rộng: qualified exports/opens, requires transitive/static

Đoạn ví dụ hoàn chỉnh dùng dạng đơn giản. Những trường hợp thực tế công cụ cần xử lý thêm:

### 8.1. Qualified exports và qualified opens

```java
module com.example.library {
    exports com.example.library.api;
    exports com.example.library.spi to com.example.plugin;
    opens com.example.library.model to com.example.framework;
}
```

Đây là **mảnh descriptor minh họa**, không phải module build độc lập vì còn cần package `api/spi/model` và các target module có thể phân giải. Ý nghĩa:

- `exports ...api`: export đến tất cả module có quyền đọc module này; `ExportsDirective.getTargetModules() == null`.
- `exports ...spi to ...plugin`: chỉ export package `spi` đến target được nêu; `getTargetModules()` trả list target.
- `opens ...model to ...framework`: cho phép reflection sâu với một target được chỉ định; `OpensDirective.getTargetModules()` trả list target.
- Không biến exports/opens thành các quyền truy cập tương đương: export là quyền truy cập compile-time và reflection public thông thường theo quy tắc Java, open phục vụ reflective access.

### 8.2. requires transitive và requires static

```java
module com.example.library {
    requires transitive com.example.api;
    requires static com.example.annotations;
}
```

Đây cũng là **mảnh minh họa**, chưa có source phụ thuộc nên không chạy độc lập. Với `RequiresDirective`, kiểm tra:

- `getDependency()` lấy `ModuleElement` của module đích.
- `isTransitive()`: `true` khi yêu cầu là transitive.
- `isStatic()`: `true` khi yêu cầu là static.
- Một directive có thể có modifier phù hợp quy tắc ngôn ngữ, nhưng đừng suy luận modifier chỉ từ chuỗi tên module.

Khi xây quy tắc kiến trúc, cần đánh giá **module readability graph**, export/qualified export, actual type accessibility và nhu cầu dependency. Đếm `requires` thuần không đủ để khẳng định một public class có thể được consumer sử dụng.

### 8.3. ModuleElement với unnamed và automatic module

Ở ứng dụng chưa tổ chức thành named module (classpath), compiler environment có thể tạo unnamed `ModuleElement`. Nó có `isUnnamed() == true` và tên rỗng. Một JAR đặt trên module path có thể trở thành **automatic module** có tên dù không viết descriptor. Hai trường hợp có semantics khác nhau; analyzer không được dùng logic “không có module-info => unnamed” như một kết luận duy nhất.

Nếu xây kiểm tra **module-info bắt buộc**, hãy phân biệt explicit named, automatic và unnamed theo API/phạm vi compiler thực sự hỗ trợ. Đừng từ chối toàn bộ thư viện classpath chỉ vì `getModuleElement("some.name")==null`; có thể module đó không được đưa vào cấu hình phân tích.

## 9. Kết nối ModuleElement với mô hình phân tích của annotation processor

Trong kiến trúc annotation processor, quan sát các phần tử ở đúng layer sẽ giảm lỗi:

```text
RoundEnvironment.getRootElements()
             │
             ├── TypeElement / PackageElement / ModuleElement (tùy input)
             │
             ▼
ProcessingEnvironment.getElementUtils()
             │
             ├── getModuleElement("module.name")
             ├── getModuleOf(typeElement)
             ├── getTypeElement(module, "pkg.Type")
             └── getPackageElement(module, "pkg")
             │
             ▼
ModuleElement.getDirectives()
             │
             ├── RequiresDirective
             ├── ExportsDirective
             ├── OpensDirective
             ├── UsesDirective
             └── ProvidesDirective
```

**Cách viết analyzer đáng tin:**

1. Đọc target module theo tên hoặc `getModuleOf(element)`, không tự dựng module name từ package name.
2. Kiểm tra null, `getKind() == MODULE` và `isUnnamed()` trước khi giả định có `module-info.java`.
3. Duyệt directives bằng kind/visitor; dùng typed getters để đọc quan hệ module/package/type.
4. Với `exports` và `opens`, phân biệt `getTargetModules()==null` với danh sách target hạn chế.
5. Với `requires`, nếu muốn kiểm tra quy tắc kiến trúc, phân biệt `transitive`/`static` và các phụ thuộc ngầm định.
6. Chọn rõ liệu phân tích source đã được load, classpath hay module path. Có thể một module hoặc type chưa **observable** trong environment và được trả `null`.
7. Phân biệt báo cáo kiểm tra compile-time với khẳng định về runtime classloading/reflection. JPMS runtime còn có module layers, cấu hình launch và một số tùy chọn nâng cao có thể ảnh hưởng quyền truy cập thực tế.
8. Đừng giữ `Element`/`TypeMirror` vượt quá vòng đời task hoặc giả định đối tượng có identity/reference ổn định giữa các lần compiler invocation. Tài liệu `Element` khuyến nghị so sánh theo `equals()`, không dùng `==` để quyết định cùng phần tử.

## 10. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| Dùng `Class.getModule()` trong processor để đọc source module | Reflection chỉ phản ánh lớp runtime đã được nạp | Dùng `Elements.getModuleElement()` |
| Lấy `getSimpleName()` làm khóa duy nhất | Nhiều module có thể có đoạn tên cuối giống nhau | Dùng `getQualifiedName()` |
| Không xử lý `null` của `getModuleElement(name)` | Compiler environment có thể không thấy module | Kiểm tra null và source/module path |
| Coi `getEnclosedElements()` là danh sách tất cả class | Module chứa package trực tiếp trong language model | Lấy `PackageElement`, sau đó duyệt kiểu nếu cần |
| Coi `getDirectives()` là các dòng chữ trong source | Model có thể chứa khai báo/quan hệ ngầm định; thứ tự không phải hợp đồng parse text | Dùng `DirectiveKind`/typed APIs; cần vị trí source thì dùng compiler tree API |
| Lấy `getTargetModules().size()` ngay | Có thể trả `null` cho unqualified exports/opens | Kiểm tra null trước |
| Nhầm `isOpen()==true` khi module chỉ có `opens p` | `isOpen()` phản ánh open module, không phải một opens directive đơn lẻ | Đọc cả `isOpen()` và `getDirectives()` |
| Nhầm `uses/provides` là instance đã được tạo | Mô hình trả về `TypeElement` và descriptor, không chạy service | Dùng `ServiceLoader` khi thực sự cần instance ở runtime |
| Đếm `requires` rồi tin có bao nhiêu dòng source | Có thể có `java.base` ngầm định | Phân biệt model và syntax source |
| Quên `-d` khi dùng compiler modular source | Có thể bị lỗi compiler thiếu output directory | Khai báo output directory phù hợp |
| Quên `-processorpath`/`-processor` | Processor không được tìm hoặc không chạy | Compile processor riêng và chỉ định rõ |
| Dùng JRE/runtime image không có compiler | `ToolProvider.getSystemJavaCompiler()` có thể trả null | Chạy bằng JDK có compiler hoặc thiết kế workflow khác |
| Chỉ gọi `getTask()` rồi ngay lập tức hỏi elements | Compiler chưa tạo xong môi trường semantic | Chạy `parse()`/`analyze()` theo đúng lifecycle |
| Mở `impl` vì nghĩ service provider cần opens | Vô tình nới reflective access | Chỉ `opens` khi có nhu cầu thực tế, tốt nhất giới hạn target |
| Giả định mỗi processor round chứa cùng root elements | Annotation processing có nhiều round, các phần tử sinh thêm | Quản lý trạng thái processor và xử lý round đúng cách |
| Nghĩ `javax.lang.model` là API cũ phải thay bằng `jakarta.*` | Namespace này là phần của Java SE compiler API hiện hành | Tiếp tục dùng `javax.lang.model` |
| Sử dụng class trong `com.sun.tools.javac.*` để truy xuất private internal | Phụ thuộc implementation không ổn định và có rào cản module | Ưu tiên API công khai `javax.lang.model` và `com.sun.source.util.JavacTask` |

**Lưu ý phiên bản:** API `ModuleElement` được giới thiệu cùng JPMS ở Java 9 và vẫn còn trong Java SE/JDK hiện hành. Tuy nhiên các ví dụ mã dùng `switch ... ->` và `Stream.toList()`, nên yêu cầu **Java 17+**. Hạn chế nhầm yêu cầu của ví dụ với thời điểm API lần đầu tồn tại.

## 11. Bài tập áp dụng và câu hỏi tự kiểm tra

**Câu 1:** Một module khai báo `opens com.example.widget.impl;` nhưng không dùng `open module`. `isOpen()` trả gì?  
**Đáp án:** `false`, bởi `isOpen()` nhận diện open module, không phải việc có một opens directive.

**Câu 2:** Làm sao tìm module chứa `TypeElement` của `com.example.widget.api.Greeter`?  
**Đáp án:** `elements.getModuleOf(greeterType)`. Nếu biết module cần tìm, có thể gọi `elements.getTypeElement(module, qualifiedName)` trước.

**Câu 3:** Tại sao `getTargetModules()` của `ExportsDirective` có thể trả null?  
**Đáp án:** Descriptor dùng dạng `exports pkg;` không giới hạn bằng danh sách `to m1,m2`. Null có nghĩa khác với danh sách target rỗng.

**Câu 4:** Processor in hai dòng `requires=java.base` và `requires=java.logging` dù mã nguồn chỉ có `requires java.logging;`. Có chắc processor lỗi không?  
**Đáp án:** Không; model có thể bao gồm phụ thuộc `java.base` ngầm định. Nếu cần phân tích đúng chữ source, dùng compiler tree API để đối chiếu khai báo.

**Câu 5:** `ProvidesDirective.getImplementations()` trả các instance đã được tạo hay các loại implementation?  
**Đáp án:** Trả danh sách `TypeElement` của các kiểu implementation, không tạo instance. `ServiceLoader` ở runtime mới thực hiện tìm và khởi tạo provider theo cơ chế dịch vụ.

**Câu 6:** Trong ứng dụng nhúng compiler, tại sao `ToolProvider.getSystemJavaCompiler()` có thể null?  
**Đáp án:** Runtime hiện tại có thể không bao gồm compiler provider; cần JDK hoặc runtime image chứa công cụ phù hợp.

**Câu 7:** Hãy viết một quy tắc báo cáo tất cả exported packages.  
**Gợi ý:** Duyệt `module.getDirectives()`, chỉ lấy `DirectiveKind.EXPORTS`, ép kiểu `ExportsDirective`, lấy `getPackage().getQualifiedName()` và phân biệt target modules null/không null. Không cần parse `module-info.java` dạng string.

**Câu 8:** Có thể dùng `ModuleElement` để lấy lịch sử runtime hoặc instance của một service không?  
**Đáp án:** Không. Nó mô tả phần tử ngôn ngữ theo compiler environment. Dùng các API runtime như `ServiceLoader`, `ModuleLayer` hoặc reflection khi thực sự cần làm việc với module đã tải.

## Nguồn tham khảo chính thức, hiện hành

- [Java SE 25 — javax.lang.model.element.ModuleElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ModuleElement.html): giao diện module, các getter, `DirectiveKind` và nested interfaces.
- [Java SE 25 — javax.lang.model.util.Elements](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getModuleElement`, `getModuleOf`, `getTypeElement(module, name)` và các API truy vấn phần tử.
- [Java SE 25 — ModuleElement.RequiresDirective](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ModuleElement.RequiresDirective.html): `getDependency`, `isTransitive`, `isStatic`.
- [Java SE 26 — ModuleElement.ExportsDirective](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ModuleElement.ExportsDirective.html): `getPackage`, `getTargetModules` và quy tắc qualified exports.
- [Java SE 25 — ModuleElement.ProvidesDirective](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ModuleElement.ProvidesDirective.html): service và danh sách implementation type.
- [Java SE 25 — com.sun.source.util.JavacTask](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html): `parse()`, `analyze()`, `getElements()` cho công cụ nhúng `javac`.
- [Java SE 25 — javax.tools.ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html): lấy compiler hệ thống, điều kiện compiler có thể không sẵn.
- [Java Language Specification — Modules, §7.7](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7): ngữ nghĩa module declaration, dependency, export, open và service.

**Tóm lại:** `ModuleElement` là **góc nhìn compiler về một module Java**. Dùng `Elements` để tìm module/type, `ModuleElement` để đọc danh tính/package/directives, và typed directive APIs để phân tích cấu trúc. Khi nhúng `javac` hoặc viết annotation processor, cần cấu hình đúng môi trường biên dịch, phân biệt named/automatic/unnamed module và tuyệt đối không đánh đồng mô hình compile-time với `java.lang.Module` ở runtime.
