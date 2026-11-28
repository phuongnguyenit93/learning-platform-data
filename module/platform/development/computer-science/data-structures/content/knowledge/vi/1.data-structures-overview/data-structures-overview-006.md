# Cấu trúc tĩnh, động, khả biến và bất biến

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa cấu trúc dữ liệu **tĩnh** và **động** xét theo khả năng thay đổi sức chứa hoặc số phần tử.
- Phân biệt **khả biến (mutable)** và **bất biến (immutable)** qua khả năng sửa trạng thái của đối tượng sau khi tạo.
- Nhận ra đây là **hai tiêu chí độc lập**: một cấu trúc có kích thước cố định vẫn có thể thay đổi phần tử; một cấu trúc bất biến vẫn có thể tạo phiên bản mới với số phần tử khác đi.
- Đọc được ví dụ về mảng cố định, mảng động, danh sách liên kết, snapshot và cấu trúc bền vững (*persistent data structure*).
- Đánh giá chi phí thời gian, bộ nhớ, việc duy trì bất biến biểu diễn và nhu cầu lưu lịch sử trước khi chọn cấu trúc.

## 1. Hai câu hỏi cần phân biệt

Giả sử một nền tảng học tập phải lưu những bài đã hoàn thành của mỗi học viên. Hai quyết định thiết kế có liên quan nhưng không giống nhau:

1. **Danh sách có thể dài thêm hoặc ngắn lại không?** Câu hỏi này liên quan đến cách tổ chức **tĩnh hoặc động**.
2. **Có thể sửa chính danh sách hiện tại không?** Câu hỏi này liên quan đến việc dữ liệu **khả biến hoặc bất biến**.

Một hệ thống có thể thêm bài vào một danh sách đang có, hoặc tạo **danh sách mới** chứa thêm bài trong khi giữ nguyên phiên bản cũ. Cả hai đều cho phép danh sách được sử dụng ở thời điểm sau chứa nhiều bài hơn, nhưng hành vi cập nhật và chi phí lưu trữ rất khác nhau.

~~~mermaid
flowchart TD
    A["Nhu cầu quản lý bài học"]
    A --> S{"Kích thước/sức chứa có thể đổi?"}
    S --> F["Tĩnh: giới hạn cố định"]
    S --> D["Động: tăng hoặc giảm được"]
    A --> M{"Có sửa đối tượng hiện tại?"}
    M --> Y["Khả biến: thay đổi tại chỗ"]
    M --> N["Bất biến: tạo phiên bản mới"]
~~~

Trong bài này, *tĩnh* và *động* chủ yếu nói về **kích thước hoặc tổ chức của cấu trúc**, còn *khả biến* và *bất biến* nói về **cách cập nhật trạng thái**. Đây không phải bốn nhóm loại trừ nhau.

## 2. Cấu trúc dữ liệu tĩnh: kích thước đã được ấn định

Theo cách phân loại nhập môn, **cấu trúc dữ liệu tĩnh** có số vị trí hoặc sức chứa được xác định trước và không tự thay đổi trong vòng đời của một đối tượng. Ví dụ cơ bản là mảng C có số phần tử cố định:

~~~c
int scores[4] = {10, 20, 30, 40};
scores[1] = 25;        // Hợp lệ: sửa giá trị phần tử.
// scores[4] = 50;     // Sai: vượt khỏi phạm vi chỉ số 0..3.
~~~

Mảng `scores` có đúng bốn vị trí. Chương trình có thể truy cập `scores[i]` với `0 <= i < 4` trong **O(1)** thời gian theo mô hình bộ nhớ thông thường. Không thể thay đổi kích thước của chính mảng này thành năm vị trí. Truy cập `scores[4]` trong C là **hành vi không xác định**, không phải một cách mở rộng mảng.

Cấu trúc có sức chứa cố định cũng có thể quản lý **ít phần tử logic hơn số ô đã cấp phát**. Ví dụ, một buffer cho tối đa 100 yêu cầu có thể mới chứa 35 yêu cầu. Khi đó:

~~~text
capacity = 5, size = 3

  [A] [B] [C] [_] [_]
   0   1   2   3   4
~~~

Bất biến cơ bản là **`0 <= size <= capacity`**. Thêm một phần tử khi đã đầy phải bị từ chối hoặc chuyển dữ liệu sang cấu trúc khác. Nếu yêu cầu nghiệp vụ có giới hạn rõ ràng, sức chứa cố định giúp dự đoán bộ nhớ và tránh phải mở rộng trong quá trình vận hành. Đổi lại, hệ thống có thể lãng phí các ô chưa dùng hoặc không đáp ứng được khi nhu cầu vượt dự kiến.

**Không nhầm lẫn với những cách dùng khác của “static”.** Kiểu tĩnh/động trong hệ thống kiểu, từ khóa `static` trong C hoặc Java, thời gian sống của biến và việc cấp phát trên stack/heap là những chủ đề riêng. Chẳng hạn một mảng C cục bộ có kích thước cố định vẫn có thể được tạo trong mỗi lần gọi hàm; nó không nhất thiết có thời gian lưu trữ *static*.

## 3. Cấu trúc dữ liệu động: quy mô thay đổi khi chạy

**Cấu trúc dữ liệu động** cho phép thay đổi số phần tử hoặc cấp phát thêm dung lượng trong quá trình sử dụng. Hai cách hiện thực quan trọng là **mảng động** và **danh sách liên kết**.

### 3.1. Mảng động và chi phí mở rộng

Mảng động phân biệt:

- **Độ dài logic (`size`):** số phần tử đã thêm.
- **Sức chứa (`capacity`):** số phần tử có thể lưu trước khi phải mở rộng vùng chứa.

Khi `size == capacity` và cần thêm một phần tử, cấu trúc có thể tạo vùng nhớ lớn hơn rồi chuyển các phần tử cũ sang. Ví dụ minh họa một chiến lược tăng sức chứa:

~~~text
size=3, capacity=4: [A] [B] [C] [_]

Thêm D:
size=4, capacity=4: [A] [B] [C] [D]

Thêm E (cấp phát vùng mới):
size=5, capacity=8: [A] [B] [C] [D] [E] [_] [_] [_]
~~~

Trong Python, `list` được cài đặt như một mảng động chứa tham chiếu tới các đối tượng:

~~~python
completed = ["intro", "arrays"]
completed.append("stack")
assert completed == ["intro", "arrays", "stack"]

completed.pop()
assert completed == ["intro", "arrays"]
~~~

Với chiến lược mở rộng sức chứa phù hợp, thêm cuối mảng động có chi phí **O(1) khấu hao**: phần lớn lần thêm là O(1), nhưng đôi khi phải sao chép O(n) tham chiếu để mở rộng. Chèn hoặc xóa ở giữa thường **O(n)** vì cần dịch chuyển các phần tử. Mảng động linh hoạt về số lượng nhưng phải đánh đổi giữa sức chứa dư và tần suất cấp phát lại.

### 3.2. Danh sách liên kết thay đổi số nút

Trong **danh sách liên kết**, các nút giữ giá trị và tham chiếu đến nút kế tiếp. Không cần một dãy ô nhớ liên tục đủ lớn:

~~~text
head
 |
 v
[A | next] -> [B | next] -> [C | None]
~~~

Nếu đã biết đầu danh sách, thêm một nút mới vào đầu chỉ cần tạo nút và điều chỉnh tham chiếu, thường **O(1)**. Nhưng lấy phần tử thứ `i` cần đi qua các liên kết, tốn O(i), tối đa **O(n)**. Mỗi nút có chi phí tham chiếu và cấp phát; các nút thường không nằm liên tiếp trong bộ nhớ.

