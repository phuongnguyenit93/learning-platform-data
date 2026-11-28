# Ứng dụng kiểm tra dấu ngoặc và lưu trạng thái xử lý

## 1. Vì sao ngăn xếp phù hợp với các bài toán lồng nhau?

**Ngăn xếp (stack)** là kiểu dữ liệu trừu tượng hoạt động theo nguyên tắc **LIFO — Last In, First Out**: phần tử được đưa vào sau cùng sẽ được lấy ra trước tiên. Các thao tác cơ bản là `push(x)` (thêm phần tử vào đỉnh), `pop()` (lấy và xóa phần tử đỉnh), `peek()` (xem đỉnh mà không xóa) và `is_empty()` (kiểm tra rỗng).

Trong chương **Ngăn xếp** của học phần **Cấu trúc dữ liệu**, hai ứng dụng quan trọng là:

1. **Kiểm tra dấu ngoặc:** một dấu đóng phải khớp với **dấu mở tương ứng gần nhất chưa được đóng**.
2. **Lưu trạng thái xử lý:** khi tạm chuyển sang một công việc hoặc trạng thái mới, chương trình có thể giữ trạng thái trước đó để **quay về, tiếp tục hoặc khôi phục**.

Hai tình huống đều có cấu trúc “vào sau, ra trước”. Khi xử lý biểu thức `{[()]}`, dấu `(` được mở sau cùng và phải đóng trước; khi đang ở bước xử lý lồng nhau, bước gần nhất cũng thường cần hoàn tất hoặc khôi phục trước bước bên ngoài.

Stack giúp biểu diễn chính xác thứ tự này. Mục tiêu của bài là hiểu **bất biến**, xây dựng thuật toán đúng, xử lý các trường hợp lỗi và phân tích **thời gian, bộ nhớ** để biết khi nào nên dùng stack trong ứng dụng thực tế.

## 2. Bài toán kiểm tra dấu ngoặc cân bằng

Cho chuỗi chỉ xét ba cặp dấu:

| Dấu mở | Dấu đóng |
|---|---|
| `(` | `)` |
| `[` | `]` |
| `{` | `}` |

Một chuỗi được coi là **cân bằng** nếu mọi dấu mở có đúng một dấu đóng cùng loại và các cặp dấu **lồng nhau hợp lệ**, tức không có hai cặp dấu đan chéo.

Ví dụ:

| Chuỗi | Hợp lệ? | Giải thích |
|---|---|---|
| `""` | Có | Không có dấu nào cần ghép |
| `"()"` | Có | Một cặp khớp nhau |
| `"({[]})"` | Có | Các cặp lồng nhau đúng thứ tự |
| `"a*(b+[c])"` | Có | Bỏ qua ký tự không phải dấu ngoặc |
| `"([)]"` | Không | `)` gặp dấu mở `[` ở đỉnh, sai loại |
| `"(()"` | Không | Còn một dấu `(` chưa đóng |
| `"())"` | Không | Dấu `)` cuối không có dấu mở tương ứng |
| `")("` | Không | Dấu đóng xuất hiện khi stack rỗng |

**Đếm số dấu mở và dấu đóng bằng nhau chưa đủ.** Chuỗi `"([)]"` có số lượng dấu mở và đóng theo từng loại bằng nhau nhưng vẫn sai, vì hai cặp dấu đan chéo. Ta cần nhớ **thứ tự** các dấu mở chưa ghép — chính là nhiệm vụ của stack.

### Bất biến cốt lõi

Sau khi xử lý xong mỗi ký tự từ trái sang phải, giả sử chưa phát hiện lỗi, stack phải chứa **chính xác các dấu mở đã gặp nhưng chưa được đóng**, theo thứ tự xuất hiện; **đỉnh stack** là dấu mở gần nhất đang chờ ghép.

Sơ đồ với chuỗi `"({[]})"` (bên phải biểu thị đỉnh):

```text
Đọc '('   → push '('  → [(]
Đọc '{'   → push '{'  → [(, {]
Đọc '['   → push '['  → [(, {, []
Đọc ']'   → pop '['   → [(, {]
Đọc '}'   → pop '{'   → [(]
Đọc ')'   → pop '('   → []

Stack rỗng sau khi duyệt hết → các cặp dấu đã khớp.
```

Khi gặp dấu đóng, chương trình phải kiểm tra dấu mở ở đỉnh. Nếu đỉnh sai loại hoặc stack rỗng, không có cách ghép hợp lệ theo nguyên tắc lồng nhau.

