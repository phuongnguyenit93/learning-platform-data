# Quadtree, octree và phân chia không gian theo vùng

Hãy tưởng tượng một bản đồ chứa hàng trăm nghìn vị trí. Một ô phố đông đúc có hàng nghìn điểm, nhưng nhiều vùng ngoại ô không có điểm nào. Nếu chia toàn bộ bản đồ thành các ô **cùng kích thước**, một ô trung tâm vẫn có thể quá đông, còn nhiều ô khác bị bỏ không. **Quadtree** giải quyết tình huống này bằng cách chỉ chia nhỏ **những vùng thực sự cần chi tiết hơn**. Trong không gian ba chiều, ý tưởng tương ứng là **octree**.

Bài học thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, nền tảng về cấu trúc dữ liệu, bất biến, thao tác và đánh đổi thời gian–bộ nhớ. Ta sẽ phân biệt các biến thể quadtree, xây dựng quy tắc chia vùng chính xác, mở rộng sang octree, phân tích tìm kiếm/chèn/xóa/truy vấn và lập trình ví dụ Python 2D lẫn 3D. Trọng tâm là hiểu **vì sao cắt tỉa cả vùng vẫn không làm bỏ sót kết quả**.

> **Thông điệp chính:** Quadtree và octree là các cấu trúc **phân chia không gian phân cấp**, không phải các cây luôn tự cân bằng. Hiệu quả của chúng phụ thuộc mật độ dữ liệu, kích thước vật thể, điều kiện chia và quy tắc ranh giới; trong trường hợp xấu, truy vấn vẫn có thể phải xét gần như toàn bộ dữ liệu.

## 1. Từ lưới đều đến phân hoạch thích nghi

Giả sử miền vuông \([0,16)\times[0,16)\) có 1.000 điểm: 950 điểm tập trung trong góc trên phải, 50 điểm rải rác nơi khác.

- **Lưới đều:** Chọn cạnh ô nhỏ để xử lý 950 điểm có thể làm xuất hiện rất nhiều ô rỗng ở các vùng khác.
- **Quadtree theo vùng:** Bắt đầu bằng **một miền gốc** rộng 16×16; chỉ chia vùng nào chứa quá nhiều điểm. Những vùng ít điểm giữ ô lớn, còn vùng góc trên phải được chia thành các ô nhỏ hơn.

~~~text
Lưới đều (minh họa ý tưởng):      Quadtree chia theo nhu cầu:

+---+---+---+---+              +---------------+-------+
|   |   |   | * |              |               |       |
+---+---+---+---+              |   vùng thưa   +---+---+
|   |   |   |***|              |               | * |***|
+---+---+---+---+              +---------------+---+---+
|   |   |   |***|              |               |   |***|
+---+---+---+---+              |    vùng thưa  +---+---+
|   |   |   |***|              |               | * |***|
+---+---+---+---+              +---------------+---+---+

* đại diện điểm; hình chỉ mang tính trực quan.
~~~

Không gian vẫn được chia thành các **miền hình học** như hình vuông, hình chữ nhật hay khối hộp. Sự khác biệt là **mức phân giải có thể thay đổi theo vị trí**: chỗ đông thì nhiều cấp, chỗ thưa thì ít cấp.

### Ba khái niệm nền tảng

**Nút vùng (region node):** một nút cây đại diện **một miền không gian** có biên được xác định rõ.

**Nút trong (internal node):** vùng đã được chia nhỏ và có các vùng con. Đối với quadtree chuẩn theo vùng 2D, phép chia tạo **bốn vị trí con**; đối với octree 3D tạo **tám vị trí con**.

**Nút lá (leaf):** vùng chưa chia tiếp; có thể chứa một bucket điểm, một trạng thái “rỗng/đặc” hoặc các đối tượng tùy biến thể.

**Chiều sâu** của nút là số lần phân chia từ vùng gốc đến vùng đó. Đừng nhầm nó với **số chiều tọa độ**: quadtree phân chia không gian 2 chiều nhưng bản thân cây có thể sâu hàng chục mức.

## 2. Quadtree theo vùng: chia một hình vuông thành bốn phần

Xét vùng gốc:

\[
R=[x_{\min},x_{\max})\times[y_{\min},y_{\max}).
\]

Ở đây sử dụng **khoảng nửa mở**: nhận biên trái/dưới, loại biên phải/trên. Cho:

\[
m_x=\frac{x_{\min}+x_{\max}}2,\qquad
m_y=\frac{y_{\min}+y_{\max}}2
\]

theo nghĩa trung điểm hình học; khi lập trình với số thực cần kiểm tra phép tính trung điểm vẫn nằm **nghiêm ngặt trong miền**.

Ta chia R thành bốn vùng con:

\[
\begin{aligned}
SW&=[x_{\min},m_x)\times[y_{\min},m_y),\\
SE&=[m_x,x_{\max})\times[y_{\min},m_y),\\
NW&=[x_{\min},m_x)\times[m_y,y_{\max}),\\
NE&=[m_x,x_{\max})\times[m_y,y_{\max}).
\end{aligned}
\]

~~~text
                 y tăng
                   ^
       ymax   +---------+---------+
              |   NW    |   NE    |
              |         |         |
          my  +---------+---------+
              |   SW    |   SE    |
              |         |         |
       ymin   +---------+---------+----> x tăng
              xmin     mx        xmax
~~~

**Bất biến phân hoạch**:

1. Hợp bốn vùng con **bằng vùng cha**.
2. Với quy ước nửa mở, mỗi điểm thuộc vùng cha nằm trong **đúng một vùng con**.
3. Không vùng con nào nằm ngoài vùng cha.
4. Một điểm thuộc nút lá phải nằm trong miền hình học của chính nút lá ấy.

Điều kiện thứ hai rất quan trọng: nó cho phép chuyển điểm xuống đúng một nhánh mà không phải đưa cùng điểm vào nhiều nhánh.

### Một quy tắc đánh số con nhất quán

Chọn bit của phía phải theo trục x và bit của phía trên theo trục y:

\[
b_x=\begin{cases}0,&x<m_x,\\1,&x\ge m_x,\end{cases}
\qquad
b_y=\begin{cases}0,&y<m_y,\\1,&y\ge m_y.\end{cases}
\]

Đặt chỉ số con:

\[
\boxed{\operatorname{childIndex}=b_x+2b_y.}
\]

| Index | \(b_x\) | \(b_y\) | Vùng |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | SW |
| 1 | 1 | 0 | SE |
| 2 | 0 | 1 | NW |
| 3 | 1 | 1 | NE |

Ví dụ với vùng \([0,8)\times[0,8)\), trung điểm \((4,4)\):

- \((1,1)\to SW\), index 0.
- \((6,1)\to SE\), index 1.
- \((1,6)\to NW\), index 2.
- \((6,6)\to NE\), index 3.
- **\((4,4)\to NE\)**, vì điểm đúng trung điểm được gán về phía có bit 1.

**Không có quy ước đánh index 0–3 bắt buộc duy nhất trong mọi thư viện.** Một số thư viện đặt NW trước hoặc dùng trục y hướng xuống dưới như trong ảnh số. Khi đọc/ghi dữ liệu hoặc phối hợp nhiều hệ thống, phải **công bố quy tắc đánh con**.

## 3. Bucket capacity, điều kiện chia và điểm trùng tọa độ

Một **point-region quadtree** (thường viết **PR quadtree**) có thể lưu tối đa **\(B\)** điểm trong mỗi nút lá thông thường. Khi muốn chèn điểm mới vào một lá đã có \(B\) điểm:

1. Kiểm tra còn có thể chia miền không.
2. Nếu được, tạo bốn vùng con.
3. Phân phối lại **tất cả điểm cũ và điểm mới** vào vùng con đúng.
4. Nếu một vùng con vẫn vượt ngưỡng, tiếp tục chia vùng đó.

Ví dụ với \(B=2\), vùng gốc \([0,8)^2\). Chèn theo thứ tự:

\[
A=(1,1),\ B=(6,1),\ C=(1,6),\
D=(6,6),\ E=(7,7),\ F=(5,5).
\]

Sau A và B, gốc vẫn là một lá chứa 2 điểm. Khi chèn C, gốc có 3 điểm, vượt \(B\) nên chia thành bốn vùng con. Điểm A vào SW, B vào SE, C vào NW. Sau đó D, E, F đều vào vùng **NE** của gốc. Khi NE có ba điểm D, E, F, vùng NE cũng được chia:

~~~text
Vùng gốc [0,8) × [0,8)

                  ROOT
           /       |       |       \
         SW       SE      NW       NE
         [A]      [B]     [C]     / | | \
                                SW SE NW NE
                                [F] [] [] [D,E]

Tại cấp 2, miền NE của gốc là [4,8) × [4,8).
Trung điểm của miền này là (6,6).
F=(5,5) vào SW; D=(6,6), E=(7,7) vào NE.
~~~

Vùng thưa được giữ ở cấp nông; chỉ vùng đông thêm một cấp. Cây không nhất thiết đồng đều về chiều sâu ở tất cả nhánh.

### Vấn đề: nhiều điểm cùng tọa độ

Giả sử có 1.000 bản ghi với ID khác nhau nhưng **đều ở \((2,2)\)**. Dù chia bao nhiêu lần, chúng luôn rơi vào **cùng một vùng con**. Nếu chỉ có quy tắc “quá B thì chia” mà không có điều kiện dừng, cây có thể chia vô hạn hoặc vượt khả năng biểu diễn số thực.

Một thiết kế an toàn thường có ít nhất một trong các biện pháp:

- **Giới hạn độ sâu** \(H_{\max}\): tới mức đó giữ bucket có thể nhiều hơn \(B\).
- **Kích thước miền tối thiểu**: không chia nếu chiều rộng/cao đã quá nhỏ.
- **Điều kiện trung điểm khả dụng**: dừng khi số thực không biểu diễn được trung điểm nằm hẳn giữa hai biên.
- **Bucket đặc biệt cho tọa độ trùng**: giữ danh sách ID ở một tọa độ mà không cố tách theo vị trí.
- **Phân chia theo tiêu chí khác** chỉ khi dữ liệu và định nghĩa cấu trúc cho phép.

**Capacity \(B\) là mục tiêu của lá, không phải định lý rằng mọi lá luôn chứa tối đa \(B\) điểm.** Lá bị giới hạn độ sâu hoặc không thể chia có thể hợp lệ khi chứa nhiều hơn \(B\).

## 4. Bất biến cây: vì sao cắt tỉa vùng không bỏ sót?

Trong PR quadtree chứa **các điểm**, cần giữ những bất biến sau:

1. **Gốc:** vùng gốc chứa tất cả điểm mà chỉ mục quản lý.
2. **Vùng con:** mọi con có miền là một phần hợp lệ của miền cha.
3. **Phân hoạch:** các vùng con phủ hết vùng cha và không chồng nhau theo quy tắc sở hữu nửa mở.
4. **Phân phối:** mỗi bản ghi có ID riêng nằm trong **đúng một lá** phù hợp với tọa độ.
5. **Nhất quán cập nhật:** thêm, xóa và di chuyển điểm phải cập nhật đúng nhánh và metadata liên quan.
6. **Điều kiện chia:** một nút không thể bị chia vô hạn; phải có giới hạn/điều kiện dừng.

Khi truy vấn điểm nằm trong vùng \(Q\), nếu miền vùng \(R\) của một nút **không giao Q**, không điểm nào trong nhánh của nó có thể thuộc Q vì mọi điểm trong nhánh đều nằm trong R:

\[
\boxed{R\cap Q=\varnothing
\Longrightarrow
\operatorname{points}(\operatorname{subtree}(R))\cap Q=\varnothing.}
\]

Đây là **bảo đảm không có false negative** của việc cắt tỉa vùng.

Ngược lại:

\[
R\cap Q\ne\varnothing
\]

chỉ cho biết **nhánh có khả năng chứa kết quả**; các điểm trong nhánh vẫn có thể nằm ngoài Q. Vì vậy ta phải kiểm tra chính xác tọa độ của các điểm trong lá có giao Q.

