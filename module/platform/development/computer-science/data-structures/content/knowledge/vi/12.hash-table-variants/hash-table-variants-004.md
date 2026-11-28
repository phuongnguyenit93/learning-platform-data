# Băm cuckoo và chuỗi di chuyển khóa khi chèn

Trong bảng băm (*hash table*), nhiều khóa có thể được tính ra cùng một chỉ số. Với **separate chaining**, bảng lưu nhiều khóa trong một danh sách tại chỉ số đó; với **linear probing**, bảng đi tìm các ô kế tiếp. **Băm cuckoo** (*cuckoo hashing*) chọn một cách khác: cho mỗi khóa **một số ít vị trí ứng viên**, thường là **hai vị trí**. Khi chèn mà vị trí mong muốn đã có khóa, khóa mới chiếm ô đó và **đẩy khóa cũ sang vị trí ứng viên còn lại**. Sự thay chỗ có thể tiếp tục thành cả một chuỗi di chuyển.

Bài học thuộc chương **Biến thể bảng băm** trong module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu là hiểu đúng bất biến, quy trình chèn, trường hợp chèn thất bại, chi phí thời gian và bộ nhớ để quyết định khi nào cấu trúc này phù hợp với một bài toán từ điển hoặc tập hợp.

## 1. Ý tưởng: mỗi khóa có hai nhà

Hình dung mỗi khóa có **hai ô hợp lệ** trong bảng. Ta sẽ dùng hai mảng có cùng kích thước \(m\):

- \(T_1\) và hàm băm \(h_1(k)\) xác định địa chỉ \(T_1[h_1(k)]\).
- \(T_2\) và hàm băm \(h_2(k)\) xác định địa chỉ \(T_2[h_2(k)]\).

Một khóa \(k\) chỉ được lưu ở **một trong hai ô này**, không xuất hiện đồng thời ở cả hai. Mỗi ô chứa tối đa một khóa. Hai hàm băm cần được chọn/thiết kế để phân bố khóa đủ tốt; việc chỉ dùng hai hàm có công thức tùy ý không tự bảo đảm hiệu năng.

**Bất biến của bảng cuckoo hai mảng**:

\[
\forall k\in S,\quad
k\in T_1[h_1(k)]\ \lor\ k\in T_2[h_2(k)],
\]

trong đó \(S\) là tập khóa hiện đang lưu, và mỗi khóa xuất hiện **đúng một lần** ở hai vị trí ứng viên.

Vì vậy, để kiểm tra khóa \(k\) có trong bảng hay không, chỉ cần:

1. Kiểm tra khóa nằm tại \(T_1[h_1(k)]\) hay không.
2. Nếu không, kiểm tra \(T_2[h_2(k)]\).
3. Nếu cả hai đều khác khóa cần tìm, kết luận không tồn tại.

~~~text
                    ┌── T1[h1(k)]  (ứng viên thứ nhất)
Truy vấn khóa k ────┤
                    └── T2[h2(k)]  (ứng viên thứ hai)

       Tối đa hai vị trí cần kiểm tra
~~~

Không phải duyệt chuỗi hay tìm qua hàng loạt ô như ở một số cách xử lý va chạm khác. Trong mô hình hàm băm và so sánh khóa có chi phí hằng số, **tra cứu có thời gian \(O(1)\) trong trường hợp xấu nhất**, bất kể khóa có mặt hay không.

## 2. Thao tác tìm kiếm, chèn và xóa

### Tìm kiếm

Hàm tìm kiếm chỉ so sánh khóa thật ở hai ô ứng viên:

~~~text
CONTAINS(k):
    if T1[h1(k)] == k: return true
    if T2[h2(k)] == k: return true
    return false
~~~

Nếu bảng lưu cặp **khóa–giá trị**, mỗi ô cần chứa khóa để xác minh truy vấn và giá trị tương ứng để trả về. Chỉ nhìn thấy một ô không rỗng là chưa đủ, vì đó có thể là khóa khác.

