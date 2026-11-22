# Định nghĩa phương thức khác với gọi phương thức — Java 17+

## 1. Hai thao tác không giống nhau

**Định nghĩa phương thức** (*method declaration/definition*) là viết tên, kiểu tham số, kiểu trả về và thân lệnh để chỉ rõ một công việc **sẽ thực hiện như thế nào**. **Gọi phương thức** (*method invocation*) là yêu cầu thực hiện công việc đó tại một vị trí cụ thể trong chương trình.

~~~java
static void greet() {                    // ĐỊNH NGHĨA
    System.out.println("Hello!");
}

public static void main(String[] args) {
    System.out.println("Start");
    greet();                               // GỌI
    greet();                               // GỌI lần nữa
    System.out.println("End");
}
~~~

**Exact stdout khi chạy lớp chứa mã trên:**

~~~text
Start
Hello!
Hello!
End
~~~

- Phần `static void greet() { ... }` chỉ **mô tả** phương thức; bản thân việc khai báo không in `Hello!`.
- Mỗi lời gọi `greet();` thực hiện thân phương thức **một lần**.
- Khi thân `greet` kết thúc, luồng điều khiển trở lại **ngay sau vị trí gọi**.
- `main` cũng là một phương thức được định nghĩa trong mã. Khi chạy ứng dụng theo cách thông thường, Java launcher/JVM gọi `main` làm điểm bắt đầu.

**Ghi nhớ:** *Định nghĩa = phương thức làm gì; lời gọi = thực hiện khi nào, với dữ liệu nào.*

## 2. Cấu trúc một định nghĩa phương thức

~~~java
static int add(int a, int b) {
    int result = a + b;
    return result;
}
~~~

| Thành phần | Mã | Ý nghĩa |
|---|---|---|
| Modifier | `static` | Cho phép gọi theo lớp, không cần instance |
| Kiểu trả về | `int` | Giá trị trả về là một số nguyên `int` |
| Tên phương thức | `add` | Tên được dùng khi gọi |
| Danh sách tham số | `int a, int b` | Hai **tham số hình thức** có tên và kiểu |
| Thân phương thức | `{ ... }` | Các lệnh chạy khi phương thức được gọi |
| Lệnh trả về | `return result;` | Trả kết quả và kết thúc lời gọi |

**Lời gọi tương ứng:**

~~~java
int total = add(2, 5);
System.out.println(total);
~~~

**Exact stdout:**

~~~text
7
~~~

Ở lời gọi, `2` và `5` là **đối số** (*arguments*), được dùng để khởi tạo các **tham số** `a` và `b` cho lần gọi đó. `add(2, 5)` là một biểu thức có giá trị `7`; `int total = ...` lưu kết quả vào biến.

Không dùng chữ `int` để khai báo kiểu của đối số tại vị trí gọi:

~~~java
// SAI: add(int 2, int 5);
// ĐÚNG: add(2, 5);
~~~

## 3. Chỉ định nghĩa không có nghĩa là tự chạy

~~~java
public final class DefineOnlyDemo {
    static void announce() {
        System.out.println("ANNOUNCE");
    }

    public static void main(String[] args) {
        System.out.println("MAIN");
        // Không hề gọi announce().
    }
}
~~~

**Exact stdout:**

~~~text
MAIN
~~~

Biên dịch bằng `javac` kiểm tra chương trình và tạo class file, **không gọi** `announce()`. Chạy bằng `java` vào `main` cũng không tự gọi `announce()` khi không có câu lệnh invocation.

Nếu thêm `announce();` bên trong `main`, lúc chạy mới xuất hiện dòng `ANNOUNCE`. Nguyên tắc này áp dụng cho cả phương thức `void` và phương thức trả giá trị.

Ngoại lệ về **cơ chế khởi động và khởi tạo lớp** không thay đổi quy tắc trên: khối khởi tạo tĩnh/constructor là cơ chế khác, không phải mọi phương thức bạn định nghĩa đều tự chạy.

