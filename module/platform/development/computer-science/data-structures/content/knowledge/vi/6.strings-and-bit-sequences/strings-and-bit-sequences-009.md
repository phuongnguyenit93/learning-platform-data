# Đặt, xóa, kiểm tra và duyệt các bit đang bật

Giả sử một thuật toán duyệt đồ thị cần đánh dấu đỉnh đã thăm. Mỗi đỉnh chỉ có hai trạng thái: **chưa thăm** (0) hoặc **đã thăm** (1). Nếu các đỉnh được đánh số từ 0 đến \(n-1\), một **bitset** có thể lưu \(n\) trạng thái bằng các bit được đóng gói trong những từ máy. Điều quan trọng là thực hiện đúng các thao tác đặt, xóa, kiểm tra và **liệt kê những vị trí đang bật** mà không phải tạo hàng triệu đối tượng Boolean.

Bài này thuộc chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là nắm bất biến của cấu trúc dữ liệu, cách ánh xạ chỉ số logic vào bộ nhớ, các phép toán bit, độ phức tạp thời gian/bộ nhớ và tiêu chí lựa chọn bitset khi xây dựng các thuật toán dùng mảng, stack, queue, bảng băm, cây, heap hoặc đồ thị.

## 1. Mô hình dãy bit và quy ước đánh số

Một dãy bit có độ dài \(n\) được mô hình hóa bằng:

\[
B = (b_0,b_1,\ldots,b_{n-1}), \qquad b_i \in \{0,1\}.
\]

Ta chọn quy ước **chỉ số 0 là bit có trọng số thấp nhất (LSB)** của từ đầu tiên. Nếu mỗi từ có \(w\) bit, bit thứ \(i\) nằm tại:

\[
\operatorname{word}(i)=\left\lfloor\frac{i}{w}\right\rfloor,\qquad
\operatorname{offset}(i)=i\bmod w.
\]

Ví dụ với \(w=8\), bitset dài 13 bit và các vị trí bật là \(\{0,3,8,12\}\):

```text
Chỉ số logic:  0  1  2  3  4  5  6  7 | 8  9 10 11 12
Giá trị:       1  0  0  1  0  0  0  0 | 1  0  0  0  1

Byte 0 (bit 7 ... bit 0): 00001001 = 0x09
Byte 1 (bit 7 ... bit 0): 00010001 = 0x11
                          ^^^
                     bit đệm ở phía cao của byte cuối
```

Ba bit cao của byte cuối không thuộc dãy logic 13 bit. Nếu dùng một từ 64 bit, các bit bật tương ứng tạo giá trị `0x0000000000001109`.

**Phân biệt chỉ số logic với cách in nhị phân:** chuỗi `00001001` thường được in từ bit cao nhất bên trái đến bit thấp nhất bên phải; chỉ số logic 0 vẫn trỏ đến bit bên **phải** theo quy ước LSB của bài.

### Bất biến biểu diễn

Với `n` bit logic lưu trong các từ không dấu rộng `w` bit:

- Số từ cần dùng là \(q=\lceil n/w\rceil\).
- Mỗi chỉ số hợp lệ phải thỏa `0 ≤ i < n`.
- Từ thứ `i // w` phải tồn tại trước khi truy cập.
- Mỗi thao tác bit phải dùng offset `i % w` trong khoảng `[0,w)`.
- Các bit vật lý từ `n` trở đi trong từ cuối là **padding**. Một lựa chọn đơn giản là buộc chúng luôn bằng 0.
- Cấu trúc phải lưu `n` riêng vì số bit vật lý `q × w` có thể lớn hơn độ dài logic.

Có thể tính số từ bằng `n / w + (n % w != 0)` với phép chia nguyên để tránh nguy cơ tràn của biểu thức `(n + w - 1) / w` khi `n` là một số nguyên rất lớn.

## 2. Tạo mặt nạ cho một vị trí bit

Gọi `offset = i % w`. Mặt nạ (mask) bật đúng một bit tại `offset` là:

\[
M = 1 \ll \operatorname{offset}.
\]

Với từ 8 bit và `offset = 3`:

```text
       bit: 7 6 5 4 3 2 1 0
mask:       0 0 0 0 1 0 0 0  = 0x08
```

Trong C/C++, phải dùng **toán hạng kiểu không dấu đủ rộng** trước khi dịch. Với từ `uint64_t`, cách tạo mask an toàn cho vị trí hợp lệ là:

```c
uint64_t mask = UINT64_C(1) << (index % 64u);
```

Điều kiện tiền đề là `index < nbits` và mảng có đủ từ; phần dư luôn nhỏ hơn 64. Không được dịch `1` kiểu `int` 32 bit sang trái 63 vị trí, cũng không được dịch một toán hạng 64 bit sang trái 64 vị trí.

## 3. Đặt bit thành 1: `set(i)`

Để đặt bit mục tiêu thành 1 mà không đổi các bit khác, thực hiện **OR theo bit**:

\[
W \gets W \mathbin{\vert} M.
\]

Ví dụ:

```text
Từ ban đầu:  00100001
Mask bit 3:  00001000
OR:          00101001
```

Hàm ý tưởng:

```text
set(i):
    require 0 <= i < n
    j = i // w
    offset = i % w
    words[j] = words[j] | (1 << offset)
```

**Tính lũy đẳng (idempotent):** đặt cùng một bit nhiều lần vẫn cho kết quả như đặt một lần. Nếu bit đang là 1, `set(i)` không chuyển nó thành 0.

Trong bài toán duyệt đồ thị, thao tác này dùng để đánh dấu đỉnh `u` đã được xử lý hoặc đã được đưa vào queue/stack.

## 4. Xóa bit về 0: `clear(i)`

Muốn xóa đúng bit mục tiêu, tạo mask rồi đảo mask để có 0 tại vị trí đó và 1 ở các vị trí khác:

\[
W \gets W \mathbin{\&} \neg M.
\]

```text
Từ ban đầu:   00101001
Mask bit 3:   00001000
NOT mask:     11110111   (giả định độ rộng 8 bit)
AND:          00100001
```

Hàm ý tưởng:

```text
clear(i):
    require 0 <= i < n
    j = i // w
    offset = i % w
    words[j] = words[j] & ~(1 << offset)
```

`clear(i)` cũng **lũy đẳng**: xóa một bit đang là 0 không làm thay đổi các bit còn lại.

**Lưu ý về NOT:** phép `~` đảo các bit trong độ rộng của **kiểu số nguyên**, không chỉ trong \(n\) bit logic. Nếu áp dụng `~` trực tiếp lên cả từ cuối của bitset, các bit padding cũng có thể bị bật. Cần mask lại phần dữ liệu logic sau các phép biến đổi toàn từ khi bất biến yêu cầu padding bằng 0.

## 5. Kiểm tra bit: `test(i)` hoặc `get(i)`

Để biết bit mục tiêu có đang bật hay không, thực hiện AND với mask:

\[
\operatorname{test}(i) = ((W \mathbin{\&} M) \ne 0).
\]

```text
Từ dữ liệu:   00101001
Mask bit 3:   00001000
AND:          00001000  → khác 0 → true

Mask bit 2:   00000100
AND:          00000000  → bằng 0 → false
```

Trong mô hình mảng từ cho phép truy cập trực tiếp, `test(i)` đọc **một từ** và thực hiện vài phép toán hằng số; thời gian `O(1)` cho một bit tại chỉ số hợp lệ.

### Phân biệt “bit bằng 0” và “chỉ số sai”

Nếu `test(i)` trả về `false` cho cả hai tình huống “bit đang 0” và “`i` ngoài phạm vi”, người gọi không phân biệt được kết quả hợp lệ với lỗi. Một API có thể:

- Ném ngoại lệ khi chỉ số sai.
- Trả kết quả gồm trạng thái lỗi và giá trị bit.
- Chọn trả `false` cho chỉ số sai **nếu hợp đồng công bố rõ** và người gọi chấp nhận.

Trong tài liệu học thuật và API cần tính đúng đắn cao, nên kiểm tra `0 ≤ i < n` thay vì âm thầm đọc một bit padding.

## 6. Đảo bit: `flip(i)` và cập nhật theo giá trị mong muốn

Phép **XOR** với mask đảo đúng bit mục tiêu:

\[
W \gets W \mathbin{\oplus} M.
\]

```text
Từ trước:     00100001
Mask bit 3:   00001000
XOR:          00101001   (0 thành 1)

Từ trước:     00101001
Mask bit 3:   00001000
XOR:          00100001   (1 thành 0)
```

Khác với `set` và `clear`, `flip` **không lũy đẳng**: gọi hai lần liên tiếp trên cùng bit khôi phục trạng thái ban đầu. Vì vậy, nếu logic yêu cầu “đánh dấu đã thăm”, dùng `set` thay vì `flip`.

Để gán một bit theo một giá trị Boolean `value`, có thể gọi `set(i)` nếu `value == true`, ngược lại gọi `clear(i)`. Cách này rõ nghĩa hơn việc tự tạo biểu thức phức tạp có thể gây nhầm dấu hoặc độ rộng kiểu.

## 7. Triển khai C với từ máy 64 bit

Ví dụ sử dụng 70 bit logic trong **hai** từ `uint64_t`. Các hàm bên dưới kiểm tra giới hạn và chỉ tạo mask bằng kiểu không dấu 64 bit. Mọi thao tác `set`, `clear`, `test`, `flip` làm việc trên một bit.

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <inttypes.h>

#define BIT_COUNT 70u
#define WORD_BITS 64u
#define WORD_COUNT (BIT_COUNT / WORD_BITS + (BIT_COUNT % WORD_BITS != 0u))

typedef struct {
    uint64_t words[WORD_COUNT];
} BitSet;

static bool valid_index(size_t i) {
    return i < BIT_COUNT;
}

static uint64_t bit_mask(size_t i) {
    return UINT64_C(1) << (unsigned)(i % WORD_BITS);
}

static bool bit_set(BitSet *bits, size_t i) {
    if (!valid_index(i)) return false;
    bits->words[i / WORD_BITS] |= bit_mask(i);
    return true;
}

static bool bit_clear(BitSet *bits, size_t i) {
    if (!valid_index(i)) return false;
    bits->words[i / WORD_BITS] &= ~bit_mask(i);
    return true;
}

