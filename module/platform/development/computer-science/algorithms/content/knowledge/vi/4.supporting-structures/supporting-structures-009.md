# Bitset và biểu diễn tập bằng các bit

> **Chủ đề:** Computer Science Algorithms → Cấu trúc hỗ trợ.  
> **Mục tiêu:** Hiểu cách ánh xạ một tập hữu hạn thành các bit, thực hiện phép toán tập hợp đúng và nhanh, chọn giữa `long`, `BitSet`, `BigInteger` và cấu trúc khác trong Java 17+, đồng thời vận dụng bitset vào duyệt tập con, đồ thị và quy hoạch động.

## 1. Bitset giải quyết bài toán gì?

Giả sử ta cần lưu một tập các phần tử khác nhau trong **vũ trụ hữu hạn** `U = {0, 1, ..., n-1}`. Thay vì giữ danh sách các chỉ số thuộc tập, ta gán cho mỗi phần tử `i` **một bit**:

- Bit thứ `i` bằng `1` ⇔ phần tử `i` thuộc tập.
- Bit thứ `i` bằng `0` ⇔ phần tử `i` không thuộc tập.

Đây là **bitset** (tập biểu diễn bằng bit). Nếu toàn bộ vũ trụ nhỏ, các bit có thể nằm trong một số nguyên 32/64 bit gọi là **bitmask**. Nếu vũ trụ lớn, bitset dùng nhiều từ máy liên tiếp. Hai cách cùng biểu diễn tập hợp; khác ở khả năng mở rộng và API.

Với `U={0,1,2,3,4,5,6,7}`, tập `A={1,3,5}` có bit 1, 3, 5 bật:

```text
Chỉ số bit:   7 6 5 4 3 2 1 0
Trạng thái A: 0 0 1 0 1 0 1 0
Nhị phân:     00101010
Giá trị số:   2^5 + 2^3 + 2^1 = 42
```

Bit `0` là bit thấp nhất (bên phải khi viết nhị phân). Cần thống nhất quy ước đánh số; nhầm hướng bit thường dẫn đến kết quả sai dù biểu thức `&` hoặc `|` có vẻ hợp lệ.

**Ý nghĩa thuật toán:** các phép hợp, giao, hiệu và hiệu đối xứng trên tập có thể được thực hiện trên **nhiều phần tử cùng lúc** nhờ các phép toán bit của CPU. Với vũ trụ lớn nhưng không quá thưa, đây là một cấu trúc hỗ trợ rất hữu ích.

**Điều kiện mô hình hóa:** bitset thông thường chỉ biểu diễn **tư cách thành viên**, không biểu diễn số lần xuất hiện. Nếu một giá trị xuất hiện 5 lần, đặt bit của nó vẫn chỉ cho biết “có xuất hiện”. Muốn lưu tần suất, dùng mảng đếm, map hoặc cấu trúc khác.

## 2. Tập hợp tương ứng với phép toán bit

Gọi `A` và `B` là hai tập trên **cùng vũ trụ và cùng cách đánh số**. Những phép toán sau đúng theo từng bit:

| Phép tập hợp | Biểu thức bit | Ý nghĩa đối với phần tử `i` |
|---|---|---|
| Hợp `A ∪ B` | `a | b` | Thuộc `A` **hoặc** `B` |
| Giao `A ∩ B` | `a & b` | Thuộc **cả hai** |
| Hiệu `A \ B` | `a & ~b` | Thuộc `A`, không thuộc `B` |
| Hiệu đối xứng `A △ B` | `a ^ b` | Thuộc đúng **một** trong hai |
| Phần bù `U \ A` | `~a & universeMask` | Không thuộc `A` nhưng nằm trong `U` |
| Kiểm tra rời nhau | `(a & b) == 0` | Không có phần tử chung |
| Kiểm tra tập con | `(a & ~b) == 0` | Mọi phần tử của `A` đều thuộc `B` |
| Kiểm tra bằng nhau | `a == b` | Các bit thành viên tương ứng bằng nhau |

Trong bảng, `a`, `b` là **bitmask của tập**, không phải số lượng phần tử. Biểu thức bitwise `&`, `|`, `^`, `~` khác các toán tử logic ngắn mạch `&&`, `||` dùng cho giá trị `boolean`.

Ví dụ:

```text
A = {1,3,5}       00101010
B = {3,4}         00011000
---------------------------------
A | B             00111010 = {1,3,4,5}
A & B             00001000 = {3}
A & ~B            00100010 = {1,5}
A ^ B             00110010 = {1,4,5}
```

### 2.1. Vì sao các phép toán này đúng?

Chỉ cần xét **một bit bất kỳ** vì các vị trí bit hoạt động độc lập. Đặt `a_i` và `b_i` là hai bit tương ứng:

- `a_i | b_i` bằng `1` khi ít nhất một trong hai bit là `1` → đúng định nghĩa hợp.
- `a_i & b_i` bằng `1` khi cả hai là `1` → đúng định nghĩa giao.
- `a_i & ~b_i` bằng `1` khi `a_i=1`, `b_i=0` → đúng định nghĩa hiệu.
- `a_i ^ b_i` bằng `1` khi hai bit khác nhau → đúng định nghĩa hiệu đối xứng.

