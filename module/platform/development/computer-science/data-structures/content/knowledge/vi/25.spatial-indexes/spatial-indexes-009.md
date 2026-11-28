# So sánh phân chia điểm với phân chia vùng dữ liệu

Trong một hệ thống bản đồ, có thể đặt các cảm biến thành nhóm dựa vào **tọa độ của chính các điểm đang có**, hoặc chia **toàn bộ khu vực bản đồ** thành những ô và đưa mỗi cảm biến vào ô tương ứng. Cả hai đều tạo chỉ mục không gian, nhưng chúng đưa ra những quyết định rất khác nhau: ranh giới do **dữ liệu quyết định** hay do **miền không gian quyết định**, có tạo vùng rỗng không, điểm nằm đúng biên thuộc nhánh nào, và truy vấn phải đi qua bao nhiêu nhóm.

Một **k-d tree xây bằng trung vị** minh họa cách phân chia tập điểm theo dữ liệu; **PR-quadtree**, **octree** và **lưới đều** minh họa cách phân chia miền không gian. **R-tree** cung cấp một góc nhìn thứ ba: nhóm các đối tượng theo hộp bao, trong đó hộp của các nhóm anh em **có thể chồng lấn**. Không nên gọi cả ba cơ chế này là một kiểu “chia không gian” rồi áp dụng chung điều kiện định tuyến, cắt nhánh hoặc độ phức tạp.

Bài thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, hướng tới nền tảng cấu trúc dữ liệu, bất biến, thao tác, độ phức tạp thời gian–bộ nhớ và việc chọn cấu trúc phù hợp từng bài toán. Ta sẽ định nghĩa ba cách tổ chức, so sánh k-d tree với quadtree/grid và R-tree, đi qua ví dụ tính tay, các ranh giới khó, truy vấn phạm vi/láng giềng gần nhất, xử lý cập nhật, ví dụ Python độc lập và bài tập có lời giải.

> **Kết luận định hướng:** “Phân chia điểm” và “phân chia vùng” mô tả **điều đang được phân nhóm hoặc chia nhỏ**, chứ không phải hai tập thuật toán tuyệt đối đối lập. **K-d tree cũng tạo những miền hình học qua các mặt chia.** Khác biệt quan trọng là nó thường **chọn ranh giới từ tập điểm**, còn PR-quadtree chia **hình chữ nhật miền không gian theo quy tắc hình học**. R-tree không bắt buộc các hộp bao anh em rời nhau.

## 1. Bài toán và ba câu hỏi cần tách biệt

Cho tập bản ghi điểm hai chiều:

\[
P=\{(id_i,x_i,y_i)\mid i=1,\ldots,n\},
\]

trong đó mỗi **ID là duy nhất**, nhưng hai ID có thể có **cùng tọa độ**. Muốn dùng chỉ mục cho các phép toán:

- **Point lookup:** có bản ghi nào ở vị trí \((x,y)\), và gồm những ID nào?
- **Range reporting:** liệt kê điểm trong một cửa sổ hình chữ nhật \(Q\).
- **Range counting:** có bao nhiêu điểm trong Q?
- **Nearest neighbor:** bản ghi nào gần vị trí q nhất theo một metric đã định nghĩa?
- **Dynamic update:** chèn, xóa, di chuyển điểm trong lúc vẫn phục vụ truy vấn.

Trước khi chọn cấu trúc, phải trả lời ba câu hỏi khác nhau.

**Câu hỏi A — Phân nhóm tập đối tượng như thế nào?** Ví dụ: lấy trung vị theo x, chia tập ID thành hai nửa có lượng phần tử gần bằng nhau, rồi đệ quy. Đây là một dạng **phân chia theo điểm/dữ liệu** (*data-driven point partition*).

**Câu hỏi B — Phân hoạch miền hình học như thế nào?** Ví dụ: lấy miền \([0,16)\times[0,16)\), cắt ngang/dọc tại tọa độ 8 thành bốn phần tư, rồi chỉ chia tiếp ô có quá nhiều điểm. Đây là **phân chia vùng** (*space/region partition*).

**Câu hỏi C — Nhóm đối tượng và bao chúng bằng hộp như thế nào?** Ví dụ: đặt nhiều tòa nhà trong cùng node R-tree; MBR của hai node có thể chồng lấn. Đây là **phân nhóm đối tượng bằng vùng bao** (*object grouping*), không tương đương một phân hoạch miền thành các phần rời nhau.

Một chỉ mục có thể kết hợp các ý tưởng ấy. Phân chia điểm bằng median của k-d tree sinh ra **mặt phẳng tách không gian**; quadtree có thể chỉ tạo **node cho vùng có dữ liệu**; và R-tree có thể nhóm **hộp chữ nhật thay vì điểm**.

## 2. Định nghĩa chính xác: phân chia tập điểm và phân hoạch miền

### 2.1. Phân chia điểm theo khóa tọa độ

Tại một node có tập bản ghi \(S\), chọn trục \(j\) và pivot \(v\), ví dụ trung vị theo:

\[
\boxed{K_j(p)=(p_j,\operatorname{ID}(p)).}
\]

Ta phân thành các tập ID:

\[
\boxed{
\begin{aligned}
S_L&=\{p\in S:K_j(p)<K_j(v)\},\\
S_R&=\{p\in S:K_j(p)>K_j(v)\}.
\end{aligned}
}
\]

Pivot được lưu **ở node hiện tại**, còn mọi ID khác nằm đúng một trong hai cây con. Khi chọn trung vị, số phần tử trái/phải thường gần bằng nhau:

\[
\boxed{|S_L|=\lfloor |S|/2\rfloor,\quad
|S_R|=|S|-1-|S_L|.}
\]

Ví dụ này có ý nghĩa **cân bằng số bản ghi**, không bảo đảm các ô hình học được tạo có diện tích gần nhau. Nếu điểm tụ thành cụm rất nhỏ, ranh giới có thể nằm sát một mép của miền bản đồ.

**Điểm trùng tọa độ:** Nhờ khóa tổng hợp \((tọa\ độ,\ ID)\), những điểm có cùng tọa độ trục vẫn được chia ổn định theo ID. Vì thế ta chỉ được kết luận:

\[
\boxed{\forall p\in S_L,\ p_j\le v_j;\qquad
\forall p\in S_R,\ p_j\ge v_j.}
\]

Không được mặc định tất cả điểm bên trái có \(p_j<v_j\) nếu đang dùng tie-break ID.

### 2.2. Phân chia vùng hình học

Cho miền gốc \(\Omega\subseteq\mathbb R^2\). Một phép phân hoạch vùng tạo các miền con \(R_1,\ldots,R_b\) sao cho:

\[
\boxed{\Omega=\bigcup_{i=1}^b R_i}
\]

và, với quy ước biên phù hợp, các miền **không chung điểm thuộc về cả hai**:

\[
\boxed{R_i\cap R_j=\varnothing\quad(i\ne j).}
\]

Ví dụ một ô hình vuông \([0,16)\times[0,16)\) chia ở x=8 và y=8 thành:

\[
\begin{aligned}
R_{SW}&=[0,8)\times[0,8),\\
R_{SE}&=[8,16)\times[0,8),\\
R_{NW}&=[0,8)\times[8,16),\\
R_{NE}&=[8,16)\times[8,16).
\end{aligned}
\]

Các miền **nửa mở** bảo đảm điểm có x=8 hoặc y=8 được gán **chính xác một ô**. Điểm \((8,8)\) thuộc ô NE; điểm \((8,4)\) thuộc SE. Một điểm ở x=16 nằm ngoài miền gốc.

Trong PR-quadtree, ta thường **chỉ thực sự tạo node con có điểm**, thay vì lưu mọi ô rỗng. Nhưng **ranh giới vẫn do hình học miền quy định**, không được dịch theo trung vị tập điểm tại mỗi bước.

### 2.3. Phân nhóm hộp bao của R-tree

Mỗi nhóm \(G_i\) của các object-entry có:

\[
\boxed{B_i=\operatorname{MBR}\Bigl(\bigcup_{o\in G_i}
\operatorname{geom}(o)\Bigr).}
\]

Các nhóm ID có thể không giao nhau, nhưng **hai MBR hình học không bắt buộc rời nhau**:

\[
G_i\cap G_j=\varnothing
\;\centernot\Rightarrow\;
B_i\cap B_j=\varnothing.
\]

Vì vậy R-tree là một **cấu trúc nhóm dữ liệu theo vùng bao có thể overlap**, không phải một phân hoạch miền \(\Omega\) thành các ô rời nhau kiểu PR-quadtree.

## 3. Bảng đối chiếu nhanh ba triết lý tổ chức

| Tiêu chí | K-d tree dựng theo median điểm | PR-quadtree / octree chia vùng | R-tree nhóm MBR |
| --- | --- | --- | --- |
| Đối tượng điển hình | Điểm \(d\) chiều | Điểm hoặc bucket điểm trong miền xác định | Điểm, hình hộp, đường, đa giác qua MBR |
| Quyết định tách | Trục + trung vị dữ liệu | Tâm hình học của ô, hoặc quy tắc phân vùng | Phân nhóm entry khi overflow |
| Số nhánh con điển hình | 2 | 4 ở 2D; 8 ở 3D | Đa nhánh, tới M entry |
| Ranh giới phụ thuộc dữ liệu? | **Có**, nếu pivot theo median | **Không** đối với vị trí ô; có đối với ô nào được chia | **Có**, theo MBR của nhóm dữ liệu |
| Hình học các miền anh em | Có thể tạo các cell rời nhau qua luật biên | Các ô rời nhau qua luật biên | MBR có thể chồng lấn |
| Một bản ghi điểm nằm ở | Một pivot/node hoặc bucket, theo quy ước | Một ô lá đối với điểm, nếu luật biên đúng | Một object-entry lá trong R-tree cơ bản |
| Vùng trống có cần node? | Không | Có thể bỏ node ô rỗng | Không có ô trống theo nghĩa phân hoạch |
| Cân bằng số điểm | Median tĩnh thường tốt | Không được bảo đảm; cụm dày có thể rất sâu | Min/max-fill theo entry, không đồng nghĩa phân bố hình học đều |
| Truy vấn phạm vi | Đi nhiều nhánh khi Q cắt mặt chia/AABB | Đi những ô giao Q | Có thể đi nhiều MBR anh em chồng lấn |
| Truy vấn NN | AABB/mặt chia làm cận dưới | Cận tới miền ô hoặc AABB điểm | Cận tới MBR, refine hình thật |
| Cập nhật | Chèn có thể làm lệch; rebuild | Chia/gộp các ô; root có thể mở rộng | ChooseSubtree/split/CondenseTree |

**Đọc bảng theo cấu trúc cụ thể.** K-d tree có nhiều biến thể (pivot lưu node, bucket ở lá, sliding midpoint), quadtree cũng có PR-quadtree, point quadtree, region quadtree và compressed quadtree. Không áp dụng mọi tính chất cho mọi biến thể chỉ vì cùng tên họ cấu trúc.

## 4. Ví dụ một tập điểm nhỏ, hai cách chia khác nhau

Cho miền:

\[
\Omega=[0,16)\times[0,16)
\]

và tám bản ghi:

| ID | Điểm \((x,y)\) | Nhận xét |
| --- | --- | --- |
| A | \((1,1)\) | Góc dưới trái |
| B | \((2,3)\) | Góc dưới trái |
| C | \((3,2)\) | Góc dưới trái |
| D | \((4,4)\) | Gần tâm cụm trái |
| E | \((12,2)\) | Dưới phải |
| F | \((13,3)\) | Dưới phải |
| G | \((12,12)\) | Trên phải |
| H | \((13,13)\) | Trên phải |

### 4.1. Chia tập điểm theo median x

Sắp theo x rồi ID (tăng dần):

Chọn trung vị ở vị trí giữa, ví dụ E nếu lấy phần tử chỉ số 4 của dãy:

~~~text
Sắp theo (x, ID):
A(1,1) B(2,3) C(3,2) D(4,4)
E(12,2) G(12,12) F(13,3) H(13,13)

                     E(12,2), axis=x
                     /              \
             4 điểm trái         3 điểm phải
             A B C D             G F H
~~~

Pivot E có x=12. **Đường chia theo x nằm tại x=12**, rất lệch về phía phải của miền \([0,16)\), nhưng hai tập nhánh có số điểm 4 và 3, cân bằng về **số bản ghi**.

