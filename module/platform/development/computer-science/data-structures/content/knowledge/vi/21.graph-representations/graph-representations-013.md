# Ảnh hưởng của biểu diễn đến BFS, DFS và duyệt láng giềng

## 1. Một thuật toán, nhiều chi phí thực thi

Trong mạng quan hệ giữa các học phần, ta có thể dùng **BFS** để tìm những học phần có thể tiếp cận từ một học phần đầu tiên, hoặc dùng **DFS** để khảo sát các chuỗi phụ thuộc. Cả hai đều cần một thao tác lặp lại rất nhiều lần:

> “Cho đỉnh `u`, hãy lấy những đỉnh kề mà ta có thể đi tới trực tiếp từ `u`.”

Nếu đồ thị lưu bằng **danh sách kề**, thao tác này chỉ phải xét những liên kết có thật tại `u`. Nếu lưu bằng **ma trận kề đặc**, ta thường phải xét cả một hàng gồm `n` ô, kể cả những ô không có cung. Nếu chỉ lưu một **danh sách cạnh thuần**, việc tìm những cung đi ra từ `u` có thể phải quét tất cả `m` bản ghi. Một biểu diễn **CSR** lại nhóm sẵn những cung cùng nguồn trong các đoạn mảng liên tiếp.

Do đó, không thể nói “BFS luôn `O(n+m)`” mà **không chỉ rõ biểu diễn và cách lấy láng giềng**. Thuật toán BFS/DFS vẫn dùng cùng ý tưởng đánh dấu, queue hoặc stack; nhưng chi phí cung cấp các láng giềng quyết định thời gian tổng.

Bài này giải thích sâu cách biểu diễn đồ thị ảnh hưởng tới **duyệt láng giềng, BFS, DFS, bộ nhớ và thứ tự thăm**, đồng thời minh họa cùng một đồ thị bằng bốn biểu diễn và đếm chính xác số mục phải kiểm tra.

## 2. Ký hiệu và phạm vi phân tích

Cho đồ thị `G=(V,E)` với:

- `n=|V|`: số đỉnh, gồm **đỉnh cô lập**.
- `m=|E|`: số cạnh vô hướng hoặc số cung có hướng, **bao gồm các cung/cạnh song song** nếu mô hình cho phép.
- `d^+(u)=outdeg(u)`: số cung đi ra từ `u`; trong đồ thị vô hướng, `d(u)=deg(u)` theo quy ước đếm bậc phù hợp.
- `r`: số đỉnh thực sự được phát hiện trong **một lượt duyệt từ nguồn `s`**.
- `q_R`: số **mục kề thực sự được quét** khi xử lý những đỉnh đã tới được. Trong đồ thị có hướng dùng danh sách kề đi ra, `q_R` là tổng bậc ra của các đỉnh tới được.

Ta giả định một ID đỉnh đã được ánh xạ sang chỉ số nguyên, hoặc các phép tra cứu ID đủ rẻ (thường `O(1)` kỳ vọng với bảng băm thích hợp). Khi so sánh độ phức tạp, ta đếm cả việc **khởi tạo trạng thái** đánh dấu nếu thuật toán tạo cấu trúc cho đủ `n` đỉnh.

Với một lượt BFS/DFS bắt đầu ở `s`, ta có `r\le n`. Cần phân biệt hai dạng chi phí:

1. **Duyệt từ một nguồn:** chỉ xử lý `r` đỉnh tới được, có thể ít hơn rất nhiều so với `n`.
2. **Duyệt toàn bộ đồ thị:** xét mọi đỉnh chưa đánh dấu để tạo rừng BFS/DFS, gồm những đỉnh cô lập; lúc đó mọi đỉnh đều được xử lý.

Số cạnh `m` là số liên kết **thật**, không phải số cặp đỉnh tối đa. Trong đồ thị vô hướng dùng danh sách kề hai chiều, một cạnh thông thường được ghi **hai mục kề**, nên số mục quét có thể là `2m` thay vì `m`, nhưng cùng bậc `O(m)`.

## 3. Một đồ thị làm ví dụ xuyên suốt

Xét đồ thị **có hướng** gồm sáu đỉnh `V={A,B,C,D,E,F}`, với bảy cung theo thứ tự đầu vào:

| Cung | Nguồn | Đích | Ghi chú |
| --- | --- | --- | --- |
| `e0` | A | B | Cung đầu tiên |
| `e1` | A | C | |
| `e2` | A | B | Cung song song với e0 |
| `e3` | B | D | |
| `e4` | C | D | |
| `e5` | C | C | Khuyên |
| `e6` | D | E | |

Danh sách kề theo cung đi ra:

```text
A: [B, C, B]    (3 mục, gồm hai cung tới B)
B: [D]          (1 mục)
C: [D, C]       (2 mục, có khuyên C -> C)
D: [E]          (1 mục)
E: []           (0 mục)
F: []           (0 mục, đỉnh cô lập)
```

Sơ đồ giản lược:

```text
       +----> B ----> D ----> E
       |             ^
       |             |
       A ----> C ----+

Ngoài sơ đồ: A -> B có hai cung khác ID; C -> C là khuyên.
F là đỉnh cô lập.
```

Khi **BFS từ A**, thứ tự phát hiện/lấy khỏi queue là:

```text
A, B, C, D, E
```

Đỉnh F không tới được. Khi **DFS từ A** theo thứ tự láng giềng trong danh sách đã cho và đi sâu trước, một thứ tự phát hiện hợp lệ là:

```text
A, B, D, E, C
```

