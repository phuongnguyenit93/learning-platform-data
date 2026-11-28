# Phân biệt cấu trúc bất biến với một khung nhìn chỉ đọc

Một hệ thống học tập lưu điểm thi trong một `dict` và cung cấp cho giao diện báo cáo một **khung nhìn chỉ đọc** (*read-only view*). Giao diện không thể gọi thao tác sửa qua khung nhìn đó. Tuy nhiên, khi giáo vụ cập nhật `dict` gốc, báo cáo vẫn nhìn thấy điểm mới. Điều này có mâu thuẫn với khái niệm **bất biến** (*immutable*) không?

Không. **Không cho sửa qua một giao diện** khác với **bảo đảm trạng thái được quan sát sẽ không thay đổi**. Một khung nhìn chỉ đọc có thể là một **cửa sổ sống** (*live view*) trên dữ liệu mutable; còn một cấu trúc dữ liệu bất biến được thiết kế để trạng thái thuộc phiên bản của chính nó không bị sửa tại chỗ. Nếu cấu trúc ngoài bất biến nhưng chứa phần tử mutable, sự ổn định cũng còn phụ thuộc vào **các đối tượng bên trong**.

Bài thuộc chương **Bất biến và phiên bản** trong module **Cấu trúc dữ liệu**. Ta sẽ phân biệt rõ **read-only view**, **immutable collection**, **shallow/deep immutability**, **snapshot** và **persistent version**; cài đặt ví dụ Python, so sánh một số API phổ biến, phân tích độ phức tạp và xây hợp đồng/kiểm thử để chọn cách cung cấp dữ liệu phù hợp.

## 1. Hai câu hỏi độc lập: “ai được sửa?” và “dữ liệu có thể đổi không?”

Hãy đặt riêng hai câu hỏi:

1. **Qua tham chiếu đang cầm, người gọi có được phép sửa dữ liệu không?**
2. **Có bất kỳ đường tham chiếu hợp lệ nào khác có thể làm dữ liệu người gọi quan sát bị thay đổi không?**

Câu hỏi thứ nhất nói về **khả năng ghi qua một giao diện** (*write capability*). Câu hỏi thứ hai nói về **khả năng thay đổi của trạng thái được quan sát** (*mutability of observed state*).

Ví dụ:

```text
          chủ sở hữu dữ liệu
                 │
                 ▼
        mutable dictionary  ◄──── sửa trực tiếp
                 │
                 │ tạo view
                 ▼
        read-only interface ──► người đọc

Người đọc không thể sửa mapping qua interface,
nhưng vẫn thấy thay đổi của dictionary nguồn.
```

**Tính chất read-only là tương đối với một đường truy cập**: “qua giao diện này, không có thao tác ghi được công bố”. Nó **không tự nói rằng toàn bộ dữ liệu trong hệ thống không còn thay đổi**.

Ngược lại, một đối tượng bất biến có thể được nhiều người tham chiếu mà không ai được sửa chính đối tượng ấy tại chỗ theo hợp đồng. Nếu muốn “cập nhật”, chương trình tạo đối tượng/phiên bản mới.

## 2. Định nghĩa các thuật ngữ cốt lõi

| Thuật ngữ | Ý nghĩa cần nhớ |
| --- | --- |
| **Mutable structure** | Cấu trúc hỗ trợ sửa trạng thái tại chỗ: thêm, xóa, gán lại phần tử/liên kết |
| **Read-only view** | Một giao diện quan sát, không công bố thao tác sửa **qua view** |
| **Live view** | View phản ánh trạng thái hiện tại của nguồn; nguồn đổi thì dữ liệu thấy qua view có thể đổi |
| **Immutable structure** | Cấu trúc không cho thay đổi trạng thái thuộc đối tượng/phiên bản sau khi tạo, theo hợp đồng |
| **Shallow immutability** | Lớp ngoài không đổi, nhưng phần tử được tham chiếu bên trong có thể mutable |
| **Deep/transitive immutability** | Trạng thái được bảo vệ khỏi sửa tại chỗ trên toàn bộ phần đồ thị đối tượng thuộc phạm vi hợp đồng |
| **Snapshot** | Ảnh chụp của một trạng thái tại thời điểm/phiên bản xác định |
| **Persistent data structure** | Cập nhật tạo phiên bản mới và giữ được các phiên bản cũ còn được tham chiếu |

Hai điều **không đồng nghĩa**:

- Một view chỉ đọc **không nhất thiết** là snapshot.
- Một snapshot **không nhất thiết** là immutable: bản sao có thể hoàn toàn độc lập với nguồn nhưng bản thân nó vẫn sửa được.

Một cấu trúc bất biến **cấp ngoài** cũng không tự trở thành bất biến sâu nếu nó chứa tham chiếu tới đối tượng mutable.

## 3. Ma trận hai trục: giao diện và nguồn dữ liệu

Ta có thể phân loại theo **đường truy cập** và **khả năng thay đổi ở nguồn**:

| Nguồn được quan sát | Giao diện người dùng nhận | Điều có thể xảy ra |
| --- | --- | --- |
| Mutable | Có quyền ghi | Người dùng và chủ sở hữu có thể sửa cùng trạng thái |
| Mutable | **Chỉ đọc** | Người dùng không sửa qua view, **nhưng vẫn thấy nguồn đổi** |
| Immutable | **Chỉ đọc** | Nội dung phiên bản ổn định nếu cả phần tử thuộc phạm vi quan sát cũng ổn định |
| Snapshot độc lập nhưng mutable | Có quyền ghi | Người dùng có thể sửa **bản sao**, nguồn ban đầu không vì thế thay đổi |

**Trường hợp dễ nhầm nhất là hàng thứ hai**. Giao diện không có phương thức `append`, `set`, `delete` hay `put`; vậy mà hai lần đọc cùng khóa có thể trả kết quả khác nhau.

### Ví dụ hình dung

```text
Thời điểm t0:
    source = {"A": 8}
    view["A"] = 8

Thời điểm t1:
    source["A"] = 10
    view["A"] = 10

Không có thao tác write nào qua view,
nhưng nội dung đọc qua view đã thay đổi.
```

Ngữ nghĩa này **có thể hoàn toàn đúng thiết kế** nếu người dùng muốn một màn hình theo dõi dữ liệu hiện hành. Nó chỉ sai nếu API hứa hẹn **“báo cáo đã chốt không đổi”**.

## 4. Aliasing: cơ chế khiến view thay đổi dù không có setter

**Aliasing** nghĩa là nhiều tham chiếu dẫn tới cùng một đối tượng.

```python
scores = {"HV001": 8}
admin_reference = scores
report_reference = scores

assert admin_reference is report_reference

admin_reference["HV001"] = 9
assert report_reference["HV001"] == 9
```

Hai biến `admin_reference` và `report_reference` chỉ là **hai tên của cùng một dictionary**. Không có dữ liệu nào được sao chép khi ta gán một tham chiếu mới cho đối tượng đã tồn tại.

Một read-only view cũng có thể giữ **tham chiếu tới nguồn mutable**. View chỉ hạn chế các **thao tác được phép qua đường truy cập đó**, không cắt đứt alias với nguồn.

### Hình dung đồ thị tham chiếu