### 4.2. Chia vùng quadtree ở giữa miền

Đầu tiên cắt miền tại x=8 và y=8:

~~~text
 y=16  +-----------------+-----------------+
       |                 |  NE: G, H        |
       |       NW        |                  |
 y=8   +-----------------+-----------------+
       |  SW: A B C D    |  SE: E F         |
       |                 |                  |
 y=0   +-----------------+-----------------+
       x=0               x=8              x=16
~~~

Ranh giới **x=8, y=8** không đổi dù bốn điểm A–D tụ ở góc trái. Nếu bucket của một lá chứa tối đa 2 điểm, SW còn 4 điểm sẽ phải chia tiếp; SE chứa 2 điểm, NE chứa 2 điểm có thể là lá.

**Điểm khác nhau:** median k-d tree ưu tiên **tách tập điểm gần đều**, còn quadtree vùng ưu tiên **ranh giới ô có quy tắc hình học ổn định**; cụm nào dày sẽ bị chia sâu hơn.

## 5. Ranh giới và bất biến: nơi nhiều lỗi bắt đầu

Hai cách chia đều cần quy tắc rõ cho điểm **nằm đúng đường chia**.

### K-d tree: khóa theo (tọa độ trục, ID)

Nếu pivot có tọa độ x=8 và ID P:

\[
K_x(p)=(p_x,id(p)).
\]

Điểm \((8,4)\) có ID đứng **trước P** có thể nằm bên trái; điểm \((8,4)\) có ID đứng **sau P** có thể nằm bên phải. Vì thế một truy vấn đóng:

\[
Q=[8,10]\times[0,5]
\]

**không được bỏ nhánh trái chỉ vì Q bắt đầu tại x=8**. Nhánh trái vẫn có thể chứa điểm x=8 được Q nhận.

Nếu chỉ prune theo mặt chia x=s và query đóng:

- Bỏ nhánh trái khi \(Q.x_{\min}>s\).
- Bỏ nhánh phải khi \(Q.x_{\max}<s\).
- Khi Q **chạm** s, phải bảo thủ, trừ khi có metadata mạnh hơn như AABB của nhánh.

### Quadtree vùng: khoảng nửa mở [lo,hi)

Một ô \([x_0,x_1)\times[y_0,y_1)\) chứa:

\[
\boxed{x_0\le x<x_1,\quad y_0\le y<y_1.}
\]

Cho \(m_x=(x_0+x_1)/2\), \(m_y=(y_0+y_1)/2\), với số thực đầu vào trong khoảng an toàn. Luật định tuyến:

- x nhỏ hơn \(m_x\): **trái**; x bằng hoặc lớn hơn \(m_x\): **phải**.
- y nhỏ hơn \(m_y\): **dưới**; y bằng hoặc lớn hơn \(m_y\): **trên**.

Nhờ vậy một điểm trên cả hai đường chia đi tới **đúng một ô NE**. Không được cho nó vào cả bốn ô chỉ vì các hình vẽ có vẻ chung cạnh.

### Q truy vấn đóng nhưng miền quadtree nửa mở

Ta có thể dùng cửa sổ truy vấn đóng:

\[
Q=[a_x,b_x]\times[a_y,b_y].
\]

Một ô quadtree \([l_x,h_x)\times[l_y,h_y)\) **chắc chắn không chứa điểm nào thuộc Q** khi có một trục i thỏa:

\[
\boxed{h_i\le a_i\quad\lor\quad l_i>b_i.}
\]

Chú ý bất đẳng thức **khác nhau** ở hai phía: \(h_i=a_i\) cho ô kết thúc **ngay trước** cận trái Q, nên ô không giao Q. Nhưng \(l_i=b_i\) cho ô bắt đầu tại **cận phải Q**, có thể chứa điểm bằng b, nên ô **có thể giao**.

Đây là điều kiện prune theo **miền ô nửa mở**, không phải điều kiện giao hai AABB **đóng** của điểm dữ liệu. Với AABB điểm đóng, ngoài Q khi \(hi_i<a_i\) hoặc \(lo_i>b_i\).

> **Nguyên tắc chung:** Định tuyến và prune phải dựa trên **bất biến và quy ước biên thực sự của chỉ mục**, không chỉ một công thức giao hộp học thuộc.

## 6. K-d tree: chia dữ liệu, đồng thời tạo các điều kiện hình học

K-d tree là ví dụ điển hình về **phép chia phụ thuộc tập điểm**, nhưng không phải một cấu trúc “không có vùng”. Mỗi pivot tách các bản ghi theo tọa độ ở một trục và đồng thời tạo một ràng buộc nửa không gian cho những hậu duệ.

### Node và cấu trúc

Một cách cài đặt k-d tree tĩnh có node:

| Trường | Ý nghĩa |
| --- | --- |
| pivot | Một bản ghi điểm, gồm ID và tọa độ |
| axis | Trục đang chia, ví dụ x hoặc y |
| left/right | Hai tập con được chia bằng khóa (tọa độ trục, ID) |
| bbox_lo/bbox_hi | AABB đóng bao mọi điểm của cây con, kể cả pivot |
| size | Số bản ghi dưới node nếu cần range counting |

Khi chọn trung vị mỗi lần, hai cây con có kích thước gần đều. Nếu mọi điểm đều trùng tọa độ \((4,4)\) nhưng có ID khác nhau, khóa tổng hợp vẫn cho phép chọn trung vị và dựng cây không cần cố tách một miền hình học không có bề rộng.

### Miền phân hoạch và AABB điểm khác nhau

**Miền phân hoạch (*split cell*):** tập vị trí hình học bị giới hạn bởi các mặt chia của tổ tiên. Nếu pivot chia x=s, một nhánh có miền nằm phía \(x\le s\), nhánh kia phía \(x\ge s\). Khi có điểm bằng s ở cả hai phía do tie ID, các **miền mô tả bằng bất đẳng thức không nghiêm ngặt có thể cùng chứa mặt biên**; ID mới xác định bản ghi thực thuộc nhánh nào.

**AABB điểm (*subtree bounding box*):** hộp đóng min/max của **các tọa độ điểm thật trong cây con**. Nó có thể nhỏ hơn split cell và phù hợp cho prune theo hình chữ nhật.

Ví dụ với một cây con chỉ chứa \((12,2)\) và \((13,3)\):

\[
\boxed{B_{\mathrm{subtree}}=[12,13]\times[2,3].}
\]

Nếu split cell của cây con còn kéo tới x=16 và y=16, AABB điểm vẫn có thể cắt tỉa tốt hơn vì không bao vùng rỗng ấy.

### Duyệt đúng với nhiều nhánh

Một truy vấn hình chữ nhật không thể chỉ theo nhánh “gần” pivot như tìm đúng khóa trong BST. Nếu Q cắt mặt chia, hai bên đều có thể chứa điểm. Cả khi Q chỉ nằm về một phía nhưng chạm mặt chia, những điểm đúng tọa độ chia có thể ở phía còn lại do tie ID.

Sử dụng **AABB của từng cây con** giúp đơn giản hóa: một node được bỏ nếu hộp đóng của nó không giao Q; nếu giao, kiểm tra pivot và các con. Đó là điều kiện prune vừa dễ chứng minh vừa không phụ thuộc vào việc trục được chọn theo chu kỳ hay theo độ trải rộng.

## 7. PR-quadtree: chia miền và phân phối điểm vào bucket

**PR-quadtree** (*point-region quadtree*) có một vùng gốc xác định. Tại mỗi node, miền hình chữ nhật có thể được chia thành bốn hình chữ nhật con theo trung điểm trục x/y. Mỗi điểm đi tới **một ô con** dựa trên vị trí.

### Các bất biến

1. **Root extent** được khai báo rõ, ví dụ \([-8,16)\times[-8,16)\); mọi điểm trong chỉ mục phải nằm trong miền ấy.
2. Bốn vùng con chia toàn bộ vùng cha, không bỏ khoảng trống và không chồng lấn **theo quy tắc nửa mở**.
3. Mỗi điểm của node cha được chuyển tới **đúng một** node con.
4. **Lá** chứa một bucket điểm; nếu bucket vượt ngưỡng, có thể chia tiếp, trừ khi đã tới giới hạn độ sâu hoặc không thể chia bằng số học hiện tại.
5. Một node trong không cần chứa bản ghi điểm nếu thiết kế quy định tất cả bản ghi nằm ở lá.
6. Không bắt buộc tạo các ô rỗng. Có thể chỉ lưu con **không rỗng**, nhưng định tuyến hình học vẫn phải dựa trên bốn vùng chuẩn.

### Vì sao một cụm có thể tạo nhánh sâu?

Giả sử miền là \([0,1024)\times[0,1024)\), bucket chứa tối đa 2 điểm, nhưng 100 điểm đều nằm trong ô rộng cỡ 1 gần \((1,1)\). Khi chia ở trung điểm, nhiều lần liên tiếp cả 100 điểm vẫn đi vào cùng một góc.

Chiều sâu tăng theo **mức độ chi tiết hình học cần để tách dữ liệu**, chứ không theo số phần tử trung vị. Nó có thể lớn hơn \(O(\log n)\) nếu tọa độ rất sát nhau trong một miền gốc lớn.

### Điểm trùng tọa độ: phải có điều kiện dừng

Nếu 100 ID đều ở \((3,3)\), mọi lần chia hình học đều đưa chúng vào **cùng một ô**. Không có phép chia tại trung điểm nào tách được các tọa độ hoàn toàn giống nhau.

Các cách xử lý hợp lệ:

- Cho phép **bucket lá chứa hơn capacity** đối với điểm cùng tọa độ.
- Giới hạn **max_depth**, giữ bucket lá dù chưa đạt giới hạn số điểm.
- Gộp một vị trí thành **một khóa tọa độ chứa nhiều ID**, nếu API phân biệt rõ số vị trí và số bản ghi.
- Dùng **compressed quadtree** để nén các chuỗi node đơn nhánh; nhưng vẫn phải có chính sách cho tọa độ trùng nhau.

Không được tiếp tục đệ quy mãi chỉ vì bucket còn quá đầy. Mã Python ở phần thực hành dùng **max_depth** và dừng sớm nếu mọi điểm có cùng tọa độ.

### Không phải mọi “quadtree” đều là PR-quadtree

**Point quadtree** cổ điển có thể lấy chính một điểm để tạo bốn góc phân chia (ranh giới phụ thuộc dữ liệu). **Region/PR-quadtree** chia miền theo trung điểm vùng. Vì vậy khi nói “quadtree chia vùng”, bài đang nói rõ về **PR-quadtree theo miền**, không áp dụng tùy tiện cho mọi biến thể mang tên quadtree.

## 8. Lưới đều và spatial hash: một cực khác của phân chia vùng

Với ô vuông cạnh \(s>0\), gốc lưới ở \((o_x,o_y)\), điểm \((x,y)\) được đưa vào bucket:

\[
\boxed{
i=\left\lfloor\frac{x-o_x}{s}\right\rfloor,\quad
j=\left\lfloor\frac{y-o_y}{s}\right\rfloor.
}
\]

Đây là **phân chia vùng cố định**: ranh giới không di chuyển vì điểm mới đến hay cũ biến mất. Ta có thể lưu:

- **Mảng 2D** nếu miền hữu hạn, kích thước lưới nhỏ và khá dày.
- **Bảng băm từ (i,j) tới bucket** nếu miền rộng hoặc thưa (*spatial hash*).

### Tọa độ âm và ô biên

Với \(s=4,o_x=o_y=0\):

| Điểm | Chỉ số \((i,j)\) |
| --- | --- |
| \((0,0)\) | \((0,0)\) |
| \((3.9,0)\) | \((0,0)\) |
| \((4,0)\) | \((1,0)\) |
| \((-0.1,0)\) | \((-1,0)\) |
| \((-4,0)\) | \((-1,0)\) |

**Phải dùng floor, không phải cắt phần thập phân về 0.** Nếu dùng int(-0.1/4) trong một ngôn ngữ có ép kiểu cắt về 0, điểm \((-0.1,0)\) sẽ bị đưa nhầm vào ô 0 thay vì ô -1.

### Lưới khác quadtree ở đâu?

