# Tuần tự hóa, khôi phục cây và mã hóa nút con rỗng

**Tuần tự hóa cây** (*tree serialization*) là chuyển một cấu trúc cây đang nằm trong bộ nhớ thành một dãy dữ liệu có thể lưu vào tệp, gửi qua mạng hoặc truyền cho chương trình khác. **Khôi phục cây** (*deserialization*) là đọc dãy ấy để dựng lại các nút và liên kết cha–con.

Thử thách chính không phải chỉ lưu đủ **giá trị nút**, mà còn phải lưu đủ **hình dạng cây**. Nếu hai nút cùng mang một giá trị, nếu một nút chỉ có con trái hoặc chỉ có con phải, hoặc nếu cây có nhiều nhánh rỗng, định dạng phải cho phép bộ giải mã phân biệt chính xác các trường hợp ấy.

Ví dụ hai cây dưới đây có cùng dãy preorder nếu chỉ ghi các nút thật:

```text
Cây 1                         Cây 2

    A                             A
   /                               \
  B                                 B

Preorder bỏ qua nhánh rỗng:
A, B                           A, B
```

Nếu bỏ thông tin về các con rỗng, **không thể biết B nằm bên trái hay bên phải A**. Vì vậy, một cách giải đơn giản và chắc chắn là mã hóa **cả các nhánh rỗng**.

Bài thuộc chương **Duyệt và biến đổi cây** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, ta chú trọng **bất biến, thao tác, thời gian và bộ nhớ** để lựa chọn cách biểu diễn phù hợp. Bài tập trung vào hai định dạng phổ biến: **preorder DFS có token rỗng** và **level-order BFS có token rỗng**, cùng các điều kiện để quá trình mã hóa/giải mã đúng, không nhập nhằng.

## 1. Mục tiêu của một định dạng tuần tự hóa cây

Xét cây nhị phân có gốc, mỗi nút chứa `value` và có tối đa hai tham chiếu `left`, `right`. Ta muốn bảo đảm những thuộc tính sau:

1. **Giữ giá trị:** giá trị mỗi nút sau giải mã phải tương đương giá trị đã mã hóa.
2. **Giữ cấu trúc:** nút nào có con trái, con phải hoặc không có con đều phải được khôi phục đúng.
3. **Giữ thứ tự hai nhánh:** con trái và con phải là hai vị trí **khác nhau**.
4. **Không nhập nhằng:** một dãy hợp lệ chỉ mô tả một cây theo quy ước định dạng.
5. **Có khả năng phát hiện lỗi:** dữ liệu thiếu, thừa hoặc token sai định dạng phải bị từ chối thay vì tự đoán.
6. **Có thể phân tích chi phí:** số token, thời gian và bộ nhớ cần được xác định rõ.

Hai yêu cầu khác nhau cần phân biệt:

- **Mã hóa/giải mã trong bộ nhớ:** chuyển cây thành danh sách token rồi dựng cây từ danh sách đó.
- **Truyền hoặc lưu trữ:** chuyển danh sách token thành **chuỗi byte**, chẳng hạn JSON UTF-8, có quy tắc cụ thể về kiểu giá trị, mã hóa ký tự và phiên bản định dạng.

Một chuỗi có thể được gọi là “biểu diễn cây” chưa chắc đã là định dạng tuần tự hóa **đầy đủ**. Nếu nó mất thông tin nhánh rỗng, dữ liệu không còn đủ để khôi phục chính xác cây nhị phân bất kỳ.

## 2. Vì sao một thứ tự duyệt thông thường chưa đủ?

Dãy preorder ghi **Gốc – Trái – Phải**, inorder ghi **Trái – Gốc – Phải**, postorder ghi **Trái – Phải – Gốc**. Khi chỉ ghi giá trị của các nút có thật, một dãy không chỉ ra ranh giới giữa những cây con rỗng.

Xét ba cấu trúc:

```text
Cây A                 Cây B                   Cây C

    X                     X                       X
   / \                   /                         \
  Y   Z                 Y                           Y
                                               /
                                              Z
```

Mỗi kiểu duyệt có thể hữu ích để so sánh hoặc dựng cây khi **kết hợp thêm thông tin khác**, nhưng **một dãy duyệt đơn lẻ nhìn chung không đủ** để phục hồi mọi liên kết trái/phải.

Ví dụ tối giản ở đầu bài:

```text
A có con trái B:   preorder = [A, B]
A có con phải B:   preorder = [A, B]
```

Ngay cả khi nhãn `A` và `B` khác nhau, hai cây vẫn có cùng preorder và postorder. Nếu nhãn còn **trùng nhau**, mức nhập nhằng có thể tăng.

### Bài toán của chúng ta khác dựng cây từ hai thứ tự duyệt

Một cách khác để dựng cây là dùng **preorder + inorder** hoặc **postorder + inorder** cùng giả định nhãn phân biệt. Ở bài này, mục tiêu chủ yếu là thiết kế **một định dạng có thể tự mang đủ thông tin**. Ta sẽ thêm các token mô tả chỗ **không có nút**, thay vì yêu cầu hai dãy duyệt độc lập hoặc nhãn duy nhất.

## 3. Thiết kế token rõ nghĩa: nút thật và nhánh rỗng

Để tránh nhầm ký hiệu rỗng với dữ liệu nút, ta dùng hai loại token khác nhau:

| Token | Ý nghĩa | Ví dụ |
|---|---|---|
| `["V", x]` | Một **nút thật**, có giá trị `x` | `["V", 8]`, `["V", "A"]` |
| `["N"]` | Một **cây con rỗng** (`None`) | `["N"]` |

Chữ `V` viết tắt của *value*; chữ `N` viết tắt của *null*. Đây là một **quy ước định dạng minh họa** do bài học chọn, không phải chuẩn bắt buộc cho mọi thư viện.

### Vì sao không dùng một chuỗi "#" đơn lẻ?

Nhiều giáo trình dùng:

```text
A, B, #, #, #
```

trong đó `#` biểu thị nhánh rỗng. Cách ấy hiệu quả nếu **# được dành riêng** và không bao giờ là giá trị hợp lệ của nút. Nhưng nếu giá trị nút thực sự có thể là `"#"` thì phải bổ sung quy tắc thoát ký tự (*escaping*) hoặc một cấu trúc token phân biệt.

Dùng `["V", "#"]` cho nút thật và `["N"]` cho nhánh rỗng sẽ không nhập nhằng:

```text
Nút thật có value = "#":  ["V", "#"]
Cây con rỗng:            ["N"]
Nút thật có value = None: ["V", null]   (khi lưu dưới dạng JSON)
```