```text
admin  ────────────────┐
                       ▼
                  dict nguồn
                       ▲
                       │ tham chiếu được view bao bọc
report ──► read-only view
```

Chừng nào admin còn quyền sửa dictionary nguồn, dữ liệu mà report đọc từ view **không được bảo đảm bất biến theo thời gian**.

## 5. Python: MappingProxyType là live read-only view

Thư viện chuẩn Python có `types.MappingProxyType`, tạo một proxy chỉ đọc trên một mapping.

```python
from types import MappingProxyType

source = {
    "HV001": 8,
    "HV002": 9,
}

view = MappingProxyType(source)

assert view["HV001"] == 8

# Không được sửa mapping qua proxy.
try:
    view["HV001"] = 10
except TypeError:
    pass
else:
    raise AssertionError("Proxy phải chặn thao tác gán")

# Nhưng chủ sở hữu nguồn vẫn được sửa.
source["HV001"] = 10
source["HV003"] = 7

assert view["HV001"] == 10
assert view["HV003"] == 7

del source["HV002"]
assert "HV002" not in view
```

Có ba thao tác quan trọng:

1. `view["HV001"] = 10`: **bị từ chối** qua proxy.
2. `source["HV001"] = 10`: **được phép** qua dictionary nguồn.
3. `view["HV001"]` sau đó: **đọc giá trị mới**.

**Kết luận:** `MappingProxyType(source)` là **read-only view**, không phải snapshot độc lập, và không bảo đảm bất biến của nội dung mà người đọc thấy.

### Không lạm dụng kết luận “view bất biến”

Lệnh `view["HV001"] = 10` thất bại chỉ chứng minh **không sửa mapping qua view bằng thao tác đó**. Nó không chứng minh nguồn đã bị đóng băng và cũng không chứng minh các **giá trị** trong mapping là bất biến.

## 6. Khung nhìn keys/items của dict cũng phản ánh nguồn hiện hành

Python còn có các đối tượng `dict_keys`, `dict_values`, `dict_items` khi gọi `keys()`, `values()`, `items()`. Chúng biểu diễn **view** trên dictionary, không phải danh sách snapshot được chụp tự động.

```python
catalog = {"DS": "Cấu trúc dữ liệu"}
keys_view = catalog.keys()
items_view = catalog.items()

assert list(keys_view) == ["DS"]

catalog["ALG"] = "Giải thuật"

assert "ALG" in keys_view
assert len(keys_view) == 2
assert ("ALG", "Giải thuật") in items_view
```

Trạng thái của `keys_view` đổi theo `catalog` mà không cần tạo lại view.

### View và iterator không có cùng lời hứa

- **View:** đối tượng cho phép quan sát tập mục của nguồn, có thể **live**.
- **Iterator:** trạng thái duyệt từng phần tử; khi nguồn thay đổi trong lúc duyệt, hành vi phụ thuộc vào thiết kế thư viện.

Không được mặc định rằng vừa có view, vừa có một **snapshot ổn định cho toàn bộ lượt lặp**. Với dictionary Python, thay đổi kích thước trong lúc lặp có thể gây `RuntimeError`. Việc thư viện có phát hiện một số cập nhật **không biến view thành snapshot**.

## 7. Read-only ở cấp ngoài vẫn có thể lộ phần tử mutable

Một mapping proxy chặn phép gán lại khóa–giá trị, nhưng **không đóng băng đối tượng được lưu làm value**.

```python
from types import MappingProxyType

source = {
    "HV001": [8, 9],
}
view = MappingProxyType(source)

# Không thể gán lại view["HV001"].
try:
    view["HV001"] = [10]
except TypeError:
    pass

# Nhưng phần tử list vẫn sửa được qua đường view.
view["HV001"].append(10)

assert source["HV001"] == [8, 9, 10]

# Chủ nguồn cũng có thể sửa cùng list.
source["HV001"].append(7)
assert view["HV001"] == [8, 9, 10, 7]
```

Có **hai đường cập nhật** cần phòng ngừa:

- Cập nhật **cấu trúc mapping** từ chủ sở hữu nguồn.
- Cập nhật **đối tượng list được mapping tham chiếu**, thậm chí **qua chính view**.

Bởi vậy, nếu một API hứa dữ liệu **hoàn toàn không thể bị người nhận thay đổi**, chỉ bao bọc mapping ngoài bằng proxy là **chưa đủ**.

## 8. Tuple là immutable ở cấp ngoài, không đóng băng các phần tử

Tuple có các vị trí tham chiếu không thể được gán lại qua giao diện thông thường:

```python
grades = (8, 9, 10)

try:
    grades[0] = 7
except TypeError:
    pass

assert grades == (8, 9, 10)
```

Nhưng nếu tuple chứa list:

```python
groups = ([8, 9], [7])

try:
    groups[0] = [10]
except TypeError:
    pass

groups[0].append(10)
assert groups == ([8, 9, 10], [7])
```

**Kết luận:** tuple cung cấp **bất biến cấu trúc ngoài**, nhưng mức bất biến sâu phụ thuộc phần tử.

### Frozen dataclass cũng có giới hạn tương tự

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Report:
    course: str
    scores: list[int]


raw = [8, 9]
report = Report("DS", raw)

try:
    report.course = "ALG"
except AttributeError:
    pass

raw.append(10)
assert report.scores == [8, 9, 10]
```

`frozen=True` ngăn gán lại thuộc tính qua API thường dùng, **không tự cấm sửa list nằm trong trường `scores`**.

## 9. Snapshot khác live view ở điểm nào?

Một **snapshot** nhằm đại diện cho **trạng thái tại một thời điểm/phiên bản xác định**. Trong khi một **live view** được phép phản ánh các cập nhật sau đó của nguồn.

```text
Thời điểm t0:
    source = {"A": 8}

    live_view ───────► source

    snapshot = {"A": 8}   (bản sao độc lập cấp ngoài)

Thời điểm t1:
    source["A"] = 10

    live_view["A"] = 10
    snapshot["A"]  = 8
```

Ví dụ Python:

```python
from types import MappingProxyType

source = {"A": 8}
live = MappingProxyType(source)

copied = dict(source)
snapshot_outer = MappingProxyType(copied)

source["A"] = 10
source["B"] = 7

assert live["A"] == 10
assert "B" in live

assert snapshot_outer["A"] == 8
assert "B" not in snapshot_outer
```

Ở đây `snapshot_outer` chỉ là **snapshot cấp ngoài**, bởi `dict(source)` sao chép các **tham chiếu** trong mapping, không sao chép sâu đối tượng con.

Cũng cần lưu ý: nếu còn đường tham chiếu tới `copied` và chủ sở hữu khác sửa nó, `snapshot_outer` **sẽ phản ánh thay đổi của `copied`**. Thiết kế snapshot an toàn phải **kiểm soát quyền sở hữu** bản sao.

## 10. Snapshot nông vẫn có thể đổi nội dung lồng nhau

Giả sử nguồn là một dictionary lưu danh sách điểm:

```python
source = {
    "HV001": [8, 9],
}

outer_copy = dict(source)

assert outer_copy is not source
assert outer_copy["HV001"] is source["HV001"]

source["HV001"].append(10)

