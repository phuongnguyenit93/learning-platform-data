# Kiểm tra kiểu, số lượng và thứ tự đối số khi gọi phương thức Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **tham số hình thức** (*formal parameter*) trong khai báo với **đối số** (*argument*) ở vị trí gọi phương thức hoặc constructor.
- Kiểm tra một lời gọi có **đúng số lượng đối số**, **đúng thứ tự** và **kiểu dữ liệu tương thích** với tham số tương ứng hay không.
- Giải thích các chuyển đổi Java tự thực hiện trong lời gọi: mở rộng kiểu nguyên thủy, mở rộng tham chiếu, boxing, unboxing và các giới hạn quan trọng.
- Nhận biết ảnh hưởng của overload, tham số biến độ dài (`varargs`), generic type inference, `null`, mảng và tính bất biến của generic types.
- Đọc được thông báo lỗi biên dịch khi truyền thiếu, thừa, sai thứ tự hoặc sai kiểu đối số; tự sửa bằng khai báo/lời gọi đúng, không ép kiểu tùy tiện.
- Hiểu Java ánh xạ đối số theo **vị trí**, đánh giá biểu thức đối số **từ trái sang phải**, và truyền giá trị kết quả đánh giá vào tham số.

## 1. Tham số và đối số: hai phía của lời gọi

Xem ví dụ:

~~~java
public class Registration {
    static void register(String username, int age, boolean active) {
        System.out.println(username + " | " + age + " | " + active);
    }

    public static void main(String[] args) {
        register("Lan", 20, true);
    }
}
~~~

Lưu thành `Registration.java` rồi chạy với JDK 17 trở lên:

~~~bash
javac Registration.java
java Registration
~~~

Kết quả:

~~~text
Lan | 20 | true
~~~

Phương thức khai báo **ba tham số hình thức** theo thứ tự: `String username`, `int age`, `boolean active`. Lời gọi `register("Lan", 20, true)` cung cấp **ba đối số thực tế** theo cùng thứ tự: chuỗi `"Lan"`, số nguyên `20`, boolean `true`.

Java ánh xạ các đối số vào tham số **theo vị trí**, từ trái sang phải:

| Vị trí | Tham số hình thức | Đối số tương ứng | Kiểm tra |
| --- | --- | --- | --- |
| 1 | `String username` | `"Lan"` | `String` tương thích `String` |
| 2 | `int age` | `20` | Literal có kiểu `int` |
| 3 | `boolean active` | `true` | `boolean` tương thích `boolean` |

Tên biến bên trong method (`username`, `age`, `active`) là tên để **thân method sử dụng**. Người gọi không truyền đối số bằng các tên đó. Java không hỗ trợ cú pháp gọi theo tên như `register(active=true, age=20, username="Lan")`; nếu viết dạng này, đó không phải named arguments hợp lệ của Java.

Các nguyên tắc tương tự áp dụng cho **constructor**, ví dụ `new Person("Lan", 20)`, và cho instance methods, ví dụ `account.deposit(100)`. Riêng cú pháp lời gọi có thể khác do receiver, generic type arguments, lambda hay method reference, nhưng compiler vẫn cần kiểm tra sự tương thích của các tham số và đối số.

## 2. Kiểm tra số lượng đối số (arity)

Với phương thức cố định:

~~~java
static void move(int x, int y) {
    System.out.println(x + "," + y);
}
~~~

Lời gọi hợp lệ:

~~~java
move(3, 4);
~~~

Vì phương thức đòi hỏi chính xác **hai đối số**, các lời gọi sau bị lỗi biên dịch:

~~~java
// Ví dụ cố ý sai; chỉ dùng để giải thích, không chạy trực tiếp.
move(3);       // Thiếu đối số thứ hai
move(3, 4, 5); // Thừa đối số thứ ba
move();        // Không cung cấp đối số nào
~~~

Không có cơ chế **giá trị mặc định cho tham số** trong khai báo method Java theo kiểu `void move(int x = 0)`. Nếu muốn hỗ trợ cách gọi với số đối số khác nhau, bạn có thể:

1. **Overload** các phương thức có danh sách tham số khác nhau và cung cấp một cách gọi mặc định rõ ràng.
2. Dùng **varargs** khi cần nhận số phần tử không cố định, cùng kiểu ở vị trí cuối.
3. Dùng kiểu dữ liệu chứa cấu hình hoặc đối tượng tham số nếu có nhiều lựa chọn mang ý nghĩa nghiệp vụ khác nhau.

Ví dụ overload hợp lệ:

~~~java
static void draw(int x, int y) {
    System.out.println("draw at " + x + "," + y);
}

static void draw(int x) {
    draw(x, 0);
}
~~~

Đây là hai **method declarations minh họa trong một lớp**, không phải chương trình độc lập. `draw(5)` sẽ dùng overload một tham số; nó gọi lại `draw(5, 0)`. Quy tắc “thiếu/thừa đối số” luôn được xét trên **tập phương thức có thể áp dụng**: `draw(5)` hợp lệ ở ví dụ này do có overload tương ứng.

### 2.1. Tham số biến độ dài (`varargs`)

Một phương thức có tham số cuối dạng `Type... name` chấp nhận số lượng đối số biến đổi ở vị trí đó:

~~~java
static void printLabels(String prefix, String... labels) {
    System.out.println(prefix + ": " + String.join(", ", labels));
}
~~~

