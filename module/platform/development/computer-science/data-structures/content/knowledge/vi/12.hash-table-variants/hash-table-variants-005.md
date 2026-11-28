# Băm Robin Hood và cân bằng khoảng cách thăm dò

Trong bảng băm dùng **địa chỉ mở** (*open addressing*), các phần tử được lưu trực tiếp vào những ô của một mảng. Khi hai khóa cùng có địa chỉ ban đầu, thuật toán phải thăm dò thêm các ô khác. Một cách thường gặp là **linear probing**: kiểm tra lần lượt các ô kế tiếp cho đến khi gặp ô trống hoặc khóa cần tìm.

**Robin Hood hashing** giữ cách thăm dò tuyến tính nhưng thay đổi quy tắc **chèn**: nếu một khóa mới đã phải đi xa vị trí ban đầu hơn khóa đang nằm trong ô hiện tại, khóa mới có quyền **đổi chỗ** với khóa cũ. Ý tưởng “lấy từ người giàu để giúp người nghèo” ở đây được hiểu theo **khoảng cách thăm dò**: khóa đã chịu nhiều lần thăm dò hơn được ưu tiên.

Bài học thuộc chương **Biến thể bảng băm** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Ta sẽ nghiên cứu bất biến lưu trữ, thao tác chèn–tìm–xóa, độ phức tạp thời gian và bộ nhớ, từ đó quyết định khi nào Robin Hood hashing phù hợp hơn linear probing thông thường hoặc các cấu trúc dữ liệu khác.

## 1. Ô gốc, chuỗi thăm dò và khoảng cách

Giả sử bảng có \(m\) ô, đánh số \(0,1,\ldots,m-1\). Với khóa \(k\), hàm băm xác định **ô gốc** (*home slot*):

\[
h(k)\in\{0,1,\ldots,m-1\}.
\]

Nếu dùng linear probing, dãy ô được kiểm tra là:

\[
h(k),\ (h(k)+1)\bmod m,\ (h(k)+2)\bmod m,\ldots
\]

Với một khóa \(k\) đang nằm ở ô \(i\), **khoảng cách thăm dò** hay **DIB** (*distance to initial bucket*) được tính:

\[
\boxed{\operatorname{DIB}(k,i)=(i-h(k)+m)\bmod m.}
\]

Ví dụ với \(m=8\), nếu khóa có ô gốc \(h(k)=6\) nhưng được lưu ở ô \(1\), dãy ô nó đã đi qua là \(6\rightarrow7\rightarrow0\rightarrow1\), nên **DIB = 3**. Phép modulo khiến định nghĩa hoạt động cả khi thăm dò vòng về đầu mảng.

| DIB | Nghĩa |
| ---: | --- |
| 0 | Khóa được lưu ngay ô gốc, không phải đi sang ô khác |
| 1 | Khóa nằm ở ô tiếp theo sau ô gốc |
| 2 | Khóa đã đi qua hai bước thăm dò |
| \(d\) | Khóa cách ô gốc \(d\) bước trên dãy thăm dò tuyến tính |

Trong cách triển khai lưu khóa trực tiếp, DIB có thể **được tính từ khóa và chỉ số ô** mà không cần một trường dữ liệu riêng. Một số triển khai tối ưu vẫn lưu DIB hoặc một phần thông tin băm để giảm phép tính lúc tra cứu.

### Bất biến quan trọng

Với mỗi khóa \(k\) đang ở ô \(i\), mọi ô từ \(h(k)\) tới ô **ngay trước \(i\)** trên dãy thăm dò đều phải có phần tử, trong mô hình Robin Hood **không dùng tombstone**. Nếu một ô trong đoạn đó thực sự trống thì khóa \(k\) đã có thể được đặt sớm hơn.

Chính tính liên tục này, kết hợp quy tắc đổi chỗ khi chèn, cho phép thuật toán **dừng tìm kiếm sớm** và **xóa bằng cách dịch lùi**.

