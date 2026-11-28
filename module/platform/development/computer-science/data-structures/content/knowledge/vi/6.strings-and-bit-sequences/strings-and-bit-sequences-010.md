# Hợp, giao, hiệu và đếm phần tử bằng phép toán bit

Giả sử một hệ thống có một triệu đối tượng được đánh số từ 0 đến 999.999. Ta muốn biết đối tượng nào đã được người dùng A chọn, đối tượng nào được người dùng B chọn, các đối tượng được **cả hai** chọn, chỉ được **một trong hai** chọn, hoặc có bao nhiêu đối tượng thỏa đồng thời hai điều kiện. Nếu lưu mỗi tập hợp bằng một **bitset**, chỉ cần các phép toán trên từ máy để tính hợp, giao, hiệu và số phần tử.

Bài thuộc chương **Chuỗi và dãy bit** trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trọng tâm là cách biểu diễn tập hợp bằng dãy bit, giữ bất biến về miền giá trị và bit đệm, dùng OR/AND/AND-NOT/XOR/NOT và **population count (popcount)** đúng cách, phân tích độ phức tạp thời gian/bộ nhớ, rồi quyết định khi nào nên dùng bitset thay cho bảng băm, danh sách hoặc bitmap nén.

## 1. Bitset biểu diễn một tập hợp như thế nào?

Cho một **miền hữu hạn, được đánh số**:

\[
U=\{0,1,\ldots,n-1\}.
\]

Một tập con \(A\subseteq U\) được biểu diễn bởi dãy \(n\) bit:

\[
B_A[i]=
\begin{cases}
1 & \text{khi } i\in A,\\
0 & \text{khi } i\notin A.
\end{cases}
\]

Ví dụ, với \(U=\{0,1,\ldots,7\}\) và \(A=\{0,2,5\}\):

```text
Chỉ số:      0 1 2 3 4 5 6 7
Thuộc A?     1 0 1 0 0 1 0 0

Viết dưới dạng byte (bit 7 ở trái, bit 0 ở phải):
             00100101 = 0x25
```

Trong bài này, quy ước **chỉ số logic 0 ứng với bit thấp nhất (LSB)** của từ lưu trữ đầu tiên. Nếu mỗi từ chứa \(w\) bit thì:

\[
\text{wordIndex}(i)=\left\lfloor\frac{i}{w}\right\rfloor,
\qquad
\text{bitOffset}(i)=i\bmod w.
\]

