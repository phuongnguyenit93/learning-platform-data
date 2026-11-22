# `DocletEnvironment`, phần tử ngôn ngữ và nội dung chú thích trong Javadoc mô-đun

**Phạm vi:** Java 9 trở lên, sử dụng Doclet API hiện đại của JDK. Các ví dụ thực hành biên dịch bằng Java 17+ và chỉ dựa vào công cụ có sẵn trong JDK. Bài học giải thích cách `javadoc` phân tích module, package, class, method và các chú thích để một **custom doclet** kiểm tra hoặc tạo tài liệu API.

> **Cốt lõi:** `DocletEnvironment` cho biết **phạm vi tài liệu và tiện ích phân tích**; `javax.lang.model` biểu diễn **các khai báo Java**; `DocTrees` và `DocCommentTree` biểu diễn **cấu trúc chú thích Javadoc**. Cần kết hợp ba lớp đó để hiểu đúng mã nguồn và nội dung chú thích.

## 1. Javadoc mô-đun là gì?

Trong Java có module, Javadoc có thể tài liệu hóa nhiều cấp:

- `module-info.java`: khai báo module (`requires`, `exports`, `opens`, `uses`, `provides`) và có thể có Javadoc comment cho module.
- `package-info.java`: vị trí chuẩn để viết Javadoc comment cho package.
- Class, interface, enum, record, annotation type: có comment riêng.
- Constructor, method, field: có comment mô tả hành vi, tham số, kết quả và ngoại lệ.
- **Standard Doclet** mặc định biến các dữ liệu trên thành HTML; **custom doclet** có thể tạo tài liệu theo định dạng riêng hoặc kiểm tra chất lượng Javadoc trong CI.

Các API đang dùng:

| Module JDK | API | Vai trò |
| --- | --- | --- |
| `jdk.javadoc` | `jdk.javadoc.doclet.Doclet`, `DocletEnvironment`, `Reporter` | Điểm mở rộng cho công cụ `javadoc`. |
| `java.compiler` | `javax.lang.model.element`, `.type`, `.util` | Mô hình khai báo Java và kiểu dữ liệu. |
| `jdk.compiler` | `com.sun.source.doctree`, `com.sun.source.util.DocTrees` | Cây cú pháp chú thích, đường dẫn tới source và thông tin tham chiếu. |

Doclet API của Java 9 thay thế API doclet cũ trong `com.sun.javadoc`. Khi viết công cụ mới, chỉ dùng `jdk.javadoc.doclet` và Language Model/DocTree API đang được hỗ trợ; không lấy ví dụ dựa vào `RootDoc`, `ClassDoc` hoặc `com.sun.javadoc.Doclet` cũ.

**Ba khái niệm không được nhầm:** `module-info.java` là file khai báo một module **của ứng dụng**; `jdk.javadoc` là module **của JDK**; `DocletEnvironment` là đối tượng mô tả **một lần chạy javadoc**, được truyền vào doclet.

## 2. Sơ đồ phối hợp các lớp

```text
javadoc --module demo.docs -doclet InspectDoclet ...
                  |
                  v
       Doclet.run(DocletEnvironment env)
                  |
      +-----------+---------------------------+
      |                                       |
      v                                       v
getIncludedElements()                   getDocTrees()
      |                                       |
      v                                       v
javax.lang.model.element.Element         DocCommentTree
  ModuleElement                            |-- getFirstSentence()
  PackageElement                           |-- getBody()/getFullBody()
  TypeElement                              |-- getBlockTags()
  ExecutableElement                        +-- DocTree nodes
  VariableElement                               TextTree, LinkTree,
      |                                          ParamTree, ReturnTree...
      v
javax.lang.model.type.TypeMirror
```

`Element` mô tả **khai báo Java** trong ngữ cảnh biên dịch/phân tích, không phải một `Class<?>` đã được nạp qua reflection. Có thể đọc tên, modifier, annotation, member, kiểu generic, quan hệ module/package mà không cần chạy class. `TypeMirror` mô tả kiểu Java, ví dụ `DeclaredType`, `ArrayType`, `TypeVariable` hoặc `WildcardType`; nếu cần so sánh type đúng ngữ nghĩa, dùng `Types` thay vì so chuỗi.

