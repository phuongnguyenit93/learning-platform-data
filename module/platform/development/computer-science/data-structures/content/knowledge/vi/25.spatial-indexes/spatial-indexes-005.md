# Truy vấn miền chữ nhật trên cây k-d

Một hệ thống bản đồ lưu hàng triệu địa điểm, nhưng màn hình của người dùng chỉ hiển thị một ô chữ nhật rất nhỏ. Nếu duyệt toàn bộ điểm rồi kiểm tra từng điểm có nằm trong cửa sổ hay không, ứng dụng sẽ làm nhiều việc thừa. **Cây k-d** (*k-dimensional tree*) giúp tổ chức các điểm theo những phép chia vuông góc với từng trục, từ đó loại được những cây con không thể chứa kết quả.

Nhưng có hai điều kiện phải hiểu thật chính xác: **miền hình học của cây con phải bao đủ dữ liệu**, và **quy tắc biên của truy vấn phải nhất quán với phép cắt tỉa**. Chỉ cần xử lý sai một dấu bằng ở biên, chương trình có thể bỏ sót điểm nằm đúng cạnh hình chữ nhật.

Bài thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, xây dựng nền tảng về bất biến, thao tác, thời gian và bộ nhớ của cấu trúc dữ liệu. Ta sẽ học cách viết truy vấn **orthogonal range reporting** (liệt kê điểm thuộc miền chữ nhật), **range counting** (đếm điểm), phân biệt cắt tỉa bằng **mặt chia** và bằng **hộp bao cây con**, xử lý biên đóng/nửa mở, phân tích độ phức tạp và viết ví dụ Python có thể đối chiếu với quét tuyến tính.

> **Bất biến quan trọng nhất:** Nếu một nhánh bị loại, ta phải chứng minh **không một điểm nào trong nhánh có thể thỏa điều kiện truy vấn**. Cắt tỉa rộng hơn mức cần thiết chỉ làm chậm; cắt tỉa nhầm một nhánh có kết quả là lỗi tính đúng.

## 1. Bài toán: liệt kê hoặc đếm điểm trong một hình chữ nhật

Trong không gian hai chiều, tập điểm:

\[
P=\{p_1,p_2,\ldots,p_n\},\qquad p_i=(x_i,y_i).
\]

Một hình chữ nhật song song với hai trục tọa độ, **bao gồm cả bốn cạnh**, được biểu diễn:

\[
\boxed{Q=[x_{\min},x_{\max}]\times[y_{\min},y_{\max}]},
\]

với \(x_{\min}\le x_{\max}\) và \(y_{\min}\le y_{\max}\).

Điểm \(p=(x,y)\) thuộc Q khi và chỉ khi:

\[
\boxed{
x_{\min}\le x\le x_{\max}
\quad\land\quad
y_{\min}\le y\le y_{\max}.
}
\]

Hai loại truy vấn chính:

**Range reporting:**

\[
\boxed{R(Q)=\{p\in P:p\in Q\}.}
\]

Kết quả là **các bản ghi hoặc ID**, không chỉ số lượng. Nếu có \(k\) điểm được trả thì riêng việc xuất chúng đã cần \(\Omega(k)\) thao tác.

**Range counting:**

\[
\boxed{C(Q)=|R(Q)|.}
\]

Kết quả là **một số nguyên**. Nếu mỗi cây con lưu sẵn số điểm, một vùng được Q chứa trọn có thể đóng góp trực tiếp số điểm ấy mà không cần liệt kê tất cả.

### Ví dụ cố định xuyên suốt

Cho các bản ghi:

| ID | Tọa độ | Ghi chú |
| --- | --- | --- |
| A | \((1,1)\) | Bên trong cửa sổ ví dụ |
| B | \((2,2)\) | Bên trong |
| C | \((4,4)\) | Trên cạnh phải và trên |
| D | \((4,1)\) | Trên cạnh phải |
| E | \((6,3)\) | Nằm ngoài phía phải |
| F | \((8,8)\) | Xa cửa sổ |
| G | \((4,4)\) | Cùng tọa độ C nhưng ID khác |
| H | \((-2,3)\) | Tọa độ x âm |
| I | \((0,0)\) | Ở gốc tọa độ |

Với:

\[
Q=[1,4]\times[1,4],
\]

kết quả theo ID là:

\[
\boxed{R(Q)=\{A,B,C,D,G\},\qquad C(Q)=5.}
\]

C và G là **hai bản ghi**, dù có cùng tọa độ. Không được bỏ G chỉ vì trùng vị trí với C. Các điểm trên biên phải/trên vẫn được nhận vì Q là **hình chữ nhật đóng**.

### So với quét tuyến tính

~~~python
def brute_rectangle(points, xmin, ymin, xmax, ymax):
    return [
        point for point in points
        if xmin <= point.x <= xmax
        and ymin <= point.y <= ymax
    ]
~~~

Quét tuyến tính kiểm tra \(n\) bản ghi, tốn \(O(n)\) với điểm 2D. Nó là **mốc tham chiếu để kiểm thử tính đúng**, đồng thời có thể đủ nhanh khi n nhỏ hoặc truy vấn hiếm.

## 2. Cây k-d lưu những gì?

K-d tree là một cây nhị phân cho các điểm nhiều chiều. Một nút thông dụng lưu:

- **Pivot:** một bản ghi điểm có ID duy nhất.
- **Axis:** trục được chọn để phân chia tại nút, như x hoặc y.
- **Left/right:** hai cây con với các điểm được phân về từng phía.
- **Bounding box (AABB):** hộp bao tất cả điểm trong cây con, gồm pivot.
- **Subtree size (tùy chọn):** số điểm trong cây con, hữu ích cho range counting.

Một cách xây cây tĩnh dễ hiểu là **chọn median** theo một trục rồi đệ quy với hai nửa dữ liệu. Với trục lựa chọn \(j\), đặt khóa:

\[
K_j(p)=(p_j,\operatorname{ID}(p)).
\]

Các ID phải duy nhất và có thứ tự ổn định. Khi chọn pivot \(v\):

\[
\boxed{\forall p\in Left(v):K_j(p)<K_j(v)}
\]

và:

\[
\boxed{\forall p\in Right(v):K_j(p)>K_j(v).}
\]

Quy ước này giúp phân chia cân bằng số bản ghi **kể cả khi nhiều điểm trùng tọa độ**. Tuy nhiên, một điểm có cùng tọa độ trục với pivot có thể xuất hiện ở phía trái **hoặc** phía phải tùy ID. Đây là lý do không thể dùng dấu so sánh tọa độ quá mạnh khi prune theo mặt chia.

### Chọn trục

Trong 2D, chính sách đơn giản là luân phiên:

\[
\boxed{\operatorname{axis}(depth)=depth\bmod 2.}
\]

Gốc chọn x, con chọn y, cháu lại chọn x. Một chính sách khác chọn **trục có khoảng trải rộng lớn nhất** trong tập điểm hiện tại.

**Điều cần nhớ:** Range query không được phụ thuộc vào việc cây chọn trục cyclic hay widest. Nếu cây giữ đúng bất biến và AABB, cả hai chính sách phải trả **cùng một tập kết quả**, dù có thể thăm số nút khác nhau.

## 3. Minh họa một phép chia theo x rồi y

Giả sử chọn điểm \(v=(5,5)\) làm pivot gốc theo trục x. Những điểm có khóa \((x,ID)\) nhỏ hơn khóa của v được đưa trái; những điểm lớn hơn được đưa phải. Ở mức kế tiếp, ta có thể đổi trục thành y.

~~~text
                       root: (5,5), axis=x
                         /               \
                 x nhỏ hơn (*)        x lớn hơn (*)
                node axis=y          node axis=y
                 /      \             /      \
              y thấp   y cao       y thấp   y cao

(*) So khóa (x,ID), không chỉ so số x khi bằng nhau.
~~~

Các đường chia hình học tạo các miền con. Điểm thực trong các miền đó có thể được bao bằng các AABB **chặt hơn** so với miền lý thuyết.

### Sự khác nhau giữa miền phân hoạch và AABB dữ liệu

**Miền phân hoạch (*split cell*):** vùng suy ra từ tất cả điều kiện tách tại các tổ tiên. Một miền có thể rất rộng, thậm chí không giới hạn về một phía nếu root không có miền gốc hữu hạn.

**AABB cây con (*subtree bounding box*):** hộp min/max tính từ **chính các điểm hiện có** trong cây con:

\[
B(v)=
[\min x,\max x]\times[\min y,\max y],
\]

trong đó min/max lấy trên **pivot v và mọi điểm dưới v**.

AABB của cây con thường nhỏ hơn miền phân hoạch. Khi truy vấn chỉ cần biết có điểm hay không, dùng AABB chặt hơn có thể prune được nhiều nhánh hơn.

> **Phân biệt:** Split cell dùng để nói điểm *có thể được phân vào vùng nào* theo cây; AABB dùng để nói điểm *hiện đang thực sự nằm trong giới hạn nào*. Không được tính AABB chỉ từ pivot mà bỏ qua hậu duệ.

## 4. Điều kiện hai hình chữ nhật giao nhau

Cho hai hộp **đóng**:

\[
A=[a_{x0},a_{x1}]\times[a_{y0},a_{y1}],
\quad
B=[b_{x0},b_{x1}]\times[b_{y0},b_{y1}].
\]

Chúng **không giao nhau** nếu có ít nhất một trục tách rời:

\[
\boxed{
a_{x1}<b_{x0}
\;\lor\;
b_{x1}<a_{x0}
\;\lor\;
a_{y1}<b_{y0}
\;\lor\;
b_{y1}<a_{y0}.
}
\]

