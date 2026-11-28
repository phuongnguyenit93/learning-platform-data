# Biểu diễn cạnh ngược và đỉnh đi vào cho đồ thị có hướng

## 1. Biết cung đi ra chưa đủ cho mọi câu hỏi

Trong nền tảng học tập, ta có thể quy ước cung `A → B` nghĩa là **học phần A là điều kiện tiên quyết trực tiếp của học phần B**. Nếu lưu danh sách kề theo hướng đi ra, `out[A]` cho biết những học phần trực tiếp phụ thuộc vào A. Nhưng để trả lời câu hỏi **“B cần hoàn thành những học phần nào trước?”**, ta lại cần biết những cung **đi vào B**.

Tương tự, một mạng theo dõi có cung `An → Bình` nếu An theo dõi Bình:

- `out[An]`: những người An đang theo dõi.
- `in[Bình]`: những người đang theo dõi Bình.

Một đồ thị có hướng chỉ có `out` vẫn đủ để lưu **toàn bộ thông tin các cung**; ta luôn có thể quét tất cả cung để tìm những nguồn dẫn đến Bình. Tuy nhiên, nếu truy vấn **đỉnh đi vào** được gọi thường xuyên, việc lưu thêm một **chỉ mục cung đi vào** hoặc xây dựng **đồ thị đảo chiều** có thể tiết kiệm rất nhiều thời gian.

**Mục tiêu bài học:** phân biệt láng giềng đi ra và đi vào; xây dựng biểu diễn đảo chiều mà không làm xuất hiện cung giả trong đồ thị gốc; tính đúng bậc vào/ra, khuyên, cung song song; phân tích chi phí theo số đỉnh `n`, số cung `m`; và sử dụng duyệt ngược trong bài toán thực tế.

## 2. Định nghĩa đỉnh đi ra, đỉnh đi vào và bậc

Đồ thị có hướng được ký hiệu:

\[
G=(V,E),\qquad E\subseteq V\times V
\]

đối với đồ thị có hướng đơn. Trong đa đồ thị, ta cần coi mỗi cung là một **bản ghi có ID riêng** vì hai cung cùng đầu mút có thể tồn tại đồng thời.

Với cung `(u,v)`, `u` là **nguồn (source/tail)** và `v` là **đích (target/head)**. Ta định nghĩa:

\[
N^+(u)=\{v\in V:(u,v)\in E\},
\]

\[
N^-(u)=\{v\in V:(v,u)\in E\}.
\]

Ở đây:

- `N⁺(u)`: tập **láng giềng đi ra** (*out-neighbors*, successors trực tiếp).
- `N⁻(u)`: tập **láng giềng đi vào** (*in-neighbors*, predecessors trực tiếp).
- `outdeg(u)`: số **cung đi ra** từ `u`.
- `indeg(u)`: số **cung đi vào** `u`.

Trong đồ thị đơn, `outdeg(u)=|N⁺(u)|` và `indeg(u)=|N⁻(u)|`. Nhưng trong **đa đồ thị**, hai cung `A→B` song song cho `N⁺(A)={B}` trong khi `outdeg(A)=2`. Vì thế phải phân biệt **số đỉnh kề phân biệt** với **số cung**, nhất là khi dùng `set` láng giềng.

Mỗi cung đóng góp đúng **một đơn vị vào tổng bậc ra** và **một đơn vị vào tổng bậc vào**:

\[
\sum_{u\in V}\operatorname{outdeg}(u)
=\sum_{u\in V}\operatorname{indeg}(u)=m.
\]

Một **cung khuyên** `u→u` đóng góp `1` vào **cả** bậc ra và bậc vào của `u`, không phải `2` vào riêng một loại bậc.

## 3. Ví dụ cụ thể: hai phía của một tập cung

Cho `V={A,B,C,D,E}` và sáu cung **có ID**:

| ID | Nguồn | Đích | Trọng số minh họa |
| --- | --- | --- | ---: |
| `e0` | A | B | 5 |
| `e1` | C | B | 2 |
| `e2` | B | D | 3 |
| `e3` | C | D | 7 |
| `e4` | D | D | 0 |
| `e5` | A | B | 9 |

```text
A ==>> B ----> D
       ^       ^
       |       |
       C ------+

e0 và e5: hai cung A -> B khác ID.
e4: cung khuyên D -> D.
E: đỉnh cô lập.
```

Ta quy ước:

- `out[u]` lưu danh sách `(đích, edge_id)` của các cung **có nguồn u**.
- `in[v]` lưu danh sách `(nguồn, edge_id)` của các cung **có đích v**.
- Bảng `edges[edge_id]` lưu `(u,v,weight)` đúng **một lần** để không sao chép trọng số sang nhiều nơi.

Hai chỉ mục cho ví dụ:

| Đỉnh | `out[u]` | `in[u]` |
| --- | --- | --- |
| A | `[(B,e0),(B,e5)]` | `[]` |
| B | `[(D,e2)]` | `[(A,e0),(C,e1),(A,e5)]` |
| C | `[(B,e1),(D,e3)]` | `[]` |
| D | `[(D,e4)]` | `[(B,e2),(C,e3),(D,e4)]` |
| E | `[]` | `[]` |

Khi xem bảng, hãy chú ý:

1. Cung `e0=A→B` tạo **một mục tại `out[A]`** và **một mục tại `in[B]`**. Đó là **hai bản ghi chỉ mục cho cùng một cung**, không phải hai cung.
2. Cung `e5=A→B` có ID khác `e0`, nên vẫn phải có **hai mục riêng** trong cả hai chỉ mục. Nếu chỉ dùng tập `{A,C}` tại `in[B]`, ta sẽ giữ đúng các **nguồn phân biệt** nhưng không đếm được chính xác số cung đi vào.
3. Khuyên `e4=D→D` xuất hiện một lần trong `out[D]` và một lần trong `in[D]`. Nó là **một cung**, đóng góp một vào mỗi loại bậc.
4. E không xuất hiện trong cung nào nhưng vẫn phải có `out[E]=in[E]=[]`.

Bậc ra theo thứ tự A, B, C, D, E là `[2,1,2,1,0]`; bậc vào là `[0,3,0,3,0]`. Hai tổng đều bằng `6=m`.

## 4. Chỉ lưu cung đi ra hay lưu cả hai chỉ mục?

**Biểu diễn chỉ có cung đi ra** thường là:

```text
out[u] = danh sách các đích v sao cho tồn tại u -> v
```

Với `out` và tập `V`, ta vẫn xác định được toàn bộ đồ thị. Nhưng để tìm tất cả **nguồn của các cung vào `x`**, nếu không có chỉ mục bổ sung, phải:

1. Xét từng đỉnh `u` trong `V`.
2. Duyệt `out[u]`.
3. Giữ những cung có đích là `x`.

Với biểu diễn danh sách kề thông thường, phép quét toàn bộ tốn **`O(n+m)`** thời gian, kể cả khi `x` chỉ có một cung đi vào.

**Biểu diễn hai chiều chỉ mục** lưu đồng thời:

```text
out[u] = [(v, edge_id), ...]
in[v]  = [(u, edge_id), ...]
```

Khi đó, truy vấn liệt kê các **cung đi vào x** đọc trực tiếp `in[x]`; với danh sách `list`, chi phí xuất `k=indeg(x)` mục là **`\Theta(k)`**. Đọc số lượng cung vào bằng `len(in[x])` là **`O(1)`**. Tương tự, đọc `outdeg(x)` bằng `len(out[x])` là `O(1)`.

**Đánh đổi:** thêm một cung phải cập nhật cả `out[u]` lẫn `in[v]`. Bộ nhớ tăng vì mỗi cung có **hai mục chỉ mục**; nếu mỗi mục có kích thước hằng số, tổng vẫn là **`\Theta(n+m)`**.

## 5. Bất biến đối ứng khi thêm, sửa và xóa cung

Nếu đồ thị giữ đồng thời bảng cạnh, `out` và `in`, tất cả phải kể cùng một tập cung:

\[
e=(u,v,w)
\Longrightarrow
\begin{cases}
(v,e)\in out[u],\\
(u,e)\in in[v].
\end{cases}
\]

Ở đây `e` là **ID cung**. Một bản ghi cung có ID cụ thể xuất hiện **đúng một lần trong từng chỉ mục** ở đúng đầu mút, kể cả khi hai đầu mút là cùng một đỉnh.

Những bất biến cần giữ:

- **Đầu mút hợp lệ:** cả `u` và `v` đều thuộc tập đỉnh.
- **ID cung duy nhất:** hai cung song song có thể cùng `u,v` nhưng phải có ID riêng.
- **Hướng không bị đảo ngoài ý muốn:** `A→B` chỉ cập nhật `out[A]` và `in[B]`, không tự tạo `B→A` trong đồ thị gốc.
- **Khuyên:** `u=v` làm cập nhật hai **chỉ mục khác nhau** của cùng đỉnh, không được bỏ sót một phía vì hai ID đỉnh trùng nhau.
- **Trọng số:** nếu trọng số lưu tập trung theo ID, đổi trọng số không cần sửa hai danh sách tham chiếu; nếu lưu bản sao ở các mục kề, phải sửa cả hai bản sao.
- **Xóa cung theo ID:** loại đúng bản ghi `edges[e]`, mục `(v,e)` ở `out[u]` và mục `(u,e)` ở `in[v]`. Không xóa nhầm các cung song song khác.
- **Xóa đỉnh:** phải loại hoặc từ chối mọi cung có nguồn **hoặc** đích là đỉnh đó; nếu không sẽ có liên kết mồ côi.

