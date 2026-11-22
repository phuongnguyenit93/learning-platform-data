# Literal nhị phân và cách đọc biểu diễn bit trong Java

## 1. Literal nhị phân là gì?

**Literal nhị phân (binary integer literal)** là cách viết một số nguyên trực tiếp trong mã Java bằng các chữ số `0` và `1`. Tiền tố `0b` hoặc `0B` cho trình biên dịch biết các chữ số theo sau ở **cơ số 2**, thay vì cơ số 10.

```java
int a = 0b1010;          // 10 ở hệ thập phân
int b = 0B1010_0101;     // 165 ở hệ thập phân
long c = 0b1_0000_0000L; // 256L, hậu tố L cho kiểu long
```

Ba cách viết `10`, `0b1010` và `0xA` biểu diễn **cùng giá trị số nguyên**; chúng khác cách trình bày tại mã nguồn. Java hỗ trợ cú pháp `0b` từ Java 7 và cú pháp này vẫn dùng bình thường trên các phiên bản Java hiện đại, bao gồm Java 17+.

Dùng literal nhị phân khi muốn cho người đọc thấy trực tiếp từng bit: cờ trạng thái (flags), mask, giao thức nhị phân, cấu hình thanh ghi, quyền truy cập hoặc định dạng dữ liệu. Với phép tính nghiệp vụ thông thường, viết số thập phân thường dễ đọc hơn.

## 2. Quy tắc cú pháp cần nhớ

- Chỉ viết chữ số `0` và `1` sau `0b`/`0B`. Ví dụ `0b102` **không hợp lệ**.
- Có thể chèn dấu gạch dưới `_` **giữa các chữ số** để phân nhóm: `0b1101_0010`. Dấu `_` là ký hiệu giúp đọc, **không ảnh hưởng giá trị**. Không đặt `_` sát sau tiền tố, ở cuối literal hoặc trước hậu tố `L`.
- Không có literal số thực nhị phân kiểu `0b1.01`. Cú pháp này dành cho số nguyên.
- Literal nhị phân thông thường có kiểu `int` (32 bit). Thêm `L` để có kiểu `long` (64 bit); nên dùng `L` viết hoa để tránh nhầm chữ `l` với số `1`.
- Dấu âm là toán tử một ngôi đặt **trước** literal: `-0b101` có giá trị `-5`; tiền tố `0b` tự nó không có dấu.
- Có thể gán hằng số `int` cho `byte`, `short` hoặc `char` khi giá trị hằng nằm trong miền của kiểu đích; ngoài miền phải chọn kiểu lớn hơn hoặc ép kiểu có chủ đích.

```java
byte maxByte = 0b0111_1111; // 127: hợp lệ
char letterA = 0b0100_0001; // 65: đơn vị mã UTF-16 cho 'A'
long big = 0b1_0000_0000_0000_0000_0000_0000_0000_0000L; // 2^32

// byte invalid = 0b1000_0000; // Lỗi biên dịch: 128 vượt miền byte
byte wrapped = (byte) 0b1000_0000; // -128: ép kiểu làm giữ 8 bit thấp
```

Đối với literal `int` không phải hệ thập phân, đủ 32 bit có thể biểu diễn cả mẫu bit có bit cao nhất bằng `1`; tương tự, literal `long` đủ 64 bit có thể biểu diễn cả mẫu bit âm. Ví dụ `0b11111111_11111111_11111111_11111111` là số `int` bằng `-1`. Ngược lại, `0b1111_1111` chỉ có tám chữ số nhị phân và là `int` bằng `255`. **Độ rộng kiểu dữ liệu và số chữ số viết ra là hai điều khác nhau.**

## 3. Cách đọc một dãy bit thành giá trị số

Trong hệ nhị phân, mỗi vị trí tính từ phải sang trái có trọng số `2^n`, bắt đầu với `n = 0` ở bit ngoài cùng bên phải (bit ít quan trọng nhất, **LSB**). Ví dụ:

```text
  0b1010_0101
    |||| ||||
    7654 3210   ← chỉ số bit
```

| Vị trí bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Trọng số | 128 | 64 | 32 | 16 | 8 | 4 | 2 | 1 |
| Bit của `1010_0101` | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 1 |

Các bit bằng `1` đóng góp `128 + 32 + 4 + 1 = 165`. Vì vậy `0b1010_0101` bằng `165`.

