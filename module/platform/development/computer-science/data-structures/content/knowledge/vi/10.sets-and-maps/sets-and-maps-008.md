# Thứ tự chèn, thứ tự sắp xếp và thứ tự duyệt không được bảo đảm

Một hệ thống học tập nhận lần lượt các mã học viên `HV03`, `HV01`, `HV03`, `HV02`. Khi cần kiểm tra mã đã xuất hiện hay chưa, **set** là lựa chọn tự nhiên vì loại được phần tử trùng. Nhưng nếu cần in báo cáo theo **thứ tự đăng ký** hoặc theo **mã tăng dần**, ta phải phân biệt rõ ba khái niệm: **thứ tự chèn**, **thứ tự sắp xếp** và **thứ tự duyệt**.

Đây là bài học thuộc chương **Tập hợp và ánh xạ** của module cấu trúc dữ liệu. Mục tiêu là hiểu điều gì được **kiểu dữ liệu trừu tượng (ADT)** bảo đảm, điều gì phụ thuộc **hiện thực cụ thể**, và khi nào phải chủ động sắp xếp hoặc lưu thêm thứ tự. Những quyết định này ảnh hưởng trực tiếp đến tính đúng đắn, khả năng tái lập kết quả và độ phức tạp thời gian, bộ nhớ.

## 1. Ba khái niệm về thứ tự cần phân biệt

Giả sử các mã được đưa vào theo dãy:

```text
Lần lượt nhận: HV03, HV01, HV03, HV02
```

Ta có ba cách nói về thứ tự:

| Khái niệm | Câu hỏi | Kết quả minh họa |
| --- | --- | --- |
| **Thứ tự chèn** (*insertion order*) | Giá trị phân biệt được thêm lần đầu theo trình tự nào? | `HV03, HV01, HV02` |
| **Thứ tự sắp xếp** (*sorted order*) | Các giá trị đứng theo quy tắc so sánh nào? | `HV01, HV02, HV03` |
| **Thứ tự duyệt** (*iteration order*) | Khi gọi vòng lặp, chương trình thực sự gặp các phần tử theo trình tự nào? | Phụ thuộc cấu trúc và hợp đồng thư viện |

**Thứ tự chèn** phản ánh thời điểm xuất hiện đầu tiên của mỗi khóa/phần tử. **Thứ tự sắp xếp** do một quy tắc so sánh quyết định, ví dụ mã tăng dần. **Thứ tự duyệt** là thứ tự mà API `iterator` hoặc vòng lặp cung cấp; tùy cấu trúc, nó có thể trùng với một trong hai thứ tự trên hoặc không có bảo đảm nào.

Trong một số trường hợp, thứ tự duyệt tình cờ trông giống thứ tự chèn hoặc thứ tự tăng dần. **Quan sát vài lần chạy không biến hiện tượng ấy thành bảo đảm của API.**

### Bất biến của Set/Map và yêu cầu thứ tự là hai việc khác nhau

- **Set ADT** bảo đảm một phần tử phân biệt xuất hiện tối đa một lần và hỗ trợ kiểm tra thành viên, thêm, xóa. ADT cơ bản **không bắt buộc** các phần tử được duyệt theo thứ tự chèn hay thứ tự sắp xếp.
- **Map ADT** bảo đảm mỗi khóa phân biệt gắn với tối đa một giá trị hiện tại. ADT cơ bản **không bắt buộc** các khóa được duyệt theo một thứ tự cụ thể.
- **Một hiện thực cụ thể** có thể cung cấp thêm cam kết: giữ thứ tự chèn, sắp theo khóa, hoặc hoàn toàn không bảo đảm thứ tự duyệt.

Không có mâu thuẫn khi một map vừa giữ khóa duy nhất, vừa giữ thứ tự chèn: tính duy nhất là bất biến lõi, còn thứ tự chèn là **đặc tính bổ sung** của hiện thực.

## 2. Một bảng so sánh những hiện thực phổ biến