Hai thuật toán đánh dấu cùng tập đỉnh `{A,B,C,D,E}`, nhưng thứ tự duyệt và cây cha có thể khác nhau. Đặc biệt, **hai cung A→B không làm B được thăm hai lần**, còn khuyên C→C không gây lặp vô hạn nếu đánh dấu đúng lúc.

Đây sẽ là dữ liệu đối chiếu cho danh sách kề, ma trận kề, danh sách cạnh và CSR.

## 4. Giao diện lấy láng giềng: chỗ biểu diễn ảnh hưởng thuật toán

Một cách nhìn hữu ích là tách phần **điều khiển BFS/DFS** khỏi phần **cấp phát các láng giềng**:

```text
BFS hoặc DFS:
    lấy một đỉnh u để xử lý
    duyệt tất cả láng giềng đi ra từ u
    nếu gặp đỉnh chưa đánh dấu:
        đánh dấu và đưa vào queue/stack
```

Khi đổi biểu diễn, vòng lặp “duyệt tất cả láng giềng” có thể tương ứng với:

| Biểu diễn | Cách lấy các cung đi ra từ u |
| --- | --- |
| Danh sách kề | Duyệt trực tiếp `adj[u]` |
| Hash set/map kề | Duyệt các phần tử/khóa trong `adj[u]` |
| Ma trận kề đặc | Quét `A[u][0],...,A[u][n-1]` và lọc ô có cạnh |
| Danh sách cạnh thuần | Quét toàn bộ `edges`, giữ những bản ghi có `source=u` |
| CSR | Duyệt `neighbor[offset[u]:offset[u+1]]` |
| CSC trên đồ thị có hướng | Các đoạn nhóm theo **đích**, thuận tiện duyệt **cung đi vào**, không trực tiếp là danh sách cung ra |

Tính đúng của BFS/DFS còn phụ thuộc việc các cung được trả về đúng **hướng**. Nếu đồ thị có `A→B` mà API nhầm các cung đi vào B thành cung đi ra B, tập đỉnh tới được sẽ thay đổi. Biểu diễn chỉ là **cách lưu**; quy ước ngữ nghĩa nguồn–đích phải được giữ ở mọi tầng.

## 5. Danh sách kề: chỉ quét liên kết tồn tại

Với danh sách kề dạng list, `adj[u]` chứa một mục cho mỗi cung đi ra từ `u`:

```python
adj = {
    "A": ["B", "C", "B"],
    "B": ["D"],
    "C": ["D", "C"],
    "D": ["E"],
    "E": [],
    "F": [],
}
```

Duyệt tất cả láng giềng của `u` chỉ đọc số mục kề của chính nó:

\[
T_{\mathrm{neighbors}}(u)=\Theta(d^+(u)).
\]

Để BFS/DFS bao phủ **toàn bộ** `n` đỉnh, cần một lần quản lý trạng thái cho các đỉnh và một lần quét các mục kề:

\[
T_{\mathrm{BFS/DFS,adj}}=\Theta(n+m)
\]

trong mô hình chuẩn, nếu mỗi cung được lưu đúng một mục đi ra (đồ thị có hướng), hoặc mỗi cạnh vô hướng được lưu số mục hằng định. Cận này cũng áp dụng cho đồ thị dày, nhưng khi `m=\Theta(n^2)`, nó trở thành `\Theta(n^2)`.

Với **BFS/DFS từ một nguồn**, phần quét các đỉnh tới được là `\Theta(r+q_R)`; nếu đã khởi tạo mảng cho **tất cả n đỉnh** thì cộng thêm `\Theta(n)`. Trong ví dụ ở mục 3, `r=5` và:

\[
q_R=d^+(A)+d^+(B)+d^+(C)+d^+(D)+d^+(E)
=3+1+2+1+0=7.
\]

Vì vậy, BFS từ A **kiểm tra bảy mục kề**, không phải `6\times6=36` cặp đỉnh.

### List, set và map có ảnh hưởng gì?

Nếu `adj[u]` là **list không sắp xếp**, kiểm tra riêng `v` có phải láng giềng của `u` hay không cần `O(d^+(u))` thời gian trường hợp xấu; nhưng **liệt kê toàn bộ** láng giềng vốn đã cần `\Theta(d^+(u))`.

Nếu `adj[u]` là **hash set/map**, kiểm tra tồn tại cung thường `O(1)` **kỳ vọng**; việc duyệt toàn bộ mục kề vẫn tỷ lệ với số mục được trả về trong mô hình thông thường. Nếu là **mảng đã sắp xếp**, có thể kiểm tra cạnh bằng tìm nhị phân `O(\log(d^+(u)+1))`, còn duyệt cả đoạn vẫn là `O(d^+(u))`.

Vì thế, **tốc độ kiểm tra một cạnh** và **tốc độ liệt kê tất cả láng giềng** là hai mục tiêu khác nhau. BFS/DFS thông thường cần liệt kê; không thể chỉ dựa vào độ phức tạp `hasEdge(u,v)` để suy ra hiệu năng duyệt.

## 6. Ma trận kề: truy cập một ô nhanh, duyệt một hàng đắt

Ma trận kề đặc lưu giá trị `A[u][v]` cho **mọi cặp** đỉnh. Ma trận Boolean cho đồ thị ở mục 3, theo thứ tự hàng/cột `A,B,C,D,E,F`, là:

```text
       A B C D E F
    A  0 1 1 0 0 0
    B  0 0 0 1 0 0
    C  0 0 1 1 0 0
    D  0 0 0 0 1 0
    E  0 0 0 0 0 0
    F  0 0 0 0 0 0
```

Để trả lời **“có ít nhất một cung A→B không?”**, ta kiểm tra ngay `A[A][B]` với chi phí **`O(1)`** khi đã có chỉ số. Nhưng để **liệt kê cung đi ra từ A**, phải kiểm tra cả **sáu ô trong hàng A** và chọn những cột có giá trị 1:

\[
T_{\mathrm{neighbors,matrix}}(u)=\Theta(n).
\]

Nếu BFS từ A xử lý `r=5` đỉnh, một hiện thực quét cả hàng sẽ kiểm tra:

\[
r\cdot n=5\cdot6=30\text{ ô}.
\]

Trong đó phần lớn ô chỉ biểu thị **không có cung**. Nếu duyệt hết các đỉnh kể cả F, nó phải quét **`n^2=36` ô**.

Vì vậy, BFS/DFS **toàn đồ thị trên ma trận đặc** theo cách quét hàng thường có:

\[
T_{\mathrm{BFS/DFS,matrix}}=\Theta(n^2).
\]

Kết quả này không mâu thuẫn với việc **kiểm tra một ô là `O(1)`**: đó là **hai thao tác khác nhau**.

### Khuyên và cung song song trong ma trận

Ma trận Boolean vẫn lưu được **sự tồn tại của khuyên C→C** tại ô chéo `A[C][C]=1`, nhưng **hai cung A→B** chỉ thành **một ô bằng 1**. Nếu bài toán chỉ hỏi khả năng tới được và duyệt từng **đỉnh kề phân biệt**, việc gộp hai cung song song vẫn giữ kết quả BFS/DFS về **tập đỉnh tới được**.

Tuy nhiên, nếu cần **đếm số cung**, phân biệt **edge ID**, tìm tuyến cụ thể hoặc tính trọng số khác nhau của hai cung, ma trận Boolean **làm mất thông tin**. Khi đó phải lưu số lượng, danh sách ID trong ô hoặc dùng biểu diễn khác.

Một ma trận **bitset** có thể giúp thao tác trên nhiều ô theo từ máy và tận dụng xử lý song song; nhưng không nên tự động khẳng định BFS trên mọi ma trận là `O(n+m)`. Cần nêu thuật toán bitset, kích thước từ máy và mô hình chi phí trước khi đưa ra cận tốt hơn.

## 7. Danh sách cạnh thuần: thuận tiện quét hết, bất lợi khi hỏi láng giềng

Danh sách cạnh lưu từng cung thành một bản ghi:

```text
edges = [
    (A,B), (A,C), (A,B),
    (B,D), (C,D), (C,C), (D,E)
]
```

Nếu không có chỉ mục theo nguồn, để tìm những cung đi ra từ `B`, chương trình phải quét **tất cả bảy bản ghi**, dù B chỉ có một cung đi ra. Với `m` bản ghi:

\[
T_{\mathrm{neighbors,edge\ list}}(u)=\Theta(m)
\]

cho cách lọc bằng cách quét toàn bộ. Nếu BFS/DFS xử lý `r` đỉnh và thực hiện một lượt lọc `m` cạnh **cho mỗi đỉnh**, riêng việc tìm láng giềng tốn:

\[
\Theta(rm).
\]

Khi cần bao phủ cả `n` đỉnh, đó là **`\Theta(nm)` cho các lượt quét cạnh**, cộng chi phí khởi tạo/xét đỉnh. Trong ví dụ, BFS từ A xử lý năm đỉnh và quét bảy bản ghi mỗi lần:

\[
5\cdot7=35\text{ lần xét bản ghi cạnh}.
\]

Đây là đặc điểm của **cách cài đặt quét lại edge list**, không phải định lý rằng mọi thuật toán dùng dữ liệu đầu vào là edge list đều bắt buộc `O(nm)`.

### Tạo danh sách kề một lần trước khi duyệt

Ta có thể:

1. Tạo `adj[u]=[]` cho **mọi đỉnh** trong V: `O(n)`.
2. Đọc mỗi cung `(u,v)` và thêm v vào `adj[u]`: `O(m)` với mảng động phù hợp.
3. Chạy BFS/DFS bằng `adj`: `O(n+m)` để duyệt toàn bộ đồ thị.

Tổng vẫn là **`O(n+m)`** về thời gian và bộ nhớ cho phần chuyển đổi + duyệt. Vì thế, khi cần chạy nhiều lượt BFS/DFS từ nhiều nguồn trên cùng một đồ thị, **xây một chỉ mục kề dùng chung** thường tốt hơn quét lại mọi bản ghi ở mỗi bước.

Danh sách cạnh thuần vẫn hữu ích khi thuật toán chủ yếu cần **duyệt tất cả các cạnh**, chẳng hạn Kruskal sắp theo trọng số hay Bellman–Ford thực hiện nhiều lượt nới lỏng. Việc tối ưu cho các thuật toán ấy khác với tối ưu cho **truy vấn láng giềng của một đỉnh**.

## 8. CSR và CSC: bố trí nén, truy cập đúng đoạn kề

**CSR (Compressed Sparse Row)** lưu các cung đi ra theo nhóm nguồn bằng hai mảng chính:

- `row_ptr`: **`n+1` offset**; hàng u bắt đầu tại `row_ptr[u]` và kết thúc trước `row_ptr[u+1]`.
- `col_idx`: các đỉnh đích đặt liền nhau theo từng hàng, có `m` mục trong đồ thị có hướng thông thường.

Với các đỉnh được đánh số `A=0, B=1, C=2, D=3, E=4, F=5`, ví dụ ở mục 3 có:

```text
row_ptr = [0, 3, 4, 6, 7, 7, 7]
col_idx = [1, 2, 1, 3, 3, 2, 4]

row A: col_idx[0:3] = [1,2,1]
row B: col_idx[3:4] = [3]
row C: col_idx[4:6] = [3,2]
row D: col_idx[6:7] = [4]
row E: col_idx[7:7] = []
row F: col_idx[7:7] = []
```

