# Ảnh hưởng của quy tắc bằng nhau và bộ so sánh đến khóa trùng

Hai tài khoản có mã `"HV01"` và `"hv01"` là một hay hai tài khoản? Hai sản phẩm cùng tên nhưng khác mã SKU có phải cùng một sản phẩm? Nếu chỉ sắp xếp học viên theo điểm số, hai người cùng điểm có bị coi là một khóa trong cây tìm kiếm hay không?

Câu trả lời phụ thuộc vào **quy tắc xác định hai khóa tương đương**. Trong chương **Tập hợp và ánh xạ**, set phải giữ các phần tử phân biệt và map phải giữ các khóa phân biệt. Nhưng “phân biệt” không tự nhiên chỉ có một nghĩa: cấu trúc dựa trên băm thường dùng **phép bằng nhau kết hợp hàm băm**, còn cấu trúc có thứ tự thường xác định sự tương đương thông qua **bộ so sánh**.

Bài học giải thích cách lựa chọn và duy trì quy tắc ấy, nhận biết các lỗi mất khóa hoặc tìm kiếm sai, đồng thời liên hệ đến độ phức tạp thời gian và bộ nhớ khi chọn cấu trúc dữ liệu cho từng bài toán.

## 1. “Khóa trùng” là một quy tắc, không chỉ là hình thức hiển thị

Giả sử một hệ thống nhận ba mã:

```text
"HV01"
"hv01"
" HV01 "
```

Theo phép so sánh chuỗi mặc định của Python, chúng là **ba chuỗi khác nhau**. Nếu nghiệp vụ quy định mã học viên **không phân biệt hoa thường và bỏ khoảng trắng ngoài**, cả ba có thể cùng đại diện một học viên.

Vì vậy, ta phải phân biệt:

- **Cùng đối tượng** (*identity*): hai biến trỏ đến đúng một đối tượng trong bộ nhớ.
- **Bằng nhau về giá trị** (*equality*): hai đối tượng thỏa quy tắc bằng nhau đã định nghĩa.
- **Tương đương theo bộ so sánh** (*comparator equivalence*): bộ so sánh có thứ tự coi hai khóa là không nhỏ hơn nhau theo cả hai chiều.

Ba quan hệ này có thể cho những kết quả khác nhau. Set/map sẽ quyết định khóa trùng dựa trên **hợp đồng cụ thể của hiện thực**, chứ không dựa vào cách người dùng nhìn tên khóa.

### Bất biến của set và map

Với set, hai phần tử được xem là tương đương sẽ đại diện **một phần tử logic**. Với map, hai khóa tương đương sẽ đại diện **một vị trí logic để gắn giá trị**.

```text
Map với hai khóa không tương đương:
  "HV01" -> 8.0
  "hv01" -> 9.0
  số khóa: 2

Map với quy tắc không phân biệt hoa thường:
  "HV01" -> 9.0
  số khóa: 1 (nếu lần ghi sau cập nhật lần ghi trước)
```

Đây là ví dụ minh họa **ngữ nghĩa ghi đè**; một API “chỉ chèn nếu chưa có” có thể từ chối lần ghi thứ hai. Quy tắc trùng khóa và quy tắc xử lý khi trùng là **hai quyết định khác nhau**.

## 2. Quy tắc bằng nhau: những tính chất nên bảo đảm

Trong thiết kế cấu trúc dữ liệu, ta thường muốn “bằng nhau” hoạt động như **quan hệ tương đương**:

1. **Phản xạ:** một khóa bằng chính nó.
2. **Đối xứng:** nếu `a` bằng `b` thì `b` bằng `a`.
3. **Bắc cầu:** nếu `a` bằng `b` và `b` bằng `c` thì `a` bằng `c`.

Các tính chất này giúp tra cứu, chèn và xóa duy trì một tập các nhóm khóa rõ ràng. Nếu bộ so sánh tùy biến đưa ra kết quả thiếu nhất quán, cấu trúc dữ liệu có thể xử lý sai hoặc tạo hành vi khó dự đoán.

**Lưu ý:** Một số giá trị đặc biệt, như `NaN` trong tính toán số thực, không tuân thủ hoàn toàn phép bằng nhau thông thường; một số thư viện có chính sách riêng cho chúng. Khi thiết kế khóa nghiệp vụ, nên chọn kiểu khóa và hợp đồng có tính nhất quán, ổn định, thay vì dựa vào các trường hợp biên ấy.

