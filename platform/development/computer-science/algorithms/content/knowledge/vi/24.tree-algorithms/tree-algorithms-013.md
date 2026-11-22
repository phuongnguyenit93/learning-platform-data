# Dựng cây ảo từ một tập đỉnh cần xử lý

**Cây ảo** (*virtual tree*, đôi khi gọi *auxiliary tree* hoặc *compressed tree of marked vertices*) là một cấu trúc nhỏ được dựng từ một **tập đỉnh được đánh dấu** trên một **cây gốc tĩnh** đã tiền xử lý. Thay vì chạy thuật toán trên toàn bộ N đỉnh của cây cho **mỗi truy vấn**, ta chỉ giữ các đỉnh quan trọng và **những LCA cần thiết để nối chúng**. Các đường dài giữa hai đỉnh được giữ lại được **nén thành một cạnh ảo**, kèm độ dài (hoặc tổng trọng số) của đoạn đường gốc.

Nếu mỗi truy vấn chỉ chứa K đỉnh cần xử lý, cây ảo thường có **không quá 2K−1 đỉnh** (với K là số đỉnh đánh dấu **phân biệt** và K≥1), bất kể N lớn đến đâu. Điều này mở ra cách giải hiệu quả cho nhiều truy vấn mà chỉ một lượng nhỏ đỉnh trong mỗi truy vấn thật sự liên quan.

Ý tưởng trung tâm:

1. Tiền xử lý cây gốc bằng DFS để có **thứ tự vào `tin`**, **thời điểm ra `tout`**, **độ sâu `depth`** và cấu trúc trả lời **LCA**.
2. Với một truy vấn, **loại đỉnh trùng**, sắp các đỉnh đánh dấu theo **`tin` tăng dần**.
3. Thêm **LCA của từng cặp đỉnh đánh dấu liên tiếp** trong thứ tự đó. Đây là cách lấy đủ đỉnh phân nhánh cần thiết mà không phải tính LCA của mọi cặp.
4. Sắp và loại trùng lần nữa, rồi dùng **stack tổ tiên** để nối mỗi đỉnh vào **tổ tiên gần nhất cũng có mặt trong tập giữ lại**.
5. Trọng số/độ dài của cạnh ảo từ tổ tiên p xuống v là **`depth[v] - depth[p]`** khi mỗi cạnh gốc có độ dài 1; nếu cây có trọng số, dùng hiệu **tổng trọng số từ gốc**.

Bài học giải thích khi nào nên dùng cây ảo, hai bất biến quan trọng nhất, vì sao số đỉnh chỉ O(K), chứng minh thuật toán thêm LCA liên tiếp, xây stack, tính toán trên cây ảo, độ phức tạp và một chương trình **Java 17+ chạy độc lập**. Ví dụ bao gồm truy vấn có đỉnh trùng, truy vấn một đỉnh, tập rỗng và rễ cây ảo khác rễ cây gốc.

## 1. Bài toán gốc và động cơ nén cây

Cho cây vô hướng liên thông gồm N đỉnh, chọn một gốc cố định r. Cây có đúng N−1 cạnh, không chu trình và giữa hai đỉnh bất kỳ tồn tại **đúng một đường đơn**.

Mỗi truy vấn cung cấp một tập đỉnh quan trọng:

\[
S=\{v_1,v_2,\dots,v_K\}.
\]

Ta có thể cần:

- Độ dài **cây con nhỏ nhất theo bao hàm cạnh** nối tất cả đỉnh trong S.
- Tổng khoảng cách giữa **mọi cặp đỉnh** thuộc S.
- Một bài **DP trên cây** mà chỉ những đỉnh S tạo sự kiện/giá trị đầu vào.
- Truy vấn các nút đánh dấu/nguồn đặc biệt mà phần lớn cây gốc không liên quan tới câu trả lời.
- Một cấu trúc chỉ gồm các điểm gặp nhau của những đường đi giữa đỉnh đánh dấu.

Nếu mỗi truy vấn DFS toàn cây O(N), Q truy vấn có thể cần O(QN), dù K nhỏ. Ví dụ N=200.000, có hàng chục nghìn truy vấn mỗi truy vấn chỉ chứa 5–20 đỉnh, quét N ở mỗi truy vấn là không hợp lý.

**Cây ảo** tập trung vào đúng các đỉnh S và các **điểm hợp lưu** cần thiết. Các đỉnh có bậc 2 nằm trên những đoạn đường không chứa đỉnh quan trọng được loại khỏi biểu diễn và thay bằng một cạnh có độ dài đúng với đường đã nén.

Cây ảo không thay đổi cây gốc. Nó là **một cây truy vấn tạm thời**, được dựng lại theo tập S của từng truy vấn.

### Phân biệt với các khái niệm dễ nhầm

- **Cây ảo:** cây nén giữ các đỉnh đánh dấu và LCA cần thiết, duy trì đường tổ tiên và khoảng cách giữa các đỉnh giữ lại.
- **Cây bao trùm nhỏ nhất (MST):** chọn cạnh để nối mọi đỉnh và giảm tổng trọng số trên **đồ thị có thể có chu trình**. Cây ảo không chạy Kruskal/Prim để chọn cạnh MST.
- **Cây đường đi ngắn nhất:** cây cha theo các đường ngắn nhất từ nguồn trên graph tổng quát. Cây ảo bắt đầu từ **một cây đã có**; đường giữa hai đỉnh trong cây gốc đã là duy nhất.
- **Thu gọn cây tùy tiện:** nén cạnh sai có thể làm mất độ dài đường đi hoặc mất thông tin về đỉnh đánh dấu bên trong một đoạn.
- **Cây con cảm sinh bởi S:** chỉ lấy các cạnh gốc có cả hai đầu trong S thường tạo graph rời rạc. Cây ảo **có thể thêm LCA không thuộc S** và biểu diễn cả đường dài bằng cạnh nén.

## 2. Mục tiêu chính xác: giữ gì và bỏ gì?

Với một tập S không rỗng, xét **hợp của các đường đi duy nhất** giữa những cặp đỉnh trong S. Hợp này là một cây con nhỏ nhất theo quan hệ **bao hàm cạnh** chứa mọi đỉnh S. Có thể gọi đó là *minimal connecting subtree* hoặc *Steiner subtree trên một cây*.

Trong cây gốc, các đỉnh quan trọng thuộc hai kiểu:

1. **Terminal / marked vertex**: đỉnh xuất hiện trong truy vấn S.
2. **Branching vertex**: một **LCA** nằm trên các đường nối các terminal, cần được giữ để biểu diễn chỗ nhiều nhánh gặp nhau.

Các đỉnh còn lại chỉ là điểm trung gian trên một đường đơn, không cần xuất thành từng cạnh nếu mục đích của bài chỉ phụ thuộc **độ dài**, **tổng trọng số**, hoặc các phép tổng hợp có thể đưa lên cạnh nén.

Cây ảo được gốc hóa theo **LCA của tất cả các terminal** (theo gốc r của cây gốc). Rễ cây ảo **không nhất thiết là r** và cũng **không nhất thiết là một terminal**.

### Những thông tin bắt buộc được bảo toàn

- Mọi đỉnh được đánh dấu **đều tồn tại** trong cây ảo.
- Mỗi cạnh ảo `p→v` biểu thị **đường duy nhất đi xuống** từ tổ tiên p đến hậu duệ v trong cây gốc.
- Tổng độ dài các cạnh ảo trên đường giữa hai terminal bằng **khoảng cách của hai terminal trong cây gốc**.
- Quan hệ tổ tiên của các đỉnh được giữ lại không bị thay đổi.
- Những điểm phân nhánh cần cho đường nối các terminal được giữ lại bằng LCA.

**Không được coi cạnh ảo là một cạnh thật có trong input.** Ví dụ cạnh ảo `1→10(2)` có thể biểu diễn hai cạnh gốc `1–5` và `5–10`. Nếu bài yêu cầu truy cập từng cạnh gốc hoặc tìm một đỉnh trung gian cụ thể, cần sử dụng thêm dữ liệu của cây gốc chứ không chỉ danh sách cạnh nén.

## 3. Ví dụ cây gốc 16 đỉnh

Xét cây có gốc **0**, đỉnh `0..15`:

~~~text
0
├── 1
│   ├── 4
│   │   ├── 8
│   │   └── 9
│   └── 5
│       └── 10
├── 2
│   ├── 6
│   │   ├── 11
│   │   └── 12
│   └── 7
│       └── 13
└── 3
    └── 14
        └── 15
~~~

Các cạnh vô hướng:

~~~text
0-1, 0-2, 0-3,
1-4, 1-5,
4-8, 4-9,
5-10,
2-6, 2-7,
6-11, 6-12,
7-13,
3-14, 14-15
~~~

Ta xét một truy vấn đánh dấu:

\[
S=\{8,9,10,11,13,15\},\qquad K=6.
\]

Đây là sáu lá rải trên các nhánh khác nhau. Nếu chỉ giữ chúng và nối trực tiếp theo ID, ta không thể biết hai nhánh 8/9 gặp nhau ở đâu hoặc vì sao khoảng cách 8→15 bằng 6.

### Cây con nối S trước khi nén

Hợp tất cả các đường giữa terminal phải giữ:

~~~text
0,1,2,3,4,5,6,7,8,9,10,11,13,14,15
~~~

Đỉnh 12 không nằm trên đường giữa bất cứ hai terminal nào nên được bỏ. Các đỉnh 3,5,6,7,14 là những điểm trung gian có thể nén trên từng đoạn, vì không phải terminal hoặc điểm phân nhánh của cây tối tiểu trong truy vấn này.

### Cây ảo sau khi nén

~~~text
0
├── 1 (1 cạnh)
│   ├── 4 (1)
│   │   ├── 8 (1)
│   │   └── 9 (1)
│   └── 10 (2: 1-5-10)
├── 2 (1)
│   ├── 11 (2: 2-6-11)
│   └── 13 (2: 2-7-13)
└── 15 (3: 0-3-14-15)
~~~

Cây ảo có **10 đỉnh**:

~~~text
[0,1,4,8,9,10,2,11,13,15]
~~~

Trong đó **6 terminal** là 8,9,10,11,13,15; **4 đỉnh LCA thêm vào** là 0,1,2,4. Cây ảo có 9 cạnh nén, nhưng tổng độ dài của các cạnh nén là:

\[
1+1+1+1+2+1+2+2+3=\boxed{14}.
\]

Cây con thật nối tất cả terminal trong cây gốc có **14 cạnh**. Tất cả các đường đi giữa terminal vẫn có đúng độ dài ban đầu.

### Đừng nhầm hai con số 9 và 14

- **9** là số cạnh của **cây ảo 10 đỉnh**: \(10-1=9\).
- **14** là tổng **độ dài các cạnh ảo**, cũng là số cạnh gốc thuộc cây con tối tiểu nối S.

Nếu yêu cầu đếm số cạnh gốc phải giữ để nối S, câu trả lời là **14**, không phải 9.

## 4. Tiền xử lý cây gốc: root, depth, tin/tout, LCA

Ta phải chọn một **gốc cố định r** cho cây gốc. Với ví dụ chọn r=0.

Trước khi trả lời bất kỳ truy vấn tập S nào, chạy DFS để tính:

| Dữ liệu | Ý nghĩa |
|---|---|
| `depth[u]` | Số cạnh từ r tới u |
| `tin[u]` | Thời điểm DFS lần đầu vào u |
| `tout[u]` | Thời điểm DFS rời u, sau khi xong toàn bộ cây con |
| `up[j][u]` | Tổ tiên cách \(2^j\) cạnh của u theo gốc cố định, với tổ tiên của r quy ước là r |
| `LCA(u,v)` | Tổ tiên chung gần nhất của u,v |
| `isAncestor(u,v)` | u có phải tổ tiên (có thể bằng v) của v không? |

### Điều kiện tổ tiên bằng tin/tout

Khi cấp phát timestamp **một lần ở mỗi sự kiện vào và ra**, ta có:

\[
\boxed{
ancestor(u,v)
\iff tin[u]\le tin[v]\ \text{và}\ tout[v]\le tout[u].
}
\]

Các khoảng **`[tin[u],tout[u]]`** lồng nhau đúng theo cấu trúc cây con: khoảng của con nằm trọn trong khoảng của cha, còn hai cây con khác nhánh không lồng vào nhau.

Ví dụ với cây 16 đỉnh và thứ tự hàng xóm như phần 3, thứ tự DFS *preorder* là:

~~~text
[0,1,4,8,9,5,10,2,6,11,12,7,13,3,14,15]
~~~

Timestamp khi vào từng đỉnh theo ID:

~~~text
tin = [0,1,13,25,2,8,14,20,3,5,9,15,17,21,26,27]
~~~

Không được kết luận u là tổ tiên của v chỉ vì `tin[u]<tin[v]`: u có thể nằm ở một nhánh đã hoàn tất trước khi DFS đến v. Cần thêm **tout** hoặc một biểu diễn khoảng cây con tương đương.

### LCA bằng Binary Lifting

Chọn:

\[
up[0][v]=parent[v],\qquad
up[j][v]=up[j-1][up[j-1][v]].
\]

Gốc r dùng `up[j][r]=r` để không truy cập chỉ số -1.

Muốn tính LCA(u,v):

1. Nếu u là tổ tiên v, trả u. Nếu v là tổ tiên u, trả v.
2. Đi j từ cấp cao nhất về 0, thử nhảy u lên `up[j][u]`.
3. Chỉ thực hiện bước nhảy nếu tổ tiên thử **vẫn chưa là tổ tiên của v**.
4. Sau vòng lặp, `up[0][u]` chính là LCA.

Mỗi truy vấn LCA tốn **O(log N)**, tiền xử lý **O(N log N)** bộ nhớ/thời gian.

Có thể dùng **Euler Tour + RMQ** để trả LCA O(1) sau tiền xử lý O(N log N) bằng Sparse Table, hoặc phương pháp RMQ chuyên dụng hơn. Khi đó bước dựng cây ảo có thể nhanh hơn theo K, nhưng cấu trúc chính của cây ảo **không đổi**.

## 5. Bước 1: sắp tập terminal theo thứ tự tin

Với truy vấn:

~~~text
S = {15,8,11,9,13,10}
~~~

Thứ tự input có thể tùy ý. Thuật toán bắt đầu bằng việc **kiểm tra ID hợp lệ, loại trùng và sắp theo tin tăng dần**:

~~~text
terminal = [8,9,10,11,13,15]
~~~

Ở cây 16 đỉnh, các timestamp là:

~~~text
tin[8]=3; tin[9]=5; tin[10]=9;
tin[11]=15; tin[13]=21; tin[15]=27
~~~

### Vì sao dùng DFS order?

Trong DFS preorder, các đỉnh của **mỗi cây con** xuất hiện trong một khoảng liên tiếp. Những terminal thuộc một nhánh sâu thường đứng cạnh nhau trước khi sang nhánh khác. Tính chất này cho phép phát hiện các **điểm phân nhánh** chỉ bằng LCA của các cặp terminal **liền kề**.

Sắp theo **ID đỉnh** không có bảo đảm tương tự. ID 8,9,10 có thể thuộc bất kỳ các nhánh nào nếu cách đánh số khác; chỉ thứ tự DFS bảo đảm cấu trúc cây con trở thành các khoảng.

### Tập hay danh sách?

Nếu truy vấn là tập, đỉnh lặp phải được **loại trùng** trước khi tính K. Ví dụ `[8,9,9,10]` có **ba terminal phân biệt**, không phải bốn. Khi dùng công thức đếm số cặp terminal hoặc ràng buộc \(2K-1\), K phải là số lượng **phân biệt**.

Nếu đề bài thực sự coi mỗi lần xuất hiện là **một vật/nhãn riêng** đặt ở cùng một đỉnh, phải phân biệt **số vật** với **số vị trí đỉnh**: cây ảo vẫn dựng từ vị trí đỉnh phân biệt, nhưng DP có thể cần lưu **bội số/khối lượng** thay vì boolean terminal. Mã trong bài mặc định mỗi ID chỉ là một terminal, không đếm bội số.

## 6. Bước 2: thêm LCA của các terminal đứng cạnh nhau

Với danh sách `terminal=[s0,s1,...,s(K−1)]` đã sắp theo tin, tạo tập bổ sung:

\[
L=\{LCA(s_i,s_{i+1})\mid 0\le i<K-1\}.
\]

Sau đó:

\[
U=S\cup L.
\]

**Không tính tất cả \(\binom K2\) cặp LCA**: chỉ cần **K−1** cặp liền kề.

Với ví dụ:

| Cặp terminal theo tin | LCA |
|---|---:|
| 8,9 | 4 |
| 9,10 | 1 |
| 10,11 | 0 |
| 11,13 | 2 |
| 13,15 | 0 |

Sau khi thêm, sắp theo tin và loại trùng:

~~~text
U = [0,1,4,8,9,10,2,11,13,15]
~~~

Rễ ảo là **0**. Các đỉnh 4,1,0,2 không được đánh dấu ban đầu, nhưng chúng cần để giữ chỗ các nhánh gặp nhau.

