# ModuleTree và các chỉ thị của module-info.java trong cây cú pháp Java

## 1. Vì sao công cụ phân tích Java cần `ModuleTree`?

Từ Java 9, Java Platform Module System (JPMS) đưa khai báo module vào tệp `module-info.java`. Một chương trình phân tích mã nguồn, quy tắc kiểm tra kiến trúc, IDE hoặc plugin compiler có thể cần đọc **module tên gì, phụ thuộc module nào, công khai package nào, mở package nào và đăng ký service nào** mà không phải tự tách chuỗi bằng biểu thức chính quy.

JDK Java Compiler Tree API trong module `jdk.compiler` cung cấp giao diện `com.sun.source.tree.ModuleTree` để biểu diễn **cây cú pháp trừu tượng (AST)** của khai báo module. Đây là API xuất hiện từ Java 9 và vẫn được JDK hiện đại công bố (Java 17+, Java 21, Java 25).

Ví dụ tệp nguồn:

~~~java
module com.example.billing {
    requires java.sql;
    requires transitive java.logging;
    exports com.example.billing.api;
    opens com.example.billing.internal to com.example.json;
    uses com.example.billing.spi.PaymentGateway;
    provides com.example.billing.spi.PaymentGateway
            with com.example.billing.impl.CardGateway;
}
~~~

Cây cú pháp tương ứng có một `CompilationUnitTree` chứa `ModuleTree`; trong `ModuleTree.getDirectives()` là các node con: `RequiresTree`, `ExportsTree`, `OpensTree`, `UsesTree` và `ProvidesTree`.

~~~text
CompilationUnitTree  (đại diện file module-info.java)
    └── getModule() -> ModuleTree
          ├── getModuleType(): STRONG hoặc OPEN
          ├── getName(): ExpressionTree (com.example.billing)
          ├── getAnnotations(): List<AnnotationTree>
          └── getDirectives(): List<DirectiveTree>
                 ├── RequiresTree
                 ├── RequiresTree
                 ├── ExportsTree
                 ├── OpensTree
                 ├── UsesTree
                 └── ProvidesTree
~~~

**Phân biệt bản chất:** AST phản ánh **mã nguồn đã viết**; nó không phải bảng module thực sự đã resolve ở runtime. `ModuleTree` dùng để phân tích cú pháp `module-info.java`; `java.lang.module.ModuleDescriptor` dùng khi cần đọc descriptor/module đã đóng gói; `javax.lang.model.element.ModuleElement` cung cấp biểu diễn module ở mức phần tử chương trình khi compiler đã phân tích ngữ nghĩa. Ba tầng phục vụ các câu hỏi khác nhau.

## 2. Những giao diện hiện hành và quan hệ giữa chúng

Các kiểu cốt lõi thuộc `com.sun.source.tree`. Mọi node triển khai `Tree`, có `getKind()` và `accept(TreeVisitor, ...)`.

| Giao diện | Nội dung AST | API chính |
| --- | --- | --- |
| `CompilationUnitTree` | Một compilation unit Java, bao gồm module declaration nếu có | `getModule()`, `getSourceFile()`, `getLineMap()` |
| `ModuleTree` | Khai báo `module ... { ... }` hoặc `open module ... { ... }` | `getName()`, `getModuleType()`, `getAnnotations()`, `getDirectives()` |
| `DirectiveTree` | Kiểu cha chung của các chỉ thị bên trong module | `getKind()`, `accept(...)` |
| `RequiresTree` | Phụ thuộc module | `getModuleName()`, `isStatic()`, `isTransitive()` |
| `ExportsTree` | Công khai package ở biên giới module | `getPackageName()`, `getModuleNames()` |
| `OpensTree` | Mở package cho truy cập lúc chạy, đặc biệt reflective access | `getPackageName()`, `getModuleNames()` |
| `UsesTree` | Khai báo dịch vụ được module tiêu thụ | `getServiceName()` |
| `ProvidesTree` | Khai báo implementation cung cấp dịch vụ | `getServiceName()`, `getImplementationNames()` |

