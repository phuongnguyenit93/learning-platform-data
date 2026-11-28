# Biểu diễn cây bằng dãy ngoặc cân bằng

Một cây có gốc thường được lưu bằng những nút liên kết: mỗi nút biết con hoặc danh sách các con của nó, còn mỗi liên kết có thể cần một con trỏ hay chỉ số. Cách này dễ chỉnh sửa, nhưng khi cây có hàng triệu nút và **chủ yếu chỉ đọc**, bộ nhớ dành cho các liên kết và cấu trúc quản lý đôi khi lớn hơn nhiều so với thông tin về **hình dạng cây**.

Với **cây có gốc và thứ tự các con xác định** (rooted ordered tree), có một cách biểu diễn rất gọn: duyệt sâu từ gốc, ghi dấu `(` khi **bước vào** mỗi nút và dấu `)` khi **rời khỏi** nút ấy. Kết quả là một **dãy ngoặc cân bằng** (balanced-parentheses sequence, viết tắt **BP**) có đúng **2n dấu ngoặc cho n nút**.

Ví dụ, hình dạng cây:

```text
A
├── B
│   ├── E
│   └── F
├── C
└── D
    └── G
```

có thể lưu bằng chuỗi:

```text
((()())()(()))
```

Chỉ từ chuỗi này và quy tắc mã hóa, ta khôi phục được **quan hệ cha–con, thứ tự anh em, cây con và thứ tự duyệt**. Khi bổ sung những **chỉ mục phụ** thích hợp cho ngoặc, rank/select và tổng độ sâu, một số thao tác điều hướng còn có thể được hỗ trợ rất nhanh mà không cần lưu mỗi liên kết như một con trỏ riêng.

Đây là bài **“Biểu diễn cây bằng dãy ngoặc cân bằng”** thuộc chương **Biểu diễn gọn**, trong học phần **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mục tiêu của học phần là hiểu cấu trúc dữ liệu qua bất biến, thao tác và độ phức tạp thời gian/bộ nhớ; bài này tập trung cách đổi một cây động về một **mô tả topology tĩnh gọn**, đồng thời phân tích thận trọng những gì được tiết kiệm và những gì phải trả thêm để truy vấn.

## 1. Mục tiêu học tập và phạm vi

Sau bài, bạn có thể:

1. Phân biệt **cây có gốc có thứ tự các con** với cây không có thứ tự và rừng.
2. Mã hóa cây thành dãy ngoặc cân bằng bằng **DFS vào/ra nút**.
3. Kiểm tra những bất biến của dãy BP, kể cả điều kiện **chỉ có một gốc**.
4. Giải mã BP để khôi phục cây, đồng thời chứng minh tính **đơn trị** của phép mã hóa.
5. Ánh xạ mỗi nút sang vị trí **ngoặc mở** của nó.
6. Tính ngoặc đóng tương ứng, cha, con đầu, anh em kế và kích thước cây con.
7. Dùng **excess**, rank và select để hiểu độ sâu, thứ tự preorder/postorder.
8. Phân biệt truy vấn quét trực tiếp, mảng chỉ mục `O(n)` và cấu trúc succinct `2n+o(n)` bit.
9. Hiểu ý nghĩa chặn thông tin theo **số Catalan** cho cây có gốc có thứ tự.
10. Cài đặt bộ mã hóa/giải mã, truy vấn và kiểm thử trong Python, C++17.
11. Nhận biết các giới hạn khi cây có nhãn, cập nhật động, truy cập ngẫu nhiên hoặc giữ ID ổn định.

**Phạm vi:** ta biểu diễn **hình dạng (topology)** của một cây có gốc, mỗi nút có **danh sách con theo thứ tự cố định**. Dữ liệu/nhãn gắn trên nút được xét riêng. Không được suy rằng 2n bit đủ lưu cả các nhãn, trọng số, khóa hay thông tin ứng dụng.

## 2. Cây có gốc và thứ tự các con là gì?

Một cây có gốc gồm n nút, n−1 cạnh (với `n\ge1`), có một nút gốc. Mỗi nút trừ gốc có đúng một cha, và không có chu trình.

Trong **cây có thứ tự các con**, nếu nút A có ba con B, C, D thì thứ tự:

```text
[B, C, D]
```

khác với:

```text
[D, C, B]
```

về mặt biểu diễn, dù tập cạnh có thể giống nhau khi không quan tâm thứ tự. Thứ tự các con quyết định trình tự DFS, nên cũng quyết định chuỗi BP.

### Các khái niệm

- **Root:** nút không có cha.
- **Parent:** nút liền trước trên đường từ một nút tới gốc.
- **Child:** nút nằm ngay dưới một nút cha.
- **Sibling:** các nút có cùng cha, sắp từ trái sang phải.
- **Leaf:** nút không có con.
- **Subtree rooted at v:** nút v và toàn bộ hậu duệ của v.
- **Depth:** số cạnh từ gốc tới nút; gốc có độ sâu 0.
- **Preorder:** thăm nút trước rồi duyệt các cây con từ trái sang phải.
- **Postorder:** duyệt các cây con trước rồi mới thăm nút.

### Vì sao đây không chỉ là cây nhị phân?

Cây BP có thể có **bất kỳ số con nào**, kể cả 0, 1, 2, 10 hay nhiều hơn. Với cây nhị phân, “con trái” và “con phải” có ý nghĩa riêng, đặc biệt khi một phía bị thiếu. Nếu chỉ lưu danh sách các con hiện có bằng BP, phải có thêm quy ước hoặc bit bổ sung để biết một con duy nhất là **trái hay phải**.

Do đó BP tiêu chuẩn cho **cây có gốc có thứ tự** không tự bảo toàn mọi chi tiết của cấu trúc cây nhị phân có các vị trí con phân biệt.

## 3. Quy tắc mã hóa BP bằng DFS

Cho nút v có các con `c_1,c_2,\ldots,c_k` theo đúng thứ tự:

1. Ghi `(` khi bước vào v.
2. Mã hóa lần lượt cây con của `c_1,c_2,\ldots,c_k`.
3. Ghi `)` khi rời v.

Viết bằng công thức đệ quy:

\[
\boxed{
BP(v)=
(\;\,BP(c_1)\,BP(c_2)\cdots BP(c_k)\;\,)
}
\]

Trong đó dấu `(` và `)` ngoài cùng thuộc về **nút v**.

### Trường hợp lá

Nếu v không có con, không có dãy con ở giữa:

```text
BP(v) = ()
```

Vậy **mỗi nút lá có mẫu `()`**, nhưng việc thấy `()` ở một vị trí không nhất thiết nói gì về các anh em khác.

### Giả mã

```text
encode(v):
    output '('
    for child in children[v] theo đúng thứ tự:
        encode(child)
    output ')'
```

Nếu cây có n nút, mỗi nút sinh đúng **một ngoặc mở và một ngoặc đóng**. Độ dài kết quả:

\[
\boxed{|BP|=2n.}
\]

Về thời gian, duyệt n nút và n−1 cạnh hết `O(n)`, chưa tính chi phí xuất kết quả không phù hợp (ví dụ nối chuỗi bất biến lặp nhiều lần). Thực tế nên tích lũy ký tự trong buffer rồi ghép một lần.

## 4. Truy vết một cây bảy nút

Dùng cây:

```text
A
├── B
│   ├── E
│   └── F
├── C
└── D
    └── G
```

Duyệt từ A:

```text
Vào A: (
  Vào B: (
    Vào E: (
    Ra E:  )
    Vào F: (
    Ra F:  )
  Ra B:   )
  Vào C:  (
  Ra C:   )
  Vào D:  (
    Vào G: (
    Ra G:  )
  Ra D:   )
Ra A:     )
```

Ghép mọi dấu theo thứ tự:

```text
((()())()(()))
```

### Đánh chỉ số cho mọi dấu ngoặc

```text
Chỉ số:  0  1  2  3  4  5  6  7  8  9 10 11 12 13
BP:      (  (  (  )  (  )  )  (  )  (  (  )  )  )
Nút mở:  A  B  E  -  F  -  -  C  -  D  G  -  -  -
Nút đóng:-  -  -  E  -  F  B  -  C  -  -  G  D  A
```

Bảng ghép ngoặc:

| Nút | Ngoặc mở p | Ngoặc đóng q | Độ sâu | Số nút trong cây con |
|---|---:|---:|---:|---:|
| A | 0 | 13 | 0 | 7 |
| B | 1 | 6 | 1 | 3 |
| E | 2 | 3 | 2 | 1 |
| F | 4 | 5 | 2 | 1 |
| C | 7 | 8 | 1 | 1 |
| D | 9 | 12 | 1 | 2 |
| G | 10 | 11 | 2 | 1 |

Thứ tự các ngoặc **mở** là preorder:

```text
A, B, E, F, C, D, G
```

Thứ tự các ngoặc **đóng** là postorder:

```text
E, F, B, C, G, D, A
```

Đây chính là lý do vị trí ngoặc có thể trở thành **định danh hình dạng** cho từng nút mà không cần trỏ tới một đối tượng nút riêng biệt.

## 5. Bất biến dãy ngoặc cân bằng

Ta đặt:

\[
E(i)=
\#\text{ngoặc mở trong }BP[0:i]
-\#\text{ngoặc đóng trong }BP[0:i].
\]

`E(i)` gọi là **excess** hay **độ dư ngoặc**, và `BP[0:i]` là tiền tố nửa mở dài i.

Với một dãy ngoặc cân bằng:

\[
E(0)=0,\qquad E(2n)=0,
\]

và:

\[
E(i)\ge0\quad\text{với mọi }0\le i\le2n.
\]

### Đối với một cây có đúng một gốc

Mã BP của một cây có gốc không rỗng có **một cặp ngoặc ngoài cùng** bao toàn bộ chuỗi. Vì vậy còn có điều kiện mạnh hơn:

\[
\boxed{
E(i)>0\quad\text{với }1\le i<2n.
}
\]

Đó là một **dãy ngoặc cân bằng nguyên thủy**: excess chỉ về 0 **tại vị trí cuối**.

### Ví dụ sai và đúng

| Chuỗi | Trạng thái | Giải thích |
|---|---|---|
| `()` | Một cây một nút | Hợp lệ |
| `(())` | Một gốc, một con | Hợp lệ |
| `(()())` | Một gốc, hai con lá | Hợp lệ |
| `()()` | Hai cây đơn, không phải một gốc | Dãy cân bằng nhưng là một **rừng** |
| `)(` | Không cân bằng | Prefix đầu âm |
| `(()` | Không cân bằng | Còn ngoặc mở |
| `())(` | Không cân bằng | Prefix âm và chia thành nhiều đoạn |
| `((()))` | Một đường gồm ba nút | Có ba cặp ngoặc lồng nhau |

Nếu bài toán yêu cầu **một cây duy nhất**, không được chấp nhận `()()` chỉ vì số ngoặc mở bằng số ngoặc đóng.

## 6. Excess có liên hệ gì với ngăn xếp DFS?

Khi đọc chuỗi từ trái sang phải:

- Gặp `(`: đẩy nút mới lên ngăn xếp; `E` tăng 1.
- Gặp `)`: kết thúc nút ở đỉnh ngăn xếp; `E` giảm 1.

Do đó sau khi đọc i ký tự, `E(i)` chính là **số nút đang mở nhưng chưa đóng**.

Với cây ví dụ:

| i | Ký tự vừa đọc tại i−1 | E(i) |
|---:|---|---:|
| 0 | Chưa đọc | 0 |
| 1 | `(` của A | 1 |
| 2 | `(` của B | 2 |
| 3 | `(` của E | 3 |
| 4 | `)` của E | 2 |
| 5 | `(` của F | 3 |
| 6 | `)` của F | 2 |
| 7 | `)` của B | 1 |
| 8 | `(` của C | 2 |
| 9 | `)` của C | 1 |
| 10 | `(` của D | 2 |
| 11 | `(` của G | 3 |
| 12 | `)` của G | 2 |
| 13 | `)` của D | 1 |
| 14 | `)` của A | 0 |

Bảng này giúp vừa **kiểm tra chuỗi**, vừa trả lời các truy vấn về **độ sâu** mà không cần một mảng độ sâu cho mỗi nút, nếu đã có phương tiện tính excess nhanh.

## 7. Kiểm tra một chuỗi BP hợp lệ

Một bộ kiểm tra cho cây một gốc cần xác nhận:

1. Chuỗi không rỗng.
2. Mọi ký tự đều là `(` hoặc `)`.
3. Độ dài chẵn.
4. Mọi prefix có excess không âm.
5. Excess cuối bằng 0.
6. **Không có prefix nội bộ** nào có excess bằng 0.

### Python: bộ xác thực cơ bản

```python
def validate_bp_tree(bp: str) -> int:
    if not isinstance(bp, str):
        raise TypeError("BP phải là chuỗi")
    if not bp or len(bp) % 2:
        raise ValueError("Cây một gốc phải có 2n ký tự, n >= 1")

    excess = 0
    for i, char in enumerate(bp):
        if char == "(":
            excess += 1
        elif char == ")":
            excess -= 1
        else:
            raise ValueError("Chỉ cho phép '(' và ')'")

        if excess < 0:
            raise ValueError("Ngoặc đóng không có ngoặc mở")
        if excess == 0 and i != len(bp) - 1:
            raise ValueError("Chuỗi mô tả rừng, không phải một cây")

    if excess != 0:
        raise ValueError("Ngoặc mở chưa được đóng")

    return len(bp) // 2


assert validate_bp_tree("()") == 1
assert validate_bp_tree("(())") == 2
assert validate_bp_tree("((()())()(()))") == 7

for wrong in ["", "(", ")(", "()()", "(()", "(x)"]:
    try:
        validate_bp_tree(wrong)
    except ValueError:
        pass
    else:
        raise AssertionError("Đã chấp nhận BP không hợp lệ")
```

Độ phức tạp: `O(n)` thời gian với `2n` ký tự và `O(1)` biến đếm bổ sung. Không cần dựng cả cây chỉ để xác thực hình dạng.

## 8. Vì sao phép mã hóa có thể giải ngược?

Từ BP hợp lệ, khi đọc:

- Mỗi `(` tạo **một nút mới**.
- Nếu ngăn xếp đang có nút, nút mới là **con tiếp theo của nút ở đỉnh**.
- Đẩy nút mới lên ngăn xếp.
- Mỗi `)` kết thúc đúng **nút ở đỉnh** và lấy nó ra.

Vì các con được gặp từ trái sang phải, **thứ tự con được khôi phục đúng**.

### Chứng minh tính đơn trị

Xét một BP hợp lệ. Mỗi ký tự `(` tạo một nút có vị trí mở xác định. Tại thời điểm đó, ngăn xếp chứa chính các tổ tiên chưa đóng của nút mới, nên cha duy nhất của nó là đỉnh ngăn xếp (nếu có). Mỗi ký tự `)` chỉ có thể đóng nút đang mở gần nhất; nếu đóng nút khác sẽ phá cấu trúc lồng ngoặc.

Như vậy mọi nút, cạnh cha–con và thứ tự xuất hiện của các con đều được xác định duy nhất. Mã hóa lại cây vừa dựng sẽ cho **đúng chuỗi BP ban đầu**.

**Nhưng:** điều đó đúng cho **hình dạng cây có thứ tự**, không bao gồm nhãn A/B/C hoặc ID ban đầu. Những nhãn đó phải được lưu hoặc thỏa một quy ước ánh xạ riêng.

## 9. Dùng vị trí ngoặc mở làm định danh nút

Trong chuỗi BP:

```text
((()())()(()))
```

các vị trí ngoặc mở lần lượt:

```text
[0, 1, 2, 4, 7, 9, 10]
```

Đây là các vị trí của nút theo preorder:

```text
preorder index: 0  1  2  3  4  5  6
node:           A  B  E  F  C  D  G
open position:  0  1  2  4  7  9 10
```

Một API có thể biểu diễn nút bằng **vị trí mở p** thay vì một con trỏ.

### Những ưu điểm

- p xác định một nút duy nhất trong BP hiện tại.
- Đoạn BP của cây con là một **khoảng liên tiếp**.
- Chỉ số preorder có thể được tính từ rank trên ngoặc mở.
- Có thể lưu nhãn trong một mảng **theo thứ tự preorder**.

### Điều phải lưu ý

Vị trí mở p **không phải ID ổn định khi chỉnh sửa cây**. Chèn thêm một nút trước p có thể dịch toàn bộ vị trí ngoặc phía sau. Nếu hệ thống yêu cầu ID bền vững qua nhiều lần thay đổi, cần một lớp ánh xạ hoặc cấu trúc khác.

## 10. Tìm ngoặc đóng tương ứng: findClose

Với nút có ngoặc mở ở p, gọi `close(p)` là vị trí ngoặc đóng khớp với nó.

Định nghĩa bằng excess:

\[
\boxed{
close(p)
=\min\{q>p:\ BP[q]=\texttt{')'},\ E(q+1)=E(p)\}.
}
\]

Tại vị trí p, E(p) bằng số tổ tiên đang mở. Sau khi đọc ngoặc `(` tại p, excess tăng thêm 1; chỉ khi đóng đúng nút ấy, excess mới trở lại mức E(p) lần đầu.

### Ví dụ

Với BP ví dụ:

```text
close(A ở 0) = 13
close(B ở 1) = 6
close(E ở 2) = 3
close(F ở 4) = 5
close(C ở 7) = 8
close(D ở 9) = 12
close(G ở 10) = 11
```

### Thuật toán quét không cần chỉ mục

```python
def find_close_slow(bp: str, open_pos: int) -> int:
    if (
        type(open_pos) is not int
        or open_pos < 0
        or open_pos >= len(bp)
        or bp[open_pos] != "("
    ):
        raise ValueError("Phải truyền vị trí ngoặc mở")

    level = 0
    for i in range(open_pos, len(bp)):
        level += 1 if bp[i] == "(" else -1
        if level == 0:
            return i

    raise ValueError("Chuỗi không cân bằng")


assert find_close_slow("((()())()(()))", 1) == 6
assert find_close_slow("((()())()(()))", 9) == 12
```

Độ phức tạp quét `O(|subtree|)` theo số dấu ngoặc của cây con, worst-case `O(n)`. Nếu muốn `findClose` nhanh thường xuyên, cần **mảng ghép ngoặc** hoặc **chỉ mục phụ trên excess**.

## 11. Tìm ngoặc mở tương ứng: findOpen

Với một ngoặc đóng ở q, ký hiệu `open(q)` là vị trí ngoặc mở ghép với nó.

Có thể quét từ q về trái bằng bộ đếm:

```python
def find_open_slow(bp: str, close_pos: int) -> int:
    if (
        type(close_pos) is not int
        or close_pos < 0
        or close_pos >= len(bp)
        or bp[close_pos] != ")"
    ):
        raise ValueError("Phải truyền vị trí ngoặc đóng")

    level = 0
    for i in range(close_pos, -1, -1):
        level += 1 if bp[i] == ")" else -1
        if level == 0:
            return i

    raise ValueError("Chuỗi không cân bằng")


assert find_open_slow("((()())()(()))", 6) == 1
assert find_open_slow("((()())()(()))", 13) == 0
```

Thuật toán là phép đối xứng của `findClose`, cũng có thể tốn `O(n)` khi không có chỉ mục.

### Ghép ngoặc bằng ngăn xếp một lần

Nếu chấp nhận dùng thêm `O(n)` phần tử chỉ mục, ta có thể quét một lượt và lưu:

```text
match[p] = q
match[q] = p
```

cho mỗi cặp ngoặc tương ứng. Sau đó `findClose` và `findOpen` đều là `O(1)` bằng truy cập mảng. Đây là ví dụ **dễ cài**, nhưng mảng chỉ số rộng có thể chiếm nhiều bộ nhớ hơn chính BP.

## 12. Tìm nút cha từ cấu trúc ngoặc

Trong quá trình quét BP, khi gặp một ngoặc mở của nút v:

- Nếu ngăn xếp chưa rỗng, **đỉnh ngăn xếp** là cha của v.
- Nếu ngăn xếp rỗng, v là gốc.

Ví dụ:

```text
Mở B tại 1: stack trước đó = [A]       → parent(B)=A
Mở E tại 2: stack trước đó = [A,B]     → parent(E)=B
Mở C tại 7: stack trước đó = [A]       → parent(C)=A
Mở G tại 10: stack trước đó = [A,D]    → parent(G)=D
```

Khi dựng chỉ mục, có thể lưu `parent[open_pos]` cho mỗi nút để truy vấn O(1).

### Có nhất thiết lưu cả mảng parent không?

Không. Trong biểu diễn succinct, thao tác **enclose** có thể tìm cặp ngoặc mở bao ngoài gần nhất bằng chỉ mục trên BP/excess. `parent(v)` chính là vị trí mở của cặp bao ngoài đó.

Nhưng nếu chỉ có **chuỗi BP thô**, tìm cha bằng quét ngược hoặc ghép ngoặc phụ có thể tốn O(n). Không được nói “BP tự nhiên cho parent O(1)” nếu chưa nêu loại chỉ mục hỗ trợ.

### Gốc có cha không?

Không. API nên trả `None`, sentinel được quy định, hoặc ném một lỗi thích hợp. Không nên cho gốc làm cha của chính nó nếu định nghĩa cây của bài yêu cầu root không có cha.

## 13. Con đầu tiên và anh em kế tiếp

Với một nút v có ngoặc mở p và ngoặc đóng q:

### Con đầu tiên

Nếu ký tự ngay sau ngoặc mở là một ngoặc mở khác:

```text
BP[p+1] == '('
```

thì nút ở vị trí p+1 là **con đầu tiên**.

Ngược lại, nếu `BP[p+1]=')'`, v là lá và không có con.

Vì cây BP hợp lệ, quy tắc này rất đơn giản:

\[
firstChild(p)=
\begin{cases}
p+1,&p+1<close(p),\\
\text{không có},&\text{ngược lại}.
\end{cases}
\]

### Anh em kế tiếp

Giả sử v không phải gốc, có cha u. Sau khi kết thúc toàn bộ cây con của v ở `close(v)`, nếu còn dấu ngoặc mở nằm **trước ngoặc đóng của u**, đó là anh em kế tiếp:

\[
nextSibling(v)=
\begin{cases}
close(v)+1,&close(v)+1<close(parent(v)),\\
\text{không có},&\text{ngược lại}.
\end{cases}
\]

Ví dụ:

```text
firstChild(A) = B (open 1)
firstChild(B) = E (open 2)
firstChild(C) = không có

nextSibling(E) = F (open 4)
nextSibling(F) = không có
nextSibling(B) = C (open 7)
nextSibling(C) = D (open 9)
nextSibling(D) = không có
```

