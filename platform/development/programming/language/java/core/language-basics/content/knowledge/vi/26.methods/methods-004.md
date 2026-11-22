# Phương thức `static` cho các chương trình nhập môn Java

> **Java core — language-basics / Phương thức**  
> **Môi trường:** JDK 17+, một file Java độc lập, không cần thư viện ngoài.  
> **Mục tiêu:** Tạo và gọi phương thức `static` từ `main`; sử dụng tham số, giá trị trả về hoặc `void`; hiểu vì sao `static` thuộc về lớp, khác phương thức instance và khi nào không nên lạm dụng trạng thái static.

## 1. `static` nghĩa là phương thức thuộc về lớp

Phương thức có từ khóa `static` được gắn với **lớp**, không cần tạo đối tượng của lớp mới gọi được:

~~~java
public final class MathHelper {
    public static int add(int left, int right) {
        return left + right;
    }
}

// Có thể gọi MathHelper.add(3, 4), trả 7.
~~~

Các thành phần chính:

| Phần khai báo | Trong ví dụ | Vai trò |
| --- | --- | --- |
| Bộ điều chỉnh | `public static` | Cho phép gọi từ nơi có quyền truy cập mà không cần đối tượng |
| Kiểu trả về | `int` | Kết quả phép cộng |
| Tên phương thức | `add` | Tên dùng ở lời gọi |
| Tham số | `int left, int right` | Nhận hai đối số kiểu int |
| Thân | `{ return left + right; }` | Lệnh thực thi và trả kết quả |

Dạng tổng quát: `[access] static ReturnType name(Type parameter, ...) { ... }`. Dấu `[...]` trong dòng mô tả chỉ biểu thị thành phần tùy chọn, **không phải cú pháp Java** phải gõ.

Không nên hiểu “static” nghĩa là phương thức chỉ chạy một lần hoặc không thể nhận tham số: mỗi lần gọi vẫn thực thi thân với đối số được cung cấp. `static` chỉ xác định **cách phương thức thuộc về lớp và truy cập thành viên**.

## 2. `main` là phương thức `static` quen thuộc nhất

Với chương trình Java 17 chạy trực tiếp từ CLI, điểm bắt đầu thông thường:

~~~java
public static void main(String[] args) {
    System.out.println(add(2, 3));
}
~~~

Ý nghĩa:

- `public`: cho phép Java launcher truy cập điểm vào.
- `static`: launcher gọi `main` **không cần tạo một đối tượng** của lớp chứa nó.
- `void`: phương thức không trả giá trị cho nơi gọi; kết quả chương trình được quan sát qua in ra hoặc tác động khác.
- `main`: tên phương thức điểm vào trong dạng chuẩn này.
- `String[] args`: mảng nhận các đối số CLI; tên biến có thể khác `args`.

Khi `add` là một phương thức static hợp lệ nằm trong cùng lớp, có thể gọi ngay bằng `add(2, 3)`. Cách viết tường minh hơn là `ClassName.add(2, 3)`; thường nên dùng tên lớp khi gọi static từ bên ngoài.

~~~java
public final class Starter {
    private static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println("sum=" + add(2, 3));
        System.out.println("qualified=" + Starter.add(4, 5));
    }
}
~~~

Biên dịch/lệnh chạy với lớp `Starter` phải dùng file `Starter.java` khi lớp là `public`. Dòng `main` không tự chạy khi chỉ có khai báo; nó được launcher gọi khi thực thi `java Starter`.

## 3. Tham số, kiểu trả về và `void` hoạt động như bình thường

`static` không làm thay đổi quy tắc tham số và giá trị trả về:

~~~java
static double average(int a, int b) {
    return ((double) a + b) / 2;
}

static boolean isEven(int number) {
    return number % 2 == 0;
}

static void greet(String name) {
    if (name == null || name.isBlank()) {
        System.out.println("hello=guest");
        return; // Kết thúc sớm vì phương thức trả void.
    }
    System.out.println("hello=" + name.trim());
}
~~~

- `average(5, 2)` trả `3.5`. Ép `(double) a` trước khi cộng/chia giữ phần thập phân và tránh cộng hai `int` trước khi chuyển kiểu.
- `isEven(8)` trả `true`; `isEven(7)` trả `false`.
- `greet(" Lan ")` in `hello=Lan`; `greet(null)` in `hello=guest`.
- Phương thức có kiểu trả về khác `void` cần cung cấp giá trị phù hợp trên tất cả các đường đi hoàn tất bình thường. Phương thức `void` có thể dùng `return;`, nhưng không thể trả một giá trị như `return 5;`.

**Phân biệt:** Các số, chuỗi hay biến đặt trong dấu ngoặc **lúc gọi** là *đối số* (*arguments*); biến có kiểu được khai báo **trong định nghĩa phương thức** là *tham số* (*parameters*). Java truyền đối số **theo giá trị**, kể cả khi giá trị đó là tham chiếu đối tượng.

## 4. Gọi phương thức `static` trong cùng lớp hoặc lớp khác