Grid có **độ phân giải không đổi** \(s\) trên toàn miền. Quadtree có thể chia **riêng** những vùng mật độ cao, giữ vùng thưa ở ô lớn; nó là một **phân vùng thích nghi theo độ sâu** dù vị trí đường chia ở mỗi ô được xác định từ hình học.

Grid thường đơn giản khi cần nhiều truy vấn địa phương với ô có kích thước liên quan **bán kính tương tác**. Nếu mật độ rất không đều hoặc kích thước vật thể chênh nhau lớn, một kích thước ô duy nhất có thể khiến một vài bucket rất đông hoặc một truy vấn phải đi qua quá nhiều ô.

## 9. R-tree: nhóm dữ liệu theo MBR, không phân chia vùng rời nhau

Một R-tree có thể nhóm các **hình chữ nhật** hoặc hình học phức tạp. Mỗi node trong lưu entry \((MBR,child)\); mỗi lá lưu \((MBR,ID)\) cho đối tượng.

Với hai nhóm đối tượng khác nhau:

\[
G_A\cap G_B=\varnothing,
\]

nhưng MBR:

\[
B_A=[0,6]\times[0,6],\qquad
B_B=[4,10]\times[4,10]
\]

vẫn giao trên \([4,6]\times[4,6]\).

Một Q nhỏ quanh \((5,5)\) giao **cả hai child-MBR**, nên truy vấn phải kiểm tra cả hai nhánh. Chọn đúng một con dựa trên tọa độ tâm Q **không an toàn**.

### Chèn/split trong R-tree

Khi chèn object mới E, R-tree có thể chọn một nhánh gây **độ tăng diện tích MBR** nhỏ nhất:

\[
\boxed{
\Delta A(B,E)=
\operatorname{area}(\operatorname{cover}(B,E))
-\operatorname{area}(B).
}
\]

Nếu node vượt sức chứa M, nó **split tập entry thành hai nhóm** đạt min-fill, không nhất thiết split miền bản đồ tại trung điểm hay trung vị điểm.

Hai node con mới có thể tiếp tục có MBR chồng lấn. Điều này khác với quadtree, nơi các **ô con có quy tắc sở hữu rời nhau**, và với k-d tree, nơi các **tập ID được chia bởi một khóa trục**.

### Dữ liệu hình học không phải hộp chữ nhật

Khi object là polygon, đường hoặc tam giác, MBR giao Q chỉ cho **ứng viên**:

\[
\operatorname{geom}(o)\cap Q\ne\varnothing
\ \Rightarrow\
\operatorname{MBR}(o)\cap Q\ne\varnothing.
\]

Chiều ngược lại không đúng nói chung. Muốn kết quả cuối chính xác, cần kiểm tra hình học thật ở lá. Đối với tập **điểm** như ví dụ của bài, bounding box suy biến tại chính điểm, nên phép lọc ở lá là chính xác.

## 10. Truy vấn phạm vi: ba cách chọn phần dữ liệu để xét

Cho cửa sổ **đóng**:

\[
\boxed{Q=[a_x,b_x]\times[a_y,b_y].}
\]

Điểm \(p=(x,y)\) thuộc Q khi:

\[
\boxed{a_x\le x\le b_x,\quad a_y\le y\le b_y.}
\]

### K-d tree: prune AABB của tập điểm

~~~text
KD_RANGE(node,Q):
    if node is None: return
    if closed_AABB(node) does not intersect Q: return

    if pivot(node) is inside Q: emit pivot
    KD_RANGE(node.left,Q)
    KD_RANGE(node.right,Q)
~~~

Nếu AABB node không giao Q, **không điểm nào dưới node có thể thuộc Q**. Nếu AABB giao, kiểm tra pivot và con; chỉ từ điều kiện giao hộp không thể suy ra tất cả pivot đều hợp lệ.

### PR-quadtree: prune ô miền nửa mở

~~~text
QUAD_RANGE(node,Q):
    if node is None: return
    if half_open_region(node) cannot contain a point in Q: return

    if node is a leaf:
        for p in its bucket:
            if p inside Q: emit p
    else:
        for every nonempty child:
            QUAD_RANGE(child,Q)
~~~

Vì mỗi điểm nằm trong đúng một ô lá, không cần duyệt lại điểm ở tổ tiên nếu node trong không chứa điểm. Nhưng phải kiểm tra **mọi ô có khả năng giao Q**, chứ không chỉ ô chứa **tâm Q**.

### R-tree: prune MBR của nhóm

~~~text
RANGE_RTREE(node,Q):
    if MBR(node) does not intersect Q: return

    if node is a leaf:
        for each object entry:
            if MBR(entry) intersects Q: emit candidate
    else:
        for each child entry:
            if child.MBR intersects Q:
                RANGE_RTREE(child,Q)
~~~

Đối với polygon, ứng viên qua MBR cần **refine**. Đối với point, MBR của mỗi point suy biến nên ứng viên là điểm thuộc Q khi predicate đúng.

### Chứng minh cắt tỉa an toàn

Điểm chung của ba cách là có một **miền bao chứng minh được** cho mọi điểm hoặc hình học thật dưới nhánh. Gọi \(S_v\) là tập dữ liệu nhánh v, \(B_v\) là miền bao.

\[
\boxed{S_v\subseteq B_v.}
\]

Nếu:

\[
\boxed{B_v\cap Q=\varnothing,}
\]

thì suy ra \(S_v\cap Q=\varnothing\), nên bỏ toàn bộ nhánh **không mất kết quả**.

Điều khác nhau nằm ở cách tạo \(B_v\) và quy tắc biên: AABB điểm **đóng**, PR-quadtree có thể dùng ô **nửa mở**, R-tree dùng MBR nhóm **đóng** và các MBR anh em **có thể overlap**.

## 11. Nearest neighbor: cận khoảng cách tới miền thay cho duyệt tất cả điểm

Với điểm truy vấn \(q=(q_x,q_y)\) và khoảng cách Euclid, một láng giềng gần nhất là:

\[
\boxed{
p^*\in\arg\min_{p\in P}
\sqrt{(p_x-q_x)^2+(p_y-q_y)^2}.
}
\]

Nếu có nhiều ID cùng khoảng cách, ví dụ trong bài chọn **ID nhỏ hơn** để phá hòa. Ta có thể so bằng bình phương khoảng cách:

\[
\boxed{D_2^2(q,p)=(p_x-q_x)^2+(p_y-q_y)^2.}
\]

### Cận dưới tới một AABB đóng

Với hộp \([l_x,h_x]\times[l_y,h_y]\), định nghĩa:

\[
\delta_x=\max(l_x-q_x,0,q_x-h_x),
\qquad
\delta_y=\max(l_y-q_y,0,q_y-h_y).
\]

Khi đó:

\[
\boxed{\operatorname{minDist}^2(q,B)=\delta_x^2+\delta_y^2.}
\]

Mọi điểm của hộp cách q **ít nhất** căn bậc hai của cận trên. Nếu đã có điểm tốt nhất ở khoảng cách bình phương \(best^2\), một nhánh có:

\[
\boxed{\operatorname{minDist}^2(q,B)>best^2}
\]

được **bỏ an toàn**.

Không tự thay dấu \(>\) bằng \(\ge\) nếu còn phải tìm ID nhỏ hơn **ở cùng khoảng cách**.

### K-d tree

Dùng AABB điểm của cây con hoặc cận theo mặt chia. AABB điểm thường chặt hơn khi có một cụm nhỏ trong một miền phân hoạch rộng. Duyệt nhánh có cận minDist nhỏ hơn trước để sớm có ứng viên tốt, rồi bỏ nhánh có cận vượt best.

### PR-quadtree

Dùng **miền hình học của ô** làm hộp cận dưới. Khi miền ô là nửa mở \([l,h)\), có thể tính khoảng cách tới **bao đóng \([l,h]\)** để có cận dưới bảo thủ. Bao đóng có thể chứa mặt biên không thuộc ô, khiến cận lỏng hơn, nhưng **không làm prune sai**.

Ví dụ ô \([0,4)\times[0,4)\) không chứa điểm có x=4. Khoảng cách từ q=(4,2) tới **bao đóng** bằng 0, dù mọi điểm thực trong ô có thể cách q dương. Đây là cận dưới an toàn, không phải kết luận có điểm cách 0.

### R-tree

Dùng cận minDist tới **MBR của nhánh**. Khi đối tượng là polygon/đường, minDist tới MBR có thể thấp hơn khoảng cách tới **hình thật**; lúc đánh giá ứng viên ở lá cần khoảng cách hình học thực theo metric nghiệp vụ.

### Kết luận về nearest neighbor

Ba cấu trúc đều có thể dùng **branch-and-bound** dựa trên cận khoảng cách, nhưng:

- K-d tree có thể có **hộp điểm chặt**.
- Quadtree có **ô không gian cố định hoặc phân cấp**, đôi khi rộng hơn cụm điểm.
- R-tree có **MBR nhóm**, các nhánh có thể chồng lấn nhiều.

Số nhánh thực sự được loại là kết quả của **phân bố dữ liệu và độ chặt cận**, không suy trực tiếp từ việc một cấu trúc được gọi là tree hay grid.

## 12. Counting và reporting: lợi ích của metadata khác nhau

Một truy vấn phạm vi có thể hỏi:

- **Reporting:** liệt kê mọi ID trong Q.
- **Counting:** chỉ trả số ID.
- **Existence:** có ít nhất một ID thuộc Q hay không.

Nếu một cây con có **AABB điểm nằm trọn trong Q**, tất cả điểm dưới nó đều hợp lệ. Khi đó:

\[
\boxed{\operatorname{count}(subtree,Q)=size(subtree).}
\]

Với k-d tree, có thể lưu **subtree size** tại mỗi node. Với quadtree, cũng có thể lưu số điểm của **ô và các ô con**; nếu **toàn bộ ô miền** nằm trong Q, size của ô được cộng trực tiếp. Nếu Q chỉ chứa **AABB dữ liệu** chặt hơn ô, cũng có thể nhận trọn khi metadata này được lưu và được chứng minh đúng.

**Không nhầm reporting và counting:** Reporting vẫn phải xuất từng ID:

\[
\boxed{T_{\mathrm{report}}=\Omega(k)}
\]

với \(k\) kết quả. Counting được phép cộng size trong \(O(1)\) cho cây con **được Q chứa trọn**, nếu size đúng và không có bộ lọc thuộc tính khác.

R-tree cũng có thể lưu **aggregate count** theo cây con, nhưng một Q chứa hoàn toàn MBR cha chỉ cho phép cộng số object trong nhánh đối với predicate thích hợp, ví dụ tất cả object-MBR nằm trong Q. Nếu đang đếm **polygon giao Q** và Q chứa **MBR cha**, tất cả polygon trong nhánh đúng là giao Q **nếu hình gốc không rỗng và nằm trong Q**. Ngược lại, nếu Q chỉ giao một phần MBR cha, không thể dùng aggregate count.

Nếu có xóa/tombstone, size phải phản ánh **số ID còn sống**. Nếu có điều kiện “chỉ đếm cảm biến đang hoạt động”, size tổng quát chưa đủ; cần metadata theo thuộc tính hoặc lọc từng bản ghi.

## 13. Cập nhật động: những cấu trúc nào phải đổi ranh giới?

### K-d tree tĩnh theo median

Nếu xây từ toàn bộ điểm ban đầu, các pivot được chọn theo trung vị. Khi chèn thêm điểm:

1. Có thể đi theo khóa (tọa độ, ID) để tìm vị trí.
2. Mở rộng AABB và cập nhật subtree size dọc đường.
3. Nhưng **không tự động giữ được median cân bằng** như cây ban đầu.

Chèn nhiều điểm theo một vùng có thể làm cây lệch, tăng chiều cao và số nhánh phải duyệt. Các hướng xử lý là **rebuild theo lô**, rebuild cây con, hoặc dùng cấu trúc động được thiết kế riêng.

Đổi tọa độ một ID bằng cách sửa trực tiếp pivot có thể phá bất biến trái/phải. Một cách an toàn về ý tưởng là **xóa vị trí cũ + chèn vị trí mới** và duy trì metadata.

### PR-quadtree

Ranh giới chia ô đã được quyết định bởi miền, không cần chọn lại pivot mỗi lần có điểm mới.

