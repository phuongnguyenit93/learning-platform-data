# Vector bit với các phép rank và select

Một **vector bit (bit vector)** là dãy có thứ tự mà mỗi phần tử chỉ nhận giá trị `0` hoặc `1`. Đây là một dạng biểu diễn rất gọn: n giá trị Boolean độc lập cần đúng **n bit thông tin** nếu n và thứ tự bit đã được biết. Tuy nhiên, chỉ lưu dãy bit không tự động trả lời nhanh mọi truy vấn.

Giả sử có dãy đánh dấu những vị trí chứa phần tử đặc biệt:

```text
Vị trí:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
Bit:     1  0  1  1  0  0  1  0  1  0  0  1  1  0  1  0
```

Kiểm tra bit ở vị trí i chỉ cần truy cập `B[i]`. Nhưng còn hai câu hỏi quan trọng:

- **Rank:** Có bao nhiêu bit 1 đứng trước một vị trí?
- **Select:** Bit 1 thứ k xuất hiện ở vị trí nào?

Hai thao tác này đưa bit vector từ một mảng cờ đơn giản thành thành phần nền tảng của **cấu trúc dữ liệu gọn (succinct data structures)**, chỉ mục bitmap, cây dạng nén, cấu trúc hỗ trợ điều hướng và nhiều thuật toán trên chuỗi.

Bài học thuộc chương **Biểu diễn gọn**, trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**: xây dựng nền tảng cấu trúc dữ liệu, bất biến, thao tác và phân tích độ phức tạp thời gian/bộ nhớ để chọn cấu trúc phù hợp. Ta sẽ xây từ định nghĩa chính xác, tính tay trên bit vector nhỏ, rồi thiết kế chỉ mục dùng **popcount, word 64 bit, superblock và block**; sau đó phân tích bộ nhớ, triển khai Python/C++17, kiểm thử và đánh đổi khi dữ liệu thay đổi.

## 1. Mục tiêu và quy ước

Sau bài này, bạn có thể:

1. Phân biệt dãy bit logic với vùng lưu trữ theo byte/từ máy, nhất là **padding** ở cuối.
2. Định nghĩa chính xác `rank1`, `rank0`, `select1` và `select0`, tránh lỗi lệch chỉ số.
3. Tính rank/select bằng tay và chứng minh quan hệ giữa hai thao tác.
4. Dùng **popcount**, phép dịch và mask để đếm bit trong một đoạn của từ máy.
5. Xây chỉ mục **superblock 512 bit + word 64 bit** cho `rank1` trong thời gian hằng số theo mô hình từ máy cố định.
6. Cài `select1` bằng tìm superblock và chọn bit trong một từ, phân biệt chặn thời gian với `rank`.
7. Cài `select0` và xử lý chính xác các bit đệm cuối buffer.
8. Phân tích bộ nhớ: payload bit, chỉ mục rank/select, container, padding và overhead cấp phát.
9. Giải thích ý tưởng `n+o(n)` bit, khác với việc đơn thuần đóng gói n Boolean.
10. Biết cách xử lý các truy vấn khi vector **thay đổi** và chọn cấu trúc phù hợp với workload.

**Quy ước cố định xuyên suốt bài:**

- Bit được đánh số **từ 0**: `B[0]` là bit đầu tiên.
- `rank1(i)` đếm số bit 1 trong **đoạn tiền tố nửa mở `[0,i)`**: không tính `B[i]`.
- `rank0(i)` đếm số bit 0 trong cùng đoạn `[0,i)`.
- `select1(k)` trả **chỉ số bắt đầu từ 0** của bit 1 **thứ k, với k bắt đầu từ 1**.
- `select0(k)` có quy ước tương tự cho bit 0.
- `rank` chấp nhận `0≤i≤n`; `select` chỉ xác định khi k thuộc `1..tổng số bit tương ứng`.
- Với `select` ngoài miền, các lớp mã bên dưới **ném lỗi `IndexError` hoặc `std::out_of_range`**; không trả kết quả giả.

Nhiều thư viện khác chọn `rank1(i)` trên đoạn **bao gồm** i hoặc `select1(k)` đánh k từ 0. Hai cách không sai nếu nhất quán, nhưng **không thể dùng lẫn** công thức, test và API giữa chúng.

## 2. Bit vector lưu những gì?

Với n bit:

\[
B=(b_0,b_1,\ldots,b_{n-1}),\qquad b_i\in\{0,1\}.
\]

Có `2^n` dãy bit khác nhau. Bởi vậy mã cố định cần ít nhất:

\[
\lceil\log_2(2^n)\rceil=n
\]

bit nếu mọi dãy đều hợp lệ và n đã biết.

### Payload và vùng cấp phát

- **n bit** là dung lượng logic.
- Nếu cấp phát theo byte, vùng dữ liệu cần `\lceil n/8\rceil` byte.
- Nếu dùng các từ 64 bit, cần `\lceil n/64\rceil` từ, tương đương `8\lceil n/64\rceil` byte payload từ máy.

Ví dụ n=130:

```text
Bit logic:                    130 bit
Đóng gói theo byte:            17 byte (136 bit)
Đóng gói bằng word 64 bit:      3 word = 24 byte (192 bit)
```

Các bit thừa ở cuối word là **padding**, không thuộc dãy B. Không được đếm chúng vào số bit 0 của vector khi thực hiện `rank0` hoặc `select0`.

### Thứ tự bit trong bộ nhớ

Ta quy định cho mỗi word:

```text
B[64*w + j] nằm ở bit j của words[w], 0 <= j < 64.
```

Với j=0, đó là bit có giá trị `2^0`. Quy ước này giúp đặt/kiểm tra bit bằng dịch và mask. Khi ghi ra file/network, phải định nghĩa thêm **thứ tự byte**; một `uint64_t` trong RAM không phải tự động là wire format portable.

## 3. Vì sao rank và select hữu ích?

Một bit vector có thể đánh dấu vị trí mà một sự kiện xảy ra.

Ví dụ:

```text
B = 1 0 1 1 0 0 1 0
    0 1 2 3 4 5 6 7  (chỉ số)
```

Những vị trí có bit 1 là:

\[
P=[0,2,3,6].
\]

Ta cần trả lời hai chiều:

- Đang ở vị trí i, **đã gặp bao nhiêu vị trí đánh dấu?** → `rank1(i)`.
- Đang cần sự kiện đánh dấu thứ k, **nó nằm ở đâu?** → `select1(k)`.

### Hai góc nhìn

```text
Vị trí gốc i  --rank-->  số lượng bit 1 trước i

Thứ tự k của bit 1 --select--> vị trí gốc
```

Rank chuyển từ **tọa độ trong vector** sang **chỉ số đếm sự kiện**. Select chuyển từ **thứ tự sự kiện** sang **tọa độ trong vector**.

Đó là hai thao tác nền tảng để lập chỉ mục trong dữ liệu gọn, nhất là khi ta không muốn lưu riêng toàn bộ danh sách vị trí của bit 1.

## 4. Định nghĩa toán học của rank

Với `0≤i≤n`:

\[
\boxed{
\operatorname{rank}_1(i)
=\sum_{j=0}^{i-1}b_j.
}
\]

Tổng rỗng bằng 0, nên:

\[
\operatorname{rank}_1(0)=0.
\]

Tổng số bit 1 của toàn vector:

\[
m_1=\operatorname{rank}_1(n).
\]

Trong đoạn `[0,i)` có đúng i vị trí; số bit 0 là:

\[
\boxed{
\operatorname{rank}_0(i)
=i-\operatorname{rank}_1(i).
}
\]

Vậy:

\[
m_0=\operatorname{rank}_0(n)=n-m_1.
\]

### Các bất biến đơn giản

Với mọi i hợp lệ:

\[
0\le\operatorname{rank}_1(i)\le i,
\]

\[
\operatorname{rank}_1(i+1)-\operatorname{rank}_1(i)=b_i
\quad(0\le i<n).
\]

Do đó `rank1` là hàm **không giảm**. Nó tăng đúng một khi đi qua một bit 1; đứng yên khi đi qua một bit 0.

Tương tự, `rank0(i+1)-rank0(i)=1-b_i`.

## 5. Định nghĩa select và miền hợp lệ

Nếu vector có `m_1` bit 1, thì với `1≤k≤m_1`:

\[
\boxed{
\operatorname{select}_1(k)
=\text{vị trí của bit 1 thứ k từ trái sang phải}.
}
\]

Tương tự `select0(k)` cho bit 0, với `1≤k≤m_0`.

Định nghĩa tương đương:

\[
\operatorname{select}_1(k)
=\min\{p\in[0,n):\operatorname{rank}_1(p+1)=k\}.
\]

Chỉ xét p sao cho `B[p]=1`; khi `k≥1`, vị trí tối thiểu thỏa công thức này thực sự là bit 1 thứ k.

### Khi không có bit phù hợp

Nếu vector toàn bit 0:

```text
B = 0 0 0 0
```

thì `rank1(i)=0` với mọi i, nhưng `select1(1)` **không tồn tại**.

Nếu vector toàn bit 1:

```text
B = 1 1 1 1
```

thì `rank0(i)=0` với mọi i, và `select0(1)` không tồn tại.

Đừng trả về `n` hoặc `0` mà không ghi rõ sentinel, vì các giá trị đó dễ bị dùng nhầm làm chỉ số hợp lệ. Trong bài, truy vấn select ngoài miền **báo lỗi**.

## 6. Tính tay rank và select trên 16 bit

Dùng bit vector:

```text
Chỉ số:  0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
B[i]:    1  0  1  1  0  0  1  0  1  0  0  1  1  0  1  0
```

Vị trí có bit 1:

```text
[0, 2, 3, 6, 8, 11, 12, 14]
```

Vị trí có bit 0:

```text
[1, 4, 5, 7, 9, 10, 13, 15]
```

### Bảng rank1 cho mọi tiền tố

