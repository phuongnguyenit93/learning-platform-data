# Trie nén và việc gộp chuỗi cạnh một con

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Trie nén và việc gộp chuỗi cạnh một con

Một trie thông thường lưu khóa `computer` bằng chuỗi cạnh `c→o→m→p→u→t→e→r`. Nếu không có khóa nào khác dùng các tiền tố trung gian, bảy nút nằm giữa gốc và ký tự cuối không tạo lựa chọn phân nhánh và cũng không phải điểm kết thúc khóa. Tuy vậy, chúng vẫn giữ nút, bảng con và con trỏ.

**Trie nén** (*compressed trie*, hay *radix trie* trong cách biểu diễn của bài) gộp những đoạn đường như vậy thành **một cạnh mang nhãn chuỗi**:

```text
Trie thường:
root -c-> o -m-> p -u-> t -e-> r*
        (mỗi cạnh một ký hiệu; các nút trung gian)

Trie nén:
root ----"computer"----> *
```

Dấu `*` nghĩa là nút **terminal**, tức chuỗi trên đường từ gốc đến nó là một khóa hoàn chỉnh. Trie nén giữ đúng tập khóa nhưng cần ít nút hơn. Ngược lại, thêm/xóa khóa nay phải xử lý **tách cạnh ở giữa nhãn**, **gộp nhãn cạnh** và những truy vấn tiền tố có thể kết thúc **giữa một cạnh**.

Bài học thuộc chương **Trie và chỉ mục chuỗi** trong mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Mục tiêu chung là hiểu bất biến, các phép toán và chi phí thời gian–bộ nhớ để lựa chọn cấu trúc phù hợp. Việc nén trie cho thấy một đánh đổi điển hình: giảm metadata và số con trỏ có thể làm tăng chi phí xử lý nhãn khi cập nhật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa **nén đường đi một con**, phân biệt trie không nén và trie nén cạnh.
2. Nêu điều kiện **chỉ gộp nút không terminal có đúng một con**; không được xóa nút terminal chỉ vì nó có một con.
3. Mô tả bất biến nhãn cạnh không rỗng, nhãn khác ký hiệu đầu tại cùng nút và dấu kết thúc khóa.
4. Xử lý bốn trường hợp chèn: thêm nhánh, khớp hết cạnh, phân kỳ giữa cạnh và khóa mới kết thúc giữa cạnh.
5. Xóa khóa và đưa trie trở về **dạng nén chuẩn** bằng việc dọn nhánh chết và gộp nút một con.
6. Tìm khóa chính xác và đếm/liệt kê theo tiền tố, kể cả khi tiền tố kết thúc giữa nhãn.
7. Cài đặt `RadixTrieSet` bằng Python và kiểm thử bằng tập tham chiếu.
8. Phân tích số nút, tổng độ dài nhãn, số ký hiệu so sánh và chi phí **cắt/nối chuỗi** khi cập nhật.
9. Nhận biết ảnh hưởng của Unicode và cách biểu diễn nhãn cạnh đối với chi phí thực tế.
10. So sánh trie nén với trie thường, Hash Set và cấu trúc chuỗi khác theo workload.

## 2. Điều gì thực sự được nén?

Trong trie không nén, **mỗi cạnh mang đúng một ký hiệu**. Một nút có thể mang ba loại thông tin:

- Nó là **gốc**, biểu diễn tiền tố rỗng.
- Nó là **terminal**, biểu diễn một khóa đã lưu.
- Nó là **điểm phân nhánh**, nơi các khóa có chung tiền tố bắt đầu khác nhau.

Nếu một nút không phải gốc, không terminal và có đúng một con, ta có thể bỏ nó mà không làm mất thông tin nào về các khóa.

### 2.1. Ví dụ một đường một con

Trước nén:

```text
parent --"ab"--> X --"cde"--> child*
                    |
                 terminal=False
                 đúng một con
```

Sau nén:

```text
parent --"abcde"--> child*
```

Phép gộp thay hai nhãn liên tiếp bằng phép nối `"ab"+"cde"`. Mọi đường tới khóa ở dưới `child` vẫn mang dãy ký hiệu cũ.

### 2.2. Khi nào **không** được gộp?

Với tập `{"an","anh"}`:

```text
root --"an"--> X* --"h"--> Y*
```

Nút `X` là **terminal**, nên phải giữ để nhận biết `an` là khóa hoàn chỉnh. Nếu bỏ `X` và dùng một cạnh `"anh"` duy nhất, trie sẽ mất khóa `an`.

Vì thế điều kiện nén chuẩn là:

> Mỗi nút **khác gốc và không terminal** phải có **ít nhất hai con**.

Nút terminal có thể có 0, 1 hoặc nhiều con. Gốc là ngoại lệ, có thể không có con hoặc có đúng một con.

### 2.3. Nén nút không giống nén nội dung chuỗi

Với một khóa dài `L` và không có phân nhánh:

- Trie thường có `L+1` nút nếu `L>0`.
- Trie nén có gốc và một nút terminal, tổng **2 nút**.
- Nhãn cạnh của trie nén vẫn phải chứa `L` ký hiệu.

Lợi ích chủ yếu là giảm **nút, con trỏ và vùng chứa nhánh**, không phải làm biến mất dữ liệu ký hiệu.

## 3. Biểu diễn trie nén cạnh

Ta chọn một trie có gốc. Mỗi cạnh mang **một chuỗi không rỗng**, thay vì một ký hiệu.

Một nút lưu:

```text
Node:
    children: first_char -> (edge_label, child_node)
    terminal: Boolean
    subtree_count: số khóa hoàn chỉnh trong cây con
```

Ví dụ:

```text
K = {"an", "anh", "ang", "ao", "ban"}

                   root
                  /    \
                "a"    "ban"
                 |        |
                 A        *
                / \
              "n" "o"
               |   |
               B*  *
              / \
            "g" "h"
             |   |
             *   *
```

Ghép các nhãn cạnh cho đường tương ứng:

- `"a"+"n" = "an"`.
- `"a"+"n"+"h" = "anh"`.
- `"a"+"n"+"g" = "ang"`.
- `"a"+"o" = "ao"`.
- `"ban" = "ban"`.

Nút `A` không terminal nhưng có hai nhánh, nên cần giữ. Nút `B` terminal dù còn hai con. Nhánh `ban` được nén thành một cạnh.

### 3.1. Độ sâu theo cạnh khác độ dài khóa

Với nhánh `ban`:

- Độ dài khóa là 3 ký hiệu.
- Đường đi từ gốc tới nút cuối chỉ qua 1 cạnh.

Nếu dùng biến `q` cho **số cạnh được đi qua** và `L` cho **số ký hiệu của khóa**, ta có `q≤L` trong trie nén không có nhãn cạnh rỗng. Nhưng **không thể suy rằng thời gian tìm chỉ O(q)**: mỗi nhãn dài vẫn phải được so khớp.

### 3.2. Vì sao dictionary con được đánh chỉ số theo ký hiệu đầu?

Mỗi cạnh tại nút có một nhãn chuỗi. Hai cạnh khác nhau **không được bắt đầu bằng cùng một ký hiệu**; nếu có phần đầu chung, phải tách thành một đoạn chung trước khi phân nhánh.

Vì thế có thể dùng:

```python
children = {
    "c": ("cat", child_cat),
    "d": ("dog", child_dog),
}
```

Ánh xạ này chọn đúng một cạnh theo ký hiệu đầu đang đọc. Sau khi chọn cạnh, thuật toán vẫn phải kiểm tra **toàn bộ nhãn**.