- Chèn một điểm vào **ô lá tương ứng**.
- Nếu bucket quá đông, **chia ô thành bốn** và phân phối lại.
- Khi xóa, nếu các con đủ thưa, có thể **gộp ô** và giảm số node.
- Khi điểm nằm **ngoài root extent**, có thể từ chối, mở rộng root theo quy tắc mới hoặc rebuild trong một miền gốc rộng hơn.

Đây là một lợi ích khi miền bản đồ ổn định. Nhưng nếu dữ liệu gồm rất nhiều điểm sát nhau, cây vẫn có thể rất sâu và cần **max_depth/bucket ngoại lệ/compression**.

### Lưới đều hoặc spatial hash

Với một điểm di chuyển từ ô \((i,j)\) sang ô \((k,\ell)\), có thể:

1. Xóa ID khỏi bucket cũ.
2. Chèn ID vào bucket mới.
3. Xóa bucket hash rỗng nếu muốn.

Không cần tái tổ chức toàn bộ ranh giới lưới. Tuy nhiên một grid với cell size s không thích hợp có thể có bucket khổng lồ, gây quét tuyến tính trong bucket.

### R-tree

Chèn một object có MBR mới bằng ChooseSubtree; node tràn cần split. Khi xóa gây underflow có thể dùng CondenseTree và reinsert; khi di chuyển object, MBR tổ tiên có thể phải mở rộng/thu hẹp.

**Ranh giới MBR là dữ liệu dẫn dắt**, nên update có thể làm đổi grouping và overlap. Một node cha có MBR **quá nhỏ, không còn bao đủ object**, có thể khiến truy vấn bỏ nhánh sai. MBR quá rộng vẫn an toàn nhưng giảm hiệu năng.

### Tóm tắt update

| Thao tác | K-d tree median | PR-quadtree | Spatial hash | R-tree |
| --- | --- | --- | --- | --- |
| Chèn | Theo split key, cập nhật bbox; có thể mất cân bằng | Tìm ô, chia bucket nếu cần | Thêm vào bucket theo chỉ số | ChooseSubtree, có thể split |
| Xóa | Cần xử lý bất biến pivot; có thể rebuild | Xóa khỏi bucket, có thể gộp | Xóa khỏi bucket | Underflow/CondenseTree |
| Di chuyển | Có thể cần remove+insert | Chuyển ô nếu vượt ranh | Chuyển bucket nếu cần | Xóa/chèn lại hoặc cập nhật MBR nhất quán |
| Ranh giới hình học | Có thể giữ cũ, nhưng không còn tối ưu trung vị | Cố định theo miền ở từng cấp | Cố định theo lưới | MBR thay đổi theo nhóm object |

## 14. Độ phức tạp: tách chi phí xây chỉ mục và chi phí truy vấn

Đặt:

- \(n\): số ID điểm.
- \(d\): số chiều.
- \(h\): chiều cao cấu trúc.
- \(D\): giới hạn số lần quadtree chia từ root đến lá.
- \(V\): số node được xét thật sự khi truy vấn.
- \(k\): số kết quả được xuất.
- \(c\): số ô lưới phải xét trong một truy vấn.
- \(M\): fanout tối đa của R-tree.

### Bảng chi phí có điều kiện