### Khoảng nửa mở khi so sánh hai vùng

Với các khoảng \([a,b)\) và \([c,d)\) **không rỗng**, chúng giao nhau khi:

\[
\boxed{a<d\quad\land\quad c<b.}
\]

Với hai hộp nửa mở \(R,Q\) trong \(d\) chiều:

\[
\boxed{R\cap Q\ne\varnothing\iff
\forall i:\ R.lo_i<Q.hi_i\ \land\ Q.lo_i<R.hi_i.}
\]

Hai miền chỉ **chạm tại biên bị loại** không giao nhau theo quy tắc này. Nếu bài toán cần tính các vùng **đóng** (chạm biên cũng tính giao), phải dùng một predicate khác và xử lý nhất quán trong cả phân hoạch lẫn truy vấn.

## 5. Octree: cùng nguyên lý trong không gian 3 chiều

**Octree** chia một vùng hộp 3D theo **ba mặt phẳng qua trung điểm**, mỗi mặt vuông góc với một trục tọa độ x, y hoặc z. Kết quả là **tám khối con** (*octants*).

Với vùng:

\[
R=[x_0,x_1)\times[y_0,y_1)\times[z_0,z_1),
\]

và trung điểm \((m_x,m_y,m_z)\), mỗi trục chọn nửa thấp hoặc nửa cao. Có:

\[
\boxed{2\cdot2\cdot2=8}
\]

tổ hợp.

Để đánh số, đặt:

\[
b_x=[x\ge m_x],\quad
b_y=[y\ge m_y],\quad
b_z=[z\ge m_z],
\]

trong đó dấu ngoặc vuông trả 1 khi điều kiện đúng và 0 khi sai. Chọn:

\[
\boxed{\operatorname{octantIndex}=b_x+2b_y+4b_z.}
\]

| Index | \(b_x\) | \(b_y\) | \(b_z\) | Ý nghĩa |
| ---: | ---: | ---: | ---: | --- |
| 0 | 0 | 0 | 0 | Thấp x, thấp y, thấp z |
| 1 | 1 | 0 | 0 | Cao x, thấp y, thấp z |
| 2 | 0 | 1 | 0 | Thấp x, cao y, thấp z |
| 3 | 1 | 1 | 0 | Cao x, cao y, thấp z |
| 4 | 0 | 0 | 1 | Thấp x, thấp y, cao z |
| 5 | 1 | 0 | 1 | Cao x, thấp y, cao z |
| 6 | 0 | 1 | 1 | Thấp x, cao y, cao z |
| 7 | 1 | 1 | 1 | Cao cả ba trục |

Ví dụ vùng gốc \([0,8)^3\), trung điểm \((4,4,4)\):

- \(P=(2,7,5)\): bit \((0,1,1)\), index \(0+2+4=\mathbf6\).
- \(Q=(4,4,4)\): bit \((1,1,1)\), index **7**.
- \(S=(0,0,0)\): bit \((0,0,0)\), index **0**.

Một điểm thuộc **đúng một khối** nhờ quy tắc nửa mở giống 2D. Khối nào đông thì có thể tiếp tục chia thành tám khối nhỏ, tạo cây sâu hơn tại các vùng đông.

**Ứng dụng:** chỉ mục điểm 3D, voxel, dựng hình 3D, không gian thế giới game, kiểm tra vùng quan sát, quản lý khối vật chất theo độ phân giải và tăng tốc tìm kiếm ứng viên va chạm.

Không nên coi octree đơn giản là “quadtree thêm một cờ”: số con khi chia tăng từ 4 lên 8, số ô tiềm năng tăng nhanh hơn và hiệu quả phụ thuộc mật độ đối tượng trong **thể tích**.

## 6. Các biến thể: không phải mọi quadtree đều lưu điểm như nhau

Tên **quadtree** là tên chung cho một **họ cấu trúc**, không phải một layout cố định. Trước khi áp dụng công thức hoặc viết API, cần hỏi cây đại diện cho **vùng không gian** hay **đối tượng dữ liệu**.

| Biến thể | Nút đại diện cho gì? | Cách chia/điểm đáng lưu ý |
| --- | --- | --- |
| **Region quadtree** | Vùng 2D | Chia vùng thành 4 phần; có thể lưu trạng thái pixel/vùng đồng nhất |
| **Point-region quadtree (PR)** | Vùng và bucket điểm | Chia khi số điểm vượt ngưỡng; mỗi điểm thuộc một vùng lá |
| **Point quadtree** | Thường một điểm làm mốc tại nút | Hai đường qua điểm mốc tạo bốn góc phần tư; ngưỡng chia có thể do điểm quyết định, không nhất thiết đúng trung điểm |
| **PM quadtree** | Vùng chứa các đoạn cạnh/hình học | Quy tắc chia phụ thuộc số/kiểu đoạn cắt vùng; có nhiều biến thể PM1/PM2/PM3 |
| **Loose quadtree** | Vùng danh nghĩa kèm vùng bao nới rộng | Cho phép một vật thể vừa ô mở rộng để giảm đăng ký vào quá nhiều ô |
| **Compressed quadtree** | Các nút quan trọng sau nén chuỗi vùng | Bỏ nhiều mức một-con thực chất chỉ duy trì phân hoạch trung gian |

**PR quadtree** là biến thể dùng trong phần mã Python chính của bài. Nó dễ giải thích vì mỗi điểm có đúng một tọa độ và nằm trong một bucket lá.

### Region quadtree dùng cho ảnh/occupancy

Thay vì lưu danh sách tọa độ điểm, lá có thể mang nhãn:

- **Trống**: vùng không có nội dung.
- **Đầy**: toàn vùng cùng một trạng thái.
- **Hỗn hợp**: phải chia tiếp để biểu diễn phần khác biệt.

Ví dụ một ảnh nhị phân 8×8: nếu toàn bộ góc trên trái là màu trắng, có thể lưu cả vùng đó thành **một lá trắng** thay vì 16 pixel riêng. Chỉ những vùng pha trộn mới cần chia sâu hơn.

Khi triển khai với ảnh, điều kiện dừng thường là **kích thước pixel tối thiểu** hoặc **độ đồng nhất màu**, không phải số điểm \(B\).

### Point quadtree không nhất thiết chia đúng trung điểm

Một **point quadtree** cổ điển có thể dùng tọa độ của chính điểm được chèn làm ranh giới bốn nhánh. Trong khi đó **PR quadtree** chia miền theo **trung điểm hình học**, không phụ thuộc điểm mốc. Hai kiểu này có thể có độ cao, cách chèn và kết quả duyệt rất khác nhau.

**Kết luận:** Khi ai đó nói “quadtree tìm kiếm nhanh”, phải xác định rõ **biến thể, quy tắc chia, cách xử lý điểm trùng và workload** trước khi đánh giá.

## 7. Thuật toán chèn điểm vào PR quadtree

Ta chọn một quy ước dễ kiểm chứng:

- Mỗi **nút lá** có danh sách các bản ghi điểm.
- Mỗi **nút trong** có bốn vị trí con và không giữ điểm trực tiếp.
- Nếu một lá có nhiều hơn \(B\) điểm, chia tiếp **chỉ khi** chưa đạt giới hạn độ sâu và trung điểm còn phân biệt được.
- Định danh bản ghi **ID** tách riêng khỏi tọa độ: hai điểm cùng tọa độ vẫn có thể là hai bản ghi.

### Mã giả

~~~text
INSERT(node, point):
    yêu cầu point nằm trong vùng node

    nếu node là NÚT TRONG:
        index = chọn vùng con dựa trên trung điểm
        INSERT(node.children[index], point)
        cập nhật metadata của node nếu đang lưu
        return

    thêm point vào bucket của node

    nếu kích thước bucket <= B:
        return

    nếu đã đạt MAX_DEPTH hoặc không thể chia hình học:
        giữ bucket tràn, return

    chia node thành bốn miền con
    chuyển toàn bộ điểm của bucket cũ
        vào đúng một miền con
    nếu một miền con lại quá B:
        tiếp tục chia miền con đó nếu được
~~~

### Diễn giải quá trình

1. Khi lá còn chỗ, thao tác chủ yếu là đi xuống một đường rồi thêm điểm.
2. Khi lá tràn, phải **phân phối lại** các điểm đang nằm trong lá vì nút đó trở thành nút trong.
3. Một lần chèn có thể kích hoạt **nhiều lần chia liên tiếp** nếu các điểm nằm sát nhau ở một vùng rất nhỏ.
4. Mỗi lần phân phối, điểm chỉ vào đúng một con theo quy tắc so sánh với trung điểm.
5. Nếu việc chia không còn hữu ích/khả thi, giữ các điểm tại lá tràn có kiểm soát.

Một lỗi nguy hiểm là chỉ chuyển **điểm mới** vào vùng con mà quên phân phối lại **điểm cũ**. Khi đó điểm cũ sẽ nằm ở nút trong hoặc bị thất lạc, làm truy vấn chỉ đi xuống các lá trả thiếu kết quả.

### Biểu diễn con rỗng

Có hai cách:

- **Tạo đủ bốn con** mỗi khi chia, dù một số vùng không chứa điểm. Dễ lập trình, truy vấn đơn giản nhưng tốn node rỗng.
- **Chỉ tạo những con có dữ liệu**, còn vị trí không tạo được coi là vùng rỗng. Tiết kiệm hơn nhưng phải giữ thông tin vị trí và biên các con cho phép tạo đúng khi chèn lần sau.

Cả hai đều đúng nếu **miền của mỗi vị trí con vẫn được xác định chính xác**. Một con chưa cấp phát không có nghĩa là có thể bỏ qua vị trí hình học của nó.

## 8. Truy vấn vùng (*range / window query*)

Cho hộp truy vấn nửa mở:

\[
Q=[q_{x0},q_{x1})\times[q_{y0},q_{y1}),\qquad
q_{x0}<q_{x1},\ q_{y0}<q_{y1}.
\]

Mục tiêu:

\[
\boxed{\operatorname{Range}(Q)=
\{p\in P:q_{x0}\le p_x<q_{x1},\
q_{y0}\le p_y<q_{y1}\}.}
\]

### Thuật toán

~~~text
RANGE(node, Q):
    nếu vùng(node) không giao Q:
        return  // cắt tỉa cả cây con

    nếu node là NÚT LÁ:
        với mỗi point trong bucket:
            nếu point thuộc Q:
                xuất point
        return

    với mỗi vùng con có thể chứa dữ liệu:
        RANGE(child, Q)
~~~

Sơ đồ:

~~~mermaid
flowchart TD
    A["Đến một nút vùng R"] --> B{"R có giao hộp truy vấn Q?"}
    B -->|Không| C["Bỏ toàn bộ cây con"]
    B -->|Có| D{"Nút lá?"}
    D -->|Có| E["Lọc từng điểm bằng predicate point-in-Q"]
    D -->|Không| F["Đi xuống các vùng con liên quan"]
    E --> G["Xuất điểm hợp lệ"]
~~~

### Ví dụ biên

Vùng gốc \([0,8)\times[0,8)\), chia tại \(x=y=4\). Truy vấn:

\[
Q=[0,4)\times[0,8).
\]

Vùng Q chỉ chứa **nửa trái**, nên có thể bỏ hoàn toàn hai nhánh phía phải (**SE** và **NE**). Điểm \((4,4)\) thuộc vùng NE nhưng **không thuộc Q**, vì biên phải \(x=4\) bị loại.

Nếu thay bằng truy vấn **biên đóng** \([0,4]\times[0,8]\), điểm \((4,4)\) phải được trả; cần xử lý biên đóng **tường minh**, chứ không tái dùng điều kiện giao nửa mở rồi giả định đúng.

### Chi phí của range query

Gọi \(V\) là số **nút cây thật sự được thăm**, \(P_V\) là tổng số điểm được kiểm tra ở các lá đã thăm, và \(k\) là số điểm trả về. Với số chiều cố định:

\[
\boxed{T_{\mathrm{range}}=O(V+P_V+k).}
\]