## 2. Quy tắc “người nghèo đi trước” khi chèn

Giả sử ta đang cầm khóa \(x\), thăm dò tới ô \(i\), và ô này đang chứa khóa \(y\).

- Gọi \(d_x\) là số bước \(x\) đã đi từ ô gốc đến \(i\).
- Gọi \(d_y=\operatorname{DIB}(y,i)\) là khoảng cách hiện tại của \(y\).

Quy tắc Robin Hood:

\[
\boxed{\text{Nếu }d_x>d_y\text{ thì đặt }x\text{ vào ô }i\text{ và tiếp tục chèn }y.}
\]

Nếu \(d_x\leq d_y\), giữ nguyên \(y\), còn \(x\) tiếp tục sang ô tiếp theo. Khi hai DIB bằng nhau, quy tắc đơn giản này **không đổi chỗ**.

~~~mermaid
flowchart TD
    A[Bắt đầu chèn khóa x] --> B[Tính ô gốc và DIB của x]
    B --> C{Ô thăm dò có trống?}
    C -->|Có| D[Đặt x, hoàn tất]
    C -->|Không| E[So sánh x với khóa y ở ô]
    E --> F{DIB của x lớn hơn DIB của y?}
    F -->|Có| G[Đặt x vào ô, cầm y thay cho x]
    F -->|Không| H[Giữ y, tiếp tục cầm x]
    G --> I[Sang ô kế tiếp, cập nhật DIB]
    H --> I
    I --> C
~~~

Điều này giúp **phân phối lại độ dài đường thăm dò**. Khóa đã phải đi xa được quyền dừng, còn khóa đang ở gần ô gốc hơn tiếp tục tìm chỗ. Mục tiêu là tránh một số khóa có đường thăm dò quá dài trong khi nhiều khóa khác hầu như không phải di chuyển.

**Lưu ý:** “cân bằng” không có nghĩa mọi khóa có DIB bằng nhau, cũng không có bảo đảm tuyệt đối rằng DIB tối đa luôn nhỏ. Tính chất chính là quy tắc ưu tiên dựa trên **chênh lệch khoảng cách**.

## 3. Ví dụ chi tiết: đổi chỗ trong bảng tám ô

Chọn \(m=8\), hàm băm minh họa \(h(k)=k\bmod8\), và lần lượt chèn các khóa:

\[
0,\ 1,\ 8,\ 16,\ 4.
\]

### Bước 1: chèn 0 và 1

- Khóa \(0\) có \(h(0)=0\), vào ô 0 với DIB 0.
- Khóa \(1\) có \(h(1)=1\), vào ô 1 với DIB 0.

~~~text
Chỉ số:    0    1    2    3    4    5    6    7
Giá trị:  [0]  [1]  [·]  [·]  [·]  [·]  [·]  [·]
DIB:       0    0
~~~

### Bước 2: chèn khóa 8

Khóa \(8\) có ô gốc 0. Ô 0 chứa 0, cả hai khóa đều có DIB 0 nên 8 đi tiếp. Tại **ô 1**, khóa 8 đã có **DIB 1**, còn khóa 1 đang ở ô gốc với **DIB 0**. Vì \(1>0\), khóa 8 **đổi chỗ** với khóa 1.

Khóa 1 được đẩy sang ô 2 (DIB 1):

~~~text
Chỉ số:    0    1    2    3    4    5    6    7
Giá trị:  [0]  [8]  [1]  [·]  [·]  [·]  [·]  [·]
DIB:       0    1    1
~~~

### Bước 3: chèn khóa 16

Khóa \(16\) cũng có ô gốc 0:

| Ô đang xem | Khóa đang cầm | DIB của khóa đang cầm | Khóa trong ô | DIB trong ô | Hành động |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 16 | 0 | 0 | 0 | Không đổi; đi tiếp |
| 1 | 16 | 1 | 8 | 1 | Không đổi; đi tiếp |
| 2 | 16 | 2 | 1 | 1 | **Đổi 16 lấy 1** |
| 3 | 1 | 2 | Ô trống | — | Đặt 1, kết thúc |