Trong danh sách token Python, giá trị rỗng kiểu dữ liệu là `None`; khi chuyển sang JSON, `None` thành `null`. **Một nút có giá trị `None` vẫn khác với việc không có nút**, vì tag `V` khác tag `N`.

### Giới hạn của trường giá trị

Định dạng ví dụ chỉ bảo đảm giữ đúng các giá trị mà bộ mã hóa dữ liệu bên ngoài có thể biểu diễn. Với **JSON**, các kiểu thông dụng là số, chuỗi, Boolean, `null`, danh sách và object có khóa chuỗi; những đối tượng Python tùy ý cần bộ chuyển đổi riêng.

Trong phần mã Python, ta dùng danh sách token có cấu trúc như `["V", 8]` để có thể chuyển sang JSON trực tiếp mà không cần biến tuple thành array.

## 4. Preorder có ký hiệu nhánh rỗng: ý tưởng

**Quy tắc mã hóa DFS preorder:**

1. Nếu đang xét một **nhánh rỗng**, ghi `["N"]` rồi trả về.
2. Nếu đang xét một **nút thật**, ghi `["V", node.value]`.
3. Tiếp tục mã hóa **cây con trái**, rồi **cây con phải**.

Với cây:

```text
            A
           /
          B
```

Ta nhận được:

```text
A có con trái B:

["V","A"], ["V","B"], ["N"], ["N"], ["N"]
    A         B       B.L     B.R     A.R

A có con phải B:

["V","A"], ["N"], ["V","B"], ["N"], ["N"]
    A       A.L        B       B.L     B.R
```

Vị trí token `["N"]` giúp bộ giải mã biết **cây con nào đã kết thúc**, do đó giữ được hình dạng trái/phải.

### Ngữ pháp đệ quy

Gọi `T` là mã của một cây con. Định dạng preorder tuân theo ngữ pháp khái niệm:

```text
T := N
   | V(value) T T
```

Nghĩa là:

- Một cây rỗng có **đúng một** token `N`.
- Một cây không rỗng có một token `V(value)`, tiếp theo là **mã cây trái** và **mã cây phải**.

**Điểm cốt lõi:** khi đọc một token `V`, bộ giải mã biết chính xác phải đọc tiếp **hai cây con**, nên không cần có dấu phân tách giữa chúng.

## 5. Ví dụ mã hóa preorder từng bước

Dùng cây sáu nút:

```text
                    8
                  /   \
                 4     12
                / \      \
               2   6      15
```

Duyệt preorder thông thường chỉ ghi các nút thật:

```text
8, 4, 2, 6, 12, 15
```

Để ghi đủ thông tin cấu trúc, mỗi lần gặp một nhánh rỗng ta thêm token `N`:

```text
V(8)
  V(4)
    V(2)
      N     # 2.left
      N     # 2.right
    V(6)
      N     # 6.left
      N     # 6.right
  V(12)
    N       # 12.left
    V(15)
      N     # 15.left
      N     # 15.right
```

Dãy tuần tự là:

```text
V8, V4, V2, N, N, V6, N, N, V12, N, V15, N, N
```

Hay với kiểu token `["V", value]` và `["N"]`:

```python
pre_tokens = [
    ["V", 8],
    ["V", 4],
    ["V", 2], ["N"], ["N"],
    ["V", 6], ["N"], ["N"],
    ["V", 12], ["N"],
    ["V", 15], ["N"], ["N"],
]
```

| Vị trí | Token | Diễn giải |
|---:|---|---|
| 0 | `V(8)` | Gốc thật `8` |
| 1 | `V(4)` | Con trái của `8` |
| 2 | `V(2)` | Con trái của `4` |
| 3–4 | `N, N` | Hai con rỗng của `2` |
| 5 | `V(6)` | Con phải của `4` |
| 6–7 | `N, N` | Hai con rỗng của `6` |
| 8 | `V(12)` | Con phải của `8` |
| 9 | `N` | Con trái rỗng của `12` |
| 10 | `V(15)` | Con phải của `12` |
| 11–12 | `N, N` | Hai con rỗng của `15` |

Dãy mã hóa dài hơn dãy các nút thật, nhưng **không bỏ sót vị trí con rỗng**. Nhờ vậy, với cùng một bộ giải mã, ta dựng lại được đúng cây ban đầu.

## 6. Bao nhiêu token là đủ?

Một cây nhị phân có `n` nút thật có tổng cộng **`2n` vị trí con** (mỗi nút có hai vị trí `left` và `right`).

Trong một cây có gốc, mỗi nút không phải gốc nối với đúng một cha, nên số liên kết con trỏ **không rỗng** là:

```text
n - 1
```

Số vị trí con **rỗng** vì thế bằng:

```text
2n - (n - 1) = n + 1
```

Do đó, preorder với một token cho mỗi nút thật và một token cho mỗi nhánh rỗng có:

```text
Số token giá trị  = n
Số token rỗng     = n + 1
Tổng số token     = 2n + 1
```

Ví dụ cây sáu nút: `n = 6`, có `7` token rỗng, tổng `13` token. Cây rỗng có `n = 0` và được mã hóa bằng **một token `["N"]`**, cũng phù hợp công thức `2n + 1`.

Đây là số **token**, không phải số **byte**. Số byte phụ thuộc độ dài giá trị nút, cú pháp JSON, Unicode và cách nén.

## 7. Cài đặt Python: tuần tự hóa preorder

Ta định nghĩa nút và hai loại token, rồi mã hóa cây theo DFS:

```python
class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right


def serialize_preorder(root):
    """Trả danh sách token ["V", value] hoặc ["N"]."""
    tokens = []

    def walk(node):
        if node is None:
            tokens.append(["N"])
            return

        tokens.append(["V", node.value])
        walk(node.left)
        walk(node.right)

    walk(root)
    return tokens


root = Node(
    8,
    left=Node(4, Node(2), Node(6)),
    right=Node(12, right=Node(15)),
)

expected_pre = [
    ["V", 8],
    ["V", 4],
    ["V", 2], ["N"], ["N"],
    ["V", 6], ["N"], ["N"],
    ["V", 12], ["N"],
    ["V", 15], ["N"], ["N"],
]

assert serialize_preorder(root) == expected_pre
assert serialize_preorder(None) == [["N"]]
assert serialize_preorder(Node("A")) == [
    ["V", "A"], ["N"], ["N"]
]
```

Một số bất biến của hàm `walk`:

- Mỗi lời gọi mã hóa **đúng một cây con**.
- Nếu là cây rỗng, hàm xuất **một token**.
- Nếu là nút thật, hàm xuất token giá trị và mã đầy đủ của **hai** cây con.
- Cây gốc không bị thay đổi: thuật toán chỉ đọc `value`, `left`, `right`.

