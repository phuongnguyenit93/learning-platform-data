# Băm hopscotch và vùng lân cận của một ô

**Hopscotch hashing** là biến thể bảng băm dùng **địa chỉ mở** (*open addressing*). Thay vì để một khóa phải thăm dò xa tùy ý khi ô gốc đã bị chiếm, hopscotch hashing cố giữ khóa **trong một vùng lân cận có kích thước giới hạn** quanh ô mà hàm băm chỉ ra. Khi không thể đặt ngay khóa mới, thuật toán di chuyển các khóa đang lưu để kéo một ô trống về gần vị trí gốc của khóa cần chèn.

Tên gọi *hopscotch* gợi đến trò chơi nhảy qua các ô: một ô trống được chuyển ngược dần về vùng cần thiết, còn những khóa bị dịch chuyển vẫn phải ở gần ô gốc của **chính chúng**.

Trong chương **Biến thể bảng băm** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, bài này làm rõ bất biến, tra cứu, chèn, xóa, bitmap vùng lân cận và độ phức tạp về thời gian, bộ nhớ. Từ đó, người học có thể đánh giá khi nào chọn hopscotch hashing thay vì linear probing, Robin Hood hashing hoặc separate chaining.

## 1. Vùng lân cận quanh ô gốc là gì?

Giả sử bảng băm có \(m\) ô, đánh số \(0,1,\ldots,m-1\), dùng hàm băm:

\[
h(k)\in\{0,1,\ldots,m-1\}.
\]

Chọn một tham số **\(H\)**, gọi là **kích thước vùng lân cận** (*neighborhood size*), với \(1\le H\le m\). Đối với ô gốc \(b\), vùng lân cận được xác định là:

\[
\boxed{N_H(b)=\{(b+d)\bmod m\mid 0\le d<H\}.}
\]

Như vậy, vùng lân cận chứa đúng **\(H\) ô liên tiếp theo chiều thăm dò**, **tính cả ô gốc**. Với \(m=12\), \(H=4\) và \(b=2\):

\[
N_4(2)=\{2,3,4,5\}.
\]

Nếu ô gốc ở gần cuối mảng, vùng lân cận có thể **vòng về đầu mảng**: với \(b=10\), \(N_4(10)=\{10,11,0,1\}\).

Cho một khóa \(k\) đang lưu tại ô \(i\), khoảng cách từ ô gốc đến vị trí hiện tại trên dãy thăm dò vòng là:

\[
d(k,i)=(i-h(k)+m)\bmod m.
\]

**Bất biến cốt lõi** của phiên bản một ô trên mỗi vị trí:

\[
\boxed{\forall k\in S,\quad 0\le d(k,\operatorname{pos}(k))<H.}
\]

Tức **mọi khóa luôn nằm trong vùng lân cận của ô gốc của chính khóa đó**. Đây là điểm khác biệt so với linear probing thông thường, nơi một khóa có thể bị dồn tới vị trí xa hơn khi có cụm dài.

### Bảng ví dụ

Giả sử \(m=12\), \(H=4\), \(h(k)=k\bmod12\). Các khóa sau có thể lưu hợp lệ:

| Khóa | Ô gốc \(h(k)\) | Ô đang lưu | Khoảng cách \(d\) | Hợp lệ? |
| ---: | ---: | ---: | ---: | --- |
| 14 | 2 | 2 | 0 | Có |
| 26 | 2 | 5 | 3 | Có |
| 17 | 5 | 6 | 1 | Có |
| 18 | 6 | 7 | 1 | Có |
| 28 | 4 | 8 | 4 | **Không**, vì \(d=H\) |

Khóa 28 phải nằm ở một trong bốn ô \(4,5,6,7\), **không thể** được lưu tại ô 8 trong cấu hình này. Lưu ý công thức \(k\bmod12\) chỉ để tính tay; việc chọn hàm băm tốt là điều quan trọng khi triển khai thực tế.

## 2. Bitmap theo ô gốc: biết khóa đang nằm ở đâu

Một triển khai hopscotch phổ biến dùng **bitmap** (*hop information*) cho từng ô gốc \(b\). Bitmap có \(H\) bit; bit thứ \(d\) bằng 1 nếu **có khóa với ô gốc \(b\)** được lưu tại ô \((b+d)\bmod m\).

