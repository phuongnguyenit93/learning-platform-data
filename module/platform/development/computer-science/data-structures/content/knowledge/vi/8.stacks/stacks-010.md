# Lịch sử hoàn tác và giới hạn của mô hình một ngăn xếp

## 1. Hoàn tác là một bài toán LIFO

Trong học phần **Cấu trúc dữ liệu**, **ngăn xếp (stack)** là kiểu dữ liệu trừu tượng tuân theo nguyên tắc **LIFO (Last In, First Out)**: phần tử được thêm vào sau cùng sẽ được lấy ra trước tiên. Stack thường cung cấp các thao tác `push(x)` để thêm đỉnh, `pop()` để lấy và xóa đỉnh, cùng `peek()` để xem đỉnh mà không làm thay đổi cấu trúc.

Khi người dùng chỉnh sửa văn bản, vẽ hình hoặc thay đổi một mô hình, họ thường muốn **Undo (hoàn tác)** thao tác gần nhất. Thứ tự hoàn tác là thứ tự **ngược với thứ tự thực hiện**:

```text
Thao tác 1: thêm chữ A
Thao tác 2: thêm chữ B
Thao tác 3: thêm chữ C

Tình trạng hiện tại: ABC

Undo lần 1 → bỏ tác động của bước 3 → AB
Undo lần 2 → bỏ tác động của bước 2 → A
Undo lần 3 → bỏ tác động của bước 1 → ""
```

Vì phải quay về trạng thái gần nhất trước tiên, stack là lựa chọn tự nhiên để lưu lịch sử. Tuy nhiên, **chỉ một stack** có thể hỗ trợ Undo theo LIFO nhưng không tự động hỗ trợ đầy đủ **Redo (làm lại)**, nhánh lịch sử hay khôi phục dữ liệu đã bị loại khỏi lịch sử.

Chủ đề này giúp làm rõ **bất biến, hợp đồng thao tác và độ phức tạp thời gian/bộ nhớ** khi áp dụng stack vào một tính năng thực tế, đồng thời chỉ ra **giới hạn của mô hình một ngăn xếp** để chọn cấu trúc phù hợp với yêu cầu ứng dụng.

## 2. Hai cách lưu một “bước có thể hoàn tác”

Trước khi viết mã, cần xác định **phần tử được push vào stack là gì**.

### Cách A — Lưu ảnh chụp trạng thái (snapshot)

Giả sử tài liệu hiện tại là `"AB"` và người dùng sửa thành `"ABC"`. Trước khi thay đổi, lưu bản `"AB"` lên stack. Khi Undo, lấy trạng thái này ra và đặt làm tài liệu hiện tại.

```text
Trước chỉnh sửa:   current = "AB", undo = ["", "A"]
Lưu trạng thái:    undo.push("AB")
Áp dụng chỉnh sửa: current = "ABC"

Sau chỉnh sửa:     current = "ABC", undo = ["", "A", "AB"]
Undo:             current = undo.pop() = "AB"
```

**Ưu điểm:** thuật toán đơn giản, dễ khôi phục chính xác trạng thái cũ nếu snapshot đầy đủ và không bị sửa ngoài ý muốn. **Hạn chế:** mỗi trạng thái có thể rất lớn; lưu nhiều snapshot dễ tốn bộ nhớ.

### Cách B — Lưu lệnh có thể đảo ngược (reversible command)

Thay vì lưu cả tài liệu, có thể lưu thao tác và thông tin cần thiết để đảo ngược:

- Thao tác “chèn `"C"` vào vị trí 2” có lệnh đảo là “xóa `"C"` ở vị trí 2”.
- Thao tác “xóa đoạn `"XY"` ở vị trí 5” muốn hoàn tác được thì phải nhớ **đoạn đã xóa và vị trí** để chèn lại.
- Thao tác “đổi màu từ đỏ sang xanh” cần giữ **màu trước đó** để trả về.

Lưu lệnh thường tiết kiệm hơn snapshot nếu thay đổi nhỏ so với tổng trạng thái. Nhưng không phải thao tác nào cũng đảo được một cách đơn giản: gửi email, thực hiện thanh toán hay cập nhật hệ thống bên ngoài có thể không có hành động hoàn tác hoàn hảo.

| Nội dung lưu trên stack | Undo hoạt động như thế nào? | Chi phí cần chú ý |
|---|---|---|
| Toàn bộ trạng thái trước chỉnh sửa | `pop` snapshot và khôi phục | Kích thước trạng thái, sao chép và giữ bản cũ |
| Lệnh kèm thông tin đảo ngược | `pop` lệnh, chạy hàm `undo` của lệnh | Dữ liệu cần để đảo lệnh; chi phí thực thi thao tác |
| Chênh lệch giữa hai phiên bản (diff) | Áp dụng diff đảo | Tạo và áp dụng diff; xử lý xung đột |

**Nguyên tắc:** một stack chỉ quyết định **thứ tự hoàn tác**; nó không tự biết phải khôi phục phần dữ liệu nào. Phần tử stack phải lưu đủ thông tin để Undo có kết quả đúng.

## 3. Mô hình một ngăn xếp: `current` và `undo_stack`

Thiết kế tối thiểu gồm:

- `current`: trạng thái đang hiển thị.
- `undo_stack`: các trạng thái **trước chỉnh sửa** còn có thể khôi phục, sắp theo thứ tự cũ → mới từ đáy đến đỉnh.

Một chỉnh sửa mới được áp dụng như sau:

```text
EDIT(new_state):
    if new_state bằng current:
        return KHÔNG_THAY_ĐỔI
    undo_stack.push(current)
    current = new_state
    return THÀNH_CÔNG
```

Hoàn tác:

```text
UNDO():
    if undo_stack rỗng:
        return KHÔNG_THỂ_HOÀN_TÁC
    current = undo_stack.pop()
    return THÀNH_CÔNG
```

### Ví dụ Python: Undo một chiều

