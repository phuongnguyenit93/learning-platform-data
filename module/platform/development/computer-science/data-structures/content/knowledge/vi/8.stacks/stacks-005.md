# Ngăn xếp lời gọi và mối liên hệ với đệ quy

## 1. Từ ngăn xếp LIFO đến các lời gọi hàm

Trong chương **Ngăn xếp** của học phần **Cấu trúc dữ liệu**, ta đã có thể mô tả một stack bằng ba phép cơ bản: `push(x)` thêm một phần tử lên đỉnh, `pop()` lấy và xóa phần tử đỉnh, còn `peek()` xem đỉnh mà không xóa. Nguyên tắc nền tảng là **LIFO (Last In, First Out)**: phần tử được thêm vào gần đây nhất được lấy ra trước tiên.

**Ngăn xếp lời gọi (call stack)** là cơ chế môi trường thực thi thường dùng để theo dõi các lời gọi hàm đang hoạt động. Khi một hàm gọi hàm khác, chương trình cần ghi nhớ nơi sẽ tiếp tục chạy, các tham số và những dữ liệu riêng của lời gọi đó. Thông tin cần thiết cho một lời gọi được biểu diễn trong một **khung lời gọi (stack frame, activation record)**.

Về mặt khái niệm:

- **Gọi hàm:** tạo một khung lời gọi mới, đặt lên đỉnh call stack.
- **Hàm đang chạy:** khung tương ứng nằm ở đỉnh của chuỗi lời gọi đang hoạt động.
- **Hàm kết thúc bình thường:** khung lời gọi được rời bỏ; chương trình quay lại hàm đã gọi nó tại vị trí thích hợp.
- **Hàm gọi tiếp một hàm khác:** lời gọi mới nằm phía trên lời gọi cũ. Hàm gọi bị tạm dừng cho đến khi lời gọi con trả kết quả hoặc luồng điều khiển được chuyển theo cơ chế khác (ví dụ ngoại lệ).

Đây là lý do call stack có hành vi **LIFO**: hàm được gọi sau cùng trong một chuỗi gọi lồng nhau thường hoàn tất trước để hàm gọi nó tiếp tục.

```text
main() gọi A(), A() gọi B(), B() gọi C()

Thời điểm C đang chạy:

       ĐỈNH NGĂN XẾP LỜI GỌI
        ┌─────────────────┐
        │ khung của C()   │ ← lời gọi đang hoạt động
        ├─────────────────┤
        │ khung của B()   │ ← đang chờ C() trả về
        ├─────────────────┤
        │ khung của A()   │ ← đang chờ B() trả về
        ├─────────────────┤
        │ khung của main()│ ← đang chờ A() trả về
        └─────────────────┘
       ĐÁY NGĂN XẾP LỜI GỌI

C hoàn tất → quay về B → B hoàn tất → quay về A → A hoàn tất → main
```

Sơ đồ là **mô hình tư duy**. Cách khung lời gọi được đặt trong bộ nhớ tùy ngôn ngữ, trình biên dịch, trình thông dịch và khả năng tối ưu hóa. Ví dụ, trình biên dịch có thể nội tuyến một hàm; runtime có thể lưu một số trạng thái trên heap. Không phải mọi khung lời gọi đều nhất thiết là một đối tượng liên tiếp được cấp phát theo đúng hình vẽ.

### Call stack khác với stack tự cài như thế nào?

| Khía cạnh | Stack như kiểu dữ liệu trừu tượng (ADT) | Call stack của chương trình |
|---|---|---|
| Mục đích | Lưu và lấy dữ liệu theo LIFO | Quản lý trạng thái các lời gọi hàm đang hoạt động |
| Phần tử | Giá trị do chương trình quyết định, ví dụ số, tác vụ, nút đồ thị | Khung lời gọi và thông tin điều khiển liên quan |
| Thao tác | Lập trình viên thường gọi `push`, `pop`, `peek` | Runtime, mã máy hoặc trình thông dịch điều phối khi gọi/trả về |
| Cách cài đặt | Mảng, mảng động, danh sách liên kết, v.v. | Phụ thuộc môi trường thực thi; có thể có nhiều cơ chế |
| Giới hạn | Theo dung lượng, bộ nhớ và chính sách ứng dụng | Theo giới hạn của runtime, luồng và tài nguyên hệ thống |