### Chèn

Chèn bắt đầu bằng việc kiểm tra khóa đã tồn tại chưa, để tránh lưu trùng một khóa. Nếu khóa chưa có:

1. Thử đặt vào \(T_1[h_1(k)]\).
2. Nếu ô trống, chèn xong.
3. Nếu ô đã có khóa \(x\), đặt \(k\) vào ô đó và lấy \(x\) ra.
4. Đưa \(x\) tới vị trí còn lại \(T_2[h_2(x)]\). Nếu ô này cũng bận, tiếp tục đẩy khóa ở đó về \(T_1\), rồi lặp lại.
5. Kết thúc khi gặp ô trống, hoặc dừng có kiểm soát nếu đã di chuyển quá nhiều lần và cần **tái băm** (*rehash*) hoặc mở rộng bảng.

~~~mermaid
flowchart TD
    A[Chèn khóa mới k] --> B{Khóa đã tồn tại?}
    B -->|Có| C[Bỏ qua hoặc cập nhật giá trị]
    B -->|Không| D[Chọn ô ứng viên hiện tại]
    D --> E{Ô có trống?}
    E -->|Có| F[Đặt khóa vào ô, hoàn tất]
    E -->|Không| G[Đặt khóa đang cầm, lấy khóa cũ ra]
    G --> H{Vượt giới hạn di chuyển?}
    H -->|Chưa| I[Chuyển khóa bị đẩy sang bảng còn lại]
    I --> D
    H -->|Rồi| J[Khôi phục tập khóa và tái băm hoặc nới bảng]
~~~

Trong suốt một chuỗi di chuyển, có thể có một **khóa đang được cầm bên ngoài bảng**. Vì thế, nếu chèn thất bại giữa chừng, không được bỏ quên khóa này khi xây lại bảng.

### Xóa

Xóa đơn giản hơn chèn: kiểm tra hai ô ứng viên, rồi đưa ô chứa khóa cần xóa về trạng thái trống. Bảng cuckoo cơ bản **không cần tombstone** như một số biến thể open addressing; các khóa còn lại vẫn nằm ở vị trí hợp lệ của chúng.

## 3. Ví dụ từng bước: một lần chèn đẩy ba khóa

Để tính tay, xét hai bảng \(T_1\) và \(T_2\) có **\(m=5\)** ô mỗi bảng. Ta dùng các hàm minh họa:

\[
h_1(k)=k\bmod5,\qquad
h_2(k)=\left\lfloor\frac{k}{5}\right\rfloor\bmod5.
\]

Đây là công thức **chỉ dùng cho ví dụ**; hai hàm này có thể phân bố rất kém đối với những bộ khóa có quy luật. Một triển khai thực tế cần họ hàm băm và cách chọn tham số tốt hơn.

Giả sử các khóa **5**, **1** và **6** đã được bố trí hợp lệ:

| Bảng | Ô 0 | Ô 1 | Ô 2 | Ô 3 | Ô 4 |
| --- | --- | --- | --- | --- | --- |
| \(T_1\) | **5** | **1** | ∅ | ∅ | ∅ |
| \(T_2\) | ∅ | **6** | ∅ | ∅ | ∅ |

Vị trí đang lưu hợp lệ vì \(h_1(5)=0\), \(h_1(1)=1\) và \(h_2(6)=1\).

**Bây giờ chèn khóa 10**. Khóa này có các ứng viên \(T_1[0]\) và \(T_2[2]\).

| Bước | Khóa đang cầm | Ô cần tới | Chuyện xảy ra | Khóa bị đẩy ra |
| ---: | ---: | --- | --- | --- |
| 1 | 10 | \(T_1[h_1(10)]=T_1[0]\) | 10 thay khóa 5 | 5 |
| 2 | 5 | \(T_2[h_2(5)]=T_2[1]\) | 5 thay khóa 6 | 6 |
| 3 | 6 | \(T_1[h_1(6)]=T_1[1]\) | 6 thay khóa 1 | 1 |
| 4 | 1 | \(T_2[h_2(1)]=T_2[0]\) | Ô trống; đặt 1 vào | Không có |

