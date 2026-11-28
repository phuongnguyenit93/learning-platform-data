# Phân biệt bộ lọc xác suất với tập hợp lưu khóa chính xác

## 1. Cùng hỏi “khóa có tồn tại không?”, nhưng mức bảo đảm khác nhau

Một hệ thống ghi nhận hàng triệu mã giao dịch, URL đã thu thập hoặc định danh người dùng. Khi một mã mới xuất hiện, hệ thống muốn kiểm tra nó đã được xử lý hay chưa. Có hai hướng thiết kế:

- **Tập hợp chính xác** (*exact set*): lưu đủ thông tin để xác định một khóa có thuộc tập hay không, ví dụ `set` trong Python, bảng băm hoặc một chỉ mục cơ sở dữ liệu có ràng buộc duy nhất.
- **Bộ lọc xác suất** (*probabilistic membership filter*): lưu một biểu diễn nén của các khóa, ví dụ **Bloom filter** hay **Cuckoo filter**, để trả lời nhanh “chắc chắn không có” hoặc “có thể có”.

Đây là một quyết định quan trọng khi lựa chọn cấu trúc dữ liệu: ta có cần **kết luận đúng tuyệt đối** hay chỉ cần **loại bớt các truy vấn chắc chắn không cần thiết**? Bộ lọc thường sử dụng ít bộ nhớ hơn, nhưng kết quả dương tính có thể không chính xác.

Với tập khóa thực tế `S`, toán tử kiểm tra thành viên đúng là:

```text
contains_exact(x) = True   nếu x thuộc S
                    False  nếu x không thuộc S
```

Bộ lọc xác suất `F` được dựng từ `S` thường có ý nghĩa:

```text
F.might_contain(x) = False  ⇒  x không thuộc tập đã được F biểu diễn
F.might_contain(x) = True   ⇒  x có thể thuộc tập đó
```

Mệnh đề đầu chỉ bảo đảm khi cấu trúc được cập nhật đầy đủ, không lỗi, không xóa nhầm, không tràn và phép băm nhất quán. Một bộ lọc cũ hoặc cập nhật sai có thể đưa ra kết quả phủ định không còn đúng với dữ liệu nguồn.

Sau bài này, bạn sẽ phân biệt rõ **đúng/sai của kết quả**, **va chạm băm**, **chi phí bộ nhớ**, **xóa**, **đồng bộ trạng thái** và cách kết hợp bộ lọc với nguồn dữ liệu chính xác.

## 2. Tập hợp chính xác hoạt động thế nào?

Tập hợp (*set*) duy trì các phần tử phân biệt. Với bảng băm, hệ thống tính `hash(x)` để tìm vị trí tra cứu, nhưng vẫn cần **so sánh khóa** để xác định phần tử đang tìm.

```text
Tập khóa S = {"u11", "u25", "u39"}

"u25" in S  -> True
"u88" in S  -> False
```

Hai khóa có thể trùng giá trị băm; đó gọi là **hash collision**. Một bảng băm chính xác có cơ chế giải quyết va chạm, chẳng hạn chaining hoặc open addressing, rồi kiểm tra quan hệ bằng nhau giữa các khóa. Vì vậy, **va chạm hash không tự tạo false positive** cho tập hợp được cài đặt đúng.

Một bảng băm điển hình có các đặc điểm:

| Tính chất | Tập hợp chính xác dựa trên bảng băm |
|---|---|
| Kiểm tra thành viên | Kết quả `True/False` chính xác theo quy tắc bằng nhau của khóa |
| Thêm, xóa | Hỗ trợ trực tiếp |
| Duyệt phần tử | Có thể duyệt lại các khóa đã lưu |
| Bộ nhớ | Tăng theo số khóa phân biệt và kích thước biểu diễn khóa |
| Tìm kiếm trung bình | Thường `O(1)` kỳ vọng với hash phù hợp |
| Trường hợp xấu | Có thể tốn `O(n)` với cấu trúc băm thông thường nếu nhiều va chạm |

Trong Python:

```python
seen = {"u11", "u25", "u39"}

assert "u25" in seen
assert "u88" not in seen

seen.add("u88")
assert "u88" in seen
seen.remove("u25")
assert "u25" not in seen
```

Đổi lại tính chính xác, `set` phải giữ các khóa cùng cấu trúc bảng, vị trí trống và thông tin quản lý. Với hàng triệu chuỗi dài, chi phí có thể lớn hơn đáng kể so với một mảng bit hoặc mảng fingerprint được đóng gói.

**Phân biệt khái niệm:** nếu hệ thống chỉ lưu một giá trị hash ngắn rồi coi các hash bằng nhau là “cùng khóa”, đó là một **biểu diễn mất thông tin**, không còn là tập hợp khóa chính xác. Để giữ tính chính xác, phải lưu đủ thông tin để phân biệt hai khóa bị va chạm.

## 3. Bloom filter: lưu dấu vết bằng các bit

**Bloom filter** cơ bản sử dụng mảng `m` bit, ban đầu toàn `0`, và `k` hàm băm chọn vị trí bit. Với khóa `x`:

1. **Thêm `x`:** tính `k` vị trí, đặt tất cả các bit tương ứng thành `1`.
2. **Tra cứu `x`:** nếu có bất kỳ bit tương ứng bằng `0`, trả về **chắc chắn không có** trong filter.
3. Nếu tất cả các bit đều bằng `1`, trả về **có thể có**.

Các bit do nhiều khóa dùng chung, nên dù chưa thêm `x`, những khóa khác vẫn có thể đã đặt toàn bộ bit mà `x` cần. Khi đó filter trả về `True` sai: **false positive**.

### Ví dụ tính tay

Giả sử Bloom filter có 8 bit và 2 phép băm. Ta đã thêm `A` tại hai vị trí `1,4` và `B` tại `2,4`:

```text
Chỉ số bit:   0 1 2 3 4 5 6 7
Giá trị:      0 1 1 0 1 0 0 0

A cần bit:      ^     ^           -> có thể có (đã thêm)
B cần bit:        ^   ^           -> có thể có (đã thêm)
C cần bit:      ^ ^               -> có thể có (chưa thêm!)
D cần bit:    ^       ^           -> chắc chắn không có
```

Trong ví dụ, `C` được băm vào hai vị trí `1,2`. Cả hai bit đều bằng `1` do `A` và `B` đặt, nên `C` là một **dương tính giả**. Ngược lại, `D` cần vị trí `0` đang bằng `0`, nên không thể đã được chèn thành công vào bộ lọc hiện tại.

Với Bloom filter **chỉ thêm** (*insertion-only*) và không có lỗi cập nhật, mỗi khóa đã chèn đều có các bit của nó bằng `1`; vì vậy không tạo âm tính giả cho những khóa ấy. Bloom filter cơ bản **không hỗ trợ xóa an toàn** bằng cách đặt những bit của khóa về `0`: bit đó có thể đang được khóa khác sử dụng.

## 4. Cuckoo filter: lưu fingerprint trong bucket

**Cuckoo filter** cũng trả lời kiểm tra thành viên gần đúng nhưng lưu **fingerprint** ngắn của khóa trong các bucket, thay vì sử dụng mảng bit theo kiểu Bloom.

Với khóa `x`, tạo fingerprint `t = F(x)` và hai bucket ứng viên `i_1, i_2`. Khi tìm `x`, chỉ cần xem trong hai bucket đó có fingerprint `t` hay không:

```text
Khóa x --hash--> fingerprint t
                  |
           +------+------+
           |             |
       bucket i1     bucket i2
           |             |
       tìm t ở một trong hai bucket
```

Một kỹ thuật phổ biến để tìm hai vị trí là:

```text
i1 = H(x) mod m
i2 = i1 XOR G(t)
```

Với `m` là lũy thừa của 2 và `G(t)` được giới hạn về số bit chỉ số, phép XOR cho phép suy ra bucket còn lại khi di chuyển fingerprint:

```text
i1 XOR G(t) = i2
i2 XOR G(t) = i1
```

Cuckoo filter có thể **xóa một fingerprint** khỏi bucket ứng viên, nhưng chỉ an toàn khi hệ thống biết chắc khóa tương ứng đã được chèn thành công và đang có trong tập cần biểu diễn. Một khóa chưa tồn tại có thể trùng fingerprint với khóa thật tại bucket ứng viên; xóa nó sẽ gây âm tính giả. Nếu hai bucket đều đầy, chèn có thể phải đẩy fingerprint sang bucket còn lại (*cuckoo kicking*) và **có thể thất bại**. Cần giới hạn lượt đẩy cùng phương án hoàn tác, vùng dự phòng hoặc xây lại, để không làm mất khóa đã được biểu diễn.

**Giống Bloom:** kết quả tìm thấy fingerprint là **“có thể có”**; cấu trúc không giữ khóa gốc để xác minh danh tính. **Khác Bloom cơ bản:** có cơ chế xóa có điều kiện và có thể chèn thất bại khi đầy. Tỷ lệ dương tính giả phụ thuộc độ dài fingerprint, số ô mỗi bucket, tải dữ liệu và cách triển khai.

## 5. So sánh kết quả: dương tính giả và âm tính giả

Ký hiệu:

- **TP (true positive):** khóa có thật, cấu trúc trả về có.
- **TN (true negative):** khóa không có, cấu trúc trả về không.
- **FP (false positive):** khóa không có, cấu trúc trả về có.
- **FN (false negative):** khóa có thật, cấu trúc trả về không.

| Trạng thái thực tế của khóa | Kết quả trả về | Phân loại | Tác động |
|---|---|---|---|
| Có | Có | TP | Phát hiện đúng |
| Không | Không | TN | Loại đúng |
| Không | Có | FP | Phải xác minh thêm hoặc xử lý thừa |
| Có | Không | FN | Có thể bỏ sót một khóa thật |

Đối với **exact set** hoạt động đúng, không có FP hoặc FN theo ngữ nghĩa khóa được khai báo. Đối với Bloom filter hoặc Cuckoo filter được duy trì hợp lệ, FP được chấp nhận và FN không phải kết quả bình thường mong đợi.

**Đừng nhầm hai loại “va chạm”:** hash collision trong tập hợp chính xác được giải quyết bằng kiểm tra khóa; bit/fingerprint collision trong bộ lọc xác suất gây mơ hồ **vì bộ lọc không giữ đủ thông tin để phân biệt khóa**.

### Một kết quả âm có “chắc chắn” theo nghĩa nào?

Nếu một Bloom filter được tạo từ snapshot `S_0`, thì trả về `False` chỉ chứng minh `x` không thuộc **tập đã được filter biểu diễn**, trong các giả định đúng của cấu trúc. Nếu cơ sở dữ liệu đã có thêm khóa sau snapshot nhưng filter chưa cập nhật, `x` vẫn có thể có trong cơ sở dữ liệu.

Vì thế cần tách biệt:

1. **Bảo đảm toán học của cấu trúc:** đối với khóa đã chèn thành công và chưa bị xóa nhầm, bộ lọc không báo âm.
2. **Bảo đảm hệ thống:** mọi khóa có trong nguồn sự thật đã được phản ánh trong phiên bản bộ lọc dùng để phục vụ truy vấn.

Một hệ thống có thể thỏa điều kiện thứ nhất nhưng vi phạm điều kiện thứ hai do trễ đồng bộ, lỗi ghi hoặc race condition.

## 6. Chi phí bộ nhớ và thời gian