Hai công thức dùng **vị trí cặp ngoặc** nên rất thuận tiện nếu `findClose` và `parent` đã nhanh.

## 14. Một cây con tương ứng với một đoạn liên tiếp

Nếu nút v có ngoặc mở p và ngoặc đóng q, toàn bộ subtree của v được mã hóa đúng bởi:

\[
\boxed{BP[p:q+1]}.
\]

Đoạn này **không chứa nút nào ngoài cây con v**, và chứa mỗi nút của subtree đúng một cặp ngoặc.

Vì vậy:

\[
q-p+1=2\,subtreeSize(v).
\]

Suy ra:

\[
\boxed{
subtreeSize(v)=\frac{close(v)-open(v)+1}{2}.
}
\]

### Ví dụ

Nút B mở ở 1 và đóng ở 6:

\[
size(B)=(6-1+1)/2=3.
\]

Subtree B gồm `B,E,F`.

Nút D mở ở 9 và đóng ở 12:

\[
size(D)=(12-9+1)/2=2.
\]

Subtree D gồm `D,G`.

### Chặn độ phức tạp

Nếu đã biết `close(v)` trong O(1), tính `subtreeSize` chỉ gồm vài phép số học nên O(1). Nếu `close(v)` phải tìm bằng quét, độ phức tạp theo quét ấy. **Phép tính kích thước không làm biến mất chi phí tìm cặp ngoặc.**

## 15. Độ sâu nút từ excess

Nếu nút v có ngoặc mở ở p, trước khi đọc ký tự `BP[p]='('`, ngăn xếp chứa **đúng các tổ tiên của v**, nên:

\[
\boxed{depth(v)=E(p).}
\]

Tương đương, sau khi đọc dấu mở:

\[
depth(v)=E(p+1)-1.
\]

### Ví dụ

Với A ở p=0:

\[
depth(A)=E(0)=0.
\]

Với E ở p=2:

\[
depth(E)=E(2)=2,
\]

vì trước khi mở E, A và B đang mở.

Với G ở p=10:

\[
depth(G)=E(10)=2.
\]

### Phân biệt depth với excess sau khi đọc ngoặc

- `E(p)` là **độ sâu của nút mở tại p**.
- `E(p+1)` là **số nút đang mở sau khi vào nút ấy**, bằng `depth+1`.

Nhầm hai giá trị gây lỗi lệch một khi tính độ sâu.

## 16. Quan hệ tổ tiên bằng khoảng ngoặc

Cho hai nút u và v có vị trí mở lần lượt p và r. u là tổ tiên của v **cho phép u=v** khi và chỉ khi ngoặc mở của v nằm **trong cặp ngoặc bao quanh u**:

\[
\boxed{
u\text{ là tổ tiên của }v
\iff
open(u)\le open(v)<close(u).
}
\]

Vì vị trí của v là ngoặc mở, nó không trùng ngoặc đóng của u.

Ví dụ:

- A là tổ tiên của mọi nút.
- B là tổ tiên của E và F.
- B **không** là tổ tiên của C, vì `open(C)=7>close(B)=6`.
- D là tổ tiên của G.
- Mỗi nút là tổ tiên của chính nó theo quy ước **không chặt**.

Nếu muốn **tổ tiên chặt**, yêu cầu thêm `u≠v`.

### Kiểm tra hai cây con có giao nhau?

Trong một cây có gốc, các đoạn cây con của hai nút bất kỳ hoặc:

- **Lồng nhau**: một nút là tổ tiên của nút kia; hoặc
- **Rời nhau**: hai nút nằm ở hai nhánh khác nhau.

Chúng **không thể giao nhau một phần** mà không lồng nhau. Đây là bất biến cấu trúc rất hữu ích cho truy vấn và thuật toán trên cây.

## 17. Preorder và postorder bằng rank/select

Ta mã hóa BP như bit vector:

```text
'(' → 1
')' → 0
```

Dùng quy ước:

\[
rank_1(i)=\#\text{bit 1 trong }[0,i),
\]

\[
rank_0(i)=i-rank_1(i).
\]

`select1(k)` trả vị trí bit 1 thứ k (k đếm từ 1); `select0(k)` tương tự cho bit 0.

### Preorder

Mỗi nút được gặp lần đầu đúng tại một dấu mở. Do đó với nút có vị trí mở p:

\[
\boxed{preorder0(v)=rank_1(p).}
\]

Đây là chỉ số **preorder bắt đầu từ 0**, vì `rank1(p)` đếm số nút đã mở **trước** v.

Nếu cần thứ tự bắt đầu từ 1:

\[
preorder1(v)=rank_1(p+1).
\]

Ngược lại, nút có chỉ số preorder bắt đầu từ 0 là:

\[
\boxed{openByPreorder(k)=select_1(k+1).}
\]

### Postorder

Mỗi nút kết thúc tại một dấu đóng q. Do đó:

\[
\boxed{postorder0(v)=rank_0(q+1)-1.}
\]

Ngược lại, dấu đóng của nút postorder thứ k (k đếm từ 0) ở:

\[
q=select_0(k+1).
\]

Và nút tương ứng là:

\[
\boxed{openByPostorder(k)=findOpen(q).}
\]

Các công thức đòi **cùng một quy ước rank/select**. Nếu thư viện khác định nghĩa rank gồm cả vị trí i hoặc select đánh từ 0, phải điều chỉnh.

## 18. Truy vết preorder/postorder bằng bảng

Với chuỗi `((()())()(()))`, bảng sau cho thấy hai thứ tự cùng tồn tại trong một BP:

| Nút | Mở | Đóng | Preorder từ 0 | Postorder từ 0 |
|---|---:|---:|---:|---:|
| A | 0 | 13 | 0 | 6 |
| B | 1 | 6 | 1 | 2 |
| E | 2 | 3 | 2 | 0 |
| F | 4 | 5 | 3 | 1 |
| C | 7 | 8 | 4 | 3 |
| D | 9 | 12 | 5 | 5 |
| G | 10 | 11 | 6 | 4 |

Ví dụ với C:

- `open(C)=7`, trước đó có bốn ngoặc mở → `preorder0(C)=4`.
- `close(C)=8`, trước hoặc tại 8 có bốn ngoặc đóng → `postorder0(C)=3`.

### Khoảng preorder của subtree

Với một nút có đoạn ngoặc `[p,q]`, các nút trong subtree của nó xuất hiện **liên tiếp** theo preorder. Khoảng chỉ số preorder bắt đầu từ 0 là:

\[
\boxed{
[rank_1(p),\ rank_1(q+1)).
}
\]

Độ dài khoảng chính bằng `subtreeSize(v)`.

Ví dụ B:

```text
open(B)=1, close(B)=6

preorder0(B)=1
subtree preorder indices = [1,4)
nodes = [B,E,F]
```

Đây là cách tự nhiên để lưu mảng giá trị nút theo preorder và truy xuất cả subtree bằng một đoạn liên tiếp.

## 19. Nút lá, số con và con thứ k

### Kiểm tra nút lá

Một nút tại ngoặc mở p là lá khi:

\[
\boxed{BP[p+1]=\texttt{')'}.}
\]

Tương đương `close(p)=p+1` hoặc `subtreeSize(p)=1`.

### Số con trực tiếp

Có thể bắt đầu từ `firstChild(v)` rồi lặp `nextSibling` đến hết. Nếu v có d con:

\[
T_{degree}=O(d)
\]

khi mỗi bước tìm anh em đã O(1) nhờ chỉ mục. Chỉ có BP thô không tự cho `degree(v)` O(1).

### Con thứ k

Với k bắt đầu từ 1:

1. Đặt c bằng con đầu tiên.
2. Đi `nextSibling` thêm k−1 lần.
3. Trả c nếu tồn tại.

Độ phức tạp O(k) theo số bước điều hướng đã tối ưu. Muốn tìm **con thứ k O(1)** hoặc truy vấn degree rất nhanh trên cây lớn có thể cần chỉ mục chuyên dụng ngoài các chỉ mục ghép ngoặc cơ bản.

### Ví dụ

```text
children(A) = [B,C,D]
degree(A) = 3
kth_child(A,1) = B
kth_child(A,3) = D

children(B) = [E,F]
degree(B) = 2
kth_child(B,2) = F

degree(C) = 0
```

## 20. LCA và điều hướng theo tổ tiên

**Lowest Common Ancestor (LCA)** của u và v là tổ tiên chung sâu nhất của hai nút.

Với ví dụ:

```text
LCA(E,F) = B
LCA(E,G) = A
LCA(C,D) = A
LCA(D,G) = D
```

### Cách dễ hiểu khi đã có parent

Có thể:

1. Đưa hai nút về cùng độ sâu bằng cách đi lên phía cha.
2. Cùng đi lên từng bước đến khi gặp nhau.

Thời gian:

\[
O(height)
\]

trong trường hợp xấu, với độ cao h tính theo số cạnh từ gốc đến lá sâu nhất.

### Cách nâng cao trên BP

Excess có thể được xem là độ cao của đường đi DFS. Các **truy vấn giá trị nhỏ nhất trên đoạn (range minimum query, RMQ)**, kết hợp thao tác tìm cặp ngoặc/enclose, giúp xây dựng điều hướng và LCA hiệu quả trên BP.

Tuy nhiên:

- Chỉ có chuỗi BP **không tự cho LCA O(1)**.
- Chỉ có rank/select trên dấu ngoặc mở/đóng **cũng chưa đủ để suy trực tiếp mọi phép điều hướng O(1)**.
- Các cấu trúc succinct chuyên dụng bổ sung index theo **excess và cực trị đoạn**, có thể hỗ trợ nhiều phép điều hướng thời gian hằng số dưới mô hình phù hợp.

Đây là phần mở rộng tự nhiên sau khi nắm chắc các phép cơ bản.

## 21. Python: mã hóa cây bằng DFS lặp, tránh tràn ngăn xếp gọi hàm

Ta biểu diễn cây đầu vào bằng một danh sách `children[v]`, trong đó mỗi phần tử là **danh sách con có thứ tự** của nút v.

Để hỗ trợ cây dạng dây dài mà không gặp giới hạn đệ quy Python, ta dùng ngăn xếp sự kiện:

- `(v, False)`: bước vào v.
- `(v, True)`: bước ra v.

```python
def encode_tree_bp(children: list[list[int]], root: int = 0) -> str:
    n = len(children)
    if n == 0:
        raise ValueError("Cây có gốc phải có ít nhất một nút")
    if type(root) is not int or not 0 <= root < n:
        raise ValueError("Gốc không hợp lệ")

    visited = set()
    output = []
    events = [(root, False)]

    while events:
        v, closing = events.pop()

        if closing:
            output.append(")")
            continue

        if v in visited:
            raise ValueError("Cây có chu trình hoặc nút nhiều cha")
        visited.add(v)
        output.append("(")

        # Dấu đóng của v phải xuất hiện sau các con.
        events.append((v, True))

        # Stack LIFO, nên đẩy các con theo thứ tự đảo.
        for child in reversed(children[v]):
            if type(child) is not int or not 0 <= child < n:
                raise ValueError("Chỉ số con không hợp lệ")
            events.append((child, False))

    if len(visited) != n:
        raise ValueError("Có nút không thể tới từ gốc")

    return "".join(output)


# ID: A=0, B=1, E=2, F=3, C=4, D=5, G=6
children = [
    [1, 4, 5],  # A -> B, C, D
    [2, 3],     # B -> E, F
    [],         # E
    [],         # F
    [],         # C
    [6],        # D -> G
    [],         # G
]

bp = encode_tree_bp(children)
assert bp == "((()())()(()))"
assert len(bp) == 2 * len(children)
assert validate_bp_tree(bp) == 7

assert encode_tree_bp([[]]) == "()"
assert encode_tree_bp([[1], [2], []]) == "((()))"
```

