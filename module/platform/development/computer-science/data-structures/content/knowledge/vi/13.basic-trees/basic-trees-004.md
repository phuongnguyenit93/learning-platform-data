# Cây có thứ tự, cây không thứ tự và rừng

Trong cấu trúc dữ liệu, **cây** (*tree*) biểu diễn quan hệ phân cấp giữa các đối tượng: thư mục chứa tệp, thành phần giao diện chứa thành phần con, biểu thức có toán hạng, hoặc tổ chức gồm các phòng ban. Tuy nhiên, không phải cây nào cũng mang cùng một ý nghĩa về **thứ tự**. Có bài toán mà hai nút con đổi vị trí là **thay đổi quan trọng**; ở bài toán khác, chúng vẫn biểu diễn cùng một quan hệ cha–con. Khi có nhiều cây tách biệt, ta cần khái niệm **rừng** (*forest*).

Bài học thuộc chương **Cây cơ bản** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Ta sẽ xác định rõ cây có thứ tự, cây không thứ tự và rừng; nghiên cứu bất biến, cách lưu trong bộ nhớ, các phép duyệt/thêm/xóa/chuyển cây con và độ phức tạp. Mục tiêu là chọn biểu diễn phù hợp với dữ liệu, thay vì vô tình đưa thêm hoặc làm mất thông tin thứ tự.

> **Phân biệt từ đầu:** Trong bài này, **cây có thứ tự** (*ordered tree*) là **cây có gốc mà các con của mỗi nút được sắp theo một thứ tự xác định**. Nó **không đồng nghĩa** với *binary search tree* (BST, cây tìm kiếm nhị phân), nơi các khóa phải thỏa một quy tắc so sánh.

## 1. Ôn lại cây có gốc và các thuật ngữ

Một **cây không hướng** trong lý thuyết đồ thị là đồ thị **liên thông** và **không có chu trình**. Khi chọn một đỉnh đặc biệt \(r\) làm **gốc** (*root*) và hướng các quan hệ từ gốc xuống, ta có **cây có gốc** (*rooted tree*).

Với cây có gốc:

- **Nút** (*node/vertex*): một thực thể trong cây.
- **Cạnh** (*edge*): quan hệ nối hai nút.
- **Cha** (*parent*): nút liền trước trên đường đi duy nhất từ gốc đến một nút không phải gốc.
- **Con** (*child*): nút có cha là nút đang xét.
- **Anh em** (*siblings*): các nút có chung một cha.
- **Lá** (*leaf*): nút không có con.
- **Nút trong** (*internal node*): nút có ít nhất một con.
- **Cây con** (*subtree*): một nút cùng toàn bộ hậu duệ của nó.
- **Độ sâu** (*depth*): số cạnh từ gốc tới nút; gốc có độ sâu 0.
- **Chiều cao** (*height*) của một nút: số cạnh trên đường đi dài nhất từ nút đó tới một lá. Theo quy ước của bài, lá có chiều cao 0; cây một nút có chiều cao 0.

Xét cây:

~~~text
          A              A là gốc
        /   \
       B     C            B, C là con của A
      / \     \
     D   E     F          D, E, F là lá
~~~

Cây có 6 nút, 5 cạnh; gốc A có hai con B và C; B có hai con D và E. Đường từ A tới E là \(A\rightarrow B\rightarrow E\), nên độ sâu của E bằng 2. Chiều cao của A là 2.

**Bất biến cấu trúc** của một cây có gốc hữu hạn là: gốc không có cha; mọi nút khác có **đúng một cha**; không có chu trình; và mọi nút đều đạt tới được từ gốc. Bởi vậy giữa gốc và mỗi nút luôn có **một đường đi duy nhất**.

Trong một cây có \(n\ge1\) nút:

\[
\boxed{|E|=n-1.}
\]

Việc chọn gốc và quyết định thứ tự các con **không làm thay đổi** số cạnh.

## 2. Cây có thứ tự: thứ tự của các con là một phần dữ liệu

Một **cây có thứ tự có gốc** (*ordered rooted tree*) là cây có gốc trong đó **các con của mỗi nút tạo thành một dãy có thứ tự**, thường viết:

\[
\operatorname{children}(u)=[c_0,c_1,\ldots,c_{d-1}],
\]

với \(d\) là số con của nút \(u\). Hai nút con có thể được phân biệt bằng vị trí **thứ nhất, thứ hai, ...**, không chỉ bằng việc chúng cùng thuộc một cha.

Ví dụ:

~~~text
Cây T1                 Cây T2

      A                     A
   /  |  \               /  |  \
  B   C   D             D   B   C
~~~

Hai hình có **cùng các nút**, **cùng quan hệ cha–con** và **cùng số cạnh**, nhưng là **hai cây có thứ tự khác nhau** nếu thứ tự các con của A là một phần của dữ liệu:

- \(T_1\): \(\operatorname{children}(A)=[B,C,D]\).
- \(T_2\): \(\operatorname{children}(A)=[D,B,C]\).

Đổi chỗ B và D không tạo hay xóa cạnh, nhưng thay đổi **vị trí anh em**. Vì vậy, đối với cây có thứ tự, phép hoán vị con thường là một **thao tác cập nhật có ý nghĩa**.

### Khi nào thứ tự là bắt buộc?

- **Biểu thức và cú pháp:** toán tử trừ \(a-b\) khác \(b-a\); vị trí toán hạng quan trọng.
- **DOM hoặc cây giao diện:** thứ tự các phần tử con có thể quyết định thứ tự hiển thị.
- **Danh mục có thứ tự ưu tiên:** danh sách bước xử lý, menu điều hướng, các mục trong tài liệu.
- **Cây quyết định:** nhánh trái/phải hoặc thứ tự các lựa chọn có thể được quy ước mang ý nghĩa khác nhau.

Trong những trường hợp này, lưu con dưới dạng **danh sách** hoặc cấu trúc hỗ trợ thứ tự là lựa chọn tự nhiên. Thứ tự không nhất thiết theo tên hay khóa; nó có thể đến từ **thứ tự xuất hiện**, **thứ tự do người dùng sắp** hoặc một quy tắc nghiệp vụ.

## 3. Cây không thứ tự: chỉ quan hệ phân cấp là quan trọng

Một **cây có gốc không thứ tự** (*unordered rooted tree*) có cùng cấu trúc cha–con nhưng **không gán ý nghĩa cho thứ tự anh em**. Ta quan tâm đến việc mỗi nút có **tập các nút con**, chứ không phân biệt “con đầu tiên” hay “con cuối cùng”.

Với hai hình ở mục 2, nếu A vẫn là cha của B, C và D, và không có quy tắc bổ sung về thứ tự, chúng mô tả **cùng một cây không thứ tự**. Vẽ lại các con từ trái sang phải không thay đổi cấu trúc.

Ví dụ:

~~~text
        Team                   Team
       /    \                 /    \
    Backend  Frontend      Frontend Backend
~~~

Nếu cấu trúc chỉ ghi nhận hai nhóm đều thuộc Team, hai cách vẽ là tương đương. Nếu UI yêu cầu Frontend luôn đứng trước Backend thì hệ thống lại **đang bổ sung thứ tự hiển thị**, và cần lưu hoặc suy ra quy tắc đó.

