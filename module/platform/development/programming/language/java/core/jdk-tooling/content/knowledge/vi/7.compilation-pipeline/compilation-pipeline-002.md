# Parse source trong Java

## 1. Parse source là gì?

**Parse source** là giai đoạn phân tích cú pháp mã nguồn. Sau khi đọc văn bản và nhận diện các token, compiler kiểm tra cách các token kết hợp với nhau theo grammar của ngôn ngữ Java, rồi xây dựng một cấu trúc biểu diễn chương trình.

Ví dụ:

~~~java
int total = price + tax;
~~~

Parser cần nhận ra đây là một khai báo biến cục bộ gồm kiểu int, tên total, dấu gán, một biểu thức cộng và dấu chấm phẩy kết thúc câu lệnh. Parser cũng phải xác định ranh giới của biểu thức và câu lệnh theo grammar Java.

Giai đoạn parse trả lời câu hỏi: **các token có tạo thành một cấu trúc Java hợp lệ hay không, và cấu trúc đó gồm những thành phần nào?**

Parse source là một bước trong compilation pipeline:

~~~text
Java source (.java)
        |
        v
Lexical analysis / scanning
        |
        v
Tokens
        |
        v
Parsing
        |
        v
Abstract Syntax Tree (AST)
        |
        v
Symbol entry, annotation processing,
semantic analysis and flow checks
        |
        v
Desugaring and bytecode generation
        |
        v
.class files
~~~

Đây là mô hình khái quát để hiểu luồng biên dịch. Chi tiết nội bộ và thứ tự một số công việc có thể khác nhau theo compiler, nhưng cần giữ rõ ranh giới giữa nhận diện token, phân tích cú pháp, kiểm tra ý nghĩa và sinh bytecode.

## 2. Từ source text đến token

Trước khi parser phân tích cấu trúc, compiler phải nhận diện các đơn vị từ vựng trong source. Giai đoạn này thường được gọi là lexical analysis, scanning hoặc lexing.

Với đoạn mã:

~~~java
int count = 10 + 20;
~~~

Một chuỗi token khái quát là:

| Văn bản | Loại token |
|---|---|
| int | Keyword / primitive type keyword |
| count | Identifier |
| = | Assignment operator |
| 10 | Integer literal |
| + | Additive operator |
| 20 | Integer literal |
| ; | Semicolon / separator |

Whitespace và comment giúp source dễ đọc nhưng thông thường không trở thành node cú pháp độc lập trong AST. Tuy vậy, compiler và công cụ phân tích vẫn có thể lưu vị trí nguồn để báo lỗi, điều hướng IDE hoặc liên kết node với đoạn văn bản ban đầu.

Cần phân biệt token với cú pháp. Token + tự nó chỉ là một toán tử. Parser mới xác định nó thuộc biểu thức nào, toán hạng trái và phải là gì, và biểu thức đó nằm trong câu lệnh nào.

Ví dụ, hai đoạn sau có thể tạo ra cấu trúc biểu thức tương đương dù cách trình bày khác nhau:

~~~java
int result = a + b * c;
~~~

~~~java
int result=a+b*c;
~~~

Parser dựa vào grammar và precedence của toán tử để hiểu phép nhân được nhóm trước phép cộng. Khoảng trắng không quyết định thứ tự thực hiện của biểu thức.

## 3. Grammar quyết định cấu trúc hợp lệ

Java Language Specification định nghĩa grammar của ngôn ngữ. Parser sử dụng các quy tắc cú pháp này để nhận biết compilation unit, khai báo package, import, class, interface, method, field, statement, expression và các cấu trúc khác.

Một số ví dụ về quan hệ giữa token và grammar:

- Một **compilation unit** có thể chứa khai báo package, các khai báo import và các khai báo kiểu cấp cao nhất.
- Một **class declaration** có modifier, tên class, phần khai báo type parameter nếu có, superclass/interfaces và class body.
- Một **method declaration** có modifier, kiểu trả về, tên, danh sách parameter và method body hoặc dấu chấm phẩy trong trường hợp khai báo phù hợp.
- Một **statement** có thể là block, khai báo biến cục bộ, biểu thức, if, for, while, return, throw, try và các cấu trúc điều khiển khác.
- Một **expression** có thể gồm literal, tên biến, lời gọi method, truy cập field, toán tử, tạo object, lambda hoặc biểu thức điều kiện.

Parser phải áp dụng precedence và associativity để tạo nhóm biểu thức chính xác. Ví dụ:

~~~java
int value = a + b * c;
~~~

Cấu trúc được hiểu tương đương:

~~~java
int value = a + (b * c);
~~~

Còn dấu ngoặc có thể thay đổi nhóm:

~~~java
int value = (a + b) * c;
~~~

Cú pháp có thể hợp lệ dù chương trình chưa có ý nghĩa về kiểu hoặc symbol. Việc kiểm tra những điều đó thuộc các bước sau.

## 4. Abstract Syntax Tree (AST)

Sau khi phân tích cú pháp, compiler biểu diễn source bằng một cây cú pháp trừu tượng, gọi là **Abstract Syntax Tree (AST)**. Mỗi node thể hiện một thành phần có ý nghĩa cú pháp như compilation unit, class, method, variable, statement, expression hoặc type.

Ví dụ:

~~~java
int total = price + tax;
~~~

Có thể hình dung AST ở mức khái quát như sau:

~~~text
VariableDeclaration
├── Type: int
├── Name: total
└── Initializer: Addition
    ├── Identifier: price
    └── Identifier: tax
~~~

AST không đơn giản là bản sao từng ký tự trong file. Nó tổ chức source theo quan hệ cú pháp và thường lược bỏ chi tiết trình bày như khoảng trắng, xuống dòng và comment. Vì thế, AST hữu ích cho compiler và các công cụ muốn hiểu cấu trúc chương trình.

Các node thường gặp trong cây của Java:

| Thành phần source | Node AST điển hình |
|---|---|
| package demo; | Package declaration / package name |
| import java.util.List; | Import tree |
| class User { ... } | Class tree |
| int age; | Variable tree |
| void run() { ... } | Method tree |
| if (ready) { ... } | If statement tree |
| a + b | Binary expression tree |
| new User() | New class expression tree |
| return value; | Return statement tree |

Một AST có thể được duyệt để tìm tất cả method, đếm lời gọi method, tìm literal, kiểm tra pattern code hoặc xây dựng công cụ phân tích tĩnh. IDE cũng sử dụng cấu trúc cú pháp để cung cấp điều hướng, completion, refactoring và hiển thị lỗi.

AST của compiler không nhất thiết bảo toàn đầy đủ định dạng ban đầu. Nếu cần sửa source mà giữ comment, khoảng trắng và style, cần thêm thông tin source position hoặc dùng parser có khả năng giữ concrete syntax/trivia. Không nên giả định rằng chuyển AST thành source sẽ tái tạo chính xác file ban đầu.

## 5. Parse error và semantic error khác nhau

Một lỗi cú pháp xuất hiện khi token không thể được tổ chức thành cấu trúc phù hợp với grammar.

Ví dụ lỗi cú pháp:

~~~java
class Example {
    void run() {
        int total = ;
    }
}
~~~

Sau dấu gán, parser mong đợi một biểu thức khởi tạo nhưng gặp dấu chấm phẩy. Compiler có thể báo lỗi tại vị trí đó hoặc tại một token liên quan, tùy cách parser phát hiện lỗi và cơ chế phục hồi.

Một chương trình khác có cú pháp hợp lệ nhưng sai về kiểu:

~~~java
class Example {
    void run() {
        int total = "hello";
    }
}
~~~

Khai báo, phép gán và literal đều được tổ chức thành cấu trúc Java hợp lệ. Tuy nhiên, chuỗi không thể gán cho biến int; lỗi này được phát hiện trong semantic analysis/type checking, sau khi parser đã tạo cấu trúc cú pháp.

Một ví dụ khác:

~~~java
class Example {
    void run() {
        UnknownType value;
    }
}
~~~

Cú pháp khai báo biến có thể được parse thành công, nhưng compiler không tìm được kiểu UnknownType khi thực hiện các bước phân giải symbol và kiểu.

| Loại lỗi | Ví dụ | Giai đoạn thường phát hiện |
|---|---|---|
| Syntax error | Thiếu ;, thiếu ), sai cấu trúc block | Parsing |
| Unknown symbol/type | Dùng class hoặc biến chưa được khai báo | Symbol resolution / semantic analysis |
| Type mismatch | Gán String cho int | Type checking |
| Definite assignment / flow error | Đọc biến cục bộ chưa chắc đã được gán | Flow analysis |
| Runtime exception | Chia số nguyên cho 0 khi chạy | Runtime |

Ranh giới trên là cách phân loại để học và chẩn đoán. Một diagnostic cụ thể đôi khi được phát hiện ở bước phụ thuộc hoặc ở một giai đoạn khác của compiler; hãy đọc nội dung và vị trí lỗi thay vì chỉ dựa vào tên giai đoạn.

