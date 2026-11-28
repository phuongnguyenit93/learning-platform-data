# Ánh xạ khóa–giá trị và tính duy nhất của khóa

Một hệ thống quản lý khóa học cần biết học viên có mã `HV102` tên gì; ứng dụng thương mại điện tử cần tìm số lượng tồn kho từ mã sản phẩm; thuật toán trên đồ thị cần lưu khoảng cách ngắn nhất hiện biết đến từng đỉnh. Điểm chung là ta cần **lấy một giá trị thông qua khóa xác định giá trị đó**, thay vì dò lần lượt một danh sách.

**Ánh xạ (map)** là kiểu dữ liệu trừu tượng (Abstract Data Type – ADT) lưu các cặp **khóa → giá trị**. Mỗi khóa phân biệt chỉ gắn với **một giá trị tại một thời điểm**; các khóa khác nhau vẫn có thể gắn cùng một giá trị. Đây là trọng tâm của chương **Tập hợp và ánh xạ**, đồng thời là nền tảng để chọn cấu trúc dữ liệu theo thao tác, bất biến và độ phức tạp về thời gian, bộ nhớ.

## 1. Map là gì?

Ta có thể hình dung một map là cuốn từ điển: **từ cần tra** là khóa, **phần giải nghĩa** là giá trị. Ví dụ:

| Khóa (mã học viên) | Giá trị (họ tên) |
| --- | --- |
| `HV101` | `An` |
| `HV102` | `Bình` |
| `HV103` | `An` |

Trong ví dụ trên:

- Có **3 khóa phân biệt**, nên map chứa 3 cặp khóa–giá trị.
- `HV101` và `HV103` đều có giá trị `An`. Điều này **hợp lệ**: map không yêu cầu giá trị phải duy nhất.
- Không thể cùng lúc tồn tại hai mục độc lập có cùng khóa `HV102` nhưng lần lượt gắn với `Bình` và `Chi`. Một thao tác cập nhật khóa `HV102` sẽ làm giá trị gắn với khóa đó chuyển thành `Chi`, nếu map sử dụng ngữ nghĩa ghi đè.

Về mặt toán học, map hữu hạn có thể xem là một **hàm bộ phận** từ tập khóa `K` đến tập giá trị `V`:

\[
M: K \rightharpoonup V.
\]

“Bộ phận” nghĩa là **không phải mọi khóa tiềm năng trong `K` đều nhất thiết có trong map**. Tập các khóa đang tồn tại là miền xác định `dom(M)`. Với mỗi `k ∈ dom(M)`, có đúng một giá trị `M[k]`. Nếu một khóa chưa tồn tại, truy vấn cần trả về dấu hiệu “không tìm thấy” hoặc báo lỗi tùy giao diện.

Trong các ngôn ngữ lập trình, map còn có tên khác như **dictionary**, **associative array**, **symbol table** hoặc **key–value store** (tùy ngữ cảnh). Khái niệm ADT mô tả **hành vi**, còn `HashMap`, `TreeMap`, `dict`… là những kiểu triển khai cụ thể với ràng buộc khác nhau.

### Bất biến: khóa là duy nhất

Với mọi khóa `k`, map có **nhiều nhất một** cặp `(k, v)`. Kéo theo:

1. **Thêm khóa mới** làm số cặp tăng một.
2. **Ghi lại khóa đã có** theo ngữ nghĩa `put`/gán sẽ thay giá trị cũ, không tăng số cặp.
3. **Xóa khóa đang có** loại cả cặp khóa–giá trị tương ứng.
4. **Giá trị có thể trùng**; tính duy nhất chỉ áp dụng lên khóa.

Ví dụ trạng thái của một map có thể biến đổi như sau:

| Thao tác | Trạng thái map | Số cặp |
| --- | --- | --- |
| Ban đầu | `{}` | `0` |
| `put("A", 10)` | `{"A": 10}` | `1` |
| `put("B", 10)` | `{"A": 10, "B": 10}` | `2` |
| `put("A", 25)` | `{"A": 25, "B": 10}` | `2` |
| `remove("B")` | `{"A": 25}` | `1` |

