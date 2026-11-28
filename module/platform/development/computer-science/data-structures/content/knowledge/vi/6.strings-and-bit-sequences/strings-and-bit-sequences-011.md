# Đánh đổi của bitset khi miền giá trị dày hoặc thưa

Một hệ thống đánh dấu những đối tượng đã xử lý có thể dùng **bitset**: mỗi ID thuộc một miền số nguyên ứng với một bit, bật nếu đối tượng nằm trong tập. Khi có một triệu ID liên tiếp, bitset chỉ cần khoảng 125 KB dữ liệu. Nhưng nếu chỉ có 100 ID xuất hiện trong miền từ 0 đến 999.999.999, một bitset dày đặc vẫn cần khoảng 125 MB để giữ 100 trạng thái bật. Trong tình huống sau, một tập băm, danh sách ID có thứ tự hoặc bitmap nén có thể phù hợp hơn.

Bài thuộc chương **Chuỗi và dãy bit** của học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là so sánh **bitset dày đặc (dense bitset)** với **biểu diễn tập thưa (sparse set)** bằng bất biến, cách tổ chức bộ nhớ và độ phức tạp; hiểu các điểm hòa vốn tương đối và biết lựa chọn cấu trúc dữ liệu theo cách sử dụng, giống như khi lựa chọn mảng, danh sách liên kết, bảng băm, cây, heap hoặc đồ thị.

## 1. Miền giá trị, số phần tử và mật độ là ba đại lượng khác nhau

Giả sử mọi phần tử có ID số nguyên không âm trong miền:

\[
U=\{0,1,\ldots,n-1\}.
\]

Một tập con `S ⊆ U` chứa đúng `k` phần tử. Ta định nghĩa **mật độ** của tập trên miền:

\[
d=\frac{k}{n},\qquad n>0.
\]

- `n`: kích thước **toàn bộ miền chỉ số**.
- `k`: số **ID thực sự có trong tập** (số bit 1).
- `d`: tỷ lệ vị trí có bit 1; `0 ≤ d ≤ 1`.

Ví dụ:

| Miền `n` | Số phần tử `k` | Mật độ `d` | Nhận xét |
|---:|---:|---:|---|
| 64 | 60 | 93,75% | Tập rất dày trên miền nhỏ |
| 1.000 | 500 | 50% | Nhiều phần tử được bật |
| 1.000.000 | 100.000 | 10% | Đáng cân nhắc bitmap trực tiếp |
| 1.000.000 | 100 | 0,01% | Tập rất thưa trên miền vừa |
| 1.000.000.000 | 100 | 0,00001% | Tập cực thưa trên miền lớn |

Cần phân biệt **dữ liệu được biểu diễn bằng bitset dày đặc** với **tập phần tử có mật độ cao**. Một bitset dày đặc *luôn* dự trữ vị trí cho toàn miền, dù mọi bit đều bằng 0. Ngược lại, một tập thưa cũng có thể được lưu bằng bitset; nó chỉ là lựa chọn chưa chắc kinh tế.

Nếu `n=0`, miền rỗng và chỉ có tập rỗng; tỷ lệ `k/n` không xác định, nên hãy xử lý riêng thay vì chia cho 0.

### Ví dụ bitset và tập ID

```text
Miền:        U = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15}
Tập S:       {1,4,9,15}

Bit logic:   0 1 0 0 1 0 0 0 0 1 0 0 0 0 0 1
              └──────── 16 vị trí ─────────┘

Bitset theo byte, bit 0 là bit thấp nhất:
byte 0 = 00010010 = 0x12
byte 1 = 10000010 = 0x82

Biểu diễn tập thưa:
indices = [1,4,9,15]
```

Hai biểu diễn chứa **cùng thông tin logic**. Sự khác biệt là một bên giữ trạng thái của mọi vị trí trong miền, bên kia giữ danh sách phần tử đang có.

## 2. Bitset dày đặc: đổi bộ nhớ theo miền lấy truy cập trực tiếp

Một bitset dày đặc có độ dài logic `n` được lưu trong các từ máy rộng `w` bit:

\[
q=\left\lceil\frac{n}{w}\right\rceil
\]

từ dữ liệu. Với `w=64`, một mảng `uint64_t` chứa `q` từ, mỗi từ chiếm 8 byte:

\[
M_{\mathrm{dense}}=8\left\lceil\frac{n}{64}\right\rceil\ \text{byte dữ liệu}.
\]

Nếu đóng gói theo byte:

\[
M_{\mathrm{byte}}=\left\lceil\frac{n}{8}\right\rceil\ \text{byte dữ liệu}.
\]

Hai công thức có lượng **padding cuối** khác nhau, nhưng khi `n` lớn đều gần `n/8` byte. Chúng chưa tính bộ nhớ chứa `n`, con trỏ, metadata, vùng cấp phát dự phòng hoặc overhead của ngôn ngữ.

### Bất biến của bitset

Với chỉ số logic hợp lệ `0 ≤ i < n`:

\[
\mathrm{wordIndex}(i)=\lfloor i/w\rfloor,\quad
\mathrm{bitOffset}(i)=i\bmod w.
\]

Một thao tác `get(i)` đọc từ `words[i // w]` và kiểm tra bit theo mask `1 << (i % w)`. Đặt và xóa bit cũng sửa đúng từ ấy.

Các bất biến cần duy trì:

1. Số từ được cấp phát đủ `ceil(n/w)`.
2. Chỉ số thao tác nằm trong `[0,n)`, không được coi các bit đệm là phần tử.
3. Bit logic thứ `i` luôn ánh xạ tới đúng từ và đúng offset theo một quy ước bit thống nhất.
4. Các bit padding ở từ cuối được giữ bằng 0 hoặc được mask khi đọc/đếm.
5. Mọi phép toán hai tập chỉ có ý nghĩa nếu cùng miền và cùng cách ánh xạ ID→vị trí bit.

