# Ghi nhận khai báo và xây dựng bảng ký hiệu trong trình biên dịch Java

Khi đọc chương trình Java, trình biên dịch không thể chỉ thay từng tên trong mã nguồn bằng một địa chỉ hay một đoạn bytecode. Trước tiên, nó cần biết **những thực thể nào đã được khai báo**: package, class, interface, record, enum, trường, phương thức, constructor, tham số và biến cục bộ. Nó cũng cần lưu quan hệ sở hữu và phạm vi nhìn thấy của mỗi khai báo, để các bước sau xác định một tên như `count` hay `process` đang nói đến thực thể nào.

Trong kiến trúc compiler, công việc này thường được gọi là **ghi nhận khai báo (enter declarations)** và xây dựng **bảng ký hiệu (symbol table)**. Với `javac`, “Enter” là tên một nhóm thao tác nội bộ; mô tả chính xác về các lớp nội bộ có thể thay đổi theo JDK. Mục tiêu của bài là hiểu luồng xử lý và các quy tắc ngôn ngữ ổn định, biết phân biệt việc khai báo đã được ghi nhận với việc tham chiếu đã được phân giải và kiểm tra kiểu.

## 1. Từ mã nguồn tới môi trường chứa ký hiệu

Hãy xét:

```java
class Invoice {
    private int total;

    int add(int amount) {
        total += amount;
        return total;
    }
}
```

Parser trước tiên tạo cây cú pháp trừu tượng (AST) thể hiện một khai báo lớp `Invoice`, một trường `total`, một phương thức `add`, tham số `amount` và các biểu thức trong thân phương thức. Nhưng chỉ AST chưa đủ để quyết định `total` trong `total += amount` là trường nào hoặc liệu phép cộng có hợp lệ.

Compiler cần tạo/lưu thông tin khái niệm như sau:

| Ký hiệu | Loại khai báo | Chủ sở hữu | Thông tin thiết yếu |
| --- | --- | --- | --- |
| `Invoice` | Type/class | Package hiện tại | Tên, modifier, type, members |
| `total` | Field | `Invoice` | `private`, kiểu `int` |
| `add(int)` | Method | `Invoice` | Kiểu trả về `int`, tham số `int` |
| `amount` | Parameter | Phương thức `add` | Kiểu `int`, phạm vi thân phương thức |

Ví dụ chỉ minh họa những thuộc tính quan trọng; cách compiler tổ chức đối tượng, scope và thời điểm tạo chúng là chi tiết triển khai.

Một **symbol** là biểu diễn có cấu trúc của một thực thể được khai báo. Một **scope** là môi trường tra cứu các tên đang khả dụng trong một vùng mã. **Symbol table** là tên khái quát cho hệ thống lưu, phân loại và tra cứu những symbol đó qua nhiều scope; không nhất thiết là một bảng phẳng duy nhất cho toàn chương trình.

```text
Byte .java
   |
   v
Lexing / Parsing --> AST (cấu trúc cú pháp)
                         |
                         v
                 Enter / ghi nhận khai báo
                         |
                +--------+--------+
                |                 |
           Type symbol        Member symbols
           và môi trường      và scope của class
                |                 |
                +--------+--------+
                         |
                         v
             Attribution / phân giải tên,
             gán type và kiểm tra kiểu
                         |
                         v
             Kiểm tra flow, lower, generate
```

Đây là mô hình học tập, không phải lời khẳng định rằng mọi compiler/JDK luôn quét cây đúng một lượt tuyến tính. `javac` có cơ chế hoàn thiện ký hiệu theo yêu cầu (*lazy completion*), đọc thêm class/source từ classpath/module path và tương tác với annotation processing.

## 2. “Ghi nhận khai báo” khác “phân giải tham chiếu” như thế nào?

Hai thao tác liên quan nhưng khác trách nhiệm:

1. **Ghi nhận khai báo:** khi thấy `class Invoice`, đăng ký sự tồn tại của `Invoice` trong môi trường package; khi hoàn thiện khai báo lớp, đăng ký các field/method/constructor vào môi trường thành viên của lớp.
2. **Phân giải tên và kiểm tra kiểu:** khi gặp `invoice.add(5)`, tra cứu `invoice`, xác định kiểu của biến, tìm các phương thức `add` khả dụng, áp dụng quy tắc truy cập và overload, sau đó xác nhận đối số `5` hợp lệ.

Tham chiếu `invoice.add(5)` không phải là một khai báo mới. Nó cần được **gắn với symbol đã khai báo**, cùng thông tin kiểu của biểu thức tại vị trí đó.

Một khai báo có thể đã được ghi nhận mà chương trình vẫn không hợp lệ. Ví dụ:

```java
class Price {
    int value() {
        return "not an int";
    }
}
```

Compiler có thể ghi nhận symbol của lớp `Price` và phương thức `value(): int`, nhưng khi phân tích thân phương thức, phát hiện `String` không thể trả về nơi yêu cầu `int`. Không nên diễn giải việc “có symbol” là “đã vượt qua type checking”.

Tương tự, symbol cho một phương thức được ghi nhận trước khi mọi lời gọi phương thức ấy được kiểm tra overload và trước khi compiler tạo bytecode. Các bước có thể đan xen theo nhu cầu, nhưng đó là các trách nhiệm logic riêng biệt.

## 3. Các loại symbol và quan hệ sở hữu

Một hệ thống symbol phải trả lời ít nhất bốn câu: **tên gì, thuộc loại nào, nằm trong môi trường nào, có kiểu/chữ ký gì?**

### Package và kiểu

Tên đầy đủ `com.example.order.Invoice` giúp xác định một kiểu thuộc package `com.example.order`. Trong cùng package, nhiều compilation unit (`.java`) có thể đóng góp khai báo top-level. `javac` cần liên kết chúng khi xét các tham chiếu giữa file.

Ký hiệu kiểu bao gồm class, interface, enum, annotation interface và record; nested type có quan hệ sở hữu với kiểu bao ngoài. Một file có thể chứa nhiều khai báo top-level hợp lệ, nhưng quy tắc tên tệp đối với top-level `public` type vẫn phải được tuân thủ.

### Member của kiểu

Field, method, constructor và nested type nằm trong cấu trúc thành viên của kiểu. Phương thức có thể trùng **tên** nhờ overload; compiler phải phân biệt các phương thức theo chữ ký hợp lệ, chứ không dùng tên làm khóa duy nhất.

Ví dụ:

```java
class Formatter {
    String format(int number) {
        return Integer.toString(number);
    }

    String format(String text) {
        return text.strip();
    }
}
```

Hai phương thức `format` có cùng tên nhưng danh sách kiểu tham số khác nhau. Khi gặp `format(10)` hay `format(" abc ")`, bước giải quyết lời gọi sẽ lựa chọn overload thích hợp dựa vào quy tắc Java, không chỉ dựa vào việc trong bảng ký hiệu tồn tại một tên `format`.

### Tham số, biến cục bộ và type parameter

Tham số phương thức, biến trong block, biến vòng lặp, tham số lambda, pattern variable và type parameter có phạm vi cùng quy tắc khác nhau. Chúng không đơn giản được đăng ký vào scope thành viên của class. Trong `javac`, thông tin về local scope gắn với môi trường phân tích thân phương thức và các cấu trúc dùng lúc attribution/flow.

Ví dụ:

```java
class Box<T> {
    private T value;

    T get() {
        return value;
    }
}
```

`T` là type parameter của `Box`; `value` là field có kiểu `T`; `get` là method trả về `T`. Không nên hiểu `T` là một class đã tồn tại ở runtime hay một trường của `Box`: nó là một biến kiểu tại compile time, chịu các quy tắc generics và type erasure về sau.