## 3. Thuật toán kiểm tra dấu ngoặc bằng stack

### Mã giả

```text
BALANCED(text):
    stack = stack rỗng

    for mỗi ký tự ch trong text:
        if ch là dấu mở:
            push(ch)

        else if ch là dấu đóng:
            if stack rỗng:
                return False

            if peek() không phải dấu mở ứng với ch:
                return False

            pop()  # Loại dấu mở vừa khớp

    return stack rỗng
```

Ta **kiểm tra loại dấu trước khi `pop`**. Điều đó giúp thuật toán dễ giải thích: chỉ xóa một dấu mở khi nó thực sự khớp với dấu đóng hiện tại.

### Ví dụ Python có thể chạy độc lập

Dưới đây dùng `list` của Python làm stack. `append` tương đương `push`, `pop` lấy cuối danh sách, và `stack[-1]` tương đương `peek`:

```python
def balanced_brackets(text):
    matching = {")": "(", "]": "[", "}": "{"}
    openings = set(matching.values())
    stack = []

    for ch in text:
        if ch in openings:
            stack.append(ch)
        elif ch in matching:
            if not stack:
                return False
            if stack[-1] != matching[ch]:
                return False
            stack.pop()

    return not stack


samples = [
    "", "()", "({[]})", "a*(b+[c])",
    "([)]", "(()", "())", ")("
]

for sample in samples:
    print(repr(sample), balanced_brackets(sample))
```

Kết quả mong đợi:

```text
'' True
'()' True
'({[]})' True
'a*(b+[c])' True
'([)]' False
'(()' False
'())' False
')(' False
```

Hàm trả `True` khi mọi dấu đóng đều khớp **và** không còn dấu mở chưa khép. Nếu bỏ kiểm tra `return not stack` ở cuối, chuỗi `"((("` sẽ bị đánh giá sai thành hợp lệ vì không có dấu đóng nào gây lỗi trong vòng lặp.

### Truy vết một chuỗi sai

Với chuỗi `"([)]"`:

| Vị trí (từ 0) | Ký tự | Hành động | Stack sau bước |
|---:|:---:|---|---|
| 0 | `(` | `push("(")` | `["("]` |
| 1 | `[` | `push("[")` | `["(", "["]` |
| 2 | `)` | Đỉnh là `[`, không khớp `(` | Báo sai, dừng |

Dù dấu `(` xuất hiện trong stack, ta **không được bỏ qua `[`** để lấy `(`, vì khi đó các cặp ngoặc sẽ đan chéo. Chỉ phần tử đỉnh được phép ghép với dấu đóng tiếp theo.

## 4. Trả thông tin lỗi cụ thể: vị trí và loại dấu

Trong trình soạn thảo mã hoặc công cụ kiểm tra biểu thức, câu trả lời `True`/`False` thường chưa đủ. Người dùng cần biết:

- Dấu đóng nào không có dấu mở.
- Dấu đóng nào sai loại so với dấu mở gần nhất.
- Dấu mở nào còn thiếu dấu đóng khi hết chuỗi.

Để báo vị trí, lưu vào stack **cặp `(dấu_mở, vị_trí)`** thay vì chỉ lưu ký tự. Các vị trí được tính từ `0` theo chỉ số ký tự Python.

```python
def check_brackets(text):
    matching = {")": "(", "]": "[", "}": "{"}
    openings = set(matching.values())
    stack = []  # Mỗi phần tử: (dấu mở, chỉ số vị trí)

    for index, ch in enumerate(text):
        if ch in openings:
            stack.append((ch, index))
            continue

        if ch not in matching:
            continue

        if not stack:
            return (
                False,
                f"Dấu đóng {ch!r} tại vị trí {index} không có dấu mở"
            )

        top_ch, top_index = stack[-1]
        if top_ch != matching[ch]:
            return (
                False,
                f"Dấu đóng {ch!r} tại vị trí {index} "
                f"không khớp dấu mở {top_ch!r} tại vị trí {top_index}"
            )

        stack.pop()

    if stack:
        top_ch, top_index = stack[-1]
        return (
            False,
            f"Dấu mở {top_ch!r} tại vị trí {top_index} chưa được đóng"
        )

    return (True, None)


for sample in ["{[()]}", "([)]", "())", "(()"]:
    print(sample, "=>", check_brackets(sample))
```

Kết quả (các vị trí bắt đầu từ 0):

