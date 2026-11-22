# Đọc vị trí, mã lỗi và ngữ cảnh thông báo biên dịch Java

Khi **javac** không biên dịch được một tệp Java, thông báo lỗi không đơn thuần là một câu tiếng Anh. Một diagnostic thường chứa nhiều manh mối: **tệp nguồn**, **dòng/cột**, **loại thông báo**, **đoạn mã gây chú ý**, **dấu đánh dấu vị trí**, **nguyên nhân kiểm tra của compiler** và đôi khi **chi tiết về symbol, kiểu hoặc method signature**.

Học cách đọc các phần này theo thứ tự giúp sửa đúng vấn đề thay vì đoán và thay đổi nhiều đoạn mã cùng lúc. Chủ đề này thuộc giai đoạn **chẩn đoán lỗi biên dịch**: trọng tâm là hiểu thông báo của compiler, truy ngược về ngữ cảnh mã nguồn và phân biệt lỗi gốc với lỗi phát sinh tiếp theo. Bài sử dụng các công cụ có sẵn từ **JDK 17+**.

## 1. Diagnostic là gì?

**Diagnostic** là một thông báo do compiler tạo ra khi phân tích nguồn hoặc thực hiện một bước liên quan đến biên dịch. Diagnostic có thể là:

- **Error**: vấn đề khiến bước biên dịch không thành công, chẳng hạn cú pháp sai, symbol không tìm thấy, kiểu không tương thích.
- **Warning**: mã vẫn có thể được biên dịch nhưng compiler cảnh báo một rủi ro hoặc vấn đề cần chú ý, chẳng hạn raw type hay unchecked operation.
- **Note / thông tin bổ sung**: giải thích về bối cảnh, khả năng dùng option khác, annotation processing hoặc những vấn đề liên quan.

Khi đọc kết quả, luôn hỏi **compiler đang cố làm gì tại vị trí đó?** Ví dụ một khai báo biến có thể đúng cú pháp nhưng sai kiểu. Trong trường hợp khác, tên của một lớp đã đúng nhưng compiler không tìm thấy JAR hoặc module chứa lớp đó. Chúng có thể tạo những câu tiếng Anh tương tự nhưng cách xử lý khác nhau.

**Một thông báo diagnostic không nhất thiết có đủ mọi trường.** Một lỗi liên quan trực tiếp đến mã nguồn thường có vị trí cụ thể. Cảnh báo tổng quát về tùy chọn compiler, classpath hoặc annotation processor có thể không gắn với dòng/cột nào trong tệp.

## 2. Cấu trúc một thông báo javac điển hình

Tạo tệp **Broken.java** với nội dung sau:

~~~java
public class Broken {
    public static void main(String[] args) {
        int total = 10;
        System.out.println(totla);
    }
}
~~~

Tên biến đã khai báo là **total**, nhưng lệnh in sử dụng **totla**. Chạy:

~~~bash
javac Broken.java
~~~

Một bản JDK hiển thị diagnostic tiếng Anh có thể cho đầu ra tương đương:

~~~text
Broken.java:4: error: cannot find symbol
        System.out.println(totla);
                           ^
  symbol:   variable totla
  location: class Broken
1 error
~~~

Ví dụ trên minh họa **hình dạng thông báo phổ biến**, không cam kết từng dấu cách, cột hiển thị hoặc cách xuống dòng bất biến giữa phiên bản JDK, locale và cách terminal trình bày.

Phân tích từng phần:

| Phần | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| **Tệp** | Broken.java | Source file liên quan đến diagnostic |
| **Dòng** | 4 | Vị trí được compiler gắn với lỗi |
| **Mức độ** | error | Đây là lỗi biên dịch, không chỉ là warning |
| **Thông điệp chính** | cannot find symbol | Không giải quyết được một tên tại ngữ cảnh này |
| **Dòng nguồn** | System.out.println(totla); | Đoạn mã đã khiến compiler báo vấn đề |
| **Caret** | ^ dưới totla | Chỉ token/vị trí mà compiler đang đánh dấu |
| **symbol** | variable totla | Symbol đang cần tìm là một biến tên totla |
| **location** | class Broken | Phạm vi hoặc vị trí tìm tên được compiler nhắc đến |
| **Tổng kết** | 1 error | Số diagnostic lỗi được công cụ báo trong lần chạy |

**Không kết luận “dòng 4 luôn là nguyên nhân gốc” một cách máy móc.** Compiler đánh dấu nơi nó phát hiện mâu thuẫn; khai báo gây lỗi có thể nằm trước đó, trong file khác hoặc trong dependency. Với ví dụ này, so sánh **total** và **totla** đủ để tìm ra lỗi chính tả.

### 2.1. Số dòng và số cột