`DocTree` là node của **Javadoc comment đã parse**. Comment có thể chứa text thuần, inline tag như `{@link ...}`, `{@code ...}`, block tag như `@param` và `@return`. Một node không phải HTML đã render; doclet chịu trách nhiệm xử lý loại node và escape khi xuất ra định dạng đích.

## 3. Vai trò của `DocletEnvironment`

Công cụ `javadoc` khởi tạo custom doclet bằng constructor công khai không tham số, gọi `init(...)`, truy vấn các tùy chọn và phiên bản ngôn ngữ hỗ trợ, rồi gọi `run(DocletEnvironment)`.

```java
@Override
public boolean run(DocletEnvironment env) {
    // env chỉ mô tả lượt chạy javadoc hiện tại.
    return true;
}
```

Đây là **đoạn minh họa bên trong lớp triển khai `Doclet`**, không phải chương trình độc lập.

| Phương thức | Ý nghĩa |
| --- | --- |
| `getSpecifiedElements()` | Các element **được người dùng chỉ rõ** khi gọi `javadoc`, ví dụ module từ `--module`. |
| `getIncludedElements()` | Các **module/package/type element** nằm trong phạm vi cần tạo tài liệu. Đây không phải set chứa toàn bộ field/method. |
| `isSelected(Element)` | Element có vượt qua quy tắc lựa chọn/visibility hay không. |
| `isIncluded(Element)` | Element vừa được chọn vừa thuộc phạm vi tài liệu hóa hay không; nên dùng khi quyết định có viết một member vào output. |
| `getElementUtils()` | Trả `Elements` để tra module/package/type, đọc annotation, metadata của element. |
| `getTypeUtils()` | Trả `Types` để phân tích `TypeMirror`, so sánh các type, subtype, erasure. |
| `getDocTrees()` | Trả `DocTrees` để lấy cây comment, đường dẫn AST, vị trí trong source, resolve link. |
| `getSourceVersion()` | Source level đã được đọc trong lần chạy. |
| `getModuleMode()` | Mức chi tiết tài liệu module: `API` hoặc `ALL`. |
| `getFileKind(TypeElement)` | Loại tệp của type, chẳng hạn `SOURCE` hoặc `CLASS`. |
| `getJavaFileManager()` | File manager của lượt chạy nếu doclet cần thao tác file qua API chuẩn. |

### `specified`, `selected`, `included` khác nhau

Theo định nghĩa Doclet API hiện hành:

1. **Specified**: element do tham số lệnh yêu cầu trực tiếp. Với `--module demo.docs`, module có thể là specified.
2. **Selected**: element được phép tài liệu hóa theo lựa chọn như visibility, kiểu/package/module. Element tổng hợp do compiler tạo không được coi là selected.
3. **Included**: element selected **và** chính nó được specified, bao chứa một specified, hoặc được bao bởi một specified. Đây là tập con thuộc phạm vi output.

Trong ví dụ module, `getSpecifiedElements().contains(module)` có thể là `true`, còn class `demo.api.Greeter` không được nêu tường minh ở CLI vẫn có thể thuộc `getIncludedElements()`. `getIncludedElements()` chỉ trả module/package/type; method public nằm bên trong class cần được xem xét qua `env.isIncluded(method)`.

**Không dùng `getSpecifiedElements()` để thống kê toàn bộ API**, không coi `isSelected` đồng nghĩa với `isIncluded`. Các set trả về không phải thứ tự ổn định để sinh file; khi xuất report, nên sắp xếp theo module, qualified type name và signature.

## 4. Mô hình các phần tử ngôn ngữ

| Kiểu `Element` | Đối tượng biểu diễn | API đáng chú ý |
| --- | --- | --- |
| `ModuleElement` | Module từ `module-info.java` | `getQualifiedName()`, `getDirectives()`, `isOpen()` |
| `PackageElement` | Package | `getQualifiedName()`, `getEnclosedElements()` |
| `TypeElement` | Class/interface/enum/record/annotation | `getQualifiedName()`, `getEnclosedElements()`, `getSuperclass()`, `getInterfaces()` |
| `ExecutableElement` | Method/constructor | `getSimpleName()`, `getParameters()`, `getReturnType()`, `getThrownTypes()` |
| `VariableElement` | Field, enum constant, parameter | `getSimpleName()`, `asType()`, `getConstantValue()` |
| `TypeParameterElement` | Type parameter như `<T>` | `getSimpleName()`, `getBounds()` |

