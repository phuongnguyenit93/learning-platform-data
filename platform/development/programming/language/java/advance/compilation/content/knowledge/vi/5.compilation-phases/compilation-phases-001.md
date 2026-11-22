# Toàn cảnh các giai đoạn xử lý trong javac

`javac` là trình biên dịch Java từ **mã nguồn** (`.java`) sang **class file** (`.class`) chứa bytecode và metadata mà JVM có thể nạp. Giữa hai đầu vào/đầu ra đó, compiler phải hiểu cú pháp, biết mỗi tên chỉ tới khai báo nào, kiểm tra kiểu và quy tắc ngôn ngữ, xử lý annotation (nếu được cấu hình), chuyển các cấu trúc cấp cao về biểu diễn phù hợp với JVM rồi sinh class file.

Hiểu các giai đoạn giúp trả lời những câu hỏi thực tế: tại sao thiếu dấu ngoặc khác với `cannot find symbol`, tại sao mã Java hợp cú pháp nhưng bị từ chối vì kiểu, một annotation processor có thể tạo thêm mã nguồn như thế nào, và vì sao Java đã biên dịch thành công vẫn có thể lỗi khi chạy.

Bài dùng Java 17+ làm chuẩn ví dụ. Tên các giai đoạn như `Parse`, `Enter`, `Attr`, `Flow`, `Lower` và `Gen` mô tả các công việc quen thuộc của OpenJDK `javac`. **Không nên hiểu đó là một API ổn định quy định compiler phải chạy một chuỗi thao tác tuyến tính duy nhất cho mọi tệp.** Công việc có thể xảy ra theo từng compilation unit, từng kiểu, từng lượt annotation processing và có thể đan xen theo quan hệ phụ thuộc.

## 1. Bản đồ tổng thể

~~~text
Tệp .java + option của javac
           │
           ▼
Đọc nguồn, nhận diện token (lexing)
           │
           ▼
Parse: xây cây cú pháp (AST)
           │
           ▼
Enter: ghi nhận package, kiểu, khai báo và symbol
           │
           ├─────────► Annotation processing (nếu được bật)
           │                   │
           │                   └── nguồn sinh thêm → parse/enter, round tiếp theo
           │
           ▼
Analyze: phân giải tên, kiểm tra kiểu, ngữ nghĩa, luồng điều khiển
           │
           ▼
Transform / Lower: hạ cấu trúc Java xuống dạng cho class file
           │
           ▼
Generate: sinh bytecode và metadata
           │
           ▼
Tệp .class ──► JVM nạp, liên kết và thực thi khi chạy ứng dụng
~~~

Sơ đồ giúp định hướng, nhưng có ba điểm dễ hiểu sai:

1. **Parse thành công không đồng nghĩa chương trình hợp lệ.** Một biểu thức có thể đúng ngữ pháp nhưng sai kiểu; một tên lớp có thể viết đúng nhưng không nằm trên classpath.
2. **Annotation processing là một nhánh có nhiều round.** Processor có thể sinh mã nguồn mới; compiler phải tiếp tục xử lý phần nguồn mới trước khi kết thúc compilation. Không phải mọi lần gọi `javac` đều có annotation processing.
3. **JVM không phải giai đoạn cuối bên trong `javac`.** `javac` tạo class file; class loading, verification, linking, initialization, JIT và thực thi là các cơ chế của runtime, xảy ra sau này nếu chạy chương trình.

Có thể chia thành ba lớp tư duy: **syntax** (mã viết có đúng cấu trúc Java không), **semantics** (mã có ý nghĩa và hợp lệ theo luật Java không), **output** (mã hợp lệ được biểu diễn bằng class file như thế nào).

## 2. Đầu vào và môi trường biên dịch

Một lời gọi tối giản:

~~~bash
javac -encoding UTF-8 --release 17 -d out Hello.java
~~~

Compiler cần nhiều thứ ngoài nội dung `Hello.java`:

| Đầu vào | Vai trò |
| --- | --- |
| Tệp `.java` | Chứa package, import, kiểu, phương thức và biểu thức cần biên dịch |
| `--release 17` | Chọn mức ngôn ngữ, API nền tảng và dạng bytecode tương ứng Java 17 |
| `-encoding UTF-8` | Chỉ định encoding để đọc tệp nguồn |
| `-d out` | Chọn thư mục xuất các tệp `.class` |
| `-cp` / `--class-path` | Cung cấp các lớp và thư viện không nằm trong Java platform modules hoặc source hiện tại |
| `--module-path` | Cung cấp module dependencies cho dự án dùng JPMS |
| `--source-path` | Hỗ trợ tìm nguồn phụ thuộc khi không liệt kê trực tiếp tất cả tệp |
| Cấu hình annotation processor | Điều khiển có chạy processor hay không và nạp processor từ đâu |