Để đọc một mask, có thể đi theo chiều ngược lại: ví dụ cần đặt các bit 7, 5, 2, 0 thành `1` thì viết `0b1010_0101`. Dấu gạch dưới nhóm 4 bit giúp so sánh với từng chữ số hex: `1010 0101` tương ứng `0xA5`.

Trong một giá trị nguyên có độ rộng `w`, các bit được đánh số `0` đến `w - 1`. Bit 0 có trọng số `1`; bit 31 là bit cao nhất của `int`; bit 63 là bit cao nhất của `long`.

## 4. Độ rộng kiểu dữ liệu và số âm: bù hai

Java dùng biểu diễn **bù hai (two's complement)** cho các kiểu số nguyên có dấu. Độ rộng cố định quyết định bit nào là bit dấu và cách mẫu bit được diễn giải.

| Kiểu Java | Độ rộng | Diễn giải |
| --- | --- | --- |
| `byte` | 8 bit | Có dấu, từ -128 đến 127 |
| `short` | 16 bit | Có dấu, từ -32768 đến 32767 |
| `char` | 16 bit | Không dấu, từ 0 đến 65535; là đơn vị mã UTF-16 |
| `int` | 32 bit | Có dấu, từ -2^31 đến 2^31 - 1 |
| `long` | 64 bit | Có dấu, từ -2^63 đến 2^63 - 1 |

Với `byte` 8 bit, để biểu diễn `-5` bằng bù hai, lấy `5` là `0000_0101`, đảo từng bit thành `1111_1010`, rồi cộng `1` thành `1111_1011`. Mẫu này khi **diễn giải như byte có dấu** là `-5`, nhưng cùng tám chữ số `0b1111_1011` khi viết thành literal `int` lại là `251`.

```java
int positive = 0b1111_1011;          // 251
byte negative = (byte) 0b1111_1011; // -5, chỉ giữ 8 bit thấp
int minusFive = -0b101;             // -5 kiểu int

// byte b = 0b1111_1011;            // Lỗi: 251 không nằm trong [-128, 127]
```

Khi `byte` hoặc `short` tham gia các phép toán số nguyên, Java thường **nâng lên `int` trước khi tính**. Với giá trị âm, quá trình này mở rộng bit dấu. Bởi vậy, muốn xem đúng 8 bit thấp của một `byte`, hãy dùng `b & 0xFF`; muốn xem 16 bit thấp của `short`, dùng `s & 0xFFFF`.

Đừng mặc định rằng một chuỗi bit có bit đầu là `1` thì luôn mang giá trị âm: `0b1000_0000` là `int` dương 128, nhưng cùng tám bit đó khi ép thành `byte` có dấu là -128. Java không có kiểu nguyên nguyên thủy `unsigned int` hay `unsigned long`; các phương thức `Integer`/`Long` hỗ trợ diễn giải không dấu khi cần.

## 5. Chạy thử chương trình Java 17+

Lưu mã sau vào tệp **`BinaryLiteralDemo.java`**.

```java
public final class BinaryLiteralDemo {
    public static void main(String[] args) {
        int value = 0b1010_0101;
        long count = 0B1_0000_0000L;
        int allOnes = 0b11111111_11111111_11111111_11111111;
        byte signedByte = (byte) 0b1111_1011;

        System.out.println(value);
        System.out.println(count);
        System.out.println(allOnes);
        System.out.println(signedByte);
        System.out.println(Integer.toBinaryString(value));
        System.out.println(Integer.toBinaryString(signedByte & 0xFF));
    }
}
```

Biên dịch và chạy:

```bash
javac BinaryLiteralDemo.java
java BinaryLiteralDemo
```

Stdout chính xác:

```text
165
256
-1
-5
10100101
11111011
```

Giải thích: `count` có hậu tố `L` nên là `long`; `allOnes` có 32 bit bằng `1` nên là `int` bù hai `-1`; `signedByte` chỉ giữ tám bit thấp rồi được diễn giải thành `-5`. Phương thức `Integer.toBinaryString` trả về chuỗi nhị phân **không có tiền tố `0b`**. Phép `& 0xFF` ngăn mở rộng bit dấu ảnh hưởng tới kết quả hiển thị của `byte` âm.

## 6. Đọc và thao tác bit bằng các toán tử

Giả sử `a = 0b1100` (12) và `b = 0b1010` (10). Các toán tử thao tác trên **bit của các toán hạng**, không phụ thuộc việc các số đã được viết bằng hệ nhị phân hay thập phân trong mã nguồn.

| Biểu thức | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `a & b` | `0b1000` = 8 | AND: bit bằng 1 khi cả hai bit đều bằng 1 |
| `a \| b` | `0b1110` = 14 | OR: bit bằng 1 khi ít nhất một bit bằng 1 |
| `a ^ b` | `0b0110` = 6 | XOR: bit bằng 1 khi hai bit khác nhau |
| `~a` | `-13` | NOT: đảo **toàn bộ 32 bit** của `int` |
| `a << 1` | `0b11000` = 24 | Dịch trái một vị trí, bit trống điền 0 |
| `a >> 1` | `0b0110` = 6 | Dịch phải số học, giữ bit dấu |
| `a >>> 1` | `0b0110` = 6 | Dịch phải logic, điền 0 từ trái |

**Lưu ý:** ký hiệu `~` không chỉ đảo bốn chữ số `1100` nhìn thấy ở source; `a` vẫn là `int` 32 bit. Bởi vậy `~12 == -13`. Nếu chỉ muốn giữ bốn bit thấp, dùng `(~a) & 0b1111`, kết quả là `0b0011`.

Với số âm, `>>` và `>>>` rất khác nhau:

```java
int n = -8;
System.out.println(n >> 1);  // -4: điền bit dấu 1 từ trái
System.out.println(n >>> 1); // 2147483644: điền bit 0 từ trái
```

Khi dịch `byte`/`short`, toán hạng được nâng lên `int`; vì vậy `>>>` trên một `byte` âm sẽ xử lý **32 bit**, không tự tạo phép dịch 8 bit. Nếu cần dịch trên một byte như dữ liệu 8 bit không dấu, hãy mask trước, chẳng hạn `(b & 0xFF) >>> 1`.

Số vị trí dịch của `int` thực tế lấy 5 bit thấp của toán hạng bên phải (`& 31`), còn `long` lấy 6 bit thấp (`& 63`). Vì vậy `1 << 32` bằng `1`, **không phải** `2^32`; để tạo bit thứ 32, dùng `1L << 32`. Các phép dịch cũng có thể làm mất bit cao hoặc thay đổi dấu nếu vượt độ rộng kiểu.

## 7. Ví dụ thực tế: mask quyền và kiểm tra từng cờ

Một trường hợp phù hợp với biểu diễn bit là tập quyền nhỏ, mỗi quyền ứng với **một bit riêng**:

```java
int READ = 0b0001;
int WRITE = 0b0010;
int EXECUTE = 0b0100;

int permissions = READ | WRITE;               // 0b0011: hai quyền
boolean canWrite = (permissions & WRITE) != 0; // true
permissions |= EXECUTE;                       // 0b0111: thêm EXECUTE
permissions &= ~WRITE;                        // 0b0101: bỏ WRITE
permissions ^= READ;                          // 0b0100: đảo trạng thái READ
```

Với mask `1 << k` (k từ 0 đến 31 đối với `int`), những thao tác tổng quát thường dùng là:

| Mục đích | Mẫu biểu thức |
| --- | --- |
| Kiểm tra bit k | `(value & (1 << k)) != 0` |
| Bật bit k | `value \|= (1 << k)` |
| Tắt bit k | `value &= ~(1 << k)` |
| Đảo bit k | `value ^= (1 << k)` |
| Trích bit k về 0 hoặc 1 | `(value >>> k) & 1` |

Dùng dấu ngoặc khi kết hợp phép bit với phép so sánh: `(permissions & WRITE) != 0`. Toán tử `&`/`|` trên số nguyên là **bitwise**; `&&`/`||` là toán tử logic trên biểu thức boolean có cơ chế đánh giá ngắn mạch.

Khi quyền hoặc trạng thái là các giá trị enum có tên và không cần ánh xạ sang định dạng nhị phân bên ngoài, `EnumSet` thường diễn đạt ý nghĩa nghiệp vụ rõ hơn các mask thô. Với tập bit dài, thay đổi kích thước động, có thể cân nhắc `java.util.BitSet`.

## 8. Chuyển đổi giữa chuỗi bit và số

Các API tiêu chuẩn dưới đây vẫn áp dụng trên Java hiện đại:

```java
int x = Integer.parseInt("1010_0101".replace("_", ""), 2); // 165
String binary = Integer.toBinaryString(x);                 // "10100101"
String padded = String.format("%8s", binary).replace(' ', '0'); // "10100101"

byte signedByte = (byte) Integer.parseInt("11111011", 2); // -5
String byteBits = String.format("%8s",
        Integer.toBinaryString(signedByte & 0xFF)).replace(' ', '0');
// byteBits = "11111011"

int rawBits = Integer.parseUnsignedInt(
        "11111111111111111111111111111111", 2); // lưu pattern 32 bit: -1 nếu đọc có dấu
String unsignedDecimal = Integer.toUnsignedString(rawBits); // "4294967295"
long unsignedValue = Integer.toUnsignedLong(rawBits);       // 4294967295L
```

- `Integer.parseInt(s, 2)` nhận **chuỗi chữ số nhị phân**, không nhận tiền tố `0b`, không chấp nhận ký tự `_`; cần loại dấu phân nhóm trong dữ liệu đầu vào nếu có.
- `Integer.toBinaryString(x)` không thêm zero ở đầu khi `x` không âm; đối với `int` âm, nó hiển thị mẫu bù hai đầy 32 bit. `Long.toBinaryString` áp dụng tương tự cho `long`.
- Để biểu diễn **đúng 8 bit** của byte, mask `& 0xFF` rồi padding. Với dữ liệu ngoại vi, luôn xác định rõ độ rộng (8/16/32/64 bit), bit nào có dấu và quy tắc endianness nếu chuyển cả chuỗi byte; literal nhị phân **không tự định nghĩa thứ tự byte** trong bộ nhớ hay giao thức.
- `parseUnsignedInt`, `toUnsignedString`, `toUnsignedLong` cho phép xử lý cùng 32 bit theo cách diễn giải không dấu; bản thân biến `int` vẫn lưu cùng một mẫu bit. Nếu cần xử lý số lớn hơn 64 bit hoặc chuỗi bit độ dài tùy ý, xem `BigInteger`/`BitSet` tùy mục đích.

## 9. Lỗi thường gặp và cách tránh

1. **Nhầm giá trị và pattern:** `0b1111_1111` là số nguyên dương `255`; chỉ khi ép sang `byte` mới thành `-1`. Mẫu **32 bit** toàn `1` mới là `-1` khi diễn giải kiểu `int`.
2. **Nhầm tiền tố với dữ liệu chuỗi:** Java chấp nhận `0b1010` trong *source code*, còn `Integer.parseInt("0b1010", 2)` ném `NumberFormatException`. Bỏ tiền tố trước khi parse.
3. **Cho rằng `toBinaryString` luôn in đủ số bit:** `Integer.toBinaryString(5)` là `"101"`. Muốn đủ tám bit phải tự pad và mask đúng độ rộng.
4. **Dùng `~` rồi chỉ nhìn các bit đã viết:** `~0b1010` không bằng `0b0101` khi xét nguyên cả `int`; cần áp mask như `(~0b1010) & 0b1111`.
5. **Bỏ qua widening, dấu và overflow:** `byte` âm được nâng lên `int` có sign extension; phép dịch có thể làm mất bit. Dùng mask, `L` và kiểu đủ rộng khi cần.
6. **Dùng thiếu ngoặc ở biểu thức flag:** viết `(flags & MASK) != 0`, tránh nhầm độ ưu tiên toán tử.
7. **Tưởng thứ tự các chữ số trong literal là endianness:** literal mô tả giá trị số. Byte order chỉ quan trọng khi tuần tự hóa thành nhiều byte hoặc đọc dữ liệu nhị phân.

## 10. Tự kiểm tra

**Câu 1.** `0b1011_0010` bằng bao nhiêu ở hệ thập phân? **Đáp án:** `128 + 32 + 16 + 2 = 178`.

**Câu 2.** `0b1100 & 0b1010` bằng gì? **Đáp án:** `0b1000` (8); chỉ bit thứ 3 bằng `1` trong cả hai toán hạng.

**Câu 3.** Vì sao `byte b = 0b1111_1111;` lỗi, còn `byte b = (byte) 0b1111_1111;` hợp lệ? **Đáp án:** literal đầu tiên là `int` dương 255, nằm ngoài miền `byte`. Ép kiểu tường minh lấy tám bit thấp và diễn giải bù hai thành `-1`.

**Câu 4.** `Integer.toBinaryString(-1)` in ra bao nhiêu bit `1`? **Đáp án:** 32 bit, vì `-1` là `int` có toàn bộ 32 bit bằng `1`.

**Ghi nhớ:** `0b` giúp biểu diễn giá trị bằng chữ số nhị phân; `int`/`long` và ép kiểu quyết định độ rộng, dấu; mask và phép dịch giúp đọc hoặc chỉnh sửa bit. Luôn kiểm tra cả **giá trị số** lẫn **độ rộng biểu diễn** khi xử lý dữ liệu nhị phân.