## 4. Scope: tra cứu ký hiệu phụ thuộc vị trí trong mã

Phạm vi (*scope*) của khai báo là vùng mà tên có thể được dùng theo quy tắc Java, miễn là không bị che khuất bởi khai báo khác. Một tham chiếu có thể tìm đến scope gần nhất, rồi xét các thành viên, kiểu lồng nhau, kiểu trong package, import và những tên khả dụng theo ngữ cảnh. **Phạm vi, che khuất tên, khả năng truy cập và tính hợp lệ của một tham chiếu là các câu hỏi khác nhau.**

Ví dụ sau được phép:

```java
public class ScopeDemo {
    private static final int VALUE = 100;

    public static void main(String[] args) {
        int VALUE = 5;

        System.out.println(VALUE);
        System.out.println(ScopeDemo.VALUE);
    }
}
```

Biên dịch và chạy trong thư mục chứa `ScopeDemo.java`:

```bash
mkdir out
javac -encoding UTF-8 -d out ScopeDemo.java
java -cp out ScopeDemo
```

Stdout:

```text
5
100
```

Ở đây biến cục bộ `VALUE` che khuất tên đơn của field `VALUE` trong thân phương thức; `ScopeDemo.VALUE` truy cập field qua tên lớp. Compiler phải phân biệt **hai symbol khác nhau có cùng tên** theo ngữ cảnh tra cứu.

Ngược lại, chương trình sau **không hợp lệ**:

```java
class InvalidScope {
    void run() {
        int count = 1;
        {
            int count = 2; // lỗi: biến cục bộ trùng tên trong scope bao ngoài
        }
    }
}
```

Trong Java, block lồng nhau không được tự do khai báo lại một local variable đang nằm trong scope của block bao ngoài. Điều này khác với việc local variable che khuất field như ví dụ trước. Đừng dùng quy tắc “scope bên trong luôn được phép định nghĩa lại mọi tên” vốn có ở một số ngôn ngữ khác.

## 5. Ghi nhận khai báo giúp tham chiếu tới thành viên được viết ở phía sau

Một đặc điểm quan trọng của Java: một phương thức thường có thể được gọi ở dòng xuất hiện **trước** dòng khai báo phương thức ấy.

```java
public class ForwardMethodDemo {
    public static void main(String[] args) {
        System.out.println(greeting());
    }

    static String greeting() {
        return "registered";
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ForwardMethodDemo.java
java ForwardMethodDemo
```

Stdout:

```text
registered
```

Compiler không giải nghĩa chương trình theo kiểu “đọc dòng trên xuống và chỉ biết những gì đã xuất hiện ở phía trên”. Khai báo method được thu thập để các vị trí tham chiếu phù hợp có thể phân giải được, dù phần định nghĩa nằm sau lời gọi.

Nhưng **không được suy ra rằng mọi tham chiếu trước khai báo đều hợp lệ**. Theo JLS `8.3.3, một số tham chiếu bằng tên đơn đến field trong field initializer hoặc initializer block bị hạn chế:

```java
class InvalidForwardField {
    int first = second; // illegal forward reference
    int second = 10;
}
```

Dù compiler có thể biết rằng field `second` được khai báo, dạng tham chiếu đó vẫn không hợp lệ theo quy tắc ngôn ngữ. Nói cách khác, **“symbol đã tồn tại” không xóa bỏ những kiểm tra về thứ tự khởi tạo và ngữ cảnh sử dụng**.

Phương thức, local variable, field initializer, enum constant và static initialization có quy tắc riêng. Khi chẩn đoán, hãy tách lỗi “không tìm được symbol” khỏi lỗi “symbol tồn tại nhưng sử dụng sai ngữ cảnh”.

## 6. Ví dụ Java 17+ tổng hợp: lớp, thành viên, overload, scope và override

Lưu tệp `SymbolTableDemo.java` với nội dung đầy đủ sau:

```java
public class SymbolTableDemo {
    private static final int VALUE = 100;

