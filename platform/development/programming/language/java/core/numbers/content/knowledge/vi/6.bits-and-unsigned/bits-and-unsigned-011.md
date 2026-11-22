# Không đồng nhất dịch phải với chia khi xử lý số âm trong Java

Trong Java, **dịch phải số nguyên có dấu** (`>>`) và **chia số nguyên** (`/`) có thể cho hai kết quả khác nhau khi số bị chia âm. Sự khác nhau đến từ **quy tắc làm tròn**, không phải từ việc viết hai phép toán theo hai cách khác nhau. Cần phân biệt thêm dịch phải không dấu (`>>>`), vì nó còn thay đổi cách xử lý bit dấu.

Bài học thuộc chủ đề **Bit và số không dấu**. Sau khi học, bạn cần biết khi nào dùng `/`, `>>` và `>>>`; có thể tự giải thích kết quả với số âm; và tránh thay phép chia bằng phép dịch bit một cách máy móc.

## 1. Ba phép toán có ba ý nghĩa

- `x / d` với `x` và `d` là kiểu nguyên (`int` hoặc `long`): Java thực hiện **chia nguyên, bỏ phần thập phân theo hướng 0**. Ví dụ `-3 / 2` được `-1`, vì thương toán học là `-1.5` và được cắt về `-1`. Dấu của số dư (`%`) theo dấu của số bị chia: `-3 % 2 == -1`.
- `x >> k`: **dịch phải số học** (arithmetic right shift), các bit bên trái được điền bằng bit dấu (0 với số không âm, 1 với số âm). Với `int` và `0 <= k <= 30`, kết quả tương đương **làm tròn xuống âm vô cực** của `x / 2^k` theo nghĩa toán học: `floor(x / 2^k)`.
- `x >>> k`: **dịch phải logic** (logical/unsigned right shift), luôn điền bit 0 từ bên trái. Với số âm, kết quả thường là một số nguyên dương rất lớn khi nhìn theo kiểu `int`; phép này không tương đương phép chia có dấu.

Điểm mấu chốt: `/` làm tròn về **0**, còn `>>` khi dịch số âm với phần dư khác 0 thì làm tròn về **âm vô cực**.

| Giá trị `x` | `k` | Thương toán học `x / 2^k` | `x / (1 << k)` | `x >> k` |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 1 | 3.5 | 3 | 3 |
| -8 | 2 | -2 | -2 | -2 |
| -7 | 2 | -1.75 | -1 | -2 |
| -3 | 1 | -1.5 | -1 | -2 |
| -1 | 1 | -0.5 | 0 | -1 |

Bảng dùng kiểu `int`, `k` từ 0 đến 30 và mẫu số dương `1 << k`. Hai phép chỉ luôn giống nhau trong miền này khi `x >= 0` hoặc `x` âm nhưng **chia hết cho `2^k`**. Chúng khác nhau một đơn vị với số âm không chia hết.

## 2. Vì sao `-3 >> 1` bằng `-2`?