Hai enum khác nhau dễ gây nhầm:

- `moduleTree.getKind()` trả `Tree.Kind.MODULE`: **đây là node thuộc loại cú pháp module**.
- `moduleTree.getModuleType()` trả `ModuleTree.ModuleKind.STRONG` cho khai báo `module` bình thường, hoặc `ModuleTree.ModuleKind.OPEN` cho `open module`: **đây là kiểu mở của module**.
- `directive.getKind()` là một trong `Tree.Kind.REQUIRES`, `EXPORTS`, `OPENS`, `USES`, `PROVIDES`. Nó **không** trả `ModuleTree.ModuleKind`.

`ModuleTree.getAnnotations()` trả các annotation được khai báo trên module, chẳng hạn annotation có `@Target(ElementType.MODULE)`; danh sách rỗng nếu không có annotation. `getName()` và các tên module/package/service là `ExpressionTree`, không phải đối tượng module đã được resolve.

**Lưu ý version:** Các interface `Tree` được JDK cảnh báo là có thể phát triển khi ngôn ngữ Java phát triển. Hãy dùng giao diện `com.sun.source.*` được export bởi `jdk.compiler` và biên dịch/kiểm thử trên JDK mục tiêu; tránh ép kiểu sang các lớp triển khai nội bộ `com.sun.tools.javac.*` hoặc dựa vào cấu trúc chi tiết của chúng.

## 3. Đọc đúng từng loại chỉ thị

### 3.1. `requires`: đọc module và hai modifier

Ví dụ:

~~~java
module com.example.feature {
    requires java.sql;
    requires transitive java.logging;
    requires static java.xml;
}
~~~

Với từng node `RequiresTree`:

| Cú pháp | `getModuleName()` | `isStatic()` | `isTransitive()` |
| --- | --- | --- | --- |
| `requires java.sql;` | `java.sql` | `false` | `false` |
| `requires transitive java.logging;` | `java.logging` | `false` | `true` |
| `requires static java.xml;` | `java.xml` | `true` | `false` |

- `requires` tạo quan hệ phụ thuộc để một module có thể đọc module khác.
- `requires transitive` cho phép các module đọc module hiện tại đồng thời đọc module được yêu cầu theo quy tắc transitive readability.
- `requires static` đánh dấu phụ thuộc cần tại thời điểm biên dịch nhưng là tùy chọn khi chạy; **không** có nghĩa là Java class `static` hay chặn mọi liên kết runtime vào module đó.
- Về cú pháp, hai modifier có thể cùng xuất hiện trong một chỉ thị; hai cờ trong AST cho phép công cụ phân biệt chúng.

Node AST chỉ lưu điều người viết khai báo. Phụ thuộc ngầm `java.base` của named module **không được tự tạo ra** trong danh sách `getDirectives()` của một source không ghi rõ `requires java.base`. Nếu cần đồ thị module đã resolve đầy đủ, phải dùng mô hình ngữ nghĩa hoặc descriptor/runtime, không suy ra từ danh sách node cú pháp.

### 3.2. `exports`: package công khai, không đồng nghĩa mở sâu

~~~java
module com.example.catalog {
    exports com.example.catalog.api;
    exports com.example.catalog.internal.spi to com.example.consumer;
}
~~~

`ExportsTree.getPackageName()` lấy tên package; `getModuleNames()` lấy danh sách **đích được cấp quyền**.

- Với `exports p;`, `getModuleNames() == null` vì package được export không điều kiện cho mọi module có thể đọc nó.
- Với `exports p to a, b;`, danh sách chứa các tên `a` và `b`.
- **Không tự đổi `null` thành “không có module nào được phép”**: `null` ở đây có nghĩa không giới hạn theo danh sách module đích.
- `exports` điều khiển quyền truy cập tới public types/public members theo module rules; nó không thay cho `opens` khi thư viện cần deep reflection.

### 3.3. `opens`: mở package ở thời gian chạy

~~~java
module com.example.catalog {
    opens com.example.catalog.dto;
    opens com.example.catalog.model to com.example.serializer;
}
~~~

