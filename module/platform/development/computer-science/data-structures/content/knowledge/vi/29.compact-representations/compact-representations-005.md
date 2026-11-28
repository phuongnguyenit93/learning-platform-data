# Dùng chỉ mục phụ để tăng tốc rank và select

Một vector bit dài một triệu phần tử có thể lưu phần dữ liệu cờ bằng khoảng **125.000 byte** nếu đóng gói đúng một bit cho mỗi phần tử. Nhưng để trả lời câu hỏi “có bao nhiêu bit 1 trước vị trí 700.000?” hoặc “bit 1 thứ 250.000 nằm ở đâu?”, cách quét lần lượt vẫn có thể phải đi qua hàng chục nghìn từ máy.

**Chỉ mục phụ (auxiliary index/directory)** giải quyết nút thắt đó bằng cách lưu một lượng nhỏ thông tin đã tính trước: số bit 1 ở đầu các đoạn, số bit trong từng từ máy, hoặc vị trí của một số bit được lấy mẫu. Truy vấn không cần đọc lại toàn bộ vector; nó đi thẳng tới vùng liên quan, rồi chỉ xử lý vài bit hoặc vài từ máy.

Chỉ mục phụ không thay thế bản thân vector bit. Nó là cấu trúc được **dựng từ dữ liệu gốc**, và phải luôn nhất quán với dữ liệu ấy. Vì vậy bài toán thiết kế không chỉ là “làm sao nhanh nhất”, mà gồm bốn câu hỏi:

1. Lưu **thông tin gì** để trả lời đúng?
2. Tổ chức theo **vị trí bit** hay theo **thứ tự bit 1/0**?
3. Bộ nhớ phụ và thời gian dựng chỉ mục là bao nhiêu?
4. Nếu vector thay đổi, chỉ mục được cập nhật hay phải xây lại?

Đây là bài **“Dùng chỉ mục phụ để tăng tốc rank và select”**, thuộc chương **Biểu diễn gọn** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu chung của học phần là hiểu bất biến, thao tác và chi phí thời gian/bộ nhớ của cấu trúc dữ liệu để lựa chọn biểu diễn phù hợp. Ta sẽ thiết kế chỉ mục từ dễ hiểu đến tinh gọn, cài đặt Python và C++17, rồi phân tích tính đúng đắn, mật độ dữ liệu, truy vấn tĩnh/động và giới hạn thông tin.

## 1. Kết quả học tập và mô hình bài toán

Sau bài, bạn có thể:

1. Xác định chính xác `rank1`, `rank0`, `select1` và `select0` theo một quy ước chỉ số.
2. Giải thích vì sao chỉ lưu bitset và `popcount` chưa đủ cho `rank` toàn cục nhanh.
3. Xây directory **superblock + word**, tính rank bằng vài phép cộng và một `popcount`.
4. Dùng **prefix theo superblock** để tìm vùng chứa bit thứ k, rồi chọn bit trong một word.
5. Xây chỉ mục select kiểu **lấy mẫu vị trí mỗi q bit 1/0**, giới hạn phạm vi tìm kiếm.
6. Phân biệt `O(1)` rank, `O(log S)` select và mục tiêu `O(1)` select của cấu trúc succinct nâng cao.
7. Tính chính xác overhead của payload, directory rank, mẫu select, padding và metadata.
8. Xử lý trường hợp vector rỗng, superblock không có bit 1, bit padding ở từ cuối và chỉ số vượt miền.
9. Giải thích tại sao directory tĩnh không thể cập nhật bit miễn phí.
10. Chọn phương án giữa quét, prefix đầy đủ, directory hai tầng, chỉ mục chọn bit, Fenwick và cấu trúc chuyên dụng.

**Mô hình:** vector tĩnh `B[0..n-1]` gồm n bit, dùng từ không dấu 64 bit. Các đoạn và tiền tố là **nửa mở**; bit đầu được đánh số 0.

## 2. Quy ước rank và select phải được chốt trước

Đặt:

\[
B=(b_0,b_1,\ldots,b_{n-1}),\quad b_i\in\{0,1\}.
\]

Với `0≤i≤n`:

\[
\boxed{\operatorname{rank}_1(i)=\sum_{j=0}^{i-1}b_j}
\]

là số bit 1 trong tiền tố **`[0,i)`**. Không tính bit tại vị trí i.

Số bit 0 trong cùng tiền tố:

\[
\boxed{\operatorname{rank}_0(i)=i-\operatorname{rank}_1(i).}
\]

Đặt `m_1=rank1(n)` và `m_0=n-m_1`.

Với `1≤k≤m_1`:

\[
\boxed{\operatorname{select}_1(k)=\text{vị trí bit 1 thứ k}}
\]

trong đó **k đếm từ 1 nhưng vị trí trả về đếm từ 0**. `select0(k)` được định nghĩa tương tự.

### Hai phương trình kiểm tra quan trọng

Nếu `p=select1(k)` thì:

\[
rank1(p)=k-1,\qquad rank1(p+1)=k.
\]

Nếu `q=select0(k)` thì:

\[
rank0(q)=k-1,\qquad rank0(q+1)=k.
\]

Các hệ thức này tạo thành **kiểm thử bất biến** rất hữu ích. Nếu code của bạn trả `select1(1)=0` trong một vector mà `B[0]=0`, giao diện đã sai, dù hàm không gây exception.

### Trường hợp không tồn tại

- `rank1(0)=rank0(0)=0`.
- `rank1(n)=m_1`, `rank0(n)=m_0`.
- `select1(0)` và `select0(0)` không hợp lệ.
- `select1(m_1+1)` hoặc `select0(m_0+1)` không hợp lệ.
- Một vector toàn 0 không có `select1(1)`.
- Một vector toàn 1 không có `select0(1)`.

Trong mã của bài, select không hợp lệ **ném lỗi**, chứ không trả số 0 hoặc vị trí n mà dễ bị hiểu nhầm.

## 3. Ví dụ xuyên suốt: 24 bit và hai trục tọa độ

Xét:

```text
Chỉ số:  0  1  2  3  4  5  6  7  8  9 10 11
B[i]:    1  0  1  1  0  0  1  0  1  0  0  1

Chỉ số: 12 13 14 15 16 17 18 19 20 21 22 23
B[i]:    1  0  1  0  0  0  1  0  1  1  0  1
```

Các bit 1 ở:

```text
P1 = [0, 2, 3, 6, 8, 11, 12, 14, 18, 20, 21, 23]
```

Các bit 0 ở:

```text
P0 = [1, 4, 5, 7, 9, 10, 13, 15, 16, 17, 19, 22]
```

Có 12 bit 1 và 12 bit 0.

| Truy vấn | Kết quả | Giải thích |
|---|---:|---|
| `rank1(0)` | 0 | Tiền tố rỗng |
| `rank1(4)` | 3 | Bit 1 ở 0, 2, 3 |
| `rank1(12)` | 6 | Đếm vị trí 0..11 |
| `rank1(16)` | 8 | Có 8 bit 1 ở 0..15 |
| `rank1(22)` | 11 | Có 11 bit 1 trước 22 |
| `rank1(24)` | 12 | Toàn bộ vector |
| `select1(1)` | 0 | Bit 1 đầu |
| `select1(5)` | 8 | Bit 1 thứ năm |
| `select1(9)` | 18 | Bit 1 thứ chín |
| `select1(12)` | 23 | Bit 1 cuối |
| `select0(5)` | 9 | Bit 0 thứ năm |
| `select0(12)` | 22 | Bit 0 cuối |

**Hai trục khác nhau:** đối số của `rank` là **vị trí trong vector**, còn đối số của `select` là **số thứ tự của một bit 1/0**. Chỉ mục rank và chỉ mục select vì thế có những cách lấy mẫu tự nhiên khác nhau.

## 4. Nếu không có chỉ mục phụ thì sao?

Bit vector có thể lưu gọn bằng các từ 64 bit:

```text
words[0]: các bit 0..63
words[1]: các bit 64..127
words[2]: các bit 128..191
...
```

Truy cập một bit chỉ cần:

```text
w = i // 64
offset = i % 64
B[i] = (words[w] >> offset) & 1
```

nhưng `rank1(i)` theo kiểu quét phải:

1. Đếm bit 1 ở mọi word **hoàn chỉnh trước i**.
2. Đếm những bit thấp trong word chứa i.

Với n=1.000.000, số word là `⌈n/64⌉=15.625`. Một truy vấn rank gần cuối có thể cần đọc hàng chục nghìn word, dù mỗi `popcount` riêng lẻ rất nhanh.

`select1(k)` kiểu quét từ đầu cũng phải đi qua word theo thứ tự và trừ popcount cho đến khi gặp word chứa bit thứ k.

### Ba chiến lược ban đầu

| Cách làm | Rank | Select | Bộ nhớ phụ |
|---|---|---|---|
| Quét bit từng cái | `O(n)` worst-case | `O(n)` | `O(1)` |
| Quét word 64 bit | `O(n/64)` word | `O(n/64)` word | `O(1)` |
| Lưu prefix tại **mọi vị trí** | `O(1)` | `O(log n)` qua tìm kiếm | `Θ(n log n)` bit nếu mỗi tổng có `Θ(log n)` bit |

Lưu prefix ở mọi vị trí làm rank nhanh, nhưng chỉ mục có thể lớn hơn rất nhiều so với n bit gốc. Giải pháp hiệu quả hơn là **lưu các mốc thưa và cộng phần nhỏ còn lại**.

## 5. Hai phép tính phần cứng giúp thiết kế chỉ mục

### Popcount

`popcount(x)` trả số bit 1 trong số nguyên không dấu x:

```python
assert (0b10110100).bit_count() == 4
```

Nếu x là word 64 bit, popcount có thể dùng chỉ thị CPU hoặc thuật toán trên tối đa 64 bit. Với mô hình word-RAM có word kích thước cố định, ta thường tính chi phí mỗi popcount là `O(1)`.

### Mask tiền tố trong một word

Muốn đếm r bit thấp của một word, với `0≤r≤64`:

\[
\operatorname{popcount}\left(word\;\&\;((1\ll r)-1)\right).
\]

Ở C/C++, dịch `1ULL<<64` là không hợp lệ. Do đó chỉ dùng trực tiếp mask này khi `r<64` và xử lý r=64 bằng `popcount(word)`. Trong các hàm rank của bài, `r=i\bmod64` luôn nằm trong `0..63`.