### Bất biến của thuật toán

Khi xử lý `(v, False)`, nút v chưa từng được thăm; ta thêm `(` và đặt sự kiện đóng sau tất cả sự kiện con. Các con được xếp ngược lên stack để chúng **được thực thi theo thứ tự ban đầu**.

Do vậy dấu đóng của v chỉ xuất hiện sau khi xử lý toàn bộ cây con, đúng định nghĩa BP.

### Phát hiện đầu vào không phải cây

Ví dụ `children=[[1],[0]]` làm nút 0 xuất hiện lần thứ hai → bị từ chối. Trường hợp có nút không nối với gốc cũng bị từ chối sau khi duyệt.

Độ phức tạp `O(n)` thời gian với đầu vào là cây hợp lệ n nút và n−1 cạnh; bộ nhớ phụ O(n) cho events/visited/output. Đầu vào giả dạng đồ thị có nhiều cạnh hơn có thể khiến số sự kiện phụ thuộc tổng số cạnh, nhưng vẫn được kiểm tra và từ chối thay vì mã hóa thành cây sai.

## 22. Python: xây chỉ mục BP tĩnh để điều hướng

Lớp sau dùng **mảng chỉ mục O(n)**, không nhằm chứng minh dung lượng succinct. Nó minh họa rõ cách:

- Kiểm tra tính cân bằng một gốc.
- Lưu cặp ngoặc đối xứng.
- Lưu parent/depth cho mỗi ngoặc mở.
- Lưu vị trí mở theo preorder, đóng theo postorder.
- Lưu prefix rank của ngoặc mở để tính excess.

```python
class BPStaticTree:
    def __init__(self, bp: str):
        validate_bp_tree(bp)
        self.bp = bp
        self.length = len(bp)
        self.n = self.length // 2

        self.match = [-1] * self.length
        self.parent = {}
        self.depth = {}
        self.opens = []
        self.closes = []
        self.rank_open_prefix = [0] * (self.length + 1)

        stack = []
        for i, ch in enumerate(bp):
            self.rank_open_prefix[i + 1] = (
                self.rank_open_prefix[i]
            )

            if ch == "(":
                self.parent[i] = stack[-1] if stack else None
                self.depth[i] = len(stack)
                self.opens.append(i)
                self.rank_open_prefix[i + 1] += 1
                stack.append(i)
            else:
                p = stack.pop()
                self.match[p] = i
                self.match[i] = p
                self.closes.append(i)

        assert not stack
        assert len(self.opens) == len(self.closes) == self.n

    def _check_open(self, p: int) -> None:
        if (
            type(p) is not int
            or not 0 <= p < self.length
            or self.bp[p] != "("
        ):
            raise IndexError("Phải truyền vị trí ngoặc mở")

    def rank1(self, i: int) -> int:
        if type(i) is not int or not 0 <= i <= self.length:
            raise IndexError("i ngoài đoạn 0..2n")
        return self.rank_open_prefix[i]

    def rank0(self, i: int) -> int:
        return i - self.rank1(i)

    def excess(self, i: int) -> int:
        return 2 * self.rank1(i) - i

    def by_preorder(self, k: int) -> int:
        if type(k) is not int or not 0 <= k < self.n:
            raise IndexError("preorder index ngoài miền")
        return self.opens[k]

    def by_postorder(self, k: int) -> int:
        if type(k) is not int or not 0 <= k < self.n:
            raise IndexError("postorder index ngoài miền")
        return self.match[self.closes[k]]

    def preorder_number(self, p: int) -> int:
        self._check_open(p)
        return self.rank1(p)

    def postorder_number(self, p: int) -> int:
        self._check_open(p)
        q = self.match[p]
        return self.rank0(q + 1) - 1

    def close(self, p: int) -> int:
        self._check_open(p)
        return self.match[p]

    def open_for_close(self, q: int) -> int:
        if (
            type(q) is not int
            or not 0 <= q < self.length
            or self.bp[q] != ")"
        ):
            raise IndexError("Phải truyền vị trí ngoặc đóng")
        return self.match[q]

    def parent_of(self, p: int):
        self._check_open(p)
        return self.parent[p]

    def depth_of(self, p: int) -> int:
        self._check_open(p)
        assert self.depth[p] == self.excess(p)
        return self.depth[p]

    def first_child(self, p: int):
        self._check_open(p)
        child = p + 1
        return child if child < self.match[p] else None

    def next_sibling(self, p: int):
        self._check_open(p)
        parent = self.parent[p]
        if parent is None:
            return None

        nxt = self.match[p] + 1
        return nxt if nxt < self.match[parent] else None

    def children_of(self, p: int):
        child = self.first_child(p)
        while child is not None:
            yield child
            child = self.next_sibling(child)

    def degree(self, p: int) -> int:
        return sum(1 for _ in self.children_of(p))

    def subtree_size(self, p: int) -> int:
        self._check_open(p)
        return (self.match[p] - p + 1) // 2

    def is_ancestor(self, u: int, v: int) -> bool:
        self._check_open(u)
        self._check_open(v)
        return u <= v < self.match[u]

    def lca(self, u: int, v: int) -> int:
        self._check_open(u)
        self._check_open(v)

        a, b = u, v
        while self.depth[a] > self.depth[b]:
            a = self.parent[a]
        while self.depth[b] > self.depth[a]:
            b = self.parent[b]

        while a != b:
            a = self.parent[a]
            b = self.parent[b]

        return a


tree = BPStaticTree("((()())()(()))")

A, B, E, F, C, D, G = tree.opens
assert (A, B, E, F, C, D, G) == (
    0, 1, 2, 4, 7, 9, 10
)

assert tree.n == 7
assert tree.close(A) == 13
assert tree.close(B) == 6
assert tree.close(D) == 12

assert tree.parent_of(A) is None
assert tree.parent_of(E) == B
assert tree.parent_of(G) == D

assert tree.first_child(A) == B
assert tree.first_child(B) == E
assert tree.first_child(C) is None

assert tree.next_sibling(E) == F
assert tree.next_sibling(B) == C
assert tree.next_sibling(C) == D
assert tree.next_sibling(D) is None

assert tree.subtree_size(A) == 7
assert tree.subtree_size(B) == 3
assert tree.subtree_size(D) == 2
assert tree.subtree_size(C) == 1

assert tree.depth_of(A) == 0
assert tree.depth_of(E) == 2
assert tree.depth_of(G) == 2
assert tree.degree(A) == 3
assert tree.degree(B) == 2
assert tree.degree(C) == 0

assert tree.is_ancestor(A, G)
assert tree.is_ancestor(B, F)
assert not tree.is_ancestor(B, C)

assert tree.lca(E, F) == B
assert tree.lca(E, G) == A
assert tree.lca(D, G) == D
assert tree.preorder_number(C) == 4
assert tree.postorder_number(B) == 2
assert tree.by_postorder(0) == E
```

### Đọc đúng bản chất của lớp ví dụ

Lớp dùng `list[int]`, `dict` và `str` của Python. Bộ nhớ thực tế của chúng **không chỉ 2n bit**; riêng mảng `match` có 2n vị trí số nguyên/tham chiếu.

Ví dụ này chủ ý giúp kiểm chứng **công thức và thao tác**. Khi triển khai succinct thật, ta thay phần lớn những mảng chỉ mục rộng bằng các cấu trúc hỗ trợ rank, select, matching và excess có overhead nhỏ hơn nhiều.

## 23. Giải mã BP để dựng lại danh sách con

Nếu không chỉ cần điều hướng trên dạng nén, ta có thể **giải mã thành cây tường minh**. Nút được đánh ID theo **preorder**, không nhất thiết giống ID của cây đầu vào.

```python
def decode_bp_children(bp: str) -> list[list[int]]:
    validate_bp_tree(bp)

    children = []
    stack = []

    for char in bp:
        if char == "(":
            v = len(children)
            children.append([])

            if stack:
                children[stack[-1]].append(v)
            stack.append(v)
        else:
            stack.pop()

    assert not stack
    return children


bp = "((()())()(()))"
decoded = decode_bp_children(bp)

assert decoded == [
    [1, 4, 5],
    [2, 3],
    [],
    [],
    [],
    [6],
    [],
]
assert encode_tree_bp(decoded) == bp

assert decode_bp_children("()") == [[]]
assert encode_tree_bp(decode_bp_children("((()))")) == "((()))"
```

### Vì sao ID sau giải mã là preorder?

Mỗi nút được cấp ID ngay khi gặp dấu `(`. Nhưng thứ tự các dấu mở chính là **thứ tự DFS preorder**, nên ID là `0,1,...,n−1` theo preorder.

Nếu đầu vào dùng ID bất kỳ, ví dụ khóa UUID hoặc ID từ cơ sở dữ liệu, BP **không lưu những khóa này**. Phải đi kèm một bảng khóa theo preorder hoặc một ánh xạ tương đương nếu ứng dụng cần khôi phục chúng.

### Độ phức tạp

Giải mã n nút tốn `O(n)` thời gian và `O(n)` bộ nhớ cho danh sách con, stack và object Python. Đây là chi phí **tạo cấu trúc tường minh**, không phải chi phí bắt buộc để lưu BP khi chỉ truy vấn trực tiếp trên dạng nén.

## 24. Kiểm thử sâu hơn: biên và mô hình tham chiếu

Các lỗi thường xuất hiện ở cây một nút, đường dài, cây nhiều con và chuỗi không hợp lệ.

### Các hình dạng đặc trưng

| Cây | BP |
|---|---|
| Một nút | `()` |
| Gốc và một con | `(())` |
| Đường ba nút | `((()))` |
| Gốc có hai con lá | `(()())` |
| Gốc có ba con lá | `(()()())` |

### Kiểm thử round-trip

```python
cases = [
    [[]],
    [[1], []],
    [[1], [2], []],
    [[1, 2], [], []],
    [[1, 2, 3], [], [], []],
    [[1, 4, 5], [2, 3], [], [], [], [6], []],
]

for original in cases:
    encoded = encode_tree_bp(original)
    decoded = decode_bp_children(encoded)

    assert encode_tree_bp(decoded) == encoded
    assert len(decoded) == len(original)

    index = BPStaticTree(encoded)
    assert index.subtree_size(index.opens[0]) == len(original)
    assert index.parent_of(index.opens[0]) is None
    assert index.excess(len(encoded)) == 0

# Đường sâu: encoder không dùng đệ quy.
long_chain = [[i + 1] for i in range(1999)] + [[]]
encoded = encode_tree_bp(long_chain)
assert len(encoded) == 4000
assert encoded == "(" * 2000 + ")" * 2000

for invalid in ["", "(", ")(", "()()", "(()", "())(", "((a))"]:
    try:
        BPStaticTree(invalid)
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("Đã chấp nhận BP không hợp lệ")
```

### Đừng chỉ kiểm thử độ dài 2n

Một chuỗi như `()()` có độ dài 4, cùng số mở/đóng và toàn bộ prefix không âm, nhưng là **hai cây gốc riêng biệt**. Nếu schema yêu cầu một cây, kiểm thử phải từ chối nó.