`OpensTree.getPackageName()` là package được mở; `getModuleNames()`:

- `null` khi `opens p;` mở cho mọi module;
- danh sách module đích khi `opens p to m1, m2;`.

Một package được `opens` để cho phép truy cập reflective ở runtime theo JPMS, **không đồng nghĩa package đó được `exports` cho client code compile thông thường**. Cũng không có quan hệ “export package thì mặc nhiên deep reflection được phép”.

Ở mức thiết kế, ưu tiên mở đúng package cho đúng framework/module khi cần, thay vì mở toàn bộ vì tiện lợi.

### 3.4. `uses` và `provides`: khai báo dịch vụ

~~~java
module com.example.payment {
    uses com.example.payment.spi.PaymentGateway;
    provides com.example.payment.spi.PaymentGateway
            with com.example.payment.impl.CardGateway,
                 com.example.payment.impl.BankGateway;
}
~~~

- `UsesTree.getServiceName()` là tên kiểu dịch vụ mà module sử dụng.
- `ProvidesTree.getServiceName()` là tên service interface/abstract type.
- `ProvidesTree.getImplementationNames()` là **danh sách** các implementation được khai báo, không chỉ một tên.
- Các node mô tả **khai báo** cho Java service loading; chúng không tạo instance, không gọi `ServiceLoader.load` và không chứng minh provider class thực sự hợp lệ cho dịch vụ. Những điều đó cần semantic checks/runtime.

Hai chỉ thị độc lập: một module có thể chỉ dùng dịch vụ, chỉ cung cấp hoặc làm cả hai, tùy thiết kế.

### 3.5. `open module` khác với `opens package`

~~~java
open module com.example.plugins {
    requires java.logging;
    exports com.example.plugins.api;
}
~~~

Ở đây `ModuleTree.getModuleType() == ModuleTree.ModuleKind.OPEN`. `open module` mở **tất cả package** cho deep reflection tại runtime; tuy nhiên package không tự được export cho source-level access. Không viết thêm `opens ...` bên trong một `open module` vì cú pháp/quy tắc JPMS không cho phép điều đó.

Ngược lại:

~~~java
module com.example.plugins {
    opens com.example.plugins.config to com.example.serializer;
}
~~~

Là module `STRONG` chỉ mở package được chỉ định cho module đích. Phân tích AST phải đọc **cả** `getModuleType()` và `getDirectives()`; không thể chỉ tìm `OpensTree` để kết luận một package có được mở không.

## 4. Một chương trình đầy đủ đọc `module-info.java` bằng compiler AST

### 4.1. Tệp nguồn cần phân tích

Tạo thư mục thử nghiệm và lưu tệp `module-info.java` như sau:

~~~java
module demo.viewer {
    requires java.logging;
    requires transitive java.sql;
    requires static java.xml;
    exports demo.api;
    exports demo.spi to demo.consumer;
    opens demo.internal to demo.reflection;
    uses demo.spi.Codec;
    provides demo.spi.Codec with demo.impl.SimpleCodec;
}
~~~

Đây là **fixture minh họa cú pháp**, chưa chứa package `demo.api`, `demo.spi`, interface `Codec` hay các module `demo.consumer` và `demo.reflection`. Chương trình bên dưới **chỉ parse** nên vẫn đọc được AST. **Không coi fixture này là một ứng dụng module đã biên dịch/chạy thành công**: nếu gọi bước semantic analysis/generate, compiler sẽ yêu cầu các module, package và class hợp lệ.

### 4.2. Chương trình `ModuleTreeDemo.java`