Ký hiệu bitmap của ô gốc \(b\) là \(B[b]\):

\[
B[b]_d=
\begin{cases}
1&\text{nếu có khóa }k\text{ với }h(k)=b
\text{ tại }(b+d)\bmod m,\\
0&\text{nếu không.}
\end{cases}
\]

**Bitmap gắn với ô gốc**, chứ không phải một cờ đơn giản cho biết ô vật lý tương ứng đang rỗng hay đầy. Một ô vật lý có thể chứa khóa thuộc vùng lân cận của **ô gốc khác**.

Ví dụ \(m=12\), \(H=4\):

~~~text
Ô vật lý:     0    1   2    3    4    5    6    7    8    9   10   11
Khóa:         ·    ·  14    ·    ·   26    ·    ·    ·    ·    ·    ·
Ô gốc 2:                 |---------- vùng N4(2) ----------|
Độ lệch d:               0    1    2    3
Bitmap B[2]: bit 3..0 = 1001
                        (khóa 14 tại d=0, khóa 26 tại d=3)
~~~

Nếu dùng biểu diễn số nguyên, bitmap \(B[2]=2^0+2^3=9\). Thứ tự in chuỗi nhị phân là bit cao trước, còn bit \(d\) tương ứng độ lệch \(d\).

Khi thêm, di chuyển hoặc xóa khóa, phải cập nhật **bitmap của ô gốc khóa đó**. Nếu một khóa chuyển từ độ lệch \(d_{\mathrm{old}}\) sang \(d_{\mathrm{new}}\), cập nhật:

\[
B[h(k)]\gets
\bigl(B[h(k)]\ \&\ \sim(1\ll d_{\mathrm{old}})\bigr)
\ |\ (1\ll d_{\mathrm{new}}).
\]

Bitmap giúp tra cứu chỉ kiểm tra các vị trí **được đánh dấu** trong vùng lân cận. Nếu \(H\) cố định và các bit nằm trong một hoặc vài từ máy, số ô phải kiểm tra được chặn bởi \(H\).

## 3. Tìm kiếm: chỉ duyệt vùng lân cận

Để tìm khóa \(k\):

1. Tính ô gốc \(b=h(k)\).
2. Đọc bitmap \(B[b]\).
3. Với mỗi bit \(d\) đang bật, kiểm tra khóa trong ô \((b+d)\bmod m\).
4. Nếu gặp chính khóa \(k\), trả về **tìm thấy**; nếu hết bit đang bật, trả về **không tìm thấy**.

~~~text
FIND(k):
    b = h(k)
    for d in offsets_set_in_bitmap(B[b]):
        i = (b + d) mod m
        if T[i].key == k:
            return FOUND
    return NOT_FOUND
~~~

Phải **so sánh khóa thật**: một ô đang nằm trong vùng của \(b\) không đồng nghĩa nó đang chứa đúng khóa cần tìm.

Nếu \(H\) là một **hằng số cố định** (ví dụ 32, khi bitmap có thể nằm trong một từ 32 bit), tìm kiếm kiểm tra tối đa \(H\) ô nên tốn **\(O(1)\) trong trường hợp xấu nhất theo \(n\)**, với giả thiết tính băm, đọc metadata và so sánh khóa là hằng số. Nếu cho phép \(H\) tăng theo số khóa, giới hạn trực tiếp là **\(O(H)\)**, không được tự gọi là \(O(1)\).

Điểm này khác với **linear probing** thông thường: thuật toán tuyến tính có thể phải đi hết một cụm dài khi tìm khóa không tồn tại, còn hopscotch giữ khóa trong vùng dài tối đa \(H\).

## 4. Chèn: tìm ô trống rồi kéo ô trống về gần gốc

Giả sử cần chèn khóa mới \(x\), có ô gốc \(b=h(x)\).

**Giai đoạn A – tìm chỗ:** Kiểm tra trùng khóa. Nếu chưa tồn tại, tìm một ô trống theo chiều thăm dò bắt đầu từ \(b\). Nếu ô trống nằm tại \(b+d\) với \(d<H\), đặt khóa vào đó và bật bit \(d\) của \(B[b]\).

