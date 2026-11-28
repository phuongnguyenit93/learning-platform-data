# Dãy bit và đóng gói nhiều giá trị Boolean trong một từ máy

Giả sử ứng dụng cần lưu trạng thái bật/tắt của một triệu tính năng, đánh dấu một triệu chỉ số đã thăm hoặc ghi nhận những ngày có sự kiện. Nếu mỗi trạng thái chiếm một byte riêng, phần dữ liệu tối thiểu là khoảng một triệu byte. Nhưng mỗi trạng thái chỉ cần hai giá trị **0 hoặc 1**, nên có thể đặt nhiều trạng thái trong các bit của một byte hoặc **từ máy (machine word)** và giảm dữ liệu xuống khoảng một phần tám.

Trong chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài này tập trung vào cách biểu diễn **dãy bit (bit sequence)** và **bitset/bitmap** bằng nhiều bit trong một đơn vị lưu trữ. Mục tiêu là hiểu bất biến của biểu diễn, tính toán vị trí bit, dùng phép toán bit chính xác, phân tích thời gian và bộ nhớ, rồi chọn giữa mảng Boolean và dãy bit đóng gói theo đặc điểm bài toán.

## 1. Dãy bit là một cấu trúc dữ liệu như thế nào?

Dãy bit độ dài \(n\) là một dãy có thứ tự:

\[
B = (b_0,b_1,\ldots,b_{n-1}), \quad b_i \in \{0,1\}.
\]

Mỗi phần tử logic là một **bit**, có thể diễn giải như giá trị Boolean:

- `0` tương ứng `false`, “chưa đánh dấu” hoặc “tắt”.
- `1` tương ứng `true`, “đã đánh dấu” hoặc “bật”.

Một bitset thường cung cấp các thao tác `get(i)`, `set(i)`, `clear(i)`, `flip(i)` và `count()`. Nếu hai bitset mô tả cùng một tập vị trí, có thể thực hiện phép `AND`, `OR`, `XOR` để kết hợp chúng.

Ví dụ dãy logic 13 bit, với các chỉ số `0`, `3`, `8` và `12` có giá trị 1:

```text
Chỉ số logic:  0  1  2  3  4  5  6  7  8  9 10 11 12
Giá trị bit:   1  0  0  1  0  0  0  0  1  0  0  0  1
               ^        ^              ^           ^
               Các bit được đánh dấu: {0, 3, 8, 12}
```

**Điểm quan trọng:** cách sắp các bit trong một hình minh họa không quyết định cách chúng được đặt trong byte hoặc từ máy. Phải quy định cụ thể **bit số 0** nằm ở phía nào của đơn vị lưu trữ.

### Dãy bit khác chuỗi ký tự `"0101"`

Chuỗi văn bản `"0101"` chứa bốn ký hiệu thuộc bảng chữ cái `{'0','1'}`. Trong UTF-8, nó thường chiếm **4 byte** vì mỗi chữ số ASCII chiếm một byte. Một dãy bit logic gồm bốn giá trị `0,1,0,1` có thể được đóng gói vào **nửa byte**, dù vùng lưu trữ vật lý thường cấp phát tối thiểu theo byte hoặc từ máy.

Vì thế, **dãy bit đóng gói** là biểu diễn nhị phân của các giá trị Boolean; nó không tự động giống biểu diễn văn bản của các chữ số `0` và `1`.

## 2. Đóng gói vào byte và từ máy

Một byte gồm 8 bit. Một từ máy có thể gồm 32 hoặc 64 bit trong những hệ thống thường gặp; ở đây lấy **\(w=64\)** làm ví dụ cho một phần tử `uint64_t`. Ký hiệu \(w\) là số bit mỗi đơn vị lưu trữ.

Nếu dùng `uint64_t words[]`, mỗi `words[j]` có thể lưu 64 giá trị Boolean. Tại vị trí logic \(i\):

\[
\text{wordIndex}=\left\lfloor\frac{i}{64}\right\rfloor,\qquad
\text{bitOffset}=i\bmod 64.
\]

Với từ máy rộng \(w\) bit bất kỳ:

\[
\text{wordIndex}=\left\lfloor\frac{i}{w}\right\rfloor,\qquad
\text{bitOffset}=i\bmod w.
\]

Giả sử quy ước **bit ở vị trí 0 của từ máy là bit thấp nhất (LSB)**. Một mask chỉ bật bit tại `bitOffset` là:

\[
\text{mask}=1\ll \text{bitOffset}.
\]

