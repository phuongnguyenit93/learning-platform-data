# Khung nhìn khóa, giá trị, cặp khóa–giá trị và thay đổi trên cấu trúc gốc

Một hệ thống học tập lưu điểm theo mã học viên trong map: `"HV01" → 8.0` và `"HV02" → 9.0`. Ứng dụng cần hiện danh sách mã, thống kê điểm và xuất từng cặp mã–điểm. Trong lúc đó, điểm số có thể được cập nhật và học viên mới có thể được thêm vào. Câu hỏi quan trọng là: **danh sách đang xem có tự phản ánh thay đổi của map không, hay đó là một bản sao tại một thời điểm?**

Bài học thuộc chương **Tập hợp và ánh xạ**. Ta tìm hiểu ba **khung nhìn (view)** phổ biến của map: **khóa**, **giá trị** và **cặp khóa–giá trị**; phân biệt view với bản sao (*snapshot*), quy tắc khi cấu trúc gốc thay đổi, cách duyệt an toàn và chi phí thời gian, bộ nhớ. Đây là kiến thức cần thiết khi xây dựng ứng dụng dựa trên map, bảng băm, cây có thứ tự và các chỉ mục phục vụ thuật toán.

## 1. Một map, ba cách nhìn cùng dữ liệu

Với map `M`, ba khung nhìn trả lời những câu hỏi khác nhau:

| Khung nhìn | Nội dung | Câu hỏi tiêu biểu |
| --- | --- | --- |
| **Khóa (keys)** | Những khóa hiện có trong map | “Mã học viên nào đã được đăng ký?” |
| **Giá trị (values)** | Giá trị hiện gắn với từng khóa | “Các điểm số hiện tại là gì?” |
| **Cặp khóa–giá trị (items/entries)** | Các liên kết `(key, value)` | “Điểm của từng học viên là bao nhiêu?” |

Ví dụ Python:

```python
scores = {"HV01": 8.0, "HV02": 9.0}

keys_view = scores.keys()
values_view = scores.values()
items_view = scores.items()

print(list(keys_view))    # ['HV01', 'HV02']
print(list(values_view))  # [8.0, 9.0]
print(list(items_view))   # [('HV01', 8.0), ('HV02', 9.0)]
```

Trong Python, `dict.keys()`, `dict.values()` và `dict.items()` trả về các **đối tượng view chuyên dụng** chứ không phải ba list độc lập. Ta có thể duyệt những view này mà không cần lập tức sao chép tất cả phần tử.

**Bất biến của map vẫn được giữ:** mỗi khóa phân biệt chỉ có một giá trị hiện tại. Khung nhìn khóa không được phép tùy ý tạo thêm khóa nằm ngoài map; khung nhìn giá trị và cặp khóa–giá trị phải tương ứng với trạng thái của map gốc.

### Khóa và giá trị không có cùng tính duy nhất

Một map có **khóa duy nhất**, nhưng **giá trị có thể lặp**:

```python
scores = {"HV01": 8.0, "HV02": 8.0, "HV03": 9.0}

assert len(scores.keys()) == 3
assert list(scores.values()).count(8.0) == 2
assert len(scores.items()) == 3
```

Vì vậy, **khung nhìn giá trị không phải set**. Nếu chuyển `scores.values()` thành set, ta có thể mất thông tin lặp; nếu chuyển thành list, ta giữ lại một phần tử giá trị cho mỗi khóa.

## 2. “View sống” khác “snapshot” như thế nào?

**View sống (live/dynamic view)** là đối tượng phản ánh trạng thái của cấu trúc gốc khi được sử dụng. **Snapshot** là dữ liệu được sao chép ở một thời điểm; thay đổi về sau ở cấu trúc gốc không tự thêm/bớt phần tử của snapshot.

Trong Python:

```python
scores = {"HV01": 8.0, "HV02": 9.0}

keys_view = scores.keys()
values_view = scores.values()
items_view = scores.items()

keys_snapshot = list(scores.keys())
items_snapshot = list(scores.items())

# Thay đổi map sau khi đã tạo các view và snapshot
scores["HV01"] = 9.5
del scores["HV02"]
scores["HV03"] = 7.0

assert list(keys_view) == ["HV01", "HV03"]
assert list(values_view) == [9.5, 7.0]
assert list(items_view) == [("HV01", 9.5), ("HV03", 7.0)]

# Bản sao list không được tự đồng bộ khi thay map.
assert keys_snapshot == ["HV01", "HV02"]
assert items_snapshot == [("HV01", 8.0), ("HV02", 9.0)]
```

Thí nghiệm cho thấy **không cần gọi lại `scores.keys()` để biết tập khóa mới**: đối tượng `keys_view` cũ vẫn tham chiếu đến map hiện tại.