Một thao tác cập nhật liên quan nhiều cấu trúc có thể **bị gián đoạn giữa chừng**. Trong hệ thống có truy cập đồng thời hoặc lưu trữ bền vững, phải có khóa/giao dịch hay cơ chế chuyển đổi nguyên tử thích hợp; nếu không, `out` và `in` có thể tạm thời mâu thuẫn.

### Chỉ mục ngược là dữ liệu suy ra

Về mặt thông tin, chỉ cần bảng cung `(u,v,w)` và tập đỉnh đã đủ để **dựng lại** cả hai danh sách kề. `in` là **chỉ mục được vật chất hóa** để tăng tốc đọc, không phải một tập cung mới độc lập. Khi không thể bảo đảm nhất quán cập nhật, có thể chọn **dựng lại từ bảng cung chuẩn** theo một chính sách rõ ràng.

## 6. Xây dựng danh sách đi vào từ danh sách đi ra

Nếu đã có tập đỉnh `V` và danh sách `out`, ta có thể dựng `in` bằng một lượt:

```text
for mỗi đỉnh v trong V:
    in[v] = danh sách rỗng

for mỗi đỉnh u trong V:
    for mỗi cung u -> v (có ID e) trong out[u]:
        in[v].append((u, e))
```

Thuật toán tạo `n` danh sách rỗng và duyệt đúng `m` mục cung đi ra:

\[
T_{\text{dựng in}}=\Theta(n+m),\qquad
S_{\text{in bổ sung}}=\Theta(n+m).
\]

Nếu `out` không ghi ID mà mỗi cặp có hướng xuất hiện tối đa một lần, có thể chỉ lưu `in[v].append(u)`. Với đa đồ thị, bản sao ID là cần thiết nếu ứng dụng muốn **phân biệt từng cung song song** khi tìm, cập nhật hoặc xóa.

Một ví dụ Python ngắn, dành cho **đồ thị có hướng đơn**:

```python
out = {
    "A": ["B", "C"],
    "B": ["D"],
    "C": ["B", "D"],
    "D": [],
    "E": [],
}

incoming = {u: [] for u in out}
for u, ds_dich in out.items():
    for v in ds_dich:
        if v not in incoming:
            raise KeyError(f"Đỉnh đích không tồn tại: {v}")
        incoming[v].append(u)

print(incoming)
# {'A': [], 'B': ['A', 'C'], 'C': ['A'],
#  'D': ['B', 'C'], 'E': []}
```

Trật tự các nguồn trong `incoming[v]` phụ thuộc trật tự quét `out`. Nếu thuật toán tiếp theo cần **thứ tự ID tăng dần**, hãy sắp xếp hoặc dùng cấu trúc có thứ tự; **đảo chiều cung không tự có nghĩa là sắp xếp lại**.

## 7. Đồ thị đảo chiều (transpose/reverse graph)

Cho đồ thị có hướng:

\[
G=(V,E).
\]

**Đồ thị đảo chiều**, ký hiệu `G^T` hoặc `G^{\mathrm{rev}}`, giữ **nguyên tập đỉnh** nhưng đảo nguồn và đích của mọi cung:

\[
G^T=(V,E^T),\qquad
E^T=\{(v,u):(u,v)\in E\}.
\]

Nếu đồ thị gốc có cung `A→B`, đồ thị đảo chiều có cung `B→A`. Đây là cung của **đồ thị mới**, không phải lệnh “thêm `B→A` vào đồ thị gốc”. Nếu cứ thêm cung ngược trực tiếp vào G, ta sẽ **thay đổi bài toán**, vì G lúc đó có thể trở thành hai chiều.

Quan hệ quan trọng:

\[
out_{G^T}[u]=in_G[u],
\qquad
in_{G^T}[u]=out_G[u].
\]

Đảo chiều hai lần phục hồi tập cung ban đầu:

\[
(G^T)^T=G.
\]

Đẳng thức này hiểu theo **đỉnh, ID liên kết và hướng cung**, không bắt buộc theo **thứ tự phần tử trong các list** sau khi triển khai lại. Với đa đồ thị, đảo từng cung **theo ID** để bảo toàn số cung song song. Với cung khuyên `u→u`, đảo chiều vẫn là `u→u`; trọng số gắn với cung đó được giữ nguyên nếu phép biến đổi chỉ đổi hướng.

Trong trường hợp có **trọng số thời gian đi đường thực tế**, đảo một cung với cùng trọng số là một phép biến đổi **toán học để phân tích đồ thị**, không có nghĩa chiều ngược ngoài đời có thật hay có cùng thời gian. Khi cần mô hình chiều đi lại thực tế, phải dùng dữ liệu về cung ngược thật.