Phép dịch trái trên phải được thực hiện bằng **kiểu số nguyên không dấu đủ rộng**, và `0 ≤ bitOffset < w`. Dịch một giá trị có độ rộng \(w\) sang trái \(w\) vị trí là không hợp lệ trong nhiều ngôn ngữ/kiểu dữ liệu, chẳng hạn C và C++.

### Minh họa bằng 13 Boolean

Dãy có các bit `{0,3,8,12}` bằng 1. Khi đóng theo từng byte với bit 0 là LSB:

```text
Các vị trí logic       Byte 0       Byte 1
0..7                   00001001     (giá trị 0x09)
8..12 (cùng padding)                00010001 (giá trị 0x11)

Byte 0: bit 0 và bit 3 được bật  → 0x09
Byte 1: bit 0 và bit 4 được bật  → 0x11
```

Nội dung **logic** chỉ có 13 bit. Ba bit cao còn lại trong byte thứ hai là **bit đệm (padding)** và không thuộc dãy.

Nếu dùng một từ 64 bit, toàn bộ 13 Boolean có thể nằm trong một `uint64_t`:

```text
words[0] = (1 << 0) | (1 << 3) | (1 << 8) | (1 << 12)
         = 0x0000000000001109
```

Vì thế, 13 bit logic cần **2 byte** nếu đóng gói sát theo byte, nhưng một mảng `uint64_t` có ít nhất **8 byte dữ liệu** để chứa chúng. Chọn đơn vị lưu trữ lớn giúp khai thác phép toán từ máy, song có thể tăng dung lượng đệm ở những dãy rất ngắn.

## 3. Bất biến của một bitset đóng gói

Với bitset dài `n` bit được lưu trong mảng các từ rộng `w` bit, số từ cần cấp phát là:

\[
q=\left\lceil\frac{n}{w}\right\rceil.
\]

Nên tính bằng công thức không cần cộng `w-1` vào `n` để tránh tràn số nguyên khi `n` rất lớn:

```text
wordCount = n / w + (n % w != 0)
```

Các bất biến cơ bản:

1. **Phạm vi:** `0 ≤ i < n` với mọi thao tác đọc/ghi phần tử logic.
2. **Số từ:** vùng chứa đủ ít nhất `q` từ, mỗi từ `w` bit.
3. **Ánh xạ nhất quán:** bit logic `i` nằm trong từ `i // w`, tại bit `i % w` (theo quy ước LSB đã chọn).
4. **Độ dài logic tách khỏi sức chứa:** bitset có thể có `q × w` bit vật lý, nhưng chỉ `n` bit đầu là dữ liệu.
5. **Bit đệm:** chọn chính sách rõ ràng, thường buộc mọi bit ngoài `[0,n)` về 0 để phép `count`, so sánh và xuất dữ liệu không tính nhầm.
6. **Kiểu toán tử:** sử dụng số nguyên không dấu, dịch bit với số vị trí hợp lệ và kiểm tra chỉ số trước khi tính mask.

Ví dụ với `n=70`, `w=64`:

```text
word[0]: bit logic  0 ... 63  (đủ 64 bit)
word[1]: bit logic 64 ... 69  (6 bit dữ liệu)
         bit vật lý 6 ... 63 (58 bit đệm)
```

Mảng có 2 từ `uint64_t`, tức 128 bit vật lý = 16 byte dữ liệu. Tuy nhiên chỉ 70 bit đầu thuộc tập trạng thái. Không được hiểu 58 bit đệm là 58 Boolean bổ sung.

## 4. Các thao tác bit đơn lẻ

Giả sử `word` là từ không dấu và `mask = 1 << offset`.

| Thao tác | Biểu thức | Kết quả |
|---|---|---|
| Đọc bit | `(word & mask) != 0` | Trả về giá trị Boolean |
| Đặt bit thành 1 | `word \|= mask` | Bật bit tại vị trí cần chọn |
| Xóa bit về 0 | `word &= ~mask` | Tắt bit tại vị trí cần chọn |
| Đảo bit | `word ^= mask` | `0 → 1`, `1 → 0` |
| Đặt bit theo `value` | Nếu `value` thì OR; ngược lại AND với `~mask` | Đúng giá trị chỉ định |

Các toán tử `&`, `|`, `^`, `~` và `<<` làm việc theo bit của giá trị số nguyên. Ví dụ:

```text
word trước:  00001001
mask:        00000100   (chỉ bit số 2)
OR kết quả:  00001101   (bật bit số 2)

word trước:  00001101
~mask:       11111011   (trong mô hình 8 bit)
AND kết quả: 00001001   (xóa bit số 2)
```

