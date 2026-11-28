# Đa ánh xạ và nhiều giá trị cho cùng một khóa

Một học viên có thể đăng ký **nhiều môn học**, một từ khóa có thể xuất hiện trong **nhiều tài liệu**, và một đỉnh đồ thị có thể nối tới **nhiều đỉnh khác**. Nếu dùng map thông thường với cặp `khóa → một giá trị`, việc gán liên tiếp những giá trị mới cho cùng khóa có thể ghi đè dữ liệu cũ. Ta cần cách biểu diễn **một khóa liên kết với nhiều giá trị**.

**Đa ánh xạ (multimap)** giải quyết nhu cầu đó. Bài học nằm trong chương **Tập hợp và ánh xạ** của module cấu trúc dữ liệu: ta sẽ làm rõ bất biến, thao tác, cách cài bằng map kết hợp list hoặc set, độ phức tạp thời gian và bộ nhớ, cùng những trường hợp ứng dụng như chỉ mục ngược và danh sách kề đồ thị.

## 1. Multimap là gì?

**Map** là một ánh xạ: mỗi khóa phân biệt chỉ có tối đa **một giá trị hiện tại**. Với một map Python thông thường:

```python
courses = {}
courses["HV01"] = "Python"
courses["HV01"] = "Cấu trúc dữ liệu"

print(courses)  # {'HV01': 'Cấu trúc dữ liệu'}
```

Phép gán thứ hai đã **thay** `"Python"`. Nếu muốn lưu toàn bộ môn học của `HV01`, ta có thể gắn khóa với **một tập hợp giá trị**:

```text
HV01 → [Python, Cấu trúc dữ liệu]
HV02 → [Python]
HV03 → [Thuật toán, Python]
```

Đó là một cách hiện thực **multimap**. Về mặt ADT, nó cho phép nhiều cặp liên kết cùng khóa; tại mức lưu trữ, ta vẫn có thể dùng một map mà mỗi khóa trỏ đến một collection:

```text
Map<Key, Collection<Value>>
```

Với cùng một khóa `k`, ta dùng `values(k)` để lấy các giá trị liên quan. **Khóa của map nền vẫn duy nhất**; nhiều giá trị nằm trong collection được gắn với khóa đó.

### Ví dụ trực quan

Cho các lượt đăng ký:

| Học viên | Môn học |
| --- | --- |
| `HV01` | `Python` |
| `HV02` | `Python` |
| `HV01` | `Cấu trúc dữ liệu` |
| `HV03` | `Thuật toán` |
| `HV01` | `Python` |

Có ít nhất hai cách hiểu hợp lệ, tùy bài toán:

- Nếu mỗi **sự kiện đăng ký** đều có ý nghĩa, kể cả một người đăng ký cùng môn nhiều lần, dùng **list**: `HV01 → [Python, Cấu trúc dữ liệu, Python]`.
- Nếu chỉ cần danh sách **môn học phân biệt** của mỗi học viên, dùng **set**: `HV01 → {Python, Cấu trúc dữ liệu}`.

**Multimap không mặc định quyết định có cho giá trị trùng hay giữ thứ tự hay không.** Đây là một phần của hợp đồng dữ liệu cần chọn khi thiết kế.

## 2. Phân biệt multimap với map, set và multiset

| Cấu trúc | Mô hình | Bảo toàn thông tin nào? |
| --- | --- | --- |
| **Map** | `k → v` | Mỗi khóa có một giá trị hiện tại; ghi lại khóa thường thay giá trị |
| **Set** | Tập các phần tử phân biệt | Một phần tử có xuất hiện không |
| **Multiset (bag)** | `x → số lần xuất hiện` | Số bản sao của mỗi phần tử |
| **Multimap** | `k → collection các v` | Những giá trị nào liên kết với mỗi khóa |

**Multiset** đếm số lần xuất hiện của **cùng một giá trị**. **Multimap** gom **các giá trị liên quan theo khóa**. Multimap dùng list có thể chứa bản sao, nhưng nó vẫn giữ nội dung từng giá trị, thay vì chỉ số đếm.

