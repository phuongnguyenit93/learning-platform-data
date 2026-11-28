# Cuckoo filter và lưu dấu vân tay của khóa

## 1. Bài toán: kiểm tra thành viên mà không lưu nguyên khóa

Giả sử hệ thống có hàng triệu mã giao dịch. Trước khi truy vấn cơ sở dữ liệu, ta muốn trả lời thật nhanh: **“Mã này có thể đã xuất hiện chưa?”** Việc giữ một tập hợp đầy đủ các chuỗi khóa trong RAM có thể tốn nhiều bộ nhớ. **Cuckoo filter** là cấu trúc dữ liệu xác suất (*probabilistic data structure*) giải quyết bài toán **kiểm tra thành viên gần đúng** (*approximate membership query*) bằng cách lưu những dấu vân tay ngắn của khóa.

Với một khóa `x`, truy vấn trả về:

- **Không có**: chắc chắn khóa không được biểu diễn trong filter, miễn là các thao tác trước đó hợp lệ và việc đồng bộ dữ liệu được bảo đảm.
- **Có thể có**: khóa có thể đã được thêm; đôi khi filter báo dương tính với khóa chưa từng thêm (**false positive**).

Trong điều kiện filter được cập nhật chính xác, các lần chèn đã báo thành công và không xóa nhầm, Cuckoo filter **không tạo false negative** đối với các khóa còn được biểu diễn. Khác với tập hợp chính xác, filter không thể trả về giá trị gắn với khóa hay chứng minh một kết quả dương tính là đúng.

Sau bài này, bạn cần nắm được cách tạo fingerprint, cách tìm hai bucket, lý do phép XOR cho phép di chuyển fingerprint mà không cần biết khóa gốc, quy trình chèn/xóa, và cách lựa chọn kích thước để cân bằng bộ nhớ, sai số và nguy cơ chèn thất bại.

## 2. Cấu trúc dữ liệu: bucket và fingerprint

Cuckoo filter dùng một mảng gồm `m` **bucket**; mỗi bucket chứa tối đa `b` fingerprint, mỗi fingerprint có `f` bit. Filter lưu fingerprint thay vì lưu khóa đầy đủ:

| Thành phần | Ý nghĩa |
|---|---|
| Khóa `x` | Dữ liệu ban đầu, ví dụ `"order-2048"`; không được giữ trong filter |
| Fingerprint `t = F(x)` | Mã ngắn `f` bit đại diện cho khóa; nhiều khóa có thể trùng fingerprint |
| Bucket `B[i]` | Nhóm tối đa `b` ô chứa fingerprint |
| Hai vị trí `i_1`, `i_2` | Hai bucket mà fingerprint của khóa được phép nằm trong đó |
| Hệ số lấp đầy `α` | Số ô đang sử dụng chia cho tổng `m × b` ô |

Minh họa với `m = 8` bucket và `b = 2` ô mỗi bucket:

```text
Chỉ số       0       1       2       3       4       5       6       7
Bucket    [  ·  ] [  ·  ] [  ·  ] [12,21] [  ·  ] [  ·  ] [ 4, ·] [  ·  ]
                    mỗi bucket có tối đa hai fingerprint

Khóa x --> fingerprint 45 --> hai bucket ứng viên: 3 và 6
                                                B[6] còn ô trống
```

Dấu `·` là ô trống. Sau khi chèn `x`, ta có thể thêm fingerprint `45` vào bucket `6` mà không phải lưu `x`. Một fingerprint đơn lẻ **không phải định danh duy nhất**: việc hai khóa khác nhau có cùng fingerprint là nguồn gốc của dương tính giả.

## 3. Từ một khóa đến hai bucket

Một phiên bản triển khai thường dùng các phép tính sau, với `m` là lũy thừa của hai:

```text
t        = F(x)                    // fingerprint f bit, khác 0
i1       = H1(x) & (m - 1)        // bucket thứ nhất
d(t)     = 1 + H2(t) % (m - 1)    // độ lệch khác 0, phụ thuộc fingerprint
i2       = i1 XOR d(t)           // bucket thứ hai
```

Trong đó, `H1` và `H2` là các phép băm có miền đầu vào tách biệt; `F` cũng được lấy từ hàm băm phân bố đều. Công thức `1 + H2(t) % (m - 1)` trong bài chọn `d(t)` từ `1..m−1` để hai bucket khác nhau. Một số triển khai dùng trực tiếp `H2(t) & (m - 1)`, khi đó độ lệch có thể bằng 0. Do `m` là lũy thừa của hai, phép XOR giữa các chỉ số `0..m−1` vẫn cho ra chỉ số hợp lệ.