Ví dụ:

```text
word = 10110100₂
r = 5
mask = 00011111₂
word & mask = 00010100₂
popcount = 2
```

Giữa hai mốc đã lưu, chỉ cần đọc **một word** và popcount phần phù hợp. Đây là ý tưởng chính của directory rank.

## 6. Thiết kế directory rank hai tầng

Ta chọn:

- **Word**: 64 bit.
- **Superblock**: 8 word liên tiếp, tức **512 bit**.

Đặt:

\[
M=\left\lceil\frac{n}{64}\right\rceil
\quad\text{và}\quad
S=\left\lceil\frac{n}{512}\right\rceil.
\]

Các mảng phụ:

1. `super_ones[s]`: tổng bit 1 trước superblock s.
2. `within[w]`: số bit 1 từ **đầu superblock chứa word w** đến trước word w.
3. `words[w]`: 64 bit dữ liệu thực tế.

Mảng `super_ones` có `S+1` mốc, bao gồm mốc cuối vector. Mảng `within` có M mục.

### Hình dung

```text
Superblock 0 (512 bit)               Superblock 1
+----+----+----+----+----+----+----+----+----+----+...
| w0 | w1 | w2 | w3 | w4 | w5 | w6 | w7 | w8 | w9 |
+----+----+----+----+----+----+----+----+----+----+

super_ones:
  0             tổng popcount(w0..w7)     ...

within:
  w0=0, w1=pc(w0), ..., w7=pc(w0..w6)
  w8=0, w9=pc(w8), ...
```

**Bất biến quan trọng:**

\[
super\_ones[\lfloor w/8\rfloor]+within[w]
\]

bằng số bit 1 **trước word w** của toàn vector.

Nếu n không chia hết cho 64, các bit padding trong word cuối phải được giữ bằng 0 khi dựng payload. Nếu cần đếm bit 0, chỉ các vị trí nhỏ hơn n mới là dữ liệu hợp lệ.

## 7. Công thức rank với directory

Với `0≤i<n`, tính:

```text
w = i // 64          chỉ số word
s = w // 8           chỉ số superblock
r = i % 64           số bit đầu word cần đếm
```

Kết quả:

\[
\boxed{
rank1(i)
=super\_ones[s]
+within[w]
+popcount\left(words[w]\;\&\;((1\ll r)-1)\right).
}
\]

Ba số đếm đúng ba miền **không chồng lấn**:

- Các superblock hoàn chỉnh trước s.
- Các word hoàn chỉnh trước w nhưng nằm trong s.
- Phần `[64w,i)` của word w.

Khi `i=n`, trả trực tiếp `total_ones` đã tính lúc dựng directory. Cách đó cũng tránh đọc `words[M]` ngoài biên khi n là bội của 64.

`rank0(i)` không cần mảng prefix riêng:

\[
\boxed{rank0(i)=i-rank1(i).}
\]

### Vì sao rank đạt O(1)?

Sau khi xây chỉ mục, mỗi truy vấn chỉ cần vài phép toán chỉ số, hai lần đọc prefix, một word, một mask và một popcount:

\[
T_{rank}=O(1)
\]

trên mô hình word-RAM cố định với popcount từ 64 bit là O(1).

Đây là **chặn thời gian truy vấn**, không nói việc dựng index là miễn phí: dựng lần đầu phải đọc dữ liệu, thường `O(n)` nếu đầu vào là n Boolean riêng lẻ.

## 8. Mô phỏng directory trên mười word

Giả sử mười word có số bit 1:

```text
word:         0  1  2  3  4  5  6  7 | 8  9
popcount:     3  1  0  2  5  0  0  1 | 0  4
             \------- super 0 ------/ \super 1/
```

Superblock 0 có `3+1+0+2+5+0+0+1=12` bit 1; superblock 1 có 4 bit 1.

```text
super_ones = [0, 12, 16]
within     = [0,3,4,4,6,11,11,11,0,0]
```

Hỏi `rank1(9*64+10)`, tức i=586. Giả sử 10 bit thấp của word 9 có hai bit 1:

```text
w = 9
s = 1
r = 10

rank1(586) = super_ones[1] + within[9] + 2
           = 12 + 0 + 2
           = 14.
```

Không quét tám word đầu. Nếu nhầm `within[9]` là tổng toàn vector thay vì trong superblock, sẽ dễ **cộng lặp** các bit trước superblock.

### Superblock rỗng

Nếu word 8 không có bit 1 thì `within[9]=0`. Việc có một hoặc nhiều superblock **không chứa bit 1** tạo ra các mốc `super_ones` liên tiếp bằng nhau. Điều này đặc biệt quan trọng khi xây select.

## 9. Số bit phụ của directory rank

Mỗi superblock có 512 bit và tối đa 8 word.

`within[w]` đếm số bit 1 trước word w **trong cùng superblock**. Giá trị cao nhất tại đầu word cuối của superblock đầy đủ là 448, cần **9 bit** nếu đóng gói tối thiểu. Triển khai đơn giản thường dùng `uint16_t`, tức 16 bit/mục.

`super_ones[s]` lưu giá trị từ 0 đến n; có thể dùng `⌈log₂(n+1)⌉` bit/mục hoặc chọn `uint32_t/uint64_t` phù hợp miền n.

### Ví dụ n = 1.000.000

```text
M = ceil(1000000/64)  = 15625 word
S = ceil(1000000/512) = 1954 superblock

Word payload = 15625 * 8 = 125000 byte
within       = 15625 * 2 =  31250 byte (uint16)
super_ones   =  1955 * 4 =   7820 byte (uint32)
---------------------------------------------
Tổng vùng mảng             = 164070 byte
```

Directory rank dùng:

\[
31.250+7.820=39.070\text{ byte},
\]

tương đương khoảng **31,3% payload**. Ví dụ giả định n vừa trong miền `uint32_t` và dùng mảng kiểu cố định; overhead `vector`, allocator, đối tượng và chỉ mục select **chưa tính**.

### Vì sao không gọi đây là n+o(n)?

Với block **cố định 64 bit** và superblock **cố định 512 bit**, số mục within tỷ lệ n, mỗi mục dùng số bit hằng, nên overhead là **Θ(n) bit**, không phải `o(n)`.

Directory này vẫn là một lựa chọn rất thực tế: đơn giản, truy vấn nhanh và nhỏ hơn nhiều so với prefix cho từng vị trí. Nhưng để tuyên bố **succinct** theo nghĩa tiệm cận `n+o(n)` phải có lập luận khác.

## 10. Chiến lược select A: tìm kiếm nhị phân trên rank

Do `rank1(i)` không giảm, muốn tìm bit 1 thứ k có thể dùng binary search trên vị trí p.

Ta tìm p nhỏ nhất thỏa:

\[
rank1(p+1)\ge k.
\]

Giả mã:

```text
select1(k):
    assert 1 <= k <= total_ones

    lo = 0
    hi = n-1
    while lo < hi:
        mid = lo + (hi-lo)//2
        if rank1(mid+1) >= k:
            hi = mid
        else:
            lo = mid+1
    return lo
```

Vì rank O(1), select kiểu này có:

\[
O(\log(n+1))
\]

thời gian worst-case và không cần thêm chỉ mục select.

### Tính đúng

`rank1(p+1)` là hàm không giảm theo p. Trước khi đi qua bit 1 thứ k, giá trị nhỏ hơn k; tại đúng vị trí bit 1 thứ k nó đạt k. Vì tìm **p đầu tiên**, đáp án đúng là vị trí bit 1 thứ k, không phải một vị trí 0 nằm phía sau nó.

### Khi nào đủ tốt?

- Rank rất thường xuyên; select ít.
- Hàng triệu bit nhưng truy vấn select không quá lớn.
- Ưu tiên cài đặt đơn giản, test dễ.
- Không muốn tăng bộ nhớ cho directory select.

**Không được kết luận select O(1)** chỉ vì rank O(1). Binary search vẫn có số vòng tỷ lệ log n.

## 11. Chiến lược select B: tìm superblock theo tổng đếm

Thay vì tìm trên mọi vị trí, ta dùng chính `super_ones`.

Nếu bit 1 thứ k thuộc superblock s, ta có:

\[
super\_ones[s]<k\le super\_ones[s+1].
\]

Khi có superblock rỗng, các tổng có thể bằng nhau; cần chọn **đúng mốc**.

Có thể dùng:

```python
from bisect import bisect_left

s = bisect_left(super_ones, k) - 1
```

với điều kiện `1≤k≤total_ones`.

### Vì sao trừ 1?

Ví dụ:

```text
super_ones = [0, 4, 4, 4, 9]
```

Superblock 0 có bốn bit 1, superblock 1 và 2 rỗng, superblock 3 có năm bit 1.

- `k=4`: `bisect_left(...,4)` trả mốc 1 → s=0.
- `k=5`: trả mốc 4 → s=3.

Nếu chọn sai một mốc có cùng tổng 4, thuật toán có thể đi vào superblock **không hề có bit 1**.

### Chọn trong superblock

Sau khi biết s:

1. `remaining=k-super_ones[s]` là thứ tự bit 1 cần tìm **bên trong superblock**.
2. Duyệt tối đa **8 word**.
3. Với mỗi word, nếu `remaining>popcount(word)` thì trừ số bit 1 và bỏ qua.
4. Khi gặp word chứa bit cần tìm, chọn bit 1 thứ `remaining` trong word.

Vì số word mỗi superblock cố định là 8, phần quét cục bộ là **hằng số** theo n. Binary search mốc superblock tốn:

\[
\boxed{O(\log(S+1)+1),\quad S=\lceil n/512\rceil.}
\]

Chi phí này có thể tốt hơn tìm theo mọi vị trí, nhưng vẫn **không phải O(1) tiệm cận** do số superblock tăng theo n.

## 12. Chọn bit 1 thứ k trong một word

Giả sử biết word 64 bit chứa bit cần tìm, và chỉ số k cục bộ hợp lệ.

Một kỹ thuật là **xóa `k−1` bit 1 thấp nhất**:

```text
repeat k-1 times:
    word = word & (word - 1)
```

Sau đó vị trí bit 1 thấp nhất còn lại chính là bit thứ k của word ban đầu.

Trong Python:

```python
def select_in_word(word: int, k: int) -> int:
    if word < 0 or word >= (1 << 64):
        raise ValueError("word không phải uint64")
    if not 1 <= k <= word.bit_count():
        raise IndexError("k ngoài miền")

    for _ in range(k - 1):
        word &= word - 1

    lowest = word & -word
    return lowest.bit_length() - 1


assert select_in_word(0b10110100, 1) == 2
assert select_in_word(0b10110100, 2) == 4
assert select_in_word(0b10110100, 3) == 5
assert select_in_word(0b10110100, 4) == 7
```

Một word có tối đa 64 bit 1, nên số vòng tối đa 63: **O(1)** trong mô hình word cố định. Ở hệ thống cần hiệu năng cao, có thể dùng lệnh bit-select chuyên dụng hoặc thuật toán chọn bit nhanh hơn.

### Vì sao không lấy `k` là vị trí bit?

Một word có thể là `10000001₂`. Bit 1 thứ hai ở vị trí 7, không phải vị trí 1. Select cần **đếm số lần xuất hiện**, không chuyển trực tiếp số thứ tự thành chỉ số bit.

## 13. Select0: không được đếm bit đệm

Với select0, ta cần đếm các bit 0 **hợp lệ** của từng vùng.

Tổng bit 0 trước superblock s:

\[
\boxed{
super\_zeros[s]
=\min(n,512s)-super\_ones[s].
}
\]

Đây là công thức đúng vì trong tiền tố có `\min(n,512s)` vị trí logic, và `super_ones[s]` bit 1.

Ở word w, số bit hợp lệ là:

\[
valid(w)=\min(64,n-64w).
\]

Bit 0 hợp lệ của word được biểu diễn bằng:

\[
zeroWord=(\sim words[w])\;\&\;((1\ll valid)-1).
\]

Với C++ phải xử lý riêng `valid=64` để tránh `1ULL<<64`.

### Ví dụ n=65

```text
B[0..63] = 0
B[64]    = 1
```

Vùng word có 128 bit vật lý, nhưng chỉ 65 bit logic:

- Có **64 bit 0 hợp lệ**.
- Có **1 bit 1 hợp lệ**.
- Có **63 bit 0 đệm** ở word cuối.

`select0(64)=63`. `select0(65)` không tồn tại.

Nếu dùng `~words[1]` mà không mask, 63 bit 0 đệm sẽ bị tính thành dữ liệu và làm `select0` trả sai.

### Hai cách làm select0

1. Tìm nhị phân trên `rank0(i)=i-rank1(i)`, O(log n) và rất dễ kiểm tra.
2. Dựng mốc `super_zeros`, tìm superblock rồi chọn bit 0 **đã mask** bên trong word, O(log S+1).

Bài sẽ minh họa cách 2 để thấy **khả năng tái sử dụng directory cho cả hai loại bit**.

## 14. Chiến lược select C: lấy mẫu theo thứ tự bit

Một hướng khác là lưu **vị trí** của một số bit 1 được chọn theo thứ tự.

Chọn bước lấy mẫu q, ví dụ q=4. Ta lưu:

```text
Vị trí của bit 1 thứ: 1, 5, 9, 13, ...
Vị trí của bit 0 thứ: 1, 5, 9, 13, ...
```

Với vector 24 bit ở đầu:

```text
Bit 1:
  thứ tự:    1 2 3 4 5 6 7 8 9 10 11 12
  vị trí:    0 2 3 6 8 11 12 14 18 20 21 23

sample_ones (q=4):
  thứ tự 1 → vị trí 0
  thứ tự 5 → vị trí 8
  thứ tự 9 → vị trí 18

sample_ones = [0, 8, 18]
```

Tương tự:

```text
sample_zeros = [1, 9, 16]
  (bit 0 thứ 1, thứ 5, thứ 9)
```

**Mục đích:** truy vấn `select1(k)` biết ngay một vị trí mốc **không đứng sau** đáp án. Nếu có mẫu kế tiếp, ta còn biết giới hạn phải của vùng chứa đáp án.

### Công thức mốc

Với k bắt đầu từ 1:

\[
a=\left\lfloor\frac{k-1}{q}\right\rfloor
\]

là chỉ số mẫu. Mẫu a tương ứng với bit 1 có thứ tự:

\[
r=aq+1.
\]

Do đó:

- `sample_ones[a]` là vị trí của bit thứ r.
- Nếu `k=r`, trả ngay mẫu.
- Nếu `k>r`, tìm trong đoạn sau mẫu a và trước mẫu a+1, nếu có.

## 15. Tìm kiếm trong khoảng giữa hai mẫu

Giả sử muốn `select1(7)` trên vector 24 bit với q=4.

Mẫu trước:

```text
a = floor((7-1)/4) = 1
r = 1*4+1 = 5
sample_ones[1] = 8
```

Mẫu tiếp theo là bit thứ 9 ở vị trí 18. Vậy bit thứ 7 phải nằm **trong khoảng vị trí [9,17]**. Ta có thể binary search `rank1(p+1)≥7` chỉ trong vùng này.

Kết quả `select1(7)=12`.

### Độ phức tạp chính xác

Nếu hai mốc bao một khoảng gồm g vị trí, tìm kiếm trên rank tốn:

\[
O(\log(g+1)).
\]

**Không được tuyên bố g≤q.** Khoảng có q lần xuất hiện bit 1 nhưng có thể chứa hàng triệu bit 0. Khi dữ liệu cực thưa, g có thể gần n dù q nhỏ.

Do vậy:

- Worst-case của cách lấy mẫu + binary search rank vẫn là **`O(\log(n+1))`**.
- Với dữ liệu có mật độ ổn định và các bit tương đối phân bố đều, khoảng giữa hai mẫu **thường nhỏ hơn**, nên nhiều truy vấn nhanh hơn.
- Để có chặn xấu nhất tốt hơn, phải bổ sung cơ chế riêng cho **khoảng thưa quá dài** hoặc index theo vị trí.

Đây là một nguyên tắc quan trọng khi đánh giá chỉ mục: **tốc độ trung bình theo dữ liệu** không giống **chặn worst-case**.

## 16. Bao nhiêu mẫu select là đủ?

Nếu vector có `m_1` bit 1, lưu mẫu các thứ tự `1,1+q,1+2q,...` thì số mẫu là:

\[
\boxed{
C_1=\left\lceil\frac{m_1}{q}\right\rceil
}
\]

với `m_1≥1`; nếu `m_1=0` thì không có mẫu nào.

Tương tự:

\[
C_0=\left\lceil\frac{m_0}{q}\right\rceil.
\]

Nếu mỗi vị trí được lưu bằng một số nguyên rộng p bit, bộ nhớ mẫu là:

\[
\boxed{p(C_1+C_0)\text{ bit}}
\]

trước padding/allocator. Với n không vượt `2^{32}-1`, có thể chọn vị trí 32 bit tùy quy ước miền và ứng dụng.

### Khi giảm q

- Mẫu nhiều hơn.
- Có nhiều điểm neo gần đáp án hơn **theo thứ tự xuất hiện**.
- Index chiếm nhiều bộ nhớ hơn.
- Không đảm bảo khoảng vị trí ngắn nếu vector rất thưa.

### Khi tăng q

- Mẫu ít hơn.
- Tiết kiệm metadata.
- Mỗi vùng giữa hai mẫu chứa nhiều lần xuất hiện hơn; tìm kiếm hoặc quét cục bộ có thể chậm hơn.

Lấy mẫu là một cách đổi **dung lượng chỉ mục** lấy **độ trễ select**, nhưng phải xác nhận hiệu quả trên phân phối bit thực tế.

## 17. Ví dụ ngân sách bộ nhớ kết hợp rank và select

Với n=1.000.000 bit và giả sử đúng:

`m_1=m_0=500.000`,

dùng:

- Word 64 bit.
- Superblock 512 bit.
- `within` 16 bit/mục.
- `super_ones` 32 bit/mục.
- Sample select1 và select0 mỗi **q=128 lần xuất hiện**.
- Mỗi vị trí sample lưu bằng `uint32_t`.

Ta có:

```text
M = 15625 word
S = 1954 superblock
C1 = ceil(500000 / 128) = 3907
C0 = ceil(500000 / 128) = 3907
```

| Thành phần | Byte |
|---|---:|
| Bit payload 64 bit/word | 125.000 |
| within `uint16_t` | 31.250 |
| super_ones `uint32_t` | 7.820 |
| sample_ones `3907×4` | 15.628 |
| sample_zeros `3907×4` | 15.628 |
| **Tổng vùng mảng** | **195.326** |

Overhead index:

\[
195.326-125.000=70.326\text{ B}.
\]

Tức khoảng **56,3%** so với payload, chưa tính đối tượng/container/allocator và bộ nhớ tạm lúc xây dựng.

### Nhận xét

- Thêm mẫu select làm tổng dung lượng tăng đáng kể.
- Với rank-only, chỉ cần 164.070 B vùng mảng.
- Với chỉ mục select **khác**, ngân sách có thể khác.
- Nếu chỉ cần select1 chứ không select0, có thể bỏ `sample_zeros`.
- Nếu cần tối ưu tuyệt đối số bit, các directory và mẫu phải được **đóng gói**, không giả định Python list int giống uint32.

Không nên tối ưu chỉ mục một cách vô thức: đo trước tần suất truy vấn thực sự.

## 18. Python: lớp chỉ mục rank/select có hai chiến lược select

Mã dưới đây là bản cài đặt **tĩnh** tự chứa. Nó hỗ trợ:

- `bit(i)`: truy cập bit.
- `rank1(i)`, `rank0(i)`: dùng directory hai tầng.
- `select1(k)`, `select0(k)`: dùng prefix superblock và popcount của word.
- `select1_sampled(k)`, `select0_sampled(k)`: dùng các vị trí mẫu để giới hạn binary search.
- `count1()`, `count0()`: số bit tổng.
- Dữ liệu được copy lúc dựng, không có API cập nhật.