~~~text
Chèn 10
  ↓
T1[0] :  10 thay 5
               ↓ khóa 5 sang ô còn lại
T2[1] :   5 thay 6
               ↓ khóa 6 sang ô còn lại
T1[1] :   6 thay 1
               ↓ khóa 1 sang ô còn lại
T2[0] :   1 vào ô trống → hoàn tất
~~~

Sau chèn:

| Bảng | Ô 0 | Ô 1 | Ô 2 | Ô 3 | Ô 4 |
| --- | --- | --- | --- | --- | --- |
| \(T_1\) | **10** | **6** | ∅ | ∅ | ∅ |
| \(T_2\) | **1** | **5** | ∅ | ∅ | ∅ |

Kiểm tra lại các bất biến: khóa 10 ở \(T_1[0]\), 6 ở \(T_1[1]\), 1 ở \(T_2[0]\), 5 ở \(T_2[1]\). **Mọi khóa vẫn xuất hiện đúng một lần và nằm ở một trong hai vị trí hợp lệ.**

Một thao tác chèn đã làm **ba khóa cũ phải đổi chỗ**. Đó là nét khác biệt quan trọng của cuckoo hashing: **đơn giản hóa tra cứu bằng cách chuyển công việc xử lý va chạm sang lúc chèn**.

## 4. Khi nào chuỗi di chuyển gặp vòng lặp?

Không phải lần chèn nào cũng tìm được ô trống. Nếu mỗi lần lấy khóa ra và đẩy sang vị trí còn lại lại quay về những ô đã xét, quá trình có thể **lặp vô hạn** nếu không có điều kiện dừng.

Ví dụ tiếp tục dùng \(m=5\) và hai hàm minh họa ở trên. Xét sáu khóa:

\[
S=\{0,1,5,6,10,11\}.
\]

Các vị trí ứng viên:

| Khóa | Vị trí trong \(T_1\) | Vị trí trong \(T_2\) |
| ---: | --- | --- |
| 0 | \(T_1[0]\) | \(T_2[0]\) |
| 1 | \(T_1[1]\) | \(T_2[0]\) |
| 5 | \(T_1[0]\) | \(T_2[1]\) |
| 6 | \(T_1[1]\) | \(T_2[1]\) |
| 10 | \(T_1[0]\) | \(T_2[2]\) |
| 11 | \(T_1[1]\) | \(T_2[2]\) |

Sáu khóa này có tổng cộng **chỉ năm ô ứng viên khác nhau**:

\[
\{T_1[0],T_1[1],T_2[0],T_2[1],T_2[2]\}.
\]

Theo nguyên lý Dirichlet (*pigeonhole principle*), **không thể đặt sáu khóa vào năm ô** mà vẫn giữ mỗi ô tối đa một khóa. Điều đáng chú ý là bảng thực tế có \(2m=10\) ô, chỉ mới chứa sáu khóa, tức có hệ số tải toàn cục \(6/10=0{,}6\). Một số ô khác vẫn trống nhưng các khóa này **không thể đến được** những ô đó thông qua hai hàm hiện tại.

Khi thành phần vị trí ứng viên bị quá tải như vậy, chuỗi đẩy khóa sẽ đi vòng mà không tạo ra chỗ cho tất cả khóa. Cần **chọn lại các hàm băm**, hoặc **tăng kích thước bảng và tái băm** để thay đổi các vị trí ứng viên.

### Góc nhìn đồ thị

Có thể mô hình hóa một cấu hình hai bảng bằng **đồ thị cuckoo**:

- Mỗi ô của \(T_1\) hoặc \(T_2\) là một **đỉnh**.
- Mỗi khóa là một **cạnh** nối hai đỉnh \(T_1[h_1(k)]\) và \(T_2[h_2(k)]\).
- Lưu khóa nghĩa là gán cạnh đó cho một trong hai đỉnh đầu mút; mỗi đỉnh nhận tối đa một cạnh.

~~~mermaid
flowchart LR
    A["T1[0]"] ---|"khóa 0"| X["T2[0]"]
    B["T1[1]"] ---|"khóa 1"| X
    A ---|"khóa 5"| Y["T2[1]"]
    B ---|"khóa 6"| Y
    A ---|"khóa 10"| Z["T2[2]"]
    B ---|"khóa 11"| Z
~~~

Điều kiện tồn tại một cách bố trí hợp lệ trong đồ thị hai lựa chọn này là **mỗi thành phần liên thông có số cạnh không vượt số đỉnh** (tức thành phần là một cây hoặc có nhiều nhất một chu trình độc lập). Nếu một thành phần có **nhiều cạnh hơn đỉnh**, không thể gán tất cả khóa của thành phần đó vào các ô ứng viên riêng biệt.

Một **chu trình đơn** trong đồ thị chưa chắc gây thất bại: một thành phần có đúng một chu trình vẫn có thể bố trí hợp lệ. Vấn đề là thành phần không còn đủ vị trí ứng viên để nhận hết khóa. Ngoài ra, cách đẩy khóa tuần tự có thể gặp đường đi dài; trong triển khai thực tế vẫn cần giới hạn bước và phương án phục hồi.

## 5. Phát hiện và xử lý chèn thất bại

Một cách triển khai an toàn là đặt giới hạn **max_kicks** cho số lần di chuyển trong một lần chèn. Nếu vượt giới hạn, thực hiện một trong các hướng:

1. **Rehash:** Chọn lại tham số cho \(h_1,h_2\), xây lại bảng từ toàn bộ khóa.
2. **Resize rồi rehash:** Mở rộng hai bảng, chọn hàm phù hợp với kích thước mới và chèn lại toàn bộ khóa.
3. **Stash nhỏ:** Trong một số biến thể, tạm giữ ít khóa khó bố trí ở vùng phụ; thao tác tìm kiếm phải kiểm tra cả stash nên không còn đúng quy tắc hai ô thuần túy.

Giới hạn di chuyển giúp tránh vòng lặp vô hạn; việc vượt ngưỡng **không tự chứng minh** rằng không tồn tại cách bố trí với hàm hiện tại. Đây là một tín hiệu để thử lại hoặc dùng quy trình xây dựng mạnh hơn.

**Không được làm mất khóa đang bị đẩy ra.** Nếu bảng đã bị thay đổi tạm thời và thử chèn thất bại, cần thu thập các khóa trong bảng **cộng khóa đang cầm bên ngoài** để xây dựng lại. Một phương án khác là xây trước cấu hình mới trên bản sao, rồi chỉ thay bảng chính sau khi thành công.

## 6. Hệ số tải và chi phí bộ nhớ

Với hai bảng mỗi bảng \(m\) ô, tổng số ô vật lý là \(2m\). Nếu có \(n\) khóa phân biệt, hệ số tải là:

\[
\boxed{\alpha=\frac{n}{2m}.}
\]

Băm cuckoo cổ điển với **hai lựa chọn ngẫu nhiên** có ngưỡng tải khả thi đặc trưng xấp xỉ **0,5** trong mô hình lý tưởng quy mô lớn; tiến gần ngưỡng này, việc tìm cách bố trí không va chạm trở nên khó hơn. Đây là kết quả dưới các giả thiết về hàm băm và phân bố khóa, **không phải cam kết phổ quát** cho mọi cài đặt.

| Hệ số tải | Ý nghĩa thực hành |
| --- | --- |
| Thấp | Nhiều ô trống, chuỗi đẩy thường ngắn hơn nhưng tốn bộ nhớ |
| Gần ngưỡng của biến thể đang dùng | Sử dụng bộ nhớ tốt hơn nhưng có nguy cơ chèn dài, rehash thường xuyên |
| Cao hơn ngưỡng khả thi điển hình của hai lựa chọn | Xác suất không thể bố trí toàn bộ khóa tăng mạnh |

