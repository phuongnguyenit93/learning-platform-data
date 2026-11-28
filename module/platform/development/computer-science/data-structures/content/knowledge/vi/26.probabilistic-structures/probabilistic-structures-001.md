# Đánh đổi độ chính xác lấy bộ nhớ hoặc tốc độ

Có những bài toán cấu trúc dữ liệu cần **kết quả chính xác tuyệt đối**, chẳng hạn xác thực quyền truy cập, tính số dư hoặc kiểm tra một giao dịch đã thanh toán. Nhưng trong nhiều ứng dụng khác, câu trả lời **gần đúng với mức sai số đã biết và được kiểm soát** có thể hữu ích hơn: ta cần lọc nhanh một lượng lớn khóa trước khi truy vấn cơ sở dữ liệu, ước lượng số người dùng duy nhất hoặc tìm các mục xuất hiện nhiều trong luồng sự kiện, trong khi bộ nhớ không đủ để giữ tất cả bản ghi.

**Cấu trúc dữ liệu xác suất và xấp xỉ** (*probabilistic / approximate data structures*) khai thác khả năng ấy: thay vì lưu đủ thông tin để trả lời mọi truy vấn chính xác, chúng lưu một bản tóm tắt nhỏ, sử dụng hàm băm, lấy mẫu hoặc ngẫu nhiên hóa. Đổi lại, một số loại truy vấn có thể trả **dương tính giả**, **ước lượng lệch**, hoặc có một **xác suất thất bại** được mô tả rõ.

Điều quan trọng là **không đồng nhất “ngẫu nhiên” với “sai số”**. Một cấu trúc dữ liệu được ngẫu nhiên hóa cũng có thể **luôn trả đáp án chính xác**, chỉ có thời gian chạy phụ thuộc vào lựa chọn ngẫu nhiên, như một skip list ngẫu nhiên với thuật toán tìm kiếm kiểm tra khóa đầy đủ.

Bài nằm trong chương **Cấu trúc xác suất** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo mục tiêu xây dựng nền tảng cấu trúc dữ liệu qua bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để chọn cấu trúc phù hợp, bài tập trung vào **cách định nghĩa sai số, đọc bảo đảm xác suất và đưa ra quyết định kỹ thuật có kiểm chứng**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt cấu trúc **chính xác**, cấu trúc **ngẫu nhiên nhưng kết quả chính xác**, và cấu trúc **trả kết quả xấp xỉ**.
- Hiểu **false positive (dương tính giả)**, **false negative (âm tính giả)**, sai số một phía và hai phía trong từng bài toán.
- Phân biệt **sai số xác suất** với **sai số do xấp xỉ giá trị**, và phân biệt bảo đảm **kỳ vọng / khấu hao / xác suất cao**.
- Mô tả **Bloom filter**: mảng bit, nhiều vị trí băm, insert và membership query; giải thích vì sao insert-only chuẩn có **không âm tính giả** nhưng có dương tính giả.
- Sử dụng các công thức thiết kế Bloom filter cho **số phần tử dự kiến n, số bit m, số hàm băm h và tỷ lệ dương tính giả p**.
- Viết một Bloom filter Python tự chứa, kiểm tra bất biến bit chỉ chuyển 0→1 và nhận biết những ràng buộc về xóa, mở rộng và khóa đã chuẩn hóa.
- Mô tả **Count-Min Sketch** và lý do trong mô hình **insert-only, tần suất không âm**, ước lượng một khóa **không nhỏ hơn** tần suất thực.
- Phát biểu bảo đảm xác suất điển hình của Count-Min Sketch bằng hai tham số **ε, δ**, và phân biệt nó với Bloom filter.
- Nhận biết mục đích của **HyperLogLog** để ước lượng số giá trị khác nhau, **reservoir sampling** để lấy mẫu, và các sketch ước lượng phân vị.
- Lập **ngân sách sai số**: tỷ lệ dương tính giả cho phép, sai số tần suất, sai số số lượng phân biệt và tác động của truy vấn sau cấu trúc.
- So sánh độ phức tạp, bộ nhớ, khả năng hợp nhất và các giới hạn về **xóa, khóa trùng, thay đổi quy mô, đối thủ thích nghi, tính bền vững và đồng thời**.
- Chọn phương án đúng khi bài toán **không chấp nhận sai số**, hoặc khi có thể dùng cấu trúc xấp xỉ làm bộ lọc trước một bước xác minh chính xác.

## 2. Vì sao cần một sự đánh đổi?

Giả sử một hệ thống thu thập **hàng triệu sự kiện** mỗi phút. Ba yêu cầu có vẻ giống nhau nhưng thực chất khác nhau:

1. **“Mã sự kiện X chắc chắn chưa từng xuất hiện trong tập đã ghi nhận?”** — có thể dùng một bộ lọc membership **một phía** để loại nhanh các trường hợp chắc chắn vắng mặt.
2. **“Khóa X đã xuất hiện bao nhiêu lần?”** — có thể lưu một ước lượng tần suất, thay vì một bộ đếm riêng cho mọi khóa.
3. **“Có khoảng bao nhiêu người dùng phân biệt?”** — có thể dùng một bản tóm tắt cardinality, không cần lưu danh sách ID duy nhất.

Một **set chính xác** thường cần lưu thông tin cho từng khóa phân biệt. Một **dictionary đếm chính xác** cần bộ đếm cho từng khóa. Với không gian khóa lớn, những cấu trúc ấy có thể tốn nhiều bộ nhớ; lưu thêm tất cả khóa còn phát sinh chi phí I/O hoặc truyền qua mạng.

Một cấu trúc xấp xỉ có thể giữ **một số lượng bit hoặc ô đếm gần như cố định** sau khi được cấu hình. Tuy nhiên:

- Nó có thể **không trả được khóa gốc** hoặc liệt kê tất cả phần tử.
- Một số câu trả lời **không đủ để ra quyết định cuối cùng** nếu sai số bị cấm.
- Độ chính xác có thể **giảm khi số phần tử thực tế vượt xa dung lượng đã thiết kế**.
- Chi phí tính toán **không phải luôn thấp hơn**: nhiều phép băm, cập nhật các hàng đếm hoặc giải mã ước lượng có thể tăng CPU.

**Đánh đổi đúng nghĩa** là chọn tối ưu theo cả ba trục **bộ nhớ – thời gian – mức độ chính xác**, chứ không phải cho phép kết quả sai một cách không kiểm soát.

## 3. Các loại bảo đảm: đừng gom mọi “xác suất” thành một

### 3.1. Kết quả chính xác, thời gian có thể ngẫu nhiên

Một **skip list ngẫu nhiên** dùng tung đồng xu để chọn chiều cao của các nút. Với cách cài đặt và giả định chuẩn, tìm kiếm/chèn/xóa có **O(log n) thời gian kỳ vọng**, còn trường hợp xấu nhất có thể O(n). Nhưng phép tìm kiếm vẫn có thể so sánh khóa thật và trả **đúng tồn tại/không tồn tại**.

Đây là ví dụ của việc **dùng ngẫu nhiên hóa để tổ chức cấu trúc**, không đánh đổi tính đúng đắn của câu trả lời. Những thuật toán kiểu **Las Vegas** có kết quả đúng và thời gian hoặc lượng công việc phụ thuộc ngẫu nhiên.

### 3.2. Thời gian/bộ nhớ được chặn, câu trả lời có rủi ro sai

**Bloom filter** giữ một mảng bit để kiểm tra **có thể thuộc tập**. Trong mô hình insert-only chuẩn:

- Kết quả **“chắc chắn không có”** đáng tin cậy.
- Kết quả **“có thể có”** cần được kiểm chứng khi nghiệp vụ đòi hỏi đúng tuyệt đối.

Đây là một dạng **sai số một phía**. Thuật toán kiểu **Monte Carlo** thường đặt giới hạn công việc và chấp nhận khả năng trả lời sai với xác suất xác định.

**Lưu ý:** Bloom filter dùng hàm băm xác định sau khi khởi tạo; xác suất sai được mô hình hóa qua phân bố/họ hàm băm và tập truy vấn, **không có nghĩa mỗi lời gọi nhất thiết tung một đồng xu mới**.

### 3.3. Ước lượng số thay vì câu trả lời yes/no

**Count-Min Sketch** trả một số ước lượng cho tần suất của khóa. Trong mô hình insert-only với trọng số không âm, nó có **hướng sai số một phía: ước lượng ≥ thực tế**, và có bảo đảm xác suất cho độ lệch cộng thêm.

**HyperLogLog** trả ước lượng **số khóa phân biệt**, có thể **cao hơn hoặc thấp hơn** giá trị thật. Độ chính xác thường được mô tả bằng **sai số tương đối thống kê**, không bằng dương tính giả.

Các khái niệm phải khớp với loại câu hỏi:

| Dạng câu hỏi | Kết quả | Cách đo sai số phù hợp |
| --- | --- | --- |
| Khóa có trong tập không? | Boolean / có thể có | False positive, false negative |
| Khóa xuất hiện bao nhiêu lần? | Số đếm | Sai số tuyệt đối/cộng thêm, overestimate |
| Có bao nhiêu khóa phân biệt? | Cardinality ước lượng | Sai số tương đối, phân phối ước lượng |
| Phân vị p99 là bao nhiêu? | Giá trị/rank ước lượng | Sai số thứ hạng hoặc xác suất lệch |
| Lấy mẫu k phần tử? | Một tập con ngẫu nhiên | Xác suất chọn đều, độ lệch do lấy mẫu |

### 3.4. Xác suất lỗi và chi phí kỳ vọng là hai đại lượng khác nhau