Lưu tệp **`ModuleTreeDemo.java`** trong cùng thư mục:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.DirectiveTree;
import com.sun.source.tree.ExportsTree;
import com.sun.source.tree.ExpressionTree;
import com.sun.source.tree.ModuleTree;
import com.sun.source.tree.OpensTree;
import com.sun.source.tree.ProvidesTree;
import com.sun.source.tree.RequiresTree;
import com.sun.source.tree.UsesTree;
import com.sun.source.util.JavacTask;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class ModuleTreeDemo {
    private static String targets(List<? extends ExpressionTree> names) {
        return names == null
                ? "ALL"
                : names.stream().map(Object::toString)
                        .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass module-info.java path");
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a JDK");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> sources =
                    files.getJavaFileObjects(Path.of(args[0]).toFile());
            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, diagnostics, List.of("-proc:none"), null, sources);

            for (CompilationUnitTree unit : task.parse()) {
                ModuleTree module = unit.getModule();
                if (module == null) {
                    throw new IllegalArgumentException("No module declaration");
                }
                System.out.println("Module: " + module.getName()
                        + " (" + module.getModuleType() + ")");

                for (DirectiveTree directive : module.getDirectives()) {
                    switch (directive.getKind()) {
                        case REQUIRES -> {
                            RequiresTree d = (RequiresTree) directive;
                            System.out.println("REQUIRES " + d.getModuleName()
                                    + ": static=" + d.isStatic()
                                    + ", transitive=" + d.isTransitive());
                        }
                        case EXPORTS -> {
                            ExportsTree d = (ExportsTree) directive;
                            System.out.println("EXPORTS " + d.getPackageName()
                                    + " -> " + targets(d.getModuleNames()));
                        }
                        case OPENS -> {
                            OpensTree d = (OpensTree) directive;
                            System.out.println("OPENS " + d.getPackageName()
                                    + " -> " + targets(d.getModuleNames()));
                        }
                        case USES -> {
                            UsesTree d = (UsesTree) directive;
                            System.out.println("USES " + d.getServiceName());
                        }
                        case PROVIDES -> {
                            ProvidesTree d = (ProvidesTree) directive;
                            System.out.println("PROVIDES " + d.getServiceName()
                                    + " -> " + targets(d.getImplementationNames()));
                        }
                        default -> throw new IllegalStateException(
                                "Unknown directive: " + directive.getKind());
                    }
                }
            }

            for (Diagnostic<? extends JavaFileObject> d
                    : diagnostics.getDiagnostics()) {
                if (d.getKind() == Diagnostic.Kind.ERROR) {
                    throw new IllegalArgumentException(
                            "Syntax error: " + d.getMessage(Locale.ROOT));
                }
            }
        }
    }
}
~~~

Lý do chọn cách viết:

1. `ToolProvider.getSystemJavaCompiler()` lấy Java compiler có trong JDK. Trong runtime image bị cắt bỏ module `jdk.compiler`, giá trị có thể `null` và công cụ phải báo thiếu compiler rõ ràng.
2. `StandardJavaFileManager` mở tệp với mã hóa `UTF-8`, dùng `try-with-resources` đóng tài nguyên.
3. `compiler.getTask(...)` cung cấp compilation task. Với JDK compiler thông thường, task là `JavacTask` nên có thể gọi `parse()` để nhận AST mà không tạo `.class` cho fixture.
4. `-proc:none` vô hiệu annotation processing trong một tác vụ compiler; trong ví dụ chỉ gọi `parse()`. Tránh tự kích hoạt các bước analyze/generate khi nhiệm vụ là đọc cú pháp.
5. Lấy `CompilationUnitTree.getModule()` trước khi duyệt directives. Phương thức này trả `null` đối với source không có module declaration; riêng một implementation không hỗ trợ API có thể ném `UnsupportedOperationException` theo contract của interface. Ví dụ được thiết kế cho javac trên JDK hiện hành.
6. Dùng `switch (directive.getKind())` rồi ép kiểu sang subtype đúng. Không cần class nội bộ của javac.
7. Với `exports`/`opens`, `targets(null)` in `ALL` vì unqualified directive không có danh sách đích; khi có `to`, in tên module.
8. Chương trình xem danh sách diagnostics và từ chối input có lỗi cú pháp; việc parse trả về một tree **không tự chứng minh input hợp lệ về cú pháp hoặc ngữ nghĩa**.

### 4.3. Biên dịch và chạy

Từ thư mục chứa hai tệp nguồn, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 ModuleTreeDemo.java
java ModuleTreeDemo module-info.java
~~~

