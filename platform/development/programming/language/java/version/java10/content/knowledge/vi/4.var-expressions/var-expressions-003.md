# Khác biệt giữa suy luận `var` và phép thu hẹp hằng số khi gán trong Java

## Mục tiêu bài học

Khi học Java 10+ và khai báo biến bằng `var`, một câu hỏi dễ gây nhầm lẫn là: vì sao `byte a = 100;` biên dịch được nhưng `var a = 100;` lại tạo ra biến kiểu `int`, không phải `byte`? Cả hai đều được trình biên dịch xử lý trước lúc chương trình chạy, nhưng **đó là hai quy tắc khác nhau**.

Sau bài học, bạn có thể:
- Xác định kiểu của biến khi dùng `var` và literal số nguyên.
- Giải thích khi nào Java cho phép tự động thu hẹp *biểu thức hằng* trong ngữ cảnh gán.
- Phân biệt `var`, kiểu đích tường minh, ép kiểu `(byte)` và việc dùng `final`.
- Nhận biết lỗi khi giá trị vượt phạm vi, khi biểu thức không còn là hằng hoặc khi biểu thức có kiểu `long`.

> Các quy tắc dưới đây vẫn áp dụng trong Java hiện đại. Ví dụ chạy độc lập với JDK 17 trở lên; `var` cho biến cục bộ được hỗ trợ từ Java 10.

## 1. Hai khai báo trông gần giống nhưng có kiểu khác nhau

~~~java
byte small = 100;       // small có kiểu byte
var number = 100;       // number có kiểu int
var another = (byte) 100; // another có kiểu byte
~~~

**`byte small = 100;` — chuyển đổi trong ngữ cảnh gán.** Bên trái đã chỉ rõ kiểu đích là `byte`. Bên phải `100` là một *integer literal* kiểu `int`, nhưng cũng là biểu thức hằng biết trước giá trị lúc biên dịch. Vì 100 nằm trong phạm vi của `byte`, Java cho phép chuyển đổi thu hẹp đặc biệt từ `int` sang `byte` mà không cần viết `(byte)`.

**`var number = 100;` — suy luận kiểu của biến cục bộ.** Bên trái chưa đưa ra kiểu đích `byte`. Trình biên dịch xác định kiểu của biểu thức khởi tạo `100` là `int` và suy luận `number` cũng có kiểu **`int`**. Java **không chọn kiểu nguyên thủy nhỏ nhất đủ chứa giá trị**.

**`var another = (byte) 100;` — suy luận từ biểu thức đã ép kiểu.** Biểu thức `(byte) 100` có kiểu `byte`, vì vậy `another` được suy luận là `byte`. Ở đây kiểu `byte` đến từ phép ép kiểu viết rõ trong biểu thức khởi tạo, không phải do `var` tự thu hẹp `100`.

Quy tắc quan trọng: **Giá trị có vừa `byte` hay không không tự quyết định kiểu của `var`**. Kiểu tĩnh của biểu thức khởi tạo mới quyết định kiểu suy luận.

## 2. Phép thu hẹp hằng số trong ngữ cảnh gán là gì?

Theo quy tắc *assignment contexts* của Java Language Specification (JLS §5.2), một biểu thức hằng có kiểu `byte`, `short`, `char` hoặc `int` có thể được chuyển đổi thu hẹp sang **`byte`, `short` hoặc `char`** khi giá trị của nó biểu diễn được trong kiểu đích.

Các giới hạn thường cần nhớ:

| Kiểu đích | Phạm vi giá trị |
| --- | --- |
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `char` | 0 đến 65.535, biểu diễn một đơn vị mã UTF-16 |

Ví dụ sau đều hợp lệ:

~~~java
byte a = 127;             // 127 là hằng int và nằm trong phạm vi byte
byte b = 40 + 2;          // 40 + 2 là biểu thức hằng int có giá trị 42
short c = 20_000 + 100;   // Biểu thức hằng int có giá trị 20_100
char letter = 65;         // Ký tự 'A' có mã UTF-16 là 65
~~~

Điểm đặc biệt: `40 + 2` thường có **kiểu biểu thức `int`**; nhờ kiểu đích `byte` và giá trị hằng phù hợp, khai báo `byte b = 40 + 2;` mới được chấp nhận. Đừng diễn giải rằng phép cộng nguyên trong Java tự tạo ra `byte`.

**Không phải mọi số nhỏ đều được tự động thu hẹp.** Những khai báo sau là **lỗi biên dịch có chủ ý**:

~~~java
// byte tooLarge = 128;  // 128 vượt giá trị lớn nhất của byte
// short tooLarge = 32768;
// char negative = -1;    // char không chứa giá trị âm
// byte fromLong = 100L;  // 100L có kiểu long, không thuộc quy tắc thu hẹp hằng số này
~~~

Dù giá trị của `100L` có thể chứa trong một `byte`, quy tắc đặc biệt ở §5.2 không cho phép gán thẳng *hằng kiểu `long`* cho `byte` theo cách ấy.

## 3. Vì sao `var` không thực hiện thu hẹp hằng số?

Khi khai báo một biến cục bộ bằng `var`, JLS §14.4.1 chỉ dẫn xét biểu thức khởi tạo **như một biểu thức độc lập, không có ngữ cảnh gán tới kiểu đích được khai báo**. Bởi vậy không có kiểu đích `byte` để kích hoạt quy tắc thu hẹp hằng số của §5.2.

So sánh:

| Khai báo | Kết quả | Lý do |
| --- | --- | --- |
| `byte x = 100;` | Hợp lệ, `x: byte` | Có kiểu đích `byte`; hằng `int` nằm trong miền giá trị |
| `var x = 100;` | Hợp lệ, `x: int` | Literal `100` có kiểu `int` |
| `var x = (byte) 100;` | Hợp lệ, `x: byte` | Biểu thức ép kiểu có kiểu `byte` |
| `short x = 10 + 20;` | Hợp lệ, `x: short` | Biểu thức hằng `int` có giá trị 30 |
| `var x = 10 + 20;` | Hợp lệ, `x: int` | Kết quả của biểu thức cộng có kiểu `int` |
| `char x = 65;` | Hợp lệ, `x: char` | Hằng `int` 65 vừa kiểu `char` |
| `var x = 65;` | Hợp lệ, `x: int` | `var` suy luận từ literal `int` |
| `var x = 'A';` | Hợp lệ, `x: char` | Literal ký tự `'A'` đã có kiểu `char` |
| `var x = 100L;` | Hợp lệ, `x: long` | Hậu tố `L` cho kiểu `long` |
| `var x = 1.0;` | Hợp lệ, `x: double` | Literal dấu phẩy động mặc định `double` |

Trong từng dòng của bảng, hãy hiểu đây là **các khai báo độc lập**; nếu chép cùng khối thì cần đổi tên `x` để tránh khai báo trùng.

## 4. Chương trình minh họa có thể biên dịch và chạy trên Java 17+

Lưu vào tệp **VarAndConstantNarrowingDemo.java**:

~~~java
public class VarAndConstantNarrowingDemo {
    static String typeOf(byte value) {
        return "byte";
    }

    static String typeOf(int value) {
        return "int";
    }

    public static void main(String[] args) {
        byte explicitByte = 100;
        short explicitShort = 40 + 2;
        char letter = 65;

        var inferredInt = 100;
        var inferredByte = (byte) 100;
        var inferredFromByte = explicitByte;
        var promoted = explicitByte + 1;

        final int LIMIT = 120;
        byte fromConstant = LIMIT;
        Byte boxed = 42;

        System.out.println("byte explicit: " + typeOf(explicitByte));
        System.out.println("var literal: " + typeOf(inferredInt));
        System.out.println("var cast: " + typeOf(inferredByte));
        System.out.println("var from byte: " + typeOf(inferredFromByte));
        System.out.println("var byte + 1: " + typeOf(promoted));
        System.out.println("short value: " + explicitShort);
        System.out.println("char value: " + letter);
        System.out.println("from constant: " + fromConstant);
        System.out.println("boxed value: " + boxed);
    }
}
~~~

Mở terminal tại thư mục chứa tệp rồi chạy:

~~~bash
javac VarAndConstantNarrowingDemo.java
java VarAndConstantNarrowingDemo
~~~

Kết quả chuẩn:

~~~text
byte explicit: byte
var literal: int
var cast: byte
var from byte: byte
var byte + 1: int
short value: 42
char value: A
from constant: 120
boxed value: 42
~~~

**Điểm quan sát:**

- Hai phương thức `typeOf(byte)` và `typeOf(int)` minh họa lựa chọn overload dựa trên **kiểu tĩnh lúc biên dịch**. Kết quả `var literal: int` cho thấy trình biên dịch không suy luận `byte` từ giá trị 100.
- `var inferredFromByte = explicitByte;` có kiểu `byte` vì biểu thức khởi tạo là một biến `byte`. Không phải cứ dùng `var` là suy ra `int`.
- `explicitByte + 1` có kiểu `int` do quy tắc *binary numeric promotion* của phép toán số nguyên; vì vậy `promoted` là `int`.
- `final int LIMIT = 120;` là biến hằng kiểu nguyên thủy được khởi tạo bằng biểu thức hằng; `byte fromConstant = LIMIT;` hợp lệ vì giá trị được biết lúc biên dịch và nằm trong miền `byte`.
- `Byte boxed = 42;` hợp lệ nhờ trường hợp đặc biệt trong ngữ cảnh gán: từ hằng `int` 42, Java cho phép thu hẹp sang `byte` rồi boxing sang `Byte`. Đừng nhầm cơ chế này với việc `var` tự suy ra `Byte`.

