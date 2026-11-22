# Thứ tự đánh giá đối tượng nhận lời gọi và các đối số trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **đối tượng nhận lời gọi** (*receiver* hoặc *target object*) và **biểu thức đối số** (*argument expressions*) trong một lời gọi phương thức Java.
- Giải thích quy tắc đánh giá runtime: **xác định/evaluate biểu thức receiver trước (nếu cần), sau đó evaluate các đối số từ trái sang phải, rồi mới chuyển quyền điều khiển vào thân phương thức**.
- Dự đoán đúng kết quả khi biểu thức receiver hoặc đối số có tác dụng phụ (*side effects*): in ra console, tăng biến đếm, gán biến, thay đổi đối tượng.
- Giải thích điều gì xảy ra nếu receiver là `null`, biểu thức receiver ném exception hoặc một đối số đánh giá thất bại.
- Nhận biết trường hợp `static` không có đối tượng nhận lời gọi ở runtime, nhưng cú pháp gọi static method qua biểu thức vẫn có thể khiến biểu thức đó được đánh giá.
- Phân biệt **thứ tự đánh giá biểu thức** với **kiểm tra kiểu/chọn overload khi biên dịch**, **dispatch động** và **thứ tự thực thi bên trong thân phương thức**.
- Viết code hạn chế side effects khó đoán và sử dụng biến trung gian để thể hiện thứ tự mong muốn.

## 1. Lời gọi có receiver và danh sách đối số

Trong biểu thức Java:

~~~java
service.process(loadId(), calculateAmount());
~~~

- `service` là biểu thức xác định **receiver**, tức đối tượng mà instance method `process` được gọi trên đó.
- `loadId()` là **biểu thức đối số thứ nhất**.
- `calculateAmount()` là **biểu thức đối số thứ hai**.
- `process` là method được chọn theo quy tắc ngôn ngữ và được thực thi sau khi đánh giá các thành phần cần thiết.

Đây là **mã minh họa**, không phải chương trình tự chạy: muốn biên dịch phải có biến `service` với kiểu phù hợp, các phương thức `loadId()`, `calculateAmount()` và chữ ký `process`.

Ví dụ lời gọi tương tự nhưng receiver là biểu thức phức tạp hơn:

~~~java
findService().process(loadId(), calculateAmount());
~~~

Ở đây `findService()` là biểu thức receiver: nó phải được đánh giá để lấy giá trị tham chiếu **trước** khi Java bắt đầu đánh giá `loadId()` và `calculateAmount()` theo quy tắc của method invocation.

**Quy tắc ghi nhớ:** với instance method có receiver là biểu thức, trình tự khái niệm là **receiver → đối số 1 → đối số 2 → ... → thực thi method**. Nếu một bước kết thúc bất thường do exception, các bước phía sau có thể không xảy ra.

## 2. Java đặc tả thứ tự nào?

Theo Java Language Specification (JLS), phần **15.12.4 — Run-Time Evaluation of Method Invocation**, quy trình gọi method ở runtime được mô tả lần lượt:

1. **Compute Target Reference (If Necessary)**: tính receiver/target reference khi hình thức lời gọi đòi hỏi; biểu thức receiver được đánh giá trước đối số.
2. **Evaluate Arguments**: đánh giá các biểu thức đối số theo đúng thứ tự **trái sang phải**; giá trị tính được dùng cho các tham số hình thức.
3. **Check Accessibility of Type and Method** ở runtime trong những trường hợp đặc tả quy định.
4. **Locate Method to Invoke**: xác định method implementation tương ứng; đối với instance invocation, target `null` gây `NullPointerException` ở giai đoạn thích hợp này.
5. **Create Frame, Synchronize, Transfer Control**: thực hiện những bước cần thiết rồi mới vào phần thân method.

Từ góc nhìn viết Java ứng dụng, thường chỉ cần ba ý chính: **tính receiver trước → tính lần lượt tất cả đối số → bắt đầu gọi implementation**. Trình tự này được ngôn ngữ quy định, không tùy tiện đảo bởi compiler hay JIT theo cách làm thay đổi hành vi quan sát được của chương trình đơn luồng hợp lệ.

**Phân biệt thời điểm:** compiler đã phân tích kiểu và lựa chọn method ở cấp source theo quy tắc overload trước khi chương trình chạy. Việc in dòng log từ `findService()`, đọc giá trị biến hoặc ném exception khi evaluate argument mới xảy ra **ở runtime**.