### Bằng nhau không phải cùng địa chỉ đối tượng

```python
a = ["array", "stack"]
b = ["array", "stack"]

assert a == b       # Nội dung hai list bằng nhau
assert a is not b   # Hai đối tượng list khác nhau
```

Ví dụ trên chỉ để phân biệt `==` với `is`. List Python **không hashable**, nên không được sử dụng trực tiếp làm khóa `dict` hoặc phần tử `set`. Nếu dùng một tuple gồm các thành phần hashable:

```python
key_a = ("array", "stack")
key_b = ("array", "stack")

assert key_a == key_b
assert len({key_a, key_b}) == 1
```

Hai tuple được so sánh theo nội dung, nên chỉ tạo một phần tử logic trong set.

## 3. Cấu trúc dựa trên băm: bằng nhau kết hợp với hash

Một **hash set** hoặc **hash map** thường tính `hash(key)` để tìm vị trí ứng viên, sau đó kiểm tra khóa thực sự có bằng nhau hay không.

Quy tắc nền tảng:

> Nếu `a == b` thì `hash(a) == hash(b)` phải đúng đối với các khóa được dùng trong cùng cấu trúc băm.

Chiều ngược lại **không đúng**: hai khóa khác nhau có thể có cùng giá trị băm. Hiện tượng đó gọi là **va chạm băm** (*hash collision*).

### Va chạm băm không có nghĩa trùng khóa

```python
class CollisionKey:
    def __init__(self, code):
        self.code = code

    def __hash__(self):
        return 7  # Mọi khóa đều có cùng hash để minh họa va chạm

    def __eq__(self, other):
        if not isinstance(other, CollisionKey):
            return NotImplemented
        return self.code == other.code


first = CollisionKey("HV01")
same = CollisionKey("HV01")
different = CollisionKey("HV02")

assert first == same
assert hash(first) == hash(same) == hash(different)

group = {first, same, different}
assert len(group) == 2           # HV01 và HV02
```

Dù tất cả đều có cùng hash, set vẫn giữ hai khóa phân biệt nhờ kiểm tra `__eq__`. Ví dụ cố tình tạo nhiều va chạm để giải thích cơ chế; đây **không phải hàm băm nên dùng trong ứng dụng thật**.

Một bảng băm hoạt động đúng phải xử lý được va chạm. Nếu chỉ so sánh hash và bỏ qua phép bằng nhau, những khóa khác nhau sẽ bị loại nhầm.

### Điều gì xảy ra khi chèn khóa trùng?

```python
grades = {}
grades["HV01"] = 7.0
grades["HV01"] = 9.0

assert len(grades) == 1
assert grades["HV01"] == 9.0

unique_ids = {"HV01", "HV01", "HV02"}
assert unique_ids == {"HV01", "HV02"}
```

Với Python `dict`, phép gán cho khóa đang có sẽ **cập nhật giá trị**. Với Python `set`, việc thêm lại phần tử tương đương không làm tăng kích thước.

## 4. Khóa có thể trùng dù kiểu dữ liệu hoặc biểu diễn khác nhau

Đừng đồng nhất “khác kiểu” với “khác khóa”. Trong Python:

```python
assert True == 1
assert 1 == 1.0
assert hash(True) == hash(1) == hash(1.0)

mapping = {1: "giá trị số nguyên"}
mapping[True] = "giá trị boolean"
mapping[1.0] = "giá trị số thực"

assert len(mapping) == 1
assert mapping[1] == "giá trị số thực"
```

Lý do là `True`, `1` và `1.0` so sánh bằng nhau trong Python và có hash tương thích. Chúng đại diện cho **một khóa logic** trong `dict`.

Nếu nghiệp vụ muốn phân biệt định danh theo loại, hãy mã hóa **loại định danh thành một phần của khóa**:

```python
ids = {
    ("int", 1): "mã số",
    ("bool", True): "cờ",
    ("float", 1.0): "giá trị đo",
}

assert len(ids) == 3
```

Điều này đặc biệt quan trọng khi dùng dữ liệu từ JSON, biểu mẫu hoặc các nguồn có quy tắc chuyển đổi kiểu khác nhau.

## 5. Tính ổn định của khóa trong bảng băm