Vì lập luận đúng cho mọi vị trí `i`, toàn bộ bitset biểu diễn đúng phép tập hợp. Đây cũng là cách chứng minh các tối ưu hóa bitset: **kiểm tra tương đương theo từng bit** thay vì chỉ thử vài giá trị số.

### 2.2. Phần bù luôn cần vũ trụ

`~a` lật **mọi bit của kiểu dữ liệu**, kể cả những bit không đại diện phần tử hợp lệ. Nếu `U={0,...,5}` thì phần bù của `{1,3,5}` phải là `{0,2,4}`. Với một `long`, `~a` còn lật cả bit 6..63. Cần giữ lại sáu bit thấp bằng một `universeMask`.

Với `0 <= n < 64` có thể dùng `(1L << n) - 1`. **Trường hợp `n=64` phải xử lý riêng** bằng `-1L`, vì Java che số bước dịch bằng 6 bit: `1L << 64` tương đương `1L << 0`, không phải số có 65 bit. Tập rỗng `n=0` có universe mask bằng `0`.

## 3. Bitmask trong Java 17: `int` và `long`

Java cung cấp toán tử bit trên số nguyên:

- `&`, `|`, `^`, `~`: giao/hợp/XOR/đảo bit.
- `<<`: dịch trái; `1L << i` tạo bit đơn tại vị trí `i`, khi `0<=i<64`.
- `>>`: dịch phải **giữ dấu**; bit dấu được sao chép khi dịch.
- `>>>`: dịch phải **không giữ dấu**; các bit cao mới điền bằng `0`.
- `Integer.bitCount(x)`, `Long.bitCount(x)`: đếm số bit `1`.
- `Long.numberOfTrailingZeros(x)`: số bit `0` liên tiếp từ bit thấp; với `x != 0`, đó là vị trí bit `1` thấp nhất.

`int` có **32 bit**, `long` có **64 bit**. Viết `1 << i` thực hiện phép dịch trên `int`; viết `1L << i` mới dùng `long`. Với một tập có đến 64 phần tử đánh số `0..63`, dùng `long` là hợp lý, nhưng giá trị số có thể **âm** khi bit 63 bật. Điều đó **không có nghĩa tập rỗng hoặc dữ liệu sai**: các bit thành viên vẫn hợp lệ.

### 3.1. Các thao tác trên một phần tử

Với `long mask` và chỉ số hợp lệ `i`:

```java
long bit = 1L << i;          // Bit đơn cho phần tử i
mask |= bit;                 // Thêm i
mask &= ~bit;                // Xóa i
mask ^= bit;                 // Đảo trạng thái i
boolean exists = (mask & bit) != 0L; // Kiểm tra có i
```

Các thao tác trên `long` có chi phí `O(1)` theo mô hình từ máy cố định. Khi giải bài toán có `n>64`, không thể chỉ dịch vượt 63 để có thêm vị trí mới; cần nhiều từ máy hoặc `BitSet`.

### 3.2. Ví dụ chạy được: các phép tập hợp

Lưu thành **BitMaskSetDemo.java**:

```java
import java.util.StringJoiner;

public class BitMaskSetDemo {
    static long bit(int index) {
        if (index < 0 || index >= 64) {
            throw new IllegalArgumentException("Bit index must be 0..63");
        }
        return 1L << index;
    }

    static long universeMask(int n) {
        if (n < 0 || n > 64) {
            throw new IllegalArgumentException("Universe size must be 0..64");
        }
        return n == 64 ? -1L : (1L << n) - 1L;
    }

    static boolean contains(long mask, int index) {
        return (mask & bit(index)) != 0L;
    }

    static String asSet(long mask, int universeSize) {
        StringJoiner joiner = new StringJoiner(", ", "{", "}");
        for (int i = 0; i < universeSize; i++) {
            if (contains(mask, i)) {
                joiner.add(Integer.toString(i));
            }
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        int n = 6;
        long a = bit(1) | bit(3) | bit(5);
        long b = bit(3) | bit(4);

        System.out.println("A = " + asSet(a, n));
        System.out.println("B = " + asSet(b, n));
        System.out.println("Union = " + asSet(a | b, n));
        System.out.println("Intersection = " + asSet(a & b, n));
        System.out.println("A minus B = " + asSet(a & ~b, n));
        System.out.println("Xor = " + asSet(a ^ b, n));
        System.out.println("Complement(A) = "
                + asSet(~a & universeMask(n), n));
        System.out.println("B has 5 = " + contains(b, 5));
        System.out.println("A count = " + Long.bitCount(a));
        System.out.println("Bit 63 count = " + Long.bitCount(bit(63)));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 BitMaskSetDemo.java
java BitMaskSetDemo
```

Kết quả:

```text
A = {1, 3, 5}
B = {3, 4}
Union = {1, 3, 4, 5}
Intersection = {3}
A minus B = {1, 5}
Xor = {1, 4, 5}
Complement(A) = {0, 2, 4}
B has 5 = false
A count = 3
Bit 63 count = 1
```