Một danh sách liên kết thông thường có thể **động và khả biến** khi thay đổi liên kết của các nút đang tồn tại. Cũng có thể thiết kế danh sách liên kết **bất biến**, tạo nút mới để xây phiên bản khác mà không sửa các nút cũ.

### 3.3. So sánh tĩnh và động

| Tiêu chí | Tĩnh theo sức chứa | Động theo số phần tử |
| --- | --- | --- |
| Khả năng mở rộng | Bị giới hạn bởi số vị trí đã ấn định | Có thể cấp phát/giải phóng hoặc tổ chức lại |
| Ví dụ | Mảng C `int a[4]`, buffer cố định | Mảng động, danh sách liên kết, cây thay đổi số nút |
| Lợi thế | Dự đoán giới hạn lưu trữ, đơn giản về dung lượng | Linh hoạt khi đầu vào tăng giảm |
| Đánh đổi | Có thể đầy hoặc để dư chỗ | Chi phí cấp phát lại, nút, liên kết, phân mảnh |
| Kết luận về tính khả biến | **Chưa biết** | **Chưa biết** |

Kích thước **của một đối tượng** và kích thước **giữa các phiên bản khác nhau** cũng cần tách bạch. Một `tuple` có độ dài cố định sau khi tạo, nhưng chương trình vẫn có thể tạo `tuple` mới dài hơn. Đó là tạo phiên bản mới, không phải mở rộng đối tượng cũ.

## 4. Khả biến: thay đổi trực tiếp trạng thái hiện tại

Một đối tượng **khả biến (mutable)** cho phép chỉnh sửa trạng thái của chính nó sau khi tạo. `list`, `dict`, `set` của Python là những ví dụ quen thuộc:

~~~python
lessons = ["intro", "arrays"]
same_lessons = lessons

lessons.append("stack")

assert lessons is same_lessons
assert same_lessons == ["intro", "arrays", "stack"]
~~~

Hai biến trên cùng tham chiếu **một** đối tượng. Việc cập nhật qua `lessons` cũng hiện ra khi đọc qua `same_lessons`. Hiện tượng nhiều biến cùng tham chiếu một đối tượng được gọi là **aliasing** (bí danh).

Điều này rất tiện khi nhiều hàm cùng cần cập nhật cấu trúc nhưng cũng có thể tạo lỗi. Chẳng hạn, nếu một màn hình giữ tham chiếu tới danh sách mà thành phần khác thay đổi ngầm, màn hình sẽ thấy dữ liệu khác với trạng thái mà nó tưởng đã lưu.

Khả biến không có nghĩa cập nhật nào cũng nhanh: sửa phần tử ở một chỉ số của mảng động thường O(1), nhưng chèn vào đầu vẫn O(n). Độ phức tạp phụ thuộc **phép toán** và **cách biểu diễn**, không chỉ phụ thuộc nhãn *mutable*.

## 5. Bất biến: cập nhật bằng cách tạo giá trị mới

Một đối tượng **bất biến (immutable)** không cho phép thay đổi trạng thái quan sát được của chính nó theo hợp đồng sử dụng. Muốn có dữ liệu khác, ta tạo một **đối tượng hoặc phiên bản mới**.

Ví dụ với `tuple` Python:

~~~python
original = ("intro", "arrays")
new_version = original + ("stack",)

assert original == ("intro", "arrays")
assert new_version == ("intro", "arrays", "stack")
assert original is not new_version
~~~

Phép nối không sửa `original`; nó tạo `tuple` mới và sao chép các tham chiếu cũ. Với `n` phần tử ban đầu, phép nối có chi phí **O(n)** thời gian và bộ nhớ bổ sung.

**Đối tượng bất biến không đồng nghĩa biến không được gán lại**:

~~~python
current = ("intro",)
previous = current
current = current + ("arrays",)

assert current == ("intro", "arrays")
assert previous == ("intro",)
~~~

Tên biến `current` chỉ được gán sang một đối tượng khác. Đối tượng mà `previous` tham chiếu vẫn nguyên vẹn.