Ví dụ:

```text
Danh sách sự kiện: [(HV01, Python), (HV01, Thuật toán), (HV01, Python)]

Multiset theo môn:    {Python × 2, Thuật toán × 1}
Multimap theo học viên:
    HV01 → [Python, Thuật toán, Python]
```

Multimap cũng khác **map hai chiều (bidirectional map)**: một bidirectional map thường áp đặt quy tắc để tra ngược giá trị một cách duy nhất, trong khi multimap cho phép nhiều giá trị cho một khóa và nhiều khóa có cùng một giá trị.

### Quan hệ với mô hình một–nhiều

Trong cơ sở dữ liệu, `học viên → danh sách môn học` là một cách nhìn theo khóa về quan hệ đăng ký. Với quan hệ **nhiều–nhiều** (nhiều học viên học nhiều môn), ta có thể tạo thêm một chỉ mục ngược `môn học → các học viên`. Hai chiều chỉ mục là các cấu trúc bổ sung, không tự đồng bộ nếu ta thay đổi một bên mà bỏ quên bên kia.

## 3. Bất biến cần quyết định trước khi cài đặt

Multimap thường cần những bất biến sau:

1. **Mỗi khóa phân biệt được lưu một lần** trong map nền, rồi trỏ tới collection liên quan.
2. **Mọi giá trị trong collection thuộc về đúng khóa đang xét**; thêm hoặc xóa một liên kết không được làm thay đổi collection của khóa khác ngoài ý muốn.
3. **Tính trùng lặp** được xác định rõ: list cho phép lặp; set không cho các giá trị được coi là bằng nhau lặp lại.
4. **Thứ tự** được xác định rõ: list giữ thứ tự chèn các giá trị trong từng khóa; set thông thường không bảo đảm thứ tự.
5. **Khóa có collection rỗng** là hợp lệ hay phải loại bỏ? Với một cách cài chuẩn hóa thông dụng, không lưu khóa khi số giá trị về 0.

Ví dụ dùng map của list:

```text
{
    "A": [1, 1, 2],
    "B": [2],
}
```

Ở đây:

- `distinctKeyCount = 2`: có hai khóa `A` và `B`.
- `associationCount = 4`: có bốn **lượt liên kết** nếu tính cả hai bản sao của `(A, 1)`.
- `values(A)` chứa ba mục, còn `values(B)` chứa một mục.
- Giá trị `2` được phép xuất hiện dưới **cả hai khóa**.

Với map của set `{"A": {1, 2}, "B": {2}}`, số liên kết phân biệt là `3`. Vì vậy, “kích thước multimap” có thể ám chỉ **số khóa** hoặc **số cặp liên kết** tùy API; nên dùng tên rõ nghĩa như `keyCount()` và `pairCount()`.

### Giữ hay xóa khóa khi collection rỗng?

Giả sử `HV01` đã hủy tất cả môn học. Ta có thể chọn:

- **Chuẩn hóa**: xóa khóa `HV01` khỏi map khi danh sách môn học rỗng. Khi đó `key in mapping` tương đương “khóa có ít nhất một giá trị”.
- **Giữ khóa rỗng**: vẫn lưu `"HV01": []` để biểu thị học viên tồn tại nhưng chưa đăng ký môn nào. Khi đó, `key in mapping` và “khóa có liên kết nào không?” là hai câu hỏi khác nhau.

Cả hai cách có thể đúng nếu hợp đồng thống nhất. Đặc biệt trong đồ thị, ta thường **giữ đỉnh không có cạnh kề** để bảo toàn thông tin rằng đỉnh vẫn tồn tại.

## 4. Những thao tác thường gặp của Multimap ADT

Cách đặt tên và xử lý lỗi có thể khác nhau giữa các thư viện. Với multimap có giá trị theo kiểu list, một giao diện minh họa là:

| Thao tác | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `add(k, v)` | Thêm một liên kết từ `k` tới `v` | Có thể thêm bản sao thứ hai của `v` |
| `getAll(k)` | Lấy tất cả giá trị liên kết với `k` | Với khóa thiếu có thể trả collection rỗng |
| `containsKey(k)` | Kiểm tra khóa đã được lưu hay chưa | Phụ thuộc quy tắc về collection rỗng |
| `containsEntry(k, v)` | Kiểm tra có liên kết `(k, v)` | Có thể cần duyệt collection |
| `removeOne(k, v)` | Xóa một bản sao của liên kết | Nếu có nhiều bản sao thì còn những bản sao khác |
| `removeAll(k, v)` | Xóa mọi bản sao của giá trị `v` tại khóa `k` | Hữu ích khi cần xóa hết giá trị lặp |
| `removeKey(k)` | Xóa toàn bộ các giá trị của `k` | Tác động tới mọi liên kết của khóa đó |
| `keys()`, `entries()` | Duyệt các khóa hoặc các liên kết | Định nghĩa rõ bản sao có được trả lặp không |
| `keyCount()`, `pairCount()` | Đếm khóa và tổng liên kết | Hai con số thường khác nhau |

**Thêm liên kết** không giống **thay toàn bộ collection**. Với một map của list, lời gọi `append` thêm một mục; còn câu lệnh `mapping[k] = [v]` có thể xóa hết các giá trị cũ. Đó là sự khác nhau quan trọng nhất khi chuyển từ map thông thường sang multimap.

Giả mã thêm liên kết:

```text
ADD(M, k, v):
    nếu k chưa tồn tại trong M:
        M[k] = collection rỗng mới
    thêm v vào M[k] theo chính sách của collection

GET_ALL(M, k):
    nếu k chưa tồn tại:
        trả collection rỗng, không làm thay đổi M
    trả các giá trị đã gắn với k
```

Nếu collection là **set**, thao tác thêm giá trị trùng không tăng số liên kết. Nếu là **list**, thao tác thêm mỗi lần có thể tăng số liên kết lên một.

## 5. Cài đặt đơn giản bằng `dict` của `list`

Python không có kiểu built-in tên `multimap`, nhưng có thể tạo một multimap bằng `dict` với giá trị là list.

```python
enrollments = {}

def add_enrollment(student_id, course):
    if student_id not in enrollments:
        enrollments[student_id] = []
    enrollments[student_id].append(course)

add_enrollment("HV01", "Python")
add_enrollment("HV02", "Python")
add_enrollment("HV01", "Cấu trúc dữ liệu")
add_enrollment("HV01", "Python")

print(enrollments["HV01"])
# ['Python', 'Cấu trúc dữ liệu', 'Python']
print(enrollments["HV02"])  # ['Python']
```

Mỗi khóa chỉ xuất hiện một lần trong `dict`, nhưng list dưới khóa ấy giữ nhiều giá trị theo thứ tự chèn. Nếu muốn giữ **một** cặp `(HV01, Python)` bất kể số lần đăng ký, nên dùng set trong vai trò collection.

### Dùng `setdefault` và `defaultdict`

Hai cách rút ngắn việc tạo collection cho khóa mới:

```python
records = [
    ("HV01", "Python"),
    ("HV02", "Thuật toán"),
    ("HV01", "Cấu trúc dữ liệu"),
]

# Cách 1: setdefault
by_student = {}
for student_id, course in records:
    by_student.setdefault(student_id, []).append(course)

print(by_student["HV01"])  # ['Python', 'Cấu trúc dữ liệu']

# Cách 2: defaultdict
from collections import defaultdict

by_student2 = defaultdict(list)
for student_id, course in records:
    by_student2[student_id].append(course)

print(by_student2["HV01"])  # ['Python', 'Cấu trúc dữ liệu']
```

Có một khác biệt quan trọng:

```python
from collections import defaultdict

groups = defaultdict(list)

print(groups.get("HV99"))  # None: không tạo khóa
print("HV99" in groups)    # False

print(groups["HV99"])      # []: tự tạo khóa rỗng
print("HV99" in groups)    # True
```

Vì `defaultdict` có thể tự thêm khóa khi truy cập `groups[k]`, hãy dùng `get` nếu mục tiêu chỉ là **đọc mà không thay đổi trạng thái**. Còn `setdefault(k, [])` chủ động thêm khóa rỗng nếu chưa có; việc tạo list mặc định xảy ra trước khi gọi hàm, dù khóa có thể đã tồn tại.

### Tránh dùng chung một list cho nhiều khóa

Đây là lỗi tham chiếu chung khi cài map của list:

```python
keys = ["HV01", "HV02"]
wrong = dict.fromkeys(keys, [])  # Cùng tham chiếu tới MỘT list
wrong["HV01"].append("Python")

print(wrong)
# {'HV01': ['Python'], 'HV02': ['Python']} — lỗi lan sang HV02

correct = {student_id: [] for student_id in keys}
correct["HV01"].append("Python")
print(correct)
# {'HV01': ['Python'], 'HV02': []}
```

Một cách cài đúng phải tạo **collection riêng** cho từng khóa. Nếu dùng đối tượng giá trị có thể thay đổi, cũng cần xét đến việc nhiều nơi cùng tham chiếu chính đối tượng đó.

## 6. Cài đặt một lớp Multimap có hợp đồng rõ ràng

Lớp dưới đây chọn **list semantics**: cho phép giá trị trùng, giữ thứ tự trong từng khóa, xóa một bản sao theo giá trị, và loại khóa khi list trở nên rỗng.

```python
class ListMultimap:
    def __init__(self):
        self._data = {}
        self._pair_count = 0

    def add(self, key, value):
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(value)
        self._pair_count += 1

    def get_all(self, key):
        # Trả tuple mới: người gọi không thể append vào list nội bộ.
        return tuple(self._data.get(key, ()))

    def contains_key(self, key):
        return key in self._data

    def remove_one(self, key, value):
        values = self._data.get(key)
        if values is None:
            return False

        try:
            values.remove(value)  # Chỉ xóa bản sao đầu tiên bằng value
        except ValueError:
            return False

        self._pair_count -= 1
        if not values:
            del self._data[key]
        return True

    def remove_key(self, key):
        values = self._data.pop(key, None)
        if values is None:
            return 0
        removed = len(values)
        self._pair_count -= removed
        return removed

    def key_count(self):
        return len(self._data)

    def pair_count(self):
        return self._pair_count


mm = ListMultimap()
mm.add("HV01", "Python")
mm.add("HV01", "Python")
mm.add("HV01", "Thuật toán")
mm.add("HV02", "Python")

assert mm.get_all("HV01") == ("Python", "Python", "Thuật toán")
assert mm.key_count() == 2
assert mm.pair_count() == 4

assert mm.remove_one("HV01", "Python")
assert mm.get_all("HV01") == ("Python", "Thuật toán")
assert mm.pair_count() == 3

assert mm.remove_key("HV02") == 1
assert mm.get_all("HV02") == ()
assert not mm.contains_key("HV02")
assert mm.key_count() == 1
assert mm.pair_count() == 2
```

**Bất biến** được duy trì: `_pair_count` bằng tổng độ dài của các list; khóa có list rỗng bị xóa. Hàm `get_all` trả một tuple mới để tránh người gọi tự thay đổi cấu trúc list bên trong. Đây là **bản sao nông**: nếu các phần tử trong list là đối tượng có thể thay đổi, người gọi vẫn có thể sửa chính đối tượng phần tử. Khi cần ngăn điều đó, phải quy định kiểu giá trị bất biến hoặc chính sách sao chép sâu phù hợp.

Trong `remove_one`, `list.remove(value)` tìm từ đầu list rồi xóa mục khớp đầu tiên; nếu có nhiều giá trị trùng, những bản sao còn lại vẫn tồn tại. Lớp này minh họa thao tác trong bối cảnh tuần tự; nó chưa có bảo đảm đồng bộ cho nhiều luồng.

