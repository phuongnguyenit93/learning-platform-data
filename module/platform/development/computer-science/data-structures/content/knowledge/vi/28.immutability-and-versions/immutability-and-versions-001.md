# Bất biến của cấu trúc sau khi tạo và bất biến của các phần tử bên trong

Một ứng dụng học tập lưu lịch sử điểm trong danh sách `scores`. Để tránh làm thay đổi lịch sử sau khi công bố kết quả, lập trình viên chuyển danh sách ấy thành một **tuple** và gọi đó là “dữ liệu bất biến”. Nhưng nếu tuple chứa **danh sách các điểm theo từng bài**, các danh sách bên trong vẫn có thể thay đổi. Khi đó, **cấu trúc ngoài không đổi** nhưng **dữ liệu quan sát được qua cấu trúc lại đổi**.

Đây là sự phân biệt quan trọng của chương **Bất biến và phiên bản** trong module **Cấu trúc dữ liệu**: **bất biến của cấu trúc sau khi tạo** (*structural immutability*) không tự động kéo theo **bất biến của các phần tử bên trong** (*deep/transitive immutability*). Sự khác nhau ảnh hưởng tới mảng, danh sách liên kết, stack, map, set, cây, đồ thị, lịch sử phiên bản, chia sẻ bộ nhớ và an toàn khi đọc đồng thời.

Bài này làm rõ các mức độ bất biến, vai trò của tham chiếu và alias, snapshot với view, sao chép nông/sâu, kỹ thuật dựng dữ liệu bất biến và chia sẻ cấu trúc giữa các phiên bản. Ta dùng Python để minh họa những trường hợp dễ hiểu sai, sau đó liên hệ độ phức tạp thời gian – bộ nhớ khi chọn cấu trúc phù hợp.

## 1. Hai nghĩa của “bất biến” cần phân biệt

Trong tiếng Việt, từ **bất biến** có thể mô tả hai ý khác nhau:

1. **Invariant (điều kiện bất biến):** một quy tắc luôn phải đúng ở những trạng thái hợp lệ của cấu trúc, ví dụ mọi khóa trong cây con trái của BST nhỏ hơn khóa ở gốc.
2. **Immutability (không thể thay đổi):** sau khi một đối tượng được tạo, một phần trạng thái hoặc toàn bộ trạng thái của đối tượng **không còn được sửa tại chỗ** qua API được cho phép.

Ví dụ, một **BST có thể thay đổi** vẫn giữ được *invariant* về thứ tự khóa sau mỗi thao tác chèn/xóa hợp lệ. Ngược lại, một đối tượng **bất biến** vẫn có thể được tạo ra với nội dung sai quy tắc nếu hàm khởi tạo không kiểm tra dữ liệu đầu vào.

Bài này chủ yếu nói về nghĩa thứ hai: **immutability**. Ta vẫn đề cập các điều kiện invariant khi cần giải thích vì sao một cấu trúc chứa phần tử bị sửa có thể trở nên không nhất quán.

### Ba câu hỏi để xác định tính bất biến

Khi đánh giá một cấu trúc, hãy hỏi riêng:

- **Khung chứa có đổi được không?** Có thể thêm/xóa vị trí, thay liên kết con, thay phần tử ở chỉ số, thêm/xóa khóa?
- **Bản thân phần tử có đổi được không?** Một phần tử có thể là đối tượng mutable như `list`, `dict`, hồ sơ có thuộc tính sửa được.
- **Có tham chiếu bên ngoài đến các phần tử ấy không?** Nếu có, ai khác có thể sửa chúng sau khi cấu trúc đã được tạo?

Chỉ khi trả lời cả ba, ta mới hiểu “không thể thay đổi” được bảo đảm ở mức nào.

## 2. Bất biến của cấu trúc: không sửa hình dạng hoặc quan hệ chứa

**Bất biến cấu trúc sau khi tạo** nghĩa là các thành phần quyết định cấu trúc chứa không bị sửa tại chỗ qua giao diện thiết kế.

Tùy kiểu dữ liệu, các thành phần đó có thể là:

| Kiểu cấu trúc | Những thay đổi thuộc phần cấu trúc |
| --- | --- |
| Mảng/danh sách | Thêm/xóa phần tử, đổi vị trí chứa, thay tham chiếu tại một chỉ số |
| Stack/queue | `push/pop`, `enqueue/dequeue` làm thay đổi tập phần tử hoặc liên kết |
| Map | Thêm/xóa khóa, thay giá trị được ánh xạ tại khóa |
| Set | Thêm/xóa thành viên |
| Danh sách liên kết | Đổi `next`, thay `head`, nối/bỏ nút |
| Cây | Đổi `left/right`, thay `root`, gắn/tháo nút |
| Đồ thị | Thêm/xóa đỉnh, cạnh hoặc liên kết kề |

Ví dụ một tuple Python:

```python
positions = (10, 20, 30)

assert len(positions) == 3

try:
    positions[1] = 99
except TypeError:
    pass
else:
    raise AssertionError("Tuple không được gán lại phần tử")
```

Sau khi tạo `positions`, ta không thể gán một tham chiếu mới vào vị trí `1` của chính tuple đó. Điều này bảo vệ **cấu trúc ngoài** và các phần tử mà nó trực tiếp lưu theo cơ chế của tuple.

**Nhưng:** tuple lưu **tham chiếu đến đối tượng**. Nó không tự đóng băng mọi đối tượng được tham chiếu.

### Không nhầm với tên biến không thể gán lại

```python
original = (10, 20)
current = original

current = (10, 20, 30)

assert original == (10, 20)
assert current == (10, 20, 30)
```

Biến `current` được **gán sang một tuple mới**. Tuple `original` không bị thay đổi.

Bởi vậy:

> “Không đổi đối tượng” khác với “không được gán lại biến đang trỏ tới đối tượng”.

Tương tự, một tham chiếu `final` trong Java hoặc `const` trong JavaScript có quy tắc riêng về việc gán lại tham chiếu; điều đó **không tự biến đối tượng mà tham chiếu trỏ đến thành bất biến sâu**.

## 3. Bất biến của phần tử: nội dung bên trong có thể vẫn thay đổi

Xét một tuple chứa hai list:

```python
scores = ([8, 9], [7, 10])

# Không thể thay tham chiếu ở vị trí 0 của tuple:
try:
    scores[0] = [10, 10]
except TypeError:
    pass

# Nhưng vẫn sửa được danh sách đang nằm ở vị trí 0:
scores[0].append(10)

assert scores == ([8, 9, 10], [7, 10])
```

Ta không hề gán lại `scores[0]`. Thay vào đó, ta lấy **đối tượng list** mà `scores[0]` đang tham chiếu, rồi gọi thao tác thay đổi **trạng thái của list**.

Sơ đồ:

```text
scores (tuple)
  vị trí 0 ───────► list A: [8, 9]
  vị trí 1 ───────► list B: [7, 10]

Sau scores[0].append(10):

scores (vẫn cùng tuple)
  vị trí 0 ───────► list A: [8, 9, 10]  ← đổi nội dung
  vị trí 1 ───────► list B: [7, 10]
```

