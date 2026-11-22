# Doclet API trong jdk.javadoc.doclet — xây dựng bộ sinh tài liệu Javadoc tùy biến (Java 9+)

## 1. Doclet là gì và khi nào cần?

`javadoc` là công cụ chuẩn của JDK để phân tích **khai báo Java và chú thích tài liệu** trong mã nguồn. Phần chịu trách nhiệm biến mô hình đã phân tích thành kết quả đầu ra gọi là **doclet**. Theo mặc định, công cụ chạy **Standard Doclet**, tạo bộ trang HTML mô tả module, package, class, interface, phương thức và các thành phần API được chọn.

Trong một số hệ thống, HTML mặc định chưa phải đầu ra mong muốn. Ví dụ:

- Xuất **danh sách API ra Markdown, JSON hoặc một định dạng do tổ chức quy định**.
- Kiểm kê module, package, kiểu dữ liệu và mô tả API công khai theo một quy tắc riêng.
- Kiểm tra sự hiện diện của Javadoc trong các lớp/phương thức quan trọng rồi tạo báo cáo.
- Thu thập thông tin khai báo để phục vụ cổng tài liệu nội bộ, khi dự án vẫn lưu mô tả trong source Java.

**Doclet API** cho phép thay thế phần tạo đầu ra của `javadoc` bằng một class Java tự viết. API chuẩn nằm trong **package `jdk.javadoc.doclet`, module `jdk.javadoc`**, xuất hiện từ **Java 9** và vẫn tồn tại trong các bản JDK hiện đại.

```text
Mã nguồn Java + /** Javadoc */ + module-info.java
                       │
                       ▼
               Công cụ javadoc
              phân tích cấu trúc
                       │
                       ▼
                DocletEnvironment
            ┌──────────┴──────────┐
            │                     │
     StandardDoclet        Custom Doclet implements Doclet
            │                     │
         HTML docs        Markdown / JSON / báo cáo / kiểm tra
```

Doclet **không cần tự viết trình phân tích cú pháp Java**: nó nhận mô hình đã được công cụ phân tích qua các API chuẩn. Một doclet không nhất thiết tạo ra HTML, thậm chí có thể chỉ phát hiện vi phạm và báo lỗi.

**Phân biệt đúng phạm vi:** Nội dung bài này là **Doclet API hiện hành `jdk.javadoc.doclet`**. Package cũ `com.sun.javadoc` từng phục vụ một API khác và đã được API mới thay thế; không dùng hướng triển khai cũ ấy cho mã JDK hiện đại.

## 2. Ba lớp API phối hợp trong một custom doclet

Doclet kết hợp những tầng sau:

| Tầng | API điển hình | Mục đích |
| --- | --- | --- |
| **Vòng đời doclet** | `Doclet`, `Doclet.Option`, `DocletEnvironment`, `Reporter` | Nhận cấu hình, chạy, trả trạng thái và báo chẩn đoán. |
| **Language Model API** | `javax.lang.model.element.*`, `javax.lang.model.type.*`, `javax.lang.model.util.*` | Truy cập module, package, class, method, kiểu tham số, modifier và quan hệ kiểu theo ngữ nghĩa Java. |
| **Compiler Tree / DocTree API** | `com.sun.source.util.DocTrees`, `com.sun.source.doctree.DocCommentTree` | Đọc cấu trúc chú thích Javadoc: câu mô tả, thẻ `@param`/`@return`, inline tags, vị trí nguồn. |

Tình huống minh họa: `DocletEnvironment.getIncludedElements()` giúp tìm các kiểu được chọn để tài liệu hóa; `TypeElement.getQualifiedName()` trả tên lớp đầy đủ; `DocTrees.getDocCommentTree(type)` trả cây chú thích của lớp nếu có. Khi cần chi tiết hơn, `TypeElement.getEnclosedElements()` cho phép duyệt phương thức/field, rồi lọc qua `environment.isIncluded(member)`.

**Không nhầm doclet với annotation processor.** Annotation processor (JSR 269) chạy trong xử lý chú thích khi biên dịch, chủ yếu phục vụ sinh mã/kiểm tra trong quy trình build. Doclet được công cụ `javadoc` gọi để phân tích và **sinh tài liệu hoặc báo cáo**. Hai công nghệ có thể cùng dùng `javax.lang.model` nhưng vòng đời, mục tiêu và cơ chế kích hoạt khác nhau.