Trong ví dụ, dùng `str` vì chuỗi Python là **bất biến**: giữ tham chiếu tới chuỗi cũ không làm nó thay đổi khi tài liệu mới được gán.

```python
class UndoOnlyText:
    def __init__(self, initial=""):
        self.current = initial
        self._undo = []

    def edit(self, new_text):
        if new_text == self.current:
            return False  # Không thêm bước lịch sử vô nghĩa

        self._undo.append(self.current)
        self.current = new_text
        return True

    def undo(self):
        if not self._undo:
            return False

        self.current = self._undo.pop()
        return True

    def can_undo(self):
        return bool(self._undo)


editor = UndoOnlyText("")
editor.edit("A")
editor.edit("AB")
editor.edit("ABC")

print(editor.current)   # ABC
print(editor.undo())    # True
print(editor.current)   # AB
print(editor.undo())    # True
print(editor.current)   # A
print(editor.undo())    # True
print(editor.current)   # ""
print(editor.undo())    # False: không còn lịch sử
```

### Bất biến của mô hình một stack

Sau mỗi thao tác thành công:

1. `current` là trạng thái hiện tại, không nằm trong `undo_stack` chỉ vì nó đang là trạng thái hiện tại.
2. Đỉnh của `undo_stack` là trạng thái cần khôi phục ở lần Undo kế tiếp.
3. Thứ tự từ đáy tới đỉnh là **các trạng thái trước chỉnh sửa theo thời gian**, từ cũ tới mới.
4. Khi Undo thất bại vì stack rỗng, `current` và `undo_stack` không thay đổi.

Ví dụ thực thi:

| Lệnh | `current` | `undo_stack` (đáy → đỉnh) |
|---|---|---|
| Khởi tạo | `""` | `[]` |
| `edit("A")` | `"A"` | `[""]` |
| `edit("AB")` | `"AB"` | `["", "A"]` |
| `edit("ABC")` | `"ABC"` | `["", "A", "AB"]` |
| `undo()` | `"AB"` | `["", "A"]` |
| `undo()` | `"A"` | `[""]` |
| `undo()` | `""` | `[]` |
| `undo()` | `""` | `[]` (thất bại) |

Nếu người dùng muốn Undo thêm một lần khi stack rỗng, ứng dụng nên trả một **trạng thái thất bại rõ ràng** hoặc vô hiệu hóa nút Undo, thay vì âm thầm làm sai dữ liệu.

## 4. Giới hạn lớn nhất của một stack: không giữ được đường làm lại

Hãy xét dãy:

```text
"" → A → AB → ABC
             ^
          Undo từ ABC về AB
```

Trước Undo, `undo_stack = ["", "A", "AB"]` và `current = "ABC"`. Khi `pop` phần tử `"AB"` để khôi phục, mô hình một stack cập nhật:

```text
current = "AB"
undo_stack = ["", "A"]
```

**Trạng thái `"ABC"` không còn được lưu ở đâu trong mô hình đó.** Nếu ngay sau đó người dùng chọn Redo, chương trình không thể suy ra duy nhất trạng thái cần khôi phục chỉ từ `current = "AB"` và `undo_stack = ["", "A"]`.

Ví dụ, cả hai lịch sử sau đều có thể dẫn tới cùng trạng thái `current = "AB"` sau Undo:

```text
Lịch sử 1: "" → A → AB → ABC, sau đó Undo
Lịch sử 2: "" → A → AB → AB!, sau đó Undo

Kết quả trong mô hình một stack:
    current = "AB"
    undo_stack = ["", "A"]

Nhưng Redo đúng phải là "ABC" ở lịch sử 1,
và là "AB!" ở lịch sử 2.
```

Do đó, từ thông tin còn lại, **không thể xác định Redo chính xác cho mọi lịch sử**.

Đây không phải lỗi của thao tác `pop`. Một stack một chiều được thiết kế để **bỏ phần tử đỉnh sau khi lấy ra**. Muốn hỗ trợ Redo, ta phải **lưu dữ liệu vừa rời khỏi lịch sử** ở nơi khác.

### Có thể “lách” bằng một biến tạm không?

Một biến như `last_undone` có thể giữ **một bước** Redo. Nhưng nếu người dùng Undo nhiều bước rồi Redo nhiều bước, một biến đơn lẻ không đủ biểu diễn cả chuỗi trạng thái chờ làm lại. Nếu lưu tất cả chúng vào một danh sách, thực chất ta đã thêm một cấu trúc lịch sử thứ hai.

Có thể thiết kế lịch sử dưới dạng **một mảng và con trỏ vị trí (cursor)**, hoặc các bản ghi chứa cả quá khứ và tương lai. Đây là những phương án hợp lệ, nhưng chúng không còn là **mô hình chỉ có một stack LIFO thuần túy cho Undo** như phần 3. Hãy phân biệt *một vùng chứa vật lý* với *một hợp đồng thao tác LIFO đơn giản*.

## 5. Hai stack cho Undo và Redo

Để hỗ trợ hai chiều lịch sử tuyến tính, thường dùng:

- `undo_stack`: các trạng thái **quá khứ**.
- `redo_stack`: các trạng thái **tương lai đã bị Undo** nhưng có thể làm lại.
- `current`: trạng thái đang hiển thị.

### Quy tắc chuyển trạng thái

**Chỉnh sửa mới `edit(new_state)`:**

1. Nếu không thay đổi, giữ nguyên cả ba thành phần.
2. Push `current` cũ vào `undo_stack`.
3. Gán `current = new_state`.
4. Xóa `redo_stack`, vì người dùng đã chọn một nhánh lịch sử mới.

**Undo:**

1. Nếu `undo_stack` rỗng, trả thất bại và giữ nguyên.
2. Push `current` vào `redo_stack`.
3. Pop `undo_stack` để trở lại trạng thái trước đó.

**Redo:**