### Cẩn thận với từ “tập”

Trong triển khai, hai nút con khác nhau có thể **mang cùng nhãn**. Chẳng hạn một thư mục có hai đối tượng trong các namespace khác nhau cùng hiển thị tên “Báo cáo”, hoặc một cây cú pháp có nhiều nút nhãn “+”. Do đó không thể dùng **tập nhãn chuỗi** để thay thế **tập đối tượng nút** nếu điều đó làm gộp nhầm các nút khác nhau.

Ví dụ:

~~~text
     A
   /   \
 X(1)  X(2)        Hai nút con riêng biệt, cùng nhãn "X".
~~~

Các nút X(1) và X(2) có **định danh riêng**, dù nhãn trùng. “Không thứ tự” nghĩa là không quan tâm vị trí anh em, **không** có nghĩa là được tự động loại bỏ những nút trùng nhãn.

## 4. Các loại thứ tự dễ bị nhầm lẫn

Một cây có thể có nhiều kiểu ràng buộc. Cần tách rõ:

| Khái niệm | Điều bị ràng buộc | Ví dụ |
| --- | --- | --- |
| **Ordered rooted tree** | **Thứ tự giữa các con** của mỗi nút | Con của A là \([B,C,D]\) chứ không phải \([D,B,C]\) |
| **Unordered rooted tree** | Không có thứ tự anh em mang ý nghĩa | Cùng các quan hệ cha–con; vẽ B trước C hay C trước B đều được |
| **Binary tree** | Mỗi nút có tối đa hai vị trí con phân biệt là **trái** và **phải** | Một nút chỉ có con trái khác với chỉ có con phải |
| **Binary search tree (BST)** | Quy tắc **so sánh khóa** giữa cây con trái, nút và cây con phải | Thường khóa bên trái nhỏ hơn khóa nút, bên phải lớn hơn theo quy ước |
| **Heap** | Quan hệ ưu tiên giữa khóa cha và con, cộng ràng buộc hình dạng | Min-heap: khóa cha không lớn hơn khóa con |
| **Cây sắp theo nhãn hiển thị** | Thứ tự trình bày được xác định bởi phép sắp xếp | Con hiển thị tăng dần theo tên |

**Ordered rooted tree không mặc nhiên là BST.** Ví dụ một cây có gốc A với các con theo thứ tự \([Z,B,K]\) vẫn là cây có thứ tự hoàn toàn hợp lệ, dù nhãn không được sắp tăng dần.

**Binary tree có thông tin vị trí trái/phải**, nên thường được coi là một dạng cây có thứ tự đặc biệt. Nhưng chỉ có hai vị trí con với ngữ nghĩa rõ ràng **không đồng nghĩa** mọi cây có thứ tự đều nhị phân: cây có thứ tự có thể có 0, 1, 2 hay nhiều con tùy bài toán.

**Rừng** ở các mục sau là một khái niệm khác: nó nói về **số thành phần cây**, không phải thứ tự giữa các con.

## 5. Rừng: nhiều cây tách rời

Trong lý thuyết đồ thị, một **rừng** (*forest*) là **đồ thị vô hướng không có chu trình**. Rừng có thể gồm một cây liên thông, nhiều cây tách biệt, các đỉnh cô lập hoặc không có đỉnh nào. **Mỗi thành phần liên thông** của rừng là một cây.

Khi mỗi thành phần được chọn một gốc, ta có **rừng có gốc** (*rooted forest*).

~~~text
   Cây thứ nhất       Cây thứ hai       Cây thứ ba

        A                  G                 K
       / \                 |                 (lá)
      B   C                H
     /
    D

             Rừng có ba cây, ba gốc A, G, K.
~~~

Các thành phần **không có cạnh nối với nhau**. Nếu thêm cạnh A—G, hai thành phần sẽ trở thành **một cây lớn hơn** khi cạnh được thêm đúng cách và không tạo chu trình.

### Công thức số cạnh của một rừng

Gọi \(n=|V|\) là số đỉnh và \(c\) là số thành phần liên thông. Vì mỗi cây thành phần có \(n_j-1\) cạnh:

\[
|E|=\sum_{j=1}^{c}(n_j-1)
=\left(\sum_{j=1}^{c}n_j\right)-c
=\boxed{n-c}.
\]

Ví dụ hình trên có \(n=4+2+1=7\) nút, \(c=3\) cây, nên có \(7-3=4\) cạnh. Cây chỉ có một đỉnh K vẫn là một thành phần hợp lệ và đóng góp **0 cạnh**.

Với rừng rỗng, \(n=0,c=0\), công thức vẫn cho \(|E|=0\). Với một cây không rỗng, \(c=1\), ta thu lại công thức \(|E|=n-1\).

### Rừng có thứ tự và rừng không thứ tự

Trong một **rừng có thứ tự** (*ordered forest*), ta có thể lưu:

1. Thứ tự các con **bên trong từng cây**.
2. Thứ tự **các cây gốc** trong một dãy \([r_0,r_1,\ldots,r_{c-1}]\).

Một **rừng không thứ tự** không gán ý nghĩa cho thứ tự các cây thành phần và các con của từng nút. Cần đọc đúng quy ước của ứng dụng: có hệ thống coi **thứ tự trong cây** là quan trọng nhưng **thứ tự các gốc trong rừng** lại không.

Ví dụ, danh sách ba cửa sổ đang mở có thể cần thứ tự hiển thị giữa các cửa sổ, còn một tập ba dự án độc lập có thể không cần thứ tự giữa các cây dự án.

## 6. Tương đương cấu trúc: khi nào hai cây được xem là giống nhau?

Việc “hai cây giống nhau” phải xác định rõ **nhãn nút**, **thứ tự con** và việc có **giữ định danh nút** hay không.

Nếu so sánh hai cây có gốc **có nhãn** về mặt cấu trúc:

- Hai cây **có thứ tự** tương đương khi nhãn gốc bằng nhau và **các cây con tương ứng theo đúng thứ tự** cũng tương đương.
- Hai cây **không thứ tự** tương đương khi nhãn gốc bằng nhau và **có thể ghép cặp các cây con** để chúng tương đương, **không phụ thuộc vị trí**.

~~~text
Cây T1:                 Cây T2:

      A                       A
     / \                     / \
    B   C                   C   B
   /                         \
  D                           D
~~~

Hai cây trên **không tương đương** dù bỏ thứ tự con, vì ở T1 nút B có con D, còn ở T2 nút C có con D. Muốn có ví dụ tương đương không thứ tự, phải đổi **vị trí của cả cây con**:

~~~text
Cây T1:                 Cây T3:

      A                       A
     / \                     / \
    B   C                   C   B
   /                             \
  D                               D
~~~

Ở T3, D vẫn là con của B. Khi đó T1 và T3:

- Khác nhau nếu coi thứ tự con của A là một phần dữ liệu: \([B,C]\neq[C,B]\).
- Tương đương nếu bỏ thứ tự anh em, vì **cùng cấu trúc gốc, nhãn và quan hệ cha–con**.

Nếu **các nút có định danh cố định** (như ID bản ghi trong database), có thể kiểm tra đơn giản xem mỗi node ID có cùng cha hay không. Nếu so sánh **cấu trúc trừu tượng không giữ định danh**, cần một phép kiểm tra tương đương cấu trúc (*tree isomorphism*) phù hợp.

