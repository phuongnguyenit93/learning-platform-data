# Độ rộng kiểu, dấu của số và hậu tố `long` trong Java hiện đại

> **Phạm vi bài học:** Hiểu chính xác số bit của các kiểu nguyên thủy, cách Java diễn giải số có dấu, kiểu của *numeric literal*, hậu tố `L`, quy tắc nâng/ép kiểu và các lỗi tràn số. Đây là kiến thức nền của Java vẫn áp dụng nguyên vẹn trên JDK hiện đại. Phần cú pháp liên quan trực tiếp Java 7 là **binary literal `0b...`** và **dấu gạch dưới `_` trong literal số**; các quy tắc `int`/`long`/dấu đã tồn tại trước Java 7 nhưng vẫn thiết yếu khi đọc và viết code hiện nay.

## 1. Độ rộng kiểu là gì, vì sao phải quan tâm?

**Độ rộng kiểu (bit width)** là số bit Java dùng để biểu diễn một giá trị của kiểu nguyên thủy. Với các kiểu số nguyên, số bit quyết định miền giá trị, cách bit dấu được hiểu và kết quả của phép chuyển kiểu, dịch bit, overflow. Đây là đặc tả của ngôn ngữ Java, **không phụ thuộc máy đang chạy hệ điều hành 32-bit hay 64-bit**.

| Kiểu nguyên thủy | Độ rộng | Có dấu? | Miền giá trị / ý nghĩa |
| --- | ---: | --- | --- |
| `byte` | 8 bit | Có | -128 đến 127 |
| `short` | 16 bit | Có | -32.768 đến 32.767 |
| `int` | 32 bit | Có | -2.147.483.648 đến 2.147.483.647 |
| `long` | 64 bit | Có | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `char` | 16 bit | **Không** | 0 đến 65.535; một đơn vị mã **UTF-16**, không nhất thiết là một ký tự Unicode hoàn chỉnh |
| `float` | 32 bit | Số dấu phẩy động | IEEE 754 binary32; có bit dấu, số mũ và phần trị |
| `double` | 64 bit | Số dấu phẩy động | IEEE 754 binary64; có bit dấu, số mũ và phần trị |

`boolean` chỉ có `true`/`false`, **không phải kiểu số** và Java Language Specification không quy định một độ rộng lưu trữ cố định cho mỗi giá trị `boolean`. Bảng trên nói về *primitive value*, không phải kích thước của object wrapper như `Integer` hoặc bộ nhớ một phần tử mảng.

Mã kiểm tra chạy trên JDK 17+; lưu thành `NumericWidthsDemo.java`:

```java
public class NumericWidthsDemo {
    public static void main(String[] args) {
        System.out.println("byte=" + Byte.SIZE + " " + Byte.MIN_VALUE + ".." + Byte.MAX_VALUE);
        System.out.println("short=" + Short.SIZE + " " + Short.MIN_VALUE + ".." + Short.MAX_VALUE);
        System.out.println("int=" + Integer.SIZE + " " + Integer.MIN_VALUE + ".." + Integer.MAX_VALUE);
        System.out.println("long=" + Long.SIZE + " " + Long.MIN_VALUE + ".." + Long.MAX_VALUE);
        System.out.println(
            "char=" + Character.SIZE + " "
            + (int) Character.MIN_VALUE + ".." + (int) Character.MAX_VALUE
        );
        System.out.println("float=" + Float.SIZE + " double=" + Double.SIZE);
    }
}
```

```bash
javac -encoding UTF-8 --release 17 NumericWidthsDemo.java
java NumericWidthsDemo
```

```text
byte=8 -128..127
short=16 -32768..32767
int=32 -2147483648..2147483647
long=64 -9223372036854775808..9223372036854775807
char=16 0..65535
float=32 double=64
```

Trong code thực tế, dùng `Byte.MIN_VALUE`/`MAX_VALUE`, `Integer.MIN_VALUE`/`MAX_VALUE` và `Long.MIN_VALUE`/`MAX_VALUE` để tránh nhập nhầm giới hạn. `SIZE` là số bit, không phải số byte.

## 2. “Có dấu” nghĩa là gì?

### 2.1. Các kiểu số nguyên có dấu