**Lưu ý:** ví dụ không xử lý đồ thị có chu trình hay nút được dùng chung giữa nhiều cha. Với các cấu trúc ấy, định dạng cây thông thường có thể mã hóa lặp nút hoặc đệ quy vô hạn. Cần quy ước tham chiếu/ID riêng nếu muốn tuần tự hóa **đồ thị**, không chỉ cây.

## 8. Khôi phục từ preorder: giải mã từng cây con

Bộ giải mã thực hiện **đúng quy tắc ngược lại**:

1. Đọc một token kế tiếp.
2. Nếu là `["N"]`, trả về cây rỗng `None`.
3. Nếu là `["V", x]`, tạo `Node(x)`.
4. Đọc đệ quy **cây trái**, sau đó **cây phải** và gắn vào nút mới.
5. Trả về nút đã gắn đủ hai cây con.

### Vì sao không cần tìm ranh giới trước?

Vì định dạng có token rỗng, mỗi lời gọi `build()` biết khi nào đã **đọc xong đúng một cây con**. Ví dụ:

```text
V(A), V(B), N, N, N
             ^  ^
             hai con của B -> build(B) hoàn tất

Token N cuối cùng thuộc con phải của A.
```

Ta không cần tìm giá trị gốc trong inorder hoặc giả định nhãn nút phân biệt. Điều cần giữ là **con trỏ đọc token tiến theo đúng thứ tự** và mỗi nhánh phải được đọc đầy đủ.

### Hàm kiểm tra và giải mã token

Để không nhầm token sai hình thức với dữ liệu hợp lệ, ta kiểm tra cấu trúc của từng token một cách tường minh.

```python
def _node_from_token(token):
    """Giải một token thành Node hoặc None; từ chối token sai."""
    if not isinstance(token, list):
        raise ValueError("Token phải là một JSON array")

    if len(token) == 1 and token[0] == "N":
        return None

    if len(token) == 2 and token[0] == "V":
        return Node(token[1])

    raise ValueError("Token không đúng định dạng N hoặc V")


def deserialize_preorder(tokens):
    """Khôi phục cây từ dãy preorder đã mã hóa nhánh rỗng."""
    iterator = iter(tokens)
    end = object()

    def build():
        token = next(iterator, end)

        if token is end:
            raise ValueError("Dữ liệu thiếu token cho cây con")

        node = _node_from_token(token)

        if node is None:
            return None

        node.left = build()
        node.right = build()
        return node

    root = build()

    if next(iterator, end) is not end:
        raise ValueError("Dữ liệu có token thừa sau cây hoàn chỉnh")

    return root


def same_tree(a, b):
    """Kiểm tra cùng giá trị và cùng cấu trúc trái/phải."""
    if a is None or b is None:
        return a is b

    return (
        a.value == b.value
        and same_tree(a.left, b.left)
        and same_tree(a.right, b.right)
    )


rebuilt = deserialize_preorder(expected_pre)

assert same_tree(root, rebuilt)
assert serialize_preorder(rebuilt) == expected_pre
assert deserialize_preorder([["N"]]) is None
```

**Bảo đảm quan trọng:** bộ giải mã **không coi thiếu token là nhánh rỗng**. Nếu một nút thật chưa có đủ hai cây con trong luồng dữ liệu, hàm báo `ValueError`. Quy tắc này phát hiện thông điệp bị cắt cụt thay vì tự suy đoán cấu trúc.

Ngược lại, nếu đọc xong một cây rồi vẫn còn token, hàm cũng báo lỗi: dữ liệu thừa không được âm thầm bỏ qua.

## 9. Kiểm thử round-trip và dữ liệu đặc biệt

Một thuộc tính cần có của hệ mã hóa/giải mã là:

```text
deserialize(serialize(T)) ≅ T
```

Ký hiệu `≅` ở đây nghĩa là **tương đương về cấu trúc và giá trị**, không phải là cùng một đối tượng trong RAM. Sau giải mã, các nút là các đối tượng `Node` mới.

### Nút có giá trị None và ký hiệu N/#

Tag phân biệt cho phép lưu các giá trị có vẻ giống ký hiệu rỗng:

```python
special = Node(
    None,
    left=Node("#"),
    right=Node("N"),
)

tokens = serialize_preorder(special)
copy = deserialize_preorder(tokens)

assert same_tree(special, copy)
assert tokens[0] == ["V", None]
assert tokens[1] == ["V", "#"]
assert ["V", "N"] in tokens
assert ["N"] in tokens
```

**Giá trị của nút** là `None` không đồng nghĩa với **không có nút**. Trường hợp không có nút được biểu diễn bằng token loại `N`, còn nút có giá trị `None` là token loại `V`.

### Giá trị trùng nhau vẫn khôi phục đúng hình dạng

```python
repeated = Node(
    7,
    left=Node(7, right=Node(7)),
    right=Node(7),
)

copy = deserialize_preorder(serialize_preorder(repeated))
assert same_tree(repeated, copy)
```

Không cần giá trị nút là duy nhất vì **vị trí của token rỗng đã mô tả cấu trúc**. Đây là khác biệt lớn với cách dựng cây từ một cặp thứ tự duyệt **không** chứa dấu rỗng.

### Phát hiện dữ liệu không hợp lệ

```python
bad_preorders = [
    [],                                      # Thiếu cả token gốc.
    [["V", "A"], ["N"]],                    # Thiếu con phải.
    [["N"], ["V", "A"]],                    # Thừa token.
    [["X", "A"]],                           # Tag lạ.
    [["V"]],                                # Thiếu giá trị.
    [["N", 123]],                           # Token rỗng dư dữ liệu.
    ["V", "A"],                              # Token không phải array.
]

for bad in bad_preorders:
    try:
        deserialize_preorder(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Phải từ chối token không hợp lệ")
```

Mã trên kiểm tra lỗi **hình thức và tính đầy đủ của cấu trúc**. Nếu dữ liệu đến từ nguồn không tin cậy, còn cần các giới hạn về kích thước, độ sâu và kiểu giá trị trước khi cấp phát quá nhiều đối tượng.

## 10. Ghi token thành JSON và đọc lại

Danh sách token ở trên là **cấu trúc dữ liệu Python**. Để lưu trữ hoặc truyền đi, ta cần một cách biến nó thành **văn bản/byte**. JSON là lựa chọn đơn giản vì danh sách token đã chứa list, chuỗi và các giá trị JSON thông dụng.