Điểm mấu chốt là tính **tự đảo** của XOR:

```text
i2 XOR d(t) = (i1 XOR d(t)) XOR d(t) = i1
```

Khi một fingerprint `t` bị đẩy khỏi bucket hiện tại `i`, thuật toán có thể tính bucket còn lại bằng `i XOR d(t)`. Nó **không cần khóa gốc**. Nếu dùng công thức như `i2 = H3(x)`, thì khi chỉ còn fingerprint trong bộ nhớ, thuật toán sẽ không biết vị trí thay thế của fingerprint bị đẩy ra.

**Ví dụ tính tay.** Giả sử `m = 8`, `i1 = 3` (nhị phân `011`), fingerprint `t = 45` và `d(t) = 5` (nhị phân `101`). Ta có `i2 = 011 XOR 101 = 110 = 6`. Nếu fingerprint đang ở bucket `6`, vị trí còn lại là `6 XOR 5 = 3`. Hai phép tính đều chỉ dùng chỉ số bucket và fingerprint.

Lưu ý: `d(t)` phải được tính nhất quán từ **chính fingerprint đang bị di chuyển**, không tính lại từ fingerprint của khóa mới. Việc đổi cách băm, độ dài fingerprint hoặc quy tắc đánh chỉ số giữa chừng sẽ làm hỏng cách tìm kiếm dữ liệu đã lưu.

## 4. Tra cứu, chèn, di chuyển và xóa

### 4.1. Tra cứu

Với khóa `x`, tính `t, i1, i2`. Nếu fingerprint `t` có trong một trong hai bucket, trả về `có thể có`; nếu không, trả về `không có`. Bộ lọc chỉ đọc tối đa `2b` ô nên thời gian tra cứu là `O(b)`, thường được xem là `O(1)` khi `b` là hằng số nhỏ.

### 4.2. Chèn

Thử đưa `t` vào bucket `i1` hoặc `i2` nếu còn ô trống. Nếu cả hai đều đầy, chọn một bucket ứng viên, chọn ngẫu nhiên một fingerprint `u` trong đó, đặt `t` vào vị trí vừa chọn, rồi chuyển `u` sang bucket còn lại của chính `u`. Lặp lại nếu bucket mới cũng đầy. Đây là cơ chế **cuckoo kicking**, tương tự việc đẩy phần tử trong cuckoo hashing.

```text
insert(x):
    (t, i1, i2) = locations(x)
    nếu B[i1] hoặc B[i2] còn ô trống:
        thêm t vào ô trống; trả về SUCCESS

    i = chọn_ngẫu_nhiên(i1, i2)
    pending = t
    history = []                   // phục vụ hoàn tác nếu thất bại
    lặp tối đa MAX_KICKS lần:
        chọn ngẫu nhiên một ô j trong B[i]
        victim = B[i][j]
        B[i][j] = pending
        history.push((i, j, victim))
        pending = victim
        i = i XOR d(pending)      // bucket còn lại của victim
        nếu B[i] còn ô trống:
            thêm pending; trả về SUCCESS

    hoàn tác history theo thứ tự ngược
    trả về FAILURE
```

Ví dụ, nếu fingerprint `21` đang nằm ở bucket `3` và `d(21) = 2`, sau khi bị đẩy nó chỉ có thể chuyển sang bucket `3 XOR 2 = 1`. Mỗi bước vẫn bảo toàn quy tắc: *fingerprint thuộc một trong đúng hai bucket được phép*. Nếu tìm được ô trống thì toàn bộ chuỗi di chuyển thành công.

**Chèn có thể thất bại**, nhất là khi hệ số lấp đầy cao hoặc các fingerprint tranh chấp cùng vài bucket. Phải đặt giới hạn số lần đẩy `MAX_KICKS` và có cách xử lý thất bại: hoàn tác như giả mã trên, giữ phần tử chưa đặt trong một vùng dự phòng (*stash*) được tra cứu cùng filter, hoặc mở rộng và xây lại từ các khóa gốc. Nếu đã ghi đè các fingerprint mà vẫn báo thất bại, nhưng không hoàn tác/giữ phần tử bị đẩy cuối cùng, filter sẽ sinh **false negative**.

### 4.3. Xóa