Nếu một khóa đã được đưa vào bảng băm, phần dữ liệu tham gia vào phép băm và phép bằng nhau cần giữ **ổn định** trong thời gian khóa còn ở đó.

Giả sử khóa có mã `"HV01"`, được băm vào một vị trí trong bảng. Nếu sửa mã thành `"HV99"` nhưng vị trí lưu trữ không được cập nhật, thao tác tra cứu theo mã mới có thể đi tới vị trí khác; tra cứu theo mã cũ lại không còn so sánh bằng. Kết quả có thể không tìm thấy mục đã chèn.

Python phòng tránh một số lỗi bằng cách không cho các kiểu mutable phổ biến như `list` và `dict` làm khóa. Tuy vậy, đối tượng do lập trình viên tự định nghĩa vẫn có thể vi phạm hợp đồng nếu triển khai `__hash__` không phù hợp.

### Dùng đối tượng khóa bất biến

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class StudentKey:
    organization_id: str
    student_id: str


key1 = StudentKey("ORG-A", "HV01")
key2 = StudentKey("ORG-A", "HV01")
key3 = StudentKey("ORG-B", "HV01")

assert key1 == key2
assert hash(key1) == hash(key2)

students = {key1: "An"}
students[key2] = "An cập nhật"

assert len(students) == 1
assert students[key1] == "An cập nhật"

students[key3] = "Bình"
assert len(students) == 2
```

`@dataclass(frozen=True)` tạo đối tượng có các trường không thể gán lại theo cách thông thường và, với các trường hashable như chuỗi, có thể sinh phép bằng nhau/hash tương thích. Các trường của khóa nên là kiểu bất biến hoặc có ngữ nghĩa băm ổn định; chỉ đánh dấu lớp là frozen không tự biến mọi đối tượng lồng bên trong thành bất biến sâu.

Ví dụ còn cho thấy một mã `HV01` có thể hợp lệ ở **hai tổ chức khác nhau**: nếu nghiệp vụ yêu cầu định danh toàn cục theo cặp tổ chức–học viên, cần dùng **khóa ghép** thay vì chỉ mã học viên.

### Khi định nghĩa phép bằng nhau tùy chỉnh

Nếu lập trình viên định nghĩa `__eq__` trên một lớp Python, `__hash__` có thể bị vô hiệu hóa theo quy tắc của ngôn ngữ; không nên tự ý đặt một hàm hash độc lập mà vi phạm `a == b ⇒ hash(a) == hash(b)`.

Một cách đơn giản là lưu **khóa bất biến đã chuẩn hóa** hoặc sử dụng kiểu dữ liệu hỗ trợ sinh `eq`/`hash` nhất quán, thay vì tùy chỉnh hai phương thức mà không có kiểm thử tính chất.

## 6. Bộ so sánh trong cấu trúc có thứ tự quyết định thế nào là trùng?

Với **tree set** hoặc **tree map** lưu khóa có thứ tự, bộ so sánh thường trả lời “khóa `a` có đứng trước khóa `b` không?”. Một cấu trúc như vậy có thể xem hai khóa **tương đương theo thứ tự** nếu chúng không được phân biệt bằng bộ so sánh.

Nếu một bộ so sánh `compare(a, b)` trả giá trị âm khi `a < b`, 0 khi tương đương, dương khi `a > b`, thì nhiều tree map/set coi:

```text
compare(a, b) == 0
```

là “khóa trùng” trong cấu trúc ấy. Điều này **có thể khác** kết quả `a.equals(b)` hoặc `a == b` theo kiểu dữ liệu.

Đối với bộ so sánh dạng `less(a, b)` dùng trong một số thư viện, hai khóa thường được coi tương đương khi:

```text
not less(a, b) and not less(b, a)
```

Đây là cơ chế quan trọng trong `std::map` và `std::set` của C++.

### Bộ so sánh chỉ xét độ dài: mất các khóa khác nội dung

Giả sử bộ so sánh sắp chuỗi theo **độ dài mà không có tiêu chí phụ**. Khi đó `"AA"` và `"BB"` có cùng độ dài, nên bộ so sánh không phân biệt được chúng, dù hai chuỗi khác nhau.

Ví dụ Java:

```java
import java.util.Comparator;
import java.util.Map;
import java.util.TreeMap;