`javac` có thể đọc nhiều tệp nguồn cùng lượt:

~~~bash
javac -encoding UTF-8 --release 17 -d out App.java Helper.java
~~~

Một invocation có thể xử lý liên quan giữa các kiểu trong nhiều tệp; không nhất thiết biên dịch xong hoàn toàn `App.java` rồi mới bắt đầu `Helper.java`. Classpath không có nghĩa là compiler tự động biên dịch mọi tệp `.java` bên trong thư viện.

Cần phân biệt **lựa chọn ngôn ngữ/target** với **phiên bản JDK chạy compiler**. Ví dụ, `--release 17` trên JDK mới hơn nhằm biên dịch với ràng buộc Java 17; nếu dùng cú pháp/API mới hơn 17, lỗi có thể xuất hiện ngay ở parse hoặc analyze. Việc chọn `-source 17 -target 17` riêng lẻ không cung cấp đầy đủ bảo đảm về API Java 17 như `--release 17`.

## 3. Giai đoạn đọc ký tự, token và parse

Trước khi hiểu ý nghĩa chương trình, compiler đọc ký tự nguồn và chia thành các **token**: keyword, identifier, literal, toán tử, dấu phân cách và những thành phần cú pháp khác. Quá trình lexical analysis cũng xử lý các quy tắc đặc thù của ngôn ngữ, bao gồm cách diễn giải Unicode escape theo Java Language Specification; đừng coi Java lexer giống bộ tách từ đơn giản trên một tệp văn bản.

Ví dụ hợp cú pháp:

~~~java
class Example {
    int total = 10 + 20;
}
~~~

Có thể hình dung các token tiêu biểu: `class`, `Example`, `{`, `int`, `total`, `=`, `10`, `+`, `20`, `;` và `}`. Đoạn này chưa nói `total` có thể truy cập ở đâu hoặc `Example` có được dùng hợp lệ trong mã khác không; đó là ngữ nghĩa.

**Parsing** đọc chuỗi token theo grammar Java và xây dựng **abstract syntax tree (AST)**. AST mô tả cấu trúc chương trình: compilation unit, class declaration, variable declaration, binary expression, method invocation... Nó loại bỏ nhiều chi tiết bề mặt không cần cho phân tích ngữ nghĩa, nhưng giữ vị trí nguồn để báo lỗi.

Ví dụ lỗi cú pháp — tệp `BrokenSyntax.java`:

~~~java
class BrokenSyntax {
    void print() {
        System.out.println("Hello")
    }
}
~~~

Thiếu dấu `;` sau lời gọi phương thức. `javac BrokenSyntax.java` sẽ báo lỗi cú pháp tại vị trí liên quan (thông điệp/địa điểm chính xác có thể khác theo JDK). Compiler có thể cố phục hồi để báo thêm lỗi, nhưng không thể coi AST chứa lỗi là chương trình hợp lệ để sinh class file.

**Đừng gán nhầm lỗi:** nếu viết `int n = "text";`, token và cấu trúc câu lệnh hoàn toàn hợp lệ; lỗi chỉ xuất hiện khi kiểm tra kiểu.

## 4. Enter: ghi nhận khai báo và symbol

Sau khi đã có cấu trúc cú pháp, compiler cần biết chương trình **khai báo những gì**. Nhóm công việc thường gọi `Enter` (và các bước hoàn thiện liên quan) đăng ký package, class, interface, thành viên và các **symbol** vào cấu trúc dữ liệu compiler.

Symbol đại diện cho một thực thể ngữ nghĩa như kiểu, biến, phương thức, package hoặc module. Tên văn bản giống nhau không có nghĩa là cùng một symbol: `List` có thể là `java.util.List` hoặc một kiểu khác tùy import và ngữ cảnh; `value` trong hai scope khác nhau có thể là hai biến khác nhau.

Ví dụ:

~~~java
class Account {
    int balance;

    int add(int amount) {
        return balance + amount;
    }
}
~~~