```python
import json


def tree_to_json(root):
    tokens = serialize_preorder(root)
    return json.dumps(
        tokens,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def tree_from_json(text):
    tokens = json.loads(text)
    if not isinstance(tokens, list):
        raise ValueError("JSON phải chứa danh sách token")
    return deserialize_preorder(tokens)


example = Node(
    "Cây 🌳",
    left=Node(None),
    right=Node("#"),
)

message = tree_to_json(example)
decoded = tree_from_json(message)

assert same_tree(example, decoded)
assert "Cây 🌳" in message
assert '["N"]' in message
```

Điểm cần nhớ:

- `ensure_ascii=False` giữ ký tự Unicode trong chuỗi JSON, thuận tiện khi hiển thị. Khi gửi dưới dạng byte, cần thống nhất **UTF-8**.
- `allow_nan=False` yêu cầu giá trị số thuộc miền JSON chuẩn; `NaN` hoặc vô cực sẽ bị từ chối khi ghi.
- `separators=(",", ":")` bỏ khoảng trắng không cần thiết, nhưng **không thay đổi nội dung logic**.
- `json.loads` khôi phục list/dict/số/chuỗi/Boolean/null theo quy tắc JSON. Nếu `node.value` là một đối tượng Python đặc biệt như ngày giờ, `Decimal` hoặc một instance tùy biến, phải có quy tắc chuyển đổi giá trị riêng.

**Không nên giải mã dữ liệu bên ngoài bằng `eval` hoặc cơ chế tải đối tượng thực thi mã tùy ý.** JSON mô tả dữ liệu; tuy vậy, vẫn cần kiểm tra schema và đặt giới hạn tài nguyên khi nhận thông điệp không tin cậy.

### Thêm phiên bản định dạng khi giao tiếp lâu dài

Một hệ thống thực tế có thể gói danh sách token trong thông điệp có phiên bản:

```json
{
  "format": "binary-tree-preorder",
  "version": 1,
  "tokens": [["V", "A"], ["N"], ["N"]]
}
```

Trường `format` và `version` giúp bên nhận biết cách diễn giải thông điệp trước khi gọi bộ giải mã. Nếu sau này chuyển sang BFS, nén ký hiệu rỗng hoặc đổi kiểu giá trị, cần định nghĩa phiên bản/schema mới hoặc có cơ chế tương thích rõ ràng.

**Ví dụ trên chỉ minh họa hợp đồng thông điệp**; hàm `tree_from_json` trước đó nhận **danh sách token trực tiếp**, chưa nhận object bao `format/version/tokens`. Không nên truyền object này cho hàm rồi kỳ vọng nó tự hiểu.

## 11. Duyệt theo mức: tuần tự hóa bằng queue BFS

Ngoài preorder DFS, ta còn có thể mã hóa cây bằng **duyệt theo mức (level-order)**, sử dụng một queue FIFO:

1. Đưa gốc vào queue.
2. Lấy một phần tử từ đầu queue.
3. Nếu là nhánh rỗng, ghi token `N` và **không sinh con**.
4. Nếu là nút thật, ghi token `V(value)` và thêm lần lượt **con trái**, rồi **con phải** vào queue.
5. Lặp cho tới khi queue rỗng.

Duyệt mức trên cây sáu nút:

```text
                    8
                  /   \
                 4     12
                / \      \
               2   6      15
```

Chuỗi token BFS khi ghi đủ mọi chỗ rỗng là:

```text
V8, V4, V12, V2, V6, N, V15, N, N, N, N, N, N
```

Cùng cây, nhưng dãy khác preorder. **Hai bộ mã hóa không thể tráo bộ giải mã cho nhau** mà vẫn bảo đảm giữ đúng hình dạng.

### Lược bỏ token rỗng ở cuối

Trong thứ tự BFS, nhiều token rỗng thường nằm ở **cuối dãy**, vì chúng tương ứng các con rỗng của những nút cuối cùng.

Ta có thể **cắt tất cả token N liên tiếp ở cuối** và quy định:

> Khi giải mã BFS, nếu dãy đã hết trong lúc đang xét các ô con của những nút còn chờ, những ô **chưa có token** được hiểu là rỗng.

Đây là quy tắc **riêng cho định dạng BFS có hỗ trợ lược bỏ hậu tố rỗng**. Nó **không được áp dụng** cho preorder DFS ở phần trước, nơi mỗi nhánh rỗng bắt buộc có token.

Với ví dụ:

```text
BFS đủ:       V8, V4, V12, V2, V6, N, V15, N, N, N, N, N, N
BFS rút gọn:  V8, V4, V12, V2, V6, N, V15
```

Token `N` ở **giữa dãy** (con trái rỗng của `12`) **không thể xóa**, vì sau nó còn token `V15` ứng với con phải của `12`. Xóa nhầm token rỗng ở giữa sẽ đổi liên kết trái/phải và làm sai hình dạng cây.

## 12. Python: serialize BFS với hậu tố rỗng rút gọn

```python
from collections import deque


def serialize_level_order(root):
    """BFS, giữ các N ở giữa và lược hậu tố N."""
    if root is None:
        return [["N"]]

    result = []
    queue = deque([root])

    while queue:
        node = queue.popleft()

        if node is None:
            result.append(["N"])
            continue

        result.append(["V", node.value])
        queue.append(node.left)
        queue.append(node.right)

    # Các ô con không được biểu diễn ở cuối được hiểu là rỗng.
    while len(result) > 1 and result[-1] == ["N"]:
        result.pop()

    return result


expected_bfs = [
    ["V", 8],
    ["V", 4],
    ["V", 12],
    ["V", 2],
    ["V", 6],
    ["N"],
    ["V", 15],
]

assert serialize_level_order(root) == expected_bfs
assert serialize_level_order(None) == [["N"]]

# Cây chỉ có con phải: token rỗng bên trái phải được giữ.
right_chain = Node("A", right=Node("B", right=Node("C")))
assert serialize_level_order(right_chain) == [
    ["V", "A"], ["N"], ["V", "B"], ["N"], ["V", "C"]
]
```

Ở phần tử `["V", node.value]`, bộ mã hóa thêm hai con **kể cả khi chúng bằng `None`**, bảo đảm các vị trí theo mức được phát biểu chính xác.

Vòng cắt hậu tố chỉ xóa `N` **sau token nút thật cuối cùng**; nó không xóa các token giá trị hoặc các dấu rỗng nằm giữa hai token nút thật.

### Tại sao định dạng BFS rút gọn vẫn không nhập nhằng?

Bộ giải mã lần lượt lấy những **nút cha chưa gắn đủ hai vị trí con** theo thứ tự FIFO. Với mỗi cha, **vị trí trái được đọc trước, vị trí phải đọc sau**.