Các ví dụ này chỉ dựa vào khả năng của ngôn ngữ Java vẫn còn dùng trong JDK hiện hành; không cần thư viện ngoài.

## 5. Khi giá trị nằm trong miền `byte` nhưng vẫn không gán trực tiếp được

Phép thu hẹp hằng số **không phụ thuộc đơn thuần vào giá trị thực tế lúc chạy**, mà phụ thuộc việc biểu thức phía phải có phải biểu thức hằng hợp lệ hay không.

### 5.1. Biến `int` thông thường không phải biểu thức hằng

~~~java
int ordinary = 100;
// byte a = ordinary;  // Lỗi biên dịch: int -> byte cần phép chuyển đổi phù hợp

var inferred = 100;
// byte b = inferred;  // Lỗi tương tự: inferred có kiểu int

byte c = (byte) ordinary; // Hợp lệ: có ép kiểu tường minh
~~~

Dù cả `ordinary` và `inferred` đang chứa 100, chúng đều là biến `int` thông thường. Java không lấy thông tin *giá trị hiện tại* của chúng để tự thu hẹp khi gán sang `byte`.

### 5.2. `final` chỉ giúp nếu thỏa định nghĩa biến hằng

~~~java
final int LIMIT = 127; // Biến hằng: final, primitive, initializer là biểu thức hằng
byte a = LIMIT;        // Hợp lệ

final int computed = 60 + 10;
byte b = computed;     // Hợp lệ, vì 60 + 10 là biểu thức hằng

final int runtime = Integer.parseInt("100");
// byte c = runtime;   // Lỗi: initializer gọi phương thức, không phải biểu thức hằng
~~~

Một biến `final` không thể gán lại sau khi đã khởi tạo, nhưng **không phải mọi biến `final` đều là biến hằng theo ngôn ngữ Java**. Khi giá trị cần được tính bằng một lời gọi phương thức lúc chạy, compiler không áp dụng cùng ngoại lệ thu hẹp hằng số.

Tương tự, `final var k = 100;` vẫn suy luận `k` là `int`; từ khóa `final` không làm `var` chọn kiểu hẹp hơn.

### 5.3. Biểu thức không phải hằng: `byte` với phép cộng

~~~java
byte a = 10;
byte b = 20;

// byte sum = a + b;   // Lỗi: a + b có kiểu int và không phải hằng compile-time
var sum = a + b;       // Hợp lệ: sum có kiểu int
byte narrowed = (byte) (a + b);
~~~

Kể cả khi hai biến `a`, `b` có kiểu `byte`, phép cộng số nguyên thường đưa toán hạng lên `int`. `var sum` phản ánh đúng kiểu kết quả của biểu thức cộng.

Nếu bắt buộc lưu kết quả vào `byte`, hãy kiểm tra điều kiện miền giá trị. Ép kiểu rõ ràng có thể mất dữ liệu: `(byte) 128` tạo ra `-128`, trong khi `byte x = 128;` báo lỗi biên dịch. Lựa chọn an toàn khi tính toán là dùng `int` cho kết quả và chỉ chuyển sang `byte` sau khi xác nhận kết quả nằm trong `[-128, 127]`.

## 6. Thu hẹp hằng số trong phép gán không đồng nghĩa với mọi chỗ dùng số hằng

Ngữ cảnh gán cho biến và ngữ cảnh truyền đối số vào phương thức tuân theo các quy tắc chuyển đổi khác nhau.

Ví dụ sau **minh họa lỗi biên dịch**:

~~~java
static void acceptByte(byte value) {
    System.out.println(value);
}

// acceptByte(100); // Lỗi: truyền int literal vào tham số byte không tự thu hẹp
~~~

Với phương thức trên, cách gọi hợp lệ là:

~~~java
acceptByte((byte) 100);
byte value = 100;
acceptByte(value);
~~~

Hai đoạn này là **mã minh họa đặt trong lớp và phương thức phù hợp**, không phải một chương trình độc lập. Tương tự, phép gán vào một biến có kiểu đích tường minh không nên được suy diễn thành quy tắc cho tất cả biểu thức hoặc tất cả lời gọi phương thức.