public class Main {
    public static void main(String[] args) {
        Map<String, Integer> scores =
            new TreeMap<>(Comparator.comparingInt(String::length));

        scores.put("AA", 10);
        scores.put("BB", 20);  // Bộ so sánh coi "AA" và "BB" là cùng khóa

        System.out.println(scores.size());   // 1
        System.out.println(scores.get("AA")); // 20
        System.out.println(scores.get("BB")); // 20
    }
}
```

`TreeMap` ở đây **ghi đè giá trị của mục tương đương**. Vì vậy nếu nghiệp vụ yêu cầu phân biệt mọi chuỗi khác nội dung, bộ so sánh chỉ xét độ dài là **không phù hợp để định nghĩa khóa**.

Trong khi đó `HashMap<String, Integer>` của Java sẽ phân biệt `"AA"` và `"BB"` vì `String.equals` so sánh nội dung chuỗi.

### C++: tính tương đương được suy từ phép “nhỏ hơn”

```cpp
#include <cassert>
#include <map>
#include <string>

struct ByLengthOnly {
    bool operator()(const std::string& a,
                    const std::string& b) const {
        return a.size() < b.size();
    }
};

int main() {
    std::map<std::string, int, ByLengthOnly> scores;
    scores.emplace("AA", 10);
    scores.emplace("BB", 20);

    assert(scores.size() == 1);
    assert(scores.find("BB") != scores.end());
    assert(scores.at("BB") == 10);
}
```

Ở đây `std::map::emplace` có ngữ nghĩa chèn; cặp thứ hai **không được chèn** vì khóa tương đương đã có, nên giá trị vẫn là `10`. Điều này khác với `put` của Java `TreeMap` ở ví dụ trên, nơi giá trị được cập nhật thành `20`.

**Kết luận:** quy tắc trùng khóa nằm ở comparator, còn việc giữ hay thay giá trị khi trùng phụ thuộc thao tác `insert`, `put`, `emplace` hay `upsert`.

## 7. Bộ so sánh phải nhất quán và đủ phân biệt

Cấu trúc tìm kiếm có thứ tự cần một bộ so sánh ổn định, nhất quán. Trong C++, bộ so sánh của `std::map` phải thỏa **thứ tự yếu nghiêm ngặt** (*strict weak ordering*). Các điều kiện cốt lõi gồm:

- Không có `a < a` theo quy tắc so sánh.
- Nếu `a < b` thì không thể đồng thời `b < a`.
- Nếu `a < b` và `b < c` thì phải có `a < c`.
- Quan hệ tương đương suy từ việc không nhỏ hơn nhau theo cả hai chiều cũng phải nhất quán.

Một comparator tùy tiện có thể phá vỡ bất biến của cây, dẫn đến kết quả tìm kiếm/chèn/xóa sai hoặc hành vi không được bảo đảm.

### Sắp xếp theo điểm nhưng vẫn giữ khóa học viên phân biệt

Giả sử cần lưu học viên theo thứ tự **điểm giảm dần**. Nếu chỉ so sánh điểm, hai học viên bằng điểm có thể bị coi là trùng trong tree set/map. Hãy thêm **mã định danh** để phá hòa:

```java
import java.util.Comparator;
import java.util.Set;
import java.util.TreeSet;

public class Main {
    record Student(String id, int score) {}