**Giai đoạn B – đưa ô trống về gần:** Nếu ô trống đầu tiên ở độ lệch \(d\ge H\), chưa thể đặt \(x\) ở đó. Ta thử tìm một khóa \(y\) ở một trong tối đa \(H-1\) ô ngay **trước ô trống** sao cho:

- Ô hiện tại của \(y\) nằm trước ô trống trên dãy thăm dò.
- Nếu chuyển \(y\) sang ô trống, ô mới vẫn **thuộc vùng lân cận \(N_H(h(y))\)**.

Khi tìm được \(y\), chuyển \(y\) tới ô trống và **cập nhật bitmap của \(h(y)\)**. Vị trí cũ của \(y\) trở thành **ô trống mới**, gần ô gốc của \(x\) hơn. Lặp lại cho đến khi ô trống mới nằm trong \(N_H(b)\); sau đó đặt \(x\) vào và cập nhật \(B[b]\).

~~~mermaid
flowchart TD
    A[Chèn khóa mới x] --> B{Khóa đã tồn tại?}
    B -->|Có| C[Giữ nguyên hoặc cập nhật giá trị]
    B -->|Không| D[Tìm ô trống từ h(x) theo chiều thăm dò]
    D --> E{Có ô trống?}
    E -->|Không| F[Rehash hoặc mở rộng]
    E -->|Có| G{Ô trống nằm trong N_H của x?}
    G -->|Có| H[Đặt x và bật bit ở bitmap h(x)]
    G -->|Không| I[Tìm khóa y trước ô trống có thể chuyển hợp lệ]
    I --> J{Tìm được y?}
    J -->|Có| K[Chuyển y, cập nhật bitmap h(y)]
    K --> G
    J -->|Không| F
~~~

**Quy tắc quyết định có được di chuyển không:**

\[
\boxed{d\bigl(y,\mathrm{empty}\bigr)<H}
\]

trong đó \(d(y,\mathrm{empty})\) là khoảng cách vòng từ ô gốc \(h(y)\) tới ô trống hiện tại. Không được chỉ xét khoảng cách từ ô gốc của **khóa mới \(x\)**, vì mỗi khóa \(y\) phải giữ bất biến theo ô gốc riêng.

Một hiện thực đơn giản thử các ứng viên từ ô **gần ô trống nhất** lùi dần; các hiện thực khác có thể dùng bitmap để tìm khóa di chuyển hợp lệ nhanh hơn.

## 5. Ví dụ cụ thể: chuỗi dịch chuyển hai lần

Xét bảng có \(m=12\), \(H=4\), \(h(k)=k\bmod12\). Ban đầu chèn lần lượt năm khóa **14, 27, 16, 17, 18**; tất cả đều ở ô gốc:

| Ô | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Khóa ban đầu | ∅ | ∅ | **14** | **27** | **16** | **17** | **18** | ∅ | ∅ | ∅ | ∅ | ∅ |

Ta cần chèn **26**, có \(h(26)=2\) và vùng lân cận:

\[
N_4(2)=\{2,3,4,5\}.
\]

Các ô 2,3,4,5 đều bận. Ô trống đầu tiên là **ô 7**, cách ô gốc 2 **năm bước**; chưa thể đặt khóa 26 vào ô 7.

| Bước | Ô trống hiện tại | Chọn khóa di chuyển | Điều kiện hợp lệ | Ô trống mới |
| ---: | ---: | --- | --- | ---: |
| 1 | 7 | Khóa **18** ở ô 6 → ô 7 | \(h(18)=6\), khoảng cách tới ô 7 là **1 < 4** | 6 |
| 2 | 6 | Khóa **17** ở ô 5 → ô 6 | \(h(17)=5\), khoảng cách tới ô 6 là **1 < 4** | 5 |
| 3 | 5 | Đặt khóa **26** tại ô 5 | \(h(26)=2\), khoảng cách tới ô 5 là **3 < 4** | Hoàn tất |

~~~text
Trước chèn:
ô:        2     3     4     5     6     7
khóa:    [14]  [27]  [16]  [17]  [18]  [·]

Nhảy 1:                         18 → ô 7
ô:        2     3     4     5     6     7
khóa:    [14]  [27]  [16]  [17]  [·]   [18]