## 7. Dùng set để lưu giá trị phân biệt theo khóa

Một số bài toán chỉ muốn **mỗi liên kết `(k, v)` xuất hiện tối đa một lần**. Ví dụ một học viên chỉ cần ghi nhận “đã đăng ký môn X” cho dù yêu cầu đăng ký được gửi lặp lại.

```python
from collections import defaultdict

courses_by_student = defaultdict(set)

registrations = [
    ("HV01", "Python"),
    ("HV01", "Python"),
    ("HV01", "Thuật toán"),
    ("HV02", "Python"),
]

for student_id, course in registrations:
    courses_by_student[student_id].add(course)

print(sorted(courses_by_student["HV01"]))
# ['Python', 'Thuật toán']
print(len(courses_by_student["HV01"]))  # 2
```

Khi dùng `set`, cả **khóa map** và **giá trị trong set** đều phải hashable theo quy tắc Python; list hoặc dict không thể thêm trực tiếp vào `set`.

Nếu chỉ cần kiểm tra một học viên có đăng ký môn hay không, `course in courses_by_student[student_id]` trung bình `O(1)` với set. Nhưng thứ tự duyệt set không được bảo đảm; nếu cần hiển thị theo thứ tự học viên đăng ký, list hoặc một cấu trúc lưu thứ tự khác phù hợp hơn.

Một phiên bản “thêm liên kết nếu chưa có” có thể viết:

```python
def add_unique(mapping, key, value):
    if key not in mapping:
        mapping[key] = set()
    old_size = len(mapping[key])
    mapping[key].add(value)
    return len(mapping[key]) > old_size  # True nếu liên kết mới

links = {}
assert add_unique(links, "HV01", "Python") is True
assert add_unique(links, "HV01", "Python") is False
assert links == {"HV01": {"Python"}}
```

Trong set multimap, thao tác `remove_one` và `remove_all` cho cùng một cặp khóa–giá trị là tương đương, vì không có nhiều bản sao.

## 8. Phân biệt khóa thiếu, khóa rỗng và giá trị hợp lệ rỗng

Multimap có hai tầng hiện diện:

1. **Khóa có trong map hay không?**
2. **Có giá trị cụ thể nào trong collection của khóa hay không?**

Ví dụ:

```python
mapping = {
    "HV01": [],              # Có khóa nhưng chưa có môn
    "HV02": [None],          # Có khóa và một giá trị None
    "HV03": ["Python"],      # Có khóa và một môn
}

print("HV01" in mapping)       # True
print(len(mapping["HV01"]))    # 0

print("HV02" in mapping)       # True
print(mapping["HV02"])         # [None] — một phần tử, dù là None

print("HV99" in mapping)       # False
print(mapping.get("HV99", []))  # [] — không chứng minh khóa có tồn tại
```

Nếu API `getAll(k)` trả collection rỗng khi khóa thiếu, thì kết quả rỗng không thể phân biệt **khóa vắng mặt** với **khóa hiện diện nhưng không có giá trị** khi chính sách lưu cho phép collection rỗng. Khi nghiệp vụ cần tách hai trạng thái, cung cấp `containsKey` hoặc kiểu kết quả có nhãn.

Cũng cần xác định liệu bản thân `None`, chuỗi rỗng `""` hoặc số `0` có được dùng như **một giá trị hợp lệ trong collection** hay không. **Collection rỗng** và **collection chứa một phần tử rỗng** khác nhau: `[]` có 0 liên kết; `[None]` có 1 liên kết.

## 9. Ứng dụng 1: xây dựng chỉ mục ngược

Một **chỉ mục ngược** (*inverted index*) nối mỗi từ khóa với các tài liệu có chứa từ đó. Đây là một multimap tự nhiên:

```text
python    → {doc1, doc2}
graph     → {doc2, doc3}
structure → {doc1}
```