Điều này quan trọng khi xây công cụ so sánh DOM, cấu trúc XML/JSON, cây biểu thức hoặc rừng các thành phần độc lập.

## 7. Cách biểu diễn cây có thứ tự, cây không thứ tự và rừng

Không có cấu trúc lưu trữ duy nhất tối ưu cho mọi trường hợp. Lựa chọn phụ thuộc khả năng truy cập cha/con, thay đổi thứ tự, thêm/xóa cây con và giới hạn bộ nhớ.

### 7.1. Danh sách con (*children list*)

Với mỗi nút, lưu một danh sách:

~~~text
A.children = [B, C]
B.children = [D, E]
C.children = [F]
D.children = []
E.children = []
F.children = []
~~~

Đây là biểu diễn tự nhiên của cây có thứ tự. Lấy con thứ \(i\) có thể \(O(1)\) nếu danh sách được lưu bằng mảng động; nhưng chèn hoặc xóa **ở giữa danh sách** có thể cần dịch chuyển \(O(d)\) phần tử, trong đó \(d\) là số con của cha.

Đối với cây không thứ tự, vẫn **có thể dùng danh sách** cho tiện triển khai; chỉ cần bảo đảm thuật toán **không xem vị trí phần tử trong danh sách là ngữ nghĩa của dữ liệu**. Khi hiển thị, có thể sắp con theo tên để ổn định đầu ra, nhưng đó là một quy tắc trình bày bổ sung.

### 7.2. Tập con (*children set*) hoặc ánh xạ theo định danh

Nếu thứ tự anh em không quan trọng và chủ yếu cần kiểm tra một nút có phải con trực tiếp hay không, có thể dùng **set/map theo định danh nút**. Thêm và kiểm tra thành viên có thể đạt \(O(1)\) **kỳ vọng** với hash phù hợp, nhưng:

- Không có vị trí con thứ nhất/thứ hai mang ý nghĩa.
- Không được làm mất các nút khác nhau chỉ vì **nhãn trùng**.
- Không mặc nhiên có thứ tự duyệt ổn định.
- Tập con chỉ mô tả quan hệ **cạnh trực tiếp**; bất biến toàn cây vẫn cần được duy trì.

### 7.3. Con trỏ cha (*parent pointer*)

Mỗi nút có thể lưu thêm \(\operatorname{parent}(u)\) để từ một nút đi ngược lên gốc. Với nút không phải gốc, con trỏ cha chỉ tới đúng một nút; với gốc, parent là **None/null**.

Có con trỏ cha:

- Lấy cha trực tiếp: \(O(1)\).
- Tìm tổ tiên/gốc bằng cách lần theo cha: \(O(h)\), với \(h\) là số cạnh đi lên.
- Kiểm tra chuyển cây con có tạo chu trình không: thường có thể duyệt **chuỗi tổ tiên của cha mới** trước khi gắn.

Đánh đổi là thêm một tham chiếu trên mỗi nút và phải **cập nhật hai chiều** khi chuyển nút. Nếu con trỏ cha không khớp danh sách con, cấu trúc có thể trông đúng khi duyệt xuống nhưng sai khi duyệt lên.

### 7.4. Danh sách cha (*parent array*)

Khi các nút có chỉ số nguyên 0 đến \(n-1\), một mảng \(\operatorname{parent}[i]\) có thể biểu diễn rừng có gốc:

~~~text
Nút:       A   B   C   D   E   F   G
Chỉ số:    0   1   2   3   4   5   6
parent:   -1   0   0   1   1   2  -1
~~~

\(-1\) đánh dấu gốc; ở đây rừng có hai gốc **A và G**. Mỗi nút còn lại có đúng một chỉ số cha. Biểu diễn gọn \(O(n)\) phần tử, nhưng nếu chỉ lưu mảng cha, việc tìm **tất cả con** của một nút có thể cần quét toàn mảng \(O(n)\) nếu chưa xây chỉ mục ngược. Muốn lưu thứ tự anh em, cần thêm **danh sách con có thứ tự** hoặc metadata về vị trí.

**Cẩn thận:** Chỉ điều kiện “mỗi nút có không quá một cha” chưa đủ để khẳng định các parent pointer tạo thành rừng. Ví dụ \(parent[A]=B\) và \(parent[B]=A\) tạo **chu trình hai nút**, không có gốc hợp lệ.

### 7.5. Biểu diễn con đầu tiên – anh em kế tiếp

Một dạng phổ biến cho cây có số con tùy ý là **first-child/next-sibling**:

- \(\operatorname{firstChild}(u)\) trỏ đến con đầu tiên.
- \(\operatorname{nextSibling}(u)\) trỏ đến nút anh em tiếp theo (hoặc null nếu không có).

~~~text
       A: firstChild → B
       B: nextSibling → C
       B: firstChild → D
       D: nextSibling → E
       C: firstChild → F
~~~

Biểu diễn này lưu **thứ tự anh em** qua chuỗi liên kết và dùng số lượng con trỏ cố định cho mỗi nút (ngoài thông tin nút), nhưng truy cập **con thứ \(i\)** có thể phải đi qua \(i\) nút anh em. Với cây không thứ tự, dùng dạng này vẫn được, nhưng thứ tự liên kết không nên bị xem là ý nghĩa.

### 7.6. Biểu diễn rừng

Với rừng có gốc, có thể lưu **danh sách các gốc** cùng cấu trúc nút của từng cây:

~~~text
forest.roots = [A, G, K]   # Rừng có thứ tự: thứ tự gốc có ý nghĩa.
forest.roots = {A, G, K}   # Rừng không thứ tự: tập định danh gốc.
~~~

Mỗi gốc không có cha và các cây con của hai gốc khác nhau **không được chia sẻ cùng một đối tượng nút** nếu cấu trúc đang biểu diễn rừng đúng nghĩa. Nếu hai cây cùng tham chiếu đến một nút con, ta đã có một cấu trúc chia sẻ dạng **DAG hoặc đồ thị khác**, không phải rừng các cây rời nhau.

## 8. Duyệt cây và rừng: thứ tự nào được bảo đảm?

Khi duyệt cây, ta cần xác định rõ **thứ tự giữa các con** và **thứ tự giữa các gốc trong rừng**. Ba cách duyệt phổ biến là:

1. **Preorder (duyệt trước):** xử lý nút hiện tại, sau đó duyệt lần lượt các cây con.
2. **Postorder (duyệt sau):** duyệt lần lượt các cây con, sau cùng mới xử lý nút hiện tại.
3. **Breadth-first search – BFS (duyệt theo chiều rộng):** xử lý theo từng mức từ gốc xuống, thường dùng hàng đợi.

Xét rừng **có thứ tự**, các gốc theo thứ tự \([A,G]\), và cây A:

~~~text
Rừng roots = [A, G]

       A                  G
     /   \
    B     C
   / \     \
  D   E     F
~~~

| Phép duyệt | Kết quả với thứ tự con và gốc đã nêu |
| --- | --- |
| Preorder trên cây A | A, B, D, E, C, F |
| Postorder trên cây A | D, E, B, F, C, A |
| Preorder cả rừng | A, B, D, E, C, F, G |
| Postorder cả rừng | D, E, B, F, C, A, G |
| BFS cả rừng, khởi tạo hàng đợi bằng \([A,G]\) | A, G, B, C, D, E, F |

