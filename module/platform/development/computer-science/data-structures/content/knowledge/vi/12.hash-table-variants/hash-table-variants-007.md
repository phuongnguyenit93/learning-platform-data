# Băm có thể mở rộng và thư mục các nhóm khóa

Trong bảng băm có kích thước cố định, khi số khóa tăng, **hệ số tải** tăng và các thao tác tìm kiếm, chèn có thể chậm vì va chạm. Cách xử lý quen thuộc là mở rộng mảng rồi băm lại gần như toàn bộ phần tử. Với dữ liệu lớn được lưu theo **khối** hoặc **trang đĩa**, việc di chuyển mọi phần tử mỗi lần mở rộng có thể tốn nhiều I/O.

**Băm có thể mở rộng** (*extendible hashing*) giải quyết vấn đề bằng một **thư mục** (*directory*) chứa các con trỏ tới **nhóm khóa** (*bucket*). Mỗi bucket chứa một số lượng giới hạn bản ghi. Khi một bucket đầy, ta chủ yếu **tách bucket đó**; chỉ khi cần thêm một bit để phân biệt các nhóm, thư mục mới phải **nhân đôi**. Nhờ vậy, cấu trúc có thể phát triển theo lượng dữ liệu mà không phải tái phân phối tất cả bucket ở mỗi lần chèn.

Bài học thuộc chương **Biến thể bảng băm** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trọng tâm là bất biến của thư mục và bucket, thuật toán tra cứu–chèn–xóa, trường hợp tách không cần nhân đôi, độ phức tạp thời gian/bộ nhớ và các điều kiện để lựa chọn cấu trúc phù hợp.

## 1. Ba thành phần của extendible hashing

Một bảng băm có thể mở rộng gồm ba thành phần chính:

1. **Hàm băm** \(h(k)\): chuyển khóa thành chuỗi bit đủ dài và phân bố tương đối đều.
2. **Thư mục** \(D\): mảng các con trỏ. Thư mục có \(2^g\) mục, trong đó \(g\) là **độ sâu toàn cục** (*global depth*).
3. **Các bucket**: mỗi bucket lưu tối đa \(B\) bản ghi trong mô hình đơn giản. Mỗi bucket có **độ sâu cục bộ** (*local depth*) riêng, ký hiệu \(\ell\).

Để trình bày nhất quán, bài học sử dụng **\(g\) bit thấp nhất** (các bit bên phải) của giá trị băm để đánh chỉ số thư mục:

\[
\boxed{\operatorname{dirIndex}(k)=h(k)\ \&\ (2^g-1).}
\]

Với \(g=2\), thư mục có bốn mục, gắn chỉ số nhị phân \(00,01,10,11\). Một số tài liệu lựa chọn **bit cao nhất** hoặc dùng bit tiền tố; đó cũng là biến thể hợp lệ nếu toàn bộ thao tác dùng nhất quán một quy ước. Các ví dụ dưới đây chỉ dùng **bit thấp nhất**.

~~~text
Khóa k
  |
  v
h(k)  ---> lấy g bit thấp nhất ---> D[index] ----> bucket chứa bản ghi

         D[00] ───────────> Bucket A
         D[01] ───────────> Bucket B
         D[10] ───────────> Bucket A  (cùng bucket với D[00])
         D[11] ───────────> Bucket C
~~~

**Điểm quan trọng:** Các mục thư mục là **con trỏ**, không nhất thiết là những bucket vật lý khác nhau. Nhiều mục hoàn toàn có thể trỏ tới **cùng một bucket**. Đây là lý do thư mục có thể nhân đôi số mục mà chỉ một nhóm khóa cần tách.

## 2. Global depth và local depth

### Global depth \(g\): số bit để tra thư mục

Thư mục có đúng \(2^g\) mục. Khi \(g\) tăng từ 2 lên 3, thư mục tăng từ 4 lên 8 con trỏ. Việc tăng \(g\) **không đồng nghĩa với tạo gấp đôi số bucket vật lý**.

### Local depth \(\ell\): số bit phân biệt một bucket

Mỗi bucket \(b\) có độ sâu cục bộ \(\ell_b\). Các mục thư mục trỏ tới bucket đó có cùng **\(\ell_b\) bit thấp nhất**. Các bucket khác nhau có thể có độ sâu cục bộ khác nhau.

**Bất biến cần giữ:**

\[
\boxed{0\leq \ell_b\leq g.}
\]

Nếu một bucket có \(\ell_b\) bit nhận dạng, thì trong bảng thư mục đầy đủ, số mục trỏ tới bucket là:

\[
\boxed{2^{g-\ell_b}.}
\]

Ví dụ với \(g=3\):

