# Quyền sở hữu cây con và những thay đổi ảnh hưởng nhiều nút

Trong một **cây có gốc**, mỗi nút không chỉ mang giá trị riêng mà còn đứng đầu một **cây con** (*subtree*) chứa toàn bộ hậu duệ của nó. Vì vậy, một thao tác có vẻ rất nhỏ — chẳng hạn chuyển một thư mục sang thư mục khác hoặc thay người quản lý của một phòng ban — có thể làm **hàng nghìn nút đổi vị trí, đường dẫn, quyền thừa kế hoặc metadata**, dù chương trình chỉ thay một cạnh cha–con.

Bài học thuộc chương **Cây cơ bản** của module **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trọng tâm là **quyền sở hữu cây con** theo nghĩa **cấu trúc và vòng đời dữ liệu**, các bất biến khi gắn/tách/chuyển/sao chép/xóa cây con, cùng sự khác biệt giữa **chi phí sửa liên kết** và **chi phí cập nhật mọi nút bị ảnh hưởng**. Ta sẽ phân tích thời gian, bộ nhớ, cách quản lý tham chiếu và một ví dụ Python độc lập.

> **Thông điệp chính:** Đổi cha của một nút có thể chỉ cần sửa vài liên kết, nhưng **toàn bộ cây con di chuyển cùng nút đó**. Nếu mỗi hậu duệ đang lưu một trường phụ thuộc vào vị trí, việc giữ dữ liệu nhất quán có thể cần công việc \(O(k)\), trong đó \(k\) là số nút của cây con.

## 1. Cây con là gì và ai “sở hữu” nó?

Xét cây có gốc:

~~~text
                     A
                   /   \
                  B     C
                /  \   / \
               D    E F   G
                   / \
                  H   I
~~~

Khi xét nút B, **cây con gốc B** gồm:

\[
\operatorname{subtree}(B)=\{B,D,E,H,I\}.
\]

Đó là **B và tất cả các nút có đường đi từ A tới chúng đi qua B**. Nút D và E là con trực tiếp của B, còn H và I là **hậu duệ** (*descendants*) nhưng không phải con trực tiếp của B.

Với nút \(u\), định nghĩa:

\[
\boxed{\operatorname{subtree}(u)
=\{u\}\cup\operatorname{descendants}(u).}
\]

Ký hiệu:

- \(n\): tổng số nút của cả cây hoặc rừng đang quản lý.
- \(k=|\operatorname{subtree}(u)|\): số nút thuộc cây con đang thao tác.
- \(h\): chiều cao hoặc độ dài đường tổ tiên đang xét, đo bằng số cạnh.
- \(d(v)\): số con trực tiếp của nút \(v\).

Trong hình, \(n=9\), còn \(k=5\) đối với cây con B. **Toàn bộ cây** chính là cây con của gốc A, nên \(|\operatorname{subtree}(A)|=n\). Một lá là cây con một nút, nên có \(k=1\).

### Hai ý nghĩa khác nhau của “quyền sở hữu”

Trong bài này cần tách hai nghĩa:

1. **Sở hữu cấu trúc (*structural ownership*):** một đối tượng nút thuộc đúng một cây/rừng đang quản lý và xuất hiện ở **một vị trí duy nhất** trong quan hệ cha–con. Cây con B nằm trọn dưới B; khi B di chuyển, các hậu duệ vẫn là một phần của cây con đó.
2. **Sở hữu nghiệp vụ hoặc quyền truy cập (*business ownership/authorization*):** tài liệu thuộc dự án nào, ai quản lý thư mục, nhóm nào có quyền đọc. Những thông tin này có thể **được kế thừa từ tổ tiên** hoặc được chỉ định tường minh. Chúng **không phải bất biến toán học của mọi cây**.

Một hệ thống có thể chọn **một chủ quản lý của mỗi cây thành phần** (*component owner*), hoặc chọn chính sách quyền riêng cho từng nút. Không được suy luận rằng chuyển nút sang cây khác **tự động cấp quyền đọc** cho mọi người của cây đích nếu ứng dụng chưa định nghĩa và thực hiện quy tắc đó.

## 2. Bất biến cấu trúc của cây và rừng có gốc

Trong **cây có gốc không rỗng**, bất biến quan trọng là:

- Có **đúng một gốc**, và gốc không có cha.
- Mỗi nút khác gốc có **đúng một cha**.
- **Không có chu trình**: không thể đi theo quan hệ con rồi trở lại nút xuất phát.
- Mọi nút đều đạt tới được từ gốc bằng một đường đi duy nhất.
- Nếu lưu cả danh sách con và con trỏ cha, hai chiều liên kết phải **khớp nhau**.

Với \(n\ge1\), số cạnh bằng:

\[
\boxed{|E|=n-1.}
\]

**Rừng có gốc** gồm \(c\) cây tách rời. Nó có \(c\) gốc, mỗi nút thuộc đúng một thành phần, và:

\[
\boxed{|E|=n-c.}
\]

Đối với mô hình **quản lý cây con với sở hữu duy nhất**, mỗi nút còn phải thỏa:

\[
\boxed{\text{mỗi nút xuất hiện đúng một lần trong rừng}.}
\]

Không được đặt **cùng một đối tượng nút** dưới hai cha:

~~~text
Sai với cây sở hữu duy nhất:

       A       B
        \     /
           X
          / \
         Y   Z

X có hai cha A và B; cấu trúc là một đồ thị chia sẻ, không phải rừng.
~~~

Nếu nghiệp vụ thực sự cần **chia sẻ** một đối tượng giữa nhiều cha, có thể phải dùng **đồ thị có hướng không chu trình (DAG)**, quan hệ tham chiếu/shortcut hoặc mô hình dữ liệu khác. Đừng ép việc dùng chung một nút thành “sao chép cây con” khi thực chất chỉ đang tạo thêm **alias**.

### Nút có cùng nhãn chưa chắc là cùng đối tượng

Hai nút đều hiển thị tên “Báo cáo” vẫn có thể là hai đối tượng khác nhau với **ID khác nhau**. Ngược lại, hai biến Python cùng trỏ tới **một đối tượng Node** không tạo ra hai nút chỉ vì có hai tên biến.

Định danh, nhãn và vị trí là ba khái niệm độc lập. Đây là nền tảng để phân biệt **di chuyển**, **sao chép** và **chia sẻ** cây con.

## 3. Một nút di chuyển thì cả cây con di chuyển

Trong hình ban đầu, giả sử ta chuyển B từ dưới A sang làm con của G:

~~~text
Trước:                             Sau:

       A                                  A
     /   \                                |
    B     C                               C
   / \   / \                             / \
  D   E F   G                           F   G
     / \                                     |
    H   I                                    B
                                            / \
                                           D   E
                                              / \
                                             H   I
~~~

Quan hệ nội bộ của cây con B **không đổi**: B vẫn là cha của D và E, E vẫn là cha của H và I. Chỉ **cạnh từ cha cũ tới B** được tháo và **cạnh từ G tới B** được thêm.

Tuy nhiên, đối với cả năm nút B, D, E, H, I:

- Đường đi từ gốc tới chúng **thay đổi**.
- Độ sâu của chúng **tăng** nếu G ở sâu hơn A.
- Các trường lưu sẵn như **đường dẫn đầy đủ**, **gốc sở hữu** hoặc **quyền thừa kế** có thể cần tính lại.

### Bất biến nào giữ nguyên?

Nếu chuyển B tới một cha mới trong **cùng cây** và không tạo chu trình:

- Tổng số nút \(n\) **không đổi**.
- Số cạnh \(n-1\) **không đổi**.
- Kích thước cây con B \(k\) **không đổi**.
- Các quan hệ cha–con **bên trong** cây con B **không đổi**.
- **Gốc của toàn cây** vẫn là A.

Những điều có thể thay đổi gồm **độ sâu**, **chiều cao**, **kích thước cây con của các tổ tiên**, thứ tự anh em, kết quả duyệt và các thuộc tính kế thừa.

**Cần chú ý:** Nếu chỉ “thêm cạnh G—B” mà quên xóa cạnh A—B, B sẽ có **hai cha**. Nếu G nằm dưới B, việc chuyển B thành con G tạo **chu trình**. Cả hai đều phá hỏng bất biến cây.

## 4. Bốn thao tác dễ bị nhầm: di chuyển, tách, sao chép, chia sẻ

| Thao tác | Điều xảy ra với nút gốc \(u\) | Hậu duệ của \(u\) | Số đối tượng nút |
| --- | --- | --- | --- |
| **Move / reparent** | Đổi cha từ \(p\) sang \(q\) | Đi theo \(u\), giữ liên kết nội bộ | Không đổi |
| **Detach / cut** | Bỏ cha cũ, biến \(u\) thành một gốc | Vẫn nằm trong cây con \(u\) | Không đổi |
| **Deep clone / copy subtree** | Tạo **nút mới** tương ứng với \(u\) và các hậu duệ | Mỗi nút được sao chép riêng; cấu trúc tương ứng được giữ | Tăng thêm \(k\) nút |
| **Share / alias** | Thêm một tham chiếu tới **cùng** đối tượng \(u\) | Dữ liệu và mọi sửa đổi đều được chia sẻ | Không tăng nút; có thể không còn là cây |