assert outer_copy["HV001"] == [8, 9, 10]
```

Bản sao dictionary **không cùng đối tượng** với dictionary gốc, nhưng hai dictionary vẫn trỏ tới **cùng một list**. Vì thế, sửa list nguồn làm nội dung quan sát từ bản sao đổi theo.

### Nhận biết ba tầng

| Tầng | Ví dụ | Cần bảo vệ điều gì? |
| --- | --- | --- |
| Cấu trúc ngoài | Dictionary khóa học | Thêm/xóa khóa, thay mapping |
| Phần tử con | List điểm | Sửa phần tử, thêm/xóa điểm |
| Đối tượng sâu hơn | Đối tượng học viên trong list | Sửa thuộc tính hoặc tham chiếu bên trong |

**Sao chép nông tách cấu trúc ngoài**; không bảo đảm mọi tầng còn lại độc lập. Ngay cả một bản sao sâu vẫn có thể mutable đối với **chính người cầm bản sao**, nếu API cho phép sửa.

## 11. Tạo snapshot bất biến đúng miền dữ liệu

Với miền dữ liệu:

```text
source: dict[str, list[int]]
```

ta có thể chuyển các list thành tuple và không lộ dictionary mới cho bên ngoài.

```python
from types import MappingProxyType


def make_score_snapshot(source):
    """Snapshot chỉ đọc cho dict[str, list[int]].

    Giả định keys là str, từng score là int bất biến,
    và nguồn không bị cập nhật đồng thời khi đang chụp.
    """
    copied = {
        student_id: tuple(scores)
        for student_id, scores in source.items()
    }
    return MappingProxyType(copied)


source = {
    "HV001": [8, 9],
    "HV002": [7],
}

stable = make_score_snapshot(source)

source["HV001"].append(10)
source["HV003"] = [5]

assert stable["HV001"] == (8, 9)
assert stable["HV002"] == (7,)
assert "HV003" not in stable

try:
    stable["HV001"] = (10,)
except TypeError:
    pass

try:
    stable["HV001"] += (10,)
except TypeError:
    pass
```

Trong phạm vi dữ liệu `str` và `int` được dùng như giá trị bất biến, snapshot trên bảo vệ **mapping ngoài** và **các dãy điểm** khỏi việc sửa thông thường qua những tham chiếu nguồn đã nêu.

### Tại sao cách này khác MappingProxyType(source)?

- `MappingProxyType(source)`: **view sống** trên dictionary gốc, dễ tạo nhưng phản ánh cập nhật.
- `MappingProxyType(dict(source))`: tách mapping cấp ngoài, nhưng vẫn chia sẻ các **value objects**.
- `MappingProxyType({k: tuple(v) ...})`: tách mapping, chuyển list điểm thành tuple, giúp dữ liệu trong miền ví dụ ổn định.

Cách dựng không tự “đóng băng” mọi đối tượng tùy ý. Nếu tuple chứa **đối tượng mutable**, người đọc vẫn có thể làm trạng thái bên trong đổi.

### Đặt tên API theo hợp đồng

Tên như `get_live_scores_view()` và `get_frozen_scores_snapshot()` diễn đạt chính xác hơn một tên chung chung `get_immutable_scores()` nếu nội dung bên trong khác nhau.

## 12. Sao chép sâu không tự đồng nghĩa với immutable

Python có `copy.deepcopy` để sao chép nhiều kiểu đồ thị đối tượng.

```python
from copy import deepcopy

source = {
    "HV001": {"grades": [8, 9]}
}

copy_deep = deepcopy(source)

assert copy_deep is not source
assert copy_deep["HV001"] is not source["HV001"]
assert (
    copy_deep["HV001"]["grades"]
    is not source["HV001"]["grades"]
)

source["HV001"]["grades"].append(10)
assert copy_deep["HV001"]["grades"] == [8, 9]

# Tuy nhiên bản sao vẫn mutable.
copy_deep["HV001"]["grades"].append(7)
assert copy_deep["HV001"]["grades"] == [8, 9, 7]
```

Phân biệt:

- **Deep copy:** tách biệt trạng thái của nhiều đối tượng con khỏi nguồn, tùy kiểu và cách sao chép.
- **Deep immutability:** ngăn thay đổi trạng thái của tất cả thành phần thuộc phạm vi hợp đồng sau khi tạo.

Một bản sao sâu **có thể được sửa** qua API của chính nó. Nếu cần dữ liệu lịch sử không thể bị sửa, phải thiết kế thêm giao diện bất biến, chuyển kiểu dữ liệu hoặc quyền sở hữu phù hợp.

**Không nên khẳng định** `deepcopy` luôn có thể sao chép đúng mọi tài nguyên (socket, file, database handle, khóa hệ thống, đối tượng tùy biến). Ngữ nghĩa và chi phí phụ thuộc đối tượng thực tế.

## 13. Read-only memoryview: không ghi qua view, buffer gốc vẫn sửa được

Không chỉ mapping mới có view chỉ đọc. Python có `memoryview` để nhìn vào **buffer** mà không nhất thiết sao chép dữ liệu.

```python
buffer = bytearray(b"ABC")
view = memoryview(buffer).toreadonly()

assert view.readonly is True
assert bytes(view) == b"ABC"

try:
    view[0] = ord("Z")
except TypeError:
    pass

# Buffer gốc vẫn có thể sửa trong cùng kích thước.
buffer[0] = ord("Z")

assert bytes(view) == b"ZBC"

# Chủ động giải phóng view khi không còn dùng.
view.release()
```

**Read-only không tự tạo một bản sao buffer.** Phép thay đổi ở nguồn có thể xuất hiện ngay khi đọc qua view.

### Giới hạn quan trọng

- Không thể **gán qua view đã chuyển read-only**, nhưng có thể có tham chiếu ghi tới buffer gốc.
- Các API buffer có quy định riêng về quyền thay đổi kích thước khi đang có exported views; ví dụ `bytearray` có thể chặn một số thao tác resize.
- Ngữ nghĩa buffer, slicing và vòng đời `memoryview` không giống hệt dictionary proxy.

Ví dụ này minh họa một nguyên tắc rộng hơn: **view chỉ đọc và dữ liệu bất biến là hai đặc tính khác nhau**, không riêng cho Python dictionary.

## 14. View sống có thể là lựa chọn tốt

Không phải cứ live view là lỗi thiết kế. Nó hữu ích khi mục tiêu là **phản ánh trạng thái hiện hành** nhưng hạn chế khả năng sửa của người đọc.

Ví dụ:

- Bảng điều khiển hiển thị số lớp học đang mở.
- Trang quan sát queue công việc do một dịch vụ khác quản lý.
- Khung nhìn thống kê các mã khóa hiện có.
- Màn hình giám sát số lượng bài kiểm tra trong một mapping được cập nhật.
- API chỉ muốn **một nguồn dữ liệu duy nhất**, không tốn sao chép toàn bộ mỗi lần đọc.

### Ưu điểm

- Có thể tạo view trong `O(1)` bằng cách bọc tham chiếu, tùy API.
- Không cần giữ một bản copy đầy đủ của dữ liệu.
- Đọc có thể thấy cập nhật mới mà không phải gọi phương thức dựng snapshot lại.

### Đánh đổi

- Giá trị quan sát phụ thuộc thời điểm đọc.
- Kết quả của hai lần đọc có thể khác nhau.
- Vòng lặp trên dữ liệu thay đổi có thể không ổn định hoặc gặp lỗi tùy API.
- Nếu lộ đối tượng con mutable, người gọi có thể sửa gián tiếp.
- Dễ làm người dùng hiểu nhầm rằng “read-only” đồng nghĩa với dữ liệu lịch sử đã chốt.

**Không phải view nào cũng live.** Có API cung cấp read-only view lên **một dữ liệu đã bất biến**, và khi đó kết quả đọc thực sự ổn định. Muốn biết, phải đọc hợp đồng **về backing data và phiên bản**, không suy chỉ từ tên “view”.

## 15. Cấu trúc immutable cũng có thể có nhiều phiên bản

Thay vì tạo view trên một đối tượng mutable, hệ thống có thể giữ các **phiên bản bất biến**.

Ví dụ rất đơn giản với tuple số nguyên:

```python
v0 = (10, 20)
v1 = v0 + (30,)
v2 = v1 + (40,)