```python
from bisect import bisect_left


class RankSelectIndex:
    WORD_BITS = 64
    WORDS_PER_SUPER = 8
    SUPER_BITS = 512

    def __init__(self, bits, sample_stride: int = 128):
        if (
            type(sample_stride) is not int
            or sample_stride < 1
        ):
            raise ValueError("sample_stride phải là số nguyên dương")

        raw = list(bits)
        for b in raw:
            if type(b) not in (int, bool) or b not in (0, 1):
                raise ValueError("Mỗi phần tử phải là 0 hoặc 1")

        self.n = len(raw)
        self.sample_stride = sample_stride

        self.words = [0] * (
            self.n // 64 + (self.n % 64 != 0)
        )

        self.samples1 = []
        self.samples0 = []
        seen1 = 0
        seen0 = 0

        for i, bit in enumerate(raw):
            if bit:
                self.words[i // 64] |= 1 << (i % 64)
                seen1 += 1
                if (seen1 - 1) % sample_stride == 0:
                    self.samples1.append(i)
            else:
                seen0 += 1
                if (seen0 - 1) % sample_stride == 0:
                    self.samples0.append(i)

        self.total_ones = seen1
        self.total_zeros = seen0

        # Prefix tại đầu mỗi superblock, và sentinel cuối.
        self.super_ones = []
        self.super_zeros = []
        self.within = []

        total = 0
        for wi, word in enumerate(self.words):
            if wi % self.WORDS_PER_SUPER == 0:
                self.super_ones.append(total)
                self.super_zeros.append(wi * 64 - total)

            self.within.append(total - self.super_ones[-1])
            total += word.bit_count()

        if self.words:
            self.super_ones.append(total)
            self.super_zeros.append(self.n - total)
        else:
            self.super_ones = [0]
            self.super_zeros = [0]

        assert total == seen1

    def _check_prefix(self, i: int) -> None:
        if type(i) is not int or not 0 <= i <= self.n:
            raise IndexError("rank cần 0 <= i <= n")

    def _check_bit(self, i: int) -> None:
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("bit index ngoài miền")

    def bit(self, i: int) -> int:
        self._check_bit(i)
        return (self.words[i // 64] >> (i % 64)) & 1

    def count1(self) -> int:
        return self.total_ones

    def count0(self) -> int:
        return self.total_zeros

    def rank1(self, i: int) -> int:
        self._check_prefix(i)
        if i == self.n:
            return self.total_ones

        wi = i // 64
        si = wi // self.WORDS_PER_SUPER
        rem = i % 64

        low_mask = (1 << rem) - 1
        return (
            self.super_ones[si]
            + self.within[wi]
            + (self.words[wi] & low_mask).bit_count()
        )

    def rank0(self, i: int) -> int:
        self._check_prefix(i)
        return i - self.rank1(i)

    @staticmethod
    def _select_in_word(word: int, k: int) -> int:
        # Tiền điều kiện: 1 <= k <= bit_count(word).
        for _ in range(k - 1):
            word &= word - 1
        lowbit = word & -word
        return lowbit.bit_length() - 1

    def _select_directory(self, k: int, target: int) -> int:
        if type(k) is not int:
            raise IndexError("k phải là số nguyên")

        total = self.total_ones if target == 1 else self.total_zeros
        if not 1 <= k <= total:
            raise IndexError("select ngoài miền")

        prefix = self.super_ones if target == 1 else self.super_zeros
        si = bisect_left(prefix, k) - 1
        remaining = k - prefix[si]

        start = si * self.WORDS_PER_SUPER
        stop = min(
            start + self.WORDS_PER_SUPER,
            len(self.words),
        )

        for wi in range(start, stop):
            # Phải loại bỏ bit padding cuối word.
            valid = min(64, self.n - 64 * wi)
            mask = (1 << valid) - 1
            word = self.words[wi] & mask

            if target == 0:
                word = (~word) & mask

            pop = word.bit_count()
            if remaining > pop:
                remaining -= pop
                continue

            offset = self._select_in_word(word, remaining)
            result = wi * 64 + offset
            assert 0 <= result < self.n
            return result

        raise AssertionError("Directory select bị sai bất biến")

    def select1(self, k: int) -> int:
        return self._select_directory(k, target=1)

    def select0(self, k: int) -> int:
        return self._select_directory(k, target=0)

    def _select_sampled(self, k: int, target: int) -> int:
        if type(k) is not int:
            raise IndexError("k phải là số nguyên")

        total = self.total_ones if target == 1 else self.total_zeros
        if not 1 <= k <= total:
            raise IndexError("select ngoài miền")

        samples = self.samples1 if target == 1 else self.samples0
        rank = self.rank1 if target == 1 else self.rank0
        a = (k - 1) // self.sample_stride

        # Sample a nằm ở thứ tự r = a*q + 1.
        r = a * self.sample_stride + 1
        anchor = samples[a]

        if k == r:
            return anchor

        # Với k > r, đáp án đứng sau anchor và
        # trước sample kế tiếp nếu có.
        lo = anchor + 1
        hi = (
            samples[a + 1] - 1
            if a + 1 < len(samples)
            else self.n - 1
        )

        while lo < hi:
            mid = lo + (hi - lo) // 2
            if rank(mid + 1) >= k:
                hi = mid
            else:
                lo = mid + 1

        assert rank(lo + 1) == k
        return lo

    def select1_sampled(self, k: int) -> int:
        return self._select_sampled(k, target=1)

    def select0_sampled(self, k: int) -> int:
        return self._select_sampled(k, target=0)


bits = [
    1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0, 1,
    1, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1,
]

index = RankSelectIndex(bits, sample_stride=4)

assert len(bits) == 24
assert index.count1() == 12
assert index.count0() == 12
assert index.rank1(4) == 3
assert index.rank1(12) == 6
assert index.rank1(16) == 8
assert index.rank1(22) == 11
assert index.rank1(24) == 12

assert index.samples1 == [0, 8, 18]
assert index.samples0 == [1, 9, 16]

for k, p in enumerate(
    [0, 2, 3, 6, 8, 11, 12, 14, 18, 20, 21, 23], 1
):
    assert index.select1(k) == p
    assert index.select1_sampled(k) == p
    assert index.rank1(p) == k - 1
    assert index.rank1(p + 1) == k

for k, p in enumerate(
    [1, 4, 5, 7, 9, 10, 13, 15, 16, 17, 19, 22], 1
):
    assert index.select0(k) == p
    assert index.select0_sampled(k) == p
    assert index.rank0(p) == k - 1
    assert index.rank0(p + 1) == k
```

### Tại sao Python dùng `list[int]`?

Ví dụ ưu tiên code dễ học và dễ kiểm thử. `words`, `within`, `super_ones` và `samples` đang là **list chứa số nguyên Python**, không phải mảng `uint64/uint16/uint32` đóng gói. Vì vậy tổng RAM của lớp Python **lớn hơn** bảng lý thuyết ở phần 17.

Muốn đạt dung lượng gần bảng, có thể dùng `array` với kiểu phù hợp, bộ nhớ ánh xạ hoặc thư viện lưu trữ theo từ/bit đóng gói, nhưng phải kiểm tra độ rộng, endian, ABI và độ dài được hỗ trợ.

## 19. Tại sao code chọn mẫu có giới hạn tìm kiếm đúng?

Với stride q, mẫu a tương ứng bit mục tiêu thứ:

\[
r=aq+1
\]

ở vị trí `anchor`. Nếu `k=r`, chính mẫu là đáp án.

Nếu `r<k<r+q`, bit mục tiêu thứ k:

- Đứng **sau** `anchor`.
- Đứng **trước** vị trí mẫu `a+1` (nếu có), vì mẫu sau có thứ tự `r+q>k`.

Vậy đáp án nằm trong:

\[
[anchor+1,\ nextAnchor-1]
\]

hoặc `[anchor+1,n-1]` nếu không còn mẫu sau.

Trong khoảng ấy, hàm `rankTarget(p+1)` không giảm, nên binary search tìm p nhỏ nhất đạt k trả đúng vị trí.

### Vì sao `rank(lo+1)==k`?

Ở vị trí đầu tiên làm rank đạt k, bit tại p phải có giá trị target, nên rank tăng lên đúng 1 từ k−1. Nếu bit tại p không phải target, rank không tăng và p không thể là vị trí đầu tiên đạt ngưỡng.

Kiểm tra `assert` trong ví dụ xác nhận kết quả; nó không thay thế việc kiểm tra đầu vào và bất biến directory.

## 20. Trường hợp đặc biệt khi vector rỗng hoặc dày/thưa

### Vector rỗng

```python
empty = RankSelectIndex([], sample_stride=8)
assert empty.n == 0
assert empty.super_ones == [0]
assert empty.super_zeros == [0]
assert empty.rank1(0) == 0
assert empty.rank0(0) == 0
assert empty.count1() == 0
assert empty.count0() == 0
```

Không tồn tại `select1(1)` hoặc `select0(1)`.

### Toàn bit 1

```python
ones = RankSelectIndex([1] * 64, sample_stride=8)
assert ones.rank1(64) == 64
assert ones.rank0(64) == 0
assert ones.select1(64) == 63
assert ones.select1_sampled(64) == 63
```

`select0(1)` không hợp lệ; trả vị trí padding sẽ là lỗi.

### Một bit 1 cuối vector

```python
last = RankSelectIndex([0] * 64 + [1], sample_stride=4)

assert last.n == 65
assert last.rank1(64) == 0
assert last.rank1(65) == 1
assert last.select1(1) == 64
assert last.select1_sampled(1) == 64
assert last.select0(64) == 63
assert last.select0_sampled(64) == 63
```

Đặc biệt, word thứ hai có **63 bit padding bằng 0**. Chỉ mục `select0` phải loại chúng khỏi các phép đếm.

### Superblock rỗng xen giữa

```python
sparse = RankSelectIndex(
    [1] + [0] * 1023 + [1],
    sample_stride=2,
)

assert sparse.n == 1025
assert sparse.count1() == 2
assert sparse.select1(1) == 0
assert sparse.select1(2) == 1024
assert sparse.select1_sampled(2) == 1024
assert sparse.rank1(512) == 1
assert sparse.rank1(1024) == 1
```

Hai bit 1 cách nhau rất xa: lấy mẫu q=2 vẫn có một đoạn tìm kiếm rộng nếu không có chỉ mục theo vị trí. Đây là bằng chứng thực tế cho giới hạn của lấy mẫu theo thứ tự xuất hiện.

## 21. C++17: directory rank/select tĩnh bằng mảng từ máy