Vì thế chúng giao nhau khi:

\[
\boxed{
a_{x0}\le b_{x1}
\;\land\;
b_{x0}\le a_{x1}
\;\land\;
a_{y0}\le b_{y1}
\;\land\;
b_{y0}\le a_{y1}.
}
\]

### Chạm biên vẫn được tính là giao

Ví dụ:

\[
A=[0,4]\times[0,4],\qquad
B=[4,8]\times[2,6].
\]

Giao là đoạn:

\[
A\cap B=\{4\}\times[2,4].
\]

Đoạn này có diện tích bằng 0 nhưng **không rỗng**. Nếu đang truy vấn **điểm** và một điểm có \(x=4\), nó có thể thuộc cả hai hộp đóng.

**Không dùng điều kiện giao nghiêm ngặt** với dấu \(<\) trong bài toán hộp đóng rồi kỳ vọng trả đủ điểm đúng cạnh. Điều kiện dùng dấu \(<\) thường phù hợp với hai vùng *nửa mở không rỗng*, không phải tự động phù hợp với hộp bao các điểm và cửa sổ đóng.

## 5. Ba trường hợp khi truy vấn đi qua một nút

Với cửa sổ Q và AABB cây con B, thuật toán có ba trường hợp **loại trừ nhau**:

**Trường hợp A — Tách rời:** \(B\cap Q=\varnothing\).

Không cần đọc bất kỳ điểm nào ở cây con. Ta bỏ nhánh **an toàn** vì mọi điểm dưới nút đều nằm trong B.

**Trường hợp B — Q bao trọn B:** \(B\subseteq Q\).

Mọi điểm trong cây con đều thuộc Q. Nếu cần **liệt kê**, thu toàn bộ điểm cây con **không cần kiểm tra predicate từng điểm**. Nếu chỉ cần **đếm**, cộng thẳng **subtree size** của nút và **không xuống các con**.

**Trường hợp C — Giao một phần:** \(B\cap Q\neq\varnothing\), nhưng \(B\not\subseteq Q\).

Kiểm tra pivot rồi đệ quy xuống các con cần thiết.

~~~mermaid
flowchart TD
    A["Bắt đầu tại nút v, có AABB B(v)"] --> B{"B(v) giao cửa sổ Q?"}
    B -->|Không| C["Loại toàn bộ cây con"]
    B -->|Có| D{"Q bao trọn B(v)?"}
    D -->|Có| E["Reporting: xuất cả cây con"]
    D -->|Có| F["Counting: cộng subtree size"]
    D -->|Không| G["Kiểm tra pivot và đệ quy xuống hai con"]
~~~

### Kiểm tra Q chứa trọn B

Trong 2D, Q chứa B khi:

\[
\boxed{
q_{x0}\le b_{x0}\le b_{x1}\le q_{x1}
\quad\land\quad
q_{y0}\le b_{y0}\le b_{y1}\le q_{y1}.
}
\]

Nếu AABB được tính **chính xác** từ các điểm của cây con, điều kiện này là đủ cho tất cả điểm. Trong ứng dụng còn có thể lưu AABB **bảo thủ** (bao rộng hơn dữ liệu thật), khi đó điều kiện Q chứa B vẫn là **đủ** nhưng có thể xảy ra ít hơn.

### Đếm có thể nhanh hơn liệt kê

Giả sử Q chứa toàn bộ AABB của một cây con có 50.000 điểm:

- **Reporting:** phải xuất 50.000 ID; mất ít nhất \(\Omega(50\,000)\) thời gian.
- **Counting:** có thể cộng đúng số \(50\,000\) trong \(O(1)\) với trường size đã lưu.

Đây là khác biệt thật sự về yêu cầu đầu ra, không phải do một kiểu truy vấn được lập chỉ mục “thông minh” hơn kiểu còn lại.

## 6. Mã giả range reporting và range counting

### Liệt kê điểm

~~~text
RANGE_REPORT(node, query):
    nếu node là null:
        return

    nếu bbox(node) hoàn toàn ngoài query:
        return

    nếu bbox(node) nằm trọn trong query:
        EMIT_SUBTREE(node)   # Đọc mọi điểm trong cây con
        return

    nếu pivot(node) thuộc query:
        xuất pivot(node)

    RANGE_REPORT(node.left, query)
    RANGE_REPORT(node.right, query)
~~~

### Đếm điểm

~~~text
RANGE_COUNT(node, query):
    nếu node là null:
        return 0

    nếu bbox(node) hoàn toàn ngoài query:
        return 0

    nếu bbox(node) nằm trọn trong query:
        return subtree_size(node)

    answer = 1 nếu pivot(node) thuộc query, ngược lại 0
    answer += RANGE_COUNT(node.left, query)
    answer += RANGE_COUNT(node.right, query)
    return answer
~~~

Để tăng tốc, có thể kiểm tra **bbox của con trước khi gọi đệ quy**; nhưng việc kiểm tra đó đã nằm ở đầu hàm trong mã giả, nên không cần lặp điều kiện thêm để giữ tính đúng.

### Bất biến chứng minh bằng quy nạp

Với một node bất kỳ:

1. Nếu B ngoài Q, số điểm hợp lệ bằng 0.
2. Nếu Q chứa B, số điểm hợp lệ bằng đúng size.
3. Nếu giao một phần, tập điểm của cây con gồm **pivot**, tập điểm của cây trái và tập điểm của cây phải, các ID không trùng nhau.

Vì vậy:

\[
\boxed{R(v,Q)
=R(\{pivot(v)\},Q)
\;\cup\;R(left(v),Q)
\;\cup\;R(right(v),Q).}
\]

Trong trường hợp C, công thức đệ quy không bỏ sót và không lặp ID nếu mỗi bản ghi được lưu đúng một lần. Kết hợp ba trường hợp, ta có thuật toán trả **đúng mọi điểm trong Q**.

## 7. Cắt tỉa bằng mặt chia: sử dụng thế nào cho an toàn?

Một k-d tree không nhất thiết phải lưu AABB tại mọi nút. Trong phiên bản cơ bản, ta có thể quyết định nhánh nào cần thăm dựa trên **mặt chia** của nút.

Giả sử pivot có tọa độ chia \(s=v_{axis}\). Theo bất biến khóa tổng hợp \((p_{axis},ID)\):

- Mọi điểm ở trái có tọa độ trên trục **\(\le s\)**.
- Mọi điểm ở phải có tọa độ trên trục **\(\ge s\)**.

Khi đó với cửa sổ đóng \([q_{\min},q_{\max}]\) trên trục chia:

| Tình huống | Nhánh có thể bỏ | Lý do |
| --- | --- | --- |
| \(q_{\max}<s\) | Phải | Mọi điểm bên phải có tọa độ \(\ge s>q_{\max}\) |
| \(q_{\min}>s\) | Trái | Mọi điểm bên trái có tọa độ \(\le s<q_{\min}\) |
| \(q_{\min}\le s\le q_{\max}\) | Không được tự bỏ trái hoặc phải chỉ theo trục này | Hai phía có thể chứa điểm tọa độ bằng s |

**Quan trọng:** Trường hợp \(q_{\min}=s\) hoặc \(q_{\max}=s\) phải được xử lý như **cửa sổ chạm mặt chia**, vì query đóng **bao gồm** điểm nằm trên mặt đó.

### Khi chỉ dùng tọa độ, không dùng ID trong khóa

Một biến thể có thể quy định:

\[
p\in Left\Rightarrow p_{axis}<s,
\qquad
p\in Right\Rightarrow p_{axis}\ge s.
\]

Khi ấy các điểm bằng s chỉ đi phải và có thể tối ưu hơn một số điều kiện. Nhưng nếu cây đã xây bằng khóa **(tọa độ, ID)** thì không được tùy tiện áp dụng quy tắc trên. **Cắt tỉa phải được chứng minh từ bất biến thực tế của cây**, không phải từ một quy ước phổ biến của thư viện khác.

### Vì sao AABB thường dễ kiểm chứng hơn?

Mặt chia chỉ cho thông tin trên **một trục tại một nút** và phải kết hợp các ràng buộc của tổ tiên. AABB cây con cung cấp min/max **trên cả hai trục**, nên chỉ cần phép giao hình chữ nhật để quyết định nhánh có thể có kết quả hay không.

Tuy nhiên, lưu AABB tốn thêm bộ nhớ và phải cập nhật khi dữ liệu thay đổi. Một k-d tree đơn giản chỉ lưu split plane vẫn có thể thực hiện range query **đúng** nếu xử lý quy tắc biên cẩn thận.

## 8. Biên đóng, nửa mở và miền suy biến

Trong thực tế, một hệ thống bản đồ có thể dùng **hình chữ nhật đóng**, còn một engine xử lý dữ liệu theo ô có thể dùng hình **nửa mở**. Hai kiểu truy vấn khác nhau ở dấu bằng.

### 8.1. Hình đóng

\[
\boxed{
Q_{\mathrm{closed}}
=[a_x,b_x]\times[a_y,b_y].
}
\]

Predicate điểm:

\[
a_x\le x\le b_x,\qquad a_y\le y\le b_y.
\]

Nếu \(a_x=b_x\), Q có thể là **đoạn thẳng đứng**; nếu cả hai cặp cận bằng nhau, Q là **một điểm**. Các truy vấn này **không rỗng** theo quy tắc đóng.

### 8.2. Hình nửa mở

\[
\boxed{
Q_{\mathrm{halfopen}}
=[a_x,b_x)\times[a_y,b_y).
}
\]