`Long.bitCount(bit(63))` bằng `1` dù số `long` tạo ra mang dấu âm. Vì thế không dùng biểu thức `mask > 0` để hỏi tập có rỗng không; dùng `mask != 0L`.

**Lưu ý về giới hạn:** hàm `asSet` quét từ `0` tới `universeSize-1`, nên mất `O(n)` để **in** ra biểu diễn. Bản thân các phép `|`, `&`, `^`, `~` của `long` vẫn là `O(1)`.

## 4. Java `BitSet`: tập lớn hơn một từ máy

`java.util.BitSet` là cấu trúc bit có khả năng **mở rộng khi cần**. Một phần tử được xác định bằng chỉ số `int` không âm. `BitSet` thích hợp khi vũ trụ hàng trăm, hàng nghìn hoặc hàng triệu chỉ số có miền đủ đặc để dùng bitset hiệu quả.

Các thao tác thông dụng:

| API | Tác dụng | Ghi chú |
|---|---|---|
| `set(i)` | Bật bit `i` | Có thể làm vùng lưu trữ mở rộng |
| `get(i)` | Trả `true` nếu bit `i` bật | Chỉ số không âm |
| `clear(i)` | Tắt bit `i` | Không đồng nghĩa xóa một phần tử khỏi danh sách có thứ tự |
| `flip(i)` | Đảo bit `i` | Từ 0→1 hoặc 1→0 |
| `set(from,to)` | Bật các bit trong `[from,to)` | Biên phải **không** bao gồm |
| `clear(from,to)` / `flip(from,to)` | Xóa/đảo một đoạn bit | Cũng dùng đoạn nửa mở |
| `or(other)` | Hợp | **Biến đổi đối tượng nhận** |
| `and(other)` | Giao | **Biến đổi đối tượng nhận** |
| `andNot(other)` | Hiệu tập hợp | **Biến đổi đối tượng nhận** |
| `xor(other)` | Hiệu đối xứng | **Biến đổi đối tượng nhận** |
| `cardinality()` | Đếm bit `1` | Số phần tử của tập |
| `nextSetBit(start)` | Vị trí bit `1` tiếp theo | Trả `-1` nếu không có |
| `nextClearBit(start)` | Vị trí bit `0` tiếp theo | Không tự giới hạn ở vũ trụ của bài |
| `length()` | Chỉ số bit bật cao nhất + 1 | Trả `0` khi mọi bit bằng `0` |
| `size()` | Số bit của dung lượng lưu trữ hiện tại | **Không** phải số phần tử tập |
| `clone()` | Sao chép bitset | Hữu ích khi không muốn sửa dữ liệu gốc |

`new BitSet(1000)` chỉ cung cấp *gợi ý dung lượng ban đầu*; nó **không bật 1000 bit**. `length()`, `size()` và `cardinality()` trả các khái niệm khác nhau; trong thực hành đếm phần tử bằng `cardinality()`.

### 4.1. Tính đột biến (*mutation*) của các phép toán

Các phương thức `a.or(b)`, `a.and(b)`, `a.andNot(b)` và `a.xor(b)` **thay đổi trực tiếp `a`**. Nếu còn cần dùng `a` về sau, phải sao chép trước:

```java
BitSet union = (BitSet) a.clone();
union.or(b);
```

Nếu viết `BitSet union = a;`, `union` và `a` là **cùng một đối tượng**; chỉnh `union` làm `a` đổi theo. Đây là nguồn lỗi phổ biến khi một bitset đóng vai trò cache/trạng thái có thể được tái sử dụng.

### 4.2. Ví dụ chạy được: hợp, giao, hiệu và phần bù có giới hạn

Lưu thành **BitSetOperationsDemo.java**:

```java
import java.util.BitSet;

public class BitSetOperationsDemo {
    static BitSet of(int... indices) {
        BitSet result = new BitSet();
        for (int index : indices) {
            result.set(index);
        }
        return result;
    }

    public static void main(String[] args) {
        int universe = 12; // Các phần tử hợp lệ: 0..11.
        BitSet a = of(1, 3, 8);
        BitSet b = of(3, 9);

        BitSet union = (BitSet) a.clone();
        union.or(b);

        BitSet intersection = (BitSet) a.clone();
        intersection.and(b);

        BitSet difference = (BitSet) a.clone();
        difference.andNot(b);

        BitSet xor = (BitSet) a.clone();
        xor.xor(b);

        BitSet complement = (BitSet) a.clone();
        complement.flip(0, universe);

        System.out.println("A: " + a);
        System.out.println("B: " + b);
        System.out.println("A | B: " + union);
        System.out.println("A & B: " + intersection);
        System.out.println("A minus B: " + difference);
        System.out.println("A ^ B: " + xor);
        System.out.println("Not A in [0,12): " + complement);
        System.out.println("A cardinality: " + a.cardinality());
        System.out.println("A length: " + a.length());
        System.out.println("Next bit from 4: " + a.nextSetBit(4));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BitSetOperationsDemo.java
java BitSetOperationsDemo
```

Kết quả:

```text
A: {1, 3, 8}
B: {3, 9}
A | B: {1, 3, 8, 9}
A & B: {3}
A minus B: {1, 8}
A ^ B: {1, 8, 9}
Not A in [0,12): {0, 2, 4, 5, 6, 7, 9, 10, 11}
A cardinality: 3
A length: 9
Next bit from 4: 8
```

`flip(0, universe)` đảo đúng các bit nằm trong **vũ trụ được khai báo**. Chỉ dùng cách này để lấy phần bù nếu `a` vốn không chứa phần tử ngoài vũ trụ; nếu không, cần chuẩn hóa hoặc kiểm tra miền chỉ số trước.

### 4.3. Duyệt các phần tử đã bật

Có thể duyệt toàn bộ vũ trụ bằng `get(i)`, nhưng khi tập khá thưa, `nextSetBit` tránh kiểm tra từng vị trí không có phần tử:

```java
for (int i = bits.nextSetBit(0);
     i >= 0 && i < universeSize;
     i = bits.nextSetBit(i + 1)) {
    System.out.println(i);
}
```

Đoạn trên minh họa với vũ trụ nhỏ có `universeSize` hợp lệ. Nếu có thể bật bit tại `Integer.MAX_VALUE`, `i + 1` bị tràn; cần thoát vòng trước khi tăng `i` ở giá trị đó. Trong ứng dụng thông thường, kiểm tra chỉ số cực đại theo miền dữ liệu thực tế.

`BitSet` không có phương thức `shiftLeft` giống số nguyên hay `BigInteger`; đừng nhầm `get(from,to)` (lấy đoạn bit và đổi chỉ số về 0) với thao tác dịch toàn bộ bitset theo nghĩa cộng vào các vị trí.

## 5. Duyệt bit đang bật nhanh hơn quét toàn bộ 64 vị trí

Với `long mask`, có hai mẹo hữu ích:

- `mask & -mask` lấy **bit `1` thấp nhất** (dưới dạng một bit đơn).
- `mask & (mask - 1)` xóa **bit `1` thấp nhất**.

Lý do: trong biểu diễn bù hai, phép trừ `1` làm các bit thấp bên dưới bit `1` thấp nhất đổi trạng thái và làm chính bit đó tắt; AND với mask gốc giữ lại tất cả bit `1` cao hơn, bỏ đi bit thấp nhất. Đặc tính vẫn đúng khi `long` có bit dấu bật.

Lưu thành **BitIterationDemo.java**:

```java
public class BitIterationDemo {
    public static void main(String[] args) {
        long mask = (1L << 0) | (1L << 2) | (1L << 63);
        System.out.println("Count: " + Long.bitCount(mask));

        long remaining = mask;
        while (remaining != 0L) {
            int index = Long.numberOfTrailingZeros(remaining);
            System.out.println("Set bit: " + index);
            remaining &= remaining - 1L;
        }
    }
}
```

```bash
javac -encoding UTF-8 BitIterationDemo.java
java BitIterationDemo
```

```text
Count: 3
Set bit: 0
Set bit: 2
Set bit: 63
```

Vòng lặp có đúng `k` bước với `k` là số bit bật, nên tốn `O(k)` thay vì phải quét 64 vị trí. Với tập số bit cố định, cả hai đều có chặn hằng nhưng kỹ thuật này đặc biệt hữu ích trong duyệt trạng thái và mặt nạ thưa.

**Không gọi `Long.numberOfTrailingZeros(0L)` để suy ra vị trí phần tử:** Java trả `64` cho đầu vào `0`, không phải chỉ số của một bit tồn tại. Kiểm tra `remaining != 0L` trước khi lấy chỉ số.

## 6. Duyệt tập con và trạng thái tổ hợp

Một mặt nạ `mask` đại diện một tập con của `n` phần tử. Nếu `n` đủ nhỏ để duyệt hết, số trạng thái là `2^n`.

### 6.1. Duyệt mọi tập con của n phần tử

Với `0 <= n <= 20` trong ví dụ thực tế (n lớn hơn phải đánh giá lại thời gian và bộ nhớ):

```java
int n = 4;
int limit = 1 << n;
for (int mask = 0; mask < limit; mask++) {
    // Từng mask đại diện đúng một tập con của {0,1,2,3}.
}
```

Bởi mỗi phần tử có hai lựa chọn “chọn” hoặc “không chọn”, ánh xạ giữa tập con và chuỗi `n` bit là một-một. Vòng trên liệt kê chính xác `2^n` trạng thái. Nếu kiểm tra từng bit cho mỗi mask thì tổng chi phí `O(n · 2^n)`; nếu xử lý mask trong `O(1)` thì riêng vòng lặp tốn `O(2^n)`.

**Cẩn thận:** `1 << n` dùng 32 bit; với `n>=31`, giới hạn có thể âm hoặc sai. `1L << n` tăng miền dịch lên 64 bit nhưng không làm thời gian `2^n` trở nên khả thi cho `n` lớn. Java giới hạn số bước dịch `int` bằng 5 bit và `long` bằng 6 bit, nên `1 << 32` có cùng kết quả với `1 << 0`.