Trong cùng lớp, gọi không kèm tên lớp thường dễ đọc:

~~~java
static int square(int n) {
    return n * n;
}

static int squarePlusOne(int n) {
    return square(n) + 1; // Gọi một phương thức static khác.
}
~~~

Khi gọi phương thức static của **lớp khác**, dùng tên lớp. Ví dụ quen thuộc trong JDK:

~~~java
int bigger = Math.max(4, 9);           // 9
String text = Integer.toString(42);   // "42"
~~~

`Math.max` và `Integer.toString` là phương thức static: không cần `new Math()` hay `new Integer(...)`. Java có cơ chế `static import` cho phép rút gọn tên lớp, nhưng trong bài nhập môn nên giữ `Math.max(...)` để thấy nguồn gốc phương thức.

Không bắt buộc mọi phương thức trong ứng dụng đều phải static. Chọn static khi hành vi có thể làm việc chỉ qua các tham số hoặc các tài nguyên lớp phù hợp, không phụ thuộc trạng thái riêng của một đối tượng.

## 5. Hạn chế: không có `this` và không truy cập instance trực tiếp

Một phương thức instance chạy với một đối tượng hiện tại, có thể dùng `this`. Một phương thức static **không có đối tượng `this` ngầm định**:

~~~java
public final class Multiplier {
    private final int factor;

    public Multiplier(int factor) {
        this.factor = factor;
    }

    public int multiply(int value) { // Instance method.
        return factor * value;
    }

    public static int triple(int value) { // Static method.
        return value * 3;
    }
}
~~~

Lời gọi hợp lệ:

~~~java
Multiplier item = new Multiplier(4);
System.out.println(item.multiply(3));       // 12.
System.out.println(Multiplier.triple(3));   // 9.
~~~

Trong phương thức static, không thể sử dụng `this.factor` hoặc gọi `multiply(3)` trực tiếp khi chưa có đối tượng phù hợp:

~~~java
// KHÔNG BIÊN DỊCH:
// static int wrong(int n) {
//     return factor * n; // factor là instance field.
// }
// static int wrongThis(int n) {
//     return this.factor * n; // 'this' không tồn tại trong static context.
// }
~~~

Nếu thật sự cần gọi phương thức instance từ một phương thức static, phải **có đối tượng** (ví dụ nhận đối tượng qua tham số hoặc tạo bằng `new`), rồi gọi `item.multiply(3)`.

| Tiêu chí | Phương thức `static` | Phương thức instance |
| --- | --- | --- |
| Thuộc về | Lớp | Đối tượng |
| Cách gọi nên dùng | `Type.method(args)` | `object.method(args)` |
| Cần đối tượng của lớp khi gọi? | Không | Có |
| Sử dụng `this` trực tiếp? | Không | Có |
| Truy cập trường instance trực tiếp? | Không | Có, trên đối tượng hiện tại |
| Gọi thành viên static khác? | Có | Có |

Constructor là cơ chế tạo/khởi tạo đối tượng, **không phải phương thức static**, và không khai báo kiểu trả về.

## 6. Trường `static`: trạng thái chung và nguy cơ khi học lập trình

Có thể khai báo một trường thuộc lớp để nhiều lần gọi phương thức static dùng chung:

~~~java
static int callCount = 0;

static int recordCall() {
    callCount++;
    return callCount;
}
~~~

Trong một lần chạy chương trình thông thường, hai lần gọi liên tiếp `recordCall()` sẽ trả `1` rồi `2`. Trạng thái **không reset về 0 ở mỗi lần gọi** vì `callCount` là trường của lớp chứ không phải biến cục bộ của phương thức.

Tuy nhiên, trạng thái static mutable làm cho kết quả phụ thuộc vào lịch sử lời gọi và gây khó kiểm thử. Khi nhiều luồng cùng sửa `callCount++`, thao tác này **không tự bảo đảm an toàn luồng**. Với bài nhập môn, ưu tiên các hàm static nhận tham số và trả kết quả rõ ràng:

~~~java
static int calculateTotal(int price, int quantity) {
    return price * quantity;
}
~~~

Phép tính trên vẫn có nguy cơ tràn `int` nếu giá trị lớn; cần kiểu hoặc kiểm tra thích hợp trong ứng dụng thực. `static final` phù hợp cho **hằng số bất biến theo hợp đồng** (ví dụ `static final int MAX_RETRIES = 3;`), nhưng `final` trên tham chiếu tới một đối tượng mutable không tự làm đối tượng bất biến.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **StaticMethodsIntroDemo.java**:

~~~java
public final class StaticMethodsIntroDemo {
    private static int callCount = 0;

    private final int factor;

    public StaticMethodsIntroDemo(int factor) {
        this.factor = factor;
    }

    public int multiply(int value) {
        return factor * value;
    }

    private static int add(int left, int right) {
        return left + right;
    }

    private static double average(int a, int b) {
        return ((double) a + b) / 2;
    }