### Ví dụ đổi chiều

```text
G:                      G^T:

A ----> B ----> D        A <---- B <---- D
        ^                         |
        |                         |
        C                         C

Trong G: A -> B và C -> B.
Trong G^T: B -> A và B -> C.
```

Ta có thể dựng `G^T` từ bảng cung trong **`O(n+m)` thời gian và bộ nhớ**. Nếu đã duy trì `in_G`, danh sách cung đi ra của `G^T` về logic chính là `in_G`; khi cần một đối tượng đồ thị mới **độc lập** để sửa, phải sao chép cấu trúc hoặc dùng lớp nhìn (*view*) chỉ đọc với quy tắc thích hợp.

## 8. Duyệt ngược để tìm những đỉnh có thể đi tới một đích

Một câu hỏi thường gặp:

> “Những đỉnh nào có **đường đi có hướng** tới đích `t`, có thể qua nhiều bước?”

Nếu chỉ kiểm tra `in[t]`, ta mới biết **những nguồn nối trực tiếp tới t**, chưa biết các đỉnh có thể đi tới `t` qua những đỉnh trung gian.

Giải pháp: chạy **BFS hoặc DFS từ `t` trên đồ thị đảo chiều `G^T`**. Tương đương, từ `t` lần theo danh sách `in` của đồ thị gốc.

Lý do đúng:

\[
u\leadsto_G t\quad\Longleftrightarrow\quad
t\leadsto_{G^T}u.
\]

Một đường đi `u→x_1→\cdots→t` trong G trở thành `t→\cdots→x_1→u` trong `G^T`. Chiều đảo ngược nhưng mỗi cung tương ứng vẫn được bảo toàn.

Trong ví dụ sáu cung ở mục 3, xuất phát từ D và lần theo `in`:

```text
Bước 0: D
Bước 1: B, C có cung trực tiếp tới D
Bước 2: A có cung tới B

Tập đỉnh có thể tới D: {A, B, C, D}
E không thể tới D.
```

Đỉnh D được tính trong tập vì có **đường đi độ dài 0 từ D tới chính D**. Nếu ứng dụng yêu cầu ít nhất một cung, phải điều chỉnh cách diễn giải kết quả.

Với danh sách kề ngược, **một lần BFS** từ đích có độ phức tạp **`O(n+m)` trong trường hợp duyệt toàn đồ thị**, hoặc theo số đỉnh/cung thực sự được thăm. Không phải chạy BFS riêng từ từng đỉnh nguồn.

### Phân biệt truy vấn trực tiếp với truy vấn nhiều bước

- `in[B]`: ai có **cung trực tiếp** tới B?
- BFS/DFS ngược từ B: ai có thể tới B **qua một hoặc nhiều cung** (và kể cả B theo quy ước đường đi rỗng)?
- `indeg(B)`: tổng **số cung trực tiếp** vào B, có thể lớn hơn số nguồn phân biệt khi có cung song song.

Ba câu hỏi này không nên bị trộn thành một thao tác duy nhất.

## 9. Những ứng dụng thuật toán khác

### 9.1. Phân tích phụ thuộc học phần

Nếu `A→B` nghĩa là **A phải học trước B**, `in[B]` liệt kê **các điều kiện tiên quyết trực tiếp** của B; `out[A]` liệt kê những học phần trực tiếp phụ thuộc vào A.

Muốn biết **toàn bộ điều kiện tiên quyết trực tiếp và gián tiếp** của B, dùng DFS/BFS ngược từ B (không chỉ đọc `in[B]`). Nếu đồ thị có **chu trình phụ thuộc**, cần phát hiện và xử lý theo quy tắc nghiệp vụ; một vòng `A→B→A` thường là lỗi dữ liệu nếu các học phần bắt buộc hình thành DAG.

### 9.2. Thành phần liên thông mạnh

Trong đồ thị có hướng, hai đỉnh `u,v` thuộc cùng **thành phần liên thông mạnh (strongly connected component, SCC)** nếu `u` đi tới được `v` và ngược lại.

Thuật toán **Kosaraju** sử dụng hai lượt DFS và một lần xét **đồ thị đảo chiều** (trước hoặc sau tùy biến thể, cùng với quy tắc thứ tự hoàn thành phù hợp). Với danh sách kề, toàn bộ quy trình có thể thực hiện trong **`O(n+m)`**.

Không phải mọi thuật toán SCC đều cần tạo đồ thị ngược: **Tarjan** là một lựa chọn khác dựa vào DFS trên đồ thị gốc. Bài học ở đây là **khả năng truy cập cung ngược** rất hữu ích cho một số thuật toán, chứ không phải điều kiện bắt buộc của mọi thuật toán đồ thị.

