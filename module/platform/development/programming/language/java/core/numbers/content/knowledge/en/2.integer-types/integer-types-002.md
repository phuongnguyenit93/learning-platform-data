# Kích thước bit và miền giá trị của từng kiểu số nguyên trong Java

## 1. Vì sao phải biết độ rộng bit và miền giá trị?

Mỗi kiểu số nguyên nguyên thủy (*primitive integral type*) trong Java có **độ rộng bit cố định**. Độ rộng đó quyết định có bao nhiêu mẫu bit khác nhau, và cách Java diễn giải các bit quyết định **giá trị nhỏ nhất/lớn nhất** có thể lưu.

Ví dụ, 8 bit có \(2^8 = 256\) tổ hợp. Nếu dùng kiểu có dấu `byte`, Java dành các tổ hợp ấy cho các giá trị từ **-128 đến 127**, chứ không phải từ 0 đến 255. Hiểu quy tắc này giúp:

- Chọn kiểu phù hợp cho dữ liệu, tránh vô tình vượt miền.
- Giải thích vì sao phép toán có thể **tràn số** (*overflow*) và cho kết quả bất ngờ.
- Hiểu chuyển kiểu (*casting*), phép toán bit và dữ liệu nhị phân.
- Phân biệt một **kiểu nguyên thủy** với đối tượng lớp bao (*wrapper*).

Bài học này xét các kiểu nguyên thủy tích phân `byte`, `short`, `int`, `long` và `char`. Bốn kiểu đầu là số nguyên **có dấu**; `char` là một giá trị tích phân **không dấu** dùng làm đơn vị mã UTF-16. `boolean` chỉ nhận `true/false` nên không thuộc bảng số nguyên.

## 2. Bảng độ rộng và miền giá trị

| Kiểu | Số bit | Số byte | Giá trị nhỏ nhất | Giá trị lớn nhất | Số giá trị khác nhau |
|---|---:|---:|---:|---:|---:|
| `byte` | 8 | 1 | -128 | 127 | \(2^8 = 256\) |
| `short` | 16 | 2 | -32_768 | 32_767 | \(2^{16} = 65\,536\) |
| `int` | 32 | 4 | -2_147_483_648 | 2_147_483_647 | \(2^{32}\) |
| `long` | 64 | 8 | -9_223_372_036_854_775_808 | 9_223_372_036_854_775_807 | \(2^{64}\) |
| `char` | 16 | 2 | 0 (U+0000) | 65_535 (U+FFFF) | \(2^{16} = 65\,536\) |

**Đây là độ rộng được đặc tả bởi Java**, giống nhau trên JVM 32 bit hoặc 64 bit. Một `int` của Java luôn có 32 bit, không phụ thuộc kích thước `int` trong ngôn ngữ C trên nền tảng khác.

Độ rộng tính theo bit của kiểu nguyên thủy cũng **không đồng nghĩa** với kích thước một đối tượng `Integer` hoặc `Long` trên heap. Đối tượng có header, căn chỉnh và overhead khác; không thể lấy 32 bit để kết luận đối tượng `Integer` dùng 4 byte bộ nhớ.

Trong Java, 1 byte gồm 8 bit. Các lớp bao công bố hằng số tương ứng: `Byte.SIZE/BYTES`, `Short.SIZE/BYTES`, `Integer.SIZE/BYTES`, `Long.SIZE/BYTES`, `Character.SIZE/BYTES`; miền giá trị nằm ở `MIN_VALUE` và `MAX_VALUE`. Các hằng số này hữu ích để tra cứu, nhưng điều cốt lõi là hiểu **cách tính và ý nghĩa** của chúng.

## 3. Suy ra miền giá trị từ số bit

### 3.1. Kiểu có dấu: số bù hai (*two's complement*)

Với kiểu có dấu rộng **n bit** (`byte`, `short`, `int`, `long`), Java dùng biểu diễn số bù hai. Miền giá trị là:

\[
\boxed{-2^{n-1} \le x \le 2^{n-1}-1}
\]

- **Giới hạn dưới**: \(-2^{n-1}\).
- **Giới hạn trên**: \(2^{n-1}-1\).
- **Số giá trị biểu diễn được**: \(2^n\), kể cả số 0.

Áp dụng cho `byte` (\(n=8\)): \(-2^7=-128\) tới \(2^7-1=127\).

Áp dụng cho `short` (\(n=16\)): \(-2^{15}=-32\,768\) tới \(2^{15}-1=32\,767\).

Áp dụng cho `int` (\(n=32\)): \(-2^{31}\) tới \(2^{31}-1\).

Áp dụng cho `long` (\(n=64\)): \(-2^{63}\) tới \(2^{63}-1\).

**Tại sao trị tuyệt đối giới hạn âm lớn hơn giới hạn dương một đơn vị?** Vì 0 chiếm một giá trị trong tập không âm. Ví dụ với `byte` có 128 giá trị âm (-128 đến -1) và 128 giá trị không âm (0 đến 127). Do đó không có giá trị `byte` dương +128 để đối xứng với -128.

### 3.2. Nhìn mẫu bit 8 bit

Với `byte`, một số ví dụ:

| Mẫu bit (8 bit) | Cách hiểu `byte` có dấu |
|---|---:|
| `0000 0000` | 0 |
| `0000 0001` | 1 |
| `0111 1111` | 127 |
| `1000 0000` | -128 |
| `1111 1111` | -1 |

Bit cao nhất có trọng số \(-2^7\) trong biểu diễn bù hai 8 bit, các bit còn lại có trọng số \(2^6,\ldots,2^0\). Vì vậy `1000 0000` là -128; `1111 1111` là \(-128+64+32+16+8+4+2+1=-1\).

Cách nhớ thực hành: đổi dấu theo bù hai bằng **đảo các bit rồi cộng 1, trong đúng độ rộng n bit**. Ví dụ, 8 bit của +1 là `0000 0001`; đảo bit thành `1111 1110`, cộng 1 được `1111 1111` tức -1.

Trong Java, kết quả của các biểu thức bit trên `byte` thường được **thăng cấp lên `int`**, nên khi thực hành đảo bit `~` phải xét độ rộng và phép ép kiểu. Không suy diễn `~((byte)1)` sẽ tự giữ đúng 8 bit: biểu thức đó có kiểu `int`.

### 3.3. `char`: 16 bit nhưng không có dấu

`char` có 16 bit, nhưng miền giá trị là:

\[
0 \le \texttt{char} \le 2^{16}-1 = 65535
\]

Nó đại diện một **UTF-16 code unit**, không phải số nguyên có dấu 16 bit như `short`. Do đó hai kiểu cùng rộng 16 bit nhưng có miền khác nhau:

- `short`: -32_768 tới 32_767.
- `char`: 0 tới 65_535.

Một ký tự Unicode nằm ngoài Basic Multilingual Plane (BMP), chẳng hạn emoji, cần **cặp surrogate gồm hai `char`**. Vì vậy một Unicode code point không nhất thiết khớp một `char`. Đếm ký tự theo code point có thể dùng `String.codePointCount(...)` hoặc `String.codePoints()`, thay vì mặc định `String.length()` là số ký tự hiển thị.

## 4. Chạy Java để quan sát

Tạo file `PrimitiveRangeDemo.java`:

```java
public class PrimitiveRangeDemo {
    public static void main(String[] args) {
        System.out.printf("byte: %d..%d (%d bits)%n",
                Byte.MIN_VALUE, Byte.MAX_VALUE, Byte.SIZE);
        System.out.printf("short: %d..%d (%d bits)%n",
                Short.MIN_VALUE, Short.MAX_VALUE, Short.SIZE);
        System.out.printf("int: %d..%d (%d bits)%n",
                Integer.MIN_VALUE, Integer.MAX_VALUE, Integer.SIZE);
        System.out.printf("long: %d..%d (%d bits)%n",
                Long.MIN_VALUE, Long.MAX_VALUE, Long.SIZE);
        System.out.printf("char: %d..%d (%d bits)%n",
                (int) Character.MIN_VALUE, (int) Character.MAX_VALUE,
                Character.SIZE);

        System.out.println("int bytes: " + Integer.BYTES);
        System.out.println("char bytes: " + Character.BYTES);
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac PrimitiveRangeDemo.java
java PrimitiveRangeDemo
```

Kết quả:

```text
byte: -128..127 (8 bits)
short: -32768..32767 (16 bits)
int: -2147483648..2147483647 (32 bits)
long: -9223372036854775808..9223372036854775807 (64 bits)
char: 0..65535 (16 bits)
int bytes: 4
char bytes: 2
```

Hai phép ép `(int)` ở dòng `char` nhằm in **giá trị số** của code unit. Nếu in `Character.MIN_VALUE` trực tiếp như ký tự, bạn có thể nhận một ký tự điều khiển không nhìn thấy.

## 5. Khi vượt miền giá trị: tràn và ép kiểu

### 5.1. Tràn số trong phép tính

Một `int` chỉ lưu được đến 2_147_483_647. Khi cộng thêm 1 bằng phép cộng `int`, kết quả quay về -2_147_483_648 theo số học modulo \(2^{32}\). Phép cộng số nguyên thông thường **không tự ném ngoại lệ**.

Cần phân biệt hai thời điểm mở rộng sang `long`:

- `(long) (max + 1)`: phép cộng **đã chạy bằng `int` và tràn** trước khi đổi kiểu.
- `(long) max + 1`: `max` được đổi thành `long` **trước phép cộng**, nên đủ miền biểu diễn.

### 5.2. Thu hẹp kiểu (*narrowing conversion*)

Ép `int` 128 sang `byte` giữ 8 bit thấp của giá trị, diễn giải lại theo miền có dấu 8 bit và cho **-128**. Ép kiểu trực tiếp không kiểm tra miền để ném lỗi.

Với gán hằng số, trình biên dịch có thể cho phép gán trực tiếp `byte b = 127;` vì 127 nằm trong miền `byte`; nhưng `byte b = 128;` là lỗi biên dịch vì vượt miền, trừ khi bạn chủ động ép kiểu.

### 5.3. Ví dụ có thể chạy

Tạo file `BoundaryDemo.java`:

```java
public class BoundaryDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;

        System.out.println("int max + 1 = " + (max + 1));
        System.out.println("widen after = " + (long) (max + 1));
        System.out.println("widen before = " + ((long) max + 1));
        System.out.println("(byte) 128 = " + (byte) 128);
        System.out.println("byte max + 1 = " + (Byte.MAX_VALUE + 1));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException e) {
            System.out.println("addExact: overflow");
        }

        long outsideInt = 2_147_483_648L;
        try {
            System.out.println(Math.toIntExact(outsideInt));
        } catch (ArithmeticException e) {
            System.out.println("toIntExact: out of int range");
        }
    }
}
```

Chạy:

```bash
javac BoundaryDemo.java
java BoundaryDemo
```

Kết quả:

```text
int max + 1 = -2147483648
widen after = -2147483648
widen before = 2147483648
(byte) 128 = -128
byte max + 1 = 128
addExact: overflow
toIntExact: out of int range
```

`Byte.MAX_VALUE + 1` in ra 128 vì toán tử cộng **thăng cấp `byte` thành `int`**, nên kết quả phép cộng có kiểu `int`. Tràn 8 bit chỉ xuất hiện nếu ép kết quả về `byte` hoặc tính trực tiếp trong một kiểu bị thu hẹp.