    private static boolean isEven(int n) {
        return n % 2 == 0;
    }

    private static String category(int n) {
        if (n < 0) {
            return "NEG";
        }
        if (n == 0) {
            return "ZERO";
        }
        return "POS";
    }

    private static void greet(String name) {
        if (name == null || name.isBlank()) {
            System.out.println("hello=guest");
            return;
        }
        System.out.println("hello=" + name.trim());
    }

    private static int recordCall() {
        callCount++;
        return callCount;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(3, 4));
        System.out.println("qualifiedAdd="
                + StaticMethodsIntroDemo.add(5, 6));
        System.out.println("average=" + average(5, 2));
        System.out.println("even8=" + isEven(8));
        System.out.println("even7=" + isEven(7));

        System.out.println("negative=" + category(-2));
        System.out.println("zero=" + category(0));
        System.out.println("positive=" + category(9));

        greet(" Lan ");
        greet(null);

        System.out.println("mathMax=" + Math.max(4, 9));
        System.out.println("callOne=" + recordCall());
        System.out.println("callTwo=" + recordCall());

        StaticMethodsIntroDemo first = new StaticMethodsIntroDemo(3);
        StaticMethodsIntroDemo second = new StaticMethodsIntroDemo(10);
        System.out.println("instanceOne=" + first.multiply(4));
        System.out.println("instanceTwo=" + second.multiply(2));
        System.out.println("classCounter=" + StaticMethodsIntroDemo.callCount);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 StaticMethodsIntroDemo.java
java StaticMethodsIntroDemo
~~~

**Expected stdout chính xác:**

~~~text
add=7
qualifiedAdd=11
average=3.5
even8=true
even7=false
negative=NEG
zero=ZERO
positive=POS
hello=Lan
hello=guest
mathMax=9
callOne=1
callTwo=2
instanceOne=12
instanceTwo=20
classCounter=2
~~~

Hai lời gọi `add` cho thấy static có thể gọi trực tiếp hoặc qua tên lớp. `instanceOne` và `instanceTwo` khác nhau vì hai đối tượng có `factor` khác nhau. `callOne`/`callTwo` và `classCounter` minh họa một trường static dùng chung trong cùng lần chạy.

## 8. Lỗi thường gặp, bài tập và checklist

| Lỗi / hiểu lầm | Cách xử lý |
| --- | --- |
| Cho rằng phải `new` mới gọi được static | Gọi `Type.method(...)` hoặc trực tiếp trong cùng lớp |
| Dùng `this` trong phương thức static | Không có `this`; cần đối tượng nếu truy cập state instance |
| Gọi phương thức instance từ `main` không qua đối tượng | Tạo/nhận đối tượng rồi gọi `object.method(...)` |
| Nghĩ static chạy chỉ một lần | Mỗi lần gọi đều thực thi thân phương thức |
| Nghĩ biến cục bộ trong static tồn tại mãi giữa các lần gọi | Biến cục bộ được tạo theo mỗi lần gọi; trường static thuộc lớp |
| Dùng static mutable field cho mọi kết quả trung gian | Ưu tiên tham số + return để tránh state dùng chung |
| Quên `return value;` trong hàm static trả `int` | Các nhánh hoàn tất bình thường phải trả giá trị đúng kiểu |
| Dùng `void` rồi cố lấy kết quả từ biểu thức gọi | `void` không cung cấp giá trị để gán |

**Bài 1.** Viết `static int cube(int n)` rồi gọi từ `main` với `n = 3`. Dự đoán kết quả.

**Bài 2.** Viết `static boolean isAdult(int age)` trả true khi `age >= 18`. In kết quả với tuổi 17, 18 và 21.

**Bài 3.** Viết `static void printIfPresent(String value)`: bỏ qua null hoặc chuỗi trắng bằng `return;`, in nếu có nội dung.

**Bài 4.** Tạo lớp có trường `factor` và phương thức instance `multiply`. Thử gọi từ `main` trước/sau khi tạo đối tượng; xác định lỗi biên dịch.

**Bài 5.** So sánh biến cục bộ `int calls = 0` khai báo trong hàm với trường `static int callCount` sau hai lần gọi. Vì sao kết quả khác nhau?

**Checklist:** Phương thức có thực sự không cần `this` hoặc trạng thái của một đối tượng không? Tham số/kiểu trả về/`void` đã đúng chưa? Tên lớp/file và lệnh CLI có khớp không? Có state static mutable gây phụ thuộc giữa các lần gọi không?

### Ghi nhớ

**`static` đặt phương thức ở cấp lớp**: rất phù hợp cho `main` và các hàm tiện ích nhỏ nhận tham số rồi trả kết quả. Phương thức static không có `this`, không trực tiếp truy cập thành viên instance nếu thiếu đối tượng. Khi cần trạng thái riêng cho từng đối tượng, dùng phương thức instance. Đừng nhầm `static method` với `static field`: trường static có thể giữ trạng thái **chung**, nên cần dùng có chủ đích.