## 4. Luồng điều khiển khi gọi phương thức

~~~mermaid
flowchart TD
    A["main: trước lời gọi"] --> B["Đánh giá các đối số"]
    B --> C["Gọi phương thức và tạo ngữ cảnh lời gọi"]
    C --> D["Chạy thân phương thức"]
    D --> E["return giá trị hoặc kết thúc void"]
    E --> F["Quay về vị trí gọi"]
    F --> G["Tiếp tục câu lệnh tiếp theo"]
~~~

Ví dụ:

~~~java
static int square(int x) {
    System.out.println("inside square");
    return x * x;
}

public static void main(String[] args) {
    System.out.println("before");
    int value = square(3);
    System.out.println("result=" + value);
    System.out.println("after");
}
~~~

**Exact stdout:**

~~~text
before
inside square
result=9
after
~~~

Dòng `inside square` ở giữa `before` và `result` vì thân phương thức chạy **trong quá trình đánh giá lời gọi**. Sau `return`, phép gán `value = 9` hoàn thành và `main` thực thi các câu lệnh còn lại.

Một lần gọi thường có bộ tham số/biến cục bộ riêng. Nhiều lời gọi nối tiếp không chia sẻ biến cục bộ chỉ vì dùng cùng tên phương thức.

## 5. Đối số, tham số và thứ tự đánh giá

Java đánh giá các đối số theo thứ tự **từ trái sang phải**, trước khi thân phương thức được gọi.

~~~java
static int trace(String tag, int value) {
    System.out.println("argument " + tag);
    return value;
}

static int sum(int left, int right) {
    System.out.println("inside sum");
    return left + right;
}

// Ở trong main:
int result = sum(trace("LEFT", 2), trace("RIGHT", 5));
System.out.println("result=" + result);
~~~

**Exact stdout:**

~~~text
argument LEFT
argument RIGHT
inside sum
result=7
~~~

Luồng thực hiện:

1. Đánh giá `trace("LEFT", 2)`, nhận `2`.
2. Đánh giá `trace("RIGHT", 5)`, nhận `5`.
3. Gọi `sum(2, 5)`, thực hiện thân `sum` và trả `7`.
4. Gán `result = 7`, rồi in kết quả.

**Sai lầm phổ biến:** tưởng `sum` bắt đầu chạy trước khi các biểu thức đối số được đánh giá.

## 6. `return` và phương thức `void`

Hai dạng thường gặp:

~~~java
static int doubleValue(int value) {
    return value * 2;
}

static void printMessage(String text) {
    System.out.println(text);
}
~~~

Cách gọi:

~~~java
int number = doubleValue(4);
printMessage("value=" + number);
~~~

**Exact stdout:**

~~~text
value=8
~~~

- Phương thức kiểu `int` phải tạo ra giá trị trả về phù hợp trên mọi đường kết thúc bình thường theo luật Java; `return value;` đồng thời **kết thúc** phương thức.
- Phương thức `void` không cung cấp giá trị để gán; nó có thể kết thúc khi chạy hết thân, hoặc dùng `return;` để rời sớm.
- Có thể gọi một phương thức trả giá trị như một statement rồi bỏ qua giá trị: `doubleValue(4);` hợp lệ, nhưng thường cần xem vì sao không dùng kết quả.
- `int x = printMessage("Hi");` **không biên dịch**, vì phương thức `void` không trả `int`.

`System.out.println` cũng là một **lời gọi phương thức**, không phải cú pháp tạo phương thức mới.

## 7. `static` và phương thức instance

**Phương thức `static`** thuộc lớp và có thể gọi qua tên lớp:

~~~java
Math.max(3, 7);
~~~

**Phương thức instance** được gọi trên một đối tượng:

~~~java
String word = "Java";
System.out.println(word.length());
~~~

Ví dụ lớp có trạng thái:

~~~java
static final class Counter {
    private int count;

    int increase(int step) {
        count += step;
        return count;
    }
}

