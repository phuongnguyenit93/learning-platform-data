# Quan hệ giữa kiểu của biểu thức khởi tạo và kiểu của biến trong Java 10+ (`var`)

Trong Java, `var` cho phép trình biên dịch suy luận **kiểu tĩnh của biến cục bộ** từ **kiểu của biểu thức khởi tạo**. Tính năng này có từ Java 10 và tiếp tục áp dụng trong Java hiện đại. Điều quan trọng nhất: kiểu được xác định **một lần tại thời điểm biên dịch**, không đổi theo các giá trị gán về sau và không phụ thuộc vào lớp thực tế của đối tượng tại thời điểm chạy.

## 1. Quy tắc suy luận cốt lõi

```java
var tenBien = bieuThucKhoiTao;
```

Với khai báo này, trình biên dịch xác định kiểu của `bieuThucKhoiTao` như một biểu thức độc lập, rồi suy ra kiểu cho `tenBien`. Sau đó, mọi phép gán và mọi lời gọi phương thức trên biến đều được kiểm tra kiểu giống như khi ta khai báo kiểu tường minh.

```java
var count = 10;          // kiểu của count là int
count = 20;              // hợp lệ
// count = "hai mươi";  // lỗi biên dịch: String không gán được cho int
```

Có thể hình dung `var count = 10;` tương đương về kiểu với `int count = 10;`. `var` không phải kiểu `Object` mặc định, không phải kiểu động và không khiến Java thay đổi cách kiểm tra kiểu.

**Phân biệt ba khái niệm:**

- **Kiểu tĩnh của biểu thức:** kiểu mà trình biên dịch xác định cho biểu thức bên phải, dựa trên quy tắc ngôn ngữ và kiểu khai báo của các toán hạng/phương thức.
- **Kiểu tĩnh của biến:** kiểu mà trình biên dịch gán cho biến được khai báo bằng `var`; nó quyết định phép gán, member và overload nào hợp lệ.
- **Lớp thực tế ở runtime:** lớp của đối tượng mà biến đang tham chiếu; có thể là lớp con của kiểu tĩnh và có thể thay đổi sau phép gán hợp lệ.

Về mặt đặc tả, với kiểu biểu thức khởi tạo `T`, Java sử dụng phép *upward projection* đối với một số kiểu suy luận nội bộ (như capture type) để ra kiểu của biến. Trong các trường hợp thông thường, có thể hiểu trực tiếp rằng **kiểu của biến chính là kiểu tĩnh của biểu thức khởi tạo**.

## 2. Biểu thức khởi tạo thuộc kiểu nào, biến nhận kiểu tương ứng

| Khai báo | Kiểu suy ra | Vì sao |
| --- | --- | --- |
| `var a = 10;` | `int` | Literal số nguyên mặc định là `int` khi nằm trong miền giá trị. |
| `var b = 10L;` | `long` | Hậu tố `L` làm literal có kiểu `long`. |
| `var c = 2.5;` | `double` | Literal dấu phẩy động mặc định là `double`. |
| `var d = 2.5f;` | `float` | Hậu tố `f` chỉ rõ `float`. |
| `var enabled = true;` | `boolean` | Biểu thức boolean. |
| `var title = "Java";` | `String` | Literal chuỗi có kiểu `String`. |
| `var codes = new int[]{1, 2};` | `int[]` | Biểu thức tạo mảng có kiểu `int[]`. |
| `var users = new ArrayList<String>();` | `ArrayList<String>` | Biểu thức `new` trả về kiểu lớp cụ thể. |
| `var names = List.of("An", "Bình");` | `List<String>` | Kiểu trả về của lời gọi generic được suy ra là `List<String>`. |

Bảng trên mô tả kiểu **lúc biên dịch**, không phải tên lớp mà `getClass()` có thể trả về ở runtime. Ví dụ, `List.of(...)` trả về một đối tượng thuộc lớp triển khai của thư viện, nhưng kiểu tĩnh của biểu thức vẫn là `List<String>`.

## 3. Kiểu của toàn bộ biểu thức, không chỉ kiểu của từng giá trị

Các toán tử Java thực hiện những quy tắc như *numeric promotion*, chia số nguyên hoặc ép kiểu trước khi `var` suy luận. Vì vậy, phải hỏi **toàn bộ biểu thức bên phải có kiểu gì?**