Không cần dependency bên thứ ba hay tùy chọn `--add-exports`. Module `jdk.compiler` export các package `com.sun.source.tree` và `com.sun.source.util` cần thiết cho API này. Trên classpath với JDK đầy đủ, chương trình có thể gọi chúng như ví dụ đã biên dịch.

**Stdout chính xác** trên JDK 24 khi chạy fixture đã cho:

~~~text
Module: demo.viewer (STRONG)
REQUIRES java.logging: static=false, transitive=false
REQUIRES java.sql: static=false, transitive=true
REQUIRES java.xml: static=true, transitive=false
EXPORTS demo.api -> ALL
EXPORTS demo.spi -> demo.consumer
OPENS demo.internal -> demo.reflection
USES demo.spi.Codec
PROVIDES demo.spi.Codec -> demo.impl.SimpleCodec
~~~

Kết quả trên không chứa `requires java.base` vì nó là phụ thuộc ngầm, không xuất hiện thành chỉ thị được viết trong fixture. Trình parse cũng không tự kiểm tra sự tồn tại của `demo.consumer`, `demo.spi.Codec` hoặc tính hợp lệ của provider: việc đó thuộc bước phân tích ngữ nghĩa.

Nếu đóng gói **công cụ phân tích** `ModuleTreeDemo` thành một named module riêng, một module descriptor phù hợp có thể là:

~~~java
module demo.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

`java.compiler` chứa `javax.tools`; `jdk.compiler` chứa tree API và `JavacTask`. Đây là descriptor của **công cụ**, không phải descriptor fixture mà công cụ đọc. Cả hai phải được đặt trong vị trí source/module path phù hợp nếu xây dự án modular thực sự.

## 5. Dùng visitor thay vì switch thủ công

Khi một công cụ chỉ cần ghi nhận dependency, có thể dùng `TreePathScanner` (hoặc `TreeScanner`) để duyệt cây:

~~~java
// Đoạn minh họa nằm sau bước parse(), với biến unit kiểu CompilationUnitTree.
new com.sun.source.util.TreePathScanner<Void, Void>() {
    @Override
    public Void visitRequires(RequiresTree directive, Void unused) {
        System.out.println("Dependency: " + directive.getModuleName());
        return super.visitRequires(directive, unused);
    }

    @Override
    public Void visitProvides(ProvidesTree directive, Void unused) {
        System.out.println("Service: " + directive.getServiceName());
        return super.visitProvides(directive, unused);
    }
}.scan(unit, null);
~~~

Đây là **đoạn mã đặt trong chương trình parse**, dùng các import `RequiresTree` và `ProvidesTree` giống mục 4; nó không tự chạy độc lập. Visitor framework sẽ đi theo cây nguồn từ compilation unit. Có thể override thêm `visitModule`, `visitExports`, `visitOpens` hoặc `visitUses` để thu thập chính xác những directive quan tâm.

Khi cần ngữ cảnh cha hoặc vị trí node, `TreePathScanner` cung cấp `TreePath` (đường đi từ gốc đến node hiện tại). Nếu chỉ cần tổng hợp cây mà không cần path, `TreeScanner` thường đủ. Với quy tắc phân tích không phức tạp, duyệt trực tiếp `module.getDirectives()` dễ đọc và tường minh hơn.

**Không tự suy từ `Tree.toString()` rằng đó là mã nguồn gốc còn nguyên comments/whitespace.** `ExpressionTree.toString()` hữu ích để minh họa hoặc log tên, nhưng AST không phải định dạng giữ toàn bộ văn bản. Dùng `SourcePositions` nếu cần ánh xạ node tới các đoạn trong tệp gốc.

## 6. Lấy vị trí dòng/cột để gợi ý cải thiện module-info.java

Khi viết linter, thông báo “package này mở quá rộng” sẽ hữu ích hơn nếu trỏ tới đúng chỉ thị. `Trees.instance(task).getSourcePositions()` kết hợp `CompilationUnitTree.getLineMap()` cho biết vị trí trong source.