Đỉnh E và F có hai offset liên tiếp **bằng nhau**, nhưng không biến mất khỏi cấu trúc. Mỗi cung A→B vẫn chiếm một mục riêng; để phân biệt hai cung song song cụ thể cần thêm mảng `edge_id` tương ứng.

Lấy tất cả cung đi ra từ u chỉ cần:

```text
for k from row_ptr[u] to row_ptr[u+1] - 1:
    v = col_idx[k]
    xử lý cung u -> v
```

Đọc hai offset là `O(1)`; duyệt đoạn tốn **`\Theta(d^+(u))`**. BFS/DFS toàn đồ thị dùng CSR có **`O(n+m)` thời gian** như danh sách kề; CSR có thể tiết kiệm overhead của nhiều list nhỏ và khai thác tính liên tục của mảng, nhất là trên đồ thị thưa, tương đối tĩnh.

**CSC (Compressed Sparse Column)** nhóm các cung theo **đích**; nó thuận tiện cho câu hỏi **“những đỉnh nào có cung đi vào v?”** hoặc BFS/DFS **ngược chiều cung gốc**. Nếu chỉ có CSC mà vẫn muốn duyệt cung **đi ra**, không thể đơn giản cắt một đoạn liên tiếp theo nguồn u, trừ khi có chỉ mục phụ hoặc cách xử lý khác.

Để thực hiện nhiều lần truy vấn ở cả hai chiều, ta có thể giữ **CSR + CSC**; đổi lại phải trả thêm bộ nhớ và giữ hai chỉ mục đồng bộ khi cập nhật. Mảng nén thường hợp với dữ liệu ít thay đổi vì thêm/xóa một cung ở giữa có thể dịch chuyển nhiều mục và offset, tốn **`O(n+m)` trong trường hợp xấu**.

## 9. Bảng độ phức tạp: chọn đúng hàng của thao tác

Với **đồ thị có hướng**, các cận dưới đây xét biểu diễn cơ bản, một mục cho mỗi cung, và đã biết chỉ số đỉnh:

| Biểu diễn | Bộ nhớ biểu diễn | Liệt kê cung đi ra từ u | BFS/DFS bao phủ toàn bộ V |
| --- | --- | --- | --- |
| Danh sách kề `list` | `\Theta(n+m)` | `\Theta(d^+(u))` | `\Theta(n+m)` |
| Danh sách kề `set/map` | `O(n+m)` về số bản ghi | `O(d^+(u))` theo mô hình băm thông thường | `O(n+m)` kỳ vọng với tra cứu hash |
| Ma trận kề **đặc** | `\Theta(n^2)` | `\Theta(n)` nếu quét hàng | `\Theta(n^2)` |
| Danh sách cạnh **thuần**, quét lại | `\Theta(n+m)` nếu giữ V | `\Theta(m)` | `O(n+nm)` cho cách quét lại mọi cạnh ở mỗi đỉnh |
| **CSR** theo nguồn | `\Theta(n+m)` | `\Theta(d^+(u))` | `\Theta(n+m)` |
| **CSC** theo đích | `\Theta(n+m)` | Không trực tiếp có đoạn theo nguồn | Phù hợp `O(n+m)` cho duyệt **ngược**; nếu duyệt **xuôi**, cần chỉ mục/thao tác khác |

Khi chỉ duyệt từ một nguồn s, phần xét láng giềng của `r` đỉnh đã tới được là:

| Biểu diễn và cách cài | Số mục cần kiểm tra trong phần duyệt từ s |
| --- | --- |
| Danh sách kề hoặc CSR | `q_R` mục kề |
| Ma trận kề quét hàng | `r\cdot n` ô |
| Danh sách cạnh quét lại toàn E tại mỗi đỉnh | `r\cdot m` bản ghi |

Để đưa ra thời gian **trọn vẹn** phải cộng việc đánh dấu, thao tác queue/stack và bước khởi tạo (`O(n)` nếu dùng mảng trạng thái đầy đủ). Với đồ thị dày `m=\Theta(n^2)`, `O(n+m)` của danh sách kề cũng là `O(n^2)`; lúc ấy ma trận có thể cạnh tranh nhờ truy cập theo chỉ số và cách bố trí dữ liệu. Không thể chọn cấu trúc chỉ dựa vào một ký hiệu Big-O mà bỏ qua hệ số hằng và bộ nhớ.

## 10. Python: cùng đồ thị, đếm số mục BFS/DFS thực sự xét

Ví dụ sau xây **bốn biểu diễn của đúng một đồ thị có hướng**: danh sách kề, ma trận Boolean, danh sách cạnh thuần và CSR. Mã cố ý tách thuật toán BFS/DFS khỏi hàm `scan(u)` cấp láng giềng.

Quy ước `scan(u)` trả các cặp `(v, exists)`:

- `exists=True` nghĩa là mục ứng với cung đi ra từ u.
- Với ma trận, nó còn trả những ô `False` (không có cung).
- Với edge list, nó duyệt **mọi bản ghi** rồi đánh dấu bản ghi có nguồn khác u là `False`.

Nhờ vậy, biến `examined` đo **số mục/ô/bản ghi đã kiểm tra** trong phần duyệt, không phải thời gian thực tế theo mili-giây.