Nhảy 2:                   17 → ô 6
ô:        2     3     4     5     6     7
khóa:    [14]  [27]  [16]  [·]   [17]  [18]

Chèn 26:                 26 → ô 5
ô:        2     3     4     5     6     7
khóa:    [14]  [27]  [16]  [26]  [17]  [18]
~~~

Sau khi chèn, các bitmap bị ảnh hưởng:

| Ô gốc | Trước | Sau | Giải thích |
| ---: | --- | --- | --- |
| 2 | **0001** | **1001** | 14 ở độ lệch 0, 26 ở độ lệch 3 |
| 5 | **0001** | **0010** | 17 chuyển từ lệch 0 sang lệch 1 |
| 6 | **0001** | **0010** | 18 chuyển từ lệch 0 sang lệch 1 |
| 3 và 4 | **0001** | **0001** | Các khóa 27 và 16 không đổi |

Mọi khóa trong bảng cuối vẫn có khoảng cách **nhỏ hơn \(H=4\)** so với ô gốc của nó. Có sáu khóa trên 12 ô, nên hệ số tải là \(\alpha=6/12=0{,}5\).

**Chi tiết dễ sai:** Các khóa **17, 18** vẫn phải được tìm thông qua bitmap của **ô gốc 5 và 6**, ngay cả khi hiện được lưu ở ô 6 và 7. Nếu di chuyển ô mà quên cập nhật bitmap, tìm kiếm có thể báo **không tìm thấy** dù khóa còn trong bảng.

## 6. Khi nào không thể đưa ô trống vào vùng lân cận?

Sự tồn tại của ô trống ở nơi khác trong mảng **không bảo đảm** khóa mới có thể chèn thành công. Thuật toán có thể tìm ô trống khá xa, nhưng không tìm được chuỗi di chuyển mà mọi khóa trung gian đều vẫn nằm trong vùng hợp lệ.

Ví dụ với \(H=4\), nếu **năm khóa phân biệt** có cùng ô gốc \(b\), cả năm đều buộc phải nằm trong **chỉ bốn ô** thuộc \(N_4(b)\). Điều này không thể thực hiện, dù toàn bảng còn rất nhiều ô trống. Theo nguyên lý Dirichlet, nhiều hơn \(H\) khóa có cùng ô gốc **không thể** cùng tồn tại trong phiên bản một khóa trên mỗi ô.

Cần phân biệt hai tình huống:

1. **Bất khả thi với hàm băm hiện tại:** Không thể giữ mọi khóa trong vùng \(H\) cho cách phân bố ô gốc đang dùng. Phải thay hàm băm, thay tham số, tăng \(H\), hoặc điều chỉnh kích thước bảng.
2. **Thuật toán tìm chỗ chưa tìm được lời giải:** Một chiến lược di chuyển tham lam cụ thể có thể không tìm được đường, dù một cách sắp xếp khác có thể phù hợp. Khi gặp bế tắc, vẫn cần chính sách thử lại có kiểm soát.

Một triển khai thực tế thường dùng **rehash** (chọn lại hàm/seed rồi chèn lại toàn bộ dữ liệu) hoặc **resize** (mở rộng bảng và xây lại). Nếu resize nhưng tiếp tục dùng một hàm băm kém, các khóa có quy luật vẫn có thể bị dồn vào cùng ô gốc. Vì vậy, **chỉ tăng số ô chưa chắc giải quyết được vấn đề**.

## 7. Cài đặt Python minh họa

Ví dụ dưới đây dùng một mảng, bitmap theo ô gốc và cách kéo ô trống ngược về vùng \(H\). Mã hỗ trợ **thêm, kiểm tra thành viên và xóa**, xử lý vòng mảng bằng modulo. Để dễ theo dõi bằng tay, nó dùng \(h(k)=k\bmod m\) cho khóa nguyên; đây **không phải hàm băm khuyến nghị** đối với dữ liệu có quy luật hoặc đầu vào đối kháng.

Mục tiêu của đoạn mã là minh họa chính xác **bất biến và cập nhật bitmap**. Nếu không tìm được cách di chuyển hợp lệ, thao tác báo lỗi để người gọi thực hiện rehash/resize; mã chưa tự động chọn hàm mới.

