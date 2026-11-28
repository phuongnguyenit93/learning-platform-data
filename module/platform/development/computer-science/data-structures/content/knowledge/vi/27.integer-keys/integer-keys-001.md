# Miền khóa hữu hạn và kích thước từ máy

Khi học các cấu trúc dữ liệu như mảng, bảng băm, cây cân bằng hoặc cây nhiều nhánh, ta thường mô tả khóa bằng một giá trị trừu tượng `key` có thể so sánh. Nhưng nếu khóa là **số nguyên nằm trong một miền đã biết**, ta có thêm thông tin rất quan trọng: mọi khóa hợp lệ đều có thể được biểu diễn bằng một số hữu hạn bit, và đôi khi có thể **đi thẳng tới vị trí của khóa** mà không cần so sánh nhiều lần hay tính hàm băm.

Ví dụ, một hệ thống chỉ quản lý số thứ tự từ 0 tới 999 có thể dùng mảng `present[1000]`; kiểm tra khóa `307` chỉ cần xem `present[307]`. Ngược lại, nếu quản lý 10.000 mã định danh nằm rải rác trong miền 0 tới một tỷ, cấp phát một tỷ ô là một lựa chọn tốn kém. Cả hai bài toán đều dùng **khóa số nguyên**, nhưng sự khác nhau giữa **số khóa thực có** và **kích thước miền khóa** dẫn tới cấu trúc phù hợp khác nhau.

Bài học này giới thiệu hai tham số nền tảng của các cấu trúc dữ liệu cho khóa nguyên:

- **Miền khóa hữu hạn** (*finite key universe*): có bao nhiêu giá trị khóa khác nhau có thể xuất hiện?
- **Kích thước từ máy** (*machine word size*): một phép toán máy xử lý trực tiếp bao nhiêu bit, và những giả định nào cho phép coi truy cập một khóa là O(1)?

Ta sẽ xác định các ký hiệu `U`, `n`, `w`, ánh xạ miền có số âm sang chỉ số mảng, phân biệt khóa có dấu/không dấu, tìm hiểu bảng địa chỉ trực tiếp và bitset, tính chi phí bộ nhớ, rồi viết chương trình Java minh họa tập số nguyên trong một miền có giới hạn. Đây là kiến thức nền để hiểu tại sao **bảng băm, cây cân bằng, trie bit, cấu trúc tìm kiếm tiền nhiệm và các kỹ thuật dùng bit** có những đánh đổi khác nhau.

## 1. Miền khóa hữu hạn là gì?

**Miền khóa** (*key universe*) là tập tất cả các giá trị mà chương trình cho phép sử dụng làm khóa. Ta thường chuẩn hóa một miền liên tục thành:

\[
\mathcal{U}=\{0,1,2,\ldots,U-1\}.
\]

Ở đây **`U` là số lượng giá trị khóa có thể có**, không phải khóa lớn nhất. Nếu khóa chạy từ 0 tới 999, miền có:

\[
U=1000,
\]

không phải 999. Nếu khóa nằm trong đoạn nguyên đóng `[a,b]`, với `a\le b`, số giá trị là:

\[
\boxed{U=b-a+1.}
\]

Trong phép tính thực tế, phải dùng kiểu số đủ rộng để tính hiệu `b-a+1`, tránh tràn nếu `a` âm rất lớn và `b` dương rất lớn.

### Ba đại lượng không được đánh đồng

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `U` | Số **giá trị khóa có thể xuất hiện** | Mã từ 0 tới 999.999 có `U=1\,000\,000` |
| `n` | Số **khóa phân biệt đang lưu** | Trong hệ thống hiện có 800 mã, `n=800` |
| `w` | Số **bit trong một từ máy** theo mô hình đang dùng | Mô hình RAM với từ 64 bit có `w=64` |

Với một tập khóa phân biệt trong miền hữu hạn:

\[
0\le n\le U.
\]

**Mật độ khóa** có thể đo bằng:

\[
\rho=\frac{n}{U}.
\]

Trong ví dụ `n=800`, `U=1\,000\,000`, chỉ có `0.08\%` miền đang được sử dụng. Đây là một tập **thưa** (*sparse*), dù mỗi khóa đều là số nguyên nhỏ hơn một triệu.

### Miền có thể không liên tục

Tập giá trị hợp lệ đôi khi không phải `[a,b]` liên tục, ví dụ chỉ những mã `\{100,200,500\}`. Khi đó:

- Có thể dùng **ánh xạ mật độ** từ mỗi mã hợp lệ sang một chỉ số `0..U-1` nếu biết trước toàn bộ mã.
- Có thể dùng bảng băm hoặc cây, nếu giá trị hợp lệ thay đổi động.
- Không nên mặc định lấy `U=max-min+1` làm số **mã hợp lệ** khi giữa các mã có nhiều khoảng trống không bao giờ dùng.

Trong bài, để minh họa mảng địa chỉ trực tiếp, ta thường giả định miền nguyên **liên tục**; `U` là số vị trí cần biểu diễn theo cách ánh xạ đã chọn.

## 2. Kích thước từ máy `w` và mô hình Word-RAM

Một **từ máy** (*machine word*) là đơn vị bit cơ bản mà mô hình tính toán giả định bộ xử lý có thể thao tác hiệu quả. Trong phân tích cấu trúc dữ liệu khóa số nguyên, mô hình **Word-RAM** thường giả định:

1. Một từ có `w` bit.
2. Các phép toán cơ bản trên một từ — so sánh, cộng/trừ trong giới hạn, các phép AND/OR/XOR và dịch bit hợp lệ — được tính **O(1)** theo mô hình.
3. Khóa hoặc chỉ số cần xử lý trực tiếp có thể biểu diễn trong một hoặc một số lượng hằng số từ.
4. Địa chỉ bộ nhớ mà thuật toán truy cập phải biểu diễn được; đối với mảng kích thước `U` thường cần `w` đủ lớn theo quy mô bài toán.

Với một miền gồm `U` giá trị phân biệt, số bit tối thiểu để **mã hóa một chỉ số** trong `0..U-1` là:

\[
\boxed{b=\lceil\log_2 U\rceil}
\]

khi `U\ge2`. Trường hợp `U=1`, về mặt lý thuyết không cần bit nào để phân biệt các khóa vì chỉ có một khả năng; nhưng kiểu dữ liệu và ô lưu trữ thực tế vẫn có chi phí.

Muốn mọi chỉ số của miền nằm trong **một từ `w` bit không dấu**:

\[
U\le 2^w
\quad\Leftrightarrow\quad
w\ge\lceil\log_2 U\rceil.
\]

Đây là quan hệ về **khả năng biểu diễn**. Nó **không nói rằng máy có đủ RAM** để tạo một bảng kích thước `U`.

### Ví dụ số bit cần thiết

| Miền liên tục | `U` | `b=\lceil\log_2 U\rceil` |
| --- | ---: | ---: |
| `\{0,1\}` | 2 | 1 bit |
| `0..15` | 16 | 4 bit |
| `0..100` | 101 | 7 bit |
| `0..999` | 1.000 | 10 bit |
| `0..65\,535` | 65.536 | 16 bit |
| `0..2^{32}-1` | `2^{32}` | 32 bit |

