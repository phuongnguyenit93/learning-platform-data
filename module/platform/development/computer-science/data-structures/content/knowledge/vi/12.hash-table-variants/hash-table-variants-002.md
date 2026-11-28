# Băm hoàn hảo cho tập khóa tĩnh

Trong một bảng băm thông thường, hai khóa khác nhau có thể được đưa đến cùng một ô. Khi ấy, bảng phải xử lý **va chạm** bằng danh sách liên kết (*separate chaining*) hoặc thăm dò (*open addressing*). Nếu **toàn bộ tập khóa đã biết trước và hầu như không thay đổi**, ta có thể đầu tư công sức khi xây dựng bảng để mọi khóa đang lưu có một địa chỉ riêng.

Đó là ý tưởng của **băm hoàn hảo** (*perfect hashing*). Trong chương **Biến thể bảng băm** thuộc nền tảng cấu trúc dữ liệu, bài học này giải thích bất biến của băm hoàn hảo, cách xây dựng bảng hai tầng FKS, độ phức tạp thời gian và bộ nhớ, cũng như thời điểm nên sử dụng nó.

## 1. Định nghĩa và phạm vi áp dụng

Cho tập **khóa phân biệt** \(S=\{k_1,k_2,\ldots,k_n\}\) và hàm băm \(h\) đưa các khóa tới tập địa chỉ. Hàm \(h\) được gọi là **hoàn hảo trên \(S\)** khi:

\[
\forall x,y\in S,\quad x\ne y\ \Longrightarrow\ h(x)\ne h(y).
\]

Nghĩa là **không có hai khóa thuộc \(S\) va chạm**. Bảo đảm này chỉ áp dụng cho các khóa **đã biết khi xây dựng**, không áp dụng tự động cho toàn bộ miền khóa có thể xuất hiện.

Ví dụ, với \(S=\{11,18,25\}\), hàm \(h(k)=k\bmod 5\) đưa ba khóa đến các ô \(1,3,0\). Hàm này hoàn hảo trên \(S\), dù hai khóa khác như \(11\) và \(16\) vẫn có cùng địa chỉ.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Băm thông thường | Có thể có va chạm, cần cơ chế giải quyết |
| **Băm hoàn hảo** | Không có va chạm **giữa các khóa thuộc tập tĩnh \(S\)** |
| **Băm hoàn hảo tối thiểu** (*minimal perfect hashing*, MPH) | Ánh xạ \(n\) khóa phân biệt **song ánh** lên đúng \(n\) địa chỉ \(0,\ldots,n-1\) |

**Băm hoàn hảo không nhất thiết là băm hoàn hảo tối thiểu.** Một cấu trúc hoàn hảo có thể dùng nhiều hơn \(n\) ô; FKS hai tầng là một ví dụ.

### Phải kiểm tra khóa khi truy vấn không thành công

Một khóa **ngoài \(S\)** vẫn có thể bị băm vào ô đang chứa khóa trong \(S\). Chẳng hạn:

```text
Đã lưu:   11 -> ô 1, 18 -> ô 3, 25 -> ô 0
Truy vấn: 16 -> ô 1
Ô 1 chứa 11, nhưng 11 != 16
Kết quả: không tìm thấy 16
```

Vì thế, để kiểm tra một khóa có thuộc tập hay không, chỉ thấy ô có dữ liệu là **chưa đủ**: phải so sánh **khóa thật trong ô** với khóa được hỏi.

## 2. Tại sao tính tĩnh lại quan trọng?

**Tập khóa tĩnh** là tập đã được xác định trước khi xây dựng cấu trúc, ít hoặc không phát sinh thao tác thêm và xóa. Ta có thể thử nhiều hàm băm, đo mức độ va chạm trên toàn bộ tập và chỉ giữ một cấu hình **không va chạm với các khóa đã lưu**.

Chi phí thử và bố trí khóa phát sinh khi **xây dựng**; sau đó ta dùng cấu trúc cố định để **tra cứu nhiều lần**. Ví dụ phù hợp gồm bộ từ khóa cố định của trình biên dịch, danh mục mã lệnh hoặc mã lỗi của một phiên bản phần mềm, và bản đồ ánh xạ chỉ đọc từ ID tới mô tả.