Với từ máy `w` cố định, `get`, `set`, `clear` và `flip` thường mất **`O(1)`** thời gian. Ngược lại, `union` và `intersection` trên toàn tập phải xử lý `q` từ, nên mất **`O(q)`**, ngay cả khi chỉ có vài bit bằng 1.

### Điểm mạnh chính

Bitset dày đặc tận dụng được:

- **Truy cập theo vị trí:** không phải tìm ID trong bảng băm hoặc danh sách.
- **Tính liên tục:** các từ máy nằm cạnh nhau, thuận lợi cho duyệt tuần tự và cache.
- **Phép toán hàng loạt:** AND, OR, XOR, AND-NOT xử lý đồng thời `w` trạng thái mỗi lượt.
- **Đếm nhanh:** popcount tính số bit 1 trong một từ và cộng qua các từ.
- **Chi phí bộ nhớ dễ dự đoán:** phụ thuộc `n`, không phụ thuộc `k`.

Tuy nhiên, chi phí bộ nhớ theo miền là nhược điểm lớn nhất khi `n` rất cao còn `k` rất nhỏ.

## 3. Tập thưa: lưu phần tử thật sự thay vì mọi vị trí

Biểu diễn thưa lưu **những ID thuộc tập**, không tạo bit cho tất cả ID trong miền. Có nhiều cách tổ chức.

### 3.1. Mảng ID đã sắp xếp

Ví dụ `S = {1,4,9,15}` có thể lưu thành:

```text
positions = [1, 4, 9, 15]
```

Nếu mỗi ID dùng 4 byte, dữ liệu phần tử lý tưởng cần `4k` byte; nếu 8 byte, cần `8k` byte. Mảng còn có thể có metadata và dung lượng dự phòng.

Bất biến quan trọng:

- Các ID đều thuộc miền `U`.
- Các ID **tăng nghiêm ngặt**, không trùng.
- Độ dài mảng đúng bằng `k`.

Nhờ thứ tự này:

- Kiểm tra thành viên bằng **tìm kiếm nhị phân**: `O(log k)`.
- Duyệt toàn bộ phần tử đang có: `O(k)`.
- Giao/hợp hai mảng đã sắp xếp bằng **hai con trỏ**: `O(k_A + k_B)`.
- Chèn/xóa một ID có thể cần dịch chuyển phần còn lại của mảng: `O(k)` trong trường hợp xấu.

Mảng có thứ tự phù hợp với tập **ít thay đổi nhưng đọc và thực hiện phép giao thường xuyên**.

### 3.2. Hash set

Một hash set lưu trực tiếp các ID có mặt, thường hỗ trợ:

- `contains(i)`: `O(1)` **kỳ vọng** trong điều kiện bảng băm được tổ chức tốt.
- `add(i)` và `remove(i)`: `O(1)` **kỳ vọng** hoặc khấu hao, tùy cách cấp phát và xử lý va chạm.
- Duyệt các ID: khoảng `O(k)` khi chỉ xét các phần tử, nhưng chi phí thực tế cũng có thể phụ thuộc dung lượng bảng.
- Giao hai tập: lặp qua tập nhỏ hơn, kiểm tra từng ID trong tập kia; thường khoảng `O(min(k_A,k_B))` **kỳ vọng** dưới những giả định hash thích hợp.

Hash set phải lưu khóa, các ô băm và thông tin quản lý; thường tốn **nhiều hơn kích thước thô `4k` hoặc `8k` byte**. Vì vậy, tuy hợp lý khi cực thưa, không thể so sánh trực tiếp bộ nhớ thực tế chỉ bằng số byte của khóa.

### 3.3. Danh sách liên kết có phù hợp không?

Danh sách liên kết giữ ID cùng các liên kết. Nó có thể hỗ trợ chèn sau một nút đã biết với chi phí thấp, nhưng tìm kiếm ID thường `O(k)`, và overhead con trỏ làm giảm hiệu quả bộ nhớ/cache. Với bài toán tập ID cần tra cứu thường xuyên, mảng có thứ tự hoặc hash set thường là điểm bắt đầu phù hợp hơn.

**Kết luận:** “sparse set” không phải một cấu trúc dữ liệu duy nhất. Cần chọn cụ thể mảng ID, hash set, cây tìm kiếm, bảng các từ khác 0 hoặc bitmap nén để đánh giá chi phí.

## 4. So sánh bộ nhớ bằng công thức và số liệu cụ thể

Giả sử ID có thể lưu vừa trong 64 bit và chưa tính metadata hoặc dung lượng dư:

\[
M_{\mathrm{dense}}\approx \frac{n}{8}\ \text{byte},\qquad
M_{\mathrm{sorted64}}\approx 8k\ \text{byte}.
\]

Hai lượng lý tưởng bằng nhau khi:

\[
\frac n8=8k
\quad\Longleftrightarrow\quad
\frac kn=\frac1{64}\approx 1{,}5625\%.
\]

**Đây chỉ là ngưỡng hòa vốn của hai mô hình dữ liệu thô**, không phải ngưỡng lựa chọn phổ quát. Khi ID là 32 bit, mảng ID thô dùng khoảng `4k` byte và ngưỡng tương tự là `k/n=1/32≈3,125%`. Hash set có overhead cao hơn, bitset theo từ có padding, và các biểu diễn nén có chi phí khác.

| Miền `n` | Số ID bật `k` | Bitset theo byte, dữ liệu | Mảng ID 64 bit, dữ liệu |
|---:|---:|---:|---:|
| 1.000 | 10 | 125 B | 80 B |
| 1.000 | 500 | 125 B | 4.000 B |
| 1.000.000 | 100 | 125.000 B | 800 B |
| 1.000.000 | 500.000 | 125.000 B | 4.000.000 B |
| 1.000.000.000 | 100 | 125.000.000 B | 800 B |
| 1.000.000.000 | 50.000.000 | 125.000.000 B | 400.000.000 B |