Sau bước này, chèn khóa \(4\) thẳng vào ô gốc số 4. Bảng cuối:

| Chỉ số | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Khóa** | 0 | 8 | 16 | 1 | 4 | ∅ | ∅ | ∅ |
| **DIB** | 0 | 1 | 2 | 2 | 0 | — | — | — |

Hệ số tải của bảng là \(\alpha=n/m=5/8=0{,}625\).

### So sánh với linear probing không đổi chỗ

Với cùng thứ tự chèn, **linear probing thông thường** sẽ bố trí khóa như sau:

| Cách chèn | Ô 0 | Ô 1 | Ô 2 | Ô 3 | Ô 4 | DIB của năm khóa | DIB lớn nhất |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Linear probing thông thường | 0 | 1 | 8 | 16 | 4 | \(0,0,2,3,0\) | **3** |
| Robin Hood hashing | 0 | 8 | 16 | 1 | 4 | \(0,1,2,2,0\) | **2** |

Trong **chính ví dụ này**, tổng DIB của cả hai cách là 5, còn Robin Hood hashing giảm DIB lớn nhất từ 3 xuống 2 và phân bố khoảng cách đều hơn.

Nếu xem DIB của năm khóa như năm quan sát, phương sai trong ví dụ là:

\[
\begin{aligned}
\operatorname{Var}_{\mathrm{linear}}&=\frac{0^2+0^2+2^2+3^2+0^2}{5}-1^2=1{,}6,\\
\operatorname{Var}_{\mathrm{Robin\ Hood}}&=\frac{0^2+1^2+2^2+2^2+0^2}{5}-1^2=0{,}8.
\end{aligned}
\]

Con số minh họa tác dụng **giảm độ phân tán của khoảng cách thăm dò**, không phải định lý rằng mọi lần chèn hoặc mọi bộ dữ liệu đều có đúng mức cải thiện đó.

## 4. Tìm kiếm và điều kiện dừng sớm

Với khóa cần tìm \(k\), bắt đầu tại \(i=h(k)\) và tăng khoảng cách \(d=0,1,2,\ldots\):

1. Nếu ô đang xét **trống**, không tìm thấy khóa.
2. Nếu khóa trong ô **bằng \(k\)**, tìm thấy.
3. Nếu khóa đang có trong ô có **DIB nhỏ hơn \(d\)** của khóa đang tìm, có thể **kết luận không tìm thấy ngay**.
4. Nếu chưa gặp điều kiện dừng, kiểm tra ô kế tiếp.

Giải thích điều kiện thứ ba: nếu \(k\) thật sự đã được chèn vào một ô **sau** vị trí hiện tại, thì khi đi ngang vị trí đang xét với DIB \(d\), \(k\) đã phải đổi chỗ với khóa đang có DIB nhỏ hơn \(d\). Việc khóa đang xét vẫn còn trong ô cho thấy, với bất biến chèn Robin Hood được bảo toàn, \(k\) **không thể đang nằm xa hơn trên dãy thăm dò**.

Viết thành giả mã:

~~~text
FIND(k):
    i = h(k)
    d = 0
    while d < m:
        if T[i] is EMPTY:
            return NOT_FOUND
        if T[i].key == k:
            return FOUND
        if DIB(T[i].key, i) < d:
            return NOT_FOUND
        i = (i + 1) mod m
        d = d + 1
    return NOT_FOUND
~~~

**Ví dụ:** dùng bảng Robin Hood ở mục 3 và tìm khóa \(17\), có \(h(17)=1\).

| Ô | DIB của truy vấn 17 | Khóa đang lưu | DIB khóa đang lưu | Xử lý |
| ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 8 | 1 | Tiếp tục |
| 2 | 1 | 16 | 2 | Tiếp tục |
| 3 | 2 | 1 | 2 | Tiếp tục |
| 4 | 3 | 4 | 0 | **Dừng sớm**, vì \(0<3\) |