## 25. Đóng gói BP thành bit: 2n bit topology

Nếu mỗi dấu `(` được mã hóa bằng bit 1 và dấu `)` bằng bit 0, chuỗi BP dài 2n dấu trở thành **bit vector dài 2n**.

Số byte payload khi đóng liên tiếp:

\[
\boxed{
B_{\text{bytes}}
=\left\lceil\frac{2n}{8}\right\rceil.
}
\]

Ví dụ:

| Số nút n | Bit topology | Byte payload đóng theo byte |
|---:|---:|---:|
| 1 | 2 | 1 |
| 7 | 14 | 2 |
| 100 | 200 | 25 |
| 1.000 | 2.000 | 250 |
| 1.000.000 | 2.000.000 | 250.000 |

Một triệu nút chỉ cần **250.000 byte payload topology**, tương đương khoảng **244,14 KiB**, nếu biết n và không tính bất kỳ nhãn hoặc chỉ mục nào.

### Bit order phải được công bố

Trong ví dụ dưới, vị trí BP thứ i tương ứng **bit `i%8` của byte `i//8`**; bit thấp của byte được ghi trước (LSB-first theo stream).

Với chuỗi ví dụ 14 bit:

```text
BP:     ((()())()(()))
Bit:    11101001011000  (đọc theo chỉ số BP từ trái qua phải)
Bytes:  97 06            (bit thấp của mỗi byte chứa ký tự trước)
```

Hai bit cao còn thừa của byte thứ hai phải bằng 0 trong quy ước canonical.

**Lưu ý:** cách hiển thị “Bit” theo thứ tự BP khác với cách viết nhị phân của từng byte theo trọng số cao→thấp. Đó không phải lỗi endian, mà là **hai quy ước hiển thị** khác nhau.

## 26. Python: serialize BP dạng packed bit và đọc lại

```python
def pack_bp(bp: str) -> bytes:
    validate_bp_tree(bp)

    payload = bytearray((len(bp) + 7) // 8)
    for i, char in enumerate(bp):
        if char == "(":
            payload[i // 8] |= 1 << (i % 8)

    return bytes(payload)


def unpack_bp(payload: bytes, bit_count: int) -> str:
    if not isinstance(payload, bytes):
        raise TypeError("payload phải là bytes")
    if type(bit_count) is not int or bit_count < 2:
        raise ValueError("bit_count không hợp lệ")
    if bit_count % 2:
        raise ValueError("BP phải có số bit chẵn")
    if len(payload) != (bit_count + 7) // 8:
        raise ValueError("Độ dài payload không khớp")

    remaining = bit_count % 8
    if remaining and (payload[-1] >> remaining) != 0:
        raise ValueError("Bit padding cuối phải bằng 0")

    bp = "".join(
        "(" if (payload[i // 8] >> (i % 8)) & 1 else ")"
        for i in range(bit_count)
    )
    validate_bp_tree(bp)
    return bp


bp = "((()())()(()))"
packed = pack_bp(bp)

assert packed == bytes.fromhex("97 06")
assert unpack_bp(packed, 14) == bp
assert unpack_bp(pack_bp("()"), 2) == "()"

try:
    unpack_bp(bytes.fromhex("97 C6"), 14)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối padding khác 0")
```

### Vì sao cần lưu n hoặc số bit?

Với một byte payload, ta không biết chắc dãy logic có 2, 4, 6 hay 8 bit nếu không có schema/metadata hoặc cách nhận biết ranh giới. Vì thế `unpack_bp` nhận `bit_count` (bằng `2n`), và kiểm tra các bit padding phải bằng 0.

Nếu chiều dài n được lưu trong header riêng, **phải cộng chi phí header** vào dung lượng thực tế. Nếu hệ thống đã biết n từ ngữ cảnh, không nhất thiết lặp lại thông tin trong từng payload.

### Mã hóa bit không phải tự động hỗ trợ truy vấn nhanh

`pack_bp` chỉ nén topology vào byte. Để lấy `parent`, `findClose` hoặc LCA nhanh mà không giải toàn bộ dữ liệu, vẫn cần **directory/chỉ mục phụ** hoặc thuật toán quét tương ứng.

## 27. C++17: xác thực và truy vấn BP bằng chỉ mục rõ ràng

Phiên bản C++ sau xây chỉ mục khớp ngoặc, parent, depth và rank từ một chuỗi BP. Nó dùng vector chỉ số rõ ràng để dễ kiểm tra, **không** tuyên bố là một cấu trúc succinct hoàn chỉnh.

```cpp
#include <cassert>
#include <cstddef>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

class BPIndex {
public:
    static constexpr std::size_t NONE =
        std::numeric_limits<std::size_t>::max();

    explicit BPIndex(const std::string& bp)
        : bp_(bp),
          match_(bp.size(), NONE),
          parent_(bp.size(), NONE),
          depth_(bp.size(), 0),
          rank_open_(bp.size() + 1, 0) {
        if (bp_.empty() || bp_.size() % 2 != 0) {
            throw std::invalid_argument("Invalid BP length");
        }

        std::vector<std::size_t> stack;
        for (std::size_t i = 0; i < bp_.size(); ++i) {
            rank_open_[i + 1] = rank_open_[i];

            if (bp_[i] == '(') {
                if (stack.empty() && i != 0) {
                    throw std::invalid_argument("Forest, not one tree");
                }

                parent_[i] = stack.empty() ? NONE : stack.back();
                depth_[i] = stack.size();
                opens_.push_back(i);
                ++rank_open_[i + 1];
                stack.push_back(i);
            } else if (bp_[i] == ')') {
                if (stack.empty()) {
                    throw std::invalid_argument("Unmatched close");
                }

                const std::size_t p = stack.back();
                stack.pop_back();

                match_[p] = i;
                match_[i] = p;
                closes_.push_back(i);

                if (stack.empty() && i + 1 != bp_.size()) {
                    throw std::invalid_argument("Forest, not one tree");
                }
            } else {
                throw std::invalid_argument("Unexpected character");
            }
        }

        if (!stack.empty() || opens_.size() != bp_.size() / 2) {
            throw std::invalid_argument("Unmatched open");
        }
    }

    std::size_t node_count() const {
        return opens_.size();
    }

    std::size_t open_at_preorder(std::size_t k) const {
        if (k >= opens_.size()) {
            throw std::out_of_range("preorder");
        }
        return opens_[k];
    }

    std::size_t rank1(std::size_t i) const {
        if (i > bp_.size()) {
            throw std::out_of_range("prefix");
        }
        return rank_open_[i];
    }

    std::size_t excess(std::size_t i) const {
        return 2 * rank1(i) - i;
    }

    std::size_t close(std::size_t p) const {
        check_open(p);
        return match_[p];
    }

    std::size_t parent(std::size_t p) const {
        check_open(p);
        return parent_[p]; // NONE cho root.
    }

    std::size_t depth(std::size_t p) const {
        check_open(p);
        return depth_[p];
    }

    std::size_t first_child(std::size_t p) const {
        check_open(p);
        return p + 1 < match_[p] ? p + 1 : NONE;
    }

    std::size_t next_sibling(std::size_t p) const {
        check_open(p);
        const std::size_t par = parent_[p];
        if (par == NONE) {
            return NONE;
        }

        const std::size_t nxt = match_[p] + 1;
        return nxt < match_[par] ? nxt : NONE;
    }

    std::size_t subtree_size(std::size_t p) const {
        check_open(p);
        return (match_[p] - p + 1) / 2;
    }

    bool is_ancestor(std::size_t a, std::size_t b) const {
        check_open(a);
        check_open(b);
        return a <= b && b < match_[a];
    }

    std::size_t preorder_number(std::size_t p) const {
        check_open(p);
        return rank1(p);
    }

private:
    void check_open(std::size_t p) const {
        if (p >= bp_.size() || bp_[p] != '(') {
            throw std::out_of_range("Not an open position");
        }
    }

    std::string bp_;
    std::vector<std::size_t> match_;
    std::vector<std::size_t> parent_;
    std::vector<std::size_t> depth_;
    std::vector<std::size_t> opens_;
    std::vector<std::size_t> closes_;
    std::vector<std::size_t> rank_open_;
};

int main() {
    const BPIndex t("((()())()(()))");

    assert(t.node_count() == 7);

    const auto A = t.open_at_preorder(0);
    const auto B = t.open_at_preorder(1);
    const auto E = t.open_at_preorder(2);
    const auto F = t.open_at_preorder(3);
    const auto C = t.open_at_preorder(4);
    const auto D = t.open_at_preorder(5);
    const auto G = t.open_at_preorder(6);

    assert(A == 0 && B == 1 && E == 2 && F == 4);
    assert(C == 7 && D == 9 && G == 10);
    assert(t.close(B) == 6);
    assert(t.close(D) == 12);

    assert(t.parent(A) == BPIndex::NONE);
    assert(t.parent(E) == B);
    assert(t.parent(G) == D);
    assert(t.first_child(A) == B);
    assert(t.first_child(C) == BPIndex::NONE);

    assert(t.next_sibling(E) == F);
    assert(t.next_sibling(B) == C);
    assert(t.next_sibling(C) == D);

    assert(t.depth(E) == 2);
    assert(t.excess(E) == 2);
    assert(t.subtree_size(B) == 3);
    assert(t.subtree_size(D) == 2);
    assert(t.is_ancestor(A, G));
    assert(!t.is_ancestor(B, C));
    assert(t.preorder_number(C) == 4);

    std::cout << "BP tree OK\n";
}
```

### An toàn và độ phức tạp

- Trình phân tích cú pháp dùng một stack và đi qua chuỗi đúng một lần: `O(n)` thời gian.
- `match` và `parent` là mảng chứa chỉ số, không phải các bit ghép ngoặc.
- Truy vấn sau khi dựng có thời gian O(1) cho những hàm đã cho vì index đã được lưu tường minh.
- Bộ nhớ phụ `O(n)` **từ máy/chỉ số**; trên máy 64 bit, chi phí này có thể lớn hơn rất nhiều so với 2n bit topology.
- Mã tránh đệ quy để xử lý cây có chiều cao lớn.
- `NONE` là sentinel ngoài mọi chỉ số vị trí hợp lệ thực tế, và API phải kiểm tra nó trước khi dùng làm vị trí.

Không nên dùng số lượng byte của chuỗi đầu vào BP như tổng bộ nhớ của đối tượng `BPIndex`.

## 28. Bảng độ phức tạp: có và không có chỉ mục

Đặt n là số nút và h là chiều cao cây, d là số con của nút đang xét.

| Thao tác | Chỉ BP, quét trực tiếp | Với chỉ mục mảng đơn giản như ví dụ |
|---|---|---|
| Xác thực BP | `O(n)` | `O(n)` khi xây |
| Tìm ngoặc đóng `close(p)` | `O(n)` worst-case | `O(1)` |
| Tìm ngoặc mở `open(q)` | `O(n)` worst-case | `O(1)` |
| Lấy parent | Có thể `O(n)` | `O(1)` |
| Con đầu | Cần biết đóng hoặc kiểm tra ký tự sát p | `O(1)` |
| Anh em kế | Phụ thuộc tìm cặp ngoặc/cha | `O(1)` |
| Kích thước subtree | Phụ thuộc `close(p)` | `O(1)` |
| Độ sâu | Có thể quét tiền tố | `O(1)` với mảng depth/rank |
| Tổ tiên | Phụ thuộc `close(u)` | `O(1)` |
| Số con d | Có thể phải quét subtree | `O(d)` theo các anh em |
| LCA bằng đi cha | Không trực tiếp thuận tiện | `O(h)` |
| Preorder ID | Quét đếm ngoặc mở | `O(1)` với rank prefix |
| Postorder ID | Quét đếm ngoặc đóng | `O(1)` với rank prefix và match |