```java
var quotient = 5 / 2;                 // int, giá trị 2
var precise = 5.0 / 2;                // double, giá trị 2.5
var promoted = (short) 1 + (short) 2; // int, giá trị 3
var small = (short) 1;                // short
var widened = (long) 5;              // long
var decimal = 3 + 0.5f;               // float, giá trị 3.5f
```

- `5 / 2` là phép chia trên hai `int`, nên tạo `int`; `var` không tự chọn `double` để giữ phần thập phân.
- Trong phép toán cộng số học, `byte`, `short` và `char` thường được nâng lên `int`; do đó cộng hai giá trị `short` vẫn tạo `int`.
- Ép kiểu rõ ràng có thể thay đổi kiểu của **biểu thức khởi tạo**. Ví dụ, `(long) 5` có kiểu `long`, còn `(short) 1` có kiểu `short`.

```java
var amount = 10;        // int
// amount = 10L;        // lỗi: không tự chuyển long về int
var amountLong = 10L;   // long ngay từ khai báo
```

Nếu cần một kiểu số cụ thể, hãy làm rõ kiểu của biểu thức khởi tạo hoặc dùng khai báo kiểu tường minh.

## 4. Kiểu tĩnh khác với lớp runtime và ảnh hưởng đến đa hình

Đối tượng có thể thuộc một lớp con, nhưng nếu biểu thức khởi tạo được khai báo trả về kiểu cha hoặc interface thì biến `var` cũng nhận **kiểu cha/interface đó**.

```java
static Number createNumber() {
    return Integer.valueOf(7);
}

// Trong một phương thức:
var number = createNumber();   // kiểu tĩnh: Number
number = Double.valueOf(3.5); // hợp lệ: Double là một Number
System.out.println(number.intValue()); // gọi thành viên của Number
```

Dù lần đầu `createNumber()` trả về đối tượng `Integer`, kiểu của biểu thức gọi phương thức là `Number` theo khai báo phương thức. Khi gán `Double` về sau, kiểu biến vẫn là `Number`.

Ngược lại:

```java
var direct = Integer.valueOf(7); // kiểu Integer
// direct = Double.valueOf(3.5); // lỗi: Double không phải Integer

var fromCast = (Number) Integer.valueOf(7); // kiểu Number
fromCast = Double.valueOf(3.5);             // hợp lệ
```

**Hệ quả đối với overload:** Java chọn overload dựa trên kiểu tĩnh của tham số tại thời điểm biên dịch, không chọn theo lớp runtime của đối tượng.

```java
static String describe(Number n)  { return "Number"; }
static String describe(Integer n) { return "Integer"; }

// Trong một phương thức:
var x = Integer.valueOf(1);           // Integer
var y = (Number) Integer.valueOf(1);  // Number
System.out.println(describe(x));      // Integer
System.out.println(describe(y));      // Number
```

Khi muốn biến đại diện cho một hợp đồng chung, khai báo tường minh thường dễ đọc và linh hoạt hơn:

```java
List<String> names = new ArrayList<>();
names = new LinkedList<>();            // hợp lệ: cùng thực hiện List<String>

var concrete = new ArrayList<String>(); // kiểu ArrayList<String>
// concrete = new LinkedList<String>(); // lỗi: LinkedList không phải ArrayList
```

`var` không tự đoán rằng ta “muốn dùng `List`” thay vì `ArrayList`.

## 5. Generics: thiếu kiểu đích có thể dẫn đến suy luận `Object`

Đây là chỗ quan hệ giữa biểu thức khởi tạo và biến dễ gây hiểu nhầm nhất. Với khai báo tường minh, kiểu bên trái có thể đóng vai trò **target type** giúp suy luận type argument. Với `var`, biểu thức khởi tạo được xét như một biểu thức độc lập; bên trái không cung cấp target type tương tự.

```java
List<String> first = new ArrayList<>(); // diamond nhận ngữ cảnh List<String>
var second = new ArrayList<>();         // ArrayList<Object>
var third = new ArrayList<String>();    // ArrayList<String>
var fourth = List.of("A", "B");          // List<String>
```

Ở `second`, toán tử diamond `<>` không có ràng buộc đủ cụ thể nên constructor generic thường suy ra `Object`; kiểu của biến là `ArrayList<Object>`. Đây **không** phải `ArrayList<String>`, cũng không chuyển thành `ArrayList<String>` sau lệnh `second.add("A")`. Ở `fourth`, đối số `"A"` và `"B"` đã cung cấp thông tin để suy ra `String`.