~~~java
// Đoạn minh họa trong scope có sẵn:
// JavacTask task, CompilationUnitTree unit, DirectiveTree directive.
com.sun.source.util.SourcePositions positions =
        com.sun.source.util.Trees.instance(task).getSourcePositions();
long offset = positions.getStartPosition(unit, directive);
if (offset != javax.tools.Diagnostic.NOPOS && unit.getLineMap() != null) {
    long line = unit.getLineMap().getLineNumber(offset);
    long column = unit.getLineMap().getColumnNumber(offset);
    System.out.println("Line " + line + ", column " + column);
}
~~~

Một số node có thể không có vị trí xác định, nên phải kiểm tra `Diagnostic.NOPOS`. Đối với công cụ chỉnh sửa source, nên dùng cả `getEndPosition(...)`, giữ nguyên encoding, line endings và dấu cách; không thay đổi văn bản bằng cách chỉnh trực tiếp đối tượng AST.

Có thể dùng `DiagnosticCollector<JavaFileObject>` để báo lỗi parse hoặc compiler; từng diagnostic cho biết `Kind`, vị trí, source, mã và thông điệp. Khi phân tích source người khác, dùng diagnostic để từ chối đề xuất tự động nếu có lỗi cú pháp thay vì tiếp tục suy đoán tree từ phần recovery của parser.

## 7. Từ cú pháp đến ngữ nghĩa: đâu là ranh giới?

Giả sử source ghi:

~~~java
module demo.missing {
    requires something.not.installed;
    exports demo.missing.api;
    provides demo.missing.spi.Plugin with demo.missing.impl.PluginA;
}
~~~

`JavacTask.parse()` có thể tạo `ModuleTree` biểu diễn đủ các chỉ thị vì **cú pháp** là hợp lệ. Nhưng `requires something.not.installed` có thể tham chiếu module không có trên module path, package `demo.missing.api` có thể chưa tồn tại hoặc provider không đáp ứng contract. Muốn khẳng định module hợp lệ, cần chạy `analyze()` với nguồn, dependency và compiler options đúng, rồi kiểm tra diagnostics, hoặc biên dịch module thật.

Bảng quyết định:

| Câu hỏi của công cụ | Nguồn dữ liệu thích hợp |
| --- | --- |
| “Tệp `module-info.java` **đang viết** các chỉ thị nào?” | `JavacTask.parse()` → `CompilationUnitTree.getModule()` → `ModuleTree.getDirectives()` |
| “Dòng nào khai báo `opens p;`?” | `SourcePositions` và `LineMap` của AST |
| “Provider class có thực sự thực thi service interface hợp lệ?” | Compiler `analyze()`/type model; kiểm tra diagnostic với dependency đầy đủ |
| “Module nào đã được resolve, có bao nhiêu layer?” | `ModuleLayer`, `java.lang.Module` và `java.lang.module.ModuleDescriptor` |
| “Descriptor trong JAR/module runtime ghi những gì?” | `ModuleDescriptor` hoặc công cụ như `jar --describe-module` |
| “Một JAR không có `module-info.java` nhưng đặt trên module path thì sao?” | Nó có thể thành **automatic module**; không thể tự giả định có `ModuleTree` nguồn tương ứng |
| “Một class nằm trong unnamed module có ModuleTree không?” | Không có khai báo module nguồn dạng `module-info.java` cho unnamed module |

Đừng nhầm `ModuleTree.getModuleType() == STRONG` với kết luận rằng **mọi package thực sự bị đóng**. Vẫn phải duyệt `opens`/`exports`; mặt khác Java command line có thể có tùy chọn điều chỉnh quyền trong runtime. AST chỉ phản ánh source, không phản ánh mọi điều chỉnh khi chạy.

`ModuleDescriptor` có cấu trúc thông tin khác AST; nó có thể bao gồm thông tin được compiler/runtime tổng hợp hoặc suy ra từ tệp module. Một bộ linter **nguồn** nên hỏi từ AST; một bộ kiểm tra **sản phẩm build** nên hỏi từ descriptor thực.

## 8. Thiết kế một rule kiểm tra kiến trúc nhỏ

