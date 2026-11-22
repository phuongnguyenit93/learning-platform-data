# Literal số nguyên và kiểu `int` mặc định trong Java

**Literal số nguyên** (*integer literal*) là số nguyên được viết trực tiếp trong mã nguồn Java: `42`, `0b101010`, `052`, `0x2A`. Các cách viết này có cơ số khác nhau nhưng cùng biểu diễn giá trị thập phân 42. **Theo mặc định literal số nguyên không có hậu tố `L` có kiểu `int`; có hậu tố `L` (hoặc `l`) thì có kiểu `long`.** Cơ số không quyết định kiểu. Phạm vi và ý nghĩa của literal thập phân và phi thập phân có vài điểm khác nhau mà người học cần nắm vững.

Bài học nói về *literal và kiểu của biểu thức lúc biên dịch*, không phải *giá trị mặc định của field* hay *phân tích chuỗi số lúc chạy*.

## 1. Bốn hệ cơ số của literal số nguyên

| Dạng | Ký hiệu đầu | Chữ số hợp lệ | Ví dụ | Giá trị thập phân |
| --- | --- | --- | --- | --- |
| Decimal (thập phân, cơ số 10) | Không có tiền tố đặc biệt; số thông thường | `0` đến `9` | `42` | 42 |
| Binary (nhị phân, cơ số 2) | `0b` hoặc `0B` | `0`, `1` | `0b101010` | 42 |
| Octal (bát phân, cơ số 8) | Số `0` ở đầu một literal có nhiều chữ số | `0` đến `7` | `052` | 42 |
| Hexadecimal (thập lục phân, cơ số 16) | `0x` hoặc `0X` | `0`–`9` và `A`–`F` (không phân biệt hoa/thường) | `0x2A` | 42 |

```java
int decimal = 42;      // 42
int binary = 0b101010; // 32 + 8 + 2 = 42
int octal = 052;       // 5 * 8 + 2 = 42
int hex = 0x2A;        // 2 * 16 + 10 = 42
```

Đây là **đoạn minh họa phép gán**, không phải một class độc lập. Sau khi biên dịch, các biến đều có giá trị nguyên 42. Chương trình không giữ lại “cơ số đã gõ” trong giá trị `int`. Vì vậy `System.out.println(0x2A)` sẽ in `42` theo mặc định, không tự in `0x2A`.

Cơ số 2 hữu ích khi nhìn mặt nạ bit, cơ số 16 giúp nhóm bit cho byte và cờ trạng thái; cơ số 10 thuận tiện cho số lượng thông thường. Cơ số 8 ít dùng hơn vì `0` đứng đầu dễ tạo bẫy.

## 2. Kiểu `int` mặc định và hậu tố `L` cho `long`

Cả bốn cách viết `7`, `0b111`, `07`, `0x7` đều có **kiểu `int`**. Thêm `L` vào cuối tạo literal **kiểu `long`**: `7L`, `0b111L`, `07L`, `0x7L`.

| Literal | Kiểu | Giá trị |
| --- | --- | --- |
| `100`, `0b1100100`, `0144`, `0x64` | `int` | 100 |
| `100L`, `0b1100100L`, `0144L`, `0x64L` | `long` | 100 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4294967295 |

`l` chữ thường cũng hợp lệ, nhưng nên dùng **`L` hoa** để tránh nhầm với `1`.

Một literal `int` có thể được *mở rộng* để gán vào `long` khi giá trị của nó hợp lệ:

```java
long a = 100;              // literal int rồi mở rộng thành long
long b = 100L;             // literal long ngay từ đầu
long c = 2_147_483_648L;   // cần hậu tố L vì lớn hơn int tối đa
// long bad = 2_147_483_648; // lỗi biên dịch: literal decimal int quá lớn
```

**Kiểu của biến đích không thay đổi quá trình phân tích literal.** `long bad = 3000000000;` không hợp lệ, dù biến `bad` có kiểu `long`. Phải viết `3_000_000_000L`. Hậu tố `L` thuộc chính literal, không tự áp dụng cho một phép cộng hay phép nhân đã thực hiện trước đó.

Một cách chứng minh kiểu literal là dùng method overload:

```java
static String category(int value) {
    return "int";
}
static String category(long value) {
    return "long";
}
// category(42)  -> "int"
// category(42L) -> "long"
```