Tuple vẫn giữ **cùng hai tham chiếu ở cùng vị trí**, nhưng dữ liệu người đọc quan sát từ tuple đã thay đổi.

### Hai lớp bất biến khác nhau

- **Nông/cấp ngoài (*shallow immutability*):** không sửa được phần trực tiếp của đối tượng chứa, nhưng đối tượng con có thể mutable.
- **Sâu/bắc cầu (*deep/transitive immutability*):** toàn bộ trạng thái có thể quan sát qua đồ thị đối tượng được bảo vệ khỏi thay đổi tại chỗ, theo hợp đồng đã xác định.

Một cấu trúc bất biến nông không nhất thiết bất biến sâu.

## 4. Aliasing: nhiều đường tham chiếu tới cùng đối tượng

**Aliasing** xảy ra khi có từ hai tham chiếu cùng trỏ tới một đối tượng mutable.

```python
external = ["Toán", "Lý"]
catalog = (external,)

assert catalog[0] is external

external.append("Hóa")

assert catalog == (["Toán", "Lý", "Hóa"],)
```

Không có thao tác nào thay đổi tuple `catalog`. Tuy nhiên, vì `catalog[0]` và `external` là **hai đường tới cùng một list**, người dùng ở bên ngoài đã làm nội dung của `catalog` thay đổi theo góc nhìn quan sát.

Điều nguy hiểm hơn là alias có thể xuất hiện **gián tiếp**, qua nhiều tầng:

```text
report (tuple)
     │
     └──► Student (đối tượng có thể sửa)
                │
                └──► grades (list mutable)
```

Ngay cả khi không cho sửa chính đối tượng `Student`, nếu trường `grades` còn trỏ tới list mutable, dữ liệu điểm vẫn có thể bị thay đổi từ bên ngoài.

### Câu hỏi thiết kế

Khi một API nhận một phần tử đầu vào là mutable, nó phải xác định rõ:

1. **Giữ nguyên tham chiếu** tới phần tử, hay **sao chép** phần tử?
2. Nếu giữ tham chiếu, phần tử có được phép thay đổi không?
3. Khi tạo phiên bản mới, các phiên bản cũ có được phép **quan sát thay đổi về sau** của phần tử chung không?

Nếu mục tiêu là **lưu lịch sử bất biến**, việc giữ tham chiếu mutable không kiểm soát thường là thiết kế nguy hiểm.

## 5. “Không đổi trực tiếp” khác với “giá trị quan sát được không đổi”

Giả sử:

```python
student = {"name": "An", "grades": [8, 9]}

record = (student,)

before = record[0]["grades"][:]

student["grades"].append(10)

assert before == [8, 9]
assert record[0]["grades"] == [8, 9, 10]
```

Bản thân tuple `record` không đổi danh sách vị trí hoặc liên kết. Nhưng câu hỏi:

```text
"Điểm của An trong record là gì?"
```

có thể trả đáp án khác nhau ở hai thời điểm.

Với nhiều ứng dụng, **tính ổn định khi đọc lại** mới là điều quan trọng. Một cấu trúc chỉ bất biến cấp ngoài có thể không đủ đáp ứng yêu cầu đó.

### Mức bảo đảm nên được mô tả chính xác

| Mức bảo đảm | Điều được giữ nguyên | Điều chưa chắc giữ nguyên |
| --- | --- | --- |
| Chỉ không gán lại biến | Tên biến không được trỏ sang đối tượng khác | Đối tượng được tham chiếu vẫn mutable |
| Cấu trúc ngoài bất biến | Vị trí/liên kết trực tiếp không sửa tại chỗ | Trạng thái của phần tử mutable |
| Snapshot nông | Các liên kết trực tiếp trong bản sao không bị sửa theo bản gốc | Đối tượng con dùng chung |
| Bất biến sâu | Trạng thái có thể quan sát qua các thành phần theo hợp đồng không đổi | Trạng thái bên ngoài phạm vi hợp đồng |
| Persistent version với giá trị bất biến | Các phiên bản cũ giữ nguyên nội dung đã ghi nhận | Thay đổi của tài nguyên bên ngoài nếu vẫn tham chiếu đến nó |

Không có một từ “immutable” nào tự cho biết tất cả những điều trên nếu API không nêu **phạm vi bảo đảm**.

## 6. Frozen dataclass vẫn có thể chứa danh sách mutable

Python hỗ trợ `@dataclass(frozen=True)` để từ chối việc gán lại các trường theo giao diện thông thường.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Student:
    student_id: str
    grades: list[int]


grades = [8, 9]
student = Student("HV001", grades)

try:
    student.student_id = "HV999"
except AttributeError:
    pass
else:
    raise AssertionError("Không được sửa trường của frozen dataclass")

# Trường grades không thể gán sang list khác,
# nhưng chính list đang được tham chiếu vẫn mutable:
grades.append(10)

assert student.grades == [8, 9, 10]

student.grades.append(7)
assert grades == [8, 9, 10, 7]
```

Từ khóa `frozen=True` bảo vệ thao tác gán lại thuộc tính qua API thông thường của dataclass; nó **không tự đệ quy đóng băng mọi đối tượng ở các trường**.

### Phiên bản dùng phần tử bất biến

```python
@dataclass(frozen=True)
class FrozenStudent:
    student_id: str
    grades: tuple[int, ...]


raw_grades = [8, 9]
fixed = FrozenStudent("HV001", tuple(raw_grades))

raw_grades.append(10)

assert fixed.grades == (8, 9)

try:
    fixed.grades += (10,)
except AttributeError:
    pass
else:
    raise AssertionError("Trường grades không được gán lại")
```

Ở đây các điểm được biểu diễn bằng `int` (bất biến theo mô hình số nguyên Python) và `grades` là tuple. Việc thay đổi `raw_grades` bên ngoài không thể sửa tuple đã tạo.

**Lưu ý:** `frozen=True` không phải một cơ chế bảo mật chống mọi cách truy cập nội bộ; ta đang nói về **hợp đồng và thao tác thông thường**, không về việc dùng kỹ thuật phản xạ để cố tình phá rào chắn.

## 7. Read-only view không phải snapshot độc lập

Một **view chỉ đọc** có thể cấm sửa qua giao diện của nó, nhưng vẫn phản ánh những thay đổi mà chủ sở hữu thực hiện trên dữ liệu gốc.

Python có `types.MappingProxyType` để tạo **view chỉ đọc** của một dictionary.

```python
from types import MappingProxyType

source = {"A": [1, 2]}
view = MappingProxyType(source)

try:
    view["B"] = [3]
except TypeError:
    pass
else:
    raise AssertionError("View không cho gán mục qua proxy")

# Người nắm giữ dictionary gốc vẫn được sửa:
source["B"] = [3]
assert "B" in view

