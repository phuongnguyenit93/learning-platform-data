# Khai thác trường hợp đặc biệt để có lời giải hiệu quả

## 1. Một bài toán khó nói chung vẫn có thể dễ trên một lớp đầu vào

Trong **lý thuyết độ khó bài toán** và thiết kế thuật toán, một bài toán có thể rất khó ở **trường hợp tổng quát**, nhưng giải nhanh trên những đầu vào có cấu trúc đặc biệt. Việc nhận ra và chứng minh cấu trúc ấy thường quan trọng không kém việc nghĩ ra thuật toán.

Ví dụ tiêu biểu:

- **Minimum Vertex Cover** (phủ đỉnh nhỏ nhất) trên đồ thị vô hướng tổng quát là bài toán tối ưu **NP-hard**; nhưng trên **cây**, có quy hoạch động giải chính xác trong **O(n)**.
- **3-SAT** là NP-complete, nhưng **2-SAT** giải được trong **O(n+m)** bằng đồ thị kéo theo và thành phần liên thông mạnh, với n biến và m mệnh đề.
- **Đường đi đơn dài nhất** trên đồ thị tổng quát là bài toán khó; trên **đồ thị có hướng không chu trình (DAG)**, quy hoạch động theo thứ tự tô-pô tìm đường đi dài nhất trong **O(V+E)**.
- **Subset Sum** với các số nguyên không âm có thuật toán **O(nS)** theo tổng đích S. Điều này có thể hiệu quả khi S nhỏ, nhưng là **giả đa thức (pseudo-polynomial)**, không tự động là đa thức theo số bit đầu vào.
- Nhiều bài toán khó với kích thước n lớn nhưng có **tham số k nhỏ** có thể giải bằng thuật toán **FPT** thời gian f(k)·poly(n), chẳng hạn nhánh cận theo kích thước phủ đỉnh k.

Tư duy chính:

~~~text
Bai toan tong quat
        |
        v
Tim rang buoc co cau truc / tham so nho / mien gia tri hep
        |
        v
Chung minh dau vao dap ung rang buoc
        |
        v
Chon thuat toan chuyen biet + chung minh dung
        |
        v
Phan tich do phuc tap tren lop dau vao do
~~~

**Không được đánh đồng** “khó trong trường hợp tổng quát” với “mọi đầu vào đều khó”. Cũng không được suy luận ngược rằng giải nhanh một lớp con đã giải được bài toán tổng quát.

### Hai câu hỏi bắt buộc

1. Cấu trúc đặc biệt là **giả thiết được đề bảo đảm** hay là điều kiện cần **kiểm tra trên input**?
2. Thuật toán chuyên biệt có **bảo toàn mục tiêu và định nghĩa nghiệm** của bài gốc hay chỉ giải một bài toán gần giống?

Bài này lấy **Minimum Vertex Cover trên cây** làm ví dụ xuyên suốt, với một chương trình Java 17 hoàn chỉnh và kiểm thử vét cạn độc lập.

## 2. Hiểu đúng các phát biểu P, NP, NP-hard và NP-complete

Một bài toán **quyết định** yêu cầu câu trả lời YES/NO. Ví dụ:

~~~text
VERTEX COVER DECISION

Input: do thi G=(V,E), so nguyen k.
Question: co ton tai tap dinh C, |C|<=k,
          sao cho moi canh co it nhat mot dau mut trong C?
~~~

Bài toán này là **NP-complete** trên đồ thị vô hướng tổng quát. Bài toán **tối ưu** tìm |C| nhỏ nhất là **NP-hard**.

- **P:** các bài toán quyết định giải được trong thời gian đa thức bằng thuật toán xác định.
- **NP:** có thể kiểm chứng chứng nhận YES trong thời gian đa thức theo kích thước input.
- **NP-hard:** khó ít nhất như các bài toán trong NP theo kiểu phép quy dẫn được định nghĩa; không nhất thiết bản thân là bài toán quyết định thuộc NP.
- **NP-complete:** vừa thuộc NP vừa NP-hard.

**P so với NP vẫn là vấn đề chưa được giải quyết.** Vì vậy, nói “NP-hard nên chắc chắn không có thuật toán đa thức” là **không có cơ sở chứng minh hiện nay**. Cách diễn đạt đúng là chưa biết thuật toán đa thức tổng quát cho các bài toán NP-complete và một thuật toán như vậy sẽ kéo theo P=NP.

### Độ khó đo theo kích thước mã hóa

Tính chất đa thức được tính theo **độ dài biểu diễn input**, không chỉ giá trị số học của một tham số.

Ví dụ:

~~~text
S = 1,000,000,000

Do dai ma nhi phan cua S chi khoang 30 bit,
nhung mang boolean dp[0..S] can hon mot ty vi tri.
~~~

Do đó O(nS) không được gọi là đa thức theo độ dài bit của S khi S có thể tăng theo lũy thừa của độ dài input.

### Hạn chế miền input thay đổi bài toán thế nào?

Bài toán tổng quát cho phép mọi G. Bài toán “VERTEX COVER trên cây” chỉ cho phép G là cây. Đây là một **lớp input con** có tính chất rất mạnh (không chu trình, một đường đơn duy nhất nối hai đỉnh). Một thuật toán đa thức trên lớp con ấy không mâu thuẫn với NP-hard của bài toán tổng quát.

### Bảng phân biệt

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| General Vertex Cover là NP-hard | Đúng | Bài tối ưu tổng quát |
| Vertex Cover trên cây giải được tuyến tính | Đúng | Tree DP |
| NP-hard có nghĩa mọi instance đều chậm | Sai | Nhiều instance/lớp con dễ |
| Có thuật toán O(n) trên cây thì general Vertex Cover thuộc P | Sai | Chưa xử lý đồ thị có chu trình |
| Mọi thuật toán O(nS) đều đa thức theo bit input | Sai | S có thể rất lớn |
| Có nghiệm đúng trên input “hầu hết là cây” thì luôn đúng | Sai | Chỉ cần một chu trình đã có thể phá giả thiết DP |

## 3. Những dạng trường hợp đặc biệt hay đem lại lợi ích

Khi tiếp cận bài toán khó, kiểm tra các dạng ràng buộc sau:

1. **Cấu trúc đồ thị:** cây, rừng, DAG, hai phía, bậc tối đa nhỏ, ít chu trình, treewidth nhỏ.
2. **Ràng buộc độ dài logic:** mỗi mệnh đề chứa tối đa hai literal (2-SAT) thay vì CNF tùy ý.
3. **Kích thước tham số:** số đỉnh cần chọn k, số lần sửa, số nhóm, số tài nguyên đặc biệt.
4. **Miền số nhỏ:** tổng S, capacity W, độ dài thời gian hay khoảng giá trị nhỏ cho DP dạng bảng.
5. **Dữ liệu đã có thứ tự:** đã sort, khoảng không giao, tính đơn điệu, thứ tự tô-pô.
6. **Tính chất đại số:** đơn điệu, lồi, tuyến tính, ma trận đặc biệt, phép toán có nghịch đảo.
7. **Bài toán chỉ cần một dạng đầu ra yếu hơn:** tìm nghiệm bất kỳ thay vì tối ưu, xấp xỉ thay vì exact (phải được đề cho phép).
8. **Các thành phần độc lập:** có thể giải riêng từng thành phần liên thông, sau đó ghép nghiệm.

Nhưng **không phải mọi ràng buộc đều làm bài toán dễ**. Ví dụ một đồ thị thưa vẫn có thể chứa các cấu trúc khó; chỉ ít cạnh hơn không tự tạo tính chất tree hay DAG.

### Phân biệt “đặc biệt” với “nhỏ”