**Cần nhớ:** toán tử `~` đảo tất cả các bit trong **độ rộng kiểu dữ liệu**, không chỉ các bit logic của bitset. Với từ cuối có padding, phải che lại các bit đệm nếu muốn giữ bất biến “padding bằng 0”.

### Vì sao một thao tác bit thường là `O(1)`?

Với `w` cố định theo kiểu máy và mảng từ cho phép truy cập ngẫu nhiên, để đọc/đổi bit thứ `i` cần:

1. Tính chỉ số từ `i // w`.
2. Tính độ lệch `i % w`.
3. Đọc một từ, thực hiện một hoặc vài phép toán bit rồi ghi lại (nếu cần).

Mỗi bước là hằng số trong mô hình RAM thông thường, nên `get`, `set`, `clear` và `flip` đều **`O(1)`** cho một bit đã được cấp phát và chỉ số hợp lệ. Thực tế hiệu năng còn chịu ảnh hưởng cache, khả năng đồng thời và cách đồng bộ các thao tác.

## 5. Ví dụ C: lưu 70 Boolean trong hai từ 64 bit

Đây là một ví dụ hoàn chỉnh với `uint64_t` và `UINT64_C(1)`. Kiểu không dấu tránh vấn đề dịch trái vào bit dấu của một số nguyên có dấu.

```c
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#define WORD_BITS 64u

static bool bit_get(
    const uint64_t *words, size_t bit_count, size_t index
) {
    if (index >= bit_count) return false;

    const size_t word_index = index / WORD_BITS;
    const unsigned offset = (unsigned)(index % WORD_BITS);
    return (words[word_index] & (UINT64_C(1) << offset)) != 0;
}

static bool bit_set(
    uint64_t *words, size_t bit_count, size_t index
) {
    if (index >= bit_count) return false;

    const size_t word_index = index / WORD_BITS;
    const unsigned offset = (unsigned)(index % WORD_BITS);
    words[word_index] |= UINT64_C(1) << offset;
    return true;
}

static bool bit_clear(
    uint64_t *words, size_t bit_count, size_t index
) {
    if (index >= bit_count) return false;

    const size_t word_index = index / WORD_BITS;
    const unsigned offset = (unsigned)(index % WORD_BITS);
    words[word_index] &= ~(UINT64_C(1) << offset);
    return true;
}

int main(void) {
    const size_t nbits = 70;
    uint64_t words[2] = {0, 0};

    bit_set(words, nbits, 0);
    bit_set(words, nbits, 63);
    bit_set(words, nbits, 64);
    bit_set(words, nbits, 69);

    printf("%d %d %d\n",
           (int)bit_get(words, nbits, 0),
           (int)bit_get(words, nbits, 64),
           (int)bit_get(words, nbits, 69));  // 1 1 1

    bit_clear(words, nbits, 63);
    printf("%d\n", (int)bit_get(words, nbits, 63)); // 0

    // Thao tác ngoài dãy bị từ chối, không dịch 70 bit.
    printf("%d\n", (int)bit_set(words, nbits, 70)); // 0
    return 0;
}
```

Điều kiện tiền đề là mảng `words` có đủ `ceil(nbits/64)` phần tử, đã khởi tạo, và được dùng đúng trong vòng đời của nó. Hàm `bit_get` trả `false` nếu chỉ số không hợp lệ để đơn giản hóa ví dụ; một API sản xuất có thể chọn **trả mã lỗi** hoặc **ném ngoại lệ** để phân biệt bit `0` với truy cập sai phạm vi.

Tại ranh giới:

- `i = 63` → `words[0]`, offset 63.
- `i = 64` → `words[1]`, offset 0.
- `i = 69` → `words[1]`, offset 5.
- `i = 70` → ngoài phạm vi logic, dù từ thứ hai còn nhiều bit vật lý trống.

Phân biệt **giới hạn logic** và **giới hạn cấp phát** là một bất biến cốt lõi của cấu trúc dữ liệu này.

## 6. Ví dụ Python: dùng `bytearray` để đóng gói bit

Một cách dễ quan sát là lưu các bit trong `bytearray`, mỗi byte chứa 8 Boolean và giữ độ dài logic `nbits` riêng.