    public static void main(String[] args) {
        Comparator<Student> byRank = Comparator
            .comparingInt(Student::score)
            .reversed()
            .thenComparing(Student::id);

        Set<Student> ranking = new TreeSet<>(byRank);

        ranking.add(new Student("HV01", 9));
        ranking.add(new Student("HV02", 9));
        ranking.add(new Student("HV03", 8));

        System.out.println(ranking.size());  // 3
    }
}
```

Ví dụ dùng cú pháp `record` của Java phiên bản hiện đại. Tiêu chí điểm giảm dần giúp sắp xếp để hiển thị; tiêu chí mã tăng dần giúp phân biệt các học viên có cùng điểm. Tuy nhiên, quy tắc này vẫn coi hai đối tượng **cùng mã và cùng điểm** là tương đương; nếu nghiệp vụ chỉ cho một học viên theo **mã** bất kể điểm hiện tại, nên dùng map `id → Student` và tạo danh sách sắp xếp phục vụ báo cáo, hoặc thiết kế khóa có thứ tự/định danh theo đúng yêu cầu.

### Vì sao “nhất quán với equals” có ích?

Ở Java, `TreeMap` hoạt động đúng theo bộ so sánh của nó, nhưng nếu kết quả `compare(a, b) == 0` không tương đương với `a.equals(b)`, cách xác định khóa có thể khác với hợp đồng thông thường của `Map` hoặc với `HashMap`.

Đây là nguồn lỗi khi chuyển đổi dữ liệu giữa các hiện thực: một map có thể giữ hai khóa phân biệt, trong khi map khác chỉ giữ một. Tốt nhất hãy **xác định rõ cùng một quy tắc đồng nhất khóa** khi nghiệp vụ đòi hỏi tính nhất quán giữa các cấu trúc.

## 8. Chuẩn hóa khóa khi nghiệp vụ có quy tắc riêng

Nhiều hệ thống quy định mã định danh **không phân biệt chữ hoa/thường**, loại khoảng trắng đầu/cuối hoặc có định dạng chuẩn. Một cách thực tế là **chuẩn hóa ngay tại biên đầu vào** rồi dùng khóa chuẩn hóa trong map/set.

```python
def normalize_id(raw_id: str) -> str:
    return raw_id.strip().casefold()

records = [
    (" HV01 ", "An"),
    ("hv01", "An cập nhật"),
    ("Hv02", "Bình"),
]

students = {}
for raw_id, name in records:
    students[normalize_id(raw_id)] = name

assert students == {
    "hv01": "An cập nhật",
    "hv02": "Bình",
}
```

`str.casefold()` là phép chuẩn hóa cho so khớp không phân biệt hoa/thường trong nhiều tình huống Unicode; tuy nhiên, các quy tắc định danh thực tế có thể còn phụ thuộc chuẩn hóa Unicode, ngôn ngữ và yêu cầu nghiệp vụ.

**Không tự động chuẩn hóa mọi khóa.** Một số hệ thống phân biệt `"ABC"` và `"abc"`; việc gộp chúng sẽ làm mất dữ liệu. Trước khi chọn chuẩn hóa, cần xác định:

1. Phần nào tạo nên **định danh**: mã nội bộ, tên hiển thị hay tổ hợp nhiều trường?
2. Có cho phép khác biệt về hoa/thường, khoảng trắng hoặc dấu hay không?
3. Khi hai bản ghi cùng khóa chuẩn hóa nhưng có **giá trị khác nhau**, phải ghi đè, giữ bản đầu, gộp dữ liệu hay báo xung đột?
4. Có cần giữ **giá trị khóa gốc** để hiển thị hoặc kiểm toán không?

### Phát hiện trùng sau khi chuẩn hóa

Nếu đang **nhập dữ liệu tài khoản**, thường cần phát hiện và báo xung đột thay vì tự ghi đè:

```python
def detect_normalized_duplicates(rows):
    seen = {}
    collisions = []

    for raw_id, payload in rows:
        canonical = raw_id.strip().casefold()
        if canonical in seen:
            collisions.append((canonical, seen[canonical], raw_id))
        else:
            seen[canonical] = raw_id

    return collisions

rows = [
    (" HV01 ", {"name": "An"}),
    ("hv02", {"name": "Bình"}),
    ("hv01", {"name": "Chi"}),
]

assert detect_normalized_duplicates(rows) == [
    ("hv01", " HV01 ", "hv01")
]
```

Ở ví dụ này, phần mềm không quyết định ai là tài khoản đúng; nó chỉ xác định hai chuỗi đầu vào **va chạm theo quy tắc định danh nghiệp vụ**. Đây là xung đột định danh, khác với **va chạm hàm băm**, nơi hai khóa có thể khác nhau hoàn toàn mà có cùng hash.

## 9. Trường hợp so sánh hai nguồn dữ liệu bằng set

Giả sử hai hệ thống gửi danh sách mã học viên với cách viết khác nhau:

```python
source_a = ["HV01", "HV02", "HV03"]
source_b = ["hv01", " hv02 ", "HV04"]
```

Nếu dùng set trực tiếp, `"HV01"` và `"hv01"` không bằng nhau theo chuỗi mặc định:

```python
raw_overlap = set(source_a) & set(source_b)
assert raw_overlap == set()
```

Nếu nghiệp vụ quy định chuẩn hóa mã học viên giống nhau:

```python
def canonical(text):
    return text.strip().casefold()