Bảng so sánh **dữ liệu thô** để hình dung bậc kích thước; không dự đoán con số `sys.getsizeof` của Python, chi phí heap allocator hay các cấu trúc hash.

### Cần phân biệt MB và MiB

`125.000.000` byte bằng **125 MB thập phân**, nhưng xấp xỉ **119,2 MiB** nếu chia theo `2^{20}` byte. Nói “khoảng 125 MB” là đúng khi dùng đơn vị thập phân; cần giữ đơn vị nhất quán trong báo cáo hiệu năng.

### Miền định danh lớn không có nghĩa phải cấp phát đến ID lớn nhất

Nếu các ID là `1001, 500000000, 999999999` nhưng tập chỉ có ba đối tượng, lưu bit tại chính giá trị ID yêu cầu một miền gần một tỷ vị trí.

Nếu ứng dụng biết trước danh sách đối tượng hợp lệ, ta có thể xây **ánh xạ ID bên ngoài → chỉ số liên tục**:

```text
external ID: 1001     500000000    999999999
compact ID:     0             1            2
```

Khi ấy một bitset chỉ cần 3 bit logic. Tuy nhiên, ánh xạ bổ sung phải được lưu, cập nhật và đồng bộ với các dữ liệu khác; lookup ID ngoài có thể cần hash map hoặc tìm kiếm trên danh sách. **Nén miền bằng remapping** khác với nén chính dãy bit.

## 5. Đánh đổi thời gian: tra cứu, cập nhật và duyệt

Gọi `q = ceil(n/w)` là số từ của bitset dày đặc, `k` số phần tử đang bật. Với hai tập A/B, gọi `k_A`, `k_B` là số phần tử mỗi tập.

| Thao tác | Bitset dày đặc | Mảng ID sắp xếp | Hash set |
|---|---|---|---|
| Kiểm tra ID `i` | `O(1)` | `O(log k)` | `O(1)` kỳ vọng |
| Đặt ID đang vắng | `O(1)` trong miền đã cấp phát | `O(k)` do dịch chuyển | `O(1)` kỳ vọng/khấu hao |
| Xóa ID | `O(1)` | `O(k)` do dịch chuyển | `O(1)` kỳ vọng |
| Liệt kê ID có mặt | `O(q+k)` với CTZ theo từ | `O(k)` | Thường `O(k)` nhưng phụ thuộc cấu trúc bảng |
| Giao/hợp hai tập | `O(q)` theo từ | `O(k_A+k_B)` bằng hai con trỏ | Giao thường `O(min(k_A,k_B))` kỳ vọng; hợp thường `O(k_A+k_B)` kỳ vọng |
| Đếm số phần tử | `O(q)` với popcount, hoặc `O(1)` nếu cache | `O(1)` từ độ dài mảng | Thường `O(1)` từ metadata |
| Dung lượng dữ liệu | `O(n)` bit | `O(k)` ID | `O(k)` khóa và bảng, overhead đáng kể |

Các ký hiệu trên dùng mô hình RAM và từ máy `w` cố định. Nếu `n` rất lớn, `q` cũng lớn; **bitset không có phép hợp/giao toàn miền `O(1)`** chỉ vì dùng một toán tử `&` hoặc `|` trong ngôn ngữ.

### Tại sao duyệt một tập rất thưa bằng bitset có thể chậm?

Nếu có `n=1.000.000.000` và `k=100`, bitset từ 64 bit có:

\[
q=\lceil 1.000.000.000/64\rceil=15.625.000\ \text{từ}.
\]

Thuật toán liệt kê bit bật bằng `CTZ` phải tìm các từ không rỗng. Nếu không có chỉ mục phụ, nó vẫn quét qua **15.625.000 từ**, dù chỉ có 100 vị trí cần xuất. Mảng ID sắp xếp chỉ cần duyệt 100 ID.

Vì vậy, khi **đọc theo chỉ số tùy ý nhiều lần**, bitset có thể tốt; khi **chỉ liệt kê phần tử trong tập rất thưa**, lưu trực tiếp ID thường tránh phần công quét miền.

### Tính giao của hai tập thưa

Giả sử A và B mỗi tập có 50 ID trong miền một tỷ ID. Nếu lưu bằng bitset dày đặc, phép giao quét hàng triệu từ. Với hai mảng sắp xếp, thuật toán hai con trỏ xử lý nhiều nhất khoảng 100 phần tử; với hash set, có thể kiểm tra lần lượt 50 ID của một tập trong tập còn lại.

Ngược lại, nếu mỗi tập có vài trăm triệu ID, bitset dày đặc cho phép AND trên một từ xử lý nhiều cặp trạng thái và có thể tiết kiệm bộ nhớ so với mảng ID riêng lẻ.

## 6. Ví dụ Python: bitset dày đặc và set thưa

Ví dụ sau dùng `bytearray` làm vùng bitset dày đặc, mỗi byte chứa 8 cờ. Tất cả chỉ số được kiểm tra theo cùng miền `[0,n)`.