Predicate điểm:

\[
a_x\le x<b_x,\qquad a_y\le y<b_y.
\]

Nếu \(a_x=b_x\) **hoặc** \(a_y=b_y\), miền nửa mở là **rỗng** và trả 0 kết quả.

### 8.3. AABB cây con là hộp đóng của các điểm

Một chi tiết dễ gây lỗi: AABB tính từ min/max của **tập điểm hữu hạn**:

\[
B=[\min x,\max x]\times[\min y,\max y]
\]

phải được hiểu là **bao gồm** cả min và max. Nếu cây con chỉ có một điểm \((4,4)\), bbox của nó là:

\[
B=[4,4]\times[4,4],
\]

vẫn **chứa một điểm**, không phải hộp rỗng.

Do đó phép kiểm tra AABB so với **Q nửa mở** phải tính việc bbox có thể là hộp suy biến:

**B không chứa điểm nào thuộc Q nếu trên ít nhất một trục:**

\[
\boxed{
B.hi_i<Q.lo_i
\quad\lor\quad
B.lo_i\ge Q.hi_i.
}
\]

Chú ý bất đẳng thức **khác nhau**: \(B.hi_i<Q.lo_i\) là điều kiện nghiêm ngặt, bởi điểm tại **biên trái Q** vẫn được nhận. Còn \(B.lo_i\ge Q.hi_i\) có dấu bằng, vì **biên phải Q bị loại**.

### 8.4. Q nửa mở chứa trọn AABB khi nào?

Với mỗi trục:

\[
\boxed{
Q.lo_i\le B.lo_i
\quad\land\quad
B.hi_i<Q.hi_i.
}
\]

Tức là cận trên phải **nghiêm ngặt nhỏ hơn** cận trên Q. Nếu \(B.hi_x=Q.hi_x\), có thể có điểm ở đúng cận trên bị loại, nên không được nhận cả cây con.

### Ví dụ biên của tập điểm

Vẫn tập A–I ở mục 1:

| Truy vấn | Quy tắc | Kết quả |
| --- | --- | --- |
| \([1,4]\times[1,4]\) | Đóng | A, B, C, D, G |
| \([1,4)\times[1,4)\) | Nửa mở | A, B |
| \([4,4]\times[1,4]\) | Đóng | C, D, G |
| \([4,4)\times[1,4)\) | Nửa mở | Rỗng |
| \([-3,0]\times[0,4]\) | Đóng | H, I |

**Không được trộn predicate đóng ở lá với phép prune nửa mở không phù hợp ở nút trong**, vì đây là nguyên nhân của lỗi thiếu điểm trên cạnh.

## 9. Minh họa từng bước với miền chữ nhật

Xét các điểm:

\[
\begin{aligned}
A&=(1,1),& B&=(2,2),& C&=(4,4),\\
D&=(4,1),& E&=(6,3),& F&=(8,8).
\end{aligned}
\]

Ta dựng k-d tree bằng median, trục x ở gốc và y ở mức kế tiếp. Khi xử lý Q=\([1,4]\times[1,4]\), một nhánh có bbox nằm hoàn toàn ở \(x\ge6\) sẽ bị loại vì Q chỉ đến \(x=4\).

Một nhánh khác có bbox \([1,2]\times[1,2]\) được Q **chứa trọn**; ta có thể trả ngay các điểm A và B mà không cần kiểm tra tọa độ riêng lẻ.

Ở nhánh có C và D (đều \(x=4\)), phải giữ **dấu bằng biên phải**, nên cả C và D hợp lệ. Kết quả:

\[
\boxed{\{A,B,C,D\}}.
\]

Ở ví dụ này không có G trùng tọa độ; nếu thêm G=(4,4) với ID khác, kết quả phải bổ sung G.

### Mô hình các nhánh

~~~text
Tại một nút:

               bbox(node) giao Q?
                       |
              +--------+--------+
             không              có
               |                 |
         bỏ toàn nhánh       bbox trong Q?
                                 |
                        +--------+-------+
                       có               không
                        |                 |
                xuất toàn cây con    kiểm tra pivot
                                    và thăm các con
~~~

Cách trình bày này tránh cần mô phỏng chính xác từng pivot của một cây cụ thể: dù cây chọn trục cyclic hay widest, ba trường hợp **ngoài / trong trọn / giao một phần** luôn đúng nếu AABB bao đủ cây con.

## 10. Cấu trúc dữ liệu và metadata cần giữ

Một node dùng để tối ưu range query thường có các trường sau:

| Trường | Vai trò | Bất biến |
| --- | --- | --- |
| point | Pivot (ID, tọa độ) | ID xuất hiện đúng một lần trong cây |
| axis | Trục phân chia tại node | Là trục hợp lệ \(0\ldots d-1\) |
| left/right | Hai con | Tuân thủ khóa phân hoạch của node |
| bbox_lo | Min từng chiều của cây con | \(\forall p\) trong cây con: \(bbox\_lo_i\le p_i\) |
| bbox_hi | Max từng chiều của cây con | \(\forall p\) trong cây con: \(p_i\le bbox\_hi_i\) |
| subtree_size | Số điểm trong cây con | \(1+size(left)+size(right)\) |

### Cách tính bottom-up

Khi dựng node từ pivot và hai con:

\[
\boxed{size(v)=1+size(left(v))+size(right(v)).}
\]

Với từng trục \(i\):

\[
\boxed{
lo_i(v)=\min\{v_i,lo_i(left),lo_i(right)\},
}
\]

\[
\boxed{
hi_i(v)=\max\{v_i,hi_i(left),hi_i(right)\}.
}
\]

Các toán hạng của con rỗng phải được bỏ qua, không tự gán min=0 hoặc max=0 vì dữ liệu có thể nằm hoàn toàn ở tọa độ âm.

### Cập nhật sai một trường gây lỗi gì?

Nếu sau khi di chuyển điểm mà bbox không còn bao điểm mới, range query có thể **prune sai** và bỏ sót điểm.

Nếu subtree_size chưa cập nhật đúng, range reporting vẫn có thể trả đúng nhưng **range counting** có thể sai ngay cả khi Q chứa trọn AABB.

Nếu ID bị trùng giữa pivot và nhánh con, reporting có thể trả trùng và counting có thể đếm sai.

**Vì vậy ba metadata quan trọng — phân hoạch, bbox và size — phải được duy trì cùng một trạng thái logic.**

## 11. Độ phức tạp: phụ thuộc số nút thăm và số kết quả

Đặt:

- \(n\): số điểm trong chỉ mục.
- \(V_Q\): số node được truy cập/kiểm tra ở phép truy vấn.
- \(k\): số điểm kết quả được xuất.
- \(d\): số chiều.

Với AABB mỗi node và số chiều d:

\[
\boxed{
T_{\mathrm{report}}=O(dV_Q+k)
}
\]

cho phép duyệt xuất kết quả **không sắp thứ tự**. Nếu thực thi **sắp k kết quả theo ID**, cộng thêm \(O(k\log k)\).

Với counting và subtree_size:

\[
\boxed{
T_{\mathrm{count}}=O(dV_Q),
}
\]

trong đó \(V_Q\) chỉ tính những node thực sự cần kiểm tra. Khi Q chứa toàn bộ bbox gốc, có thể trả size gốc với **\(O(d)\)** phép so sánh, không cần duyệt \(n\) điểm.

### Vì sao vẫn có trường hợp xấu \(O(n)\)?

Nếu nhiều AABB của cây con đều giao Q một phần, thuật toán phải thăm nhiều node, thậm chí gần như **toàn bộ n node**. Chiều cao \(O(\log n)\) không bảo đảm range query chỉ xét \(O(\log n)\) node.

Trường hợp báo cáo k điểm cũng có giới hạn dưới:

\[
\boxed{T_{\mathrm{report}}=\Omega(k).}
\]

Một truy vấn trả hàng triệu điểm không thể xử lý và xuất đủ kết quả trong thời gian hằng số.

### Cận chuyên biệt thường thấy trong tài liệu

Đối với **k-d tree cân đối theo các phép chia trục và các giả thiết hình học chuẩn** trong \(d\) chiều cố định, một cận kinh điển cho truy vấn hộp song song trục là:

\[
\boxed{O(n^{1-1/d}+k)}
\]

với reporting; trong 2D là:

\[
\boxed{O(\sqrt n+k).}
\]

Cận này đòi hỏi **cách tổ chức phân hoạch và giả thiết tương ứng**; không phải lời hứa cho mọi kiểu cây k-d, mọi tie-break, mọi cách chèn động hoặc mọi cấu trúc chỉ dựa vào bounding box. Nó cũng không thay thế cận theo số node **thực sự đã thăm \(V_Q\)** khi phân tích một triển khai cụ thể.

### Chi phí xây dựng và bộ nhớ

Nếu mỗi node dùng **sort lại tập điểm con** để chọn median, với n điểm và d cố định, chi phí xây cây cân đối của cách viết đơn giản thường:

\[
\boxed{O(n\log^2n).}
\]

Nếu có lựa chọn trung vị tuyến tính hoặc cấu trúc giữ các danh sách sắp, có thể cải thiện trong giả thiết thích hợp.

Với d chiều, mỗi node lưu \(2d\) tọa độ AABB và một số nguyên size:

\[
\boxed{\text{Bộ nhớ}=O(nd)}
\]

cho toàn bộ các node và bbox, khi ID/điểm cũng được lưu tại các node. Với d=2 cố định, đó là \(O(n)\) bộ nhớ.

## 12. Python: k-d tree 2D hỗ trợ reporting và counting

