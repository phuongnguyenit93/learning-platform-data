# R-tree và nhóm các hộp bao có thể chồng lấn

Hãy tưởng tượng một hệ thống quản lý bản đồ có hàng triệu đoạn đường, tòa nhà và vùng hành chính. Mỗi đối tượng có thể chiếm **một diện tích**, không chỉ là một điểm. Khi người dùng kéo một hình chữ nhật trên bản đồ để chọn các tòa nhà giao với vùng ấy, việc duyệt mọi đối tượng sẽ rất tốn kém. Ta cần một cấu trúc có thể **bỏ cả nhóm đối tượng** nếu biết vùng chứa nhóm không giao cửa sổ truy vấn.

**R-tree** là một họ chỉ mục không gian theo dạng cây cân bằng, dùng các **hình chữ nhật bao tối thiểu** (*minimum bounding rectangle*, viết tắt **MBR**) để nhóm các đối tượng hoặc nhóm cây con. Khác với một quadtree phân chia không gian thành những vùng có quy tắc sở hữu rõ ràng, **MBR của các nhánh khác nhau trong R-tree có thể chồng lấn**. Vì vậy một truy vấn có thể phải đi xuống **nhiều nhánh cùng cấp**.

Bài học thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, hướng tới hiểu cấu trúc dữ liệu, bất biến, thao tác và độ phức tạp thời gian–bộ nhớ để chọn cấu trúc phù hợp. Ta sẽ xây R-tree từ các hộp bao, giải thích chiến lược chọn nhánh, thao tác split/gộp, tìm kiếm theo vùng, nearest neighbor, bulk loading và các biến thể. Phần thực hành cung cấp Python 2D với **quadratic split**, truy vấn giao hình chữ nhật và các phép kiểm chứng.

> **Ý chính:** Mỗi nhánh của R-tree có một MBR **bao trọn dữ liệu** trong nhánh ấy. Nếu MBR không giao vùng truy vấn, bỏ cả nhánh là an toàn. Nếu MBR giao vùng truy vấn, nhánh **có thể** có kết quả nhưng không chắc chắn; và vì các MBR có thể chồng lấn, thường phải xét nhiều nhánh.

## 1. Bài toán: chỉ mục cho điểm, hình chữ nhật và hình học có kích thước

Một **điểm** được biểu diễn bởi \((x,y)\), có thể truy vấn bằng k-d tree hoặc spatial hash. Nhưng dữ liệu GIS và đồ họa thường gồm:

- Tòa nhà: đa giác với chiều rộng và chiều cao.
- Đường: đường gấp khúc hoặc đoạn thẳng.
- Lô đất: vùng có diện tích.
- Vùng phục vụ: đa giác hoặc hợp nhiều đa giác.
- Vật thể game 2D/3D: hình chữ nhật/hộp bao va chạm.

Một đối tượng như đoạn đường có thể **cắt qua nhiều ô của lưới** hoặc **nhiều vùng của quadtree**. R-tree nhóm các đối tượng bằng MBR, không bắt buộc mỗi đối tượng phải nằm gọn trong một phân vùng không gian không chồng lấn.

Với tập đối tượng \(O=\{o_1,\ldots,o_n\}\) và cửa sổ truy vấn Q, mục tiêu của *intersection query* là:

\[
\boxed{
\operatorname{Intersect}(Q)=
\{o_i\in O:\operatorname{geom}(o_i)\cap Q\ne\varnothing\}.
}
\]

Nếu chỉ lưu MBR của hình gốc, phép tìm dựa trên MBR thường là bước **lọc ứng viên** (*broad phase*). Đối với đa giác hoặc đường, cần kiểm tra giao **hình học gốc** (*narrow phase*) trước khi trả kết quả chính xác.

Nếu các đối tượng được lưu **chính là hình chữ nhật**, phép kiểm tra giao MBR là chính xác, không cần refine hình học khác.

## 2. Hộp bao tối thiểu MBR là gì?

Với một hình học 2D \(G\), hình chữ nhật bao tối thiểu song song với hai trục được xác định bởi:

\[
\boxed{
\operatorname{MBR}(G)=
[x_{\min},x_{\max}]\times[y_{\min},y_{\max}].
}
\]

Trong đó:

\[
\begin{aligned}
x_{\min}&=\min_{p\in G}p_x,& x_{\max}&=\max_{p\in G}p_x,\\
y_{\min}&=\min_{p\in G}p_y,& y_{\max}&=\max_{p\in G}p_y.
\end{aligned}
\]

Ta dùng **hộp đóng**: cả biên dưới, trên, trái và phải đều được nhận. Một điểm \((4,7)\) có MBR suy biến \([4,4]\times[7,7]\), nhưng **không phải hộp rỗng**.

### Ví dụ từ hình học thật

Cho tam giác có ba đỉnh \(A=(1,1)\), \(B=(5,1)\), \(C=(3,4)\). MBR là:

\[
\boxed{[1,5]\times[1,4]}.
\]

MBR chứa toàn bộ tam giác, nhưng phần lớn các điểm trong hình chữ nhật **không thuộc tam giác**. Nếu một Q rất nhỏ nằm gần góc \((5,4)\), nó có thể giao MBR nhưng **không giao tam giác**. Vì vậy giao MBR chỉ chứng minh **khả năng** giao hình thật.

### Phép hợp hộp bao

Với hai MBR:

\[
A=[a_{x0},a_{x1}]\times[a_{y0},a_{y1}],\quad
B=[b_{x0},b_{x1}]\times[b_{y0},b_{y1}],
\]

hộp bao tối thiểu của cả hai là:

\[
\boxed{
\operatorname{MBR}(A,B)=
[\min(a_{x0},b_{x0}),\max(a_{x1},b_{x1})]
\times
[\min(a_{y0},b_{y0}),\max(a_{y1},b_{y1})].
}
\]

Lưu ý: **hộp bao hợp** không đồng nghĩa hình học *hợp hai hình*. Khoảng trống giữa chúng có thể vẫn nằm trong MBR chung.

### Diện tích và độ tăng diện tích

Với MBR \(R=[x_0,x_1]\times[y_0,y_1]\):

\[
\boxed{area(R)=(x_1-x_0)(y_1-y_0).}
\]

Nếu thêm đối tượng E có hộp bao \(B_E\) vào nhóm đang có hộp R, độ tăng diện tích là:

\[
\boxed{
\Delta A(R,E)=
area(\operatorname{MBR}(R,B_E))-area(R)\ge0.
}
\]

Độ tăng này là heuristic quan trọng khi chọn nhánh để **chèn**. Nó không tự bảo đảm cây cân về số đối tượng hay tối ưu cho mọi truy vấn.

## 3. Khi nào hai MBR giao nhau?

Với hộp đóng A và B, chúng **không giao** nếu tồn tại một trục tách rời:

\[
\boxed{
A.x_{\max}<B.x_{\min}
\;\lor\; B.x_{\max}<A.x_{\min}
\;\lor\;
A.y_{\max}<B.y_{\min}
\;\lor\; B.y_{\max}<A.y_{\min}.
}
\]

Phủ định điều kiện trên cho ta:

\[
\boxed{
\operatorname{intersects}(A,B)\iff
A.x_{\min}\le B.x_{\max}
\land B.x_{\min}\le A.x_{\max}
\land A.y_{\min}\le B.y_{\max}
\land B.y_{\min}\le A.y_{\max}.
}
\]

### Chạm cạnh vẫn được tính là giao

Ví dụ:

\[
A=[0,4]\times[0,4],\quad B=[4,7]\times[2,6].
\]

Hai hộp giao tại đoạn \(\{4\}\times[2,4]\), dù phần giao có diện tích 0. Nếu bài toán tìm tất cả hình **chạm hoặc giao**, phải dùng dấu \(\le\) phù hợp.

Nếu nghiệp vụ yêu cầu *giao có diện tích dương*, cần một predicate khác: với các hình chữ nhật có diện tích dương, phải có độ dài giao **dương trên cả hai trục**, tức:

\[
\max(A.x_{\min},B.x_{\min})<
\min(A.x_{\max},B.x_{\max})
\]

và điều kiện tương tự trên y. Đừng lẫn **giao tập hợp không rỗng** với **giao có diện tích dương**.

### Hộp bao chứa trọn hộp khác

Q chứa B khi:

\[
\boxed{
Q.x_{\min}\le B.x_{\min}\le B.x_{\max}\le Q.x_{\max}
\quad\land\quad
Q.y_{\min}\le B.y_{\min}\le B.y_{\max}\le Q.y_{\max}.
}
\]

Điều kiện chứa trọn giúp xử lý nhanh khi muốn đếm các đối tượng có MBR được Q chứa, nhưng đối với câu hỏi **hình thật chứa/giao Q**, cần xét đúng ý nghĩa hình học và metadata thích hợp.

## 4. Cấu trúc R-tree: nút lá, nút trong và entry

Một R-tree là **cây nhiều nhánh cân bằng theo cấp**. Ta chọn:

- \(M\): **số entry tối đa** trong một node (*maximum fanout*).
- \(m\): **số entry tối thiểu** ở node không phải gốc, thường \(2\le m\le\lfloor M/2\rfloor\) trong cấu hình điển hình.

Hai loại node:

**Nút lá (leaf):** chứa các entry \((MBR(o),ID(o))\). ID dẫn tới dữ liệu hình học thực; mỗi đối tượng thường có **một leaf entry** trong R-tree chuẩn.

**Nút trong (internal):** chứa các entry \((MBR(child),pointer(child))\), mỗi entry chỉ tới một **node con**, còn hộp bao chứa toàn bộ dữ liệu dưới node con ấy.

~~~text
                      ROOT
           +------------+-------------+
           |                          |
      [MBR của A]                [MBR của B]
           |                          |
       NODE A                      NODE B
       /    \                      /   \
    MBR A1 MBR A2              MBR B1 MBR B2
      |      |                   |      |
    LEAF   LEAF                LEAF   LEAF
    o1,o2  o3,o4               o5,o6  o7,o8

R-tree có thể có MBR(A) giao MBR(B).
Một truy vấn giao cả hai MBR phải xem cả hai nhánh.
~~~

### Bất biến cốt lõi

1. **Bao phủ:** MBR của mỗi entry nút trong chứa toàn bộ MBR của các entry thuộc cây con tương ứng.
2. **Cấp lá:** Tất cả lá ở **cùng một độ sâu** từ gốc (*height-balanced* theo cấp).
3. **Sức chứa:** Mọi node không phải gốc có số entry trong \([m,M]\), trừ những trạng thái trung gian lúc split/condense.
4. **Gốc đặc biệt:** Root có thể có ít hơn m entry; một cây một lá là hợp lệ. Sau split gốc, root mới thường có ít nhất 2 con.
5. **Định danh:** Mỗi đối tượng có một ID duy nhất nếu API của bài yêu cầu không trùng ID; không nhầm **đối tượng trùng hộp bao** với đối tượng trùng ID.
6. **Nhất quán cập nhật:** Sau thêm/xóa, entry MBR ở cha phải được cập nhật đủ để luôn bao dữ liệu trong con.

### Phân biệt entry trong và entry lá

| Cấp | Một entry đại diện | MBR của entry lấy từ |
| --- | --- | --- |
| Lá | Đối tượng thật hoặc bản ghi tham chiếu đối tượng | Hình học bao của đối tượng |
| Nút trong | Một cây con | Hợp hộp bao của các entry dưới con |

Không nên gọi mọi entry là “điểm”: trong R-tree, đối tượng có thể là vùng, đoạn, hình chữ nhật hay đa giác.

## 5. Điểm khác biệt lớn: MBR của các nhánh có thể chồng lấn

Xét hai nhóm đối tượng, mỗi nhóm được bao bằng một MBR:

\[
A=[0,6]\times[0,6],
\quad
B=[4,10]\times[4,10].
\]

Phần giao:

\[
\boxed{A\cap B=[4,6]\times[4,6].}
\]

Một cửa sổ nhỏ:

\[
Q=[4.5,5.5]\times[4.5,5.5]
\]

giao **cả A và B**. Dù các entry ở cùng một node, Q có thể phải đi xuống cả hai nhánh.

~~~text
    y
   10         +-----------+ B
              |           |
    6   +-----+---+       |
        | A   | Q |       |
    4   |     +---+-------+
        |         |
    0   +---------+------------- x
        0         6          10

Q nằm trong phần chồng lấn MBR A và MBR B.
~~~

**Điểm quan trọng:** Chồng lấn MBR của nhánh **không có nghĩa một đối tượng phải bị lưu hai lần**. Một object có thể nằm trong **đúng một leaf entry**, nhưng hai MBR *bao nhóm đối tượng khác nhau* có thể giao nhau. Đây là sự khác nhau giữa **đường tìm kiếm có thể phân nhánh** và **trùng dữ liệu**.

### Vì sao chồng lấn làm truy vấn tốn kém?

Nếu Q giao một MBR ở cấp gốc, ta đi một nhánh. Nếu Q giao bốn MBR, ta cần xem cả bốn nhánh vì **mỗi nhánh đều có thể chứa kết quả**. Ở các cấp sâu hơn, hiện tượng này có thể lặp lại.

Các chiến lược nhóm/split thường cố gắng giảm:

- **Overlap:** diện tích giao giữa các MBR anh em.
- **Coverage:** diện tích bao của MBR, bao gồm nhiều vùng không có dữ liệu thật.
- **Perimeter/margin:** tổng chiều dài cạnh hộp, thường liên quan độ trải rộng hình học.

Nhưng không có một thước đo đơn giản nào đảm bảo mọi kiểu truy vấn đều tối ưu. Với dữ liệu đa giác phức tạp hoặc phân bố rất lệch, nhiều MBR có thể vẫn chồng lấn đáng kể.

## 6. Truy vấn giao hình chữ nhật: duyệt tất cả nhánh có thể liên quan

Giả sử Q là hộp chữ nhật truy vấn. Ta phải trả các entry lá có MBR giao Q, rồi nếu cần, kiểm tra hình học thật.

### Thuật toán tìm ứng viên

~~~text
SEARCH(node, Q):
    nếu node rỗng: return
    nếu MBR(node) không giao Q: return

    nếu node là lá:
        với mỗi object-entry e trong node:
            nếu intersects(e.MBR, Q):
                xuất e như một ứng viên
        return

    với mỗi child-entry e của node:
        nếu intersects(e.MBR, Q):
            SEARCH(e.child, Q)
~~~

Nếu node con có MBR **không giao** Q, không một đối tượng bên dưới nó có thể giao Q. Lý do: mọi hộp bao đối tượng đều nằm trong MBR của nhánh. Đây là điều kiện cắt tỉa **không bỏ sót ứng viên thật**.

Ngược lại, nếu MBR một nhánh giao Q, chưa chắc có object-entry nào trong nhánh có MBR giao Q. MBR có thể chứa **khoảng trống** giữa các đối tượng được nhóm.

### Tại sao không đi xuống đúng một nhánh?

Trong **binary search tree** tìm một khóa, phép so sánh tạo đường đi có một lựa chọn trái/phải. Nhưng trong R-tree, hai child-MBR có thể chồng lấn. Khi Q giao cả hai, chỉ đi một nhánh có thể **bỏ sót kết quả** của nhánh còn lại.

~~~mermaid
flowchart TD
    A["Nhận truy vấn Q tại node"] --> B{"MBR node giao Q?"}
    B -->|Không| C["Prune cả cây con"]
    B -->|Có| D{"Node lá?"}
    D -->|Có| E["Kiểm tra từng object-entry: MBR giao Q?"]
    D -->|Không| F["Xét TẤT CẢ child-entry giao Q"]
    F --> G["Đệ quy nhiều nhánh nếu cùng giao"]
    E --> H["Xuất ứng viên, rồi refine hình thật nếu cần"]
~~~

### Broad phase và refine

Nếu entry lưu **chính hình chữ nhật cần tìm**, kiểm tra MBR giao Q là phép kiểm tra chính xác.

Nếu entry đại diện cho **tam giác, đường cong hoặc đa giác**:

\[
\operatorname{geom}(o)\cap Q\ne\varnothing
\Longrightarrow
\operatorname{MBR}(o)\cap Q\ne\varnothing.
\]

Nhưng chiều ngược lại **không luôn đúng**. Do đó:

1. R-tree trả các **ứng viên** có MBR giao Q.
2. Bước **refine** kiểm tra hình học thật.
3. Chỉ trả ứng viên thỏa predicate cuối.

### Truy vấn chứa trọn và truy vấn điểm

**Containment query:** Nếu muốn các object có MBR **nằm trọn trong Q**, một phép giao MBR là chưa đủ; ở lá phải kiểm tra **contains**. Nếu muốn hình học thật được Q chứa, cần predicate chứa hình gốc thích hợp.

**Point query:** Điểm \(q=(q_x,q_y)\) có thể được coi là hộp suy biến:

\[
Q=[q_x,q_x]\times[q_y,q_y].
\]

Do dùng hộp **đóng**, Q vẫn hợp lệ. R-tree trả những đối tượng mà MBR chứa q; hình thật phải refine nếu cần.

## 7. Chi phí truy vấn và ảnh hưởng của overlap

Gọi:

- \(h\): chiều cao cây theo số cấp node.
- \(V\): tổng số node đã thực sự được thăm.
- \(E_V\): tổng số entry kiểm tra ở những node đó.
- \(k_c\): số ứng viên MBR giao Q.
- \(k\): số kết quả hình học thật.

Với mỗi phép giao 2D mất \(O(1)\), chi phí truy vấn là:

\[
\boxed{
T_{\mathrm{search}}
=O(V+E_V+k_c\,T_{\mathrm{refine}}+k).
}
\]

Nếu dữ liệu **chính là hình chữ nhật**, \(T_{\mathrm{refine}}=O(1)\) hoặc có thể bỏ bước refine. Với đa giác hoặc đường phức tạp, refine có chi phí theo số đỉnh/cạnh hay thư viện hình học đang dùng.

### Vì sao không tự động \(O(\log n+k)\)?

Dù cây có cùng độ sâu ở mọi lá, cửa sổ Q có thể **giao rất nhiều MBR anh em**, khiến thuật toán duyệt nhiều nhánh. Trong trường hợp xấu, số entry phải xét gần toàn bộ chỉ mục:

\[
\boxed{T_{\mathrm{search}}=O(n)}
\]

với số chiều cố định và đối tượng hình chữ nhật có kiểm tra giao hằng số, bỏ qua chi phí xuất kết quả. Đây là cận trường hợp xấu, không phải nói R-tree thường chậm như quét tuyến tính.

### Overlap và coverage khác nhau

Hai nhóm có MBR không giao nhau sẽ không tạo **nhân đôi nhánh** cho một vùng Q rất nhỏ. Nhưng một MBR có diện tích bao cực lớn và nhiều khoảng trống vẫn có thể gây duyệt **thừa** dù không giao MBR anh em.

Vì vậy cần xem cả:

- **Overlap giữa MBR anh em:** nhiều nhánh cùng được mở.
- **Coverage của mỗi MBR:** một nhánh được mở dù không chứa đối tượng thật ở vùng Q.
- **Số entry trên một node:** quyết định chi phí quét entry và fanout.
- **Kích thước/trình tự truy vấn:** cửa sổ lớn sẽ chạm nhiều hộp hơn.

Không thể chỉ giảm chiều cao bằng cách tăng fanout rồi kết luận truy vấn sẽ nhanh hơn: fanout lớn cũng khiến mỗi node có **nhiều entry phải kiểm tra**.

## 8. Chọn nhánh khi chèn: tối thiểu hóa độ tăng diện tích

Để đưa một đối tượng E có MBR B vào R-tree, thường chọn **một đường từ gốc xuống lá**, rồi đặt entry ở lá đã chọn.

Tại một node trong với các child-MBR \(R_1,\ldots,R_t\), heuristic cơ bản của R-tree là chọn:

\[
\boxed{
j=\arg\min_i\left(
\operatorname{area}(\operatorname{MBR}(R_i,B))
-\operatorname{area}(R_i)
\right).
}
\]

Tức là chọn nhánh có **độ tăng diện tích** khi bao B **nhỏ nhất**.

### Xử lý hòa để kết quả ổn định

Nếu nhiều nhánh cùng độ tăng diện tích, có thể lần lượt ưu tiên:

1. MBR hiện tại có diện tích nhỏ hơn.
2. Node con có ít entry hơn.
3. Thứ tự vị trí con nhỏ hơn để tạo quyết định ổn định.

Đây là một heuristic minh họa; các biến thể R-tree có thể chọn tiêu chí khác, như tăng overlap hoặc margin ở một số cấp.

### Ví dụ định lượng

Hai child-MBR:

\[
R_A=[0,4]\times[0,4],\qquad
R_B=[6,10]\times[0,4].
\]

Đối tượng mới:

\[
B=[3,5]\times[1,2].
\]

Cho nhánh A:

\[
R'_A=[0,5]\times[0,4],
\quad
\Delta A_A=20-16=\boxed{4}.
\]

Cho nhánh B:

\[
R'_B=[3,10]\times[0,4],
\quad
\Delta A_B=28-16=\boxed{12}.
\]

Do \(4<12\), heuristic chọn **nhánh A**. Điều đó giúp giảm diện tích tăng thêm của MBR ở thời điểm chèn, nhưng **không bảo đảm tối ưu toàn cục** sau nhiều lần chèn.

### Chèn một đối tượng lớn

Nếu B rất rộng và giao nhiều nhóm, R-tree chuẩn thường **chọn một lá** phù hợp để lưu B, thay vì đăng ký object-entry B vào mọi lá mà nó giao như một biến thể spatial grid. Sau đó MBR dọc đường tổ tiên có thể phải mở rộng nhiều.

Điều này giúp giảm việc nhân bản object-entry, nhưng có thể làm **overlap và coverage** của các MBR tăng. Tìm vị trí đặt tốt cho đối tượng lớn là một lý do khiến chiến lược chọn nhóm/split quan trọng.

## 9. Xử lý tràn node: tách thành hai nhóm

Giả sử node chứa tối đa **M** entry. Khi chèn entry thứ **\(M+1\)**, node bị **overflow** và phải được chia (*split*) hoặc xử lý theo chiến lược khác của biến thể.

Với split cơ bản:

1. Phân \(M+1\) entry thành **hai nhóm**.
2. Mỗi nhóm có ít nhất **m** entry.
3. Mỗi nhóm tạo một node ở **cùng cấp** với node cũ.
4. Cha được cập nhật entry MBR của node cũ và thêm entry MBR của node mới.
5. Nếu cha cũng overflow, split có thể lan ngược lên tới root.

Nếu root bị split, tạo **root mới** chứa hai nhánh vừa tách. Điều này tăng chiều cao cây thêm một cấp, đồng thời giữ **mọi lá cùng độ sâu**.

### Ví dụ sức chứa

Chọn \(M=4\), \(m=2\). Một node có 5 entry sẽ cần chia thành hai nhóm có kích thước hợp lệ, như \((2,3)\) hoặc \((3,2)\). Cặp nhóm \((1,4)\) **không hợp lệ** nếu node sau split không phải root và yêu cầu min-fill 2.

### Không phải split là chia miền tại trung điểm

Quadtree thường chia **một vùng** thành bốn phần theo trung điểm. R-tree split **một tập entry** thành hai nhóm, rồi lấy MBR chung của mỗi nhóm. Hai nhóm có thể bao **những vùng chồng lấn nhau**, dù mỗi object-entry thuộc **đúng một nhóm**.

Đây là bản chất của **spatial grouping**, khác với **space partitioning**.