| Cấu trúc hoặc kiểu cụ thể | Thứ tự duyệt được bảo đảm | Điểm cần nhớ |
| --- | --- | --- |
| Python `set`, `frozenset` | **Không có bảo đảm về thứ tự** | Không dựa vào kết quả `for x in s` cho nghiệp vụ cần thứ tự |
| Python `dict` từ Python 3.7 | **Thứ tự chèn của khóa** | Thay giá trị khóa cũ không đổi vị trí; xóa rồi chèn lại sẽ đặt khóa ở cuối |
| Java `HashSet`, `HashMap` | **Không bảo đảm thứ tự duyệt** | Không suy ra thứ tự từ cách bảng băm lưu trữ |
| Java `LinkedHashSet`, `LinkedHashMap` | Theo **thứ tự chèn** ở cấu hình mặc định | `LinkedHashMap` còn có thể được cấu hình theo thứ tự truy cập |
| Java `TreeSet`, `TreeMap` | Theo **thứ tự so sánh khóa/phần tử** | Cần bộ so sánh hoặc thứ tự tự nhiên phù hợp |
| JavaScript `Set`, `Map` | Theo **thứ tự chèn** | Đây là đặc tính được quy định cho các collection này |
| C++ `std::unordered_set`, `std::unordered_map` | **Không bảo đảm thứ tự duyệt** | Các cấu trúc dựa trên băm |
| C++ `std::set`, `std::map` | Theo **thứ tự so sánh khóa/phần tử** | Thường được hiện thực bằng cây tìm kiếm cân bằng |

Bảng trên nói về **hợp đồng của các kiểu cụ thể**, không phải mọi collection của mỗi ngôn ngữ. Riêng `LinkedHashMap` có chế độ duyệt theo thứ tự truy cập; nếu bật chế độ đó, thao tác truy cập có thể làm thay đổi vị trí một mục. Trong C++, thứ tự của `std::map` là thứ tự của bộ so sánh, mặc định thường là tăng dần theo `std::less`, chứ không nhất thiết là “thứ tự chữ cái” trong mọi miền khóa.

## 3. Python `set`: duy nhất nhưng không có cam kết thứ tự

`set` của Python được thiết kế để quản lý các phần tử hashable phân biệt và tra cứu thành viên nhanh. Vòng lặp được phép duyệt mọi phần tử nhưng **không có hợp đồng bảo đảm trình tự**.

```python
codes = {"HV03", "HV01", "HV02"}

# Đúng: kiểm tra sự hiện diện và số lượng
assert "HV01" in codes
assert len(codes) == 3

# Đúng: kiểm tra nội dung tập hợp, không phụ thuộc thứ tự
assert codes == {"HV01", "HV02", "HV03"}

# Có thể duyệt, nhưng thứ tự không được bảo đảm:
for code in codes:
    print(code)
```

Các lỗi thường gặp là:

```python
codes = {"HV03", "HV01", "HV02"}

# Không nên dùng kết quả đầu tiên làm "mã nhỏ nhất"
arbitrary_code = next(iter(codes))

# Không nên coi đây là bản ghi đầu tiên được chèn
some_code = codes.pop()   # Xóa và trả một phần tử tùy ý
```

Hai thao tác trên **không** được mô tả là lấy phần tử đầu tiên theo thứ tự chèn, phần tử nhỏ nhất hoặc lớn nhất. Muốn tìm mã nhỏ nhất theo so sánh chuỗi, có thể dùng `min(codes)`; nếu muốn liệt kê toàn bộ theo thứ tự, dùng `sorted(codes)`.

### Vì sao `set` đôi khi trông như đã sắp xếp?

Với một số tập số nguyên nhỏ, kết quả duyệt có thể tình cờ xuất hiện theo thứ tự tăng dần:

```python
numbers = {3, 1, 2}

# Không viết một kiểm thử phụ thuộc vào thứ tự duyệt:
# assert list(numbers) == [1, 2, 3]  # Không có cam kết
assert sorted(numbers) == [1, 2, 3]    # Có yêu cầu sắp xếp rõ ràng
```

Thứ tự duyệt của set có thể phụ thuộc cách băm, vị trí trong bảng, kích thước bảng, những thao tác thêm/xóa trước đó, phiên bản trình thông dịch và các yếu tố khi chạy. Với chuỗi trong Python, cơ chế ngẫu nhiên hóa hàm băm còn có thể làm thứ tự quan sát được khác nhau giữa các lần chạy tiến trình.

Một set **không bị thay đổi** thường có thứ tự duyệt ổn định trong cùng tiến trình với cùng trạng thái hiện thực, nhưng đây không phải cơ sở để viết chương trình yêu cầu thứ tự kết quả tái lập giữa môi trường hoặc lần chạy.

## 4. Python `dict`: thứ tự chèn là cam kết cụ thể

Từ **Python 3.7**, ngôn ngữ bảo đảm `dict` duyệt các khóa theo **thứ tự chúng được chèn lần đầu**. Khi lặp trực tiếp trên dict, ta nhận các **khóa**; khi lặp qua `items()`, ta nhận các **cặp khóa–giá trị** cũng theo thứ tự khóa.

