# Integer, Long: highestOneBit và lowestOneBit

## 1. Chọn một bit đang bật trong một mẫu bit

Một số nguyên có thể được nhìn như giá trị số hoặc như một dãy bit. Khi dùng nó làm mặt nạ (`bit mask`), ta thường cần tách riêng một bit đang bật, tức bit có giá trị 1.

- `highestOneBit` giữ lại **bit 1 ở vị trí cao nhất**, phía trái.
- `lowestOneBit` giữ lại **bit 1 ở vị trí thấp nhất**, phía phải.
- Các bit còn lại trong kết quả đều bằng 0.
- Nếu đầu vào bằng 0, không có bit 1 nào nên cả hai trả 0.

Ví dụ với số dương 40:

```text
40                    = 0010 1000
highestOneBit(40) = 32 = 0010 0000
lowestOneBit(40)  =  8 = 0000 1000
```

Các dãy trên chỉ hiển thị tám bit cuối cho dễ đọc; `int` thực tế có 32 bit.

Kết quả là **mặt nạ chứa một bit**, không phải số thứ tự của bit và không phải số lượng bit 1. Nếu đánh số từ 0 ở bên phải, bit cao nhất của 40 nằm ở vị trí 5 nhưng `highestOneBit(40)` trả 32, không trả 5.

## 2. Chọn đúng độ rộng kiểu dữ liệu

| API | Đầu vào | Kết quả | Độ rộng được xét |
| --- | --- | --- | ---: |
| `Integer.highestOneBit(int)` | `int` | `int` | 32 bit |
| `Integer.lowestOneBit(int)` | `int` | `int` | 32 bit |
| `Long.highestOneBit(long)` | `long` | `long` | 64 bit |
| `Long.lowestOneBit(long)` | `long` | `long` | 64 bit |

Đây là các phương thức `static`; không cần tạo một đối tượng `Integer` hoặc `Long`. Ví dụ:

```java
int smallMask = Integer.lowestOneBit(40);
long largeMask = Long.highestOneBit((1L << 40) | (1L << 7));
```

Với mặt nạ 64 bit, viết `1L << position` để phép dịch thực hiện trên `long`. Viết `1 << 40` vẫn là dịch trên `int`; trong Java, khoảng dịch `int` chỉ dùng năm bit thấp của khoảng dịch, nên đó không tạo bit ở vị trí 40.

Cũng không ép một mặt nạ `long` về `int` trước khi tìm bit: các bit cao có thể bị mất ngay tại bước ép kiểu.

## 3. Số âm được xét theo biểu diễn bù hai

`int` và `long` của Java là số nguyên có dấu theo biểu diễn bù hai. Các phương thức này xét **mẫu bit hiện có**, không tự lấy trị tuyệt đối của đầu vào.

Mọi `int` âm đều bật bit dấu ở vị trí 31, nên:

```java
Integer.highestOneBit(-40) == Integer.MIN_VALUE
```

Giá trị trả về là mẫu `0x80000000`, được đọc như số `-2147483648`. Đây vẫn là mẫu chỉ có một bit 1.

Tương tự, mọi `long` âm có `Long.highestOneBit(value) == Long.MIN_VALUE`, là mẫu `0x8000000000000000`.

`lowestOneBit` vẫn chọn từ phía phải. Ví dụ `-40` có 32 bit:

```text
-40:    11111111 11111111 11111111 11011000
lowest: 00000000 00000000 00000000 00001000
```

Do đó `Integer.lowestOneBit(-40)` trả 8.

Các trường hợp cần nhớ:

| Đầu vào int | highestOneBit | lowestOneBit |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 40 | 32 | 8 |
| -1 | `Integer.MIN_VALUE` | 1 |
| -8 | `Integer.MIN_VALUE` | 8 |
| `Integer.MIN_VALUE` | `Integer.MIN_VALUE` | `Integer.MIN_VALUE` |

Chỉ `Integer.MIN_VALUE` trong các đầu vào `int` mới có bit 1 duy nhất ở bit dấu, nên `lowestOneBit` của nó cũng là một giá trị âm. Với `long`, trường hợp tương ứng là `Long.MIN_VALUE`.

Không dùng điều kiện `bit > 0` để diễn đạt “có một bit được chọn” cho mặt nạ tổng quát. Hãy dùng `bit != 0`.

## 4. Quan hệ low bit: x & -x