1. Nếu `redo_stack` rỗng, trả thất bại và giữ nguyên.
2. Push `current` vào `undo_stack`.
3. Pop `redo_stack` để tiến tới trạng thái từng bị Undo.

Sơ đồ minh họa:

```text
                 edit("ABC")
     [A, AB]  -----------------> current ABC
      undo                             redo []
                     Undo
     [A]     <----------------- current AB
      undo                             redo [ABC]

                     Redo
     [A, AB]  -----------------> current ABC
      undo                             redo []
```

Các stack trong sơ đồ chỉ lược bớt trạng thái ban đầu để dễ nhìn; quy tắc chuyển vẫn như nhau.

### Mã Python: lịch sử hai chiều

```python
class TextHistory:
    def __init__(self, initial=""):
        self.current = initial
        self._undo = []
        self._redo = []

    def edit(self, new_text):
        if new_text == self.current:
            return False

        self._undo.append(self.current)
        self.current = new_text
        self._redo.clear()
        return True

    def undo(self):
        if not self._undo:
            return False

        self._redo.append(self.current)
        self.current = self._undo.pop()
        return True

    def redo(self):
        if not self._redo:
            return False

        self._undo.append(self.current)
        self.current = self._redo.pop()
        return True

    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)


history = TextHistory("")
history.edit("A")
history.edit("AB")
history.edit("ABC")

history.undo()
print(history.current)  # AB

history.undo()
print(history.current)  # A

history.redo()
print(history.current)  # AB

history.edit("AB!")
print(history.current)  # AB!
print(history.redo())   # False
```

Cách lưu này hỗ trợ Undo/Redo cho **lịch sử tuyến tính**. `edit` sẽ loại bỏ nhánh Redo khi phát sinh chỉnh sửa mới, thay vì duy trì một cây phiên bản có nhiều nhánh.

### Vết thực thi đầy đủ

Quy ước bên phải là đỉnh của stack:

| Lệnh | `current` | `undo_stack` | `redo_stack` |
|---|---|---|---|
| Khởi tạo | `""` | `[]` | `[]` |
| `edit("A")` | `"A"` | `[""]` | `[]` |
| `edit("AB")` | `"AB"` | `["", "A"]` | `[]` |
| `edit("ABC")` | `"ABC"` | `["", "A", "AB"]` | `[]` |
| `undo()` | `"AB"` | `["", "A"]` | `["ABC"]` |
| `undo()` | `"A"` | `[""]` | `["ABC", "AB"]` |
| `redo()` | `"AB"` | `["", "A"]` | `["ABC"]` |
| `edit("AB!")` | `"AB!"` | `["", "A", "AB"]` | `[]` |
| `redo()` | `"AB!"` | `["", "A", "AB"]` | `[]` (thất bại) |

Sau hai lần Undo, đỉnh `redo_stack` là `"AB"`: đây chính là trạng thái cần tiến tới **trước** khi có thể Redo tiếp tới `"ABC"`. LIFO trên `redo_stack` bảo đảm thứ tự làm lại đúng.

## 6. Bất biến và chứng minh hành vi đúng

Đối với lịch sử hai stack, cần giữ các bất biến:

1. `current` luôn là trạng thái có hiệu lực.
2. Đỉnh `undo_stack` là trạng thái trước gần nhất có thể khôi phục.
3. Đỉnh `redo_stack` là trạng thái tiếp theo gần nhất có thể làm lại.
4. Chỉnh sửa mới **làm rỗng Redo** nếu thực sự thay đổi trạng thái.
5. Undo/Redo thất bại vì lịch sử rỗng **không được làm thay đổi** `current` hoặc các stack.

**Chứng minh theo thao tác:**

- **Khởi tạo:** cả hai stack rỗng, `current` đúng bằng trạng thái ban đầu; không có quá khứ hoặc tương lai để khôi phục.
- **Edit:** trạng thái cũ trở thành quá khứ gần nhất ở đỉnh Undo, trạng thái mới có hiệu lực; các trạng thái từng Undo không còn là đường làm lại hợp lệ của nhánh mới nên bị xóa.
- **Undo:** trạng thái vừa rời khỏi `current` được đẩy lên Redo trước khi `current` đổi thành phần tử quá khứ gần nhất. Nhờ vậy trạng thái vừa bỏ có thể được khôi phục ngay bằng Redo.
- **Redo:** chuyển động ngược lại: lưu trạng thái hiện tại vào Undo trước khi lấy trạng thái mới từ Redo. Người dùng có thể Undo lại bước vừa Redo.
- **Không có phần tử:** trả thất bại mà không sửa dữ liệu; bất biến được bảo toàn.

Chẳng hạn, `undo(); redo()` liên tiếp sẽ đưa người dùng trở lại đúng trạng thái ban đầu **nếu không có chỉnh sửa hoặc tác động khác xen vào**, và các thao tác đều thành công.

### Vì sao thứ tự cập nhật quan trọng?

Trong mô hình snapshot bất biến, ta phải giữ lại `current` cũ **trước khi gán `current` mới**. Nếu thực hiện `current = _undo.pop()` rồi mới push `current` vào Redo, trạng thái bị Undo sẽ mất: stack Redo nhận nhầm trạng thái đã khôi phục.

Tương tự, khi Redo phải giữ trạng thái cũ vào Undo trước khi thay đổi `current`. Đó là điểm cốt lõi để duy trì khả năng đi lại hai chiều trong lịch sử.

Các ví dụ dùng `list` Python và giả định các thao tác bộ nhớ thông thường thành công; trong hệ thống có yêu cầu chịu lỗi hoặc nhiều luồng, cần xem việc chuyển trạng thái là **một thao tác logic nguyên tử**, không để quan sát trạng thái nửa chừng.

## 7. Nhánh lịch sử và lý do phải xóa Redo sau một edit mới

Giả sử đang có lịch sử:

```text
A → AB → ABC
          ^
       current

Undo:
A → AB → ABC
     ^
  current

Sau đó sửa AB thành AB!:
A → AB ──→ ABC    (nhánh cũ)
       \
        └─→ AB!   (nhánh mới, current)
```

Mô hình **hai stack tuyến tính** chọn chỉ giữ nhánh mà người dùng vừa đi tiếp: `AB!`. Vì vậy lần `edit("AB!")` sẽ xóa Redo đang giữ `ABC`.

**Vì sao?** Nếu cho phép Redo tiếp từ `AB!` sang `ABC` mà không có quy tắc cụ thể, người dùng sẽ nhìn thấy một thay đổi không phải “làm lại thao tác vừa Undo” trên nhánh hiện tại. Lịch sử trở nên mơ hồ.

Nếu yêu cầu sản phẩm là **giữ nhiều nhánh** (như lịch sử phiên bản, hệ thống quản lý source code hoặc công cụ thiết kế có nhánh), một stack hoặc hai stack tuyến tính không còn đủ để mô hình hóa đầy đủ:

- Dùng **cây trạng thái** khi mỗi trạng thái có một trạng thái cha và có thể có nhiều con.
- Dùng **đồ thị phiên bản có hướng (DAG)** nếu muốn tái sử dụng các phiên bản và biểu diễn quan hệ hợp nhất.
- Dùng **lịch sử thao tác có định danh** và một con trỏ tới phiên bản hiện tại để điều hướng rõ ràng.

Những thiết kế này vẫn có thể dùng stack cho một phần thuật toán, nhưng **cấu trúc chính của lịch sử** đã khác một stack LIFO đơn giản.

## 8. Snapshot với dữ liệu có thể thay đổi: bẫy tham chiếu

Ví dụ văn bản dùng `str` bất biến. Với các đối tượng **có thể thay đổi (mutable)** như `list` hoặc `dict`, việc push một **tham chiếu** không đồng nghĩa lưu một snapshot độc lập.

### Ví dụ sai

```python
state = {"items": ["A"]}
undo_stack = []

undo_stack.append(state)       # Chỉ lưu tham chiếu cùng đối tượng
state["items"].append("B")     # Sửa ngay đối tượng đó

print(undo_stack[-1]["items"]) # ['A', 'B'], không còn là ['A']
```

Nếu sau đó Undo bằng cách pop đối tượng từ `undo_stack`, ta không khôi phục được trạng thái cũ. Cả “bản đang dùng” và “bản đã lưu” đều trỏ tới **cùng một đối tượng đã bị sửa**.

### Lưu snapshot độc lập

Trong Python, có thể dùng `copy.deepcopy` cho các cấu trúc dữ liệu hỗ trợ sao chép sâu:

```python
from copy import deepcopy

state = {"items": ["A"]}
undo_stack = []

undo_stack.append(deepcopy(state))
state["items"].append("B")

state = undo_stack.pop()
print(state)  # {'items': ['A']}
```

Với hệ thống có cả Undo và Redo, phải bảo đảm **các trạng thái lưu trong hai stack không bị sửa ngoài ý muốn**. Cách dễ kiểm soát là chỉ cho phép chỉnh sửa qua một API duy nhất, và tạo snapshot độc lập ở thời điểm ghi lịch sử.

**Lưu ý:**

- `deepcopy` không phải giải pháp phù hợp cho mọi đối tượng. Tài nguyên bên ngoài như kết nối mạng, tệp đang mở, đối tượng khóa hoặc hệ thống có chia sẻ tham chiếu chủ đích có thể cần quy trình snapshot riêng.
- Nếu một trạng thái có kích thước `S`, việc sao chép có thể tốn **`O(S)` thời gian và bộ nhớ**.
- Trong ứng dụng phức tạp, có thể dùng **cấu trúc dữ liệu bất biến (immutable/persistent data structure)** hoặc lưu **diff** để chia sẻ phần không thay đổi giữa các phiên bản.
- Một snapshot bộ nhớ **không tự đảo ngược tác dụng bên ngoài** như ghi cơ sở dữ liệu hay gửi thông báo.

### Cẩn thận với khả năng sửa trạng thái ngoài API

Ngay cả khi lớp lịch sử có `undo()` và `redo()` đúng, nếu mã bên ngoài được phép sửa trực tiếp một đối tượng `current` có thể thay đổi, hệ thống không biết đã xảy ra chỉnh sửa mới để ghi lịch sử hoặc xóa nhánh Redo. Một thiết kế an toàn nên **đóng gói trạng thái**, cung cấp API thay đổi rõ ràng và không phát tham chiếu mutable có thể sửa tùy ý.

## 9. Lưu lệnh thay vì lưu cả trạng thái

Một cách khác để xây Undo/Redo là dùng **Command Pattern**. Mỗi lệnh có:

- `apply(state)`: tính trạng thái sau thao tác.
- `undo(state)`: phục hồi trạng thái trước thao tác.
- Dữ liệu cần thiết để thực hiện hai hướng trên, chẳng hạn vị trí và nội dung chèn.

Ta lưu **lệnh** trên hai stack thay vì lưu snapshot của toàn bộ tài liệu. Dưới đây là ví dụ chỉ hỗ trợ thao tác chèn vào chuỗi **bất biến**. Mục tiêu là minh họa điều phối lịch sử, không phải một trình soạn thảo hoàn chỉnh.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class InsertText:
    index: int
    text: str

    def apply(self, document):
        if not 0 <= self.index <= len(document):
            raise ValueError("vị trí chèn không hợp lệ")
        return (
            document[:self.index]
            + self.text
            + document[self.index:]
        )

    def undo(self, document):
        end = self.index + len(self.text)
        if document[self.index:end] != self.text:
            raise ValueError("trạng thái không khớp để hoàn tác")
        return document[:self.index] + document[end:]


