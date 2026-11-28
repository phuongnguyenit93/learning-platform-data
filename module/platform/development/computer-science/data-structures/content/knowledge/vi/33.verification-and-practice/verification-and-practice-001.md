# Viết đặc tả phép toán trước khi cài đặt cấu trúc

Một cấu trúc dữ liệu tốt không bắt đầu bằng việc chọn mảng, cây hay bảng băm. Nó bắt đầu bằng câu hỏi: **người sử dụng được phép làm gì, mỗi thao tác phải tạo ra kết quả nào, và điều gì luôn đúng sau thao tác?** Những câu trả lời đó tạo thành *đặc tả* (specification). Sau khi chốt đặc tả, ta mới chọn biểu diễn và cài đặt phù hợp về thời gian, bộ nhớ.

Trong quá trình học cấu trúc dữ liệu, đặc tả giúp phân biệt ba khái niệm:

- **Kiểu dữ liệu trừu tượng (ADT):** tập giá trị và các phép toán được quan sát từ bên ngoài, chẳng hạn Stack với `push`, `pop`, `peek`.
- **Hợp đồng phép toán (contract):** đầu vào hợp lệ, kết quả, trạng thái sau thao tác và cách xử lý lỗi.
- **Biểu diễn và thuật toán:** mảng động, danh sách liên kết, bảng băm, cây, heap, đồ thị... dùng để thực thi hợp đồng với chi phí nhất định.

Hai chương trình có thể cài đặt Stack bằng hai cấu trúc hoàn toàn khác nhau nhưng vẫn đúng cùng một đặc tả. Ngược lại, một chương trình chạy nhanh và không gặp lỗi cú pháp vẫn có thể *sai* nếu `pop` trả về phần tử cũ nhất thay vì mới nhất.

## 1. Đặc tả một phép toán cần ghi những gì?

Một hợp đồng nên trả lời được các câu hỏi sau **trước khi viết mã**:

| Thành phần | Câu hỏi cần trả lời | Ví dụ với Stack |
|---|---|---|
| Mô hình trạng thái | Cấu trúc biểu diễn giá trị logic nào? | Một dãy hữu hạn, từ đáy tới đỉnh |
| Tên phép toán, tham số | Người gọi cung cấp gì? | `push(x)` nhận một giá trị `x` |
| Điều kiện đầu vào | Khi nào thao tác được áp dụng? | `pop()` cần Stack có phần tử để trả về |
| Giá trị trả về | Người gọi quan sát được gì? | `pop()` trả phần tử trên đỉnh |
| Hậu điều kiện | Trạng thái phải thay đổi như thế nào? | `pop()` loại đúng một phần tử ở đỉnh |
| Trường hợp lỗi | Đầu vào/ trạng thái biên được xử lý ra sao? | `pop()` trên Stack rỗng ném `EmptyStackError` |
| Bất biến | Điều gì phải đúng trước và sau mọi thao tác công khai? | `size` bằng số phần tử logic và không âm |
| Cam kết chi phí | Độ phức tạp mong muốn theo kích thước nào? | `peek()` thời gian `O(1)` |
| Ngữ nghĩa phụ | Thứ tự, trùng lặp, `null`, đồng thời, quyền sở hữu dữ liệu? | Stack cho phép giá trị trùng; không tự bảo đảm an toàn luồng |

**Tiền điều kiện** (*precondition*) nói về trạng thái và tham số khi gọi phép toán; **hậu điều kiện** (*postcondition*) nói về điều phải đúng khi phép toán kết thúc thành công. Nếu một đầu vào không đáp ứng tiền điều kiện, ta phải chọn và ghi rõ: thao tác bị cấm với trách nhiệm thuộc về người gọi, hay API có hành vi lỗi đã định nghĩa (trả `None`, trả mã lỗi, ném ngoại lệ...). Không được im lặng để người cài đặt tự đoán.

Đặc tả cũng phải tách rõ hành vi quan sát được khỏi chi tiết lưu trữ. Với Stack, người gọi biết thứ tự LIFO (vào sau, ra trước), nhưng không cần biết có biến `topIndex`, mảng cấp phát bao nhiêu ô hoặc có dùng nút liên kết hay không.

## 2. Bắt đầu từ mô hình toán học đơn giản

Giả sử trạng thái trừu tượng của Stack là dãy:

\[
S = [s_0,s_1,\ldots,s_{n-1}],\qquad n\ge 0
\]

Quy ước `s_0` ở **đáy**, `s_{n-1}` ở **đỉnh**. Ký hiệu `S ⧺ [x]` là nối `x` vào cuối dãy, `S[:-1]` là dãy bỏ phần tử cuối, `|S|` là độ dài. Đây là quy ước của **đặc tả logic**, chưa phải cách bố trí bộ nhớ.

Ta có thể viết các phép toán theo bảng sau:

| Phép toán | Khi thành công | Khi Stack rỗng | Chi phí mục tiêu |
|---|---|---|---|
| `new()` | Tạo `S = []` | Không áp dụng | `O(1)` |
| `push(x)` | `S' = S ⧺ [x]`; không trả giá trị | Vẫn thêm được `x` | `O(1)` khấu hao nếu dùng mảng động |
| `pop()` | Trả `s_{n-1}`; `S' = S[:-1]` | Ném `EmptyStackError`, giữ nguyên `S` | `O(1)` |
| `peek()` | Trả `s_{n-1}`; `S' = S` | Ném `EmptyStackError`, giữ nguyên `S` | `O(1)` |
| `size()` | Trả `n`; `S' = S` | Trả `0` | `O(1)` |
| `is_empty()` | Trả `n == 0`; `S' = S` | Trả `True` | `O(1)` |

Ở đây `S'` là trạng thái sau thao tác. Giá trị `x` có thể trùng với phần tử khác và có thể là `None`: tính rỗng được xác định bằng số phần tử, không phải bằng giá trị ở đỉnh. Bảng chọn **ngoại lệ** làm chính sách lỗi; một hệ thống khác có thể dùng kiểu kết quả `Result` hoặc `Option`, miễn là nhất quán và được nêu rõ.

Ví dụ, trạng thái ban đầu `S = ["A", "B"]` cho chuỗi hành động:

```text
push("C")  -> S = ["A", "B", "C"]
peek()     -> "C"; S vẫn là ["A", "B", "C"]
pop()      -> "C"; S = ["A", "B"]
pop()      -> "B"; S = ["A"]
size()     -> 1;   S vẫn là ["A"]
```

Nếu dùng Stack cho lịch sử hoàn tác của trình soạn thảo, `push` đưa một thao tác mới lên đỉnh; `pop` lấy thao tác mới nhất để hoàn tác. Tính LIFO là điều kiện nghiệp vụ quan trọng hơn việc Stack lưu bằng mảng hay danh sách liên kết.

### Viết hợp đồng chính xác hơn

Ký hiệu Hoare `{P} C {Q}` diễn đạt rằng nếu tiền điều kiện `P` đúng và lệnh `C` **kết thúc bình thường**, thì hậu điều kiện `Q` phải đúng. Với `pop` trên Stack không rỗng:

\[
\{\ |S|>0\ \}\quad r\leftarrow\operatorname{pop}(S)
\quad\{\ r=\operatorname{last}(S_{old})\ \land\ S=\operatorname{init}(S_{old})\ \}
\]

`S_old` là ảnh chụp logic trước phép gọi; `init` trả về dãy bỏ phần tử cuối. Nếu `|S| = 0`, hợp đồng *lỗi* riêng quy định ném `EmptyStackError` và giữ nguyên trạng thái. Cần viết cả hai nhánh vì công thức Hoare ở trên chỉ mô tả nhánh kết thúc bình thường.

Một số tính chất suy ra trực tiếp từ đặc tả:

\[
\begin{aligned}
\operatorname{size}(\operatorname{push}(S,x)) &= |S|+1,\\
\operatorname{peek}(\operatorname{push}(S,x)) &= x,\\
\operatorname{pop}(\operatorname{push}(S,x)) &= (x,S).
\end{aligned}
\]

Ở biểu thức cuối, cặp `(x, S)` nghĩa là kết quả trả về bằng `x` **và** trạng thái còn lại bằng Stack ban đầu. Đây là những *thuộc tính có thể kiểm thử*, không phụ thuộc cài đặt.

## 3. Bất biến: điều luôn phải được giữ đúng

Một **bất biến trừu tượng** của Stack là số phần tử logic không âm, và `size()` phải trả đúng số đó. Khi chọn cách cài đặt bằng mảng động, ta bổ sung **bất biến biểu diễn**:

```text
_data: mảng có độ dài capacity >= 1
_size: số phần tử đang sử dụng

0 <= _size <= capacity
Các phần tử logic của Stack = _data[0:_size]
_data[_size:] là vùng chưa sử dụng
```

Điều kiện `_data[_size:]` là *vùng chưa sử dụng* không ngụ ý mọi ô phải khác hay bằng `None`; đó là lựa chọn nội bộ. Ta có thể chủ động gán `None` cho các ô sau khi lấy phần tử để giải phóng tham chiếu, nhưng ngữ nghĩa Stack chỉ phụ thuộc vào đoạn `_data[0:_size]`.

Hàm trừu tượng hóa liên kết biểu diễn với đặc tả:

\[
\alpha(\_data,\_size) = \_data[0:\_size].
\]

Muốn chứng minh một thao tác cài đặt đúng, kiểm tra hai việc: nó **bảo toàn bất biến biểu diễn** và tác động của nó qua hàm `α` **khớp hợp đồng logic**. Chẳng hạn, sau `pop` thành công, `_size` giảm một và `α` không còn phần tử cuối cũ.

Đừng lẫn một *bất biến nội bộ* như `_size <= capacity` với một *cam kết công khai* như `size()` luôn chính xác. Thay đổi chiến lược cấp phát không được làm thay đổi kết quả mà người dùng quan sát.

## 4. Từ đặc tả tới một cài đặt tham chiếu

Sau khi xác định hành vi, ta có thể chọn mảng động vì cần lấy/đưa phần tử ở cuối nhanh và muốn dữ liệu nằm liên tiếp trong bộ nhớ. Mã Python dưới đây là một cài đặt nhỏ để đối chiếu trực tiếp với hợp đồng. `None` vẫn là giá trị được phép đưa vào Stack.

```python
from typing import Any


class EmptyStackError(IndexError):
    pass


class ArrayStack:
    def __init__(self) -> None:
        self._data: list[Any] = [None] * 2
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def push(self, value: Any) -> None:
        if self._size == len(self._data):
            new_data = [None] * (2 * len(self._data))
            for i in range(self._size):
                new_data[i] = self._data[i]
            self._data = new_data

        self._data[self._size] = value
        self._size += 1

    def peek(self) -> Any:
        if self._size == 0:
            raise EmptyStackError("Stack rong")
        return self._data[self._size - 1]

    def pop(self) -> Any:
        if self._size == 0:
            raise EmptyStackError("Stack rong")
        self._size -= 1
        value = self._data[self._size]
        self._data[self._size] = None  # Bo tham chieu o vung khong su dung
        return value
```

Đối chiếu với đặc tả:

1. Khởi tạo `_size = 0` nên `α = []`; mọi phép gọi đọc đều phản ánh Stack rỗng.
2. `push` chỉ ghi ở vị trí `_size` rồi tăng `_size`, nên `α' = α ⧺ [value]`. Khi đầy mảng, bản sao có cùng thứ tự phần tử và tăng `capacity`.
3. `pop` kiểm tra rỗng **trước** khi sửa trạng thái; nhánh lỗi do đó giữ nguyên Stack. Ở nhánh thành công, phần tử cũ ở đỉnh được trả về, `_size` giảm một và vùng logic mất đúng phần tử cuối.
4. `peek` chỉ đọc ô `_size - 1`, không thay đổi trạng thái. `__len__` và `is_empty` dựa trên cùng `_size`.

Về chi phí, `peek`, `pop`, `__len__` và `is_empty` đều `O(1)`. Phần lớn lần `push` cũng là `O(1)`, nhưng lần phải nhân đôi mảng sẽ sao chép `n` phần tử, tức `O(n)` cho **riêng lần đó**. Vì dung lượng tăng theo hệ số hai, tổng số phần tử sao chép qua `m` lần `push` bắt đầu từ Stack rỗng là `O(m)`; do đó `push` có chi phí **khấu hao `O(1)`**, không có bảo đảm `O(1)` trong trường hợp xấu nhất của một lần gọi. Mảng trong ví dụ không thu nhỏ sau `pop`, nên lượng bộ nhớ được giữ lại phản ánh mức dung lượng lớn nhất từng đạt tới, kể cả khi Stack hiện có ít phần tử.