Lưu ý thêm về terminology: một lời gọi viết bằng tên đơn giản như `execute(x)`, bằng `this.execute(x)`, bằng `TypeName.staticMethod(x)` hoặc bằng `super.execute(x)` có hình thức receiver khác nhau. Không phải mọi lời gọi đều phải chạy một biểu thức tạo receiver tường minh; nguyên tắc trái-sang-phải áp dụng cho những biểu thức cần được đánh giá ở lời gọi tương ứng.

## 3. Ví dụ Java 17+ hoàn chỉnh: receiver trước, đối số từ trái sang phải

Lưu tệp **`EvaluationOrderDemo.java`**:

~~~java
public class EvaluationOrderDemo {
    static final class Worker {
        private final String name;

        Worker(String name) {
            this.name = name;
        }

        void execute(int first, int second) {
            System.out.println("method " + name + " received " + first + "," + second);
        }
    }

    static Worker createReceiver() {
        System.out.println("1. receiver");
        return new Worker("W");
    }

    static int argument(String label, int value) {
        System.out.println(label);
        return value;
    }

    public static void main(String[] args) {
        createReceiver().execute(
                argument("2. first argument", 10),
                argument("3. second argument", 20)
        );
        System.out.println("4. after invocation");
    }
}
~~~

Biên dịch và chạy từ thư mục có tệp, với JDK 17 trở lên:

~~~bash
javac EvaluationOrderDemo.java
java EvaluationOrderDemo
~~~

Kết quả **stdout chính xác**:

~~~text
1. receiver
2. first argument
3. second argument
method W received 10,20
4. after invocation
~~~

Vì sao kết quả theo thứ tự này?

1. Java phải đánh giá `createReceiver()` để lấy tham chiếu tới đối tượng `Worker("W")`. Do đó dòng `1. receiver` xuất hiện trước.
2. Java đánh giá `argument("2. first argument", 10)`, in dòng thứ hai, nhận kết quả `10`.
3. Java đánh giá `argument("3. second argument", 20)`, in dòng thứ ba, nhận kết quả `20`.
4. Sau khi đã có các giá trị đối số, Java thực hiện `execute(10,20)` trên đối tượng `Worker("W")`. Lúc này thân method mới in dòng `method W received 10,20`.
5. Lời gọi kết thúc bình thường, `main` tiếp tục in `4. after invocation`.

Đây là **thứ tự bắt buộc về mặt hành vi**. Thay đổi vị trí viết hai lời gọi `argument(...)` sẽ đổi thứ tự đánh giá của chúng.

### 3.1. Không đồng nhất tham số với biểu thức đối số

Trong khai báo `void execute(int first, int second)`, `first` và `second` là **tham số hình thức**. Còn các lời gọi `argument(...)` là **biểu thức đối số**. Các biểu thức được đánh giá xong mới truyền giá trị vào tham số. Thân `execute` nhận hai giá trị `10` và `20`; nó không tự gọi lại biểu thức đã tạo ra các giá trị đó.

### 3.2. Một đối số có thể là biểu thức lồng nhau

Ví dụ:

~~~java
worker.execute(convert(load()), other());
~~~

Java tính biểu thức receiver `worker`, sau đó hoàn thành toàn bộ biểu thức đối số đầu `convert(load())` (bao gồm lời gọi lồng `load()`) rồi mới bắt đầu biểu thức đối số thứ hai `other()`. Bên trong biểu thức đối số đầu, quy tắc đánh giá biểu thức Java tiếp tục được áp dụng; không có việc luân phiên “nửa đối số thứ nhất, nửa đối số thứ hai”.

Đây là **đoạn minh họa** cần các phương thức và kiểu dữ liệu tương ứng; không phải tệp chạy độc lập.

## 4. Receiver được xác định trước khi đối số thay đổi biến

Trường hợp tinh tế: một biến tham chiếu có thể bị gán lại **trong khi đánh giá đối số**, nhưng receiver đã được tính trước đó sẽ vẫn là tham chiếu ban đầu.

Lưu **`ReceiverSnapshotDemo.java`**:

~~~java
public class ReceiverSnapshotDemo {
    static final class Box {
        final String label;

        Box(String label) {
            this.label = label;
        }

        void describe(Box other) {
            System.out.println("receiver=" + this.label
                    + ", argument=" + other.label);
        }
    }

    public static void main(String[] args) {
        Box current = new Box("OLD");
        current.describe(current = new Box("NEW"));
        System.out.println("current variable=" + current.label);
    }
}
~~~

Chạy:

~~~bash
javac ReceiverSnapshotDemo.java
java ReceiverSnapshotDemo
~~~

Output:

~~~text
receiver=OLD, argument=NEW
current variable=NEW
~~~

Các bước xảy ra:

1. Java đánh giá `current` **bên trái `.describe`**, lưu giá trị tham chiếu tới đối tượng `Box("OLD")` làm receiver của **lời gọi đang thực hiện**.
2. Java bắt đầu đánh giá đối số `current = new Box("NEW")`; phép gán làm **biến `current`** trỏ sang đối tượng mới, và biểu thức gán trả về tham chiếu mới để làm đối số.
3. Thân `describe` chạy trên receiver **OLD**, còn tham số `other` nhận đối tượng **NEW**.
4. Sau lời gọi, biến `current` ở `main` vẫn tham chiếu NEW.

Đây không phải hiện tượng “Java lưu ảnh chụp toàn bộ đối tượng”. Java chỉ giữ **giá trị tham chiếu receiver đã được xác định**. Nếu đối tượng OLD bị thay đổi trạng thái qua một tham chiếu khác trong lúc đánh giá đối số, method vẫn có thể quan sát trạng thái mới của cùng đối tượng OLD. Phân biệt rõ **giữ tham chiếu** với **sao chép đối tượng**.

### 4.1. Ví dụ với `String` và gán trong đối số

~~~java
String text = "one";
boolean starts = text.startsWith(text = "two");
System.out.println(starts);
System.out.println(text);
~~~

Đây là **đoạn đặt trong method**, không phải chương trình độc lập. Kết quả:

~~~text
false
two
~~~

Receiver `text` của `startsWith` được đánh giá khi vẫn là `"one"`; biểu thức đối số `text = "two"` chạy sau, nên `startsWith` kiểm tra liệu `"one"` có bắt đầu bằng `"two"` không (kết quả `false`). Biến `text` sau lời gọi giữ tham chiếu tới `"two"`.

Ví dụ này cũng được JLS dùng để minh họa việc xác định target reference trước khi đánh giá đối số.

## 5. Nếu receiver là `null`, đối số vẫn được đánh giá trước khi ném NPE

Một nhầm lẫn rất phổ biến là JVM sẽ ngay lập tức ném `NullPointerException` khi gặp `nullReceiver.method(argument())` và bỏ qua `argument()`. Đối với **lời gọi instance method thông thường**, quy trình chuẩn là: tính receiver (có thể nhận `null`), **sau đó đánh giá các đối số**, rồi kiểm tra tham chiếu nhận lời gọi khi xác định method để invoke. Vì vậy tác dụng phụ của đối số có thể vẫn xuất hiện **trước** NPE.

Lưu **`NullReceiverDemo.java`**:

~~~java
public class NullReceiverDemo {
    static final class Handler {
        void handle(int code, String label) {
            System.out.println("method body");
        }
    }

    static Handler missing() {
        System.out.println("receiver evaluated");
        return null;
    }

    static int first() {
        System.out.println("first argument evaluated");
        return 1;
    }

    static String second() {
        System.out.println("second argument evaluated");
        return "ready";
    }

    public static void main(String[] args) {
        try {
            missing().handle(first(), second());
        } catch (NullPointerException expected) {
            System.out.println("caught NullPointerException");
        }
    }
}
~~~

Chạy:

~~~bash
javac NullReceiverDemo.java
java NullReceiverDemo
~~~

Output:

~~~text
receiver evaluated
first argument evaluated
second argument evaluated
caught NullPointerException
~~~

Dòng `method body` **không xuất hiện** vì `handle` không được thực thi trên receiver `null`. Tuy nhiên, `first()` và `second()` **đã chạy** trước khi exception được ném.

**Giới hạn của quy tắc này:** nếu lỗi phát sinh **ngay trong quá trình đánh giá biểu thức receiver**, Java dừng tại chỗ lỗi đó và không bắt đầu đánh giá đối số. Ví dụ, nếu `missing()` tự ném exception thay vì trả `null`, các đối số sẽ không được đánh giá. `null` được trả về bình thường và một biểu thức ném exception là **hai tình huống khác nhau**.

## 6. Exception ở receiver hoặc đối số làm ngừng đánh giá phần còn lại

Quy tắc thực thi của Java bao gồm khái niệm **abrupt completion**: nếu đang đánh giá một biểu thức mà biểu thức ném exception (hoặc kết thúc bất thường theo quy tắc thích hợp), các phần sau vốn phụ thuộc vào biểu thức đó sẽ không được đánh giá trong lời gọi đang xét.

### 6.1. Receiver ném exception: không chạy đối số

Lưu **`ReceiverFailureDemo.java`**:

~~~java
public class ReceiverFailureDemo {
    static final class Worker {
        void run(int value) {
            System.out.println("method body");
        }
    }

    static Worker target() {
        System.out.println("receiver begins");
        throw new IllegalStateException("receiver failed");
    }

    static int argument() {
        System.out.println("argument begins");
        return 10;
    }