### Vì sao BFS cả rừng có thể cho A, G trước B?

Khi duyệt **toàn bộ một rừng** theo nhiều nguồn gốc đồng thời, ta có thể đưa **tất cả gốc** vào hàng đợi trước. Khi đó hai gốc A và G đều ở mức 0, nên kết quả BFS bắt đầu bằng A, G.

Một cách khác là **duyệt BFS từng cây riêng biệt rồi nối kết quả**, sẽ cho A, B, C, D, E, F, G. Hai cách phù hợp với hai **quy ước duyệt rừng khác nhau**; phải mô tả rõ phương pháp đang dùng.

### Cây không thứ tự thì kết quả có ổn định không?

Preorder và postorder vẫn có thể thực hiện trên cây không thứ tự, nhưng **không có một dãy nhãn duy nhất được định nghĩa bởi cấu trúc**. Nếu duyệt B trước C thì preorder cây A là A, B, D, E, C, F; nếu duyệt C trước B có thể là A, C, F, B, D, E. Cả hai hợp lệ nếu thứ tự anh em không mang ý nghĩa.

Khi cần đầu ra có thể tái lập (*deterministic*) để ghi log, xuất tệp hoặc kiểm thử, ta có thể **chọn thứ tự trình bày bổ sung** bằng ID hoặc một tiêu chí so sánh đã được quy định. Nhưng việc sắp xếp đó là một **quy tắc của thuật toán xuất dữ liệu**, không nhất thiết biến cây gốc thành cây có thứ tự về mặt ngữ nghĩa.

### Độ phức tạp duyệt

Với \(n\) nút trong một cây hoặc rừng được duyệt đúng một lần:

\[
\boxed{T_{\mathrm{traversal}}=O(n).}
\]

Mỗi nút được xử lý một lần và mỗi cạnh cha–con được đi qua số lần hằng số. Với DFS đệ quy, bộ nhớ ngăn xếp là \(O(h)\) theo độ sâu đường đệ quy lớn nhất của một cây đang duyệt; nếu một rừng có nhiều cây, có thể xử lý lần lượt mà không tăng độ sâu đệ quy theo số gốc. Với BFS, hàng đợi có thể chứa \(O(w)\) nút, trong đó \(w\) là **độ rộng lớn nhất của một mức** khi duyệt rừng theo nhiều nguồn, và \(w\le n\).

Nếu dùng lối duyệt để **tìm một nhãn bất kỳ** mà không có chỉ mục phụ, trường hợp xấu nhất vẫn là \(O(n)\). **Thứ tự anh em không tự làm phép tìm khóa thành \(O(\log n)\)** như một cây tìm kiếm cân bằng.

## 9. Thao tác cập nhật: thêm, đổi thứ tự, tách và ghép

Một phép cập nhật đúng phải giữ **bất biến của cây/rừng**: không chu trình, mỗi nút không phải gốc có đúng một cha, mỗi thành phần có một gốc và các thành phần không chia sẻ nút.

### 9.1. Thêm một nút con

Tạo nút mới \(x\) rồi gắn dưới nút cha \(p\). Nếu là cây có thứ tự, phải quyết định **vị trí chèn** trong dãy con, chẳng hạn:

~~~text
Trước: A.children = [B, C]
Chèn X tại vị trí 1:
Sau:   A.children = [B, X, C]
~~~

Nếu các con nằm trong mảng động, chèn giữa dãy có thể làm dịch chuyển nhiều phần tử; nếu là danh sách liên kết và đã có vị trí chèn, thay đổi con trỏ có thể nhanh hơn. Đối với cây không thứ tự, chỉ cần bổ sung quan hệ cha–con, không cần chọn vị trí ngữ nghĩa.

### 9.2. Đổi thứ tự các con

Ở cây có thứ tự, đổi \([B,C,D]\) thành \([C,B,D]\) là **thay đổi dữ liệu**. Ở cây không thứ tự, hai danh sách chỉ là hai cách biểu diễn của cùng tập con, miễn các nút và quan hệ cha–con không đổi.

Nếu thứ tự thực tế được suy ra từ **nhãn**, **chỉ số ưu tiên** hoặc một phép so sánh, cần giữ nó nhất quán khi các thuộc tính đó thay đổi; nếu không, nên lưu thứ tự rõ ràng thay vì ngầm dựa vào thứ tự lặp của set/hash map.

### 9.3. Tách cây con khỏi cha để tạo một cây mới trong rừng

Đối với cây ở mục 8, nếu tách cây con gốc B khỏi A:

~~~text
Trước:
      A               G
     / \
    B   C
   / \
  D   E

Sau khi tách B:
      A         B         G
      |        / \
      C       D   E
~~~

Chỉ cần **xóa cạnh A—B** và đặt parent của B thành null. Toàn bộ hậu duệ của B **giữ nguyên** dưới B. Rừng ban đầu có hai thành phần A và G; sau khi tách sẽ có ba thành phần A, B, G.

Về đồ thị:

\[
\Delta n=0,\qquad \Delta |E|=-1,\qquad\Delta c=+1,
\]

nên công thức \(|E|=n-c\) vẫn đúng.

### 9.4. Ghép hai cây bằng một cạnh

Giả sử B đang là gốc của một cây khác trong rừng, muốn gắn B làm con của G. Nếu G và B thuộc **hai cây khác nhau**, việc thêm cạnh G—B tạo thành một cây lớn hơn, không tạo chu trình:

~~~text
Trước:    G       B         Sau:      G
                 / \                  |
                D   E                 B
                                     / \
                                    D   E
~~~

Khi ghép:

\[
\Delta n=0,\qquad\Delta |E|=+1,\qquad\Delta c=-1.
\]

Nếu muốn **di chuyển** B từ cha cũ A sang cha mới G, thực chất ta **gỡ cạnh cũ rồi nối cạnh mới**. Số nút không đổi; nếu vẫn chỉ có một cây thành phần, số cạnh của thành phần đó cũng không đổi.

### 9.5. Ngăn chu trình khi chuyển cây con

Không được gắn một nút làm con của **chính nó** hoặc một **hậu duệ của nó**.

~~~text
      A
      |
      B
      |
      C

Sai: chuyển A xuống làm con của C.
Khi đó A → B → C → A tạo chu trình.
~~~

Một cách kiểm tra khi có parent pointer: **trước khi chuyển cây con gốc \(x\) dưới cha mới \(p\)**, đi ngược từ \(p\) lên các tổ tiên. Nếu gặp \(x\), thao tác phải bị từ chối vì \(p\) nằm trong cây con của \(x\).

Nếu không có con trỏ cha, có thể duyệt cây con của \(x\) để xem \(p\) có nằm trong đó không, tốn tối đa \(O(|\operatorname{subtree}(x)|)\).

### 9.6. Xóa nút và xóa toàn bộ cây con không giống nhau

- **Xóa cả cây con:** loại \(x\) cùng toàn bộ hậu duệ khỏi cấu trúc; nếu bộ nhớ do chương trình quản lý, cần giải phóng hoặc thu hồi các nút thích hợp.
- **Chỉ xóa nút \(x\):** phải quyết định xử lý các con của \(x\). Có thể nâng chúng lên cha cũ, tạo thành nhiều gốc mới hoặc từ chối phép xóa.