Tuy nhiên, cần phân biệt **view** với **iterator**: một view có thể được duyệt lại nhiều lần để đọc trạng thái hiện tại; một iterator đã tạo từ view có trạng thái duyệt riêng, và không bảo đảm an toàn nếu map bị thay đổi cấu trúc giữa chừng.

### Một dòng thời gian ngắn

| Thời điểm | Thao tác trên map gốc | `keys_view` khi đọc lúc đó | `keys_snapshot` đã tạo trước |
| --- | --- | --- | --- |
| `t0` | Ban đầu: `HV01, HV02` | `HV01, HV02` | `HV01, HV02` |
| `t1` | Cập nhật điểm `HV01` | `HV01, HV02` | `HV01, HV02` |
| `t2` | Xóa `HV02` | `HV01` | `HV01, HV02` |
| `t3` | Thêm `HV03` | `HV01, HV03` | `HV01, HV02` |

Một snapshot không tự “hỏng” khi dữ liệu gốc thay đổi; nó đơn giản biểu diễn **một thời điểm khác**. Khi thiết kế API, hãy nói rõ người nhận cần **dữ liệu mới nhất** hay **ảnh chụp của một thời điểm**.

## 3. Khung nhìn khóa: tra cứu, duyệt và phép toán tập hợp

Trong Python, `dict_keys` hỗ trợ tra cứu khóa và nhiều **phép toán kiểu tập hợp**. Lý do: mỗi khóa của dict là duy nhất và hashable.

```python
scores = {"HV01": 8.0, "HV02": 9.0, "HV03": 8.0}
keys = scores.keys()

assert "HV02" in keys
assert "HV99" not in keys
assert len(keys) == 3

# Phép toán tập hợp trên khóa
active = {"HV02", "HV03", "HV04"}
assert keys & active == {"HV02", "HV03"}
assert keys - active == {"HV01"}
assert keys | active == {"HV01", "HV02", "HV03", "HV04"}
assert {"HV01", "HV02"} <= keys
```

Các kết quả như `keys & active` là **set mới**, không phải một view tự đồng bộ. Bản thân `keys` vẫn sống:

```python
scores = {"HV01": 8, "HV02": 9}
keys = scores.keys()

existing = keys & {"HV01", "HV03"}
assert existing == {"HV01"}

scores["HV03"] = 10
assert "HV03" in keys
assert keys & {"HV01", "HV03"} == {"HV01", "HV03"}
assert existing == {"HV01"}  # Kết quả phép giao cũ không tự cập nhật
```

Đây là khác biệt quan trọng giữa **đối tượng view** và **kết quả một phép toán đã được tính xong**. Khi ứng dụng muốn kiểm tra các khóa hợp lệ theo tập quy tắc mới nhất, cần thực hiện phép toán tại thời điểm phù hợp.

### View khóa không phải giao diện thêm/xóa tùy ý

Trong Python, `keys_view.add(...)` hoặc `keys_view.remove(...)` không phải thao tác được hỗ trợ. Muốn thay đổi nội dung map, phải thao tác lên **map gốc**:

```python
users = {"HV01": "An"}
keys = users.keys()

users["HV02"] = "Bình"
assert "HV02" in keys

del users["HV01"]
assert "HV01" not in keys
```

Những thư viện ở ngôn ngữ khác có thể cho phép xóa thông qua một view được hỗ trợ, vì vậy cần đọc hợp đồng cụ thể thay vì suy từ Python ra mọi map.

## 4. Khung nhìn giá trị: có thể lặp, không thay cho chỉ mục ngược

`dict_values` cung cấp các giá trị **theo những mục hiện có trong map**. Khi nhiều khóa gắn cùng một giá trị, giá trị đó xuất hiện tương ứng nhiều lần trong phép duyệt.

```python
score_by_id = {
    "HV01": 8.0,
    "HV02": 8.0,
    "HV03": 9.0,
}

values = score_by_id.values()

assert list(values) == [8.0, 8.0, 9.0]
assert 8.0 in values
assert 10.0 not in values
```

Cần phân biệt hai dạng kiểm tra:

- `key in mapping` hoặc `key in mapping.keys()`: tra cứu **theo khóa**; với hash map, thường `O(1)` trung bình.
- `value in mapping.values()`: tìm một **giá trị** bất kỳ bằng phép duyệt; thường cần đến `O(n)`.

Không dùng `values_view` như một chỉ mục ngược có hiệu năng tương đương map. Nếu thường xuyên cần tìm **mọi học viên có điểm 8**, có thể xây thêm chỉ mục `điểm → tập mã học viên`, và đồng bộ nó khi cập nhật điểm.

### Không nhầm số giá trị với số giá trị phân biệt

```python
counts = {"A": 2, "B": 2, "C": 0}

assert len(counts.values()) == 3
assert set(counts.values()) == {0, 2}
assert len(set(counts.values())) == 2
```