## 3. Hợp đồng `Doclet` và vòng đời chạy

Một class tự viết triển khai `jdk.javadoc.doclet.Doclet`, có **public no-argument constructor** để công cụ có thể khởi tạo. Năm phương thức của interface:

| Phương thức | Khi nào và dùng để làm gì? |
| --- | --- |
| `init(Locale locale, Reporter reporter)` | Công cụ gọi khi khởi tạo; lưu `Reporter` để phát thông báo có phân loại. |
| `getName()` | Trả tên định danh ngắn, không chứa khoảng trắng, của doclet. |
| `getSupportedOptions()` | Cung cấp các tùy chọn do doclet hỗ trợ, có thể trả `Set.of()` khi không có. |
| `getSupportedSourceVersion()` | Cho biết phiên bản ngôn ngữ Java mà doclet hỗ trợ; thường dùng `SourceVersion.latestSupported()`. |
| `run(DocletEnvironment environment)` | Điểm vào thực hiện công việc; trả `true` nếu thành công, `false` nếu thất bại. |

Công cụ làm việc theo thứ tự đại ý:

```text
javadoc -doclet tools.ApiSummaryDoclet ...
         │
         ▼
Tải class và tạo instance bằng constructor không tham số
         │
         ▼
init(locale, reporter)
         │
         ▼
getSupportedOptions() + getSupportedSourceVersion()
         │
         ▼
Phân tích mã nguồn và chuẩn bị môi trường
         │
         ▼
run(DocletEnvironment) → ghi báo cáo và trả success/failure
```

Không nên tự tạo `DocletEnvironment` bằng mã ứng dụng hoặc gọi `run()` mà bỏ qua giao thức khởi tạo: môi trường và vòng đời do công cụ `javadoc` cung cấp.

`Reporter` cho phép:

```java
reporter.print(Diagnostic.Kind.NOTE, "Generated summary");
reporter.print(Diagnostic.Kind.WARNING, element, "Missing API comment");
reporter.print(Diagnostic.Kind.ERROR, "Cannot write output");
```

Đây là **trích đoạn minh họa**, giả định `reporter` đã được `init` cung cấp, `element` là `Element` hợp lệ và đã import `javax.tools.Diagnostic`. So với việc in trực tiếp ra `System.out` hoặc `System.err`, `Reporter` để công cụ quản lý mức độ lỗi, vị trí nguồn và cách hiển thị thông báo. Vị trí hiển thị stdout/stderr cụ thể tùy môi trường thực thi.

## 4. `DocletEnvironment`: đầu vào quan trọng nhất

`DocletEnvironment` đại diện cho một lần thực thi `javadoc`. Nó cung cấp các tập phần tử, công cụ xử lý mô hình và tùy chọn chọn lọc:

| API | Điều cần hiểu |
| --- | --- |
| `getSpecifiedElements()` | Những phần tử được **chỉ định** bằng cách gọi `javadoc`, là điểm bắt đầu quá trình chọn. |
| `getIncludedElements()` | Những **module, package và type** được đưa vào tài liệu theo quy tắc chọn lọc; không tự suy diễn tập này đã liệt kê sẵn mọi method/field. |
| `isIncluded(Element e)` | Xác định một phần tử cụ thể có thuộc phạm vi tài liệu hóa hay không, kể cả method/field. |
| `isSelected(Element e)` | Xác định phần tử được phép chọn theo các tùy chọn visibility/selection. |
| `getDocTrees()` | Cấp `DocTrees` để truy cập Javadoc comments và source trees. |
| `getElementUtils()` | Công cụ `Elements` truy vấn symbol/type/package/module. |
| `getTypeUtils()` | Công cụ `Types` kiểm tra kiểu, quan hệ kế thừa và biến đổi `TypeMirror`. |
| `getSourceVersion()` | Phiên bản ngôn ngữ được dùng để phân tích nguồn. |
| `getModuleMode()` | Mức độ nội dung module (API hoặc chi tiết) tùy cấu hình `javadoc`. |
| `getJavaFileManager()` | Quản lý file được dùng trong lần gọi công cụ. |
| `getFileKind(TypeElement)` | Nguồn của type được thể hiện bằng loại `JavaFileObject.Kind` tương ứng. |