    public static void main(String[] args) {
        try {
            target().run(argument());
        } catch (IllegalStateException expected) {
            System.out.println("caught: " + expected.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac ReceiverFailureDemo.java
java ReceiverFailureDemo
~~~

Output:

~~~text
receiver begins
caught: receiver failed
~~~

`argument begins` và `method body` không xuất hiện vì đánh giá `target()` bị gián đoạn trước khi có receiver.

### 6.2. Đối số thứ hai ném exception: không chạy đối số thứ ba

Lưu **`ArgumentFailureDemo.java`**:

~~~java
public class ArgumentFailureDemo {
    static final class Target {
        void accept(int a, int b, int c) {
            System.out.println("method body");
        }
    }

    static Target target() {
        System.out.println("receiver");
        return new Target();
    }

    static int first() {
        System.out.println("argument 1");
        return 1;
    }

    static int second() {
        System.out.println("argument 2");
        throw new IllegalArgumentException("bad argument");
    }

    static int third() {
        System.out.println("argument 3");
        return 3;
    }

    public static void main(String[] args) {
        try {
            target().accept(first(), second(), third());
        } catch (IllegalArgumentException expected) {
            System.out.println("caught: " + expected.getMessage());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ArgumentFailureDemo.java
java ArgumentFailureDemo
~~~

Output:

~~~text
receiver
argument 1
argument 2
caught: bad argument
~~~

Java đã tính receiver, đánh giá xong đối số đầu, rồi bắt đầu đối số thứ hai. Khi `second()` ném `IllegalArgumentException`, Java **không gọi `third()`** và **không vào thân `accept`**. Side effects đã xảy ra từ receiver và đối số đầu không tự bị rollback.

### 6.3. Bảng tổng hợp các trường hợp

| Tình huống | Receiver được đánh giá? | Đối số được đánh giá? | Thân instance method chạy? |
| --- | --- | --- | --- |
| Receiver/đối số đều thành công, receiver khác `null` | Có, nếu có biểu thức receiver | Theo thứ tự trái → phải | Có |
| Biểu thức receiver ném exception | Bắt đầu rồi thất bại | Không | Không |
| Receiver trả về `null` bình thường | Có | Có, trừ khi đối số tự gây lỗi | Không; sau đánh giá đối số sẽ phát sinh NPE |
| Đối số thứ nhất ném exception | Thành công trước đó | Đối số 1 bắt đầu rồi lỗi; các đối số sau không chạy | Không |
| Đối số thứ hai ném exception | Thành công trước đó | Đối số 1 hoàn tất, đối số 2 lỗi, đối số tiếp theo bỏ qua | Không |
| Tất cả đối số hoàn tất nhưng method body ném exception | Có | Tất cả hoàn tất | Có, rồi kết thúc bất thường |

Bảng giả định lời gọi **instance method bình thường** và không có lỗi runtime khác như linkage errors. Không nên áp dụng cột “receiver null sẽ NPE” cho lời gọi phương thức `static` vì static method không cần receiver instance.

## 7. Lời gọi `static`: có hay không có biểu thức receiver?

Khi gọi trực tiếp qua **tên lớp**:

~~~java
Math.max(computeA(), computeB());
~~~

Java không cần một đối tượng `Math` ở runtime; `Math.max` là static method. Compiler xác định đây là lời gọi static, rồi các biểu thức `computeA()` và `computeB()` được đánh giá từ trái sang phải.

Java vẫn **cho phép cú pháp gọi static method qua biểu thức** có kiểu phù hợp, dù điều này dễ gây hiểu lầm và thường bị IDE cảnh báo. Trong dạng đó, biểu thức bên trái dấu chấm **vẫn được đánh giá** để bảo toàn tác dụng phụ; giá trị tham chiếu thu được không dùng làm receiver cho static method. Ngay cả kết quả `null` cũng không gây NPE chỉ vì gọi static method.

Lưu **`StaticInvocationDemo.java`**:

~~~java
public class StaticInvocationDemo {
    static final class Utility {
        static void report(int number) {
            System.out.println("static body=" + number);
        }
    }

    static Utility source() {
        System.out.println("source expression");
        return null;
    }

    static int value() {
        System.out.println("argument expression");
        return 7;
    }

    public static void main(String[] args) {
        source().report(value());
        Utility.report(8);
    }
}
~~~

Chạy:

~~~bash
javac StaticInvocationDemo.java
java StaticInvocationDemo
~~~

Output:

~~~text
source expression
argument expression
static body=7
static body=8
~~~

`source().report(value())` đánh giá `source()` trước `value()`. Dù `source()` trả `null`, lời gọi static `report` vẫn chạy. Đây là hệ quả của **phương thức được xác định là static tại compile time**; không có dispatch động qua receiver `null`.

**Cách viết khuyến nghị:** luôn gọi static method qua **tên lớp**, như `Utility.report(8)`, để người đọc không tưởng rằng phương thức cần một đối tượng. Không cố tình gọi static qua biểu thức chỉ để dựa vào side effects của biểu thức đó.

## 8. Lời gọi trên `this`, `super` và tên method ngắn

Không phải lời gọi nào cũng có biểu thức receiver phức tạp:

~~~java
process(first(), second());
this.process(first(), second());
super.process(first(), second());
~~~

Đây là ba **mẫu minh họa** trong ngữ cảnh lớp/phương thức phù hợp; dòng `super.process(...)` chỉ hợp lệ ở nơi có method phù hợp để truy cập qua `super`. Khi có instance invocation dạng `process(...)`, receiver có thể được xác định ngầm định từ `this` theo ngữ cảnh; `this.process(...)` nêu tường minh. `super.process(...)` có cơ chế chọn triển khai lớp cha theo quy tắc của Java.

Dù không có lời gọi `findReceiver()` ở phía trước, **các biểu thức đối số vẫn được đánh giá từ trái sang phải**. Không nhầm việc nhận diện receiver với việc “chạy thân method”: code trong method vẫn bắt đầu sau khi các đối số hoàn tất.

Đối với constructor `new Item(a(), b())`, các biểu thức đối số cũng được đánh giá theo thứ tự từ trái sang phải trước khi phần thân constructor nhận được các giá trị. Constructor không phải instance method bình thường; việc cấp phát đối tượng, gọi constructor cha và initializer có những quy tắc riêng. Vì vậy, không sao chép máy móc câu “receiver null kiểm tra sau đối số” sang cú pháp constructor.

## 9. Side effects ở các đối số: toán tử `++`, phép gán và tham chiếu

Một nguồn bug thường gặp là đặt nhiều biểu thức **vừa đọc vừa thay đổi** cùng một biến trong danh sách đối số.

Ví dụ:

~~~java
static void show(int first, int second, int third) {
    System.out.println(first + "," + second + "," + third);
}
~~~

Trong một method có `int x = 0;`, lời gọi:

~~~java
show(x++, ++x, x);
System.out.println("x=" + x);
~~~

in:

~~~text
0,2,2
x=2
~~~

Lý do:

1. `x++` trả về giá trị cũ `0`, **sau đó** tăng `x` thành `1`.
2. `++x` tăng `x` thành `2`, **rồi** trả về `2`.
3. Đối số thứ ba đọc `x` hiện tại là `2`.
4. Phương thức `show` nhận các **giá trị đã đánh giá** `0,2,2`.

Java quy định thứ tự, nên kết quả không phải “undefined behavior” chỉ vì có nhiều `++`; tuy nhiên mã này **khó đọc và dễ nhầm**. Dùng biến trung gian sẽ rõ hơn:

~~~java
int x = 0;
int first = x++;
int second = ++x;
int third = x;
show(first, second, third);
~~~

Hai đoạn mô tả cùng trình tự khi đặt trong những phạm vi riêng biệt có trạng thái ban đầu `x = 0`. Không ghép cả hai nguyên văn vào cùng một block khi chúng cùng khai báo `x`.

### 9.1. Đánh giá tham chiếu và thay đổi nội dung đối tượng

Giả sử một method nhận `StringBuilder`, và các đối số có thể thay đổi chính đối tượng `StringBuilder`. Java đánh giá **giá trị tham chiếu** theo thứ tự; nhưng **trạng thái đối tượng** có thể bị thay đổi bởi một đối số đến sau. Ví dụ:

~~~java
static void view(StringBuilder buffer, String snapshot) {
    System.out.println(buffer + " | " + snapshot);
}
~~~

Giả sử code trong một method:

~~~java
StringBuilder text = new StringBuilder("A");
view(text, text.append("B").toString());
~~~

Output là:

~~~text
AB | AB
~~~

Đối số thứ nhất được đánh giá trước, nhưng nó chỉ lưu **tham chiếu** tới `text`, không sao chép nội dung `"A"`. Đối số thứ hai gọi `append("B")`, biến đổi cùng đối tượng thành `"AB"` rồi tạo `String` snapshot `"AB"`. Khi thân `view` chạy, `buffer` vẫn trỏ đối tượng `StringBuilder` đã bị đổi.

**Bài học:** “đối số được đánh giá từ trái sang phải” không có nghĩa toàn bộ trạng thái các đối tượng được đóng băng ngay khi tính từng đối số.

## 10. Varargs cũng giữ thứ tự biểu thức

Với tham số biến độ dài `String... items`, các **biểu thức đối số thực tế** vẫn được đánh giá theo thứ tự xuất hiện. Khi lời gọi được xử lý ở dạng variable arity, Java gom các giá trị phù hợp vào mảng để truyền vào tham số cuối.

Lưu **`VarargsOrderDemo.java`**:

~~~java
public class VarargsOrderDemo {
    static String label(String name) {
        System.out.println("evaluate " + name);
        return name;
    }

    static void join(String... items) {
        System.out.println("joined=" + String.join("-", items));
    }

    public static void main(String[] args) {
        join(label("A"), label("B"), label("C"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac VarargsOrderDemo.java
java VarargsOrderDemo
~~~

Output:

~~~text
evaluate A
evaluate B
evaluate C
joined=A-B-C
~~~

Dùng varargs không khiến Java đánh giá các `label(...)` song song hoặc đảo thứ tự. Trường hợp truyền **một đối số đã là mảng** như `join(new String[] {"A","B"})` có dạng gọi khác về mặt tạo mảng, nhưng vẫn chỉ có một biểu thức đối số được đánh giá ở lời gọi đó.

Không cần suy đoán chi tiết bố trí mảng tạm trong bộ nhớ để giải thích thứ tự observable của các lời gọi `label`.

## 11. Đừng nhầm thứ tự đánh giá với overload resolution và dynamic dispatch

Ba giai đoạn/khái niệm cần tách riêng:

| Nội dung | Diễn ra chủ yếu khi nào? | Ví dụ |
| --- | --- | --- |
| Xác định overload phù hợp | Khi **biên dịch**, dựa trên kiểu tĩnh và quy tắc áp dụng phương thức | Chọn `print(Object)` hay `print(String)` |
| Đánh giá receiver và các biểu thức đối số | Khi **chạy**, theo thứ tự được JLS quy định | `provider().print(createValue())` |
| Chọn implementation override | Khi **chạy** đối với lời gọi instance cần dynamic dispatch | Biến kiểu `Base` trỏ đối tượng `Derived`, gọi method bị override |

Overload không có nghĩa Java phải **chạy tất cả các biểu thức đối số thử nghiệm** để xem phương thức nào phù hợp. Compiler xác định phương thức theo kiểu và cấu trúc biểu thức, chứ không cần chạy `createValue()` nhiều lần. Một lần gọi bình thường đánh giá biểu thức receiver và các đối số cần thiết đúng theo quy tắc runtime, không lặp chỉ để quyết định overload.

Ví dụ chạy độc lập **`DispatchOrderDemo.java`**:

~~~java
public class DispatchOrderDemo {
    static class Base {
        void show(Object value) {
            System.out.println("Base.show(Object)");
        }
    }

    static class Derived extends Base {
        @Override
        void show(Object value) {
            System.out.println("Derived.show(Object)");
        }

        void show(String value) {
            System.out.println("Derived.show(String)");
        }
    }

    static Base receiver() {
        System.out.println("receiver");
        return new Derived();
    }

    static String argument() {
        System.out.println("argument");
        return "text";
    }

    public static void main(String[] args) {
        receiver().show(argument());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DispatchOrderDemo.java
java DispatchOrderDemo
~~~

Output:

~~~text
receiver
argument
Derived.show(Object)
~~~

Giải thích:

1. `receiver()` được đánh giá trước và có **kiểu khai báo trả về `Base`**, dù đối tượng thực tế được trả về là `Derived`.
2. Tập overload có thể áp dụng ở compile time được tìm theo kiểu `Base`; do đó chữ ký được chọn là `show(Object)`, không phải overload `show(String)` chỉ khai báo ở `Derived`.
3. `argument()` được đánh giá tiếp theo và tạo giá trị kiểu `String` tương thích với `Object`.
4. Khi gọi instance method đã chọn, dispatch động tới bản **override `Derived.show(Object)`** và in dòng cuối.

Không thể suy luận “runtime object là Derived + runtime argument là String nên tự gọi Derived.show(String)”. Overload resolution và dynamic dispatch là hai cơ chế khác nhau.

## 12. Phân biệt quy tắc đánh giá với thứ tự thực thi giữa nhiều luồng

Quy tắc thứ tự đánh giá của **một biểu thức gọi method trong một luồng** không tạo cam kết rằng mọi log từ **nhiều luồng chạy đồng thời** sẽ xuất hiện theo một thứ tự chung. Nếu worker thread khác cũng in console, các dòng từ những hoạt động độc lập có thể xen vào theo scheduling.

Điều bắt buộc ở đây là Java phải bảo toàn **ngữ nghĩa đánh giá receiver và đối số** của cùng lời gọi. Việc có dữ liệu chia sẻ giữa các luồng còn chịu Java Memory Model, đồng bộ hóa và các quy tắc về *happens-before*; đó là chủ đề riêng. Đừng dùng thứ tự in xen kẽ từ nhiều luồng để kết luận ngôn ngữ cho phép hoán đổi tự do các side effects trong cùng lời gọi.

Tương tự, compiler/JIT có thể tối ưu hóa những phép tính thuần khiết nếu kết quả quan sát được vẫn phù hợp với semantics của Java. Không nên diễn giải “đánh giá trái sang phải” như yêu cầu từng phép toán luôn phải nằm trong một chỉ thị CPU theo đúng vị trí của mã nguồn.

## 13. Những lỗi suy luận phổ biến

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Đối số được tính trước receiver.” | Biểu thức xác định receiver, khi cần, được đánh giá **trước** các đối số. |
| “Nếu receiver null thì không đối số nào chạy.” | Với instance invocation thông thường, đối số vẫn được đánh giá trước khi null receiver gây NPE ở bước invoke. |
| “Nếu receiver ném exception thì đối số vẫn được chạy.” | Receiver thất bại làm dừng lời gọi, các đối số chưa bắt đầu không được đánh giá. |
| “Một đối số lỗi vẫn không ảnh hưởng các đối số phía sau.” | Khi đối số hoàn thành bất thường, các đối số phía sau không chạy; thân method không được gọi. |
| “Tham số là biểu thức được chạy trong method.” | Biểu thức **đối số** chạy trước; tham số nhận giá trị do lời gọi truyền vào. |
| “Gán lại biến receiver trong đối số đổi receiver của cùng lời gọi.” | Target reference đã tính trước được giữ cho lời gọi hiện tại; phép gán chỉ đổi biến sau đó. |
| “Đánh giá một tham chiếu lưu bản sao nội dung object.” | Chỉ giá trị tham chiếu được dùng; các đối số sau vẫn có thể sửa object đã được tham chiếu. |
| “Java được tự đổi thứ tự đối số để tối ưu.” | Java phải bảo toàn ngữ nghĩa và side effects quan sát được theo quy tắc trái sang phải. |
| “Gọi static qua null sẽ luôn NPE.” | Static method không cần receiver instance; nếu cú pháp hợp lệ và biểu thức receiver chỉ trả null bình thường, bản thân lời gọi static không NPE. |
| “Overload được quyết định sau khi chạy các đối số.” | Overload resolution ở compile time; giá trị runtime phục vụ lời gọi implementation đã được lựa chọn theo quy tắc ngôn ngữ. |
| “Receiver có kiểu runtime Derived nên overload Derived(String) tự được chọn.” | Overload theo kiểu tĩnh; override dispatch theo đối tượng runtime ở trường hợp phù hợp. |
| “Side effect của đối số 1 tự bị hoàn tác nếu đối số 2 lỗi.” | Java không rollback side effects bình thường chỉ vì đối số sau ném exception. |

## 14. Quy trình đọc một lời gọi có side effects

Khi thấy lời gọi như:

~~~java
factory().work(nextId(), compute(), after());
~~~

Bạn có thể làm theo trình tự:

1. **Kiểm tra hợp lệ ở compile time**: có method `work` áp dụng cho các kiểu đối số tương ứng không? Receiver/method có truy cập được không?
2. **Xác định biểu thức receiver**: `factory()` có side effect hoặc có thể ném exception không?
3. **Đánh dấu đối số từ trái sang phải**: `nextId()` → `compute()` → `after()`; với biểu thức lồng nhau, xét tiếp thứ tự bên trong.
4. **Theo dõi biến bị thay đổi**: phép gán, `++`, thao tác với collection hoặc đối tượng mutable.
5. **Xét điểm exception có thể xuất hiện**: receiver ném exception, một đối số ném exception, hay receiver chỉ trả `null` bình thường.
6. **Sau khi đối số hoàn tất**, xác định method implementation được gọi; lưu ý khả năng dynamic dispatch nếu là instance method.
7. **Cuối cùng mới xét thân method**: những câu lệnh trong thân method không thể chạy trước khi hoàn tất các đối số của chính lời gọi đó.

Nếu các tác dụng phụ khiến đọc một biểu thức quá khó, tách ra thành các câu lệnh rõ ràng:

~~~java
Worker target = createWorker();
int id = nextId();
int amount = calculateAmount();
target.execute(id, amount);
~~~

Mã minh họa này yêu cầu `Worker` và các method liên quan tương thích. Đây là cách thể hiện rõ thứ tự; tuy nhiên nếu `createWorker()` trả `null`, cả `nextId()` và `calculateAmount()` vẫn chạy trước khi Java ném NPE ở lời gọi `target.execute(...)`, giống quy tắc với một lời gọi instance trực tiếp khi các biểu thức đối số tương ứng đều hoàn tất.

Khi bạn **muốn dừng sớm nếu receiver null trước khi chạy các tác vụ tính đối số**, cần kiểm tra có chủ đích:

~~~java
Worker target = createWorker();
if (target == null) {
    throw new IllegalStateException("No worker available");
}
int id = nextId();
int amount = calculateAmount();
target.execute(id, amount);
~~~

Khi đó việc dừng sớm là do **câu lệnh `if` bạn tự viết**, không phải do Java tự kiểm tra `null` trước các đối số của method invocation.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Với `factory().send(first(), second())`, nếu mọi biểu thức đều hoàn tất bình thường, thứ tự đánh giá là gì?  
**Đáp án:** `factory()` trước, `first()` sau, rồi `second()`; sau đó mới thực thi `send`.

**Câu 2.** `factory()` ném exception. `first()` và `second()` có chạy không?  
**Đáp án:** Không. Receiver không hoàn tất bình thường, nên Java dừng lời gọi và không đánh giá các đối số.

**Câu 3.** `factory()` trả về `null` bình thường; `first()` và `second()` không lỗi. Trong instance invocation thông thường, log từ hai đối số có thể xuất hiện trước NPE không?  
**Đáp án:** Có. Cả hai đối số được đánh giá trước khi `null` receiver dẫn tới NPE khi cố gắng invoke instance method.

**Câu 4.** `first()` hoàn tất; `second()` ném exception; `third()` có chạy trong `target.call(first(), second(), third())` không?  
**Đáp án:** Không. `third()` không bắt đầu và thân `call` không được thực thi.

**Câu 5.** Trong `current.describe(current = other)`, `describe` chạy trên đối tượng nào nếu `current` ban đầu trỏ A, `other` trỏ B?  
**Đáp án:** Chạy trên A, vì receiver được chốt trước khi đối số gán `current = other`. Đối số truyền vào có giá trị tham chiếu B.

**Câu 6.** `StringBuilder sb = new StringBuilder("A"); view(sb, sb.append("B").toString());` — tại sao đối số đầu tiên có thể thấy nội dung `"AB"` trong thân `view`?  
**Đáp án:** Đối số đầu là tham chiếu tới cùng đối tượng `StringBuilder`, không phải bản sao văn bản. Đối số thứ hai đã thay đổi đối tượng trước khi method chạy.

**Câu 7.** `Utility u = null; u.staticCall(doWork());` có nhất thiết ném NPE chỉ vì `u` null không?  
**Đáp án:** Không, nếu `staticCall` thực sự là static method và cú pháp hợp lệ. Cần phân biệt lỗi có thể phát sinh từ `doWork()` hoặc nội dung static method với việc receiver null.

**Câu 8.** `show(i++, ++i, i)` với `i=0` truyền những giá trị nào?  
**Đáp án:** Lần lượt `0, 2, 2`, vì mỗi biểu thức được đánh giá từ trái qua phải.

**Câu 9.** `Base provider()` trả đối tượng `Derived`, trong đó `Derived` overload `show(String)` còn `Base` chỉ có `show(Object)`. Lời gọi `provider().show("text")` tự động chọn `Derived.show(String)` không?  
**Đáp án:** Không. Overload được chọn theo kiểu tĩnh `Base`: `show(Object)`; tại runtime có thể dispatch tới bản override `Derived.show(Object)` nếu có.

## Tài liệu tham khảo

- Java Language Specification, [§15.12.4 Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.4) — thứ tự target reference, arguments, lookup và invocation.
- Java Language Specification, [§15.7 Evaluation Order](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.7) — các quy tắc đánh giá biểu thức Java và việc bảo toàn thứ tự/side effects.

## Ghi nhớ

Trong một lời gọi instance method bình thường, Java **xác định receiver trước**, **đánh giá từng biểu thức đối số theo thứ tự trái sang phải**, rồi mới thực hiện lời gọi. Nếu receiver hoặc một đối số ném exception, các bước sau của lời gọi bị bỏ qua; nếu receiver chỉ **trả về `null` bình thường**, các đối số có thể vẫn được tính trước khi xuất hiện NPE. Việc xác định receiver sớm giữ nguyên **tham chiếu của lời gọi hiện tại** ngay cả khi một đối số gán lại biến receiver. Thứ tự này được Java đặc tả và giúp dự đoán chính xác tác dụng phụ; tuy nhiên code dễ bảo trì nhất vẫn là code diễn đạt rõ thứ tự bằng tên và các biến trung gian khi lời gọi trở nên phức tạp.