### Tách B khỏi A

~~~text
Trước:                    Sau:

       A                        A        B
     /   \                      |       / \
    B     C                     C      D   E
   / \                               / \
  D   E                             H   I
     / \
    H   I
~~~

Giả sử ban đầu chỉ có **một cây**. Sau thao tác tách cây con B:

\[
\Delta n=0,\qquad
\Delta |E|=-1,\qquad
\Delta c=+1.
\]

Cây con B trở thành một **cây độc lập trong rừng**, không có nghĩa B và hậu duệ đã bị xóa khỏi bộ nhớ hoặc bị sao chép.

### Sao chép B dưới một cha khác

Nếu muốn **giữ B ở chỗ cũ** đồng thời có **một bản sao độc lập** dưới G, phải tạo các nút mới \(B',D',E',H',I'\). Một bản sao cấu trúc hợp lệ không được để \(B'\) trỏ tới **chính D/E** của cây cũ nếu quy tắc sở hữu yêu cầu mỗi nút chỉ có một cha.

~~~text
Nguồn:     B                 Bản sao:      B'
          / \                             /  \
         D   E                           D'   E'
            / \                              / \
           H   I                            H'  I'
~~~

**Shallow copy** một object chỉ sao chép những trường trực tiếp; nếu trường children vẫn trỏ tới các **nút con cũ**, hai phiên bản có thể chia sẻ cây con ngoài ý muốn. **Deep copy cấu trúc** phải sao chép đủ các đối tượng nút; với payload là đối tượng có thể thay đổi, còn phải quyết định **sao chép payload sâu đến đâu**.

### Tạo nhiều tham chiếu không đồng nghĩa nhân bản

~~~python
# Pseudocode về danh tính:
alias = original_node         # Cùng một đối tượng.
copy_of_node = clone_tree(original_node)  # Các Node mới.
~~~

Alias hợp lệ khi chỉ là **biến tham chiếu bên ngoài cấu trúc cây**; nhưng nếu gắn cùng đối tượng thành con của hai cha, ta đã thay đổi mô hình thành dạng chia sẻ, không còn một rừng sở hữu duy nhất.

## 5. Đổi cha: kiểm tra chu trình trước khi cập nhật

Cho cây:

~~~text
      A
      |
      B
      |
      C
      |
      D
~~~

Yêu cầu “đưa B xuống làm con của D” là **không hợp lệ**, vì D là **hậu duệ** của B. Nếu xóa cạnh A—B rồi thêm cạnh D—B, ta tạo vòng B→C→D→B, không còn gốc hợp lệ cho thành phần đó.

### Điều kiện an toàn

Muốn chuyển cây con gốc \(u\) làm con của \(q\), điều kiện bắt buộc là:

\[
\boxed{q\notin\operatorname{subtree}(u).}
\]

Đồng thời cần kiểm tra \(u\) và \(q\) thực sự thuộc **rừng/không gian quản lý được phép**, các liên kết không bị cạnh tranh cập nhật và vị trí chèn con (nếu cây có thứ tự) hợp lệ.

**Cách 1 — Có parent pointer:** Đi từ \(q\) lần lượt lên cha, nếu gặp \(u\) thì từ chối. Nếu đường dài nhất tới gốc có \(h\) cạnh, kiểm tra tốn \(O(h)\) thời gian và \(O(1)\) bộ nhớ phụ cho biến con trỏ.

**Cách 2 — Không có parent pointer:** Duyệt toàn cây con \(u\), nếu gặp \(q\) thì từ chối. Chi phí tối đa \(O(k)\) thời gian và bộ nhớ phụ tùy phương pháp duyệt.

**Cách 3 — Có nhãn tổ tiên/hậu duệ:** Các cấu trúc như Euler tour có thể dùng chỉ số vào/ra để kiểm tra quan hệ tổ tiên nhanh trong **phiên bản cây không đổi**. Nhưng sau khi di chuyển cây con, các nhãn đó có thể cần cập nhật hoặc xây lại; không được dùng nhãn cũ sau cập nhật rồi cho rằng kết quả còn đúng.

### Thứ tự thực hiện an toàn

~~~mermaid
flowchart TD
    A["Yêu cầu chuyển cây con gốc u tới cha q"] --> B["Kiểm tra u và q thuộc cấu trúc quản lý"]
    B --> C{"q nằm trong cây con u?"}
    C -->|Có| D["Từ chối: sẽ tạo chu trình"]
    C -->|Không| E["Kiểm tra vị trí chèn và điều kiện nghiệp vụ"]
    E --> F["Tháo liên kết từ cha cũ hoặc danh sách gốc"]
    F --> G["Gắn u vào q và cập nhật parent"]
    G --> H["Cập nhật hoặc vô hiệu metadata liên quan"]
~~~

Đây là **trình tự logic** trong chương trình tuần tự. Trong hệ nhiều luồng, không được để phép đọc nhìn thấy trạng thái giữa bước tháo và bước gắn mà không có giao thức đồng bộ/phần tử giao dịch phù hợp.

## 6. Cập nhật một cạnh, nhưng ảnh hưởng những nút nào?

Cần tách hai phạm vi:

- **Nơi phải sửa liên kết vật lý:** thường gồm \(u\), cha cũ và cha mới, cùng danh sách gốc nếu có.
- **Nơi giá trị suy ra có thể thay đổi:** có thể gồm **mọi hậu duệ của \(u\)**, **tổ tiên của cha cũ và cha mới**, hoặc các nút khác nếu hệ thống dùng chỉ số duyệt toàn cục.

Lấy ví dụ chuyển B sang dưới G ở mục 3, với \(k=5\):

| Thông tin | Nút nào có thể bị ảnh hưởng? | Ví dụ |
| --- | --- | --- |
| Parent pointer trực tiếp | **B** | B.parent đổi từ A sang G |
| Danh sách con | **A và G** | A bỏ B, G thêm B |
| Độ sâu cache | **B, D, E, H, I** | Mỗi nút đi theo cây con B đổi độ sâu |
| Đường dẫn từ gốc cache | **B, D, E, H, I** | Tiền tố đường dẫn từ A/B thành A/C/G/B |
| Kích thước cây con cache | **Các tổ tiên liên quan** của cha cũ/cha mới | A và các tổ tiên có thể giảm số hậu duệ; G và các tổ tiên có thể tăng |
| Chiều cao cache | Có thể thay đổi ở **tổ tiên** | Nhánh sâu nhất của A hoặc G có thể đổi |
| Gốc sở hữu cache | **Toàn bộ cây con B nếu chuyển qua cây khác** | Tất cả nút chuyển sang chủ quản lý thành phần mới |
| Quyền kế thừa cache | **Toàn bộ cây con B**, tùy chính sách | Chuyển thư mục sang dự án khác có thể đổi quyền mặc định |
| Thứ tự duyệt hoặc chỉ số DFS toàn cục | Có thể ảnh hưởng **nhiều nút khác** | Di chuyển một nhánh làm đổi vị trí của các nhánh xuất hiện sau nó |

### 6.1. Cập nhật độ sâu của cả cây con

Giả sử \(d_{\mathrm{old}}(u)\) là độ sâu của \(u\) trước chuyển, \(d_{\mathrm{new}}(u)\) là độ sâu sau chuyển. Với mọi \(x\in\operatorname{subtree}(u)\):

\[
\boxed{d_{\mathrm{new}}(x)
=d_{\mathrm{old}}(x)+\Delta,\quad
\Delta=d_{\mathrm{new}}(u)-d_{\mathrm{old}}(u).}
\]

Lý do: đoạn đường **từ \(u\) xuống \(x\)** không thay đổi; chỉ đoạn từ **gốc tới \(u\)** đổi độ dài. Nếu có **độ sâu lưu sẵn trên từng nút**, ta có thể duyệt \(k\) nút và cộng cùng \(\Delta\), tốn \(O(k)\).

Ví dụ:

~~~text
Trước: A(depth=0) → B(depth=1) → E(depth=2) → H(depth=3)

Sau:   A(depth=0) → C(1) → G(2) → B(3) → E(4) → H(5)

Δ = 3 - 1 = +2.
Độ sâu B, E, H đều tăng đúng 2.
~~~

Nếu **không lưu độ sâu**, mà chỉ đi ngược các parent pointer mỗi lần cần biết độ sâu, thao tác chuyển **không phải cập nhật \(k\) số độ sâu**. Đổi lại, **một truy vấn độ sâu** có thể phải đi \(O(h)\) bước.