Hai method là **đoạn khai báo bên trong class**, không độc lập. `42` chọn overload `int`; `42L` chọn overload `long`.

## 3. Phạm vi của literal thập phân và dấu âm đơn ngôi

Primitive `int` có phạm vi `-2_147_483_648` đến `2_147_483_647`; primitive `long` có phạm vi `-9_223_372_036_854_775_808L` đến `9_223_372_036_854_775_807L`.

Literal **thập phân** không hậu tố thông thường nhận các trị từ `0` đến `2_147_483_647`. Java dành ngoại lệ cho token `2147483648` khi nó là toán hạng của phép âm đơn ngôi `-`, để cho phép viết `-2147483648`, tức `Integer.MIN_VALUE`. Ngoại lệ tương tự cho `9223372036854775808L` trong `-9223372036854775808L`.

```java
int max = 2_147_483_647;
int min = -2_147_483_648;
long maxLong = 9_223_372_036_854_775_807L;
long minLong = -9_223_372_036_854_775_808L;

// int badInt = 2_147_483_648;  // lỗi nếu không là toán hạng của dấu âm
// long badLong = 9_223_372_036_854_775_808L; // lỗi nếu không là toán hạng của dấu âm
```

Về cú pháp, `-42` gồm **toán tử `-`** và **literal `42`**, chứ dấu âm không nằm trong token literal. Đây là lý do trường hợp tối thiểu của kiểu nguyên cần một ngoại lệ ngôn ngữ. Nếu mục tiêu là ghi rõ giới hạn, có thể dùng `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE` và `Long.MAX_VALUE`.

## 4. Literal hex/nhị phân được diễn giải như mẫu bit có dấu