| i | Đoạn đã xét | rank1(i) | rank0(i) |
|---:|---|---:|---:|
| 0 | Rỗng | 0 | 0 |
| 1 | `[0,1)` | 1 | 0 |
| 2 | `[0,2)` | 1 | 1 |
| 3 | `[0,3)` | 2 | 1 |
| 4 | `[0,4)` | 3 | 1 |
| 5 | `[0,5)` | 3 | 2 |
| 6 | `[0,6)` | 3 | 3 |
| 7 | `[0,7)` | 4 | 3 |
| 8 | `[0,8)` | 4 | 4 |
| 9 | `[0,9)` | 5 | 4 |
| 10 | `[0,10)` | 5 | 5 |
| 11 | `[0,11)` | 5 | 6 |
| 12 | `[0,12)` | 6 | 6 |
| 13 | `[0,13)` | 7 | 6 |
| 14 | `[0,14)` | 7 | 7 |
| 15 | `[0,15)` | 8 | 7 |
| 16 | `[0,16)` | 8 | 8 |

Ví dụ:

\[
\operatorname{rank}_1(4)=3
\]

vì trước vị trí 4 có các bit 1 tại 0, 2, 3.

\[
\operatorname{rank}_1(13)=7
\]

vì đoạn `[0,13)` chứa bảy bit 1.

### Bảng select

| k | select1(k) | select0(k) |
|---:|---:|---:|
| 1 | 0 | 1 |
| 2 | 2 | 4 |
| 3 | 3 | 5 |
| 4 | 6 | 7 |
| 5 | 8 | 9 |
| 6 | 11 | 10 |
| 7 | 12 | 13 |
| 8 | 14 | 15 |

Ví dụ `select1(5)=8` vì bit 1 thứ năm ở vị trí 8. `select0(5)=9` vì bit 0 thứ năm ở vị trí 9.

## 7. Các hệ thức rank/select để tự kiểm tra

Nếu `p=select1(k)`, thì:

\[
\boxed{
\operatorname{rank}_1(p)=k-1
}
\]

và:

\[
\boxed{
\operatorname{rank}_1(p+1)=k.
}
\]

Điều này đúng vì rank đếm **trước vị trí**, còn select trả vị trí của chính bit thứ k.

Tương tự:

\[
\operatorname{rank}_0(\operatorname{select}_0(k)+1)=k.
\]

### Truy vấn vị trí bit 1 đầu tiên không đứng trước i

Đếm số bit 1 **trước** i bằng `rank1(i)`, rồi yêu cầu bit tiếp theo:

\[
p=\operatorname{select}_1(\operatorname{rank}_1(i)+1),
\]

nếu còn tồn tại bit 1.

Kết quả p là vị trí bit 1 **nhỏ nhất ≥i**. Nếu `B[i]=1`, p bằng chính i.

### Truy vấn bit 1 cuối cùng trước i

Đặt `k=rank1(i)`. Nếu `k>0`, thì:

\[
p=\operatorname{select}_1(k)
\]

là vị trí bit 1 **lớn nhất nhỏ hơn i**.

Những công thức này hữu ích cho truy vấn predecessor/successor trên tập vị trí đánh dấu.

## 8. Giải pháp ngây thơ: quét hoặc lưu toàn bộ prefix

Trước khi tối ưu, hãy biết hai cách cơ bản.

### Quét trực tiếp

```text
rank1(i):
    count = 0
    for j = 0 .. i-1:
        count += B[j]
    return count
```

Thời gian `O(i)`, trong trường hợp xấu `O(n)`. Không cần chỉ mục phụ, nhưng chậm khi nhiều truy vấn.

Để `select1(k)`:

```text
count = 0
for i = 0 .. n-1:
    if B[i] == 1:
        count += 1
        if count == k:
            return i
```

Thời gian `O(n)` worst-case.

### Lưu mảng tổng tiền tố

Tạo:

\[
prefix[0]=0,\quad
prefix[i+1]=prefix[i]+B[i].
\]

Khi đó:

```text
rank1(i) = prefix[i]
```

là `O(1)`. Nhưng mảng có `n+1` số đếm, mỗi số có thể lên tới n và cần `\lceil\log_2(n+1)\rceil` bit nếu lưu tối thiểu theo trường cố định.

Overhead lý thuyết khoảng:

\[
(n+1)\lceil\log_2(n+1)\rceil\text{ bit},
\]

lớn hơn rất nhiều so với n bit gốc khi n lớn. Với mảng số 32 bit thông thường, prefix còn có thể tốn **4(n+1) byte**.

Đây là lý do cần **chỉ mục phân cấp**, thay vì lưu một số đếm đầy đủ ở mọi vị trí.

## 9. Popcount: đếm bit 1 trong một từ máy

Một word 64 bit có thể lưu 64 phần tử Boolean. Phép **population count (popcount)** trả số bit 1 trong word.

Ví dụ:

```text
word = 0b10110100
popcount(word) = 4
```

Trong Python:

```python
assert (0b10110100).bit_count() == 4
```

Trong C++20 có `std::popcount` trong `<bit>`. Với C++17 có thể dùng intrinsic phù hợp compiler, hoặc tự cài thuật toán xóa bit 1 thấp nhất.

### Thuật toán Kernighan

```text
count = 0
while word != 0:
    word = word & (word - 1)
    count += 1
```

Mỗi vòng bỏ một bit 1, nên số vòng bằng số bit 1 ban đầu. Trên word 64 bit, tối đa 64 vòng.

Trong mô hình từ máy **cố định** và với popcount phần cứng, xử lý một word thường được xem là `O(1)`. Không nên áp nhận định đó cho các số nguyên tùy ý lớn mà không xét số bit.

## 10. Đếm phần tiền tố của một word bằng mask

Cho word 64 bit và cần đếm đúng t bit thấp, với `0≤t≤64`.

Nếu `0≤t<64`, mask là:

\[
mask=(1\ll t)-1.
\]

Số bit 1 trong đoạn thấp:

\[
\boxed{
\operatorname{popcount}(word\ \&\ mask).
}
\]

### Ví dụ

```text
word = 0b10110100
t = 5

mask              = 0b00011111
word & mask       = 0b00010100
popcount          = 2
```

Chỉ các bit ở vị trí 0..4 được tính.

### Cẩn thận với t=64 trong C/C++

Đối với kiểu 64 bit, phép `1ULL << 64` là dịch quá độ rộng và không hợp lệ. Khi t=64, phải trả trực tiếp `popcount(word)` hoặc dùng nhánh xử lý riêng.

Trong chỉ mục dưới đây, khi rank ở đúng cuối toàn vector, ta có thể trả tổng `ones` đã tính sẵn; còn trong một word chưa kết thúc, phần còn lại `t=i%64` luôn thuộc `0..63`.

## 11. Từ word tới chỉ mục rank hai tầng

Chỉ một từ 64 bit không giải quyết được rank trên vector hàng triệu bit. Nếu truy vấn rank tại vị trí i, ta cần:

1. Số bit 1 trong **mọi word hoàn chỉnh trước i**.
2. Số bit 1 trong **phần word đang chứa i**.

Nếu mỗi truy vấn cộng lại toàn bộ các word trước đó, chi phí vẫn là `O(n/64)`.

Ta lưu hai tầng chỉ mục:

- **Superblock:** nhóm **8 word × 64 bit = 512 bit**.
- **Block/word:** một word 64 bit.

Dữ liệu lưu:

1. `super_prefix[s]`: số bit 1 **trước** superblock s.
2. `within_super[w]`: số bit 1 trong **các word trước word w nhưng vẫn trong cùng superblock**.
3. `words[w]`: word 64 bit thực tế chứa các bit.

Chỉ mục rank không lưu mỗi bit riêng; nó chỉ lưu các tổng ở ranh giới word và superblock.

## 12. Công thức rank1 dùng superblock và word

Với `0≤i<n`:

```text
word_idx    = floor(i / 64)
super_idx   = floor(word_idx / 8)
offset      = i mod 64
```

Lúc đó:

\[
\boxed{
\operatorname{rank}_1(i)=
super\_prefix[super\_idx]
+within\_super[word\_idx]
+\operatorname{popcount}
\left(
words[word\_idx]\ \&\ ((1\ll offset)-1)
\right).
}
\]

Công thức tách tiền tố thành **ba đoạn rời nhau**:

1. Mọi superblock trước superblock hiện tại.
2. Những word hoàn chỉnh từ đầu superblock tới trước word hiện tại.
3. Phần bit đầu word hiện tại nằm trước i.

Không đoạn nào bị đếm hai lần.

### Trường hợp `i=n`

Ta lưu sẵn `total_ones`, nên:

```text
rank1(n) = total_ones
```

Cần nhánh này vì nếu n là bội của 64, `word_idx=n/64` có thể chính bằng độ dài mảng word. Truy cập `words[word_idx]` sẽ vượt biên.

### Trường hợp `i=0`

Nếu n>0, `word_idx=0`, `super_idx=0`, `offset=0`. Mask `(1<<0)-1=0`, nên kết quả bằng 0.

Nếu n=0, chỉ có truy vấn `rank1(0)` hợp lệ và trả 0 ngay; không truy cập word nào.

## 13. Truy vết trên chín word

Để thấy công thức hoạt động, giả sử một vector có **9 word 64 bit** với số bit 1 trong từng word:

```text
word index:      0  1  2  3  4  5  6  7 | 8
popcount:        4  0 12  7  2  0  3  9 | 5
                 \-------- super 0 ----/ \super 1
```

Superblock 0 có:

\[
4+0+12+7+2+0+3+9=37
\]

bit 1. Superblock 1 có 5 bit 1.

Chỉ mục superblock (gồm mốc kết thúc):

```text
super_prefix = [0, 37, 42]
```

Chỉ mục trong superblock tại đầu từng word:

```text
within_super = [0,4,4,16,23,25,25,28,0]
```

Nếu hỏi `rank1(8*64+10)`, tức i=522:

- `word_idx=8`.
- `super_idx=1`.
- `within_super[8]=0`.
- `super_prefix[1]=37`.

Giả sử 10 bit thấp của `words[8]` chứa 3 bit 1. Khi đó:

\[
rank1(522)=37+0+3=40.
\]

Không cần quét 8 word đầu.

### Vì sao within_super của word 8 bằng 0?