# Giá trị list bên trong cũng vẫn mutable:
view["A"].append(99)
assert source["A"] == [1, 2, 99]
```

Vì `view` là **cửa sổ nhìn vào dictionary gốc**, nó không phải ảnh chụp độc lập ở thời điểm tạo.

### Phân biệt ba lựa chọn

| Lựa chọn | Giao diện có cho sửa không? | Có thấy thay đổi sau đó của nguồn? |
| --- | --- | --- |
| Dictionary gốc mutable | Có | Có, vì là chính dữ liệu ấy |
| `MappingProxyType(source)` | Không cho sửa mapping qua proxy | **Có** khi `source` thay đổi |
| Snapshot độc lập được tạo đúng cách | Tùy loại snapshot | **Không** trong phạm vi trạng thái đã được tách biệt |

**Read-only view** và **immutable snapshot** là hai hợp đồng khác nhau. Không nên dùng từ “snapshot” cho một giao diện chỉ đọc nhưng vẫn nối trực tiếp tới dữ liệu mutable đang được cập nhật.

## 8. Sao chép nông (*shallow copy*) không giải quyết alias sâu

Với cấu trúc lồng nhau:

```python
original = {
    "HV001": {"grades": [8, 9]},
    "HV002": {"grades": [7, 10]},
}

shallow = original.copy()

assert shallow is not original
assert shallow["HV001"] is original["HV001"]

original["HV001"]["grades"].append(10)

assert shallow["HV001"]["grades"] == [8, 9, 10]
```

`dict.copy()` tạo một dictionary mới, nhưng **không tự sao chép các dictionary và list nằm bên trong**.

Nếu thay ánh xạ ở cấp ngoài, hai dictionary tách biệt:

```python
original["HV003"] = {"grades": [10]}
assert "HV003" not in shallow
```

Tuy vậy, hai bản vẫn cùng tham chiếu tới hồ sơ `HV001` đã có lúc sao chép, nên **chỉnh sửa hồ sơ bên trong** ảnh hưởng cả hai.

### Cách hiểu đúng

- **Tách cấu trúc ngoài:** một phép sao chép nông có thể làm được.
- **Tách trạng thái lồng nhau:** cần bước bổ sung nếu các phần tử mutable.
- **Làm bất biến mọi thành phần:** chỉ sao chép sâu **vẫn chưa đủ** nếu bản sao sau đó còn có thể bị sửa.

## 9. Sao chép sâu khác với đóng băng sâu

Python có `copy.deepcopy` để sao chép đệ quy nhiều loại đối tượng phổ biến.

```python
import copy

original = {
    "HV001": {"grades": [8, 9]},
}

independent = copy.deepcopy(original)

assert independent is not original
assert independent["HV001"] is not original["HV001"]
assert independent["HV001"]["grades"] is not original["HV001"]["grades"]

original["HV001"]["grades"].append(10)

assert independent["HV001"]["grades"] == [8, 9]
assert original["HV001"]["grades"] == [8, 9, 10]
```

Với các `dict` và `list` thông thường ở ví dụ, `deepcopy` cho bản sao **độc lập về các đối tượng con mutable** tại thời điểm sao chép.

Nhưng bản sao `independent` **vẫn mutable**:

```python
independent["HV001"]["grades"].append(5)

assert independent["HV001"]["grades"] == [8, 9, 5]
```

Do đó:

> **Deep copy** là kỹ thuật **tách quyền sở hữu/trạng thái**, còn **deep immutability** là hợp đồng **không thể thay đổi trạng thái sau khi tạo**.

### Giới hạn thực tế của deepcopy

- Không phải mọi tài nguyên như socket, khóa hệ điều hành, iterator sống, callback hoặc đối tượng bên ngoài đều có ngữ nghĩa sao chép sâu hợp lý.
- Lớp tùy biến có thể quyết định cách `deepcopy` hoạt động.
- Sao chép sâu của một đồ thị lớn có thể tốn `O(n)` thời gian/bộ nhớ hoặc hơn nếu logic sao chép phức tạp.
- Nếu nguồn đang bị thay đổi đồng thời, sao chép **không tự cung cấp tính nguyên tử hoặc snapshot nhất quán**.

Vì vậy, nên dùng cách sao chép **đúng miền dữ liệu** và làm rõ giới hạn, thay vì xem `deepcopy` là giải pháp phổ quát cho mọi bài toán bất biến.

## 10. Dựng snapshot bất biến theo kiểu dữ liệu miền

Giả sử dữ liệu đầu vào có hợp đồng rõ ràng:

```text
dict[str, list[int]]
```

Ta có thể tạo snapshot bằng cách:

1. Tạo **dictionary mới**.
2. Chuyển mỗi `list[int]` thành **tuple[int,...]`.
3. Chỉ cung cấp dictionary mới qua một **read-only proxy**; không lộ tham chiếu mutable tới dictionary chứa trong proxy.

```python
from types import MappingProxyType


def make_grade_snapshot(source):
    """Snapshot cho dict[str, list[int]] với lá là int."""
    copied = {
        student_id: tuple(grades)
        for student_id, grades in source.items()
    }
    return MappingProxyType(copied)


grade_source = {
    "HV001": [8, 9],
    "HV002": [7, 10],
}
snapshot = make_grade_snapshot(grade_source)

grade_source["HV001"].append(10)
grade_source["HV003"] = [5]

assert snapshot["HV001"] == (8, 9)
assert "HV003" not in snapshot

try:
    snapshot["HV001"] += (10,)
except TypeError:
    pass
else:
    raise AssertionError("Không được sửa mapping qua proxy")
```

Trong ví dụ, các khóa là `str` và phần tử là `int`, đều được dùng như **giá trị bất biến**, nên snapshot giữ được dữ liệu cũ trong phạm vi hợp đồng.

### Tại sao cách này khác `MappingProxyType(source)`?

Vì `copied` là dictionary **mới**, và các giá trị đã được chuyển thành tuple. Tham chiếu `grade_source` ở bên ngoài không còn trỏ tới các container mà snapshot đang dùng. Lưu ý mã dùng giả định **không có đường thay đổi khác tới `copied`** sau khi tạo.

### Với các kiểu dữ liệu phức tạp hơn?

Một hồ sơ có thể chứa:

```text
Student:
  id: str
  profile: dict
  grades: list
  attachments: mutable objects
```

Khi đó, “chuyển list thành tuple” ở một cấp chưa chắc đủ. Cần xây **kiểu dữ liệu bất biến cho từng trường**, kiểm tra mọi đối tượng con, hoặc đưa dữ liệu về biểu diễn giá trị đã được chuẩn hóa (chẳng hạn chuỗi/số/tuple của các lá bất biến).

## 11. Khái niệm phiên bản: giữ trạng thái cũ khi tạo trạng thái mới

Trong một cấu trúc mutable, cập nhật thường sửa **chính đối tượng đang tồn tại**:

```python
mutable = [10, 20]
old_alias = mutable

mutable.append(30)

assert old_alias == [10, 20, 30]
assert old_alias is mutable
```

Biến `old_alias` không giữ một **phiên bản lịch sử**. Nó chỉ là alias của **cùng một list** đã thay đổi.

Ngược lại, nếu mỗi cập nhật trả về một **đối tượng mới** và đối tượng cũ giữ nguyên, ta có thể biểu diễn các phiên bản:

```python
version_0 = (10, 20)
version_1 = version_0 + (30,)
version_2 = version_1 + (40,)

assert version_0 == (10, 20)
assert version_1 == (10, 20, 30)
assert version_2 == (10, 20, 30, 40)
```

