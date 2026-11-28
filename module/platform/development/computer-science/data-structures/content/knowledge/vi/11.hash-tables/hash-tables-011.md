# Băm lại khi tăng hoặc giảm dung lượng

## 1. Vì sao bảng băm phải thay đổi dung lượng?

Một **bảng băm (hash table)** dùng hàm băm để định vị cặp **khóa–giá trị**. Trong cách tổ chức đơn giản với `m > 0` ngăn hoặc ô, khóa `k` được đưa đến chỉ số ban đầu:

\[
i_m(k)=h(k)\bmod m.
\]

Ở đây `h(k)` là **mã băm của khóa**, còn `i_m(k)` là **chỉ số phụ thuộc vào dung lượng** `m`. Khi dữ liệu ngày càng nhiều, bảng có nhiều va chạm hơn; khi dữ liệu ít đi, một mảng quá lớn gây lãng phí bộ nhớ. Vì vậy, bảng thường **tăng dung lượng (grow)** hoặc **giảm dung lượng (shrink)**.

**Vấn đề quan trọng:** đổi `m` làm thay đổi cách xác định vị trí. Không thể chỉ tạo thêm các ô rỗng hoặc cắt bớt mảng mà giữ nguyên bản ghi tại các vị trí cũ. Phải **phân bố lại** các khóa vào cấu trúc mới; thao tác này thường gọi là **băm lại (rehash)**.

Trong thực tế, tên gọi có thể khác nhau giữa thư viện:

- **Resize:** thay đổi số ngăn/ô của bảng.
- **Rehash:** duyệt các bản ghi đang hoạt động và đặt lại chúng theo quy tắc định vị của bảng mới. Rehash có thể đi kèm resize, hoặc giữ nguyên dung lượng để dọn các ô mang dấu đã xóa.
- **Tính lại mã băm:** không phải lúc nào cũng cần. Nếu mã băm của khóa vẫn hợp lệ và được lưu sẵn, một số cách cài đặt có thể tái sử dụng mã đó rồi tính chỉ số mới; nếu thay hàm băm hoặc seed, phải tạo mã băm phù hợp với quy tắc mới.

Đích của rehash là **giữ nguyên tập ánh xạ khóa–giá trị**, không phải làm thay đổi ý nghĩa của các khóa.

## 2. Ví dụ từng bước: từ 5 ngăn lên 11 ngăn

Giả sử khóa là số nguyên không âm, `h(k)=k`, và bảng dùng **nối chuỗi (separate chaining)**: mỗi ngăn có thể chứa nhiều khóa. Ta lưu:

```text
(12, "A"), (17, "B"), (22, "C"), (9, "D")
```

Với `m=5`:

| Khóa | `h(k) mod 5` | Vị trí ban đầu |
| ---: | ---: | --- |
| 12 | 2 | Ngăn 2 |
| 17 | 2 | Ngăn 2 |
| 22 | 2 | Ngăn 2 |
| 9 | 4 | Ngăn 4 |

```text
Trước khi tăng (m = 5):
ngăn 0:  -
ngăn 1:  -
ngăn 2:  12:A -> 17:B -> 22:C
ngăn 3:  -
ngăn 4:  9:D
```

Giả sử quyết định tăng lên `m'=11`. Mỗi khóa phải được xét lại:

| Khóa | Chỉ số cũ `k mod 5` | Chỉ số mới `k mod 11` |
| ---: | ---: | ---: |
| 12 | 2 | 1 |
| 17 | 2 | 6 |
| 22 | 2 | 0 |
| 9 | 4 | 9 |

```text
Sau khi tăng và phân bố lại (m = 11):
ngăn  0:  22:C
ngăn  1:  12:A
ngăn  2:  -
ngăn  3:  -
ngăn  4:  -
ngăn  5:  -
ngăn  6:  17:B
ngăn  7:  -
ngăn  8:  -
ngăn  9:  9:D
ngăn 10:  -
```