| Tiêu chí | Exact `set` / bảng băm | Bloom filter | Cuckoo filter |
|---|---|---|---|
| Thông tin lưu | Khóa đầy đủ và metadata | Mảng `m` bit | Fingerprint ngắn trong bucket |
| Bộ nhớ | Phụ thuộc số và kích thước khóa | Theo số bit được cấp | Theo số bucket, ô và fingerprint |
| Kiểm tra thành viên | Chính xác | Gần đúng | Gần đúng |
| Trả về hoặc duyệt khóa | Có thể | Không | Không thể khôi phục khóa từ fingerprint |
| Thêm | Thường `O(1)` kỳ vọng | `O(k)` phép băm/đặt bit | Thường nhanh; có thể phải đẩy nhiều lần |
| Tra cứu | Thường `O(1)` kỳ vọng | `O(k)` | `O(b)` với `b` ô mỗi bucket |
| Xóa | Trực tiếp | Không an toàn trong bản cơ bản | Có điều kiện, cần biết khóa tồn tại |
| Khi gần đầy | Bảng băm có thể mở rộng | Không thất bại chỉ vì hết ô, nhưng FP tăng | Chèn có thể thất bại |

Với `k` và `b` nhỏ được cố định từ cấu hình, Bloom và Cuckoo thường được xem là có tra cứu `O(1)`. Độ phức tạp bảng băm là **trung bình/kỳ vọng**, không phải bảo đảm trường hợp xấu. Việc băm khóa dài vẫn tiêu tốn thời gian theo chiều dài khóa, bất kể cấu trúc được dùng.

### Ước lượng bộ nhớ Bloom filter

Giả sử cần biểu diễn khoảng `n` khóa và muốn tỷ lệ dương tính giả mục tiêu `p_{fp}`. Với các phép băm phân bố tốt, xác suất dương tính giả của Bloom filter được xấp xỉ:

```text
p_fp ≈ (1 - exp(-k n / m))^k

m ≈ -n ln(p_fp) / (ln 2)^2       // số bit tối ưu gần đúng
k ≈ (m / n) ln 2                // số hash gần tối ưu
```

Ví dụ `n = 1.000.000` khóa và `p_{fp} = 0,01` (1%):

```text
m ≈ 9.585.059 bit
  ≈ 1.198.133 byte
  ≈ 1,14 MiB

k ≈ 6,64 -> chọn khoảng 7 hàm băm/vị trí
```

Đây là phần dung lượng **mảng bit**, chưa tính thông tin về seed, căn chỉnh và metadata. Bộ lọc không giữ một triệu chuỗi khóa, trong khi exact set cần bộ nhớ cho từng khóa cùng bảng băm. Tuy nhiên, số byte thực tế của exact set phụ thuộc ngôn ngữ lập trình, độ dài khóa, bộ cấp phát và hệ số tải nên không thể kết luận một con số duy nhất chỉ từ `n`.

Nếu vượt đáng kể `n` dự kiến nhưng vẫn giữ nguyên `m` và `k`, tỷ lệ FP của Bloom filter tăng. Việc muốn hạ FP có thể đòi hỏi **xây lại từ khóa nguồn** hoặc dùng một biến thể filter có khả năng mở rộng; không thể mặc định kéo dài mảng bit là đủ vì cách tính vị trí băm có thể thay đổi.

### Chi phí của một false positive

Giả sử hệ thống có `Q = 100.000` truy vấn đến các khóa **thực sự không tồn tại**, với tỷ lệ FP khoảng 1%. Khi ấy số lần phải tra cứu nguồn chính xác vì filter trả về “có thể có” vào khoảng:

```text
Số lần xác minh thêm kỳ vọng ≈ Q × p_fp
                           ≈ 100.000 × 0,01 = 1.000
```

Đây là giá trị kỳ vọng theo giả định mô hình và dữ liệu truy vấn phù hợp; lượng FP thực tế có thể khác. Với thiết kế đúng, các FP này **làm tăng chi phí kiểm tra**, không làm thay đổi kết luận tồn tại sau khi nguồn chính xác xác minh.

## 7. Kết hợp bộ lọc với nguồn dữ liệu chính xác

Một mô hình sử dụng phổ biến là đặt bộ lọc trước một kho dữ liệu có thể kiểm chứng:

```text
                  +--------------------+
Truy vấn x ------>| Bloom/Cuckoo filter |
                  +----------+---------+
                             |
                   +---------+----------+
                   |                    |
              chắc chắn không       có thể có
                   |                    |
          trả lời KHÔNG*         truy vấn nguồn chính xác
                                        |
                                +-------+-------+
                                |               |
                           thật sự có      thật sự không
                                |               |
                           trả lời CÓ       trả lời KHÔNG

*Chỉ khi filter đã bao phủ đầy đủ trạng thái nguồn đang được kiểm tra.
```

Trong ví dụ hệ thống chống xử lý trùng sự kiện:

- **Nguồn sự thật** lưu mã đã xử lý với cơ chế kiểm tra duy nhất hoặc transaction phù hợp.
- **Bộ lọc** chỉ là lớp tối ưu: nếu nhận kết quả “có thể đã xử lý”, hệ thống xác minh mã trong nguồn sự thật.
- Nếu filter nói “chưa có”, hệ thống chỉ được bỏ qua truy vấn xác minh trong trường hợp **đã bảo đảm filter đồng bộ** với toàn bộ các mã đã ghi. Thao tác ghi mới vẫn cần ràng buộc duy nhất nếu có khả năng hai yêu cầu đến đồng thời.

### Các tình huống lệch trạng thái

| Tình huống | Hậu quả có thể gặp | Cách xử lý |
|---|---|---|
| Ghi thành công vào DB nhưng chưa cập nhật filter | Filter có thể trả về không cho khóa đã có trong DB | Bảo đảm cập nhật có thứ tự và tính nhất quán, hoặc xác minh DB khi trạng thái filter chưa tin cậy |
| Xóa khỏi DB nhưng filter chưa xóa | Filter có thể trả về có thể có cho khóa đã xóa | Thường gây truy vấn xác minh thừa |
| Xóa nhầm fingerprint của Cuckoo filter | Có thể mất khả năng biểu diễn khóa khác | Chỉ xóa khóa được chứng minh tồn tại; quản lý thêm trùng và lỗi thao tác |
| Snapshot được dựng thiếu một shard | Có thể tạo kết quả âm sai so với toàn hệ thống | Theo dõi phạm vi dữ liệu, phiên bản và tiến độ đồng bộ |
| Thay hash, seed hoặc chuẩn hóa khóa | Truy vấn có thể tìm sai vị trí bit/bucket | Xây lại filter hoặc dùng quy trình chuyển đổi được xác thực |

**Điểm mấu chốt:** FP của bộ lọc là đặc điểm của thuật toán; FN so với cơ sở dữ liệu thường chỉ ra lỗi vận hành, đồng bộ hoặc dùng sai điều kiện. Đối với nghiệp vụ quan trọng như quyền truy cập, tài chính, chống gian lận hoặc kiểm tra ràng buộc dữ liệu, kết quả dương tính từ filter **không thay thế bằng chứng chính xác**.

## 8. Mã Python minh họa: bộ lọc chỉ làm bước sàng lọc

Ví dụ dưới đây cài đặt một Bloom filter nhỏ bằng `bytearray` và dùng `set` làm nguồn sự thật. `blake2b` giúp tạo vị trí băm ổn định; mỗi hàm băm sử dụng chỉ số riêng để tránh dùng cùng một dữ liệu đầu vào. Mã chỉ nhận **khóa chuỗi** và hoạt động đồng bộ trong **một tiến trình**, nhằm minh họa thứ tự xử lý.