- **Expected time O(log n):** Thời gian trung bình theo nguồn ngẫu nhiên có cận bậc logarit.
- **Worst-case time O(n):** Có đầu vào/trạng thái làm một thao tác cần tuyến tính.
- **Amortized O(1):** Chi phí một chuỗi thao tác được phân bổ; **không đồng nghĩa** xác suất lỗi và cũng không nhất thiết dùng ngẫu nhiên.
- **Probability of failure ≤ δ:** Một sự kiện sai vượt ngưỡng xảy ra với xác suất không quá δ theo mô hình xác suất đã giả định.

Nếu sai số hoặc thời gian xấu nhất là vấn đề sống còn, phải đọc **loại bảo đảm**, không chỉ đọc ký hiệu O(log n).

## 4. Phân biệt dương tính giả và âm tính giả

Giả sử ta hỏi “khóa X có thuộc tập S không?”:

| Sự thật | Cấu trúc trả “có / có thể có” | Cấu trúc trả “không” |
| --- | --- | --- |
| X thực sự thuộc S | **True positive (TP)** | **False negative (FN)** |
| X không thuộc S | **False positive (FP)** | **True negative (TN)** |

Ví dụ hệ thống đã từng xử lý các ID **A, B, C**:

- Hỏi A, trả “có thể có”: **true positive**.
- Hỏi D (chưa ghi nhận), trả “có thể có”: **false positive**.
- Hỏi D, trả “chắc chắn không”: **true negative**.
- Hỏi A, trả “không”: **false negative**, điều mà Bloom filter insert-only chuẩn **không tạo ra** nếu insert và truy vấn dùng cùng trạng thái/hàm băm.

**Tỷ lệ false positive** thường được định nghĩa theo số truy vấn **thực sự âm tính**:

\[
\mathrm{FPR}=\frac{FP}{FP+TN}.
\]

Đừng chia FP cho **tổng mọi truy vấn** rồi gọi đó là FPR; mẫu số của FPR chỉ gồm những trường hợp **thực tế không thuộc tập**.

Nếu một bộ lọc có FPR khoảng 1%, không có nghĩa **1% câu trả lời “có thể có” là sai**. Tỷ lệ sai trong nhóm dương tính còn phụ thuộc tỷ lệ khóa thực sự thuộc tập (*base rate / prevalence*).

### 4.1. Ví dụ xác suất có điều kiện

Giả sử trong 10 triệu truy vấn:

- 5% truy vấn hỏi khóa **thực sự có**, tức 500.000 truy vấn.
- 95% hỏi khóa **không có**, tức 9.500.000 truy vấn.
- Bloom filter có FPR mục tiêu 1% trên các truy vấn âm tính theo mô hình ngẫu nhiên.

Số lượt “có thể có” kỳ vọng xấp xỉ:

~~~text
True positive:       500 000
False positive:       95 000 = 1% của 9 500 000
-----------------------------------------------
Có thể có:           595 000

Tỷ lệ false positive trong nhóm "có thể có":
95 000 / 595 000 ≈ 15,97%
~~~

Điều này chứng tỏ **FPR 1% không đồng nghĩa chỉ 1% câu trả lời dương tính bị sai**. Tỷ lệ dương tính thật, quy trình truy vấn và số khóa đã insert ảnh hưởng mạnh tới lợi ích của một bộ lọc.

## 5. Bloom filter: nhớ các dấu vết băm thay vì lưu mọi khóa

**Bloom filter** là một cấu trúc membership xấp xỉ. Nó có:

- Một **mảng m bit**, ban đầu đều bằng 0.
- **h hàm băm hoặc vị trí băm** cho mỗi khóa, mỗi giá trị trong khoảng 0 đến m−1.
- Thao tác **add(x)** để bật các bit tương ứng.
- Thao tác **might_contain(x)** để kiểm tra các bit ấy.

### 5.1. Insert một khóa

Giả sử m=12, h=3. Ba vị trí băm của khóa A là 1, 4, 10:

~~~text
index: 0 1 2 3 4 5 6 7 8 9 10 11
bit:   0 0 0 0 0 0 0 0 0 0  0  0

add(A) → đặt bit 1, 4, 10 thành 1

index: 0 1 2 3 4 5 6 7 8 9 10 11
bit:   0 1 0 0 1 0 0 0 0 0  1  0
~~~

Nếu khóa B băm vào các vị trí 4, 7, 10, thao tác add(B) **không đặt lại bit đã bằng 1 thành 0**; chỉ bật thêm bit 7:

~~~text
bit:   0 1 0 0 1 0 0 1 0 0  1  0
~~~

### 5.2. Query membership

Đối với một khóa X:

- Nếu **ít nhất một vị trí băm của X chứa bit 0**, trả **“chắc chắn không có”** trong mô hình insert-only chuẩn.
- Nếu **tất cả h vị trí đều có bit 1**, trả **“có thể có”**.

Có thể nhiều khóa khác nhau đã bật đủ các bit đó, nên “có thể có” **không chứng minh X thực sự đã được insert**.

### 5.3. Vì sao không có false negative khi chỉ thêm?

Khi add(x), mọi vị trí băm của x được bật thành 1. Sau đó thao tác add của các khóa khác **chỉ có thể bật thêm bit 1**, không xóa bit đã bật.

Vậy đối với khóa x từng được add thành công, tất cả các bit của x vẫn là 1; might_contain(x) luôn trả “có thể có”.

Bất biến một chiều:

\[
\text{bit 0}\longrightarrow\text{bit 1},\qquad \text{không có bước }1\longrightarrow0.
\]

**Tiền điều kiện quan trọng:** Không thực hiện xóa bit tùy ý, không mất dữ liệu, không thay đổi seed/hàm băm giữa insert/query, và không có lỗi cập nhật đồng thời. Nếu hệ thống vi phạm những điều kiện ấy, false negative **có thể xuất hiện ngoài mô hình chuẩn**.

### 5.4. Vì sao vẫn có false positive?

Giả sử khóa D **chưa hề được add**, nhưng ba vị trí băm của D tình cờ đều đã được bật bởi A, B và các khóa khác. Query D sẽ trả “có thể có”.

Bloom filter không thể phân biệt:

~~~text
"Ba bit của D được bật bởi chính D"
với
"Ba bit của D được bật bởi những khóa khác"
~~~

Do đó nó đánh đổi **thông tin danh tính khóa** lấy **mảng bit nhỏ**.

## 6. Công thức ước lượng tỷ lệ dương tính giả của Bloom filter

Giả định có n **khóa phân biệt** được insert, m bit, h vị trí băm được phân bố đủ đều và gần độc lập theo mô hình lý tưởng.

Xác suất một lần đặt bit **không** chạm vào một vị trí cụ thể là:

\[
1-\frac1m.
\]

Sau khoảng hn lần đặt bit, xác suất vị trí ấy vẫn bằng 0:

\[
P(bit=0)=\left(1-\frac1m\right)^{hn}
\approx e^{-hn/m}.
\]

Vì vậy, xác suất bit đang là 1 xấp xỉ:

\[
P(bit=1)\approx 1-e^{-hn/m}.
\]

Để một khóa **chưa insert** bị trả lời dương tính giả, cả h bit tương ứng phải bằng 1. Công thức kinh điển là:

\[
\boxed{p_{\mathrm{FP}}\approx (1-e^{-hn/m})^h}.
\]

Đây là **xấp xỉ theo mô hình hàm băm lý tưởng**, không phải bảo đảm tuyệt đối cho mọi bộ dữ liệu hoặc mọi chuỗi truy vấn do đối thủ chọn.

### 6.1. Số vị trí băm tối ưu

Với m và n cố định, giá trị h gần tối ưu là:

\[
\boxed{h_{\mathrm{opt}}\approx\frac{m}{n}\ln 2}.
\]

Trong cài đặt, chọn **số nguyên h ≥ 1** gần giá trị này.

Khi h quá nhỏ, ít vị trí được bật cho mỗi khóa nhưng query ít điều kiện, nên tỷ lệ sai có thể cao. Khi h quá lớn, các bit nhanh bị lấp đầy và cả insert/query phải tính nhiều hash, cũng không tốt.

**Nhiều hàm băm hơn không phải lúc nào cũng chính xác hơn.**

### 6.2. Dung lượng bit cho n và p mục tiêu

Từ phép tối ưu trên, số bit cần thiết xấp xỉ:

\[
\boxed{m\approx-\frac{n\ln p}{(\ln2)^2}}.
\]

Số **bit trên mỗi khóa**:

\[
\boxed{\frac mn\approx-\frac{\ln p}{(\ln2)^2}}.
\]

Nếu muốn FPR mục tiêu **1%**:

~~~text
n dự kiến:   1 000 000 khóa phân biệt
p mục tiêu:  0,01
m cần:       khoảng 9,59 triệu bit
bộ nhớ bit:  khoảng 1,14 MiB
h tối ưu:    khoảng 7 vị trí băm mỗi khóa
~~~

Nếu giảm p xuống **0,1%** với cùng n:

~~~text
p mục tiêu:  0,001
m cần:       khoảng 14,38 triệu bit
bộ nhớ bit:  khoảng 1,71 MiB
h tối ưu:    khoảng 10 vị trí băm mỗi khóa
~~~

Giảm FPR mười lần cần thêm bộ nhớ và số vị trí băm. Con số trên chỉ tính **mảng bit**, chưa tính đối tượng Python, seed, bộ đếm kích thước hoặc metadata.

### 6.3. Đọc công thức một cách đúng đắn