```python
scores = {}

scores["HV03"] = 8.0
scores["HV01"] = 9.0
scores["HV02"] = 7.5

assert list(scores) == ["HV03", "HV01", "HV02"]
assert list(scores.items()) == [
    ("HV03", 8.0),
    ("HV01", 9.0),
    ("HV02", 7.5),
]
```

Điều này không có nghĩa dict **tự sắp xếp** các khóa. Nó chỉ nhớ thứ tự chèn.

### Cập nhật giá trị, xóa và chèn lại

```python
scores = {"HV03": 8.0, "HV01": 9.0, "HV02": 7.5}

scores["HV03"] = 10.0            # Chỉ thay giá trị
assert list(scores) == ["HV03", "HV01", "HV02"]

del scores["HV01"]               # Loại khóa
scores["HV01"] = 9.5              # Chèn khóa trở lại
assert list(scores) == ["HV03", "HV02", "HV01"]
```

**Quy tắc:** gán giá trị mới cho một khóa đang tồn tại không thay đổi vị trí chèn; **xóa rồi chèn lại** tạo một lượt chèn mới, nên khóa trở thành mục ở cuối thứ tự.

Một `dict` có thể giữ thứ tự chèn dù dùng cơ chế băm ở bên trong. Vì vậy, **“dựa trên bảng băm” không đồng nghĩa “không thể giữ thứ tự”**. Bảo đảm phải được tra theo hợp đồng cụ thể của kiểu dữ liệu.

### Sự khác biệt giữa khóa và giá trị khi duyệt

```python
scores = {"HV03": 8, "HV01": 9, "HV02": 8}

assert list(scores.keys()) == ["HV03", "HV01", "HV02"]
assert list(scores.values()) == [8, 9, 8]
```

Giá trị `8` có thể lặp ở nhiều khóa. Thứ tự các giá trị khi duyệt đi theo thứ tự **khóa tương ứng**, không có nghĩa các giá trị được sắp tăng dần.

### Lưu ý về `dict` trong Python cũ

Python 3.6 trên CPython đã có hành vi giữ thứ tự chèn như một chi tiết hiện thực, nhưng từ **Python 3.7** đây mới là bảo đảm của ngôn ngữ. Khi viết mã phải chạy trên môi trường có phiên bản cũ hơn, cần xác định rõ phiên bản và hợp đồng sử dụng.

## 5. Thứ tự sắp xếp phụ thuộc vào bộ so sánh

**Sắp xếp** cần một tiêu chí: theo mã tăng dần, theo điểm giảm dần, theo thời điểm hay theo một thuộc tính nghiệp vụ. Đây là điều kiện rõ ràng hơn “duyệt theo thứ tự”.

Trong Python, `sorted(iterable)` tạo một **list mới** gồm các phần tử được sắp theo khóa so sánh mặc định hoặc theo tham số `key`:

```python
codes = {"HV03", "HV01", "HV02"}

sorted_codes = sorted(codes)
assert sorted_codes == ["HV01", "HV02", "HV03"]

# Set gốc vẫn là set, không biến thành tập hợp có thứ tự:
assert codes == {"HV03", "HV01", "HV02"}
```

Không thể biến một Python `set` thành “set có thứ tự” chỉ bằng cách gọi `sorted(set)`: kết quả là **list đã sắp xếp**. Nếu tiếp tục chuyển list ấy về set, bảo đảm thứ tự duyệt lại không còn.

### Sắp xếp theo thứ tự số học thay vì chuỗi

```python
codes = {"SP2", "SP10", "SP1"}

# So sánh chuỗi theo thứ tự từ điển:
assert sorted(codes) == ["SP1", "SP10", "SP2"]

# So sánh giá trị số ở phần đuôi:
assert sorted(codes, key=lambda code: int(code[2:])) == [
    "SP1", "SP2", "SP10"
]
```

Hàm `key` ở ví dụ giả định mỗi mã đều có tiền tố `SP` và phần còn lại là chữ số. Dữ liệu không theo định dạng đó cần được kiểm tra trước. Việc chuyển đổi trong khóa so sánh cũng có chi phí riêng, dù nhiều trường hợp nhỏ có thể xem là hằng số theo độ dài mã.

### Sắp xếp theo trường của map

```python
scores = {"HV03": 8.0, "HV01": 9.0, "HV02": 7.5}

# Sắp khóa theo mã tăng dần:
assert sorted(scores) == ["HV01", "HV02", "HV03"]

# Sắp cặp theo điểm giảm dần, rồi theo mã tăng dần để xử lý hòa điểm:
ranking = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
assert ranking == [
    ("HV01", 9.0),
    ("HV03", 8.0),
    ("HV02", 7.5),
]
```