assert v0 == (10, 20)
assert v1 == (10, 20, 30)
assert v2 == (10, 20, 30, 40)
```

`v1` và `v2` là các tuple mới; `v0` không đổi. Một **cấu trúc persistent** phát triển ý tưởng này bằng cách dùng **structural sharing** để tránh sao chép toàn bộ cấu trúc khi cập nhật.

### Snapshot khác view sống về phiên bản

```text
View sống:
       viewer ──► mutable state hiện tại
                      |
             sửa tại chỗ qua chủ sở hữu
                      ↓
                state mới

Phiên bản bất biến:
       reader A ──► root_v0
       reader B ──► root_v1

       root_v0 không bị sửa để tạo root_v1.
```

Gốc `root_v0` tiếp tục dẫn tới dữ liệu phiên bản cũ. Nếu phần tử được chia sẻ là **bất biến theo hợp đồng**, việc cập nhật `root_v1` không làm người đọc `root_v0` thấy giá trị khác.

### Đừng nhầm persistent với durability

**Persistent** trong cấu trúc dữ liệu là **giữ phiên bản cũ sau cập nhật**, không tự hứa dữ liệu đã được ghi bền xuống ổ đĩa hoặc có khả năng phục hồi sau khi tiến trình kết thúc.

## 16. Chia sẻ cấu trúc bất biến khác chia sẻ nguồn mutable

Một cấu trúc persistent có thể tái sử dụng **nhánh không đổi** giữa hai phiên bản:

```text
        v0                    v1
        A                     A'
       / \                   /  \
      B   C                 B    C'
                               /
                              X

B được chia sẻ: không tạo lại B, không sửa B.
```

Ý tưởng này chỉ an toàn khi **nhánh B không thể bị sửa tại chỗ** bởi một tham chiếu khác.

Ngược lại, khi view sống trỏ vào một mapping mutable:

```text
read_only_view ──► mutable_map
admin          ──► mutable_map
```

việc chia sẻ tham chiếu tồn tại nhưng **không giữ trạng thái cũ**: admin sửa map thì view đọc giá trị mới.

**Cùng là “chia sẻ”, nhưng hợp đồng về quyền sửa và lịch sử hoàn toàn khác nhau.**

## 17. Một API chỉ đọc trên đối tượng mutable: dễ lộ alias

Xét lớp tự viết:

```python
class CourseStore:
    def __init__(self):
        self._courses = []

    def add(self, name):
        self._courses.append(name)

    def get_courses_unsafe(self):
        # Trả thẳng list mutable nội bộ.
        return self._courses


store = CourseStore()
store.add("Cấu trúc dữ liệu")

external = store.get_courses_unsafe()
external.append("Môn lạ")

assert store.get_courses_unsafe() == [
    "Cấu trúc dữ liệu", "Môn lạ"
]
```

Dù lớp `CourseStore` không công bố `remove`, việc trả **list nội bộ** đã mở một đường sửa khác.

### Cải tiến 1: trả tuple snapshot cấp ngoài

```python
class CourseStoreWithSnapshot:
    def __init__(self):
        self._courses = []

    def add(self, name):
        self._courses.append(name)

    def get_snapshot(self):
        return tuple(self._courses)


store = CourseStoreWithSnapshot()
store.add("Cấu trúc dữ liệu")

old = store.get_snapshot()
store.add("Giải thuật")

assert old == ("Cấu trúc dữ liệu",)
assert store.get_snapshot() == (
    "Cấu trúc dữ liệu", "Giải thuật"
)
```

Trong ví dụ, phần tử là `str` bất biến nên tuple đủ để cho một snapshot ổn định.

### Cải tiến 2: view sống (cần tài liệu rõ)

Một lớp có thể thiết kế một **giao diện chỉ đọc** gọi vào `_courses` nội bộ mỗi khi người dùng hỏi `len` hoặc đọc một vị trí. Khi chủ sở hữu `CourseStore` thêm khóa học, view sẽ phản ánh khóa học mới. Đó cũng có thể là API hợp lý nếu tên và tài liệu nêu rõ **live view**, không giả là snapshot.

## 18. Những thao tác bất biến có thể cho người dùng cảm giác “đã sửa”

Một API của immutable collection có thể hỗ trợ các tên như:

```text
new_list = old_list.add(x)
new_map  = old_map.put(k, v)
new_tree = old_tree.insert(k)
```

Dù tên phương thức gợi một thao tác cập nhật, điều quan trọng là **đối tượng nào bị sửa**.

### Hai ngữ nghĩa trái ngược

```text
Mutable:
    list.add(x)
    list cũ đổi

Immutable/persistent:
    list2 = list.add(x)
    list cũ không đổi
    list2 chứa thay đổi
```

Nếu người dùng bỏ qua giá trị trả về của hàm cập nhật bất biến, thay đổi có thể **không được giữ lại**.

Ví dụ tuple:

```python
old = (1, 2)
new = old + (3,)

assert old == (1, 2)
assert new == (1, 2, 3)
```

Việc tạo một phiên bản mới không làm `old` biến thành phiên bản mới, và việc gán lại biến ngoài không thay đổi đối tượng cũ.

## 19. Java: unmodifiable view và bản sao unmodifiable

Trong Java, `Collections.unmodifiableList(backingList)` cung cấp **một view không cho sửa qua wrapper**. Nhưng nếu code khác còn tham chiếu tới `backingList`, nó vẫn có thể thay đổi nguồn.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>();
backing.add("DS");

List<String> view = Collections.unmodifiableList(backing);

// view.add("ALG"); // Ném UnsupportedOperationException.

backing.add("ALG");

assert view.size() == 2;
assert view.get(1).equals("ALG");
```

Từ `unmodifiable` ở đây mô tả **các thao tác qua wrapper**, không hàm ý backing list bất biến.

### List.copyOf tạo collection tách biệt về trạng thái ngoài

Ở Java hiện đại (Java 10+), `List.copyOf(...)` trả một list **unmodifiable** chứa các phần tử được sao chép theo thứ tự tại thời điểm gọi, với giả định đầu vào phù hợp và không thay đổi đồng thời khi sao chép.