Nếu chỉ mở rộng mảng cũ và giữ khóa 12 tại ngăn 2, lần tìm sau sẽ tính `12 mod 11 = 1` và tìm ở ngăn 1: **bản ghi vẫn còn trong bộ nhớ nhưng không truy cập được bằng khóa**. Bất biến “khóa nằm đúng ngăn theo dung lượng hiện tại” bị phá vỡ.

Tăng dung lượng có thể giúp giảm va chạm. Tuy nhiên, **không bảo đảm** mọi khóa sau rehash đều ở ngăn riêng: kết quả còn phụ thuộc hàm băm và tập khóa. Khi giảm từ 11 về 5 ngăn, các khóa 12, 17, 22 lại cùng ngăn 2; dữ liệu vẫn đúng nếu cơ chế xử lý va chạm được duy trì.

## 3. Hệ số tải là tín hiệu để tăng hoặc giảm

Gọi `n` là số **khóa khác nhau đang hoạt động** và `m` là số ngăn/ô. **Hệ số tải (load factor)** là:

\[
\alpha=\frac{n}{m}.
\]

Ý nghĩa của `\alpha` phụ thuộc vào chiến lược xử lý va chạm:

| Đặc điểm | Nối chuỗi | Địa chỉ mở |
| --- | --- | --- |
| Cách lưu | Mỗi ngăn có thể giữ nhiều nút | Mỗi ô giữ tối đa một bản ghi đang hoạt động |
| Giá trị tải có thể có | `\alpha\geq0`, có thể lớn hơn 1 | `0\leq\alpha\leq1` |
| Khi tải tăng | Chuỗi trong ngăn thường dài hơn | Ít ô trống hơn, đường thăm dò có thể dài hơn |
| Lý do tăng dung lượng | Giảm độ dài chuỗi kỳ vọng | Giữ ô trống và hạn chế thăm dò dài |
| Lý do giảm dung lượng | Tránh mảng đầu ngăn quá rộng | Tránh nhiều ô không sử dụng nhưng vẫn phải giữ đủ chỗ chèn |

Một **chính sách minh họa** là:

- Tăng khi `\alpha>0{,}75`, ví dụ nhân đôi `m`.
- Giảm khi `\alpha<0{,}20`, ví dụ chia đôi `m), nhưng không xuống dưới dung lượng tối thiểu.

Đây là **ngưỡng thiết kế**, không phải quy tắc bắt buộc của mọi bảng băm. Một số cấu trúc dùng tỷ lệ khác, làm tròn dung lượng lên số nguyên tố, hoặc giữ nguyên dung lượng để giảm chi phí cấp phát.

### Vì sao cần ngưỡng tăng và giảm khác nhau?

Giả sử bảng tăng từ `m=8` lên `m=16` vì có 7 khóa:

\[
\alpha_{\text{trước}}=\frac78=0{,}875,
\qquad
\alpha_{\text{sau}}=\frac7{16}=0{,}4375.
\]

Nếu chính sách **giảm ngay khi tải thấp hơn 0,5**, việc tăng lên 16 ô sẽ lập tức kích hoạt giảm lại 8 ô; sau đó có thể lại kích hoạt tăng. Cấu trúc sẽ **co–giãn liên tục (resize thrashing)** dù dữ liệu thay đổi rất ít.

Khi ngưỡng tăng `0,75` và ngưỡng giảm `0,20` cách xa nhau, kích thước sau khi tăng hoặc giảm không chạm ngay ngưỡng ngược lại. Vùng đệm này gọi là **hysteresis**: giúp tránh nhiều lần cấp phát và rehash liên tiếp do số khóa dao động.

Khi giảm, còn phải kiểm tra **dung lượng mới có hợp lệ không**. Với địa chỉ mở, nếu `m_{mới}\leq n` thì không còn ô trống cho một lần chèn mới và cách tổ chức có thể không đáp ứng ngưỡng tải mong muốn; cần chọn `m_{mới}` lớn hơn `n` đủ nhiều. Với các quy tắc thăm dò đặc biệt, kích thước mới cũng phải thỏa điều kiện toán học của dãy.

## 4. Rehash khi dùng chuỗi liên kết

Với **separate chaining**, mảng chứa các đầu ngăn; mỗi ngăn lưu một danh sách các bản ghi. Thay đổi `m` thường gồm những bước:

1. **Chọn dung lượng mới** `m_{mới}>0`, theo chính sách tải và giới hạn bộ nhớ.
2. **Cấp phát mảng đầu ngăn mới** với tất cả ngăn ban đầu rỗng.
3. **Duyệt từng nút của bảng cũ**; tính `i_{mới}(k)` cho khóa trong nút và đưa cặp `(k,v)` vào đúng ngăn của bảng mới.
4. **Công bố bảng mới** sau khi đã chuyển đủ bản ghi; giữ số phần tử `n` không đổi.

Mã giả:

```text
REHASH_CHAINING(old_buckets, new_m):
    new_buckets = array_of_empty_chains(new_m)
    for chain in old_buckets:
        for (key, value) in chain:
            i = hash(key) mod new_m
            append_or_link(new_buckets[i], (key, value))
    return new_buckets