Word 8 là **word đầu của superblock mới**. Đã có `super_prefix[1]=37` đếm tất cả các word trước đó, nên phần đếm trong superblock mới phải bắt đầu lại ở 0.

## 14. Bộ nhớ của chỉ mục rank

Với n bit:

- Số word 64 bit: `M=\lceil n/64\rceil`.
- Số superblock 512 bit: `S=\lceil n/512\rceil`.
- Mảng `super_prefix` có thể chứa `S+1` tổng tiền tố.
- `within_super` có M số đếm cục bộ.

Một superblock có tối đa 512 bit. Số bit 1 **trước đầu một word trong superblock** không vượt 448, nên cần tối đa **9 bit** nếu đóng gói thật chặt (vì `448<512`). Trong triển khai tiện dụng, có thể dùng `uint16_t`, tức 16 bit cho mỗi số cục bộ.

`super_prefix` cần chứa các số từ 0 đến n nên về mặt thông tin có thể cần `\lceil\log_2(n+1)\rceil` bit mỗi mục; trong chương trình thực tế thường dùng `uint32_t` hoặc `uint64_t` tùy n.

### Ví dụ một triệu bit

Với n=1.000.000:

```text
word 64 bit:
  ceil(1000000 / 64) = 15625 word
  15625 * 8 = 125000 byte

superblock 512 bit:
  ceil(1000000 / 512) = 1954 superblock
  super_prefix có 1955 mục
```

Nếu mô hình hóa bằng mảng số cố định:

| Thành phần | Cách tính | Byte |
|---|---|---:|
| Word payload | `15.625×8` | 125.000 |
| within_super kiểu 16 bit | `15.625×2` | 31.250 |
| super_prefix kiểu 32 bit | `1.955×4` | 7.820 |
| **Tổng vùng mảng** | | **164.070** |

Chỉ mục phụ dùng **39.070 byte**, khoảng **31,3%** so với payload word. Đây là ví dụ **đánh đổi bộ nhớ lấy thời gian truy vấn**, không phải một tuyên bố rằng chỉ mục này đã đạt `n+o(n)` bit.

**Quan trọng:** lớp Python bên dưới sử dụng `list[int]` và số nguyên Python, không có layout 16/32-bit nén như bảng. Các số trong bảng là **ước lượng cho một thiết kế mảng kiểu cố định**, không phải kết quả `sys.getsizeof` của lớp Python.

## 15. Python: xây bit vector có chỉ mục rank

Ta triển khai một lớp chỉ số tĩnh cho các bit được cung cấp lúc khởi tạo. Sau khi xây chỉ mục, lớp không cho phép thay đổi các word.

Lớp chấp nhận giá trị `0`, `1`, `False`, `True`, nhưng từ chối các loại khác để giữ hợp đồng rõ ràng.

```python
from bisect import bisect_left


class IndexedBitVector:
    WORD_BITS = 64
    WORDS_PER_SUPER = 8
    SUPER_BITS = WORD_BITS * WORDS_PER_SUPER

    def __init__(self, bits):
        raw = list(bits)
        for b in raw:
            if type(b) not in (int, bool) or b not in (0, 1):
                raise ValueError("Mỗi phần tử phải là bit 0 hoặc 1")

        self.n = len(raw)
        self.words = [0] * ((self.n + 63) // 64)

        for i, b in enumerate(raw):
            if b:
                self.words[i // 64] |= 1 << (i % 64)

        self.super_prefix = []
        self.within_super = []
        total = 0

        for wi, word in enumerate(self.words):
            # Ghi tổng ở đầu mỗi superblock 8 word.
            if wi % self.WORDS_PER_SUPER == 0:
                self.super_prefix.append(total)

            self.within_super.append(
                total - self.super_prefix[-1]
            )
            total += word.bit_count()

        # Sentinel ở ranh giới kết thúc toàn vector.
        self.super_prefix.append(total)
        self.total_ones = total

    def _check_prefix(self, i: int) -> None:
        if type(i) is not int or not 0 <= i <= self.n:
            raise IndexError("rank cần 0 <= i <= n")

    def _check_bit_index(self, i: int) -> None:
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("bit index ngoài miền")

    def bit(self, i: int) -> int:
        self._check_bit_index(i)
        return (self.words[i // 64] >> (i % 64)) & 1

    def rank1(self, i: int) -> int:
        self._check_prefix(i)

        if i == self.n:
            return self.total_ones

        wi = i // 64
        super_idx = wi // self.WORDS_PER_SUPER
        offset = i % 64

        mask = (1 << offset) - 1
        partial = (self.words[wi] & mask).bit_count()

        return (
            self.super_prefix[super_idx]
            + self.within_super[wi]
            + partial
        )

    def rank0(self, i: int) -> int:
        self._check_prefix(i)
        return i - self.rank1(i)

    def count1(self) -> int:
        return self.total_ones

    def count0(self) -> int:
        return self.n - self.total_ones


bits = [
    1, 0, 1, 1, 0, 0, 1, 0,
    1, 0, 0, 1, 1, 0, 1, 0,
]

bv = IndexedBitVector(bits)

assert bv.n == 16
assert bv.words[0] == 0x594D
assert bv.count1() == 8
assert bv.count0() == 8

assert bv.rank1(0) == 0
assert bv.rank1(4) == 3
assert bv.rank1(8) == 4
assert bv.rank1(13) == 7
assert bv.rank1(16) == 8

assert bv.rank0(16) == 8
assert bv.bit(11) == 1
assert bv.bit(10) == 0
```

### Tại sao `super_prefix` có mục cuối?

Mục kết thúc giúp xác định **tổng số bit 1 tới cuối superblock cuối**, kể cả khi superblock cuối có ít hơn 512 bit. Nó cũng dùng cho phép tìm superblock của bit 1 thứ k.

Lưu ý `rank1(n)` trả thẳng `total_ones` nên không cần truy cập từ cuối không tồn tại.

### Bất biến sau khi xây

Với mỗi word wi:

\[
super\_prefix[\lfloor wi/8\rfloor]
+within\_super[wi]
\]

bằng số bit 1 **trước word wi**. Bất biến này chính là cơ sở để công thức `rank1` đúng.

## 16. Chứng minh `rank1` đúng và nhanh

Cho vị trí i trong `[0,n)`. Tập các bit trước i được chia thành ba tập rời nhau:

1. Bit ở tất cả các superblock hoàn chỉnh đứng trước superblock chứa i.
2. Bit trong các word hoàn chỉnh đứng trước word chứa i nhưng vẫn trong superblock hiện tại.
3. Các bit từ đầu word hiện tại tới trước i.

`super_prefix` đếm tập 1; `within_super` đếm tập 2; `popcount(words[wi]&mask)` đếm tập 3.

Vì ba tập **không giao nhau** và hợp lại đúng `[0,i)`, tổng ba số là `rank1(i)`. Trường hợp i=n được giải bằng tổng tiền tố cuối đã tính sẵn.

### Thời gian

Mỗi truy vấn `rank1` chỉ:

- Tính vài chỉ số bằng phép chia/dịch với hằng 64 và 8.
- Đọc hai mục chỉ mục.
- Đọc một word 64 bit.
- Tạo một mask và gọi popcount.

Trên mô hình **word-RAM cố định với popcount word 64 bit trong thời gian hằng**, `rank1(i)` có:

\[
\boxed{O(1)\text{ thời gian truy vấn sau khi xây chỉ mục}.}
\]

Chi phí xây các word và directory là `O(n)` khi đọc n bit đầu vào (và mảng lưu cố định theo từ).

### Điều không được nhầm

`O(1)` của `rank1` **không suy ra** `O(1)` cho `select1`. Việc tìm vị trí bit thứ k có thể cần thêm tìm kiếm hoặc một chỉ mục select chuyên dụng.

## 17. Select1 từ chỉ mục rank: hai chiến lược

### Chiến lược A: binary search trên rank1

Vì `rank1(i)` không giảm, ta có thể tìm vị trí p nhỏ nhất sao cho:

\[
rank1(p+1)\ge k.
\]

Dùng binary search trên `p∈[0,n)`:

```text
lo = 0
hi = n - 1

while lo < hi:
    mid = (lo + hi) // 2

    if rank1(mid + 1) >= k:
        hi = mid
    else:
        lo = mid + 1

return lo
```

Vì mỗi `rank1` là `O(1)`, ta nhận:

\[
O(\log(n+1))
\]

thời gian select khi k hợp lệ. Đây là cách đơn giản và dễ kiểm thử.

### Chiến lược B: tìm superblock trước

Mảng `super_prefix` không giảm. Muốn tìm bit 1 thứ k, ta tìm superblock s chứa nó, tức:

\[
super\_prefix[s]<k\le super\_prefix[s+1].
\]

Do một số superblock có thể **không có bit 1**, mảng prefix có thể có các giá trị bằng nhau. Cần tìm **đúng superblock** bằng quy tắc lower bound có xử lý bản ghi trùng.

Sau khi có s:

1. Đặt `remaining=k-super_prefix[s]`.
2. Duyệt tối đa **8 word** của superblock s.
3. Trừ popcount của mỗi word nếu còn chưa tới bit cần tìm.
4. Ở word cuối, xác định vị trí bit 1 thứ `remaining` trong riêng word đó.

Với superblock cố định 512 bit, phần quét cục bộ có **giới hạn hằng số**. Thời gian còn lại là binary search trên khoảng `S+1` mốc superblock:

\[
\boxed{O(\log(S+1)+1),\quad S=\lceil n/512\rceil.}
\]

Chưa phải chặn `O(1)` tổng quát cho select khi n tăng.

## 18. Chọn bit 1 thứ k trong một word

Với word 64 bit khác 0, nếu k nằm trong `1..popcount(word)`, ta có thể bỏ `k-1` bit 1 thấp nhất bằng:

```text
repeat k-1 times:
    word = word & (word - 1)
```

Sau đó, bit 1 thấp nhất còn lại chính là bit thứ k của word ban đầu.

Phần bit 1 thấp nhất của số nguyên dương không dấu có thể lấy bằng:

```text
lowbit = word & -word
```

Trong Python, có thể lấy vị trí của nó bằng:

```python
offset = (lowbit.bit_length() - 1)
```

Ví dụ:

```text
word = 0b10110100
Vị trí bit 1: [2,4,5,7]
```

Chọn bit 1 thứ ba:

```text
Bỏ bit vị trí 2 → còn vị trí [4,5,7]
Bỏ bit vị trí 4 → còn vị trí [5,7]
Bit thấp nhất hiện tại ở vị trí 5.
```

Vì word có đúng 64 bit, cách làm mất tối đa 63 lần lặp. Đây là **hằng số theo n**, dù có thể chậm hơn lệnh bit-select chuyên biệt trên phần cứng/thư viện tối ưu.

## 19. Python: thêm select1 và select0

Ta mở rộng lớp `IndexedBitVector` đã định nghĩa ở phần 15.

- `select1` dùng tìm kiếm superblock.
- `select0` dùng binary search trên `rank0` để đơn giản và đặc biệt **không đếm bit padding cuối**.

```python
def _select1(self, k: int) -> int:
    if type(k) is not int or not 1 <= k <= self.count1():
        raise IndexError("k không phải thứ tự bit 1 hợp lệ")

    # Superblock chứa bit 1 thứ k:
    # lấy vị trí trước mốc đầu tiên có prefix >= k.
    super_idx = bisect_left(self.super_prefix, k) - 1
    remaining = k - self.super_prefix[super_idx]

    start_word = super_idx * self.WORDS_PER_SUPER
    end_word = min(
        start_word + self.WORDS_PER_SUPER,
        len(self.words),
    )

    for wi in range(start_word, end_word):
        word = self.words[wi]
        count = word.bit_count()

        if remaining > count:
            remaining -= count
            continue

        # Lấy bit 1 thứ remaining trong word hiện tại.
        for _ in range(remaining - 1):
            word &= word - 1

        lowbit = word & -word
        offset = lowbit.bit_length() - 1
        result = wi * 64 + offset

        assert 0 <= result < self.n
        return result

    raise AssertionError("Chỉ mục select1 không nhất quán")


def _select0(self, k: int) -> int:
    if type(k) is not int or not 1 <= k <= self.count0():
        raise IndexError("k không phải thứ tự bit 0 hợp lệ")

    # Chỉ tìm trên các vị trí logic 0..n-1.
    # Không bao giờ đếm các bit padding thành bit 0.
    lo, hi = 0, self.n - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if self.rank0(mid + 1) >= k:
            hi = mid
        else:
            lo = mid + 1
    return lo


IndexedBitVector.select1 = _select1
IndexedBitVector.select0 = _select0

assert [bv.select1(k) for k in range(1, 9)] == [
    0, 2, 3, 6, 8, 11, 12, 14
]
assert [bv.select0(k) for k in range(1, 9)] == [
    1, 4, 5, 7, 9, 10, 13, 15
]

assert bv.select1(1) == 0
assert bv.select1(5) == 8
assert bv.select1(8) == 14
assert bv.select0(5) == 9

for k in range(1, bv.count1() + 1):
    p = bv.select1(k)
    assert bv.rank1(p) == k - 1
    assert bv.rank1(p + 1) == k

for k in range(1, bv.count0() + 1):
    p = bv.select0(k)
    assert bv.rank0(p + 1) == k
```

### Vì sao dùng `bisect_left(prefix,k)-1`?

Giả sử:

```text
super_prefix = [0, 4, 4, 4, 9]
```

Superblock 0 có 4 bit 1; superblock 1 và 2 rỗng; superblock 3 có thêm 5 bit 1.

- Với `k=4`, `bisect_left(...,4)` trả chỉ số 1, suy ra superblock **0**: đúng.
- Với `k=5`, `bisect_left(...,5)` trả chỉ số 4, suy ra superblock **3**: đúng.

Không được chọn bừa một trong các mốc có prefix bằng nhau; những superblock rỗng phải được bỏ qua đúng cách.

### Ghi chú về ví dụ Python

Phương pháp gán:

```python
IndexedBitVector.select1 = _select1
IndexedBitVector.select0 = _select0
```

chỉ để giữ phần cài đặt rank và select ở hai đoạn giải thích khác nhau. Trong thư viện thật, nên đặt `select1` và `select0` **trực tiếp trong định nghĩa lớp**.

## 20. Trường hợp biên: n=0, n=64, n=65 và các bit padding

Các lỗi indexing thường nằm đúng tại **ranh giới word**.

### Vector rỗng

```python
empty = IndexedBitVector([])

assert empty.n == 0
assert empty.rank1(0) == 0
assert empty.rank0(0) == 0
assert empty.count1() == 0
assert empty.count0() == 0
assert empty.super_prefix == [0]
```

Không có vị trí hợp lệ cho `select1(1)` hoặc `select0(1)`; phải báo lỗi.

### Đúng 64 bit

```python
all_one = IndexedBitVector([1] * 64)

assert all_one.rank1(0) == 0
assert all_one.rank1(64) == 64
assert all_one.select1(64) == 63
assert all_one.count0() == 0
```

`rank1(64)` phải trả tổng 64, **không** truy cập `words[1]` vì chỉ có một word.

### 65 bit

```python
boundary = IndexedBitVector([0] * 64 + [1])

assert len(boundary.words) == 2
assert boundary.rank1(64) == 0
assert boundary.rank1(65) == 1
assert boundary.select1(1) == 64
assert boundary.select0(64) == 63
```

Word thứ hai có một bit 1 ở offset 0 và **63 bit padding bằng 0**. Nếu `select0` duyệt thẳng tất cả bit 0 của word cuối mà không giới hạn chiều dài logic, nó có thể trả các vị trí 65..127 **không tồn tại**. Lớp đã tránh lỗi bằng cách chỉ tìm trong `[0,n)`.

### Không chấp nhận `rank1(n+1)`

Rank ở cuối `n` là hợp lệ, nhưng `n+1` là ngoài miền. Không tự làm tròn hoặc cố đọc thêm word.

## 21. C++17: triển khai rank và select trên word 64 bit

Đây là một cài đặt độc lập dùng:

- `std::uint64_t` cho word.
- `std::vector<std::uint16_t>` cho tiền tố cục bộ.
- `std::vector<std::size_t>` cho superblock prefix.
- `popcount` thủ công vì `std::popcount` chỉ chuẩn hóa từ C++20.
- `select1` qua `std::lower_bound`; `select0` qua binary search trên `rank0`.

```cpp
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

class IndexedBitVector {
public:
    explicit IndexedBitVector(const std::vector<int>& bits)
        : n_(bits.size()),
          words_(n_ / 64 + (n_ % 64 != 0), std::uint64_t{0}) {
        for (std::size_t i = 0; i < n_; ++i) {
            if (bits[i] != 0 && bits[i] != 1) {
                throw std::invalid_argument("Bit must be 0 or 1");
            }
            if (bits[i] == 1) {
                words_[i / 64] |=
                    (std::uint64_t{1} << (i % 64));
            }
        }

        std::size_t total = 0;
        for (std::size_t wi = 0; wi < words_.size(); ++wi) {
            if (wi % 8 == 0) {
                super_prefix_.push_back(total);
            }

            within_super_.push_back(
                static_cast<std::uint16_t>(
                    total - super_prefix_.back()
                )
            );
            total += popcount(words_[wi]);
        }

        super_prefix_.push_back(total);
        ones_ = total;
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
        const unsigned offset = static_cast<unsigned>(i % 64);

        const std::uint64_t mask = offset == 0
            ? std::uint64_t{0}
            : ((std::uint64_t{1} << offset) - 1);

        return (
            super_prefix_[si]
            + within_super_[wi]
            + popcount(words_[wi] & mask)
        );
    }

    std::size_t rank0(std::size_t i) const {
        return i - rank1(i);
    }

    std::size_t select1(std::size_t k) const {
        if (k == 0 || k > ones_) {
            throw std::out_of_range("select1 rank");
        }

        const auto it = std::lower_bound(
            super_prefix_.begin(), super_prefix_.end(), k
        );
        const std::size_t si =
            static_cast<std::size_t>(
                it - super_prefix_.begin() - 1
            );

        std::size_t remaining = k - super_prefix_[si];
        const std::size_t start = si * 8;
        const std::size_t end =
            std::min(start + 8, words_.size());

        for (std::size_t wi = start; wi < end; ++wi) {
            std::uint64_t word = words_[wi];
            const unsigned count = popcount(word);

            if (remaining > count) {
                remaining -= count;
                continue;
            }

            while (remaining > 1) {
                word &= word - 1;
                --remaining;
            }

            unsigned offset = 0;
            while ((word & 1ULL) == 0) {
                word >>= 1;
                ++offset;
            }

            const std::size_t pos = wi * 64 + offset;
            assert(pos < n_);
            return pos;
        }

        throw std::logic_error("Broken select1 index");
    }

    std::size_t select0(std::size_t k) const {
        if (k == 0 || k > count0()) {
            throw std::out_of_range("select0 rank");
        }

        std::size_t lo = 0;
        std::size_t hi = n_ - 1;

        while (lo < hi) {
            const std::size_t mid = lo + (hi - lo) / 2;
            if (rank0(mid + 1) >= k) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        return lo;
    }

private:
    static unsigned popcount(std::uint64_t word) {
        unsigned result = 0;
        while (word != 0) {
            word &= word - 1;
            ++result;
        }
        return result;
    }

    std::size_t n_;
    std::size_t ones_ = 0;
    std::vector<std::uint64_t> words_;
    std::vector<std::size_t> super_prefix_;
    std::vector<std::uint16_t> within_super_;
};

int main() {
    const std::vector<int> bits = {
        1, 0, 1, 1, 0, 0, 1, 0,
        1, 0, 0, 1, 1, 0, 1, 0,
    };

    const IndexedBitVector bv(bits);

    assert(bv.size() == 16);
    assert(bv.count1() == 8);
    assert(bv.count0() == 8);

    assert(bv.rank1(0) == 0);
    assert(bv.rank1(4) == 3);
    assert(bv.rank1(16) == 8);
    assert(bv.select1(1) == 0);
    assert(bv.select1(5) == 8);
    assert(bv.select1(8) == 14);
    assert(bv.select0(5) == 9);

    const IndexedBitVector zero(std::vector<int>{});
    assert(zero.rank1(0) == 0);

    const IndexedBitVector edge(
        std::vector<int>(64, 1)
    );
    assert(edge.rank1(64) == 64);
    assert(edge.select1(64) == 63);

    std::cout << "rank/select OK\n";
}
```