Compiler phải nhận biết `Account` là một kiểu, `balance` là field, `amount` là parameter và `add(int)` là một method declaration. Nhờ bảng khai báo, compiler có thể phân tích các tham chiếu đến thành viên mà không phụ thuộc vào thứ tự đặt method trong thân class.

Giai đoạn ghi nhận khai báo chưa chứng minh mọi biểu thức trong thân method đúng kiểu hay luồng điều khiển hợp lệ. Trong một compiler thực tế, việc enter các khai báo và hoàn thiện symbol có nhiều bước; “Enter” là cách gọi khái quát, không phải toàn bộ ngữ nghĩa được giải quyết cùng một thời điểm.

### Package, import, classpath và module

Khi phân giải kiểu, compiler cần truy được declaration từ source hiện tại, source path, classpath, module path và Java platform APIs đúng cấu hình. Có khai báo `import java.util.List;` không có nghĩa là `List` đã được nạp hoặc toàn bộ thư viện được chép vào chương trình; import giúp tên ngắn được hiểu theo phạm vi hợp lệ.

Với named modules, compiler còn xét `requires`, `exports` và khả năng truy cập giữa module. Một package nằm trong module hiện diện trên module path vẫn có thể **không đọc được hoặc không được export** tới module đang biên dịch.

## 5. Analyze: phân giải tên, kiểm tra kiểu và luật ngữ nghĩa

Sau cú pháp và nhận diện khai báo, compiler thực hiện các kiểm tra cần thiết để quyết định mã có hợp lệ theo Java Language Specification hay không. Trong OpenJDK `javac`, nhóm này liên quan các bước như attribution (thường gọi `Attr`), kiểm tra tính hợp lệ của khai báo, suy luận kiểu và flow analysis.

**Phân giải tên và overload:** với `Math.max(3, 4)`, compiler phải xác định `Math` là kiểu nào và chọn overload phù hợp từ các chữ ký phương thức khả dụng. Quy tắc overload resolution phụ thuộc loại đối số, chuyển đổi kiểu, boxing, varargs, generic và thứ tự ưu tiên theo JLS.

**Kiểm tra kiểu:** ví dụ:

~~~java
class WrongType {
    void demo() {
        int age = "twenty";
    }
}
~~~

Parser chấp nhận cấu trúc của khai báo; semantic analysis phát hiện `String` không gán được cho `int`. Thông báo kiểu như `incompatible types` thuộc nhóm lỗi ngữ nghĩa, không phải lỗi lexer.

**Kiểm tra khả năng truy cập:** một method `private` chỉ có thể được dùng ở các vị trí được luật truy cập của Java cho phép. Compiler còn kiểm tra kế thừa, ghi đè, checked exceptions, generic bounds và nhiều ràng buộc khác.

**Suy luận kiểu:** cú pháp `var` và lambda không có nghĩa là “không kiểm tra kiểu”. Java vẫn là ngôn ngữ kiểm tra kiểu tĩnh; compiler suy ra kiểu dựa trên initializer hoặc target type ở các ngữ cảnh hợp lệ. Ví dụ:

~~~java
import java.util.function.Function;

class Inference {
    static void example() {
        var message = "ready";             // String
        Function<Integer, Integer> twice = x -> x * 2;
    }
}
~~~

Đoạn mã trên hợp lệ với Java 17; nhận xét `String` và `Function<Integer, Integer>` mô tả kết quả phân tích kiểu, không phải kiểu được xác định lúc chạy bằng cách nhìn vào giá trị.

### Flow analysis: trạng thái biến và đường điều khiển

Trình biên dịch còn xét những đường điều khiển có thể đi tới một điểm sử dụng biến hoặc câu lệnh. Hai trường hợp quen thuộc là **definite assignment** và **reachability**.

~~~java
class WrongFlow {
    void demo(boolean flag) {
        int result;
        if (flag) {
            result = 10;
        }
        System.out.println(result);
    }
}
~~~

Lỗi vì `result` chưa chắc đã được gán nếu `flag` bằng `false`. Compiler không cần chạy chương trình để nhận biết đường đi đó.

Một ví dụ khác:

~~~java
class Unreachable {
    void demo() {
        return;
        // System.out.println("never"); // Nếu bỏ dấu //, đây là statement không thể tới
    }
}
~~~

