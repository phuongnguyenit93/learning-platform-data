# Luồng thực thi lời gọi, return và kết thúc bất thường trong phương thức Java

Phương thức (method) là đơn vị hành vi quan trọng của class và object. Khi một phương thức gọi phương thức khác, chương trình không đơn giản “nhảy vào rồi quay lại”: Java phải xác định phương thức nào được gọi, đánh giá đối tượng nhận lời gọi và đối số, tạo ngữ cảnh thực thi cho lần gọi, thực hiện các câu lệnh rồi **hoàn tất bình thường** hoặc **kết thúc bất thường** vì một lỗi/ngoại lệ hay một cơ chế điều khiển luồng.

Bài này giải thích quá trình đó từ mã Java 17+ thực tế: **method invocation → thực thi thân method → `return` / `throw` → quay về điểm gọi hoặc lan truyền exception**. Bạn sẽ học cả cách đọc call stack và cách `try`, `catch`, `finally` ảnh hưởng đến kết quả.

## 1. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| **Caller (bên gọi)** | Đoạn mã chứa biểu thức hoặc câu lệnh gọi phương thức |
| **Callee (bên được gọi)** | Phương thức được thực thi bởi lần gọi đó |
| **Arguments (đối số)** | Các biểu thức được truyền tại điểm gọi, ví dụ `sum(2, 3)` có hai đối số |
| **Parameters (tham số)** | Biến nhận giá trị của đối số trong khai báo method, ví dụ `int left, int right` |
| **Call stack** | Mô hình ngăn xếp các lời gọi đang hoạt động của một thread |
| **Stack frame** | Ngữ cảnh thực thi của một lần gọi phương thức, chứa thông tin cần thiết cho lần gọi đó theo ngữ nghĩa JVM |
| **Normal completion của lời gọi** | Lời gọi hoàn tất theo đường trả về hợp lệ, tiếp tục thực thi caller |
| **Abrupt completion** | Một cấu trúc thực thi bị kết thúc theo lý do như `return`, `break`, `continue` hoặc `throw`, thay vì đi hết bình thường qua các câu lệnh của nó |

Một điểm rất quan trọng về thuật ngữ của Java: **câu lệnh `return` làm thân phương thức hoàn thành bất thường với lý do “return” theo Java Language Specification, nhưng bản thân _method invocation_ vẫn có thể hoàn thành bình thường và trả giá trị cho caller**. Ngược lại, nếu một exception thoát ra khỏi method mà không được xử lý trong method đó, **lời gọi method kết thúc bất thường bởi `throw`**.

Ví dụ:

~~~java
static int add(int a, int b) {
    return a + b;
}
~~~

`return` dừng thân method và cung cấp một giá trị. Khi gọi `int result = add(2, 3);`, lời gọi `add(2, 3)` hoàn tất bình thường với kết quả `5`.

## 2. Mô hình một lần gọi phương thức

Với lời gọi `result = account.deposit(amount);`, có thể dùng mô hình sau:

~~~text
Caller
  |
  | 1. Xác định cách gọi, kiểu và phương thức phù hợp
  | 2. Đánh giá biểu thức receiver và arguments
  | 3. Chuyển các giá trị đối số sang parameters
  v
Callee / method body
  |
  | 4. Thực thi các câu lệnh theo luồng điều khiển
  |
  +---- return / kết thúc thân void bình thường ------+
  |                                                   |
  +---- exception thoát khỏi method ------------------+----> caller xử lý hoặc lan tiếp
                                                      |
Caller tiếp tục sau lời gọi nếu lời gọi hoàn tất bình thường
~~~

Ở mức **ngôn ngữ**, các biểu thức đối số được đánh giá theo thứ tự trái sang phải; lời gọi instance còn có biểu thức receiver. Các bước của JVM có thể được tối ưu hóa bởi JIT và không nhất thiết tạo một frame vật lý độc lập đúng như hình vẽ cho mọi method nhỏ. Tuy nhiên, **thứ tự và hành vi quan sát được** phải tôn trọng ngữ nghĩa Java.

### Phương thức instance và phương thức static

~~~java
class Calculator {
    int doubleValue(int value) {
        return value * 2;
    }

    static int tripleValue(int value) {
        return value * 3;
    }
}
~~~

Đây là **class minh họa** có thể biên dịch khi được đặt trong một tệp nguồn phù hợp; nó không tự có `main` để chạy độc lập.

- `new Calculator().doubleValue(4)` là lời gọi **instance method** trên một object cụ thể; bên trong instance method có thể dùng `this`.
- `Calculator.tripleValue(4)` gọi **static method**, không có `this` của một Calculator cụ thể.
- Khi dùng `instance.method()`, Java cần xác định đối tượng nhận lời gọi. Việc receiver là `null` sẽ dẫn đến `NullPointerException` đối với lời gọi instance nếu quá trình đánh giá không ném một ngoại lệ khác trước.
- Một static method có thể được gọi từ method khác và vẫn có một lần gọi trong luồng thực thi; `static` không đồng nghĩa với “không dùng call stack”.

## 3. Trình tự gọi lồng nhau: đọc từ caller đến callee rồi quay về

Tạo file **`CallFlowDemo.java`**:

~~~java
public class CallFlowDemo {
    static int trace(String label, int value) {
        System.out.println("trace " + label + ": " + value);
        return value;
    }