`len(counts.values())` bằng **số mục của map**, không phải số giá trị khác nhau. Phép chuyển sang set tạo dữ liệu mới, loại trùng và yêu cầu các giá trị phải hashable; nếu giá trị là list/dict, không thể gọi `set(counts.values())` trực tiếp.

## 5. Khung nhìn cặp khóa–giá trị: giữ mối liên hệ

`dict_items` trả các cặp `(key, value)` khi duyệt. Nó phù hợp với xuất báo cáo, kiểm tra dữ liệu và biến đổi map:

```python
grades = {"HV01": 8, "HV02": 9}

for student_id, grade in grades.items():
    print(f"{student_id}: {grade}")

pairs = list(grades.items())
assert pairs == [("HV01", 8), ("HV02", 9)]
```

Duyệt cặp giúp tránh phải duyệt khóa rồi tra cứu lại từng giá trị; mỗi cặp đã có sẵn khóa và giá trị tương ứng.

Với các **giá trị hashable**, `dict_items` hỗ trợ một số phép toán kiểu set trên cặp:

```python
scores = {"HV01": 8, "HV02": 9}
entries = scores.items()

assert ("HV01", 8) in entries
assert ("HV01", 9) not in entries
assert entries & {("HV01", 8), ("HV99", 0)} == {("HV01", 8)}
```

Không phải mọi `dict_items` đều dùng được như một set các cặp. Nếu giá trị là list/dict **không hashable**, một số phép toán tập hợp cần hash các cặp sẽ không phù hợp:

```python
groups = {"A": [1, 2], "B": [3]}

# Duyệt cặp vẫn đúng:
assert list(groups.items()) == [("A", [1, 2]), ("B", [3])]

# Không dùng set(groups.items()) vì tuple chứa list không hashable.
```

Mặc dù cú pháp lặp trả một tuple `(key, value)` cho mỗi mục, **giá trị bên trong tuple vẫn có thể là một đối tượng mutable**, nên cần hiểu rõ tính nông của bản sao khi sử dụng snapshot.

## 6. Map gốc thay đổi sau khi có view

Các thao tác cơ bản lên map gốc tác động đến từng view như sau:

| Thao tác trên map | View khóa | View giá trị | View cặp |
| --- | --- | --- | --- |
| Thêm khóa mới | Có thêm khóa | Có thêm giá trị | Có thêm cặp |
| Cập nhật giá trị khóa có sẵn | Tập khóa không đổi | Phản ánh giá trị mới | Cặp của khóa phản ánh giá trị mới |
| Xóa một khóa | Không còn khóa đó | Không còn giá trị của mục bị xóa | Không còn cặp tương ứng |
| `clear()` | Trở thành rỗng | Trở thành rỗng | Trở thành rỗng |

Ví dụ:

```python
inventory = {"SP01": 0, "SP02": 4}
keys, values, pairs = inventory.keys(), inventory.values(), inventory.items()

inventory["SP01"] = 7
assert list(keys) == ["SP01", "SP02"]
assert list(values) == [7, 4]
assert list(pairs) == [("SP01", 7), ("SP02", 4)]

inventory.pop("SP02")
assert list(keys) == ["SP01"]

inventory.clear()
assert len(keys) == len(values) == len(pairs) == 0
```

Với Python `dict` từ phiên bản 3.7, phép duyệt các khóa giữ **thứ tự chèn**. Thay giá trị không đổi vị trí khóa; xóa rồi chèn lại cùng một khóa khiến khóa đó được tính là mục mới ở cuối thứ tự.

### View vẫn tham chiếu map cũ nếu biến được gán sang map khác

Đây là lỗi tinh tế liên quan đến **thay đổi đối tượng** và **gán lại biến**:

```python
data = {"A": 1}
old_view = data.keys()

data = {"B": 2}  # Biến data nay trỏ tới dict khác
assert list(old_view) == ["A"]
assert list(data.keys()) == ["B"]
```

`old_view` tham chiếu **đối tượng dict ban đầu**, không phải “tên biến `data`”. Việc gán lại biến không chuyển view sang dict mới. Nếu các thành phần ứng dụng truyền quanh view, cần biết chính xác đối tượng gốc và vòng đời của nó.

## 7. Duyệt view trong lúc thay đổi map: rủi ro và cách an toàn

Có một khác biệt lớn giữa **thay đổi map sau khi tạo view** và **thay đổi cấu trúc map trong khi đang duyệt view bằng iterator**.

Python có thể phát sinh `RuntimeError` khi thêm hoặc xóa khóa trong lúc vòng lặp duyệt `dict` hoặc các view của nó. Không nên dùng vòng lặp sau để lọc khóa:

```python
grades = {"HV01": 8, "HV02": 0, "HV03": 9}

# Không an toàn:
# for key in grades.keys():
#     if grades[key] == 0:
#         del grades[key]
```

Cách an toàn là duyệt **snapshot của các khóa** hoặc tạo map mới.