**Lưu ý:** sắp xếp theo `scores.items()` tạo danh sách cặp mới; thứ tự của `scores` không bị thay đổi. Nếu cần truy cập dữ liệu theo thứ tự điểm thường xuyên và thay đổi điểm liên tục, có thể cân nhắc cấu trúc chỉ mục sắp xếp bổ trợ thay vì sắp lại toàn bộ mỗi lần đọc.

## 6. Sắp xếp ổn định không sửa được thứ tự đầu vào tùy ý

Thuật toán sắp xếp **ổn định** giữ nguyên thứ tự tương đối của những phần tử có **khóa sắp xếp bằng nhau**. Python `sorted` và `list.sort` là ổn định.

```python
records = [
    ("HV03", 8),
    ("HV01", 9),
    ("HV02", 8),
]

# Hai học viên điểm 8 giữ thứ tự HV03 rồi HV02 như trong records:
by_score = sorted(records, key=lambda item: -item[1])
assert by_score == [
    ("HV01", 9),
    ("HV03", 8),
    ("HV02", 8),
]
```

Nhưng nếu `records` được tạo từ một cấu trúc **có thứ tự duyệt không được bảo đảm**, thứ tự gốc của các mục bằng điểm cũng không được bảo đảm. Khi cần kết quả hoàn toàn xác định, hãy bổ sung **quy tắc phá hòa**:

```python
records = {("HV03", 8), ("HV01", 9), ("HV02", 8)}

# Duyệt set có thể ở thứ tự nào cũng được;
# tiêu chí điểm rồi mã tạo kết quả hoàn toàn xác định.
ranking = sorted(records, key=lambda item: (-item[1], item[0]))
assert ranking == [
    ("HV01", 9),
    ("HV02", 8),
    ("HV03", 8),
]
```

Một tiêu chí phá hòa cần phản ánh yêu cầu nghiệp vụ. Với bài toán xếp hạng, có thể là thời điểm đạt điểm trước hoặc mã học viên; không nên mặc định rằng thứ tự hash set chính là quy tắc hòa điểm.

## 7. Cách giữ thứ tự chèn khi loại trùng

Nếu cần **giữ phần tử phân biệt theo lần xuất hiện đầu tiên**, hãy chọn cấu trúc có cam kết phù hợp hoặc phối hợp list với set.

### Cách 1: kết hợp `list` để lưu thứ tự và `set` để tra cứu

```python
def unique_first_seen(values):
    seen = set()
    result = []

    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

events = ["HV03", "HV01", "HV03", "HV02", "HV01"]

assert unique_first_seen(events) == ["HV03", "HV01", "HV02"]
```

Ở mỗi lần đọc một giá trị, `seen` trả lời “đã gặp chưa?”, trong khi `result` là **chuỗi có thứ tự**. Thuật toán bảo đảm thứ tự chèn vì nó chỉ thêm vào cuối list khi phần tử xuất hiện lần đầu.

Với `n` giá trị đầu vào và `d` giá trị phân biệt, nếu kiểm tra/thêm trên hash set trung bình `O(1)` thì thuật toán tốn thời gian trung bình `O(n)`, bộ nhớ phụ `O(d)`. Mã giả định các phần tử hashable. Nếu không thể băm phần tử, cần chọn chiến lược so sánh hoặc chuẩn hóa khác.

### Cách 2: dùng khóa của `dict` trong Python 3.7+

```python
events = ["HV03", "HV01", "HV03", "HV02", "HV01"]

unique_codes = list(dict.fromkeys(events))
assert unique_codes == ["HV03", "HV01", "HV02"]
```

`dict.fromkeys` xây map có các khóa duy nhất theo lần xuất hiện đầu tiên. Nhờ hợp đồng giữ thứ tự chèn của `dict`, khi chuyển các khóa thành list, thứ tự này vẫn được giữ. Cách này phù hợp khi chỉ cần loại trùng và phần tử là khóa hợp lệ của dict.

**Giới hạn:** kết quả `list(dict.fromkeys(...))` là list có thứ tự. Nếu lại chuyển sang `set` rồi duyệt để hiển thị, sẽ mất cam kết thứ tự.

## 8. Cách hiển thị kết quả nhất quán từ set và map

Những chương trình tự động chấm bài, tạo báo cáo và xuất dữ liệu thường cần kết quả **tái lập**. Nên tách **cấu trúc xử lý bên trong** khỏi **cách xuất kết quả**:

```python
students_in_a = {"HV03", "HV01", "HV02"}
students_in_b = {"HV02", "HV04"}

# Dùng set để tính các phần tử cần hiển thị.
both = students_in_a & students_in_b
all_students = students_in_a | students_in_b

# Chọn thứ tự hiển thị rõ ràng ngay tại biên xuất dữ liệu.
print(sorted(both))          # ['HV02']
print(sorted(all_students))  # ['HV01', 'HV02', 'HV03', 'HV04']
```

Nếu mục tiêu là tạo chuỗi để lưu vào file log, có thể làm như sau:

```python
permissions = {"read", "write", "admin"}

stable_text = ",".join(sorted(permissions))
assert stable_text == "admin,read,write"
```

Đầu ra `stable_text` ổn định vì chương trình quy định thứ tự trước khi nối chuỗi. **Không nên dùng trực tiếp `",".join(permissions)`** nếu thứ tự ký tự trong file là một phần của định dạng yêu cầu.

### Kết quả kiểm thử nên so sánh theo ngữ nghĩa

Khi **thứ tự không thuộc yêu cầu**, nên so sánh bằng set thay vì so sánh danh sách tạo từ set:

```python
actual = {3, 1, 2}

assert actual == {1, 2, 3}    # Kiểm tra đúng tập hợp
# Không nên khẳng định list(actual) có một thứ tự cụ thể.

# Khi thứ tự là yêu cầu, chủ động sắp xếp rồi so sánh:
assert sorted(actual) == [1, 2, 3]
```

Nếu đầu ra là JSON hoặc văn bản mà thứ tự các phần tử có ý nghĩa với người dùng hoặc hệ thống tiếp nhận, cần định nghĩa và kiểm thử thứ tự ấy như một phần hợp đồng xuất dữ liệu.

## 9. Tương tác với thuật toán đồ thị

Trong đồ thị, một danh sách kề có thể được hiện thực thành map từ đỉnh tới set các đỉnh kề:

```python
adjacency = {
    "A": {"C", "B"},
    "B": {"D"},
    "C": {"D"},
    "D": set(),
}
```

Nếu BFS duyệt trực tiếp `for neighbor in adjacency[vertex]`, thuật toán vẫn khám phá các đỉnh có thể đến được, nhưng **thứ tự những đỉnh cùng mức** có thể không được bảo đảm nếu tập láng giềng là set. Điều đó ảnh hưởng đến thứ tự xuất kết quả và có thể ảnh hưởng đường đi cụ thể được chọn khi có nhiều đường ngắn nhất.

Để BFS có kết quả duyệt theo thứ tự mã tăng dần:

```python
from collections import deque

def bfs_sorted_neighbors(graph, start):
    visited = {start}
    queue = deque([start])
    traversal = []

    while queue:
        current = queue.popleft()
        traversal.append(current)

        for neighbor in sorted(graph.get(current, set())):
            if neighbor not in visited:
                visited.add(neighbor)  # Đánh dấu ngay khi đưa vào queue.
                queue.append(neighbor)

    return traversal

adjacency = {
    "A": {"C", "B"},
    "B": {"D"},
    "C": {"D"},
    "D": set(),
}

assert bfs_sorted_neighbors(adjacency, "A") == ["A", "B", "C", "D"]
```

**Bất biến BFS** vẫn là mỗi đỉnh chỉ được đưa vào hàng đợi sau lần đầu được đánh dấu, nên tránh xử lý trùng. Việc `sorted` trên các tập kề chỉ quy định **trình tự thăm láng giềng**, không thay đổi tính đúng đắn của BFS trong việc xác định tập đỉnh có thể đến được.

Nếu đồ thị có `V` đỉnh và `E` cạnh, BFS cơ bản với danh sách kề và tra cứu thành viên trung bình hằng số thường có thời gian `O(V + E)`. Khi sắp xếp láng giềng trên mỗi đỉnh được xử lý, thời gian có thêm phần khoảng `O(Σ_v deg(v) log(deg(v) + 1))`; bộ nhớ phụ cho từng lần sắp xếp có thể lên đến `O(max_v deg(v))` ngoài hàng đợi và set đã thăm. Đây là chi phí hợp lý nếu yêu cầu kết quả có thứ tự xác định.

### Chọn dữ liệu kề theo mục đích