**Chú ý:** cột “chỉ mục mảng” dùng nhiều mảng chỉ số rộng và vì thế có `O(n)` **số nguyên** phụ. Không nên nhầm với đảm bảo succinct `2n+o(n)` **bit**.

### Có chỉ mục tốt hơn không?

Có. Nhiều cấu trúc dữ liệu BP tĩnh hỗ trợ điều hướng cơ bản bằng `2n+o(n)` bit dưới mô hình word-RAM thích hợp. Nhưng cần mô tả **chỉ mục chuyên dụng theo excess/range-min**, không đủ chỉ bật một tùy chọn “đóng gói chuỗi thành bit”.

## 29. Catalan: đếm số hình dạng cây có gốc có thứ tự

Chặn thông tin phải bắt đầu từ việc đếm các đối tượng hợp lệ, không phải cứ nhìn số ngoặc.

### Số dãy ngoặc cân bằng nói chung

Với n cặp ngoặc, số chuỗi ngoặc cân bằng (Dyck words) là số **Catalan thứ n**:

\[
C_n=\frac{1}{n+1}\binom{2n}{n}.
\]

Ví dụ `C_3=5`.

### Nhưng cây một gốc có n nút không phải C_n hình dạng

Mã BP của một cây **một gốc** là chuỗi cân bằng **nguyên thủy**, bắt đầu bằng `(` của gốc và kết thúc bằng `)` của gốc, không về excess 0 giữa chừng.

Bỏ cặp ngoặc ngoài cùng sẽ còn **một dãy ngoặc cân bằng bất kỳ có n−1 cặp**, tương ứng với rừng các cây con của gốc. Vì vậy:

\[
\boxed{
\#\text{rooted ordered trees with n nodes}=C_{n-1}.
}
\]

Đây là chỗ rất dễ nhầm **`C_n` với `C_{n-1}`**.

### Ví dụ n=3

Có:

\[
C_2=2
\]

hình dạng:

```text
Dây 3 nút:          ((()))
Gốc có 2 con lá:    (()())
```

Trong khi có `C_3=5` dãy ngoặc cân bằng **bất kỳ** với ba cặp, bao gồm các chuỗi biểu diễn **rừng** có nhiều cây gốc.

## 30. Giới hạn thông tin tối thiểu của topology

Với n nút, số hình dạng là `C_{n-1}`. Một mã **độ dài cố định** phân biệt mọi hình dạng cần ít nhất:

\[
\boxed{
L_{\min}(n)=\left\lceil\log_2 C_{n-1}\right\rceil
}
\]

bit khi n và loại cây đã được biết.

BP dùng đúng:

\[
L_{\mathrm{BP}}(n)=2n
\]

bit logic, chưa tính byte padding và index.

### Ví dụ n=7

Có:

\[
C_6=132
\]

hình dạng. Vì `2^7=128<132≤256=2^8`, chặn fixed-length là **8 bit**, trong khi BP dùng **14 bit**.

Sự chênh lệch không mâu thuẫn: BP không phải mã cố định tối ưu tuyệt đối cho **mỗi n nhỏ**, mà là một biểu diễn có cấu trúc cho phép điều hướng thuận tiện.

### Khi n lớn

Dùng xấp xỉ Catalan:

\[
C_m\sim\frac{4^m}{\sqrt{\pi}\,m^{3/2}},
\]

ta được với `m=n-1`:

\[
\log_2 C_{n-1}
=
2(n-1)-\frac32\log_2(n-1)-\frac12\log_2\pi+o(1).
\]

Do đó:

\[
\boxed{
2n-\log_2 C_{n-1}=O(\log n).
}
\]

Với n lớn, phần chênh giữa **2n bit topology của BP** và chặn lý thuyết chỉ có bậc log n, nhỏ hơn rất nhiều so với n.

**Kết luận:** BP có **2n bit topology** là một biểu diễn sát chặn thông tin tiệm cận, đồng thời giữ được cấu trúc lồng nhau để xây chỉ mục điều hướng.

## 31. Succinct BP: 2n + o(n) bit có nghĩa gì?

Một cấu trúc BP **succinct** nhắm tới việc lưu:

\[
\boxed{2n+o(n)\text{ bit}}
\]

để hỗ trợ các thao tác điều hướng được quy định, thường trong thời gian rất nhanh, kể cả O(1) cho nhiều thao tác cơ bản dưới mô hình word-RAM phù hợp.

### Tách hai thành phần

1. **2n bit**: hai dấu ngoặc mã hóa mỗi nút.
2. **o(n) bit phụ**: chỉ mục giúp trả lời matching, enclose, rank/select, excess và các tìm kiếm cần thiết.

Ký hiệu `o(n)` có nghĩa overhead tăng **chậm hơn tuyến tính** so với n; không phải “0 byte”, và không có nghĩa mọi thư viện đều đạt được.

### Tại sao mảng match đầy đủ chưa succinct?

Nếu lưu một số nguyên 32 bit cho mỗi vị trí ngoặc:

```text
match[0 .. 2n-1]
```

thì riêng mảng match dùng:

\[
2n\cdot32=64n\text{ bit},
\]

lớn hơn nhiều so với 2n bit topology. Parent/depth còn làm tổng tăng thêm.

Lớp Python/C++ trong bài cố ý đi theo cách dễ hiểu đó. Chúng là **các bộ điều hướng đúng đắn**, không phải triển khai succinct 2n+o(n).

### Về chặn thông tin

Số Catalan `C_{n-1}` cho thấy chặn topology là `2n-O(\log n)` bit. Vì vậy cấu trúc dùng `2n+o(n)` bit là **sát giới hạn thông tin tới thành phần thấp hơn tuyến tính**, dù 2n không phải bằng chính xác `⌈log₂C_{n-1}⌉`.

## 32. Chỉ mục excess: tìm cặp ngoặc mà không lưu 2n số nguyên

Với BP mã hóa `(=+1` và `)=-1`, tìm cặp ngoặc là bài toán tìm vị trí mà **tổng độ dư** trở lại một mức cho trước.

### Một hướng xây chỉ mục

Chia BP thành các block, ví dụ một số hằng hoặc số bit phụ thuộc `log n`. Với mỗi block, lưu một số thông tin tổng hợp:

- Tổng thay đổi excess của cả block.
- Excess nhỏ nhất tương đối với đầu block.
- Excess lớn nhất tương đối với đầu block.
- Một số mốc/siêu block để định vị block cần tìm nhanh.

Khi hỏi `close(p)`:

1. Biết excess mục tiêu `E(p)`.
2. Quét một phần block chứa p hoặc dùng bảng tra cứu ngắn.
3. Bỏ qua các block mà dải excess **không chứa** mục tiêu.
4. Tìm block đầu tiên có khả năng chứa vị trí cần tìm.
5. Xác định đúng dấu ngoặc trong block đó.

### Vì sao lưu min/max theo block có ích?

Trong một dãy bước +1/−1, excess di chuyển **mỗi bước đúng một đơn vị**. Nếu mức mục tiêu nằm ngoài khoảng [min,max] mà block đạt tới, chắc chắn không có vị trí phù hợp trong block. Ta có thể bỏ qua toàn block thay vì kiểm tra từng bit.

Nếu các mức min/max được tổ chức thêm trong cấu trúc phân cấp hoặc RMQ thích hợp, việc định vị có thể nhanh hơn quét tuyến tính.

### Đừng tuyên bố quá mức

Chỉ lưu min/max của từng block rồi quét block tuần tự **chưa cho matching O(1) worst-case**. Để đạt `2n+o(n)` bit với các thao tác nhanh cần thiết kế cấu trúc phụ, kích thước block/bảng tra cứu và chứng minh độ phức tạp cụ thể.

Tên gọi thường gặp là **range min–max tree / excess directory**. Nó là một hướng thiết kế chứ không phải thuộc tính tự nhiên của chuỗi BP thô.

## 33. Rank/select có vai trò gì trong BP?

Nếu ánh xạ:

```text
'(' = 1
')' = 0
```

thì BP trở thành một bit vector. Từ đó:

\[
E(i)=rank_1(i)-rank_0(i)=2rank_1(i)-i.
\]

Vì vậy nếu hỗ trợ `rank1(i)` nhanh, ta tính excess ngay bằng một phép nhân hai và phép trừ.

### Ánh xạ nút theo preorder

Vị trí mở của nút preorder thứ k (k bắt đầu từ 0):

\[
p=select_1(k+1).
\]

Ngược lại `preorder0(p)=rank1(p)`.

### Ánh xạ nút theo postorder

Vị trí đóng của nút postorder thứ k (k bắt đầu từ 0):

\[
q=select_0(k+1).
\]

Để lấy nút, phải tìm `open(q)`.

### Điều chưa được giải quyết chỉ bằng rank/select

Rank/select **đếm** và **định vị ngoặc theo thứ tự xuất hiện**, nhưng không trực tiếp biết ngoặc mở nào khớp ngoặc đóng nào. Matching là phép truy vấn trên **cấu trúc lồng nhau**, cần excess search/index phù hợp.

Vì vậy một thiết kế BP đầy đủ thường có cả:

- Chỉ mục **rank/select bit vector**.
- Chỉ mục **findClose/findOpen/enclose/excess**.
- Có thể thêm hỗ trợ RMQ/LCA và các phép điều hướng chuyên biệt.

## 34. Nhãn nút và dữ liệu đi kèm BP

BP chỉ xác định topology. Cây ứng dụng thường còn chứa:

- ID/khóa nút.
- Trọng số, timestamp.
- Nhãn chuỗi.
- Thuộc tính kiểu node.
- Con trỏ tới bản ghi ngoài cây.

Một phương án phổ biến: lưu nhãn theo **preorder**:

```text
BP:     ((()())()(()))
Open:   A B E F C D G

labels = ["A","B","E","F","C","D","G"]
```

Với nút có vị trí mở p:

\[
labels[rank1(p)]
\]

là nhãn của nó, nếu `labels` đã được tổ chức đúng preorder.

### Tại sao tiện?

- Mảng nhãn liên tục, có tính cục bộ tốt.
- Truy cập nhãn của node chỉ cần chuyển từ open position sang preorder index.
- Cây con v tương ứng với **một đoạn liên tiếp** trong mảng preorder labels.

Ví dụ với B, subtree preorder là `[1,4)`:

```text
labels[1:4] = ["B","E","F"]
```

### Nhưng phải cộng chi phí nhãn

Nếu mỗi nhãn dùng 8 byte cố định, n nhãn cần thêm `8n` byte trước metadata, lớn hơn nhiều so với `2n/8=n/4` byte topology. Vì thế tuyên bố “một triệu nút chỉ chiếm 250 KiB” **chỉ đúng cho topology**, không đúng cho toàn bộ cây có nhãn.

## 35. So sánh BP với biểu diễn cây khác