    static class Greeter {
        static String message() {
            return "ready";
        }
    }

    static class Base {
        String label() {
            return "base";
        }
    }

    static class Derived extends Base {
        @Override
        String label() {
            return "derived";
        }
    }

    static int combine(int left, int right) {
        return left + right;
    }

    static String combine(String left, String right) {
        return left + right;
    }

    public static void main(String[] args) {
        int VALUE = 5;
        Base item = new Derived();

        System.out.println("field=" + SymbolTableDemo.VALUE);
        System.out.println("local=" + VALUE);
        System.out.println("nested=" + Greeter.message());
        System.out.println("overloadInt=" + combine(2, 3));
        System.out.println("overloadString=" + combine("a", "b"));
        System.out.println("dispatch=" + item.label());
    }
}
```

Chạy từ thư mục chứa file:

```bash
mkdir out
javac -encoding UTF-8 -d out SymbolTableDemo.java
java -cp out SymbolTableDemo
```

Stdout chính xác:

```text
field=100
local=5
nested=ready
overloadInt=5
overloadString=ab
dispatch=derived
```

Cách liên hệ với bảng ký hiệu:

| Biểu thức | Compiler cần xử lý |
| --- | --- |
| `SymbolTableDemo.VALUE` | Tra cứu class `SymbolTableDemo` và field static `VALUE` |
| `VALUE` trong `main` | Tra cứu biến cục bộ `VALUE` trong scope gần nhất |
| `Greeter.message()` | Tra cứu nested type `Greeter` và static method `message` |
| `combine(2, 3)` | Tập phương thức tên `combine`; chọn overload nhận `int, int` |
| `combine("a", "b")` | Chọn overload nhận `String, String` |
| `Base item = new Derived()` | Kiểm tra quan hệ subtype và phép gán hợp lệ |
| `item.label()` | Khi biên dịch, kiểm tra member theo kiểu tĩnh `Base`; khi chạy, dispatch tới override của `Derived` |

Dòng cuối cần đặc biệt lưu ý: **symbol resolution ở compile time không đồng nghĩa lựa chọn implementation tại runtime**. Compiler xác nhận lời gọi `label()` có chữ ký hợp lệ thông qua kiểu tĩnh; máy ảo Java có thể chọn implementation ghi đè dựa trên kiểu đối tượng thực tế.

Sau biên dịch, ngoài `SymbolTableDemo.class` còn có class file cho các nested class, thường đặt tên theo dạng `SymbolTableDemo$Greeter.class`, `SymbolTableDemo$Base.class` và `SymbolTableDemo$Derived.class`. Tên/định dạng class file là một tầng khác với bảng symbol nội bộ của compiler.

## 7. Bên trong \`javac\`: Enter và hoàn thiện khai báo

Các tên sau giúp người học định vị trách nhiệm trong mã nguồn OpenJDK; **đây là API nội bộ của `jdk.compiler`**, không phải giao diện ổn định để ứng dụng phụ thuộc trực tiếp:

| Khái niệm/đơn vị trong `javac` | Chức năng khái quát |
| --- | --- |
| `JCTree`, `JCCompilationUnit`, `JCClassDecl` | Các nút của AST cho compilation unit và khai báo |
| `Enter` | Đăng ký các class symbol và môi trường liên quan |
| `TypeEnter` | Hoàn thiện thông tin kiểu, quan hệ kế thừa, type parameter và thành viên khi cần |
| `Symbol` và các dạng class/method/variable symbol | Biểu diễn định danh, chủ sở hữu, kiểu, modifier cùng metadata |
| `Scope` | Hỗ trợ tập hợp và tra cứu ký hiệu trong môi trường |
| `Attr`, `Resolve` | Phân giải tên/ngữ nghĩa, gán kiểu cho biểu thức, kiểm tra lời gọi và khả năng truy cập |
| `Flow` | Phân tích các ràng buộc luồng điều khiển như definite assignment và reachability |

Đừng đồng nhất tên class nội bộ với **một bước bắt buộc duy nhất** trong Java Language Specification. JLS quy định kết quả ngữ nghĩa cần tuân thủ; `javac` là một triển khai có kiến trúc cụ thể.

Trong thiết kế `javac` hiện đại, có thể hiểu *enter* theo hai lớp trách nhiệm:

**Lớp 1 — tạo biểu diễn cho class.** Khi quét compilation unit, compiler thiết lập class symbol, gắn nó vào môi trường bao quanh, nhận biết các class lồng nhau và lưu môi trường để tiếp tục xử lý.

**Lớp 2 — hoàn thiện thông tin class.** Khi cần dùng thành viên hay kiểu của class, compiler hoàn thiện type parameter, supertype, interface, field/method/constructor và các thông tin liên quan. Một phần công việc có thể được **trì hoãn** cho đến khi cần (*on-demand completion*). Vì vậy không nên áp đặt rằng compiler luôn ghi xong 100% mọi field và method của mọi class theo thứ tự file rồi mới tiến hành type checking.

Đặc điểm này giúp giải thích vì sao compiler có thể phát hiện kiểu từ source hoặc class file liên quan, có thể phân tích class A trước khi hoàn thiện class B, và vẫn cho phép tham chiếu hợp lệ giữa các khai báo.

Những bản `javac` cũ dùng tên `MemberEnter` cho nhiều trách nhiệm mà các phiên bản mới đặt trong `TypeEnter`; sơ đồ và bài viết về internals cần được đối chiếu đúng phiên bản JDK. Không viết mã ứng dụng trực tiếp vào `com.sun.tools.javac.*` nếu không thực sự xây dựng công cụ phụ thuộc compiler và chấp nhận việc API nội bộ thay đổi.

## 8. Từ AST sang symbol, rồi mới tới type: đọc đúng lỗi biên dịch

Hãy xét ba tình huống riêng biệt.

### Tên không tồn tại trong scope

```java
class MissingName {
    void run() {
        System.out.println(unknownValue);
    }
}
```

Compiler không tìm thấy symbol hợp lệ cho `unknownValue`. Thông báo điển hình có dạng `cannot find symbol` và chỉ ra variable `unknownValue`. Hãy kiểm tra khai báo, lỗi gõ tên, import, package, classpath, module visibility và phạm vi.

### Có tên nhưng dùng sai kiểu

```java
class WrongType {
    int count = 3;