Các luật này đều thuộc **kiểm tra thời điểm biên dịch**; khác với chuyện lúc chạy chương trình thực tế có đi qua một nhánh nào đó hay không. Đừng hiểu “flow analysis” là compiler luôn chứng minh được mọi tính chất của chương trình: nó thực hiện những kiểm tra được Java quy định, không thể loại trừ mọi bug logic hoặc mọi exception runtime.

## 6. Annotation processing: nhánh mở rộng có nhiều round

Annotation processing theo `javax.annotation.processing` (JSR 269) cho phép processor **đọc mô hình khai báo và annotation**, đưa ra diagnostics, và sinh thêm source/class/resource qua API như `Filer`. Nó thường được dùng để sinh mã từ annotation, metadata hoặc adapter, nhưng **không có nghĩa mọi annotation đều có processor**.

Quy trình về mặt ý niệm:

~~~text
Nguồn ban đầu được nhận diện
          │
          ▼
Round 1: processor xem element và annotation phù hợp
          │
          ├── Có nguồn mới được sinh? ──► Round 2
          │                                 │
          │                                 └── Có nguồn mới? → round tiếp
          ▼
Round cuối: processingOver() = true
          │
          ▼
Biên dịch nguồn ban đầu + nguồn sinh thêm (nếu cấu hình cho phép)
~~~

Processor được gọi theo nhiều round khi có nguồn mới; ở round cuối, chúng có cơ hội hoàn tất nhưng không được giả định sẽ được phép tiếp tục tạo nguồn cho round mới. Không được viết processor theo cách phụ thuộc vào số lượng round cụ thể cho mọi dự án. Các tệp nguồn sinh thêm cần khai báo hợp lệ và được đưa qua những kiểm tra compiler cần thiết trước khi tạo class file.