```java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>();
source.add("DS");

List<String> frozenOuter = List.copyOf(source);
source.add("ALG");

assert frozenOuter.size() == 1;
assert frozenOuter.get(0).equals("DS");
```

Nếu các phần tử là đối tượng mutable, `List.copyOf` **không tự deep-copy các phần tử**. Ngoài ra, API này có quy tắc riêng về phần tử `null` (không chấp nhận), nên không thể xem nó là phép thay thế trực tiếp cho mọi collection bất kỳ.

### Phân biệt đúng ba trường hợp Java

- `Collections.unmodifiableList(backing)`: read-only **view**; backing đổi thì view có thể đổi.
- `List.copyOf(source)`: list unmodifiable với **cấu trúc ngoài** không đi theo những sửa đổi sau đó của list mutable nguồn.
- **Các phần tử trong cả hai**: nếu là mutable thì trạng thái của chúng vẫn có thể đổi, tùy ai nắm tham chiếu.

## 20. JavaScript và TypeScript: khóa quyền ghi có nhiều mức

**TypeScript** có kiểu như `Readonly<T>` và `readonly`, thường giúp trình kiểm tra kiểu chặn gán qua những tham chiếu được khai báo chỉ đọc. Nhưng kiểu của TypeScript **không tự đóng băng đối tượng JavaScript lúc chạy**.

```typescript
type Profile = {
  name: string;
  points: number[];
};

const original: Profile = {
  name: "An",
  points: [8, 9]
};

const readOnly: Readonly<Profile> = original;

// readOnly.name = "Bình"; // Lỗi kiểm tra kiểu.

original.name = "Bình";  // Hợp lệ qua alias mutable.

console.log(readOnly.name); // "Bình"
readOnly.points.push(10);   // Mảng lồng bên trong vẫn mutable.
```

**JavaScript `Object.freeze`** ngăn sửa các thuộc tính trực tiếp của đối tượng ở mức runtime theo cơ chế của JS, nhưng cũng **không tự đóng băng các đối tượng lồng nhau**.

```javascript
const data = {
  course: "DS",
  grades: [8, 9]
};

Object.freeze(data);

// Không thể gán lại data.course qua API thông thường
// của đối tượng đã freeze (có thể lỗi trong strict mode).

data.grades.push(10);
console.log(data.grades); // [8, 9, 10]
```

Để có deep immutability thực sự, cần thiết kế **giá trị bên trong** và/hoặc thuật toán freeze đệ quy phù hợp với kiểu dữ liệu, vòng tham chiếu, object đặc biệt và hợp đồng runtime.

**Nhớ:** compile-time readonly, runtime shallow freeze, unmodifiable wrapper và snapshot độc lập là **những biện pháp khác nhau**.

## 21. C++ const cũng phụ thuộc đường tham chiếu và kiểu dữ liệu

Trong C++, `const` giúp giới hạn những thao tác sửa qua một đường truy cập nhất định. Tuy nhiên, **không nên đồng nhất nó với bảo đảm deep immutability tổng quát**.

Ví dụ một con trỏ hằng trỏ tới dữ liệu mutable khác với một con trỏ tới dữ liệu được xem là hằng:

```cpp
int x = 10;

int* const fixed_pointer = &x;
// fixed_pointer không được gán sang địa chỉ khác.
*fixed_pointer = 20; // x vẫn đổi được.

const int* read_only_pointer = &x;
// *read_only_pointer = 30; // Không cho sửa qua con trỏ này.

x = 40; // Vẫn sửa được qua tham chiếu mutable x.
```

Điều quan trọng:

- **Không được đổi con trỏ** khác với **không được đổi đối tượng được trỏ tới**.
- Một đường đọc `const` không loại bỏ những alias mutable hợp lệ khác.
- Những cấu trúc có con trỏ, container và tài nguyên bên ngoài còn cần xét **quy tắc constness/ownership riêng**.

Ta không dùng ví dụ `const_cast` phá rào chắn, vì mục tiêu là hiểu **hợp đồng truy cập**, không phải tìm cách vượt API.

## 22. Snapshot trong hệ thống đồng thời cần nhất quán khi chụp

Ngay cả khi tạo một bản sao rồi đóng băng nó, **quá trình lấy dữ liệu nguồn** có thể không nhất quán nếu nguồn bị cập nhật đồng thời.

Giả sử báo cáo gồm hai trường liên quan:

```text
course_count = 3
total_students = 100
```

Người ghi cập nhật cả hai trường để biểu diễn cùng một trạng thái mới. Nếu bên đọc lấy `course_count` **trước** khi ghi và `total_students` **sau** khi ghi, bản sao có thể chứa hai giá trị đến từ **hai thời điểm khác nhau**.

Một khi bản sao bị đóng băng, nó sẽ **ổn định**, nhưng có thể ổn định ở một trạng thái **không từng tồn tại như một phiên bản nghiệp vụ hợp lệ**.

### Hai yêu cầu riêng

1. **Immutability sau khi tạo:** không ai sửa bản snapshot qua API sau khi công bố.
2. **Snapshot consistency lúc tạo:** toàn bộ dữ liệu được lấy từ một trạng thái/phiên bản nhất quán.

Muốn bảo đảm điều thứ hai, hệ thống có thể cần khóa, transaction, versioning, MVCC hoặc cơ chế snapshot chuyên biệt. Không phải chỉ gọi `dict(source)` trong bối cảnh có cập nhật đồng thời là tự có tính nguyên tử.

### View và nhiều lần đọc

Read-only live view càng không tự bảo đảm hai lần đọc liên tiếp thuộc cùng phiên bản. Nếu cần báo cáo tài chính, điểm thi đã chốt hay kết quả kiểm toán, phải xác định yêu cầu **cố định phiên bản** thay vì chỉ **cấm người đọc ghi**.

## 23. Thread safety không suy ra từ từ “read-only”

Một API cung cấp read-only view không có nghĩa mọi thao tác đọc sẽ an toàn khi nguồn bị sửa từ một luồng khác.

Cần phân biệt:

- **Khả năng sửa qua view:** bị chặn hoặc không.
- **An toàn của cập nhật đồng thời nguồn:** phụ thuộc cấu trúc và mô hình đồng bộ.
- **Tính nhất quán nhiều lần đọc:** cần chính sách phiên bản/snapshot.
- **Tính ổn định của phần tử:** phụ thuộc phần tử có mutable và bị sửa không.
- **Công bố snapshot tới luồng khác:** phụ thuộc mô hình bộ nhớ của ngôn ngữ/runtime.

Một cấu trúc bất biến sâu sau khi đã được **công bố an toàn** giúp giảm nhu cầu khóa bảo vệ chính nội dung của phiên bản trong quá trình đọc. Nhưng việc **đổi tham chiếu `current_version`**, gộp cập nhật hoặc xử lý nhiều người ghi vẫn là một bài toán đồng bộ riêng.

**Kết luận:** read-only là một thuộc tính quyền truy cập; thread safety là một thuộc tính hành vi **trong môi trường đồng thời**. Không được suy trực tiếp thuộc tính thứ hai từ thuộc tính thứ nhất.

## 24. Chi phí thời gian và bộ nhớ của các lựa chọn