Ở ví dụ này, mọi phần tử đều là số nguyên bất biến, nên cả ba tuple có nội dung ổn định.

Một **persistent data structure** được thiết kế để cho phép **giữ và tiếp tục sử dụng phiên bản cũ** sau khi tạo phiên bản mới, thường bằng **chia sẻ cấu trúc an toàn** thay vì sao chép toàn bộ dữ liệu cho mỗi lần thay đổi.

### Đặc tính chính của việc có phiên bản

- Phiên bản cũ còn có thể dùng để tra cứu.
- Phiên bản mới chứa thay đổi mong muốn.
- Trạng thái của phiên bản cũ không bị sửa khi tạo phiên bản mới.
- Những phần không bị ảnh hưởng có thể được **chia sẻ** để tiết kiệm bộ nhớ.
- Nếu phần tử dùng chung là mutable, phải xử lý riêng để bảo vệ ngữ nghĩa phiên bản.

Lưu ý: không phải mọi thao tác trả object mới đều là một hiện thực persistent hiệu quả; ta còn phải xem **chi phí sao chép, chia sẻ và tính an toàn của các phần tử**.

## 12. Chia sẻ cấu trúc khác với chia sẻ trạng thái mutable không kiểm soát

**Structural sharing** nghĩa là hai phiên bản cùng tham chiếu đến **một nút con hoặc một cây con không thay đổi**.

```text
Phiên bản V0:       A ──► B ──► C

Tạo V1 bằng thêm X ở đầu:

Phiên bản V0:       A ──► B ──► C
                         ▲
Phiên bản V1:       X ──► A ──► B ──► C

Các nút A, B, C được chia sẻ, nhưng không bị sửa.
```

Nếu các nút được thiết kế **bất biến** và payload của chúng có ngữ nghĩa ổn định, chia sẻ là an toàn: phiên bản `V1` có thể tái sử dụng phần đuôi của `V0`.

### Điều kiện quan trọng

**Chia sẻ đối tượng bất biến** thường phù hợp cho các phiên bản. **Chia sẻ đối tượng mutable mà bất kỳ bên nào có thể sửa** lại có thể làm cả hai phiên bản thay đổi nội dung quan sát được.

Do đó, persistent structure không chỉ là “dùng lại cùng một con trỏ”. Nó còn cần **quy tắc cập nhật không sửa nút cũ** và **hợp đồng về payload**, nhất là với dữ liệu lồng nhau.

## 13. Ví dụ Python: danh sách liên kết persistent

Một danh sách liên kết đơn có thể lưu mỗi nút dưới dạng `(value, next)` và **không cho sửa** hai trường ấy.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    value: int
    next: "Link | None" = None


v0 = Link(20, Link(30))
v1 = Link(10, v0)

assert v0.value == 20
assert v1.value == 10
assert v1.next is v0


def take_values(head):
    result = []
    node = head
    while node is not None:
        result.append(node.value)
        node = node.next
    return result


assert take_values(v0) == [20, 30]
assert take_values(v1) == [10, 20, 30]
```

Tạo `v1` bằng cách **thêm một nút mới ở đầu** và trỏ tới đuôi `v0`. Không sửa `v0` hoặc các nút trong nó.

### Độ phức tạp

- **Prepend** (thêm đầu) một nút: `O(1)` thời gian, `O(1)` bộ nhớ nút mới.
- **Đọc nút đầu:** `O(1)`.
- **Duyệt cả danh sách:** `O(n)` thời gian.
- **Thay phần tử ở sâu trong linked list persistent:** có thể phải sao chép đường tiền tố tới vị trí đó, tốn `O(i)` cho chỉ số `i` tính từ đầu, nếu dùng cấu trúc đơn giản này.

Giải pháp chỉ hiệu quả khi **hình dạng cấu trúc phù hợp thao tác**. Không phải tất cả cập nhật trên mọi cấu trúc persistent đều mặc định `O(1)`.

## 14. Cạm bẫy: nút persistent nhưng payload mutable

Thay kiểu của trường `value` thành một list mutable:

```python
@dataclass(frozen=True)
class LinkWithList:
    value: list[int]
    next: "LinkWithList | None" = None


points = [8, 9]
old_root = LinkWithList(points)
new_root = LinkWithList([10], old_root)

points.append(5)

assert old_root.value == [8, 9, 5]
assert new_root.next.value == [8, 9, 5]
```

Dù `LinkWithList` có `frozen=True` và `next` không được gán lại, **payload của nút cũ đã đổi**. Mọi phiên bản chia sẻ nút ấy đều quan sát trạng thái mới.

Đây là lỗi nền tảng nếu ta muốn **lưu lịch sử phiên bản điểm học viên**.

### Khắc phục theo miền dữ liệu

Thay vì lưu `list[int]`, có thể chuyển thành `tuple[int,...]` tại ranh giới nhận dữ liệu:

```python
@dataclass(frozen=True)
class LinkWithTuple:
    value: tuple[int, ...]
    next: "LinkWithTuple | None" = None


input_scores = [8, 9]
safe_old = LinkWithTuple(tuple(input_scores))
safe_new = LinkWithTuple((10,), safe_old)

input_scores.append(5)

assert safe_old.value == (8, 9)
assert safe_new.next is safe_old
```

Bây giờ đuôi được chia sẻ chỉ chứa **các giá trị bất biến** theo hợp đồng; thay đổi danh sách đầu vào không ảnh hưởng lịch sử.

## 15. Cây tìm kiếm nhị phân persistent: sao chép đường đi

Một BST bình thường thay đổi `left/right` khi chèn hoặc cập nhật. Trong **persistent BST**, ta có thể chọn **path copying**:

1. Đi theo đường tìm khóa từ gốc.
2. Khi thay đổi ở một vị trí, **tạo các nút mới trên đường đi ấy**.
3. Những cây con không bị ảnh hưởng được **chia sẻ nguyên vẹn**.
4. Trả **gốc mới**, giữ **gốc cũ** cho phiên bản trước.

Ví dụ:

```text
BST phiên bản v0:

          10
         /  \
        5    15

Chèn khóa 12 vào v1:

          10'          ← nút mới
         /   \
        5     15'      ← nút mới
             /
            12        ← nút mới

Nút 5 vẫn được chia sẻ giữa v0 và v1.
Nút 10 và 15 của v0 không bị sửa.
```

Ta dùng dấu phẩy trên `10'` và `15'` để chỉ **đối tượng mới có cùng khóa**, không phải khóa mới.

### Mã Python: Node bất biến và put trả gốc mới

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PNode:
    key: int
    value: str
    left: "PNode | None" = None
    right: "PNode | None" = None


def persistent_put(root, key, value):
    """Trả gốc BST mới, không sửa nút của phiên bản cũ."""
    if root is None:
        return PNode(key, value)

    if key < root.key:
        new_left = persistent_put(root.left, key, value)
        if new_left is root.left:
            return root
        return PNode(
            root.key, root.value,
            new_left, root.right
        )

    if key > root.key:
        new_right = persistent_put(root.right, key, value)
        if new_right is root.right:
            return root
        return PNode(
            root.key, root.value,
            root.left, new_right
        )

    # Khóa đã có: trả gốc cũ nếu không cần đổi giá trị.
    if root.value == value:
        return root

    return PNode(
        root.key, value,
        root.left, root.right
    )


def persistent_find(root, key):
    """Trả (found, value), phân biệt thiếu khóa và value=None."""
    current = root
    while current is not None:
        if key == current.key:
            return True, current.value

        current = (
            current.left if key < current.key
            else current.right
        )

    return False, None
```