Nếu cần thêm hoặc xóa khóa thường xuyên, tính hoàn hảo có thể bị phá vỡ và cần xây dựng lại một phần hoặc toàn bộ cấu trúc. Vì vậy, băm hoàn hảo là một **lựa chọn thiết kế cho dữ liệu tĩnh**.

## 3. Phương pháp FKS: xây dựng bảng băm hoàn hảo hai tầng

Phương pháp **FKS** (Fredman–Komlós–Szemerédi) dùng **họ hàm băm phổ dụng** (*universal hashing*) và phép chọn ngẫu nhiên để xây dựng một bảng tĩnh. Mục tiêu:

- **Tra cứu \(O(1)\) trong trường hợp xấu nhất** sau khi bảng đã xây dựng thành công.
- **Bộ nhớ \(O(n)\)** cho \(n\) khóa phân biệt.
- **Xây dựng \(O(n)\) theo kỳ vọng**, với giả thiết các phép tính băm và thao tác trên khóa có chi phí hằng số, họ hàm phổ dụng và lựa chọn ngẫu nhiên độc lập.

FKS chia công việc thành hai tầng.

1. **Tầng một:** Chọn hàm \(h_1\) để phân \(n\) khóa vào \(m=n\) nhóm (*bucket*). Nhiều khóa **được phép** thuộc cùng nhóm.
2. **Tầng hai:** Nếu nhóm \(i\) chứa \(b_i\) khóa, cấp một bảng phụ kích thước \(b_i^2\) và tìm hàm \(h_{2,i}\) đưa các khóa trong nhóm đến **các ô khác nhau**.

```mermaid
flowchart TD
    A[Truy vấn khóa k] --> B[Tính nhóm i = h1(k)]
    B --> C[Đọc thông tin bảng phụ i]
    C --> D[Tính địa chỉ j = h2_i(k)]
    D --> E[Truy cập ô j]
    E --> F{Khóa ở ô có bằng k?}
    F -->|Có| G[Tìm thấy]
    F -->|Không hoặc ô trống| H[Không tìm thấy]
```

Sau khi xây dựng, một truy vấn chỉ cần tối đa hai phép băm, một lần đọc ô phụ và một phép so sánh khóa. Không phải duyệt danh sách hay thăm dò hàng loạt ô.

## 4. Xây dựng tầng một

Giả sử \(S\) có \(n>0\) khóa phân biệt và chọn \(m=n\) nhóm. Đặt:

\[
B_i=\{k\in S:h_1(k)=i\},\qquad b_i=|B_i|.
\]

Vì mỗi khóa thuộc đúng một nhóm, \(\sum_{i=0}^{n-1}b_i=n\).

Ta chọn ngẫu nhiên \(h_1\) trong **họ băm phổ dụng**. Sau khi phân nhóm, tính:

\[
Q=\sum_{i=0}^{n-1}b_i^2.
\]

Nếu **\(Q\leq4n\)**, chấp nhận \(h_1\). Nếu không, chọn ngẫu nhiên hàm tầng một mới và phân nhóm lại. Ràng buộc này bảo đảm tổng số ô ở tất cả bảng phụ tầng hai **không quá \(4n\)**.

### Vì sao sẽ tìm được hàm tầng một phù hợp?

Một họ băm phổ dụng vào \(n\) nhóm bảo đảm với mỗi cặp khóa phân biệt \(x,y\):

\[
\Pr[h_1(x)=h_1(y)]\leq\frac1n.
\]

Tổng bình phương kích thước các nhóm có thể viết thành:

\[
Q=n+2\sum_{\{x,y\}\subseteq S}\mathbf1[h_1(x)=h_1(y)].
\]

Theo tính tuyến tính của kỳ vọng:

\[
\mathbb E[Q]\leq n+2\binom n2\frac1n=2n-1<2n.
\]

Theo bất đẳng thức Markov:

\[
\Pr[Q>4n]\leq\frac{\mathbb E[Q]}{4n}<\frac12.
\]

Như vậy, mỗi lần chọn hàm tầng một có **xác suất thành công lớn hơn \(1/2\)**. Khi chọn độc lập ở mỗi lần thử, số lần thử để gặp một hàm đạt ràng buộc là **hằng số theo kỳ vọng**.