static bool bit_test(const BitSet *bits, size_t i, bool *value) {
    if (!valid_index(i) || value == NULL) return false;
    *value = (bits->words[i / WORD_BITS] & bit_mask(i)) != 0;
    return true;
}

static bool bit_flip(BitSet *bits, size_t i) {
    if (!valid_index(i)) return false;
    bits->words[i / WORD_BITS] ^= bit_mask(i);
    return true;
}

int main(void) {
    BitSet bits = {{0}};
    bool value = false;

    bit_set(&bits, 0);
    bit_set(&bits, 5);
    bit_set(&bits, 63);
    bit_set(&bits, 64);
    bit_set(&bits, 69);

    bit_test(&bits, 64, &value);
    printf("bit 64 = %d\n", (int)value); // 1

    bit_clear(&bits, 63);
    bit_flip(&bits, 5);  // bit 5: 1 -> 0
    bit_test(&bits, 5, &value);
    printf("bit 5 = %d\n", (int)value); // 0

    printf("word0 = %016" PRIx64 "\n", bits.words[0]);
    printf("word1 = %016" PRIx64 "\n", bits.words[1]);
    // word0 chứa duy nhất bit 0 đang bật
    // word1 chứa các bit offset 0 và 5 đang bật

    printf("invalid = %d\n", (int)bit_set(&bits, 70)); // 0
    return 0;
}
```

Trong ví dụ, `bit_set`, `bit_clear` và `bit_flip` trả `true` khi **chỉ số hợp lệ và thao tác đã thực hiện**, không phải “bit vừa chuyển trạng thái”. Hàm `bit_test` dùng tham số đầu ra `value` để phân biệt giá trị bit với kết quả kiểm tra tính hợp lệ.

Các hàm giả định con trỏ `bits` là con trỏ hợp lệ; nếu nhận dữ liệu từ bên ngoài, API thực tế cần bổ sung kiểm tra con trỏ hoặc thiết kế kiểu sở hữu đảm bảo tiền điều kiện đó.

## 8. Duyệt toàn bộ bit so với chỉ liệt kê bit đang bật

Có hai yêu cầu khác nhau:

1. **Duyệt mọi vị trí từ 0 đến `n-1`**, kiểm tra mỗi vị trí là 0 hay 1.
2. **Chỉ xuất các vị trí có bit bằng 1** theo thứ tự tăng dần.

Cách trực tiếp nhất để liệt kê bit bật:

```text
for i from 0 to n-1:
    if test(i):
        emit(i)
```

Với `test(i)` là `O(1)`, chi phí là **`O(n)`** phép kiểm tra, ngay cả khi chỉ có vài bit đang bật. Nếu cần xử lý mọi vị trí, đây là cách rõ ràng và hợp lý. Nhưng khi cần liệt kê **chỉ các bit 1**, ta có thể tận dụng phép toán trên cả từ máy.

Gọi:

- `w`: số bit mỗi từ.
- `q = ceil(n / w)`: số từ.
- `r`: số bit đang bật trong toàn bộ dãy.

Mục tiêu là quét từng từ, **bỏ qua từ bằng 0**, và xử lý từng bit 1 mà không kiểm tra từng vị trí 0.

## 9. Mẹo `x & (x - 1)`: xóa bit 1 thấp nhất

Với số nguyên không dấu khác 0, biểu thức:

\[
x \gets x\ \&\ (x-1)
\]

**xóa đúng bit 1 thấp nhất** trong `x`, đồng thời giữ nguyên các bit 1 cao hơn.

Ví dụ `x = 0b00101100`:

```text
x:           00101100
x - 1:       00101011
x & (x - 1): 00101000
```

Bit 1 thấp nhất của `x` nằm tại vị trí 2 và đã bị xóa. Lặp lại thao tác:

```text
00101100  →  00101000  →  00100000  →  00000000
   3 bit 1      2 bit 1      1 bit 1      0 bit 1
```

Sau đúng **`popcount(x)` lần** (số bit đang bật ban đầu), giá trị trở về 0. Kỹ thuật này thường được gọi là **thuật toán Brian Kernighan** khi dùng để đếm bit 1.

```c
unsigned popcount_loop(uint64_t x) {
    unsigned count = 0;
    while (x != 0) {
        x &= x - UINT64_C(1);
        ++count;
    }
    return count;
}
```

Hàm trên mất số vòng lặp bằng số bit 1 trong từ. Với từ cố định 64 bit, số vòng không vượt 64; xét theo `r_word` bit đang bật trong một từ, số lần lặp là **`O(r_word)`**.

**Lưu ý:** khi `x == 0`, công thức trừ 1 không có ích để xóa bit thấp nhất. Vòng lặp phải kiểm tra `x != 0` trước. Trong biểu thức số nguyên không dấu của C/C++, `x - 1` tại 0 có phép quấn vòng theo modulo, nhưng không nên gọi nó như một phép xóa bit hợp lệ.

## 10. Cách tìm vị trí bit 1 thấp nhất

Biểu thức `x & (x - 1)` xóa bit 1 thấp nhất, nhưng để **xuất chỉ số** của bit đó, ta còn phải xác định vị trí của nó.

Có hai cách thường gặp.

### 10.1. Đếm số bit 0 ở cuối (count trailing zeros, CTZ)

Với `x != 0`, **CTZ** là số bit 0 liên tiếp tính từ phía bit thấp nhất cho đến bit 1 đầu tiên:

```text
x = 00101000
              ^^^
           3 bit 0 ở cuối