Các token thực sự có mặt quyết định những vị trí đầu tiên. Khi dãy token kết thúc, **tất cả vị trí còn lại mặc định rỗng**. Vì việc rút gọn chỉ được thực hiện ở cuối, không có nút thật nào bị mất hay bị dịch vị trí.

Điều kiện quan trọng là bộ giải mã phải **tuân đúng quy ước token vắng mặt ở hậu tố**, và phải **từ chối token thừa** nếu đã hết tất cả vị trí con hợp lệ.

## 13. Python: giải mã BFS rút gọn

Bộ giải mã cần một queue chứa các nút thật **đang chờ gắn con**. Với mỗi nút cha, ta đọc tối đa hai token: con trái, rồi con phải.

```python
def deserialize_level_order(tokens):
    """Nhận token BFS; các vị trí thiếu ở cuối được coi rỗng."""
    if not isinstance(tokens, list) or not tokens:
        raise ValueError("Cần một danh sách token không rỗng")

    root = _node_from_token(tokens[0])

    if root is None:
        if len(tokens) != 1:
            raise ValueError("Cây rỗng không được có token thừa")
        return None

    queue = deque([root])
    i = 1

    while queue and i < len(tokens):
        parent = queue.popleft()

        if i < len(tokens):
            left = _node_from_token(tokens[i])
            i += 1
            parent.left = left
            if left is not None:
                queue.append(left)

        if i < len(tokens):
            right = _node_from_token(tokens[i])
            i += 1
            parent.right = right
            if right is not None:
                queue.append(right)

    if i != len(tokens):
        raise ValueError("Có token không thuộc vị trí con hợp lệ")

    # Nếu queue còn cha khi hết token, con còn thiếu là rỗng.
    return root


bfs_copy = deserialize_level_order(expected_bfs)

assert same_tree(root, bfs_copy)
assert serialize_level_order(bfs_copy) == expected_bfs

assert deserialize_level_order([["N"]]) is None
assert same_tree(
    deserialize_level_order([["V", "A"]]),
    Node("A"),
)
assert same_tree(
    deserialize_level_order([
        ["V", "A"], ["N"], ["V", "B"]
    ]),
    Node("A", right=Node("B")),
)
```

Hàm `deserialize_level_order` dùng hàm `_node_from_token` đã định nghĩa ở phần DFS. Vì cùng một loại token, ta có thể **dùng chung quy tắc kiểm tra hình thức token**, dù thứ tự diễn giải chúng là khác nhau.

### Tránh nút mồ côi

Giả sử nhận chuỗi:

```text
V(A), N, N, V(B)
```

Sau `V(A)`, hai token `N, N` cho biết `A` không có con nào. Lúc đó không còn nút cha nào chờ gắn con, nên token `V(B)` còn lại là **mồ côi** (*orphan token*). Bộ giải mã phải từ chối thay vì tự gắn `B` vào một vị trí bất kỳ.

```python
bad_bfs = [
    [],
    [["N"], ["V", "A"]],  # Cây rỗng có dữ liệu thừa.
    [["V", "A"], ["N"], ["N"], ["V", "B"]],
    [["V", "A"], ["unknown"]],
]

for tokens in bad_bfs:
    try:
        deserialize_level_order(tokens)
    except ValueError:
        pass
    else:
        raise AssertionError("Phải báo lỗi dữ liệu BFS sai")
```

Với định dạng **BFS rút gọn**, một dãy kết thúc trước khi liệt kê hết vị trí con có thể vẫn hợp lệ: các vị trí còn lại được coi rỗng. Vì thế, **không thể dùng quy tắc “thiếu token luôn là lỗi” của preorder** cho BFS rút gọn.

## 14. Truy vết giải mã: DFS và BFS khác nhau ở đâu?

### DFS preorder: đọc sâu, hoàn tất một cây con trước

Với:

```text
V(A), V(B), N, N, N
```

Bộ giải mã DFS hoạt động:

| Lượt | Token | Hành động |
|---:|---|---|
| 1 | `V(A)` | Tạo nút `A`, cần dựng trái và phải |
| 2 | `V(B)` | Tạo nút `B`, gắn làm trái của `A` |
| 3 | `N` | `B.left = None` |
| 4 | `N` | `B.right = None`; hoàn tất `B` |
| 5 | `N` | `A.right = None`; hoàn tất `A` |

Hàm đệ quy luôn biết **đang giải mã cây con nào**, vì trạng thái ấy nằm trong call stack.

### BFS: đọc ngang, cha trước con

Với cùng cây, dãy BFS đủ là:

```text
V(A), V(B), N, N, N
```

Dãy rút gọn là:

```text
V(A), V(B)
```

Bộ giải mã BFS lấy `A` khỏi queue cha, gắn `B` vào trái, gắn phải rỗng do hết dãy, rồi xem các ô con của `B` còn lại là rỗng.

**Lưu ý:** trên cây nhỏ này, dãy preorder đủ và BFS đủ tình cờ giống nhau. Điều đó **không có nghĩa hai định dạng tương đương**. Với cây có nhiều nhánh, hai thứ tự và cách suy luận vị trí khác nhau rõ rệt.

### Bảng so sánh

| Tiêu chí | DFS preorder đầy đủ null | BFS theo mức, rút hậu tố null |
|---|---|---|
| Quy tắc duyệt | Nút – trái – phải | Từng mức, từ trái sang phải |
| Cấu trúc điều khiển | Đệ quy hoặc stack | Queue FIFO |
| Có cần đánh dấu nhánh rỗng? | **Tất cả vị trí rỗng** | Giữ rỗng ở giữa; **hậu tố có thể bỏ** |
| Cây rỗng | `[N]` | `[N]` |
| Có thể đọc/khôi phục lần lượt? | Có, đệ quy xử lý token kế tiếp | Có, với queue cha chờ |
| Xử lý nhãn trùng | Được, vì lưu cấu trúc | Được, vì lưu cấu trúc |
| Bộ nhớ điều khiển | O(h) stack | O(w) queue, với w là độ rộng mức lớn nhất |
| Cách phát hiện thiếu token | Thiếu nhánh rỗng là lỗi | Thiếu token **ở cuối** được hiểu rỗng |

Trong bảng, `h` là chiều cao cây và `w` là độ rộng tối đa của một mức. Đối với mã BFS trên, queue có thể chứa cả tham chiếu rỗng lúc mã hóa; số lượng ấy vẫn cùng bậc với độ rộng mức.

## 15. Duyệt DFS không đệ quy trên cây rất sâu