Chưa cần chạm tới ô trống số 5 đã biết khóa 17 không có trong bảng.

**Điều kiện áp dụng:** Dừng sớm dựa vào cách chèn Robin Hood nhất quán và cách xóa không làm hỏng các chuỗi thăm dò. Nếu chỉ gắn nhãn “Robin Hood” cho một bảng linear probing thông thường, hoặc xóa tùy ý tạo ra các lỗ trống, quy tắc trên có thể trả kết quả sai.

## 5. Xóa bằng dịch lùi (backward-shift deletion)

Một cách xóa đơn giản là đánh dấu ô đã xóa (*tombstone*). Tuy nhiên, tombstone làm việc tìm kiếm và chèn phức tạp hơn: ô đánh dấu không thể luôn được xem như ô trống thật, nếu không sẽ cắt đứt chuỗi tìm kiếm của những khóa nằm phía sau.

Với Robin Hood hashing tuyến tính, một lựa chọn thường dùng là **xóa bằng dịch lùi** (*backward-shift deletion*):

1. Tìm ô \(i\) chứa khóa cần xóa.
2. Xem ô kế tiếp \(j=(i+1)\bmod m\).
3. Nếu ô \(j\) có khóa với **DIB lớn hơn 0**, di chuyển khóa đó từ \(j\) về \(i\), làm DIB của nó giảm 1. Sau đó tiếp tục kiểm tra ô kế tiếp.
4. Dừng khi gặp **ô trống**, hoặc ô chứa khóa có **DIB = 0**. Đặt ô cuối cùng đang cần lấp thành trống.

Tại sao dừng ở khóa DIB 0? Vì khóa đó đã nằm đúng tại ô gốc: dịch lùi nó một bước sẽ đưa nó tới **ô không thuộc dãy thăm dò hợp lệ trước ô gốc**, có nguy cơ làm hỏng tìm kiếm.

### Ví dụ xóa khóa 8

Ban đầu:

~~~text
Chỉ số:    0    1    2     3    4    5    6    7
Khóa:     [0]  [8]  [16]  [1]  [4]  [·]  [·]  [·]
DIB:       0    1    2     2    0
~~~

Xóa khóa **8** ở ô 1:

- Khóa **16** tại ô 2 có DIB 2, nên dịch về ô 1, DIB trở thành 1.
- Khóa **1** tại ô 3 có DIB 2, nên dịch về ô 2, DIB trở thành 1.
- Khóa **4** tại ô 4 có DIB 0, nên dừng; để ô 3 trống.

~~~text
Chỉ số:    0     1    2    3    4    5    6    7
Khóa:     [0]  [16]  [1]  [·]  [4]  [·]  [·]  [·]
DIB:       0     1    1         0
~~~

Các khóa còn lại vẫn nằm trên đúng dãy thăm dò tính từ ô gốc. Việc tìm khóa **16** hoặc **1** vẫn thành công và phép dừng sớm vẫn hợp lệ.

**Độ phức tạp:** Xóa phải tìm khóa rồi có thể dịch nhiều phần tử, nên **không bảo đảm \(O(1)\) trong trường hợp xấu nhất**. Trong tình huống có cụm dài, số lần dịch có thể là \(O(n)\). Đổi lại, bảng không tích lũy tombstone.

## 6. Cài đặt Python minh họa đầy đủ

Đoạn mã sau dùng **số nguyên** làm khóa, lấy \(h(k)=k\bmod m\) để người học dễ theo dõi các ô gốc. Đây là **hàm minh họa**, có thể phân bố kém nếu khóa có quy luật; khi dùng trong ứng dụng thực tế cần hàm băm tốt và đánh giá đặc tính dữ liệu.