## 10. Heuristic quadratic split: chọn hai hạt giống xa nhau

Một cách split kinh điển là **quadratic split**. Ý tưởng: tìm hai entry nên thuộc hai nhóm khác nhau vì nếu ghép chúng chung sẽ tạo ra **nhiều diện tích bao thừa**.

### Bước 1 — PickSeeds

Với hai entry i, j có MBR \(R_i,R_j\), tính:

\[
\boxed{
waste(i,j)=
\operatorname{area}(\operatorname{MBR}(R_i,R_j))
-\operatorname{area}(R_i)
-\operatorname{area}(R_j).
}
\]

Chọn cặp có **waste lớn nhất** làm hai hạt giống ban đầu của hai nhóm.

**Lưu ý về dấu:** Khi hai MBR chồng lấn, tổng diện tích riêng có thể lớn hơn diện tích MBR bao chung, nên waste có thể **âm**. Công thức vẫn là tiêu chí lựa chọn; đừng giả định waste luôn không âm.

### Bước 2 — PickNext

Với một entry E chưa phân nhóm, tính:

\[
\Delta A=area(\operatorname{MBR}(GroupA,E))-area(GroupA),
\]
\[
\Delta B=area(\operatorname{MBR}(GroupB,E))-area(GroupB).
\]

Chọn entry có chênh lệch **\(|\Delta A-\Delta B|\)** lớn nhất, vì quyết định đưa entry đó vào nhóm nào có tác động khác nhau nhiều nhất.

Đưa E vào nhóm có **độ tăng diện tích nhỏ hơn**. Nếu hòa, có thể ưu tiên diện tích MBR hiện tại nhỏ hơn, rồi số entry ít hơn, cuối cùng theo thứ tự ổn định.

### Bước 3 — Bắt buộc min-fill

Nếu nhóm A hiện có \(a\) entry, còn \(r\) entry chưa phân nhóm, và:

\[
\boxed{a+r=m,}
\]

thì **tất cả entry còn lại phải vào A**, nếu không A sẽ không đạt min-fill. Tương tự cho nhóm B.

Điều kiện này phải được kiểm tra **trước khi chọn PickNext**. Nếu bỏ qua, thuật toán có thể tạo node thiếu số entry tối thiểu.

### Mã giả quadratic split

~~~text
QUADRATIC_SPLIT(items, m):
    seedA, seedB = cặp items có waste lớn nhất
    groupA = [seedA]; groupB = [seedB]
    remaining = items trừ hai seed

    while remaining chưa rỗng:
        nếu len(groupA) + len(remaining) == m:
            đưa hết remaining vào groupA; break
        nếu len(groupB) + len(remaining) == m:
            đưa hết remaining vào groupB; break

        pick = entry có abs(enlargeA - enlargeB) lớn nhất
        đưa pick vào nhóm có:
            (enlargement, diện tích MBR nhóm, số entry) nhỏ hơn
        bỏ pick khỏi remaining

    trả hai nhóm và MBR của mỗi nhóm
~~~

### Vì sao gọi là quadratic?

Việc thử **mọi cặp hạt giống** có khoảng:

\[
\binom{M+1}{2}=O(M^2)
\]

cặp. Các bước chọn entry tiếp theo cũng có thể tốn bậc hai theo số entry của node. Đây là chi phí theo **fanout M tại một node split**, không phải \(O(n^2)\) cho toàn bộ tập đối tượng nếu chỉ split một node kích thước giới hạn.

Ngoài quadratic split, các chiến lược **linear split** hoặc **R\*-tree split** có thể đánh đổi thời gian split để giảm overlap/coverage tốt hơn trên dữ liệu cụ thể.

## 11. Chèn hoàn chỉnh và lan truyền split lên root

Sau khi hiểu chọn nhánh và split, ta ghép chúng thành một thao tác **Insert**.

~~~text
INSERT(root, object):
    bbox = MBR(object)
    leaf = CHOOSE_LEAF(root, bbox)
    thêm object-entry (bbox, object.ID) vào leaf

    từ leaf đi ngược về gốc:
        cập nhật MBR của node hiện tại
        nếu node hiện tại có M+1 entry:
            split node thành hai node cùng cấp
            tại cha:
                sửa entry trỏ tới node cũ
                thêm entry trỏ tới node mới

    nếu root cũ split:
        tạo root mới chứa hai child-entry
~~~

### Hình dung khi root bị tràn

~~~text
Trước split:
             ROOT (5 entries, M=4)
             [e1 e2 e3 e4 e5]

Sau split:
                   NEW ROOT
                  /        \
             GROUP A      GROUP B
             [2 entries]  [3 entries]

Tất cả lá được nâng thêm một cấp dưới root mới.
~~~

Trong chương trình, một cách cài đặt ngắn gọn là cho hàm chèn đệ quy **trả về node anh em mới khi split**. Node cha nhận node ấy, cập nhật MBR, và nếu chính cha tràn thì lại split. Root tạo mới khi hàm chèn vào root trả về một node anh em.

### Chọn lá không tự động không chồng lấn

Một đối tượng B có thể giao MBR của nhiều nhánh. Nhưng thuật toán chèn chọn **một nhánh** theo heuristic, không phải tìm “nhánh duy nhất chứa tọa độ” như một cây chia không gian rời nhau.

Đây là lý do R-tree hỗ trợ các đối tượng lớn linh hoạt hơn cách đặt từng object vào một ô duy nhất, nhưng có thể phải trả giá bằng **nhiều MBR cha giao nhau**.

## 12. Xóa và CondenseTree: xử lý node thiếu entry

Xóa một entry không chỉ là xóa ID tại lá. Sau đó một node có thể còn **ít hơn m entry**, vi phạm min-fill. Thuật toán R-tree cổ điển dùng thủ tục thường gọi là **CondenseTree** để xử lý từ lá về gốc.

### Các bước khái quát

1. **FindLeaf:** Tìm entry lá của đối tượng theo ID và/hoặc MBR; phải khám phá tất cả nhánh MBR có thể chứa đối tượng, vì vùng có thể chồng lấn.
2. **DeleteEntry:** Xóa entry đúng ID khỏi lá.
3. **CondenseTree:** Đi từ lá lên root. Nếu node còn đủ m entry, cập nhật MBR của entry cha. Nếu node thiếu m, loại node khỏi cha và đưa các entry/cây con cần thiết vào danh sách **tái chèn ở đúng cấp**.
4. **Reinsert:** Đưa các mục bị tách ra trở lại cây, bảo toàn cấp của các subtree entry nếu tái chèn nguyên subtree.
5. **Root adjustment:** Nếu root không phải lá và chỉ còn một con, có thể cho con ấy trở thành root mới, làm giảm chiều cao một cấp; nếu không còn đối tượng, trả về root lá rỗng theo quy ước.

### Vì sao phải giữ đúng cấp khi tái chèn?

Giả sử một node trong ở độ sâu 2 có entry trỏ tới các subtree mà lá nằm ở độ sâu 5. Nếu đem entry subtree này gắn trực tiếp vào **lá** khác, cây sẽ không còn giữ bất biến **mọi lá cùng độ sâu**.

Vì thế CondenseTree cần biết **cấp đích** của mục tái chèn, hoặc chọn cách thu tất cả object-entry dưới nhánh bị loại và **chèn lại từ lá**. Cách thứ hai dễ giải thích nhưng có thể tốn hơn.

### Xóa không có nghĩa phải hợp hai MBR

R-tree không phải cây nhị phân chỉ còn hai nhánh để merge. Sau xóa, có thể:

- Chỉ **thu hẹp MBR** của node nếu nó vẫn đủ entry.
- **Loại một node thiếu entry** rồi tái chèn các object/subtree.
- **Thu gọn root** khi nó chỉ có một node con.

Quá trình xóa có thể khiến MBR **nhỏ đi**, giảm coverage và overlap; nhưng nếu metadata không được cập nhật, phép tìm kiếm có thể trở nên kém hiệu quả, thậm chí **sai** nếu một MBR bị làm nhỏ hơn phạm vi dữ liệu thực.

### Một ví dụ số lượng

Với \(M=4,m=2\), node lá chứa 2 đối tượng A,B. Nếu xóa B, node chỉ còn 1 entry; nó thiếu min-fill. Cách CondenseTree có thể loại node này và tái chèn A vào một lá khác. Cha sau khi mất child-entry cũng có thể thiếu m và phải xử lý tiếp.

**Không tùy tiện giữ một node có 1 entry rồi khẳng định cây đã thỏa bất biến min-fill**. Một cài đặt có thể cho phép node thiếu theo chính sách riêng, nhưng khi ấy phải mô tả cấu trúc biến thể ấy rõ ràng.

## 13. Cập nhật, di chuyển và nhất quán dữ liệu

Nếu một tòa nhà đổi biên hình học, một xe di chuyển hoặc một polygon được chỉnh sửa, MBR lưu ở lá có thể thay đổi.

### Cập nhật một đối tượng

Một quy trình an toàn, dễ hiểu:

1. Tìm và xóa object-entry cũ theo ID.
2. Tính **MBR mới** từ hình học mới.
3. Chèn lại object-entry mới theo heuristic.
4. Bảo đảm các entry MBR ở tổ tiên được cập nhật/condense đúng.

Nếu thay MBR ở lá **mà không mở rộng MBR của cha**, một truy vấn giao với vị trí mới có thể thấy MBR cha **không giao Q**, bỏ nhánh và gây **false negative**.

### Object-ID và tọa độ/hình học

Hai hình chữ nhật giống hệt có thể tương ứng hai đối tượng khác nhau:

~~~text
ID shop-17: [2,4] × [3,5]
ID shop-23: [2,4] × [3,5]
~~~

Chúng phải được lưu và truy vấn như **hai object-entry khác ID**, trừ khi nghiệp vụ chủ động khử trùng đối tượng theo khóa khác. Không được coi MBR là ID.

Nếu đối tượng hình học thay đổi nhưng ID không đổi, cần cập nhật **một phiên bản nhất quán** của dữ liệu hình học và chỉ mục. Dữ liệu chỉ mục mới nhưng hình học gốc cũ (hoặc ngược lại) có thể tạo false positive/false negative bất ngờ.

### Xử lý đồng thời

Trong hệ thống nhiều luồng hoặc cơ sở dữ liệu, thao tác cập nhật R-tree có thể liên quan **nhiều node** từ lá lên gốc. Một truy vấn đang duyệt không nên thấy MBR cha đã sửa nhưng con chưa sửa hoặc một split mới hoàn thành một nửa.

Các triển khai production cần cơ chế khóa/latch, giao dịch, snapshot hoặc copy-on-write thích hợp. Cây Python minh họa ở phần sau chỉ phục vụ **thao tác tuần tự**, không tự bảo đảm an toàn đa luồng.

## 14. Các biến thể: R-tree, R+-tree, R*-tree

Không phải mọi cấu trúc có tên R-tree đều dùng chính xác cùng quy tắc nhóm và tách.

| Cấu trúc | Ý tưởng đáng chú ý | Đánh đổi |
| --- | --- | --- |
| **R-tree cơ bản** | Object-entry nằm ở lá; nhóm theo MBR, MBR anh em có thể chồng lấn | Dễ hiểu, chồng lấn có thể làm tìm nhiều nhánh |
| **R\*-tree** | Chọn chèn/split dựa thêm overlap, margin; có thể **forced reinsertion** khi overflow | Thường tìm cách cải thiện chất lượng nhóm, nhưng tốn xử lý chèn |
| **R+-tree** | Tìm cách giảm/tránh overlap ở các vùng của nút trong bằng cách chia nhỏ vùng và có thể nhân bản tham chiếu đối tượng cắt ranh giới | Query có thể duyệt ít nhánh chồng lấn hơn nhưng chèn/xóa và dedup phức tạp |
| **R-tree bulk-loaded STR** | Xây nhóm hàng loạt bằng sắp theo không gian rồi đóng các node | Phù hợp dữ liệu tĩnh/khối lượng lớn; chèn động vẫn cần cơ chế cập nhật |

