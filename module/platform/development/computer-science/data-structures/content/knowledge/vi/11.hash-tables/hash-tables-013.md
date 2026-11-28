# Khóa thay đổi sau khi chèn và nguy cơ không tìm lại được dữ liệu

## 1. Một bản ghi còn trong bảng nhưng vì sao tìm không thấy?

Giả sử ứng dụng dùng **bảng băm (hash table)** để lưu số lượng tồn kho theo mã sản phẩm. Mỗi thao tác `put(k, v)` xác định nơi lưu cặp **khóa–giá trị** dựa vào khóa `k`; thao tác `get(k)` về sau phải tính lại vị trí tìm kiếm theo cùng quy tắc.

Nếu mã sản phẩm được lấy từ một **đối tượng có thể thay đổi**, việc chỉnh sửa mã sau khi chèn có thể làm bảng không còn định vị được bản ghi đã lưu. Đáng chú ý: **bản ghi chưa hề bị xóa, nhưng tìm bằng chính đối tượng khóa cũ vẫn có thể thất bại**.

Đây là lỗi **khóa thay đổi sau khi chèn (mutable key)**. Nó liên quan trực tiếp đến ba khái niệm nền tảng:

- **Hàm băm** `hash(k)`: tính một mã băm dựa trên trạng thái khóa.
- **Phép so sánh bằng nhau** `equals(a, b)` hoặc `a == b`: xác định hai khóa có cùng ý nghĩa logic hay không.
- **Vị trí lưu/đường thăm dò**: được tính từ mã băm và dung lượng bảng khi chèn và khi tìm.

**Nguyên tắc:** Những thuộc tính dùng để xác định `hash` và quan hệ bằng nhau của một khóa cần **ổn định trong suốt thời gian khóa đang được lưu trong bảng**. Không phải toàn bộ đối tượng đều bất biến; điều bắt buộc là phần trạng thái tạo nên **danh tính khóa** phải ổn định.

## 2. Vết lỗi với một bảng nối chuỗi rất nhỏ

Xét bảng có `m=8` ngăn, xử lý va chạm bằng **nối chuỗi (separate chaining)** và lấy:

\[
i(k)=h(k)\bmod8.
\]

Định nghĩa đối tượng `KhoaNhanVien` có thuộc tính `ma`; ví dụ đơn giản cho `h(k)=k.ma` và hai khóa bằng nhau khi giá trị `ma` bằng nhau.

**Bước 1 — chèn:** tạo đối tượng `k` với `k.ma=10`, chèn `(k, "Hồ sơ A")`. Bản ghi được đưa vào ngăn `10 mod 8=2`.

```text
Mảng ngăn (m = 8)

0: -
1: -
2: (k, "Hồ sơ A")       k.ma = 10
3: -
4: -
5: -
6: -
7: -
```

**Bước 2 — sửa khóa tại chỗ:** chương trình gọi `k.ma = 11` mà **không** thông báo cho bảng băm.

Đối tượng `k` vẫn chính là đối tượng nằm trong ngăn 2. Bảng không tự theo dõi mọi thuộc tính của đối tượng và không tự chuyển nút sang ngăn mới:

```text
0: -
1: -
2: (k, "Hồ sơ A")       k.ma = 11  <-- nút vẫn nằm ở ngăn cũ
3: -                    11 mod 8 = 3
4: -
5: -
6: -
7: -
```

**Bước 3 — tìm:** gọi `get(k)`. Chương trình tính lại `h(k)=11` và đến **ngăn 3**. Ngăn này rỗng nên trả kết quả *không tìm thấy*, mặc dù nút vẫn nằm ở **ngăn 2**.

Lỗi không phụ thuộc việc truyền “cùng tham chiếu đối tượng” hay “một đối tượng mới có cùng mã”. Dù cùng tham chiếu, nếu thuật toán **định vị bằng mã băm mới** trước khi so sánh khóa, nó vẫn có thể đi đến sai ngăn.

Với địa chỉ mở (open addressing), tình huống tương tự xảy ra: khóa được đặt trên một **dãy thăm dò cũ**, còn `get` dùng dãy mới. Bảng có thể kết luận không thấy trước khi đi đến ô chứa khóa thực tế.

> Không phải mọi lần thay đổi hash đều chắc chắn gây thất bại trong mọi bảng: một số mã băm khác nhau có thể vô tình dẫn đến cùng vị trí hoặc cùng đường thăm dò. Điều đó chỉ là trùng hợp, **không phải bảo đảm tính đúng đắn**.