`byte`, `short`, `int`, `long` biểu diễn số nguyên có dấu theo **two's complement** (bù hai). Với độ rộng `n` bit, miền giá trị là từ `-2^(n-1)` đến `2^(n-1)-1`. Một bit cao nhất thể hiện dấu theo cách diễn giải two's complement: ví dụ bit pattern 8 bit `1111_1111` của `byte` là **-1**, còn `0111_1111` là **127**.

Đó là lý do miền âm có nhiều hơn miền dương một giá trị: `Integer.MIN_VALUE` bằng -2.147.483.648, nhưng `Integer.MAX_VALUE` chỉ bằng 2.147.483.647. Không thể lấy giá trị dương tương ứng của `Integer.MIN_VALUE` trong chính `int` mà không bị overflow.

**`char` là ngoại lệ:** `char` cũng có 16 bit, nhưng **không có dấu**, dùng làm một đơn vị mã UTF-16. Trong phép toán số học, `char` thường được nâng lên `int`. Với ký tự Unicode ngoài BMP (chẳng hạn nhiều emoji), một code point dùng **hai** `char` (surrogate pair); vì vậy không dùng `char` để mặc định biểu diễn mọi ký tự Unicode.

### 2.2. Chuyển kiểu không thay đổi ý nghĩa của bit theo mong muốn của người viết

Ví dụ `(byte) 0xFF` giữ 8 bit thấp `1111_1111`, nên giá trị `byte` là -1. Khi cần đọc một octet trong giao thức như **số không dấu 0..255**, ta có thể chuyển cách diễn giải bằng:

```java
byte raw = (byte) 0xFF;
int unsignedValue = raw & 0xFF;            // 255
int sameValue = Byte.toUnsignedInt(raw);    // 255: API Java 8+
```

Đây là *snippet* đặt trong method; không phải chương trình có `main`. Trong Java, `Byte.toUnsignedInt` trả về `int`, **không tạo một kiểu `unsigned byte` mới**. Tương tự, `Integer.toUnsignedLong`, `Integer.compareUnsigned`, `Long.parseUnsignedLong` là tiện ích được bổ sung từ **Java 8** để làm việc với cách diễn giải không dấu; các kiểu `int` và `long` vẫn là kiểu signed.

## 3. Literal nguyên: kiểu được quyết định ngay khi biên dịch

*Integer literal* là hằng số nguyên viết trực tiếp trong mã nguồn: `42`, `0xFF`, `0b1010`, `1_000`, `3_000_000_000L`. Java không suy ra rằng một literal “quá lớn với `int`” thì tự chuyển nó sang `long`.

**Quy tắc cốt lõi:**

- Literal nguyên **không có hậu tố `L`/`l`** có kiểu `int`.
- Literal nguyên **có hậu tố `L`/`l`** có kiểu `long`.
- Luôn ưu tiên chữ hoa **`L`** vì chữ thường `l` dễ nhầm với chữ số `1`.
- Dấu trừ `-` là **toán tử một ngôi**, không phải một phần của literal. Vì vậy `-42L` được phân tích thành toán tử `-` tác động lên literal `42L`.
- Phân biệt *kiểu của literal* với *kiểu biến nhận giá trị*: khai báo `long` ở bên trái **không cứu được** một literal `int` sai phạm vi hoặc phép tính `int` đã tràn trước đó.

### 3.1. Khi nào cần hậu tố `L`?

```java
int okInt = 2_000_000_000;
long smallLong = 1_000;            // int literal, được widening sang long
long largeLong = 3_000_000_000L;  // literal long ngay từ đầu
long mask = 0xFFFF_FFFFL;         // kiểu long, giá trị dương 4294967295
```

Các khai báo sau **không biên dịch**, chỉ để phân tích lỗi; không chép chúng vào file runnable:

```java
long invalid = 3_000_000_000;  // ERROR: literal decimal thiếu L, vượt int
int tooLarge = 3_000_000_000L; // ERROR: long không tự thu hẹp về int
byte outOfRange = 128;         // ERROR: ngoài miền byte
```

Với biên dương của `long`, `9_223_372_036_854_775_807L` là hợp lệ; lớn hơn `Long.MAX_VALUE` thì không thể biểu diễn bằng `long`. Với số nguyên vượt 64 bit, cân nhắc `java.math.BigInteger` thay vì ép kiểu hoặc chờ overflow.