- n trong công thức thường là số **khóa phân biệt**, không phải số lần add cùng một khóa.
- Nếu số khóa thực tế **lớn hơn n đã thiết kế**, FPR thực tế thường tăng.
- Nếu ít khóa hơn dự kiến, bộ lọc có thể chính xác hơn mục tiêu thiết kế.
- h là số vị trí băm; các vị trí **có thể trùng nhau** nếu xây từ các hàm băm hữu hạn.
- Giả định hash phân bố tốt là yếu tố nền tảng; độ chính xác đo được cần kiểm tra trên workload thực tế.
- FPR không thể hiểu là “một xác suất sai độc lập hoàn toàn qua từng lần hỏi cùng một khóa”: với hash và trạng thái cố định, cùng truy vấn thường cho **cùng kết quả**.


## 7. Python: Bloom filter chỉ thêm khóa

Cài đặt minh họa sau chỉ chấp nhận khóa **str** để cách mã hóa khóa rõ ràng. Nó sử dụng **bytearray** và tính nhiều vị trí bằng SHA-256 với tiền tố/chỉ số hàm băm. Những vị trí băm này **không phải bằng chứng đã đạt giả định độc lập toán học** trong công thức; bản triển khai sản xuất cần đánh giá hash và workload.

~~~python
import hashlib
import math