## 3. Hai bất biến dễ bị phá vỡ

Để làm một khóa hợp lệ trong hash map, cần thỏa hợp đồng về băm và so sánh:

\[
a=b\quad\Longrightarrow\quad hash(a)=hash(b).
\]

Nghĩa là **hai khóa được xem là bằng nhau phải có cùng mã băm**. Chiều ngược lại **không đúng**: hai khóa khác nhau vẫn có thể va chạm.

Ngoài hợp đồng tại một thời điểm, một khóa đang nằm trong bảng còn cần **tính ổn định theo thời gian**:

1. **Bất biến về định vị:** mã băm/dãy thăm dò dùng để tìm khóa phải tương thích với vị trí mà khóa đã được chèn theo cấu hình bảng hiện tại.
2. **Bất biến về danh tính logic:** quan hệ bằng nhau giữa khóa đã lưu và những khóa dùng để tra cứu phải tiếp tục phản ánh đúng danh tính mà map định nghĩa; không được bất ngờ biến hai khóa độc lập thành cùng một khóa logic.

Ví dụ ban đầu hai đối tượng có `ma=10` và `ma=11` là hai khóa khác nhau. Nếu đổi đối tượng đầu từ `10` thành `11` khi cả hai vẫn đang nằm trong bảng, lúc đó **hai khóa có thể trở nên bằng nhau**, dù đang có hai bản ghi riêng. Điều này vi phạm mục tiêu “mỗi khóa logic ứng với tối đa một giá trị” của map.

Tình huống thay đổi một thuộc tính **chỉ tham gia so sánh bằng nhau** nhưng không tham gia hash cũng có thể gây sai ngữ nghĩa. Ngược lại, một thuộc tính **chỉ tham gia hash** nhưng không tham gia phép bằng nhau có thể khiến hai khóa bằng nhau nhận mã băm khác nhau. Một thiết kế khóa đúng phải xem **hash và equality như một cặp quy tắc nhất quán**, không chỉnh sửa tùy tiện một nửa.

## 4. Ví dụ Python: thấy lỗi qua một bảng nối chuỗi tự cài đặt

Ví dụ sau dùng mảng ngăn chứa các cặp khóa–giá trị. Nó không dựa vào chi tiết cài đặt của `dict` Python, nên có thể quan sát trực tiếp cơ chế **đi sai ngăn**. Phạm vi ví dụ: khóa kiểu `Khoa` có mã nguyên không âm, bảng có 8 ngăn và không tự thay đổi kích thước.

```python
class Khoa:
    def __init__(self, ma: int):
        self.ma = ma

    def __hash__(self):
        return hash(self.ma)

    def __eq__(self, other):
        return isinstance(other, Khoa) and self.ma == other.ma

    def __repr__(self):
        return f"Khoa({self.ma})"


class BangBamNoiChuoi:
    def __init__(self, so_ngan=8):
        if so_ngan <= 0:
            raise ValueError("Số ngăn phải dương")
        self.ngan = [[] for _ in range(so_ngan)]

    def _vi_tri(self, khoa):
        return hash(khoa) % len(self.ngan)

    def gan(self, khoa, gia_tri):
        chuoi = self.ngan[self._vi_tri(khoa)]
        for i, (k_cu, _) in enumerate(chuoi):
            if k_cu == khoa:
                chuoi[i] = (k_cu, gia_tri)
                return
        chuoi.append((khoa, gia_tri))

    def lay(self, khoa):
        for k_cu, gia_tri in self.ngan[self._vi_tri(khoa)]:
            if k_cu == khoa:
                return gia_tri
        raise KeyError(khoa)

    def xoa(self, khoa):
        chuoi = self.ngan[self._vi_tri(khoa)]
        for i, (k_cu, gia_tri) in enumerate(chuoi):
            if k_cu == khoa:
                chuoi.pop(i)
                return gia_tri
        raise KeyError(khoa)


bang = BangBamNoiChuoi(8)
k = Khoa(10)
bang.gan(k, "Hồ sơ A")
print(bang.lay(Khoa(10)))  # Hồ sơ A
print(bang._vi_tri(k))     # 2

k.ma = 11                 # SỬA phần trạng thái định danh khóa
print(bang._vi_tri(k))    # 3: vị trí dự kiến mới
print(bang.ngan[2])       # [(Khoa(11), 'Hồ sơ A')] ở ngăn cũ

try:
    print(bang.lay(k))
except KeyError:
    print("Không tìm thấy bằng chính đối tượng k")

try:
    print(bang.lay(Khoa(10)))
except KeyError:
    print("Không tìm thấy bằng mã cũ 10")

# Chỉ để minh họa cách phục hồi trong môi trường được kiểm soát:
k.ma = 10                 # Khôi phục đúng danh tính cũ
gia_tri = bang.xoa(k)     # Xóa trước khi đổi khóa
k.ma = 11
bang.gan(k, gia_tri)      # Chèn lại theo mã băm mới
print(bang.lay(Khoa(11)))  # Hồ sơ A
```