### Cách A: duyệt bản sao list khóa

```python
grades = {"HV01": 8, "HV02": 0, "HV03": 9}

for key in list(grades.keys()):
    if grades[key] == 0:
        del grades[key]

assert grades == {"HV01": 8, "HV03": 9}
```

`list(grades.keys())` tạo một list `O(n)` phần tử; khi xóa trong map gốc, list khóa vẫn giữ tập khóa của thời điểm tạo ra. Vì vậy vòng lặp không phụ thuộc iterator động đang duyệt chính dict gốc.

### Cách B: lọc thành map mới

```python
grades = {"HV01": 8, "HV02": 0, "HV03": 9}

filtered = {
    student_id: grade
    for student_id, grade in grades.items()
    if grade > 0
}

assert filtered == {"HV01": 8, "HV03": 9}
assert grades == {"HV01": 8, "HV02": 0, "HV03": 9}
```

Cách này không sửa map gốc; nó xây một cấu trúc mới chỉ chứa các mục đáp ứng điều kiện.

### Chỉ thay giá trị, không đổi số khóa

Trong Python `dict`, cập nhật **giá trị** của khóa đã tồn tại mà không thêm/xóa khóa thường được phép trong lúc duyệt:

```python
scores = {"HV01": 8, "HV02": 9}

for student_id in scores:
    scores[student_id] += 1

assert scores == {"HV01": 9, "HV02": 10}
```

Tuy nhiên, nếu logic vòng lặp **dựa trên giá trị đang thay đổi**, cần phân biệt giá trị cũ và mới để tránh lỗi nghiệp vụ. Một thay đổi cấu trúc phức tạp có thể khiến iterator lỗi hoặc bỏ qua mục, kể cả khi chương trình cố giữ tổng số khóa không đổi; cách an toàn là không sửa tập khóa khi duyệt trực tiếp.

**Quan trọng:** tạo một view trước khi thay đổi map là việc hợp lệ. Điều cần tránh là **sửa cấu trúc trong thời gian iterator trên view đang hoạt động**.

## 8. Snapshot nông, snapshot sâu và khung nhìn chỉ đọc

Một bản sao danh sách cặp không đồng nghĩa với bản sao độc lập của **toàn bộ đồ thị đối tượng**. Ví dụ các giá trị là dict có thể thay đổi:

```python
profiles = {
    "HV01": {"score": 8},
}

snapshot = list(profiles.items())
assert snapshot == [("HV01", {"score": 8})]

# Thay đổi bên trong đối tượng giá trị đang được tham chiếu
profiles["HV01"]["score"] = 9

# Tuple cũ vẫn giữ tham chiếu tới dict giá trị đó.
assert snapshot[0][1]["score"] == 9
```

`list(profiles.items())` sao chép **các tuple cặp**, nhưng không sao chép sâu giá trị. Tương tự, `profiles.copy()` và `dict(profiles)` tạo **bản sao nông** của map; các giá trị mutable bên trong có thể vẫn chia sẻ.

Khi cần một bản sao độc lập của các đối tượng con trong dữ liệu thông thường, có thể cân nhắc `copy.deepcopy`:

```python
from copy import deepcopy

profiles = {"HV01": {"score": 8}}
deep_snapshot = deepcopy(profiles)

profiles["HV01"]["score"] = 9
assert deep_snapshot["HV01"]["score"] == 8
```

`deepcopy` có chi phí phụ thuộc số và kích thước đối tượng được sao chép, đồng thời không phải mọi kiểu đối tượng đều sao chép sâu theo cách mong muốn. Với hệ thống dữ liệu phức tạp, có thể cần mô hình bất biến hoặc cơ chế snapshot/giao dịch riêng.

### Khung nhìn chỉ đọc vẫn có thể là live view

Python có `types.MappingProxyType`: lớp bọc không cho sửa **các mục của map thông qua proxy**, nhưng vẫn phản ánh thay đổi hợp lệ được thực hiện trực tiếp trên map gốc.

```python
from types import MappingProxyType

config = {"mode": "safe"}
read_only = MappingProxyType(config)

assert read_only["mode"] == "safe"

config["mode"] = "fast"
assert read_only["mode"] == "fast"

# read_only["mode"] = "unsafe"  # TypeError: không cho gán qua proxy
```

Do đó, **chỉ đọc không đồng nghĩa với snapshot bất biến**. Ngay cả proxy chỉ đọc ở mức map cũng không tự làm cho mọi đối tượng giá trị lồng bên trong trở thành bất biến.

Ba yêu cầu nên được nói rõ riêng:

- **Không cho người nhận sửa map qua giao diện này** → view chỉ đọc/proxy.
- **Muốn dữ liệu phản ánh trạng thái mới của map** → live view.
- **Muốn trạng thái được cố định tại thời điểm đọc** → snapshot với mức sao chép/bất biến thích hợp.