### 5.1. Bất biến nông và bất biến sâu

Một cấu trúc bên ngoài không cho phép gán lại phần tử vẫn có thể chứa **đối tượng con khả biến**:

~~~python
record = (["intro"], "student-01")

record[0].append("arrays")    # Sửa list bên trong tuple.
assert record == (["intro", "arrays"], "student-01")
~~~

`tuple` bất biến về việc gán lại các phần tử của chính nó, nhưng không tự biến `list` lồng trong thành bất biến. Đây là sự khác biệt giữa **bất biến nông (shallow immutability)** và **bất biến sâu (deep immutability)**. Tương tự, `@dataclass(frozen=True)` trong Python không tự đóng băng mọi `list` hoặc `dict` mà đối tượng giữ bên trong.

**Bất biến cũng không đồng nghĩa hashable.** Một `tuple` chứa `list` không thể làm khóa của `dict` vì thành phần `list` không hashable. Với bảng băm, khóa cần thỏa quy tắc băm, so sánh và giữ ổn định trong thời gian sử dụng.

## 6. Ma trận hai trục: bốn nhóm cấu trúc

| | **Khả biến: cập nhật tại chỗ** | **Bất biến: tạo đối tượng/phiên bản mới** |
| --- | --- | --- |
| **Tĩnh theo kích thước đối tượng** | Mảng C `int a[4]`: số ô cố định, giá trị ô sửa được | `tuple`, chuỗi `str`: kích thước và nội dung của đối tượng không được sửa tại chỗ |
| **Động theo các lần cập nhật hoặc phiên bản** | Mảng động `list`, danh sách liên kết khả biến, cây được thêm/xóa nút tại chỗ | Danh sách liên kết bất biến, cây bền vững: phiên bản mới có thể chứa nhiều/ít phần tử và chia sẻ nút cũ |

Trong ô **động + bất biến**, *động* đề cập khả năng quy mô **thay đổi giữa các phiên bản**, chứ không có nghĩa đối tượng bất biến tự lớn lên. Cùng một ý tưởng trừu tượng như stack, queue, cây hay đồ thị có thể được hiện thực theo những cách khác nhau trên hai trục.

## 7. Ví dụ: giữ lịch sử hoàn tác mà không làm đổi phiên bản cũ

Một trình soạn bài học cần lưu lịch sử để có thể hoàn tác. Nếu lưu một tham chiếu đến cấu trúc khả biến, “bản cũ” có thể đổi theo:

~~~python
lessons = ["intro", "arrays"]
history = [lessons]  # Cùng tham chiếu.

lessons.append("stack")
assert history[0] == ["intro", "arrays", "stack"]
~~~

Nếu muốn giữ bản cũ và phần tử đều là chuỗi bất biến, ta có thể sao chép nông danh sách:

~~~python
lessons = ["intro", "arrays"]
history = [lessons.copy()]

lessons.append("stack")
assert history[0] == ["intro", "arrays"]
assert lessons == ["intro", "arrays", "stack"]
~~~

Tạo bản sao bằng `list.copy()` cần **O(n)** thời gian và bộ nhớ theo số tham chiếu. Nếu các phần tử lại chứa đối tượng con khả biến, sao chép nông chưa đủ để bảo vệ toàn bộ trạng thái lịch sử. Cần quản lý quyền sửa, sao chép sâu khi thích hợp hoặc dùng những thành phần bất biến.

### 7.1. Cấu trúc dữ liệu bền vững và chia sẻ cấu trúc

**Cấu trúc dữ liệu bền vững (persistent data structure)** duy trì khả năng truy cập các phiên bản cũ sau khi có cập nhật. Nhiều cách cài đặt tận dụng **structural sharing** (chia sẻ cấu trúc): chỉ tạo những nút mới cần thiết và dùng lại phần cũ không đổi.

