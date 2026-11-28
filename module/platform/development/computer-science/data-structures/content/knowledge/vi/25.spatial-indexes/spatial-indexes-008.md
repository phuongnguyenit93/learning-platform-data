# Chèn, tách nút và ảnh hưởng của độ chồng lấn trong R-tree

Khi xây một chỉ mục bản đồ, hai đối tượng ở xa nhau nên được đặt vào những nhóm có **hộp bao nhỏ, ít giao nhau**. Nếu nhiều hộp bao của các nhóm cùng phủ một vùng trống, một truy vấn tại vùng đó có thể phải mở hàng loạt nhánh dù cuối cùng không tìm thấy đối tượng nào. Trong **R-tree**, chất lượng của việc **chèn** và **tách nút** quyết định trực tiếp lượng công việc dư này.

Chèn vào R-tree không giống chèn khóa vào cây tìm kiếm nhị phân. Một đối tượng mới có thể giao nhiều vùng của các node con; thuật toán thường **chọn một nhánh** bằng heuristic như *minimum area enlargement*. Khi node tràn, nó phải phân các entry thành hai nhóm đạt **min-fill**, tính lại hộp bao, cập nhật cha và có thể tiếp tục tách lên tận gốc. Những quyết định cục bộ ấy tạo ra các **MBR có thể chồng lấn**, ảnh hưởng lâu dài tới thời gian tìm kiếm, bộ nhớ và I/O.

Bài học thuộc chương **Chỉ mục không gian** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**, với mục tiêu hiểu **bất biến, thao tác và độ phức tạp** để chọn cấu trúc dữ liệu phù hợp. Nội dung tập trung vào đường đi của một lần chèn, *ChooseSubtree*, các chính sách split, độ chồng lấn và chi phí truy vấn, cách đo chất lượng cây, cùng mã Python mô phỏng R-tree 2D với kiểm thử đối chiếu.

> **Ý chính:** R-tree không bắt buộc các MBR anh em không giao nhau. Điều bắt buộc là **mỗi MBR cha bao đầy đủ dữ liệu ở nhánh con**, **mọi lá cùng cấp** và số entry của các node hợp lệ. Chọn nhóm khéo giúp giảm duyệt thừa; chọn nhóm sai có thể vẫn tạo cây **đúng** nhưng truy vấn chậm.

## 1. Bài toán cụ thể: thêm một hình chữ nhật vào chỉ mục

Xét hệ thống lưu những cửa hàng, tòa nhà và vùng phục vụ. Mỗi đối tượng \(o\) có một **hình học thật** \(\operatorname{geom}(o)\) và một hộp bao tối thiểu song song trục:

\[
\boxed{B(o)=\operatorname{MBR}(\operatorname{geom}(o)).}
\]

R-tree tổ chức các object-entry của dữ liệu bằng các hộp bao ấy. Mỗi lần một vùng mới \(N\) được thêm vào, cây cần:

1. Tìm **node lá thích hợp** để chứa \(B(N)\).
2. Chèn một object-entry với **ID duy nhất**.
3. Cập nhật MBR của mọi node liên quan trên đường đi lên.
4. Khi node vượt sức chứa, **tách nút** thành hai nhóm.
5. Nếu cha bị tràn do xuất hiện thêm child-entry, xử lý tiếp cho đến khi cấu trúc hợp lệ.

Ta muốn cây sau chèn vẫn cho đáp án đúng với truy vấn:

\[
\boxed{
\operatorname{Candidates}(Q)=
\{o:B(o)\cap Q\ne\varnothing\}.
}
\]

Đây là **kết quả giao MBR**. Nếu đối tượng thật là đa giác, đường hoặc hình cong, những ứng viên này phải được kiểm tra thêm bằng predicate hình học thật mới có kết quả giao chính xác.

### Vì sao việc nhóm lại quan trọng?

Một object-entry hình chữ nhật chỉ nằm tại **một lá** trong R-tree cơ bản. Tuy nhiên, nhiều leaf-entry được gộp thành những node có MBR lớn. **Hai nhóm không có object trùng nhau** vẫn có thể có **hai MBR chồng lấn**. Khi Q giao MBR của cả hai nhóm, hệ thống buộc phải kiểm tra cả hai vì mỗi nhóm đều có thể chứa ứng viên hợp lệ.

## 2. Hộp bao, diện tích và các phép toán nền tảng

Trong 2D, biểu diễn một **hộp đóng**:

\[
B=[x_{\min},x_{\max}]\times[y_{\min},y_{\max}],
\quad x_{\min}\le x_{\max},\ y_{\min}\le y_{\max}.
\]

Với hai hộp \(A,B\), hộp bao chung nhỏ nhất là:

\[
\boxed{
\begin{aligned}
\operatorname{cover}(A,B)=
&[\min(A.x_{\min},B.x_{\min}),
\max(A.x_{\max},B.x_{\max})]\\
&\times[\min(A.y_{\min},B.y_{\min}),
\max(A.y_{\max},B.y_{\max})].
\end{aligned}
}
\]

Diện tích của một hộp:

\[
\boxed{\operatorname{area}(B)=
(B.x_{\max}-B.x_{\min})(B.y_{\max}-B.y_{\min}).}
\]

Nếu thêm hộp E vào một nhóm đang có MBR R, **độ tăng diện tích**:

\[
\boxed{
\Delta_A(R,E)=
\operatorname{area}(\operatorname{cover}(R,E))
-\operatorname{area}(R)\ge0.
}
\]

### Đo diện tích chồng lấn

Độ dài giao của hai khoảng trên x:

\[
\ell_x=\max\bigl(
0,\min(A.x_{\max},B.x_{\max})
-\max(A.x_{\min},B.x_{\min})
\bigr).
\]

Tương tự tính \(\ell_y\), rồi:

\[
\boxed{\operatorname{overlapArea}(A,B)=\ell_x\ell_y.}
\]

Hai hộp **chạm cạnh** có thể giao nhau như tập hợp nhưng \(\operatorname{overlapArea}=0\). Đây là hai predicate khác nhau:

- **Giao hình học** (*intersects*): giao chứa ít nhất một điểm, kể cả cạnh và đỉnh.
- **Diện tích giao** (*overlap area*): độ đo 2D của giao; chạm biên thì bằng 0.

Trong quá trình tối ưu R-tree, overlap area thường được dùng để so **mức chồng lấn vùng**. Khi thực thi truy vấn giao hộp đóng, phép tìm vẫn phải đi xuống nhánh **chạm biên**, dù overlap area bằng 0.

### Diện tích bao thừa và coverage

MBR chứa cả khoảng trống giữa các đối tượng. Giả sử hai hộp bé ở hai đầu một hành lang:

~~~text
 [object A]---------------------------[object B]
 |<------ MBR của nhóm rất rộng ----->|
            phần lớn là khoảng trống
~~~

Một query rơi vào khoảng trống có thể giao MBR nhóm, khiến node ấy được thăm dù không có object-entry giao Q. Vì vậy ngoài **overlap giữa các nhóm**, còn phải chú ý **coverage**: độ rộng vùng MBR bao các đối tượng của nhóm.

## 3. Bất biến phải giữ trước và sau một lần chèn

Chọn hai thông số:

\[
\boxed{M=\text{số entry tối đa của một node}},\qquad
\boxed{m=\text{số entry tối thiểu của node không phải gốc}}.
\]

Trong bài dùng \(M=4,m=2\) để ví dụ. Một cấu hình chuẩn thường thỏa \(2\le m\le\lfloor M/2\rfloor\); điều kiện này cho phép phân \(M+1\) entry thành **hai node**, mỗi node không dưới m và không quá M.

R-tree có hai loại node:

| Loại node | Mỗi entry chứa | Ý nghĩa MBR |
| --- | --- | --- |
| **Lá** | \((ID,\operatorname{MBR}(object))\) | Hộp bao của một object thật |
| **Node trong** | \((pointer(child),\operatorname{MBR}(child))\) | Hộp bao của **mọi object-entry** trong nhánh child |

### Những bất biến cốt lõi

1. **Bao phủ:** MBR ở một child-entry phải chứa toàn bộ MBR của node con mà entry trỏ tới.
2. **Cân bằng theo cấp:** Tất cả lá có **cùng độ sâu từ gốc**, dù MBR không cân về diện tích.
3. **Min/max entry:** Mỗi node không phải gốc có số entry trong \([m,M]\) sau khi thao tác hoàn thành.
4. **Gốc đặc biệt:** Root có thể là một lá rỗng hoặc ít entry; root trong thường có ít nhất hai con sau khi thu gọn.
5. **Không mất/nhân bản dữ liệu:** Mỗi object-ID của R-tree cơ bản được lưu tại đúng một leaf-entry.
6. **Cùng độ cao khi split:** Hai node sinh từ một node tràn phải cùng cấp; cha nhận thêm một tham chiếu node con, không tự thay đổi độ sâu của một nhánh riêng lẻ.

**Đúng về mặt dữ liệu chưa đồng nghĩa nhanh:** Một cây có MBR cha rộng hơn cần thiết nhưng vẫn bao các con có thể cho kết quả truy vấn **đúng**, song tốn thêm lượt thăm. Một MBR cha **quá nhỏ, không bao đủ dữ liệu**, có thể gây bỏ sót đối tượng và làm sai kết quả.

## 4. Đường đi của INSERT trong R-tree

Một lần chèn bắt đầu từ root, đi xuống lá bằng heuristic, rồi cập nhật ngược lên trên.

~~~mermaid
flowchart TD
    A["Nhận object mới với MBR E"] --> B["ChooseSubtree từ root"]
    B --> C["Đến một node lá"]
    C --> D["Thêm (ID, E) vào lá"]
    D --> F{"Số entry > M?"}
    F -->|Không| G["Tính lại MBR, cập nhật cha"]
    F -->|Có| H["Split thành hai nhóm đạt min-fill"]
    H --> I["Cha cập nhật entry con cũ và nhận thêm entry con mới"]
    I --> J{"Cha có overflow?"}
    J -->|Có| H
    J -->|Không| K["Lan cập nhật MBR tới root"]
    G --> K
    K --> L{"Root bị split?"}
    L -->|Có| M["Tạo root mới có 2 con"]
    L -->|Không| N["Hoàn tất"]
    M --> N
~~~

Đây là sơ đồ ý tưởng. Một triển khai đệ quy có thể tách **trước khi quay về cha** và để hàm chèn trả về một node anh em mới, giúp tránh phải lưu riêng chuỗi con trỏ cha.

### Từng phần của INSERT

**ChooseSubtree:** Chọn một cây con để đi tiếp; nhiều child-MBR có thể giao hộp mới nhưng ta không chèn object vào tất cả chúng.

**Leaf insert:** Đưa object-entry vào lá đã chọn. Nếu lá còn chỗ, chỉ cần bảo đảm MBR của lá và các tổ tiên bao hộp mới.

**Split:** Nếu thêm vượt sức chứa, tách tập entry thành hai node cùng cấp và cập nhật cha. Cha có thêm một child-entry và có thể tràn tiếp.

**Root split:** Khi root tràn, tạo **root mới** với hai child-entry trỏ tới hai node được tách. Tất cả lá sâu thêm **một cấp** so với root, nên vẫn cùng độ sâu.

### Vì sao không chèn vào mọi nhánh giao?