## 9. Ứng dụng: thống kê dữ liệu, đối chiếu khóa và làm báo cáo

Một hệ thống có các yêu cầu dữ liệu sau:

```python
required_ids = {"HV01", "HV02", "HV03"}
grades = {"HV01": 9, "HV02": 0}
```

**1. Xác định mã còn thiếu dữ liệu điểm**

```python
missing_ids = required_ids.difference(grades.keys())
assert missing_ids == {"HV03"}
```

Với Python, phép hiệu giữa set và view khóa dùng quy tắc tập hợp nên không cần tạo list khóa trung gian. Kết quả `missing_ids` là một set mới được tính **tại thời điểm phép trừ chạy**.

**2. Phân biệt học viên chưa có điểm với học viên có điểm bằng 0**

```python
assert "HV02" in grades.keys()      # Có hồ sơ điểm
assert grades["HV02"] == 0          # Giá trị hợp lệ là 0
assert "HV03" not in grades.keys()  # Chưa có khóa
```

Không kiểm tra sự tồn tại bằng `if grades.get("HV02")` vì `0` là falsy.

**3. Tạo báo cáo có thứ tự ổn định**

```python
report_rows = sorted(grades.items(), key=lambda pair: pair[0])

assert report_rows == [
    ("HV01", 9),
    ("HV02", 0),
]
```

Ở đây `sorted` tạo một **list mới** với các cặp tại thời điểm tạo báo cáo. Sau đó, cập nhật `grades` không tự thay các tuple `(mã, điểm)` đã nằm trong `report_rows` nếu điểm là số bất biến.

**4. Thống kê giá trị**

```python
average = sum(grades.values()) / len(grades) if grades else None
assert average == 4.5
```

Để tính trung bình phải duyệt các giá trị: đây không phải một tra cứu khóa `O(1)` mà là công việc `O(n)` với `n` mục hiện có. Việc tạo view ban đầu rẻ, nhưng **tiêu thụ tất cả phần tử trong view vẫn tốn công tương ứng số mục**.

### Chỉ mục ngược cần được đồng bộ

Nếu ứng dụng cần thường xuyên tìm học viên theo điểm, có thể xây:

```python
from collections import defaultdict

grades = {"HV01": 9, "HV02": 0, "HV03": 9}
students_by_score = defaultdict(set)

for student_id, score in grades.items():
    students_by_score[score].add(student_id)

assert students_by_score[9] == {"HV01", "HV03"}
```

Chỉ mục `students_by_score` là **cấu trúc dữ liệu riêng**, không phải một live view tự đồng bộ của `grades`. Nếu cập nhật điểm `HV01` thành `10` trong map gốc, phải cập nhật chỉ mục phụ tương ứng hoặc xây lại khi cần. Đây là ví dụ điển hình về khác biệt giữa **khung nhìn dữ liệu gốc** và **kết quả tính toán được lưu riêng**.

## 10. Java: các collection view được chống lưng bởi Map

Trong Java, ba phương thức của `Map<K,V>` trả các collection view:

- `keySet()` trả `Set<K>` chứa khóa.
- `values()` trả `Collection<V>` chứa các giá trị, có thể trùng.
- `entrySet()` trả `Set<Map.Entry<K,V>>` chứa các mục ánh xạ khóa–giá trị.

Các view này thông thường được **chống lưng bởi map gốc** (*backed by map*): thay đổi ở map được phản ánh trong view; một số thao tác xóa qua view cũng tác động ngược lại map.

```java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        Map<String, Integer> grades = new LinkedHashMap<>();
        grades.put("HV01", 8);
        grades.put("HV02", 0);

        Set<String> keys = grades.keySet();
        Collection<Integer> values = grades.values();
        Set<Map.Entry<String, Integer>> entries = grades.entrySet();

        grades.put("HV03", 9);
        System.out.println(keys.contains("HV03"));  // true

        keys.remove("HV01");                         // Xóa qua view
        System.out.println(grades.containsKey("HV01")); // false

        for (Map.Entry<String, Integer> entry : entries) {
            if (entry.getKey().equals("HV02")) {
                entry.setValue(7);  // Sửa giá trị qua entry (được hỗ trợ)
            }
        }
        System.out.println(grades.get("HV02"));      // 7

        values.remove(Integer.valueOf(9));           // Xóa một mục có giá trị 9
        System.out.println(grades.containsKey("HV03")); // false
    }
}
```

Ví dụ dùng `LinkedHashMap` để các ví dụ có thứ tự chèn dễ theo dõi. Khi `values().remove(value)` gặp nhiều mục có cùng giá trị, thao tác xóa **một** mục khớp, không có nghĩa xóa tất cả khóa mang giá trị đó. Ngoài ra, `Map.Entry.setValue` không được hỗ trợ bởi mọi hiện thực map; hãy dựa vào hợp đồng của kiểu cụ thể.

