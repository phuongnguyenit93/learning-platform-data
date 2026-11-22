# Từ ký tự nguồn đến token và cây cú pháp trừu tượng trong Java

Khi đọc một tệp **.java**, trình biên dịch không hiểu toàn bộ chương trình bằng cách nhìn ngay vào từng dòng như con người. Nó đi qua những mức biểu diễn có cấu trúc ngày càng rõ: **ký tự nguồn → đơn vị từ vựng (token) → cấu trúc cú pháp → cây cú pháp trừu tượng (AST)**. Sau đó compiler mới tiếp tục những công việc như phân giải tên, kiểm tra kiểu, phân tích luồng và sinh bytecode.

Hiểu chặng đầu này giúp giải thích vì sao có mã trông “gần đúng” nhưng compiler lại báo lỗi ký tự, lỗi cú pháp hoặc lỗi kiểu hoàn toàn khác nhau; vì sao khoảng trắng đôi khi làm thay đổi ý nghĩa; và vì sao AST thể hiện cấu trúc biểu thức chứ không đơn thuần là bản sao của từng ký tự.

## 1. Toàn cảnh đường đi của mã nguồn

Ví dụ tệp **Expressions.java**:

~~~java
public class Expressions {
    public static void main(String[] args) {
        int result = 2 + 3 * 4;
        System.out.println(result);
    }
}
~~~

Có thể hình dung đường đi:

~~~text
Tệp .java (byte, theo charset)
       |
       v
Giải mã thành ký tự Unicode của mã nguồn
       |
       v
Dịch Unicode escape, nhận diện kết thúc dòng
       |
       v
Phân tích từ vựng (lexical analysis / scanning)
       |  Bỏ qua khoảng trắng và comment khi lập token stream
       v
Token stream: int | result | = | 2 | + | 3 | * | 4 | ;
       |
       v
Phân tích cú pháp (parsing) theo ngữ pháp Java
       |
       v
AST: khai báo biến
       └── giá trị khởi tạo: cộng
           ├── 2
           └── nhân
               ├── 3
               └── 4
       |
       v
Các bước ngữ nghĩa và sinh mã (ngoài phạm vi chính của bài)
~~~

**Điều cốt lõi:** lexer nhận diện *“đây là token gì?”*; parser xác định *“các token kết hợp thành cấu trúc hợp lệ nào?”*. AST là một kết quả của bước parser. **AST chưa chứng minh chương trình đúng kiểu hoặc chạy được.**

Ba cấp dữ liệu không nên trộn lẫn:

| Cấp | Ví dụ | Thông tin chủ yếu |
| --- | --- | --- |
| Ký tự nguồn | Các ký tự của chuỗi "result = 2 + 3 * 4;" | Văn bản, vị trí, dấu cách, dấu nháy |
| Token | IDENTIFIER(result), ASSIGN(=), INT_LITERAL(2), PLUS(+), ... | Loại token, nội dung và thường có vị trí nguồn |
| AST | VariableDecl(result, Binary(+,...)) | Quan hệ cha–con, ưu tiên toán tử, loại cấu trúc ngữ pháp |

Trong một compiler thực tế, các pha có thể phối hợp và có tối ưu hóa nội bộ; sơ đồ là **mô hình khái niệm**, không khẳng định mọi compiler bắt buộc lưu ba bản trung gian riêng biệt trong bộ nhớ.

## 2. Đầu vào: byte, ký tự Unicode và quy tắc từ vựng

### 2.1. Tệp nguồn có encoding; ngôn ngữ xử lý ký tự

Tệp trên đĩa là **byte**. Công cụ biên dịch phải giải mã byte theo character encoding đã chọn (ví dụ UTF-8) rồi mới làm việc với ký tự mã nguồn. Khi dùng **javac**, có thể yêu cầu encoding bằng tùy chọn **-encoding**:

~~~bash
javac -encoding UTF-8 -d out Expressions.java
~~~

