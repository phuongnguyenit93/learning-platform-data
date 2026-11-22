# Cấu trúc khai báo phương thức và ý nghĩa từng thành phần trong Java

Trong Java, **phương thức (method)** xác định một thao tác có thể thực hiện trong phạm vi lớp, interface hoặc một kiểu khai báo thích hợp. Một khai báo phương thức trả lời các câu hỏi: **ai được gọi**, **gọi bằng tên nào**, **cần cung cấp những dữ liệu gì**, **trả lại kết quả gì**, **có thể báo lỗi nào**, và **mã nào được thực thi** khi gọi. Hiểu cấu trúc khai báo là bước nền trước khi sử dụng phương thức của đối tượng và thiết kế API dễ đọc.

Bài này dùng Java 17 trở lên, phân tích từ phương thức đơn giản đến phương thức có generic, tham số biến độ dài, ngoại lệ và phương thức đặc biệt trong lớp trừu tượng/interface.

## 1. Nhìn tổng thể một khai báo phương thức

Xét phương thức trong một lớp:

~~~java
public final int addPoints(int amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("Điểm không được âm");
    }
    points = Math.addExact(points, amount);
    return points;
}
~~~

Đây là **đoạn phương thức nằm trong một lớp có trường `int points`**, chưa phải một tệp độc lập. Các thành phần gồm:

| Thành phần | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Modifier quyền truy cập | `public` | Xác định phạm vi mã được phép gọi phương thức |
| Modifier hành vi | `final` | Ngăn lớp con override phương thức instance này |
| Kiểu trả về | `int` | Kết quả được trả về là số nguyên `int` |
| Tên phương thức | `addPoints` | Định danh dùng trong lời gọi |
| Danh sách tham số | `(int amount)` | Nhận một đối số `int`, gán cho tham số `amount` |
| Thân phương thức | `{ ... }` | Chứa các câu lệnh thực hiện công việc |
| Câu lệnh trả về | `return points;` | Kết thúc lời gọi hiện tại và trả về giá trị |

Phương thức ở trên không khai báo `throws`, nhưng vẫn có thể ném ngoại lệ **unchecked**, chẳng hạn `IllegalArgumentException` hoặc `ArithmeticException` từ `Math.addExact`. Việc có `throws` hay không không phải là cam kết rằng phương thức không bao giờ ném ngoại lệ.

### Mẫu cú pháp khái quát

~~~text
[annotation]
[method-modifier ...] [<type-parameters>] return-type methodName(
    [formal-parameters]
) [throws ExceptionType1, ExceptionType2] {
    // method body
}
~~~

Dấu ngoặc vuông trong sơ đồ biểu diễn **thành phần tùy chọn khi giải thích cú pháp**, không phải ký tự gõ nguyên xi vào Java. Các phần luôn cần trong một khai báo phương thức thông thường có thân là **kiểu trả về, tên, dấu ngoặc tròn và thân**; modifier, generic type parameters, tham số và `throws` có thể vắng mặt.

Ví dụ tối giản hợp lệ bên trong một lớp:

~~~java
void greet() {
    System.out.println("Xin chào");
}
~~~

Trong ví dụ này, phương thức có quyền truy cập mặc định của package (không viết `public`, `protected` hoặc `private`), không cần đối số và không trả về giá trị. **Dấu ngoặc `()` vẫn bắt buộc trong phần khai báo**, dù không có tham số.

## 2. Modifier: quyền truy cập và tính chất phương thức

Một phương thức có thể có modifier quyền truy cập và modifier thay đổi cách sử dụng. Không phải modifier nào cũng hợp lệ cùng lúc hoặc trong mọi loại khai báo.

### Các mức truy cập

| Cách khai báo | Quyền gọi cơ bản |
| --- | --- |
| `public` | Mã truy cập được lớp chứa có thể gọi, tùy các ràng buộc module và kiểu khác |
| `protected` | Cùng package hoặc những ngữ cảnh lớp con được phép theo quy tắc Java |
| *Không ghi access modifier* | **Package-private**: các kiểu trong cùng package |
| `private` | Chỉ trong phạm vi lớp hoặc kiểu khai báo được phép theo quy tắc truy cập Java; các nestmate có cơ chế truy cập tương ứng |