Gọi `n` là số phần tử cấp ngoài; `m` là tổng số phần tử/con đối tượng cần sao chép nếu xử lý sâu; `h` là chiều cao cấu trúc cây; `k` là số phần tử cần đọc.

| Phương án | Chi phí tạo điển hình | Bộ nhớ thêm | Đặc tính |
| --- | --- | --- | --- |
| Trả thẳng tham chiếu mutable | `O(1)` | `O(1)` | Người gọi có thể sửa nguồn |
| Tạo read-only proxy/view | Thường `O(1)` | Thường `O(1)` | **Không tách** nguồn mutable |
| `tuple(list)` | `O(n)` | `O(n)` | Snapshot vị trí ngoài, phần tử dùng chung |
| `dict.copy()` hoặc `dict(source)` | `O(n)` | `O(n)` | Snapshot mapping nông |
| `deepcopy` trên cây/đồ thị dữ liệu thông thường | Thường theo kích thước phần được sao chép | Tương ứng số đối tượng mới | Có thể tách các đối tượng mutable, nhưng vẫn mutable |
| Chuyển `dict[str,list[int]]` thành mapping proxy của tuple | `O(m+n)` với `m` là tổng điểm | `O(m+n)` | Snapshot ổn định cho miền `str/int` |
| Persistent BST path copying | `O(h)` mỗi cập nhật | `O(h)` nút mới | Chia sẻ nhánh bất biến giữa các phiên bản |
| Duyệt snapshot có `k` mục | `O(k)` | `O(1)` hoặc tùy iterator | Nội dung ổn định nếu snapshot đúng hợp đồng |

Bảng giả định phép so sánh/truy cập cơ bản có chi phí hằng số; `deepcopy` có thể đắt hơn khi các lớp tùy biến có logic riêng.

### Có nên luôn trả snapshot?

**Không nhất thiết.** Nếu dữ liệu nguồn có hàng triệu bản ghi và người dùng cần **xem hiện trạng mới nhất**, tạo bản sao toàn bộ mỗi lần có thể rất tốn kém.

Ngược lại, nếu báo cáo phải **tái lập được theo thời điểm**, chỉ trả live view có thể vi phạm hợp đồng. Khi cần vừa giữ nhiều phiên bản vừa tránh sao chép `O(n)` mỗi lần, hãy cân nhắc **persistent structure, MVCC hoặc cơ chế snapshot phù hợp** với môi trường.

### Chi phí ẩn

- Snapshot sâu phải duyệt các đối tượng con; có thể tạo nhiều cấp phát.
- View sống giữ tham chiếu tới dữ liệu nguồn, ảnh hưởng vòng đời bộ nhớ.
- Phiên bản persistent giữ các nút cũ còn được tham chiếu, có thể làm bộ nhớ tăng theo lịch sử.
- Các iterator bị giữ lâu có thể vô tình kéo dài vòng đời dữ liệu/phiên bản.
- Bọc view không tự khắc phục độ phức tạp kém của cấu trúc nền (ví dụ BST không cân bằng cao `n`).

## 25. Liên hệ cấu trúc dữ liệu: map, set, cây và đồ thị

Sự khác nhau giữa view và immutable ảnh hưởng đến nhiều cấu trúc:

### Map và set

- `map.keys()` hoặc một `keySet` view có thể phản ánh việc thêm/xóa khóa tại map nguồn.
- Một **immutable set version** cố định các thành viên của phiên bản.
- Nếu phần tử set là đối tượng mutable với thông tin hash/equality biến đổi, invariant bảng băm còn có thể bị phá.

### Cây tìm kiếm nhị phân

- Một **read-only wrapper** quanh BST mutable có thể không công bố `insert/delete` cho người đọc, nhưng writer sửa BST gốc thì phép tìm/duyệt sau đó có thể thấy khóa mới.
- Một **persistent BST version** tạo gốc mới và giữ gốc cũ; các nhánh không đổi có thể được chia sẻ an toàn.
- Nếu người đọc cần một lượt duyệt **tái lập đúng phiên bản**, gốc bất biến an toàn hơn một live wrapper không có cơ chế snapshot.

### Đồ thị

- View chỉ đọc của danh sách kề mutable có thể phản ánh đỉnh/cạnh mới do chủ sở hữu thêm.
- Bản copy nông của map đỉnh tới danh sách kề có thể vẫn chia sẻ **các list cạnh**.
- Muốn snapshot đồ thị nhất quán cần xác định đúng phạm vi **đỉnh, cạnh, thuộc tính và trạng thái liên quan**.

### Mảng và buffer

- `memoryview.toreadonly()` cấm ghi qua view, nhưng buffer gốc vẫn có thể thay đổi nội dung.
- Dữ liệu dạng bytes bất biến phù hợp khi cần một ảnh chụp byte ổn định đã được tách khỏi nguồn mutable.

**Nguyên tắc chung:** trạng thái nào được coi là thành phần của cấu trúc? Ai còn đường sửa tới trạng thái ấy? Hai câu hỏi này quyết định hợp đồng, không chỉ tên lớp.

## 26. Thiết kế API: ghi rõ live view hay snapshot

Hai tên API sau có thể được hiểu rất khác:

```text
get_current_courses_view()
get_courses_snapshot(version_id)
```

Một tài liệu API tốt nên nêu:

1. **Tính chất live/snapshot:** kết quả có phản ánh cập nhật sau thời điểm gọi không?
2. **Quyền ghi qua giao diện:** có phương thức sửa ngoài ý muốn không?
3. **Mức độ sâu:** phần tử bên trong có mutable không?
4. **Ownership:** ai giữ tham chiếu tới nguồn/bản sao?
5. **Độ nhất quán:** snapshot được chụp nhất quán bằng cơ chế nào?
6. **Iterator:** nếu dữ liệu nguồn đổi trong lúc duyệt, điều gì xảy ra?
7. **Phiên bản:** có giữ được lịch sử nếu cập nhật không?
8. **Hiệu năng:** tạo snapshot và đọc/duyệt tốn thời gian/bộ nhớ bao nhiêu?
9. **Đồng thời:** có bảo đảm nào khi nhiều luồng đọc/ghi?
10. **Vòng đời:** kết quả có làm dữ liệu nguồn hoặc phiên bản cũ tiếp tục tồn tại trong bộ nhớ không?

### Ví dụ hai hợp đồng API rõ ràng

**API A – view sống:**

```text
get_current_scores_view():
- Trả giao diện chỉ đọc của mapping hiện hành.
- Không cho sửa mapping qua view.
- Thay đổi của chủ sở hữu nguồn có thể được nhìn thấy.
- Phần tử nếu mutable có thể cần hợp đồng riêng.
- Không bảo đảm snapshot nhất quán cho nhiều lần đọc.
```

**API B – snapshot phiên bản:**

```text
get_final_scores_snapshot():
- Trả trạng thái điểm đã chốt của một phiên bản.
- Không cho sửa mapping hay dãy điểm qua giao diện công bố.
- Không giữ alias mutable từ đầu vào trong phạm vi điểm số.
- Các cập nhật sau tạo phiên bản khác, không đổi phiên bản này.
- Thời điểm chụp và nhất quán khi chụp được quy định rõ.
```