### Duyệt và xóa an toàn bằng iterator của view

Java có một cách xóa được hỗ trợ khi đang duyệt `entrySet()`: sử dụng `Iterator.remove()` của chính iterator.

```java
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

public class Main {
    public static void main(String[] args) {
        Map<String, Integer> grades = new LinkedHashMap<>();
        grades.put("HV01", 9);
        grades.put("HV02", 0);
        grades.put("HV03", 8);

        Iterator<Map.Entry<String, Integer>> it =
            grades.entrySet().iterator();

        while (it.hasNext()) {
            Map.Entry<String, Integer> entry = it.next();
            if (entry.getValue() == 0) {
                it.remove(); // Xóa thông qua chính iterator đang duyệt
            }
        }

        System.out.println(grades.containsKey("HV02")); // false
    }
}
```

Với `HashMap` và `LinkedHashMap`, việc sửa cấu trúc map bằng phương thức khác trong khi iterator đang hoạt động có thể gây `ConcurrentModificationException`. Cơ chế *fail-fast* chỉ phát hiện lỗi trên cơ sở **nỗ lực tốt nhất**, không nên dùng nó như cơ chế bảo đảm an toàn đồng thời. Với map bất biến hoặc các map đồng thời đặc biệt, tập thao tác được hỗ trợ và ngữ nghĩa iterator có thể khác.

**Điểm khác biệt quan trọng:** Python `dict_keys` không hỗ trợ `remove` qua view, còn Java `Map.keySet()` của một map mutable thường hỗ trợ thao tác xóa ngược lên map gốc. Không nên áp dụng máy móc quy tắc của một ngôn ngữ cho ngôn ngữ khác.

## 11. JavaScript Map: iterator, không phải các view collection của Python

Trong JavaScript, `Map.prototype.keys()`, `values()` và `entries()` trả về các **iterator**. Đây không phải ba đối tượng collection có thể duyệt đi duyệt lại tự do như `dict_keys`, `dict_values` và `dict_items` của Python.

```javascript
const scores = new Map([
  ["HV01", 8],
  ["HV02", 9],
]);

const keyIterator = scores.keys();
console.log([...keyIterator]); // ['HV01', 'HV02']

// keyIterator đã được tiêu thụ; để duyệt lại, tạo iterator mới.
console.log([...keyIterator]); // []

scores.set("HV03", 7);
console.log([...scores.keys()]);   // ['HV01', 'HV02', 'HV03']
console.log([...scores.values()]); // [8, 9, 7]
console.log([...scores.entries()]);
// [['HV01', 8], ['HV02', 9], ['HV03', 7]]
```

Map JavaScript duy trì thứ tự chèn theo hợp đồng của ngôn ngữ. Iteration có ngữ nghĩa gắn với Map hiện tại; không nên xem iterator như snapshot bất biến, đặc biệt nếu đang thêm/xóa mục trong lúc duyệt.

Khi tạo mảng bằng toán tử spread, ta thu được snapshot **nông** tại thời điểm lấy các phần tử:

```javascript
const data = new Map([["A", 1]]);
const snapshot = [...data.entries()];

data.set("A", 5);
data.set("B", 2);

console.log(snapshot);            // [['A', 1]]
console.log([...data.entries()]); // [['A', 5], ['B', 2]]
```

Mỗi mục trong `[...map.entries()]` là một mảng `[key, value]` được trả ra khi duyệt; sửa phần tử trong mảng cặp đã lấy ra không tương đương với gọi `map.set(key, value)`. Nếu `value` là một đối tượng mutable, các snapshot nông vẫn có thể chia sẻ tham chiếu tới đối tượng đó.

## 12. Độ phức tạp thời gian và bộ nhớ

Đặt `n` là số khóa phân biệt hiện có trong map. Bảng sau xét **Python `dict` dựa trên bảng băm**; giả định hash và phép so sánh một khóa có chi phí cơ bản hằng số và bảng băm vận hành ở mức tải phù hợp.

| Tác vụ | Thời gian điển hình | Bộ nhớ bổ sung |
| --- | --- | --- |
| Lấy `d.keys()`, `d.values()`, `d.items()` | `O(1)` | `O(1)` cho đối tượng view |
| Gọi `len(view)` | `O(1)` | `O(1)` |
| `key in d` hoặc `key in d.keys()` | Trung bình `O(1)` | `O(1)` |
| `value in d.values()` | `O(n)` trong tình huống cần duyệt nhiều mục | `O(1)` cho việc kiểm tra |
| `(key, value) in d.items()` | Trung bình `O(1)` khi tra khóa và so sánh giá trị có chi phí hằng số | `O(1)` |
| Duyệt toàn bộ một view | `O(n)` | `O(1)` cho iterator cơ bản |
| `list(d.keys())`, `list(d.values())`, `list(d.items())` | `O(n)` | `O(n)` |
| `dict(d)` hoặc `d.copy()` | `O(n)` | `O(n)` (bản sao nông) |
| `sorted(d.keys())` | `O(n log n)` nếu so sánh cơ bản hằng số | `O(n)` cho list kết quả |
| Phép giao hai tập khóa có `n` và `m` mục | Thường `O(n + m)` theo cách xây/tính tổng quát dựa trên hash set | Tùy kích thước tập kết quả |
| Tính tổng `sum(d.values())` | `O(n)` | `O(1)` |