### 9.3. Sắp xếp topo và bậc vào

**Kahn** là thuật toán sắp xếp topo cho đồ thị có hướng không chu trình:

1. Khởi tạo `indeg[v]` cho mọi đỉnh.
2. Đưa các đỉnh có bậc vào 0 vào queue.
3. Lấy một đỉnh ra, đưa vào kết quả, và giảm bậc vào của từng đích trong **`out[u]`**.
4. Nếu kết quả có ít hơn `n` đỉnh thì đồ thị chứa chu trình.

Thuật toán này chỉ cần **bộ đếm bậc vào** và **danh sách cung đi ra**. Nó **không bắt buộc lưu toàn bộ `in[v]`**. Ta có thể tính bậc vào một lượt từ `out` trong `O(n+m)` rồi dùng mảng đếm. Đây là ví dụ cần phân biệt giữa **giữ danh sách tất cả cung vào** với **chỉ giữ số lượng cung vào**.

## 10. Độ phức tạp theo cách biểu diễn

Giả sử số đỉnh là `n`, số cung thực là `m`, và phép truy cập ID/bản ghi có chi phí hằng số trong mô hình phân tích:

| Biểu diễn | Bộ nhớ | Liệt kê các cung đi vào `v` | Lấy `indeg(v)` | Lấy các cung đi ra `v` |
| --- | --- | --- | --- | --- |
| Chỉ `out` dạng list | `O(n+m)` | `O(n+m)` khi quét toàn bộ | `O(n+m)` nếu không có bộ đếm | `O(outdeg(v))` |
| Cả `out` và `in` dạng list | `O(n+m)`, hai bản ghi kề/cung | `\Theta(indeg(v))` để xuất tất cả | `O(1)` qua `len(in[v])` | `\Theta(outdeg(v))` |
| `out` cộng bộ đếm `indeg` | `O(n+m)` | `O(n+m)` nếu không có `in` | `O(1)` | `\Theta(outdeg(v))` |
| Ma trận kề `n×n` | `O(n^2)` | `O(n)` bằng quét **cột** `v` | `O(n)` nếu không cache | `O(n)` bằng quét **hàng** `v` |
| Danh sách cung thuần (*edge list*) | `O(n+m)` nếu giữ cả đỉnh | `O(m)` để lọc cung có đích `v` | `O(m)` nếu quét | `O(m)` nếu quét |

Trong ma trận kề, **đảo chiều** tương ứng với **chuyển vị**:

\[
A_{G^T}[i][j]=A_G[j][i].
\]

Tạo một bản sao ma trận chuyển vị đặc thường mất **`O(n^2)` thời gian và bộ nhớ**. Nếu chỉ cần **xem** ma trận chuyển vị và API hỗ trợ truy cập hoán đổi chỉ số, có thể dùng một *view* mà không cấp phát thêm ma trận, nhưng việc duyệt hàng/cột vẫn xét tới `n` ô.

### Thêm, xóa và tái dựng

Với list kề và ID cung đã biết:

- **Thêm cung `u→v`:** nối một mục vào `out[u]` và một mục vào `in[v]`; thường `O(1)` phân bổ/kỳ vọng khi không phải kiểm tra trùng đầu mút, cộng chi phí tra ID đỉnh.
- **Xóa cung theo ID:** nếu tìm và lọc list ở hai phía, tốn `O(outdeg(u)+indeg(v))` trong trường hợp xấu. Có thể thêm chỉ mục vị trí hoặc cấu trúc thích hợp để hỗ trợ xóa nhanh hơn, nhưng phải giữ đồng bộ.
- **Dựng `in` lại toàn bộ từ `out`:** `O(n+m)`. Nếu vừa thay đổi G mà vẫn dùng bản sao `G^T` cũ, kết quả duyệt ngược sẽ **lỗi thời**.

Đối với đồ thị **vô hướng**, khái niệm `in` và `out` không phân biệt theo chiều nên thường không cần hai chỉ mục như trên. Bài này chỉ áp dụng trực tiếp cho **đồ thị có hướng**.

## 11. Python: lớp đồ thị lưu đồng thời cung ra và cung vào

Ví dụ sau lưu **đỉnh kể cả khi cô lập**, **mỗi cung theo ID**, và **hai danh sách kề**. Cho phép cung song song và khuyên; trọng số được lưu trong bảng cung để không phải giữ nhiều bản sao. Từng ví dụ đầu ra có thể đối chiếu với mục 3.