Ví dụ triển khai **tập hợp Robin Hood** với các thao tác chèn, tìm, xóa và mở rộng. Mỗi ô rỗng dùng giá trị **None**; chỉ số nguyên là khóa hợp lệ, nhờ đó None không thể trùng với khóa dữ liệu.

~~~python
class RobinHoodHashSet:
    def __init__(self, capacity=8):
        if type(capacity) is not int or capacity < 4:
            raise ValueError("capacity phải là số nguyên >= 4")
        self.slots = [None] * capacity
        self.size = 0

    def _check(self, key):
        if type(key) is not int:
            raise TypeError("Ví dụ chỉ chấp nhận khóa int")

    def _home(self, key):
        return key % len(self.slots)

    def _dib(self, key, index):
        return (index - self._home(key)) % len(self.slots)

    def _find_index(self, key):
        index = self._home(key)
        distance = 0
        capacity = len(self.slots)

        while distance < capacity:
            resident = self.slots[index]
            if resident is None:
                return None
            if resident == key:
                return index
            if self._dib(resident, index) < distance:
                return None   # Dừng sớm theo bất biến Robin Hood.
            index = (index + 1) % capacity
            distance += 1
        return None

    def contains(self, key):
        self._check(key)
        return self._find_index(key) is not None

    def _insert_new(self, key):
        """Chèn khóa chắc chắn chưa tồn tại; luôn có ô trống."""
        capacity = len(self.slots)
        index = self._home(key)
        distance = 0

        while distance < capacity:
            resident = self.slots[index]
            if resident is None:
                self.slots[index] = key
                return

            resident_distance = self._dib(resident, index)
            if distance > resident_distance:
                # Khóa đang cầm đi xa hơn: đổi chỗ.
                self.slots[index], key = key, resident
                distance = resident_distance

            index = (index + 1) % capacity
            distance += 1

        raise RuntimeError("Không tìm thấy ô trống")

    def _resize(self, new_capacity):
        old = self.slots
        self.slots = [None] * new_capacity
        for key in old:
            if key is not None:
                self._insert_new(key)
        # Không đổi self.size: số khóa vẫn giữ nguyên.

    def add(self, key):
        self._check(key)
        if self._find_index(key) is not None:
            return False  # Không chèn trùng một khóa.

        capacity = len(self.slots)
        if (self.size + 1) * 10 > capacity * 7:
            self._resize(capacity * 2)  # Giữ tải <= 0,7.

        self._insert_new(key)
        self.size += 1
        return True

    def remove(self, key):
        self._check(key)
        index = self._find_index(key)
        if index is None:
            return False

        capacity = len(self.slots)
        next_index = (index + 1) % capacity

        # Dịch lùi cho tới ô trống hoặc khóa nằm đúng ô gốc.
        while (self.slots[next_index] is not None
               and self._dib(self.slots[next_index], next_index) > 0):
            self.slots[index] = self.slots[next_index]
            index = next_index
            next_index = (next_index + 1) % capacity

        self.slots[index] = None
        self.size -= 1
        return True


table = RobinHoodHashSet(capacity=8)
for key in [0, 1, 8, 16, 4]:
    table.add(key)

print(table.slots)
# [0, 8, 16, 1, 4, None, None, None]

print(table.contains(16))  # True
print(table.contains(17))  # False (có thể dừng sớm tại ô 4)

table.remove(8)
print(table.slots)
# [0, 16, 1, None, 4, None, None, None]
print(table.contains(1))   # True
print(table.size)          # 4
~~~

**Những điểm cần đọc kỹ trong mã:**

- Chèn kiểm tra khóa đã tồn tại trước khi đổi chỗ, tránh lưu trùng khóa.
- Khi đổi chỗ, biến **key** nhận khóa cũ bị đẩy ra; biến **distance** được đặt lại bằng DIB của khóa cũ tại ô vừa rời, rồi tăng khi sang ô kế tiếp.
- Tìm kiếm có điều kiện dừng sớm nếu DIB của khóa tại ô nhỏ hơn khoảng cách mà khóa truy vấn đã đi.
- Xóa dùng dịch lùi, không tạo tombstone.
- Khi thêm phần tử khiến hệ số tải dự kiến vượt \(0{,}7\), bảng tăng kích thước và **chèn lại toàn bộ khóa** bằng quy tắc Robin Hood.