Một API có thể thực hiện **cả hai** để phục vụ hai nhóm nhu cầu.

## 27. Kiểm thử để phân biệt read-only view với immutable snapshot

Tập kiểm thử nên kiểm tra **hành vi theo thời gian**, không chỉ kiểm tra “gọi setter có bị lỗi không?”.

### Test 1: không sửa qua view

```python
from types import MappingProxyType

source = {"A": 1}
view = MappingProxyType(source)

try:
    view["A"] = 2
except TypeError:
    pass
else:
    raise AssertionError("View không được hỗ trợ ghi")
```

### Test 2: view vẫn thấy nguồn thay đổi

```python
source["A"] = 3
source["B"] = 4

assert view["A"] == 3
assert "B" in view
```

### Test 3: snapshot không đi theo sửa đổi của nguồn

```python
data = {"HV001": [8, 9]}
snapshot = make_score_snapshot(data)

data["HV001"].append(10)
data["HV002"] = [7]

assert snapshot["HV001"] == (8, 9)
assert "HV002" not in snapshot
```

### Test 4: không sửa phần tử bên trong snapshot

```python
try:
    snapshot["HV001"][0] = 100
except TypeError:
    pass
else:
    raise AssertionError("Tuple điểm không được sửa tại chỗ")
```

### Test 5: thử giá trị mutable nếu hợp đồng chưa đóng băng

```python
from types import MappingProxyType

raw = {"A": [1]}
weak_view = MappingProxyType(raw)

weak_view["A"].append(2)

assert raw["A"] == [1, 2]
```

Test 5 **cố ý biểu diễn một điểm yếu** của chỉ-read-only cấp ngoài; không được xem việc list thay đổi là kết quả “an toàn”.

### Test 6: giữ phiên bản cũ sau cập nhật

```python
v0 = (10, 20)
v1 = v0 + (30,)

assert v0 == (10, 20)
assert v1 == (10, 20, 30)
```

Tập test nên phản ánh đúng **hợp đồng phiên bản**, không chỉ kiểu trả về.

## 28. Những lỗi thường gặp

1. **“Không sửa qua view được, vậy dữ liệu đã immutable.”** Nguồn có thể mutable và bị sửa qua alias khác.
2. **Gọi live view là snapshot.** View có thể phản ánh thay đổi sau thời điểm tạo.
3. **Chỉ copy mapping ngoài nhưng vẫn chia sẻ list giá trị.** Snapshot nông không bảo vệ dữ liệu lồng nhau.
4. **Tưởng `MappingProxyType(source)` sao chép dictionary.** Nó tạo một read-only proxy tới nguồn.
5. **Tưởng `dict.copy()` tạo các object con mới.** Chỉ sao chép các tham chiếu cấp ngoài.
6. **Tưởng `deepcopy` làm đối tượng được đóng băng.** Bản sao vẫn có thể mutable.
7. **Tưởng tuple không thể chứa list.** Tuple chỉ giữ nguyên các vị trí tham chiếu.
8. **Tưởng frozen dataclass tự đóng băng trường list.** Phần tử vẫn mutable.
9. **Trả thẳng list nội bộ rồi nghĩ đã che quyền ghi do lớp không có setter.** Người gọi có thể sửa qua alias.
10. **Dùng `dict.keys()` như danh sách snapshot.** Đây là một view có thể theo nguồn.
11. **Dùng `memoryview.toreadonly()` rồi khẳng định bytes buffer gốc bất biến.** Buffer có thể vẫn được sửa qua chủ sở hữu.
12. **Tưởng TypeScript `Readonly<T>` là runtime freeze.** Đây chủ yếu là ràng buộc cấp kiểu.
13. **Tưởng Java `Collections.unmodifiableList` tách backing list.** View có thể phản ánh thay đổi backing.
14. **Tưởng `Object.freeze` đóng băng mọi object con.** Freeze thông thường là nông.
15. **Cho rằng snapshot đã bất biến thì lúc chụp chắc chắn nhất quán.** Cập nhật đồng thời có thể tạo bản sao từ nhiều thời điểm.
16. **Cho rằng read-only đồng nghĩa thread-safe.** Đồng thời phụ thuộc cả nguồn, công bố dữ liệu và iterator.
17. **Không xác định phạm vi snapshot:** mapping, value, thuộc tính sâu, tài nguyên ngoài có thể có bảo đảm khác nhau.
18. **Không kiểm soát quyền sở hữu bản copy rồi công bố qua proxy.** Alias tới bản copy vẫn có thể sửa dữ liệu.
19. **Giữ con trỏ tới đối tượng khóa mutable trong BST/hash map.** Có thể phá bất biến thứ tự/băm.
20. **Đánh đồng immutable với persistent và lưu bền trên đĩa.** Đây là những hợp đồng khác nhau.
21. **Bọc view trên dữ liệu có chi phí truy vấn cao rồi nghĩ thao tác đã nhanh hơn.** View không thay đổi độ phức tạp nền.
22. **Không kiểm thử cập nhật nguồn sau khi tạo kết quả.** Dễ bỏ sót sự khác biệt cơ bản giữa view sống và snapshot.

## 29. Tự luyện tập

**Bài 1.** Phân biệt “không được ghi qua giao diện” và “dữ liệu không thể thay đổi sau khi tạo”. Vì sao hai điều này không đồng nghĩa?

**Bài 2.** Với `source={"A":1}` và `view=MappingProxyType(source)`, sau `source["A"]=2`, `view["A"]` là bao nhiêu? Có được gán `view["A"]=3` không?

**Bài 3.** Một view chỉ đọc nhưng chứa giá trị `list[int]`. Người dùng có thể gọi `view["A"].append(9)` không? Hợp đồng nào chưa được bảo vệ?

**Bài 4.** So sánh `dict.keys()` với `list(dict.keys())` sau khi có khóa mới được thêm vào dictionary.

**Bài 5.** Với `t=([1,2], [3])`, tại sao `t[0]=[10]` thất bại nhưng `t[0].append(10)` thành công?

**Bài 6.** Vì sao `@dataclass(frozen=True)` có trường `scores: list[int]` vẫn không phải bất biến sâu?

**Bài 7.** Cho `copy=dict(source)` với `source={"A":[1]}`. Sau `source["A"].append(2)`, `copy["A"]` bằng gì? Vì sao?

**Bài 8.** Phân biệt `MappingProxyType(source)` và `MappingProxyType(dict(source))` trong trường hợp dictionary gốc thêm một khóa mới.

**Bài 9.** Nếu bản sao `dict(source)` vẫn chứa `list`, tại sao chưa đủ làm snapshot điểm đã chốt?

**Bài 10.** Thiết kế snapshot ổn định cho dữ liệu `dict[str,list[int]]` và ghi rõ giả định về kiểu phần tử, quyền sở hữu và cập nhật đồng thời.

**Bài 11.** `deepcopy` có tự tạo immutable object không? Hãy cho ví dụ.

**Bài 12.** `memoryview(bytearray).toreadonly()` cấm loại thao tác nào, và vì sao dữ liệu qua view vẫn có thể đổi?

**Bài 13.** Khi nào live read-only view là một lựa chọn tốt hơn snapshot toàn bộ?