Tùy chọn này quyết định cách đọc byte trong tệp; nó **khác** cú pháp Unicode escape được viết bên trong nguồn. Nếu encoding của tệp không khớp với encoding compiler sử dụng, nội dung Unicode có thể bị đọc sai hoặc gây lỗi ngay trước khi việc nhận diện token diễn ra.

Ngôn ngữ Java dùng Unicode, nên identifier có thể chứa những chữ cái không thuộc ASCII nếu thỏa quy tắc định danh của Java, ví dụ **tổngSố**. Tuy nhiên việc lexer coi một ký tự là một phần identifier, khoảng trắng hoặc ký tự không hợp lệ vẫn do Java Language Specification (JLS) quyết định; không phải mọi ký tự nhìn giống chữ hay khoảng trắng đều được đối xử giống nhau.

### 2.2. Ba bước chuyển dịch từ vựng theo JLS

JLS mô tả quá trình dịch ký tự trước khi có token theo thứ tự:

1. **Unicode escapes** trong dòng ký tự đầu vào được biến thành ký tự tương ứng.
2. Dòng ký tự sau bước trên được chia thành **input characters** và **line terminators**.
3. Từ đó nhận diện **input elements** gồm khoảng trắng, comment và token. Khoảng trắng/comment không trở thành token được dùng bởi ngữ pháp cú pháp.

Thứ tự có ý nghĩa. Ví dụ chuỗi nguồn dưới đây chứa Unicode escape với ký tự **a**:

~~~java
public cl\u0061ss Demo {
}
~~~

Sau dịch Unicode escape, phần **cl\u0061ss** trở thành **class**. Lexer vì thế nhận diện **class** là keyword. Đây là một ví dụ có thể biên dịch khi lưu thành **Demo.java**:

~~~bash
javac Demo.java
~~~

Unicode escape dùng dấu gạch chéo ngược, một hoặc nhiều chữ **u** và đúng bốn chữ số thập lục phân cho một UTF-16 code unit. Với ký tự ngoài Basic Multilingual Plane, một cặp UTF-16 surrogate có thể được biểu diễn bằng hai Unicode escapes theo quy tắc JLS.

**Không nhầm Unicode escape và string escape.** Hai lớp xử lý xảy ra ở thời điểm khác nhau:

- **\u000a** trong mã nguồn được xử lý trước khi lexer phân loại dấu nháy và chuỗi: nó tạo ký tự xuống dòng thật.
- **\n** nằm bên trong một Java string literal là escape sequence được diễn giải trong văn cảnh literal.

Do đó đoạn sau **cố ý không hợp lệ**:

~~~java
// Không hợp lệ: Unicode escape biến thành xuống dòng ngay trong literal.
String text = "\u000a";
~~~

Trong khi đoạn sau hợp lệ:

~~~java
String text = "\n";
~~~

Quy tắc sớm này cũng có nghĩa **Unicode escapes có thể tạo dấu gạch chéo, dấu nháy hoặc dấu xuống dòng trước khi xác định comment/string**. Khi review mã nguồn có những escape lạ trong comment, đừng giả định mọi ký tự nhìn thấy sau **//** đều mãi là nội dung comment. Chi tiết về điều kiện nhận dạng dấu **\\** và escape liên tiếp phải theo JLS §3.3, không suy đoán “thấy backslash-u là thay thế trong mọi trường hợp”.

### 2.3. Line terminator không chỉ là trình bày

JLS nhận diện kết thúc dòng theo **LF**, **CR** hoặc cặp **CRLF**. Chúng giúp compiler theo dõi vị trí lỗi và xác định nơi kết thúc comment kiểu **//**. Một dấu xuống dòng phát sinh từ Unicode escape có thể đổi chỗ comment kết thúc. Độ rộng tab hoặc cách IDE xuống dòng ảnh hưởng cách con người nhìn thấy tệp, nhưng ngữ pháp Java dựa trên các ký tự đầu vào đã chuẩn hóa theo quy tắc của ngôn ngữ.

## 3. Lexer (scanner): tách ký tự thành token