### 6.2. Duyệt các tập con của một mặt nạ cho trước

Với `mask` có `k` bit bật, tất cả **tập con** của mask có thể duyệt như sau:

```java
int mask = 0b10110; // Tập {1,2,4}.
for (int sub = mask; ; sub = (sub - 1) & mask) {
    // Xử lý sub: sub là một tập con của mask, gồm cả mask và 0.
    if (sub == 0) {
        break;
    }
}
```

Công thức `(sub-1)&mask` đi lần lượt qua các tập con theo thứ tự giá trị giảm. Kiểm tra `sub==0` **sau khi xử lý** để vẫn tính cả tập rỗng; nếu quên dừng, `(0-1)&mask` quay lại `mask`.

Với `mask = 0b10110` (ba bit bật), thứ tự là:

```text
10110, 10100, 10010, 10000, 00110, 00100, 00010, 00000
```

Có đúng `2^k` tập con. Nếu phải lặp trên **mọi mask** của `n` phần tử và duyệt tất cả `sub ⊆ mask`, số cặp `(mask,sub)` là `3^n`: mỗi phần tử hoặc không thuộc mask, hoặc thuộc mask nhưng không thuộc sub, hoặc thuộc cả hai.

### 6.3. Bitmask DP

Nhiều bài toán tối ưu trạng thái theo tập đã chọn: `dp[mask]` có thể là chi phí nhỏ nhất sau khi chọn đúng tập `mask`. Khi còn cần biết phần tử cuối, dùng `dp[mask][last]`.

Ví dụ kinh điển là bài toán người du lịch phiên bản DP theo tập con (*Held–Karp*): `mask` xác định các thành phố đã ghé, `last` xác định thành phố hiện tại. Một cách cài đặt thông dụng dùng `O(n·2^n)` trạng thái và `O(n²·2^n)` phép chuyển, nên thực tế chỉ phù hợp khi `n` tương đối nhỏ.

**Điều quan trọng:** bitmask nén biểu diễn trạng thái; nó **không tự giảm số trạng thái `2^n`**. Lợi ích nằm ở việc kiểm tra/thêm/xóa thành viên và lưu trạng thái gọn, nhanh, chính xác.

## 7. Bitset trong bài toán tổng tập con (*subset sum*)

Cho các trọng lượng nguyên không âm `w1, ..., wn`; mỗi phần tử được sử dụng **tối đa một lần**. Ta cần biết các tổng nào có thể tạo được.

Ý tưởng: bit thứ `s` bật ⇔ có một tập con đã xét có tổng đúng `s`. Ban đầu chỉ tổng `0` có thể đạt, nên bitset chứa duy nhất bit `0`:

```text
reachable = ...00001      (bit 0 bật)
```

Khi xét một món có trọng lượng `w`, các tổng mới gồm:

1. **Không chọn món:** những tổng cũ, biểu diễn bằng `reachable`.
2. **Chọn món:** mỗi tổng cũ `s` tạo tổng `s+w`, biểu diễn bằng `reachable << w`.

Vậy bước chuyển là:

`newReachable = reachable OR (reachable << w)`.

Phép OR phải được thực hiện với **trạng thái trước khi thêm món**, nếu không có thể vô tình dùng một món nhiều lần.

### 7.1. Java 17: dùng `BigInteger` để dịch bit

`BigInteger` cung cấp `shiftLeft`, `or`, `testBit`; đối tượng là **bất biến**, rất phù hợp để minh họa công thức trên. Khi chỉ dùng số không âm, bit thứ `s` tương ứng trực tiếp với tổng `s`.

Lưu thành **SubsetSumBitsDemo.java**:

```java
import java.math.BigInteger;

public class SubsetSumBitsDemo {
    public static void main(String[] args) {
        int[] weights = {3, 5, 8};
        BigInteger reachable = BigInteger.ONE; // Chỉ tổng 0.

        for (int weight : weights) {
            if (weight < 0) {
                throw new IllegalArgumentException("Weights must be nonnegative");
            }
            reachable = reachable.or(reachable.shiftLeft(weight));
        }

        int[] targets = {0, 3, 4, 5, 8, 11, 13, 16};
        for (int target : targets) {
            System.out.println(target + " -> " + reachable.testBit(target));
        }
    }
}
```

```bash
javac -encoding UTF-8 SubsetSumBitsDemo.java
java SubsetSumBitsDemo
```

```text
0 -> true
3 -> true
4 -> false
5 -> true
8 -> true
11 -> true
13 -> true
16 -> true
```

Các tập con của `{3,5,8}` tạo những tổng `0,3,5,8,11,13,16`; tổng `8` có thể đến từ `{8}` hoặc `{3,5}`, nhưng bit `8` chỉ cần bật một lần.

### 7.2. Vì sao bước chuyển đúng?

Giả sử trước khi xét món mới, `reachable` mô tả **chính xác** tập các tổng đạt được bằng những món đã xét (giả thiết quy nạp). Bất kỳ tập con của những món sau khi thêm `w` đều thuộc đúng một trong hai trường hợp:

- Không chứa `w` → tổng là một bit đã bật trước đó.
- Chứa `w` → bỏ `w` còn một tập con của món cũ với tổng `s`, nên tổng mới là `s+w`, nằm trong phần dịch trái.

Hai trường hợp bao phủ mọi khả năng và không tạo tổng không hợp lệ; OR cho tập tổng mới chính xác. Đây là ví dụ bitset **hỗ trợ quy hoạch động**, không phải một kỹ thuật độc lập thay thế chứng minh DP.

### 7.3. Độ phức tạp và ranh giới áp dụng

Gọi `W` là tổng tất cả trọng lượng, `n` là số món và `wordBits` là số bit mỗi từ lưu trữ (thường xét ở mức 32 hoặc 64). Trên mô hình thao tác theo từ máy, OR/dịch bit của một bitset dài tới `W+1` có chi phí cỡ `O(W/wordBits)` mỗi món, tổng `O(n·W/wordBits)` phép xử lý từ và `O(W/wordBits)` từ lưu trữ, chưa kể chi phí cấp phát bản sao trong thư viện.

Đây là thuật toán **giả đa thức** theo giá trị `W`: nếu trọng lượng rất lớn nhưng viết bằng ít chữ số, số bit cần có cũng rất lớn. `BigInteger` không phải lựa chọn tốt cho mọi bộ dữ liệu.

Với `BitSet` Java, không có lệnh dịch toàn bộ bitset dựng sẵn. Có thể tự hiện thực bước chuyển hoặc dùng `BigInteger` như trên. Nếu cập nhật một mảng `boolean[]` hoặc `BitSet` **tại chỗ** cho phiên bản 0/1, duyệt tổng `s` **giảm dần** để tránh tái sử dụng món đang xét. Với bài toán dùng mỗi món không giới hạn, thứ tự chuyển khác.

## 8. Ứng dụng trong đồ thị, lọc dữ liệu và giao tập

### 8.1. Danh sách kề dạng bitset

Với đồ thị có `V` đỉnh đánh số `0..V-1`, đặt `neighbors[u]` là bitset của các đỉnh kề với `u`. Khi đó:

- Kiểm tra có cạnh `u → v`: `neighbors[u].get(v)` (truy xuất một bit).
- Lấy các hàng xóm chung của `u` và `v`: sao chép bitset rồi `and`.
- Đếm số hàng xóm chung: lấy `cardinality()` sau phép giao.
- Gộp tập đỉnh đã thăm hoặc tập ứng viên: dùng `or`/`andNot`.

Mã minh họa phần **giao hàng xóm** (đây là đoạn bổ trợ, không phải chương trình độc lập):

```java
BitSet common = (BitSet) neighbors[u].clone();
common.and(neighbors[v]);
int numberOfCommonNeighbors = common.cardinality();
```

Nếu đồ thị **dày**, bitset cạnh có thể tiết kiệm so với việc duyệt nhiều phần tử riêng lẻ khi giao hàng xóm. Nếu đồ thị **rất thưa** và số đỉnh lớn, danh sách kề hoặc tập băm có thể tốn ít bộ nhớ hơn.

Một ma trận kề kiểu bitset cần tới cỡ `V²` bit để biểu diễn mọi cặp đỉnh, chưa kể overhead đối tượng. Biểu diễn danh sách kề cho đồ thị thưa có chi phí theo số đỉnh và cạnh, nên cần so sánh theo dữ liệu thực tế.

### 8.2. Lọc điều kiện trên tập ID

Giả sử mỗi thuộc tính của một đối tượng tương ứng một bitset chỉ số các ID thỏa thuộc tính đó. Truy vấn:

> “Có thuộc tính X và Y, nhưng không có Z”

có thể biểu diễn bằng `X AND Y AND NOT Z`. Bitset hỗ trợ kết hợp nhiều điều kiện hàng loạt và đếm số kết quả bằng phép đếm bit. Tuy vậy, mỗi đối tượng phải có **chỉ số ổn định**; nếu ID là chuỗi hoặc số cực lớn, cần ánh xạ ID → vị trí 0-based qua từ điển hoặc nén tọa độ.

### 8.3. Những bài toán thường được lợi

- Sàng Eratosthenes: đánh dấu số nguyên là nguyên tố/hợp số bằng bitset.
- Tìm tập phần tử chung giữa nhiều danh sách có vũ trụ xác định.
- Quy hoạch động theo tập đã chọn, kiểm tra trùng trạng thái.
- Biểu diễn các trạng thái `visited` khi vũ trụ nhỏ.
- Xử lý đồ thị có bitset hàng xóm, đếm/giao các tập đỉnh.
- Lọc hàng loạt theo điều kiện boolean khi các chỉ số đủ đặc.

Các ứng dụng này vẫn yêu cầu phân tích **cả thuật toán**, không thể kết luận tổng thời gian `O(1)` chỉ vì có một phép `&` trên mỗi bước.

## 9. Chi phí: bitset có thực sự tiết kiệm?

Gọi:

- `U` là số phần tử có thể có trong vũ trụ.
- `k` là số phần tử thực sự thuộc tập, `0<=k<=U`.
- `w` là số bit trên một từ máy (thường 64 trong phân tích lý thuyết).