Ba khái niệm **specified**, **selected** và **included** có ý nghĩa khác nhau: một phần tử được nêu trực tiếp trong lệnh là *specified*; các quy tắc hiển thị quyết định nó có *selected*; chỉ các phần tử đáp ứng quan hệ phạm vi và selection mới *included* trong đầu ra. Tùy chọn như `--show-members`, `--show-types`, `--show-packages`, `--show-module-contents` ảnh hưởng tới những phần tử được tài liệu hóa.

Với **Java module**, `module-info.java` được biểu diễn bởi `ModuleElement`; các package và kiểu tương ứng là `PackageElement` và `TypeElement`. Có thể đọc comment trên module/package khi nguồn có Javadoc thích hợp. **Không đồng nhất module với package**: module có tên và các directive như `requires`/`exports`/`opens`; package nhóm các type.

## 5. Chương trình hoàn chỉnh: viết doclet xuất danh sách class sang file

Ta tạo một dự án Java module nhỏ và một custom doclet để **trích tên class cùng câu Javadoc đầu tiên** thành file văn bản. Đây là ví dụ thuần **Java 17+**, không dùng API nội bộ hoặc thư viện ngoài, có thể chạy bằng `javac` và `javadoc` trong JDK hiện đại.

### 5.1. Cấu trúc thư mục

```text
doclet-demo/
├── tools/
│   └── ApiSummaryDoclet.java
├── src/
│   └── com.example.greeting/
│       ├── module-info.java
│       └── com/
│           └── example/
│               └── greeting/
│                   └── GreetingService.java
└── tool-classes/            (được javac tạo)
```

`tool-classes` chứa **class của doclet đã biên dịch**; `src` chứa **mã nguồn của module sẽ được phân tích**. Hai vai trò này khác nhau: doclet là *công cụ*, còn module `com.example.greeting` là *đối tượng được tài liệu hóa*.

### 5.2. File `src/com.example.greeting/module-info.java`

```java
/** Demonstration module for a custom doclet. */
module com.example.greeting {
    exports com.example.greeting;
}
```

Khai báo `exports` giúp package này thuộc API công khai của module. Trong dự án thực, các directive và lựa chọn tài liệu hóa có thể phức tạp hơn.

### 5.3. File `src/com.example.greeting/com/example/greeting/GreetingService.java`

```java
package com.example.greeting;

/** Provides a greeting service. */
public class GreetingService {
    /** Returns a greeting for a user.
     * @param name user name
     * @return greeting text
     */
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Doclet demo sẽ đọc chú thích ở **class**, không đưa method `greet` vào file tổng hợp. Phần duyệt method chi tiết sẽ được giải thích sau.

### 5.4. File `tools/ApiSummaryDoclet.java`

```java
package tools;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import jdk.javadoc.doclet.Doclet;
import jdk.javadoc.doclet.DocletEnvironment;
import jdk.javadoc.doclet.Reporter;

public final class ApiSummaryDoclet implements Doclet {
    private Reporter reporter;
    private Path output = Path.of("api-summary.txt");

    @Override
    public void init(Locale locale, Reporter reporter) {
        this.reporter = reporter;
    }

    @Override
    public String getName() {
        return "ApiSummary";
    }