Ta có thể tạo một đối tượng `Stack` bằng mảng để triển khai thuật toán. Đối tượng đó **không đồng nhất** với call stack, mặc dù cùng dùng nguyên tắc LIFO.

## 2. Một khung lời gọi chứa những gì?

Khái niệm **stack frame** giúp giải thích tại sao hai lần gọi cùng một hàm vẫn có thể giữ trạng thái riêng. Tùy môi trường, một khung hoặc các dữ liệu liên quan đến lời gọi có thể bao gồm:

1. **Thông tin điều khiển:** vị trí cần tiếp tục sau khi lời gọi con hoàn tất, hoặc thông tin cho cơ chế trả về.
2. **Tham số và các biến cục bộ:** dữ liệu thuộc lần gọi đang diễn ra; phần lưu trữ cụ thể tùy runtime.
3. **Trạng thái tính toán trung gian:** các giá trị hoặc vị trí chương trình cần giữ trong khi chờ lời gọi khác.
4. **Thông tin liên kết với lời gọi trước:** đủ để khôi phục môi trường thực thi thích hợp khi quay về.

Ví dụ:

```python
def outer(a):
    x = a + 1
    y = inner(x)
    return x * y

def inner(b):
    result = b * 2
    return result

print(outer(4))  # 50
```

Diễn biến:

- Gọi `outer(4)`: dữ liệu của lần gọi gồm `a = 4`, sau đó `x = 5`.
- `outer` gọi `inner(5)`: lần gọi mới có tham số `b = 5` và tính `result = 10`.
- `inner` trả `10`; `outer` tiếp tục tại phép gán `y = inner(x)`, nên `y = 10`.
- `outer` trả `x * y = 5 * 10 = 50`.

Trong thời gian `inner` chạy, `outer` vẫn cần nhớ `x = 5` và công việc còn lại. Ngăn xếp lời gọi cung cấp một cách tổ chức tự nhiên cho trạng thái đang chờ đó.

**Không nên kết luận mọi biến cục bộ chắc chắn được lưu trực tiếp trên call stack vật lý.** Một số biến có thể nằm trong thanh ghi, vùng nhớ khác hoặc được trình biên dịch tối ưu hóa. Điều quan trọng trong mô hình học là **trạng thái logic của mỗi lần gọi được giữ riêng**.

## 3. Đệ quy là gì và tại sao liên quan đến call stack?

**Đệ quy (recursion)** xảy ra khi một hàm gọi lại chính nó (**đệ quy trực tiếp**) hoặc gọi qua một chuỗi hàm dẫn về nó (**đệ quy gián tiếp/tương hỗ**).

Một hàm đệ quy đúng thường cần:

- **Trường hợp cơ sở (base case):** điều kiện dừng mà ta biết kết quả trực tiếp, không cần gọi tiếp.
- **Bước đệ quy (recursive case):** chia bài toán thành lời gọi trên dữ liệu nhỏ hơn hoặc trạng thái tiến gần đến điều kiện dừng.
- **Đại lượng tiến triển:** một cách giải thích vì sao cuối cùng sẽ tới base case, chẳng hạn `n` giảm dần về `0`, hoặc kích thước cây con giảm dần.
- **Cách kết hợp kết quả:** xử lý giá trị trả về sau khi lời gọi con hoàn tất, nếu thuật toán cần.

Mỗi lần gọi đệ quy là **một lần gọi hàm mới**, dù tên hàm giống nhau. Vì vậy, các lời gọi đệ quy đang chờ trả về tạo nên một chuỗi khung lời gọi trên call stack.