// Trong main:
Counter counter = new Counter();
System.out.println(counter.increase(2));
System.out.println(counter.increase(3));
~~~

**Exact stdout:**

~~~text
2
5
~~~

`increase` chỉ là định nghĩa trong lớp `Counter`. `new Counter()` tạo đối tượng với `count = 0`; **lời gọi** `counter.increase(...)` mới làm tăng `count`.

Gọi phương thức instance cần đối tượng phù hợp. Trong ngữ cảnh `static`, không thể viết `increase(2)` như thể đó là static method của lớp ngoài khi không có đối tượng `Counter`.

## 8. Phương thức có thể gọi phương thức khác

~~~java
static int twice(int value) {
    return value * 2;
}

static int fourfold(int value) {
    int first = twice(value);
    return twice(first);
}
~~~

Gọi `fourfold(3)` làm `twice(3)` trả 6, rồi `twice(6)` trả 12. Java thực thi lần lượt các lời gọi và quay lại phương thức gọi sau mỗi kết quả.

**Lưu ý:** việc định nghĩa `twice` và `fourfold` không tự tạo các lần gọi đó. Chỉ khi thực sự gọi `fourfold(3)` thì các lời gọi bên trong mới diễn ra.

Nếu các phương thức gọi nhau lặp mãi mà thiếu điều kiện dừng (đệ quy vô hạn), chương trình có thể gây `StackOverflowError`. Đây là vấn đề khi **thực thi lời gọi**, không phải do chỉ có nhiều định nghĩa.

## 9. Tác dụng của một lời gọi khi truyền giá trị và tham chiếu

Lời gọi đánh giá biểu thức đối số rồi dùng kết quả để khởi tạo **tham số riêng**. Sửa tham số primitive không làm thay đổi biến caller:

~~~java
static void replaceLocal(int value) { value = 100; }
int original = 5;
replaceLocal(original);
System.out.println(original); // 5.
~~~

Với tham số object, giá trị sao chép là **tham chiếu**: hai biến có thể cùng trỏ tới một đối tượng mutable.

~~~java
static void addMark(StringBuilder text) { text.append("!"); }
StringBuilder message = new StringBuilder("Hi");
addMark(message);
System.out.println(message); // Hi!
~~~

`append` làm thay đổi **object dùng chung**; trái lại, `text = new StringBuilder("Other")` chỉ gán lại biến tham số, không gán lại biến của caller. Điểm chính của bài này là **thân phương thức chỉ tạo tác dụng khi được gọi**. Bài tham số/đối số và bài truyền tham trị phân tích sâu hơn về phạm vi, alias, mảng và `final`.


## 10. Cùng một tên có thể dẫn tới những thân phương thức khác nhau

~~~java
static String describe(int value) { return "int:" + value; }
static String describe(String value) { return "String:" + value; }

System.out.println(describe(7));    // int:7.
System.out.println(describe("Hi")); // String:Hi.
~~~

Hai **định nghĩa** có cùng tên nhưng khác kiểu tham số; mỗi **lời gọi** được compiler phân giải tới overload phù hợp theo kiểu biểu thức đối số. Chỉ thay kiểu trả về hoặc tên biến tham số không tạo overload mới.

Bài hiện tại tập trung vào mối quan hệ *định nghĩa → lựa chọn lời gọi → thực thi thân*. Bài nạp chồng chuyên sâu sẽ giải thích chữ ký, mở rộng kiểu, boxing, varargs, `null` mơ hồ và generic erasure.


## 11. Chương trình Java 17+ hoàn chỉnh

Tạo file đúng tên **`MethodDefinitionCallDemo.java`**:

~~~java
public final class MethodDefinitionCallDemo {
    private MethodDefinitionCallDemo() {}

    static int square(int number) {
        System.out.println("body square " + number);
        return number * number;
    }

    static void greet(String name) {
        System.out.println("body greet " + name);
    }