Trong biểu diễn bù hai có độ rộng cố định, bit 1 thấp nhất có thể tách bằng:

```java
int low = x & -x;
long low64 = y & -y;
```

Đây là quan hệ giúp hiểu `lowestOneBit`, không bắt buộc phải tự viết thay API. Với 40, `40 & -40` bằng 8.

Lý do là `-x` tương ứng đảo bit rồi cộng 1: phần từ bit 1 thấp nhất trở xuống khiến đúng bit đó còn lại sau phép AND. Các bit thấp hơn vốn bằng 0 trong x.

Trường hợp `MIN_VALUE` cần được đọc theo ngữ nghĩa Java: phép đổi dấu nguyên thông thường có thể tràn và giữ cùng mẫu bit. Vì vậy quan hệ `x & -x` vẫn tách được bit dấu cho `MIN_VALUE`; không nên diễn giải nó như phép lấy số dương đối của x luôn biểu diễn được.

Các phép toán bit ở đây không cần chuyển qua số thực hoặc dùng logarit.

## 5. Ứng dụng thường gặp

### Chọn lũy thừa hai không vượt quá số dương

Nếu `n > 0`, `Integer.highestOneBit(n)` là lũy thừa của 2 lớn nhất không vượt quá n. Ví dụ 40 cho 32; 32 cho 32; 31 cho 16.

Đây là phép chọn phía dưới. Nếu cần lũy thừa hai nhỏ nhất **không nhỏ hơn n**, đó là bài toán khác; không được coi `highestOneBit(40)` là 64.

Cũng không dịch trái kết quả một bit một cách vô điều kiện: `Integer.highestOneBit(Integer.MAX_VALUE)` là `1 << 30`; dịch trái tiếp tạo bit dấu và không còn là một số `int` dương. Cần quy định miền đầu vào và xử lý giới hạn nếu xây hàm tìm kích thước lũy thừa hai.

### Duyệt những cờ đang bật

Có thể tách bit thấp nhất rồi xóa chính bit đó:

```java
int remaining = mask;
while (remaining != 0) {
    int bit = Integer.lowestOneBit(remaining);
    // Xu ly co duoc bieu dien boi bit.
    remaining ^= bit;
}
```

Đoạn này minh họa để đặt trong một phương thức. Vì `bit` chắc chắn đang bật và chỉ chứa một bit 1, XOR sẽ tắt nó. Mỗi vòng loại một bit, kể cả bit dấu, nên điều kiện là `remaining != 0`.

Không viết `while (remaining > 0)` nếu muốn hỗ trợ cả mẫu bit có bit dấu bật; vòng lặp đó bỏ qua mặt nạ âm ngay từ đầu.

### Phân biệt “một bit” và “lũy thừa hai dương”

Điều kiện:

```java
x != 0 && Integer.highestOneBit(x) == Integer.lowestOneBit(x)
```

kiểm tra mẫu bit có đúng một bit 1. Nó chấp nhận `Integer.MIN_VALUE`. Nếu yêu cầu là lũy thừa hai **dương**, cần điều kiện `x > 0` thay cho `x != 0`.

Nếu chỉ so sánh hai kết quả mà quên loại 0, số 0 cũng lọt qua vì cả hai hàm đều trả 0.

## 6. Chương trình chạy đầy đủ

Lưu thành `OneBitDemo.java`. Chương trình dùng API có trên Java 17 trở lên.

```java
import java.util.Locale;

public class OneBitDemo {
    private static void showInt(int value) {
        System.out.printf(Locale.ROOT,
                "int %d [0x%08x] -> highest=%d [0x%08x], lowest=%d [0x%08x]%n",
                value, value,
                Integer.highestOneBit(value), Integer.highestOneBit(value),
                Integer.lowestOneBit(value), Integer.lowestOneBit(value));
    }

    private static void showLong(long value) {
        System.out.printf(Locale.ROOT,
                "long %d -> highest=%d [0x%016x], lowest=%d [0x%016x]%n",
                value, Long.highestOneBit(value), Long.highestOneBit(value),
                Long.lowestOneBit(value), Long.lowestOneBit(value));
    }

    private static boolean hasOneBitPattern(int value) {
        return value != 0
                && Integer.highestOneBit(value) == Integer.lowestOneBit(value);
    }

    public static void main(String[] args) {
        showInt(0);
        showInt(40);
        showInt(-40);
        showInt(Integer.MIN_VALUE);
        showLong((1L << 40) | (1L << 7));
        showLong(Long.MIN_VALUE);

        int remaining = 0b101100;
        System.out.print("set-bit masks:");
        while (remaining != 0) {
            int bit = Integer.lowestOneBit(remaining);
            System.out.print(" " + bit);
            remaining ^= bit;
        }
        System.out.println();

        int positive = 40;
        int floorPowerOfTwo = Integer.highestOneBit(positive);
        System.out.println("largest power of two <= 40 = " + floorPowerOfTwo);
        System.out.println("40 & -40 = " + (positive & -positive));
        System.out.println("0 has one set bit = "
                + hasOneBitPattern(0));
        System.out.println("-8 has one set bit = "
                + hasOneBitPattern(-8));
        System.out.println("MIN_VALUE has one set bit = "
                + hasOneBitPattern(Integer.MIN_VALUE));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OneBitDemo.java
java OneBitDemo
```

