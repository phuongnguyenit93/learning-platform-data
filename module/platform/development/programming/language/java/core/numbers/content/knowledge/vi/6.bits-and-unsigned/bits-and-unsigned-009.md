# `bitCount`, leading zeros, trailing zeros và one-bit helpers trong Java

## 1. Mục tiêu và mô hình bit

Trong Java, `int` luôn có **32 bit** và `long` luôn có **64 bit** (`Integer.SIZE == 32`, `Long.SIZE == 64`). Các phép toán bit xử lý **mẫu bit có độ rộng cố định**, kể cả khi giá trị được diễn giải là số âm theo biểu diễn bù hai (two's complement). Các hàm tiện ích của `Integer` và `Long` giúp đếm bit 1, xác định vị trí bit 1, hoặc cô lập bit 1 ở đầu/cuối mà không cần tự dịch bit qua từng vị trí.

Ví dụ, số `40` có dạng nhị phân `101000`. Khi xem dưới dạng `int`, nó có **26 bit 0 ở bên trái**, sau đó là `101000`; hai bit 1 nằm tại vị trí 5 và 3 (đánh số từ phải sang, bắt đầu từ 0). Vì vậy:

- `Integer.bitCount(40)` trả `2`.
- `Integer.numberOfLeadingZeros(40)` trả `26`.
- `Integer.numberOfTrailingZeros(40)` trả `3`.
- `Integer.highestOneBit(40)` trả `32` (bit 1 tại vị trí 5).
- `Integer.lowestOneBit(40)` trả `8` (bit 1 tại vị trí 3).

Các phương thức dưới đây là `static`, không thay đổi đối số và không phụ thuộc việc bạn in giá trị theo hệ thập phân, thập lục phân hay nhị phân.

## 2. Tổng quan API

| `Integer` (`int`, 32 bit) | `Long` (`long`, 64 bit) | Ý nghĩa |
| --- | --- | --- |
| `Integer.bitCount(x)` | `Long.bitCount(x)` | Số lượng bit bằng 1 (population count, **popcount**) trong toàn bộ mẫu bit. |
| `Integer.numberOfLeadingZeros(x)` | `Long.numberOfLeadingZeros(x)` | Số bit 0 liên tiếp **từ bit cao nhất** đến trước bit 1 đầu tiên. |
| `Integer.numberOfTrailingZeros(x)` | `Long.numberOfTrailingZeros(x)` | Số bit 0 liên tiếp **từ bit thấp nhất** đến trước bit 1 đầu tiên. |
| `Integer.highestOneBit(x)` | `Long.highestOneBit(x)` | Giá trị chỉ giữ lại **bit 1 cao nhất**; các bit khác bằng 0. |
| `Integer.lowestOneBit(x)` | `Long.lowestOneBit(x)` | Giá trị chỉ giữ lại **bit 1 thấp nhất**; các bit khác bằng 0. |

Các kết quả đếm luôn là `int`, kể cả với `Long`. Hai hàm `highestOneBit`/`lowestOneBit` trả lại đúng kiểu đầu vào (`int` hoặc `long`). Không có giá trị trả về `-1` để báo không tìm thấy bit 1: hai hàm *one-bit* trả `0`; hai hàm đếm số bit 0 trả **độ rộng bit** khi đầu vào bằng `0`.

### Các trường hợp biên cần nhớ

| Đầu vào `int` | `bitCount` | Leading zeros | Trailing zeros | `highestOneBit` | `lowestOneBit` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0` | 0 | 32 | 32 | 0 | 0 |
| `40` (`0b101000`) | 2 | 26 | 3 | 32 | 8 |
| `-1` (32 bit 1) | 32 | 0 | 0 | `Integer.MIN_VALUE` | 1 |
| `Integer.MIN_VALUE` (chỉ bit dấu bằng 1) | 1 | 0 | 31 | `Integer.MIN_VALUE` | `Integer.MIN_VALUE` |

Với `long`, thay độ rộng `32` bằng `64`. Chẳng hạn `Long.numberOfTrailingZeros(0L) == 64`, `Long.bitCount(-1L) == 64`, và `Long.highestOneBit(-1L) == Long.MIN_VALUE`.

## 3. `bitCount`: đếm số bit 1

`Integer.bitCount(x)` và `Long.bitCount(x)` trả số bit 1 trong toàn bộ 32/64 bit. Hàm này **không** đếm chữ số `1` trong chuỗi thập phân; cũng **không** đếm số bit cần dùng để biểu diễn độ lớn của số.

```java
int a = 0b1010_0101; // Bốn bit 1
int count = Integer.bitCount(a); // 4
long b = 0b1_0000_0000L;
int longCount = Long.bitCount(b); // 1
```

Số âm phải được tính theo bù hai: `Integer.bitCount(-1) == 32`, còn `Long.bitCount(-1L) == 64`. Điều này hữu ích khi làm việc với cờ bit (flags), bitmap, bitset nén trong số nguyên hoặc thuật toán Hamming distance: `Integer.bitCount(a ^ b)` là số vị trí bit khác nhau giữa hai mẫu `int`.

Ví dụ, nếu `permissions` là một tập cờ và `mask` chỉ định các quyền cần kiểm tra, `Integer.bitCount(permissions & mask)` đếm số quyền đã bật **trong phạm vi `mask`**. Đối với ứng dụng cần tập bit lớn hơn 64 bit, `java.util.BitSet` phù hợp hơn; `BitSet.cardinality()` đếm số bit 1 của tập đó.

## 4. Leading zeros: đếm bit 0 từ đầu cao

`numberOfLeadingZeros(x)` bắt đầu từ bit cao nhất (bit 31 của `int`, bit 63 của `long`) và đếm đến trước bit 1 đầu tiên. Một số dương có bit 1 cao nhất ở vị trí `p` thì:

- Với `int`: `p = 31 - Integer.numberOfLeadingZeros(x)` khi `x != 0`.
- Với `long`: `p = 63 - Long.numberOfLeadingZeros(x)` khi `x != 0`.

Với `x > 0`, số bit tối thiểu để biểu diễn dạng nhị phân không dấu chính là `Integer.SIZE - Integer.numberOfLeadingZeros(x)`. Ví dụ `40` cần 6 bit (`101000`), nên `32 - 26 = 6`.

Với `x == 0`, Java trả `32` hoặc `64` vì toàn bộ bit đều bằng 0; phải xử lý riêng nếu bài toán cần vị trí một bit 1. Với số âm, bit dấu cao nhất luôn bằng 1, nên số leading zeros bằng **0**, dù giá trị tuyệt đối lớn hay nhỏ.

```java
int x = 40;
int highestSetIndex = x == 0
        ? -1
        : Integer.SIZE - 1 - Integer.numberOfLeadingZeros(x);
// highestSetIndex == 5
```

Dùng `-1` trong đoạn trên là **quy ước do ứng dụng tự chọn** cho trường hợp không có bit 1, không phải giá trị trả trực tiếp của `numberOfLeadingZeros`.

## 5. Trailing zeros: đếm bit 0 từ đầu thấp

`numberOfTrailingZeros(x)` đếm bit 0 liên tiếp từ bit thấp nhất (bit 0) đến trước bit 1 đầu tiên. Khi `x != 0`, kết quả chính là **chỉ số của bit 1 thấp nhất**:

```java
int mask = 0b0010_1000; // 40
int lowestSetIndex = Integer.numberOfTrailingZeros(mask); // 3
```

Một số nguyên khác 0 chia hết cho `2^k` khi và chỉ khi ít nhất `k` bit thấp nhất bằng 0. Vì vậy trailing zeros cho biết số thừa số 2 của một số nguyên khác 0 theo biểu diễn bit (ví dụ `40 = 5 × 2^3`, nên có 3 bit 0 ở cuối). Công thức vẫn hữu ích với số âm khi cần thao tác trên mẫu bit, nhưng không dùng để suy ra dấu.

`Integer.numberOfTrailingZeros(0) == 32`, `Long.numberOfTrailingZeros(0L) == 64`. Đây là sentinel hợp lệ của API: không được đưa trực tiếp `32` vào `1 << index` với kỳ vọng tạo bit ở vị trí 32.

Trong bài toán liệt kê các bit đang bật, trailing zeros tìm ngay chỉ số bit thấp nhất; sau đó có thể xóa bit ấy và tiếp tục đến khi mẫu bit bằng 0.

## 6. `highestOneBit` và `lowestOneBit`: tạo mặt nạ chỉ có một bit 1

Hai hàm này trả về một **mặt nạ one-hot**: chỉ bit 1 cao nhất hoặc thấp nhất còn được giữ lại.

```java
int x = 0b0010_1000;          // 40
int high = Integer.highestOneBit(x); // 0b0010_0000 = 32
int low  = Integer.lowestOneBit(x);  // 0b0000_1000 = 8
```

Nếu `x == 0`, cả hai đều trả `0`. Nếu `x` âm, các hàm vẫn đọc toàn bộ mẫu 32/64 bit, không bỏ bit dấu. Do đó:

```java
int highNegative = Integer.highestOneBit(-1);
// Integer.MIN_VALUE, tức 0x80000000, hiển thị dạng int là -2147483648

long highNegativeLong = Long.highestOneBit(-1L);
// Long.MIN_VALUE, tức 0x8000000000000000
```

**Ý nghĩa kết quả phụ thuộc cách diễn giải signed/unsigned.** Bit dấu ở vị trí 31 biểu diễn mặt nạ `0x80000000`; nếu in như `int`, giá trị âm, nhưng nếu in như số nguyên không dấu thì đó là `2147483648`:

```java
String unsignedText =
        Integer.toUnsignedString(Integer.highestOneBit(-1));
// "2147483648"
```

Với **số dương** `x`, `highestOneBit(x)` là lũy thừa của 2 lớn nhất không vượt quá `x`; còn `lowestOneBit(x)` là lũy thừa của 2 ứng với bit 1 thấp nhất. Không đồng nhất `highestOneBit` với phép làm tròn lên lũy thừa 2: ví dụ `highestOneBit(40) == 32`, trong khi lũy thừa 2 tiếp theo là `64`.

Có thể nhận ra hai phép biến đổi bit tương đương khi thao tác trên mẫu bù hai:

- `x & -x` cô lập bit 1 thấp nhất, tương đương `lowestOneBit(x)`.
- `x & (x - 1)` **xóa** bit 1 thấp nhất, không tương đương `lowestOneBit(x)`.

Phép trừ một và đổi dấu ở đây dùng số nguyên Java có độ rộng cố định. Đối với mã ứng dụng, các phương thức tên rõ ràng của JDK thường dễ đọc và ít gây nhầm hơn.

## 7. Ví dụ Java 17 đầy đủ, chạy được

Lưu thành tệp `BitHelpersDemo.java`:

```java
public class BitHelpersDemo {
    public static void main(String[] args) {
        int x = 0b0010_1000; // 40: các bit 1 ở vị trí 5 và 3

        System.out.println("bitCount(40) = " + Integer.bitCount(x));
        System.out.println("leadingZeros(40) = "
                + Integer.numberOfLeadingZeros(x));
        System.out.println("trailingZeros(40) = "
                + Integer.numberOfTrailingZeros(x));
        System.out.println("highestOneBit(40) = "
                + Integer.highestOneBit(x));
        System.out.println("lowestOneBit(40) = "
                + Integer.lowestOneBit(x));

        System.out.println("leadingZeros(0) = "
                + Integer.numberOfLeadingZeros(0));
        System.out.println("trailingZeros(0) = "
                + Integer.numberOfTrailingZeros(0));
        System.out.println("bitCount(-1) = "
                + Integer.bitCount(-1));
        System.out.println("highestOneBit(-1), signed = "
                + Integer.highestOneBit(-1));
        System.out.println("highestOneBit(-1), unsigned = "
                + Integer.toUnsignedString(Integer.highestOneBit(-1)));

        long large = 1L << 40;
        System.out.println("Long.bitCount(2^40) = "
                + Long.bitCount(large));
        System.out.println("Long.leadingZeros(2^40) = "
                + Long.numberOfLeadingZeros(large));
        System.out.println("Long.trailingZeros(2^40) = "
                + Long.numberOfTrailingZeros(large));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BitHelpersDemo.java
java BitHelpersDemo
```

Đầu ra chính xác:

```text
bitCount(40) = 2
leadingZeros(40) = 26
trailingZeros(40) = 3
highestOneBit(40) = 32
lowestOneBit(40) = 8
leadingZeros(0) = 32
trailingZeros(0) = 32
bitCount(-1) = 32
highestOneBit(-1), signed = -2147483648
highestOneBit(-1), unsigned = 2147483648
Long.bitCount(2^40) = 1
Long.leadingZeros(2^40) = 23
Long.trailingZeros(2^40) = 40
```

Giải thích phép dịch `1L << 40`: chữ `L` đảm bảo phép dịch thực hiện trên `long` 64 bit. Kết quả có một bit 1 ở vị trí 40, nên có 40 bit 0 bên phải, 23 bit 0 bên trái và tổng cộng một bit 1.

## 8. Ứng dụng: duyệt nhanh từng cờ bit đang bật

Giả sử mỗi bit biểu diễn một tính năng được bật. Mẫu `0b101010` có các bit 1 tại vị trí 1, 3, 5. Có thể dùng `numberOfTrailingZeros` để tìm vị trí rồi xóa chính bit thấp nhất bằng `mask &= mask - 1`.

Lưu thành tệp `ActiveBitsDemo.java`:

```java
public class ActiveBitsDemo {
    public static void main(String[] args) {
        int mask = 0b101010;

        while (mask != 0) {
            int index = Integer.numberOfTrailingZeros(mask);
            System.out.println("Bit bat: " + index);
            mask &= mask - 1;
        }
    }
}
```

```bash
javac ActiveBitsDemo.java
java ActiveBitsDemo
```

```text
Bit bat: 1
Bit bat: 3
Bit bat: 5
```

Vòng lặp thực hiện đúng một lần cho mỗi bit 1, tức `Integer.bitCount(maskBanDau)` lượt. Nếu `mask` có bit dấu đang bật, cách này vẫn xử lý được vị trí 31; điều kiện `mask != 0` kiểm tra **mẫu bit**, không đòi hỏi giá trị phải dương. Để kiểm tra một bit cụ thể:

```java
int flags = 0b101010;
int index = 3;
boolean enabled = (flags & (1 << index)) != 0; // true
```

Ở đây `index` phải thuộc `0..31` với `int`; với `long`, dùng `1L << index` và giới hạn `0..63`.

## 9. Một số mẫu sử dụng hữu ích

### Kiểm tra mẫu bit có đúng một bit 1

```java
static boolean hasExactlyOneBitSet(int x) {
    return Integer.bitCount(x) == 1;
}
```

Hàm nhận cả `Integer.MIN_VALUE` là mẫu có đúng một bit 1. Nếu mục tiêu là kiểm tra **số nguyên dương** có phải lũy thừa của 2 hay không, cần thêm điều kiện `x > 0`:

```java
static boolean isPositivePowerOfTwo(int x) {
    return x > 0 && Integer.bitCount(x) == 1;
}
```

Hoặc dùng `x > 0 && (x & (x - 1)) == 0`. Điều kiện `x > 0` tránh nhầm `0` và số âm có duy nhất bit dấu. Với `long`, thay `Integer.bitCount` bằng `Long.bitCount`.

### Lấy chỉ số bit cao nhất và thấp nhất

```java
static int highestSetBitIndex(int x) {
    return x == 0 ? -1
            : Integer.SIZE - 1 - Integer.numberOfLeadingZeros(x);
}

static int lowestSetBitIndex(int x) {
    return x == 0 ? -1 : Integer.numberOfTrailingZeros(x);
}
```

Các hàm trả `-1` cho `0` theo quy ước riêng. Chúng có thể dùng với cả `int` âm vì chỉ số nói về **vị trí trong mẫu bit**. Ví dụ, `highestSetBitIndex(Integer.MIN_VALUE) == 31`.

### Đếm số bit khác nhau của hai số

```java
int a = 0b1010;
int b = 0b0011;
int hammingDistance = Integer.bitCount(a ^ b); // 2
```

XOR cho bit 1 tại những vị trí khác nhau; `bitCount` đếm chúng. Đây là phép so sánh 32 bit (hoặc 64 bit với `Long.bitCount`), kể cả với số âm.

## 10. Lưu ý và lỗi thường gặp

1. **Quên độ rộng bit cố định.** `bitCount(-1)` là `32`/`64`, không phải `1`, vì `-1` ở dạng bù hai toàn bit 1.
2. **Bỏ qua `0`.** `numberOfLeadingZeros(0)` và `numberOfTrailingZeros(0)` trả `Integer.SIZE`/`Long.SIZE`; còn `highestOneBit(0)` và `lowestOneBit(0)` đều trả `0`. Cần xử lý `0` trước khi tính chỉ số bit hay dịch `1` theo kết quả.
3. **Lẫn giữa vị trí và mặt nạ.** `numberOfTrailingZeros(40)` là **vị trí** `3`; `lowestOneBit(40)` là **giá trị mặt nạ** `8`. Tương tự, `highestOneBit(40)` là `32`, còn chỉ số bit cao nhất là `5`.
4. **Hiểu nhầm dấu của `highestOneBit` ở số âm.** Hàm có thể trả `Integer.MIN_VALUE` hoặc `Long.MIN_VALUE`; bit dấu vẫn là một bit 1 bình thường khi thao tác bit. Dùng `Integer.toUnsignedString`/`Long.toUnsignedString` nếu cần hiển thị không dấu.
5. **Dùng toán tử dịch với sai kiểu hoặc chỉ số ngoài biên.** `1 << 40` thực hiện trên `int` và Java chỉ dùng 5 bit thấp của lượng dịch, nên không tạo bit ở vị trí 40. Dùng `1L << 40` cho `long`; giới hạn chỉ số dịch hợp lệ theo nhu cầu `0..31`/`0..63`.
6. **Quên ưu tiên toán tử.** Nên viết `(x & (x - 1)) == 0` và `(flags & (1 << index)) != 0` với ngoặc rõ ràng.
7. **Dùng bit trick cho số 0 khi kiểm tra lũy thừa 2.** `(0 & (0 - 1)) == 0` đúng, nhưng `0` không phải lũy thừa 2. Bắt buộc kiểm tra `x > 0` nếu đang xét số nguyên dương.
8. **Nhầm leading/trailing zeros với bit đầu/cuối của chuỗi.** `Integer.toBinaryString(40)` trả `"101000"` (không tự đệm 26 số 0 đầu). Kết quả `numberOfLeadingZeros` vẫn tính trên toàn bộ 32 bit.

Các phương thức này diễn đạt rõ thao tác bit và thường được JVM tối ưu tốt, đôi khi bằng chỉ thị máy chuyên dụng; không nên mặc định chúng có tốc độ cố định trên mọi nền tảng hoặc tự thay thế bằng vòng lặp thủ công nếu chưa có phép đo.

## 11. Tự kiểm tra

1. Với `0b1001_0000` (`144`), `bitCount` bằng bao nhiêu? `numberOfTrailingZeros` bằng bao nhiêu? `highestOneBit` và `lowestOneBit` bằng bao nhiêu?
2. Vì sao `Integer.numberOfLeadingZeros(-8)` bằng `0`, dù `Integer.toBinaryString(-8)` dài 32 ký tự?
3. Vì sao `Integer.bitCount(Integer.MIN_VALUE) == 1` nhưng `Integer.MIN_VALUE` không phải lũy thừa 2 **dương**?
4. Điều gì xảy ra nếu lỡ tính `1 << Integer.numberOfTrailingZeros(0)`?

**Đáp án:** (1) Lần lượt `2`, `4`, `128`, `16`. (2) Bit dấu (bit 31) của mọi `int` âm bằng 1 nên không có bit 0 ở đầu. (3) Chỉ có bit dấu bật, giá trị được diễn giải là số âm. (4) Dịch `1 << 32` trên `int` tương đương `1 << 0`, cho `1`, vì Java chỉ xét 5 bit thấp của số lượng dịch; đó là lý do cần xử lý `0` trước.

**Ghi nhớ:** `bitCount` trả **số bit 1**; leading/trailing zeros trả **số bit 0 liên tiếp từ hai đầu mẫu bit**; `highestOneBit`/`lowestOneBit` trả **mặt nạ chứa đúng một bit 1** hoặc `0`. Luôn phân biệt kết quả là *số lượng*, *vị trí*, hay *mặt nạ*, và kiểm tra `0` trước khi suy ra chỉ số.