```

Nếu đã biết mỗi bản ghi của bảng cũ là một khóa hợp lệ duy nhất, rehash **không cần tìm khóa trùng một lần nữa** khi thêm nút vào bảng mới. Có thể liên kết các nút cũ sang chuỗi mới nếu quản lý con trỏ cẩn thận, hoặc tạo các nút mới. Nếu đang duyệt danh sách liên kết rồi thay `next` của nút cũ để nối vào ngăn mới, cần lưu tham chiếu đến nút kế tiếp **trước khi đổi liên kết**, tránh làm mất phần chưa duyệt.

**Bất biến sau rehash:** tất cả cặp khóa–giá trị cũ vẫn còn đúng một lần; mỗi khóa nằm trong chuỗi theo `i_{mới}(k)`; `n` không đổi; không còn nút nào cần tra cứu trong mảng cũ.

## 5. Rehash khi dùng địa chỉ mở

Với **open addressing**, mỗi bản ghi nằm trực tiếp trong một ô, còn va chạm được giải quyết bằng **dãy thăm dò**. Đổi dung lượng có thể làm thay cả **ô ban đầu** lẫn **thứ tự thăm dò**, nên không thể sao chép nguyên trạng từng ô sang mảng mới.

Giả sử dùng linear probing, với:

\[
p_m(k,j)=\big(h(k)\bmod m+j\big)\bmod m.
\]

Trong bảng cũ có thể có một khóa bị đẩy từ vị trí ban đầu đến ô khác vì va chạm. Khi tạo bảng mới, phải:

1. Chọn `m_{mới}` phù hợp, còn khoảng trống và đạt điều kiện của phương pháp thăm dò.
2. Tạo mảng mới với các ô ở trạng thái **EMPTY**.
3. Duyệt bảng cũ; chỉ lấy các ô **OCCUPIED**, bỏ qua `EMPTY` và `DELETED` (tombstone).
4. Tái chèn mỗi bản ghi bằng **quy tắc thăm dò ứng với `m_{mới}`**; nếu ô đầu bận, tìm ô thích hợp theo dãy mới.
5. Sau khi chuyển đủ bản ghi, thay bảng cũ bằng bảng mới; số khóa `n` không đổi, số tombstone về 0.

Mã giả:

```text
REHASH_OPEN_ADDRESSING(old_slots, new_m):
    new_slots = array_of_EMPTY(new_m)
    for slot in old_slots:
        if slot.state == OCCUPIED:
            (key, value) = slot.record
            for j in valid_probes(key, new_m):
                i = probe(key, j, new_m)
                if new_slots[i] == EMPTY:
                    new_slots[i] = OCCUPIED(key, value)
                    break
            else:
                ERROR("Dung lượng hoặc quy tắc thăm dò không phù hợp")
    return new_slots