## 4. Bất biến biểu diễn

Với `K` là tập các khóa đang lưu và `label(v)` là chuỗi nối nhãn từ gốc tới nút `v`, một trie nén chuẩn thỏa:

1. **Gốc luôn tồn tại**, mang chuỗi rỗng.
2. Mọi cạnh có nhãn `str` **không rỗng**.
3. Từ một nút, không có hai cạnh có cùng **ký hiệu đầu**.
4. Mọi nút ngoài gốc có một cha duy nhất; cấu trúc không có chu trình.
5. `terminal(v)=True` khi và chỉ khi `label(v)∈K`.
6. Mọi nút khác gốc **không terminal** có ít nhất hai con.
7. Mọi nút khác gốc tồn tại đều nằm trên đường tới ít nhất một khóa terminal.
8. Nếu có `subtree_count`, nó bằng số khóa hoàn chỉnh trong cây con:

\[
count(v)=\mathbf 1_{terminal(v)}
+\sum_{u\in children(v)}count(u).
\]

Do đó:

\[
count(root)=|K|.
\]

### 4.1. Bất biến về ký hiệu đầu

Cho hai khóa `cat` và `car`. Không thể để gốc chứa cả hai cạnh `"cat"` và `"car"` vì cùng bắt đầu bằng `c`. Biểu diễn nén đúng là:

```text
root --"ca"--> X
                / \
              "t" "r"
               |   |
               *   *
```

Nút `X` không terminal nhưng có hai con. Những nhãn từ `X` bắt đầu bằng `t` và `r`, khác nhau.

### 4.2. Khóa rỗng là trường hợp tại gốc

Nếu `""` được phép lưu, ta đặt `root.terminal=True`. Gốc có thể vừa terminal vừa có cạnh cho các khóa không rỗng. Không tạo cạnh nhãn rỗng để biểu diễn khóa rỗng.

### 4.3. Không phải tiền tố nào cũng có nút

Trong trie thường, mọi ký hiệu dọc đường đi kết thúc tại một nút. Với cạnh `"alphabet"`, tiền tố `a`, `al`, `alp` có thể **chỉ là vị trí giữa nhãn**, không phải nút thật. Đây là khác biệt quan trọng khi tìm tiền tố và chèn khóa ngắn.

## 5. Tiền tố chung dài nhất (LCP) là thao tác nền tảng

Khi chèn hoặc tìm, ta so sánh phần khóa chưa đọc với nhãn cạnh hiện tại.

Gọi `remaining` là phần khóa còn lại, `edge` là nhãn cạnh. LCP (*longest common prefix*) là dãy ký hiệu dài nhất đứng đầu cả hai.

| `remaining` | `edge` | LCP | Kết luận |
| --- | --- | --- | --- |
| `cater` | `cat` | `cat` | Khớp toàn bộ nhãn, đi tiếp |
| `car` | `cat` | `ca` | Phân kỳ giữa cạnh |
| `cat` | `cater` | `cat` | Khóa kết thúc giữa cạnh |
| `cater` | `cater` | `cater` | Khớp hết cả cạnh và khóa |
| `caz` | `cat` | `ca` | Không khớp toàn bộ cạnh |

### 5.1. Phân chia các trường hợp

Gọi `j` là độ dài LCP, `a` là số ký hiệu còn lại của truy vấn và `b` là độ dài nhãn:

- `j=b`: đi hết cạnh; có thể tiếp tục tới nút sau cạnh.
- `j=a<b`: truy vấn kết thúc ở **giữa cạnh**.
- `0<j<a` và `j<b`: phân kỳ ở giữa cạnh.
- Không có cạnh ứng với ký hiệu đầu: tìm thất bại hoặc chèn một nhánh mới.

Nếu chọn được cạnh bằng ký hiệu đầu, `j≥1`. Điều đó giúp khi tách cạnh, đoạn chung luôn không rỗng.

### 5.2. Không cần tạo `word[offset:]` để so khớp

Một cài đặt có thể giữ chỉ số `offset` vào khóa gốc và so sánh `word[offset+j]` với `edge[j]`. Nhờ vậy, chỉ riêng **việc so sánh** không phải sao chép chuỗi đầu vào tại mỗi bước.

Tuy nhiên, nếu cần tạo nhãn cạnh mới sau khi tách, phép cắt `edge[j:]` có thể vẫn sao chép chuỗi cũ dài; đó là chi phí khác, sẽ phân tích riêng.

## 6. Tìm khóa đầy đủ: chỉ chấp nhận nút terminal

Ví dụ trie chỉ lưu `"cater"` bằng một cạnh:

```text
root --"cater"--> *
```

Kết quả:

| Truy vấn | Đúng là tiền tố của khóa? | `contains` |
| --- | --- | --- |
| `cat` | Có | False |
| `cate` | Có | False |
| `cater` | Có | True |
| `caz` | Không | False |
| `caterx` | Không | False |

### 6.1. Giả mã

```text
CONTAINS(root, word):
    node = root
    pos = 0

    while pos < len(word):
        edge = node.children.get(word[pos])
        if edge không tồn tại:
            return FALSE

        label, child = edge
        if word[pos:] không bắt đầu bằng TOÀN BỘ label:
            return FALSE

        pos += len(label)
        node = child

    return node.terminal
```

Truy vấn `cat` không khớp **toàn bộ** nhãn `cater`, nên không thể là khóa hoàn chỉnh đang lưu. Nó có thể là tiền tố hợp lệ, nhưng đó là **API khác**.

### 6.2. Bất biến vòng lặp

Sau mỗi lần đi hết một cạnh, `node` đại diện chính xác `word[:pos]`. Nếu thiếu cạnh hoặc nhãn không khớp toàn bộ, không có đường hợp lệ cho khóa. Nếu hết khóa tại nút, `terminal` quyết định tư cách khóa hoàn chỉnh.

Khi `word=""`, vòng lặp không thực hiện bước nào; trả `root.terminal`.

## 7. Tìm và liệt kê theo tiền tố kết thúc giữa cạnh

Trong trie chỉ lưu `"alphabet"`:

```text
root --"alphabet"--> *
```

Tiền tố `"alp"` là hợp lệ mặc dù không có nút sau đúng ba ký hiệu. Một thuật toán tiền tố chỉ chấp nhận khớp khi tới **ranh giới nút** là sai.

### 7.1. Giả mã định vị tiền tố

```text
LOCATE_PREFIX(root, prefix):
    node = root
    pos = 0

    while pos < len(prefix):
        edge = node.children.get(prefix[pos])
        if không có edge:
            return NONE

        label, child = edge
        j = LCP(prefix từ pos, label)

        if j == len(label):
            pos += j
            node = child
            continue

        if pos + j == len(prefix):
            # Tiền tố hết ngay giữa nhãn cạnh.
            return (child, label, j)

        return NONE

    return (node, "", 0)
```

Hàm trả về nút cuối cạnh và thông tin phần nhãn đã dùng. Không cần tạo thêm nút để phục vụ truy vấn tiền tố.

### 7.2. Đếm tiền tố

Nếu `prefix` hết giữa nhãn cạnh `label` dẫn tới nút `child`, mọi khóa trong cây con `child` đều bắt đầu bằng `prefix`. Vì vậy:

\[
count\_prefix(prefix)=count(child).
\]

Nếu không tìm được đường phù hợp, kết quả bằng 0. Nếu tiền tố rỗng, kết quả bằng tổng số khóa tại gốc.

### 7.3. Liệt kê phải dựng đủ ký tự của nhãn cạnh