Dùng set để mỗi tài liệu chỉ xuất hiện một lần trong danh sách kết quả của mỗi từ khóa:

```python
from collections import defaultdict

documents = {
    "doc1": "python structure python",
    "doc2": "python graph",
    "doc3": "graph",
}

index = defaultdict(set)

for doc_id, text in documents.items():
    for word in text.split():
        index[word].add(doc_id)

print(sorted(index["python"]))  # ['doc1', 'doc2']
print(sorted(index["graph"]))   # ['doc2', 'doc3']

# Tài liệu chứa đồng thời cả "python" và "graph"
result = index.get("python", set()) & index.get("graph", set())
print(sorted(result))           # ['doc2']
```

`doc1` chứa từ `python` hai lần, nhưng **chỉ liên kết với từ khóa ấy một lần** do dùng set. Nếu ứng dụng muốn đo số lần xuất hiện trong từng tài liệu, có thể thay giá trị bằng map tần suất, chẳng hạn `word → {doc_id: frequency}`. Chọn list, set hay map phụ thuộc câu hỏi nghiệp vụ.

## 10. Ứng dụng 2: danh sách kề đồ thị

Đồ thị có thể lưu các đỉnh kề của mỗi đỉnh trong một cấu trúc `vertex → neighbors`:

```python
adjacency = {
    "A": ["B", "C"],
    "B": ["C"],
    "C": [],
    "D": [],
}

for vertex, neighbors in adjacency.items():
    print(vertex, "→", neighbors)
```

Cấu trúc này là **map của các collection** và có thể được xem như một cách dùng ý tưởng multimap. Đỉnh `C` và `D` vẫn tồn tại trong đồ thị dù list kề rỗng. Nếu chọn chính sách “xóa khóa khi không còn giá trị”, ta phải lưu tập đỉnh riêng để không làm mất thông tin đỉnh cô lập.

- Với **đồ thị đơn**, có thể dùng set để tránh cạnh kề trùng; danh sách kề dùng set phù hợp khi cần tra nhanh một cạnh có tồn tại không.
- Với **đa đồ thị**, có thể có nhiều cạnh cùng cặp đầu mút; list các cạnh hoặc các mã cạnh riêng giúp giữ thông tin bản sao.
- Với **đồ thị có trọng số**, giá trị có thể là các cặp `(neighbor, weight)` hoặc đối tượng cạnh thay vì chỉ là mã đỉnh.

Với `V` đỉnh và `E` cạnh, biểu diễn danh sách kề thông thường cần `O(V + E)` bộ nhớ (nếu lưu mỗi đỉnh và mỗi cạnh một số lần hằng định). Đây là ví dụ điển hình của việc chọn cấu trúc dựa trên yêu cầu bất biến và thao tác.

## 11. Độ phức tạp của multimap

Đặt `d` là số khóa phân biệt, `m_k` là số giá trị gắn với khóa `k`, và `P = Σ_k m_k` là tổng số liên kết (tính cả bản sao nếu dùng list). Giả định map nền là **hash map** với phép băm/so sánh khóa tốn thời gian hằng số trung bình.

| Thao tác | Map của list | Map của set |
| --- | --- | --- |
| Tìm collection theo khóa | `O(1)` trung bình | `O(1)` trung bình |
| Thêm liên kết `(k, v)` | `O(1)` trung bình và khấu hao cho `append` | `O(1)` trung bình |
| Kiểm tra có `v` dưới khóa `k` | `O(m_k)` | `O(1)` trung bình |
| Xóa một `v` dưới khóa `k` | `O(m_k)` do tìm và dịch phần tử | `O(1)` trung bình |
| Xóa toàn bộ khóa `k` | `O(1)` cho thao tác bỏ mục map; giải phóng collection có thể phụ thuộc `m_k` | Tương tự |
| Duyệt tất cả liên kết | `O(P)` | `O(P)` |
| Lấy bản sao tất cả giá trị của một khóa | `O(m_k)` | `O(m_k)` |
| Tổng bộ nhớ lưu liên kết và khóa | `O(d + P)` | `O(d + P)` |

