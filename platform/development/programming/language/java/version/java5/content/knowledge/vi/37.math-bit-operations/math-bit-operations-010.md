# Integer, Long: bitCount, rotateLeft và rotateRight

## 1. Đếm bit và xoay bit giải quyết hai việc khác nhau

Khi dùng số nguyên như một mặt nạ, ta có thể cần biết **bao nhiêu bit đang bật** hoặc **di chuyển vị trí của các bit mà không làm mất chúng**.

- `bitCount` đếm số bit 1 trong toàn bộ biểu diễn của giá trị.
- `rotateLeft` xoay trái: bit đi ra khỏi đầu cao quay về đầu thấp.
- `rotateRight` xoay phải: bit đi ra khỏi đầu thấp quay về đầu cao.

Xoay bit khác dịch bit: phép dịch có thể bỏ các bit ra khỏi đầu dãy; phép xoay đưa chúng trở lại ở đầu kia.

Các phương thức này là `static`, nhận giá trị nguyên thủy. Không cần tạo đối tượng `Integer` hoặc `Long`.

| API | Độ rộng dữ liệu | Kiểu kết quả |
| --- | ---: | --- |
| `Integer.bitCount(int)` | 32 bit | `int`, từ 0 đến 32 |
| `Long.bitCount(long)` | 64 bit | `int`, từ 0 đến 64 |
| `Integer.rotateLeft/rotateRight(int, int)` | 32 bit | `int` |
| `Long.rotateLeft/rotateRight(long, int)` | 64 bit | `long` |

Chú ý: `Long.bitCount` vẫn trả `int`; số lượng bit không cần kiểu `long`.

## 2. bitCount xét biểu diễn bù hai, kể cả bit dấu

Ví dụ:

```text
44 = 00000000 00000000 00000000 00101100
                                      ^^ ^
Có 3 bit 1.
```

`Integer.bitCount(44)` là 3. Nó không phải số chữ số nhị phân cần để viết 44, không phải vị trí bit cao nhất và không phải số bit 0.

Với số âm, hàm xét toàn bộ biểu diễn bù hai:

| Giá trị | Kết quả |
| --- | ---: |
| `Integer.bitCount(0)` | 0 |
| `Integer.bitCount(1)` | 1 |
| `Integer.bitCount(-1)` | 32 |
| `Integer.bitCount(Integer.MIN_VALUE)` | 1 |
| `Long.bitCount(-1L)` | 64 |
| `Long.bitCount(Long.MIN_VALUE)` | 1 |

`-1` có toàn bộ bit bằng 1 ở độ rộng tương ứng. `MIN_VALUE` chỉ có bit dấu bằng 1. Hàm không tự đổi số âm thành trị tuyệt đối.

Cùng một giá trị số âm khi mở rộng từ `int` lên `long` được mở rộng dấu, nên có thể có thêm các bit 1 ở phần cao. Chọn đúng độ rộng theo dữ liệu muốn xét.

Một ứng dụng trực tiếp là đếm cờ trong mặt nạ. Nếu chỉ một tập bit là hợp lệ, đếm sau khi chọn tập đó:

```java
int activeKnownFlags = Integer.bitCount(flags & knownMask);
```

Đây là biểu thức minh họa trong một phương thức, với `flags` và `knownMask` đã được định nghĩa. Bit không thuộc `knownMask` không tham gia kết quả.

## 3. Xoay bit trên một vòng có độ rộng cố định

Xét `int x = 0x80000001`. Bit cao nhất và bit thấp nhất đều bằng 1:

```text
x:                 10000000 00000000 00000000 00000001
rotateLeft(x, 1):  00000000 00000000 00000000 00000011
rotateRight(x, 1): 11000000 00000000 00000000 00000000
```

Khi xoay trái một bước, bit ở vị trí 31 quay về vị trí 0, còn bit cũ ở vị trí 0 chuyển lên vị trí 1.

Khi xoay phải một bước, bit cũ ở vị trí 0 quay về vị trí 31, còn bit cũ ở vị trí 31 chuyển xuống vị trí 30.

Kết quả có thể đổi dấu khi được đọc như số nguyên có dấu. Phép xoay xét mẫu bit, không cố gắng giữ giá trị số hoặc dấu của đầu vào.

### So sánh với phép dịch

Cũng với x trên:

| Biểu thức | Kết quả hệ 16 | Điều xảy ra |
| --- | --- | --- |
| `x << 1` | `00000002` | Bit cao bị bỏ, đầu thấp thêm 0 |
| `Integer.rotateLeft(x, 1)` | `00000003` | Bit cao quay về đầu thấp |
| `x >>> 1` | `40000000` | Bit thấp bị bỏ, đầu cao thêm 0 |
| `Integer.rotateRight(x, 1)` | `c0000000` | Bit thấp quay về đầu cao |

`>>` là dịch phải số học, dùng bit dấu để lấp phần cao; `>>>` là dịch phải logic, lấp bằng 0. Cả hai đều không phải phép xoay tổng quát.