```python
class DenseBitSet:
    def __init__(self, nbits: int):
        if nbits < 0:
            raise ValueError("nbits phải không âm")
        self.nbits = nbits
        self.data = bytearray(nbits // 8 + (nbits % 8 != 0))

    def _check(self, i: int) -> None:
        if not 0 <= i < self.nbits:
            raise IndexError("Chỉ số ngoài miền")

    def add(self, i: int) -> None:
        self._check(i)
        self.data[i // 8] |= 1 << (i % 8)

    def discard(self, i: int) -> None:
        self._check(i)
        self.data[i // 8] &= ~(1 << (i % 8)) & 0xFF

    def contains(self, i: int) -> bool:
        self._check(i)
        return bool(self.data[i // 8] & (1 << (i % 8)))

    def count(self) -> int:
        # int.bit_count() được hỗ trợ từ Python 3.10.
        return sum(byte.bit_count() for byte in self.data)

    def positions(self):
        for byte_index, byte in enumerate(self.data):
            while byte:
                lowbit = byte & -byte
                offset = lowbit.bit_length() - 1
                yield byte_index * 8 + offset
                byte ^= lowbit


n = 1000
chosen = [1, 4, 9, 15, 900]

dense = DenseBitSet(n)
sparse = set()

for i in chosen:
    dense.add(i)
    sparse.add(i)

assert dense.contains(900) is True
assert dense.contains(10) is False
assert dense.count() == len(sparse) == 5
assert list(dense.positions()) == sorted(sparse)

dense.discard(4)
sparse.discard(4)
assert list(dense.positions()) == sorted(sparse)
```

Hai cấu trúc có cùng ý nghĩa tập hợp, nhưng:

- `dense` có đúng `ceil(n/8)` byte dữ liệu trong `bytearray`, bất kể có bao nhiêu bit đang bật.
- `sparse` chỉ lưu các ID có mặt dưới dạng một `set` Python. Kích thước bộ nhớ thật còn gồm bảng băm, đối tượng số nguyên và overhead runtime.
- `dense.positions()` phải xét mọi byte (rồi mới xuất bit 1); việc `sorted(sparse)` sắp xếp các ID có chi phí `O(k log k)`, trong khi chỉ duyệt set không cam kết thứ tự.

Ví dụ cố ý dùng `n=1000` để chạy nhanh và dễ kiểm chứng; không cần cấp phát một bitset một tỷ bit chỉ để thấy sự khác biệt về độ phức tạp.

### Giao và hợp của hai bitset dày đặc trong Python

Khi hai đối tượng có cùng `nbits`:

```python
def dense_union(a: DenseBitSet, b: DenseBitSet) -> DenseBitSet:
    if a.nbits != b.nbits:
        raise ValueError("Hai tập phải cùng miền")
    out = DenseBitSet(a.nbits)
    out.data[:] = bytes(x | y for x, y in zip(a.data, b.data))
    return out


def dense_intersection_count(a: DenseBitSet, b: DenseBitSet) -> int:
    if a.nbits != b.nbits:
        raise ValueError("Hai tập phải cùng miền")
    return sum((x & y).bit_count() for x, y in zip(a.data, b.data))


a = DenseBitSet(100)
b = DenseBitSet(100)
for i in (1, 2, 20):
    a.add(i)
for i in (2, 20, 30):
    b.add(i)

assert list(dense_union(a, b).positions()) == [1, 2, 20, 30]
assert dense_intersection_count(a, b) == 2
```

`dense_union` phải xử lý tất cả byte, ngay cả khi chỉ có vài vị trí bật. `dense_intersection_count` không cấp phát một bitset kết quả; nó AND từng byte rồi đếm, dùng bộ nhớ phụ hằng số ngoài bộ đếm và các giá trị tạm nhỏ.

**Bất biến padding:** các hàm `add` chỉ bật chỉ số trong miền và khởi tạo buffer bằng 0, nên bit đệm của byte cuối vẫn bằng 0. Nếu bổ sung phép NOT, nạp byte từ tệp hoặc API sửa trực tiếp `data`, cần **mask** bit đệm để `count` và `positions` không tính vị trí ngoài miền.

## 7. Một lựa chọn trung gian: chỉ lưu những từ máy khác 0

Bitset dày đặc không nhất thiết phải chiếm vùng nhớ cho mọi từ 64 bit. Ta có thể chia miền thành các khối, chỉ lưu **khối có bit 1** trong một bảng ánh xạ:

```text
wordIndex -> 64-bit word

  0     -> 0x0000000000000010  (bit 1)
  15    -> 0x0000000000000200  (bit 969)
  10000 -> 0x8000000000000000  (bit 640063)
```

Cấu trúc này thường được gọi là **sparse word bitmap** hoặc một biến thể **chunked/segmented bitset**.

Nếu `t` là số từ **khác 0**, ta lưu khoảng `t` cặp `(wordIndex, wordValue)` và metadata bảng, thay vì cấp phát tất cả `q` từ.

Bất biến:

1. Mọi `wordIndex` hợp lệ trong `[0,q)`.
2. Các giá trị lưu trong bảng **khác 0**; khi xóa bit cuối trong một từ thì xóa luôn mục của từ đó.
3. Cùng một từ chỉ có một bản ghi.
4. Bit logic ngoài `n` trong từ cuối không được xem là phần tử.
5. Một từ không có trong bảng được hiểu là **toàn 0**.

### Ví dụ Python với từ 64 bit

```python
class SparseWordBitmap:
    WORD_BITS = 64

    def __init__(self, nbits: int):
        if nbits < 0:
            raise ValueError("nbits phải không âm")
        self.nbits = nbits
        self.words: dict[int, int] = {}

    def _loc(self, i: int) -> tuple[int, int]:
        if not 0 <= i < self.nbits:
            raise IndexError("Chỉ số ngoài miền")
        return divmod(i, self.WORD_BITS)

    def add(self, i: int) -> None:
        j, bit = self._loc(i)
        self.words[j] = self.words.get(j, 0) | (1 << bit)

    def discard(self, i: int) -> None:
        j, bit = self._loc(i)
        value = self.words.get(j, 0) & ~(1 << bit)
        if value:
            self.words[j] = value
        else:
            self.words.pop(j, None)

    def contains(self, i: int) -> bool:
        j, bit = self._loc(i)
        return bool(self.words.get(j, 0) & (1 << bit))

    def count(self) -> int:
        return sum(word.bit_count() for word in self.words.values())

    def positions(self):
        for j in sorted(self.words):
            word = self.words[j]
            while word:
                lowbit = word & -word
                yield j * self.WORD_BITS + lowbit.bit_length() - 1
                word ^= lowbit


b = SparseWordBitmap(1_000_000_000)
for i in (3, 4, 65, 999_999_999):
    b.add(i)

assert b.count() == 4
assert list(b.positions()) == [3, 4, 65, 999_999_999]

b.discard(4)
assert not b.contains(4)
assert list(b.positions()) == [3, 65, 999_999_999]
```