Nếu n≤20, có thể liệt kê 2ⁿ tập con và kết quả có thể đủ nhanh trong một bài thực tế. Nhưng đó là khai thác **giới hạn kích thước**, không phải chứng minh rằng bài toán tổng quát đã chuyển thành P.

Ngược lại, nếu G là cây, n có thể lên tới hàng trăm nghìn và thuật toán O(n) vẫn có cơ sở rõ ràng.

### Cần bảo toàn đầu ra

Một trường hợp đặc biệt phải dẫn tới **đúng nghiệm cho đầu vào thuộc lớp đó**. Không được tùy tiện xóa cạnh để làm đồ thị thành cây rồi áp dụng tree DP; nghiệm của cây đã xóa cạnh có thể không phủ được các cạnh bị xóa.

## 4. Ví dụ trung tâm: Minimum Vertex Cover

Cho đồ thị vô hướng G=(V,E), một tập C⊆V là **vertex cover** nếu **mỗi cạnh** (u,v)∈E có **u∈C hoặc v∈C**.

Mục tiêu tối ưu là tìm tập C có số đỉnh nhỏ nhất:

~~~text
minimize |C|

subject to:
  for each edge (u,v) in E:
      u in C OR v in C
~~~

### Ví dụ đường đi

~~~text
0 -- 1 -- 2 -- 3 -- 4
~~~

Một phủ đỉnh tối ưu là {1,3}, kích thước 2. Mỗi cạnh đều có ít nhất một đầu mút thuộc {1,3}.

Lưu ý:

- Không yêu cầu **cả hai** đầu mút thuộc C; chỉ **ít nhất một**.
- Không yêu cầu các đỉnh trong C liên thông với nhau.
- Đây là **vertex cover**, không phải **edge cover**, **independent set** hay **dominating set**.
- Với n≥1 và không có cạnh, tập rỗng là một vertex cover tối ưu kích thước 0.

### Bài tổng quát khó ở đâu?

Trên đồ thị có chu trình và cấu trúc tùy ý, quyết định chọn một đỉnh có thể ảnh hưởng đến nhiều cạnh chéo giữa các vùng. Không có một cách tách cây cha–con tự nhiên để mỗi nhánh độc lập sau khi cố định trạng thái của nút cha.

Bài toán quyết định “có phủ đỉnh kích thước ≤k không?” là NP-complete, còn việc tối thiểu hóa số đỉnh là NP-hard.

### Khi đồ thị là cây

Cây là đồ thị vô hướng **liên thông và không chu trình**. Cây có n đỉnh thì có đúng n−1 cạnh (với n≥1), và mỗi cặp đỉnh có một đường đi đơn duy nhất.

Ta có thể chọn một đỉnh bất kỳ làm **gốc** (ví dụ 0), tạo quan hệ cha–con. Nếu biết trạng thái có/chưa chọn của một đỉnh v, mọi cây con của các con của v trở nên **độc lập** cho mục tiêu phủ cạnh: giữa hai cây con không có cạnh nối ngang.

Đây chính là tính chất cấu trúc làm xuất hiện lời giải DP tuyến tính.

## 5. Quy hoạch động hai trạng thái trên cây

Chọn gốc 0 và xét mỗi đỉnh v cùng cây con của nó. Định nghĩa:

~~~text
dp0[v] = so dinh it nhat de phu moi canh
         o trong cay con goc v,
         VOI dieu kien v KHONG DUOC CHON

dp1[v] = so dinh it nhat de phu moi canh
         o trong cay con goc v,
         VOI dieu kien v DUOC CHON
~~~

Hai trạng thái này đã cố định việc chọn v, nên có thể ghép các phương án tối ưu của cây con.

### Trường hợp v không được chọn

Với mỗi cạnh (v,u), u là con của v. Nếu v không thuộc C thì **u bắt buộc thuộc C** để phủ cạnh (v,u).

~~~text
dp0[v] = SUM_{u la con cua v} dp1[u]
~~~

### Trường hợp v được chọn

Nếu v thuộc C, mọi cạnh (v,u) đã được phủ tại v, nên mỗi u có thể chọn hoặc không, miễn phần cây con bên dưới được phủ tối ưu:

~~~text
dp1[v] = 1
       + SUM_{u la con cua v} min(dp0[u], dp1[u])
~~~

Số 1 là chi phí chọn chính v.

### Lá và cây chỉ có một đỉnh

Với lá v không có con:

~~~text
dp0[v] = 0
dp1[v] = 1
~~~

Không có cạnh nào trong cây con gồm một đỉnh; nếu không chọn v thì cần 0 đỉnh. Nếu buộc chọn v thì cần 1 đỉnh.

### Kết quả tại gốc

~~~text
minVertexCoverSize = min(dp0[root], dp1[root])
~~~

Nếu cần **trả cả tập đỉnh**, phải truy vết lựa chọn phù hợp trạng thái tối ưu từ gốc xuống các con, không chỉ in kích thước.

## 6. Mô phỏng trên một cây cụ thể

Cây có 7 đỉnh:

~~~text
        0
       / \
      1   2
     / \ / \
    3  4 5  6
~~~

Danh sách cạnh:

~~~text
(0,1), (0,2), (1,3), (1,4), (2,5), (2,6)
~~~

Lấy 0 làm gốc. Các lá 3,4,5,6 đều có:

~~~text
dp0[leaf]=0
dp1[leaf]=1
~~~

Với v=1, có hai con 3,4:

~~~text
dp0[1] = dp1[3] + dp1[4] = 1+1 = 2

dp1[1] = 1 + min(dp0[3],dp1[3])
           + min(dp0[4],dp1[4])
       = 1 + 0 + 0
       = 1
~~~

Với v=2 tương tự: dp0[2]=2, dp1[2]=1.

Tại gốc v=0:

~~~text
dp0[0] = dp1[1] + dp1[2]
       = 1 + 1
       = 2

dp1[0] = 1 + min(2,1) + min(2,1)
       = 3
~~~

Bảng DP:

| Đỉnh | dp0 (không chọn đỉnh) | dp1 (chọn đỉnh) |
| ---: | ---: | ---: |
| 3,4,5,6 | 0 | 1 |
| 1 | 2 | 1 |
| 2 | 2 | 1 |
| 0 | 2 | 3 |

Vì dp0[0] nhỏ hơn dp1[0], phương án tối ưu **không chọn 0**. Khi đó cả 1 và 2 buộc phải chọn:

~~~text
C = {1,2}
|C| = 2
~~~

Mỗi cạnh có ít nhất một đầu mút 1 hoặc 2. Không có nghiệm kích thước 1 vì một đỉnh không thể phủ đồng thời các cạnh thuộc hai nhánh sâu. DP đã chứng minh một cách tổng quát rằng kích thước tối ưu là 2.

### Ví dụ đường đi và ngôi sao

Đường đi năm đỉnh:

~~~text
0 -- 1 -- 2 -- 3 -- 4

optimal C={1,3}
size=2
~~~

Ngôi sao sáu đỉnh có 0 nối với 1,2,3,4,5:

~~~text
       1
       |
  2 -- 0 -- 3
      / \
     4   5

optimal C={0}
size=1
~~~

Hai cây đều có n−1 cạnh, nhưng cấu trúc khác nhau tạo ra nghiệm tối ưu khác nhau. Đây là ví dụ tại sao không thể quyết định bằng một quy tắc tham lam đơn giản như “cứ lấy lá”, nếu không chứng minh.

## 7. Truy vết tập đỉnh tối ưu và xử lý hòa

Chỉ biết dp0[root] và dp1[root] cho kích thước tối ưu, chưa đủ để trả tập đỉnh.

Gọi `take[v]` là việc chọn đỉnh v. Tại gốc:

~~~text
take[root] = (dp1[root] < dp0[root])
~~~