```python
from collections import deque


def tao_bon_bieu_dien(n, edges):
    adj = [[] for _ in range(n)]
    matrix = [[False] * n for _ in range(n)]
    counts = [0] * n

    for u, v in edges:
        if not (0 <= u < n and 0 <= v < n):
            raise ValueError("Đầu mút phải là chỉ số từ 0 đến n-1")
        adj[u].append(v)
        matrix[u][v] = True  # Gộp cung song song: chỉ còn có/không
        counts[u] += 1

    row_ptr = [0]
    for count in counts:
        row_ptr.append(row_ptr[-1] + count)

    next_pos = row_ptr[:-1].copy()
    col_idx = [0] * len(edges)
    for u, v in edges:
        k = next_pos[u]
        col_idx[k] = v
        next_pos[u] += 1

    return adj, matrix, (row_ptr, col_idx)


def bfs(start, scan):
    visited = {start}
    queue = deque([start])
    order = []
    examined = 0

    while queue:
        u = queue.popleft()
        order.append(u)
        for v, exists in scan(u):
            examined += 1
            if exists and v not in visited:
                visited.add(v)  # Đánh dấu ngay khi thêm vào queue
                queue.append(v)

    return order, examined


def dfs(start, scan):
    # Stack lưu iterator để khi quay lại u không quét từ đầu.
    visited = {start}
    order = [start]
    stack = [(start, iter(scan(start)))]
    examined = 0

    while stack:
        u, neighbors = stack[-1]
        try:
            v, exists = next(neighbors)
        except StopIteration:
            stack.pop()
            continue

        examined += 1
        if exists and v not in visited:
            visited.add(v)
            order.append(v)
            stack.append((v, iter(scan(v))))

    return order, examined


names = "ABCDEF"
edges = [
    (0, 1),  # e0: A -> B
    (0, 2),  # e1: A -> C
    (0, 1),  # e2: A -> B (song song)
    (1, 3),  # e3: B -> D
    (2, 3),  # e4: C -> D
    (2, 2),  # e5: C -> C (khuyên)
    (3, 4),  # e6: D -> E
]
n = len(names)
adj, matrix, csr = tao_bon_bieu_dien(n, edges)
row_ptr, col_idx = csr


def scan_list(u):
    return ((v, True) for v in adj[u])


def scan_matrix(u):
    return ((v, matrix[u][v]) for v in range(n))


def scan_edges(u):
    # Quét TOÀN BỘ edge list cho từng u.
    return ((v, source == u) for source, v in edges)


def scan_csr(u):
    return ((col_idx[k], True)
            for k in range(row_ptr[u], row_ptr[u + 1]))


scans = {
    "Danh sách kề": scan_list,
    "Ma trận kề": scan_matrix,
    "Danh sách cạnh": scan_edges,
    "CSR": scan_csr,
}

print(adj)       # [[1, 2, 1], [3], [3, 2], [4], [], []]
print(row_ptr)   # [0, 3, 4, 6, 7, 7, 7]
print(col_idx)   # [1, 2, 1, 3, 3, 2, 4]
print(matrix[0][1])  # True: ma trận chỉ giữ sự hiện diện

for label, scan in scans.items():
    order, checked = bfs(0, scan)
    print(label, "".join(names[v] for v in order), checked)

# Danh sách kề ABCDE 7
# Ma trận kề ABCDE 30
# Danh sách cạnh ABCDE 35
# CSR ABCDE 7

for label, scan in scans.items():
    order, checked = dfs(0, scan)
    print(label, "".join(names[v] for v in order), checked)

# Cả bốn đều thăm các đỉnh A, B, D, E, C theo DFS:
# Danh sách kề ABDEC 7
# Ma trận kề ABDEC 30
# Danh sách cạnh ABDEC 35
# CSR ABDEC 7

for label, scan in scans.items():
    print(label, bfs(5, scan))

# Từ F: chỉ thăm [5] trong cả bốn biểu diễn.
# Số mục kiểm tra tương ứng: list 0, matrix 6,
# edge list 7, CSR 0.
```

### Đọc kết quả đo

Với BFS từ A có `r=5` đỉnh tới được:

- **Danh sách kề** đọc **7 mục** vì có đúng 7 cung đi ra từ những đỉnh được thăm.

- **CSR** cũng đọc **7 mục**; khác biệt chủ yếu nằm ở cách bố trí các mục và chi phí tạo/cập nhật cấu trúc.

- **Ma trận kề** đọc **30 ô**, tức `5 × 6`; mỗi hàng gồm cả ô không có cung.

- **Danh sách cạnh** quét **35 bản ghi**, tức `5 × 7`, do chưa lập chỉ mục theo nguồn.

Các số 7, 30, 35 chỉ đo **số mục được xem**, không đo thời gian chạy hay toàn bộ chi phí cấp phát. Chính chương trình minh họa giữ cả bốn biểu diễn nên bộ nhớ của chương trình này là `O(n^2+m)`, không phải bộ nhớ của từng lựa chọn riêng lẻ.

### Vì sao kết quả DFS cũng có thứ tự ABDEC?

Đoạn DFS dùng **stack chứa iterator của từng đỉnh**. Khi gặp B từ A, nó đi sâu theo B→D→E trước, rồi mới quay về A để xét C. Đây là cách hiện thực tương đương kiểu DFS đệ quy theo thứ tự láng giềng. Nếu dùng stack chỉ chứa đỉnh và **đưa tất cả láng giềng lên stack cùng lúc**, thứ tự phát hiện có thể khác, vì stack là LIFO; muốn mô phỏng cùng thứ tự cần chú ý cách đẩy phần tử.

## 11. Thứ tự láng giềng làm thay đổi thứ tự BFS/DFS

BFS và DFS không nhất thiết tạo cùng một thứ tự thăm hoặc cây cha trên mọi biểu diễn, ngay cả khi **tập cung toán học giống nhau**.

Ví dụ `adj[A]=[B,C]` và `adj[A]=[C,B]` có cùng tập láng giềng phân biệt nhưng:

- BFS có thể đưa B trước C hoặc C trước B.
- DFS có thể đi sâu vào nhánh B trước hoặc nhánh C trước.
- Với hai đường ngắn nhất cùng độ dài, `parent` do BFS chọn có thể khác nhau, dù **khoảng cách ít cung nhất** không đổi.

Ảnh hưởng của cấu trúc:

| Kiểu lưu láng giềng | Thứ tự thường gặp |
| --- | --- |
| List/vector | Theo thứ tự lưu/chèn, nếu không tự sắp xếp |
| Mảng đã sắp xếp | Theo thứ tự khóa/ID đã quy định |
| Hash set | **Không bảo đảm** tăng dần theo ID |
| Hash map | Có thể có quy tắc thứ tự riêng của ngôn ngữ/thư viện, **không mặc nhiên là thứ tự tăng** |
| CSR | Theo thứ tự các mục trong đoạn nén; không tự sắp xếp |
| Ma trận quét cột từ 0 tới n−1 | Theo **chỉ số đỉnh tăng dần**, bất kể thứ tự chèn cung |
| Edge list quét tuần tự | Theo thứ tự bản ghi hiện có trong edge list |

Nếu bài kiểm thử yêu cầu thứ tự cụ thể, hãy quy định rõ **thứ tự duyệt láng giềng**. Có thể sắp `adj[u]` tăng dần trong giai đoạn xây dựng, rồi BFS/DFS đọc trực tiếp. Nếu thường xuyên thay đổi cung, việc duy trì mảng đã sắp xếp làm thêm/xóa đắt hơn so với append hoặc hash set.

Với danh sách kề có `d(u)` mục, sắp xếp một danh sách thường tốn `O(d(u)\log(d(u)+1))`; tổng chi phí tiền xử lý qua mọi đỉnh là `O(\sum_u d(u)\log(d(u)+1))`. Không nên vô tình **sắp xếp lại từng danh sách mỗi khi BFS/DFS xử lý một đỉnh** nếu có thể chuẩn bị thứ tự một lần cho nhiều lượt duyệt.

**Tính đúng và tính tái lập khác nhau:** thứ tự BFS/DFS có thể thay đổi mà kết quả “có tới được đỉnh v không?” vẫn đúng. Nhưng nếu đầu ra là **một đường đi cụ thể**, người dùng có thể nhìn thấy một đường khác khi thay đổi thứ tự kề.

## 12. Đồ thị có hướng, vô hướng, trọng số và đa cạnh

### Hướng cung và duyệt ngược

Trong đồ thị có hướng, một cung `u→v` cho phép BFS/DFS đi **từ u tới v**, không tự cho phép **v tới u**. Danh sách kề và CSR thường nhóm **cung đi ra**. Nếu muốn trả lời “những đỉnh nào đi tới được đích t?”, có thể chạy BFS/DFS từ t trên **đồ thị đảo chiều**, sử dụng danh sách cung đi vào hoặc CSC.

Phải phân biệt **đảo chiều trong một chỉ mục để truy vấn** với **tự thêm cung ngược vào đồ thị gốc**. Thao tác thứ hai làm thay đổi quan hệ tới được.

### Đồ thị vô hướng

Với cạnh `{u,v}`, `u\ne v`, danh sách kề thường ghi **hai mục đối ứng**, nên duyệt toàn bộ sẽ kiểm tra khoảng `2m` mục cạnh, vẫn là `O(n+m)`. Nếu chỉ ghi một phía rồi dùng BFS như thể đó là đồ thị có hướng, kết quả có thể sai.

Trong ma trận kề vô hướng đơn, `A[u][v]=A[v][u]`; quét hàng vẫn tốn `O(n)` với ma trận đặc. Một cạnh vô hướng có khuyên được đếm bậc hai lần theo quy ước chuẩn, nhưng khi tìm láng giềng, nó không nên làm cùng một đỉnh được đánh dấu nhiều lần.

### Khuyên và cung/cạnh song song

Khuyên `u→u` trỏ về chính u. Nếu u đã được đánh dấu khi xử lý `adj[u]`, khuyên không thêm u vào queue/stack lần nữa. Cung song song A→B có thể làm vòng lặp quét **hai mục** nhưng chỉ phát hiện B **một lần**.

Nếu thuật toán cần phân biệt tuyến **e0** và **e2** dù chúng cùng A→B, chỉ lưu `parent[B]=A` là chưa đủ; phải lưu **`parent_edge[B]`** hoặc ID liên kết trong kết quả. Matrix Boolean và set láng giềng đơn thuần có thể mất tính bội. Truy vấn tới được vẫn đúng với một liên kết gộp, nhưng **đếm cung, trọng số, chu trình hai cạnh trong đa đồ thị** hoặc xây hành trình theo ID có thể sai.

### Đồ thị có trọng số

BFS chuẩn tối thiểu hóa **số cung**, không tối thiểu hóa tổng trọng số bất kỳ. Ma trận trọng số cần ký hiệu riêng cho **không có cạnh**, vì cạnh trọng số `0` vẫn hợp lệ; danh sách kề hoặc CSR có thể lưu `(neighbor,weight)` hay một mảng trọng số song song.

Nếu muốn đường đi **tổng chi phí nhỏ nhất**, lựa chọn thuật toán phải phù hợp trọng số: Dijkstra cho trọng số không âm, Bellman–Ford khi có trọng số âm và cần xử lý chu trình âm tới được. Việc chuyển từ list sang ma trận **không làm BFS tự trở thành thuật toán đường đi ngắn nhất theo trọng số**.