| Bucket | Local depth | Các chỉ số thư mục cùng trỏ tới bucket | Số con trỏ |
| --- | ---: | --- | ---: |
| A, nhận dạng bằng bit thấp **0** | 1 | 000, 010, 100, 110 | 4 |
| B, nhận dạng bằng hai bit thấp **01** | 2 | 001, 101 | 2 |
| C, nhận dạng bằng ba bit thấp **011** | 3 | 011 | 1 |
| D, nhận dạng bằng ba bit thấp **111** | 3 | 111 | 1 |

Trong cấu hình đầy đủ này, cả tám mục thư mục đều được bao phủ đúng một lần bởi bốn bucket vật lý. Các mẫu bit nhận dạng **không được chồng lên nhau**: chẳng hạn, nếu bucket B đã nhận dạng bằng hai bit thấp **01** thì không thể thêm một bucket riêng nhận dạng bằng ba bit thấp **101** mà vẫn giữ nguyên B, vì mục 101 đã trỏ tới B.

### Hai bất biến bổ sung

- **Bất biến ánh xạ:** Mỗi khóa \(k\) trong bucket \(b\) phải thỏa \(D[\operatorname{dirIndex}(k)]=b\).
- **Bất biến dung lượng:** Mỗi bucket có tối đa \(B\) bản ghi trong phiên bản không dùng overflow page.

Từ ba bất biến này, người học có thể kiểm tra đúng/sai của thuật toán chèn, tách và gộp.

## 3. Tra cứu và cập nhật giá trị

Tra cứu một khóa \(k\) cần:

1. Tính \(h(k)\).
2. Lấy \(g\) bit thấp để được chỉ số \(i\) của thư mục.
3. Theo con trỏ \(D[i]\) tới bucket được chọn.
4. Tìm khóa thật trong bucket; nếu gặp khóa, trả giá trị tương ứng.

~~~text
FIND(k):
    i = low_bits(h(k), g)
    b = D[i]
    for record in b:
        if record.key == k:
            return record.value
    return NOT_FOUND
~~~

Phải **so sánh khóa thật**, vì nhiều khóa có thể thuộc cùng một bucket. Nếu chỉ nhìn con trỏ thư mục rồi kết luận khóa tồn tại, ta có thể trả về bản ghi sai.

Nếu chỉ **đổi giá trị** của khóa đã tồn tại, không cần tách bucket hay cập nhật thư mục: chỉ cập nhật bản ghi đó trong bucket hiện hành. Nếu khóa chưa có và bucket còn chỗ, chèn trực tiếp.

Khi bucket đầy, quy trình tách sẽ dựa trên **so sánh local depth và global depth**.

## 4. Tách bucket: hai trường hợp quyết định

Giả sử bucket \(b\) đang đầy, cần chèn khóa \(x\). Gọi \(\ell\) là local depth hiện tại của bucket đó và \(g\) là global depth của thư mục.

### Trường hợp A: \(\ell<g\) — tách bucket, không nhân đôi thư mục

Đã có đủ bit trong thư mục để phân biệt hai nhóm con. Ta:

1. Tạo bucket mới và tăng local depth của cả bucket cũ và mới từ \(\ell\) lên \(\ell+1\).
2. Xét **bit vị trí \(\ell\)** của chỉ số thư mục (đếm từ 0 ở bit thấp nhất).
3. Các mục từng trỏ tới bucket cũ có bit đó bằng 0 tiếp tục trỏ bucket cũ; các mục có bit đó bằng 1 trỏ bucket mới.
4. Phân phối lại **những khóa trong bucket vừa tách** theo \(\ell+1\) bit thấp của hàm băm; thử chèn khóa mới.

~~~text
Trước: g=2, một bucket local depth=1
D[00] ──┐
        ├──> Bucket even [2, 4]
D[10] ──┘

Tách (không tăng g):
D[00] ─────> Bucket "00" [4]      local depth=2
D[10] ─────> Bucket "10" [2, 6]   local depth=2
~~~

Không phải đổi con trỏ của các bucket khác. Đây là ưu điểm của cấu trúc thư mục: **tách cục bộ khi \(g\) đã đủ lớn**.

### Trường hợp B: \(\ell=g\) — nhân đôi thư mục rồi tách

Toàn bộ \(g\) bit hiện có đang nhận dạng bucket này; chưa có bit tiếp theo trong thư mục để phân biệt hai nhóm con. Do vậy:

1. **Nhân đôi mảng con trỏ thư mục**: tăng \(g\) thành \(g+1\). Với cách lấy bit thấp của bài, nửa trên ban đầu là bản sao các con trỏ ở nửa dưới.
2. Tách bucket như trường hợp A, nâng local depth lên \(\ell+1=g\) mới.
3. Chỉ cập nhật những con trỏ liên quan tới bucket vừa tách, rồi phân phối lại khóa trong bucket đó.

~~~text
Trước: g=1                  Sau nhân đôi: g=2
D[0] → Bucket even          D[00] → Bucket even
D[1] → Bucket odd           D[01] → Bucket odd
                             D[10] → Bucket even
                             D[11] → Bucket odd