class CommandHistory:
    def __init__(self, initial=""):
        self.document = initial
        self._undo = []
        self._redo = []

    def execute(self, command):
        next_document = command.apply(self.document)
        if next_document == self.document:
            return False

        self._undo.append(command)
        self.document = next_document
        self._redo.clear()
        return True

    def undo(self):
        if not self._undo:
            return False

        command = self._undo[-1]
        previous_document = command.undo(self.document)
        self._undo.pop()
        self._redo.append(command)
        self.document = previous_document
        return True

    def redo(self):
        if not self._redo:
            return False

        command = self._redo[-1]
        next_document = command.apply(self.document)
        self._redo.pop()
        self._undo.append(command)
        self.document = next_document
        return True


history = CommandHistory("")
history.execute(InsertText(0, "A"))
history.execute(InsertText(1, "B"))
history.execute(InsertText(2, "C"))
print(history.document)  # ABC

history.undo()
print(history.document)  # AB

history.redo()
print(history.document)  # ABC

history.undo()
history.execute(InsertText(2, "!"))
print(history.document)  # AB!
print(history.redo())    # False: đã rẽ nhánh
```

### Bất biến khi dùng lệnh

Sau khi một lệnh được áp dụng:

- Đỉnh Undo là lệnh có thể **đảo tác động gần nhất** trong ngữ cảnh hiện tại.
- Khi Undo, lệnh được chuyển sang Redo vì nó vẫn có thể **áp dụng lại** lên trạng thái vừa khôi phục.
- Khi Redo, lệnh quay lại Undo.
- Chỉnh sửa mới hủy Redo của tuyến lịch sử cũ.

Ví dụ dùng `InsertText` như một đối tượng **bất biến** nhờ `@dataclass(frozen=True)`. Điều đó tránh việc mã bên ngoài vô tình sửa vị trí/nội dung của lệnh sau khi lệnh đã được đưa vào lịch sử. Trong ví dụ, `apply`/`undo` tạo chuỗi mới rồi mới cập nhật cấu trúc lịch sử; nếu thao tác kiểm tra thất bại, lịch sử chưa bị dịch chuyển.

### Giới hạn của cách lưu lệnh

- **Không phải lệnh nào cũng đảo ngược được:** xóa dữ liệu cần lưu phần đã xóa; gửi email không thể thu hồi chỉ bằng một lệnh.
- **Phụ thuộc vào ngữ cảnh:** một lệnh “chèn tại chỉ số 5” có thể không còn có nghĩa nếu tài liệu bị chỉnh sửa trực tiếp bên ngoài lịch sử.
- **Undo không tự động là nghiệp vụ đảo của mọi tác dụng phụ:** ví dụ, “hoàn tiền” khác với “xóa dấu vết giao dịch”.
- **Chi phí thực thi lệnh** có thể lớn hơn thao tác stack `O(1)`; ví dụ chèn chuỗi vào giữa một chuỗi Python phải tạo chuỗi mới.
- **Một thao tác người dùng có thể gồm nhiều lệnh nội bộ**, vì vậy có thể cần gom chúng vào một bước Undo logic.

## 10. Nhóm thao tác và ranh giới của một bước Undo

Không phải mỗi phím gõ hoặc mỗi thay đổi nhỏ đều nên trở thành một bước Undo độc lập. Ví dụ, khi người dùng gõ một từ liên tục, họ có thể mong một lần Undo xóa cả từ thay vì chỉ một ký tự. Khi kéo một đối tượng trên màn hình, ứng dụng có thể tạo hàng trăm cập nhật tọa độ nhưng người dùng chỉ muốn Undo **một lần kéo**.

Có thể dùng một **lệnh tổng hợp (composite command)** chứa danh sách các thao tác nhỏ:

```text
Một bước kéo đối tượng:
    move(10, 10) → (11, 10)
    move(11, 10) → (12, 10)
    move(12, 10) → (20, 20)

Lệnh tổng hợp lưu:
    trạng thái trước (10, 10)
    trạng thái sau   (20, 20)