- Nếu cần **tránh cạnh trùng** và kiểm tra nhanh cạnh có tồn tại không, map của set phù hợp.
- Nếu cần **giữ thứ tự chèn cạnh** hoặc cho phép nhiều cạnh cùng đầu mút, map của list hoặc cấu trúc cạnh riêng có thể phù hợp.
- Nếu cần **duyệt láng giềng theo mã tăng dần thường xuyên**, hãy cân nhắc lưu thứ tự sẵn hoặc dùng một cấu trúc có hỗ trợ duyệt được sắp xếp, thay vì liên tục sắp lại.

## 10. Phân tích chi phí của việc chọn thứ tự

Gọi `n` là số phần tử phân biệt, `m` là tổng số phần tử đầu vào và `k` là số kết quả cần xuất.

| Tác vụ | Cách điển hình | Thời gian | Bộ nhớ phụ |
| --- | --- | --- | --- |
| Tra cứu thành viên trong hash set | `x in s` | Trung bình `O(1)` | `O(1)` |
| Loại trùng bằng set | `set(values)` | Trung bình `O(m)` | `O(n)` |
| Loại trùng giữ lần xuất hiện đầu tiên | List + hash set | Trung bình `O(m)` | `O(n)` |
| Duyệt một cấu trúc chứa `n` phần tử | Vòng lặp | Thông thường tỷ lệ với số phần tử duyệt; chi tiết tùy cấu trúc | `O(1)` cho vòng lặp cơ bản |
| Sắp xếp `n` phần tử có thể so sánh | `sorted(values)` | `O(n log n)` | `O(n)` cho list kết quả |
| Lấy `k` phần tử đầu từ list đã sắp | `ordered[:k]` | `O(k)` | `O(k)` cho list cắt mới |
| Duyệt tree set theo thứ tự | Duyệt các nút theo thứ tự | `O(n)` để xuất tất cả phần tử | Phụ thuộc hiện thực iterator |

Các đánh giá giả định hash/so sánh khóa có chi phí cơ bản hằng số, dữ liệu đầu vào là hữu hạn, và không tính chi phí định dạng/ghi ra thiết bị ngoài. Với hash set, thời gian một thao tác có thể lớn hơn mức trung bình vì va chạm băm hoặc tái băm.

Cần phân biệt **chi phí duy trì cấu trúc có thứ tự** với **chi phí sắp xếp một lần**:

- **Hash set** có thêm/tra cứu trung bình `O(1)`, nhưng không cung cấp thứ tự duyệt; khi cần toàn bộ phần tử tăng dần, sắp xếp kết quả thường tốn `O(n log n)`.
- **Tree set** cân bằng thường có tra cứu/chèn/xóa `O(log n)`, nhưng duyệt theo thứ tự khóa mất `O(n)` cho `n` phần tử, nên hợp lý khi cần thứ tự thường xuyên.
- **List đã sắp** cho phép duyệt tăng dần trực tiếp và tìm kiếm nhị phân `O(log n)`, nhưng thêm/xóa có thể mất `O(n)` do dịch phần tử.
- **Cấu trúc giữ thứ tự chèn** thích hợp khi cần trình tự xuất hiện; nó không tự thay thế một cấu trúc duy trì thứ tự tăng dần.

Không có một lựa chọn luôn tốt nhất. Phải dựa trên số lần thêm/xóa, số lần tra cứu, yêu cầu thứ tự và bộ nhớ được phép sử dụng.

## 11. Các tình huống biên và rủi ro về tính đúng đắn

### Đổi kiểu dữ liệu có thể làm mất thứ tự

```python
ordered = ["HV03", "HV01", "HV02"]
as_set = set(ordered)

# Kết quả này vẫn đúng về phần tử, nhưng không có thứ tự chèn:
assert as_set == {"HV03", "HV01", "HV02"}
```

Nếu cần giữ cả tính duy nhất lẫn thứ tự từ đầu, nên chọn list+set hoặc dict giữ thứ tự chèn.

### Không phải các giá trị nào cũng có thể sắp xếp chung

Trong Python 3, việc sắp xếp một set gồm các giá trị không có quy tắc so sánh tương thích có thể gây `TypeError`:

```python
mixed = {1, "2", 3}
# sorted(mixed)  # TypeError: không thể so sánh trực tiếp int và str

# Nếu nghiệp vụ chấp nhận thứ tự theo chuỗi:
ordered = sorted(mixed, key=lambda x: str(x))
assert ordered == [1, "2", 3]
```

Ví dụ này minh họa một lựa chọn so sánh tùy biến. Nếu nhiều giá trị chuyển thành cùng một chuỗi khi dùng `str`, cần thêm tiêu chí phá hòa để đầu ra hoàn toàn xác định.

### Không sửa kích thước set/dict khi đang duyệt