### Tại sao LCA của cặp liền kề là đủ?

Những terminal trong một cây con tạo thành **một đoạn liên tiếp theo DFS order**. Xét một đỉnh x là điểm phân nhánh cần thiết của các đường nối S, tức có terminal ở ít nhất hai nhánh con khác nhau của x, hoặc x tự là terminal quan trọng.

Nếu hai nhánh con của x đều chứa terminal, khi xem các terminal đã sắp theo tin, sẽ có **một ranh giới giữa hai nhóm nhánh**: terminal cuối của nhóm nhánh trước đứng ngay trước terminal đầu của nhóm nhánh sau. LCA của hai terminal liền kề ấy chính là **x**. Vì vậy mọi điểm phân nhánh quan trọng có mặt trong S hoặc trong danh sách L.

Những LCA giữa **các cặp không liền kề** không thêm một điểm phân nhánh thiết yếu mới. Có thể có cùng LCA xuất hiện từ nhiều cặp, nên chỉ cần loại trùng sau khi thêm.

Đây là lý do **LCA closure theo DFS-order neighbor** là đủ để dựng cây ảo chuẩn.

### Cận số đỉnh ảo

Với K terminal phân biệt:

- Ban đầu có K đỉnh.
- Xét đúng K−1 cặp liền kề.
- Mỗi cặp tạo nhiều nhất một LCA mới.

Do đó:

\[
\boxed{|U|\le K+(K-1)=2K-1\qquad(K\ge1).}
\]

Khi K=1, không thêm LCA, cây ảo có 1 đỉnh. Khi K=0, cây ảo rỗng theo quy ước của mã.

**Đây là cận trên, không phải lúc nào cũng đạt.** Nhiều LCA có thể trùng nhau hoặc đã thuộc S; ví dụ tất cả terminal cùng nằm trên một đường tổ tiên thì không cần thêm đỉnh phân nhánh nào.

## 7. Bước 3: dựng cạnh ảo bằng stack tổ tiên

Sau bước 2, danh sách U đã **sắp theo tin tăng dần**. Vì tập này chứa đủ các LCA cần thiết, mỗi đỉnh (trừ rễ ảo) có một **tổ tiên gần nhất cũng thuộc U**. Ta nối đỉnh đó vào tổ tiên gần nhất ấy.

Thuật toán stack:

~~~text
buildVirtualTree(terminals):
    unique terminals sorted by tin
    if terminals empty:
        return empty tree

    nodes = copy(terminals)
    for i = 0 .. terminals.size-2:
        nodes.add(LCA(terminals[i], terminals[i+1]))
    sort nodes by tin, remove duplicates

    stack = empty
    virtualEdges = empty

    for v in nodes:
        while stack not empty
              and not isAncestor(stack.top, v):
            stack.pop()

        if stack is empty:
            virtualRoot = v
        else:
            p = stack.top
            virtualEdges.add(p, v, depth[v]-depth[p])

        stack.push(v)

    return virtualRoot, nodes, virtualEdges, terminals
~~~

Stack chứa **chuỗi tổ tiên đang mở** trong những đỉnh đã giữ của cây ảo. Khi gặp v thuộc một nhánh mới, những đỉnh ở nhánh cũ không còn là tổ tiên của v nên được pop. Đỉnh còn lại trên đỉnh stack là **tổ tiên gần nhất trong U** của v.

### Mô phỏng trên U của ví dụ

~~~text
U = [0,1,4,8,9,10,2,11,13,15]
~~~

| Đỉnh mới v | Stack sau khi bỏ các đỉnh không còn là tổ tiên | Cạnh ảo thêm vào | Độ dài |
|---:|---|---|---:|
| 0 | [] | Gốc ảo 0 | — |
| 1 | [0] | 0→1 | 1 |
| 4 | [0,1] | 1→4 | 1 |
| 8 | [0,1,4] | 4→8 | 1 |
| 9 | [0,1,4] | 4→9 | 1 |
| 10 | [0,1] | 1→10 | 2 |
| 2 | [0] | 0→2 | 1 |
| 11 | [0,2] | 2→11 | 2 |
| 13 | [0,2] | 2→13 | 2 |
| 15 | [0] | 0→15 | 3 |

Sau mỗi dòng, thuật toán **push v**. Các cạnh ảo theo thứ tự sinh là:

~~~text
[0->1(1), 1->4(1), 4->8(1), 4->9(1), 1->10(2),
 0->2(1), 2->11(2), 2->13(2), 0->15(3)]
~~~

Các cạnh được định hướng **từ tổ tiên xuống hậu duệ** theo gốc cố định của cây gốc. Tập cạnh gốc vốn vô hướng; chiều cạnh ảo chỉ phản ánh quan hệ tổ tiên khi chạy DP.

### Bất biến quan trọng khi quét U

Trước khi xử lý một đỉnh v mới:

- Stack là một đường gồm các đỉnh U đã gặp còn có thể là tổ tiên của những đỉnh sắp tới.
- Các đỉnh bị pop không thể là cha ảo của v vì **không phải tổ tiên của v**.
- Nếu v không phải đỉnh đầu tiên, luôn còn ít nhất một tổ tiên trong stack, vì **LCA chung của các terminal đã nằm trong U** và mọi điểm phân nhánh thiết yếu đã được bổ sung.
- Đỉnh trên cùng còn lại là **tổ tiên sâu nhất trong U** của v.
- Mỗi v khác rễ được gắn đúng một cha, và cha có độ sâu nhỏ hơn nên không thể tạo chu trình.

Từ đó, với M=|U| đỉnh, tạo đúng **M−1 cạnh ảo** và được một cây liên thông.

## 8. Cách tính độ dài / trọng số của cạnh nén

Với cạnh ảo `p→v`, p là **tổ tiên** của v trong cây gốc. Trên cây không trọng số:

\[
\boxed{len(p,v)=depth[v]-depth[p].}
\]

Ví dụ:

- `1→10`: đường gốc 1–5–10, nên \(len=3-1=2\).
- `2→11`: đường gốc 2–6–11, nên \(len=3-1=2\).
- `0→15`: đường gốc 0–3–14–15, nên \(len=3-0=3\).

Mỗi cạnh ảo có độ dài **ít nhất 1**, vì U đã loại trùng và v khác p.

Nếu cây gốc có trọng số cạnh \(w\), tiền xử lý:

\[
rootSum[x]=\sum_{e\text{ trên đường }r\leadsto x} w(e).
\]

Khi p là tổ tiên của v, trọng số nén đúng là:

\[
\boxed{weight(p,v)=rootSum[v]-rootSum[p].}
\]

**Không dùng \(depth[v]-depth[p]\) cho trọng số tùy ý**, vì depth thường chỉ đếm cạnh. Nếu cây có cạnh âm, hiệu rootSum vẫn biểu diễn đúng **tổng theo đường duy nhất**; nhưng khi nói “cây con có tổng trọng số nhỏ nhất” phải làm rõ mục tiêu: *cây con tối thiểu theo bao hàm cạnh nối các terminal* là duy nhất, còn nếu cho phép thêm nhánh âm không cần thiết để giảm tổng tiền, nghiệm tối ưu theo trọng số có thể khác.

### Bảo toàn khoảng cách

Với hai đỉnh a,b thuộc U, đường đi duy nhất giữa chúng trong cây ảo gồm các cạnh nén của những đoạn **không chồng nhau** trên đường a↔b của cây gốc. Bởi vậy:

\[
\boxed{dist_{virtual}(a,b)=dist_{original}(a,b)}
\]

khi mỗi cạnh ảo được gán đúng độ dài/tổng trọng số của đoạn đường đã nén.

Vì tất cả terminal đều thuộc U, khoảng cách giữa **mọi cặp terminal** được bảo toàn.

Cây ảo **không nhất thiết giữ từng đỉnh nằm giữa**: nếu cần xuất danh sách toàn bộ đỉnh trên đường gốc, phải triển khai giải nén bằng thông tin cha/LCA của cây gốc.

## 9. Hai truy vấn: rễ ảo có thể không phải rễ gốc

**Truy vấn lớn:**

~~~text
S = {8,9,10,11,13,15}
Rễ cây gốc = 0
Rễ cây ảo = 0
Đỉnh ảo = [0,1,4,8,9,10,2,11,13,15]
~~~

**Truy vấn nhỏ có dữ liệu đầu vào trùng:**

~~~text
input = [10,9,8,9]
terminal sau loại trùng theo tin = [8,9,10]
LCA(8,9)=4
LCA(9,10)=1