**Lexical analysis**, hay scanning, chuyển chuỗi ký tự sau các bước dịch thành token có loại xác định. Một token thường mang:

- **Kind/type**: identifier, keyword, literal, dấu phân cách hay toán tử.
- **Lexeme**: chuỗi ký tự tương ứng, chẳng hạn **result** hoặc **+=**.
- **Vị trí nguồn**: offset/dòng/cột dùng để báo lỗi hoặc hỗ trợ công cụ. Định dạng cụ thể phụ thuộc compiler.

JLS phân loại token thành **identifier, keyword, literal, separator, operator**. Khoảng trắng và comment là những input elements khác, thường bị bỏ khỏi token stream phục vụ parsing.

### 3.1. Các loại token bằng ví dụ

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| Keyword | **class**, **public**, **int**, **if**, **return** | Có ý nghĩa ngữ pháp do ngôn ngữ quy định |
| Identifier | **Expressions**, **result**, **main**, **println** | Tên do lập trình viên hoặc API đặt, xét theo ngữ cảnh |
| Literal | **42**, **3.5**, **'A'**, **"Hello"**, **true**, **null** | Biểu diễn giá trị trực tiếp trong nguồn |
| Separator | **(**, **)**, **{**, **}**, **[**, **]**, **;**, **,**, **.** | Phân định các phần cú pháp |
| Operator | **=**, **+**, **\***, **==**, **&&**, **++**, **->** | Phép gán, tính toán, so sánh, biểu thức lambda... |

**Lưu ý ngôn ngữ theo phiên bản:** Java có các **contextual keywords** và tên bị hạn chế trong một số ngữ cảnh như **var**, **yield**, **record** hoặc **sealed**. Không nên xây dựng lexer Java đời mới bằng bảng “mọi chuỗi này đều luôn là từ khóa” đơn giản; việc diễn giải một số từ còn phụ thuộc ngữ cảnh cú pháp và phiên bản nguồn. **true**, **false**, **null** là literal theo JLS, không đơn thuần là identifier do người dùng đặt.

### 3.2. Phân tách cụ thể một câu lệnh

Cho nguồn:

~~~java
int result = 2 + 3 * 4;
~~~

Có thể biểu diễn luồng token bằng bảng:

| Thứ tự | Lexeme | Nhóm token |
| ---: | --- | --- |
| 1 | **int** | Keyword |
| 2 | **result** | Identifier |
| 3 | **=** | Operator |
| 4 | **2** | Integer literal |
| 5 | **+** | Operator |
| 6 | **3** | Integer literal |
| 7 | **\*** | Operator |
| 8 | **4** | Integer literal |
| 9 | **;** | Separator |

Dấu cách giữa chúng không được liệt kê vì không phải token cú pháp. Ngược lại, **khoảng trắng vẫn có thể quyết định ranh giới token**: **int result** chứa keyword **int** rồi identifier **result**; còn **intresult** là một identifier riêng, không phải hai token.

### 3.3. Chuỗi ký tự và comment được nhận diện theo quy tắc lexer

Xét:

~~~java
int result /* cộng giá trị */ = 2 + 3; // ghi chú
String message = "2 + 3";
~~~

Ở câu lệnh đầu, các comment không góp token vào biểu thức. Trong câu lệnh sau, phần **"2 + 3"** được nhận diện là **một string literal token**, không bị tách thành các toán tử và số ở bên trong dấu nháy.

Phải phân biệt các ý:

- **/** và **\*** độc lập là operator; **/* ... */** là comment nhiều dòng theo ngữ pháp từ vựng.
- **//** bắt đầu end-of-line comment và kéo dài đến line terminator.
- **/**, **\*** hoặc dấu **+** trong một string literal hợp lệ là nội dung literal, không được lex thành toán tử bên ngoài chuỗi.
- **/***\* ... \*/** là dạng tài liệu Javadoc đặc biệt đối với công cụ tài liệu, nhưng khi phân tích cú pháp chương trình Java thì vẫn là comment; compiler/công cụ có thể giữ metadata comment ở một đường xử lý riêng để phục vụ Javadoc.

