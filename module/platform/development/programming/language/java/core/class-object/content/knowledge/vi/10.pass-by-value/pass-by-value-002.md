# Truyền giá trị nguyên thủy vào phương thức trong Java

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích quy tắc **Java luôn truyền đối số theo giá trị** (*pass-by-value*) và áp dụng quy tắc đó chính xác với tám kiểu nguyên thủy (*primitive types*).
- Phân biệt **biến của bên gọi** (*caller variable*), **biểu thức đối số** (*argument expression*) và **biến tham số** (*parameter variable*) trong một lần gọi phương thức.
- Dự đoán kết quả khi method gán lại hoặc tăng/giảm tham số thuộc kiểu `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`.
- Hiểu tại sao method không thể hoán đổi hai **biến nguyên thủy của caller** chỉ bằng việc hoán đổi hai tham số.
- Dùng **return value** hoặc một thiết kế API thích hợp để caller chủ động cập nhật biến, thay vì trông chờ method thay đổi biến nguyên thủy bên ngoài.
- Nhận biết các phép chuyển đổi được phép khi truyền primitive arguments, tác động của overloading và các lỗi thường gặp về widening, narrowing, boxing và unboxing.
- Phân biệt việc **đánh giá biểu thức đối số trước khi gọi** (có thể có side effects lên biến caller) với việc **gán lại tham số bên trong method**.
- Tự biên dịch/chạy các ví dụ Java 17+ và lý giải stdout.

## 1. Nguyên tắc chính: method nhận một bản sao giá trị

Xét một method:

~~~java
static void change(int number) {
    number = 100;
}
~~~

Đây là **khai báo phương thức minh họa** cần được đặt trong một lớp Java. Bên gọi thực hiện:

~~~java
int original = 10;
change(original);
System.out.println(original);
~~~

Kết quả là **`10`**, không phải `100`.

Khi chương trình đến lời gọi `change(original)`:

1. Java đánh giá biểu thức đối số `original` và nhận **giá trị kiểu `int` bằng 10**.
2. Java khởi tạo một **biến tham số riêng** mang tên `number` cho lần gọi này, chứa **bản sao giá trị 10**.
3. Thân method chạy. Câu lệnh `number = 100;` chỉ thay giá trị của **biến tham số `number`**, không gán lại biến `original` của caller.
4. Method kết thúc. Bên gọi tiếp tục với `original` vẫn bằng 10.

Có thể hình dung như sau:

~~~text
Caller:                      Callee: change(...)
int original = 10    --->    int number = 10  (bản sao giá trị)
                               number = 100
                               return
Caller đọc original: 10      Biến number của lần gọi đã kết thúc
~~~

**Ghi nhớ một câu:** *Truyền một biến nguyên thủy cho method là truyền **giá trị hiện tại của biến**, không trao quyền sửa trực tiếp chính biến bên gọi.*

Đây không phải quy tắc tùy ý của một compiler; là ngữ nghĩa ngôn ngữ Java. Tham số của method có đời sống riêng trong lời gọi. Nhiều lần gọi cùng một method cũng có các tham số của từng lần thực thi, không chia sẻ một biến tham số toàn cục.

### 1.1. Định nghĩa ba thuật ngữ

| Thuật ngữ | Ví dụ | Nghĩa |
| --- | --- | --- |
| **Biến bên gọi** | `int original = 10;` | Nơi caller lưu giá trị hiện hành |
| **Đối số thực tế** | `original` trong `change(original)` | Biểu thức được đánh giá để lấy một giá trị |
| **Tham số hình thức** | `int number` trong `change(int number)` | Biến được khởi tạo từ giá trị đối số khi gọi method |

Tên biến bên gọi và tên tham số không cần giống nhau. Ngay cả khi chúng **cùng tên**, chúng vẫn là các biến khác nhau trong hai phạm vi riêng.

### 1.2. Java có bao nhiêu kiểu nguyên thủy?

Tám kiểu nguyên thủy của Java là:

| Kiểu | Dữ liệu chủ yếu | Ví dụ giá trị |
| --- | --- | --- |
| `byte` | Số nguyên có dấu 8 bit | `(byte) 7` |
| `short` | Số nguyên có dấu 16 bit | `(short) 300` |
| `int` | Số nguyên có dấu 32 bit | `42` |
| `long` | Số nguyên có dấu 64 bit | `42L` |
| `float` | Số thực dấu chấm động 32 bit | `1.5f` |
| `double` | Số thực dấu chấm động 64 bit | `1.5d` |
| `char` | Đơn vị mã UTF-16 không dấu 16 bit | `'A'` |
| `boolean` | Giá trị logic | `true`, `false` |

Cả tám loại đều **truyền theo giá trị**. Với primitive argument, giá trị được truyền không phải là một object hay object reference. `int` không “trỏ vào” vùng nhớ của biến `int` ở caller theo quy tắc Java.

## 2. Chương trình độc lập: gán lại tham số không thay đổi caller

Lưu vào tệp **`PrimitivePassByValueDemo.java`**:

~~~java
public class PrimitivePassByValueDemo {
    static void changeInt(int number) {
        System.out.println("inside before=" + number);
        number = 100;
        System.out.println("inside after=" + number);
    }

    static void changeBoolean(boolean enabled) {
        enabled = !enabled;
        System.out.println("inside enabled=" + enabled);
    }

    static void changeChar(char letter) {
        letter = 'Z';
        System.out.println("inside letter=" + letter);
    }