Một đối tượng dài có thể giao nhiều MBR anh em. R-tree cơ bản vẫn tìm **một lá phù hợp** và lưu object-entry **một lần**. Nếu gắn vào mọi lá có giao, ta đã chọn một mô hình nhân bản khác, cần logic khử trùng ID và cập nhật/xóa phức tạp hơn.

## 5. ChooseSubtree: ưu tiên tăng diện tích nhỏ nhất

Giả sử một node trong có các child-MBR \(R_1,\ldots,R_t\), object mới có MBR E.

Heuristic R-tree cơ bản chọn:

\[
\boxed{
j=\arg\min_i \Delta_A(R_i,E).
}
\]

Nếu nhiều nhánh có cùng độ tăng diện tích, có thể phá hòa theo:

1. Diện tích MBR hiện tại nhỏ hơn.
2. Số entry trong con ít hơn.
3. Vị trí child-entry sớm hơn, để thuật toán ổn định.

Heuristic này chọn **nơi chiếm ít diện tích tăng thêm nhất tại thời điểm chèn**. Nó không tối ưu toàn cục cho mọi truy vấn tương lai.

### Ví dụ với số cụ thể

Hai nhóm:

\[
R_A=[0,4]\times[0,4],\qquad
R_B=[6,10]\times[0,4].
\]

Object mới:

\[
E=[3,5]\times[1,2].
\]

Nếu vào A:

\[
\operatorname{cover}(R_A,E)=[0,5]\times[0,4],
\quad \Delta_A=20-16=\boxed{4}.
\]

Nếu vào B:

\[
\operatorname{cover}(R_B,E)=[3,10]\times[0,4],
\quad \Delta_B=28-16=\boxed{12}.
\]

Chọn **A** vì \(4<12\).

### Khi E đã nằm trọn bên trong một MBR

Nếu \(E\subseteq R_A\), thì \(\Delta_A=0\). Đây là dấu hiệu hấp dẫn để chọn A, nhưng cũng có thể \(E\subseteq R_B\) và hai MBR overlap. Quy tắc phá hòa quyết định đường đi; về lâu dài, tie-break khác nhau có thể tạo cấu trúc khác nhau.

### Khác với chọn nhánh của k-d tree

Ở k-d tree, trục chia cho một điều kiện trái/phải rõ ràng. Ở R-tree, không có một phép so sánh duy nhất khiến chỉ một nhánh có khả năng liên quan; ChooseSubtree là **heuristic quyết định chèn**, còn Search vẫn phải kiểm tra **tất cả child-MBR giao Q**.

## 6. Tách nút: yêu cầu trước khi nói đến thuật toán

Khi node có \(M+1\) entry, ta cần chia thành hai tập không giao nhau theo **danh tính entry**:

\[
G_A\cup G_B=S,\qquad G_A\cap G_B=\varnothing.
\]

Đồng thời:

\[
\boxed{m\le|G_A|\le M,\quad m\le|G_B|\le M.}
\]

Mỗi nhóm tạo một node mới (hoặc một node giữ lại vị trí cũ và một **sibling** mới). Hộp bao được tính lại từ **đúng các entry** của từng nhóm:

\[
B_A=\operatorname{cover}_{e\in G_A}B(e),\quad
B_B=\operatorname{cover}_{e\in G_B}B(e).
\]

**Điểm mấu chốt:** Việc phân entry theo nhóm **không đòi hỏi \(B_A\cap B_B=\varnothing\)**. Hai MBR của hai nhóm có thể giao nhau, dù không có một entry nào xuất hiện ở cả hai.

### Split khác với chia hình học cố định

Quadtree có thể chia một hình chữ nhật không gian thành bốn vùng con theo trung điểm. R-tree chia **danh sách entry** thành hai nhóm dựa vào hình học của các entry, rồi mới lấy hộp bao của nhóm.

Vì vậy split có thể tạo những hình chữ nhật có diện tích rất khác nhau và vẫn giao nhau. Mục tiêu thực tế là **đặt những entry có quan hệ không gian phù hợp vào cùng nhóm** để giảm overlap và vùng bao thừa, trong khi vẫn giữ min-fill/max-fill.

## 7. Một ví dụ cho thấy cùng dữ liệu, nhóm khác nhau tạo overlap khác nhau

Cho bốn object-entry:

\[
\begin{aligned}
A&=[0,2]\times[0,2],\\
B&=[4,6]\times[4,6],\\
C&=[1,3]\times[4,6],\\
D&=[4,6]\times[1,3].
\end{aligned}
\]

Với cấu hình \(m=2\), mỗi nhóm sau split cần ít nhất hai entry. Hai phương án sau đều có **2 entry trên mỗi node**, nhưng hình học rất khác.

### Phân nhóm xấu: ghép các góc đối diện

Chia:

\[
G_1=\{A,B\},\qquad G_2=\{C,D\}.
\]

Hai MBR:

\[
B_1=[0,6]\times[0,6],\quad
B_2=[1,6]\times[1,6].
\]

Diện tích:

\[
\operatorname{area}(B_1)=36,\qquad
\operatorname{area}(B_2)=25.
\]

Vì \(B_2\subset B_1\), phần giao của hai MBR có diện tích:

\[
\boxed{\operatorname{overlapArea}(B_1,B_2)=25.}
\]

Tổng diện tích MBR anh em là \(36+25=61\), rất nhiều so với tổng diện tích bốn object-entry.

### Phân nhóm tốt hơn: ghép theo bên trái và bên phải

Chia:

\[
G_L=\{A,C\},\qquad G_R=\{B,D\}.
\]

Khi ấy:

\[
B_L=[0,3]\times[0,6],\quad
B_R=[4,6]\times[1,6].
\]

Hai hộp **không giao** trên trục x, nên:

\[
\boxed{\operatorname{overlapArea}(B_L,B_R)=0.}
\]

Tổng diện tích hai MBR:

\[
18+10=\boxed{28},
\]

nhỏ hơn nhiều so với 61 ở phương án trước.

| Tiêu chí | Ghép đối diện \(\{A,B\},\{C,D\}\) | Ghép trái/phải \(\{A,C\},\{B,D\}\) |
| --- | ---: | ---: |
| Số entry hai nhóm | 2 và 2 | 2 và 2 |
| Diện tích hai MBR cộng lại | 61 | 28 |
| Overlap area | 25 | 0 |
| Bất biến min-fill | Đạt | Đạt |
| Một query nhỏ có thể mở cả hai nhánh? | Có | Ít khả năng hơn khi Q hẹp trên x |

Với Q là một hình chữ nhật nhỏ quanh \((4.5,5)\), hai MBR của phương án xấu đều giao Q; phương án tốt chỉ có MBR bên phải giao Q. Hai phương án **đều đúng về mặt dữ liệu**, nhưng phương án tốt **tránh được một nhánh thăm dư** cho truy vấn này.

> **Bài học:** Tách nút không chỉ để giải quyết số entry \(M+1\). Nó còn là cơ hội tổ chức lại dữ liệu, làm MBR hẹp hơn và giảm nhiều nhánh cùng bị truy vấn chạm.

## 8. Quadratic split: chọn hai hạt giống theo diện tích bao thừa

**Quadratic split** là một thuật toán split kinh điển, dễ minh họa quyết định nhóm.

### Bước 1 — PickSeeds

Tại node bị tràn, xét các cặp entry \(e_i,e_j\). Định nghĩa:

\[
\boxed{
\operatorname{waste}(i,j)=
\operatorname{area}(\operatorname{cover}(B_i,B_j))
-\operatorname{area}(B_i)
-\operatorname{area}(B_j).
}
\]

Chọn **cặp có waste lớn nhất** làm hai hạt giống (*seeds*) cho hai nhóm A và B. Ý tưởng là hai entry ấy sẽ gây nhiều diện tích bao thừa nếu buộc ở chung.

**Chú ý:** Nếu hai entry đã chồng lấn lớn, \(\operatorname{waste}\) có thể **âm**. Ví dụ hai hộp giống nhau có diện tích 16 cho:

\[
\operatorname{waste}=16-16-16=\boxed{-16}.
\]

Không được tự dùng \(\max(0,\operatorname{waste})\) rồi gọi đó là đúng nguyên tắc PickSeeds đã mô tả; nó có thể đổi thứ tự chọn hạt giống trong các trường hợp chồng lấn.

### Bước 2 — PickNext

Với một entry E chưa được gán, tính:

\[
\Delta_A(E)=
\operatorname{area}(\operatorname{cover}(B_A,B_E))
-\operatorname{area}(B_A),
\]

\[
\Delta_B(E)=
\operatorname{area}(\operatorname{cover}(B_B,B_E))
-\operatorname{area}(B_B).
\]

Độ khác biệt:

\[
\boxed{D(E)=|\Delta_A(E)-\Delta_B(E)|.}
\]

Chọn entry có \(D(E)\) **lớn nhất**: với entry ấy, việc gán vào nhóm nào ảnh hưởng độ tăng diện tích khác nhau mạnh nhất.

### Bước 3 — Chọn nhóm cho entry

Với entry vừa chọn, ưu tiên nhóm có:

1. \(\Delta\) nhỏ hơn.
2. Nếu hòa, diện tích MBR nhóm hiện tại nhỏ hơn.
3. Nếu tiếp tục hòa, số entry nhóm ít hơn.
4. Nếu vẫn hòa, nhóm A theo quy tắc cố định.

Sau khi gán, cập nhật MBR nhóm bằng **cover**; không chỉ tăng biến đếm entry.

### Bước 4 — Giữ min-fill

Tại mọi bước, nếu A có \(a\) entry, còn \(r\) entry chưa được gán và:

\[
\boxed{a+r=m,}
\]

thì **phải đưa toàn bộ r entry vào A**. Nếu không, A không thể đạt min-fill. Tương tự với B. Khi điều kiện bắt buộc xuất hiện, không tiếp tục chọn PickNext như bình thường.

### Mã giả

~~~text
QUADRATIC_SPLIT(entries, m):
    (seedA, seedB) = pair with largest waste
    groupA = [seedA]; groupB = [seedB]
    remaining = entries excluding both seeds
    boxA = MBR(seedA); boxB = MBR(seedB)

    while remaining is not empty:
        if size(groupA) + size(remaining) == m:
            append all remaining to groupA; break
        if size(groupB) + size(remaining) == m:
            append all remaining to groupB; break

        e = entry maximizing abs(enlargementA(e)-enlargementB(e))
        choose group by:
            (enlargement, current_area, group_size, fixed_tie)
        append e to chosen group and update its box
        remove e from remaining

    return groupA, groupB
~~~

### Phức tạp của split

PickSeeds xét \(\binom{M+1}{2}=\Theta(M^2)\) cặp. Trong một phiên bản đơn giản, mỗi lượt PickNext quét các entry còn lại, cho tổng thêm \(O(M^2)\). Vì thế:

\[
\boxed{T_{\mathrm{quadratic\ split}}=O(M^2)}
\]

phép so sánh/đánh giá hộp trong 2D, với fanout M của **một node**. Đây không phải khẳng định mọi lần chèn vào cây n object tốn \(O(n^2)\).

## 9. Linear split, quadratic split và chất lượng nhóm

Các R-tree truyền thống còn có **linear split**, chọn hạt giống theo độ tách chuẩn hóa trên các trục và phân các entry với ít thao tác hơn. So sánh khái quát:

| Tiêu chí | Linear split | Quadratic split |
| --- | --- | --- |
| Cách chọn seeds | Heuristic tách theo các trục | Cặp có waste diện tích lớn |
| Công việc tại node \(M+1\) entry | Có thể thiết kế \(O(M)\) | \(O(M^2)\) |
| Chi phí CPU khi node tràn | Thường thấp hơn | Cao hơn |
| Chất lượng nhóm trên một workload | Tùy phân bố, không bảo đảm tốt hơn | Tùy phân bố, không bảo đảm ít overlap nhất |
| Bất biến cần giữ | Min-fill, max-fill, cùng cấp, MBR đúng | Giống nhau |

**Không suy ra rằng quadratic split luôn tạo hai MBR ít chồng lấn hơn linear split.** Nó tối ưu từng lựa chọn cục bộ bằng diện tích bao, không phải duyệt toàn bộ mọi cách phân hoạch để tìm nghiệm toàn cục.

### Vì sao “ít diện tích” và “ít overlap” khác nhau?

Giả sử một split tạo:

- Phương án X: tổng diện tích hai MBR nhỏ, nhưng phần giao giữa hai MBR khá lớn.
- Phương án Y: tổng diện tích hơi lớn hơn, nhưng hai MBR gần như không giao.

Nếu workload chủ yếu là **cửa sổ truy vấn nhỏ**, Y có thể thăm ít nhánh hơn do ít overlap, dù tổng diện tích lớn hơn. Vì vậy diện tích và overlap là **hai mục tiêu khác nhau**.

Một quyết định nhóm có thể đúng với heuristic diện tích nhưng chưa tốt cho **số nhánh phải mở**. Các biến thể như R\*-tree dùng thêm thước đo overlap, margin và tái chèn để cải thiện chất lượng nhóm trong nhiều tình huống.

## 10. R*-tree: giảm overlap thay vì chỉ nhìn enlargement

**R\*-tree** là biến thể R-tree quan tâm rõ hơn tới **overlap, margin/perimeter và diện tích**, không chỉ diện tích mở rộng. Một số đặc điểm nổi bật:

- Chọn subtree có thể tối ưu **overlap enlargement** ở cấp ngay trên lá, tùy thuật toán cụ thể.
- Split có thể thử thứ tự sắp entry theo các cạnh MBR, chọn **trục và điểm chia** dựa trên tổng margin rồi so overlap và diện tích.
- Khi overflow, có thể thực hiện **forced reinsertion** (tái chèn một phần entry) thay vì split ngay, trong những điều kiện được thuật toán quy định.

### Overlap enlargement