Xét một danh sách liên kết bất biến: mỗi nút là cặp `(giá_trị, đuôi)`, trong đó giá trị minh họa là chuỗi bất biến.

~~~python
EMPTY = None


def cons(value, tail=EMPTY):
    return (value, tail)


def head(linked):
    if linked is EMPTY:
        raise IndexError("Danh sách rỗng")
    return linked[0]


def tail(linked):
    if linked is EMPTY:
        raise IndexError("Danh sách rỗng")
    return linked[1]


def to_list(linked):
    result = []
    while linked is not EMPTY:
        result.append(head(linked))
        linked = tail(linked)
    return result


v1 = cons("arrays", cons("intro"))
v2 = cons("stack", v1)

assert to_list(v1) == ["arrays", "intro"]
assert to_list(v2) == ["stack", "arrays", "intro"]
assert tail(v2) is v1
~~~

Sơ đồ chia sẻ phần đuôi:

~~~text
v1 ---> [arrays] ---> [intro] ---> None
           ^
           |
v2 ---> [stack] --+
~~~

Tạo `v2` chỉ cần thêm một nút mới, **O(1)** thời gian và bộ nhớ bổ sung; `v1` vẫn nguyên vẹn. Không phải mọi cập nhật vào danh sách bất biến đều O(1): sửa ở vị trí thứ `i` thường phải tạo lại các nút trên đường đi tới đó, chi phí O(i). Trong **cây tìm kiếm cân bằng bất biến**, thay đổi một khóa có thể tạo lại đường từ gốc xuống nút được sửa, thường **O(log n)** thời gian và bộ nhớ mới cho mỗi lần cập nhật, trong khi chia sẻ các nhánh khác.

Từ **persistent** ở đây nói về **giữ các phiên bản cũ có thể truy cập**, khác với *durable persistence* tức lưu dữ liệu bền vững xuống ổ đĩa hoặc cơ sở dữ liệu. Các cấu trúc `v1`, `v2` vẫn có thể biến mất khi tiến trình kết thúc nếu không được lưu vào nơi bền vững.

Giữ nhiều phiên bản không miễn phí: các nút cũ còn được tham chiếu tiếp tục chiếm bộ nhớ. Chia sẻ cấu trúc giúp giảm bản sao, nhưng bộ nhớ vẫn tăng theo số nút mới và số phiên bản còn được giữ.

### 7.2. Vì sao biểu diễn bất biến quyết định hiệu suất?

Nếu lặp lại `current = current + (x,)` trên `tuple` từ rỗng cho `n` phần tử, mỗi lần nối phải sao chép các tham chiếu đã có. Tổng công việc tăng theo `1 + 2 + ... + n`, tức **O(n²)**. Trong khi đó, nếu bài toán chỉ cần **thêm đầu**, xây `n` nút bằng `cons` trên danh sách liên kết bất biến có thể tốn tổng **O(n)**.

Điều đó cho thấy *bất biến* không tự gây ra một độ phức tạp cố định; cách tổ chức và thao tác được chọn mới quyết định chi phí.

## 8. “Bất biến” của đối tượng khác “bất biến” của thuật toán

Trong tiếng Việt, **bất biến** còn là cách dịch của **invariant** — tính chất phải luôn đúng ở các thời điểm được quy định của một thuật toán hay cấu trúc dữ liệu.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Immutable object** | Đối tượng có cho phép thay đổi trạng thái sau khi tạo không? | `tuple` không cho phép gán lại phần tử |
| **Invariant** | Điều kiện nào phải được giữ đúng trước và sau các thao tác hợp lệ? | `0 <= size <= capacity`; mọi cha trong min-heap không lớn hơn con |

**Cấu trúc khả biến vẫn có invariant.** Chẳng hạn, min-heap khả biến có thể thêm/xóa phần tử, nhưng phải khôi phục quan hệ thứ tự giữa các nút bằng các thuật toán `sift-up` hoặc `sift-down`. Cấu trúc bất biến cũng phải giữ các ràng buộc hợp lệ ở **mỗi phiên bản**.