Tương tự với phương thức generic không có dữ liệu đầu vào để suy luận:

```java
var empty1 = Collections.emptyList();             // List<Object>
var empty2 = Collections.<String>emptyList();     // List<String>
List<String> empty3 = Collections.emptyList();    // List<String> từ target type
```

Các ví dụ này cần `import java.util.*;`. Khi kiểu tham số generic ảnh hưởng tới API hoặc sự an toàn kiểu, nên ghi rõ type argument hoặc khai báo kiểu bên trái; đừng kỳ vọng `var` suy ra ý định chưa được biểu thức thể hiện.

## 6. Lời gọi phương thức, toán tử điều kiện, ép kiểu và mảng

**Lời gọi phương thức:** kiểu biến dựa trên kiểu trả về *đã được xác định ở compile time*, gồm các type argument được suy luận từ lời gọi; không dựa trên đối tượng thực tế được trả về.

```java
var sizes = List.of("a", "bb").stream()
        .map(String::length)
        .toList(); // List<Integer> (toList có từ Java 16)
```

**Toán tử điều kiện `?:`:** hai nhánh tham gia quy tắc xác định kiểu của **toàn bộ** biểu thức điều kiện. Chỉ sau đó `var` nhận kết quả.

```java
boolean flag = true;
var numeric = flag ? 1 : 2L;           // long, giá trị 1L
var message = flag ? "OK" : "Retry";   // String
var floating = flag ? 1 : 2.5;        // double, giá trị 1.0
```

Với hai nhánh có kiểu tham chiếu khác nhau, kiểu chung có thể phức tạp (ví dụ một supertype hay intersection type). Không mặc định rằng Java lấy kiểu của nhánh đang chạy; cả hai nhánh được kiểm tra ở thời điểm biên dịch.

**Ép kiểu:** phép cast thay đổi kiểu tĩnh của biểu thức khi cast hợp lệ, do đó có thể ảnh hưởng trực tiếp đến kiểu của biến:

```java
var value1 = Integer.valueOf(5);          // Integer
var value2 = (Number) Integer.valueOf(5); // Number
```

**Mảng:** biểu thức `new int[]{...}` có kiểu xác định, còn cú pháp initializer rút gọn `{...}` cần một kiểu đích tường minh:

```java
var good = new int[]{1, 2, 3}; // int[]
int[] alsoGood = {1, 2, 3};
// var bad = {1, 2, 3};        // lỗi biên dịch
```

## 7. Khi biểu thức chưa đủ thông tin để có một kiểu hợp lệ

`var` không thể giải quyết mọi biểu thức. Những khai báo sau **không biên dịch**:

```java
// var noInitializer;                    // thiếu biểu thức khởi tạo
// var nothing = null;                   // literal null không xác định kiểu cụ thể
// var handler = () -> System.out.println("hi"); // lambda cần target type
// var comparer = String::compareTo;     // method reference cần target type
// var values = {1, 2, 3};              // array initializer rút gọn cần target type
// var result = System.out.println("x"); // biểu thức void không có giá trị để gán
```

Cách sửa là cung cấp kiểu đích khi biểu thức cần nó:

```java
String nullable = null;
Runnable handler = () -> System.out.println("hi");
Comparator<String> comparer = String::compareTo;
int[] values = {1, 2, 3};

// Có thể dùng var nếu biểu thức đã có kiểu nhờ cast phù hợp:
var nullableWithType = (String) null; // String
var typedHandler = (Runnable) () -> System.out.println("hi"); // Runnable
```

Các ví dụ `Comparator` cần `import java.util.Comparator;`. `var` không ngăn một biến kiểu tham chiếu nhận `null` về sau; nó chỉ không thể suy luận kiểu từ **duy nhất literal `null`** khi khởi tạo.

## 8. Ví dụ đầy đủ có thể biên dịch và chạy

Lưu mã sau vào `VarInitializerTypeDemo.java` (Java 17 trở lên):

