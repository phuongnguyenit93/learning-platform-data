# Quy tắc giới hạn số bit dịch theo kiểu toán hạng trong Java

> **Java core — language-basics / Toán tử bit**  
> **Môi trường:** JDK 17+, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Biết Java xác định số bit dịch thực sự theo **kiểu của toán hạng bên trái sau khi nâng kiểu**, giải thích vì sao dịch 32/64 bit hoặc dịch với số âm không báo lỗi, và tránh mất dữ liệu vì chuyển sang `long` quá muộn.

## 1. Toán tử dịch bit và hai toán hạng

Java có ba toán tử dịch bit dành cho các kiểu số nguyên:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `x << n` | Dịch trái, điền bit 0 ở bên phải | `1 << 3` → 8 |
| `x >> n` | Dịch phải **có dấu**, giữ bit dấu ở bên trái | `-8 >> 1` → -4 |
| `x >>> n` | Dịch phải **không dấu**, điền bit 0 ở bên trái | `-8 >>> 1` → 2147483644 |

Trong `x << n`, `x` là **giá trị bị dịch**, `n` là **số lượng dịch** (*shift distance*). Cả hai phải là kiểu nguyên (hoặc wrapper được unbox); `float`, `double` và `boolean` không được dùng làm toán hạng dịch.

**Đừng hiểu số lượng dịch là số bit Java sẽ dùng nguyên vẹn.** Java chỉ lấy một số bit thấp của `n`, theo kiểu kết quả của toán hạng **trái**.

## 2. Quy tắc quan trọng nhất: `int` dùng 5 bit thấp, `long` dùng 6 bit thấp

| Kiểu toán hạng trái **sau unary numeric promotion** | Độ rộng | Bit thấp của số lượng dịch được dùng | Số lượng dịch hiệu lực |
| --- | ---: | --- | --- |
| `int` | 32 bit | 5 bit thấp, mask `0x1F` | `n & 0x1F`, từ 0 đến 31 |
| `long` | 64 bit | 6 bit thấp, mask `0x3F` | `n & 0x3F`, từ 0 đến 63 |
| `byte`, `short`, `char` | Nâng thành `int` | **5 bit thấp**, không phải 3/4 bit | `n & 0x1F` |

Ví dụ dễ nhớ:

~~~java
int a = 1;
System.out.println(a << 31); // -2147483648
System.out.println(a << 32); // 1, vì 32 & 31 == 0
System.out.println(a << 33); // 2, vì 33 & 31 == 1

long b = 1L;
System.out.println(b << 32); // 4294967296
System.out.println(b << 64); // 1, vì 64 & 63 == 0
System.out.println(b << 65); // 2, vì 65 & 63 == 1
~~~

**Mấu chốt:** `1 << 32` bằng **1**, không phải 0; còn `1L << 32` bằng **4294967296**. Java không tự động ném ngoại lệ khi số lượng dịch đạt hoặc vượt độ rộng bit.

Đây là phép lấy **các bit thấp của khoảng dịch**, không phải cơ chế kiểm tra `n <= 31` hay `n <= 63` rồi từ chối trường hợp vượt giới hạn.

## 3. Số lượng dịch âm vẫn được mask

Java **không báo lỗi** chỉ vì số lượng dịch âm; số nguyên âm cũng có dạng bit, và Java vẫn lấy các bit thấp:

~~~java
int intEffective = -1 & 0x1F;  // 31
long longEffective = -1 & 0x3F; // 63

int highInt = 1 << -1;   // như 1 << 31: -2147483648
long highLong = 1L << -1; // như 1L << 63: -9223372036854775808
~~~

| Biểu thức | Số lượng dịch hiệu lực | Kết quả |
| --- | ---: | ---: |
| `1 << 0` | 0 | 1 |
| `1 << 31` | 31 | -2147483648 |
| `1 << 32` | 0 | 1 |
| `1 << 33` | 1 | 2 |
| `1 << -1` | 31 | -2147483648 |
| `1L << 32` | 32 | 4294967296 |
| `1L << 63` | 63 | -9223372036854775808 |
| `1L << 64` | 0 | 1 |
| `1L << -1` | 63 | -9223372036854775808 |

Không nên dùng mask tự động của toán tử dịch làm cách “kiểm tra hợp lệ” input. Nếu nghiệp vụ quy định chỉ chấp nhận `0 <= n && n < 32` hoặc `0 <= n && n < 64` thì **kiểm tra trước** rồi mới dịch; nếu không, input bất thường có thể âm thầm biến thành một khoảng dịch khác.