Ở đoạn mã này, `key` là số nguyên và `value` là chuỗi, đều được dùng như các giá trị bất biến. Không cho phép trùng khóa dưới nhiều nút: khi `key` đã tồn tại, `put` thay giá trị bằng một nút mới, không thêm một nút cùng khóa.

### Thử tạo ba phiên bản

```python
v0 = PNode(
    10, "goc",
    PNode(5, "trai"),
    PNode(15, "phai")
)

v1 = persistent_put(v0, 12, "moi")
v2 = persistent_put(v1, 5, "cap-nhat")

assert persistent_find(v0, 12) == (False, None)
assert persistent_find(v1, 12) == (True, "moi")
assert persistent_find(v2, 12) == (True, "moi")

assert persistent_find(v0, 5) == (True, "trai")
assert persistent_find(v1, 5) == (True, "trai")
assert persistent_find(v2, 5) == (True, "cap-nhat")

assert v1 is not v0
assert v1.left is v0.left   # Chia sẻ nhánh không đổi
assert v1.right is not v0.right

assert v2 is not v1
assert v2.right is v1.right # Chia sẻ nhánh phải
```

Những `assert` cuối minh họa cả hai đặc tính:

- **Phiên bản cũ không đổi.**
- **Cây con không bị cập nhật được chia sẻ.**

**Giới hạn:** đây là **BST thường, không tự cân bằng**, dùng đệ quy. Nếu cây lệch thành chuỗi, một lần `put` có thể tốn `O(n)` và gặp giới hạn đệ quy. Dữ liệu sản xuất cần cấu trúc persistent cân bằng nếu muốn bảo đảm `O(log n)` ở trường hợp xấu nhất.

## 16. Vì sao path copying chỉ cần O(h) nút mới?

Gọi `h` là chiều cao BST, `n` là số nút hiện có.

Khi chèn hoặc cập nhật một khóa:

- Đường so sánh từ gốc tới vị trí cần đổi có chiều dài tối đa `h`.
- Tại mỗi nút trên đường về, thuật toán tạo **một bản nút mới** và giữ nguyên tham chiếu tới cây con không đổi.
- Những cây con nằm ngoài đường tìm **không bị sao chép**.

Vì vậy, nếu phép cập nhật thực sự thay đổi trạng thái:

```text
Thời gian cập nhật: O(h)
Số nút mới:         O(h)
Bộ nhớ đệ quy:      O(h)
```

Nếu BST cân đối, `h=O(log n)`; một lần cập nhật có thể dùng **`O(log n)` thời gian và số nút mới**. Nếu BST lệch, cả hai có thể là `O(n)`.

### Khi giữ nhiều phiên bản

Với `m` lần cập nhật thành công và vẫn giữ tất cả gốc phiên bản, bộ nhớ của một cấu trúc persistent dùng path copying có thể được ước lượng bằng:

```text
Số nút ban đầu:          O(n)
Số nút tạo thêm:         O(mh_max)

Tổng tối đa:             O(n + m h_max)
```

trong đó `h_max` là chiều cao lớn nhất của các cây trong quá trình cập nhật. Với cây cân đối, `h_max` thường được chặn theo `O(log(n+m))` tương ứng với số khóa qua các thời điểm.

Đây là **giới hạn trên cho số nút được cấp phát** trong mô hình đơn giản. Nếu không còn ai giữ một phiên bản hoặc nút nào nữa, cơ chế quản lý bộ nhớ có thể thu hồi các đối tượng không còn được tham chiếu.

**Không phải mọi thao tác persistent đều sao chép `O(h)`:** ví dụ prepend vào danh sách liên kết chỉ tạo một nút mới. Chi phí phụ thuộc hình dạng và thao tác.

## 17. Phiên bản cũ vẫn có thể bị ảnh hưởng bởi payload mutable

Path copying chỉ bảo vệ **liên kết và nút** nếu chúng bất biến. Nếu các nút cùng chứa hoặc chia sẻ **một đối tượng giá trị mutable**, nội dung quan sát có thể thay đổi.

```python
@dataclass(frozen=True)
class BadPNode:
    key: int
    value: list[int]
    left: "BadPNode | None" = None
    right: "BadPNode | None" = None


shared_values = [8, 9]
r0 = BadPNode(10, shared_values)
r1 = BadPNode(5, [7], right=r0)

shared_values.append(10)

assert r0.value == [8, 9, 10]
assert r1.right.value == [8, 9, 10]
```

Những nút ở đây **không bị đổi liên kết**, nhưng giá trị điểm của khóa `10` đã đổi ở cả hai gốc.

### Giải pháp phải đi từ mô hình phần tử

Có thể:

- Dùng **giá trị nguyên thủy bất biến** như `int`, `str`, các tuple lồng nhau chỉ chứa phần tử bất biến.
- Chuyển dữ liệu mutable đầu vào thành **kiểu giá trị bất biến** ngay lúc đưa vào cấu trúc.
- Xác định rõ quyền sở hữu: không để lại tham chiếu cho bên ngoài sửa trạng thái chung.
- Tạo snapshot phù hợp với miền dữ liệu trước khi lưu vào nút mới.
- Nếu giá trị là tài nguyên ngoài (file, network, hồ sơ trong cơ sở dữ liệu), xác định liệu dữ liệu lịch sử nên lưu **giá trị tại thời điểm chụp** hay chỉ lưu **định danh tới tài nguyên sống**.

Chia sẻ cấu trúc giúp tiết kiệm bộ nhớ chỉ khi những phần được chia sẻ có **ngữ nghĩa ổn định**.

## 18. Bất biến sâu và khóa tra cứu: ảnh hưởng tới map, set, cây và bảng băm

Một đối tượng mutable nằm trong cấu trúc không chỉ làm **snapshot mất ổn định**, mà đôi khi còn làm **bất biến thuật toán bị phá**.

### Trường hợp khóa dùng để tổ chức BST

BST phân nhánh theo khóa, chẳng hạn hồ sơ có `student_id`. Nếu một đối tượng khóa bị thay đổi **sau khi đã đặt vào cây** mà không tháo/chèn lại theo vị trí mới, nút có thể nằm sai phía.

Ví dụ về ý tưởng:

```text
          key = 50
         /
   key = 30

Nếu sửa đối tượng khóa ở nút trái:
   30 → 70

Hình dạng vẫn như cũ, nhưng 70 > 50 mà lại nằm bên trái.
```

Tìm theo khóa `70` từ gốc sẽ rẽ phải, có thể báo thiếu dù nút tồn tại vật lý.

### Trường hợp hash map/hash set

Bảng băm dựa vào giá trị băm và quy tắc bằng nhau. Nếu khóa đang làm phần tử của set hoặc khóa của map **thay đổi các trường ảnh hưởng tới `hash`/`equals`**, việc tra cứu có thể sai hoặc không tìm thấy phần tử theo cách mong đợi.