Nếu `prefix="alp"` và nhãn cạnh là `"alphabet"`, không được bắt đầu phát khóa tại `child` bằng đường `"alp"`, vì sẽ tạo **chuỗi thiếu `habet`**.

Trước khi duyệt từ `child`, hãy nối `prefix` với **phần nhãn còn lại**. Sau đó duyệt các nhãn cạnh trong cây con và chỉ phát tại nút terminal.

## 8. Chèn khóa: thêm nhánh mới và tách cạnh

Một lời gọi `insert(word)` trong trie dạng Set chỉ được tăng số khóa khi `word` **chưa** có.

### 8.1. Thiếu cạnh bắt đầu: tạo một nhánh mang cả hậu tố

Ban đầu:

```text
root --"cat"--> *
```

Chèn `dog`: chưa có nhánh `d`, nên tạo một cạnh `"dog"` tới nút terminal mới. **Không cần** tạo các nút riêng `d,o,g`.

### 8.2. Khớp hết nhãn: đi xuống nút con

Nếu đang có:

```text
root --"ca"--> X --"r"--> Y*
```

và cần chèn `cart`, ta đi qua `"ca"` rồi `"r"`, đến nút `car`, sau đó thêm cạnh `"t"`. Nút `car` vẫn terminal, đồng thời có con.

### 8.3. Phân kỳ giữa cạnh: tách tại LCP

Ban đầu:

```text
root --"cat"--> *
```

Chèn `car`: LCP là `ca`. Kết quả:

```text
root --"ca"--> X
                / \
             "t"   "r"
              |     |
              *     *
```

Nút `X` không terminal, có hai con. Cạnh cũ được tách thành `"ca"` và `"t"`; khóa mới dùng nhánh `"r"`.

### 8.4. Khóa mới kết thúc giữa nhãn cũ

Ban đầu:

```text
root --"cater"--> *
```

Chèn `cat`: LCP là `cat` và khóa mới hết trước khi nhãn cũ hết.

```text
root --"cat"--> X* --"er"--> *
```

Nút `X` mới phải là terminal. Nó có một con nhưng vẫn **hợp lệ** vì là điểm kết thúc khóa.

### 8.5. Bộ đếm sau khi tách

Giả sử `old_child` chứa `c` khóa hoàn chỉnh. Khi thêm một khóa mới qua nút `middle` vừa tạo:

\[
count(middle)=c+1.
\]

`count(old_child)` **giữ nguyên**, vì tập khóa cũ không đổi. Các tổ tiên trên đường tới `middle` tăng 1. Với chèn trùng, không tăng bất kỳ bộ đếm nào.

## 9. Xóa khóa: dọn nhánh và gộp trở về dạng chuẩn

Xóa có hai điều kiện an toàn:

1. **Xác nhận khóa cần xóa tồn tại tại nút terminal** trước khi sửa.
2. Sau khi bỏ terminal, chỉ xóa nhánh không còn khóa; chỉ gộp nút **không terminal có đúng một con**.

### 9.1. Xóa từ ngắn nhưng giữ từ dài

```text
Trước: root --"cat"--> X* --"er"--> Y*
Xóa "cat".
Sau:   root --"cater"--> Y*
```

Nút `X` không còn terminal, chỉ có một con nên bị gộp. Khóa `cater` vẫn còn.

### 9.2. Xóa một nhánh phân kỳ

```text
Trước:
root --"ca"--> X
                / \
             "t"   "r"
              |     |
              *     *

Xóa "car".

Sau:
root --"cat"--> *
```

Sau khi xóa nhánh `r`, nút `X` trở thành không terminal có một con; gộp `ca + t` thành `cat`.

### 9.3. Không được cắt nhánh còn khóa

Nếu có `an` và `anh`:

- Xóa `anh`: bỏ nhánh cuối, giữ nút `an` terminal.
- Xóa `an`: bỏ terminal `an` và gộp cạnh thành `anh`, nhưng không làm mất khóa `anh`.

Nếu gọi xóa một tiền tố `a` chưa được lưu, phải trả False và **giữ nguyên** mọi nút, nhãn và bộ đếm.

### 9.4. Giả mã dọn từ dưới lên

```text
DELETE(root, word):
    đi theo các nhãn cạnh, lưu path các (parent, edge, child)
    nếu thiếu cạnh, khớp một phần hoặc node cuối không terminal:
        return FALSE

    bỏ terminal của node cuối
    giảm count tại root và mọi node thuộc path
    giảm size

    for mỗi cạnh trên path từ dưới lên:
        if child.count == 0:
            xóa cạnh từ parent tới child
        else if child không terminal và có đúng một con:
            gộp nhãn parent->child với nhãn child->grandchild
            nối parent trực tiếp tới grandchild

    return TRUE
```

Không bao giờ gộp gốc. Một nút terminal một con là hợp lệ và không bị loại.

## 10. Cài đặt Python: cấu trúc RadixTrieSet

Ta dùng dictionary:

```text
children[first_char] = (full_label, child_node)
```

Nhãn cạnh không rỗng; khóa dictionary phải là ký hiệu đầu của nhãn. API cho phép khóa rỗng và lưu các khóa **phân biệt**. Mỗi ký hiệu là một code point của `str` Python.

### 10.1. Lớp nút, LCP và tìm chính xác

```python
class RadixNode:
    __slots__ = ("children", "terminal", "subtree_count")

    def __init__(self):
        self.children = {}
        self.terminal = False
        self.subtree_count = 0


class RadixTrieSet:
    def __init__(self):
        self._root = RadixNode()
        self._size = 0

    @staticmethod
    def _validate(text):
        if not isinstance(text, str):
            raise TypeError("khóa/tiền tố phải là str")

    @staticmethod
    def _lcp(word, pos, label):
        """Đếm ký hiệu chung, không tạo word[pos:]."""
        j = 0
        while (
            j < len(label)
            and pos + j < len(word)
            and word[pos + j] == label[j]
        ):
            j += 1
        return j

    def __len__(self):
        return self._size

    def _find_exact_node(self, word):
        node = self._root
        pos = 0

        while pos < len(word):
            edge = node.children.get(word[pos])
            if edge is None:
                return None

            label, child = edge
            if not word.startswith(label, pos):
                return None

            pos += len(label)
            node = child

        return node

    def contains(self, word):
        self._validate(word)
        node = self._find_exact_node(word)
        return node is not None and node.terminal
```

`startswith(label,pos)` phải khớp **toàn bộ nhãn cạnh**; nếu truy vấn hết giữa nhãn, nó không phải khóa hoàn chỉnh.

Các phương thức sau phải đặt **trong cùng lớp `RadixTrieSet`**, ngang mức thụt lề với `contains`.

### 10.2. Chèn và tách cạnh