Ở đây hai bit 3 và 4 cùng thuộc **một từ**, nên chia sẻ một bản ghi dữ liệu. Mô hình này có thể tiết kiệm hơn hash set lưu từng ID nếu mỗi từ chứa nhiều bit 1, nhưng bảng từ vẫn có overhead.

Với từ cố định 64 bit:

- Tra cứu/đặt/xóa bit: thường `O(1)` **kỳ vọng** nhờ bảng băm theo `wordIndex`.
- Bộ nhớ: `O(t)` mục bảng, với `t≤min(q,k)` khi chỉ có các từ khác 0.
- Đếm số bit 1: `O(t)` nếu dùng popcount mỗi từ.
- Liệt kê **theo thứ tự tăng** như `positions`: `O(t log t + k)` do phải sắp xếp các `wordIndex`. Nếu không cần thứ tự, có thể bỏ bước `sorted` và duyệt các từ trong thứ tự bảng trả về, thường `O(t+k)`.

Cấu trúc trung gian này đặc biệt hữu ích khi bit 1 **tập trung thành các cụm trong một số ít từ**. Nếu mỗi từ chỉ có một bit 1, bảng có số mục gần bằng số ID và có thể không tốt hơn một hash set ID thông thường.

## 8. Bitmap nén: tận dụng các khối dày, thưa hoặc các dải liên tiếp

Các bitmap nén không chỉ lưu một mảng bit thô. Chúng khai thác phân bố dữ liệu để tiết kiệm bộ nhớ hoặc tăng tốc thao tác.

### 8.1. Run-length encoding (RLE)

Nếu các bit có nhiều đoạn liên tiếp giống nhau, thay vì lưu tất cả bit, ta có thể giữ chiều dài mỗi đoạn:

```text
Bit:     0000000000111111111100000000
RLE:     (0,10), (1,10), (0,8)
```

Khi có rất ít dải dài, RLE tiết kiệm bộ nhớ. Nhưng với bit 0/1 xen kẽ liên tục, số đoạn nhiều và overhead có thể lớn hơn dãy bit nguyên thủy.

Truy cập ngẫu nhiên có thể cần tìm đoạn chứa vị trí; nếu chỉ duyệt RLE tuyến tính thì công tìm kiếm phụ thuộc số đoạn, còn nếu có chỉ mục phụ có thể cải thiện. Không thể nói mọi dạng RLE đều cho `get(i) = O(1)`.

### 8.2. Bitmap chia thành container thích ứng

Một số thư viện bitmap nén hiện đại, chẳng hạn dòng thiết kế **Roaring bitmap**, chia không gian ID thành các khối và chọn dạng lưu trữ cho từng khối dựa vào phân bố phần tử.

Một khối có ít phần tử có thể dùng **mảng ID cục bộ**, còn khối dày có thể dùng **bitmap cục bộ**; các đoạn liên tiếp có thể dùng dạng **run container** khi có hỗ trợ.

```text
Miền ID lớn
    │
    ├── Khối A: rất ít ID bật       → lưu mảng ID
    ├── Khối B: nhiều ID bật        → lưu bitmap
    ├── Khối C: dải ID liên tiếp    → lưu các run
    └── Khối D: không có ID         → không cần container
```

Ưu điểm là thích ứng với **mật độ cục bộ**: toàn miền có thể thưa, nhưng một vài khối rất dày. Một số phép hợp/giao có thể xử lý theo cặp container phù hợp thay vì quét toàn bộ miền.

Đổi lại, cấu trúc phức tạp hơn, có metadata, quy tắc chuyển đổi container và chi phí duy trì. Độ phức tạp cụ thể của `contains`, `add`, `union` và `intersection` phụ thuộc loại container, số khối và triển khai; không nên tự gán tất cả thao tác bằng `O(1)`.

### 8.3. Mật độ toàn cục chưa đủ để chọn biểu diễn

Hai tập cùng có `n=1.000.000` và `k=10.000` (mật độ 1%) có thể phân bố khác nhau:

- Tập A: 10.000 ID rải đều khắp miền.
- Tập B: 10.000 ID liên tiếp trong một đoạn ngắn.

Tập B có thể nén cực tốt bằng một run. Tập A có thể phù hợp với danh sách ID, hash set hoặc các container thưa. Vì vậy cần xem cả **số phần tử, vị trí và mức độ tập trung**, không chỉ `d=k/n`.

## 9. Ứng dụng trong đồ thị: bitset kề hay danh sách kề?

Đối với đồ thị có `V` đỉnh, có hai dạng biểu diễn phổ biến.

**Danh sách kề:** mỗi đỉnh lưu danh sách các đỉnh kề. Bộ nhớ phụ thuộc số đỉnh và số cạnh, thường `O(V+E)`, với `E` là số cạnh (đồ thị vô hướng thường giữ mỗi cạnh ở hai danh sách).

**Ma trận kề dạng bitset:** mỗi đỉnh có một bitset độ dài `V` để đánh dấu đỉnh kề, dùng khoảng:

\[
V^2\ \text{bit}\approx \frac{V^2}{8}\ \text{byte dữ liệu}.
\]

Với `V=100.000`, một ma trận kề bitset cần gần **1,25 tỷ byte** dữ liệu nếu lưu đầy đủ `V²` bit, chưa tính padding và metadata. Trong khi đó, với chỉ vài cạnh trung bình trên mỗi đỉnh, danh sách kề có thể tiết kiệm hơn nhiều.