Ví dụ cơ bản:

```python
def countdown(n):
    if n == 0:
        print("Bắt đầu!")
        return
    print(n)
    countdown(n - 1)

countdown(3)
```

Kết quả:

```text
3
2
1
Bắt đầu!
```

Các lời gọi tạo ra theo thứ tự `countdown(3) → countdown(2) → countdown(1) → countdown(0)`. Lời gọi `countdown(0)` gặp base case, trả về trước; sau đó các lời gọi còn lại lần lượt kết thúc theo thứ tự ngược lại.

Để minh họa đơn giản, ví dụ giả định `n` là số nguyên không âm. Với `countdown(-1)`, đại lượng không tiến về `0` nên hàm không có điều kiện dừng phù hợp; cần kiểm tra đầu vào nếu muốn hàm xử lý cả số âm.

## 4. Truy vết đầy đủ: tính giai thừa bằng đệ quy

Giai thừa của số nguyên không âm `n` được định nghĩa:

\[
n! =
\begin{cases}
1, & n=0,\\
n\cdot(n-1)!, & n>0.
\end{cases}
\]

Ta có thể viết:

```python
def factorial(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError("n phải là số nguyên không âm")
    if n == 0:
        return 1
    return n * factorial(n - 1)

print(factorial(4))  # 24
```

Khi tính `factorial(4)`, mỗi lần gọi cần giữ lại giá trị `n` riêng của nó để sau khi `factorial(n - 1)` trả về thì nhân với `n`.

### Giai đoạn đi sâu: tạo các lời gọi mới

```text
factorial(4)
  cần 4 * factorial(3)
           cần 3 * factorial(2)
                    cần 2 * factorial(1)
                             cần 1 * factorial(0)
                                      trả 1
```

Ngay trước khi lời gọi cơ sở `factorial(0)` trả về:

```text
          top
           ↓
     ┌──────────────────────────────┐
     │ factorial(0): trả ngay 1     │
     ├──────────────────────────────┤
     │ factorial(1): chờ nhân với 1 │
     ├──────────────────────────────┤
     │ factorial(2): chờ nhân với 2 │
     ├──────────────────────────────┤
     │ factorial(3): chờ nhân với 3 │
     ├──────────────────────────────┤
     │ factorial(4): chờ nhân với 4 │
     └──────────────────────────────┘
```

Đó là năm lời gọi đang hoạt động của `factorial`: với `n = 4, 3, 2, 1, 0`. Các lời gọi chưa hoàn tất **không thể dùng chung một biến `n` duy nhất**, bởi mỗi lời gọi cần ghi nhớ giá trị của riêng nó.

### Giai đoạn quay lui: trả kết quả theo LIFO

| Khung kết thúc | Giá trị nhận từ lời gọi con | Phép tính | Giá trị trả về |
|---|---|---|---|
| `factorial(0)` | Không cần | Base case | `1` |
| `factorial(1)` | `factorial(0) = 1` | `1 × 1` | `1` |
| `factorial(2)` | `factorial(1) = 1` | `2 × 1` | `2` |
| `factorial(3)` | `factorial(2) = 2` | `3 × 2` | `6` |
| `factorial(4)` | `factorial(3) = 6` | `4 × 6` | `24` |

Thứ tự hoàn tất **`factorial(0) → factorial(1) → factorial(2) → factorial(3) → factorial(4)`** ngược với thứ tự đi sâu. Nhờ cơ chế call stack, không cần tự tạo một danh sách để nhớ từng phép nhân chưa thực hiện.

### Tự quan sát thời điểm gọi và trả về

```python
def trace_factorial(n, depth=0):
    indent = "  " * depth
    print(f"{indent}Gọi factorial({n})")
    if n == 0:
        print(f"{indent}Trả 1")
        return 1

    child = trace_factorial(n - 1, depth + 1)
    result = n * child
    print(f"{indent}Trả {n} * {child} = {result}")
    return result

trace_factorial(3)
```