```python
from collections import deque


class DoThiCoHuongHaiPhia:
    def __init__(self):
        self.ra = {}       # vertex_id -> [(target_id, edge_id), ...]
        self.vao = {}      # vertex_id -> [(source_id, edge_id), ...]
        self.cung = {}     # edge_id -> (source, target, weight)
        self._next_id = 0

    def them_dinh(self, u: str):
        if u in self.ra:
            raise ValueError("Đỉnh đã tồn tại")
        self.ra[u] = []
        self.vao[u] = []

    def them_cung(self, u: str, v: str, weight=1) -> int:
        if u not in self.ra or v not in self.ra:
            raise KeyError("Nguồn và đích phải tồn tại")
        eid = self._next_id
        self._next_id += 1
        self.cung[eid] = (u, v, weight)
        self.ra[u].append((v, eid))
        self.vao[v].append((u, eid))
        return eid

    def xoa_cung(self, eid: int):
        u, v, weight = self.cung.pop(eid)
        # Chỉ loại các mục có ID cần xóa;
        # những cung song song cùng đầu mút vẫn còn.
        self.ra[u] = [(d, j) for d, j in self.ra[u] if j != eid]
        self.vao[v] = [(s, j) for s, j in self.vao[v] if j != eid]
        return u, v, weight

    def bac_ra(self, u: str) -> int:
        return len(self.ra[u])

    def bac_vao(self, v: str) -> int:
        return len(self.vao[v])

    def cac_nguon_di_vao(self, v: str):
        # Trả (nguồn, edge_id), không làm mất cung song song.
        return list(self.vao[v])

    def bfs_nguoc(self, dich: str):
        if dich not in self.ra:
            raise KeyError(dich)
        hang_doi = deque([dich])
        da_tham = {dich}
        thu_tu = []
        while hang_doi:
            v = hang_doi.popleft()
            thu_tu.append(v)
            for nguon, _ in self.vao[v]:
                if nguon not in da_tham:
                    da_tham.add(nguon)  # Đánh dấu ngay khi vào queue
                    hang_doi.append(nguon)
        return thu_tu

    def dao_chieu(self):
        # Tạo đồ thị độc lập; giữ nguyên edge_id để tiện đối chiếu.
        nguoc = DoThiCoHuongHaiPhia()
        for u in self.ra:
            nguoc.them_dinh(u)
        for eid, (u, v, weight) in self.cung.items():
            nguoc.cung[eid] = (v, u, weight)
            nguoc.ra[v].append((u, eid))
            nguoc.vao[u].append((v, eid))
        nguoc._next_id = self._next_id
        return nguoc


g = DoThiCoHuongHaiPhia()
for ma in "ABCDE":
    g.them_dinh(ma)

e0 = g.them_cung("A", "B", 5)
e1 = g.them_cung("C", "B", 2)
e2 = g.them_cung("B", "D", 3)
e3 = g.them_cung("C", "D", 7)
e4 = g.them_cung("D", "D", 0)  # Khuyên
e5 = g.them_cung("A", "B", 9)  # Cung song song

print((e0, e1, e2, e3, e4, e5))  # (0, 1, 2, 3, 4, 5)
print(g.ra["A"])                 # [('B', 0), ('B', 5)]
print(g.vao["B"])                # [('A', 0), ('C', 1), ('A', 5)]
print(g.vao["E"])                # []: đỉnh cô lập
print([g.bac_ra(v) for v in "ABCDE"])   # [2, 1, 2, 1, 0]
print([g.bac_vao(v) for v in "ABCDE"])  # [0, 3, 0, 3, 0]
print(sum(map(g.bac_ra, "ABCDE")))      # 6
print(sum(map(g.bac_vao, "ABCDE")))     # 6

print(g.bfs_nguoc("D"))         # ['D', 'B', 'C', 'A']
print(g.bfs_nguoc("B"))         # ['B', 'A', 'C']
print(g.bfs_nguoc("E"))         # ['E']

t = g.dao_chieu()
print(t.ra["B"])               # [('A', 0), ('C', 1), ('A', 5)]
print(t.cung[e0])              # ('B', 'A', 5)
print(g.cung[e0])              # ('A', 'B', 5): g không đổi
print(t.cung[e4])              # ('D', 'D', 0): khuyên giữ nguyên

g.xoa_cung(e0)
print(g.vao["B"])              # [('C', 1), ('A', 5)]
print(g.ra["A"])               # [('B', 5)]
print(g.bac_vao("B"))          # 2
print(t.ra["B"])               # [('A', 0), ('C', 1), ('A', 5)]: t vẫn giữ e0
```

**Giải thích các kết quả:**