Để xóa khóa `x`, tính `t, i1, i2`, tìm **một** ô chứa `t` trong hai bucket và xóa ô đó. Đây là lợi thế của Cuckoo filter so với Bloom filter cơ bản, vốn không thể xóa một khóa bằng cách đơn giản đặt các bit của khóa về 0.

Nhưng việc xóa có **tiền điều kiện quan trọng**: ứng dụng phải biết chắc khóa đã được chèn thành công và còn tồn tại. Nếu xóa một khóa vắng mặt nhưng nó vô tình có fingerprint trùng với khóa khác trong bucket ứng viên, filter có thể xóa nhầm fingerprint đang đại diện cho khóa thật, gây false negative. Nếu cần xử lý nhiều lần chèn cùng một khóa, tầng ứng dụng cũng phải định nghĩa rõ ngữ nghĩa tập hợp hay đa tập và quản lý số lần chèn/xóa tương ứng.

## 5. Mã Python minh họa

Ví dụ dưới đây mô phỏng các bucket bằng danh sách để nhìn rõ thao tác. `blake2b` được dùng để băm ổn định, đồng thời thêm tiền tố riêng cho chỉ số, fingerprint và độ lệch; cách làm này giúp tránh dùng lẫn các miền băm. Đây là mã **giải thích thuật toán**, chưa nén fingerprint xuống từng bit và chưa xử lý truy cập đồng thời.

```python
from hashlib import blake2b
from random import Random


class CuckooFilter:
    def __init__(self, bucket_count=8, bucket_size=2,
                 fingerprint_bits=10, max_kicks=200, seed=7):
        if bucket_count < 2 or bucket_count & (bucket_count - 1):
            raise ValueError("bucket_count phai la luy thua cua 2 va >= 2")
        if bucket_size < 1 or not 1 <= fingerprint_bits <= 32:
            raise ValueError("kich thuoc bucket/fingerprint khong hop le")
        if max_kicks < 1:
            raise ValueError("max_kicks phai duong")
        self.buckets = [[] for _ in range(bucket_count)]
        self.b = bucket_size
        self.f_bits = fingerprint_bits
        self.mask = bucket_count - 1
        self.max_kicks = max_kicks
        self.rng = Random(seed)

    @staticmethod
    def _hash(data):
        return int.from_bytes(blake2b(data, digest_size=8).digest(), "little")

    def _delta(self, fp):
        width = (self.f_bits + 7) // 8
        data = fp.to_bytes(width, "little")
        return 1 + self._hash(b"alt:" + data) % self.mask

    def _locations(self, key):
        data = key.encode("utf-8")  # vi du chi nhan khoa chuoi
        i1 = self._hash(b"idx:" + data) & self.mask
        fp = 1 + self._hash(b"fp:" + data) % ((1 << self.f_bits) - 1)
        return fp, i1, i1 ^ self._delta(fp)

    def might_contain(self, key):
        fp, i1, i2 = self._locations(key)
        return fp in self.buckets[i1] or fp in self.buckets[i2]

    def insert(self, key):
        fp, i1, i2 = self._locations(key)
        for i in (i1, i2):
            if len(self.buckets[i]) < self.b:
                self.buckets[i].append(fp)
                return True

        i = self.rng.choice((i1, i2))
        pending = fp
        history = []
        for _ in range(self.max_kicks):
            slot = self.rng.randrange(self.b)
            victim = self.buckets[i][slot]
            history.append((i, slot, victim))
            self.buckets[i][slot] = pending
            pending = victim
            i ^= self._delta(pending)
            if len(self.buckets[i]) < self.b:
                self.buckets[i].append(pending)
                return True

        for i, slot, victim in reversed(history):
            self.buckets[i][slot] = victim
        return False

    def delete(self, key):
        fp, i1, i2 = self._locations(key)
        for i in (i1, i2):
            if fp in self.buckets[i]:
                self.buckets[i].remove(fp)
                return True
        return False


cf = CuckooFilter()
assert cf.insert("order-2048")
assert cf.might_contain("order-2048")
assert cf.delete("order-2048")
assert not cf.might_contain("order-2048")
```

Ở đây, `insert` trả về `False` khi không thể đặt phần tử sau số lần thử tối đa; nhờ lịch sử hoàn tác, trạng thái trước thao tác được khôi phục. `delete` trả về `True` chỉ có nghĩa là đã tìm và xóa một fingerprint trùng khớp, **không xác nhận danh tính khóa**. Các `assert` cuối dùng một khóa duy nhất để tránh nhập nhằng do va chạm. Bộ nhớ thực tế của Python lớn hơn rất nhiều so với con số `f` bit/fingerprint vì mỗi số nguyên và mỗi danh sách đều có chi phí đối tượng.