Các phương thức `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.negateExact` và `Math.toIntExact` giúp phát hiện trường hợp tràn/ngoài miền liên quan. Chúng ném `ArithmeticException` ở trường hợp không biểu diễn được.

## 6. Ký hiệu số nguyên và các giới hạn cần nhớ

### 6.1. Literal `int` và `long`

Mặc định, literal số nguyên thập phân không có hậu tố là `int` khi hợp lệ; thêm `L` để viết `long`:

```java
int population = 2_000_000_000;
long bigger = 3_000_000_000L;
long maximum = Long.MAX_VALUE;
```

Viết `3_000_000_000` không có hậu tố `L` gây lỗi vì vượt phạm vi literal `int`, ngay cả khi vế trái khai báo `long`. Gạch dưới trong số chỉ giúp dễ đọc; không đổi giá trị hay kiểu.

Hai trị âm thấp nhất `-2147483648` và `-9223372036854775808L` có quy tắc từ vựng đặc biệt trong Java cho toán tử trừ đơn ngôi; để tránh nhầm lẫn, ưu tiên `Integer.MIN_VALUE` và `Long.MIN_VALUE` trong mã ứng dụng.

### 6.2. Một số bẫy ở biên

- `Math.abs(Integer.MIN_VALUE)` vẫn bằng `Integer.MIN_VALUE`, tức số âm, vì +2_147_483_648 vượt miền `int`. Tương tự cho `Long.MIN_VALUE`.
- `-Integer.MIN_VALUE` vẫn bằng `Integer.MIN_VALUE` do tràn khi đổi dấu.
- `Integer.MIN_VALUE / -1` trả lại `Integer.MIN_VALUE` vì thương dương không thể biểu diễn trong `int`.
- Chuyển biểu thức sang `long` **sau khi phép tính tràn** không khôi phục được kết quả ban đầu.
- `SIZE/BYTES` thể hiện độ rộng **giá trị nguyên thủy**, không cho biết tổng bộ nhớ mảng, wrapper object hay cấu trúc dữ liệu (còn phụ thuộc overhead, căn chỉnh và VM).

Nếu số nguyên có thể vượt miền `long`, dùng `java.math.BigInteger`. Nó không có một độ rộng cố định kiểu 64 bit, nên không có miền MIN/MAX cố định tương tự các kiểu nguyên thủy.

## 7. Có kiểu `unsigned int` và `unsigned long` không?

Java **không có kiểu nguyên thủy riêng tên `unsigned int` hay `unsigned long`**. Tuy vậy, Java hỗ trợ các phép toán *diễn giải mẫu bit* dưới góc nhìn không dấu:

- 32 bit không dấu có miền **0 đến 4_294_967_295**, tức \(0\) đến \(2^{32}-1\).
- 64 bit không dấu có miền **0 đến 18_446_744_073_709_551_615**, tức \(0\) đến \(2^{64}-1\); giá trị cao nhất này vượt miền `long` có dấu.
- Các API hỗ trợ gồm `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedLong`, `Integer.toUnsignedString`, cùng các phương thức `Long.compareUnsigned`, `Long.divideUnsigned`, `Long.toUnsignedString`.

Ví dụ:

```java
System.out.println(Integer.toUnsignedLong(-1));
System.out.println(Integer.toUnsignedString(-1));
```

Cả hai dòng in ra `4294967295`. Mẫu bit `0xFFFF_FFFF` có thể hiểu là -1 nếu diễn giải theo `int` có dấu, hoặc 4_294_967_295 nếu diễn giải theo 32 bit không dấu. Các API unsigned **không thay đổi độ rộng 32 bit hoặc 64 bit** của giá trị lưu trong biến.

Riêng `char` vốn là kiểu không dấu 16 bit, dùng cho code unit UTF-16; đừng dùng `char` để thay thế số nguyên không dấu thông thường chỉ vì cùng độ rộng `short`.

## 8. Chọn kiểu cho dữ liệu và kiểm tra đầu vào

