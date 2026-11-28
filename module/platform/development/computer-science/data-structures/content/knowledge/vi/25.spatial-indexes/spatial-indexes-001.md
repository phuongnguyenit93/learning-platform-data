# Điểm, hộp bao và truy vấn trên dữ liệu nhiều chiều

Một bảng băm có thể trả lời nhanh câu hỏi “bản ghi có ID 42 nằm ở đâu?”, nhưng không trực tiếp giải quyết các câu hỏi như **“những điểm nào nằm trong vùng này?”**, **“những hình nào cắt qua cửa sổ bản đồ?”** hoặc **“vị trí nào gần điểm truy vấn nhất?”**. Các câu hỏi ấy dựa trên **quan hệ hình học**, chứ không đơn thuần dựa trên tính bằng nhau của khóa.

Trong chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, ta sẽ xây dựng nền tảng từ **điểm**, **hộp bao theo trục tọa độ** và **truy vấn trên dữ liệu nhiều chiều**. Bài tập trung vào bất biến hình học, thuật toán kiểm tra chính xác, cách tổ chức chỉ mục và đánh đổi về **thời gian, bộ nhớ, cập nhật**. Đây là cơ sở để hiểu các cấu trúc như **k-d tree**, **quadtree**, **R-tree** và **lưới không gian** ở những bài tiếp theo.

> **Ý chính:** Hộp bao giúp **loại nhanh** nhiều đối tượng chắc chắn không liên quan, nhưng một hộp bao giao với vùng truy vấn **không luôn chứng minh** hình học gốc giao vùng đó. Chỉ mục tốt phải giữ đúng hai bước: **tìm ứng viên không bỏ sót** và **kiểm tra chính xác khi cần**.

## 1. Vì sao dữ liệu nhiều chiều cần cách tra cứu khác?

Đối với dữ liệu một chiều, ta có thể sắp xếp các số theo một trục:

\[
2<5<9<13.
\]

Một truy vấn khoảng \([4,10]\) chỉ cần lấy các phần tử ở đoạn tương ứng, có thể dùng tìm kiếm nhị phân trên mảng đã sắp.

Nhưng điểm hai chiều \(p=(x,y)\) có **hai tọa độ độc lập**. Giả sử:

\[
p=(2,8),\qquad q=(5,3).
\]

Ta có \(p_x<q_x\) nhưng \(p_y>q_y\). Không có một quan hệ nhỏ–lớn tự nhiên duy nhất vừa phản ánh mọi câu hỏi theo \(x\), theo \(y\), theo khoảng cách và theo vùng không gian.

Sắp các điểm **chỉ theo tọa độ \(x\)** có thể tăng tốc điều kiện \(a\le x\le b\), nhưng **không tự xử lý** điều kiện đồng thời \(c\le y\le d\). Càng nhiều chiều, ta càng cần cách tổ chức dữ liệu có thể loại bỏ **cả nhóm điểm** nhờ thông tin hình học.

### Các ứng dụng điển hình

- **Bản đồ:** tìm địa điểm nằm trong khung nhìn hoặc gần vị trí truy vấn.
- **Game/robot:** tìm đối tượng trong vùng quan sát, phát hiện ứng viên va chạm.
- **Đồ họa máy tính:** loại vật thể nằm ngoài vùng camera trước khi tính giao hình học chi tiết.
- **Cảm biến và IoT:** lọc điểm theo kinh độ, vĩ độ, thời gian hoặc độ cao.
- **Dữ liệu khoa học:** tìm các mẫu thỏa đồng thời nhiều ngưỡng thuộc tính.
- **Kho vận:** tìm kho nằm trong vùng phục vụ, hoặc kho gần điểm giao hàng nhất.

Một điểm quan trọng là “nhiều chiều” không nhất thiết chỉ có không gian vật lý. Đối với một số hệ thống, vector \((x,y,t)\) mô tả **vị trí và thời gian**. Tuy nhiên, khi kết hợp các đại lượng khác đơn vị, **khái niệm khoảng cách** phải được định nghĩa cẩn thận.

## 2. Điểm trong không gian \(d\) chiều

Một **điểm** (*point*) trong không gian Euclid \(d\) chiều được biểu diễn bằng vector:

\[
\boxed{p=(p_1,p_2,\ldots,p_d)\in\mathbb R^d.}
\]

| Số chiều | Biểu diễn | Ví dụ |
| --- | --- | --- |
| 1 | \((x)\) | Nhiệt độ hoặc một vị trí trên trục |
| 2 | \((x,y)\) | Vị trí trên mặt phẳng |
| 3 | \((x,y,z)\) | Vị trí trong không gian ba chiều |
| \(d\) | \((p_1,\ldots,p_d)\) | Vector đặc trưng hoặc tọa độ nhiều chiều |

Trong một tập điểm, **tọa độ không nhất thiết là định danh duy nhất**. Hai bản ghi khác nhau có thể cùng vị trí:

~~~text
ID 101 -> point (3, 5), tên "Cửa hàng A"
ID 205 -> point (3, 5), tên "Cửa hàng B"
~~~

Nếu cần giữ hai bản ghi, không thể tự động gộp chúng chỉ vì tọa độ bằng nhau. Chỉ mục có thể tổ chức theo vị trí, nhưng **ID bản ghi** vẫn được bảo toàn.

### Độ chính xác và hệ tọa độ

Mọi công thức hình học trong các mục đầu giả định các tọa độ đã được đưa về **một hệ tọa độ phẳng nhất quán**, và các chiều có ý nghĩa so sánh phù hợp.

Ví dụ:

- Tọa độ tính bằng **mét** trong một hệ phẳng cục bộ: dùng khoảng cách Euclid có thể hợp lý.
- Vĩ độ/kinh độ **theo độ** trên Trái Đất: không nên áp dụng trực tiếp công thức khoảng cách Euclid trên hai số độ để lấy **khoảng cách thực theo mét**.
- Vector gồm **nhiệt độ** và **doanh thu**: cần chuẩn hóa và định nghĩa metric theo ngữ cảnh trước khi dùng k-nearest neighbors.

**Không được suy ra đơn vị khoảng cách từ kiểu dữ liệu float.** Cùng một cặp số có thể biểu diễn các đại lượng rất khác nhau.

## 3. Hộp bao song song trục tọa độ: AABB

**Hộp bao song song các trục** (*axis-aligned bounding box*, **AABB**) trong \(d\) chiều được xác định bằng hai vector:

\[
\mathbf{lo}=(l_1,\ldots,l_d),\qquad
\mathbf{hi}=(u_1,\ldots,u_d),
\]

với bất biến:

\[
\boxed{l_i\le u_i\quad\forall i\in\{1,\ldots,d\}.}
\]

Nếu dùng **biên đóng** ở cả hai phía, hộp là tích Descartes các khoảng:

\[
\boxed{B=\prod_{i=1}^{d}[l_i,u_i].}
\]

Trong hai chiều:

\[
B=[x_{\min},x_{\max}]\times[y_{\min},y_{\max}],
\]

thường được gọi là **hình chữ nhật bao**. Trong ba chiều, đó là **khối hộp chữ nhật**. Các công thức kiểm tra bao chứa và giao nhau đều mở rộng tự nhiên tới \(d\) chiều.

### Minh họa 2D

~~~text
                 y
                 ^
            6    |
            5    |      +-------------+
            4    |      |             |
            3    |      |     B       |
            2    |      +-------------+
            1    |
            0    +----------------------------> x
                        2           6

B: xmin=2, xmax=6, ymin=2, ymax=5
~~~

Hộp \(B\) gồm **mọi điểm** có \(2\le x\le6\) và \(2\le y\le5\). Các điểm nằm **trên cạnh hoặc góc** cũng thuộc hộp do ta đã chọn quy ước biên đóng.

### Hộp bao nhỏ nhất theo trục cho một tập điểm

Cho tập hữu hạn \(S=\{p^{(1)},\ldots,p^{(n)}\}\) gồm các điểm trong \(\mathbb R^d\). AABB nhỏ nhất chứa mọi điểm của \(S\) có:

\[
\boxed{l_i=\min_j p_i^{(j)},\qquad
u_i=\max_j p_i^{(j)}.}
\]

Ví dụ:

\[
S=\{(1,2),(4,5),(3,1)\}.
\]

Khi đó:

\[
\operatorname{AABB}(S)=[1,4]\times[1,5].
\]

Tính hộp bao cho \(n\) điểm \(d\) chiều cần **\(O(nd)\)** phép so sánh trong mô hình đọc toàn bộ tọa độ, dùng **\(O(d)\)** bộ nhớ phụ.

**Tập rỗng:** không có min/max hữu hạn xác định. Một API có thể biểu diễn hộp rỗng bằng giá trị đặc biệt, nhưng không nên tự đưa vào một hộp có \(lo>hi\) rồi coi là AABB hợp lệ nếu cấu trúc đang yêu cầu \(lo_i\le hi_i\).

### Hộp suy biến

Quy tắc cho phép \(l_i=u_i\). Hộp như \([3,3]\times[1,5]\) biểu diễn một đoạn thẳng đứng trong 2D; \([3,3]\times[5,5]\) biểu diễn một điểm. Nó có diện tích bằng 0 nhưng **không phải tập rỗng** nếu biên đóng.

Đừng dùng điều kiện “diện tích \(>0\)” để quyết định một hộp bao có chứa điểm hay không.

## 4. Phép kiểm tra hình học cơ bản

Với mọi truy vấn, phải thống nhất: **tọa độ cùng số chiều**, cùng hệ quy chiếu và **quy ước biên đóng/mở**. Các công thức dưới đây dùng **AABB biên đóng**.

### 4.1. Điểm nằm trong hộp

Điểm \(p=(p_1,\ldots,p_d)\) thuộc AABB \(B=[lo,hi]\) khi và chỉ khi:

\[
\boxed{p\in B\iff
\bigwedge_{i=1}^{d}(lo_i\le p_i\le hi_i).}
\]

Trong 2D:

\[
x_{\min}\le p_x\le x_{\max}
\quad\text{và}\quad
y_{\min}\le p_y\le y_{\max}.
\]

Mỗi phép kiểm tra xem đủ \(d\) tọa độ nên có thời gian **\(O(d)\)**; trong 2D hoặc 3D cố định thường xem là **\(O(1)\)**.