### R\*-tree và forced reinsertion

Một kỹ thuật của R\*-tree là khi một node overflow, **không nhất thiết split ngay**. Nó có thể chọn một phần entry để **tái chèn** ở cùng cấp phù hợp, nhằm cải thiện việc nhóm. Để tránh vòng lặp vô hạn khi một thao tác chèn làm overflow lặp lại, thuật toán cần kiểm soát việc forced reinsertion theo **cấp trong cùng một chuỗi chèn**.

Không nên mô tả R\*-tree như chỉ thay quadratic split bằng một công thức khác. Tối ưu của R\*-tree có thể liên quan **chọn subtree, chọn trục split, thứ tự phân phối và forced reinsertion**.

### R+-tree và trùng tham chiếu

R-tree thường giữ một object-entry tại một lá. R+-tree có thể phân chia các vùng để giảm overlap nhưng cần **lưu nhiều tham chiếu** cho một hình cắt qua nhiều vùng. Query trả object có thể phải **dedup theo ID**. Cần phân biệt sự nhân bản này với hiện tượng hai **MBR của hai nhóm chồng lấn** trong R-tree cơ bản.

### Các biến thể 3D hoặc nhiều chiều

R-tree có thể dùng **minimum bounding box** trong \(d\) chiều:

\[
B=\prod_{i=1}^{d}[lo_i,hi_i].
\]

Các phép giao, hợp bao và diện tích mở rộng tổng quát thành **thể tích hộp** khi d=3 hoặc **hypervolume** trong \(d\) chiều. Nhưng với d cao, MBR có thể trở nên kém chọn lọc và chồng lấn đáng kể; không nên giả định chỉ cần tăng số chiều là hiệu năng luôn giữ nguyên.

## 15. Bulk loading: xây cây theo lô bằng STR

Nếu có hàng triệu đối tượng **gần như tĩnh**, chèn từng object vào R-tree có thể khiến chất lượng nhóm phụ thuộc thứ tự chèn. Một chiến lược dựng hàng loạt phổ biến là **Sort-Tile-Recursive (STR)**.

Trong 2D, ý tưởng mức cao của STR:

1. Tính MBR và **tâm hộp** của từng đối tượng.
2. Sắp các entry theo tọa độ x của tâm.
3. Chia thành các **dải (slices)** x, mỗi dải chứa một lượng entry đủ để đóng các node.
4. Trong từng dải, sắp theo tọa độ y của tâm.
5. Đóng tối đa M entry thành mỗi node lá.
6. Tạo entry MBR cho các node vừa đóng và **lặp lại ở các cấp trên** cho tới khi chỉ còn root.

~~~text
               Các object-MBR trong 2D
                    |
               Sort theo center-x
                    |
             Chia thành các dải x
                    |
          Sort center-y trong từng dải
                    |
           Đóng các nhóm tối đa M entry
                    |
              Node lá cùng cấp
                    |
             Lặp lại với MBR node
                    |
                   ROOT
~~~

### Số dải

Nếu có \(n\) entry và mỗi node chứa tối đa M, số nhóm lá mục tiêu là:

\[
g=\left\lceil\frac nM\right\rceil.
\]

Một phiên bản STR 2D có thể chọn khoảng:

\[
\boxed{s=\lceil\sqrt g\rceil}
\]

dải trên trục x, sau đó nhóm theo y trong từng dải. Đây là cách mô tả **lược đồ**; khi triển khai phải xử lý các trường hợp nhóm cuối thiếu m entry, số entry nhỏ hơn M, và chính sách phân phối để tránh node không đủ min-fill.

### Bulk loading không phải dynamic insertion

STR ưu tiên tạo cây tốt từ **toàn bộ tập dữ liệu hiện có**. Khi một đối tượng mới đến, không thể chỉ thêm vào danh sách đã sắp rồi mặc định cây còn đúng. Có thể:

- Chèn động bằng heuristic R-tree.
- Giữ một chỉ mục delta rồi định kỳ merge/rebuild.
- Rebuild toàn bộ khi cập nhật đủ nhiều.

Tổng chi phí phải tính cả **xây dựng, truy vấn, cập nhật và số lần rebuild**, không chỉ một lần truy vấn trên cây mới xây.

## 16. Nearest neighbor trên R-tree: khoảng cách tới MBR là cận dưới

R-tree không chỉ hỗ trợ cửa sổ chữ nhật; nó cũng có thể hỗ trợ **láng giềng gần nhất** với một điểm truy vấn \(q=(q_x,q_y)\).

Với hộp đóng \(B=[x_0,x_1]\times[y_0,y_1]\), khoảng cách Euclid bình phương từ q tới hộp là:

\[
\boxed{
\operatorname{minDist}^2(q,B)=
\delta_x^2+\delta_y^2,
}
\]

trong đó:

\[
\delta_x=\max(x_0-q_x,\;0,\;q_x-x_1),\qquad
\delta_y=\max(y_0-q_y,\;0,\;q_y-y_1).
\]

Vì mọi điểm hình học thuộc một object đều nằm trong MBR object, ta có:

\[
\boxed{
\operatorname{distance}^2(q,\operatorname{geom}(o))
\ge\operatorname{minDist}^2(q,\operatorname{MBR}(o)).
}
\]

Đối với node trong, cận minDist của MBR node cũng là cận dưới cho **mọi đối tượng trong cây con**.

### Best-first bằng hàng đợi ưu tiên

1. Đưa root vào **min-heap** theo minDist² tới MBR root.
2. Lấy node có cận nhỏ nhất ra.
3. Nếu cận lớn hơn bình phương khoảng cách tốt nhất tới **đối tượng thật**, có thể dừng hoặc bỏ nhánh.
4. Với node trong, thêm những node con với cận minDist².
5. Với node lá, đánh giá khoảng cách tới object-entry, dùng **hình thật** nếu nghiệp vụ hỏi khoảng cách tới hình gốc.
6. Tiếp tục tới khi heap rỗng hoặc cận nhỏ nhất còn lại không thể thắng best.

**Quy tắc tie:** Nếu cùng khoảng cách và muốn ID nhỏ nhất, không bỏ nhánh chỉ vì minDist² bằng best²; một nhánh khác có thể có object cùng khoảng cách nhưng ID ưu tiên hơn.

### Ví dụ hình bao chứa điểm truy vấn

Cho một polygon hình chữ U có MBR \([0,10]\times[0,10]\), truy vấn tại \(q=(5,5)\) ở **khoảng rỗng giữa chữ U**.

- minDist² tới MBR là **0** vì q nằm trong MBR.
- Khoảng cách thật từ q tới polygon có thể **dương**.

Vì vậy không được trả polygon ấy với khoảng cách 0 chỉ vì MBR chứa q. Cận dưới dùng để **ưu tiên và prune**, không thay thế hàm khoảng cách hình học thật.

### kNN trên R-tree

Với kNN, giữ **max-heap k ứng viên thật**. Khi đã có đủ k đối tượng, dùng khoảng cách của ứng viên tệ nhất làm ngưỡng prune vùng; nếu chưa đủ k, không được loại nhánh chỉ vì nó xa hơn một ứng viên duy nhất. Khi object có nhiều tham chiếu trong một biến thể chỉ mục, **dedup theo ID** trước khi đếm top-k.

### Khoảng cách tới hình chữ nhật

Nếu đối tượng **chính là hình chữ nhật đóng B**, minDist(q,B) bằng khoảng cách hình học thật từ điểm q tới đối tượng B. Khi ấy bước đánh giá entry lá chỉ cần tính cùng công thức, không cần polygon-distance.

Nếu object là **điểm**, MBR suy biến tại tọa độ điểm, minDist(q,B) trở thành khoảng cách Euclid bình phương giữa hai điểm.

## 17. So sánh R-tree với k-d tree, quadtree và spatial grid

| Cấu trúc | Dữ liệu thường phù hợp | Nguyên tắc tổ chức | Điểm dễ nhầm |
| --- | --- | --- | --- |
| **R-tree** | Hộp, đường, đa giác, đối tượng có diện tích | Nhóm object bằng MBR, có thể chồng lấn | Một Q có thể phải đi nhiều nhánh |
| **k-d tree** | Điểm ít chiều, tương đối tĩnh | Split theo một trục ở mỗi node | Trục chia thay đổi; NN phải backtrack |
| **Quadtree/Octree** | Vùng 2D/3D, point cloud/voxel | Chia một vùng thành 4/8 miền con | Vùng phân hoạch thường có luật sở hữu riêng |
| **Uniform grid** | Điểm/vật thể có scale tương đối đều | Kích thước ô cố định | Chọn kích thước ô quyết định rất nhiều |
| **Spatial hash** | Lưới trên miền rộng/thưa | Chỉ lưu bucket của ô có dữ liệu | Truy vấn qua ô trống vẫn có chi phí nếu phải liệt kê |
| **Quét tuyến tính** | n nhỏ, truy vấn ít, cập nhật nhiều | Không tạo chỉ mục | Chi phí mỗi truy vấn theo n nhưng rất đơn giản |

### Ví dụ lựa chọn theo workload

**Bản đồ các đa giác địa chính:** R-tree/R\*-tree là ứng viên tự nhiên vì mỗi đối tượng có một MBR và truy vấn giao hình, chứa hình được dùng nhiều.

**Một triệu điểm 2D, thay đổi ít:** k-d tree hoặc spatial grid/quadtree có thể cạnh tranh tốt; cần benchmark theo loại truy vấn.

**Phân tử hoặc voxel trong mô phỏng 3D:** octree phù hợp khi cần biểu diễn độ phân giải theo vùng; R-tree 3D cũng có thể dùng cho hộp vật thể nhưng không tự có lợi thế hơn mọi cách chia vùng.

**Một vài trăm vật thể cập nhật mỗi khung hình:** quét trực tiếp hoặc một grid đơn giản đôi khi có tổng chi phí thấp hơn việc liên tục sửa/condense một cây nhiều cấp.

### Không có một “cấu trúc nhanh nhất”

Hiệu quả phụ thuộc vào:

- Kiểu đối tượng là điểm, hình chữ nhật hay polygon.
- Tỷ lệ truy vấn giao, chứa, NN/radius và cập nhật.
- Độ chồng lấn giữa các object-MBR.
- Hệ tọa độ và metric.
- Dữ liệu nằm trong RAM hay ngoài bộ nhớ.
- Số chiều và phân bố theo cụm.

Chọn một cấu trúc chỉ vì độ cao cây là \(O(\log n)\) có thể bỏ qua **chi phí mở nhiều nhánh** do overlap.

## 18. Chi phí theo fanout, chiều cao và dữ liệu

Giả sử mỗi node không phải gốc giữ từ m đến M entry, còn mọi lá cùng cấp. Với n object-entry trong cây, độ cao theo số cấp **có thể khá nhỏ** khi M lớn, vì mỗi node chứa nhiều entry.

### Chiều cao và số trang

Với các node gần đầy M entry và cân bằng theo cấp, số node lá xấp xỉ \(n/M\), số node cấp trên xấp xỉ \(n/M^2\), v.v. Chiều cao thường khoảng:

\[
\boxed{h\approx\log_M n}
\]

trong điều kiện **fanout hữu hiệu** gần M; đây là ước lượng, không phải bảo đảm truy vấn chỉ thăm h node.

Với min-fill m, cấu trúc không phải gốc có ít nhất m entry giúp giới hạn hiện tượng node quá thưa, nhưng các trường hợp có gốc ít entry, node ở mức khác và quá trình split/xóa đều cần xử lý riêng.

### Bảng đánh đổi