### C++17 và chi phí popcount

`std::popcount` thuộc **C++20**. Để giữ ví dụ tương thích C++17, ta dùng thuật toán bỏ từng bit 1. Với word 64 bit, số vòng tối đa 64: một hằng số.

Trên compiler phù hợp, có thể thay bằng intrinsic popcount phần cứng để tăng tốc, nhưng phải kiểm tra khả năng biên dịch/nền tảng. Phân tích `O(1)` của rank dựa vào **word cố định**, không dựa vào cú pháp riêng của C++20.

### Chỉ số và overflow

Một cách viết phổ biến là `(n_+63)/64`, nhưng phép cộng có thể overflow về lý thuyết nếu n tiến sát giới hạn `size_t`. Bản cài đặt ở trên **đã dùng công thức không cần cộng tràn**:

```cpp
const std::size_t word_count =
    n_ / 64 + (n_ % 64 != 0);
```

Ngoài ra, cấp phát thực tế sẽ bị giới hạn bởi bộ nhớ và khả năng của allocator trước khi đạt các giá trị cực đại đó. Với dữ liệu nhập không tin cậy, vẫn cần kiểm tra miền kích thước.

## 22. Select0 và lỗi đếm padding

Xét n=65 với:

```text
B[0..63] = 0
B[64] = 1
```

Có 64 bit 0 hợp lệ. Vùng chứa bằng hai word 64 bit:

```text
word 0: 64 bit 0 hợp lệ
word 1: bit 0 là 1, bit 1..63 chỉ là padding
```

Nếu thực hiện:

```text
popcount(~words[1])
```

trên toàn word, sẽ nhận 63 bit 0 từ padding (trên word có bit thấp là 1), dù **không có bit logic nào nữa**.

### Cách xử lý đúng

Một trong hai cách:

1. Khi đếm bit 0 trong word cuối, **mask** chỉ những vị trí `<n`.
2. Tính `rank0(i)=i-rank1(i)` cho `i≤n` và tìm `select0` bằng rank0.

Bài chọn cách 2, tránh tự xây một bộ máy select0 theo word phải xử lý tail padding phức tạp.

Nếu sau này tối ưu select0 ở cấp word, luôn tính số **bit hợp lệ** của word cuối:

\[
valid=\min(64,n-64\,wordIndex).
\]

Chỉ bit trong `[0,valid)` của word được xét.

## 23. So sánh độ phức tạp các chiến lược

Đặt:

- `n`: số bit logic.
- `M=\lceil n/64\rceil`: số word.
- `S=\lceil n/512\rceil`: số superblock.

| Cách tổ chức | rank1 | select1 | Bộ nhớ phụ |
|---|---|---|---|
| Chỉ lưu bit, quét trực tiếp | `O(n)` worst-case | `O(n)` | `O(1)` |
| Mảng prefix tại mọi vị trí | `O(1)` | `O(log n)` qua tìm trên prefix | `\Theta(n\log n)` bit cho mảng số đếm |
| Word + superblock 512 bit như bài | `O(1)` | `O(log(S+1)+1)` | `\Theta(n)` bit với block kích thước cố định |
| Word + superblock, select bằng binary search trên rank | `O(1)` | `O(log(n+1))` | Như trên |
| Chỉ mục succinct tĩnh nâng cao | Có thể `O(1)` | Có thể `O(1)` | `o(n)` bit phụ trong mô hình phù hợp |

Các thời gian tính **sau khi xây chỉ mục**. Xây ban đầu cần đọc toàn bộ n bit nên là `O(n)` trong biểu diễn từng bit đầu vào.

### Vì sao chỉ mục ví dụ vẫn dùng `Θ(n)` bit phụ?

Vì ta dùng superblock cố định 512 bit và một số đếm (16 bit) cho mỗi word 64 bit. Số mục `within_super` tỷ lệ `n/64` và mỗi mục dùng 16 bit hằng số, nên tổng overhead tỷ lệ **n**.

**Đây là kỹ thuật thực tế và dễ cài**, nhưng chưa phải một chứng minh cấu trúc `n+o(n)`. Hai khái niệm cần phân biệt:

- **Compact:** tiết kiệm đáng kể so với mảng Boolean rộng và hỗ trợ truy vấn nhanh.
- **Succinct:** tiệm cận chặn thông tin `n` bit với overhead **nhỏ hơn tuyến tính** trong mô hình và tập truy vấn xác định.

## 24. Làm sao đạt ý tưởng `n+o(n)` bit?

Trong lý thuyết cấu trúc dữ liệu gọn, một bit vector n bit có thể được tăng cường các chỉ mục để hỗ trợ rank và select trong **O(1)** thời gian dưới những giả định word-RAM thích hợp, trong khi tổng dùng:

\[
\boxed{n+o(n)\text{ bit}.}
\]

Điều này không phải hệ quả tự động của lớp Python hay C++ ở trên. Nó cần **thiết kế chỉ mục phân cấp tinh hơn**, bảng tra cứu hoặc cấu trúc select chuyên biệt.

### Phác thảo ý tưởng rank ít overhead

Thay superblock 512 bit cố định bằng:

\[
L=\Theta((\log n)^2)\text{ bit}
\]

và block nhỏ:

\[
b=\Theta(\log n)\text{ bit}.
\]

Lưu:

- Tổng tiền tố tại đầu superblock: khoảng `n/L` mục, mỗi mục dùng `O(\log n)` bit.
- Tổng cục bộ tại đầu block: khoảng `n/b` mục, mỗi mục dùng `O(\log L)=O(\log\log n)` bit.
- Trong block nhỏ: tính popcount/mask nhanh bằng từ máy hoặc bảng tra cứu phù hợp.

Overhead tổng quát:

\[
O\!\left(\frac{n}{\log n}\right)
+
O\!\left(\frac{n\log\log n}{\log n}\right)
=o(n).
\]

Điều quan trọng là **tăng kích thước superblock theo n** chứ không giữ hằng 512 nếu muốn overhead tiệm cận o(n).

### Select cần cấu trúc bổ sung

Select khó hơn vì nó **đi từ số lượng tới vị trí**. Một chỉ mục select O(1) có thể dùng:

- Chia nhóm theo **số lượng bit 1**, thay vì theo số vị trí.
- Lưu mẫu vị trí cho một số lần xuất hiện.
- Xử lý riêng nhóm “dày” và nhóm “thưa”.
- Bảng tra cứu hoặc kỹ thuật predecessor/select bên trong nhóm.

Cần thiết kế và chứng minh riêng để đạt O(1) với o(n) bit phụ. **Không được kết luận** rằng chỉ vì rank đạt O(1) thì select cũng đạt O(1) mà không cần chỉ mục thích hợp.

### Giới hạn mô hình

Độ phức tạp O(1) ở đây dựa trên mô hình word-RAM, từ máy đủ lớn để đánh địa chỉ dữ liệu và các phép bitwise/tra cứu theo kích thước đã chọn. Kết quả lý thuyết không phải cam kết tốc độ tuyệt đối trên mọi ngôn ngữ, compiler và kiến trúc.

## 25. Cấu trúc đã có rank có thể xây select bằng binary search

Khi không cần tốc độ select cực cao, chiến lược đơn giản là:

1. Xây chỉ mục rank O(1).
2. Với truy vấn `select1(k)`, tìm vị trí nhỏ nhất p sao cho `rank1(p+1)≥k`.
3. Trả về p.

Tính đơn điệu của rank bảo đảm binary search đúng:

```text
Nếu rank1(mid+1) < k:
    bit thứ k phải nằm sau mid.
Ngược lại:
    bit thứ k ở mid hoặc trước đó.
```

Với k hợp lệ, vị trí tìm được nhất thiết chứa bit 1. Nếu `B[p]=0` thì `rank1(p+1)=rank1(p)`, nên p không thể là vị trí đầu tiên làm rank đạt k.

### Khi nào nên chọn cách này?

- Chủ yếu truy vấn rank; select hiếm.
- Dữ liệu không quá lớn.
- Muốn cài đơn giản và dễ kiểm thử.
- Không muốn dành thêm bộ nhớ cho chỉ mục select.
- Độ trễ `O(log n)` vẫn đạt yêu cầu.

Nếu ứng dụng hỏi select liên tục, có thể thêm chỉ mục chuyên dụng sau khi benchmark và đo tradeoff thực tế.

## 26. Cập nhật bit khiến chỉ mục rank/select bị cũ

Đến đây, mọi lớp triển khai đều coi bit vector là **tĩnh** sau khi xây.

Giả sử thay `B[p]` từ 0 thành 1. Khi đó:

- `rank1(i)` **không đổi** với `i≤p`.
- `rank1(i)` **tăng 1** với `i>p`.
- Tổng số bit 1 tăng 1.
- Vị trí của các bit thứ k có thể thay đổi theo k.
- Mọi `super_prefix` của những superblock sau p có thể cần cập nhật.
- Các tổng cục bộ của các word tiếp theo trong cùng superblock có thể thay đổi.

Vì vậy sửa bit trong `words` mà **không sửa directory** khiến rank/select trả sai.

### Giá cập nhật với chỉ mục tĩnh của bài

Nếu cập nhật tại word wi:

- Thay đổi word bằng XOR/OR/AND mask tốn O(1).
- Sửa vài mục `within_super` sau wi trong superblock hiện tại: tối đa 7 word khác.
- Sửa các mốc `super_prefix` phía sau superblock hiện tại: có thể `O(S)`.

Do đó cập nhật theo cách trực tiếp trên directory này có worst-case **`O(S)`**, tức `O(n/512)` với kích thước superblock cố định.

**Không được quảng cáo cấu trúc là rank O(1), select nhanh và update O(1) cùng lúc** nếu chưa có thiết kế cập nhật tương ứng.