## 6. Parser xử lý lỗi như thế nào?

Khi gặp cú pháp sai, parser thường tạo diagnostic gồm thông tin như:

- Tên file source.
- Dòng và cột xảy ra lỗi.
- Vị trí hoặc đoạn source liên quan.
- Loại diagnostic, ví dụ ERROR hoặc WARNING.
- Thông điệp giải thích cấu trúc mà compiler mong đợi hoặc token gây lỗi.

Compiler có thể cố gắng phục hồi sau một lỗi để tiếp tục phân tích và báo thêm lỗi khác. Ví dụ, parser có thể bỏ qua một token hoặc đồng bộ lại tại dấu ;, dấu } hay một điểm bắt đầu cấu trúc tiếp theo. Vì vậy, một file sai cú pháp có thể tạo nhiều diagnostic; các lỗi phía sau đôi khi chỉ là hệ quả của lỗi đầu tiên.

Khi sửa lỗi, nên xử lý diagnostic đầu tiên có vị trí đáng tin cậy rồi biên dịch lại. Một dấu ngoặc thiếu ở phía trên có thể khiến parser hiểu sai nhiều dòng phía dưới.

Diagnostic không phải lúc nào cũng chỉ đúng ký tự cần chèn. Vị trí báo lỗi thường là nơi compiler nhận ra rằng chuỗi token không còn phù hợp với grammar. Token gây ra lỗi có thể nằm sau vị trí mà lỗi thực sự bắt đầu.

## 7. Quan sát giai đoạn parse bằng javac

**javac** là compiler Java đi kèm JDK. Khi chạy lệnh javac thông thường, compiler thực hiện nhiều bước của compilation pipeline, bao gồm parse, phân giải và kiểm tra, rồi sinh bytecode nếu không có lỗi ngăn cản.

Lệnh cơ bản:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/Greeting.java
~~~

Ý nghĩa:

- **--release 17:** biên dịch theo API và bytecode của Java 17.
- **-encoding UTF-8:** chỉ định encoding của source file.
- **-d out:** đặt file .class được sinh ra trong thư mục out.
- **src/demo/Greeting.java:** source cần biên dịch.

Lệnh trên là một lần biên dịch hoàn chỉnh, không phải lệnh chỉ chạy parser. Nếu muốn quan sát riêng AST sau parse trong một công cụ Java, có thể sử dụng Compiler Tree API.

Không nên dựa vào các class nội bộ như com.sun.tools.javac.parser.Parser để xây dựng công cụ lâu dài. Những class nội bộ này là implementation detail, có thể thay đổi giữa các JDK và thường không phải API được cam kết ổn định.

## 8. Dùng JavacTask.parse() để parse source mà chưa phân tích ngữ nghĩa

JDK cung cấp Java Compiler API và Compiler Tree API trong module **jdk.compiler**. **JavacTask.parse()** cho phép yêu cầu compiler parse source và trả về các **CompilationUnitTree**.

Điểm quan trọng:

- **parse()** tạo cấu trúc cú pháp và phát sinh diagnostic cú pháp.
- **analyze()** yêu cầu compiler thực hiện các bước phân tích ngữ nghĩa như phân giải và kiểm tra kiểu.
- **generate()** yêu cầu sinh class file.
- Chỉ gọi parse() giúp công cụ quan sát cú pháp mà chưa chủ động yêu cầu các bước analyze/generate.

Ví dụ hoàn chỉnh dưới đây đưa source vào bộ nhớ, parse và in thông tin của compilation unit:

~~~java
import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.util.JavacTask;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;
import java.net.URI;
import java.util.List;

public class ParseSourceDemo {

    private static final class SourceFile extends SimpleJavaFileObject {
        private final String content;