Các hàm DFS đệ quy trực quan, nhưng trên một cây dạng đường thẳng với hàng nghìn hoặc hàng chục nghìn nút, Python có thể ném `RecursionError` vì **giới hạn call stack**. Không nên xem việc tăng giới hạn đệ quy vô điều kiện là giải pháp an toàn cho mọi dữ liệu đầu vào.

Riêng **mã hóa preorder**, ta có thể thay call stack bằng một stack tường minh mà vẫn giữ token null cho mọi vị trí:

```python
def serialize_preorder_iterative(root):
    tokens = []
    stack = [root]

    while stack:
        node = stack.pop()

        if node is None:
            tokens.append(["N"])
            continue

        tokens.append(["V", node.value])

        # Stack LIFO: đẩy phải trước để đi trái trước.
        stack.append(node.right)
        stack.append(node.left)

    return tokens


assert serialize_preorder_iterative(root) == expected_pre
assert serialize_preorder_iterative(None) == [["N"]]
assert serialize_preorder_iterative(right_chain) == serialize_preorder(
    right_chain
)
```

Ở mỗi nút thật, ta ghi token `V` rồi đẩy **phải trước, trái sau**, vì stack LIFO sẽ lấy cây trái trước. Với nhánh rỗng, ta vẫn ghi một token `N`, giữ nguyên ngữ pháp mã hóa preorder.

### Giải mã preorder không đệ quy bằng vị trí con chờ

Một cách tiếp cận là lưu các khung `[node, next_slot]`, trong đó `next_slot` bằng:

- `0`: sắp gắn con trái.
- `1`: sắp gắn con phải.
- `2`: cả hai con đã có kết quả; khung có thể đóng.

Khi đọc token nút thật, gắn nút vào ô con đang chờ rồi đưa một khung mới lên stack. Khi đọc token rỗng, gắn `None` vào ô con đó mà không tạo khung con.

```python
def deserialize_preorder_iterative(tokens):
    iterator = iter(tokens)
    end = object()

    first = next(iterator, end)
    if first is end:
        raise ValueError("Thiếu token gốc")

    root = _node_from_token(first)
    if root is None:
        if next(iterator, end) is not end:
            raise ValueError("Cây rỗng có token thừa")
        return None

    # Mỗi khung: [node, số ô con đã gắn].
    stack = [[root, 0]]

    for token in iterator:
        while stack and stack[-1][1] == 2:
            stack.pop()

        if not stack:
            raise ValueError("Dữ liệu có token thừa")

        child = _node_from_token(token)
        frame = stack[-1]

        if frame[1] == 0:
            frame[0].left = child
        else:
            frame[0].right = child

        frame[1] += 1

        if child is not None:
            stack.append([child, 0])

    while stack and stack[-1][1] == 2:
        stack.pop()

    if stack:
        raise ValueError("Thiếu token nhánh con")

    return root


deep_copy = deserialize_preorder_iterative(expected_pre)
assert same_tree(root, deep_copy)

assert deserialize_preorder_iterative([["N"]]) is None
assert serialize_preorder_iterative(
    deserialize_preorder_iterative(expected_pre)
) == expected_pre
```

Đây là phiên bản giải mã **chặt chẽ**: dù dùng stack tường minh, nó vẫn yêu cầu token cho **từng nhánh rỗng**. Nếu hết dữ liệu mà còn khung có một hoặc hai ô con chưa gắn, hàm báo lỗi.

Không đệ quy giúp tránh một giới hạn của runtime nhưng **không biến thuật toán thành O(1) bộ nhớ**: stack trạng thái vẫn có thể dài tới O(h).

## 16. Độ phức tạp thời gian và bộ nhớ

Gọi `n` là số nút thật của cây, `h` là chiều cao tính theo số nút trên đường dài nhất từ gốc tới lá, `w` là số nút lớn nhất trên một mức.

| Thuật toán | Thời gian | Bộ nhớ điều khiển (không tính cây/token đầu ra) |
|---|---|---|
| Serialize preorder DFS đệ quy | **O(n)** | **O(h)** call stack |
| Deserialize preorder DFS đệ quy | **O(n)** | **O(h)** call stack |
| Serialize preorder DFS lặp | **O(n)** | **O(h)** stack tường minh |
| Deserialize preorder DFS lặp | **O(n)** | **O(h)** stack khung |
| Serialize BFS và cắt hậu tố null | **O(n)** | **O(w)** queue, ngoài dãy token |
| Deserialize BFS rút gọn | **O(n)** | **O(w)** queue |
| Chuyển danh sách token thành JSON | Phụ thuộc **kích thước byte** | Phụ thuộc độ dài văn bản/kiểu giá trị |

**Vì sao O(n)?** Với preorder đầy đủ, có `n` token `V` và `n+1` token `N`, tổng `2n+1 = O(n)`. Mỗi token được đọc hoặc ghi một lần với lượng công việc hằng số (nếu chi phí xử lý giá trị coi là O(1)).

Với BFS đầy đủ, mỗi nút thật tạo hai vị trí con và mỗi vị trí được xử lý không quá một lần; số token cũng tối đa `2n+1`. Việc cắt hậu tố chỉ đi qua những token rỗng cuối, tổng không quá O(n).

### Chi phí thật khi giá trị rất lớn

Nếu một nút chứa chuỗi dài hàng triệu ký tự, mã hóa nó không thể thực sự tốn O(1) tính theo số byte. Mô hình O(n) ở trên thường **coi giá trị mỗi nút có kích thước giới hạn** hoặc tính riêng chi phí chuyển từng giá trị.

Gọi `B` là tổng số byte văn bản JSON được tạo. Ghi/đọc JSON ít nhất phải xử lý O(B) dữ liệu và sử dụng bộ nhớ phù hợp với bộ đệm. Vì vậy khi đánh giá thực tế, nên nêu cả **số nút n** và **kích thước thông điệp B**.

### Bộ nhớ token và cây mới

- Mã hóa tạo danh sách token dài O(n) và cần thêm O(h) hoặc O(w) bộ nhớ điều khiển.
- Giải mã tạo O(n) đối tượng nút mới; nếu đầu vào đã được đọc thành một danh sách token, danh sách ấy cũng chiếm O(n) phần tử.
- Tổng bộ nhớ không gồm cây đầu vào thường là O(n) trong các phiên bản lưu toàn bộ token/cây kết quả.
- Với API kiểu streaming, có thể giảm việc giữ **toàn bộ danh sách token cùng lúc**, nhưng vẫn cần trạng thái DFS/BFS và bộ nhớ cho cây đang dựng.