| Hoạt động | Chi phí cần quan tâm | Vì sao |
| --- | --- | --- |
| Search | Số node và entry kiểm tra; số ứng viên refine | Overlap có thể khiến mở nhiều nhánh |
| ChooseLeaf | Quét tới M child-entry ở mỗi cấp | So độ tăng diện tích và tie-break |
| Split | Quadratic split \(O(M^2)\) tại node | Chọn seed và phân phối entry |
| Insert | Một đường xuống + cập nhật ngược + có thể split lan cấp | Fanout và diện tích nhóm ảnh hưởng |
| Delete | Tìm leaf + CondenseTree + reinsert | Có thể duyệt nhiều nhánh vì overlap |
| NN/kNN | MinDist, thứ tự hàng đợi, số entry hình thật | Cận MBR có thể lỏng |
| Bộ nhớ | Object-entry, child-entry, MBR và con trỏ | Fanout/độ lấp đầy quyết định overhead |
| I/O | Số trang đọc/ghi khi dữ liệu ngoài RAM | R-tree thường được thiết kế theo page/block |

### Cận trường hợp xấu

Với object rectangle và giao rectangle 2D, truy vấn có thể phải kiểm tra \(O(n)\) object-entry nếu gần như mọi MBR cấp cao đều giao Q. Việc mỗi node có M entry không loại bỏ trường hợp xấu này; nó chỉ đổi cách nhóm node và số I/O.

Đối với chèn, một đường xuống thường cần \(O(Mh)\) phép xét child-entry theo heuristic, còn split có thể phát sinh ở nhiều cấp. Nếu từng cấp dùng quadratic split, chi phí split riêng một đường có thể đến \(O(hM^2)\) trong một chuỗi overflow, chưa kể chi phí I/O/ghi log.

### Tối ưu bộ nhớ ngoài

Trong cơ sở dữ liệu, mỗi node thường được thiết kế để vừa **một trang đĩa**. Một phép tìm đọc số ít node có thể giảm số trang I/O so với quét toàn bộ dữ liệu.

Nhưng nếu các MBR overlap lớn, một truy vấn nhỏ vẫn có thể tải nhiều trang từ những nhánh khác nhau. Vì thế đánh giá R-tree cần cả **độ lấp đầy trang**, **số trang truy cập** và **độ chọn lọc của MBR**, không chỉ h.

## 19. Dữ liệu địa lý và hệ tọa độ

R-tree nhóm MBR trong **hệ tọa độ được lưu**, chứ không tự hiểu quả đất hay đơn vị khoảng cách.

### Kinh độ/vĩ độ

Với \((longitude,latitude)\) theo độ:

- R-tree có thể dùng MBR theo độ để lọc hình học/truy vấn cửa sổ.
- Diện tích MBR theo **độ vuông** không phải diện tích mặt đất theo mét vuông.
- Vùng cắt qua kinh tuyến đổi ngày \(-180^\circ/+180^\circ\) có thể cần **tách thành nhiều hộp** hoặc dùng mô hình wraparound.
- Khi cần khoảng cách bán kính hoặc NN **theo mét**, minDist Euclid từ tọa độ độ không tự là cận hợp lệ theo metric địa lý. Phải dùng CRS, phép chiếu và cận khoảng cách đúng.

### Trục z và thời gian

Một R-tree 3D dùng hộp \([x_0,x_1]\times[y_0,y_1]\times[z_0,z_1]\). Nếu trục thứ ba là **thời gian**, các phép giao hộp 3D vẫn có nghĩa cho truy vấn không gian–thời gian, nhưng **thể tích hộp** sẽ mang đơn vị m²·giây (nếu x/y theo mét), không phải m³.

Vì vậy heuristic tăng volume cần được đánh giá theo ý nghĩa đơn vị và workload; metric NN hỗn hợp x/y/t cần **trọng số hoặc chuẩn hóa** có chủ đích.

### Bảo toàn tính đúng khi qua CRS

Nếu object gốc được lưu ở hệ tọa độ A nhưng Q đến từ hệ B, phải chuyển cùng hệ hoặc dùng phép biến đổi hình học/bounding box **bảo thủ**. Chỉ chuyển hai góc của một hộp trong một phép chiếu phi tuyến chưa chắc bao đủ toàn bộ đường biên sau biến đổi.

Một hộp biến đổi **quá nhỏ** có thể làm R-tree bỏ sót đối tượng; một hộp bảo thủ rộng hơn có thể làm tìm thừa nhưng vẫn giữ tính đúng.

## 20. Python: xây R-tree 2D bằng quadratic split

Ví dụ dưới đây dùng **Python 3.10+** và thư viện chuẩn. Mỗi object-entry lưu một **hình chữ nhật đóng**; vì vậy tìm giao và khoảng cách tới đối tượng được tính **trực tiếp bằng MBR**, không cần polygon refine.

Ví dụ hỗ trợ:

- Chèn bản ghi hình chữ nhật có **ID duy nhất**.
- Tìm lá bằng **độ tăng diện tích MBR** nhỏ nhất.
- Split node overflow theo **quadratic split** có kiểm soát min-fill.
- Lan truyền split lên root, bảo đảm lá cùng cấp.
- Truy vấn tất cả ID có hình chữ nhật giao Q.
- Tìm **một hình chữ nhật gần điểm q nhất** bằng cận minDist trên các MBR.
- Kiểm tra bất biến sức chứa, cấp lá, MBR và ID.

**Quy ước:** Các hộp đều đóng, kể cả hộp suy biến tại một điểm/đoạn; chạm cạnh là giao. Chỉ có **một object-entry cho mỗi ID**, không có thao tác xóa/CondenseTree trong mã minh họa.