### 4.2. Hai AABB giao nhau

Hai khoảng đóng trên một trục, \([a,b]\) và \([c,d]\), giao nhau khi:

\[
a\le d\quad\text{và}\quad c\le b.
\]

Với hộp \(A\) và \(B\) \(d\) chiều:

\[
\boxed{A\cap B\neq\varnothing
\iff
\bigwedge_{i=1}^{d}
(A.lo_i\le B.hi_i\ \land\ B.lo_i\le A.hi_i).}
\]

Một cách viết tương đương:

\[
A\cap B=\varnothing
\iff
\exists i:\ (A.hi_i<B.lo_i)\ \lor\ (B.hi_i<A.lo_i).
\]

Điểm then chốt: chỉ cần **tách rời trên một trục** là hai AABB **không giao**.

### 4.3. Hai hộp chạm biên vẫn giao nhau

Xét:

\[
A=[1,3]\times[0,2],\qquad
B=[3,5]\times[1,4].
\]

Hai hộp có chung đoạn biên \(x=3,\ y\in[1,2]\). Vì dùng khoảng **đóng**, ta có \(A\cap B\neq\varnothing\).

Nếu ứng dụng chỉ tính là “giao” khi hai vùng chồng lên nhau với **diện tích dương**, phải dùng một **predicate khác**, ví dụ yêu cầu độ dài giao **dương trên cả hai trục** với hình chữ nhật không suy biến. Không được âm thầm đổi nghĩa của từ “giao nhau”.

### 4.4. Một hộp bao trọn hộp khác

Hộp \(A\) chứa toàn bộ hộp \(B\) khi:

\[
\boxed{A\supseteq B\iff
\bigwedge_{i=1}^{d}(A.lo_i\le B.lo_i\ \land\
B.hi_i\le A.hi_i).}
\]

Ví dụ \([0,10]\times[0,10]\) bao trọn \([2,6]\times[3,8]\), nhưng không bao trọn \([-1,6]\times[3,8]\).

### 4.5. Hộp bao hợp của hai hộp

Một hộp **nhỏ nhất song song trục chứa cả A và B** được tính:

\[
\boxed{
\operatorname{envelope}(A,B).lo_i=\min(A.lo_i,B.lo_i),
}
\]

\[
\boxed{
\operatorname{envelope}(A,B).hi_i=\max(A.hi_i,B.hi_i).
}
\]

Đây là **hộp bao của hợp \(A\cup B\)**, không phải chính xác tập \(A\cup B\). Nếu A và B nằm rất xa nhau, hộp bao hợp có thể chứa một **vùng rỗng lớn không thuộc A lẫn B**.

Phép envelope quan trọng khi xây các nút trong R-tree hoặc tính hộp bao của một nhóm đối tượng.

## 5. Biên đóng và biên nửa mở: cần chọn nhất quán

Khi xử lý hình học để tìm các điểm nằm trong cửa sổ truy vấn, cách đơn giản là dùng **biên đóng**:

\[
[a,b]=\{x:a\le x\le b\}.
\]

Khi chia một mặt phẳng thành **ô lưới không chồng lên nhau**, cách dùng **nửa mở**:

\[
[a,b)=\{x:a\le x<b\}
\]

có thể thuận tiện hơn vì điểm đúng trên đường phân cách thường thuộc **đúng một ô**.

Ví dụ hai ô kề nhau:

\[
C_0=[0,10)\times[0,10),\quad
C_1=[10,20)\times[0,10).
\]

Điểm \((10,5)\) **không thuộc \(C_0\)** nhưng thuộc \(C_1\). Nếu cả hai ô dùng biên đóng, nó sẽ nằm trong **cả hai ô**.

| Ngữ cảnh | Quy ước có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Kiểm tra điểm có nằm trên ranh giới vùng | Biên đóng | Kể cả cạnh và góc |
| Lưới phân hoạch để gán một điểm vào ô | Nửa mở | Cần xử lý cạnh ngoài cùng riêng nếu miền hữu hạn |
| Phát hiện ứng viên va chạm khi tiếp xúc cũng tính là giao | Biên đóng | Chạm cạnh cũng được chọn |
| Kiểm tra phần giao có diện tích dương | Predicate riêng | Không dùng lẫn với “giao không rỗng” |

**Quan trọng:** Mỗi lớp dữ liệu nên công bố rõ quy tắc. Nếu hộp bao của chỉ mục dùng biên đóng, còn truy vấn sử dụng nửa mở, phải chuyển đổi điều kiện kiểm tra chính xác; nếu không có thể **bỏ sót hoặc đếm trùng điểm biên**.

## 6. Các kiểu truy vấn không gian phổ biến

### 6.1. Truy vấn phạm vi điểm (*orthogonal range query*)

Cho tập điểm \(P\) và hộp truy vấn \(Q\), trả về:

\[
\boxed{R_{\mathrm{point}}(Q)=\{p\in P:p\in Q\}.}
\]

Trong 2D, \(Q=[a,b]\times[c,d]\) yêu cầu đồng thời:

\[
a\le p_x\le b,\qquad c\le p_y\le d.
\]

Đây là truy vấn **range theo nhiều chiều**, khác với tra cứu bằng khóa chính xác. Nếu không có chỉ mục, quét \(n\) điểm tốn \(O(nd)\) thời gian và \(O(k)\) bộ nhớ kết quả khi có \(k\) điểm thỏa, chưa tính chi phí lưu tập đầu vào.

### 6.2. Truy vấn cửa sổ đối tượng (*window/intersection query*)

Với một tập hình học \(G=\{g_1,\ldots,g_n\}\) và cửa sổ \(Q\), cần tìm:

\[
\boxed{R_{\mathrm{geometry}}(Q)=
\{g\in G:g\cap Q\neq\varnothing\}.}
\]

Điểm khác biệt: nếu \(g\) là **đường thẳng, đa giác hoặc vùng có hình dạng phức tạp**, hộp bao \(B(g)\) chỉ là đại diện gần đúng bên ngoài.

Mọi điểm của \(g\) nằm trong \(B(g)\), nên:

\[
\boxed{g\cap Q\neq\varnothing
\Longrightarrow B(g)\cap Q\neq\varnothing.}
\]

Nhưng **chiều ngược lại không đúng**: \(B(g)\cap Q\neq\varnothing\) **không đảm bảo** \(g\cap Q\neq\varnothing\). Phải kiểm tra hình học thật nếu ứng dụng cần kết quả chính xác.

### 6.3. Truy vấn hộp giao nhau (*bounding-box intersection*)

Khi dữ liệu **chính là các AABB** và ta chỉ quan tâm đến việc hộp nào giao hộp \(Q\), phép kiểm tra ở mục 4 là **chính xác**. Không cần bước hình học chi tiết nếu không tồn tại hình học khác nằm bên trong các hộp.

### 6.4. Truy vấn lân cận theo bán kính

Cho tâm \(q\), bán kính \(r\ge0\), một metric \(D\), trả về:

\[
\boxed{R_{\mathrm{radius}}(q,r)=
\{p\in P:D(p,q)\le r\}.}
\]

Với Euclid 2D, miền truy vấn là **hình tròn**, không phải AABB. Ta có thể dùng hộp \([q_x-r,q_x+r]\times[q_y-r,q_y+r]\) để **tìm ứng viên**, rồi kiểm tra khoảng cách thật để loại các điểm ở góc hộp nhưng ngoài hình tròn.

### 6.5. Láng giềng gần nhất và \(k\) láng giềng

**Nearest neighbor (NN)** tìm điểm \(p^*\) có khoảng cách đến \(q\) nhỏ nhất:

\[
\boxed{p^*=\operatorname*{argmin}_{p\in P}D(p,q).}
\]

**\(k\)-nearest neighbors (kNN)** lấy \(k\) điểm gần \(q\) nhất theo một quy tắc xử lý **khoảng cách bằng nhau** đã xác định. Nếu có hai điểm cùng khoảng cách, nhiều đáp án đều đúng khi không yêu cầu thứ tự phụ; trong API cần đầu ra ổn định, có thể sắp theo **(khoảng cách, ID)**.

NN/kNN khác với truy vấn phạm vi: ta **chưa biết trước** giới hạn vùng chứa đủ điểm gần nhất. Các chỉ mục thường duyệt các vùng có **cận dưới khoảng cách nhỏ** trước để sớm tìm được ứng viên tốt.

### 6.6. Truy vấn kết hợp

Một sản phẩm có thể hỏi: “Tìm 10 cửa hàng gần nhất, chỉ trong vùng phục vụ và đang mở cửa”. Khi đó chỉ mục không gian trả ứng viên theo vị trí, còn điều kiện thời gian, trạng thái, danh mục phải được **lọc bổ sung**. Cần thiết kế thứ tự lọc phù hợp để tránh phải xét quá nhiều ứng viên.

## 7. Ví dụ có số liệu: range và giao nhau trong mặt phẳng

Giả sử có năm bản ghi điểm:

| ID | Tọa độ \((x,y)\) | Mô tả |
| --- | --- | --- |
| A | \((1,1)\) | Gần góc trái dưới |
| B | \((3,2)\) | Ở giữa vùng |
| C | \((5,5)\) | Phía trên bên phải |
| D | \((6,1)\) | Phía phải |
| E | \((2,4)\) | Phía trên |

Hỏi những điểm nào nằm trong hộp:

\[
Q=[1,4]\times[1,3].
\]

Ta kiểm tra từng tọa độ:

- **A \((1,1)\):** nằm trên biên trái/dưới, **được nhận** theo biên đóng.
- **B \((3,2)\):** hai tọa độ đều thuộc khoảng, **được nhận**.
- **C \((5,5)\):** \(x>4,y>3\), **bị loại**.
- **D \((6,1)\):** \(x>4\), **bị loại**.
- **E \((2,4)\):** \(y>3\), **bị loại**.

Kết quả:

\[
\boxed{R_{\mathrm{point}}(Q)=\{A,B\}.}
\]

### Kiểm tra giao với một vùng khác

Đặt \(S=[2,6]\times[0,2]\). Giao của hai AABB:

\[
Q\cap S=[2,4]\times[1,2].
\]

Giao **không rỗng** và có diện tích dương. Nếu thay \(S\) bằng \([4,6]\times[0,2]\), hai hộp vẫn giao nhau theo **biên đóng**, nhưng chỉ còn chung một đoạn tại \(x=4\).