| Biểu diễn | Lưu topology bằng gì? | Điểm mạnh | Điểm đánh đổi |
|---|---|---|---|
| Nút + con trỏ | Liên kết cha/con/anh em hoặc vector con | Dễ cập nhật, API trực tiếp | Con trỏ, allocator, phân mảnh |
| Mảng parent | Một chỉ số cha cho mỗi nút | Đơn giản, parent trực tiếp | Con đầu/anh em cần thêm index |
| Mảng children/CSR | Offset và danh sách con liên tục | Duyệt con thuận tiện, dữ liệu cache-friendly | Dùng nhiều chỉ số/offset |
| DFS preorder + subtree end | Chỉ số đầu/cuối cây con | Truy vấn subtree theo đoạn | Cần cấu trúc khác cho child/parent |
| BP (2n bit) | Một cặp ngoặc trên mỗi nút | Gọn, cấu trúc lồng nhau, subtree liên tục | Truy vấn nhanh cần index |
| LOUDS | Bit vector mô tả bậc nút theo thứ tự tầng | Điều hướng BFS, hỗ trợ rank/select | Thứ tự nút và công thức điều hướng khác |

### BP có giống “first child/next sibling” không?

BP cho phép suy ra `firstChild` và `nextSibling` từ vị trí ngoặc, nhưng **không cần lưu hai con trỏ** trong payload topology. Nếu cài bằng mảng match/parent đầy đủ, tổng bộ nhớ lại có thể lớn. Tiết kiệm lớn nhất xuất hiện khi đi kèm chỉ mục gọn hơn.

### BP và LOUDS khác về thứ tự duyệt

BP theo **DFS/preorder**, còn LOUDS thường mã hóa bậc nút theo **BFS/level order**. Cả hai là họ biểu diễn gọn, nhưng không thể dùng công thức BP cho LOUDS nếu không chứng minh lại.

## 36. Cập nhật động: điểm yếu của chuỗi BP liền mạch

Một dãy BP tĩnh rất thuận tiện để lưu và truy vấn, nhưng nếu chèn một nút vào giữa cây, chuỗi bit phải thay đổi.

### Chèn lá mới

Giả sử thêm một lá H làm con đầu của C:

```text
Trước: C = ()
Sau:   C = (())
```

Ta phải chèn đúng hai ký tự `()` vào vị trí thích hợp trong chuỗi BP của toàn cây.

Nếu BP nằm trong một mảng bit liền nhau, chèn hai bit có thể buộc **dịch toàn bộ suffix**; worst-case `O(n)` bit thao tác. Các vị trí mở/đóng phía sau bị thay đổi và index rank/matching có thể bị cũ.

### Xóa một subtree

Với nút v có đoạn `[p,close(p)]`, xóa subtree là xóa **toàn bộ đoạn đó**. Đây là lợi thế hình học vì subtree tạo thành một đoạn liên tiếp, nhưng trên mảng bit tĩnh vẫn phải dịch phần sau đoạn bị xóa.

### Một số chiến lược

- **Immutable snapshots:** tạo phiên bản BP mới theo đợt, dễ cache và publish.
- **Batch rebuild:** gom cập nhật rồi xây lại topology/index.
- **Block-based dynamic BP:** chia BP thành block và dùng cây cân bằng lưu tổng/min excess.
- **Persistent tree representation:** giữ nhiều phiên bản, chia sẻ vùng không đổi; cần thiết kế đặc biệt.

Một dynamic BP có thể hỗ trợ cập nhật hiệu quả hơn mảng bit liền mạch, nhưng không tự giữ mọi thao tác O(1) với tổng `2n+o(n)` bit như cấu trúc static.

## 37. Tính nhất quán khi cây thay đổi

Với BP, các thông tin sau phụ thuộc topology hiện tại:

- Vị trí ngoặc mở/đóng.
- Chỉ số preorder/postorder.
- Parent/child/sibling.
- Subtree size.
- Depth và excess.
- Mốc directory và bảng ghép ngoặc.
- Vị trí trong mảng nhãn nếu nhãn được lưu theo preorder.

Khi sửa cây, **không được chỉ sửa chuỗi BP** rồi tiếp tục dùng bảng `match`/`parent` cũ.

### Hai cách giữ nhất quán

1. **Đóng băng cấu trúc:** mọi truy vấn dùng cùng phiên bản BP và các chỉ mục được dựng từ chính nó.
2. **Cập nhật đồng bộ hoặc thay bản snapshot:** thay BP và index thành một đơn vị nhất quán; người đọc không được thấy BP mới với chỉ mục cũ.

Trong hệ thống nhiều luồng, cần quan tâm đến tính nguyên tử của việc publish phiên bản và vòng đời bộ nhớ. Chia sẻ một cấu trúc bất biến theo snapshot thường đơn giản hơn cập nhật tại chỗ nhiều index phụ.

## 38. Trường hợp nào không nên dùng BP làm biểu diễn chính?

BP đặc biệt phù hợp với:

- Cây có gốc, thứ tự con ổn định.
- Truy vấn nhiều hơn cập nhật.
- Dữ liệu topology rất lớn, ngân sách bộ nhớ chặt.
- Cần lấy subtree theo đoạn preorder.
- Xây chỉ mục tĩnh để đọc nhanh.

Nhưng cần cân nhắc biểu diễn khác khi:

- Chèn/xóa nút ở giữa rất thường xuyên.
- Node ID cần ổn định qua nhiều phiên bản mà không thêm bảng ánh xạ.
- Cây nhỏ, vài con trỏ không phải nút thắt.
- Các phép truy vấn đặc biệt không được hỗ trợ bởi chỉ mục hiện có.
- Cần giữ riêng vị trí **con trái/con phải bị thiếu** của cây nhị phân.
- Dữ liệu của nút lớn đến mức tiết kiệm topology không ảnh hưởng đáng kể tổng RAM.
- Phải trao đổi dữ liệu với một giao thức đã định nghĩa layout khác.

Mục tiêu của cấu trúc dữ liệu là **phù hợp workload**, không phải cực tiểu hóa riêng một hạng mục dung lượng.

## 39. Bài toán thực tế: cây phân cấp một triệu nút

Giả sử một hệ thống quản lý cây phân cấp tĩnh có:

```text
n = 1,000,000 nút
Mỗi nút có thứ tự con cố định
Chủ yếu truy vấn cha, con, subtree và nhãn
Cập nhật theo batch hằng ngày
```

### Phương án con trỏ

Nếu mỗi nút lưu hai liên kết 64 bit theo dạng first-child/next-sibling, riêng vùng liên kết đã dùng:

\[
1.000.000\times2\times8
=16.000.000\text{ byte}.
\]

Đây **chỉ là một giả thiết** về hai con trỏ 8 byte, chưa tính đối tượng nút, nhãn, allocator và alignment.

### Phương án BP

BP topology:

\[
2n=2.000.000\text{ bit}
=250.000\text{ byte}.
\]

Tức giảm rất mạnh vùng dữ liệu **topology**, nhưng phải cộng:

- Directory điều hướng match/enclose/rank/select nếu cần tốc độ cao.
- Mảng nhãn/ID theo preorder.
- Metadata n, version và serialization.
- Bộ nhớ tạm khi dựng lại hằng ngày.
- Bảng ánh xạ ID ổn định nếu ứng dụng cần.

### Quyết định thực tế

Nếu các truy vấn nhiều và cập nhật theo đợt, một BP tĩnh có chỉ mục succinct hoặc directory tối ưu là ứng viên tốt. Nếu hàng triệu nút bị chèn/xóa tương tác liên tục, cần benchmark dynamic BP hoặc một biểu diễn cây khác.

Không được lấy **250.000 byte** làm tổng RAM của toàn ứng dụng.

## 40. Checklist kiểm thử và lỗi dễ gặp

| Lỗi thường gặp | Hậu quả | Cách kiểm tra/sửa |
|---|---|---|
| Chấp nhận `()()` như cây một gốc | Giải mã thành rừng | Yêu cầu excess dương trước cuối |
| Chỉ so số dấu mở và đóng | Có thể bỏ sót prefix âm | Kiểm tra mọi prefix |
| Không giữ thứ tự các con | Cây mã hóa đổi nghĩa | DFS con từ trái sang phải |
| Đóng ngoặc trước khi xử lý hết con | Sai cây con | Emit ')' sau các con |
| Dùng ID nút ngoài làm open position | Sai ánh xạ | Tách ID ứng dụng và BP position |
| Đếm depth bằng E(p+1) | Lệch một | Depth = E(p) |
| Rank preorder gồm cả p sai quy ước | Lệch một | Preorder0 = rank1(p) |
| Postorder ID lấy rank0(q) mà trừ sai | Lệch một | Postorder0 = rank0(q+1)-1 |
| Tính subtree size bằng `close-open` | Không nguyên hoặc thiếu dấu | Dùng `(close-open+1)/2` |
| Cho `firstChild` của lá là `p+1` | Trả ngoặc đóng | Kiểm tra p+1<close(p) |
| Cho nextSibling của root tồn tại | Sai cây một gốc | Root không có anh em |
| Tìm parent bằng ngoặc mở ngay trước | Nhầm anh em thành cha | Dùng stack/enclose |
| Đồng nhất Catalan C_n với cây n nút một gốc | Sai số trạng thái | Số hình dạng là C_(n-1) |
| Cho BP thô mọi truy vấn O(1) | Bỏ qua chi phí index | Nêu rõ quét/array/succinct |
| Gọi mảng match 2n chỉ số là `o(n)` | Sai kế toán bộ nhớ | Chỉ mục đó dùng Θ(n log n) bit tùy width |
| Dùng `sizeof(struct)` làm chi phí BP | Bỏ qua layout | Đo payload/index riêng |
| Bỏ bit_count khi unpack | Lẫn padding thành data | Lưu n hoặc biết schema |
| Không kiểm tra padding cuối byte | Không canonical | Yêu cầu các bit dư bằng 0 |
| Đọc nhãn theo ID ngoài thay vì preorder | Lấy nhãn sai nút | labels[rank1(open)] |
| Cập nhật BP mà giữ chỉ mục cũ | Parent/size/close sai | Rebuild hoặc cập nhật đồng bộ |
| Dùng đệ quy trên đường sâu hàng triệu nút | Có thể tràn stack | DFS lặp với event stack |
| Áp BP ordered-tree cho cây nhị phân thiếu một phía | Mất trái/phải | Thêm bit vị trí hoặc mã chuyên biệt |

## 41. Quy trình chọn và thiết kế biểu diễn BP

Khi một ứng dụng cần lưu cây lớn, hãy đi theo từng bước:

1. **Xác định loại cây:** một gốc hay rừng; ordered hay unordered; nhị phân có vị trí con hay cây tổng quát.
2. **Tách topology và payload:** nhãn, khóa, trọng số, metadata là dữ liệu khác 2n bit.
3. **Chọn quy tắc DFS:** vào nút ghi `(`, rời nút ghi `)`, duyệt con theo thứ tự.
4. **Kiểm tra BP:** độ dài chẵn, prefix không âm, excess về 0 đúng một lần ở cuối nếu là một gốc.
5. **Chọn định danh nút:** open position, preorder index, hoặc ID ứng dụng với bảng ánh xạ.
6. **Liệt kê truy vấn:** parent, first child, sibling, subtree, depth, LCA, degree, kth child, labels.
7. **Chọn chỉ mục:** quét, mảng match/parent, hoặc index succinct theo excess/rank/select.
8. **Tính không gian:** BP payload, padding, index, labels, header, allocator, peak build.
9. **Xác định kiểu cập nhật:** bất biến, rebuild theo batch hay dynamic.
10. **Test** cây một nút, đường dài, sao nhiều con, rừng sai, prefix âm, nhãn/ID và bit padding.
11. **Benchmark** truy vấn/giải mã/dựng index với cây có nhiều hình dạng khác nhau.
12. **Ghi rõ version và wire layout** nếu dữ liệu cần lưu bền vững hoặc truyền giữa hệ thống.

