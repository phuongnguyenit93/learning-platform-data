# Toàn cảnh tám kiểu nguyên thủy trong Java (Java 17+)

Java có **tám kiểu nguyên thủy** (*primitive types*): `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`. Chúng biểu diễn các giá trị cơ bản, khác với kiểu tham chiếu như `String`, mảng hoặc đối tượng. Nắm được miền giá trị, literal và cách các kiểu tương tác giúp tránh tràn số, mất chính xác và lỗi gán kiểu.

## 1. Bảng tổng quan

| Kiểu | Kích thước, miền giá trị | Ví dụ | Công dụng |
| --- | --- | --- | --- |
| `byte` | 8 bit, −128 đến 127 | `byte a = -5;` | Dữ liệu số nhỏ, byte nhị phân |
| `short` | 16 bit, −32.768 đến 32.767 | `short b = 32000;` | Tương thích định dạng cần số nguyên 16 bit |
| `int` | 32 bit, −2.147.483.648 đến 2.147.483.647 | `int c = 42;` | Số nguyên thông thường |
| `long` | 64 bit, −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | `long d = 9_000_000_000L;` | Số nguyên vượt miền `int` |
| `float` | 32 bit IEEE 754, khoảng 6–7 chữ số thập phân có nghĩa | `float e = 1.25F;` | Số thực cần ít dung lượng/độ chính xác hơn |
| `double` | 64 bit IEEE 754, khoảng 15–16 chữ số có nghĩa | `double f = 2.5;` | Số thực mặc định |
| `char` | 16 bit không dấu, 0–65.535 | `char g = 'A';` | Một **đơn vị mã UTF-16** |
| `boolean` | Hai giá trị `true`, `false` | `boolean h = true;` | Logic điều kiện |

Bốn kiểu `byte`, `short`, `int`, `long` là **số nguyên có dấu**. `char` là đơn vị mã 16 bit **không dấu**, không phải mọi ký tự Unicode đầy đủ đều gói được trong một `char`: ví dụ emoji ngoài BMP cần hai `char` khi mã hóa UTF-16.

`float` và `double` lưu giá trị **xấp xỉ**, hỗ trợ cả `NaN`, `Infinity` và `-0.0`. Riêng `boolean` **không** nhận số `0` hoặc `1` thay cho `false`/`true`. Java không quy định kích thước lưu trữ cố định của `boolean`; số bit trong bảng là độ rộng giá trị theo ngôn ngữ, **không phải cam kết số byte RAM cho mọi biến**.

## 2. Ví dụ Java 17+ có thể chạy ngay

Tạo tệp UTF-8 tên **`PrimitiveTypesDemo.java`**:

~~~java
public class PrimitiveTypesDemo {
    static int defaultNumber;       // Field int mac dinh 0.
    static boolean defaultFlag;     // Field boolean mac dinh false.
    static char defaultCharacter;   // Field char mac dinh ma 0.