### Hộp bao của năm điểm

Giá trị nhỏ nhất/lớn nhất theo từng trục của A–E là:

\[
x_{\min}=1,\quad x_{\max}=6,\quad
y_{\min}=1,\quad y_{\max}=5.
\]

Vậy:

\[
\boxed{\operatorname{AABB}(\{A,B,C,D,E\})
=[1,6]\times[1,5].}
\]

Hộp này bao tất cả năm điểm, nhưng **không có nghĩa** mọi vị trí trong hình chữ nhật \([1,6]\times[1,5]\) đều chứa một điểm dữ liệu.

## 8. Khoảng cách Euclid và các metric thường gặp

Đối với hai điểm \(p,q\in\mathbb R^d\), khoảng cách Euclid:

\[
\boxed{D_2(p,q)=
\sqrt{\sum_{i=1}^{d}(p_i-q_i)^2}.}
\]

Trong 2D, đó là công thức Pythagoras. Khi chỉ cần **so sánh điểm nào gần hơn**, có thể tránh tính căn bậc hai bằng cách so **bình phương khoảng cách**:

\[
\boxed{D_2^2(p,q)=\sum_{i=1}^{d}(p_i-q_i)^2.}
\]

Vì căn bậc hai **đồng biến** trên số không âm, thứ tự các điểm theo \(D_2^2\) giống thứ tự theo \(D_2\). So với bán kính \(r\), kiểm tra:

\[
D_2^2(p,q)\le r^2.
\]

**Các metric khác** có thể phù hợp hơn tùy ứng dụng:

| Metric | Công thức | Một ý nghĩa thường gặp |
| --- | --- | --- |
| Euclid \(L_2\) | \(\sqrt{\sum_i|p_i-q_i|^2}\) | Độ dài đường thẳng trong không gian Euclid |
| Manhattan \(L_1\) | \(\sum_i|p_i-q_i|\) | Tổng dịch chuyển theo các trục |
| Chebyshev \(L_\infty\) | \(\max_i|p_i-q_i|\) | Độ lệch lớn nhất ở một chiều |

Ví dụ từ \(q=(0,0)\) tới \(p=(3,4)\): \(L_2=5\), \(L_1=7\), \(L_\infty=4\).

**Metric phải khớp truy vấn:** một cây chỉ mục tối ưu cho khoảng cách Euclid và tọa độ phẳng không mặc nhiên cho kết quả đúng khi dùng khoảng cách đường đi theo mạng đường phố hay khoảng cách địa lý trên mặt cầu.

## 9. Khoảng cách nhỏ nhất từ điểm đến AABB

Đây là công cụ quan trọng để **cắt tỉa nhánh** (*pruning*) khi tìm láng giềng gần nhất.

Với điểm truy vấn \(q\) và hộp \(B=[lo,hi]\), đặt:

\[
\delta_i=
\begin{cases}
lo_i-q_i,&q_i<lo_i,\\
0,&lo_i\le q_i\le hi_i,\\
q_i-hi_i,&q_i>hi_i.
\end{cases}
\]

Khoảng cách Euclid nhỏ nhất từ \(q\) tới **bất kỳ điểm nào trong hộp** là:

\[
\boxed{\operatorname{minDist}_2(q,B)
=\sqrt{\sum_{i=1}^{d}\delta_i^2}.}
\]

Và bình phương của nó là:

\[
\boxed{\operatorname{minDist}_2^2(q,B)
=\sum_{i=1}^{d}\delta_i^2.}
\]

### Ví dụ

Cho \(q=(0,0)\), \(B=[2,4]\times[3,5]\). Điểm gần \(q\) nhất **trong hộp** là góc \((2,3)\), nên:

\[
\operatorname{minDist}_2^2(q,B)=2^2+3^2=13.
\]

Nếu \(q=(3,4)\) thì \(q\in B\), khoảng cách nhỏ nhất bằng 0. Nếu \(q=(5,4)\), chỉ lệch trục \(x\) một đơn vị, nên minDist bằng 1.

### Quy tắc cắt tỉa an toàn cho NN

Giả sử một nút chỉ mục chứa các đối tượng mà mọi điểm ứng viên đều nằm trong AABB \(B\). Ta đang có ứng viên gần nhất với **bình phương khoảng cách tốt nhất** \(best^2\). Nếu:

\[
\boxed{\operatorname{minDist}_2^2(q,B)>best^2,}
\]

thì **không điểm nào trong nhánh B có thể tốt hơn ứng viên hiện tại**; có thể bỏ qua nhánh.

Nếu dùng dấu **bằng**, khả năng có điểm khác **cùng khoảng cách** vẫn tồn tại. Có được bỏ qua trong trường hợp bằng hay không phụ thuộc yêu cầu xử lý **tie**. Với API chọn ID nhỏ nhất khi bằng khoảng cách, cần cẩn thận để không bỏ một ứng viên cùng khoảng cách nhưng có ID ưu tiên hơn.

**Bất biến của cắt tỉa:** hộp phải **bao hết dữ liệu của nhánh**. Nếu hộp được tính thiếu một điểm, thuật toán có thể bỏ nhầm nhánh chứa nghiệm thực sự.

## 10. Vì sao cần chỉ mục không gian?

Giả sử có \(n=10^6\) điểm, mỗi lần nhận truy vấn chỉ cần vài chục điểm nằm trong một cửa sổ nhỏ. **Quét tuyến tính** phải kiểm tra gần như toàn bộ một triệu điểm cho mỗi truy vấn, dù kết quả chỉ có vài chục bản ghi.

Một **chỉ mục không gian** (*spatial index*) tổ chức dữ liệu theo vị trí hoặc theo **hộp bao của các nhóm đối tượng**, giúp từ chối nhanh những nhóm chắc chắn không thể chứa kết quả.

~~~mermaid
flowchart TD
    Q["Truy vấn Q: vùng hoặc điểm cần tìm"] --> I["Chỉ mục không gian"]
    I --> B{"Hộp bao nhánh có thể liên quan?"}
    B -->|Không| P["Bỏ cả nhánh"]
    B -->|Có| C["Đi xuống hoặc lấy ứng viên"]
    C --> E{"Ứng viên thỏa predicate chính xác?"}
    E -->|Có| R["Đưa vào kết quả"]
    E -->|Không| X["Loại ứng viên"]
~~~

Chỉ mục chỉ có thể loại nhánh **an toàn** khi thông tin được lưu là một **cận bảo thủ**:

- Truy vấn giao hình học: nếu AABB nhánh **không giao** \(Q\), mọi đối tượng trong nhánh đều không giao \(Q\).
- Truy vấn điểm trong vùng: nếu AABB nhánh **không giao** \(Q\), không điểm nào của nhánh nằm trong \(Q\).
- NN: nếu khoảng cách nhỏ nhất từ điểm truy vấn tới AABB nhánh đã lớn hơn khoảng cách tốt nhất, có thể bỏ qua nhánh theo quy tắc tie thích hợp.

**Một chỉ mục không phải máy đoán kết quả chính xác.** Nếu các AABB chồng lấp rất nhiều hoặc mọi đối tượng nằm sát nhau, chỉ mục vẫn có thể phải duyệt gần hết dữ liệu.

## 11. Lưới đều (*uniform grid* / spatial hashing)

Một cách chia mặt phẳng đơn giản là thành các **ô lưới** có kích thước cố định \(s_x\times s_y\). Để định vị một điểm \((x,y)\) với gốc lưới \((x_0,y_0)\), ta tính:

\[
\boxed{c_x=\left\lfloor\frac{x-x_0}{s_x}\right\rfloor,\qquad
c_y=\left\lfloor\frac{y-y_0}{s_y}\right\rfloor.}
\]

Sau đó dùng cặp \((c_x,c_y)\) làm khóa trong một **hash map** chứa danh sách điểm thuộc ô.

Ví dụ \(x_0=y_0=0,s_x=s_y=10\):

- Điểm \((3,7)\) thuộc ô \((0,0)\).
- Điểm \((13,7)\) thuộc ô \((1,0)\).
- Điểm \((-1,7)\) thuộc ô \((-1,0)\), vì \(\lfloor-0{,}1\rfloor=-1\).

Điểm nằm đúng tại \(x=10\) thuộc ô \((1,\cdot)\) theo quy ước nửa mở.

### Truy vấn bằng lưới

Với cửa sổ AABB \(Q\), xác định các ô có khả năng giao \(Q\), duyệt danh sách ứng viên từ những ô đó, rồi **kiểm tra tọa độ từng điểm** bằng predicate point-in-box.

Nếu \(Q\) nhỏ so với toàn miền và các điểm phân bố tương đối đều, số ô và số điểm phải kiểm tra có thể thấp hơn nhiều so với quét toàn bộ.

**Đánh đổi:**

- Ô quá lớn → có nhiều điểm không liên quan trong cùng một ô.
- Ô quá nhỏ → một truy vấn có thể đi qua rất nhiều ô và tốn metadata.
- Phân bố điểm không đều → một ô rất đông và nhiều ô rỗng.
- Đối tượng là hình có diện tích, không phải điểm → phải quyết định lưu ở **mọi ô giao hình**, lưu ở ô của tâm cùng cơ chế xử lý khác, hoặc dùng chỉ mục phù hợp hơn để tránh bỏ sót.

Với lưới có số chiều \(d\), số ô cần duyệt cho một cửa sổ có thể tăng theo **tích số ô trên từng chiều**, nên không thể khẳng định truy vấn luôn \(O(1)\).

## 12. k-d tree: chia tập điểm theo các trục

**k-d tree** (*k-dimensional tree*) là cây tìm kiếm nhị phân phân chia điểm theo các tọa độ. Một nút chọn một **trục phân chia** và một giá trị ngưỡng; các điểm được phân nhóm theo trục đó.

Trong 2D, có thể luân phiên trục \(x,y\) qua các mức. Với tập điểm tĩnh, mỗi bước thường chọn **trung vị** (*median*) theo trục để tạo hai tập tương đối cân đối.

~~~text
Ví dụ ý tưởng:

           Phân chia theo x
                 |
       x nhỏ     |     x lớn
         vùng L  |  vùng R
                 |
       Ở vùng L và R, chia tiếp theo y,
       rồi x, rồi y, ...