    public static void main(String[] args) {
        int number = 10;
        boolean enabled = true;
        char letter = 'A';

        changeInt(number);
        System.out.println("outside number=" + number);

        changeBoolean(enabled);
        System.out.println("outside enabled=" + enabled);

        changeChar(letter);
        System.out.println("outside letter=" + letter);
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac PrimitivePassByValueDemo.java
java PrimitivePassByValueDemo
~~~

**Stdout chính xác:**

~~~text
inside before=10
inside after=100
outside number=10
inside enabled=false
outside enabled=true
inside letter=Z
outside letter=A
~~~

Phân tích:

- `changeInt(number)` nhận bản sao `10`, gán thành `100` bên trong method. Caller vẫn có `number == 10`.
- `changeBoolean(enabled)` nhận bản sao `true` và đảo thành `false`. Điều này **không** thay đổi biến `enabled` của `main`.
- `changeChar(letter)` nhận bản sao ký tự `'A'`, gán thành `'Z'`; caller vẫn giữ `'A'`.

Không có ngoại lệ chỉ vì `boolean` hay `char` khác nhóm số nguyên. Chúng cũng là primitive values, nên tham số được khởi tạo từ giá trị đối số và mọi phép gán tham số đều chỉ ảnh hưởng biến tham số.

## 3. Phân biệt sửa tham số với cập nhật biến caller qua kết quả trả về

Nếu muốn caller thay đổi biến `number` thành giá trị mới, cách rõ ràng là **trả kết quả từ method**, sau đó **caller chủ động gán lại**:

~~~java
static int doubled(int value) {
    return value * 2;
}

// Trong main hoặc một method khác:
int number = 7;
number = doubled(number);
~~~

Sau lệnh `number = doubled(number);`, caller có `number == 14`. Method `doubled` không bí mật thay đổi biến bên ngoài. Nó chỉ tính kết quả từ bản sao tham số rồi **trả một giá trị `int`**. Chính phép gán `number = ...` của caller làm biến caller đổi.

### 3.1. Ví dụ chạy hoàn chỉnh

Lưu **`ReturnPrimitiveDemo.java`**:

~~~java
public class ReturnPrimitiveDemo {
    static int addFive(int value) {
        value += 5;
        return value;
    }

    static boolean toggle(boolean value) {
        return !value;
    }

    static char nextChar(char value) {
        return (char) (value + 1);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean active = true;
        char letter = 'A';

        addFive(score);
        System.out.println("ignored return=" + score);

        score = addFive(score);
        System.out.println("assigned return=" + score);

        active = toggle(active);
        System.out.println("active=" + active);

        letter = nextChar(letter);
        System.out.println("letter=" + letter);
    }
}
~~~

Lệnh:

~~~bash
javac ReturnPrimitiveDemo.java
java ReturnPrimitiveDemo
~~~

Output:

~~~text
ignored return=10
assigned return=15
active=false
letter=B
~~~

Điểm mấu chốt nằm ở hai lời gọi `addFive(score)`:

- Lời gọi đầu tính ra `15` nhưng **bỏ qua giá trị trả về**; `score` của caller giữ nguyên `10`.
- Lời gọi thứ hai có phép gán `score = ...`, nên caller nhận và lưu `15`.

Chọn kiểu trả về đúng cho nghiệp vụ. Một method `void` có thể thực hiện tính toán và log nhưng **không thể trực tiếp cung cấp một primitive result** qua `return value;`. Nếu muốn caller nhận kết quả, thường nên thiết kế method có return type phù hợp.

### 3.2. Kết quả method là giá trị, không phải tên biến

Với `return value;` trong một method trả `int`, Java trả **giá trị của biểu thức `value`**, không trả quyền sửa local/parameter variable mang tên `value`. Caller nhận một giá trị tương thích với kiểu trả về.

Nếu caller viết `int result = addFive(10);` thì `result` là biến mới. Không có mối liên kết để một phép gán sau này vào biến tham số cũ làm `result` thay đổi.

## 4. Vì sao hoán đổi hai primitive parameters không hoán đổi biến caller?

Một lỗi kinh điển:

~~~java
static void swap(int a, int b) {
    int temporary = a;
    a = b;
    b = temporary;
}
~~~

Method này **hoán đổi giá trị của hai tham số cục bộ** (`a`, `b`) trong lần gọi, nhưng không hoán đổi biến nguyên thủy của caller.

Lưu **`PrimitiveSwapDemo.java`**:

~~~java
public class PrimitiveSwapDemo {
    static void swap(int a, int b) {
        int temporary = a;
        a = b;
        b = temporary;
        System.out.println("inside swap=" + a + "," + b);
    }

    static int[] swappedValues(int a, int b) {
        return new int[] {b, a};
    }

    public static void main(String[] args) {
        int first = 3;
        int second = 8;

        swap(first, second);
        System.out.println("outside swap=" + first + "," + second);

        int[] values = swappedValues(first, second);
        first = values[0];
        second = values[1];

        System.out.println("after assignment=" + first + "," + second);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrimitiveSwapDemo.java
java PrimitiveSwapDemo
~~~

Output:

~~~text
inside swap=8,3
outside swap=3,8
after assignment=8,3
~~~

**Vì sao `swappedValues` hoạt động?** Method nhận hai primitive values và trả về một **mảng mới chứa hai giá trị đã đảo**. Caller đọc các phần tử mảng rồi tự gán vào `first`, `second`. Đây là một API **trả kết quả**, không phải method sửa trực tiếp hai biến primitive của caller.

Ở ví dụ này, mảng chỉ là một cách chuyển **hai kết quả** về caller; nó là object và có semantics tham chiếu riêng. Trong thiết kế thực tế, một record/value type có tên rõ ràng có thể thích hợp hơn một mảng khó biết ý nghĩa vị trí.

### 4.1. Có thể hoán đổi bằng lời gọi method nhưng làm biến caller đổi được không?

Với **chỉ hai tham số nguyên thủy truyền theo giá trị**, method không có đường tham chiếu ngược tới **chính các biến local của caller**. Tuy vậy, một method có thể sửa **field**, **phần tử mảng** hoặc một object mutable được truyền vào qua reference; đó là **một cơ chế khác** và không biến Java thành pass-by-reference cho local variables.

Đừng nhầm hai mục tiêu:

- **Thay đổi giá trị của một biến local `int x` ở caller**: cần caller gán lại hoặc điều khiển flow phù hợp.
- **Thay đổi trạng thái của một object mà caller cũng đang giữ reference**: có thể qua object method/field/array; đó không phải hoán đổi trực tiếp các biến local primitive.

## 5. Mỗi lần gọi có tham số của riêng lần gọi

Dù cùng gọi một method nhiều lần, tên parameter bên trong không phải là một “biến duy nhất được chia sẻ”.

~~~java
static void printAfterIncrement(int n) {
    n++;
    System.out.println(n);
}
~~~

Trong cùng method caller:

~~~java
int x = 4;
printAfterIncrement(x);
printAfterIncrement(x);
System.out.println(x);
~~~

Nếu chạy, output:

~~~text
5
5
4
~~~

Ở **mỗi lời gọi**, parameter `n` bắt đầu bằng bản sao giá trị hiện tại của `x` là `4`. Sau khi `n++` in `5`, lần gọi ấy kết thúc. Lần gọi tiếp theo lại nhận `4`, không “nhớ” giá trị `n` của lần trước. Biến `x` vẫn giữ `4`.

### 5.1. Recursion cũng không chia sẻ một tham số duy nhất

Lưu **`RecursivePrimitiveDemo.java`**:

~~~java
public class RecursivePrimitiveDemo {
    static void descend(int n) {
        System.out.println("enter=" + n);
        if (n > 0) {
            descend(n - 1);
        }
        System.out.println("exit=" + n);
    }

    public static void main(String[] args) {
        int start = 2;
        descend(start);
        System.out.println("main=" + start);
    }
}
~~~

Chạy:

~~~bash
javac RecursivePrimitiveDemo.java
java RecursivePrimitiveDemo
~~~

Output:

~~~text
enter=2
enter=1
enter=0
exit=0
exit=1
exit=2
main=2
~~~

Mỗi lần gọi đệ quy có giá trị tham số `n` của riêng nó: 2, 1, rồi 0. Khi các lời gọi trả về, mỗi frame tiếp tục in giá trị `n` **của chính lần gọi ấy**. Vì thế output đi xuống 2 → 1 → 0, rồi quay lên 0 → 1 → 2.

Ví dụ cũng cho thấy truyền `start` vào method không tự thay đổi `start` trong `main`.

## 6. Chuyển đổi kiểu khi truyền primitive values

Nói “truyền bản sao giá trị” không có nghĩa **kiểu đối số luôn trùng chính xác kiểu tham số**. Trước khi body chạy, compiler kiểm tra **method invocation conversion** và Java có thể thực hiện chuyển đổi hợp lệ.

Ví dụ:

~~~java
static void printLong(long value) {
    System.out.println(value);
}

// Trong một method:
int number = 12;
printLong(number); // Hợp lệ: int -> long
~~~

Ở đây caller cung cấp biểu thức kiểu `int` có giá trị 12. Method yêu cầu `long`; Java cho phép **primitive widening** (`int` → `long`). Parameter `value` nhận một **giá trị `long` tương ứng**, độc lập với biến `number` của caller.

Nếu body viết `value = 1000L;` thì caller vẫn có `number == 12`.

### 6.1. Các primitive widening conversions thường gặp

| Kiểu nguồn | Các kiểu đích widening hợp lệ |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có primitive type rộng hơn |
| `boolean` | Không widening sang kiểu số hoặc từ kiểu số |

Một số widening chuyển số nguyên lớn sang float/double có thể **mất độ chính xác biểu diễn** do làm tròn. “Widening” mô tả một nhóm phép chuyển kiểu được phép, không phải bảo đảm giữ nguyên mọi bit hay mọi giá trị toán học.

**Không có** primitive widening từ `int` → `byte`, `int` → `short`, `double` → `float` hoặc `char` → `short`.

### 6.2. Không tự động narrowing một literal `int` chỉ vì nó vừa trong miền `byte`

Xem:

~~~java
static void acceptByte(byte n) {
    System.out.println(n);
}

// Trong caller:
// acceptByte(10);        // Lỗi: int không tự thu hẹp xuống byte
byte value = 10;
acceptByte(value);       // Hợp lệ: đã là byte
acceptByte((byte) 10);   // Hợp lệ: cast tường minh
~~~

Đây là đoạn minh họa khi được đặt trong class/method thích hợp. Điểm dễ gây nhầm là **phép gán biến** `byte value = 10;` có quy tắc đặc biệt cho hằng số nguyên nằm trong miền kiểu nhỏ, còn **lời gọi method** không tự áp dụng thu hẹp `int` → `byte` chỉ để tìm tham số phù hợp.

Cast `(byte) 10` có chủ đích, nhưng không nên cast tùy tiện. Ví dụ `(byte) 130` cho một giá trị khác 130 do giới hạn 8 bit. Để tránh bug nghiệp vụ, chọn kiểu tham số thể hiện đúng miền giá trị cần nhận.

### 6.3. Kiểu `char` cũng là primitive

~~~java
static void printCode(int code) {
    System.out.println(code);
}

// Trong caller:
char c = 'A';
printCode(c); // Hợp lệ: char -> int, in 65
~~~

`char` biểu diễn một **đơn vị mã UTF-16**, không phải lúc nào cũng biểu diễn được một ký tự Unicode hoàn chỉnh. Phép widening `char` → `int` cho giá trị số nguyên tương ứng của đơn vị mã đó. Đây không phải truyền tham chiếu hay tạo String mới.

### 6.4. Boolean không trở thành số

Nếu method nhận `int`, lời gọi `f(true)` không hợp lệ trừ khi có overload `f(boolean)` phù hợp. Java **không** chuyển `true` thành `1` hoặc `false` thành `0` theo ngầm định.

## 7. Chương trình về primitive widening và overloading

Lưu **`PrimitiveConversionsDemo.java`**:

~~~java
public class PrimitiveConversionsDemo {
    static void showLong(long number) {
        System.out.println("long=" + number);
        number = 999L;
    }

    static void showDouble(double number) {
        System.out.println("double=" + number);
    }

    static void showByte(byte number) {
        System.out.println("byte=" + number);
    }

    static String choose(long number) {
        return "chosen long";
    }

    static String choose(Integer number) {
        return "chosen Integer";
    }

    static void showCodePointUnit(int code) {
        System.out.println("code=" + code);
    }

    public static void main(String[] args) {
        int value = 12;
        showLong(value);
        System.out.println("caller=" + value);

        float decimal = 1.5f;
        showDouble(decimal);

        byte small = 10;
        showByte(small);
        showByte((byte) 20);

        char letter = 'A';
        showCodePointUnit(letter);

        System.out.println(choose(7));
        System.out.println(choose(Integer.valueOf(7)));
    }
}
~~~

Chạy:

~~~bash
javac PrimitiveConversionsDemo.java
java PrimitiveConversionsDemo
~~~

Output:

~~~text
long=12
caller=12
double=1.5
byte=10
byte=20
code=65
chosen long
chosen Integer
~~~

Giải thích:

- `showLong(value)` dùng widening `int` → `long`. Sau khi method tự gán `number = 999L`, caller vẫn giữ `value == 12`.
- `showDouble(decimal)` dùng widening `float` → `double`. `1.5f` có biểu diễn nhị phân chính xác nên khi in ở đây là `1.5`.
- `showByte(small)` truyền trực tiếp biến kiểu `byte`; `showByte((byte) 20)` dùng cast tường minh.
- `showCodePointUnit(letter)` nhận `int` tương ứng đơn vị mã UTF-16 của `'A'`, là 65.
- Với `choose(7)`, đối số `7` có kiểu `int`: overload `choose(long)` áp dụng nhờ primitive widening **ở pha strict**, trước khi cần boxing thành `Integer`.
- Với `choose(Integer.valueOf(7))`, kiểu tĩnh của đối số đã là `Integer` nên overload cùng kiểu `choose(Integer)` áp dụng trực tiếp.

Hai overload chỉ nhằm minh họa **quy tắc chọn phương thức phù hợp**, không làm thay đổi nguyên tắc **pass-by-value**. Sau khi chọn overload, mỗi method vẫn nhận parameter variable riêng.

### 7.1. Thứ tự xét primitive widening và boxing trong overload

Ở mức khái quát, Java xét overload theo các pha:

1. **Strict invocation**: xét fixed arity với các phép chuyển đổi không cần boxing/unboxing, như identity, primitive widening và reference widening.
2. **Loose invocation**: nếu pha trước không có method áp dụng, xét thêm boxing/unboxing và các tổ hợp được cho phép.
3. **Variable arity**: nếu vẫn không có method áp dụng, xét cách gọi varargs với số lượng đối số biến đổi.

Do đó primitive widening có thể được chọn **trước** boxing nếu một overload phù hợp xuất hiện ở pha đầu. Tuy vậy trong một pha có nhiều ứng viên, compiler phải áp dụng quy tắc **most-specific**; không nên tổng quát hóa “primitive luôn thắng wrapper”.

Ví dụ, `Integer n = 7;` khi truyền cho method chỉ nhận `long` có thể được **unbox `Integer` → `int` rồi widening → `long`**. Việc unboxing xảy ra trước khi parameter nhận giá trị và có thể ném `NullPointerException` nếu wrapper là `null`.

### 7.2. Pass-by-value vẫn đúng khi có unboxing/boxing

Trong lời gọi `accept(Integer.valueOf(7))` với tham số `int`, Java có thể unboxing object wrapper để lấy **giá trị primitive 7** truyền vào parameter. Method sửa parameter `int` cũng không sửa `Integer` object hay biến wrapper của caller.

Ngược lại, nếu method nhận `Integer` và bạn truyền một biến `int`, Java có thể boxing trước khi truyền **giá trị tham chiếu** đến wrapper object. Wrapper `Integer` là immutable; nhưng đó là **truyền tham số kiểu tham chiếu theo giá trị**, không phải truyền local primitive variable theo tham chiếu.

## 8. Thứ tự đánh giá biểu thức đối số khác với sửa tham số

Một điểm tinh tế: trước khi vào thân method, Java **đánh giá biểu thức đối số**. Nếu biểu thức đối số tự thay đổi biến caller, caller có thể đổi **trước khi method bắt đầu**, nhưng điều đó không phải vì method đã sửa biến tham số.

Ví dụ:

~~~java
static void printValues(int first, int second) {
    System.out.println(first + "," + second);
}

// Trong caller:
int x = 3;
printValues(x++, x);
System.out.println(x);
~~~

Kết quả khi chạy:

~~~text
3,4
4
~~~

Giải thích:

1. Java đánh giá đối số đầu `x++`: biểu thức cung cấp **giá trị cũ 3**, đồng thời tăng **biến `x` bên caller** lên 4.
2. Java đánh giá đối số thứ hai `x`: nhận giá trị 4.
3. Hai tham số `first` và `second` của method nhận **các bản sao giá trị 3 và 4**.
4. Thân method in `3,4`. Sau khi method hoàn tất, caller in `4`, vì chính biểu thức `x++` đã tăng x trước đó.

**Phân biệt thật rõ:**

- `method(x)` và method gán lại parameter: caller **không đổi** do phép gán trong method.
- `method(x++)`: caller **có thể đổi**, do side effect của **biểu thức đối số** được đánh giá ở caller trước khi method chạy.
- `x = method(x)`: caller **có thể đổi**, do **phép gán của caller sau khi method trả về**.

### 8.1. Chương trình đầy đủ về thứ tự đối số

Lưu **`PrimitiveArgumentOrderDemo.java`**:

~~~java
public class PrimitiveArgumentOrderDemo {
    static void show(int first, int second, int third) {
        first = 100;
        System.out.println("method values=" +
                first + "," + second + "," + third);
    }

    public static void main(String[] args) {
        int x = 2;
        show(x++, ++x, x);
        System.out.println("caller x=" + x);
    }
}
~~~

Lệnh:

~~~bash
javac PrimitiveArgumentOrderDemo.java
java PrimitiveArgumentOrderDemo
~~~

Output:

~~~text
method values=100,4,4
caller x=4
~~~

Diễn biến:

- `x++` truyền giá trị 2, rồi đổi x thành 3.
- `++x` đổi x thành 4 trước khi trả giá trị đối số thứ hai là 4.
- Đối số thứ ba đọc x hiện tại là 4.
- `show` nhận `(2,4,4)`, nhưng câu lệnh trong thân `first = 100;` đổi **tham số bản sao** rồi in `100,4,4`.
- Bên gọi vẫn giữ x bằng 4.

Java quy định thứ tự đánh giá trái sang phải của các đối số. Tuy nhiên, code có nhiều `++` trong một lời gọi **khó đọc**; trong chương trình thật nên cân nhắc tách thành biến trung gian.

### 8.2. Nếu biểu thức đối số ném ngoại lệ?

Nếu biểu thức đối số ném exception, lời gọi method có thể không được thực thi. Các biểu thức đối số đã hoàn tất trước đó có thể đã có side effects; chúng không tự rollback. Đây là đặc điểm của evaluation order, độc lập với cách method truyền tham số theo giá trị.

## 9. `final` với parameter primitive

Có thể khai báo parameter nguyên thủy với modifier `final`:

~~~java
static int addOne(final int value) {
    // value++; // Không hợp lệ: không thể gán lại final parameter
    return value + 1;
}
~~~

Khi parameter là `final`, compiler ngăn phép **gán lại biến parameter**; method vẫn được phép **đọc** và sử dụng giá trị ấy để tính toán.

Nếu không khai báo `final`, Java cho phép `value++` trong thân method, nhưng phép thay đổi ấy chỉ áp dụng cho **parameter variable** và vẫn không sửa biến caller.

**Không nên nhầm:**

- `final int x`: ngăn gán lại giá trị số trong biến x sau khi đã được gán hợp lệ.
- `final SomeObject obj`: ngăn gán lại reference variable obj, **không** tự làm object được tham chiếu bất biến.

Parameter primitive không có object bên trong để “mutate”, nên `final` ở đây tập trung hoàn toàn vào phép gán lại parameter.

### 9.1. Effectively final và lambda

Một parameter primitive không khai báo `final` nhưng **không bao giờ bị gán lại** có thể là **effectively final**. Điều này quan trọng khi lambda hoặc local/anonymous class capture parameter.

Ví dụ:

~~~java
static Runnable makeTask(int number) {
    return () -> System.out.println(number);
}
~~~

Đây là phương thức minh họa hợp lệ trong class có import/cú pháp tương ứng. `number` được lambda capture vì effectively final. Nếu bạn gán lại `number` trong method rồi vẫn capture nó, compiler sẽ báo lỗi theo quy tắc biến được capture phải final hoặc effectively final.

Điều này không thay đổi pass-by-value: `number` được khởi tạo từ **giá trị primitive của caller**, và việc sử dụng nó trong lambda không trao quyền sửa local variable của caller.

## 10. Tác động tới fields và biến local của caller

Giả sử một class có field `total`:

~~~java
class Meter {
    int total = 10;

    void change(int value) {
        value = 99;  // Chỉ thay đổi parameter.
    }
}
~~~

Gọi `meter.change(meter.total)` **không** đổi field `meter.total`; method chỉ nhận giá trị hiện hành của field.

Muốn cập nhật field, method cần có câu lệnh **ghi field** hoặc trả kết quả để caller gán:

~~~java
class Meter {
    int total = 10;

    void increaseBy(int amount) {
        total += amount;      // Ghi instance field thực sự
    }

    int doubled(int value) {
        return value * 2;
    }
}
~~~

Trong `increaseBy(5)`, field `total` thay đổi vì thân method **truy cập và gán field** của object nhận lời gọi; **không phải** vì tham số `amount` giữ tham chiếu tới field ở caller.

### 10.1. Chương trình minh họa gán field trực tiếp

Lưu **`PrimitiveFieldDemo.java`**:

~~~java
public class PrimitiveFieldDemo {
    private int score = 10;

    void changeCopy(int score) {
        score = 99;
        System.out.println("parameter=" + score);
    }

    void changeField(int amount) {
        this.score += amount;
    }

    public static void main(String[] args) {
        PrimitiveFieldDemo exam = new PrimitiveFieldDemo();

        exam.changeCopy(exam.score);
        System.out.println("field after copy=" + exam.score);

        exam.changeField(5);
        System.out.println("field after update=" + exam.score);
    }
}
~~~

Chạy:

~~~bash
javac PrimitiveFieldDemo.java
java PrimitiveFieldDemo
~~~

Output:

~~~text
parameter=99
field after copy=10
field after update=15
~~~

`changeCopy(int score)` khai báo tham số trùng tên field; `score = 99` là phép gán vào **parameter**, không phải vào field. Nếu muốn ghi field, phải dùng `this.score` hoặc một truy cập field rõ ràng khác. `changeField` sử dụng `this.score += amount`, nên thay đổi trường dữ liệu thật của object.

Đây là điểm liên kết giữa **pass-by-value** và **shadowing**: hai biến trùng tên không trở thành một biến, và Java không tự gắn parameter với field.

## 11. Giá trị primitive đặc biệt: overflow, dấu chấm động và boolean

Pass-by-value bảo đảm **tính độc lập của biến parameter**, không bảo đảm phép toán trên giá trị luôn trực quan về toán học.

### 11.1. Số nguyên overflow

Java dùng số nguyên có dấu hữu hạn cho `byte`, `short`, `int`, `long`. Một phép tính có thể tràn miền (overflow) mà không tự động báo lỗi cho các toán tử thông thường như `+`.

~~~java
static int plusOne(int value) {
    return value + 1;
}
~~~

Nếu gọi `plusOne(Integer.MAX_VALUE)`, kết quả kiểu `int` là **`Integer.MIN_VALUE`** do quy tắc tràn số nguyên. Caller vẫn không bị sửa bởi thân method, nhưng **giá trị trả về** có thể không phù hợp nghiệp vụ.

Nếu yêu cầu báo lỗi thay vì tràn, có thể dùng `Math.addExact(value, 1)` với kiểu phù hợp để nhận `ArithmeticException` khi overflow.

### 11.2. `float` và `double` có NaN và vô cực

Kiểu dấu chấm động theo IEEE 754 có các giá trị như `NaN`, `POSITIVE_INFINITY` và `NEGATIVE_INFINITY`. Method truyền/nhận chúng theo giá trị, nhưng phép so sánh có thể gây bất ngờ:

~~~java
static boolean same(double left, double right) {
    return left == right;
}
~~~

Với `Double.NaN`, biểu thức `Double.NaN == Double.NaN` là `false`. Đây là quy tắc so sánh floating-point, **không** phải việc phương thức truyền sai hoặc làm mất tham số.

`float` → `double` là widening hợp lệ nhưng có thể thấy kết quả in thập phân khác kiểu literal bạn tưởng, vì một số phân số thập phân không biểu diễn chính xác ở dạng nhị phân. Ví dụ giá trị `0.1f` khi mở rộng sang double vẫn chứa độ chính xác của **giá trị float ban đầu**, không biến thành `0.1` toán học chính xác.

### 11.3. Đối với `boolean`

Một method có thể dùng `boolean` để tính ra boolean mới và trả về. Nhưng method không thể làm biến boolean của caller đổi bằng cách viết `flag = !flag;` trên tham số. Nếu muốn caller nhận giá trị đảo, trả boolean và caller tự gán `flag = toggle(flag);`.

## 12. Boxing/unboxing: điểm giao giữa primitive và reference

Mặc dù bài này tập trung vào primitive values, trong Java code thường gặp kiểu wrapper `Integer`, `Long`, `Boolean`, `Character`, v.v.

- **Boxing** biến primitive value thành một wrapper reference thích hợp theo quy tắc ngôn ngữ.
- **Unboxing** trích giá trị primitive từ wrapper reference.
- Wrapper classes tiêu chuẩn như `Integer` là **immutable**.

Ví dụ:

~~~java
static void consumeInt(int value) {
    value++;
}

// Trong caller:
Integer boxed = Integer.valueOf(5);
consumeInt(boxed); // Unboxing thành int 5 trước khi truyền
~~~

`consumeInt` nhận một **tham số `int` có giá trị 5**. Phép `value++` trong method không đổi biến `boxed` và cũng không “đổi nội dung Integer object”.

Nếu `boxed` bằng `null`, việc unboxing trước khi gọi method ném `NullPointerException`; method không được thực thi bình thường. Điều này khác trường hợp một primitive variable vốn không thể chứa `null`.

Một trường hợp dễ sai là nghĩ Java sẽ tự chuyển `int` → `long` → `Long` trong lời gọi nhận `Long`. Chuỗi **primitive widening rồi boxing** như vậy **không** phải method invocation conversion được phép tự động nói chung. Cần dùng literal `5L`, một biểu thức kiểu `long`, hoặc chuyển đổi tường minh có chủ đích.

## 13. Những lỗi phổ biến

| Nhầm lẫn hoặc lỗi | Giải thích/cách xử lý |
| --- | --- |
| “Truyền `int` vào method là truyền địa chỉ của biến int.” | Java truyền **giá trị số**; tham số là biến khác. |
| “Gán lại tham số trong method làm biến local của caller đổi.” | Sai; method chỉ gán lại parameter. Trả kết quả rồi caller tự gán nếu muốn đổi. |
| “`swap(int a,int b)` sẽ hoán đổi hai biến bên ngoài.” | Sai; chỉ hoán đổi hai tham số bản sao. |
| “Nếu caller thấy biến đổi sau `f(x++)` thì method đã sửa x.” | Sai về nguyên nhân: **đối số `x++`** đã sửa x trước khi method chạy. |
| “Nếu method trả `int` mà không gán kết quả, caller tự cập nhật.” | Sai; phải gán kết quả hoặc dùng nó tại nơi gọi. |
| “Các lần gọi cùng method dùng chung một parameter variable.” | Sai; mỗi lần thực thi có parameter binding riêng. |
| “`final int x` khiến method không đọc được x.” | Sai; `final` chỉ ngăn gán lại parameter. |
| “`int` sang `long` khi gọi là pass-by-reference.” | Sai; đó là chuyển đổi kiểu của giá trị rồi truyền theo giá trị. |
| “Literal `10` tự truyền được vào `byte` nếu nằm trong miền byte.” | Method invocation không tự narrowing `int` → `byte`; dùng kiểu/cast phù hợp. |
| “`Integer` đưa vào method `int` sẽ làm object biến đổi khi tham số tăng.” | Sai; unboxing tạo giá trị primitive, wrapper không bị mutate. |
| “`Integer null` unboxing thành 0.” | Sai; unboxing null ném `NullPointerException`. |
| “`float` sang `double` luôn sửa được mọi sai số thập phân.” | Sai; giá trị float ban đầu đã có giới hạn độ chính xác. |
| “Sửa instance field thông qua method là bằng chứng Java truyền primitive theo tham chiếu.” | Sai; field thay đổi vì method có câu lệnh gán field, không vì tham số alias với field. |
| “Method không thể có side effect nếu chỉ nhận primitive arguments.” | Sai; method có thể sửa field, static state, I/O, gọi method khác. Chỉ **tham số primitive** không đại diện cho biến caller. |
| “`boolean` hoặc `char` có cách truyền riêng.” | Không; cả tám primitive types đều theo cơ chế pass-by-value. |

## 14. Cách phân tích nhanh bất kỳ lời gọi primitive nào

Khi thấy `result = compute(x, y);`, hãy lần lượt tự hỏi:

1. **Kiểu tĩnh của `x` và `y` là gì?** Có phải primitive không? Ví dụ `int`, `double`.
2. **Biểu thức đối số là gì?** `x` chỉ đọc, nhưng `x++` hay `x = 7` có thể thay đổi biến của caller ngay khi đánh giá.
3. **Compiler chọn phương thức nào?** Kiểm tra kiểu/thứ tự/số lượng tham số và các chuyển đổi hợp lệ.
4. **Giá trị thực tế được chuyển vào từng parameter là gì?** Nếu có widening/unboxing, xem chuyển đổi trước lúc body chạy.
5. **Method có làm gì với parameter?** `parameter++` chỉ đổi biến tham số; không đổi local/field bên caller vì tham số mang cùng **giá trị cũ**.
6. **Method có sửa trạng thái khác không?** Nếu thân method dùng `this.field++` hoặc static field, đó là side effect độc lập với cơ chế truyền primitive.
7. **Có return value không?** Nếu có, caller có dùng `x = method(x)` để cập nhật x không?
8. **Có overflow, NaN, null-unboxing hay exception không?** Chúng có thể ảnh hưởng kết quả hoặc làm lời gọi thất bại, nhưng không đổi pass-by-value thành pass-by-reference.

Nếu bạn vẽ sơ đồ, hãy vẽ một **ô riêng cho tham số**; không nối mũi tên “tham số `int` trỏ tới biến `int` của caller”. Cả hai ô có thể chứa cùng số 5 lúc bắt đầu nhưng **không phải cùng một biến**.

## 15. Phân biệt nhanh với truyền một đối tượng

Java chỉ có **pass-by-value** ngay cả khi kiểu tham số là reference type. Nhưng lúc đó “giá trị được sao chép” là **reference value**, có thể trỏ cùng một object với caller; method có thể sửa object mutable qua reference đó.

Ví dụ minh họa:

~~~java
static void changeInt(int value) {
    value = 99;
}

static void changeArray(int[] values) {
    values[0] = 99;
}
~~~

Caller:

~~~java
int n = 1;
int[] data = {1};

changeInt(n);
changeArray(data);

System.out.println(n);       // 1
System.out.println(data[0]); // 99
~~~

Dòng cuối khác nhau **không** vì Java có hai chế độ truyền tham số. Với `changeInt`, parameter chứa bản sao **số nguyên 1**; gán lại nó không sửa n. Với `changeArray`, parameter chứa bản sao **tham chiếu tới mảng**, nên `values[0] = 99` thay đổi **chính array object** mà caller cũng đang tham chiếu.

Nếu method `changeArray` viết `values = new int[]{99};`, phép gán lại parameter reference này cũng **không** đổi biến `data` của caller.

Bài hiện tại nhấn mạnh trường hợp primitive; ví dụ mảng ở đây chỉ để tránh ngộ nhận rằng Java có pass-by-reference riêng cho đối tượng.

## 16. Bài tập có đáp án

### Bài 1. Gán lại tham số

~~~java
static void f(int n) {
    n = 40;
}
~~~

Nếu caller viết `int a = 4; f(a);`, sau lời gọi `a` bằng bao nhiêu?  
**Đáp án:** 4. Method chỉ gán lại parameter `n`.

### Bài 2. Tăng tham số

~~~java
static void increase(int n) {
    n++;
}
~~~

Caller dùng `int count = 9; increase(count);`. `count` là bao nhiêu?  
**Đáp án:** 9. Phép `n++` chỉ thay parameter của lần gọi.

### Bài 3. Trả kết quả

~~~java
static int increase(int n) {
    return n + 1;
}
~~~

Caller viết `int count = 9; count = increase(count);`. Kết quả?  
**Đáp án:** 10. Chính câu lệnh gán của caller nhận giá trị trả về.

### Bài 4. Swap

Method `swap(int a, int b)` hoán đổi hai parameter. Caller có `int x = 1, y = 2; swap(x, y);`. x/y sau đó?  
**Đáp án:** `x == 1`, `y == 2`. Hai biến caller không bị gán lại.

### Bài 5. Đối số có side effect

Caller: `int x = 1; f(x++);`, với `f(int value)` chỉ in value. Giá trị in và giá trị x sau lời gọi?  
**Đáp án:** Method in 1, caller có x = 2. Side effect của `x++` xảy ra **trước** thân method.

### Bài 6. Boolean

~~~java
static void deactivate(boolean active) {
    active = false;
}
~~~

Caller: `boolean active = true; deactivate(active);`. Caller có active bằng gì?  
**Đáp án:** `true`. Parameter được khởi tạo từ bản sao `true`.

### Bài 7. Char

~~~java
static void change(char ch) {
    ch = 'Z';
}
~~~

Caller `char letter = 'A'; change(letter);`. Caller có letter bằng gì?  
**Đáp án:** `'A'`.

### Bài 8. Widening

Method chỉ có tham số `long`. Caller có biến `int value = 5;`; gọi `f(value)` có hợp lệ không và có sửa value không?  
**Đáp án:** Hợp lệ nhờ widening `int` → `long`. Method nhận giá trị `long` tương ứng; sửa parameter không sửa biến `value`.

### Bài 9. Narrowing literal

Method chỉ có `f(byte n)`. `f(5)` tự hợp lệ vì 5 nằm trong miền byte không?  
**Đáp án:** Không. Literal `5` mặc định là `int`; method invocation không tự narrowing xuống `byte` chỉ nhờ giá trị nhỏ.

### Bài 10. Hai lần gọi

Caller `int x = 3; f(x); f(x);`; body `f(int n)` chỉ `n++` và in n. Hai lần in là gì, x sau đó bằng gì?  
**Đáp án:** In 4 rồi 4; x vẫn 3. Mỗi lời gọi nhận bản sao giá trị 3.

### Bài 11. Field khác parameter

Trong instance method có câu lệnh `this.counter += amount;`, field có thể thay đổi không?  
**Đáp án:** Có. Method **gán trực tiếp instance field**. Điều đó không có nghĩa `amount` là tham chiếu đến biến primitive caller.

### Bài 12. Integer null

Method nhận `int n`, caller truyền biến `Integer boxed = null;`. Lỗi gì có thể xảy ra?  
**Đáp án:** `NullPointerException` khi unboxing `boxed` để chuẩn bị primitive argument, trước khi vào body method.

### Bài 13. Float và double

Method nhận `double`, caller truyền `float f = 0.1f;`. Có hợp lệ không và có bảo đảm số thập phân trở nên chính xác bằng 0.1 không?  
**Đáp án:** Hợp lệ do `float` → `double`. Nhưng widening không phục hồi độ chính xác thập phân đã mất trong giá trị float.

### Bài 14. StringBuilder so với int

Tại sao method có thể gọi `builder.append("X")` khiến caller thấy object đổi, trong khi `n = 99` trên parameter `int` không làm biến caller đổi?  
**Đáp án:** Với `StringBuilder`, parameter chứa bản sao **reference** tới cùng object mutable, nên method sửa object đó. Với `int`, parameter chỉ chứa bản sao số; gán lại parameter không sửa biến bên ngoài. Cả hai vẫn là pass-by-value.

## Tài liệu tham khảo

- Java Language Specification, [`4.2 — Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): tám kiểu nguyên thủy và giá trị.
- Java Language Specification, [`8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): khai báo tham số hình thức.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): đánh giá đối số và chuyển quyền điều khiển vào method.
- Java Language Specification, [`5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3): các phép chuyển đổi kiểu hợp lệ khi truyền đối số.

## Kết luận

Trong Java, **mọi đối số được truyền theo giá trị**. Khi truyền một primitive value như `int`, `double` hoặc `boolean`, method nhận **một bản sao giá trị** trong biến tham số riêng. Gán lại hoặc tăng parameter **không tự thay đổi biến primitive của caller**; điều này vẫn đúng nếu tên hai biến giống nhau, method gọi đệ quy hay có chuyển đổi kiểu widening.

Muốn caller lưu giá trị mới, hãy **trả kết quả và để caller tự gán**, hoặc thiết kế một thao tác cập nhật state rõ ràng khi nghiệp vụ thực sự cần. Đừng nhầm thay đổi do **biểu thức đối số `x++`**, thay đổi **field trong thân method**, hoặc sửa một **object mutable qua reference** với việc Java truyền biến primitive theo tham chiếu. Hiểu sự phân biệt này giúp dự đoán code chính xác và tránh bug khi xây dựng API Java.