Đây là khai báo minh họa trong một lớp. Lời gọi có thể là:

~~~java
printLabels("none");
printLabels("one", "A");
printLabels("two", "A", "B");
printLabels("array", new String[] {"X", "Y"});
~~~

Nếu có `main` gọi bốn câu trên theo thứ tự, kết quả là:

~~~text
none: 
one: A
two: A, B
array: X, Y
~~~

Tham số `prefix` vẫn là **tham số cố định bắt buộc**. Phần `labels` có thể nhận 0 hoặc nhiều `String` ở hình thức lời gọi biến độ dài, hoặc nhận trực tiếp một `String[]` phù hợp. Trong thân phương thức, `labels` có kiểu mảng `String[]`.

Chỉ **tham số cuối** được khai báo dạng varargs; mỗi method nhiều nhất một varargs parameter. `void f(String... texts, int count)` không hợp lệ. Cú pháp `String...` và `String[]` có những điểm khác biệt khi gọi, nhưng không được khai báo cả hai để tạo overload có cùng chữ ký.

**Cẩn trọng:** Varargs không bỏ qua kiểm tra kiểu. `printLabels("bad", 1)` không hợp lệ vì `1` không thể được chuyển thành `String` bằng chuyển đổi lời gọi phù hợp.

## 3. Kiểm tra kiểu dữ liệu đối số

Không nhất thiết kiểu biểu thức đối số phải **trùng chính xác** kiểu tham số. Java cho phép một số **chuyển đổi hợp lệ tại thời điểm gọi** (*method invocation conversions*), miễn đáp ứng quy tắc áp dụng phương thức.

Ví dụ:

~~~java
static void readLong(long value) {
    System.out.println(value);
}

static void display(Object value) {
    System.out.println(value);
}
~~~

Trong một method của cùng lớp, những lời gọi sau hợp lệ:

~~~java
readLong(5);        // int -> long (mở rộng kiểu nguyên thủy)
display("Hello");   // String -> Object (mở rộng tham chiếu)
display(10);        // int được boxing thành Integer, sau đó có thể dùng như Object
~~~

Ngược lại, Java không tự động chuyển mọi kiểu sang mọi kiểu khác:

~~~java
// Ví dụ cố ý sai khi đặt trong method tương ứng:
// readLong("5");    // String không tự được parse thành số long
// readLong(true);   // boolean không thể thành long
~~~

### 3.1. Mở rộng kiểu nguyên thủy (primitive widening)

Một số chuyển đổi tự động điển hình:

| Kiểu đối số | Kiểu tham số chấp nhận bằng widening | Ghi chú |
| --- | --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` | Có thể mất độ chính xác khi chuyển sang float/double đủ lớn |
| `short` | `int`, `long`, `float`, `double` | Không tự thành `char` |
| `char` | `int`, `long`, `float`, `double` | `char` là đơn vị mã UTF-16 không dấu |
| `int` | `long`, `float`, `double` | `int` không tự thu hẹp thành `byte` hoặc `short` trong lời gọi method |
| `long` | `float`, `double` | Một số giá trị không biểu diễn chính xác trong dấu chấm động |
| `float` | `double` | Chuyển sang `double` |

`boolean` không tham gia các chuyển đổi số. Widening là các chuyển đổi compiler cho phép, nhưng **không đồng nghĩa luôn giữ nguyên độ chính xác toán học**: `long` sang `float` có thể bị làm tròn.

### 3.2. Thu hẹp kiểu không tự xảy ra trong lời gọi method

Ví dụ:

~~~java
static void acceptByte(byte value) {
    System.out.println(value);
}
~~~

Câu gọi `acceptByte(10)` **không hợp lệ**, mặc dù literal `10` nằm trong miền `byte`: kiểu của literal nguyên mặc định là `int`; Java không tự thực hiện chuyển đổi thu hẹp `int -> byte` chỉ để khớp tham số khi gọi method.

Đây là điểm khác biệt với **assignment conversion**:

~~~java
byte b = 10;        // Hợp lệ: quy tắc riêng cho hằng int khi gán
acceptByte(b);      // Hợp lệ: b đã có kiểu byte
acceptByte((byte) 10); // Hợp lệ: ép kiểu tường minh
~~~

Những dòng `acceptByte` là ví dụ nằm trong method của lớp có khai báo `acceptByte(byte)` bên trên. Phép ép kiểu phải có lý do; `(byte) 130` không giữ giá trị 130 mà cho kết quả khác do mất dữ liệu. Khi cần đại diện giá trị `int`, lựa chọn tham số `int` thường an toàn và rõ ràng hơn ép kiểu để vượt kiểm tra.

### 3.3. Boxing, unboxing và nguy cơ `null`

Java có thể boxing `int` thành `Integer`, hoặc unboxing `Integer` thành `int` theo quy tắc lời gọi. Ví dụ:

~~~java
static void takeInteger(Integer value) {
    System.out.println(value);
}

static void takeInt(int value) {
    System.out.println(value);
}
~~~

Trong một method phù hợp:

~~~java
takeInteger(7);                 // Boxing int -> Integer
takeInt(Integer.valueOf(7));    // Unboxing Integer -> int
~~~

Tuy nhiên:

~~~java
Integer maybe = null;
// takeInt(maybe); // Biên dịch hợp lệ nhưng lúc chạy ném NullPointerException khi unboxing
~~~

Khi `maybe` là `null`, việc unboxing để truyền vào tham số `int` gây lỗi runtime. Compiler có thể kiểm tra *kiểu* nhưng không thể bảo đảm tất cả dữ liệu runtime khác null.

Một chuỗi chuyển đổi không phải lúc nào cũng được phép: ví dụ Java **không** tự thực hiện widening `int -> long` rồi boxing thành `Long` để đáp ứng một tham số `Long` ở lời gọi thông thường. Muốn gọi `takeLongObject(Long)` từ `int x`, có thể ghi `takeLongObject(Long.valueOf(x))` (với chuyển đổi `int` sang `long` theo overload `Long.valueOf(long)`) hoặc dùng giá trị `long` được boxing phù hợp.

### 3.4. Widening reference và static type

Nếu kiểu tham số là `Object`, bạn có thể truyền biểu thức kiểu `String`, `Integer` hoặc một đối tượng của lớp con thích hợp:

~~~java
static void inspect(Object item) {
    System.out.println(item);
}
~~~

`inspect("hello")` hợp lệ vì `String` là subtype của `Object`; `inspect(5)` hợp lệ nhờ boxing thành `Integer` rồi phù hợp với `Object`.

Ngược lại, nếu method nhận `String` thì biến được khai báo kiểu `Object` **không tự động** truyền vào được dù hiện tại nó đang trỏ tới `String`:

~~~java
Object value = "text";
// consumeString(value); // Không biên dịch nếu consumeString(String) là overload duy nhất
~~~

Compiler kiểm tra dựa trên **kiểu tĩnh của biểu thức** và các quy tắc chuyển đổi được phép; nó không bỏ qua kiểu khai báo chỉ vì dữ liệu runtime tình cờ thuộc kiểu hẹp hơn. Nếu thật sự cần thu hẹp, có thể kiểm tra bằng `instanceof` hoặc cast được kiểm soát; cast sai có thể gây `ClassCastException`.

## 4. Thứ tự đối số quyết định chúng được ánh xạ vào tham số nào

Hai lời gọi có cùng **số lượng** và **tập kiểu** chưa chắc có cùng ý nghĩa:

~~~java
static int subtract(int left, int right) {
    return left - right;
}
~~~

`subtract(9, 4)` trả `5`, trong khi `subtract(4, 9)` trả `-5`. Cả hai đều hợp lệ về mặt kiểu vì mỗi đối số có kiểu `int`, nhưng **khác ý nghĩa nghiệp vụ**. Compiler không biết đâu là “số bị trừ” mà bạn chủ định: tên tham số không được dùng để tự sắp xếp lại đối số tại nơi gọi.

Khi danh sách kiểu cũng khác nhau, đảo thứ tự có thể tạo **lỗi biên dịch**:

~~~java
static void pay(String accountId, int amount) {
    System.out.println(accountId + ": " + amount);
}
~~~

Hợp lệ: `pay("ACC-1", 100)`. Không hợp lệ: `pay(100, "ACC-1")` vì vị trí 1 mong `String` nhưng nhận `int`, vị trí 2 mong `int` nhưng nhận `String`. Khi compiler có thể nhìn thấy nhiều overload `pay`, một overload khác có thể áp dụng; vì thế phải xét **tập các phương thức cùng tên có thể gọi**, không phán quyết chỉ dựa trên một khai báo đơn lẻ.

### 4.1. Java đánh giá biểu thức đối số từ trái sang phải

Java đánh giá các biểu thức đối số theo **thứ tự từ trái sang phải**; sau đó các giá trị được truyền vào tham số tương ứng. Nếu biểu thức đối số có side effects, thứ tự quan sát được có ý nghĩa:

Tệp **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int next(String label, int value) {
        System.out.println("evaluate " + label);
        return value;
    }

    static void accept(int first, int second) {
        System.out.println("called " + first + "," + second);
    }

    public static void main(String[] args) {
        accept(next("first", 10), next("second", 20));
    }
}
~~~

Chạy:

~~~bash
javac ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Output:

~~~text
evaluate first
evaluate second
called 10,20
~~~

Đối số thứ nhất được đánh giá trước đối số thứ hai. Đây là **thứ tự đánh giá**, không phải thứ tự mà overload được chọn: compiler chọn phương thức dựa trên kiểm tra kiểu, còn việc đánh giá biểu thức diễn ra khi chương trình chạy.

Để code dễ đọc và ít lỗi, không nên dựa vào nhiều side effects khó theo dõi trong cùng danh sách đối số; có thể tính trước các biến có tên rõ ràng rồi gọi method.

## 5. Overload ảnh hưởng đến kiểm tra kiểu, số lượng và thứ tự

**Method overloading** là khai báo nhiều phương thức cùng tên với danh sách kiểu tham số khác nhau hợp lệ. Ví dụ:

~~~java
static void send(String message) { }
static void send(String message, int retries) { }
static void send(int code, String message) { }
~~~

Đoạn trên gồm các khai báo minh họa trong cùng một lớp. Các lời gọi:

- `send("hello")` khớp phương thức một tham số `String`.
- `send("hello", 3)` khớp `send(String, int)`.
- `send(404, "Not found")` khớp `send(int, String)`.
- `send(404)` không khớp phương thức nào trong ba khai báo; thiếu overload nhận một `int`.
- `send(3, 4)` không khớp vì các overload hai tham số đều cần ít nhất một `String`.

Tên tham số, kiểu trả về và `throws` **không đủ tạo overload mới** nếu chữ ký Java vẫn trùng. Tại lời gọi, overload resolution là bước xem các phương thức khả dụng nào áp dụng và phương thức nào được ưu tiên theo quy tắc ngôn ngữ.

### 5.1. Ưu tiên áp dụng kiểu nào?

Ở mức tổng quát, Java kiểm tra tính áp dụng của overload theo **các pha**:

1. **Pha strict invocation**: trước hết xét các lời gọi có số tham số cố định và cho phép các chuyển đổi nghiêm ngặt như primitive widening hoặc reference widening, chưa cần boxing/unboxing.
2. **Pha loose invocation**: nếu pha trước không tìm được phương thức áp dụng, xét thêm boxing/unboxing và những chuyển đổi được phép liên quan.
3. **Pha variable arity**: nếu hai pha trước vẫn không có phương thức áp dụng, xét cách gọi các phương thức varargs bằng số đối số biến đổi.

Sau khi có các ứng viên áp dụng trong pha thích hợp, Java áp dụng quy tắc **most specific** để chọn. Có thể xuất hiện lời gọi **mơ hồ** (*ambiguous*) nếu không xác định được một phương thức phù hợp duy nhất.

Vì vậy câu nói “Java luôn chọn phương thức khớp kiểu chính xác” chỉ là trực giác trong một số tình huống đơn giản, không phải thuật toán overload resolution đầy đủ.

### 5.2. Widening có thể được ưu tiên trước boxing

Ví dụ:

~~~java
static String select(long value) {
    return "long";
}

static String select(Integer value) {
    return "Integer";
}
~~~

Lời gọi `select(7)` với literal `7` có kiểu `int` chọn `select(long)` nhờ primitive widening trong pha strict; Java chưa cần tới boxing thành `Integer`. Ngược lại, `select(Integer.valueOf(7))` có kiểu `Integer` và chọn overload `Integer` phù hợp trực tiếp.

Điều này giải thích vì sao một số chương trình in kết quả khác dự đoán của người chỉ nghĩ “`int` đi với `Integer` vì tên giống nhau”. Trong Java, **kiểu tĩnh của biểu thức** và các pha overload resolution mới quyết định.

### 5.3. Cùng số lượng nhưng xung đột khi truyền `null`

Cho hai overload:

~~~java
static void find(String text) { }
static void find(Integer number) { }
~~~

Lời gọi `find(null)` bị lỗi biên dịch do mơ hồ: `null` có thể dùng cho cả hai kiểu tham chiếu, và không có kiểu nào cụ thể hơn kiểu còn lại trong tình huống này. Các lời gọi `find((String) null)` hoặc `find((Integer) null)` thể hiện kiểu mong muốn rõ ràng; nhưng **runtime vẫn có thể có `null`**, nên method cần xử lý phù hợp.

Không thể truyền `null` cho một primitive parameter như `int`. Nếu API thường xuyên nhận `null`, cân nhắc thiết kế overload tránh tình huống mơ hồ hoặc quy định hợp đồng đầu vào chặt chẽ.

### 5.4. Varargs có thể thua overload cố định

Giả sử một lớp có:

~~~java
static void log(Object item) { }
static void log(String... items) { }
~~~

Lời gọi `log("hello")` thường chọn `log(Object)`: phương thức cố định `Object` đã áp dụng trong pha strict, trong khi `log(String...)` cần cơ chế varargs cho một `String`. Nếu gọi `log("A", "B")`, overload `Object` không nhận hai đối số; varargs có thể áp dụng.

Lưu ý khi truyền **một mảng `String[]`**, phương thức varargs có thể áp dụng như phương thức nhận **một đối số mảng ở dạng cố định**. Quy tắc này là lý do không nên áp dụng câu “fixed arity luôn thắng varargs” một cách máy móc cho mọi biểu thức.

## 6. Ví dụ hoàn chỉnh Java 17+: kiểm tra nhiều dạng lời gọi

Lưu chương trình độc lập sau vào **`ArgumentValidationDemo.java`**:

~~~java
import java.util.List;

public class ArgumentValidationDemo {
    static void record(String label, int quantity) {
        System.out.println(label + ":" + quantity);
    }

    static int subtract(int left, int right) {
        return left - right;
    }

    static long square(long value) {
        return value * value;
    }

    static String select(long value) {
        return "long";
    }

    static String select(Integer value) {
        return "Integer";
    }

    static void printTags(String category, String... tags) {
        System.out.println(category + ":" + String.join(",", tags));
    }

    static <T> T identity(T value) {
        return value;
    }

    static void showNumbers(List<? extends Number> values) {
        System.out.println("numbers=" + values.size());
    }

    public static void main(String[] args) {
        record("apples", 3);

        System.out.println("minus=" + subtract(9, 4));
        System.out.println("minus reversed=" + subtract(4, 9));
        System.out.println("square=" + square(5));

        System.out.println("select int=" + select(7));
        System.out.println("select boxed=" + select(Integer.valueOf(7)));

        printTags("levels", "basic", "advanced");
        printTags("empty");

        Integer copy = identity(42);
        System.out.println("copy=" + copy);

        showNumbers(List.of(1, 2, 3));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ArgumentValidationDemo.java
java ArgumentValidationDemo
~~~

**Output chính xác:**

~~~text
apples:3
minus=5
minus reversed=-5
square=25
select int=long
select boxed=Integer
levels:basic,advanced
empty:
copy=42
numbers=3
~~~

Giải thích các lời gọi:

| Lời gọi | Vì sao hợp lệ? |
| --- | --- |
| `record("apples", 3)` | Đúng hai đối số theo đúng thứ tự `String, int` |
| `subtract(9,4)` và `subtract(4,9)` | Cả hai khớp `(int,int)`, nhưng giá trị và vị trí đảo ngược làm đổi kết quả |
| `square(5)` | `int` được widening sang `long` |
| `select(7)` | Chọn overload `select(long)` trước khi cần boxing |
| `select(Integer.valueOf(7))` | Kiểu tĩnh của đối số là `Integer`, khớp overload `select(Integer)` |
| `printTags("levels", "basic", "advanced")` | Một đối số cố định `String`, hai đối số `String` cho varargs |
| `printTags("empty")` | Hợp lệ vì phần varargs có thể có 0 phần tử |
| `identity(42)` | Generic type inference cho phép lời gọi, kết quả phù hợp `Integer` |
| `showNumbers(List.of(1,2,3))` | Đối số là danh sách có kiểu phần tử phù hợp với `? extends Number` |

Bài thực hành: sửa `record("apples", 3)` thành `record(3, "apples")` và chạy lại `javac`. Bạn sẽ thấy lỗi **không tìm được lời gọi phù hợp** do hai kiểu đối số bị đảo. Khôi phục dòng đúng trước khi tiếp tục biên dịch.

## 7. Generic: compiler kiểm tra cả kiểu phần tử

Dấu `<...>` trong generic types **không bị bỏ qua** khi kiểm tra lời gọi Java source.

Ví dụ phương thức:

~~~java
static void printNames(java.util.List<String> names) {
    for (String name : names) {
        System.out.println(name);
    }
}
~~~

Trong một method cùng lớp, lời gọi với biến:

~~~java
java.util.List<String> names = java.util.List.of("Lan", "Minh");
printNames(names); // Hợp lệ
~~~

Nhưng:

~~~java
java.util.List<Integer> ages = java.util.List.of(20, 21);
// printNames(ages); // Sai kiểu: List<Integer> không thể chuyển thành List<String>
~~~

Generic trong Java thường **invariant**: `List<Integer>` không phải subtype của `List<Number>`, dù `Integer` là subtype của `Number`. Nếu viết method:

~~~java
static void show(java.util.List<Number> numbers) { }
~~~

thì một biến có kiểu `List<Integer>` không thể truyền trực tiếp cho `show(List<Number>)`. Điều này ngăn code trong method thêm một `Double` vào danh sách thực tế chỉ chấp nhận `Integer`.

Để **đọc** các giá trị số mà không cần thêm phần tử, có thể chọn tham số `List<? extends Number>`; danh sách `List<Integer>`, `List<Double>` và `List<Number>` phù hợp trong những ngữ cảnh tương ứng. Ngược lại, nếu method cần nhận một nơi chứa có thể **thêm Integer**, kiểu `List<? super Integer>` có thể phù hợp, với quy tắc đọc khác. Đừng dùng wildcard chỉ để tắt lỗi; chọn theo chức năng đọc/ghi thực tế.

### 7.1. Generic method và suy luận kiểu

Ví dụ:

~~~java
static <T> T echo(T value) {
    return value;
}
~~~

Đoạn này là khai báo method dùng trong một class. Lời gọi `String result = echo("Java");` hợp lệ vì compiler có thể suy luận kiểu `T` phù hợp. Trong các tình huống generic phức tạp, kiểu mong đợi ở ngữ cảnh nhận kết quả có thể tham gia suy luận kiểu; vì vậy việc chọn phương thức generic không thể luôn mô tả đơn giản là “chỉ nhìn literal rồi chốt kiểu”.

Điều quan trọng vẫn là: **các đối số phải đáp ứng quan hệ kiểu mà chữ ký phương thức yêu cầu**. Ví dụ:

~~~java
static <T extends Number> void numberOnly(T value) { }
~~~

`numberOnly(3)` hợp lệ vì `Integer` thuộc `Number`; `numberOnly("3")` không hợp lệ vì `String` không thỏa bound `T extends Number`.

### 7.2. Không thể overload chỉ bằng đối số generic bị xóa kiểu

Hai khai báo:

~~~java
// Hai dòng sau không thể cùng xuất hiện trong một lớp:
// void process(java.util.List<String> values) { }
// void process(java.util.List<Integer> values) { }
~~~

gây **name clash** liên quan đến type erasure. Dù khác phần `String` và `Integer`, JVM-erased parameter types đều là `List`. Đây là vấn đề hợp lệ của các khai báo overload, khác với việc một lời gọi có type arguments không phù hợp.

## 8. Thông báo lỗi khi truyền sai và cách đọc

Các thông báo cụ thể thay đổi tùy JDK và lời gọi. Nhưng phân tích thường bắt đầu bằng những câu sau:

| Nhóm lỗi | Tình huống | Cách sửa |
| --- | --- | --- |
| Thiếu đối số | `register("Lan",20)` khi chỉ có `register(String,int,boolean)` | Truyền đối số `boolean` thứ ba hoặc định nghĩa overload hợp lý |
| Thừa đối số | `register("Lan",20,true,1)` | Xóa đối số dư hoặc chọn API có bốn tham số thực sự |
| Sai thứ tự kiểu | `register(20,"Lan",true)` | Đổi thứ tự thành `String,int,boolean` |
| Không tương thích primitive | `readLong(true)` | Không thể chuyển `boolean` thành số; xem lại ý nghĩa dữ liệu |
| Không tự thu hẹp | `acceptByte(10)` với `acceptByte(byte)` | Dùng biến `byte`, cast an toàn có chủ ý hoặc đổi tham số thành `int` |
| Chưa có overload áp dụng | `send(404)` khi chỉ có overload `String` hoặc hai tham số | Sửa lời gọi theo API hoặc cung cấp overload có ý nghĩa |
| Lời gọi mơ hồ | `find(null)` với `find(String)`, `find(Integer)` | Chỉ rõ kiểu cần dùng; cân nhắc API ít overload mơ hồ |
| Truyền `Object` vào `String` | Biến khai báo `Object` dù đối tượng runtime là `String` | Kiểm tra kiểu và thu hẹp có chủ ý, hoặc thiết kế kiểu tĩnh phù hợp |
| `List<Integer>` vào `List<String>` | Generic type arguments khác nhau | Truyền collection đúng kiểu hoặc thay đổi abstraction đúng yêu cầu |
| Unboxing null | Biến `Integer` null truyền vào tham số `int` | Kiểm tra null, dùng giá trị mặc định có chủ ý hoặc thiết kế API nhận nullable |
| Tham số dạng mảng | Method nhận `int[]` nhưng caller truyền hai `int` | Truyền `new int[]{...}` hoặc dùng `int...` ở tham số cuối nếu cần varargs |
| Sai overload do boxing/widening | Kỳ vọng `Integer` nhưng `int` chọn `long` | Xem kiểu tĩnh và ba pha áp dụng; viết giá trị/kiểu rõ ràng khi cần |
| Lời gọi nhầm constructor | `new User("Lan", true)` khi constructor nhận `(String,int)` | Kiểm tra trực tiếp constructor signatures và thứ tự đối số |

Khi gặp lỗi `method ... cannot be applied to given types`, `no suitable method found`, `incompatible types` hoặc `reference ... is ambiguous`, nên đọc thông tin về **required** (kiểu tham số được yêu cầu), **found** (kiểu đối số compiler thấy) và **reason**. Đừng tự cast tất cả đối số chỉ để hết lỗi: compiler có thể đang báo một sai lệch nghiệp vụ.

### 8.1. Vì sao runtime không sửa được sai kiểu compile-time?

Xem đoạn minh họa:

~~~java
Object object = "Java";
// printNames(object); // Sai nếu printNames chỉ nhận List<String>
~~~

Một method đòi `List<String>` không thể nhận trực tiếp `Object` chỉ vì người lập trình biết `object` hiện chứa một `String` (thực tế dữ liệu cũng không đúng hình dạng list). Nên thiết kế kiểu/đối số phản ánh dữ liệu thật.

Ví dụ khác chính xác hơn cho quan hệ Object/String:

~~~java
static void printText(String text) {
    System.out.println(text);
}

// Trong một method:
Object object = "Java";
// printText(object); // Không biên dịch: Object không chuyển sang String ngầm định
if (object instanceof String text) {
    printText(text);    // Hợp lệ: text đã được kiểm tra là String
}
~~~

Các đoạn trên là ví dụ ghép vào lớp thích hợp, không phải tệp chương trình độc lập. Pattern matching cho `instanceof` có sẵn trong Java 17. Việc compiler kiểm tra kiểu tĩnh giúp phát hiện lỗi trước khi chương trình chạy; nhưng một số vấn đề dữ liệu như `null` hoặc kết quả ép kiểu có điều kiện vẫn cần xử lý ở runtime.

## 9. Constructor cũng được kiểm tra đối số

Constructor có tên cùng lớp và không có kiểu trả về. Khi tạo đối tượng, compiler cũng phải tìm constructor áp dụng đúng số lượng và kiểu đối số:

~~~java
class Ticket {
    final String event;
    final int seats;

    Ticket(String event, int seats) {
        this.event = event;
        this.seats = seats;
    }
}
~~~

Trong một method thích hợp:

~~~java
Ticket ok = new Ticket("Concert", 2);
// Ticket missing = new Ticket("Concert");     // Thiếu seats
// Ticket reversed = new Ticket(2, "Concert"); // Đảo kiểu đối số
// Ticket extra = new Ticket("Concert", 2, true); // Thừa đối số
~~~

Java hỗ trợ **constructor overloading**, nên một lớp có thể khai báo thêm `Ticket(String event)` để ấn định số ghế mặc định, miễn tuân thủ các quy tắc chữ ký. Khi dùng `this(...)` hoặc `super(...)` để gọi constructor khác, các đối số cũng phải tương thích với constructor được gọi.

**Không phân biệt overload constructor bằng kiểu trả về**, vì constructor không khai báo kiểu trả về. Đặt `void Ticket(...)` sẽ khai báo một method bình thường mang tên `Ticket`, không phải constructor.

## 10. Truyền đối số theo giá trị không có nghĩa đối tượng được sao chép

Sau khi compiler chọn phương thức áp dụng, tại runtime Java **đánh giá biểu thức đối số** rồi truyền **giá trị** vào parameter tương ứng:

- Với primitive, giá trị như `int 5` được sao chép vào parameter `int`.
- Với reference, **giá trị tham chiếu** được sao chép; cả caller và callee có thể trỏ tới cùng một đối tượng. Method có thể thay đổi đối tượng nếu đối tượng mutable và API cho phép.
- **Gán lại parameter** không gán lại biến của caller.

Ví dụ chạy độc lập **`ArgumentValuesDemo.java`**:

~~~java
public class ArgumentValuesDemo {
    static void update(int number, StringBuilder text) {
        number = 99;
        text.append("!");
        text = new StringBuilder("Other");
        System.out.println("inside=" + number + "," + text);
    }

    public static void main(String[] args) {
        int quantity = 5;
        StringBuilder label = new StringBuilder("Hi");

        update(quantity, label);
        System.out.println("outside=" + quantity + "," + label);
    }
}
~~~

Chạy:

~~~bash
javac ArgumentValuesDemo.java
java ArgumentValuesDemo
~~~

Output:

~~~text
inside=99,Other
outside=5,Hi!
~~~

Sự khác nhau xuất phát từ việc tham số `number` là bản sao số `5`, còn parameter `text` ban đầu chứa bản sao tham chiếu tới cùng `StringBuilder`. Lời gọi `text.append("!")` sửa đối tượng đó; sau đó việc gán `text = new StringBuilder("Other")` chỉ đổi biến parameter bên trong method.

**Liên hệ với kiểm tra đối số:** kiểu của `quantity` là `int`, kiểu của `label` là `StringBuilder`; compiler xác nhận cả hai tương thích với thứ tự tham số `(int,StringBuilder)` trước khi chương trình chạy. Java không đưa đối tượng vào method bằng cách truyền biến của caller theo tham chiếu.

## 11. Những bẫy nhỏ ảnh hưởng đến cách đọc lời gọi

### 11.1. Mảng khác chuỗi nhiều đối số

Giả sử:

~~~java
static int lengthOf(int[] numbers) {
    return numbers.length;
}
~~~

`lengthOf(new int[]{1,2,3})` là **một đối số kiểu `int[]`**, hợp lệ. `lengthOf(1,2,3)` là **ba đối số kiểu `int`**, không hợp lệ vì method không khai báo varargs. Nếu muốn hỗ trợ dạng nhiều số, khai báo `static int lengthOf(int... numbers)`, một cú pháp có nghĩa gọi biến độ dài và nhận mảng trong thân method.

### 11.2. Argument có thể là biểu thức phức tạp

`register("Lan".trim(), 18 + 2, !false)` vẫn có ba đối số, với kiểu tĩnh lần lượt `String`, `int`, `boolean`. Mỗi biểu thức được đánh giá để tạo **giá trị đối số**. Không đếm dấu phẩy trong generic type arguments hay trong lời gọi lồng nhau như những đối số độc lập của method ngoài; parser xác định cấu trúc cú pháp.

### 11.3. Thứ tự kiểu khác với thứ tự tên

Khai báo `void position(int x, int y)` không tự bảo vệ bạn khỏi `position(y, x)` khi cả hai biểu thức đều kiểu `int`. Compiler chỉ thấy lời gọi tương thích; kết quả nghiệp vụ có thể sai. Nếu tham số cùng kiểu nhưng ý nghĩa dễ nhầm, dùng biến có tên rõ, object chứa cấu hình, hoặc thiết kế API diễn đạt ý định.

### 11.4. Static type khác runtime class

Nếu có overload `display(Object)` và `display(String)`, biến `Object ref = "Java";` khi gọi `display(ref)` chọn overload `display(Object)` dựa trên kiểu tĩnh `Object`, dù đối tượng thực là `String`. Nếu method được chọn là instance method và bị override thì dispatch động có thể chọn implementation khi chạy, nhưng **overload resolution đã xảy ra lúc biên dịch**. Không dùng loại runtime của đối tượng để giả định overload được chọn.

### 11.5. Không có chuyển đổi từ mọi chuỗi sang số

Dù `"42"` chứa ký tự số, `sum("42", 3)` không phù hợp với `sum(int,int)`. Nếu dữ liệu thật sự là văn bản nhập vào, chuyển đổi có chủ ý qua `Integer.parseInt("42")`, đồng thời xử lý `NumberFormatException` nếu dữ liệu không hợp lệ.

### 11.6. Truyền `null` có thể hợp lệ về kiểu nhưng sai nghiệp vụ

Một parameter kiểu tham chiếu như `String` về mặt hệ thống kiểu Java thông thường có thể nhận `null`, trừ khi API dùng các công cụ kiểm tra hoặc hợp đồng cụ thể khác. Compiler không mặc nhiên ngăn `greet(null)`; nếu thân method gọi `name.length()`, có nguy cơ `NullPointerException`. Khi cần giá trị không null, dùng kiểm tra ở điểm vào hoặc các cơ chế phân tích phù hợp.

## 12. Quy trình kiểm tra lời gọi từng bước

Khi đọc `service.process(arg1, arg2, ...)`, hãy kiểm tra:

1. **Đối tượng/kiểu nhận lời gọi và tên method**: xác định các phương thức tên `process` có thể truy cập, trong phạm vi hợp lệ. Quy tắc `static`, instance và quyền truy cập có thể loại một số ứng viên.
2. **Đếm đối số ở lời gọi**: không nhầm số phần tử của mảng truyền vào với số đối số. Xem có overload/varargs thích hợp không.
3. **Xác định kiểu tĩnh từng biểu thức**: literal, biến, biểu thức toán học, lời gọi method, generic method invocation. Đừng đoán từ giá trị runtime.
4. **Ghép thứ tự từng đối số với từng tham số**: vị trí 1 với vị trí 1, vị trí 2 với vị trí 2; Java không tự đổi chỗ theo tên.
5. **Xét chuyển đổi hợp lệ**: exact, primitive/reference widening, boxing/unboxing và những chuyển đổi của các pha giải quyết overload; không tự cho phép narrowing hoặc parse chuỗi.
6. **Nếu có nhiều overload**, áp dụng pha applicability và quy tắc most-specific. Kiểm tra khả năng **ambiguous method call**.
7. **Nếu có generics**, xét bounds, type inference, invariance/wildcards; không suy luận rằng tất cả `List<...>` có thể truyền thay nhau.
8. **Nếu có varargs**, tách tham số cố định và phần cuối dạng mảng/varargs; bảo đảm mỗi phần tử có kiểu tương thích.
9. **Kiểm tra ý nghĩa nghiệp vụ**: dù compiler chấp nhận, đảo hai số cùng kiểu hoặc truyền null vẫn có thể sai.
10. **Khi có lỗi**, so thông tin `required`, `found` và danh sách candidate methods; sửa nguyên nhân ở kiểu, số lượng, thứ tự hoặc API.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `static void order(String id, int count)` được gọi bằng `order(4, "X")`. Có hợp lệ không?  
**Đáp án:** Không, nếu đó là overload duy nhất. Hai đối số bị đảo thứ tự kiểu. Sửa thành `order("X", 4)`.

**Câu 2.** `static void scale(long value)` gọi bằng `scale(10)` có hợp lệ không?  
**Đáp án:** Có. `int` của literal `10` có thể widening thành `long`.

**Câu 3.** `static void byteValue(byte b)` gọi bằng `byteValue(10)` có tự hợp lệ vì `10` nằm trong phạm vi byte không?  
**Đáp án:** Không. Method invocation không tự thu hẹp literal `int` xuống `byte`. Dùng biến có kiểu `byte`, cast có chủ ý, hoặc thiết kế method nhận `int`.

**Câu 4.** Với `static void labels(String... items)`, `labels()`, `labels("A")` và `labels("A", "B")` có hợp lệ không?  
**Đáp án:** Có. Phần varargs cho phép 0, 1 hoặc nhiều `String`.

**Câu 5.** Giả sử có `f(long)` và `f(Integer)`; `f(5)` thường chọn overload nào?  
**Đáp án:** `f(long)`, vì primitive widening áp dụng ở pha strict trước khi cần boxing `int -> Integer`.

**Câu 6.** Với `void pick(String)` và `void pick(Integer)`, `pick(null)` có luôn chọn overload nào đó không?  
**Đáp án:** Không. Trong trường hợp này lời gọi mơ hồ vì hai kiểu tham chiếu không có quan hệ most-specific đủ để chọn duy nhất.

**Câu 7.** Biến `List<Integer> ages` có trực tiếp phù hợp với tham số `List<Number>` không?  
**Đáp án:** Không. Java generics thường invariant. Nếu chỉ cần đọc các số, `List<? extends Number>` có thể là tham số phù hợp hơn.

**Câu 8.** `subtract(9, 4)` và `subtract(4, 9)` có khác nhau về kiểm tra kiểu không, nếu cả hai tham số đều là `int`?  
**Đáp án:** Cả hai đều hợp lệ về kiểu và số lượng, nhưng kết quả toán học khác nhau. Compiler không xác định ý nghĩa “số bị trừ” thay cho lập trình viên.

**Câu 9.** `Object obj = "A";`, method duy nhất `consume(String)`. `consume(obj)` có tự hợp lệ vì obj đang chứa String không?  
**Đáp án:** Không. Kiểu tĩnh của `obj` là `Object`; cần kiểm tra và thu hẹp có chủ ý hoặc đổi kiểu khai báo phù hợp.

**Câu 10.** Nếu phương thức nhận `int[]`, `call(new int[]{1,2})` và `call(1,2)` có cùng số lượng đối số không?  
**Đáp án:** Không. Lời gọi đầu có **một đối số là mảng**; lời gọi sau có **hai đối số là số nguyên**. Phương thức chỉ nhận `int[]` không nhận dạng gọi thứ hai trừ khi khai báo API hỗ trợ biến độ dài.

## Ghi nhớ

Khi gọi một phương thức Java, **số lượng**, **thứ tự** và **kiểu tĩnh của đối số** phải phù hợp với một phương thức hoặc constructor có thể áp dụng. Java ghép đối số **theo vị trí**, không theo tên tham số. Compiler cho phép một số chuyển đổi như widening, boxing/unboxing và varargs nhưng không tùy ý narrowing hay parse chuỗi thành số. Khi có nhiều overload, Java giải quyết theo các pha và quy tắc chọn phương thức cụ thể nhất; generic type bounds và `null` cũng có thể quyết định lời gọi hợp lệ hay bị lỗi. Sau khi kiểm tra hợp lệ, biểu thức đối số được đánh giá **từ trái sang phải** và giá trị của chúng được truyền vào các tham số. Kiểm tra biên dịch giúp tránh lỗi kiểu/số lượng, còn đúng **ý nghĩa nghiệp vụ** của thứ tự đối số vẫn cần người viết mã bảo đảm.