## 27. Một hướng cho bit vector động: Fenwick trên số bit 1 mỗi word

Nếu ứng dụng cần **flip/set bit thường xuyên**, có thể thay mảng tổng superblock tĩnh bằng **Fenwick tree (Binary Indexed Tree)** trên số bit 1 của mỗi word.

Mỗi word có:

\[
count[w]=popcount(words[w]).
\]

Fenwick lưu các tổng của dãy `count`.

Khi flip một bit:

1. Sửa đúng bit trong word.
2. Số bit 1 của word thay đổi `\Delta=+1` hoặc `−1`.
3. Cập nhật Fenwick ở vị trí word tương ứng.

Khi hỏi rank:

1. Dùng Fenwick lấy tổng bit 1 của **những word đứng trước**.
2. Cộng popcount của phần word hiện tại trước i.

### Độ phức tạp

Với M word:

| Thao tác | Chặn thời gian |
|---|---|
| Flip một bit | `O(\log(M+1))` |
| rank1 | `O(\log(M+1))` |
| select1 với tìm thứ k qua Fenwick | `O(\log(M+1))` nếu có phép tìm theo tổng |
| Truy cập bit | `O(1)` |
| Bộ nhớ ngoài word | `O(M)` số đếm |

Fenwick không giữ rank O(1) như directory tĩnh nhưng hỗ trợ cập nhật hiệu quả hơn. Với nhu cầu **chèn/xóa bit làm thay đổi chiều dài và dịch vị trí**, Fenwick theo các word cố định chưa đủ; cần cấu trúc bit vector động phức tạp hơn, ví dụ cây lưu block và tổng.

### Không phải mọi cập nhật giống nhau

- **Set/clear/flip tại vị trí hiện có:** thay một bit, n không đổi.
- **Insert/delete một bit:** thay đổi thứ tự/vị trí của các bit phía sau, n thay đổi; cấu trúc vector nguyên khối có thể phải dịch lượng lớn dữ liệu.

Hãy xác định rõ bài toán trước khi chọn chỉ mục.

## 28. Rank và select trong bitmap index

Giả sử một cột dữ liệu có n bản ghi và bit vector B đánh dấu các bản ghi thỏa điều kiện:

```text
B[i] = 1 nếu bản ghi i có trạng thái "active".
```

Khi đó:

- `rank1(i)` trả số bản ghi active **trước** bản ghi i.
- `select1(k)` trả vị trí bản ghi active thứ k.
- `rank1(n)` trả tổng số bản ghi active.

Một ánh xạ giữa **chỉ số bản ghi gốc** và **chỉ số dày của tập active** có thể dùng rank/select:

```text
B[i] == 1:
    thứ tự active của bản ghi i (đếm từ 1)
    = rank1(i+1)

thứ tự active k:
    vị trí bản ghi gốc = select1(k)
```

Ví dụ vector 16 bit đầu bài có 8 bản ghi active. Bản ghi tại vị trí 11 là active thứ:

\[
rank1(12)=6.
\]

Ngược lại active thứ 6 nằm ở:

\[
select1(6)=11.
\]

### Bitset vẫn có thể cần thêm cấu trúc

Nếu chỉ lọc bằng AND/OR giữa các điều kiện, word bitwise là đủ. Nhưng nếu cần **truy xuất bản ghi active thứ k nhanh**, select mới trở nên quan trọng.

Vì vậy phải thiết kế chỉ mục theo **loại truy vấn** thực tế, không chỉ theo số bit dùng để lưu trạng thái.

## 29. Rank/select trong cây và chuỗi nén

Các cấu trúc dữ liệu gọn tận dụng rank/select như thao tác điều hướng cơ sở.

### Cây nhị phân và ký hiệu bit

Một cách biểu diễn cây có thể dùng dãy bit đánh dấu:

- Nút có con hoặc không.
- Vị trí ranh giới giữa các danh sách con.
- Ngoặc mở/đóng trong biểu diễn ngoặc cân bằng.

Rank/select giúp chuyển từ **vị trí trên chuỗi bit** sang **thứ tự nút, thứ tự ngoặc hoặc ranh giới danh sách**. Tuy nhiên công thức điều hướng cụ thể phụ thuộc **đúng kiểu mã hóa cây**; không có một công thức rank/select chung đủ cho mọi cách mã hóa.

### Wavelet tree

Trong một wavelet tree, mỗi nút lưu bit vector chỉ ra ký hiệu đi sang nhánh trái hay phải. Rank trên bit vector giúp ánh xạ vị trí của ký hiệu từ dãy ở nút cha xuống dãy ở nút con.

Select được dùng để đi ngược ánh xạ vị trí từ nút con về cha. Kết quả là một cấu trúc hỗ trợ truy vấn trên chuỗi, ví dụ:

- Đếm số lần xuất hiện của ký hiệu trong tiền tố.
- Tìm lần xuất hiện thứ k.
- Truy vấn thứ tự/quantile theo thiết kế.

**Độ phức tạp toàn wavelet tree còn phụ thuộc chiều cao cây và bảng chữ cái**, không chỉ chi phí rank/select trên một bit vector.

### Chuỗi ký tự và chỉ mục nén

Trong một số chỉ mục văn bản nén, bit vector đánh dấu ranh giới hoặc hỗ trợ ánh xạ giữa các mức biểu diễn. Rank/select giúp giảm nhu cầu lưu danh sách offset dạng số nguyên rộng.

Lợi ích là tiết kiệm bộ nhớ, nhưng các index có thể phải đánh đổi nhiều bước rank/select cho một truy vấn mức cao.

## 30. Bit vector thưa: có cần lưu đủ n bit?

Nếu chỉ có m bit 1 và m rất nhỏ so với n, một bit vector n bit có thể chưa phải lựa chọn gọn nhất.

Số cách đặt đúng m bit 1 trong n vị trí là:

\[
\binom nm.
\]

Nếu biết chắc tổng bit 1 bằng m, chặn thông tin của mã cố định cho trạng thái này là:

\[
\boxed{
\left\lceil\log_2\binom nm\right\rceil\text{ bit}.
}
\]

Khi `m\ll n`, nó có thể nhỏ hơn n rất nhiều.

### Lưu danh sách vị trí bit 1

Một phương án:

```text
positions = [0, 2, 3, 6, 8, 11, 12, 14]
```

Với m vị trí, mỗi vị trí lưu bằng `\lceil\log_2 n\rceil` bit, cần khoảng:

\[
m\lceil\log_2n\rceil
\]

bit payload trước khi nén chênh lệch, cộng metadata.

Nếu m rất nhỏ, cách này có thể tiết kiệm hơn n bit. Nhưng:

- `rank1(i)` cần tìm vị trí chèn trong danh sách, ví dụ binary search `O(\log m)`.
- `select1(k)` chỉ cần lấy phần tử thứ k trong danh sách, `O(1)` nếu mảng truy cập ngẫu nhiên.
- `rank0` vẫn tính bằng `i-rank1(i)`.
- `select0` cần kỹ thuật khác.

Các cấu trúc bit vector thưa như **Elias–Fano** cho dãy số nguyên tăng có thể giúp lưu danh sách vị trí gọn và hỗ trợ các phép truy vấn nhất định, nhưng hiệu năng/tính năng phụ thuộc biến thể.

**Không có một biểu diễn luôn tối ưu** cho cả vector dày và vector cực thưa.

## 31. Bài toán dữ liệu tĩnh và dữ liệu động

Cần phân biệt:

- **Static bit vector:** xây một lần, sau đó chỉ đọc.
- **Point-update bit vector:** cho phép set/clear/flip các bit tại vị trí hiện có.
- **Dynamic bit vector:** cho phép cả chèn/xóa bit, làm thay đổi chiều dài và thứ tự.
- **Persistent bit vector:** giữ hoặc truy vấn nhiều phiên bản, với mô hình lưu khác.

### Chỉ số static

Superblock directory đã trình bày là lựa chọn mạnh cho dữ liệu tĩnh:

- Xây `O(n)`.
- Rank nhanh.
- Select có thể thêm chỉ mục.
- Lưu trữ có thể được đóng gói tối ưu.

### Point update

Có thể dùng Fenwick hoặc segment tree trên các tổng popcount theo word. Rank và select sẽ phụ thuộc thêm vào chiều cao chỉ mục, nhưng cập nhật không cần sửa mọi prefix sau vị trí.

### Insert/delete

Chèn hoặc xóa một bit tại vị trí giữa có thể làm thay đổi cách chia word, superblock và offset của tất cả phần tử sau. Cấu trúc hỗ trợ chèn/xóa hiệu quả cần quản lý block bằng cây hoặc một thiết kế dynamic bit vector phù hợp, không chỉ thêm một hàm `insert` vào mảng word tĩnh.

## 32. Đánh đổi giữa rank nhanh, select nhanh và bộ nhớ

Có ba kiểu workload điển hình.

### Chủ yếu truy vấn rank

Nếu hệ thống thường hỏi `rank1(i)` nhưng hiếm khi hỏi select:

- Word + superblock là thiết kế đơn giản.
- Có thể dùng binary search trên rank khi select hiếm.
- Không cần dành nhiều bộ nhớ cho chỉ mục select.

### Chủ yếu truy vấn select

Nếu hệ thống thường hỏi bit 1 thứ k:

- Có thể lưu trực tiếp danh sách vị trí bit 1 khi số bit 1 ít.
- Với vector dày, dùng chỉ mục select chuyên dụng.
- Có thể lấy mẫu vị trí theo thứ tự bit 1 để giảm phạm vi tìm kiếm.

### Truy vấn cân bằng và dữ liệu rất lớn

Nếu cả rank/select đều thường xuyên và n lớn:

- Đo tổng số byte của vector + index.
- Quan tâm tới kích thước cache và độ trễ bộ nhớ.
- Cân nhắc cấu trúc succinct tĩnh có bảo đảm phù hợp.
- Benchmark trên phân phối dày/thưa, bit tập trung thành cụm hoặc xen kẽ.

### Một vài đánh đổi