### Lựa chọn chế độ processing

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-proc:none` | Không chạy annotation processing; vẫn biên dịch mã nguồn |
| `-proc:only` | Chạy annotation processing và không tiếp tục biên dịch bytecode thông thường |
| `-proc:full` | Yêu cầu cả annotation processing và biên dịch (trên bản JDK hỗ trợ) |
| `-processor p.MyProcessor` | Chỉ định processor cần chạy |
| `--processor-path path` | Chọn nơi tìm processor trên classpath kiểu processor |
| `-s generated` | Chọn thư mục ghi các tệp nguồn sinh bởi annotation processor |
| `-XprintRounds` | Hiển thị thông tin về các round xử lý |
| `-XprintProcessorInfo` | Hiển thị processor được yêu cầu xử lý annotation nào |

**Khác biệt phiên bản:** JDK 23 thay đổi chính sách annotation processing ngầm định so với các bản cũ; cần **cấu hình processing rõ ràng** khi build phụ thuộc vào code generation, thay vì tin rằng một processor tự động được phát hiện trên classpath ở mọi JDK. `-proc:full` đã được hỗ trợ ở các bản cập nhật JDK 17 phù hợp, nhưng nếu cần tương thích với một bản 17 rất cũ, hãy kiểm tra `javac -help` của đúng JDK đó.

`-XprintRounds` chỉ có thông tin hữu ích khi annotation processing thực sự chạy. Dùng option này một mình trong lệnh không có processor không đảm bảo thấy các round. `-proc:only` cũng không đảm bảo có file `.class` sau lệnh.

Annotation processor tiêu chuẩn thao tác với mô hình phần tử và các file được tạo; không nên đồng nhất nó với plugin sửa AST nội bộ, compiler plugin hoặc thao tác trực tiếp lên bytecode. Nếu công cụ dựa vào API nội bộ của `javac`, khả năng tương thích JDK phải được đánh giá riêng.

## 7. Hạ cấu trúc ngôn ngữ: từ Java cấp cao tới JVM

Java cho phép viết nhiều cấu trúc tiện dụng không được biểu diễn nguyên xi bằng một instruction JVM tương ứng. Sau khi kiểm tra ngữ nghĩa, compiler thực hiện **desugaring / lowering** để biểu diễn các cấu trúc đó trong hình thức phù hợp để tạo bytecode và metadata.

Các ví dụ khái niệm:

| Cấu trúc nguồn | Điều cần được biểu diễn sau biên dịch |
| --- | --- |
| Generic `List<String>` | Quy tắc **type erasure** trong descriptors/bytecode, kèm metadata như generic signature khi cần |
| Enhanced `for` | Vòng lặp tương đương thích hợp cho array hoặc `Iterable` / `Iterator` |
| Autoboxing/unboxing | Chuyển đổi tương đương giữa primitive và wrapper |
| `try`-with-resources | Đảm bảo đóng tài nguyên theo thứ tự/quy tắc exception của Java |
| Lambda / method reference | Cơ chế biểu diễn đối tượng hàm, thường qua `invokedynamic` và bootstrap metadata trên OpenJDK `javac` |
| `record` | Class có thành viên và hành vi được compiler tạo theo đặc tả record |
| Switch expression | Điều khiển luồng và tính toán giá trị tương ứng trong bytecode |

Danh sách mô tả **kết quả và cơ chế quan sát thường gặp**, không khẳng định compiler luôn biến đổi thành đúng một cấu trúc Java nguồn tương đương hoặc luôn phát ra một chuỗi instruction cố định. Chi tiết có thể khác theo JDK, `--release`, target và ngữ cảnh. Ví dụ, bytecode của lambda không phải lúc nào cũng là một anonymous class file tách riêng: trên OpenJDK thường có `invokedynamic`.

### Generic và erasure

Xem ví dụ:

~~~java
import java.util.List;

public class GenericDemo {
    public static int count(List<String> values) {
        return values.size();
    }

    public static void main(String[] args) {
        System.out.println(count(List.of("A", "B")));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 GenericDemo.java
java GenericDemo
~~~

Stdout:

~~~text
2
~~~

Ở mã nguồn, kiểu `List<String>` cho phép compiler kiểm tra ràng buộc phần tử. Trong descriptor method ở class file, tham số tương ứng dạng `java.util.List` sau erasure; metadata generic có thể giữ thông tin chữ ký để công cụ/reflection truy vấn. **Không** kết luận rằng JVM kiểm tra từng phần tử của `List` dưới dạng `String` vì nhìn thấy generic ở source; phần lớn generic Java được kiểm tra lúc biên dịch.

Quan sát class file bằng:

~~~bash
javap -p -s -v GenericDemo
~~~

Dùng output để nhận diện descriptor, `Signature` attribute và instruction. Output chi tiết có thể thay đổi theo phiên bản JDK; không nên kiểm thử bằng cách so toàn bộ văn bản `javap -v` giữa các JDK.

## 8. Generate: xuất class file và bytecode

Giai đoạn sinh mã (thường gọi `Gen`) tạo một hoặc nhiều file `.class` với cấu trúc được Java Virtual Machine Specification quy định. Ngoài instruction của method, class file còn có thể chứa constant pool, mô tả field/method, descriptors, access flags, `Code` attribute, exception table, line number, generic signatures, annotation metadata và thông tin khác.

Ví dụ đầy đủ — tệp `Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        int x = 20;
        int y = 22;
        System.out.println("Result: " + (x + y));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 Hello.java
java Hello
~~~

Stdout chính xác:

~~~text
Result: 42
~~~

Sau khi biên dịch thành công có `Hello.class`. Có thể xem bytecode bằng:

~~~bash
javap -c -p Hello
~~~

`javap` giúp thấy các thao tác nạp hằng, gọi method, điều khiển luồng và các instruction phát sinh; nó **không thực thi** method. Trình biên dịch có quyền tối ưu hoặc biểu diễn lại một số biểu thức theo ngữ nghĩa Java và phiên bản target, nên nội dung bytecode cụ thể không nhất thiết giống một minh họa instruction viết tay.

Nếu cần class file ở thư mục riêng:

~~~bash
mkdir out
javac --release 17 -d out Hello.java
java -cp out Hello
javap -classpath out -c Hello
~~~

Lưu ý `out` phải tồn tại trước khi sử dụng nó làm thư mục `-d` trong ví dụ. Một tệp nguồn có nhiều kiểu top-level hoặc nested type có thể sinh **nhiều** file `.class`. Nếu có lỗi biên dịch, không được giả định mọi class file của lượt gọi đã được tạo hoặc là phiên bản mới nhất: hãy kiểm tra mã thoát và xử lý các file output cũ cẩn thận.

### Tại sao cùng mã nguồn có thể cho class file khác nhau?

Các yếu tố có thể ảnh hưởng gồm phiên bản `javac`, target/release, option debug, annotation processing, implementation compiler và thay đổi nguồn phụ thuộc. Không nên dựa vào tính giống nhau tuyệt đối từng byte giữa các JDK để chứng minh hai chương trình có cùng ngữ nghĩa.