Trong mẫu diagnostic dạng văn bản **Broken.java:4: error...**, số **4** là dòng. Với nhiều diagnostic javac tiêu chuẩn, vị trí cột được thể hiện bằng caret dưới đoạn source, không nhất thiết có một số cột ghi rõ trong header. IDE và Java Compiler API có thể cung cấp số cột riêng.

Khi dùng Java Compiler API:

- **getLineNumber()** và **getColumnNumber()** trả về vị trí theo quy ước dòng/cột của API, bắt đầu từ **1** đối với vị trí hợp lệ.
- **getPosition()** trả về offset ký tự từ đầu source object, bắt đầu từ **0**.
- Nếu compiler không có vị trí phù hợp, API trả **Diagnostic.NOPOS** cho những thông tin vị trí đó.
- **getStartPosition()**, **getPosition()**, **getEndPosition()** cho phép công cụ đánh dấu phạm vi nguồn; không nên tự suy một khoảng chính xác từ ký tự caret duy nhất.

Đừng nhầm cột trong trình biên dịch với vị trí pixel trong IDE. **Tab**, chữ Unicode, font có độ rộng biến đổi, CRLF và hiển thị terminal có thể làm vị trí nhìn bằng mắt khác với vị trí theo ký tự/offset của công cụ. Nếu caret có vẻ lệch, mở tệp ở chế độ hiển thị whitespace hoặc xem vị trí qua IDE.

### 2.2. Đường dẫn tương đối và tuyệt đối

Tùy cách gọi, diagnostic có thể dùng tên tệp như **Broken.java**, đường dẫn tương đối như **src/main/java/app/Broken.java**, hoặc đường dẫn dài hơn. Nếu biên dịch nhiều nguồn cùng tên, cần chú ý **đường dẫn đầy đủ trong thông báo** chứ không chỉ tên cuối.

Khi chạy trong Gradle/Maven hoặc CI, vị trí làm việc có thể khác với terminal của bạn. Kiểm tra lệnh biên dịch thực sự được build tool dùng; đừng mặc định diagnostic path luôn được tính từ thư mục hiện tại đang mở trong IDE.

## 3. Dấu caret chỉ nơi phát hiện, không luôn chỉ nơi cần sửa

Compiler thực hiện nhiều bước: đọc ký tự, phân tích token, tạo cây cú pháp, giải quyết tên, kiểm tra kiểu, phân tích luồng và một số phép kiểm tra liên quan. Ở mỗi bước, nó chọn một **vị trí nguồn có ý nghĩa** để gắn diagnostic.

Ví dụ lỗi thiếu dấu phân cách:

~~~java
public class MissingSemicolon {
    public static void main(String[] args) {
        int a = 10
        System.out.println(a);
    }
}
~~~

Compiler có thể đánh dấu ở token **System** thuộc dòng tiếp theo, vì tại đó nó nhận ra dòng khai báo trước chưa kết thúc bằng **;**. Sửa đúng là thêm dấu chấm phẩy sau **10**, không phải xóa System.

Một trường hợp khác:

~~~java
class WrongType {
    public static void main(String[] args) {
        int count = "five";
    }
}
~~~

Đây là **lỗi kiểu**, không phải lỗi ký tự hay dấu ngoặc. Compiler có thể đánh dấu biểu thức **"five"**, nhưng nguyên nhân là khai báo **int** không tương thích với giá trị **String**.

**Quy trình khi caret có vẻ không chỉ đúng nguyên nhân:** đọc vài dòng trước và sau, kiểm tra dấu ngoặc/dấu chấm phẩy, truy cập khai báo của symbol liên quan, và xem kiểu của biểu thức. Vị trí diagnostic là **điểm bắt đầu điều tra**, không phải mệnh lệnh sửa đúng ký tự đang được trỏ đến.

## 4. Phân biệt “mã lỗi” với câu thông báo và nhãn cảnh báo

Trong javac thường có ít nhất ba khái niệm nên tách riêng:

1. **Thông điệp người đọc thấy**: chẳng hạn **cannot find symbol**, **incompatible types**, **';' expected**. Văn bản có thể khác theo phiên bản và ngôn ngữ hiển thị.
2. **Mã diagnostic**: chuỗi do compiler cung cấp, lấy qua **javax.tools.Diagnostic.getCode()** hoặc cơ chế dành cho công cụ. Giá trị này **phụ thuộc implementation**, không phải một bộ số lỗi chuẩn chung cho mọi compiler Java.
3. **Nhóm cảnh báo (lint category)**: ví dụ **[unchecked]**, **[rawtypes]**, **[deprecation]** khi bật tùy chọn lint thích hợp. Đây là nhãn phân loại warning, không đồng nghĩa mã diagnostic đầy đủ.