Ví dụ yêu cầu: “Hạn chế `opens` không điều kiện ở các module nghiệp vụ”.

Các bước triển khai hợp lý:

1. Dùng `JavaCompiler`/`JavacTask.parse()` đọc từng `module-info.java` thuộc phạm vi dự án đã chỉ định.
2. Kiểm tra `module.getModuleType()`. Nếu là `OPEN`, thông báo policy vì **toàn bộ package** được mở sâu; kiểm tra có ngoại lệ được duyệt hay không.
3. Với `STRONG`, duyệt `getDirectives()`. Khi `getKind() == Tree.Kind.OPENS`, ép sang `OpensTree`.
4. Nếu `getModuleNames() == null`, đánh dấu **mở không điều kiện**. Nếu có danh sách module, đối chiếu allowlist hoặc quy tắc kiến trúc.
5. Dùng `SourcePositions` để chỉ rõ file/dòng. Không tự rewrite source nếu diagnostics chưa sạch hoặc vì tool chưa biết phụ thuộc thật của framework.
6. Khi cần kiểm tra module có thật sự compile và các provider có hợp lệ, bổ sung bước semantic compile/integration test riêng.

Ví dụ logic kiểm tra là một phần của vòng lặp `for (DirectiveTree directive : module.getDirectives())`:

~~~java
// Đoạn minh họa đặt trong chương trình có biến module kiểu ModuleTree.
if (module.getModuleType() == ModuleTree.ModuleKind.OPEN) {
    System.out.println("Policy: entire module is open");
}
for (DirectiveTree directive : module.getDirectives()) {
    if (directive.getKind() == com.sun.source.tree.Tree.Kind.OPENS) {
        OpensTree opened = (OpensTree) directive;
        if (opened.getModuleNames() == null) {
            System.out.println("Policy: unqualified opens "
                    + opened.getPackageName());
        }
    }
}
~~~

Công cụ này chỉ **phát hiện mẫu cú pháp**; chưa kết luận đó là lỗ hổng bảo mật hoặc sai kiến trúc. Nhiều framework serialization, injection hay proxy có thể cần mở package. Quy tắc policy nên xét use case, mức tin cậy và module đích trước khi chặn build.

## 9. Các lỗi thường gặp khi phân tích `ModuleTree`

| Hiện tượng hoặc sai lầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `CompilationUnitTree.getModule() == null` | Đang parse tệp Java bình thường không có module declaration | Kiểm tra file đúng là `module-info.java`; đối xử `null` như tình huống hợp lệ với ordinary compilation unit. |
| Môi trường không có compiler | Chạy bằng runtime image tối giản thiếu `jdk.compiler` | Sử dụng JDK đầy đủ hoặc build image có module compiler cần thiết. |
| `getModuleNames() == null` bị diễn giải là “không export/open tới ai” | `exports p;`/`opens p;` không có mệnh đề `to` | Hiểu `null` là **mở quyền cho mọi module phù hợp**, không phải danh sách rỗng. |
| Dùng `module.getKind()` để phân biệt `open module` | `Tree.Kind.MODULE` áp dụng cho cả hai | Dùng `getModuleType()` và enum `OPEN`/`STRONG`. |
| Linter chỉ tìm `OpensTree` nên bỏ qua `open module` | `open module` là thuộc tính toàn module, không phải chuỗi `opens` con | Kiểm tra `ModuleKind.OPEN` trước khi duyệt directives. |
| Tưởng `parse()` xác minh dependency và service implementation | Parse chỉ tạo cây cú pháp | Gọi `analyze()`/compile với đúng module path và xem diagnostics khi cần ngữ nghĩa. |
| Dùng regex để parse `module-info.java` | Comment, annotation, multiline, modifiers và service list dễ làm regex sai | Dùng AST theo ngữ pháp Java hiện hành. |
| Gọi API nội bộ `com.sun.tools.javac.tree.JCTree` | Phụ thuộc implementation và quyền export nội bộ | Chỉ dùng `com.sun.source.tree`/`com.sun.source.util` được export bởi `jdk.compiler`. |
| Linter bịa thêm `requires java.base` trong danh sách “đã viết” | Trộn implicit readability với source AST | Báo riêng explicit và implicit nếu cần; đừng sửa `getDirectives()` bằng giả định. |
| Báo lỗi từ tree khi parser đã phục hồi cú pháp sai | `parse()` có thể trả tree dù có diagnostic lỗi | Kiểm tra `DiagnosticCollector`, tránh kết luận source hợp lệ chỉ vì có node. |
| Bảo rằng package tồn tại vì có `exports p;` | AST chỉ giữ ký hiệu package | Chuyển sang semantic analysis/build để xác minh. |
| Biên dịch chương trình dùng Tree API mà thiếu `jdk.compiler` trong module descriptor | Named module công cụ chưa `requires jdk.compiler` | Khai báo module dependency của công cụ, chạy bằng JDK. |