Nếu bucket tối đa \(B\) và không tràn, \(P_V\le B\,L_V\), với \(L_V\) là số lá được thăm. Nhưng nếu nhiều điểm trùng ở lá giới hạn độ sâu, bucket có thể lớn hơn \(B\).

**Không có bảo đảm \(O(\log n+k)\) cho mọi PR quadtree**: cửa sổ lớn có thể phải xem nhiều lá và trả gần hết \(n\) điểm. Với truy vấn không có kết quả nhưng các miền vẫn giao, cây cũng có thể phải thăm nhiều nút trước khi chứng minh không có điểm.

## 9. Truy vấn bán kính: cận dưới khoảng cách tới vùng

Cho tâm \(q=(q_x,q_y)\), bán kính \(r\ge0\). Trả các điểm thỏa:

\[
\boxed{D_2^2(p,q)
=(p_x-q_x)^2+(p_y-q_y)^2\le r^2.}
\]

Một phương án là lấy **hộp ứng viên**:

\[
[q_x-r,q_x+r]\times[q_y-r,q_y+r]
\]

rồi thực hiện range query và lọc khoảng cách. Nhưng nếu range query mặc định **nửa mở**, hộp này cần được xử lý **đúng tại biên trên** để không bỏ một điểm có \(p_x=q_x+r\) hoặc \(p_y=q_y+r\).

Một cách tổng quát, tránh vấn đề “truy vấn hình tròn đóng so với hộp nửa mở”, là dùng **cận dưới khoảng cách từ tâm tới vùng nút**:

Với vùng \(R\) có các biên \(lo_i,hi_i\), đặt:

\[
\delta_i=
\begin{cases}
lo_i-q_i,&q_i<lo_i,\\
0,&lo_i\le q_i\le hi_i,\\
q_i-hi_i,&q_i>hi_i.
\end{cases}
\]

Rồi:

\[
\boxed{\operatorname{minDist}_2^2(q,R)
=\sum_i\delta_i^2.}
\]

Với R nửa mở, công thức dùng **bao đóng** của R làm **cận dưới an toàn** cho tất cả điểm thực sự thuộc R. Có thể đạt cận tại biên không thuộc R, nhưng điều đó chỉ khiến ta thăm một nhánh dư, **không làm mất kết quả**.

Quy tắc cắt tỉa:

\[
\boxed{\operatorname{minDist}_2^2(q,R)>r^2
\implies\text{bỏ nhánh R}.}
\]

Nếu minDist **bằng** \(r^2\), không được loại vì truy vấn bán kính dùng điều kiện \(\le r^2\); có thể có điểm ngay trên đường tròn.

Ở lá, kiểm tra khoảng cách thật từng điểm. Việc một vùng có minDist nhỏ hơn bán kính **không bảo đảm mọi điểm trong vùng đều thỏa**.

## 10. Nearest neighbor và k-nearest neighbors

**Nearest neighbor (NN)** tìm điểm gần \(q\) nhất theo metric đã định:

\[
\boxed{p^*=\arg\min_{p\in P}D(p,q).}
\]

**kNN** tìm \(k\) điểm gần nhất. Khi các điểm cùng khoảng cách, một API có thể quy định ưu tiên theo **ID** để kết quả ổn định.

### Branch-and-bound cho NN

1. Bắt đầu chưa có ứng viên tốt nhất hoặc có \(bestDist^2=+\infty\).
2. Chọn vùng có **minDist nhỏ** trước để sớm tìm ứng viên gần.
3. Khi đến lá, so khoảng cách thật của các điểm với ứng viên hiện tại.
4. Nếu một vùng còn lại có \(\operatorname{minDist}_2^2>bestDist^2\), bỏ vùng đó.
5. Tiếp tục cho tới khi mọi nhánh có thể chứa điểm tốt hơn đều đã được xét.

Nếu xét **bằng khoảng cách** và cần ưu tiên ID nhỏ nhất, khi minDist bằng bestDist phải cân nhắc **tiếp tục duyệt** để không bỏ một điểm cùng khoảng cách nhưng có ID tốt hơn.

### Mở rộng sang kNN

Ta có thể giữ **max-heap của k điểm tốt nhất** hiện tại, trong đó phần tử đầu là ứng viên tệ nhất trong k điểm đã tìm. Khi đủ k ứng viên, ngưỡng cắt tỉa là khoảng cách của ứng viên tệ nhất đó. Nếu chưa đủ k, chưa có quyền bỏ vùng chỉ vì minDist lớn hơn khoảng cách của một ứng viên riêng lẻ.

**Điểm quan trọng:** Dù quadtree có chiều cao nhỏ, NN không tự động chỉ đi xuống **một** đường. Có thể phải quay lại nhiều nhánh nếu vùng của chúng vẫn gần điểm truy vấn.

### Quyền truy cập dữ liệu không gian không đồng nghĩa thứ tự khoảng cách

Quadtree phân theo **vị trí vùng**, không sắp xếp toàn bộ điểm theo khoảng cách tới một tâm truy vấn bất kỳ. Tâm truy vấn thay đổi thì thứ tự các điểm gần nhất có thể thay đổi. Vì vậy NN/kNN cần sử dụng cận khoảng cách và thuật toán ưu tiên nhánh, không chỉ đọc các lá theo thứ tự DFS.

## 11. Xóa, di chuyển và gộp vùng sau cập nhật

Một cây phục vụ dữ liệu động cần trả lời cả ba câu hỏi: **điểm cũ nằm ở đâu?**, **điểm mới thuộc vùng nào?**, và **cây có cần tái tổ chức sau cập nhật không?**

### Xóa điểm

Với bản ghi ID biết trước:

1. Tra bản ghi theo ID để biết tọa độ cũ.
2. Đi từ gốc xuống vùng lá chứa tọa độ ấy.
3. Xóa đúng bản ghi khỏi bucket lá.
4. Cập nhật metadata, ví dụ số điểm trong cây con.
5. Nếu nhiều vùng con giờ đủ ít điểm, có thể **gộp lại** thành một lá.

Nếu không có ánh xạ **ID → tọa độ** hoặc vị trí nút, để tìm một ID bất kỳ có thể phải quét toàn bộ cây. Một hash map theo ID thường là chỉ mục phụ đáng có trong ứng dụng có xóa/cập nhật theo ID.

### Gộp bốn con khi số điểm ít

Giả sử một nút trong có bốn cây con, tổng số điểm của chúng còn **không quá \(B\)**. Nếu mô hình cho phép, ta có thể:

- Thu thập các điểm còn lại từ cả bốn cây con.
- Xóa/cắt bốn nhánh con.
- Đặt tất cả điểm vào bucket của nút cha, chuyển nó thành **lá**.

Điều kiện tổng số điểm \(\le B\) là **đủ** để gộp, nhưng không bắt buộc mọi triển khai phải gộp ngay sau xóa. Không gộp có thể để lại nhiều nút rỗng và làm truy vấn lãng phí; gộp quá thường xuyên có thể gây **chia–gộp lặp lại** khi số điểm dao động quanh ngưỡng \(B\).

### Hysteresis để tránh chia–gộp liên tục

Một thiết kế có thể chọn **ngưỡng chia** khác **ngưỡng gộp**:

- Chia khi số điểm vượt \(B_{\mathrm{split}}\).
- Chỉ gộp khi tổng số điểm xuống dưới \(B_{\mathrm{merge}}\), với \(B_{\mathrm{merge}}<B_{\mathrm{split}}\).

Việc dùng hai ngưỡng tạo khoảng đệm khi dữ liệu dao động. Nếu ứng dụng yêu cầu nút lá luôn có tối đa B điểm, phải điều chỉnh bất biến và không cho phép lá gộp vượt giới hạn đó.

### Di chuyển điểm

