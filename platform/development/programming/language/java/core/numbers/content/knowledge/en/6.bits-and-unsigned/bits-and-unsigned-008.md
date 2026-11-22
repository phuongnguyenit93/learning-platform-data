# parseUnsignedInt, parseUnsignedLong và toUnsignedString trong Java

## 1. Mục tiêu và ngữ cảnh

Java có kiểu nguyên thủy `byte`, `short`, `int`, `long` mang dấu; không có kiểu nguyên thủy riêng cho số nguyên không dấu 32 bit hoặc 64 bit. Tuy nhiên, 32 hoặc 64 bit của một giá trị vẫn có thể được **diễn giải là không dấu** thông qua các API của `Integer` và `Long`.

Bài học này giải thích ba thao tác thường đi cùng nhau:

- `Integer.parseUnsignedInt(...)`: đọc chuỗi biểu diễn số không dấu 32 bit và trả về **mẫu bit** dưới dạng `int`.
- `Long.parseUnsignedLong(...)`: đọc chuỗi biểu diễn số không dấu 64 bit và trả về **mẫu bit** dưới dạng `long`.
- `Integer.toUnsignedString(...)` và `Long.toUnsignedString(...)`: diễn giải mẫu bit theo nghĩa không dấu rồi xuất chuỗi.

Điểm quan trọng nhất: **giá trị âm khi in theo kiểu có dấu không có nghĩa việc phân tích unsigned bị sai**. Chính cùng một mẫu bit có hai cách diễn giải.

## 2. Cùng bit, hai cách hiểu

| Bề rộng | Cách hiểu có dấu | Cách hiểu không dấu |
| --- | --- | --- |
| 32 bit (`int`) | −2³¹ đến 2³¹ − 1 | 0 đến 2³² − 1 = 4.294.967.295 |
| 64 bit (`long`) | −2⁶³ đến 2⁶³ − 1 | 0 đến 2⁶⁴ − 1 = 18.446.744.073.709.551.615 |