| Cấu trúc | Xây dựng / lưu trữ | Truy vấn cửa sổ | Truy vấn NN | Ghi chú |
| --- | --- | --- | --- | --- |
| K-d tree median tĩnh, sort lại mỗi cấp | Build \(O(n\log^2n)\) khi d cố định; metadata \(O(nd)\) | \(O(dV+k)\), không sắp ID | \(O(dV)\) cho 1-NN DFS | \(V\le n\); worst-case có thể thăm mọi node |
| PR-quadtree bucket, max depth D | Phân phối điểm qua tối đa D cấp, \(O(nD)\) theo cách cài đặt đơn giản; node không rỗng có thể đến \(O(nD)\) | \(O(V+k')\) với \(k'\) là số điểm kiểm tra ở các bucket thăm | \(O(V+k')\) nếu tính khoảng cách từng điểm ở lá | \(D\) phụ thuộc độ phân giải và giới hạn số học; không mặc định \(O(\log n)\) |
| Spatial hash/grid thưa | Trung bình \(O(n)\) xây bucket với giả thiết hash tốt; lưu \(O(n+b)\) cho b bucket | \(O(c+k')\) với c ô xét và \(k'\) điểm kiểm tra | Phụ thuộc mở rộng ô và cận dừng | Có thể có bucket rất đông; worst-case không tránh O(n) |
| R-tree | Build động phụ thuộc M, split; dữ liệu 2D \(O(n)\) node/entry khi M cố định | \(O(V+E_V+k)\) cho MBR rectangle | MinDist tới MBR, phụ thuộc số nhánh | Overlap khiến phải mở nhiều nhánh dù h nhỏ |

**Ghi chú:** Một chương trình thực tế có thể sắp kết quả theo ID, thêm \(O(k\log k)\); còn truy vấn polygon cần thêm chi phí kiểm tra hình gốc.

### Cận chuyên biệt của k-d tree

Trong mô hình **k-d tree cân bằng theo phân hoạch trực giao chuẩn**, có kết quả kinh điển cho orthogonal range reporting ở d chiều cố định:

\[
\boxed{O(n^{1-1/d}+k).}
\]

Trong 2D:

\[
\boxed{O(\sqrt n+k).}
\]

Cận này gắn với **mô hình xây cây và giả thiết phân hoạch tương ứng**; nó không phải cam kết áp dụng nguyên xi cho mọi biến thể, mọi cập nhật động, mọi xử lý trùng tọa độ hoặc mọi cách lưu AABB.

### Tại sao quadtree có thể sâu dù ít điểm?

Nếu hai điểm \(p_1,p_2\) nằm rất sát nhau trong miền gốc cực lớn, phép chia **theo trung điểm vùng** có thể đưa cả hai vào cùng góc qua nhiều cấp. Với tọa độ liên tục, không có cận chiều sâu theo **chỉ n** nếu không đặt thêm giả thiết về độ phân giải, khoảng cách tối thiểu giữa các điểm, min cell size hoặc max_depth.

### Tại sao k-d tree median có thể có cell rất méo?

Median cân bằng **số điểm**, không cân bằng **thể tích miền**. Nếu điểm nằm gần một cạnh, pivot vẫn nằm gần cạnh đó. Không thể suy ra mọi cell k-d tree có aspect ratio tốt hoặc mọi nearest-neighbor query đều nhanh.

### Mọi cấu trúc đều có trường hợp xấu

Một truy vấn phạm vi trả tất cả n điểm phải xuất:

\[
\boxed{\Omega(n)}
\]

thao tác đầu ra. NN exact có thể phải xét nhiều nhánh nếu cận dưới quá lỏng. Tên cấu trúc “tree” hay “hash” không đảm bảo một kết quả tức thời không phụ thuộc phân bố dữ liệu.

## 15. Sự đánh đổi giữa miền gốc, độ phân giải và số chiều

### Miền gốc của quadtree

Nếu root extent quá rộng so với dữ liệu, phần lớn phép chia ban đầu chỉ đưa toàn bộ điểm vào cùng một góc, sinh ra **chuỗi một con** trước khi tách được các điểm.

Nếu root extent quá nhỏ, điểm ngoài miền bị từ chối hoặc bắt buộc **mở rộng root**. Việc mở rộng phải giữ các ranh giới con và tính đúng cho các điểm đã chèn.

### Kích thước ô grid

Nếu s quá lớn, nhiều điểm dồn vào một bucket. Nếu s quá nhỏ, một query rộng phải xét quá nhiều ô; hash map thưa giảm bộ nhớ cho ô rỗng nhưng không tự giảm chi phí **liệt kê các ô trong vùng Q**.

### Kích thước MBR đối tượng R-tree

Nếu đối tượng lớn và dài, MBR có thể bao phần lớn không gian. R-tree không thể làm MBR nhóm nhỏ hơn **hình học mà nó phải chứa**. Khi nhiều object lớn giao nhau, chồng lấn có phần là đặc trưng dữ liệu, không thể loại hết bằng split.

### Khi số chiều tăng

PR-octree 3D có **8 nhánh** mỗi lần chia; một quadtree tổng quát \(d\) chiều có thể cần **\(2^d\) ô** sau một lần chia đầy đủ. Duy trì node cho mọi ô sẽ trở nên tốn kém khi d cao, nên thường cần cấu trúc thưa hoặc chiến lược khác.

K-d tree vẫn có **2 nhánh mỗi node** ở mọi d, nhưng cận khoảng cách và số vùng phải xét có thể kém chọn lọc ở không gian nhiều chiều (*curse of dimensionality*). Không nên mặc định lựa chọn phù hợp cho 2D vẫn tối ưu cho vector hàng trăm chiều.

## 16. Chọn cấu trúc theo workload thay vì theo tên

| Tình huống | Ứng viên nên thử | Tại sao |
| --- | --- | --- |
| Nhiều điểm 2D/3D, dữ liệu ít đổi, truy vấn NN/range thường xuyên | K-d tree median, PR-quadtree | Có cơ hội prune theo hộp/cell, cân nhắc độ phân bố |
| Vùng bản đồ hữu hạn, điểm di chuyển và mật độ thay đổi cục bộ | PR-quadtree hoặc lưới thích nghi | Ranh giới miền rõ, cập nhật bucket và chia/gộp tại chỗ |
| Hệ thống game nhiều vật thể nhỏ, tìm các phần tử gần trong bán kính cố định | Uniform grid/spatial hash | Chỉ số bucket đơn giản theo cell size liên quan bán kính |
| Nhiều polygon, đường, MBR có kích thước khác nhau | R-tree/R*-tree | Nhóm object có diện tích bằng MBR; broad phase trước refine |
| Tập dữ liệu n nhỏ, query hiếm, cập nhật rất thường xuyên | Quét tuyến tính | Tránh overhead xây/bảo trì chỉ mục |
| Không gian cực lớn nhưng chỉ vài ô có dữ liệu | Spatial hash thưa/quadtree chỉ lưu ô có điểm | Không cần cấp phát bộ nhớ cho mọi ô rỗng |
| Query gần như luôn lấy hết điểm | Quét tuần tự hoặc scan phần lớn dữ liệu | Chi phí xuất \(k\) có thể áp đảo lợi ích prune |
| Dữ liệu nhiều chiều, chấp nhận sai số | Thử chỉ mục ANN chuyên biệt | Đo độ chính xác/recall và độ trễ, giữ brute force làm chuẩn |

**Không có lựa chọn thắng tuyệt đối.** Ngay trong một nhóm bài toán, kết quả còn phụ thuộc kích thước ô, kích thước bucket, phân bố cụm, tỷ lệ query/update, cache locality và I/O. Hãy dùng baseline quét tuyến tính để kiểm chứng, rồi benchmark nhiều cấu hình.

## 17. Python: chung dữ liệu, hai cách chia — k-d tree và PR-quadtree

Ví dụ dưới đây dùng **Python 3.10+**, thư viện chuẩn và **hai chỉ mục tĩnh**. K-d tree xây median, mỗi node chứa một pivot và AABB điểm. PR-quadtree dùng một **miền gốc nửa mở**, chia ô theo trung điểm, lưu ID trong bucket lá.

Để so được tính đúng của hai cấu trúc, cả hai hỗ trợ:

- **Range query đóng** trả danh sách ID sắp từ điển.
- **1-NN Euclid** trả ID gần nhất, phá hòa bằng ID.
- **ID duy nhất**, nhưng **tọa độ có thể trùng**.
- Kiểm tra bất biến bằng hàm validate.

Hai cây **không cần có hình dạng giống nhau** và không cần trả ID theo cùng thứ tự duyệt. Việc sắp ID cuối cùng trong range query chỉ nhằm làm kết quả có thứ tự ổn định để đối chiếu; thao tác sắp cộng thêm \(O(k\log k)\).

~~~python
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Point:
    id: str
    x: float
    y: float


def parse_points(records):
    """Trả các điểm 2D, giữ mỗi ID đúng một lần."""
    seen = set()
    points = []
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
    return points


@dataclass(frozen=True)
class ClosedWindow:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def __post_init__(self):
        values = (self.xmin, self.ymin, self.xmax, self.ymax)
        if not all(isfinite(v) for v in values):
            raise ValueError("Biên Q phải hữu hạn")
        if self.xmin > self.xmax or self.ymin > self.ymax:
            raise ValueError("Cận Q không hợp lệ")

    def contains(self, p: Point) -> bool:
        return (
            self.xmin <= p.x <= self.xmax
            and self.ymin <= p.y <= self.ymax
        )

    def intersects_data_bbox(self, lo, hi) -> bool:
        """MBR từ dữ liệu là hộp ĐÓNG, kể cả khi suy biến."""
        return not (
            hi[0] < self.xmin or lo[0] > self.xmax
            or hi[1] < self.ymin or lo[1] > self.ymax
        )

    def may_hit_halfopen_region(self, lo, hi) -> bool:
        """Region [lo,hi) có thể chứa một điểm thuộc Q đóng?"""
        return not (
            hi[0] <= self.xmin or lo[0] > self.xmax
            or hi[1] <= self.ymin or lo[1] > self.ymax
        )


def dist_sq(q, p: Point) -> float:
    return (q[0] - p.x) ** 2 + (q[1] - p.y) ** 2


def min_dist_sq(q, lo, hi) -> float:
    """Khoảng cách² tới hộp đóng; là cận dưới cho dữ liệu trong hộp."""
    dx = max(lo[0] - q[0], 0.0, q[0] - hi[0])
    dy = max(lo[1] - q[1], 0.0, q[1] - hi[1])
    return dx * dx + dy * dy


def checked_query(q):
    values = tuple(float(v) for v in q)
    if len(values) != 2 or not all(isfinite(v) for v in values):
        raise ValueError("q phải có hai tọa độ hữu hạn")
    return values


# PHẦN A — K-D TREE: chia theo median của tập điểm.
@dataclass
class KDNode:
    point: Point
    axis: int
    left: KDNode | None
    right: KDNode | None
    lo: tuple[float, float]
    hi: tuple[float, float]
    size: int


class MedianKDIndex:
    def __init__(self, records):
        self.root = self._build(parse_points(records), depth=0)

    def _build(self, points, depth):
        if not points:
            return None

        axis = depth % 2
        points = sorted(
            points,
            key=lambda p: (
                p.x if axis == 0 else p.y, p.id
            ),
        )
        mid = len(points) // 2
        pivot = points[mid]
        left = self._build(points[:mid], depth + 1)
        right = self._build(points[mid + 1:], depth + 1)

        lo = [pivot.x, pivot.y]
        hi = [pivot.x, pivot.y]
        size = 1
        for child in (left, right):
            if child is None:
                continue
            size += child.size
            for i in (0, 1):
                lo[i] = min(lo[i], child.lo[i])
                hi[i] = max(hi[i], child.hi[i])

        return KDNode(
            pivot, axis, left, right,
            tuple(lo), tuple(hi), size
        )

    def range_ids(self, window: ClosedWindow) -> list[str]:
        hits = []

        def visit(node):
            if node is None:
                return
            if not window.intersects_data_bbox(node.lo, node.hi):
                return
            if window.contains(node.point):
                hits.append(node.point.id)
            visit(node.left)
            visit(node.right)

        visit(self.root)
        return sorted(hits)

    def nearest_id(self, raw_query) -> str | None:
        q = checked_query(raw_query)
        best = None       # Cặp (distance², ID).

        def visit(node):
            nonlocal best
            if node is None:
                return
            bound = min_dist_sq(q, node.lo, node.hi)
            if best is not None and bound > best[0]:
                return

            candidate = (dist_sq(q, node.point), node.point.id)
            if best is None or candidate < best:
                best = candidate

            children = [
                child for child in (node.left, node.right)
                if child is not None
            ]
            children.sort(
                key=lambda child: min_dist_sq(
                    q, child.lo, child.hi
                )
            )
            for child in children:
                visit(child)

        visit(self.root)
        return None if best is None else best[1]

    def validate(self) -> bool:
        """Kiểm tra mọi split key, bbox và subtree size."""
        seen = set()

        def walk(node, constraints):
            if node is None:
                return []

            if node.point.id in seen:
                raise AssertionError("ID xuất hiện hơn một lần")
            seen.add(node.point.id)

            for axis, boundary, is_left in constraints:
                current = (
                    node.point.x if axis == 0 else node.point.y,
                    node.point.id,
                )
                if is_left and not current < boundary:
                    raise AssertionError("Sai phân hoạch nhánh trái")
                if not is_left and not current > boundary:
                    raise AssertionError("Sai phân hoạch nhánh phải")

            pivot_key = (
                node.point.x if node.axis == 0 else node.point.y,
                node.point.id,
            )
            descendants_left = walk(
                node.left,
                constraints + [(node.axis, pivot_key, True)],
            )
            descendants_right = walk(
                node.right,
                constraints + [(node.axis, pivot_key, False)],
            )
            all_points = (
                [node.point] + descendants_left + descendants_right
            )

            lo = (
                min(p.x for p in all_points),
                min(p.y for p in all_points),
            )
            hi = (
                max(p.x for p in all_points),
                max(p.y for p in all_points),
            )
            if node.lo != lo or node.hi != hi:
                raise AssertionError("AABB dữ liệu bị sai")
            if node.size != len(all_points):
                raise AssertionError("Subtree size không đúng")
            return all_points

        walk(self.root, [])
        return True
~~~

### Giải thích phần k-d tree

**Chọn median:** Sort theo \((x,ID)\) ở cấp chẵn và \((y,ID)\) ở cấp lẻ, chọn phần tử giữa. Pivot không xuất hiện lần nữa trong hai con; số ID được chia gần đều. **Không chia miền theo trung điểm hình học**.

**AABB:** Tính bottom-up từ tọa độ pivot và các hộp con. Mọi điểm trong cây con nằm trong **hộp đóng** này; nên dùng phép giao hộp đóng với query đóng.

**NN:** Tính cận dưới đến AABB; khi cận lớn hơn best² mới prune. Xét các con theo cận tăng dần để có khả năng tìm best tốt sớm. Kết quả phá hòa bằng ID; hai điểm trùng tọa độ không bị gộp.

**Validate:** Thu tất cả điểm dưới mỗi node để so min/max, size và khóa phân hoạch tại mọi tổ tiên. Đây là kiểm tra học thuật, không phải thao tác cần chạy sau mọi query ở production.

## 18. Python: PR-quadtree phân chia hình chữ nhật miền

Phần dưới **nối tiếp mã ở mục 17**; dùng lại Point, ClosedWindow, parse_points, dist_sq, min_dist_sq và checked_query. Cây PR-quadtree xây tĩnh từ một tập điểm trong miền gốc đã biết, chỉ tạo các con **có điểm**, nhưng mỗi con luôn tương ứng **một trong bốn vùng hình học chuẩn**.

Mỗi lá chứa tối đa **capacity** điểm, trừ các trường hợp không thể tách thêm vì:

- Đã tới giới hạn **max_depth**.
- Mọi điểm có **cùng tọa độ**, dù ID khác nhau.
- Trung điểm float không còn nằm nghiêm ngặt giữa hai biên, nên một phép chia nữa sẽ không làm tiến triển.

Đây là những quy tắc dừng cần thiết để ví dụ không đệ quy vô hạn.

~~~python
@dataclass
class QuadNode:
    lo: tuple[float, float]
    hi: tuple[float, float]
    points: list[Point]
    children: list[QuadNode]
    size: int

    @property
    def is_leaf(self):
        return len(self.children) == 0


class RegionQuadIndex:
    def __init__(
        self,
        records,
        extent=(0.0, 0.0, 16.0, 16.0),
        capacity=2,
        max_depth=20,
    ):
        if (type(capacity) is not int or capacity < 1
                or type(max_depth) is not int or max_depth < 0):
            raise ValueError("capacity>=1 và max_depth>=0")

        x0, y0, x1, y1 = (float(v) for v in extent)
        if (not all(isfinite(v) for v in (x0, y0, x1, y1))
                or x0 >= x1 or y0 >= y1):
            raise ValueError("Root extent phải hữu hạn và có diện tích")

        points = parse_points(records)
        for p in points:
            if not (x0 <= p.x < x1 and y0 <= p.y < y1):
                raise ValueError("Điểm nằm ngoài root extent nửa mở")

        self.capacity = capacity
        self.max_depth = max_depth
        self.root = self._build(
            points, (x0, y0), (x1, y1), depth=0
        )

    @staticmethod
    def _quadrants(lo, hi):
        x0, y0 = lo
        x1, y1 = hi
        # Tránh (x0+x1)/2 để giảm nguy cơ overflow.
        mx = x0 + (x1 - x0) / 2.0
        my = y0 + (y1 - y0) / 2.0
        rectangles = [
            ((x0, y0), (mx, my)),  # SW, index 0
            ((mx, y0), (x1, my)),  # SE, index 1
            ((x0, my), (mx, y1)),  # NW, index 2
            ((mx, my), (x1, y1)),  # NE, index 3
        ]
        return mx, my, rectangles

    def _build(self, points, lo, hi, depth):
        def make_leaf():
            return QuadNode(
                lo, hi, list(points), [], len(points)
            )

        # Nhánh rỗng và bucket nhỏ đều là lá.
        if len(points) <= self.capacity:
            return make_leaf()

        # Dừng khi quá sâu hoặc mọi bản ghi cùng tọa độ.
        if depth >= self.max_depth:
            return make_leaf()
        if all(
            (p.x, p.y) == (points[0].x, points[0].y)
            for p in points
        ):
            return make_leaf()

        mx, my, regions = self._quadrants(lo, hi)
        if not (
            lo[0] < mx < hi[0] and lo[1] < my < hi[1]
        ):
            return make_leaf()

        groups = [[], [], [], []]
        for p in points:
            # Điểm trên đường chia thuộc nửa phải/trên.
            quadrant = int(p.x >= mx) + 2 * int(p.y >= my)
            groups[quadrant].append(p)

        children = []
        for i, group in enumerate(groups):
            if not group:
                continue  # Không lưu ô rỗng.
            child_lo, child_hi = regions[i]
            children.append(
                self._build(
                    group, child_lo, child_hi, depth + 1
                )
            )
        return QuadNode(lo, hi, [], children, len(points))

    def range_ids(self, window: ClosedWindow) -> list[str]:
        hits = []

        def visit(node):
            if not window.may_hit_halfopen_region(
                node.lo, node.hi
            ):
                return

            if node.is_leaf:
                for point in node.points:
                    if window.contains(point):
                        hits.append(point.id)
                return

            for child in node.children:
                visit(child)

        visit(self.root)
        return sorted(hits)

    def nearest_id(self, raw_query) -> str | None:
        q = checked_query(raw_query)
        best = None  # (distance², ID).

        def visit(node):
            nonlocal best
            # Bao đóng của ô nửa mở là một miền bao bảo thủ.
            bound = min_dist_sq(q, node.lo, node.hi)
            if best is not None and bound > best[0]:
                return

            if node.is_leaf:
                for point in node.points:
                    candidate = (dist_sq(q, point), point.id)
                    if best is None or candidate < best:
                        best = candidate
                return

            children = sorted(
                node.children,
                key=lambda child: min_dist_sq(
                    q, child.lo, child.hi
                ),
            )
            for child in children:
                visit(child)

        visit(self.root)
        return None if best is None else best[1]

    def validate(self) -> bool:
        """Kiểm tra vùng nửa mở, định tuyến và số ID."""
        seen = set()

        def walk(node, depth):
            if node.is_leaf:
                if node.children:
                    raise AssertionError("Lá không được có con")
                if (len(node.points) > self.capacity
                        and depth < self.max_depth):
                    # Bucket quá đầy vẫn hợp lệ khi mọi điểm
                    # cùng tọa độ hoặc không thể chia tiếp.
                    same = all(
                        (p.x, p.y) == (
                            node.points[0].x, node.points[0].y
                        )
                        for p in node.points
                    )
                    mx, my, _ = self._quadrants(
                        node.lo, node.hi
                    )
                    separable = (
                        node.lo[0] < mx < node.hi[0]
                        and node.lo[1] < my < node.hi[1]
                    )
                    if not same and separable:
                        raise AssertionError(
                            "Bucket quá đầy dù có thể chia"
                        )
                own_points = list(node.points)
            else:
                if node.points:
                    raise AssertionError(
                        "Nút trong không chứa pivot điểm"
                    )
                mx, my, expected_regions = self._quadrants(
                    node.lo, node.hi
                )
                used_regions = set()
                own_points = []
                for child in node.children:
                    region = (child.lo, child.hi)
                    if region not in expected_regions:
                        raise AssertionError("Sai miền ô con")
                    if region in used_regions:
                        raise AssertionError("Hai con cùng miền")
                    used_regions.add(region)
                    own_points.extend(walk(child, depth + 1))

                # Từng điểm phải thuộc vùng con tương ứng.
                for point in own_points:
                    expected_index = (
                        int(point.x >= mx)
                        + 2 * int(point.y >= my)
                    )
                    expected = expected_regions[expected_index]
                    if expected not in used_regions:
                        raise AssertionError("Thiếu ô chứa điểm")

            for p in own_points:
                if not (
                    node.lo[0] <= p.x < node.hi[0]
                    and node.lo[1] <= p.y < node.hi[1]
                ):
                    raise AssertionError("Điểm nằm sai ô")

            if node.size != len(own_points):
                raise AssertionError("Sai số lượng điểm cây con")

            if node.is_leaf:
                for p in own_points:
                    if p.id in seen:
                        raise AssertionError("ID xuất hiện nhiều lần")
                    seen.add(p.id)
            return own_points

        collected = walk(self.root, 0)
        if len(collected) != len(seen):
            raise AssertionError("ID trùng hoặc bị mất")
        return True
~~~

### Đọc các điều kiện dừng

Giả sử capacity=2, max_depth=12 và có 20 ID cùng tọa độ (3,3). Đó là **20 bản ghi**, nhưng chỉ **một vị trí hình học**. Quadtree không thể tách chúng bằng đường chia vùng; ví dụ giữ cả 20 trong **một bucket lá**. Điều này không vi phạm tính đúng, nhưng cho thấy giới hạn capacity là mục tiêu của thuật toán, **không phải bất biến bắt buộc trong mọi ngoại lệ**.

### Vì sao quadtree không cần AABB điểm?

Mỗi node đã có một **miền ô hình học** được chứng minh chứa mọi điểm dưới node. Ta dùng chính miền này để prune, không nhất thiết lưu thêm min/max tọa độ thật. Đổi lại, miền có thể khá rộng so với điểm đang lưu và làm cận NN lỏng hơn.

Nếu ứng dụng muốn tăng tốc, có thể lưu thêm **AABB điểm chặt** ở quadtree như k-d tree. Khi đó **vùng phân hoạch** và **AABB dữ liệu** là hai metadata khác nhau; cả hai phải được cập nhật đúng khi chèn/xóa.

### Giới hạn số học và miền gốc

Đoạn mã dùng float để minh họa. Ngay cả tọa độ hữu hạn cũng có thể gặp overflow hoặc mất độ phân giải ở phép trừ, chia hay bình phương cho giá trị cực trị. Ví dụ giả định miền vừa phải để phép tính trung điểm tiến triển; khi không thể chia thêm, nó giữ nguyên bucket để tránh đệ quy vô hạn.

Point ngoài miền gốc bị **từ chối có chủ đích**. Trong hệ thống động, có thể chọn chính sách mở rộng root thay thế, nhưng phải thiết kế lại ranh giới và kiểm thử bản ghi cũ. Không được âm thầm đưa điểm ngoài extent vào một ô bất kỳ.

## 19. Python: kiểm thử cùng tập điểm, cùng truy vấn

Phần sau **nối tiếp** hai lớp MedianKDIndex và RegionQuadIndex. Nó cố tình dùng:

- Điểm nằm đúng **trục phân chia** \(x=8\), \(y=8\).
- Hai bản ghi cùng tọa độ \((8,8)\) nhưng khác ID.
- Query đóng có **chiều rộng/chiều cao bằng 0**.
- Query ngoài toàn bộ dữ liệu và query bao toàn bộ miền gốc.
- Hai cây có thể tổ chức khác nhau nhưng phải trả **cùng ID kết quả**.

~~~python
records = [
    ("A", 1, 1),
    ("B", 2, 3),
    ("C", 3, 2),
    ("D", 4, 4),
    ("E", 12, 2),
    ("F", 13, 3),
    ("G", 12, 12),
    ("H", 13, 13),
    ("I", 8, 8),   # Giao hai đường chia quadtree.
    ("J", 8, 4),   # Nằm đúng đường chia x.
    ("K", 8, 8),   # Khác ID nhưng trùng tọa độ I.
]

kd = MedianKDIndex(records)
quad = RegionQuadIndex(
    records,
    extent=(0.0, 0.0, 16.0, 16.0),
    capacity=2,
    max_depth=16,
)

assert kd.validate()
assert quad.validate()

# Truy vấn đóng chứa đúng điểm (8,8), nhận cả I và K.
q_at_boundary = ClosedWindow(8, 8, 8, 8)
assert kd.range_ids(q_at_boundary) == ["I", "K"]
assert quad.range_ids(q_at_boundary) == ["I", "K"]

# Quadtree định tuyến x=8 sang nửa phải,
# nhưng Q đóng [0,8] vẫn phải thấy các điểm có x=8.
left_window = ClosedWindow(0, 0, 8, 8)
assert kd.range_ids(left_window) == [
    "A", "B", "C", "D", "I", "J", "K"
]
assert quad.range_ids(left_window) == [
    "A", "B", "C", "D", "I", "J", "K"
]

# Q đóng tại điểm (4,4) nhận đúng D.
assert kd.range_ids(ClosedWindow(4, 4, 4, 4)) == ["D"]
assert quad.range_ids(ClosedWindow(4, 4, 4, 4)) == ["D"]

# Root quadtree nửa mở: (16,16) nằm ngoài.
assert quad.range_ids(ClosedWindow(16, 16, 16, 16)) == []

# 1-NN, tie theo ID, không gộp bản ghi trùng tọa độ.
assert kd.nearest_id((8, 8)) == "I"
assert quad.nearest_id((8, 8)) == "I"
assert kd.nearest_id((8, 4)) == "J"
assert quad.nearest_id((8, 4)) == "J"


def brute_range(rows, window):
    return sorted(
        item_id
        for item_id, x, y in rows
        if window.xmin <= x <= window.xmax
        and window.ymin <= y <= window.ymax
    )


def brute_nn(rows, query):
    if not rows:
        return None
    qx, qy = query
    return min(
        ((x - qx) ** 2 + (y - qy) ** 2, item_id)
        for item_id, x, y in rows
    )[1]


windows = [
    ClosedWindow(0, 0, 8, 8),
    ClosedWindow(8, 8, 8, 8),
    ClosedWindow(4, 4, 4, 4),
    ClosedWindow(8, 0, 16, 16),
    ClosedWindow(-1, -1, 20, 20),
    ClosedWindow(16, 16, 16, 16),
    ClosedWindow(50, 50, 60, 60),
]
queries = [
    (0, 0),
    (8, 4),
    (8, 8),
    (12, 12),
    (16, 16),
    (-2, -2),
]

for window in windows:
    expected = brute_range(records, window)
    assert kd.range_ids(window) == expected
    assert quad.range_ids(window) == expected

for query in queries:
    expected = brute_nn(records, query)
    assert kd.nearest_id(query) == expected
    assert quad.nearest_id(query) == expected

# Tất cả điểm cùng tọa độ: quadtree phải dừng, không đệ quy vô hạn.
duplicates = [
    (f"copy-{i:03d}", 3, 3)
    for i in range(30)
]
kd_duplicate = MedianKDIndex(duplicates)
quad_duplicate = RegionQuadIndex(
    duplicates,
    extent=(0, 0, 16, 16),
    capacity=2,
    max_depth=20,
)
assert kd_duplicate.validate()
assert quad_duplicate.validate()
assert len(
    quad_duplicate.range_ids(ClosedWindow(3, 3, 3, 3))
) == 30
assert quad_duplicate.nearest_id((3, 3)) == "copy-000"
assert kd_duplicate.nearest_id((3, 3)) == "copy-000"

# Tập rỗng vẫn hợp lệ.
empty_kd = MedianKDIndex([])
empty_quad = RegionQuadIndex([], extent=(0, 0, 16, 16))
assert empty_kd.validate()
assert empty_quad.validate()
assert empty_kd.range_ids(ClosedWindow(0, 0, 1, 1)) == []
assert empty_quad.range_ids(ClosedWindow(0, 0, 1, 1)) == []
assert empty_kd.nearest_id((5, 5)) is None
assert empty_quad.nearest_id((5, 5)) is None

# PR-quadtree từ chối điểm ngoài root extent.
try:
    RegionQuadIndex([("outside", 16, 4)],
                    extent=(0, 0, 16, 16))
    raise AssertionError("Phải từ chối điểm ngoài extent")
except ValueError:
    pass
~~~

### Điều gì được kiểm chứng?

1. **Bản ghi không mất/không trùng:** Mỗi ID xuất hiện đúng một lần trong kết quả range.
2. **Tọa độ trùng nhưng ID khác:** I và K được giữ riêng, NN phá hòa bằng ID.
3. **Ranh giới trùng đường chia:** Q đóng nhận điểm x=8/y=8, dù PR-quadtree định tuyến bằng ô nửa mở.
4. **Cửa sổ suy biến:** Q là một điểm vẫn có thể có nhiều ID.
5. **Hai cách chia khác nhau:** K-d tree và quadtree có hình dạng khác nhau nhưng kết quả phải giống quét tuyến tính.
6. **Miền quadtree:** Điểm ở cận trên x=16 bị loại theo root extent \([0,16)\).
7. **Không phân chia vô hạn:** 30 ID cùng tọa độ được xử lý bằng một bucket ngoại lệ.
8. **Tập rỗng:** Range rỗng và NN trả None.

Các lệnh assert chỉ là **ví dụ học thuật cho người đọc chạy**. Trong nhiệm vụ biên soạn STEP 4, tác giả **không thực thi Python hoặc vòng kiểm thử QA học thuật**; việc viết ra assert không phải bằng chứng đã chạy thành công.

## 20. Thiết kế benchmark để so hai cách chia

Một benchmark công bằng cần cho **cùng bộ dữ liệu và cùng query** chạy qua các chỉ mục khác nhau. Không nên kết luận từ một ví dụ nơi quadtree chia vừa đẹp hay median k-d tree chọn trúng trục thuận lợi.

### Nên thu những chỉ số nào?

| Chỉ số | Vì sao quan trọng |
| --- | --- |
| n, miền gốc, phân bố tọa độ | Dữ liệu quyết định chất lượng chia |
| k-d tree: chiều cao, số node, độ chặt AABB | Median không đồng nghĩa cell đẹp |
| Quadtree: độ sâu cực đại, số bucket, tỷ lệ bucket đầy | Độ sâu phản ánh mật độ/độ phân giải |
| Grid: cell size, số bucket có dữ liệu, bucket đông nhất | Một ô cố định có thể quá rộng/quá hẹp |
| R-tree: M/m, overlap MBR anh em, mức lấp đầy | Overlap tạo nhiều nhánh truy vấn |
| Số node hoặc ô được thăm mỗi Q | Công việc duyệt thực sự |
| Số point/object-entry kiểm tra | Khối lượng lọc ở lá/pivot |
| Số điểm kết quả k | Tránh nhầm chi phí xuất với chi phí tìm |
| Thời gian build và cập nhật | Giá phải trả để xây và duy trì chỉ mục |
| p50/p95/p99 độ trễ | Query bất lợi có thể ảnh hưởng trải nghiệm |
| Bộ nhớ, số trang I/O, cache miss | Cấu trúc con trỏ và ô khác nhau |

### Bộ dữ liệu nên dùng

**Phân bố đều:** Điểm rải đều trong miền; so việc quadtree chia ô và median k-d tree cân bằng số bản ghi.

**Một hoặc nhiều cụm:** Các cụm dày cách nhau bởi vùng trống rộng; quadtree có thể tạo nhánh sâu trong cụm, còn k-d tree median tách ID gần đều.

**Tất cả điểm trên một đường:** Ví dụ mọi \(y=4\). Nếu chọn trục y liên tục, k-d tree không có thông tin tọa độ mới để phân tách hình học, dù vẫn dùng ID để chọn pivot; quadtree cũng có nhiều ô không chứa điểm.

**Nhiều điểm trùng tọa độ:** Cần đánh giá số điểm/bucket, cách xử lý max_depth và tính đúng ID.

**Một vài outlier xa:** Outlier có thể làm root extent của quadtree phải rất lớn hoặc tạo AABB nhóm rộng trong R-tree; median k-d tree có thể vẫn cân về số điểm nhưng không cân về thể tích.

**Truy vấn điểm/đường suy biến:** Cực kỳ hữu ích để phát hiện điều kiện biên sai giữa hộp đóng và ô nửa mở.

**Truy vấn phạm vi rộng:** Khi k gần n, chi phí xuất đầu ra có thể áp đảo lợi ích cắt tỉa.

**NN gần đường chia:** Kiểm tra thuật toán không bỏ nhánh chỉ vì query ở phía đối diện.

### Cách làm benchmark có kiểm soát

1. Tạo một tập điểm với **ID và tọa độ cố định**, ghi rõ số chiều và miền.
2. Xác định rõ query là **hộp đóng hay nửa mở**, metric NN là Euclid hay metric khác.
3. Chạy brute-force để có kết quả chuẩn trên mọi query.
4. Xây k-d tree median và quadtree với nhiều cấu hình bucket/max_depth; grid với nhiều cell size nếu so thêm.
5. Kiểm tra **mọi kết quả bằng brute-force** trước khi đo tốc độ.
6. Lặp nhiều query đại diện cả vùng đông/rỗng, biên và trường hợp xấu.
7. Tách **thời gian xây**, **thời gian cập nhật** và **thời gian truy vấn**; báo cáo median và độ trễ đuôi.
8. Đo **node visits, bucket scans, số kết quả k, bộ nhớ** để hiểu nguyên nhân chậm/nhanh.

### Tại sao quadtree không luôn nhanh hơn k-d tree khi dữ liệu phân cụm?

Giả sử mọi điểm ở một vùng cực nhỏ trong miền gốc rộng. Một quadtree không nén có thể duyệt nhiều **node đơn nhánh** trước khi tới bucket. K-d tree median không cần lần lượt đi qua những bước chia miền rỗng; nó chia số điểm thành các tập gần đều. Nhưng quadtree có thể được **nén** hoặc root được chọn sát dữ liệu hơn để giảm nhược điểm ấy.

### Tại sao k-d tree không luôn tốt hơn grid khi điểm di chuyển?

Median tree được tối ưu lúc build; nhiều lần chèn/di chuyển có thể làm phân hoạch không còn cân bằng. Grid định tuyến điểm bằng công thức chỉ số ô cố định, nên cập nhật một điểm sang ô mới thường rẻ. Đổi lại, bucket quá đông hoặc query quá rộng có thể khiến grid phải kiểm tra nhiều điểm/ô.

**Kết luận benchmark:** Chọn cấu trúc theo tổng chi phí của **workload thực**, không chỉ độ sâu lý thuyết hoặc một truy vấn đẹp.

## 21. Những hiểu lầm thường gặp khi so sánh các chỉ mục

1. **“K-d tree phân chia điểm nên không chia không gian.”** Sai. Mỗi phép tách theo trục cũng tạo các miền hình học; điểm khác biệt là ranh giới thường lấy từ dữ liệu.
2. **“Quadtree luôn chia theo tọa độ của một điểm pivot.”** Sai với **PR-quadtree**: nó chia ô theo trung điểm miền. Có biến thể point quadtree dùng tọa độ điểm, nên cần gọi đúng loại.
3. **“K-d tree median tạo hai miền có diện tích bằng nhau.”** Sai. Nó cân bằng **số bản ghi**, không cân bằng diện tích.
4. **“Quadtree luôn chia dữ liệu thành bốn nhóm có số điểm gần bằng nhau.”** Sai. Một ô có thể chứa toàn bộ điểm, ba ô còn lại rỗng.
5. **“Mỗi node của quadtree luôn phải có đủ bốn con.”** Sai với cài đặt thưa; chỉ cần lưu các ô con có điểm và giữ quy tắc hình học đúng.
6. **“R-tree chia miền thành các ô không chồng lấn như PR-quadtree.”** Sai. MBR của các node con có thể giao nhau.
7. **“Hai MBR R-tree giao nhau chứng minh cùng một ID nằm ở hai nhánh.”** Sai. Hai nhóm ID khác nhau vẫn có hộp bao chồng lấn.
8. **“R-tree chỉ lưu điểm.”** Sai. Nó đặc biệt hữu ích cho những đối tượng có **kích thước**, như hình hộp, đường và polygon.
9. **“Hai điểm cùng tọa độ có thể tự gộp thành một bản ghi.”** Sai nếu ID khác nhau và query đang tìm bản ghi.
10. **“K-d tree chọn median trên một trục nên mọi điểm trái có tọa độ nghiêm ngặt nhỏ hơn.”** Sai khi tie bằng ID cho phép điểm cùng tọa độ chia sang hai phía.
11. **“Nếu Q đóng bắt đầu đúng mặt chia x=s, ta luôn bỏ được nhánh trái.”** Sai nếu trái có thể chứa điểm x=s.
12. **“Quadtree nên dùng hộp đóng cho cả bốn ô con và chèn điểm biên vào tất cả ô giao.”** Sai đối với **định tuyến mỗi điểm vào đúng một lá**. Dùng quy tắc nửa mở hoặc luật sở hữu biên tương đương.
13. **“Điểm x=8 phải vào ô trái khi chia [0,16) tại 8.”** Với luật [lo,hi) đã chọn, x=8 thuộc **ô phải**.
14. **“Truy vấn đóng Q có cận trên x=8 chỉ cần thăm ô trái [0,8).”** Sai. Q còn nhận điểm ở x=8, thuộc ô phải [8,16).
15. **“Ô quadtree [0,8) giao query đóng [8,10] tại x=8.”** Sai theo tập hợp: ô **không chứa x=8**, nên không giao Q trên trục x.
16. **“AABB dữ liệu đóng suy biến [4,4] là hộp rỗng.”** Sai: nó chứa vị trí x=4. Không dùng luật prune của ô nửa mở cho AABB đóng.
17. **“Truy vấn phạm vi chỉ cần đi ô quadtree chứa tâm cửa sổ.”** Sai. Q có thể phủ nhiều ô.
18. **“Quadtree có bốn nhánh là NN luôn nhanh hơn k-d tree có hai nhánh.”** Sai. NN phụ thuộc độ chặt cận, số ô thăm và phân bố dữ liệu.
19. **“Điểm nào thuộc bbox quadtree thì chắc chắn có bản ghi ở đó.”** Sai. Ô hình học có thể chứa nhiều khoảng trống.
20. **“Cận khoảng cách đến bao đóng của ô nửa mở có thể gây prune sai.”** Không, nếu nó thật sự bao toàn bộ điểm của ô. Nó chỉ có thể quá lỏng.
21. **“Nếu minDist² bằng best² thì có thể loại nhánh khi muốn ID nhỏ nhất.”** Sai. Nhánh còn có thể chứa điểm cùng khoảng cách và ID nhỏ hơn.
22. **“NN với tọa độ kinh/vĩ độ tính bằng Euclid sẽ tự cho kết quả gần nhất theo mét.”** Sai. Metric/hệ quy chiếu cần được xác định riêng.
23. **“Quadtree chia tiếp đến khi mọi bucket <=capacity dù tất cả ID ở cùng tọa độ.”** Có nguy cơ **không kết thúc**. Cần điều kiện dừng độ sâu/độ phân giải hoặc xử lý bucket trùng tọa độ.
24. **“Có thể đặt một điểm ngoài root extent vào quadtree mà không đổi cấu trúc.”** Sai nếu muốn giữ bất biến miền bao. Phải mở rộng root, rebuild hoặc từ chối.
25. **“Grid chỉ cần phép ép int để chia ô cho tọa độ âm.”** Sai nếu ép kiểu cắt về 0. Cần **floor** để xác định đúng ô nửa mở.
26. **“Một grid rất mịn luôn nhanh hơn grid thô.”** Sai. Query có thể cần duyệt quá nhiều ô và tốn overhead hash.
27. **“Một grid rất thô luôn tiết kiệm.”** Nó có thể tạo bucket khổng lồ, khiến mỗi truy vấn gần như quét toàn bộ điểm.
28. **“Sparse hash cấp phát bộ nhớ cho mọi ô trong toàn không gian.”** Không. Nó có thể chỉ lưu các ô **đang có dữ liệu**.
29. **“Chèn mới vào k-d tree median sẽ duy trì trung vị đúng ở mọi node.”** Sai nếu chỉ chèn theo split key mà không tái cân bằng/rebuild.
30. **“R-tree chèn luôn đi vào ô chứa tâm object.”** Sai. ChooseSubtree có thể tối ưu độ tăng diện tích MBR hay overlap.
31. **“Mọi R-tree query chỉ đi một đường root–lá.”** Sai. MBR có thể chồng lấn và Q giao nhiều nhánh.
32. **“R-tree trả polygon chính xác nếu MBR polygon giao Q.”** Sai. Cần bước **refine** hình học gốc.
33. **“Có một cấu trúc chỉ mục luôn bảo đảm mọi range query \(O(\log n)\).”** Sai với các cấu trúc đang xét; có thể có k=n kết quả, cần ít nhất \(\Omega(n)\) để xuất chúng.
34. **“Chiều cao thấp đồng nghĩa số node phải duyệt thấp.”** Sai nếu quadtree có nhiều ô giao Q hoặc R-tree có nhiều MBR overlap.
35. **“K-d tree median luôn có cell vuông vức.”** Sai. Median cân bằng số điểm, không giới hạn aspect ratio của cell.
36. **“Một quadtree root lớn luôn tốt hơn root nhỏ.”** Sai. Root lớn có thể tạo nhiều chuỗi một con trước khi đến vùng dày; root nhỏ lại có thể từ chối dữ liệu mới.
37. **“Với root half-open, điểm ở cận trên hi vẫn thuộc miền.”** Sai. \([lo,hi)\) loại cận trên.
38. **“Có thể đổi quy tắc biên mà không đổi code query.”** Sai. Điều kiện prune phải khớp việc định tuyến/bao vùng.
39. **“Tổng sibling-overlap của R-tree bằng số nhánh mở.”** Sai. Overlap area là thước đo hình học; những hộp chỉ chạm biên có overlap area 0 nhưng query đóng vẫn có thể mở nhiều nhánh.
40. **“Một Q với k=0 luôn nhanh.”** Sai. MBR/ô có thể giao Q dù bên trong không có điểm hợp lệ.
41. **“Subtree size đúng cho counting ngay cả khi các điểm đã bị xóa nhưng metadata chưa sửa.”** Sai. Size phải phản ánh ID hiện hành.
42. **“Đổi thứ tự xây/chèn chỉ mục được phép làm đổi tập kết quả đúng.”** Sai. Cấu trúc và hiệu năng có thể đổi, **predicate và tập dữ liệu** thì không.
43. **“Chỉ cần đầu vào float hữu hạn, mọi phép tính trung điểm/bình phương sẽ hữu hạn.”** Sai. Giá trị trung gian vẫn có thể tràn hoặc mất độ phân giải.
44. **“Nếu chọn k-d tree thì không cần quét tuyến tính làm đối chứng.”** Sai. Brute-force độc lập giúp phát hiện lỗi định tuyến/cắt nhánh và có thể nhanh cho dữ liệu nhỏ.

## 22. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Trung vị theo điểm và trung điểm theo miền khác nhau ra sao?

Cho miền \([0,16)\times[0,16)\) với x của các điểm là 1, 2, 3, 4, 12, 12, 13, 13. Đường chia đầu tiên của một PR-quadtree 2D ở đâu? K-d tree median chọn tọa độ pivot x nào nếu lấy phần tử chỉ số 4 (0-based) trong dãy đã sắp?

**Lời giải:** PR-quadtree cắt miền tại **x=8 và y=8**. K-d tree median theo x lấy phần tử thứ năm có **x=12**. Ranh giới quadtree theo hình học miền; pivot median theo phân bố điểm.

### Câu 2. Median có cân bằng thể tích không?

Một k-d tree chia 9 điểm thành hai nhóm 4 và 4, pivot 1; vị trí pivot nằm sát x=99 trong miền x từ 0 tới 100. Có thể kết luận hai cell có diện tích bằng nhau không?

**Lời giải:** **Không.** Median chỉ cân bằng số bản ghi. Hai phần miền theo x=99 có thể có bề rộng 99 và 1.

### Câu 3. Điểm trên đường chia quadtree

Miền gốc \([0,16)\times[0,16)\) chia tại \((8,8)\). Điểm \((8,8)\) thuộc góc phần tư nào nếu dùng luật nửa mở?

**Lời giải:** **NE**: x=8 thuộc nửa phải \([8,16)\), y=8 thuộc nửa trên \([8,16)\). Nó không thuộc SW/SE/NW.

### Câu 4. Điểm đúng cận trên root

Với root extent \([0,16)\times[0,16)\), hai điểm \((15,15)\) và \((16,4)\) có được nhận không?

**Lời giải:** \((15,15)\) **được nhận**. \((16,4)\) **nằm ngoài miền** vì x=16 bằng cận trên bị loại.

### Câu 5. Query đóng chạm ô bên phải

Q có miền x là \([0,8]\); một ô quadtree có x trong \([8,16)\). Có thể bỏ ô này chỉ từ thông tin x không?

**Lời giải:** **Không.** Q đóng nhận x=8, và ô phải cũng nhận x=8. Nó có thể chứa điểm thuộc Q.

### Câu 6. Query đóng bắt đầu ở biên trên của ô trái

Q có x trong \([8,10]\); một ô quadtree có x trong \([0,8)\). Có thể bỏ ô đó không?

**Lời giải:** **Có**, vì mọi điểm trong ô có x<8, còn Q yêu cầu x≥8. Điều kiện prune là \(region.hi_x\le Q.x_{\min}\).

### Câu 7. Query hộp đóng và AABB dữ liệu suy biến

Một k-d tree leaf chỉ có điểm (8,3), AABB là \([8,8]\times[3,3]\). Q đóng \([8,10]\times[0,5]\). Có được prune leaf do AABB rộng 0 không?

**Lời giải:** **Không.** Điểm \((8,3)\) thuộc Q. Hộp bao đóng suy biến vẫn có thể giao Q tại một điểm.

### Câu 8. Tie-break của median k-d tree

Pivot k-d tree chia theo x tại \(s=8\), ID M. Điểm P có x=8 và ID B (B đứng trước M). Theo khóa \((x,ID)\), P nằm về đâu?

**Lời giải:** **Trái**, vì \((8,\text{"B"})<(8,\text{"M"})\). Không được suy ra mọi điểm trái có x<8.

### Câu 9. Có thể bỏ nhánh k-d tree khi Q bắt đầu tại s?

Với pivot ở x=8 và Q đóng có miền x là \([8,12]\), có thể bỏ toàn bộ nhánh trái dựa riêng vào mặt chia x không?

**Lời giải:** **Không.** Nhánh trái có thể chứa điểm x=8 với ID nhỏ hơn pivot; Q vẫn nhận x=8. Cần điều kiện mạnh hơn hoặc kiểm tra AABB của nhánh.

### Câu 10. Grid với tọa độ âm

Grid có \(s=4\), gốc 0. Điểm \((-0.1,3)\) nằm ở cell chỉ số \((i,j)\) nào?

**Lời giải:** \(i=\lfloor-0.1/4\rfloor=-1\), \(j=\lfloor3/4\rfloor=0\). Cell là **(-1,0)**. Ép kiểu về 0 sẽ đưa nhầm x vào ô 0.

### Câu 11. Cùng tọa độ, khác ID

Hai điểm I và K cùng ở \((8,8)\). Query đóng chỉ gồm vị trí \((8,8)\) phải trả bao nhiêu bản ghi?

**Lời giải:** **Hai** ID I và K. Dữ liệu đang định danh **bản ghi**, không gộp mọi bản ghi có chung tọa độ.

### Câu 12. Quadtree với nhiều tọa độ trùng

Capacity=2 nhưng 100 ID cùng ở (3,3). Điều gì xảy ra nếu cứ chia vùng tới khi bucket nhỏ hơn hoặc bằng 2 mà không có điều kiện dừng?

**Lời giải:** Có thể **chia mãi** và không bao giờ phân tách được điểm vì mọi ID có cùng tọa độ. Cần max_depth, giới hạn độ phân giải hoặc cho một bucket đặc biệt chứa nhiều ID.

### Câu 13. K-d tree chia đều số điểm

Một node chứa 11 ID, chọn median ở vị trí 5 (0-based). Hai cây con chứa bao nhiêu ID?

**Lời giải:** **5 bên trái, 5 bên phải**, còn một ID là pivot. Nếu trùng tọa độ trục, tie ID vẫn cho phân chia này.

### Câu 14. R-tree chồng lấn

Hai nhóm R-tree có MBR \([0,6]\times[0,6]\) và \([4,10]\times[4,10]\). Query là một điểm (5,5). Cần đi xuống mấy nhánh nếu không có metadata nào khác?

**Lời giải:** **Cả hai**, vì Q giao cả hai MBR. Không được chọn một đường duy nhất chỉ vì đã vào một nhánh trước.

### Câu 15. Overlap không có nghĩa duplicate

Hai child-MBR của R-tree giao nhau. Có thể kết luận cùng một object-entry được lưu ở cả hai node không?

**Lời giải:** **Không.** Các node có thể chứa hai tập ID rời nhau nhưng MBR hình học chồng lấn.

### Câu 16. Polygon giao MBR nhưng không giao Q

Một tam giác có MBR lớn bao Q, nhưng Q nằm ở vùng ngoài tam giác. R-tree trả tam giác như ứng viên có hợp lệ không, và kết quả cuối cần làm gì?

**Lời giải:** Trả **ứng viên MBR** là hợp lệ. Sau bước **refine hình học tam giác thật**, phải loại nó nếu tam giác không giao Q.

### Câu 17. Tính cận NN tới AABB

Cho \(q=(1,4)\), hộp đóng \(B=[3,6]\times[2,5]\). Tính minDist² Euclid.

**Lời giải:** Trục x cách 2, trục y nằm trong khoảng nên cách 0:

\[
\boxed{\operatorname{minDist}^2=2^2+0^2=4.}
\]

Đây là cận dưới của các điểm trong B, không phải khẳng định đã có bản ghi cách q đúng 2.

### Câu 18. Cắt nhánh NN khi cận bằng best

Best hiện tại có dist²=9. Một ô quadtree có lower bound²=9. Nếu NN phá hòa theo ID, có được prune không?

**Lời giải:** **Không.** Ô ấy vẫn có thể chứa điểm cùng khoảng cách nhưng ID nhỏ hơn best. Điều kiện an toàn đơn giản là prune khi **bound²>best²**.

### Câu 19. Cận tới ô nửa mở

Ô \([0,4)\times[0,4)\), q=(4,2). Cận khoảng cách tới **bao đóng** của ô bằng bao nhiêu? Nó có thể nhỏ hơn khoảng cách thật tới mọi điểm lưu trong ô không?

**Lời giải:** Cận bằng **0** vì q nằm trên cạnh bao đóng. Nó có thể nhỏ hơn mọi khoảng cách tới điểm thật, nhưng vẫn là **cận dưới an toàn**, chỉ khiến duyệt thêm.

### Câu 20. Chi phí xuất kết quả

Một range query trả tất cả n=100.000 điểm. Có cấu trúc nào trong bài có thể xuất đầy đủ các ID trong \(O(\log n)\) không?

**Lời giải:** **Không.** Chỉ riêng việc xuất 100.000 ID đã cần \(\Omega(n)\) thao tác, bất kể cấu trúc.

### Câu 21. Vì sao quadtree có thể sâu hơn k-d tree?

Cho hai điểm cực sát nhau trong một miền gốc rất lớn. Với bucket capacity=1, quadtree có thể chia nhiều cấp trước khi tách chúng. K-d tree median đối với hai điểm cần tối đa bao nhiêu lần chọn pivot trên một đường tới lá?

**Lời giải:** K-d tree median cho hai điểm có một node pivot và một child-node, chiều sâu \(O(\log 2)\), không phụ thuộc độ gần tọa độ. Quadtree phụ thuộc **độ phân giải hình học** cần để điểm rơi vào ô khác nhau.

### Câu 22. Cập nhật cảm biến di chuyển

Một điểm trong spatial hash chuyển từ (3,3) sang (9,3) với cell size 4, gốc 0. Cần chuyển bucket nào?

**Lời giải:** (3,3) ở cell (0,0); (9,3) ở cell (2,0). Xóa ID khỏi **(0,0)** và thêm vào **(2,0)**. Không phải thay lại ranh giới lưới.

### Câu 23. Metadata size và đếm

Một cây con có size=120 và AABB điểm nằm hoàn toàn trong Q. Nếu chỉ cần đếm điểm, có thể trả bao nhiêu mà không duyệt từng điểm?

**Lời giải:** **120**, nếu size phản ánh đúng số bản ghi còn sống và predicate chỉ là thuộc Q. Reporting vẫn phải xuất từng ID.

### Câu 24. Chọn chỉ mục theo ba workload

(a) Một triệu điểm 2D ít thay đổi, hỏi NN; (b) nhiều nhân vật nhỏ di chuyển liên tục, tìm các phần tử trong ô gần vị trí; (c) hàng trăm nghìn đa giác và đường, hỏi giao một cửa sổ. Nêu cấu trúc đáng thử.

**Lời giải:** (a) **k-d tree median** hoặc quadtree phù hợp, so với brute-force; (b) **uniform grid/spatial hash** hoặc PR-quadtree động, chọn cell/bucket theo mật độ; (c) **R-tree/R\*-tree** dùng MBR lọc ứng viên rồi refine hình thật. Quyết định cuối dựa vào benchmark workload, không chỉ tên cấu trúc.

## 23. Tổng kết: so sánh đúng điều đang được chia

Có ba cách nhìn quan trọng:

**K-d tree median — chia tập điểm theo dữ liệu.** Tại mỗi node, chọn pivot/trục theo tọa độ điểm, phân ID thành hai tập gần bằng số lượng. Nó cũng tạo các ràng buộc hình học, nhưng **vị trí mặt chia phụ thuộc tập điểm**; median không đảm bảo các miền có diện tích bằng nhau. Với dữ liệu tĩnh ít chiều, AABB điểm có thể hỗ trợ prune range và NN hiệu quả.

**PR-quadtree — chia miền hình học theo ô.** Miền gốc được cắt thành bốn ô nửa mở theo trung điểm, rồi chỉ chia tiếp ô cần độ phân giải cao hơn. Định tuyến dựa trên **vị trí thuộc ô**, không dựa trên median. Mỗi điểm thuộc đúng một ô nếu quy tắc biên đúng, nhưng dữ liệu tập trung có thể khiến cây rất sâu hoặc bucket quá đông nếu không có điều kiện dừng.

**R-tree — nhóm đối tượng bằng MBR.** Một node chứa MBR bao dữ liệu của những nhánh con; hai MBR anh em **có thể chồng lấn**, khiến một query phải đi nhiều nhánh. Đây là cấu trúc đặc biệt phù hợp những object có kích thước như đường và polygon; MBR thường là bước lọc ứng viên, không thay thế predicate hình học thật.

Grid/spatial hash đứng ở phía **phân vùng cố định**: đơn giản cho cập nhật điểm, nhưng nhạy với cell size và mật độ bucket.

Tuy khác cơ chế xây dựng, các chỉ mục đều dựa vào một nguyên tắc đúng đắn:

\[
\boxed{
\text{Nếu miền bao của nhánh không thể giao Q,}
\quad\text{bỏ nhánh an toàn.}
}
\]

Với nearest neighbor, thay giao vùng bằng **cận dưới khoảng cách** tới miền bao; chỉ prune khi cận đã chứng minh **không thể thắng nghiệm tốt nhất hiện tại**.

**Quy trình chọn cấu trúc:** xác định điểm hay hình có diện tích, hệ tọa độ và quy tắc biên → xem dữ liệu tĩnh hay động, phân bố đều hay tập trung → chọn cách chia phù hợp và giới hạn độ sâu/bucket → triển khai predicate query cùng bất biến → đối chiếu với quét tuyến tính, đặc biệt ở biên/trùng tọa độ → đo số node/ô thăm, số điểm kiểm tra, độ trễ, bộ nhớ và chi phí cập nhật.

Một chỉ mục không gian tốt là chỉ mục **giữ đúng toàn bộ kết quả và giảm công việc trên workload thực**, không phải chỉ mục có sơ đồ cây đẹp nhất hoặc ít cấp nhất.