Nếu khóa chỉ nhận một trong 101 giá trị 0–100, 7 bit là đủ để phân biệt chúng vì `2^6=64<101\le128=2^7`. Tuy nhiên, trong chương trình Java, ta có thể chọn `byte`, `short` hoặc `int` tùy tính thuận tiện và phạm vi có dấu. **Số bit thông tin tối thiểu không nhất thiết là kích thước đối tượng/kiểu thực tế.**

### Kích thước từ máy khác kích thước địa chỉ và kiểu khóa

Một máy thường được gọi là “64 bit” không có nghĩa:

- Mọi khóa đều dài đúng 64 bit.
- Mọi con trỏ đều nhất thiết chiếm đúng 8 byte trong tất cả môi trường.
- Mỗi phép toán trên số nguyên dài tùy ý đều O(1).
- Có thể cấp phát mảng `2^{64}` phần tử.

Ví dụ, Java có `int` **32 bit có dấu** và `long` **64 bit có dấu**, bất kể phần lớn chương trình hiện đại chạy trên bộ xử lý 64 bit. Các kiểu số lớn như `BigInteger` cần nhiều từ khi độ dài bit tăng, nên chi phí so sánh/cộng/trừ không còn mặc định O(1) theo số bit.

Trong chứng minh thuật toán, cần nêu rõ `w` là **tham số của mô hình**, hay là một hằng số máy (thường 32/64 bit) trong chương trình cụ thể.

## 3. Số nguyên có dấu và không dấu: cùng số bit, khác khoảng giá trị

Với `w` bit, có đúng `2^w` **mẫu bit** phân biệt. Nhưng cách diễn giải mẫu bit quyết định miền giá trị số học.

**Số nguyên không dấu `w` bit**:

\[
0\le x\le2^w-1.
\]

