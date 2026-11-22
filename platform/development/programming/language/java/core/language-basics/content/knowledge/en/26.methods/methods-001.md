# Khai báo phương thức: tên, tham số, kiểu trả về và thân trong Java

> **Java core — language-basics / Phương thức**  
> **Môi trường:** JDK 17+, ví dụ một file độc lập, không dùng thư viện ngoài.  
> **Mục tiêu:** Tự khai báo và gọi phương thức, xác định rõ **tên**, **danh sách tham số**, **kiểu trả về** và **thân**; hiểu `void`, `return`, phạm vi biến, `static` và phương thức đối tượng.

## 1. Cấu trúc của một khai báo phương thức

Phương thức là một khối hành vi có tên được định nghĩa trong một lớp, interface hoặc kiểu cho phép khai báo phương thức của Java.

~~~java
public static int add(int left, int right) {
    int result = left + right;
    return result;
}
~~~

Các phần trong khai báo:

| Thành phần | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Bộ điều chỉnh | `public static` | Quyền truy cập và thuộc về lớp hay đối tượng |
| Kiểu trả về | `int` | Kết quả mà nơi gọi nhận được |
| Tên phương thức | `add` | Định danh để gọi phương thức |
| Tham số hình thức | `int left, int right` | Hai biến nhận đối số khi gọi |
| Thân phương thức | `{ ... }` | Những câu lệnh chạy khi phương thức được gọi |
| Lệnh kết thúc có giá trị | `return result;` | Trả giá trị và kết thúc lần gọi |

Khi gọi `add(3, 4)`, đối số `3` gán vào tham số `left` và `4` gán vào `right`, nên phương thức trả `7`. Chỉ **khai báo** không làm thân chạy; thân được thực hiện khi có lời gọi phù hợp.

Dạng khái quát:

~~~java
[modifiers] ReturnType methodName(Type1 parameter1, Type2 parameter2) {
    // statements
}
~~~

Dấu ngoặc vuông trong dòng minh họa là **ký hiệu mô tả tùy chọn**, không phải ký tự phải nhập vào Java. Một khai báo có thể **không có tham số**: `static String version() { return "17+"; }`. Các loại phương thức không trừu tượng thông thường có thân trong dấu `{ }`; khai báo phương thức `abstract` hoặc trong interface có thể dùng dấu `;` thay cho thân theo quy tắc riêng.

## 2. Đặt tên và chọn kiểu trả về

Tên phương thức tuân theo quy tắc định danh của Java; thông lệ là **lowerCamelCase** với một động từ hoặc cụm mô tả hành động như `calculateTotal`, `findFirst`, `printReport`:

~~~java
static int square(int number) {
    return number * number;
}

static boolean isPositive(int number) {
    return number > 0;
}

static String title() {
    return "Java 17";
}
~~~

Kiểu trả về có thể là primitive (`int`, `boolean`, `double`...), lớp (`String`), mảng (`int[]`), một interface hoặc `void`.

- Với kiểu khác `void`, `return expression;` phải trả giá trị **gán được** cho kiểu khai báo; các đường điều khiển hoàn tất bình thường không được thiếu kết quả.
- Với `void`, phương thức không cung cấp giá trị trả về; có thể kết thúc bằng `return;` hoặc đi đến cuối thân.
- `return` kết thúc **lần gọi phương thức hiện tại**, không tự động kết thúc `main`, vòng lặp của phương thức gọi hay toàn bộ JVM.

~~~java
static void announce(String text) {
    if (text == null) {
        return; // Kết thúc phương thức void sớm.
    }
    System.out.println(text);
}
~~~

Một phương thức `void` không thể dùng `return 5;`; một phương thức khai báo trả `int` không thể dùng `return "five";`.

## 3. Tham số hình thức khác đối số thực tế

~~~java
static double average(int a, int b) {
    return ((double) a + b) / 2;
}

// Trong phương thức main:
// double result = average(5, 2); // 3.5
~~~

`a` và `b` là **tham số hình thức** (*parameters*) trong khai báo; `5` và `2` là **đối số** (*arguments*) tại lời gọi.

- Đối số tương ứng với tham số theo **thứ tự vị trí**, cần tương thích kiểu; `average(2, 5)` cho cùng kết quả ở đây nhưng không phải mọi phương thức đều đối xứng.
- Trong khai báo, **mỗi tham số cần ghi kiểu**: `int a, int b`, không phải `int a, b` nếu đang viết danh sách tham số phương thức.
- Không thể dùng cùng một tên cho hai tham số trong cùng khai báo.
- Tham số chỉ có phạm vi trong phần thân/phạm vi cho phép của phương thức, không phải biến toàn cục.
- Java **truyền đối số theo giá trị**: với primitive, tham số nhận bản sao giá trị; với đối tượng, tham số nhận bản sao **tham chiếu**.

~~~java
static void incrementLocal(int value) {
    value++;
}

// int count = 10;
// incrementLocal(count);
// count vẫn bằng 10.
~~~