    @Override
    public Set<? extends Option> getSupportedOptions() {
        return Set.of(new Option() {
            @Override
            public int getArgumentCount() {
                return 1;
            }

            @Override
            public String getDescription() {
                return "File to receive the API summary";
            }

            @Override
            public Kind getKind() {
                return Kind.STANDARD;
            }

            @Override
            public List<String> getNames() {
                return List.of("-summary-file");
            }

            @Override
            public String getParameters() {
                return "<file>";
            }

            @Override
            public boolean process(String option, List<String> arguments) {
                output = Path.of(arguments.get(0));
                return true;
            }
        });
    }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean run(DocletEnvironment environment) {
        List<TypeElement> types = environment.getIncludedElements().stream()
                .filter(e -> e.getKind() == ElementKind.CLASS)
                .map(e -> (TypeElement) e)
                .sorted(Comparator.comparing(
                        t -> t.getQualifiedName().toString()))
                .toList();

        List<String> lines = new ArrayList<>();
        lines.add("# API summary");

        for (TypeElement type : types) {
            var comment =
                    environment.getDocTrees().getDocCommentTree(type);
            String sentence = comment == null ? "(no Javadoc)" :
                    comment.getFirstSentence().stream()
                            .map(Object::toString)
                            .collect(Collectors.joining()).trim();
            lines.add("- " + type.getQualifiedName() + ": " + sentence);
        }

        try {
            Files.write(output, lines, StandardCharsets.UTF_8);
            reporter.print(Diagnostic.Kind.NOTE,
                    "Wrote " + types.size() + " type(s) to " + output);
            return true;
        } catch (IOException e) {
            reporter.print(Diagnostic.Kind.ERROR,
                    "Unable to write " + output + ": " + e.getMessage());
            return false;
        }
    }
}
```

Giải thích các điểm chính:

1. Class `public final` không định nghĩa constructor, nên Java cung cấp **constructor không tham số với cùng khả năng truy cập public**, đáp ứng điều kiện để `javadoc` khởi tạo doclet.
2. `init` lưu `Reporter`; một vòng chạy doclet sử dụng bộ reporter của công cụ.
3. `getSupportedOptions` khai báo **một** tùy chọn `-summary-file <file>`, nhận một giá trị. `process` được gọi trước `run` khi người dùng truyền tùy chọn; nó thay đường dẫn file đầu ra.
4. `getSupportedSourceVersion` trả `SourceVersion.latestSupported()`, tức phiên bản Java tối đa mà công cụ hiện tại hỗ trợ. Nếu doclet có ràng buộc riêng, nên công bố chính xác phiên bản được hỗ trợ.
5. `environment.getIncludedElements()` lấy các phần tử đủ điều kiện; ví dụ lọc **`ElementKind.CLASS`** để chỉ xuất class, chưa xuất interface/record/enum.
6. `TypeElement.getQualifiedName()` tạo tên đã bao gồm package. `sorted(...)` cho output **ổn định**, không phụ thuộc thứ tự set mà `javadoc` cung cấp.
7. `getDocCommentTree(type)` trả cây Javadoc nếu có; nếu không có comment, code ghi `(no Javadoc)` thay vì lỗi `NullPointerException`.
8. `getFirstSentence()` lấy các nút comment thuộc phần mô tả đầu. Ví dụ nối `toString()` để có một **bản tóm tắt đơn giản**, không phải renderer Markdown/HTML đầy đủ: nếu comment có inline tags hoặc markup phức tạp, một doclet production phải xử lý chúng bằng cây `DocTree` và cơ chế escape định dạng đích.
9. `Files.write` ghi báo cáo bằng UTF-8. `Reporter` thông báo thành công hoặc lỗi; `run` trả boolean để công cụ xác định kết quả.

Ví dụ dành cho file/dự án được tin cậy; trong hệ thống build thực, phải kiểm soát đường dẫn output và tránh ghi đè file nhạy cảm.

### 5.5. Biên dịch và chạy

Đứng tại **thư mục `doclet-demo`** có cấu trúc như trên:

```bash
javac --release 17 -d tool-classes tools/ApiSummaryDoclet.java
javadoc -quiet -doclet tools.ApiSummaryDoclet -docletpath tool-classes -summary-file api-summary.txt --module-source-path src --module com.example.greeting
```

Lệnh thứ nhất biên dịch **doclet**, không cần chạy chương trình có `main` và không cần biên dịch module demo thành .class trước. Lệnh thứ hai:

- `-doclet tools.ApiSummaryDoclet`: chỉ định tên class doclet đầy đủ.
- `-docletpath tool-classes`: nơi công cụ tìm class và dependency của doclet (khác với đường dẫn tới mã nguồn cần sinh tài liệu).
- `-summary-file api-summary.txt`: tùy chọn **tự định nghĩa** mà `getSupportedOptions` đã đăng ký.
- `--module-source-path src`: đường dẫn tìm cấu trúc mã nguồn module; với ví dụ này module nằm ở `src/com.example.greeting`.
- `--module com.example.greeting`: chỉ định module cần phân tích.
- `-quiet`: hạn chế một số thông báo thông thường của công cụ; **không phải cơ chế tắt `Reporter`**, lỗi chẩn đoán vẫn có thể xuất hiện.

Sau khi chạy thành công, **nội dung chính xác của file `api-summary.txt`**:

```text
# API summary
- com.example.greeting.GreetingService: Provides a greeting service.
```

Bạn cũng sẽ thấy một ghi chú chẩn đoán, ví dụ:

```text
Note: Wrote 1 type(s) to api-summary.txt
```

Ghi chú trên được `Reporter` in ra và có thể xuất hiện ở stderr hoặc nơi nhận diagnostic của công cụ. Chương trình đã được kiểm chứng trên OpenJDK 24: biên dịch thành công với `javac --release 17`, chạy `javadoc` với module nguồn và nhận đúng file/tin nhắn nói trên.

**Vì đã chọn một custom doclet**, lệnh này sinh **báo cáo văn bản** do code quyết định; nó **không tự sinh bộ trang HTML chuẩn của Standard Doclet**. Muốn vừa có HTML chuẩn vừa có báo cáo riêng, có thể chạy hai lần riêng biệt hoặc cân nhắc tích hợp/hệ thống build thích hợp.

## 6. Tùy chọn riêng bằng `Doclet.Option`

Một custom doclet có thể nhận các cờ của công cụ `javadoc` đồng thời khai báo tùy chọn riêng qua `getSupportedOptions()`. Một `Doclet.Option` định nghĩa:

| Phương thức | Vai trò trong ví dụ |
| --- | --- |
| `getNames()` | Danh sách tên được chấp nhận, ở đây `List.of("-summary-file")`; có thể đăng ký các alias hợp lệ. |
| `getArgumentCount()` | Số đối số công cụ tiêu thụ, ở đây **1**. |
| `getParameters()` | Chuỗi hiển thị trong help, ở đây `<file>`. |
| `getDescription()` | Mô tả ngắn công dụng của cờ. |
| `getKind()` | Loại cờ: `STANDARD`, `EXTENDED` hoặc `OTHER`. |
| `process(String, List<String>)` | Phân tích/ghi nhận đối số; trả `true` khi hợp lệ, `false` nếu xử lý thất bại. |

Điểm thực hành: **`getNames` chỉ khai báo tên, còn `process` phải áp dụng cấu hình.** Cờ không tự tạo tác dụng. Nếu muốn hỗ trợ nhiều tùy chọn, trả `Set` gồm nhiều `Option` object, mỗi object gắn đúng số lượng tham số và cách xử lý.

Với đầu ra từ người dùng hoặc CI, nên kiểm tra:

- `Path` hợp lệ, vị trí output được phép ghi; tránh cho dữ liệu không tin cậy cung cấp đường dẫn tùy ý.
- Hậu tố/tên file phù hợp định dạng, trường hợp file đã tồn tại và chính sách ghi đè.
- Nơi chạy có quyền ghi, thư mục cha tồn tại.
- Có thông báo `Diagnostic.Kind.ERROR` dễ hiểu khi tùy chọn sai hoặc không thể ghi file; trả `false` từ `run` khi thực thi thất bại.

Không gọi phương thức `run` ngay trong `process`: tại thời điểm xử lý tùy chọn, chưa nên giả định đã có `DocletEnvironment` đầy đủ.

## 7. Từ class sang module, package và các thành viên API

Ví dụ chỉ xuất tên **class** vì biểu thức lọc dùng `ElementKind.CLASS`. Khi xây dựng bộ tài liệu API thực sự, phải chọn đúng loại phần tử:

| Loại phần tử | Interface mô hình | Ví dụ dữ liệu |
| --- | --- | --- |
| Module | `ModuleElement` | Tên module và các directive `requires`, `exports`, `uses`, `provides`. |
| Package | `PackageElement` | Tên package, module chứa nó, chú thích package. |
| Class/interface/record/enum | `TypeElement` | Qualified name, modifiers, superclass, interfaces, annotations, enclosed elements. |
| Method/constructor | `ExecutableElement` | Tên, tham số, return type, type parameters, thrown types. |
| Field/parameter | `VariableElement` | Tên, kiểu và vị trí trong type/method. |

Một cách duyệt phương thức hợp lý (trích đoạn **không độc lập**; nằm trong `run(DocletEnvironment environment)`, có `TypeElement type` đã kiểm tra và import `Element`, `ElementKind`):

```java
for (Element member : type.getEnclosedElements()) {
    if (member.getKind() == ElementKind.METHOD
            && environment.isIncluded(member)) {
        var comment =
                environment.getDocTrees().getDocCommentTree(member);
        String methodName = member.getSimpleName().toString();
        // Tùy mục tiêu, kiểm tra comment == null và phân tích DocTree.
    }
}
```

Phương thức `getIncludedElements()` cung cấp module/package/type; **không nên giả định mọi method đã được liệt kê trực tiếp**. Duyệt `getEnclosedElements()` và dùng `isIncluded(member)` để tôn trọng visibility và quy tắc tài liệu hóa.

Với module, `getModuleMode()` giúp biết mức nội dung module được cấu hình. Còn `--show-module-contents api|all`, `--show-packages exported|all` và `--show-members ...` giúp xác định phạm vi trước khi doclet xuất dữ liệu. Đây là chính sách **chọn các phần tử được phân tích**; custom doclet vẫn phải quyết định **cách trình bày** và cách xử lý Javadoc comments.

## 8. Cách lấy và xử lý Javadoc comments đúng ngữ nghĩa

Chú thích Javadoc có nhiều cấu trúc:

```java
/** Returns a personalized greeting.
 * @param name non-null name
 * @return greeting text
 * @throws IllegalArgumentException when name is blank
 */