Mã dưới đây dành cho **Python 3.10+**, chỉ dùng thư viện chuẩn. Nó minh họa hai cách chọn trục (**cyclic** hoặc **widest spread**), median split với tie-break bằng ID, AABB chính xác, subtree size và hai kiểu biên truy vấn:

- **Đóng:** bao gồm cả cạnh phải và cạnh trên.
- **Nửa mở:** bao gồm trái/dưới, loại phải/trên.

Mọi điểm có **ID riêng**, kể cả những điểm trùng tọa độ. Chỉ mục này là **tĩnh**: sau khi xây, không sửa tọa độ gốc tại chỗ. Khi có thay đổi, cần dùng chiến lược cập nhật/rebuild ở phần sau.

~~~python
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Point:
    id: str
    x: float
    y: float

    def axis_value(self, axis: int) -> float:
        return self.x if axis == 0 else self.y


@dataclass
class Node:
    point: Point
    axis: int
    left: Node | None
    right: Node | None
    lo: tuple[float, float]
    hi: tuple[float, float]
    size: int


class RectangleKDTree:
    def __init__(self, records, axis_strategy="cyclic"):
        if axis_strategy not in ("cyclic", "widest"):
            raise ValueError("Chọn cyclic hoặc widest")

        points = []
        seen = set()
        for item_id, raw_x, raw_y in records:
            if not isinstance(item_id, str) or not item_id:
                raise ValueError("ID phải là chuỗi không rỗng")
            if item_id in seen:
                raise ValueError("Trùng ID")

            x, y = float(raw_x), float(raw_y)
            if not (isfinite(x) and isfinite(y)):
                raise ValueError("Tọa độ phải hữu hạn")

            seen.add(item_id)
            points.append(Point(item_id, x, y))

        self.axis_strategy = axis_strategy
        self.root = self._build(points, depth=0)

    def _choose_axis(self, points, depth):
        if self.axis_strategy == "cyclic":
            return depth % 2

        spread_x = (
            max(p.x for p in points) - min(p.x for p in points)
        )
        spread_y = (
            max(p.y for p in points) - min(p.y for p in points)
        )
        # Nếu trải rộng bằng nhau, chọn x để ổn định.
        return 0 if spread_x >= spread_y else 1

    def _build(self, points, depth):
        if not points:
            return None

        axis = self._choose_axis(points, depth)
        ordered = sorted(
            points, key=lambda p: (p.axis_value(axis), p.id)
        )
        middle = len(ordered) // 2
        pivot = ordered[middle]

        left = self._build(ordered[:middle], depth + 1)
        right = self._build(ordered[middle + 1:], depth + 1)

        lo = [pivot.x, pivot.y]
        hi = [pivot.x, pivot.y]
        size = 1

        for child in (left, right):
            if child is None:
                continue
            size += child.size
            for axis_id in (0, 1):
                lo[axis_id] = min(lo[axis_id], child.lo[axis_id])
                hi[axis_id] = max(hi[axis_id], child.hi[axis_id])

        return Node(
            pivot, axis, left, right, tuple(lo), tuple(hi), size
        )

    @staticmethod
    def _parse_query(xmin, ymin, xmax, ymax, closed):
        values = tuple(
            float(v) for v in (xmin, ymin, xmax, ymax)
        )
        if not all(isfinite(v) for v in values):
            raise ValueError("Cận truy vấn phải hữu hạn")
        if type(closed) is not bool:
            raise ValueError("closed phải là bool")

        a, b, c, d = values
        if a > c or b > d:
            raise ValueError("Cận min không được vượt cận max")
        return a, b, c, d

    def _search(self, xmin, ymin, xmax, ymax,
                closed, want_points):
        xmin, ymin, xmax, ymax = self._parse_query(
            xmin, ymin, xmax, ymax, closed
        )
        # Hình nửa mở suy biến là tập rỗng.
        if not closed and (xmin == xmax or ymin == ymax):
            return [] if want_points else 0

        result = []
        count = 0

        def bbox_outside(node):
            if closed:
                return (
                    node.hi[0] < xmin or node.lo[0] > xmax
                    or node.hi[1] < ymin or node.lo[1] > ymax
                )
            return (
                node.hi[0] < xmin or node.lo[0] >= xmax
                or node.hi[1] < ymin or node.lo[1] >= ymax
            )

        def bbox_inside(node):
            if closed:
                return (
                    xmin <= node.lo[0] and node.hi[0] <= xmax
                    and ymin <= node.lo[1] and node.hi[1] <= ymax
                )
            return (
                xmin <= node.lo[0] and node.hi[0] < xmax
                and ymin <= node.lo[1] and node.hi[1] < ymax
            )

        def point_inside(point):
            if closed:
                return (
                    xmin <= point.x <= xmax
                    and ymin <= point.y <= ymax
                )
            return (
                xmin <= point.x < xmax
                and ymin <= point.y < ymax
            )

        def emit_all(node):
            if node is None:
                return
            result.append(node.point)
            emit_all(node.left)
            emit_all(node.right)

        def visit(node):
            nonlocal count
            if node is None or bbox_outside(node):
                return

            if bbox_inside(node):
                if want_points:
                    emit_all(node)   # Kết quả đúng, không lọc lại.
                else:
                    count += node.size
                return

            if point_inside(node.point):
                if want_points:
                    result.append(node.point)
                else:
                    count += 1

            visit(node.left)
            visit(node.right)

        visit(self.root)
        if want_points:
            # Thứ tự ổn định để kiểm thử: cộng O(k log k).
            return sorted(result, key=lambda p: p.id)
        return count

    def range_rect(self, xmin, ymin, xmax, ymax, closed=True):
        """Trả bản ghi trong hộp đóng hoặc nửa mở."""
        return self._search(
            xmin, ymin, xmax, ymax, closed, want_points=True
        )

    def count_rect(self, xmin, ymin, xmax, ymax, closed=True):
        """Đếm bằng subtree size khi query bao trọn bbox."""
        return self._search(
            xmin, ymin, xmax, ymax, closed, want_points=False
        )

    def validate(self):
        """Kiểm tra phân hoạch, AABB và subtree size."""
        all_ids = set()

        def walk(node, constraints):
            if node is None:
                return []

            for axis, boundary, left_side in constraints:
                key = (node.point.axis_value(axis), node.point.id)
                if left_side and not (key < boundary):
                    raise AssertionError("Sai khóa nhánh trái")
                if not left_side and not (key > boundary):
                    raise AssertionError("Sai khóa nhánh phải")

            if node.point.id in all_ids:
                raise AssertionError("ID bị lặp")
            all_ids.add(node.point.id)

            pivot_key = (
                node.point.axis_value(node.axis), node.point.id
            )
            left_points = walk(
                node.left, constraints + [(node.axis, pivot_key, True)]
            )
            right_points = walk(
                node.right, constraints + [(node.axis, pivot_key, False)]
            )
            all_points = [node.point] + left_points + right_points

            if node.size != len(all_points):
                raise AssertionError("subtree size không khớp")

            expected_lo = (
                min(p.x for p in all_points),
                min(p.y for p in all_points),
            )
            expected_hi = (
                max(p.x for p in all_points),
                max(p.y for p in all_points),
            )
            if node.lo != expected_lo or node.hi != expected_hi:
                raise AssertionError("AABB không đúng với dữ liệu")
            return all_points

        records = walk(self.root, [])
        if len(records) != len(all_ids):
            raise AssertionError("Số ID không nhất quán")
        return True
~~~

### Vì sao ví dụ này không mất điểm trùng tọa độ?

Khi xây, mỗi điểm được sắp theo \((x,ID)\) hoặc \((y,ID)\); ID phân biệt các bản ghi cùng tọa độ. Tại một nút, chính pivot **không xuất hiện lại** ở hai danh sách con.

Khi báo cáo, một node có thể được thu trọn bởi hàm emit_all **hoặc** được kiểm tra pivot rồi duyệt hai con, không thực hiện cả hai nhánh xử lý trên cùng node. Vì vậy không có một ID nào được đưa ra hai lần chỉ do việc cắt tỉa.

### Vì sao counting nhanh hơn trên vùng bao trọn?

Hàm count_rect gọi cùng quy tắc bbox_outside/bbox_inside như range_rect, nhưng khi Q bao trọn bbox cây con, nó chỉ cộng **node.size** thay vì gọi emit_all. Trên tập điểm có \(n\) bản ghi và Q bao toàn bộ gốc, phép đếm chỉ cần kiểm tra bbox gốc rồi đọc size, trong khi phép liệt kê vẫn phải duyệt/xuất \(n\) bản ghi.

## 13. Python: bộ ví dụ và đối chiếu với quét tham chiếu

Đoạn sau **nối tiếp trực tiếp** lớp RectangleKDTree ở mục 12.

~~~python
records = [
    ("A", 1, 1),
    ("B", 2, 2),
    ("C", 4, 4),
    ("D", 4, 1),
    ("E", 6, 3),
    ("F", 8, 8),
    ("G", 4, 4),  # Trùng tọa độ với C.
    ("H", -2, 3),
    ("I", 0, 0),
]

tree = RectangleKDTree(records, axis_strategy="cyclic")
wide = RectangleKDTree(records, axis_strategy="widest")
assert tree.validate()
assert wide.validate()

def ids(points):
    return [p.id for p in points]


# Hình đóng có nhận cạnh trên/phải.
assert ids(tree.range_rect(1, 1, 4, 4)) == [
    "A", "B", "C", "D", "G"
]
assert tree.count_rect(1, 1, 4, 4) == 5