Sau tách bucket odd:
D[00] → Bucket even, local depth=1
D[01] → Bucket "01", local depth=2
D[10] → Bucket even, local depth=1
D[11] → Bucket "11", local depth=2
~~~

**Nhân đôi thư mục chỉ sao chép con trỏ**, không sao chép mọi bản ghi trong các bucket. Phân phối lại bản ghi chỉ cần thực hiện trên **bucket đang bị tách**.

~~~mermaid
flowchart TD
    A[Chèn khóa mới k] --> B[Tính i từ g bit của h(k)]
    B --> C[Đến bucket D[i]]
    C --> D{Khóa đã có?}
    D -->|Có| E[Cập nhật giá trị hoặc bỏ qua]
    D -->|Không| F{Bucket còn chỗ?}
    F -->|Có| G[Chèn bản ghi]
    F -->|Không| H{Local depth nhỏ hơn global depth?}
    H -->|Có| I[Tách bucket và phân phối lại khóa]
    H -->|Không| J[Tăng g và nhân đôi thư mục]
    J --> I
    I --> B
~~~

Vòng lặp về bước tra thư mục là cần thiết: **sau tách, bucket mới vẫn có thể đầy** nếu nhiều khóa có chung các bit thấp. Khi đó có thể phải tách tiếp.

## 5. Ví dụ xuyên suốt với bucket chứa tối đa hai khóa

Để dễ tính tay, chọn:

- **Dung lượng bucket** \(B=2\) bản ghi.
- **Hàm băm minh họa** \(h(k)=k\) cho khóa nguyên không âm.
- **Dùng bit thấp nhất** để chọn thư mục.
- Ban đầu \(g=1\), có hai bucket với local depth đều bằng 1.

Hàm \(h(k)=k\) ở đây giúp dễ quan sát nhị phân, **không phải lựa chọn khuyến nghị** cho dữ liệu thực tế có mẫu khóa bất lợi. Trong hệ thống thật, hàm băm cần tạo chuỗi bit phân bố tốt.

### Bước 1: chèn 1 rồi 3

Vì cả 1 và 3 đều có bit thấp nhất là 1, chúng thuộc bucket lẻ.

| Chỉ số thư mục | Bucket được trỏ tới | Local depth | Khóa |
| --- | --- | ---: | --- |
| 0 | Even | 1 | ∅ |
| 1 | Odd | 1 | 1, 3 |

Bucket Odd đầy, nhưng cả hai khóa vẫn được lưu đúng.

### Bước 2: chèn 5 — phải nhân đôi thư mục

Khóa 5 cũng có bit thấp 1, nên đi vào Odd. Vì Odd có \(\ell=1=g\), ta **nhân đôi thư mục**, tăng \(g=2\), rồi tách Odd theo **hai bit thấp**:

| Khóa | Nhị phân ở hai bit thấp | Bucket mới |
| ---: | --- | --- |
| 1 | 01 | Odd-01 |
| 3 | 11 | Odd-11 |
| 5 | 01 | Odd-01 |

Trạng thái sau chèn:

| Chỉ số \(g=2\) | Bucket vật lý | Local depth | Khóa |
| --- | --- | ---: | --- |
| 00 | Even | 1 | ∅ |
| 01 | Odd-01 | 2 | **1, 5** |
| 10 | Even | 1 | ∅ |
| 11 | Odd-11 | 2 | **3** |

Hai mục **00** và **10** vẫn trỏ tới **cùng một bucket Even**; chúng chưa cần tách. Nhân đôi thư mục đã tạo bốn **mục con trỏ**, nhưng chỉ có **ba bucket vật lý**.

### Bước 3: chèn 2, 4 rồi 6 — tách mà không nhân đôi

Khóa 2 và 4 cùng có bit thấp 0 nên đi vào Even, làm bucket này đầy. Chèn 6 cũng có bit thấp 0. Lúc này Even có **local depth \(\ell=1\)** còn thư mục có **global depth \(g=2\)**, vì vậy \(\ell<g\): chỉ cần **tách Even**.

Theo hai bit thấp:

| Khóa | Hai bit thấp | Bucket sau tách |
| ---: | --- | --- |
| 2 | 10 | Even-10 |
| 4 | 00 | Even-00 |
| 6 | 10 | Even-10 |

Trạng thái cuối sau sáu khóa:

| Mục thư mục | Bucket vật lý | Local depth | Khóa |
| --- | --- | ---: | --- |
| 00 | Even-00 | 2 | **4** |
| 01 | Odd-01 | 2 | **1, 5** |
| 10 | Even-10 | 2 | **2, 6** |
| 11 | Odd-11 | 2 | **3** |

~~~text
g = 2                           B = 2

Directory                     Bucket vật lý
  00 ────────────────────> [4]          (l=2)
  01 ────────────────────> [1, 5]       (l=2)
  10 ────────────────────> [2, 6]       (l=2)
  11 ────────────────────> [3]          (l=2)
~~~