### Những thao tác có thể thay đổi lựa chọn

| Nhu cầu đồ thị | Danh sách kề / tập thưa | Ma trận kề bitset |
|---|---|---|
| Duyệt hàng xóm của đỉnh bậc thấp | `O(deg(v))` | Quét bitset `O(V/w + deg(v))` với CTZ |
| Kiểm tra cạnh `(u,v)` | Có thể `O(deg(u))` hoặc `O(log deg(u))` nếu sắp xếp | `O(1)` tra bit |
| Đếm hàng xóm chung của u, v | Có thể giao hai danh sách/tập kề | AND + popcount khoảng `O(V/w)` |
| Bộ nhớ đồ thị thưa | Thường tốt | Có thể lãng phí `Θ(V²)` bit |
| Đồ thị rất dày, nhiều truy vấn giao hàng xóm | Chi phí lưu nhiều ID | Bitmap theo từ có thể thuận lợi |

Không có một lựa chọn thắng mọi bài toán. Với BFS/DFS trên đồ thị thưa, danh sách kề giúp chỉ duyệt cạnh thực. Với truy vấn hàng xóm chung lặp lại trên đồ thị tương đối dày, bitmap có thể tăng tốc đáng kể.

### Bitset đánh dấu “đã thăm” khác với ma trận kề

Ngay cả khi **danh sách kề** là biểu diễn tốt nhất cho cạnh, một bitset độ dài `V` vẫn có thể là cách tốt để lưu `visited` trong BFS/DFS. Ta có thể dùng **kết hợp nhiều cấu trúc**: danh sách kề cho đồ thị, bitset cho trạng thái đã thăm, queue hoặc stack cho thứ tự duyệt.

## 10. Ứng dụng trong lọc và tìm kiếm

Giả sử có `N` tài liệu, với các bộ lọc:

- `is_active`: tài liệu còn hiệu lực.
- `is_public`: tài liệu công khai.
- `contains_graph`: tài liệu chứa từ khóa “graph”.

Nếu các tập rất dày, lưu ba bitset cùng miền và tính:

```text
result = is_active AND is_public AND contains_graph
```

mỗi từ máy xử lý nhiều tài liệu cùng lúc; đếm kết quả có thể kết hợp `popcount` trực tiếp mà không cần tạo bản sao bitset.

Nhưng với một từ khóa cực hiếm chỉ xuất hiện trong 20 tài liệu trên miền một tỷ tài liệu, lưu một bitset dày đặc riêng cho từ đó thường lãng phí. **Posting list** chứa 20 ID hoặc một bitmap nén hợp lý hơn.

### Phép giao pha trộn dense–sparse

Giả sử tập A là bitset dày đặc còn tập B là danh sách `k_B` ID hiếm. Muốn lấy `A ∩ B`, ta có thể:

```text
result = []
for id in sparse_B:
    if dense_A.test(id):
        result.append(id)
```

Chi phí `O(k_B)` lượt kiểm tra bit và xuất kết quả, thay vì tạo bitmap B kích thước `n` rồi AND trên `q` từ. Mô hình này hữu ích khi **một điều kiện phổ biến, điều kiện kia rất hiếm**.

Ngược lại, khi cả hai tập đều dày và phải giao nhiều lần, AND trên từng từ có thể hiệu quả hơn kiểm tra từng ID.

**Bài học thiết kế:** phép toán trên tập không bắt buộc hai toán hạng phải có **cùng cấu trúc vật lý**, miễn API biết ánh xạ miền và cung cấp thuật toán kết hợp phù hợp.

## 11. Miền chỉ số thay đổi làm đánh đổi phức tạp hơn

Trong một bitset dày đặc, nếu `n` ban đầu là 1.000 nhưng xuất hiện ID 1.000.000.000, chương trình không thể đơn giản bật bit đó nếu chưa mở rộng vùng lưu trữ.

Một chiến lược có thể:

1. Chọn miền cố định, từ chối ID ngoài `[0,n)`.
2. Tự mở rộng bitset để hỗ trợ ID mới, tốn công cấp phát/sao chép vùng mới và tăng bộ nhớ theo chỉ số lớn nhất.
3. Dùng remapping ID ngoài → chỉ số liên tục.
4. Chọn hash set, sparse word bitmap hoặc bitmap chia khối nếu miền thay đổi và rất thưa.

Lưu ý: mảng động tăng dung lượng theo hệ số có thể cho chi phí append khấu hao thấp khi **số vị trí tăng tuần tự**. Nhưng một lần nhảy từ ID 1.000 lên ID một tỷ vẫn phải cấp phát/biểu diễn khoảng một tỷ vị trí nếu dùng bitset dày đặc ánh xạ trực tiếp; tăng dung lượng theo hệ số không xóa được nhược điểm đó.

### ID âm hoặc ID có kiểu khác số nguyên

Nếu ID có thể là số âm, chuỗi hay UUID, bitset trực tiếp không thể dùng giá trị đó làm chỉ số mảng. Cần ánh xạ sang miền liên tục hoặc cấu trúc tập hỗ trợ khóa tổng quát (hash set, cây tìm kiếm). Chi phí và vòng đời của ánh xạ phải được tính cùng bitset.

### Xóa phần tử không nhất thiết thu nhỏ bitset

Với bitset, `clear(i)` chỉ xóa một bit, thường `O(1)` và không giảm `capacity`. Nếu miền đang được mở rộng dần rồi ít ID hoạt động trở lại, bộ nhớ vẫn có thể lớn. Muốn thu nhỏ phải có chính sách riêng, hoặc chọn cấu trúc giải phóng các khối rỗng khi xóa.

## 12. Cache, băng thông và chi phí thực tế

Độ phức tạp Big-O giúp loại bỏ các lựa chọn rõ ràng không phù hợp, nhưng hiệu năng còn phụ thuộc cách bộ nhớ được truy cập.