Thông tin gỡ lỗi như line numbers hoặc local variable metadata phụ thuộc các tùy chọn `-g` và cấu hình compiler; thay đổi metadata không nhất thiết thay đổi hành vi tính toán của chương trình.

## 9. Đặt ví dụ cạnh các giai đoạn: lỗi được phát hiện ở đâu?

Ba đoạn minh họa sau mô tả **các nhóm lỗi**, không cam kết diagnostic luôn xuất hiện trong một pass nội bộ duy nhất.

| Mã hoặc tình huống | Phần công việc liên quan | Vì sao lỗi |
| --- | --- | --- |
| Thiếu `;` / thiếu `}` | Lexing / parsing | Token không tạo được cấu trúc cú pháp hợp lệ |
| `MissingType value;` khi không có khai báo `MissingType` | Enter / name resolution / attribution | Compiler không phân giải được tên kiểu |
| `int x = "abc";` | Attribution / type checking | Gán sai kiểu |
| Dùng biến local chưa chắc đã được gán | Flow analysis | Vi phạm definite assignment |
| Truy cập `private` từ ngữ cảnh không hợp lệ | Semantic checks | Vi phạm access control |
| `-proc:only` nhưng chờ `Hello.class` | Chế độ processing/output | Lệnh được yêu cầu không sinh bytecode thông thường |
| Compile được, chạy lỗi `NoClassDefFoundError` | Class loading/linking lúc runtime | Class cần thiết không có lúc chạy hoặc không tải được |

Một thông báo diagnostic thường có **vị trí tệp, dòng, cột, mã lỗi và mô tả**; lỗi ở pha sớm có thể khiến phân tích tiếp theo bị hạn chế hoặc sinh thêm lỗi phụ. Vì vậy, khi gặp nhiều diagnostic, sửa lỗi đầu tiên có nguyên nhân rõ ràng rồi biên dịch lại thường giúp loại bỏ các lỗi dây chuyền.

Không có sự phân tách tuyệt đối “lỗi pha nào chỉ được xuất hiện ở pha đó” trong API công khai. Ví dụ, việc phân giải tên có thể liên quan enter, attribution và tải symbol từ classpath, nên bảng là bản đồ học tập, không phải hợp đồng chi tiết của implementation.

## 10. Cách quan sát compiler thay vì đoán pipeline

### 10.1. Dùng option public của javac

Đối với `Hello.java` ở mục 8:

~~~bash
javac -version
javac --release 17 -Xlint:all -d out Hello.java
javac -verbose --release 17 -d out Hello.java
~~~

- `-Xlint:all` bật các cảnh báo thuộc danh mục lint được `javac` hỗ trợ; nó không biến compiler thành bộ giải thích từng pha.
- `-verbose` hiển thị thông tin bổ sung như việc compiler đọc nguồn, nạp class và ghi output. Các dòng log và thứ tự có thể thay đổi theo JDK; **không** nên coi chúng là bản trace hoàn chỉnh của parse/enter/attr/flow/lower.
- `javac -X` cho biết các tùy chọn bổ sung mà bản `javac` hiện tại hỗ trợ. Những cờ nội bộ `-XD...` có thể thay đổi và không nên được xem là public contract ổn định.
- Dùng `-Xdiags:verbose` (nếu được hỗ trợ) khi cần ngữ cảnh diagnostic chi tiết hơn; điều này không tự sửa lỗi.

Nếu cần quan sát annotation processing, cấu hình một processor thực sự rồi thêm:

~~~bash
javac -XprintRounds -XprintProcessorInfo -processor com.example.MyProcessor -processorpath processor-classes -d out App.java
~~~

Đây là **mẫu lệnh cấu hình**, chỉ chạy được khi lớp processor `com.example.MyProcessor` đã được biên dịch và hiện diện ở `processor-classes`, `App.java` có thực và mọi dependency đã đầy đủ. Các option log không tự tạo processor.

### 10.2. Java Compiler Tree API và TaskListener

JDK có module `jdk.compiler` với API như `com.sun.source.util.JavacTask`, `TaskEvent` và `TaskListener` để công cụ theo dõi những sự kiện cấp cao. `TaskEvent.Kind` bao gồm `PARSE`, `ENTER`, `ANALYZE`, `GENERATE`, `ANNOTATION_PROCESSING`, `ANNOTATION_PROCESSING_ROUND` và `COMPILATION`.