        private SourceFile(String className, String content) {
            super(
                    URI.create("string:///"
                            + className.replace('.', '/')
                            + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE
            );
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK with jdk.compiler is required.");
        }

        String source = """
                package demo;

                import java.util.List;

                class Greeting {
                    String message() {
                        return "hello";
                    }
                }
                """;

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        JavaFileObject sourceFile = new SourceFile("demo.Greeting", source);

        JavacTask task = (JavacTask) compiler.getTask(
                null,
                null,
                diagnostics,
                List.of("--release", "17", "-proc:none"),
                null,
                List.of(sourceFile)
        );

        int compilationUnitCount = 0;

        for (CompilationUnitTree unit : task.parse()) {
            compilationUnitCount++;

            String packageName = unit.getPackageName() == null
                    ? "<default>"
                    : unit.getPackageName().toString();

            System.out.println("Package: " + packageName);
            System.out.println("Imports: " + unit.getImports().size());

            for (Tree declaration : unit.getTypeDecls()) {
                if (declaration instanceof ClassTree type) {
                    System.out.println(
                            "Top-level type: " + type.getSimpleName());
                }
            }
        }

        long syntaxErrors = diagnostics.getDiagnostics().stream()
                .filter(diagnostic ->
                        diagnostic.getKind() == Diagnostic.Kind.ERROR)
                .count();

        System.out.println("Compilation units: " + compilationUnitCount);
        System.out.println("Syntax errors: " + syntaxErrors);
    }
}
~~~

Lưu thành **ParseSourceDemo.java**, sau đó biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ParseSourceDemo.java
java ParseSourceDemo
~~~

Kết quả:

~~~text
Package: demo
Imports: 1
Top-level type: Greeting
Compilation units: 1
Syntax errors: 0
~~~

Chương trình tạo một JavaFileObject từ chuỗi source trong bộ nhớ, đưa file đó cho compiler, rồi gọi JavacTask.parse(). Nó duyệt từng compilation unit và đọc package name, danh sách import cùng các kiểu cấp cao nhất.

Ví dụ không gọi task.analyze() hoặc task.generate(). Do đó, chương trình chỉ minh họa việc parse và kiểm tra syntax diagnostics. Import java.util.List trong source mẫu không được yêu cầu phân giải kiểu ở bước này; việc kiểm tra import có tồn tại và sử dụng đúng hay không thuộc bước phân tích sau.

ToolProvider.getSystemJavaCompiler() cần compiler của JDK. Nếu chương trình chạy trong runtime image đã lược bỏ module compiler hoặc môi trường chỉ có runtime, kết quả có thể là null. Công cụ parse source vì thế nên chạy trong môi trường có jdk.compiler.

## 9. Duyệt AST bằng Compiler Tree API

Các node trong AST được biểu diễn qua những interface thuộc package com.sun.source.tree. Ví dụ:

- **CompilationUnitTree:** một file source đã parse.
- **ClassTree:** khai báo class, interface, enum hoặc record.
- **MethodTree:** khai báo method hoặc constructor.
- **VariableTree:** khai báo biến, field hoặc parameter.
- **BlockTree:** một block câu lệnh.
- **IfTree:** câu lệnh điều kiện.
- **MethodInvocationTree:** lời gọi method.
- **BinaryTree:** biểu thức toán tử hai ngôi.
- **LiteralTree:** literal như số, chuỗi, boolean hoặc null.

Để duyệt nhiều loại node, dùng **TreeScanner**. Đây là ví dụ minh họa cách đếm các method declaration trong một compilation unit đã parse:

~~~java
import com.sun.source.tree.MethodTree;
import com.sun.source.util.TreeScanner;

class MethodCounter extends TreeScanner<Integer, Void> {

    @Override
    public Integer visitMethod(MethodTree node, Void unused) {
        Integer nested = super.visitMethod(node, unused);
        return 1 + (nested == null ? 0 : nested);
    }