### 8.1. Stack sức chứa cố định nhưng khả biến

Ta có thể mô phỏng bằng Python một stack có **sức chứa giới hạn cố định**. Bên trong dùng `list` làm vùng lưu, nhưng giao diện lớp không cho phép tăng số vị trí:

~~~python
class BoundedStack:
    def __init__(self, capacity):
        if capacity < 0:
            raise ValueError("Sức chứa không âm")
        self._slots = [None] * capacity
        self._size = 0

    def push(self, value):
        if self._size == len(self._slots):
            raise OverflowError("Stack đầy")
        self._slots[self._size] = value
        self._size += 1

    def pop(self):
        if self._size == 0:
            raise IndexError("Stack rỗng")
        self._size -= 1
        result = self._slots[self._size]
        self._slots[self._size] = None
        return result

    def peek(self):
        if self._size == 0:
            raise IndexError("Stack rỗng")
        return self._slots[self._size - 1]

    def size(self):
        return self._size


stack = BoundedStack(2)
stack.push("A")
stack.push(None)  # None vẫn có thể là dữ liệu hợp lệ.
assert stack.size() == 2
assert stack.peek() is None

try:
    stack.push("C")
except OverflowError:
    pass
else:
    raise AssertionError("Stack đầy phải từ chối thêm")

assert stack.pop() is None
assert stack.pop() == "A"
~~~

Những bất biến quan trọng gồm `0 <= _size <= len(_slots)`; các ô từ `0` đến `_size - 1` là phần tử logic của stack; ô `_size - 1` là đỉnh khi không rỗng. Số ô không đổi, nhưng giá trị các ô và `_size` có thể cập nhật. Đây là thiết kế **sức chứa cố định + khả biến**, với thao tác `push`, `pop`, `peek` đều O(1); `push` phải từ chối khi đầy.

## 9. So sánh thời gian và bộ nhớ

Với `n` phần tử, các chi phí điển hình là:

| Cấu trúc và phép toán | Thời gian | Bộ nhớ / đánh đổi |
| --- | --- | --- |
| Mảng cố định: truy cập chỉ số | **O(1)** | Cần chỗ lưu cho toàn bộ sức chứa |
| Mảng động khả biến: thêm cuối | **O(1) khấu hao** | Có chỗ dự phòng; đôi khi cấp phát lại O(n) |
| Mảng động khả biến: chèn/xóa giữa | **O(n)** | Phải dịch phần tử |
| Danh sách liên kết khả biến: thêm đầu | **O(1)** | Cấp phát nút và tham chiếu |
| Danh sách liên kết: lấy phần tử thứ `i` | **O(i)**, xấu nhất **O(n)** | Cần đi theo liên kết |
| `tuple` bất biến: nối thêm cuối | **O(n)** | Sao chép tham chiếu vào đối tượng mới |
| Danh sách liên kết bất biến: thêm đầu | **O(1)** | Một nút mới, chia sẻ đuôi cũ |
| Cây cân bằng bất biến: cập nhật một khóa | Thường **O(log n)** | Tạo lại đường cập nhật, chia sẻ các nhánh khác |

Ký hiệu **O(1) khấu hao** không nói rằng mỗi lần thêm cuối mảng động đều O(1); khi cần mở rộng, một lần thêm có thể tốn O(n). “Tĩnh” cũng không tự bảo đảm nhanh hơn “động”: một buffer cố định có thể cần duyệt O(n), trong khi bảng băm động cho tra cứu theo khóa thường O(1) kỳ vọng.

Với cấu trúc bất biến, bộ nhớ phải xét theo **số phiên bản cần giữ**, không chỉ kích thước phiên bản mới nhất. Cây bền vững có thể tiết kiệm bản sao nhờ chia sẻ nhánh nhưng cũng duy trì những nút của phiên bản cũ cho đến khi không còn được tham chiếu.