Phiên bản C++ dưới đây tập trung vào directory **superblock + word**. Nó không lưu mẫu select riêng; muốn thêm sample cho C++, có thể dùng cùng quy tắc lấy mẫu như Python.

Sử dụng:

- `std::uint64_t` cho word.
- `std::uint16_t` cho đếm cục bộ.
- `std::size_t` cho tổng tiền tố, chỉ số và n.
- `popcount` kiểu Kernighan để mã chạy trên C++17.
- `std::lower_bound` để tìm superblock chứa bit thứ k.

```cpp
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

class RankSelectDirectory {
public:
    explicit RankSelectDirectory(
        const std::vector<int>& bits
    )
        : n_(bits.size()),
          words_(
              n_ / 64 + (n_ % 64 != 0),
              std::uint64_t{0}
          ) {
        for (std::size_t i = 0; i < n_; ++i) {
            if (bits[i] != 0 && bits[i] != 1) {
                throw std::invalid_argument("bit must be 0 or 1");
            }
            if (bits[i] == 1) {
                words_[i / 64] |=
                    (std::uint64_t{1} << (i % 64));
            }
        }

        std::size_t count = 0;
        for (std::size_t wi = 0; wi < words_.size(); ++wi) {
            if (wi % 8 == 0) {
                super_ones_.push_back(count);

                // wi*64 <= n_ tại đầu word hợp lệ.
                super_zeros_.push_back(wi * 64 - count);
            }

            within_.push_back(
                static_cast<std::uint16_t>(
                    count - super_ones_.back()
                )
            );
            count += popcount(words_[wi]);
        }

        if (words_.empty()) {
            super_ones_.push_back(0);
            super_zeros_.push_back(0);
        } else {
            super_ones_.push_back(count);
            super_zeros_.push_back(n_ - count);
        }
        ones_ = count;
    }

    std::size_t size() const {
        return n_;
    }

    std::size_t count1() const {
        return ones_;
    }

    std::size_t count0() const {
        return n_ - ones_;
    }

    int bit(std::size_t i) const {
        if (i >= n_) {
            throw std::out_of_range("bit index");
        }
        return static_cast<int>(
            (words_[i / 64] >> (i % 64)) & 1ULL
        );
    }

    std::size_t rank1(std::size_t i) const {
        if (i > n_) {
            throw std::out_of_range("rank index");
        }
        if (i == n_) {
            return ones_;
        }

        const std::size_t wi = i / 64;
        const std::size_t si = wi / 8;
        const unsigned rem = static_cast<unsigned>(i % 64);

        const std::uint64_t mask = rem == 0
            ? std::uint64_t{0}
            : ((std::uint64_t{1} << rem) - 1);

        return (
            super_ones_[si]
            + within_[wi]
            + popcount(words_[wi] & mask)
        );
    }

    std::size_t rank0(std::size_t i) const {
        return i - rank1(i);
    }

    std::size_t select1(std::size_t k) const {
        return select_target(k, true);
    }

    std::size_t select0(std::size_t k) const {
        return select_target(k, false);
    }

private:
    static unsigned popcount(std::uint64_t x) {
        unsigned result = 0;
        while (x != 0) {
            x &= x - 1;
            ++result;
        }
        return result;
    }

    static unsigned select_in_word(
        std::uint64_t x, std::size_t k
    ) {
        while (k > 1) {
            x &= x - 1;
            --k;
        }

        unsigned offset = 0;
        while ((x & 1ULL) == 0) {
            x >>= 1;
            ++offset;
        }
        return offset;
    }

    std::size_t select_target(
        std::size_t k, bool search_one
    ) const {
        const std::size_t total =
            search_one ? ones_ : (n_ - ones_);

        if (k == 0 || k > total) {
            throw std::out_of_range("select rank");
        }

        const auto& prefix =
            search_one ? super_ones_ : super_zeros_;

        const auto it = std::lower_bound(
            prefix.begin(), prefix.end(), k
        );

        const std::size_t si =
            static_cast<std::size_t>(
                it - prefix.begin() - 1
            );

        std::size_t remaining = k - prefix[si];
        const std::size_t start = si * 8;
        const std::size_t stop =
            std::min(start + 8, words_.size());

        for (std::size_t wi = start; wi < stop; ++wi) {
            const std::size_t valid =
                std::min(std::size_t{64}, n_ - wi * 64);

            const std::uint64_t mask = valid == 64
                ? std::numeric_limits<std::uint64_t>::max()
                : ((std::uint64_t{1} << valid) - 1);

            std::uint64_t word = words_[wi] & mask;

            if (!search_one) {
                word = (~word) & mask;
            }

            const unsigned count = popcount(word);
            if (remaining > count) {
                remaining -= count;
                continue;
            }

            const unsigned offset =
                select_in_word(word, remaining);
            const std::size_t result = wi * 64 + offset;

            assert(result < n_);
            return result;
        }

        throw std::logic_error("directory invariant broken");
    }

    std::size_t n_;
    std::size_t ones_ = 0;
    std::vector<std::uint64_t> words_;
    std::vector<std::uint16_t> within_;
    std::vector<std::size_t> super_ones_;
    std::vector<std::size_t> super_zeros_;
};

int main() {
    const std::vector<int> bits = {
        1,0,1,1,0,0,1,0,1,0,0,1,
        1,0,1,0,0,0,1,0,1,1,0,1
    };

    const RankSelectDirectory d(bits);

    assert(d.size() == 24);
    assert(d.count1() == 12);
    assert(d.count0() == 12);
    assert(d.rank1(0) == 0);
    assert(d.rank1(4) == 3);
    assert(d.rank1(12) == 6);
    assert(d.rank1(24) == 12);
    assert(d.rank0(24) == 12);
    assert(d.select1(5) == 8);
    assert(d.select1(9) == 18);
    assert(d.select1(12) == 23);
    assert(d.select0(5) == 9);
    assert(d.select0(12) == 22);

    const RankSelectDirectory empty(
        std::vector<int>{}
    );
    assert(empty.rank1(0) == 0);

    const RankSelectDirectory boundary(
        std::vector<int>(64, 0)
    );
    assert(boundary.rank0(64) == 64);
    assert(boundary.select0(64) == 63);

    std::cout << "rank/select directory OK\n";
}
```

### Những điều cần hiểu trong C++

- Không dùng `1ULL<<64`: mask word đầy đủ được xử lý riêng bằng `UINT64_MAX` tương đương.
- `std::lower_bound` trên các tổng **không giảm** xử lý được superblock rỗng khi dùng quy tắc trừ 1.
- `std::uint16_t` đủ cho `within` vì số bit 1 trước một word trong cùng superblock không vượt 448.
- Mỗi superblock có tối đa 8 word nên phần quét local có chặn hằng.
- `std::size_t` và word 64 bit có dung lượng/truy cập tùy nền tảng; phải đo `capacity` và vùng heap khi muốn con số RAM chính xác.
- Đây là ví dụ **dữ liệu tĩnh**. Nếu thay một bit trong `words_` mà quên xây lại directory, rank/select sẽ sai.

## 22. Chứng minh select theo superblock đúng

Ta chứng minh cho `select1(k)`; `select0` tương tự khi chỉ đếm bit 0 hợp lệ.

### Bước 1: xác định superblock

`super_ones[s]` là số bit 1 trước superblock s. Vì các superblock phủ toàn vector, dãy prefix không giảm, bắt đầu bằng 0 và kết thúc bằng `m_1`.

Với `1≤k≤m_1`, tồn tại ít nhất một superblock chứa bit 1 thứ k. Chọn:

\[
s=\operatorname{lowerBound}(super\_ones,k)-1.
\]

Ta có:

\[
super\_ones[s]<k\le super\_ones[s+1].
\]

Đó chính là superblock chứa bit thứ k. Quy tắc lower bound bảo đảm bỏ qua các superblock có cùng tổng vì không chứa bit 1.

### Bước 2: tìm word

Đặt:

\[
remaining=k-super\_ones[s].
\]

Khi duyệt word theo thứ tự:

- Nếu `popcount(word)<remaining`, toàn word nằm **trước** bit cần tìm. Trừ popcount và bỏ qua là đúng.
- Nếu `popcount(word)≥remaining`, bit cần tìm nằm **trong** word hiện tại.

Mỗi word của superblock được xét tối đa một lần, và trong một superblock có tối đa 8 word.

### Bước 3: tìm bit

Xóa `remaining−1` bit 1 thấp nhất trong word hiện tại. Bit 1 thấp nhất còn lại là bit thứ remaining của word ban đầu, nên trả vị trí toàn cục `64*wi+offset`.

Đó chính là bit 1 thứ k của toàn vector.

### Với select0

`super_zeros[s]` được tính từ số vị trí logic trước superblock và số bit 1 trước đó. Trong mỗi word, mask `valid` đảm bảo chỉ đếm các bit 0 thuộc `B[0..n-1]`; vì vậy lập luận trên vẫn đúng.

## 23. Vì sao chỉ mục giúp select mà vẫn có giới hạn?

Hai chỉ mục minh họa có đặc điểm khác nhau:

| Phương án | Định vị ban đầu | Phần việc còn lại | Worst-case |
|---|---|---|---|
| Chỉ có rank | Binary search trên vị trí 0..n-1 | Mỗi bước gọi rank O(1) | `O(log(n+1))` |
| Directory superblock | Binary search trên S+1 mốc | Tối đa 8 word + chọn bit 64 bit | `O(log(S+1)+1)` |
| Mẫu mỗi q bit | Vị trí mẫu gần nhất theo thứ tự | Binary search vùng g vị trí | `O(log(g+1))≤O(log(n+1))` |
| Chỉ mục select O(1) chuyên dụng | Tra cấu trúc phân cấp/select | Một số thao tác giới hạn | `O(1)` trong mô hình tương ứng |

**Một truy vấn vẫn có thể phải tìm kiếm nhiều lần dù directory rất nhỏ.** Chặn worst-case của cả thuật toán phải gồm **cả việc định vị** và **việc chọn trong đoạn**.

Với directory cố định 512 bit, `S≈n/512`; binary search mốc có ít bước hơn binary search trực tiếp trên n vị trí, nhưng hai chặn đều có bậc `O(log n)` khi n tăng.

## 24. Chỉ mục select O(1) cần điều gì khác?