public String greet(String name) {
    if (name.isBlank()) {
        throw new IllegalArgumentException("blank");
    }
    return "Hello, " + name;
}
```

`DocTrees.getDocCommentTree(element)` trả `DocCommentTree`; từ đó có thể đọc:

- `getFirstSentence()`: phần câu đầu (phục vụ tóm tắt).
- `getBody()`: phần nội dung còn lại của mô tả.
- `getBlockTags()`: các `@param`, `@return`, `@throws`, `@since` và block tags khác.
- Các nút như `TextTree`, `LinkTree`, `LiteralTree`, `ParamTree`, `ReturnTree`: giữ cấu trúc, phù hợp để viết visitor và xuất sang định dạng mong muốn.

Ví dụ Javadoc không tồn tại thì `getDocCommentTree(...)` có thể trả `null`. Một doclet thực tế nên tách **chú thích thiếu** khỏi **chú thích có nhưng sai cấu trúc**, và tránh gọi `toString()` trên toàn bộ cây rồi coi kết quả là Markdown/HTML hợp lệ.

Khi chuyển sang HTML/Markdown/JSON:

1. Dùng `DocTree` hoặc `DocTreePath` để hiểu loại nút, liên kết đến element đích và nội dung.
2. **Escape** các ký tự đặc biệt theo định dạng xuất: HTML entity hoặc JSON escaping, thay vì nhúng văn bản Javadoc vào output bằng nối chuỗi thiếu kiểm tra.
3. Giải quyết `{@link ...}` hoặc `@see` theo **mô hình symbol** và phạm vi tài liệu, không chuyển bừa thành URL đoán.
4. Ghi chẩn đoán kèm `Element` hoặc `DocTreePath` bằng `Reporter` nếu có thể, để người viết tài liệu sửa đúng vị trí.
5. Kiểm tra ngôn ngữ nguồn, encoding và quy tắc tách câu; ví dụ `getFirstSentence` có quy tắc phân đoạn theo locale/cấu hình công cụ.

**Điểm giới hạn của demo:** nối `getFirstSentence().stream().map(Object::toString)` đơn giản và phù hợp khi chú thích chỉ chứa văn bản thuần. Với inline tags phức tạp, phải dùng visitor/renderer thực sự nếu muốn nội dung Markdown chính xác.

## 9. Doclet khác Standard Doclet và Taglet thế nào?

| Nhu cầu | Hướng áp dụng |
| --- | --- |
| Cần HTML API chuẩn | Dùng `javadoc` mặc định (**Standard Doclet**), không cần custom Doclet. |
| Cần thêm cách hiển thị **một custom tag** trong HTML mặc định | Tìm hiểu `jdk.javadoc.doclet.Taglet` và cấu hình cho Standard Doclet. |
| Cần **thay toàn bộ kiểu đầu ra** thành JSON, Markdown hay báo cáo | Viết class triển khai `Doclet` và chạy `javadoc -doclet ...`. |
| Cần kiểm tra chất lượng Javadoc mà không sinh HTML | Custom doclet có thể kiểm tra elements, phát diagnostics, trả `false` khi vi phạm chính sách. |
| Cần giải mã hoặc biến đổi mã bytecode đã biên dịch | Doclet không phải công cụ bytecode; dùng API/phương pháp phù hợp khác. |

Điểm mấu chốt là **Taglet mở rộng cách Standard Doclet hiển thị một tag**, còn **Doclet xác định toàn bộ đầu ra và quy trình tạo tài liệu**. Đừng dùng custom Doclet để sao chép lại mọi tính năng HTML, link, search/index của Standard Doclet khi mục tiêu chỉ là thêm một thẻ riêng.

## 10. Kết hợp với build và kiểm thử

Trong CI hoặc script build, thực hiện theo hai giai đoạn:

```text
javac compile custom doclet
          ↓
