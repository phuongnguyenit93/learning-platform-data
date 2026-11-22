# Giới hạn truy cập thân phương thức qua mô hình khai báo Java

## 1. Bản chất vấn đề

Trong annotation processing (JSR 269), một processor thường có `Element`, `TypeElement` hoặc `ExecutableElement` đại diện cho class, method và constructor. Những đối tượng này mô tả **khai báo** và **kiểu**, không phải toàn bộ cây câu lệnh của mã nguồn.

Câu hỏi trung tâm: **Có thể lấy thân phương thức (`{ ... }`), các lệnh `if`/`return`, biểu thức hoặc lời gọi method chỉ bằng `ExecutableElement` hay `Elements` không?**

**Không.** API mô hình khai báo `javax.lang.model` cho phép đọc **tên, modifiers, signature, parameters, return type, throws, annotations, các quan hệ với khai báo khác**, nhưng **không có phương thức chuẩn nào như `ExecutableElement.getBody()`**. `Elements` cũng không phải parser và không cung cấp cây statement/expression.

Muốn phân tích thân phương thức **khi compiler có sẵn cây mã nguồn**, một ứng dụng dùng `javac` có thể sử dụng **Compiler Tree API công khai** trong module `jdk.compiler`:

- `com.sun.source.util.Trees`: ánh xạ `Element` sang cây mã nguồn hoặc `TreePath`.
- `com.sun.source.tree.MethodTree`: khai báo phương thức ở dạng syntax tree, có `getBody()`.
- `com.sun.source.tree.BlockTree` và các loại `Tree`: câu lệnh, biểu thức trong thân.
- `com.sun.source.util.TreePathScanner`: duyệt syntax tree, ví dụ tìm `MethodInvocationTree`.
- `Trees.getElement(TreePath)` và `Trees.getTypeMirror(TreePath)`: lấy thông tin symbol/type của node khi môi trường compiler đã phân giải được.

Đây là **API được tài liệu JDK công bố**, **không phải** việc dùng class triển khai nội bộ `com.sun.tools.javac.*`. Tuy vậy nó là **mở rộng dành cho môi trường compiler hỗ trợ `com.sun.source`** (thường là `javac`), không phải hợp đồng bắt buộc của mọi implementation JSR 269. Nếu không có source tree, không thể coi method body là thứ được mô hình khai báo bảo đảm cung cấp.

Bài này tập trung vào ranh giới đó, cách dùng hai tầng API đúng lúc, trường hợp trả `null`, các rủi ro và chương trình **Java 17+ chạy được**.

### Kết quả học tập

Sau bài, bạn sẽ biết:

1. Những dữ liệu method mà `ExecutableElement` có và không có.
2. Vì sao `Element.getEnclosedElements()` và `Elements.getAllMembers()` không giúp tìm statements trong thân.
3. Khác biệt giữa **không có cây nguồn** và **có khai báo nguồn nhưng method không có body**.
4. Cách lấy `TreePath`, `MethodTree.getBody()` và duyệt bằng `TreePathScanner` khi chạy với javac.
5. Cách xử lý class từ JAR/classpath, phương thức abstract/default/native, generated source, nhiều vòng processing và khả năng tương thích module.
6. Cách kiểm thử một processor phân tích thân mà không phụ thuộc chi tiết nội bộ của JDK.

## 2. Mô hình khai báo: đọc được gì?

### 2.1. `ExecutableElement` là khai báo executable

`javax.lang.model.element.ExecutableElement` biểu diễn khai báo **method**, **constructor**, và một số dạng initializer theo hợp đồng mô hình, bao gồm method của annotation interface. Các member chính:

| API | Lấy được gì? | Có phải thân method không? |
| --- | --- | --- |
| `getSimpleName()` | Tên method; constructor có quy tắc tên riêng | Không |
| `getModifiers()` | `public`, `static`, `abstract`, `final`... | Không |
| `getParameters()` | Danh sách `VariableElement` đại diện tham số | Không |
| `getReturnType()` | `TypeMirror` của kiểu trả về, `void` nếu thích hợp | Không |
| `getThrownTypes()` | Những kiểu trong `throws` | Không |
| `getTypeParameters()` | Type parameters của method generic | Không |
| `getReceiverType()` | Receiver type theo hợp đồng API, khi có | Không |
| `isVarArgs()` | Có dùng varargs không | Không |
| `isDefault()` | Method `default` của interface hay không | Không |
| `getDefaultValue()` | Giá trị mặc định của **annotation element** | **Không** |
| `asType()` | `ExecutableType` của khai báo | Không |
| `getAnnotationMirrors()` | Annotation metadata gắn trên khai báo | Không |
| `getEnclosingElement()` | Class/interface chứa method | Không |

Ví dụ:

```java
ExecutableElement m = /* method có từ RoundEnvironment */;

String name = m.getSimpleName().toString();
int paramCount = m.getParameters().size();
String returns = m.getReturnType().toString();
boolean isAbstract = m.getModifiers().contains(Modifier.ABSTRACT);
```

*Đây là đoạn minh họa không độc lập: `m`, `Modifier` và các imports cần nằm trong processor thật.* Những thông tin trên đủ để xây kiểm tra signature, sinh adapter hoặc báo compiler error mà **không cần nhìn vào phần implementation**.

### 2.2. `getDefaultValue()` không liên quan đến `return` trong thân

Đây là lỗi hiểu API phổ biến. Với annotation interface:

```java
public @interface Rule {
    int limit() default 10;
}
```

`ExecutableElement.getDefaultValue()` trên annotation member `limit` trả giá trị mặc định `10`. Nó **không thể** dùng để lấy biểu thức `return 10;` của method trong một class:

```java
public int limit() {
    return 10;
}
```

Hai khai báo có ý nghĩa khác nhau trong ngôn ngữ Java.

### 2.3. `getEnclosedElements()` không duyệt câu lệnh

`ExecutableElement` có các phần tử khai báo liên quan như parameters/type parameters. Nhưng `return`, `if`, `while`, phép gán hoặc lời gọi method trong block **không phải** `Element` tương ứng với các khai báo được bao chứa thông thường.

`TypeElement.getEnclosedElements()` trả những **members được khai báo trực tiếp** trong class như fields, methods, constructors và nested types; không có nghĩa nó đã parse sâu từng method body.