Mã trên mô tả hợp đồng của các phép toán khi chúng kết thúc bình thường và ngoại lệ rỗng đã định nghĩa. Nếu hệ thống cần cam kết cụ thể khi **hết bộ nhớ**, giới hạn dung lượng, hoặc bị nhiều luồng truy cập, phải bổ sung đặc tả và cài đặt tương ứng; không nên mặc định các trường hợp đó đã được bảo đảm.

## 5. Đặc tả dẫn tới kiểm thử như thế nào?

Một bộ kiểm thử tốt nên được viết từ hành vi công khai, **không đọc trực tiếp** `_data` hoặc `_size`. Các ca tối thiểu gồm Stack mới tạo, thao tác trên Stack rỗng, một phần tử, nhiều phần tử, giá trị trùng nhau, `None`, và số lượng phần tử đủ để kích hoạt tăng dung lượng.

```python
stack = ArrayStack()
assert stack.is_empty()
assert len(stack) == 0

try:
    stack.pop()
    assert False, "Phai bao loi khi pop Stack rong"
except EmptyStackError:
    pass
assert len(stack) == 0  # Nhanh loi khong thay doi trang thai

stack.push(None)
stack.push("A")
stack.push("A")
assert stack.peek() == "A"
assert len(stack) == 3
assert stack.pop() == "A"
assert stack.pop() == "A"
assert stack.pop() is None
assert stack.is_empty()

for i in range(1000):
    stack.push(i)
for i in reversed(range(1000)):
    assert stack.pop() == i
assert stack.is_empty()
```

Với chương trình lớn hơn, dùng **kiểm thử dựa trên mô hình**: giữ một dãy chuẩn `model` chỉ đóng vai trò mô tả Stack, tạo nhiều chuỗi ngẫu nhiên gồm `push`, `pop`, `peek`, rồi so sánh kết quả và kích thước của cài đặt với `model`. Ví dụ, sau `push(x)` thì `model.append(x)`; khi `model` không rỗng, `pop()` phải bằng `model.pop()`; khi rỗng, cả hai nhánh theo hợp đồng đều phải báo lỗi tương ứng mà không đổi trạng thái. Cách này tìm lỗi chỉ xuất hiện sau nhiều phép toán đan xen, nhất là ở các lần tăng dung lượng.

Ngoài việc so kết quả, có thể kiểm thử **thuộc tính**: `push(x)` rồi `pop()` phải trả `x` và khôi phục trạng thái logic trước đó; `peek()` không làm thay đổi kích thước; một lần `pop` thất bại không khiến `is_empty()` chuyển thành `False`. Những thuộc tính này thường hữu ích hơn việc chỉ kiểm một vài giá trị cố định.

## 6. Không phải mọi cấu trúc đều có cùng hợp đồng

Cùng tên phép toán có thể mang ý nghĩa khác khi áp dụng cho ADT khác. Viết đặc tả trước khi cài đặt giúp phát hiện các quyết định còn thiếu:

| Cấu trúc | Phép toán | Những quyết định phải ghi rõ |
|---|---|---|
| Queue | `enqueue(x)`, `dequeue()` | FIFO; xóa ở đầu; hành vi khi Queue rỗng; có giới hạn dung lượng hay không |
| Deque | `add_first`, `add_last`, `remove_first`, `remove_last` | Phân biệt chính xác hai đầu; xử lý khi rỗng |
| Set | `add(x)` | Phần tử trùng có bị bỏ qua không; `add` trả trạng thái mới hay cờ đã thêm? |
| Map | `put(k, v)`, `get(k)`, `remove(k)` | `put` ghi đè hay từ chối khóa tồn tại; khóa vắng mặt biểu diễn ra sao; quy tắc so sánh khóa |
| Heap ưu tiên | `insert(x)`, `extract_min()` | Đỉnh nhỏ nhất theo thứ tự nào; xử lý phần tử có độ ưu tiên bằng nhau; khi rỗng |
| Đồ thị | `add_edge(u, v)`, `neighbors(u)` | Có hướng/vô hướng; có cạnh trùng hay tự khuyên; đỉnh chưa tồn tại xử lý thế nào |

Đặc biệt, với `Map.get(k)`, nếu giá trị `None` được phép lưu, trả `None` để báo “không tìm thấy” là **mơ hồ**. Cần chọn một trong các cách: `contains_key(k)` kèm `get`, trả kiểu `Option<Value>`, hoặc ném `KeyError` khi vắng khóa. Tương tự, với bảng băm phải nêu quy tắc bằng nhau của khóa và yêu cầu giá trị băm nhất quán với phép so sánh bằng nhau. Những quyết định này thuộc **ngữ nghĩa**, không phải tối ưu hóa triển khai.