```python
    def insert(self, word):
        """True nếu thêm mới; False nếu khóa đã tồn tại."""
        self._validate(word)

        node = self._root
        path = [node]
        pos = 0

        while pos < len(word):
            first = word[pos]
            edge = node.children.get(first)

            if edge is None:
                # Một cạnh cho toàn bộ hậu tố còn lại.
                leaf = RadixNode()
                leaf.terminal = True
                leaf.subtree_count = 1
                node.children[first] = (word[pos:], leaf)

                for ancestor in path:
                    ancestor.subtree_count += 1

                self._size += 1
                return True

            label, child = edge
            common = self._lcp(word, pos, label)

            if common == len(label):
                # Nhãn khớp hoàn toàn: đi tới nút con.
                pos += common
                node = child
                path.append(node)
                continue

            # Có chung ký hiệu đầu, nhưng phân kỳ hoặc
            # khóa mới kết thúc ở giữa nhãn cũ.
            middle = RadixNode()
            old_tail = label[common:]
            middle.children[old_tail[0]] = (old_tail, child)
            node.children[first] = (label[:common], middle)

            remaining_start = pos + common

            if remaining_start == len(word):
                middle.terminal = True
            else:
                new_tail = word[remaining_start:]
                leaf = RadixNode()
                leaf.terminal = True
                leaf.subtree_count = 1
                middle.children[new_tail[0]] = (new_tail, leaf)

            # Cây con cũ không đổi; chỉ thêm một khóa.
            middle.subtree_count = child.subtree_count + 1

            for ancestor in path:
                ancestor.subtree_count += 1

            self._size += 1
            return True

        # Khóa kết thúc đúng tại một nút có sẵn.
        if node.terminal:
            return False

        node.terminal = True
        for ancestor in path:
            ancestor.subtree_count += 1

        self._size += 1
        return True
```

Ở nhánh split, `common≥1` do đã chọn cạnh theo ký hiệu đầu, và `common<len(label)` do chưa khớp hết nhãn. Vì vậy `label[:common]` và `old_tail` đều không rỗng. Nếu `new_tail` tồn tại, ký hiệu đầu của nó phải khác `old_tail` do `common` là LCP dài nhất.

### 10.3. Xóa, dọn và gộp

```python
    def delete(self, word):
        """True nếu xóa thành công; False nếu không có khóa."""
        self._validate(word)

        node = self._root
        pos = 0
        path = []  # (parent, first_char, child)

        while pos < len(word):
            first = word[pos]
            edge = node.children.get(first)
            if edge is None:
                return False

            label, child = edge
            if not word.startswith(label, pos):
                return False

            pos += len(label)
            path.append((node, first, child))
            node = child

        if not node.terminal:
            return False

        node.terminal = False
        self._root.subtree_count -= 1

        for _, _, child in path:
            child.subtree_count -= 1

        self._size -= 1

        for parent, first, child in reversed(path):
            if child.subtree_count == 0:
                del parent.children[first]
                continue

            if not child.terminal and len(child.children) == 1:
                # Gộp hai nhãn cạnh đi qua một nút một con.
                parent_label, _ = parent.children[first]
                _, (next_label, grandchild) = next(
                    iter(child.children.items())
                )
                parent.children[first] = (
                    parent_label + next_label,
                    grandchild,
                )

        return True
```

Vòng dọn chạy từ dưới lên. Gộp chỉ thay đổi đường biểu diễn, không đổi nút terminal còn sống hay số khóa trong các cây con được giữ. Sau khi xóa đến rỗng, gốc vẫn tồn tại.

**Chú ý:** phép nối `parent_label+next_label` tạo chuỗi mới. Nếu nhãn rất dài, thời gian của phép nối không thể mặc định O(1).

### 10.4. Định vị tiền tố có thể hết giữa nhãn

```python
    def _prefix_location(self, prefix):
        """Trả (node, edge_label, matched) hoặc None.

        Khi hết giữa một cạnh, node ở cuối cạnh,
        edge_label là nhãn đầy đủ và matched là
        số ký hiệu đầu đã thuộc prefix.
        """
        node = self._root
        pos = 0

        while pos < len(prefix):
            edge = node.children.get(prefix[pos])
            if edge is None:
                return None

            label, child = edge
            common = self._lcp(prefix, pos, label)

            if common == len(label):
                pos += common
                node = child
                continue

            if pos + common == len(prefix):
                return (child, label, common)

            return None

        return (node, "", 0)

    def count_prefix(self, prefix):
        self._validate(prefix)
        location = self._prefix_location(prefix)
        if location is None:
            return 0
        node, _, _ = location
        return node.subtree_count

    def has_key_with_prefix(self, prefix):
        return self.count_prefix(prefix) > 0
```

Nếu `prefix="alp"` dừng giữa cạnh `"alphabet"`, `_prefix_location` trả nút cuối cạnh để đọc `subtree_count`. Không cần sao chép phần đuôi của nhãn chỉ để trả lời **số lượng khóa**.

### 10.5. DFS lặp: liệt kê và khôi phục nhãn

```python
    def iter_keys(self, prefix=""):
        """Generator khóa theo thứ tự code point Unicode."""
        self._validate(prefix)
        location = self._prefix_location(prefix)
        if location is None:
            return

        start, edge_label, matched = location
        path = list(prefix)

        if edge_label:
            # prefix kết thúc giữa cạnh:
            # phải thêm phần nhãn chưa thuộc prefix.
            path.extend(edge_label[matched:])

        # (is_exit, node, incoming_label)
        stack = [(False, start, "")]

        while stack:
            is_exit, node, label = stack.pop()

            if is_exit:
                del path[-len(label):]
                continue

            if label:
                path.extend(label)

            if node.terminal:
                yield "".join(path)

            if label:
                stack.append((True, None, label))

            # Stack LIFO: đẩy nhánh lớn trước.
            edges = sorted(
                node.children.items(),
                key=lambda pair: pair[0],
                reverse=True,
            )
            for _, (child_label, child) in edges:
                stack.append((False, child, child_label))

    def keys_with_prefix(self, prefix="", limit=None):
        self._validate(prefix)

        if limit is not None:
            if type(limit) is not int or limit < 0:
                raise ValueError("limit phải là None hoặc int >= 0")
            if limit == 0:
                return []

        result = []
        for word in self.iter_keys(prefix):
            result.append(word)
            if limit is not None and len(result) >= limit:
                break

        return result
```

Mã duyệt dùng hai loại sự kiện **vào/ra nút** để duy trì danh sách ký hiệu `path`, chỉ tạo chuỗi hoàn chỉnh tại nút terminal. Khi bắt đầu từ tiền tố giữa cạnh, nó thêm **phần còn lại của nhãn** trước khi phát kết quả đầu tiên.

Các nhánh cùng cha có ký hiệu đầu khác nhau, nên `sorted` theo ký hiệu đầu rồi DFS terminal trước con cho thứ tự từ điển theo code point.

## 11. Kiểm thử chèn và tìm khóa

Các đoạn kiểm thử đặt sau khi ghép đầy đủ các phương thức của `RadixTrieSet` ở mục 10.

### 11.1. Tách cạnh hai lần

```python
trie = RadixTrieSet()

assert trie.insert("cater")
assert trie.contains("cater")
assert not trie.contains("cat")
assert trie.count_prefix("cat") == 1
assert trie.keys_with_prefix("ca") == ["cater"]

# Khóa mới kết thúc giữa cạnh.
assert trie.insert("cat")
assert trie.contains("cat")
assert trie.contains("cater")
assert trie.count_prefix("cat") == 2

# Khóa mới phân kỳ giữa cạnh.
assert trie.insert("car")
assert trie.insert("cart")

assert trie.contains("car")
assert trie.contains("cart")
assert trie.contains("cat")
assert trie.contains("cater")

assert not trie.contains("ca")
assert not trie.contains("cate")
assert not trie.contains("caz")

assert len(trie) == 4
assert trie.count_prefix("ca") == 4
assert trie.count_prefix("car") == 2
assert trie.count_prefix("cate") == 1
assert trie.count_prefix("xyz") == 0

assert trie.keys_with_prefix("ca") == [
    "car", "cart", "cat", "cater"
]
assert trie.keys_with_prefix("c", limit=2) == [
    "car", "cart"
]

# Chèn trùng không tăng bộ đếm.
assert not trie.insert("cater")
assert len(trie) == 4
```