Một cấu hình có thể chọn ngưỡng mở rộng bảo thủ, chẳng hạn **0,45**, để tránh đi sát ngưỡng lý tưởng. Ngưỡng thực tế cần đo theo phương pháp băm, kích thước bảng và dữ liệu. Các biến thể **nhiều hơn hai hàm băm** hoặc nhiều ô trên mỗi bucket có thể đạt ngưỡng tải khác và thay đổi số phép tra cứu.

## 7. Cài đặt Python minh họa có tái băm

Đoạn mã dưới đây xây một tập hợp cuckoo dùng **hai bảng**, với khóa nguyên trong miền \([0,p-1]\). Hai hàm băm có tham số được chọn độc lập để minh họa tính ngẫu nhiên. Khi một chuỗi đẩy khóa vượt giới hạn, chương trình **xây lại tất cả khóa trong các bảng và khóa vừa bị đẩy ra**, thử tham số khác và mở rộng nếu cần.

Đây là một cài đặt phục vụ học thuật. Họ hàm tuyến tính modulo nguyên tố có tính chất băm phổ dụng cho từng hàm, nhưng **chỉ tính phổ dụng từng đôi không đủ để tự suy ra các giới hạn xác suất chèn cuckoo tốt nhất**. Những phân tích chặt chẽ thường cần giả thiết mạnh hơn về hàm băm hoặc một họ hàm được chứng minh phù hợp.

~~~python
import random


class CuckooSet:
    P = 2**61 - 1  # Một số nguyên tố Mersenne.

    def __init__(self, m=5, seed=None):
        if type(m) is not int or m < 2:
            raise ValueError("m phải là số nguyên >= 2")
        self.rng = random.Random(seed)
        self.m = m
        self.t1 = [None] * m
        self.t2 = [None] * m
        self.n = 0
        self.p1 = self._new_params()
        self.p2 = self._new_params()

    def _new_params(self):
        a = self.rng.randrange(1, self.P)
        b = self.rng.randrange(self.P)
        return a, b

    def _check_key(self, key):
        if type(key) is not int or not (0 <= key < self.P):
            raise ValueError("Khóa phải là số nguyên trong [0, P-1]")

    def _index(self, key, params, m):
        a, b = params
        return ((a * key + b) % self.P) % m

    def contains(self, key):
        self._check_key(key)
        i = self._index(key, self.p1, self.m)
        j = self._index(key, self.p2, self.m)
        return self.t1[i] == key or self.t2[j] == key

    def _place(self, keys, m, p1, p2):
        """Thử xây bảng mới; trả None nếu một chuỗi bị giới hạn."""
        t1 = [None] * m
        t2 = [None] * m
        for key in keys:
            current = key
            side = 0
            for _ in range(2 * m):
                params = p1 if side == 0 else p2
                table = t1 if side == 0 else t2
                i = self._index(current, params, m)
                if table[i] is None:
                    table[i] = current
                    break
                table[i], current = current, table[i]
                side = 1 - side
            else:
                return None
        return t1, t2

    def _rebuild(self, keys, min_m):
        m = max(self.m, min_m)
        while True:
            if len(keys) > 0.9 * m:  # Tải = n/(2m) <= 0,45.
                m *= 2
                continue
            for _ in range(8):  # Thử 8 cặp hàm mới trước khi nới bảng.
                p1 = self._new_params()
                p2 = self._new_params()
                result = self._place(keys, m, p1, p2)
                if result is not None:
                    self.m, self.p1, self.p2 = m, p1, p2
                    self.t1, self.t2 = result
                    self.n = len(keys)
                    return
            m *= 2

    def add(self, key):
        self._check_key(key)
        if self.contains(key):
            return False  # Khóa đã tồn tại.

        if self.n + 1 > 0.9 * self.m:
            keys = [x for x in self.t1 + self.t2 if x is not None]
            self._rebuild(keys + [key], self.m * 2)
            return True

        current = key
        side = 0
        for _ in range(2 * self.m):
            params = self.p1 if side == 0 else self.p2
            table = self.t1 if side == 0 else self.t2
            i = self._index(current, params, self.m)
            if table[i] is None:
                table[i] = current
                self.n += 1
                return True
            table[i], current = current, table[i]
            side = 1 - side

        # Các ô đã bị đổi chỗ; current là khóa bị đẩy ra cuối cùng.
        # Phải giữ current khi tái xây dựng để không mất dữ liệu.
        keys = [x for x in self.t1 + self.t2 if x is not None]
        self._rebuild(keys + [current], self.m)
        return True

    def remove(self, key):
        self._check_key(key)
        i = self._index(key, self.p1, self.m)
        if self.t1[i] == key:
            self.t1[i] = None
        else:
            j = self._index(key, self.p2, self.m)
            if self.t2[j] != key:
                return False
            self.t2[j] = None
        self.n -= 1
        return True