Stdout:

```text
int 0 [0x00000000] -> highest=0 [0x00000000], lowest=0 [0x00000000]
int 40 [0x00000028] -> highest=32 [0x00000020], lowest=8 [0x00000008]
int -40 [0xffffffd8] -> highest=-2147483648 [0x80000000], lowest=8 [0x00000008]
int -2147483648 [0x80000000] -> highest=-2147483648 [0x80000000], lowest=-2147483648 [0x80000000]
long 1099511627904 -> highest=1099511627776 [0x0000010000000000], lowest=128 [0x0000000000000080]
long -9223372036854775808 -> highest=-9223372036854775808 [0x8000000000000000], lowest=-9223372036854775808 [0x8000000000000000]
set-bit masks: 4 8 32
largest power of two <= 40 = 32
40 & -40 = 8
0 has one set bit = false
-8 has one set bit = false
MIN_VALUE has one set bit = true
```

Dạng hệ 16 được in đủ 8 hoặc 16 chữ số để thấy bit dấu và độ rộng. Ba cờ của `0b101100` được tách lần lượt thành mặt nạ 4, 8, 32. Đầu vào `-8` không phải một mẫu chỉ có một bit 1: các bit cao của biểu diễn bù hai cũng đang bật.

## 7. Khi cần vị trí bit thay vì mặt nạ

Với `int x != 0`, có thể tìm chỉ số bit cao nhất bằng `31 - Integer.numberOfLeadingZeros(x)`; chỉ số bit thấp nhất bằng `Integer.numberOfTrailingZeros(x)`. Với `long`, dùng các phương thức của `Long` và mốc 63.

Các phương thức đếm số 0 trả về `int`, trong khi `highestOneBit`/`lowestOneBit` trả mặt nạ cùng kiểu đầu vào. Đừng dùng lẫn hai loại kết quả.

Số 0 không có vị trí bit 1 hợp lệ. Các API đếm số 0 có giá trị quy ước cho 0, nhưng chương trình phải xử lý trường hợp đó trước khi coi kết quả là một chỉ số bit.

Nếu đầu vào được mở rộng từ một `int` âm sang `long`, các bit dấu được mở rộng. Vì thế `Long.highestOneBit((long) negativeInt)` xét một mẫu 64 bit, không phải chỉ 32 bit ban đầu. Chọn độ rộng theo dữ liệu thực sự cần xử lý.

## 8. Tự kiểm tra

1. `Integer.highestOneBit(72)` và `Integer.lowestOneBit(72)` bằng bao nhiêu?
2. `Long.lowestOneBit(0L)` có ném ngoại lệ không?
3. Vì sao `highestOneBit(-1)` không bằng 1?
4. Có thể dùng `highestOneBit(n) << 1` như hàm “lũy thừa hai kế tiếp” cho mọi `int` dương không?

Đáp án:

1. 64 và 8, vì `72 = 0b1001000`.
2. Không, trả `0L`.
3. `-1` có toàn bộ 32 bit bật; bit cao nhất là bit dấu, nên kết quả là `Integer.MIN_VALUE`.
4. Không; còn trường hợp n vốn đã là lũy thừa hai, yêu cầu bao gồm hay không bao gồm n, và giới hạn tràn vào bit dấu.

Tham khảo API hiện hành: [Integer.highestOneBit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#highestOneBit(int)), [Integer.lowestOneBit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Integer.html#lowestOneBit(int)), [Long.highestOneBit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#highestOneBit(long)) và [Long.lowestOneBit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#lowestOneBit(long)).