Ở cây có thứ tự, nếu nâng các con của \(x\) lên cha cũ, cần xác định chúng được chèn ở **vị trí nào và theo thứ tự nào**. Đây là quy tắc nghiệp vụ, không được tự ý chọn mà không thông báo.

## 10. Rừng và phép biến đổi thêm một gốc giả

Một **rừng có gốc** có thể biến thành **một cây có gốc duy nhất** bằng cách thêm một **gốc giả** (*super-root*, *virtual root*) và nối gốc giả tới gốc của từng cây thành phần.

~~~text
Rừng:             Sau khi thêm gốc giả R:

   A      G                 R
  / \     |               /   \
 B   C    H              A     G
                        / \     \
                       B   C     H
~~~

Nếu rừng có \(n\) nút và \(c\) cây, ban đầu số cạnh là \(n-c\). Thêm một nút R và \(c\) cạnh:

\[
n'=n+1,\qquad |E'|=(n-c)+c=n=n'-1.
\]

Do đó kết quả là một cây. Phép biến đổi này hữu ích khi thuật toán hoặc định dạng dữ liệu chỉ chấp nhận **một gốc duy nhất**.

Với rừng có thứ tự, thứ tự các cây thành phần có thể trở thành **thứ tự các con của R**. Nếu rừng không có thứ tự giữa các gốc, ta không nên tự gán ý nghĩa cho vị trí của các con R.

**Cảnh báo:** Gốc giả là một nút **kỹ thuật**, không nhất thiết là đối tượng có thật trong miền dữ liệu. Khi tính số nút, chiều cao, độ sâu hoặc xuất kết quả cho người dùng, cần quyết định có tính R hay bỏ R. Ví dụ, khi thêm R, mọi nút gốc cũ tăng độ sâu thêm 1 so với cấu trúc ban đầu.

## 11. Cài đặt Python: rừng có thứ tự và cập nhật an toàn

Ví dụ dưới đây triển khai một **rừng có thứ tự** với:

- Nút có **định danh đối tượng riêng**, một nhãn hiển thị, danh sách con và con trỏ cha.
- Danh sách gốc của rừng.
- Thao tác **chuyển cây con** (*move*) sang cha mới, **tách cây con** (*detach*) thành một cây độc lập và **đổi thứ tự con** (*reorder*).
- Duyệt DFS preorder, postorder và BFS đa gốc.
- So sánh cấu trúc có thứ tự/không thứ tự bằng chữ ký đệ quy dành cho cây nhỏ.

Mã chủ động kiểm tra việc chuyển cây con xuống hậu duệ để tránh chu trình. Để giữ bất biến, các liên kết nên được chỉnh **thông qua các phương thức của lớp rừng**, không sửa trực tiếp danh sách con hoặc trường parent từ bên ngoài.

~~~python
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    label: str
    children: list[Node] = field(default_factory=list)
    parent: Node | None = field(default=None, repr=False)


class OrderedForest:
    def __init__(self):
        self.roots: list[Node] = []

    def _check_member(self, node: Node) -> None:
        top = node
        while top.parent is not None:
            top = top.parent
        if top not in self.roots:
            raise ValueError("Nút không thuộc rừng này")

    def add_root(self, node: Node) -> None:
        # Giả định node mới chưa được quản lý bởi rừng khác.
        if node.parent is not None or node in self.roots:
            raise ValueError("Nút chưa độc lập hoặc đã là gốc")
        self.roots.append(node)

    def move(self, node: Node, new_parent: Node,
             position: int | None = None) -> None:
        self._check_member(node)
        self._check_member(new_parent)

        if node.parent is new_parent:
            raise ValueError("Đã cùng cha; dùng reorder để đổi vị trí")

        # Cấm gắn node xuống chính nó hoặc hậu duệ của nó.
        cursor = new_parent
        while cursor is not None:
            if cursor is node:
                raise ValueError("Di chuyển này sẽ tạo chu trình")
            cursor = cursor.parent

        size = len(new_parent.children)
        if position is not None and not (0 <= position <= size):
            raise IndexError("Vị trí con không hợp lệ")

        if node.parent is None:
            self.roots.remove(node)
        else:
            node.parent.children.remove(node)

        node.parent = new_parent
        if position is None:
            new_parent.children.append(node)
        else:
            new_parent.children.insert(position, node)

    def detach(self, node: Node) -> bool:
        self._check_member(node)
        if node.parent is None:
            return False  # Đã là gốc độc lập của rừng.

        parent = node.parent
        parent.children.remove(node)
        node.parent = None
        self.roots.append(node)
        return True

    def reorder(self, parent: Node,
                new_children: list[Node]) -> None:
        self._check_member(parent)
        # eq=False giữ so sánh theo danh tính đối tượng.
        if (len(new_children) != len(parent.children)
                or set(new_children) != set(parent.children)):
            raise ValueError("Phải hoán vị đúng các con hiện có")
        parent.children[:] = new_children


def preorder(root: Node):
    yield root.label
    for child in root.children:
        yield from preorder(child)


def postorder(root: Node):
    for child in root.children:
        yield from postorder(child)
    yield root.label


def breadth_first(forest: OrderedForest):
    queue = deque(forest.roots)
    while queue:
        node = queue.popleft()
        yield node.label
        queue.extend(node.children)


def ordered_signature(node: Node):
    """Chữ ký cây có nhãn, có thứ tự con."""
    return (
        node.label,
        tuple(ordered_signature(c) for c in node.children)
    )


def unordered_signature(node: Node):
    """Chữ ký cây có nhãn, bỏ qua thứ tự anh em."""
    child_signatures = [
        unordered_signature(c) for c in node.children
    ]
    return (node.label, tuple(sorted(child_signatures)))


# Tạo 7 nút độc lập (không gộp theo nhãn).
A, B, C, D, E, F, G = [Node(x) for x in "ABCDEFG"]
forest = OrderedForest()
for node in [A, B, C, D, E, F, G]:
    forest.add_root(node)

# Dựng A(B(D,E), C(F)) và cây G độc lập.
forest.move(B, A)
forest.move(C, A)
forest.move(D, B)
forest.move(E, B)
forest.move(F, C)

print([r.label for r in forest.roots])  # ['A', 'G']
print(list(preorder(A)))              # ['A','B','D','E','C','F']
print(list(postorder(A)))             # ['D','E','B','F','C','A']
print(list(breadth_first(forest)))    # ['A','G','B','C','D','E','F']

old_ordered = ordered_signature(A)
old_unordered = unordered_signature(A)

# Đổi thứ tự anh em B và C: thay cây có thứ tự.
forest.reorder(A, [C, B])
assert ordered_signature(A) != old_ordered
assert unordered_signature(A) == old_unordered

# Tách B: từ hai cây thành ba cây.
forest.detach(B)
assert len(forest.roots) == 3

# Ghép B vào dưới G: trở lại hai cây.
forest.move(B, G)
assert B.parent is G
assert len(forest.roots) == 2

# Hệ quản lý từ chối đưa G xuống con B của chính G.
try:
    forest.move(G, B)