~~~python
from __future__ import annotations

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import isfinite


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        bounds = (self.x0, self.y0, self.x1, self.y1)
        if not all(isfinite(x) for x in bounds):
            raise ValueError("Biên hộp phải hữu hạn")
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("Cận min không được lớn hơn max")

    def union(self, other: Rect) -> Rect:
        return Rect(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def intersects(self, other: Rect) -> bool:
        return not (
            self.x1 < other.x0 or other.x1 < self.x0
            or self.y1 < other.y0 or other.y1 < self.y0
        )

    def contains(self, other: Rect) -> bool:
        return (
            self.x0 <= other.x0 <= other.x1 <= self.x1
            and self.y0 <= other.y0 <= other.y1 <= self.y1
        )

    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def min_dist_sq(self, q: tuple[float, float]) -> float:
        dx = max(self.x0 - q[0], 0.0, q[0] - self.x1)
        dy = max(self.y0 - q[1], 0.0, q[1] - self.y1)
        return dx * dx + dy * dy


@dataclass(frozen=True)
class ObjectEntry:
    id: str
    bbox: Rect


@dataclass
class RNode:
    leaf: bool
    entries: list = field(default_factory=list)
    bbox: Rect | None = None


class SimpleRTree:
    def __init__(self, max_entries: int = 4, min_entries: int = 2):
        if (type(max_entries) is not int
                or type(min_entries) is not int
                or max_entries < 4
                or min_entries < 2
                or min_entries > max_entries // 2):
            raise ValueError("Cần M>=4 và 2<=m<=floor(M/2)")
        self.M = max_entries
        self.m = min_entries
        self.root = RNode(leaf=True)
        self.ids: set[str] = set()

    @staticmethod
    def _box(entry) -> Rect:
        # ObjectEntry.bbox hoặc RNode.bbox.
        assert entry.bbox is not None
        return entry.bbox

    def _recalc(self, node: RNode):
        if not node.entries:
            node.bbox = None
            return
        result = self._box(node.entries[0])
        for entry in node.entries[1:]:
            result = result.union(self._box(entry))
        node.bbox = result

    @staticmethod
    def _enlarge(box: Rect, other: Rect) -> float:
        return box.union(other).area() - box.area()

    def _choose_child(self, node: RNode, rect: Rect) -> RNode:
        def key(pair):
            index, child = pair
            box = self._box(child)
            return (
                self._enlarge(box, rect),
                box.area(),
                len(child.entries),
                index,
            )
        return min(enumerate(node.entries), key=key)[1]

    def _split(self, node: RNode) -> RNode:
        """Mutate node thành nhóm A; trả sibling cùng cấp là nhóm B."""
        items = list(node.entries)
        assert len(items) == self.M + 1

        # PickSeeds: cặp có diện tích bao thừa (waste) lớn nhất.
        seed_pair = None
        best_waste = float("-inf")
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a = self._box(items[i])
                b = self._box(items[j])
                waste = a.union(b).area() - a.area() - b.area()
                if waste > best_waste:
                    best_waste = waste
                    seed_pair = (i, j)

        i, j = seed_pair
        group_a = [items[i]]
        group_b = [items[j]]
        box_a = self._box(items[i])
        box_b = self._box(items[j])
        remaining = [
            item for index, item in enumerate(items)
            if index not in (i, j)
        ]

        while remaining:
            # Giữ min-fill cho cả hai node sau split.
            if len(group_a) + len(remaining) == self.m:
                group_a.extend(remaining)
                remaining.clear()
                break
            if len(group_b) + len(remaining) == self.m:
                group_b.extend(remaining)
                remaining.clear()
                break

            # PickNext: entry có độ chênh enlargement lớn nhất.
            chosen_index = max(
                range(len(remaining)),
                key=lambda pos: abs(
                    self._enlarge(box_a, self._box(remaining[pos]))
                    - self._enlarge(box_b, self._box(remaining[pos]))
                ),
            )
            entry = remaining.pop(chosen_index)
            rect = self._box(entry)
            key_a = (
                self._enlarge(box_a, rect),
                box_a.area(),
                len(group_a),
                0,
            )
            key_b = (
                self._enlarge(box_b, rect),
                box_b.area(),
                len(group_b),
                1,
            )
            if key_a <= key_b:
                group_a.append(entry)
                box_a = box_a.union(rect)
            else:
                group_b.append(entry)
                box_b = box_b.union(rect)

        # Các nhóm không được vi phạm min-fill hoặc max-fill.
        assert self.m <= len(group_a) <= self.M
        assert self.m <= len(group_b) <= self.M

        node.entries = group_a
        self._recalc(node)
        sibling = RNode(leaf=node.leaf, entries=group_b)
        self._recalc(sibling)
        return sibling

    def _insert(self, node: RNode, record: ObjectEntry):
        if node.leaf:
            node.entries.append(record)
        else:
            child = self._choose_child(node, record.bbox)
            new_sibling = self._insert(child, record)
            if new_sibling is not None:
                node.entries.append(new_sibling)

        self._recalc(node)
        if len(node.entries) > self.M:
            return self._split(node)
        return None

    def insert(self, item_id: str, bbox: Rect):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        if not isinstance(bbox, Rect):
            raise TypeError("bbox phải là Rect")
        if item_id in self.ids:
            raise ValueError("ID đã tồn tại")

        record = ObjectEntry(item_id, bbox)
        sibling = self._insert(self.root, record)
        if sibling is not None:
            new_root = RNode(
                leaf=False, entries=[self.root, sibling]
            )
            self._recalc(new_root)
            self.root = new_root
        self.ids.add(item_id)

    def search(self, window: Rect) -> list[str]:
        """Trả ID của mọi hình chữ nhật đóng giao window."""
        if not isinstance(window, Rect):
            raise TypeError("window phải là Rect")
        hits = []

        def visit(node):
            if node.bbox is None or not node.bbox.intersects(window):
                return
            if node.leaf:
                for record in node.entries:
                    if record.bbox.intersects(window):
                        hits.append(record.id)
            else:
                for child in node.entries:
                    if child.bbox.intersects(window):
                        visit(child)

        visit(self.root)
        return sorted(hits)

    def nearest_rectangle(self, q: tuple[float, float]):
        """Trả ID hình chữ nhật gần q nhất, tie theo ID."""
        q = tuple(float(v) for v in q)
        if len(q) != 2 or not all(isfinite(v) for v in q):
            raise ValueError("q phải gồm hai tọa độ hữu hạn")
        if self.root.bbox is None:
            return None

        # Min-heap những node/object chưa xử lý.
        frontier = []
        serial = 0
        heappush(
            frontier, (self.root.bbox.min_dist_sq(q), serial, self.root)
        )
        best = None  # (distance², ID)

        while frontier:
            bound, _, item = heappop(frontier)
            if best is not None and bound > best[0]:
                break  # Mọi mục còn lại có lower bound >= bound.

            if isinstance(item, ObjectEntry):
                candidate = (item.bbox.min_dist_sq(q), item.id)
                if best is None or candidate < best:
                    best = candidate
                continue

            # RNode: các entry chứa hộp bao là cận dưới hợp lệ.
            for entry in item.entries:
                serial += 1
                heappush(
                    frontier,
                    (self._box(entry).min_dist_sq(q), serial, entry),
                )

        return best[1] if best is not None else None

    def validate(self) -> bool:
        """Kiểm tra cùng cấp lá, min-fill, MBR và ID."""
        leaf_depths = set()
        seen = set()

        def walk(node: RNode, depth: int, is_root: bool):
            count = len(node.entries)
            if is_root:
                if count > self.M:
                    raise AssertionError("Root vượt sức chứa")
                if not node.leaf and count < 2:
                    raise AssertionError("Root trong cần >=2 con")
            elif not (self.m <= count <= self.M):
                raise AssertionError("Vi phạm min-fill/max-fill")

            if node.leaf:
                leaf_depths.add(depth)
                for record in node.entries:
                    if not isinstance(record, ObjectEntry):
                        raise AssertionError("Lá không chứa object-entry")
                    if record.id in seen:
                        raise AssertionError("ID trùng")
                    seen.add(record.id)
            else:
                for child in node.entries:
                    if not isinstance(child, RNode):
                        raise AssertionError("Node trong phải chứa node")
                    walk(child, depth + 1, False)

            if not node.entries:
                expected = None
            else:
                expected = self._box(node.entries[0])
                for entry in node.entries[1:]:
                    expected = expected.union(self._box(entry))
            if node.bbox != expected:
                raise AssertionError("MBR của node không đúng")

        walk(self.root, 0, True)
        if len(leaf_depths) != 1:
            raise AssertionError("Lá không cùng độ sâu")
        if seen != self.ids:
            raise AssertionError("Bộ ID và cây không khớp")
        return True
~~~

### Phân tích những điểm thiết kế quan trọng

**Nút trong sử dụng tham chiếu node con:** Để mã gọn, mỗi RNode con vừa đại diện **child-entry**, vừa giữ trường bbox tương ứng. Trong hệ cơ sở dữ liệu, child-entry thường tách riêng thành \((MBR,pointer/pageID)\), còn node con nằm trên một page khác.

**Một object-entry chỉ thuộc một lá:** Mặc dù hai MBR nhánh có thể chồng lấn, thuật toán _choose_child chỉ chọn một con. Vì thế search không cần tập seen trong ví dụ R-tree cơ bản; nếu một biến thể chủ động nhân bản object-entry, phải dedup.

**Sức chứa cố định:** Mỗi split xảy ra khi node có đúng M+1 entry. Quadratic split có hai hạt giống và đảm bảo min-fill, còn root có quy tắc đặc biệt.

**BBox cập nhật lên cha:** Hàm _insert gọi _recalc trên đường quay về sau khi con có thể split. Điều này duy trì MBR của node trong **bao đúng tất cả đối tượng của nhánh**.

**Nearest tìm hình chữ nhật, không phải tâm:** nearest_rectangle dùng khoảng cách từ q tới **toàn bộ hình chữ nhật**. Một hình chữ nhật rất lớn bao q có khoảng cách 0 dù **tâm** của nó có thể ở xa q. Nếu ứng dụng muốn hình có tâm gần nhất, cần lưu/định nghĩa metric khác.

**Không chạy đồng thời:** Trong ví dụ, thao tác insert thay nhiều node tại chỗ. Nó không thiết kế cho truy vấn đọc xen giữa một lần insert; hệ thống production cần cơ chế nhất quán dữ liệu.

## 21. Python: kiểm chứng quadratic split và phép tìm giao

Đoạn sau **nối tiếp** các lớp Rect, ObjectEntry, RNode và SimpleRTree ở mục 20. Dữ liệu gồm các hình chữ nhật tách nhau, chạm cạnh, chồng lấn và một object điểm suy biến.

~~~python
rectangles = [
    ("A", Rect(0, 0, 2, 2)),
    ("B", Rect(3, 0, 5, 2)),
    ("C", Rect(0, 4, 2, 6)),
    ("D", Rect(3, 4, 5, 6)),
    ("E", Rect(8, 8, 10, 10)),
    ("F", Rect(9, 0, 11, 2)),
    ("G", Rect(4, 4, 7, 7)),
    ("H", Rect(-2, -2, -1, -1)),
    ("I", Rect(0, 0, 0, 0)),  # Hộp suy biến là một điểm.
]

tree = SimpleRTree(max_entries=4, min_entries=2)

for item_id, rect in rectangles:
    tree.insert(item_id, rect)
    assert tree.validate()

assert not tree.root.leaf  # Sau 9 entry, M=4 cần nhiều cấp.
assert tree.ids == {item_id for item_id, _ in rectangles}

# Q chạm các cạnh nên A,B,C,D,G đều giao.
assert tree.search(Rect(1, 1, 4, 4)) == [
    "A", "B", "C", "D", "G"
]

# Giao với hai MBR phía xa.
assert tree.search(Rect(6, 3, 9, 9)) == ["E", "G"]

# Hộp query suy biến ở (0,0) giao A và I.
assert tree.search(Rect(0, 0, 0, 0)) == ["A", "I"]

assert tree.search(Rect(50, 50, 60, 60)) == []

# R-tree này tìm hình chữ nhật gần q, không tìm tâm hộp.
assert tree.nearest_rectangle((6, 4)) == "G"

# Bốn hộp A,B,C,D cùng dist²=1.25 tới (2.5,3);
# quy tắc ID nhỏ hơn chọn A.
assert tree.nearest_rectangle((2.5, 3)) == "A"


def brute_intersections(rows, query):
    return sorted(
        item_id for item_id, box in rows
        if box.intersects(query)
    )


def brute_nearest(rows, query):
    return min(
        (box.min_dist_sq(query), item_id)
        for item_id, box in rows
    )[1]


windows = [
    Rect(1, 1, 4, 4),
    Rect(6, 3, 9, 9),
    Rect(0, 0, 0, 0),
    Rect(-3, -3, 1, 1),
    Rect(50, 50, 60, 60),
]
for query in windows:
    assert tree.search(query) == brute_intersections(
        rectangles, query
    )

for query in [(0, 0), (6, 4), (2.5, 3), (20, 20)]:
    assert tree.nearest_rectangle(query) == brute_nearest(
        rectangles, query
    )

# Hai object có thể có hộp giống hệt nhưng ID riêng.
tree.insert("J", Rect(0, 0, 2, 2))
assert tree.search(Rect(0, 0, 0, 0)) == ["A", "I", "J"]
assert tree.validate()

# Trường hợp bất lợi: nhiều object-MBR là cùng một điểm.
same_point = SimpleRTree(max_entries=4, min_entries=2)
for n in range(20):
    same_point.insert(f"p{n:02d}", Rect(2, 2, 2, 2))
    assert same_point.validate()
assert len(same_point.search(Rect(2, 2, 2, 2))) == 20
assert same_point.nearest_rectangle((2, 2)) == "p00"

empty = SimpleRTree()
assert empty.search(Rect(0, 0, 1, 1)) == []
assert empty.nearest_rectangle((0, 0)) is None
assert empty.validate()
~~~

### Kiểm thử độc lập phát hiện điều gì?

**Quét tuyến tính** kiểm tra giao từng rectangle mà không dùng MBR của node, không chọn nhánh và không quadratic split. Nếu thuật toán insert tạo MBR cha thiếu dữ liệu, phép search có thể sai trong khi brute-force vẫn đúng.

Test **mỗi lần chèn đều validate** giúp phát hiện sớm node thiếu m entry, node vượt M, lá không cùng cấp hoặc MBR stale. Test **điểm suy biến** xác nhận giao của hộp đóng không đòi diện tích dương; test **20 MBR trùng nhau** xác nhận ID không bị gộp và split vẫn hữu hạn.

**Lưu ý:** Đây là mã hướng dẫn để người học tự chạy và kiểm chứng. Theo giới hạn tác vụ biên soạn STEP 4, tác giả **không thực thi Python** trong bước viết bài; các assert được viết ra không phải xác nhận đã chạy kiểm thử tự động.

## 22. Hạn chế và kiểm soát tính đúng trong code minh họa

Mã ở mục 20 chủ yếu giải thích chèn, tách và tìm kiếm, không hướng đến tối ưu dữ liệu lớn.

**Không cài xóa:** Để thêm xóa thực tế, cần FindLeaf/CondenseTree, tái chèn đúng cấp, xử lý root co chiều cao và duy trì bộ ID nhất quán. Không nên xóa khỏi một danh sách lá tùy ý rồi để node dưới min-fill.

**Chưa lưu polygon:** Các object trong ví dụ chính là Rect. Nếu thay bằng hình thật, phải lưu tham chiếu hình gốc và refine bằng predicate giao/khoảng cách hình thật. MBR chỉ là broad phase.

**Tính diện tích bằng float:** Tọa độ đầu vào hữu hạn nhưng hiệu và tích số lớn có thể **tràn**, tạo vô cực hoặc NaN trong area/enlargement/waste. Một triển khai production nên giới hạn miền đầu vào hoặc dùng số học/kiểu dữ liệu phù hợp. Heuristic dựa trên giá trị NaN không đáng tin cậy.

**Cấp phát động:** Node Python chứa danh sách và con trỏ đối tượng; không tối ưu locality hoặc kích thước trang đĩa. Cấu trúc ngoài bộ nhớ cần quản lý page, cache, logging và phục hồi lỗi.

**Không có concurrency:** Các bước split, cập nhật MBR và thay root không được thực hiện như giao dịch atomic trong mã; cần khóa hoặc snapshot khi nhiều luồng cùng truy cập.

**Điều kiện giao là hộp đóng:** Nếu ứng dụng dùng nửa mở hoặc yêu cầu giao có diện tích dương, phải thay predicate và kiểm thử lại tất cả ranh giới; không thể chỉ đổi tên hàm.

**Tie về khoảng cách:** nearest_rectangle sử dụng cặp (khoảng cách bình phương, ID). Với hộp khác nhau cùng khoảng cách, ID nhỏ hơn được ưu tiên; với nhiều object cùng MBR, vẫn giữ đủ ID.

**Chiều cao vẫn cân bằng theo cấp:** R-tree không bảo đảm các nhóm có diện tích/khối lượng dữ liệu đồng đều, nhưng thuật toán insert/split vẫn giữ **mọi lá cùng cấp**, một bất biến khác với sự cân bằng hình học.

## 23. Những lỗi và hiểu lầm thường gặp

1. **“Hai MBR của hai child-entry trong R-tree không bao giờ chồng lấn.”** Sai. Overlap là đặc điểm quan trọng, có thể khiến một query mở nhiều nhánh.
2. **“Chỉ cần đi một nhánh giống binary search tree.”** Sai. Nếu Q giao nhiều MBR, bỏ bất kỳ nhánh nào còn liên quan có thể gây **false negative**.
3. **“MBR của node luôn bằng chính hình học gốc.”** Sai. Nó là hộp bao của một nhóm đối tượng hoặc cây con, thường chứa khoảng trống.
4. **“MBR giao Q thì hình thật chắc chắn giao Q.”** Sai với polygon, đường hoặc hình khác hình chữ nhật; cần bước **refine**.
5. **“MBR không giao Q vẫn có thể có hình thật trong Q.”** Không thể nếu MBR bao chính xác hoặc bảo thủ đầy đủ hình thật.
6. **“MBR node chỉ cần bao một entry nổi bật.”** Sai. Nó phải bao tất cả entry con và hậu duệ.
7. **“Object lớn phải đăng ký vào mọi leaf nó cắt.”** Không phải trong R-tree cơ bản; thường chọn một leaf entry và mở rộng MBR tổ tiên.
8. **“Hai MBR anh em overlap nghĩa là cùng object chắc chắn xuất hiện hai lần.”** Sai. Overlap của **vùng bao** không đồng nghĩa **nhân bản object-entry**.
9. **“Hai object cùng hình chữ nhật là một object.”** Sai nếu ID khác nhau; cần giữ cả hai theo bài toán quản lý bản ghi.
10. **“R-tree chuẩn luôn có đúng hai con ở mỗi node.”** Sai. Nó là cây nhiều nhánh, fanout tối đa M.
11. **“Mọi node R-tree đều có ít nhất m entry kể cả root.”** Sai. Root có quy tắc đặc biệt.
12. **“Split R-tree luôn chia miền hình học thành hai vùng không giao.”** Sai. Split chia **tập entry** thành hai nhóm và MBR của hai nhóm vẫn có thể overlap.
13. **“Khi split chỉ cần đạt tổng M+1 entry, không cần min-fill.”** Sai. Các node sau split phải có số entry hợp lệ theo m và M.
14. **“Quadratic split chọn cặp hạt giống có hai tâm xa nhau nhất.”** Không chính xác. Heuristic trình bày chọn cặp có **waste diện tích MBR** lớn nhất, không đơn thuần khoảng cách tâm.
15. **“Waste luôn không âm.”** Sai. MBR chồng lấn có thể khiến diện tích bao chung nhỏ hơn tổng diện tích hai MBR.
16. **“PickNext chỉ chọn entry bất kỳ rồi đặt vào nhóm ít phần tử.”** Sai. Quadratic split xét chênh lệch enlargement và điều kiện min-fill.
17. **“Chọn nhánh tăng diện tích nhỏ nhất chắc chắn tối ưu về overlap trong tương lai.”** Sai. Đó là heuristic cục bộ.
18. **“Thêm entry vào leaf xong là đủ, không cần cập nhật cha.”** Sai. MBR tổ tiên phải được cập nhật; nếu thiếu có thể prune sai.
19. **“Khi node overflow chỉ split node đó; root không bao giờ đổi.”** Sai. Overflow có thể lan lên tới root, tạo root mới.
20. **“Xóa entry tại lá mà không condense vẫn luôn đúng chuẩn R-tree.”** Sai nếu node còn dưới min-fill và cấu trúc quy định phải duy trì min-fill.
21. **“CondenseTree có thể gắn subtree-entry vào lá bất kỳ.”** Sai. Phải tái chèn đúng cấp hoặc tái chèn toàn bộ object-entry từ lá.
22. **“Xóa object xong mà giữ size/MBR cũ sẽ luôn an toàn.”** MBR cũ nới rộng có thể vẫn đúng nhưng chậm; metadata đếm cũ có thể sai, còn MBR bị thu nhỏ thiếu dữ liệu là lỗi nghiêm trọng.
23. **“Di chuyển vật thể chỉ cần sửa MBR tại leaf.”** Sai nếu MBR tổ tiên không còn bao vật thể ở vị trí mới.
24. **“Hộp đóng chỉ chạm cạnh thì không tính giao.”** Sai. Predicate giao tập hợp nhận cả cạnh/đỉnh.
25. **“Hộp suy biến có diện tích 0 phải bị loại khỏi chỉ mục.”** Sai. Một điểm hoặc đoạn vẫn có thể là đối tượng hợp lệ.
26. **“Một truy vấn chứa trọn MBR cha luôn đồng nghĩa Q chứa mọi polygon thật theo mọi định nghĩa.”** Nếu Q chứa toàn bộ MBR và hình thật nằm trong MBR, Q thực sự chứa hình theo tọa độ phẳng; nhưng với predicate khác như chỉ tính biên, rỗng hình hoặc CRS khác, phải định nghĩa đúng. Không tự áp dụng cho mọi nghiệp vụ.
27. **“R\*-tree chỉ thay cách tìm kiếm mà không đổi chèn/split.”** Sai. Nó có thể tối ưu choose-subtree, split và forced reinsertion.
28. **“R+-tree và R-tree giống hệt về việc nhân bản object-entry.”** Sai. Các biến thể giảm overlap có thể dùng nhiều tham chiếu, đòi dedup.
29. **“STR là phương pháp chèn từng đối tượng mới theo thời gian thực.”** Sai. STR là một cách **bulk-load** từ tập dữ liệu hiện có.
30. **“Cây cao O(log n) thì range query O(log n) trong mọi tình huống.”** Sai. Overlap làm một Q mở nhiều nhánh, còn việc xuất k kết quả cần \(\Omega(k)\).
31. **“MBR gần q nhất chắc chắn chứa object có khoảng cách bằng minDist.”** Sai với hình học không phải hình chữ nhật; minDist chỉ là cận dưới.
32. **“Dùng khoảng cách Euclid giữa hai tâm MBR là cận dưới khoảng cách tới hình.”** Không nói chung; tâm có thể xa mặc dù hình bao q. Phải dùng minDist từ q tới **hộp** hoặc chứng minh cận khác.
33. **“Nếu NN có cận bằng best thì luôn được prune.”** Sai nếu cần tie-break theo ID hoặc trả tất cả nghiệm cùng khoảng cách.
34. **“Kinh độ/vĩ độ theo độ có thể dùng diện tích độ vuông như diện tích mét vuông.”** Sai. Hệ tọa độ/metric quyết định ý nghĩa hình học.
35. **“Tăng số chiều không làm ảnh hưởng overlap.”** Sai. Bbox trong nhiều chiều có thể kém chọn lọc và chi phí so sánh tăng.
36. **“R-tree cơ bản nên được xem là chỉ mục khoảng cách gần đúng.”** Sai. Nếu predicate/cận đúng và duyệt đủ nhánh, nó hỗ trợ truy vấn **chính xác**; gần đúng là một lựa chọn thuật toán khác.

## 24. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Tính MBR của tam giác

Một tam giác có các đỉnh A=(1,1), B=(5,1), C=(3,4). Hãy tìm MBR song song trục.

**Lời giải:**

\[
x_{\min}=1,\ x_{\max}=5,\quad
y_{\min}=1,\ y_{\max}=4.
\]

Vậy \(\boxed{MBR=[1,5]\times[1,4]}\).

### Câu 2. Tính MBR hợp hai hình chữ nhật

Cho \(A=[0,2]\times[1,3]\), \(B=[4,6]\times[-1,2]\). Tính MBR chung.

**Lời giải:** Lấy min và max từng trục:

\[
\boxed{\operatorname{MBR}(A,B)=[0,6]\times[-1,3].}
\]

Đây là hộp bao cả hai hình, bao gồm cả vùng trống giữa chúng.

### Câu 3. Chạm cạnh có giao không?

Cho \(A=[0,4]\times[0,4]\), \(B=[4,7]\times[2,6]\). Hai hình giao nhau không nếu giao định nghĩa là **có ít nhất một điểm chung**?

**Lời giải:** **Có.** Giao là đoạn \(\{4\}\times[2,4]\). Giao có diện tích 0 nhưng không rỗng.

### Câu 4. Giao MBR khác giao polygon

Một tam giác có MBR là [0,10]×[0,10]. Một cửa sổ Q nằm ở góc trên phải của MBR nhưng ngoài tam giác. R-tree có thể trả ứng viên tam giác này không? Có nên trả tam giác như kết quả giao hình chính xác không?

**Lời giải:** R-tree có thể trả tam giác như một **ứng viên** vì Q giao MBR. Sau phép kiểm tra polygon thật, phải **loại** nếu Q không giao tam giác. MBR giao chỉ là điều kiện cần.

### Câu 5. Tính độ tăng diện tích

Một nhánh có \(R=[0,4]\times[0,4]\), đối tượng mới \(E=[3,5]\times[1,2]\). Tính \(\Delta A\) khi đưa E vào nhánh.

**Lời giải:** MBR mới \([0,5]\times[0,4]\), area cũ \(4\cdot4=16\), area mới \(5\cdot4=20\). Vậy:

\[
\boxed{\Delta A=20-16=4.}
\]

### Câu 6. Chọn giữa hai nhánh

Vẫn E ở câu 5, nhánh B có MBR \([6,10]\times[0,4]\). Nhánh A tăng diện tích 4, nhánh B tăng bao nhiêu và heuristic chọn nhánh nào?

**Lời giải:** B phải mở rộng thành \([3,10]\times[0,4]\), diện tích từ 16 lên 28 nên \(\Delta B=12\). Chọn **A** vì 4<12.

### Câu 7. Hai MBR cha chồng lấn

Nhánh A có MBR \([0,6]\times[0,6]\), B có MBR \([4,10]\times[4,10]\). Q=\([5,5]\times[5,5]\) là một điểm. Cần duyệt nhánh nào?

**Lời giải:** Q giao **cả A và B**, nên phải duyệt **cả hai**. Chỉ đi một nhánh có thể bỏ sót object-entry trong nhánh còn lại.

### Câu 8. Object-entry có bị nhân đôi không?

Hai MBR cha overlap. Có thể kết luận object ID X chắc chắn xuất hiện trong cả hai lá không?

**Lời giải:** **Không.** R-tree cơ bản có thể lưu mỗi object-entry **đúng một lần** trong một lá, dù MBR của hai nhóm khác nhau giao nhau.

### Câu 9. Fanout và min-fill

Một R-tree có \(M=4,m=2\). Khi node lá tràn tới 5 entry, những cặp kích thước nhóm nào hợp lệ?

**Lời giải:** Hai nhóm phải có tổng 5 entry và mỗi nhóm có ít nhất 2, nhiều nhất 4; vậy chỉ có **(2,3)** hoặc **(3,2)**.

### Câu 10. Split tại root

Root đang là lá với M=4 và chèn entry thứ năm, cần split. Root mới có bao nhiêu child-entry và cây tăng cao bao nhiêu cấp?

**Lời giải:** Hai nhóm split trở thành **hai node lá**; root mới có **2 child-entry** trỏ tới chúng. Chiều cao tăng **1 cấp**, mọi lá vẫn cùng độ sâu.

### Câu 11. Tính waste cho hai hộp rời

Cho \(A=[0,1]\times[0,1]\) và \(B=[4,5]\times[0,1]\). Tính waste của cặp theo quadratic split.

**Lời giải:** Mỗi hộp area=1, MBR chung \([0,5]\times[0,1]\) có area=5. Vậy:

\[
\boxed{waste=5-1-1=3.}
\]

### Câu 12. Waste có thể âm không?

Cho hai hộp giống nhau \(A=B=[0,4]\times[0,4]\). Tính waste.

**Lời giải:** MBR chung area=16, tổng area riêng=32, nên:

\[
\boxed{waste=16-16-16=-16.}
\]

Vì vậy không được giả định waste luôn không âm.

### Câu 13. Quy tắc min-fill khi phân nhóm

Chọn \(m=2\). Một nhóm A hiện có 1 entry và chỉ còn 1 entry chưa được gán. Có thể đưa entry ấy sang nhóm B không?

**Lời giải:** **Không**, nếu hai nhóm cần ít nhất m=2 entry. Phải đưa entry còn lại vào **A** để tránh node thiếu min-fill.

### Câu 14. Chi phí quadratic split

Một node có 9 entry sau overflow. PickSeeds cần xét bao nhiêu cặp và độ phức tạp theo M của bước này?

**Lời giải:**

\[
\binom92=\frac{9\cdot8}{2}=\boxed{36}.
\]

Khi số entry là M+1, số cặp là \(\Theta(M^2)\).

### Câu 15. Điều gì xảy ra khi xóa dưới min-fill?

Với \(M=4,m=2\), node lá có 2 object-entry; xóa một entry chỉ còn 1. Điều gì cần xử lý trong R-tree chuẩn?

**Lời giải:** Node bị **underflow**. Có thể dùng CondenseTree: loại node thiếu entry khỏi cha, tái chèn entry còn lại đúng cấp và cập nhật các MBR; underflow có thể lan ngược lên root.

### Câu 16. Vì sao tái chèn cần đúng cấp?

Một node trong bị loại do underflow còn trỏ tới các subtree sâu. Có thể gắn nguyên subtree-entry ấy vào một lá bất kỳ không?

**Lời giải:** **Không.** Làm vậy phá bất biến mọi lá cùng độ sâu. Phải tái chèn subtree ở **cấp phù hợp** hoặc thu object-entry của nó và chèn lại vào các lá.

### Câu 17. Đối tượng di chuyển ra ngoài MBR cha

Một entry MBR của xe được đổi từ \([1,2]\times[1,2]\) sang \([20,21]\times[20,21]\), nhưng MBR cha vẫn \([0,5]\times[0,5]\). Truy vấn quanh \((20,20)\) có nguy cơ gì?

**Lời giải:** R-tree có thể thấy MBR cha **không giao Q** và bỏ nhánh chứa xe, gây **false negative**. Phải cập nhật MBR dọc đường hoặc xóa/chèn lại.

### Câu 18. Trùng MBR khác ID

Hai bản ghi A và B có cùng MBR \([2,4]\times[3,5]\). Với Q là \([3,3]\times[4,4]\), số object-entry giao Q là bao nhiêu?

**Lời giải:** **2**, vì cả hai hộp đều chứa điểm Q và A/B là hai ID khác nhau.

### Câu 19. MBR của một điểm

Vật thể P chỉ là điểm (4,7), MBR có diện tích bao nhiêu? Nó có được R-tree hỗ trợ không?

**Lời giải:** MBR \([4,4]\times[7,7]\), diện tích **0** nhưng vẫn là hình chữ nhật đóng hợp lệ. R-tree có thể lưu object-entry ấy.

### Câu 20. Nearest rectangle theo hộp

Cho q=(6,4), các hình A=[3,5]×[4,6] và B=[4,7]×[4,7]. Khoảng cách từ q tới từng hình bằng bao nhiêu, hình nào gần hơn?

**Lời giải:** q cách A theo x 1, y 0 nên \(D(q,A)=1\). q nằm trong B nên \(D(q,B)=0\). **B gần hơn**, dù tâm hình B không nhất thiết gần q hơn tâm A.

### Câu 21. MBR cận dưới nhưng hình thật xa hơn

Một hình chữ U có MBR chứa q ở vùng rỗng giữa hai nhánh chữ U. minDist(q,MBR)=0. Có thể kết luận khoảng cách tới hình chữ U bằng 0 không?

**Lời giải:** **Không.** q có thể không thuộc hình thật; khoảng cách tới hình thật có thể lớn hơn 0. Phải đánh giá khoảng cách tới geometry thật ở lá.

### Câu 22. Khi nào có thể prune trong NN?

Best hiện tại có khoảng cách bình phương 9; một MBR node có minDist²=16. Có thể bỏ không? Nếu minDist²=9 và tie theo ID thì sao?

**Lời giải:** Với 16>9, **bỏ được**. Với 9=9, không được tự bỏ nếu nhánh có thể chứa object cùng khoảng cách nhưng ID nhỏ hơn best.

### Câu 23. STR xây theo lô

Một tập có 100 object-MBR, M=10. Số nhóm lá mục tiêu \(g\) và số dải x STR 2D xấp xỉ là bao nhiêu theo công thức \(s=\lceil\sqrt g\rceil\)?

**Lời giải:** \(g=\lceil100/10\rceil=10\); \(s=\lceil\sqrt{10}\rceil=\boxed{4}\) dải x. Đây là một tham số tổ chức nhóm sơ bộ, không tự xác nhận các nhóm cuối thỏa min-fill.

### Câu 24. Chọn cấu trúc cho ba workload

(a) Bản đồ nhiều polygon, thường hỏi giao một cửa sổ; (b) 1.000 điểm cập nhật liên tục, truy vấn rất ít; (c) 2 triệu điểm 2D gần như tĩnh, thường hỏi NN. Hãy nêu cấu trúc đáng thử.

**Lời giải:** (a) **R-tree/R\*-tree** đáng thử với MBR và refine hình; (b) **quét tuyến tính hoặc grid đơn giản** có thể hợp lý; (c) **k-d tree**, spatial index phù hợp hoặc quét vector hóa làm baseline. Đo workload thật trước khi quyết định.

## 25. Đánh giá hiệu năng và kiểm thử tính đúng

Một R-tree có vẻ rất “cân bằng” về số cấp vẫn có thể truy vấn chậm do **overlap** hoặc MBR có **coverage quá lớn**. Muốn chọn chiến lược chèn/split hoặc biến thể, phải đo trên bộ dữ liệu và workload thực.

### Chỉ số quan trọng

| Chỉ số | Giải thích |
| --- | --- |
| Số object-entry \(n\) | Quy mô dữ liệu gốc |
| Fanout M, min-fill m | Sức chứa và mức lấp đầy node |
| Chiều cao \(h\) | Số cấp từ root tới lá |
| Số node đọc \(V\) | Chi phí duyệt cấu trúc |
| Số entry so với Q \(E_V\) | Công việc lọc MBR |
| Số child-MBR cùng giao Q | Mức nhiều nhánh do overlap |
| Tổng diện tích chồng lấn MBR anh em | Đánh giá chất lượng grouping |
| Tổng diện tích/chu vi MBR | Đánh giá coverage/margin |
| Số ứng viên \(k_c\) | Số MBR object giao Q |
| Số kết quả thật \(k\) | Số object vượt qua refine |
| Tỷ lệ \(k_c/k\) khi \(k>0\) | Mức dư ứng viên |
| Split/Condense/Reinsert | Chi phí cập nhật |
| Thời gian build/rebuild | Chi phí chuẩn bị |
| p50/p95/p99 truy vấn | Độ trễ bình thường và đuôi chậm |
| Số page I/O và cache miss | Chi phí thiết bị bộ nhớ |

### Nên thử những dữ liệu nào?

1. **Hộp nhỏ phân bố đều:** overlap thường có cơ hội thấp hơn.
2. **Hộp rất lớn:** một object có thể khiến MBR cha bao gần toàn miền.
3. **Nhiều hộp chồng lấn:** đánh giá khả năng mở nhiều nhánh.
4. **Nhiều hộp trùng nhau:** kiểm tra ID, split khi không có khoảng cách hình học để tách.
5. **Hộp suy biến:** điểm và đoạn thẳng để phát hiện lỗi biên.
6. **Dữ liệu thành cụm:** tạo vùng dày và vùng trống rộng.
7. **Đối tượng di chuyển:** đo chi phí cập nhật/xóa/chèn và chất lượng cây sau nhiều thay đổi.
8. **Vùng truy vấn nhỏ/lớn/đúng cạnh:** đánh giá mức cắt tỉa và độ đúng predicate.
9. **Thứ tự chèn khác nhau:** xáo thứ tự object mà không đổi tập dữ liệu để thấy độ nhạy của heuristic.
10. **Dữ liệu 3D hoặc nhiều chiều:** đo hiệu quả MBR khi tăng số trục.

### Đối chiếu với quét tuyến tính

Với mỗi Q trong tập truy vấn kiểm thử, tính:

\[
\boxed{
\operatorname{IDs}_{\mathrm{Rtree}}(Q)=
\operatorname{IDs}_{\mathrm{brute}}(Q).
}
\]

Nếu R-tree lưu polygon, phải đối chiếu **sau refine** bằng cùng predicate hình học gốc. Nếu R-tree chỉ trả ứng viên MBR, không nên bắt buộc tập ứng viên bằng tập kết quả hình học cuối — các ứng viên dư có thể là đúng theo broad phase.

Với nearest rectangle, so cặp **(bình phương khoảng cách tới hình chữ nhật, ID)**; với nearest polygon, phải so khoảng cách tới **polygon thật**, không chỉ MBR.

### Property-based và kiểm thử bất biến

Sau mỗi chuỗi chèn, một hàm validate hữu ích nên xác nhận:

- Mỗi object ID xuất hiện đúng một lần trong cây R-tree cơ bản.
- Tất cả lá có cùng độ sâu.
- Mọi node không phải root có \(m\le entries\le M\).
- MBR node bằng hoặc bao đầy đủ hợp MBR của các entry dưới nó.
- Mỗi child-entry trỏ đúng node con và MBR không bị stale.
- Root chỉ là lá rỗng hoặc có cấu trúc phù hợp quy tắc root.
- Mọi query mẫu trả đúng với quét tuyến tính, kể cả tại ranh giới chạm.

**Không chỉ dùng random:** dữ liệu sinh ngẫu nhiên thường hiếm khi tạo đúng cùng tọa độ, đúng biên hoặc cùng MBR. Phải thêm các ca có chủ đích; đây là nơi những lỗi về giao hộp đóng và xử lý min-fill dễ lộ nhất.

## 26. Tổng kết và quy trình chọn R-tree

**R-tree** nhóm các đối tượng có kích thước bằng **MBR**, sắp xếp các nhóm thành một **cây nhiều nhánh cân bằng theo cấp**. Mỗi nút trong lưu MBR của các cây con; mỗi lá lưu MBR và ID của đối tượng.

Ba đặc điểm quyết định tính đúng và hiệu năng:

1. **MBR bao đầy đủ:** MBR của một cây con phải bao toàn bộ dữ liệu của nó. Nhánh có MBR không giao Q được bỏ an toàn.
2. **MBR có thể chồng lấn:** Q giao nhiều child-MBR thì **phải xét tất cả** nhánh có khả năng chứa kết quả; không thể tìm bằng một đường đơn như BST.
3. **Node có min/max sức chứa:** Chèn có thể overflow và split lan lên root; xóa có thể underflow, cần CondenseTree/tái chèn hoặc cơ chế duy trì bất biến tương đương.

Chèn R-tree thường đi xuống nhánh gây **độ tăng diện tích MBR nhỏ nhất**. Khi node tràn, quadratic split chọn hai hạt giống theo độ bao thừa, phân phối các entry theo độ tăng diện tích và tôn trọng min-fill. Các biến thể như **R\*-tree** tối ưu thêm overlap, margin và reinsertion; **STR** phù hợp xây cây hàng loạt từ tập dữ liệu tĩnh.

**R-tree không đồng nghĩa chính xác hóa hình học.** Nếu entry là polygon, đường hay vùng phức tạp, MBR chỉ giúp lọc ứng viên; phải dùng predicate giao/chứa/khoảng cách của **hình thật** để trả kết quả đúng. Đối với đối tượng là hình chữ nhật, phép giao MBR có thể chính là phép kiểm tra cuối.

Về hiệu năng, chiều cao cây thường nhỏ nhờ fanout lớn, nhưng **overlap và coverage** quyết định có phải mở nhiều nhánh hay không. Trong trường hợp xấu, truy vấn có thể xét gần như mọi object-entry; việc xuất k kết quả cũng cần ít nhất \(\Omega(k)\).

**Quy trình áp dụng thực tế:** xác định CRS/đơn vị và kiểu hình học → định nghĩa rõ giao/tiếp xúc/chứa → tính MBR bảo thủ hợp lệ → chọn M,m theo bộ nhớ/trang đĩa → chọn heuristic insertion, split hoặc bulk-load → giữ bất biến khi xóa/di chuyển → đối chiếu với quét tuyến tính và refine hình thật → benchmark số node thăm, overlap, I/O, độ trễ và chi phí cập nhật. R-tree có giá trị khi nó **giảm công việc tìm ứng viên mà vẫn không bỏ sót đối tượng hợp lệ**.