## 10. Chọn cấu trúc theo nhu cầu thực tế

| Nhu cầu | Lựa chọn khởi đầu hợp lý | Lý do |
| --- | --- | --- |
| Bảng trạng thái của đúng 12 tháng | Mảng kích thước cố định, khả biến nếu cần sửa ô | Số ô được biết trước |
| Danh sách bài thường xuyên thêm/xóa, truy cập theo chỉ số | Mảng động khả biến | Truy cập vị trí O(1), thêm cuối O(1) khấu hao |
| Hàng đợi chấm bài thay đổi theo lượng yêu cầu | Queue động, ví dụ `deque` | Thêm cuối và lấy đầu O(1), tuân thủ FIFO |
| Tra bài theo mã nhiều lần | Bảng băm khả biến hoặc chỉ mục phù hợp | Tra theo khóa thường O(1) kỳ vọng |
| Hoàn tác chỉnh sửa hoặc xem lại lần phát hành cũ | Snapshot bất biến hoặc cấu trúc bền vững | Phiên bản cũ không bị cập nhật mới làm thay đổi |
| Cây mục lục cần giữ lịch sử phiên bản | Cây bền vững nếu chi phí phù hợp | Có thể chia sẻ nhánh không đổi |
| Đồ thị tiên quyết được cập nhật thường xuyên | Danh sách kề khả biến hoặc đồ thị có phiên bản | Chọn theo thao tác, chu trình và nhu cầu lịch sử |

**Không thể xếp toàn bộ cây, heap, bảng băm hoặc đồ thị vào một nhóm tĩnh/động, khả biến/bất biến cố định.** Mỗi mô hình có thể có nhiều cách cài đặt với những hợp đồng và chi phí khác nhau.

### Những câu hỏi nên đặt trước khi triển khai

1. Quy mô có được biết trước hay cần tăng giảm không? Có giới hạn trên rõ ràng?
2. Thao tác chính là cập nhật phần tử, thay độ dài, tra theo khóa, chèn giữa, hay giữ lịch sử?
3. Có thành phần khác giữ tham chiếu tới trạng thái cũ không? Việc sửa tại chỗ có gây tác dụng phụ?
4. Có cần bất biến sâu cho toàn bộ bản ghi và các đối tượng lồng nhau không?
5. Những invariant nào cần duy trì: khóa duy nhất, LIFO/FIFO, `size <= capacity`, thuộc tính heap hay đồ thị không chu trình?
6. Cấu trúc được truy cập đồng thời không? **Bất biến giúp tránh sửa đối tượng dùng chung**, nhưng việc thay thế tham chiếu chung hoặc cập nhật qua nhiều bước vẫn có thể cần cơ chế đồng bộ.
7. Tổng chi phí lưu trữ, sao chép, duy trì chỉ mục và số phiên bản phải giữ có phù hợp không?

Độ phức tạp Big O là điểm khởi đầu; cần đo trên quy mô và mẫu thao tác gần với ứng dụng. Mảng động có thể nhanh nhờ tính cục bộ bộ nhớ; danh sách liên kết chịu chi phí nút và con trỏ; cấu trúc bền vững có thể đổi bộ nhớ để nhận được khả năng dùng lại phiên bản cũ.

## 11. Những hiểu lầm thường gặp