## 5. Xây dựng các bảng phụ tầng hai

Với nhóm \(B_i\) có \(b_i\) khóa:

- Nếu \(b_i=0\): không cấp ô phụ.
- Nếu \(b_i=1\): cấp một ô, không cần tìm hàm mới.
- Nếu \(b_i\geq2\): cấp \(s_i=b_i^2\) ô; chọn ngẫu nhiên hàm \(h_{2,i}\) từ họ phổ dụng vào \(s_i\) ô và thử bố trí các khóa. Nếu có va chạm, bỏ cách bố trí đó rồi thử hàm mới.

Tại sao lại cấp **\(b_i^2\) ô** cho một nhóm có \(b_i\) khóa? Với \(b=b_i\geq2\), gọi \(C\) là **số cặp khóa va chạm** trong một lần thử. Họ băm phổ dụng cho:

\[
\mathbb E[C]
\leq\binom b2\frac1{b^2}
=\frac{b-1}{2b}<\frac12.
\]

Vì hễ có va chạm thì \(C\geq1\), suy ra:

\[
\Pr[C\geq1]\leq\mathbb E[C]<\frac12.
\]

Vậy một lần chọn hàm tầng hai có xác suất **không va chạm lớn hơn \(1/2\)**; số lần thử để tìm một hàm đạt yêu cầu có kỳ vọng không quá 2.

**Bất biến cuối cùng** là mỗi khóa ở đúng một nhóm theo \(h_1\), các khóa **trong cùng nhóm** có vị trí phụ riêng theo \(h_{2,i}\), và toàn bộ tham số hàm băm phải **giữ nguyên trong suốt thời gian tra cứu**. Thay đổi hàm đòi hỏi bố trí lại các khóa liên quan.

## 6. Ví dụ tính tay

Xét tập khóa:

\[
S=\{10,17,24,31,40\},\qquad n=5.
\]

Giả sử lần chọn tầng một dùng \(h_1(k)=k\bmod5\), ta có:

| Khóa | Chỉ số tầng một | Nhóm |
| ---: | ---: | --- |
| 10 | 0 | \(B_0\) |
| 17 | 2 | \(B_2\) |
| 24 | 4 | \(B_4\) |
| 31 | 1 | \(B_1\) |
| 40 | 0 | \(B_0\) |

Kích thước nhóm lần lượt là \((2,1,1,0,1)\). Tổng số ô phụ:

\[
Q=2^2+1^2+1^2+0^2+1^2=7\leq4n=20.
\]

Vì vậy, tầng một thỏa điều kiện. Nhóm 0 chứa hai khóa 10 và 40, nên cấp \(2^2=4\) ô. Thử \(h_{2,0}(k)=k\bmod4\):

\[
h_{2,0}(10)=2,\qquad h_{2,0}(40)=0.
\]

Không va chạm; có thể giữ hàm này cho nhóm 0. Các nhóm chỉ chứa một khóa dùng một ô.

```text
Tầng 1          Bảng phụ tầng 2
Nhóm 0  --->    [40, ∅, 10, ∅]     4 ô
Nhóm 1  --->    [31]               1 ô
Nhóm 2  --->    [17]               1 ô
Nhóm 3  --->    []                 0 ô
Nhóm 4  --->    [24]               1 ô
```

Tra cứu **40**: nhóm 0, ô phụ 0, thấy đúng khóa 40 → tìm thấy. Tra cứu **90**: nhóm 0, ô phụ 2, thấy khóa 10 → so sánh \(10\ne90\), kết luận không tìm thấy. Hai lần tra cứu đều sử dụng số bước hằng số.

Các phép chia lấy dư ở ví dụ chỉ để dễ tính tay. Trong FKS thực tế, các hàm được **chọn ngẫu nhiên từ một họ phổ dụng hợp lệ**, rồi kiểm tra điều kiện tầng một và điều kiện không va chạm tầng hai.

## 7. Chọn họ băm phổ dụng hợp lệ

Với khóa nguyên trong miền \(U=\{0,1,\ldots,p-1\}\), \(p\) là **số nguyên tố**, một họ băm phổ dụng kinh điển là:

\[
\boxed{h_{a,b}^{(m)}(k)=((ak+b)\bmod p)\bmod m}
\]

trong đó \(1\leq a<p\), \(0\leq b<p\), \(1\leq m\leq p\). Chọn \(a\) và \(b\) **đều, độc lập** trong các miền đã nêu. Họ này bảo đảm mỗi cặp khóa phân biệt cố định có xác suất va chạm không quá \(1/m\).

Trong FKS, dùng \(m=n\) cho tầng một và \(m=b_i^2\) cho tầng hai. Với khóa nguyên không âm, có thể chọn số nguyên tố:

\[
p>\max\bigl(\max S,n^2\bigr).
\]

Như vậy toàn bộ khóa đều nằm trong \(U\) và mọi bảng phụ có kích thước không quá \(p\). Đối với **chuỗi** hoặc những khóa không thuộc miền này, cần cách biểu diễn và họ băm phù hợp: nếu hai khóa phân biệt đã bị biến thành cùng giá trị modulo \(p\) trước bước băm, bảo đảm phổ dụng nêu trên không còn đúng cho cặp đó.

## 8. Cài đặt minh họa bằng Python

Đoạn mã tạo một **tập khóa tĩnh**: loại khóa trùng, thử hàm tầng một đến khi tổng bình phương nhóm không quá \(4n\), rồi tạo các bảng phụ không va chạm. Mỗi ô chứa khóa thật để kiểm tra cả những truy vấn không thuộc tập.

```python
import random


def is_prime(x: int) -> bool:
    if x < 2:
        return False
    d = 2
    while d * d <= x:
        if x % d == 0:
            return False
        d += 1
    return True


def hash_index(key, params, p, size):
    a, b = params
    return ((a * key + b) % p) % size


class StaticPerfectHashSet:
    def __init__(self, keys, p, seed=None):
        keys = list(keys)
        if any(type(key) is not int for key in keys):
            raise ValueError("Chỉ hỗ trợ khóa nguyên trong ví dụ")

        keys = list(dict.fromkeys(keys))  # Loại khóa trùng.
        n = len(keys)
        if type(p) is not int or not is_prime(p) or p <= n * n:
            raise ValueError("p phải nguyên tố và lớn hơn n^2")
        if any(not (0 <= key < p) for key in keys):
            raise ValueError("Mọi khóa phải thuộc [0, p-1]")

        rng = random.Random(seed)

        def random_params():
            return rng.randrange(1, p), rng.randrange(p)

        self.n = n
        self.p = p
        self.primary = None
        self.secondary = []
        self.tables = []
        if n == 0:
            return

        # Tầng 1: chỉ chấp nhận tổng bình phương nhóm <= 4n.
        while True:
            candidate = random_params()
            groups = [[] for _ in range(n)]
            for key in keys:
                i = hash_index(key, candidate, p, n)
                groups[i].append(key)
            if sum(len(group) ** 2 for group in groups) <= 4 * n:
                self.primary = candidate
                break

        # Tầng 2: mỗi nhóm có một bảng phụ không va chạm.
        for group in groups:
            count = len(group)
            if count == 0:
                self.secondary.append(None)
                self.tables.append([])
                continue
            if count == 1:
                self.secondary.append(None)
                self.tables.append([group[0]])
                continue

            size = count * count
            while True:
                params = random_params()
                slots = [None] * size
                for key in group:
                    j = hash_index(key, params, p, size)
                    if slots[j] is not None:
                        break  # Có va chạm, thử bộ tham số khác.
                    slots[j] = key
                else:
                    # Không gặp va chạm.
                    self.secondary.append(params)
                    self.tables.append(slots)
                    break

    def contains(self, key):
        if self.n == 0 or type(key) is not int or not (0 <= key < self.p):
            return False
        i = hash_index(key, self.primary, self.p, self.n)
        slots = self.tables[i]
        if not slots:
            return False
        if len(slots) == 1:
            return slots[0] == key
        j = hash_index(key, self.secondary[i], self.p, len(slots))
        return slots[j] == key


table = StaticPerfectHashSet([10, 17, 24, 31, 40], p=101, seed=42)
print(table.contains(40))  # True
print(table.contains(24))  # True
print(table.contains(90))  # False
print(sum(map(len, table.tables)) <= 4 * table.n)  # True
```