**Trường hợp đặc biệt ở biên âm:** `-2147483648` và `-9223372036854775808L` là cú pháp hợp lệ nhờ quy tắc riêng cho literal giới hạn khi đứng ngay sau toán tử `-`. Ngược lại, literal dương `2147483648` hoặc `9223372036854775808L` đứng độc lập không hợp lệ. Trong code thông thường, dùng `Integer.MIN_VALUE`/`Long.MIN_VALUE` dễ đọc và ít sai hơn.

### 3.2. Cơ số và dấu gạch dưới: phần cú pháp Java 7 vẫn hữu ích

Java 7 đưa vào:

- Literal **nhị phân** bắt đầu bằng `0b` hoặc `0B`, ví dụ `0b1010_0101`.
- Dấu `_` để nhóm chữ số trong numeric literal: `1_000_000`, `3_000_000_000L`, `0xFF_00`, `0b1111_0000`. Dấu gạch dưới **không làm thay đổi giá trị hay kiểu** của literal.

Literal thập lục phân `0x` vẫn hữu ích cho bitmask. Cần nhớ kiểu và độ rộng: `0xFFFF_FFFF` là literal `int` với bit pattern 32 bit toàn 1 nên biểu diễn **-1**; `0xFFFF_FFFFL` là literal `long` 64 bit, cùng 32 bit thấp nhưng còn 32 bit cao bằng 0 nên biểu diễn **4.294.967.295**.

```java
int binary = 0b1010_0101;     // 165
int grouped = 1_000_000;      // 1000000
int signedHex = 0xFFFF_FFFF;  // -1
long positiveHex = 0xFFFF_FFFFL; // 4294967295
```

Dấu `_` chỉ được dùng **giữa các chữ số của literal**. Những cách viết như `1_`, `_1000` (khi đứng riêng), `0b_1010`, `1_.5`, `12_L` đều không hợp lệ trong vai trò literal số. Khi đọc dữ liệu từ chuỗi, `Long.parseLong("3_000")` **không** nhận gạch dưới, còn `Long.parseLong("3000")` thì nhận; ký hiệu `L` cũng chỉ thuộc cú pháp *source code*, không phải nội dung có thể truyền thẳng vào parser.

### 3.3. Chương trình quan sát kiểu literal

Lưu thành `LongLiteralDemo.java`:

```java
public class LongLiteralDemo {
    public static void main(String[] args) {
        int binary = 0b1010_0101;
        int grouped = 1_000_000;
        long big = 3_000_000_000L;
        int signedHex = 0xFFFF_FFFF;
        long positiveHex = 0xFFFF_FFFFL;

        System.out.println("binary=" + binary);
        System.out.println("grouped=" + grouped);
        System.out.println("big=" + big);
        System.out.println("hex int=" + signedHex);
        System.out.println("hex long=" + positiveHex);
        System.out.println("parsed=" + Long.parseLong("3000000000"));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 LongLiteralDemo.java
java LongLiteralDemo
```

```text
binary=165
grouped=1000000
big=3000000000
hex int=-1
hex long=4294967295
parsed=3000000000
```

## 4. Kiểu của phép tính và kiểu biến đích là hai vấn đề khác nhau

### 4.1. Numeric promotion

Java thực hiện *numeric promotion* trước nhiều phép toán:

- `byte`, `short` và `char` thường được nâng thành `int` khi tham gia cộng/trừ/nhân/chia với nhau. Vì vậy `byte + byte` trả **`int`**, không phải `byte`.
- `int` kết hợp `long` thường tạo biểu thức kiểu `long`; ví dụ `intValue + 1L` là `long`.
- `long` kết hợp `float` sẽ tạo kết quả `float`, có thể mất độ chính xác của phần nguyên; `float` kết hợp `double` cho kiểu `double`.
- Gán một biểu thức `int` vào biến `long` chỉ *widening* **sau khi** biểu thức đó đã được tính.

```java
byte a = 100;
byte b = 27;
int sum = a + b;             // 127; kết quả là int
long widened = (long) a + b; // phép cộng được thực hiện ở long
```