Một Undo: quay về (10, 10)
Một Redo: đi tới (20, 20)
```

Nếu lưu các lệnh con và khi Undo phải đảo từng lệnh, thứ tự đảo là **ngược với thứ tự thực hiện**:

```text
Thực hiện:    A → B → C
Hoàn tác:     undo(C) → undo(B) → undo(A)
Làm lại:      A → B → C
```

Điều này lại thể hiện nguyên tắc LIFO. Tuy nhiên, mô hình một stack chỉ giải quyết **thứ tự lấy lệnh**; việc xác định **ranh giới một thao tác người dùng**, **thành công toàn bộ hay thất bại toàn bộ**, và **tác dụng phụ** cần được thiết kế riêng.

Với các lệnh có thể thất bại giữa chừng, đừng ghi nhận một bước Undo đã hoàn tất nếu trạng thái thực tế mới chỉ cập nhật một phần. Trong hệ thống yêu cầu tính nguyên tử, cần cơ chế giao dịch hoặc rollback phù hợp trước khi thêm một bước lịch sử.

## 11. Giới hạn bộ nhớ và độ dài lịch sử

Lịch sử Undo không thể tăng vô hạn trong mọi ứng dụng. Nếu lưu snapshot của tài liệu lớn, mỗi bước có thể giữ rất nhiều dữ liệu.

Gọi:

- `k`: số bước lịch sử đang giữ.
- `S`: kích thước một snapshot, giả định tương đương nhau.
- `r`: số trạng thái trong `redo_stack`.
- `L`: độ dài văn bản hiện tại khi dùng chuỗi.

### Chi phí với snapshot

Nếu mỗi snapshot là bản sao độc lập kích thước `S`, giữ `k` snapshot có thể cần **`O(kS)` bộ nhớ**. Tạo một snapshot mới có thể tốn **`O(S)` thời gian**. Với các chuỗi Python bất biến như trong `TextHistory`, việc **đưa tham chiếu chuỗi đã tồn tại vào danh sách** thường `O(1)` trung bình phân bổ; nhưng quá trình **tạo chuỗi phiên bản mới** có thể tốn `O(L)` thời gian và bộ nhớ.

Bảng sau phân biệt chi phí thao tác cấu trúc với chi phí dữ liệu:

| Hoạt động | Chi phí về cấu trúc lịch sử | Chi phí có thể phát sinh thêm |
|---|---|---|
| Push snapshot đã tồn tại | `O(1)` amortized | Bộ nhớ của snapshot đã tạo |
| Pop snapshot | `O(1)` amortized | Chi phí hủy/giải phóng đối tượng nếu có |
| Tạo bản sao sâu của trạng thái cỡ `S` | Không chỉ là thao tác stack | Có thể `O(S)` thời gian và bộ nhớ |
| So sánh hai chuỗi dài `L` xem có thay đổi không | Không chỉ là thao tác stack | Có thể `O(L)` thời gian |
| Xóa `redo_stack` có `r` mục bằng `list.clear()` | Làm rỗng lịch sử | Có thể `O(r)` để bỏ các tham chiếu |
| Khôi phục snapshot chuỗi bất biến bằng gán tham chiếu | `O(1)` | Việc cập nhật giao diện/hiển thị có thể tốn thêm |

Nếu giữ cả Undo và Redo, bộ nhớ lưu lịch sử có thể tỷ lệ với **tổng số và kích thước snapshot trong hai stack**, ngoài trạng thái hiện tại. Không nên dùng độ phức tạp `O(1)` của `push` để kết luận toàn bộ thao tác chỉnh sửa hoặc hoàn tác luôn `O(1)`.

### Các chính sách giới hạn lịch sử

1. **Giữ tối đa `k` bước:** khi thêm lịch sử mới vượt ngưỡng, bỏ bước **cũ nhất**, không phải bước mới nhất.
2. **Giới hạn theo dung lượng bộ nhớ:** tính tổng kích thước snapshot/diff, loại dần lịch sử cũ khi vượt ngân sách.
3. **Gộp các chỉnh sửa liên tiếp:** nhiều thao tác nhỏ được nhóm thành một bước Undo.
4. **Dùng delta, diff hoặc command:** lưu phần thay đổi thay vì sao chép toàn bộ tài liệu.
5. **Dùng checkpoint định kỳ:** lưu snapshot thưa hơn và chuỗi thao tác ở giữa, chấp nhận chi phí khôi phục cao hơn.

Đặc biệt, **stack thuần LIFO không xóa nhanh phần tử ở đáy**. Nếu cần bỏ **bước lịch sử cũ nhất** mỗi khi đầy, việc gọi `pop()` sẽ loại nhầm bước mới nhất. Dùng mảng có giới hạn và dịch phần tử có thể tốn `O(k)` cho lần loại cũ nhất; dùng cấu trúc hỗ trợ hai đầu như `deque` hoặc bộ đệm vòng có thể phục vụ chính sách giữ `k` bước tốt hơn.

Nếu dùng `collections.deque(maxlen=k)`, thao tác thêm tại cuối có thể tự loại phần tử đầu khi đầy. Nó vẫn có thể phục vụ Undo bằng cách pop cuối, nhưng **không phải chỉ một stack thuần túy** vì hệ thống lịch sử còn thực hiện loại bỏ phần tử ở phía đáy.

## 12. Nhiều người dùng, lưu bền và tác dụng phụ: giới hạn ngoài LIFO

Một stack cục bộ thường đủ cho chỉnh sửa tuần tự trên một thiết bị. Nhưng nhiều loại ứng dụng cần hơn thế.

### 12.1. Nhiều người cùng chỉnh sửa

Giả sử người A thêm đoạn văn, người B sửa cùng đoạn ngay sau đó. Nếu A nhấn Undo, không thể luôn “lấy snapshot trước thao tác của A” rồi ghi đè toàn bộ tài liệu, vì điều đó có thể làm mất thay đổi hợp lệ của B.

Khi có chỉnh sửa đồng thời, hệ thống cần xác định **ai sở hữu thao tác**, **phạm vi ảnh hưởng** và **cách xử lý xung đột**. Các cơ chế cộng tác như biến đổi thao tác (OT) hoặc kiểu dữ liệu nhân bản không xung đột (CRDT) có thể hỗ trợ mô hình chỉnh sửa cộng tác, nhưng cách Undo theo người dùng vẫn đòi hỏi quy tắc rõ ràng. Một stack LIFO toàn cục không giải quyết đủ vấn đề này.

### 12.2. Khôi phục sau khi đóng ứng dụng

Stack lưu trong RAM sẽ biến mất khi tiến trình kết thúc, trừ khi ứng dụng có cơ chế **lưu bền**. Một hệ thống Undo/Redo cần tồn tại qua lần mở ứng dụng có thể lưu snapshot, nhật ký thao tác hoặc định dạng phiên bản xuống đĩa. Khi khôi phục, phải kiểm tra tính toàn vẹn, phiên bản dữ liệu và trạng thái cập nhật chưa hoàn tất.

**Event sourcing** lưu một nhật ký sự kiện để tái dựng trạng thái; nhật ký thường là dãy sự kiện append-only, không đồng nghĩa với stack Undo. “Hoàn tác” trong hệ thống như vậy có thể được biểu diễn bằng **sự kiện bù trừ**, không nhất thiết xóa sự kiện cũ.

### 12.3. Tác dụng phụ không thể xóa đơn giản

Ví dụ, khi một thao tác “gửi email” đã xảy ra, Undo trong giao diện có thể xóa email khỏi hàng đợi **nếu chưa gửi**, nhưng sau khi email đã tới người nhận thì không thể khôi phục thế giới như trước chỉ bằng `pop` một snapshot.

Tương tự, một lệnh đặt hàng đã gửi tới dịch vụ ngoài có thể cần một yêu cầu hủy riêng, và việc hủy có thể thất bại. Cần phân biệt:

- **Đảo trạng thái nội bộ:** quay về bản dữ liệu cũ.
- **Bù trừ nghiệp vụ:** tạo thao tác mới để giảm tác động của thao tác trước.
- **Rollback nguyên tử:** chỉ có thể bảo đảm trong phạm vi hệ thống có cơ chế giao dịch phù hợp.

Stack quản lý thứ tự công việc; nó không bảo đảm mọi tác động đều đảo ngược được.

### 12.4. Truy cập đồng thời

Mã mẫu ở trên giả định **một luồng điều khiển cập nhật lịch sử tại một thời điểm**. Nếu nhiều luồng cùng sửa `current` và các stack, việc kiểm tra `can_undo()` rồi gọi `undo()` có thể bị luồng khác xen vào. Hệ thống cần đồng bộ hoặc thiết kế trạng thái bất biến với cơ chế cập nhật nguyên tử.

## 13. Chọn cấu trúc lịch sử theo yêu cầu

| Yêu cầu | Cấu trúc gợi ý | Điểm cần lưu ý |
|---|---|---|
| Chỉ Undo các thay đổi gần nhất | Một stack quá khứ + trạng thái hiện tại | Đơn giản; không Redo đầy đủ |
| Undo và Redo theo một dòng thời gian | Hai stack + trạng thái hiện tại | Chỉnh sửa mới làm rỗng Redo |
| Undo/Redo và di chuyển bằng con trỏ lịch sử | Mảng phiên bản + cursor | Cần xử lý cắt nhánh khi edit mới |
| Lịch sử có nhiều nhánh | Cây hoặc DAG phiên bản | Lựa chọn nhánh cần rõ ràng |
| Giới hạn `k` trạng thái, bỏ cũ nhất | Deque/bộ đệm vòng hoặc cơ chế tỉa lịch sử | Pop đỉnh một stack không xóa được đáy nhanh |
| Tài liệu lớn, thay đổi nhỏ | Command hoặc diff | Cần đủ dữ liệu đảo thao tác, có thể có xung đột |
| Chỉnh sửa cộng tác | Lịch sử thao tác có ngữ cảnh/cơ chế hợp nhất | Một stack toàn cục không đủ |
| Khôi phục qua lần khởi động mới | Nhật ký/snapshot lưu bền | Cần bảo toàn dữ liệu và xử lý phục hồi |

Không có cấu trúc “tốt nhất” cho mọi yêu cầu. Hãy bắt đầu từ **hợp đồng nghiệp vụ**: cần Undo bao xa, có Redo không, có giữ nhánh không, có nhiều người chỉnh sửa không, có giới hạn bộ nhớ không, và thao tác có thể đảo được hay không.

## 14. Những lỗi thường gặp

1. **Chỉ lưu trạng thái mới sau chỉnh sửa mà không lưu trạng thái cũ.** Khi Undo, không có dữ liệu để quay về phiên bản trước.
2. **Quên push `current` vào Redo trước khi Undo.** Trạng thái vừa rời khỏi không còn được giữ, nên Redo sai hoặc không thực hiện được.
3. **Quên xóa Redo sau chỉnh sửa mới.** Người dùng có thể đi vào nhánh lịch sử đã bị từ bỏ, gây hành vi bất ngờ.
4. **Ghi lịch sử cả khi nội dung không thay đổi.** Tạo ra bước Undo rỗng, làm người dùng cần nhấn nhiều lần để thấy thay đổi thật.
5. **Lưu tham chiếu tới đối tượng mutable rồi sửa trực tiếp.** Snapshot cũ thay đổi theo trạng thái hiện tại, làm Undo không đúng.
6. **Cho mã khác sửa trực tiếp trạng thái mà không ghi lịch sử.** Nội dung và các stack không còn đồng bộ.
7. **Tưởng `pop()` là xóa bước cũ nhất.** Stack LIFO xóa bước **mới nhất**; muốn giới hạn lịch sử theo tuổi cần cơ chế xóa ở đáy.
8. **Đồng nhất Undo với đảo mọi tác dụng phụ.** Không phải email hay giao dịch bên ngoài đều hoàn tác được một cách nguyên tử.
9. **Chỉ đếm thao tác `O(1)` của stack rồi bỏ qua chi phí dữ liệu.** Sao chép snapshot, dựng diff và vẽ lại giao diện có thể đắt hơn nhiều.
10. **Không quy định thao tác thất bại.** Khi `undo_stack` hoặc `redo_stack` rỗng, cần trả trạng thái rõ ràng và giữ nguyên dữ liệu.
11. **Không gom nhóm hành động nhiều bước.** Một thao tác người dùng có thể bị chia thành quá nhiều lần Undo hoặc bị ghi nhận khi chưa hoàn tất.
12. **Giả định một lịch sử tuyến tính phục vụ tốt nhiều người hoặc nhiều nhánh.** Cần mô hình phiên bản và quy tắc xung đột thích hợp.

## 15. Kiểm thử hành vi biên

Có thể chạy các kiểm thử sau với lớp `TextHistory` trong phần 5:

```python
h = TextHistory("")
assert h.undo() is False
assert h.redo() is False
assert h.current == ""