| Cấu trúc | Lưu trữ ý tưởng | Truy vấn thành viên | Hợp/giao hai tập |
|---|---|---|---|
| `long` (U ≤ 64) | 64 bit | `O(1)` | `O(1)` |
| Bitset nhiều từ | Khoảng `U` bit + overhead | `O(1)` cho bit trong vùng đã cấp phát; có thể mở rộng khi `set` | `O(ceil(U/w))` cho quét toàn miền |
| `boolean[U]` | Một phần tử boolean cho mỗi chỉ số, dung lượng JVM phụ thuộc cài đặt | `O(1)` | `O(U)` thao tác phần tử thông thường |
| `HashSet<Integer>` | Bộ nhớ theo `k` phần tử và overhead băm/đối tượng | Kỳ vọng `O(1)` | Thường xét/tìm theo số phần tử được duyệt |
| Danh sách chỉ số có thứ tự | Theo `k` | Tìm nhị phân `O(log k)` | Trộn hai danh sách đã sắp xếp `O(kA+kB)` |

Các độ phức tạp ở bảng là mức **thuật toán**; thời gian cụ thể phụ thuộc việc cấp phát bộ nhớ, số từ máy đã sử dụng và cách thư viện triển khai. `BitSet` có thể nở khi bật bit ở chỉ số lớn; vì vậy một thao tác `set(i)` vượt dung lượng hiện tại có thể cần cấp phát/sao chép, không phải mọi thao tác có chặn xấu nhất cố định.

**Ví dụ về dữ liệu thưa:** tập `{7, 1_000_000_000}` có chỉ hai phần tử nhưng vũ trụ rất lớn. Dùng một `BitSet` trực tiếp trên chỉ số hàng tỷ tốn nhiều bộ nhớ; `HashSet<Integer>` hoặc nén tọa độ thành `{0,1}` có thể phù hợp hơn.

**Không nhầm tốc độ với bộ nhớ:** bitset thường nhanh khi kết hợp nhiều tập vì sử dụng song song các bit trong mỗi từ; nhưng nếu chỉ hỏi vài ID trên một vũ trụ rất rộng và thưa, chi phí biểu diễn có thể vượt lợi ích.

## 10. Những lỗi Java thường gặp

### 10.1. Dịch sai kiểu và sai chỉ số

```java
long wrong = 1 << 40;  // Phép dịch diễn ra trên int: 40 & 31 = 8.
long right = 1L << 40; // Phép dịch đúng trên long, chỉ số 40.
```

Java sử dụng 5 bit thấp của số bước dịch với `int` và 6 bit thấp với `long`. Vì vậy `1L << 64` bằng `1L`, còn `1 << 32` bằng `1`. Phải xác thực chỉ số hợp lệ trước khi dịch.

### 10.2. Nhầm bit dấu với lỗi dữ liệu

`1L << 63` là một giá trị `long` âm, nhưng **chính xác** là mặt nạ của bit 63. Các phép `&`, `|`, `^`, `Long.bitCount` vẫn hoạt động theo bit. Nếu cần so sánh **thứ tự không dấu** của hai mask, cân nhắc `Long.compareUnsigned`; nếu chỉ cần kiểm tra có phần tử hay không, dùng `mask != 0L`.

### 10.3. Lật tất cả bit mà không chặn vũ trụ

`~mask` lật cả bit nằm ngoài `0..U-1`. Khi chỉ có `n` phần tử hợp lệ, dùng `(~mask) & universeMask(n)` cho `long` hoặc `bitset.flip(0,n)` với BitSet đã được giới hạn miền.

### 10.4. Đánh đồng phép gán tham chiếu và sao chép

```java
BitSet a = new BitSet();
BitSet alias = a;
alias.set(3); // a cũng có bit 3 vì alias và a là cùng đối tượng.
```

Muốn hai đối tượng độc lập, dùng `(BitSet) a.clone()`.

### 10.5. Nhầm `size`, `length`, `cardinality`

- `cardinality()` là số bit `1`.
- `length()` là chỉ số bit `1` cao nhất cộng một, hoặc `0` nếu tập rỗng.
- `size()` là dung lượng lưu trữ theo số bit, có thể lớn hơn `length()` và thường khác `cardinality()`.

Dùng `cardinality()` để đếm phần tử tập.

### 10.6. Mất thông tin khi cần tần suất hoặc thứ tự

Bitset chỉ biểu diễn **có/không**, không giữ nguyên thứ tự thêm vào, không giữ số lần xuất hiện. Nếu bài toán cần “xuất hiện 3 lần” hoặc thứ tự duyệt nguồn, phải lưu thêm dữ liệu.

### 10.7. Sai khi ghép các hệ đánh số

Nếu bit `5` trong tập A biểu diễn “Khách hàng X” nhưng bit `5` trong tập B biểu diễn “Khách hàng Y”, phép `A & B` không có nghĩa tập hợp hợp lệ. Cần dùng cùng một từ điển ánh xạ phần tử → chỉ số.

### 10.8. Chia sẻ `BitSet` có thể sửa giữa nhiều luồng