javadoc -doclet <FQN> -docletpath <classes-or-jar> ...
          ↓
read/verify generated artifact
          ↓
publish only if success and checks pass
```

Các nguyên tắc thực tế:

- **Khóa rõ phiên bản JDK** dùng biên dịch và chạy `javadoc`. `getSupportedSourceVersion()` phụ thuộc runtime của công cụ; nếu đầu ra phải tái lập, nên kiểm tra thông tin JDK trong CI.
- **Sắp xếp phần tử trước khi ghi.** Nhiều phương thức trả `Set`; thứ tự duyệt không phải giao diện xuất dữ liệu ổn định. Ví dụ sort theo qualified name.
- **Chạy với tập mã nguồn tối thiểu để kiểm thử.** Tạo module có một class có Javadoc, thêm class thiếu Javadoc, method có `@param` và cả trường hợp custom tag; kiểm tra kết quả và diagnostics.
- **Không đánh đồng exit status với chất lượng dữ liệu.** Kiểm tra thêm file đầu ra có tồn tại, đúng encoding, số lượng phần tử, không chứa các phần tử ngoài phạm vi và không bị overwrite ngoài ý muốn.
- **Hạn chế môi trường thực thi của custom doclet.** Doclet là **mã Java có thể ghi file và làm tác vụ khác với quyền của tiến trình `javadoc`**. Chỉ chạy doclet tin cậy và kiểm soát input/output path trong CI.
- **Bảo toàn nội dung comment:** nếu đầu ra có liên kết, HTML/Markdown hay tham chiếu đến API ngoài dự án, cần quy tắc escaping và resolution nhất quán.
- **Tách output của công cụ và chẩn đoán.** `Reporter` dành cho note/warning/error; file báo cáo chuyên biệt dành cho nội dung cần tiêu thụ tiếp.

Nếu dự án chuyển từ Java không có module sang Java modules, nên kiểm tra lại `--module-source-path`, `--module`, `--module-path` và `exports`. Một file `module-info.java` đặt sai cấu trúc thư mục có thể khiến `javadoc` không tìm thấy module dù code Java bên trong hoàn toàn hợp lệ.

## 11. Những lỗi dễ mắc và hướng giải quyết

| Lỗi hoặc hiểu nhầm | Nguyên nhân và cách khắc phục |
| --- | --- |
| `javadoc: error - Cannot find doclet class ...` | Tên FQN sai, `-docletpath` không trỏ tới file class/JAR, hoặc thư mục biên dịch không phù hợp package. |
| `ClassNotFoundException` / `NoClassDefFoundError` | Thiếu class của doclet hoặc dependency trên `-docletpath`. Kiểm tra cách đóng gói và đường classpath. |
| `module not found` | `--module-source-path` sai bố cục, module name ở lệnh khác `module-info.java`, hoặc thiếu module dependency. |
| Custom doclet chạy nhưng không có file HTML | Khi chọn `-doclet`, doclet tự quyết định đầu ra. Nếu chỉ ghi file văn bản thì không có HTML chuẩn. |
| `getIncludedElements()` không có method | Tập này chứa module/package/type; duyệt `getEnclosedElements()` và kiểm tra `isIncluded(member)`. |
| `getDocCommentTree(type) == null` | Element không có Javadoc tương ứng hoặc nguồn không chứa comment cần thiết; phải kiểm tra `null` trước. |
| Chú thích có `{@link}` in ra ký tự thô | Ví dụ `toString()` không phải renderer hoàn chỉnh; dùng `DocTree` visitor và giải quyết tham chiếu. |
| `-summary-file` không được nhận diện | Doclet quên đăng ký `Option` hoặc tên được khai báo khác tham số truyền. |
| `getSupportedOptions()` trả option nhưng không ghi đường dẫn | `process` chỉ chạy logic mà bạn lập trình; phải lưu cấu hình và dùng trong `run`. |
| `run` ném `IOException` | Đường output không tồn tại hoặc bị cấm ghi; báo lỗi qua `Reporter`, xử lý lỗi, không báo success. |
| Kết quả thay đổi giữa các lượt trên cùng nguồn | Duyệt `Set` không sort, lệch JDK/locale/cấu hình selection hoặc yếu tố thời gian; khóa cấu hình và kiểm tra đầu ra. |
| Bản tổng hợp thiếu API công khai của package | `exports`, các quy tắc `--show-*`, visibility hoặc `isIncluded` lọc khác mong đợi; kiểm tra đúng module và tùy chọn. |

Một cách debug có hệ thống là bắt đầu bằng module và một class nhỏ như ví dụ, xác nhận `javadoc` nhận đúng `-docletpath` và nguồn, rồi tăng dần: classes → methods → module directives → links và metadata. Nhờ đó xác định được lỗi thuộc **lựa chọn phần tử**, **phân tích comment**, hay **ghi file output**.

## 12. Tự kiểm tra kiến thức

**Câu hỏi 1.** Muốn xuất danh sách tất cả class public của module sang file text và không cần HTML chuẩn, có nên viết custom `Doclet`? **Có**. Dùng `DocletEnvironment` để lấy types được include, rồi tự định nghĩa cách ghi. Trong ví dụ dùng `ElementKind.CLASS` và qualified name.

**Câu hỏi 2.** Để lấy `@param` của từng method, chỉ lặp `getIncludedElements()` đã đủ chưa? **Chưa**. Cần duyệt members của `TypeElement`, áp dụng `isIncluded` rồi lấy `DocCommentTree` và các block tags.

**Câu hỏi 3.** Vì sao có `getSupportedOptions()` mà lệnh `-summary-file` vẫn không ảnh hưởng đầu ra? **Vì** option chỉ khai báo tên/số tham số, còn code trong `process` và `run` phải chủ động lưu và dùng giá trị.

**Câu hỏi 4.** Nếu báo cáo cần Markdown đầy đủ có `{@link}` và code snippet, nối `DocTree.toString()` có đủ không? **Không**. Cần đọc loại DocTree, resolve link, xử lý escaping/formatting và kiểm thử kết quả.

**Câu hỏi 5.** Custom doclet là extension của compiler hay của `javadoc`? **Của công cụ `javadoc`**. Nó dùng một số API mô hình ngôn ngữ chung với compiler, nhưng tạo tài liệu theo vòng đời doclet.

## Tài liệu tham khảo chính thức còn áp dụng

- Oracle Java SE 26 — [Package `jdk.javadoc.doclet`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/package-summary.html): phạm vi API Doclet, thuật ngữ selected/specified/included và lựa chọn phần tử.
- Oracle Java SE 26 — [Interface `Doclet`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/Doclet.html): constructor, vòng đời, năm phương thức và `run`.
- Oracle Java SE 26 — [`Doclet.Option`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/Doclet.Option.html): nhận và xử lý custom options.
- Oracle Java SE 26 — [`DocletEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/DocletEnvironment.html): module/package/type elements, `DocTrees`, `isIncluded` và tiện ích model.
- Oracle Java SE 26 — [`Reporter`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/Reporter.html): báo diagnostics gắn với nguồn.
- Oracle Java SE 26 — [The `javadoc` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): `-doclet`, `-docletpath`, `--module-source-path`, `--module` và cách phân tích Java source.

**Điểm cần nhớ:** `jdk.javadoc.doclet.Doclet` là extension point chuẩn từ **Java 9** để thay phần sinh đầu ra của công cụ `javadoc`. `DocletEnvironment` cung cấp mô hình module/package/type và `DocTrees` để đọc Javadoc; `Doclet.Option` nhận cấu hình; `Reporter` phát thông báo; `run` tạo kết quả. Khi chỉ cần HTML mặc định hoặc một custom tag, hãy dùng các khả năng của Standard Doclet thay vì tự viết lại toàn bộ trình tạo tài liệu.