### 6.2. Cập nhật kích thước cây con của tổ tiên

Đặt \(size(v)=|\operatorname{subtree}(v)|\). Nếu chuyển cây con \(u\) có \(k\) nút:

- Những **tổ tiên chỉ thuộc nhánh cha cũ** mất đi \(k\) nút, nên kích thước cây con của họ giảm \(k\).
- Những **tổ tiên chỉ thuộc nhánh cha mới** nhận thêm \(k\) nút, nên kích thước tăng \(k\).
- Những **tổ tiên chung** của cả hai nhánh vẫn chứa chính \(k\) nút ấy, nên kích thước **không đổi**.
- \(size(u)\) và \(size(x)\) của mọi \(x\) nằm **bên trong** cây con được chuyển **không đổi**.

Do đó, nếu đã cache size ở mỗi nút, không nhất thiết phải duyệt **mọi hậu duệ của \(u\)** để cập nhật size. Chỉ cần cập nhật trên những **đường tổ tiên bị ảnh hưởng**, có thể tốn \(O(h)\) nếu có parent pointer và dữ liệu cache được duy trì đúng.

Ví dụ:

~~~text
       R
      / \
     A   C
    /     \
   B       G
  / \
 D   E

Chuyển B từ A sang G:
  size(B) giữ nguyên = 3
  size(A) giảm 3
  size(G) tăng 3
  size(C) tăng 3
  size(R) giữ nguyên vì vẫn sở hữu cả ba nút B,D,E
~~~

**Không nên giảm rồi tăng size trên mọi tổ tiên chung một cách thiếu kiểm soát** nếu trạng thái trung gian có thể bị đọc. Thuật toán tuần tự có thể tính trước hai nhánh tổ tiên và áp dụng các thay đổi cùng một giao dịch, hoặc dùng cơ chế khóa/phiên bản phù hợp.

### 6.3. Chiều cao cache khác kích thước cache

Chiều cao của một nút có con:

\[
h(v)=1+\max_{c\in children(v)}h(c).
\]

Khi tách một cây con, chiều cao của cha cũ có thể:

- **Giảm** nếu nhánh bị tách là nhánh sâu nhất duy nhất.
- **Không đổi** nếu còn một nhánh khác sâu tương đương.

Khi gắn cây con ở nơi mới, chiều cao của cha mới có thể **tăng**. Việc kiểm tra lại chiều cao các **tổ tiên** có thể cần tính maximum trên các con của từng nút; nếu chỉ dùng danh sách con và không có metadata hỗ trợ, công việc cập nhật chiều cao có thể bao gồm quét nhiều danh sách con, không đơn giản luôn là \(O(h)\).

**Chiều cao nội tại của nút \(u\) và các hậu duệ** vẫn không đổi khi chỉ chuyển cả cây con mà không sửa cấu trúc bên trong.

### 6.4. Đường dẫn và tiền tố kế thừa

Trong cây thư mục, đường dẫn có thể là chuỗi:

~~~text
Trước:
  /projects/alpha/reports
  /projects/alpha/reports/2026
  /projects/alpha/reports/2026/november

Sau khi chuyển reports sang /archive:
  /archive/reports
  /archive/reports/2026
  /archive/reports/2026/november
~~~

Chỉ cần sửa cha của **reports**, nhưng nếu mỗi tệp/thư mục hậu duệ **đang cache đường dẫn tuyệt đối**, ít nhất các bản ghi đó phải được **cập nhật hoặc làm mất hiệu lực cache**.

Một thiết kế khác lưu **tên cục bộ** và con trỏ cha, rồi xây đường dẫn khi cần bằng cách đi lên gốc. Cách này đổi lấy chi phí truy vấn theo chiều sâu đường đi; nó có thể hữu ích khi thao tác chuyển cây con diễn ra thường xuyên.

### 6.5. Quyền truy cập và kế thừa

Nếu chính sách là “quyền mặc định được kế thừa từ thư mục cha gần nhất”, chuyển một thư mục sang nhánh khác có thể đổi kết quả kiểm tra quyền đối với **mọi tài liệu bên trong**.

Không được chỉ thay parent pointer rồi tiếp tục tin các cache quyền cũ. Tùy thiết kế, hệ thống phải **tính lại**, **làm mất hiệu lực cache**, **gắn phiên bản chính sách**, hoặc xử lý chuyển giao theo một giao dịch có kiểm soát. Tài liệu có quyền tường minh có thể là ngoại lệ theo chính sách; không suy đoán rằng mọi quyền đều được kế thừa giống nhau.

**Quan trọng về an toàn:** Nếu thay đổi cây ảnh hưởng quyền truy cập, yêu cầu đọc/ghi phải sử dụng **phiên bản quyền hợp lệ** và không được để cache cũ cấp nhầm quyền. Đây là yêu cầu ứng dụng, không được tự bảo đảm bởi cấu trúc cây.

## 7. Cập nhật ngay hay tính khi truy vấn?

Một bài toán thường có hai lựa chọn:

**Eager update (cập nhật sẵn):** lưu các trường suy ra như depth, root ID, absolute path, effective ACL; khi chuyển cây con, cập nhật tất cả nút bị ảnh hưởng.

**Lazy computation / lazy invalidation (tính khi cần):** chủ yếu lưu parent pointer và thông tin cục bộ; khi truy vấn, đi theo tổ tiên hoặc tính lại từ cache đã bị đánh dấu hết hạn.

| Khía cạnh | Cập nhật sẵn (*eager*) | Tính khi cần (*lazy*) |
| --- | --- | --- |
| Chuyển một cây con \(k\) nút | Có thể phải sửa \(O(k)\) bản ghi hậu duệ | Có thể chỉ sửa liên kết, metadata tổ tiên và phiên bản |
| Đọc độ sâu/đường dẫn | Nhanh nếu cache còn đúng | Có thể đi theo parent pointer \(O(h)\) |
| Bộ nhớ | Tốn thêm trường/cache trên từng nút | Có thể giảm cache, hoặc cần metadata hiệu lực |
| Tính nhất quán | Phải cập nhật đồng bộ cả cây con | Phải kiểm tra và xử lý cache hết hạn đúng cách |
| Nhiều lần đọc, ít lần move | Có thể thuận lợi | Có thể tính lại lặp đi lặp lại |
| Nhiều lần move, ít lần đọc | Có thể quá tốn chi phí cập nhật | Có thể thuận lợi hơn |

Không nên mặc định mọi thuộc tính đều dùng cùng một chính sách. Một hệ thống có thể **cache subtree size**, **không cache depth**, và **tính quyền truy cập bằng truy vấn theo tổ tiên** tùy đặc tính workload.

### Gắn version cho cây hoặc cây con

Một chiến lược đơn giản là duy trì **phiên bản của cấu trúc**. Khi move, tăng phiên bản; khi truy vấn một cache, nếu phiên bản không trùng thì tính lại.

Ưu điểm là cách này tránh bỏ sót cache lỗi thời. Nhược điểm là **một lần di chuyển nhỏ có thể khiến nhiều cache không liên quan phải tính lại** nếu phiên bản quá thô. Phiên bản theo cây con, nhật ký thay đổi hoặc hệ thống chỉ mục động có thể cải thiện, nhưng phức tạp hơn.

### Euler tour và chỉ số vào/ra

Trong một cây có gốc **đang cố định**, một phép DFS có thể gán:

\[
tin(u),\qquad tout(u),
\]

sao cho:

\[
\boxed{u\text{ là tổ tiên của }v
\iff tin(u)\le tin(v)<tout(u)}
\]

khi \(tout\) là **chỉ số kết thúc không bao gồm** của đoạn DFS con \(u\).

Điều này cho phép kiểm tra quan hệ tổ tiên nhanh \(O(1)\) và duyệt cây con như một đoạn chỉ số liên tiếp trong cấu trúc DFS phù hợp.

**Nhưng** sau khi chuyển hoặc đổi thứ tự cây con, **các chỉ số DFS toàn cục của nhiều nút có thể thay đổi**, kể cả nút không nằm trong cây con được chuyển. Nếu cần hỗ trợ nhiều phép cập nhật động, phải xây lại chỉ số hoặc dùng cấu trúc dữ liệu động thích hợp; không dùng các mốc tin/tout cũ để xác nhận tính đúng.

## 8. Cập nhật cấu trúc và vòng đời dữ liệu: xóa không đồng nghĩa giải phóng

Khi người dùng yêu cầu “xóa thư mục”, có ít nhất ba ngữ nghĩa:

1. **Xóa cạnh cha–con:** biến thư mục thành một cây gốc độc lập trong rừng. Đây là **detach**, không phải xóa dữ liệu.
2. **Xóa cây con khỏi mô hình:** loại thư mục cùng mọi hậu duệ khỏi tập nút đang quản lý.
3. **Giải phóng tài nguyên vật lý:** thu hồi bộ nhớ, xóa file, giải phóng bản ghi DB hoặc hủy các tài nguyên bên ngoài. Điều này có thể diễn ra theo cơ chế và thời điểm khác với xóa logic.

Nếu cây con \(u\) có \(k\) nút, **xóa logic toàn cây con** cần xử lý được danh sách các nút bị xóa, thường tốn \(O(k)\) để đi qua chúng nếu có cleanup hoặc bookkeeping cho từng nút.

### Công thức số thành phần sau khi xóa

Trong rừng có \(n\) nút, \(c\) cây, \(|E|=n-c\):

- **Xóa cây con không phải gốc** có \(k\) nút: còn \(n-k\) nút, vẫn \(c\) cây, nên còn \((n-k)-c\) cạnh. Số cạnh bị xóa là **\(k\)**: \(k-1\) cạnh bên trong cây con và một cạnh nối lên cha.
- **Xóa một cây gốc** có \(k\) nút: còn \(n-k\) nút, số thành phần giảm còn \(c-1\), nên số cạnh bị xóa là **\(k-1\)**: chỉ các cạnh bên trong cây đó.

Nếu **tách** cây con mà không xóa các nút, số thành phần lại **tăng một** và số cạnh giảm đúng một.

### Tham chiếu bên ngoài và garbage collection

Trong Python/Java và nhiều môi trường có **garbage collector**, xóa nút khỏi danh sách con **không bảo đảm bộ nhớ được thu hồi ngay**. Nếu biến hoặc cấu trúc khác vẫn giữ tham chiếu tới nút/cây con, đối tượng vẫn có thể sống.

Ngược lại, trong C/C++ với cơ chế sở hữu hoặc cấp phát thủ công, cần thiết kế ai có trách nhiệm hủy cây con, tránh:

- **Double free:** hai nhánh cùng cho rằng mình sở hữu cùng một đối tượng nút.
- **Dangling pointer:** một tham chiếu còn được sử dụng sau khi đối tượng đã bị hủy.
- **Memory leak:** tách mất mọi đường tham chiếu quản lý mà không giải phóng đối tượng.

Các lựa chọn như **unique ownership**, tham chiếu không sở hữu (*borrowed reference*), smart pointer, hoặc vùng nhớ theo arena tùy ngôn ngữ đều cần quy tắc vòng đời rõ ràng.

**Không đồng nhất “có thể đi đến từ gốc” với “chắc chắn tồn tại trong bộ nhớ”.** Sau detach, một cây con có thể không còn nối vào cây ban đầu nhưng vẫn là đối tượng hợp lệ; sau logical delete, tham chiếu cũ có thể còn về mặt ngôn ngữ nhưng không còn được phép thao tác trong rừng đang quản lý.

## 9. Mã Python: quản lý một rừng với sở hữu duy nhất

Mô hình sau dùng **rừng có gốc và có thứ tự**: mỗi nút có danh sách con theo thứ tự và con trỏ cha. Lớp quản lý một tập nút đã đăng ký, đảm bảo mọi nút thuộc **đúng một cây thành phần**. Các thao tác công khai hỗ trợ:

- Tạo gốc và thêm nút con mới.
- Xác định gốc của thành phần hiện tại (*owner root*) bằng cách đi lên parent.
- Chuyển cây con sang cha mới, có kiểm tra chu trình **trước khi sửa liên kết**.
- Tách cây con thành gốc độc lập.
- **Clone toàn bộ cây con** bằng nút mới, không chia sẻ các node.
- Xóa logic toàn bộ cây con, đánh dấu các nút không còn thuộc rừng.
- Kiểm tra lại mọi bất biến của rừng để phục vụ học tập.

Ví dụ chọn nhãn là chuỗi **không thay đổi**, còn danh tính mỗi nút được nhận biết bằng **chính đối tượng Python**. Các trường parent/children không nên sửa trực tiếp từ bên ngoài các phương thức của lớp.

~~~python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(eq=False)
class Node:
    label: str
    parent: Node | None = field(default=None, repr=False)
    children: list[Node] = field(default_factory=list, repr=False)


class OwnedForest:
    def __init__(self):
        self.roots: list[Node] = []
        self._members: set[Node] = set()

    def _require_member(self, node):
        if node not in self._members:
            raise ValueError("Nút không thuộc rừng đang quản lý")

    @staticmethod
    def _check_position(position, length):
        if position is not None:
            if type(position) is not int or not (0 <= position <= length):
                raise IndexError("Vị trí con không hợp lệ")

    def create_root(self, label):
        node = Node(label)
        self._members.add(node)
        self.roots.append(node)
        return node

    def create_child(self, parent, label, position=None):
        self._require_member(parent)
        self._check_position(position, len(parent.children))

        node = Node(label, parent=parent)
        if position is None:
            parent.children.append(node)
        else:
            parent.children.insert(position, node)
        self._members.add(node)
        return node

    def owner_root(self, node):
        """Trả gốc của cây thành phần mà node đang thuộc."""
        self._require_member(node)
        current = node
        while current.parent is not None:
            current = current.parent
        return current

    def subtree_nodes(self, node):
        """Duyệt trước toàn bộ cây con, tính cả node."""
        self._require_member(node)
        result = []
        stack = [node]
        while stack:
            current = stack.pop()
            result.append(current)
            # Đẩy ngược để các con được xử lý theo thứ tự trái→phải.
            stack.extend(reversed(current.children))
        return result

    def path_from_root(self, node):
        """Đường nhãn để minh họa; nhãn có thể không duy nhất."""
        self._require_member(node)
        labels = []
        current = node
        while current is not None:
            labels.append(current.label)
            current = current.parent
        return "/" + "/".join(reversed(labels))

    def move(self, node, new_parent, position=None):
        """Chuyển cả cây con node dưới new_parent trong cùng rừng."""
        self._require_member(node)
        self._require_member(new_parent)

        if node.parent is new_parent:
            raise ValueError("Đã cùng cha: cần thao tác đổi thứ tự riêng")

        # Đi từ cha mới lên gốc: kiểm tra chu trình TRƯỚC khi sửa.
        current = new_parent
        while current is not None:
            if current is node:
                raise ValueError("Cha mới nằm trong cây con được chuyển")
            current = current.parent

        self._check_position(position, len(new_parent.children))

        if node.parent is None:
            self.roots.remove(node)
        else:
            node.parent.children.remove(node)

        node.parent = new_parent
        if position is None:
            new_parent.children.append(node)
        else:
            new_parent.children.insert(position, node)

    def detach(self, node):
        """Tách node thành một gốc mới, giữ nguyên các hậu duệ."""
        self._require_member(node)
        if node.parent is None:
            return False  # Đã là một gốc.

        node.parent.children.remove(node)
        node.parent = None
        self.roots.append(node)
        return True

    def clone_subtree(self, node, new_parent=None, position=None):
        """Sao chép CẤU TRÚC thành các Node độc lập."""
        self._require_member(node)
        if new_parent is not None:
            self._require_member(new_parent)
            self._check_position(position, len(new_parent.children))
        elif position is not None:
            self._check_position(position, len(self.roots))

        clone_root = Node(node.label)
        clones = [clone_root]
        stack = [(node, clone_root)]

        while stack:
            source, target = stack.pop()
            for child in source.children:
                new_child = Node(child.label, parent=target)
                target.children.append(new_child)
                clones.append(new_child)
                stack.append((child, new_child))

        if new_parent is None:
            if position is None:
                self.roots.append(clone_root)
            else:
                self.roots.insert(position, clone_root)
        else:
            clone_root.parent = new_parent
            if position is None:
                new_parent.children.append(clone_root)
            else:
                new_parent.children.insert(position, clone_root)

        self._members.update(clones)
        return clone_root

    def delete_subtree(self, node):
        """Xóa logic cây con, không chỉ tháo một cạnh."""
        self._require_member(node)
        victims = self.subtree_nodes(node)

        if node.parent is None:
            self.roots.remove(node)
        else:
            node.parent.children.remove(node)

        self._members.difference_update(victims)
        for victim in victims:
            # Cắt mọi liên kết để các tham chiếu ngoài không tạo
            # ra một cấu trúc trông như vẫn còn thuộc rừng.
            victim.parent = None
            victim.children.clear()
        return len(victims)

    def validate(self):
        """Kiểm tra duy nhất, đúng parent và mọi node đều đạt từ gốc."""
        if len(set(self.roots)) != len(self.roots):
            raise ValueError("Trùng gốc")

        visited = set()
        stack = [(root, None) for root in self.roots]
        while stack:
            node, expected_parent = stack.pop()
            if node in visited:
                raise ValueError("Nút trùng/chia sẻ hoặc có chu trình")
            if node.parent is not expected_parent:
                raise ValueError("Parent pointer và children không khớp")
            visited.add(node)
            stack.extend((child, node) for child in node.children)

        if visited != self._members:
            raise ValueError("Nút đăng ký nhưng không đạt tới từ gốc")
        return True