Gán lại một tham số tham chiếu không đổi biến của caller; nhưng gọi phương thức làm thay đổi **đối tượng mutable được tham chiếu chung** có thể làm caller thấy trạng thái mới. Đây vẫn là truyền theo giá trị của tham chiếu, không phải truyền biến theo tham chiếu.

## 4. Thân phương thức, biến cục bộ và luồng điều khiển

Phần thân là một khối lệnh `{ ... }`. Nó có thể khai báo biến cục bộ, kiểm tra điều kiện, lặp, gọi phương thức khác và trả kết quả:

~~~java
static int clamp(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min must not exceed max");
    }
    if (value < min) {
        return min;
    }
    if (value > max) {
        return max;
    }
    return value;
}
~~~

Hàm này trả số đã giới hạn vào đoạn `[min, max]`. Các `return` nằm ở nhánh khác nhau; khi đi tới một `return`, phần còn lại của thân không chạy.

**Phạm vi và khởi tạo:**

~~~java
static int example(int input) {
    int doubled = input * 2; // Biến cục bộ.
    return doubled;
}
// doubled và input không dùng trực tiếp bên ngoài phương thức.
~~~

Biến cục bộ phải được **gán chắc chắn trước khi đọc**. Một khai báo như `int result; return result;` không biên dịch nếu chưa có đường gán hợp lệ. Không thể khai báo trực tiếp **một phương thức bên trong thân một phương thức khác**; hãy đặt nó là thành viên của lớp hoặc một kiểu phù hợp.

**Lỗi biên dịch điển hình:**

~~~java
// SAI: thiếu return cho trường hợp number <= 0.
// static int missingResult(int number) {
//     if (number > 0) return number;
// }

// SAI: kiểu return không tương thích.
// static int wrongType() { return "Java"; }

// SAI: khai báo phương thức lồng trực tiếp trong phương thức.
// static void outer() { int inner() { return 1; } }
~~~

## 5. `static` khác phương thức của đối tượng

Phương thức `static` thuộc về **lớp** và có thể gọi bằng tên lớp. Phương thức **instance** gắn với một đối tượng, nên thường gọi qua tham chiếu đối tượng:

~~~java
public final class Counter {
    private int count;

    public Counter(int initial) {
        count = initial;
    }

    public void increase() { // Phương thức instance.
        count++;
    }

    public int current() { // Phương thức instance.
        return count;
    }

    public static int add(int a, int b) { // Phương thức static.
        return a + b;
    }
}
~~~

Cách gọi (nếu đặt lớp ví dụ vào file hợp lệ):

~~~java
Counter counter = new Counter(2);
counter.increase();
System.out.println(counter.current()); // 3
System.out.println(Counter.add(3, 4)); // 7
~~~

**Đặc biệt:** `Counter(int initial)` là **constructor**, vì tên trùng với lớp và **không có kiểu trả về**; nó không phải phương thức `void`. Ngược lại, `void Counter()` sẽ là một phương thức có tên `Counter`, không phải constructor.

`static` không được dùng trực tiếp biến instance qua `this` khi không có đối tượng. Trong ví dụ chạy ở cuối bài, `main` là `static`; nó gọi các phương thức static trực tiếp và tạo đối tượng trước khi gọi phương thức instance.

## 6. Chữ ký phương thức, nạp chồng và tham số thay đổi

Với các phương thức thông thường trong một lớp, **chữ ký** chủ yếu được phân biệt bằng **tên và kiểu các tham số theo thứ tự**. Tên biến tham số và kiểu trả về **không đủ** để tạo một overload khác:

~~~java
static String describe(int number) {
    return "int:" + number;
}

static String describe(String text) {
    return "String:" + text;
}
~~~

Hai phương thức cùng tên `describe` được **nạp chồng** (*overloading*) vì một cái nhận `int`, cái kia nhận `String`. Lời gọi `describe(12)` chọn phiên bản `int`; `describe("12")` chọn phiên bản `String`. Trình biên dịch dùng kiểu tại nơi gọi để phân giải overload.

~~~java
// SAI nếu đã có static int add(int a, int b):
// static long add(int x, int y) { return x + y; }
// Chỉ đổi tên tham số và kiểu trả về không tạo overload hợp lệ.
~~~

Nếu cần số đối số `int` thay đổi, có thể dùng **varargs**, phải đặt sau cùng trong danh sách tham số:

~~~java
static int sumAll(int... values) {
    int sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}

// sumAll(2, 3, 4) == 9; sumAll() == 0.
~~~

`int... values` hoạt động như một mảng `int[]` trong thân. Không cần dùng varargs cho mọi bài: số lượng tham số cố định thường làm hợp đồng đơn giản hơn.

## 7. Cú pháp CLI và chương trình Java 17+ runnable

Tạo file **MethodDeclarationDemo.java**:

~~~java
public final class MethodDeclarationDemo {
    private final String prefix;

    // Constructor: không có kiểu trả về.
    public MethodDeclarationDemo(String prefix) {
        this.prefix = prefix;
    }