| Thiết kế | Ưu tiên | Nhược điểm |
|---|---|---|
| Word thuần | Bộ nhớ payload | Rank/select quét chậm |
| Word + directory rank | Rank nhanh | Select cần tìm thêm |
| Word + rank + select index | Cả hai truy vấn nhanh | Overhead và xây chỉ mục |
| Danh sách vị trí bit 1 | Vector thưa, select1 nhanh | Rank bằng tìm kiếm; select0 khó |
| Fenwick trên word | Point update nhanh hơn prefix tĩnh | Rank/select `O(\log n)` |
| Succinct static bit vector | Gần chặn thông tin + truy vấn nhanh | Cài đặt/chứng minh phức tạp |

## 33. Đo bộ nhớ đúng cách

Đối với bit vector, cần tách:

1. **Bit logic:** n.
2. **Word payload:** `64\lceil n/64\rceil` bit.
3. **Rank index:** superprefix và within-super.
4. **Select index:** nếu có.
5. **Metadata:** n, total_ones, length/capacity, con trỏ.
6. **Allocator/container overhead.**
7. **Bộ nhớ tạm khi xây dựng index.**

### Ví dụ trong Python

```python
import sys

n = 1_000_000
bits = [0] * n

# Đây chỉ là kích thước nông của list, chưa tính
# toàn bộ đối tượng được tham chiếu.
print(sys.getsizeof(bits))

# Một bytearray chứa bit đã đóng gói có payload 125000 B.
packed_bytes = bytearray((n + 7) // 8)
print(len(packed_bytes))
print(sys.getsizeof(packed_bytes))
```

Một `list[int]` với một triệu tham chiếu tốn nhiều RAM hơn vector bit được đóng gói; lớp ví dụ `IndexedBitVector` cũng sử dụng các `list[int]` để giữ word và prefix, nên không thể đồng nhất tổng bộ nhớ Python của nó với bảng kiểu cố định đã tính.

### Khi đo C++

`sizeof(IndexedBitVector)` chỉ đo các trường nằm trực tiếp trong object, **không cộng vùng heap** của vector word/index.

Muốn ước lượng số byte đã cấp cho các phần tử vector, xét:

```text
capacity() * sizeof(element_type)
```

cho từng vector, rồi cộng allocator overhead khi cần chính xác hơn. Nếu muốn đo **cả tiến trình**, dùng profiler/heap measurement cùng một workload.

### Đừng bỏ qua peak memory

Khi xây index, chương trình có thể cùng lúc giữ:

- Dãy đầu vào chưa đóng gói.
- Word đã đóng gói.
- Directory rank.
- Directory select.
- Buffer tạm hoặc bảng tra cứu.

Bộ nhớ cao nhất trong quá trình xây dựng có thể cao hơn đáng kể cấu trúc cuối. Điều này quan trọng khi xử lý dữ liệu hàng tỷ bit.

## 34. Benchmark đúng các truy vấn rank/select

Một benchmark có ý nghĩa nên dùng nhiều dạng bit vector:

- **Toàn 0**.
- **Toàn 1**.
- **Luân phiên `010101...`**.
- **Dày**: tỷ lệ bit 1 cao.
- **Thưa**: rất ít bit 1.
- **Tập trung thành cụm**: nhiều đoạn dài toàn 0/toàn 1.
- **Ngẫu nhiên có seed cố định**.
- **Độ dài sát mốc** 63, 64, 65, 511, 512, 513.

Các truy vấn cũng nên có phân phối:

- `rank1(0)` và `rank1(n)`.
- Rank gần đầu, giữa, cuối.
- Select bit đầu tiên và bit cuối cùng.
- Select vào superblock rỗng/trống kế tiếp.
- Select0 gần các bit padding ở word cuối.

### Cần đo những gì?

- **Thời gian xây index**.
- **Throughput và p95/p99 latency** của rank/select nếu phù hợp.
- **Tổng RAM và peak RAM**.
- **Độ trễ cập nhật** nếu dùng bản động.
- **Kích thước dữ liệu thực** với mật độ khác nhau.

Đặc biệt, một cấu trúc dùng ít bit hơn chưa chắc nhanh hơn: vài lần truy cập chỉ mục phân tán trong RAM có thể đắt hơn một phép quét word liên tục nếu dữ liệu nhỏ và đã nằm trong cache.

## 35. Kiểm thử đúng đắn bằng mô hình tham chiếu chậm

Với n nhỏ, cách đơn giản nhất là đối chiếu với danh sách bit thuần.

```python
def slow_rank1(bits, i):
    return sum(bits[:i])


def slow_select(bits, target_bit, k):
    positions = [
        i for i, value in enumerate(bits)
        if value == target_bit
    ]
    if not 1 <= k <= len(positions):
        raise IndexError
    return positions[k - 1]


def verify(bits):
    bv = IndexedBitVector(bits)

    for i in range(len(bits) + 1):
        assert bv.rank1(i) == slow_rank1(bits, i)
        assert bv.rank0(i) == i - slow_rank1(bits, i)

    for k in range(1, bv.count1() + 1):
        assert bv.select1(k) == slow_select(bits, 1, k)

    for k in range(1, bv.count0() + 1):
        assert bv.select0(k) == slow_select(bits, 0, k)


verify([])
verify([0] * 65)
verify([1] * 64)
verify([0] * 64 + [1])
verify([1, 0] * 32 + [1])
verify([0] * 512 + [1])
verify([1] * 512 + [0] * 512 + [1])
```

### Vì sao những ca này quan trọng?

- `[]` kiểm tra không truy cập word/superblock không tồn tại.
- `65 bit` kiểm tra padding ở word thứ hai.
- `64 bit` kiểm tra `rank1(n)` tại ranh giới word.
- `512` và `513` kiểm tra ranh giới superblock.
- Superblock toàn 0 khiến `super_prefix` có nhiều mục bằng nhau; `select1` phải bỏ qua đúng.
- Select0 phải bỏ qua bit padding.

### Thuộc tính nên kiểm thử thêm

Với mọi i trong `[0,n)`:

\[
rank1(i+1)-rank1(i)=B[i].
\]

Với mọi k hợp lệ:

\[
rank1(select1(k)+1)=k.
\]

Với mọi i trong `[0,n]`:

\[
rank1(i)+rank0(i)=i.
\]

Những thuộc tính này đặc biệt hữu ích trong kiểm thử sinh ngẫu nhiên hoặc property-based testing.

## 36. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Không nêu rank tiền tố đóng/mở | Lệch một ở mọi truy vấn | Dùng rõ `rank1(i)` trên `[0,i)` |
| Nhầm k của select từ 0 với từ 1 | Trả sai vị trí | Chọn quy ước và kiểm thử |
| Cho `select1(0)` trả 0 | Lẫn chỉ số 0 hợp lệ | Báo lỗi ngoài miền |
| Quên `rank1(0)=0` | Sai biên đầu | Tổng rỗng bằng 0 |
| Quên `rank1(n)=total_ones` | Vượt word khi n chia hết cho 64 | Xử lý n riêng |
| Dịch `1ULL<<64` | Dịch vượt độ rộng C++ | Chỉ dịch 0..63, có nhánh t=64 |
| Không mask word cuối khi đếm 0 | Đếm padding thành bit 0 | Giới hạn `i≤n` hoặc mask valid bits |
| Đọc `within_super` như tổng toàn vector | Cộng thiếu/thừa superblock | Dùng đúng super_prefix + local + partial |
| Không reset local prefix khi sang superblock mới | Đếm lặp các word cũ | Reset từ 0 mỗi 8 word |
| Cho `select1` dùng prefix trùng không xử lý | Chọn nhầm superblock rỗng | Lower bound đúng điều kiện |
| Không kiểm tra k hợp lệ | Bit thấp nhất có thể bằng 0 và vòng lặp sai | Chỉ cho `1≤k≤count` |
| Dùng binary search trên bit `B[i]` thay vì rank | Bit vector không được sắp xếp | Binary search trên tổng không giảm |
| Sửa bit nhưng quên sửa index | Rank/select sai sau update | Dùng bản tĩnh hoặc index động |
| Tuyên bố select O(1) chỉ vì rank O(1) | Sai độ phức tạp | Phân tích tìm kiếm/chỉ mục select riêng |
| Gọi fixed 512-bit directory là `n+o(n)` | Overhead Θ(n) bit | Dùng tham số tăng theo n và cấu trúc succinct |
| Chỉ tính payload word | Đánh giá thấp RAM | Cộng directory, container, capacity |
| Coi `list[int]` Python là mảng uint64 nén | Overhead Python rất khác | Dùng kiểu mảng cố định nếu cần |
| Dùng bit position với byte order không khai báo | File không portable | Định nghĩa serialization |
| Coi điểm chèn/xóa bit như set/clear | Dịch vị trí toàn suffix | Chọn dynamic bit vector |
| Không test toàn 0/toàn 1 | Select ngoài miền bị bỏ sót | Kiểm thử hai cực trị |
| Không test độ dài 64, 512 | Dễ sai ranh giới block | Thêm trường hợp chính xác bội word |
| Không kiểm tra input bit ngoài 0/1 | Mã hóa trạng thái không hợp lệ | Xác thực input |

## 37. Quy trình lựa chọn cấu trúc bit vector

Khi có một bài toán mà dữ liệu chủ yếu là các cờ nhị phân, hãy trả lời lần lượt:

1. **Có n bao nhiêu?** Độ dài cố định hay thay đổi?
2. **Mật độ bit 1 thế nào?** Dày, thưa hay thành cụm?
3. **Truy vấn chủ yếu là gì?** `B[i]`, rank, select, AND/OR, predecessor/successor?
4. **Có cập nhật không?** Chỉ set/clear hay cả insert/delete?
5. **Mục tiêu độ trễ?** Rank O(1) có đủ, select O(log n) chấp nhận được không?
6. **Ngân sách bộ nhớ?** Có chấp nhận overhead directory 20–40% payload hay cần cấu trúc succinct hơn?
7. **Mô hình môi trường?** Python object, C++ array, memory-mapped file, GPU?
8. **Có cần serialize?** Quy định byte/bit order và count.
9. **Có kiểm thử biên?** 0, 1, 63/64/65, 511/512/513, toàn 0/toàn 1.
10. **Có benchmark trên workload thật?** Tính cả build, RAM, latency và peak.