### Duyệt tuần tự

Bitset dày đặc lưu các byte/từ liên tiếp. Khi AND/OR hoặc popcount toàn dãy, CPU có thể tận dụng truy cập tuần tự, cache line và đôi khi SIMD. Với tập đủ dày, chi phí duyệt nhiều từ có thể thấp hơn một thuật toán thưa phải theo nhiều con trỏ ngẫu nhiên.

### Truy cập ngẫu nhiên

Hash set có thời gian tra cứu `O(1)` kỳ vọng, nhưng có thể phải truy cập nhiều vị trí bộ nhớ không liên tiếp, gây cache miss. Bitset dày đặc truy cập một từ được tính trực tiếp từ chỉ số, thường có đường đi đơn giản hơn. Tuy nhiên nếu miền bitset quá lớn, truy cập ngẫu nhiên vẫn có thể miss cache; không nên gọi là “luôn nhanh hơn hash set”.

### Cấp phát và giải phóng

Tập thưa có thể tạo nhiều đối tượng hoặc ô trong bảng. Bitset thường cấp phát một vùng lớn, dễ quản lý nhưng có nguy cơ yêu cầu quá nhiều bộ nhớ. Bitmap chia khối tạo ít vùng hơn so với lưu từng bit hoặc từng ID trong những tình huống thích hợp, nhưng thêm chi phí metadata.

### Đồng thời

Hai luồng sửa hai bit khác nhau **trong cùng một từ** vẫn có thể tranh chấp dữ liệu. Phép `words[j] |= mask` bình thường là đọc-sửa-ghi, không tự nguyên tử. Với mã C/C++, thiếu đồng bộ trên từ dùng chung có thể tạo data race và hành vi không xác định. Atomic word hoặc khóa có thể cần thiết.

Hash set dùng chung cũng cần cơ chế đồng bộ riêng. Vì vậy **đồng thời** không phải đặc tính tự giải quyết của dense hay sparse; nó là một chiều lựa chọn cần đánh giá.

## 13. Phân tích nhiều điều kiện trước khi chọn cấu trúc

Một cách quyết định thực tế:

| Câu hỏi | Khi câu trả lời là… | Hướng thường nên thử |
|---|---|---|
| Miền `n` có nhỏ, cố định và các ID liên tục? | Có | Bitset dày đặc |
| Mật độ `k/n` cao? | Có | Bitset theo từ, phép toán hàng loạt |
| Miền cực lớn nhưng `k` rất nhỏ? | Có | Mảng ID / hash set |
| Các ID chủ yếu xuất hiện trong vài khối? | Có | Sparse word bitmap / bitmap chia khối |
| Có các dải ID liên tiếp dài? | Có | RLE / bitmap nén có run |
| Cần kiểm tra thành viên ngẫu nhiên rất nhiều lần? | Có | Bitset hoặc hash set, đo cache/chi phí |
| Cần liệt kê chỉ vài ID đang có? | Có | Biểu diễn lưu trực tiếp ID |
| Cần giao/hợp giữa các tập lớn, thường xuyên? | Có | Bitset theo từ hoặc bitmap nén hỗ trợ phép toán tập hợp |
| Miền ID thay đổi hoặc ID rất lớn? | Có | Remapping hoặc cấu trúc thưa/động |
| Cần thứ tự tăng dần khi duyệt? | Có | Mảng sắp xếp, cây, hoặc bitset với CTZ; hash set có thể phải sắp xếp |
| Dữ liệu vừa dày vừa thưa theo từng vùng? | Có | Bitmap lai thích ứng theo khối |

Bắt đầu bằng **bất biến của tập và miền**: ID nào hợp lệ, cùng ID có cùng ý nghĩa trong các tập không, có cho phép thay đổi miền không, và có cần thứ tự duyệt không. Sau đó mới xem bộ nhớ và độ phức tạp.

## 14. Đo hiệu năng công bằng

Để so sánh dense bitset với sparse set, thử cả **ba phân bố** ở cùng `n` và `k`:

1. ID chọn ngẫu nhiên rải đều trên miền.
2. ID tập trung thành vài cụm nhỏ.
3. ID tạo thành các dải liên tiếp dài.

Đo riêng các thao tác thực tế:

- `contains(i)` trên ID có mặt và vắng mặt.
- `add(i)`, `discard(i)` khi tập thay đổi.
- Liệt kê tất cả các ID có mặt.
- `union/intersection` lặp lại giữa các cặp tập.
- `count()` và đếm phần giao, nếu có yêu cầu.

Cần đo **dung lượng bộ nhớ sống, đỉnh bộ nhớ, thời gian cấp phát và thời gian truy vấn**. Trong Python, `sys.getsizeof` trên một đối tượng không nhất thiết cộng toàn bộ bộ nhớ mà các đối tượng con, phần tử `int` hoặc bảng nội bộ đang dùng. Để so sánh chính xác, nên dùng phương pháp đo toàn bộ cấu trúc và kiểm thử trên cùng phiên bản runtime.

**Đừng đo chỉ một mức mật độ**. Bitset có thể thắng khi các tập tương đối dày và cần AND/OR hàng loạt, nhưng thua rõ ràng khi liệt kê 100 ID trên miền một tỷ vị trí.

## 15. Bài tập tự kiểm tra

**Câu 1.** Miền có `n=1.000.000` và tập có `k=100` ID. Mật độ bằng bao nhiêu phần trăm, và bitset đóng gói theo byte cần bao nhiêu byte dữ liệu?

**Đáp án:** `d=100/1.000.000=0,0001=0,01%`. Bitset cần `ceil(1.000.000/8)=125.000` byte dữ liệu.

**Câu 2.** Với miền một tỷ vị trí, chỉ có 100 ID bật, vì sao bitset dày đặc có thể kém kinh tế hơn mảng ID 64 bit?