## 13. Bộ nhớ duyệt và lựa chọn theo quy mô đồ thị

Cần tách **bộ nhớ của cấu trúc lưu đồ thị** khỏi **bộ nhớ phụ của BFS/DFS**:

| Hạng mục | Bộ nhớ thường gặp |
| --- | --- |
| Danh sách kề / CSR / CSC / danh sách cạnh kèm V | `O(n+m)` |
| Ma trận kề đặc | `O(n^2)` |
| `visited`, `parent`, `distance` nếu lưu theo mọi đỉnh | `O(n)` |
| Queue BFS hoặc stack DFS | `O(n)` trong trường hợp xấu |

Với **đồ thị thưa** `m=O(n)`, danh sách kề hoặc CSR thường giúp cả bộ nhớ và việc duyệt kề tăng gần tuyến tính. Với **đồ thị dày** `m=\Theta(n^2)`, danh sách kề có thể chứa `\Theta(n^2)` mục, khiến nó không còn lợi thế tiệm cận so với ma trận đặc; ma trận Boolean được đóng gói bit hoặc tính toán theo từ máy có thể đáng cân nhắc.

Điều kiện quan trọng là **mức độ thay đổi dữ liệu**:

- **Đồ thị thường xuyên thêm/xóa cung:** danh sách kề động bằng list/set/map thường thuận tiện; cần duy trì đúng chiều và xử lý trùng.
- **Đồ thị lớn, ít cập nhật, duyệt rất nhiều lần:** CSR/CSC nén các đoạn kề có thể mang lại lợi thế cấp phát và truy cập bộ nhớ liên tục.
- **Tập đỉnh vừa phải, đồ thị dày, truy vấn cặp đỉnh dày đặc:** ma trận có truy cập ô `O(1)` theo chỉ số; nhưng BFS/DFS quét hàng vẫn có cận `O(n^2)`.
- **Dữ liệu nhập/xuất dưới dạng từng bản ghi cạnh:** giữ edge list làm nguồn chuẩn, nhưng dựng một chỉ mục kề trước khi chạy nhiều lượt BFS/DFS.

Một nguyên tắc thực dụng: **hãy tối ưu thao tác chiếm phần lớn thời gian của workload**. Nếu ứng dụng phải duyệt láng giềng hàng triệu lần, chi phí truy xuất theo từng đỉnh thường quan trọng hơn khả năng quét toàn bộ edge list một lần. Nếu ứng dụng chỉ kiểm tra một cặp đỉnh mỗi lần, phép `hasEdge` có thể quan trọng hơn tốc độ liệt kê mọi láng giềng.

## 14. Những nhầm lẫn thường gặp

1. **“BFS luôn O(n+m), bất kể cách lưu đồ thị.”** Sai: nếu tìm láng giềng bằng quét hàng ma trận thì thường `O(n^2)`; quét edge list lại cho mỗi đỉnh có thể thành `O(nm)`.
2. **“Ma trận kiểm tra cạnh O(1) thì duyệt kề cũng O(1).”** Sai: muốn tìm **tất cả** láng giềng phải xét hàng có n ô.
3. **“Danh sách cạnh thuần đồng nghĩa danh sách kề.”** Sai: edge list chưa nhóm cung theo nguồn, phải lọc cả m bản ghi để biết cung đi ra một đỉnh.
4. **“Lưu CSR là mặc nhiên sắp xếp láng giềng.”** Sai: chỉ nhóm theo hàng; thứ tự trong từng đoạn phụ thuộc quá trình xây dựng.
5. **“CSC là CSR dùng cho cùng chiều.”** Không đúng khi duyệt đồ thị có hướng: CSC nhóm theo **đích**, thuận tiện đi ngược chiều cung gốc.
6. **“Cung song song sẽ tạo hai lần thăm cùng một đỉnh.”** Sai khi đánh dấu lúc phát hiện; chỉ làm tăng số mục cạnh phải xem.
7. **“Khuyên khiến BFS/DFS lặp vô hạn.”** Không nếu dùng `visited` đúng; tự trỏ về đỉnh đã phát hiện bị bỏ qua.
8. **“Tập đỉnh có thể suy ra đầy đủ từ edge list.”** Sai nếu có đỉnh cô lập; phải giữ V riêng.
9. **“Thứ tự BFS/DFS phải giống nhau trên mọi cấu trúc.”** Sai: phụ thuộc thứ tự láng giềng và cách dùng stack/queue, dù tập đỉnh tới được không đổi.
10. **“Danh sách kề có hasEdge O(1) trong mọi biến thể.”** Sai với list; hash set/map chỉ thường có `O(1)` kỳ vọng.
11. **“Ma trận Boolean biểu diễn nguyên vẹn đa đồ thị.”** Sai: một ô True không giữ số cung song song hay edge ID riêng.
12. **“Nếu đồ thị dày, chắc chắn ma trận luôn chạy nhanh hơn.”** Không chắc: cần xét thuật toán cụ thể, mật độ, bộ nhớ, bitset và hệ số hằng.
13. **“BFS trên ma trận trọng số tự tìm tổng trọng số nhỏ nhất.”** Sai: BFS cơ bản đếm số bước; trọng số cần thuật toán phù hợp.
14. **“Đã có visited thì mọi DFS cài bằng stack đều cho cùng thứ tự.”** Sai: đưa láng giềng lên stack theo thứ tự khác với giữ iterator khung DFS có thể thay đổi thứ tự phát hiện.
15. **“Chỉ cần đo số ô được xem là đã đo xong tốc độ thực.”** Chưa đủ: còn chi phí cấp phát, locality, bộ nhớ đệm, hash, nhánh và ngôn ngữ lập trình.

## 15. Tự kiểm tra