    void run() {
        count = "three";
    }
}
```

Symbol `count` có tồn tại; vấn đề là `String` không gán được cho `int`. Đây là lỗi kiểm tra kiểu, thường được thông báo dưới dạng `incompatible types`. Tìm thêm import hoặc khai báo field khác sẽ không giải quyết đúng nguyên nhân.

### Có nhiều khai báo cùng chữ ký không hợp lệ

```java
class DuplicateMethod {
    void save(int value) { }

    void save(int number) { } // lỗi: trùng chữ ký save(int)
}
```

Tên tham số `value` hay `number` không làm hai phương thức thành overload khác nhau. Trình biên dịch phải kiểm tra tính hợp lệ/duy nhất của khai báo dựa trên chữ ký Java. Trường hợp này khác với ví dụ `combine(int, int)` và `combine(String, String)` ở trên.

Ba đoạn trong mục 8 **cố tình không biên dịch**, dùng để nhận biết các kiểu lỗi; không ghép chúng với chương trình chạy ở mục 6.

## 9. Import, package và classpath có tác động tới việc xây dựng môi trường tên

Một lỗi `cannot find symbol` không nhất thiết nghĩa là parser không đọc được khai báo. Ví dụ:

```java
package demo.app;

import demo.model.Invoice;

public class App {
    Invoice current;
}
```

Compiler phải tìm được `demo.model.Invoice` trong source được biên dịch cùng lúc, source path hoặc class/module path hợp lệ. Nếu class không có mặt, import không tạo ra thực thể ấy. **Import là một cơ chế mang tên khai báo đã tồn tại vào phạm vi tra cứu**, không phải lệnh “tải thêm thư viện từ Internet” hay lệnh biên dịch tự động mọi file cùng tên.

Các điểm cần phân biệt:

- `package demo.app;` xác định không gian tên của compilation unit, không tạo ra folder vật lý hộ mã. Đường dẫn file trong quy trình build thông thường cần phù hợp package.
- `import demo.model.Invoice;` giúp dùng tên đơn `Invoice` theo quy tắc import; không thay thế việc cung cấp source/class tương ứng.
- Hai kiểu có cùng tên đơn nhưng khác package vẫn là hai ký hiệu khác nhau, ví dụ `java.util.Date` và `java.sql.Date`. Import không giải quyết mọi xung đột tự động; đôi khi phải dùng tên đầy đủ.
- `-classpath`/`--class-path`, `-sourcepath`/`--source-path` và các tùy chọn module path chi phối những định nghĩa compiler có thể tìm được. Việc tìm thêm một source để lấy khai báo cũng có thể liên quan biên dịch ngầm.
- Accessibility theo `public`, `protected`, package access và `private` được kiểm tra theo ngữ cảnh; **tìm thấy symbol** chưa chắc có quyền sử dụng nó.

Khi build nhiều module JPMS, khả năng *readability* và export package còn ảnh hưởng tới tính nhìn thấy của kiểu. Đừng áp một sơ đồ scope chỉ dành cho project classpath lên mọi module mà bỏ qua ranh giới module.

## 10. Symbol table khác constant pool, local variable table và reflection

Các tên gọi “bảng” trong hệ sinh thái Java dễ bị nhầm:

| Khái niệm | Thời điểm/phạm vi | Ý nghĩa |
| --- | --- | --- |
| Bảng ký hiệu compiler | Khi phân tích và biên dịch source/class | Lưu thực thể khai báo, scope, type và quan hệ cần cho phân giải |
| Constant pool của class file | Trong bytecode `.class` | Lưu hằng, tên và tham chiếu biểu tượng theo định dạng JVM class file |
| LocalVariableTable attribute | Thông tin debug *tùy chọn* trong `.class` | Có thể mô tả tên/slot/vùng sống của local variable khi có debug info |
| Reflection | Runtime | Quan sát phần thông tin về class/member mà JVM cung cấp qua API |
| Bảng symbol của debugger/IDE | Tùy công cụ | Có thể xây mô hình tên riêng phục vụ tìm kiếm, refactor, breakpoint |

Không có quy tắc “compiler copy nguyên bảng ký hiệu vào class file”. Nhiều cấu trúc compile time bị loại bỏ hoặc chuyển đổi khi sinh bytecode. Ví dụ tên biến cục bộ có thể không có trong class file nếu không phát sinh debug attributes phù hợp; type parameter chịu những giới hạn của erasure và metadata signature.

Lệnh:

```bash
javap -p SymbolTableDemo
```

cho phép xem thông tin class/member từ class file đã biên dịch (với `-p`, bao gồm member không public). Đây là **cửa sổ quan sát artifact**, không phải cách in toàn bộ symbol table đang tồn tại bên trong `javac` trong giai đoạn Enter.

## 11. Công cụ công khai để quan sát khai báo và symbol

Nếu xây dựng annotation processor hoặc công cụ phân tích mã nguồn, nên ưu tiên những API được JDK hỗ trợ:

- `javax.lang.model.element.Element` cùng `TypeElement`, `ExecutableElement`, `VariableElement` để xem khai báo và quan hệ thành viên;
- `javax.lang.model.type.TypeMirror` để biểu diễn kiểu ở mức mô hình ngôn ngữ;
- `javax.lang.model.util.Elements` và `Types` để tìm kiểu, so sánh kiểu, tìm member;
- `javax.annotation.processing.AbstractProcessor` và `RoundEnvironment` để xử lý khai báo được compiler cung cấp ở các vòng annotation processing;
- `com.sun.source.tree.*` và `com.sun.source.util.Trees`/`TreePath` để liên hệ một vị trí trong AST với `Element` tương ứng, khi dùng compiler/tree APIs hỗ trợ.

Ví dụ mã **minh họa nằm bên trong một annotation processor**, không phải tệp Java độc lập:

```java
TypeElement type = processingEnv.getElementUtils()
        .getTypeElement("demo.model.Invoice");