    @Override
    public Integer reduce(Integer left, Integer right) {
        if (left == null) {
            return right;
        }
        if (right == null) {
            return left;
        }
        return left + right;
    }
}
~~~

Đây là một class minh họa, không phải chương trình độc lập. Sau khi có **CompilationUnitTree unit**, có thể dùng:

~~~java
int methodCount = new MethodCounter().scan(unit, null);
~~~

TreeScanner tự đi qua các node con. Mỗi lần gặp method, visitMethod cộng một rồi tiếp tục duyệt các thành phần bên trong method. Tùy mục đích, có thể override các visitor khác để tìm field, lời gọi method, literal hoặc cấu trúc điều khiển.

Nếu cần biết vị trí source của một node, có thể dùng **Trees.instance(task)** và **SourcePositions** trong Compiler Tree API. Vị trí này hữu ích khi xây dựng diagnostic, báo cáo phân tích hoặc liên kết kết quả với editor. Cần nhớ rằng vị trí được tính theo source file và hệ tọa độ của compiler; công cụ nên dùng API vị trí thay vì tự đoán từ chuỗi đã format.

## 10. Khi nào nên parse source bằng javac API?

Parse source hữu ích cho các công cụ làm việc trực tiếp với cấu trúc Java:

- **Static analysis:** tìm pattern code, kiểm tra quy ước hoặc phát hiện cấu trúc đáng chú ý.
- **Source inspection:** liệt kê package, class, method, field và annotation.
- **Code metrics:** đếm method, statement hoặc các cấu trúc cú pháp.
- **Refactoring tools:** xác định node và vị trí source trước khi tạo thay đổi.
- **Documentation tools:** trích xuất khai báo và cấu trúc source để tạo báo cáo.
- **Build tooling:** kiểm tra hoặc phân tích source trong quy trình build.
- **IDE tooling:** hỗ trợ điều hướng, tìm symbol, completion và hiển thị lỗi.

Nếu chỉ cần biên dịch ứng dụng, hãy dùng javac hoặc build tool như Gradle/Maven. Không cần tự viết parser riêng để biên dịch Java thông thường.

Nếu cần phân tích đầy đủ type, method overload, generic, annotation processing hoặc quan hệ symbol, chỉ parse là chưa đủ. Cần các bước analyze phù hợp và phải quản lý classpath/module path để compiler tìm thấy dependency. Công cụ cũng cần cân nhắc annotation processor có thể thực thi code trong quá trình compilation; không nên bật xử lý annotation không tin cậy trong một công cụ phân tích source an toàn.

## 11. Các lỗi thường gặp khi làm việc với parse source

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Parser báo lỗi tại dấu ; | Biểu thức hoặc cấu trúc phía trước chưa hoàn chỉnh. | Kiểm tra token ngay trước vị trí báo lỗi. |
| Nhiều lỗi xuất hiện sau một lỗi ngoặc | Parser phục hồi từ cấu trúc block bị sai. | Sửa lỗi đầu tiên rồi parse lại. |
| Source hợp cú pháp nhưng javac vẫn fail | Lỗi nằm ở phân giải symbol, type checking, flow hoặc bước sau. | Đọc loại diagnostic và phân biệt parse với analyze. |
| Compiler không tìm thấy compiler | Đang chạy runtime thiếu jdk.compiler hoặc không có system compiler. | Chạy công cụ bằng JDK đầy đủ có compiler module. |
| AST thiếu comment hoặc format | AST tập trung vào cấu trúc cú pháp, không phải bản sao lossless của source. | Lưu source positions hoặc chọn parser giữ trivia nếu cần. |
| Parse source đúng nhưng tool báo lỗi khi analyze | Classpath, module path, release hoặc dependency không đúng. | Cấu hình môi trường compiler và dependency tương ứng. |
| Source tiếng Việt hoặc ký tự Unicode lỗi | Đọc file bằng encoding sai. | Chỉ định encoding phù hợp, ví dụ UTF-8, khi đọc source. |
| Dùng class nội bộ javac bị lỗi sau khi nâng JDK | Phụ thuộc implementation detail không có cam kết tương thích. | Ưu tiên Java Compiler API và Compiler Tree API công khai. |

Một nguyên tắc chẩn đoán hữu ích là xác định compiler đang dừng ở bước nào. Lỗi cú pháp cần sửa source grammar; lỗi symbol/type cần kiểm tra dependency và ngữ nghĩa; lỗi sinh bytecode hoặc runtime cần xem các bước sau nữa.

## 12. Checklist khi phân tích source Java

- [ ] Đã phân biệt source text, token và AST.
- [ ] Đã hiểu parser kiểm tra grammar và tạo cấu trúc cú pháp.
- [ ] Đã phân biệt syntax error với symbol/type/flow error.
- [ ] Đã hiểu parser có thể phục hồi và phát ra nhiều diagnostic.
- [ ] Đã biết compilation unit chứa package, imports và type declarations.
- [ ] Đã dùng API công khai nếu cần parse source bằng chương trình.
- [ ] Đã phân biệt JavacTask.parse(), analyze() và generate().
- [ ] Đã cấu hình JDK/compiler module, release và encoding phù hợp.
- [ ] Đã dùng AST visitor/scanner thay vì phân tích source bằng regex cho cấu trúc Java phức tạp.
- [ ] Đã cân nhắc source position, comment và format nếu công cụ cần sửa hoặc hiển thị lại source.

Parse source biến văn bản Java thành cấu trúc mà compiler và công cụ có thể hiểu. Khi nắm rõ token, grammar, AST và ranh giới với semantic analysis, việc đọc diagnostic, xây dựng công cụ phân tích source và xử lý lỗi biên dịch sẽ chính xác hơn.