## 2. Thế nào là hai khóa “giống nhau”?

Tính duy nhất cần một **quy tắc xác định bằng nhau**. Nếu hai khóa `k1` và `k2` được cấu trúc dữ liệu coi là bằng nhau, chúng đại diện cho **cùng một vị trí logic** trong map, kể cả khi được tạo thành hai đối tượng khác nhau.

- Với map dùng **hàm băm**, hai khóa bằng nhau phải có hàm băm tương thích: nếu `k1 == k2` thì `hash(k1) == hash(k2)`. Cùng giá trị băm **chưa đủ** để kết luận hai khóa bằng nhau, bởi có thể xảy ra va chạm.
- Với map dùng **cây có thứ tự**, việc coi hai khóa là cùng khóa thường dựa vào **bộ so sánh**: khi so sánh cho kết quả bằng nhau, cây xem đó là một khóa. Cần bảo đảm quy tắc so sánh nhất quán.
- Một số khóa trông giống nhau với người dùng vẫn khác nhau theo quy tắc của chương trình. Ví dụ Python mặc định phân biệt `"hv01"` và `"HV01"`.

Nếu nghiệp vụ muốn hai chuỗi đó cùng chỉ một học viên, hãy **chuẩn hóa khóa trước khi đưa vào map**:

```python
def normalize_student_id(student_id: str) -> str:
    return student_id.strip().upper()

scores = {}
scores[normalize_student_id(" hv01 ")] = 8.0
scores[normalize_student_id("HV01")] = 9.0

print(scores)  # {'HV01': 9.0}
print(len(scores))  # 1
```

Việc chọn chuẩn hóa nào là quyết định của **nghiệp vụ**. Không nên tự biến các khóa thành chữ thường/chữ hoa khi phân biệt chữ hoa là một phần của định danh hợp lệ.

## 3. Các thao tác của Map ADT

Giao diện bên dưới minh họa các thao tác thường gặp. Tên hàm, giá trị trả về và cách xử lý khóa vắng mặt tùy thư viện cụ thể.

| Thao tác | Ý nghĩa | Ghi chú về bất biến |
| --- | --- | --- |
| `containsKey(k)` | Kiểm tra khóa có trong map không | Khác với kiểm tra giá trị có xuất hiện |
| `get(k)` | Lấy giá trị gắn với khóa `k` | Khóa vắng mặt có thể trả dấu hiệu riêng hoặc lỗi |
| `put(k, v)` | Gắn `k` với `v`; ghi đè nếu đã có | Không tạo khóa thứ hai bằng `k` |
| `putIfAbsent(k, v)` | Chỉ gắn `k` nếu khóa chưa tồn tại | Bảo toàn giá trị đang có |
| `remove(k)` | Xóa cặp theo khóa `k` | Giảm kích thước nếu tìm thấy |
| `size()` | Số khóa phân biệt đang có | Không phải số giá trị phân biệt |
| `keys()` | Duyệt các khóa | Mỗi khóa đúng một lần |
| `values()` | Duyệt các giá trị | Các giá trị có thể lặp |
| `entries()` / `items()` | Duyệt các cặp khóa–giá trị | Giữ đúng liên hệ giữa từng khóa và giá trị |
| `clear()` | Xóa tất cả cặp | Kích thước về 0 |

Ở mức ADT, ta có thể đặc tả `put`:

```text
PUT(M, k, v):
    nếu M đã chứa khóa tương đương k:
        thay giá trị cũ gắn với k thành v
        trả về UPDATED
    ngược lại:
        thêm cặp (k, v) mới vào M
        trả về INSERTED
```

Đây là **một cách định nghĩa phổ biến**, không phải hành vi của mọi API. Có giao diện `insert` từ chối khóa đã có; có giao diện `put` trả về giá trị cũ, `None` hoặc một cờ trạng thái. Khi dùng thư viện thật, cần kiểm tra hợp đồng của hàm thay vì giả định mọi thao tác “thêm” đều ghi đè.