`Elements.getAllMembers(type)` còn xét **members kế thừa**, nhưng cũng chỉ trả khai báo, không trả toàn bộ statements bên trong các phương thức kế thừa.

### 2.4. `TypeMirror` mô tả kiểu, không mô tả code

`m.getReturnType()` và `m.getParameters().get(0).asType()` trả mô hình kiểu. `Types.isSameType` hay `Types.isAssignable` có thể kiểm tra quan hệ kiểu, nhưng không có nhiệm vụ khôi phục các lệnh `return`, lệnh gọi hoặc thứ tự thực thi.

**Ghi nhớ:** `Element/Elements` trả lời “khai báo gì?”. `TypeMirror/Types` trả lời “kiểu và quan hệ kiểu gì?”. Compiler Tree API mới có thể trả lời “trong source có những nút cú pháp gì?”, nếu source sẵn có.

## 3. Tại sao không thể đọc thân method qua JSR 269 portable?

Một processor có thể được gọi với những symbol bắt nguồn từ:

- File `.java` đang được javac phân tích.
- Generated source file xuất hiện từ vòng annotation processing trước.
- Class đã biên dịch nằm trong directory/JAR trên classpath.
- Module trong JDK hoặc một named module khác.
- Các khai báo được compiler tạo/mô hình hóa mà không có source node tương ứng theo cách đơn giản.

`javax.lang.model` cố ý mô tả ngữ nghĩa khai báo chung, để compiler không cần cung cấp AST của từng method cho mọi nguồn. Khi source chỉ được nhìn thấy dưới dạng `.class`, **bytecode không chứa nguyên văn Java source body**; nhiều chi tiết source như comment, cách viết expression hoặc sugar syntax đã mất hoặc được biến đổi.

Vì thế:

- Không thể giả định `ExecutableElement` chứa syntax tree.
- Không thể suy `getBody()` từ `getParameters()` hay `getEnclosingElement()`.
- Không thể gọi runtime reflection và mong lấy được source statements. `java.lang.reflect.Method` cũng chỉ nêu signature, modifiers, annotations, không đưa method body source.
- Không thể nhìn vào `getDocComment(...)` để coi Javadoc là code. Javadoc comment là tài liệu và có thể hoàn toàn vắng mặt.
- Không thể chỉ nhìn method signature để kết luận nó **gọi** method nào bên trong.

Nếu yêu cầu chỉ là **kiểm tra hợp đồng khai báo**, ví dụ “method phải `public`, không `static`, trả `CompletableFuture<T>`”, hãy giữ logic trong mô hình khai báo. Không đưa thêm phụ thuộc vào syntax tree nếu không cần.

## 4. Compiler Tree API công khai: lối đi khi có mã nguồn

### 4.1. Module và packages

Bộ API phục vụ AST của Java compiler nằm trong module `jdk.compiler`:

| API | Vai trò |
| --- | --- |
| `com.sun.source.util.Trees` | Bridge giữa compiler model `Element` và source tree. |
| `com.sun.source.util.TreePath` | Một node cùng đường đi từ compilation unit đến node đó. |
| `com.sun.source.tree.MethodTree` | AST khai báo method/constructor, có `getBody()`. |
| `com.sun.source.tree.BlockTree` | Block statements trong một thân method cụ thể. |
| `com.sun.source.tree.MethodInvocationTree` | Node lời gọi method trong source. |
| `com.sun.source.util.TreePathScanner` | Walker biết ngữ cảnh TreePath để duyệt sâu. |
| `com.sun.source.util.TreeScanner` | Walker cho tree không cần path. |
| `com.sun.source.util.SourcePositions` | Offset của source nodes khi có thông tin. |

**Tên package `com.sun.source.*` không đồng nghĩa với “internal API không được hỗ trợ”.** Những type trên là **public documented interfaces/classes của module `jdk.compiler`**. Tuy vậy việc một annotation processor được chạy bởi compiler khác `javac` **không bảo đảm** `Trees.instance(processingEnv)` có sẵn.

Nếu chương trình là **named module** và tự sử dụng cả JSR 269 lẫn Compiler Tree API, cần thiết kế `module-info.java` với những module phù hợp, ví dụ:

```java
module demo.processor {
    requires java.compiler;
    requires jdk.compiler;
    provides javax.annotation.processing.Processor
            with demo.processor.BodyProcessor;
}
```

*Đây là minh họa khai báo module cho processor được đóng gói đúng dạng module.* Ví dụ thực hành dùng classpath, không yêu cầu `module-info.java` hoặc service registration vì `javac` được truyền `-processor` rõ ràng.

### 4.2. Lấy Trees từ ProcessingEnvironment

Trong processor chạy với `javac`:

```java
private Trees trees;

@Override
public synchronized void init(ProcessingEnvironment env) {
    super.init(env);
    try {
        trees = Trees.instance(env);
    } catch (IllegalArgumentException unsupported) {
        trees = null;
    }
}
```

`Trees.instance(env)` có thể báo không có implementation phù hợp với processing environment. Vì vậy code muốn hỗ trợ nhiều compiler nên có đường fallback:

- Nếu tính năng của processor **chỉ** kiểm tra signature: tiếp tục xử lý bằng `Element` khi `trees == null`.
- Nếu bắt buộc phân tích body: báo diagnostic rõ ràng “compiler này không cung cấp source trees” hoặc cho build thất bại có chủ đích; không im lặng coi mọi method không có body.
- Nếu cần plugin/compiler-specific AST khác, phải xác định hợp đồng và mức phụ thuộc riêng, không gọi đó là API JSR 269 portable.

### 4.3. Từ method element đến MethodTree

Một cách phổ biến:

```java
TreePath path = trees == null ? null : trees.getPath(method);
MethodTree tree = path != null && path.getLeaf() instanceof MethodTree
        ? (MethodTree) path.getLeaf()
        : null;
BlockTree body = tree == null ? null : tree.getBody();
```

Đây là đoạn minh họa có `ExecutableElement method` trong processor, với imports `TreePath`, `MethodTree`, `BlockTree`.

**Có ba trạng thái cần phân biệt:**