Lúc này thư mục vẫn chỉ có **bốn mục**, dù chúng ta vừa chèn thêm ba khóa. Ta đã mở rộng bằng **tách một bucket**, không nhân đôi toàn bộ thư mục thêm lần nữa.

### Đọc và kiểm tra bất biến trên ví dụ

Tìm khóa **6**: lấy hai bit thấp của \(h(6)=6\) là **10**, theo \(D[10]\) đến Even-10 rồi đọc các khóa **2, 6**. Thấy 6 nên trả về **tìm thấy**.

Tìm khóa **7**: hai bit thấp là **11**, đến Odd-11 chứa 3, so sánh \(3\ne7\), trả về **không tìm thấy**.

Trên cấu hình cuối, mọi bucket đều có \(\ell=2=g\) và mỗi bucket có không quá \(B=2\) khóa. Các khóa 1 và 5 cùng chia sẻ hai bit thấp 01 nên cùng một bucket; việc kiểm tra khóa thật là bắt buộc.

## 6. Xóa khóa, gộp bucket và thu nhỏ thư mục

Xóa một khóa không nhất thiết buộc phải gộp bucket ngay. Một triển khai đơn giản có thể chỉ xóa bản ghi và **giữ nguyên thư mục**, đổi lại là có thể duy trì nhiều bucket trống hoặc ít sử dụng.

Một biến thể tiết kiệm bộ nhớ có thể **gộp hai bucket buddy** sau xóa. Với quy ước bit thấp của bài, hai bucket buddy ở độ sâu cục bộ \(\ell\) là hai bucket khác nhau có cùng \(\ell-1\) bit thấp, và khác nhau ở **bit thứ \(\ell-1\)**.

Có thể gộp khi thỏa đồng thời:

1. Hai bucket có **cùng local depth \(\ell\)** và đúng là cặp buddy của nhau.
2. Tổng số bản ghi của hai bucket **không vượt quá \(B\)**.
3. Việc đổi con trỏ thư mục và giảm local depth xuống \(\ell-1\) vẫn giữ đúng bất biến ánh xạ.

Sau gộp, nhiều mục thư mục có thể cùng trỏ về bucket mới với local depth \(\ell-1\). Nếu **không còn bucket nào có local depth bằng global depth \(g\)**, ta có thể giảm \(g\) đi 1 và **thu nhỏ thư mục một nửa**. Một số cách cài đặt giữ \(g\ge1\), số khác cho phép thư mục có một mục khi \(g=0\).

### Ví dụ xóa và gộp từ bảng ở mục 5

Trước xóa:

~~~text
g = 2
00 → [4]       l=2       01 → [1, 5]    l=2
10 → [2, 6]    l=2       11 → [3]       l=2
~~~

**Xóa khóa 1:** Odd-01 còn [5]; buddy của nó là Odd-11 chứa [3]. Vì tổng có \(1+1=B=2\) khóa, có thể gộp thành **một bucket lẻ** local depth 1. Khi đó D[01] và D[11] cùng trỏ tới bucket [5, 3]. Nhưng Even-00 và Even-10 vẫn có local depth 2, nên **global depth vẫn bằng 2**.

**Xóa khóa 2:** Even-10 còn [6]; buddy Even-00 có [4]. Tổng là 2, nên gộp thành một bucket chẵn local depth 1. Lúc này mọi bucket đều có local depth 1, vì vậy có thể giảm global depth từ **2 xuống 1** và thu nhỏ thư mục:

~~~text
g = 1
D[0] → [4, 6]      local depth=1
D[1] → [5, 3]      local depth=1
~~~

**Cẩn thận:** Gộp không phải cứ hai bucket cùng ít bản ghi là được. Chúng phải là **buddy đúng nghĩa**, cùng local depth và có thể giảm chung một bit phân biệt. Gộp sai sẽ khiến một số chỉ số thư mục trỏ nhầm bucket.

## 7. Cài đặt Python minh họa thư mục động

Mã dưới đây thể hiện hai trường hợp tách, cập nhật con trỏ thư mục, tra cứu và xóa/gộp. Mỗi bucket chứa tối đa **B** cặp khóa–giá trị. Để có thể quan sát các bit trực tiếp, mã dùng khóa nguyên không âm và **hàm băm đồng nhất \(h(k)=k\)** trong một miền giá trị giới hạn. Đây là mã **minh họa thuật toán**, không phải hàm băm hay hệ lưu trữ khuyến nghị cho đầu vào đối kháng.

~~~python
class Bucket:
    def __init__(self, local_depth):
        self.local_depth = local_depth
        self.items = []  # Danh sách (key, value)