- `g.bfs_nguoc("D")` thăm D, rồi B và C, tiếp theo tới A; E bị loại vì không có đường đến D. Thứ tự cụ thể phụ thuộc thứ tự các mục `vao`, còn **tập kết quả** là bất biến theo đồ thị.
- `e0` và `e5` cùng nguồn A, đích B nhưng khác ID. Sau khi xóa `e0`, `e5` vẫn còn trong **cả hai chỉ mục**.
- `t` là **bản sao đồ thị đảo chiều** tại thời điểm tạo. Xóa cạnh trong `g` sau đó không tự xóa cạnh tương ứng trong `t`. Nếu muốn `t` luôn mới, phải cập nhật đồng bộ hoặc dựng lại.
- Trong `dao_chieu`, mỗi cung giữ **ID và trọng số** nhưng đảo `(u,v)` thành `(v,u)`. Bảng `cung` được tạo mới nên G gốc không bị sửa.

**Giới hạn của ví dụ:** chưa có xóa đỉnh, giao dịch nhiều luồng hay xác thực miền giá trị trọng số; xóa cung tìm và lọc cả hai list nên không phải thời gian xấu nhất `O(1)`. Nếu triển khai cho đồ thị lớn và cập nhật thường xuyên, cân nhắc bộ chỉ mục theo ID và cách quản lý vòng đời đối tượng.

## 12. Ma trận kề, danh sách cạnh và đồ thị đảo chiều

Cùng một truy vấn “những cung nào đi vào đỉnh `v`?” có cách triển khai khác nhau theo biểu diễn:

**Ma trận kề:** với quy ước `A[u][v]` biểu diễn cung `u→v`, muốn tìm nguồn vào `v` phải quét **cột `v`**. Ngược lại, quét **hàng `u`** để tìm các cung đi ra. Đảo chiều đồ thị tương ứng với **chuyển vị ma trận**, không phải tự làm ma trận đối xứng.

**Danh sách cạnh:** nếu có `edges=[(u,v,weight,edge_id),...]`, muốn liệt kê các cung vào `v` có thể lọc `edge.target==v`, tốn **`O(m)`**. Để xây dựng danh sách kề đảo chiều, duyệt mỗi bản ghi và chèn `u` vào danh sách của `v`, với tổng chi phí `O(n+m)`.

**Danh sách kề hai phía:** `in[v]` đã là danh sách cung đi ra trong đồ thị đảo chiều, nên phù hợp khi cần hỏi cả hai chiều truy vấn. Nhưng **không được** nhầm việc lưu thêm chỉ mục `in` với việc thay đổi `E` của đồ thị gốc.

Khi các đỉnh dùng ID chuỗi, có thể cần bảng ánh xạ `ID → index` cho ma trận; khi dùng `dict` cho danh sách kề, việc tra ID thông thường là `O(1)` kỳ vọng nếu băm tốt và khóa ổn định, chưa kể chi phí băm chuỗi dài.

## 13. Những sai lầm thường gặp

1. **Nhầm `in[v]` với `out[v]`.** Cung `A→B` thuộc `out[A]` và `in[B]`, không mặc nhiên thuộc `out[B]`.
2. **Thêm cung ngược vào G khi chỉ muốn truy vấn đi vào.** Biến đổi đó làm thay đổi quan hệ khả năng đi tới trong đồ thị gốc.
3. **Đếm số nguồn phân biệt thay cho số cung đi vào.** Hai cung song song A→B làm `indeg(B)=2` dù chỉ có một nguồn phân biệt.
4. **Chỉ thêm một phía khi có khuyên `u→u`.** Cần cập nhật cả `out[u]` và `in[u]`.
5. **Quên đỉnh cô lập.** Đỉnh không có cung vẫn phải tồn tại trong cả hai bảng.
6. **Xóa cung nhưng không sửa `in`.** Truy vấn người theo dõi/điều kiện tiên quyết có thể trả dữ liệu đã xóa.
7. **Dùng một edge ID cho hai cung khác nhau.** Không còn khả năng truy vết và xóa một cung riêng biệt.
8. **Tưởng duyệt trực tiếp `in[v]` trả mọi đỉnh có thể tới v.** Nó chỉ trả **đỉnh có cung trực tiếp**; cần BFS/DFS ngược cho quan hệ nhiều bước.
9. **Tưởng sắp xếp topo cần toàn bộ danh sách `in`.** Kahn có thể dùng riêng bộ đếm bậc vào và `out`.
10. **Đảo trọng số hoặc giả định chiều ngược ngoài đời thật tồn tại.** Transpose là phép biến đổi toán học trên cung và thuộc tính, không là dữ liệu đường ngược thực tế.
11. **Lấy kết quả từ bản sao `G^T` cũ sau khi G đã cập nhật.** Cần tái dựng hoặc duy trì đồng bộ.
12. **Đếm mỗi mục trong cả `out` lẫn `in` như một cung mới.** Mỗi cung chỉ là một bản ghi `edges[edge_id]`, hai mục là hai chỉ mục.

## 14. Tự kiểm tra