Các dòng in về việc **gọi** sẽ đi vào sâu từng cấp; các dòng in về việc **trả** sẽ xuất hiện từ cấp sâu nhất trở lên. `depth` ở ví dụ chỉ được dùng để thụt lề cho dễ nhìn, không phải biến bắt buộc của một hàm đệ quy.

## 5. Phân tích độ sâu đệ quy và chi phí bộ nhớ

**Độ sâu đệ quy** là số lời gọi lồng nhau còn đang hoạt động trên cùng một chuỗi khi chương trình đi sâu nhất. Độ sâu này giúp ước lượng lượng trạng thái cần giữ cùng lúc.

Giả sử mỗi lần gọi có lượng dữ liệu điều khiển và biến cục bộ hằng số, không xét chi phí tính toán số nguyên lớn:

- `factorial(n)` có `n + 1` lời gọi của chính hàm đó đang hoạt động ở thời điểm sâu nhất, tính cả `factorial(0)`.
- **Thời gian:** mỗi cấp thực hiện số lượng thao tác cơ bản hằng số, tổng cộng `O(n)`.
- **Không gian phụ do các lời gọi:** có `O(n)` khung hoạt động, tương ứng `O(n)` bộ nhớ trong mô hình phân tích thông thường.

Một vòng lặp có thể giải cùng bài toán:

```python
def factorial_iterative(n):
    if not isinstance(n, int) or n < 0:
        raise ValueError("n phải là số nguyên không âm")
    result = 1
    for value in range(2, n + 1):
        result *= value
    return result

print(factorial_iterative(4))  # 24
```

Trong mô hình số học coi một phép nhân là `O(1)`, phiên bản lặp cũng mất `O(n)` thời gian nhưng chỉ dùng **`O(1)` biến trạng thái phụ**, không tạo chuỗi `n + 1` lời gọi đệ quy. Với Python, số nguyên có độ dài không giới hạn cố định; phân tích chính xác thời gian nhân và bộ nhớ lưu kết quả lớn phải tính thêm kích thước các số.

### Phân biệt độ sâu và tổng số lời gọi

Một thuật toán có thể có rất nhiều lời gọi **tổng cộng** nhưng số khung tồn tại cùng lúc lại thấp hơn. Ví dụ Fibonacci đệ quy đơn giản:

```python
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
```

Hàm này tính lặp nhiều bài toán con: ví dụ `fibonacci(5)` tính lại `fibonacci(3)` và `fibonacci(2)` ở nhiều nhánh. **Tổng thời gian** tăng theo cấp số nhân (có thể chặn trên bằng `O(2^n)`), nhưng **độ sâu lời gọi tối đa** vẫn là `O(n)`: một lời gọi con hoàn tất rồi mới đi sang lời gọi con khác. Số khung đồng thời và tổng số lần thực thi hàm là hai đại lượng khác nhau.

| Bài toán | Thời gian trong mô hình cơ bản | Độ sâu gọi tối đa | Bộ nhớ phụ do khung gọi |
|---|---|---|---|
| `factorial(n)` đệ quy | `O(n)` | `O(n)` | `O(n)` |
| `factorial(n)` vòng lặp | `O(n)` | `O(1)` | `O(1)` |
| `fibonacci(n)` đệ quy ngây thơ | `O(2^n)` là chặn trên | `O(n)` | `O(n)` |
| Duyệt cây nhị phân đệ quy, `N` nút và chiều cao `h` | `O(N)` | `O(h)` | `O(h)` |

Ở đây, `h` tính theo **số nút trên đường từ gốc đến lá dài nhất**. Với cây tương đối cân bằng, `h = O(log N)`; với cây lệch thành một chuỗi, `h = O(N)`.

## 6. Khi nào call stack có thể bị quá sâu?