Tạo view `O(1)` **không có nghĩa duyệt hoặc xuất toàn bộ view là `O(1)`**. View tránh sao chép khi chưa cần tiêu thụ dữ liệu, nhưng mỗi mục vẫn cần được xử lý khi thống kê, in ra hoặc tạo báo cáo.

Các nhận xét trên **không** cam kết chi phí xấu nhất cho mọi thao tác hash map: va chạm nhiều hoặc tái băm có thể làm một số thao tác chậm hơn. Với **tree map** cân bằng, một lần tra cứu khóa thường `O(log n)`, trong khi duyệt toàn bộ `n` mục theo thứ tự khóa là `O(n)`.

### Khi nào nên chọn view hay snapshot?

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Chỉ duyệt hoặc kiểm tra trên map đang có | View | Ít bộ nhớ phụ, luôn đọc trạng thái map hiện tại |
| Cần tiếp tục quan sát khóa sau khi map thay đổi | Giữ view | View phản ánh các lần thêm/xóa khóa |
| Cần danh sách ổn định để lọc/xóa trên map | `list(d)` hoặc bản sao | Không duyệt trực tiếp cấu trúc đang bị sửa |
| Cần báo cáo theo thời điểm | Snapshot thích hợp | Không tự cập nhật khi map thay đổi |
| Cần bảo đảm không thay đổi cả đối tượng lồng nhau | Deep copy hoặc dữ liệu bất biến | Snapshot nông vẫn chia sẻ tham chiếu |
| Cần giao diện đọc nhưng muốn map nền tiếp tục cập nhật | Read-only proxy/live view | Ngăn ghi qua giao diện, nhưng phản ánh thay đổi của gốc |
| Cần thứ tự khóa ổn định theo tiêu chí | `sorted(d.items(), key=...)` | Có tiêu chí sắp xếp rõ ràng |

Trong hệ thống có nhiều luồng, tiến trình hoặc giao dịch, **view không tự tạo ra một ảnh chụp nhất quán tại một thời điểm**. Ngay cả việc gọi `list(view)` có thể cần đồng bộ nếu map đang bị sửa đồng thời; muốn bảo đảm nhất quán cần cơ chế khóa, snapshot có kiểm soát hoặc giao dịch thích hợp.

## 13. Những nhầm lẫn thường gặp

1. **“`d.keys()` trả list khóa.”** Trong Python, nó trả một view sống; `list(d.keys())` mới tạo list.
2. **“Lấy view một lần thì nội dung được cố định.”** Không: view phản ánh map gốc khi đọc ở lần sau.
3. **“Mọi kết quả liên quan đến view đều động.”** Sai: `d.keys() & other` tạo một set kết quả mới và không tự cập nhật.
4. **“`d.values()` là một set.”** Sai: giá trị có thể lặp; phép kiểm tra thành viên trong values thường phải duyệt.
5. **“`len(d.values())` là số giá trị phân biệt.”** Sai: đây là số mục/khóa trong map.
6. **“View khóa của Python có thể thêm/xóa trực tiếp như set.”** Không có API `add`/`remove` tương ứng; phải sửa dict gốc.
7. **“Thêm hoặc xóa khóa trong vòng lặp trên `d.items()` luôn an toàn.”** Không: có thể gây `RuntimeError`; duyệt snapshot hoặc xây map mới.
8. **“Sao chép list các cặp là sao chép sâu mọi giá trị.”** Sai: các giá trị mutable có thể vẫn dùng chung tham chiếu.
9. **“Proxy chỉ đọc là bản sao bất biến.”** Không nhất thiết: `MappingProxyType` phản ánh thay đổi của dict gốc.
10. **“Các thư viện `Map` đều có view y hệt Python.”** Sai: Java có các collection view được chống lưng bởi map, JavaScript trả iterator.
11. **“`values().remove(value)` của Java xóa mọi khóa có giá trị ấy.”** Thao tác thông thường chỉ xóa một mục khớp.
12. **“Dữ liệu đọc qua view luôn là snapshot nhất quán khi nhiều luồng cập nhật.”** Không: cần thiết kế đồng bộ hoặc cơ chế snapshot/giao dịch riêng.

## 14. Tự luyện tập