Python thường không cho dùng `list` làm khóa dictionary vì list không hashable. Nhưng một lớp tùy biến được viết là hashable **không tự bảo đảm trạng thái dùng để băm sẽ mãi bất biến**. Đây là lý do phải cẩn thận với những đối tượng khóa tự viết.

### Giá trị mutable và khóa mutable là hai rủi ro khác nhau

| Vị trí của đối tượng mutable | Rủi ro chính |
| --- | --- |
| **Value** trong tree map | Phiên bản/snapshot có thể quan sát dữ liệu đổi |
| **Key** trong BST | Vị trí nút có thể không còn phù hợp với comparator |
| **Key** trong hash map/set | Giá trị băm/bằng nhau không còn khớp vị trí lưu |
| **Phần tử** của tuple/linked list | Dữ liệu hiển thị qua cấu trúc ngoài thay đổi |
| **Thuộc tính** tham gia sắp xếp trong hàng đợi ưu tiên | Thứ tự ưu tiên hiện tại có thể không còn phản ánh heap invariant |

Thông điệp chung: **thiết kế bất biến phải xét vai trò của mỗi phần tử**, không chỉ kiểu chứa bên ngoài.

## 19. Tính bất biến và an toàn đồng thời

Đối tượng bất biến thực sự thường thuận lợi khi **nhiều luồng chỉ đọc** cùng một phiên bản, bởi không có thao tác sửa tại chỗ trên trạng thái chia sẻ cần phối hợp.

Nhưng cần phân biệt:

- **Đối tượng bất biến sâu:** bản thân trạng thái được đọc không đổi sau khi tạo.
- **Bất biến nông + phần tử mutable:** phần tử vẫn có thể bị luồng khác sửa.
- **Snapshot được công bố an toàn:** ngoài việc tạo giá trị, hệ thống còn phải bảo đảm người đọc nhận được một phiên bản được công bố nhất quán theo mô hình bộ nhớ của nền tảng.
- **Nhiều cập nhật đồng thời:** việc tạo và chọn “phiên bản hiện hành” có thể cần khóa, nguyên tử, transaction hoặc cơ chế đồng bộ khác.

Không nên tuyên bố “dùng tuple nên toàn hệ thống thread-safe”. Tuple chứa list mutable hoặc đối tượng tham chiếu tới tài nguyên sống **không cho bảo đảm ấy**.

### Ví dụ về gốc phiên bản

Một ứng dụng có thể giữ:

```text
current_root → version 12
old_root     → version 11
```

Tạo `version 13` bằng path copying không sửa `version 12`, nhưng thao tác **gán/đăng phiên bản mới vào `current_root`** vẫn cần cơ chế nhất quán nếu nhiều luồng cùng ghi hoặc cần nhóm nhiều bước thành một giao dịch.

Bài học ở đây là: **immutability giảm một loại rủi ro chia sẻ trạng thái**, chứ không giải quyết tất cả các yêu cầu đồng bộ, thứ tự sự kiện hoặc truy cập tài nguyên ngoài.

## 20. Chi phí bộ nhớ và thời gian khi chọn cấu trúc

Không có một mức bất biến nào miễn phí trong mọi bài toán. Hãy phân tích theo **thao tác và dạng dữ liệu**.

| Cách biểu diễn/cập nhật | Chi phí điển hình | Nhận xét |
| --- | --- | --- |
| `list.append(x)` mutable | `O(1)` khấu hao | Thay trực tiếp list; các alias quan sát thay đổi |
| `tuple + (x,)` | `O(n)` | Tạo tuple mới dài hơn; phần tử cũ vẫn được tham chiếu |
| Chuyển `list` thành `tuple` | `O(n)` | Sao chép các tham chiếu ở cấp ngoài, không deep-freeze |
| `dict.copy()` | `O(n)` | Sao chép nông mapping |
| `copy.deepcopy` trên đồ thị container thông thường | Thường theo kích thước đồ thị được sao chép | Chi phí/ý nghĩa tùy các kiểu đối tượng |
| Prepend linked list persistent | `O(1)` | Một nút mới, chia sẻ đuôi bất biến |
| Cập nhật persistent BST bằng path copying | `O(h)` thời gian, `O(h)` nút mới | Tái sử dụng các cây con không đổi |
| Duyệt một phiên bản BST | `O(n)` | Không tự thay đổi phiên bản |
| Cập nhật mutable BST thường | `O(h)` thời gian, thường `O(1)` liên kết thay đổi | Không giữ lịch sử trừ khi bổ sung cơ chế khác |

Trong bảng, `n` là số phần tử hoặc số nút liên quan, `h` là chiều cao BST. Với cây cân đối `h=O(log n)`; với cây lệch `h=Θ(n)`.

### Không so sánh chỉ bằng Big-O của một phép cập nhật

Cần xét thêm:

- Có bao nhiêu **phiên bản cũ** được giữ lại?
- Phần tử có lớn hoặc có cấu trúc lồng nhau phức tạp không?
- Có thường xuyên cần snapshot/undo/audit không?
- Hầu hết thao tác là **đọc**, hay **ghi liên tục**?
- Bộ nhớ được chia sẻ giữa các phiên bản bao nhiêu?
- Có yêu cầu **concurrent reads** và cơ chế công bố phiên bản an toàn không?

Một cấu trúc mutable đơn giản có thể tiết kiệm cấp phát trong ứng dụng chỉ có một trạng thái hiện hành. Một cấu trúc persistent có thể phù hợp hơn khi cần giữ nhiều trạng thái và chia sẻ phần không thay đổi.

## 21. Thiết kế API: ghi rõ mức bất biến và quyền sở hữu

Thay vì chỉ ghi “return immutable list”, tài liệu API nên làm rõ:

**Ví dụ hợp đồng yếu:**

```text
get_courses() trả một collection chỉ đọc.
```

Người dùng vẫn chưa biết liệu:

- Collection có thể thay đổi do nguồn cập nhật không?
- Các `Course` bên trong có thể sửa không?
- Collection là snapshot hay live view?
- Có thể giữ kết quả để dùng lại như lịch sử không?

**Ví dụ hợp đồng rõ hơn:**

```text
get_course_snapshot():
- Trả snapshot tại thời điểm gọi.
- Các khóa mã học phần là str bất biến.
- Các danh sách buổi học được chuyển thành tuple.
- Không có tham chiếu mutable bên ngoài tới container của snapshot.
- Các bản snapshot cũ không thay đổi sau thao tác cập nhật mới.
```

Những câu hỏi nên được trả lời trong thiết kế:

1. **Ownership:** ai nắm quyền sửa đối tượng gốc?
2. **Copy policy:** sao chép nông, sâu hay chuẩn hóa thành giá trị bất biến?
3. **Element contract:** phần tử nào phải là immutable?
4. **Version contract:** phiên bản cũ có phải giữ nguyên toàn bộ nội dung hay chỉ topology?
5. **Concurrency contract:** một lần đọc thuộc về phiên bản nào và được công bố ra sao?
6. **Performance:** thao tác nào phải `O(1)`, `O(log n)` hay chấp nhận `O(n)`?