### 11.2. Thêm nhánh khác

```python
assert trie.insert("do")
assert trie.insert("dog")
assert len(trie) == 6
assert trie.count_prefix("do") == 2
assert trie.keys_with_prefix("d") == ["do", "dog"]
assert trie.keys_with_prefix("") == [
    "car", "cart", "cat", "cater", "do", "dog"
]
```

### 11.3. Xóa và nén lại

```python
assert trie.delete("cart")
assert trie.contains("car")
assert trie.count_prefix("ca") == 3

assert trie.delete("car")
assert not trie.contains("car")
assert trie.contains("cat")
assert trie.contains("cater")
assert trie.count_prefix("ca") == 2

assert trie.delete("cat")
assert not trie.contains("cat")
assert trie.contains("cater")
assert trie.count_prefix("cate") == 1
assert trie.keys_with_prefix("cat") == ["cater"]

# "cate" chỉ là vị trí giữa nhãn.
assert not trie.delete("cate")
assert trie.contains("cater")

assert trie.delete("cater")
assert trie.keys_with_prefix("c") == []
assert trie.contains("do")
assert trie.contains("dog")

# Xóa "do" nhưng vẫn giữ "dog".
assert trie.delete("do")
assert not trie.contains("do")
assert trie.contains("dog")
assert trie.keys_with_prefix("d") == ["dog"]

assert trie.delete("dog")
assert len(trie) == 0
assert trie.count_prefix("") == 0
assert not trie.delete("dog")
```

### 11.4. Chuỗi rỗng

```python
empty = RadixTrieSet()

assert not empty.contains("")
assert empty.count_prefix("") == 0
assert empty.keys_with_prefix("") == []

assert empty.insert("")
assert empty.contains("")
assert empty.count_prefix("") == 1
assert empty.keys_with_prefix("") == [""]

assert empty.insert("abc")
assert empty.keys_with_prefix("") == ["", "abc"]
assert empty.keys_with_prefix("ab") == ["abc"]

assert empty.delete("")
assert not empty.contains("")
assert empty.contains("abc")
assert empty.count_prefix("") == 1
assert empty.delete("abc")
assert len(empty) == 0
```

## 12. Kiểm tra bất biến của cấu trúc sau cập nhật

Bài kiểm thử `contains` không đủ phát hiện mọi lỗi: một trie có thể tìm đúng từ nhưng giữ **nút không terminal một con** hoặc bộ đếm sai.

### 12.1. Hàm kiểm tra toàn cây

```python
def validate_radix(trie):
    root = trie._root
    seen = set()
    totals = {}
    stack = [(root, False)]

    while stack:
        node, expanded = stack.pop()

        if not expanded:
            assert id(node) not in seen
            seen.add(id(node))

            if node is not root and not node.terminal:
                assert len(node.children) >= 2

            stack.append((node, True))
            for first, (label, child) in node.children.items():
                assert isinstance(label, str) and label
                assert first == label[0]
                assert isinstance(child, RadixNode)
                stack.append((child, False))
        else:
            expected = int(node.terminal)
            for _, child in node.children.values():
                assert totals[id(child)] > 0
                expected += totals[id(child)]

            assert node.subtree_count == expected
            totals[id(node)] = expected

    assert totals[id(root)] == len(trie)


sample = RadixTrieSet()

for word in ["cater", "cat", "car", "cart", "do", "dog", ""]:
    assert sample.insert(word)
    validate_radix(sample)

for word in ["car", "cart", "cat", "cater", "", "do", "dog"]:
    assert sample.delete(word)
    validate_radix(sample)

assert len(sample) == 0
```

Hàm kiểm tra duyệt toàn bộ trie nên phù hợp cho **unit test hoặc debug**, không cần chạy sau mọi lần cập nhật ở hệ thống có lưu lượng cao.

### 12.2. Đối chiếu với Set độc lập

```python
def check_against_set(trie, reference, prefixes):
    assert len(trie) == len(reference)

    for prefix in prefixes:
        expected = sorted(
            key for key in reference
            if key.startswith(prefix)
        )
        assert trie.keys_with_prefix(prefix) == expected
        assert trie.count_prefix(prefix) == len(expected)


sample = RadixTrieSet()
reference = set()

for word in ["", "alphabet", "alp", "alpine", "alps", "abc", "a"]:
    sample.insert(word)
    reference.add(word)
    check_against_set(
        sample, reference, ["", "a", "al", "alp", "alph"]
    )

for word in ["alp", "alps", "alphabet", "a", "", "missing"]:
    sample.delete(word)
    reference.discard(word)
    check_against_set(
        sample, reference, ["", "a", "al", "alp", "alph"]
    )
```

Mô hình tham chiếu quét nhiều khóa và có thể chậm, nhưng giúp phát hiện lỗi độc lập với hình dạng nén cạnh.

## 13. Vì sao tách và gộp không làm sai tập khóa?

### 13.1. Chứng minh cho tách cạnh

Trước khi tách, một cạnh mang nhãn `label` từ `parent` tới `old_child`. Ta chọn:

```text
common   = label[:j]
old_tail = label[j:]
```

Rồi thay bằng:

```text
parent --common--> middle --old_tail--> old_child
```

Vì `common+old_tail=label`, **mọi đường cũ tới nút terminal dưới `old_child` vẫn có cùng dãy ký hiệu**. Thêm một nhánh mới hoặc đặt terminal tại `middle` làm xuất hiện đúng một khóa mới.

Do `j` là LCP dài nhất, nếu nhánh mới tồn tại thì ký hiệu đầu của hậu tố mới khác ký hiệu đầu `old_tail`. Bất biến cạnh ra vẫn đúng.

### 13.2. Chứng minh cho gộp cạnh

Giả sử `middle` không terminal và có đúng một con:

```text
parent --a--> middle --b--> child
```

Thay bằng `parent --(a+b)--> child`. Vì `middle` không terminal, không khóa nào kết thúc tại nó. Vì chỉ có một con, mọi khóa đi qua `middle` đều phải đi tiếp qua `b`.

Do đó không có khóa nào mất hoặc xuất hiện thêm.

### 13.3. Vì sao xóa nhánh count bằng 0 là đúng?

Theo bất biến `count(v)` bằng số nút terminal trong cây con `v`. Nếu `count(child)=0`, cây con ấy không chứa khóa hoàn chỉnh nào. Cắt cạnh tới nó không ảnh hưởng tập khóa còn sống.

Nếu `count(child)>0`, không được cắt: ít nhất một khóa vẫn cần đường ấy.

### 13.4. Kết luận tính đúng theo quy nạp

Trie rỗng ban đầu thỏa bất biến. Chèn thêm một khóa đúng một lần và giữ các khóa cũ; xóa bỏ đúng một khóa và chỉ dọn/gộp những đoạn không cần cho khóa khác. Vì vậy, theo quy nạp trên số thao tác, cấu trúc tiếp tục biểu diễn đúng tập khóa sau mọi chuỗi chèn/xóa hợp lệ.

## 14. Thời gian: phải tính cả so khớp nhãn cạnh

Gọi:

- `L`: số ký hiệu của khóa.
- `P`: số ký hiệu tiền tố truy vấn.
- `q`: số cạnh nén đã đi qua trên một đường.
- `d_v`: số nhánh tại nút `v`.
- `σ`: kích thước bảng ký hiệu.
- `g(d_v,σ)`: chi phí chọn một cạnh bằng ký hiệu đầu.
- `B`: tổng độ dài các **chuỗi nhãn mới phải sao chép** khi split/merge.