a = {canonical(value) for value in source_a}
b = {canonical(value) for value in source_b}

assert a & b == {"hv01", "hv02"}
assert a - b == {"hv03"}
assert b - a == {"hv04"}
```

Khi đó, **phép giao, hợp, hiệu và quan hệ tập con** đều được tính trên cùng một **miền khóa chuẩn hóa**. Nếu mỗi nguồn áp dụng một bộ quy tắc khác nhau, kết quả so sánh tập hợp có thể sai về nghiệp vụ dù thuật toán set được cài đúng.

## 10. Quy tắc trùng khóa ảnh hưởng tới thao tác và độ phức tạp

Đặt `n` là số **khóa phân biệt theo quy tắc tương đương đã chọn**. Nếu thay đổi quy tắc tương đương, giá trị `n` có thể thay đổi dù số bản ghi đầu vào không đổi.

| Cấu trúc | Cách xác định khóa trùng | Tìm / chèn / xóa điển hình | Bộ nhớ |
| --- | --- | --- | --- |
| Hash set / hash map | Equality và hash tương thích | Trung bình/kỳ vọng `O(1)` | `O(n)` |
| Tree set / tree map cân bằng | Tương đương theo comparator | `O(log n)` | `O(n)` |
| Mảng cặp chưa sắp | So sánh lần lượt theo quy tắc equality | `O(n)` cho tìm; chèn có kiểm tra trùng `O(n)` | `O(n)` |
| Mảng cặp đã sắp | So sánh theo thứ tự đã chọn | Tìm `O(log n)`; chèn/xóa có thể `O(n)` do dịch phần tử | `O(n)` |

Các mốc trên giả định **tính hash hoặc so sánh một khóa có chi phí hằng số**. Với khóa chuỗi dài hoặc comparator phức tạp, mỗi lần băm/so sánh còn có chi phí phụ thuộc độ dài khóa hoặc logic so sánh.

Một comparator không nhất quán có thể làm kết quả sai; do đó độ phức tạp tốt **không cứu được tính đúng đắn**.

### Khi quy tắc so sánh tốn nhiều thời gian

Ví dụ mỗi lần so sánh hai chuỗi dài cần kiểm tra nhiều ký tự, chi phí tra cứu tree map còn phụ thuộc số ký tự được đọc trong mỗi lần so sánh. Nếu mỗi phép so sánh tốn tối đa `O(L)`, tìm kiếm theo cây cân bằng tốn tối đa khoảng `O(L log n)` theo mô hình đơn giản.

Tương tự, hash của khóa chuỗi dài có thể mất `O(L)` để tính; Python có thể có tối ưu/cơ chế lưu hash cho một số kiểu bất biến, nhưng không nên xem mọi khóa tùy ý đều có chi phí băm đúng bằng một hằng số.

### Khi nhiều khóa va chạm băm

Hai khóa **không bằng nhau** vẫn có thể cùng hash. Nếu phân bố hash tệ, nhiều mục có thể nằm cùng vùng xử lý va chạm, khiến thao tác tốn hơn mức trung bình. Một số cách cài đặt có thể có giới hạn xấu nhất `O(n)` cho tìm/chèn/xóa trong tình huống va chạm nhiều. Vì vậy cần thiết kế hàm băm phù hợp và luôn bảo đảm `equal ⇒ same hash`.

## 11. Kiểm tra quy tắc bằng nhau và bộ so sánh

Trước khi dùng một kiểu khóa tùy chỉnh trong set/map, hãy kiểm tra bằng **các tình huống phản ví dụ**, không chỉ bằng một trường hợp chèn thành công.

### Kiểm tra bằng nhau và băm trong Python

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class CourseKey:
    school: str
    code: str

a = CourseKey("A", "CS101")
b = CourseKey("A", "CS101")
c = CourseKey("B", "CS101")

assert a == b
assert hash(a) == hash(b)
assert a != c

courses = {a: "Cấu trúc dữ liệu"}
courses[b] = "Cấu trúc dữ liệu nâng cao"
assert len(courses) == 1

courses[c] = "Cấu trúc dữ liệu của trường B"
assert len(courses) == 2
```