Nói một phương thức `public` không có nghĩa mọi mã đều có thể gọi bất chấp lớp chứa `private`/package-private hay package chưa được `exports` trong hệ thống module. **Khả năng truy cập phương thức còn phụ thuộc kiểu chứa phương thức và ngữ cảnh sử dụng**.

Một phương thức khai báo **không ghi access modifier** là package-private. `default` trong `default void run() { ... }` của interface là **modifier phương thức có thân mặc định**, không phải từ khóa chỉ mức truy cập “default”.

### Các modifier hành vi thường gặp

| Modifier | Ý nghĩa chính | Cần chú ý |
| --- | --- | --- |
| `static` | Phương thức thuộc lớp, gọi qua tên lớp; không có `this` | Không trực tiếp dùng instance field nếu không có đối tượng |
| `final` | Cấm override phương thức instance ở lớp con | Không áp dụng để làm giá trị trả về bất biến |
| `abstract` | Khai báo phương thức chưa có triển khai, thân kết thúc bằng `;` | Lớp chứa phải abstract, trừ ngữ cảnh interface thích hợp |
| `synchronized` | Đồng bộ lúc thực thi theo monitor của instance hoặc `Class` nếu static | Không thay thế thiết kế đồng thời đúng trên toàn bộ hệ thống |
| `native` | Khai báo phương thức được triển khai bằng cơ chế native | Không có thân Java; ít dùng trong mã ứng dụng thông thường |
| `strictfp` | Modifier lịch sử liên quan dấu phẩy động | Java 17 đã dùng ngữ nghĩa dấu phẩy động chặt chẽ; không cần nó cho mã mới |

Một khai báo không thể vừa `abstract` vừa `final`; `abstract` cần được triển khai bằng override trong lớp con cụ thể, còn `final` ngăn override. Một phương thức `abstract` cũng không khai báo `static` hoặc `private` theo cách trái với các quy tắc này.

**Thông thường**, trong ví dụ ứng dụng, ta dùng `public` cho thao tác cung cấp ra ngoài, `private` cho chi tiết triển khai, `static` cho thao tác không phụ thuộc trạng thái của một instance và `final` khi thật sự muốn cấm override.

## 3. Kiểu trả về: `void` và phương thức trả về giá trị

Sau modifier là kiểu trả về, ví dụ `int`, `String`, `boolean`, `List<String>`, `int[]` hoặc `void`.

- **`void`:** phương thức không trả một giá trị kết quả. Có thể viết `return;` để kết thúc sớm, hoặc đi đến cuối thân phương thức.
- **Kiểu cụ thể:** phương thức phải bảo đảm các đường kết thúc bình thường trả về một biểu thức phù hợp với kiểu khai báo, chẳng hạn `return count;` nếu trả `int`.
- **Kiểu tham chiếu:** có thể trả về một tham chiếu tới đối tượng, ví dụ `String`, `Student`, `List<String>`; kiểu trả về không tự tạo đối tượng.
- **Mảng:** `int[] scores()` trả một tham chiếu đến mảng `int[]`.

Các ví dụ hợp lệ khi đặt trong lớp:

~~~java
void reset() {
    count = 0;
}

int count() {
    return count;
}

String status(boolean ready) {
    if (ready) {
        return "READY";
    }
    return "WAITING";
}
~~~

Giả định lớp có trường `int count`. Đoạn này chỉ minh họa phương thức; chưa phải một chương trình có `main`.

Một ví dụ lỗi cố ý:

~~~java
int broken(boolean ok) {
    if (ok) {
        return 1;
    }
    // Lỗi biên dịch: có đường đi kết thúc bình thường mà không trả int
}
~~~

**`return` và `System.out.println` không đồng nghĩa.** `println` hiển thị ra stdout, còn `return` truyền giá trị kết quả về nơi gọi. Một phương thức có thể in dữ liệu nhưng không trả giá trị, trả giá trị nhưng không in, hoặc làm cả hai.

## 4. Tên phương thức và quy ước đặt tên