## 6. Xác suất dương tính giả và chi phí bộ nhớ

Giả sử fingerprint phân bố gần đều, mỗi bucket có `b` ô, và hai bucket ứng viên chứa tối đa `2b` fingerprint. Với truy vấn một khóa chưa được chèn, xác suất fingerprint của nó trùng với ít nhất một ô có thể **xấp xỉ**:

```text
p ≈ 1 - (1 - 1 / (2^f - 1))^(2b) ≈ 2b / 2^f
```

Đây là công thức thiết kế gần đúng trong điều kiện băm phù hợp; mức lấp đầy, phân bố hash, sự phụ thuộc giữa các bucket và cách cài đặt đều có thể ảnh hưởng tỷ lệ đo được. Để nhắm đến một ngưỡng `p`, có thể ước lượng ban đầu:

```text
f >= ceil(log2(2b / p))
```

Với `b = 4`:

| Mục tiêu dương tính giả | Chọn `f` tối thiểu theo ước lượng | Xấp xỉ `8 / 2^f` |
|---|---:|---:|
| 1% | 10 bit | 0,781% |
| 0,1% | 13 bit | 0,098% |
| 0,01% | 17 bit | 0,0061% |

**Ví dụ kích thước.** Một filter với `m = 1.024` bucket, `b = 4` và `f = 10` có `4.096` ô. Nếu triển khai nén chặt fingerprint, phần lưu fingerprint cần `1.024 × 4 × 10 = 40.960` bit, tức **5.120 byte**. Ở hệ số lấp đầy `α = 0,90`, số khóa đang được biểu diễn khoảng `3.686`, tương đương `10 / 0,90 ≈ 11,1` bit cho mỗi khóa. Con số này **chưa tính** bit đánh dấu ô trống, header, căn chỉnh vùng nhớ, vùng dự phòng hay các cấu trúc hỗ trợ.

Để lên kế hoạch cho `n` khóa, số bucket lý thuyết tối thiểu được ước lượng bằng `m ≥ ceil(n / (b × α))`. Nếu triển khai yêu cầu `m` là lũy thừa của hai, phải làm tròn lên và tính lại độ lấp đầy thực tế. Đừng xem `α = 0,90` hay `0,95` là một cam kết mọi cấu hình đều chèn được: ngưỡng chèn thành công phụ thuộc `b`, `f`, thuật toán đẩy và phân bố dữ liệu.

### Độ phức tạp

| Thao tác | Chi phí | Điều cần nhớ |
|---|---|---|
| Tra cứu | `O(b)`, thường coi là `O(1)` | Chỉ kiểm tra hai bucket |
| Xóa | `O(b)` | Chỉ an toàn khi biết chắc khóa đang có |
| Chèn khi bucket còn chỗ | `O(b)` | Có thể ghi trực tiếp |
| Chèn phải đẩy | Tối đa `O(MAX_KICKS × b)` | Có thể thất bại, cần rollback/stash |
| Lưu trữ | `O(m × b × f)` bit cho fingerprint | Phụ thuộc cách đóng gói ô |

## 7. So sánh với Bloom filter và lựa chọn thiết kế

| Tiêu chí | Bloom filter cơ bản | Counting Bloom filter | Cuckoo filter |
|---|---|---|---|
| Dữ liệu lưu | Mảng bit | Mảng bộ đếm | Fingerprint trong các bucket |
| Tra cứu gần đúng | Có | Có | Có |
| Xóa riêng từng khóa | Không an toàn nếu chỉ xóa bit | Có, khi duy trì bộ đếm đúng | Có, khi khóa chắc chắn đã chèn |
| Chèn khi gần đầy | Vẫn đặt bit nhưng sai số tăng | Vẫn cập nhật nếu bộ đếm chưa tràn | Có thể chèn thất bại |
| Nguồn dương tính giả | Các bit được chia sẻ | Các bộ đếm được chia sẻ | Trùng fingerprint tại bucket ứng viên |

Cuckoo filter thường phù hợp khi ứng dụng **cần xóa khóa** và muốn giữ tra cứu gọn trong bộ nhớ. Bloom filter cơ bản đơn giản hơn khi dữ liệu chỉ được thêm và không xóa. Hiệu quả bộ nhớ giữa các phương án thay đổi theo tỷ lệ dương tính giả mục tiêu, tải dữ liệu, cách đóng gói và chi phí metadata; không có cấu trúc nào luôn tốt hơn ở mọi cấu hình.