```java
import java.util.ArrayList;
import java.util.List;

public class VarInitializerTypeDemo {
    static Number makeNumber() {
        return Integer.valueOf(7);
    }

    static String choose(Number n) {
        return "Number";
    }

    static String choose(Integer n) {
        return "Integer";
    }

    public static void main(String[] args) {
        var count = 10;                         // int
        var total = 10L;                         // long
        var ratio = 5 / 2;                       // int
        var exactRatio = 5.0 / 2;                // double
        var text = "Java";                       // String

        var fixed = new ArrayList<String>();     // ArrayList<String>
        fixed.add("A");
        var inferred = List.of("A", "B");         // List<String>

        var empty = new ArrayList<>();           // ArrayList<Object>
        empty.add("C");

        var number = makeNumber();               // Number
        var overload = choose(number);           // chọn choose(Number)
        number = Double.valueOf(3.5);            // Number vẫn là kiểu tĩnh

        var choice = true ? 1 : 2.5;             // double
        var numbers = new int[]{1, 2, 3};        // int[]

        System.out.println("count=" + count + ", total=" + total);
        System.out.println("ratio=" + ratio + ", exactRatio=" + exactRatio);
        System.out.println("text=" + text);
        System.out.println("fixed=" + fixed + ", inferred=" + inferred);
        System.out.println("empty=" + empty);
        System.out.println("overload=" + overload);
        System.out.println("numberType=" + number.getClass().getSimpleName()
                + ", number=" + number);
        System.out.println("choice=" + choice + ", len=" + numbers.length);
    }
}
```

Biên dịch và chạy:

```bash
javac VarInitializerTypeDemo.java
java VarInitializerTypeDemo
```

Kết quả chuẩn:

```text
count=10, total=10
ratio=2, exactRatio=2.5
text=Java
fixed=[A], inferred=[A, B]
empty=[C]
overload=Number
numberType=Double, number=3.5
choice=1.0, len=3
```

Giải thích điểm cốt lõi: `number` có **kiểu tĩnh `Number`** vì `makeNumber()` khai báo trả về `Number`; overload được chọn là `choose(Number)` ngay khi biên dịch. Sau khi gán `Double`, `number.getClass()` cho biết lớp runtime là `Double`, nhưng kiểu tĩnh của `number` vẫn là `Number`.

## 9. Cách chọn giữa `var` và kiểu tường minh

- Dùng `var` khi kiểu của biểu thức khởi tạo rõ ngay tại chỗ và giữ cho mã dễ đọc, ví dụ `var count = 0;` hoặc `var names = List.of("A", "B");`.
- Dùng kiểu tường minh khi muốn nhấn mạnh **hợp đồng interface/supertype**, ví dụ `List<String> names = new ArrayList<>();`.
- Kiểm tra kỹ literal số, toán tử `/`, numeric promotion, `?:` và cast: chúng quyết định kiểu biểu thức **trước khi** suy ra kiểu biến.
- Với generic factory/diamond không có ngữ cảnh đủ mạnh, ghi rõ type argument hoặc kiểu biến để tránh suy ra `Object` ngoài ý định.
- Với lambda, method reference, `null` và array initializer dạng `{...}`, cung cấp target type hợp lệ bằng khai báo/cast hoặc viết lại biểu thức.
- Đừng dựa vào lần gán thứ hai, phương thức gọi về sau hoặc `getClass()` để dự đoán kiểu mà `var` đã suy luận.

## 10. Tự kiểm tra

Trong một phương thức có biến `boolean flag = true;`, hãy xác định kiểu tĩnh của các biến và cho biết khai báo cuối có biên dịch không:

```java
var a = 2 + 3.0;
var b = (short) 1;
var c = List.of(1, 2);
var d = new ArrayList<>();
var e = flag ? 1 : 2L;
// var f = null;
```

Đáp án: `a` là `double` (toán hạng `double`); `b` là `short` (cast); `c` là `List<Integer>` (đối số `Integer` từ boxing và type inference); `d` là `ArrayList<Object>` (diamond thiếu target type); `e` là `long` (numeric conditional expression); `f` không hợp lệ vì `null` không cung cấp kiểu suy luận. Cần `import java.util.List;` và `import java.util.ArrayList;` cho ví dụ này.

**Ghi nhớ:** `var` bỏ phần lặp lại của khai báo kiểu, nhưng không bỏ hệ thống kiểu tĩnh của Java. Hãy xác định **kiểu của toàn bộ biểu thức khởi tạo lúc biên dịch**; đó là cơ sở để hiểu kiểu, hành vi gán và các lời gọi hợp lệ của biến.

## Tài liệu tham khảo chính thức

- [Java Language Specification, §14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4.1).
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [OpenJDK FAQ về local-variable type inference](https://cr.openjdk.org/~briangoetz/jep-286/lvti-faq.html).