~~~python
class HopscotchSet:
    def __init__(self, capacity=12, neighborhood=4):
        if type(capacity) is not int or capacity < 2:
            raise ValueError("capacity phải là số nguyên >= 2")
        if (type(neighborhood) is not int
                or not (1 <= neighborhood <= capacity)):
            raise ValueError("Cần 1 <= neighborhood <= capacity")

        self.slots = [None] * capacity
        self.hop = [0] * capacity  # H bit cho mỗi ô gốc.
        self.H = neighborhood
        self.size = 0

    def _home(self, key):
        if type(key) is not int:
            raise TypeError("Ví dụ chỉ hỗ trợ khóa nguyên int")
        return key % len(self.slots)

    def _distance(self, home, index):
        return (index - home) % len(self.slots)

    def contains(self, key):
        home = self._home(key)
        bits = self.hop[home]
        capacity = len(self.slots)

        while bits:
            lowest = bits & -bits
            offset = lowest.bit_length() - 1
            i = (home + offset) % capacity
            if self.slots[i] == key:
                return True
            bits &= bits - 1  # Xóa bit thấp nhất để xét bit tiếp.
        return False

    def add(self, key):
        home = self._home(key)
        if self.contains(key):
            return False  # Không tạo khóa trùng.

        capacity = len(self.slots)
        # Tìm ô trống đầu tiên theo chiều thăm dò từ home.
        free_offset = 0
        while (free_offset < capacity
               and self.slots[(home + free_offset) % capacity] is not None):
            free_offset += 1
        if free_offset == capacity:
            raise RuntimeError("Bảng đầy: cần mở rộng và tái băm")

        # Kéo ô trống về gần home tới khi free_offset < H.
        while free_offset >= self.H:
            free_index = (home + free_offset) % capacity
            moved = False

            # Thử khóa ở các ô ngay trước ô trống, gần nhất trước.
            max_back = min(self.H - 1, free_offset)
            for back in range(1, max_back + 1):
                candidate_offset = free_offset - back
                candidate_index = (home + candidate_offset) % capacity
                resident = self.slots[candidate_index]
                if resident is None:
                    continue

                resident_home = self._home(resident)
                new_d = self._distance(resident_home, free_index)
                if new_d >= self.H:
                    continue  # Không được đẩy ra ngoài vùng của resident.

                old_d = self._distance(resident_home, candidate_index)
                self.slots[free_index] = resident
                self.slots[candidate_index] = None

                self.hop[resident_home] &= ~(1 << old_d)
                self.hop[resident_home] |= 1 << new_d
                free_offset = candidate_offset
                moved = True
                break

            if not moved:
                # Các khóa cũ vẫn hợp lệ dù vài ô đã được di chuyển.
                # Khóa mới chưa được thêm; người gọi cần rehash/resize.
                raise RuntimeError("Không kéo được ô trống vào vùng H")

        i = (home + free_offset) % capacity
        self.slots[i] = key
        self.hop[home] |= 1 << free_offset
        self.size += 1
        return True

    def remove(self, key):
        home = self._home(key)
        bits = self.hop[home]
        capacity = len(self.slots)

        while bits:
            lowest = bits & -bits
            offset = lowest.bit_length() - 1
            i = (home + offset) % capacity
            if self.slots[i] == key:
                self.slots[i] = None
                self.hop[home] &= ~(1 << offset)
                self.size -= 1
                return True
            bits &= bits - 1
        return False


table = HopscotchSet(capacity=12, neighborhood=4)
for key in [14, 27, 16, 17, 18, 26]:
    table.add(key)

print(table.slots[2:8])
# [14, 27, 16, 26, 17, 18]

print(format(table.hop[2], "04b"))  # 1001
print(format(table.hop[5], "04b"))  # 0010
print(table.contains(26))          # True
print(table.contains(38))          # False

table.remove(17)
print(table.contains(17))          # False
print(table.size)                  # 5
~~~

### Vì sao việc xóa ở đây đơn giản?

Khi xóa khóa \(k\), đoạn mã chỉ xóa ô vật lý chứa \(k\) và **tắt bit tương ứng của \(B[h(k)]\)**. Không cần dịch lùi toàn bộ cụm như biến thể Robin Hood dùng backward-shift deletion, bởi tìm kiếm hopscotch dựa vào **bitmap của ô gốc**, không dựa vào việc liên tục quét đến ô trống đầu tiên.

