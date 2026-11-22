# Hậu tố `L` và kiểu mặc định của literal số nguyên trong Java

## 1. Literal số nguyên có kiểu gì?

**Integer literal** là cách viết trực tiếp một giá trị số nguyên trong mã Java, ví dụ `10`, `1_000`, `0xFF` hay `42L`. Trong **Java 17+**, kiểu của literal số nguyên được xác định ngay khi compiler phân tích biểu thức, **không phải chờ xem biến bên trái có kiểu gì**.

Quy tắc quan trọng:

- **Không có hậu tố `L` hoặc `l`**: literal số nguyên có kiểu **`int`** (32 bit).
- **Có hậu tố `L` hoặc `l`**: literal số nguyên có kiểu **`long`** (64 bit).
- Nên viết **`L` hoa**: `1L`, `100_000L` thay vì `1l`, vì chữ `l` thường dễ nhầm với số `1`.
- Chọn kiểu **`long` cho biến nhận** không tự chuyển một literal quá lớn không có `L` thành literal `long`.

~~~java
int a = 42;              // Literal 42 có kiểu int
long b = 42;             // Hợp lệ: int được widening sang long
long c = 42L;            // Literal 42L có kiểu long
long d = 3_000_000_000L; // Hợp lệ: có L, vượt phạm vi int
// long bad = 3_000_000_000; // Lỗi compile: literal int quá lớn
~~~

Ở dòng `long b = 42;`, **bản thân `42` vẫn là literal `int`**. Sau đó Java cho phép chuyển mở rộng (*widening primitive conversion*) từ `int` sang `long` khi gán. Cần phân biệt **kiểu của literal** và **kiểu của biến**.

## 2. Phạm vi giá trị của int và long

| Kiểu | Kích thước | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|---:|
| `int` | 32 bit | −2.147.483.648 | 2.147.483.647 |
| `long` | 64 bit | −9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Các giá trị có thể truy cập bằng `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE` và `Long.MAX_VALUE`.

~~~java
int largestInt = 2_147_483_647;
long firstBeyondInt = 2_147_483_648L;
long largestLong = 9_223_372_036_854_775_807L;
~~~

**Tại sao dòng thứ hai cần `L`?** Vì `2_147_483_648` không có hậu tố bị phân tích như một decimal `int` literal, quá phạm vi của `int`, nên chương trình bị từ chối ở bước biên dịch. Biến đích có kiểu `long` không chữa được literal đã sai.

**`L` không làm `long` vô hạn.** Viết một giá trị dương lớn hơn `Long.MAX_VALUE`, kể cả có `L`, cũng bị compiler từ chối:

~~~java
// long tooBig = 9_223_372_036_854_775_808L; // Sai
~~~

Nếu thật sự cần số nguyên có độ lớn vượt `long`, hãy dùng `java.math.BigInteger` và khởi tạo từ chuỗi; không có hậu tố integer literal nào tự biến nó thành `BigInteger`.

## 3. Số âm và hai giá trị MIN_VALUE đặc biệt

Dấu `-` là **toán tử một ngôi** (*unary minus*), không phải ký tự thuộc một integer literal dương. Ví dụ `-5L` được hiểu là toán tử `-` áp dụng lên literal `5L`.

Java dành trường hợp đặc biệt cho giới hạn âm của `int` và `long` khi literal decimal tương ứng nằm ngay dưới toán tử unary minus:

~~~java
int minInt = -2147483648;                 // Hợp lệ
long minLong = -9223372036854775808L;    // Hợp lệ

// int invalid = 2147483648;            // Sai, literal int dương quá lớn
// long invalidLong = 9223372036854775808L; // Sai, literal long dương quá lớn
~~~