```python
from hashlib import blake2b


class BloomFilter:
    def __init__(self, bit_count, hash_count):
        if not isinstance(bit_count, int) or bit_count <= 0:
            raise ValueError("bit_count phai duong")
        if not isinstance(hash_count, int) or hash_count <= 0:
            raise ValueError("hash_count phai duong")
        self.bit_count = bit_count
        self.hash_count = hash_count
        self.bits = bytearray((bit_count + 7) // 8)

    def _positions(self, key):
        if not isinstance(key, str):
            raise TypeError("key phai la chuoi")
        data = key.encode("utf-8")
        for i in range(self.hash_count):
            raw = blake2b(
                b"bloom-v1:" + i.to_bytes(4, "big") + data,
                digest_size=8
            ).digest()
            yield int.from_bytes(raw, "big") % self.bit_count

    def add(self, key):
        for pos in self._positions(key):
            self.bits[pos // 8] |= 1 << (pos % 8)

    def might_contain(self, key):
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._positions(key)
        )


# Mo phong mot kho chinh xac trong mot tien trinh.
exact_keys = set()
filter_ = BloomFilter(bit_count=1024, hash_count=7)


def add_key(key):
    exact_keys.add(key)
    filter_.add(key)


def contains_key(key):
    if not filter_.might_contain(key):
        # Chi an toan neu filter phan anh du moi khoa trong exact_keys.
        return False
    return key in exact_keys


for key in ("order-1", "order-2", "order-3"):
    add_key(key)

assert contains_key("order-2")
assert not contains_key("missing")

# Doi chieu: moi khoa da them deu co ket qua duong tinh trong filter.
assert all(filter_.might_contain(x) for x in exact_keys)
```

Vì bộ lọc có thể trả về dương tính giả, hàm `contains_key()` **vẫn kiểm tra `set` khi filter trả về `True`**. Đoạn mã không khẳng định khóa `"missing"` luôn bị Bloom filter loại trực tiếp; nếu bị FP, `set` vẫn trả về `False`.

**Giới hạn của ví dụ:** thao tác `exact_keys.add(key)` và `filter_.add(key)` không phải một transaction nguyên tử. Nếu có truy vấn đồng thời chen vào giữa hai thao tác, filter có thể chưa thấy khóa đã được ghi vào `set`. Hệ thống thực tế cần thiết kế đồng bộ, snapshot theo phiên bản, cơ chế rebuild hoặc đường kiểm tra chính xác khi filter chưa hoàn toàn cập nhật. Một bảng băm `set` trong RAM cũng không tự thay thế cơ sở dữ liệu bền vững khi dịch vụ cần khôi phục sau sự cố.

## 9. Chọn cấu trúc dựa trên yêu cầu thật

| Yêu cầu | Lựa chọn và lý do |
|---|---|
| Cần xác minh chắc chắn khóa tồn tại hay không | Exact set hoặc chỉ mục cơ sở dữ liệu |
| Cần lọc nhanh lượng lớn truy vấn vắng mặt, cho phép thỉnh thoảng xác minh thừa | Bloom filter kết hợp nguồn chính xác |
| Cần xóa phần tử khỏi filter, có quy trình kiểm soát xóa rõ ràng | Cuckoo filter hoặc Counting Bloom filter |
| Cần liệt kê khóa, tra cứu thuộc tính hoặc cập nhật thông tin của từng khóa | Exact set/map hoặc kho dữ liệu |
| Cần kiểm tra số lần khóa xuất hiện gần đúng | Count-Min Sketch (bài toán **tần suất**, khác kiểm tra thành viên) |
| Cần đếm khoảng bao nhiêu khóa phân biệt | HyperLogLog (bài toán **cardinality**, khác kiểm tra thành viên) |

Trước khi quyết định, hãy xác định **quy mô dữ liệu**, **tỷ lệ truy vấn vào khóa không tồn tại**, **giới hạn RAM**, **chi phí truy vấn xác minh**, **nghiệp vụ có chấp nhận FP không**, và **có cần xóa hoặc duyệt khóa không**. Bộ lọc xác suất đáng dùng nhất khi loại bỏ phần lớn truy vấn âm tiết kiệm được nhiều hơn chi phí duy trì bộ lọc.

### Tính đúng đắn của câu trả lời không chỉ phụ thuộc cấu trúc

Hai triển khai có cùng thuật toán vẫn có thể cho kết quả khác nhau nếu chúng dùng cách mã hóa khóa khác nhau: ví dụ `"User42"` với `"user42"`, hoặc chuỗi Unicode được chuẩn hóa theo hai quy tắc. Cần khai báo rõ ngữ nghĩa **khóa nào được xem là bằng nhau** và dùng cùng quy tắc cho nguồn chính xác lẫn filter.