`getEnclosedElements()` trả **khai báo được bao trực tiếp** trong element, không có nghĩa chỉ có method public, cũng không tự bao gồm các method inherited. Muốn lấy method thực của một class:

```java
// Minh họa: type là TypeElement, env là DocletEnvironment.
for (ExecutableElement method :
        javax.lang.model.util.ElementFilter.methodsIn(type.getEnclosedElements())) {
    if (env.isIncluded(method)) {
        System.out.println(method.getSimpleName());
    }
}
```

Đoạn code này phải ở trong một phương thức có `type` và `env` hợp lệ. Với method overloaded, chỉ in `getSimpleName()` sẽ gây trùng; khi lập chỉ mục tài liệu hãy dùng thêm parameter types hoặc signature.

### Comment cho module/package

Một Javadoc comment đặt **trước** khai báo `module` trong `module-info.java` được gắn với `ModuleElement`. Tương tự, comment trước khai báo `package` trong `package-info.java` gắn với `PackageElement`. Có thể gọi `env.getDocTrees().getDocCommentTree(moduleElement)` hoặc `getDocCommentTree(packageElement)` để lấy thông tin. Element không có chú thích có thể trả `null` — phải kiểm tra trước khi truy cập các phần của cây.

## 5. `DocCommentTree`: tách câu đầu, body và block tags

Ví dụ một method được viết Javadoc:

```java
/**
 * Returns a greeting. This sentence provides more details.
 *
 * @param name recipient name
 * @return greeting text
 */
public String greet(String name) {
    return "Hello, " + name;
}
```

Javadoc phân tích thành:

- **First sentence**: `Returns a greeting.`; Standard Doclet thường dùng để tạo đoạn summary.
- **Body**: phần tiếp theo trước block tags, ví dụ `This sentence provides more details.`.
- **Full body**: gồm cả câu đầu và body, **không** bao gồm block tags.
- **Block tags**: `@param ...`, `@return ...`, `@throws ...`, v.v.

```java
// Minh họa trong doclet: method là ExecutableElement hợp lệ.
DocCommentTree comment = env.getDocTrees().getDocCommentTree(method);
if (comment != null) {
    var firstSentence = comment.getFirstSentence();
    var fullBody = comment.getFullBody();
    var blockTags = comment.getBlockTags();
}
```

Các method trên trả **`List<? extends DocTree>`**, không phải `String` đã chuyển HTML. `getFirstSentence()` và `getBody()` có thể có nhiều node nếu có inline tag, HTML hoặc cấu trúc lồng nhau. Không mặc định ranh giới câu đầu bằng cách tách tại dấu chấm đầu tiên, vì Javadoc dùng quy tắc riêng.

| API | Kết quả |
| --- | --- |
| `DocCommentTree.getFirstSentence()` | Node thuộc câu đầu của comment |
| `DocCommentTree.getBody()` | Node sau câu đầu, trước block tags |
| `DocCommentTree.getFullBody()` | Node của cả first sentence lẫn phần body còn lại |
| `DocCommentTree.getBlockTags()` | Node của các block tags ở cuối comment |
| `DocTrees.getDocCommentTree(Element)` | `DocCommentTree` hoặc `null` khi không có comment |

### Các loại node thường gặp

| Kiểu node | Cú pháp Javadoc | API |
| --- | --- | --- |
| `TextTree` | Chữ thường | `getBody()` |
| `LinkTree` | `{@link Type#method}` hoặc `{@linkplain Type}` | `getReference()`, `getLabel()` |
| `LiteralTree` | `{@code x < y}` hoặc `{@literal ...}` | `getBody()` |
| `ParamTree` | `@param name ...`, `@param <T> ...` | `getName()`, `isTypeParameter()`, `getDescription()` |
| `ReturnTree` | `@return ...` | `getDescription()` |
| `ThrowsTree` | `@throws IOException ...` | `getExceptionName()`, `getDescription()` |
| `SeeTree` | `@see ...` | `getReference()` |
| `UnknownBlockTagTree` | Tag custom không có cách diễn giải được công cụ biết sẵn | `getTagName()`, `getContent()` |