Mã chưa có hàm thu nhỏ bảng; đây là một lựa chọn đơn giản để tránh việc tăng/giảm dung lượng liên tục. Trong bảng băm ánh xạ **khóa–giá trị**, mỗi ô cần chứa cả khóa và giá trị; khi đổi chỗ hoặc dịch lùi phải di chuyển **toàn bộ bản ghi**, để giá trị không bị gắn nhầm khóa.

## 7. Phân tích độ phức tạp

Ký hiệu \(n\) là số khóa hiện có, \(m\) là số ô của mảng và \(\alpha=n/m\) là **hệ số tải** (*load factor*), với \(0\leq\alpha<1\).

| Thao tác | Chi phí điển hình với phân bố băm tốt, tải được khống chế | Trường hợp xấu nhất |
| --- | --- | --- |
| Tìm khóa tồn tại | Thường gần \(O(1)\), phụ thuộc phân bố khoảng cách | \(O(n)\) khi phải duyệt cụm dài |
| Tìm khóa không tồn tại | Thường gần \(O(1)\); có thể dừng sớm nhờ DIB | \(O(n)\) |
| Chèn không resize | Thường gần \(O(1)\), có thể đổi chỗ nhiều khóa | \(O(n)\) |
| Chèn gây resize | Rehash toàn bộ bảng, chi phí tuyến tính tại thời điểm đó | \(O(n)\) cho một lần mở rộng |
| Xóa bằng dịch lùi | Thường dịch ít ô khi tải vừa phải | \(O(n)\) |
| Bộ nhớ | \(O(m)\) ô, cộng metadata nếu có | \(O(n)\) nếu duy trì \(m=\Theta(n)\) |

Với các giả thiết về băm ngẫu nhiên/phân bố đủ tốt và hệ số tải được giữ dưới một ngưỡng phù hợp, Robin Hood hashing thường có **thời gian tra cứu và cập nhật kỳ vọng thấp**. Khi tính cả các lần tăng kích thước theo cấp số nhân, chi phí resize có thể được **phân bổ** cho nhiều thao tác chèn.

Tuy vậy, **không có bảo đảm \(O(1)\) trường hợp xấu nhất** cho một thao tác đơn lẻ của Robin Hood hashing cơ bản. Nếu nhiều khóa cùng ô gốc hoặc tạo cụm dài, thuật toán vẫn có thể thăm dò \(O(n)\) ô; quy tắc đổi chỗ giúp cân bằng khoảng cách chứ không loại bỏ sự hình thành cụm.

Một lưu ý khi so sánh độ phức tạp: **chi phí băm hoặc so sánh khóa dài** có thể không hằng số. Ví dụ sử dụng phép modulo trên số nguyên Python, còn ứng dụng dùng chuỗi dài cần tính cả thời gian tính hàm băm và so sánh chuỗi.

## 8. Cân bằng DIB không đồng nghĩa loại bỏ clustering

Hai hiện tượng cần phân biệt:

- **Primary clustering:** một vùng gồm nhiều ô liên tiếp đang có khóa, làm thao tác thăm dò có thể đi qua nhiều ô.
- **Phân bố DIB:** số bước mỗi khóa phải đi xa ô gốc trước khi được lưu; đây là đại lượng mà quy tắc Robin Hood trực tiếp tác động.

Robin Hood hashing **vẫn dùng linear probing**, nên các cụm dài vẫn có thể xuất hiện. Quy tắc đổi chỗ có xu hướng làm các khoảng cách thăm dò giữa các khóa trong cụm **ít chênh lệch hơn**, tránh một số khóa bị đẩy quá xa trong khi khóa khác đứng quá gần ô gốc.