Nếu cần hỗ trợ cả `rank` và `select` trong **O(1)** thời gian với dung lượng gần chặn n bit, phải dùng cấu trúc **succinct** tinh vi hơn.

Một hướng thiết kế theo **thứ tự xuất hiện**:

1. Chia các bit 1 thành nhóm có **t** lần xuất hiện.
2. Lưu vị trí đầu của mỗi nhóm.
3. Phân loại nhóm theo **độ dài khoảng vị trí** mà nó trải qua.
4. Với nhóm rất thưa, có thể lưu vị trí các bit 1 trong nhóm theo cách riêng.
5. Với nhóm dày, dùng chỉ mục con/bảng tra cứu để chọn trực tiếp.
6. Chọn tham số dựa trên `log n` để tổng overhead là `o(n)`.

Lý do phải phân loại: nhóm chứa t bit 1 có thể trải qua t vị trí (rất dày) hoặc hàng triệu vị trí (rất thưa). Chỉ lưu một mốc mỗi t bit chưa đủ để khống chế thời gian.

### Mục tiêu thông tin

Với một bit vector **bất kỳ** dài n, số trạng thái là `2^n`, nên n bit là chặn dữ liệu cố định. Trong mô hình word-RAM và các giả định phù hợp, tồn tại cấu trúc tĩnh hỗ trợ rank/select O(1) bằng:

\[
\boxed{n+o(n)\text{ bit}.}
\]

Đó là một **kết quả thiết kế chuyên biệt**, không phải bảo đảm cho mọi mảng `super_prefix`/sample viết tay.

### Cấu trúc hỗ trợ rank cũng cần tinh gọn

Với chỉ mục rank phân cấp tăng kích thước theo n, một cách phác thảo dùng:

- Superblock dài `L=Θ((log n)^2)` bit.
- Block nhỏ dài `b=Θ(log n)` bit.
- Tổng prefix tại superblock dùng `O(log n)` bit/mốc.
- Tổng cục bộ tại block dùng `O(log log n)` bit/mốc.
- Popcount hoặc lookup ngắn cho phần còn lại.

Overhead:

\[
O\left(\frac{n}{\log n}\right)
+O\left(\frac{n\log\log n}{\log n}\right)
=o(n).
\]

Phần select O(1) cần **chỉ mục riêng tương thích** để vẫn giữ tổng overhead o(n).

## 25. Mật độ bit ảnh hưởng thiết kế chỉ mục

Gọi mật độ bit 1:

\[
\rho=\frac{m_1}{n}\quad(n>0).
\]

### Vector dày (ρ gần 1)

Nếu phần lớn bit là 1:

- `select1(k)` có thể nằm gần vị trí k−1.
- Số bit 0 rất ít; `select0` có thể khó tìm hơn bằng quét word.
- Danh sách vị trí bit 0 có thể nhỏ.
- Mốc lấy mẫu bit 1 nằm gần nhau theo vị trí.

### Vector thưa (ρ gần 0)

Nếu chỉ có ít bit 1:

- `select1(k)` có thể cách các mẫu rất xa theo vị trí.
- Lưu trực tiếp danh sách vị trí bit 1 có thể tốt hơn bitset n bit.
- `rank1(i)` qua tìm kiếm nhị phân trong danh sách vị trí có thể đủ nhanh.
- `select1(k)` trong danh sách vị trí truy cập trực tiếp O(1).

### Vector thành cụm

Nếu có những đoạn dài toàn 0 hoặc toàn 1, khoảng cách giữa mẫu có thể rất không đều. Chỉ nhìn vào mật độ trung bình ρ chưa đủ; phải xem **phân bố theo vị trí**.

Một chỉ mục hiệu quả trên dữ liệu ngẫu nhiên mật độ 50% có thể khác đáng kể trên dữ liệu có cùng mật độ nhưng từng nửa vector gồm toàn 0 hoặc toàn 1.

## 26. Lựa chọn thay thế: danh sách vị trí và Elias–Fano

Nếu bit vector có đúng m bit 1 trong n vị trí, ta có thể lưu danh sách tăng:

\[
P=[p_1,p_2,\ldots,p_m]
\]

thay cho n bit.

Với m số nguyên thuộc `0..n-1`, mỗi số cần `⌈log₂n⌉` bit theo biểu diễn fixed-width riêng. Payload khoảng:

\[
m\lceil\log_2n\rceil.
\]

### Truy vấn trên danh sách vị trí

- `select1(k)=P[k-1]`: O(1) khi mảng hỗ trợ truy cập ngẫu nhiên.
- `rank1(i)`: số phần tử trong P **nhỏ hơn i**, tìm bằng `lower_bound(P,i)`, O(log(m+1)).
- `rank0(i)=i-rank1(i)`.
- `select0` cần index hoặc thuật toán riêng.

Ví dụ với n=1.000.000 và m=100:

- Bit vector đầy đủ cần 1.000.000 bit ≈125.000 B payload.
- 100 vị trí, mỗi vị trí 20 bit, cần khoảng 2.000 bit ≈250 B payload trước padding/header/index.

Một cấu trúc như **Elias–Fano** khai thác tính tăng của P để lưu gọn hơn một dãy số cố định trong nhiều chế độ thưa và hỗ trợ các truy vấn phù hợp. Tuy nhiên, thời gian rank/select và không gian của các biến thể phụ thuộc triển khai; không nên khẳng định mọi Elias–Fano đều cho mọi phép O(1).

**Bài học:** nếu dữ liệu thưa, thay đổi **biểu diễn chính** có thể hiệu quả hơn gắn thêm nhiều chỉ mục vào bit vector dày.

## 27. Khi nào nên lấy mẫu cả 0 và 1?

Nếu ứng dụng hỏi cả:

```text
select1(k)
select0(k)
```

ta có thể:

- Lưu directory `super_ones` và suy ra `super_zeros` từ vị trí ranh giới.
- Dùng cùng một mảng word và mask bit hợp lệ.
- Nếu truy vấn select rất nhiều, lưu mẫu riêng cho bit 1 và bit 0.
- Nếu chỉ hỏi select1, bỏ index select0 để tiết kiệm.

### Thêm prefix 0 có thật sự phải lưu toàn bộ?

Không nhất thiết. Với đầu superblock s ở vị trí `min(n,512s)`:

\[
super\_zeros[s]=\min(n,512s)-super\_ones[s].
\]

Vậy có thể **tính khi cần** từ `super_ones`, giảm bộ nhớ prefix 0. Nhưng để dùng `std::lower_bound` trên một mảng vật lý như ví dụ C++, ta đã chọn lưu `super_zeros` riêng cho dễ hiểu và truy vấn nhanh.

### Đổi bộ nhớ lấy CPU

Nếu không lưu super_zeros:

- Có thể binary search theo chỉ số s, mỗi bước tính `min(n,512s)-super_ones[s]`.
- Số bước vẫn O(log S).
- Mỗi bước thêm một phép nhân/trừ/min.

Vì vậy thậm chí trong cùng chiến lược superblock, ta vẫn có lựa chọn **tính nhanh từ dữ liệu đã có** hay **lưu lại giá trị suy ra**.

## 28. Cập nhật một bit: chỉ mục tĩnh không còn đúng

Giả sử đổi một bit tại p từ 0 thành 1.

Khi đó:

\[
rank1(i)\text{ tăng 1 với mọi }i>p,
\]

và không đổi nếu `i≤p`.

Hậu quả:

- Word chứa p thay đổi.
- `within` của những word phía sau p trong cùng superblock thay đổi.
- `super_ones` của tất cả superblock sau p thay đổi.
- `super_zeros` tương ứng giảm.
- `total_ones` tăng.
- Những vị trí bit 1 được lấy mẫu **có thể thay đổi theo thứ tự**; không thể sửa đơn giản chỉ một mẫu theo vị trí p.
- Thứ tự của các bit 0 cũng thay đổi, nên mẫu select0 cũng có thể bị ảnh hưởng.

Nếu chỉ ghi `words[p//64]` mà giữ nguyên directory, rank và select sẽ trả kết quả **không nhất quán**.

### Cách xử lý dữ liệu tĩnh

Xây chỉ mục một lần, sau đó coi vector bit là **bất biến**. Mọi cập nhật tạo một phiên bản mới hoặc phải xây lại directory. Đây là cách phù hợp với nhiều index đọc thường xuyên và chỉ cập nhật theo đợt.

### Khi cần cập nhật một bit thường xuyên

Dùng **Fenwick tree** trên số bit 1 của từng word:

1. Mỗi word lưu `count[w]=popcount(words[w])`.
2. Fenwick lưu prefix của `count`.
3. Flip một bit làm count của một word tăng/giảm 1.
4. Cập nhật Fenwick bằng điểm delta.

Với M word:

- Set/flip bit: `O(log(M+1))`.
- Rank: `O(log(M+1))`.
- Select1 với tìm theo tổng Fenwick: `O(log(M+1))`.
- Truy cập bit: O(1).

Đây là đánh đổi **tốc độ truy vấn tĩnh O(1)** lấy **khả năng cập nhật hiệu quả**.

## 29. Point update khác chèn/xóa bit

Cần phân biệt hai loại thay đổi:

1. **Point update:** `B[p]` từ 0 sang 1 hoặc ngược lại; chiều dài n không đổi.
2. **Insert/delete:** chèn hoặc xóa một bit tại vị trí p; làm thay đổi vị trí của mọi bit đứng sau p.

Fenwick trên các word cố định hỗ trợ loại 1 tương đối tốt. Nhưng với loại 2, ranh giới word và vị trí logic của cả suffix bị dịch. Một cấu trúc hỗ trợ insert/delete nhanh thường cần:

- Các block bit có khả năng tách/gộp.
- Một cây cân bằng quản lý kích thước và tổng bit 1 của các block.
- Cơ chế cập nhật chỉ mục khi thay đổi chiều dài.

**Không được lấy độ phức tạp của set/flip bit để áp cho insert/delete bit.** Hai bài toán khác nhau về cấu trúc.

## 30. Cách dùng trong bitmap index và lọc dữ liệu

Giả sử B đánh dấu các bản ghi “đang hoạt động”:

```text
B[i]=1 nếu record i đang active.
```

Khi ấy:

- `rank1(i)` = số bản ghi active đứng trước bản ghi i.
- `rank1(n)` = tổng bản ghi active.
- `select1(k)` = ID vị trí của bản ghi active thứ k.
- `rank0(i)` = số bản ghi inactive trước i.
- `select0(k)` = vị trí bản ghi inactive thứ k.