forest = OwnedForest()
A = forest.create_root("A")
B = forest.create_child(A, "B")
C = forest.create_child(A, "C")
D = forest.create_child(B, "D")
E = forest.create_child(B, "E")
H = forest.create_child(E, "H")
I = forest.create_child(E, "I")
F = forest.create_child(C, "F")
G = forest.create_child(C, "G")

assert len(forest.subtree_nodes(B)) == 5
assert forest.owner_root(H) is A
assert forest.path_from_root(H) == "/A/B/E/H"
assert forest.validate()

forest.move(B, G)  # Chuyển cả B, D, E, H, I.
assert forest.path_from_root(H) == "/A/C/G/B/E/H"
assert forest.owner_root(H) is A  # Cùng một cây thành phần.
assert forest.validate()

# Không được chuyển C xuống con G của chính C.
try:
    forest.move(C, G)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối thao tác tạo chu trình")

# Clone tạo 5 Node mới, không dùng chung node với nguồn.
copy_B = forest.clone_subtree(B, new_parent=A)
assert len(forest.subtree_nodes(copy_B)) == 5
assert copy_B is not B
assert copy_B.children[0] is not D
assert forest.validate()

# Tách bản sao thành cây độc lập trong rừng.
assert forest.detach(copy_B)
assert forest.owner_root(copy_B) is copy_B
assert len(forest.roots) == 2
assert forest.validate()

# Xóa logic toàn bộ cây bản sao.
assert forest.delete_subtree(copy_B) == 5
assert len(forest.roots) == 1
assert forest.validate()

try:
    forest.owner_root(copy_B)
except ValueError:
    print("Bản sao đã không còn thuộc rừng")
~~~

### Đọc kỹ các bất biến trong mã

1. **eq=False** giữ so sánh theo danh tính đối tượng. Hai nút đều có nhãn "B" vẫn có thể là hai nút riêng. Tập _members vì thế có thể phân biệt các bản sao.
2. **owner_root** được **suy ra từ parent pointer** tại lúc truy vấn. Di chuyển một cây con qua thành phần khác không cần cập nhật trường owner riêng trên mọi hậu duệ; chúng sẽ được suy ra thuộc gốc mới khi truy vấn tiếp.
3. **move** kiểm tra thành viên, chu trình và vị trí chèn trước khi thay liên kết. Với cùng một cha, mã yêu cầu một API **reorder riêng** thay vì diễn giải ngầm move thành đổi vị trí anh em.
4. **detach** giữ nguyên nội bộ cây con và chỉ biến node thành gốc mới; mọi nút vẫn có trong _members.
5. **clone_subtree** tạo một Node mới cho **mỗi nút** của cây con và chép lại quan hệ cha–con. Vì ví dụ chỉ có label kiểu chuỗi, không cần xử lý tài nguyên hay payload có thể thay đổi phức tạp.
6. **delete_subtree** cắt liên kết và loại các đối tượng khỏi tập thành viên. Đây là **xóa logic khỏi cấu trúc quản lý**, không thể ép Python giải phóng đối tượng khi còn biến bên ngoài tham chiếu tới chúng.
7. **validate** duyệt toàn bộ rừng để kiểm tra không có nút lặp, parent pointer khớp children và không còn nút được đăng ký nhưng không đạt từ gốc. Nó là phép kiểm tra **\(O(n)\)**, không nên mặc định gọi sau mọi thao tác trong một hệ thống hiệu năng cao.

**Hạn chế cố ý của mã:** Đây là ví dụ **tuần tự** trong một rừng; không cung cấp khóa đồng bộ, giao dịch cơ sở dữ liệu, hệ thống phân quyền, định danh toàn cục hay chuyển quyền sở hữu giữa **hai đối tượng OwnedForest độc lập**. Nếu thực hiện chuyển dữ liệu giữa hai bộ quản lý, phải đồng thời chuyển đăng ký thành viên, đảm bảo **chỉ một chủ quản lý** và có cơ chế xử lý lỗi giữa chừng. Không chuyển bằng cách sửa trực tiếp trường children rồi chỉ gọi một nửa API.

## 10. Độ phức tạp: chi phí liên kết khác chi phí lan truyền

Với cây/rừng chứa \(n\) nút, thao tác ở cây con \(u\) có \(k\) nút, độ sâu tối đa \(h\) và bậc của cha là \(d\), cần phân biệt **chi phí của cấu trúc dữ liệu** với chi phí nghiệp vụ.

| Thao tác | Chi phí điển hình | Giả thiết và nguyên nhân |
| --- | --- | --- |
| Tìm gốc sở hữu bằng parent pointer | \(O(h)\) thời gian, \(O(1)\) bộ nhớ phụ | Đi lên chuỗi cha tới gốc |
| Duyệt hoặc đếm tất cả nút của một cây con | \(O(k)\) thời gian | Mỗi nút con được xét một lần |
| Kiểm tra cha mới có nằm dưới nút chuyển hay không | \(O(h)\) với parent pointer | Duyệt tổ tiên của cha mới |
| Chỉ đổi liên kết khi đã có tham chiếu và vị trí | Có thể \(O(1)\) | Danh sách liên kết có handle, không có cache cần sửa |
| Move trong lớp Python minh họa | \(O(h+d_{\text{old}}+d_{\text{new}}+c)\) trường hợp xấu nhất | Kiểm tra chu trình, tìm/xóa phần tử trong list, chèn list và có thể tìm gốc trong list |
| Detach trong lớp minh họa | \(O(d_{\text{old}})\) nếu nút chưa là gốc | List.remove tìm vị trí con; append gốc phân bổ \(O(1)\) |
| Cập nhật độ sâu lưu sẵn của toàn cây con | \(O(k)\) | Mỗi nút cộng một giá trị \(\Delta\) |
| Cập nhật subtree size trên các đường tổ tiên | \(O(h)\) khi truy cập/cập nhật mỗi tổ tiên \(O(1)\) | Những tổ tiên chung không đổi giá trị ròng |
| Xây lại cached path của cả cây con | Ít nhất \(O(k)\) lần cập nhật; chi phí byte có thể lớn hơn | Chuỗi đường dẫn có thể dài và cần tạo lại |
| Sao chép cấu trúc cây con | \(O(k)\) thời gian và \(O(k)\) node mới | Mỗi node và cạnh được sao chép |
| Xóa logic cả cây con có cleanup | \(O(k)\) cộng chi phí tháo liên kết | Duyệt và vô hiệu từng node |
| Xác minh toàn bộ rừng | \(O(n)\) thời gian, \(O(n)\) bộ nhớ tập đã thăm | Kiểm tra các liên kết và tập thành viên |
| Truy vấn đường dẫn không cache | \(O(h)\) theo số nút; cộng độ dài các nhãn | Đi ngược các cha, nối chuỗi |
| Rebuild Euler tour cho cả rừng | \(O(n)\) | Đánh chỉ số vào/ra theo một lần DFS |

**Chú ý \(d_{\text{old}},d_{\text{new}}\):** Với danh sách con lưu bằng mảng động, việc tìm và xóa một con hoặc chèn vào giữa có thể cần \(O(d)\). Nếu dùng danh sách liên kết đã giữ handle của vị trí phần tử, phần cập nhật liên kết có thể gần \(O(1)\), nhưng việc kiểm tra chu trình, cache và giao dịch vẫn là các công việc riêng.

### “Move \(O(1)\)” có thể vừa đúng vừa gây hiểu lầm

Giả sử ta có sẵn con trỏ tới cây con B, cha cũ và cha mới; cấu trúc giữ các liên kết thuận tiện. Việc đổi hai cạnh **có thể thực hiện trong thời gian hằng số**.

Tuy nhiên, nếu mỗi nút trong B đang lưu độ sâu hoặc chủ sở hữu **tính sẵn**, phải sửa đủ \(k\) bản ghi. Cùng một thao tác nghiệp vụ có thể có:

\[
\boxed{T_{\mathrm{move}}
=T_{\mathrm{validate}}
+T_{\mathrm{relink}}
+T_{\mathrm{metadata}}
+T_{\mathrm{persistence}}.}
\]

Với ví dụ quản lý quyền trong cơ sở dữ liệu, phần ghi bản ghi, cập nhật chỉ mục, log giao dịch hoặc đồng bộ nhiều máy còn có thể tốn hơn phần đổi liên kết trong RAM.

### Biểu diễn cũng làm thay đổi chi phí