**Các event không có quan hệ một-một với toàn bộ pass nội bộ.** Đặc biệt, không có yêu cầu mỗi class phải sinh đúng một event cho mọi tên bước như `Attr`, `Flow` hay `Lower`. Dùng event để hiểu quá trình ở mức API được hỗ trợ; không suy ra thứ tự cố định của mọi method bên trong compiler.

Ví dụ công cụ Java 17+ để theo dõi một biên dịch — tệp `TraceCompiler.java`:

~~~java
import com.sun.source.util.JavacTask;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import java.io.IOException;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class TraceCompiler {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Can JDK compiler de chay vi du");
        }

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(null, null, null)) {
            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects("Hello.java");

            JavacTask task = (JavacTask) compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none"),
                    null, units);

            task.setTaskListener(new TaskListener() {
                @Override
                public void started(TaskEvent event) {
                    System.out.println("START " + event.getKind());
                }

                @Override
                public void finished(TaskEvent event) {
                    System.out.println("END   " + event.getKind());
                }
            });

            boolean success = task.call();
            System.out.println("SUCCESS " + success);
        }
    }
}
~~~

Đặt `TraceCompiler.java` cùng thư mục với `Hello.java` ở mục 8 và chạy bằng JDK 17+:

~~~bash
javac TraceCompiler.java
java TraceCompiler
~~~

Với nguồn `Hello.java` hợp lệ và compiler hoạt động, dòng cuối là:

~~~text
SUCCESS true
~~~

Các dòng `START ...` / `END ...` phía trên phản ánh event thực tế và có thể có nhiều event hoặc khác thứ tự chi tiết theo phiên bản; vì thế không in một transcript cứng để tránh làm người học hiểu sai. Ví dụ đặt `-proc:none` để cô lập bước biên dịch khỏi processor được cài ngầm trong môi trường. Lớp `JavacTask` thuộc API dành cho công cụ dựa trên `javac`; nó khác các lớp implementation nội bộ trong `com.sun.tools.javac.*`.

**Lưu ý quan trọng:** phương thức `task.call()` kích hoạt biên dịch; listener chỉ theo dõi sự kiện. Nó không phải trình kiểm thử bytecode hoặc profiler hiệu năng. Các công cụ build/IDE có thể dùng Java Compiler API theo cách riêng.

## 11. Những thứ thường bị nhầm là pha của javac