Vì mọi nhãn cạnh không rỗng, `q≤L` trên đường tới khóa đầy đủ không rỗng.

### 14.1. Tìm và kiểm tra tiền tố

Tìm phải chọn các cạnh và so khớp nhãn. Với một thuật toán không so lại đoạn đã đọc, tổng số ký hiệu so khớp trên đường truy vấn không vượt một lượng tuyến tính theo `L`:

\[
T_{\mathrm{contains}}
=O\left(L+1+\sum_{\text{nút đã thăm}}g(d_v,σ)\right).
\]

Nếu dùng dictionary con và tra một ký hiệu có chi phí **O(1) kỳ vọng**, ta có:

\[
T_{\mathrm{contains}}=O(L+1)\quad\text{kỳ vọng}.
\]

Định vị tiền tố tương tự, với `P` thay `L`; nhờ bộ đếm cây con, `count_prefix` có thể hoàn thành trong O(P+1) kỳ vọng.

**Không được nói O(q)** chỉ vì q nhỏ: một nhãn cạnh duy nhất có thể chứa hàng triệu ký hiệu cần so sánh.

### 14.2. Chèn và xóa: chi phí sao chép nhãn

Mã Python dùng thao tác:

```python
old_tail = label[common:]
new_head = label[:common]
merged = parent_label + next_label
```

`str` bất biến; cắt/nối tạo chuỗi mới và có thể sao chép dữ liệu. Vì thế chặn hữu ích là:

\[
T_{\mathrm{update}}=
O\left(L+1+\sum g(d_v,σ)+B\right),
\]

với `B` là tổng số ký hiệu được sao chép vào các nhãn mới, cộng những chi phí runtime/allocator nếu cần phân tích độ trễ thực tế.

**Không có bảo đảm `B≤L`** trong cài đặt này.

### 14.3. Phản ví dụ xóa khóa rất ngắn

Cho:

```text
K = {"a", "a" + "x" * 1000000}
```

Trie nén có nút terminal `a` và một cạnh con mang nhãn một triệu ký hiệu `x`. Xóa khóa `a` (dài 1 ký hiệu) khiến nút ấy không terminal một con, nên cần gộp:

```text
"a" + "x"*1000000
```

Tạo chuỗi mới dài hơn một triệu ký hiệu. Thời gian xóa **không thể được mô tả đầy đủ bằng O(L) với `L=1`** trong mô hình sao chép `str`.

### 14.4. Phản ví dụ tương tự khi chèn

Ban đầu chỉ lưu `"a"+"x"*1000000`, là một cạnh rất dài. Chèn `ab` yêu cầu tách sau ký hiệu `a`, tạo hậu tố cũ `"x"*1000000`.

Khóa mới dài 2 ký hiệu, nhưng việc tạo `old_tail` có thể phải sao chép gần một triệu ký hiệu. Vì vậy, lợi thế ít nút đi kèm chi phí **xử lý nhãn dài** khi cập nhật.

### 14.5. Có cách tránh sao chép dài không?

Có thể dùng:

- Tham chiếu tới một đoạn trong vùng lưu chuỗi gốc, với thông tin vị trí đầu/cuối và quy tắc vòng đời dữ liệu.
- Rope hoặc cấu trúc các đoạn chuỗi có thể nối mà không sao chép toàn bộ.
- Cơ chế nén đường lười, kèm một quá trình chuẩn hóa nén sau.
- Vùng dữ liệu byte được chia sẻ và các chỉ mục đoạn.

Những lựa chọn này cần bất biến riêng về vòng đời nhãn và chi phí so khớp; không được tự kết luận mọi cập nhật đều O(L) nếu chưa đặc tả phép thao tác trên nhãn.

## 15. Bộ nhớ: ít nút hơn nhưng không mất dữ liệu ký hiệu

Gọi `n` là số khóa phân biệt, `S` là tổng độ dài của các khóa và `N_c` là số nút trie nén.

Trie không nén có:

\[
N_{\mathrm{plain}}\le S+1.
\]

Trong trie nén chuẩn, mỗi nút ngoài gốc là **terminal** hoặc là **nút phân nhánh không terminal với ít nhất hai con**. Số nút terminal không vượt `n`, còn số nút phân nhánh được chặn tuyến tính theo số khóa terminal.

Một chặn đơn giản là:

\[
N_c=O(n+1),\qquad N_c\le 2n+1.
\]

### 15.1. Tổng độ dài nhãn cạnh

Đặt `A` là tổng số ký hiệu của **mọi nhãn cạnh đang lưu**, mỗi cạnh đếm một lần.

Mỗi cạnh nằm trên đường của ít nhất một khóa hoàn chỉnh; vì thế:

\[
A\le S.
\]

Trong mô hình một nút và một mục cạnh có overhead hằng số, bộ nhớ có dạng:

\[
M_{\mathrm{radix}}=O(N_c+A)=O(n+S).
\]

Điều này không khẳng định luôn ít byte hơn Hash Set: còn đối tượng chuỗi nhãn, dictionary con, cờ terminal, bộ đếm và metadata cấp phát.

### 15.2. Tiền tố chung được lưu một lần

Cho 26 từ, mỗi từ gồm 100 ký hiệu `a` rồi một chữ cuối khác nhau `a,b,\ldots,z`.

- Tổng ký hiệu các khóa: `S=26\cdot101=2626`.
- Trie thường có 100 nút cho đường chung, 26 nút cuối và gốc: `127` nút.
- Trie nén có gốc, một nút phân nhánh sau nhãn `a` lặp 100 lần, và 26 nút terminal: **28 nút**.
- Đoạn `a` dài 100 ký hiệu được lưu một lần ở nhãn cạnh gốc tới nút phân nhánh.

Lợi ích ở ví dụ là giảm hàng chục nút metadata, trong khi vẫn giữ các ký hiệu cần phân biệt 26 từ.

### 15.3. Bộ nhớ tạm

Trong cài đặt Python:

- `insert` giữ `path` có tối đa O(q) tham chiếu.
- `delete` giữ các bộ ba cha–con trên đường, O(q) phần tử.
- Split/merge có thể tạo các chuỗi tạm dài O(B) ký hiệu.
- `keys_with_prefix` xây danh sách kết quả; tổng ký hiệu đầu ra `Z` có thể rất lớn.
- Generator `iter_keys` tránh giữ toàn bộ danh sách nhưng vẫn tạo từng chuỗi đầy đủ tại nút terminal.

Phân tích **bộ nhớ cấu trúc**, **bộ nhớ phụ tạm** và **bộ nhớ kết quả** nên được trình bày riêng.

## 16. Unicode, ký hiệu và ranh giới nén

Mã ở mục 10 duyệt chuỗi Python theo **Unicode code point**. Người dùng có thể thấy một chữ có dấu, nhưng dữ liệu được biểu diễn bởi một code point tổ hợp sẵn hoặc nhiều code point kết hợp.

### 16.1. Hai chuỗi hiển thị giống nhau

```python
import unicodedata

composed = "bàn"
decomposed = "ba\u0300n"

assert composed != decomposed
assert (
    unicodedata.normalize("NFC", composed)
    == unicodedata.normalize("NFC", decomposed)
)
```

Nếu ứng dụng xem chúng là một khóa, phải chuẩn hóa **khi chèn, tìm, xóa và tìm tiền tố**, không chỉ ở một thao tác.

### 16.2. Ví dụ chuẩn hóa NFC