Comment và khoảng trắng thường được bỏ khi xây dựng AST; do đó AST cơ bản không phải bản thể hiện trung thực từng dấu cách/comment của nguồn. Formatter và IDE muốn giữ nguyên vị trí comment sẽ cần thêm dữ liệu nguồn hoặc cấu trúc cú pháp giàu thông tin hơn AST thuần túy.

### 3.4. Quy tắc “longest possible match” (maximal munch)

Lexer thường nhận **token dài nhất có thể** theo quy tắc của JLS thay vì tự chia nhỏ để tạo một biểu thức có vẻ hợp lý. Ví dụ:

~~~text
Nguồn:    a--b
Token:    IDENTIFIER(a)  --  IDENTIFIER(b)
Không là: IDENTIFIER(a)  -  -  IDENTIFIER(b)
~~~

Nếu người lập trình muốn trừ một số âm, cần viết ranh giới rõ ràng:

~~~java
int a = 5;
int b = 2;
int c = a - -b;
System.out.println(c);
~~~

Kết quả là **7**. Còn **a--b** không phải cú pháp thay cho **a - -b**: lexer nhận **--**, khiến parser phải xử lý theo quy tắc toán tử giảm giá trị và vị trí các toán hạng, dẫn đến lỗi cú pháp khi viết như trên.

**Ngoại lệ có ngữ cảnh:** Java hiện đại có quy tắc đặc biệt cho **các dấu > liên tiếp trong generic type arguments** và một số contextual keywords. Chẳng hạn **List<List<String>>** có thể đóng hai tham số kiểu bằng **>>**, trong khi **a >> 1** là biểu thức dịch bit. Lexer/parser không thể được giải thích chính xác chỉ bằng một mẹo “luôn lấy toán tử dài nhất rồi không xét ngữ cảnh” cho mọi trường hợp.

### 3.5. Literal không phải lúc nào cũng là số rồi dấu

**1_000**, **0xFF**, **3.14** là những literal hợp lệ (tùy ngữ cảnh và kiểu). Lexer phải hiểu cấu trúc của từng loại literal, không chỉ gom mọi chuỗi chữ số. Ví dụ **"hello world"** chứa khoảng trắng nhưng là một string literal token; **'A'** là character literal. Cú pháp text block **"""..."""** được hỗ trợ ở Java 17+, có quy tắc riêng đối với dấu phân cách và xuống dòng. Các ký tự hoặc escape thiếu hợp lệ trong literal có thể khiến lexer/compiler báo lỗi trước khi có AST hoàn chỉnh.

## 4. Parser: từ token thành cấu trúc ngữ pháp

Sau khi có token stream, **parser** áp dụng các production rule trong ngữ pháp Java để nhận diện compilation unit, khai báo class/interface, field, method, statement, expression và các cấu trúc lồng nhau. Một chuỗi token hợp lệ về mặt từ vựng vẫn có thể **không hợp lệ về cú pháp**.

Ví dụ lexer tách được toàn bộ token sau:

~~~java
int result = ;
~~~

Nhưng parser không thể tạo biểu thức hợp lệ sau dấu **=** vì gặp **;** quá sớm. Đây là **lỗi cú pháp**. Ngược lại:

~~~java
int result = "hello";
~~~

có cấu trúc cú pháp hợp lệ (khai báo biến với initializer), nhưng **không gán được String vào int**. Lỗi này thuộc bước phân tích ngữ nghĩa/kiểm tra kiểu về sau, không phải lỗi scanner.

### 4.1. AST biểu diễn cấu trúc, không phải chuỗi token phẳng

Trong câu:

~~~java
int result = 2 + 3 * 4;
~~~

toán tử **\*** có độ ưu tiên cao hơn **+**. Parser xây dựng một cấu trúc tương đương:

~~~text
Variable declaration: result
├── Type: int
└── Initializer: PLUS
    ├── Left:  INTEGER_LITERAL(2)
    └── Right: MULTIPLY
        ├── Left:  INTEGER_LITERAL(3)
        └── Right: INTEGER_LITERAL(4)