```python
values = {1, 2, 3, 4}

# Tránh xóa trực tiếp trong vòng lặp trên values.
filtered = {x for x in values if x % 2 == 0}
assert filtered == {2, 4}
```

Trong Python, thêm/xóa phần tử vào `set` hoặc thêm/xóa khóa `dict` ngay trong quá trình duyệt thường gây `RuntimeError`. Nếu cần sửa dữ liệu, duyệt trên một bản sao hoặc xây tập/map kết quả mới. Ngoài tính an toàn, việc sửa collection trong khi duyệt còn khiến cách hiểu “phần tử tiếp theo” trở nên khó xác định.

## 12. Ví dụ tổng hợp: ba kiểu xuất danh sách học viên

Một hệ thống điểm danh nhận các mã theo thời gian, trong đó có thể xuất hiện trùng. Hệ thống cần tạo ba kết quả: tập mã để tra cứu, danh sách mã theo lần đầu điểm danh và danh sách mã sắp tăng dần.

```python
checkins = ["HV03", "HV01", "HV03", "HV02", "HV01", "HV04"]

# 1. Tập để tra cứu thành viên và loại trùng:
unique_set = set(checkins)

# 2. Thứ tự xuất hiện đầu tiên:
first_seen = list(dict.fromkeys(checkins))

# 3. Thứ tự mã tăng dần:
sorted_codes = sorted(unique_set)

assert unique_set == {"HV01", "HV02", "HV03", "HV04"}
assert first_seen == ["HV03", "HV01", "HV02", "HV04"]
assert sorted_codes == ["HV01", "HV02", "HV03", "HV04"]

print("Lần đầu xuất hiện:", first_seen)
print("Theo mã tăng dần:", sorted_codes)
```

Cả ba biểu diễn chứa cùng **các mã phân biệt**, nhưng mỗi biểu diễn phục vụ một yêu cầu khác nhau. Nếu phải xuất báo cáo ổn định giữa các lần chạy, nên xuất `first_seen` hoặc `sorted_codes` theo hợp đồng của hệ thống, thay vì in trực tiếp tập `unique_set`.

Một phương án khác là dùng map `mã → thời điểm đăng ký đầu tiên` và sắp theo thời điểm nếu cần thứ tự thời gian, đồng thời lưu thêm số đếm trong multiset nếu phải biết số lần điểm danh. Việc lựa chọn cấu trúc bắt đầu từ **thông tin cần giữ lại**, rồi mới đến độ phức tạp.

## 13. Những hiểu lầm thường gặp

1. **“Hash set luôn duyệt theo thứ tự tăng dần.”** Sai: kết quả quan sát có thể trùng thứ tự tăng dần một cách tình cờ, nhưng không có hợp đồng.
2. **“Mọi hash map đều không giữ thứ tự.”** Không chính xác: Python `dict` từ 3.7 và Java `LinkedHashMap` là các ví dụ có cam kết thứ tự chèn.
3. **“Thứ tự chèn và thứ tự sắp xếp là một.”** Sai: `HV03` có thể được chèn trước `HV01`, nhưng khi sắp tăng dần `HV01` đứng trước.
4. **“`sorted(set)` trả về set có thứ tự.”** Sai: Python `sorted` trả về `list`.
5. **“`dict` tự sắp xếp khóa.”** Sai: `dict` giữ thứ tự chèn; muốn sắp khóa cần gọi `sorted(mapping)`.
6. **“Cập nhật giá trị trong dict làm khóa đi xuống cuối.”** Với Python `dict`, gán lại giá trị khóa cũ không đổi thứ tự; xóa rồi chèn lại mới đưa khóa xuống cuối.
7. **“Sắp xếp ổn định sẽ tạo kết quả giống nhau từ dữ liệu duyệt tùy ý.”** Chưa đủ: các phần tử có khóa sắp xếp bằng nhau vẫn giữ thứ tự đầu vào; cần tiêu chí phá hòa nếu thứ tự đầu vào không được bảo đảm.
8. **“Thứ tự duyệt set không ảnh hưởng thuật toán.”** Nó có thể ảnh hưởng thứ tự báo cáo, đường đi BFS được chọn khi có nhiều đường ngắn nhất và tính tái lập của kiểm thử.
9. **“Duyệt theo thứ tự có sẵn luôn miễn phí.”** Có trường hợp phải sắp xếp `O(n log n)` hoặc chấp nhận chi phí duy trì cây `O(log n)` mỗi lần cập nhật.
10. **“Có phần tử giống nhau là có cùng thứ tự.”** Hai set bằng nhau về nội dung không nhất thiết cung cấp cùng một trình tự duyệt có ý nghĩa theo hợp đồng.