Tham số **seed** giúp tái hiện kết quả khi học; trong ứng dụng có thể dùng nguồn ngẫu nhiên phù hợp. Để xây dựng bảng ánh xạ **khóa–giá trị** thay vì chỉ tra cứu thành viên tập hợp, mỗi ô phụ có thể lưu cả khóa và giá trị, rồi kiểm tra khóa trước khi trả lại giá trị.

Việc kiểm tra số nguyên tố bằng phép chia thử trong mã chỉ phục vụ ví dụ; nó tốn thêm thời gian tùy vào \(p\). Phân tích \(O(n)\) cho xây dựng FKS dưới đây giả định **đã có sẵn số nguyên tố và họ băm hợp lệ**, và các phép toán băm là hằng số. Python dùng số nguyên có độ dài tùy ý nên không tràn khi nhân, nhưng phép toán trên số nguyên rất dài có chi phí phụ thuộc số bit.

## 9. Độ phức tạp và các giả thiết

| Hoạt động hoặc tài nguyên | Độ phức tạp | Lý do |
| --- | --- | --- |
| Xây dựng FKS | **\(O(n)\) theo kỳ vọng** | Mỗi tầng có số lần thử hằng số theo kỳ vọng; tổng số ô phụ bị chặn bởi \(4n\) |
| Tra cứu khóa có mặt | **\(O(1)\) trường hợp xấu nhất** | Tối đa hai phép băm, đọc một ô và so sánh khóa |
| Tra cứu khóa không có mặt | **\(O(1)\) trường hợp xấu nhất** | Đọc ô trống hoặc so sánh khóa thật để loại kết quả sai |
| Bộ nhớ | **\(O(n)\)** | \(n\) thông tin nhóm và tối đa \(4n\) ô phụ, cộng tham số |
| Chèn hoặc xóa khóa | Không được bảo đảm \(O(1)\) bởi thiết kế tĩnh | Có thể phải bố trí lại nhóm hoặc xây dựng lại bảng |

**Phân biệt hai kiểu bảo đảm:** Thời gian **xây dựng** là kỳ vọng theo các lần chọn ngẫu nhiên hàm băm. Một khi cấu trúc đã xây dựng xong, **mỗi lần tra cứu** có số phép truy cập cố định; đây là giới hạn trường hợp xấu nhất trên tập khóa đã lưu và với mô hình chi phí băm hằng số.

**Không bỏ điều kiện tầng một:** Một nhóm lớn có thể cần tới \(n^2\) ô nếu đặt toàn bộ khóa vào cùng nhóm. Chính điều kiện \(\sum b_i^2\leq4n\) giúp kiểm soát tổng bộ nhớ tuyến tính.

**Không nhầm băm hoàn hảo với băm mật mã:** FKS bảo đảm không va chạm giữa khóa cố định đã cho. Nó không tự động cung cấp khả năng chống một đối thủ biết tham số và chọn thêm các khóa thích ứng.

## 10. Lựa chọn cấu trúc phù hợp

| Cấu trúc | Khi nào hữu ích? | Đánh đổi |
| --- | --- | --- |
| **FKS cho tập tĩnh** | Khóa ổn định, tra cứu nhiều, cần \(O(1)\) trường hợp xấu nhất | Cần xây dựng trước; có các ô phụ trống |
| Bảng băm với chaining | Thường xuyên thêm/xóa khóa | Có thể duyệt chuỗi dài khi nhiều khóa cùng ô |
| Bảng băm với open addressing | Muốn lưu dữ liệu tập trung và xử lý dữ liệu động | Phụ thuộc hệ số tải và quy tắc thăm dò |
| Mảng sắp xếp + tìm kiếm nhị phân | Cần thứ tự khóa hoặc truy vấn theo khoảng | Tra cứu \(O(\log n)\) thay vì \(O(1)\) |
| Minimal perfect hash | Muốn ánh xạ đúng \(n\) khóa vào \(n\) chỉ số | Cần thuật toán xây dựng riêng và thường vẫn cần xác minh khóa ngoài tập |