### Chuyển giữa chỉ số gốc và chỉ số dày

Nếu `B[i]=1`, thứ tự active của bản ghi i (đếm từ 1) là:

\[
rank1(i+1).
\]

Ngược lại, bản ghi active thứ k có vị trí:

\[
select1(k).
\]

Chỉ mục rank/select giúp chuyển giữa **vị trí trong bảng gốc** và **vị trí trong danh sách chỉ gồm các bản ghi active** mà không cần lưu một bảng ánh xạ đầy đủ tại mọi vị trí.

### Khi nào cần select?

Nếu chỉ cần lọc hai tập điều kiện bằng AND/OR, thao tác theo word là đủ. Khi cần “lấy bản ghi active thứ k” hoặc “nhảy tới lần xuất hiện tiếp theo”, select làm cấu trúc thuận tiện hơn.

## 31. Cây gọn và wavelet tree cũng dùng directory này

Trong biểu diễn gọn của cây, những chuỗi bit có thể đánh dấu loại nút, ranh giới danh sách con hoặc cấu trúc ngoặc. Rank/select trở thành các phép hỗ trợ điều hướng.

Trong **wavelet tree**, mỗi nút chứa một bit vector đánh dấu ký hiệu đi sang nhánh trái/phải:

- Rank chuyển một vị trí từ dãy ở nút cha xuống vị trí tương ứng ở nút con.
- Select có thể chuyển vị trí của ký hiệu ngược từ nút con lên nút cha.

Chỉ mục phụ cho rank/select vì thế nằm trên **đường truy vấn** của cấu trúc cao hơn. Nếu một truy vấn đi qua h mức và dùng O(1) rank mỗi mức, phần rank góp O(h) thời gian; với select O(log S), chi phí có thể lớn hơn đáng kể.

**Tối ưu một primitive** như rank/select có thể ảnh hưởng trực tiếp tới hiệu năng của nhiều cấu trúc dữ liệu gọn bên trên. Nhưng không nên coi chi phí của toàn wavelet tree chỉ là O(1) vì mỗi bit vector có rank O(1); chiều cao và các bước còn lại vẫn phải được tính.

## 32. Đo hiệu năng và bộ nhớ mà không ngộ nhận

Một benchmark đúng cần ghi rõ:

- n, mật độ `m_1/n`, mức độ tập trung thành cụm.
- Kích thước word và superblock.
- Bước lấy mẫu q.
- Tổng byte payload và các index.
- `sizeof`/capacity/allocator overhead hoặc `sys.getsizeof` khi có object Python.
- Thời gian **dựng** directory.
- Thời gian **rank1/rank0/select1/select0** trên các truy vấn phân bố khác nhau.
- Peak memory khi xây cả input và index.
- Ngôn ngữ/phiên bản/compiler/CPU.

### Vì sao không chỉ đo trung bình?

Một vector có các bit 1 rải đều cho mẫu select hoạt động tốt, nhưng một vector có **khoảng trống rất dài** giữa hai nhóm bit 1 có thể có truy vấn select rơi vào vùng tìm kiếm rộng hơn.

Nên đo thêm p95/p99 hoặc phân phối độ trễ, đặc biệt với truy vấn select và các trường hợp thưa.

### Python và C++ không so RAM trực tiếp bằng số bit lý thuyết

Lớp Python dùng `list[int]` và số nguyên Python; tổng RAM không bằng phép nhân 8 byte/word. C++ với `std::vector<uint64_t>` gần hơn tới vùng word cố định nhưng vẫn có capacity/allocator.

Để so sánh công bằng, hãy đo **đúng cùng loại layout và workload**, không lấy dung lượng lý thuyết của C++ để đại diện cho đối tượng Python.

## 33. Kiểm thử tự động bằng mô hình tham chiếu

Với n nhỏ, tạo cách tính rank/select chậm nhưng đơn giản:

```python
def slow_rank1(bits, i):
    return sum(bits[:i])


def slow_select(bits, target, k):
    positions = [
        i for i, bit in enumerate(bits)
        if bit == target
    ]
    if not 1 <= k <= len(positions):
        raise IndexError("select ngoài miền")
    return positions[k - 1]


def check_index(bits, stride):
    idx = RankSelectIndex(bits, sample_stride=stride)

    for i in range(len(bits) + 1):
        assert idx.rank1(i) == slow_rank1(bits, i)
        assert idx.rank0(i) == i - slow_rank1(bits, i)

    for k in range(1, idx.count1() + 1):
        expected = slow_select(bits, 1, k)
        assert idx.select1(k) == expected
        assert idx.select1_sampled(k) == expected

    for k in range(1, idx.count0() + 1):
        expected = slow_select(bits, 0, k)
        assert idx.select0(k) == expected
        assert idx.select0_sampled(k) == expected


for stride in [1, 2, 4, 16, 128]:
    check_index([], stride)
    check_index([0] * 65, stride)
    check_index([1] * 64, stride)
    check_index([0] * 64 + [1], stride)
    check_index([1, 0] * 33, stride)
    check_index([1] + [0] * 1023 + [1], stride)
    check_index([0] * 512 + [1] + [0] * 512, stride)
```

### Cần thử dữ liệu không hợp lệ

- `rank1(-1)`, `rank1(n+1)`.
- `select1(0)`, `select0(0)`.
- `select1(m_1+1)`, `select0(m_0+1)`.
- `sample_stride=0` hoặc âm.
- Input bit `2`, `−1`, chuỗi hoặc số thực.
- `n=0` và truy vấn select bất kỳ.

Một mô hình tham chiếu chậm đủ tốt để phát hiện lỗi; nó **không cần** tối ưu vì chỉ chạy trong kiểm thử nhỏ.

### Hai bất biến nên kiểm tra

Với mọi `i∈[0,n]`:

\[
rank1(i)+rank0(i)=i.
\]

Với mọi `k∈[1,m_1]`:

\[
rank1(select1(k)+1)=k.
\]

Tương tự cho bit 0. Các đẳng thức này rất hữu ích cho property-based testing.

## 34. Các lỗi điển hình khi xây chỉ mục phụ

| Lỗi | Vì sao sai? | Cách sửa |
|---|---|---|
| Quên quy ước rank `[0,i)` | Lệch một khi kết hợp select | Ghi rõ API và test biên |
| Nhầm k select 1-based và vị trí 0-based | Trả sai sự kiện | Quy ước và kiểm thử tường minh |
| Không lưu tổng cuối `rank1(n)` | Có thể đọc quá word cuối | Lưu total_ones |
| Không reset `within` đầu superblock | Đếm lặp các word trước | Đếm cục bộ từ đầu superblock |
| Cộng `super_ones` hai lần | Rank lớn hơn thực tế | Chia ba đoạn không chồng lấn |
| Không mask phần word trước i | Rank tính cả bit sau i | Mask `(1<<rem)-1` |
| Dịch `1ULL<<64` trong C++ | Dịch quá độ rộng | Nhánh valid=64 riêng |
| Dùng `~word` không mask | Select0 đếm cả padding | Chỉ giữ `valid` bit cuối |
| `lower_bound` chọn sai ở prefix trùng | Select vào superblock rỗng | Dùng `lower_bound(prefix,k)-1` |
| Không kiểm tra k hợp lệ | Có thể vòng lặp trên word 0 | Chặn k trước khi tìm |
| Dùng rank O(1) để khẳng định select O(1) | Quên chi phí tìm kiếm | Tính riêng định vị và chọn |
| Nghĩ khoảng mẫu có tối đa q vị trí | Nhầm số lần xuất hiện với khoảng cách | Giữ chặn theo g |
| Không cộng chi phí chỉ mục select | Đánh giá RAM thấp | Cộng mọi directory/sample |
| Nhầm `list[int]` Python với uint16 array | Tính sai bộ nhớ thực tế | Đo object/allocator |
| Update bit nhưng không cập nhật prefix | Rank/select bị cũ | Chỉ số tĩnh hoặc index động |
| Nhầm flip bit với insert bit | Không xét dịch cả suffix | Chọn cấu trúc theo thao tác |
| Gọi directory 512/64 là `n+o(n)` | Overhead còn Θ(n) | Thiết kế asymptotic theo log n |
| Chỉ benchmark mật độ 50% ngẫu nhiên | Bỏ qua vector thành cụm/thưa | Test nhiều phân phối |
| Quên vector n=0 | Truy cập word không tồn tại | Trả rank(0)=0, select không hợp lệ |
| Quên n=64/65, 512/513 | Sai ở ranh giới word/superblock | Thêm unit test biên |

## 35. Hướng dẫn chọn chiến lược theo workload

| Nhu cầu chính | Cấu trúc gợi ý | Lý do |
|---|---|---|
| Đọc bit, AND/OR hàng loạt | Bitset/word array | Không cần rank/select index |
| Nhiều `rank`, ít `select` | Superblock + word | Rank O(1), select bằng tìm kiếm |
| Nhiều select nhưng memory vừa phải | Directory + sample/select index | Giảm phạm vi truy vấn |
| Vector rất thưa | Danh sách vị trí / Elias–Fano | Có thể dùng ít bit hơn n |
| Cần rank/select O(1) và gần n bit | Cấu trúc succinct tĩnh chuyên dụng | Cần chỉ mục phân cấp có chứng minh |
| Flip/set bit thường xuyên | Fenwick trên popcount word | Update/rank/select O(log M) |
| Chèn/xóa bit giữa dãy | Dynamic bit vector/tree of blocks | Quản lý lại vị trí và tổng |
| Dữ liệu được build theo đợt | Rebuild index theo batch | Đơn giản, tránh chi phí update liên tục |

### Một quy trình thực hành

1. Xác định **đúng quy ước rank/select**.
2. Đếm n, m1, m0 và kiểm tra mật độ.
3. Ghi nhu cầu truy vấn: bao nhiêu rank, select1, select0, cập nhật?
4. Chọn mức block/word và có cần sample select không.
5. Tính byte payload + directory + sample + header/allocator.
6. Lập bảng chặn thời gian cho từng thao tác.
7. Viết unit test với các trường hợp rỗng, toàn 0/1, ranh giới từ.
8. Benchmark cả build, thời gian truy vấn, peak RAM.
9. Nếu update thường xuyên, cân nhắc thay index tĩnh ngay từ thiết kế.
10. Chọn phương án đủ nhanh với tổng bộ nhớ phù hợp, không chạy theo một chỉ số duy nhất.