Trên các JDK mới có thêm node như `SnippetTree` cho `{@snippet ...}` (giới thiệu từ Java 18). Nếu doclet phải **biên dịch bằng Java 17**, tránh import `SnippetTree` trong source Java 17. Điều này không có nghĩa tag mới lỗi thời; hãy xác định rõ runtime/source baseline trước khi dùng API xuất hiện ở JDK sau.

Khi xử lý nhiều node có cấu trúc lồng nhau, dùng `DocTreeVisitor` hoặc `DocTreeScanner` thay cho regex. `DocTree.toString()` chỉ hữu ích với bài minh họa đơn giản; không coi kết quả đó là HTML an toàn hay liên kết đã resolve.

## 6. Lab đầy đủ: custom doclet đọc mô-đun, class, method và tag

Lab yêu cầu **JDK 17+**, có `javac` và `javadoc`; không cần thư viện ngoài. Tạo cấu trúc như sau:

```text
demo-project/
├── InspectDoclet.java
├── src/
│   └── demo.docs/
│       ├── module-info.java
│       └── demo/
│           └── api/
│               ├── package-info.java
│               └── Greeter.java
└── out/               # tạo sau khi biên dịch
```

**Tệp `src/demo.docs/module-info.java`:**

```java
/** API documentation for the greeting module. */
module demo.docs {
    exports demo.api;
}
```

**Tệp `src/demo.docs/demo/api/package-info.java`:**

```java
/** Greeting API package. */
package demo.api;
```

**Tệp `src/demo.docs/demo/api/Greeter.java`:**

```java
package demo.api;

/** Greets a caller. Supports custom names. */
public class Greeter {
    /**
     * Returns a greeting.
     * @param name recipient name
     * @return greeting text
     */
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

**Tệp `InspectDoclet.java`:**

```java
import com.sun.source.doctree.DocCommentTree;
import com.sun.source.doctree.DocTree;
import com.sun.source.doctree.ParamTree;
import com.sun.source.doctree.ReturnTree;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.ModuleElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;
import jdk.javadoc.doclet.Doclet;
import jdk.javadoc.doclet.DocletEnvironment;
import jdk.javadoc.doclet.Reporter;

public class InspectDoclet implements Doclet {
    @Override
    public void init(Locale locale, Reporter reporter) { }

    @Override
    public String getName() { return "InspectDoclet"; }

    @Override
    public Set<? extends Option> getSupportedOptions() { return Set.of(); }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean run(DocletEnvironment env) {
        ModuleElement module = env.getElementUtils().getModuleElement("demo.docs");
        TypeElement type = env.getElementUtils().getTypeElement("demo.api.Greeter");

        System.out.println("Specified module: "
                + env.getSpecifiedElements().contains(module));
        System.out.println("Included class: "
                + env.getIncludedElements().contains(type));
        System.out.println("Module included: " + env.isIncluded(module));
        System.out.println("Class kind: " + type.getKind());

        DocCommentTree classComment = env.getDocTrees().getDocCommentTree(type);
        System.out.println("Class first sentence: "
                + text(classComment.getFirstSentence()));

        ExecutableElement method = ElementFilter.methodsIn(
                type.getEnclosedElements()).stream()
                .filter(m -> m.getSimpleName().contentEquals("greet"))
                .findFirst().orElseThrow();
        System.out.println("Method selected: " + env.isSelected(method));

        DocCommentTree methodComment = env.getDocTrees().getDocCommentTree(method);
        System.out.println("Method first sentence: "
                + text(methodComment.getFirstSentence()));
        for (DocTree tag : methodComment.getBlockTags()) {
            if (tag instanceof ParamTree param) {
                System.out.println("@param " + param.getName() + ": "
                        + text(param.getDescription()));
            } else if (tag instanceof ReturnTree ret) {
                System.out.println("@return: " + text(ret.getDescription()));
            }
        }
        return true;
    }