Các điều kiện này giúp người dùng hiểu chính xác **điều gì không thay đổi**, không chỉ thấy một tên kiểu có vẻ an toàn.

## 22. Kiểm thử tính bất biến qua alias và phiên bản

Một cách kiểm thử mạnh là **chủ động giữ lại tham chiếu đầu vào**, rồi thay đổi chúng để xem snapshot có bị ảnh hưởng hay không.

### Kiểm tra snapshot đã tách phần tử

```python
data = {
    "HV001": [8, 9],
    "HV002": [7],
}

snap = make_grade_snapshot(data)

# Sửa chính list đang được nguồn tham chiếu.
data["HV001"][0] = 100
data["HV002"].append(10)

# Thêm khóa mới vào nguồn.
data["HV003"] = [5]

assert snap["HV001"] == (8, 9)
assert snap["HV002"] == (7,)
assert "HV003" not in snap
```

### Kiểm tra phiên bản cũ giữ nguyên

```python
before = PNode(10, "A", PNode(5, "B"))
after = persistent_put(before, 20, "C")

assert persistent_find(before, 20) == (False, None)
assert persistent_find(after, 20) == (True, "C")
assert before.left is after.left
assert after is not before
```

### Kiểm tra giá trị mutable làm vỡ bảo đảm phiên bản

```python
raw = [1, 2]
problem = LinkWithList(raw)

raw.append(3)

assert problem.value == [1, 2, 3]  # Cố ý chứng minh nguy cơ
```

Không nên xem test cuối là một tính chất **mong muốn**; nó là **negative test** giúp người học nhận ra rằng `frozen` không thay thế việc đóng băng phần tử.

### Các tính chất nên kiểm tra thêm

- Không thay đổi **cấu trúc cũ** sau mỗi cập nhật persistent.
- Những nhánh không đổi được **chia sẻ tham chiếu** theo chủ ý.
- Những nhánh đổi được cấp phát nút mới.
- Cập nhật một giá trị trong phiên bản sau không làm thay đổi bản trước.
- Không có tham chiếu mutable bên ngoài làm dữ liệu snapshot đổi.
- Nếu có `parent`, `height`, `subtree_size` hoặc thứ tự BST, kiểm thử độc lập các bất biến ấy.

**Ghi chú quy trình:** đây là ví dụ kiểm thử để người học tự chạy, chưa thay thế vòng **Content QA chuyên môn STEP 6** của hệ thống biên soạn học liệu.

## 23. Lỗi thường gặp

1. **Cho rằng tuple tự đóng băng list/dict nằm bên trong.** Tuple chỉ bảo vệ các vị trí tham chiếu của nó.
2. **Cho rằng `@dataclass(frozen=True)` làm mọi trường con bất biến sâu.** Trường list vẫn sửa được.
3. **Cho rằng view chỉ đọc là snapshot.** Một `MappingProxyType(source)` vẫn thấy dictionary nguồn thay đổi.
4. **Dùng `dict.copy()` rồi nghĩ đã có deep copy.** Các đối tượng con có thể vẫn dùng chung.
5. **Nghĩ deep copy làm bản sao bất biến.** Bản sao thường vẫn mutable.
6. **Giữ alias tới phần tử mutable sau khi tạo “snapshot”.** Bên ngoài vẫn có thể sửa nội dung.
7. **Chỉ kiểm tra `is` khác nhau ở cấp ngoài.** Hai container khác nhau vẫn có thể cùng tham chiếu một phần tử.
8. **Nhầm việc gán lại biến với sửa đối tượng.** Tạo tuple mới không sửa tuple cũ.
9. **Nhầm bất biến (invariant) với immutability.** BST mutable vẫn có invariant thứ tự.
10. **Không xác định chính sách khóa trùng/comparator.** Phần tử hoặc khóa bị sửa có thể làm sai cấu trúc tra cứu.
11. **Thay đổi khóa trong BST mà không sắp xếp lại.** Vị trí của nút có thể sai.
12. **Thay đổi trạng thái ảnh hưởng `hash` của khóa bảng băm.** Tra cứu có thể hỏng.
13. **Chia sẻ nút mutable giữa các phiên bản persistent.** Sửa một nút ảnh hưởng nhiều phiên bản.
14. **Dùng nút bất biến nhưng payload mutable.** Nội dung lịch sử vẫn có thể đổi.
15. **Sao chép cả cấu trúc mỗi lần cập nhật mà không xét chi phí.** Với tuple lớn, thêm cuối `O(n)`.
16. **Tuyên bố mọi thao tác persistent đều `O(1)`.** Path copying có thể cần `O(h)` nút mới.
17. **Cho rằng cây persistent thường tự cân bằng.** Chiều cao vẫn có thể tăng tuyến tính.
18. **Cho rằng bất biến sâu tự bảo đảm an toàn đồng thời toàn hệ thống.** Công bố phiên bản và ghi đồng thời vẫn có hợp đồng riêng.
19. **Giữ tài nguyên bên ngoài trong snapshot và mặc định nội dung tài nguyên không đổi.** Định danh tài nguyên không phải bản chụp giá trị.
20. **Chỉ kiểm thử giá trị lúc tạo, không thử thay đổi alias sau đó.** Rất dễ bỏ sót lỗi nông/sâu.

## 24. Tự luyện tập

**Bài 1.** Phân biệt **invariant** và **immutability** bằng ví dụ một BST có thể chèn/xóa nhưng luôn giữ thứ tự khóa.

**Bài 2.** Một tuple `t=([1,2],[3,4])` không cho gán `t[0]=...`. Có thể gọi `t[0].append(5)` không? Sau đó tuple có “đổi” theo nghĩa nào?

**Bài 3.** Với `external=["A"]` và `snapshot=(external,)`, nếu gọi `external.append("B")`, dữ liệu đọc qua `snapshot` là gì? Vì sao?

**Bài 4.** Vì sao một `@dataclass(frozen=True)` có trường `grades: list[int]` vẫn chưa đủ để giữ lịch sử điểm?

**Bài 5.** So sánh `MappingProxyType(source)` với một snapshot thực sự tách biệt. Nếu `source["x"]=2` thì điều gì xảy ra?

**Bài 6.** Với `original={"a":[1]}` và `copy=original.copy()`, sau `original["a"].append(2)`, `copy["a"]` bằng bao nhiêu? Nếu `original["b"]=[3]` thì `"b" in copy` là gì?

**Bài 7.** `copy.deepcopy` khác với cách chuyển `list[int]` thành `tuple[int,...]` ở điều kiện “còn sửa được sau khi tạo” như thế nào?

**Bài 8.** Đề xuất cách tạo snapshot ổn định cho `dict[str,list[int]]` mà không để việc sửa list nguồn ảnh hưởng kết quả.

**Bài 9.** Trong danh sách liên kết persistent `v1=Link(10,v0)`, những nút nào được tạo mới và những nút nào được chia sẻ? Chi phí prepend?

**Bài 10.** Nếu trường `value` của `Link` là list mutable, vì sao có thể làm nhiều phiên bản thay đổi dữ liệu quan sát được dù `next` không đổi?