U = [1,4,8,9,10]
rễ ảo = 1
cạnh ảo = [1->4(1),4->8(1),4->9(1),1->10(2)]
~~~

Ở truy vấn thứ hai, **0 không cần xuất hiện** trong cây ảo: mọi đỉnh được chọn đều thuộc cây con của 1. Nếu bắt buộc thêm 0 vào mọi truy vấn, số đỉnh vẫn O(K+1) nhưng kết quả không còn là **cây nén tối thiểu**; thuật toán DP có thể phải xử lý một đoạn dư, và không đúng hợp đồng bài học đang xét.

Tổng độ dài cạnh ảo của truy vấn nhỏ:

\[
1+1+1+2=5.
\]

Khoảng cách các terminal:

~~~text
dist(8,9)  = 2
dist(8,10) = 4
dist(9,10) = 4
Tổng ba cặp = 10
~~~

**Truy vấn một terminal** `{12}`: U chỉ có đỉnh 12, rễ ảo=12, không cạnh và tổng độ dài 0.

**Truy vấn không terminal** `{}`: demo trả **cây ảo rỗng** với rễ=-1, không cạnh. ID -1 là **giá trị báo không tồn tại**, không phải một đỉnh gốc hợp lệ.

## 10. Một ứng dụng: số cạnh cây con tối thiểu nối terminal

Với cây gốc không trọng số và mỗi cạnh có chi phí 1, muốn đếm **số cạnh gốc** nằm trong cây con nhỏ nhất theo bao hàm cạnh chứa mọi terminal S, chỉ cần:

\[
\boxed{\text{answer}=\sum_{(p,v)\in E_{virtual}} (depth[v]-depth[p]).}
\]

Trong ví dụ lớn, kết quả là **14**. Với một terminal, kết quả 0; với tập rỗng, quy ước cũng là 0.

Vì sao được cộng từng cạnh nén đúng một lần?

- Mỗi cạnh ảo tương ứng với một đoạn đường gốc từ tổ tiên được giữ tới hậu duệ được giữ.
- Cây ảo giữ tất cả điểm nhánh và các terminal, nên hai đoạn nén của **hai cạnh ảo khác nhau** không có cạnh gốc chung.
- Hợp các đoạn đó đúng là cây con nhỏ nhất nối toàn bộ terminal.

Vì thế tổng độ dài các cạnh nén bằng **số cạnh gốc của hợp đường**. Không cần quay về cây N đỉnh để đếm cạnh ở mỗi truy vấn.

### Trường hợp trọng số cạnh

Thay `depth` bằng `rootSum` nếu muốn **tổng trọng số của đúng cây con nối tối thiểu theo bao hàm cạnh**:

\[
\sum_{(p,v)\in E_{virtual}}(rootSum[v]-rootSum[p]).
\]

Nếu trọng số không âm, cây con theo bao hàm cạnh cũng có tổng trọng số nhỏ nhất trong các cây con liên thông chứa S (việc thêm cạnh không âm không làm giảm tổng). Nếu có trọng số âm, **bài tối ưu tổng trọng số cho phép thêm nhánh** là một bài khác; chỉ dùng công thức này khi mục tiêu thực sự là tổng trọng số **trên hợp các đường giữa terminal**.

## 11. Một ứng dụng nâng cao: tổng khoảng cách giữa mọi cặp terminal

Giả sử truy vấn chứa K terminal phân biệt và yêu cầu:

\[
Ans=\sum_{\{a,b\}\subseteq S} dist(a,b).
\]

Nếu tính riêng LCA/distance cho mọi cặp, ta cần \(O(K^2)\) phép truy vấn, có thể quá chậm với K lớn. Cây ảo cho phép xử lý bằng **DP một lượt từ lá lên** trong O(|U|)=O(K) sau khi dựng.

Gốc hóa cây ảo. Với mỗi đỉnh v, đặt `cnt[v]` là số terminal trong **cây con ảo của v** (tính cả v nếu v là terminal). Xét một cạnh ảo p→v có độ dài L. Có đúng:

\[
cnt[v]\cdot(K-cnt[v])
\]

**cặp terminal không thứ tự** có hai đầu nằm ở **hai phía của cạnh này**. Đường nối một cặp như thế bắt buộc qua đoạn đường gốc mà cạnh nén biểu diễn, nên cạnh đóng góp:

\[
\boxed{L\cdot cnt[v]\cdot(K-cnt[v])}
\]

vào tổng khoảng cách tất cả cặp. Cộng mọi cạnh ảo:

\[
\boxed{
Ans=\sum_{(p,v)\in E_{virtual}}
len(p,v)\,cnt[v]\,(K-cnt[v]).
}
\]

**Không chia đôi** kết quả nếu đã dùng công thức cặp **không thứ tự** qua cạnh như trên. Cặp (a,b) được đếm đúng một lần tại mỗi cạnh trên đường của nó; tổng theo cạnh chính là tổng theo cặp.

### Mô phỏng DP trên cây ảo lớn

S có 6 terminal: 8,9,10,11,13,15. Ta có:

| Cạnh ảo | len | Số terminal dưới con cnt | Số cặp qua cạnh | Đóng góp |
|---|---:|---:|---:|---:|
| 0→1 | 1 | 3 | 3·3=9 | 9 |
| 1→4 | 1 | 2 | 2·4=8 | 8 |
| 4→8 | 1 | 1 | 1·5=5 | 5 |
| 4→9 | 1 | 1 | 5 | 5 |
| 1→10 | 2 | 1 | 5 | 10 |
| 0→2 | 1 | 2 | 8 | 8 |
| 2→11 | 2 | 1 | 5 | 10 |
| 2→13 | 2 | 1 | 5 | 10 |
| 0→15 | 3 | 1 | 5 | 15 |
| **Tổng** | | | | **80** |

Nếu cộng trực tiếp 15 khoảng cách giữa 6 terminal, ta cũng được **80**. Tuy nhiên DP trên cây ảo vẫn O(K) bất kể số cặp tăng theo \(K^2\).

### Thứ tự xử lý DP

Nếu các cạnh ảo được sinh theo **thứ tự DFS preorder của các đỉnh ảo**, mọi cạnh từ cha tới con xuất hiện **trước** các cạnh từ con tới hậu duệ. Vì thế có thể xử lý **danh sách cạnh theo thứ tự ngược** để tổng hợp cnt từ lá lên.

Một cách tổng quát hơn là dựng adjacency list của cây ảo rồi thực hiện DFS/postorder. Trong chương trình Java dưới đây, danh sách cạnh sinh khi quét U theo tin bảo đảm **cha luôn xuất hiện trước con**, nên xử lý cạnh đảo chiều là hợp lệ.

**Lưu ý overflow:** số cặp có thể tỷ lệ \(K^2\); nhân thêm độ dài có thể vượt `long` nếu N và K cực lớn. Mã dùng `Math.multiplyExact` và `Math.addExact` để **ném lỗi rõ ràng** thay vì nhận một tổng bị tràn.

## 12. Java 17+: tiền xử lý cây và dựng cây ảo từng truy vấn

Chương trình **VirtualTreeSubsetDemo.java** hoàn chỉnh dưới đây:

- Kiểm tra input là **cây vô hướng có N≥1 đỉnh và N−1 cạnh**, dùng DSU để từ chối chu trình, self-loop và cạnh không hợp lệ.
- Dùng DFS **lặp với stack frame** để tính `tin/tout`, `depth` và `up[j][v]`; không dựa vào call stack Java khi cây là một đường rất sâu.
- Tìm LCA bằng **Binary Lifting** O(log N).
- Với từng truy vấn, chỉ tạo những cấu trúc O(K) cần thiết: danh sách terminal đã loại trùng, danh sách LCA bổ sung, danh sách cạnh ảo và stack tổ tiên. **Không cấp phát mảng visited mới dài N cho mỗi truy vấn**.
- Cạnh ảo lưu **đỉnh cha, đỉnh con và độ dài đoạn nén**. Mỗi danh sách kết quả là bản sao không sửa được bằng `List.copyOf`.
- Xử lý tập rỗng, một đỉnh và ID terminal không hợp lệ.
- Minh họa tổng độ dài cây con nối terminal và **DP tính tổng khoảng cách giữa mọi cặp terminal**.