- **Parent pointer + children list:** dễ đi lên kiểm tra chu trình; remove/insert trong mảng con có thể \(O(d)\).
- **First-child / next-sibling:** biểu diễn được thứ tự anh em; nếu đã có con trỏ predecessor, tháo/gắn nhanh, nếu chưa có thì có thể phải duyệt anh em.
- **Parent array:** lấy cha \(O(1)\), nhưng tìm tất cả con có thể cần quét \(O(n)\) nếu không có chỉ mục ngược.
- **Mảng theo vị trí heap:** thích hợp cây complete, nhưng di chuyển một cây con tùy ý có thể làm **rất nhiều chỉ số thay đổi** hoặc tạo khoảng trống; không tự có thao tác move \(O(1)\).
- **Cây cân bằng với metadata:** thay đổi cấu trúc còn phải khôi phục bất biến cân bằng của loại cây đó. Các phép quay cây không thể được xem như move tùy ý trong một cây tổng quát.

## 11. Đồng thời và tính nguyên tử khi chuyển cây con

Trong chương trình tuần tự, các bước tháo/gắn liên kết diễn ra theo thứ tự rõ ràng. Trong hệ nhiều luồng hoặc nhiều dịch vụ, một phép đọc có thể xen vào giữa hai bước nếu không được đồng bộ.

Ví dụ:

~~~text
Luồng ghi:       1. Xóa B khỏi A.children
                 2. Đặt B.parent = G
                 3. Thêm B vào G.children

Luồng đọc:       Xem cây sau bước 1 nhưng trước bước 3?
                 B có thể tạm không đạt tới từ gốc.
~~~

Một thiết kế sản xuất phải xác định **điểm tuyến tính hóa** (*linearization point*) hoặc giao thức nhất quán tương đương cho cập nhật cấu trúc, ví dụ:

- Khóa vùng cấu trúc đủ lớn để phép đọc không thấy trạng thái nửa cũ nửa mới.
- Dựng phiên bản cây mới hoặc dùng cơ chế copy-on-write rồi chuyển tham chiếu gốc khi đã hoàn chỉnh.
- Giao dịch cơ sở dữ liệu để cập nhật quan hệ cha–con và những metadata bắt buộc một cách nguyên tử.
- Phiên bản cấu trúc và retry đối với các truy vấn đang đọc một phiên bản đã cũ.

**Không có cơ chế nào trong số này tự động miễn phí.** Khóa quá rộng có thể làm giảm song song; copy-on-write có thể tăng RAM; giao dịch ghi hàng nghìn hậu duệ có thể tạo nhiều I/O. Phải thiết kế theo mức đảm bảo đọc/ghi của sản phẩm.

### Quyền sở hữu và giao dịch qua hai hệ quản lý

Nếu cây con B được **chuyển từ rừng X sang rừng Y**:

1. Kiểm tra B thuộc X và đích thuộc Y.
2. Xác định danh sách \(k\) nút cần thay đổi đăng ký chủ quản lý nếu hệ thống lưu owner ID trực tiếp.
3. Thực hiện tháo/gắn liên kết và chuyển thành viên sao cho không có **hai chủ cùng có quyền sửa độc lập** trên cùng một Node.
4. Di chuyển quyền, chỉ mục, bản ghi phụ và tài nguyên liên quan theo chính sách.
5. Xử lý lỗi giữa chừng bằng rollback hoặc giao thức chuyển giao có trạng thái.

Trong cơ sở dữ liệu, thao tác này có thể cần log và transaction; trong nhiều máy, có thể cần quy trình chuyển giao nhiều bước. **Việc đặt lại một con trỏ trong bộ nhớ không bảo đảm chuyển quyền sở hữu nghiệp vụ thành công**.

## 12. Bốn ví dụ ứng dụng

### 12.1. Thư mục và file

Thư mục **reports** có 500 file và thư mục con. Khi chuyển reports từ /team-a sang /team-b, hệ thống có thể chỉ cập nhật **parent ID** của reports. Nhưng nếu mỗi file lưu **full path**, hệ thống có thể phải cập nhật hoặc làm mất hiệu lực cache của toàn bộ 501 nút (tính cả reports).

Nếu quyền file thừa kế từ thư mục cha, thay đổi parent còn có thể yêu cầu **kiểm tra lại quyền** trước khi phục vụ truy cập. Cách tổ chức cache, chỉ mục full-text và transaction sẽ quyết định chi phí vận hành.

### 12.2. Cây tổ chức nhân sự

Nhóm B có 100 thành viên và được chuyển sang dưới quản lý của nhóm C. Những quan hệ **bên trong B** có thể không đổi, nhưng:

- Độ sâu cấp quản lý của nhân sự trong B có thể đổi.
- Các báo cáo “tổng nhân sự cấp dưới” ở những cấp quản lý cũ và mới cần cập nhật.
- Nếu quyền phê duyệt dựa trên người quản lý cấp trên, điều kiện truy cập của cả nhóm có thể đổi.

Cập nhật số nhân sự **trên đường tổ tiên** có thể chỉ tốn \(O(h)\); cập nhật quyền trực tiếp cho **toàn bộ người trong nhóm** có thể tốn \(O(k)\).

### 12.3. Cây cú pháp của chương trình

Khi công cụ biên dịch thay một biểu thức bằng một cây con mới, các nút mới không thể vô tình **dùng lại các node thuộc hai cha** trong AST có sở hữu duy nhất. Nếu một node xuất hiện ở nhiều vị trí, trình duyệt hoặc bộ biến đổi có thể xử lý cùng đối tượng nhiều lần, làm thay đổi dữ liệu ngoài ý muốn.

Một phép **clone cây con** giữ cấu trúc nhưng tạo node mới, phù hợp với những phép biến đổi cần tính độc lập. Các trình biên dịch dùng **DAG chia sẻ biểu thức** có thể cho phép nhiều tham chiếu đến cùng node, nhưng đó là một mô hình khác và cần thuật toán xử lý chia sẻ rõ ràng.

### 12.4. Cây thành phần giao diện

Di chuyển một thành phần UI sang container khác có thể làm thay đổi:

- Vị trí hiển thị và thứ tự anh em.
- Ngữ cảnh thuộc tính được cung cấp từ tổ tiên.
- Tọa độ tương đối, kích thước và quá trình layout.
- Vòng đời hoặc trạng thái của thành phần tùy framework.

Chi phí thực tế có thể ảnh hưởng cả các anh em đang cùng chia sẻ layout, không chỉ các nút nằm trong cây con vừa di chuyển. Do đó, **số nút trong cây con không luôn là cận trên cho số đối tượng bị tính lại trong toàn ứng dụng**.

## 13. Chọn cách tổ chức dữ liệu theo workload

| Workload chính | Gợi ý biểu diễn / chiến lược | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Thường xuyên di chuyển cây con lớn | Parent pointer, dữ liệu theo quan hệ; hạn chế cache phụ thuộc tổ tiên | Truy vấn depth/path có thể phải đi \(O(h)\) |
| Rất nhiều truy vấn đường dẫn, hiếm khi move | Cache path/depth, có cơ chế vô hiệu hoặc cập nhật khi move | Chi phí \(O(k)\) trong thao tác move |
| Thường hỏi size của một cây con | Cache subtree size, cập nhật trên đường tổ tiên | Phải xử lý đúng nhánh tổ tiên chung |
| Thường truy vấn tổ tiên trong cây gần như tĩnh | Euler tour, tin/tout hoặc chỉ mục DFS | Nhãn lỗi thời khi cây thay đổi |
| Thường sao chép cây biểu thức | Clone node theo cây con, dùng ID mới | Shallow copy gây chia sẻ con vô tình |
| Quản lý quyền thừa kế | Chính sách rõ ràng và cache có phiên bản | Nguy cơ áp dụng quyền cũ sau move |
| Xóa nhiều cây con | Truyền đạt rõ delete vs detach; cleanup theo node | Rò rỉ tài nguyên, tham chiếu cũ |
| Dữ liệu có nhiều cha thực sự | Mô hình DAG/đồ thị và sở hữu riêng | Không dùng thuật toán chỉ đúng với cây |

Lựa chọn tốt có thể là **kết hợp nhiều cấu trúc**: parent pointer để đi lên, danh sách con để duyệt xuống, hashmap theo ID để tìm nút nhanh, và metadata có phiên bản cho các phép tổng hợp quan trọng.

## 14. Sai lầm thường gặp