    public static void main(String[] args) {
        byte smallest = -128;
        short tickets = 30_000;
        int population = 2_000_000_000;
        long distance = 9_000_000_000L;
        float rate = 1.25F;
        double price = 2.5D;
        char grade = 'A';
        boolean active = true;

        System.out.println("byte=" + smallest);
        System.out.println("short=" + tickets);
        System.out.println("int=" + population);
        System.out.println("long=" + distance);
        System.out.println("float=" + rate);
        System.out.println("double=" + price);
        System.out.println("char=" + grade + ", code=" + (int) grade);
        System.out.println("boolean=" + active);

        System.out.println("defaultInt=" + defaultNumber);
        System.out.println("defaultBoolean=" + defaultFlag);
        System.out.println("defaultCharCode=" + (int) defaultCharacter);

        int sum = smallest + tickets;
        System.out.println("promotedSum=" + sum);
        System.out.println("intDivision=" + (5 / 2));
        System.out.println("doubleDivision=" + (5 / 2.0));
        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("narrowByte=" + (byte) 130);
        System.out.println("decimalEqual=" + (0.1 + 0.2 == 0.3));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa tệp:

~~~bash
java -version
javac -version
javac -encoding UTF-8 PrimitiveTypesDemo.java
java PrimitiveTypesDemo
~~~

**Expected output:**

~~~text
byte=-128
short=30000
int=2000000000
long=9000000000
float=1.25
double=2.5
char=A, code=65
boolean=true
defaultInt=0
defaultBoolean=false
defaultCharCode=0
promotedSum=29872
intDivision=2
doubleDivision=2.5
overflow=-2147483648
narrowByte=-126
decimalEqual=false
~~~

Lý giải các dòng cần chú ý:

- `9_000_000_000L` có hậu tố `L` để mang kiểu `long`; `1.25F` có `F` để mang kiểu `float`; `2.5D` là `double`, và `D` có thể bỏ.
- `'A'` là `char`, ép sang `int` cho mã UTF-16 `65`. Ép kiểu `(int)` ở đây chỉ để hiển thị mã số.
- `smallest + tickets` được **nâng kiểu thành `int`**, tính `-128 + 30000 = 29872`.
- `5 / 2` chia số nguyên thành `2`; `5 / 2.0` chia số thực thành `2.5`.
- `Integer.MAX_VALUE + 1` tràn số nguyên `int` về `-2147483648`; ép `130` xuống `byte` cho `-126`.
- `0.1 + 0.2 == 0.3` là `false` vì số thực nhị phân không biểu diễn chính xác nhiều phân số thập phân.

## 3. Literal và phép chuyển kiểu

### Viết literal đúng kiểu

~~~java
int days = 7;                   // int
long distance = 5_000_000_000L; // long
float portion = 0.5F;           // float
double ratio = 0.5;             // double
char separator = ':';           // char
boolean valid = false;          // boolean
~~~

Literal nguyên thập phân như `7` mặc định có kiểu `int` (nếu nằm trong miền); literal số thực như `0.5` mặc định có kiểu `double`. Lỗi phổ biến:

~~~java
// float x = 0.5;         // Sai: double khong tu thu hep thanh float.
float x = 0.5F;
// long y = 5000000000;   // Sai: literal nguyen khong co L vuot mien int.
long y = 5_000_000_000L;
~~~

Java còn cho phép literal hệ 16, hệ 2, ví dụ `0xFF` và `0b1010`. Dấu gạch dưới như `1_000_000` giúp chia nhóm chữ số tại vị trí hợp lệ nhưng không làm thay đổi giá trị.

### Widening (mở rộng) và narrowing (thu hẹp)

Một số phép chuyển đổi số học thông dụng:

~~~text
byte → short → int → long → float → double
               ↑
             char
~~~

Chuyển `int` sang `long` thường không mất giá trị. Nhưng **mở rộng kiểu không luôn bảo toàn độ chính xác**: một số `long` lớn không được `float` hoặc `double` biểu diễn nguyên vẹn. Ngược lại, thu hẹp như `int` sang `byte` có thể thay đổi giá trị:

~~~java
int original = 130;
byte narrowed = (byte) original; // -126
~~~

Phép gán hằng số nguyên đặc biệt được phép khi nằm trong miền, ví dụ `byte b = 100;` dù literal `100` có kiểu `int`. Nhưng biến `int` nói chung không tự thu hẹp về `byte`:

~~~java
int n = 100;
// byte b = n; // Sai neu khong ep kieu.
byte b = (byte) n;
~~~

### Integer promotion trong biểu thức

Với toán tử số học thông thường, `byte`, `short` và `char` được nâng thành `int` trước phép tính:

~~~java
byte left = 10, right = 20;
int sum = left + right;        // Dung.
// byte sum2 = left + right;  // Loi bien dich: ket qua la int.
~~~

**Kiểu của biến ở vế trái không tự đổi kiểu của phép tính.** Vì vậy `double answer = 5 / 2;` cho `2.0`, không phải `2.5`.

## 4. Giá trị mặc định và lỗi chưa khởi tạo

**Field** của đối tượng/lớp nhận giá trị mặc định nếu chưa khởi tạo tường minh: số nguyên `0`, số thực `0.0`, `char` là mã 0, `boolean` là `false`. Đây là lý do ba static fields trong chương trình ví dụ có thể được đọc ngay.

**Biến cục bộ** thì khác:

~~~java
int count;
// System.out.println(count); // Loi bien dich: count chua duoc gan.
count = 3;
System.out.println(count); // 3
~~~

Java yêu cầu biến cục bộ được gán chắc chắn trước khi đọc; không có quy tắc mọi biến primitive tự nhận `0` khi vừa khai báo.

Không primitive nào nhận `null` trực tiếp:

~~~java
// int n = null;         // Sai.
// boolean b = null;     // Sai.
Integer boxed = null;    // Dung: Integer la kieu tham chieu.
~~~

Các lớp bao tương ứng như `Integer`, `Long`, `Double` và `Boolean` là **wrapper/reference types**, không phải tám primitive types. Khi unboxing wrapper đang null về primitive sẽ ném `NullPointerException` khi chạy.


## 5. Từ giá trị cần lưu đến kiểu nên chọn

Bảng tám kiểu phía trên giúp nhận diện khả năng biểu diễn; khi lập trình, còn cần xét **giá trị lớn nhất của kết quả trung gian** và **độ chính xác mong muốn**:

- Với số đếm, thường bắt đầu từ `int`; dùng `long` khi tổng/tích có thể vượt giới hạn `int`. Chuyển toán hạng sang `long` **trước phép tính**, vì biến nhận kiểu `long` không sửa được kết quả `int` đã tràn.
- Với đại lượng đo gần đúng, `double` thường phù hợp; `float` chỉ khi dữ liệu hoặc API yêu cầu 32 bit. Không dùng số thực nhị phân nếu phép tính thập phân phải chính xác tuyệt đối: khi cần, xét `BigDecimal` hoặc đơn vị nguyên nhỏ nhất.
- `byte`/`short` chủ yếu hữu ích khi định dạng dữ liệu yêu cầu đúng độ rộng; `boolean` dùng cho điều kiện; `char` dành cho **một code unit UTF-16**, còn văn bản tổng quát dùng `String`.

Đây chỉ là bản đồ định hướng. Các bài về số nguyên, dấu phẩy động, Unicode và lựa chọn kiểu sẽ lần lượt phân tích điều kiện, rủi ro và cách tự kiểm chứng bằng mã nguồn.

## 6. Bài tập tự kiểm tra

1. **Phân loại tám kiểu:** Kể tên bốn kiểu nguyên có dấu, hai kiểu số thực, kiểu ký tự và kiểu logic.  
   *Đáp án:* `byte`/`short`/`int`/`long`; `float`/`double`; `char`; `boolean`.
2. **Dự đoán:** `double x = 7 / 2;` và `double y = 7 / 2.0;` cho kết quả gì?  
   *Đáp án:* `x = 3.0`, `y = 3.5`.
3. **Giải thích:** Vì sao `float f = 0.25;` không hợp lệ nhưng `float f = 0.25F;` hợp lệ?  
   *Đáp án:* `0.25` là literal `double`; `F` tạo literal `float`.
4. **Tràn số:** Dự đoán `(byte) 130`.  
   *Đáp án:* `-126` do chuyển về giá trị 8 bit có dấu.
5. **Biến cục bộ:** Vì sao `int x; System.out.println(x);` trong phương thức không biên dịch, nhưng đọc một field `int` chưa khai báo initializer được?  
   *Đáp án:* Local variable không có giá trị mặc định; field có giá trị mặc định `0`.
6. **Unicode:** Có thể chứa trọn emoji ngoài BMP trong một `char` không?  
   *Đáp án:* Không; nó cần hai đơn vị mã UTF-16. Dùng `String` khi xử lý văn bản.

## Ghi nhớ

Java 17 có **đúng tám primitive types**. `int` và `double` thường là lựa chọn mặc định cho số nguyên và số thực; `boolean` không phải số; `char` là **một UTF-16 code unit**. Hãy kiểm tra miền giá trị, hậu tố literal, quy tắc nâng/ép kiểu, tràn số và sai số dấu phẩy động **trước khi** quyết định kiểu dữ liệu cho bài toán.