```text
{[()]} => (True, None)
([)] => (False, "Dấu đóng ')' tại vị trí 2 không khớp dấu mở '[' tại vị trí 1")
()) => (False, "Dấu đóng ')' tại vị trí 2 không có dấu mở")
(() => (False, "Dấu mở '(' tại vị trí 0 chưa được đóng")
```

Trong trường hợp còn nhiều dấu mở chưa được đóng, ví dụ `"([{"`, phiên bản này báo **dấu ở đỉnh** (dấu mở mới nhất chưa khớp). Một công cụ chỉnh sửa có thể muốn báo **tất cả** các dấu chưa khớp; khi đó duyệt hoặc sao chép các phần tử còn lại trong stack để tạo danh sách lỗi.

**Phạm vi bài toán:** hàm minh họa xem **mọi** ký tự `(`, `)`, `[`, `]`, `{`, `}` trong chuỗi đều là dấu ngoặc cần kiểm tra. Trong mã nguồn thực tế, dấu ngoặc bên trong chuỗi ký tự hoặc chú thích thường không có cùng ý nghĩa cú pháp, ví dụ `print(")")`. Công cụ phân tích mã cần **tách token và nhận biết ngữ cảnh chuỗi/chú thích (lexical analysis)** trước khi áp dụng quy tắc ghép dấu ngoặc cho các token thích hợp. Thuật toán ở đây giải bài toán dấu ngoặc đơn giản, chưa phải bộ phân tích cú pháp đầy đủ.

## 5. Vì sao thuật toán đúng và hiệu quả?

### Lập luận tính đúng đắn qua bất biến

Xét tiền tố các ký tự đã duyệt và giả sử thuật toán chưa trả `False`:

1. **Ban đầu**, stack rỗng; chưa có dấu mở chưa khớp nên bất biến đúng.
2. **Gặp dấu mở**, thêm nó vào đỉnh; đó chính là dấu mở gần nhất chưa có dấu đóng.
3. **Gặp dấu đóng**, dấu mở hợp lệ duy nhất có thể ghép là đỉnh stack. Nếu đỉnh sai loại hoặc rỗng, chuỗi không hợp lệ. Nếu khớp, `pop` xóa đúng cặp vừa hoàn thành; các dấu mở bên ngoài vẫn giữ nguyên thứ tự.
4. **Gặp ký tự khác**, không ảnh hưởng tới các dấu ngoặc nên bất biến giữ nguyên.

Sau khi quét hết, nếu stack rỗng thì mọi dấu mở đều đã được ghép; nếu không, còn dấu mở thiếu dấu đóng. Vì vậy thuật toán trả đúng tính cân bằng của chuỗi theo phạm vi đã định nghĩa.

### Độ phức tạp

Gọi `n` là số ký tự trong chuỗi và `d` là **độ sâu lồng ngoặc lớn nhất chưa khớp tại một thời điểm**:

| Phép đo | Chi phí | Lý do |
|---|---|---|
| Thời gian | **`O(n)`** | Duyệt một lần; mỗi dấu mở push tối đa một lần, mỗi dấu đóng pop tối đa một lần |
| Bộ nhớ phụ | **`O(d)`**, tối đa `O(n)` | Stack chỉ lưu các dấu mở chưa khớp |
| Kiểm tra `peek`/`pop` | **`O(1)`** trung bình | Thao tác ở cuối mảng động |
| Bảng ánh xạ `matching` | **`O(1)`** | Chỉ có ba cặp dấu cố định |

Với `"((((...))))"`, độ sâu `d` có thể tỉ lệ với `n`, nên trường hợp xấu nhất dùng `O(n)` bộ nhớ. Nếu mỗi nhóm ngoặc đóng ngay sau khi mở, ví dụ `"()[]{}"`, stack tại một thời điểm chỉ chứa nhiều nhất một dấu, nên bộ nhớ phụ `O(1)` cho chuỗi này.

Không thể giải đầy đủ bài toán nhiều loại ngoặc lồng nhau chỉ bằng **một biến đếm tổng**: ngoài độ sâu, ta cần nhớ loại và thứ tự của các dấu mở.

## 6. Từ dấu ngoặc đến khái niệm lưu trạng thái xử lý

Việc kiểm tra ngoặc thực chất là một ví dụ rất gọn của **lưu trạng thái đang chờ**. Khi gặp `(`, bộ kiểm tra ghi nhớ rằng một phạm vi đã bắt đầu. Nếu gặp `[` bên trong, nó lưu thêm phạm vi mới. Khi `]` xuất hiện, phạm vi trong cùng được kết thúc trước; sau đó mới tiếp tục phạm vi bao ngoài.