# Hình nửa mở loại x=4 hoặc y=4.
assert ids(tree.range_rect(1, 1, 4, 4, closed=False)) == [
    "A", "B"
]
assert tree.count_rect(1, 1, 4, 4, closed=False) == 2

# Cửa sổ đóng suy biến vẫn có kết quả.
assert ids(tree.range_rect(4, 1, 4, 4)) == [
    "C", "D", "G"
]
assert ids(tree.range_rect(4, 4, 4, 4)) == ["C", "G"]

# Nửa mở suy biến là miền rỗng.
assert tree.range_rect(4, 1, 4, 4, closed=False) == []
assert tree.count_rect(4, 1, 4, 4, closed=False) == 0

# Tọa độ âm vẫn được xử lý bình thường.
assert ids(tree.range_rect(-3, 0, 0, 4)) == ["H", "I"]

# Đếm toàn miền bằng subtree size.
assert tree.count_rect(-10, -10, 10, 10) == len(records)

# Khi Q không giao dữ liệu, kết quả rỗng.
assert tree.range_rect(100, 100, 200, 200) == []

# Tập rỗng vẫn là một chỉ mục hợp lệ.
empty = RectangleKDTree([])
assert empty.range_rect(0, 0, 1, 1) == []
assert empty.count_rect(0, 0, 1, 1) == 0
assert empty.validate()


def brute_query(records, xmin, ymin, xmax, ymax, closed):
    def eligible(item):
        _, x, y = item
        if closed:
            return xmin <= x <= xmax and ymin <= y <= ymax
        return xmin <= x < xmax and ymin <= y < ymax

    return sorted(item_id for item_id, x, y in records
                  if eligible((item_id, x, y)))


for xmin, ymin, xmax, ymax in [
    (1, 1, 4, 4),
    (4, 1, 4, 4),
    (4, 4, 4, 4),
    (-3, 0, 0, 4),
    (0, 0, 10, 10),
    (5, 0, 7, 5),
    (100, 100, 200, 200),
]:
    for closed in (True, False):
        expected = brute_query(
            records, xmin, ymin, xmax, ymax, closed
        )
        for index in (tree, wide):
            actual = ids(index.range_rect(
                xmin, ymin, xmax, ymax, closed=closed
            ))
            count = index.count_rect(
                xmin, ymin, xmax, ymax, closed=closed
            )
            assert actual == expected
            assert count == len(expected)
~~~

### Điều gì được kiểm chứng?

1. **Nội dung và số lượng khớp nhau:** count_rect trả đúng độ dài kết quả reporting.
2. **Biên đóng/nửa mở không lẫn nhau:** điểm đúng \(x=4\), \(y=4\) xuất hiện hay bị loại đúng quy tắc.
3. **Hộp suy biến:** truy vấn đóng vẫn có thể tìm điểm; nửa mở suy biến trả rỗng.
4. **Tọa độ âm:** không có giả định miền gốc phải bắt đầu từ 0.
5. **ID trùng tọa độ:** C và G được giữ riêng.
6. **Hai chính sách trục:** cyclic và widest phải cho cùng ID kết quả.
7. **Quét tuyến tính độc lập:** dùng predicate đơn giản không phụ thuộc cấu trúc cây để phát hiện lỗi cắt tỉa.

### Giới hạn của mã

Đây là mã minh họa, chưa phải thư viện production:

- Chỉ hỗ trợ **2D** và metric không liên quan tới truy vấn range; mở rộng \(d\) chiều yêu cầu tổng quát hóa vòng lặp trên trục.
- Dùng **sort lại tập con ở mỗi node** nên build không tối ưu.
- Dùng Python float; tọa độ cực lớn, phép hiệu trong spread hoặc các giá trị sát ranh giới có thể cần quy tắc số học chuyên biệt.
- validate dùng phép thu thập cây con và danh sách ràng buộc tổ tiên, ưu tiên rõ ràng hơn tốc độ.
- Không hỗ trợ cập nhật đồng thời, ghi nhật ký giao dịch, thay đổi ID hay cập nhật tọa độ tại chỗ.
- Range reporting sắp ID cuối nên có thêm \(O(k\log k)\) nếu người dùng cần đầu ra theo thứ tự ổn định.

## 14. Cập nhật động: tại sao AABB và subtree size phải thay đổi?

Một cây được xây bằng median thường có chiều cao nhỏ khi tập điểm tĩnh. Nhưng nếu dữ liệu dịch chuyển, chèn hoặc xóa liên tục, ba loại bất biến đều có thể thay đổi:

1. **Phân hoạch:** một điểm sau cập nhật còn thuộc đúng phía của mọi mặt chia tổ tiên không?
2. **AABB:** hộp của node có còn bao tất cả điểm trong cây con không?
3. **Size:** số điểm được lưu trong cây con có còn đúng không?

### Thêm điểm

Với điểm mới \(p\), có thể đi từ gốc bằng khóa \((p_{axis},ID)\) tại mỗi node cho tới nhánh trống. Sau đó:

- Thêm một node mới.
- Tăng **subtree_size** ở tất cả tổ tiên trên đường chèn.
- Mở rộng AABB của mỗi tổ tiên khi cần.

Điều hướng mất \(O(h)\) với h là chiều cao hiện tại; cập nhật bbox hai chiều cũng mất \(O(h)\). Nhưng cây có thể **lệch dần** sau nhiều lần chèn; không thể tiếp tục giả định h luôn \(O(\log n)\).

### Xóa điểm

Xóa trong k-d tree khó hơn xóa BST một chiều vì mỗi node có thể dùng **trục khác**. Có các hướng:

**Lazy deletion:** đánh dấu ID đã xóa; bỏ qua nó khi reporting. Cần bảo đảm range counting không tính bản ghi đã xóa: nếu dùng subtree_size phải duy trì **số bản ghi còn sống**, không phải size từ khi xây.

**Xóa có tái tổ chức:** thay node bị xóa bằng một điểm phù hợp từ cây con, bảo toàn các ràng buộc của trục chia tại các mức liên quan. Cần cẩn thận khi có tọa độ bằng nhau và tie-break ID.

**Rebuild cây con:** thu thập các bản ghi còn sống, xây median tree mới, tính lại AABB và size. Chi phí có thể cao hơn một phép thay node, nhưng dễ kiểm chứng tính đúng.

### Di chuyển điểm

Giả sử ID P trước ở \((2,2)\), sau đổi thành \((50,50)\), nhưng node vẫn nằm ở nhánh chịu ràng buộc \(x<10\). Nếu chỉ sửa tọa độ:

- Cấu trúc **vi phạm phân hoạch**.
- AABB cũ có thể không bao điểm mới.
- Một truy vấn quanh \((50,50)\) có thể bỏ nhánh đang chứa P và **không tìm thấy P**.

Với k-d tree động, cách rõ ràng là xem move như **xóa vị trí cũ rồi chèn vị trí mới**, hoặc dựng lại cây con liên quan. Cả hai cần cập nhật bbox/size đúng.

### Rebuild theo phiên bản

Trong hệ thống có nhiều truy vấn chạy đồng thời, có thể:

1. Giữ một phiên bản cây tĩnh đang phục vụ truy vấn.
2. Thu thập thay đổi trong một cấu trúc phụ (*delta/overlay*).
3. Khi xây xong cây mới, thay phiên bản một cách nhất quán.
4. Hợp nhất kết quả cây cũ và delta, xử lý ID đã bị xóa/chuyển.

Nếu chỉ tra cây cũ mà bỏ delta, truy vấn sẽ thiếu điểm vừa thêm. Nếu vẫn trả điểm cũ đã di chuyển, truy vấn có thể chứa bản ghi đã lỗi thời. Thiết kế phiên bản cần định nghĩa rõ thời điểm nhìn thấy cập nhật và cách **dedup/tombstone**.

## 15. Tối ưu reporting/counting có trách nhiệm

Ba trường hợp **ngoài / nhận trọn / giao một phần** là khung căn bản. Có thể bổ sung tối ưu tùy workload, nhưng không nên đánh đổi tính đúng.

### 15.1. Trả kết quả không sắp nếu API cho phép

Trong ví dụ Python, việc sắp theo ID giúp kiểm thử và đầu ra ổn định. Nếu giao diện chỉ cần một tập điểm, không cần thứ tự, có thể phát kết quả theo thứ tự duyệt cây:

\[
T_{\mathrm{report}}=O(V_Q+k)
\]

trong 2D cố định. Nếu sắp:

\[
T_{\mathrm{report}}=O(V_Q+k\log k+k).
\]

Để phân trang theo ID hoặc theo khoảng cách, chỉ đọc một số lượng tùy ý rồi dừng **không tương đương** truy vấn top-k có thứ tự. Phải tổ chức thêm chỉ mục/thủ tục chọn nếu yêu cầu kết quả có thứ tự toàn cục.

### 15.2. Chỉ đếm, không materialize danh sách

Với các truy vấn thống kê như “có bao nhiêu cảm biến trong khu vực?”, việc tạo một danh sách hàng triệu điểm chỉ để lấy độ dài là công việc thừa. Hãy sử dụng subtree_size khi AABB được chứa trọn.

Tuy nhiên, nếu đang áp dụng thêm bộ lọc **không gian kết hợp thuộc tính** (ví dụ chỉ đếm cảm biến đang hoạt động), subtree_size tổng quát không còn đủ. Cần metadata theo thuộc tính hoặc vẫn kiểm tra từng bản ghi.

### 15.3. Dừng khi chỉ muốn biết có tồn tại hay không