**Class loading và verification.** Bytecode được sinh từ `javac` sẽ được JVM nạp và kiểm tra theo các quy tắc JVM ở runtime. Lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError` khi chạy thường liên quan classpath/class loader hoặc liên kết, dù biên dịch trước đó thành công.

**JIT.** Just-In-Time compiler chuyển/hạ mã khi chạy để tối ưu trên JVM phù hợp, khác với trình biên dịch nguồn `javac`. `javac` không cần chạy chương trình mới sinh ra `.class`.

**Gradle/Maven incremental compilation.** Build tool quyết định task nào cần chạy, lấy nguồn/dependency ở đâu và có thể bỏ qua một lượt `javac` nếu không có gì thay đổi. Đây là lớp điều phối build **bên ngoài** pipeline ngữ nghĩa của compiler. `javac` không tự đồng nghĩa với toàn bộ Gradle build.

**Packaging và deployment.** Lệnh tạo JAR, đóng gói ứng dụng, dựng container, ký artifact và phát hành là bước riêng. Một class file hợp lệ chưa chắc ứng dụng đầy đủ các dependency để chạy.

**Annotation runtime.** Annotation có retention policy `RUNTIME` có thể được đọc bằng reflection; điều đó độc lập với việc có processor lúc biên dịch. Một annotation có thể không được process nhưng vẫn tồn tại trong metadata runtime, tùy retention.

## 12. Chẩn đoán theo dấu hiệu

| Triệu chứng | Nên kiểm tra trước |
| --- | --- |
| `';' expected`, `illegal start of expression` | Token, dấu phân cách, cấu trúc câu lệnh; parse |
| `cannot find symbol` | Chính tả, import, package, nguồn, dependency, module visibility |
| `incompatible types` | Kiểu của hai vế, generic, overload, conversion, target type |
| `variable ... might not have been initialized` | Mọi nhánh gán biến, definite assignment |
| Processor không tạo nguồn | Cấu hình processor, module/classpath, option processing, log round |
| Thấy `.java` sinh ra nhưng không có `.class` | Có dùng `-proc:only` không, còn lỗi compilation không, `-d` chỉ đâu |
| Class file có format cũ/mới ngoài ý muốn | JDK thực tế, `--release`/`-target`, file output cũ |
| Biên dịch được nhưng lỗi khi `java` | Runtime classpath/module path, main class và dependency |

Một quy trình ngắn khi chẩn đoán:

1. In `javac -version` và giữ lại **toàn bộ lệnh** cùng working directory.
2. Biên dịch lại có kiểm soát, theo dõi exit code và diagnostic đầu tiên.
3. Nếu nghi xử lý annotation, kiểm tra processor thực sự được enable và thêm `-XprintRounds`.
4. Nếu lỗi output, xác minh `-d` và những file class được tạo mới; dùng `javap` quan sát descriptor/bytecode khi phù hợp.
5. Nếu lỗi chỉ xảy ra lúc chạy, kiểm tra JVM và runtime classpath; đừng tiếp tục sửa “pha parse” của mã đã biên dịch đúng.

## 13. Tự kiểm tra hiểu biết

**Câu 1.** `int n = "abc";` lỗi ở parse hay semantic analysis?  
**Trả lời:** Cấu trúc cú pháp hợp lệ; lỗi nằm ở kiểm tra kiểu.

**Câu 2.** Vì sao một processor có thể khiến compiler đọc thêm tệp `.java` trong cùng invocation?  
**Trả lời:** Processor sinh nguồn bằng cơ chế hỗ trợ của annotation processing; nguồn mới tham gia các round tiếp và quá trình biên dịch khi được cấu hình.

**Câu 3.** Có thể dùng mỗi `-verbose` để có timeline chính xác mọi pass nội bộ không?  
**Trả lời:** Không. Log verbose không phải hợp đồng trace tất cả pass; dùng TaskListener nếu cần sự kiện cấp cao, hoặc công cụ dành riêng cho việc quan sát nội bộ với hiểu biết về phiên bản JDK.

**Câu 4.** Tại sao `List<String>` trong source không nhất thiết tạo ra một kiểu JVM chuyên biệt riêng cho String?  
**Trả lời:** Java generics chủ yếu dựa trên erasure. Compiler kiểm tra kiểu generic và sinh descriptor/metadata tương ứng; JVM không tự tạo một class `List<String>` mới cho mỗi tham số kiểu.

**Câu 5.** Chạy `javac -proc:only` rồi không thấy `Hello.class` có chứng minh compiler lỗi không?  
**Trả lời:** Không. `-proc:only` yêu cầu xử lý annotation mà không tiếp tục sinh bytecode thông thường.

**Câu 6.** Nếu `java Hello` báo không tìm thấy class dù `javac` thành công, compiler đang ở pha nào?  
**Trả lời:** Lượt biên dịch đã kết thúc. Đó là vấn đề khi JVM khởi chạy, tìm/nạp class hoặc liên kết dependency; cần kiểm tra runtime classpath/module path.

## 14. Ghi nhớ và tài liệu tra cứu

- **Parse** kiểm tra cấu trúc cú pháp và tạo AST; **Enter** lập thông tin khai báo/symbol; **Analyze** phân giải tên, kiểm tra kiểu và luồng; **Lower/Generate** chuẩn bị và xuất bytecode.
- **Annotation processing** chỉ tham gia khi được cấu hình/enable phù hợp; có thể có nhiều round và nguồn sinh thêm.
- Giai đoạn của OpenJDK `javac` mô tả một implementation; **TaskEvent.Kind** là các sự kiện được API hỗ trợ, không phải danh sách đầy đủ những hàm/pass nội bộ.
- `javac` tạo class file; **JVM/JIT/Gradle/Maven** là các lớp công việc khác cần phân biệt khi tìm nguyên nhân lỗi.
- Dùng diagnostic, `-Xlint`, `-verbose`, `-XprintRounds`, `javap` và khi cần `TaskListener` để quan sát kết quả thật, không suy đoán từ một sơ đồ.

Tài liệu chính thức để đối chiếu theo phiên bản: [The javac Command (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), [TaskEvent.Kind (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskEvent.Kind.html), [Processor (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html).