Các đánh giá trên phụ thuộc thao tác và hiện thực: `get_all` của lớp `ListMultimap` ở trên **tạo tuple mới**, nên riêng lời gọi đó tốn `O(m_k)` thời gian và bộ nhớ; một API trả view có thể chỉ tốn `O(1)` để tạo view nhưng sẽ có quy tắc khác về tính thay đổi của dữ liệu. Khi xóa khóa, một số môi trường cần duyệt hoặc giải phóng các phần tử bên trong collection; không nên mặc định mọi chi phí dọn dẹp đều là `O(1)`.

Hash map có thể gặp va chạm băm hoặc tái băm, nên `O(1)` không phải bảo đảm thời gian tệ nhất cho mọi đầu vào. Nếu cần duyệt **khóa theo thứ tự**, có thể dùng tree map để tra cứu khóa trong `O(log d)`; giá trị trong mỗi khóa vẫn có thể là list/set tùy yêu cầu.

### Bài toán lập chỉ mục từ `n` cặp dữ liệu

Với `n` cặp đầu vào, xây dựng `dict` của list thường tốn thời gian trung bình `O(n)`, bộ nhớ `O(d + n)`. Với `dict` của set, thời gian trung bình cũng thường `O(n)` khi cả khóa và giá trị hashable; số liên kết thực lưu `P` có thể nhỏ hơn `n` do loại cặp trùng, nên bộ nhớ là `O(d + P)`.

Nếu số giá trị gắn một khóa rất lớn, việc tìm hoặc xóa một giá trị cụ thể khỏi list có thể là nút thắt `O(m_k)`. Khi đó, dùng set cho giá trị phân biệt hoặc một chỉ mục bổ trợ sẽ phù hợp hơn, miễn là quy tắc trùng lặp và thứ tự cho phép.

## 12. Những lỗi thường gặp

1. **Gán trực tiếp `mapping[k] = v` khi muốn thêm một giá trị:** phép gán thông thường có thể thay toàn bộ collection đang có.
2. **Dùng list khi cần loại cặp trùng:** thêm cùng giá trị hai lần làm list chứa hai bản sao; dùng set nếu nghiệp vụ chỉ cần liên kết duy nhất.
3. **Dùng set khi phải giữ thứ tự hoặc số lần lặp:** set sẽ loại các bản sao, và thứ tự duyệt không được bảo đảm.
4. **Chia sẻ cùng một list/set giữa nhiều khóa:** sửa collection dưới một khóa có thể vô tình thay đổi collection của khóa khác.
5. **Nhầm tổng liên kết với số khóa:** `len(mapping)` đếm số khóa; muốn tổng số mục trong các collection, cần tính `sum(len(v) for v in mapping.values())` hoặc duy trì biến tổng.
6. **Dùng `defaultdict(list)[missing]` chỉ để tra cứu:** truy cập có thể tạo khóa mới rỗng.
7. **Xóa giá trị cuối nhưng quên xử lý khóa rỗng:** hãy thống nhất chính sách xóa hay giữ khóa, đặc biệt với đỉnh đồ thị cô lập.
8. **Trả collection nội bộ có thể thay đổi ra ngoài:** người gọi có thể sửa list/set mà bỏ qua kiểm soát bất biến, bộ đếm hoặc kiểm tra dữ liệu của lớp.
9. **Thay đổi multimap khi đang duyệt các khóa của map Python:** thêm/xóa khóa trong vòng lặp trên `dict` có thể gây lỗi; nếu cần, duyệt bản sao danh sách khóa hoặc xây cấu trúc mới.
10. **Giả định phép kiểm tra rồi thêm là nguyên tử trong hệ thống đồng thời:** một hash map thông thường không tự bảo đảm giao dịch cho nhiều tác nhân cùng cập nhật; cần đồng bộ hoặc API nguyên tử theo nền tảng.

## 13. Tự luyện tập