Với một **hằng compile-time** nằm trong phạm vi đích, Java cho phép một số phép narrowing trong khai báo: `byte b = 100 + 20;` hợp lệ vì giá trị hằng 120 vừa `byte`, nhưng `byte b = 100 + 40;` lỗi vì 140 vượt giới hạn. Ngoại lệ đối với hằng này không có nghĩa phép cộng hai biến `byte` tạo ra `byte`.

### 4.2. Widening và narrowing

| Chuyển đổi | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| `int` → `long` | `long n = someInt;` | Không mất giá trị vì miền `long` chứa miền `int` |
| `byte` → `int` | `int n = someByte;` | Giá trị âm vẫn âm (*sign extension*) |
| `long` → `int` | `int n = (int) someLong;` | Bỏ các bit cao; có thể đổi giá trị nghiêm trọng |
| `int` → `byte` | `byte n = (byte) 130;` | Chỉ giữ 8 bit thấp: kết quả -126 |
| `long` → `double` | `double d = someLong;` | Không bảo đảm giữ nguyên mọi số nguyên 64 bit vì độ chính xác hữu hạn |

**Ép kiểu tường minh không kiểm tra overflow.** Khi cần chuyển `long` sang `int` mà **không chấp nhận mất dữ liệu**, dùng `Math.toIntExact(long)` (API từ **Java 8**) để nhận `ArithmeticException` nếu ngoài phạm vi.

## 5. Tràn số: vì sao `long` bên trái vẫn có thể sai?

Giả sử cần đổi 30 ngày ra mili giây:

```java
long wrongMillis = 30 * 24 * 60 * 60 * 1_000;
long rightMillis = 30L * 24 * 60 * 60 * 1_000;
```

**Dòng đầu sai:** toàn bộ toán hạng là `int`, nên phép nhân tính ở `int`, tràn qua giới hạn 2.147.483.647 rồi **mới** gán kết quả tràn cho `long`. Dòng thứ hai bắt đầu bằng `30L`, khiến chuỗi nhân thực hiện ở `long`. Có thể dùng `(long) days * ...` nếu giá trị `days` là biến kiểu `int`.