Các literal phi thập phân (nhị phân, bát phân, hex) thể hiện **mẫu bit**. Literal không `L` phải vừa trong độ rộng 32 bit cho `int`; có `L` là độ rộng 64 bit cho `long`. Khi bit dấu bật, diễn giải bù hai (*two's complement*) cho một giá trị âm.

| Literal | Kiểu | Giá trị |
| --- | --- | --- |
| `0x7FFF_FFFF` | `int` | 2147483647 |
| `0x8000_0000` | `int` | -2147483648 |
| `0xFFFF_FFFF` | `int` | -1 |
| `0b11111111_11111111_11111111_11111111` | `int` | -1 |
| `0xFFFF_FFFFL` | `long` | 4294967295 |
| `0x1_0000_0000L` | `long` | 4294967296 |

Ví dụ:

```java
int allBitsOne = 0xFFFF_FFFF;   // -1: cả 32 bit bằng 1
int signBit = 0x8000_0000;     // -2147483648
long positive = 0xFFFF_FFFFL;  // 4294967295 (trong 64 bit)
// int invalid = 0x1_0000_0000; // lỗi: cần 33 bit
```

**Đừng coi `0xFFFF_FFFF` là một số `int` dương bằng 4294967295.** Nó là mẫu bit 32 bit có dấu nên có giá trị `-1`. Nếu cần dùng giá trị dương tương ứng, thêm `L` vào literal trước khi tính.

Một trường hợp khác: `-0x8000_0000` vẫn bằng `-2147483648` khi biểu thức mang kiểu `int`, do phép đổi dấu giá trị nhỏ nhất của `int` tràn và quay lại chính nó. Viết `0x8000_0000L` nếu muốn giá trị dương 2147483648L.

## 5. Tách chữ số bằng gạch dưới

Từ Java 7, có thể đặt `_` **giữa các chữ số** của literal số nguyên để đọc dễ hơn. Gạch dưới không thay đổi giá trị, cơ số hay kiểu.

```java
int count = 1_000_000;
int bits = 0b1010_1100;
int rgb = 0x00FF_80A0;
long distance = 9_000_000_000L;
```

Các ví dụ dưới đây là **minh họa lỗi biên dịch khi bỏ dấu chú thích**:

```java
// int a = _100;   // '_' không đứng trước chữ số đầu
// int b = 100_;   // '_' không đứng sau chữ số cuối
// int c = 0x_FF;  // '_' không đứng sát tiền tố 0x
// int d = 0b_101; // '_' không đứng sát tiền tố 0b
// long e = 123_L; // '_' không đứng trước hậu tố L
```

Cách nhóm hữu ích: nhóm ba chữ số thập phân (`1_000_000`), nhóm bốn bit (`0b1100_1010`), nhóm hai hoặc bốn chữ số hex (`0xCA_FE`). Ký tự `_` trong tên biến là quy tắc khác; ở đây chỉ nói về ký tự nằm trong token số.

## 6. Bẫy số 0 đứng đầu: bát phân, không phải số đệm

Trong Java, `010` là literal **cơ số 8**, nên bằng `8` thập phân. `077` bằng `63`. Các chữ số `8` và `9` không hợp lệ sau số 0 dẫn vào một literal bát phân.

```java
int a = 010; // 8
int b = 077; // 63
int c = 10;  // 10
// int invalid08 = 08; // lỗi biên dịch
// int invalid09 = 09; // lỗi biên dịch
```

Phân biệt số viết trong **mã nguồn** với chuỗi được **parse lúc runtime**:

| Biểu thức | Kết quả | Vì sao |
| --- | --- | --- |
| `010` | `8` | Literal bát phân |
| `Integer.parseInt("010")` | `10` | `parseInt` mặc định dùng cơ số 10 |
| `Integer.parseInt("010", 8)` | `8` | Truyền cơ số 8 tường minh |
| `Integer.parseInt("2A", 16)` | `42` | Parse hai chữ số hex |
| `Integer.decode("010")` | `8` | `decode` hiểu tiền tố 0 là bát phân |
| `Integer.decode("0x2A")` | `42` | `decode` hiểu tiền tố 0x là hex |

Lưu ý: `Integer.parseInt("0x2A", 16)` không chấp nhận tiền tố `0x`; `Integer.decode("0x2A")` phù hợp hơn nếu chuỗi đã chứa tiền tố cơ số. Không nhầm lẫn các hàm phân tích chuỗi này với ngữ pháp literal của trình biên dịch.

## 7. Phép toán, tràn số và chuyển kiểu

Với hai toán hạng `int`, phép cộng số nguyên thường được thực hiện **bằng kiểu `int`**; chuyển kết quả vào biến `long` chỉ diễn ra sau đó:

```java
long overflowed = 2_147_483_647 + 1; // int tràn trước -> -2147483648L
long correct = 2_147_483_647L + 1;  // long + int -> 2147483648L
```

Tương tự, `long product = 100_000 * 100_000;` thực hiện phép nhân `int` trước khi mở rộng, có thể tràn; nên dùng `100_000L * 100_000` nếu cần tích chính xác kiểu `long`.

“Literal mặc định là `int`” **không ngăn** gán một hằng `int` nằm trong miền giá trị cho `byte`, `short` hay `char`. Java cho phép chuyển hẹp trong ngữ cảnh gán một số **biểu thức hằng tại thời điểm biên dịch**:

```java
byte small = 127;      // hợp lệ: giá trị int 127 vừa byte
short sh = 30_000;     // hợp lệ: vừa short
char letter = 65;      // hợp lệ: ký tự 'A'
byte sum = 1 + 2;      // hợp lệ: constant expression bằng 3
long widened = 100;    // hợp lệ: mở rộng int -> long

// byte tooBig = 128;  // lỗi: không vừa byte
// short tooBigShort = 40_000; // lỗi: không vừa short
```

Biến `int` thông thường khác với biểu thức hằng:

```java
int local = 10;
// byte wrong = local; // lỗi: không tự chuyển hẹp từ biến int

final int fixed = 10; // constant variable, initializer là hằng biểu thức
byte ok = fixed;       // hợp lệ vì giá trị nằm trong phạm vi byte
byte narrowed = (byte) 0xFF; // -1: ép kiểu tường minh cắt bớt bit
```

Với `byte`, nếu cần diễn giải bit như số **không dấu** từ 0 đến 255, `Byte.toUnsignedInt(narrowed)` cho `255`. Đây là thao tác đọc giá trị bit, không tạo ra kiểu primitive `unsigned byte` trong Java.

## 8. Ví dụ Java 17+ chạy được hoàn chỉnh

Tạo tệp **`IntegerLiteralDemo.java`**:

```java
public class IntegerLiteralDemo {
    static String kind(int value) {
        return "int";
    }

    static String kind(long value) {
        return "long";
    }

    public static void main(String[] args) {
        int decimal = 42;
        int binary = 0b101010;
        int octal = 052;
        int hexadecimal = 0x2A;

        System.out.println("decimal=" + decimal);
        System.out.println("binary=" + binary);
        System.out.println("octal=" + octal);
        System.out.println("hexadecimal=" + hexadecimal);
        System.out.println("42 type=" + kind(42));
        System.out.println("42L type=" + kind(42L));
        System.out.println("octal010=" + 010);
        System.out.println("parse010=" + Integer.parseInt("010"));
        System.out.println("parse2A=" + Integer.parseInt("2A", 16));
        System.out.println("allBitsInt=" + 0xFFFF_FFFF);
        System.out.println("allBitsLong=" + 0xFFFF_FFFFL);
        System.out.println("minIntHex=" + 0x8000_0000);

        long overflowed = 2_147_483_647 + 1;
        long correct = 2_147_483_647L + 1;
        System.out.println("overflowed=" + overflowed);
        System.out.println("correct=" + correct);

        byte narrow = (byte) 0xFF;
        System.out.println("narrow=" + narrow);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac IntegerLiteralDemo.java
java IntegerLiteralDemo
```

Đầu ra chính xác:

```text
decimal=42
binary=42
octal=42
hexadecimal=42
42 type=int
42L type=long
octal010=8
parse010=10
parse2A=42
allBitsInt=-1
allBitsLong=4294967295
minIntHex=-2147483648
overflowed=-2147483648
correct=2147483648
narrow=-1
```

Nhận xét từ output: các tiền tố cơ số khác nhau không đổi giá trị 42; hậu tố `L` đổi kiểu literal và ảnh hưởng overload; toàn bộ bit 1 của `int` được diễn giải thành -1; phép cộng `int` có thể tràn trước khi gán cho `long`.

## 9. Tình huống sai thường gặp và quy trình đọc literal

| Viết sai hoặc hiểu sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| `long x = 3000000000;` | Literal thập phân không `L` vượt `int` | `long x = 3_000_000_000L;` |
| `int x = 09;` | 9 không thuộc hệ bát phân | `int x = 9;` |
| `int mask = 0x1_0000_0000;` | Cần hơn 32 bit để biểu diễn | Dùng `long mask = 0x1_0000_0000L;` |
| Mong `0xFFFF_FFFF` bằng 4294967295 | Đây là mẫu `int` 32 bit có dấu | Dùng `0xFFFF_FFFFL` nếu cần giá trị dương |
| `long n = 2_147_483_647 + 1;` cho âm | Tràn trong phép cộng `int` trước khi mở rộng | `long n = 2_147_483_647L + 1;` |
| `byte b = 128;` | Hằng `int` vượt miền kiểu `byte` | Chọn kiểu phù hợp hoặc kiểm tra lại dữ liệu |
| `0x_FF` báo lỗi | Gạch dưới đứng sát tiền tố | `0xFF` hoặc `0xF_F` |
| Nhầm `"010"` với `010` | Chuỗi dùng API parse, literal do compiler phân tích | Chỉ rõ cơ số khi parse chuỗi |

Khi gặp một literal, hãy kiểm tra theo thứ tự:

1. **Tiền tố:** `0b` → nhị phân, `0x` → hex, `0` dẫn trước các chữ số → bát phân, dạng còn lại → thập phân.
2. **Hậu tố:** có `L` → `long`; không → `int`, lưu ý giới hạn và ngoại lệ `-2147483648`.
3. **Giá trị bit:** literal phi thập phân có bit dấu bật sẽ biểu diễn số âm trong `int`/`long`.
4. **Ngữ cảnh biểu thức:** phép tính `int` có thể tràn trước khi giá trị được gán vào `long`.
5. **Kiểu đích:** hằng có thể chuyển hẹp có điều kiện sang `byte`/`short`/`char`, còn biến `int` không đương nhiên làm được.

**Cốt lõi:** `42`, `0b101010`, `052` và `0x2A` đều là literal `int` mang giá trị 42. Cần `L` để tạo literal `long`; tiền tố cơ số quy định cách đọc chữ số, còn bit dấu, quy tắc kiểu và biểu thức quyết định kết quả cuối cùng.