**Bài 11.** Khi chèn một khóa vào persistent BST bằng path copying, vì sao chỉ cần tạo nút mới trên đường tìm kiếm từ gốc?

**Bài 12.** Với cây ban đầu gốc `10`, con trái `5`, con phải `15`, chèn `12` vào phiên bản mới. Nút `5` có phải tạo lại không? Những nút nào phải mới?

**Bài 13.** Phân tích số nút mới, thời gian và bộ nhớ đệ quy cho `persistent_put` theo chiều cao `h`. Điều gì xảy ra nếu cây lệch thành chuỗi?

**Bài 14.** Vì sao giá trị `int` hoặc `str` thường an toàn để chia sẻ giữa các phiên bản hơn một `list` mutable?

**Bài 15.** Nếu một đối tượng dùng làm khóa BST thay đổi trường so sánh sau khi được chèn, thuật toán tìm kiếm có thể sai như thế nào?

**Bài 16.** Vì sao một đối tượng hashable tùy biến nhưng có `__hash__` phụ thuộc vào trường mutable có thể là lựa chọn nguy hiểm cho khóa dictionary?

**Bài 17.** Một hệ thống có dữ liệu bất biến sâu nhưng nhiều luồng cùng thay `current_root`. Có cần thảo luận đồng bộ hay không? Vì sao?

**Bài 18.** Với danh sách độ dài `n`, so sánh chi phí của `list.append` và `tuple + (x,)`. Khi nào chấp nhận chi phí tạo tuple mới?

**Bài 19.** Một API trả collection chỉ đọc nhưng cho phép cập nhật các hồ sơ `Student` bên trong. Cần ghi rõ những giới hạn nào trong hợp đồng?

**Bài 20.** Viết bộ kiểm thử chứng minh snapshot điểm số không bị thay đổi khi người gọi sửa danh sách đầu vào hoặc thêm khóa vào dictionary nguồn.

<details>
<summary>Đáp án và gợi ý</summary>

1. *Invariant* là điều kiện luôn phải đúng ở trạng thái hợp lệ, ví dụ mọi khóa ở trái nút BST nhỏ hơn khóa nút; *immutability* là không sửa trạng thái tại chỗ theo hợp đồng. BST mutable có thể giữ invariant bằng thuật toán cập nhật đúng.
2. Có thể gọi `t[0].append(5)`. Vị trí tuple vẫn trỏ tới cùng list, nhưng dữ liệu list đổi thành `[1,2,5]`; tuple bất biến cấp ngoài, không sâu.
3. `snapshot[0]` sẽ là `["A","B"]` vì tuple và biến `external` cùng trỏ tới một list.
4. `frozen=True` chặn gán lại trường nhưng không chặn sửa list mà trường trỏ tới.
5. `MappingProxyType(source)` phản ánh thay đổi của mapping nguồn; snapshot độc lập đúng cách không đổi theo nguồn trong phạm vi đã sao chép/đóng băng.
6. `copy["a"] == [1,2]` vì hai mapping chia sẻ list; `"b" in copy` là `False` vì thêm khóa mới chỉ ở dictionary gốc.
7. `deepcopy` cố tạo các bản sao con độc lập nhưng thường vẫn mutable; chuyển list các `int` thành tuple cho một cấu trúc cố định không cho sửa vị trí/phần tử số qua API của tuple.
8. Dựng dictionary mới với `{k: tuple(v) for k,v in source.items()}` rồi chỉ công bố qua proxy chỉ đọc; giả định `str/int` là giá trị bất biến và không lộ dict mới cho bên khác sửa.
9. Chỉ tạo nút `Link(10,v0)` mới, còn toàn bộ đuôi `v0` được chia sẻ; prepend `O(1)` thời gian và một nút bộ nhớ.
10. Hai gốc cùng truy cập một payload mutable; sửa list làm giá trị quan sát qua cả hai thay đổi dù liên kết không sửa.
11. Chỉ đường từ gốc tới vị trí cập nhật thay đổi quan hệ con/giá trị. Các cây con khác không đổi có thể dùng lại nếu chúng bất biến.
12. Nút `5` được chia sẻ. Tạo nút mới `12`, bản mới của `15` (đổi con trái) và bản mới của gốc `10` (đổi con phải).
13. `O(h)` thời gian, `O(h)` nút mới và `O(h)` call stack. Nếu cây lệch, `h=Θ(n)` và một lần cập nhật có thể tuyến tính.
14. Các giá trị này thường không có thao tác sửa trạng thái tại chỗ, nên chia sẻ không tạo đường cập nhật làm mất ổn định phiên bản. List mutable cho phép thay đổi nội dung.
15. Nút có thể nằm ở nhánh trái dù khóa mới lớn hơn gốc; tìm bằng so sánh sẽ rẽ phải và báo không tìm thấy.
16. Khi đối tượng đổi trường ảnh hưởng tới băm, bucket/vị trí tra cứu và quy tắc bằng nhau có thể không còn khớp trạng thái lúc thêm, làm truy vấn sai.
17. Vẫn cần hợp đồng công bố phiên bản/đồng bộ để người đọc và các luồng ghi thống nhất về phiên bản hiện hành; bất biến sâu chỉ giải quyết việc sửa trạng thái đã công bố.
18. `list.append` có `O(1)` khấu hao; `tuple+(x,)` cần tạo tuple mới và sao chép `n` tham chiếu, `O(n)`. Chọn tuple khi ưu tiên dữ liệu bất biến nhỏ hoặc số lần cập nhật ít.
19. Nêu rõ đây là **view hay snapshot**, phần tử có mutable không, ai có quyền sửa phần tử, thay đổi bên ngoài có được nhìn thấy không và có bảo đảm dùng lại như lịch sử không.
20. Sau khi tạo snapshot, giữ alias tới các list nguồn rồi sửa chúng, thêm/xóa khóa trong dictionary nguồn; khẳng định các tuple giá trị và tập khóa của snapshot vẫn như thời điểm tạo.

</details>

## Ghi nhớ

**Bất biến của cấu trúc ngoài không tự đồng nghĩa với bất biến của phần tử bên trong.** Tuple, frozen object hoặc read-only view có thể vẫn chứa/tham chiếu tới **list, dictionary hoặc đối tượng mutable**. Nếu có alias bên ngoài, dữ liệu có thể đổi mà không cần thay cấu trúc ngoài. Muốn **snapshot/lịch sử phiên bản ổn định**, hãy xác định mức bảo đảm, tách quyền sở hữu và **đóng băng đúng các phần tử lồng nhau**; `deepcopy` tách nhiều trạng thái nhưng không tự làm bản sao bất biến. Cấu trúc persistent có thể giữ nhiều phiên bản bằng **structural sharing**: tạo nút mới ở phần bị ảnh hưởng và chia sẻ những nút **thực sự bất biến**; prepend linked list có thể `O(1)`, còn cập nhật persistent BST thường cần `O(h)` nút mới. Cuối cùng, tính bất biến giúp đọc dữ liệu dễ dự đoán hơn nhưng **không thay thế quy tắc đồng bộ, comparator và các bất biến thuật toán** khi hệ thống tiếp tục hoạt động.