Mỗi môi trường thực thi có giới hạn độ sâu đệ quy, dung lượng ngăn xếp luồng hoặc các giới hạn tài nguyên khác. Nếu số lần gọi lồng nhau tăng không kiểm soát, chương trình có thể phát sinh **lỗi giới hạn đệ quy** hoặc **tràn ngăn xếp lời gọi (call stack overflow)**.

### Thiếu base case hoặc không tiến gần base case

```python
def bad_countdown(n):
    return bad_countdown(n)  # n không đổi; không thể tới điểm dừng
```

Hàm này không có điều kiện dừng và không làm bài toán nhỏ đi. Khi được gọi, chuỗi lời gọi tiếp tục cho đến khi chạm giới hạn của môi trường thực thi.

Lỗi tinh vi hơn là có base case nhưng dữ liệu không tiến về nó:

```python
def also_bad(n):
    if n == 0:
        return 0
    return also_bad(n + 1)  # Với n > 0, đi xa khỏi n == 0
```

**Quy tắc thiết kế:** với đầu vào hợp lệ, xác định một đại lượng hữu hạn, không âm và giảm dần nghiêm ngặt qua mỗi bước đệ quy, hoặc một quan hệ tiến triển tương tự bảo đảm có điểm dừng. Với đệ quy trên cây, số nút chưa xử lý hoặc kích thước cây con là đại lượng phù hợp nếu cấu trúc hữu hạn và không có chu trình.

### Đệ quy rất sâu dù thuật toán đúng

Ngay cả một hàm kết thúc về mặt toán học vẫn có thể vượt giới hạn runtime khi đầu vào quá lớn:

```python
def depth(n):
    if n == 0:
        return 0
    return 1 + depth(n - 1)
```

`depth(n)` đúng với `n ≥ 0`, nhưng tạo độ sâu tuyến tính theo `n`. Trong Python, vượt giới hạn đệ quy thường sinh ngoại lệ `RecursionError`. Giới hạn cụ thể phụ thuộc phiên bản và cấu hình môi trường; không nên giả định một con số cố định.

Không nên mặc định rằng chỉ cần tăng giới hạn bằng `sys.setrecursionlimit(...)` là an toàn: call stack hoặc các nguồn lực thực thi khác vẫn có giới hạn. Nếu đầu vào có thể tạo độ sâu rất lớn, **dùng vòng lặp hoặc stack dữ liệu tường minh** thường dễ kiểm soát hơn.

### Đệ quy đuôi và tối ưu hóa

**Đệ quy đuôi (tail recursion)** là trường hợp một lời gọi đệ quy là hành động cuối cùng của hàm; sau khi lời gọi con trả về, lời gọi cha không phải làm phép tính bổ sung nào.

```python
def factorial_tail(n, acc=1):
    if n == 0:
        return acc
    return factorial_tail(n - 1, n * acc)
```

Trong một số ngôn ngữ và cấu hình tối ưu, trình biên dịch có thể biến lời gọi đuôi thành dạng lặp và không làm tăng độ sâu call stack. **Python không bảo đảm tối ưu lời gọi đuôi**, nên `factorial_tail(n)` vẫn có thể vượt giới hạn đệ quy. Đừng nhầm “đệ quy đuôi” với “chắc chắn dùng `O(1)` bộ nhớ” trong mọi ngôn ngữ.

## 7. Chuyển đệ quy thành stack tường minh

Một cách hiểu sâu cơ chế call stack là tự lưu trạng thái cần xử lý vào **stack dữ liệu**. Khi đó thay vì runtime tự quản lý các khung lời gọi đệ quy, chương trình dùng `append`/`pop` của một danh sách làm stack.

### Ví dụ: duyệt cây nhị phân theo thứ tự trước (preorder)

Preorder xử lý **nút hiện tại → cây con trái → cây con phải**.

```text
        A
       / \
      B   C
     / \
    D   E

Kết quả preorder: A, B, D, E, C
```