except ValueError as exc:
    print("Chặn chu trình:", exc)
~~~

### Phân tích thiết kế trong mã

**Thứ nhất, tên hiển thị khác định danh.** Cờ `eq=False` trong `@dataclass` giúp hai đối tượng `Node("X")` khác nhau không bị coi là cùng một nút chỉ vì có cùng nhãn. Điều này quan trọng khi dùng tập các con hoặc kiểm tra hoán vị bằng `set`.

**Thứ hai, con trỏ cha và danh sách con phải đồng bộ.** Khi `move`, mã xóa liên kết cũ, cập nhật `node.parent` rồi thêm vào `new_parent.children`. Nếu bỏ một trong các bước, dữ liệu có thể không còn là cây.

**Thứ ba, kiểm tra chu trình phải diễn ra trước khi đổi liên kết.** Mã duyệt từ cha mới lên gốc; nếu gặp nút cần chuyển, thao tác bị từ chối mà trạng thái rừng chưa bị thay đổi.

**Thứ tư, việc tách cây con không xóa hậu duệ.** `detach(B)` chỉ ngắt liên kết đến cha của B và thêm B vào danh sách gốc. Các con D và E vẫn nằm dưới B.

**Thứ năm, so sánh có thứ tự khác không thứ tự.** Chữ ký `ordered_signature` giữ nguyên dãy các cây con; chữ ký `unordered_signature` sắp chữ ký các cây con để bỏ qua phép hoán vị anh em.

**Giới hạn ví dụ:** Đây là mô hình tuần tự dành cho cây nhỏ, chưa phải hệ quản lý node đa luồng hoặc API kiểm soát quyền sở hữu giữa nhiều rừng độc lập. Việc tạo chữ ký lồng nhau, sắp xếp chữ ký và dùng đệ quy có thể tốn nhiều bộ nhớ hoặc vượt giới hạn ngăn xếp trên cây cực sâu; không nên mặc định các hàm chữ ký tối ưu cho dữ liệu hàng triệu nút. Trong ứng dụng lớn, có thể dùng ID và thuật toán so sánh cây chuyên dụng, hoặc duyệt lặp với ngăn xếp tường minh.

## 12. Phân tích độ phức tạp thời gian và bộ nhớ

Ký hiệu:

- \(n\): tổng số nút trong một cây hoặc rừng.
- \(c\): số cây thành phần (số gốc).
- \(d\): số con của một nút đang xét.
- \(h\): độ sâu lớn nhất của cây hoặc của thành phần đang duyệt.
- \(w\): số nút lớn nhất cùng nằm trong hàng đợi BFS theo từng mức.

Các độ phức tạp sau giả định **đã có tham chiếu trực tiếp tới nút** khi thao tác, trừ khi nêu khác.

| Thao tác | Độ phức tạp điển hình | Giải thích |
| --- | --- | --- |
| Lấy cha bằng parent pointer | \(O(1)\) | Đọc một tham chiếu |
| Lấy con thứ \(i\) trong mảng con có thứ tự | \(O(1)\) | Truy cập chỉ số trực tiếp |
| Duyệt tất cả \(d\) con trực tiếp | \(O(d)\) | Phải xử lý đủ \(d\) nút |
| Thêm con vào cuối mảng động | \(O(1)\) phân bổ, **chưa tính kiểm tra chu trình** | Có thể phải mở rộng mảng khi hết sức chứa |
| Chèn/xóa một con giữa mảng con | \(O(d)\) | Có thể dịch phần tử hoặc tìm vị trí con |
| Kiểm tra liệu cha mới là hậu duệ bằng chuỗi parent | \(O(h)\) | Duyệt các tổ tiên của cha mới |
| Chuyển một cây con với mã minh họa | \(O(h+d_{\mathrm{old}}+d_{\mathrm{new}}+c)\) trường hợp xấu nhất | Kiểm tra tổ tiên, tìm/xóa trong danh sách con, chèn vị trí và có thể tìm/xóa gốc trong danh sách rừng |
| Duyệt DFS preorder/postorder toàn rừng | \(O(n)\) | Mỗi nút và cạnh được duyệt số lần hằng số |
| Duyệt BFS toàn rừng | \(O(n)\) | Hàng đợi chứa từng nút một lần |
| Tìm nút theo nhãn, không có chỉ mục | \(O(n)\) trường hợp xấu nhất | Thứ tự con không tự tạo chỉ mục tìm kiếm |
| Đếm số cây khi có danh sách gốc | \(O(1)\) | Lấy độ dài danh sách gốc |
| Lưu con trỏ cha và danh sách con | \(O(n)\) | Tổng số cạnh con là \(n-c\); cộng một con trỏ cha mỗi nút |

**Bộ nhớ phụ khi duyệt:** DFS đệ quy cần \(O(h)\) cho call stack nếu xử lý một thành phần tại một thời điểm; BFS theo nhiều gốc đồng thời cần \(O(w)\), tối đa \(O(n)\). Nếu đầu vào là một chuỗi nút rất sâu, DFS đệ quy có nguy cơ vượt giới hạn stack ngay cả khi \(O(n)\) tổng thời gian; duyệt lặp dùng stack tường minh có thể an toàn hơn.

**Không suy ra \(O(\log n)\) từ chữ “có thứ tự”.** Một cây có thứ tự vẫn có thể là một chuỗi dài \(n\) nút hoặc một nút gốc có \(n-1\) con. Chỉ các cấu trúc có **bất biến tìm kiếm và cân bằng phù hợp** mới có thể chứng minh các giới hạn \(O(\log n)\) cho một số thao tác.

### Thứ tự có làm tăng chi phí bộ nhớ không?

Không nhất thiết. Nếu đã dùng danh sách con, ta có thể lưu thứ tự bằng **vị trí trong danh sách** mà không cần một trường `order` riêng. Nếu dùng tập con không thứ tự, có thể có chi phí bảng băm hoặc liên kết nội bộ cao hơn tùy cách triển khai. **Ordered tree và unordered tree mô tả ngữ nghĩa**, còn con trỏ, mảng, set hoặc map là **quyết định biểu diễn**; chi phí phải đo theo triển khai thật.

## 13. Khi nào chọn loại cây hoặc rừng nào?

| Yêu cầu | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Cấu trúc giao diện có thứ tự hiển thị | Cây có thứ tự, danh sách con | Giữ thứ tự phần tử anh em |
| Cú pháp biểu thức cần vị trí toán hạng | Cây có thứ tự hoặc cây nhị phân có trái/phải | Đổi chỗ toán hạng có thể đổi ý nghĩa |
| Phân cấp nhóm mà thứ tự con không quan trọng | Cây không thứ tự, dùng định danh nút rõ ràng | Tránh gán ý nghĩa cho vị trí trình bày |
| Nhiều hệ phân cấp độc lập | Rừng có gốc | Có nhiều gốc, mỗi thành phần là cây |
| Thuật toán chỉ xử lý một gốc | Rừng + gốc giả | Chuyển thành một cây kỹ thuật để tái sử dụng thuật toán |
| Cần truy vấn khóa theo khoảng hoặc tìm theo thứ tự khóa | Cây tìm kiếm phù hợp, chẳng hạn cây cân bằng | Có thêm bất biến thứ tự **theo khóa**, không chỉ theo vị trí anh em |
| Cần kiểm tra một nút có con trực tiếp với ID nhất định | Bổ sung map/set theo ID | Tránh quét tất cả con khi bậc lớn |
| Cần duyệt trước/sau có đầu ra ổn định | Cây có thứ tự hoặc quy tắc sắp con tường minh | Bảo đảm thứ tự xuất kết quả |
| Dữ liệu là đồ thị có chu trình hoặc nhiều cha | Đồ thị tổng quát hoặc DAG | Không ép mô hình vào cây/rừng sai bất biến |