```python
def make_bitset(nbits: int) -> bytearray:
    if nbits < 0:
        raise ValueError("nbits phải không âm")
    return bytearray((nbits + 7) // 8)

def set_bit(buf: bytearray, nbits: int, index: int) -> None:
    if not 0 <= index < nbits:
        raise IndexError("index ngoài dãy")
    buf[index // 8] |= 1 << (index % 8)

def get_bit(buf: bytearray, nbits: int, index: int) -> bool:
    if not 0 <= index < nbits:
        raise IndexError("index ngoài dãy")
    return bool(buf[index // 8] & (1 << (index % 8)))

def clear_bit(buf: bytearray, nbits: int, index: int) -> None:
    if not 0 <= index < nbits:
        raise IndexError("index ngoài dãy")
    buf[index // 8] &= ~(1 << (index % 8)) & 0xFF

nbits = 13
bits = make_bitset(nbits)
for index in (0, 3, 8, 12):
    set_bit(bits, nbits, index)

print(bits.hex())                 # 0911
print(get_bit(bits, nbits, 8))    # True
print(get_bit(bits, nbits, 9))    # False

clear_bit(bits, nbits, 3)
print(bits.hex())                 # 0111
```

`bytearray` có thể chứa giá trị 0–255 ở mỗi vị trí, vì thế việc cập nhật thông qua OR, AND và XOR được thực hiện trên một byte nguyên thay vì từng Boolean riêng.

**Lưu ý về tính đúng đắn:** `make_bitset` trả về bộ đệm có số byte tương ứng `nbits`. Các hàm đọc/ghi giả định `nbits` và `buf` vẫn phù hợp với nhau. Nếu bên ngoài thay kích thước `buf` mà không cập nhật `nbits`, bất biến có thể bị phá vỡ. Trong API thực tế, nên **đóng gói `buffer` và `bitLength` trong cùng một đối tượng** rồi quản lý chúng qua các phương thức.

### Đảo toàn bộ dãy và xử lý padding

Với 13 bit, byte thứ hai chỉ sử dụng 5 bit thấp. Nếu đảo mọi byte bằng XOR với `0xFF`, ba bit cao trong byte cuối sẽ thành 1 dù chúng không thuộc dữ liệu logic.

```python
def invert_all(buf: bytearray, nbits: int) -> None:
    for j in range(len(buf)):
        buf[j] ^= 0xFF

    used = nbits % 8
    if used != 0:
        buf[-1] &= (1 << used) - 1

bits = make_bitset(13)
set_bit(bits, 13, 0)
invert_all(bits, 13)

assert get_bit(bits, 13, 0) is False
assert get_bit(bits, 13, 12) is True
assert bits[-1] & 0b11100000 == 0  # padding vẫn bằng 0
```

Nếu độ dài chia hết cho 8, byte cuối không có padding và không cần mask. Nếu độ dài bằng 0, bộ đệm rỗng; đoạn `if used != 0` không chạy, tránh truy cập `buf[-1]` ngoài phạm vi.

## 7. Tính bộ nhớ thực tế

Giả sử cần lưu `n` Boolean.

### Lưu mỗi Boolean trong một byte

Trong **mô hình một byte cho một Boolean**, phần dữ liệu cần `n` byte. Một số ngôn ngữ và thư viện dùng biểu diễn lớn hơn hoặc thêm overhead; ví dụ một `list` Python chứa nhiều tham chiếu đến đối tượng Boolean nên tốn bộ nhớ vượt xa `n` byte. Vì vậy, `n` byte chỉ là **mốc so sánh**, không phải cam kết của mọi mảng Boolean.

### Đóng gói theo byte

Số byte dữ liệu cần:

\[
M_{\text{byte-packed}}=\left\lceil\frac{n}{8}\right\rceil.
\]

### Đóng gói theo từ 64 bit

Nếu lưu trong mảng `uint64_t`:

\[
M_{\text{word-packed}}=8\left\lceil\frac{n}{64}\right\rceil
\quad\text{byte}.
\]

Đây là dung lượng **dữ liệu của mảng từ**, chưa tính con trỏ, độ dài, bộ cấp phát, alignment hoặc metadata của đối tượng.

| Số Boolean \(n\) | Một byte/Boolean | Đóng gói byte | Đóng gói từ 64 bit |
|---:|---:|---:|---:|
| 13 | 13 B | 2 B | 8 B |
| 64 | 64 B | 8 B | 8 B |
| 70 | 70 B | 9 B | 16 B |
| 1.000 | 1.000 B | 125 B | 128 B |
| 1.000.000 | 1.000.000 B | 125.000 B | 125.000 B |

Ở các dãy lớn, phần padding cuối thường nhỏ so với tổng dữ liệu. Với một triệu cờ, dữ liệu được đóng gói cần **125.000 byte**, bằng một phần tám so với mốc một byte cho mỗi Boolean. Tỷ lệ này là lý do bitmap được dùng cho tập trạng thái lớn và tương đối dày đặc.