```python
import unicodedata


def normalize_key(text):
    if not isinstance(text, str):
        raise TypeError("khóa phải là str")
    return unicodedata.normalize("NFC", text)


trie = RadixTrieSet()
assert trie.insert(normalize_key("bàn"))
assert trie.contains(normalize_key("ba\u0300n"))
assert trie.keys_with_prefix(normalize_key("bà")) == ["bàn"]
```

`NFC` không có nghĩa loại bỏ dấu; `ban` và `bàn` vẫn khác nhau. Nếu ứng dụng cần không phân biệt hoa/thường, có thể thêm `casefold` nhưng phải kiểm tra khả năng nó làm thay đổi dãy ký hiệu.

### 16.3. Độ dài khóa phụ thuộc loại ký hiệu

Một trie trên byte UTF-8, một trie trên code point và một trie trên **grapheme cluster** có thể dùng các giá trị `L` khác nhau cho cùng một chuỗi hiển thị.

Nếu cho phép truy vấn tiền tố kết thúc giữa một grapheme cluster, hành vi có thể không phù hợp với trải nghiệm nhập liệu. Cần xác định **ranh giới ký hiệu hợp lệ** trước khi xây chỉ mục.

### 16.4. Thứ tự từ điển cũng cần hợp đồng

`iter_keys` ở bài sắp nhánh theo ký hiệu đầu dạng code point Unicode. Thứ tự đó không nhất thiết là thứ tự từ điển tiếng Việt theo quy tắc collation của một locale. Nếu cần thứ tự ngôn ngữ, phải chọn quy tắc sắp thích hợp; nén đường không tự giải quyết vấn đề ấy.

## 17. Khi nào trie nén đáng sử dụng?

| Tiêu chí | Trie thường | Trie nén cạnh |
| --- | --- | --- |
| Một cạnh mang | Một ký hiệu | Chuỗi ký hiệu không rỗng |
| Số nút với một khóa dài `L>0` | `L+1` | 2 |
| Tìm chính xác | Đi theo từng ký hiệu | Chọn cạnh và so khớp cả nhãn |
| Chèn phân kỳ | Tạo nhánh bằng nút từng ký hiệu | Có thể phải split nhãn |
| Xóa | Dọn nút không còn khóa | Dọn và merge cạnh |
| Tiền tố kết thúc giữa đường | Luôn có nút tại mỗi ký hiệu | Có thể nằm giữa nhãn |
| Số nút (nén chuẩn) | Theo số tiền tố phân biệt | O(số khóa) |
| Cập nhật với chuỗi bất biến | Không cần split nhãn dài | Có thể copy nhãn dài |

### 17.1. Workload nhiều đoạn một con

Nếu từ điển có những đường dài gần như không phân nhánh, trie nén thường giảm đáng kể số nút và overhead của các bảng con nhỏ.

### 17.2. Workload chèn/xóa liên tục

Nếu từ khóa thường xuyên phân kỳ giữa những nhãn rất dài, chi phí cắt/nối chuỗi có thể đáng kể. Khi ấy nên đo tần suất split/merge và số ký hiệu được sao chép, hoặc cân nhắc biểu diễn nhãn dạng đoạn tham chiếu.

### 17.3. So với Hash Set

Hash Set thường đơn giản khi chỉ tra chính xác khóa nguyên vẹn, nhưng không tự chỉ mục các tiền tố. Trie nén phù hợp khi có nhiều truy vấn `count_prefix`, autocomplete và từ điển đầu vào cùng chia sẻ những đoạn đầu.

Không có phương án tối ưu tuyệt đối: độ dài khóa, phân bố tiền tố, byte mỗi nút và tần suất cập nhật quyết định lựa chọn.

## 18. Các lỗi triển khai điển hình

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Gộp nút terminal một con | Mất khóa là tiền tố của khóa dài hơn | Chỉ gộp nút không terminal |
| Không gộp nút không terminal một con | Trie mất dạng nén chuẩn | Dọn từ dưới lên sau xóa |
| Cho phép nhãn cạnh rỗng | Đường có thể không tiến, logic mơ hồ | Mọi nhãn phải khác rỗng |
| Hai nhánh ra cùng ký hiệu đầu | Không chọn được duy nhất cạnh | Split tại LCP |
| `contains` cho phép dừng giữa cạnh | Nhận nhầm tiền tố thành khóa | Khớp hết nhãn và kiểm tra terminal |
| Từ chối tiền tố nằm giữa cạnh | Bỏ sót gợi ý hợp lệ | Dùng LCP và `_prefix_location` |
| Liệt kê quên phần nhãn chưa đọc | Xuất chuỗi bị thiếu ký hiệu | Khôi phục đuôi nhãn trước DFS |
| Split làm tăng count của nhánh cũ | Đếm sai số khóa | Giữ nguyên count nhánh cũ, chỉ tăng middle/tổ tiên |
| Chèn trùng vẫn tăng `size` | Trùng khóa và sai count | Kiểm tra terminal trước cập nhật |
| Xóa từ chưa terminal nhưng vẫn dọn | Có thể mất khóa khác | Xác nhận tồn tại trước khi sửa |
| Chỉ tính số cạnh `q` | Bỏ qua chi phí so khớp nhãn dài | Tính ký hiệu đã so sánh |
| Khẳng định mọi cập nhật O(L) | Bỏ chi phí copy nhãn cũ | Cộng chi phí `B` |
| Không chuẩn hóa Unicode nhất quán | Hai dạng cùng chữ đi vào hai nhánh | Chuẩn hóa cả đọc và ghi |
| Tính bộ nhớ chỉ bằng số nút | Bỏ chuỗi nhãn và metadata | Đếm `N_c`, `A` và overhead |
| Dùng đệ quy không kiểm soát độ sâu | Có thể vượt giới hạn runtime | DFS lặp hoặc giới hạn độ sâu |

## 19. Bài tập vận dụng có gợi ý giải

### Bài 1 — Nén một khóa đơn

Trie chỉ lưu `"algorithm"` dài 9 ký hiệu. Có bao nhiêu nút trong trie không nén và trie nén chuẩn?

**Gợi ý:** Trie không nén có 10 nút tính cả gốc. Trie nén có gốc và một nút terminal, tổng 2; nhãn cạnh vẫn gồm 9 ký hiệu.

### Bài 2 — Nút một con nào được giữ?

Trie lưu `{"an","anh"}`. Nút `an` terminal có một con. Có được gộp hai cạnh thành `anh` không?

**Gợi ý:** Không. Gộp sẽ làm mất khóa `an`.

### Bài 3 — Split do phân kỳ

Chỉ lưu `cat`, sau đó chèn `car`. Hãy vẽ trie nén.

**Gợi ý:** Gốc có cạnh `ca` tới nút không terminal với hai nhánh `t` và `r` tới hai nút terminal.

### Bài 4 — Split do khóa ngắn hơn

Chỉ lưu `cater`, sau đó chèn `cat`. Nút nào phải là terminal?

**Gợi ý:** Tạo một nút `cat` terminal, có cạnh `er` tới nút terminal `cater`.

### Bài 5 — Tìm chính xác và tiền tố

Trie chỉ lưu `alphabet` bằng một cạnh. Tính `contains("alp")`, `count_prefix("alp")` và `keys_with_prefix("alp")`.

**Gợi ý:** `False`, 1 và `["alphabet"]`. Tiền tố hết giữa nhãn nhưng vẫn có khóa trong cây con.

### Bài 6 — Phân kỳ giữa nhãn