Với node đang xét có các MBR anh em \(R_1,\ldots,R_t\), nếu gán E vào nhánh i và thay \(R_i\) bằng \(R'_i=\operatorname{cover}(R_i,E)\), độ tăng overlap của nhánh i với các nhánh còn lại:

\[
\boxed{
\Delta O_i=
\sum_{j\ne i}\operatorname{overlapArea}(R'_i,R_j)
-\sum_{j\ne i}\operatorname{overlapArea}(R_i,R_j).
}
\]

Chọn \(\Delta O_i\) nhỏ có thể giảm nguy cơ một query phải mở **nhiều nhánh cùng cấp**.

**Lưu ý:** Tính \(\Delta O_i\) cần so với nhiều sibling-MBR; nó thường đắt hơn một phép tính enlargement đơn giản. Khi nào dùng overlap criterion, dùng thế nào để phá hòa và có áp dụng ở mọi cấp không là chi tiết của **biến thể/triển khai cụ thể**, không phải một quy tắc duy nhất cho mọi R-tree.

### Margin/perimeter

Với hình chữ nhật 2D, chu vi là:

\[
\boxed{\operatorname{perimeter}(R)=
2\bigl((x_{\max}-x_{\min})+(y_{\max}-y_{\min})\bigr).}
\]

Minimize margin có thể giúp giảm các nhóm dài và mảnh. Tuy nhiên, hai hộp cùng diện tích có thể có chu vi khác nhau; margin, area và overlap là những **hàm mục tiêu không tương đương**.

### Forced reinsertion và nguy cơ lặp

R\*-tree có thể lấy một tỷ lệ entry từ node overflow để chèn lại, cho phép các entry được đưa sang nhóm phù hợp hơn. Để tránh vòng lặp tái chèn vô hạn, một triển khai chuẩn cần **theo dõi cấp đã forced-reinsert trong cùng một thao tác chèn** và quy tắc riêng khi root overflow.

Không tự thay quadratic split bằng một vòng lặp “thử chèn lại mãi đến khi node hết tràn”: cách đó có thể không kết thúc hoặc phá min-fill nếu không có chính sách đầy đủ.

## 11. Thứ tự chèn ảnh hưởng cấu trúc như thế nào?

Chèn lần lượt các hộp theo thứ tự A,B,C,... tạo những quyết định cục bộ. Khi chèn một hộp mới, các nhánh hiện có chịu ảnh hưởng từ **những hộp đã chèn trước đó**, nên thay đổi thứ tự có thể:

- Đổi đường ChooseSubtree của cùng một object.
- Làm một node đạt \(M+1\) entry sớm hoặc muộn hơn.
- Đổi cặp seeds ở thời điểm split.
- Tạo MBR anh em chồng lấn nhiều hoặc ít hơn.
- Đổi số node phải thăm cho cùng một Q.

### Chèn theo nhóm không gian và chèn xen kẽ

Giả sử các hộp nhỏ nằm thành hai cụm cách xa nhau ở trái và phải bản đồ.

**Chèn theo cụm:** Nếu đưa các hộp trái trước, chúng có thể sớm được nhóm cùng nhau; sau đó các hộp phải hình thành nhóm riêng (không luôn như vậy).

**Chèn xen kẽ:** Nếu đưa trái–phải–trái–phải, khi các node chưa đủ thông tin phân cụm, một số nhóm có thể chứa entry thuộc cả hai cụm, khiến MBR kéo dài qua vùng trống.

Đây là **hiện tượng có thể xảy ra**, không phải bảo đảm mọi trình tự xen kẽ đều xấu. Heuristic và split cụ thể, min-fill, dữ liệu và các bước forced reinsertion đều ảnh hưởng kết quả.

### Vì sao bulk loading đáng cân nhắc?

Nếu có đầy đủ dữ liệu tĩnh từ đầu, thay vì chèn theo thời gian tới, ta có thể dùng **bulk loading** (ví dụ STR, Sort-Tile-Recursive) để tổ chức nhóm theo tọa độ trong một lượt. STR thường sắp theo tâm MBR trên các trục, chia thành các dải và đóng các node theo sức chứa.

Bulk loading không miễn phí và vẫn cần xử lý min-fill ở nhóm cuối, nhưng có thể giảm ảnh hưởng của thứ tự chèn ngẫu nhiên. Với dữ liệu cập nhật liên tục, có thể phải kết hợp **chèn động** và **rebuild theo lô**.

## 12. Tính đúng so với hiệu năng: ba loại “chồng lấn”

Để đánh giá chất lượng R-tree cần phân biệt:

**(1) Overlap giữa MBR của hai object thật:** Hai tòa nhà, vùng phục vụ hoặc các hình có thể giao nhau về mặt hình học. Đây là **đặc tính của dữ liệu**, không nhất thiết sửa được bằng split.

**(2) Overlap giữa MBR của hai nhóm anh em:** Các nhóm chứa các object khác nhau nhưng MBR bao có thể giao nhau. Đây là thứ mà choose-subtree/split có thể tác động.

**(3) Một query Q giao MBR của nhiều nhóm:** Đây là **chi phí tra cứu thực tế**, gần với số nhánh phải mở. Dù overlap area bằng 0 vì chỉ chạm cạnh, Q tại đúng cạnh vẫn có thể mở nhiều nhánh nếu truy vấn dùng hộp đóng.

### Minh họa một query không có kết quả vẫn phải duyệt nhiều

Hai nhóm có:

\[
B_A=[0,5]\times[0,5],\qquad
B_B=[3,8]\times[3,8].
\]

Chọn Q nhỏ ở \([3.5,4]\times[3.5,4]\). Q giao **cả hai MBR**. Nếu các object-entry thật của A chỉ ở góc dưới trái, còn object-entry thật của B chỉ ở góc trên phải, Q có thể không giao object-entry nào. Thuật toán vẫn phải đi xuống cả hai nhóm để **chứng minh kết quả rỗng**.

Vì vậy khi benchmark không chỉ đo số kết quả \(k\); một truy vấn có \(k=0\) vẫn có thể rất tốn kém nếu MBR anh em overlap rộng hoặc có coverage nhiều khoảng trống.

## 13. Minh họa min-fill buộc nhận một entry không thuận lợi

Chọn \(M=4,m=2\). Một node sau chèn có năm hộp nhỏ liên tiếp theo trục x:

\[
\begin{aligned}
A&=[0,1]\times[0,1],\\
B&=[1,2]\times[0,1],\\
C&=[2,3]\times[0,1],\\
D&=[3,4]\times[0,1],\\
E&=[100,101]\times[0,1].
\end{aligned}
\]

Hộp E ở rất xa bốn hộp còn lại.

### Chọn seeds

Ghép A và E có MBR \([0,101]\times[0,1]\), diện tích 101; mỗi hộp riêng có diện tích 1. Do đó:

\[
\boxed{\operatorname{waste}(A,E)=101-1-1=99.}
\]

Đây là cặp seed có khoảng cách tách lớn nhất theo tiêu chí waste ở ví dụ này.

### Phân phối phần còn lại

Ban đầu:

\[
G_A=\{A\},\qquad G_E=\{E\},
\]

và còn B,C,D. Heuristic có xu hướng đưa B rồi C vào nhóm A vì tăng diện tích nhóm A rất nhỏ, trong khi cho vào nhóm E làm MBR trải dài qua vùng trống.

Lúc này nhóm A có 3 entry, nhóm E có 1 entry, còn D chưa được gán. Nếu đưa D vào A, nhóm E sẽ chỉ có 1 entry, vi phạm \(m=2\). Vì vậy thuật toán **buộc phải đưa D vào nhóm E**:

\[
G_A=\{A,B,C\},\qquad G_E=\{D,E\}.
\]

Nhóm E có MBR:

\[
[3,101]\times[0,1].
\]

Nó chứa một hành lang trống rất dài, nhưng vẫn là một kết quả **hợp lệ** theo min-fill. Ví dụ cho thấy:

- **Min-fill có thể xung đột với độ chặt hình học.**
- Không thể đòi split làm cả hai hộp đều nhỏ khi dữ liệu bất lợi và sức chứa buộc nhóm ít nhất hai entry.
- Chi phí truy vấn của R-tree còn phụ thuộc mạnh vào **phân bố và kích thước hình gốc**, không chỉ thuật toán.

## 14. Vì sao split có thể lan truyền tới nhiều cấp?

Giả sử node lá L đã có M entry. Khi chèn entry thứ \(M+1\), L phải tách thành L và L'. Cha của L ban đầu có t entry:

- Entry đại diện L được cập nhật MBR.
- Cha nhận thêm entry đại diện L'.
- Vì thế số entry cha tăng thành \(t+1\).

Nếu \(t=M\), cha cũng tràn. Nó lại split thành hai node trong cùng cấp và truyền một sibling lên node ông. Chuỗi này có thể lặp qua nhiều cấp đến root.

~~~text
                ROOT  (đủ M entry)
                 |
              ...node cha (đủ M)
                 |
              LEAF L (đủ M)
                 |
              chèn E
                 v
          L -> [L, sibling L']
                 |
         cha thêm một child-entry -> overflow
                 |
         cha -> [cha, sibling cha']
                 |
         ... có thể lan đến ROOT ...
                 |
       root mới có hai con cùng cấp
~~~

### Điều gì không xảy ra?

Không “tách một nhánh thành cấp sâu hơn rồi giữ các nhánh khác nông hơn”. R-tree là **cây cân bằng theo độ sâu lá**: node mới do split có **cùng cấp** với node cũ; chỉ khi root tăng cấp thì **tất cả** đường root–lá tăng đồng thời một.

### Ví dụ số node nhỏ

Với \(M=4,m=2\), root là lá đang giữ bốn object-entry. Chèn entry thứ năm:

1. Root lá tách thành hai lá 2 và 3 entry.
2. Tạo root trong có đúng **hai child-entry**.
3. Cây có hai cấp node thay vì một.
4. Sau đó tìm kiếm Q phải kiểm tra **cả hai child-MBR** ở root nếu Q giao cả hai.

**Chỉ số quan trọng** không chỉ là root tăng cấp; đó là **độ overlap giữa hai child-MBR** và số object-entry phải xét trong các lá.

## 15. Truy vấn cửa sổ và hệ quả của overlap sau nhiều lần split

Với truy vấn hộp đóng Q, tìm kiếm các entry hình chữ nhật:

~~~text
SEARCH(node, Q):
    nếu node rỗng hoặc MBR(node) không giao Q:
        return

    nếu node là lá:
        kiểm tra MBR từng object-entry; xuất entry giao Q
        return

    với mọi child-entry của node:
        nếu child.MBR giao Q:
            SEARCH(child, Q)
~~~

**Mỗi child-entry giao Q đều phải được xét**, kể cả khi đã tìm thấy một kết quả ở child khác. R-tree không bảo đảm rằng một vùng không gian chỉ có **một đường đi** như một phân hoạch quadtree không chồng lấn.

### Phân biệt ba số lượng

- \(V\): số **node** thật sự được truy cập.
- \(E_V\): tổng số **entry** cần kiểm tra trong các node đã truy cập.
- \(k\): số object-entry được trả như kết quả giao hộp.

Với hộp 2D và chi phí kiểm tra giao hằng số:

\[
\boxed{T_{\mathrm{search}}=O(V+E_V+k).}
\]

Nếu đối tượng thật là polygon, thêm bước **refine** hình học cho những object-MBR giao Q; chi phí phụ thuộc vào predicate hình gốc.

### Vì sao chiều cao nhỏ không bảo đảm truy vấn nhanh?

Một R-tree có thể có chiều cao khoảng \(\log_M n\), nhưng nếu Q giao nhiều child-MBR ở mỗi cấp, truy vấn có thể phải mở **rất nhiều** nhánh. Trong trường hợp xấu, thuật toán có thể xét gần mọi entry:

\[
\boxed{T_{\mathrm{search}}=O(n)}
\]

cho dữ liệu là hình chữ nhật 2D và bỏ qua chi phí xuất đầu ra. Không có bảo đảm chung \(O(\log n+k)\) chỉ nhờ cây cân theo cấp.

### Một phản ví dụ về số kết quả

Giả sử có 50 leaf-node, mỗi leaf có 20 entry, và mọi MBR leaf đều giao một Q rất nhỏ vì MBR bao trùm vùng trống ở tâm bản đồ. Nếu **không một entry lá nào thật sự giao Q**, truy vấn trả \(k=0\) nhưng vẫn có thể phải xét tới 1.000 object-entry.

Không thể đánh giá chất lượng split chỉ bằng số **kết quả trả về**; phải đo số **node/entry đã thăm** để tìm ra chúng.

## 16. Cập nhật MBR: bảo thủ rộng thì chậm, thiếu thì sai

Sau khi chèn, đối tượng mới phải nằm trong **MBR của mọi tổ tiên** trên đường đến root. Có hai trạng thái cần phân biệt:

**MBR rộng hơn cần thiết:** Vẫn chứa tất cả object. Truy vấn có thể mở nhánh không cần thiết, nhưng điều kiện prune “MBR không giao Q” vẫn an toàn.

**MBR bị thu nhỏ thiếu object:** Có thể tồn tại object ở ngoài MBR cha. Khi Q giao object nhưng không giao MBR cha, cả nhánh bị bỏ và chương trình **trả thiếu**.

### Điều gì cần làm sau split?

Giả sử node cũ có MBR \(R\), split thành A và B. Không được đặt MBR của A và B bằng R rồi tuyên bố đã cập nhật tối ưu. Mỗi hộp cần được **tính lại từ đúng entry nhóm**:

\[
\boxed{
\operatorname{MBR}(A)=\operatorname{cover}_{e\in A}B(e),\quad
\operatorname{MBR}(B)=\operatorname{cover}_{e\in B}B(e).
}
\]

Nếu dùng R cũ cho cả hai child-entry, truy vấn vẫn có thể **đúng** vì cả hai hộp rộng quá mức, nhưng sẽ tạo **overlap nhân tạo** rất lớn và làm mất lợi ích của split.

### Tại sao cần cập nhật ngược lên root?

Nếu một object mới mở rộng MBR của node lá mà entry ở cha vẫn giữ hộp cũ, cha có thể bị lỗi bao phủ. Vì thế cả đường từ lá tới root phải được sửa, kể cả khi **không có node nào tràn**.

### Xóa và di chuyển

Với delete, MBR của nhóm có thể thu hẹp; còn với move một đối tượng ra ngoài hộp cũ, MBR tổ tiên phải mở rộng hoặc object phải được **xóa khỏi lá cũ rồi chèn lại**. Một R-tree có min-fill thường dùng thủ tục kiểu **CondenseTree** khi xóa tạo node underflow; việc tái chèn subtree cần bảo toàn cấp lá.

Ví dụ Python ở phần sau cố ý chỉ hỗ trợ **chèn và truy vấn**, không giả vờ rằng cập nhật xóa/chuyển động có thể thực hiện bằng cách sửa tọa độ trong entry.

## 17. Đo độ chồng lấn sau split như thế nào?

Để so hai chính sách chèn/split, cần một số đo cụ thể thay vì nói “cây này có vẻ gọn”.

### Pairwise sibling overlap

Một node trong có các child-MBR \(B_1,\ldots,B_t\). Đặt:

\[
\boxed{
O_{\mathrm{parent}}=
\sum_{1\le i<j\le t}
\operatorname{overlapArea}(B_i,B_j).
}
\]

Tổng trên toàn bộ node trong:

\[
\boxed{O_{\mathrm{tree}}=\sum_{v\in\mathrm{internal}}O_v.}
\]

Đây là một **chỉ số hình học** giúp so sánh các cấu trúc trên **cùng dữ liệu/hệ tọa độ**, không phải trực tiếp số node truy vấn sẽ mở.

### Coverage và margin

Với một tập node có MBR \(B_v\), có thể báo cáo:

\[
\boxed{
A_{\mathrm{sum}}=\sum_v\operatorname{area}(B_v).
}
\]

Hoặc tổng chu vi (*margin*):

\[
\boxed{
P_{\mathrm{sum}}=\sum_v2(\operatorname{width}(B_v)
+\operatorname{height}(B_v)).
}
\]

Khi đo, phải nói rõ **cộng những cấp nào**: chỉ node con của root, mọi node không phải root hay mọi node trong cây. Cộng nhiều cấp sẽ đếm một vùng nhiều lần theo các MBR khác nhau; chỉ số vẫn hữu ích cho so sánh **có kiểm soát**, nhưng không phải diện tích hợp vùng trong mặt phẳng.

### Vì sao overlap area chưa đủ?

Hai MBR có thể chỉ **chạm cạnh** nên overlap area bằng 0. Nhưng một query đóng đúng trên cạnh chung có thể giao cả hai và khiến tìm kiếm phải thăm hai nhánh. Với nhiều MBR suy biến (điểm hoặc đoạn), overlap area cũng có thể bằng 0 dù nhiều node cùng giao một query.

Vì vậy khi benchmark thực tế nên đo thêm:

- **Số node và entry được truy cập trên mỗi Q**.
- **Số lần một node trong có từ hai child-MBR trở lên cùng giao Q**, gọi là *branch forks*.
- **Số object-MBR ứng viên** trước khi refine hình học thật.
- **Thời gian p50/p95/p99**, số I/O và cache miss khi khả dụng.

### Hệ tọa độ quyết định ý nghĩa area

Nếu một trục là mét còn trục kia là giây, tích rộng×cao có đơn vị mét·giây; nó không phải diện tích địa lý. Với kinh độ/vĩ độ, “độ vuông” cũng không tương đương diện tích mét vuông.

Heuristic R-tree vẫn có thể vận hành trên tọa độ này, nhưng cần **định nghĩa và chuẩn hóa dữ liệu** theo workload thực để các lựa chọn diện tích/overlap có ý nghĩa.

## 18. Python: R-tree 2D với ChooseSubtree, quadratic split và thống kê overlap

Ví dụ dưới đây sử dụng **Python 3.10+** và chỉ dùng thư viện chuẩn. Nó chủ ý tập trung vào chủ đề bài học:

- Nhập object-ID duy nhất và MBR hình chữ nhật **đóng**.
- Chọn một cây con theo **area enlargement** rồi phá hòa ổn định.
- Split node \(M+1\) entry bằng **quadratic split**, tuân thủ min-fill.
- Xử lý split lan lên root, tính lại MBR bottom-up.
- Truy vấn những hình chữ nhật giao một cửa sổ.
- Thu **node visits**, **entry tests**, **branch forks**, tổng overlap area của các MBR anh em.
- Kiểm tra bất biến sức chứa, cấp lá và hộp bao.

Đây là R-tree lưu **hình chữ nhật làm object thật**. Nếu dữ liệu gốc là polygon hoặc đường, cần thêm bước refine sau khi tìm các object-MBR ứng viên. API minh họa thao tác **tuần tự**, chưa hỗ trợ xóa, đồng thời hoặc lưu trữ trên đĩa.

~~~python
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        if not all(isfinite(v) for v in (
            self.x0, self.y0, self.x1, self.y1
        )):
            raise ValueError("Tất cả tọa độ phải hữu hạn")
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("Cận dưới không được vượt cận trên")

    def cover(self, other: Rect) -> Rect:
        return Rect(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def perimeter(self) -> float:
        return 2 * (
            (self.x1 - self.x0) + (self.y1 - self.y0)
        )

    def intersects(self, other: Rect) -> bool:
        # Hộp đóng: chạm cạnh/đỉnh vẫn là giao.
        return not (
            self.x1 < other.x0 or other.x1 < self.x0
            or self.y1 < other.y0 or other.y1 < self.y0
        )

    def contains(self, other: Rect) -> bool:
        return (
            self.x0 <= other.x0 <= other.x1 <= self.x1
            and self.y0 <= other.y0 <= other.y1 <= self.y1
        )

    def overlap_area(self, other: Rect) -> float:
        dx = max(
            0.0, min(self.x1, other.x1)
            - max(self.x0, other.x0)
        )
        dy = max(
            0.0, min(self.y1, other.y1)
            - max(self.y0, other.y0)
        )
        return dx * dy


@dataclass(frozen=True)
class ObjectEntry:
    id: str
    bbox: Rect


@dataclass
class RNode:
    leaf: bool
    entries: list = field(default_factory=list)
    bbox: Rect | None = None


class InsertRTree:
    def __init__(self, M=4, m=2):
        if (type(M) is not int or type(m) is not int
                or M < 4 or m < 2 or m > M // 2):
            raise ValueError("Cần M>=4 và 2<=m<=floor(M/2)")
        self.M = M
        self.m = m
        self.root = RNode(leaf=True)
        self.ids: set[str] = set()
        self.total_splits = 0
        self.root_splits = 0

    @staticmethod
    def _box(item) -> Rect:
        # ObjectEntry và RNode đều có thuộc tính bbox.
        assert item.bbox is not None
        return item.bbox

    @staticmethod
    def _union_all(items) -> Rect | None:
        if not items:
            return None
        box = InsertRTree._box(items[0])
        for item in items[1:]:
            box = box.cover(InsertRTree._box(item))
        return box

    def _recalc(self, node: RNode):
        node.bbox = self._union_all(node.entries)

    @staticmethod
    def _enlargement(current: Rect, added: Rect) -> float:
        return current.cover(added).area() - current.area()

    def _choose_subtree(self, parent: RNode, rect: Rect):
        assert not parent.leaf

        def priority(pair):
            index, child = pair
            box = self._box(child)
            return (
                self._enlargement(box, rect),
                box.area(),
                len(child.entries),
                index,
            )

        return min(
            enumerate(parent.entries), key=priority
        )[1]

    def _split(self, node: RNode) -> RNode:
        """Giữ nhóm A trong node; trả sibling nhóm B cùng cấp."""
        items = list(node.entries)
        assert len(items) == self.M + 1

        # PickSeeds: tìm cặp với waste diện tích lớn nhất.
        best_pair = None
        largest_waste = float("-inf")
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a = self._box(items[i])
                b = self._box(items[j])
                waste = (
                    a.cover(b).area() - a.area() - b.area()
                )
                if waste > largest_waste:
                    best_pair = (i, j)
                    largest_waste = waste

        assert best_pair is not None
        first, second = best_pair
        group_a = [items[first]]
        group_b = [items[second]]
        box_a = self._box(items[first])
        box_b = self._box(items[second])
        pending = [
            item for index, item in enumerate(items)
            if index not in (first, second)
        ]

        while pending:
            # Khi vừa đủ entry để một nhóm đạt m,
            # mọi entry còn lại buộc phải vào nhóm ấy.
            if len(group_a) + len(pending) == self.m:
                group_a.extend(pending)
                pending.clear()
                break
            if len(group_b) + len(pending) == self.m:
                group_b.extend(pending)
                pending.clear()
                break

            # PickNext: khác biệt enlargement lớn nhất.
            chosen = max(
                range(len(pending)),
                key=lambda pos: abs(
                    self._enlargement(
                        box_a, self._box(pending[pos])
                    ) -
                    self._enlargement(
                        box_b, self._box(pending[pos])
                    )
                ),
            )
            item = pending.pop(chosen)
            rect = self._box(item)

            # Enlargement -> diện tích -> số entry -> nhóm A.
            rank_a = (
                self._enlargement(box_a, rect),
                box_a.area(),
                len(group_a),
                0,
            )
            rank_b = (
                self._enlargement(box_b, rect),
                box_b.area(),
                len(group_b),
                1,
            )
            if rank_a <= rank_b:
                group_a.append(item)
                box_a = box_a.cover(rect)
            else:
                group_b.append(item)
                box_b = box_b.cover(rect)

        if not (self.m <= len(group_a) <= self.M):
            raise AssertionError("Nhóm A vi phạm sức chứa")
        if not (self.m <= len(group_b) <= self.M):
            raise AssertionError("Nhóm B vi phạm sức chứa")

        node.entries = group_a
        self._recalc(node)
        sibling = RNode(leaf=node.leaf, entries=group_b)
        self._recalc(sibling)
        self.total_splits += 1
        return sibling

    def _insert_recursive(
        self, node: RNode, record: ObjectEntry
    ) -> RNode | None:
        if node.leaf:
            node.entries.append(record)
        else:
            child = self._choose_subtree(node, record.bbox)
            sibling = self._insert_recursive(child, record)
            if sibling is not None:
                node.entries.append(sibling)

        # Cập nhật bbox trên đường đi ngược từ lá lên.
        self._recalc(node)
        if len(node.entries) == self.M + 1:
            return self._split(node)
        return None

    def insert(self, object_id: str, box: Rect):
        if not isinstance(object_id, str) or not object_id:
            raise ValueError("ID phải là chuỗi không rỗng")
        if not isinstance(box, Rect):
            raise TypeError("box phải thuộc kiểu Rect")
        if object_id in self.ids:
            raise ValueError("ID đã tồn tại")

        sibling = self._insert_recursive(
            self.root, ObjectEntry(object_id, box)
        )
        if sibling is not None:
            old_root = self.root
            self.root = RNode(
                leaf=False, entries=[old_root, sibling]
            )
            self._recalc(self.root)
            self.root_splits += 1
        self.ids.add(object_id)

    def search(self, query: Rect, with_stats=False):
        """Trả ID giao hộp; tùy chọn trả thêm thống kê duyệt."""
        if not isinstance(query, Rect):
            raise TypeError("query phải thuộc kiểu Rect")
        result = []
        stats = {
            "node_visits": 0,
            "entry_tests": 0,
            "branch_forks": 0,
        }

        def visit(node):
            stats["node_visits"] += 1
            if node.leaf:
                for entry in node.entries:
                    stats["entry_tests"] += 1
                    if entry.bbox.intersects(query):
                        result.append(entry.id)
            else:
                matching_children = []
                for child in node.entries:
                    stats["entry_tests"] += 1
                    if self._box(child).intersects(query):
                        matching_children.append(child)
                if len(matching_children) > 1:
                    stats["branch_forks"] += 1
                for child in matching_children:
                    visit(child)

        if (self.root.bbox is not None
                and self.root.bbox.intersects(query)):
            visit(self.root)

        ids = sorted(result)
        return (ids, stats) if with_stats else ids

    def metrics(self):
        """Đo số node, độ cao và overlap giữa sibling-MBR."""
        report = {
            "nodes": 0,
            "leaves": 0,
            "height": 0,
            "sibling_overlap_area": 0.0,
            "positive_overlap_pairs": 0,
            "sum_child_coverage_area": 0.0,
        }

        def walk(node, depth):
            report["nodes"] += 1
            report["height"] = max(report["height"], depth)
            if node.leaf:
                report["leaves"] += 1
                return

            boxes = [self._box(c) for c in node.entries]
            report["sum_child_coverage_area"] += sum(
                b.area() for b in boxes
            )
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    area = boxes[i].overlap_area(boxes[j])
                    report["sibling_overlap_area"] += area
                    if area > 0:
                        report["positive_overlap_pairs"] += 1
            for child in node.entries:
                walk(child, depth + 1)

        walk(self.root, 0)
        return report

    def validate(self):
        """Kiểm tra entry, MBR, ID, min-fill và cấp lá."""
        seen = set()
        leaf_depths = set()

        def check(node, depth, root):
            count = len(node.entries)
            if root:
                if count > self.M:
                    raise AssertionError("Root overflow")
                if not node.leaf and count < 2:
                    raise AssertionError("Root trong phải có >=2 con")
            elif not (self.m <= count <= self.M):
                raise AssertionError("Node vi phạm min/max-fill")

            if node.leaf:
                leaf_depths.add(depth)
                for entry in node.entries:
                    if not isinstance(entry, ObjectEntry):
                        raise AssertionError("Lá phải chứa object-entry")
                    if entry.id in seen:
                        raise AssertionError("ID bị nhân bản")
                    seen.add(entry.id)
            else:
                for child in node.entries:
                    if not isinstance(child, RNode):
                        raise AssertionError("Nút trong cần child-node")
                    check(child, depth + 1, False)

            expected = self._union_all(node.entries)
            if node.bbox != expected:
                raise AssertionError("MBR node không đúng")

        check(self.root, 0, True)
        if len(leaf_depths) != 1:
            raise AssertionError("Các lá có độ sâu khác nhau")
        if seen != self.ids:
            raise AssertionError("Danh sách ID không khớp chỉ mục")
        return True
~~~

### Giải thích lựa chọn cài đặt

**Entry của node trong:** Để tránh thêm một lớp con trỏ riêng, mỗi RNode con tự mang MBR và được lưu trực tiếp trong danh sách entry của cha. Một R-tree trên đĩa thường lưu \((MBR,\text{pageID})\) riêng, nhưng bất biến hình học vẫn như nhau.

**PickSeeds và PickNext:** Đều đánh giá hình chữ nhật theo diện tích; tie được giải quyết bằng thứ tự entry hiện có, nên kết quả mang tính xác định với cùng chuỗi chèn và cùng số học.

**Min-fill:** Mỗi lần split có đúng \(M+1\) entry. Khi một nhóm cần toàn bộ entry còn lại để đạt m, chúng được gán bắt buộc; sau đó mã xác minh cả hai nhóm trong giới hạn.

**Truy vấn:** Ở node trong, duyệt **mọi** child-MBR giao Q; nếu nhiều con giao, tăng bộ đếm branch_forks. Không có phép định tuyến sang chỉ một nhánh như trong BST.

**Overlap metrics:** Chỉ cộng diện tích giao của **từng cặp child-MBR trong cùng một node trong**. Giá trị này không phải diện tích hợp của tất cả vùng overlap; một miền được ba MBR phủ có thể được cộng nhiều lần trong tổng các cặp.

**validate:** Chạy trong môi trường học để kiểm tra metadata; chi phí của nó cao hơn thao tác tra cứu thông thường. Cài đặt chưa có API delete/move hoặc xử lý đồng thời.

## 19. Python: bài kiểm chứng chèn, split và ảnh hưởng chồng lấn

Đoạn dưới đây **nối tiếp** các định nghĩa Rect, ObjectEntry, RNode và InsertRTree ở mục 18. Tất cả assert được viết để người học **tự chạy**, không phải xác nhận rằng tác giả đã thực thi mã trong bước biên soạn.

~~~python
objects = [
    ("A", Rect(0, 0, 2, 2)),
    ("B", Rect(3, 0, 5, 2)),
    ("C", Rect(0, 4, 2, 6)),
    ("D", Rect(3, 4, 5, 6)),
    ("E", Rect(8, 8, 10, 10)),
    ("F", Rect(9, 0, 11, 2)),
    ("G", Rect(4, 4, 7, 7)),
    ("H", Rect(-2, -2, -1, -1)),
    ("I", Rect(0, 0, 0, 0)),   # MBR suy biến tại 1 điểm.
    ("J", Rect(2, 2, 2, 2)),
    ("K", Rect(0, 0, 2, 2)),   # Trùng hộp A nhưng ID khác.
]

index = InsertRTree(M=4, m=2)
for i, (object_id, box) in enumerate(objects):
    index.insert(object_id, box)
    assert index.validate()
    if i == 3:
        # Đúng M=4 entry, root vẫn là một lá.
        assert index.root.leaf
    if i == 4:
        # Entry thứ 5 buộc split root lá.
        assert not index.root.leaf
        assert index.root_splits == 1

assert index.total_splits >= 1
assert index.ids == {item_id for item_id, _ in objects}

# Hình chữ nhật đóng: một điểm Q chạm nhiều đối tượng.
assert index.search(Rect(0, 0, 0, 0)) == ["A", "I", "K"]
assert index.search(Rect(4, 4, 4, 4)) == ["D", "G"]

# Truy vấn lớn hơn dữ liệu trả mọi ID; truy vấn xa trả rỗng.
assert index.search(Rect(-100, -100, 100, 100)) == sorted(
    item_id for item_id, _ in objects
)
assert index.search(Rect(100, 100, 110, 110)) == []


def brute_search(entries, query):
    return sorted(
        item_id for item_id, box in entries
        if box.intersects(query)
    )


windows = [
    Rect(1, 1, 4, 4),
    Rect(0, 0, 0, 0),
    Rect(4, 4, 4, 4),
    Rect(-3, -3, 1, 1),
    Rect(2, 2, 2, 2),
    Rect(100, 100, 110, 110),
]
for window in windows:
    ids, statistics = index.search(window, with_stats=True)
    assert ids == brute_search(objects, window)
    assert statistics["node_visits"] >= 0
    assert statistics["entry_tests"] >= 0
    assert statistics["branch_forks"] >= 0

# Cùng dữ liệu, đổi thứ tự chèn: kết quả đúng không được đổi.
reversed_index = InsertRTree(M=4, m=2)
for item_id, box in reversed(objects):
    reversed_index.insert(item_id, box)
    assert reversed_index.validate()
for window in windows:
    assert index.search(window) == reversed_index.search(window)

# Ví dụ nhóm tốt/xấu ở mục 7 được tính độc lập.
bad_a = Rect(0, 0, 6, 6)
bad_b = Rect(1, 1, 6, 6)
good_left = Rect(0, 0, 3, 6)
good_right = Rect(4, 1, 6, 6)
assert bad_a.area() + bad_b.area() == 61
assert bad_a.overlap_area(bad_b) == 25
assert good_left.area() + good_right.area() == 28
assert good_left.overlap_area(good_right) == 0

# Nhiều ID tại cùng một hộp điểm: không được gộp bản ghi.
same_point = InsertRTree(M=4, m=2)
for j in range(36):
    same_point.insert(f"P{j:03d}", Rect(2, 2, 2, 2))
    assert same_point.validate()

found, stats = same_point.search(
    Rect(2, 2, 2, 2), with_stats=True
)
assert len(found) == 36
assert stats["branch_forks"] > 0

# Diện tích overlap bằng 0 nhưng các MBR điểm vẫn cùng giao Q.
shape_metrics = same_point.metrics()
assert shape_metrics["sibling_overlap_area"] == 0

# Cây rỗng là hợp lệ.
empty = InsertRTree(M=4, m=2)
assert empty.search(Rect(0, 0, 1, 1)) == []
assert empty.validate()
~~~

### Vì sao bộ test tập trung vào MBR trùng và split?

**MBR trùng nhau:** Một thuật toán split chỉ dựa trên khoảng cách tâm có thể không có thông tin để phân chia. Với tie ổn định và min-fill, cây vẫn phải hoàn tất split mà không làm mất ID, cho dù mọi hộp đều là cùng một điểm.

**Overlap area bằng 0 nhưng có branch forks:** MBR là các hộp điểm có diện tích bằng 0; dù nhiều child-MBR cùng giao truy vấn điểm, metric diện tích chồng lấn vẫn bằng 0. Vì vậy cần đo **số nhánh thực sự mở**, không chỉ tổng overlap area.

**Thứ tự chèn:** Hai cây dựng từ cùng bộ dữ liệu theo hai thứ tự khác nhau có thể có cấu trúc/chi phí khác nhau, nhưng các tập ID kết quả của cùng Q phải **giống nhau**.

**Quét độc lập:** Hàm brute_search kiểm tra từng object-rectangle, không sử dụng node cha hoặc heuristic split. Nó phát hiện lỗi MBR thiếu dữ liệu mà một phép so sánh hai R-tree mắc cùng lỗi có thể bỏ qua.

**Không chạy mã trong STEP 4:** Những assert là ví dụ cho người học. Nội dung Python chỉ được soạn và đọc lại dưới nhiệm vụ này; việc chạy kiểm thử phần mềm/QA học thuật thuộc giai đoạn khác.

## 20. Độ phức tạp của chèn và split

Đặt:

- \(n\): số object-entry trong toàn cây.
- \(M\): số entry tối đa trong một node.
- \(m\): số entry tối thiểu ở node không phải root.
- \(h\): số cấp theo đường root–lá.
- \(S\): số node split trong một lần chèn.

### Chi phí chọn nhánh

Ở mỗi node trong, ChooseSubtree quét tối đa M child-entry. Với chi phí giao/cover/area hằng số trong 2D:

\[
\boxed{T_{\mathrm{descend}}=O(Mh).}
\]

Nếu có heuristic **overlap enlargement** cần so một nhánh ứng viên với nhiều sibling, chi phí lựa chọn có thể lớn hơn, tùy cách cài đặt và caching metadata.

### Chi phí cập nhật MBR

Sau chèn, một triển khai có thể **mở rộng** bbox trên đường đi bằng cover hiện tại với bbox mới trong \(O(1)\) mỗi cấp. Mã Python minh họa dùng hàm _recalc từ danh sách entry, tốn tối đa **\(O(M)\) mỗi cấp**, để dễ bảo đảm bất biến.

Vì vậy chi phí không split của mã minh họa vẫn thuộc:

\[
\boxed{O(Mh).}
\]

### Chi phí split

Quadratic split một node tràn có \(M+1\) entry:

\[
\boxed{T_{\mathrm{split}}=O(M^2).}
\]

Một lần chèn có thể split **tối đa một node ở mỗi cấp** trên đường đi được lựa chọn, nên \(S\le h\) trước khi tính root mới. Bỏ qua chi phí I/O và với mô hình CPU đơn giản:

\[
\boxed{
T_{\mathrm{insert}}=O(Mh+SM^2)
\subseteq O(hM^2).
}
\]

Nếu M được cố định theo kích thước page, đây thường là một lượng công việc nhỏ trên mỗi cấp; nhưng R-tree chèn không có bảo đảm “chỉ một phép so sánh ở mỗi cấp”.

### Chiều cao và sức chứa

Trong trạng thái hợp lệ, các node không phải root có ít nhất m entry, và mọi lá cùng cấp, giúp hạn chế cây quá thưa. Nếu mức lấp đầy điển hình gần M, chiều cao thường xấp xỉ \(\log_M n\) cấp.

**Không dùng \(O(\log n)\) của chiều cao để khẳng định mọi truy vấn tìm không gian là \(O(\log n)\)**: một Q giao nhiều MBR anh em nên có thể mở rất nhiều nhánh.

### Chi phí tìm kiếm

Với những node thực thăm có tổng \(E_V\) entry phải kiểm tra:

\[
\boxed{T_{\mathrm{query}}=O(V+E_V+k)}
\]

trên dữ liệu hình chữ nhật 2D, với \(k\) kết quả không cần sắp. Nếu đầu ra cần **sắp ID**, cộng thêm \(O(k\log k)\), đúng như hàm search Python minh họa.

Trường hợp xấu \(V\) và \(E_V\) có thể đạt quy mô toàn cây, cho thời gian \(O(n)\) với M cố định và không tính chi phí xuất. **Overlap lớn** thường khiến \(V\) tăng dù số kết quả thật k vẫn rất nhỏ.

### Bộ nhớ và I/O

Một object-entry cần ID/tham chiếu và MBR; node trong cần child-entry và MBR. Với fanout giới hạn và số chiều cố định, bộ nhớ của cây là **\(O(n)\)**. Khi lưu ngoài RAM, chi phí đọc/ghi trang có thể quan trọng hơn số phép cộng/trừ của quadratic split.

**Đánh đổi M:** Fanout M lớn giảm số cấp nhưng tăng số entry cần xét trong node, tăng chi phí split \(O(M^2)\) và kích thước trang. Fanout M nhỏ khiến cây sâu hơn. Thông số phù hợp phụ thuộc tổ chức page, phân bố dữ liệu và tỷ lệ chèn/truy vấn.

## 21. Benchmark công bằng giữa các chính sách chèn và tách

Để so hai cách split, không chỉ nhìn một phép chèn hay một tổng diện tích. Hãy tạo một tập đối tượng duy nhất và thử nhiều cách xây/chèn:

- **R-tree chèn tuần tự**, choose-subtree theo minimum area enlargement và quadratic split.
- Một **chiến lược split khác** (ví dụ linear split) với cùng M,m.
- **R\*-tree** có tiêu chí overlap/margin nếu có triển khai đầy đủ.
- **STR bulk loading** nếu dữ liệu tĩnh và cần xây hàng loạt.
- **Quét tuyến tính** làm baseline cho những tập nhỏ hoặc truy vấn rất rộng.

### Dữ liệu phải đa dạng

| Nhóm dữ liệu | Điều cần quan sát |
| --- | --- |
| Những hình vuông nhỏ rải đều | Khả năng tạo nhóm cục bộ |
| Hai hoặc nhiều cụm xa nhau | Có bị tạo MBR dài qua vùng trống không? |
| Hộp kích thước rất khác nhau | Hộp lớn có làm mở rộng nhiều MBR cha không? |
| Nhiều hộp chồng lấn thật | Phần overlap nào là bất khả tránh do dữ liệu? |
| Nhiều hộp cùng tọa độ | Tie, min-fill và split có kết thúc không? |
| Hộp suy biến thành điểm/đoạn | Predicate giao và overlap area có phân biệt đúng không? |
| Hộp xuất hiện theo trục tăng dần | Thứ tự chèn có làm cây lệch về hình học không? |
| Thứ tự chèn đảo ngược/ngẫu nhiên | Độ nhạy của heuristic |
| Cửa sổ rất nhỏ, cửa sổ rất rộng | Số nhánh thăm và chi phí xuất kết quả |
| Hình thật là polygon/đường | Số ứng viên MBR dư trước bước refine |

### Cần ghi cả chi phí tạo chỉ mục

Một chính sách split đắt CPU hơn có thể tạo cây query nhanh hơn. Nếu một lần xây phục vụ hàng triệu truy vấn, khoản đầu tư khi xây có thể đáng giá; nếu liên tục chèn/xóa nhưng hầu như không query, chính sách rẻ hơn có thể thắng về tổng chi phí.

Nên báo cáo ít nhất:

1. **Thời gian build và chi phí trung bình mỗi insert**.
2. **Số split/root split**, số lần cập nhật MBR và độ lấp đầy node.
3. **Tổng sibling overlap area**, coverage/margin ở những cấp được định nghĩa rõ.
4. **Số node visits, entry tests, branch forks trên mỗi Q**.
5. **Số object-MBR ứng viên** và số kết quả hình thật sau refine.
6. **Độ trễ truy vấn p50/p95/p99**, chi phí I/O/cache nếu có.
7. **Bộ nhớ** dùng cho node, MBR, con trỏ và các metadata khác.

### Hiệu ứng thứ tự chèn

Với cùng danh sách object, thực hiện ít nhất:

- Thứ tự ban đầu theo thời gian thực.
- Thứ tự ngược.
- Một số thứ tự được xáo ngẫu nhiên có seed cố định.
- Thứ tự được sắp theo một trục hoặc tâm MBR.

Đồng thời dùng **cùng tập truy vấn** cho mọi cây. Vì R-tree có heuristic cục bộ và split phụ thuộc lịch sử, thay đổi thứ tự có thể làm số node được thăm khác nhau, nhưng **tập ID kết quả đúng phải giống nhau**.

### Đối chiếu với brute force

Với mỗi Q và dữ liệu là hình chữ nhật, bắt buộc:

\[
\boxed{
\operatorname{IDs}_{Rtree}(Q)=
\operatorname{IDs}_{brute}(Q).
}
\]

Nếu dùng polygon, so **kết quả sau refine** với predicate polygon–Q độc lập. Không so tập ứng viên MBR với tập kết quả polygon như thể chúng buộc phải bằng nhau; ứng viên dư là hợp lệ trong broad phase.

### Không chỉ dựa trên random

Random float liên tục hiếm khi tạo đúng trường hợp hai biên bằng nhau, cùng tọa độ hoặc MBR suy biến. Phải chủ động tạo các test:

- Hai hình chạm đúng cạnh.
- Một hình nằm trọn trong một hình khác.
- Các hình khác ID nhưng MBR giống hệt.
- Một object nằm ngoài MBR cha sai lệch trong một bản test cố tình làm hỏng metadata.
- Node đúng M entry, sau đó chèn thêm một entry.
- Root split và split lan nhiều cấp.
- Q giao nhiều child-MBR nhưng không giao object-entry nào.

**Thứ tự ưu tiên:** kiểm chứng tính đúng trước, đo chất lượng nhóm và hiệu năng sau. Một cây có ít node visits nhưng bỏ sót object do bbox sai không phải một tối ưu hợp lệ.

## 22. Sai lầm thường gặp khi chèn và split R-tree

1. **“R-tree có thể đặt object vào nhánh duy nhất chứa tâm nó.”** Không phải điều kiện bắt buộc. ChooseSubtree thường dùng tiêu chí MBR/enlargement, và object có kích thước.
2. **“Nếu E giao hai child-MBR thì phải chèn object-entry vào cả hai.”** Sai với R-tree cơ bản: một object-entry thường được gán vào **một lá**.
3. **“Hai child-MBR chồng lấn nghĩa là object bị nhân bản.”** Sai: hai nhóm khác object vẫn có MBR chồng lấn.
4. **“Mỗi lần chèn phải chia lại mọi nhánh có MBR giao E.”** Sai. Chèn đi theo **một đường ChooseSubtree**, split chỉ lan nếu có overflow.
5. **“Diện tích hộp bao luôn bằng tổng diện tích các object.”** Sai. Hộp bao chứa khoảng trống và có thể bao những object chồng lấn.
6. **“Chọn độ tăng diện tích nhỏ nhất bảo đảm overlap nhỏ nhất.”** Sai. Hai thước đo khác nhau.
7. **“Minimum enlargement bảo đảm query sau này nhanh nhất.”** Sai. Đó là heuristic cục bộ, nhạy lịch sử chèn.
8. **“Area enlargement chỉ cần tính diện tích của E.”** Sai. Nó là diện tích MBR mới trừ diện tích MBR nhóm hiện tại.
9. **“Đưa E vào một nhóm đã chứa nó sẽ luôn thắng mọi tiêu chí.”** Với area enlargement, nó có \(\Delta A=0\), nhưng nếu nhiều nhóm cùng 0 cần tie-break; với overlap criterion có thể cần xét thêm tác động tới nhóm anh em.
10. **“Khi node có đúng M entry phải split ngay.”** Sai. Overflow xảy ra khi **vượt M**, tức khi thêm entry thứ \(M+1\).
11. **“Split là chia miền không gian thành hai vùng rời nhau.”** Sai. Nó chia **tập entry**; MBR hai nhóm có thể giao nhau.
12. **“Min-fill áp dụng y hệt cho cả root.”** Sai. Root có quy tắc sức chứa đặc biệt.
13. **“Tách 5 entry thành (1,4) hợp lệ với m=2.”** Sai. Nhóm có 1 entry vi phạm min-fill.
14. **“Mọi lần split phải tạo hai nhóm bằng nhau tuyệt đối.”** Không bắt buộc; chỉ cần đạt min/max và đúng chính sách split.
15. **“PickSeeds của quadratic split chọn hai tâm xa nhất.”** Không chính xác. Nó chọn cặp có **waste diện tích MBR lớn nhất**.
16. **“Waste luôn không âm.”** Sai. Hộp chồng lấn có thể tạo waste âm.
17. **“PickNext luôn chọn entry gần seed theo khoảng cách Euclid.”** Sai. Nó chọn theo **chênh lệch area enlargement** của hai nhóm.
18. **“Có thể bỏ qua min-fill cho tới khi không còn entry.”** Sai. Phải ép các entry còn lại vào nhóm đang cần chúng trước khi không thể đạt m.
19. **“Group MBR chỉ cần tính từ hai seeds.”** Sai. Phải mở rộng theo **mọi entry đã gán**.
20. **“Sau split, dùng nguyên MBR cũ cho cả hai nhóm là tối ưu.”** Sai. Dù có thể vẫn bao dữ liệu, nó tạo overlap/coverage nhân tạo.
21. **“Chỉ cập nhật bbox của node lá, không cần cha.”** Sai. MBR của các tổ tiên phải bao hộp mới để tránh bỏ sót query.
22. **“Split leaf xong là hết; cha không bị ảnh hưởng số entry.”** Sai. Cha nhận thêm child-entry, có thể overflow.
23. **“Split root làm một số lá sâu hơn các lá khác.”** Sai trong R-tree đúng. Root mới nâng **toàn bộ** cây thêm một cấp.
24. **“R-tree luôn thấp nên query giao hộp chỉ đi một đường.”** Sai. Overlap làm mở nhiều nhánh cùng cấp.
25. **“Một query với k=0 chắc chắn rẻ.”** Sai. Nhiều MBR cha có thể giao Q trong vùng trống.
26. **“Overlap area bằng 0 chứng minh không query nào phải mở hai nhánh.”** Sai với MBR chạm cạnh hoặc suy biến thành điểm/đoạn.
27. **“Tổng diện tích MBR là diện tích hợp vùng.”** Sai: các MBR chồng lấn sẽ bị đếm nhiều lần; cộng qua nhiều cấp còn cộng lại cùng vùng.
28. **“Tổng overlap area phản ánh chính xác số I/O.”** Sai. I/O còn phụ thuộc page, cache, lịch sử truy vấn, branch forks và độ lấp đầy.
29. **“Linear split luôn kém quadratic split.”** Không có bảo đảm tổng quát; quadratic đắt hơn nhưng vẫn có thể tạo overlap đáng kể.
30. **“R\*-tree chỉ thay tên của quadratic split.”** Sai. Nó có thể thay choose-subtree, split criteria và forced reinsertion.
31. **“Forced reinsertion có thể thực hiện tùy ý vô hạn.”** Sai. Cần giới hạn/kiểm soát theo cấp và một chuỗi chèn.
32. **“Cùng bộ object, đổi thứ tự chèn thì cấu trúc R-tree phải giống nhau.”** Sai. Heuristic phụ thuộc cấu trúc tại thời điểm chèn.
33. **“Đổi thứ tự chèn được phép làm thay đổi tập object kết quả.”** Sai nếu thuật toán đúng và dùng cùng predicate hình học.
34. **“MBR cha nới rộng sẽ làm query sai.”** Không nhất thiết: hộp rộng vẫn bao dữ liệu, nhưng prune kém.
35. **“MBR cha nhỏ hơn dữ liệu thật chỉ làm giảm overlap.”** Sai nguy hiểm: có thể khiến query prune sai và bỏ sót.
36. **“Polygon giao MBR truy vấn tức là polygon giao Q.”** Sai. Broad phase phải refine theo hình học thật.
37. **“Hình chỉ chạm cạnh thì không cần xét trong truy vấn giao hộp đóng.”** Sai. Giao đóng bao gồm cạnh/đỉnh.
38. **“MBR suy biến có area=0 là dữ liệu không hợp lệ.”** Sai. Điểm/đoạn có hộp bao hợp lệ với diện tích 0.
39. **“R-tree 3D có thể dùng công thức giao 2D.”** Sai. Phải xét cả z và các trục còn lại.
40. **“Chiều cao \(\log n\) đồng nghĩa thời gian truy vấn \(\log n\).”** Sai. Có thể duyệt \(\Theta(n)\) entry nếu rất nhiều MBR liên quan.
41. **“Các trường hợp số thực cực lớn luôn tính area hữu hạn vì tọa độ hữu hạn.”** Sai. Phép trừ/tích vẫn có thể tràn, làm heuristic thiếu tin cậy.
42. **“Quét tuyến tính là baseline vô ích.”** Sai. Nó dễ kiểm chứng, đồng thời có thể tốt hơn cây khi dữ liệu nhỏ, query quá rộng hoặc cập nhật quá nhiều.

## 23. Bài tập tự kiểm tra kèm lời giải

### Câu 1. Hộp bao chung

Cho \(A=[0,2]\times[1,3]\) và \(B=[4,6]\times[-1,2]\). Hãy tính MBR chung.

**Lời giải:** Lấy min và max trên từng trục:

\[
\boxed{\operatorname{cover}(A,B)=[0,6]\times[-1,3].}
\]

Hộp chung có diện tích \(6\cdot4=24\), lớn hơn tổng diện tích riêng \(4+6=10\) vì bao cả khoảng trống giữa hai hình.

### Câu 2. Area enlargement

Một nhóm có \(R=[0,4]\times[0,4]\). Chèn E=\([3,5]\times[1,2]\) vào nhóm ấy. Tính \(\Delta_A\).

**Lời giải:** Hộp mới \([0,5]\times[0,4]\), diện tích mới 20, cũ 16:

\[
\boxed{\Delta_A=20-16=4.}
\]

### Câu 3. So hai nhánh

Nhánh A tăng diện tích 4 khi thêm E, nhánh B tăng diện tích 12. Heuristic minimum enlargement chọn nhánh nào?

**Lời giải:** **Nhánh A**. Đây là quyết định cục bộ theo diện tích mở rộng, không phải khẳng định A luôn tạo overlap toàn cây nhỏ hơn.

### Câu 4. Tie khi chọn nhánh

Hai nhánh đều có enlargement 0; MBR của A có diện tích 10, của B diện tích 20. Theo tie-break nêu ở mục 5, chọn gì?

**Lời giải:** **A**, vì sau khi hòa enlargement, ưu tiên diện tích MBR hiện tại nhỏ hơn. Nếu tiếp tục hòa, có thể xét số entry rồi vị trí.

### Câu 5. Overlap area khác intersects

Cho \(A=[0,4]\times[0,4]\), \(B=[4,7]\times[2,6]\). Hai hình có giao không? overlap area bằng bao nhiêu?

**Lời giải:** Chúng **giao theo tập hợp** tại đoạn \(\{4\}\times[2,4]\). Độ rộng giao theo x là 0, do đó:

\[
\boxed{\operatorname{overlapArea}(A,B)=0.}
\]

Query đóng đúng cạnh x=4 vẫn có thể mở cả hai nhánh.

### Câu 6. Tính diện tích overlap dương

Cho \(A=[0,6]\times[0,6]\), \(B=[4,10]\times[4,10]\). Tính overlap area.

**Lời giải:** Giao là \([4,6]\times[4,6]\), rộng 2, cao 2:

\[
\boxed{\operatorname{overlapArea}(A,B)=2\cdot2=4.}
\]

### Câu 7. Một object-entry có bị nhân đôi không?

Q giao cả hai child-MBR của root. Có thể kết luận cùng một object-ID nằm ở cả hai lá không?

**Lời giải:** **Không.** Trong R-tree cơ bản, mỗi object-entry được lưu ở **một lá**, còn MBR của hai nhóm khác object vẫn có thể giao nhau.

### Câu 8. Ngưỡng tràn

Node R-tree có \(M=4\) và hiện giữ 4 entry. Nó đã overflow chưa? Thêm một entry nữa thì sao?

**Lời giải:** 4 entry là **hợp lệ**, chưa overflow. Thêm entry thứ năm thành \(M+1=5\), cần split hoặc cơ chế overflow hợp lệ khác của biến thể.

### Câu 9. Min-fill của hai nhóm

Với \(M=4,m=2\), node tràn tới 5 entry. Những kích thước nhóm nào hợp lệ?

**Lời giải:** Chỉ các cặp \((2,3)\) hoặc \((3,2)\). Cặp \((1,4)\) vi phạm \(m=2\).

### Câu 10. Waste của hai hộp xa nhau

Cho \(A=[0,1]\times[0,1]\), \(B=[4,5]\times[0,1]\). Tính waste khi xét cặp seeds.

**Lời giải:** MBR chung \([0,5]\times[0,1]\) có diện tích 5; hai hộp riêng diện tích 1 mỗi hộp:

\[
\boxed{\operatorname{waste}=5-1-1=3.}
\]

### Câu 11. Waste âm

Cho hai hộp giống nhau \(A=B=[0,4]\times[0,4]\). Waste của chúng có thể âm không?

**Lời giải:** Có:

\[
\boxed{\operatorname{waste}=16-16-16=-16.}
\]

Công thức PickSeeds không mặc định waste không âm.

### Câu 12. PickNext

Một entry E có \(\Delta_A=2\), \(\Delta_B=20\); entry F có \(\Delta_A=7\), \(\Delta_B=8\). Quadratic PickNext chọn entry nào trước?

**Lời giải:** Chênh lệch E là \(|2-20|=18\); F là \(|7-8|=1\). Chọn **E** trước vì chênh lệch lớn hơn, rồi ưu tiên đưa E vào nhóm A nếu không có min-fill bắt buộc.

### Câu 13. Forced min-fill

Chọn \(m=2\). Nhóm A có 3 entry, B có 1 entry, và chỉ còn 1 entry chưa gán. Có thể đưa entry cuối vào A nếu enlargement A nhỏ hơn không?

**Lời giải:** **Không.** Phải đưa entry cuối vào B để B đạt min-fill 2. Điều kiện bất biến cấu trúc ưu tiên hơn heuristic enlargement.

### Câu 14. Phân nhóm trái/phải so với ghép đối diện

Với bốn entry ở mục 7, phân nhóm xấu có tổng diện tích MBR là 61, overlap 25; phân nhóm trái/phải có tổng diện tích 28, overlap 0. Phương án nào có khả năng mở ít nhánh hơn cho Q nhỏ ở \(x=4.5\)?

**Lời giải:** **Nhóm trái/phải** có khả năng ít nhánh hơn: child-MBR trái kết thúc tại x=3, nên một Q nhỏ quanh x=4.5 chỉ giao phía phải. Với nhóm đối diện, Q có thể giao cả hai MBR. Đây là so sánh cho Q cụ thể, không phải bảo đảm mọi Q đều như vậy.

### Câu 15. Root split

Root ban đầu là lá chứa M=4 entry. Thêm entry thứ năm và split thành 2 và 3 entry. Điều gì xảy ra với cấu trúc?

**Lời giải:** Hai nhóm trở thành **hai node lá**. Một **root mới** chứa hai child-entry trỏ tới chúng; cây tăng **một cấp**, và mọi lá vẫn ở độ sâu bằng nhau.

### Câu 16. Split lan lên cha

Một lá đã đầy và cha của nó cũng có đúng M child-entry. Khi lá split, cha có thể gặp điều kiện gì?

**Lời giải:** Cha nhận thêm **một** child-entry cho sibling mới, nên số entry tăng từ M lên \(M+1\): **cha overflow** và có thể phải split tiếp.

### Câu 17. MBR cũ được sao sang hai node sau split

Hai nhóm con sau split đều giữ nguyên MBR cũ của node cha trước khi split. Điều này có thể đúng về dữ liệu không và vì sao vẫn không tốt?

**Lời giải:** Nếu MBR cũ **bao đủ mọi entry**, hai hộp con vẫn có thể là cận bao an toàn, nên truy vấn không nhất thiết sai. Nhưng nó tạo **coverage/overlap nhân tạo**, khiến Q chạm cả hai nhánh nhiều hơn. Nên tính lại MBR **chặt** từ mỗi nhóm.

### Câu 18. MBR tổ tiên thiếu dữ liệu

Một object mới có MBR \([20,22]\times[20,22]\) đã ở lá, nhưng MBR root vẫn \([0,10]\times[0,10]\). Truy vấn quanh (21,21) có nguy cơ gì?

**Lời giải:** Query có thể thấy MBR root **không giao Q** rồi bỏ toàn bộ cây, gây **false negative**. Phải cập nhật MBR dọc đường lên root.

### Câu 19. Overlap area bằng 0 nhưng vẫn có branch forks

Hai child-MBR đều bằng \([2,2]\times[2,2]\). Overlap area của chúng bằng bao nhiêu? Truy vấn điểm Q tại \((2,2)\) phải làm gì?

**Lời giải:** Overlap area bằng **0** vì hai hộp suy biến diện tích 0. Nhưng query Q **giao cả hai**, nên phải xét cả hai nhánh nếu chúng là hai nhóm object khác nhau.

### Câu 20. Truy vấn kết quả rỗng mà vẫn tốn kém

Q giao MBR của 20 cây con nhưng không giao bất kỳ object-entry nào. Có thể báo rằng truy vấn chỉ tốn \(O(1)\) vì k=0 không?

**Lời giải:** **Không.** Thuật toán vẫn phải mở các node liên quan và kiểm tra entry để chứng minh không có kết quả. Chi phí phụ thuộc \(V\) và \(E_V\), không chỉ k.

### Câu 21. Tổng số cặp seeds

Node có 9 entry sau tràn. PickSeeds kiểm tra bao nhiêu cặp?

**Lời giải:**

\[
\binom92=\frac{9\cdot8}{2}=\boxed{36}.
\]

Nếu số entry là \(M+1\), số cặp thuộc \(\Theta(M^2)\).

### Câu 22. Độ phức tạp chèn có split

Nếu một lần chèn đi qua h cấp, mỗi cấp phải xét tối đa M entry và có S lần quadratic split, hãy viết cận CPU đơn giản.

**Lời giải:**

\[
\boxed{O(Mh+SM^2),\quad S\le h.}
\]

Với M cố định theo kích thước page, chi phí thường tăng theo số cấp; nhưng tính I/O và chính sách tối ưu overlap có thể làm hằng số đáng kể.

### Câu 23. Thứ tự chèn và tính đúng

Cùng tập object nhưng hai thứ tự chèn khác nhau tạo hai cây có cấu trúc, số split và overlap khác nhau. Hai cây có thể trả **tập ID khác nhau** cho cùng phép giao Q không?

**Lời giải:** **Không**, nếu cả hai đúng và dùng cùng predicate. Heuristic ảnh hưởng hiệu năng và nhóm dữ liệu, **không được làm đổi kết quả toán học**.

### Câu 24. Chọn chính sách cho hai workload

(a) Hàng triệu MBR gần như tĩnh, thường truy vấn cửa sổ nhỏ; (b) vài trăm đối tượng cập nhật liên tục, truy vấn rất ít. Nêu phương án đáng thử.

**Lời giải:** (a) Thử **bulk loading STR**, R-tree/R\*-tree ít overlap và benchmark theo số node/page được thăm. (b) **Quét tuyến tính hoặc lưới đơn giản** có thể có tổng chi phí tốt hơn duy trì cây với split/condense thường xuyên. Không chọn chỉ dựa trên chiều cao cây.

## 24. Tổng kết và quy trình áp dụng

**Chèn R-tree** gồm chọn một nhánh theo heuristic, chèn object-entry tại lá, cập nhật MBR lên tổ tiên và **split** nếu vượt số entry tối đa M. Một lần split có thể lan ngược qua nhiều cấp, thậm chí tạo root mới; sau mọi bước, phải giữ **min-fill, max-fill, tất cả lá cùng độ sâu và MBR cha bao đủ dữ liệu con**.

**Quadratic split** chọn hai hạt giống có waste diện tích bao chung lớn, sau đó chọn entry còn lại có chênh lệch enlargement giữa hai nhóm lớn nhất. Điều kiện min-fill có quyền **buộc phân nhóm không đẹp về hình học**. Vì vậy ngay cả split hợp lệ vẫn có thể tạo những MBR rộng hoặc chồng lấn.

**Overlap ảnh hưởng truy vấn** vì một cửa sổ Q có thể giao MBR của nhiều child-entry và phải mở **tất cả nhánh có khả năng chứa kết quả**. Chiều cao nhỏ không đủ để bảo đảm tìm kiếm nhanh. Ngoài overlap area, còn cần theo dõi coverage, margin, node visits, entry tests, branch forks và I/O; với MBR suy biến, overlap area bằng 0 vẫn có thể có nhiều nhánh được mở.

**R-tree cơ bản, R\*-tree và bulk loading** có những lựa chọn tối ưu khác nhau. Minimum area enlargement và quadratic split dễ triển khai; R\*-tree có thể quan tâm rõ hơn đến overlap/margin và forced reinsertion; STR có thể phù hợp khi dữ liệu tĩnh và được nạp thành lô. Không có chiến lược nào được bảo đảm thắng trên mọi phân bố.

Quy trình thực hành nên là:

1. Xác định **kiểu object, hệ tọa độ, predicate giao/tiếp xúc và tỷ lệ query–update**.
2. Chọn M,m theo bộ nhớ hoặc kích thước page, rồi định nghĩa bất biến node/root.
3. Cài **ChooseSubtree, split, cập nhật MBR và xử lý root** với tie-break rõ ràng.
4. Kiểm tra dữ liệu **trùng MBR, chạm biên, node vừa tràn, root split, query không có kết quả**.
5. So tập ID với **quét tuyến tính độc lập**, và refine hình học thật nếu cần.
6. Đo **overlap/coverage** cùng **node visits, branch forks, độ trễ, bộ nhớ và I/O** trên nhiều thứ tự chèn.
7. Nếu cây mất chọn lọc sau nhiều cập nhật, cân nhắc thay heuristic, **R\*-tree hoặc rebuild/bulk loading**.

Một R-tree tốt không chỉ **giữ dữ liệu đúng**; nó còn **nhóm đối tượng hợp lý để giảm số nhánh phải duyệt**. Nhưng tối ưu cấu trúc luôn phải đứng sau **bất biến bao phủ**: một node được cắt tỉa sai có thể khiến cả hệ thống bỏ sót những đối tượng mà truy vấn cần tìm.