`BitSet` không tự cung cấp bảo đảm an toàn luồng cho các thao tác ghi đồng thời. Nếu nhiều luồng sửa hoặc đọc trong khi sửa, cần đồng bộ hóa, phân vùng dữ liệu hoặc thiết kế snapshot bất biến phù hợp.

## 11. Kiểm tra bằng bài tập nhỏ

**Bài 1.** Trong vũ trụ `U={0,...,7}`, cho `X={0,2,5}` và `Y={2,6}`. Tính hợp, giao, hiệu `X\Y` và hiệu đối xứng.

**Đáp án:** `X∪Y={0,2,5,6}`; `X∩Y={2}`; `X\Y={0,5}`; `X△Y={0,5,6}`.

**Bài 2.** Phần bù của `X={0,2,5}` trong `U={0,...,7}` là gì?

**Đáp án:** `{1,3,4,6,7}`. Nếu chỉ viết `~maskX` bằng một `long` mà không chặn vũ trụ, đáp án bao gồm các bit không thuộc U và bị sai.

**Bài 3.** `mask=0b10110` có bao nhiêu tập con, kể cả tập rỗng?

**Đáp án:** `mask` có ba bit `1` (vị trí 1, 2, 4), nên có `2^3=8` tập con. Đoạn duyệt submask ở phần 6 liệt kê đủ 8 tập con.

**Bài 4.** `new BitSet(1024)` có `cardinality()` và `length()` ban đầu bằng bao nhiêu?

**Đáp án:** đều bằng `0`, vì chưa bật bit nào. `size()` biểu diễn dung lượng hiện tại, không phải số bit đã bật.

**Bài 5.** Vì sao công thức `reachable |= reachable << w` không thể dùng nguyên xi với `BitSet` trong Java?

**Đáp án:** `BitSet` không có toán tử dịch toàn bộ bitset, cũng không hỗ trợ trực tiếp `|=` như toán tử trên số nguyên. Cần dùng `BigInteger` bất biến như ví dụ hoặc tự triển khai thao tác dịch/OR, đồng thời bảo đảm mỗi món chỉ được sử dụng một lần.

**Bài 6.** Có `V=100_000` đỉnh nhưng chỉ vài trăm cạnh. Có nên tạo `V` bitset, mỗi bitset có khả năng chứa `V` bit để biểu diễn toàn ma trận kề?

**Gợi ý:** cân nhắc danh sách kề vì đồ thị rất thưa. Nếu bật nhiều bit cao rải rác, dung lượng bitset sẽ tăng đáng kể; riêng ma trận đầy đủ cần cỡ `V²` bit (khoảng 1,25 GB chưa tính overhead), thường không đáng với vài trăm cạnh.

## 12. Quy trình chọn cấu trúc và kiểm chứng

Khi thấy bài toán liên quan đến tập phần tử hoặc trạng thái boolean, hỏi tuần tự:

1. **Vũ trụ là gì?** Mỗi phần tử có thể ánh xạ ổn định đến chỉ số không âm không?
2. **Vũ trụ có nhỏ hoặc đủ đặc không?** Tối đa 64 phần tử có thể dùng `long`; lớn hơn dùng `BitSet`, hoặc cấu trúc thưa nếu cần.
3. **Phép toán chính là gì?** Nếu nhiều lần hợp/giao/hiệu/đếm thành viên, bitset thường đáng xem xét. Nếu chỉ có vài thành viên rải rác, `HashSet` hay danh sách có thể phù hợp.
4. **Có tính chất tập hợp thật không?** Cần tần suất, thứ tự hoặc giá trị gắn theo mỗi phần tử thì một bitset đơn thuần chưa đủ.
5. **Có ranh giới chỉ số và vũ trụ rõ ràng không?** Kiểm tra `n=0`, `n=64`, vị trí bit 63, phần bù, chỉ số ngoài miền.
6. **Có dùng lại đối tượng không?** Với `BitSet`, các phép toán gộp thường sửa đối tượng nhận; cần clone nếu muốn giữ nguyên dữ liệu nguồn.
7. **Đếm chi phí theo miền đúng:** phân biệt số phần tử thực có `k`, độ rộng vũ trụ `U`, số từ máy `ceil(U/w)` và số trạng thái `2^n`.
8. **Chứng minh tính đúng:** xét phép toán theo từng bit; với DP bitset, chứng minh hai trường hợp chọn/không chọn bao phủ mọi nghiệm.
9. **Thử các ca biên:** tập rỗng, tập đầy, hai tập rời nhau, trùng hoàn toàn, phần tử 0, phần tử cao nhất, vũ trụ cực lớn nhưng thưa.

**Ghi nhớ:** Bitset là **cách biểu diễn và thao tác tập hữu hạn bằng các bit**, giúp tận dụng phép toán theo từ máy. Nó mạnh khi số chỉ số có giới hạn rõ ràng và cần xử lý nhiều quan hệ thành viên cùng lúc; chọn đúng cấu trúc còn phụ thuộc vào độ lớn, độ thưa, yêu cầu lưu thông tin và tính đúng của thuật toán bao quanh.