Đừng dùng kết luận `O(h)` cho call stack để nói “tổng giải mã chỉ tốn O(h) bộ nhớ”: **cây kết quả có n nút** và phải được tính riêng.

## 17. Định dạng rút gọn, khả năng tương thích và rủi ro

### 17.1. Không trộn các quy tắc thiếu token

Đối với **preorder đầy đủ null**:

```text
V(A), N
```

là **không hợp lệ**: cây con phải của `A` chưa có token.

Đối với **BFS rút gọn**:

```text
V(A), N
```

lại **hợp lệ**: `A.left` rỗng được ghi rõ; `A.right` rỗng được hiểu từ việc hết dãy. Cùng token nhưng khác **hợp đồng giải mã**, nên không được tự động hoán đổi bộ giải mã.

### 17.2. Nút rỗng khác nút có giá trị rỗng

Ví dụ:

```text
["N"]            => không có nút
["V", null]      => nút thật có giá trị null
["V", "#"]       => nút thật có chuỗi "#"
["V", "N"]       => nút thật có chuỗi "N"
```

Không nên viết bộ giải mã kiểu `if not value: return None`, vì các giá trị hợp lệ như `0`, `False`, `""` hoặc `None` sẽ bị hiểu sai thành cây rỗng. Bộ giải mã phải xét **tag token**, không suy ra sự tồn tại của nút từ tính truthy/falsy của giá trị.

### 17.3. Giá trị, kiểu và escaping

Nếu thay định dạng có tag bằng chuỗi phân cách:

```text
A,B,#,#,#
```

cần định nghĩa cách thoát dấu phẩy, dấu `#` và ký tự xuống dòng trong giá trị. Một chuỗi giá trị như `"A,B"` không thể chỉ tách bằng dấu phẩy mà vẫn giữ nguyên.

Dùng JSON sẽ giải quyết nhiều vấn đề escape cơ bản cho chuỗi, nhưng **vẫn cần phân biệt token nút và token null** và thống nhất schema giá trị.

### 17.4. Dữ liệu không tin cậy và giới hạn tài nguyên

Một chuỗi token có thể hợp lệ về cú pháp nhưng cực lớn hoặc cực sâu. Khi nhận từ người dùng/dịch vụ bên ngoài, hệ thống nên:

- Giới hạn kích thước thông điệp trước khi phân tích JSON.
- Giới hạn số token và số nút được phép cấp phát.
- Giới hạn độ sâu cây theo hợp đồng, hoặc dùng giải mã lặp thay vì đệ quy.
- Kiểm tra tag, số trường của từng token và kiểu giá trị.
- Từ chối token thừa/thiếu theo đúng quy tắc định dạng.
- Nếu hỗ trợ tham chiếu/ID để mã hóa đồ thị, phải kiểm tra ID và chu trình theo mô hình riêng.

Một định dạng tuần tự hóa **không tự bảo đảm an toàn** cho bộ giải mã. Tính đúng đắn cấu trúc và giới hạn tài nguyên là hai vấn đề phải giải quyết song song.

## 18. Bất biến và chứng minh khả năng khôi phục

### 18.1. Preorder đầy đủ: quy nạp theo cây con

Xét thuộc tính:

> `deserialize_preorder(serialize_preorder(T))` tạo một cây **cùng cấu trúc và giá trị** với `T`.

**Cơ sở:** nếu `T` rỗng, bộ mã hóa ghi `["N"]`. Bộ giải mã đọc token ấy và trả `None`. Vậy thuộc tính đúng.

**Bước quy nạp:** giả sử thuộc tính đúng cho hai cây con `L` và `R`. Với cây có gốc `N` và giá trị `x`, bộ mã hóa tạo:

```text
V(x) + encode(L) + encode(R)
```

Bộ giải mã đọc `V(x)`, tạo nút mang giá trị `x` rồi đọc đúng một cây con từ dãy tiếp theo. Theo giả thiết quy nạp, nó dựng đúng `L`; sau khi `L` kết thúc, tiếp tục dựng đúng `R`. Ghép hai kết quả dưới gốc `x` cho cây tương đương `T`.

**Vì sao không nhập nhằng?** Ngữ pháp `T := N | V(value) T T` buộc mỗi lời gọi giải mã xác định đúng điểm kết thúc cây con mà không cần biết trước số nút trong cây ấy.

### 18.2. BFS rút gọn: bất biến queue cha

Sau khi xử lý k vị trí con đầu tiên theo thứ tự BFS, queue chứa chính xác các **nút thật đã tạo nhưng chưa gắn hết những vị trí con còn cần xét**. Hai vị trí của mỗi cha được đọc theo thứ tự trái rồi phải.

Mỗi token `V` tạo một nút và gắn nó vào đúng vị trí sắp tới, sau đó nút ấy được đưa vào queue để chờ xử lý các con của nó. Token `N` gắn một vị trí rỗng và không sinh nút cha mới.

Khi dãy kết thúc, các vị trí chưa liệt kê thuộc **hậu tố vị trí rỗng** theo quy ước mã hóa, nên giữ `None` là chính xác. Do vậy bộ giải mã khôi phục đúng liên kết trái/phải. Nếu vẫn còn token mà queue đã hết cha hợp lệ, dữ liệu có phần dư và phải bị từ chối.

### 18.3. Kiểm thử hai chiều

Có hai tính chất nên kiểm tra:

```text
Tính chất 1: decode(encode(tree)) ≅ tree

Tính chất 2: encode(decode(tokens)) == tokens
             (nếu tokens ở dạng chuẩn/canonical)
```

Với preorder đầy đủ, dãy hợp lệ không có token thừa hoặc thiếu nên thường có một biểu diễn chuẩn.

Với BFS rút gọn, một dãy hợp lệ có thể chứa **các token N cuối không cần thiết**. Giải mã rồi mã hóa lại sẽ **cắt bớt hậu tố ấy**, nên tính chất 2 chỉ chắc chắn đúng nếu đầu vào **đã ở dạng rút gọn chuẩn**.

## 19. Tự luyện có đáp án

**Bài 1 — Phân biệt nhánh.** Hai cây `A` có một con `B`, một cây đặt bên trái, cây còn lại đặt bên phải. Preorder chỉ ghi nhãn có phân biệt được không?

*Lời giải:* **Không.** Cả hai cùng là `[A,B]`. Nếu dùng token null, cây con trái có `V(A),V(B),N,N,N`, còn cây con phải có `V(A),N,V(B),N,N`.

**Bài 2 — Đếm token.** Cây nhị phân có `n=10` nút thật. Preorder đầy đủ token rỗng có bao nhiêu token giá trị, token rỗng và tổng token?