Lưu đúng tên tệp **VirtualTreeSubsetDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class VirtualTreeSubsetDemo {
    record VirtualEdge(int from, int to, int length) {
        @Override
        public String toString() {
            return from + "->" + to + "(" + length + ")";
        }
    }

    record VirtualTree(
        int root,
        List<Integer> nodes,
        List<Integer> terminals,
        List<VirtualEdge> edges
    ) {}

    static final class DSU {
        final int[] parent;
        final int[] size;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean unite(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]) {
                int tmp = a;
                a = b;
                b = tmp;
            }
            parent[b] = a;
            size[a] += size[b];
            return true;
        }
    }

    static final class Frame {
        final int vertex;
        final int parent;
        int nextNeighbor;

        Frame(int vertex, int parent) {
            this.vertex = vertex;
            this.parent = parent;
        }
    }

    static final class TreeToolkit {
        final int n;
        final int root;
        final int levels;
        final List<List<Integer>> graph;
        final int[][] up;
        final int[] depth;
        final int[] tin;
        final int[] tout;
        int timer = 0;

        TreeToolkit(int n, int[][] edges, int root) {
            if (n < 1) {
                throw new IllegalArgumentException("n must be positive");
            }
            if (root < 0 || root >= n) {
                throw new IllegalArgumentException("invalid root");
            }
            Objects.requireNonNull(edges, "edges");
            if (edges.length != n - 1) {
                throw new IllegalArgumentException("tree requires n-1 edges");
            }

            this.n = n;
            this.root = root;
            this.graph = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                graph.add(new ArrayList<>());
            }

            DSU dsu = new DSU(n);
            for (int[] edge : edges) {
                if (edge == null || edge.length != 2
                        || edge[0] < 0 || edge[0] >= n
                        || edge[1] < 0 || edge[1] >= n
                        || edge[0] == edge[1]) {
                    throw new IllegalArgumentException("invalid tree edge");
                }
                int u = edge[0];
                int v = edge[1];
                if (!dsu.unite(u, v)) {
                    throw new IllegalArgumentException(
                        "graph contains a cycle"
                    );
                }
                graph.get(u).add(v);
                graph.get(v).add(u);
            }

            int log = 1;
            while ((1L << log) <= n) {
                log++;
            }
            this.levels = log;
            this.up = new int[levels][n];
            this.depth = new int[n];
            this.tin = new int[n];
            this.tout = new int[n];
            Arrays.fill(tin, -1);

            preprocess();
        }

        // Entry/exit timestamps and binary lifting without recursion.
        private void preprocess() {
            ArrayDeque<Frame> stack = new ArrayDeque<>();
            tin[root] = timer++;
            up[0][root] = root;
            for (int j = 1; j < levels; j++) {
                up[j][root] = root;
            }
            stack.push(new Frame(root, -1));

            while (!stack.isEmpty()) {
                Frame frame = stack.peek();
                List<Integer> neighbors = graph.get(frame.vertex);

                if (frame.nextNeighbor == neighbors.size()) {
                    tout[frame.vertex] = timer++;
                    stack.pop();
                    continue;
                }

                int v = neighbors.get(frame.nextNeighbor++);
                if (v == frame.parent) {
                    continue;
                }
                if (tin[v] != -1) {
                    throw new IllegalStateException("cycle during DFS");
                }

                depth[v] = depth[frame.vertex] + 1;
                up[0][v] = frame.vertex;
                for (int j = 1; j < levels; j++) {
                    up[j][v] = up[j - 1][up[j - 1][v]];
                }

                tin[v] = timer++;
                stack.push(new Frame(v, frame.vertex));
            }
        }

        private void checkVertex(int v) {
            if (v < 0 || v >= n) {
                throw new IllegalArgumentException("invalid terminal");
            }
        }

        boolean isAncestor(int u, int v) {
            return tin[u] <= tin[v] && tout[v] <= tout[u];
        }

        int lca(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            if (isAncestor(u, v)) {
                return u;
            }
            if (isAncestor(v, u)) {
                return v;
            }

            for (int j = levels - 1; j >= 0; j--) {
                int candidate = up[j][u];
                if (!isAncestor(candidate, v)) {
                    u = candidate;
                }
            }
            return up[0][u];
        }

        long distance(int u, int v) {
            int ancestor = lca(u, v);
            return (long) depth[u] + depth[v]
                - 2L * depth[ancestor];
        }

        VirtualTree buildVirtualTree(int... requested) {
            Objects.requireNonNull(requested, "requested");
            if (requested.length == 0) {
                return new VirtualTree(
                    -1, List.of(), List.of(), List.of()
                );
            }

            List<Integer> sorted = new ArrayList<>();
            for (int v : requested) {
                checkVertex(v);
                sorted.add(v);
            }
            sorted.sort(Comparator.comparingInt(v -> tin[v]));

            List<Integer> terminals = new ArrayList<>();
            for (int v : sorted) {
                if (terminals.isEmpty()
                        || terminals.get(terminals.size() - 1) != v) {
                    terminals.add(v);
                }
            }

            List<Integer> allNodes = new ArrayList<>(terminals);
            for (int i = 0; i + 1 < terminals.size(); i++) {
                allNodes.add(lca(terminals.get(i), terminals.get(i + 1)));
            }
            allNodes.sort(Comparator.comparingInt(v -> tin[v]));

            List<Integer> nodes = new ArrayList<>();
            for (int v : allNodes) {
                if (nodes.isEmpty() || nodes.get(nodes.size() - 1) != v) {
                    nodes.add(v);
                }
            }

            ArrayDeque<Integer> stack = new ArrayDeque<>();
            List<VirtualEdge> virtualEdges = new ArrayList<>();

            for (int v : nodes) {
                while (!stack.isEmpty()
                        && !isAncestor(stack.peek(), v)) {
                    stack.pop();
                }
                if (!stack.isEmpty()) {
                    int p = stack.peek();
                    virtualEdges.add(
                        new VirtualEdge(p, v, depth[v] - depth[p])
                    );
                }
                stack.push(v);
            }

            return new VirtualTree(
                nodes.get(0),
                List.copyOf(nodes),
                List.copyOf(terminals),
                List.copyOf(virtualEdges)
            );
        }

        long steinerEdgeCount(VirtualTree tree) {
            long answer = 0L;
            for (VirtualEdge edge : tree.edges()) {
                answer = Math.addExact(answer, edge.length());
            }
            return answer;
        }

        long markedPairDistanceSum(VirtualTree tree) {
            int k = tree.terminals().size();
            if (k < 2) {
                return 0L;
            }

            Map<Integer, Long> count = new HashMap<>();
            for (int node : tree.nodes()) {
                count.put(node, 0L);
            }
            for (int terminal : tree.terminals()) {
                count.put(terminal, 1L);
            }

            long answer = 0L;
            // Each parent edge is created before descendant edges.
            for (int i = tree.edges().size() - 1; i >= 0; i--) {
                VirtualEdge edge = tree.edges().get(i);
                long c = count.get(edge.to());
                long pairs = Math.multiplyExact(c, (long) k - c);
                long contribution = Math.multiplyExact(
                    (long) edge.length(), pairs
                );
                answer = Math.addExact(answer, contribution);
                count.put(
                    edge.from(),
                    Math.addExact(count.get(edge.from()), c)
                );
            }
            return answer;
        }
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {0, 2}, {0, 3},
            {1, 4}, {1, 5},
            {4, 8}, {4, 9}, {5, 10},
            {2, 6}, {2, 7},
            {6, 11}, {6, 12}, {7, 13},
            {3, 14}, {14, 15}
        };

        TreeToolkit toolkit = new TreeToolkit(16, edges, 0);
        VirtualTree large = toolkit.buildVirtualTree(
            15, 8, 11, 9, 13, 10
        );

        System.out.println("DFS entry timestamps: "
            + Arrays.toString(toolkit.tin));
        System.out.println("Terminals (sorted): " + large.terminals());
        System.out.println("Virtual nodes: " + large.nodes());
        System.out.println("Virtual root: " + large.root());
        System.out.println("Virtual edges: " + large.edges());
        System.out.println("Virtual edge count: " + large.edges().size());
        System.out.println("Original Steiner subtree edge count: "
            + toolkit.steinerEdgeCount(large));
        System.out.println("Marked-pair distance sum: "
            + toolkit.markedPairDistanceSum(large));
        System.out.println("Distance(8,15): "
            + toolkit.distance(8, 15));
        System.out.println("Distance(11,13): "
            + toolkit.distance(11, 13));

        VirtualTree local = toolkit.buildVirtualTree(10, 9, 8, 9);
        System.out.println("Local terminals: " + local.terminals());
        System.out.println("Local root: " + local.root());
        System.out.println("Local edges: " + local.edges());
        System.out.println("Local pair sum: "
            + toolkit.markedPairDistanceSum(local));

        VirtualTree single = toolkit.buildVirtualTree(12);
        System.out.println("Singleton: root=" + single.root()
            + ", edges=" + single.edges());

        VirtualTree empty = toolkit.buildVirtualTree();
        System.out.println("Empty set: root=" + empty.root()
            + ", nodes=" + empty.nodes());

        try {
            toolkit.buildVirtualTree(16);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid terminal rejected: "
                + ex.getMessage());
        }

        try {
            new TreeToolkit(4, new int[][] {
                {0, 1}, {1, 2}, {2, 0}
            }, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Cyclic input rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac VirtualTreeSubsetDemo.java
java VirtualTreeSubsetDemo
~~~

**Stdout chính xác của ví dụ:**

~~~text
DFS entry timestamps: [0, 1, 13, 25, 2, 8, 14, 20, 3, 5, 9, 15, 17, 21, 26, 27]
Terminals (sorted): [8, 9, 10, 11, 13, 15]
Virtual nodes: [0, 1, 4, 8, 9, 10, 2, 11, 13, 15]
Virtual root: 0
Virtual edges: [0->1(1), 1->4(1), 4->8(1), 4->9(1), 1->10(2), 0->2(1), 2->11(2), 2->13(2), 0->15(3)]
Virtual edge count: 9
Original Steiner subtree edge count: 14
Marked-pair distance sum: 80
Distance(8,15): 6
Distance(11,13): 4
Local terminals: [8, 9, 10]
Local root: 1
Local edges: [1->4(1), 4->8(1), 4->9(1), 1->10(2)]
Local pair sum: 10
Singleton: root=12, edges=[]
Empty set: root=-1, nodes=[]
Invalid terminal rejected: invalid terminal
Cyclic input rejected: graph contains a cycle
~~~

### Đọc chương trình theo từng giai đoạn

**Tiền xử lý một lần.** `TreeToolkit` xác thực graph là cây bằng DSU và dựng danh sách kề vô hướng. `preprocess` dùng DFS stack frame, ghi `tin` khi vào và `tout` khi hoàn tất; đồng thời điền `depth` và bảng `up` ngay lúc khám phá từng đỉnh. Cách này tránh đệ quy sâu trên đường cây dài.

**Phân biệt gốc cây gốc và gốc cây ảo.** `TreeToolkit.root` là gốc cố định để tính ancestor/LCA. `VirtualTree.root` là LCA chung của terminal **trong một truy vấn**. Với tập `[8,9,10]`, rễ ảo là 1 dù gốc cây gốc vẫn là 0.

**Loại trùng terminal trước khi thêm LCA.** Danh sách `terminal` được sắp theo tin và không có phần tử trùng. Điều này bảo đảm kích thước O(K) và công thức `cnt*(K-cnt)` tính đúng số **cặp terminal phân biệt**.

**Chỉ thêm LCA liền kề.** Vòng `for (i+1<terminals.size())` thêm đúng K−1 LCA. Sau khi sắp/loại trùng lần hai, `nodes` là toàn bộ tập đỉnh ảo.

**Stack tổ tiên.** Mỗi v được xử lý một lần. Trong vòng `while`, đỉnh không còn là tổ tiên v bị pop. Nếu stack không rỗng, cha ảo là top và cạnh nén có độ dài `depth[v]-depth[p]`. Vì allNodes đã chứa đủ LCA, toàn bộ danh sách tạo **một cây**, không phải rừng.

**DP không quét N đỉnh mỗi truy vấn.** `markedPairDistanceSum` dùng `HashMap` chỉ cho các **đỉnh của cây ảo**. Nó đảo thứ tự các cạnh do build sinh để cộng số terminal từ con lên cha; mỗi cạnh đóng góp `len*c*(K-c)`. Việc không cấp phát/cụ thể hóa mảng dài N trên mỗi truy vấn rất quan trọng khi N lớn, K nhỏ và Q lớn.

**Kiểm tra số học.** Tổng khoảng cách có thể lớn; `Math.multiplyExact`/`Math.addExact` báo overflow thay vì trả kết quả `long` không đáng tin.

### API trả về và trạng thái giữa các truy vấn

`VirtualTree` chỉ gồm `root`, `nodes`, `terminals`, `edges`, các danh sách đã được `List.copyOf`. Không có trạng thái visited toàn graph bị sửa trên mỗi truy vấn. Hai lời gọi liên tiếp `buildVirtualTree(...)` không cần dọn danh sách cạnh ảo cũ.

Cấu trúc `TreeToolkit` vẫn giữ toàn bộ dữ liệu tiền xử lý của cây gốc. Nếu graph gốc thay đổi cạnh hoặc đổi gốc, **không tái sử dụng** toolkit cũ để suy ra LCA theo cây mới; phải dựng lại hoặc sử dụng thuật toán động phù hợp.

## 13. Chứng minh đúng: từ LCA closure đến cây nén

Có thể tách thành bốn bổ đề.

### 13.1. Mọi terminal được giữ lại

Ta bắt đầu U bằng toàn bộ tập terminal phân biệt. Bước thêm LCA chỉ bổ sung đỉnh; bước sắp/loại trùng không xóa phần tử khác nhau. Vậy mọi terminal đều thuộc U.

### 13.2. Tập U chứa các điểm phân nhánh cần thiết

Trong DFS preorder, tập terminal thuộc mỗi cây con liên tiếp theo thứ tự tin. Một điểm phân nhánh x cần thiết xuất hiện khi terminal nằm ở hai hay nhiều nhánh dưới x. Tại ranh giới giữa hai khối terminal của hai nhánh, có một cặp terminal **liền kề** với LCA đúng bằng x. Vì ta thêm LCA của mọi cặp liền kề, x thuộc U.

Nếu x tự là terminal thì x đã được giữ ngay từ đầu. Vì vậy không mất điểm terminal hoặc điểm phân nhánh cần thiết khi nén các đường.

### 13.3. Stack dựng đúng cha gần nhất trong U

Duyệt U theo tin tăng dần. Khi xử lý v, tất cả những đỉnh đã gặp nhưng không phải tổ tiên của v không thể là cha của v; chúng được pop. Các tổ tiên của v nằm trên một chuỗi từ gốc tới v và được khám phá theo thứ tự sâu tăng dần, nên top còn lại chính là **tổ tiên sâu nhất thuộc U**.

Vì U chứa LCA của mọi nhóm phân nhánh, rễ chung của U có trước mọi đỉnh khác và luôn còn trên stack khi cần. Mỗi đỉnh khác rễ nhận một cha, không tạo chu trình do cha là tổ tiên thực sự có độ sâu nhỏ hơn.

### 13.4. Cạnh nén bảo toàn đường

Mỗi cạnh ảo p→v thay thế đường duy nhất từ p tới v trong cây gốc. Giữa p và v không có một đỉnh U khác, nếu có thì đỉnh trung gian sâu hơn p phải là cha gần nhất của v thay cho p.

Các cạnh ảo tạo phân hoạch theo đoạn đường của hợp các đường nối terminal, không bỏ đường giữa các điểm phân nhánh. Tổng độ dài của các đoạn nén trên đường giữa hai terminal bằng tổng các đoạn tương ứng trong cây gốc.

**Kết luận:** cây ảo chứa đầy đủ terminal, nối chúng đúng cấu trúc tổ tiên cần thiết, có không quá 2K−1 đỉnh và bảo toàn khoảng cách.

## 14. Độ phức tạp đầy đủ

Gọi N là số đỉnh cây gốc; K là số ID đầu vào của truy vấn, và k là số terminal **phân biệt** sau khi loại trùng, với \(k\le K\).

### Tiền xử lý cây gốc

| Công việc | Thời gian | Bộ nhớ |
|---|---:|---:|
| Kiểm tra cây bằng DSU, xây adjacency | O(N α(N)) (N−1 cạnh) | O(N) |
| DFS tính tin/tout/depth | O(N) | O(N) |
| Điền Binary Lifting `up` | **O(N log N)** | **O(N log N)** |
| LCA mỗi cặp | **O(log N)** | O(1) bộ nhớ bổ sung |

Giải thuật DSU amortized gần tuyến tính; chi phí O(N log N) của bảng up thường chi phối phần tiền xử lý.

### Dựng cây ảo của một truy vấn

- Kiểm tra K ID và sắp theo tin: **O(K log K)**.
- Loại trùng: O(K).
- Tính k−1 LCA, mỗi cái O(log N): **O(k log N)**.
- Thêm LCA, sắp tối đa 2k−1 đỉnh: **O(k log k)**.
- Loại trùng lần hai: O(k).
- Quét stack nối cạnh: **O(k)**, vì mỗi đỉnh push một lần và pop tối đa một lần.

Tổng cho một truy vấn dùng Binary Lifting:

\[
\boxed{O(K\log K+k\log N)}
\]

với bộ nhớ tạm **O(K)** ngoài phần dữ liệu cây gốc đã tiền xử lý.

Nếu K đã phân biệt, thường viết:

\[
\boxed{O(K\log K+K\log N)}.
\]

Nếu LCA được trả O(1) bằng Euler-RMQ đã tiền xử lý, tổng một truy vấn có thể là **O(K log K)** do bước sắp.

### DP trên cây ảo

Cây ảo có M≤2k−1 đỉnh, M−1 cạnh. Duyệt để tính tổng số cạnh nén hoặc tổng khoảng cách cặp terminal mất **O(M)=O(k)** thời gian và bộ nhớ tạm O(k) cho cnt.

### Tổng Q truy vấn

Với tập truy vấn kích thước K1,...,KQ:

\[
O\left(N\log N+
\sum_{i=1}^{Q}(K_i\log K_i+K_i\log N)\right)
\]

với Binary Lifting và phần DP tuyến tính sau dựng. Điều này thường nhỏ hơn \(O(QN)\) khi từng K_i rất nhỏ so với N.

**Quan trọng:** nếu chỉ muốn tính một vài LCA đơn lẻ, dựng cây ảo là thừa. Nó hữu ích khi một truy vấn có **nhiều đỉnh liên quan** và cần tính cấu trúc/DP liên kết giữa chúng.

## 15. Những tình huống biên cần chốt trong đặc tả

| Tình huống | Quy tắc đúng |
|---|---|
| K=0 | Trả cây ảo rỗng; demo root=-1, nodes/edges rỗng |
| K=1 | Chỉ giữ terminal đó, không thêm LCA, không cạnh |
| Terminal trùng nhiều lần | Loại trùng trước khi dựng và trước khi đếm cặp nếu bài mô tả một **tập** |
| Terminal đã là tổ tiên của terminal khác | Đã có trong U; không cần thêm một bản sao |
| Mọi terminal nằm cùng một nhánh dài | Cây ảo có thể là một đường nén |
| Rễ ảo không phải rễ cây gốc | Bình thường; không ép thêm rễ gốc |
| Terminal là rễ cây gốc | Rễ ảo bằng rễ gốc nếu rễ thuộc S |
| Mọi đỉnh gốc đều là terminal | Cây ảo có thể chứa N đỉnh và N−1 cạnh thật |
| Cây gốc dạng sao | LCA của các lá là tâm; cây ảo gồm các lá đánh dấu và tâm |
| Cây gốc dạng đường | Các terminal có quan hệ tổ tiên nối tiếp; LCA mới ít hoặc không có |
| Gốc cây thay đổi | Cần tiền xử lý lại theo gốc mới hoặc kỹ thuật đổi gốc chuyên biệt |
| Graph chứa chu trình | Không phải cây; thuật toán LCA/cây ảo chuẩn không áp dụng trực tiếp |
| Graph không liên thông | Là rừng; cần xử lý từng thành phần và quy ước truy vấn khác thành phần |
| Cạnh có trọng số | Lưu thêm rootSum; độ dài nén theo tổng trọng số nếu mục tiêu là tổng |
| Input ID ngoài `0..N-1` | Báo lỗi, không truy cập mảng tùy tiện |
| N rất lớn | Cần cân nhắc RAM bảng up, danh sách kề, giới hạn mảng Java |
| Nhiều truy vấn liên tiếp | Không để mark/edge của truy vấn trước rò sang truy vấn sau |
| Cặp terminal cùng ID lặp | Trong mô hình tập, chỉ là **một đỉnh**, không tạo cặp với chính nó |

### Nếu truy vấn trải qua nhiều cây của một rừng

Một rừng không có một gốc chung và không có đường đi giữa các đỉnh khác thành phần. Không thể nén nó thành **một cây ảo thật** chứa tất cả terminal thuộc nhiều thành phần, trừ khi thêm siêu gốc giả theo quy ước riêng.

Một lựa chọn hợp lệ là: nhóm terminal theo `componentId`, dựng **một cây ảo cho mỗi nhóm**, rồi thu rừng ảo. Nếu bài yêu cầu “tập terminal phải liên thông”, cần trả **không có lời giải** khi terminal thuộc nhiều thành phần. Mã trong bài từ chối rừng từ đầu nên không có trường hợp ngầm nhập nhằng.

## 16. Lỗi thường gặp khi dựng cây ảo

1. **Sắp terminal theo ID** thay vì tin, khiến LCA liền kề không còn đủ để giữ các điểm nhánh.
2. **Không loại trùng terminal**, dẫn tới đếm sai K, xuất trùng nút hoặc tính sai số cặp.
3. **Tính LCA của mọi cặp \(K^2\)** dù chỉ cần K−1 cặp liền kề theo tin.
4. **Không thêm LCA**, làm các terminal ở hai nhánh không có điểm gặp nhau trong U.
5. **Thêm LCA nhưng quên sắp U lần hai**, khiến stack nhận thứ tự không theo DFS.
6. **Quên loại trùng LCA**, tạo cạnh độ dài 0 giữa hai bản sao cùng đỉnh hoặc kết cấu không phải cây.
7. **Dùng điều kiện `tin[u]<tin[v]` thay cho isAncestor**, sai khi hai đỉnh nằm ở nhánh khác nhau.
8. **Đánh giá tổ tiên bằng depth đơn thuần**, trong khi hai đỉnh cùng cấp hoặc khác cấp có thể nằm ở nhánh khác nhau.
9. **Không pop các đỉnh đã rời nhánh** khi xử lý v tiếp theo, làm v gắn vào cha ảo ở nhánh sai.
10. **Pop cả rễ chung rồi coi nút tiếp theo là gốc mới**, phá tính liên thông của cây ảo.
11. **Nối mỗi đỉnh vào LCA của nó với terminal liền trước** mà không bảo đảm đây là cha ảo gần nhất trong U.
12. **Gán độ dài cạnh ảo bằng 1** dù đoạn đường gốc giữa cha và con ảo dài nhiều cạnh.
13. **Dùng `depth[v]-depth[p]` cho tổng trọng số tùy ý**, quên `rootSum` của cây có trọng số.
14. **Đếm số cạnh ảo thay cho số cạnh gốc** trong bài hỏi kích thước Steiner subtree.
15. **Gộp bội số terminal thành một node rồi vẫn đếm K như số lần xuất hiện**, trong khi DP không lưu khối lượng của từng vị trí.
16. **Dùng `cnt*(K-cnt)/2` cho mỗi cạnh**, chia đôi sai nếu đã đếm cặp không thứ tự.
17. **Duyệt DP từ cha xuống nhưng chưa có cnt của con**, dẫn tới kết quả chưa tổng hợp đầy đủ.
18. **Lưu mảng visited/marked độ dài N và dọn toàn bộ N mỗi truy vấn**, phá lợi thế O(K).
19. **Dùng một adjacency ảo toàn cục mà không xóa/đánh dấu phiên truy vấn**, để cạnh cũ rò sang truy vấn mới.
20. **Xem cạnh ảo là cạnh thật trong input** rồi in sai đường gốc hoặc đếm số cạnh gốc.
21. **Dùng LCA theo gốc A nhưng tin/tout theo gốc B**, khiến quan hệ tổ tiên và phép thêm LCA không nhất quán.
22. **Không kiểm tra input là cây**, cố tính cây ảo trực tiếp trên graph có chu trình.
23. **Không dự trù thời gian/nhớ tiền xử lý LCA**, nhầm chi phí dựng O(K) với toàn bộ pipeline không tốn gì.
24. **Không xác nhận danh sách U đã chứa đủ LCA**, rồi áp dụng stack nối cạnh nhưng nhận nhiều gốc ảo.
25. **Dùng int cho tổng khoảng cách cặp terminal** dù kết quả có thể vượt 32-bit.
26. **Nhầm “cây con bao hàm cạnh tối thiểu” với tối ưu tổng trọng số khi có nhánh âm**, dẫn đến phát biểu sai về trọng số.

## 17. Cách kiểm thử và oracle độc lập

Để kiểm tra dựng cây ảo trên cây nhỏ, không chỉ nhìn tổng trọng số mà nên đối chiếu cấu trúc:

1. **Mọi terminal** xuất hiện đúng một lần trong U.
2. `|U|<=2K−1` khi K≥1.
3. Cây ảo có **|U|−1 cạnh**, mỗi đỉnh khác rễ đúng một cha.
4. Với từng cạnh ảo p→v, p là **tổ tiên thực sự** của v và `depth[v]>depth[p]`.
5. Không có một đỉnh U khác nằm **nghiêm ngặt giữa p và v** trên đường tổ tiên.
6. Mọi đường giữa terminal trong cây ảo có tổng độ dài bằng `distOriginal(u,v)` tính bằng LCA trên cây gốc.
7. Tổng `len` các cạnh ảo bằng số cạnh của **hợp đường gốc** nối terminal.
8. Tổng cặp từ DP bằng phép cộng trực tiếp \(\sum_{i<j}dist(s_i,s_j)\) trên K nhỏ.
9. Với K=0,1 và terminal trùng, kết quả khớp quy ước và không truy cập index sai.
10. Chạy nhiều truy vấn liên tiếp rồi chạy lại truy vấn đầu; kết quả không được thay đổi do trạng thái cũ.

### Oracle nối terminal trên cây gốc

Với K nhỏ, có thể duyệt từng cặp terminal và đánh dấu **các cạnh gốc** trên đường duy nhất của chúng (dùng cha và LCA để lần đường). Hợp các cạnh đó chính là cây con tối thiểu nối S. Đếm số cạnh của hợp và so với tổng `len` của cây ảo.

Oracle này tốn công hơn cây ảo nhưng dễ tin cậy ở graph nhỏ, hữu ích cho kiểm thử ngẫu nhiên. Có thể đối chiếu thêm tổng khoảng cách cặp terminal bằng LCA để xác minh DP.

### Một kiểm thử phản ví dụ cho “không thêm LCA”

Trong cây:

~~~text
    0
   / \
  1   2
 /     \
3       4
~~~

Nếu terminal là `{3,4}` mà chỉ giữ `[3,4]`, không đỉnh nào là tổ tiên của đỉnh kia, nên không có cách nối một cạnh **tổ tiên–hậu duệ**. Phải thêm `LCA(3,4)=0`, tạo:

~~~text
0 -> 3 (2 cạnh gốc)
0 -> 4 (2 cạnh gốc)
~~~

Hai cạnh nén giữ đúng khoảng cách `dist(3,4)=4`. Không thể bỏ LCA 0 dù nó không nằm trong tập terminal.

## 18. Bài tập tự kiểm tra

**Bài 1 — Terminal trùng.** Với input `[10,9,8,9]` trên cây ví dụ, K phân biệt bằng bao nhiêu?

*Đáp án:* **3** terminal: 8,9,10. Cây ảo không tạo hai đỉnh 9.

**Bài 2 — LCA liền kề.** Với terminal theo tin `[8,9,10]`, phải bổ sung LCA nào?

*Đáp án:* `LCA(8,9)=4` và `LCA(9,10)=1`. U là `[1,4,8,9,10]` theo tin.

**Bài 3 — Rễ cây ảo.** Vì sao cây ảo của `[8,9,10]` có rễ 1, không phải 0?

*Đáp án:* Vì 1 là **LCA của cả ba terminal** và mọi đường giữa chúng nằm trong cây con của 1. Đưa 0 vào là dư thừa.

**Bài 4 — Độ dài nén.** Cạnh ảo 1→10 có độ dài mấy cạnh gốc?

*Đáp án:* **2**, theo đường gốc 1–5–10 hoặc hiệu depth[10]−depth[1]=3−1.

**Bài 5 — Cận kích thước.** Với K=6 terminal phân biệt, cây ảo có tối đa bao nhiêu đỉnh?

*Đáp án:* **2K−1=11**; ví dụ chỉ cần **10**.

**Bài 6 — Thứ tự sắp.** Vì sao không thể thay sắp theo tin bằng sắp tăng dần ID?

*Đáp án:* Vì các terminal của một cây con tạo một **đoạn liên tiếp theo thứ tự DFS**, không có bảo đảm tương tự theo nhãn ID tùy ý. Chứng minh LCA liền kề phụ thuộc tính chất đó.

**Bài 7 — Stack tổ tiên.** Khi đỉnh tiếp theo thuộc nhánh khác, phải làm gì trước khi nối cạnh?

*Đáp án:* Pop liên tục các đỉnh trên stack **không phải tổ tiên** của đỉnh mới. Đỉnh top còn lại là cha ảo gần nhất.

**Bài 8 — Cây con tối thiểu.** Cây ảo ví dụ lớn có 9 cạnh nén, nhưng hợp đường gốc nối terminal có bao nhiêu cạnh?

*Đáp án:* **14**, bằng tổng độ dài các cạnh ảo, không phải số lượng cạnh ảo.

**Bài 9 — Tổng cặp.** Với một cạnh ảo dài 2 và có 1 trong K=6 terminal ở phía dưới nó, cạnh đóng góp bao nhiêu vào tổng khoảng cách mọi cặp không thứ tự?

*Đáp án:* \(2\cdot1\cdot(6-1)=10\).

**Bài 10 — Công thức DP.** Vì sao tổng khoảng cách cặp terminal được tính theo \(len\cdot cnt\cdot(K-cnt)\)?

*Đáp án:* Mỗi cặp có một đầu ở dưới cạnh và một đầu ở ngoài sẽ đi qua cạnh đó; có `cnt*(K-cnt)` cặp như thế, mỗi cặp dùng toàn bộ độ dài đoạn nén.

**Bài 11 — Trường hợp một đỉnh.** Với S={12}, cây ảo có bao nhiêu đỉnh/cạnh, rễ là ai?

*Đáp án:* **1 đỉnh**, **0 cạnh**, rễ ảo=12.

**Bài 12 — Cây rỗng theo truy vấn.** Nếu S rỗng, một API có thể biểu diễn thế nào?

*Đáp án:* Theo demo: `root=-1`, danh sách node/edge rỗng. Đây là quy ước API cho **truy vấn rỗng**, không phải gốc hợp lệ.

**Bài 13 — Có trọng số.** Nếu cha ảo p là tổ tiên của v trên cây gốc có trọng số, tính trọng số cạnh nén bằng cách nào?

*Đáp án:* Dùng **`rootSum[v]-rootSum[p]`**. Không lấy `depth[v]-depth[p]` nếu độ dài cạnh không đồng nhất.

**Bài 14 — Thay đổi cây.** Có thể cập nhật một cạnh gốc rồi tiếp tục dùng tin/tout/up cũ không?

*Đáp án:* **Không** nếu thay đổi cấu trúc cây; DFS order và quan hệ tổ tiên có thể đổi, cần tiền xử lý lại hoặc cấu trúc động chuyên dụng.

**Bài 15 — Nhiều truy vấn.** Vì sao không nên clear mảng `marked[N]` sau mỗi truy vấn nếu K rất nhỏ?

*Đáp án:* Clear toàn bộ N ô gây **O(N)** mỗi truy vấn, làm mất lợi thế O(K). Dùng danh sách node của cây ảo, `HashMap` kích thước O(K), hoặc kỹ thuật phiên/timestamp chỉ xóa những đỉnh đã chạm.

**Bài 16 — Kiểm tra tổng.** Với `S={8,9,10}`, tổng ba khoảng cách giữa terminal là bao nhiêu?

*Đáp án:* \(dist(8,9)+dist(8,10)+dist(9,10)=2+4+4=\boxed{10}\).

**Bài 17 — Tính tối thiểu.** Nếu bỏ một đỉnh không phải terminal nhưng nó là LCA của hai nhánh chứa terminal, có còn dựng được cây nén theo cạnh tổ tiên–hậu duệ như cũ không?

*Đáp án:* Không thể giữ đúng điểm hợp lưu nhánh bằng cùng một tập cạnh tổ tiên–hậu duệ nếu bỏ LCA đó. Nó phải được giữ làm điểm nối hoặc cần một biểu diễn phức tạp khác có ý nghĩa tương đương.

**Bài 18 — Thời gian.** Với K terminal phân biệt, Binary Lifting LCA O(log N), cần bao nhiêu lần LCA để bổ sung các đỉnh phân nhánh?

*Đáp án:* **K−1 lần**, không phải \(K(K-1)/2\). Tổng dựng là \(O(K\log K+K\log N)\).

**Tổng kết:** Khi chỉ một tập nhỏ S của cây gốc cần xử lý, hãy **sắp terminal theo tin**, thêm **LCA của các cặp liên tiếp**, loại trùng và dùng **stack tổ tiên** để tạo cây ảo. Cây ảo có tối đa **2K−1 đỉnh**, mỗi cạnh đại diện cho một đoạn đường tổ tiên–hậu duệ; độ dài nén là `depth[child]-depth[parent]` (hoặc hiệu rootSum nếu có trọng số). Cách dựng giữ nguyên quan hệ tổ tiên và khoảng cách giữa các terminal, cho phép chạy DP trên O(K) đỉnh thay vì quét O(N) đỉnh mỗi truy vấn.