1. **Không có `TreePath`**: `trees == null` hoặc `trees.getPath(method) == null`. Compiler không cung cấp source tree cho element này; có thể vì method đến từ JAR/class file.
2. **Có `MethodTree` nhưng `getBody() == null`**: khai báo source có mặt, nhưng method không có block body; điển hình là abstract method của interface/class, hoặc native method.
3. **Có `MethodTree` và `BlockTree`**: có thể duyệt AST statements trong body.

**Đừng gom trạng thái 1 và 2 thành cùng một lỗi**. Thực tế chúng mang thông tin khác nhau: “không thể quan sát source implementation” và “khai báo không có source block implementation”.

`Trees.getTree(ExecutableElement)` cũng trả trực tiếp `MethodTree` nếu tìm được; trả `null` nếu không tìm thấy. `getPath(...)` thường hữu ích hơn cho phân tích tiếp vì chứa compilation unit và ngữ cảnh của node.

## 5. Duyệt statements và expressions trong MethodTree

Khi `body != null`, có thể đọc:

```java
List<? extends StatementTree> statements = body.getStatements();
```

`StatementTree` có nhiều subtype:

| Node | Phần cú pháp |
| --- | --- |
| `ReturnTree` | Lệnh `return expression;` |
| `IfTree` | Điều kiện `if/else` |
| `ForLoopTree`, `EnhancedForLoopTree` | Vòng `for` thông thường và enhanced for |
| `WhileLoopTree`, `DoWhileLoopTree` | Các vòng lặp |
| `TryTree` | `try`, catches và finally/resources |
| `ThrowTree` | `throw` |
| `VariableTree` | Khai báo biến cục bộ |
| `ExpressionStatementTree` | Một expression được dùng như statement |
| `SwitchTree` hoặc `SwitchExpressionTree` | Switch statement hoặc switch expression |
| `SynchronizedTree` | Block `synchronized` |

Một lời gọi method như `Math.abs(n)` là `MethodInvocationTree`, thường xuất hiện **nằm sâu trong một biểu thức** như `return Math.abs(n);`; chỉ duyệt `body.getStatements()` cấp đầu tiên là chưa đủ nếu muốn tìm mọi invocation nodes.

### Scanner có ngữ cảnh

`TreePathScanner<R, P>` có thể bắt từng invocation:

```java
private static final class CallCounter
        extends TreePathScanner<Void, Void> {
    int count;

    @Override
    public Void visitMethodInvocation(
            MethodInvocationTree tree, Void unused) {
        count++;
        return super.visitMethodInvocation(tree, unused);
    }
}

// Chỉ scan khi methodPath và MethodTree.getBody() có mặt.
CallCounter counter = new CallCounter();
counter.scan(methodPath, null);
System.out.println(counter.count);
```

Đây là đoạn **minh họa, không phải file Java độc lập**. `methodPath` là `TreePath` của method. `scan(methodPath, null)` duyệt subtree của khai báo method, bao gồm cả phần syntax mà scanner nhìn thấy bên dưới. Vì vậy `count` là **số node method invocation trong cú pháp được quét**, **không** phải “bao nhiêu lần method đã chạy”. Một invocation bên trong loop chỉ tạo một syntax node dù runtime gọi nhiều lần; một nhánh không bao giờ thực thi vẫn được đếm.

Cũng cần cẩn thận với nested lambda, anonymous class, local classes và annotation syntax: scanner có thể duyệt code lồng nhau, không đồng nghĩa tất cả invocation đều thuộc luồng thực thi trực tiếp của method bên ngoài. Nếu cần một loại phân tích giới hạn, hãy tùy biến visitor để bỏ những subtree không thuộc phạm vi mong muốn.

### Liên kết syntax node với declaration

Khi cần biết invocation `helper(value)` gọi **method nào**, đừng chỉ dùng text `tree.getMethodSelect().toString()`. Có thể lấy symbol bằng:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree node, Void unused) {
    Element target = trees.getElement(getCurrentPath());
    if (target instanceof ExecutableElement called) {
        // Phân tích called.getEnclosingElement(), tên và signature.
    }
    return super.visitMethodInvocation(node, unused);
}
```

Đây là **mẫu minh họa cho scanner có biến `Trees trees`** đã được cung cấp, không phải phần của demo chính. `getElement(TreePath)` có thể trả `null` nếu symbol không được phân giải hoặc path không phù hợp. Với generic methods/overloads, phải dùng symbol và type model; không đoán dựa vào chuỗi tên method.

## 6. So sánh các loại phương thức

| Tình huống | `ExecutableElement` có thông tin khai báo? | Có `TreePath`? | `MethodTree.getBody()` |
| --- | --- | --- | --- |
| Method instance đang được biên dịch từ source | Có | Thường có khi javac cung cấp tree | `BlockTree` nếu source khai báo body |
| Interface `default` method có body | Có | Thường có khi source sẵn | `BlockTree` |
| Method `abstract` khai báo trong source | Có | Có thể có | `null` vì không có body |
| Method `native` trong source | Có | Có thể có | `null` vì body là dấu `;` |
| Method của dependency chỉ đọc từ `.class` hoặc JAR | Có nếu symbol được load | Thường **`null`** | Không truy cập được qua source tree |
| Generated source từ vòng processor trước | Có khi compiler đưa vào mô hình | Có thể có ở vòng phù hợp và compiler có tree | Tùy source được sinh |
| Method từ JDK module/classpath binary | Có nếu resolve được | Không nên trông đợi | Không có source AST theo hợp đồng |
| Compiler implementation không hỗ trợ `Trees` | Có theo JSR 269 | Không bảo đảm | Không dùng được Compiler Tree API |

Bảng nói về **khả năng API**, không phải quy tắc rằng mọi compiler bắt buộc trả giống nhau. Đặc biệt, hãy **kiểm tra `null` ở cả bước lấy source path lẫn body**.

Một method **không có body trong Java source** vẫn có thể có semantics thông qua lớp thực thi khác hoặc native implementation. Mặt khác, method `default` trong interface **có source body** dù bản thân nó nằm trong một interface. Không suy luận đơn giản rằng “interface method luôn không có body”.

## 7. Ví dụ đầy đủ: phân tích body khi có source, không đoán body từ .class

Demo tạo một annotation processor chạy trên JDK 17+, kết hợp cả hai API:

- `ExecutableElement`: kiểm tra **return type** và **số parameter** dù method có body hay không.
- `Trees.getPath(method)`: kiểm tra cây source có sẵn hay không.
- `MethodTree.getBody()`: phân biệt một method có body với abstract method.
- `TreePathScanner`: đếm **cú pháp invocation** trong source method có body.
- `Elements.getTypeElement("demo.lib.Binary")`: tra cứu **dependency đã biên dịch** và xác minh nó có signature nhưng **không có source path** trong fixture.
- `Filer.createSourceFile`: sinh `BodyReport.java` để ứng dụng có thể in kết quả kiểm tra.

### 7.1. Cây thư mục

```text
method-body-demo/
├── src/
│   └── demo/
│       ├── api/
│       │   └── CheckBody.java
│       └── processor/
│           └── BodyProcessor.java
├── lib/
│   └── demo/lib/
│       └── Binary.java
├── app/
│   └── demo/app/
│       ├── Rules.java
│       ├── Calculator.java
│       └── Main.java
└── build/
    ├── library/        # Binary.class được biên dịch trước
    ├── processor/      # annotation và processor classes
    ├── generated/      # BodyReport.java
    └── classes/        # app classes và BodyReport.class