~~~

Như vậy kết quả phép tính là **14**, dù nhìn từ trái sang phải người mới học đôi khi nhầm thành **(2 + 3) * 4 = 20**.

Nếu thêm ngoặc:

~~~java
int result = (2 + 3) * 4;
~~~

thì AST của initializer sẽ có phép **MULTIPLY** ở cấp ngoài, và phép **PLUS** nằm bên trong (parser hoặc AST API có thể giữ thêm nút **PARENTHESIZED** cho phần đặt ngoặc). Giá trị trở thành **20**.

**Nhận diện ngữ pháp ≠ tính toán giá trị:** AST mô tả biểu thức và thứ tự thực hiện; compiler có thể tính hằng hoặc tối ưu hóa ở giai đoạn sau, nhưng việc một AST có nút PLUS không đồng nghĩa parser đã chạy phép cộng.

### 4.2. Một chương trình nhỏ minh họa khác biệt AST

Tạo **Expressions.java**:

~~~java
public class Expressions {
    public static void main(String[] args) {
        int first = 2 + 3 * 4;
        int second = (2 + 3) * 4;
        System.out.println(first);
        System.out.println(second);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -d out Expressions.java
java -cp out Expressions
~~~

**Standard output chính xác:**

~~~text
14
20
~~~

Từ lexer, cả hai câu lệnh đều chứa token **2**, **+**, **3**, **\***, **4** (câu lệnh thứ hai có thêm **(**, **)**). Từ parser, chúng có hình dạng AST khác nhau theo ngữ pháp ưu tiên và dấu ngoặc. Mẫu này đủ để phân biệt **tokenization** và **parsing** mà không phải tự viết một compiler.

### 4.3. Cây cú pháp cụ thể (CST/parse tree) so với AST

**Parse tree/CST** (theo cách gọi chung trong lý thuyết compiler) có thể giữ gần đầy đủ các thành phần của grammar: nút trung gian, dấu ngoặc, dấu phân cách và terminal. **AST** chọn những nút hữu ích để biểu diễn ý nghĩa cấu trúc của chương trình như class, method, statement, expression.

| Tiêu chí | CST / parse tree khái niệm | AST |
| --- | --- | --- |
| Trọng tâm | Cách chuỗi token khớp quy tắc ngữ pháp | Cấu trúc chương trình phục vụ phân tích |
| Dấu chấm phẩy, ngoặc, phân cách | Thường hiện diện tường minh | Có thể được lược bỏ hoặc biểu diễn gián tiếp |
| Nút grammar trung gian | Thường nhiều | Thường ít hơn, gần các khái niệm ngôn ngữ |
| Công dụng | Parser, formatter cần giữ chi tiết cú pháp | Static analysis, IDE, kiểm tra ngữ nghĩa, chuyển đổi mã |

**Không có một hình dạng AST duy nhất áp dụng cho mọi compiler**. Ví dụ ở Java Compiler Tree API, các nút có enum kind như **CLASS**, **VARIABLE**, **PLUS**, **MULTIPLY**, và có node **PARENTHESIZED**. Một thư viện parser khác có thể dùng tên/nút trung gian khác nhưng vẫn biểu diễn cùng cấu trúc Java.

## 5. Thử quan sát AST thật bằng Java Compiler Tree API

Java cung cấp API phân tích cây cú pháp trong **jdk.compiler**, tiêu biểu là **com.sun.source.tree** và **com.sun.source.util.JavacTask**. Đây là API compiler/tree được công bố cho công cụ, khác với việc truy cập các class implementation nội bộ không ổn định trong **com.sun.tools.javac.***.

Ví dụ sau tạo một Java source **trong bộ nhớ**, gọi **parse()**, đi qua class declaration rồi tìm initializer của biến **answer**. Nó giúp kiểm chứng AST một cách thực tế.

Tạo tệp **InspectAst.java** (toàn bộ là một chương trình độc lập):

~~~java
import com.sun.source.tree.BinaryTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;
import java.net.URI;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class InspectAst {
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(
                URI.create("string:///Example.java"),
                JavaFileObject.Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static void main(String[] args) throws Exception {
        String code = "class Example { int answer = 2 + 3 * 4; }";
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        JavacTask task = (JavacTask) compiler.getTask(
            null, null, null, List.of("-proc:none"), null,
            List.of(new Source(code))
        );

        for (CompilationUnitTree unit : task.parse()) {
            for (Tree declaration : unit.getTypeDecls()) {
                System.out.println(declaration.getKind());
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitVariable(
                    VariableTree variable, Void unused
                ) {
                    if (variable.getName().contentEquals("answer")) {
                        Tree initializer = variable.getInitializer();
                        BinaryTree addition = (BinaryTree) initializer;
                        System.out.println(initializer.getKind());
                        System.out.println(
                            addition.getRightOperand().getKind()
                        );
                    }
                    return super.visitVariable(variable, unused);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Từ thư mục chứa tệp, chạy với **JDK 17+** (cần JDK có module **jdk.compiler**, không chỉ runtime image bị lược compiler):

~~~bash
javac -d out InspectAst.java
java -cp out InspectAst
~~~

**Standard output đã kiểm chứng trên JDK 21:**

~~~text
CLASS
PLUS
MULTIPLY
~~~

Cách đọc:

1. **CLASS**: AST chứa một top-level class **Example**.
2. **PLUS**: initializer của biến **answer** có phép cộng ở cấp ngoài.
3. **MULTIPLY**: nhánh bên phải của phép cộng là phép nhân **3 * 4**.

Gọi **JavacTask.parse()** để lấy cây cú pháp, **không gọi analyze()** hoặc generate() trong ví dụ này. Vì vậy chương trình minh họa đúng ranh giới **parser tạo AST**, không khẳng định đã kiểm tra mọi tên hay kiểu trong source string. Một runtime image không có Java compiler có thể khiến **ToolProvider.getSystemJavaCompiler()** trả về **null**; hãy dùng JDK đầy đủ.

**Lưu ý riêng về API:** **com.sun.source.tree** phản ánh cây theo Java Compiler API, không phải bộ token thô và không nhất thiết lưu comment/khoảng trắng. Nếu cần thao tác với mọi ký tự/format, hãy dùng parser tooling được thiết kế cho source-preserving hoặc bổ sung source positions. Không dùng các class nội bộ **com.sun.tools.javac.parser.*** như một public API ổn định cho ứng dụng.

## 6. Nhận diện ba nhóm lỗi theo giai đoạn

Ba đoạn dưới đây **minh họa lỗi**; chúng không phải ba chương trình đầy đủ để chạy.

### 6.1. Lỗi ở mức từ vựng

~~~java
String value = "chưa đóng;
~~~

Dấu nháy kép mở string mà không kết thúc hợp lệ. Scanner không thể tạo một string literal hoàn chỉnh và compiler báo lỗi liên quan literal/string. Tương tự, Unicode escape sai cú pháp hoặc ký tự không được phép cũng có thể gây lỗi giai đoạn đầu.

### 6.2. Lỗi ở mức cú pháp

~~~java
int count = ;
~~~

Các ký tự đều tách được thành token thông thường, nhưng ngữ pháp yêu cầu một expression sau dấu **=**; parser không thể tạo một khai báo biến hoàn chỉnh hợp lệ.

### 6.3. Lỗi ngữ nghĩa/kiểm tra kiểu

~~~java
int count = "five";
~~~

Token hợp lệ, cú pháp khai báo biến hợp lệ, AST có một initializer là string literal. Nhưng kiểu **String** không thể gán vào **int**. Lỗi xuất hiện khi compiler phân tích nghĩa của cây (type attribution/type checking).

| Dấu hiệu | Vùng xử lý khả dĩ | Cách suy luận |
| --- | --- | --- |
| Illegal character, unclosed literal | Đọc ký tự/scanning | Kiểm tra encoding, dấu nháy, escape |
| Expected ';', expected expression | Parsing | Kiểm tra trật tự token, dấu phân cách |
| Incompatible types, cannot find symbol | Semantic analysis | Kiểm tra kiểu, scope, import, khai báo |

**Thông báo lỗi không phải ranh giới tuyệt đối giữa các pha**: compiler thực có chiến lược phát hiện và phục hồi lỗi, một lỗi sớm có thể gây nhiều diagnostics tiếp theo. Khi gỡ lỗi, nên bắt đầu từ **lỗi đầu tiên có nguyên nhân rõ ràng** và xem lại mã nguồn đúng tại vị trí báo lỗi.

## 7. Vị trí nguồn, phục hồi lỗi và ích lợi cho IDE

Trong khi token stream của parser thường loại khoảng trắng/comment, compiler vẫn cần **source positions** (offset/dòng/cột) để báo lỗi chính xác. AST API có thể phối hợp với tiện ích như **Trees** và **SourcePositions** để truy ngược vị trí của một node về tệp nguồn. Với IDE, đó là nền tảng cho highlight, điều hướng đến khai báo, tìm tham chiếu và refactor.

Khi token thiếu hoặc không hợp lệ, parser thường **cố phục hồi lỗi** để tìm thêm vấn đề trong cùng lần biên dịch; một số AST node được sinh trong tình trạng chưa hoàn chỉnh hoặc đánh dấu lỗi. Do đó:

- “Có AST” không có nghĩa mã nguồn hợp lệ.
- AST của source lỗi không nên được phân tích như một cây hoàn chỉnh nếu công cụ không xử lý trạng thái lỗi.
- Một formatter muốn giữ nguyên comment/dấu cách cần thêm thông tin ngoài AST cấu trúc cơ bản.
- Khả năng nhận diện contextual keyword và cú pháp mới phụ thuộc **source level**; ví dụ mã Java 21 có thể không parse khi yêu cầu compiler dùng nguồn Java 17 nếu cú pháp chỉ có ở Java 21.

Trong các chương trình lớn, các pha còn có hoạt động thu thập symbol, phân giải type và sinh biểu diễn thấp hơn. Đừng coi lexer, parser và AST là toàn bộ quy trình compilation.

## 8. Những hiểu nhầm thường gặp

1. **“Dấu cách không có ý nghĩa trong Java.”** Khoảng trắng thường không thành token nhưng có thể tách hai lexeme: **int value** khác **intvalue**. Bên trong string literal, dấu cách còn là dữ liệu của literal.
2. **“Mỗi từ được ngăn bằng dấu cách là một token.”** Các toán tử như **>=**, **++** có thể là một token; chuỗi **"hello world"** có dấu cách nhưng là một literal token.
3. **“Lexer biết biểu thức nào phải nhân trước.”** Lexer chỉ nhận diện token **+**, **\***; parser áp dụng precedence/associativity để tạo cây.
4. **“AST giữ nguyên mã nguồn.”** AST mô tả cấu trúc; nó không bảo đảm giữ dấu cách, comment, lựa chọn ngoặc và mọi chi tiết định dạng.
5. **“Cứ tạo được AST thì Java hợp lệ.”** Còn phải phân giải tên, kiểm tra kiểu, khả năng truy cập, definite assignment và các ràng buộc khác.
6. **“Unicode escapes chỉ hoạt động bên trong string.”** Chúng được xử lý từ rất sớm trong dòng ký tự nguồn, kể cả những vùng nhìn giống comment hoặc keyword.
7. **“Token dài nhất luôn giải thích được mọi ngữ cảnh.”** JLS có ngoại lệ để xử lý contextual keywords và dấu **>** trong generic types.
8. **“Bất kỳ dấu giống khoảng trắng Unicode đều được lexer Java bỏ qua.”** JLS quy định các white-space input elements cụ thể; không thay bằng quy tắc của trình soạn thảo hoặc hàm kiểm tra khoảng trắng tổng quát.
9. **“Token và AST giống nhau vì đều là đối tượng compiler.”** Token là đơn vị từ vựng tuyến tính; AST là cây cấu trúc.
10. **“com.sun.tools.javac.* có thể dùng như API công khai lâu dài.”** Đây là nhóm implementation nội bộ; cần phân biệt với Java Compiler Tree API được cung cấp qua **com.sun.source.tree**.

## 9. Bài tập tự thực hành

**Bài 1 — Đếm và phân loại token.** Với câu:

~~~java
boolean ready = value >= 10 && value != 20;
~~~

Hãy tự đánh dấu **keyword**, **identifier**, **literal**, **operator** và **separator**. Chú ý **>=**, **&&**, **!=** mỗi cụm là một operator token, không phải các token rời.

**Bài 2 — Dựng AST bằng tay.** Vẽ hai cây cho:

~~~java
int a = 5 + 2 * 3;
int b = (5 + 2) * 3;
~~~

Sau đó chạy chương trình Java hợp lệ để xác nhận **a = 11**, **b = 21**. Hãy giải thích node phép toán nào nằm ở gốc của từng initializer.

**Bài 3 — Tìm giai đoạn gây lỗi.** Phân loại ba mảnh mã:

~~~java
String a = "missing;
int b = ;
int c = "ok";
~~~

Lần lượt xác định lỗi literal, lỗi grammar và lỗi kiểu. Những dòng này cố ý không hợp lệ; không ghép thành ví dụ chạy được.

**Bài 4 — Khám phá Tree API.** Đổi source string trong **InspectAst.java** thành:

~~~java
class Example { int answer = (2 + 3) * 4; }
~~~

Dự đoán **initializer.getKind()** trước khi chạy. Sau đó thử in các node con để thấy parser giữ ngoặc bằng cấu trúc **PARENTHESIZED**. Không ép cast initializer thành BinaryTree của phép cộng như ví dụ gốc nếu cấu trúc mới khác; hãy kiểm tra kind trước khi cast.

**Bài 5 — Kiểm tra ranh giới token.** Giải thích vì sao **a - -b** khác với **a--b** và vì sao **int number** khác **intnumber**, dù số ký tự thay đổi rất ít.

## 10. Tự kiểm tra kiến thức

- Vì sao compiler cần đọc encoding của tệp trước khi xử lý Unicode escapes?
- Ba bước dịch lexical input trong JLS diễn ra theo thứ tự nào?
- Khoảng trắng/comment có biến thành token tham gia grammar hay không? Khi nào whitespace lại ảnh hưởng ranh giới token?
- Vì sao dấu **+** trong **"2 + 3"** không trở thành một operator token?
- Quy tắc maximal munch giải thích điều gì trong **a--b**?
- Khi nào lỗi xuất hiện ở lexical analysis, parsing hoặc semantic analysis?
- Tại sao AST của **2 + 3 * 4** lại có phép cộng phía ngoài phép nhân?
- Vì sao công cụ format mã nguồn thường cần giữ thông tin bổ sung bên cạnh AST?
- **JavacTask.parse()** cho phép quan sát điều gì, và tại sao điều đó chưa đồng nghĩa với kiểm tra kiểu hoàn tất?

## 11. Nguồn tham khảo chuẩn

- **Java Language Specification (JLS) – Chapter 3, Lexical Structure:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html
- **JLS – Chapter 19, Syntax:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-19.html
- **Java SE 21 – Compiler Tree API (com.sun.source.tree):** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- **Java SE 21 – JavacTask:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- **Java SE 21 – javac tool:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Ghi nhớ:** Mã nguồn bắt đầu là các ký tự đã được giải mã; Java áp dụng những quy tắc chuyển dịch ký tự đặc thù, lexer nhận diện token, parser kết hợp chúng theo grammar thành AST. **Token trả lời “thành phần nào xuất hiện?”; AST trả lời “chúng tạo nên cấu trúc chương trình nào?”** Cả hai là cơ sở cho những bước kiểm tra ngữ nghĩa và sinh bytecode về sau.