Mẫu hành vi tổng quát:

```text
Bắt đầu công việc A
    Lưu trạng thái A
    Bắt đầu công việc B
        Lưu trạng thái B
        Hoàn thành B → khôi phục / tiếp tục từ trạng thái B
    Hoàn thành A → khôi phục / tiếp tục từ trạng thái A
```

Một phần tử stack có thể lưu nhiều hơn một ký tự:

- **Dấu mốc** xác định phạm vi hiện tại, ví dụ loại ngoặc hoặc ID thao tác.
- **Vị trí tiếp tục** sau khi hoàn thành công việc con, ví dụ chỉ số đang duyệt.
- **Dữ liệu trung gian** cần dùng khi quay lại, ví dụ giá trị đã tính hoặc tham số.
- **Ảnh chụp trạng thái** để khôi phục khi hoàn tác hay quay lui.

Mỗi lần `push` là một quyết định “hãy nhớ trạng thái này”; mỗi lần `pop` là “lấy lại trạng thái gần nhất”. **Nội dung một frame** phụ thuộc bài toán, nhưng quy tắc LIFO không thay đổi.

## 7. Ứng dụng lưu trạng thái: Undo và Redo

Trong trình soạn thảo, người dùng thường muốn **Undo** (hoàn tác thao tác gần nhất) và **Redo** (thực hiện lại thao tác vừa hoàn tác). Một mô hình dễ hiểu là dùng **hai stack lịch sử**:

- `undo_stack` giữ các trạng thái **trước** những chỉnh sửa còn có thể hoàn tác.
- `redo_stack` giữ các trạng thái vừa được hoàn tác để có thể khôi phục theo chiều ngược lại.
- `current` là trạng thái đang hiển thị.

Với thao tác **chỉnh sửa mới**:

1. Đưa `current` cũ vào `undo_stack`.
2. Cập nhật `current` sang trạng thái mới.
3. **Xóa `redo_stack`**, vì người dùng đã rẽ sang một nhánh lịch sử mới.

Với **Undo**: đưa `current` vào `redo_stack`, rồi lấy đỉnh `undo_stack` làm `current` mới.

Với **Redo**: đưa `current` vào `undo_stack`, rồi lấy đỉnh `redo_stack` làm `current` mới.

### Cài đặt Python dùng ảnh chụp văn bản

Ví dụ dùng `str` bất biến nên các phiên bản văn bản đã lưu sẽ không bị sửa tại chỗ:

```python
class TextHistory:
    def __init__(self, initial=""):
        self.current = initial
        self.undo_stack = []
        self.redo_stack = []

    def edit(self, new_text):
        if new_text == self.current:
            return False  # Không có thay đổi, giữ nguyên lịch sử

        self.undo_stack.append(self.current)
        self.current = new_text
        self.redo_stack.clear()
        return True

    def undo(self):
        if not self.undo_stack:
            return False

        self.redo_stack.append(self.current)
        self.current = self.undo_stack.pop()
        return True

    def redo(self):
        if not self.redo_stack:
            return False

        self.undo_stack.append(self.current)
        self.current = self.redo_stack.pop()
        return True


history = TextHistory("A")
history.edit("AB")
history.edit("ABC")
history.undo()
print(history.current)  # AB
history.undo()
print(history.current)  # A
history.redo()
print(history.current)  # AB
history.edit("AB!")
print(history.current)           # AB!
print(history.redo())            # False: nhánh redo đã bị xóa
```

Trong mô hình này, `undo()` và `redo()` khi stack lịch sử rỗng trả `False`, không làm thay đổi trạng thái. Đây là **chính sách xử lý underflow** phù hợp vì “không còn bước để hoàn tác” là tình huống bình thường ở giao diện người dùng.

### Theo dõi hai stack

Quy ước bên phải là đỉnh của mỗi stack:

| Thao tác | `current` | `undo_stack` | `redo_stack` |
|---|---|---|---|
| Khởi tạo | `A` | `[]` | `[]` |
| `edit("AB")` | `AB` | `[A]` | `[]` |
| `edit("ABC")` | `ABC` | `[A, AB]` | `[]` |
| `undo()` | `AB` | `[A]` | `[ABC]` |
| `undo()` | `A` | `[]` | `[ABC, AB]` |
| `redo()` | `AB` | `[A]` | `[ABC]` |
| `edit("AB!")` | `AB!` | `[A, AB]` | `[]` |