Trước tiên, phiên bản đệ quy:

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def preorder_recursive(root):
    if root is None:
        return
    print(root.value)
    preorder_recursive(root.left)
    preorder_recursive(root.right)


root = Node("A",
            Node("B", Node("D"), Node("E")),
            Node("C"))
preorder_recursive(root)  # A B D E C (mỗi giá trị một dòng)
```

Mỗi lời gọi đang chờ duyệt cây con phải, nên runtime cần lưu trạng thái để quay lại đúng cây con sau khi xử lý cây con trái.

Phiên bản tương đương dùng stack tường minh:

```python
def preorder_iterative(root):
    if root is None:
        return []

    stack = [root]
    result = []

    while stack:
        node = stack.pop()
        result.append(node.value)

        # Push phải trước để trái nằm trên đỉnh và được lấy ra trước.
        if node.right is not None:
            stack.append(node.right)
        if node.left is not None:
            stack.append(node.left)

    return result


print(preorder_iterative(root))  # ['A', 'B', 'D', 'E', 'C']
```

Vết thực thi của phiên bản lặp, **bên phải là đỉnh stack**:

| Lần xử lý | Nút vừa `pop` | Stack sau khi thêm các con | Kết quả đã ghi |
|---:|---|---|---|
| Khởi tạo | — | `[A]` | `[]` |
| 1 | `A` | `[C, B]` | `[A]` |
| 2 | `B` | `[C, E, D]` | `[A, B]` |
| 3 | `D` | `[C, E]` | `[A, B, D]` |
| 4 | `E` | `[C]` | `[A, B, D, E]` |
| 5 | `C` | `[]` | `[A, B, D, E, C]` |

**Tại sao phải push nút phải trước?** Vì stack là LIFO: phần tử được thêm cuối sẽ được pop trước. Muốn xử lý cây con trái trước, ta phải thêm nút trái **sau** nút phải.

Cả hai cách đều thăm mỗi nút một lần, nên tốn `O(N)` thời gian với cây có `N` nút. Phiên bản đệ quy sử dụng `O(h)` bộ nhớ phụ cho khung lời gọi; phiên bản lặp dùng stack các nút chưa thăm, tối đa `O(h)` phần tử đối với cây nhị phân (không tính danh sách `result` chứa `N` giá trị). Phiên bản lặp tránh đệ quy sâu nhưng **không loại bỏ nhu cầu lưu trạng thái**; nó chuyển nhu cầu đó từ call stack sang stack do chương trình quản lý.

### Không phải mọi phép chuyển đều chỉ là thêm một danh sách

Ví dụ preorder chỉ cần lưu **nút sẽ xử lý**. Với một thuật toán có công việc **sau khi lời gọi con trả về** (như giai thừa, duyệt cây inorder/postorder hoặc thuật toán quay lui phức tạp), stack tường minh có thể cần khung chứa thêm thông tin:

- Tham số và dữ liệu cục bộ của trạng thái hiện tại.
- Giai đoạn xử lý (mới bắt đầu, đã xử lý con trái, đang chờ con phải, ...).
- Giá trị trung gian được giữ lại để tiếp tục khi công việc con hoàn tất.

Những thông tin này tương ứng với phần trạng thái call stack ngầm định đã lưu hộ hàm đệ quy.

## 8. Ngoại lệ, ngăn xếp lời gọi và truy vết lỗi

Khi hàm gọi sâu phát sinh ngoại lệ mà không xử lý tại chỗ, lỗi có thể **lan truyền qua các hàm gọi**. Trong quá trình này, runtime thực hiện **stack unwinding**: rời khỏi những lời gọi liên quan theo thứ tự từ trong ra ngoài, cho đến khi tìm được nơi xử lý ngoại lệ hoặc chương trình kết thúc do lỗi chưa được xử lý.

```python
def level_three():
    raise ValueError("dữ liệu không hợp lệ")

def level_two():
    try:
        level_three()
    finally:
        print("Dọn dẹp ở level_two")