Bài này chọn quy tắc **ưu tiên không chọn** nếu hai trạng thái bằng nhau; đây chỉ là một tie-break hợp lệ, không phải điều kiện tối ưu bắt buộc.

Sau đó đi từ cha xuống con:

- Nếu cha **không được chọn**, con **bắt buộc được chọn** để phủ cạnh nối cha–con.
- Nếu cha **được chọn**, con có thể chọn trạng thái chi phí nhỏ hơn: chọn khi dp1[con]<dp0[con], không chọn nếu ngược lại hoặc hòa.

Giả mã:

~~~text
take[root] = dp1[root] < dp0[root]

for each non-root vertex v in parent-before-child order:
    p = parent[v]

    if take[p] == false:
        take[v] = true
    else:
        take[v] = dp1[v] < dp0[v]
~~~

Kết thúc, thu các v có `take[v]=true`. Bởi vì mỗi nhánh con được chọn nhất quán với trạng thái của cha và DP, tập thu được vừa phủ mọi cạnh, vừa có kích thước tối ưu.

### Có thể có nhiều nghiệm tối ưu

Nếu hai trạng thái ở một con cùng tối ưu, có thể chọn một trong hai miễn không vi phạm việc phủ cạnh với cha. Bài này cố định tie-break để output **có thể dự đoán** và dễ test.

Không được khẳng định nghiệm tối ưu là duy nhất chỉ vì chương trình trả một danh sách đỉnh cụ thể.

### Lưu ý về thứ tự output

Java demo thu các đỉnh được chọn theo thứ tự chỉ số tăng dần, bất kể thứ tự duyệt cây. Điều này giúp output ổn định và kiểm thử đơn giản.

## 8. Chứng minh tính đúng của Tree DP

Chứng minh bằng **quy nạp trên kích thước cây con**.

**Cơ sở:** cây con chỉ chứa lá v và không có cạnh nội bộ. Nếu v không được chọn, phủ 0 cạnh cần 0 đỉnh; nếu v buộc được chọn thì cần đúng 1 đỉnh. Nên dp0[v]=0 và dp1[v]=1 là tối ưu.

**Giả thiết quy nạp:** với mọi con u của v, dp0[u] và dp1[u] là chi phí tối ưu đúng theo trạng thái đã cố định của u.

**Trường hợp v không chọn:** mỗi cạnh (v,u) buộc u phải được chọn. Vì cây không có cạnh nối giữa các cây con khác nhau, việc lựa chọn trong cây con u không ảnh hưởng các cây con khác. Chi phí nhỏ nhất là tổng dp1[u]. Bất kỳ lời giải hợp lệ nào cũng phải trả ít nhất mức đó; ghép các nghiệm đạt dp1[u] lại đạt chính mức đó. Nên dp0[v] tối ưu.

**Trường hợp v được chọn:** cạnh (v,u) đã được phủ, trạng thái u có thể tùy chọn. Với mỗi u, chi phí tốt nhất là min(dp0[u],dp1[u]), cộng thêm 1 cho v. Các cây con độc lập nên tổng này đạt được và không có lời giải rẻ hơn. Nên dp1[v] tối ưu.

Suy ra đúng tại mọi đỉnh. Tại gốc, không có cạnh nối với cha, nên nghiệm toàn cây có thể chọn hoặc không chọn gốc, và **min(dp0[root],dp1[root])** là tối ưu toàn cục.

### Vì sao giả thiết “không có chu trình” quan trọng?

Nếu có cạnh nối giữa hai cây con khác nhau, các lựa chọn không còn độc lập. Chẳng hạn thêm cạnh (3,5) vào cây ở phần 6: chọn {1,2} không phủ cạnh (3,5). Công thức DP ban đầu không ghi nhận ràng buộc mới này.

**Không được** lấy tùy ý một spanning tree của đồ thị có chu trình rồi áp dụng tree DP cho toàn bộ đồ thị gốc. Nó chỉ tối ưu trên cạnh của spanning tree, có thể bỏ sót các cạnh còn lại.

## 9. Độ phức tạp của lời giải chuyên biệt

Với một cây n đỉnh:

- Kiểm số cạnh bằng n−1: O(1) cho điều kiện và O(n) để duyệt input.
- Xây danh sách kề: O(n+m), m=n−1.
- Duyệt từ gốc để lấy cha và thứ tự: O(n+m).
- Tính DP từ cuối thứ tự về đầu: mỗi cạnh xét hữu hạn lần, O(n+m).
- Truy vết và thu danh sách đỉnh: O(n).

Tổng **O(n+m)=O(n)** cho cây, dùng **O(n+m)=O(n)** bộ nhớ. Việc kiểm cạnh trùng qua hash set như mã ví dụ có **thời gian kỳ vọng O(n)** với giả thiết thao tác hash bình quân O(1).

### Tránh stack overflow trên cây đường dài

Cách cài DFS đệ quy rất dễ hiểu nhưng với cây là đường đi dài hàng trăm nghìn đỉnh có thể gây `StackOverflowError` trong Java.

Chương trình dưới đây dùng **thứ tự duyệt dạng hàng đợi trong một mảng `order`**, rồi tính DP theo thứ tự đảo ngược. Không có đệ quy theo chiều cao cây, nên tránh rủi ro stack overflow từ độ sâu lớn.

### So với vét cạn

Vét cạn thử 2ⁿ tập đỉnh, kiểm từng tập có phủ đủ cạnh hay không, chi phí khoảng:

~~~text
O(2^n * m)
~~~

Với n=6, cách này rất phù hợp làm **oracle kiểm thử**. Nhưng với n=100.000, nó bất khả thi. DP trên cây vẫn tuyến tính, kể cả khi n rất lớn.

### Thực tế của input

Câu “thuật toán O(n)” giả định input đúng dạng cây đơn vô hướng, cấu trúc kề đủ để duyệt cạnh O(1) trung bình và thao tác cộng/so sánh trên số nguyên kích thước đủ nhỏ. Với một thuật toán kiểm tra tính cây trên input tổng quát n đỉnh m cạnh, riêng bước đọc/kiểm điều kiện tốn O(n+m).

## 10. Java 17: chương trình Tree Vertex Cover hoàn chỉnh

Chương trình `SpecialCaseVertexCoverDemo.java` chứng minh cả quy trình:

1. Nhận đồ thị vô hướng dưới dạng n và danh sách cạnh 0-index.
2. **Xác nhận đầu vào đúng là cây**; không âm thầm bỏ cạnh hoặc tự giả định.
3. Chọn gốc 0, tạo cha và thứ tự duyệt, không đệ quy.
4. Tính dp0, dp1 từ lá lên gốc.
5. Truy vết một vertex cover tối ưu và trả danh sách đỉnh tăng dần.
6. So kết quả với **brute force** trên mọi cây có nhãn n=1..6, được sinh bằng **chuỗi Prüfer**.
7. Có ví dụ đồ thị tổng quát là tam giác; brute force vẫn giải được khi rất nhỏ, nhưng **tree solver từ chối** thay vì cho kết quả sai.