**Vì sao có sự bất đối xứng?** Miền số nguyên có dấu kiểu bù hai (*two's complement*) có một giá trị âm nhiều hơn số giá trị dương. Nhờ quy tắc về toán tử `-`, Java cho phép viết trực tiếp `Integer.MIN_VALUE` và `Long.MIN_VALUE`.

Không áp dụng ngoại lệ này cho phép cộng thông thường hoặc biến đích `long`. Ví dụ `long x = 2147483648;` vẫn là lỗi. Nếu chỉ cần giá trị nhỏ nhất, viết `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE` thường dễ đọc hơn.

## 4. Kiểu mặc định không chỉ áp dụng cho hệ thập phân

Integer literal Java có nhiều cách viết:

| Cách viết | Literal | Giá trị theo hệ 10 | Kiểu khi không có hậu tố |
|---|---|---:|---|
| Thập phân | `26` | 26 | `int` |
| Thập lục phân | `0x1A` hoặc `0X1A` | 26 | `int` |
| Nhị phân | `0b11010` hoặc `0B11010` | 26 | `int` |
| Bát phân | `032` | 26 | `int` |
| Thập phân có hậu tố | `26L` | 26 | `long` |
| Thập lục phân có hậu tố | `0x1AL` | 26 | `long` |

**Lưu ý số 0 đầu:** `010` là literal **bát phân**, mang giá trị **8**, không phải 10. Viết `08` là sai vì chữ số 8 không hợp lệ trong hệ bát phân.

### Khi literal khác hệ thập phân tràn phần dấu

Với literal **thập lục phân, nhị phân hoặc bát phân**, Java cho phép biểu diễn trực tiếp mẫu bit trong độ rộng `int` hoặc `long`. Mẫu bit có bit dấu bằng 1 được hiểu thành số âm theo biểu diễn bù hai.

~~~java
int intBits = 0xFFFF_FFFF;
long longBits = 0xFFFF_FFFFL;
long allLongBits = 0xFFFF_FFFF_FFFF_FFFFL;

System.out.println(intBits);      // -1
System.out.println(longBits);     // 4294967295
System.out.println(allLongBits);  // -1
~~~

**Điểm tinh tế:** cùng các chữ số `0xFFFF_FFFF`, literal không hậu tố là `int` 32 bit (giá trị `-1`), còn `0xFFFF_FFFFL` là `long` 64 bit (giá trị `4_294_967_295`). Vì độ rộng đã đổi, bit cao nhất của `long` này không phải bit dấu.

Không khái quát sai rằng “literal hex luôn dương” hoặc “chỉ decimal mới có thể âm”.

## 5. Dấu gạch dưới `_` giúp dễ đọc, không đổi kiểu

Java cho phép dùng dấu gạch dưới **giữa các chữ số** của nhiều dạng literal:

~~~java
int population = 1_000_000;
long distance = 12_345_678_901L;
int mask = 0b1010_1100;
long colorCode = 0xAB_CD_EFL;
~~~

`1_000_000` vẫn là `int`; `12_345_678_901L` vẫn là `long`. Gạch dưới không làm tăng giới hạn kiểu hoặc thay thế hậu tố `L`.

Ví dụ cú pháp **không hợp lệ**:

~~~java
// int a = _123;          // Đây là tên định danh _123, không phải số 123
// int b = 123_;          // Không đặt _ ở cuối literal
// int c = 0x_FF;         // Không đặt _ ngay sau tiền tố 0x
// long d = 123_L;        // Không đặt _ ngay trước hậu tố L
~~~

Để giữ mã dễ đọc, nhóm chữ số theo ý nghĩa (`1_000_000L`, `0xFF_00_00_00L`) thay vì đặt dấu `_` tùy ý.

## 6. Kiểu của biểu thức được quyết định trước khi gán

Đây là một trong những lỗi Java phổ biến nhất khi học hậu tố `L`.

~~~java
long wrong = 2_000_000_000 + 2_000_000_000;
long correct = 2_000_000_000L + 2_000_000_000;

System.out.println(wrong);   // -294967296
System.out.println(correct); // 4000000000
~~~

Vì cả hai toán hạng đầu tiên là literal `int`, biểu thức `int + int` được tính bằng **32 bit** và tràn trước khi chuyển sang `long`. Java vẫn cho phép gán kết quả `int` đã tràn sang `long`; nó **không tính lại phép cộng bằng 64 bit**.

Ở dòng `correct`, một toán hạng có hậu tố `L`, nên phép cộng dùng `long` do **binary numeric promotion**. Kết quả 4 tỷ nằm trong phạm vi `long`.

Hai cách đúng cho phép tính này:

~~~java
long bySuffix = 2_000_000_000L + 2_000_000_000;
long byCast = (long) 2_000_000_000 + 2_000_000_000;
~~~

**Vị trí ép kiểu quyết định kết quả:**

~~~java
long stillWrong = (long) (2_000_000_000 + 2_000_000_000);
// Đã tràn int bên trong ngoặc rồi mới chuyển sang long.
~~~

Với phép nhân, nguyên tắc tương tự:

~~~java
long wrongProduct = 1_500_000_000 * 3;
long rightProduct = 1_500_000_000L * 3;
// rightProduct = 4500000000; wrongProduct đã tràn int.
~~~

Khi xử lý số lượng lớn hoặc tiền bạc, đừng nghĩ “khai báo biến `long` là đủ”. Cần kiểm soát **kiểu của phép tính** ngay từ toán hạng.

## 7. Ví dụ Java 17 hoàn chỉnh và kết quả chạy

Tạo tệp **`IntegerLiteralDemo.java`** với nội dung:

~~~java
public final class IntegerLiteralDemo {
    private IntegerLiteralDemo() {}

    static String overload(int value) {
        return "int: " + value;
    }

    static String overload(long value) {
        return "long: " + value;
    }

    public static void main(String[] args) {
        int defaultInt = 42;
        long widened = 42;
        long explicitLong = 42L;
        long bigLong = 3_000_000_000L;

        int hexInt = 0xFFFF_FFFF;
        long hexLong = 0xFFFF_FFFFL;
        int octal = 017;
        int binary = 0b1010;

        long overflowBeforeWiden = 2_000_000_000 + 2_000_000_000;
        long promoteFirst = 2_000_000_000L + 2_000_000_000;
        long castFirst = (long) 2_000_000_000 + 2_000_000_000;

        int minInt = -2147483648;
        long minLong = -9223372036854775808L;

        byte small = 127; // int constant được thu hẹp hợp lệ
        var inferredInt = 7;
        var inferredLong = 7L;

        System.out.println("int default: " + defaultInt);
        System.out.println("widened into long: " + widened);
        System.out.println("explicit long: " + explicitLong);
        System.out.println("big long: " + bigLong);
        System.out.println("hex int: " + hexInt);
        System.out.println("hex long: " + hexLong);
        System.out.println("octal: " + octal);
        System.out.println("binary: " + binary);
        System.out.println("overflow before widen: " + overflowBeforeWiden);
        System.out.println("long before add: " + promoteFirst);
        System.out.println("cast before add: " + castFirst);
        System.out.println("minimum int: " + minInt);
        System.out.println("minimum long: " + minLong);
        System.out.println("byte from int literal: " + small);
        System.out.println(overload(inferredInt));
        System.out.println(overload(inferredLong));
    }
}
~~~

Mở terminal trong thư mục chứa file và dùng **JDK 17 hoặc mới hơn**.

**Bash (Linux/macOS):**

~~~bash
java -version
javac -version
javac --release 17 -encoding UTF-8 IntegerLiteralDemo.java
java -cp . IntegerLiteralDemo
~~~

**PowerShell (Windows):**

~~~powershell
java -version
javac -version
javac --release 17 -encoding UTF-8 .\IntegerLiteralDemo.java
java -cp . IntegerLiteralDemo
~~~

**Kết quả dự kiến:**

~~~text
int default: 42
widened into long: 42
explicit long: 42
big long: 3000000000
hex int: -1
hex long: 4294967295
octal: 15
binary: 10
overflow before widen: -294967296
long before add: 4000000000
cast before add: 4000000000
minimum int: -2147483648
minimum long: -9223372036854775808
byte from int literal: 127
int: 7
long: 7
~~~

Ba điểm nên tự kiểm chứng:

1. `42` và `42L` có thể in **cùng một giá trị**, nhưng mang **kiểu khác nhau**.
2. `0xFFFF_FFFF` khác `0xFFFF_FFFFL` do độ rộng `int`/ `long`.
3. Hai overload `overload(int)` và `overload(long)` cho thấy `var inferredInt = 7` có kiểu `int`, còn `var inferredLong = 7L` có kiểu `long`.

Ví dụ được thiết kế có thể chạy độc lập; đầu ra trên là **kỳ vọng cần đối chiếu sau khi tự chạy**, không phải một khẳng định đã thực thi chương trình trên máy của bạn.

## 8. Vì sao byte hoặc short có thể nhận literal không có hậu tố?

Dù integer literal không hậu tố có kiểu `int`, compiler cho phép **narrowing conversion đặc biệt của biểu thức hằng** trong một số ngữ cảnh gán/khởi tạo, nếu giá trị nằm trong phạm vi kiểu đích:

~~~java
byte a = 127;      // Hợp lệ dù 127 là int literal
short b = 30_000;  // Hợp lệ dù 30000 là int literal
char c = 65;       // Hợp lệ: ký tự 'A'

// byte invalid = 128;       // Lỗi: ngoài phạm vi byte
// short invalid2 = 40_000;  // Lỗi: ngoài phạm vi short
// byte invalid3 = 127L;     // Lỗi: không tự thu hẹp long literal như vậy
~~~

Điều này **không thay đổi kiểu mặc định của literal**: `127` vẫn là `int`. Quy tắc chuyển kiểu khi gán giải thích vì sao đoạn đầu hợp lệ.

Với biến hoặc biểu thức không phải hằng thích hợp, compiler không nhất thiết cho phép thu hẹp:

~~~java
int source = 127;
// byte target = source; // Lỗi vì source là int variable
byte target = (byte) source; // Ép kiểu tường minh; chỉ dùng khi đã kiểm tra miền
~~~

Không dùng cast để “che” một giá trị ngoài phạm vi: cast số nguyên quá lớn xuống kiểu nhỏ có thể cắt bớt bit và làm sai dữ liệu.

## 9. Các lỗi thường gặp và cách sửa đúng

| Tình huống | Vì sao sai hoặc bất ngờ? | Cách sửa |
|---|---|---|
| `long n = 3_000_000_000;` | Decimal int literal quá lớn dù biến đích là long | `3_000_000_000L` |
| `int n = 3_000_000_000L;` | Long literal không tự thu hẹp thành int | Chọn `long` nếu dữ liệu thực sự lớn |
| `long sum = 2_000_000_000 + 2_000_000_000;` | Phép cộng int tràn trước khi gán | Dùng `L` ở một toán hạng, hoặc cast trước phép tính |
| `long n = 9223372036854775808L;` | Vượt `Long.MAX_VALUE` | Chọn miền dữ liệu hợp lệ hoặc `BigInteger` |
| `int n = 08;` | `0` đầu mở đầu cách viết bát phân | Viết `8` cho hệ thập phân |
| `long n = 0xFFFF_FFFF;` | Literal int có bit dấu 1, thành `-1` trước khi mở rộng | `0xFFFF_FFFFL` nếu muốn 4.294.967.295 |
| `int n = 123_L;` | Dấu `_` không được ngay trước hậu tố | `123L` hoặc `1_23L` |
| Dùng `1l` | Hợp lệ nhưng dễ đọc nhầm `l` và `1` | Dùng `1L` |
| `var value = 1;` rồi mong long | `var` suy ra int từ initializer | `var value = 1L;` |

**Phân biệt hai giai đoạn:** một literal nằm ngoài phạm vi hợp lệ thường gây **lỗi biên dịch**; nhưng phép toán trên các literal `int` hợp lệ vẫn có thể **tràn lúc đánh giá** mà không tự ném exception. Với phép cộng hoặc nhân cần phát hiện tràn, xem `Math.addExact` và `Math.multiplyExact` theo yêu cầu dữ liệu.

## 10. Bài tập thực hành kèm đáp án

### Bài A — xác định kiểu và giá trị

Phân loại `100`, `100L`, `0b1010`, `0xFFL`, `010`.

**Đáp án:** `100` là int 100; `100L` là long 100; `0b1010` là int 10; `0xFFL` là long 255; `010` là int 8 (hệ bát phân).

### Bài B — lỗi dù đích là long

~~~java
long population = 4_000_000_000;
~~~

**Đáp án:** lỗi compile vì literal `4_000_000_000` không có hậu tố và vượt miền `int`. Sửa thành `long population = 4_000_000_000L;`.

### Bài C — dự đoán phép nhân

~~~java
long x = 1_500_000_000 * 3;
long y = 1_500_000_000L * 3;
~~~

**Đáp án:** `x = 205032704` (phép nhân int 4.500.000.000 bị tràn theo modulo 2³², sau đó mở rộng sang long); `y = 4500000000`. Nếu phép tính cần đúng 4,5 tỷ, phải làm phép nhân bằng `long` trước.

### Bài D — phân biệt cùng mẫu hex

~~~java
int a = 0xFFFF_FFFF;
long b = 0xFFFF_FFFFL;
~~~

**Đáp án:** `a == -1`, `b == 4294967295L`. Cùng các chữ số hex nhưng khác **độ rộng và bit dấu** của kiểu literal.

### Bài E — sửa ba dòng không hợp lệ

~~~java
// long a = 2147483648;
// int b = 2147483648L;
// long c = 9223372036854775808L;
~~~

**Đáp án gợi ý:** với `a`, thêm `L`. Với `b`, đổi biến sang `long` nếu cần giá trị đó. Với `c`, số vượt miền `long`, nên phải thay đổi yêu cầu dữ liệu, dùng `BigInteger` hoặc xử lý đầu vào ngoài phạm vi — **không có hậu tố số nguyên lớn hơn `L` trong Java**.

## 11. Checklist và kết luận

- [ ] Hiểu literal số nguyên **không `L` có kiểu `int`**, có `L` có kiểu `long`.
- [ ] Không nhầm kiểu của literal với kiểu biến bên trái phép gán.
- [ ] Nhớ giới hạn `int` 32 bit và `long` 64 bit.
- [ ] Biết cách viết `Integer.MIN_VALUE` và `Long.MIN_VALUE` bằng toán tử âm với literal tương ứng.
- [ ] Nhận ra decimal, hex, binary, octal và ảnh hưởng của bit dấu.
- [ ] Dùng `L` hoa; dùng `_` giữa chữ số chỉ để dễ đọc.
- [ ] Biết phép cộng/nhân `int` có thể tràn **trước khi gán sang long**.
- [ ] Hiểu `var x = 1` suy ra int, còn `var x = 1L` suy ra long.
- [ ] Không nhầm quy tắc thu hẹp hằng `byte b = 127;` với kiểu literal byte.
- [ ] Biên dịch và chạy `IntegerLiteralDemo.java`, đối chiếu toàn bộ output.

**Kết luận:** Trong Java, hậu tố **`L` quyết định literal số nguyên có kiểu `long` thay vì `int`**. Kiểu được xác định **trước** khi áp dụng phép gán hoặc phép toán. Viết `L` đúng chỗ không chỉ giúp biểu diễn các số vượt `int`, mà còn đảm bảo những biểu thức cần độ rộng 64 bit được tính bằng `long` thay vì tràn `int` rồi mới được chuyển kiểu.