Khi thiết kế, hãy đánh giá **tần suất cập nhật khóa**, **số lượt tra cứu so với số lần xây dựng**, **ngân sách bộ nhớ** và **yêu cầu độ trễ tối đa**. Với danh mục ID bất biến qua một phiên bản phát hành và được hỏi liên tục, băm hoàn hảo rất đáng cân nhắc. Với tập khóa thay đổi từng giây, bảng băm động thường thuận tiện hơn.

## 11. Sai lầm thường gặp

1. **Hiểu “hoàn hảo” là không có va chạm với mọi khóa ngoài tập.** Điều kiện chỉ áp dụng cho tập \(S\) đã xây dựng.
2. **Đồng nhất perfect hash với minimal perfect hash.** FKS có thể dùng nhiều ô hơn số khóa.
3. **Chọn một hàm khác ở mỗi lần tra cứu.** Hàm cần cố định để tra cứu đến đúng vị trí đã lưu.
4. **Không kiểm tra tổng bình phương kích thước nhóm.** Khi ấy bộ nhớ tầng hai có thể tăng bậc \(n^2\).
5. **Bỏ bước so sánh khóa thật.** Khóa ngoài tập vẫn có thể băm vào một ô đang chứa khóa khác.
6. **Thêm khóa mới rồi tiếp tục mặc định bảng hoàn hảo.** Khóa mới có thể phá vỡ bất biến và buộc phải xây dựng lại.

## 12. Tự kiểm tra

**Câu 1.** Vì sao FKS cho phép va chạm ở tầng một nhưng không cho phép ở tầng hai?

**Trả lời:** Tầng một chỉ phân khóa thành nhóm. Mỗi nhóm sau đó có một bảng phụ hoàn toàn không va chạm, nên địa chỉ gồm **chỉ số nhóm và chỉ số ô phụ** xác định duy nhất khóa đang lưu.

**Câu 2.** Với \(n=6\), các nhóm tầng một có kích thước \(3,1,1,1,0,0\). Tầng một có đạt điều kiện và cần bao nhiêu ô phụ?

**Trả lời:** \(\sum b_i^2=3^2+1+1+1=12\leq4\cdot6=24\); tầng một đạt điều kiện và có **12 ô phụ**, chưa kể thông tin quản lý nhóm.

**Câu 3.** Một nhóm có \(b=4\) khóa, kích thước bảng phụ \(b^2=16\). Giới hạn trên cho kỳ vọng số cặp va chạm trong một lần thử là bao nhiêu?

**Trả lời:**

\[
\mathbb E[C]\leq\frac{\binom 42}{16}=\frac6{16}=0{,}375.
\]

Do đó xác suất có va chạm không quá \(0{,}375\), còn xác suất **không có va chạm** ít nhất \(0{,}625\).

**Câu 4.** Bảng hoàn hảo trên 100 khóa được tra cứu bằng khóa mới không thuộc tập. Nếu ô được băm đến đang chứa dữ liệu, có thể kết luận khóa tồn tại không?

**Trả lời:** Không. Phải so sánh khóa đang lưu với khóa truy vấn; ô chứa khóa khác phải trả về **không tìm thấy**.

## 13. Ghi nhớ

**Băm hoàn hảo cho tập khóa tĩnh** dành thời gian xây dựng để tạo ánh xạ **không va chạm giữa các khóa đã biết**. Phương pháp FKS phân khóa vào các nhóm ở tầng một, tạo bảng phụ \(b_i^2\) ô không va chạm ở tầng hai, và chỉ chấp nhận hàm tầng một khi \(\sum b_i^2\leq4n\). Với họ hàm phổ dụng, cấu trúc có **thời gian xây dựng \(O(n)\) theo kỳ vọng**, **bộ nhớ \(O(n)\)** và **tra cứu \(O(1)\) trong trường hợp xấu nhất**, theo các giả thiết chi phí đã nêu.

Đây là lựa chọn thích hợp khi **tập khóa ổn định** và cần tra cứu nhanh, lặp lại nhiều lần. Khi tập khóa thay đổi thường xuyên, hãy tính cả chi phí xây dựng lại trước khi chọn nó cho ứng dụng.