## 36. Câu hỏi tự kiểm tra có lời giải

**Câu 1.** `rank1(i)` trong bài đếm đoạn nào?

**Đáp án:** `[0,i)`, tức những vị trí đứng **trước i**, không tính vị trí i.

**Câu 2.** `select1(k)` trả giá trị kiểu gì?

**Đáp án:** **Vị trí bắt đầu từ 0** của bit 1 **thứ k**, với k đếm từ 1.

**Câu 3.** `rank0(i)` được tính thế nào từ rank1?

**Đáp án:** `rank0(i)=i-rank1(i)`.

**Câu 4.** Với vector đầu bài, `rank1(12)` bằng bao nhiêu?

**Đáp án:** **6**, vì có sáu bit 1 ở vị trí 0..11.

**Câu 5.** `select1(9)` của vector đầu bài là gì?

**Đáp án:** **18**.

**Câu 6.** `select0(12)` của vector đầu bài là gì?

**Đáp án:** **22**.

**Câu 7.** Nếu `p=select1(k)` thì `rank1(p)` bằng bao nhiêu?

**Đáp án:** `k-1`, vì `rank1(p)` chưa tính bit tại p.

**Câu 8.** Nếu `p=select1(k)` thì `rank1(p+1)` bằng bao nhiêu?

**Đáp án:** **k**, vì tiền tố này vừa chứa thêm bit thứ k.

**Câu 9.** Một vector một triệu bit có bao nhiêu word 64 bit?

**Đáp án:** `⌈1.000.000/64⌉=15.625` word.

**Câu 10.** Một superblock trong ví dụ chứa bao nhiêu word và bao nhiêu bit?

**Đáp án:** **8 word**, mỗi word 64 bit, tổng **512 bit**.

**Câu 11.** `super_ones[s]` lưu gì?

**Đáp án:** Số bit 1 **trước superblock s**, không tính nội dung của superblock s.

**Câu 12.** `within[w]` lưu gì?

**Đáp án:** Số bit 1 trong các word đứng trước w **kể từ đầu superblock chứa w**.

**Câu 13.** Rank1 dùng ba hạng tử nào?

**Đáp án:** `super_ones[s] + within[w] + popcount(words[w]&low_mask)`.

**Câu 14.** Vì sao rank1 đạt O(1) sau khi xây directory?

**Đáp án:** Mỗi truy vấn chỉ đọc vài mốc, một word và popcount trên 64 bit cố định.

**Câu 15.** Vì sao select1 bằng binary search trên rank vẫn là O(log n)?

**Đáp án:** Phải **tìm vị trí** đầu tiên mà rank đạt k; mỗi rank O(1) nhưng có O(log n) bước.

**Câu 16.** Dãy `super_ones=[0,4,4,4,9]` chứa bit 1 thứ 5 ở superblock nào?

**Đáp án:** **Superblock 3** (đánh số từ 0); superblock 1 và 2 rỗng.

**Câu 17.** Khi đã tìm được superblock, chọn bit thứ k trong đó mất thời gian bao nhiêu?

**Đáp án:** **O(1)** trong mô hình cố định 8 word ×64 bit, vì chỉ quét tối đa 8 word và chọn trong một word.

**Câu 18.** Chặn thời gian select1 theo superblock là gì nếu có S superblock?

**Đáp án:** `O(log(S+1)+1)`.

**Câu 19.** Vì sao `select0` cần mask word cuối?

**Đáp án:** Bit padding ngoài n có thể là 0 nhưng **không thuộc vector**.

**Câu 20.** Với n=65, B[0..63]=0 và B[64]=1, `select0(64)` là gì?

**Đáp án:** **63**.

**Câu 21.** Với n=65, `select0(65)` có hợp lệ trong ví dụ câu 20 không?

**Đáp án:** **Không**, vì chỉ có 64 bit 0 hợp lệ.

**Câu 22.** Bước mẫu q=4 chọn các bit 1 thứ mấy?

**Đáp án:** **Thứ 1, 5, 9, 13, ...**.

**Câu 23.** Với vector đầu bài, `samples1` khi q=4 là gì?

**Đáp án:** `[0,8,18]`.

**Câu 24.** Với vector đầu bài, `samples0` khi q=4 là gì?

**Đáp án:** `[1,9,16]`.

**Câu 25.** Khi hỏi `select1(7)` với q=4, vùng tìm kiếm theo mẫu có thể giới hạn ở đâu?

**Đáp án:** Sau vị trí 8 của bit thứ 5 và trước vị trí 18 của bit thứ 9, tức **[9,17]**.

**Câu 26.** Có thể khẳng định khoảng giữa hai mẫu luôn dài không quá q vị trí không?

**Đáp án:** **Không.** q chỉ đếm **số lần xuất hiện target**, không giới hạn số bit đối lập nằm giữa.

**Câu 27.** Nếu có m1 bit 1 và lấy mẫu mỗi q bit 1, số mẫu là bao nhiêu?

**Đáp án:** `⌈m1/q⌉` nếu m1 dương; bằng 0 nếu không có bit 1.

**Câu 28.** Với n=1.000.000 và m1=m0=500.000, q=128, có bao nhiêu mẫu mỗi loại?

**Đáp án:** `⌈500.000/128⌉=3.907` mẫu bit 1 và 3.907 mẫu bit 0.

**Câu 29.** Hai mảng mẫu uint32 ở câu 28 tốn bao nhiêu byte?

**Đáp án:** `2×3.907×4=31.256` byte.

**Câu 30.** Directory rank ví dụ dùng bao nhiêu byte phụ khi n=1.000.000?

**Đáp án:** **39.070 B** từ `within` 31.250 B và `super_ones` 7.820 B theo giả định kiểu cố định.

**Câu 31.** Tổng mảng payload + rank directory + hai sample từ câu 28 là bao nhiêu?

**Đáp án:** **195.326 B**, chưa tính metadata/allocator.

**Câu 32.** Vì sao directory cố định 512/64 bit chưa đạt `n+o(n)`?

**Đáp án:** Số bộ đếm local tỷ lệ n, mỗi bộ đếm dùng số bit hằng, nên overhead **Θ(n)**, không phải o(n).

**Câu 33.** Mục tiêu succinct cho vector n bit bất kỳ là gì?

**Đáp án:** Tổng dung lượng **`n+o(n)` bit** với các truy vấn rank/select hiệu quả trong mô hình tính toán phù hợp.

**Câu 34.** Một chỉ mục rank O(1) có tự bảo đảm select O(1) không?

**Đáp án:** **Không.** Cần tìm kiếm hoặc thiết kế chỉ mục select chuyên biệt.

**Câu 35.** Tại sao cập nhật bit từ 0 sang 1 làm directory tĩnh bị sai?

**Đáp án:** Các tổng prefix đứng sau vị trí cập nhật phải tăng 1; mẫu select cũng có thể đổi.

**Câu 36.** Fenwick trên số bit 1 theo word cho rank và point update chi phí nào?

**Đáp án:** `O(log(M+1))`, với M là số word.

**Câu 37.** Insert một bit có giống flip một bit không?

**Đáp án:** **Không.** Insert làm thay đổi chiều dài và vị trí của suffix, nên cần cấu trúc hỗ trợ dịch/chia block.

**Câu 38.** Khi nào lưu danh sách vị trí bit 1 có thể tốt hơn bitset?

**Đáp án:** Khi m1 rất nhỏ so với n; lưu m1 chỉ số có thể dùng ít bit hơn n-bit vector.

**Câu 39.** Nếu chỉ quan tâm rank, có cần giữ `samples1/samples0` không?

**Đáp án:** **Không.** Directory rank đã đủ; bỏ mẫu giảm overhead.

**Câu 40.** Thuộc tính nào đối chiếu trực tiếp select và rank sau mỗi truy vấn?

**Đáp án:** Với `p=select1(k)`, kiểm tra `rank1(p+1)=k`; tương tự cho bit 0.

## Ghi nhớ

- **Chỉ mục phụ** tăng tốc rank/select bằng cách lưu tổng tiền tố hoặc vị trí mẫu, thay vì quét lại toàn vector. Chỉ mục là **dữ liệu dẫn xuất**, phải nhất quán với bit vector nguồn.
- Chỉ mục rank hai tầng dùng **superblock 512 bit + word 64 bit**. Với `super_ones`, `within` và popcount phần word, `rank1(i)` được trả trong **O(1)** sau khi dựng index trong mô hình word-RAM cố định.
- **Select1/select0** cần định vị bit theo thứ tự xuất hiện. Tìm superblock bằng prefix rồi chọn trong tối đa 8 word có chặn **`O(log(S+1)+1)`**; binary search trực tiếp trên rank là `O(log(n+1))`.
- **Lấy mẫu select mỗi q lần xuất hiện** lưu vị trí của bit mục tiêu thứ `1,1+q,1+2q,...`. Nó giới hạn vùng tìm kiếm giữa các mẫu nhưng **không giới hạn độ dài vùng theo q** nếu bit thưa; worst-case binary search vẫn có thể O(log n).
- **Select0 phải bỏ qua bit padding** cuối từ máy. Có thể suy ra prefix bit 0 từ `prefix0(i)=i-prefix1(i)`, không nhất thiết lưu index 0 hoàn toàn độc lập.
- Directory cố định 512/64 bit dùng **Θ(n) bit phụ**, dù rất hữu ích trong thực tế. Muốn đạt **`n+o(n)` bit và rank/select O(1)** cần cấu trúc succinct chuyên dụng và chứng minh tương ứng.
- **Static và dynamic khác nhau:** flip bit làm prefix và sample bị cũ. Khi cập nhật thường xuyên, dùng Fenwick/segment tree hoặc dynamic bit vector; chèn/xóa bit còn khó hơn set/clear.
- Chọn chỉ mục theo **mật độ, loại truy vấn, tần suất cập nhật và tổng chi phí**: payload, directory, mẫu, metadata, build time và peak RAM. Một chỉ mục tốt là chỉ mục đáp ứng đúng workload với bộ nhớ chấp nhận được, không chỉ là index nhiều tầng nhất.