Chẳng hạn, hợp đồng của `put(k, v)` có thể viết như sau:

```text
Mô hình: M là ánh xạ hữu hạn từ khóa sang giá trị.
Tiền điều kiện: k thuộc miền khóa hợp lệ.
Thành công: M' = M với khóa k được gán giá trị v.
Kết quả: trả Option chứa giá trị cũ nếu k đã tồn tại,
         hoặc None-option nếu k chưa tồn tại.
Bảo toàn: mọi khóa khác k giữ nguyên ánh xạ.
Mục tiêu: O(1) kỳ vọng khi dùng bảng băm có phân phối tốt;
          không coi đó là bảo đảm O(1) xấu nhất.
```

Quy tắc “mọi khóa khác `k` giữ nguyên” là một **điều kiện khung** (*frame condition*): phép toán chỉ được thay đổi phần trạng thái đã cho phép. Thiếu điều kiện khung, một cài đặt vô tình xóa các cặp khóa khác vẫn có thể thỏa câu mô tả sơ sài “sau `put`, `get(k) == v`”.

## 7. Chú ý các ràng buộc phi chức năng

Đặc tả hành vi trả lời **đúng là gì**; đặc tả chi phí trả lời **đúng với nguồn lực nào**. Cả hai cần phù hợp bài toán, nhưng mức bảo đảm phải được nói chính xác:

- **Độ phức tạp theo kích thước:** nêu `n` là số phần tử, số đỉnh/cạnh hay dung lượng bộ đệm. Phân biệt chi phí tệ nhất, trung bình, kỳ vọng và khấu hao. Một HashMap thường có tra cứu `O(1)` *kỳ vọng*, trong khi cây tìm kiếm cân bằng có `O(log n)` *trường hợp xấu nhất*.
- **Bộ nhớ và quyền sở hữu:** xác định cấu trúc sao chép giá trị hay lưu tham chiếu, việc xóa có giải phóng tham chiếu không, có tạo ảnh chụp bất biến hay thay đổi trực tiếp không. Với cấu trúc có phiên bản, cần ghi rõ phép toán tạo phiên bản mới hay sửa phiên bản hiện tại.
- **Thứ tự duyệt:** `Set` và `Map` có cần giữ thứ tự chèn không? `neighbors(u)` trong đồ thị có thứ tự ổn định không? Nếu không có cam kết, không nên viết kiểm thử ngầm dựa vào thứ tự.
- **Đồng thời:** cấu trúc có được gọi đồng thời từ nhiều luồng hay không? Nếu có, phải xác định tính nguyên tử, thứ tự hiệu lực quan sát được, và cam kết nhất quán (ví dụ linearizability). Không thể suy tính an toàn luồng từ việc `push` hay `pop` chạy đúng trong một luồng.
- **Hỏng hóc và giao dịch:** khi thao tác thất bại do đầu vào không hợp lệ hoặc không còn chỗ, trạng thái có giữ nguyên không? Đặc tả rõ tính nguyên tử của thao tác trước khi tối ưu hóa.

Không phải bài tập nào cũng cần cam kết hết các mục trên. Điều quan trọng là đánh dấu chính xác mục nào được bảo đảm, mục nào nằm ngoài phạm vi; tránh để người dùng tự suy từ ví dụ.

## 8. Quy trình viết đặc tả trước khi cài đặt

Một quy trình ngắn, có thể áp dụng cho mảng, danh sách liên kết, Stack, Queue, bảng băm, cây, heap và đồ thị:

1. **Viết nhu cầu sử dụng:** ví dụ “lấy lại thao tác hoàn tác mới nhất”, “tìm người dùng theo ID”, hoặc “truy vấn tổng trên đoạn”. Đây là nguồn gốc để chọn ngữ nghĩa, không phải chọn ngay thuật toán.
2. **Chọn mô hình logic:** dãy, tập hợp, ánh xạ, cây có thứ tự, đồ thị... Quy ước thế nào là hai trạng thái bằng nhau.
3. **Liệt kê phép toán công khai:** tên, tham số, kiểu kết quả; tách thao tác chỉ đọc khỏi thao tác thay đổi trạng thái.
4. **Viết hợp đồng từng phép toán:** điều kiện đầu vào, kết quả, hậu điều kiện, điều kiện khung; ghi rõ trường hợp rỗng, trùng, không tồn tại, vượt giới hạn.
5. **Phát biểu bất biến và thuộc tính tổng quát:** những điều phải đúng sau bất kỳ chuỗi thao tác hợp lệ nào.
6. **Chốt mục tiêu chi phí:** thời gian/bộ nhớ và phạm vi bảo đảm; từ đây mới chọn mảng động, danh sách, hash, cây cân bằng, v.v.
7. **Tạo kiểm thử từ đặc tả:** ca biên, chuỗi thao tác, mô hình tham chiếu, kiểm thử thuộc tính; kiểm tra hành vi qua API công khai.
8. **Cài đặt và đối chiếu:** chỉ ra mỗi nhánh thuật toán duy trì bất biến và làm đúng hậu điều kiện; tối ưu hóa không làm đổi hợp đồng.

Có thể dùng khuôn mẫu sau cho từng phép toán:

```text
ADT / mô hình logic: ...
Phép toán: op(params) -> Result
Tiền điều kiện / miền tham số: ...
Kết quả trả về: ...
Hậu điều kiện thành công: ...
Điều kiện khung (phần không thay đổi): ...
Trường hợp lỗi và trạng thái sau lỗi: ...
Bất biến cần giữ: ...
Cam kết thời gian và bộ nhớ: ...
Các ca kiểm thử và thuộc tính: ...
```

### Bài tập tự kiểm tra

**Tình huống:** Thiết kế Queue để xử lý yêu cầu theo thứ tự đến. Mô hình là dãy `Q`, đầu dãy là yêu cầu đến sớm nhất. Đặc tả `enqueue(x)` và `dequeue()` sao cho có thể thay thế cài đặt mảng vòng bằng danh sách liên kết mà không sửa mã gọi.

Một lời giải mẫu:

```text
enqueue(x): Q' = Q ⧺ [x]; không trả giá trị.
dequeue() khi |Q| > 0:
    trả Q[0]; Q' = Q[1:]; các phần tử còn lại giữ nguyên thứ tự.
dequeue() khi |Q| = 0:
    ném EmptyQueueError; Q' = Q.
size(): trả |Q|, không đổi Q.
is_empty(): trả (|Q| == 0), không đổi Q.

Thuộc tính:
    dequeue(enqueue([], x)) trả x và còn Queue rỗng.
    enqueue(x), enqueue(y), dequeue() trả x (FIFO).
Mục tiêu: enqueue/dequeue O(1) với mảng vòng có tăng dung lượng
          (enqueue khấu hao) hoặc danh sách liên kết có con trỏ đầu/cuối.
```

Hãy tự thử thêm chính sách khi Queue đạt dung lượng tối đa: chặn chờ, báo lỗi, hay bỏ phần tử? Mỗi lựa chọn làm thay đổi hợp đồng, vì vậy phải quyết định **trước khi** viết thuật toán.

## 9. Những dấu hiệu đặc tả còn thiếu

Đọc lại một bản đặc tả và đặt câu hỏi:

- Nếu cấu trúc rỗng, thao tác đọc/xóa có kết quả nào? Trạng thái sau lỗi ra sao?
- Nếu có phần tử trùng hoặc giá trị `None`, có bị nhập nhằng với “không tồn tại” không?
- Nếu gọi lặp nhiều lần, thao tác có bảo toàn thứ tự, số lượng và các phần không liên quan không?
- Người gọi có đang dựa vào chi tiết cài đặt như vị trí ô nhớ hoặc thứ tự bucket không?
- Phát biểu `O(1)` hoặc `O(log n)` có chỉ rõ trường hợp xấu nhất, kỳ vọng hay khấu hao không?
- Có thể viết kiểm thử chỉ từ tài liệu, khi chưa nhìn thấy phần cài đặt không?

Nếu câu cuối chưa trả lời được, rất có thể tài liệu mới mô tả *ý định* chứ chưa đủ chính xác để trở thành *hợp đồng*. Khi hợp đồng rõ ràng, việc chọn cấu trúc dữ liệu trở thành một quyết định có thể kiểm chứng: cấu trúc được chọn phải thực hiện đúng ngữ nghĩa, giữ bất biến và đáp ứng mức chi phí đã cam kết.