### Khi nào đóng gói có thể kém thuận lợi?

- Chỉ có vài Boolean: metadata của đối tượng và padding có thể lớn hơn phần tiết kiệm.
- Cần truy cập qua **con trỏ tới từng Boolean**: bit được đóng gói không có địa chỉ byte độc lập.
- Cập nhật đồng thời nhiều bit: các bit khác nhau có thể cùng nằm trong một từ, gây tranh chấp khi ghi.
- Phần lớn bit bằng 0 trong không gian chỉ số cực lớn: cấu trúc **sparse set**, hash set hoặc bitmap nén có thể phù hợp hơn cấp phát cả khoảng chỉ số.

Tức là đóng gói tối ưu **mật độ lưu trữ**, nhưng không đồng nghĩa luôn tối ưu mọi kiểu truy cập.

## 8. Phép toán trên nhiều bit một lúc

Ưu điểm khác của cách đóng gói là mỗi lệnh trên từ máy có thể xử lý nhiều Boolean đồng thời. Nếu hai bitset `A` và `B` có cùng độ dài logic và cùng quy ước bit, ta có thể thực hiện các phép toán trên từng từ:

| Phép toán tập hợp | Bitwise | Ý nghĩa |
|---|---|---|
| Giao `A ∩ B` | `A & B` | Vị trí bằng 1 ở cả hai |
| Hợp `A ∪ B` | `A \| B` | Vị trí bằng 1 ở ít nhất một |
| Hiệu đối xứng | `A ^ B` | Vị trí bằng 1 ở đúng một phía |
| Hiệu `A \ B` | `A & ~B` | Có trong `A` và không có trong `B` |
| Bù trên miền `[0,n)` | `~A` + mask padding | Đảo trong đúng `n` bit logic |

Ví dụ hai từ 8 bit:

```text
A:        00101101
B:        00011001
A & B:    00001001
A | B:    00111101
A ^ B:    00110100
```

Với bitset dài `n`, mảng các từ rộng `w` cần `q = ceil(n/w)` từ. Thực hiện AND/OR/XOR toàn bộ dãy mất **`O(q) = O(ceil(n/w))`** phép xử lý từ, thay vì một phép riêng cho từng Boolean.

Đây là **song song theo bit trong một từ**: một phép AND 64 bit xử lý đồng thời 64 cặp cờ logic. Nếu `w` được coi là hằng số máy, cả hai cách vẫn là `O(n)` theo ký hiệu tiệm cận, nhưng số phép lặp và lưu lượng bộ nhớ có thể thấp hơn đáng kể.

### Đếm số bit 1 (population count)

Phép `popcount` trả về số bit 1 trong một từ. Với mảng từ:

\[
\operatorname{count}(B)
=\sum_{j=0}^{q-1}\operatorname{popcount}(\text{words}[j]),
\]

với điều kiện bit padding đã bằng 0 hoặc đã được loại khỏi phép đếm.

CPU hiện đại có thể cung cấp lệnh đếm bit 1 trên từng từ; một số ngôn ngữ/thư viện cung cấp hàm tương ứng. Chi phí thường là **`O(q)`** khi mỗi lần `popcount` trên một từ rộng cố định được coi là `O(1)`. Nếu `popcount` được mô phỏng bằng vòng lặp từng bit, hằng số sẽ khác.

Trong Python, số nguyên có phương thức `bit_count()` ở các phiên bản hiện đại:

```python
word_a = 0b00101101
word_b = 0b00011001

print((word_a & word_b).bit_count())  # 2
print((word_a | word_b).bit_count())  # 5
print((word_a ^ word_b).bit_count())  # 3
```

Các tính toán này có ích trong đếm thành viên, phép giao tập, trạng thái đã thăm và nhiều thuật toán xử lý mặt nạ.

## 9. So sánh độ phức tạp

Đặt `n` là số bit logic, `w` là độ rộng từ máy, `q = ceil(n/w)`.

| Thao tác | Mảng Boolean một phần tử/giá trị | Bitset lưu theo từ |
|---|---|---|
| Đọc một giá trị `get(i)` | `O(1)` | `O(1)` |
| Gán một giá trị `set/clear(i)` | `O(1)` | `O(1)` |
| Đảo một giá trị `flip(i)` | `O(1)` | `O(1)` |
| Tìm/duyệt tất cả giá trị | `O(n)` | `O(q)` khi xử lý theo từ, cộng chi phí liệt kê từng bit cần xuất |
| Đếm bit 1 | `O(n)` nếu kiểm tra từng phần tử | `O(q)` với `popcount` theo từ |
| AND/OR hai tập cùng miền | `O(n)` nếu chạy từng Boolean | `O(q)` theo từ |
| Xóa cả dãy | `O(n)` nếu gán từng phần tử | `O(q)` để ghi 0 vào các từ |
| Dung lượng dữ liệu | `O(n)` phần tử Boolean | `O(q)` từ, tương đương `O(n)` bit |