## 14. Tự luyện tập

**Bài 1.** Cho dãy `["C", "A", "B", "A", "C"]`. Hãy viết tập các phần tử phân biệt, danh sách các phần tử theo lần xuất hiện đầu tiên và danh sách tăng dần.

**Bài 2.** Trong Python 3.7+, một dict được chèn lần lượt các khóa `"C"`, `"A"`, `"B"`. Sau đó gán lại giá trị của `"C"`. Viết kết quả của `list(d)` và giải thích.

**Bài 3.** Tiếp tục bài 2, xóa `"A"` rồi thêm lại `"A"`. Thứ tự khóa là gì?

**Bài 4.** Giải thích vì sao không được dùng `next(iter(my_set))` để lấy phần tử nhỏ nhất. Viết hai cách có chủ đích để tìm phần tử nhỏ nhất hoặc sắp xếp toàn bộ phần tử.

**Bài 5.** Giả sử các học viên có điểm `[("HV03", 8), ("HV01", 9), ("HV02", 8)]`. Hãy sắp theo điểm giảm dần, nếu bằng điểm thì theo mã tăng dần; nêu hàm `key` phù hợp.

**Bài 6.** Một ứng dụng duyệt đồ thị theo BFS, lưu láng giềng trong `set`. Vì sao hai lần chạy có thể cho thứ tự BFS khác nhau dù tập đỉnh đến được giống nhau? Cần làm gì để tạo kết quả tái lập?

**Bài 7.** Chọn giữa hash set, tree set, list+set và dict giữ thứ tự chèn cho ba nhu cầu: (a) kiểm tra tồn tại nhiều lần mà không cần thứ tự; (b) xuất tăng dần thường xuyên; (c) loại trùng nhưng giữ lượt xuất hiện đầu tiên.

**Bài 8.** Với `n` mã phân biệt, so sánh chi phí điển hình của việc lấy danh sách tăng dần từ hash set với việc duyệt một tree set đã duy trì thứ tự.

<details>
<summary>Gợi ý đáp án</summary>

1. Tập phân biệt `{"A", "B", "C"}`; thứ tự xuất hiện đầu tiên `["C", "A", "B"]`; thứ tự tăng dần `["A", "B", "C"]`.
2. `["C", "A", "B"]`. Cập nhật giá trị của khóa `"C"` không thay đổi vị trí của khóa đó trong `dict`.
3. `["C", "B", "A"]`. Xóa rồi thêm lại tạo một lượt chèn mới ở cuối.
4. `next(iter(s))` chỉ lấy một phần tử được duyệt đầu tiên, không có cam kết nhỏ nhất. Dùng `min(s)` để lấy phần tử nhỏ nhất khi có thể so sánh, hoặc `sorted(s)` để nhận toàn bộ theo thứ tự.
5. `sorted(records, key=lambda item: (-item[1], item[0]))`, kết quả `[("HV01", 9), ("HV02", 8), ("HV03", 8)]`.
6. Thứ tự duyệt `set` không được bảo đảm nên thứ tự đưa láng giềng vào queue có thể khác. Sắp xếp láng giềng bằng `sorted(graph[vertex])` trước khi duyệt nếu kiểu đỉnh có quy tắc so sánh phù hợp.
7. (a) hash set; (b) tree set hoặc cấu trúc sắp xếp phù hợp; (c) list+set hoặc Python `dict` giữ thứ tự chèn.
8. Hash set + `sorted` thường `O(n log n)` để có toàn bộ danh sách tăng dần; duyệt tree set đã được duy trì thứ tự là `O(n)`, nhưng thêm/xóa phần tử trong tree set thường là `O(log n)` mỗi thao tác.

</details>

## Ghi nhớ

**Thứ tự chèn** mô tả lịch sử thêm phần tử, **thứ tự sắp xếp** theo quy tắc so sánh, còn **thứ tự duyệt** do hợp đồng và hiện thực của collection quyết định. Set/Map ADT cơ bản chỉ bảo đảm tính duy nhất của phần tử/khóa, không mặc nhiên bảo đảm một thứ tự duyệt. Python `set` không có cam kết thứ tự; Python `dict` từ 3.7 giữ thứ tự chèn; các kiểu tree set/map hỗ trợ thứ tự sắp xếp. Khi cần kết quả tái lập, hãy lưu rõ thứ tự mong muốn hoặc **chủ động sắp xếp trước khi xuất**, đồng thời tính chi phí duy trì hay tạo thứ tự vào lựa chọn cấu trúc dữ liệu.