Tên phương thức là định danh như `calculateTotal`, `isReady`, `getBalance`. Quy tắc định danh của Java áp dụng: không được dùng keyword `class`, `return` làm tên phương thức theo cách thông thường, không bắt đầu bằng chữ số, và có phân biệt chữ hoa/chữ thường.

Quy ước Java phổ biến là **lowerCamelCase**:

- `deposit`, `withdraw`: động từ thể hiện thao tác thay đổi trạng thái;
- `calculateTotal`: hành vi tính toán;
- `isActive`, `hasPermission`: câu hỏi cho giá trị `boolean`;
- `balance`, `getBalance`: cung cấp trạng thái đọc nếu có lý do công khai.

Nên đặt tên thể hiện mục đích thay vì tên mơ hồ như `doSomething`. Tên phương thức là một phần API mà người gọi phải hiểu, nên dễ đọc quan trọng hơn việc rút ngắn vài ký tự.

Tên phương thức có phân biệt chữ hoa/thường: `print` và `Print` là hai tên khác nhau. Đừng dùng cách khác hoa/thường để tạo hai hành vi khó phân biệt.

## 5. Danh sách tham số hình thức

Tham số hình thức (*formal parameter*) được khai báo **trong dấu ngoặc tròn**; từng tham số thông thường có kiểu và tên:

~~~java
int multiply(int left, int right) {
    return left * right;
}
~~~

Khi gọi `multiply(3, 4)`, hai biểu thức `3`, `4` là **đối số (arguments)**; còn `left`, `right` là **tham số** trong thân phương thức. Thứ tự đối số tương ứng thứ tự tham số, và Java kiểm tra kiểu có tương thích hay có phép chuyển đổi được phép.

Một phương thức có thể không có tham số: `balance()`. Có nhiều tham số thì ngăn cách bằng dấu phẩy: `transfer(Account receiver, long amount)`.

Tham số có thể có modifier `final` và annotation thích hợp:

~~~java
void printLabel(final String label) {
    System.out.println(label);
}
~~~

`final` ở đây **cấm gán lại biến tham số** `label` trong phương thức, nhưng không tự bảo đảm mọi đối tượng được tham chiếu là bất biến. Tham số cũng có thể là kiểu nguyên thủy, kiểu tham chiếu, mảng và kiểu generic phù hợp.

### Java luôn truyền đối số theo giá trị

Với `int amount`, bản sao của giá trị số nguyên được gán cho tham số. Với `Account account`, bản sao **giá trị tham chiếu** được gán cho tham số; cả người gọi và phương thức có thể chỉ đến cùng một đối tượng. Phương thức có thể đổi trạng thái đối tượng nếu được phép, nhưng gán `account = new Account(...)` trong thân phương thức không làm biến của người gọi trỏ đến đối tượng mới.

Phân biệt điều này với “truyền tham chiếu” theo nghĩa ngôn ngữ khác; Java truyền **giá trị**, kể cả khi giá trị ấy là một tham chiếu.

## 6. Varargs: số lượng đối số thay đổi

Cú pháp `Type... name` khai báo **tham số biến độ dài** (*variable arity parameter*), gọi tắt là *varargs*. Ví dụ:

~~~java
int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(total, number);
    }
    return total;
}
~~~

`sum(1, 2, 3)` trả 6; `sum()` trả 0; có thể gọi bằng mảng `sum(new int[] {1, 2, 3})` vì tại thời điểm thực thi, tham số varargs được xử lý như một mảng.

Quy tắc khai báo:

- Mỗi phương thức tối đa **một** tham số varargs.
- Nếu có varargs, nó phải là **tham số cuối cùng**.
- Viết `int... numbers`, không viết `int numbers...`.
- Thân phương thức có thể dùng `numbers.length`, `numbers[index]` và vòng lặp trên mảng.

Ví dụ **sai cú pháp cố ý**, không thể biên dịch:

~~~java
void invalid(String... names, int year) {
}
~~~

Varargs không có nghĩa mọi cách gọi đều hợp lệ: Java vẫn kiểm tra kiểu đối số, và các lời gọi có overload/varargs đôi khi có thể trở nên mơ hồ.