## 10. Bài thực hành tự kiểm tra

**Bài 1.** Với `requires static java.sql;`, giá trị của `RequiresTree.isStatic()` và `isTransitive()` là gì?

Đáp án: `true` và `false`. `isStatic` ở đây là modifier phụ thuộc module; nó không liên quan tới static field hay static method.

**Bài 2.** Hai chỉ thị `exports demo.api;` và `exports demo.api to demo.client;` có cùng `getPackageName()`. Phân biệt chúng bằng gì?

Đáp án: `getModuleNames()` là `null` với chỉ thị không có `to`; với chỉ thị có `to`, nó chứa tên `demo.client`.

**Bài 3.** Một source khai báo `open module x { requires java.sql; }`. `getModuleType()` trả gì? Có `OpensTree` nào không?

Đáp án: trả `OPEN` và không cần có `OpensTree`. Mọi package trong open module được mở sâu theo JPMS dù không có chỉ thị `opens` riêng.

**Bài 4.** `ModuleTree.getDirectives()` có chắc chứa node `requires java.base` không?

Không. Nếu nguồn không ghi chỉ thị đó, AST không tự thêm node chỉ vì runtime có phụ thuộc ngầm `java.base`.

**Bài 5.** Khi parse một fixture có `provides SomeService with MissingClass;`, không thấy parse error có nghĩa provider hợp lệ không?

Không. Parser kiểm tra cú pháp; khả năng tìm symbol, quyền truy cập, quan hệ implements và khả năng khởi tạo provider thuộc bước phân tích ngữ nghĩa.

**Bài 6.** Khi nào dùng `ModuleDescriptor` thay vì `ModuleTree`?

Khi muốn biết **module descriptor của artifact đã build hoặc module runtime**. `ModuleTree` phù hợp với công cụ đọc/chẩn đoán **source declaration**.

**Bài 7.** Một linter muốn tìm chỉ thị `opens` trên dòng mấy nên dựa vào `toString()` hay `SourcePositions`?

Dựa vào `SourcePositions` phối hợp `LineMap`; `toString()` không bảo đảm giữ đầy đủ whitespace và comment của source.

## 11. Tài liệu API và ngữ nghĩa đang được hỗ trợ

- [JDK 25 — `com.sun.source.tree.ModuleTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/ModuleTree.html)
- [JDK 25 — `ModuleTree.ModuleKind` (`STRONG`/`OPEN`)](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/ModuleTree.ModuleKind.html)
- [JDK 25 — `DirectiveTree` và các subtype](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/DirectiveTree.html)
- [JDK 25 — `RequiresTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/RequiresTree.html)
- [JDK 25 — `ExportsTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/ExportsTree.html)
- [JDK 25 — `OpensTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/OpensTree.html)
- [JDK 25 — `UsesTree` và `ProvidesTree`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/UsesTree.html)
- [JDK 25 — `JavacTask.parse()`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html)
- [JDK 25 — `CompilationUnitTree.getModule()`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/tree/CompilationUnitTree.html)
- [JDK 25 — `SourcePositions` và `Trees`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html)
- [JDK 25 — Module `jdk.compiler`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/module-summary.html)
- [JLS `7.7` — Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7)