Ví dụ trong một dịch vụ kiểm tra mã giao dịch, tầng dữ liệu chính xác (cơ sở dữ liệu hoặc tập hợp khóa) là nguồn sự thật:

1. Mã bị filter trả về **không có**: có thể bỏ qua truy vấn xác minh tồn tại *nếu* filter đồng bộ đầy đủ và nhất quán với nguồn dữ liệu.
2. Mã trả về **có thể có**: vẫn phải truy vấn nguồn chính xác trước khi kết luận trùng.
3. Khi một mã được lưu/xóa thành công ở nguồn chính xác, cập nhật filter theo thứ tự và cơ chế đồng bộ đã thiết kế; nếu filter không còn tin cậy, phải xây lại từ dữ liệu gốc.

## 8. Những lỗi triển khai thường gặp

- **Băm lại sai khi đẩy fingerprint:** dùng khóa mới để tính bucket cho fingerprint bị đẩy. Cách đúng là `i_mới = i_hiện_tại XOR d(fingerprint_bị_đẩy)`.
- **Xóa dựa trên kết quả “có thể có”:** trả lời dương tính không chứng minh khóa tồn tại. Chỉ xóa khi có bằng chứng từ nguồn dữ liệu chính xác, đồng thời cân nhắc số lần chèn trùng.
- **Không xử lý chèn thất bại:** một fingerprint bị đẩy cuối cùng có thể bị mất. Phải rollback, dùng stash, hoặc xây lại; ứng dụng cần biết chèn đã thành công hay chưa.
- **Tăng kích thước filter bằng cách copy bucket:** số bucket mới làm thay đổi `i1` và `i2`. Thông thường phải dựng lại từ các khóa gốc; fingerprint cũ không đủ để tái tạo chỉ số ban đầu của khóa.
- **Đánh giá bộ nhớ từ `f` mà bỏ qua lưu trữ:** mảng đối tượng, padding, bit đánh dấu và độ lấp đầy thấp có thể khiến chi phí lớn hơn nhiều so với `f/α`.
- **Đổi hash hoặc xử lý đồng thời không an toàn:** việc thay đổi seed, hàm hash hay ghi/xóa trong lúc đang kick có thể phá bất biến. Triển khai thực tế cần thông số băm ổn định, đồng bộ hóa thao tác và kiểm tra dữ liệu khi khôi phục.
- **Tin rằng dữ liệu đầu vào luôn ngẫu nhiên:** nếu đối tượng sử dụng có thể cố tình tạo nhiều va chạm, cần cân nhắc hash có khóa bí mật, giới hạn công việc mỗi lần chèn và giám sát tỷ lệ thất bại.

## 9. Tự kiểm tra

**Câu 1.** Với `m = 16`, một fingerprint có `d(t) = 9` và đang nằm tại bucket `5`. Bucket còn lại là gì?\
**Đáp án:** `5 XOR 9 = 12`. Từ bucket `12`, tính `12 XOR 9 = 5`.

**Câu 2.** Với `b = 4` và mục tiêu dương tính giả khoảng `0,1%`, nên bắt đầu thử fingerprint bao nhiêu bit?\
**Đáp án:** `ceil(log2(8 / 0,001)) = 13` bit; sau đó đo bằng dữ liệu và cấu hình thực tế.

**Câu 3.** Vì sao không thể gọi `delete(x)` chỉ vì `might_contain(x)` trả về `True`?\
**Đáp án:** `True` có thể là dương tính giả. Xóa fingerprint trùng trong bucket ứng viên có thể xóa nhầm dấu vân tay của một khóa thật.

**Câu 4.** Điều gì phải xảy ra nếu chuỗi cuckoo kicking chạm giới hạn mà chưa tìm được ô trống?\
**Đáp án:** Phải giữ nguyên tập các fingerprint đang được biểu diễn: hoàn tác chuỗi ghi đè, bảo quản fingerprint chưa đặt trong stash, hoặc xử lý xây lại từ khóa gốc. Không được âm thầm làm mất fingerprint.

Khi thiết kế Cuckoo filter, hãy xác định rõ **tỷ lệ dương tính giả chấp nhận được**, **số khóa tối đa**, **độ lấp đầy dự kiến**, **ngữ nghĩa xóa**, và **cách xử lý chèn thất bại**. Chính các ràng buộc đó quyết định `f`, `b`, `m` và độ an toàn của bộ lọc trong hệ thống thực tế.