### Phân biệt khóa không tồn tại và giá trị rỗng

Đây là một lỗi thiết kế thường gặp: **map có thể chứa khóa với giá trị `None` hoặc `null`**, vì vậy không thể luôn suy ra “không có khóa” chỉ từ “giá trị được trả về là `None`”.

```python
data = {"user-1": None}

print(data.get("user-1"))      # None: khóa có tồn tại
print(data.get("user-2"))      # None: khóa không tồn tại
print("user-1" in data)        # True
print("user-2" in data)        # False

# Khi cần phân biệt trong một lượt truy vấn:
missing = object()
value = data.get("user-2", missing)
if value is missing:
    print("Không tìm thấy khóa")
```

Nếu chỉ hỏi khóa tồn tại hay không, dùng `containsKey` hoặc cú pháp `k in map`. Nếu cần giá trị, cần quyết định rõ cách xử lý trường hợp thiếu khóa.

## 4. Thực hành bằng Python: `dict`

Python cung cấp `dict` để lưu ánh xạ khóa–giá trị. Truy cập bằng `d[k]` khác với truy cập vị trí `a[i]` của danh sách: chỉ số ở đây là **khóa**, có thể là chuỗi, số hoặc đối tượng hashable phù hợp.

```python
student_scores = {
    "HV101": 8.5,
    "HV102": 7.0,
}

# Tra cứu theo khóa
print(student_scores["HV101"])            # 8.5
print(student_scores.get("HV999"))         # None nếu không có
print(student_scores.get("HV999", 0.0))    # 0.0 là giá trị mặc định
print("HV102" in student_scores)           # True

# Thêm khóa mới, rồi cập nhật khóa đã có
student_scores["HV103"] = 8.5
student_scores["HV102"] = 9.0
print(len(student_scores))                 # 3, không tăng vì cập nhật HV102

# Xóa
removed_score = student_scores.pop("HV101")
print(removed_score)                       # 8.5
student_scores.pop("HV999", None)           # Khóa thiếu: không gây KeyError

# Duyệt cặp khóa–giá trị
for student_id, score in student_scores.items():
    print(student_id, score)
```

Khi truy cập trực tiếp `student_scores["HV999"]`, Python báo `KeyError`. `dict.get` cho phép cung cấp giá trị mặc định và không làm xuất hiện khóa mới. Nếu muốn chỉ khởi tạo khi khóa thiếu, dùng `setdefault`:

```python
settings = {"theme": "dark"}
settings.setdefault("theme", "light")
settings.setdefault("language", "vi")
print(settings)  # {'theme': 'dark', 'language': 'vi'}
```

**Chú ý về thứ tự:** Trong Python từ phiên bản 3.7, thứ tự duyệt `dict` theo **thứ tự chèn khóa** là bảo đảm của ngôn ngữ. Gán lại giá trị của khóa sẵn có không thay đổi vị trí chèn của nó. Tuy nhiên, **Map ADT nói chung không bảo đảm thứ tự**; các ngôn ngữ và kiểu `HashMap` khác có thể duyệt theo thứ tự khác. Thứ tự chèn cũng không đồng nghĩa với sắp xếp khóa.

### Khi tạo map từ các cặp khóa trùng

```python
rows = [
    ("HV101", 7.0),
    ("HV102", 8.0),
    ("HV101", 9.0),
]

result = dict(rows)
print(result)              # {'HV101': 9.0, 'HV102': 8.0}
print(len(result))         # 2
```

Khi có khóa lặp, `dict(rows)` giữ **giá trị từ lần gán cuối** cho khóa đó. Thông tin `HV101` từng có `7.0` đã bị thay thế; nếu cần giữ lịch sử hoặc nhiều bản ghi trên một khóa, phải dùng cấu trúc khác, chẳng hạn `dict[str, list[float]]`.

## 5. Vì sao khóa phải phù hợp với cơ chế tra cứu?