Một cấu trúc BP phù hợp có thể giảm mạnh bộ nhớ topology, nhưng quyết định đúng phải cân bằng **dung lượng, khả năng điều hướng, cập nhật và chi phí triển khai**.

## 42. Bài tập tự kiểm tra có lời giải

**Câu 1.** Một cây có gốc với n nút sinh bao nhiêu dấu ngoặc theo quy tắc DFS của bài?

**Đáp án:** Chính xác **2n** dấu: mỗi nút một ngoặc mở khi vào và một ngoặc đóng khi ra.

**Câu 2.** Nút lá được mã hóa bằng chuỗi nào?

**Đáp án:** `()` vì nút không có cây con nằm giữa hai dấu của nó.

**Câu 3.** Chuỗi `()()` có phải BP của một cây đúng một gốc không?

**Đáp án:** **Không.** Nó cân bằng nhưng biểu diễn hai cây đơn, tức một rừng.

**Câu 4.** Bất biến excess đặc biệt của BP một gốc là gì?

**Đáp án:** `E(0)=E(2n)=0` và `E(i)>0` với mọi `1≤i<2n`.

**Câu 5.** Cây đường ba nút có chuỗi BP nào?

**Đáp án:** `((()))`.

**Câu 6.** Cây một gốc có hai con lá có BP nào?

**Đáp án:** `(()())`.

**Câu 7.** BP của cây ví dụ A có các con B,C,D; B có E,F; D có G là gì?

**Đáp án:** `((()())()(()))`.

**Câu 8.** Chuỗi trên có bao nhiêu nút?

**Đáp án:** 14 dấu ngoặc tương ứng **7 cặp**, tức 7 nút.

**Câu 9.** Trong chuỗi ví dụ, B mở và đóng ở đâu?

**Đáp án:** Mở ở **1**, đóng ở **6**.

**Câu 10.** Kích thước subtree của B bằng bao nhiêu?

**Đáp án:** `(6−1+1)/2=3` nút: B, E, F.

**Câu 11.** D mở ở 9 và đóng ở 12. Subtree D có bao nhiêu nút?

**Đáp án:** `(12−9+1)/2=2` nút: D, G.

**Câu 12.** Độ sâu của một nút có ngoặc mở ở p bằng biểu thức excess nào?

**Đáp án:** **`E(p)`**, không phải `E(p+1)`.

**Câu 13.** Độ sâu của G trong cây ví dụ là bao nhiêu?

**Đáp án:** **2** cạnh từ A qua D tới G.

**Câu 14.** Muốn kiểm tra u là tổ tiên của v, cần so sánh gì?

**Đáp án:** `open(u)≤open(v)<close(u)` nếu “tổ tiên” cho phép u=v.

**Câu 15.** B có phải tổ tiên của C trong ví dụ không?

**Đáp án:** **Không**, vì `open(C)=7>close(B)=6`.

**Câu 16.** Làm sao tìm con đầu tiên của nút có ngoặc mở ở p?

**Đáp án:** Nếu `p+1<close(p)` thì con đầu mở ở `p+1`; nếu không là lá.

**Câu 17.** Anh em kế của B trong ví dụ là nút nào?

**Đáp án:** **C**, ở vị trí mở `close(B)+1=7`, vẫn trước ngoặc đóng của A.

**Câu 18.** Anh em kế của C là nút nào?

**Đáp án:** **D**, ở vị trí mở 9.

**Câu 19.** Một nút root có anh em kế theo mô hình một gốc không?

**Đáp án:** **Không**.

**Câu 20.** Preorder của cây ví dụ là gì?

**Đáp án:** `A,B,E,F,C,D,G`.

**Câu 21.** Postorder của cây ví dụ là gì?

**Đáp án:** `E,F,B,C,G,D,A`.

**Câu 22.** Với ngoặc mở tại p, công thức preorder index bắt đầu từ 0 là gì?

**Đáp án:** `rank1(p)`, nếu `rank1` đếm số ngoặc mở trong `[0,p)`.

**Câu 23.** Với ngoặc đóng tại q, postorder index bắt đầu từ 0 là gì?

**Đáp án:** `rank0(q+1)-1`.

**Câu 24.** Nút preorder thứ k đếm từ 0 có ngoặc mở tại đâu?

**Đáp án:** `select1(k+1)`, nếu `select1` đánh thứ tự từ 1.

**Câu 25.** Subtree của B ứng với khoảng preorder nào trong ví dụ?

**Đáp án:** `[1,4)`, chứa B, E và F.

**Câu 26.** Một BP của n nút cần bao nhiêu byte payload khi đóng theo byte?

**Đáp án:** `⌈2n/8⌉` byte, không tính header và index.

**Câu 27.** Một triệu nút cần bao nhiêu byte topology theo BP?

**Đáp án:** **250.000 byte**, khoảng 244,14 KiB payload bit.

**Câu 28.** Nếu có thêm nhãn 8 byte/nút, có thể nói toàn cây một triệu nút chỉ cần 250.000 byte không?

**Đáp án:** **Không.** Nhãn đã cần thêm khoảng 8.000.000 byte, chưa tính index/metadata.

**Câu 29.** Số hình dạng cây có gốc có thứ tự với n nút là Catalan nào?

**Đáp án:** **`C_{n-1}`**, không phải `C_n`; cặp ngoài cùng thuộc gốc.

**Câu 30.** Với n=3, có bao nhiêu hình dạng?

**Đáp án:** `C_2=2`: đường ba nút và gốc có hai con lá.

**Câu 31.** Với n=7, có bao nhiêu hình dạng và chặn mã cố định là bao nhiêu bit?

**Đáp án:** `C_6=132` hình dạng, cần ít nhất `⌈log₂132⌉=8` bit.

**Câu 32.** Tại sao BP dùng 14 bit cho n=7 dù chặn ở câu 31 chỉ 8 bit?

**Đáp án:** BP chọn mã mang cấu trúc để điều hướng dễ; nó không nhất thiết tối ưu tuyệt đối với n nhỏ, nhưng sát chặn thông tin tiệm cận.

**Câu 33.** Vì sao chỉ lưu hai bit mỗi nút chưa bảo đảm `findClose` O(1)?

**Đáp án:** Không có chỉ mục, có thể phải quét qua toàn subtree tới ngoặc đóng tương ứng.

**Câu 34.** Mảng `match` hai chiều cho mọi vị trí cho thời gian `findClose` bao nhiêu?

**Đáp án:** **O(1)** sau khi dựng, nhưng phải dùng **O(n)** phần tử chỉ số rộng.

**Câu 35.** Biểu thức excess qua rank là gì nếu ngoặc mở là bit 1?

**Đáp án:** `E(i)=2rank1(i)-i`.

**Câu 36.** Chỉ có rank/select ngoặc mở/đóng đã đủ tìm mọi cặp ngoặc O(1) chưa?

**Đáp án:** **Chưa.** Cần thêm hỗ trợ cấu trúc lồng nhau, ví dụ chỉ mục tìm mức excess.

**Câu 37.** Chỉ mục range min–max hỗ trợ điều gì?

**Đáp án:** Giúp tìm các vùng có thể chứa mức excess mục tiêu để tăng tốc matching và các phép điều hướng.

**Câu 38.** `2n+o(n)` bit mô tả điều gì?

**Đáp án:** 2n bit topology BP cộng thêm lượng chỉ mục phụ tăng chậm hơn tuyến tính, dưới mô hình phù hợp.

**Câu 39.** Vì sao mảng `parent` hoặc `match` bằng chỉ số 32/64 bit cho mỗi nút chưa đạt overhead `o(n)`?

**Đáp án:** Tổng số bit phụ vẫn **tỷ lệ n** hoặc lớn hơn, không phải thấp hơn tuyến tính.

**Câu 40.** Khi chèn lá vào giữa một BP bitstream liền mạch, điều gì xảy ra?

**Đáp án:** Phải chèn một cặp `()` và có thể dịch cả suffix; vị trí nút và chỉ mục cũ bị thay đổi.

**Câu 41.** Nếu ứng dụng cần giữ ID node ổn định qua cập nhật, BP open position có đủ không?

**Đáp án:** **Không.** Cần ánh xạ ID hoặc cấu trúc khác hỗ trợ ID bền vững.

**Câu 42.** Vì sao dạng cây nhị phân chỉ còn một con có thể bị mất thông tin khi dùng BP ordered-tree thông thường?

**Đáp án:** BP giữ danh sách con hiện diện theo thứ tự, nhưng không tự ghi **con duy nhất là trái hay phải**; phải thêm bit/ràng buộc.

**Câu 43.** Nếu muốn lấy nhãn của một nút mở ở p và nhãn lưu theo preorder, truy vấn gì?

**Đáp án:** `labels[rank1(p)]`.

**Câu 44.** LCA của E và F trong cây ví dụ là gì?

**Đáp án:** **B**.

**Câu 45.** Điều gì cần đảm bảo khi cập nhật BP cùng chỉ mục trong hệ đa luồng?

**Đáp án:** BP và chỉ mục phải thuộc cùng một phiên bản nhất quán, chẳng hạn publish snapshot bất biến mới một cách an toàn.

## Ghi nhớ

- Một **cây có gốc có thứ tự các con** được mã hóa bằng DFS: **vào nút ghi `(`, ra nút ghi `)`**. Mỗi nút tạo một cặp, nên topology cần **2n bit logic** khi đóng gói ngoặc thành bit.
- Dãy BP hợp lệ cho **một gốc** có excess bắt đầu và kết thúc ở 0, đồng thời **dương ở mọi tiền tố nội bộ**. `()()` là một rừng, không phải một cây duy nhất.
- **Ngoặc mở đại diện cho nút**; ngoặc đóng ghép tương ứng xác định đoạn subtree. `subtreeSize(v)=(close(v)-open(v)+1)/2` và `depth(v)=E(open(v))`.
- **Con đầu** mở ngay sau ngoặc mở của cha nếu nút không phải lá; **anh em kế** mở ngay sau ngoặc đóng của nút hiện tại nếu vẫn nằm trong cặp ngoặc của cha. Quan hệ **tổ tiên** được kiểm tra bằng sự lồng nhau của hai đoạn.
- Với `'('=1`, `')'=0`: **`preorder0(v)=rank1(open(v))`**, **`postorder0(v)=rank0(close(v)+1)-1`**. Nhãn có thể lưu liên tục theo preorder, nhưng chúng **không nằm trong 2n bit topology**.
- Số hình dạng cây có gốc có thứ tự với n nút là **`C_{n-1}`**. BP dùng 2n bit, chỉ cách chặn thông tin `log₂C_{n-1}` một lượng bậc `O(log n)` khi n lớn.
- **BP thô không tự hỗ trợ mọi truy vấn O(1).** Mảng match/parent là cách học dễ nhưng tốn nhiều bit phụ; cấu trúc succinct `2n+o(n)` cần chỉ mục trên **rank/select, excess và min–max** cùng phân tích cụ thể.
- BP đặc biệt hợp với **cây lớn, ít cập nhật, truy vấn nhiều**. Khi chèn/xóa hoặc cần ID ổn định, phải cân nhắc chỉ mục động, rebuild theo batch hoặc một cấu trúc cây khác.