table = CuckooSet(m=5, seed=42)
for key in (5, 1, 6, 10, 11, 20):
    table.add(key)

print(table.contains(10))  # True
print(table.contains(12))  # False
print(table.remove(6))     # True
print(table.contains(6))   # False
print(table.n)             # 5
~~~

**Đọc mã:** hàm **add** luôn kiểm tra trùng khóa, dùng hai vị trí ứng viên và đẩy khóa luân phiên giữa \(T_1\), \(T_2\). Trong lần chèn thất bại, biến **current** giữ khóa đang nằm ngoài bảng và được đưa vào danh sách tái xây dựng. Hàm **_rebuild** chỉ ghi đè các bảng chính **sau khi** tìm được cấu hình đặt được mọi khóa. Hàm **remove** xóa trực tiếp tại một trong hai vị trí ứng viên.

**Giới hạn của ví dụ:** việc dùng seed cố định tạo kết quả lặp lại phục vụ học tập, không hướng đến bảo vệ khỏi đối thủ chọn khóa. Chi phí rehash khi nới bảng hoặc chuỗi chèn thất bại có thể là \(O(n)\) tại thời điểm xảy ra. Để xử lý cặp khóa–giá trị, thay mỗi ô khóa bằng một bản ghi chứa cả khóa và giá trị; khi đẩy phải di chuyển **cả bản ghi**, nếu không sẽ làm sai ánh xạ.

## 8. Độ phức tạp: nhanh khi đọc, phức tạp hơn khi ghi

| Thao tác / tài nguyên | Độ phức tạp | Điều kiện |
| --- | --- | --- |
| **Tra cứu thành công** | \(O(1)\) trường hợp xấu nhất | Tối đa hai ô, hàm băm và so sánh khóa có chi phí hằng số |
| **Tra cứu thất bại** | \(O(1)\) trường hợp xấu nhất | Vẫn chỉ kiểm tra hai ô ứng viên |
| **Xóa khóa** | \(O(1)\) trường hợp xấu nhất | Xóa trực tiếp một trong hai ô, không tái cân bằng |
| **Chèn khóa** | Thường gần \(O(1)\), có thể dài; bảo đảm kỳ vọng phụ thuộc giả thiết | Chuỗi đẩy khóa, có thể rehash hoặc resize |
| **Chèn khi tái băm** | Có thể \(O(n)\) hoặc lớn hơn trong một thao tác | Phải chèn lại nhiều khóa; thử ngẫu nhiên có thể thất bại |
| **Bộ nhớ** | \(O(m)\) ô, tức \(2m\) ô cộng metadata | Nếu duy trì \(m=\Theta(n)\), tổng là \(O(n)\) |