## 4. Khoảng xoay lớn, bằng 0 hoặc âm

Vì xoay đủ một vòng đưa các bit về chỗ cũ, khoảng xoay được hiểu theo độ rộng:

- Với `int`, chỉ năm bit thấp của khoảng xoay có tác dụng, tương ứng `distance & 31`.
- Với `long`, chỉ sáu bit thấp có tác dụng, tương ứng `distance & 63`.

Các hệ quả:

```java
Integer.rotateLeft(x, 0) == x
Integer.rotateLeft(x, 32) == x
Integer.rotateLeft(x, 33) == Integer.rotateLeft(x, 1)

Long.rotateLeft(y, 64) == y
Long.rotateRight(y, 65) == Long.rotateRight(y, 1)
```

Đây là các đẳng thức minh họa với x là `int`, y là `long`.

Khoảng xoay âm cũng hợp lệ: xoay trái -1 bước tương đương xoay phải 1 bước. Không cần tự coi khoảng âm là lỗi nếu muốn giữ đúng hợp đồng của API.

Nếu tự viết công thức từ phép dịch, cần hiểu cả cách Java rút gọn khoảng dịch lẫn việc chọn `>>>` thay cho `>>`. Dùng `rotateLeft`/`rotateRight` diễn đạt trực tiếp thao tác và giảm rủi ro viết sai.

## 5. Hai tính chất hữu ích để kiểm chứng

Xoay chỉ đổi vị trí, nên số bit 1 được giữ nguyên:

```java
Integer.bitCount(Integer.rotateLeft(x, d)) == Integer.bitCount(x)
```

Xoay ngược lại cùng khoảng sẽ phục hồi mẫu ban đầu:

```java
Integer.rotateRight(Integer.rotateLeft(x, d), d) == x
```

Hai tính chất cũng đúng với `Long`. Chúng giúp kiểm tra một thuật toán có thao tác xoay, nhưng không thay cho xác nhận rằng thuật toán đã chọn đúng hướng và đúng khoảng. Ví dụ xoay sai một khoảng vẫn giữ nguyên số bit 1.

Tất cả đầu vào 0 cho kết quả xoay bằng 0. Mẫu toàn bit 1 như `-1` cũng không đổi sau mọi phép xoay.

## 6. Chương trình chạy đầy đủ

Lưu thành `BitCountRotateDemo.java`. Chương trình dùng API có trên Java 17 trở lên.

```java
import java.util.Locale;

public class BitCountRotateDemo {
    public static void main(String[] args) {
        System.out.println("int bitCount(0) = " + Integer.bitCount(0));
        System.out.println("int bitCount(44) = " + Integer.bitCount(44));
        System.out.println("int bitCount(-1) = " + Integer.bitCount(-1));
        System.out.println("int bitCount(MIN_VALUE) = "
                + Integer.bitCount(Integer.MIN_VALUE));
        System.out.println("long bitCount(-1L) = " + Long.bitCount(-1L));

        int x = 0x80000001;
        System.out.printf(Locale.ROOT, "x = %08x%n", x);
        System.out.printf(Locale.ROOT, "left 1 = %08x%n", Integer.rotateLeft(x, 1));
        System.out.printf(Locale.ROOT, "right 1 = %08x%n", Integer.rotateRight(x, 1));
        System.out.printf(Locale.ROOT, "shift left 1 = %08x%n", x << 1);
        System.out.printf(Locale.ROOT, "logical shift right 1 = %08x%n", x >>> 1);
        System.out.printf(Locale.ROOT, "left 33 = %08x%n", Integer.rotateLeft(x, 33));
        System.out.printf(Locale.ROOT, "left -1 = %08x%n", Integer.rotateLeft(x, -1));
        System.out.println("left 32 unchanged = " + (Integer.rotateLeft(x, 32) == x));
        int rotated = Integer.rotateLeft(x, 11);
        System.out.println("inverse rotation = "
                + (Integer.rotateRight(rotated, 11) == x));
        System.out.println("bit count preserved = "
                + (Integer.bitCount(rotated) == Integer.bitCount(x)));

        long y = 0x8000000000000001L;
        System.out.printf(Locale.ROOT, "long left 1 = %016x%n", Long.rotateLeft(y, 1));
        System.out.printf(Locale.ROOT, "long right 1 = %016x%n", Long.rotateRight(y, 1));
        System.out.println("long left 64 unchanged = " + (Long.rotateLeft(y, 64) == y));

        byte b = (byte) 0x80;
        System.out.println("promoted byte bitCount = " + Integer.bitCount(b));
        System.out.println("8-bit unsigned bitCount = "
                + Integer.bitCount(Byte.toUnsignedInt(b)));
        System.out.printf(Locale.ROOT, "rotate 0x81 as int = %08x%n",
                Integer.rotateLeft(0x81, 1));

        int first = 0b101100;
        int second = 0b100101;
        System.out.println("different bit positions = "
                + Integer.bitCount(first ^ second));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 BitCountRotateDemo.java
java BitCountRotateDemo
```