`int` có 32 bit và biểu diễn số nguyên âm theo bù hai (two's complement). Mẫu bit của `-3` là:

~~~text
-3 (int)       = 11111111 11111111 11111111 11111101 = 0xFFFFFFFD
-3 >> 1        = 11111111 11111111 11111111 11111110 = 0xFFFFFFFE = -2
-3 >>> 1       = 01111111 11111111 11111111 11111110 = 0x7FFFFFFE = 2147483646
-3 / 2         = -1                                      = 0xFFFFFFFF
~~~

Khi dùng `>>`, bit 1 bên trái được lặp lại, giữ dấu âm. Bit thấp bị loại bỏ, nên số `-3` chuyển thành `-2`. Trong phép chia `-3 / 2`, Java tính thương `-1.5` rồi bỏ phần lẻ về phía 0, được `-1`; phép chia không được định nghĩa là “dịch bit rồi bỏ bit cuối”.

Khi dùng `>>>`, bit 0 được chèn vào trái. Điều này phù hợp với ý nghĩa **dịch một mẫu bit 32 bit như số không dấu**: `0xFFFFFFFD` được hiểu là `4294967293` trong miền unsigned 32 bit, và chia lấy phần nguyên cho 2 được `2147483646`. Tuy nhiên biến `int` trong Java **vẫn là kiểu có dấu**; để xem giá trị unsigned ban đầu, dùng `Integer.toUnsignedLong(-3)`.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu đúng tên tệp `ShiftVsDivision.java`:

~~~java
public class ShiftVsDivision {
    public static void main(String[] args) {
        printCase(-3, 1);
        printCase(-8, 2);
        printCase(-7, 2);
        printCase(7, 1);
        printCase(-1, 1);

        System.out.println("Math.floorDiv(-3, 2) = "
                + Math.floorDiv(-3, 2));
        System.out.println("-3 >>> 1 = " + (-3 >>> 1));
        System.out.println("-3 unsigned = "
                + Integer.toUnsignedLong(-3));
    }

    private static void printCase(int x, int k) {
        if (k < 0 || k > 30) {
            throw new IllegalArgumentException("k must be from 0 to 30");
        }
        int divisor = 1 << k;
        System.out.println("x=" + x + ", k=" + k
                + ": /=" + (x / divisor)
                + ", >>=" + (x >> k));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ShiftVsDivision.java
java ShiftVsDivision
~~~

Đầu ra chính xác:

~~~text
x=-3, k=1: /=-1, >>=-2
x=-8, k=2: /=-2, >>=-2
x=-7, k=2: /=-1, >>=-2
x=7, k=1: /=3, >>=3
x=-1, k=1: /=0, >>=-1
Math.floorDiv(-3, 2) = -2
-3 >>> 1 = 2147483646
-3 unsigned = 4294967293
~~~

Quan sát các dòng `-3`, `-7` và `-1`: chia nguyên và dịch phải khác nhau. Dòng `-8` cho thấy số âm **chia hết** cho lũy thừa của 2 thì kết quả vẫn trùng nhau. Dòng `7` minh họa trường hợp số dương.

## 4. Chọn toán tử theo ý nghĩa cần tính

**Trường hợp A — muốn thương chia nguyên theo quy tắc Java:** dùng `/`.

~~~java
int quantity = -7;
int result = quantity / 4; // -1: làm tròn về 0
~~~

Không thay thành `quantity >> 2`: phép dịch cho `-2`. Đây có thể là lỗi khó thấy nếu thử nghiệm chỉ với số dương hoặc số âm chia hết.

**Trường hợp B — muốn làm tròn xuống khi chia cho lũy thừa của 2:** dùng `Math.floorDiv(x, divisor)` để thể hiện rõ ý định, hoặc `x >> k` nếu thật sự đang làm phép toán bit và hiểu giới hạn của `k`.

~~~java
int x = -7;
int floorByApi = Math.floorDiv(x, 4); // -2
int floorByBits = x >> 2;             // -2
~~~

`Math.floorDiv` còn dùng được với các số chia dương khác 2, 4, 8, ...; `>>` chỉ có quan hệ trên với phép chia cho lũy thừa của 2. Trong công thức `floor(x / 2^k)`, ký hiệu `floor` là phép làm tròn toán học, **không phải** một phép chia nguyên Java.

**Trường hợp C — đang thao tác mẫu bit hoặc muốn dịch không dấu:** dùng `>>>` khi cần điền 0 từ bên trái; nếu muốn xử lý giá trị `int` như unsigned 32 bit, dùng các API thể hiện rõ cách hiểu unsigned.

~~~java
int bits = -3; // 0xFFFFFFFD
int shifted = bits >>> 1;                // 2147483646
long unsigned = Integer.toUnsignedLong(bits); // 4294967293
int quotient = Integer.divideUnsigned(bits, 2); // 2147483646
~~~

`>>>` hữu ích khi tách trường bit, xử lý mặt nạ, dữ liệu nhị phân hoặc một thuật toán chủ động dùng biểu diễn unsigned. Không dùng `>>>` để thay `/` với số âm có dấu.

## 5. Các giới hạn dễ bỏ sót

1. **Số lần dịch bị rút gọn theo độ rộng kiểu dữ liệu.** Với `int`, Java chỉ dùng 5 bit thấp của số đếm dịch (`k & 31`); với `long` là 6 bit thấp (`k & 63`). Vì vậy `x >> 32` thực chất giống `x >> 0` khi `x` là `int`; nó không biểu diễn chia cho `2^32`. Tương tự `1L >> 64` giống `1L >> 0`.
2. **Tránh viết `1 << 31` làm số chia dương kiểu `int`.** Giá trị đó là `Integer.MIN_VALUE` (`-2147483648`), do bit dấu được bật lên. Mẫu `x / (1 << k)` trong bảng chỉ dùng `0 <= k <= 30`. Nếu phải tính lũy thừa của 2 lớn hơn, xét `long` hoặc cách biểu diễn phù hợp trước khi chia.
3. **`byte` và `short` được nâng lên `int` trước khi dịch.** Ví dụ nếu `byte b = -3`, thì `b >>> 1` hoạt động trên `int` 32 bit đã được mở rộng dấu, kết quả là `2147483646`, không phải phép dịch riêng trên mẫu 8 bit `0xFD`. Nếu cần xử lý byte không dấu, chuyển `b & 0xFF` trước rồi mới dịch.
4. **`long` tuân theo cùng khác biệt làm tròn.** `-3L / 2L` cho `-1L`, còn `-3L >> 1` cho `-2L`. Số đếm dịch của `long` dùng giới hạn 64 bit thay vì 32 bit.
5. **Đừng suy ra “dịch luôn nhanh hơn chia” để tự thay toán tử.** Hai biểu thức phải có cùng ngữ nghĩa với *mọi* đầu vào hợp lệ trước khi tối ưu; trình biên dịch/JIT có thể tự chọn cách thực hiện phù hợp nhưng chương trình vẫn phải bảo toàn cách làm tròn của `/`. Việc thay sai phép toán là lỗi đúng đắn, bất kể hiệu năng.
6. **Kiểm tra trường hợp âm sát 0 và số âm lẻ.** `-1 / 2 == 0` nhưng `-1 >> 1 == -1` là phép thử nhỏ nhất làm lộ khác biệt; hãy thêm cả `-3`, `-7` và số âm chia hết như `-8`.

Với số chia là `2^k` dương và biểu diễn được, có thể ghi nhớ công thức:

~~~text
x / (2^k)  = truncateTowardZero(x / 2^k)
x >> k     = floor(x / 2^k)
~~~

Với `x < 0` và có số dư khác 0, kết quả `x >> k` **nhỏ hơn kết quả chia nguyên đúng 1**. Với `x >= 0` hoặc số âm chia hết, chúng trùng nhau. Đây là lý do phép dịch bit không thể mặc định thay thế phép chia trong logic xử lý số nguyên có dấu.

## 6. Tự kiểm tra

Hãy dự đoán trước khi chạy Java:

- `-9 / 4` và `-9 >> 2` lần lượt bằng bao nhiêu?
- `-12 / 4` và `-12 >> 2` có bằng nhau không?
- `-1 >>> 1` là bao nhiêu đối với kiểu `int`, và vì sao nó không phải kết quả của `-1 / 2`?

**Đáp án:** `-9 / 4 == -2`, `-9 >> 2 == -3`; cả hai biểu thức với `-12` đều bằng `-3` vì chia hết cho 4; `-1 >>> 1 == 2147483647` vì `-1` có toàn bit 1 và `>>>` chèn 0 vào đầu, trong khi `-1 / 2 == 0`.

Khi đọc code hiện có, hãy xác định ngay mục đích: **chia số có dấu**, **làm tròn xuống**, hay **dịch mẫu bit không dấu**. Chọn toán tử theo mục đích ấy, đặc biệt khi dữ liệu đầu vào có thể âm.