if (type != null) {
    for (Element member : type.getEnclosedElements()) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.NOTE,
                member.getKind() + " " + member.getSimpleName()
        );
    }
}
```

Để sử dụng thật, cần khai báo processor, import các lớp `javax.lang.model.element.*` và `javax.tools.Diagnostic`, cấu hình processor path/annotation processing của build, và đảm bảo kiểu `demo.model.Invoice` xuất hiện trong môi trường biên dịch. Không phải mọi tên compiler có thể phân giải đều được hiển thị ở mọi thời điểm/round; `getTypeElement` có thể trả `null`.

Gọi `getEnclosedElements()` giúp quan sát các thành viên khai báo liên quan tới kiểu; đó không phải snapshot của mọi local variable trong từng thân phương thức, cũng không phải bản sao của `com.sun.tools.javac.code.Scope`.

## 12. Những lỗi hiểu sai thường gặp

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “Parser biết có tên `x` nên lời gọi chắc hợp lệ” | AST lưu cú pháp; phân giải tên, quyền truy cập và kiểm tra kiểu còn phải chạy |
| “Symbol table là một `Map<String, Object>` duy nhất” | Compiler cần nhiều môi trường/scope, loại symbol, overload, owner và type |
| “Có thể khai báo lại mọi local variable trong block con” | Java hạn chế redeclaration khi local cùng tên vẫn nằm trong scope bao ngoài |
| “Đã ghi nhận field nên dùng trước khai báo ở mọi nơi đều hợp lệ” | JLS có hạn chế riêng về forward field reference trong initializer |
| “Method tên giống nhau luôn bị trùng” | Overload hợp lệ nếu khác chữ ký theo quy tắc Java |
| “Compiler chọn override tại build time” | Compiler phân giải lời gọi/type; runtime dispatch có thể chọn implementation override |
| “Import sinh ra class còn thiếu” | Import chỉ điều chỉnh phạm vi tra cứu; class/source vẫn phải có trong build |
| “`javap` in bảng symbol của `javac`” | `javap` đọc class file sau khi compile, không truy cập đầy đủ trạng thái compiler |
| “Enter luôn chạy xong mọi member trước mọi bước khác” | Hoàn thiện kiểu/thành viên có thể theo yêu cầu và đan xen với các hoạt động compiler |
| “`com.sun.tools.javac.*` là API ứng dụng ổn định” | Đây là nội bộ triển khai; ưu tiên `javax.lang.model`, `javax.tools` và `com.sun.source` khi phù hợp |

## 13. Quy trình chẩn đoán thực tế

Khi lỗi biên dịch liên quan tên, khai báo hoặc symbol, có thể đi theo thứ tự:

1. **Xác định loại lỗi:** parser báo sai cú pháp, `cannot find symbol`, ambiguous reference, duplicate declaration, illegal forward reference, incompatible types hay access error? Mỗi nhóm gợi ý một tầng khác.
2. **Tìm khai báo gốc:** tên đầy đủ là gì, symbol thuộc package/class/block nào, có thật sự được đưa vào compilation unit hay classpath/module path?
3. **Kiểm tra scope tại vị trí sử dụng:** local/parameter có che field không; import có xung đột không; static context có đang gọi member instance không?
4. **Kiểm tra chữ ký và kiểu:** overload nào áp dụng, generic type parameter và inference ra sao, có conversion hay access restriction nào?
5. **Kiểm tra quy tắc đặc biệt:** forward reference, definite assignment, inheritance/override, duplicate methods và visibility theo module.
6. **Tái hiện bằng compiler/JDK đúng dự án:** chạy `javac` với nguồn và đường dẫn tường minh; không dùng lớp còn sót trong output cũ làm bằng chứng.
7. **Phân biệt compile-time với runtime:** bytecode, reflection hoặc lỗi runtime là hậu quả ở giai đoạn khác, không đủ để suy ra chính xác các thao tác Enter nội bộ.

Chẳng hạn lỗi `cannot find symbol: variable count` trong một lambda có thể xuất phát từ việc tên nằm ngoài scope; lỗi `variable count might not have been initialized` cho thấy compiler đã biết biến `count` nhưng phân tích definite assignment chưa thỏa. Hai lỗi cần hai cách sửa khác nhau.

## 14. Bài tập tự kiểm tra

**Bài A — dự đoán output.** Ở `ScopeDemo`, biến nào được in bởi `System.out.println(VALUE)`, biến nào được in bởi `System.out.println(ScopeDemo.VALUE)`? Đáp án lần lượt là local `5` và static field `100`; chúng có cùng tên nhưng thuộc scope/owner khác.

**Bài B — phân biệt “không tồn tại” với “sai kiểu”.** Thử biên dịch hai chương trình `MissingName` và `WrongType` (trong mục 8, mỗi lần một file riêng). Một lỗi do không phân giải được tên, lỗi còn lại do symbol có kiểu không phù hợp. Ghi lại thông báo thực tế từ phiên bản `javac` bạn chạy.

**Bài C — thứ tự khai báo.** Đổi vị trí `greeting()` và `main()` trong `ForwardMethodDemo`: chương trình vẫn biên dịch/chạy. Thử ví dụ `InvalidForwardField`: lỗi xảy ra dù field `second` tồn tại về mặt khai báo. Giải thích bằng sự khác nhau giữa phạm vi và quy tắc forward reference.

**Bài D — overload và override.** Trong `SymbolTableDemo`, dự đoán `combine("a","b")` chọn member nào và `item.label()` chạy implementation nào. Đáp án: overload `combine(String,String)` được chọn khi compile; `Derived.label()` chạy nhờ dynamic dispatch. Đây là hai quyết định xảy ra ở hai thời điểm.

## 15. Tổng kết và tài liệu chuẩn

Ghi nhận khai báo giúp compiler xây dựng mô hình về **thực thể, kiểu, chữ ký, owner và scope**. Mô hình này là nền tảng để phân giải các lần sử dụng tên, kiểm tra overload, quyền truy cập, quan hệ kế thừa và tính hợp lệ của chương trình. Trong `javac`, class symbols được ghi nhận và nội dung kiểu có thể được hoàn thiện theo yêu cầu; các bước attribution, kiểm tra flow và sinh mã tiếp tục sử dụng kết quả ấy.

Khi đọc hoặc debug compiler, hãy luôn tách ba câu: **“đã thấy khai báo chưa?”, “tham chiếu này nối với khai báo nào và có hợp lệ không?”, “đã sinh class file gì?”** Trả lời chúng theo thứ tự sẽ giúp xác định đúng nơi phát sinh lỗi.

Tài liệu đào sâu:

- [Java Language Specification, Chapter 6 — Names](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html): scope, shadowing, name resolution, access control.
- [Java Language Specification, `8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.3): quy tắc forward field reference.
- [OpenJDK `Enter.java`](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/classes/com/sun/tools/javac/comp/Enter.java): mã nguồn tham khảo triển khai hiện hành; đối chiếu tag JDK đang dùng vì nội bộ có thể đổi.
- [`javax.lang.model.element` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/package-summary.html): mô hình khai báo công khai cho tooling/annotation processing.