Stdout:

```text
int bitCount(0) = 0
int bitCount(44) = 3
int bitCount(-1) = 32
int bitCount(MIN_VALUE) = 1
long bitCount(-1L) = 64
x = 80000001
left 1 = 00000003
right 1 = c0000000
shift left 1 = 00000002
logical shift right 1 = 40000000
left 33 = 00000003
left -1 = c0000000
left 32 unchanged = true
inverse rotation = true
bit count preserved = true
long left 1 = 0000000000000003
long right 1 = c000000000000000
long left 64 unchanged = true
promoted byte bitCount = 25
8-bit unsigned bitCount = 1
rotate 0x81 as int = 00000102
different bit positions = 2
```

Các giá trị xoay được in ở hệ 16 với độ rộng cố định để nhìn được vòng 32/64 bit. Không suy từ số thập phân âm rằng phép xoay làm mất bit.

## 7. Cẩn thận với byte, short và một phần của int

Java nâng `byte` hoặc `short` lên `int` khi gọi các API nhận `int`. Với giá trị âm, quá trình này mở rộng dấu.

Ví dụ `(byte) 0x80` có một bit 1 trong tám bit của nó, nhưng khi đưa trực tiếp vào `Integer.bitCount`, mẫu 32 bit trở thành `0xffffff80`, có 25 bit 1. Nếu muốn đếm đúng tám bit dữ liệu, dùng:

```java
int count = Integer.bitCount(Byte.toUnsignedInt(b));
// Tuong duong Integer.bitCount(b & 0xff)
```

Tương tự, với dữ liệu 16 bit cần xét không dấu, có thể chọn `Short.toUnsignedInt` hoặc mặt nạ `0xffff` trước khi đếm.

`Integer.rotateLeft(0x81, 1)` xoay trên **32 bit**, nên cho `0x00000102`, không phải phép xoay tám bit cho `0x03`. Chỉ ép kết quả ấy về `byte` cũng không đưa bit ở vị trí 7 quay về vị trí 0; bit đó mới chỉ chuyển lên vị trí 8 rồi bị bỏ khi thu hẹp kiểu.

Nếu thuật toán đòi xoay một trường 8 hoặc 16 bit, phải thiết kế phép xoay đúng độ rộng của trường. Không coi các API này là phép xoay trên “số bit đang được dùng” của giá trị.

## 8. Đếm số vị trí khác nhau bằng XOR

XOR bật một bit khi hai đầu vào có bit khác nhau ở vị trí đó. Ghép với `bitCount` sẽ đếm số vị trí khác nhau, tức khoảng cách Hamming của hai mẫu cùng độ rộng:

```java
int first = 0b101100;
int second = 0b100101;
int distance = Integer.bitCount(first ^ second); // 2
```

`bitCount` không tự cho biết các vị trí khác nhau nằm ở đâu; nó chỉ trả số lượng. Nếu chỉ quan tâm một trường bit, chọn mặt nạ trường trước khi đếm.

Phép xoay thường xuất hiện trong các thuật toán trộn bit, xử lý từ dữ liệu và một số thuật toán đã có đặc tả. Khi triển khai một đặc tả, hướng xoay, độ rộng từ và khoảng xoay đều là một phần của thuật toán; không thay một phép dịch bằng xoay vì thấy “giữ nhiều bit hơn”.

## 9. Lỗi thường gặp và bài tập

Những lỗi cần tránh:

- Đếm số bit của trị tuyệt đối thay vì mẫu bù hai mà API thật sự xét.
- Mong `Long.bitCount` trả `long`.
- Nhầm xoay 32 bit với xoay 8 bit vì đầu vào nhìn nhỏ.
- Dùng `>>` để ghép công thức xoay phải/trái mà quên mở rộng dấu.
- Cho rằng khoảng xoay lớn hơn độ rộng hoặc âm gây ngoại lệ.
- Tạo mặt nạ `long` bằng `1 << position` thay vì `1L << position` khi vị trí nằm ở phần cao.

Tự kiểm tra:

1. `Integer.bitCount(0b101010)` là bao nhiêu?
2. `Integer.rotateLeft(1, 31)` có giá trị gì?
3. `Integer.rotateRight(1, 1)` có cùng mẫu bit với kết quả câu 2 không?
4. `Long.rotateLeft(1L, 64)` trả gì?

Đáp án:

1. 3.
2. `Integer.MIN_VALUE`, mẫu `0x80000000`.
3. Có; bit thấp nhất quay về bit cao nhất của vòng 32 bit.
4. `1L`, vì 64 bước là một vòng đầy đủ.

Tham khảo API hiện hành: [Integer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html) và [Long](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html), các phương thức `bitCount`, `rotateLeft`, `rotateRight`.