class BloomFilter:
    def __init__(self, expected_items: int, target_fp: float):
        if expected_items <= 0:
            raise ValueError("expected_items phải dương")
        if not (0 < target_fp < 1):
            raise ValueError("target_fp phải trong (0,1)")

        self.n = expected_items
        self.p = target_fp
        ln2 = math.log(2)
        self.m = max(1, math.ceil(-self.n * math.log(self.p) / ln2**2))
        self.h = max(1, round(self.m / self.n * ln2))
        self.bits = bytearray((self.m + 7) // 8)

    def _positions(self, key: str):
        if not isinstance(key, str):
            raise TypeError("Chỉ hỗ trợ khóa str")
        data = key.encode("utf-8")
        for i in range(self.h):
            digest = hashlib.sha256(
                b"bloom-v1|" + i.to_bytes(8, "big") + b"|" + data
            ).digest()
            yield int.from_bytes(digest, "big") % self.m

    def add(self, key: str) -> None:
        for pos in self._positions(key):
            self.bits[pos // 8] |= (1 << (pos % 8))

    def might_contain(self, key: str) -> bool:
        for pos in self._positions(key):
            if not (self.bits[pos // 8] & (1 << (pos % 8))):
                return False
        return True


bf = BloomFilter(expected_items=1000, target_fp=0.01)
keys = [f"user-{i}" for i in range(1000)]

for key in keys:
    bf.add(key)

# Với cấu trúc chỉ-thêm hợp lệ không có âm tính giả.
assert all(bf.might_contain(key) for key in keys)
assert len(bf.bits) == (bf.m + 7) // 8

# Với khóa chưa thêm, trả True hoặc False đều có thể xảy ra.
unknown_answer = bf.might_contain("not-inserted")
assert isinstance(unknown_answer, bool)

# Thêm lại đúng khóa không thể tắt bit đã bật.
before = bytes(bf.bits)
bf.add("user-0")
assert bytes(bf.bits) == before
assert bf.might_contain("user-0")
~~~

### 7.1. Bất biến và độ phức tạp

- **Mảng bit** chỉ đổi 0→1. Không có lệnh xóa bit.
- **Mã hóa khóa** trong add và query phải giống nhau; cùng khóa tạo cùng vị trí.
- **add / might_contain:** O(h) phép băm/kiểm tra bit trong mô hình phép băm O(1).
- Nếu phải quét chuỗi khóa dài L để băm h lần như mã trên, chi phí có thể là **O(hL)**.
- **Bộ nhớ bit:** m bit, được bytearray cấp phát thành **⌈m/8⌉ byte**; còn overhead đối tượng Python.
- **Khởi tạo:** Θ(m) thao tác theo kích thước bit/byte được cấp phát.

Một khóa chưa được add **có thể** nhận True. Không được viết một assertion đòi mọi khóa lạ đều trả False: chính tỷ lệ dương tính giả là phần đánh đổi.

### 7.2. Không được xóa trực tiếp

Nếu hai khóa X và Y cùng bật một bit, việc “xóa X” bằng cách đặt bit ấy về 0 có thể khiến Y — vốn đã add — trở thành **âm tính giả**.

**Counting Bloom filter** dùng các bộ đếm thay bit, nhưng chỉ xóa an toàn khi hệ thống **biết chính xác khóa và số lần thêm/xóa**, không giảm nhầm bộ đếm dùng chung và không bị **tràn bộ đếm**. Việc dùng might_contain để quyết định “chắc chắn đã thêm” rồi xóa là **không an toàn** vì chính truy vấn ấy có thể trả dương tính giả.

### 7.3. Dung lượng, vòng đời và cập nhật

Nếu số khóa phân biệt thực tế vượt xa n đã chọn, các bit dần bão hòa; tỷ lệ dương tính giả thường tăng. Lúc đó phải **xây lại từ nguồn khóa chính xác** hoặc dùng biến thể có khả năng mở rộng được thiết kế riêng.

Không được đơn giản đổi m, h hoặc seed của bộ lọc đã chứa dữ liệu: vị trí băm của những khóa cũ sẽ đổi, gây nguy cơ âm tính giả.

Nếu hai bộ lọc có **cùng m, h, hash version, seed và cách chuẩn hóa khóa**, phép **OR theo bit** cho một bộ lọc biểu diễn hợp của hai tập. Nếu thông số khác nhau, không OR tùy tiện. Khi hai tập có trùng khóa, số khóa phân biệt của hợp có thể **nhỏ hơn tổng** hai kích thước.

### 7.4. Dùng làm bộ lọc trước cơ sở dữ liệu

~~~text
Query khóa X
    |
    v
Bloom.might_contain(X)?
    |
    +-- False ---> Không có (nếu filter đồng bộ/đầy đủ)
    |
    +-- True ----> Truy vấn CSDL chính xác
                    |
                    +--> Trả kết luận thật
~~~

Đây là cách **giảm chi phí truy vấn đắt tiền** mà vẫn trả kết luận chính xác cuối cùng. Bloom không tự biết dữ liệu của CSDL: nếu CSDL thêm khóa nhưng không cập nhật Bloom, hệ thống có thể **trả sai âm tính** do **bộ lọc không đồng bộ**, bất chấp chứng minh insert-only của bản thân Bloom.

Trong ví dụ 10 triệu truy vấn với 5% thực sự có và FPR 1% của các truy vấn không có, số truy vấn CSDL kỳ vọng khoảng **500.000 + 95.000 = 595.000**. Nhưng phải cộng chi phí hash, cache, quản lý vòng đời và cập nhật mảng bit để kết luận có lợi về hiệu năng hay không.

### 7.5. Bảo mật, chuẩn hóa và nhiều luồng

- “Alice”, “alice” và hai chuỗi Unicode có biểu diễn khác nhau **không mặc nhiên giống khóa**; chuẩn hóa phải nhất quán.
- Lưu bản sao cấu trúc phải đi kèm **m, h, hash version, seed, encoding**; chỉ lưu bytearray là chưa đủ cho tương thích lâu dài.
- Bloom filter **không phải công cụ mã hóa hoặc xác thực quyền**. Đối thủ có thể tìm các khóa dương tính giả bằng truy vấn thích nghi, nên FPR trong mô hình khóa ngẫu nhiên không phải bảo đảm an ninh.
- Khi nhiều luồng cùng cập nhật bit nằm trên cùng byte/từ máy, cần **cập nhật nguyên tử hoặc khóa** thích hợp. Nếu mất cập nhật, một khóa đã add có thể thiếu bit.
- Nếu cần hết hạn theo khoảng thời gian, phải có chính sách **phân vùng thời gian, xây lại hoặc cấu trúc hỗ trợ xóa**, không tắt bit của một Bloom filter chuẩn.

## 8. Count-Min Sketch: ước lượng tần suất

Giả sử một luồng sự kiện chứa:

~~~text
A, B, A, C, A, B, D, A

Tần suất thực:
A=4; B=2; C=1; D=1
~~~

Muốn **đếm chính xác**, ta có thể lưu dictionary từ khóa tới số lần xuất hiện. Nhưng với rất nhiều khóa phân biệt, bộ nhớ tỉ lệ với số khóa.

**Count-Min Sketch (CMS)** giữ một bảng đếm **d hàng × w cột**, mọi ô khởi tạo bằng 0. Mỗi hàng có một hash riêng biến khóa thành chỉ số cột.

### 8.1. Update và query

Với một lần xuất hiện của khóa x có trọng số c > 0, **tăng ô băm tương ứng ở mọi hàng**:

\[
counter[r, hash_r(x)] \mathrel{+}=c,
\quad r=0,\ldots,d-1.
\]

Để ước lượng tần suất của x, lấy:

\[
\boxed{\widehat f(x)=\min_r counter[r,hash_r(x)]}.
\]

Mỗi ô đếm số lần của x **cộng va chạm của các khóa khác**. Trong luồng chỉ tăng với bộ đếm không tràn:

\[
\boxed{\widehat f(x)\ge f(x)}.
\]

Đó là sai số **một phía theo hướng đếm lớn hơn thực tế**. Khác Bloom, CMS trả **con số**, không phải membership Boolean.

### 8.2. Ví dụ va chạm

~~~text
Tần suất thật của X = 5.

Ô tương ứng ở hàng 0: 8   (5 của X + 3 va chạm)
Ô tương ứng ở hàng 1: 5   (5 của X + 0 va chạm)
Ô tương ứng ở hàng 2: 7   (5 của X + 2 va chạm)

estimate(X) = min(8, 5, 7) = 5.
~~~

Nếu mọi hàng có va chạm, ví dụ 8, 6, 7, thì estimate(X)=6 và đã **overestimate 1**.

### 8.3. Bảo đảm xác suất tiêu chuẩn

Gọi N là tổng trọng số các lần update không âm:

\[
N=\sum_x f(x).
\]

Chọn chiều rộng và số hàng:

\[
w=\left\lceil\frac{e}{\varepsilon}\right\rceil,\qquad
d=\left\lceil\ln\frac1\delta\right\rceil.
\]

Với họ hash đủ độc lập theo mô hình chuẩn, cho **một khóa truy vấn cố định**, ta có:

\[
\boxed{
f(x)\le\widehat f(x)\le f(x)+\varepsilon N
\quad\text{với xác suất ít nhất }1-\delta.
}
\]

Trong đó:

- **ε:** ngưỡng sai số **cộng thêm tính theo tổng N**, không phải % sai số tương đối trên f(x).
- **δ:** xác suất vượt ngưỡng sai số, theo phân bố hash/truy vấn giả định.
- **w:** tăng theo 1/ε, tức càng muốn chính xác càng cần nhiều cột.
- **d:** tăng theo log(1/δ), tức muốn tin cậy hơn cần nhiều hàng.

Ví dụ với **N = 1.000.000**, ε=0,001 và δ=0,01:

~~~text
w = ceil(e/0,001) = 2719 cột
d = ceil(ln 100) = 5 hàng

Tổng ô đếm = 2719 * 5 = 13 595.
Ngưỡng sai số cộng = 0,001 * 1 000 000 = 1 000.

Với xác suất ít nhất 99% trong mô hình chuẩn:
f(x) <= estimate(x) <= f(x) + 1 000
cho một khóa truy vấn cố định.
~~~

**Đơn vị bộ nhớ:** 13.595 **ô đếm**, không phải 13.595 bit. Nếu dùng counter 32-bit, phần bảng chứa ít nhất 54.380 byte; với Python int/list còn nhiều overhead hơn.

Một khóa hiếm có f(x)=2 có thể nhận ước lượng hàng trăm mà vẫn thỏa cận cộng thêm 1.000. Vì vậy, không được nói “ε=0,001 tức mọi khóa được đếm chính xác đến 0,1%”.


## 9. Python: Count-Min Sketch có trọng số không âm

Đoạn mã dưới đây lưu **d hàng × w cột** bằng list Python và dùng hash khác tiền tố theo số hàng. Đây là bản học tập: các công thức xác suất chuẩn giả định chất lượng và mức độc lập hash phù hợp; SHA-256 với tiền tố hàng không phải chứng minh toán học các giả định ấy.

~~~python
import hashlib
import math


class CountMinSketch:
    def __init__(self, epsilon: float, delta: float):
        if epsilon <= 0:
            raise ValueError("epsilon phải dương")
        if not (0 < delta < 1):
            raise ValueError("delta phải thuộc (0,1)")

        self.width = max(1, math.ceil(math.e / epsilon))
        self.depth = max(1, math.ceil(math.log(1 / delta)))
        self.rows = [
            [0 for _ in range(self.width)]
            for _ in range(self.depth)
        ]
        self.total = 0

    def _column(self, key: str, row: int) -> int:
        if not isinstance(key, str):
            raise TypeError("Ví dụ này chỉ nhận khóa str")

        digest = hashlib.sha256(
            b"cms-v1|" + row.to_bytes(8, "big")
            + b"|" + key.encode("utf-8")
        ).digest()

        return int.from_bytes(digest, "big") % self.width

    def add(self, key: str, weight: int = 1) -> None:
        if not isinstance(weight, int) or weight <= 0:
            raise ValueError("weight phải là số nguyên dương")

        for row in range(self.depth):
            col = self._column(key, row)
            self.rows[row][col] += weight

        self.total += weight

    def estimate(self, key: str) -> int:
        return min(
            self.rows[row][self._column(key, row)]
            for row in range(self.depth)
        )


cms = CountMinSketch(epsilon=0.01, delta=0.01)

events = ["A", "B", "A", "C", "A", "B", "D", "A"]
exact = {"A": 4, "B": 2, "C": 1, "D": 1}

for event in events:
    cms.add(event)

assert cms.total == 8

# Với update không âm, mọi estimate >= tần suất thật.
for key, count in exact.items():
    assert count <= cms.estimate(key) <= cms.total

# Một khóa không có thật có thể nhận estimate dương do va chạm.
unknown = cms.estimate("never-seen")
assert 0 <= unknown <= cms.total

# Bổ sung trọng số 3 cho A: count thật thành 7.
cms.add("A", weight=3)
assert cms.total == 11
assert cms.estimate("A") >= 7

# Khóa hiếm vẫn có thể bị overestimate, không có âm tính giả
# theo hướng tần suất thực lớn hơn estimate khi chỉ cộng.
~~~

### 9.1. Chi phí và đơn vị bộ nhớ

| Thao tác | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Khởi tạo bảng | Θ(wd) | Θ(wd) **ô đếm** |
| add(x, weight) | O(d) phép hash/cộng | O(1) phụ |
| estimate(x) | O(d) phép hash và lấy min | O(1) phụ |
| Lưu tất cả bảng | Không phụ thuộc trực tiếp số khóa phân biệt | O(wd) ô |

Mã dùng list và Python int, nên **một ô không phải một byte hay một bit**. Với khóa dài L, mỗi hash có thể tốn O(L) thời gian. Với bộ đếm có giới hạn số bit trong hệ thống sản xuất, phải ngăn **overflow**, nếu không bất biến ước lượng ≥ tần suất thật có thể bị phá.

### 9.2. CMS có thể làm gì với ngưỡng tần suất?

Giả sử muốn biết khóa x có xuất hiện **ít nhất T lần** không.

- Nếu **estimate(x) < T**, ta biết **f(x) ≤ estimate(x) < T** trong mô hình chỉ tăng: không phải khóa đạt ngưỡng.
- Nếu **estimate(x) ≥ T**, x **có thể** đạt ngưỡng nhưng cũng có thể là trường hợp **bị phóng đại do va chạm**.

Vì vậy, với một bộ lọc ngưỡng, CMS có thể dùng để loại những khóa chắc chắn dưới ngưỡng, rồi kiểm chứng những khóa còn lại theo nhu cầu nghiệp vụ.

Nhưng CMS tự nó **không có danh sách những khóa đã xuất hiện**. Nếu muốn tìm heavy hitters trong một không gian khóa lớn mà không có danh sách ứng viên bên ngoài, cần kết hợp với thuật toán theo dõi ứng viên.

### 9.3. Vì sao không được cập nhật trọng số âm tùy tiện?

Bảo đảm **không đếm thấp hơn thật** dựa trên các bộ đếm là tổng **các đóng góp không âm**. Nếu cho phép trừ ở những ô đã chia sẻ giữa nhiều khóa, một số mô hình update động có thể làm mất chứng minh này.

Có các biến thể sketch phục vụ luồng có xóa (*turnstile stream*), nhưng chúng có **định nghĩa và bảo đảm khác**. Không được áp dụng nguyên công thức insert-only rồi giả định vẫn đúng với mọi thao tác trừ.

### 9.4. Khi nào có thể hợp nhất hai sketch?

Hai CMS có **cùng w, d, hàm băm, seed, kiểu khóa, version** có thể cộng **từng ô tương ứng** để tạo ước lượng cho luồng hợp nhất, miễn các bộ đếm không tràn.

Nếu hai bảng dùng hash khác nhau, không thể cộng ô theo vị trí rồi giữ ý nghĩa truy vấn như cũ.

Sau khi merge, N là **tổng trọng số của cả hai luồng**, nên ngưỡng sai số cộng theo εN có thể lớn hơn trước. Không được nhầm “hợp nhất không mất dữ liệu đếm trong ô” với “sai số không tăng”.

### 9.5. Nhiều truy vấn và xác suất thất bại chung

Bảo đảm **1−δ cho một khóa cố định** không tự chuyển thành “mọi truy vấn trong hệ thống đều có xác suất sai ≤δ”.

Nếu cần bảo đảm đồng thời cho **Q khóa được xác định trước**, có thể dùng **union bound**: chọn ngân sách δ cho mỗi truy vấn không vượt quá **δ_toàn_hệ_thống/Q**. Các truy vấn phụ thuộc thích nghi vào kết quả sketch cần xem xét mô hình riêng.

Đây là nguyên tắc chung: **một bảo đảm thống kê theo truy vấn không nhất thiết là bảo đảm toàn bộ một luồng truy vấn**.

## 10. HyperLogLog: ước lượng số phần tử phân biệt

Bài toán **distinct count/cardinality** hỏi có bao nhiêu khóa khác nhau, ví dụ “trong một ngày có khoảng bao nhiêu ID người dùng duy nhất?”.

Một **set chính xác** lưu từng khóa; bộ nhớ thông thường tăng theo số khóa phân biệt. **HyperLogLog (HLL)** sử dụng các giá trị băm của khóa và một mảng nhỏ các **thanh ghi (*register*)** để ước lượng cardinality.

### 10.1. Trực giác toán học

Với một hash đủ đều, quan sát một chuỗi có **nhiều bit 0 đầu** là một sự kiện hiếm. Số lượng khóa phân biệt càng lớn, cơ hội thấy một giá trị băm có chuỗi 0 đầu dài càng tăng.

HLL chia không gian hash thành **m bucket**, mỗi bucket giữ thông tin liên quan đến **độ dài chuỗi bit 0 đầu lớn nhất** đã quan sát. Nó kết hợp các thanh ghi bằng một bộ ước lượng có bước điều chỉnh cho miền số nhỏ/lớn theo biến thể.

~~~text
Luồng:
u1, u2, u1, u3, u4, u2, u5, ...

Số khóa phân biệt thật: 5

HyperLogLog:
không giữ danh sách {u1,u2,u3,u4,u5};
chỉ giữ thông tin thống kê trong các register.
~~~

HLL không thể biết **ID nào** đã xuất hiện từ các thanh ghi, và cũng không phải Bloom filter để hỏi chính xác membership của một ID.

### 10.2. Sai số thống kê

Với HLL cổ điển và giả định băm phù hợp, sai số chuẩn tương đối (*relative standard error*) thường được xấp xỉ bằng:

\[
\boxed{\mathrm{RSE}\approx\frac{1.04}{\sqrt m}}.
\]

Ví dụ:

~~~text
m = 4096 thanh ghi
sqrt(m) = 64

RSE xấp xỉ = 1,04 / 64 = 0,01625
             = 1,625%.
~~~

Nếu giả sử lưu mỗi thanh ghi trong **một byte**, vùng lưu thanh ghi chiếm **4 KiB**; các triển khai thực tế có thể dùng biểu diễn nén hoặc metadata khác.

**Diễn giải quan trọng:** RSE là **độ lệch chuẩn tương đối thống kê**, không phải cam kết “mọi kết quả luôn nằm trong ±1,625% giá trị thật”. HLL có thể **đếm cao hoặc đếm thấp**; những trường hợp cardinality nhỏ/rất lớn, hash kém hoặc điều chỉnh không phù hợp có thể cần phân tích riêng.

### 10.3. Hợp nhất HyperLogLog

Hai HLL tương thích về **số thanh ghi, hash, seed và cách chia bucket** có thể hợp nhất bằng **max từng thanh ghi tương ứng**. Điều này thích hợp cho việc ước lượng số người dùng duy nhất trong **hợp nhiều phân vùng**.

Nếu chỉ cộng hai ước lượng distinct, một người xuất hiện ở cả hai phân vùng bị tính hai lần. HLL merge tránh phép cộng ngây thơ ấy nhờ kết hợp dấu vết hash.

### 10.4. Trường hợp không nên dùng HLL

- Cần **liệt kê tất cả ID** → HLL không lưu chúng.
- Cần **cardinality chính xác** của một tập nhỏ → set chính xác thường dễ và có thể ít phức tạp hơn.
- Cần **membership** cho một ID → dùng set/Bloom theo mức chính xác cần thiết.
- Cần **distinct chính xác theo một cửa sổ trượt với xóa dữ liệu cũ** → HLL thường không cho phép xóa trực tiếp từng khóa; cần phân vùng theo thời gian, tái xây hoặc cấu trúc cửa sổ chuyên dụng.

## 11. Reservoir sampling: ít bộ nhớ để giữ mẫu đại diện

Một luồng có thể rất dài và **không biết trước số phần tử n**. Nếu muốn chọn ngẫu nhiên k **entry** sao cho **mỗi entry trong toàn bộ luồng có xác suất k/n xuất hiện trong mẫu** (khi n ≥ k), thuật toán **reservoir sampling (Algorithm R)** giải quyết với O(k) bộ nhớ.

Đây là một dạng đánh đổi: kết quả mẫu chứa các **entry thật**, nhưng **không phải toàn bộ dữ liệu**. Những thống kê suy ra từ mẫu có thể có **sai số lấy mẫu**; bản thân entry trong mẫu không phải dữ liệu bị làm tròn.

### 11.1. Thuật toán

1. Giữ k phần tử đầu vào một mảng **reservoir**.
2. Khi gặp phần tử thứ i, với i > k, chọn ngẫu nhiên một số nguyên j trong [1,i].
3. Nếu j ≤ k, thay phần tử ở reservoir[j−1] bằng entry mới.
4. Nếu j > k, bỏ entry mới.
5. Khi hết luồng, trả reservoir. Nếu n < k, trả toàn bộ n phần tử đã thấy.

~~~text
k = 3
Đã đọc 3 entry:
reservoir = [A, B, C]

Gặp entry thứ 4 là D:
chọn j đều từ {1,2,3,4}.

Nếu j=2:
reservoir = [A, D, C].

Nếu j=4:
reservoir giữ nguyên.
~~~

### 11.2. Vì sao mỗi entry có xác suất k/n?

Khi gặp entry thứ i>k:

- Entry mới được chọn vào reservoir với xác suất **k/i**.
- Một entry cũ đã nằm trong mẫu bị thay với xác suất **1/i**: xác suất chọn ô cụ thể của nó trong i lựa chọn.
- Vì vậy một entry cũ sống sót qua bước i với xác suất **(i−1)/i**.

Với một entry đã có xác suất **k/(i−1)** ở thời điểm i−1, sau bước i xác suất còn được giữ là:

\[
\frac{k}{i-1}\cdot\frac{i-1}{i}=\frac{k}{i}.
\]

Từ cơ sở i=k, quy nạp cho thấy sau n phần tử, mỗi entry có **xác suất k/n** nằm trong mẫu.

### 11.3. Python

~~~python
import random


def reservoir_sample(stream, k: int, seed=None):
    if k < 0:
        raise ValueError("k phải không âm")
    if k == 0:
        return []

    rng = random.Random(seed)
    reservoir = []

    for i, entry in enumerate(stream, start=1):
        if i <= k:
            reservoir.append(entry)
        else:
            # j đồng đều trong [0, i-1].
            j = rng.randrange(i)
            if j < k:
                reservoir[j] = entry

    return reservoir


sample = reservoir_sample(range(100), k=10, seed=7)
assert len(sample) == 10
assert len(set(sample)) == 10
assert all(0 <= x < 100 for x in sample)

assert reservoir_sample([1, 2], 5, seed=7) == [1, 2]
assert reservoir_sample([], 3, seed=7) == []
assert reservoir_sample([1, 2, 3], 0, seed=7) == []
~~~

Mã có **O(n)** thời gian để xét từng entry của luồng và **O(k)** bộ nhớ. Với k=0 có thể trả ngay mà không đọc stream.

**Lưu ý:** Nếu một giá trị xuất hiện nhiều lần, mỗi **lần xuất hiện là một entry riêng** có xác suất chọn theo số lần xuất hiện. Đây **không phải lấy mẫu đều trên các giá trị phân biệt**. Nếu cần lấy mẫu có trọng số, lấy mẫu không hoàn lại theo khóa hoặc yêu cầu thống kê khác, phải dùng thuật toán tương ứng.

### 11.4. Kết quả mẫu có thể sai như thế nào?

Reservoir sampling bảo đảm phân phối lựa chọn **đều theo entry**, không bảo đảm một mẫu nhỏ luôn phản ánh đúng tỷ lệ dân số cho từng nhóm.

Ví dụ nếu 1% luồng thuộc nhóm hiếm và k rất nhỏ, mẫu có thể **không chứa phần tử nhóm hiếm nào** dù thuật toán đúng. Đó là **sai số lấy mẫu**, không phải lỗi lập trình. Cần chọn k theo mức tin cậy/yêu cầu phân tích, và cân nhắc lấy mẫu phân tầng nếu nhóm hiếm rất quan trọng.

## 12. Sketch phân vị: sai số thứ hạng không giống sai số giá trị

Một hệ thống đo độ trễ thường quan tâm **p50, p95, p99** thay vì giữ mọi độ trễ để sort.

Ví dụ 99% request mất khoảng 50–100 ms, còn 1% rất chậm; ta cần ước lượng **p99** để phát hiện đuôi phân phối.

Một **quantile sketch** như KLL hoặc một cấu trúc tóm tắt phân vị phù hợp có thể lưu ít hơn toàn bộ dữ liệu nhưng trả **phân vị xấp xỉ**.

### 12.1. Sai số theo rank

Với N phần tử đã sắp, phân vị p liên quan tới **vị trí/rank khoảng pN**. Một bảo đảm kiểu:

\[
|\widehat{rank}-pN|\le\varepsilon N
\]

nghĩa là rank của kết quả có thể lệch **εN vị trí**, không có nghĩa **giá trị thời gian** chênh tối đa ε phần trăm.

Nếu phân phối độ trễ có một **bước nhảy mạnh** gần p99, sai số rank rất nhỏ vẫn có thể dẫn tới sai khác nhiều mili giây.

### 12.2. Không thể chuyển các bảo đảm giữa những sketch

- Bloom: tỷ lệ **dương tính giả** membership.
- CMS: **overestimate tần suất** với sai số cộng εN.
- HLL: **độ lệch tương đối thống kê** của distinct count.
- Quantile sketch: có thể kiểm soát **rank**, với bảo đảm cụ thể tùy thuật toán/biến thể.
- Reservoir sampling: mỗi **entry được chọn đều**, nhưng thống kê trên mẫu có rủi ro lấy mẫu.

Các cấu trúc khác nhau **không cùng thước đo sai số**. Chỉ so “đều dùng 1 MiB” mà không xét câu hỏi cần trả lời sẽ dẫn đến chọn sai cấu trúc.


## 13. Bảng đối chiếu các cấu trúc và mục tiêu

| Cấu trúc | Câu hỏi hỗ trợ | Đơn vị bộ nhớ chính | Loại sai số | Thao tác nổi bật |
| --- | --- | --- | --- | --- |
| **Set chính xác** | Khóa có tồn tại không? | Phụ thuộc số khóa và nội dung khóa | Không sai trong hợp đồng lưu trữ | Membership, insert, delete |
| **Dictionary đếm chính xác** | Tần suất của khóa X? | Một bản ghi/counter cho mỗi khóa | Không sai nếu không overflow | Update, lookup theo key |
| **Bloom filter** | X có thể thuộc tập không? | **m bit** | **Dương tính giả**; không âm tính giả khi chỉ thêm đúng cách | Add, might_contain |
| **Count-Min Sketch** | X xuất hiện bao nhiêu lần? | **w × d ô đếm** | **Đếm cao hơn thật** trong luồng chỉ tăng; cận cộng xác suất | Add count, estimate |
| **HyperLogLog** | Khoảng bao nhiêu khóa phân biệt? | **m thanh ghi** | Có thể cao hoặc thấp; RSE tương đối | Add, estimate cardinality, merge |
| **Reservoir sampling** | Một mẫu k entry đều từ luồng? | **k entry** | Không lưu toàn bộ; thống kê mẫu có sai số lấy mẫu | Update mẫu theo luồng |
| **Quantile sketch** | p50/p95/p99 xấp xỉ? | Bản tóm tắt có kích thước tùy thuật toán | Sai số rank/ước lượng phân vị | Update, query quantile |
| **Skip list ngẫu nhiên** | Tìm/chèn/xóa khóa chính xác? | O(n) kỳ vọng | **Kết quả chính xác**; thời gian ngẫu nhiên | Search/insert/delete |

**Bộ nhớ cơ bản không đồng nghĩa toàn bộ footprint.** Mảng bit có metadata, bảng counter có kích thước counter, set lưu thêm hash/khóa và con trỏ, còn mã Python có overhead đối tượng lớn hơn biểu diễn mảng byte/từ máy thuần túy.

### 13.1. Chọn cấu trúc từ câu hỏi, không từ tên thuật toán

**Nếu cần kiểm tra membership và có bước xác minh sau:** Bloom filter là ứng viên.

**Nếu cần tần suất của một khóa do hệ thống cung cấp:** Count-Min Sketch là ứng viên.

**Nếu cần số ID phân biệt toàn luồng:** HyperLogLog là ứng viên.

**Nếu cần nhìn một nhóm entry đại diện, không phải ước lượng tần suất của mọi ID:** Reservoir sampling.

**Nếu cần p99 của dữ liệu có phân phối lệch:** Quantile sketch với bảo đảm rank phù hợp.

**Nếu cần trả lời chính xác, không chấp nhận sai số:** Set, dictionary, cây hoặc cấu trúc chính xác phù hợp thường là lựa chọn mặc định. Có thể dùng cấu trúc xấp xỉ **để lọc** nhưng phải xác minh bước cuối.

### 13.2. Xác suất không luôn làm truy vấn nhanh hơn

Với Bloom filter, mỗi membership query thường cần h phép băm. Với CMS, một query cần d lần băm và đọc bộ đếm. Một dictionary được cache tốt có thể truy vấn rất nhanh.

Giá trị của sketch thường xuất hiện khi **dung lượng dữ liệu lớn**, **truy vấn nguồn chính xác đắt tiền**, **truyền dữ liệu qua mạng tốn kém**, hoặc muốn giữ **summary của nhiều phân vùng**. Nếu n nhỏ và bộ nhớ dồi dào, cấu trúc chính xác có thể vừa nhanh vừa đơn giản hơn.

### 13.3. Hợp nhất không có một công thức chung

- Bloom filter tương thích: **OR theo bit**.
- Count-Min Sketch tương thích: **cộng từng ô đếm**.
- HyperLogLog tương thích: **max từng thanh ghi**.
- Reservoir sampling ở nhiều nguồn: không thể chỉ **nối hai mẫu kích thước k rồi chọn tùy ý** nếu số lượng phần tử gốc mỗi nguồn khác nhau; cần giải pháp sampling phân tán có xác suất theo kích thước nguồn.
- Quantile sketch: phép merge phải tuân theo **API và bảo đảm của thuật toán cụ thể**.

Một giao diện mang tên “merge” không làm mọi cấu trúc có cùng tính chất toán học.

## 14. Thiết kế ngân sách sai số: từ yêu cầu nghiệp vụ tới số bit

### 14.1. Bước 1 — Xác định loại sai số có thể chấp nhận

Trước khi chọn tham số, hãy hỏi:

1. Có cho phép **false positive** không?
2. Có cho phép **false negative** không?
3. Có cho phép **đếm cao hơn** hay **đếm thấp hơn** không?
4. Sai số cần giới hạn trên **một truy vấn**, **một ngày**, hay **toàn bộ hệ thống**?
5. Có bước **xác minh chính xác** ở cuối không?
6. Sai số gây hậu quả **tăng tải**, **bỏ sót cơ hội**, hay **vi phạm an toàn/tính đúng đắn**?

Ví dụ, Bloom filter phù hợp để giảm số truy vấn không cần thiết. Nhưng không được dùng “có thể đã thanh toán” như bằng chứng thanh toán, hay dùng một cấu trúc có false positive để tự động cấp quyền truy cập.

### 14.2. Bước 2 — Xác định quy mô n và đặc tính khóa

Đối với Bloom, cần ước lượng **số khóa phân biệt tối đa trong vòng đời bộ lọc**. Với CMS, cần hiểu **tổng trọng số N** và số khóa có thể truy vấn. Với HLL, cần biết phạm vi cardinality mà thuật toán cần hoạt động tốt.

Đối với cả ba, chất lượng hash và mã hóa khóa ảnh hưởng đến độ chính xác. Phân tích lý thuyết trên một họ hash ngẫu nhiên phù hợp không tự bảo đảm cùng kết quả với mọi hàm hash tự viết.

### 14.3. Bước 3 — Chọn tham số theo ngân sách

Ví dụ lọc membership cho **một triệu khóa phân biệt**:

| Mục tiêu FPR | Số bit gần đúng | Dung lượng mảng bit | Số vị trí băm gần tối ưu |
| --- | ---: | ---: | ---: |
| 10% | 4,79 triệu | 0,57 MiB | 3 |
| 1% | 9,59 triệu | 1,14 MiB | 7 |
| 0,1% | 14,38 triệu | 1,71 MiB | 10 |
| 0,01% | 19,17 triệu | 2,29 MiB | 13 |

Các giá trị là **ước lượng công thức**, chưa tính metadata và overhead; số vị trí băm là số nguyên gần mức tối ưu.

Giảm FPR từ 1% xuống 0,1% có thể giảm các trường hợp không tồn tại bị đưa tới CSDL từ khoảng **95.000 xuống 9.500** trong workload 10 triệu truy vấn đã nêu. Tuy nhiên, đổi lại phải tính thêm bộ nhớ và **nhiều phép băm hơn trên mọi truy vấn**.

### 14.4. Bước 4 — Xác định cách đo thực tế

Không chỉ dựa vào công thức; khi có dữ liệu kiểm định chính xác, hãy đo:

- **FPR quan sát được** trên các khóa chắc chắn vắng mặt.
- **Tỷ lệ bit 1 / độ bão hòa** của Bloom.
- **Độ lệch estimate(x) − exact_count(x)** của CMS trên một tập khóa kiểm chứng.
- **Sai số tương đối** của HLL trên tập nhỏ có cardinality chính xác.
- **Sai số rank** của phân vị, đặc biệt ở đuôi như p99.
- **Bộ nhớ thực tế** tính cả thư viện/metadata và **độ trễ p50/p95/p99** của các thao tác.
- **Chi phí xác minh** sau bộ lọc, không chỉ CPU của bản thân cấu trúc.

Bước đo này thuộc quy trình phát triển/đánh giá ứng dụng thực tế; **không thay thế bảo đảm lý thuyết**, và bản thân đo thống kê cũng có sai số mẫu.

### 14.5. Bước 5 — Có kế hoạch khi giả định bị vi phạm

Một hệ thống cần phản ứng nếu:

- **n vượt dự báo** → Bloom bão hòa, FPR tăng.
- **Tổng N tăng** → Sai số cộng εN của CMS lớn hơn.
- **Hash version hoặc kiểu encoding thay đổi** → Bản tóm tắt cũ có thể không tương thích.
- **Dữ liệu được xóa / hết hạn** → Cần cửa sổ thời gian hoặc biến thể cho delete, không dùng giả định insert-only.
- **Dữ liệu đến từ nhiều máy** → Cần hợp nhất đúng phép toán và metadata.
- **Truy vấn bị đối thủ điều khiển** → Không áp dụng ngây thơ các giả định về truy vấn ngẫu nhiên.

### 14.6. Kết quả chính xác cuối cùng và chỉ mục xấp xỉ

Có thể thiết kế **hai tầng**:

~~~text
Tầng 1: Bloom / sketch nhỏ, phản hồi nhanh
              |
         Quyết định sơ bộ
              |
Tầng 2: Set / database / log có chứng cứ chính xác
              |
        Quyết định cuối cùng
~~~

Cách này giữ lợi ích về tốc độ/bộ nhớ của tầng xấp xỉ nhưng không bắt buộc đem rủi ro sai số vào **quyết định nghiệp vụ chính xác**.

Ví dụ đối với kiểm tra ID đã được duyệt, “Bloom trả False” chỉ là bằng chứng không có khi chính sách **đã cập nhật đầy đủ**. “Bloom trả True” phải tra nguồn có thẩm quyền. Với thanh toán, bảo mật hoặc quyền truy cập, không được chỉ dựa vào bộ lọc xấp xỉ để ra quyết định cấp quyền hoặc từ chối.

## 15. Các lỗi suy luận và triển khai thường gặp

| Lỗi | Tại sao sai? | Cách hiểu/sửa đúng |
| --- | --- | --- |
| “Cấu trúc xác suất luôn trả lời sai đôi khi” | Skip list ngẫu nhiên có thể luôn trả đúng | Phân biệt ngẫu nhiên hóa thời gian với xấp xỉ kết quả |
| “FPR 1% nghĩa là 1% mọi truy vấn bị sai” | FPR tính trên **truy vấn thực sự âm tính** | Mẫu số là FP+TN |
| “1% kết quả ‘có thể có’ là sai” | Tỷ lệ này còn phụ thuộc tỷ lệ khóa thật có | Dùng base rate/conditional probability |
| “Bloom trả True nghĩa là chắc chắn có” | Bloom có dương tính giả | Dương tính cần kiểm chứng nếu đòi chính xác |
| “Bloom có thể xóa bằng cách tắt bit” | Bit dùng chung giữa các khóa | Dùng biến thể thích hợp hoặc tái xây |
| “Bloom có âm tính giả do va chạm hash” | Va chạm chỉ có thể bật thêm bit | Trong insert-only đúng cách, không âm tính giả |
| “Đổi seed của Bloom mà vẫn giữ bit” | Vị trí cũ và mới không khớp | Seed/version phải đi cùng dữ liệu |
| “Thêm càng nhiều hash càng tốt” | Bit bão hòa nhanh, CPU tăng | Chọn h gần (m/n)ln2 |
| “n trong Bloom là số lượt add kể cả trùng” | Bit của một key lặp lại không tạo khóa mới | Dùng số khóa phân biệt dự kiến |
| “Bloom luôn có FPR đúng p đã chọn” | Công thức có giả định hash và n | p là mục tiêu/xấp xỉ, cần đo trên workload |
| “Có thể liệt kê mọi khóa từ mảng bit” | Dữ liệu danh tính đã bị mất | Giữ nguồn khóa chính xác nếu cần liệt kê |
| “CMS trả số đếm chính xác” | Các khóa va chạm ô đếm | CMS có thể overestimate |
| “CMS có sai số ε% của từng f(x)” | Công thức là **εN** cộng thêm | Phân biệt sai số cộng với tương đối |
| “CMS estimate lớn nghĩa là chắc chắn heavy hitter” | Có thể bị va chạm phóng đại | Kiểm chứng hoặc có khoảng bất định |
| “CMS có thể tự liệt kê mọi khóa nặng” | Không lưu danh tính khóa | Kết hợp với tracker ứng viên |
| “Dùng counter tràn vẫn giữ bất biến CMS” | Overflow làm số giảm/đổi dấu | Chọn counter đủ lớn, phát hiện overflow |
| “CMS có update âm mà vẫn bảo đảm như chỉ-thêm” | Chứng minh một phía dựa vào tăng không âm | Cần mô hình turnstile/biến thể khác |
| “HLL có FPR như Bloom” | HLL trả ước lượng cardinality | Dùng sai số tương đối/RSE |
| “RSE 1,6% là sai số tối đa 1,6%” | RSE là độ lệch chuẩn thống kê | Không đồng nhất với chặn tuyệt đối |
| “Cộng distinct của hai máy sẽ cho distinct chung” | ID xuất hiện ở cả hai bị đếm hai lần | Merge HLL tương thích hoặc tính hợp chính xác |
| “Reservoir luôn phản ánh đúng tỷ lệ nhóm hiếm” | Mẫu có dao động ngẫu nhiên | Phân tích sai số lấy mẫu |
| “Lấy mẫu đều theo entry là đều theo giá trị phân biệt” | Giá trị lặp xuất hiện nhiều entry | Xác định rõ đơn vị lấy mẫu |
| “Sai số rank p99 là sai số ms” | Chênh rank và chênh giá trị khác nhau | Đọc đúng bảo đảm của sketch phân vị |
| “Hai sketch khác seed vẫn cộng/OR/max tùy ý” | Các ô/register không tương ứng | Kiểm tra metadata tương thích |
| “Đo một vài truy vấn đủ bảo đảm cho mọi đối thủ” | Workload thích nghi khác phân bố ngẫu nhiên | Xác định mô hình đe dọa/bảo đảm |
| “Cấu trúc xấp xỉ tự đồng bộ với CSDL” | Có thể thiếu cập nhật sau lỗi mạng | Duy trì độ nhất quán nguồn chính xác |
| “Dùng Bloom để cấp quyền truy cập” | False positive có hậu quả an ninh | Luôn xác minh ở nguồn có thẩm quyền |

**Bài học chung:** Trước khi tối ưu, phải chỉ rõ **đại lượng được xấp xỉ, chiều sai số, công thức xác suất, giả định về luồng và nguồn sự thật**. Sai số không có hợp đồng là **lỗi khó kiểm soát**, không phải tối ưu hóa.


## 16. Bài tập tự luyện có đáp án

### Nhóm A — Hiểu bản chất sai số

**Bài 1 — Ngẫu nhiên có đồng nghĩa sai?** Một skip list chọn chiều cao nút bằng tung đồng xu nhưng tìm kiếm vẫn so sánh đầy đủ các khóa. Nó có nhất thiết trả kết quả membership sai không?

*Đáp án:* **Không**. Nó có thể luôn trả đúng; sự ngẫu nhiên ảnh hưởng tới hình dạng và **thời gian kỳ vọng**, không bắt buộc ảnh hưởng tới tính đúng của kết quả.

**Bài 2 — Monte Carlo và Las Vegas.** Trong hai mô hình, mô hình nào chấp nhận xác suất sai kết quả, còn mô hình nào giữ kết quả đúng nhưng thời gian có thể ngẫu nhiên?

*Đáp án:* **Monte Carlo** có thể chấp nhận một xác suất sai theo đặc tả; **Las Vegas** trả đáp án đúng và để chi phí chạy phụ thuộc ngẫu nhiên.

**Bài 3 — FP và FN.** Một khóa Z chưa được insert nhưng Bloom trả “có thể có”. Đây là loại lỗi nào?

*Đáp án:* **False positive (dương tính giả)**.

**Bài 4 — Định nghĩa FPR.** Nếu có 10.000 truy vấn thực sự âm tính và 200 lần trả sai dương tính, FPR quan sát được là bao nhiêu?

*Đáp án:* **200/10.000 = 2%**, bất kể có bao nhiêu truy vấn thực sự dương tính.

**Bài 5 — Đọc FPR có điều kiện.** Bloom có FPR 1% nhưng chỉ 5% truy vấn thực sự có. Có thể nói “1% kết quả có thể có là sai” không?

*Đáp án:* **Không**. Theo ví dụ với 10 triệu truy vấn, khoảng **95.000/595.000 ≈ 15,97%** câu trả lời “có thể có” là dương tính giả.

**Bài 6 — Chi phí ngẫu nhiên và khấu hao.** Một thao tác có O(log n) thời gian kỳ vọng có tự động bảo đảm O(log n) thời gian xấu nhất cho mọi lần gọi không?

*Đáp án:* **Không**. Cần phân biệt expectation, worst-case, amortized và xác suất vượt ngưỡng.

### Nhóm B — Bloom filter

**Bài 7 — Bất biến bit.** Bloom filter insert-only biến đổi bit theo những chiều nào?

*Đáp án:* Chỉ **0→1** hoặc giữ nguyên; không có chuyển **1→0**.

**Bài 8 — Vì sao không âm tính giả?** Một khóa X đã được add thành công. Tại sao query X không trả False trong mô hình chuẩn?

*Đáp án:* **Tất cả h vị trí băm của X đã được bật** và không có thao tác nào tắt chúng.

**Bài 9 — False positive.** Vì sao Bloom có thể trả True cho khóa chưa được thêm?

*Đáp án:* Các khóa khác có thể đã **bật đủ những vị trí băm** của khóa đang hỏi.

**Bài 10 — Dung lượng.** Công thức xấp xỉ số bit m của Bloom theo n khóa phân biệt và FPR p là gì?

*Đáp án:* **m ≈ −n ln(p)/(ln 2)²**, giả định mô hình hàm băm lý tưởng.

**Bài 11 — Số hash.** Số vị trí băm gần tối ưu là bao nhiêu?

*Đáp án:* **h ≈ (m/n) ln 2**, làm tròn thành số nguyên dương.

**Bài 12 — Ví dụ 10.000 khóa.** Với n=10.000 và p mục tiêu 1%, khoảng bao nhiêu bit và bao nhiêu hash?

*Đáp án:* Khoảng **95.851 bit**, chọn **7 vị trí băm**, tương đương khoảng **11,7 KiB** mảng bit, chưa kể overhead.

**Bài 13 — Khi n tăng.** Bloom thiết kế cho 1 triệu khóa nhưng sau đó có 5 triệu khóa phân biệt. Điều gì có thể xảy ra?

*Đáp án:* Các bit bão hòa hơn, **FPR thường tăng**; cần xây lại hoặc dùng cấu trúc mở rộng thích hợp.

**Bài 14 — Khóa trùng.** Add cùng một key 100 lần có bật thêm bit mới ngoài lần đầu không?

*Đáp án:* **Không**, vì cùng key luôn băm vào cùng các vị trí theo cùng thông số.

**Bài 15 — Xóa khóa.** Tại sao không được xóa một key bằng cách tắt tất cả các bit của nó?

*Đáp án:* Các key khác có thể dùng chung bit; tắt sẽ tạo **false negative** cho các key ấy.

**Bài 16 — Truy vấn CSDL.** Bloom trả True cho khóa X trong một hệ thống yêu cầu membership chính xác. Có được kết luận X tồn tại không?

*Đáp án:* **Không**; phải kiểm tra nguồn chính xác. Bloom True chỉ có nghĩa **có thể tồn tại**.

**Bài 17 — Sai do không đồng bộ.** CSDL đã thêm X nhưng thao tác cập nhật Bloom bị bỏ lỡ. Bloom trả False cho X là do giả định nào bị vi phạm?

*Đáp án:* Bộ lọc không còn **bao phủ đầy đủ tập khóa của CSDL**; lỗi ở đồng bộ hệ thống, nằm ngoài bảo đảm insert-only khi khóa đã add.

**Bài 18 — Hợp nhất.** Hai Bloom filter muốn OR từng bit cần điều kiện gì?

*Đáp án:* **Cùng m, h, hash/seed/version và quy tắc mã hóa khóa**.

### Nhóm C — Count-Min Sketch

**Bài 19 — CMS trả gì?** CMS là một membership filter Boolean hay bộ ước lượng tần suất?

*Đáp án:* **Bộ ước lượng tần suất** theo khóa đã biết.

**Bài 20 — Tại sao lấy min?** Tại sao query CMS lấy **min** của những bộ đếm được băm tới?

*Đáp án:* Mỗi hàng chứa **tần suất thật + phần va chạm không âm**. Lấy min chọn hàng có ít va chạm nhất.

**Bài 21 — Truy vết.** Tần suất thật của A là 5; ba hàng trả 8, 6, 7. Ước lượng của CMS là bao nhiêu?

*Đáp án:* **min(8,6,7)=6**; overestimate 1.

**Bài 22 — Sai số một phía.** Với update không âm và không overflow, CMS có thể trả estimate(x) nhỏ hơn f(x) không?

*Đáp án:* **Không**, theo bất biến các bộ đếm luôn chứa đóng góp của x cộng đóng góp khóa khác.

**Bài 23 — Công thức ε.** Khi N=1.000.000, ε=0,001, ngưỡng sai số cộng theo bảo đảm tiêu chuẩn là bao nhiêu?

*Đáp án:* **εN=1.000** đơn vị đếm.

**Bài 24 — Đọc sai số.** Nếu f(x)=2 và CMS ước lượng 600, có nhất thiết vi phạm bảo đảm εN=1.000 không?

*Đáp án:* **Không**. Sai số cộng 598 vẫn nhỏ hơn 1.000; cận không phải sai số tương đối 0,1% của 2.

**Bài 25 — Số hàng/cột.** Với ε=0,001, δ=0,01, chọn w và d theo công thức nào và được bao nhiêu gần đúng?

*Đáp án:* **w=⌈e/ε⌉=2719**, **d=⌈ln(1/δ)⌉=5**, tức **13.595 ô đếm**.

**Bài 26 — Heavy hitter.** Nếu CMS estimate(x) thấp hơn T, có thể kết luận tần suất thật nhỏ hơn T trong mô hình insert-only không?

*Đáp án:* **Có**, vì f(x)≤estimate(x)<T. Nếu estimate≥T thì vẫn có khả năng **dương tính giả theo ngưỡng** do overestimate.

**Bài 27 — Tìm tên khóa phổ biến.** Chỉ có bảng CMS, không có danh sách khóa hay tracker ứng viên. Có thể liệt kê toàn bộ tên khóa từng xuất hiện không?

*Đáp án:* **Không**. Bảng không lưu danh tính từng key; cần một cách giữ ứng viên riêng.

**Bài 28 — Update âm.** Có được áp dụng nguyên bảo đảm một phía của CMS insert-only cho một chương trình cho phép trừ tùy ý khỏi những ô đếm không?

*Đáp án:* **Không**. Phải định nghĩa lại mô hình update và chọn biến thể/định lý thích hợp.

### Nhóm D — Distinct, sampling, quantile

**Bài 29 — Cardinality.** Muốn ước lượng số người dùng phân biệt trong luồng ID lớn, trong các cấu trúc đã học nên nghĩ tới cấu trúc nào?

*Đáp án:* **HyperLogLog** nếu cho phép sai số thống kê; set nếu cần đếm chính xác.

**Bài 30 — HLL RSE.** HLL có m=4096 thanh ghi. Sai số chuẩn tương đối gần đúng là bao nhiêu?

*Đáp án:* **1,04/√4096 = 1,04/64 ≈ 1,625%**.

**Bài 31 — RSE có phải cận tuyệt đối?** HLL RSE≈1,625% có nghĩa không kết quả nào sai quá 1,625% không?

*Đáp án:* **Không**. RSE mô tả độ lệch chuẩn thống kê, không phải biên sai số tuyệt đối cho mọi lần chạy.

**Bài 32 — Merge distinct.** Hai phân vùng có các ID trùng nhau. Tại sao không cộng trực tiếp hai ước lượng HLL?

*Đáp án:* ID chung sẽ bị **đếm hai lần**. Các HLL tương thích nên merge bằng **max từng thanh ghi**.

**Bài 33 — Reservoir sampling.** Lấy mẫu k=10 từ n=1000 entry bằng reservoir sampling chuẩn. Mỗi entry có xác suất có mặt trong mẫu cuối là bao nhiêu?

*Đáp án:* **k/n=10/1000=1%**.

**Bài 34 — Lấy mẫu giá trị trùng.** Nếu giá trị A xuất hiện 100 lần trong stream, reservoir sampling theo entry có chọn đều trên **các giá trị phân biệt** không?

*Đáp án:* **Không**. Mỗi lần xuất hiện là một entry riêng; giá trị xuất hiện nhiều lần có cơ hội xuất hiện trong mẫu cao hơn.

**Bài 35 — Phân vị p99.** Một sketch bảo đảm sai số rank ±0,001N. Nếu N=1.000.000, điều đó có nghĩa độ trễ p99 chỉ sai ±0,1% mili giây không?

*Đáp án:* **Không**. Nó bảo đảm **rank lệch tối đa 1.000 vị trí** theo điều kiện thuật toán, không phải giá trị ms lệch 0,1%.

### Nhóm E — Chọn kiến trúc an toàn

**Bài 36 — Cấp quyền.** Có thể dùng Bloom True như điều kiện duy nhất để cho người dùng truy cập tài nguyên bảo mật không?

*Đáp án:* **Không**. Dương tính giả có thể cấp quyền sai; phải xác thực/ủy quyền qua nguồn chính xác.

**Bài 37 — Chọn theo câu hỏi.** Hệ thống cần cả membership nhanh và tần suất cho một khóa. Một Bloom duy nhất có trả số lần xuất hiện được không?

*Đáp án:* **Không**. Bloom phục vụ membership xấp xỉ; có thể cần thêm **CMS hoặc bộ đếm chính xác**, tùy yêu cầu.

**Bài 38 — Truy vấn ở quy mô lớn.** Một bảo đảm δ=0,01 cho một truy vấn có chứng minh luôn ≤1% khả năng ít nhất một lỗi trong 10.000 truy vấn không?

*Đáp án:* **Không**. Bảo đảm riêng từng truy vấn không tự cho cận đồng thời toàn hệ thống; cần phân bổ ngân sách/union bound và xét truy vấn có thích nghi không.

**Bài 39 — Dữ liệu hết hạn.** Cần đếm distinct theo cửa sổ 1 giờ trượt với việc quên những sự kiện cũ. Có thể dùng một HLL duy nhất với thao tác “xóa ID cũ” tùy ý không?

*Đáp án:* **Không**. HLL thường không hỗ trợ xóa trực tiếp; cần **phân vùng thời gian, tái dựng hoặc cấu trúc cửa sổ chuyên dụng**.

**Bài 40 — Quyết định đầu tư bộ nhớ.** Giảm Bloom FPR từ 1% xuống 0,1% có chắc làm toàn hệ thống nhanh hơn không?

*Đáp án:* **Không chắc**. Giảm truy vấn dương tính giả nhưng tăng số bit/hash và chi phí vận hành. Cần so **độ trễ, CPU, bộ nhớ, tỷ lệ truy vấn âm tính và chi phí xác minh**.

## 17. Tổng kết và cách ghi nhớ

Cấu trúc xác suất và xấp xỉ hữu ích khi **không thể hoặc không cần giữ toàn bộ dữ liệu chính xác trong bộ nhớ**, nhưng phải nắm rõ loại câu hỏi và **hợp đồng sai số**.

**Bloom filter** trả lời membership xấp xỉ: **False = chắc chắn vắng mặt**, **True = có thể tồn tại** theo mô hình chỉ-thêm, đầy đủ và đồng bộ. Nó dùng khoảng **m bit** và h vị trí băm; tỷ lệ dương tính giả phụ thuộc **n, m, h và hash**.

**Count-Min Sketch** ước lượng tần suất từng khóa: trong luồng chỉ tăng, **estimate(x) ≥ f(x)**; cận xác suất điển hình có sai số **cộng thêm εN**, không phải ε phần trăm tần suất riêng của mọi khóa.

**HyperLogLog** ước lượng **số khóa phân biệt**, có sai số tương đối thống kê. **Reservoir sampling** chọn **mẫu k entry đều** từ một luồng mà không lưu toàn bộ dữ liệu. **Quantile sketch** tóm tắt phân phối để trả phân vị, thường cần đọc **sai số rank** đúng nghĩa.

Không phải mọi cấu trúc dùng ngẫu nhiên đều trả kết quả xấp xỉ: **skip list ngẫu nhiên** có thể giữ kết quả tìm kiếm chính xác và chỉ đánh đổi **thời gian kỳ vọng**.

**Ghi nhớ:** **Xác định câu hỏi → chọn loại sai số chấp nhận → định lượng ngân sách bộ nhớ/CPU → kiểm tra giả định → đo trên workload → giữ nguồn xác minh chính xác khi cần.** Chỉ chấp nhận sai số khi biết rõ **sai theo hướng nào, với xác suất nào và hậu quả gì**. Sự đánh đổi là một quyết định thiết kế có kiểm soát, không phải lời cho phép kết quả sai tùy ý.
