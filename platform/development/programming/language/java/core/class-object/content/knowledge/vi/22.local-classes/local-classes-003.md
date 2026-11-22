# Truy cập biến cục bộ `final` và `effectively final` từ lớp cục bộ trong Java

Một **lớp cục bộ (local class)** là class được khai báo bên trong một block, chẳng hạn thân method, constructor hoặc một block lệnh. Ngoài việc có fields và methods riêng, local class còn có thể **sử dụng biến cục bộ và tham số** của phạm vi chứa nó. Java đặt ra một điều kiện quan trọng: **biến local hoặc tham số được tham chiếu từ phần thân local class phải là `final` hoặc `effectively final`** và phải đáp ứng quy tắc *definite assignment* tại nơi sử dụng.

`final` là modifier bạn viết tường minh; `effectively final` là tính chất compiler suy ra từ cách biến được gán. Một biến không có chữ `final` vẫn được capture nếu trong phạm vi của nó biến **không bị gán lại theo những quy tắc mà Java áp dụng cho effectively final**. Ngược lại, `final StringBuilder builder` có thể trỏ tới một `StringBuilder` vẫn sửa được: `final` cấm **gán lại biến**, không làm **object đích bất biến**.

Bài thuộc **Java core - class-object**, mục **Lớp cục bộ**; phạm vi là cách local class tham chiếu dữ liệu bên ngoài nó, không phải học thuộc chung chung từ khóa `final`. Các ví dụ dùng **Java 17+**, phân biệt rõ chương trình hoàn chỉnh với đoạn minh họa; mỗi chương trình chạy độc lập có tên tệp, lệnh `javac`/`java` và stdout xác định.

## 1. Kết quả học tập cần đạt

Sau bài này, bạn có thể:

1. Nhận diện một **local class declaration** và phạm vi nhìn thấy tên lớp.
2. Phân biệt **local variable**, **method parameter**, **instance field**, **static field** và **field riêng của local class**.
3. Giải thích vì sao một local class được phép sử dụng biến local `final` hoặc `effectively final`.
4. Phân biệt **gán lại reference** với **mutate object được reference**.
5. Dự đoán lỗi compile-time khi local variable được capture nhưng bị gán lại.
6. Hiểu trường hợp biến được gán một lần theo nhánh `if`, vòng `for` thông thường và enhanced `for`.
7. Giải thích cách local object tiếp tục sử dụng các giá trị đã capture sau khi method chứa nó trả về.
8. Phân biệt `this` trong local class với `Outer.this`, đồng thời xử lý shadowing.
9. So sánh local class với lambda, anonymous class và static nested class ở mức capture.
10. Viết các hàm trả interface mà implementation là local class, tránh lộ kiểu triển khai không cần thiết.
11. Kiểm thử output và hành vi khi biến được capture là reference tới object mutable.
12. Hiểu vì sao `effectively final` **không tự đồng nghĩa thread safety**.

## 2. Nhận diện local class qua vị trí khai báo

Ví dụ đơn giản:

~~~java
public class Example {
    void execute() {
        int base = 10;

        class Adder {
            int add(int value) {
                return base + value;
            }
        }

        Adder adder = new Adder();
        System.out.println(adder.add(5));
    }
}
~~~

Đây là **class minh họa hợp lệ**, chưa có `main`. `Adder` là **local class** vì được khai báo trong body của method `execute()`. Tên `Adder` có thể dùng trong phần scope hợp lệ của block chứa khai báo, nhưng **không thể dùng làm tên kiểu bên ngoài scope đó** như một public API thông thường.

Biến `base` không khai báo `final`, nhưng không bị gán lại sau khi có giá trị 10, nên nó **effectively final**. `Adder.add()` được phép tham chiếu `base`.

Khác với local class:

- **Top-level class** được khai báo ở cấp file/package.
- **Member class** được khai báo trong một class/interface, không phải trong block method.
- **Non-static inner member class** có enclosing object theo quan hệ member.
- **Static nested member class** không có enclosing instance ngầm định.
- **Anonymous class** tạo một instance từ class body không có tên.
- **Lambda expression** là một biểu thức hiện thực functional interface, có quy tắc capture gần gũi nhưng ngữ nghĩa `this` khác anonymous/local class.

**Local class cũng là một loại nested class**, nhưng điểm nhận diện ở đây là **vị trí trong block** và quyền tham chiếu các local variables của phạm vi ấy.

## 3. Chương trình hoàn chỉnh 1 — capture một biến effectively final

Tạo tệp **`LocalCaptureBasicsDemo.java`**:

~~~java
public class LocalCaptureBasicsDemo {
    public static void main(String[] args) {
        int base = 10;
        final String prefix = "result=";

        class Calculator {
            int plus(int amount) {
                return base + amount;
            }

            void print(int amount) {
                System.out.println(prefix + plus(amount));
            }
        }

        Calculator first = new Calculator();
        Calculator second = new Calculator();

        first.print(3);
        second.print(7);
        System.out.println("different objects="
                + (first != second));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 LocalCaptureBasicsDemo.java
java LocalCaptureBasicsDemo
~~~

**Stdout chính xác:**

~~~text
result=13
result=17
different objects=true
~~~

Ở đây, `base` **effectively final**, còn `prefix` **explicitly final**. Hai biến đều được local class `Calculator` sử dụng hợp lệ. Hai lời gọi `new Calculator()` tạo **hai objects khác nhau**; tuy nhiên cả hai đọc cùng các giá trị đã capture trong invocation của `main`.

Không nên hiểu rằng `base` trở thành một **static field** hay mọi Calculator ở mọi lần chạy method đều dùng một ô nhớ local có thể sửa chung. Java chỉ bảo đảm hành vi capture theo ngôn ngữ; chi tiết compiler lưu giá trị capture như thế nào không phải hợp đồng API mà ứng dụng cần phụ thuộc.

## 4. `final` và `effectively final`: định nghĩa dễ áp dụng

`final` được viết rõ:

~~~java
final int limit = 5;
final String label = "Java";
~~~

Biến đã khởi tạo như trên **không thể gán lại** theo các quy tắc của Java. Còn:

~~~java
int limit = 5;
String label = "Java";
~~~

hai biến **không** có modifier `final`, nhưng có thể được coi là effectively final nếu những lần sử dụng/phép gán trong phạm vi tiếp theo đáp ứng quy tắc JLS: chúng không bị gán lại sau khởi tạo. Với biến local chưa có initializer, Java cho phép những mẫu gán một lần phù hợp với *definite assignment* mà vẫn effectively final.

Các thao tác dễ làm mất điều kiện effectively final:

~~~java
int number = 5;
number = 6;       // Gán lại.
number++;         // Phép tăng là một cập nhật biến.
number += 2;      // Compound assignment cập nhật biến.
~~~

Đây là một **đoạn minh họa hợp lệ nếu đứng riêng**, nhưng sau các cập nhật ấy, `number` **không còn effectively final** theo nghĩa có thể được capture từ local class. Java không xét “giá trị cuối vẫn là 5 hay đã đổi thật” bằng phân tích mục đích nghiệp vụ; compiler xét quy tắc assignment.

Một biến đã khai báo `final` không cho những phép cập nhật ấy sau khi nó được khởi tạo. Khi cần thay đổi dữ liệu có ý nghĩa, hãy tạo **biến kết quả mới**, hoặc thiết kế state mutable có quyền sở hữu rõ ràng thay vì cố gán lại biến được capture.

## 5. Vì sao Java ràng buộc capture như vậy?

Biến local bình thường có vòng đời theo **mỗi lần gọi method/block**. Trong khi đó, một local-class object có thể được trả ra khỏi method và sống lâu hơn lần gọi ấy.

~~~text
Gọi method makeTask(...)
    |
    | tạo local variable text
    | khai báo local class Task sử dụng text
    | tạo Task object
    v
method trả về Task dưới interface Runnable
    |
    | stack frame của makeTask kết thúc
    v
Task.run() vẫn cần giá trị text đã được capture
~~~

Nếu mã nguồn cho phép gán đi gán lại biến local như một state liên kết tự động với object đã thoát khỏi method, sẽ xuất hiện những vấn đề về vòng đời/quan sát và race rất khó giải thích. Yêu cầu final/effectively final giúp hành vi capture của Java rõ ràng: local class dùng **giá trị được capture**, không phải một ô biến local có thể được gán lại sau này.

Đừng suy từ sơ đồ rằng JVM bắt buộc tạo đúng một field với tên cụ thể hoặc một object wrapper nào đó. Compiler có quyền dùng chiến lược triển khai hợp lệ; Java Language Specification quyết định **hành vi và tính hợp lệ của chương trình**, không hứa hình dạng bytecode cho mọi compiler.

## 6. Chương trình hoàn chỉnh 2 — object sống lâu hơn lần gọi method

Tạo tệp **`EscapingLocalClassDemo.java`**:

~~~java
public class EscapingLocalClassDemo {
    static Runnable makeTask(String user) {
        int attempt = 3;

        class GreetingTask implements Runnable {
            @Override
            public void run() {
                System.out.println("user=" + user
                        + ",attempt=" + attempt);
            }
        }

        return new GreetingTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("An");
        Runnable second = makeTask("Binh");

        first.run();
        second.run();
        first.run();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 EscapingLocalClassDemo.java
java EscapingLocalClassDemo
~~~

**Stdout:**

~~~text
user=An,attempt=3
user=Binh,attempt=3
user=An,attempt=3
~~~

`GreetingTask` là một local class nằm trong **static method** `makeTask`; điều đó không cản nó capture `user` và `attempt`, vì đây là parameters/locals của lần gọi method chứ không phải instance fields của một enclosing object.

Mỗi lần gọi `makeTask` có **bộ giá trị nguồn riêng**, nên `first` nhớ An còn `second` nhớ Binh. Sau khi method trả về, các `Runnable` vẫn hoạt động. Không cần cho `attempt` trở thành biến static; cũng không cần cấp phát một enclosing instance chỉ để giữ giá trị local đã capture.

## 7. Capture tham số method cũng cần effectively final

Tham số của method hay constructor về bản chất cũng là những biến có scope giới hạn. Khi local class đọc một **method parameter**, quy tắc `final` hoặc `effectively final` áp dụng.

~~~java
static Runnable makeMessage(String message) {
    class Printer implements Runnable {
        @Override
        public void run() {
            System.out.println(message);
        }
    }

    return new Printer();
}
~~~

Đây là **method minh họa hợp lệ** khi đặt trong một class Java. Tham số `message` không được gán lại trong method nên effectively final.

Nếu thêm:

~~~java
// Minh họa CỐ Ý KHÔNG HỢP LỆ khi ghép vào method trên:
// message = message.trim();
~~~

method sẽ không biên dịch nếu phần thân local class còn tham chiếu `message`. Phép gán ấy làm tham số không còn effectively final, kể cả bạn thực hiện gán **trước** khi tạo Printer và cho rằng Printer chỉ cần giá trị sau cùng.

Muốn chuẩn hóa đầu vào, hãy tạo một **local value mới**:

~~~java
static Runnable makeTrimmedMessage(String message) {
    String normalized = message.trim();

    class Printer implements Runnable {
        @Override
        public void run() {
            System.out.println(normalized);
        }
    }
    return new Printer();
}
~~~

Đây là method minh họa hợp lệ khi đặt trong class; `normalized` chỉ được gán một lần, nên capture được. Việc `message.trim()` yêu cầu message khác null là một điều kiện input riêng.

## 8. Chương trình hoàn chỉnh 3 — capture tham số và dữ liệu đã chuẩn hóa

Tạo tệp **`ParameterCaptureDemo.java`**:

~~~java
public class ParameterCaptureDemo {
    static Runnable printRepeated(String raw, int count) {
        if (raw == null || count < 0) {
            throw new IllegalArgumentException("invalid input");
        }

        String normalized = raw.trim();

        class MessagePrinter implements Runnable {
            @Override
            public void run() {
                StringBuilder builder = new StringBuilder();
                for (int i = 0; i < count; i++) {
                    builder.append(normalized).append("!");
                }
                System.out.println(builder);
            }
        }

        return new MessagePrinter();
    }

    public static void main(String[] args) {
        Runnable first = printRepeated(" Hi ", 2);
        Runnable second = printRepeated(" Java ", 1);

        first.run();
        second.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ParameterCaptureDemo.java
java ParameterCaptureDemo
~~~

**Stdout:**

~~~text
Hi!Hi!
Java!
~~~

`raw`, `count` và `normalized` không bị gán lại. Local class chỉ thực sự sử dụng `count` và `normalized`, nên đây là hai biến được capture. `raw` được method dùng để chuẩn hóa trước khi tạo object; không cần capture trực tiếp.

Biến `i` trong method `run()` **không được capture từ phạm vi ngoài**: nó là loop variable cục bộ của chính `run()`. Nó có thể tăng trong vòng lặp bình thường, vì ràng buộc effectively final đang bàn chỉ phát sinh khi một biến local/parameter bị **tham chiếu từ phần thân local/inner class khác hoặc lambda**.

## 9. Gán lại biến trước hay sau local class đều là vấn đề

Một ngộ nhận: “Miễn tôi gán lại biến trước `new Task()` thì chắc capture được.” Không đúng. Compiler xem **cách biến được gán trong phạm vi liên quan**, không dựa vào thứ tự chạy mà bạn tưởng là an toàn.

Đoạn **cố ý không biên dịch**:

~~~java
public class InvalidReassignmentExample {
    public static void main(String[] args) {
        int number = 1;
        number = 2;

        class Show {
            void print() {
                System.out.println(number); // compile-time error
            }
        }

        new Show().print();
    }
}
~~~

Lỗi ở `number`: đã được gán initializer 1 rồi gán lại 2, nên không effectively final. Việc bản thân local class không viết `number = ...` **không cứu được** biến đã bị gán lại ở enclosing method.

Một đoạn **cũng cố ý không biên dịch**:

~~~java
public class InvalidLaterAssignmentExample {
    public static void main(String[] args) {
        int number = 1;

        class Show {
            void print() {
                System.out.println(number); // compile-time error
            }
        }

        number = 2;
        new Show().print();
    }
}
~~~

Dù phép gán thứ hai nằm **sau khai báo class**, việc này vẫn phá effectively final. Cả hai khối code được đánh dấu **ví dụ lỗi biên dịch**, không phải demo được yêu cầu chạy.

**Cách sửa:** giữ biến capture không bị gán lại và chuyển kết quả vào biến tên khác, hoặc dùng một state holder có chính sách mutation rõ nếu ứng dụng thực sự cần state thay đổi.

## 10. Chương trình hoàn chỉnh 4 — tính giá trị mới trong biến khác

Tạo tệp **`NewLocalValueDemo.java`**:

~~~java
public class NewLocalValueDemo {
    public static void main(String[] args) {
        int original = 4;
        int doubled = original * 2;

        class Printer {
            String describe() {
                return "original=" + original
                        + ",doubled=" + doubled;
            }
        }

        Printer printer = new Printer();
        System.out.println(printer.describe());
        System.out.println("sum=" + (original + doubled));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NewLocalValueDemo.java
java NewLocalValueDemo
~~~

**Stdout:**

~~~text
original=4,doubled=8
sum=12
~~~

Các local variables `original` và `doubled` chỉ được gán một lần và được capture. Nếu mục tiêu là tính một giá trị khác, `int doubled = original * 2` thường rõ nghĩa hơn `original *= 2` rồi cố sử dụng `original` trong local class.

Đây là phương pháp rất hữu ích khi chuẩn hóa input, tính giá trị cấu hình, tạo callback và truyền behavior sang API khác: **biến kết quả mới vừa rõ ý vừa bảo toàn điều kiện capture**.

## 11. Biến `final` không đồng nghĩa object bất biến

Xét:

~~~java
final StringBuilder buffer = new StringBuilder("A");
buffer.append("B");
~~~

Hai câu lệnh này **hợp lệ**. Modifier `final` cấm viết `buffer = new StringBuilder("C")` sau khởi tạo, nhưng vẫn cho `append` sửa **chính StringBuilder đã tham chiếu**.

Tương tự:

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>();
names.add("An");
~~~

Nếu biến `names` không bị **gán lại**, nó có thể effectively final; việc `names.add(...)` thay đổi trạng thái list không phải phép gán lại biến `names`.

Phân biệt ba tầng:

| Tầng | Ví dụ | Điều gì có thể đổi? |
| --- | --- | --- |
| Local variable/reference | `builder = anotherBuilder` | Biến `builder` trỏ sang object khác |
| Object được tham chiếu | `builder.append("X")` | Nội dung của StringBuilder cũ |
| Trạng thái của local-class object | `task.times++` bên trong Task | Field riêng của Task |

Quy tắc final/effectively final quản lý **tầng biến được capture**. Nó **không** đóng băng object graph hoặc cấm mọi state mutation ở nơi khác.

## 12. Chương trình hoàn chỉnh 5 — capture reference, mutate object

Tạo tệp **`MutableReferenceCaptureDemo.java`**:

~~~java
public class MutableReferenceCaptureDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");

        class Reporter {
            void show() {
                System.out.println("text=" + builder);
            }
        }

        Reporter reporter = new Reporter();
        reporter.show();

        builder.append("B");
        reporter.show();

        builder.append("C");
        reporter.show();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 MutableReferenceCaptureDemo.java
java MutableReferenceCaptureDemo
~~~

**Stdout chính xác:**

~~~text
text=A
text=AB
text=ABC
~~~

Biến `builder` vẫn trỏ tới **cùng object**, nên nó effectively final. Các lệnh `append` sửa state của StringBuilder ấy; `Reporter` quan sát nội dung thay đổi.

**Không có mâu thuẫn** với capture: local class không đọc “một local variable đã bị gán lại”. Nó đang giữ giá trị reference tới object mà state bên trong có thể đổi.

Cách này có thể hữu ích trong một mô hình state holder, nhưng cũng có thể gây **aliasing**: nhiều nơi cùng sửa object mà Reporter nắm giữ. Nếu yêu cầu một ảnh chụp dữ liệu bất biến, hãy tạo `String snapshot = builder.toString()` rồi capture `snapshot` thay vì capture chính StringBuilder.

## 13. Snapshot giá trị khác với chia sẻ một mutable holder

Một local class capture `int count = 5` có một giá trị primitive không đổi theo quy tắc capture. Còn nếu capture `int[] state = {5}`, thứ được capture là **reference tới array**; caller vẫn có thể gán `state[0] = 9`.

Sơ đồ:

~~~text
Local variable state (reference không bị gán lại)
         |
         v
      int[] A [5]        <-- sau đó sửa A[0] thành 9
         ^
         |
 Local-class object dùng cùng reference tới A
~~~

Muốn local class quan sát **giá trị thời điểm tạo**, hãy lưu primitive/string immutable đã được snapshot. Muốn nó quan sát **state đang đổi**, hãy dùng một holder được quản lý có chủ đích. Đặc biệt nếu nhiều threads truy cập holder, cần cơ chế đồng bộ thích hợp.

## 14. Chương trình hoàn chỉnh 6 — primitive snapshot và array mutable

Tạo tệp **`CapturedArrayDemo.java`**:

~~~java
public class CapturedArrayDemo {
    public static void main(String[] args) {
        int snapshot = 5;
        int[] mutableCell = {5};

        class Reader {
            void print() {
                System.out.println("snapshot=" + snapshot
                        + ",cell=" + mutableCell[0]);
            }
        }

        Reader reader = new Reader();
        reader.print();

        mutableCell[0] = 9;
        reader.print();

        mutableCell[0] = 12;
        reader.print();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 CapturedArrayDemo.java
java CapturedArrayDemo
~~~

**Stdout:**

~~~text
snapshot=5,cell=5
snapshot=5,cell=9
snapshot=5,cell=12
~~~

`snapshot` là primitive local effectively final: luôn 5 trong chương trình. `mutableCell` cũng effectively final ở **mức biến reference**, nhưng array object đổi lần lượt từ 5 sang 9 rồi 12.

Không nên “lách luật effectively final” bằng cách bọc mọi biến trong mảng một phần tử rồi cập nhật tùy tiện. Cách đó có thể hợp lệ về cú pháp, nhưng **giấu mutable state**, làm code khó hiểu, đặc biệt với callback hoặc concurrency. Nếu cần state, đặt tên một type/holder có invariant và ownership rõ.

## 15. Blank `final`: gán một lần theo luồng điều khiển

Biến final **không nhất thiết có initializer ngay tại declaration**. Một **blank final local** có thể được gán sau khai báo theo các đường điều khiển thích hợp, miễn compiler chứng minh được definite assignment trước khi dùng và không có gán lại trái phép.

~~~java
final int fee;
boolean premium = true;

if (premium) {
    fee = 20;
} else {
    fee = 5;
}

class Receipt {
    int total(int base) {
        return base + fee;
    }
}
~~~

Đây là đoạn Java minh họa hợp lệ nếu đặt trong một method. `fee` được gán đúng một lần trên mỗi execution path, nên `Receipt` có thể tham chiếu nó. Từ khóa `final` không có nghĩa phải viết một giá trị hard-coded trong mọi trường hợp.

Một biến local không khai báo `final` nhưng có cách gán tương tự cũng **có thể effectively final** nếu đáp ứng quy tắc JLS (bao gồm các điều kiện về definite/unassignment). Đừng suy rằng mọi assignment trong nhánh `if` tự làm mất effectively final.

## 16. Chương trình hoàn chỉnh 7 — final và effectively final sau `if`

Tạo tệp **`ConditionalCaptureDemo.java`**:

~~~java
public class ConditionalCaptureDemo {
    public static void main(String[] args) {
        boolean premium = true;

        final int fixedFee;
        if (premium) {
            fixedFee = 20;
        } else {
            fixedFee = 5;
        }

        int discount;
        if (premium) {
            discount = 3;
        } else {
            discount = 0;
        }

        class Receipt {
            int total(int base) {
                return base + fixedFee - discount;
            }
        }

        Receipt receipt = new Receipt();
        System.out.println("fee=" + fixedFee);
        System.out.println("discount=" + discount);
        System.out.println("total=" + receipt.total(100));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConditionalCaptureDemo.java
java ConditionalCaptureDemo
~~~

**Stdout chính xác:**

~~~text
fee=20
discount=3
total=117
~~~

`fixedFee` là blank final. `discount` không khai báo final, nhưng mỗi đường `if/else` gán nó đúng một lần trước khi capture, và không có lệnh gán lại sau đó: trong ví dụ nó được phép capture với tư cách effectively final.

Nếu một nhánh không khởi tạo `discount` và code vẫn sử dụng nó, đó là **vấn đề definite assignment** riêng. Compiler cần biết biến có giá trị trên mọi đường đi tới chỗ đọc, bất kể vấn đề effectively final.

## 17. Vòng `for` thường: index thay đổi nên không effectively final

Vòng lặp chỉ số thông thường:

~~~java
for (int i = 0; i < 3; i++) {
    // i bị cập nhật bởi i++.
}
~~~

Biến `i` được tăng theo iteration nên **không effectively final**. Nếu một local class trong loop body cố truy cập trực tiếp `i` và object ấy có thể được giữ lại, compiler từ chối:

~~~java
// ĐOẠN CỐ Ý KHÔNG BIÊN DỊCH khi bỏ chú thích lỗi:
for (int i = 0; i < 3; i++) {
    class InvalidTask {
        void run() {
            // System.out.println(i);
            // i không effectively final do i++ trong for.
        }
    }
}
~~~

Mẫu đúng là khai báo **biến snapshot mới trong mỗi lượt lặp**:

~~~java
for (int i = 0; i < 3; i++) {
    int capturedIndex = i;

    class Task {
        void run() {
            System.out.println(capturedIndex);
        }
    }

    new Task().run();
}
~~~

Mỗi lần chạy body của loop có một local `capturedIndex` được khởi tạo từ giá trị `i` hiện tại, rồi không gán lại. Nó effectively final và được local class dùng hợp lệ.

**Chú ý:** điều này khác với việc chỉ ghi `final int capturedIndex = i;` về hiệu lực capture; cả explicit final và effectively final đều hợp lệ. Đặt `final` có thể giúp nhấn mạnh chủ ý nhưng không phải lúc nào cũng bắt buộc.

## 18. Chương trình hoàn chỉnh 8 — mỗi vòng lặp giữ đúng chỉ số

Tạo tệp **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            int capturedIndex = i;

            class IndexTask implements Runnable {
                @Override
                public void run() {
                    System.out.println("index=" + capturedIndex);
                }
            }

            tasks.add(new IndexTask());
        }

        System.out.println("task count=" + tasks.size());
        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

**Stdout:**

~~~text
task count=3
index=0
index=1
index=2
~~~

Các tasks chạy **sau khi vòng tạo tasks đã kết thúc**. Mỗi task vẫn ghi đúng chỉ số của lượt lặp tạo ra mình, nhờ mỗi biến `capturedIndex` có giá trị riêng, đủ điều kiện capture.

Sai lầm thường gặp là muốn tất cả tasks tham chiếu trực tiếp cùng biến `i` đang tăng trong for. Java không cho capture biến ấy ở local/inner class, tránh một lớp bug phổ biến từ những ngôn ngữ có semantics capture khác.

## 19. Enhanced `for`: biến phần tử có quy tắc thuận lợi hơn

Với enhanced for:

~~~java
for (String word : java.util.List.of("A", "B")) {
    class Printer {
        void run() {
            System.out.println(word);
        }
    }
    new Printer().run();
}
~~~

Đây là một đoạn Java hợp lệ khi đặt trong method. Biến `word` của enhanced-for được khai báo cho các lần lặp theo quy tắc ngôn ngữ, và nếu bạn không gán lại nó trong body, có thể capture từ local class.

Khác với `i++` trong basic for, ở đây không có phép cập nhật biến `word` bằng code của bạn. Nhưng nếu bạn viết `word = word.toLowerCase();` trong body, biến đó không còn đáp ứng effectively final cho capture.

Một local class vẫn có thể capture **giá trị reference tới phần tử mutable** trong enhanced for; nếu phần tử là mutable object, thay đổi bên trong object vẫn có thể nhìn thấy ở các tasks tương ứng.

## 20. Chương trình hoàn chỉnh 9 — capture phần tử enhanced-for

Tạo tệp **`EnhancedForCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class EnhancedForCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (String word : List.of("Java", "Core")) {
            class WordTask implements Runnable {
                @Override
                public void run() {
                    System.out.println("word=" + word);
                }
            }
            tasks.add(new WordTask());
        }

        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnhancedForCaptureDemo.java
java EnhancedForCaptureDemo
~~~

**Stdout:**

~~~text
word=Java
word=Core
~~~

Cả hai WordTask objects được gọi **sau loop**, nhưng vẫn đọc giá trị tương ứng của mỗi lượt enhanced for. Vì String immutable, không có rủi ro một thread khác sửa bên trong object String đang được tham chiếu.

Đừng khái quát rằng mọi biến xuất hiện trong vòng lặp đều được capture. Hãy nhìn biến **có bị gán lại không**, nó được khai báo ở **scope nào**, và compiler có xác định nó được khởi tạo đúng cách không.

## 21. Phạm vi tên của local class: được dùng ở đâu?

Tên một local class chỉ có phạm vi theo **block** chứa declaration và các quy tắc lexical scope, không trở thành một member type có thể viết `Outer.LocalType` từ mọi nơi.

~~~java
class Processor {
    Runnable create() {
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println("work");
            }
        }
        return new Task();
    }
}
~~~

Đây là class minh họa hợp lệ. Một caller có thể giữ kết quả dưới `Runnable`, nhưng **không thể** ở một class khác khai báo `Processor.Task task` như với static nested class, vì `Task` không phải member type của Processor.

Muốn công bố khả năng sử dụng, trả một **interface hoặc superclass phù hợp**. Nếu caller cần biết concrete class, xét chuyển nó thành member nested class hoặc top-level class với visibility rõ.

Một local class có thể được dùng nhiều lần **bên trong scope hợp lệ**, nhưng tên ấy không được công bố vào API bên ngoài method.

## 22. Chương trình hoàn chỉnh 10 — trả về interface, giấu local type

Tạo tệp **`LocalStrategyDemo.java`**:

~~~java
interface IntOperation {
    int apply(int value);
}

public class LocalStrategyDemo {
    static IntOperation adding(int delta) {
        class AddOperation implements IntOperation {
            @Override
            public int apply(int value) {
                return value + delta;
            }
        }

        return new AddOperation();
    }

    public static void main(String[] args) {
        IntOperation add7 = adding(7);
        IntOperation add2 = adding(2);

        System.out.println("add7 to 3=" + add7.apply(3));
        System.out.println("add7 to 5=" + add7.apply(5));
        System.out.println("add2 to 3=" + add2.apply(3));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalStrategyDemo.java
java LocalStrategyDemo
~~~

**Stdout chính xác:**

~~~text
add7 to 3=10
add7 to 5=12
add2 to 3=5
~~~

`AddOperation` chỉ là implementation trong body của `adding`. Caller sử dụng interface `IntOperation`, không cần và cũng không thấy tên kiểu local ngoài scope.

Tham số `delta` được capture vì không bị gán lại. Mỗi lần gọi `adding` tạo một local-class object nhớ giá trị delta tương ứng.

**Khi nào nên dùng?** Khi behavior cần nhiều methods, state hoặc cấu trúc rõ hơn một lambda đơn giản, local class có thể tốt. Khi chỉ cần một method của functional interface với ít code, lambda thường ngắn gọn hơn. Đừng ép local class vào tất cả callbacks chỉ để minh họa capture.

## 23. `this` của local class không phải `this` của enclosing object

Nếu local class nằm trong instance method của một Outer class:

- `this` trong method của **local class** là instance local class.
- `Outer.this` trong ngữ cảnh inner/local class có enclosing Outer instance phù hợp là **Outer object**.
- Private members của Outer có thể được truy cập theo rules, nhưng nếu tên bị field cục bộ che, cần qualified reference.
- Biến local và parameter của method không phải **fields của Outer** và không truy cập qua `Outer.this.localVariable`.

Ví dụ:

~~~java
class Host {
    private String label = "outer";

    Runnable create() {
        int number = 2;

        class Task implements Runnable {
            private String label = "local";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Host.this.label);
                System.out.println(number);
            }
        }

        return new Task();
    }
}
~~~

Đây là class minh họa hợp lệ; local variable `number` được capture, còn `Host.this.label` là đọc instance field của enclosing Host object, một cơ chế **khác**.

## 24. Chương trình hoàn chỉnh 11 — shadowing và `Outer.this`

Tạo tệp **`LocalThisAndOuterDemo.java`**:

~~~java
final class Host {
    private final String label;

    Host(String label) {
        this.label = label;
    }

    Runnable create(String name) {
        int length = name.length();

        class Task implements Runnable {
            private final String label = "LOCAL";

            @Override
            public void run() {
                System.out.println("local=" + this.label);
                System.out.println("host=" + Host.this.label);
                System.out.println("argument=" + name);
                System.out.println("length=" + length);
            }
        }

        return new Task();
    }
}

public class LocalThisAndOuterDemo {
    public static void main(String[] args) {
        Host host = new Host("H");
        host.create("AB").run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocalThisAndOuterDemo.java
java LocalThisAndOuterDemo
~~~

**Stdout:**

~~~text
local=LOCAL
host=H
argument=AB
length=2
~~~

Trong Task, `this.label` là field của local-class object; `Host.this.label` là private field của Host được gắn với local class instance vì nó được tạo trong instance context.

`name` là method parameter và `length` là local variable: chúng được capture vì effectively final. Không thể dùng `Host.this.length`, vì `length` không phải field của Host.

Nếu tạo local class trong một **static method**, không có `Host.this` ở đó; tuy nhiên local class vẫn có thể capture các locals/parameters effectively final của static method.

## 25. Local class trong static method vẫn capture local variables

Một local class **không cần enclosing instance** để dùng effectively final variables từ static method:

~~~java
class Tasks {
    private static final String PREFIX = "task:";

    static Runnable build(String label) {
        int version = 17;

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        PREFIX + label + "/" + version);
            }
        }

        return new Task();
    }
}
~~~

Đây là class minh họa hợp lệ. `Task` có thể truy cập `PREFIX` (static field), `label` (parameter được capture) và `version` (local được capture).

Nhưng nếu code của Task cần một instance field `Tasks.owner` của một Tasks object cụ thể, nó phải có reference phù hợp. **Quy tắc effectively final không tạo ra một enclosing object** và không làm instance members thành static.

## 26. Generic method: local class có thể sử dụng kiểu `T` của method

Một local class có thể được khai báo trong generic method và sử dụng type parameter có scope phù hợp, khác với static nested **member** class vốn không tự thừa hưởng type parameter của enclosing generic class.

~~~java
class Factory {
    static <T> java.util.function.Supplier<T> fixed(T value) {
        class Holder implements java.util.function.Supplier<T> {
            @Override
            public T get() {
                return value;
            }
        }
        return new Holder();
    }
}
~~~

Đây là code Java hợp lệ. `Holder` là local class trong generic method, được phép dùng `T` thuộc lexical scope của method. Nó capture tham số `value` vì tham số không bị gán lại.

Do Java generics sử dụng **type erasure**, không suy rằng mỗi `T` tạo một runtime class khác. Ta phân tích hành vi typed references theo static type rules.

## 27. Chương trình hoàn chỉnh 12 — generic local class và capture `T`

Tạo tệp **`GenericLocalClassDemo.java`**:

~~~java
import java.util.function.Supplier;

public class GenericLocalClassDemo {
    static <T> Supplier<String> describe(T value) {
        String prefix = "got:";

        class Description implements Supplier<String> {
            @Override
            public String get() {
                return prefix + value;
            }
        }

        return new Description();
    }

    public static void main(String[] args) {
        Supplier<String> text = describe("java");
        Supplier<String> number = describe(42);

        System.out.println(text.get());
        System.out.println(number.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 GenericLocalClassDemo.java
java GenericLocalClassDemo
~~~

**Stdout chính xác:**

~~~text
got:java
got:42
~~~

Ở method `describe(T value)`, parameter `value` và local `prefix` effectively final; local class được phép dùng cả hai. Biểu thức nối String `prefix + value` sử dụng cơ chế chuyển object sang chuỗi của Java; trong demo, String và Integer có kết quả xác định.

Một kiểu local có thể phức tạp hơn nếu khai báo riêng type parameters, nhưng đối với bài capture, quan trọng là **các tên kiểu trong scope** và **điều kiện gán lại của biến được capture**.

## 28. Local class so với lambda và anonymous class

Local class, anonymous class và lambda cùng có thể tham chiếu locals/parameters effectively final từ phạm vi chứa. Tuy nhiên **không đồng nhất chúng**:

| Cơ chế | Local class | Anonymous class | Lambda |
| --- | --- | --- | --- |
| Có tên class trong block? | Có | Không | Không khai báo class body mang tên |
| Tạo implementation của interface? | Có | Có | Có nếu target là functional interface |
| Capture local/parameter | Final/effectively final | Final/effectively final | Final/effectively final |
| `this` trong thân behavior | Local-class instance | Anonymous-class instance | `this` của lexical enclosing context |
| Có thể có nhiều methods riêng | Có | Có trong giới hạn loại anonymous class | Không định nghĩa một class với nhiều methods |
| Có thể return dưới interface | Có | Có | Có |
| Cần lưu ý `Outer.this` | Có khi enclosing instance phù hợp | Có khi enclosing instance phù hợp | Dùng theo lexical context |

Chọn theo độ phức tạp: local class thích hợp khi cần type có **tên trong một block** và một implementation đáng kể; lambda thích hợp cho behavior ngắn của functional interface; anonymous class khi cần instance body riêng nhưng không cần tên type.

Không cố viết `this` trong lambda như thể `this` là một object lambda mới. Cũng không dựa vào class name do JVM sinh cho lambda như một API ổn định.

## 29. Chương trình hoàn chỉnh 13 — local class, anonymous class và lambda

Tạo tệp **`ThreeCaptureFormsDemo.java`**:

~~~java
public class ThreeCaptureFormsDemo {
    public static void main(String[] args) {
        String word = "Java";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("local=" + word);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" + word);
            }
        };

        Runnable lambda =
                () -> System.out.println("lambda=" + word);

        new LocalTask().run();
        anonymous.run();
        lambda.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ThreeCaptureFormsDemo.java
java ThreeCaptureFormsDemo
~~~

**Stdout:**

~~~text
local=Java
anonymous=Java
lambda=Java
~~~

`word` effectively final nên cả ba hình thức đều dùng được. Nếu thêm `word = "Other";` trong method, compiler không cho ba phần thân behavior tham chiếu `word` theo quy tắc capture.

Ví dụ cố tình không quan sát `this` hay identity của lambda để tránh nhầm đó là yếu tố giải thích điều kiện final/effectively final. Sự khác biệt về `this` sẽ quan trọng khi body thật sự truy cập enclosing instance.

## 30. Capture không phải cơ chế đồng bộ đa luồng

Việc compiler cho capture một reference effectively final **không đồng nghĩa object đích thread-safe**:

~~~java
java.util.List<String> shared =
        new java.util.ArrayList<>();

class Task implements Runnable {
    @Override
    public void run() {
        shared.add("x");
    }
}
~~~

Đây là **đoạn class minh họa trong method**, hợp lệ nếu biến `shared` nằm trong scope và không bị gán lại. Nó không tự bảo đảm an toàn khi nhiều threads cùng gọi `run()` trên các tasks hoặc cùng sửa ArrayList.

Một số điều cần tách:

- Biến `shared` được capture **dưới dạng reference value**; bản thân nó effectively final.
- Object `ArrayList` vẫn mutable và các thao tác của nó không tự đồng bộ.
- Đọc/ghi dữ liệu giữa threads cần thỏa Java Memory Model; một local class không tự cung cấp lock.
- Nếu chỉ cần snapshot bất biến, có thể capture `List.copyOf(source)` với elements bất biến theo hợp đồng.
- Nếu cần shared counters, dùng `AtomicInteger`, synchronization hoặc công cụ concurrency phù hợp.

Với một `AtomicInteger`, biến reference giữ nó có thể final/effectively final, trong khi `incrementAndGet()` thay **state của AtomicInteger** an toàn theo hợp đồng concurrency API.

## 31. Chương trình hoàn chỉnh 14 — capture `AtomicInteger` có chủ đích

Tạo tệp **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();

        class IncrementTask implements Runnable {
            @Override
            public void run() {
                counter.incrementAndGet();
            }
        }

        Thread first = new Thread(new IncrementTask());
        Thread second = new Thread(new IncrementTask());

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("counter=" + counter.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Stdout chính xác sau khi hai threads `join()` thành công:**

~~~text
counter=2
~~~

`counter` effectively final vì reference không gán lại, nhưng object AtomicInteger vẫn cập nhật được. `incrementAndGet` thực hiện cập nhật atomic theo API. Hai threads có thể chạy theo thứ tự khác nhau, song sau khi `join()` hoàn tất, mỗi thread đã tăng một lần; giá trị in ra là 2.

**Không dùng kết quả này để kết luận** capture của biến reference làm mọi mutable object thread-safe. Sự an toàn ở đây đến từ **AtomicInteger** và trình tự đợi thread kết thúc, không đến từ việc local class được phép capture.

## 32. Lỗi phổ biến: dùng array một phần tử để “qua mặt” final

Một lối viết thỉnh thoảng gặp:

~~~java
int[] result = {0};

class Counter {
    void increment() {
        result[0]++;
    }
}
~~~

Đoạn code này hợp lệ trong một method. Vì reference biến `result` không bị gán lại, nó effectively final; còn phần tử mảng vẫn thay đổi.

Nhưng nó thường khó đọc và không thể thay thế đúng nghĩa cho một thiết kế state:

- `result[0]` che giấu rằng đây là một state container.
- Không có invariant hay method diễn đạt ý nghĩa của trạng thái.
- Nếu nhiều tasks giữ cùng array, chúng cùng chia sẻ mutation.
- `result[0]++` **không atomic**, nên dùng đa luồng có thể mất updates.
- Với một API callback kéo dài, object state rõ ràng hoặc lớp concurrency phù hợp thường dễ bảo trì hơn.

Nên tạo một class có trách nhiệm rõ (`Counter`, `Progress`) hoặc dùng `AtomicInteger` khi đúng yêu cầu. Nếu chỉ cần một giá trị tính xong, **tạo local result mới trước khi capture** sẽ đơn giản hơn.

## 33. Shadowing không làm mất quyền truy cập nhưng đổi tên được chọn

Nếu local class có field trùng tên với biến trong method, **name resolution** có thể khiến tên đơn giản trỏ vào field của local class chứ không phải local variable ngoài. Vì Java không có cú pháp “`MethodName.this.localVariable`”, tốt nhất **tránh dùng cùng tên** nếu cần cả hai.

Ví dụ:

~~~java
class Parent {
    private int level = 10;

    void method() {
        int localLevel = 5;

        class Child {
            private int level = 20;

            void print() {
                System.out.println(level);
                System.out.println(this.level);
                System.out.println(Parent.this.level);
                System.out.println(localLevel);
            }
        }

        new Child().print();
    }
}
~~~

Đây là định nghĩa hợp lệ. `level` trỏ field của Child (20), `Parent.this.level` trỏ private field của Parent (10), `localLevel` trỏ local variable của method (5).

Nếu khai báo một local variable cũng có tên `level`, field Child có thể che tên ấy trong body của Child; bạn **không thể** đơn giản viết `Parent.this.level` để lấy local variable vì `Parent.this.level` luôn là **field của Parent**. Dùng tên khác giúp phân biệt rõ hơn.

## 34. Definite assignment là điều kiện riêng với effectively final

Một biến có thể chưa bị gán lại nhưng vẫn **chưa được khởi tạo trên mọi đường chạy** trước khi local class đọc nó. Java phân tích *definite assignment*:

~~~java
// ĐOẠN CỐ Ý KHÔNG BIÊN DỊCH:
void bad(boolean condition) {
    int value;
    if (condition) {
        value = 5;
    }

    class Printer {
        void print() {
            System.out.println(value); // chưa definitely assigned
        }
    }
}
~~~

Nếu `condition` false, `value` chưa có giá trị. Vì thế compiler không cho đọc nó trong Printer, dù không có đoạn code nào đang gán lại sau khi Printer được khai báo.

Sửa bằng cách cho mọi đường control flow gán một lần:

~~~java
void good(boolean condition) {
    int value;
    if (condition) {
        value = 5;
    } else {
        value = 0;
    }

    class Printer {
        void print() {
            System.out.println(value);
        }
    }

    new Printer().print();
}
~~~

Đoạn **method hợp lệ** khi đặt trong một class. `value` vừa definitely assigned trước khi đọc, vừa effectively final.

Có ba phép kiểm tra khác nhau: **biến còn trong scope không**, **đã được gán trước khi dùng chưa**, và **có đáp ứng final/effectively final để capture không**. Mỗi phép kiểm tra có thể dẫn tới một lỗi biên dịch riêng.

## 35. Câu hỏi về performance và thiết kế

Một local class có thể được dùng để đóng gói behavior gắn với vài biến trong method mà không cần public type. Tuy nhiên:

- Mỗi `new LocalTask()` có thể tạo object riêng theo semantics của `new`.
- Capture các references lớn có thể khiến **object đích còn reachable** chừng nào task còn giữ reference.
- Dùng local class cho một chức năng quá dài làm method khó đọc.
- Trả về local implementation dưới interface giúp che chi tiết nhưng API nên tài liệu hóa contract thật.
- Với callbacks sống lâu, cân nhắc lifecycle, cancellation và quản lý shared mutable state.
- Không tối ưu bằng cách đổi effectively final locals thành mutable arrays khi chưa đo đạc.
- Nếu chỉ truyền một hàm ngắn, lambda có thể giảm boilerplate; nếu cần nhiều methods và state riêng, local class có thể dễ hiểu hơn.

Về memory: **capturing một object reference có thể góp phần giữ object còn reachable**. Từ khóa `final`/effectively final không làm object tự thu hồi sớm. Điều này đặc biệt cần nhớ với callback/listener lưu vào registry sống lâu.

## 36. Bảng lỗi compile-time và hướng sửa

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Local class đọc biến bị gán lại bằng `=` | Không effectively final | Đọc biến snapshot mới được gán một lần |
| Local class đọc biến bị `++` | Không effectively final | Capture bản sao của chỉ số/giá trị |
| Capture tham số đã bị chuẩn hóa bằng phép gán lại | Tham số không effectively final | `String normalized = input.trim()` |
| Dùng biến local có nhánh chưa gán giá trị | Không definitely assigned | Gán giá trị trên mọi đường dùng |
| Muốn `return counter++` trong method local | `counter` local ngoài bị mutate | Thiết kế holder có ownership rõ |
| Capture `for (int i...; i++)` trực tiếp | Index thay đổi theo vòng lặp | `int snapshot = i` trong body |
| Capture enhanced-for variable rồi gán lại nó | Biến iteration không effectively final | Tạo local mới hoặc không gán lại |
| Hiểu `final List` là list immutable | Final khóa reference, không khóa list | Immutable snapshot/defensive copy |
| Dùng ArrayList capture ở nhiều threads | Race ở mutable list | Concurrency API hoặc synchronization |
| Hiểu `this` trong local class là Outer | `this` chỉ local object | `Outer.this` nếu hợp lệ |
| Muốn dùng local class name từ method khác | Local class type ngoài scope | Trả interface hoặc chuyển thành member class |
| Nghĩ `effectively final` áp dụng cho mọi field | Đây là quy tắc capture locals/parameters | Phân biệt fields với locals |
| Capture reference tới builder còn mutable | Các tác vụ chia sẻ mutable state | Snapshot bằng String/immutable DTO nếu cần |
| Sửa biến local sau khi định nghĩa Task nhưng trước run | Capture vẫn không hợp lệ | Không gán lại biến captured |
| Dùng `final` để “tạo thread safety” | Không đồng bộ mutable object | `AtomicInteger`, lock hoặc immutable model |

Không nên chữa lỗi compile bằng cách biến local variable thành một **static field toàn cục**: điều ấy thay đổi dữ liệu từ **riêng một lần gọi method** thành dữ liệu **chia sẻ toàn class**, có thể sinh ra bug concurrency và lifecycle nghiêm trọng hơn lỗi ban đầu.

## 37. Quy trình giải đề về capture local variables

Với câu hỏi “đoạn Java có biên dịch không, và in gì?”, hãy theo thứ tự:

1. Tìm **local class**: nó nằm trong method/block nào?
2. Liệt kê **những biến không phải field của local class** mà body thực sự đọc.
3. Với từng biến, xác định nó là **local variable**, **formal parameter**, **field** hay static member.
4. Với local/parameter, xét scope và *definite assignment*.
5. Xem biến có bị **gán lại, increment/decrement hoặc compound assignment** ở bất kỳ đường liên quan nào không.
6. Nếu thỏa final/effectively final, xác định **giá trị được capture** ở lần gọi method ấy.
7. Nếu biến là reference, vẽ thêm **object được tham chiếu**: có method khác sửa object đó không?
8. Nếu có nhiều lần gọi method, phân biệt mỗi lần gọi có **bộ local values riêng**.
9. Nếu có vòng lặp, phân biệt basic-for index với snapshot của body và enhanced-for iteration variable.
10. Khi local class dùng `this`, phân biệt local-class object với enclosing `Outer.this`.
11. Nếu object chạy sau method kết thúc hoặc ở thread khác, xét lifecycle và concurrency riêng.
12. Sau khi xác minh compiler cho phép, mới tính stdout từng lệnh theo thứ tự chạy.

**Điều quan trọng nhất:** lỗi effectively final là **compile-time**. Không tính một stdout tưởng tượng cho chương trình có lỗi compile-time rồi kết luận “nó sẽ in giá trị cuối”.

## 38. Bài tập tự luyện

**Câu 1.** Biến `int n = 5;` không gán lại sau đó. Local class trong cùng method có được đọc `n` dù không viết `final` không?

**Câu 2.** Nếu thêm `n = 6;` trước khi local class tạo object, câu trả lời thay đổi thế nào?

**Câu 3.** Nếu phép gán lại `n = 6;` nằm **sau** khai báo local class, có giải quyết được lỗi không?

**Câu 4.** `final StringBuilder b = new StringBuilder("A");`, sau đó gọi `b.append("B")`. Biến b còn được local class capture không, và local class thấy nội dung gì?

**Câu 5.** `List<String> list = new ArrayList<>(); list.add("X");`. Việc `add` có tự khiến biến list không effectively final không?

**Câu 6.** Một local class đọc formal parameter `name`. Nếu method viết `name = name.trim()`, có biên dịch không? Viết cách sửa.

**Câu 7.** `final int x;` được gán `x=1` ở nhánh if và `x=2` ở nhánh else. Local class dùng x sau if/else được không?

**Câu 8.** Một biến `int x;` chỉ được gán ở nhánh if, không có else, local class đọc x sau if. Có lỗi gì?

**Câu 9.** Vì sao `for (int i=0;i<3;i++)` không cho local class capture trực tiếp i trong body?

**Câu 10.** Cách làm nào cho phép tạo ba Runnable nhớ lần lượt 0, 1, 2 trong basic for?

**Câu 11.** Enhanced for `for(String word : words)` có thể capture word nếu không gán lại không?

**Câu 12.** Local class tạo trong static method có thể capture locals của static method không?

**Câu 13.** Local class tạo trong instance method có thể đọc `private int field` của enclosing object không? Qua biểu thức nào nếu có trùng tên?

**Câu 14.** `this` bên trong instance method của local class là object nào?

**Câu 15.** Nếu local class trả về dưới interface Runnable, caller có cần biết tên local class để gọi `run()` không?

**Câu 16.** Sau khi method trả về một Runnable được local class tạo, biến local trong stack frame ban đầu không còn được gọi như biến local trực tiếp. Vì sao Runnable vẫn dùng được giá trị capture?

**Câu 17.** Capture `int[] state = {0}` rồi nhiều threads cập nhật `state[0]++`. Việc state effectively final có làm cập nhật atomic không?

**Câu 18.** Capture `AtomicInteger count` rồi dùng `incrementAndGet` có vi phạm effectively final của biến count không?

**Câu 19.** Local class và lambda có cùng quy tắc capture final/effectively final không? `this` có ý nghĩa hoàn toàn giống nhau không?

**Câu 20.** Vì sao có thể là vấn đề nếu một long-lived listener capture một object lớn?

**Câu 21.** Class local bên trong generic method `<T> T process(T input)` có thể dùng `T` trong scope không?

**Câu 22.** Nếu local class body không tham chiếu biến local `x`, việc gán lại x có làm declaration của local class sai về capture không?

**Câu 23.** Tại sao một class có field instance `int total` có thể cập nhật `total++` trong method, trong khi một captured local `int total` không thể bị gán lại?

**Câu 24.** Khi một local class dùng tên `value` trùng giữa field local class và enclosing method, có nhất thiết tên đơn giản tham chiếu local variable ngoài không?

### Đáp án và giải thích

1. Có, `n` effectively final.
2. Không; `n` bị gán lại và mất điều kiện capture.
3. Không; compiler vẫn xét phép gán lại trong phạm vi liên quan.
4. Có. Reference b không bị gán lại; nếu gọi `append` trước khi đọc, local class thấy `"AB"`.
5. Không; `add` mutate object, không gán lại biến local list.
6. Không nếu local class đọc tham số name; dùng `String normalized = name.trim()` và capture normalized.
7. Có, nếu mỗi đường gán đúng một lần và definite assignment thỏa.
8. Biến không definitely assigned trên đường condition=false.
9. Vì `i++` làm i không effectively final.
10. Trong mỗi lượt lặp `int capturedIndex = i;`, rồi local class capture biến snapshot này.
11. Có, theo quy tắc biến iteration của enhanced for khi không bị gán lại.
12. Có, static context không cấm capture local variables/parameters.
13. Có, theo access/enclosing-instance rules; dùng `Outer.this.field` khi cần chỉ rõ receiver.
14. Instance của chính local class.
15. Không; interface Runnable là API bên ngoài, caller chỉ cần `run()`.
16. Các giá trị cần thiết được capture theo semantics Java, không phụ thuộc việc stack frame còn sống.
17. Không. `state[0]++` không atomic, mảng mutable có race.
18. Không. Phép tăng đổi state AtomicInteger, không gán lại biến reference count.
19. Có quy tắc capture tương tự; `this` trong lambda theo lexical enclosing context, khác local/anonymous object.
20. Reference được capture có thể giữ object còn reachable lâu hơn dự kiến.
21. Có, type parameter T thuộc lexical scope thích hợp của generic method.
22. Không, chỉ biến thực sự được tham chiếu từ local class mới liên quan quy tắc capture ấy.
23. Instance field là member state và không phải local variable cần capture; có thể được mutate nếu method/visibility cho phép.
24. Không. Name resolution và shadowing có thể chọn field của local class; đặt tên khác để rõ.

## 39. Checklist trước khi hoàn thành bài thực hành

- Đã chỉ rõ đây là **local class trong block**, không phải static nested member class?
- Tên local class chỉ được dùng trong scope đúng?
- Mỗi captured local/parameter có **final hoặc effectively final**?
- Biến được definitely assigned trước khi body đọc?
- Không có phép gán lại/++/compound assignment lên biến captured?
- Nếu cần tính giá trị mới, đã đặt vào **biến mới** thay vì gán lại biến captured?
- Đã phân biệt **biến reference không đổi** với **object mutable vẫn đổi**?
- Với `List`, array, builder, mutable DTO, đã xác định alias có chủ đích hay không?
- Với vòng basic for, đã snapshot index theo từng iteration?
- Với enhanced for, đã bảo đảm element variable không bị gán lại?
- Nếu local class được trả qua interface, caller không phụ thuộc tên local class ngoài scope?
- Nếu local class có `this`, nó được hiểu là local object?
- Nếu cần enclosing instance, `Outer.this` được dùng trong context hợp lệ?
- Nếu local class ở static method, không giả định có enclosing Outer object?
- Nếu có threads, đã chọn mutable holder/concurrency API phù hợp?
- Đã kiểm tra stdout của các chương trình **biên dịch được**, không dùng output giả định cho code cố ý lỗi?
- Đã thử ít nhất một case method trả local implementation, một case reference mutable và một case loop capture?

## 40. Tài liệu chính thức để đối chiếu (Java 17)

- [JLS 17 §14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): nơi khai báo local class, scope và điều kiện capture.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): định nghĩa final/effectively final variables và assignment.
- [JLS 17 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): quy tắc khởi tạo trước khi đọc.
- [JLS 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi local class và local variables.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): phân giải tên trùng.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing-instance relationship.
- [JLS 17 §15.8.4 — Qualified `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): ý nghĩa `Outer.this`.
- [JLS 17 §15.27.2 — Lambda Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.2): quy tắc capture và lexical context trong lambda.
- [JLS 17 §14.14.2 — Enhanced for Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2): biến iteration của enhanced for.
- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): interface dùng để xuất bản local implementations.
- [Java SE 17 — AtomicInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): ví dụ quản lý state mutable đồng thời có chủ đích.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo snapshot không hỗ trợ mutation ở mức list khi cần capture dữ liệu collection an toàn.

**Kết luận:** local class có thể sử dụng **biến local hoặc tham số** của enclosing scope khi biến ấy là `final` hoặc **`effectively final`** và đã được gán hợp lệ. `effectively final` không cần keyword, chỉ cần cách viết code không gán lại biến theo quy tắc JLS. Khi capture một reference, object được reference vẫn có thể mutable; vì vậy hãy kiểm soát alias, ownership và concurrency riêng. Nếu cần một giá trị được tính qua nhiều bước, đặt **kết quả hoàn chỉnh vào biến mới** rồi capture. Khi cần lưu callback lâu dài hoặc dùng vòng lặp, xác định rõ **giá trị ở mỗi lần gọi/lượt lặp** và **thời gian sống của object được capture**.