~~~

### Truy vấn range

Với mỗi nút:

1. Kiểm tra điểm ở nút có thuộc cửa sổ \(Q\) không.
2. Dựa trên trục và ngưỡng phân chia, xác định nhánh nào **có khả năng chứa điểm thuộc Q**.
3. Bỏ nhánh chắc chắn không liên quan; duyệt nhánh còn lại.

Nếu lưu thêm **AABB bao toàn bộ điểm trong mỗi cây con**, ta còn có thể dùng predicate AABB giao Q như ở mục 4 để cắt tỉa.

### Truy vấn nearest neighbor

Có thể đi xuống nhánh chứa điểm truy vấn trước để tìm ứng viên tốt, sau đó kiểm tra nhánh còn lại **nếu** cận dưới khoảng cách từ truy vấn tới vùng của nhánh vẫn có thể tốt hơn ứng viên hiện tại.

**Đánh đổi:**

- Trong dữ liệu ít chiều và phân bố thuận lợi, k-d tree có thể loại được nhiều điểm.
- Với dữ liệu xấu hoặc số chiều cao, nhiều nhánh không thể loại, khiến truy vấn gần \(O(n)\).
- Việc chèn/xóa liên tục có thể làm cây mất cân đối nếu không có chiến lược cân bằng/xây lại.
- Chọn trục và ngưỡng chia không thay thế được việc **xử lý điểm trùng tọa độ** hoặc ID bản ghi trùng.

**Không đồng nhất k-d tree với BST một chiều.** K-d tree thay đổi tiêu chí so sánh theo trục, còn BST thường dùng một thứ tự khóa tổng quát.

## 13. Quadtree và octree: chia không gian thành các vùng

Trong 2D, **quadtree** thường chia một vùng thành **bốn ô con**. Trong 3D, **octree** chia một khối thành **tám khối con**. Có nhiều biến thể, ví dụ **point quadtree**, **region quadtree**, **loose quadtree**, nên cách xử lý điểm trùng hoặc đối tượng cắt ranh giới có thể khác nhau.

~~~text
     Vùng ban đầu             Chia thành bốn vùng con

  +---------------+         +-------+-------+
  |               |         |  NW   |  NE   |
  |               |   ->    +-------+-------+
  |               |         |  SW   |  SE   |
  +---------------+         +-------+-------+
~~~

Một cách triển khai cho **điểm** là đặt giới hạn \(b\) điểm trên mỗi ô lá. Khi số điểm vượt ngưỡng, chia ô thành bốn vùng nhỏ rồi phân phối điểm theo quy tắc biên nhất quán.

### Vấn đề cần xử lý

- Nếu nhiều điểm có **cùng tọa độ**, chia lặp vô hạn không giúp tách chúng. Cần giới hạn độ sâu, độ phân giải tối thiểu hoặc cho phép bucket chứa nhiều bản ghi trùng vị trí.
- Nếu điểm phân bố rất lệch, một số vùng bị chia sâu còn vùng khác rất thưa.
- Với đối tượng rộng, một hình có thể cắt nhiều ô; việc **sao chép tham chiếu** vào nhiều ô cần tránh trả trùng ID, hoặc dùng cơ chế lưu tại nút tổ tiên thích hợp.
- Khi dữ liệu ngoài miền gốc ban đầu, cần mở rộng miền hoặc có chính sách khác.

Quadtree phù hợp khi **phân hoạch không gian thành các vùng** là ý tưởng tự nhiên, chẳng hạn phát hiện lân cận trong game 2D hoặc tổ chức bản đồ có mật độ không đồng đều.

## 14. R-tree: nhóm các đối tượng theo hộp bao

**R-tree** được thiết kế để lập chỉ mục các đối tượng không gian có **hộp bao**: điểm, đường, đa giác hoặc những hình học khác.

Mỗi nút trong thường chứa nhiều mục dạng **(AABB bao nhánh, con trỏ tới nút con)**. Các lá lưu mục tham chiếu đối tượng hoặc bản ghi hình học. Hộp bao của một nút cha phải chứa **hộp bao của mọi đối tượng trong nhánh**.

~~~text
                    ROOT
             +----------------+
             | MBR_1 | MBR_2  |
             +----------------+
                 /        \
        +------------+   +------------+
        | hộp nhóm 1 |   | hộp nhóm 2 |
        +------------+   +------------+
             |                |
          các hình          các hình
~~~

**MBR** (*minimum bounding rectangle*) trong 2D thường chỉ hộp bao chữ nhật song song trục nhỏ nhất của đối tượng hoặc nhóm đối tượng; trong nhiều chiều có thể dùng thuật ngữ **minimum bounding box**.

### Truy vấn giao cửa sổ

1. Kiểm tra xem AABB của mục trong nút hiện tại có **giao Q** không.
2. Nếu không giao, **loại cả nhánh**.
3. Nếu giao, đi xuống và kiểm tra các hộp con.
4. Tới lá, lấy đối tượng ứng viên; nếu đối tượng không phải AABB và cần quan hệ giao hình học chính xác, kiểm tra hình gốc.

Đặc điểm quan trọng: **các MBR của các nhánh khác nhau trong R-tree có thể chồng lấp**. Khi một cửa sổ truy vấn chạm nhiều hộp, thuật toán có thể phải đi vào nhiều nhánh. Vì thế R-tree **không bảo đảm một đường tìm duy nhất** như BST.

### Ví dụ về false positive

Giả sử hình gốc là một **đoạn thẳng chéo** từ \((0,0)\) tới \((10,10)\). Hộp bao của nó là:

\[
B=[0,10]\times[0,10].
\]

Cho cửa sổ nhỏ:

\[
Q=[0,1]\times[9,10].
\]

Hai AABB giao nhau vì \(Q\subseteq B\). Nhưng đoạn thẳng chéo có \(y=x\), còn các điểm trong \(Q\) có \(x\le1\) và \(y\ge9\); do đó **đoạn thẳng không giao Q**.

R-tree có thể trả đoạn thẳng làm **ứng viên**, nhưng **phải loại sau khi kiểm tra chính xác**.

### Chèn và cập nhật

Khi thêm đối tượng mới, R-tree phải chọn nhánh để chèn, mở rộng các hộp bao tổ tiên nếu cần, và có thể **chia nút (*split*)** khi quá số mục. Có các chiến lược chọn nhánh và chia nút khác nhau, ảnh hưởng mức **chồng lấp MBR**, diện tích bao và hiệu năng.

Khi đối tượng di chuyển, hộp bao cũ có thể không còn đúng. Nếu chỉ sửa tọa độ đối tượng mà **không cập nhật chỉ mục và hộp bao tổ tiên**, hệ thống có thể **bỏ sót** đối tượng trong truy vấn.

## 15. So sánh các cấu trúc và độ phức tạp

Gọi \(n\) là số đối tượng, \(d\) là số chiều, \(k\) là số kết quả thực sự được trả về. Bảng sau mô tả **xu hướng và giới hạn**, không phải hứa hẹn hiệu năng cho mọi phân bố dữ liệu.

| Cấu trúc | Dữ liệu thường dùng | Điểm mạnh | Rủi ro / trường hợp xấu |
| --- | --- | --- | --- |
| Quét tuyến tính | Điểm/hình bất kỳ | Đơn giản, dễ kiểm chứng | Range/NN thường phải kiểm tra \(n\) đối tượng |
| Lưới đều / spatial hash | Điểm hoặc đối tượng nhỏ theo ô | Ô lân cận truy cập dễ, cập nhật điểm thường đơn giản | Ô rất đông hoặc phải duyệt quá nhiều ô |
| k-d tree | Điểm ít chiều | Phân hoạch theo trục, hỗ trợ range và NN | Dữ liệu lệch, số chiều cao, cập nhật nhiều |
| Quadtree / octree | Vùng 2D/3D, phân bố không đều | Phân hoạch vùng theo cấp, hỗ trợ truy vấn cục bộ | Chia sâu, nhiều đối tượng giao ranh giới |
| R-tree | Hộp bao hình học, chỉ mục đĩa hoặc RAM | Lọc window/intersection, lưu các nhóm MBR | Nhiều MBR chồng lấp gây duyệt nhiều nhánh |

### Độ phức tạp cần đọc đúng điều kiện

- **Quét điểm range:** \(O(nd+k)\) nếu tính riêng chi phí xuất \(k\) phần tử; thường ghi \(O(n)\) với \(d\) cố định và \(k\le n\).
- **Kiểm tra một điểm trong hộp / hai hộp giao nhau:** \(O(d)\), thường xem \(O(1)\) nếu \(d=2,3\) cố định.
- **Xây AABB cho \(n\) điểm:** \(O(nd)\).
- **k-d tree tĩnh** dùng sắp xếp lại tại từng cấp: một cách triển khai đơn giản có thể tốn \(O(n\log^2 n)\) để xây cây cân đối từ điểm phân biệt; những cách tổ chức trung vị phù hợp có thể cải thiện. Truy vấn NN **không có bảo đảm \(O(\log n)\) cho mọi dữ liệu**; trường hợp xấu có thể \(O(n)\).
- **Quadtree** có số nút phụ thuộc chính sách phân chia, giới hạn độ sâu và phân bố dữ liệu; không nên khẳng định truy vấn \(O(\log n)\) vô điều kiện.
- **R-tree** thường hoạt động hiệu quả khi hộp nhóm gọn và ít chồng lấp; truy vấn có thể xấu tới \(O(n)\) khi phải xem gần như mọi mục.
- **Xuất \(k\) kết quả luôn cần ít nhất \(\Omega(k)\)** thời gian để đưa đủ chúng ra ngoài, dù chỉ mục tìm vị trí bắt đầu rất nhanh.

**Quan trọng:** Những ký hiệu trên nói về số thao tác cấu trúc. Trong hệ thống lưu trữ lớn, **đọc trang đĩa, truy cập cache, cấp phát node và cập nhật chỉ mục** có thể chi phối thời gian thật.

## 16. Lời nguyền số chiều (*curse of dimensionality*)

Khi số chiều \(d\) tăng, số vùng phân hoạch có thể tăng rất nhanh. Ví dụ chia **mỗi trục thành 10 khoảng**, không gian \(d\) chiều có:

\[
\boxed{10^d\text{ ô}.}
\]