**Số nguyên có dấu dạng bù hai (*two's complement*) `w` bit**:

\[
-2^{w-1}\le x\le2^{w-1}-1.
\]

Hai kiểu đều có **`2^w` giá trị**, nhưng khoảng số khác nhau.

Ví dụ với 8 bit:

| Mẫu bit | Giải thích không dấu | Giải thích bù hai có dấu |
| --- | ---: | ---: |
| `0000\,0000` | 0 | 0 |
| `0111\,1111` | 127 | 127 |
| `1000\,0000` | 128 | -128 |
| `1111\,1111` | 255 | -1 |

Một lỗi thực tế là **so sánh hai giá trị theo quy tắc có dấu trong khi khóa được định nghĩa là không dấu**. Khi đó, mẫu bit có bit cao nhất bằng 1 bị xem là số âm và thứ tự khóa sai.

### Trong Java

- `int` có giá trị từ `-2^{31}` tới `2^{31}-1`.
- `long` có giá trị từ `-2^{63}` tới `2^{63}-1`.
- Có thể diễn giải mẫu bit `int` theo thứ tự không dấu bằng `Integer.compareUnsigned(a,b)`.
- Có thể chuyển mẫu bit `int` thành giá trị không dấu dưới dạng `long` bằng `Integer.toUnsignedLong(x)`.
- Nếu cần biểu diễn chính xác `2^{64}` hoặc `2^{64}-1` như **số dương**, phải dùng kiểu lớn hơn `long` có dấu, chẳng hạn `BigInteger`.

**Không viết** `1 << 32` để biểu diễn `2^{32}` trong Java: `1` là `int` và số bit dịch được lấy theo 5 bit thấp, nên `1 << 32` tương đương `1 << 0`. Dùng `1L << 32` cho giá trị `2^{32}`; riêng `2^{64}` không biểu diễn được bằng `long` có dấu.

```java
import java.math.BigInteger;

public class IntegerWordExamples {
    public static void main(String[] args) {
        long twoTo32 = 1L << 32;
        BigInteger twoTo64 = BigInteger.ONE.shiftLeft(64);

        System.out.println(twoTo32); // 4294967296
        System.out.println(twoTo64); // 18446744073709551616
        System.out.println(Integer.toUnsignedLong(-1)); // 4294967295
        System.out.println(Integer.compareUnsigned(-1, 1) > 0); // true
    }
}
```

### Tràn số không phải mở rộng miền khóa

Nếu tính `x+1` ở `Integer.MAX_VALUE`, kết quả kiểu `int` bị tràn về miền âm. Điều này **không có nghĩa miền khóa được mở rộng tuần hoàn** nếu đề bài nói về thứ tự số nguyên thông thường.

Tương tự, không nên dùng giá trị `-1` làm mã “không tìm thấy” khi `-1` là một khóa hợp lệ. Có thể trả về `null` với kiểu đóng hộp, `OptionalInt`, hoặc cặp `(found,value)`.

## 4. Chuẩn hóa đoạn có số âm thành chỉ số không âm

Bảng địa chỉ trực tiếp và bitset thường yêu cầu chỉ số từ 0 trở lên. Điều đó **không có nghĩa chỉ lưu được khóa không âm**.

Nếu miền hợp lệ là đoạn đóng `[a,b]`, ánh xạ:

\[
\boxed{\operatorname{index}(x)=x-a}
\quad\text{với }a\le x\le b.
\]

Ánh xạ ngược:

\[
\boxed{x=a+\operatorname{index}(x)}.
\]

Ví dụ, với khóa từ `-3` tới `10`:

\[
U=10-(-3)+1=14.
\]

| Khóa `x` | Chỉ số `x-(-3)` |
| ---: | ---: |
| -3 | 0 |
| -2 | 1 |
| 0 | 3 |
| 4 | 7 |
| 10 | 13 |

```text
Miền khóa: -3 -2 -1  0  1  2  3  4  5  6  7  8  9 10
Chỉ số:     0  1  2  3  4  5  6  7  8  9 10 11 12 13
```

**Điều kiện tiền đề:** phải kiểm tra `a\le x\le b` **trước khi truy cập mảng**, nếu không có thể truy cập ngoài biên.

### Cẩn thận với tràn khi lấy hiệu

Trong Java, đoạn `[Integer.MIN_VALUE,Integer.MAX_VALUE]` có:

\[
U=2^{32}=4\,294\,967\,296.
\]

Giá trị này **không vừa trong `int` có dấu**. Phép tính sau là sai nếu kết quả cần giữ trong `int`:

```java
int a = Integer.MIN_VALUE;
int b = Integer.MAX_VALUE;
int wrongUniverse = b - a + 1; // Tràn số!
```

Phải mở rộng kiểu **trước khi trừ**:

```java
long universe = (long) b - (long) a + 1L;
long offset = (long) x - (long) a;
```

Một `offset` có thể biểu diễn bằng `long` nhưng **không có nghĩa có thể ép về `int` để làm chỉ số `boolean[]`**. Java array/`BitSet` trong ví dụ bên dưới dùng chỉ số `int`, nên cần kiểm tra giới hạn triển khai. Đối với miền quá lớn, phải dùng cấu trúc chia trang, ánh xạ thưa hoặc một cấu trúc khác.

### Đổi thứ tự có dấu thành thứ tự không dấu bằng XOR

Với số `int` 32 bit, biểu thức:

```java
int orderedBits = x ^ Integer.MIN_VALUE;
```

đảo bit dấu. Nếu so sánh **`orderedBits` dưới dạng không dấu**, thứ tự của các giá trị `x` có dấu sẽ được bảo toàn:

```text
x (signed):      -2            -1             0             1
x ^ MIN:      0x7ffffffe    0x7fffffff    0x80000000    0x80000001
                 (so sánh các bit mới theo unsigned)
```

Điều này hữu ích khi dùng trie bit hoặc các thuật toán thứ tự trên biểu diễn nhị phân. **Không dùng trực tiếp so sánh có dấu** của `orderedBits`, vì nó sẽ đổi ý nghĩa của cách sắp xếp.

## 5. Địa chỉ trực tiếp: biến giá trị khóa thành địa chỉ

Với miền `\{0,\dots,U-1\}` nhỏ, ta có thể lưu một bảng:

```text
index:       0   1   2   3   4   5   6   7
present:     F   T   F   T   F   T   F   F
                 ^       ^       ^
                 1       3       5
```

Tìm `3` chỉ cần đọc `present[3]`. Không cần duyệt một cây hoặc tính hàm băm.

Mã giả:

```text
contains(x):
    require 0 <= x < U
    return present[x]

insert(x):
    require 0 <= x < U
    present[x] = true

delete(x):
    require 0 <= x < U
    present[x] = false
```

Trong mô hình RAM với **mảng đã cấp phát** và chỉ số truy cập được biểu diễn trong từ máy, những thao tác này có thể tính là **O(1) trong trường hợp xấu nhất**.

### Tập hợp và ánh xạ khóa → giá trị là hai bài toán khác nhau

Nếu chỉ hỏi **khóa có thuộc tập không**, `present[x]` có thể là một cờ boolean hoặc một bit.

Nếu muốn lưu `key → value`, có thể dùng:

```text
values[x] = giá trị gắn với x
occupied[x] = true/false
```

Cần lưu **trạng thái có khóa** riêng nếu `null` hoặc `0` có thể là một giá trị hợp lệ. Một mảng chỉ lưu `values[x]` với giá trị mặc định 0 sẽ không phân biệt được **“chưa có mục”** với **“mục có giá trị 0”** nếu không đặt quy ước hoặc metadata bổ sung.

### Chi phí khởi tạo và dung lượng

Bảng địa chỉ trực tiếp dùng một ô cho **mỗi giá trị có thể có**, không chỉ mỗi khóa đang lưu:

\[
\text{Bộ nhớ}=\Theta(U)\text{ ô}.
\]

Việc cấp phát và khởi tạo toàn bảng thường liên quan tới `U`, ngay cả khi `n=0`. Một số hệ điều hành có thể cấp phát trang vật lý theo nhu cầu, nhưng **không được nhầm kỹ thuật cấp phát lười với bảo đảm mảng khổng lồ là miễn phí**.

Ưu điểm của direct addressing lớn nhất khi miền **nhỏ, cố định hoặc tương đối đậm đặc**.

## 6. Bitset: dùng một bit cho mỗi khóa có thể có

Nếu chỉ lưu **tập khóa** (có/không), một ô `boolean` hoặc tham chiếu đối tượng có thể lãng phí. **Bitset** (*bitmap, bit vector*) dùng **một bit cho mỗi giá trị trong miền**:

\[
\operatorname{bit}(x)=
\begin{cases}
1 & \text{nếu khóa }x\text{ hiện có},\\
0 & \text{nếu không}.
\end{cases}
\]

Ví dụ miền `U=16`, tập khóa hiện có:

\[
S=\{0,3,5,9\}.
\]

Bit tại các vị trí 0, 3, 5, 9 được bật:

```text
Bit index:    15 14 13 12 11 10  9  8  7  6  5  4  3  2  1  0
Giá trị:       0  0  0  0  0  0  1  0  0  0  1  0  1  0  0  1

Viết từ bit cao xuống thấp:
    0000 0010 0010 1001  (hex 0x0229)
```

Tập chỉ có bốn khóa, nhưng bitset vẫn mô hình hóa **16 khả năng**.

### Bitwise trên một từ

Nếu toàn bộ miền có `U\le64` và dùng mẫu bit của `long`, khóa `x` tương ứng mask:

```java
long mask = 1L << x;  // Chỉ hợp lệ khi 0 <= x < 64.
```

Các thao tác cơ bản:

```java
long bits = 0L;
bits |= 1L << 3;               // Thêm khóa 3.
bits |= 1L << 5;               // Thêm khóa 5.
boolean has3 = (bits & (1L << 3)) != 0; // true.
bits &= ~(1L << 3);            // Xóa khóa 3.
int count = Long.bitCount(bits); // Số bit đang bật.
```

Không quên **kiểm tra giới hạn khóa**: trong Java, `1L << 64` không dịch đúng 64 vị trí, vì số bit dịch của `long` được lấy theo 6 bit thấp; kết quả tương đương `1L << 0`.

### Khi miền lớn hơn một từ

Bitset có thể được chia thành các từ `long` 64 bit:

\[
\operatorname{wordIndex}(x)=\left\lfloor \frac{x}{64}\right\rfloor,
\qquad
\operatorname{bitIndex}(x)=x\bmod64.
\]

```text
U = 130:

words[0]: các khóa 0..63
words[1]: các khóa 64..127
words[2]: các khóa 128..129 (62 bit còn lại không dùng)
```

Mã giả hoặc Java với `x\ge0` và được kiểm tra `x<U`:

```java
int wi = x >>> 6;       // x / 64 khi x >= 0.
int bi = x & 63;        // x % 64 khi x >= 0.
long mask = 1L << bi;

words[wi] |= mask;                // insert(x)
boolean found = (words[wi] & mask) != 0; // contains(x)
words[wi] &= ~mask;               // delete(x)
```

Nếu số lượng từ cần cấp phát được tính từ `U`, dùng toán học đủ rộng:

\[
N_{\text{words}}=\left\lceil\frac{U}{64}\right\rceil.
\]

Với `U` lớn, không nên tính `(U+63)/64` trong kiểu có nguy cơ tràn. Một cách an toàn cho `U\ge0` là `U/64 + (U%64 == 0 ? 0 : 1)` với kiểu đủ rộng.

### Cái gì thực sự O(1)?

Khi từ chứa bit mục tiêu đã có trong RAM:

- Kiểm tra `contains(x)`: truy cập một từ và AND mask → O(1) trong Word-RAM.
- `insert(x)` và `delete(x)`: sửa một từ → O(1).
- `Long.bitCount(word)`: O(1) theo mô hình từ cố định.

Nhưng **tìm khóa tiếp theo** (*successor*) hoặc **duyệt toàn bộ tập** không tự nhiên trở thành O(1) chỉ vì một bit truy cập nhanh. Thuật toán có thể phải **quét qua nhiều từ không có bit nào bật**.

Nếu dùng `java.util.BitSet.nextSetBit(i)` để tìm bit bật tiếp theo, nó bỏ qua các vùng bit theo **đơn vị từ máy**, nhưng trong trường hợp xấu vẫn có thể phải kiểm tra nhiều từ. Với một miền có `U` bit, tìm từ khóa đầu đến bit bật xa nhất có thể tốn **O(⌈U/w⌉)** bước kiểm tra từ, không phải O(1) cho mọi `U`.

## 7. Đếm, tìm phần tử kế tiếp và giới hạn của bitset

Bitset hữu ích vì một từ giữ nhiều cờ. Tuy nhiên, cần phân biệt ba thao tác:

### 7.1. Membership

`contains(x)` chỉ đọc **một bit** sau khi tính được chỉ số, nên O(1) trong mô hình RAM với mảng chứa bit đã sẵn sàng.

### 7.2. Cardinality

`cardinality()` đếm tổng số bit bật. Nếu chưa lưu sẵn biến đếm, phải đi qua các từ hiện diện trong bitset và cộng `popcount`:

\[
\operatorname{cardinality}(S)
=\sum_i \operatorname{popcount}(words[i]).
\]

Chi phí điển hình là O(`U/w`) khi bitset dùng mảng từ cho toàn miền. Có thể duy trì biến `size` và cập nhật nó khi bật/tắt một bit **thực sự đổi trạng thái**, từ đó đọc `size` trong O(1).

### 7.3. Successor

Cho `successor(x)` là khóa **nhỏ nhất không nhỏ hơn `x`** đang có trong tập (còn gọi là `ceiling(x)`):

1. Xét các bit từ vị trí `x` trong từ hiện tại.
2. Nếu còn bit bật trong phần từ đó, lấy bit bật thấp nhất.
3. Nếu không, sang từ tiếp theo cho đến khi gặp từ khác 0.
4. Nếu hết miền, trả về “không tìm thấy”.

Trong một từ khác 0, `Long.numberOfTrailingZeros(mask)` có thể xác định vị trí bit bật thấp nhất. **Phải kiểm tra mask khác 0** trước khi dùng kết quả: trong Java, `Long.numberOfTrailingZeros(0L)` trả về 64, không phải một vị trí bit hợp lệ của từ.

```text
Miền 0..127, các khóa {2, 5, 70, 120}:

word[0] có bit 2, 5.
word[1] có bit (70-64)=6 và bit (120-64)=56.

ceiling(6):
  phần còn lại của word[0] không có bit bật;
  sang word[1], thấy bit 6 -> trả 70.

ceiling(121):
  các bit từ 121 trở đi không có bit bật -> không tìm thấy.
```

Nếu khoảng trống lớn và số từ nhiều, phép tìm kế tiếp tốn thời gian tỷ lệ với **số từ bị quét**, dù `contains(x)` vẫn O(1).

### 7.4. Range scan và thứ tự

Với khóa trong đoạn `[a,b]`, có thể dùng `nextSetBit` để lặp từng khóa hợp lệ. Nếu đoạn dài `\ell=b-a+1`, chi phí trên bitmap chia từ thường được đánh giá theo số từ giao với khoảng và số kết quả `r`:

\[
O\left(\left\lceil\frac{\ell}{w}\right\rceil+r+1\right)
\]

trong mô hình bitset được quét **có giới hạn theo các từ giao với đoạn** và phần bit biên được xử lý đúng. Đây là **mô hình bậc chi phí**, không phải số lệnh chính xác của API Java trong mọi môi trường. Riêng `BitSet.nextSetBit(i)` không nhận cận trên: nếu không có bit bật gần đó, lời gọi cuối cùng có thể tiếp tục quét **qua cả cận `b`** tới một bit ở xa hơn hoặc tới hết vùng từ đã cấp phát. Muốn bảo đảm chặt số từ chỉ thuộc đoạn truy vấn, phải cài đặt phép quét **có cận trên ở mức từ**.

Đối với tập cực kỳ thưa, một cây cân bằng có thể tìm khóa đầu bằng O(log n), rồi duyệt `r` khóa tiếp theo trong O(r) bằng iterator, **không phải quét qua hàng triệu bit 0**.

### Rank và select cần cấu trúc phụ trợ

Hai truy vấn khác với membership:

- `rank(x)`: có bao nhiêu khóa trong tập nhỏ hơn (hoặc không lớn hơn) `x`?
- `select(k)`: khóa thứ `k` trong thứ tự tăng là gì?

Một bitset thô có thể tính bằng đếm hoặc quét nhưng **không tự bảo đảm O(1)** cho các truy vấn này. Có thể thêm bảng tiền tố, cấu trúc rank/select chuyên biệt hoặc dùng cây có thông tin kích thước cây con. Không nên suy O(1) cho mọi phép toán chỉ từ `contains(x)=O(1)`.

## 8. Chi phí bộ nhớ: `U` lớn nhưng `n` nhỏ

Với miền liên tục `U` giá trị:

- Bảng địa chỉ trực tiếp dùng **O(U) ô**.
- Bitset lý tưởng cần **`U` bit**, tức xấp xỉ `U/8` byte, làm tròn theo số từ và thêm metadata.
- Nếu chỉ lưu `n` khóa như các số nguyên trong một mảng, phần lưu khóa thuần có **O(n)** ô, nhưng tìm kiếm/chèn/xóa phụ thuộc cách tổ chức.

Ví dụ:

| Miền khóa | `U` | Bitset lý tưởng (chỉ dữ liệu bit) | Bảng 8 byte/ô |
| --- | ---: | ---: | ---: |
| `0..100` | 101 | 13 byte sau làm tròn theo byte | 808 byte |
| `0..999\,999` | 1.000.000 | 125.000 byte ≈ 122,1 KiB | 8.000.000 byte ≈ 7,63 MiB |
| `0..999\,999\,999` | 1.000.000.000 | 125.000.000 byte ≈ 119,2 MiB | 8.000.000.000 byte ≈ 7,45 GiB |
| Toàn bộ mẫu bit 32 bit | `2^{32}` | 536.870.912 byte = 512 MiB | 34.359.738.368 byte = 32 GiB |

**Lưu ý:** con số trong bảng là kích thước **payload lý tưởng** theo giả định 8 byte/ô, không phải dự báo chính xác dung lượng một `Object[]` Java. Mảng thực tế có header, căn chỉnh, kiểu tham chiếu phụ thuộc JVM, giới hạn kích thước mảng và overhead quản lý khác.

Tương tự, `java.util.BitSet` dùng các từ `long` và có metadata; cấp phát động theo bit cao nhất được sử dụng, nên dung lượng thực có thể khác một chút so với `U/8`.

### Ví dụ về độ thưa

Giả sử chỉ có `n=500` khóa trong miền `U=1\,000\,000\,000`:

\[
\rho=\frac{500}{1\,000\,000\,000}=0.0000005.
\]

Bitset lý tưởng chiếm khoảng **119,2 MiB** để ghi nhận chỉ **500 khóa**. Một danh sách chứa 500 khóa kiểu `int` chỉ dùng `500\times4=2\,000` byte cho phần số nguyên thuần, dù danh sách đó không tự hỗ trợ mọi thao tác nhanh.

Trong tình huống này, **bảng băm hoặc cây cân bằng** thường đáng cân nhắc hơn một bitmap dày đặc của toàn miền. Ngược lại, nếu `U` chỉ có 101 giá trị và phần lớn giá trị có mặt, bitset rất gọn.

### Khi `U` vừa một từ nhưng n nhỏ

Nếu `U\le w`, toàn bộ tập có thể nằm trong **một từ**. Ví dụ tập mã trạng thái 0–31 dùng một số `int` làm bitmap:

```text
32 trạng thái có/không -> 32 bit = 4 byte payload.
```

Đó là tình huống đặc biệt hữu ích: `contains`, thêm/xóa và nhiều thao tác hợp/giao tập có thể được thực hiện bằng **một số ít phép bitwise**.

## 9. So sánh với bảng băm và cây tìm kiếm cân bằng

Khi phải chọn cấu trúc dữ liệu, cần hỏi rõ **các thao tác cần hỗ trợ** và **mối quan hệ giữa `n` với `U`**.

| Cấu trúc | Bộ nhớ theo mô hình cơ bản | Tìm chính xác | Thứ tự/successor | Phù hợp khi |
| --- | --- | --- | --- | --- |
| Bảng địa chỉ trực tiếp | O(U) **ô** | O(1) worst-case sau cấp phát | Tìm khóa kế tiếp bằng quét thường O(U) worst-case | Miền nhỏ, cần ánh xạ nhanh |
| Bitset dày đặc | O(U) **bit** | O(1) worst-case theo một từ | Quét theo từ; successor worst-case O(⌈U/w⌉) | Miền vừa, chủ yếu lưu membership và phép tập hợp |
| Bảng băm thông dụng | O(n) kỳ vọng/dung lượng theo số mục | O(1) **trung bình/kỳ vọng** với giả định phù hợp | Không duy trì thứ tự | Miền lớn, tập thưa, tìm chính xác |
| AVL/Red-Black tree | O(n) nút | O(log n) worst-case | O(log n) tìm vị trí, duyệt kế O(1) khấu hao mỗi mục | Cần thứ tự, predecessor/range, tập thưa |
| Mảng đã sắp | O(n) | O(log n) | Tìm vị trí O(log n), quét tuyến tính liên tiếp | Dữ liệu chủ yếu đọc, ít cập nhật |
| Trie nhị phân theo bit | Phụ thuộc cách lưu nút, thường theo `n` và `w` | O(w) theo đường bit | Có thể hỗ trợ bài toán thứ tự với logic riêng | Khóa có độ dài bit cố định và cần khai thác tiền tố |

**“Trung bình O(1)” của bảng băm** không phải cam kết worst-case O(1) cho mọi dãy khóa hay mọi hàm băm. **“O(log n)” của cây cân bằng** là bảo đảm khi thực sự duy trì được bất biến cân bằng; cây BST không tự cân bằng có thể bị lệch thành O(n).

### Không coi O(1) là miễn phí

Truy cập `present[x]` O(1) nhưng nếu phải:

- Cấp phát hàng gigabyte RAM.
- Tạo một bảng khổng lồ khi khởi động.
- Đọc trang bộ nhớ không có trong cache.
- Dọn và ghi lại dữ liệu toàn miền.

thì chi phí thực tế có thể lớn hơn cấu trúc O(log n) nhưng gọn. Phân tích Big-O phải gắn với **mô hình bộ nhớ và thao tác được tính**, chứ không thay thế việc đánh giá tài nguyên.

### Cây cân bằng với bitmap hỗ trợ hai kiểu truy vấn

Một thiết kế có thể kết hợp:

- Bitset để kiểm tra **thuộc tập** nhanh trong miền tương đối nhỏ.
- Cây cân bằng để hỗ trợ **thứ tự**, predecessor và successor khi tập thưa.

Tuy nhiên, duy trì hai cấu trúc đồng thời làm tăng chi phí cập nhật và yêu cầu bảo đảm chúng luôn nhất quán. Chỉ nên làm khi workload thực sự cần cả hai tính năng với mức hiệu năng phù hợp.

## 10. Khóa số nguyên cho phép thuật toán chuyên biệt nào?

Biết khóa thuộc một miền hữu hạn cho phép nhiều kỹ thuật không áp dụng trực tiếp cho khóa so sánh tổng quát.

### 10.1. Counting sort

Nếu `n` khóa nằm trong miền `0..U-1` và `U` vừa phải, **counting sort** đếm số lần xuất hiện của từng giá trị:

```text
count[0..U-1] = 0
for each key x:
    count[x]++

for x = 0..U-1:
    xuất x đúng count[x] lần
```

Thời gian O(n+U), bộ nhớ phụ thường O(U) nếu chỉ đếm (hoặc thêm O(n) khi cần tạo mảng đầu ra ổn định). Khi `U` lớn hơn `n` quá nhiều, bước quét toàn bộ `U` có thể trở thành nút thắt.

### 10.2. Radix sort

**Radix sort** xử lý từng nhóm bit/chữ số của khóa. Nếu dùng cơ số `B=2^d`, mỗi lượt có thể dùng counting sort trên một chữ số gồm `d` bit:

\[
\text{số lượt}=\left\lceil\frac{w}{d}\right\rceil.
\]

Trong mô hình khóa `w` bit, thời gian điển hình của radix sort dựa trên counting sort là:

\[
O\left((n+B)\left\lceil\frac{w}{d}\right\rceil\right).
\]

Cần xét cách xử lý **bit dấu** để có thứ tự số nguyên có dấu đúng, và cân bằng giữa bộ đếm `B` với số lượt `w/d`. Không phải cứ chọn `B` cực lớn thì nhanh hơn.

### 10.3. Trie bit và phép tìm tiền nhiệm

**Trie nhị phân** chọn nhánh 0/1 theo các bit của khóa. Với khóa dài `w` bit, một đường từ gốc đến lá có thể gồm O(w) bước. Nếu `w=32` hoặc 64 là hằng số của môi trường, đó là số bước bị chặn; nhưng số nút, tính cục bộ bộ nhớ và việc cấp phát vẫn là vấn đề.

**Predecessor/successor** là bài toán tìm khóa lớn nhất nhỏ hơn `x` hoặc nhỏ nhất lớn hơn `x`. Các cấu trúc chuyên cho **miền nguyên hữu hạn**, như **van Emde Boas tree**, tận dụng cấu trúc bit của miền để đạt độ phức tạp lý thuyết O(log log U) cho các thao tác chính trong mô hình thích hợp, nhưng phiên bản cổ điển có **chi phí không gian O(U)** và tiền đề cài đặt đáng lưu ý.

Đó là lý do `U` và `w` là các tham số quan trọng bên cạnh `n`: chúng có thể xuất hiện trong những giới hạn độ phức tạp **không viết hoàn toàn theo `n`**.

### 10.4. Hợp và giao tập bằng bitwise

Nếu hai tập có cùng miền và cùng ánh xạ bit:

\[
S_A\cup S_B \leftrightarrow A\ \mathrm{OR}\ B,
\]

\[
S_A\cap S_B \leftrightarrow A\ \mathrm{AND}\ B,
\]

\[
S_A\setminus S_B \leftrightarrow A\ \mathrm{AND}\ \mathrm{NOT}\ B.
\]

Với bitmap gồm `U` bit, một phép hợp/giao toàn tập xử lý O(⌈U/w⌉) từ, thay vì xét từng khóa riêng lẻ. Nếu `U\le w`, các phép này có thể gói trong một phép toán từ.

**Cẩn thận với complement:** phép NOT lật cả những bit **ngoài miền** ở từ cuối. Phải che chúng đi bằng mask để không xuất hiện những khóa `x\ge U` không hợp lệ.

## 11. Bài toán mẫu: chọn cấu trúc cho các miền khác nhau

### Tình huống A: mã trạng thái 0–31

Một chương trình cần lưu tập các trạng thái đang bật, miền có `U=32` và thao tác chính là thêm/xóa/kiểm tra trạng thái.

**Lựa chọn:** một bitmap `int` 32 bit hoặc một `BitSet` nhỏ. Một từ là đủ để lưu toàn bộ trạng thái; hợp/giao giữa các tập là phép OR/AND.

**Không cần** xây cây cân bằng chỉ để hỏi một cờ trạng thái có bật hay không.

### Tình huống B: điểm kiểm tra 0–100

Một lớp học có thể có nhiều học sinh cùng đạt một điểm. Nếu chỉ cần biết **có học sinh nào đạt điểm `x` không**, có thể dùng `boolean[101]` hoặc `BitSet`. Nếu cần **đếm số học sinh ở mỗi điểm**, dùng `int[101]`.

Điểm cần phân biệt: cấu trúc tập membership `present[x]` không lưu được **số lần xuất hiện**. Một tập cho điểm 80 chỉ biết “80 có tồn tại”, trong khi bảng tần suất biết “có 17 học sinh đạt 80”.

### Tình huống C: 10.000 mã trong miền 0–1.000.000.000

Miền rất lớn, nhưng số khóa ít:

\[
n=10\,000,\quad U=1\,000\,000\,001.
\]

**Lựa chọn:** bảng băm nếu ưu tiên tìm chính xác; cây cân bằng nếu cần thứ tự, predecessor/successor hay truy vấn khoảng. Bitset toàn miền có thể tốn khoảng 119 MiB chỉ để lưu membership.

### Tình huống D: thao tác `range(a,b)` thường xuyên

Nếu miền tương đối dày và truy vấn hay lấy một đoạn lớn, bitset cho phép quét nhiều bit liên tiếp bằng các từ; nếu tập thưa với khoảng trống dài, cây cân bằng hoặc B+ tree với liên kết lá thường tránh phải quét những vùng bit rỗng.

**Lựa chọn cuối cùng** còn phụ thuộc liệu dữ liệu nằm trong RAM hay trang lưu trữ, kích thước khóa/giá trị, tần suất cập nhật và độ rộng trung bình của các khoảng.

## 12. Java hoàn chỉnh: tập số nguyên có miền giới hạn bằng `BitSet`

Chương trình sau cài đặt một tập khóa nguyên **không trùng** trong đoạn đóng `[minKey,maxKey]`, có thể gồm số âm. Nó:

- Tính `U=maxKey-minKey+1` bằng `long` để tránh tràn khi trừ.
- Giới hạn `U` cho phù hợp với `BitSet` trong ví dụ dùng chỉ số `int`.
- Ánh xạ khóa `x` sang bit có chỉ số `x-minKey`.
- Hỗ trợ `add`, `remove`, `contains` với hợp đồng rõ ràng.
- Hỗ trợ `ceiling(x)` (khóa nhỏ nhất `\ge x`) và `higher(x)` (khóa nhỏ nhất `>x`).
- Hỗ trợ quét khoảng với **cận đóng/mở** mà không cộng/trừ trong `int` ở biên cực trị.
- Giữ một biến `size` để không phải đếm lại toàn bộ bitmap sau mỗi lần hỏi số phần tử.

Chương trình dùng `java.util.BitSet` thay vì thao tác từng `long` để tập trung vào **miền khóa, ánh xạ chỉ số và chi phí truy vấn**. `BitSet` là cấu trúc có thể tăng dung lượng lưu bit theo chỉ số cao nhất được bật; nó **không phải cấu trúc thưa thực sự** cho một miền rất lớn.

```java
import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;

public class FiniteIntegerUniverseDemo {
    static final class BoundedIntegerSet {
        private final int minKey;
        private final int maxKey;
        private final int universe;
        private final BitSet bits;
        private int size;

        BoundedIntegerSet(int minKey, int maxKey) {
            if (maxKey < minKey) {
                throw new IllegalArgumentException("Invalid range");
            }
            long u = (long) maxKey - (long) minKey + 1L;
            // BitSet dùng chỉ số int; ví dụ này không nhận miền
            // rộng tới mức U không vừa trong int có dấu.
            if (u > Integer.MAX_VALUE) {
                throw new IllegalArgumentException(
                    "Universe exceeds this demo's index limit");
            }
            this.minKey = minKey;
            this.maxKey = maxKey;
            this.universe = (int) u;
            this.bits = new BitSet(universe);
        }

        int universeSize() {
            return universe;
        }

        int size() {
            return size;
        }

        // Khóa nằm NGOÀI miền là đầu vào sai của API membership.
        private int indexOf(int key) {
            if (key < minKey || key > maxKey) {
                throw new IllegalArgumentException(
                    "Key outside bounded universe: " + key);
            }
            // Ép sang long TRƯỚC khi trừ để tránh tràn số.
            return (int) ((long) key - (long) minKey);
        }

        boolean contains(int key) {
            return bits.get(indexOf(key));
        }

        boolean add(int key) {
            int index = indexOf(key);
            if (bits.get(index)) {
                return false;
            }
            bits.set(index);
            size++;
            return true;
        }

        boolean remove(int key) {
            int index = indexOf(key);
            if (!bits.get(index)) {
                return false;
            }
            bits.clear(index);
            size--;
            return true;
        }

        // Khóa nhỏ nhất >= x, hoặc null nếu không có.
        // Với truy vấn thứ tự, x có thể ngoài miền; ta kẹp cận.
        Integer ceiling(int x) {
            if (x > maxKey) {
                return null;
            }
            int start = x <= minKey
                ? 0
                : (int) ((long) x - (long) minKey);
            int index = bits.nextSetBit(start);
            if (index < 0 || index >= universe) {
                return null;
            }
            long answer = (long) minKey + index;
            return (int) answer;
        }

        // Khóa nhỏ nhất > x, hoặc null nếu không có.
        Integer higher(int x) {
            if (x >= maxKey) {
                return null;
            }
            // Ở đây x < maxKey <= Integer.MAX_VALUE,
            // do đó x + 1 không thể tràn int.
            return ceiling(x < minKey ? minKey : x + 1);
        }

        // Đoạn [a,b], [a,b), (a,b], (a,b) tùy hai cờ.
        List<Integer> range(int a, boolean includeA,
                            int b, boolean includeB) {
            List<Integer> result = new ArrayList<>();
            // Tính biên bằng long để xử lý MIN/MAX và biên mở.
            long lower = Math.max(
                (long) minKey, (long) a + (includeA ? 0L : 1L));
            long upper = Math.min(
                (long) maxKey, (long) b - (includeB ? 0L : 1L));
            if (lower > upper) {
                return result;
            }

            int start = (int) (lower - (long) minKey);
            for (int index = bits.nextSetBit(start);
                    index >= 0;
                    index = bits.nextSetBit(index + 1)) {
                long value = (long) minKey + index;
                if (value > upper) {
                    break;
                }
                result.add((int) value);
            }
            return result;
        }
    }

    public static void main(String[] args) {
        BoundedIntegerSet set = new BoundedIntegerSet(-3, 10);

        for (int x : new int[] {-3, 0, 1, 4, 10}) {
            set.add(x);
        }
        System.out.println("U=" + set.universeSize()
            + ", size=" + set.size());
        System.out.println("contains(-3)=" + set.contains(-3)
            + ", contains(2)=" + set.contains(2));
        System.out.println("ceiling(2)=" + set.ceiling(2));
        System.out.println("higher(4)=" + set.higher(4));
        System.out.println("range[-1,10)="
            + set.range(-1, true, 10, false));
        System.out.println("add(4)=" + set.add(4));
        System.out.println("remove(0)=" + set.remove(0));
        System.out.println("all=" + set.range(-3, true, 10, true));
        System.out.println("final size=" + set.size());
    }
}
```

Đầu ra dự kiến:

```text
U=14, size=5
contains(-3)=true, contains(2)=false
ceiling(2)=4
higher(4)=10
range[-1,10)=[0, 1, 4]
add(4)=false
remove(0)=true
all=[-3, 1, 4, 10]
final size=4
```

### Giải thích những quyết định trong mã

**Tại sao `contains(2)` trả `false` nhưng `contains(11)` ném lỗi?**

Khóa 2 thuộc miền `[-3,10]` nhưng chưa được thêm; khóa 11 **không thuộc miền hợp lệ** của cấu trúc. Đây là một hợp đồng API rõ ràng. Một thư viện khác có thể chọn trả `false` cho cả khóa ngoài miền, nhưng phải nhất quán.

**Tại sao `ceiling` và `range` chấp nhận cận ngoài miền?**

Cận truy vấn không nhất thiết là một khóa hợp lệ của tập. Ví dụ hỏi “khóa nhỏ nhất lớn hơn 100” trên miền 0..10 phải trả không tìm thấy, không cần coi đó là một thao tác chèn ngoài miền.

**Tại sao `ceiling` trả `Integer`, không trả `int` với sentinel `-1`?**

Vì miền có thể bao gồm khóa `-1`. Giá trị `null` biểu thị không tìm thấy mà không chiếm mất một khóa hợp lệ.

**Tại sao phải dùng kiểu `long` ở `range`?**

Cận mở như `a=Integer.MAX_VALUE` phải được chuyển về `a+1` bằng **phép tính không tràn** trước khi giao với miền. Tương tự, cận trên mở `b=Integer.MIN_VALUE` tương ứng `b-1`. Cách dùng `long` tránh tình huống khóa ở biên làm truy vấn trả sai.

**Tại sao `range` không được gọi O(r) trong mọi trường hợp?**

`BitSet.nextSetBit` có thể phải đi qua những từ rỗng trước khi gặp bit bật. Vì API không nhận cận trên, mã minh họa còn có thể quét **xa hơn đoạn yêu cầu** trước khi nhận ra đã hết kết quả. Thời gian quét phụ thuộc **số từ thực sự được kiểm tra**, không chỉ số lượng `r` kết quả.

### Giới hạn của chương trình

`BitSet` và mảng Java dùng chỉ số `int` trong ví dụ; cấu trúc không được thiết kế để cấp phát miền rộng tới `2^{32}`, dù **mẫu bit của một số `int`** có 2^32 khả năng. Bộ nhớ có sẵn và giới hạn mảng thực tế có thể nhỏ hơn nhiều ngưỡng `Integer.MAX_VALUE`. Chương trình cũng không triển khai lưu trữ bền vững, truy cập đồng thời hay dữ liệu đi kèm khóa; nó là **tập membership minh họa trong RAM**.

## 13. Thực hành kiểm tra bằng một oracle tập hợp

Để kiểm thử cấu trúc dựa trên miền hữu hạn, có thể dùng `TreeSet<Integer>` làm tập chuẩn:

```text
oracle = {}
boundedSet = new BoundedIntegerSet(-3, 10)

for operation in a valid-key sequence:
    expected = oracle.add/remove(key)
    actual = boundedSet.add/remove(key)
    assert expected == actual

    for key from -3 to 10:
        assert boundedSet.contains(key) == oracle.contains(key)
    assert boundedSet.size() == oracle.size()
```

Với miền nhỏ, quét toàn bộ `U` khóa sau mỗi cập nhật là cách **dễ phát hiện lỗi ánh xạ**. Với miền rất lớn, không nên quét `U` sau mỗi thao tác; dùng test chọn mẫu, kiểm tra tập khóa đang lưu hoặc kỹ thuật kiểm chứng khác.

Các trường hợp biên nên thử:

| Trường hợp | Kết quả cần có |
| --- | --- |
| Thêm khóa nhỏ nhất `minKey` | Bit đầu tiên được bật |
| Thêm khóa lớn nhất `maxKey` | Bit cuối cùng của miền được bật |
| Thêm lại khóa đã có | Không tăng `size` |
| Xóa khóa chưa có nhưng vẫn trong miền | Không giảm `size` |
| Chèn khóa ngoài miền | Báo lỗi theo hợp đồng của ví dụ |
| `ceiling` dưới cận dưới | Trả khóa nhỏ nhất đang có, nếu có |
| `higher(maxKey)` | Trả `null` |
| Khoảng mở với hai cận bằng nhau | Kết quả rỗng |
| Khoảng ở `Integer.MIN/MAX_VALUE` | Không tràn khi tính cận |
| Xóa đến tập rỗng | `size=0` và quét khoảng trả danh sách rỗng |

## 14. Những sai lầm thường gặp

1. **Nhầm `U` với `n`.** Một tập có 500 khóa trong miền một tỷ cần nhiều ô nếu cấp phát địa chỉ trực tiếp cho mọi khả năng.
2. **Nhầm khóa lớn nhất với số phần tử miền.** Miền `0..999` có 1.000 giá trị, không phải 999.
3. **Quên `+1` khi tính đoạn đóng `[a,b]`.** Số giá trị là `b-a+1`.
4. **Tính `b-a+1` trong `int` khi cận có thể là MIN/MAX.** Cần mở rộng kiểu trước khi trừ.
5. **Cho rằng máy 64 bit có thể cấp phát mảng `2^{64}` ô.** Khả năng biểu diễn địa chỉ không đồng nghĩa dung lượng RAM.
6. **Cho rằng mọi phép toán trên `BigInteger` là O(1).** Giá trị có thể chiếm nhiều từ máy, nên chi phí phụ thuộc độ dài bit.
7. **Không phân biệt so sánh có dấu và không dấu.** Cùng mẫu bit có thể mang thứ tự số học khác nhau.
8. **Dùng `1 << 32` hoặc `1L << 64` để biểu diễn `2^{32}` hoặc `2^{64}`.** Java giới hạn số bit dịch theo độ rộng toán hạng, gây kết quả bất ngờ.
9. **Dùng `-1` làm “không tìm thấy” dù miền hợp lệ có khóa -1.** Dùng một dạng kết quả phân biệt được trạng thái tìm thấy.
10. **Dùng chỉ số âm cho `BitSet` hoặc array.** Cần ánh xạ `x-minKey` và kiểm tra biên.
11. **Ép `offset` kiểu `long` sang `int` khi chưa kiểm tra dung lượng miền.** Có thể tràn thành chỉ số sai.
12. **Nhầm `boolean[U]` với `U` bit đúng nghĩa.** Dung lượng boolean array phụ thuộc biểu diễn JVM; bitset mới có mục tiêu nén bit.
13. **Giả định `BitSet` tự động tiết kiệm bộ nhớ cho một tập thưa có bit cao rất lớn.** Nó vẫn phải lưu đủ các từ tới vùng bit cao đã được dùng.
14. **Gọi `nextSetBit` là O(1) bất kể `U`.** Có thể phải quét qua rất nhiều từ rỗng.
15. **Coi `cardinality()` trên bitmap không có bộ đếm là O(1).** Có thể cần đếm các từ; chỉ `size` được duy trì riêng mới đọc O(1).
16. **Nhầm membership với ánh xạ giá trị.** Bitset chỉ trả “có/không”; muốn lưu payload phải có cấu trúc bổ sung.
17. **Dùng 0 làm dấu “ô trống” trong bảng mà 0 cũng là giá trị hợp lệ.** Cần cờ `occupied` hoặc quy ước không xung đột.
18. **Cho rằng bảng băm có worst-case O(1) vì trung bình O(1).** Các trường hợp va chạm hoặc giả định hàm băm ảnh hưởng bảo đảm.
19. **Dùng complement trên toàn từ cuối mà không che bit ngoài `U`.** Có thể tạo những bit “khóa” nằm ngoài miền.
20. **Lấy thuật toán cho tập khóa phân biệt để xử lý khóa trùng mà không đổi biểu diễn.** Muốn đếm tần suất hoặc lưu nhiều bản ghi cùng khóa phải dùng bộ đếm, danh sách hoặc khóa ghép.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Miền `[0,999]` có bao nhiêu khóa có thể có?

**Đáp án:** `U=999-0+1=1000`.

**Câu 2.** Phân biệt `U`, `n` và `w`.

**Đáp án:** `U` là số giá trị khóa được phép; `n` là số khóa phân biệt đang lưu; `w` là số bit của một từ trong mô hình máy.

**Câu 3.** Nếu `U=101`, cần bao nhiêu bit tối thiểu để mã hóa một vị trí khóa?

**Đáp án:** `\lceil\log_2 101\rceil=7` bit vì 6 bit chỉ có 64 mẫu, còn 7 bit có 128 mẫu.

**Câu 4.** Với số nguyên không dấu 8 bit, miền giá trị là gì? Với số nguyên bù hai có dấu 8 bit thì sao?

**Đáp án:** Không dấu `[0,255]`; có dấu `[-128,127]`. Cả hai có 256 mẫu bit.

**Câu 5.** Một tập có `n=500` khóa trong miền `U=1\,000\,000\,000` có phải tập đậm đặc không?

**Đáp án:** Không, rất thưa; `n/U=5\times10^{-7}`.

**Câu 6.** Với miền `[-3,10]`, khóa `4` được ánh xạ tới chỉ số bit nào?

**Đáp án:** `4-(-3)=7`.

**Câu 7.** Tại sao phép tính `(int)b-(int)a+1` có thể sai khi `a=Integer.MIN_VALUE` và `b=Integer.MAX_VALUE`?

**Đáp án:** Vì miền có `2^{32}` phần tử, vượt giới hạn kiểu `int` có dấu; phép trừ/cộng trong `int` bị tràn. Cần chuyển sang `long` trước khi tính.

**Câu 8.** Miền `U=16` với tập `\{0,3,5,9\}` có bitmap 16 bit bằng gì khi viết từ bit cao xuống thấp?

**Đáp án:** `0000\,0010\,0010\,1001`, tức `0x0229`.

**Câu 9.** Trong bitmap chia theo từ 64 bit, khóa `70` nằm ở từ số mấy và bit số mấy (đếm từ 0)?

**Đáp án:** `70/64=1`, bit `70\bmod64=6`.

**Câu 10.** Vì sao `contains(x)` bằng địa chỉ trực tiếp có thể O(1), còn khởi tạo cả bảng có thể O(U)?

**Đáp án:** Tra cứu chỉ đọc đúng một ô đã có; khởi tạo/cấp phát có thể phải chuẩn bị hoặc biểu diễn đủ `U` ô.

**Câu 11.** Dung lượng bitset lý tưởng cho `U=1\,000\,000` là bao nhiêu byte?

**Đáp án:** `U/8=125\,000` byte, khoảng 122,1 KiB, chưa kể metadata và làm tròn từ máy.

**Câu 12.** Dung lượng bitmap lý tưởng cho toàn bộ `2^{32}` mẫu bit của khóa 32 bit là bao nhiêu?

**Đáp án:** `2^{32}/8=536\,870\,912` byte, tức 512 MiB.

**Câu 13.** Khi chỉ cần membership của các khóa `0..31`, dùng bao nhiêu từ `int` 32 bit là đủ?

**Đáp án:** Một từ `int`, nếu mỗi bit mã hóa trạng thái có/không của một khóa.

**Câu 14.** Vì sao không thể gọi `BitSet.nextSetBit(i)` là O(1) worst-case theo `U`?

**Đáp án:** Nó có thể phải quét nhiều từ không có bit bật trước khi tìm thấy khóa kế tiếp hoặc tới hết bitmap.

**Câu 15.** Một bitset đã cấp phát nhưng không giữ biến `size`. Muốn biết tổng số bit bật, cần thao tác gì?

**Đáp án:** Đếm bit bật trong các từ (ví dụ `popcount`) và cộng lại; không được mặc định là O(1) trên toàn miền.

**Câu 16.** Với một bitmap tập hợp, phép toán nào cho hợp và giao của hai tập cùng miền?

**Đáp án:** OR cho hợp và AND cho giao; phép hiệu dùng `A AND NOT B` cùng xử lý mask biên phù hợp.

**Câu 17.** Nếu một bảng direct-address cần lưu giá trị số 0 hợp lệ, tại sao chỉ dùng 0 làm dấu “không có khóa” sẽ sai?

**Đáp án:** Không thể phân biệt mục thật có giá trị 0 với ô chưa từng được gán; cần cờ tồn tại hoặc cách đánh dấu không xung đột.

**Câu 18.** Với miền cực lớn nhưng chỉ lưu vài nghìn khóa, thường cân nhắc bảng băm hay bitset dày đặc trước?

**Đáp án:** Bảng băm thường là ứng viên tốt cho tìm chính xác do dùng bộ nhớ theo số mục `n` thay vì số khả năng `U`; nếu cần thứ tự, cân nhắc cây cân bằng.

**Câu 19.** Tại sao `Integer.compareUnsigned(-1,1)` cho kết quả xem `-1` lớn hơn `1`?

**Đáp án:** Mẫu bit của `-1` là `0xffffffff`, có giá trị không dấu `2^{32}-1`, lớn hơn 1.

**Câu 20.** Thuật toán kiểu van Emde Boas được nhắc tới vì đại lượng nào xuất hiện trong độ phức tạp của nó?

**Đáp án:** Kích thước miền `U`: một số thao tác đạt O(log log U) trong mô hình lý thuyết phù hợp, đánh đổi chi phí không gian lớn của phiên bản cổ điển.

**Điểm ghi nhớ:** Với khóa số nguyên, cần phân biệt **miền có `U` giá trị**, **tập đang lưu `n` khóa** và **từ máy có `w` bit**. Từ `U` và `w` ta biết khả năng biểu diễn chỉ số, cách đóng gói các bit và giá của những cấu trúc địa chỉ trực tiếp. **Miền nhỏ/đậm đặc** thường hợp với mảng hoặc bitset; **miền lớn/tập thưa** thường hợp hơn với bảng băm hoặc cây khi cần thứ tự. Truy cập bit có thể O(1), nhưng duyệt khoảng và tìm phần tử kế tiếp còn chịu chi phí quét những từ rỗng. Luôn kiểm tra **cận miền, dấu số nguyên, tràn số và dung lượng bộ nhớ thực tế** trước khi chọn cấu trúc.