Ngoài ra, toán tử gán kết hợp (ví dụ `byte x = 1; x += 1;`) có quy tắc chuyển đổi riêng. Nó không chứng minh rằng phép gán thông thường `x = x + 1` sẽ hợp lệ; trong trường hợp này `x + 1` là `int`. Khi giải thích suy luận `var`, hãy xét **kiểu của biểu thức khởi tạo**, không trộn với ngoại lệ của gán kết hợp.

## 7. Nên chọn `var` hay kiểu tường minh?

**Nên viết rõ `byte`, `short`, `char` khi kiểu lưu trữ là một phần yêu cầu**, ví dụ giao thức nhị phân, hợp đồng dữ liệu hoặc API xác định kiểu cụ thể:

~~~java
byte protocolCode = 100;
short packetCount = 250;
char initial = 'A';
~~~

**Có thể dùng `var` khi kiểu biểu thức rõ ràng** và bạn thực sự muốn giữ kiểu của nó:

~~~java
var code = 100;             // int
var longCode = 100L;        // long
var byteCode = (byte) 100;  // byte
~~~

Đừng chọn `var` chỉ vì số hiện tại nhỏ, rồi mặc định nó tiết kiệm bộ nhớ như `byte`. Mục đích của `var` là giảm việc ghi lặp tên kiểu, **không phải tối ưu kích cỡ kiểu số**. Với biểu thức số học, đặc biệt là literal và toán tử `+`, `-`, `*`, hãy biết quy tắc xác định kiểu của biểu thức.

Cũng đừng dùng phép ép kiểu để che việc giá trị có thể tràn miền. Nếu dữ liệu cần `byte` nhưng đầu vào có thể vượt phạm vi, hãy kiểm tra miền trước, sau đó mới ép kiểu theo chủ đích.

## 8. Câu hỏi tự kiểm tra

Đọc từng dòng như một khai báo độc lập, xác định kiểu/kết quả hoặc lỗi biên dịch:

~~~java
byte a = 10 + 20;
var b = 10 + 20;
var c = (short) 10;
short d = 32767;
// short e = 32768;
int f = 12;
// byte g = f;
final int h = 12;
byte i = h;
// byte j = 12L;
var k = 12L;
~~~

**Đáp án:**

1. `a` là `byte`, vì `10 + 20` là biểu thức hằng `int` có giá trị 30 và vừa `byte`.
2. `b` là `int`, vì kết quả của phép cộng hai literal `int` có kiểu `int`.
3. `c` là `short`, do biểu thức khởi tạo có ép kiểu `(short)`.
4. `d` là `short`; `e` lỗi vì 32.768 vượt `short`.
5. `f` là `int`; `g` lỗi vì `f` không phải biểu thức hằng.
6. `h` là biến hằng `int`; `i` là `byte`, khai báo được vì 12 vừa miền `byte`.
7. `j` lỗi vì `12L` có kiểu `long`; `k` có kiểu `long`.

## 9. Ghi nhớ và tài liệu chuẩn

- **`var`**: xác định kiểu của biến từ **kiểu biểu thức khởi tạo**, với biểu thức được xét độc lập, không lấy kiểu nhỏ nhất chứa được giá trị.
- **Thu hẹp hằng số khi gán**: cần **kiểu đích rõ ràng**, một biểu thức hằng thuộc kiểu được phép và giá trị nằm trong phạm vi kiểu đích.
- **Ép kiểu `(byte)`, `(short)`, `(char)`**: làm đổi kiểu của biểu thức một cách tường minh, có thể mất dữ liệu nếu giá trị vượt miền.
- **`final`**: không làm kiểu suy luận của `var` tự thu hẹp; chỉ các biến `final` thỏa định nghĩa *constant variable* mới tham gia biểu thức hằng theo quy tắc ngôn ngữ.

Tham khảo:
- [JLS §14.4.1 — Local Variable Declarators and Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4.1): kiểu của biến cục bộ khai báo với `var`.
- [JLS §5.2 — Assignment Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.2): điều kiện thu hẹp biểu thức hằng khi gán.
- [JLS §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): định nghĩa biến hằng.
- [JLS §15.29 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29): những biểu thức được tính là hằng tại thời điểm biên dịch.

**Kết luận:** `byte x = 100;` và `var x = 100;` khác nhau vì dòng thứ nhất có **kiểu đích `byte`** cho quy tắc thu hẹp hằng số, còn dòng thứ hai suy luận trực tiếp **kiểu `int` của biểu thức `100`**. Cả hai đều an toàn kiểu tĩnh và vẫn là quy tắc của Java hiện đại.