Hai câu `lay` thất bại vì **hai lý do liên quan nhưng khác nhau**:

- Tìm bằng `k` sau khi sửa `ma=11` đi vào ngăn 3, nhưng bản ghi vẫn ở ngăn 2.
- Tìm bằng `Khoa(10)` đi vào ngăn 2, song khóa lưu tại đây đã trở thành `Khoa(11)` và **không còn bằng** `Khoa(10)`.

Đoạn phục hồi cuối chỉ thực hiện được vì ví dụ còn biết **trạng thái cũ** (`ma=10`) và chưa phát sinh xung đột. Trong ứng dụng thực tế, không nên dựa vào việc tạm đổi ngược một khóa đã hỏng. Cách an toàn là **xóa bản ghi khi khóa cũ còn hợp lệ, sau đó mới chuyển sang khóa mới và chèn lại**.

## 5. Nếu thêm khóa mới sau khi khóa cũ bị sửa thì sao?

Tiếp tục xét trạng thái lỗi **trước khi phục hồi** ở mục 4:

```text
Ngăn 2: (k, "Hồ sơ A"), nhưng k.ma hiện là 11
Ngăn 3: rỗng
```

Nếu chương trình gọi `gan(Khoa(11), "Hồ sơ B")`, mã băm đưa khóa mới tới ngăn 3. Vì ngăn 3 chưa có khóa bằng `11`, thao tác có thể chèn thành công. Sau đó:

```text
Ngăn 2: (Khoa(11), "Hồ sơ A")  <-- vị trí sai
Ngăn 3: (Khoa(11), "Hồ sơ B")  <-- vị trí đúng
```

Bảng lúc này chứa **hai khóa logic bằng nhau** nhưng nằm ở hai ngăn khác nhau. Tra cứu khóa `11` có thể trả `"Hồ sơ B"`, còn bản ghi `"Hồ sơ A"` vẫn nằm trong cấu trúc nhưng không được truy cập theo đường định vị thông thường.

Đây không chỉ là lỗi “mất khả năng tìm kiếm”; nó còn có thể gây **bản ghi trùng, cập nhật nhầm, xóa không hết, thống kê số phần tử sai về mặt logic**. Một phép tái băm vô tình gom dữ liệu về cùng ngăn cũng không tự đưa ra được quyết định đúng nếu hai bản ghi cùng khóa có giá trị khác nhau.

## 6. Không phải mọi thay đổi của đối tượng khóa đều nguy hiểm

Điểm mấu chốt không phải “không bao giờ được sửa một đối tượng”, mà là **không được sửa phần trạng thái quyết định danh tính của khóa khi nó đang được dùng trong bảng**.

| Loại thay đổi | Ví dụ | Tác động dự kiến |
| --- | --- | --- |
| Đổi thuộc tính tham gia `hash` | `ma=10` thành `ma=11` khi `hash` dựa trên `ma` | Có thể đi tới sai ngăn/dãy thăm dò |
| Đổi thuộc tính tham gia `equals` | Đổi mã hoặc thuộc tính dùng để xác định hai khóa bằng nhau | Có thể làm tìm theo mã cũ thất bại, sinh khóa logic trùng |
| Đổi thuộc tính **không** tham gia `hash` và `equals` | Đổi tên hiển thị của nhân viên, giữ mã định danh | Không ảnh hưởng định vị và danh tính khóa nếu quy tắc được thiết kế đúng |
| Đổi **giá trị** ứng với khóa | Cập nhật số lượng tồn kho hoặc trạng thái hồ sơ | Là thao tác map bình thường; khóa không đổi |
| Đổi dung lượng bảng qua API rehash | Bảng tự chuyển bản ghi sang vị trí mới | Hợp lệ vì cấu trúc chủ động cập nhật vị trí theo quy tắc mới |