Bảng sử dụng mô hình từ máy cố định. **`O(q)` không phải `O(1)` với toàn bộ bitset:** khi tăng độ dài `n`, số từ `q` vẫn tăng. Trường hợp cần **liệt kê toàn bộ vị trí có bit 1**, chi phí còn phụ thuộc số kết quả được xuất, ít nhất là `Ω(r)` với `r` vị trí được báo cáo.

Nếu bitset thay đổi kích thước động, phải cộng chi phí mở rộng mảng từ. Với chiến lược cấp phát tăng theo hệ số, thêm đơn vị lưu trữ ở cuối có thể có chi phí khấu hao tương tự dynamic array; nhưng việc mở rộng **miền bit** và việc **đặt một bit đã tồn tại** là hai kiểu thao tác khác nhau.

## 10. Những chi tiết dễ làm sai khi triển khai

### 10.1. Nhầm số thứ tự bit với giá trị bit

Một số người đọc chuỗi nhị phân `10000000` và cho rằng “bit 0 nằm ở bên trái”. Đó chỉ là cách viết chữ số nhị phân theo quy ước **MSB bên trái**. Nếu bit logic `0` được ánh xạ tới **LSB**, thì bật bit 0 của một byte cho kết quả `00000001`.

Quy tắc cần công bố rõ: `index 0 → LSB` hay `index 0 → MSB`. Cả hai đều có thể dùng nếu nhất quán.

### 10.2. Lẫn thứ tự byte (endianness) với thứ tự bit

Giá trị số nguyên 64 bit `0x0000000000001109` có cùng các bit mang giá trị 1 dù CPU lưu các byte theo little-endian hay big-endian. Tuy nhiên, thứ tự byte trong bộ nhớ **khác nhau** theo endianness.

- **Bit numbering:** quy ước bit logic `i` tương ứng bit nào trong một từ.
- **Byte order:** cách các byte của từ được sắp trong bộ nhớ khi mã hóa/ghi ra ngoài.

Không nên ghi thẳng vùng nhớ `uint64_t[]` thành tệp rồi mặc nhiên mong mọi hệ thống giải mã giống nhau. Định dạng lưu trữ cần chỉ rõ độ rộng từ, endianness, thứ tự bit, `bitLength` và chính sách padding, hoặc tuần tự hóa thành một dãy byte với quy ước thống nhất.

### 10.3. Dịch trái với số lượng bit bằng độ rộng từ

Trong C/C++, `UINT64_C(1) << 64` không hợp lệ vì độ dịch bằng độ rộng toán hạng. Luôn dùng `index % 64` trước khi dịch, đồng thời kiểm tra `index < nbits`. Không dùng `1 << 63` với một `int` 32 bit hoặc phép dịch có dấu có thể gây hành vi không mong đợi.

### 10.4. Phép NOT bật cả padding

Nếu dãy dài 70 bit lưu trong hai từ 64 bit, toán tử `~words[1]` đảo cả 58 bit padding. Với quy ước padding bằng 0, cần giữ **sáu bit thấp** của từ cuối.

Công thức mask cuối cho `r = n % w`:

\[
\text{validMask}=
\begin{cases}
2^w-1 & \text{nếu }r=0\text{ và từ cuối đầy},\\
2^r-1 & \text{nếu }1\le r<w.
\end{cases}
\]

Với `r=0`, không dịch giá trị `1` sang trái `w` lần để tạo mask. Với `n=0`, không có từ cuối cần thao tác.

### 10.5. Xem bit như một ô Boolean có thể lấy địa chỉ

Các bit nằm chung một byte/từ, nên không thể lấy con trỏ thông thường tới từng **bit độc lập** như lấy địa chỉ `bool` trong một mảng Boolean không đóng gói. Một số thư viện trả về **proxy reference** cho phép viết cú pháp giống tham chiếu nhưng thực chất phải đọc, sửa rồi ghi cả đơn vị lưu trữ.