## 7. Generic method: tham số kiểu đặt trước kiểu trả về

Trong generic method, **danh sách tham số kiểu** (*type parameters*) được đặt **sau modifier nhưng trước kiểu trả về**.

~~~java
public static <T extends CharSequence> String describe(T label, int value) {
    return label + " = " + value;
}
~~~

Ở đây:

- `public static`: modifier.
- `<T extends CharSequence>`: khai báo tham số kiểu `T`, có giới hạn trên là `CharSequence`.
- `String`: kiểu **trả về**, độc lập với việc chọn `T`.
- `describe`: tên phương thức.
- `(T label, int value)`: danh sách tham số gồm một giá trị kiểu `T` và một `int`.

Có thể truyền `String` hoặc `StringBuilder` làm `label` vì cả hai tương thích với `CharSequence`. Trình biên dịch thường suy luận `T` từ đối số; khi cần có thể ghi type witness, chẳng hạn `Example.<String>describe("x", 3)` nếu phương thức nằm trong lớp `Example`.

Đừng nhầm `<T>` đứng **trước** kiểu trả về với `List<T>` **làm** kiểu trả về. Một phương thức generic có thể đồng thời có cả hai:

~~~java
static <T> java.util.List<T> singleton(T element) {
    return java.util.List.of(element);
}
~~~

Đoạn này độc lập ở mức khai báo trong lớp; `List.of` không nhận `null` làm phần tử và có thể ném `NullPointerException`.

## 8. Mệnh đề `throws` và phân biệt với `throw`

`throws` xuất hiện **sau dấu ngoặc tròn** (và sau các dấu ngoặc mảng nếu dùng cú pháp mảng hậu tố không khuyến khích), trước thân phương thức:

~~~java
static String readFirstLine(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
~~~

Đoạn này minh họa một phương thức đặt trong lớp, dùng API Java 17+. `throws java.io.IOException` thông báo rằng thao tác có thể ném một **checked exception**; bên gọi thông thường phải `catch` hoặc tiếp tục khai báo `throws` thích hợp. Phương thức đọc có thể trả `null` nếu tệp không có dòng nào.

So sánh:

| Từ khóa | Vị trí thường gặp | Ý nghĩa |
| --- | --- | --- |
| `throws IOException` | Trong **header** của phương thức | Khai báo loại ngoại lệ có thể lan ra để trình biên dịch kiểm tra |
| `throw new IOException("...")` | Trong **thân** phương thức | Thực sự ném một đối tượng ngoại lệ tại thời điểm thực thi |
| `return value` | Trong **thân** phương thức | Trả kết quả và kết thúc lời gọi bình thường |

Một phương thức có thể khai báo `throws A, B` cho nhiều kiểu exception thích hợp. Với **unchecked exception** như `IllegalArgumentException`, Java không yêu cầu khai báo `throws`. Khai báo `throws` không bắt buộc có một lệnh `throw` trực tiếp trong thân: ngoại lệ cũng có thể phát sinh từ phương thức được gọi.

## 9. Thân phương thức và quy tắc kết thúc

Phần `{ ... }` là **method body**, chứa các khai báo biến cục bộ, câu lệnh, lời gọi phương thức, điều kiện, vòng lặp, `try`/`catch` và `return` phù hợp.

~~~java
static String verdict(int score) {
    if (score >= 5) {
        return "PASS";
    }
    return "RETRY";
}
~~~

Khi gọi `verdict(7)`, nhánh `if` trả `"PASS"`; phần sau không được thực thi trong lời gọi ấy. Khi gọi `verdict(3)`, kết quả là `"RETRY"`.

Một phương thức `void` có thể đi đến dấu `}` cuối thân mà không cần `return;`. Với phương thức trả giá trị, Java không cho phép đường thực thi bình thường rơi ra khỏi cuối thân mà thiếu giá trị trả về.

Đặc biệt, **không phải mọi phương thức đều có thân trong chính khai báo**. Phương thức `abstract` hoặc `native` kết thúc bằng dấu `;`, còn triển khai đến từ lớp con hoặc mã native tương ứng:

~~~java
abstract class Shape {
    abstract double area();
}
~~~

*Đây là đoạn định nghĩa lớp trừu tượng minh họa; không có `main`.* Không viết `{ }` cho `abstract double area();`; nếu viết thân rỗng, khai báo không còn tuân theo cú pháp phương thức abstract.

## 10. Ví dụ đầy đủ: đọc từng phần và chạy thử

Tạo tệp **`MethodDeclarationDemo.java`**. Tệp có lớp `Report` ở mức package và một lớp `public MethodDeclarationDemo` chứa `main`.

~~~java
import java.io.IOException;

class Report {
    private int total;

    Report(int opening) {
        if (opening < 0) {
            throw new IllegalArgumentException("Số ban đầu không được âm");
        }
        this.total = opening;
    }

    public int add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Số cộng không được âm");
        }
        total = Math.addExact(total, amount);
        return total;
    }

    public void print() {
        System.out.println("Total: " + total);
    }

    public void print(String prefix) {
        System.out.println(prefix + total);
    }

    public static boolean isValid(int amount) {
        return amount >= 0;
    }

    public static <T extends CharSequence> String join(
            T label, String... parts) throws IOException {
        if (parts.length == 0) {
            throw new IOException("Thiếu nội dung");
        }
        return label + ": " + String.join(", ", parts);
    }
}