| Số chiều \(d\) | Số ô nếu chia mỗi trục làm 10 |
| ---: | ---: |
| 2 | 100 |
| 3 | 1.000 |
| 5 | 100.000 |
| 10 | 10.000.000.000 |

Không nhất thiết phải **cấp phát toàn bộ** số ô này nếu dùng spatial hash thưa; tuy nhiên số chiều tăng vẫn có thể làm:

- Khó giữ đủ mật độ điểm trong các vùng nhỏ.
- Nhiều vùng có cận dưới khoảng cách gần nhau, làm **cắt tỉa NN kém hiệu quả**.
- Tăng chi phí lưu và so sánh hộp bao (\(2d\) tọa độ cho min/max).
- Tăng chi phí tính metric \(O(d)\) trên mỗi cặp điểm.

Một chỉ mục rất tốt ở 2D **không nhất thiết** tốt ở 100D hoặc 768D. Đối với vector embedding nhiều chiều, có thể cần các phương pháp **approximate nearest neighbor (ANN)** phù hợp, chấp nhận đánh đổi độ chính xác/recall lấy tốc độ và bộ nhớ.

**Không nhầm ANN với kết quả chính xác:** nếu bài toán yêu cầu trả đúng NN toàn cục theo metric, giải thuật gần đúng cần được đánh giá bằng tỷ lệ tìm đúng, không được gắn nhãn “kết quả NN chính xác” mà không kiểm chứng.

## 17. Python: cài đặt AABB \(d\) chiều và các truy vấn cơ bản

Ví dụ dưới đây dùng **Python 3.10+**, chỉ dùng thư viện chuẩn, và tuân theo các quy tắc:

1. Tọa độ là các số thực **hữu hạn**, không nhận NaN hoặc vô cực.
2. Mọi phép toán giữa hai điểm/hộp phải dùng **cùng số chiều**.
3. Hộp có **biên đóng**, vì vậy các điểm và hộp chạm ranh giới vẫn được tính là giao.
4. Một bản ghi có **ID** riêng, nên hai bản ghi cùng tọa độ vẫn là hai đối tượng.
5. Hàm kNN phá hòa theo thứ tự **(bình phương khoảng cách, ID)** để kết quả ổn định.

~~~python
from dataclasses import dataclass
from heapq import nsmallest
from math import isfinite


def coordinates(values):
    """Chuẩn hóa vector; không cho phép vector rỗng/NaN/vô cực."""
    result = tuple(float(value) for value in values)
    if not result or not all(isfinite(value) for value in result):
        raise ValueError("Tọa độ phải có ít nhất 1 chiều, hữu hạn")
    return result


def same_dimensions(left, right):
    if len(left) != len(right):
        raise ValueError("Hai đối tượng phải cùng số chiều")


@dataclass(frozen=True)
class AABB:
    lo: tuple[float, ...]
    hi: tuple[float, ...]

    def __post_init__(self):
        lo = coordinates(self.lo)
        hi = coordinates(self.hi)
        same_dimensions(lo, hi)
        if any(a > b for a, b in zip(lo, hi)):
            raise ValueError("lo phải <= hi trên mọi trục")

        object.__setattr__(self, "lo", lo)
        object.__setattr__(self, "hi", hi)

    @property
    def dimension(self):
        return len(self.lo)

    def contains_point(self, point):
        point = coordinates(point)
        same_dimensions(self.lo, point)
        return all(
            low <= value <= high
            for low, value, high in zip(self.lo, point, self.hi)
        )

    def intersects(self, other):
        same_dimensions(self.lo, other.lo)
        return all(
            low_a <= high_b and low_b <= high_a
            for low_a, high_a, low_b, high_b in zip(
                self.lo, self.hi, other.lo, other.hi
            )
        )

    def contains_box(self, other):
        same_dimensions(self.lo, other.lo)
        return all(
            low_a <= low_b and high_b <= high_a
            for low_a, high_a, low_b, high_b in zip(
                self.lo, self.hi, other.lo, other.hi
            )
        )

    def envelope(self, other):
        """AABB nhỏ nhất bao trọn cả hai hộp."""
        same_dimensions(self.lo, other.lo)
        return AABB(
            tuple(min(a, b) for a, b in zip(self.lo, other.lo)),
            tuple(max(a, b) for a, b in zip(self.hi, other.hi)),
        )

    def min_distance_sq(self, point):
        """Bình phương khoảng cách Euclid từ điểm tới hộp."""
        point = coordinates(point)
        same_dimensions(self.lo, point)
        return sum(
            max(low - value, 0.0, value - high) ** 2
            for low, value, high in zip(self.lo, point, self.hi)
        )

    @classmethod
    def from_points(cls, points):
        """Xây AABB theo một lượt quét, O(nd) thời gian, O(d) bộ nhớ."""
        iterator = iter(points)
        try:
            first = coordinates(next(iterator))
        except StopIteration:
            raise ValueError("Không thể tạo AABB từ tập điểm rỗng")

        low = list(first)
        high = list(first)
        for raw_point in iterator:
            point = coordinates(raw_point)
            same_dimensions(first, point)
            for i, value in enumerate(point):
                low[i] = min(low[i], value)
                high[i] = max(high[i], value)
        return cls(tuple(low), tuple(high))


@dataclass(frozen=True)
class PointRecord:
    id: str
    point: tuple[float, ...]

    def __post_init__(self):
        object.__setattr__(self, "point", coordinates(self.point))


def squared_distance(a, b):
    a = coordinates(a)
    b = coordinates(b)
    same_dimensions(a, b)
    return sum((x - y) ** 2 for x, y in zip(a, b))


def range_points(records, query_box):
    """Bản tham chiếu: quét tuyến tính và lọc điểm trong AABB."""
    return [
        record for record in records
        if query_box.contains_point(record.point)
    ]


def intersecting_boxes(box_records, query_box):
    """Mỗi phần tử là (ID, AABB); tìm hộp giao cửa sổ."""
    return [
        item_id for item_id, item_box in box_records
        if item_box.intersects(query_box)
    ]


def within_radius(records, center, radius):
    if not isfinite(radius) or radius < 0:
        raise ValueError("Bán kính phải hữu hạn và không âm")
    radius_sq = radius ** 2
    return [
        record for record in records
        if squared_distance(record.point, center) <= radius_sq
    ]


def k_nearest(records, center, k):
    if type(k) is not int or k < 1:
        raise ValueError("k phải là số nguyên dương")
    # Trả tối đa min(k, len(records)) phần tử.
    return nsmallest(
        k,
        records,
        key=lambda rec: (squared_distance(rec.point, center), rec.id)
    )


points = [
    PointRecord("A", (1, 1)),
    PointRecord("B", (3, 2)),
    PointRecord("C", (5, 5)),
    PointRecord("D", (6, 1)),
    PointRecord("E", (2, 4)),
]

query = AABB((1, 1), (4, 3))
assert [rec.id for rec in range_points(points, query)] == ["A", "B"]

overall = AABB.from_points(rec.point for rec in points)
assert overall == AABB((1, 1), (6, 5))

region = AABB((2, 0), (6, 2))
assert query.intersects(region)
assert query.envelope(region) == AABB((1, 0), (6, 3))
assert AABB((0, 0), (10, 10)).contains_box(query)

assert query.min_distance_sq((0, 0)) == 2.0
assert query.min_distance_sq((3, 2)) == 0.0

assert [rec.id for rec in within_radius(points, (1, 1), 2.3)] == [
    "A", "B"
]
assert [rec.id for rec in k_nearest(points, (1, 1), 2)] == ["A", "B"]

boxes = [
    ("X", AABB((0, 0), (2, 2))),
    ("Y", AABB((10, 10), (12, 12))),
    ("Z", AABB((4, 3), (5, 7))),
]
# Z giao query đúng tại góc (4, 3), nên được chọn do biên đóng.
assert intersecting_boxes(boxes, query) == ["X", "Z"]

# Kiểm tra biên và số chiều:
assert AABB((2, 3), (2, 3)).contains_point((2, 3))
assert AABB((0, 0), (1, 1)).intersects(
    AABB((1, 1), (2, 2))
)
~~~

### Đọc đúng ví dụ

**Quét tuyến tính** trong range_points có chi phí \(O(nd+k)\) khi tính cả đầu ra, với \(d\) chiều và \(k\) kết quả. Nó là **mốc tham chiếu về tính đúng** để so sánh với các phiên bản có chỉ mục sau này.

**AABB có thể suy biến:** hộp \([2,2]\times[3,3]\) có diện tích 0 nhưng chứa điểm \((2,3)\). Một hộp chạm hộp khác ở đúng một góc vẫn **giao nhau**.

**Cùng tọa độ, khác bản ghi:** nếu thêm PointRecord("A2", (1,1)), cả A và A2 đều được tìm thấy trong Q; phép kNN trả một số bản ghi gần nhất theo thứ tự có tie. Không nên dùng tọa độ làm ID nếu nghiệp vụ cho phép nhiều bản ghi cùng vị trí.

**Chú ý về float:** chương trình từ chối NaN/vô cực ở đầu vào, nhưng không tự áp dụng ngưỡng epsilon cho các phép so sánh. Trong dữ liệu hình học tính toán, việc chọn epsilon tùy ý có thể khiến các predicate không còn nhất quán; nên xác định sai số và quy tắc làm tròn theo ứng dụng, đặc biệt khi tọa độ được tính qua nhiều phép biến đổi.

**Chi phí của kNN tham chiếu:** heapq.nsmallest xét từng bản ghi, tính khoảng cách \(O(d)\) cho mỗi bản ghi rồi duy trì \(k\) kết quả; khi \(k\ll n\), phần quản lý heap thường \(O(n\log k)\). Nó **chưa phải một chỉ mục NN** vì vẫn phải xem mọi điểm.

## 18. Python: k-d tree tĩnh với hộp bao cây con

Để thấy **chỉ mục khác gì quét tuyến tính**, ta có thể xây k-d tree cho tập điểm ít chiều **không thay đổi**. Mỗi nút lưu:

- Một bản ghi điểm.
- Hai cây con trái/phải được phân theo trục tại mức đó.
- Một AABB **bao tất cả điểm trong cây con của nút**, tính sau khi dựng hai nhánh.