**Lưu toàn bộ mã sau thành `SpecialCaseVertexCoverDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public class SpecialCaseVertexCoverDemo {

    public record Result(int size, int[] vertices) {}

    private static long edgeKey(int u, int v) {
        int a = Math.min(u, v);
        int b = Math.max(u, v);
        return ((long) a << 32) | (b & 0xffffffffL);
    }

    // Exact minimum vertex cover on a simple undirected tree.
    public static Result solveTree(int n, int[][] edges) {
        if (n <= 0) {
            throw new IllegalArgumentException(
                    "tree must have at least one vertex");
        }
        Objects.requireNonNull(edges, "edges");
        if (edges.length != n - 1) {
            throw new IllegalArgumentException(
                    "not a tree: edge count");
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            graph.add(new ArrayList<>());
        }

        Set<Long> seenEdges = new HashSet<>();
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("invalid edge");
            }

            int u = edge[0];
            int v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "invalid vertex");
            }
            if (u == v) {
                throw new IllegalArgumentException("self-loop");
            }
            if (!seenEdges.add(edgeKey(u, v))) {
                throw new IllegalArgumentException("parallel edge");
            }

            graph.get(u).add(v);
            graph.get(v).add(u);
        }

        // A parent-before-child order without recursion.
        // -2 means unvisited, -1 is the root's parent.
        int[] parent = new int[n];
        Arrays.fill(parent, -2);
        parent[0] = -1;

        int[] order = new int[n];
        order[0] = 0;
        int count = 1;

        for (int i = 0; i < count; i++) {
            int v = order[i];
            for (int u : graph.get(v)) {
                if (u == parent[v]) {
                    continue;
                }
                if (parent[u] != -2) {
                    throw new IllegalArgumentException(
                            "not a tree: cycle");
                }

                parent[u] = v;
                order[count++] = u;
            }
        }

        if (count != n) {
            throw new IllegalArgumentException(
                    "not a tree: disconnected");
        }

        int[] dp0 = new int[n];
        int[] dp1 = new int[n];

        // Reverse order: children are processed before parents.
        for (int i = n - 1; i >= 0; i--) {
            int v = order[i];
            dp1[v] = 1;

            for (int u : graph.get(v)) {
                if (parent[u] == v) {
                    dp0[v] += dp1[u];
                    dp1[v] += Math.min(dp0[u], dp1[u]);
                }
            }
        }

        boolean[] take = new boolean[n];
        // Break ties in favor of not taking the root.
        take[0] = dp1[0] < dp0[0];

        // Recover a complete optimal cover, parent first.
        for (int i = 1; i < n; i++) {
            int v = order[i];
            int p = parent[v];

            if (!take[p]) {
                take[v] = true;
            } else {
                // If equal, prefer not taking this child.
                take[v] = dp1[v] < dp0[v];
            }
        }

        int selectedCount = 0;
        for (boolean chosen : take) {
            if (chosen) {
                selectedCount++;
            }
        }

        int[] vertices = new int[selectedCount];
        int index = 0;
        for (int v = 0; v < n; v++) {
            if (take[v]) {
                vertices[index++] = v;
            }
        }

        int optimum = Math.min(dp0[0], dp1[0]);
        if (selectedCount != optimum) {
            throw new AssertionError(
                    "DP reconstruction mismatch");
        }
        return new Result(optimum, vertices);
    }

    private static boolean coversAllEdges(
            int n, int[][] edges, int[] vertices) {
        boolean[] chosen = new boolean[n];
        for (int v : vertices) {
            if (v < 0 || v >= n || chosen[v]) {
                return false;
            }
            chosen[v] = true;
        }

        for (int[] e : edges) {
            if (!chosen[e[0]] && !chosen[e[1]]) {
                return false;
            }
        }
        return true;
    }

    // Oracle ONLY for small n; exponential on general graphs.
    private static int bruteForceMinimum(
            int n, int[][] edges) {
        if (n > 20) {
            throw new IllegalArgumentException(
                    "brute force only supports n <= 20");
        }

        int best = n + 1;
        int limit = 1 << n;
        for (int mask = 0; mask < limit; mask++) {
            int count = Integer.bitCount(mask);
            if (count >= best) {
                continue;
            }

            boolean covers = true;
            for (int[] e : edges) {
                int u = e[0];
                int v = e[1];
                boolean hasU = (mask & (1 << u)) != 0;
                boolean hasV = (mask & (1 << v)) != 0;
                if (!hasU && !hasV) {
                    covers = false;
                    break;
                }
            }
            if (covers) {
                best = count;
            }
        }
        return best;
    }

    // Decode a Prüfer sequence into its labeled tree.
    // For n>=2, sequence length must be n-2.
    private static int[][] decodePrufer(
            int n, int[] sequence) {
        if (n == 1) {
            return new int[0][2];
        }

        int[] degree = new int[n];
        Arrays.fill(degree, 1);
        for (int v : sequence) {
            degree[v]++;
        }

        int[][] edges = new int[n - 1][2];
        int position = 0;

        for (int v : sequence) {
            int leaf = 0;
            while (degree[leaf] != 1) {
                leaf++;
            }

            edges[position++] = new int[] {leaf, v};
            degree[leaf]--;
            degree[v]--;
        }

        int first = -1;
        int second = -1;
        for (int v = 0; v < n; v++) {
            if (degree[v] == 1) {
                if (first == -1) {
                    first = v;
                } else {
                    second = v;
                }
            }
        }

        edges[position] = new int[] {first, second};
        return edges;
    }

    // Cayley/Prüfer: n^(n-2) labeled trees for n>=2.
    private static int verifyAllSmallTrees() {
        int checked = 0;

        for (int n = 1; n <= 6; n++) {
            int length = Math.max(0, n - 2);
            int possibilities = 1;
            for (int i = 0; i < length; i++) {
                possibilities *= n;
            }

            // Decode each integer as a base-n Prüfer sequence.
            for (int code = 0; code < possibilities; code++) {
                int[] sequence = new int[length];
                int value = code;
                for (int i = 0; i < length; i++) {
                    sequence[i] = value % n;
                    value /= n;
                }

                int[][] edges = decodePrufer(n, sequence);
                Result dp = solveTree(n, edges);
                int brute = bruteForceMinimum(n, edges);

                if (dp.size() != brute
                        || dp.vertices().length != brute
                        || !coversAllEdges(
                                n, edges, dp.vertices())) {
                    throw new AssertionError(
                            "DP differs from brute force");
                }
                checked++;
            }
        }

        if (checked != 1442) {
            throw new AssertionError(
                    "wrong enumeration count");
        }
        return checked;
    }

    private static void show(String label, Result result) {
        System.out.println(label
                + ": size=" + result.size()
                + ", vertices="
                + Arrays.toString(result.vertices()));
    }

    public static void main(String[] args) {
        show("balanced", solveTree(7, new int[][] {
                {0,1}, {0,2},
                {1,3}, {1,4},
                {2,5}, {2,6}
        }));

        show("path", solveTree(5, new int[][] {
                {0,1}, {1,2}, {2,3}, {3,4}
        }));

        show("star", solveTree(6, new int[][] {
                {0,1}, {0,2}, {0,3}, {0,4}, {0,5}
        }));

        show("single", solveTree(1, new int[0][2]));

        int[][] triangle = {
                {0,1}, {1,2}, {2,0}
        };
        try {
            solveTree(3, triangle);
        } catch (IllegalArgumentException error) {
            System.out.println("triangle rejected: "
                    + error.getMessage());
        }

        try {
            solveTree(4, triangle);
        } catch (IllegalArgumentException error) {
            System.out.println("triangle plus isolated: "
                    + error.getMessage());
        }

        try {
            solveTree(3, new int[][] {
                    {0,1}, {0,1}
            });
        } catch (IllegalArgumentException error) {
            System.out.println("parallel edges: "
                    + error.getMessage());
        }

        System.out.println("triangle brute force = "
                + bruteForceMinimum(3, triangle));

        int tested = verifyAllSmallTrees();
        System.out.println(
                "all labeled trees n=1..6 checked = " + tested);
        System.out.println(
                "all DP sizes match brute force = true");
    }
}
~~~

**Biên dịch và chạy với JDK 17 trở lên:**

~~~bash
javac SpecialCaseVertexCoverDemo.java
java SpecialCaseVertexCoverDemo
~~~

**Stdout xác định:**

~~~text
balanced: size=2, vertices=[1, 2]
path: size=2, vertices=[1, 3]
star: size=1, vertices=[0]
single: size=0, vertices=[]
triangle rejected: not a tree: edge count
triangle plus isolated: not a tree: cycle
parallel edges: parallel edge
triangle brute force = 2
all labeled trees n=1..6 checked = 1442
all DP sizes match brute force = true
~~~

### Điểm quan trọng của chương trình

- `solveTree` **chỉ** trả lời đúng trên đồ thị là cây vô hướng đơn; đầu vào không thỏa điều kiện bị từ chối rõ ràng.
- Kiểm n−1 cạnh là **cần nhưng không đủ** nếu chưa kiểm liên thông: tam giác cộng một đỉnh cô lập vẫn có n−1 cạnh nhưng không phải cây.
- Kiểm cạnh trùng và self-loop ngăn những mô hình không phải đồ thị đơn lọt qua giả thiết.
- Thứ tự duyệt `order` bảo đảm cha được xét trước con, và thứ tự đảo cho phép tính DP từ con lên cha **không cần đệ quy**.
- `bruteForceMinimum` chỉ dùng làm kiểm thử hoặc xử lý đồ thị rất nhỏ; độ phức tạp mũ không thuộc lời giải chuyên biệt O(n).
- Tập đỉnh kết quả được kiểm cả **kích thước tối ưu** lẫn **thực sự phủ mọi cạnh**.

Đây là bài học quan trọng về thiết kế API: thuật toán chuyên biệt nên công bố và kiểm tra điều kiện áp dụng thay vì lặng lẽ đưa ra đáp án có vẻ hợp lý trên đầu vào không được hỗ trợ.

## 11. Kiểm thử độc lập bằng chuỗi Prüfer và brute force

Để xác minh quy hoạch động trên nhiều cây khác nhau, ta không chỉ thử một vài ví dụ do người viết chọn.

**Chuỗi Prüfer** là một cách mã hóa cây có nhãn. Với n≥2, mỗi chuỗi độ dài n−2 mà mỗi phần tử nằm trong {0,…,n−1} tương ứng duy nhất với một cây có nhãn n đỉnh, và ngược lại. Do đó số cây có nhãn là:

~~~text
n^(n-2)
~~~

Với n=1 có đúng một cây một đỉnh.

Số cây cho từng n nhỏ:

| n | Số cây có nhãn |
| ---: | ---: |
| 1 | 1 |
| 2 | 1 |
| 3 | 3 |
| 4 | 16 |
| 5 | 125 |
| 6 | 1.296 |
| **Tổng** | **1.442** |

### Oracle vét cạn không dùng công thức DP

Trên từng cây, thử mọi bitmask chọn/không chọn n đỉnh:

~~~text
for mask in [0, 2^n):
    if every edge (u,v) has u or v selected:
        best = min(best, number of selected vertices)
~~~

Với n≤6, nhiều nhất có 64 tập đỉnh cho mỗi cây. Oracle không giả sử cấu trúc cha–con; nó giải bài tối ưu theo đúng định nghĩa gốc.

Sau đó so với Tree DP:

1. `dp.size` bằng optimum vét cạn.
2. Số đỉnh trong `dp.vertices` bằng optimum.
3. Mọi cạnh có ít nhất một đầu mút nằm trong `dp.vertices`.
4. Có đúng 1.442 cây được kiểm, không bỏ sót dạng cây có nhãn n≤6.

Đây là một kiểm thử rất mạnh cho thuật toán nhỏ. Nó **không thay thế chứng minh quy nạp** ở phần 8, nhưng giúp phát hiện nhiều lỗi cài đặt như thiếu trạng thái, sai truy vết, nhầm cha/con hoặc đếm sai.

### Không phải “1.442 cây ngẫu nhiên”

Bộ test **liệt kê toàn bộ** các cây có nhãn từ 1 đến 6 đỉnh, chứ không phải lấy ngẫu nhiên 1.442 mẫu. Khi vượt n=6, số cây tăng nhanh theo n^(n−2), nên exhaustive không còn thực tế với n lớn. Có thể kết hợp test sinh cây ngẫu nhiên và các dạng cực trị như đường dài, sao, cây cân bằng.

## 12. Trường hợp đặc biệt khác của Vertex Cover

### Rừng (forest)

Rừng là hợp của các thành phần liên thông **không có chu trình**. Mỗi thành phần là một cây, nên có thể chạy Tree DP độc lập trên từng thành phần rồi hợp các tập phủ đỉnh tối ưu.

~~~text
optimum(forest)
  = SUM over connected tree components optimum(component)
~~~

Tổng thời gian vẫn O(n+m) với danh sách kề. **Mã Java hiện tại chỉ nhận cây liên thông**, không tự cài rừng; để hỗ trợ rừng cần chọn gốc cho từng thành phần và tính/truy vết riêng.

### Đồ thị hai phía (bipartite)

Minimum Vertex Cover **không trọng số** trên đồ thị hai phía giải được đa thức nhờ **định lý König**: kích thước phủ đỉnh nhỏ nhất bằng kích thước **maximum matching**.

Nếu đồ thị có hai phía L,R, có thể tìm matching cực đại bằng **Hopcroft–Karp**, thời gian O(E√V) trong cài đặt chuẩn. Từ matching, xây phủ đỉnh tối ưu bằng các đường luân phiên theo quy tắc thích hợp.

Cần xác nhận đồ thị **thực sự hai phía** (ví dụ tô hai màu qua BFS/DFS). Đồ thị có chu trình lẻ không hai phía, và không được dùng định lý König để suy ra kích thước vertex cover của nó.

**Cây là một lớp con của đồ thị hai phía**, nhưng Tree DP trực tiếp O(n) thường đơn giản hơn cho cây.

### Trọng số trên đỉnh của cây

Nếu chọn đỉnh v có chi phí w[v] thay vì 1, chỉ cần thay:

~~~text
dp1[v] = w[v] + SUM min(dp0[child],dp1[child])
dp0[v] = SUM dp1[child]
~~~

Vẫn giải được trong O(n) trên cây, với kiểu số đủ rộng cho tổng chi phí. Mã minh họa dùng trọng số đơn vị và trả **số lượng đỉnh**, không cài weighted version.

### Đồ thị bậc tối đa 2

Mỗi thành phần liên thông của đồ thị đơn vô hướng có bậc tối đa 2 là **đường đi hoặc chu trình**. Trên đường đi, DP tương tự cây; trên chu trình, có thể xét hai trường hợp chọn/không chọn một đỉnh cố định rồi chạy DP trên phần còn lại, kết hợp ràng buộc biên.

Đây là ví dụ khác về “ít cấu trúc hơn cây nhưng vẫn xử lý được bằng số trạng thái nhỏ”. Không được suy ra rằng mọi đồ thị bậc nhỏ bất kỳ đều dễ theo cách này.

### Treewidth nhỏ

Một đồ thị có **treewidth t nhỏ** có thể hỗ trợ DP trên một tree decomposition, giữ trạng thái cho các đỉnh trong mỗi bag. Nhiều bài toán khó trên đồ thị có thời gian dạng 2^O(t)·poly(n) khi đã có phân rã thích hợp.

Nhưng không phải chỉ cần “nhìn có vẻ giống cây” là có treewidth nhỏ. Tìm phân rã phù hợp cũng là một phần của bài toán thuật toán và không được bỏ qua trong phân tích.

## 13. 2-SAT dễ hơn 3-SAT: khai thác độ dài mệnh đề

**SAT** hỏi một công thức Boolean có tồn tại cách gán true/false cho các biến làm công thức đúng hay không.

Trong dạng CNF, công thức là phép AND của các mệnh đề OR. Ví dụ:

~~~text
(x OR y)
AND (NOT x OR z)
AND (NOT y OR NOT z)
~~~

Nếu mỗi mệnh đề có **tối đa hai literal**, ta có bài toán **2-SAT**, giải được trong **O(n+m)** theo số biến n và mệnh đề m bằng đồ thị kéo theo (implication graph) và SCC.

### Biến đổi mệnh đề 2 literal thành hai cung kéo theo

~~~text
(a OR b)  equivalent to
(NOT a => b) AND (NOT b => a)
~~~

Tạo một đỉnh cho mỗi literal x và NOT x. Với mỗi mệnh đề (a OR b), thêm hai cung:

~~~text
NOT a -> b
NOT b -> a
~~~

Tính các thành phần liên thông mạnh (SCC) trong đồ thị có hướng. Công thức **vô nghiệm khi và chỉ khi** có một biến x sao cho x và NOT x thuộc **cùng một SCC**.

Nếu không có mâu thuẫn này, có thể suy ra một phép gán thỏa bằng thứ tự SCC thích hợp.

### Tại sao 3-SAT không áp dụng y nguyên?

**3-SAT** (mệnh đề có đúng ba literal trong dạng chuẩn) là NP-complete. Phép thay mỗi mệnh đề ba literal thành hai literal bằng cách bỏ một literal **không bảo toàn** tập nghiệm.

Ví dụ `(x OR y OR z)` đúng khi x=y=false và z=true, nhưng `(x OR y)` sẽ sai. Vì thế không thể “rút ngắn” mệnh đề tùy ý để biến 3-SAT thành 2-SAT mà vẫn nói đã giải đúng bài toán gốc.

### Ý nghĩa thiết kế

Ràng buộc “mỗi mệnh đề có tối đa hai literal” là **thuộc tính hình thức của input**, có thể kiểm qua từng mệnh đề. Nó đổi một bài toán khó tổng quát thành lớp có cấu trúc kéo theo mạnh, dẫn tới thuật toán tuyến tính.

## 14. Đường đi dài nhất: DAG thay cho đồ thị có chu trình

Bài toán **longest simple path** trên đồ thị tổng quát là NP-hard trong dạng tối ưu thích hợp, vì không được lặp đỉnh và có thể phải chọn giữa nhiều chu trình/nhánh tương tác.

Nếu đồ thị có hướng là **DAG (Directed Acyclic Graph)**, ta có thể tìm đường đi dài nhất bằng DP theo thứ tự tô-pô.

### Công thức

Giả sử tìm đường đi có trọng số lớn nhất từ nguồn s. Khởi tạo:

~~~text
dist[s] = 0
dist[v] = -INFINITY voi v khac s
~~~

Lấy thứ tự tô-pô `topo` trong đó mỗi cung u→v có u đứng trước v. Duyệt các đỉnh theo thứ tự đó, với mỗi cung (u,v,w):

~~~text
if dist[u] is reachable:
    dist[v] = max(dist[v], dist[u] + w)
~~~

Vì không có chu trình, lúc xử lý v thì mọi tiền nhiệm của v đều đã được xét. Không có ràng buộc đường đi đơn khó xử lý: mọi đường đi có hướng trong DAG tự động không lặp đỉnh.

### Độ phức tạp

Tính topo bằng Kahn/DFS và nới lỏng mọi cạnh đúng một lần: **O(V+E)** thời gian, **O(V+E)** bộ nhớ nếu tính cả danh sách kề.

### Điều kiện cần kiểm

Nếu input chỉ hứa “đồ thị có hướng” mà **không bảo đảm DAG**, phải kiểm có thứ tự tô-pô chứa đủ V đỉnh. Nếu còn chu trình, không áp dụng công thức này như thuật toán longest simple path tổng quát.

Trọng số cạnh âm vẫn xử lý được trên DAG, vì DP theo topo không dựa vào giả định trọng số không âm. Nhưng cần dùng sentinel cho trạng thái không đến được và kiểu số tránh tràn khi cộng trọng số.

## 15. Miền số nhỏ: Subset Sum và giả đa thức

Bài toán **Subset Sum** hỏi có chọn một tập con các số sao cho tổng đúng S không.

Với n số **nguyên không âm** và S nguyên không âm, ta có thể dùng DP:

~~~text
dp[t] = co the tao tong t tu cac phan tu da xu ly?

dp[0] = true

for each value a:
    for t from S downTo a:
        dp[t] = dp[t] OR dp[t-a]
~~~

Vòng t **phải duyệt giảm** nếu mỗi phần tử chỉ được dùng một lần; duyệt tăng dễ dùng lại cùng phần tử trong một lượt, biến bài thành dạng unbounded.

Thời gian **O(nS)**, bộ nhớ **O(S)**, có thể phù hợp nếu S chỉ vài nghìn hoặc vài trăm nghìn.

### Vì sao đây không chứng minh Subset Sum thuộc P?

Nếu S được mã hóa nhị phân, độ dài mã hóa của S chỉ O(log S). Một thuật toán phụ thuộc tuyến tính vào **giá trị S** có thể là mũ theo số bit dùng để viết S.

Vì vậy phải gọi O(nS) là **pseudo-polynomial**. Nó thực tế nhanh khi S nhỏ nhưng không phải chứng minh đa thức cho các trường hợp có S cực lớn.

### Những điều kiện không được bỏ qua

- Các số a phải không âm với DP đơn giản trên các tổng 0..S; nếu có số âm, cần trạng thái hoặc miền tổng khác.
- Các phần tử lớn hơn S có thể bỏ qua **khi tất cả số không âm**, vì chúng không thể góp vào tổng S; điều này không còn đúng nếu có số âm để bù.
- Nếu bài cho phép lặp lại phần tử tùy ý, công thức chuyển và thứ tự vòng lặp thay đổi.
- Nếu mục tiêu là **đếm số cách** hoặc **tối ưu số phần tử**, boolean DP trên không trả đủ thông tin.

Đây là ví dụ điển hình của khai thác **miền trị số nhỏ** thay vì khai thác cấu trúc đồ thị.

## 16. Tham số nhỏ: Vertex Cover theo k và FPT

Đôi khi đồ thị không phải cây hoặc hai phía, nhưng câu hỏi là:

~~~text
Co vertex cover kich thuoc <= k hay khong?
~~~

Với k nhỏ, ta có thể dùng **branching theo một cạnh chưa được phủ**.

Chọn một cạnh (u,v). Bất kỳ vertex cover hợp lệ nào cũng phải chứa **u hoặc v**. Từ đây tách hai nhánh:

~~~text
hasCoverAtMostK(G,k):
    if E is empty:
        return true
    if k < 0:
        return false

    choose an edge (u,v) in E

    return hasCoverAtMostK(G minus u, k-1)
        OR hasCoverAtMostK(G minus v, k-1)
~~~

Ở đây “G minus u” nghĩa là chọn u vào phủ đỉnh và loại các cạnh kề u khỏi danh sách cạnh còn phải phủ. Hai nhánh là đầy đủ vì mỗi phủ đỉnh phải chứa ít nhất một trong hai đầu mút cạnh (u,v).

### Độ phức tạp theo k

Mỗi nhánh giảm k ít nhất 1, có tối đa 2 nhánh mỗi mức, nên cây tìm kiếm có O(2^k) nút trong phân tích đơn giản. Nếu mỗi nút xử lý đồ thị bằng thời gian đa thức, ta được:

~~~text
O(2^k * poly(n+m))
~~~

Đây là dạng **Fixed-Parameter Tractable (FPT)** theo k. Khi k nhỏ, thuật toán có thể hữu ích dù n lớn. Khi k≈n, nó vẫn có thể rất chậm.

### Điều khác với tree DP

- Tree DP O(n+m) giải **tối ưu chính xác** khi đồ thị là cây, bất kể kích thước nghiệm.
- Branching FPT giải **bài quyết định ≤k** trên đồ thị tổng quát, nhưng thời gian mũ theo k.
- Một chiến lược thực tế có thể kiểm tra tree trước, sau đó dùng FPT nếu k nhỏ, nếu không thì chọn thuật toán tổng quát hoặc thông báo giới hạn.

### Kernelization

Một thuật toán FPT đôi khi có thể **rút gọn instance** trong thời gian đa thức thành một instance tương đương với kích thước phụ thuộc k; đây gọi là **kernelization**. Các quy tắc rút gọn phải bảo toàn câu trả lời YES/NO theo chứng minh, không phải tùy tiện xóa cạnh/đỉnh.

## 17. Kiểm tra giả thiết, promise và chiến lược hybrid

### Trường hợp đề hứa cấu trúc

Nếu đề ghi rõ input **luôn là một cây**, thuật toán có thể tin vào hợp đồng đó. Tất nhiên cần vẫn hiểu các quy ước về chỉ số, self-loop và cạnh trùng. Không cần tìm lời giải tổng quát cho những input bị loại khỏi miền đề.

### Trường hợp input không được bảo đảm

Nếu một chương trình thư viện nhận đồ thị tùy ý, nên **kiểm điều kiện** trước khi gọi thuật toán chuyên biệt. Với cây vô hướng đơn:

- n≥1.
- Có đúng n−1 cạnh.
- Mọi đỉnh hợp lệ, không có self-loop, không có cạnh song song nếu định nghĩa input là đồ thị đơn.
- Đồ thị liên thông (kiểm BFS/DFS).
- Hai điều kiện n−1 cạnh và liên thông là đủ kết luận không có chu trình đối với đồ thị vô hướng đơn.

Chương trình Java demo kiểm các yêu cầu ấy. Một tam giác cộng một đỉnh cô lập có 4 đỉnh và 3 cạnh, vẫn **không phải cây**. Đây là lý do kiểm mỗi `m==n−1` là chưa đủ.

### Hybrid algorithm

Một chiến lược có thể là:

~~~text
if graph is tree:
    use Tree DP        // exact, O(n+m)
else if graph is bipartite:
    use maximum matching + Konig
else if n is tiny:
    use exact brute force
else if requested k is small:
    use FPT branching
else:
    use an authorized general solver / approximation
    or report unsupported exact instance
~~~

Ở mỗi nhánh:

- Phải chứng minh test điều kiện đúng và không quá tốn thời gian.
- Phải giữ đúng định nghĩa nghiệm mà bài toán yêu cầu.
- Nếu dùng xấp xỉ, phải **ghi rõ đây là xấp xỉ**, có tỷ lệ bảo đảm hay không; không lặng lẽ gọi đáp án tối ưu.
- Nếu từ chối đầu vào, thông báo không hỗ trợ **khác với** kết luận “không có nghiệm”.

### Một lưu ý về kiểm điều kiện

Không phải ràng buộc nào cũng dễ nhận diện. Kiểm một đồ thị có phải cây hoặc DAG có thể làm tuyến tính; nhưng việc tìm ra một tham số cấu trúc thích hợp như treewidth nhỏ **kèm decomposition tối ưu** có thể là phần khó riêng. Không được bỏ qua chi phí nhận dạng cấu trúc trong phân tích thuật toán tổng thể.

## 18. Quy trình thực hành để tận dụng một trường hợp đặc biệt

Một quy trình đáng tin cho bài thi và ứng dụng:

**Bước 1 – Xác định bài toán quyết định/tối ưu.** Input là gì, đầu ra cần tối ưu gì, một nghiệm hợp lệ phải thỏa điều kiện nào? Tránh nhầm vertex cover với independent set, hoặc đúng một phương án với tất cả phương án.

**Bước 2 – Nhận ra khó khăn tổng quát.** Nếu bài thuộc nhóm NP-hard, đừng mặc định cần thử mọi tập con ngay. Kiểm các điều kiện mà đề hoặc dữ liệu có thể cho.

**Bước 3 – Tìm cấu trúc có chứng minh.** Cây/rừng, đồ thị hai phía, DAG, độ dài mệnh đề, tổng đích nhỏ, tham số k nhỏ. Ghi chính xác điều kiện thay vì nói chung “graph sparse”.

**Bước 4 – Thiết kế trạng thái đủ.** Với tree vertex cover, trạng thái duy nhất từ phía cha ảnh hưởng cây con là “v được chọn hay không”, nên hai giá trị dp0/dp1 là đủ. Với cấu trúc khác, số trạng thái có thể lớn hơn.

**Bước 5 – Chứng minh các phần con độc lập.** Đây là chỗ quan trọng nhất. Nếu có cạnh chéo giữa các cây con, cộng chi phí riêng từng cây con sẽ không còn đúng.

**Bước 6 – Phân tích độ phức tạp với miền input thật.** Tree DP O(n), Subset Sum O(nS) giả đa thức, FPT O(2^k poly(n)), chứ không gom tất cả vào từ “nhanh”.

**Bước 7 – Chọn cách xử lý input ngoài miền.** Xác minh điều kiện, áp dụng nhánh fallback đúng, hoặc từ chối; tuyệt đối không âm thầm bỏ dữ liệu để khớp giả thiết.

**Bước 8 – Kiểm thử độc lập.** Với n nhỏ, so lời giải chuyên biệt với vét cạn theo định nghĩa bài toán, sau đó test dữ liệu lớn kiểu đường dài/sao để kiểm hiệu năng và stack.

### Quy tắc đặt tên

Trong code và tài liệu, nên đặt rõ `solveTree`, `solveBipartite`, `solveAtMostK` thay vì một hàm tên quá rộng `solveVertexCover` nhưng ngầm chỉ hỗ trợ cây. Tên phản ánh miền hợp lệ làm giảm nguy cơ gọi nhầm thuật toán.

## 19. Lỗi phổ biến, phản ví dụ và bài tập

### Những lỗi hay làm sai lời giải

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “NP-hard thì mọi input đều khó” | Nhầm worst-case tổng quát với lớp con | Tìm cấu trúc đặc biệt |
| “Giải cây O(n) nên giải mọi graph O(n)” | Không còn độc lập cây con khi có chu trình | Giữ điều kiện tree |
| Chỉ kiểm m=n−1 | Tam giác + đỉnh cô lập cũng thỏa | Kiểm liên thông/chu trình |
| Xóa cạnh dư để tạo spanning tree | Có thể bỏ ràng buộc phủ cạnh | Không biến input một cách sai |
| Chỉ dùng greedy chọn bậc cao nhất | Không bảo đảm optimal cho general graph | DP/FPT/matching/đối chứng |
| Lấy mọi lá làm đáp án | Có thể chọn quá nhiều đỉnh | Sử dụng dp0/dp1 |
| Quên điều kiện cha không chọn thì con phải chọn | Cạnh cha–con không được phủ | Truy vết đúng |
| Trộn `dp0` và `dp1` | Sai ngữ nghĩa trạng thái | Ghi rõ từng trạng thái |
| Duyệt DP trước khi xử lý con | Lấy giá trị con chưa tính | Thứ tự con trước cha |
| Không xác minh tập đỉnh đầu ra | Kích thước có thể đúng nhưng tập không phủ | Kiểm mỗi cạnh |
| Nhầm vertex cover với edge cover | Hai bài khác nhau | Định nghĩa đầu ra |
| Coi 2-SAT và 3-SAT cùng độ khó | Độ dài mệnh đề quyết định thuật toán | SCC cho 2-SAT |
| Tự bỏ literal khỏi mệnh đề 3-SAT | Đổi tập nghiệm | Giữ đúng công thức |
| Chạy longest-path topo trên graph có chu trình | Thứ tự topo không hợp lệ | Kiểm DAG |
| Gọi O(nS) là đa thức theo bit input | S có thể mũ theo số bit | Ghi pseudo-polynomial |
| Dùng DP Subset Sum 0..S cho số âm không sửa trạng thái | Bỏ tổng âm hoặc bù | Thiết kế miền trạng thái mới |
| Duyệt tổng tăng ở 0/1 Subset Sum | Dùng một item nhiều lần | Duyệt giảm |
| Gọi FPT là polynomial tổng quát | Vẫn có 2^k | Phân tích tham số |
| Bỏ chi phí nhận diện đặc trưng | Tổng runtime bị đánh giá thấp | Tính cả recognition |
| Dùng brute force cho n rất lớn | 2^n không khả thi | Khai thác lớp con thật sự |
| Giữ đệ quy trên cây cực dài | Stack overflow | Duyệt lặp + đảo thứ tự |
| Dùng approximation rồi ghi “optimal” | Sai hợp đồng đầu ra | Báo rõ mức xấp xỉ |

### Bài tập từ cơ bản đến nâng cao

1. Định nghĩa vertex cover của một đồ thị vô hướng.
2. Phân biệt “bài toán quyết định Vertex Cover” với “Minimum Vertex Cover tối ưu”.
3. Giải thích tại sao NP-hard không có nghĩa mọi instance đều khó.
4. Nêu điểm khác nhau giữa thời gian đa thức theo input bits và giả đa thức.
5. Với cây 0–1–2–3–4, tìm một vertex cover nhỏ nhất.
6. Với ngôi sao có tâm 0 và năm lá, giải thích vì sao chọn 0 là tối ưu.
7. Viết hai trạng thái dp0[v] và dp1[v] của Tree Vertex Cover.
8. Chứng minh nếu v không được chọn thì mọi con của v phải được chọn.
9. Chứng minh công thức dp1[v]=1+Σ min(dp0[u],dp1[u]).
10. Tính dp của các lá trong cây 7 đỉnh ở phần 6.
11. Tính dp0[1],dp1[1] và dp0[2],dp1[2].
12. Tính dp0[0]=2,dp1[0]=3 và truy vết {1,2}.
13. Tự tạo cây có nhiều vertex cover tối ưu khác nhau.
14. Thay đổi tie-break khi dp0==dp1 và kiểm kích thước optimum không đổi.
15. Viết trình duyệt lặp tránh stack overflow trên cây đường dài.
16. Chứng minh đồ thị vô hướng đơn liên thông có n−1 cạnh là cây.
17. Tạo phản ví dụ m=n−1 nhưng đồ thị không liên thông.
18. Thêm cạnh (3,5) vào cây nhị phân; giải thích vì sao DP cũ có thể cho tập không phủ cạnh đó.
19. Viết predicate kiểm một tập đỉnh có phủ mọi cạnh hay không.
20. Viết brute force 2^n để tìm optimum khi n≤20.
21. Đối chiếu Tree DP với brute force trên mọi cây n=4.
22. Mã hóa/giải mã chuỗi Prüfer để sinh cây có nhãn n=6.
23. Giải thích tại sao có 1.296 cây có nhãn n=6 và 1.442 cây cho n=1..6.
24. Mở rộng tree solver thành forest solver bằng duyệt các thành phần.
25. Mở rộng dp1[v] cho trọng số w[v] trên cây.
26. Giải thích cách dùng matching để giải min vertex cover trên đồ thị hai phía.
27. Cho một đồ thị chu trình lẻ, giải thích vì sao không hai phía.
28. Biến một mệnh đề (a∨b) thành hai cung kéo theo.
29. Giải thích điều kiện SCC cho biết 2-SAT vô nghiệm.
30. Tìm một phép gán làm `(x∨y∨z)` đúng nhưng `(x∨y)` sai.
31. Viết DP longest path cho DAG từ một nguồn cho trước.
32. Tạo đồ thị có hướng chứa chu trình và kiểm thuật toán topo phải từ chối.
33. Giải thích tại sao O(nS) cho Subset Sum là pseudo-polynomial.
34. Dùng Subset Sum với các số không âm và mục tiêu S nhỏ; giải thích vòng duyệt giảm.
35. Thiết kế phản ví dụ duyệt tổng tăng làm dùng một item nhiều lần.
36. Viết nhánh theo cạnh (u,v) cho Vertex Cover với tham số k.
37. Chứng minh mọi vertex cover phải chứa u hoặc v với cạnh (u,v).
38. Phân tích cây tìm kiếm O(2^k) khi mỗi nhánh giảm k một đơn vị.
39. Đề xuất hybrid solver: cây, hai phía, n nhỏ, k nhỏ, còn lại từ chối hoặc dùng solver tổng quát.
40. Phân biệt “đầu vào không được hỗ trợ” với “không tồn tại nghiệm”.
41. Thiết kế kiểm thử đường 100.000 đỉnh cho thuật toán không đệ quy.
42. Kiểm thử tính đúng của tập vertex cover trả về và so với optimum trên n nhỏ.

## 20. Checklist và tổng kết

Trước khi khai thác một trường hợp đặc biệt, hãy trả lời:

- Bài toán đang yêu cầu **quyết định, tìm một nghiệm, hay tối ưu**?
- Độ khó tổng quát được phát biểu chính xác là gì? Có nhầm NP-hard và NP-complete không?
- Đầu vào có cấu trúc được đề **hứa bảo đảm** hay phải tự nhận diện?
- Điều kiện đặc biệt là **cây, rừng, DAG, bipartite, 2-SAT, tổng nhỏ hay tham số k nhỏ**?
- Có chứng minh thuật toán chuyên biệt đúng trên **mọi input thuộc lớp đó**?
- Có làm mất cạnh/mệnh đề/điều kiện khi “đơn giản hóa” input không?
- Nếu dùng DP, trạng thái có ghi đủ tương tác giữa các phần con không?
- Nếu trả tập nghiệm, đã truy vết và kiểm tính hợp lệ độc lập chưa?
- Runtime có tính chi phí nhận diện, chuẩn bị dữ liệu và ghép kết quả không?
- Đã phân biệt đa thức theo input bits, giả đa thức và FPT chưa?
- Nếu input không thuộc lớp đặc biệt, có **fallback đúng hoặc thông báo không hỗ trợ**?
- Đã test ca nhỏ bằng brute force và ca lớn theo cấu trúc xấu nhất chưa?
- Có tránh gọi xấp xỉ là tối ưu khi đề đòi nghiệm exact không?

**Kết luận:** Độ khó của một bài toán phụ thuộc vào **miền input và mục tiêu cần giải**, chứ không chỉ tên bài toán. Minimum Vertex Cover là NP-hard trên đồ thị tổng quát nhưng có lời giải DP **O(n)** trên cây:

~~~text
dp0[v] = SUM dp1[child]
dp1[v] = 1 + SUM min(dp0[child],dp1[child])
answer = min(dp0[root],dp1[root])
~~~

Tương tự, 2-SAT, longest path trên DAG, Subset Sum khi tổng nhỏ và Vertex Cover theo tham số k minh họa nhiều cách giảm độ khó nhờ **cấu trúc, miền trị số hoặc tham số**. Một lời giải đáng tin phải chứng minh điều kiện áp dụng, giữ nguyên ý nghĩa nghiệm, phân tích độ phức tạp đúng mô hình và kiểm thử độc lập; chỉ như vậy “khai thác trường hợp đặc biệt” mới là một **thuật toán hiệu quả và đúng**, không phải một mẹo tối ưu thiếu bảo đảm.