Với `dict` trong Python, khóa phải **hashable**: có giá trị băm ổn định trong suốt thời gian tồn tại ở trong map và có quy tắc so sánh tương thích với giá trị băm. Các kiểu bất biến như chuỗi, số và tuple chỉ chứa phần tử hashable thường có thể dùng làm khóa; list và dict thông thường không được phép vì thay đổi được.

```python
routes = {
    ("Hà Nội", "Đà Nẵng"): 760,
    ("Đà Nẵng", "Huế"): 100,
}

print(routes[("Đà Nẵng", "Huế")])  # 100

# Không hợp lệ vì list không hashable:
# routes[["Hà Nội", "Đà Nẵng"]] = 760   # TypeError
```

Tính bất biến của đối tượng chỉ là một gợi ý thực hành: điều kiện quyết định là hợp đồng `hash` và phép so sánh. Đối tượng tự định nghĩa vẫn có thể dùng làm khóa nếu triển khai đúng các quy tắc đó.

Một ví dụ đặc biệt của Python là `True == 1`, nên chúng được coi là khóa tương đương:

```python
example = {1: "một"}
example[True] = "đúng"
print(len(example))    # 1
print(example[1])      # 'đúng'
```

Nếu nghiệp vụ cần phân biệt các loại định danh khác nhau có giá trị biểu diễn giống nhau, hãy thiết kế **kiểu khóa có ngữ nghĩa rõ ràng** (ví dụ thêm tiền tố loại định danh), thay vì mặc định rằng khác kiểu thì luôn khác khóa.

## 6. Các cách hiện thực Map ADT

Map ADT không bắt buộc dùng bảng băm. Gọi `n` là số khóa phân biệt trong map và `U` là số khóa có thể có trong một miền định danh hữu hạn.

| Hiện thực | Tìm theo khóa | Chèn/cập nhật | Xóa | Bộ nhớ điển hình | Điểm mạnh |
| --- | --- | --- | --- | --- | --- |
| **Hash map** (bảng băm) | Trung bình `O(1)` | Trung bình `O(1)` | Trung bình `O(1)` | `O(n)` | Truy cập nhanh theo khóa, không cần thứ tự |
| **Tree map** (cây tìm kiếm cân bằng) | `O(log n)` | `O(log n)` | `O(log n)` | `O(n)` | Duyệt khóa đã sắp, truy vấn khoảng |
| **Mảng cặp khóa–giá trị chưa sắp** | `O(n)` | `O(n)` nếu cần kiểm tra trùng khóa | `O(n)` | `O(n)` | Dễ cài đặt khi dữ liệu rất nhỏ |
| **Mảng cặp khóa–giá trị đã sắp** | `O(log n)` bằng tìm nhị phân | `O(n)` do cần dịch phần tử | `O(n)` | `O(n)` | Đọc nhiều, sửa ít, dữ liệu gọn |
| **Địa chỉ trực tiếp** (direct addressing) | `O(1)` | `O(1)` | `O(1)` | `O(U)` | Miền khóa nguyên nhỏ và biết trước |

Các đánh giá giả định so sánh, tính băm và truy cập cơ bản có chi phí hằng số. Bộ nhớ `O(n)` cho hash map/tree map tính số mục và cấu trúc phụ trợ, chưa tính dung lượng dữ liệu lớn nằm trong đối tượng giá trị; với địa chỉ trực tiếp cần cấp chỗ cho cả miền `U` dù nhiều khóa chưa xuất hiện.

### Hash map hoạt động thế nào?

Hash map thường sử dụng hàm băm `h(k)` để xác định vùng lưu trữ cần kiểm tra. Hai khóa khác nhau vẫn có thể rơi vào cùng một vùng (**va chạm băm**), vì vậy hiện thực cần cơ chế giải quyết va chạm và **so sánh bằng nhau** để phân biệt khóa:

```text
PUT_HASH_MAP(table, key, value):
    region = locate(hash(key), table)
    tìm trong region một khóa tương đương key

    nếu tìm thấy:
        cập nhật giá trị của đúng khóa đó
    ngược lại:
        lưu cặp (key, value) vào table
        tăng số khóa phân biệt

    nếu table quá đầy:
        mở rộng và phân bố lại các mục nếu cần
```

Nếu hàm băm phân bố hợp lý và hệ số tải được kiểm soát, tìm/chèn/xóa có thời gian **trung bình hoặc kỳ vọng `O(1)`**. Một thao tác có thể tốn `O(n)` khi nhiều khóa va chạm hoặc khi phải tái băm để mở rộng bảng. Chi phí `O(1)` thường được hiểu theo trung bình và, với chuỗi lần chèn mở rộng bảng, theo phân tích khấu hao; không phải giới hạn tệ nhất cho mọi đầu vào.

### Tree map khác gì?

Tree map thường tổ chức khóa trong cây tìm kiếm cân bằng (như cây đỏ–đen hoặc AVL), cho phép tìm, thêm, xóa theo khóa trong `O(log n)`. Tính năng nổi bật là **khóa có thứ tự**: có thể duyệt tăng dần, tìm khóa nhỏ nhất/lớn nhất, tìm khóa gần nhất hoặc trích một khoảng khóa. Cái giá là thêm chi phí so sánh, cân bằng cây và con trỏ liên kết.

Lựa chọn giữa hash map và tree map nên dựa vào **truy vấn cần thực hiện**: chỉ tra cứu chính xác mã thì thường ưu tiên hash map; cần truy vấn `mã trong đoạn [a, b]` hoặc duyệt theo thứ tự khóa thì tree map phù hợp hơn.

## 7. Quan hệ giữa map và set

Map và set đều bảo đảm **không có khóa/phần tử trùng nhau**, nhưng thông tin cần lưu khác nhau:

| Câu hỏi | Cấu trúc phù hợp | Ví dụ |
| --- | --- | --- |
| “Mã học viên này đã xuất hiện chưa?” | Set | `{"HV101", "HV102"}` |
| “Điểm hiện tại của mã học viên này là bao nhiêu?” | Map | `{"HV101": 8.5, "HV102": 7.0}` |
| “Mã học viên này xuất hiện bao nhiêu lần?” | Map từ mã tới bộ đếm | `{"HV101": 3, "HV102": 1}` |
| “Học viên này đã có những điểm nào trong lịch sử?” | Map từ mã tới danh sách | `{"HV101": [7.0, 8.5]}` |

Có thể xem set như một trường hợp đặc biệt của map chỉ cần **khóa**, với một giá trị đánh dấu chung không mang ý nghĩa nghiệp vụ. Ngược lại, việc bỏ các giá trị của map sẽ cho tập các khóa phân biệt. Tuy nhiên, cách hai cấu trúc được cài đặt và hiệu năng thực tế còn tùy thư viện.

Với Python:

```python
grades = {"HV101": 8.5, "HV102": 7.0}
unique_ids = set(grades)                 # Tập khóa, không lấy giá trị
print(unique_ids == {"HV101", "HV102"})  # True
```

## 8. Ứng dụng 1: đếm tần suất xuất hiện

Danh sách sự kiện có thể xuất hiện nhiều lần cho cùng một mã. Nếu dùng set, ta chỉ biết mã nào đã xuất hiện; dùng map từ **mã → số lần xuất hiện** sẽ giữ được cả tính duy nhất của khóa lẫn số lần:

```python
student_events = ["HV101", "HV102", "HV101", "HV103", "HV102", "HV101"]

counts = {}
for student_id in student_events:
    counts[student_id] = counts.get(student_id, 0) + 1

print(counts)                # {'HV101': 3, 'HV102': 2, 'HV103': 1}
print(len(counts))           # 3 mã phân biệt
print(sum(counts.values()))  # 6 sự kiện
```

Nếu có `m` sự kiện và `d` mã khác nhau, với hash map có thao tác trung bình `O(1)`, tổng thời gian trung bình là `O(m)`, bộ nhớ phụ là `O(d)`. Nếu dùng list và lặp qua tất cả cặp trước đó để tìm khóa mỗi lần, chi phí có thể lớn hơn nhiều, lên tới `O(m²)` trong trường hợp nhiều khóa khác nhau.