Ví dụ `std::vector<bool>` trong C++ có biểu diễn/chuyên biệt hóa không giống `std::vector<T>` thông thường; các thao tác phần tử có thể trả proxy thay vì `bool&`. Khi cần con trỏ, iterator hay cách thao tác giống mảng đối tượng Boolean thật, cần đọc kỹ hợp đồng kiểu đó.

### 10.6. Hai luồng sửa hai bit khác nhau nhưng chung một từ

Sửa một bit bằng `word |= mask` thường gồm các bước **đọc từ → biến đổi → ghi lại từ**. Giả sử hai luồng cùng sửa hai bit khác nhau của một từ:

```text
Ban đầu: 00000000

Luồng A đọc 00000000, chuẩn bị bật bit 0 → 00000001
Luồng B đọc 00000000, chuẩn bị bật bit 1 → 00000010

A ghi 00000001
B ghi 00000010   → thay đổi của A bị mất
```

Đây là ví dụ **lost update**. Trong các ngôn ngữ có khái niệm data race như C/C++, ghi/đọc không đồng bộ trên cùng một từ còn có thể gây hành vi không xác định.

Nếu cần cập nhật đồng thời, phải dùng cơ chế phù hợp, ví dụ **atomic fetch-or/fetch-and/fetch-xor** trên từ dữ liệu hoặc khóa bảo vệ. Đổi lại, nhiều luồng cùng sửa bit trong một từ sẽ có thể tranh chấp cache line hoặc thao tác atomic, dù chúng sửa các vị trí bit khác nhau.

## 11. Khi nào chọn bitset, khi nào chọn cấu trúc khác?

| Nhu cầu | Cấu trúc đáng cân nhắc | Lý do |
|---|---|---|
| Nhiều cờ Boolean trên một miền chỉ số nhỏ hoặc dày đặc | **Bitset/bitmap** | Mật độ bộ nhớ cao, truy cập theo chỉ số nhanh |
| Kết hợp tập đánh dấu bằng giao/hợp/hiệu | **Bitset theo từ máy** | AND/OR/XOR xử lý nhiều vị trí mỗi lần |
| Cần lưu dấu “đã thăm” trong đồ thị với đỉnh đánh số liên tiếp | **Bitset** | Đánh dấu và kiểm tra mỗi đỉnh `O(1)` |
| Chỉ có vài phần tử được bật trong không gian chỉ số cực lớn | **Hash set/sparse bitmap** | Không cần cấp phát toàn miền |
| Tập số nguyên rất lớn với các cụm dày thưa xen kẽ | **Compressed bitmap** | Có thể tận dụng các dải hoặc container theo mật độ |
| Nhiều luồng thường xuyên sửa các cờ độc lập | **Atomic bitmap hoặc mảng Boolean phù hợp** | Cân nhắc tranh chấp từ/cache line và yêu cầu đồng bộ |
| Chỉ có ít cờ cấu hình cho một đối tượng | **Trường Boolean hoặc bit flags** | Ưu tiên giao diện rõ ràng khi bộ nhớ không là nút thắt |

### Tình huống: đánh dấu đỉnh đã thăm của đồ thị

Một thuật toán duyệt đồ thị có `V = 1.000.000` đỉnh được đánh số `0` đến `V-1` cần biết đỉnh nào đã thăm.

Nếu dùng mảng một byte cho mỗi đỉnh, phần dữ liệu là khoảng 1 MB. Với bitset, dữ liệu chỉ khoảng **125 KB**. Đối với mỗi đỉnh `u`:

```text
if not visited.get(u):
    visited.set(u)
    đưa u vào queue/stack
```

Vì `get` và `set` đều `O(1)`, độ phức tạp tổng quát của BFS/DFS **không đổi** bởi lựa chọn này, nhưng dung lượng bộ nhớ dành cho trạng thái đã thăm giảm đáng kể. Nếu đỉnh dùng mã định danh thưa, không nằm trong miền liên tục, cần thêm ánh xạ ID sang chỉ số hoặc cân nhắc hash set.

### Tình huống: quyền truy cập được mã hóa bằng một từ

Một ứng dụng nhỏ có 8 loại quyền. Có thể dùng một byte hoặc một từ để giữ cả 8 cờ:

```text
bit 0: đọc
bit 1: ghi
bit 2: xóa
bit 3: quản trị
...
```

Kiểm tra quyền ghi bằng phép AND với mask bit 1. Thêm quyền bằng OR; thu hồi quyền bằng AND với mask đảo. Với trường hợp ít quyền, một giá trị bitmask đơn lẻ có thể tiện hơn cấp phát mảng Boolean. Tuy nhiên, cần định nghĩa rõ ý nghĩa từng vị trí để tránh sử dụng “số ma thuật”.