def level_one():
    try:
        level_two()
    except ValueError as error:
        print("Đã xử lý:", error)

level_one()
```

Kết quả:

```text
Dọn dẹp ở level_two
Đã xử lý: dữ liệu không hợp lệ
```

Thứ tự này cho thấy khi lỗi truyền từ `level_three` trở về nơi gọi, khối `finally` của `level_two` vẫn được chạy trước khi `level_one` nhận lỗi. Tuy nhiên, **không phải mọi cách chấm dứt chương trình đều bảo đảm chạy mã dọn dẹp** (ví dụ tiến trình bị kết thúc cưỡng bức); cần xét đúng ngữ nghĩa của ngôn ngữ.

**Stack trace/traceback** là thông tin hữu ích khi gỡ lỗi: nó có thể hiển thị chuỗi các hàm đã dẫn đến vị trí xảy ra lỗi, thường theo vị trí tệp và số dòng. Đó là biểu diễn của lịch sử lời gọi liên quan tới lỗi, **không phải** một stack dữ liệu mà người lập trình bắt buộc phải quản lý bằng `push`/`pop`.

## 9. Lỗi tư duy thường gặp khi học đệ quy

1. **Quên điều kiện dừng.** Hàm cứ gọi lại chính nó; cần base case rõ ràng và xử lý đúng đầu vào.
2. **Có base case nhưng không tiến về nó.** Ví dụ `n + 1` khi cần giảm về `0`; kiểm tra đại lượng tiến triển.
3. **Cho rằng các lời gọi cùng chia sẻ một biến cục bộ.** `factorial(4)` và `factorial(3)` giữ giá trị `n` riêng. Biến toàn cục hoặc đối tượng chia sẻ có hành vi khác và cần được đánh giá riêng.
4. **Nhầm thứ tự gọi với thứ tự trả về.** Lời gọi sâu nhất thường hoàn tất trước. Phép nhân trong `factorial` được thực hiện ở giai đoạn quay về.
5. **Đếm tổng số lời gọi thành độ sâu tối đa.** Fibonacci ngây thơ tạo rất nhiều lời gọi tổng cộng, nhưng không giữ đồng thời toàn bộ số lời gọi ấy trên call stack.
6. **Coi đệ quy luôn chậm hơn lặp hoặc ngược lại.** Hiệu quả phụ thuộc bài toán, cách triển khai, tối ưu của ngôn ngữ và dữ liệu. Đệ quy thường biểu đạt cấu trúc phân cấp rất rõ, còn vòng lặp tránh độ sâu call stack lớn.
7. **Giả định đệ quy đuôi luôn dùng bộ nhớ hằng số.** Phụ thuộc ngôn ngữ/runtime; Python không bảo đảm điều đó.
8. **Nhầm call stack với stack ADT tự tạo.** Đổi dung lượng một stack mảng do ứng dụng tự quản lý không nhất thiết tăng giới hạn khung lời gọi của runtime.

## 10. Khi nào nên chọn đệ quy hay stack tường minh?

| Tiêu chí | Đệ quy dùng call stack | Vòng lặp dùng stack tường minh |
|---|---|---|
| Cách biểu diễn | Mỗi bài toán con là một lời gọi hàm | Mỗi trạng thái chờ được thêm vào cấu trúc dữ liệu |
| Mã nguồn | Thường ngắn gọn với cây, chia để trị | Có thể dài hơn do tự quản lý trạng thái |
| Thứ tự xử lý | Theo thứ tự lời gọi và trả về của hàm | Do thứ tự `push`/`pop` quyết định |
| Độ sâu lớn | Có thể chạm giới hạn đệ quy/call stack | Không phụ thuộc trực tiếp vào độ sâu đệ quy nhưng vẫn cần bộ nhớ cho stack dữ liệu |
| Trạng thái trung gian | Runtime quản lý khung gọi | Chương trình phải lưu thông tin cần thiết |
| Kiểm soát tài nguyên | Bị ràng buộc bởi runtime | Có thể giới hạn và xử lý tràn cho stack tự quản lý |

**Dùng đệ quy** khi cấu trúc bài toán tự nhiên là phân cấp, độ sâu trong giới hạn an toàn và tính dễ đọc quan trọng. **Dùng stack tường minh** khi cần kiểm soát chính sách bộ nhớ, xử lý đầu vào rất sâu hoặc muốn mô phỏng thuật toán tìm kiếm theo chiều sâu bằng vòng lặp.

Một lựa chọn đúng phải xét đồng thời **bất biến thao tác**, **độ phức tạp thời gian**, **không gian phụ** và **giới hạn thực thi**, thay vì chỉ đếm số dòng mã.

## 11. Tự luyện tập và đối chiếu đáp án

**Câu 1.** Hàm `A()` gọi `B()`, `B()` gọi `C()`. Khi `C()` đang chạy, khung nào nằm trên cùng trong call stack? Nếu không có ngoại lệ hoặc cơ chế điều khiển đặc biệt, hàm nào tiếp tục chạy ngay khi `C()` trả về?

**Đáp án:** Khung của `C()` ở đỉnh. Sau `C()`, `B()` tiếp tục tại vị trí sau lời gọi `C()`.

**Câu 2.** Cho `factorial(3)` với base case `factorial(0) = 1`. Hãy viết thứ tự lời gọi và thứ tự trả kết quả.

**Đáp án:** Gọi: `3 → 2 → 1 → 0`. Trả: `factorial(0) = 1`, `factorial(1) = 1`, `factorial(2) = 2`, `factorial(3) = 6`.

**Câu 3.** Hàm đệ quy duyệt một cây có `N` nút, chiều cao `h`. Nếu ở mỗi nút chỉ xử lý hằng số thao tác và gọi đệ quy tới các cây con, thời gian và bộ nhớ call stack là bao nhiêu?

**Đáp án:** Thời gian `O(N)`, bộ nhớ phụ của call stack `O(h)`. Nếu cây cân bằng, `h` cỡ `O(log N)`; nếu cây lệch, `h` có thể là `O(N)`.

**Câu 4.** Khi dùng stack tường minh để duyệt preorder cây nhị phân, tại sao phải `push` cây con phải **trước** cây con trái?

**Đáp án:** Stack hoạt động LIFO nên nút trái được thêm sau sẽ được lấy ra trước, đúng yêu cầu xử lý trái trước phải.

**Câu 5.** Có nên cho rằng hàm `factorial_tail` trong Python an toàn với mọi `n` rất lớn vì đó là đệ quy đuôi?

**Đáp án:** Không. Python không bảo đảm tối ưu lời gọi đuôi, nên vẫn có thể gặp `RecursionError`. Với độ sâu lớn, dùng vòng lặp hoặc cách xử lý không yêu cầu nhiều khung lồng nhau.

**Câu 6.** Một hàm có base case nhưng vẫn rơi vào đệ quy vô hạn. Điều nào cần kiểm tra đầu tiên?

**Đáp án:** Kiểm tra mỗi bước đệ quy có làm giảm hoặc tiến triển một đại lượng đảm bảo tới base case với mọi đầu vào hợp lệ hay không; đồng thời kiểm tra các nhánh có bỏ qua base case và dữ liệu có tạo chu trình hay không.

**Ghi nhớ:** Call stack quản lý những lần gọi hàm đang hoạt động theo **LIFO**. Đệ quy tạo ra các lời gọi lồng nhau, mỗi lời gọi có trạng thái logic riêng và sẽ trả kết quả khi các lời gọi sâu hơn hoàn tất. Phân tích độ sâu cho biết chi phí bộ nhớ khung gọi; chuyển sang stack tường minh có thể kiểm soát được cách lưu trạng thái nhưng vẫn phải tôn trọng bất biến LIFO và đánh giá chi phí thời gian, bộ nhớ của thuật toán.