Trie chỉ có `alphabet`. Vì sao `count_prefix("alx")` bằng 0 dù ký hiệu đầu `a` có cạnh?

**Gợi ý:** Nhãn khác ở ký hiệu thứ ba; không thể chỉ chọn theo ký hiệu đầu rồi bỏ qua phần còn lại của nhãn.

### Bài 7 — Xóa dẫn đến gộp

Trie lưu `cat` và `car`. Sau xóa `car`, dạng nén chuẩn là gì?

**Gợi ý:** Chỉ còn cạnh `cat` từ gốc tới nút terminal; nút không terminal `ca` một con được gộp.

### Bài 8 — Xóa từ ngắn

Trie lưu `cat` và `cater`. Xóa `cat` nhưng giữ `cater` như thế nào?

**Gợi ý:** Bỏ terminal tại `cat`, rồi gộp `cat+er` thành `cater`.

### Bài 9 — Bộ đếm khi split

Trước tách, nhánh cũ chứa 7 khóa. Thêm một khóa qua nhánh mới sau split. Bộ đếm của nút giữa, nút con cũ và các tổ tiên thay đổi ra sao?

**Gợi ý:** Nút giữa có count 8; nút con cũ vẫn 7; các tổ tiên trên đường tăng 1.

### Bài 10 — Độ phức tạp khi nhãn rất dài

Một cạnh dài 100.000 ký hiệu. Có thể khẳng định tìm hết cạnh ấy O(1) chỉ vì số cạnh là một không?

**Gợi ý:** Không. So khớp 100.000 ký hiệu có thể cần Θ(100.000) phép so sánh ký hiệu.

### Bài 11 — Xóa một khóa ngắn và copy dài

Trie lưu `"a"` và `"a"+"x"*1000000`. Xóa `"a"` có độ dài 1. Vì sao ghép nhãn vẫn có thể rất đắt?

**Gợi ý:** Phải tạo nhãn mới chứa hơn một triệu ký hiệu bằng phép nối `str`. Chi phí sao chép `B` có thể lớn hơn `L` của khóa xóa.

### Bài 12 — Chèn ngắn vào cạnh dài

Trie chỉ lưu `"a"+"x"*1000000`. Chèn `"ab"`. Tại sao việc tạo hậu tố cũ `old_tail` có thể tốn thời gian?

**Gợi ý:** Phải cắt một nhãn rất dài sau ký hiệu `a`, có thể sao chép gần một triệu ký hiệu.

### Bài 13 — Số nút và ký hiệu nhãn

Một trie nén chuẩn lưu `n` khóa phân biệt. Vì sao số nút có chặn O(n+1) nhưng dung lượng nhãn vẫn phụ thuộc tổng ký hiệu `S`?

**Gợi ý:** Nút không terminal một con bị loại, chỉ giữ terminal và điểm phân nhánh. Nhưng nhãn cạnh phải lưu đủ các đoạn ký hiệu để phân biệt khóa dài.

### Bài 14 — Unicode

Vì sao `"bàn"` và `"ba\u0300n"` có thể đi theo hai đường khác nhau nếu chưa chuẩn hóa?

**Gợi ý:** Dãy code point khác nhau; chuẩn hóa NFC nhất quán trước khi tìm/chèn/xóa và truy vấn tiền tố nếu muốn coi chúng như một khóa.

### Bài 15 — Kiểm thử bất biến

Viết ý tưởng hàm kiểm tra không có nút không terminal một con, mọi nhãn không rỗng và bộ đếm đúng.

**Gợi ý:** Duyệt cây hậu tự, so terminal cộng tổng count các con; với nút khác gốc không terminal yêu cầu ít nhất hai con. Có thể đối chiếu với `validate_radix`.

### Bài 16 — Chọn cấu trúc theo workload

Ứng dụng tra nhiều khóa dài, ít cập nhật và nhiều đoạn một con. Ứng dụng khác chèn/xóa liên tục các khóa phân kỳ giữa nhãn rất dài. Bạn cần đo thêm những gì?

**Gợi ý:** Số nút tiết kiệm, tổng ký hiệu nhãn, số lần split/merge, ký hiệu bị sao chép, bộ nhớ đỉnh, độ trễ cập nhật và tần suất truy vấn tiền tố.

## 20. Checklist trước khi triển khai

```text
1. Hợp đồng:
   - Set, Map hay Multiset?
   - Cho phép khóa rỗng và chèn trùng không?
   - Ký hiệu là byte, code point hay grapheme?
   - Chuẩn hóa Unicode có nhất quán không?

2. Biểu diễn:
   - Nhãn cạnh luôn không rỗng?
   - Mỗi cạnh ra có ký hiệu đầu duy nhất?
   - Chỉ nút không terminal một con bị gộp?
   - Gốc vẫn được giữ khi trie rỗng?
   - subtree_count bằng số khóa terminal của cây con?

3. Tìm:
   - contains phải khớp hết nhãn mới tới terminal?
   - Prefix có thể kết thúc giữa cạnh?
   - Đếm tiền tố có đọc count đúng ở nút cuối cạnh?
   - Liệt kê có khôi phục phần nhãn còn lại?

4. Chèn:
   - Thiếu cạnh thì thêm cả hậu tố?
   - Khớp hết cạnh thì đi tiếp?
   - Phân kỳ giữa cạnh thì tạo middle và hai hậu tố?
   - Khóa hết giữa cạnh thì middle terminal?
   - Chèn trùng có giữ nguyên count?

5. Xóa:
   - Xác nhận terminal trước khi sửa?
   - Dọn cây con có count = 0?
   - Merge nút không terminal một con từ dưới lên?
   - Không xóa nút terminal còn khóa?

6. Chi phí:
   - L, P: số ký hiệu truy vấn?
   - q: số cạnh nén đã đi qua?
   - B: tổng ký hiệu copy do split/merge?
   - N_c: số nút; A: tổng độ dài nhãn cạnh?
   - Bộ nhớ cấu trúc, tạm và kết quả đã tách riêng?

7. Kiểm thử:
   - Từ ngắn là tiền tố của từ dài?
   - Khóa rỗng, thiếu, trùng, xóa tới rỗng?
   - Prefix dừng giữa nhãn cạnh?
   - Split/merge nhãn dài?
   - Bất biến được xác minh sau chuỗi cập nhật?
```

## 21. Tổng kết

**Trie nén** giữ nguyên quan hệ tiền tố nhưng thay chuỗi nút không terminal một con bằng cạnh mang **đoạn chuỗi dài**. Nén làm số nút giảm và có thể tiết kiệm đáng kể metadata, nhất là với các khóa dài ít phân nhánh.

Đổi lại, thuật toán phải phân biệt ranh giới rõ ràng: **tìm chính xác chỉ thành công tại nút terminal**, trong khi **tìm tiền tố có thể dừng giữa nhãn**. Chèn phải tách cạnh ở điểm LCP; xóa phải dọn nhánh rỗng và gộp lại nút không terminal một con mà vẫn bảo toàn các khóa có chung tiền tố.

Khi phân tích hiệu năng, đừng chỉ đếm số cạnh đã đi. Cần tính số ký hiệu so khớp, chi phí xử lý bảng con và đặc biệt là lượng ký hiệu `B` bị **sao chép khi cắt/nối nhãn bất biến**. Với bất biến, ví dụ kiểm thử và mô hình chi phí rõ ràng, radix trie trở thành lựa chọn hữu ích cho chỉ mục chuỗi có nhiều tiền tố chung mà không đánh đổi tính đúng lấy việc nén cấu trúc.