class ExtendibleHash:
    def __init__(self, bucket_capacity=2, max_hash_bits=16):
        if type(bucket_capacity) is not int or bucket_capacity < 1:
            raise ValueError("bucket_capacity phải >= 1")
        if type(max_hash_bits) is not int or max_hash_bits < 1:
            raise ValueError("max_hash_bits phải >= 1")

        self.capacity = bucket_capacity
        self.max_bits = max_hash_bits
        self.global_depth = 1
        self.directory = [Bucket(1), Bucket(1)]
        self.size = 0

    def _check_key(self, key):
        if type(key) is not int or not (0 <= key < (1 << self.max_bits)):
            raise ValueError("Khóa phải là int không âm trong miền đã chọn")

    def _index(self, key):
        return key & ((1 << self.global_depth) - 1)

    def _bucket(self, key):
        return self.directory[self._index(key)]

    def lookup(self, key):
        """Trả về (found, value) để phân biệt vắng mặt với value=None."""
        self._check_key(key)
        for k, value in self._bucket(key).items:
            if k == key:
                return True, value
        return False, None

    def _split(self, key, bucket):
        old_depth = bucket.local_depth

        # Nếu local depth = global depth thì nhân đôi directory.
        if old_depth == self.global_depth:
            if self.global_depth == self.max_bits:
                raise RuntimeError("Hết bit băm, cần chiến lược khác")
            self.directory += self.directory[:]  # Sao chép con trỏ.
            self.global_depth += 1

        # Bit số old_depth phân biệt hai bucket con.
        new_bucket = Bucket(old_depth + 1)
        bucket.local_depth = old_depth + 1
        low_bits = key & ((1 << old_depth) - 1)

        # Chỉ cập nhật các mục đang trỏ tới bucket và có bit mới = 1.
        start = low_bits | (1 << old_depth)
        step = 1 << (old_depth + 1)
        for i in range(start, len(self.directory), step):
            if self.directory[i] is bucket:
                self.directory[i] = new_bucket

        # Chỉ phân phối lại bản ghi của bucket vừa tách.
        old_items = bucket.items
        bucket.items = []
        for old_key, value in old_items:
            self._bucket(old_key).items.append((old_key, value))

    def put(self, key, value):
        self._check_key(key)

        while True:
            bucket = self._bucket(key)
            for pos, (old_key, _) in enumerate(bucket.items):
                if old_key == key:
                    bucket.items[pos] = (key, value)
                    return False  # Đã cập nhật khóa hiện có.

            if len(bucket.items) < self.capacity:
                bucket.items.append((key, value))
                self.size += 1
                return True

            # Bucket đầy; tách rồi thử lại với chỉ số mới.
            self._split(key, bucket)

    def _try_merge(self, key, bucket):
        # Ở đây giữ thư mục có ít nhất hai mục (g >= 1).
        while bucket.local_depth > 1:
            depth = bucket.local_depth
            index = self._index(key)
            buddy_index = index ^ (1 << (depth - 1))
            buddy = self.directory[buddy_index]

            if (buddy is bucket
                    or buddy.local_depth != depth
                    or len(bucket.items) + len(buddy.items) > self.capacity):
                break

            merged = Bucket(depth - 1)
            merged.items = bucket.items + buddy.items

            # Cả hai nhóm con nay trỏ tới một bucket cha.
            for i, ref in enumerate(self.directory):
                if ref is bucket or ref is buddy:
                    self.directory[i] = merged
            bucket = merged

        # Có thể giảm g nếu tất cả local depth đều nhỏ hơn g.
        while self.global_depth > 1:
            if any(b.local_depth == self.global_depth for b in self.directory):
                break
            self.directory = self.directory[:len(self.directory) // 2]
            self.global_depth -= 1

    def delete(self, key):
        self._check_key(key)
        bucket = self._bucket(key)
        for pos, (old_key, _) in enumerate(bucket.items):
            if old_key == key:
                bucket.items.pop(pos)
                self.size -= 1
                self._try_merge(key, bucket)
                return True
        return False

    def show(self):
        for i, bucket in enumerate(self.directory):
            print(
                f"{i:0{self.global_depth}b}: "
                f"depth={bucket.local_depth}, "
                f"keys={[key for key, _ in bucket.items]}"
            )


table = ExtendibleHash(bucket_capacity=2)
for key in [1, 3, 5, 2, 4, 6]:
    table.put(key, f"value-{key}")

print(table.global_depth)  # 2
table.show()                # 00:[4], 01:[1,5], 10:[2,6], 11:[3]
print(table.lookup(6))      # (True, 'value-6')
print(table.lookup(7))      # (False, None)

table.delete(1)
table.delete(2)
print(table.global_depth)  # 1: cả hai cặp buddy đã gộp
table.show()                # 0:[4,6], 1:[5,3]
~~~

### Đọc những điểm cốt lõi trong mã

- **Thư mục chứa tham chiếu đến đối tượng Bucket:** dùng phép kiểm tra danh tính đối tượng khi cập nhật để biết những mục nào đang cùng trỏ một bucket.
- **Nhân đôi thư mục** bằng cách lặp lại danh sách tham chiếu, không tạo bản sao của các bucket cũ.
- Khi tách, **chỉ cập nhật các chỉ số có bit phân biệt mới bằng 1** trong những mục tương ứng với bucket cũ.
- **Phân phối lại đúng một bucket** khi tách, không quét và băm lại tất cả khóa ở bucket khác.
- Khi xóa, chỉ gộp **buddy có cùng local depth** và tổng khóa không vượt dung lượng.
- Hàm tra cứu trả về cặp **(found, value)** để hỗ trợ cả trường hợp giá trị đã lưu chính là **None**.

Trong ví dụ, thao tác _try_merge quét các con trỏ thư mục để sửa tham chiếu khi gộp. Triển khai cho hệ lưu trữ thật có thể tối ưu bằng cách xác định trực tiếp các dải chỉ số chia sẻ cùng bucket; bên cạnh đó cần cơ chế duy trì tính nhất quán khi nhiều luồng đọc và ghi đồng thời.

## 8. Trường hợp các khóa không thể được tách bằng bit hiện có

Giả sử một bucket đầy và các khóa của nó có cùng **nhiều bit thấp** trong giá trị băm. Khi tách, chúng vẫn có thể rơi vào cùng một bucket con; thuật toán phải thử thêm bit ở mức sâu hơn.

Ví dụ các khóa **1, 257 và 513** đều có tám bit thấp giống nhau là **00000001**. Với bucket dung lượng 2 và hàm minh họa \(h(k)=k\), chỉ tăng từ độ sâu 1 đến 2 hoặc 3 chưa đủ phân biệt cả ba khóa. Phải xét đến **bit thứ 8** (đếm từ 0) mới tách được một số khóa. Nếu chọn hàm băm phù hợp hơn, các giá trị băm có thể phân bố đều hơn và tránh nhu cầu tăng độ sâu quá nhanh.

Nếu hai khóa phân biệt có **giá trị băm giống hệt nhau trên toàn bộ số bit được phép sử dụng**, tăng global depth cũng không thể phân biệt chúng. Với số khóa trùng giá trị băm nhiều hơn dung lượng bucket, cấu trúc thuần túy không thể tiếp tục tách thành công.

Cần một chiến lược rõ ràng: **đổi seed/hàm băm và xây dựng lại**, dùng **trang tràn** (*overflow page*), cấu trúc phụ cho va chạm hoặc giới hạn độ sâu. Không được để vòng tách lặp vô hạn hoặc tạo thư mục có kích thước không kiểm soát.

Trong mã Python ở mục 7, các khóa nguyên bị giới hạn vào một miền \(0\le k<2^{\mathrm{max\_bits}}\) và hàm đồng nhất giúp mọi **khóa phân biệt** có chuỗi bit khác nhau trong miền đó. Dù vậy, hai khóa khác nhau ở bit rất cao vẫn có thể buộc thư mục lớn nếu số khóa ít; đây là **giới hạn bộ nhớ của cách minh họa**, không phải một giải pháp sản xuất.

## 9. Độ phức tạp về thời gian và bộ nhớ

Gọi \(n\) là số khóa phân biệt, \(B\) là dung lượng của một bucket và \(g\) là global depth. Giả sử hàm băm đã được tính, thao tác trên chỉ số và con trỏ có chi phí hằng số.

| Thao tác hoặc tài nguyên | Chi phí | Lưu ý |
| --- | --- | --- |
| **Tra chỉ số thư mục** | \(O(1)\) | Lấy \(g\) bit thấp và đọc một con trỏ |
| **Tìm kiếm** | \(O(B)\) nếu bucket dò tuyến tính; thành \(O(1)\) khi \(B\) cố định | Đọc đúng một bucket vật lý, rồi so sánh các bản ghi trong bucket |
| **Chèn không tách** | \(O(B)\) | Kiểm tra khóa và chèn trong bucket còn chỗ |
| **Tách bucket** | Phân phối lại \(O(B)\) bản ghi, cộng chi phí cập nhật con trỏ | Có thể phải tách nhiều lần nếu các bit chưa phân biệt được khóa |
| **Nhân đôi thư mục** | \(O(2^g)\) con trỏ tại thời điểm mở rộng | Số mục tăng từ \(2^g\) lên \(2^{g+1}\) |
| **Xóa không gộp** | \(O(B)\) | Chỉ tìm và xóa bản ghi trong bucket |
| **Xóa có gộp/thu nhỏ** | Thêm chi phí sửa con trỏ và rút gọn thư mục | Có thể phải gộp lặp lại qua nhiều mức |
| **Bộ nhớ thư mục** | \(O(2^g)\) con trỏ | **Không** tự động bằng \(O(n)\) |
| **Bộ nhớ bucket** | Tỷ lệ với số bucket và dung lượng từng bucket | Có thể có bucket ít phần tử hoặc rỗng |

Trong cơ sở dữ liệu hoặc hệ thống lưu trữ theo trang, nếu **thư mục nằm trong RAM** và **mỗi bucket vừa một trang**, một truy vấn thường cần **một lần đọc trang bucket** sau khi tra thư mục. Nếu thư mục nằm trên đĩa, cần tính thêm I/O để đọc mục thư mục; việc tách/gộp còn phát sinh thao tác ghi trang.

### Vì sao không thể khẳng định mọi thao tác đều \(O(1)\) trong trường hợp xấu nhất?

Tra cứu trong một bucket kích thước cố định có chi phí bị chặn. Nhưng **chèn** có thể cần nhiều lần tách và một hoặc nhiều lần nhân đôi thư mục, trong đó mỗi lần nhân đôi sao chép \(2^g\) con trỏ. Do vậy không có bảo đảm chèn \(O(1)\) trong trường hợp xấu nhất đối với phiên bản thư mục đầy đủ này.

Với hàm băm có phân bố tốt, dung lượng bucket thích hợp và quản lý độ sâu hợp lý, thao tác đọc và nhiều thao tác ghi thường có chi phí nhỏ. Tuy nhiên, các phát biểu về **kỳ vọng** hoặc **chi phí phân bổ** phải nêu rõ mô hình băm và cách tăng kích thước; định nghĩa extendible hashing tự nó không đủ để chứng minh mọi workload đều có chi phí cập nhật hằng số.

### Thư mục có thể là nút thắt bộ nhớ

Thư mục dùng \(2^g\) con trỏ. Nếu một nhánh khóa buộc global depth tăng cao, rất nhiều mục có thể vẫn cùng trỏ tới những bucket cũ. Ví dụ:

\[
g=20\quad\Longrightarrow\quad |D|=2^{20}=1\,048\,576\text{ con trỏ}.
\]

Điều này có thể xảy ra dù số bucket vật lý thấp hơn nhiều. Chính sự khác biệt giữa **số mục thư mục** và **số bucket vật lý** là đánh đổi trung tâm của extendible hashing.

## 10. Khi nào nên sử dụng và so sánh với biến thể khác?

| Cấu trúc | Cách mở rộng | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Extendible hashing** | Tách bucket; nhân đôi thư mục khi \(\ell=g\) | Tra cứu có đường đi ngắn qua directory; hữu ích với bucket theo trang | Thư mục \(2^g\) con trỏ có thể tăng nhanh; cập nhật con trỏ khi tách/gộp |
| **Linear hashing** | Tách bucket theo một thứ tự tăng dần, thường không cần directory kích thước \(2^g\) | Tránh mảng thư mục nhân đôi; mở rộng dần | Cách xác định bucket và quản lý con trỏ tách phức tạp hơn |
| **Separate chaining** | Có thể tăng số bucket và băm lại, hoặc dùng danh sách ở mỗi ô | Cài đặt linh hoạt, xử lý va chạm dễ | Chuỗi dài làm tra cứu chậm, có overhead con trỏ/nút |
| **Cuckoo hashing** | Rehash/resize khi chuỗi chèn không đặt được khóa | Tra cứu ít vị trí ứng viên | Chèn có thể đẩy nhiều khóa và tái băm |
| **Robin Hood hashing** | Mở rộng mảng khi tải cao, chèn đổi chỗ theo DIB | Dữ liệu trong mảng liên tục; cân bằng khoảng cách thăm dò | Chèn và xóa có thể di chuyển nhiều phần tử |
| **B-tree/B+ tree** | Tách nút/trang của cây, giữ thứ tự khóa | Hỗ trợ tìm theo khoảng và duyệt có thứ tự | Quản lý cấu trúc cây; truy vấn khóa đơn có đường đi nhiều mức |

**Extendible hashing đặc biệt phù hợp** với bảng tra cứu khóa–giá trị trên đĩa hoặc trong hệ lưu trữ theo trang, khi cần xử lý tìm kiếm chính xác và tăng trưởng dữ liệu mà tránh băm lại toàn bộ tập khóa mỗi lần. Nếu truy vấn cần **khoảng giá trị, thứ tự hoặc sắp xếp**, các cấu trúc cây như B+ tree có thể phù hợp hơn vì hashing không bảo toàn thứ tự.

Đối với dữ liệu lưu hoàn toàn trong RAM và kích thước vừa phải, bảng băm động thông thường có thể đơn giản hơn. Quyết định cuối cùng cần dựa trên **độ trễ tra cứu, tần suất chèn/xóa, số lần đọc/ghi trang và ngân sách bộ nhớ cho directory**.

## 11. Những lỗi và nhầm lẫn thường gặp

1. **“Mỗi mục thư mục có một bucket riêng.”** Sai: nhiều chỉ số có thể cùng trỏ một bucket khi local depth nhỏ hơn global depth.
2. **“Tách bucket nào cũng phải nhân đôi thư mục.”** Sai: chỉ cần nhân đôi nếu bucket đầy có \(\ell=g\).
3. **“Nhân đôi thư mục cũng nhân đôi dữ liệu.”** Sai: chỉ nhân đôi **con trỏ**; các bản ghi ở bucket khác không bị sao chép.
4. **“Local depth của mọi bucket luôn bằng global depth.”** Sai: một số bucket đã tách nhiều lần, số khác chưa tách và vẫn có local depth thấp hơn.
5. **“Chỉ cần kiểm tra chỉ số thư mục là biết khóa có tồn tại.”** Sai: vẫn phải so sánh khóa thật trong bucket.
6. **“Đủ chỗ ở bucket khác thì có thể chèn khóa vào đó tùy ý.”** Sai: khóa phải ở bucket do các bit băm và directory chỉ tới.
7. **“Xóa xong cứ gộp hai bucket ít phần tử bất kỳ.”** Sai: hai bucket phải là **buddy** phù hợp, cùng local depth và đủ dung lượng để gộp.
8. **“Gộp một cặp bucket là lập tức giảm global depth.”** Sai: chỉ giảm \(g\) khi không bucket nào còn cần mức bit đó.
9. **“Tăng \(g\) luôn giải quyết được va chạm.”** Sai: nếu các khóa có giá trị băm trùng nhau trên toàn bộ số bit sử dụng, phải đổi chiến lược.
10. **“Directory dùng bộ nhớ tuyến tính theo số khóa trong mọi trường hợp.”** Sai: directory có \(2^g\) con trỏ; một độ sâu bất lợi có thể làm nó lớn hơn đáng kể.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một bảng có global depth \(g=4\). Một bucket có local depth \(\ell=2\). Có bao nhiêu mục thư mục trỏ tới bucket đó?

**Lời giải:**

\[
2^{g-\ell}=2^{4-2}=4.
\]

Với quy ước bit thấp, bốn mục này có chung hai bit thấp nhận dạng bucket.

**Câu 2.** Một bucket đầy có \(\ell=2\), còn thư mục có \(g=3\). Để chèn thêm, có phải nhân đôi thư mục không?

**Lời giải:** **Không.** Vì \(\ell<g\), có thể tách bucket thành hai bucket local depth 3 và cập nhật các mục trỏ tới bucket đó ngay trong thư mục hiện tại.

**Câu 3.** Nếu bucket đầy có \(\ell=g=3\), quá trình chèn cần làm gì?

**Lời giải:** Tăng global depth thành **4**, nhân đôi mảng con trỏ từ \(2^3=8\) lên \(2^4=16\) mục, rồi tách bucket và phân phối lại các khóa của nó dựa trên bit phân biệt mới.

**Câu 4.** Sau khi đã chèn các khóa 1, 3, 5, 2, 4, 6 ở mục 5, vì sao chỉ số 00 và 10 không còn cùng trỏ vào một bucket?

**Lời giải:** Khi chèn khóa 6, bucket Even local depth 1 đã đầy trong khi global depth 2. Bucket được tách thành **Even-00** chứa 4 và **Even-10** chứa 2,6; mỗi bucket mới có local depth 2 nên các mục 00 và 10 trỏ tới hai bucket vật lý khác nhau.

**Câu 5.** Xóa 1 khỏi Odd-01 rồi gộp được Odd-01 và Odd-11. Vì sao chưa thể giảm global depth ngay?

**Lời giải:** Vì lúc ấy Even-00 và Even-10 vẫn có local depth 2 bằng global depth 2. Chúng cần hai bit để phân biệt và chưa thể biểu diễn bằng thư mục một bit.

**Câu 6.** Với \(g=20\), số mục directory là bao nhiêu? Nó có bằng số bucket vật lý không?

**Lời giải:** Directory có \(2^{20}=1\,048\,576\) con trỏ. Số bucket vật lý có thể **ít hơn nhiều** vì nhiều mục cùng trỏ tới một bucket.

## 13. Ghi nhớ

**Băm có thể mở rộng (extendible hashing)** dùng **thư mục \(2^g\) mục** để chọn bucket theo \(g\) bit của hàm băm. Mỗi bucket có **local depth \(\ell\le g\)** và có thể được nhiều mục thư mục cùng trỏ tới. Khi bucket đầy:

- Nếu **\(\ell<g\)**, chỉ cần **tách bucket** và cập nhật các con trỏ tương ứng.
- Nếu **\(\ell=g\)**, phải **nhân đôi thư mục**, sau đó tách bucket.

Tra cứu đi qua một mục thư mục và một bucket; với dung lượng bucket cố định, thao tác đọc có thể giới hạn số phần tử phải xem. Cấu trúc cho phép tăng trưởng theo từng nhóm khóa, rất hữu ích cho dữ liệu lưu theo trang. Đánh đổi là **bộ nhớ thư mục \(O(2^g)\)** và chi phí cập nhật con trỏ, tách/gộp, tái xử lý khi phân bố băm kém. Khi chọn cấu trúc, cần đánh giá cùng lúc **tải bucket, số lần I/O, tăng trưởng directory và yêu cầu cập nhật dữ liệu**.