**`byte`** phù hợp khi cần biểu diễn các giá trị trong -128..127 hoặc thao tác byte nhị phân. Khi muốn giá trị 0..255 từ một byte nhị phân, xem `Byte.toUnsignedInt(...)` hoặc `b & 0xFF`.

**`short`** phù hợp khi một API, định dạng tệp hoặc giao thức quy định chính xác 16 bit có dấu; trong tính toán nghiệp vụ thông thường, `int` đơn giản và phổ biến hơn.

**`int`** là lựa chọn thường gặp cho chỉ số, biến đếm và số nguyên 32 bit có giới hạn rõ ràng. Với chỉ số mảng Java, `int` là kiểu cơ bản hay dùng; kích thước mảng còn bị giới hạn bởi JVM/bộ nhớ, không chỉ bởi `Integer.MAX_VALUE`.

**`long`** dùng khi cần miền lớn hơn, như số đếm lớn, mili giây từ mốc thời gian hoặc lượng dữ liệu có thể vượt 32 bit. Dù vậy, `long` cũng hữu hạn: nếu phép tính có nguy cơ vượt 64 bit, cân nhắc `BigInteger` hoặc quy tắc kiểm tra tràn.

**`char`** dùng khi làm việc ở mức đơn vị mã UTF-16; nếu yêu cầu xử lý **Unicode code point**, chọn API duyệt code point để tránh chia đôi surrogate pair.

Khi nhận dữ liệu từ bên ngoài rồi ép sang kiểu hẹp, kiểm tra giá trị trước khi đổi kiểu:

```java
static byte requireByteRange(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("outside byte range");
    }
    return (byte) value;
}
```

Đây là **đoạn phương thức minh họa** (đặt trong một class để dùng), không phải chương trình có `main` độc lập. Điểm chính là phải kiểm tra **trước** khi ép kiểu: nếu ép trước, dữ liệu có thể đã mất bit quan trọng.

## 9. Tự kiểm tra kiến thức

1. **8 bit có bao nhiêu mẫu bit?** — \(2^8=256\) mẫu.
2. **Vì sao `byte` có miền -128..127 thay vì -127..127?** — Theo số bù hai, 8 bit mã hóa 128 giá trị âm và 128 giá trị không âm; số 0 đã chiếm một mẫu.
3. **`short` và `char` cùng 16 bit, miền có giống nhau không?** — Không. `short` có dấu: -32_768..32_767; `char` không dấu: 0..65_535.
4. **`int` 32 bit có thể chứa giá trị 3_000_000_000 không?** — Không dưới cách diễn giải có dấu. Có thể dùng `long` hoặc diễn giải mẫu bit unsigned bằng API tương ứng.
5. **Vì sao `long result = Integer.MAX_VALUE + 1;` vẫn nhận kết quả âm?** — Hai toán hạng được cộng bằng `int` trước, gây tràn; kết quả âm sau đó mới được mở rộng sang `long`. Dùng `long result = (long) Integer.MAX_VALUE + 1;`.
6. **Một emoji có bắt buộc chỉ chiếm 1 `char` vì `char` là 16 bit?** — Không. Unicode code point ngoài BMP thường cần hai code unit UTF-16, tức hai `char`.
7. **`long` có bảo đảm mọi số nguyên đều lưu được?** — Không. Miền của `long` có dấu chỉ từ \(-2^{63}\) đến \(2^{63}-1\); số lớn hơn cần cách biểu diễn khác như `BigInteger`.

**Cốt lõi:** Độ rộng **n bit** cho \(2^n\) mẫu bit; với kiểu **có dấu**, miền là \([-2^{n-1},2^{n-1}-1]\); với `char` **không dấu 16 bit**, miền là \([0,2^{16}-1]\). Luôn xác định **kiểu thực sự tham gia phép tính** trước khi suy luận về tràn số hoặc chuyển kiểu.