    private static String text(List<? extends DocTree> nodes) {
        return nodes.stream().map(Object::toString)
                .collect(Collectors.joining()).trim();
    }
}
```

**Biên dịch/chạy** trong `demo-project` (tạo thư mục `out` trước):

```bash
mkdir out
javac --release 17 -d out InspectDoclet.java
javadoc --module-source-path src --module demo.docs -doclet InspectDoclet -docletpath out
```

Các lệnh trên đã chạy với **OpenJDK 24**. Kết quả được quan sát:

```text
Constructing Javadoc information...
Specified module: true
Included class: true
Module included: true
Class kind: CLASS
Class first sentence: Greets a caller.
Method selected: true
Method first sentence: Returns a greeting.
@param name: recipient name
@return: greeting text
```

Dòng trạng thái của công cụ `javadoc` có thể thay đổi theo phiên bản hoặc locale; các dòng từ doclet cho thấy chính xác dữ liệu mẫu.

**Giải thích:**

1. `--module-source-path src --module demo.docs` chọn module và nguồn có layout tương ứng, tạo `ModuleElement` cho `demo.docs`.
2. `-doclet InspectDoclet -docletpath out` yêu cầu dùng custom doclet; lab in báo cáo ra console, **không** tạo HTML Standard Doclet.
3. `getSpecifiedElements().contains(module)` là `true` vì module được chỉ định trên CLI.
4. `getIncludedElements().contains(type)` là `true` vì class thuộc package `demo.api` được export và nằm trong phạm vi tài liệu.
5. `TypeElement.getKind()` trả `CLASS`; `ElementFilter.methodsIn(...)` lọc method được khai báo bên trong class.
6. `DocTrees.getDocCommentTree(type)` cho cây comment của class, `getFirstSentence()` trả phần mô tả đầu.
7. `getBlockTags()` lấy tag `@param`/`@return` của method; `ParamTree` và `ReturnTree` cho phép đọc giá trị có cấu trúc.
8. `getSupportedSourceVersion()` là khả năng mà doclet **tuyên bố hỗ trợ**, còn `env.getSourceVersion()` phản ánh source level mà công cụ đã đọc.

`init` được để rỗng để tập trung vào chủ đề. Doclet sản xuất nên giữ `Reporter` rồi dùng `reporter.print(Diagnostic.Kind.ERROR, "...")` khi input sai; `run` trả `false` để báo lỗi cho công cụ nếu không thể hoàn thành.

## 7. Tìm và kiểm tra `{@link}`: từ comment về khai báo Java

Một comment có thể chứa:

```java
/**
 * Dùng {@link java.lang.String} để xử lý tên;
 * tên được chuẩn hóa qua {@code trim()}.
 * @see java.lang.CharSequence
 */