```

Ở lần compile ứng dụng cuối, **`Binary.java` không là source input**; javac chỉ thấy `Binary.class` trên classpath. Đây là điều kiện quan trọng để kiểm thử việc source AST không có sẵn.

### 7.2. `src/demo/api/CheckBody.java`

```java
package demo.api;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
public @interface CheckBody {}
```

Processor chỉ cần annotation trong source, không cần giữ nó trong bytecode runtime. `@Target(METHOD)` giúp người dùng không vô tình gắn annotation lên field/class.

### 7.3. `src/demo/processor/BodyProcessor.java`

```java
package demo.processor;

import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import demo.api.CheckBody;

import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.api.CheckBody")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class BodyProcessor extends AbstractProcessor {

    private Trees trees;

    @Override
    public synchronized void init(ProcessingEnvironment env) {
        super.init(env);
        try {
            trees = Trees.instance(env);
        } catch (IllegalArgumentException unsupported) {
            trees = null;
        }
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        if (round.processingOver()) {
            return true;
        }

        List<String> rows = new ArrayList<>();

        for (Element e :
                round.getElementsAnnotatedWith(CheckBody.class)) {

            if (e.getKind() != ElementKind.METHOD) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@CheckBody requires a method", e);
                continue;
            }

            ExecutableElement method = (ExecutableElement) e;

            TreePath path = trees == null
                    ? null : trees.getPath(method);

            MethodTree tree = path != null
                    && path.getLeaf() instanceof MethodTree
                    ? (MethodTree) path.getLeaf()
                    : null;

            boolean hasBody =
                    tree != null && tree.getBody() != null;

            CallCounter counter = new CallCounter();
            if (hasBody) {
                counter.scan(path, null);
            }

            rows.add(method.getSimpleName()
                    + ":source=" + (path != null)
                    + ",body=" + hasBody
                    + ",calls=" + counter.count
                    + ",return=" + method.getReturnType()
                    + ",params=" + method.getParameters().size());
        }

        if (rows.isEmpty()) {
            return true;
        }

        Collections.sort(rows);

        TypeElement binary = processingEnv.getElementUtils()
                .getTypeElement("demo.lib.Binary");

        if (binary == null) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Missing binary dependency");
            return true;
        }

        ExecutableElement external =
                ElementFilter.methodsIn(
                        binary.getEnclosedElements())
                        .stream()
                        .filter(x -> x.getSimpleName()
                                .contentEquals("external"))
                        .findFirst()
                        .orElseThrow();

        rows.add("binaryPath="
                + (trees != null
                        && trees.getPath(external) != null));

        try {
            JavaFileObject output = processingEnv.getFiler()
                    .createSourceFile("demo.app.BodyReport");

            try (Writer writer = output.openWriter()) {
                writer.write(
                        "package demo.app; "
                        + "public final class BodyReport { "
                        + "public static String details() { return \""
                        + String.join("|", rows)
                                .replace("\\", "\\\\")
                                .replace("\"", "\\\"")
                        + "\"; } }");
            }
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, ex.getMessage());
        }
        return true;
    }

    private static final class CallCounter
            extends TreePathScanner<Void, Void> {
        int count;

        @Override
        public Void visitMethodInvocation(
                MethodInvocationTree node, Void unused) {
            count++;
            return super.visitMethodInvocation(node, unused);
        }
    }
}
```

Đây là processor được thử nghiệm với Java 17 target. Những điểm cần quan sát:

1. `Trees.instance(env)` là bridge compiler-specific có kiểm tra khả năng sử dụng; `ExecutableElement` vẫn được xử lý ngay cả khi `trees == null`.
2. `TreePath path` khác với `MethodTree.getBody()`; có path nhưng không có body là trường hợp thực sự được kiểm thử với abstract method.
3. `CallCounter` chỉ được scan nếu có body; không dereference `null`.
4. `getTypeElement("demo.lib.Binary")` vẫn trả khai báo của dependency `Binary.class`; `trees.getPath(external)` không nhất thiết trả source path.
5. `Collections.sort(rows)` giúp thứ tự report ổn định bất kể thứ tự processor duyệt annotation trong vòng xử lý.
6. `Filer` tạo file báo cáo trong cùng compilation invocation; không yêu cầu ghi lên source code hiện có.
7. `@SupportedAnnotationTypes` và `@SupportedSourceVersion` khai báo phạm vi processor; `-processor` trong CLI sẽ chọn implementation rõ ràng.

**Giới hạn demo:** Có một tập source được annotate trong package `demo.app`, và code sinh **một** `BodyReport`. Trong thư viện production có nhiều rounds và modules, phải quản lý output ownership, đừng tạo trùng class trong cùng compilation; cần xử lý generated source, thư viện bị thiếu, cùng tên class ở module khác, và chính sách error/fallback.

### 7.4. `lib/demo/lib/Binary.java`

```java
package demo.lib;

public final class Binary {
    public int external(int value) {
        return value + 1;
    }
}
```

Class này được compile **trước** vào `build/library`, sau đó phần compile ứng dụng chỉ đưa **directory class** vào classpath, không truyền `Binary.java` như source input. Processor vì thế vẫn thấy method signature nhưng không có source path cho method `external` trong test này.

### 7.5. `app/demo/app/Rules.java`

```java
package demo.app;