### Ví dụ ứng dụng thực tế

**DOM của một trang web:** Thứ tự các thẻ con có thể ảnh hưởng bố cục và thao tác dựng giao diện. Dùng cấu trúc **có thứ tự** là cần thiết.

**Cấu trúc phòng ban:** Nếu chỉ lưu quan hệ quản lý giữa phòng ban và đơn vị trực thuộc, thứ tự hiển thị giữa các đơn vị có thể không phải dữ liệu cốt lõi. Có thể dùng **cây không thứ tự**, rồi sắp theo tên khi xuất báo cáo.

**Danh sách nhiều dự án riêng biệt:** Mỗi dự án có một gốc và một cấu trúc phân cấp nhiệm vụ. Tập các dự án tạo thành **rừng**. Nếu màn hình cho người dùng kéo thả để sắp xếp các dự án, cần lưu thêm **thứ tự các gốc**.

**Cây cú pháp của chương trình:** Nhiều toán tử và cấu trúc điều khiển có thứ tự thao tác. Biểu diễn bằng cây có thứ tự hoặc cây nhị phân có vai trò trái/phải rõ ràng giúp tránh nhầm thứ tự đối số.

**Tổ chức thư mục:** Các tệp và thư mục con có thể được lưu như các đối tượng trong một cây phân cấp; thứ tự hiển thị có thể được sắp theo tên hoặc thời gian sửa. Không nên giả định **thứ tự hiển thị** là một phần cấu trúc cây nếu hệ tệp không bảo đảm nó.

## 14. Các nhầm lẫn thường gặp

1. **“Cây có thứ tự nghĩa là các khóa được sắp tăng dần như BST.”** Sai. Đây chủ yếu là **thứ tự các nút con**, không phải một điều kiện so sánh khóa giữa các cây con.
2. **“Cây không thứ tự không thể duyệt DFS/BFS.”** Sai. Vẫn duyệt được, chỉ là **dãy kết quả không được xác định duy nhất** nếu chưa chọn quy tắc duyệt các con.
3. **“Đổi chỗ hai nút con là thay đổi một cây không thứ tự.”** Nếu chỉ đổi **vị trí hiển thị** và giữ mọi cạnh/nhãn như cũ, cấu trúc cây không thứ tự không đổi.
4. **“Hai nút có nhãn giống nhau là một nút.”** Sai. Phải phân biệt **định danh đối tượng nút** với **nhãn**; dùng set nhãn có thể làm mất nút hợp lệ.
5. **“Mọi cây có gốc đều là cây nhị phân.”** Sai. Cây tổng quát có thể có nhiều hơn hai con; cây nhị phân có tối đa hai vị trí con trái/phải.
6. **“Chỉ cần mỗi nút có không quá một cha là đủ để có rừng.”** Sai. Các parent pointer có thể vẫn tạo chu trình; cần bảo đảm **không có chu trình** và mỗi thành phần có gốc phù hợp.
7. **“Rừng phải gồm ít nhất hai cây.”** Trong lý thuyết đồ thị, một cây đơn lẻ cũng là rừng; một đồ thị không có cạnh và nhiều đỉnh cô lập cũng là rừng; rừng rỗng cũng hợp lệ.
8. **“Rừng có \(n\) nút luôn có \(n-1\) cạnh.”** Sai khi có nhiều thành phần. Công thức đúng là \(|E|=n-c\) với \(c\) thành phần.
9. **“Tách cây con tức là xóa toàn bộ hậu duệ.”** Sai. Tách chỉ bỏ cạnh với cha cũ và biến gốc cây con thành một gốc mới.
10. **“Có thể nối một nút tới bất kỳ nút nào để tạo cây.”** Sai. Nối một nút xuống hậu duệ của chính nó gây **chu trình**; nhiều cha hoặc chia sẻ nút giữa các cây cũng phá bất biến.
11. **“Thứ tự lặp của hash set luôn ổn định và có thể dùng làm thứ tự anh em.”** Sai. Nếu thứ tự mang ý nghĩa, phải lưu nó một cách rõ ràng hoặc có quy tắc sắp xếp ổn định.
12. **“Có thứ tự thì tìm tên nút chắc chắn \(O(\log n)\).”** Sai. Nếu không có bất biến tìm kiếm và chỉ mục phụ, tìm một nhãn bất kỳ vẫn có thể cần \(O(n)\).
13. **“Cứ thêm gốc giả là có một nút nghiệp vụ thật.”** Sai. Gốc giả chỉ là nút kỹ thuật giúp thuật toán xử lý rừng như một cây; phải xét có nên tính gốc giả vào kết quả hay không.
14. **“Chỉ sửa danh sách con là đủ.”** Nếu có parent pointer, cần cập nhật **cả hai chiều liên kết** và danh sách gốc của rừng khi thích hợp.
15. **“Hai cây có cùng số nút và cùng nhãn thì chắc chắn đẳng cấu.”** Sai. Hình dạng các cây con và quan hệ cha–con cũng phải tương đương.

## 15. Câu hỏi tự kiểm tra kèm lời giải

### Câu 1. Phân biệt thay đổi thứ tự và thay đổi cấu trúc

Hai cây có chung gốc A. Cây thứ nhất có \(\operatorname{children}(A)=[B,C,D]\); cây thứ hai có \(\operatorname{children}(A)=[C,D,B]\). Các nút không có con khác. Hai cây có giống nhau không?

**Lời giải:** Nếu là **cây có thứ tự**, chúng **khác nhau** vì thứ tự anh em thay đổi. Nếu là **cây không thứ tự**, chúng tương đương vì A vẫn có đúng ba con B, C, D; không cạnh nào bị đổi.

### Câu 2. Phân biệt cây có thứ tự và cây tìm kiếm nhị phân

Cây A có ba con theo thứ tự \([90,10,50]\). Có thể gọi đây là cây có thứ tự không? Có tự động là BST không?

**Lời giải:** **Có** thể gọi là cây có thứ tự vì dãy con được xác định rõ. **Không** phải BST theo định nghĩa thông thường: A có **ba con**, còn BST là cây nhị phân với ràng buộc khóa của cây con trái và phải; hơn nữa thứ tự ba nhãn không tạo bất biến tìm kiếm.

### Câu 3. Đếm nút, cạnh và gốc trong rừng

Một rừng có ba cây, lần lượt chứa 5, 3 và 1 nút. Tổng số nút và cạnh bằng bao nhiêu?

**Lời giải:** Tổng số nút là \(n=5+3+1=9\). Có \(c=3\) thành phần nên:

\[
|E|=n-c=9-3=6.
\]

Nếu cả ba thành phần đều có gốc, rừng có **ba gốc**. Cây một nút là một thành phần hợp lệ với 0 cạnh.