## 12. Bài tập tự kiểm tra có đáp án

**Câu 1.** Một dãy dài 130 bit được lưu trong các từ `uint64_t`. Cần bao nhiêu từ và bao nhiêu byte dữ liệu? Có bao nhiêu bit đệm?

**Đáp án:** `ceil(130/64) = 3` từ = **24 byte** dữ liệu; có `3×64−130 = 62` bit đệm.

**Câu 2.** Với `index = 70`, bit này nằm trong từ 64 bit thứ mấy, ở vị trí nào trong từ (đếm từ 0)?

**Đáp án:** `70 // 64 = 1`, `70 % 64 = 6`; nằm ở `words[1]`, bit thứ 6.

**Câu 3.** Bitset 13 bit có các vị trí `0,3,8,12` bằng 1. Với quy ước bit 0 là LSB, hai byte dữ liệu là gì?

**Đáp án:** `0x09 0x11`. Byte thứ hai chỉ dùng 5 bit thấp; 3 bit cao là padding.

**Câu 4.** Vì sao `word &= ~(1 << i)` cần xem lại khi `i = 64` và `word` là một từ 64 bit?

**Đáp án:** Dịch 64 vị trí không hợp lệ trên kiểu 64 bit trong C/C++; cần tính `bitOffset = i % 64` và chọn đúng từ `i // 64`. Dùng kiểu không dấu đủ rộng cho mask.

**Câu 5.** Với hai bitset cùng độ dài, phép hợp và giao có thể thực hiện ra sao? Độ phức tạp nếu có `q` từ?

**Đáp án:** Hợp là OR từng từ, giao là AND từng từ; tổng `O(q)` thao tác từ, chưa tính cấp phát kết quả nếu tạo bitset mới.

**Câu 6.** Một bitset dài 70 bit được đảo toàn bộ bằng `~` trên hai từ 64 bit. Vì sao cần mask ở từ cuối?

**Đáp án:** `~` đảo cả 58 bit đệm trong từ thứ hai. Phải chỉ giữ 6 bit thấp hợp lệ, chẳng hạn mask `(1 << 6) − 1` trên từ 64 bit không dấu.

**Câu 7.** Vì sao hai luồng sửa hai bit khác nhau trong cùng một từ có thể làm mất cập nhật?

**Đáp án:** Thao tác `set` thông thường phải đọc, đổi rồi ghi **cả từ**. Hai luồng có thể đọc cùng giá trị cũ, sau đó mỗi bên ghi phiên bản bỏ qua thay đổi của bên kia. Cần atomic hoặc cơ chế đồng bộ phù hợp.

**Câu 8.** Nếu chỉ 20 vị trí được bật trên miền 10 tỷ chỉ số, có luôn nên cấp phát một bitset dày đặc không?

**Đáp án:** Không. Một bitset dày đặc cần khoảng **1,25 tỷ byte** dữ liệu cho 10 tỷ bit; hash set hoặc cấu trúc lưu tập thưa thường phù hợp hơn khi chỉ có 20 phần tử.

## Ghi nhớ

- **Dãy bit** là dãy Boolean logic; **bitset đóng gói** lưu nhiều Boolean trong mỗi byte hoặc từ máy.
- Với từ rộng `w`, bit logic `i` ánh xạ tới `wordIndex = i // w` và `bitOffset = i % w`. Bit số 0 nằm ở LSB hay MSB phải được quy định nhất quán.
- Bộ nhớ dữ liệu của bitset lưu theo từ là `w × ceil(n/w)` bit; lưu theo byte cần `ceil(n/8)` byte, chưa tính metadata. Số bit vật lý cuối có thể lớn hơn độ dài logic vì **padding**.
- `get`, `set`, `clear` và `flip` trên một bit hợp lệ thường `O(1)`. Phép AND/OR/XOR và đếm bit 1 toàn bộ dãy thường mất `O(ceil(n/w))` thao tác từ.
- Các lỗi cần tránh gồm **dịch quá độ rộng từ**, **tính cả bit đệm**, **nhầm thứ tự byte/thứ tự bit**, **nhầm chuỗi chữ số 0/1 với bitset**, và **cập nhật đồng thời các bit chung một từ mà thiếu đồng bộ**.
- Chọn bitset khi miền chỉ số tương đối dày đặc hoặc cần phép toán tập hợp nhanh. Với miền cực thưa, cần cân nhắc các cấu trúc tập hợp hoặc bitmap nén để tối ưu tổng bộ nhớ.