**Bài 1.** Với `d = {"A": 1, "B": 2}`, tạo `keys = d.keys()` và `old_keys = list(d)`. Sau khi thêm `d["C"] = 3`, nội dung của hai biến khi đọc lại khác nhau ra sao?

**Bài 2.** Với `d = {"A": 1, "B": 1, "C": 2}`, cho biết `len(d.values())` và `len(set(d.values()))`. Giải thích nguyên nhân khác nhau.

**Bài 3.** Viết biểu thức Python để tìm các mã thuộc tập `required` nhưng chưa có trong khóa của map `grades`, không cần chuyển view khóa thành list.

**Bài 4.** Tại sao không nên viết `for k in d.keys(): del d[k]`? Viết hai cách thay thế để xóa các khóa có giá trị bằng `0`.

**Bài 5.** Với `d = {"A": 1}`, đặt `keys = d.keys()`, `shared = keys & {"A", "B"}`; thêm `d["B"] = 2`. Hãy cho biết `shared` có tự đổi không và cách lấy phép giao mới.

**Bài 6.** Cho `d = {"A": {"score": 8}}`. Lấy `snapshot = list(d.items())` rồi thực hiện `d["A"]["score"] = 10`. Giá trị bên trong snapshot là bao nhiêu? Nêu một cách lấy bản sao độc lập hơn.

**Bài 7.** Trong Java `Map` mutable, xóa một khóa bằng `keySet().remove(k)` sẽ ảnh hưởng tới map gốc hay chỉ ảnh hưởng view? Nêu cách xóa một mục an toàn trong khi duyệt `entrySet()` của `HashMap`.

**Bài 8.** JavaScript `Map.keys()` giống hoàn toàn `dict.keys()` của Python không? Một iterator sau khi duyệt hết có thể tái sử dụng để duyệt lại từ đầu không?

**Bài 9.** Với `n` mục trong Python `dict`, so sánh thời gian/bộ nhớ của `d.keys()` và `list(d.keys())`. Khi nào nên trả view thay vì snapshot?

**Bài 10.** Một dịch vụ quản lý học viên dùng `grades` và một chỉ mục phụ `grade → set(student_id)`. Nếu thay điểm của một học viên trong `grades`, chỉ mục phụ có tự cập nhật như `grades.items()` không? Cần làm gì?

<details>
<summary>Đáp án và gợi ý</summary>

1. `keys` thấy `A, B, C`; `old_keys` vẫn chỉ chứa `A, B` do nó là snapshot dạng list.
2. `len(d.values()) == 3`, còn `len(set(d.values())) == 2` vì giá trị `1` lặp ở hai khóa.
3. `missing = required.difference(grades.keys())` nếu `required` là set; kết quả là set mã còn thiếu.
4. Thay đổi kích thước dict khi iterator đang duyệt có thể gây `RuntimeError`. Có thể dùng `for k in list(d): ... del d[k]` hoặc `filtered = {k: v for k, v in d.items() if v != 0}` rồi thay map bằng map mới theo mục đích.
5. `shared` vẫn là `{"A"}`; thực hiện lại `keys & {"A", "B"}` để nhận `{"A", "B"}`.
6. Snapshot nông vẫn tham chiếu dict giá trị nên chứa `score = 10`. Dùng `copy.deepcopy(d)` nếu cần sao chép cả dữ liệu lồng nhau trong trường hợp thông thường.
7. Xóa qua `keySet()` được hỗ trợ thường xóa mục tương ứng khỏi map gốc. Dùng `Iterator<Map.Entry<K,V>>` trên `entrySet()` và gọi `iterator.remove()`.
8. Không. JavaScript trả một iterator có trạng thái tiêu thụ; sau khi hết cần gọi `map.keys()` để tạo iterator khác.
9. `d.keys()`: tạo view `O(1)` thời gian và bộ nhớ; `list(d.keys())`: `O(n)` thời gian và bộ nhớ. Dùng view khi cần quan sát map hiện tại và không yêu cầu kết quả cố định.
10. Không. Chỉ mục ngược là cấu trúc tính toán riêng; phải cập nhật cả hai trong cùng thao tác nghiệp vụ hoặc xây lại chỉ mục.

</details>

## Ghi nhớ

**View khóa, giá trị và cặp khóa–giá trị** cho phép nhìn cùng một map theo ba góc độ khác nhau. Trong Python, `dict.keys()`, `dict.values()` và `dict.items()` là **live views** phản ánh thay đổi của map gốc; chúng khác `list(...)` hay `dict.copy()` là các **bản sao nông**. Không thay đổi tập khóa khi đang duyệt trực tiếp iterator của dict/view; cần snapshot hoặc cách lọc an toàn. Hãy phân biệt **live view**, **iterator**, **snapshot** và **giao diện chỉ đọc**, đồng thời tính đúng chi phí duyệt, sao chép và đồng bộ nếu dữ liệu được cập nhật liên tục.