*Lời giải:* Có **10** token giá trị, **11** token rỗng, tổng **21** token.

**Bài 3 — Cây rỗng.** Theo định dạng của bài, cây rỗng được mã hóa thành gì? Tại sao không dùng dãy rỗng?

*Lời giải:* `[["N"]]`. Một token N mô tả rõ “cây gốc rỗng”; dãy rỗng bị coi là **dữ liệu thiếu**, giúp phát hiện thông điệp bị cắt cụt.

**Bài 4 — Giá trị None.** Một nút lá mang giá trị Python `None` được mã hóa preorder như thế nào?

*Lời giải:* `[["V", None], ["N"], ["N"]]` trong Python, tương ứng `[["V", null], ["N"], ["N"]]` trong JSON. Nó khác cây rỗng `[["N"]]`.

**Bài 5 — Giải mã preorder.** Dãy `V(A),V(B),N,N,N` khôi phục thành cây nào?

*Lời giải:* Nút `A` có **con trái `B`**, con phải rỗng; `B` là lá.

**Bài 6 — Dãy sai.** Dãy `V(A),N` có phải biểu diễn preorder đầy đủ hợp lệ không?

*Lời giải:* **Không.** `A` đã có nhánh trái rỗng nhưng thiếu token của nhánh phải. Bộ giải mã phải báo lỗi.

**Bài 7 — BFS rút gọn.** Cây `A` có con phải `B`, không có con trái, và `B` là lá. Dãy BFS rút gọn là gì?

*Lời giải:* `V(A),N,V(B)`. Token N ở giữa bắt buộc có để chỉ ra `B` là **con phải**, còn các token N ở cuối có thể bỏ.

**Bài 8 — Không xóa null giữa dãy.** Vì sao không thể chuyển `V(A),N,V(B)` thành `V(A),V(B)` trong BFS?

*Lời giải:* Không còn token N ở vị trí con trái, bộ giải mã sẽ gắn `B` làm **con trái của A**, thay đổi hình dạng cây.

**Bài 9 — Hai thứ tự có thể tráo bộ giải mã?** Có thể lấy dãy preorder đầy đủ rồi luôn giải mã bằng bộ giải mã BFS không?

*Lời giải:* **Không.** Hai định dạng xác định thứ tự vị trí con khác nhau. Một số cây nhỏ tình cờ cho dãy tương tự, nhưng không có bảo đảm cho mọi cây.

**Bài 10 — Round-trip.** Vì sao `same_tree(root, decoded)` nên so sánh **cả nhánh trái lẫn nhánh phải**, không chỉ danh sách giá trị preorder?

*Lời giải:* Hai cây khác hình dạng có thể cho cùng preorder nếu bỏ token rỗng. Tính đúng của khôi phục yêu cầu tương đương **cả cấu trúc và giá trị**.

**Bài 11 — Nhãn trùng.** Ba nút đều mang giá trị `7` có làm định dạng preorder kèm dấu rỗng trở nên nhập nhằng không?

*Lời giải:* **Không.** Mỗi vị trí con rỗng được đánh dấu rõ, nên hai cây khác cấu trúc tạo dãy token khác nhau dù nhãn lặp.

**Bài 12 — Cây sâu.** Mã hóa/giải mã DFS đệ quy trên một cây dạng đường rất dài có vấn đề nào trong Python?

*Lời giải:* Có thể vượt giới hạn độ sâu gọi hàm và phát sinh **`RecursionError`**. Cách lặp với stack tường minh tránh phụ thuộc vào độ sâu gọi hàm DFS, nhưng vẫn có chi phí bộ nhớ.

**Bài 13 — Bộ nhớ BFS.** Đối với cây nhị phân có độ rộng mức lớn nhất là `w`, queue dùng trong tuần tự hóa BFS cần bộ nhớ điều khiển cỡ nào?

*Lời giải:* **O(w)**, chưa tính dãy token O(n). Queue có thể tạm chứa cả các vị trí rỗng nhưng vẫn cùng bậc với độ rộng mức của nút thật.

**Bài 14 — Dữ liệu thừa.** Bộ giải mã preorder đọc `N` đầu tiên, nhưng còn token `V(X)` phía sau. Nên làm gì?

*Lời giải:* **Báo lỗi**. Token N đầu đã biểu diễn toàn bộ cây rỗng; phần tử còn lại không thuộc cây nào.

**Bài 15 — Định dạng có phiên bản.** Vì sao khi gửi cây qua mạng nên có thông tin `format` và `version`?

*Lời giải:* Bên nhận phải biết đang dùng **preorder đầy đủ null**, **BFS rút gọn** hay biến thể khác, và xác định schema giá trị. Phiên bản giúp tránh giải mã nhầm khi quy tắc thay đổi.

**Bài 16 — Giới hạn tài nguyên.** Một JSON có cú pháp đúng nhưng chứa hàng triệu token và cây cực sâu có tự động an toàn để giải mã không?

*Lời giải:* **Không.** Cần giới hạn kích thước, số nút và độ sâu, đồng thời chọn cách giải mã phù hợp; tính hợp lệ cú pháp không thay thế việc kiểm soát tài nguyên.

## 20. Tổng kết

**Tuần tự hóa cây** phải bảo toàn **giá trị và hình dạng**, không chỉ thứ tự những nút thật được duyệt. Trong định dạng **DFS preorder**, ghi `V(value)` cho một nút và `N` cho mọi cây con rỗng giúp bộ giải mã nhận biết đúng điểm kết thúc từng cây con. Một cây có `n` nút thật cần **`2n+1` token**, đủ để khôi phục chính xác cả khi các giá trị trùng nhau.

Trong định dạng **BFS theo mức**, queue giữ các nút cha đang chờ gắn con; ta có thể **lược hậu tố token rỗng** nếu bộ giải mã thống nhất rằng các vị trí còn thiếu ở **cuối** là rỗng. Không được bỏ các token rỗng **ở giữa** dãy hoặc áp dụng quy ước này cho preorder đầy đủ.

Với mỗi cách, hãy định nghĩa rõ **schema token, thứ tự trái/phải, chính sách thiếu/thừa dữ liệu và giới hạn tài nguyên**. Thuật toán mã hóa/khôi phục dùng **O(n) thời gian theo số nút** khi giá trị nút có chi phí xử lý hằng số, đồng thời dùng O(h) stack DFS hoặc O(w) queue BFS cho điều khiển; bộ nhớ token và cây kết quả thường là O(n). Quan trọng nhất là kiểm tra tính chất **giải mã sau mã hóa giữ nguyên cấu trúc và giá trị**, chứ không chỉ kiểm tra một dãy nhãn đơn giản.