    // Phương thức instance: cần đối tượng để gọi.
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            return prefix + "bạn";
        }
        return prefix + name.trim();
    }

    public static int add(int left, int right) {
        return left + right;
    }

    private static double average(int a, int b) {
        return ((double) a + b) / 2;
    }

    private static void announce(String label) {
        System.out.println("announce=" + label);
    }

    private static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        if (value < min) {
            return min;
        }
        if (value > max) {
            return max;
        }
        return value;
    }

    private static int lengthOrMinusOne(String value) {
        return value == null ? -1 : value.length();
    }

    private static void incrementLocal(int value) {
        value++; // Không đổi biến bên ngoài phương thức.
    }

    private static String describe(int number) {
        return "int:" + number;
    }

    private static String describe(String text) {
        return "String:" + text;
    }

    private static int sumAll(int... values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(3, 4));
        System.out.println("average=" + average(5, 2));
        announce("GO");

        System.out.println("clampLow=" + clamp(-5, 0, 10));
        System.out.println("clampMiddle=" + clamp(6, 0, 10));
        System.out.println("clampHigh=" + clamp(18, 0, 10));

        System.out.println("length=" + lengthOrMinusOne("Java"));
        System.out.println("lengthNull=" + lengthOrMinusOne(null));

        MethodDeclarationDemo demo =
                new MethodDeclarationDemo("Xin chào, ");
        System.out.println("greet=" + demo.greet(" Lan "));
        System.out.println("greetBlank=" + demo.greet("  "));

        int counter = 10;
        incrementLocal(counter);
        System.out.println("afterCall=" + counter);

        System.out.println("describeNumber=" + describe(12));
        System.out.println("describeText=" + describe("12"));
        System.out.println("sumAll=" + sumAll(2, 3, 4));
        System.out.println("sumNone=" + sumAll());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file, trong Bash, PowerShell hoặc Command Prompt:

~~~bash
javac -encoding UTF-8 MethodDeclarationDemo.java
java MethodDeclarationDemo
~~~

**Expected stdout chính xác:**

~~~text
add=7
average=3.5
announce=GO
clampLow=0
clampMiddle=6
clampHigh=10
length=4
lengthNull=-1
greet=Xin chào, Lan
greetBlank=Xin chào, bạn
afterCall=10
describeNumber=int:12
describeText=String:12
sumAll=9
sumNone=0
~~~

`add`/`average` minh họa nhận tham số và trả giá trị; `announce` là `void`. Ba nhánh `clamp` cho thấy nhiều đường `return`; `greet` là phương thức instance có tham chiếu `this` gián tiếp qua trường `prefix`. `afterCall=10` chứng minh tham số `int` không sửa biến caller. Hai `describe` minh họa overload, còn `sumAll()` cho thấy varargs có thể nhận 0 đối số.

## 8. Lỗi thường gặp và bài tập

| Lỗi / hiểu lầm | Cách sửa |
| --- | --- |
| Quên kiểu trả về trong khai báo phương thức | Ghi `T` hoặc `void`; chỉ constructor mới không có kiểu trả về |
| Nhầm tham số và đối số | Tham số đặt trong khai báo; đối số truyền ở nơi gọi |
| Viết `static int add(int a, b)` | Ghi đủ kiểu: `int a, int b` |
| Thiếu `return` trên một đường đi của hàm trả kết quả | Bảo đảm mọi đường hoàn tất bình thường đều trả giá trị |
| `return value;` trong hàm `void` | Dùng `return;` hoặc bỏ return |
| Gọi method instance từ `main` mà không có đối tượng | Tạo đối tượng, rồi gọi qua tham chiếu |
| Muốn overload chỉ bằng đổi kiểu trả về/tên tham số | Đổi danh sách kiểu tham số một cách hợp lệ |
| Mong sửa biến `int` của caller bằng cách sửa tham số | Giá trị tham số là bản sao; trả kết quả rồi gán ở caller |

**Bài 1.** Viết `static int multiply(int a, int b)` và gọi trong `main` với `3, 5`; ghi chính xác giá trị trả về.

**Bài 2.** Viết `static String category(int n)` trả `"NEG"`, `"ZERO"` hoặc `"POS"`, không bỏ sót đường `return`.

**Bài 3.** Viết `static void printIfNonBlank(String text)`, xử lý `null` và chuỗi blank bằng `return;` rồi in khi hợp lệ.

**Bài 4.** Tạo một lớp có trường instance, constructor và phương thức instance trả giá trị; so sánh cách gọi với một phương thức `static`.

**Bài 5.** Viết hai overload `format(int value)` và `format(double value)`. Giải thích vì sao chỉ viết hai hàm cùng tham số nhưng kiểu trả về khác nhau là sai.

**Bài 6.** Dùng `int... values` để viết hàm đếm số phần tử dương; thử không đối số, một đối số và nhiều đối số.

### Ghi nhớ

**Một phương thức được định nghĩa bởi tên, tham số, kiểu trả về và thân lệnh.** Khi gọi, đối số được truyền theo giá trị vào tham số. `return value;` cung cấp kết quả cho phương thức có kiểu trả về, còn `void` không trả giá trị. Dùng `static` khi hành vi thuộc lớp, dùng phương thức instance khi cần trạng thái đối tượng, và phân biệt rõ method với constructor.