- **“Tĩnh nghĩa là không thể đổi giá trị.”** Sai: mảng có kích thước cố định vẫn sửa được phần tử nếu không có ràng buộc khác.
- **“Động nghĩa là mọi cập nhật diễn ra tại chỗ.”** Sai: cấu trúc bền vững có thể tạo phiên bản khác với số phần tử thay đổi mà không sửa phiên bản cũ.
- **“Gán `saved = current` đã tạo snapshot.”** Sai với đối tượng khả biến Python: đó là hai tham chiếu tới cùng một đối tượng.
- **“`tuple` làm mọi dữ liệu bên trong trở thành bất biến sâu.”** Sai: `tuple` có thể chứa `list` vẫn sửa được.
- **“Bất biến đồng nghĩa hashable.”** Sai: `tuple` chứa `list` không hashable.
- **“Persistent nghĩa là tự lưu trên ổ đĩa.”** Sai trong ngữ cảnh cấu trúc dữ liệu: persistent nghĩa là các phiên bản cũ còn truy cập được.
- **“Immutable và invariant là cùng một khái niệm.”** Sai: một bên nói về quyền sửa đối tượng, một bên nói về tính chất đúng cần duy trì.
- **“Dùng đối tượng bất biến là đủ để bảo đảm mọi truy cập đồng thời an toàn.”** Sai: phối hợp thay đổi tham chiếu và giao dịch vẫn có thể cần đồng bộ hóa.

## 12. Bài tập vận dụng

**Bài 1 — Phân loại theo hai trục.** Một mảng C `int scores[5]` có năm phần tử. Chương trình thường xuyên cập nhật `scores[2]`. Đây là cấu trúc tĩnh hay động? Khả biến hay bất biến?

*Gợi ý:* Tĩnh theo số ô, khả biến vì giá trị tại một ô có thể sửa.

**Bài 2 — Bí danh.** Với `current = ["A", "B"]; saved = current; current.append("C")`, `saved` chứa gì? Làm thế nào giữ danh sách cũ nếu các phần tử chỉ là chuỗi?

*Gợi ý:* `saved` cũng trở thành `["A", "B", "C"]`. Sao chép danh sách trước khi cập nhật, ví dụ `saved = current.copy()`. Nếu phần tử lồng nhau khả biến, cần xem xét sao chép sâu hoặc dùng dữ liệu bất biến.

**Bài 3 — Chi phí phiên bản.** Tại sao xây `tuple` từ rỗng bằng cách lặp phép nối thêm cuối `n` lần có thể tốn O(n²), trong khi thêm đầu trên danh sách liên kết bất biến chỉ tốn tổng O(n)?

*Gợi ý:* `tuple` phải sao chép mọi tham chiếu cũ trong mỗi lần nối; danh sách liên kết bất biến chỉ tạo một nút mới và dùng lại phần đuôi.

**Bài 4 — Bất biến và invariant.** Một min-heap lưu bằng mảng động có thể thêm, xóa phần tử nhưng phải giữ `parent <= child` sau mỗi thao tác. Tính khả biến của heap khác invariant này ra sao?

*Gợi ý:* Đối tượng heap là khả biến vì trạng thái và số phần tử có thể đổi; quan hệ thứ tự cha – con là điều kiện phải được thuật toán duy trì.

**Bài 5 — Thiết kế thực tế.** Hệ thống có một triệu bài học, cần tra theo mã thường xuyên, thêm bài mỗi ngày và xem lại nội dung theo từng lần phát hành. Có nên dùng đúng một cấu trúc không?

*Gợi ý:* Có thể kết hợp chỉ mục băm để tra theo mã với cấu trúc lưu phiên bản hoặc snapshot cho lịch sử. Cần tính chi phí cập nhật chỉ mục, quản lý tham chiếu và bộ nhớ của các phiên bản.

## Tổng kết

**Tĩnh và động** trả lời câu hỏi về sức chứa và khả năng thay đổi quy mô; **khả biến và bất biến** trả lời câu hỏi trạng thái của đối tượng hiện tại có thể bị sửa sau khi tạo hay không. Hai tiêu chí độc lập: một mảng cố định vẫn có thể thay đổi phần tử; một cấu trúc bất biến có thể tạo nhiều phiên bản dài ngắn khác nhau. Khi lựa chọn mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap hoặc đồ thị, cần xét **thao tác thực tế, invariant, khả năng giữ phiên bản, thời gian, bộ nhớ và nhu cầu chia sẻ dữ liệu**. Những yếu tố đó mới quyết định cấu trúc nào phù hợp với bài toán.