Tại dòng cuối, `redo_stack` bị xóa vì chuỗi trạng thái đi tiếp từ `AB` sang `AB!`. Nếu vẫn cho Redo quay lại `ABC`, lịch sử sẽ không còn phản ánh một chuỗi thao tác tuyến tính có thể giải thích rõ cho người dùng.

### Bất biến và chi phí bộ nhớ của lịch sử

Sau mỗi thao tác thành công, đỉnh `undo_stack` là trạng thái có thể khôi phục khi Undo tiếp theo; đỉnh `redo_stack` là trạng thái có thể khôi phục khi Redo tiếp theo. Hoàn tác và làm lại chỉ dịch chuyển các trạng thái giữa hai stack mà **không sửa nội dung của snapshot**.

- Các thao tác thêm/lấy phần tử ở cuối mảng động có **`O(1)` trung bình phân bổ** nếu coi việc dịch chuyển tham chiếu là đơn vị chi phí.
- Bản `edit` có phép so sánh hai chuỗi `new_text == current`, nên chi phí kiểm tra có thể tới **`O(L)`** với độ dài chuỗi `L`. Việc **tạo nội dung văn bản mới** cũng có thể tốn `O(L)`.
- Nếu giữ nhiều phiên bản văn bản độc lập, **bộ nhớ lưu lịch sử có thể lớn**: xấp xỉ tổng kích thước những phiên bản còn được tham chiếu trong hai stack và `current`. Một bản triển khai thực tế có thể lưu **thao tác đảo ngược (command/inverse operation)** hoặc khác biệt giữa các phiên bản thay vì chụp toàn bộ văn bản.
- Nếu ứng dụng giới hạn lịch sử còn `k` bước, việc loại các trạng thái cũ nhất cần chính sách riêng; `pop` chuẩn của stack chỉ lấy trạng thái **mới nhất**.

## 8. Ứng dụng lưu trạng thái: điểm lưu và khôi phục khi xử lý lồng nhau

Một chương trình xử lý nhiều bước có thể cần **điểm lưu (checkpoint)** để quay lại khi một bước thử nghiệm thất bại. Khi các bước được lồng nhau, stack là cách tự nhiên để quản lý các checkpoint:

- `begin()`: lưu bản sao trạng thái hiện tại lên stack.
- `rollback()`: lấy checkpoint mới nhất và khôi phục trạng thái đó.
- `commit()`: bỏ checkpoint mới nhất nhưng **giữ** các thay đổi hiện tại.

Đây là mô hình minh họa cho trạng thái xử lý trong bộ nhớ, **không phải** một hệ thống giao dịch cơ sở dữ liệu đầy đủ.

```python
from copy import deepcopy


class CheckpointProcessor:
    def __init__(self, initial_state):
        self.state = deepcopy(initial_state)
        self.checkpoints = []

    def begin(self):
        self.checkpoints.append(deepcopy(self.state))

    def rollback(self):
        if not self.checkpoints:
            raise IndexError("không có checkpoint để khôi phục")
        self.state = self.checkpoints.pop()

    def commit(self):
        if not self.checkpoints:
            raise IndexError("không có checkpoint để chốt")
        self.checkpoints.pop()


p = CheckpointProcessor({"total": 0})
p.begin()                   # Điểm lưu ngoài: total = 0
p.state["total"] = 10

p.begin()                   # Điểm lưu trong: total = 10
p.state["total"] = 99
p.rollback()                # Quay lại điểm lưu trong
print(p.state["total"])     # 10

p.commit()                  # Chốt phạm vi ngoài, giữ total = 10
print(p.state["total"])     # 10
```

**Tại sao phải khôi phục checkpoint gần nhất trước?** Vì checkpoint bên trong được tạo sau, tương ứng phạm vi xử lý đang hoạt động gần nhất. Nếu bỏ qua checkpoint bên trong để khôi phục checkpoint bên ngoài, quan hệ lồng nhau giữa các phạm vi sẽ không còn nhất quán.

### Lưu ý về đối tượng có thể thay đổi

Nếu trạng thái là `dict` hoặc `list`, chỉ lưu tham chiếu bằng `checkpoints.append(state)` có thể **không tạo được bản sao độc lập**. Sửa đối tượng đang dùng cũng có thể sửa “trạng thái đã lưu” vì cả hai trỏ tới cùng một đối tượng.

Ví dụ sai:

```python
state = {"progress": [1]}
history = [state]              # Chỉ lưu tham chiếu
state["progress"].append(2)
print(history[0]["progress"])  # [1, 2] — snapshot bị thay đổi
```