AABB giúp bỏ nguyên nhánh khi nó **không giao hộp truy vấn**, hoặc khi **khoảng cách nhỏ nhất từ truy vấn tới hộp nhánh** lớn hơn khoảng cách tốt nhất đã biết.

**Đoạn mã dưới đây nối tiếp các định nghĩa AABB, PointRecord, coordinates và squared_distance ở mục 17.** Nó được cung cấp để người học tự chạy cùng mã mục 17; đây không phải cài đặt đa luồng hay chỉ mục cập nhật động.

~~~python
from dataclasses import dataclass


@dataclass
class KDNode:
    record: PointRecord
    region: AABB
    left: "KDNode | None" = None
    right: "KDNode | None" = None


def build_kd(records, depth=0):
    """Xây k-d tree cân theo trung vị, với bbox chính xác cho từng nhánh."""
    if not records:
        return None

    dimension = len(records[0].point)
    for record in records:
        if len(record.point) != dimension:
            raise ValueError("Mọi điểm phải có cùng số chiều")

    axis = depth % dimension
    ordered = sorted(
        records, key=lambda rec: (rec.point[axis], rec.id)
    )
    middle = len(ordered) // 2
    pivot = ordered[middle]

    left = build_kd(ordered[:middle], depth + 1)
    right = build_kd(ordered[middle + 1:], depth + 1)

    region = AABB(pivot.point, pivot.point)
    if left is not None:
        region = region.envelope(left.region)
    if right is not None:
        region = region.envelope(right.region)

    return KDNode(pivot, region, left, right)


def kd_range(root, query_box):
    result = []

    def visit(node):
        if node is None:
            return
        if not node.region.intersects(query_box):
            return  # Cả cây con chắc chắn không chứa kết quả.

        if query_box.contains_point(node.record.point):
            result.append(node.record)
        visit(node.left)
        visit(node.right)

    visit(root)
    return sorted(result, key=lambda rec: rec.id)


def kd_nearest(root, query_point):
    if root is None:
        return None
    query_point = coordinates(query_point)
    same_dimensions(root.record.point, query_point)
    best = None  # ((squared distance, ID), PointRecord)

    def visit(node):
        nonlocal best
        if node is None:
            return

        # Chỉ loại khi minDist LỚN HƠN rõ ràng best.
        # Nếu bằng, vẫn kiểm tra để xử lý tie theo ID.
        if (best is not None
                and node.region.min_distance_sq(query_point) > best[0][0]):
            return

        candidate_key = (
            squared_distance(node.record.point, query_point),
            node.record.id,
        )
        if best is None or candidate_key < best[0]:
            best = (candidate_key, node.record)

        children = [
            child for child in (node.left, node.right)
            if child is not None
        ]
        # Duyệt vùng gần hơn trước để sớm có best tốt.
        children.sort(key=lambda child: (
            child.region.min_distance_sq(query_point),
            child.record.id,
        ))
        for child in children:
            visit(child)

    visit(root)
    return best[1]


index = build_kd(points)  # Biến points từ mục 17.
assert index is not None
assert [rec.id for rec in kd_range(index, query)] == ["A", "B"]
assert kd_nearest(index, (1, 1)).id == "A"

# Với cùng quy tắc tie, kết quả chỉ mục phải khớp quét tham chiếu.
for center in [(1, 1), (2, 2), (4, 3), (6, 6)]:
    expected = k_nearest(points, center, 1)[0].id
    actual = kd_nearest(index, center).id
    assert actual == expected
~~~

### Tại sao cắt tỉa vẫn đúng?

Mỗi AABB nhánh được tính từ **điểm trong nút và hộp của cả hai cây con**, nên nó **chứa tất cả điểm trong nhánh**. Nếu AABB ấy không giao cửa sổ Q, mọi điểm bên trong nhánh đều ở ngoài Q. Với NN, minDist là **cận dưới** của khoảng cách tới mọi điểm của nhánh; nếu cận dưới đã lớn hơn ứng viên tốt nhất, không điểm nào trong đó có thể thay thế ứng viên hiện tại.

### Những giới hạn của mã

- Hàm build_kd **sắp xếp lại các điểm ở mỗi mức**; với các nhánh cân theo trung vị, chi phí xây dựng trong cách viết đơn giản này là khoảng **\(O(n\log^2 n)\)** khi số chiều cố định và so sánh tọa độ có chi phí hằng số.
- Mã lưu **một AABB và hai liên kết con** ở mỗi nút, nên metadata tốn \(O(nd)\) tọa độ. Ở \(d=2\) cố định, đó là \(O(n)\) bộ nhớ theo số nút.
- Cây có chiều cao \(O(\log n)\) do chia theo trung vị số bản ghi, nhưng **không có nghĩa mọi phép NN/range luôn \(O(\log n)\)**; trong trường hợp xấu vẫn có thể phải duyệt \(O(n)\) điểm.
- **Không sửa trực tiếp tọa độ của các PointRecord đã đưa vào chỉ mục.** Thay tọa độ phải cập nhật cấu trúc, AABB các nhánh hoặc xây lại chỉ mục; nếu không, kết quả cắt tỉa có thể sai. Ví dụ dùng dataclass bất biến cho tọa độ để tránh vô tình sửa tại chỗ.
- Truy vấn sâu, tập trùng điểm lớn, dữ liệu nhiều chiều và khả năng cập nhật là các vấn đề cần cài đặt riêng ở hệ thống sản xuất.

## 19. Khi dữ liệu được cập nhật liên tục

Trong hệ thống động, có thể có ba kiểu thay đổi:

1. **Thêm đối tượng:** cần đưa nó vào nhánh hoặc ô lưới phù hợp và cập nhật các hộp bao liên quan.
2. **Xóa đối tượng:** cần bỏ tham chiếu, điều chỉnh metadata nếu cần; có thể phải gộp vùng/nút hoặc tái cân bằng.
3. **Di chuyển đối tượng:** tọa độ/hình học thay đổi, nên vị trí trong chỉ mục hoặc AABB tổ tiên có thể không còn bao đúng đối tượng.

Một sai lầm nghiêm trọng là **chỉ sửa bản ghi gốc**:

~~~text
Ban đầu:  điểm P ở (2, 2), trong AABB nhánh [0, 4] × [0, 4]
Sau:      điểm P chuyển tới (50, 50)
Nhưng:    AABB nhánh vẫn là [0, 4] × [0, 4]
~~~

Khi truy vấn quanh \((50,50)\), nhánh cũ có AABB không giao vùng mới nên bị **cắt tỉa**, dẫn đến **bỏ sót P**, dù bản ghi P có tọa độ mới. Đây là lỗi **sai tính đúng**, không chỉ lỗi hiệu năng.

### Chiến lược cập nhật

| Chỉ mục | Hướng xử lý thường gặp | Cần chú ý |
| --- | --- | --- |
| Lưới/spatial hash | Xóa bản ghi khỏi ô cũ, thêm vào ô mới | Có thể dùng chỉ số đảo ID→ô, xử lý điểm biên |
| k-d tree tĩnh | Xây lại theo đợt hoặc dùng cấu trúc hỗ trợ cập nhật động | Cây có thể mất cân đối, hộp nhánh phải đúng |
| Quadtree | Chuyển điểm giữa các ô, chia hoặc gộp vùng khi cần | Giới hạn độ sâu, nhiều điểm trùng vị trí |
| R-tree | Cập nhật MBR, có thể xóa/chèn lại hoặc điều chỉnh nhánh | MBR tổ tiên, chồng lấp, split/merge |
| Chỉ mục kết hợp | Giữ bản chính cùng overlay cho thay đổi mới | Phải hợp nhất kết quả và tránh trả trùng ID |

Không có thao tác “cập nhật tọa độ \(O(1)\)” chung cho mọi cấu trúc. Chi phí phụ thuộc **bất biến chỉ mục**, số nhánh bị ảnh hưởng, chính sách cân bằng, cache và nơi lưu trữ.

### Đồng thời và phiên bản dữ liệu

Nếu luồng truy vấn đọc hộp bao **phiên bản cũ** trong khi luồng khác cập nhật điểm sang vị trí mới, kết quả có thể sai nếu không có đồng bộ. Có thể sử dụng khóa, snapshot, phiên bản chỉ mục hoặc cơ chế transaction; mức bảo đảm phải phù hợp với yêu cầu sản phẩm.

Một hệ thống chỉ mục không gian ngoài bộ nhớ còn có thể cần khôi phục sau sự cố: cập nhật bản ghi nhưng chưa cập nhật chỉ mục phải được **phát hiện và sửa** bằng log/rebuild hoặc cơ chế nhất quán khác.

## 20. Tọa độ địa lý và phép chiếu: đừng coi kinh độ/vĩ độ là mét

Dữ liệu bản đồ thường được cho dưới dạng **vĩ độ, kinh độ** (latitude, longitude). Hai số này thường đo bằng **độ góc**, không phải khoảng cách phẳng theo mét.

### Ba khác biệt quan trọng

1. **Khoảng cách:** Một độ kinh độ tương ứng độ dài mặt đất khác nhau tùy vĩ độ. Dùng \(D_2\) trực tiếp trên (kinh độ, vĩ độ) không cho khoảng cách mét chính xác.
2. **Đường đổi ngày quốc tế:** Một vùng gần kinh độ \(+179^\circ\) có thể ở sát vùng \(-179^\circ\), nhưng biểu diễn số thô khiến chúng có vẻ cách nhau khoảng 358 độ.
3. **Vùng cực và phép chiếu:** Các phép chiếu phẳng có thể gây biến dạng khoảng cách, diện tích và hình dạng tùy vị trí.

Nếu mục tiêu là truy vấn theo **khoảng cách địa lý**, có thể dùng công thức khoảng cách trên cầu như **haversine** cho mô hình cầu, hoặc thuật toán khoảng cách trên ellipsoid phù hợp với yêu cầu chính xác; cũng có thể **chiếu tọa độ sang hệ phẳng thích hợp** cho một khu vực nhỏ.

**Quy tắc dữ liệu:** Mọi bản ghi và hộp truy vấn phải khai báo **CRS** (*coordinate reference system*, hệ quy chiếu tọa độ) và **thứ tự trục** thống nhất. Có API dùng \((longitude,latitude)\), có API dùng \((latitude,longitude)\). Đảo nhầm trục có thể đưa đối tượng tới vùng hoàn toàn khác.