## 4. Kiểu toán hạng **trái** quyết định độ rộng, không phải biến nhận kết quả

Hai toán hạng của toán tử dịch được áp dụng *unary numeric promotion* riêng biệt. Kiểu của **toán hạng trái đã nâng kiểu** là kiểu kết quả; toán hạng phải chỉ cung cấp số lượng dịch.

~~~java
int x = 1;

long tooLate = x << 40;        // int dịch 40 -> 40 & 31 = 8 -> 256
long correct = ((long) x) << 40; // long dịch đúng 40 -> 1099511627776
~~~

`tooLate` có kiểu `long` ở **biến đích**, nhưng phép dịch được thực hiện bằng `int` trước khi gán. Kể cả `(long) (x << 40)` cũng chuyển kiểu **sau phép dịch**, nên vẫn cho 256.

Dùng `1L` hoặc cast bên trái **trước phép dịch** khi cần dãy 64 bit:

~~~java
long bit40 = 1L << 40;    // 1099511627776
long bit40b = (long) 1 << 40; // cùng kết quả
~~~

Kiểu **toán hạng phải** không nâng kiểu kết quả bên trái thành `long`:

~~~java
int value = 1;
long distance = 33L;
int shifted = value << distance; // 2: 33 & 31 = 1
~~~

**Kết luận:** Trong phép `left << distance`, hãy nhìn vào **kiểu left**, không nhìn kiểu của `distance` hay kiểu biến đích.

## 5. `byte`, `short`, `char` được nâng thành `int`

Dù `byte` có 8 bit, `short`/`char` có 16 bit, phép dịch vẫn dùng **quy tắc 32 bit** vì toán hạng trái được nâng thành `int` trước phép toán:

~~~java
byte small = 1;
short brief = 1;
char ch = 1;

int a = small << 8;  // 256, không phải 0
int b = brief << 16; // 65536
int c = ch << 32;    // 1, vì 32 & 31 = 0
~~~

Dòng `byte result = small << 8;` không biên dịch khi `small` là biến: biểu thức có kiểu `int`, không được gán ngầm vào `byte`. Nếu ép về `byte` sau phép dịch, giá trị có thể bị cắt mất các bit cao:

~~~java
byte narrowed = (byte) (small << 8); // 0
~~~

Đừng nghĩ “dịch byte quá 8 bit nên bị mask theo 8” — phép dịch trả `int`; chỉ khi cast về `byte` mới bị thu hẹp về 8 bit.

## 6. Quy tắc mask áp dụng cho cả `<<`, `>>`, `>>>`

Không chỉ phép dịch trái: cả ba toán tử đều dùng quy tắc 5/6 bit thấp của số lượng dịch.

~~~java
int x = -8;
int signed = x >> 33;   // -4, vì 33 & 31 = 1
int unsigned = x >>> 33; // 2147483644, cũng dịch 1 bit
~~~

`>>` giữ bit dấu khi dịch phải; `>>>` điền bit 0 từ bên trái. Chúng có thể cho kết quả rất khác nhau khi `x` âm, nhưng **quy tắc giới hạn số lượng dịch là giống nhau**.

| Biểu thức | Kết quả | Vì sao |
| --- | ---: | --- |
| `-8 >> 1` | -4 | Dịch phải số âm và giữ dấu |
| `-8 >> 33` | -4 | 33 trở thành 1 |
| `-8 >>> 1` | 2147483644 | Điền 0 từ bên trái |
| `-8 >>> 33` | 2147483644 | 33 trở thành 1 |
| `1 >>> 32` | 1 | 32 trở thành 0 |
| `1L >>> 64` | 1 | 64 trở thành 0 |

Điều này không đồng nghĩa với các phép dịch “không thể mất bit”. Phép dịch trái có thể đẩy bit cao ra khỏi miền biểu diễn, dẫn tới kết quả âm hoặc mất dữ liệu; Java không tự ném ngoại lệ tràn số vì phép dịch.

## 7. Chương trình Java 17+ runnable

Tạo file **ShiftDistanceDemo.java**:

~~~java
public final class ShiftDistanceDemo {
    public static void main(String[] args) {
        int one = 1;
        long wide = 1L;

        System.out.println("int31=" + (one << 31));
        System.out.println("int32=" + (one << 32));
        System.out.println("int33=" + (one << 33));
        System.out.println("intMinusOne=" + (one << -1));

        System.out.println("long32=" + (wide << 32));
        System.out.println("long63=" + (wide << 63));
        System.out.println("long64=" + (wide << 64));
        System.out.println("long65=" + (wide << 65));
        System.out.println("longMinusOne=" + (wide << -1));

        long tooLate = one << 40;
        long correct = ((long) one) << 40;
        System.out.println("lateWiden=" + tooLate);
        System.out.println("earlyWiden=" + correct);

        long distance = 33L;
        int intWithLongDistance = one << distance;
        System.out.println("longDistanceOnInt=" + intWithLongDistance);

        byte small = 1;
        short brief = 1;
        char ch = 1;
        System.out.println("byteShift=" + (small << 8));
        System.out.println("shortShift=" + (brief << 16));
        System.out.println("charShift32=" + (ch << 32));
        System.out.println("narrowedByte=" + (byte) (small << 8));

        int negative = -8;
        System.out.println("signedRight33=" + (negative >> 33));
        System.out.println("unsignedRight33=" + (negative >>> 33));
        System.out.println("unsignedNoShift=" + (one >>> 32));
        System.out.println("longUnsignedNoShift=" + (wide >>> 64));

        System.out.println("maskedIntMinusOne=" + (-1 & 0x1F));
        System.out.println("maskedLongMinusOne=" + (-1 & 0x3F));
    }
}
~~~

Mở terminal trong thư mục chứa file và chạy (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 ShiftDistanceDemo.java
java ShiftDistanceDemo
~~~

**Expected stdout chính xác:**

~~~text
int31=-2147483648
int32=1
int33=2
intMinusOne=-2147483648
long32=4294967296
long63=-9223372036854775808
long64=1
long65=2
longMinusOne=-9223372036854775808
lateWiden=256
earlyWiden=1099511627776
longDistanceOnInt=2
byteShift=256
shortShift=65536
charShift32=1
narrowedByte=0
signedRight33=-4
unsignedRight33=2147483644
unsignedNoShift=1
longUnsignedNoShift=1
maskedIntMinusOne=31
maskedLongMinusOne=63
~~~

Các dòng `int32=1` và `long64=1` cho thấy Java **mask số lượng dịch**, không dừng ở biên 32/64. `lateWiden=256` và `earlyWiden=1099511627776` chứng minh cần chuyển kiểu bên trái trước phép dịch. Các dòng `byteShift`, `shortShift` và `charShift32` chứng minh `byte`/`short`/`char` sử dụng quy tắc `int`.

## 8. Checklist và bài tập

| Nếu cần... | Hãy nhớ... |
| --- | --- |
| Dịch `int` | Số lượng dịch hiệu lực `n & 0x1F` |
| Dịch `long` | Số lượng dịch hiệu lực `n & 0x3F` |
| Dịch `byte`/`short`/`char` | Trái được nâng thành `int` trước phép dịch |
| Lấy bit thứ 40 | Dùng `1L << 40`, không phải `1 << 40` |
| Kiểm tra input số lượng dịch | Kiểm tra miền cụ thể trước khi thực hiện phép dịch |
| Dịch phải số âm | Phân biệt `>>` giữ dấu và `>>>` điền 0 |

**Bài 1.** Dự đoán `1 << 32`, `1 << 33`, `1L << 32`, `1L << 64`. Giải thích vì sao kết quả khác nhau theo kiểu toán hạng bên trái.

**Bài 2.** So sánh `long x = 1 << 40;` và `long y = 1L << 40;`. Vì sao chỉ một cách thực sự dịch 40 bit của `long`?

**Bài 3.** Cho `byte b = 1;`. Tính `b << 8`, nêu kiểu kết quả, rồi giải thích `(byte)(b << 8)`.

**Bài 4.** Với `int n = -8;`, tính `n >> 33` và `n >>> 33`. Hai phép dùng khoảng dịch hiệu lực nào?

**Bài 5.** Nếu hệ thống yêu cầu số bit dịch từ 0 đến 31, vì sao không nên chỉ dùng `value << userCount` mà không validate `userCount`?

### Ghi nhớ

**Java chỉ dùng 5 bit thấp của số lượng dịch cho `int` và 6 bit thấp cho `long`.** `byte`, `short`, `char` nâng thành `int` trước phép dịch. Quy tắc áp dụng cho cả `<<`, `>>`, `>>>`, kể cả số lượng dịch âm hoặc vượt độ rộng; chúng không tự báo lỗi. Nếu cần 64 bit, hãy làm cho **toán hạng trái** là `long` trước phép dịch.