Trong ví dụ `CheckpointProcessor`, `deepcopy` tạo bản sao độc lập cho các cấu trúc dữ liệu phù hợp. Tuy nhiên, không phải mọi đối tượng đều có thể sao chép sâu an toàn (ví dụ tài nguyên bên ngoài hoặc đối tượng mang khóa). Ứng dụng thật cần quyết định rõ **phần trạng thái nào được lưu và cách sao chép/khôi phục**.

Nếu một trạng thái có kích thước `S`, `begin()` dùng `deepcopy` có thể cần **`O(S)` thời gian và bộ nhớ** cho snapshot. `rollback()` và `commit()` chỉ pop checkpoint nên phần thao tác stack thường `O(1)`, không tính chi phí giải phóng dữ liệu hay những hiệu ứng bên ngoài. Với nhiều cấp lồng nhau, tổng bộ nhớ checkpoint có thể tăng theo tổng kích thước các bản sao.

## 9. Ứng dụng lưu công việc cần xử lý: duyệt đồ thị theo chiều sâu

Stack không chỉ dùng để lưu **trạng thái quá khứ** mà còn dùng để lưu **công việc chưa thực hiện**. Trong **Depth-First Search (DFS)**, khi một đỉnh có nhiều láng giềng, chương trình ưu tiên đi sâu theo một nhánh rồi mới trở về nhánh còn lại.

Ví dụ đồ thị:

```text
    S
   / \
  A   B
  |   |
  C   D
   \ /
    G
```

Ta có thể dùng stack các đỉnh đang chờ để tìm một đường đi từ `S` đến `G`. Bảng `parent` lưu đỉnh dẫn tới mỗi đỉnh khi đỉnh đó được phát hiện, nhờ vậy có thể dựng lại đường đi sau khi tìm thấy đích.

```python
def find_path_dfs(graph, start, goal):
    pending = [start]
    visited = {start}
    parent = {start: None}

    while pending:
        vertex = pending.pop()  # LIFO: xử lý đỉnh thêm gần nhất

        if vertex == goal:
            route = []
            current = goal
            while current is not None:
                route.append(current)
                current = parent[current]
            route.reverse()
            return route

        # Đảo thứ tự để xét ưu tiên láng giềng đứng trước.
        for neighbor in reversed(graph.get(vertex, [])):
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = vertex
                pending.append(neighbor)

    return None


graph = {
    "S": ["A", "B"],
    "A": ["C"],
    "B": ["D"],
    "C": ["G"],
    "D": ["G"],
    "G": [],
}

print(find_path_dfs(graph, "S", "G"))  # ['S', 'A', 'C', 'G']
print(find_path_dfs(graph, "S", "X"))  # None
```

**Bất biến:** mỗi đỉnh trong `pending` đã được phát hiện nhưng chưa xử lý; mỗi đỉnh được đánh dấu `visited` nhiều nhất một lần. `parent[v]` trỏ đến đỉnh mà từ đó `v` được phát hiện, nên có thể truy vết ngược từ đích về điểm bắt đầu.

Với `V` đỉnh và `E` cạnh trong đồ thị lưu bằng danh sách kề, thuật toán có **`O(V + E)` thời gian** và **`O(V)` bộ nhớ phụ** cho stack, tập `visited`, bảng `parent` và đường đi trả về. Mỗi đỉnh được thêm vào stack tối đa một lần.

**Giới hạn quan trọng:** DFS tìm được **một đường đi** nếu có, nhưng **không bảo đảm đường đi ngắn nhất** trong đồ thị không trọng số. Nếu cần tìm đường đi ít cạnh nhất, **BFS với queue (FIFO)** thường phù hợp hơn. Ngoài ra, cách đánh dấu `visited` khi đưa vào stack như ví dụ có thể tạo cây phát hiện khác với DFS đệ quy giữ iterator cho từng đỉnh; điều này không ảnh hưởng đến tính hợp lệ của một đường đi được tìm thấy ở đây.

## 10. Chọn stack nào cho từng loại trạng thái?

Có ba mô hình sử dụng thường gặp:

| Mô hình | Dữ liệu đưa vào stack | Khi nào `pop`? | Ứng dụng |
|---|---|---|---|
| **Phạm vi đang mở** | Dấu mở và vị trí của nó | Khi gặp dấu đóng tương ứng | Kiểm tra dấu ngoặc, phân tích cấu trúc lồng nhau |
| **Lịch sử đã xử lý** | Snapshot hoặc thao tác đảo ngược | Khi Undo hoặc Rollback | Trình soạn thảo, checkpoint |
| **Công việc chưa xử lý** | Nút đồ thị, tác vụ hoặc frame | Khi cần xử lý công việc mới nhất | DFS, quay lui, mô phỏng đệ quy |