Kiểm thử này kiểm tra được các khóa bằng nhau có hash bằng nhau và được gom đúng. Nó chưa chứng minh **mọi** khóa đều tuân thủ hợp đồng; với kiểu khóa phức tạp, nên có bộ kiểm thử tính chất trên nhiều đầu vào.

### Kiểm tra comparator bằng các trường hợp hòa

Với một bộ so sánh sắp theo `(điểm giảm dần, mã tăng dần)`, hãy kiểm thử:

- Hai học viên **cùng điểm, khác mã** phải vẫn là hai khóa phân biệt nếu mã là định danh.
- Hai bản ghi **cùng mã, khác điểm** có thể cần được cập nhật theo mã, thay vì xem là hai khóa; nếu vậy comparator theo cả điểm và mã **không phải lựa chọn phù hợp để định danh**.
- Bộ so sánh phải cho kết quả ổn định, nhất quán qua nhiều lần sử dụng.
- Nếu khóa có thể thay đổi điểm sau khi nằm trong tree set, việc thay đổi trường tham gia so sánh **có thể phá vỡ vị trí trong cây**; nên xóa và chèn lại theo API phù hợp, hoặc lưu khóa bất biến và dữ liệu thay đổi ở nơi khác.

### Danh sách kiểm tra ngắn

| Câu hỏi thiết kế | Vì sao cần trả lời? |
| --- | --- |
| Khóa được đồng nhất theo trường nào? | Tránh gộp nhầm hai đối tượng nghiệp vụ |
| Equality có nhất quán, ổn định không? | Tránh tìm/xóa sai |
| Equality và hash có tương thích không? | Giữ đúng bất biến bảng băm |
| Comparator có tạo thứ tự hợp lệ không? | Giữ bất biến của cây có thứ tự |
| Khi comparator trả tương đương, nghiệp vụ có thật sự muốn gộp khóa không? | Tránh làm mất bản ghi |
| Có cần tiêu chí phá hòa không? | Giữ các khóa khác nhau trong sắp xếp |
| Quy tắc chuẩn hóa có thống nhất giữa các nguồn không? | Tránh bỏ sót hoặc gộp nhầm khi đối chiếu |
| Khi trùng khóa thì cập nhật, từ chối hay gộp? | Bảo vệ dữ liệu hiện có |

## 12. Những nhầm lẫn thường gặp

1. **“Hash bằng nhau nghĩa là hai khóa trùng.”** Sai. Cần so sánh bằng nhau; hai khóa khác nhau có thể va chạm hash.
2. **“Hai đối tượng khác nhau luôn là hai khóa khác nhau.”** Sai. Nếu equality coi chúng bằng nhau, set/map dựa trên băm sẽ xem là cùng khóa khi hợp đồng hash phù hợp.
3. **“Hai chuỗi trông giống nhau luôn bằng nhau.”** Sai. Khác hoa/thường, khoảng trắng hoặc biểu diễn Unicode có thể khiến so sánh mặc định cho kết quả khác.
4. **“Dùng comparator chỉ so điểm vẫn giữ đủ học viên cùng điểm.”** Không bảo đảm: tree set/map có thể coi các khóa không phân biệt theo comparator là trùng.
5. **“Bộ so sánh chỉ để quyết định thứ tự duyệt.”** Với nhiều tree set/map, nó còn quyết định **tương đương khóa**, ảnh hưởng trực tiếp tới số phần tử.
6. **“Có thể sửa tùy ý trường của khóa sau khi chèn.”** Nếu trường ấy tham gia hash/equality/comparison, kết quả tra cứu có thể sai.
7. **“Một quy tắc chuẩn hóa luôn phù hợp mọi ứng dụng.”** Quy tắc phụ thuộc vào định danh nghiệp vụ; gộp sai mã có thể gây mất dữ liệu.
8. **“Cùng quy tắc trùng khóa thì mọi API xử lý khóa trùng giống nhau.”** Không đúng. `put` có thể ghi đè; `insert`/`emplace` có thể không chèn khi đã có.
9. **“Chỉ cần so độ dài chuỗi là đã có thứ tự khóa hữu ích cho mọi bài toán.”** So độ dài không phân biệt các chuỗi cùng độ dài; phải bổ sung tiêu chí nếu cần giữ các chuỗi đó thành khóa riêng.
10. **“Phép toán set độc lập quy tắc equality.”** Hợp/giao/hiệu đều dựa trên khái niệm phần tử tương đương; đổi quy tắc sẽ có thể đổi kết quả.