    static int twice(int number) {
        System.out.println("twice begin");
        int result = number * 2;
        System.out.println("twice end");
        return result;
    }

    static int combine(int first, int second) {
        System.out.println("combine begin");
        int doubled = twice(first);
        System.out.println("combine end");
        return doubled + second;
    }

    public static void main(String[] args) {
        System.out.println("main begin");
        int answer = combine(trace("first", 3), trace("second", 4));
        System.out.println("answer = " + answer);
        System.out.println("main end");
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac -encoding UTF-8 CallFlowDemo.java
java CallFlowDemo
~~~

Stdout:

~~~text
main begin
trace first: 3
trace second: 4
combine begin
twice begin
twice end
combine end
answer = 10
main end
~~~

Giải thích theo thứ tự:

1. `main` in `main begin`.
2. Java cần đánh giá đối số của `combine(...)`. `trace("first", 3)` chạy trước, in một dòng và trả `3`; sau đó `trace("second", 4)` in một dòng và trả `4`.
3. `combine(3, 4)` bắt đầu, in `combine begin`.
4. `combine` gọi `twice(first)` với `first = 3`; `twice` in hai dòng rồi `return 6`.
5. Việc trả về từ `twice` khiến `combine` tiếp tục ở dòng sau `int doubled = twice(first);`. `combine` in `combine end`, sau đó trả `6 + 4 = 10`.
6. `main` nhận kết quả `10` rồi in `answer = 10` và `main end`.

Tại thời điểm `twice` đang chạy, các lời gọi chưa hoàn tất có quan hệ như sau:

~~~text
      Đỉnh stack (lời gọi đang thực thi)
       +---------------------------+
       | twice(first)              |
       +---------------------------+
       | combine(3, 4)             |
       +---------------------------+
       | main(args)                |
       +---------------------------+
      Đáy stack
~~~

Khi `twice` trả về, luồng tiếp tục trong `combine`; khi `combine` trả về, luồng tiếp tục trong `main`. **Một lời gọi lồng nhau tạm thời chuyển quyền điều khiển sang callee; caller chưa hoàn tất vẫn có thể tiếp tục sau khi callee trả về.**

### Vì sao phải để ý thứ tự đánh giá đối số?

Trong `combine(trace("first", 3), trace("second", 4))`, hai đối số đều có tác dụng phụ là in log. Java đảm bảo các biểu thức đối số được đánh giá **từ trái sang phải** trong lời gọi phương thức. Nếu đối số đầu tiên ném exception, đối số thứ hai **không được đánh giá**, và thân method đích chưa được vào.

Không nên dựa vào thứ tự đánh giá để cố tình tạo side effect phức tạp trong nhiều đối số. Một kiểu mã dễ đọc hơn là:

~~~java
int first = trace("first", 3);
int second = trace("second", 4);
int answer = combine(first, second);
~~~

Đoạn này chỉ minh họa cách tổ chức câu lệnh, đặt trong `main` hoặc một phương thức thích hợp; kết quả tương ứng giữ nguyên.

## 4. Truyền tham số: Java luôn truyền đối số bằng giá trị

Trước khi chạy thân method, giá trị của từng argument được chuyển cho parameter tương ứng theo quy tắc invocation conversion. Với kiểu nguyên thủy, method nhận **bản sao giá trị nguyên thủy**; với kiểu tham chiếu, method nhận **bản sao giá trị tham chiếu**.

Tạo file **`ParameterFlowDemo.java`**:

~~~java
public class ParameterFlowDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(int number, Box box) {
        number = 99;
        box.value = 20;
        box = new Box(500);

        System.out.println("inside number = " + number);
        System.out.println("inside box = " + box.value);
    }

    public static void main(String[] args) {
        int number = 5;
        Box box = new Box(10);

        change(number, box);

        System.out.println("outside number = " + number);
        System.out.println("outside box = " + box.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterFlowDemo.java
java ParameterFlowDemo
~~~

Stdout:

~~~text
inside number = 99
inside box = 500
outside number = 5
outside box = 20
~~~

Trong `change`:

- Gán `number = 99` chỉ thay đổi parameter cục bộ. Biến `number` trong `main` vẫn là `5`.
- Ban đầu parameter `box` tham chiếu **cùng Box** với biến `box` ở `main`. `box.value = 20` sửa trạng thái Box chung, nên caller thấy `20`.
- Lệnh `box = new Box(500)` chỉ gán **tham chiếu mới cho parameter `box`**. Nó không gán lại biến ở caller; Box của caller vẫn chứa `20`.
- Khi `change` kết thúc, parameter không còn trong lần gọi đó. Object được tạo bằng `new Box(500)` không tự được trả cho caller.

Vì vậy cách nói “Java truyền object theo tham chiếu để method sửa được biến gốc” là thiếu chính xác. **Java pass-by-value**, và giá trị được truyền có thể là một tham chiếu tới object mutable.

## 5. `return` kết thúc thân phương thức như thế nào?

### Phương thức trả về giá trị

Một phương thức có kiểu trả về khác `void` phải có đường thực thi hợp lệ để trả ra giá trị phù hợp hoặc kết thúc bằng exception. `return expression;` đánh giá biểu thức, áp dụng chuyển đổi kiểu cho giá trị trả về nếu được cho phép, rồi kết thúc thân method.

~~~java
static int absolute(int number) {
    if (number >= 0) {
        return number;
    }
    return -number;
}
~~~

Đây là **đoạn method minh họa**, đặt trong class tương ứng. Nếu `number = 3`, method trả `3` qua nhánh đầu; nếu `number = -3`, method trả `3` qua nhánh sau. Trong Java, riêng giá trị `Integer.MIN_VALUE` làm phép `-number` với `int` bị tràn và vẫn âm; khi thiết kế hàm trị tuyệt đối dùng trong nghiệp vụ nên xét trường hợp biên này.

Sau khi thực hiện một `return`, những câu lệnh ở đường đi thông thường phía sau nó **không được chạy**. Mã rõ ràng không thể tới được có thể gây lỗi biên dịch `unreachable statement`.

Ví dụ lỗi biên dịch, **không ghép vào ví dụ chạy**:

~~~java
static int broken() {
    return 1;
    // System.out.println("never"); // Nếu bỏ chú thích sẽ unreachable.
}
~~~

### Phương thức `void` và `return;`

Method `void` không cung cấp kết quả dùng như một giá trị của biểu thức. Nó có thể kết thúc khi luồng điều khiển đi đến cuối thân hoặc dùng `return;` để kết thúc sớm.

~~~java
static void printPositive(int value) {
    if (value <= 0) {
        return;
    }
    System.out.println(value);
}
~~~

Một method có kiểu `void` không được `return 42;`. Ngược lại, method có kiểu `int` không được chỉ viết `return;`.

### Nhiều đường `return` là hợp lệ

Lưu file **`ReturnBranchesDemo.java`**:

~~~java
public class ReturnBranchesDemo {
    static String grade(int score) {
        if (score < 0 || score > 100) {
            return "invalid";
        }
        if (score >= 80) {
            return "good";
        }
        if (score >= 50) {
            return "pass";
        }
        return "retry";
    }

    static void announce(String name) {
        if (name == null || name.isBlank()) {
            System.out.println("skip");
            return;
        }
        System.out.println("Hello " + name);
    }

    public static void main(String[] args) {
        System.out.println(grade(101));
        System.out.println(grade(85));
        System.out.println(grade(65));
        System.out.println(grade(20));

        announce("");
        announce("Mai");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReturnBranchesDemo.java
java ReturnBranchesDemo
~~~

Stdout:

~~~text
invalid
good
pass
retry
skip
Hello Mai
~~~

Mỗi lần gọi `grade` chỉ đi theo **một nhánh trả về**. Sau `return "good";`, các điều kiện phía dưới không còn được kiểm tra trong lần gọi đó. `announce("")` in `skip` và dừng sớm; `announce("Mai")` đi tiếp để in lời chào.

Hãy dùng nhiều `return` khi mỗi nhánh ngắn, có ý nghĩa và dễ kiểm tra. Không có quy tắc yêu cầu mọi phương thức Java chỉ được có một lệnh `return`.

### Mọi đường điều khiển của method non-void phải được bao phủ

Ví dụ **không biên dịch**:

~~~java
static int sign(int number) {
    if (number > 0) {
        return 1;
    }
    // Lỗi: có đường đi tới cuối method mà không trả int.
}
~~~

Compiler không chấp nhận một method khai báo `int` nếu có đường thực thi đi tới cuối method mà không trả về giá trị. Method có thể ném exception thay cho việc trả giá trị ở một nhánh hợp lệ:

~~~java
static int parseCount(String value) {
    if (value == null) {
        throw new IllegalArgumentException("value is required");
    }
    return Integer.parseInt(value);
}
~~~

Đoạn thứ hai là method hợp lệ: khi `value` null, nó **không trả `int`** mà kết thúc bất thường bởi exception. Khi không null, nó đánh giá `Integer.parseInt` và có thể trả `int` hoặc tiếp tục ném exception nếu chuỗi không hợp lệ.

## 6. `return` của kiểu tham chiếu không tự sao chép object

Nếu một method trả về `Student`, `Box` hoặc một kiểu tham chiếu khác, giá trị trả về là tham chiếu, không mặc định là bản sao sâu của object.

~~~java
class Document {
    String title;

    Document(String title) {
        this.title = title;
    }
}

class DocumentRepository {
    private final Document document = new Document("Draft");

    Document current() {
        return document; // Trả tham chiếu tới cùng object.
    }
}
~~~

Hai class trên là **mã minh họa**, không có `main`. Nếu caller nhận `Document d = repository.current();` và sửa `d.title`, object trong `DocumentRepository` cũng được sửa, bởi `d` chỉ đến cùng document.

Với object mutable, cần cân nhắc cung cấp thao tác kiểm soát hoặc bản sao phòng vệ nếu không muốn caller tác động trực tiếp đến state nội bộ. `return` không thay đổi quy tắc alias của Java.

Nếu method trả về `int` hoặc primitive khác, caller nhận **giá trị** nguyên thủy đã tính. Nếu method trả một tham chiếu `null`, invocation vẫn có thể hoàn tất bình thường với giá trị kết quả là `null`; lỗi `NullPointerException` có thể phát sinh ở lần dùng kết quả về sau.

## 7. “Kết thúc bất thường” do `throw` khác gì `return`?

`throw` làm luồng điều khiển rời khỏi vị trí đang thực thi với một exception. Nếu exception không được xử lý ở bên trong method hiện tại, nó đi **lên caller** qua các lời gọi đang hoạt động. Caller có thể bắt bằng `catch`, hoặc exception tiếp tục lan lên cao hơn.

Ví dụ:

~~~text
main()
   |
   +--> process(text)
           |
           +--> parsePositive(text)
                   |
                   +--> có thể throw IllegalArgumentException
           |
           +--> nếu throw không được catch ở đây:
                process không trở về theo đường return thông thường
   |
   +--> main catch exception rồi tiếp tục
~~~

Java phân biệt:

- **Checked exceptions:** một số loại exception mà compiler yêu cầu phải xử lý hoặc khai báo bằng `throws`, ví dụ `java.io.IOException`. Quy tắc kiểm tra này dựa trên kiểu exception và ngữ cảnh lời gọi.
- **Unchecked exceptions:** `RuntimeException` và các subclass của nó, cùng các subclass của `Error`, không bắt buộc khai báo hoặc catch ở compile time. Ví dụ `IllegalArgumentException`, `NumberFormatException`, `NullPointerException`.
- **`throw`:** câu lệnh **phát sinh** một exception object.
- **`throws`:** phần khai báo method mô tả các exception có thể thoát ra theo hợp đồng kiểu; bản thân `throws` không tự ném exception.
- **`catch`:** xử lý exception phù hợp phát sinh từ khối `try` tương ứng.

Không nên catch `Exception` tràn lan chỉ để chương trình “không báo lỗi”. Chọn vị trí xử lý có thể đưa ra hành vi hợp lý: thông báo cho người dùng, yêu cầu nhập lại, khôi phục tác vụ hoặc đóng tài nguyên.

## 8. Chạy thực tế: exception đi xuyên qua các tầng lời gọi

Lưu tệp **`ExceptionFlowDemo.java`**:

~~~java
public class ExceptionFlowDemo {
    static int parsePositive(String text) {
        System.out.println("parse begin: " + text);
        int value = Integer.parseInt(text);

        if (value <= 0) {
            throw new IllegalArgumentException("must be positive");
        }

        System.out.println("parse end");
        return value;
    }

    static int process(String text) {
        System.out.println("process begin");

        try {
            int number = parsePositive(text);
            System.out.println("process normal");
            return number * 2;
        } finally {
            System.out.println("process finally");
        }
    }

    public static void main(String[] args) {
        for (String input : new String[] {"4", "0", "oops"}) {
            System.out.println("input=" + input);

            try {
                System.out.println("result=" + process(input));
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" +
                        ex.getClass().getSimpleName());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExceptionFlowDemo.java
java ExceptionFlowDemo
~~~

Stdout:

~~~text
input=4
process begin
parse begin: 4
parse end
process normal
process finally
result=8
input=0
process begin
parse begin: 0
process finally
caught=IllegalArgumentException
input=oops
process begin
parse begin: oops
process finally
caught=NumberFormatException
~~~

### Phân tích trường hợp `"4"`

1. `main` bắt đầu gọi `process("4")`.
2. `process` in `process begin` rồi gọi `parsePositive("4")`.
3. `parsePositive` đổi chuỗi thành số 4, in `parse end`, `return 4`.
4. `process` in `process normal` rồi chuẩn bị `return 8`.
5. Trước khi phương thức hoàn tất, block `finally` in `process finally`.
6. Lời gọi `process` hoàn tất bình thường với giá trị 8; chỉ **sau đó** biểu thức bên ngoài mới được in qua `System.out.println("result=" + ...)`.

### Phân tích trường hợp `"0"`

`parsePositive("0")` parse được số 0 nhưng phát sinh `IllegalArgumentException` ở điều kiện không dương. Vì thế dòng `parse end` **không chạy**, `parsePositive` không trả giá trị, `process` không in `process normal`.

Trước khi exception rời `process`, `finally` in `process finally`. `main` nhận exception tại `catch (IllegalArgumentException ex)` và in tên class exception. Không có dòng `result=...` vì phần đánh giá đối số cho `println` chưa hoàn tất.

### Phân tích trường hợp `"oops"`

`Integer.parseInt("oops")` ném `NumberFormatException`. Đây là subclass của `IllegalArgumentException`, nên cùng `catch (IllegalArgumentException ex)` xử lý được. `ex.getClass().getSimpleName()` phản ánh **kiểu runtime** `NumberFormatException`.

Cả hai lỗi đều khiến `finally` chạy trong điều kiện thông thường, nhưng nguyên nhân exception khác nhau. Đó là lý do khi chẩn đoán lỗi phải đọc **loại exception và stack trace**, không chỉ xem có một câu lệnh `catch` nào đó.

## 9. `try`, `catch` và `finally` thay đổi đường đi ra sao?

Một method có thể hoàn tất qua nhiều nhánh:

~~~text
                       try
                        |
             +----------+----------+
             |                     |
       không exception         exception
             |                     |
       lệnh kế tiếp       có catch phù hợp?
             |              /             \
             |            có               không
             |            |                  |
             |       chạy catch         lan exception
             |            |                  |
             +------------+------------------+
                          |
                    finally nếu có
                          |
             tiếp tục, return hoặc throw
             theo kết quả cuối cùng
~~~

Sơ đồ đơn giản hóa trường hợp các block không tự ném exception khác. Trên thực tế, chính `catch` hay `finally` cũng có thể `return` hoặc `throw`, làm thay đổi kết quả. `finally` được thực thi khi điều khiển rời khỏi `try`/`catch` theo các cơ chế thông thường, bao gồm `return` và exception; nhưng không thể dựa vào `finally` như một bảo đảm chạy trong mọi trường hợp JVM/tiến trình bị dừng đột ngột.

### `finally` vẫn chạy khi có `return` trong `try`

Tạo file **`FinallyReturnDemo.java`**:

~~~java
public class FinallyReturnDemo {
    static int calculate() {
        int value = 1;

        try {
            System.out.println("try");
            return value;
        } finally {
            value = 9;
            System.out.println("finally value=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + calculate());
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
~~~

Stdout:

~~~text
try
finally value=9
returned=1
~~~

Giải thích: biểu thức của `return value;` được đánh giá khi `value` còn là 1. Trước khi hoàn tất lần gọi, `finally` đặt **biến cục bộ** `value` thành 9 rồi in log. Giá trị trả về đã xác định trước đó vẫn là 1.

**Phân biệt trường hợp trả về object mutable:** Nếu `return ref;` đã đánh giá tham chiếu tới một object, `finally` có thể thay đổi các field của object ấy trước khi caller sử dụng. Caller vẫn nhận cùng tham chiếu nhưng có thể quan sát trạng thái object sau khi `finally` sửa nó. Điều đó không mâu thuẫn với việc giá trị tham chiếu của biểu thức `return` đã được xác định.

### Không `return` trong `finally` nếu muốn giữ kết quả của `try`

Đoạn method sau hợp lệ nhưng **không nên áp dụng như kiểu thiết kế thông thường**:

~~~java
static int confusing() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
~~~

Lệnh `return 2;` trong `finally` thay thế lý do hoàn tất trước đó, khiến method trả **2**. Tương tự, nếu `try` đã ném exception mà `finally` thực hiện `return`, exception ban đầu có thể bị che mất. Nếu `finally` ném exception mới, exception mới có thể thay thế kết quả đang chờ, làm khó việc chẩn đoán.

Hãy giữ `finally` cho công việc cleanup phù hợp, tránh `return`, `break`, `continue` hoặc cố tình ném lỗi khác từ cleanup trừ khi thiết kế và hợp đồng thực sự yêu cầu.

### Catch xong chưa chắc method dừng

~~~java
static int recover() {
    try {
        Integer.parseInt("bad");
        return 1;
    } catch (NumberFormatException ex) {
        System.out.println("recovered");
    }
    return 2;
}
~~~

Đây là **đoạn minh họa method**, khi được gọi sẽ in `recovered` và trả 2. Exception đã được `catch` xử lý; control flow tiếp tục sau block `try-catch`. Không phải cứ có exception xuất hiện thì method luôn kết thúc ngay, và cũng không phải mọi `catch` đều phải `return`.

## 10. `try-with-resources` và thứ tự đóng tài nguyên

Khi method sử dụng file, stream, socket hoặc kết nối có `AutoCloseable`, nên học cách đóng tài nguyên trong luồng thực thi. `try-with-resources` cung cấp cơ chế đóng tự động khi kết thúc block, kể cả khi block ném exception.

Tạo file **`ResourceCloseDemo.java`**:

~~~java
public class ResourceCloseDemo {
    static final class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource second = new Resource("B")) {
            System.out.println("body");
        }

        System.out.println("after");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ResourceCloseDemo.java
java ResourceCloseDemo
~~~

Stdout:

~~~text
open A
open B
body
close B
close A
after
~~~

Các tài nguyên được khởi tạo từ trái sang phải và được đóng theo thứ tự **ngược lại**: B rồi A. Đóng tài nguyên là phần của quá trình rời khỏi block, được xử lý trước khi control flow tiếp tục đến dòng `after`.

Nếu thân `try` ném exception và `close()` cũng ném exception, cơ chế try-with-resources thường giữ exception chính và gắn lỗi đóng tài nguyên thành **suppressed exception**; có thể kiểm tra bằng `Throwable.getSuppressed()`. Điều này giúp bảo toàn nguyên nhân chính thay vì tùy tiện dùng `return` trong `finally` khiến lỗi gốc bị che.

Một số trường hợp đặc biệt như JVM bị dừng tức thời vẫn không có bảo đảm cleanup diễn ra. Không đồng nhất `try-with-resources` với lịch thu gom rác: GC không thay thế cơ chế đóng tài nguyên theo logic nghiệp vụ.

## 11. Checked exception, `throws` và ranh giới của method

Với checked exception như `java.io.IOException`, compiler kiểm tra những method có thể làm exception thoát ra. Một method có thể xử lý bằng `catch` hoặc khai báo ngoại lệ trong chữ ký.

Đoạn method minh họa:

~~~java
static String firstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (java.io.BufferedReader reader =
            java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Đoạn này không phải tệp chạy độc lập; nó là một method đặt trong class, dùng một tham số `Path` đã được caller cung cấp. `newBufferedReader` và `readLine` có thể gây `IOException`. Method **khai báo `throws IOException`** để caller chịu trách nhiệm xử lý hoặc lan tiếp, đồng thời đóng reader sau khi kết thúc block.

Ví dụ caller xử lý:

~~~java
try {
    String line = firstLine(path);
    System.out.println(line);
} catch (java.io.IOException ex) {
    System.out.println("Cannot read file: " + ex.getMessage());
}
~~~

Đây cũng là **đoạn minh họa**, yêu cầu biến `path` thuộc kiểu `Path` và method `firstLine` trong cùng ngữ cảnh phù hợp. Điều cần nhớ không phải cú pháp I/O chi tiết, mà là **kết thúc bất thường có thể đi xuyên qua ranh giới nhiều method**, và `throws` làm rõ một phần hợp đồng của method.

Một method khai báo `throws IOException` không đồng nghĩa rằng mọi lần gọi đều sẽ ném exception. Nếu đường chạy hoàn tất và trả về, invocation vẫn bình thường. Ngược lại, unchecked exception có thể thoát ra dù method không khai báo nó trong `throws`.

## 12. Thứ tự đánh giá và lỗi ngay ở đối số

Đôi khi lỗi xuất hiện **trước khi method đích bắt đầu chạy**. Khi đọc stack trace hoặc log, phải xác định exception phát sinh trong biểu thức chuẩn bị lời gọi, hay trong chính thân method.

Tạo file **`ArgumentEvaluationDemo.java`**:

~~~java
public class ArgumentEvaluationDemo {
    static int first() {
        System.out.println("first argument");
        return 1;
    }

    static int second() {
        System.out.println("second argument");
        throw new IllegalStateException("failed to prepare second");
    }

    static void receive(int a, int b) {
        System.out.println("receive body");
    }

    public static void main(String[] args) {
        try {
            receive(first(), second());
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
        System.out.println("main continues");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentEvaluationDemo.java
java ArgumentEvaluationDemo
~~~

Stdout:

~~~text
first argument
second argument
caught: failed to prepare second
main continues
~~~

`first()` chạy và trả 1, rồi `second()` bắt đầu, in log và ném `IllegalStateException`. Vì đối số thứ hai không được đánh giá xong, method `receive` **không được vào**, nên dòng `receive body` không xuất hiện. `catch` trong `main` xử lý exception, rồi chương trình in `main continues`.

### Biểu thức receiver cũng được đánh giá trước lời gọi instance

Với `getService().run(computeArgument())`, biểu thức `getService()` được đánh giá để xác định receiver trước biểu thức đối số. Nếu đánh giá receiver **tự ném exception**, các đối số phía sau không được đánh giá. Nếu kết quả receiver là `null`, trong một lời gọi instance thông thường Java vẫn thực hiện đánh giá các biểu thức đối số trước khi phát hiện lời gọi không có receiver hợp lệ và ném `NullPointerException` (trừ khi có exception khác xảy ra sớm hơn). Đây là khác biệt tinh tế giữa **receiver expression ném exception** và **receiver expression trả `null`**.

Không nhất thiết phải viết mã có side effect bên trong đối số để chứng minh quy tắc này. Trong thiết kế thông thường, đặt các kết quả trung gian vào biến cục bộ rõ tên sẽ giúp debug tốt hơn.

## 13. Overloading chọn chữ ký, overriding chọn triển khai

Một lời gọi instance chịu ảnh hưởng của hai cơ chế dễ bị lẫn:

- **Overloading**: nhiều method cùng tên nhưng khác danh sách tham số; compiler chọn chữ ký phù hợp dựa trên kiểu biểu thức tại điểm gọi và các quy tắc overload resolution.
- **Overriding**: subclass cung cấp triển khai cho instance method được kế thừa và cho phép override; runtime chọn triển khai phù hợp dựa trên kiểu thực tế của receiver.

Tạo file **`DispatchFlowDemo.java`**:

~~~java
public class DispatchFlowDemo {
    static class Parent {
        String render(Object value) {
            return "Parent(Object)";
        }

        String render(String value) {
            return "Parent(String)";
        }
    }

    static final class Child extends Parent {
        @Override
        String render(Object value) {
            return "Child(Object)";
        }
    }

    public static void main(String[] args) {
        Parent receiver = new Child();
        Object data = "hello";

        System.out.println(receiver.render(data));
        System.out.println(receiver.render("hello"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 DispatchFlowDemo.java
java DispatchFlowDemo
~~~

Stdout:

~~~text
Child(Object)
Parent(String)
~~~

Ở dòng đầu, biến `data` có **kiểu khai báo `Object`**, dù đối tượng runtime của nó là `String`. Compiler chọn overload `render(Object)`. Receiver runtime là `Child` nên triển khai overriding `Child.render(Object)` được gọi.

Ở dòng thứ hai, đối số literal `"hello"` có kiểu `String`, compiler chọn overload `render(String)`. `Child` không override phiên bản này, vì vậy dùng triển khai kế thừa `Parent.render(String)`.

Dù cả hai lệnh cùng có receiver runtime là Child và dữ liệu chuỗi nội dung giống nhau, phương thức chạy có thể khác vì **overload resolution trước, dynamic dispatch sau**. Đây là yếu tố quan trọng khi lần theo luồng gọi của một hierarchy class.

Static methods không được override bằng dynamic dispatch như instance methods. Nếu subclass khai báo static method cùng chữ ký phù hợp, đó là **method hiding**; cách phân giải khác overriding.

## 14. Recursion cũng là những lần gọi phương thức thông thường

Một method có thể gọi lại chính mình. Mỗi lần gọi có **parameters và local variables riêng** theo ngữ nghĩa, cùng một quan hệ caller–callee như những method khác. Phải có điều kiện dừng để không lặp vô hạn.

Tạo file **`RecursiveReturnDemo.java`**:

~~~java
public class RecursiveReturnDemo {
    static int factorial(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        if (n <= 1) {
            return 1;
        }
        return n * factorial(n - 1);
    }

    public static void main(String[] args) {
        System.out.println(factorial(4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecursiveReturnDemo.java
java RecursiveReturnDemo
~~~

Stdout:

~~~text
24
~~~

Trình tự các lời gọi:

~~~text
factorial(4)
  -> 4 * factorial(3)
          -> 3 * factorial(2)
                  -> 2 * factorial(1)
                          -> return 1
                  -> return 2
          -> return 6
  -> return 24
~~~

Các phép nhân được hoàn tất theo chiều **quay về**: sau khi `factorial(1)` trả 1 thì `factorial(2)` tính 2, rồi `factorial(3)` tính 6, cuối cùng `factorial(4)` tính 24.

Nếu thiếu điều kiện dừng hoặc độ sâu quá lớn, quá trình có thể dẫn tới `StackOverflowError`. Java **không bảo đảm tối ưu hóa tail recursion**, nên không dựa vào lời gọi đệ quy vô hạn hoặc quá sâu để xử lý dữ liệu lớn. Ví dụ dùng `int` nên cũng có giới hạn biểu diễn: `factorial(13)` vượt miền `int` và gây tràn nếu chỉ nhân thông thường; đây là vấn đề số học độc lập với call stack.

## 15. Exception và call stack: đọc lỗi như một đường đi

Khi exception không được xử lý trong một method, JVM có thể tạo stack trace mô tả chuỗi lời gọi có liên quan. Một trace minh họa có thể có dạng:

~~~text
java.lang.IllegalStateException: failed
    at Demo.leaf(Demo.java:...)
    at Demo.middle(Demo.java:...)
    at Demo.main(Demo.java:...)
~~~

Đây là **mô phỏng định dạng**, không phải stdout cố định: số dòng, tên file và các chi tiết có thể khác nhau theo chương trình, môi trường và cách JVM xây dựng stack trace.

Đọc từ trên xuống:

1. Dòng đầu cho biết **loại exception và thông điệp**.
2. Frame gần đầu thường dẫn đến vị trí ném/phát hiện lỗi.
3. Frame phía dưới cho thấy caller đã gọi đường thực thi đi tới lỗi.
4. Đọc ngược luồng này giúp tìm input nào gây lỗi, method nào chuyển input, và có `catch` nào đã xử lý hay chưa.

Nếu exception không được xử lý và thoát tới entry point của thread, cơ chế mặc định thường in stack trace ra **stderr**, không phải stdout. Không nên chép một output stack trace với số dòng tự đoán làm “đầu ra chính xác” của bài học.

### Khi nào một lời gọi không trở về bình thường?

- Thân method phát sinh exception và không catch được tại đó.
- Một method được gọi bên trong nó ném exception; method hiện tại không xử lý.
- Một biểu thức receiver hoặc argument ném exception trước khi thân method đích chạy.
- Code trong `finally` làm phát sinh exception thay thế đường hoàn tất đang chờ.
- JVM có thể gặp lỗi nghiêm trọng như `StackOverflowError` hoặc `OutOfMemoryError`; đừng mặc định mọi lỗi runtime đều có thể xử lý và tiếp tục an toàn.

Việc có một `return` ở cuối file method không bảo đảm method luôn trả kết quả: bất kỳ biểu thức hoặc thao tác nào trước đó cũng có thể ném exception nếu điều kiện gây lỗi xảy ra.

## 16. Thực hành phân tích luồng trước khi chạy

### Bài 1 — Dự đoán thứ tự log

Cho đoạn mã minh họa đặt trong class:

~~~java
static int left() {
    System.out.println("L");
    return 2;
}

static int right() {
    System.out.println("R");
    return 3;
}

static int sum(int a, int b) {
    System.out.println("S");
    return a + b;
}
~~~

Khi gọi `System.out.println(sum(left(), right()));`, kết quả:

~~~text
L
R
S
5
~~~

Giải thích: Java đánh giá hai đối số từ trái qua phải, sau đó chạy thân `sum`; `println` ngoài cùng chỉ in số 5 khi biểu thức `sum(...)` đã hoàn tất.

### Bài 2 — `return` sớm

~~~java
static String status(int count) {
    if (count < 0) {
        return "invalid";
    }
    if (count == 0) {
        return "empty";
    }
    return "active";
}
~~~

Dự đoán `status(-2)`, `status(0)`, `status(3)` lần lượt là `invalid`, `empty`, `active`. Chỉ một nhánh `return` được thực hiện trong từng lời gọi.

### Bài 3 — Exception khiến câu lệnh sau không chạy

~~~java
static int fail() {
    throw new IllegalStateException("boom");
}

static int compute() {
    int result = fail();
    System.out.println("unreachable at runtime");
    return result + 1;
}
~~~

Đoạn là **minh họa**, có thể biên dịch trong class thích hợp. Phần sau `fail()` là cú pháp có thể biên dịch vì compiler không buộc phải suy ra lời gọi `fail` luôn ném exception, nhưng **khi chạy phiên bản `fail` này** sẽ không in dòng `unreachable at runtime` và sẽ không thực hiện `return result + 1`. Cần phân biệt “compiler phát hiện unreachable statement” với “một dòng không được tới do dữ liệu/exception lúc chạy”.

### Bài 4 — `finally` và giá trị trả về

~~~java
static int value() {
    int n = 1;
    try {
        return n + 1;
    } finally {
        n = 100;
    }
}
~~~

Kết quả là **2**, không phải 101. Biểu thức `n + 1` được đánh giá trước khi `finally` chạy; `finally` chỉ đổi biến cục bộ.

### Bài 5 — Đọc call stack đệ quy

Với `factorial(4)`, hãy viết ra các lời gọi đang chờ khi `factorial(1)` bắt đầu. Thứ tự từ đáy tới đỉnh stack là `main → factorial(4) → factorial(3) → factorial(2) → factorial(1)`. Sau `return 1`, các mức trả lần lượt `2`, `6` và `24`.

## 17. Lỗi thường gặp khi đọc và viết luồng gọi

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Hễ gặp `return` trong callee là toàn bộ chương trình dừng.” | `return` dừng lần gọi callee; caller có thể tiếp tục sau lời gọi. |
| “`return` và `throw` đều trả một giá trị.” | `return` trả kết quả hoặc kết thúc method `void`; `throw` lan một exception, không trả giá trị thông thường. |
| “Method `void` không thể dừng sớm.” | `void` dùng được `return;` không có biểu thức. |
| “Parameter primitive và reference đều truyền theo tham chiếu.” | Java truyền bằng giá trị; với object, bản sao của **tham chiếu** được truyền. |
| “Hai đối số có thể chạy theo thứ tự tùy ý.” | Java quy định đánh giá từ trái sang phải trong lời gọi. |
| “Method đích luôn chạy dù đối số phát sinh lỗi.” | Nếu chuẩn bị argument ném exception, method đích có thể chưa được vào. |
| “Method có `return` chắc chắn không có exception.” | Bất kỳ biểu thức nào trước/trong quá trình return cũng có thể ném exception; `finally` cũng có thể thay đổi kết quả. |
| “`finally` chỉ chạy khi có exception.” | Nó được thực hiện cả trên các đường hoàn tất bình thường và `return` trong điều kiện thông thường. |
| “Giá trị trả về luôn được tính sau `finally`.” | Biểu thức `return` được đánh giá trước; `finally` chạy trước khi lời gọi thực sự hoàn tất. |
| “`return` trong `finally` là cách sửa kết quả an toàn.” | Nó che khuất `return` hoặc exception đang chờ; nên tránh. |
| “`throws` tự ném exception.” | `throws` chỉ khai báo loại exception có thể thoát ra; `throw` mới phát sinh exception. |
| “Overload được quyết định bằng kiểu object runtime của argument.” | Overload resolution dựa trên kiểu ở compile time; overriding dùng dynamic dispatch cho instance method. |
| “Không có `catch` thì mọi exception tự biến mất khi method kết thúc.” | Exception có thể lan tiếp qua caller, cuối cùng làm thread kết thúc nếu không được xử lý. |
| “Method kết thúc sẽ lập tức hủy mọi object nó tạo.” | Object có thể vẫn reachable qua caller hoặc field; việc thu hồi bộ nhớ không đồng nhất với method return. |

## 18. Checklist kiểm tra kết quả học

- [ ] Tôi xác định được caller, callee, argument và parameter trong một lời gọi.
- [ ] Tôi có thể vẽ call stack của ba lời gọi lồng nhau và chỉ ra thứ tự quay về.
- [ ] Tôi dự đoán được thứ tự in log khi đối số là các lời gọi method khác.
- [ ] Tôi phân biệt method `void`, method có giá trị trả về, `return;` và `return expression;`.
- [ ] Tôi hiểu `return` thoát khỏi một lần gọi, còn exception không xử lý có thể lan qua nhiều lời gọi.
- [ ] Tôi hiểu primitive và tham chiếu object đều được truyền theo giá trị trong Java.
- [ ] Tôi chỉ ra được vị trí method đích chưa chạy vì receiver hoặc đối số ném exception.
- [ ] Tôi biết `try`, `catch`, `finally` có thể thay đổi luồng điều khiển như thế nào.
- [ ] Tôi dự đoán được giá trị trả về từ `try` khi `finally` chỉnh sửa một biến cục bộ.
- [ ] Tôi biết tại sao `return` trong `finally` có nguy cơ che mất lỗi gốc.
- [ ] Tôi biết ý nghĩa của checked exception, unchecked exception, `throw` và `throws`.
- [ ] Tôi phân biệt overload resolution và dynamic dispatch khi gọi method của class có kế thừa.
- [ ] Tôi chạy được từng chương trình Java 17+ trong bài và đối chiếu stdout trước/sau khi thay đổi dữ liệu.

Khi cần phân tích một chương trình Java có nhiều phương thức, hãy lần lượt hỏi: **đối số nào được đánh giá trước, method nào thật sự được chọn, phương thức đang chạy có thể đi ra bằng `return` hay `throw`, `finally` có được thực hiện không, và caller sẽ tiếp tục ở vị trí nào?** Trả lời lần lượt những câu hỏi này giúp lần theo luồng thực thi có hệ thống, tìm lỗi chính xác và thiết kế hành vi class dễ kiểm thử.