### Câu 4. Duyệt cây có thứ tự

Cho cây A có hai con theo thứ tự \([B,C]\); B có hai con \([D,E]\); C có một con \([F]\). Hãy viết preorder và postorder.

**Lời giải:**

- **Preorder:** A, B, D, E, C, F.
- **Postorder:** D, E, B, F, C, A.

Nếu đổi thứ tự hai con của A thành \([C,B]\), preorder thay đổi thành **A, C, F, B, D, E**. Trong cách nhìn cây **không thứ tự**, cả hai dãy đều có thể là một cách duyệt hợp lệ.

### Câu 5. BFS của rừng có nhiều gốc

Rừng có danh sách gốc \([A,G]\), cây A như câu 4 và G là nút độc lập. Nếu BFS được khởi tạo bằng **cả hai gốc đồng thời**, kết quả là gì?

**Lời giải:** **A, G, B, C, D, E, F**. Lý do: hàng đợi ban đầu có A, G ở mức 0. Sau khi xử lý A, B và C được thêm vào cuối hàng đợi; G được xử lý trước B, C.

Nếu thay vào đó duyệt BFS **hết cây A rồi đến cây G**, kết quả là A, B, C, D, E, F, G. Cần thống nhất quy ước duyệt rừng.

### Câu 6. Tách một cây con

Trong rừng câu 5 có hai thành phần. Tách cây con gốc B khỏi A nhưng vẫn giữ B, D, E là một cây độc lập. Hãy cho biết số cây và số cạnh thay đổi thế nào.

**Lời giải:** B trở thành **gốc mới**, rừng có **ba cây**. Số nút không đổi; xóa một cạnh A—B nên số cạnh giảm một. Nếu ban đầu có \(n=7,c=2\), số cạnh là 5. Sau tách, \(n=7,c=3\), số cạnh là 4.

### Câu 7. Chuyển cây con có thể tạo chu trình

Trong một cây có đường A → B → C, người dùng muốn chuyển cây con gốc A xuống làm con của C. Có được phép không? Kiểm tra nhanh thế nào nếu nút có con trỏ cha?

**Lời giải:** **Không.** Vì C là hậu duệ của A, thêm cạnh C—A tạo chu trình. Đi từ **C lên chuỗi cha**, ta gặp B rồi A; nếu gặp chính gốc cây con A, phải từ chối thao tác. Kiểm tra này tốn \(O(h)\) với \(h\) là số bước đi lên.

### Câu 8. Mảng cha có chắc chắn mô tả rừng không?

Với ba nút A, B, C, mảng cha cho biết \(\operatorname{parent}(A)=B\), \(\operatorname{parent}(B)=A\), \(\operatorname{parent}(C)=\text{null}\). Nó có phải một rừng có gốc hợp lệ không?

**Lời giải:** **Không.** A và B trỏ lẫn nhau, tạo chu trình A—B—A theo quan hệ cha. C là một cây một nút, nhưng toàn bộ cấu trúc không phải rừng hợp lệ. Điều kiện mỗi nút có tối đa một con trỏ cha **không loại bỏ chu trình**.

### Câu 9. So sánh cấu trúc với nhãn trùng

Gốc A có hai nút con riêng biệt cùng nhãn X. Có được lưu \(\operatorname{children}(A)\) thành tập chuỗi \(\{"X"\}\) không?

**Lời giải:** **Không**, nếu phải giữ hai nút khác nhau. Tập nhãn chỉ còn một giá trị X và làm mất thông tin số nút. Có thể dùng danh sách hai đối tượng Node("X"), hoặc tập **định danh nút khác nhau**.

### Câu 10. Gốc giả và số cạnh

Một rừng có \(n=12\) nút và \(c=4\) cây. Thêm gốc giả R nối đến bốn gốc cũ. Cây mới có bao nhiêu nút và cạnh?

**Lời giải:** Trước khi thêm, số cạnh là \(12-4=8\). Thêm R và bốn cạnh được \(n'=13\), \(|E'|=8+4=12=n'-1\). Kết quả là một cây có gốc R, với điều kiện các thành phần ban đầu đều là cây.

### Câu 11. Chi phí tìm kiếm không có chỉ mục

Một cây có thứ tự chứa 100.000 nút, nhưng không có BST invariant hoặc map theo ID. Tìm một nhãn không tồn tại có đảm bảo \(O(\log n)\) không?

**Lời giải:** **Không.** Thứ tự anh em không cung cấp quan hệ lớn–nhỏ để loại bỏ toàn bộ nhánh khi tìm theo nhãn. Trong trường hợp xấu nhất phải xét cả 100.000 nút, chi phí \(O(n)\).

### Câu 12. Chọn biểu diễn đúng yêu cầu

Một ứng dụng có các thẻ giao diện kéo thả; thứ tự của các thẻ con quyết định vị trí hiển thị. Ứng dụng khác chỉ cần biết tập nhóm phụ thuộc một dự án, không yêu cầu thứ tự. Nên chọn biểu diễn con nào?

**Lời giải:** Với thẻ giao diện, dùng **danh sách con có thứ tự** và duy trì thứ tự khi kéo thả. Với tập nhóm không có thứ tự ngữ nghĩa, có thể dùng **set/map theo ID** hoặc danh sách chỉ dùng để lưu trữ, nhưng không được phụ thuộc vào thứ tự lặp để quyết định ý nghĩa.

## 16. Ghi nhớ và nguyên tắc lựa chọn

**Cây có thứ tự** là cây có gốc mà **vị trí giữa các nút anh em** mang ý nghĩa; danh sách con thường là cách biểu diễn trực tiếp. **Cây không thứ tự** lưu cùng quan hệ cha–con nhưng **bỏ qua vị trí anh em**, không được gộp nhầm các nút khác nhau chỉ vì có cùng nhãn. Hai loại này đều khác **BST**, nơi khóa được tổ chức theo quy tắc so sánh.

**Rừng** là một đồ thị không hướng không chu trình; mỗi thành phần liên thông là một cây. Khi chọn một gốc cho mỗi thành phần, ta được **rừng có gốc**. Nếu rừng có \(n\) nút và \(c\) thành phần, số cạnh là:

\[
\boxed{|E|=n-c.}
\]

Trong thao tác cập nhật, phải giữ các bất biến: **không chu trình**, **mỗi nút không phải gốc có đúng một cha**, **mọi nút thuộc đúng một thành phần**. Tách cây con làm tăng số thành phần; ghép hai cây bằng một cạnh hợp lệ làm giảm số thành phần; đổi thứ tự anh em chỉ thay đổi ngữ nghĩa **khi bài toán yêu cầu thứ tự**.

Cuối cùng, lựa chọn biểu diễn theo nhu cầu: **danh sách con** cho thứ tự và truy cập theo vị trí, **set/map theo ID** nếu chủ yếu cần tra thành viên trực tiếp, **con trỏ cha** khi thường xuyên truy ngược hoặc di chuyển cây con, **mảng cha** để lưu rừng theo chỉ số, và **gốc giả** khi cần biến nhiều cây thành một cây để dùng lại thuật toán. Duyệt toàn bộ cây/rừng có thời gian \(O(n)\); không có bảo đảm tìm kiếm \(O(\log n)\) chỉ vì cây có thứ tự.