Java biểu diễn `int` và `long` bằng bù hai (two's complement). Tất cả bit bằng 1 có giá trị có dấu là `-1`, nhưng nếu xem là không dấu thì tương ứng với 2³² − 1 hoặc 2⁶⁴ − 1.

~~~java
int bits32 = -1;
long bits64 = -1L;

System.out.println(bits32);                           // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
System.out.println(bits64);                           // -1
System.out.println(Long.toUnsignedString(bits64));    // 18446744073709551615
~~~

Đây là *đoạn minh họa đặt trong một phương thức*; chương trình Java chạy hoàn chỉnh nằm ở phần 6. `toUnsignedString` không thay đổi bit trong biến. Nó chỉ chọn cách chuyển các bit thành ký tự thập phân.

Với số có bit dấu bằng 0, ví dụ `42`, chuỗi có dấu và không dấu giống nhau; sự khác biệt thường lộ ra khi bit cao nhất bằng 1.

## 3. Integer.parseUnsignedInt: chuỗi → mẫu bit 32 bit

Hai chữ ký thường dùng:

~~~java
static int Integer.parseUnsignedInt(String s)
static int Integer.parseUnsignedInt(String s, int radix)
~~~

- Nếu không truyền `radix`, hệ cơ số mặc định là **10**.
- `radix` từ **2 đến 36**. Chữ cái trong hệ 16 có thể viết hoa hoặc thường.
- Chuỗi phải biểu diễn giá trị thuộc khoảng **0 đến 4294967295**. Ngoài khoảng, sai chữ số theo cơ số, chuỗi rỗng hoặc dấu trừ sẽ gây `NumberFormatException`.
- Hàm trả về `int`, bởi vậy kết quả có thể âm theo cách hiểu có dấu. Để sử dụng giá trị không dấu chính xác dưới dạng kiểu lớn hơn, gọi `Integer.toUnsignedLong(int)`.

Ví dụ theo từng bước:

~~~java
int value = Integer.parseUnsignedInt("4294967295");
System.out.println(value);                           // -1
System.out.println(Integer.toUnsignedString(value)); // 4294967295
System.out.println(Integer.toUnsignedLong(value));   // 4294967295
~~~

`Integer.toUnsignedLong(value)` tạo `long` trong khoảng 0..4294967295; đây là cách dễ nhất để thực hiện phép tính 32 bit không dấu khi cần không gian số rộng hơn.

Với hệ 16:

~~~java
int hexBits = Integer.parseUnsignedInt("FFFFFFFF", 16);
System.out.println(hexBits);                            // -1
System.out.println(Integer.toUnsignedString(hexBits, 16)); // ffffffff
~~~

Chuỗi `"FFFFFFFF"` không có tiền tố `0x`. Khi chỉ định cơ số 16, truyền `"FF"` chứ không truyền `"0xFF"`; `parseUnsignedInt` không tự phát hiện hoặc loại bỏ tiền tố. Tương tự, chuỗi nhập từ người dùng cần được xử lý phần tiền tố theo quy ước của ứng dụng trước khi parse.

## 4. Long.parseUnsignedLong: chuỗi → mẫu bit 64 bit

Hai chữ ký tương ứng:

~~~java
static long Long.parseUnsignedLong(String s)
static long Long.parseUnsignedLong(String s, int radix)
~~~

Hàm chấp nhận **0 đến 18446744073709551615** (2⁶⁴ − 1), vượt giới hạn dương của `Long.parseLong` là 9223372036854775807. Kết quả vẫn là kiểu `long` có dấu: nếu bit cao nhất bằng 1 thì khi in trực tiếp sẽ ra số âm.

~~~java
long bits = Long.parseUnsignedLong("18446744073709551615");

System.out.println(bits);                            // -1
System.out.println(Long.toUnsignedString(bits));      // 18446744073709551615
System.out.println(Long.toUnsignedString(bits, 16));  // ffffffffffffffff
~~~

Không có kiểu nguyên thủy nào của Java có thể chứa **toàn bộ** giá trị unsigned 64 bit theo nghĩa số dương. Nếu cần biểu diễn như số dương để tính toán vượt 64 bit, dùng `java.math.BigInteger` sau khi chuyển mẫu bit thành chuỗi:

~~~java
import java.math.BigInteger;

// Đoạn minh họa trong phương thức:
long raw = Long.parseUnsignedLong("18446744073709551615");
BigInteger positiveValue = new BigInteger(Long.toUnsignedString(raw));
System.out.println(positiveValue.add(BigInteger.ONE)); // 18446744073709551616
~~~

Cũng có thể tính `BigInteger.valueOf(raw).add(BigInteger.ONE.shiftLeft(64))` khi `raw < 0`. Tuyệt đối không dùng `BigInteger.valueOf(raw)` một mình cho trường hợp `raw` âm nếu mục đích là lấy **giá trị unsigned**.

## 5. toUnsignedString: mẫu bit → chuỗi và cơ số

| API | Đối số đầu vào | Ý nghĩa |
| --- | --- | --- |
| `Integer.toUnsignedString(int value)` | Mẫu bit 32 bit | Chuỗi thập phân unsigned 32 bit |
| `Integer.toUnsignedString(int value, int radix)` | Mẫu bit và cơ số | Chuỗi unsigned 32 bit ở cơ số chỉ định |
| `Long.toUnsignedString(long value)` | Mẫu bit 64 bit | Chuỗi thập phân unsigned 64 bit |
| `Long.toUnsignedString(long value, int radix)` | Mẫu bit và cơ số | Chuỗi unsigned 64 bit ở cơ số chỉ định |

Ví dụ cùng một mẫu bit:

~~~java
int n = 0x8000_0000;
System.out.println(Integer.toString(n));             // -2147483648
System.out.println(Integer.toUnsignedString(n));     // 2147483648
System.out.println(Integer.toUnsignedString(n, 16)); // 80000000
System.out.println(Integer.toUnsignedString(n, 2));  // 10000000000000000000000000000000
~~~

Kết quả `toUnsignedString(value, radix)` **không tự thêm tiền tố** như `0x` hay `0b` và dùng chữ cái thường cho các chữ số lớn hơn 9. Những cơ số không hợp lệ được `toUnsignedString` xử lý theo quy ước của `Integer.toString`/`Long.toString`: dùng hệ 10; khác với hàm parse, vốn báo lỗi khi `radix` nằm ngoài 2..36.

Cặp thao tác lý tưởng khi trao đổi dữ liệu là `parseUnsignedInt` ↔ `Integer.toUnsignedString` hoặc `parseUnsignedLong` ↔ `Long.toUnsignedString` với **cùng cơ số**. Mẫu bit có thể âm nếu quan sát bằng `int`/`long` nhưng vẫn giữ được giá trị unsigned gốc trong phạm vi biểu diễn.

## 6. Ví dụ chạy độc lập trên Java 17+

Tạo tệp `UnsignedNumbersDemo.java`:

~~~java
import java.math.BigInteger;

public class UnsignedNumbersDemo {
    public static void main(String[] args) {
        int maxU32 = Integer.parseUnsignedInt("4294967295");
        long maxU64 = Long.parseUnsignedLong("18446744073709551615");

        System.out.println("u32 as int: " + maxU32);
        System.out.println("u32 decimal: " + Integer.toUnsignedString(maxU32));
        System.out.println("u32 as long: " + Integer.toUnsignedLong(maxU32));
        System.out.println("u32 from hex: " +
                Integer.toUnsignedString(Integer.parseUnsignedInt("FFFFFFFF", 16)));

        System.out.println("u64 as long: " + maxU64);
        System.out.println("u64 decimal: " + Long.toUnsignedString(maxU64));
        System.out.println("u64 hex: " + Long.toUnsignedString(maxU64, 16));

        System.out.println("compare u32 > 1: " +
                (Integer.compareUnsigned(maxU32, 1) > 0));
        System.out.println("u32 / 10: " + Integer.divideUnsigned(maxU32, 10));
        System.out.println("u32 % 10: " + Integer.remainderUnsigned(maxU32, 10));

        System.out.println("u64 / 10: " + Long.divideUnsigned(maxU64, 10L));
        System.out.println("u64 % 10: " + Long.remainderUnsigned(maxU64, 10L));

        BigInteger big = new BigInteger(Long.toUnsignedString(maxU64));
        System.out.println("u64 plus one: " + big.add(BigInteger.ONE));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac UnsignedNumbersDemo.java
java UnsignedNumbersDemo
~~~

Kết quả chuẩn:

~~~text
u32 as int: -1
u32 decimal: 4294967295
u32 as long: 4294967295
u32 from hex: 4294967295
u64 as long: -1
u64 decimal: 18446744073709551615
u64 hex: ffffffffffffffff
compare u32 > 1: true
u32 / 10: 429496729
u32 % 10: 5
u64 / 10: 1844674407370955161
u64 % 10: 5
u64 plus one: 18446744073709551616
~~~

Giải thích:

1. Hai lời gọi `parseUnsigned...` trả về mẫu bit toàn 1, được in trực tiếp thành `-1` theo kiểu có dấu.
2. Hai lời gọi `toUnsignedString` giải mã chính xác mẫu bit theo miền không dấu; lời gọi với `radix = 16` trả chữ `f` thường.
3. `Integer.toUnsignedLong` mở rộng mẫu 32 bit ra số dương `long`, tránh *sign extension* của phép chuyển kiểu `(long) maxU32`.
4. `compareUnsigned`, `divideUnsigned` và `remainderUnsigned` dùng cách hiểu unsigned, nên số lớn nhất 32/64 bit lớn hơn 1 và chia 10 có số dư 5.
5. `BigInteger` cho phép cộng vượt giới hạn unsigned 64 bit mà không tràn.

## 7. Kiểm tra biên, dữ liệu lỗi và radix

Thử các tình huống tiêu biểu:

| Lời gọi | Kết quả |
| --- | --- |
| `Integer.parseUnsignedInt("0")` | `0` |
| `Integer.parseUnsignedInt("2147483648")` | `-2147483648` (bit của 2³¹) |
| `Integer.parseUnsignedInt("4294967295")` | `-1` |
| `Integer.parseUnsignedInt("4294967296")` | `NumberFormatException`: vượt 32 bit unsigned |
| `Long.parseUnsignedLong("9223372036854775808")` | `Long.MIN_VALUE` |
| `Long.parseUnsignedLong("18446744073709551615")` | `-1L` |
| `Long.parseUnsignedLong("18446744073709551616")` | `NumberFormatException`: vượt 64 bit unsigned |
| `Integer.parseUnsignedInt("1010", 2)` | `10` |
| `Long.parseUnsignedLong("ff", 16)` | `255L` |
| `Integer.parseUnsignedInt("-1")` | `NumberFormatException`: dấu âm không hợp lệ |
| `Integer.parseUnsignedInt("0xFF", 16)` | `NumberFormatException`: `0x` không phải chữ số của hệ 16 |
| `Integer.parseUnsignedInt("12 3")` | `NumberFormatException`: có khoảng trắng bên trong |

Chuỗi có thể có dấu cộng ở đầu (`"+42"`) và các số 0 dẫn đầu (`"00042"`); chúng không làm thay đổi giá trị. Tuy nhiên, các hàm parse không tự `trim()` khoảng trắng, không nhận dấu phân cách `_` của cú pháp literal Java, và không chấp nhận dấu trừ ngay cả khi số âm đó có mẫu bit hợp lệ. Chỉ chuẩn hóa dữ liệu đầu vào (ví dụ `trim()` hoặc bỏ tiền tố) khi quy định định dạng đầu vào cho phép.

Phân biệt lỗi của parser và giá trị âm hợp lệ trong kết quả:

~~~java
try {
    int bits = Integer.parseUnsignedInt("4294967296");
    System.out.println(Integer.toUnsignedString(bits));
} catch (NumberFormatException ex) {
    System.out.println("Giá trị không thuộc miền unsigned 32 bit");
}
~~~

Đoạn trên in duy nhất:

~~~text
Giá trị không thuộc miền unsigned 32 bit
~~~

Không nên bắt `NumberFormatException` rồi chuyển mặc định về `0` nếu `0` là một giá trị có ý nghĩa nghiệp vụ; hãy thông báo lỗi nhập hoặc trả kết quả xác thực rõ ràng.

## 8. So sánh và tính toán đúng ngữ nghĩa không dấu

Chỉ parse và xuất chuỗi là chưa đủ nếu ứng dụng còn phải so sánh, chia, chia lấy dư.

~~~java
int a = Integer.parseUnsignedInt("4294967295");
int b = 1;

System.out.println(a < b);                           // true: so sánh signed (-1 < 1)
System.out.println(Integer.compareUnsigned(a, b) > 0); // true: so sánh unsigned
System.out.println(Integer.divideUnsigned(a, 2));     // 2147483647
System.out.println(Integer.remainderUnsigned(a, 2));  // 1
~~~

Đây là đoạn minh họa trong phương thức. `Long` có API tương ứng: `Long.compareUnsigned`, `Long.divideUnsigned`, `Long.remainderUnsigned`. Phép `+`, `-`, `*` trên `int`/`long` giữ các bit thấp và có thể tràn (wrap modulo 2³²/2⁶⁴); Java không tự báo tràn cho các phép này. Nếu nghiệp vụ yêu cầu phát hiện tràn **trong miền unsigned**, cần kiểm tra riêng hoặc dùng `BigInteger` để tính rồi kiểm tra giới hạn.

Với **unsigned 32 bit**, cũng có thể mở rộng cả hai toán hạng bằng `Integer.toUnsignedLong` rồi dùng các phép so sánh/chia có dấu trên `long`, vì mọi unsigned 32 bit đều nằm trong miền dương của `long`. Mẹo tương tự không áp dụng trọn vẹn cho unsigned 64 bit: cần API unsigned của `Long` hoặc `BigInteger`.

## 9. Áp dụng: mã nhận diện 32 bit từ giao thức hoặc tệp nhị phân

Một giao thức có thể quy định trường `requestId` là số không dấu 32 bit. Giá trị `4026531841` có mẫu bit `0xF0000001`; nếu lưu bằng `int`, Java nhìn nó thành số âm. Ta vẫn có thể truyền và ghi lại chính xác chuỗi thập phân unsigned:

~~~java
int requestIdBits = Integer.parseUnsignedInt("4026531841");
String wireText = Integer.toUnsignedString(requestIdBits);

System.out.println(requestIdBits); // -268435455
System.out.println(wireText);      // 4026531841
~~~

Đây là đoạn minh họa trong phương thức. Khi nhận dữ liệu từ luồng byte, thứ tự byte (*endianness*) và việc ghép bit là vấn đề riêng; `parseUnsignedInt` nhận **chuỗi chữ số**, không giải mã trực tiếp mảng byte hay xử lý byte order. Nếu cần đọc một byte như 0..255, dùng `Byte.toUnsignedInt(byteValue)` để tránh ảnh hưởng của sign extension.

## 10. Lỗi thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Dùng `Integer.parseInt("4294967295")` | Vượt `Integer.MAX_VALUE` | `Integer.parseUnsignedInt` |
| Dùng `Long.parseLong` cho 2⁶⁴ − 1 | Vượt `Long.MAX_VALUE` | `Long.parseUnsignedLong` |
| In `System.out.println(bits)` rồi cho rằng dữ liệu sai | Thấy số âm | `Integer.toUnsignedString` hoặc `Long.toUnsignedString` |
| Ép `(long) intBits` để lấy unsigned 32 bit | Âm do sign extension | `Integer.toUnsignedLong(intBits)` |
| So sánh `a < b` với các bit unsigned | Dùng thứ tự signed | `compareUnsigned(a, b)` |
| Chia `a / b` khi toán hạng có bit dấu bằng 1 | Dùng phép chia signed | `divideUnsigned` và `remainderUnsigned` |
| Truyền `"0xFF"` cùng radix 16 | Parse thất bại | Bỏ tiền tố, truyền `"FF"` |
| Để số nguyên lớn thành literal `18446744073709551615L` | Không biên dịch | Parse từ chuỗi; dùng `BigInteger` khi cần số dương |
| Mong parse tự loại bỏ khoảng trắng hoặc `_` | `NumberFormatException` | Chuẩn hóa đầu vào có kiểm soát |

## 11. Tự kiểm tra

**Câu 1.** Vì sao `Integer.parseUnsignedInt("4294967295")` trả `-1` nhưng không ném lỗi?

Vì chuỗi hợp lệ với số không dấu 32 bit; hàm trả lại đúng 32 bit toàn 1 dưới kiểu `int` có dấu. `Integer.toUnsignedString` sẽ chuyển chính 32 bit ấy thành `"4294967295"`.

**Câu 2.** Làm cách nào nhận unsigned 32 bit lớn nhất thành số dương để cộng với 1 mà không mất dữ liệu?

~~~java
int raw = Integer.parseUnsignedInt("4294967295");
long sum = Integer.toUnsignedLong(raw) + 1L;
System.out.println(sum); // 4294967296
~~~

Đây là đoạn minh họa trong phương thức; `long` có đủ miền dương cho kết quả này.

**Câu 3.** Có thể làm phép cộng `+1` trên unsigned 64 bit lớn nhất và nhận số dương 18446744073709551616 dưới kiểu `long` không?

Không. Kiểu `long` không chứa được số dương đó. Chuyển sang `BigInteger` theo cách ở phần 4 trước khi cộng.

**Câu 4.** Nếu input là `"ffffffffffffffff"` theo hệ 16, nên dùng API nào để giữ đủ mẫu bit?

`Long.parseUnsignedLong("ffffffffffffffff", 16)`, rồi `Long.toUnsignedString(result, 16)` để xuất lại. Kết quả xuất là `"ffffffffffffffff"`.

## 12. Ghi nhớ

- `parseUnsignedInt` và `parseUnsignedLong` **kiểm tra miền giá trị unsigned**, trả về mẫu bit trong kiểu có dấu tương ứng.
- `toUnsignedString` **xuất các bit theo miền unsigned**, không thay đổi mẫu bit đã lưu.
- Với 32 bit, `Integer.toUnsignedLong` giúp chuyển thành số dương `long`; với 64 bit cần `BigInteger` nếu muốn số dương vượt `Long.MAX_VALUE`.
- Cơ số khi parse và khi xuất phải phù hợp với định dạng dữ liệu. Chú ý các điều kiện lỗi, phép so sánh/chia unsigned và tràn số khi tính toán.