Với **các mô hình băm ngẫu nhiên đủ mạnh** và hệ số tải được giữ cách xa ngưỡng, nhiều phân tích cuckoo hashing cổ điển cho chi phí chèn **\(O(1)\) theo kỳ vọng/phân bổ kỳ vọng** khi tính cả việc tái băm thích hợp. **Không có giới hạn \(O(1)\) trường hợp xấu nhất cho chèn trong biến thể cơ bản**: một chuỗi đẩy có thể dài và một lần tái băm có thể chèn lại toàn bộ dữ liệu.

Lưu ý: số bước chèn còn phụ thuộc cách xử lý vòng lặp, họ hàm băm, mô hình đối thủ, ngưỡng tải và chiến lược resize. Không thể dùng chỉ định nghĩa băm phổ dụng cho từng hàm để khẳng định thời gian chèn trung bình hằng số trong mọi hoàn cảnh.

### Chèn vào cùng một bảng duy nhất

Một biến thể khác lưu tất cả khóa trong **một mảng**, với hai chỉ số \(h_1(k)\) và \(h_2(k)\) trong cùng mảng. Nguyên tắc di chuyển vẫn tương tự, nhưng cần xác định chính xác vị trí còn lại của khóa bị đẩy và xử lý trường hợp hai hàm cho cùng chỉ số. Bài học này sử dụng **hai mảng riêng biệt** để làm rõ đường đi của khóa trong quá trình chèn.

## 9. Khi nào nên chọn cuckoo hashing?

| Cấu trúc | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| **Cuckoo hashing** | Tra cứu \(O(1)\) trường hợp xấu nhất với hai ô ứng viên, xóa đơn giản | Chèn có thể đẩy nhiều khóa, gặp vòng lặp và cần rehash |
| **Separate chaining** | Chèn/xóa dễ; linh hoạt khi hệ số tải cao hơn 1 | Chuỗi dài làm tra cứu chậm trong trường hợp xấu nhất |
| **Linear probing** | Dữ liệu nằm liên tục trong mảng, tận dụng cache tốt | Dễ xuất hiện cụm (*clustering*), xóa cần xử lý cẩn thận |
| **Băm hoàn hảo tĩnh** | Tra cứu không va chạm trên tập khóa đã biết | Thêm/xóa thường đòi hỏi xây dựng lại |
| **Cây tìm kiếm cân bằng** | Tra cứu và cập nhật \(O(\log n)\) trường hợp xấu nhất, hỗ trợ thứ tự | Nhiều con trỏ hoặc metadata; thao tác truy vấn khác với hash table |

**Cuckoo hashing phù hợp** khi số lượt tra cứu lớn, cần giới hạn rõ ràng cho số ô phải đọc, dữ liệu thay đổi nhưng tốc độ chèn không phải yêu cầu khắt khe nhất và hệ thống chấp nhận các lần rehash. Với workload ghi dày đặc, tải rất cao hoặc yêu cầu giới hạn tuyệt đối thời gian của từng lần chèn, cần cân nhắc một biến thể chuyên dụng hoặc cấu trúc khác.

## 10. Sai lầm thường gặp

1. **Nghĩ mỗi khóa xuất hiện ở cả hai bảng.** Không: hai vị trí là hai **ứng viên**; khóa chỉ được lưu **một lần**.
2. **Chèn vào ô bận mà bỏ khóa cũ.** Phải tiếp tục di chuyển khóa cũ đến vị trí còn lại; nếu không sẽ mất dữ liệu.
3. **Đẩy khóa sang bất kỳ ô trống nào.** Mỗi khóa chỉ hợp lệ tại các vị trí do hàm băm của chính nó chỉ ra.
4. **Không giới hạn chuỗi di chuyển.** Có thể lặp vô hạn khi thành phần ứng viên không đủ chỗ.
5. **Nghĩ còn ô trống toàn bảng thì chắc chắn chèn được.** Ô trống ngoài các vị trí ứng viên của thành phần liên quan không giúp đặt khóa.
6. **Rehash mà quên khóa đang cầm.** Sau chuỗi đẩy thất bại, khóa cuối đã bị lấy ra khỏi bảng phải được đưa vào tập khóa cần tái xây dựng.
7. **Kết luận hai hàm băm tùy ý luôn đủ tốt.** Tính chất độc lập/phân bố của hàm băm và hệ số tải quyết định khả năng tạo chuỗi ngắn.
8. **Dùng bảo đảm \(O(1)\) tra cứu để suy ra \(O(1)\) chèn tệ nhất.** Chèn là thao tác khác hẳn và có thể cần tái băm.