Điểm chung là **bất biến trên đỉnh**: phần tử ở đỉnh luôn là phạm vi cần đóng tiếp theo, trạng thái cần khôi phục tiếp theo hoặc công việc cần thực hiện tiếp theo. Điều này cho phép giải thích rõ tại sao dùng LIFO.

### So sánh chi phí

| Bài toán | Thời gian | Bộ nhớ phụ | Nguyên nhân |
|---|---|---|---|
| Ghép dấu ngoặc trong chuỗi dài `n` | `O(n)` | `O(d)`, tối đa `O(n)` | Stack lưu dấu mở với độ sâu lồng lớn nhất `d` |
| Undo/Redo di chuyển tham chiếu snapshot | `O(1)` trung bình phân bổ cho thao tác stack | Phụ thuộc kích thước và số snapshot | Nội dung snapshot có thể lớn |
| Checkpoint dùng `deepcopy` | `O(S)` để lưu snapshot kích thước `S` | `O(S)` mỗi snapshot | Sao chép dữ liệu có thể thay đổi |
| DFS trên đồ thị | `O(V + E)` | `O(V)` | Lưu đỉnh chờ xử lý và đánh dấu đã thăm |

Một stack có thể được cài bằng **mảng động** hoặc **danh sách liên kết**. Với mảng động, `push`/`pop` ở cuối thường `O(1)` trung bình phân bổ; với danh sách liên kết đơn lấy nút đầu làm đỉnh, chúng đạt `O(1)` trong mô hình thao tác chuẩn, đổi lại mỗi nút cần thêm tham chiếu và cấp phát riêng. Hãy cân nhắc mức sử dụng bộ nhớ, chi phí cấp phát và kích thước phần tử thật sự được lưu.

## 11. Các lỗi thiết kế và kiểm thử cần nhớ

1. **Chỉ đếm số dấu ngoặc.** `"([)]"` có số lượng khớp nhưng thứ tự lồng sai. Stack phải lưu cả loại và thứ tự dấu mở.
2. **Gặp dấu đóng liền `pop` mà chưa kiểm tra rỗng.** Với chuỗi `")("`, `pop` trên stack rỗng sẽ gây underflow. Phải kiểm tra trước.
3. **Quên kiểm tra stack sau khi quét hết.** Chuỗi `"((("` không có dấu đóng sai loại nhưng vẫn chưa hoàn thành.
4. **Không phân biệt ngoặc trong chuỗi/chú thích của ngôn ngữ lập trình.** Một trình kiểm tra mã thực sự cần xử lý token và ngữ cảnh.
5. **Dùng trạng thái mutable làm snapshot mà không sao chép.** Các lần sửa tiếp theo có thể làm thay đổi cả bản sao được kỳ vọng là “đã lưu”.
6. **Quên xóa redo khi tạo một chỉnh sửa mới sau undo.** Điều này phá vỡ lịch sử tuyến tính của mô hình hai stack.
7. **Bỏ qua giới hạn bộ nhớ của lịch sử.** Lưu nhiều bản sao nội dung lớn có thể khiến bộ nhớ tăng nhanh; cân nhắc giới hạn lịch sử hoặc lưu thay đổi thay vì toàn bộ snapshot.
8. **Nhầm DFS với đường đi ngắn nhất.** DFS dùng stack để ưu tiên đi sâu; BFS dùng queue để tìm đường đi ngắn nhất theo số cạnh trong đồ thị không trọng số.
9. **Nhầm `O(1)` của `push` với chi phí sao chép trạng thái.** Thêm một tham chiếu có thể nhanh, nhưng tạo snapshot kích thước lớn tốn thời gian và bộ nhớ tương ứng.
10. **Không xác định chính sách stack rỗng.** Chọn ngoại lệ, kết quả thất bại hoặc hành vi khác một cách nhất quán để mã gọi biết cách xử lý.

Có thể kiểm tra một số trường hợp biên trực tiếp với các hàm và lớp trong bài:

```python
assert balanced_brackets("") is True
assert balanced_brackets("({[]})") is True
assert balanced_brackets("([)]") is False
assert balanced_brackets(")") is False
assert balanced_brackets("(((") is False

history = TextHistory("start")
assert history.undo() is False
assert history.edit("next") is True
assert history.undo() is True
assert history.current == "start"
assert history.redo() is True
assert history.current == "next"

processor = CheckpointProcessor({"count": 0})
processor.begin()
processor.state["count"] = 1
processor.rollback()
assert processor.state["count"] == 0
```

Các phép kiểm tra trên xác nhận những hành vi cơ bản và trường hợp rỗng; khi dùng trong sản phẩm thực tế cần thêm kiểm thử cho dữ liệu lớn, trạng thái lồng sâu và chính sách bộ nhớ được lựa chọn.

## 12. Tự luyện tập có đáp án

**Bài 1.** Với chuỗi `"{([{}])}"`, hãy viết stack dấu mở ngay sau khi đọc bốn ký tự đầu. Chuỗi có hợp lệ không?

**Đáp án:** Bốn ký tự đầu là `{`, `(`, `[`, `{`. Stack từ đáy tới đỉnh là `["{", "(", "[", "{"]`. Các dấu đóng `}`, `]`, `)`, `}` lần lượt khớp đỉnh; cuối cùng stack rỗng nên chuỗi hợp lệ.

**Bài 2.** Giải thích vì sao `"([)]"` sai dù số lượng `(`, `)`, `[`, `]` đều bằng nhau.

**Đáp án:** Khi gặp `)`, đỉnh stack là `[`. Dấu `)` cần khớp `(` nhưng `(` đang nằm dưới `[`; việc đóng chéo vi phạm cấu trúc lồng nhau.

**Bài 3.** Bạn gọi `edit("A")`, `edit("AB")`, `undo()`, `edit("AC")` trên `TextHistory("")`. Trạng thái hiện tại và khả năng Redo ra sao?

**Đáp án:** Sau `edit("A")` và `edit("AB")`, `current = "AB"`. `undo()` đưa `current` về `"A"` và lưu `"AB"` trong redo. `edit("AC")` tạo nhánh mới, nên `current = "AC"` và `redo_stack` bị xóa. `redo()` trả `False`.

**Bài 4.** Trong mô hình checkpoint, thực hiện `begin()` ở trạng thái `x = 1`, sửa `x = 2`, `begin()` lần nữa, sửa `x = 3`, rồi `rollback()`. `x` bằng mấy và còn bao nhiêu checkpoint?

**Đáp án:** `x = 2`. Chỉ checkpoint gần nhất bị lấy ra, nên còn một checkpoint của phạm vi ngoài (đã lưu `x = 1`).

**Bài 5.** Chuỗi có `n` ký tự với độ sâu lồng ngoặc lớn nhất bằng `d`. Thuật toán dùng stack tiêu tốn bao nhiêu thời gian và bộ nhớ phụ?

**Đáp án:** `O(n)` thời gian để duyệt chuỗi và `O(d)` bộ nhớ phụ cho các dấu mở chưa ghép; trong trường hợp xấu nhất `d = O(n)`.

**Bài 6.** Vì sao một stack DFS không đủ để bảo đảm đường đi ngắn nhất đến đích?

**Đáp án:** Stack xử lý nhánh mới nhất trước, nên có thể đi sâu theo một nhánh dài rồi mới xét nhánh ngắn hơn. Với đồ thị không trọng số, BFS theo từng lớp dùng queue mới bảo đảm tìm được đường đi ít cạnh nhất khi thực hiện đúng.

## 13. Ghi nhớ khi áp dụng

Khi một bài toán yêu cầu **khớp cấu trúc lồng nhau, quay về trạng thái gần nhất hoặc tiếp tục công việc được tạo sau cùng**, hãy xem xét stack. Với dấu ngoặc, phần tử đỉnh là dấu mở cần ghép tiếp theo; với Undo/Redo, đỉnh là snapshot có thể khôi phục tiếp theo; với DFS, đỉnh là công việc sẽ được xét tiếp.

Mỗi ứng dụng cần mô tả rõ **phần tử stack chứa gì**, **khi nào push/pop**, **bất biến sau thao tác** và **xử lý trường hợp rỗng hoặc đầy**. Chi phí của thao tác LIFO thường nhỏ, nhưng chi phí lưu trạng thái có thể lớn nếu mỗi phần tử chứa toàn bộ dữ liệu. Chọn cấu trúc và chính sách lưu trữ dựa trên thứ tự xử lý cần bảo đảm, giới hạn bộ nhớ và yêu cầu thực tế của ứng dụng.