Truy vấn **existence** hỏi “Q có chứa ít nhất một điểm không?”. Khi tìm được một pivot thuộc Q hoặc một cây con có bbox được Q chứa trọn và size dương, có thể trả **True ngay**.

Không cần xuất toàn bộ \(k\) điểm. Tuy nhiên, trong trường hợp không tồn tại điểm nào, vẫn có thể phải kiểm tra nhiều node để chứng minh **False**.

### 15.4. Bulk build và cache locality

Nếu dữ liệu tĩnh, xây cây theo lô từ mảng các điểm có thể hiệu quả hơn chèn từng điểm. Cũng có thể lưu node trong **mảng liên tiếp** thay vì cấp phát một object rời rạc ở mỗi node, nhằm cải thiện locality của CPU cache.

Việc chọn cấu trúc lưu trữ không thay đổi bất biến toán học. Nó ảnh hưởng hằng số thời gian, bộ nhớ cấp phát, serialization và khả năng chạy ngoài bộ nhớ.

### 15.5. AABB chặt và cách duy trì

AABB tính đúng min/max của tất cả điểm là **chặt theo từng trục**. Một AABB được cố tình nới rộng vẫn cho phép prune an toàn nếu nó luôn bao đủ điểm, nhưng có thể giảm hiệu quả vì nhiều vùng có vẻ giao Q hơn thực tế.

**AABB quá nhỏ mới là nguy hiểm:** nếu một điểm nằm ngoài bbox, phép loại nhánh có thể trở thành false negative.

### 15.6. Query plan khi vùng quá rộng

Nếu Q bao hầu hết dữ liệu và yêu cầu xuất tất cả điểm, quét tuyến tính qua một mảng liên tiếp có thể nhanh hơn việc duyệt node/cấp phát đối tượng cây. Thử **fast path** hoặc lựa chọn kế hoạch truy vấn theo độ chọn lọc có thể hợp lý.

Không nên quyết định hiệu năng chỉ từ \(O(\sqrt n+k)\) hay \(O(V_Q+k)\); phải đo **thời gian thực, chi phí I/O, cache miss và số kết quả**.

## 16. Phạm vi áp dụng: cửa sổ song song trục, 3D và dữ liệu địa lý

### 16.1. Vì sao gọi là truy vấn orthogonal?

Cạnh của hình chữ nhật Q **song song với trục tọa độ**. Kiểm tra một điểm chỉ cần bốn so sánh:

\[
x_{\min}\le x\le x_{\max},
\qquad y_{\min}\le y\le y_{\max}.
\]

Vùng có thể bị xoay một góc \(\theta\), hoặc là một đa giác bất kỳ, **không còn là** orthogonal rectangle query trong cùng hệ trục.

### 16.2. Hình chữ nhật xoay

Một hướng xử lý:

1. Tính **AABB bao hình xoay**.
2. Dùng k-d tree để lấy các điểm ứng viên trong AABB.
3. Kiểm tra hình học thật để xác định điểm có thuộc hình chữ nhật xoay hay không.

Các điểm nằm trong AABB nhưng nằm ngoài hình xoay là **false positive của bước lọc**, không được trả như kết quả thật.

Không thể bỏ bước kiểm tra hình học cuối nếu kết quả phải đúng theo hình xoay.

### 16.3. Truy vấn trong 3D

Một hộp 3D:

\[
Q=[x_0,x_1]\times[y_0,y_1]\times[z_0,z_1]
\]

được xử lý bằng cùng nguyên tắc: trên **mỗi trục**, kiểm tra min/max của node so với Q; nếu có ít nhất một trục không giao, bỏ nhánh. Nếu Q chứa bbox trên **tất cả** các trục, có thể xuất hoặc đếm toàn bộ cây con.

Ở \(d\) chiều:

\[
\boxed{
B\cap Q\ne\varnothing
\iff
\forall i,\ B.lo_i\le Q.hi_i\land Q.lo_i\le B.hi_i.
}
\]

Chi phí mỗi phép giao là \(O(d)\); bộ nhớ bbox của node là \(O(d)\).

### 16.4. Kinh độ/vĩ độ

Kinh độ và vĩ độ là **độ góc**, không phải đơn vị khoảng cách phẳng theo mét. K-d tree có thể tổ chức điểm theo cặp (kinh độ, vĩ độ) để lọc sơ bộ một hình chữ nhật độ, nhưng:

- Một độ kinh độ biểu diễn quãng đường khác nhau theo vĩ độ.
- Vùng băng qua kinh tuyến đổi ngày \(+180^\circ/-180^\circ\) không thể luôn biểu diễn bằng một khoảng kinh độ thông thường \([min,max]\); có thể cần chia thành hai cửa sổ.
- Phải thống nhất **CRS** (hệ quy chiếu tọa độ) và thứ tự trục \((longitude,latitude)\) hoặc \((latitude,longitude)\).
- Nếu yêu cầu bán kính/NN theo mét, phải dùng metric địa lý hoặc phép chiếu thích hợp; công thức Euclid trên độ không tự cho mét.

### 16.5. Truy vấn hỗn hợp không gian và thuộc tính

Câu hỏi “địa điểm trong Q và loại = bệnh viện” có thêm một predicate không gian **và** một predicate thuộc tính. Có thể:

- Dùng k-d tree lọc theo Q rồi kiểm tra thuộc tính.
- Có một chỉ mục phụ theo loại và giao các tập ID.
- Lưu metadata phân loại theo cây con nếu workload đáng chi phí bộ nhớ.

Không được dùng subtree_size tổng để trả số bệnh viện trong Q nếu metadata không phân biệt loại.

## 17. Kiểm thử tính đúng: ranh giới và đối chiếu độc lập

Một số lỗi range query chỉ xuất hiện tại các trường hợp hiếm:

- Điểm nằm đúng trên cạnh trái, phải, dưới hoặc trên.
- Hai điểm cùng tọa độ nhưng khác ID.
- Cửa sổ đóng có chiều rộng hoặc chiều cao bằng 0.
- Cửa sổ nửa mở suy biến.
- Điểm có tọa độ âm.
- AABB cây con chỉ còn một điểm \([x,x]\times[y,y]\).
- Q chứa trọn bbox của một nhánh lớn.
- Q không giao bất kỳ điểm nào.
- Nhiều điểm có cùng tọa độ của mặt chia.
- K-d tree chọn trục khác nhau nhưng vẫn phải trả cùng một tập ID.

### Bảng kiểm thử ranh giới

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Q đóng chạm điểm ở cận phải | Phải trả điểm |
| Q nửa mở chạm điểm ở cận phải | Phải loại điểm |
| Q đóng suy biến thành một điểm | Có thể trả nhiều ID cùng tọa độ |
| Q nửa mở suy biến | Rỗng |
| bbox suy biến tại đúng cận trái Q nửa mở | **Có thể giao**, không được prune sai |
| bbox bắt đầu đúng cận phải Q nửa mở | **Ngoài Q**, có thể prune |
| Q bao bbox node | Reporting xuất toàn bộ; counting cộng size |
| Q không giao bbox node | Không duyệt hậu duệ |
| Q có nhiều kết quả hơn một bucket | Không bỏ sót do chỉ kiểm tra pivot |

### Property-based test

Một cách kiểm tra mạnh là sinh ngẫu nhiên nhiều tập điểm, nhiều cửa sổ Q và nhiều cấu trúc cây:

~~~text
for each random dataset P:
    build KDTree(P, axis=cyclic)
    build KDTree(P, axis=widest)

    for each window Q:
        expected = brute_force(P,Q)
        assert KDTree_cyclic.range(Q) == expected
        assert KDTree_widest.range(Q) == expected
        assert KDTree_cyclic.count(Q) == len(expected)
        assert KDTree_widest.count(Q) == len(expected)
~~~

Với dữ liệu ngẫu nhiên thuần túy, xác suất tạo đúng một điểm \(x=x_{\max}\) có thể thấp. Vì vậy **phải thêm trường hợp biên được chọn có chủ đích**, không chỉ dựa vào random.

### Một phép thử bất biến trực tiếp

Với mỗi node:

1. Thu toàn bộ điểm từ pivot và hai con.
2. Kiểm tra **subtree_size** đúng bằng số bản ghi thu được.
3. Kiểm tra min/max của các điểm đúng bằng **bbox_lo/bbox_hi**.
4. Kiểm tra mọi điểm ở nhánh trái/phải thỏa khóa phân hoạch của mỗi tổ tiên.
5. Kiểm tra không ID nào xuất hiện quá một lần.

Đây là kiểm tra thường **đắt hơn truy vấn thông thường**, nhưng hữu ích cho môi trường phát triển và phát hiện lỗi dữ liệu/cập nhật trước khi chạy benchmark.

## 18. Benchmark: đo số node thăm, không chỉ độ cao cây

Với cùng bộ dữ liệu và cùng cửa sổ Q, so sánh ba phương pháp:

1. **Quét tuyến tính** toàn bộ điểm.
2. **K-d tree chỉ prune khi bbox không giao Q**.
3. **K-d tree có thêm nhận trọn bbox và subtree_size**.

### Chỉ số nên thu

| Chỉ số | Vai trò |
| --- | --- |
| \(n\) | Số điểm trong dữ liệu |
| \(h\) | Chiều cao cây |
| \(V_Q\) | Số node phải kiểm tra bbox |
| Số node bị prune | Hiệu quả loại cây con |
| Số cây con nhận trọn | Hiệu quả tối ưu reporting/counting |
| Số pivot phải kiểm tra predicate | Lượng lọc chính xác |
| \(k\) | Số bản ghi kết quả |
| Thời gian build | Chi phí xây chỉ mục trước khi truy vấn |
| Thời gian p50/p95/p99 | Phân bố độ trễ của các cửa sổ |
| Bộ nhớ | Node, bbox, size, kết quả trung gian |