```

Khi giảm dung lượng với **quadratic probing**, dù `n<m_{mới}` vẫn có khả năng một dãy không đến được ô trống nếu hệ số và kích thước chọn sai. Với **double hashing**, cần bảo đảm bước nhảy nguyên tố cùng nhau với `m_{mới}`; nếu không, dãy có thể chỉ thăm một phần các ô. Vì thế, chính sách resize phải xét **cả tải lẫn tính hợp lệ của dãy thăm dò**.

### Rehash không nhất thiết phải đổi dung lượng

Địa chỉ mở dùng tombstone thường theo dõi thêm `d`: số ô mang dấu **DELETED**. Sau nhiều lần thêm–xóa, số khóa `n` có thể nhỏ nhưng đường thăm dò vẫn dài vì các tombstone không cho phép tìm kiếm dừng. Khi đó có thể dựng lại với **cùng `m`**, bỏ qua tombstone và tái chèn chỉ các bản ghi đang hoạt động.

Gọi `\beta=(n+d)/m` là tỷ lệ ô không còn EMPTY. Nếu `\alpha=n/m` nhỏ nhưng `\beta` lớn, **dọn tombstone** có thể hữu ích hơn việc tiếp tục giảm dung lượng. Hành vi thực tế vẫn phụ thuộc vị trí của các ô và phân bố khóa.

## 6. Ví dụ Python: bảng nối chuỗi tự tăng và giảm

Ví dụ dưới đây là một bảng băm đơn giản cho **khóa nguyên**, dùng danh sách các cặp `(key,value)` ở từng ngăn để tập trung vào resize. Việc chèn vào danh sách là mô hình **nối chuỗi**, không phải địa chỉ mở; phiên bản dùng linked list thật có thể thay danh sách Python bằng các nút `next` nhưng ý tưởng rehash không đổi.

Chính sách minh họa:

- Bắt đầu với `m=4` ngăn và không giảm xuống dưới 4.
- Sau khi chèn **khóa mới**, nếu `n/m>0,75` thì nhân đôi dung lượng.
- Sau khi xóa, nếu `n/m<0,20` và `m>4` thì chia đôi dung lượng (không thấp hơn 4).
- Cập nhật **giá trị của khóa cũ** không làm thay đổi `n`, nên không kích hoạt resize chỉ vì cập nhật.

```python
class BangBamTuCoGian:
    DUNG_LUONG_TOI_THIEU = 4

    def __init__(self):
        self.ngan = [[] for _ in range(self.DUNG_LUONG_TOI_THIEU)]
        self.so_khoa = 0

    def _chi_so(self, khoa: int, dung_luong=None):
        m = len(self.ngan) if dung_luong is None else dung_luong
        return khoa % m

    def _bam_lai(self, dung_luong_moi: int):
        ngan_moi = [[] for _ in range(dung_luong_moi)]
        for chuoi in self.ngan:
            for khoa, gia_tri in chuoi:
                i = self._chi_so(khoa, dung_luong_moi)
                ngan_moi[i].append((khoa, gia_tri))

        # Chỉ thay bảng sau khi toàn bộ khóa đã vào đúng ngăn mới.
        self.ngan = ngan_moi

    def gan(self, khoa: int, gia_tri):
        i = self._chi_so(khoa)
        for j, (khoa_cu, _) in enumerate(self.ngan[i]):
            if khoa_cu == khoa:
                self.ngan[i][j] = (khoa, gia_tri)
                return  # Cập nhật không tăng số khóa

        self.ngan[i].append((khoa, gia_tri))
        self.so_khoa += 1
        if self.so_khoa / len(self.ngan) > 0.75:
            self._bam_lai(len(self.ngan) * 2)

    def lay(self, khoa: int):
        for khoa_cu, gia_tri in self.ngan[self._chi_so(khoa)]:
            if khoa_cu == khoa:
                return gia_tri
        raise KeyError(khoa)

    def xoa(self, khoa: int):
        i = self._chi_so(khoa)
        for j, (khoa_cu, gia_tri) in enumerate(self.ngan[i]):
            if khoa_cu == khoa:
                self.ngan[i].pop(j)
                self.so_khoa -= 1
                m = len(self.ngan)
                if (m > self.DUNG_LUONG_TOI_THIEU
                        and self.so_khoa / m < 0.20):
                    m_moi = max(self.DUNG_LUONG_TOI_THIEU, m // 2)
                    self._bam_lai(m_moi)
                return gia_tri
        raise KeyError(khoa)

    def thong_ke(self):
        m = len(self.ngan)
        return m, self.so_khoa, self.so_khoa / m

    def xem(self):
        return [
            [(k, v) for k, v in chuoi]
            for chuoi in self.ngan
        ]


bang = BangBamTuCoGian()
for k in [1, 5, 9]:
    bang.gan(k, str(k))
print(bang.thong_ke())  # (4, 3, 0.75)

bang.gan(13, "13")
print(bang.thong_ke())  # (8, 4, 0.5): đã tăng dung lượng
print(bang.xem())
# [[], [(1, '1'), (9, '9')], [], [], [],
#  [(5, '5'), (13, '13')], [], []]

bang.gan(9, "moi")
print(bang.thong_ke())  # (8, 4, 0.5): chỉ cập nhật
print(bang.lay(9))      # moi

bang.xoa(13)
bang.xoa(9)
bang.xoa(5)
print(bang.thong_ke())  # (4, 1, 0.25): đã giảm dung lượng
print(bang.lay(1))      # 1: khóa còn lại vẫn tìm đúng
```

Diễn biến của ví dụ:

| Thời điểm | `m` | `n` | `α=n/m` | Hành động |
| --- | ---: | ---: | ---: | --- |
| Sau thêm `1,5,9` | 4 | 3 | 0,75 | Chưa vượt ngưỡng tăng |
| Ngay sau thêm `13`, trước resize | 4 | 4 | 1,00 | Vượt ngưỡng, cần tăng |
| Sau tăng | 8 | 4 | 0,50 | Đã phân bố lại cả bốn khóa |
| Sau cập nhật `9` | 8 | 4 | 0,50 | Không thay đổi số khóa |
| Sau xóa `13,9` | 8 | 2 | 0,25 | Chưa dưới ngưỡng giảm |
| Sau xóa thêm `5`, trước resize | 8 | 1 | 0,125 | Dưới ngưỡng, cần giảm |
| Sau giảm | 4 | 1 | 0,25 | Chỉ giữ khóa `1` và giá trị của nó |

Đoạn mã dùng ngăn là danh sách Python và tính `k mod m` nên phù hợp để học. Trong hệ thống lớn, cần cân nhắc kích thước khóa, chi phí cấp phát, ràng buộc đồng thời và chính sách tải được chọn theo dữ liệu thực.

## 7. Độ phức tạp của rehash và chi phí phân bổ

Nếu **mảng cũ** có `m_{cũ}` ngăn/ô, mảng mới có `m_{mới}` ngăn/ô và đang lưu `n` khóa:

1. Duyệt bảng cũ tốn `O(m_{cũ}+n)` đối với nối chuỗi, hoặc `O(m_{cũ})` để quét các ô của địa chỉ mở.
2. Khởi tạo mảng mới tốn `O(m_{mới})`.
3. Phân bố lại `n` bản ghi thường tốn `O(n)` kỳ vọng nếu tính băm, so sánh khóa và việc đặt bản ghi có chi phí phù hợp; trong nối chuỗi, có thể gắn nút vào đầu ngăn mới với chi phí hằng số trên mỗi nút.

Vì vậy, chi phí một lần rehash nối chuỗi thường là:

\[
T_{\text{rehash}}=O(m_{cũ}+m_{mới}+n)
\]

với giả định thời gian băm khóa `O(1)`. Đối với địa chỉ mở, biểu thức tương tự là **kỳ vọng** dưới điều kiện phân bố và tải thích hợp; nếu nhiều khóa liên tục va chạm, việc tái chèn có thể đắt hơn. Khóa dài có thể khiến việc tính mã băm từ đầu tốn thời gian bổ sung.

**Một lần rehash không phải `O(1)`.** Tuy nhiên, khi tăng dung lượng theo cấp số nhân, giữa hai lần tăng thường có nhiều thao tác thêm. Tổng chi phí các lần mở rộng có thể được **phân bổ (amortized)** trên các lần thêm, dẫn đến chi phí tăng dung lượng trung bình phân bổ `O(1)` cho mỗi lần thêm trong mô hình thích hợp.

Ví dụ, khi tăng `4 → 8 → 16 → 32`, số khóa cần phân bố lại qua các lần tăng có tổng bậc tuyến tính so với số khóa đã thêm, không phải mỗi lần thêm đều phải chuyển toàn bộ bảng.

Đối với **giảm dung lượng**, cũng cần các ngưỡng tăng–giảm tách biệt để bảo đảm đủ thao tác xảy ra giữa những lần co–giãn; nếu không, chỉ vài lần thêm và xóa luân phiên có thể gây rehash lặp lại và phá vỡ hiệu năng phân bổ mong đợi.

**Bộ nhớ tạm:** trong một đợt rehash, có thể phải đồng thời giữ mảng cũ và mảng mới; bộ nhớ đỉnh vì thế cao hơn bộ nhớ ổn định sau khi thay bảng. Với nối chuỗi, còn có lựa chọn tái sử dụng nút cũ hoặc tạo nút mới, ảnh hưởng đến bộ nhớ và chi phí thao tác.

## 8. Những bất biến và lỗi thường gặp

Để duy trì tính đúng đắn khi thay kích thước, hãy kiểm tra:

1. **Không mất khóa hoặc giá trị:** mọi cặp đang hoạt động trước rehash đều còn sau rehash, trừ cặp chủ động bị xóa.
2. **Không tạo bản sao logic:** mỗi khóa trong map chỉ có một bản ghi đang hoạt động. Cập nhật không làm tăng `n`.
3. **Chỉ số và dãy thăm dò dùng dung lượng mới:** sau resize, mọi `get/put/remove` đều dùng cùng quy tắc của bảng mới.
4. **Không chuyển tombstone thành bản ghi:** với địa chỉ mở, chỉ tái chèn các ô `OCCUPIED`; các dấu `DELETED` được bỏ đi.
5. **Không giảm quá nhỏ:** bảo đảm dung lượng tối thiểu, đủ chỗ chèn và điều kiện của phương pháp thăm dò (ví dụ bước nhảy của băm kép).
6. **Không thay định nghĩa bằng nhau của khóa:** các thuộc tính tham gia băm hoặc so sánh phải nhất quán; rehash không chữa được khóa đã bị thay đổi sai khi lưu.
7. **Không công bố bảng mới khi mới chuyển một phần bản ghi:** quá trình tái cấu trúc phải quản lý nhất quán. Trong môi trường có nhiều luồng, cần cơ chế đồng bộ hoặc thiết kế rehash theo giai đoạn phù hợp để tránh truy cập dữ liệu nửa cũ nửa mới.

Một số thư viện có thể tận dụng việc tăng dung lượng lên gấp đôi để tính nhanh vị trí mới từ mã băm đã lưu, thay vì gọi lại toàn bộ hàm băm; song về mặt logic các phần tử vẫn **phải được đặt theo quy tắc định vị mới**. Không nên coi tối ưu hóa ấy là lý do được phép giữ nguyên toàn bộ mảng cũ.

Các con trỏ, chỉ số ô hoặc iterator trỏ vào **cấu trúc nội bộ** có thể không còn hợp lệ sau resize. Người dùng API nên tra cứu bằng khóa thay vì phụ thuộc vị trí vật lý của một bản ghi; quy tắc iterator cụ thể phụ thuộc từng thư viện.

## 9. Tự kiểm tra

**Câu 1.** Một bảng có `m=5`, lưu khóa `12` tại ngăn `12 mod 5=2`. Nếu chỉ thêm ô để thành `m=11` mà không chuyển khóa, thao tác tìm sẽ có kết quả gì?

**Đáp án:** Tra cứu mới tính `12 mod 11=1` và tìm ở ngăn 1; khóa vẫn ở ngăn 2 nên có thể báo không tìm thấy. Cần phân bố lại theo `m=11`.

**Câu 2.** Bảng nối chuỗi có `n=30` khóa, `m=10` ngăn, sau đó mở rộng lên 40 ngăn. Hệ số tải trước và sau là bao nhiêu?

**Đáp án:** Trước: `α=30/10=3`. Sau: `α=30/40=0,75`. `n` không đổi vì rehash không thêm hoặc xóa khóa.

**Câu 3.** Một bảng địa chỉ mở có 20 khóa đang hoạt động và 15 tombstone. Khi dựng lại bảng với cùng dung lượng, phải chuyển bao nhiêu bản ghi?

**Đáp án:** Chỉ 20 bản ghi ở trạng thái `OCCUPIED`. Tombstone không chứa khóa đang hoạt động nên bị bỏ qua; số tombstone sau dựng lại bằng 0.

**Câu 4.** Vì sao đặt ngưỡng tăng tại `α>0,75` và ngưỡng giảm tại `α<0,70` có thể gây nhiều lần resize?

**Đáp án:** Hai ngưỡng quá gần nhau, và tùy tỷ lệ thay đổi dung lượng, bảng có thể tăng rồi lập tức thỏa điều kiện giảm. Cần vùng đệm đủ rộng và kiểm tra tải sau resize để tránh dao động.

**Câu 5.** Khi giảm một bảng băm kép từ 17 xuống 12 ô, chỉ cần `n<12` là đủ bảo đảm chèn lại mọi khóa không?

**Đáp án:** Chưa đủ. Ngoài chỗ trống và hệ số tải phù hợp, mỗi bước nhảy `h_2(k)` còn cần nguyên tố cùng nhau với `12` để đi qua đủ các ô theo quy tắc băm kép đang dùng. Phải tính hoặc thiết kế lại các hàm phụ thuộc dung lượng.

**Câu 6.** Nếu sau khi tăng bảng mà `get(k)` vẫn đúng với mọi khóa, có thể kết luận mỗi thao tác thêm đều tốn `O(1)` chắc chắn không?

**Đáp án:** Không. Một lần rehash có thể tốn thời gian tuyến tính theo số khóa và dung lượng; `O(1)` thường là thời gian **kỳ vọng, phân bổ** khi giả định phân bố băm tốt, tải được kiểm soát và chiến lược tăng–giảm hợp lý.

**Ghi nhớ:** Băm lại là việc **đưa các bản ghi đang hoạt động vào đúng vị trí theo dung lượng và quy tắc định vị hiện tại** (bao gồm dãy thăm dò nếu dùng địa chỉ mở). Tăng bảng giúp giữ hiệu năng khi tải cao; giảm bảng tiết kiệm bộ nhớ khi tải thấp; dựng lại cùng kích thước có thể dọn tombstone. Mọi thay đổi phải giữ nguyên ánh xạ khóa–giá trị, bảo vệ các bất biến tra cứu và chọn ngưỡng tránh co–giãn liên tục.