### Chọn nhanh theo mục tiêu

- **Chỉ cần truy cập bit và phép toán hàng loạt:** bitset/word array là đủ.
- **Dữ liệu tĩnh và nhiều rank:** word + superblock index là điểm khởi đầu tốt.
- **Dữ liệu tĩnh và nhiều select:** thêm select index hoặc xem cấu trúc succinct chuyên dụng.
- **Vector rất thưa:** cân nhắc danh sách vị trí/Elias–Fano.
- **Cập nhật một bit thường xuyên:** Fenwick/segment tree trên số bit 1 của word.
- **Chèn/xóa giữa dãy:** cần dynamic bit vector có cơ chế quản lý block.

## 38. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một bit vector n phần tử độc lập có bao nhiêu cấu hình?

**Đáp án:** `2^n` cấu hình; cần n bit thông tin cho mã cố định nếu n đã biết.

**Câu 2.** Bài quy định `rank1(i)` tính trên đoạn nào?

**Đáp án:** Đoạn tiền tố **`[0,i)`**, không gồm `B[i]`.

**Câu 3.** `rank1(0)` bằng bao nhiêu?

**Đáp án:** Bằng **0**, vì tiền tố rỗng.

**Câu 4.** Nếu vector có 8 bit 1, `rank1(n)` bằng gì?

**Đáp án:** **8**, vì toàn bộ n bit đã được xét.

**Câu 5.** `rank0(i)` tính từ `rank1(i)` như thế nào?

**Đáp án:** `rank0(i)=i-rank1(i)`.

**Câu 6.** Bài định nghĩa `select1(k)` với k bắt đầu từ mấy?

**Đáp án:** **k bắt đầu từ 1**; kết quả là **chỉ số vị trí bắt đầu từ 0**.

**Câu 7.** Với `B=[1,0,1,1,0,0,1,0]`, `rank1(4)` bằng bao nhiêu?

**Đáp án:** **3**, vì có bit 1 ở vị trí 0, 2, 3 trước vị trí 4.

**Câu 8.** Cùng B ở câu 7, `select1(4)` bằng gì?

**Đáp án:** **6**, là vị trí bit 1 thứ tư.

**Câu 9.** Cùng B, `select0(2)` bằng gì?

**Đáp án:** **4**, vì các bit 0 ở vị trí 1, 4, 5, 7.

**Câu 10.** Nếu `p=select1(k)`, quan hệ đúng của `rank1(p+1)` là gì?

**Đáp án:** `rank1(p+1)=k`.

**Câu 11.** Nếu `p=select1(k)`, `rank1(p)` bằng gì?

**Đáp án:** `k-1` vì bit tại p chưa được tính.

**Câu 12.** Muốn tìm bit 1 đầu tiên tại hoặc sau vị trí i, có thể dùng công thức nào?

**Đáp án:** `select1(rank1(i)+1)` nếu có đủ bit 1.

**Câu 13.** Một vector dài 130 bit cần bao nhiêu word 64 bit?

**Đáp án:** `\lceil130/64\rceil=3` word, vùng word 24 byte.

**Câu 14.** 130 bit logic có bao nhiêu bit padding nếu dùng 3 word 64 bit?

**Đáp án:** `192-130=62` bit padding.

**Câu 15.** Vì sao `popcount(word & mask)` hữu ích cho rank?

**Đáp án:** Nó đếm bit 1 chỉ trong phần word nằm trước vị trí cần hỏi.

**Câu 16.** Với `word=0b10110100`, popcount của word bằng bao nhiêu?

**Đáp án:** **4**.

**Câu 17.** Với word câu 16 và t=5, popcount của 5 bit thấp bằng bao nhiêu?

**Đáp án:** `0b10110100 & 0b00011111=0b00010100` có **2** bit 1.

**Câu 18.** Một superblock của bài dài bao nhiêu bit và có bao nhiêu word?

**Đáp án:** **512 bit**, gồm **8 word 64 bit**.

**Câu 19.** `super_prefix[s]` lưu gì?

**Đáp án:** Số bit 1 **trước superblock s**.

**Câu 20.** `within_super[w]` lưu gì?

**Đáp án:** Số bit 1 trong những word đứng trước w **trong cùng superblock**.

**Câu 21.** Vì sao rank1 là O(1) sau khi xây chỉ mục của bài?

**Đáp án:** Chỉ cần đọc vài tổng, một word và popcount một mask 64 bit, với số phép toán bị chặn hằng trong mô hình từ máy cố định.

**Câu 22.** `select1(k)` qua tìm superblock có chặn nào với S superblock?

**Đáp án:** `O(\log(S+1)+1)` vì binary search trên các tổng superblock rồi quét tối đa 8 word và chọn bit trong word 64 bit.

**Câu 23.** Vì sao `select1(k)` không đương nhiên O(1) chỉ vì rank1 O(1)?

**Đáp án:** Select phải **tìm vị trí** ứng với số thứ tự k; nếu thiếu index select O(1), vẫn cần tìm kiếm.

**Câu 24.** Với vector dài đúng 64 bit và toàn 1, `rank1(64)` bằng gì?

**Đáp án:** **64**, phải xử lý i=n thay vì truy cập word kế tiếp.

**Câu 25.** Với 65 bit gồm 64 bit 0 và bit cuối 1, `select0(64)` bằng gì?

**Đáp án:** **63**. Những bit 0 trong phần padding của word thứ hai không được tính.

**Câu 26.** Khi `super_prefix=[0,4,4,4,9]`, bit 1 thứ 5 thuộc superblock nào?

**Đáp án:** **Superblock 3** (đánh số từ 0). Superblock 1 và 2 không có bit 1.

**Câu 27.** Mảng tổng tiền tố cho từng vị trí dùng bao nhiêu bit phụ nếu mỗi tổng cần `Θ(log n)` bit?

**Đáp án:** `Θ(n\log n)` bit phụ, quá lớn so với n bit payload.

**Câu 28.** Directory cố định 512/64 bit của bài có đạt `n+o(n)` bit không?

**Đáp án:** **Chưa**; với các số đếm cố định cho mỗi word, overhead phụ là `Θ(n)` bit.

**Câu 29.** Ý tưởng tăng superblock lên `Θ(log²n)` và dùng block `Θ(log n)` nhằm mục tiêu gì?

**Đáp án:** Giảm tổng các số đếm phụ xuống `o(n)` bit, đồng thời vẫn hỗ trợ rank nhanh theo thiết kế phù hợp.

**Câu 30.** Vì sao chỉ sửa `words` mà không sửa superprefix sau khi flip một bit là sai?

**Đáp án:** Các tổng tiền tố đứng sau vị trí ấy sẽ bị cũ, nên rank và select không phản ánh vector mới.

**Câu 31.** Fenwick trên số bit 1 của từng word hỗ trợ point update trong bao lâu?

**Đáp án:** `O(\log(M+1))` với M là số word.

**Câu 32.** Trong bitmap đánh dấu bản ghi active, `rank1(i+1)` cho bản ghi i đang active có nghĩa gì?

**Đáp án:** Thứ tự **đếm từ 1** của bản ghi active đó trong toàn bộ các bản ghi từ đầu tới i.

**Câu 33.** Với vector rất thưa, vì sao lưu danh sách vị trí bit 1 có thể tốt?

**Đáp án:** Chỉ cần lưu m vị trí thay vì n bit khi `m\ll n`, nhưng rank và select0 cần cách xử lý riêng.

**Câu 34.** Làm sao tìm các vị trí bit 1 khi cần kiểm thử select?

**Đáp án:** Dùng mô hình tham chiếu chậm `[i for i,b in enumerate(bits) if b==1]` rồi so `select1(k)` với mục thứ `k−1` trong danh sách.

**Câu 35.** Vì sao nên benchmark cả mật độ dày, thưa và dữ liệu thành cụm?

**Đáp án:** Phân phối bit ảnh hưởng tới số word rỗng, phạm vi tìm kiếm, hành vi cache, branch và hiệu quả chọn cấu trúc.

## Ghi nhớ

- **Bit vector** biểu diễn n Boolean bằng n bit logic; vùng word có thể có padding. Các bit padding **không thuộc vector** và không được tính vào rank0/select0.
- Trong bài, **`rank1(i)` đếm trên `[0,i)`**, còn **`select1(k)` trả vị trí bit 1 thứ k với k bắt đầu từ 1**. Bởi vậy `rank1(select1(k)+1)=k`.
- **Rank0 không cần index riêng:** `rank0(i)=i-rank1(i)`.
- Với **word 64 bit**, popcount và mask đếm nhanh những bit nằm trong một word. Kết hợp **superblock 512 bit + prefix trong từng word** cho phép `rank1` **O(1)** sau khi xây chỉ mục trong mô hình word-RAM cố định.
- **Select cần tìm vị trí**, không tự O(1) chỉ vì rank O(1). Mẫu của bài tìm superblock bằng binary search, rồi chọn bit trong tối đa 8 word: `O(log(S+1)+1)`. Select0 mẫu dùng binary search trên rank0: `O(log(n+1))`.
- **n+o(n) bit** là mục tiêu của cấu trúc succinct. Directory 512/64 bit cố định của bài dùng **Θ(n) bit phụ**; muốn đạt o(n) phải thiết kế phân cấp tăng theo n và một index select phù hợp.
- **Truy vấn tĩnh và cập nhật động khác nhau.** Flip một bit làm các tổng prefix phía sau thay đổi; dùng Fenwick/segment tree hoặc dynamic bit vector nếu cần cập nhật thường xuyên.
- **Lựa chọn cuối cùng phụ thuộc workload:** tỷ lệ rank/select, mật độ bit 1, truy cập ngẫu nhiên, cập nhật, yêu cầu thời gian, chi phí chỉ mục và peak memory. Một vector bit tốt phải tiết kiệm bộ nhớ **mà vẫn giữ những thao tác cần thiết đủ nhanh và đúng ở mọi ranh giới**.