**Bài 1.** Với các cặp `(A, 1), (A, 2), (B, 2), (A, 1)`, hãy viết kết quả dưới dạng map của list và map của set. Số khóa và số liên kết ở hai cách khác nhau thế nào?

**Bài 2.** Một học viên có `["Python", "Python", "Thuật toán"]`. Nếu phải lưu cả ba **lượt đăng ký**, nên dùng list hay set? Nếu chỉ lưu **môn phân biệt** thì sao?

**Bài 3.** Giải thích sự khác nhau giữa `removeOne("A", 1)` và `removeKey("A")` với `A → [1, 1, 2]`.

**Bài 4.** Một `defaultdict(list)` rỗng nhận lời gọi `d["unknown"]`. Tại sao sau đó `"unknown" in d` có thể đúng dù chưa thêm liên kết nào?

**Bài 5.** Thiết kế một multimap `từ khóa → tập mã tài liệu`. Đầu vào có từ khóa lặp trong cùng một tài liệu. Nêu cách ngăn tài liệu lặp trong kết quả và độ phức tạp trung bình khi xây chỉ mục từ `n` lượt từ khóa.

**Bài 6.** Với `d` khóa và tổng `P` liên kết, vì sao thao tác kiểm tra một giá trị nằm dưới khóa `k` có thể tốn `O(m_k)` bằng list nhưng chỉ `O(1)` trung bình bằng set?

**Bài 7.** Trong đồ thị lưu `A → ["B"]` và `B → []`, nếu xóa cạnh `A → B` làm list của `A` trở thành rỗng, có nên xóa luôn khóa `A` không? Giải thích lựa chọn theo bất biến.

<details>
<summary>Đáp án tham khảo</summary>

1. Map của list: `{A: [1, 2, 1], B: [2]}`, có 2 khóa và 4 lượt liên kết. Map của set: `{A: {1, 2}, B: {2}}`, có 2 khóa và 3 liên kết phân biệt.
2. List nếu cần số lần và thứ tự lượt đăng ký; set nếu chỉ cần tập môn học phân biệt.
3. `removeOne("A", 1)` chỉ bỏ một bản sao `1`, còn `A → [1, 2]`. `removeKey("A")` bỏ toàn bộ liên kết và xóa khóa `A`.
4. Truy cập `d["unknown"]` kích hoạt factory `list`, tự tạo khóa có list rỗng. Dùng `d.get("unknown")` để tra cứu mà không thêm.
5. Dùng `defaultdict(set)` rồi gọi `index[word].add(doc_id)`. Mỗi tài liệu chỉ xuất hiện một lần dưới mỗi từ khóa; xây chỉ mục trung bình `O(n)` khi hash/so sánh có chi phí cơ bản hằng số.
6. List phải duyệt tuần tự tối đa `m_k` giá trị; set tra cứu theo băm trung bình hằng số nếu giá trị hashable và hash phân bố hợp lý.
7. Nếu map là nơi duy nhất lưu toàn bộ đỉnh, giữ `A: []` để bảo toàn đỉnh `A`. Chỉ xóa khóa rỗng nếu đỉnh được lưu độc lập hoặc quy ước mỗi khóa chỉ tồn tại khi có cạnh và việc mất khóa không làm mất thông tin cần giữ.

</details>

## Ghi nhớ

**Multimap cho phép một khóa liên kết với nhiều giá trị** bằng mô hình `khóa → collection các giá trị`. Chọn **list** khi cần giữ thứ tự hoặc bản sao; chọn **set** khi cần các liên kết phân biệt và tra cứu thành viên nhanh. Xác định rõ chính sách về khóa rỗng, số khóa và tổng liên kết trước khi viết thao tác thêm/xóa. Với hash map làm nền, việc nhóm `n` cặp dữ liệu thường tốn `O(n)` thời gian trung bình và `O(d + P)` bộ nhớ, trong đó `d` là số khóa phân biệt và `P` là số liên kết lưu thực tế.