Ví dụ: nếu mã nhân viên là danh tính ổn định và tên hiển thị chỉ là dữ liệu mô tả, người dùng đổi tên nhân viên sẽ không làm ảnh hưởng `hash` hay `equals`. Việc cho **tên hiển thị** tham gia phép băm dù nó không phải phần danh tính là một dấu hiệu thiết kế khóa dễ gặp rủi ro.

### Khóa so sánh bằng danh tính đối tượng

Trong một số ngôn ngữ, nếu khóa dùng **danh tính tham chiếu** để so sánh và băm (identity-based key), thay đổi các trường dữ liệu khác không làm thay đổi danh tính khóa. Nhưng khi đó hai đối tượng có cùng nội dung chưa chắc được xem là cùng khóa. Cần chọn **equality theo danh tính** hay **equality theo nội dung** phù hợp với yêu cầu nghiệp vụ; không nên mặc nhiên đồng nhất hai cách.

## 7. Dùng khóa bất biến: cách phòng ngừa được ưu tiên

Cách dễ kiểm soát nhất là dùng khóa có phần danh tính **bất biến (immutable)**: số nguyên, chuỗi bất biến, tuple các thành phần bất biến, hoặc đối tượng giá trị bất biến với hợp đồng băm–bằng nhau rõ ràng.

Ví dụ Python với `dataclass(frozen=True)`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MaDonHang:
    chi_nhanh: str
    so_don: int


ma_cu = MaDonHang("HN", 42)
don_hang = {ma_cu: {"trang_thai": "Đang xử lý"}}
print(don_hang[MaDonHang("HN", 42)]["trang_thai"])
# Đang xử lý

# Đổi value (dữ liệu đơn hàng): hợp lệ, khóa vẫn là ma_cu.
don_hang[ma_cu]["trang_thai"] = "Đã đóng gói"

# ma_cu.so_don = 43  # FrozenInstanceError nếu thực thi

# Khi nghiệp vụ thực sự cần đổi mã định danh:
ma_moi = MaDonHang("HN", 43)
if ma_moi in don_hang:
    raise ValueError("Mã đơn mới đã tồn tại")
gia_tri = don_hang.pop(ma_cu)  # Xóa bằng khóa cũ còn hợp lệ
don_hang[ma_moi] = gia_tri     # Thêm theo khóa mới
print(don_hang[MaDonHang("HN", 43)]["trang_thai"])
# Đã đóng gói
```

Lưu ý: `frozen=True` ngăn gán lại thuộc tính thông thường, nhưng **không tự động làm bất biến sâu** những đối tượng lồng bên trong. Nếu một trường tham gia hash/equality trỏ tới dữ liệu có thể thay đổi, thiết kế vẫn cần xem xét. Ở ví dụ này, các trường định danh là `str` và `int` bất biến.

Python cũng chủ động không cho dùng những kiểu có thể thay đổi thông thường như `list` hay `dict` trực tiếp làm khóa `dict` vì chúng không hashable. Nhưng một **lớp tự định nghĩa** có `__hash__` dựa trên trường mutable vẫn có thể được chèn và tạo ra lỗi như trên; `hashable` **không đồng nghĩa** với “an toàn nếu thay đổi nội dung”.

## 8. Nếu bắt buộc đổi mã khóa thì thay đổi thế nào cho đúng?

Trường hợp mã sản phẩm hoặc mã hồ sơ thực sự phải đổi, hãy coi việc đổi mã là **một thao tác cập nhật cấu trúc**, không phải chỉnh sửa âm thầm thuộc tính của khóa đã chèn.

### Quy trình an toàn khi chỉ có một bảng băm

1. Xác định **khóa cũ** và **khóa mới** bằng các giá trị danh tính rõ ràng.
2. Kiểm tra khóa cũ còn tồn tại; xác định cách xử lý nếu khóa mới đã tồn tại.
3. **Xóa bản ghi theo khóa cũ trước khi trạng thái khóa cũ bị sửa.**
4. Tạo khóa mới hoặc cập nhật đối tượng sau khi đã lấy nó ra khỏi bảng.
5. **Chèn lại** cặp `(khóa_mới, giá_trị)`, để hàm băm và cơ chế xử lý va chạm chọn đúng vị trí.
6. Kiểm tra rằng khóa mới tìm được, khóa cũ không còn, và số bản ghi logic phù hợp.

Mã giả:

```text
DOI_KHOA(map, old_key, new_key):
    if not map.contains(old_key):
        ERROR("Không có khóa cũ")
    if new_key != old_key and map.contains(new_key):
        ERROR("Khóa mới đã được dùng")

    value = map.remove(old_key)
    map.put(new_key, value)