Với chỉ số hợp lệ \(0\le i<n\), giá trị tại vị trí \(i\) được kiểm tra bằng mask \(1\ll(i\bmod w)\) trên từ \(\text{words}[i//w]\).

**Điều kiện tiên quyết của các phép tập hợp:** các bitset phải dùng **cùng miền chỉ số, cùng ánh xạ ID sang vị trí bit và cùng quy ước biểu diễn**. Nếu trong bitset A, bit 5 có nghĩa “đỉnh 5”, còn trong bitset B, bit 5 có nghĩa “người dùng 5”, phép AND tuy hợp lệ ở mức bit nhưng không có ý nghĩa tập hợp mong muốn.

### Tại sao một tập hợp chỉ cần một bit mỗi phần tử của miền?

Vì một phần tử hoặc thuộc tập, hoặc không thuộc tập, nên mỗi vị trí chỉ cần một giá trị Boolean. Với miền \(n\) vị trí, bitset lý tưởng cần \(n\) bit dữ liệu logic. Triển khai thực tế thường cấp phát theo **byte** hoặc **từ máy**, do đó có thể có bit đệm và metadata lưu độ dài.

Tập hợp không lưu mỗi ID riêng như một danh sách. ID được suy ra từ **vị trí bit**. Nhờ vậy, hai tập cùng miền có thể kết hợp bằng các phép toán bit trên toàn bộ từ máy.

## 2. Bốn phép tập hợp cơ bản

Xét hai tập \(A,B\subseteq U\). Ta có:

| Phép toán tập hợp | Biểu thức trên bitset | Điều kiện để bit \(i\) của kết quả bằng 1 |
|---|---|---|
| **Hợp** \(A\cup B\) | `A \| B` (OR) | \(i\) thuộc A **hoặc** B |
| **Giao** \(A\cap B\) | `A & B` (AND) | \(i\) thuộc **cả** A và B |
| **Hiệu** \(A\setminus B\) | `A & ~B` (AND-NOT) | \(i\) thuộc A nhưng **không** thuộc B |
| **Hiệu đối xứng** \(A\triangle B\) | `A ^ B` (XOR) | \(i\) thuộc **đúng một** trong hai tập |

Phép **bù** trong miền \(U\) là \(U\setminus A\), có thể biểu diễn bằng `~A` **sau khi giới hạn kết quả về đúng \(n\) bit logic**.

### Bảng chân trị cho một vị trí

| Bit A | Bit B | A OR B | A AND B | A AND NOT B | A XOR B |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 | 0 |
| 0 | 1 | 1 | 0 | 0 | 1 |
| 1 | 0 | 1 | 0 | 1 | 1 |
| 1 | 1 | 1 | 1 | 0 | 0 |

Vì kết quả tại một vị trí chỉ phụ thuộc hai bit tương ứng, ta có thể áp dụng bảng chân trị **đồng thời** cho 8, 32 hoặc 64 vị trí trong một phép toán trên byte/từ máy.

### Hợp: phép OR

```text
A:      00100101
B:      00000110
A | B:  00100111
```

Mỗi vị trí bằng 1 nếu xuất hiện trong ít nhất một tập. Khi nhiều tập cần hợp, có thể OR các từ tương ứng lần lượt để tích lũy kết quả.

### Giao: phép AND

```text
A:      00100101
B:      00000110
A & B:  00000100
```

Chỉ các bit cùng bằng 1 mới được giữ lại. Ví dụ trên cho biết phần tử 2 thuộc cả hai tập.

### Hiệu: phép AND-NOT

```text
A:        00100101
B:        00000110
NOT B:    11111001  (trong phạm vi 8 bit)
A & ~B:   00100001
```

Hiệu có hướng: \(A\setminus B\) **khác** \(B\setminus A\) trong trường hợp tổng quát. Không nên nhầm hiệu với XOR:

- `A & ~B` giữ phần tử chỉ thuộc A.
- `A ^ B` giữ phần tử chỉ thuộc **A hoặc B**, theo cả hai hướng.

### Hiệu đối xứng: phép XOR

```text
A:      00100101
B:      00000110
A ^ B:  00100011
```

XOR hữu ích khi cần biết những vị trí có trạng thái khác nhau giữa hai bộ cờ hoặc giữa hai phiên bản của một tập hợp.

## 3. Ví dụ xuyên suốt trên 13 vị trí

Cho miền:

\[
U=\{0,1,2,\ldots,12\}.
\]

Xét hai tập:

\[
A=\{0,2,5,8,12\},\qquad
B=\{1,2,8,9\}.
\]

Số phần tử ban đầu là \(|A|=5\) và \(|B|=4\).

Với cách đóng gói theo byte, bit logic 0 là LSB trong byte đầu:

```text
                 Byte 0       Byte 1
              (bit 0..7)   (bit 8..12 + padding)

A:              00100101       00010001
                   0x25           0x11

B:              00000110       00000011
                   0x06           0x03
```

Trong byte thứ hai, chỉ **5 bit thấp** là dữ liệu (vị trí logic 8 đến 12); **3 bit cao** là padding.

Ta tính từng phép:

| Phép | Byte 0 | Byte 1 | Các vị trí có bit 1 | Số phần tử |
|---|---|---|---|---:|
| A | `0x25` | `0x11` | \(\{0,2,5,8,12\}\) | 5 |
| B | `0x06` | `0x03` | \(\{1,2,8,9\}\) | 4 |
| \(A\cup B\) | `0x27` | `0x13` | \(\{0,1,2,5,8,9,12\}\) | 7 |
| \(A\cap B\) | `0x04` | `0x01` | \(\{2,8\}\) | 2 |
| \(A\setminus B\) | `0x21` | `0x10` | \(\{0,5,12\}\) | 3 |
| \(B\setminus A\) | `0x02` | `0x02` | \(\{1,9\}\) | 2 |
| \(A\triangle B\) | `0x23` | `0x12` | \(\{0,1,5,9,12\}\) | 5 |

Bảng cho thấy phép toán bit hoạt động **theo từng từ**, không cần tách mỗi Boolean ra khỏi bộ nhớ rồi xử lý riêng.

### Kiểm tra bằng quan hệ số phần tử

Theo công thức cộng-trừ:

\[
|A\cup B|=|A|+|B|-|A\cap B|
=5+4-2=7.
\]

Ngoài ra:

\[
|A\setminus B|=|A|-|A\cap B|=5-2=3,
\]

\[
|A\triangle B|
=|A|+|B|-2|A\cap B|
=5+4-4=5.
\]

Những công thức này là **bất biến toán học** hữu ích để kiểm tra kết quả phép toán bit trong chương trình.

## 4. Phép NOT và câu hỏi “bù so với miền nào?”

Một giá trị nhị phân trong từ máy có **độ rộng vật lý** xác định, còn bitset có **độ dài logic** \(n\). Vì vậy phép NOT không thể hiểu là “lật mọi bit trong bộ nhớ” nếu mục tiêu là lấy bù theo miền \(U=\{0,\ldots,n-1\}\).

Với \(n=13\), bù của A là:

\[
U\setminus A=\{1,3,4,6,7,9,10,11\}.
\]

Kết quả theo byte:

```text
A:               00100101  00010001
NOT A (8 bit):   11011010  11101110
                                   ^^^
                           bit padding cũng đã bị đảo

Mask byte cuối:             00011111
Bù hợp lệ:       11011010  00001110
                   0xDA       0x0E
```

Tại byte cuối, ta chỉ giữ 5 bit dữ liệu bằng mask `0x1F`:

```text
complement_last_byte = (~last_byte) & 0x1F
```

**Bù của tập hợp phải tương ứng với một miền cụ thể.** Nếu không xác định \(n\), câu “những phần tử không thuộc A” có thể là vô hạn hoặc mơ hồ. Với bitset, \(n\) là một phần của dữ liệu và hợp đồng API.

### Tạo mask cho từ cuối

Với từ rộng \(w\) bit và \(r=n\bmod w\):

\[
\text{tailMask}=
\begin{cases}
2^w-1 & \text{khi }r=0\text{ và tồn tại từ cuối đầy},\\
2^r-1 & \text{khi }1\le r<w.
\end{cases}
\]

Nếu \(n=0\), không có từ cuối để đọc hay sửa.

**Trong C/C++, không tạo \(2^w-1\) bằng `(1 << w) - 1` trên kiểu có đúng \(w\) bit**, vì dịch bằng độ rộng toán hạng là không hợp lệ. Với từ 64 bit không dấu, dùng `UINT64_MAX` khi từ cuối đầy.

Với một hiệu `A & ~B`, nếu A đã bảo đảm padding bằng 0, AND sẽ tự loại các bit padding, dù NOT của B lật chúng. Tuy vậy, việc **mask kết quả cuối** vẫn là quy tắc tốt cho các API có thể nhận bitset từ nguồn ngoài hoặc thao tác bù toàn bộ.

## 5. Đếm số phần tử bằng `popcount`

**Cardinality** (lực lượng) của tập hợp A là số vị trí có bit 1 trong bitset:

\[
|A|=\sum_{i=0}^{n-1} B_A[i].
\]

Với một từ máy \(x\), `popcount(x)` là số bit 1 trong biểu diễn nhị phân của từ đó.

Ví dụ:

```text
x = 00100101
các bit 1 ở vị trí 0, 2, 5
popcount(x) = 3
```

Nếu bitset được lưu trong \(q=\lceil n/w\rceil\) từ máy, ta có thể tính:

\[
|A|=\sum_{j=0}^{q-1}\operatorname{popcount}(A_j),
\]

với điều kiện các bit đệm bằng 0 hoặc từ cuối được mask trước khi đếm.

Đếm trực tiếp kết quả các phép toán:

\[
|A\cap B|=\sum_j\operatorname{popcount}(A_j\ \&\ B_j),
\]

\[
|A\cup B|=\sum_j\operatorname{popcount}(A_j\ |\ B_j),
\]

\[
|A\setminus B|=\sum_j\operatorname{popcount}(A_j\ \&\ \sim B_j).
\]

**Ưu điểm:** nếu chỉ cần **số phần tử**, ta không phải tạo bitset kết quả trung gian. Có thể AND/OR từng từ rồi popcount ngay, chỉ duy trì một biến tổng.

### Hai cách đếm bit 1 trong một từ

**Cách dùng primitive CPU/thư viện:** Nhiều CPU và compiler hiện đại có lệnh hoặc hàm `popcount`, hoạt động hiệu quả trên từ 32/64 bit. Trong mô hình RAM với từ cố định, coi một lần popcount trên một từ là \(O(1)\). Tổng đếm cả bitset là \(O(q)\).

**Cách xóa bit 1 thấp nhất:** Với từ không dấu khác 0, biểu thức `x &= x - 1` xóa bit 1 thấp nhất. Số lần lặp chính là số bit 1:

```text
count = 0
while x != 0:
    x = x & (x - 1)
    count += 1
return count
```

Nếu có \(r_j\) bit 1 trong từ `j`, cách này chạy \(r_j\) vòng. Trên toàn bitset, phải đi qua \(q\) từ và xóa tổng cộng \(r\) bit 1, nên chi phí \(O(q+r)\) phép xử lý từ trong mô hình từ cố định. Trên một từ 64 bit, \(r_j\le64\), vì vậy thuật toán cũng bị chặn bởi một hằng số cho mỗi từ.

## 6. Không cần dựng kết quả mới để đếm hợp, giao, hiệu

Cho hai bitset A, B cùng độ dài \(n\). Một thuật toán chỉ **đếm giao** có thể viết:

```text
intersection_count(A, B):
    require A.bitLength == B.bitLength
    total = 0
    for j in 0 .. wordCount-1:
        word = A.words[j] & B.words[j]
        if j is last word:
            word = word & validTailMask
        total += popcount(word)
    return total
```

Các thao tác khác chỉ cần thay phép toán tạo `word`:

- Đếm hợp: `A.words[j] | B.words[j]`.
- Đếm hiệu \(A\setminus B\): `A.words[j] & ~B.words[j]`.
- Đếm hiệu đối xứng: `A.words[j] ^ B.words[j]`.
- Đếm phần bù A: `(~A.words[j]) & validMask(j)`.

Không tạo mảng kết quả mới nên bộ nhớ phụ là **\(O(1)\)** ngoài dữ liệu đầu vào và biến đếm (giả sử bộ đếm chứa được giá trị đến \(n\)).

### Công thức tiết kiệm phép tính

Nếu đã biết \(|A|\), \(|B|\) và \(|A\cap B|\), ta suy ra:

\[
|A\cup B|=|A|+|B|-|A\cap B|,
\]

\[
|A\setminus B|=|A|-|A\cap B|,
\]

\[
|A\triangle B|=|A|+|B|-2|A\cap B|.
\]

Những đẳng thức này có thể giảm số lần quét nếu các số đếm đã được tính hoặc lưu sẵn. Nhưng nếu phải đếm lại \(|A|\), \(|B|\) và \(|A\cap B|\) từ đầu, việc tận dụng công thức chưa chắc nhanh hơn một lượt quét trực tiếp; lựa chọn còn phụ thuộc cache, băng thông bộ nhớ và số truy vấn lặp lại.

## 7. Ví dụ Python: bitset trong một số nguyên

Python hỗ trợ số nguyên độ dài tùy ý và có toán tử `&`, `|`, `^`, `~` cùng phương thức `int.bit_count()`. Đây là cách gọn để học quy tắc tập hợp trên một miền nhỏ.

```python
N = 13
DOMAIN_MASK = (1 << N) - 1

def make_mask(indices):
    mask = 0
    for index in indices:
        if not 0 <= index < N:
            raise IndexError("Vị trí ngoài miền")
        mask |= 1 << index
    return mask

def members(mask):
    # Dễ hiểu cho ví dụ; duyệt tất cả N vị trí.
    return [i for i in range(N) if (mask >> i) & 1]

a = make_mask([0, 2, 5, 8, 12])
b = make_mask([1, 2, 8, 9])

union = a | b
intersection = a & b
difference = a & ~b
reverse_difference = b & ~a
symmetric = a ^ b
complement_a = (~a) & DOMAIN_MASK

print(members(union))             # [0, 1, 2, 5, 8, 9, 12]
print(members(intersection))      # [2, 8]
print(members(difference))        # [0, 5, 12]
print(members(reverse_difference))# [1, 9]
print(members(symmetric))         # [0, 1, 5, 9, 12]
print(members(complement_a))      # [1, 3, 4, 6, 7, 9, 10, 11]

print(a.bit_count())              # 5
print(b.bit_count())              # 4
print(union.bit_count())          # 7
print(intersection.bit_count())   # 2
print(difference.bit_count())     # 3
print(symmetric.bit_count())      # 5

assert union.bit_count() == (
    a.bit_count() + b.bit_count() - intersection.bit_count()
)
```

`int.bit_count()` có trong Python từ phiên bản 3.10. Hàm `members` được viết theo cách duyệt toàn miền để minh họa; nếu số bit bật rất ít, có thể dùng vòng lặp loại bit 1 thấp nhất để tránh kiểm tra từng vị trí.

**Lưu ý về độ phức tạp:** `int` của Python có thể chứa **hàng triệu bit**. Khi đó phép `a | b` hay `a.bit_count()` không phải \(O(1)\) độc lập kích thước số nguyên; runtime phải xử lý các từ nội bộ của `int`. Trong bài này, với \(N=13\), mọi phép toán chỉ xử lý số lượng từ nội bộ rất nhỏ.

### Vì sao phải mask sau `~` trong Python?

Số nguyên Python không bị giới hạn vào đúng 13 bit vật lý. Với số nguyên không âm \(a\), `~a` là số âm theo quy tắc biểu diễn số nguyên có dấu không giới hạn chiều rộng logic, không phải trực tiếp một dãy 13 bit. Để lấy phần bù theo \(U\), cần:

```python
complement_a = (~a) & ((1 << N) - 1)
```

Biểu thức này đảm bảo chỉ các vị trí từ 0 đến `N-1` được giữ lại. Đây cũng là nguyên tắc chung khi thực hiện NOT trên bitset có padding.

## 8. Ví dụ C: bitset 70 vị trí trên hai từ 64 bit

Một triển khai thực tế thường lưu nhiều từ `uint64_t`. Ví dụ có miền từ 0 đến 69, nên số từ là:

\[
q=\left\lceil\frac{70}{64}\right\rceil=2.
\]

Từ đầu có 64 bit dữ liệu, từ thứ hai chỉ có **6 bit dữ liệu** và 58 bit padding. Hai tập sau dùng để kiểm tra:

\[
A=\{0,2,63,64,69\}, \qquad B=\{2,63,65,69\}.
\]

Suy ra:

- \(A\cup B=\{0,2,63,64,65,69\}\), có **6** phần tử.
- \(A\cap B=\{2,63,69\}\), có **3** phần tử.
- \(A\setminus B=\{0,64\}\), có **2** phần tử.
- \(A\triangle B=\{0,64,65\}\), có **3** phần tử.

Mã C11 hoàn chỉnh:

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define NBITS 70u
#define WORD_BITS 64u
#define WORD_COUNT (NBITS / WORD_BITS + (NBITS % WORD_BITS != 0u))

typedef struct {
    uint64_t words[WORD_COUNT];
} BitSet;

static bool bit_set(BitSet *set, size_t i) {
    if (i >= NBITS) return false;
    const size_t j = i / WORD_BITS;
    const unsigned offset = (unsigned)(i % WORD_BITS);
    set->words[j] |= UINT64_C(1) << offset;
    return true;
}

static uint64_t tail_mask(void) {
    const unsigned used = NBITS % WORD_BITS;
    return used == 0u
        ? UINT64_MAX
        : ((UINT64_C(1) << used) - UINT64_C(1));
}

// Đếm bằng cách xóa lần lượt bit 1 thấp nhất.
static size_t popcount_word(uint64_t word) {
    size_t count = 0;
    while (word != 0) {
        word &= word - UINT64_C(1);
        ++count;
    }
    return count;
}

static size_t count_bits(const BitSet *set) {
    size_t total = 0;
    for (size_t j = 0; j < WORD_COUNT; ++j) {
        uint64_t word = set->words[j];
        if (j + 1 == WORD_COUNT) word &= tail_mask();
        total += popcount_word(word);
    }
    return total;
}

int main(void) {
    BitSet a = {{0}};
    BitSet b = {{0}};
    BitSet uni = {{0}};
    BitSet inter = {{0}};
    BitSet diff = {{0}};
    BitSet sym = {{0}};

    const size_t positions_a[] = {0, 2, 63, 64, 69};
    const size_t positions_b[] = {2, 63, 65, 69};

    for (size_t i = 0; i < sizeof positions_a / sizeof positions_a[0]; ++i) {
        bit_set(&a, positions_a[i]);
    }
    for (size_t i = 0; i < sizeof positions_b / sizeof positions_b[0]; ++i) {
        bit_set(&b, positions_b[i]);
    }

    for (size_t j = 0; j < WORD_COUNT; ++j) {
        uni.words[j] = a.words[j] | b.words[j];
        inter.words[j] = a.words[j] & b.words[j];
        diff.words[j] = a.words[j] & ~b.words[j];
        sym.words[j] = a.words[j] ^ b.words[j];
    }

    // Từ cuối chỉ có 6 bit hợp lệ.
    const uint64_t mask = tail_mask();
    uni.words[WORD_COUNT - 1] &= mask;
    inter.words[WORD_COUNT - 1] &= mask;
    diff.words[WORD_COUNT - 1] &= mask;
    sym.words[WORD_COUNT - 1] &= mask;

    printf("A=%zu, B=%zu\n", count_bits(&a), count_bits(&b));
    printf("union=%zu, intersection=%zu\n",
           count_bits(&uni), count_bits(&inter));
    printf("A_minus_B=%zu, symmetric=%zu\n",
           count_bits(&diff), count_bits(&sym));

    // A=5, B=4
    // union=6, intersection=3
    // A_minus_B=2, symmetric=3
    return 0;
}
```

Ví dụ dùng độ dài cố định `NBITS = 70` nên `WORD_COUNT > 0`, có thể truy cập từ cuối. Nếu thiết kế API động cho phép `NBITS = 0`, phải xử lý dãy rỗng **trước khi** truy cập `words[WORD_COUNT - 1]`.

Hàm `count_bits` dùng phiên bản popcount portable không phụ thuộc compiler builtin; số vòng trong mỗi từ bằng số bit 1 của từ. Nếu môi trường hỗ trợ intrinsic popcount cho `uint64_t`, có thể thay hàm đó để giảm số vòng xử lý, sau khi kiểm tra tính tương thích compiler và kiến trúc.

## 9. Độ phức tạp theo số bit và số từ

Gọi:

- \(n\): số bit logic của mỗi tập.
- \(w\): độ rộng một từ máy, ví dụ 64.
- \(q=\lceil n/w\rceil\): số từ lưu một tập.
- \(r\): tổng số bit đang bật trong kết quả cần liệt kê.

Giả sử A và B đã có cùng miền, lưu trong mảng từ liên tiếp và đã bảo đảm padding hợp lệ.

| Thao tác | Thời gian thường gặp | Bộ nhớ phụ |
|---|---|---|
| Kiểm tra phần tử `test(i)` | \(O(1)\) | \(O(1)\) |
| Đặt/xóa một bit `set(i)/clear(i)` | \(O(1)\) | \(O(1)\) |
| Tạo bitset kết quả hợp \(A\cup B\) | \(O(q)\) | \(O(q)\) từ mới |
| Tạo bitset kết quả giao \(A\cap B\) | \(O(q)\) | \(O(q)\) từ mới |
| Tạo bitset kết quả hiệu \(A\setminus B\) | \(O(q)\) | \(O(q)\) từ mới |
| Hợp/giao/hiệu **tại chỗ** trên A | \(O(q)\) | \(O(1)\) ngoài dữ liệu A |
| Đếm số bit 1 bằng popcount theo từ | \(O(q)\) nếu popcount mỗi từ \(O(1)\) | \(O(1)\) |
| Đếm giao chỉ từ A và B, không tạo bitset | \(O(q)\) nếu popcount theo từ \(O(1)\) | \(O(1)\) |
| Đếm bit 1 bằng `x &= x-1` | \(O(q+r)\) | \(O(1)\) |
| Liệt kê toàn bộ vị trí đang bật | \(O(q+r)\) nếu CTZ mỗi từ có chi phí hằng số | \(O(1)\) ngoài đầu ra |

**Diễn giải quan trọng:** \(q\) vẫn tăng theo \(n\). Nếu \(w=64\) là hằng số cố định, \(O(q)\) và \(O(n)\) có cùng bậc tiệm cận, nhưng xử lý theo từ có thể giảm số thao tác vòng lặp và lưu lượng dữ liệu xuống khoảng 1/64 so với mô hình một phần tử mỗi byte trong các tình huống phù hợp.

Ngoài ra, phép tạo kết quả mới phải cấp phát \(q\) từ. Nếu chương trình chỉ cần **số phần tử giao**, dùng `popcount(A[j] & B[j])` trực tiếp giúp tránh bộ nhớ \(O(q)\) cho bitset tạm.

### Khi dùng số nguyên lớn thay cho mảng từ

Trong Python, bitset có thể được giữ trong một `int` duy nhất. Nó vẫn là cấu trúc có kích thước phụ thuộc \(n\), và phép AND/OR/XOR cần xử lý nhiều “limb” bên trong khi \(n\) lớn. Không thể đánh giá chúng như một phép toán đơn \(O(1)\) cho tập hợp hàng triệu bit.

## 10. Duy trì bất biến khi thực hiện các phép tập hợp

Một bitset đóng gói không chỉ là một dãy số. Nó còn có **quy ước giải thích** dãy đó. Khi kết hợp hai bitset, phải bảo vệ những bất biến sau.

### 10.1. Cùng độ dài và cùng ý nghĩa bit

Nếu A có miền 100 đỉnh và B có miền 200 đỉnh, phép `A & B` cần hợp đồng rõ ràng: từ chối do khác miền, hoặc mở rộng miền có quy tắc xác định. Không nên tự ghép các từ có chiều dài khác nhau mà không định nghĩa ý nghĩa cho các bit thiếu.

Tương tự, hai bảng phân quyền có thể cùng 64 bit nhưng dùng hai bảng ánh xạ quyền→vị trí khác nhau. Bitwise AND vẫn chạy được về mặt máy tính, nhưng kết quả không đúng ý nghĩa nghiệp vụ.

### 10.2. Không tính các bit đệm

Với \(n=70\), hai từ 64 bit chứa 58 bit padding. Phép `~` trên từ cuối sẽ bật toàn bộ 58 bit này nếu không mask. Sau đó `popcount` có thể báo số lượng lớn hơn số phần tử logic.

Chính sách đơn giản là giữ padding luôn bằng 0. Đối với các kết quả AND/OR/XOR/difference, áp dụng tail mask sau khi kết hợp nếu không thể chắc chắn mọi đầu vào đã có padding sạch.

### 10.3. Tránh sửa nguồn ngoài ý muốn

Hai kiểu API khác nhau:

- `union(a, b)` **trả bitset mới**, giữ A và B.
- `a.union_in_place(b)` **sửa A**, không tạo bản sao kết quả mới.

Khi làm việc với đồ thị hoặc nhiều truy vấn dùng chung một bitset, sửa A ngoài ý muốn có thể phá trạng thái phục vụ truy vấn sau. Cần đặt tên API rõ ràng và kiểm thử rằng hàm thuần không thay đổi các đầu vào.

### 10.4. Không cập nhật metadata số phần tử sai cách

Nếu bitset lưu sẵn `cachedCount` để trả kích thước tập trong \(O(1)\), cập nhật số đếm phải theo **số bit thực sự chuyển trạng thái**, không phải theo số lần gọi.

Ví dụ:

- `set(i)` trên bit đang 1 **không** làm kích thước tập tăng.
- `clear(i)` trên bit đang 0 **không** làm kích thước tập giảm.
- Sau khi OR toàn từ, chênh lệch số đếm là `popcount(newWord) - popcount(oldWord)` trên phần dữ liệu hợp lệ.

Metadata giúp đọc số lượng nhanh nhưng thêm chi phí duy trì. Đối với ứng dụng hiếm khi hỏi số phần tử, quét popcount có thể đơn giản và ít rủi ro hơn.

## 11. Một số quan hệ tập hợp kiểm tra bằng phép toán bit

Ngoài tạo tập mới, ta có thể dùng bitwise để trả lời những câu hỏi logic.

### Kiểm tra hai tập rời nhau

Hai tập **rời nhau** nếu giao rỗng:

\[
A\cap B=\varnothing
\quad\Longleftrightarrow\quad
(A_j\ \&\ B_j)=0\ \text{với mọi }j.
\]

Có thể quét lần lượt các từ và **dừng ngay khi tìm được một từ AND khác 0**. Trường hợp xấu vẫn \(O(q)\); nếu gặp giao sớm, công việc thực tế ít hơn.

### Kiểm tra tập con

\(A\subseteq B\) khi không có phần tử nào chỉ thuộc A:

\[
A\subseteq B
\quad\Longleftrightarrow\quad
A\setminus B=\varnothing.
\]

Dạng bit:

```text
is_subset(A, B):
    for each word j:
        if (A[j] & ~B[j]) != 0:
            return false
    return true
```

Phải cùng miền và xử lý padding đúng cách. Thuật toán có thể dừng sớm khi gặp bit vi phạm.

### Kiểm tra hai tập bằng nhau

Hai tập cùng miền bằng nhau khi:

\[
A=B\quad\Longleftrightarrow\quad
(A_j\oplus B_j)=0\quad\text{với mọi }j.
\]

Có thể so sánh từng từ hoặc sử dụng XOR rồi kiểm tra bằng 0, không nhất thiết tạo bitset XOR riêng.

### Số vị trí khác nhau giữa hai trạng thái

**Khoảng cách Hamming** của hai dãy bit cùng độ dài là:

\[
d_H(A,B)=|A\triangle B|
=\sum_j\operatorname{popcount}(A_j\oplus B_j).
\]

Ví dụ A và B ở phần 3 có khoảng cách Hamming bằng **5**. Phép tính này hữu ích khi so sánh hai ảnh nhị phân, hai tập quyền hoặc hai snapshot cờ trạng thái.

## 12. Đếm giao và hợp để tính chỉ số tương đồng

Một ứng dụng phân loại hoặc tìm kiếm có thể cần đo mức độ trùng lặp giữa hai tập. Một số thước đo dùng số phần tử hợp/giao:

### Jaccard

\[
J(A,B)=\frac{|A\cap B|}{|A\cup B|}.
\]

Với A và B trong ví dụ:

\[
J(A,B)=\frac{2}{7}\approx 0{,}286.
\]

Nếu cả hai tập đều rỗng thì mẫu số bằng 0. Ứng dụng phải **định nghĩa chính sách** cho trường hợp này; một quy ước thường dùng là coi hai tập rỗng giống nhau hoàn toàn và cho giá trị 1, nhưng quy ước cụ thể phụ thuộc ngữ cảnh.

### Đếm phần tử chung

Nếu chỉ quan tâm có bao nhiêu đối tượng cùng thuộc hai tập, chỉ cần:

```text
total = 0
for each word j:
    total += popcount(A[j] & B[j])
```

Không cần lưu \((A\cap B)\) như một bitset. Đây là ví dụ của việc lựa chọn **truy vấn trực tiếp** thay vì tạo cấu trúc tạm, giúp giảm cấp phát và sử dụng bộ nhớ.

### Tỷ lệ phần tử của A cũng nằm trong B

Nếu A không rỗng:

\[
\frac{|A\cap B|}{|A|}.
\]

Ví dụ trên, tỷ lệ là \(2/5 = 0{,}4\). Cần xử lý riêng khi \(|A|=0\); không được chia cho 0.

Tất cả các thước đo này có thể tính từ các bộ đếm popcount, nhưng bitset chỉ là cách mã hóa tập hợp; nó **không tự quyết định** công thức thống kê nào là phù hợp cho bài toán.

## 13. Ứng dụng trong cấu trúc dữ liệu và thuật toán

### 13.1. Tìm đỉnh kề chung trong đồ thị

Với đồ thị có \(V\) đỉnh được đánh số từ 0 đến \(V-1\), có thể lưu tập đỉnh kề của mỗi đỉnh bằng một bitset độ dài \(V\).

- `neighbors[u] & neighbors[v]` cho biết những đỉnh kề chung của u và v.
- `popcount(neighbors[u] & neighbors[v])` đếm số đỉnh kề chung.

Nếu mỗi bitset dùng \(q=\lceil V/w\rceil\) từ, một truy vấn hai đỉnh mất \(O(q)\) thao tác từ, không cần duyệt toàn bộ các cặp cạnh riêng lẻ.

**Đánh đổi bộ nhớ:** lưu bitset kề cho **mọi** đỉnh tạo một dạng ma trận kề cần khoảng \(V^2\) bit dữ liệu. Đồ thị thưa có thể phù hợp hơn với **danh sách kề**, còn đồ thị dày hoặc truy vấn giao tập kề thường xuyên có thể hưởng lợi từ bitset.

### 13.2. Bộ lọc tìm kiếm theo nhiều điều kiện

Giả sử mỗi tài liệu có một ID và hệ thống lưu bitset:

- `containsData`: tài liệu chứa từ khóa “data”.
- `containsGraph`: tài liệu chứa “graph”.
- `isArchived`: tài liệu đã lưu trữ.

Truy vấn “có data **và** graph nhưng **không** đã lưu trữ” có thể biểu diễn:

```text
result = containsData & containsGraph & ~isArchived
```

Nếu các đầu vào cùng miền tài liệu và padding hợp lệ, kết quả là bitset đánh dấu các tài liệu thỏa điều kiện. Có thể dùng popcount để biết số tài liệu phù hợp trước khi liệt kê ID.

Hệ thống tìm kiếm thực tế có thể dùng **posting lists, compressed bitmaps hoặc cấu trúc lai** tùy mật độ xuất hiện của mỗi từ khóa. Bitset dày đặc không luôn là lựa chọn tốt nhất khi mỗi từ chỉ có ở một số rất ít tài liệu.

### 13.3. Gộp tập đánh dấu đã thăm

Hai nhánh của một thuật toán có thể tạo hai bitset đánh dấu các đối tượng đã xử lý. Phép OR cho biết những đối tượng được ít nhất một nhánh xử lý. Phép AND cho biết đối tượng cả hai nhánh đều xử lý; hiệu cho biết các đối tượng chỉ nhánh thứ nhất đã xử lý.

Khi có nhiều luồng cập nhật **cùng một từ máy**, phép OR kiểu đọc-sửa-ghi thông thường có thể bị **lost update** nếu thiếu đồng bộ. Việc tính OR của **hai bản snapshot đã hoàn tất** khác với việc nhiều luồng cùng ghi vào một bitset; trường hợp thứ hai có thể cần atomic hoặc khóa.

## 14. Khi nào bitset không phải lựa chọn tốt nhất?

Nếu miền \(U\) rất lớn mà tập hợp chứa rất ít phần tử, bitset dày đặc phải cấp phát nhiều từ bằng 0.

Ví dụ:

- Miền có \(n=1.000.000.000\) ID.
- Mỗi tập chỉ có 100 ID đang bật.
- Dãy bit lưu theo byte cần khoảng **125.000.000 byte** dữ liệu cho mỗi tập, chưa tính metadata.

Trong trường hợp đó, danh sách ID có thứ tự, hash set hoặc bitmap nén có thể tiết kiệm hơn nhiều. Các phép tập hợp có thể được hiện thực bằng:

- **Hai danh sách đã sắp xếp:** duyệt hai con trỏ để tính giao/hợp, chi phí \(O(|A|+|B|)\) theo số phần tử thực sự.
- **Hash set:** kiểm tra thành viên thường có thời gian kỳ vọng \(O(1)\) mỗi phần tử dưới các giả định bảng băm thông dụng, nhưng có overhead cho mỗi khóa.
- **Bitmap nén:** tận dụng các dải liên tục hoặc cấu trúc container thích ứng giữa miền dày và miền thưa; hiệu quả tùy phân bố dữ liệu và thuật toán.

Nếu miền vừa phải, nhiều bit được bật và truy vấn giao/hợp lặp lại thường xuyên, bitset theo từ máy có lợi thế rõ rệt vì thao tác một từ xử lý đồng thời nhiều vị trí.

## 15. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách tránh |
|---|---|---|
| AND hai bitset không cùng ánh xạ ID→bit | Kết quả có thể vô nghĩa dù phép toán vẫn chạy | Bảo đảm cùng miền và cùng quy ước |
| Dùng `A ^ B` để tính \(A\setminus B\) | Giữ cả phần tử chỉ thuộc B | Dùng `A & ~B` |
| Dùng `~A` mà không mask | Bật cả padding hoặc tạo số âm không mong đợi trong Python | Giới hạn kết quả về đúng \(n\) bit |
| Đếm popcount trên từ cuối có bit đệm 1 | Đếm cả phần tử không tồn tại | Xóa/mask padding |
| Tưởng OR/AND toàn bitset là \(O(1)\) | Bỏ qua \(q\) từ cần xử lý | Tính \(O(q)\), với \(q=\lceil n/w\rceil\) |
| Tạo bitset kết quả khi chỉ cần số lượng | Cấp phát và ghi mảng trung gian không cần thiết | Tính popcount trực tiếp trên từng từ |
| Giữ `cachedCount` nhưng tăng khi set bit vốn đã 1 | Sai kích thước tập | Chỉ cập nhật theo thay đổi trạng thái thực tế |
| Bất cẩn với `1 << 63` kiểu `int` | Dịch trên kiểu không phù hợp | Dùng toán hạng không dấu đủ rộng |
| Dịch `1 << 64` trên từ 64 bit | Không hợp lệ trong C/C++ | Xử lý riêng từ đầy khi làm tail mask |
| Sửa tập A tại chỗ dù người gọi cần A ban đầu | Mất dữ liệu cho các truy vấn sau | Phân biệt toán tử tạo mới với biến thể in-place |
| Nhiều luồng OR lên cùng từ mà không đồng bộ | Có thể mất cập nhật hoặc data race | Dùng atomic hoặc khóa phù hợp |
| Cấp phát bitset dày đặc cho miền cực thưa | Lãng phí RAM và thời gian quét các từ 0 | Xem xét sparse set/bitmap nén |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Với \(A=\{0,2,5,8,12\}\) và \(B=\{1,2,8,9\}\), hãy tính hợp, giao và hiệu \(A\setminus B\).

**Đáp án:** \(A\cup B=\{0,1,2,5,8,9,12\}\), \(A\cap B=\{2,8\}\), \(A\setminus B=\{0,5,12\}\).

**Câu 2.** Tại sao hiệu \(A\setminus B\) được tính bằng AND-NOT, không phải XOR?

**Đáp án:** AND-NOT giữ những bit bằng 1 ở A và 0 ở B. XOR giữ các bit khác nhau ở hai tập theo **cả hai hướng**, bao gồm cả vị trí chỉ thuộc B.

**Câu 3.** Trong ví dụ 13 bit, byte cuối của A là `0x11`. Tại sao lấy NOT rồi dùng luôn popcount là không chính xác?

**Đáp án:** Byte cuối có 3 bit padding. NOT bật cả các bit không thuộc miền; cần áp dụng mask `0x1F` trước khi đếm phần bù. Kết quả hợp lệ ở byte cuối là `0x0E`.

**Câu 4.** Hai bitset dài 1.000.000 bit dùng từ 64 bit. Cần bao nhiêu từ để thực hiện phép giao?

**Đáp án:** `ceil(1.000.000 / 64) = 15.625` từ cho mỗi bitset. Phép AND toàn tập cần 15.625 thao tác AND từ (chưa tính cấp phát, ghi bộ nhớ và phần xử lý bổ sung).

**Câu 5.** Muốn đếm giao của A và B, vì sao không nhất thiết phải tạo bitset \(A\cap B\)?

**Đáp án:** Có thể dùng `sum(popcount(A[j] & B[j]))` theo từng từ và cộng vào biến đếm. Cách này tránh mảng kết quả \(O(q)\), dùng \(O(1)\) bộ nhớ phụ.

**Câu 6.** Nếu \(|A|=10\), \(|B|=7\), \(|A\cap B|=4\), hãy tính \(|A\cup B|\), \(|A\setminus B|\) và \(|A\triangle B|\).

**Đáp án:** Lần lượt \(10+7-4=13\), \(10-4=6\) và \(10+7-2\times4=9\).

**Câu 7.** Kiểm tra \(A\subseteq B\) bằng biểu thức bit nào mà không cần tạo bitset kết quả?

**Đáp án:** Kiểm tra mọi từ của `A & ~B` bằng 0 (sau khi bảo đảm cùng miền và padding). Chỉ cần thấy một từ khác 0 là biết A không phải tập con của B.

**Câu 8.** Nếu chỉ cần số vị trí khác nhau giữa hai tập cờ, dùng phép nào?

**Đáp án:** Đếm bit 1 của `A ^ B` trên toàn bộ các từ. Đây là khoảng cách Hamming giữa hai dãy bit cùng độ dài.

**Câu 9.** Hai tập có giao và hợp đều rỗng. Có thể tính \(J(A,B)=|A\cap B|/|A\cup B|\) trực tiếp không?

**Đáp án:** Không, vì mẫu số bằng 0. Ứng dụng phải chọn quy ước xử lý hai tập rỗng trước khi tính tỷ lệ.

**Câu 10.** Tại sao việc lưu sẵn số bit 1 có thể khiến phép `count()` \(O(1)\) nhưng làm các thao tác cập nhật phức tạp hơn?

**Đáp án:** Phải duy trì số đếm chính xác mỗi lần set/clear hoặc kết hợp nhiều từ, dựa trên số bit **thực sự** đổi trạng thái. Nếu cập nhật sai, metadata mất nhất quán với dữ liệu.

## Ghi nhớ

- Trên cùng một miền chỉ số, **hợp = OR**, **giao = AND**, **hiệu \(A\setminus B\) = AND-NOT**, **hiệu đối xứng = XOR**. Phần bù = NOT **giới hạn trong miền \(n\) bit**.
- **Popcount** đếm số bit 1. Kết hợp phép toán theo từ với popcount giúp tính \(|A\cup B|\), \(|A\cap B|\), \(|A\setminus B|\) và khoảng cách Hamming mà **không cần tạo bitset kết quả**.
- Với \(q=\lceil n/w\rceil\) từ máy, hợp/giao/hiệu toàn bitset mất **\(O(q)\)** thời gian; tạo kết quả mới dùng \(O(q)\) bộ nhớ, còn đếm trực tiếp chỉ cần \(O(1)\) bộ nhớ phụ.
- Luôn bảo vệ **miền chỉ số, ánh xạ ID→bit, độ dài logic và các bit padding**. Không sử dụng phép NOT trên toàn độ rộng vật lý mà quên tail mask.
- Bitset phù hợp với tập hợp trên miền tương đối dày đặc và nhiều phép toán hàng loạt. Với miền cực thưa, **danh sách có thứ tự, hash set hoặc bitmap nén** có thể tiết kiệm tổng bộ nhớ và thời gian hơn.