import demo.api.CheckBody;

public interface Rules {

    @CheckBody
    int required(int number);

    @CheckBody
    default int fallback(int number) {
        return Math.abs(number);
    }
}
```

`required` là abstract interface method, **không có body**. `fallback` là default interface method, **có body** chứa một invocation node `Math.abs(number)`.

### 7.6. `app/demo/app/Calculator.java`

```java
package demo.app;

import demo.api.CheckBody;

public final class Calculator {

    @CheckBody
    public int twice(int value) {
        return helper(value);
    }

    private int helper(int value) {
        return value * 2;
    }
}
```

Method `twice` có body, chứa invocation `helper(value)`. `helper` không được annotate, nên processor chỉ đọc nó nếu chủ động duyệt source tree hoặc model; fixture này đếm invocation cú pháp trong `twice`, không cố thực thi `helper` trong processor.

### 7.7. `app/demo/app/Main.java`

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println(BodyReport.details());
        System.out.println("value=" + new Calculator().twice(7));
    }
}
```

`BodyReport` chưa có trước lúc compile ứng dụng; nó được processor sinh bằng `Filer` và compiler tiếp tục biên dịch.

### 7.8. Lệnh chạy trên Linux/macOS

Ở thư mục `method-body-demo`:

```bash
mkdir -p build/library build/processor build/classes build/generated

# Bước 1: tạo dependency dạng compiled class, không có source đầu vào
# trong lần compile ứng dụng.
javac --release 17 -d build/library lib/demo/lib/Binary.java

# Bước 2: build annotation và processor.
javac --release 17 -d build/processor \
  src/demo/api/CheckBody.java \
  src/demo/processor/BodyProcessor.java

# Bước 3: compile app, chọn processor rõ ràng; dependency Binary là .class.
javac --release 17 \
  -cp "build/processor:build/library" \
  -processorpath build/processor \
  -processor demo.processor.BodyProcessor \
  -s build/generated \
  -d build/classes \
  app/demo/app/Rules.java \
  app/demo/app/Calculator.java \
  app/demo/app/Main.java

# Bước 4: chạy báo cáo đã được sinh.
java -cp build/classes demo.app.Main
```

### 7.9. Lệnh trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Force build/library,build/processor,build/classes,build/generated | Out-Null

javac --release 17 -d build/library lib/demo/lib/Binary.java

javac --release 17 -d build/processor src/demo/api/CheckBody.java src/demo/processor/BodyProcessor.java

javac --release 17 -cp "build/processor;build/library" -processorpath build/processor -processor demo.processor.BodyProcessor -s build/generated -d build/classes app/demo/app/Rules.java app/demo/app/Calculator.java app/demo/app/Main.java