**Số nguyên Java không tự ném ngoại lệ khi overflow trong phép cộng/trừ/nhân bình thường**; kết quả vòng theo độ rộng cố định (two's complement). Đối với tính toán cần bảo toàn giá trị, dùng `Math.addExact`, `subtractExact`, `multiplyExact`, `toIntExact` (các API này có từ **Java 8**) hoặc `BigInteger` khi giá trị có thể vượt khỏi `long`.

Lưu thành `OverflowDemo.java`:

```java
public class OverflowDemo {
    public static void main(String[] args) {
        long wrongMillis = 30 * 24 * 60 * 60 * 1_000;
        long rightMillis = 30L * 24 * 60 * 60 * 1_000;

        System.out.println("wrong ms=" + wrongMillis);
        System.out.println("right ms=" + rightMillis);
        System.out.println("wrapped=" + (Integer.MAX_VALUE + 1));

        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException error) {
            System.out.println("checked addition: overflow");
        }

        try {
            System.out.println(Math.toIntExact(3_000_000_000L));
        } catch (ArithmeticException error) {
            System.out.println("narrowing: outside int range");
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 OverflowDemo.java
java OverflowDemo
```

```text
wrong ms=-1702967296
right ms=2592000000
wrapped=-2147483648
checked addition: overflow
narrowing: outside int range
```

**Các bẫy liên quan:**

1. `(long) (a * b)` có thể ép kiểu **quá muộn** nếu `a` và `b` đều là `int`; dùng `(long) a * b` để phép nhân có kiểu `long` từ đầu.
2. `-Integer.MIN_VALUE` vẫn ra `Integer.MIN_VALUE` do tràn số; `Math.negateExact(Integer.MIN_VALUE)` ném `ArithmeticException`.
3. `long` cũng có thể tràn; hậu tố `L` giúp chọn kiểu 64 bit nhưng **không** tạo phạm vi vô hạn.
4. Đừng dựa vào overflow như cách kiểm tra đầu vào; hãy kiểm tra miền giá trị và dùng checked arithmetic nếu nghiệp vụ yêu cầu tính đúng tuyệt đối.

## 6. Dịch bit: độ rộng và dấu quyết định kết quả

Các toán tử bit vẫn xuất hiện thường xuyên trong xử lý binary protocol, cờ trạng thái, checksum và serialization:

- `<<`: dịch trái, các bit tràn ra ngoài độ rộng bị loại bỏ.
- `>>`: dịch phải **có giữ dấu**, điền bit dấu vào phía trái.
- `>>>`: dịch phải **điền 0**, thường dùng khi xử lý bit pattern không dấu.

**Kiểu toán hạng trái quyết định độ rộng của phép dịch.** Với `int`, số vị trí dịch chỉ dùng **5 bit thấp** của toán hạng phải (tương đương modulo 32); với `long` dùng **6 bit thấp** (modulo 64). Vì vậy:

- `1 << 40` thực chất dịch `int` đi 8 vị trí, ra **256**.
- `1L << 40` dịch `long` đi 40 vị trí, ra **1.099.511.627.776**.
- `(long) (1 << 40)` vẫn ra **256**, vì ép kiểu diễn ra sau phép dịch.

Lưu thành `BitWidthDemo.java`:

```java
public class BitWidthDemo {
    public static void main(String[] args) {
        byte raw = (byte) 0xFF;

        System.out.println("signed byte=" + raw);
        System.out.println("unsigned byte=" + (raw & 0xFF));
        System.out.println("int shift=" + (1 << 40));
        System.out.println("long shift=" + (1L << 40));
        System.out.println("signed right=" + (-8 >> 1));
        System.out.println("zero-fill right=" + (-8 >>> 1));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BitWidthDemo.java
java BitWidthDemo
```

```text
signed byte=-1
unsigned byte=255
int shift=256
long shift=1099511627776
signed right=-4
zero-fill right=2147483644
```

`>>>` không biến `int` thành kiểu unsigned; kết quả vẫn có kiểu `int`. Khi cần xử lý dãy bit từ mạng/file, viết rõ **độ rộng, endianness, bit mask và cách mở rộng dấu** theo hợp đồng dữ liệu. Tránh suy diễn “64-bit JVM” nghĩa là mọi phép toán shift tự động dùng `long`.

## 7. `float`/`double` cũng có độ rộng nhưng không giống `int`/`long`

Số dấu phẩy động có cách biểu diễn khác số nguyên: `float` dùng 32 bit (binary32), `double` dùng 64 bit (binary64). Bit của chúng chia cho **dấu, số mũ và phần trị**. Dấu ở đây không tạo miền nguyên kiểu two's complement; cả hai có thể biểu diễn `NaN`, vô cực dương/âm và có sai số làm tròn.

- `1.0` và `1.0d` là literal `double`; `1.0f` là literal `float`. Đây là **hậu tố `F`/`D`**, khác hậu tố `L` chỉ dùng cho số nguyên.
- `float value = 1.0;` không tự biên dịch chỉ vì số là 1.0: literal bên phải có kiểu `double`; cần `1.0f` hoặc phép chuyển kiểu có chủ đích.
- `double` có khoảng **53 bit độ chính xác nhị phân**, nên nhiều giá trị nguyên `long` lớn không thể biểu diễn chính xác bằng `double` mặc dù `double` cũng chiếm 64 bit.
- `0.1 + 0.2` với `double` không chính xác tuyệt đối theo thập phân; kết quả có thể hiển thị `0.30000000000000004`. Với tiền hoặc số thập phân yêu cầu chính xác, dùng `BigDecimal` (đầu vào chuỗi/`valueOf` phù hợp) hoặc lưu đơn vị nhỏ nhất bằng số nguyên, cùng quy tắc làm tròn rõ ràng.

Lưu thành `PrecisionDemo.java`:

```java
import java.math.BigDecimal;

public class PrecisionDemo {
    public static void main(String[] args) {
        long original = 9_007_199_254_740_993L;
        double asDouble = original;

        System.out.println("round-trip equal=" + (original == (long) asDouble));
        System.out.println("round-trip value=" + (long) asDouble);
        System.out.println("double sum=" + (0.1 + 0.2));
        System.out.println(
            "decimal sum=" +
            new BigDecimal("0.1").add(new BigDecimal("0.2")).toPlainString()
        );
    }
}
```

```bash
javac -encoding UTF-8 --release 17 PrecisionDemo.java
java PrecisionDemo
```

```text
round-trip equal=false
round-trip value=9007199254740992
double sum=0.30000000000000004
decimal sum=0.3
```

Vì thế, **chọn `long` thay `double`** cho một ID nguyên lớn hoặc đếm số lượng cần giá trị nguyên chính xác. Chỉ đổi sang dấu phẩy động khi bài toán cho phép biểu diễn xấp xỉ.

## 8. Những tình huống chọn kiểu thường gặp

| Tình huống | Kiểu/cú pháp thường phù hợp | Lý do và cảnh báo |
| --- | --- | --- |
| Số lượng nhỏ, chỉ số mảng, vòng lặp | `int` | Thông dụng, đủ độ rộng cho các API dùng `int`; vẫn phải kiểm tra giới hạn |
| Epoch milliseconds, timeout lớn, kích thước hoặc bộ đếm có thể vượt `int` | `long`, `...L` | Miền rộng hơn; tính toán đầu vào phải được nâng lên `long` từ sớm |
| ID số 64 bit nhận từ hệ khác | `long` nếu hợp đồng dùng signed 64 bit | Không chuyển qua `double` hoặc JavaScript Number nếu cần giữ đúng mọi bit |
| Một byte giao thức 0..255 | `byte` để lưu raw bits, `& 0xFF` khi diễn giải | Java `byte` có dấu; xác định rõ byte order cho trường nhiều byte |
| Bitmask, cờ trạng thái | `int`/`long` với `0b...`/`0x...` | Định nghĩa rõ bit index, mask và phép shift |
| Phép tính nguy cơ vượt miền | `Math.*Exact` hoặc `BigInteger` | Chọn kiểm tra overflow hoặc miền lớn theo yêu cầu |
| Tiền/số thập phân có quy tắc làm tròn chính xác | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất | `float`/`double` có sai số nhị phân |
| Giá trị số đọc từ text | `Integer.parseInt`, `Long.parseLong`, `BigInteger` | Parser nhận chuỗi chữ số hợp lệ; ký pháp `L`, `_` của source không phải cú pháp parse |

Với ứng dụng lưu trữ/giao tiếp, kiểu Java phải đi cùng **đặc tả miền số ở database, JSON, API và các client khác**. Ví dụ JSON có thể mang một số nguyên 64 bit, nhưng JavaScript `Number` không biểu diễn chính xác mọi số nguyên 64 bit; đôi khi hợp đồng API cần truyền ID dạng chuỗi. Quyết định này thuộc thiết kế giao thức và không thay đổi bản chất `long`.

## 9. Các lỗi phổ biến cần tự nhận ra

1. **Tưởng khai báo `long` làm biểu thức trước dấu `=` chạy ở `long`.** Sai: `long ms = 30 * 24 * 60 * 60 * 1000;` bị tràn `int`. Sửa bằng `30L` hoặc ép toán hạng đầu tiên.
2. **Quên `L` với literal nguyên lớn hơn `Integer.MAX_VALUE`.** Sửa thành `3_000_000_000L`.
3. **Dùng hậu tố `l` viết thường.** Vẫn hợp lệ nhưng dễ đọc nhầm; ưu tiên `L`.
4. **Hiểu `0xFFFF_FFFF` là 4.294.967.295 trong `int`.** Nó mang dấu trong 32 bit, nên có giá trị -1; cần `0xFFFF_FFFFL` nếu muốn giá trị dương đó bằng `long`.
5. **Cho rằng `byte + byte` có kiểu `byte`.** Kết quả được nâng lên `int`; nếu ép về `byte` cần biết khả năng mất dữ liệu.
6. **Dùng `(long) (a * b)` thay vì `(long) a * b`.** Ép sau phép nhân không cứu được overflow đã xảy ra.
7. **Dùng `1 << 40` để lấy bit 40.** Toán hạng trái là `int`; phải dùng `1L << 40`.
8. **Lẫn `>>>` với kiểu unsigned.** Đây là phép dịch điền 0; nó không đổi kiểu dữ liệu.
9. **Tin rằng `double` 64 bit giữ đúng mọi `long` 64 bit.** Độ chính xác nhị phân của `double` không đủ cho mọi giá trị nguyên 64 bit.
10. **Trộn hậu tố source với dữ liệu text:** `Long.parseLong("123L")` hoặc `Long.parseLong("1_000")` ném `NumberFormatException`; hãy parse theo định dạng input thực sự được chấp nhận.
11. **Nhầm `char` 16 bit là một Unicode code point.** Dữ liệu Unicode ngoài BMP cần xử lý bằng code point API khi có yêu cầu.
12. **Dựa vào overflow cho dữ liệu nghiệp vụ quan trọng.** Số nguyên Java có thể vòng mà không ném lỗi; dùng kiểm tra miền hoặc checked arithmetic.

## 10. Luyện tập có đáp án

**Bài 1.** Cho `long x = 2_147_483_648;`. Có chạy được không?  
**Đáp án:** Không. Literal decimal thiếu `L` vượt phạm vi `int`. Đúng: `long x = 2_147_483_648L;`.

**Bài 2.** `long result = 2_000_000_000 + 2_000_000_000;` cho kết quả nào?  
**Đáp án:** `-294967296`. Hai toán hạng là `int` và cộng ở `int` trước khi widening. Sửa thành `2_000_000_000L + 2_000_000_000` để ra `4000000000`.

**Bài 3.** `byte b = (byte) 255; int value = b & 0xFF;` thì `b` và `value` là bao nhiêu?  
**Đáp án:** `b = -1`; `value = 255`.

**Bài 4.** Khác nhau giữa `1 << 40` và `1L << 40`?  
**Đáp án:** Kết quả tương ứng `256` và `1099511627776`. Độ rộng toán hạng trái quyết định cách tính số vị trí shift.

**Bài 5.** `char` có thể giữ trọn mọi ký tự Unicode trong một phần tử không?  
**Đáp án:** Không. Nó chứa một code unit UTF-16; một số Unicode code point cần hai code unit.

**Bài 6.** Tại sao `long value = 9_007_199_254_740_993L; double d = value;` không giữ được số nguyên gốc?  
**Đáp án:** `double` có 64 bit lưu trữ nhưng chỉ khoảng 53 bit độ chính xác phần trị; `d` được làm tròn.

**Bài thực hành A.** Viết hàm `long durationMillis(int days)`, tính số mili giây bằng phép nhân kiểu `long` và dùng `Math.multiplyExact` khi phải báo lỗi overflow. Kiểm tra `days = 1`, `30`, `365` và giá trị rất lớn.

**Bài thực hành B.** Nhận một giá trị hex 8 bit do người dùng nhập, parse theo radix 16 thành số 0..255, chuyển sang `byte` để lưu và in cả giá trị có dấu/không dấu. Xác minh input ngoài phạm vi bị từ chối.

**Bài thực hành C.** So sánh `Long.MAX_VALUE` với `Long.MAX_VALUE + 1`, sau đó thay phép cộng bằng `Math.addExact`. Giải thích vì sao kết quả và cách báo lỗi khác nhau.

## 11. Tài liệu chuẩn để tra cứu

- [Java Language Specification — Integer Literals (`3.10.1)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.1): quy tắc `int`/`long`, hậu tố `L`, cú pháp nhị phân và dấu `_`.
- [Java Language Specification — Primitive Types and Values (`4.2)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): miền giá trị, signed integer, `char`, `float`/`double`.
- [Java Language Specification — Numeric Contexts (`5.6)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6): nâng kiểu trong biểu thức số học.
- [Java Language Specification — Shift Operators (`15.19)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): quy tắc dịch bit và số bit dùng từ toán hạng dịch.
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, `toIntExact` và các toán tử kiểm tra overflow.

**Ghi nhớ:** `int` luôn là signed 32 bit, `long` luôn là signed 64 bit; hậu tố **`L`** quyết định kiểu của literal, còn kiểu của **toàn biểu thức** quyết định liệu phép tính có tràn trước khi gán hay không. Java 7 bổ sung `0b` và `_` để literal dễ đọc hơn; khi dùng Java hiện đại, phải tiếp tục phân biệt rõ độ rộng, bit dấu, phép promotion và giới hạn giá trị.