**Câu 1.** Đồ thị có hướng có `n=1.000`, `m=2.000`. BFS toàn bộ trên danh sách kề và trên ma trận kề đặc có độ phức tạp nào?

**Đáp án:** Danh sách kề `O(n+m)`; ma trận đặc quét toàn bộ hàng `O(n^2)`. Với dữ liệu cụ thể, nó tương ứng bậc vài nghìn mục so với một triệu ô, chưa kể hằng số.

**Câu 2.** Nếu `out[u]` có ba mục trong list, một lần liệt kê các cung ra từ u cần xét bao nhiêu mục? Nếu ma trận có n=100 đỉnh thì sao?

**Đáp án:** List xét **3 mục**; ma trận kề đặc quét **100 ô** của hàng u theo cách cài thông thường.

**Câu 3.** Một edge list có 50 cung. Nếu BFS xử lý 10 đỉnh và lần nào cũng quét toàn bộ edge list để tìm cung ra, có bao nhiêu lượt xét bản ghi?

**Đáp án:** **500 lượt xét** (`10×50`) theo cách cài quét lại, chưa tính queue và đánh dấu.

**Câu 4.** Với ví dụ mục 3, vì sao BFS từ A chỉ xét 7 mục trong danh sách kề nhưng 30 ô ở ma trận?

**Đáp án:** BFS tới được **5 đỉnh**. Tổng bậc ra của chúng là **7**, còn ma trận quét **5 hàng × 6 ô = 30**.

**Câu 5.** Ma trận Boolean gộp hai cung A→B thành một ô True. Điều gì được bảo toàn cho BFS và thông tin gì bị mất?

**Đáp án:** Vẫn bảo toàn việc B có thể tới được từ A; nhưng không còn biết đó là **hai cung riêng**, không giữ được hai edge ID hay các trọng số độc lập.

**Câu 6.** CSR có `row_ptr=[0,3,4,6,7,7,7]`. Đồ thị có bao nhiêu đỉnh và đỉnh chỉ số 4 có bao nhiêu mục cung đi ra?

**Đáp án:** Có **6 đỉnh** (`len(row_ptr)-1`). Đỉnh 4 có `row_ptr[5]-row_ptr[4]=7-7=0` mục.

**Câu 7.** Đang dùng CSC cho đồ thị có hướng. Khi cần duyệt các **cung đi vào** B, CSC hay CSR thuận tiện hơn? Khi cần duyệt các **cung đi ra** B thì sao?

**Đáp án:** CSC thuận tiện cung vào vì nhóm theo đích; CSR thuận tiện cung ra vì nhóm theo nguồn.

**Câu 8.** Một đồ thị vô hướng có `m=12` cạnh không khuyên, lưu mỗi cạnh ở cả hai danh sách kề. Có bao nhiêu mục kề được quét khi duyệt toàn đồ thị?

**Đáp án:** **24 mục kề**, tức `2m`; thời gian duyệt vẫn `O(n+m)`.

**Câu 9.** Nếu đổi `adj[A]` từ `[B,C]` thành `[C,B]` nhưng giữ nguyên các liên kết, BFS/DFS có bắt buộc giữ nguyên thứ tự thăm không?

**Đáp án:** **Không**. Thứ tự duyệt và cha có thể thay đổi; tuy nhiên các đỉnh tới được và khoảng cách ít cung nhất trong BFS không đổi.

**Câu 10.** Đồ thị lớn có hàng triệu cung, không cập nhật thường xuyên và chạy BFS nhiều lần. Nên cân nhắc danh sách cạnh quét lại hay CSR/danh sách kề?

**Đáp án:** Cân nhắc **CSR hoặc danh sách kề** để duyệt đoạn cung ra trực tiếp trong `O(d^+(u))`; tránh quét lại toàn bộ edge list cho mỗi đỉnh.

**Câu 11.** Khuyên C→C và hai cung song song A→B có làm tăng số lần phát hiện đỉnh tương ứng trong BFS đúng không?

**Đáp án:** Không. Mỗi đỉnh chỉ được đánh dấu và đưa vào queue một lần; các cung vẫn có thể được quét riêng, ảnh hưởng số mục xét nhưng không tạo thêm đỉnh.

**Câu 12.** Nếu cần tìm **tổng trọng số nhỏ nhất** trên đồ thị có các cung trọng số không âm, tại sao chỉ đổi biểu diễn từ danh sách kề sang ma trận kề chưa đủ?

**Đáp án:** Vì BFS chuẩn tối thiểu hóa số cung chứ không tính tổng trọng số. Cần chọn thuật toán đường đi phù hợp, chẳng hạn **Dijkstra** cho trọng số không âm, trên một biểu diễn hỗ trợ truy vấn cần thiết.

**Ghi nhớ:** **Chi phí duyệt đồ thị phụ thuộc trực tiếp vào cách lấy láng giềng**. BFS/DFS trên **danh sách kề hoặc CSR** thường là **`O(n+m)`** để bao phủ toàn đồ thị; trên **ma trận kề đặc** quét hàng thường là **`O(n^2)`**; trên **danh sách cạnh thuần** quét lại mỗi đỉnh có thể là **`O(nm)`**. Với một nguồn chỉ thăm `r` đỉnh, phần quét tương ứng có thể là **`q_R` mục kề**, **`r·n` ô** hoặc **`r·m` bản ghi**. Hãy giữ đúng **hướng cung, đỉnh cô lập, khuyên và tính bội**, quy định **thứ tự láng giềng** khi cần kết quả ổn định, và chọn biểu diễn theo **mật độ, kiểu truy vấn, chi phí cập nhật và bộ nhớ thực tế**.