java -cp build/classes demo.app.Main
```

Phân cách các classpath entries là **`:` trên Linux/macOS** và **`;` trên Windows**. Trong PowerShell nên quote toàn bộ chuỗi classpath khi có dấu `;`. `-processorpath` dành cho **implementation processor**; `-cp` dành cho các dependencies mà source và processor model phải resolve, gồm annotation API và `Binary.class`.

**Lưu ý trên JDK 23+:** Ví dụ có `-processor demo.processor.BodyProcessor` nên chủ động bật annotation processing; không dựa vào implicit discovery từ classpath của JDK cũ. Processor cần chạy trong JDK có `jdk.compiler` và Compiler Tree API; runtime JRE thu gọn không nhất thiết cung cấp compiler.

### 7.10. Stdout chính xác

```text
fallback:source=true,body=true,calls=1,return=int,params=1|required:source=true,body=false,calls=0,return=int,params=1|twice:source=true,body=true,calls=1,return=int,params=1|binaryPath=false
value=14
```

Ngoài ra các file này tồn tại:

```text
build/generated/demo/app/BodyReport.java
build/classes/demo/app/BodyReport.class
```

**Giải thích từng phần output:**

- `fallback:source=true,body=true`: interface default method có source path và block body.
- `fallback:calls=1`: cây source có một `MethodInvocationTree` cho `Math.abs(number)`.
- `required:source=true,body=false`: method abstract được khai báo trong source (có path), nhưng `MethodTree.getBody() == null`.
- `required:calls=0`: không scan vì không có body; **không suy luận** rằng mọi interface abstract method đều trả runtime call count 0.
- `twice:source=true,body=true,calls=1`: block có một lời gọi `helper(value)`.
- Cả ba phương thức có `return=int` và `params=1` từ `ExecutableElement`, **kể cả method không có body**.
- `binaryPath=false`: `Binary.external` có model declaration lấy từ `.class`, nhưng **không có source path** trong compilation fixture này.
- `value=14`: khi runtime thực thi `new Calculator().twice(7)`, kết quả là `14`. Kết quả này **độc lập** với count cú pháp invocation của processor.

Compiler không báo lỗi trong fixture hợp lệ; `BodyReport.java` và `BodyReport.class` tồn tại sau compilation.

## 8. Source tree không phải bytecode hay control-flow graph

`MethodTree.getBody()` cho syntax tree của **mã nguồn**:

- Giữ cấu trúc các statement, expression, lambda, local class... theo những AST nodes mà `com.sun.source.tree` biểu diễn.
- Không tự thực thi chương trình.
- Không báo số lần một nhánh/vòng lặp chạy lúc runtime.
- Không tự cung cấp bytecode đã biên dịch.
- Không đảm bảo source mà bạn thấy là mã “sau mọi biến đổi compiler”; AST có thể được compiler bổ sung/biến đổi tùy giai đoạn và implementation.
- Không tự đưa ra control-flow graph (CFG), reachability, data-flow facts hay kết quả symbolic execution.

Ví dụ:

```java
public void printIf(boolean enabled) {
    if (enabled) {
        System.out.println("yes");
    }
}
```

Một scanner đếm `MethodInvocationTree` nhìn thấy **một** invocation `println`. Runtime có thể gọi nó **0** lần nếu `enabled == false` hoặc **1** lần trong lần thực thi method này nếu true. Đếm AST node không xác định nhánh được thực thi.

Muốn phân tích các ràng buộc phức tạp như “mọi đường đi đều đóng resource”, “biến được gán trước khi đọc”, “taint flow từ input đến sink”, hay “lời gọi này luôn chạy”, cần một static analysis engine phù hợp, xây trên parser/AST + semantic model và (khi cần) CFG/data-flow, không chỉ lấy `MethodTree.getBody()`.

## 9. Phân biệt đọc cú pháp và đọc ngữ nghĩa

Một node `MethodInvocationTree` có thể biểu diễn:

```java
helper(value)
obj.helper(value)
Math.abs(value)
```

Đọc `getMethodSelect().toString()` chỉ phản ánh text/cấu trúc cú pháp; overload resolution và dynamic dispatch không thể được xác định đáng tin chỉ từ tên string.

Khi compiler có symbol mapping, dùng:

```java
@Override
public Void visitMethodInvocation(
        MethodInvocationTree call, Void ignored) {

    Element resolved = trees.getElement(getCurrentPath());
    if (resolved instanceof ExecutableElement target) {
        String owner = target.getEnclosingElement().toString();
        String methodName = target.getSimpleName().toString();
        // Dùng Elements/Types để kiểm tra owner, params và return type.
    }
    return super.visitMethodInvocation(call, ignored);
}
```

Đoạn này là **ví dụ tích hợp không standalone**, chạy trong `TreePathScanner` có tham chiếu `Trees trees`. `getCurrentPath()` là path đang visit. `Trees.getElement(path)` có thể trả `null` khi compiler chưa phân giải đủ hoặc với node không gắn symbol; code phải kiểm tra.

Để kiểm tra type của biểu thức, `Trees.getTypeMirror(path)` có thể trả mô hình kiểu khi sẵn có. Để so sánh kiểu với generic substitutions, dùng `Types` thay vì chuỗi biểu diễn. Cũng cần nhớ rằng resolved compile-time target của một virtual method call không phải lúc nào cũng là implementation thực thi ở runtime do dynamic dispatch.

## 10. Vòng đời processing và nguồn được sinh

Một annotation processor có thể chạy **nhiều vòng** (rounds). Source được `Filer.createSourceFile(...)` sinh trong một vòng có thể tham gia các vòng tiếp theo. Vì vậy:

- `round.processingOver()` đánh dấu final round; không tạo thêm source như một cách kích hoạt round khác.
- Không tạo cùng output file nhiều lần (có thể gây `FilerException`).
- Không giữ `TreePath`, `Element` hoặc source tree của vòng/task cũ làm cache toàn cục để dùng trong compilation task mới; mô hình và source positions gắn với môi trường compile cụ thể.
- Nếu phân tích source vừa sinh, kiểm tra nó thực sự đã có mặt trong round tiếp theo và compiler có path tương ứng. Không giả định `Filer.createSourceFile` ngay lập tức cho một `ExecutableElement` và AST hoàn chỉnh của file mới trong cùng vị trí xử lý.
- Một processor chạy trên classpath hoặc module input có thể gặp symbol không có AST, dù các symbol đó có method signature.

Nếu tool được thiết kế để làm việc trên **nhiều compiler khác nhau**, phát hiện `Trees` và chính sách fallback là một phần của API contract của chính tool. Nếu **bắt buộc** truy cập statement-level source, nên nói rõ yêu cầu “chạy với javac/JDK compiler” trong tài liệu.

## 11. Chức năng nào nên dùng phương pháp nào?

| Nhu cầu | Công cụ phù hợp | Ghi chú |
| --- | --- | --- |
| Kiểm tra method có `public` không | `ExecutableElement.getModifiers()` | Hoàn toàn declaration-level. |
| Kiểm tra parameters/return type | `ExecutableElement` + `Types` | Có thể phân tích cả method từ dependency compiled. |
| Xem `throws`, type parameters, annotation | `ExecutableElement` | Không cần AST. |
| Xem annotation member default | `ExecutableElement.getDefaultValue()` | Không phải method body. |
| Kiểm tra method override/hide | `Elements.overrides(...)` / `hides(...)` | Ngữ nghĩa khai báo; không cần source body. |
| Đọc câu lệnh `return`, `if`, loops | `Trees` + `MethodTree`/`BlockTree` | Chỉ khi compiler có source tree. |
| Liệt kê invocation **trong mã nguồn** | `TreePathScanner` | Kết quả là syntax nodes, không phải số lần runtime gọi. |
| Biết biểu thức gọi method khai báo nào | `Trees.getElement(TreePath)` | Phải có symbol được phân giải; kiểm tra `null`. |
| Phân tích method từ JAR không có source | Library phân tích bytecode/class file độc lập | Không thể suy ra nguyên văn Java source từ declaration model. |
| Muốn source thật từ dependency | Cung cấp source tương ứng, qua sourcepath/build tooling hoặc source archive do tool quản lý | Source được cung cấp bên ngoài không tự gắn vào `Trees` khi compiler chỉ đọc `.class`. |
| Muốn runtime call count | Profiling/instrumentation/tracing có kiểm soát | Không lấy từ `MethodTree`. |

Đối với code generation dựa trên signatures (DTO, API adapter, serializer metadata...), hạn chế dùng tree API để giữ processor portable. Chỉ phụ thuộc AST nếu yêu cầu thật sự là kiểm tra/biến đổi logic trong body.

## 12. Trường hợp khó và các bẫy thiết kế

### 12.1. Method từ JAR: có model nhưng không có source

Khi processor thấy `demo.lib.Binary` trên classpath, `Elements.getTypeElement` tìm ra class, `ElementFilter.methodsIn(binary.getEnclosedElements())` có thể tìm `external`, và `ExecutableElement` cho phép đọc return type/parameters/modifiers. Tuy nhiên `Trees.getPath(external)` thường trả `null`.

**Đừng** coi `null` là bằng chứng source gốc chưa từng có method body. Nó chỉ nghĩa compiler **không thể cung cấp source path** trong môi trường biên dịch đang xét. `Binary.external` thực tế có bytecode đã được compile.

### 12.2. Abstract/native methods: có source path, không có body

Với:

```java
public abstract class Parent {
    public abstract int compute(int number);
}
```

`compute` có `ExecutableElement` và có thể có `MethodTree` nếu source sẵn, nhưng `getBody() == null`. Tương tự native method có thể không có source body. Trường hợp này khác dependency binary path null.

### 12.3. Interface default method có thể có body

`default int fallback(int n) { return Math.abs(n); }` có body. Đừng dùng `element.getEnclosingElement().getKind() == INTERFACE` như điều kiện “body luôn trống”.

### 12.4. Code của lambda, local/anonymous class

Một visitor đếm toàn bộ subtree của method có thể đi vào lambda/local class hoặc anonymous class được khai báo bên trong. Nếu thuật toán chỉ quan tâm invocation trực tiếp của body ngoài, phải định nghĩa nghĩa của “trực tiếp”, rồi chặn/điều chỉnh traversal một cách rõ ràng.

### 12.5. Truy cập nội bộ javac không cần thiết

Các class `com.sun.tools.javac.tree.JCTree`, `TreeMaker`, `JavacProcessingEnvironment` và tương tự **không phải** JSR 269 portable public contract. Chúng có thể biến động qua release và yêu cầu export đặc biệt theo module. Nếu chỉ muốn đọc source, hãy ưu tiên documented `com.sun.source.*`.

### 12.6. Source positions và byte offsets

`Trees.getSourcePositions()` có thể cho start/end positions của tree node trong compilation unit. Nhưng đừng nhầm đây là byte offsets UTF-8 của file hoặc range chắc chắn có mặt với mọi AST node. Source compiler dùng chỉ số ký tự/positions theo hợp đồng API; có thể trả giá trị không xác định.

Để trích text chính xác phục vụ hiển thị, cần biết `CompilationUnitTree.getSourceFile()`, encoding và khả năng truy cập source nội dung; **không** tự dùng positions để sửa file gốc trong annotation processor. Compiler Tree API phục vụ phân tích, `Filer` phục vụ sinh **file mới**.

### 12.7. Class loader không cho bạn Java source body

Runtime reflection (`Method`) có thể lấy types, modifiers/annotations và invocation, nhưng không lấy lại source statements. Có bytecode cũng không đồng nghĩa có source tương ứng. Decompiler là công cụ riêng, tạo mã gần tương đương ở mức nào đó nhưng không tái lập đúng nguyên văn; nó không thay thế cho `Trees` trong compiler đang phân tích source.

### 12.8. Phân tích không đáng tin cậy hoặc code được sinh

Processor là Java code được thực thi trong quá trình build, với các quyền của build process. Hãy tin tưởng, pin version và kiểm soát dependencies của processor. Bản thân việc *đọc AST* không tương đương với chạy code đang được compile; nhưng **nạp/chạy** class vừa compile là bước riêng có rủi ro, không nên thực hiện chỉ để “xem method làm gì”.

## 13. Kiểm thử theo trạng thái và khả năng compiler

Một bộ test có giá trị nên xác minh **hai tầng**: declaration model luôn có những dữ liệu nào và AST chỉ xuất hiện khi điều kiện phù hợp.

| Test | Fixture | Điều cần khẳng định |
| --- | --- | --- |
| Concrete source method | `Calculator.twice(int)` | `ExecutableElement` có params/return; `Trees.getPath` và body có mặt. |
| Default interface method | `Rules.fallback(int)` | Path có mặt; body có một invocation syntax node. |
| Abstract interface method | `Rules.required(int)` | Path có mặt; body `null`, nhưng return/parameter vẫn được đọc. |
| Compiled binary method | `Binary.external(int)` chỉ có `.class` trên classpath | `ExecutableElement` có metadata; trong fixture `Trees.getPath(...) == null`. |
| Generated source | `BodyReport.java` | Generated source/class được compiler tạo trong build hợp lệ. |
| No Trees support | Compiler implementation không hỗ trợ Trees | Tool báo không hỗ trợ hoặc chuyển sang signature-only; không ném `NullPointerException`. |
| Missing type | Không có `demo.lib.Binary` trên classpath | Processor báo diagnostic rõ, không `NullPointerException` ở `getTypeElement`. |
| Invalid annotation target | Annotation được cấu hình trên kind khác METHOD nếu target cho phép | Processor kiểm tra `ElementKind` và báo ERROR. |
| Method source không có body | Native/abstract method | `MethodTree` có thể có, `getBody() == null`. |
| Multi-round processor | Source được sinh ở round đầu | Không ghi đè same Filer output hoặc giữ stale tree giữa rounds. |
| Nested code | Lambda/local class trong body | Đếm traversal theo phạm vi đã định nghĩa, không coi node count là runtime call count. |
| Java target version | `--release 17` trên JDK khác nhau | Không phụ thuộc API mới hơn Java 17 trong demo; dùng processor activation rõ trên JDK 23+. |

Không viết test `assertEquals(1, getAllMembers(...).size())` hoặc assert byte-for-byte output của compiler AST: chi tiết model/AST có thể phụ thuộc code và compiler version. Nên assert **từng hành vi có ý nghĩa**, bao gồm `null` vs non-`null`.

Với compilation test trong Java, có thể lấy lỗi qua `DiagnosticCollector<JavaFileObject>` và kiểm tra `task.call()`:

```java
boolean success = Boolean.TRUE.equals(task.call());
boolean hasError = diagnostics.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
```

*Đây là mẫu minh họa không độc lập*, yêu cầu `task` và `diagnostics` được cấu hình trước. Khi source hợp lệ, mong `success` và không có ERROR; khi đầu vào vi phạm hợp đồng của processor, mong compilation thất bại và có ERROR.

## 14. Những lỗi thường gặp

**1. Gọi một method không tồn tại: `ExecutableElement.getBody()`.**  
API `ExecutableElement` không có method này. Với source tree, dùng `Trees.getTree(method)` hoặc `getPath(method)` rồi `MethodTree.getBody()`.

**2. Coi `Elements.getAllMembers(type)` là lệnh liệt kê statement.**  
Nó trả **members của type**, bao gồm inheritance; không trả các lệnh bên trong body.

**3. Dùng `getDefaultValue()` để lấy expression trong `return`.**  
Method này chỉ đọc default value của annotation element.

**4. Lấy `Trees.instance(processingEnv)` mà không nghĩ đến compiler khác.**  
JSR 269 processor chạy với implementation không hỗ trợ `Trees` có thể bị lỗi khi khởi tạo. Cần bắt lỗi hỗ trợ và có policy fallback.

**5. Không kiểm tra `Trees.getPath(method) == null`.**  
Symbol lấy từ `.class`/JAR có thể không có source tree. Không kết luận rằng method không có implementation.

**6. Không phân biệt `MethodTree` có mặt nhưng `getBody() == null`.**  
Abstract/native methods là ví dụ điển hình của khai báo không có block body.

**7. Cho rằng interface method luôn không có body.**  
Default và static methods của interface có source body; không phán đoán bằng container kind.

**8. Duyệt `BlockTree.getStatements()` một tầng rồi nghĩ đã thấy mọi lời gọi.**  
Invocation có thể nằm trong return expression, if condition, loop hoặc lambda. Dùng scanner đủ độ sâu và xác định ranh giới traversal.

**9. Đếm `MethodInvocationTree` rồi gọi đó là runtime call count.**  
Số syntax nodes không bằng số lần câu lệnh được chạy, càng không phải profiling.

**10. Xác định method target bằng `toString()` của invocation.**  
Overloading, generics, instance receivers và dynamic dispatch làm suy luận text-only thiếu tin cậy. Sử dụng symbol mapping `Trees.getElement(path)` và `Types` nếu cần.

**11. Dùng source positions như byte offsets để sửa file gốc.**  
Cần xét encoding, vị trí không xác định và compiler ownership. JSR 269 chủ yếu sinh file mới qua `Filer`, không sửa source người dùng.

**12. Khẳng định bytecode class file chứa nguyên văn thân Java.**  
Bytecode không giữ toàn bộ cách viết source và comments; decompilation là ước lượng/cách dựng lại, không phải truy cập AST nguồn.

**13. Chuyển sang `com.sun.tools.javac.*` khi chỉ cần đọc tree.**  
Các API nội bộ có nguy cơ không tương thích JDK; dùng documented `com.sun.source.*` nếu có.

**14. Không bật annotation processing ở JDK 23+.**  
Ví dụ chỉ định `-processor` và processor path rõ để tool chạy. Đừng chỉ dựa vào classpath implicit discovery cũ.

**15. Đưa source ở dependency JAR vào classpath và đợi `Trees` tự đọc kèm sources JAR.**  
Compiler model có thể chỉ dựa vào `.class`. Sources attachment là dữ liệu ngoài quy trình biên dịch; không tự xuất hiện thành `TreePath` cho methods binary.

**16. Tự sửa source trong processor.**  
Filer sinh output mới, không phải API để rewrite method body đang compile. Nếu mục tiêu là code transformation, cần kiến trúc/compiler tooling phù hợp, không “lách” qua Element model.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `ExecutableElement` có cho phép lấy return type và parameters của method trong JAR không?  
**Có**, khi compiler resolve được declaration. Nhưng **không** có phương thức chuẩn để lấy body.

**Câu 2.** Có sự khác biệt nào giữa `trees.getPath(method) == null` và `methodTree.getBody() == null`?  
**Có**: trường hợp đầu là không tìm được đường tới source node, trường hợp sau có khai báo source tree nhưng method không có block body.

**Câu 3.** Interface `default` method có body không?  
**Có**, nếu source định nghĩa block, ví dụ `default int twice(int x) { return x * 2; }`.

**Câu 4.** Có thể dùng `Elements.getAllMembers` để tìm câu lệnh `return` không?  
**Không**. Đó là phép tìm members, không phải AST traversal.

**Câu 5.** `TreePathScanner` đếm hai invocation nodes có nghĩa method chạy hai lần không?  
**Không**. Nó đếm cấu trúc source mà scanner đi qua, không phải runtime executions.

**Câu 6.** `Trees` có thuộc `java.compiler` giống `ExecutableElement` không?  
**Không**. `ExecutableElement` ở module `java.compiler`; `Trees`/`MethodTree` thuộc **`jdk.compiler`**, phù hợp khi chạy trên JDK compiler hỗ trợ.

**Câu 7.** Nếu `Trees.getPath(binaryMethod) == null`, phải báo method là `abstract`?  
**Không**. Method binary có thể có bytecode, chỉ là source tree không sẵn trong môi trường hiện tại.

**Câu 8.** Nếu cần biết `helper(value)` tham chiếu đến declaration nào, chỉ xem `MethodInvocationTree.toString()` đủ không?  
**Không**. Dùng `Trees.getElement(TreePath)` khi có symbol mapping rồi kiểm tra `ExecutableElement`.

**Câu 9.** Muốn kiểm tra method `public` và kiểu trả về trong processor dùng phương pháp nào?  
**Dùng declaration/type model**: `getModifiers()`, `getReturnType()`, `Types`. Không cần AST.

**Câu 10.** Muốn sửa body của source có sẵn bằng JSR 269 portable thì gọi API nào?  
**Không có API chuẩn như vậy**. JSR 269 hỗ trợ phân tích khai báo, diagnostic và tạo files mới; sửa body đòi hỏi tooling khác.

## Tài liệu chính thức, còn hiệu lực

- [Java SE 26 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html): giao diện khai báo method/constructor, không có method truy cập body.
- [Java SE 26 — `Element`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html) và [`Elements`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html): members, enclosing và tra cứu declaration.
- [Java SE 26 — `TypeMirror`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html) và [`Types`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Types.html): type model và các quan hệ kiểu.
- [Java SE 26 — `Trees`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/Trees.html): lấy `Tree`/`TreePath` từ `Element`, bridge với source compiler.
- [Java SE 26 — `MethodTree`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/tree/MethodTree.html) và [`BlockTree`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/tree/BlockTree.html): cây khai báo phương thức, `getBody()` và danh sách statements.
- [Java SE 26 — `TreePathScanner`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/TreePathScanner.html) và [`MethodInvocationTree`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/tree/MethodInvocationTree.html): duyệt source tree và lời gọi phương thức.
- [Java SE 26 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getElementUtils()`, `getTypeUtils()` và môi trường processor.
- [Java SE 26 — `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cấu hình `-processor`, `-processorpath`, `-s` và `--release`.

**Kết luận:** Mô hình khai báo Java cho biết **một method là gì** nhưng không bảo đảm cho biết **các câu lệnh trong method**. Khi source AST sẵn có từ javac, dùng `Trees` và `MethodTree.getBody()` với đầy đủ xử lý `null`; khi chỉ có `.class` hoặc compiler không hỗ trợ tree, hãy giữ các phân tích declaration-level hoặc dùng một công cụ bytecode/source-analysis khác có hợp đồng rõ ràng.