Khi hệ số tải tăng gần 1, số ô trống giảm, các cụm thường dài hơn và chi phí di chuyển khi chèn/xóa có thể cao. Vì vậy, dù Robin Hood hashing có thể hoạt động ở mức tải đáng kể, ứng dụng vẫn phải **chọn ngưỡng tải**, theo dõi phân bố DIB và tăng kích thước khi cần.

Các tối ưu như lưu DIB, lưu một phần mã băm, dùng nhóm ô và truy cập bộ nhớ theo SIMD có thể thay đổi chi phí thực tế. Chúng là **kỹ thuật triển khai bổ sung**, không thay đổi nguyên tắc cốt lõi là so sánh khoảng cách và đổi chỗ khi chèn.

## 9. Quyết định sử dụng cấu trúc nào

| Cấu trúc | Ưu điểm | Điểm cần cân nhắc |
| --- | --- | --- |
| **Robin Hood hashing** | Phân bố đường thăm dò đều hơn trong nhiều tình huống; tìm kiếm có thể dừng sớm; dữ liệu nằm trực tiếp trong mảng | Chèn có thể đổi chỗ nhiều khóa; xóa dịch lùi tốn công; vẫn có cụm |
| **Linear probing truyền thống** | Cài đặt đơn giản, dữ liệu liên tiếp có tính cục bộ cache | Một số khóa có thể đi rất xa; tìm thất bại có thể quét cả cụm |
| **Separate chaining** | Chèn/xóa linh hoạt; không bắt buộc bảng có ô trống | Dùng thêm bộ nhớ danh sách/con trỏ; tìm có thể duyệt nhiều nút |
| **Cuckoo hashing** | Tra cứu tối đa một số ít ô ứng viên khi bất biến được giữ | Chèn có chuỗi đẩy khóa, đôi lúc cần rehash |
| **Cây tìm kiếm cân bằng** | Tra cứu/chèn/xóa \(O(\log n)\) trường hợp xấu nhất; hỗ trợ truy vấn có thứ tự | Tốn metadata, nhiều thao tác con trỏ |

Robin Hood hashing thường phù hợp với **tập hợp hoặc bảng ánh xạ trong bộ nhớ**, khi cần bố trí dữ liệu gọn, tra cứu nhanh và chấp nhận việc các thao tác cập nhật đôi lúc di chuyển nhiều ô. Nếu yêu cầu chặt chẽ về độ trễ tệ nhất của từng phép chèn hoặc cần duyệt khóa theo thứ tự, nên cân nhắc cấu trúc khác.

Trong thực tế, đừng chỉ so sánh trung bình số phép băm. Hãy đo **phần trăm phân vị độ trễ**, số lần đổi chỗ khi chèn, DIB tối đa, tốc độ xóa và lượng bộ nhớ tại hệ số tải của dữ liệu thật.

## 10. Những nhầm lẫn thường gặp

1. **“Khóa mới luôn lấy chỗ của khóa cũ.”** Sai: chỉ đổi chỗ nếu DIB của khóa mới **lớn hơn** DIB của khóa đang lưu; nếu không, tiếp tục thăm dò.
2. **“Robin Hood hashing không có va chạm.”** Sai: va chạm vẫn xảy ra, nhưng được giải quyết bằng thăm dò và đổi chỗ.
3. **“DIB là chỉ số mảng.”** Sai: DIB là **số bước từ ô gốc đến vị trí hiện tại**, tính theo modulo kích thước bảng.
4. **“Khi có ô trống trước khóa thì vẫn tìm thấy khóa đó ở phía sau.”** Nếu đúng bất biến của thăm dò tuyến tính và không có tombstone, khóa ở phía sau không thể hợp lệ khi đường từ ô gốc đến đó có lỗ trống.
5. **“Có thể dùng điều kiện dừng sớm sau khi xóa bằng cách đặt ô thành trống ngay.”** Sai: lỗ trống giữa một cụm có thể làm tìm kiếm trả sai; cần dịch lùi hoặc xử lý tombstone đúng.
6. **“Robin Hood hashing đảm bảo mọi tìm kiếm \(O(1)\) tệ nhất.”** Sai: đường thăm dò có thể dài đến \(O(n)\).
7. **“Mỗi lần chèn chỉ dịch tối đa một khóa.”** Sai: một lần chèn có thể kéo theo **nhiều lần đổi chỗ**.
8. **“Resize chỉ cần copy phần tử sang đúng chỉ số cũ.”** Sai: đổi kích thước bảng sẽ đổi ô gốc, nên phải **tính lại vị trí và chèn lại khóa**.