Tuy vậy, việc xóa có thể tạo lỗ trống xen giữa các khóa khác, còn lần chèn tiếp theo sẽ tự tìm và dùng ô trống phù hợp. Đây là điểm cần chú ý khi tự triển khai: không được dùng lẫn logic tìm kiếm dừng ở ô trống của linear probing với logic tìm kiếm theo bitmap của hopscotch.

**Giới hạn của mã:** Không có resize tự động và không có đồng bộ đa luồng. Nếu chèn báo lỗi, các khóa đã lưu **vẫn được giữ**, dù một vài khóa có thể đã được dời chỗ hợp lệ; khóa mới chưa được thêm. Một phiên bản sản xuất thường dùng chiến lược **rehash trên một bảng mới**, chỉ thay thế bảng hiện hành sau khi đã xây dựng thành công và xác minh đầy đủ các bitmap.

## 8. Phân tích độ phức tạp và bộ nhớ

Gọi \(n\) là số khóa đang lưu, \(m\) là số ô bảng, \(H\) là kích thước vùng lân cận, hệ số tải:

\[
\alpha=\frac{n}{m},\quad 0\le\alpha\le1.
\]

| Hoạt động | Chi phí / bảo đảm | Giải thích |
| --- | --- | --- |
| **Tìm kiếm** | \(O(H)\), thành \(O(1)\) nếu \(H\) cố định | Chỉ xem những vị trí đánh dấu trong bitmap của ô gốc |
| **Xóa** | \(O(H)\), thành \(O(1)\) nếu \(H\) cố định | Tìm khóa qua bitmap, xóa ô và tắt bit |
| **Chèn** | Thường nhanh khi phân bố khóa tốt; có thể \(O(mH)\) trong một lần thử tham lam | Quét tìm ô trống rồi thử di chuyển, tối đa \(H-1\) ứng viên cho mỗi lần kéo |
| **Rehash/resize** | Có thể cần bố trí lại \(O(n)\) khóa hoặc nhiều lần thử | Xảy ra khi tải cao hoặc không tìm được cách đặt phù hợp |
| **Ô dữ liệu** | \(O(m)\) | Một mảng chứa tối đa một bản ghi trong mỗi ô |
| **Hop bitmap** | \(mH\) bit (xấp xỉ), hoặc \(O(m)\) từ máy khi \(H\) cố định, vừa một từ | Mỗi ô gốc giữ \(H\) bit thông tin vị trí |

Với **\(H\) cố định** và \(m=\Theta(n)\), tổng bộ nhớ là **\(O(n)\)** theo mô hình mỗi bitmap là một từ máy và một ô chứa một bản ghi. Nếu \(H\) tăng theo \(n\), phải tính chi phí metadata là \(O(mH)\) **bit**, không tự suy ra hằng số.

**Phân biệt giới hạn xấu nhất và hiệu năng trung bình:** Hopscotch có một lợi thế rõ ràng cho **tra cứu**, vì vùng kiểm tra được giới hạn. Chèn thì có thể phải đi tìm ô trống xa rồi di chuyển nhiều khóa hoặc tái băm. Chỉ từ bất biến vùng lân cận **không thể khẳng định mọi lần chèn có giới hạn \(O(1)\) trong trường hợp xấu nhất**.

Trong thực tế, các phân tích kỳ vọng hoặc số đo hiệu năng còn phụ thuộc họ hàm băm, độ dài vùng \(H\), hệ số tải và chính sách thử lại. Với khóa rất dài, thời gian băm và so sánh khóa cũng cần tính thêm.

## 9. Hệ số tải, kích thước H và đánh đổi

Chọn \(H\) ảnh hưởng trực tiếp đến tốc độ tra cứu, khả năng chèn và bộ nhớ metadata:

| Tham số | Khi nhỏ | Khi lớn |
| --- | --- | --- |
| \(H\) | Ít ô cần tra cứu, bitmap gọn; khó chèn nếu nhiều khóa có chung vùng | Nhiều cách bố trí, nhưng mỗi truy vấn có thể phải xét thêm vị trí và bitmap lớn hơn |
| Hệ số tải \(\alpha\) | Nhiều ô trống, di chuyển thường dễ hơn; dùng bộ nhớ dư | Khó tìm ô trống gần, dễ phải di chuyển hoặc rehash |
| Số ô \(m\) | Tiết kiệm ô dữ liệu; dễ quá tải hoặc tắc vùng lân cận | Phân bố rộng hơn, nhưng tốn bộ nhớ |

Một cấu hình có thể dùng **\(H=32\)** với bitmap 32 bit hoặc \(H=64\) với bitmap 64 bit. Đó là **ví dụ cấu hình**, không phải khuyến nghị bất biến cho mọi máy và workload. Ngay cả với \(H\) đủ lớn, một hàm băm quá kém vẫn có thể làm nhiều khóa rơi vào cùng ô gốc và gây chèn thất bại.

Hãy đo số bước tìm ô trống, số lần di chuyển, tốc độ tra cứu thành công/thất bại, số lần rehash và bộ nhớ metadata trên **dữ liệu thật** trước khi quyết định ngưỡng tải.

## 10. So sánh với các biến thể bảng băm khác

| Cấu trúc | Cách xử lý va chạm | Tính chất cần ghi nhớ |
| --- | --- | --- |
| **Linear probing** | Đi lần lượt đến ô trống tiếp theo | Cài đặt đơn giản, nhưng tìm kiếm có thể phải quét cụm dài |
| **Robin Hood hashing** | Đổi chỗ khi khóa đang cầm có khoảng cách thăm dò lớn hơn khóa tại ô | Cân bằng khoảng cách thăm dò; không bắt buộc khóa ở trong vùng \(H\) cố định |
| **Hopscotch hashing** | Giữ mọi khóa trong vùng \(H\) quanh ô gốc, kéo ô trống bằng cách chuyển các khóa khác | Truy vấn bị chặn bởi độ rộng vùng lân cận; cần metadata và logic di chuyển đúng |
| **Cuckoo hashing** | Mỗi khóa có vài vị trí ứng viên; đẩy khóa cũ sang vị trí khác khi chèn | Tra cứu số ô cố định; chèn có thể tạo chuỗi và phải rehash |
| **Separate chaining** | Mỗi ô trỏ tới danh sách/cấu trúc chứa các khóa va chạm | Dễ cập nhật, nhưng truy vấn có thể tốn \(O(n)\) trong trường hợp xấu nhất |

Hopscotch đặc biệt đáng cân nhắc khi muốn **giữ dữ liệu trong một mảng**, tra cứu có giới hạn số ô theo \(H\), đồng thời chấp nhận sự phức tạp của chèn. Một số biến thể hopscotch còn được nghiên cứu cho truy cập **đồng thời** (concurrent), nhưng triển khai song song phải xử lý trạng thái trung gian, đồng bộ bitmap và cơ chế bảo vệ đọc/ghi; **thuật toán tuần tự ở trên không tự trở thành thread-safe**.

## 11. Các lỗi dễ gặp khi tự cài đặt

1. **Tính vùng lân cận mà quên ô gốc.** Vùng \(H\) ô là các độ lệch \(0,\ldots,H-1\), không phải \(1,\ldots,H\).
2. **Quên phép modulo khi vượt cuối mảng.** Với ô gốc 10, \(m=12,H=4\), các vị trí hợp lệ là 10, 11, 0, 1.
3. **Đưa khóa vào ô trống nằm ngoài vùng của nó.** Làm hỏng bất biến và tra cứu sẽ bỏ sót khóa.
4. **Chỉ kiểm tra khoảng cách từ ô gốc của khóa mới khi di chuyển khóa cũ.** Khóa cũ phải ở trong vùng của **chính ô gốc khóa cũ**.
5. **Đổi ô vật lý mà không đổi bitmap.** Thao tác tìm kiếm sẽ xét sai vị trí dù khóa vẫn còn.
6. **Nhầm bitmap của ô gốc với cờ ô vật lý đang có dữ liệu.** Một ô đang chứa khóa có thể thuộc bitmap của một ô gốc khác.
7. **Xóa ô nhưng không tắt bit.** Bitmap có thể trỏ tới ô trống hoặc khóa mới thuộc ô gốc khác.
8. **Cho rằng còn ô trống là chắc chắn chèn được.** Ô trống ngoài những vùng hợp lệ không đảm bảo tồn tại cách bố trí.
9. **Bỏ qua rehash khi thuật toán di chuyển bế tắc.** Một lần chèn cần có cách thất bại rõ ràng, tránh lặp vô hạn.
10. **Xem H cố định là đủ để chèn luôn \(O(1)\).** H chỉ trực tiếp giới hạn khu vực **tra cứu**; việc tìm ô trống và tái băm có thể tốn nhiều bước.