1. **“Đổi cha chỉ ảnh hưởng một nút.”** Sai nếu các nút hậu duệ lưu độ sâu, đường dẫn, gốc sở hữu hoặc quyền kế thừa.
2. **“Di chuyển cả cây con luôn phải đi qua mọi hậu duệ.”** Không nhất thiết. Nếu chỉ lưu parent pointer và children, việc đổi liên kết có thể rất rẻ; chi phí \(O(k)\) phát sinh khi cần cập nhật hoặc xử lý dữ liệu của \(k\) nút.
3. **“Một nút có thể có hai cha mà vẫn là cây.”** Sai với cây có gốc thông thường và bất biến sở hữu duy nhất; cấu trúc chia sẻ có thể là DAG/đồ thị.
4. **“Chỉ cần so sánh nhãn để nhận biết nút.”** Sai. Hai nút nhãn giống nhau có thể có ID khác nhau, và hai biến có thể cùng trỏ tới một Node.
5. **“Detach cũng là delete.”** Detach chỉ ngắt một cạnh và biến cây con thành một cây độc lập; delete loại đối tượng khỏi cấu trúc quản lý.
6. **“Shallow copy là đã nhân bản toàn cây con.”** Sai. Tham chiếu tới children có thể vẫn trỏ về các node nguồn.
7. **“Xóa tham chiếu trong danh sách con chắc chắn giải phóng bộ nhớ.”** Sai trong môi trường có GC nếu còn tham chiếu khác; với quản lý bộ nhớ thủ công, cần quy tắc hủy rõ ràng.
8. **“Có thể gắn cây con dưới một hậu duệ của chính nó.”** Sai: thao tác tạo chu trình.
9. **“Chỉ sửa parent pointer là đủ khi có children list.”** Sai: hai chiều liên kết sẽ không khớp, gây lỗi khi duyệt và kiểm tra.
10. **“Kích thước cây con của tất cả tổ tiên đều tăng hoặc giảm.”** Sai: với move trong cùng cây, các tổ tiên chung có thay đổi ròng bằng 0.
11. **“Chiều cao của cây con đổi khi chuyển nó nguyên vẹn.”** Chiều cao **nội tại** của cây con không đổi; độ sâu từ gốc toàn cây và chiều cao các tổ tiên có thể đổi.
12. **“Độ sâu của từng hậu duệ thay đổi một lượng khác nhau.”** Nếu chỉ đổi vị trí cả cây con và giữ cấu trúc nội bộ, tất cả hậu duệ thay đổi độ sâu cùng một \(\Delta\).
13. **“Thay đổi một nhánh chỉ làm sai Euler index của nhánh đó.”** Một phép thay đổi thứ tự/di chuyển có thể đổi thứ tự DFS của **nhiều nút khác**.
14. **“Giá trị owner có cache không cần làm mới sau move.”** Nếu chuyển qua cây khác, cache gốc/owner cũ có thể sai đối với toàn cây con.
15. **“Move cấu trúc tự động cập nhật quyền truy cập.”** Quyền nghiệp vụ cần quy tắc và cơ chế cập nhật/kiểm tra riêng.
16. **“Có thể kiểm tra chu trình sau khi gắn.”** Khi kiểm tra quá muộn, thao tác có thể đã phá bất biến và việc phục hồi trở nên khó khăn.
17. **“Code tuần tự đúng thì đa luồng cũng đúng.”** Khi đọc xen giữa tháo/gắn, một nút có thể tạm mất đường đi từ gốc hoặc xuất hiện tại hai vị trí.
18. **“Cập nhật sẵn luôn tốt hơn tính khi cần.”** Eager tốt cho nhiều lần đọc nhưng move có thể tốn \(O(k)\); lazy đổi chi phí cập nhật lấy truy vấn \(O(h)\).
19. **“Đếm nút bị ảnh hưởng bằng đúng \(k\) trong mọi ứng dụng.”** Metadata tổ tiên, thứ tự DFS của các nhánh khác hoặc layout UI có thể liên quan tới nhiều nút ngoài cây con.
20. **“Move trong một cây và move qua hai cây có cùng ảnh hưởng.”** Chuyển giữa các cây có thể thay đổi gốc sở hữu của \(k\) nút và số thành phần; chuyển trong cùng cây thường không đổi số thành phần.

## 15. Ví dụ có số liệu: một lần chuyển làm thay đổi gì?

Xét rừng có hai cây A và X:

~~~text
    Cây 1:                   Cây 2:

       A                         X
      / \                       / \
     B   C                     Y   Z
    / \   \
   D   E   F
      / \
     H   I
~~~

Cây A có 8 nút: A, B, C, D, E, F, H, I. Cây X có 3 nút: X, Y, Z. Tổng rừng:

\[
n=11,\quad c=2,\quad |E|=n-c=9.
\]

Cây con B chứa:

\[
\operatorname{subtree}(B)=\{B,D,E,H,I\},
\qquad k=5.
\]

### Bước 1 — Tách B thành cây độc lập

Xóa cạnh A—B, giữ nguyên năm nút B, D, E, H, I:

\[
n'=11,\quad c'=3,\quad |E'|=8.
\]

Rừng lúc này có ba gốc A, X, B. Gốc B có chiều cao nội tại là 2 cạnh vì đường B→E→H dài 2 cạnh.

### Bước 2 — Gắn B làm con của Y

Gắn B dưới Y, là nút thuộc cây X:

~~~text
      A                    X
      |                   / \
      C                  Y   Z
      |                  |
      F                  B
                        / \
                       D   E
                          / \
                         H   I
~~~

Trở lại \(c=2\), \(n=11\), \(|E|=9\), nhưng **chủ cây thành phần của B, D, E, H, I** đã đổi từ A sang X.

Độ sâu trước chuyển (tính từ A):

| Nút | B | D | E | H | I |
| --- | ---: | ---: | ---: | ---: | ---: |
| Độ sâu cũ | 1 | 2 | 2 | 3 | 3 |

Độ sâu sau chuyển (tính từ X):

| Nút | B | D | E | H | I |
| --- | ---: | ---: | ---: | ---: | ---: |
| Độ sâu mới | 2 | 3 | 3 | 4 | 4 |

Tất cả độ sâu tăng **\(\Delta=+1\)**. Nếu mỗi nút cache depth, năm bản ghi cần sửa. Nếu truy gốc bằng parent pointer, một truy vấn tới H đi qua H→E→B→Y→X và tính được gốc mới mà không cần ghi lại năm trường owner.

### Bước 3 — Những kích thước cây con nào đổi?

Trước khi tách, \(size(B)=5\), \(size(A)=8\), \(size(X)=3\), \(size(Y)=1\). Sau khi B sang dưới Y:

\[
size(B)=5,\quad size(A)=3,\quad
size(X)=8,\quad size(Y)=6.
\]

Năm nút B, D, E, H, I **không đổi quan hệ nội bộ**, nên kích thước cây con riêng của chúng không đổi. Các thay đổi size chủ yếu ở **tổ tiên cũ và mới**.

### Bước 4 — Nếu thay move bằng clone thì sao?