## 9. Ứng dụng 2: nhóm nhiều giá trị theo một khóa

Tính duy nhất của khóa **không có nghĩa một khóa chỉ được liên quan đến một bản ghi trong nghiệp vụ**. Giá trị của map có thể là **một tập hợp hoặc danh sách**, nhờ đó mỗi khóa vẫn chỉ có một mục nhưng chứa nhiều dữ liệu liên quan:

```python
registrations = [
    ("HV101", "Python"),
    ("HV102", "Cấu trúc dữ liệu"),
    ("HV101", "Thuật toán"),
    ("HV101", "Python"),
]

# Mỗi mã học viên ánh xạ tới tập môn học đã đăng ký
courses_by_student = {}
for student_id, course in registrations:
    if student_id not in courses_by_student:
        courses_by_student[student_id] = set()
    courses_by_student[student_id].add(course)

print(sorted(courses_by_student["HV101"]))
# ['Python', 'Thuật toán']
```

Giá trị là `set` nên không lặp lại tên môn học; nếu cần giữ lịch sử đăng ký, kể cả sự kiện trùng, hãy dùng `list` làm giá trị. Cách phối hợp map với set/list thường xuất hiện trong **danh sách kề của đồ thị**, chỉ mục tra cứu và các bài toán gom nhóm.

## 10. Các lỗi tư duy và lỗi lập trình thường gặp

1. **Cho rằng khóa và giá trị đều phải duy nhất.** Chỉ khóa phải duy nhất; hai học viên có thể trùng tên hoặc điểm.
2. **Cho rằng ghi trùng khóa sẽ tạo thêm một mục.** Với phép gán/`put` ghi đè, kích thước không tăng; dữ liệu cũ có thể mất. Nếu phải lưu nhiều giá trị, hãy dùng list/set làm giá trị hoặc mô hình dữ liệu khác.
3. **Nhầm `get(k)` trả `None` với khóa thiếu.** Hãy dùng `k in mapping` hoặc một sentinel riêng nếu `None` là giá trị hợp lệ.
4. **Giả định khóa cùng hash là cùng khóa.** Hàm băm có va chạm; tra cứu đúng cần kiểm tra bằng nhau.
5. **Dùng đối tượng khóa thay đổi trạng thái liên quan đến băm/so sánh.** Điều này có thể phá hỏng khả năng tìm lại mục đã chèn; ở Python, nhiều kiểu mutable đã bị cấm làm khóa.
6. **Đồng nhất map với thứ tự sắp xếp.** Map ADT không yêu cầu có thứ tự. Python `dict` giữ thứ tự chèn, còn nhu cầu duyệt theo thứ tự khóa có thể dùng `sorted(mapping)` hoặc tree map phù hợp.
7. **Sửa kích thước map trong khi đang duyệt.** Với `dict` Python, xóa/thêm khóa giữa vòng lặp có thể gây `RuntimeError`. Hãy xác định danh sách khóa cần xóa trước:

```python
scores = {"HV101": 8, "HV102": 0, "HV103": 9}
for student_id in list(scores):
    if scores[student_id] == 0:
        del scores[student_id]
print(scores)  # {'HV101': 8, 'HV103': 9}
```

8. **Dùng map khi dữ liệu cần lịch sử đầy đủ của các lần cập nhật.** Giá trị hiện tại không tự lưu lại giá trị cũ. Muốn audit hoặc truy vết lịch sử, cần ghi log sự kiện hoặc lưu các phiên bản riêng.

## 11. Cách chọn cấu trúc phù hợp

Trước khi chọn `dict`, `HashMap`, `TreeMap` hay một cấu trúc khác, hãy trả lời:

- **Khóa là gì?** Mã học viên, mã sản phẩm, tọa độ, hay tổ hợp nhiều trường? Khóa cần có quy tắc bằng nhau ổn định và đúng nghiệp vụ.
- **Một khóa có thể ứng với nhiều giá trị nghiệp vụ không?** Nếu có, giá trị của map cần là một collection hoặc một bản ghi tổng hợp.
- **Thao tác nào quan trọng nhất?** Tra cứu chính xác, thêm/xóa thường xuyên, đếm tần suất, hay truy vấn theo khoảng khóa?
- **Có cần thứ tự hay không?** Đừng suy diễn thứ tự từ khái niệm map; chọn cấu trúc bảo đảm đúng loại thứ tự mong muốn.
- **Miền khóa rộng đến đâu?** Miền số nguyên nhỏ có thể phù hợp địa chỉ trực tiếp; miền lớn và thưa thường hợp với hash map hoặc tree map.

Map giúp mã hóa rõ quy tắc **“một khóa xác định một giá trị hiện tại”**. Thiết kế đúng khóa và ngữ nghĩa cập nhật thường quan trọng không kém việc tối ưu thời gian tra cứu.

## 12. Tự kiểm tra

**Bài 1.** Một map ban đầu rỗng nhận lần lượt `put("A", 4)`, `put("B", 4)`, `put("A", 9)`. Hãy xác định số cặp và giá trị gắn với `"A"` và `"B"`, giả sử `put` ghi đè.

**Bài 2.** Tại sao `{"HV101": "An", "HV102": "An"}` vẫn là map hợp lệ? Tính duy nhất được áp dụng lên thành phần nào?

**Bài 3.** Để thống kê lượt truy cập mỗi trang web theo đường dẫn URL, bạn sẽ chọn set hay map? Hãy mô tả cấu trúc khóa và giá trị.

**Bài 4.** Phân biệt `containsKey(k)` và `get(k)` trong trường hợp giá trị hợp lệ có thể là `None`.

**Bài 5.** Bài toán cần liệt kê các mã sản phẩm theo thứ tự tăng dần và truy vấn một khoảng mã thường xuyên. Nên cân nhắc hash map hay tree map? Vì sao?

**Bài 6.** Với dữ liệu `[("X", 1), ("X", 2), ("Y", 3)]`, muốn giữ cả `1` và `2` dưới khóa `X` thì nên cấu trúc lại giá trị của map như thế nào?

<details>
<summary>Đáp án tham khảo</summary>

1. Hai cặp: `{"A": 9, "B": 4}`. Lần ghi `A` thứ hai thay giá trị cũ.
2. Vì khóa `HV101` và `HV102` khác nhau, còn giá trị `An` được phép lặp. Tính duy nhất áp dụng cho khóa.
3. Dùng map `URL → số lượt truy cập`, tăng bộ đếm mỗi khi có sự kiện.
4. `containsKey` phân biệt khóa tồn tại hay không; `get` có thể trả `None` cho cả khóa tồn tại mang `None` và khóa vắng mặt nếu không có dấu hiệu phân biệt.
5. Tree map vì cấu trúc này lưu khóa theo thứ tự và hỗ trợ tìm theo khoảng hiệu quả; hash map chủ yếu phù hợp tra cứu chính xác khóa.
6. Dùng `{"X": [1, 2], "Y": [3]}`; giá trị của mỗi khóa là một danh sách các giá trị liên quan.

</details>

## Ghi nhớ

**Map là ánh xạ từ khóa sang giá trị, với mỗi khóa phân biệt ứng với tối đa một giá trị hiện tại.** Khóa duy nhất, giá trị có thể trùng hoặc là một tập hợp dữ liệu. Ghi đè khóa cũ không làm tăng kích thước map, và tìm kiếm đúng phụ thuộc vào quy tắc bằng nhau của khóa. Hash map thường cho tra cứu trung bình `O(1)`; tree map thường cho các thao tác `O(log n)` và hỗ trợ duyệt theo thứ tự khóa. Hãy chọn hiện thực dựa trên bất biến, truy vấn chính và yêu cầu về thời gian, bộ nhớ.