```

Mã giả mô tả **thứ tự logic**, chưa giải quyết lỗi cấp phát, ngoại lệ hay truy cập đồng thời. Nếu bảng được chia sẻ giữa nhiều luồng hoặc cần bảo đảm nguyên tử, quy trình phải được thực hiện dưới cơ chế đồng bộ/giao dịch thích hợp; khi thao tác thêm thất bại, cần có chiến lược phục hồi.

### Thiết kế tốt hơn khi mã nghiệp vụ thường xuyên thay đổi

Nếu mã hiển thị thay đổi nhiều lần, có thể dùng **ID nội bộ bất biến** làm khóa, còn mã hiển thị là **thuộc tính của giá trị**:

```text
Khóa bất biến:    employee_id = 8451
Giá trị:          {display_code: "NV-2026-22", name: "Lan", ...}

Đổi display_code chỉ sửa giá trị, không thay khóa employee_id.
```

Nếu cần tra cứu nhanh từ `display_code` đến `employee_id`, có thể duy trì một bảng chỉ mục phụ. Khi thay mã hiển thị, phải cập nhật chỉ mục phụ có kiểm soát, tránh để hai bảng mâu thuẫn nhau.

## 9. Tại sao resize/rehash không phải cách sửa khóa mutable?

**Đổi dung lượng bảng** và **đổi trạng thái khóa** là hai sự kiện khác nhau:

- Khi resize, bảng **chủ động** biết dung lượng mới; nó duyệt bản ghi và đưa chúng vào đúng vị trí theo công thức mới.
- Khi một đối tượng khóa bị sửa từ bên ngoài, bảng có thể **không được thông báo**; đường tìm mới không còn dẫn đến vị trí cũ.

Một đợt rehash sau khi khóa đã bị sửa *có thể* khiến bản ghi lại tìm thấy vì bảng xét trạng thái hiện tại của khóa. Nhưng đó **không phải cách phục hồi đáng tin cậy**: đã có thể xuất hiện các bản ghi trùng khóa, giá trị mâu thuẫn hoặc khác biệt về phép so sánh. Rehash không thể tự biết liệu cần giữ giá trị cũ, giá trị mới hay từ chối thay đổi mã.

Do vậy, **không sửa khóa tại chỗ rồi chờ bảng tự resize**. Hãy dùng khóa bất biến hoặc một API đổi khóa kiểm soát được quan hệ giữa bản ghi cũ và bản ghi mới.

## 10. Những lỗi triển khai thường gặp

1. **Giữ đối tượng khóa trong map rồi đổi thuộc tính định danh:** vị trí lưu cũ không tự cập nhật.
2. **Chỉ xem hash mà quên equality:** dù mã băm không đổi, quan hệ bằng nhau có thể thay đổi khiến tra cứu theo giá trị cũ sai hoặc tạo bản ghi trùng.
3. **Cho trường hiển thị dễ đổi tham gia `__hash__`/`equals`:** biến một thao tác đổi nhãn thành nguy cơ hỏng chỉ mục.
4. **Xóa sau khi đã sửa khóa:** thao tác `remove` có thể tìm theo hash mới và không thấy bản ghi để xóa.
5. **Sửa khóa để “đổi tên” thay vì remove–insert:** hai khóa có thể vô tình trở nên bằng nhau và không còn một giá trị duy nhất.
6. **Tin rằng dùng cùng tham chiếu là đủ:** thuật toán vẫn định vị trước khi so sánh đối tượng.
7. **Tin rằng lớp hashable chắc chắn an toàn:** khả năng tính mã băm không bảo đảm mã băm ổn định theo thời gian.
8. **Mong resize tự sửa mọi lỗi:** tái băm không quyết định được cách hợp nhất những khóa đã thành bằng nhau.

## 11. Kiểm tra bất biến bằng các kịch bản nhỏ

Một bộ kiểm tra cơ bản cho cấu trúc map dùng khóa đối tượng nên có các trường hợp:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Thêm bằng khóa `a`, tìm bằng khóa `b` khác đối tượng nhưng `a == b` | Tìm thấy đúng giá trị nếu hợp đồng hash/equality nhất quán |
| Cập nhật `value` của một khóa đang tồn tại | Vẫn tìm thấy bằng khóa cũ; không tăng số lượng khóa |
| Thay đổi thuộc tính chỉ để hiển thị, không tham gia hash/equality | Vẫn tìm thấy bằng khóa cũ |
| Thay đổi trường định danh khi khóa vẫn trong bảng | **Không cho phép qua API** hoặc phải thực hiện chuyển khóa có kiểm soát |
| Chuyển từ `old_key` sang `new_key` khác danh tính | Khóa mới tìm thấy, khóa cũ không tồn tại, giá trị được bảo toàn |
| `new_key` đã có sẵn | Thực thi chính sách xung đột rõ ràng, không âm thầm ghi đè |

Nếu ứng dụng có nhiều chỉ mục hoặc lưu trữ lâu dài, hãy bổ sung kiểm tra tính nhất quán giữa khóa chính, chỉ mục phụ và dữ liệu giá trị. Một lỗi mutable key có thể không xuất hiện ngay lúc chèn mà chỉ bộc lộ sau nhiều thao tác cập nhật, xóa hoặc rehash.

## 12. Tự kiểm tra

**Câu 1.** Bảng có 8 ngăn, khóa có mã `10` nên được chèn vào ngăn `2`. Nếu đổi mã ngay trên đối tượng khóa thành `11` mà không xóa và chèn lại, tìm khóa sẽ bắt đầu ở ngăn nào? Vì sao có thể thất bại?

**Đáp án:** Bắt đầu ở ngăn `11 mod 8=3`, trong khi bản ghi vẫn ở ngăn `2`. Bảng không tự chuyển bản ghi khi một thuộc tính khóa thay đổi.

**Câu 2.** Điều kiện `a == b => hash(a) == hash(b)` có nghĩa mọi khóa có cùng hash đều bằng nhau không?

**Đáp án:** Không. Điều kiện chỉ đi từ **khóa bằng nhau** đến **mã băm bằng nhau**. Các khóa khác nhau có thể có cùng mã băm hoặc cùng ngăn.

**Câu 3.** Một đối tượng được dùng làm khóa có thuộc tính `id` và `ten_hien_thi`, nhưng cả `hash` lẫn `equals` chỉ dựa vào `id`. Sửa `ten_hien_thi` có làm hỏng bảng không?

**Đáp án:** Thông thường không, vì thay đổi đó không làm đổi mã băm hoặc quan hệ bằng nhau của khóa. Sửa `id` khi khóa còn trong bảng mới là hành động nguy hiểm.

**Câu 4.** Tại sao thao tác `remove(k)` sau khi đã sửa trường định danh của `k` có thể không xóa được bản ghi cũ?

**Đáp án:** Vì `remove` cũng phải tính vị trí hoặc dãy thăm dò từ hash **hiện tại** của khóa; nó có thể đi tới vị trí khác với nơi bản ghi đã được lưu.

**Câu 5.** Nếu hai khóa ban đầu khác nhau nhưng sau khi sửa một khóa chúng trở nên bằng nhau, bảng có thể gặp lỗi gì ngoài tìm không thấy?

**Đáp án:** Có thể có **hai bản ghi cùng khóa logic** ở hai vị trí khác nhau, cập nhật/xóa không nhất quán và giá trị trả về phụ thuộc vị trí được tìm thấy.

**Câu 6.** Khi cần thay mã đơn hàng, vì sao dùng một đối tượng khóa mới bất biến rồi chuyển bản ghi từ khóa cũ sang khóa mới thường an toàn hơn việc sửa trực tiếp đối tượng đang được dùng làm khóa?

**Đáp án:** Vì `remove(old_key)` dùng danh tính cũ còn hợp lệ để lấy bản ghi ra; `put(new_key, value)` cho bảng tự tính vị trí mới và kiểm tra xung đột. Không có giai đoạn khóa đang lưu nhưng hash đã đổi.

**Ghi nhớ:** Bảng băm định vị bản ghi dựa trên **mã băm và quan hệ bằng nhau của khóa**. Khi thuộc tính quyết định danh tính bị thay đổi **sau khi chèn**, bản ghi có thể còn trong bộ nhớ nhưng không tìm, sửa hoặc xóa được qua API thông thường; thậm chí sinh khóa trùng logic. Cách phòng ngừa hiệu quả nhất là **khóa có danh tính bất biến**, chỉ thay đổi `value` hoặc những thuộc tính không tham gia hash/equality; nếu thật sự cần đổi khóa, hãy **xóa theo khóa cũ trước, rồi chèn lại theo khóa mới** với quy tắc xử lý xung đột rõ ràng.