Với điểm \(p\) di chuyển sang \(p'\):

- Nếu \(p'\) vẫn nằm trong **lá hiện tại**, có thể chỉ cần cập nhật tọa độ và bản ghi theo ID.
- Nếu \(p'\) sang một vùng khác, có thể xử lý như **xóa vị trí cũ + chèn vị trí mới**.
- Nếu \(p'\) nằm **ngoài miền gốc**, phải xử lý chính sách miền trước khi sửa dữ liệu.

Một phương án tiết kiệm có thể tìm **tổ tiên chung nhỏ nhất** của lá cũ và mới rồi chỉ tổ chức lại bên dưới tổ tiên ấy; đó là tối ưu, không phải yêu cầu bắt buộc để có thuật toán đúng.

**Đừng sửa tọa độ bản ghi rồi quên sửa chỉ mục.** Điểm có thể bị giữ ở một lá mà miền của lá không còn chứa nó, khiến phép cắt tỉa nhánh trả **thiếu kết quả**.

### Mở rộng miền gốc

Nếu quadtree quản lý \([0,8)^2\), điểm mới \((9,3)\) nằm ngoài miền gốc. Có các lựa chọn:

1. **Từ chối** điểm ngoài miền.
2. **Xây lại chỉ mục** với miền gốc lớn hơn và chèn lại toàn bộ điểm.
3. **Mở rộng gốc động** bằng cách đặt gốc cũ vào một trong bốn vùng con của gốc mới, với điều kiện vùng mới và cách căn chỉnh bảo đảm miền gốc cũ khớp trọn một vùng con.

Phương án 3 thường dùng cách tăng cạnh gốc theo lũy thừa hai và **căn chỉnh miền**. Nếu chọn ranh giới tùy ý, gốc cũ có thể không trùng một vùng con của gốc mới, khiến việc giữ nguyên cây cũ dưới một con trở nên sai.

**Không tự mở rộng gốc bằng cách chỉ sửa max x/max y của cùng một nút** trong một cây đã có nhiều cấp: các trung điểm của các nút con trước đó có thể không còn phù hợp với phân hoạch mới.

## 12. Lưu đoạn thẳng, hình chữ nhật và vật thể 3D

PR quadtree cho điểm có quy tắc rõ ràng: mỗi điểm chỉ thuộc một miền lá. Nhưng **một vật thể có diện tích/thể tích** có thể cắt nhiều vùng con cùng lúc.

Ví dụ vật thể AABB:

\[
O=[3,6]\times[3,6]
\]

giao bốn góc phần tư của vùng gốc \([0,8)^2\), chia ở \((4,4)\). Nếu vật thể chỉ được đặt vào **ô chứa tâm**, các truy vấn ở vùng khác vẫn giao vật thể nhưng có thể không tới ô lưu ID, gây **false negative**.

### Chiến lược A — Sao chép tham chiếu vào mọi vùng liên quan

Một vật thể có thể được đăng ký vào **mọi lá mà AABB của nó giao**. Khi truy vấn:

1. Duyệt các vùng liên quan.
2. Gộp ID từ các lá.
3. **Khử trùng theo ID**, vì cùng vật thể có thể xuất hiện nhiều nơi.
4. Kiểm tra giao AABB/hình học thật khi cần.

Chi phí lưu tăng theo số membership:

\[
\boxed{M=\sum_{a=1}^{n}r_a,}
\]

trong đó \(r_a\) là số lá chứa tham chiếu tới vật thể \(a\). Vật thể rất lớn có thể xuất hiện trong **nhiều lá**, thậm chí tăng mạnh khi vùng được chia sâu.

### Chiến lược B — Giữ vật thể ở nút tổ tiên phù hợp

Một chiến lược khác là **chỉ đẩy vật thể xuống** nếu hộp bao của nó nằm **trọn trong đúng một vùng con**; nếu vật thể cắt qua ranh giới của nhiều con, **giữ nó tại nút hiện tại**.

Ví dụ O cắt cả bốn góc phần tư của gốc thì có thể ở ngay bucket của gốc, còn một vật thể nhỏ hoàn toàn thuộc NE có thể được đưa xuống NE.

Thuật toán truy vấn phải **kiểm tra các vật thể được giữ ở mọi nút tổ tiên đã thăm**, không chỉ các lá, và vẫn phải duyệt các vùng con có thể liên quan.

Ưu điểm: một vật thể thường chỉ được lưu **một lần**, tránh nhiều membership. Nhược điểm: nút gần gốc có thể chứa nhiều vật thể lớn, khiến truy vấn nhỏ vẫn phải kiểm tra chúng.

### Loose quadtree và loose octree

**Loose quadtree/octree** nới rộng phạm vi bao (*loose bounds*) của các nút so với miền phân hoạch danh nghĩa. Một vật thể có thể được gắn vào một nút có **loose bound chứa trọn** nó, giảm việc đăng ký nhiều lá khi vật thể dịch chuyển nhẹ.

Nhưng các loose bound có thể **chồng lấp**, nên việc chọn nhánh và cắt tỉa phải dựa đúng hộp bao được dùng để bao vật thể. Không thể mặc định rằng mọi truy vấn chỉ cần đi một nhánh vì các miền danh nghĩa không giao.

### Cần phân biệt broad-phase và narrow-phase

Đối với kiểm tra va chạm:

- **Broad-phase:** dùng quadtree/octree, hộp bao và vùng để tìm các **cặp có khả năng va chạm**.
- **Narrow-phase:** kiểm tra hình học thật, ví dụ giao đa giác, giao tam giác, thể tích hoặc khoảng cách chính xác.

Hai hộp bao giao nhau chỉ là **điều kiện cần** cho hai hình học nằm trong các hộp đó giao nhau, không tự là **điều kiện đủ**.

## 13. Region quadtree cho ảnh và octree cho voxel

Ngoài chỉ mục điểm, phân chia vùng còn dùng để **nén và biểu diễn trạng thái theo độ phân giải**.

### Quadtree của ảnh nhị phân

Một ảnh nhị phân có mỗi pixel là **trắng hoặc đen**. Quadtree có thể được dựng:

~~~text
BUILD(region):
    nếu mọi pixel trong region cùng màu:
        trả về một lá mang màu đó

    nếu region đã tới 1 pixel:
        trả về một lá mang giá trị pixel

    chia region thành 4 vùng con
    BUILD từng vùng con
    trả về nút trong gồm 4 kết quả
~~~

Một vùng 64×64 hoàn toàn trắng có thể được biểu diễn bằng **một lá**, không cần lưu 4096 nút pixel. Nhưng ảnh có mẫu bàn cờ luân phiên có thể đòi hỏi chia đến từng pixel và tạo nhiều nút.

Đây là **quadtree nén theo tính đồng nhất**, không phải PR quadtree phân chia theo số điểm. Điều kiện chia khác nhau dù đều tạo bốn vùng con.

### Octree của thể tích/voxel

Trong 3D, mỗi voxel có thể biểu diễn trạng thái vật chất, mật độ hoặc giá trị màu. Octree giúp:

- Giữ **khối đồng nhất** ở mức thô.
- Chia sâu những vị trí có **ranh giới hình dạng** hoặc chi tiết quan trọng.
- Truy vấn một vùng 3D hoặc chỉ xét khối có thể giao đối tượng.
- Giữ các cấp độ chi tiết (*level of detail, LOD*) khác nhau.

Ví dụ một thể tích 128×128×128 phần lớn rỗng có thể được lưu bằng một số khối lớn rỗng cộng các khối nhỏ quanh vật thể thay vì cấp phát tất cả \(128^3\) voxel.

**Đánh đổi:** Quá nhiều biên phức tạp hoặc nhiễu nhỏ có thể làm cây phải chia sâu ở nhiều nơi. Octree không bảo đảm nén tốt mọi dữ liệu 3D.

### Đếm ô tiềm năng theo độ sâu

Nếu bắt đầu từ một vùng gốc và chia **đều tất cả vùng** tới độ sâu \(h\):

| Đại lượng | Quadtree 2D | Octree 3D |
| --- | --- | --- |
| Số con khi chia một nút | 4 | 8 |
| Số vùng ở đúng độ sâu \(h\) | \(4^h\) | \(8^h\) |
| Tổng số nút từ mức 0 tới \(h\) | \((4^{h+1}-1)/3\) | \((8^{h+1}-1)/7\) |
| Nếu cạnh gốc \(L\) và chia đôi mỗi trục | Cạnh vùng \(L/2^h\) | Cạnh vùng \(L/2^h\) |
| Nếu miền gốc cạnh \(L\) | Diện tích một lá \(L^2/4^h\) | Thể tích một lá \(L^3/8^h\) |

Những công thức này nói về cây **đã chia đầy đủ mọi vùng**, không phải số node của cây thích nghi chứa dữ liệu thưa. Một quadtree thực tế có thể chỉ có vài vùng ở độ sâu sâu nhất.

## 14. Độ phức tạp: sâu bao nhiêu và tốn bao nhiêu bộ nhớ?

Đặt:

- \(n\): số điểm thật.
- \(B\): bucket capacity của lá thông thường.
- \(H\): giới hạn độ sâu cho phép.
- \(h\le H\): chiều cao thực của cây.
- \(N\): tổng số nút cây đã cấp, gồm lá và nút trong.
- \(V\): số nút thăm trong một truy vấn.
- \(P_V\): số điểm được kiểm tra ở các lá thăm.
- \(k\): số điểm kết quả.

### Tra cứu/chèn một điểm

Nếu chưa cần chia, việc tìm vùng lá của một điểm đi qua **một đường** dài tối đa \(h\), nên chi phí điều hướng là \(O(h)\) với số chiều cố định. Thêm vào bucket có thể \(O(1)\) phân bổ nếu bucket là mảng động.

Khi phải chia, điểm trong bucket bị phân phối lại. Nếu một lần chèn kích hoạt nhiều mức chia liên tiếp, tổng chi phí phụ thuộc **số lần chia và số bản ghi bị phân phối ở mỗi mức**, chứ không chỉ số cạnh của đường đi. Với \(B\) cố định và những lá không tràn trừ ở giới hạn độ sâu, một phép chèn có thể cần công việc \(O(BH)\) trong trường hợp nhiều lần chia; nếu lá giới hạn chứa nhiều bản ghi, chi phí thao tác bucket có thể lớn hơn.

### Vì sao không tự có độ sâu \(O(\log n)\)?

Giả sử 1.000 điểm nằm cực kỳ gần nhau trong một góc nhỏ. Mỗi lần chia có thể vẫn đưa tất cả điểm xuống **một** vùng con. Cây có thể tạo một **chuỗi nhánh sâu**, trong khi các nhánh còn lại rỗng.

Không có bất biến cân bằng theo **số điểm** nào bắt buộc bốn vùng con phải nhận số điểm tương đương. Quadtree cân theo **không gian hình học**, không tự cân theo số bản ghi.

Nếu điểm phân bố tương đối đều và mỗi lá có khoảng \(B\) điểm, chiều sâu có thể có xu hướng theo:

\[
\text{2D: }h\approx\log_4(n/B),\qquad
\text{3D: }h\approx\log_8(n/B),
\]

nhưng đây chỉ là **ước lượng trong điều kiện phân bố thuận lợi**, không phải bảo đảm trường hợp xấu.

### Truy vấn và bộ nhớ

| Công việc | Chi phí tổng quát | Lưu ý |
| --- | --- | --- |
| Chọn con từ một nút 2D/3D | \(O(1)\) | Số chiều cố định và 4/8 con |
| Đi tới lá theo một điểm | \(O(h)\) | Có thể sâu tới \(H\) |
| Thêm một điểm không chia | \(O(h)\) cộng chi phí bucket | Cần xác minh ID/vùng |
| Thêm điểm gây chia | Phụ thuộc số lần chia và điểm phân phối | Không luôn hằng số |
| Xóa điểm khi biết tọa độ | \(O(h)\) cho điều hướng, cộng xóa/gộp | Xóa trong list có thể duyệt bucket |
| Range query | \(O(V+P_V+k)\) | Phải thăm nhiều vùng nếu Q lớn |
| Radius query | \(O(V+P_V+k)\) | Dùng minDist cắt tỉa |
| Nearest neighbor | Có thể xét gần \(O(N+n)\) | Trường hợp xấu cắt tỉa yếu |
| Bộ nhớ | \(O(N+n)\) bản ghi/nút | Nếu lưu đủ con và nhiều mức rỗng, N có thể lớn |
| Build bằng chèn từng điểm | Tổng chi phí của các lần chèn | Phụ thuộc phân bố, B, H |

**Cận an toàn theo giới hạn độ sâu:** với \(H\) hữu hạn, cấu trúc không thể có đường dài hơn \(H\) phép chia; nhưng số nút có thể tăng theo số điểm và số cấp được phân nhánh. Trường hợp xấu, một loạt các vùng chia thưa có thể khiến metadata tăng đáng kể, vì mỗi nút trong quadtree/octree chuẩn dành chỗ cho 4/8 vị trí con.

Nếu mọi vùng đều chia tới H, tổng node có thể tăng tới \(\Theta(4^H)\) ở 2D hoặc \(\Theta(8^H)\) ở 3D. Đó là số lượng **vùng tiềm năng**, không phải khẳng định mọi dữ liệu n điểm đều tạo đủ các nút đó.

### Số chiều cao và overhead

Trong \(d\) chiều, mỗi lần chia đôi **mọi trục** sinh \(2^d\) con. Với \(d=10\), một nút trong có thể có 1.024 vị trí con; với \(d=20\), có hơn một triệu vị trí. Vì vậy thuật toán region splitting dạng quadtree/octree **không mở rộng nguyên xi** tới không gian rất nhiều chiều.

## 15. Số thực, quy tắc biên và giới hạn phân giải

Phân chia vùng được biểu diễn toán học bằng tọa độ thực, nhưng chương trình phải dùng **kiểu số cụ thể**, có giới hạn độ chính xác.

### Khi nào không nên chia tiếp?

Với vùng một chiều \([a,b)\), để chia đúng đôi phải có trung điểm \(m\) thỏa:

\[
\boxed{a<m<b.}
\]

Nếu \(m=a\) hoặc \(m=b\) sau làm tròn số thực, một nửa có thể không còn độ rộng biểu diễn hữu ích. Nếu cứ chia, cây có thể tạo các vùng trùng biên hoặc lặp vô hạn.

Ở 2D/3D, chỉ chia theo trung điểm khi **mọi trục được yêu cầu chia đều có trung điểm nằm trong khoảng mở**. Nếu có một trục không còn đủ độ phân giải, có thể **dừng chia** hoặc chuyển sang một biến thể chia theo số trục còn có ích; ví dụ Python trong bài chọn dừng chia để giữ định nghĩa quadtree/octree chuẩn.

### Phép tính trung điểm

Viết \((a+b)/2\) có nguy cơ **tràn** khi \(a,b\) là những số dương rất lớn dù trung điểm thực vẫn hữu hạn. Viết \(a+(b-a)/2\) tránh được vài trường hợp nhưng hiệu \(b-a\) cũng có thể tràn khi a và b khác dấu và độ lớn cực đại.

Một cách tính số thực khác là:

\[
m=a/2+b/2.
\]

Nó thường tránh được lỗi tràn tổng ở các biên hữu hạn cực lớn, song vẫn có thể chịu sai số làm tròn/underflow. **Phải kiểm tra điều kiện \(a<m<b\) sau phép tính**, không chỉ dựa vào công thức.

### Không dùng NaN hoặc vô cực làm tọa độ thông thường

Với NaN, những phép so sánh như \(x<m\), \(x\ge m\) có thể đều **False**, khiến điểm được đưa nhầm nhánh. Vô cực làm trung điểm hoặc khoảng cách mất ý nghĩa như một giá trị hữu hạn.

Một API nên **từ chối tọa độ không hữu hạn**, thống nhất thứ tự trục và bảo đảm mọi chiều của điểm tương ứng với miền gốc.

### Biên của miền gốc

Nếu gốc là \([0,8)\times[0,8)\):

- \((0,0)\) **được nhận**.
- \((7{,}999,3)\) **được nhận**.
- \((8,3)\) **không được nhận**.
- \((-0{,}001,3)\) **không được nhận**.

Đừng dùng cách kẹp điểm ngoài miền về biên trong chỉ mục nhưng vẫn giữ tọa độ gốc; khi đó bất biến “điểm thuộc miền nút chứa nó” bị phá và các truy vấn có thể bỏ sót.

### Tọa độ địa lý, vật lý và thời gian

Nếu dữ liệu là kinh độ/vĩ độ theo **độ**, một phép chia ở trung điểm số học theo hai trục **không tạo ra các vùng có diện tích mặt đất bằng nhau**. Đặc biệt vùng qua đường đổi ngày \(-180^\circ/+180^\circ\) cần xử lý kinh độ tuần hoàn, có thể phải tách thành nhiều hộp hoặc dùng mô hình không gian khác.

Nếu dùng octree để lưu \((x,y,z)\) theo **mét**, việc tính khoảng cách Euclid 3D có ý nghĩa như khoảng cách thẳng trong hệ tọa độ đó. Nhưng với vector \((x,y,t)\), chiều thời gian không cùng đơn vị với hai trục không gian; muốn NN/kNN phải định nghĩa metric hoặc phép chuẩn hóa riêng.

## 16. Python: một region tree hỗ trợ cả quadtree và octree

Mã sau dùng **Python 3.10+** và thư viện chuẩn, với một lớp chung cho **2D và 3D** để thể hiện sự giống nhau của hai cấu trúc:

- 2D: mỗi lần chia tạo \(2^2=4\) con → quadtree.
- 3D: mỗi lần chia tạo \(2^3=8\) con → octree.

Thiết kế là **point-region tree**; mỗi nút trong giữ đủ 4/8 vùng con, mọi điểm nằm tại **một lá**, và nút có metadata **count** là tổng số điểm trong cây con. Lớp hỗ trợ thêm/xóa/di chuyển theo ID, truy vấn hộp nửa mở, bán kính đóng và nearest neighbor theo **bình phương khoảng cách Euclid**, có ưu tiên ID khi hai điểm cách đều.

**Quy ước:** hộp vùng có biên dưới bao gồm, biên trên loại trừ. Điểm trùng tọa độ được phép nếu **ID khác nhau**. Khi đạt max_depth hoặc số thực không còn trung điểm khả dụng, lá có thể chứa hơn capacity điểm.

~~~python
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class Point:
    id: str
    coords: tuple[float, ...]


@dataclass
class RegionNode:
    lo: tuple[float, ...]
    hi: tuple[float, ...]
    depth: int
    points: list[Point] = field(default_factory=list)
    children: list[RegionNode] | None = None
    count: int = 0


class PointRegionTree:
    def __init__(self, lower, upper, capacity=2, max_depth=8):
        lower = tuple(float(x) for x in lower)
        upper = tuple(float(x) for x in upper)
        if len(lower) not in (2, 3) or len(lower) != len(upper):
            raise ValueError("Bài minh họa chỉ hỗ trợ 2D hoặc 3D")
        if not all(isfinite(x) for x in lower + upper):
            raise ValueError("Biên miền phải hữu hạn")
        if not all(a < b for a, b in zip(lower, upper)):
            raise ValueError("Miền phải có độ rộng dương trên mọi trục")
        if type(capacity) is not int or capacity < 1:
            raise ValueError("capacity phải là số nguyên dương")
        if type(max_depth) is not int or max_depth < 0:
            raise ValueError("max_depth phải không âm")

        self.dimension = len(lower)
        self.capacity = capacity
        self.max_depth = max_depth
        self.root = RegionNode(lower, upper, depth=0)
        self.by_id: dict[str, Point] = {}

    def _coords(self, raw):
        value = tuple(float(x) for x in raw)
        if (len(value) != self.dimension
                or not all(isfinite(x) for x in value)):
            raise ValueError("Sai số chiều hoặc tọa độ không hữu hạn")
        return value

    @staticmethod
    def _contains(node, coords):
        return all(
            a <= x < b
            for a, x, b in zip(node.lo, coords, node.hi)
        )

    @staticmethod
    def _middle(node):
        # Thử tính trung điểm bằng a/2 + b/2.
        middle = tuple(
            a / 2.0 + b / 2.0
            for a, b in zip(node.lo, node.hi)
        )
        if not all(
            a < m < b
            for a, m, b in zip(node.lo, middle, node.hi)
        ):
            return None  # Không chia được với độ chính xác hiện tại.
        return middle

    @staticmethod
    def _child_index(coords, middle):
        index = 0
        for axis, (x, m) in enumerate(zip(coords, middle)):
            if x >= m:
                index |= 1 << axis
        return index

    def _split(self, node):
        middle = self._middle(node)
        if middle is None:
            return False

        children = []
        for mask in range(1 << self.dimension):
            child_lo = tuple(
                middle[axis] if mask & (1 << axis)
                else node.lo[axis]
                for axis in range(self.dimension)
            )
            child_hi = tuple(
                node.hi[axis] if mask & (1 << axis)
                else middle[axis]
                for axis in range(self.dimension)
            )
            children.append(
                RegionNode(child_lo, child_hi, node.depth + 1)
            )

        old_points = node.points
        node.points = []
        node.children = children

        # node.count đang là tổng số điểm, nên không cộng lại ở node.
        for point in old_points:
            index = self._child_index(point.coords, middle)
            self._insert(children[index], point)
        return True

    def _insert(self, node, point):
        if node.children is not None:
            middle = self._middle(node)
            assert middle is not None
            index = self._child_index(point.coords, middle)
            self._insert(node.children[index], point)
            node.count += 1
            return

        node.points.append(point)
        node.count += 1
        if (len(node.points) > self.capacity
                and node.depth < self.max_depth):
            self._split(node)

    def add(self, item_id, coords):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        if item_id in self.by_id:
            raise ValueError("ID đã tồn tại")

        point = Point(item_id, self._coords(coords))
        if not self._contains(self.root, point.coords):
            raise ValueError("Điểm ngoài miền gốc")

        self._insert(self.root, point)
        self.by_id[item_id] = point

    def _gather(self, node, output):
        if node.children is None:
            output.extend(node.points)
            return
        for child in node.children:
            self._gather(child, output)

    def _remove(self, node, point):
        if node.children is None:
            node.points.remove(point)
            node.count -= 1
            return

        middle = self._middle(node)
        assert middle is not None
        index = self._child_index(point.coords, middle)
        self._remove(node.children[index], point)
        node.count -= 1

        if node.count <= self.capacity:
            # Thu tất cả điểm rồi gộp nhánh thành một lá.
            remaining = []
            for child in node.children:
                self._gather(child, remaining)
            assert len(remaining) == node.count
            node.points = remaining
            node.children = None

    def remove(self, item_id):
        point = self.by_id[item_id]
        self._remove(self.root, point)
        del self.by_id[item_id]
        return point

    def move(self, item_id, coords):
        old = self.by_id[item_id]
        new = Point(item_id, self._coords(coords))
        if not self._contains(self.root, new.coords):
            raise ValueError("Điểm mới ngoài miền gốc")
        if old.coords == new.coords:
            return

        # Mô hình tuần tự; cập nhật hai thao tác như một giao dịch logic.
        self._remove(self.root, old)
        self._insert(self.root, new)
        self.by_id[item_id] = new

    @staticmethod
    def _overlap_half_open(node, qlo, qhi):
        return all(
            a < d and c < b
            for a, b, c, d in zip(node.lo, node.hi, qlo, qhi)
        )

    def query_box(self, lower, upper):
        qlo, qhi = self._coords(lower), self._coords(upper)
        if any(a > b for a, b in zip(qlo, qhi)):
            raise ValueError("Cận min lớn hơn max")
        if any(a == b for a, b in zip(qlo, qhi)):
            return []  # Hộp nửa mở suy biến thành rỗng.

        result = []

        def visit(node):
            if (node.count == 0 or
                    not self._overlap_half_open(node, qlo, qhi)):
                return
            if node.children is not None:
                for child in node.children:
                    visit(child)
            else:
                for p in node.points:
                    if all(
                        a <= x < b
                        for a, x, b in zip(qlo, p.coords, qhi)
                    ):
                        result.append(p)

        visit(self.root)
        return sorted(result, key=lambda p: p.id)

    @staticmethod
    def _distance_sq(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    @staticmethod
    def _min_distance_sq(node, q):
        # Cận dưới tới bao đóng của miền nửa mở.
        return sum(
            max(a - x, 0.0, x - b) ** 2
            for a, x, b in zip(node.lo, q, node.hi)
        )

    def query_radius(self, center, radius):
        q = self._coords(center)
        radius = float(radius)
        if not isfinite(radius) or radius < 0:
            raise ValueError("Bán kính phải hữu hạn và không âm")
        threshold = radius ** 2
        result = []

        def visit(node):
            if (node.count == 0 or
                    self._min_distance_sq(node, q) > threshold):
                return
            if node.children is not None:
                for child in node.children:
                    visit(child)
            else:
                for p in node.points:
                    if self._distance_sq(p.coords, q) <= threshold:
                        result.append(p)

        visit(self.root)
        return sorted(result, key=lambda p: p.id)

    def nearest(self, center):
        q = self._coords(center)
        best_key = None
        best_point = None

        def visit(node):
            nonlocal best_key, best_point
            if node.count == 0:
                return
            lower = self._min_distance_sq(node, q)
            if best_key is not None and lower > best_key[0]:
                return  # Không cắt tỉa bằng dấu >= do tie theo ID.

            if node.children is None:
                for p in node.points:
                    key = (self._distance_sq(p.coords, q), p.id)
                    if best_key is None or key < best_key:
                        best_key = key
                        best_point = p
                return

            children = sorted(
                node.children,
                key=lambda child: self._min_distance_sq(child, q)
            )
            for child in children:
                visit(child)

        visit(self.root)
        return best_point  # None nếu cây rỗng.

    def validate(self):
        """Kiểm tra số lượng, ID duy nhất và vùng chứa điểm."""
        seen = set()

        def check(node):
            if node.children is None:
                if node.count != len(node.points):
                    raise AssertionError("Sai count của lá")
                for p in node.points:
                    if not self._contains(node, p.coords):
                        raise AssertionError("Điểm nằm ngoài vùng lá")
                    if p.id in seen or self.by_id.get(p.id) != p:
                        raise AssertionError("ID bị trùng hoặc sai record")
                    seen.add(p.id)
                return node.count

            if node.points or len(node.children) != (1 << self.dimension):
                raise AssertionError("Sai hình dạng nút trong")
            subtotal = sum(check(child) for child in node.children)
            if subtotal != node.count:
                raise AssertionError("Sai tổng điểm cây con")
            return subtotal

        total = check(self.root)
        if total != len(self.by_id) or seen != set(self.by_id):
            raise AssertionError("Dữ liệu gốc và chỉ mục không khớp")
        return True
~~~

### Đọc kỹ bất biến trong cài đặt

**Điểm nằm trong lá:** Mỗi lần chèn chọn con bằng cách so tọa độ với trung điểm. Vì các vùng con phân hoạch không gian, không có điểm nào đồng thời thuộc hai vùng con.

**Count tại nút trong:** Trường count đếm **tổng điểm của toàn cây con**. Khi một lá chia, tất cả điểm cũ được chuyển xuống các con và các con tự tăng count; count của cha **không bị cộng lại**, vì số điểm của cây con không đổi.

**Giới hạn độ sâu:** Một lá ở max_depth có thể chứa nhiều điểm hơn capacity. Nếu tất cả điểm cùng tọa độ, cây vẫn dừng do giới hạn và không chia mãi.

**Gộp sau xóa:** Khi tổng số điểm dưới một nút trong giảm còn \(\le B\), chương trình thu các điểm con lại thành một lá. Điều này có thể duyệt thêm nhiều node và thay đổi bố cục cây, nhưng không làm thay đổi **ID hoặc tọa độ** của điểm.

**Nearest neighbor:** Quá trình chỉ loại nhánh khi cận dưới khoảng cách **lớn hơn** khoảng cách tốt nhất. Nếu bằng, nhánh vẫn có thể chứa một điểm cùng khoảng cách với ID nhỏ hơn, nên phải xét khi muốn tie-break ổn định.

**Validate:** Hàm kiểm tra số điểm tại mỗi nút, việc điểm có nằm trong vùng lá hay không, ID không bị lặp và bản ghi ánh xạ theo ID khớp với cây. Trong triển khai sản xuất còn có thể kiểm tra **ranh giới chính xác của từng con**, giới hạn cấp phát và phiên bản cập nhật.

**Giới hạn minh họa:** Đây là **cây điểm tĩnh về miền gốc** nhưng hỗ trợ cập nhật tọa độ trong miền. Nó không cho phép điểm mới nằm ngoài gốc, chưa có transaction/khóa đa luồng, không hỗ trợ đối tượng hình học lớn và không tối ưu bộ nhớ cho các nhánh rỗng.

## 17. Python: ví dụ 2D và 3D, đối chiếu với quét tuyến tính

Đoạn ví dụ tiếp theo **dùng lại** các lớp Point và PointRegionTree ở mục 16. Ta sẽ kiểm tra dữ liệu đã nói ở mục 3, di chuyển điểm giữa các vùng, tạo thêm điểm **trùng tọa độ** nhưng khác ID, rồi tạo octree 3D.

~~~python
# PR quadtree 2D, miền gốc [0,8) × [0,8).
tree2d = PointRegionTree((0, 0), (8, 8),
                         capacity=2, max_depth=6)

for item_id, xy in [
    ("A", (1, 1)),
    ("B", (6, 1)),
    ("C", (1, 6)),
    ("D", (6, 6)),
    ("E", (7, 7)),
    ("F", (5, 5)),
]:
    tree2d.add(item_id, xy)

assert tree2d.validate()
assert tree2d.root.children is not None
assert tree2d.root.children[3].children is not None

# Range query nửa mở: phía trái không chứa x=4.
left = tree2d.query_box((0, 0), (4, 8))
assert [p.id for p in left] == ["A", "C"]

top_right = tree2d.query_box((4, 4), (8, 8))
assert [p.id for p in top_right] == ["D", "E", "F"]

# Radius query dùng khoảng cách Euclid, kể cả biên tròn.
near = tree2d.query_radius((6, 6), 1.5)
assert [p.id for p in near] == ["D", "E", "F"]

assert tree2d.nearest((7.5, 7.5)).id == "E"

# Chuyển F từ NE sang SW: cây cập nhật lại cấu trúc.
tree2d.move("F", (1, 3))
assert [p.id for p in tree2d.query_box((0, 0), (4, 4))] == [
    "A", "F"
]
assert tree2d.validate()

# Trùng tọa độ vẫn là hai bản ghi khác ID.
tree2d.add("H", (6, 6))
assert [p.id for p in tree2d.query_box((6, 6), (7, 7))] == [
    "D", "H"
]
assert tree2d.validate()

tree2d.remove("H")
assert "H" not in tree2d.by_id
assert tree2d.validate()

# Octree 3D: cùng lớp, mỗi nút trong có 8 con.
tree3d = PointRegionTree((0, 0, 0), (8, 8, 8),
                         capacity=1, max_depth=5)
tree3d.add("P", (2, 7, 5))  # Octant index 6.
tree3d.add("Q", (4, 4, 4))  # Octant index 7.
tree3d.add("R", (0, 0, 0))  # Octant index 0.

assert tree3d.validate()
assert tree3d.root.children is not None
assert len(tree3d.root.children) == 8

# x < 4, nhận P và R nhưng không nhận Q ở đúng x=4.
left3d = tree3d.query_box((0, 0, 0), (4, 8, 8))
assert [p.id for p in left3d] == ["P", "R"]
assert [p.id for p in tree3d.query_radius((2, 7, 5), 0)] == [
    "P"
]
assert tree3d.nearest((4, 4, 4)).id == "Q"

tree3d.move("Q", (6, 6, 6))
assert tree3d.validate()

# Hàm quét tham chiếu: kiểm chứng độ đúng trên tập điểm nhỏ.
def brute_box(records, lower, upper):
    return sorted(
        p.id for p in records
        if all(a <= x < b
               for a, x, b in zip(lower, p.coords, upper))
    )


def brute_nearest(records, query):
    if not records:
        return None
    return min(
        records,
        key=lambda p: (
            sum((x-y)**2 for x, y in zip(p.coords, query)),
            p.id,
        )
    )


for lower, upper in [
    ((0, 0), (8, 8)),
    ((0, 0), (4, 4)),
    ((4, 4), (8, 8)),
    ((6, 6), (7, 7)),
]:
    expected = brute_box(tree2d.by_id.values(), lower, upper)
    actual = [p.id for p in tree2d.query_box(lower, upper)]
    assert actual == expected

for query in [(0, 0), (3, 3), (6, 6), (7.8, 7.8)]:
    expected = brute_nearest(tree2d.by_id.values(), query)
    assert tree2d.nearest(query).id == expected.id
~~~

### Cách diễn giải

Trong ví dụ 2D, A, B, C nằm ở ba vùng khác nhau sau lần chia đầu. D, E và F cùng thuộc NE, khiến NE cần chia sâu hơn. Sau khi F được chuyển khỏi NE, vùng này chỉ còn D và E; nếu tổng điểm đã không vượt capacity, cây có thể **gộp trở lại**.

Trong ví dụ 3D, cùng công thức bit chọn đúng octant cho P, Q, R. Điểm \((4,4,4)\) nằm đúng trung điểm mỗi trục nhưng theo nửa mở được đưa về **nửa cao** trên cả ba trục, tức index 7.

**Kiểm chứng với quét tham chiếu** là kỹ thuật quan trọng: lấy cùng dữ liệu đầu vào, so từng tập ID hoặc điểm gần nhất với thuật toán đơn giản không cắt tỉa. Với cây động, nên kiểm tra sau **mỗi chuỗi thêm/xóa/move**, không chỉ trên dữ liệu vừa xây.

### Vì sao hàm query_box trả danh sách đã sắp?

Lệnh sắp theo ID giúp kết quả **ổn định và dễ kiểm thử**. Chi phí truy vấn lúc này bao gồm thêm \(O(k\log k)\) trong trường hợp tổng quát để sắp \(k\) kết quả. Nếu ứng dụng chỉ cần một **tập không thứ tự**, có thể bỏ bước sắp và sử dụng giới hạn chi phí \(O(V+P_V+k)\) như phần lý thuyết.

## 18. So sánh quadtree/octree với lưới, k-d tree và R-tree

| Cấu trúc | Cách chia dữ liệu | Điểm mạnh | Khó khăn thường gặp |
| --- | --- | --- | --- |
| **Lưới đều** | Các ô có cùng kích thước | Ánh xạ điểm → ô bằng số học; cập nhật điểm đơn giản | Hotspot và nhiều ô rỗng |
| **Spatial hashing** | Lưới đều nhưng chỉ lưu bucket có dữ liệu | Phù hợp miền rất rộng/thưa | Truy vấn cửa sổ lớn có thể liệt kê vô số ô |
| **PR quadtree** | 2D, mỗi vùng chia 4 khi cần | Phân giải thích nghi vùng đông/thưa | Sâu khi điểm tập trung, metadata vùng |
| **Octree** | 3D, mỗi vùng chia 8 khi cần | Phù hợp voxel và point cloud 3D | Overhead lớn hơn, nhiều nút rỗng |
| **k-d tree** | Chia tập điểm bằng mặt phẳng theo một trục | Có thể chọn ngưỡng trung vị để cân theo số điểm | Cập nhật động và phân bố điểm khó |
| **R-tree** | Nhóm hình theo minimum bounding rectangles | Hữu ích cho polygon/đường/hình học kích thước khác nhau | Các hộp của các nhánh có thể chồng lấp |
| **Quét tuyến tính** | Không lập chỉ mục | Đơn giản, không cần xây dựng/cập nhật | Mỗi truy vấn thường xét \(n\) đối tượng |

**Chọn PR quadtree** khi dữ liệu điểm 2D có mật độ thay đổi theo vùng và truy vấn chủ yếu là cửa sổ/bán kính. **Chọn octree** khi dữ liệu thực sự là 3D và việc chia thể tích theo độ phân giải có ích. **Chọn R-tree hoặc chiến lược lưu vật thể lớn** nếu đối tượng là hình học có kích thước đa dạng; **chọn k-d tree** khi dữ liệu điểm tương đối tĩnh và việc chia theo trung vị phù hợp workload.

### Một đối tượng rất lớn là phép thử quan trọng

Vật thể 2D có AABB bao gần hết thế giới hoặc vật thể 3D chiếm gần hết khối gốc sẽ giao rất nhiều vùng con. Nếu đăng ký ở mọi lá, nó có thể bị **nhân bản ID nhiều lần**; nếu giữ ở gốc/tổ tiên, mỗi truy vấn phải xét nó như một ứng viên. Lựa chọn lưu trữ không thể được quyết định chỉ từ số điểm hay số nút.

### Thời gian theo dữ liệu và thiết bị

Trong bộ nhớ RAM, cây có nhiều đối tượng con trỏ rời rạc có thể chịu chi phí **cache miss**. Với dữ liệu trên đĩa, chỉ mục như R-tree thường được tổ chức để quản lý **trang dữ liệu** và giảm I/O; quadtree/octree trong RAM không tự động là lựa chọn tốt nhất khi lưu hàng tỷ đối tượng ngoài bộ nhớ.

Một bản đồ game nhỏ với hàng trăm đối tượng cũng có thể không cần chỉ mục: **quét tuyến tính** dễ viết, dễ kiểm tra và đôi khi nhanh hơn phần điều phối cây. Nên đo bằng workload thực tế thay vì chọn vì tên cấu trúc “nâng cao”.

## 19. Bài toán thực tế và lựa chọn biến thể

### 19.1. Điểm quan tâm trên bản đồ

Ứng dụng có hàng triệu vị trí POI trong một miền phẳng đã chiếu thích hợp. Quadtree có thể chia sâu ở trung tâm đô thị, để vùng thưa ở cấp nông. Truy vấn cửa sổ bản đồ chỉ duyệt những vùng giao với khung nhìn rồi kiểm tra điểm.

Nếu dữ liệu là **kinh độ/vĩ độ**, phải cân nhắc hệ tọa độ, vùng quanh đường đổi ngày và phép đo khoảng cách. Chia tọa độ độ bằng trung điểm số học **không** tạo các vùng cùng kích thước mét trên bề mặt Trái Đất.

### 19.2. Game 2D với vật thể di chuyển

Một PR quadtree có thể tìm vật thể theo **tâm điểm**. Nếu mỗi vật thể có bán kính va chạm, chỉ dùng khoảng cách tâm và một phạm vi tìm kiếm nhỏ có thể bỏ sót cặp va chạm khi vật thể lớn.

Các hướng xử lý gồm **nới vùng truy vấn theo bán kính lớn nhất**, dùng **loose quadtree** hoặc đăng ký AABB vào các vùng phù hợp. Cần dựa vào **điều kiện va chạm thực tế**, không chỉ tên cấu trúc.

### 19.3. Point cloud 3D

Octree có thể quản lý hàng triệu điểm 3D, chia sâu nơi mật độ điểm cao. Truy vấn “mọi điểm trong khối hộp này” cắt tỉa các khối không giao. Truy vấn gần điểm 3D sử dụng **minDist theo cả ba trục**.

Với point cloud có nhiều điểm trùng hoặc gần trùng, nên dùng **bucket capacity, min region size** và giới hạn sâu để tránh tạo một đường dài không hữu ích.

### 19.4. Voxel và biểu diễn thế giới theo độ phân giải

Thay vì giữ một voxel duy nhất cho mọi vị trí ở độ phân giải cao nhất, octree cho phép một khối đồng nhất được biểu diễn ở cấp thô, còn vùng gần bề mặt được chia mịn. Đây là **region octree lưu trạng thái vùng**, không nhất thiết có danh sách điểm ở lá.

Hiệu quả bộ nhớ phụ thuộc vào **mức độ đồng nhất**. Thể tích chứa nhiều chi tiết phức tạp ở mọi nơi có thể không nén tốt.

### 19.5. Phân phối tính toán theo vùng

Một hệ thống mô phỏng có thể dùng phân hoạch vùng để chia công việc. Các vùng đông nhận nhiều tài nguyên xử lý. Tuy nhiên:

- Một đối tượng có thể đi qua ranh giới vùng giữa các bước mô phỏng.
- Tương tác với đối tượng ở vùng láng giềng cần trao đổi dữ liệu.
- Nếu chia toàn bộ vùng theo giới hạn đối tượng, ta chưa chắc đạt **cân bằng tải máy chủ** do chi phí xử lý mỗi đối tượng có thể khác nhau.

Quadtree hỗ trợ tổ chức vùng, nhưng cân bằng workload còn cần **thống kê chi phí xử lý** và chiến lược di chuyển tác vụ phù hợp.

## 20. Sai lầm thường gặp

1. **“Quadtree luôn có bốn nút con chứa dữ liệu.”** Một phép chia tạo bốn **vị trí vùng**; một số có thể rỗng hoặc chưa cấp phát.
2. **“Octree là cây có tám cấp.”** Sai. Octree nói **tám vùng con khi chia**, không nói cây chỉ sâu tám mức.
3. **“Quadtree tự cân bằng số điểm như AVL.”** Sai. Nó chia theo **không gian**, không tự bảo đảm số điểm tương đương giữa các nhánh.
4. **“Càng chia sâu thì kết quả càng chính xác.”** Với điểm và predicate đúng, truy vấn đã có thể **chính xác** trước khi chia sâu; chia sâu chủ yếu ảnh hưởng hiệu năng và bộ nhớ.
5. **“Cây chỉ cần điều kiện quá capacity là chia mãi.”** Sai khi nhiều điểm trùng tọa độ hoặc số thực không còn trung điểm khả dụng.
6. **“Một điểm đúng trung điểm có thể rơi tùy ý vào hai con.”** Nếu cần mỗi điểm có một vị trí duy nhất, phải dùng quy tắc ranh giới nhất quán.
7. **“Xóa một điểm không cần cập nhật metadata count.”** Sai nếu các truy vấn/gộp dựa vào count của cây con.
8. **“Khi nút lá tràn, chỉ cần đẩy điểm mới vào một con.”** Sai: điểm cũ cũng cần được chuyển hoặc được xử lý tường minh theo biến thể.
9. **“Vùng nút giao cửa sổ nghĩa là mọi điểm bên trong nút đều thuộc Q.”** Sai: vẫn cần kiểm tra điểm/hình học ở lá.
10. **“Vùng nút không giao Q nhưng vẫn có thể chứa điểm thuộc Q.”** Không thể nếu miền nút thật sự **bao hết điểm thuộc nhánh** và predicate giao phù hợp.
11. **“Một vùng nửa mở có thể dùng lẫn với truy vấn đóng mà không cần sửa điều kiện biên.”** Sai ở những điểm đúng biên.
12. **“Quadtree chỉ được dùng cho điểm.”** Sai: region quadtree có thể lưu trạng thái ảnh, PM quadtree lưu đoạn, các biến thể khác lưu AABB/vật thể.
13. **“Gắn vật thể lớn theo tâm là đủ cho mọi truy vấn giao.”** Sai: tâm có thể ở xa trong khi hình vẫn giao vùng truy vấn.
14. **“Vật thể lớn đăng ký ở nhiều lá không cần dedup.”** Sai: có thể trả một đối tượng nhiều lần.
15. **“Khi move, chỉ sửa tọa độ trong bản ghi gốc.”** Sai nếu bản ghi còn nằm ở vùng lá cũ mà nó đã rời khỏi.
16. **“Thay đổi biên của root đã phân chia là đủ để mở rộng cây.”** Sai nếu trung điểm/con cũ không còn tương ứng phân hoạch mới.
17. **“Một lá trống phải bị xóa khỏi cây trong mọi trường hợp.”** Không bắt buộc; có thể giữ nút rỗng để đơn giản hoặc nén khi cần tiết kiệm.
18. **“Quadtree luôn tìm NN chỉ với một đường từ gốc đến lá.”** Sai: các nhánh khác có cận dưới đủ gần có thể chứa nghiệm tốt hơn.
19. **“Nếu minDist bằng bestDist thì luôn có thể prune.”** Sai khi API cần tie theo ID hoặc phải trả tất cả điểm cùng khoảng cách.
20. **“Cây cân theo trung điểm bảo đảm chiều cao \(O(\log n)\).”** Sai với điểm tập trung trong một vùng cực nhỏ.
21. **“Mọi quadtree sử dụng thứ tự con SW,SE,NW,NE.”** Sai: thứ tự phải được định nghĩa bởi từng cài đặt.
22. **“Số nút quadtree luôn đúng bằng 4 lần số điểm.”** Không có công thức tổng quát như vậy; số nút phụ thuộc cách chia, H và dữ liệu.
23. **“Octree 3D dùng công thức giao hộp 2D là đủ.”** Sai: phải kiểm tra cả trục **z**.
24. **“Kinh độ/vĩ độ độ góc là hệ tọa độ phẳng tính bằng mét.”** Sai: metric và phép chiếu phải phù hợp bài toán.
25. **“Có hai điểm cùng tọa độ nghĩa là có một ID.”** Sai: nhiều đối tượng khác ID vẫn có thể ở cùng vị trí.
26. **“Có thể dùng NaN để đánh dấu điểm trống rồi vẫn so sánh với trung điểm.”** Sai: NaN phá vỡ giả định về so sánh có thứ tự.
27. **“Điểm ngoài gốc có thể được gắn vào một lá biên mà không ảnh hưởng tính đúng.”** Sai: nó vi phạm bất biến vùng chứa điểm.
28. **“Nếu query trả k điểm thì luôn có thể hoàn tất trong \(O(1)\).”** Sai: cần ít nhất \(\Omega(k)\) công việc xuất dữ liệu.

## 21. Kiểm thử và benchmark có hệ thống

Một chỉ mục vùng chỉ thực sự đáng dùng khi nó trả **đúng dữ liệu** và đạt hiệu năng tốt hơn phương án đơn giản trên workload thực.

### Kiểm thử tính đúng

- **Điểm nằm ở bốn góc vùng gốc**: góc trái/dưới hợp lệ, điểm tại biên phải/trên của vùng nửa mở bị từ chối.
- **Điểm đúng đường trung điểm**: luôn đi về vùng có bit 1 tương ứng.
- **Điểm ở gần trung điểm từ hai phía**: hai điểm cách rất nhỏ nhưng phải được đặt đúng theo giá trị so sánh thực.
- **Nhiều điểm cùng tọa độ khác ID**: không mất ID và không chia vô hạn.
- **Vùng trống**, **toàn vùng** và **hộp truy vấn suy biến**: kết quả đúng theo định nghĩa nửa mở.
- **Bán kính 0**: chỉ trả các điểm đúng tại tâm (kể cả nhiều ID trùng tọa độ).
- **Truy vấn NN với khoảng cách bằng nhau**: giữ đúng quy tắc tie theo ID.
- **Xóa ở lá sâu rồi gộp**: count của mọi tổ tiên và danh sách ID vẫn đúng.
- **Chuyển qua ranh giới con**: dữ liệu xuất hiện tại vị trí mới, không bị giữ sai tại lá cũ.
- **Điểm nằm ngoài miền**: áp dụng đúng chính sách từ chối/mở rộng.
- **Octree 3D**: kiểm tra cả trục z và các vị trí 0–7.
- **Dữ liệu cạnh cực lớn/cực nhỏ**: phép tính trung điểm có điều kiện dừng.

### So sánh kết quả với quét tuyến tính

Với mỗi bộ dữ liệu thử, dùng một hàm tham chiếu quét mọi điểm rồi kiểm tra:

\[
\boxed{\operatorname{IDs}_{\mathrm{tree}}(Q)
=\operatorname{IDs}_{\mathrm{brute}}(Q).}
\]

Đối với NN, so theo cặp **(bình phương khoảng cách, ID)**. Đây là cách phát hiện **false negative** do tính sai vùng hoặc dùng sai bất đẳng thức ở biên.

### Chỉ số hiệu năng cần báo cáo

| Chỉ số | Ý nghĩa |
| --- | --- |
| \(n\) | Số bản ghi điểm |
| \(N\) | Tổng số nút cây, gồm vùng rỗng |
| \(h\) | Chiều cao cây thực |
| \(B,H\) | Bucket capacity và giới hạn sâu |
| Số lần split/merge | Chi phí cập nhật động |
| \(V\) | Số nút được thăm theo một truy vấn |
| \(P_V\) | Số điểm phải kiểm tra chính xác |
| \(k\) | Số kết quả thật |
| p50/p95/p99 | Độ trễ theo phân vị, tránh bỏ qua truy vấn chậm |
| Bộ nhớ đỉnh | Metadata, vùng con, bucket, tập kết quả |
| Tỷ lệ truy vấn/cập nhật | Đánh đổi giữa xây dựng và duy trì |

### Các trường hợp dữ liệu phải benchmark

1. **Phân bố đều** trên toàn miền.
2. **Một cụm rất dày**, vùng khác hầu như không có điểm.
3. **Nhiều tọa độ giống nhau**, chạm giới hạn độ sâu.
4. **Điểm nằm trên một đường** hoặc mặt phẳng trong 3D.
5. **Truy vấn nhỏ**, truy vấn chạm nhiều vùng và truy vấn phủ toàn miền.
6. **Dữ liệu dịch chuyển liên tục**, gây split/merge.
7. **Các vật thể có kích thước khác nhau**, nếu dùng chiến lược shape-aware.

**Đánh giá công bằng:** đo riêng chi phí **xây dựng**, **truy vấn**, **chèn**, **xóa**, **move**, và chi phí **rebuild** nếu có. Một cấu trúc có range query nhanh nhưng xây lại cực đắt có thể không phù hợp ứng dụng cập nhật mỗi khung hình.

## 22. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Phân chia quadtree ở trung điểm

Vùng gốc \(R=[0,8)\times[0,8)\). Viết bốn vùng con theo thứ tự **SW, SE, NW, NE**.

**Lời giải:** Trung điểm là \((4,4)\), nên:

\[
\begin{aligned}
SW&=[0,4)\times[0,4),\\
SE&=[4,8)\times[0,4),\\
NW&=[0,4)\times[4,8),\\
NE&=[4,8)\times[4,8).
\end{aligned}
\]

Các vùng con không chồng nhau theo quy ước nửa mở, và hợp của chúng bằng R.

### Câu 2. Điểm đúng ranh giới

Trong vùng câu 1, điểm \((4,4)\) thuộc con nào? \((8,3)\) có nằm trong gốc không?

**Lời giải:** Điểm \((4,4)\) có \(b_x=b_y=1\), thuộc **NE**, index 3. Điểm \((8,3)\) **ngoài gốc**, vì \(x=8\) là biên phải bị loại khỏi \([0,8)\).

### Câu 3. Tọa độ âm

Vùng gốc \(R=[-8,8)\times[-8,8)\) có trung điểm \((0,0)\). Điểm \(p=(-0.01,0)\) thuộc con nào nếu index \(=b_x+2b_y\)?

**Lời giải:** \(p_x<0\) nên \(b_x=0\); \(p_y=0\ge0\) nên \(b_y=1\). Index \(=0+2=\boxed{2}\), vùng **NW**.

### Câu 4. Thứ tự chèn và chia vùng

Với \(B=2\), vùng \([0,8)^2\), chèn A=(1,1), B=(6,1), C=(1,6). Khi nào gốc chia và mỗi điểm đi vào con nào?

**Lời giải:** Sau A và B, gốc có đúng 2 điểm nên vẫn là lá. Chèn C làm số điểm thành **3 > B**, nên chia thành bốn vùng. A→SW, B→SE, C→NW; NE rỗng.

### Câu 5. Vùng đông được chia tiếp

Tiếp tục câu 4, chèn D=(6,6), E=(7,7), F=(5,5). Giả sử \(B=2\). Vùng nào cần chia lần nữa và điểm nằm ở những con nào của vùng đó?

**Lời giải:** D, E, F đều vào vùng NE gốc \([4,8)^2\), khiến NE có 3 điểm. Trung điểm của vùng NE là \((6,6)\). F=(5,5) thuộc SW cấp hai; D=(6,6) và E=(7,7) cùng thuộc NE cấp hai. Chỉ cần chia sâu vùng NE gốc, không chia lại các vùng thưa khác.

### Câu 6. Point quadtree và PR quadtree

Một cây dùng tọa độ của chính điểm được chèn để chọn hai đường phân chia; cây khác luôn chia mỗi vùng tại trung điểm. Có thể mặc định chúng là cùng một cài đặt không?

**Lời giải:** **Không.** Cách đầu tương ứng với một biến thể **point quadtree**; cách sau là **region/PR quadtree**. Quy tắc chia khác có thể làm cây khác về hình dạng, độ sâu và chi phí cập nhật.

### Câu 7. Chỉ số octree

Gốc octree là \([0,8)^3\). Với quy tắc \(index=b_x+2b_y+4b_z\), hãy tính index của \(P=(2,7,5)\), \(Q=(4,4,4)\), \(R=(0,0,0)\).

**Lời giải:** Trung điểm \((4,4,4)\).

- P có bit \((0,1,1)\), index **6**.
- Q có bit \((1,1,1)\), index **7**.
- R có bit \((0,0,0)\), index **0**.

Các điểm nằm đúng trung điểm thuộc **nửa cao** của trục tương ứng.

### Câu 8. Số ô ở độ sâu h

Nếu chia **đều mọi vùng** của quadtree tới độ sâu \(h=3\), có bao nhiêu lá và tổng số nút? Octree chia đều tới độ sâu \(h=2\) thì sao?

**Lời giải:**

\[
\begin{aligned}
\text{Quadtree: }L&=4^3=64,\quad
N=(4^4-1)/3=(256-1)/3=85.\\
\text{Octree: }L&=8^2=64,\quad
N=(8^3-1)/7=(512-1)/7=73.
\end{aligned}
\]

Đó là cây **phân hoạch đầy đủ**, không phải số nút bắt buộc của cây thích nghi.

### Câu 9. Truy vấn nửa mở

Tập điểm gồm A=(1,1), B=(6,1), C=(1,6), D=(6,6), E=(4,4). Truy vấn \(Q=[0,4)\times[0,8)\) trả những điểm nào?

**Lời giải:** **A và C**, vì tọa độ x của chúng nhỏ hơn 4. Điểm E=(4,4) **bị loại** do biên phải \(x=4\) không thuộc Q, dù y=4 hợp lệ.

### Câu 10. Vì sao prune là an toàn?

Một nút có vùng R hoàn toàn nằm ở phía phải \(x\ge10\), còn hộp truy vấn Q nằm ở \(x<5\). Có cần đi xuống các hậu duệ của R không?

**Lời giải:** **Không**, nếu mọi điểm thuộc nhánh R đều nằm trong miền R. Hai vùng không giao nhau trên trục x, do đó không điểm nào trong R có thể thuộc Q. Đây là cắt tỉa dựa trên **bất biến vùng bao dữ liệu**.

### Câu 11. False positive ở mức vùng

Vùng R giao cửa sổ Q, nhưng tất cả điểm trong lá của R đều nằm ngoài Q. Việc R được thăm có phải lỗi của quadtree không?

**Lời giải:** **Không.** R giao Q chỉ là **điều kiện cần** để nhánh có thể liên quan. Thuật toán phải kiểm tra tọa độ thật của từng điểm; việc thăm ứng viên dư là hợp lệ, còn trả sai điểm mới là lỗi.

### Câu 12. Truy vấn bán kính và cận dưới

Cho \(q=(10,3)\), vùng R có \(x\in[2,6)\), \(y\in[0,5)\). Tính bình phương minDist từ q tới **bao đóng** của R. Nếu ứng viên NN hiện tại có bình phương khoảng cách 9, có thể prune R không?

**Lời giải:** Trục x cách bao vùng \(10-6=4\); trục y có q=3 nằm trong [0,5]. Vậy:

\[
\operatorname{minDist}^2(q,R)=4^2+0^2=\boxed{16}.
\]

Vì \(16>9\), mọi điểm trong R cách q xa hơn ứng viên hiện tại: **có thể bỏ R**.

### Câu 13. Điểm cùng khoảng cách, khác ID

Hai điểm A=(-1,0), B=(1,0), truy vấn NN tại q=(0,0). Nếu quy tắc tie là ID nhỏ hơn đứng trước, kết quả nào được chọn? Có thể bỏ một nhánh khi minDist bằng khoảng cách tốt nhất không?

**Lời giải:** A và B đều có bình phương khoảng cách 1; kết quả là **A** do ID nhỏ hơn. Nếu chưa xác minh ID trong nhánh có minDist bằng 1, không được bỏ nhánh đó chỉ vì khoảng cách bằng best. Dùng điều kiện prune nghiêm ngặt **minDist² > bestDist²** là an toàn cho quy tắc này.

### Câu 14. Trùng tọa độ và giới hạn sâu

Một PR quadtree có \(B=1,H_{\max}=5\). Có 100 điểm khác ID đều ở (2,2). Có thể duy trì yêu cầu mọi lá luôn không quá một điểm mà vẫn chỉ chia theo trung điểm không?

**Lời giải:** **Không.** Tất cả các điểm trùng sẽ luôn đi cùng một nhánh và ở độ sâu tối đa 5 không thể chia thêm. Cần cho phép bucket tràn ở lá cuối, lưu danh sách ID trùng hoặc dùng một chiến lược khác. Giới hạn sâu bảo đảm **không chia vô hạn**.

### Câu 15. Move điểm qua vùng

Điểm F trước ở (5,5), sau chuyển tới (1,3) trong vùng gốc \([0,8)^2\). Nó chuyển từ con nào sang con nào của gốc? Điều gì phải cập nhật?

**Lời giải:** F chuyển từ **NE (index 3)** sang **SW (index 0)**. Phải lấy F khỏi lá cũ, đưa vào lá mới, cập nhật count trên các đường tổ tiên và cân nhắc gộp/chia lại nếu các ngưỡng bị vượt.

### Câu 16. Xóa rồi gộp

Một nút trong có tổng 3 điểm ở bốn cây con, capacity \(B=2\). Xóa một điểm và còn tổng 2 điểm. Có thể gộp nút trong thành lá không?

**Lời giải:** **Có**, nếu mô hình cho phép gộp khi tổng điểm \(\le B\). Thu thập hai điểm và bỏ các nhánh con để trở thành một lá có 2 điểm. Không phải mọi triển khai bắt buộc gộp ngay; giữ nút trong vẫn đúng nếu dữ liệu/metadata được duy trì.

### Câu 17. Vật thể lớn giao nhiều vùng

Một hình AABB \([3,6]\times[3,6]\) nằm trong gốc \([0,8)^2\) chia tại (4,4). Nếu hình được gắn chỉ vào ô chứa tâm (4.5,4.5), truy vấn nhỏ ở (3.5,3.5) có thể bị bỏ sót không?

**Lời giải:** **Có.** Tâm hình thuộc **NE** nhưng hình vươn sang **SW**. Nếu truy vấn nhỏ chỉ đi nhánh SW, nó sẽ không tìm thấy hình lưu ở NE. Phải dùng chiến lược **nhiều ô**, **giữ ở tổ tiên** hoặc một chỉ mục hỗ trợ hình rộng.

### Câu 18. Dedup hình qua nhiều lá

Một vật thể R được đăng ký vào 7 lá. Cửa sổ truy vấn chạm đủ 7 lá và chỉ lấy danh sách ID từ từng lá. Kết quả có thể xuất R bao nhiêu lần? Cách khắc phục?

**Lời giải:** Có thể xuất **7 lần** nếu nối danh sách thô. Dùng một tập **seen ID** để chỉ đưa R vào kết quả một lần, và sau đó áp dụng predicate giao hình chính xác khi cần.

### Câu 19. Chia theo số chiều

Nếu chia đôi tất cả các trục của vùng \(d\) chiều, tại \(d=2,3,5,10\) một nút có bao nhiêu vị trí con?

**Lời giải:**

\[
2^2=4,\quad2^3=8,\quad2^5=32,\quad2^{10}=1024.
\]

Chi phí metadata tăng nhanh khi số chiều lớn; đừng tự mở rộng octree thành cây 100D mà không tính bộ nhớ.

### Câu 20. Trung điểm số thực không còn chia được

Một nút có biên \([a,b)\) rất hẹp, và phép tính trung điểm cho số float \(m=a\). Có nên tiếp tục chia tại m không?

**Lời giải:** **Không.** Chia như vậy tạo một khoảng có độ rộng 0 hoặc ranh giới không tiến triển. Cần **dừng chia**, cho phép bucket giữ nhiều điểm hơn B, hoặc chọn chiến lược độ chính xác/phân hoạch khác.

### Câu 21. Chọn chỉ mục cho ba bài toán

(a) 1.000 điểm trong 2D, truy vấn hiếm; (b) point cloud 3D có vùng rỗng và vùng dày; (c) nhiều polygon kích thước rất khác nhau, cần tìm hình giao cửa sổ. Chọn ứng viên triển khai ban đầu nào?

**Lời giải:** (a) **quét tuyến tính** có thể đủ, cần benchmark; (b) **octree** đáng thử vì phân giải thích nghi theo thể tích; (c) **R-tree** hoặc quadtree có chính sách lưu vật thể lớn và kiểm tra hình thật. Không có một lựa chọn thắng mọi workload.

### Câu 22. Vì sao kết quả truy vấn có chi phí \(\Omega(k)\)?

Một truy vấn vùng trả đúng 50.000 điểm. Có thể hứa tổng thời gian xuất toàn bộ kết quả là \(O(1)\) không?

**Lời giải:** **Không.** Chỉ riêng việc ghi/đưa ra \(k=50\,000\) kết quả đã cần ít nhất \(\Omega(k)\) thao tác trong mô hình đầu ra từng bản ghi. Chỉ mục giúp giảm **phần tìm kiếm ứng viên**, không xóa chi phí tạo đầu ra.

## 23. Tổng kết và cách áp dụng

**Quadtree** phân chia không gian 2D thành **bốn vùng con** khi cần; **octree** làm điều tương tự trong 3D thành **tám khối con**. Với quy tắc nửa mở, mỗi điểm thuộc đúng một vùng con, nên chèn và cập nhật có thể đi theo một đường xác định.

Đối với PR quadtree có bucket capacity B, một lá được chia khi quá tải và vẫn đủ điều kiện chia. Phải thiết lập **max_depth hoặc giới hạn độ phân giải** để xử lý những điểm trùng/điểm cực gần. Xóa có thể kích hoạt **gộp**, còn move phải cập nhật đúng nhánh. Mọi phép chia/gộp phải giữ bất biến rằng **vùng nút bao toàn bộ điểm trong cây con**.

**Truy vấn range** loại nhánh nếu vùng nút **không giao Q**; **truy vấn bán kính và NN** loại nhánh theo **cận dưới khoảng cách**. Với predicate đúng và metadata không lỗi thời, những phép cắt tỉa này không bỏ sót điểm thật. Nhưng thời gian vẫn phụ thuộc số nút được thăm và số điểm phải kiểm tra, không tự có bảo đảm \(O(\log n)\).

Đối với **vật thể có diện tích/thể tích**, cần một chiến lược khác cho điểm: đăng ký tham chiếu vào nhiều vùng rồi **dedup**, hoặc giữ vật thể ở một nút tổ tiên chứa trọn hộp bao. Nếu chỉ lưu ở ô chứa tâm mà truy vấn giao hình chỉ đi qua các vùng của cửa sổ, rất dễ bỏ sót vật thể lớn.

**Quy trình thực hành:** xác định hệ tọa độ/miền gốc → chọn quadtree, octree hay biến thể thích hợp → công bố quy ước biên và thứ tự con → đặt capacity và giới hạn sâu → triển khai chèn/xóa/move với bất biến rõ ràng → đối chiếu với quét tuyến tính → đo hiệu năng trên dữ liệu đều, dữ liệu cụm và nhiều điểm trùng. **Lựa chọn cấu trúc tốt là lựa chọn giữ đúng kết quả với chi phí phù hợp dữ liệu**, không phải cấu trúc có tên phức tạp nhất.