    static int trace(String tag, int value) {
        System.out.println("arg " + tag + "=" + value);
        return value;
    }

    static int add(int left, int right) {
        System.out.println("body add " + left + "+" + right);
        return left + right;
    }

    static int twice(int value) {
        System.out.println("body twice " + value);
        return value * 2;
    }

    static int fourfold(int value) {
        System.out.println("body fourfold start");
        int first = twice(value);
        int result = twice(first);
        System.out.println("body fourfold end");
        return result;
    }

    static String describe(int value) {
        return "int:" + value;
    }

    static String describe(String value) {
        return "String:" + value;
    }

    static void replaceLocal(int value) {
        value = 100;
        System.out.println("inside local=" + value);
    }

    static void appendMark(StringBuilder builder) {
        builder.append("!");
        System.out.println("inside builder=" + builder);
    }

    static final class Counter {
        private int count;

        int increase(int step) {
            count += step;
            System.out.println("body increase count=" + count);
            return count;
        }
    }

    public static void main(String[] args) {
        System.out.println("main begin");

        int first = square(3);
        System.out.println("square result=" + first);
        System.out.println("square second=" + square(4));

        greet("Mai");

        int total = add(trace("left", 2), trace("right", 5));
        System.out.println("add result=" + total);

        System.out.println("fourfold result=" + fourfold(3));

        System.out.println("overload int=" + describe(7));
        System.out.println("overload String=" + describe("Hi"));

        int original = 5;
        replaceLocal(original);
        System.out.println("outside original=" + original);

        StringBuilder builder = new StringBuilder("Hi");
        appendMark(builder);
        System.out.println("outside builder=" + builder);

        Counter counter = new Counter();
        System.out.println("counter first=" + counter.increase(2));
        System.out.println("counter second=" + counter.increase(3));

        System.out.println("main end");
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal trong thư mục chứa file. Không cần Maven, Gradle, thư viện ngoài JDK hay preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 MethodDefinitionCallDemo.java
java -cp . MethodDefinitionCallDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\MethodDefinitionCallDemo.java
java -cp . MethodDefinitionCallDemo
~~~

### Exact expected stdout

~~~text
main begin
body square 3
square result=9
body square 4
square second=16
body greet Mai
arg left=2
arg right=5
body add 2+5
add result=7
body fourfold start
body twice 3
body twice 6
body fourfold end
fourfold result=12
overload int=int:7
overload String=String:Hi
inside local=100
outside original=5
inside builder=Hi!
outside builder=Hi!
body increase count=2
counter first=2
body increase count=5
counter second=5
main end
~~~

**Cách quan sát:** dòng `body square 3` xuất hiện trước `square result=9`, chứng minh thân chạy ở **thời điểm gọi**. Hai dòng `arg left/right` xuất hiện trước `body add`. `fourfold` gọi `twice` hai lần; biến `original` vẫn là 5 sau khi truyền vào tham số `int`; đối tượng `StringBuilder` đổi nội dung qua phương thức. `Counter` giữ trạng thái vì hai lời gọi được thực hiện trên **cùng object**.

## 12. Những lỗi thường gặp

| Sai lầm | Tại sao sai? | Cách sửa |
|---|---|---|
| Viết phương thức rồi chờ nó tự chạy | Định nghĩa không phải lời gọi | Gọi đúng tên với dấu `()` tại nơi cần |
| Nhầm `add(int a, int b)` với `add(2, 3)` | Một bên khai báo tham số; bên kia cung cấp đối số | Phân biệt cú pháp định nghĩa và gọi |
| Không có `()` khi muốn thực thi | Tên phương thức đơn lẻ không phải lời gọi Java thông thường | Viết `greet();` |
| Gọi sai số đối số/kiểu | Lỗi biên dịch | Khớp chữ ký/overload phù hợp |
| Gán kết quả từ phương thức `void` | `void` không tạo giá trị | Gọi riêng, không gán |
| Nghĩ `return` chỉ in hoặc lưu giá trị | `return` kết thúc phương thức và trả về caller | Dùng kết quả ở biểu thức/lệnh gán |
| Gọi instance method như static method | Thiếu đối tượng | Tạo instance rồi gọi `obj.method()` |
| Nghĩ gán tham số `int` thay biến caller | Java truyền đối số theo giá trị | Trả giá trị mới hoặc thay dữ liệu theo API |
| Nghĩ `StringBuilder` tự sao chép khi truyền | Giá trị tham chiếu trỏ cùng object mutable | Hiểu mutation khác gán lại tham số |
| Chỉ khác kiểu trả về để overload | Không tạo chữ ký khác | Thay số lượng/kiểu/thứ tự tham số phù hợp |
| Cho rằng `javac` thực thi toàn bộ method | Compiler kiểm tra và tạo class file | Dùng `java` và lời gọi thực tế để chạy |
| Cho rằng hai định nghĩa cùng tên/cùng tham số được phép | Khai báo trùng chữ ký | Đổi tên hoặc tạo overload hợp lệ |

## 13. Bài tập có đáp án

### A — Định nghĩa và lời gọi

~~~java
static void ping() {
    System.out.println("PING");
}
public static void main(String[] args) {
    System.out.println("START");
}
~~~

**Câu hỏi:** chạy lớp thì có in `PING` không? **Đáp án:** không; chỉ in `START`. Muốn in `PING`, thêm `ping();` vào `main`.

### B — Đếm số lần gọi

~~~java
static void hi() { System.out.println("HI"); }
public static void main(String[] args) {
    hi();
    hi();
}
~~~

**Exact stdout:**

~~~text
HI
HI
~~~

Định nghĩa một lần, nhưng thân thực thi **hai lần**.

### C — Tham số và đối số

~~~java
static int subtract(int a, int b) {
    return a - b;
}
// Trong main:
System.out.println(subtract(10, 3));
~~~

**Đáp án:** `a` và `b` là tham số; `10` và `3` là đối số; stdout `7`.

### D — `void` hay `int`?

~~~java
static void announce() {
    System.out.println("READY");
}
// int n = announce(); // Có hợp lệ không?
~~~

**Đáp án:** không; `announce()` không trả giá trị. Dùng `announce();` như một câu lệnh riêng.

### E — Đối tượng và trạng thái

~~~java
Counter counter = new Counter();
System.out.println(counter.increase(1));
System.out.println(counter.increase(2));
~~~

**Đáp án:** phương thức instance `increase` cập nhật cùng trường `count`; với lớp Counter ở chương trình chính, stdout gồm `body increase count=1`, `1`, `body increase count=3`, `3` theo thứ tự.

## 14. Checklist và kết luận

- [ ] Phân biệt **định nghĩa** và **gọi** phương thức.
- [ ] Biết khai báo modifier, kiểu trả về, tên và tham số.
- [ ] Gọi với dấu `()` và danh sách đối số đúng.
- [ ] Hiểu thân phương thức chỉ chạy khi lời gọi được thực thi.
- [ ] Biết `return` trả kết quả và quay về caller; `void` không trả giá trị.
- [ ] Hiểu thứ tự đánh giá đối số từ trái sang phải.
- [ ] Phân biệt `static` và instance method.
- [ ] Biết phương thức có thể gọi các phương thức khác.
- [ ] Hiểu truyền theo giá trị, kể cả giá trị tham chiếu object.
- [ ] Nhận diện overloading và lỗi chữ ký/phương thức không phù hợp.
- [ ] Chạy `MethodDefinitionCallDemo.java` bằng Java 17+ và đối chiếu exact stdout.

**Kết luận:** Định nghĩa phương thức là **mô tả một hành vi có thể được dùng lại**; lời gọi phương thức mới **thực thi hành vi đó** với các đối số cụ thể, sau đó nhận kết quả hoặc tiếp tục sau phương thức `void`. Hiểu khác biệt này là nền tảng để đọc đúng luồng thực thi Java.