**Câu 1.** Với các cung `A→B`, `C→B` và `B→D`, `out[B]` và `in[B]` gồm những đỉnh nào?

**Đáp án:** `out[B]=[D]`; `in[B]=[A,C]`. Chỉ có cung B→D đi ra từ B, còn A→B và C→B đi vào B.

**Câu 2.** Nếu có **hai** cung song song A→B, một cung C→B và một cung khuyên B→B, hãy tính `indeg(B)` và `outdeg(B)`.

**Đáp án:** `indeg(B)=4`: hai cung từ A, một từ C, một khuyên. `outdeg(B)=1` do cung khuyên. Nếu `in[B]` chỉ lưu **tập nguồn phân biệt**, nó có `{A,C,B}` gồm ba phần tử, không phải bậc vào 4.

**Câu 3.** Khi thêm cung `u→v` trong một biểu diễn có cả hai chỉ mục và edge ID `e`, những mục nào phải được thêm?

**Đáp án:** Thêm `(v,e)` vào `out[u]` và `(u,e)` vào `in[v]`, đồng thời lưu bản ghi `e→(u,v,...)`. Cung `v→u` không được tự tạo trong đồ thị gốc.

**Câu 4.** Vì sao một phép duyệt trực tiếp `in[D]` không đủ tìm mọi đỉnh có thể tới D trong đồ thị `A→B→D`?

**Đáp án:** `in[D]` chỉ chứa B. A có đường tới D **qua B**, nên phải lặp lại việc tìm nguồn của những đỉnh đã phát hiện; BFS/DFS từ D trên đồ thị đảo chiều trả B rồi A.

**Câu 5.** Cho cung `A→B` trọng số 7 trong G. Nó biến thành gì trong `G^T`? Có được suy ra ngoài đời tồn tại đường B→A giá 7 không?

**Đáp án:** Trong `G^T` có cung B→A trọng số 7 tương ứng, nhưng đó là **biểu diễn toán học**. Không được tự suy ra một liên kết thực tế chiều B→A có tồn tại hoặc cùng chi phí.

**Câu 6.** Có thể xây dựng toàn bộ danh sách `in` từ `out` với chi phí bao nhiêu nếu có `n` đỉnh và `m` cung?

**Đáp án:** Tạo n danh sách rỗng và quét m mục cung đi ra, tổng **`\Theta(n+m)` thời gian** và bộ nhớ cho chỉ mục ngược mới.

**Câu 7.** Một chương trình chỉ cần `indeg(v)` để chạy Kahn, không cần liệt kê nguồn đi vào. Có nhất thiết lưu `in[v]` cho mọi đỉnh?

**Đáp án:** Không. Có thể duy trì hoặc tính trước **bộ đếm bậc vào** trong `O(n+m)`, rồi dùng `out` để giảm bậc vào khi loại đỉnh; toàn bộ danh sách `in` không bắt buộc.

**Câu 8.** Khi đã có `out` và `in` dạng list, lấy `indeg(v)` và liệt kê toàn bộ `k` cung vào `v` có chi phí lần lượt thế nào?

**Đáp án:** `len(in[v])` là **`O(1)`**, còn liệt kê `k` mục là **`\Theta(k)`**, giả sử tra được đỉnh trong thời gian hằng số.

**Câu 9.** Một cung khuyên D→D tạo bao nhiêu bản ghi cung thực và bao nhiêu mục chỉ mục nếu giữ `out` và `in`?

**Đáp án:** Có **một bản ghi cung** với một edge ID, một mục trong `out[D]` và một mục trong `in[D]`. Nó đóng góp một vào bậc ra và một vào bậc vào D.

**Câu 10.** Sau khi tạo bản sao `T=G^T`, G xóa một cung, nhưng T không thay đổi. Có nên tiếp tục dùng T để trả lời những truy vấn đi vào trên dữ liệu mới của G?

**Đáp án:** Không. T đã **lỗi thời**. Cần cập nhật T đúng cách đồng thời với G hoặc dựng lại từ G trước khi dùng kết quả làm thông tin hiện hành.

**Ghi nhớ:** Trong **đồ thị có hướng**, `out[u]` lưu các cung **xuất phát từ u**, còn `in[u]` lưu các cung **đi tới u**. **Đồ thị đảo chiều** `G^T` biến mỗi cung `u→v` thành `v→u` trong một đồ thị mới, nên duyệt từ đích trên `G^T` cho biết các đỉnh **có thể đi tới đích trong G**. Duy trì đồng thời hai danh sách kề tốn **`O(n+m)` bộ nhớ**, giúp liệt kê cung vào nhanh theo số mục cần trả, nhưng bắt buộc cập nhật hai phía **nhất quán** khi thêm/xóa, đặc biệt với **khuyên, cung song song và đỉnh cô lập**.