### Dữ liệu thử có ý nghĩa

**Phân bố đều:** kiểm tra hiệu quả trên tập điểm trải đều.

**Phân bố theo cụm:** nhiều điểm gần nhau và vùng rỗng lớn.

**Điểm nằm trên đường:** ví dụ mọi \(y=3\); dễ phát hiện trường hợp chia theo một trục ít thông tin.

**Trùng tọa độ:** nhiều ID tại \((4,4)\); thử điểm trên cạnh Q và mặt chia.

**Truy vấn chọn lọc thấp:** Q gần như phủ mọi điểm; chi phí xuất \(k\) có thể chi phối.

**Truy vấn chọn lọc cao:** Q rất nhỏ, kỳ vọng nhiều nhánh bị prune.

### Ý nghĩa thực tế

Hai cây cùng \(n\) và cùng chiều cao vẫn có thể khác lớn về \(V_Q\): trục chia, phân bố và độ chặt AABB quyết định nhánh nào giao Q.

Ngược lại, việc thêm metadata bbox/size không miễn phí: tăng bộ nhớ, thời gian build và chi phí cập nhật. Nếu n nhỏ, quét một mảng điểm liên tiếp có thể rẻ hơn duyệt cây. **Chọn theo workload được đo**, không theo giả định rằng “có cây là phải nhanh hơn”.

## 19. Các sai lầm phổ biến cần tránh

1. **“Cây k-d chỉ cần kiểm tra một trục để biết điểm thuộc hình chữ nhật.”** Sai. Điểm phải thỏa điều kiện **cả x và y**.
2. **“K-d tree là BST của tọa độ x.”** Sai. Trục chia có thể luân phiên hoặc được chọn theo dữ liệu; mỗi mức có thể dùng trục khác.
3. **“Mọi điểm trái pivot có x nhỏ hơn pivot.”** Sai nếu node chia theo y; ngay cả khi chia theo x, tie-break ID có thể đưa điểm cùng x sang trái.
4. **“Bbox cây con chỉ cần lấy tọa độ của pivot.”** Sai. Phải bao **pivot và toàn bộ hậu duệ**.
5. **“Bbox của một nút chứa đúng một điểm là hộp rỗng.”** Sai. Hộp đóng \([x,x]\times[y,y]\) chứa chính điểm đó.
6. **“Hộp đóng chạm cạnh thì không giao.”** Sai. Giao có thể là một đoạn hoặc một điểm.
7. **“Bbox không giao Q vẫn có thể có điểm hợp lệ.”** Không thể nếu bbox bao đủ các điểm và điều kiện biên được thực hiện đúng.
8. **“Bbox giao Q nghĩa là mọi điểm trong nhánh thuộc Q.”** Sai. Có thể phải kiểm tra pivot và các nhánh con.
9. **“Chỉ cần đi một phía của split plane trong mọi trường hợp.”** Sai. Q cắt mặt chia thường yêu cầu xét cả hai phía.
10. **“Khi \(q_{\min}=s\), có thể luôn bỏ nhánh trái.”** Sai nếu tie-break theo ID cho phép điểm có tọa độ s ở bên trái và cửa sổ **đóng** nhận s.
11. **“Có thể dùng dấu \(<\) khi so giao hai hộp đóng.”** Sai tại các ranh giới. Với hộp đóng, hai khoảng chạm tại một điểm vẫn giao.
12. **“Hộp truy vấn nửa mở và hộp bao dữ liệu nửa mở có cùng điều kiện giao.”** Sai. AABB min/max của các điểm là **đóng**, nên điều kiện cắt tỉa có dấu nghiêm ngặt khác ở hai phía.
13. **“Một Q đóng có chiều rộng 0 là rỗng.”** Sai. Nó có thể chứa các điểm trên một đường thẳng.
14. **“Q nửa mở có \(a=b\) vẫn chứa điểm đúng tọa độ a.”** Sai. \([a,a)\) là rỗng.
15. **“Điểm trùng tọa độ nên chỉ đếm một lần.”** Sai khi có nhiều ID đại diện các bản ghi khác nhau.
16. **“Để reporting nhanh, chỉ cần cộng subtree_size.”** Sai. Reporting phải xuất các bản ghi; subtree_size chỉ là **số lượng**.
17. **“Range counting luôn bằng độ dài danh sách reporting dù size lỗi thời.”** Sai. Cần cập nhật metadata khi chèn/xóa.
18. **“Q bao bbox thì luôn có thể cộng size cho câu hỏi đếm theo thuộc tính.”** Sai nếu size không phân biệt điều kiện thuộc tính.
19. **“Sắp kết quả theo ID miễn phí.”** Sai. Có thể thêm \(O(k\log k)\).
20. **“Median split bảo đảm mọi range query \(O(\log n)\).”** Sai. Vùng truy vấn có thể giao nhiều cây con; chi phí xuất k điểm ít nhất \(\Omega(k)\).
21. **“Cắt tỉa theo AABB cho kết quả gần đúng.”** Không, nếu AABB hợp lệ và predicate chính xác, nó là **cắt tỉa an toàn cho kết quả chính xác**.
22. **“Sau move có thể giữ nguyên mọi bbox.”** Sai nếu điểm ra ngoài bbox cũ; có thể gây false negative.
23. **“Cập nhật tombstone không ảnh hưởng counting.”** Sai. Số bản ghi còn sống đã thay đổi.
24. **“Đổi trục chia của node mà không tổ chức lại cây con cũng đúng.”** Sai: bất biến phân hoạch có thể không còn đúng.
25. **“Dữ liệu địa lý dùng kinh/vĩ độ thì hình chữ nhật tọa độ cũng chính là hình tròn theo mét.”** Sai. Query cửa sổ độ và query bán kính mét là hai bài toán khác nhau.
26. **“Vùng quay 45° có thể dùng AABB và trả toàn bộ điểm của AABB.”** Sai. Bước AABB chỉ lọc ứng viên, cần kiểm tra hình xoay thật.
27. **“Nếu chọn cyclic và widest spread, hai cây được phép cho hai kết quả range khác nhau.”** Sai nếu cả hai đúng, dùng cùng dữ liệu và cùng predicate.
28. **“Random test đã đủ để kiểm tra dấu bằng ranh giới.”** Sai. Cần chủ động thêm dữ liệu nằm đúng các cận và mặt chia.

## 20. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Xác định điểm thuộc miền đóng

Cho \(Q=[1,4]\times[1,4]\) và các điểm A=(1,1), B=(2,2), C=(4,4), D=(4,1), E=(6,3). Hãy liệt kê ID thuộc Q.

**Lời giải:** A, B nằm trong Q; C ở góc trên phải và D ở cạnh phải vẫn thuộc Q. E có x=6 ngoài cận phải. Kết quả là **A, B, C, D**.

### Câu 2. Thay miền đóng bằng nửa mở

Vẫn tập ở câu 1, nhưng Q đổi thành \([1,4)\times[1,4)\). Những điểm nào được nhận?

**Lời giải:** Chỉ **A, B**. C và D có x=4, bằng cận phải bị loại. E ở ngoài như trước.

### Câu 3. Cửa sổ đóng suy biến

Q=\([4,4]\times[1,4]\). Các điểm C=(4,4), D=(4,1), G=(4,4) nhưng khác ID, và B=(2,2). Q có rỗng không, kết quả là gì?

**Lời giải:** Q là một **đoạn thẳng đứng** và không rỗng. Trả **C, D, G**; B không có x=4.

### Câu 4. Miền nửa mở suy biến

Q=\([4,4)\times[1,4)\). Có điểm \((4,2)\) nào thuộc Q không?

**Lời giải:** **Không.** Khoảng \([4,4)\) là tập rỗng; tích Descartes của nó với khoảng y cũng rỗng.

### Câu 5. Giao của hai hộp đóng

Cho \(A=[0,4]\times[0,4]\), \(B=[4,7]\times[2,6]\). Chúng có giao không?

**Lời giải:** Có. Giao là \(\{4\}\times[2,4]\), một đoạn trên đường \(x=4\). Hai hộp đóng giao nhau dù chỉ chạm cạnh.

### Câu 6. Cắt tỉa một bbox ngoài Q

Q=\([0,5]\times[0,5]\); bbox cây con là \(B=[6,9]\times[1,4]\). Có thể loại toàn bộ cây con không?

**Lời giải:** **Có**. Trục x tách rời: \(B.lo_x=6>Q.hi_x=5\). Mọi điểm trong cây con nằm trong B nên không điểm nào thuộc Q.

### Câu 7. Q chứa trọn bbox

Một node có bbox \([2,4]\times[1,3]\) và subtree_size=120. Q=\([0,5]\times[0,5]\). Nếu hỏi số điểm trong Q, có thể trả bao nhiêu mà không đi xuống con?

**Lời giải:** **120 điểm**, vì Q chứa toàn bộ bbox. Nếu hỏi liệt kê, vẫn phải lấy ra đầy đủ 120 bản ghi thay vì chỉ trả số 120.

### Câu 8. Bbox giao một phần Q

Q=\([0,5]\times[0,5]\), bbox \([4,8]\times[1,3]\). Có được lấy ngay subtree_size làm kết quả đếm không?

**Lời giải:** **Không.** Bbox giao Q, nhưng phần có x>5 nằm ngoài Q. Phải kiểm tra pivot và các cây con; chỉ được cộng size ở những nhánh được Q chứa trọn.