public class MethodDeclarationDemo {
    public static void main(String[] args) {
        Report report = new Report(10);

        System.out.println(report.add(5));
        report.print();
        report.print("Số dư = ");
        System.out.println(Report.isValid(0));

        try {
            System.out.println(Report.join(
                    new StringBuilder("Mục"), "A", "B"));
            Report.join("Rỗng");
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac -encoding UTF-8 MethodDeclarationDemo.java
java MethodDeclarationDemo
~~~

Stdout:

~~~text
15
Total: 15
Số dư = 15
true
Mục: A, B
Lỗi: Thiếu nội dung
~~~

### Phân tích từng khai báo trong chương trình

**Constructor `Report(int opening)`:** trông gần giống phương thức, nhưng đây là **constructor**, không phải method theo ngữ nghĩa khai báo Java. Nó có tên trùng lớp và **không có kiểu trả về**, kể cả `void`. `new Report(10)` tạo đối tượng rồi khởi tạo trường `total` qua constructor.

**`public int add(int amount)`:** `public` là quyền truy cập, `int` là kiểu trả về, `add` là tên, `amount` là tham số kiểu `int`. Trong thân, điều kiện không hợp lệ ném ngoại lệ; nếu hợp lệ, trường instance `total` được cộng và phương thức trả số dư mới.

**`public void print()`:** không có tham số, kiểu trả về `void`. Nó in `Total: 15`, **không trả giá trị** cho biến phía gọi.

**`public void print(String prefix)`:** cùng tên `print` nhưng có thêm tham số. Đây là một **overload** khác của `print`; JVM/compiler phân biệt hai lời gọi theo danh sách tham số thích hợp.

**`public static boolean isValid(int amount)`:** phương thức static, dùng `Report.isValid(0)` mà không cần một đối tượng `Report` nhận lời gọi. Phương thức không phụ thuộc trường `total` của instance và trả `boolean`.

**`public static <T extends CharSequence> String join(T label, String... parts) throws IOException`:** cùng lúc minh họa quyền truy cập, modifier static, tham số kiểu generic, kiểu trả về `String`, tham số thông thường, varargs và mệnh đề checked exception. Lời gọi với `StringBuilder` cho thấy `T` không buộc phải là `String`.

**`public static void main(String[] args)`:** điểm vào thông dụng khi chạy ứng dụng Java 17 theo cách cổ điển. `public` cho phép launcher truy cập, `static` cho phép chạy không cần tạo `MethodDeclarationDemo`, `void` không trả kết quả, `String[] args` nhận đối số dòng lệnh (có thể không có phần tử).

Số tiền, điểm hay tổng ở đây chỉ là dữ liệu minh họa; điều quan trọng là **cùng một khuôn cấu trúc khai báo** có thể biểu diễn các hành vi rất khác nhau.

## 11. Phương thức instance và phương thức static

Hai dạng này cùng có cấu trúc header–body, nhưng cách gọi và quyền tiếp cận trạng thái khác nhau:

| Đặc điểm | Instance method | Static method |
| --- | --- | --- |
| Ví dụ khai báo | `int add(int amount)` | `static boolean isValid(int amount)` |
| Cách gọi thông thường | `report.add(5)` | `Report.isValid(5)` |
| Có `this`? | Có (trong ngữ cảnh thích hợp) | Không |
| Truy cập field instance? | Có thể dùng trực tiếp field của `this` | Cần có tham chiếu tới một đối tượng |
| Có thể overload? | Có | Có |
| Override trong lớp con? | Có khi đủ điều kiện và không `final` | Static method **không override**; có thể bị *hide* |

Không nên gọi phương thức static qua biến đối tượng (dù Java có các trường hợp cho phép) vì cách viết `Report.isValid(...)` thể hiện rõ đây là thao tác cấp lớp.

Trong `Report.add`, tên `total` tương đương `this.total` khi không có biến khác che tên. Còn `Report.isValid` không thể viết `this.total`, do phương thức static không có `this`.

## 12. Overloading: cùng tên nhưng khác danh sách tham số

Hai khai báo dưới đây trong `Report` hợp lệ:

~~~java
public void print() {
    System.out.println("Total: " + total);
}

public void print(String prefix) {
    System.out.println(prefix + total);
}
~~~

Chúng khác **số lượng và kiểu tham số**, nên trình biên dịch có thể chọn phương thức phù hợp với `report.print()` hoặc `report.print("Số dư = ")`.

Theo Java Language Specification, **method signature** liên quan đến **tên phương thức và danh sách kiểu tham số hình thức** theo những quy tắc tương thích/generic cụ thể. Nó **không gồm kiểu trả về, tên biến tham số, access modifier hay mệnh đề throws** để phân biệt overload.

Ví dụ cố ý gây lỗi:

~~~java
int size() {
    return 1;
}

long size() {
    return 2L;
}
~~~

Nếu đặt hai khai báo này trong cùng một lớp, compiler báo **trùng khai báo phương thức**: chỉ khác kiểu trả về `int` và `long` là chưa đủ tạo một overload hợp lệ.

Tương tự, việc thay `int value` bằng `int count` **chỉ đổi tên tham số**, không tạo chữ ký mới. Varargs `String... values` được xem như kiểu mảng `String[]` trong chữ ký; không thể khai báo thêm overload `void test(String[] values)` bên cạnh `void test(String... values)` của cùng lớp như thể chúng là hai chữ ký riêng.

Đừng nhầm **overloading** (nhiều phương thức cùng tên với tham số khác nhau) và **overriding** (lớp con đưa ra triển khai thay thế một phương thức instance đủ điều kiện của lớp cha).

## 13. Overriding và annotation `@Override`

Annotation có thể xuất hiện trước modifier của phương thức. `@Override` yêu cầu compiler kiểm tra rằng phương thức thực sự override hoặc triển khai phương thức phù hợp từ lớp cha/interface.

Ví dụ độc lập: tạo tệp **`OverrideMethodDemo.java`**:

~~~java
class Message {
    public String text() {
        return "Base";
    }
}

class FriendlyMessage extends Message {
    @Override
    public String text() {
        return "Hello";
    }
}

public class OverrideMethodDemo {
    public static void main(String[] args) {
        Message message = new FriendlyMessage();
        System.out.println(message.text());
    }
}
~~~

~~~bash
javac OverrideMethodDemo.java
java OverrideMethodDemo
~~~

Stdout:

~~~text
Hello
~~~

`@Override` là annotation; nó không phải kiểu trả về. `public String text()` trong lớp con có cùng tên và danh sách tham số với phương thức được override, và có kiểu trả về tương thích. Nếu vô tình đổi tên thành `texts()`, compiler báo lỗi nhờ `@Override`. Trong ví dụ này, gọi `message.text()` chọn triển khai của **đối tượng thực tế** `FriendlyMessage`.

`@Override` không thay thế quy tắc override: không thể override phương thức `final` hợp lệ ở lớp cha; phương thức static không được override, chỉ có thể bị che theo quy tắc hiding.

## 14. Khác biệt khi khai báo phương thức trong interface

Interface có thể khai báo phương thức trừu tượng, phương thức `default`, `static` và `private` theo các quy tắc của phiên bản Java hiện đại.

Ví dụ định nghĩa kiểu (không chứa `main`):

~~~java
interface Greeter {
    String greet(String name);

    default String greetMorning(String name) {
        return "Good morning, " + name;
    }

    static boolean validName(String name) {
        return name != null && !name.isBlank();
    }

    private String prefix() {
        return "Hello";
    }

    default String greetWithPrefix(String name) {
        return prefix() + ", " + name;
    }
}
~~~

Giải thích:

- `String greet(String name);` là phương thức trừu tượng của interface, ngầm hiểu `public abstract`. Nó có **dấu `;` thay vì body**, và một lớp triển khai cụ thể phải cung cấp triển khai tương ứng nếu không được kế thừa triển khai hợp lệ.
- `default String greetMorning(...)` có thân thực thi mặc định và được phép trong interface.
- `static boolean validName(...)` thuộc chính interface, gọi qua `Greeter.validName(...)`.
- `private String prefix()` là phương thức trợ giúp nội bộ trong interface (Java 9+), có thân và không được các lớp triển khai gọi trực tiếp như phương thức public.

Modifier `default` trong interface **khác hẳn** tình huống lớp không viết access modifier (package-private). Trên Java 17, không thể tự ý dùng `default` làm method modifier trong một lớp thông thường giống như trong interface.

## 15. Những lỗi cú pháp, kiểu và khai báo thường gặp

| Lỗi | Ví dụ sai hoặc hiểu nhầm | Cách hiểu đúng |
| --- | --- | --- |
| Quên kiểu trả về | `public calculate() { ... }` trong lớp không tên `calculate` | Phương thức phải có kiểu trả về như `void`, `int`, `String`; constructor là trường hợp riêng |
| Ghi `void` cho constructor | `void Report(int opening) { ... }` | Đây trở thành một phương thức tên `Report`, **không phải constructor** |
| Quên `()` | `void greet { ... }` | Cần `void greet() { ... }` |
| Trả sai kiểu | `int count() { return "x"; }` | Biểu thức sau `return` phải phù hợp kiểu `int` |
| Thiếu return | `int count() { if (ok) return 1; }` | Các đường kết thúc bình thường phải trả giá trị |
| Trả giá trị từ `void` | `void run() { return 1; }` | `void` chỉ có thể `return;` hoặc kết thúc thân |
| Dùng `this` trong static | `static void run() { this.run(); }` | Static method không có `this` |
| Đặt varargs ở giữa | `void f(int... values, String name)` | Varargs, nếu có, phải đứng cuối |
| Sai vị trí tham số kiểu | `static String <T> f(T x)` | Viết `static <T> String f(T x)` |
| Định nghĩa overload chỉ khác return | `int f()` và `String f()` | Cùng chữ ký, không phải hai overload hợp lệ |
| Nhầm `throws` với `throw` | `throws new IOException()` trong header | `throws IOException` khai báo kiểu; `throw new IOException()` trong thân |
| Dùng `abstract` cùng body | `abstract void f() { }` | Phương thức abstract kết thúc bằng `;` |
| Dùng `default` như package-private | `default void f() { }` ở lớp thường | Package-private là **không ghi access modifier** |
| Nhầm tham số với đối số | Gọi `add(amount)` rồi cho `amount` là declaration | `int amount` ở khai báo là parameter; biểu thức khi gọi là argument |

Một lỗi khác là **khai báo phương thức trong thân một phương thức khác** như “hàm lồng nhau”. Java không hỗ trợ khai báo một phương thức thông thường trực tiếp bên trong một phương thức khác; cần đưa khai báo thành thành viên của lớp hoặc dùng một cấu trúc phù hợp như lambda cho một chức năng cụ thể.

## 16. Cách đọc nhanh một khai báo phức tạp

Xem dòng khai báo sau (đây chỉ là header; thân đã có trong phương thức `Report.join` ở ví dụ hoàn chỉnh):

~~~java
public static <T extends CharSequence> String join(
        T label, String... parts) throws IOException
~~~

Đọc từ trái sang phải:

1. `public` — bên gọi có quyền truy cập theo ngữ cảnh.
2. `static` — thao tác thuộc lớp, không có `this`.
3. `<T extends CharSequence>` — khai báo kiểu tổng quát `T`.
4. `String` — kiểu kết quả.
5. `join` — tên phương thức.
6. `T label` — tham số thứ nhất, có kiểu `T`.
7. `String... parts` — tham số cuối nhận một số lượng biến đổi phần tử `String`.
8. `throws IOException` — thông báo checked exception có thể lan tới bên gọi.
9. `{ ... }` ở bản định nghĩa thực tế — chứa câu lệnh thực hiện thao tác.

Cách đọc này hữu ích khi gặp chữ ký phương thức của thư viện Java. Đọc được khai báo cho phép dự đoán phương thức được phép gọi ở đâu và kiểm tra kiểu đầu vào/đầu ra trước khi viết mã thực thi.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Trong `private static long multiply(int a, int b)`, đâu là access modifier, modifier cấp lớp, kiểu trả về, tên và tham số?

**Câu 2.** Sửa khai báo `public sum(int a, int b) { return a + b; }` thành phương thức trả tổng nguyên hợp lệ, không nhầm với constructor.

**Câu 3.** Vì sao `void send(String... messages, boolean urgent)` không hợp lệ? Nếu muốn truyền nhiều thông điệp, hãy sửa vị trí tham số.

**Câu 4.** Một phương thức ghi `int value()` nhưng chỉ có `System.out.println(5);` trong thân, không `return`. Có biên dịch được không? Vì sao?

**Câu 5.** Hai phương thức `int size()` và `long size()` trong cùng lớp có tạo overload hợp lệ không? Nếu cần hai hành vi khác nhau, có thể thay đổi điều gì?

**Câu 6.** `throws IOException` khác `throw new IOException("error")` ở đâu? Trường hợp ngoại lệ checked, bên gọi cần làm gì?

**Câu 7.** Trong `static <T> T identity(T item)`, thành phần `<T>` và hai chữ `T` còn lại có cùng vai trò không?

**Câu 8.** Phương thức có `@Override` vẫn phải tuân theo quy tắc nào? `static` và `final` có thể override như phương thức instance bình thường không?

**Đáp án đối chiếu:**

1. `private`, `static`, `long`, `multiply`, hai tham số `int a` và `int b`.
2. `public int sum(int a, int b) { return a + b; }`.
3. Varargs phải cuối: `void send(boolean urgent, String... messages)`.
4. Không; phương thức khai báo trả `int` nhưng có thể kết thúc bình thường mà không trả một `int`.
5. Không; chỉ khác return type. Hãy thay đổi danh sách kiểu/số lượng tham số hoặc đặt tên phương thức khác theo ý nghĩa.
6. `throws` là khai báo trong header; `throw` thực hiện ném ngoại lệ trong body. Bên gọi xử lý hoặc tiếp tục khai báo ngoại lệ checked phù hợp.
7. `<T>` **khai báo tham số kiểu**; `T` ở vị trí return type và parameter type **sử dụng** kiểu ấy.
8. Phương thức phải thực sự override/triển khai một khai báo hợp lệ; `final` ngăn override, còn `static` áp dụng hiding thay vì overriding.

## 18. Tài liệu đối chiếu

- [Java Language Specification 17, §8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): cấu trúc phương thức trong lớp, modifier, tham số, method signature, body và ngoại lệ.
- [Java Language Specification 17, §9.4 — Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4): khai báo phương thức trong interface.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): quy tắc lời gọi và lựa chọn phương thức.

**Ghi nhớ:** cấu trúc **modifier → tham số kiểu (nếu có) → kiểu trả về → tên → danh sách tham số → throws (nếu có) → thân hoặc dấu chấm phẩy** xác định hợp đồng của phương thức. Đọc từng phần của khai báo giúp hiểu cách gọi đúng, kiểu dữ liệu được truyền và nhận, cùng những ràng buộc mà Java kiểm tra khi biên dịch.