assert h.edit("A") is True
assert h.edit("A") is False  # Không thêm bước vô nghĩa
assert h.undo() is True
assert h.current == ""
assert h.undo() is False
assert h.redo() is True
assert h.current == "A"

h.edit("AB")
h.edit("ABC")
assert h.undo() is True
assert h.current == "AB"
assert h.redo() is True
assert h.current == "ABC"

assert h.undo() is True
assert h.current == "AB"
assert h.edit("AB!") is True
assert h.redo() is False  # Nhánh ABC không còn làm lại được
assert h.current == "AB!"
```

Ngoài ra, nên kiểm thử: nhiều lần Undo liên tiếp; nhiều lần Redo liên tiếp; tài liệu rỗng; trạng thái rất lớn; đối tượng mutable; giới hạn số bước; và tình huống cấp phát bộ nhớ thất bại nếu ứng dụng yêu cầu chịu lỗi.

## 16. Bài tập tự luyện có đáp án

### Bài 1. Một stack và Undo

Bắt đầu từ `current = "X"` và `undo_stack = []`. Thực hiện `edit("XY")`, `edit("XYZ")` rồi `undo()`. Hãy xác định `current` và `undo_stack`.

**Đáp án:** Sau hai lần edit, `undo_stack = ["X", "XY"]`, `current = "XYZ"`. Undo lấy đỉnh `"XY"`, nên `current = "XY"` và `undo_stack = ["X"]`.

### Bài 2. Vì sao Redo không xác định?

Sau một lần Undo, `current = "AB"` và `undo_stack = ["", "A"]`. Có thể suy ra trạng thái cần Redo là `"ABC"` không?

**Đáp án:** Không. Trạng thái trước Undo có thể là `"ABC"`, `"AB!"` hoặc nhiều nội dung khác. Nếu trạng thái vừa bị Undo không được giữ ở nơi khác thì một stack quá khứ không đủ thông tin để Redo.

### Bài 3. Hai lần Undo, một lần Redo

Giả sử trạng thái ban đầu là `""`, thực hiện `edit("A")`, `edit("AB")`, `edit("ABC")`, sau đó `undo()` hai lần và `redo()` một lần. Tình trạng cuối cùng của hai stack là gì?

**Đáp án:** `current = "AB"`, `undo_stack = ["", "A"]`, `redo_stack = ["ABC"]`. Lần Redo tiếp theo có thể khôi phục `"ABC"`.

### Bài 4. Chỉnh sửa mới sau Undo

Từ `current = "ABC"`, Undo về `"AB"` rồi edit thành `"AB!"`. Vì sao Redo không nên quay lại `"ABC"` trong mô hình hai stack tuyến tính?

**Đáp án:** Lần edit mới tạo nhánh lịch sử khác từ `"AB"`. Quy tắc tuyến tính xóa Redo để không vô tình trộn hai nhánh. Muốn giữ cả hai nhánh cần cấu trúc phiên bản dạng cây hoặc DAG.

### Bài 5. Snapshot và aliasing

Một đối tượng `state = {"nums": [1]}` được push vào Undo rồi thực hiện `state["nums"].append(2)`. Tại sao Undo có thể không khôi phục được `[1]`?

**Đáp án:** Stack chỉ giữ tham chiếu tới cùng đối tượng. Thao tác append sửa cả đối tượng mà lịch sử đang trỏ đến. Cần snapshot độc lập, cấu trúc bất biến hoặc cơ chế ghi thay đổi phù hợp.

### Bài 6. Giới hạn lịch sử

Một ứng dụng chỉ giữ tối đa 20 bước Undo. Khi thêm bước thứ 21, bước nào nên bị loại nếu muốn giữ 20 bước **gần nhất**? Vì sao `pop()` của stack không phù hợp?

**Đáp án:** Loại **bước cũ nhất** ở đáy lịch sử. `pop()` loại bước mới nhất ở đỉnh, trái với mục tiêu. Có thể dùng deque hoặc bộ đệm có cơ chế tỉa phía đầu.

### Bài 7. Phân tích chi phí

Giả sử lưu `k` snapshot độc lập, mỗi snapshot chiếm `S` byte. Bộ nhớ lịch sử là bao nhiêu? Nếu chỉ lưu tham chiếu tới chuỗi Python bất biến, thao tác push có còn cần sao chép `S` byte không?

**Đáp án:** Nếu snapshot độc lập cùng kích thước thì chi phí là `O(kS)`. Push một tham chiếu tới chuỗi bất biến đã tồn tại thường `O(1)` trung bình phân bổ, nhưng **việc tạo phiên bản chuỗi mới** vẫn có thể cần `O(S)` thời gian và bộ nhớ.

### Bài 8. Hoàn tác thao tác bên ngoài

Một ứng dụng có nút Undo cho hành động “gửi thông báo đến hệ thống khác”. Có thể chỉ pop snapshot nội bộ để chắc chắn thông báo không còn tác động hay không?

**Đáp án:** Không. Snapshot chỉ khôi phục dữ liệu nội bộ; thông báo có thể đã được bên ngoài nhận hoặc xử lý. Cần thiết kế hành động bù trừ/thu hồi nếu khả thi, cùng trạng thái lỗi và quy tắc nghiệp vụ thích hợp.

## 17. Tổng kết

**Một ngăn xếp** mô tả rất tốt quá khứ của một chuỗi chỉnh sửa: lưu trạng thái trước khi edit, sau đó `pop` để quay về trạng thái gần nhất. Đây là mô hình Undo tối thiểu, đơn giản và trực tiếp dựa trên **LIFO**.

Tuy nhiên, Undo làm mất đường tiến về trạng thái vừa rời khỏi nếu không có nơi lưu riêng. **Hai stack** — một cho quá khứ và một cho tương lai vừa bị hoàn tác — giúp hỗ trợ **Undo/Redo tuyến tính**; chỉnh sửa mới phải xóa nhánh Redo cũ. Nếu cần giữ nhiều nhánh, xóa lịch sử cũ nhất, cộng tác đa người dùng hoặc khôi phục xuyên phiên, phải xem xét **cây/DAG phiên bản, deque, command/diff, nhật ký lưu bền hoặc cơ chế đồng bộ**.

Điểm quyết định không chỉ là chọn số lượng stack mà là mô tả rõ **thông tin mỗi phần tử lưu trữ, bất biến sau thao tác, điều kiện rỗng, chính sách rẽ nhánh, khả năng đảo ngược và chi phí bộ nhớ**. Khi những điều kiện này được xác định, ta mới có thể xây dựng lịch sử hoàn tác đáng tin cậy và phù hợp với từng ứng dụng.