### AABB trên kinh độ có tính tuần hoàn

Trong hệ kinh độ chuẩn hóa \([-180^\circ,180^\circ]\), một vùng cắt qua kinh tuyến đổi ngày có thể không biểu diễn đúng bằng một khoảng \([lon_{\min},lon_{\max}]\) thông thường. Cần **chia thành hai vùng**, hoặc dùng cấu trúc/predicate xử lý khoảng tuần hoàn.

Ví dụ, vùng bao những vị trí từ \(170^\circ\) Đông qua đường đổi ngày tới \(170^\circ\) Tây thường được tách thành:

\[
[170^\circ,180^\circ]\quad\cup\quad[-180^\circ,-170^\circ].
\]

Nếu lấy thẳng min=-170, max=170, ta lại biểu diễn **vùng gần như đối diện**. Điều này có thể làm kết quả range query sai ngay cả khi công thức AABB trên mặt phẳng đúng.

### Thời gian như một chiều

Một bản ghi \((x,y,t)\) có thể được lưu trong không gian ba chiều, với hộp \([x_0,x_1]\times[y_0,y_1]\times[t_0,t_1]\). Truy vấn range theo cả ba trục vẫn dùng phép so sánh tọa độ. Nhưng nếu cần “điểm gần nhất” theo một metric, phải quyết định **một giây tương đương bao nhiêu mét** hoặc dùng metric đặc thù; không có lựa chọn tự nhiên chung cho mọi ứng dụng.

## 21. Chọn chỉ mục và đo hiệu năng

Trước khi chọn k-d tree, quadtree, R-tree hoặc lưới, hãy xác định **workload**:

| Câu hỏi | Ví dụ cần đo | Tác động tới lựa chọn |
| --- | --- | --- |
| Số chiều và loại tọa độ? | 2D phẳng, 3D, địa lý, vector 100D | Chi phí hình học và hiệu quả cắt tỉa |
| Dữ liệu là điểm hay hình phức tạp? | 5 triệu điểm, 100.000 polygon | k-d tree cho điểm; R-tree thường phù hợp cho MBR hình |
| Loại truy vấn chủ yếu? | Range, intersect, NN, kNN, radius | Mỗi chỉ mục có ưu thế khác nhau |
| Kích thước cửa sổ? | 0,01% hay 80% toàn miền | Cửa sổ lớn có thể buộc trả gần hết dữ liệu |
| Phân bố điểm? | Đều, cụm dày, nhiều điểm trùng | Quyết định cách chia vùng và phân bố nhánh |
| Tỷ lệ cập nhật? | Chủ yếu đọc hay di chuyển liên tục | Xây tĩnh so với cập nhật động |
| Bộ nhớ/thiết bị? | RAM, SSD, dữ liệu ngoài bộ nhớ | Metadata, số trang I/O, cache locality |
| Có hình học chính xác sau lọc? | Đường, đa giác, vật thể 3D | Chi phí refine và false positive |
| Kết quả cần chuẩn hóa thứ tự? | Sắp theo ID, khoảng cách | Phân biệt kết quả tập hợp và thứ tự trả về |

### Những chỉ số benchmark quan trọng

- **Số nhánh/nút chỉ mục được thăm** cho mỗi truy vấn.
- **Số ứng viên được trả** so với **số kết quả thực sự** (tỷ lệ false positive).
- **Thời gian p50/p95/p99**, tách theo loại truy vấn và kích thước cửa sổ.
- **Chi phí xây chỉ mục**, số lần chia nút, cập nhật, rebuild.
- **Bộ nhớ ổn định và đỉnh**, metadata hộp bao, tham chiếu và cache.
- **Độ chính xác/recall** nếu dùng ANN, so với nghiệm chính xác trên tập kiểm tra.
- **Số trang đĩa đọc/ghi** nếu cấu trúc nằm ngoài RAM.

### Một phép đo công bằng

1. Tạo dữ liệu thử có cùng ID, tọa độ và loại đối tượng cho mọi ứng viên.
2. Xác nhận câu trả lời của chỉ mục bằng **quét tham chiếu** trên các truy vấn nhỏ và nhiều trường hợp biên.
3. Dùng cả dữ liệu **phân bố đều** và **phân bố theo cụm**; thêm nhiều điểm trùng tọa độ.
4. Tách phép đo **xây dựng**, **query**, **insert**, **delete** và **update vị trí**.
5. Đo những truy vấn trả rất ít kết quả, trung bình và rất nhiều kết quả.
6. Báo cáo điều kiện phần cứng, số chiều, hệ tọa độ, cách xử lý biên, quy tắc tie và tham số chỉ mục.
7. Nếu có truy vấn hình học phức tạp, đo **candidate filtering** và **exact refinement** riêng; không coi mọi ứng viên MBR đều là kết quả thật.

**Không có chỉ mục thắng tuyệt đối:** một quét tuyến tính vector hóa trong RAM có thể nhanh hơn một cây chỉ mục phức tạp trên tập nhỏ; một chỉ mục cần thiết ở hàng triệu đối tượng có thể chưa đáng chi phí xây ở vài trăm điểm.

## 22. Các lỗi và hiểu lầm thường gặp

1. **“Hai điểm có \(x\) gần nhau thì chắc chắn gần nhau trong 2D.”** Sai: khoảng cách còn phụ thuộc \(y\).
2. **“Dữ liệu 2D có thể chỉ sắp theo \(x\) rồi giải quyết mọi truy vấn bằng tìm kiếm nhị phân.”** Sai: điều kiện \(y\) và khoảng cách vẫn cần xử lý.
3. **“Điểm nằm trên cạnh hộp phải bị loại.”** Tùy quy ước; trong bài này **hộp đóng** nên điểm biên được nhận.
4. **“Hai hình chữ nhật chạm cạnh không giao nhau.”** Sai nếu dùng predicate giao **không rỗng** của hai hộp đóng.
5. **“Diện tích hộp bằng 0 nghĩa là không có điểm.”** Sai: hộp suy biến vẫn có thể chứa đoạn hoặc điểm.
6. **“Hộp bao của hợp hai hình bằng chính hợp của hai hình.”** Sai: envelope có thể chứa vùng trống lớn.
7. **“MBR giao cửa sổ nghĩa là đường hoặc đa giác gốc cũng giao.”** Sai: MBR chỉ lọc ứng viên.
8. **“Nếu MBR không giao Q vẫn có thể có hình bên trong giao Q.”** Với MBR được tính đúng và bao **toàn bộ hình**, điều đó **không thể** xảy ra; đây chính là bảo đảm an toàn khi cắt tỉa.
9. **“AABB một cây con được tính một lần rồi giữ mãi dù điểm di chuyển.”** Sai: bbox lỗi thời có thể gây **false negative**.
10. **“Một R-tree luôn đi xuống đúng một nhánh.”** Sai: các MBR có thể chồng lấp, phải duyệt nhiều nhánh.
11. **“k-d tree luôn tìm NN trong \(O(\log n)\).”** Sai: trường hợp xấu có thể duyệt nhiều, thậm chí tất cả điểm.
12. **“Quadtree cứ chia tiếp là giải quyết được nhiều điểm trùng tọa độ.”** Sai: cần độ sâu tối đa hoặc bucket chứa nhiều bản ghi.
13. **“Mỗi điểm có tọa độ duy nhất.”** Sai: nhiều ID có thể cùng tọa độ.
14. **“Tăng số chiều không ảnh hưởng chỉ mục.”** Sai: số vùng, chi phí hộp bao và hiệu quả cắt tỉa có thể thay đổi mạnh.
15. **“Kinh độ/vĩ độ có thể dùng Euclid trực tiếp để ra mét.”** Sai: phải xét CRS, phép chiếu và metric địa lý.
16. **“Tính minDist tới AABB cho luôn khoảng cách thật tới hình nằm bên trong.”** Sai: đó chỉ là **cận dưới**; hình có thể nằm rất xa điểm gần nhất của hộp.
17. **“Khi NN có hai điểm cùng khoảng cách thì chọn bất kỳ vẫn là đầu ra ổn định.”** Không nếu API yêu cầu thứ tự theo ID; cần chính sách tie và cắt tỉa phù hợp.
18. **“Dùng số thực NaN trong min/max mà không kiểm tra vẫn an toàn.”** Sai: nhiều phép so sánh với NaN trả False, có thể làm hỏng predicate.
19. **“Chỉ cần ghi số kết quả, không cần đo số ứng viên.”** Sai: quá nhiều false positive có thể làm bước refine rất tốn công.
20. **“R-tree lưu hộp bao sẽ giải quyết luôn mọi bài toán hình học.”** Sai: cần predicate chính xác, metric và chỉ mục bổ sung tùy nghiệp vụ.
21. **“Một ô grid có thể dùng cả biên đóng và vẫn chắc chắn gán mỗi điểm vào đúng một ô.”** Sai tại ranh giới giữa các ô; nên thống nhất quy tắc nửa mở hoặc tie.
22. **“Thêm tọa độ thời gian vào vector thì Euclid tự có ý nghĩa.”** Sai: cần định nghĩa cách so sánh các đơn vị.

## 23. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Điểm thuộc hình chữ nhật

Cho \(Q=[2,7]\times[1,5]\). Những điểm nào thuộc Q theo quy tắc biên đóng: \(A=(2,1)\), \(B=(7,6)\), \(C=(4,3)\), \(D=(8,2)\)?

**Lời giải:** A thuộc Q vì nằm trên góc biên; C nằm bên trong; B bị loại vì \(y=6>5\); D bị loại vì \(x=8>7\). Kết quả **A, C**.

### Câu 2. Giao hai AABB

Cho \(A=[1,4]\times[0,3]\) và \(B=[4,8]\times[2,6]\). Chúng có giao theo biên đóng không? Giao là gì?

**Lời giải:** Trục \(x\) giao tại \(\{4\}\); trục \(y\) giao trên \([2,3]\). Do đó:

\[
A\cap B=[4,4]\times[2,3],
\]

không rỗng nhưng có diện tích bằng 0.

### Câu 3. Xác định AABB nhỏ nhất

Tính hộp bao của \((2,5)\), \((-1,3)\), \((4,-2)\) và \((0,1)\).

**Lời giải:** Giá trị min/max của \(x\) là \(-1,4\), của \(y\) là \(-2,5\). Vậy:

\[
\operatorname{AABB}=[-1,4]\times[-2,5].
\]

### Câu 4. Hộp có chứa một hộp khác?

Đặt \(A=[0,6]\times[0,6]\), \(B=[2,5]\times[1,4]\) và \(C=[-1,2]\times[1,4]\). Hộp nào được A chứa hoàn toàn?

**Lời giải:** \(B\subseteq A\), vì min của B không nhỏ hơn min A và max B không lớn hơn max A trên cả hai trục. \(C\not\subseteq A\), vì \(x_{\min}(C)=-1<0\).

### Câu 5. Hình thật và hộp bao

Một đoạn thẳng từ \((0,0)\) tới \((10,10)\) có AABB \([0,10]\times[0,10]\). Nó có giao với \(Q=[0,1]\times[9,10]\) không?

**Lời giải:** **AABB giao Q**, vì Q nằm trong hộp bao. Nhưng điểm trên đoạn thẳng thỏa \(y=x\), nên trong vùng có \(x\le1\), \(y\ge9\), không thể có điểm nào trên đoạn. **Đoạn thẳng thật không giao Q**. Đây là false positive của bộ lọc hộp bao.

### Câu 6. Khoảng cách Euclid

Cho \(q=(0,0)\), \(p=(3,4)\), \(r=(2,2)\). Điểm nào gần q hơn?

**Lời giải:** \(D_2^2(q,p)=3^2+4^2=25\), còn \(D_2^2(q,r)=2^2+2^2=8\). Vì \(8<25\), **r gần q hơn**. Không cần tính căn bậc hai để so sánh.

### Câu 7. MinDist từ điểm tới hộp

Cho \(q=(1,4)\) và \(B=[3,6]\times[2,5]\). Tính bình phương khoảng cách nhỏ nhất từ q tới B.

**Lời giải:** Trục \(x\): q ở trái B, \(\delta_x=3-1=2\). Trục \(y\): \(4\in[2,5]\), \(\delta_y=0\). Do đó \(\operatorname{minDist}_2^2=2^2+0^2=4\).

### Câu 8. Quy tắc prune

Đang tìm NN của q, đã có ứng viên với bình phương khoảng cách \(best^2=16\). Một nhánh có AABB với \(\operatorname{minDist}_2^2(q,B)=25\). Có thể bỏ nhánh không? Nếu minDist bằng 16 thì sao?

**Lời giải:** **Có thể bỏ** khi \(25>16\), vì mọi điểm trong nhánh cách q ít nhất 5, trong khi ứng viên hiện tại cách 4. Nếu minDist bằng 16, muốn bảo toàn quy tắc **tie theo ID** thì không được bỏ một cách tùy tiện; có thể còn điểm khác cùng khoảng cách nhưng ID tốt hơn.

### Câu 9. Gán ô grid

Với lưới gốc \((0,0)\), kích thước ô \(10\times10\), tính chỉ số ô của \((12,7)\), \((10,10)\) và \((-1,7)\).

**Lời giải:**

- \((12,7)\to(\lfloor1{,}2\rfloor,\lfloor0{,}7\rfloor)=(1,0)\).
- \((10,10)\to(1,1)\) theo nửa mở.
- \((-1,7)\to(\lfloor-0{,}1\rfloor,0)=(-1,0)\).

Không làm tròn về 0 khi tính chỉ số ô âm; phải dùng **floor**.

### Câu 10. Vì sao cần ID ngoài tọa độ?

Hai bản ghi A và B cùng ở \((3,5)\). Một lưới không gian chỉ lưu một giá trị theo khóa \((3,5)\) sẽ gây nguy cơ gì?

**Lời giải:** Nếu ghi đè, hệ thống có thể **mất một bản ghi**. Nên lưu **danh sách ID tại mỗi vị trí hoặc ô** hay một cấu trúc hỗ trợ nhiều bản ghi trùng tọa độ; khóa của bản ghi phải được phân biệt với khóa ô.

### Câu 11. k-d tree và độ phức tạp

Một k-d tree được xây cân đối bằng trung vị cho 100.000 điểm 2D. Có thể kết luận mọi truy vấn NN sẽ chỉ thăm \(O(\log n)\) nút không?

**Lời giải:** **Không.** Chiều cao của cây có thể là \(O(\log n)\), nhưng khi nhiều vùng không thể loại bằng cận dưới khoảng cách, phép NN phải kiểm tra nhiều nhánh và có thể gần \(O(n)\) trong trường hợp xấu.

### Câu 12. Quadtree có nhiều điểm trùng

Một quadtree tự chia khi ô vượt 8 điểm. Có 1000 bản ghi ở cùng vị trí \((5,5)\). Chia liên tục có tách riêng được chúng không?

**Lời giải:** **Không**, nếu mỗi lần chia các bản ghi vẫn rơi vào cùng một ô con. Cần giới hạn độ sâu/độ phân giải, bucket cho điểm trùng hoặc chính sách đặc biệt để tránh chia vô hạn.

### Câu 13. Dữ liệu thay đổi và hộp bao lỗi thời

Điểm P được chuyển từ \((2,2)\) tới \((50,50)\), nhưng AABB cây con vẫn là \([0,4]\times[0,4]\). Điều gì có thể xảy ra khi truy vấn quanh \((50,50)\)?

**Lời giải:** Chỉ mục có thể **bỏ cả nhánh** vì AABB cũ không giao vùng truy vấn mới, gây **false negative** — bỏ sót P. Phải cập nhật các hộp bao và vị trí chỉ mục hoặc xây lại chỉ mục.

### Câu 14. Số ô lưới trong nhiều chiều

Nếu chia mỗi trục thành 8 khoảng bằng nhau, số ô lý thuyết của lưới 2D, 3D và 6D lần lượt là bao nhiêu?

**Lời giải:** \(8^2=64\), \(8^3=512\), \(8^6=262\,144\). Số ô tăng rất nhanh theo số chiều, dù có thể chỉ lưu các ô đang có dữ liệu.

### Câu 15. Tọa độ địa lý và thứ tự trục

Một API yêu cầu \((longitude,latitude)\) nhưng một bản ghi được gửi theo \((latitude,longitude)\). Có thể khẳng định một chỉ mục AABB vẫn trả đúng địa điểm vì đều là hai số thực không?

**Lời giải:** **Không.** Hai trục có ý nghĩa khác nhau; đảo chúng tạo vị trí sai. Cần thống nhất thứ tự trục, CRS và metric. Nếu tìm khoảng cách mét, không dùng Euclid trên độ kinh/vĩ một cách máy móc.

### Câu 16. Chọn chỉ mục

Ba hệ thống: (a) game 2D gồm rất nhiều điểm di chuyển và truy vấn đối tượng gần nhau; (b) kho polygon địa chính cần tìm hình giao cửa sổ; (c) 500 điểm ít thay đổi và chỉ truy vấn hiếm. Chọn ứng viên ban đầu nào?

**Lời giải:** (a) có thể thử **uniform grid/spatial hashing** hoặc **quadtree** với chính sách cập nhật; (b) **R-tree** để lọc MBR, sau đó dùng kiểm tra polygon chính xác; (c) **quét tuyến tính** có thể đủ đơn giản và nhanh, chỉ dựng chỉ mục khi benchmark chứng minh cần thiết.

### Câu 17. Đầu ra \(k\) kết quả

Một chỉ mục trả 100.000 điểm thuộc cửa sổ Q. Có thể tuyên bố cả truy vấn, gồm việc gửi tất cả kết quả, tốn \(O(1)\) không?

**Lời giải:** **Không.** Chỉ riêng việc xuất \(k=100\,000\) điểm đã cần ít nhất \(\Omega(k)\) thời gian. Một độ phức tạp truy vấn phù hợp thường gồm phần tìm kiếm **cộng** chi phí xuất kết quả.

### Câu 18. Chọn metric phù hợp

Cho hai điểm \((0,0)\) và \((3,4)\). Vì sao có thể dùng khoảng cách Euclid 5 trong mặt phẳng mét nhưng không thể coi kết quả là 5 mét nếu tọa độ thực ra là kinh độ/vĩ độ theo độ?

**Lời giải:** Công thức Euclid 5 chỉ là khoảng cách theo **đơn vị tọa độ phẳng**. Với kinh độ/vĩ độ, các thành phần là **độ góc**, độ dài thật trên Trái Đất phụ thuộc vị trí và hình học địa cầu. Cần metric địa lý hoặc phép chiếu thích hợp.

## 24. Tổng kết

**Điểm** là vector tọa độ trong \(d\) chiều. **AABB** là tích các khoảng theo trục, được mô tả bằng min/max và dùng để kiểm tra nhanh **bao chứa**, **giao nhau** và **cận dưới khoảng cách**. Với hộp đóng:

\[
\boxed{p\in B\iff\forall i:\ lo_i\le p_i\le hi_i,}
\]

\[
\boxed{A\cap B\neq\varnothing\iff
\forall i:\ A.lo_i\le B.hi_i\ \land\ B.lo_i\le A.hi_i.}
\]

**Range query** tìm điểm trong vùng; **window query** tìm hình giao vùng; **radius/NN/kNN** dựa vào metric. Một chỉ mục không gian như lưới, k-d tree, quadtree hoặc R-tree giúp **bỏ qua cả nhóm đối tượng không thể là kết quả**, nhưng phải giữ AABB bao đúng dữ liệu và thực hiện **refinement** khi hình gốc không phải chính AABB.

Chi phí quét toàn bộ \(n\) điểm \(d\) chiều thường \(O(nd)\); chỉ mục có thể giảm đáng kể số đối tượng phải xét trong dữ liệu và truy vấn thuận lợi, song **không bảo đảm tốt nhất trong mọi trường hợp**. Số chiều, phân bố dữ liệu, vùng truy vấn, tỷ lệ cập nhật và mục tiêu p99 đều ảnh hưởng lựa chọn.

Khi thực hành, luôn xác định **quy ước biên**, **thứ tự trục**, **hệ tọa độ**, **đơn vị metric**, **ID tách khỏi tọa độ** và **chính sách cập nhật chỉ mục**. Chọn cấu trúc phù hợp không chỉ là chọn phép tìm nhanh, mà còn là **bảo đảm không bỏ sót dữ liệu** với chi phí thời gian và bộ nhớ phù hợp bài toán.