Nếu dữ liệu do người dùng chủ động chọn để gây va chạm, hash yếu có thể khiến FP tăng hoặc làm các cấu trúc bị quá tải. Hệ thống nên dùng hash và seed phù hợp với mô hình đe dọa, giám sát tải, kiểm thử trường hợp xấu và luôn có đường xác minh chính xác cho quyết định cần độ tin cậy cao.

## 10. Bài tập tự kiểm tra

**Câu 1.** Một khóa `x` chưa từng được thêm nhưng Bloom filter báo `True`. Đây là lỗi hay hiện tượng được phép?

**Đáp án:** Đây là **dương tính giả (FP)**, được phép trong mô hình Bloom filter. Phải xác minh bằng tập hợp chính xác trước khi kết luận `x` thực sự tồn tại.

**Câu 2.** Hai khóa `A` và `B` có cùng mã hash trong một bảng băm chính xác. Có bắt buộc hệ thống nhầm chúng là cùng một khóa không?

**Đáp án:** Không. Bảng băm chính xác giải quyết va chạm rồi so sánh khóa theo quy tắc bằng nhau. Chỉ lưu một dấu hash ngắn rồi bỏ khóa mới có thể làm mất tính chính xác.

**Câu 3.** Bộ lọc Bloom có `m = 1.000.000` bit và `k` cố định. Nếu số khóa được thêm vượt nhiều lần dự kiến, vấn đề chính là gì?

**Đáp án:** Nhiều bit chuyển thành `1`, tỷ lệ FP tăng. Bộ lọc không tự báo lỗi đầy như Cuckoo filter, nhưng khả năng loại truy vấn âm giảm mạnh.

**Câu 4.** Một khóa đã được ghi vào DB nhưng sự kiện cập nhật Bloom filter bị mất. Nếu filter trả về `False`, có thể kết luận khóa không tồn tại trong DB không?

**Đáp án:** Không. Đây là lỗi đồng bộ so với nguồn sự thật, khiến kết quả âm không còn bảo đảm cho DB. Cần xác minh DB hoặc khôi phục/tạo lại filter.

**Câu 5.** Cuckoo filter trả về “có thể có” cho khóa `y`. Có an toàn để gọi xóa `y` ngay lập tức không?

**Đáp án:** Không. Kết quả dương có thể do fingerprint trùng với khóa khác. Xóa phải dựa trên bằng chứng khóa đang thực sự tồn tại và đã được chèn thành công.

**Câu 6.** Bạn cần lưu 200.000 mã vé để trả lời chính xác, hỗ trợ xóa và liệt kê mã. Nên chọn Bloom filter làm nguồn duy nhất không?

**Đáp án:** Không. Cần lưu mã trong set hoặc nguồn dữ liệu chính xác; Bloom filter có thể hỗ trợ sàng lọc truy vấn vắng mặt nhưng không lưu danh sách mã hoặc cho bằng chứng dương tính chính xác.

**Câu 7.** Trong 100.000 truy vấn vào khóa thật sự vắng mặt, bộ lọc có FP khoảng 2%. Dự kiến khoảng bao nhiêu truy vấn vẫn phải kiểm tra nguồn chính xác?

**Đáp án:** Khoảng `100.000 × 0,02 = 2.000` truy vấn theo kỳ vọng. Số lượng thực tế còn phụ thuộc dữ liệu và chất lượng hash.

Trong các ứng dụng cần kiểm tra thành viên, **tập hợp chính xác trả lời “có hay không”**, còn **bộ lọc xác suất giúp quyết định khi nào có thể bỏ qua một lần kiểm tra tốn kém**. Lợi ích của bộ lọc đến từ việc tiết kiệm bộ nhớ và công việc truy vấn, trong khi tính đúng đắn cuối cùng vẫn phải dựa trên bất biến của filter, điều kiện đồng bộ và nguồn dữ liệu chính xác khi cần.