ctz(x) = 3
```

Nhiều CPU có lệnh tương ứng và một số compiler/thư viện cung cấp hàm `countr_zero` / `trailing_zeros`. Khi dùng primitive hỗ trợ trên từ máy cố định, việc tìm vị trí bit thấp nhất thường có chi phí **`O(1)`**.

Nếu không có primitive, có thể dùng cách đếm tuần tự trên một từ không dấu:

```c
static unsigned trailing_zeros_nonzero(uint64_t x) {
    unsigned result = 0;
    // Tiền điều kiện: x != 0
    while ((x & UINT64_C(1)) == 0) {
        x >>= 1;
        ++result;
    }
    return result;
}
```

Trên một từ 64 bit, hàm duyệt tối đa 63 bit 0 trước bit 1 đầu tiên nên bị chặn bởi một hằng số. Khi phân tích theo độ rộng từ `w` thay đổi, cách đếm tuần tự này là **`O(w)`** trong trường hợp xấu; vì thế cần nêu rõ giả định khi nói toàn bộ phép liệt kê chỉ mất `O(q+r)`.

**Không gọi CTZ trên giá trị 0** nếu API chưa xác định rõ kết quả. Ví dụ một số builtin của compiler C có hành vi không xác định khi nhận 0; vòng lặp cần kiểm tra từ khác 0 trước.

### 10.2. Tách bit 1 thấp nhất thành một mask

Với số nguyên không dấu khác 0, có thể lấy mask chỉ chứa bit 1 thấp nhất:

\[
\operatorname{lowbit}(x)=x\ \&\ (-x).
\]

Ví dụ:

```text
x:         00101100
lowbit(x): 00000100
```

Trong C/C++, nên hiểu `-x` trên **số nguyên không dấu** theo quy tắc modulo; trong Python, số nguyên có độ dài tùy ý và biểu thức `x & -x` cũng hoạt động với `x` dương.

Khi đã có `lowbit` (lũy thừa của 2), ta có thể lấy vị trí bằng `bit_length(lowbit) - 1` trong Python, hoặc dùng CTZ trên từ máy. Sau đó dùng `x ^= lowbit` để loại bit đã xuất, hoặc `x &= x - 1` để xóa bit thấp nhất.

## 11. Duyệt chỉ các bit đang bật theo từng từ

Ý tưởng là đi qua các từ lưu trữ, bỏ qua từ toàn 0 và lặp trên các bit 1:

```text
for each wordIndex j in 0 .. q-1:
    x = words[j]  // bản sao cục bộ, không sửa dữ liệu gốc
    x = x & validMask(j)  // bỏ padding nếu cần

    while x != 0:
        offset = ctz(x)
        emit(j * w + offset)
        x = x & (x - 1)
```

Vì luôn lấy **bit 1 thấp nhất trước**, và các từ được duyệt từ thấp đến cao, chỉ số xuất ra là **thứ tự tăng dần**. Đây là cách rất hữu ích để duyệt các đỉnh đã thăm, các quyền đã bật, các cột được chọn hoặc những chỉ số thỏa điều kiện.

### Ví dụ từng bước

Với dãy 13 bit có các vị trí bật \(\{0,3,8,12\}\) và đóng gói trong một từ:

```text
x = 0x1109 = 0001 0001 0000 1001 (bit 12,8,3,0)

Bước 1: ctz(x) = 0   → xuất 0    → x &= x-1 = 0x1108
Bước 2: ctz(x) = 3   → xuất 3    → x &= x-1 = 0x1100
Bước 3: ctz(x) = 8   → xuất 8    → x &= x-1 = 0x1000
Bước 4: ctz(x) = 12  → xuất 12   → x &= x-1 = 0
Kết quả: [0, 3, 8, 12]
```

Vòng lặp không phải thử lần lượt 13 bit; nó chạy **4 lượt**, bằng đúng số bit 1 trong từ. Tuy nhiên, việc tìm các từ không rỗng vẫn phải quét qua các từ trong mảng nếu không có chỉ mục phụ.

### Chi phí

Với `q` từ máy và `r` bit 1:

- Duyệt toàn bộ dãy bằng `test(i)` từng bit: **`O(n)`** thao tác.
- Quét từng từ, CTZ bằng một primitive hằng số và xóa mỗi bit 1: **`O(q+r)`** thao tác từ.
- Nếu CTZ được hiện thực bằng quét tuần tự tối đa `w` bit, chi phí tổng quát là **`O(q+rw)`** trong mô hình cho phép `w` thay đổi. Với `w=64` cố định, ta vẫn có `O(q+r)` theo số từ và bit xuất.
- Nếu sử dụng bitmap nén hoặc chỉ mục các từ khác 0, có thể tránh duyệt mọi từ zero; nhưng cấu trúc và chi phí cập nhật phức tạp hơn.

Chi phí **`Ω(r)` là không tránh khỏi** khi yêu cầu xuất chính xác `r` vị trí bật, vì phải tạo đủ `r` kết quả.

## 12. Ví dụ C: in các vị trí đang bật theo thứ tự tăng dần

Mã sau minh họa duyệt bitset 70 bit trong hai từ 64 bit, **không thay đổi mảng nguồn**. Hàm đếm zero đơn giản giữ ví dụ độc lập với các compiler builtin.

```c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define WORD_BITS 64u
#define BIT_COUNT 70u
#define WORD_COUNT (BIT_COUNT / WORD_BITS + (BIT_COUNT % WORD_BITS != 0u))