Ví dụ, khi javac không giải quyết được biến, thông điệp dễ thấy có thể là **cannot find symbol**; với công cụ dùng javac, mã diagnostic có thể có dạng tiền tố **compiler.err.**. Không nên ghi cứng một mã cụ thể rồi cho rằng mọi bản javac, IDE, Eclipse compiler và hệ thống build phải trả cùng chuỗi.

**Thông điệp không phải mã lỗi ổn định để chương trình parse.** Nếu cần tự động hóa, ưu tiên API cấu trúc với **Diagnostic.Kind**, vị trí, nguồn và diagnostic code nếu được hỗ trợ. Nếu lưu mã để phân tích xu hướng lỗi qua nhiều JDK, ghi kèm **vendor, phiên bản javac, option và ngôn ngữ** để tránh diễn giải nhầm.

### 4.1. Lỗi (error), cảnh báo (warning) và note

| Nhóm | Ý nghĩa | Có buộc biên dịch thất bại? |
| --- | --- | --- |
| **ERROR** | Quy tắc biên dịch bị vi phạm | Có |
| **WARNING** | Vấn đề compiler cảnh báo, có thể vẫn tạo class file | Thông thường không; **-Werror** có thể biến warning thành thất bại của bước compile |
| **MANDATORY_WARNING** trong API | Một loại warning bắt buộc theo quy tắc công cụ/ngôn ngữ | Không tự đồng nghĩa với compile error |
| **NOTE** | Thông tin bổ sung | Không |
| **OTHER** | Loại thông báo không thuộc các nhóm cụ thể trên | Phải xem thông điệp thực tế |

**Có class file không có nghĩa không có warning.** Ngược lại, khi dùng **-Werror**, compiler có thể chấm dứt biên dịch không thành công vì warning dù nguồn không có lỗi cú pháp thông thường.

## 5. Các nhóm lỗi thường gặp và cách đọc ngữ cảnh

### 5.1. “cannot find symbol”

Ví dụ:

~~~java
class NameError {
    void show() {
        System.out.println(userNmae);
    }
}
~~~

Trong ngữ cảnh trên, compiler không tìm được biến **userNmae**. Cần kiểm tra:

- Có khai báo biến hay không; có viết nhầm chữ hoặc khác chữ hoa/thường không?
- Biến có nằm trong scope tại điểm sử dụng không?
- Với method hoặc class, tên, import, kiểu receiver và classpath/module path đã đúng chưa?
- Có gọi member của sai object hoặc một type không cung cấp method đó không?

**Không tự động thêm import** khi diagnostic đang nói tới **local variable**. Trường **symbol: variable ...** khác với **symbol: class ...** hoặc **symbol: method ...**, nên xem phần symbol/location trước khi sửa.

### 5.2. “incompatible types”

Ví dụ:

~~~java
class TypeError {
    String name = 42;
}
~~~

Compiler thấy một giá trị số nguyên ở vị trí cần **String**. Cần đọc đủ hai vế: **required** (kiểu mong muốn) và **found/provided** (kiểu thực), hoặc cách diễn đạt tương đương trong diagnostic. Vấn đề có thể nằm ở:

- Kiểu của biến nhận kết quả;
- Giá trị trả về của method;
- Kiểu generic trong collection;
- Overload đang được lựa chọn;
- Chuyển kiểu tự động không được Java cho phép.

Đừng khắc phục bằng cast bừa. Hãy xác định contract trước: biến phải là String, hay dữ liệu thực sự phải được chuyển đổi thành String?

### 5.3. “';' expected”, “')' expected”, “reached end of file while parsing”

Đây thường là nhóm lỗi cú pháp. Kiểm tra:

- Dấu chấm phẩy sau statement;
- Cặp ngoặc tròn, ngoặc vuông và ngoặc nhọn;
- Dấu nháy chuỗi hoặc char literal;
- Cấu trúc if, for, method, class;
- Một token ở dòng trước khiến parser hiểu sai phần tiếp theo.

Ví dụ:

~~~java
class UnclosedBlock {
    void run() {
        System.out.println("Hello");
    // Thiếu ngoặc nhọn để đóng method và class.
~~~

Tùy cấu trúc chính xác, compiler có thể báo ở cuối tệp vì parser chưa nhận được phần đóng cần thiết. Sửa tại **đầu mối mất cân bằng ngoặc**, không phải thêm ký tự tùy ý vào cuối file chỉ để dập một thông báo.

### 5.4. “package ... does not exist” hoặc package không visible

Nếu nguồn chứa:

~~~java
import example.library.Widget;
~~~

mà javac không tìm được thư viện, cần kiểm tra **dependency và compile classpath/module path**. Khi chạy theo JPMS, lỗi về package **not visible** có thể liên quan **requires** hoặc **exports**, không chỉ JAR thiếu.

**Import không tải thư viện.** Dòng import đúng chính tả vẫn không khiến lớp xuất hiện trên classpath. Khi phân loại lỗi, tách câu hỏi “có tìm thấy type?” khỏi “type có được phép truy cập không?”.

### 5.5. Lỗi overload và tham số method

Thông điệp như **method ... cannot be applied to given types** thường kèm các phần **required**, **found**, **reason** hoặc danh sách **candidate methods**. Hãy đối chiếu:

- Số lượng đối số;
- Thứ tự và kiểu từng đối số;
- Generic type arguments;
- Constructor/method có public và truy cập được không;
- Static/instance context;
- Có overload nào có thể áp dụng theo quy tắc chuyển kiểu của Java không?

Nếu diagnostic dài, dùng **-Xdiags:verbose** (phần 7) để mở rộng ngữ cảnh. Cẩn thận khi sử dụng code fix tự động của IDE nếu nó đổi contract phương thức chỉ để khớp lời gọi sai.

## 6. Một lỗi gốc có thể kéo theo nhiều thông báo

Một cú pháp sai đầu file có thể khiến parser hiểu nhầm những dòng tiếp theo. Một type không tìm thấy có thể khiến nhiều biểu thức sử dụng type đó tiếp tục không kiểm tra được. Vì vậy output có thể chứa hàng chục diagnostics nhưng không có nghĩa có hàng chục nguyên nhân độc lập.

Ví dụ minh họa:

~~~java
class CascadingErrors {
    void run() {
        UnknownType item = new UnknownType();
        System.out.println(item.value());
    }
}
~~~

Nếu **UnknownType** không có khai báo hoặc dependency, compiler không thể xác định kiểu và method **value()** một cách tin cậy. Sửa hoặc bổ sung đúng type trước khi đánh giá các thông báo tiếp theo; danh sách diagnostic ở lần biên dịch sau có thể thay đổi.

Cách xử lý hữu ích:

1. Đọc **diagnostic đầu tiên đủ cụ thể**, gồm file, vị trí và thông điệp.
2. Kiểm tra vài dòng xung quanh và các khai báo liên quan.
3. Sửa một nguyên nhân có bằng chứng.
4. Biên dịch lại, xem còn thông báo nào.
5. Chỉ xử lý warning sau khi đã hiểu các error làm cản trở phân tích.

**Không áp dụng cứng “luôn sửa dòng 1 trong danh sách”.** Khi compiler xử lý nhiều tệp hoặc annotation processor, thứ tự diagnostics có thể không trùng thứ tự phụ thuộc nguyên nhân. Một lỗi dependency nền tảng có thể quan trọng hơn vài dòng báo lỗi đầu tiên trong source downstream.

## 7. Tùy chọn javac giúp đọc diagnostics chi tiết hơn

### 7.1. Hiển thị thêm chi tiết với -Xdiags

Thử:

~~~bash
javac -Xdiags:verbose Broken.java
~~~

**-Xdiags:verbose** chọn chế độ diagnostic chi tiết hơn, hữu ích khi lời gọi method hoặc generic type inference có nhiều candidate. Có thể so với:

~~~bash
javac -Xdiags:compact Broken.java
~~~

Hai lựa chọn điều khiển **cách trình bày diagnostic**, không sửa mã và không tự thay đổi quy tắc kiểu của Java. Không bảo đảm mọi lỗi đơn giản như typo sẽ có thông điệp khác biệt đáng kể giữa hai chế độ.

### 7.2. Bật nhóm cảnh báo với -Xlint

Tạo **WarningSample.java**:

~~~java
import java.util.List;

public class WarningSample {
    List values;
}
~~~

Biên dịch:

~~~bash
javac -Xlint:rawtypes WarningSample.java
~~~

Compiler có thể báo cảnh báo **[rawtypes]** tại khai báo **List values** vì kiểu generic List đã bị dùng không kèm type arguments. Để xem thêm nhiều nhóm cảnh báo:

~~~bash
javac -Xlint:all WarningSample.java
~~~

**-Xlint:rawtypes** và **-Xlint:unchecked** là hai nhóm khác nhau; raw declaration có thể xuất hiện mà chưa có một unchecked invocation cụ thể. Khi nhận cảnh báo, đọc cả **nhãn lint**, dòng nguồn và giải thích.

Có thể xem những nhóm lint được bản JDK hỗ trợ bằng:

~~~bash
javac --help-lint
~~~

Không nên cho rằng mọi JDK có cùng bộ warning category hoặc bật cùng nhóm theo mặc định. Tham số lint giúp đặt câu hỏi chẩn đoán rõ hơn, không biến một lỗi logic được biên dịch hợp lệ thành lỗi kiểu tự động.

### 7.3. Đổi warning thành thất bại build với -Werror

~~~bash
javac -Xlint:rawtypes -Werror WarningSample.java
~~~

**-Werror** yêu cầu javac xem warning là điều kiện khiến compilation task thất bại. Trong ví dụ có raw List, bước compile sẽ không được coi là thành công khi warning được phát hiện. Cách dùng này phù hợp CI khi dự án cần kiểm soát warning mới.

Phân biệt:

- **Lỗi được phát hiện**: quy tắc ngôn ngữ bị vi phạm.
- **Warning gây thất bại do -Werror**: nguồn được phép theo quy tắc chính nhưng chính sách build không chấp nhận warning.

Đừng nói một warning đã “biến thành lỗi cú pháp” chỉ vì -Werror khiến exit code khác 0.

### 7.4. Giới hạn lượng thông báo hiển thị

Với dự án sinh nhiều lỗi, có thể điều chỉnh:

~~~bash
javac -Xmaxerrs 20 -Xmaxwarns 20 Broken.java
~~~

Hai tùy chọn giới hạn **số lỗi/cảnh báo được in ra**, không loại bỏ nguyên nhân trong nguồn và không khắc phục compilation. Khi chỉ một số thông báo xuất hiện, đừng kết luận phần còn lại không tồn tại.

Khi xử lý một codebase đang hỏng nặng, có thể giới hạn output để dễ đọc, sửa lỗi gốc, rồi chạy lại với output đầy đủ trước khi kết luận thành công.

### 7.5. Diagnostic code nội bộ và giới hạn ổn định

Một số bản javac có chế độ nội bộ như **-XDrawDiagnostics** để hiển thị các khóa thông báo dành cho việc chẩn đoán/compiler testing. Đây **không phải giao diện thông điệp ổn định để ứng dụng production phụ thuộc**; nếu nghiên cứu, hãy kiểm tra bản JDK cụ thể và không khẳng định các khóa như **compiler.err...** là tiêu chuẩn chung của ngôn ngữ Java.

Nếu muốn thu thập diagnostic trong một công cụ Java chính thức, lựa chọn phù hợp hơn là **Java Compiler API** và **DiagnosticCollector**, như ở phần 9.

## 8. Đọc log biên dịch trong IDE, Maven, Gradle và CI

Mỗi công cụ có thể bọc thông điệp javac bằng log riêng. Chẳng hạn build tool có thể đặt trước đường dẫn task, dấu thời gian, dấu hiệu mức độ hoặc tóm tắt số lỗi. Cần **tách lớp log của công cụ khỏi diagnostic gốc**.

Ví dụ dạng minh họa, không phải log chính xác của mọi phiên bản:

~~~text
> Task :compileJava FAILED
.../src/main/java/app/Broken.java:4: error: cannot find symbol
        System.out.println(totla);
                           ^
...
~~~

Ở đây **compileJava FAILED** cho biết task của Gradle thất bại; còn **Broken.java:4: error: cannot find symbol** là thông tin giúp xác định lỗi nguồn. Nếu Maven/Gradle dùng compiler khác hoặc formatter tùy biến, message và vị trí có thể được diễn đạt khác.

Các bước chẩn đoán:

1. **Xác nhận task/module đang biên dịch**: nhiều dự án có cùng tên file ở main/test hoặc nhiều subproject.
2. **Ghi lại JDK và compiler thực sự được dùng**: terminal dùng JDK khác IDE/CI sẽ có khác biệt về API và message.
3. **Tìm diagnostic gốc** trước khi đọc tóm tắt stack trace dài của build tool.
4. **Mở đúng revision nguồn**: log CI có thể ứng với commit khác với file hiện có trên máy.
5. **Kiểm tra root cause của dependency** nếu nhiều class không được tìm thấy.
6. **Biên dịch lại sau sửa** và lưu exit status để xác nhận.

**Runtime exception không phải compile diagnostic.** Stack trace như **NullPointerException** hay **ClassNotFoundException** trong lúc chạy cho biết lỗi runtime, khác với thông báo javac khi biên dịch. Tuy vậy một build tool cũng có thể ném exception trong chính quy trình build, nên nhìn vào task và thời điểm xảy ra.

## 9. Đọc diagnostics có cấu trúc qua Java Compiler API

Khi viết IDE plugin, công cụ kiểm tra source hoặc hệ thống chấm bài, có thể cần thông tin có cấu trúc thay vì phân tích chuỗi stderr. Java cung cấp **javax.tools.JavaCompiler**, **javax.tools.Diagnostic**, **DiagnosticListener** và **DiagnosticCollector**.

Các trường hữu ích của **Diagnostic**:

| API | Ý nghĩa |
| --- | --- |
| **getKind()** | ERROR, WARNING, MANDATORY_WARNING, NOTE hoặc OTHER |
| **getSource()** | Source object liên quan; có thể null nếu không gắn vào source |
| **getLineNumber()** | Số dòng khi có vị trí |
| **getColumnNumber()** | Số cột khi có vị trí |
| **getPosition()** | Offset của vị trí diagnostic trong source |
| **getStartPosition(), getEndPosition()** | Phạm vi vị trí để highlight |
| **getCode()** | Mã do implementation cung cấp; có thể null |
| **getMessage(Locale)** | Thông điệp có thể được bản địa hóa; nội dung phụ thuộc compiler |

Dùng **getKind**, vị trí và source để xây dựng trình xem lỗi; lưu **getCode** nếu hữu ích nhưng không lấy nó làm khóa duy nhất quyết định hành vi trên mọi compiler.

### 9.1. Ví dụ độc lập: thu thập lỗi mà không parse stderr

Tạo tệp **CompileReport.java**:

~~~java
import java.net.URI;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class CompileReport {
    static final class MemorySource extends SimpleJavaFileObject {
        private final String content;

        MemorySource(String name, String content) {
            super(
                URI.create("string:///" + name),
                JavaFileObject.Kind.SOURCE
            );
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    public static void main(String[] args) {
        String source = String.join("\n",
            "public class Broken {",
            "    public static void main(String[] args) {",
            "        int total = 10;",
            "        System.out.println(totla);",
            "    }",
            "}"
        );

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("Cần chạy bằng JDK đầy đủ");
            return;
        }

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        JavaCompiler.CompilationTask task = compiler.getTask(
            null,
            null,
            collector,
            List.of("--release", "17", "-proc:none"),
            null,
            List.of(new MemorySource("Broken.java", source))
        );

        Boolean successful = task.call();
        System.out.println("success=" + successful);

        for (Diagnostic<? extends JavaFileObject> d
                : collector.getDiagnostics()) {
            System.out.println(
                d.getKind() + " line " + d.getLineNumber()
            );
        }
    }
}
~~~

Biên dịch và chạy trên JDK có hỗ trợ **--release 17** (ví dụ JDK 17 hoặc JDK 21):

~~~bash
javac CompileReport.java
java CompileReport
~~~

Đầu ra chuẩn cho ví dụ với compiler javac thông thường:

~~~text
success=false
ERROR line 4
~~~

**Vì sao kết quả có thể dự đoán?** Source trong bộ nhớ có class Broken và đúng một tham chiếu đến biến chưa khai báo **totla** ở dòng 4. Compiler được yêu cầu không chạy annotation processors qua **-proc:none**, nên không có mã được sinh thêm làm thay đổi tình huống. API collector nhận diagnostic thay vì chỉ trông chờ stderr của trình biên dịch.

**Phạm vi ví dụ:** Chương trình CompileReport là mã có thể chạy độc lập. Nó cố ý **biên dịch một đoạn Broken.java không hợp lệ trong bộ nhớ**, nên kết quả success là false; bản thân **CompileReport.java** vẫn phải biên dịch thành công. Nếu dùng một Java runtime image đã lược bỏ **jdk.compiler**, ToolProvider có thể không cung cấp system JavaCompiler. Sử dụng JDK đầy đủ.

Có thể mở rộng vòng lặp để đọc thêm dữ liệu:

~~~java
// Minh họa phần thân vòng lặp: không phải chương trình độc lập.
System.out.println("column=" + d.getColumnNumber());
System.out.println("code=" + d.getCode());
System.out.println("message=" + d.getMessage(java.util.Locale.ENGLISH));
~~~

Với phiên bản code trên, thêm ba lệnh này **bên trong vòng for** khi cần. Nội dung **code** và **message** là thông tin phụ thuộc compiler; không nên ghi một stdout cố định cho chúng.

### 9.2. Một diagnostic có thể không có vị trí

Không phải mọi thông báo đều đi kèm source location. Khi tích hợp API, kiểm tra:

~~~java
// Minh họa khi biến d có kiểu Diagnostic<? extends JavaFileObject>.
if (d.getPosition() == Diagnostic.NOPOS) {
    System.out.println("Không có vị trí nguồn cụ thể");
}
~~~

Nếu không có source, **getSource()** có thể trả null. Vì thế một hệ thống lưu diagnostic nên cho phép **source, line, column** vắng mặt, thay vì giả định mỗi warning đều thuộc một dòng trong tệp .java.

### 9.3. Lưu ý về mã diagnostic

**Diagnostic.getCode()** trả về mã do implementation xác định. Có thể dùng để nhóm thông điệp trong một phiên bản javac, nhưng khi nâng JDK hoặc đổi compiler, hãy kiểm chứng lại mapping. Bản địa hóa có thể làm **getMessage(Locale)** đổi ngôn ngữ mà mã diagnostic vẫn cùng dạng trong một implementation; không dùng văn bản tiếng Anh của message làm giao thức máy bắt buộc.

## 10. Tình huống thực tế: đọc, xác minh, sửa, biên dịch lại

Xét đoạn code:

~~~java
import java.util.List;

public class OrderReport {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        System.out.println(names.get(2));
    }
}
~~~

**Ví dụ này biên dịch thành công.** Lỗi tiềm ẩn ở đây là **IndexOutOfBoundsException tại runtime**, vì danh sách chỉ có hai phần tử chỉ số 0 và 1. Không nên chờ javac báo lỗi về get(2): compiler không thể suy ra toàn bộ trạng thái runtime từ lời gọi chung này. Mục đích là phân biệt lỗi không được compiler báo với compile diagnostic.

Ngược lại, đổi thành:

~~~java
// Đoạn mã minh họa lỗi kiểu, không phải một chương trình độc lập.
List<String> names = List.of("An", "Binh");
names.add(42);
~~~

Compiler có đủ thông tin static để báo lỗi kiểu tham số: **add(String)** không chấp nhận int/Integer. Kết luận chẩn đoán đúng là sửa kiểu phần tử hoặc dữ liệu được thêm, không cố thêm import hay classpath.

### 10.1. Mẫu quy trình năm câu hỏi

Khi gặp một diagnostic, trả lời theo trình tự:

1. **Ở đâu?** File chính xác, dòng, cột hoặc token đang được chỉ tới; có đúng revision code không?
2. **Mức độ gì?** ERROR, WARNING hay NOTE; có chính sách **-Werror** không?
3. **Compiler đang nói gì?** Đọc thông điệp chính, symbol, required/found, location, method candidates và các dòng note.
4. **Vì sao tại ngữ cảnh này?** Kiểm tra scope, khai báo, kiểu, package/module, dependency hoặc cú pháp trước đó.
5. **Bằng chứng sửa xong?** Biên dịch lại bằng cùng JDK/options, kiểm tra còn diagnostic hay không, rồi chạy test nếu chương trình có thể biên dịch.

Không nên chỉ nhìn dòng **1 error** cuối log; đó là **kết quả tổng hợp**, không nói lỗi thuộc lớp nào.

## 11. Những lỗi chẩn đoán thường gặp

**Sai lầm 1 — Sửa đúng vị trí caret mà không đọc dòng trước.** Một dấu chấm phẩy thiếu ở dòng 3 có thể gây lỗi tại token dòng 4. Cần đọc cả statement đang mở.

**Sai lầm 2 — Thấy cannot find symbol là thêm import.** Nếu symbol là biến cục bộ viết sai tên, import không giúp gì. Nếu symbol là class từ dependency, ngoài tên còn phải kiểm tra classpath/module path.

**Sai lầm 3 — Chỉ đọc dòng đầu của một diagnostic nhiều dòng.** Những phần **symbol, location, required, found, reason** có thể là dữ kiện quyết định để sửa đúng.

**Sai lầm 4 — Xem tất cả warnings là errors.** Warning thường không chặn compile trừ khi chính sách build đặt **-Werror** hoặc công cụ xử lý khác. Nhưng không vì thế mà bỏ qua warning.

**Sai lầm 5 — Coi mã lỗi javac là số ID chuẩn hóa của Java.** Diagnostic code là implementation-dependent; các compiler khác nhau có thể dùng mã khác.

**Sai lầm 6 — Sao chép nguyên một diagnostic từ CI rồi đối chiếu với tệp không cùng commit.** Kết quả báo lỗi liên quan revision lúc compile. Kiểm tra branch/commit trước khi dựa vào số dòng.

**Sai lầm 7 — Fix từng diagnostic trong 100 lỗi mà không kiểm tra lỗi gốc.** Khi một type quan trọng thiếu, nhiều message tiếp theo có thể là hệ quả. Sửa nguyên nhân chung trước.

**Sai lầm 8 — Nhầm runtime stack trace với lỗi javac.** Phải phân biệt quá trình compiler đang phân tích mã nguồn hay JVM đang thực thi ứng dụng.

**Sai lầm 9 — Đọc caret như số cột tuyệt đối trên mọi công cụ.** Terminal, IDE và compiler API có quy tắc hiển thị vị trí khác nhau. Khi cần vị trí cho editor, dùng API có cấu trúc.

**Sai lầm 10 — Tắt warning mà không hiểu.** Các annotation hoặc lựa chọn build có thể suppress một nhóm cảnh báo; điều đó không chứng minh nguồn an toàn.

## 12. Bài tập thực hành

### Bài 1 — Đọc symbol và location

Biên dịch **Broken.java** ở phần 2, trả lời:

- File và dòng nào được compiler chỉ tới?
- Symbol bị thiếu là biến hay class?
- Dòng nào khai báo tên gần giống nhưng khác chính tả?
- Tại sao cách sửa thích hợp không phải thêm import?

Sửa **totla** thành **total**, biên dịch lại và chạy **java Broken**. Kết quả chuẩn:

~~~text
10
~~~

### Bài 2 — Phân loại lỗi cú pháp và kiểu

Cho hai fragment:

~~~java
int n = ;
String text = 99;
~~~

Hãy giải thích vì sao fragment đầu sai cấu trúc cú pháp, fragment sau sai kiểu. Thử đặt mỗi fragment trong method của một tệp Java hợp lệ để quan sát diagnostic cụ thể.

### Bài 3 — So sánh compact và verbose

Chạy **javac -Xdiags:compact Broken.java** rồi **javac -Xdiags:verbose Broken.java**. So sánh mức độ chi tiết; không buộc hai đầu ra phải khác nhau ở mọi lỗi.

Nếu muốn nhìn khác biệt rõ hơn, tạo các overload hoặc lời gọi generic sai tham số, sau đó so sánh các phần required/found/candidate mà compiler cung cấp.

### Bài 4 — Quan sát warning

Tạo **WarningSample.java** ở phần 7. Chạy:

~~~bash
javac -Xlint:rawtypes WarningSample.java
javac -Xlint:rawtypes -Werror WarningSample.java
~~~

Giải thích vì sao một lệnh có thể hoàn tất biên dịch kèm warning, còn lệnh kia báo thất bại theo chính sách.

### Bài 5 — Phân loại lỗi phụ thuộc

Giả sử compiler báo **package example.api does not exist** từ một import. Hãy liệt kê kiểm tra cần làm về JAR/source path/module path trước khi sửa cấu trúc Java source. Nếu javac báo package trong named module **not visible**, kiểm tra thêm requires/exports.

### Bài 6 — Thu thập diagnostic bằng API

Chạy **CompileReport.java**; giải thích vì sao main của CompileReport chạy thành công nhưng **task.call()** trả false. Bổ sung in **getColumnNumber()**, **getCode()**, **getMessage(Locale.ENGLISH)**; xác định phần nào có thể khác khi đổi JDK.

### Bài 7 — Đọc log build

Chọn một log thực tế có từ hai module/subproject. Xác định:

- Diagnostic bắt đầu từ dòng nào trong log;
- File và revision nào tương ứng;
- Có bao nhiêu lỗi nguồn và cảnh báo;
- Build tool thất bại vì compile error, -Werror hay lý do khác.

Không chỉnh sửa hoặc xóa phần log nguồn trước khi tìm được nguyên nhân.

## 13. Câu hỏi tự kiểm tra

- Tại sao caret đôi khi trỏ sang dòng sau lỗi cú pháp thực sự?
- Sự khác nhau giữa **file:line**, cột hiển thị, offset ký tự và **Diagnostic.NOPOS** là gì?
- Trong thông báo cannot find symbol, phần symbol và location cung cấp thông tin gì?
- Khi nào should kiểm tra required/found thay vì thêm import?
- Mã diagnostic và văn bản message có phải một bộ mã lỗi ổn định của Java không?
- **-Xlint** khác **-Xdiags:verbose** như thế nào?
- **-Werror** thay đổi chính sách build ra sao?
- Vì sao sửa một lỗi dependency có thể khiến nhiều diagnostic khác biến mất?
- JavaCompiler API có ưu điểm gì so với parse stderr bằng regular expression?
- Vì sao một lỗi IndexOutOfBoundsException không xuất hiện như compile diagnostic trong ví dụ OrderReport?

## 14. Tài liệu tham khảo

- **Oracle JDK 17 – javac command (diagnostics, -Xdiags, -Xlint, -Werror, -Xmaxerrs):** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- **Oracle JDK 21 – javac command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html
- **Java SE 17 – javax.tools.Diagnostic:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- **Java SE 17 – javax.tools.DiagnosticCollector:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- **Java SE 17 – javax.tools.JavaCompiler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **Java Language Specification 17 – Types, Expressions and Statements:** https://docs.oracle.com/javase/specs/jls/se17/html/index.html

**Ghi nhớ:** Để đọc lỗi javac, bắt đầu bằng **tệp, dòng/cột và mức độ**, sau đó đọc **thông điệp chính, symbol/type context và đoạn nguồn**. Dấu caret đánh dấu nơi compiler phát hiện vấn đề, không luôn là nơi sửa. Mã diagnostic, nhãn lint và thông điệp văn bản là những thông tin khác nhau. Chẩn đoán tốt là tìm ra nguyên nhân được bằng chứng hỗ trợ, sửa tối thiểu và **biên dịch lại để xác nhận**.