### Câu 9. Tại sao không prune khi query chạm mặt chia?

Một node chia theo x tại \(s=4\), khóa phân hoạch \((x,ID)\). Truy vấn Q có miền x là \([4,7]\). Có thể tự loại toàn bộ nhánh trái không?

**Lời giải:** **Không.** Một điểm bên trái có thể có x=4 nhưng ID nhỏ hơn ID của pivot. Q đóng nhận x=4, nên điểm ấy có thể hợp lệ. Chỉ từ điều kiện mặt chia, phải xử lý cả hai nhánh có thể chứa điểm bằng s.

### Câu 10. Khi nào bỏ nhánh phải?

Node chia x ở s=4, tất cả điểm trong nhánh phải có x≥4. Truy vấn có x thuộc \([-1,3]\). Có thể bỏ nhánh phải không?

**Lời giải:** **Có**, vì \(q_{\max}=3<4=s\). Không điểm nào trong nhánh phải có x≤3.

### Câu 11. AABB một điểm và Q nửa mở

Một lá chỉ có điểm P=(4,4), bbox là \([4,4]\times[4,4]\). Q nửa mở là \([4,6)\times[4,6)\). Có thể prune vì bbox có chiều rộng 0 không?

**Lời giải:** **Không.** P thuộc Q do x=y=4 là cận **dưới bao gồm**. Bbox đóng suy biến vẫn chứa P, và điều kiện giao đúng phải giữ nhánh này.

### Câu 12. Bbox bắt đầu tại cận phải nửa mở

Một bbox có miền x là \([6,9]\); Q nửa mở theo x là \([0,6)\). Có thể prune theo trục x không?

**Lời giải:** **Có**. Mọi điểm trong bbox có x≥6, trong khi Q đòi x<6. Điều kiện ngoài là \(B.lo_x\ge Q.hi_x\), bao gồm dấu bằng.

### Câu 13. Điều kiện Q nửa mở chứa trọn bbox

Q nửa mở \([0,6)\times[0,6)\), bbox \([2,6]\times[2,4]\). Có được nhận trọn cây con không?

**Lời giải:** **Không.** Bbox có max x=6, nghĩa là có thể có điểm tại x=6, bị Q loại. Muốn nhận trọn, phải có \(B.hi_x<6\) và cận tương ứng trên trục y cũng thỏa điều kiện.

### Câu 14. Hai ID cùng tọa độ

Các bản ghi C và G cùng ở \((4,4)\), nhưng ID khác. Truy vấn đóng chỉ có điểm \((4,4)\). Kết quả reporting và counting là gì?

**Lời giải:** Reporting trả **C, G**; counting trả **2**. Tọa độ không phải khóa định danh duy nhất của bản ghi.

### Câu 15. Chi phí xuất kết quả

Một truy vấn trên cây k-d có thể xác định ngay Q chứa bbox gốc có n=1.000.000 điểm. Chi phí counting và reporting khác nhau thế nào?

**Lời giải:** Counting có thể trả ngay \(subtree\_size(root)\) sau \(O(1)\) phép so sánh trong 2D. Reporting phải **xuất cả triệu bản ghi**, nên cần ít nhất \(\Omega(10^6)\) thao tác đầu ra. Nếu sắp ID còn có chi phí sắp.

### Câu 16. Kiểm tra subtree_size

Một node có pivot, cây trái chứa 7 điểm, cây phải 12 điểm. subtree_size của node phải bằng bao nhiêu?

**Lời giải:**

\[
size=1+7+12=\boxed{20}.
\]

Nếu size lưu 19, range counting có thể sai khi Q chứa trọn bbox node.

### Câu 17. Cập nhật metadata sau khi xóa

Một node có size=100 và toàn bộ bbox nằm trong Q. Xóa một điểm trong cây con nhưng không sửa size. Range counting trả gì và sai ở đâu?

**Lời giải:** Nó vẫn có thể trả **100** dù số điểm sống chỉ còn **99**. Vì vậy phải cập nhật size theo việc xóa/tombstone hoặc xây lại chỉ mục.

### Câu 18. Tọa độ di chuyển ra ngoài bbox

Một điểm ban đầu ở \((2,2)\), sau chuyển tới \((20,20)\), nhưng bbox của nhánh vẫn là \([0,5]\times[0,5]\). Truy vấn Q quanh \((20,20)\) sẽ gặp nguy cơ gì?

**Lời giải:** Bbox cũ không giao Q, khiến nhánh bị **prune sai** và điểm mới bị bỏ sót. Đây là **false negative**, nghiêm trọng hơn việc chỉ duyệt thừa.

### Câu 19. Range counting có bộ lọc thuộc tính

Node có size=100, bbox nằm trong Q, nhưng chỉ 20 điểm có thuộc tính active=True. Nếu câu hỏi là “đếm điểm active trong Q”, có thể cộng size=100 không?

**Lời giải:** **Không.** Size không mã hóa thuộc tính active. Cần thêm metadata đếm active theo cây con hoặc kiểm tra từng bản ghi để biết chính xác số 20.

### Câu 20. Chi phí truy vấn theo số node

Một phép range query thăm 50 node, trả k=100 điểm và không cần sắp. Trong 2D, biểu thức tổng quát của thời gian là gì?

**Lời giải:** Với mỗi node có chi phí kiểm tra AABB hằng số và mỗi kết quả xuất một lần, chi phí là \(O(V_Q+k)=O(50+100)\). Không nên nói \(O(\log n)\) chỉ vì cây có chiều cao log n.

### Câu 21. Hộp 3D

Cho Q=\([0,5]\times[0,5]\times[0,5]\) và bbox cây con B=\([1,4]\times[1,4]\times[6,8]\). Có thể prune B không?

**Lời giải:** **Có.** Tuy x/y giao Q, trục z hoàn toàn tách rời vì \(B.lo_z=6>Q.hi_z=5\). Chỉ cần **một trục** tách rời là đủ để bỏ toàn nhánh.

### Câu 22. Hai chiến lược trục

Một k-d tree dùng trục cyclic, một cây khác dùng widest spread, cả hai dựng từ cùng tập điểm. Có được trả hai tập ID khác nhau cho cùng Q đóng không?

**Lời giải:** **Không**, nếu hai cây đúng và dùng cùng predicate. Chúng có thể khác số node thăm, thời gian và bộ nhớ xây, nhưng **tập kết quả phải giống nhau**.

### Câu 23. Cửa sổ xoay

Một hình chữ nhật xoay 30° có AABB giao rất nhiều điểm. Có thể coi tất cả điểm bên trong AABB đều thuộc hình chữ nhật xoay không?

**Lời giải:** **Không.** AABB chỉ tạo **ứng viên**; cần kiểm tra điểm có thật sự nằm trong hình xoay. Trả toàn bộ ứng viên sẽ có false positive.

### Câu 24. Chọn phương án khi Q rất lớn

Q bao gần như mọi điểm, một k-d tree có rất nhiều node cấp phát rời rạc, còn các điểm gốc nằm trong một mảng liên tiếp. Có thể phương án quét tuyến tính nhanh hơn không?

**Lời giải:** **Có.** Khi gần hết dữ liệu đều được trả, lợi ích prune nhỏ và chi phí duyệt con trỏ/cache miss có thể cao hơn duyệt mảng tuần tự. Cần benchmark, không chỉ nhìn độ phức tạp tiệm cận.

## 21. Tổng kết

Truy vấn miền chữ nhật (*orthogonal range query*) trên k-d tree cần ba thao tác chính với **AABB cây con**:

1. **Ngoài:** bbox không giao Q → bỏ nguyên cây con.
2. **Trong trọn:** Q chứa bbox → reporting xuất mọi ID trong cây con; counting cộng **subtree_size**.
3. **Giao một phần:** kiểm tra pivot và đệ quy hai cây con.

Với hộp truy vấn **đóng**, một điểm nằm đúng cạnh phải/trên vẫn được trả. Với hộp **nửa mở**, biên trái/dưới được nhận nhưng biên phải/trên bị loại. AABB tính từ min/max của **các điểm** là hộp **đóng**, nên phép prune với Q nửa mở phải dùng điều kiện bất đẳng thức phù hợp; không được trộn lẫn quy ước.

Cắt tỉa dựa vào **mặt chia** cũng hợp lệ, nhưng nếu xây cây với khóa \((tọa độ,ID)\), hai phía có thể cùng chứa điểm có tọa độ đúng bằng giá trị chia. Vì vậy, khi một cửa sổ đóng chạm mặt chia, phải kiểm tra cả nhánh có khả năng chứa điểm trên mặt ấy.

Khi xây bằng median, chiều cao của cây có thể được giữ \(O(\log n)\), nhưng **truy vấn không tự được bảo đảm \(O(\log n)\)**. Chi phí thực phụ thuộc số node thăm \(V_Q\), số kết quả \(k\), độ chặt AABB và quy tắc đầu ra. Counting có thể nhanh hơn reporting nhờ **subtree_size**, còn reporting luôn cần ít nhất \(\Omega(k)\) thao tác.

**Quy trình áp dụng:** xác định quy ước biên → xây k-d tree với ID duy nhất và AABB/size chính xác → triển khai ngoài/trong trọn/giao một phần → đối chiếu cùng tập dữ liệu bằng quét tuyến tính, đặc biệt ở biên và tọa độ trùng → đo số node thăm, độ trễ, bộ nhớ và tỷ lệ cập nhật. Một chỉ mục tốt phải **vừa không bỏ sót kết quả, vừa giảm công việc thực tế** so với phương án đơn giản.