**Đáp án:** Bitset cần khoảng 125.000.000 byte dữ liệu, trong khi mảng 100 ID 64 bit có dữ liệu thô khoảng 800 byte. Mảng còn overhead, nhưng chênh lệch đủ lớn để cần cân nhắc biểu diễn thưa.

**Câu 3.** Nếu chỉ so `n/8` byte của bitset với `8k` byte của mảng ID 64 bit, ngưỡng hòa vốn theo mật độ là bao nhiêu? Có phải ngưỡng chung của mọi phần mềm không?

**Đáp án:** `k/n=1/64≈1,5625%`. Không phải ngưỡng chung; nó bỏ qua padding, metadata, cấp phát, cache và hiệu quả của các thao tác cần chạy.

**Câu 4.** Một bitset dùng từ 64 bit, với `n=1.000.000.000` và `k=100`. Liệt kê bit bật bằng cách quét từng từ có phải `O(k)` không?

**Đáp án:** Không. Không có chỉ mục phụ, phải quét `q=15.625.000` từ, rồi xuất 100 vị trí; thời gian khoảng `O(q+k)` khi dùng CTZ hằng số trên từ máy.

**Câu 5.** Một mảng ID tăng nghiêm ngặt có những ưu/nhược điểm gì so với bitset dày đặc?

**Đáp án:** Dùng `O(k)` ID, kiểm tra thành viên `O(log k)`, duyệt `O(k)`; giao/hợp hai mảng sắp xếp `O(k_A+k_B)`. Nhưng chèn hoặc xóa có thể phải dịch chuyển `O(k)` phần tử.

**Câu 6.** Hai tập cực thưa đều có 20 phần tử trong miền một tỷ vị trí. Để tính giao, cách nào nên được thử trước?

**Đáp án:** Duyệt mảng ID/khóa của một tập rồi kiểm tra trong tập kia (hash set hoặc hai con trỏ nếu cả hai đã sắp xếp), thay vì cấp phát hai bitset dày đặc và AND trên toàn miền.

**Câu 7.** Tại sao một sparse word bitmap có thể tốt hơn lưu từng ID khi các bit 1 tập trung vào vài khối 64 bit?

**Đáp án:** Mỗi khối 64 bit được lưu bằng **một từ** và một khóa chỉ số khối; nhiều ID trong cùng khối chia sẻ một mục bảng. Số mục `t` có thể nhỏ hơn nhiều so với `k`.

**Câu 8.** Cùng có mật độ 1%, một tập gồm một dải 10.000 ID liên tiếp và tập khác gồm 10.000 ID rải đều. Vì sao biểu diễn tốt có thể khác nhau?

**Đáp án:** Tập liên tiếp có thể biểu diễn gọn bằng một run, trong khi tập rải đều có nhiều đoạn và cần mảng ID, hash set hoặc container thưa. Mật độ toàn cục không phản ánh tính liên tiếp.

**Câu 9.** Tại sao với đồ thị thưa thường dùng danh sách kề, nhưng vẫn có thể dùng bitset `visited` trong BFS?

**Đáp án:** Danh sách kề chỉ lưu cạnh thực, tránh `Θ(V²)` bit cho ma trận kề. Trạng thái `visited` chỉ cần `V` bit, nên bitset vẫn rất tiết kiệm và cho kiểm tra/đặt bit `O(1)`.

**Câu 10.** Nếu miền đang có 1.000 vị trí và xuất hiện ID một tỷ, việc tăng `capacity` theo hệ số có giải quyết được nhu cầu RAM của bitset ánh xạ trực tiếp không?

**Đáp án:** Không. Bitset dày đặc vẫn phải biểu diễn mọi vị trí từ 0 tới ID mới nếu dùng ánh xạ trực tiếp. Cần cân nhắc remapping hoặc cấu trúc thưa.

**Câu 11.** Giao giữa một bitset dày đặc A và danh sách 50 ID thưa B có thể tính thế nào mà không tạo bitset B?

**Đáp án:** Duyệt 50 ID của B, gọi `A.contains(id)` cho từng ID và giữ những ID có bit A bằng 1. Khi A hỗ trợ tra cứu `O(1)`, chi phí khoảng `O(50)` lượt kiểm tra, chưa tính xây kết quả.

## Ghi nhớ

- **`n` là kích thước miền**, **`k` là số phần tử thực có**, còn **`d=k/n` là mật độ**. Bitset dày đặc có dung lượng theo `n`, bất kể có bao nhiêu bit đang bật.
- Một bitset theo từ `w` cần khoảng **`n/8` byte dữ liệu**; tra cứu, đặt, xóa một bit trong miền đã cấp phát thường `O(1)`, nhưng hợp/giao/đếm toàn miền cần xử lý **`O(ceil(n/w))` từ**.
- **Mảng ID sắp xếp** và **hash set** giữ phần tử thực sự, thường hợp lý hơn khi `k≪n`. Mỗi cấu trúc đổi thời gian tra cứu, cập nhật, thứ tự duyệt và overhead bộ nhớ theo cách khác nhau.
- **Ngưỡng hòa vốn theo bộ nhớ thô không phải quy tắc tuyệt đối**. Hãy tính metadata, padding, chi phí cache, mẫu truy vấn và phân bố ID.
- **Sparse word bitmap, bitmap nén và container thích ứng** có thể phối hợp ưu điểm của dày và thưa, nhất là khi mật độ khác nhau theo từng vùng.
- Có thể kết hợp cấu trúc: **danh sách kề cho đồ thị thưa, bitset cho `visited`**, hoặc **bitset cho bộ lọc phổ biến và posting list cho bộ lọc hiếm**.
- Chọn biểu diễn theo **miền giá trị, mật độ, phân bố, phép toán chủ đạo, khả năng mở rộng và vòng đời dữ liệu**, không chỉ theo việc bitset có “tiết kiệm 8 lần” so với một byte cho mỗi Boolean.