```

Comment này chỉ là đoạn minh họa, cần đặt ngay trước khai báo Java hợp lệ. `LinkTree` chứa reference và label; `LiteralTree` cho đoạn code; `SeeTree` là block tag. **Không** thể chỉ tách chuỗi `java.lang.String` từ raw text rồi bảo đảm đó là phần tử Java được resolve đúng trong mọi module.

Với `DocTrees` trong `env`, quy trình đúng là:

1. `docTrees.getPath(element)` lấy `TreePath` của khai báo chứa comment (có thể `null` nếu không có source path).
2. `docTrees.getDocCommentTree(element)` lấy comment.
3. Duyệt nodes và tìm `LinkTree`, lấy `link.getReference()` (kiểu `ReferenceTree`).
4. `DocTreePath.getPath(treePath, comment, referenceTree)` tạo đường dẫn đến node tham chiếu trong ngữ cảnh source.
5. `docTrees.getElement(docTreePath)` lấy `Element` được tham chiếu; xử lý `null` khi không giải được.

Nếu cần tham chiếu kiểu Java, `DocTrees.getType(docTreePath)` là API liên quan. Nếu cần vị trí trong source để báo cảnh báo, dùng `DocTrees.getSourcePositions()`. Khi xuất kết quả ra HTML, phải escape text và xử lý link đúng ngữ nghĩa; **comment của người lập trình vẫn là input**, không phải HTML an toàn mặc định.

## 8. Phạm vi tài liệu theo visibility/module

`javadoc` hiện đại có lựa chọn giúp xác định API đưa vào báo cáo:

| Tùy chọn | Công dụng |
| --- | --- |
| `--module tên` | Module được yêu cầu tạo tài liệu. |
| `--module-source-path đường/dẫn` | Nơi tìm source modules. |
| `--show-types public|protected|package|private` | Visibility của type được xét. |
| `--show-members public|protected|package|private` | Visibility của member được xét. |
| `--show-packages exported|all` | Chỉ exported packages hay tất cả packages. |
| `--show-module-contents api|all` | Mức chi tiết khai báo module được tài liệu hóa. |
| `--expand-requires transitive|all` | Mở rộng các module phụ thuộc theo chính sách chỉ định. |

`env.getModuleMode()` cho mức độ chi tiết được yêu cầu (`API` hoặc `ALL`). Không suy ra `ALL` nghĩa là **bỏ qua** toàn bộ bộ lọc visibility; cần kiểm tra `isIncluded` trên từng element.

Khi sử dụng custom doclet, một số tùy chọn sinh HTML của Standard Doclet không được hỗ trợ; nếu cần tùy chọn **riêng** của doclet, hãy triển khai `Doclet.Option` và trả từ `getSupportedOptions()`.

## 9. Áp dụng: kiểm tra Javadoc của API trong CI

Một công cụ có ích là báo lỗi các method API công khai thiếu Javadoc hoặc thiếu mô tả `@param`. Quy trình phù hợp:

1. Lấy `env.getIncludedElements()`, lọc `TypeElement` bằng `ElementFilter.typesIn(...)`.
2. Duyệt `type.getEnclosedElements()`, lọc method bằng `ElementFilter.methodsIn(...)`.
3. Chỉ kiểm tra những method `env.isIncluded(method) == true`.
4. Đọc `DocTrees.getDocCommentTree(method)`; nếu `null`, báo rõ comment thiếu, không gọi tiếp `getFullBody()`.
5. Với comment có tag, đọc `ParamTree.getName()`, `isTypeParameter()` và `getDescription()`; đối chiếu với `method.getParameters()` và type params.
6. Đối chiếu `@return` với kiểu trả về; không bắt buộc `@return` cho `void` hoặc constructor.
7. Xuất báo cáo có thứ tự ổn định theo module/class/method signature; dùng `Reporter` để báo lỗi chính xác.

Đoạn **minh họa nằm trong `run`**:

```java
for (TypeElement type : ElementFilter.typesIn(env.getIncludedElements())) {
    for (ExecutableElement method :
            ElementFilter.methodsIn(type.getEnclosedElements())) {
        if (!env.isIncluded(method)) {
            continue;
        }
        DocCommentTree comment = env.getDocTrees().getDocCommentTree(method);
        if (comment == null) {
            System.out.println("Missing Javadoc: " + method);
        }
    }
}
```

Ở môi trường thực tế, đừng dùng mỗi `method.getSimpleName()` làm khóa báo cáo, vì các method overloaded có thể trùng tên. Dùng chữ ký tham số, kiểu generic và ngữ cảnh module/type. Đừng coi `DocTree.toString()` là cách kiểm chứng mọi tag có hợp lệ; phải kiểm tra từng node/chính sách.

### Mở rộng đối với module và package

Doclet có thể kiểm tra module-level Javadoc trong `module-info.java`, package-level Javadoc trong `package-info.java` và yêu cầu tài liệu cho exported API. Dùng `Elements.getModuleElement(...)`/`getPackageElement(...)` nếu cần tìm theo tên; tránh suy ra package từ chuỗi file path vì nhiều module có layout và nguồn khác nhau.

Khi xuất metadata máy đọc được, phân biệt **mã nguồn đang phân tích** với **bytecode/runtime**: `Element` có thể mô tả source mà không cần class tồn tại để reflection. Công cụ kiểm tra tài liệu thường nên chạy ngay trong bước build/Javadoc với source path chính xác.

## 10. Lỗi phổ biến và cách sửa

| Sai lầm | Tác động | Cách sửa |
| --- | --- | --- |
| Chỉ dùng `getSpecifiedElements()` để sinh toàn bộ API | Thiếu các type nằm trong module được chọn | Dùng `getIncludedElements()` và `isIncluded` |
| Mong `getIncludedElements()` chứa mọi method, field | Duyệt thiếu members | Lấy `getEnclosedElements()` của type và kiểm tra `isIncluded(member)` |
| Nhầm `isSelected` với `isIncluded` | Ghi phần tử không thuộc phạm vi cần tài liệu | Dựa vào `isIncluded` khi quyết định output |
| Gọi `getFullBody()` sau `getDocCommentTree(...)` mà không kiểm tra null | Có thể ném `NullPointerException` | Xử lý comment không có |
| Tách `@param`, `{@link}` bằng regex | Sai với tag/HTML/inline tags lồng nhau | Dùng các `DocTree` type và `DocTreePath` |
| Coi `DocCommentTree` là HTML đã render | Output sai, có thể tiềm ẩn XSS | Render theo node, escape cho định dạng đích |
| Dùng Java reflection để đọc comment từ code | Không có cây chú thích source | Dùng `javax.lang.model` và `DocTrees` |
| Bắt đầu doclet mới bằng `com.sun.javadoc` cũ | Phụ thuộc API đã được thay thế | Dùng `jdk.javadoc.doclet.Doclet` |
| Dùng `SnippetTree` trong doclet bắt buộc chạy Java 17 | Không biên dịch với JDK 17 | Dùng API có trong baseline đã chọn |
| Dựa vào thứ tự của một `Set` | Báo cáo không ổn định qua các lần chạy | Sắp xếp rõ ràng |
| Giả định mọi `{@link}` resolve được | Có thể crash hoặc tạo link hỏng | Kiểm tra kết quả `getElement` và báo diagnostic |

## 11. Bài tập tự kiểm tra

1. Thêm một method public không có Javadoc vào `Greeter`; dùng `Reporter` báo lỗi thay vì chỉ `System.out.println`.
2. Tạo hai overload `greet(String)` và `greet(String, int)`; làm sao ghi report không bị trùng khóa tên `greet`?
3. Dùng `getDocCommentTree(...)` lấy câu đầu trong comment của `ModuleElement` và `PackageElement`; trường hợp nào phải kiểm tra null?
4. Thêm inline `{@link java.lang.String}` vào class comment, giải phần tử được tham chiếu bằng `DocTreePath`/`DocTrees`.
5. Thêm method package-private và đổi selection tương ứng; quan sát sự khác nhau của `isSelected` và `isIncluded`.
6. Một method generic có `@param <T>` và `@param item`. Vì sao cần `ParamTree.isTypeParameter()` khi kiểm tra tài liệu?

**Định hướng đáp án:** `DocletEnvironment` quyết định phạm vi; `Element` và `TypeMirror` biểu diễn code; `DocCommentTree` và typed `DocTree` biểu diễn nội dung. Luôn xử lý comment thiếu, visibility, overloaded methods, link không resolve được và output escaping.

## Tài liệu chuẩn còn áp dụng

- [Java SE 26 — `jdk.javadoc.doclet` package](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/package-summary.html)
- [Java SE 26 — `Doclet`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/Doclet.html)
- [Java SE 26 — `DocletEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.javadoc/jdk/javadoc/doclet/DocletEnvironment.html)
- [Java SE 26 — `DocTrees`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/DocTrees.html)
- [Java SE 26 — `DocCommentTree`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/doctree/DocCommentTree.html)
- [Java SE 26 — Language Model `Elements`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html)

**Ghi nhớ:** Custom doclet nhận một `DocletEnvironment` mỗi lượt chạy. Dùng môi trường để xác định elements cần tài liệu, Language Model để hiểu khai báo, `DocTrees` để hiểu comment, rồi render/kiểm tra với quy tắc rõ ràng. Những API này tiếp tục được hỗ trợ trong Java hiện đại.