**Bài 14.** Vì sao snapshot bất biến được tạo từ các trường đang bị writer sửa đồng thời có thể **không nhất quán ngay từ lúc chụp**?

**Bài 15.** So sánh Java `Collections.unmodifiableList(source)` với `List.copyOf(source)` khi source thay đổi sau đó. Cả hai đã deep-freeze phần tử chưa?

**Bài 16.** Khác biệt giữa `Readonly<T>` của TypeScript và `Object.freeze` của JavaScript? Hai cách này có bảo đảm bất biến sâu không?

**Bài 17.** Một persistent BST giữ `root_v0` khi tạo `root_v1`. Điều gì giúp reader của `root_v0` không thấy khóa mới như một live view của BST mutable?

**Bài 18.** Vì sao một đối tượng được chia sẻ giữa các phiên bản phải có hợp đồng về payload, không chỉ về liên kết nút?

**Bài 19.** Phân tích chi phí tạo read-only proxy, snapshot nông và snapshot đầy đủ phù hợp miền `dict[str,list[int]]` với `n` khóa, tổng `m` điểm.

**Bài 20.** Đề xuất hai tên API và mô tả hợp đồng cho chức năng “theo dõi điểm đang cập nhật” và chức năng “xuất điểm kỳ thi đã chốt”.

**Bài 21.** Một nút BST được giữ nguyên vị trí nhưng người khác sửa thuộc tính dùng làm khóa. Bất biến cấu trúc nào có thể bị phá? Read-only view quanh cây có ngăn được điều đó không?

**Bài 22.** Viết bốn test chứng minh: view chặn ghi qua proxy, view vẫn thấy sửa nguồn, snapshot giữ dữ liệu cũ, phần tử trong snapshot không bị sửa qua người đọc.

<details>
<summary>Đáp án và gợi ý</summary>

1. Read-only giới hạn thao tác trên **một đường tham chiếu**. Dữ liệu còn có thể bị sửa qua chủ sở hữu hoặc alias khác; immutable yêu cầu trạng thái thuộc đối tượng/phiên bản không sửa tại chỗ theo hợp đồng.
2. `view["A"]==2` vì proxy là live view. Gán `view["A"]=3` bị `TypeError`.
3. Nếu API trả list mutable, `append` có thể sửa chính list nguồn; view chỉ bảo vệ mapping ngoài, không bảo vệ phần tử sâu.
4. `dict.keys()` là view sống nên có thể thấy khóa mới; `list(dict.keys())` tạo danh sách các khóa tại thời điểm gọi và không tự thêm khóa mới sau đó. Danh sách này bản thân vẫn mutable.
5. Tuple không cho gán lại tham chiếu tại chỉ số, nhưng list tại chỉ số đó vẫn là đối tượng mutable.
6. `frozen=True` cấm gán lại thuộc tính qua giao diện thông thường, không chặn thay đổi đối tượng list được tham chiếu.
7. `copy["A"] == [1,2]` vì `dict(source)` tạo mapping ngoài mới nhưng giữ cùng list.
8. `MappingProxyType(source)` thấy cả khóa mới; `MappingProxyType(dict(source))` không theo việc thêm khóa vào source, vì proxy trỏ tới bản copy cấp ngoài. Tuy nhiên value mutable vẫn có thể bị chia sẻ.
9. Các list con vẫn có thể đổi sau khi snapshot được dựng; cần copy/chuyển chúng sang biểu diễn bất biến và kiểm soát alias.
10. Tạo `MappingProxyType({k:tuple(v) for k,v in source.items()})`, với `k` là `str`, phần tử `int` bất biến, không lộ dictionary mới và nguồn ổn định trong lúc chụp hoặc được đồng bộ.
11. Không. `deepcopy({"A":[1]})` tạo dictionary/list mới, nhưng người cầm bản sao vẫn gọi `append` vào list được.
12. Cấm ghi qua view read-only. `bytearray` nguồn vẫn có thể sửa các byte trong phạm vi hợp lệ nên `bytes(view)` có thể khác.
13. Khi cần dữ liệu mới nhất với chi phí tạo view nhỏ, không cần lưu lịch sử, người đọc không được phép sửa và hành vi thay đổi khi duyệt đã được quy định.
14. Người đọc có thể chụp một số trường trước cập nhật và một số trường sau cập nhật; bản sao ổn định nhưng không đại diện một trạng thái nghiệp vụ nguyên tử.
15. `Collections.unmodifiableList(source)` là wrapper view, có thể phản ánh sửa nguồn; `List.copyOf(source)` tách membership/positions khỏi sửa đổi sau đó của list mutable nguồn. Cả hai đều không deep-copy các đối tượng con mutable.
16. `Readonly<T>` là ràng buộc cấp kiểu, không tự khóa runtime; `Object.freeze` tác động runtime tới thuộc tính trực tiếp, nhưng không tự đóng băng sâu. Hai cách không tự bảo đảm deep immutability.
17. Update persistent tạo root/nút mới và không sửa nút cũ; reader giữ `root_v0` vẫn thấy trạng thái cũ, với điều kiện phần tử chia sẻ ổn định.
18. Nếu payload là mutable list, sửa list qua một alias sẽ làm mọi phiên bản chia sẻ payload quan sát nội dung mới, phá lịch sử dù liên kết nút không đổi.
19. Proxy thường `O(1)` thời gian/bộ nhớ tạo; sao chép nông dict `O(n)`; tạo mapping mới có tuple các điểm `O(n+m)` thời gian và bộ nhớ, chưa tính chi phí đồng bộ.
20. `get_live_scores_view()`: chỉ đọc qua interface nhưng theo nguồn cập nhật. `get_final_scores_snapshot()`: kết quả độc lập với thay đổi sau đó của nguồn, phần tử điểm bất biến và có hợp đồng consistency.
21. Vị trí khóa có thể vi phạm quy tắc toàn bộ cây con trái nhỏ hơn và cây con phải lớn hơn, làm tìm kiếm sai. Read-only view không ngăn chủ sở hữu hoặc alias sửa đối tượng khóa.
22. Dùng `MappingProxyType` thử gán (phải lỗi), sửa `source` rồi đọc view (thấy mới), tạo `make_score_snapshot` rồi sửa nguồn (snapshot không đổi), thử gán mapping/tuple bên trong (phải lỗi).

</details>

## Ghi nhớ

**Read-only view chỉ chặn thao tác ghi qua một giao diện; nó không tự làm dữ liệu nguồn thành bất biến.** Một **live view** như `MappingProxyType(source)` có thể phản ánh thay đổi của dictionary nguồn và vẫn để lộ các value mutable. **Immutable structure** bảo vệ trạng thái thuộc một đối tượng/phiên bản sau khi tạo, nhưng **bất biến cấp ngoài chưa đủ** nếu có list/dict mutable bên trong. **Snapshot** là trạng thái ở một thời điểm, còn **persistent version** giữ trạng thái cũ khi cập nhật tạo phiên bản mới; cả hai cần chính sách rõ về **độ sâu, alias, ownership, tính nhất quán khi chụp và chia sẻ phần tử**. Khi chọn giải pháp, hãy hỏi riêng: **“người đọc có được ghi không?”, “nguồn có còn đổi không?” và “lần đọc này thuộc phiên bản nào?”**.