Nếu giữ nguyên cây con B dưới A và **clone** một bản sao \(B'\) gồm 5 nút dưới Y:

\[
n'=11+5=16,\qquad c'=2,\qquad
|E'|=n'-c'=14.
\]

Tổng tăng 5 nút và 5 cạnh: bốn cạnh nội bộ trong bản sao cùng một cạnh nối bản sao với Y. Nút B và B' **khác danh tính**; sửa nhãn D' trong bản sao **không được làm đổi** nhãn D ở cây nguồn.

Đây là cách kiểm tra nhanh tính đúng của ý nghĩa **move vs clone**: move giữ \(n\) không đổi, còn clone thêm \(k\) nút.

## 16. Câu hỏi tự kiểm tra có lời giải

### Câu 1. Xác định kích thước cây con

Trong cây A có các cạnh A—B, A—C, B—D, B—E, E—H, E—I, C—F, C—G, cây con B có bao nhiêu nút? H và I có phải con trực tiếp của B không?

**Lời giải:** Cây con B gồm **B, D, E, H, I**, nên \(k=5\). H và I là **hậu duệ** của B nhưng là con trực tiếp của **E**, không phải B.

### Câu 2. Di chuyển trong cùng cây

Trong cây câu 1, chuyển B thành con của G. Tổng \(n\), số cạnh và số cây thành phần thay đổi ra sao?

**Lời giải:** Nếu G nằm ngoài cây con B thì thao tác hợp lệ. Ta xóa A—B rồi thêm G—B, nên **\(n\), \(|E|\) và số thành phần \(c\) đều giữ nguyên**. Toàn bộ B, D, E, H, I đi theo B.

### Câu 3. Tách cây con

Một cây có 20 nút và 19 cạnh. Tách một cây con không phải gốc có 7 nút để nó trở thành một thành phần độc lập trong rừng. Có bao nhiêu nút, cạnh và thành phần sau thao tác?

**Lời giải:** Không xóa nút nào, nên \(n=20\). Bỏ đúng một cạnh nối cây con với cha cũ, nên \(|E|=18\). Từ một cây thành **hai cây**, \(c=2\). Kiểm tra \(n-c=20-2=18\).

### Câu 4. Xóa hẳn cây con

Tiếp theo câu 3, xóa toàn bộ cây con độc lập có 7 nút khỏi rừng. Rừng còn bao nhiêu nút, cạnh và thành phần?

**Lời giải:** Xóa một thành phần gốc 7 nút, có \(7-1=6\) cạnh nội bộ. Còn \(n=13\), \(|E|=18-6=12\), \(c=1\). Đúng theo \(n-c=13-1=12\).

### Câu 5. Vì sao không thể thêm một cạnh thứ hai vào cùng node?

Nút X đã là con của A. Nếu gắn **cùng đối tượng X** vào danh sách con của B mà không tháo khỏi A thì vi phạm điều gì?

**Lời giải:** X xuất hiện dưới **hai cha** A và B, vi phạm bất biến mỗi nút không phải gốc có **đúng một cha** và mỗi đối tượng node thuộc đúng một vị trí cấu trúc. Nếu cần một bản sao độc lập, phải **clone** cây con X với các node mới.

### Câu 6. Kiểm tra chu trình

Có đường A→B→C→D. Có thể chuyển B xuống làm con của D không? Nếu có parent pointer, kiểm tra thế nào?

**Lời giải:** **Không.** D là hậu duệ của B. Đi ngược từ D tới cha D→C→B, ta gặp chính B, nên phải **từ chối trước khi sửa liên kết**.

### Câu 7. Tính thay đổi độ sâu

Một cây con gốc U có độ sâu cũ 2. Sau khi chuyển, U có độ sâu mới 5. Một hậu duệ W của U trước đó có độ sâu 8. Độ sâu mới của W là bao nhiêu?

**Lời giải:** \(\Delta=5-2=3\). Vì cấu trúc bên trong U không đổi, \(d_{\mathrm{new}}(W)=8+3=\mathbf{11}\).

### Câu 8. Cập nhật size khi đổi cha

Cây R có hai nhánh A và C. B là cây con 5 nút dưới A; ta chuyển B sang G thuộc nhánh C. Kích thước cây con của R, A, C, G, B sẽ biến đổi thế nào?

**Lời giải:** R là **tổ tiên chung** trước và sau chuyển, nên \(size(R)\) **không đổi**. \(size(A)\) **giảm 5**, \(size(C)\) và \(size(G)\) **tăng 5**, còn \(size(B)\) **không đổi**.

### Câu 9. Vì sao chiều cao khác kích thước?

Một cha P có hai cây con cao lần lượt 4 và 4. Xóa một trong hai cây con khỏi P; chiều cao P có chắc giảm không?

**Lời giải:** **Không.** Sau khi bỏ một nhánh cao 4, nhánh còn lại vẫn cao 4 nên chiều cao P vẫn là \(1+4=5\). Trong khi đó, kích thước cây con P **chắc chắn giảm** đúng số nút của nhánh bị loại.

### Câu 10. Chọn eager hay lazy

Một công cụ quản lý cấu trúc thường xuyên di chuyển cây con hàng nghìn nút nhưng rất ít khi truy vấn đường dẫn đầy đủ. Có nên lưu đường dẫn tuyệt đối ở từng nút và cập nhật ngay mỗi lần move không?

**Lời giải:** Thường **không phải lựa chọn đầu tiên**. Có thể chỉ lưu tên cục bộ và parent pointer, rồi xây đường dẫn khi cần với chi phí \(O(h)\); điều này tránh cập nhật đường dẫn của \(k\) nút mỗi lần move. Nếu truy vấn đường dẫn quá thường xuyên, có thể cân nhắc cache kèm cơ chế invalidation.

### Câu 11. Tính chất của sao chép

Một cây con có 9 nút. Clone cấu trúc đầy đủ rồi gắn bản sao dưới một nút khác trong cùng rừng. Tổng số node tăng bao nhiêu? Nếu chỉ tạo alias tới root cũ thì sao?

**Lời giải:** Clone thật tăng **9 node**, vì mỗi node được tạo mới. Alias tới root cũ **không tăng số node**; nếu dùng alias làm cạnh cha mới khi root cũ vẫn còn cha, mô hình sở hữu duy nhất bị vi phạm.

### Câu 12. Xóa logic và thu hồi bộ nhớ

Trong Python, sau khi xóa một cây con khỏi Forest, chương trình vẫn giữ biến external trỏ tới một node đã bị xóa. Có thể khẳng định đối tượng đó đã được giải phóng RAM không?

**Lời giải:** **Không.** Tham chiếu external vẫn tồn tại, nên đối tượng có thể còn sống trong bộ nhớ. Lớp quản lý có thể từ chối thao tác trên node vì nó không còn thuộc rừng, nhưng thu hồi bộ nhớ là cơ chế khác.

### Câu 13. Metadata tổ tiên và hậu duệ

Một thao tác move một cây con 1000 nút chỉ đổi hai cạnh. Vì sao việc cập nhật size cache có thể chỉ gần \(O(h)\), nhưng cập nhật depth cache lại cần \(O(1000)\)?

**Lời giải:** Size của **từng node trong cây con** không đổi; chỉ kích thước các tổ tiên cũ và mới bị ảnh hưởng, nên có thể cập nhật trên các đường tổ tiên. Độ sâu của **mọi nút trong cây con** đổi theo cùng \(\Delta\), nên nếu depth được lưu tường minh trên từng node thì cần cập nhật đủ 1000 node.

### Câu 14. Euler tour sau khi move

Một chỉ mục ghi tin/tout từ DFS của cây, sau đó chuyển một cây con sang nhánh khác. Có thể dùng nguyên tin/tout cũ để trả lời quan hệ tổ tiên không?

**Lời giải:** **Không** trừ khi hệ thống có cơ chế cập nhật chỉ mục động bảo đảm tính đúng. Các nhãn DFS cũ phản ánh cấu trúc và thứ tự duyệt trước move; cần xây lại hoặc cập nhật bằng cấu trúc chuyên dụng.

### Câu 15. Quyền kế thừa

Thư mục B được chuyển từ dự án A sang dự án C. Nếu quyền đọc tài liệu bên trong B được **kế thừa từ dự án cha**, điều gì phải được kiểm tra trước khi cho người dùng truy cập?

**Lời giải:** Phải xác định **chính sách quyền mới** và bảo đảm quá trình tính/kiểm tra quyền sử dụng thông tin đã cập nhật, không dùng cache thừa kế từ A một cách mù quáng. Cần xử lý các ngoại lệ quyền tường minh và phiên bản cập nhật nếu ứng dụng quy định.

### Câu 16. Chi phí thật của một thao tác move

Một API báo thời gian đổi parent pointer chỉ vài thao tác \(O(1)\), nhưng tổng thời gian move rất lớn khi chuyển thư mục chứa 50.000 bản ghi. Giải thích vì sao hai quan sát này không mâu thuẫn.

**Lời giải:** Chi phí đổi liên kết là **một thành phần**. API có thể còn kiểm tra chu trình, cập nhật 50.000 đường dẫn hoặc quyền cache, ghi database, chỉ mục, log và đồng bộ. Tổng thời gian có thể là \(O(k)\) theo số hậu duệ dù phần relink nhỏ.

## 17. Tổng kết

Trong một **cây có gốc**, cây con của \(u\) gồm \(u\) và tất cả hậu duệ. Với mô hình **sở hữu duy nhất**, mỗi nút thuộc đúng một vị trí trong một cây thành phần; không được gắn **cùng một Node** dưới hai cha. **Move** đổi cha nhưng giữ nguyên node; **detach** biến cây con thành một gốc độc lập; **clone** tạo đủ các node mới; **delete subtree** loại cả cây con khỏi cấu trúc quản lý.

**Bất biến trọng tâm:** không chu trình, mỗi nút không phải gốc có đúng một cha, các liên kết parent–children nhất quán, và mọi node được quản lý đạt tới từ đúng một gốc.

Khi chuyển cây con có \(k\) nút, hãy tách:

- **Đổi liên kết:** có thể nhỏ, thậm chí \(O(1)\) nếu có các handle phù hợp.
- **Kiểm tra chu trình:** thường \(O(h)\) khi có parent pointer.
- **Cập nhật metadata tổ tiên:** như subtree size, có thể theo đường tổ tiên \(O(h)\).
- **Cập nhật metadata hậu duệ:** như depth/path/owner cache, có thể \(O(k)\).
- **Sao chép hoặc xóa cả cây con:** cần xử lý \(O(k)\) node.

Khi xây hệ thống thực, hãy quyết định rõ **quyền sở hữu nút**, **quy tắc kế thừa dữ liệu**, **thời điểm cập nhật cache**, **vòng đời của đối tượng** và **cơ chế đồng bộ**. Một phép sửa cạnh đúng về hình học chưa chắc đã đúng về dữ liệu hoặc quyền truy cập; sự lựa chọn tốt là duy trì đầy đủ bất biến với chi phí phù hợp workload.