## 11. Tự kiểm tra

**Câu 1.** Bảng có \(m=8\), khóa \(k\) có ô gốc \(h(k)=7\) nhưng đang ở ô 2. DIB bằng bao nhiêu?

**Lời giải:**

\[
\operatorname{DIB}(k,2)=(2-7+8)\bmod8=3.
\]

Các bước thăm dò là \(7\rightarrow0\rightarrow1\rightarrow2\).

**Câu 2.** Khóa đang chèn có DIB 4, khóa đang ở ô có DIB 2. Theo Robin Hood hashing, nên làm gì?

**Lời giải:** Vì \(4>2\), khóa đang chèn **chiếm ô hiện tại**; khóa cũ được đưa vào biến tạm để tiếp tục thăm dò ô kế tiếp.

**Câu 3.** Trong bảng ở mục 3, tại ô 4, truy vấn khóa 17 đã có DIB 3 nhưng ô đang chứa khóa 4 với DIB 0. Có cần đi tới ô 5 không?

**Lời giải:** Không. Vì \(0<3\), có thể **dừng sớm** và kết luận 17 không tồn tại, miễn là bất biến Robin Hood và quy tắc xóa được duy trì.

**Câu 4.** Vì sao khi xóa khóa 8 trong ví dụ phải dời 16 và 1 về phía trước nhưng không dời khóa 4?

**Lời giải:** Khóa 16 và 1 có DIB lớn hơn 0, nên lùi một ô vẫn nằm trên chuỗi thăm dò hợp lệ. Khóa 4 có DIB 0, đang ở ô gốc; dời nó lùi một ô sẽ sai.

**Câu 5.** Bảng có 64 ô, lưu 40 khóa. Hệ số tải bằng bao nhiêu và trường hợp xấu nhất cho một lần chèn là bao nhiêu?

**Lời giải:** \(\alpha=40/64=0{,}625\). Dù tải chưa cao, trường hợp xấu nhất một lần chèn vẫn có thể cần \(O(n)\) bước khi các khóa tạo cụm dài hoặc khi phải resize; không thể bảo đảm hằng số chỉ từ hệ số tải.

## 12. Ghi nhớ

**Robin Hood hashing** là biến thể **open addressing dùng linear probing**. Khi chèn, thuật toán so sánh **khoảng cách thăm dò (DIB)** của khóa đang cầm với khóa đang nằm trong ô và **đổi chỗ nếu khóa đang cầm có DIB lớn hơn**. Quy tắc này giúp phân bố khoảng cách bớt lệch trong nhiều trường hợp.

Tra cứu có thể **dừng sớm** khi DIB của khóa đang nằm trong ô nhỏ hơn khoảng cách thăm dò hiện tại. Xóa bằng **backward-shift deletion** giữ bất biến mà không phải dùng tombstone. Dù tra cứu thường nhanh với hàm băm tốt và tải được kiểm soát, chèn, tìm và xóa vẫn có thể tốn **\(O(n)\) trong trường hợp xấu nhất**. Cân nhắc hiệu quả cân bằng DIB, chi phí di chuyển khóa, bộ nhớ và độ trễ cập nhật khi chọn cấu trúc cho từng bài toán.