## 12. Tự kiểm tra

**Câu 1.** Với \(m=12,H=4\), vùng lân cận của ô gốc \(b=11\) gồm những ô nào?

**Lời giải:** \(N_4(11)=\{11,0,1,2\}\). Các chỉ số được tính theo modulo 12.

**Câu 2.** Với \(m=12\), khóa \(k\) có \(h(k)=10\) đang nằm ở ô 1. Khoảng cách thăm dò là bao nhiêu, và có hợp lệ khi \(H=4\) không?

**Lời giải:**

\[
d(k,1)=(1-10+12)\bmod12=3.
\]

Vì \(3<4\), vị trí này **hợp lệ**.

**Câu 3.** Trong ví dụ chèn 26, tại sao không đặt 26 trực tiếp vào ô 7 dù ô này trống?

**Lời giải:** Ô gốc của 26 là 2, nên ô 7 có khoảng cách \(5\), vượt giới hạn \(H-1=3\). Phải kéo ô trống về một trong các ô 2,3,4,5 trước.

**Câu 4.** Sau khi chuyển khóa 17 từ ô 5 sang ô 6, bitmap nào cần cập nhật và thay đổi thế nào?

**Lời giải:** Vì \(h(17)=5\), phải cập nhật \(B[5]\), tắt bit 0 và bật bit 1. Với \(H=4\), bitmap đổi từ **0001** thành **0010**.

**Câu 5.** Vì sao năm khóa có cùng ô gốc không thể cùng tồn tại trong bảng với \(H=4\), dù toàn bảng còn nhiều chỗ trống?

**Lời giải:** Cả năm chỉ có bốn ô hợp lệ trong \(N_4(b)\). Theo nguyên lý Dirichlet, không thể bố trí năm khóa phân biệt vào bốn ô mà mỗi ô chỉ chứa một khóa. Cần thay hàm băm, đổi cấu hình hoặc cách giải quyết va chạm.

**Câu 6.** Có thể xóa khóa tại ô vật lý rồi giữ nguyên bitmap để tối ưu thời gian không?

**Lời giải:** **Không.** Phải tắt bit trong bitmap của ô gốc khóa đó. Một bit còn bật có thể khiến tra cứu kiểm tra ô đã xóa; nếu ô đó được tái sử dụng cho khóa khác, metadata còn có thể trở nên không nhất quán.

## 13. Ghi nhớ

**Hopscotch hashing** giữ mỗi khóa trong **\(H\) ô liên tiếp tính từ ô gốc**, có xử lý vòng mảng. Mỗi ô gốc có thể duy trì **hop bitmap** để biết những độ lệch nào đang chứa khóa thuộc ô gốc đó, qua đó giới hạn số vị trí cần tra cứu.

Khi chèn mà ô trống đầu tiên ở quá xa, thuật toán **di chuyển các khóa khác để kéo ô trống vào vùng lân cận của khóa mới**, đồng thời bảo toàn vùng hợp lệ và cập nhật bitmap của **từng khóa bị di chuyển**. Nếu không tìm được cách bố trí, cần **rehash/resize hoặc thay cấu hình**. Với \(H\) cố định, tra cứu và xóa có độ phức tạp **\(O(1)\) theo số khóa** trong mô hình chi phí băm hằng số; chèn có thể tốn nhiều bước và đôi lúc phải xây lại bảng.

Khi lựa chọn giữa hopscotch, Robin Hood, cuckoo và chaining, hãy cân nhắc **giới hạn độ trễ tra cứu, tần suất chèn, hệ số tải, chi phí metadata và khả năng tái băm** theo workload thực tế.