## 11. Tự kiểm tra

**Câu 1.** Trong ví dụ \(m=5\), vì sao chèn khóa 10 đẩy lần lượt 5, 6 và 1?

**Lời giải:** 10 chọn \(T_1[0]\), nơi đang có 5. Khóa 5 có vị trí còn lại \(T_2[h_2(5)]=T_2[1]\), đang chứa 6. Khóa 6 chuyển sang \(T_1[h_1(6)]=T_1[1]\), đang chứa 1. Khóa 1 chuyển sang \(T_2[h_2(1)]=T_2[0]\) còn trống, nên quá trình dừng.

**Câu 2.** Với hai bảng mỗi bảng 50 ô và \(n=40\) khóa, hệ số tải \(\alpha\) là bao nhiêu?

**Lời giải:**

\[
\alpha=\frac{n}{2m}=\frac{40}{2\cdot50}=0{,}4.
\]

**Câu 3.** Vì sao sáu khóa \(\{0,1,5,6,10,11\}\) không thể bố trí đồng thời theo hai hàm minh họa với \(m=5\)?

**Lời giải:** Chúng chỉ có năm ô ứng viên khác nhau: \(T_1[0]\), \(T_1[1]\), \(T_2[0]\), \(T_2[1]\), \(T_2[2]\). Sáu khóa không thể chiếm riêng sáu vị trí trong năm ô. Cần thay đổi hàm băm hoặc kích thước bảng.

**Câu 4.** Sau khi vượt giới hạn đẩy khóa, tại sao không được chỉ lấy các khóa còn nằm trong hai bảng để rehash?

**Lời giải:** Khóa bị đẩy ra cuối cùng đang nằm trong biến tạm, chưa có ô trong bảng. Nếu bỏ biến này, tái băm sẽ làm mất đúng một khóa. Phải đưa cả khóa đang cầm vào tập tái xây dựng.

**Câu 5.** Một cấu trúc cuckoo với hai bảng bảo đảm kiểm tra tối đa bao nhiêu vị trí khi tìm một khóa không tồn tại?

**Lời giải:** **Hai** vị trí, \(T_1[h_1(k)]\) và \(T_2[h_2(k)]\). Điều này đúng sau khi bảng đã được xây dựng và duy trì bất biến; không phụ thuộc số phần tử hiện có.

## 12. Ghi nhớ

**Cuckoo hashing** cho mỗi khóa hai vị trí ứng viên và giữ khóa ở **đúng một** vị trí trong số đó. Khi chèn vào ô đã có khóa, khóa mới **đẩy khóa cũ** đến vị trí còn lại, tạo **chuỗi di chuyển** cho đến khi có ô trống. Nếu chuỗi lặp hoặc quá dài, cần giới hạn bước, **rehash** hoặc **resize**, đồng thời giữ cả khóa đang bị đẩy ra để không mất dữ liệu.

Đổi lại cho độ phức tạp chèn khó dự đoán hơn, cấu trúc hai bảng cung cấp **tra cứu và xóa \(O(1)\) trường hợp xấu nhất** với các giả thiết về chi phí băm hằng số. Khi lựa chọn cấu trúc dữ liệu, hãy cân nhắc **độ trễ tra cứu, tần suất cập nhật, hệ số tải, bộ nhớ dự phòng và chi phí tái băm** cùng nhau.