static unsigned trailing_zeros_nonzero(uint64_t value) {
    unsigned count = 0;
    // Chỉ gọi khi value != 0.
    while ((value & UINT64_C(1)) == 0) {
        value >>= 1;
        ++count;
    }
    return count;
}

static void print_set_bits(const uint64_t words[WORD_COUNT]) {
    for (size_t j = 0; j < WORD_COUNT; ++j) {
        uint64_t value = words[j];

        // Chỉ giữ 6 bit hợp lệ trong từ cuối khi BIT_COUNT = 70.
        if (j + 1 == WORD_COUNT && BIT_COUNT % WORD_BITS != 0u) {
            unsigned used = BIT_COUNT % WORD_BITS;
            value &= (UINT64_C(1) << used) - UINT64_C(1);
        }

        while (value != 0) {
            unsigned bit_offset = trailing_zeros_nonzero(value);
            size_t logical_index = j * WORD_BITS + bit_offset;
            printf("%zu ", logical_index);
            value &= value - UINT64_C(1);
        }
    }
    putchar('\n');
}

int main(void) {
    uint64_t words[WORD_COUNT] = {0};

    // Bật các vị trí logic 0, 5, 63, 64, 69.
    words[0] = (UINT64_C(1) << 0)
             | (UINT64_C(1) << 5)
             | (UINT64_C(1) << 63);
    words[1] = (UINT64_C(1) << 0) | (UINT64_C(1) << 5);

    print_set_bits(words); // 0 5 63 64 69
    return 0;
}
```

**Các tình huống biên được xử lý:**

- Khi một từ bằng 0, vòng `while` không chạy; CTZ không nhận giá trị 0.
- Khi từ cuối chỉ có 6 bit dữ liệu, mask loại bỏ 58 bit padding.
- Bit 63 của từ thứ nhất và bit 64 của dãy được phân biệt chính xác.
- Lấy `value` là bản sao cục bộ, nên `print_set_bits` không xóa bit trong `words`.

Mã cố định `BIT_COUNT=70`. Nếu triển khai cấu trúc có độ dài động, phải tính số từ, kiểm tra giới hạn, cấp phát đúng số phần tử và tránh dịch bằng đúng `WORD_BITS` khi tạo tail mask. Với từ cuối đầy (\(n\bmod w=0\)), không cần mask phần dư; với dãy rỗng (\(n=0\)), không được đọc từ cuối vì không có từ nào.

## 13. Ví dụ Python: đối tượng bitset với iterator chỉ duyệt bit bật

Một cách triển khai thực hành là dùng danh sách các **từ số nguyên 64 bit**, mỗi từ chứa tối đa 64 Boolean. API giữ `_words` bên trong, chỉ cho phép sửa qua những phương thức đã kiểm tra giới hạn:

```python
class BitSet:
    WORD_BITS = 64

    def __init__(self, nbits: int):
        if nbits < 0:
            raise ValueError("Độ dài phải không âm")
        self.nbits = nbits
        self._words = [0] * (nbits // 64 + (nbits % 64 != 0))

    def _location(self, index: int) -> tuple[int, int]:
        if not 0 <= index < self.nbits:
            raise IndexError("Chỉ số ngoài bitset")
        return divmod(index, 64)

    def set(self, index: int) -> None:
        j, offset = self._location(index)
        self._words[j] |= 1 << offset

    def clear(self, index: int) -> None:
        j, offset = self._location(index)
        self._words[j] &= ~(1 << offset)

    def test(self, index: int) -> bool:
        j, offset = self._location(index)
        return bool(self._words[j] & (1 << offset))

    def flip(self, index: int) -> None:
        j, offset = self._location(index)
        self._words[j] ^= 1 << offset

    def iter_set_bits(self):
        for word_index, word in enumerate(self._words):
            # Duyệt bản sao cục bộ; iterator không xóa dữ liệu gốc.
            while word:
                lowbit = word & -word
                offset = lowbit.bit_length() - 1
                yield word_index * 64 + offset
                word ^= lowbit

    def count(self) -> int:
        # int.bit_count() có từ Python 3.10.
        return sum(word.bit_count() for word in self._words)


bits = BitSet(70)
for i in (0, 5, 63, 64, 69):
    bits.set(i)

print(bits.test(64))           # True
print(bits.count())            # 5
print(list(bits.iter_set_bits())) # [0, 5, 63, 64, 69]

bits.clear(63)
bits.flip(5)
print(list(bits.iter_set_bits())) # [0, 64, 69]
print(bits.count())              # 3
```

Vì `_words` không được công bố để sửa trực tiếp, các phương thức trên chỉ bật các vị trí nằm trong độ dài logic, nên padding ban đầu bằng 0 vẫn được giữ là 0. Nếu một phiên bản API cho phép can thiệp vào mảng từ, thao tác đảo nguyên từ hoặc nạp dữ liệu nhị phân, cần bổ sung kiểm tra/mask padding để duy trì bất biến đó.

**Độ phức tạp trong Python:** `iter_set_bits` duyệt danh sách từ và xóa dần bit 1 trong một số nguyên. Biểu thức `word & -word`, `bit_length()` và XOR trong Python làm việc trên số nguyên độ dài tùy ý; tại đây mỗi từ luôn có **nhiều nhất 64 bit**, nên các phép tính được chặn bởi kích thước cố định. Với một số nguyên Python chứa **hàng triệu bit** thay cho danh sách từ 64 bit, không thể mặc nhiên coi từng phép toán số nguyên lớn là `O(1)`.

### Trường hợp không có bit nào bật

```python
empty = BitSet(130)
print(list(empty.iter_set_bits()))  # []
print(empty.count())               # 0
```

Một iterator hợp lệ phải trả kết quả rỗng và không gọi phép tìm bit 1 thấp nhất trên từ bằng 0.

## 14. Duyệt một bitset mà không xóa trạng thái

Trong giả mã và các ví dụ trên, vòng lặp đặt `x = words[j]` rồi thay đổi **biến cục bộ** `x`; dữ liệu gốc vẫn giữ nguyên. Nếu vô tình thực hiện `words[j] &= words[j] - 1` để duyệt, chương trình sẽ **xóa các dấu đánh dấu** ngay trong cấu trúc.

Tính chất này có thể là mong muốn trong một số thuật toán tiêu thụ công việc (ví dụ lấy rồi xóa phần tử cần xử lý), nhưng phải là quyết định API rõ ràng. Với hàm `enumerate_set_bits()` thông thường, người gọi kỳ vọng việc duyệt **không sửa bitset**.

Nếu nhiều luồng sửa bitset trong khi đang duyệt, iterator cũng cần quy định rõ tính nhất quán:

- **Snapshot:** chụp trạng thái trước khi duyệt; cần chi phí sao chép hoặc cơ chế phiên bản.
- **Khóa bảo vệ:** cố định trạng thái trong đoạn duyệt; đổi lại thời gian chờ của luồng ghi.
- **Iterator quan sát thay đổi:** kết quả có thể phụ thuộc thời điểm, cần hợp đồng rõ ràng.

Không mặc định một phép OR/AND/XOR đọc-sửa-ghi từ máy thông thường là an toàn khi nhiều luồng cùng thay đổi các bit trong **cùng một từ**. Trường hợp cần đồng thời có thể sử dụng atomic fetch-or/fetch-and/fetch-xor hoặc khóa, với những đánh đổi về hiệu năng.

## 15. Quản lý bit đệm và xử lý thao tác trên toàn dãy

Một dãy 70 bit dùng hai từ 64 bit có tổng 128 bit vật lý, trong đó **58 bit cuối** là padding.

```text
words[0]: 64 bit dữ liệu (vị trí logic 0..63)
words[1]:  6 bit dữ liệu (vị trí logic 64..69)
           58 bit padding (không thuộc dãy)
```

Với độ dài `n` và phần dư `r = n % w`, mask của từ cuối (nếu từ cuối không đầy) là:

\[
\operatorname{validMask} = (1 \ll r)-1,\qquad 1\le r<w.
\]

Trong C/C++ với từ 64 bit:

```c
// Chỉ dùng khi 1 <= used && used < 64:
uint64_t valid_mask = (UINT64_C(1) << used) - UINT64_C(1);
last_word &= valid_mask;
```

Nếu `r == 0`, từ cuối (khi có tồn tại) sử dụng đủ `w` bit; **không** tạo mask bằng cách dịch `1` trái `w` vị trí. Nếu `n == 0`, không có từ cuối.

Khi gọi `set/clear/flip` với `i < n`, padding không thay đổi. Nhưng nếu thực hiện `NOT` toàn từ, giải tuần tự từ tệp, nhập mask có độ dài lớn hơn hoặc kết hợp bitset có kích thước không tương thích, cần khôi phục bất biến padding trước khi `count()` hoặc liệt kê các bit 1.

### Tại sao padding ảnh hưởng đến việc duyệt?

Nếu từ cuối có một bit padding bằng 1 và iterator không mask, nó sẽ xuất một vị trí `i ≥ n`, mặc dù đó không phải phần tử logic. Trong đồ thị, có thể dẫn đến truy cập đỉnh không tồn tại; trong kiểm tra quyền, có thể nhận diện một quyền không hợp lệ.

Bài toán **liệt kê chính xác** đòi hỏi vừa dùng thuật toán duyệt bit 1, vừa bảo đảm **miền chỉ số** và **bất biến bộ nhớ** đúng.

## 16. Ứng dụng: duyệt đồ thị, tập vị trí và bộ lọc

### 16.1. Đánh dấu các đỉnh đã thăm

Với đồ thị có các đỉnh đánh số `0..V-1`, bitset `visited` thường hỗ trợ:

```text
if not visited.test(v):
    visited.set(v)
    queue.push(v)
```

`test` và `set` là `O(1)`, nên dùng bitset thay cho mảng Boolean không làm thay đổi bậc độ phức tạp `O(V+E)` của BFS trên danh sách kề. Nó có thể giảm bộ nhớ lưu trạng thái đã thăm từ mốc một byte mỗi đỉnh xuống khoảng một bit mỗi đỉnh (chưa tính metadata và padding).

Nếu cần duyệt **tất cả đỉnh đã thăm** sau BFS, iterator theo từ có thể xuất trực tiếp những chỉ số bật. Nhưng nếu đồ thị có không gian định danh cực lớn và chỉ vài đỉnh tồn tại, một `hash set` có thể thích hợp hơn cấp phát bitset dày đặc.

### 16.2. Tập chỉ số đang hoạt động

Một hệ thống quản lý các mục có số thứ tự liên tục có thể dùng bitset `active`. Đặt bit khi mục được kích hoạt, xóa khi hủy và liệt kê các chỉ số bật để tạo báo cáo. Phép giao hai bitset bằng AND cho biết những mục hoạt động trong **cả hai** tập; phép hợp bằng OR cho biết những mục hoạt động trong **ít nhất một** tập.

Khi hai bitset cùng miền dài `n`, phép AND/OR toàn bộ mất `O(q)` thao tác từ, với `q = ceil(n/w)`. Khi cần liệt kê kết quả, cộng chi phí `O(r)` cho `r` bit được xuất dưới giả định CTZ hằng số.

### 16.3. Lập lịch bằng mặt nạ nhỏ

Nếu có 7 ngày trong tuần, một từ 8 bit đủ lưu trạng thái bảy ngày:

```text
bit 0: Thứ Hai
bit 1: Thứ Ba
...
bit 6: Chủ nhật
bit 7: padding
```

Thêm lịch vào Thứ Hai bằng `set(0)`; bỏ lịch Thứ Sáu bằng `clear(4)`; kiểm tra Chủ nhật bằng `test(6)`. Liệt kê ngày có lịch bằng kỹ thuật bit thấp nhất, tối đa bảy kết quả. Với miền rất nhỏ, một mặt nạ đơn là lựa chọn đơn giản, dễ truyền qua giao diện số nguyên và ít cần cấu trúc cấp phát riêng.

## 17. Khi nào nên duyệt theo bit, theo từ hoặc dùng cấu trúc thưa?

| Nhu cầu | Cách nên cân nhắc | Lý do |
|---|---|---|
| Phải kiểm tra **mọi vị trí** từ 0 đến \(n-1\) | Duyệt từng bit | Rõ ràng, `O(n)` và không bỏ qua vị trí 0 |
| Chỉ cần **những bit đang bật** | Quét từ và dùng CTZ + `x&(x-1)` | Bỏ qua các bit 0 trong từ, chi phí `O(q+r)` theo mô hình từ máy |
| Chủ yếu cần **đếm** bit 1 | `popcount` theo từ | Không cần tạo danh sách chỉ số |
| Miền chỉ số **rất lớn và cực thưa** | Hash set, danh sách có thứ tự hoặc bitmap nén | Tránh quét/cấp phát số lượng lớn từ zero |
| Nhiều phép **giao, hợp, XOR** hai tập lớn | Bitset đóng gói theo từ | Phép toán song song trên nhiều bit |
| Cần tìm bit 1 kế tiếp nhiều lần | CTZ theo từ và có thể thêm chỉ mục các từ khác 0 | Giảm lặp quét nếu mẫu truy vấn phù hợp |
| Nhiều luồng ghi đồng thời | Atomic bitset hoặc cơ chế đồng bộ phù hợp | Tránh mất cập nhật trong cùng từ |

Bitset đặc biệt tốt khi **miền giá trị được đánh số dày đặc**, số bit tương đối lớn và phải thực hiện nhiều phép toán tập hợp. Một sparse set có thể tốt hơn khi \(r\ll n\) và chi phí duy trì mảng \(q\) từ lớn so với số bit thực sự bật.

## 18. Lỗi thường gặp

1. **Dùng `1 << i` thay vì `1 << (i % w)`** khi lưu nhiều từ. Nếu `i ≥ w`, phép dịch không hợp lệ hoặc không tạo bit mong muốn.
2. **Không kiểm tra `i < n`** trước khi truy cập. Bit padding vẫn nằm trong vùng vật lý nhưng không phải bit logic.
3. **Nhầm phép set với flip.** `set` luôn đưa bit về 1; `flip` thay đổi 0 thành 1 và 1 thành 0.
4. **Gọi CTZ khi từ bằng 0.** Một số API không định nghĩa trường hợp này; phải có điều kiện `while (x != 0)`.
5. **Thao tác `~` trên từ cuối rồi quên mask padding.** Duyệt có thể xuất các vị trí vượt `n-1`.
6. **Xóa trực tiếp các bit của cấu trúc trong hàm chỉ có nhiệm vụ duyệt.** Nếu không tạo bản sao cục bộ, dữ liệu gốc bị thay đổi.
7. **Tuyên bố duyệt bit bật là `O(r)` cho cả một bitset nhiều từ.** Nếu phải quét mọi từ, chi phí còn có `O(q)`.
8. **Quên chi phí của số nguyên tùy ý.** Các phép toán trên một số nguyên Python hàng triệu bit không tương đương một lệnh CPU trên `uint64_t`.
9. **Ghi đồng thời vào hai bit chung một từ mà không đồng bộ.** Phép đọc-sửa-ghi có thể mất cập nhật hoặc gây data race, tùy ngôn ngữ.
10. **Nhầm thứ tự bit khi tuần tự hóa ra byte.** Phải công bố mapping LSB/MSB và thứ tự byte để đọc lại dữ liệu trên hệ thống khác.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Bit logic `i = 131` nằm trong từ 64 bit nào và ở vị trí offset nào?

**Đáp án:** `131 // 64 = 2`, `131 % 64 = 3`. Nó nằm trong `words[2]` tại bit offset 3.

**Câu 2.** Từ có giá trị `0b00101100`. Lặp `x &= x - 1` bao nhiêu lần để `x` trở thành 0?

**Đáp án:** Ba lần vì từ ban đầu có ba bit 1.

**Câu 3.** Cho `x = 0x1109`. Dùng CTZ và `x &= x - 1` để liệt kê các chỉ số bit bật theo thứ tự tăng dần.

**Đáp án:** Các chỉ số là **`0, 3, 8, 12`**.

**Câu 4.** Vì sao `set(i)` và `clear(i)` lũy đẳng, còn `flip(i)` thì không?

**Đáp án:** Set luôn đưa bit về 1 và clear luôn đưa về 0, nên thao tác lặp lại không đổi kết quả. Flip đổi trạng thái, lặp hai lần trả về trạng thái ban đầu.

**Câu 5.** Bitset dài 70 bit lưu trong hai từ 64 bit. Có bao nhiêu bit padding và điều gì xảy ra nếu `NOT` từ cuối mà không mask?

**Đáp án:** Có `128 - 70 = 58` bit padding. Chúng có thể bị bật và bị hiểu nhầm thành phần tử logic khi đếm hoặc duyệt.

**Câu 6.** Một bitset dài `n` bit có `q` từ và `r` bit bật. Thuật toán quét từng từ, dùng CTZ hằng số và xóa bit thấp nhất có chi phí nào?

**Đáp án:** **`O(q+r)`** thao tác từ. Nếu phải quét `q` từ, không thể bỏ thành phần `q` chỉ vì `r` nhỏ.

**Câu 7.** Khi muốn biết có bao nhiêu bit đang bật nhưng không cần vị trí, có nhất thiết tạo danh sách mọi chỉ số bật không?

**Đáp án:** Không. Có thể dùng `popcount` trên mỗi từ rồi cộng, thường mất `O(q)` với primitive đếm bit của từ máy.

**Câu 8.** Hai luồng cùng đặt hai bit khác nhau trong một từ bằng OR thông thường. Vì sao cần cân nhắc atomic?

**Đáp án:** OR thông thường có thể là chuỗi thao tác đọc-sửa-ghi không nguyên tử. Hai luồng có thể đọc cùng giá trị cũ và ghi chồng lên nhau, làm mất một lần đặt bit.

**Câu 9.** Nếu \(n=10^9\) và chỉ \(r=100\) bit bật, có nên mặc định dùng một bitset dày đặc để chỉ liệt kê 100 chỉ số ấy?

**Đáp án:** Không. Bitset dày đặc cần khoảng 125 MB dữ liệu và phép quét phải xét nhiều từ zero; một tập thưa hoặc bitmap nén có thể phù hợp hơn khi chỉ có 100 vị trí.

## Ghi nhớ

- Với từ rộng `w`, bit logic `i` nằm ở `words[i // w]`, offset `i % w`; tạo mask trên **kiểu không dấu đủ rộng** và kiểm tra `0 ≤ i < n`.
- **Set:** `word |= mask`; **clear:** `word &= ~mask`; **test:** `(word & mask) != 0`; **flip:** `word ^= mask`. Các thao tác một bit thường là **`O(1)`** trong mô hình mảng từ máy.
- Với từ `x != 0`, `x & (x - 1)` xóa **bit 1 thấp nhất**. Kết hợp với **CTZ** để tìm vị trí và liệt kê các bit đang bật theo thứ tự tăng.
- Quét các từ và xuất các bit 1 mất **`O(q+r)`** nếu CTZ trên từ cố định là `O(1)`, với `q=ceil(n/w)` và `r` số bit bật; duyệt mọi vị trí bằng test riêng mất **`O(n)`**.
- Khi duyệt, thay đổi **bản sao cục bộ của từ** để không phá trạng thái gốc. Giữ **padding bằng 0**, tránh gọi CTZ trên 0 và bảo vệ thao tác chung một từ nếu có truy cập đồng thời.
- Bitset phù hợp với miền chỉ số dày đặc và các phép toán trên tập; khi miền cực thưa, xem xét tập băm hoặc bitmap nén để tiết kiệm bộ nhớ và công quét.