## 13. Tự luyện tập

**Bài 1.** Trong Python, các khóa `1`, `True` và `1.0` có được giữ thành ba mục riêng trong một `dict` không? Giải thích quan hệ giữa equality và hash.

**Bài 2.** Một hệ thống nhận `"HV01"`, `"hv01"`, `" HV01 "`. Nếu quy định mã không phân biệt hoa thường và bỏ khoảng trắng ngoài, hãy viết hàm chuẩn hóa và tính số khóa phân biệt.

**Bài 3.** Hai đối tượng `a` và `b` có `hash(a) == hash(b)` nhưng `a != b`. Hash set có được chứa đồng thời chúng không? Vì sao?

**Bài 4.** Java `TreeMap` dùng comparator chỉ so `String.length()`. Sau `put("AB", 1)` và `put("CD", 2)`, map chứa bao nhiêu khóa? Lấy theo khóa `"AB"` sẽ ra giá trị gì?

**Bài 5.** Trong C++, `std::map` với comparator chỉ so độ dài nhận `emplace("AB", 1)` và `emplace("CD", 2)`. Số khóa là bao nhiêu và vì sao kết quả giá trị có thể khác Java `put`?

**Bài 6.** Một hệ thống xếp hạng theo điểm giảm dần nhưng cần giữ mọi học viên phân biệt theo mã. Hãy nêu tiêu chí sắp xếp để không loại các học viên cùng điểm.

**Bài 7.** Viết ví dụ khóa ghép để phân biệt cùng mã học viên `"HV01"` thuộc hai tổ chức khác nhau.

**Bài 8.** Vì sao không nên dùng đối tượng có trường khóa thay đổi được làm khóa hash map hoặc tree map? Cách nào an toàn hơn?

**Bài 9.** Với `A = {"HV01", "HV02"}` và `B = {"hv01", "HV03"}`, hãy tính giao trước và sau khi áp dụng quy tắc không phân biệt hoa thường; giải thích sự thay đổi.

<details>
<summary>Gợi ý đáp án</summary>

1. Chỉ một mục: Python coi `True == 1 == 1.0` và hash tương thích, nên những lần gán sau cập nhật cùng một khóa.
2. Có thể dùng `raw.strip().casefold()`; cả ba mã chuẩn hóa thành `"hv01"` nên chỉ một khóa phân biệt.
3. Có. Hash collision không đồng nghĩa equality; hash set phải kiểm tra bằng nhau để phân biệt.
4. Một khóa logic; `get("AB")` trả `2` vì `TreeMap.put` cập nhật giá trị của khóa tương đương.
5. Một khóa logic; `emplace` không thay giá trị mục đang tồn tại nên giá trị vẫn là `1`.
6. Sắp theo cặp `(-score, student_id)` nếu mã phân biệt và không đổi trong miền nghiệp vụ; hoặc dùng map theo mã, sắp bản sao phục vụ báo cáo.
7. Dùng khóa tuple như `("ORG-A", "HV01")` và `("ORG-B", "HV01")` hoặc kiểu khóa bất biến có hai trường.
8. Sửa trường dùng để băm/so sánh có thể khiến cấu trúc tìm sai vị trí. Dùng khóa bất biến; nếu muốn đổi định danh, xóa mục cũ rồi chèn khóa mới theo quy trình kiểm soát.
9. Trước chuẩn hóa, giao là tập rỗng. Sau khi chuẩn hóa hai nguồn bằng `casefold()`, giao là `{"hv01"}`.

</details>

## Ghi nhớ

**Quy tắc bằng nhau và bộ so sánh quyết định phần tử/khóa nào bị xem là trùng.** Với hash set/map, hai khóa bằng nhau phải có hash tương thích; cùng hash chưa chắc đã bằng nhau. Với tree set/map, các khóa không được bộ so sánh phân biệt có thể bị coi là cùng khóa, kể cả khi nội dung khác nhau. Hãy chọn **định danh nghiệp vụ**, **chuẩn hóa có chủ đích**, **khóa ổn định** và **bộ so sánh đủ phân biệt** trước khi chọn cách cài đặt; đồng thời xác định rõ hành vi khi chèn trùng và chi phí tra cứu, cập nhật, xóa.
