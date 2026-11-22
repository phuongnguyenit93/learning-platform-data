# Trọng số âm, cạnh trùng và nhiều cạnh cùng trọng số

## 1. Vì sao ba tình huống này quan trọng đối với cây khung?

**Cây khung nhỏ nhất (minimum spanning tree, MST)** là một cây sử dụng tất cả đỉnh của một **đồ thị vô hướng liên thông**, không có chu trình, với **tổng trọng số cạnh nhỏ nhất** trong số mọi cây khung của đồ thị đó.

Trong các ví dụ nhập môn, trọng số thường là số dương và mỗi cặp đỉnh chỉ có một cạnh. Nhưng bài toán cây khung **không đòi hỏi hai giả thiết đó**:

- **Trọng số âm:** có thể đại diện khoản tiết kiệm, phần thưởng hoặc chi phí được bù trừ. Kruskal và Prim **vẫn đúng** với trọng số âm.
- **Cạnh trùng/cạnh song song:** nhiều bản ghi có thể có cùng hai đầu mút; phải hiểu chúng là **những cạnh vật lý khác nhau** hay **bản ghi lặp** của cùng một cạnh. Nếu tồn tại nhiều cạnh song song, thuật toán vẫn chọn theo trọng số và không tạo chu trình.
- **Nhiều cạnh cùng trọng số:** thuật toán có thể chọn một trong nhiều cách hợp lệ. **Giá trị tổng nhỏ nhất không đổi**, nhưng **tập cạnh được chọn có thể khác nhau**.

Chủ đề quan trọng hơn cú pháp sắp xếp: muốn tìm đúng MST, ta phải tách ba câu hỏi:
1. **Cạnh nào được phép xuất hiện trong một cây khung?** Cạnh được chọn không được tạo chu trình, kể cả self-loop hoặc cạnh song song nối hai đỉnh đã kết nối.
2. **Trọng số của một tập cạnh được tính ra sao?** Tổng có thể là số âm, bằng 0 hoặc dương; không được chỉ lấy cạnh dương hoặc bỏ cạnh âm.
3. **Khi hai cạnh bằng trọng số, chọn cạnh nào?** Cần một quy tắc tie-break nếu muốn kết quả tái lập, nhưng không được lẫn **đầu ra xác định** với **MST duy nhất**.

Bài sẽ dùng **Kruskal + Disjoint Set Union (DSU/Union-Find)** để triển khai đầy đủ bằng Java 17. Sau đó so sánh với Prim, chứng minh tính đúng bằng **tính chất lát cắt và trao đổi**, và kiểm tra độc lập bằng brute force trên đồ thị nhỏ.

## 2. Cây khung, rừng khung và định nghĩa trọng số

Cho đồ thị vô hướng \(G=(V,E,w)\), với n đỉnh, m **cạnh có ID riêng**; \(w(e)\) là trọng số cạnh e, có thể âm. Các đỉnh được đánh số từ 0 tới n−1.

Một **cây khung** T của đồ thị liên thông phải thỏa:
- Bao phủ **mọi đỉnh** của G.
- Liên thông.
- Không chứa chu trình.
- Có đúng **n−1 cạnh** nếu n≥1.

Giá trị của cây:

\[
w(T)=\sum_{e\in T}w(e).
\]

MST là cây khung có tổng \(w(T)\) **nhỏ nhất**, không phải cây có cạnh riêng lẻ nhỏ nhất ở mọi vị trí và cũng không phải đường đi ngắn nhất từ một nguồn.

### Đồ thị không liên thông

Nếu đồ thị có c thành phần liên thông, **không tồn tại một cây khung duy nhất bao phủ cả đồ thị** khi c>1. Thay vào đó, **rừng khung nhỏ nhất** (*minimum spanning forest, MSF*) chứa một MST cho mỗi thành phần ban đầu. Số cạnh được chọn là:

\[
\boxed{|F|=n-c.}
\]

Nó không phải một rừng tùy ý: mỗi thành phần liên thông **phải được nối đủ các đỉnh của thành phần ấy**; vì thế không được chọn rừng rỗng chỉ vì tổng 0 “rẻ hơn” một rừng có các cạnh dương.

Với n=0, ta quy ước rừng rỗng có c=0, tổng trọng số 0, không có cây khung trên một tập đỉnh không tồn tại. Với n=1, cây khung gồm một đỉnh và **không cạnh**, tổng 0, ngay cả nếu đỉnh có self-loop âm.

### Trọng số âm không gây khó khăn cho định nghĩa

Một cây có thể có tổng âm. Ví dụ ba đỉnh 0,1,2 với:

~~~text
0 --(-3)-- 1 --(0)-- 2
 \                 /
  ------(4)--------
~~~

Cây khung tốt nhất chọn trọng số −3 và 0, tổng **−3**. Không có phép biến đổi hoặc điều kiện nào yêu cầu \(w(e)\ge0\). Điều bắt buộc là chọn đủ cạnh nối các đỉnh mà **không tạo chu trình**.

Cũng không được tự động chọn mọi cạnh âm. Nếu ba cạnh âm tạo một chu trình, cây khung vẫn chỉ chọn đủ hai cạnh để nối ba đỉnh, dù việc chọn cả ba làm tổng âm hơn: tập ba cạnh **không phải cây**.

## 3. Ba loại dữ liệu dễ bị lẫn

### 3.1. Cạnh trùng dưới dạng bản ghi

Giả sử input vô hướng có hai dòng:

~~~text
ID 0: (0,1,5)
ID 1: (1,0,5)
~~~

Chúng có cùng hai đầu mút không xét chiều và cùng trọng số. Có hai cách diễn giải:

- Nếu đây là **hai bản ghi của cùng một liên kết vật lý**, hệ thống có thể **chuẩn hóa rồi khử bản ghi lặp** trong giai đoạn làm sạch dữ liệu, nếu điều đó đúng theo đặc tả.
- Nếu đây là **hai cạnh song song độc lập**, chúng là hai cạnh **có ID khác nhau**. Cây khung có thể chọn một trong hai; **không thể chọn cả hai**, vì chúng nối hai đỉnh đã cùng thành phần và tạo chu trình độ dài 2 trong mô hình đa đồ thị.

Đối với **giá trị tối ưu MST/MSF** trên đồ thị vô hướng, bỏ bớt bản sao đúng nghĩa có **cùng hai đầu mút, cùng trọng số** không thay đổi chi phí nhỏ nhất. Tuy nhiên, việc đó **có thể thay đổi số lời giải MST phân biệt theo ID cạnh**, thay đổi ID kết quả và làm mất thông tin nguồn dữ liệu. Không được tự khử trùng khi bài yêu cầu xử lý hoặc đếm từng cạnh vật lý.

### 3.2. Cạnh song song có trọng số khác nhau

~~~text
ID 0: (5,6,-1)
ID 1: (5,6, 3)
~~~

Nếu muốn nối đỉnh 5 với đỉnh 6 trong cây khung, cạnh −1 tốt hơn cạnh 3. Kruskal xét theo trọng số tăng sẽ chọn cạnh −1 khi hai đỉnh còn thuộc hai tập rời nhau; cạnh 3 về sau tạo chu trình và bị bỏ.

Nếu chỉ cần **chi phí MST** và không có những ràng buộc phụ thuộc ID cạnh, có thể giữ **trọng số nhỏ nhất** giữa mỗi cặp đỉnh vô hướng để giảm dữ liệu; nhưng khi cần số lượng cạnh, tính đa dạng lời giải hoặc ID vật lý, phải giữ cạnh và ý nghĩa gốc.

### 3.3. Nhiều cạnh bằng trọng số nhưng khác hai đầu mút

Xét hình vuông với cạnh trọng số 1:

~~~text
0 --1-- 1
|       |
1       1
|       |
3 --1-- 2
~~~

Bỏ một cạnh bất kỳ của chu trình ta được cây khung 3 cạnh, tổng 3. Có **nhiều MST** khác nhau với cùng trọng số. Không thể yêu cầu Kruskal trả cùng bộ ID cạnh trên mọi thứ tự tie mà không có chính sách sắp xếp cụ thể.

**Có trọng số bằng nhau không có nghĩa chắc chắn có nhiều MST.** Đồ thị chỉ là một đường 0--1--2 với cả hai cạnh trọng số 1 vẫn chỉ có **một** cây khung: cả hai cạnh đều bắt buộc.

### 3.4. Self-loop

Cạnh (u,u,w) nối một đỉnh với chính nó. Nó **không giúp nối hai thành phần khác nhau** và nếu đưa vào tập cạnh, tự tạo chu trình. Vì vậy **self-loop không bao giờ thuộc cây khung**, kể cả w là −100 hay −1.000.000.

Cạnh âm không cho phép vi phạm điều kiện không chu trình. Một thuật toán tham lam chỉ lấy “mọi cạnh âm” là sai ngay trên self-loop âm và chu trình âm.

## 4. Kruskal không cần trọng số không âm

**Kruskal** xét **tất cả cạnh vô hướng theo thứ tự trọng số tăng dần**, rồi chỉ thêm cạnh nếu nó nối **hai thành phần khác nhau** của rừng hiện tại.

Cách triển khai:

~~~text
kruskal(n, edges):
    sort edges by (weight ascending, normalized endpoints, edge ID)
    dsu = n singleton sets
    selected = []
    total = 0

    for each edge e=(u,v,w):
        if dsu.find(u) == dsu.find(v):
            continue              // Tạo chu trình hoặc self-loop.

        dsu.union(u,v)
        selected.add(e)
        total += w

    return selected, total, dsu.componentCount
~~~

Để kết quả **có thể tái lập** trên ví dụ, ta chọn khóa sắp xếp:

\[
\boxed{(w(e),\min(u,v),\max(u,v),ID(e))}
\]

theo thứ tự tăng. Đây là **tie-break cho việc hiển thị**, không phải một quy tắc toán học bắt buộc để tìm MST.

**Cốt lõi của Kruskal chỉ dựa vào phép so sánh trọng số**, không dựa vào w≥0:
- Cạnh âm được xét trước cạnh 0 và cạnh dương.
- Nếu cạnh âm nối hai thành phần rời, chọn nó thường giúp giảm tổng.
- Nếu cạnh âm tạo chu trình, **phải bỏ qua**, dù giá trị âm có vẻ có lợi.
- Cạnh song song nối hai đỉnh đã kết nối sẽ bị DSU từ chối.
- Khi trọng số hòa, một quy tắc thứ tự thứ cấp chỉ giúp chọn một nghiệm xác định.

### Tại sao không dùng Dijkstra làm tiền đề về dấu trọng số?

**Dijkstra** cho đường đi ngắn nhất có tính chất chốt khoảng cách dựa trên **cạnh không âm**. **Kruskal/Prim** cho cây khung dùng **tính chất lát cắt** và cấu trúc không chu trình, nên **không cần trọng số không âm**. Không được áp dụng điều kiện của bài **đường đi ngắn nhất** sang bài **cây khung**.

Hai mục tiêu khác nhau: đường đi ngắn nhất giữa các đỉnh không nhất thiết nằm trong MST; một MST không bảo đảm mọi cặp đỉnh có đường đi ngắn nhất theo trọng số.

## 5. DSU bảo đảm không tạo chu trình

**Disjoint Set Union (DSU, Union-Find)** duy trì các thành phần liên thông của rừng cạnh đã chọn.

Hai thao tác:
- **find(x):** trả đại diện của thành phần chứa x.
- **union(u,v):** nếu hai đại diện khác nhau, gộp chúng và trả true; nếu cùng đại diện, trả false.

Khi Kruskal xét cạnh (u,v):
- Nếu find(u)!=find(v), hiện chưa có đường trong rừng từ u tới v. Thêm cạnh **không thể tạo chu trình**; union thành công, số thành phần giảm một.
- Nếu find(u)==find(v), rừng đã có đường từ u tới v. Thêm cạnh sẽ tạo chu trình (self-loop cũng thuộc trường hợp này), nên **bỏ cạnh**.

DSU thường dùng:
- **Path compression:** rút ngắn chuỗi cha mỗi lần find.
- **Union by size/rank:** gắn cây nhỏ vào cây lớn.

Với hai kỹ thuật đó, chi phí trung bình khấu hao của find/union gần như hằng số, chính xác là **O(α(n))**, trong đó α là hàm Ackermann đảo tăng cực chậm.

**Không dùng visited của DFS thay DSU một cách tùy tiện.** Mỗi cạnh Kruskal được xét trong một trạng thái rừng thay đổi liên tục; DSU cho phép kiểm tra hai đầu có cùng thành phần hay không một cách hiệu quả.

## 6. Vì sao Kruskal đúng dù có cạnh âm và hòa?

### 6.1. Tính chất lát cắt (cut property)

Một **lát cắt** chia đỉnh thành hai tập khác rỗng A và V\A. Một cạnh **đi qua lát cắt** nếu có một đầu ở A và đầu kia ở V\A.

Trong một đồ thị liên thông, xét một tập cạnh A0 đã chọn **không có chu trình** và nằm trong ít nhất một MST. Nếu cạnh e là một cạnh nhẹ nhất đi qua một lát cắt **không cắt qua cạnh nào của A0**, thì e là **cạnh an toàn**: tồn tại một MST chứa cả A0 và e.

Tại thời điểm Kruskal xét e nối hai thành phần DSU khác nhau, có thể chọn lát cắt là **thành phần DSU chứa một đầu e** và phần còn lại. Các cạnh đã chọn không băng qua lát cắt đó. Vì các cạnh được xét theo trọng số tăng, e là một cạnh nhẹ nhất có thể nối thành phần ấy với phần bên ngoài ở thời điểm đó.

### 6.2. Chứng minh trao đổi (exchange argument)

Giả sử T là một MST chứa các cạnh đã chọn, nhưng chưa chứa e. Thêm e vào T tạo đúng một chu trình. Chu trình đó phải có một cạnh f khác cũng đi qua lát cắt đang xét.

Vì e là **một cạnh nhẹ nhất qua lát cắt**, ta có \(w(e)\le w(f)\). Thay f bằng e tạo một cây khung mới:

\[
T'=T-\{f\}+\{e\},
\]

với:

\[
w(T')=w(T)-w(f)+w(e)\le w(T).
\]

Do T đã tối ưu, T' cũng tối ưu và chứa e. Như vậy ta có thể mở rộng tập cạnh Kruskal đã chọn mà **không làm mất khả năng hoàn thành thành MST**.

**Dấu trọng số không xuất hiện trong chứng minh.** Bất đẳng thức w(e)≤w(f) vẫn đúng nếu cả hai âm, bằng 0 hoặc dương. Khi hòa w(e)==w(f), ta có **hai cách chọn khác nhau có thể cùng tối ưu**.

### 6.3. Khi đồ thị không liên thông

Áp dụng chứng minh trong từng thành phần liên thông của đồ thị ban đầu. Vì không có cạnh giữa các thành phần khác nhau, không thể tạo một cây khung chung; Kruskal tạo một MST cho **mỗi thành phần**, tức **MSF**.

Khi thuật toán dừng sau khi xét toàn bộ cạnh, không còn cạnh nào nối hai tập DSU thuộc cùng một thành phần liên thông gốc. Nếu còn cạnh như vậy, nó đã được xét và union thành công khi hai tập còn rời nhau. Do đó rừng có đúng n−c cạnh và nối đủ mỗi thành phần.

**Kết luận:** Kruskal với trọng số tăng dần + bỏ cạnh tạo chu trình trả một MST/MSF đúng, kể cả trọng số âm, cạnh song song và hòa trọng số.

## 7. Khác biệt giữa một MST và tất cả MST

Với nhiều cạnh cùng trọng số, có thể tồn tại **nhiều MST khác nhau**. Kruskal **không liệt kê tất cả**: nó trả **một** MST ứng với chính sách tie-break.

- Nếu các cạnh đều có **trọng số phân biệt**, đồ thị liên thông có MST **duy nhất** (bỏ self-loop cũng không làm tính chất này sai).
- Nếu có cạnh cùng trọng số, MST **có thể duy nhất hoặc không**. Cạnh trùng trọng số trên một đường vẫn có thể đều bắt buộc; hòa trong chu trình thường tạo nhiều phương án.
- Nếu các cạnh song song có cùng hai đầu và cùng trọng số nhưng **ID khác nhau**, có thể coi việc đổi ID cạnh được chọn là hai MST khác nhau theo **danh tính vật lý**. Nếu chỉ so **tập cặp đỉnh** không tính ID, đó có thể bị coi là cùng kết quả; định nghĩa “khác nhau” phải rõ.
- Một chính sách sort ổn định **không chứng minh MST là duy nhất**. Nó chỉ chọn ra một nghiệm xác định trên cùng đầu vào.

**Chọn cạnh tùy ý trong nhóm hòa thường vẫn đúng để tìm một MST**, vì mỗi cạnh được chọn phải là cạnh nhẹ nhất cắt qua một lát cắt phù hợp và không tạo chu trình. Nhưng nếu mục tiêu là **đếm hoặc liệt kê mọi MST**, phải xử lý các nhóm trọng số bằng nhau theo một thuật toán riêng; chỉ thay tie-break rồi hy vọng liệt kê đủ là không đáng tin cậy.

### Cạnh bắt buộc và cạnh tùy chọn

- **Cạnh bắt buộc** xuất hiện trong mọi MST.
- **Cạnh tùy chọn** xuất hiện trong một số MST nhưng không phải tất cả.
- **Cạnh không thể chọn** không xuất hiện trong bất kỳ MST nào.

Trọng số hòa không tự quyết định một cạnh thuộc nhóm nào. Cần phân tích các lát cắt/chu trình và các cạnh bằng trọng số có thể thay thế nhau. Ví dụ hai đỉnh chỉ có một cạnh trọng số 1 thì cạnh ấy bắt buộc; hai cạnh song song cùng trọng số 1 thì từng cạnh có thể thay thế cạnh kia.

## 8. Một ví dụ tổng hợp với âm, song song, hòa, loop và đỉnh cô lập

Xét đồ thị vô hướng có **8 đỉnh 0..7**, cạnh đánh số đúng theo **vị trí trong danh sách đầu vào**:

| ID | Cạnh nhập | Trọng số | Ý nghĩa |
|---:|---|---:|---|
| 0 | (0,1) | −4 | Cạnh âm nối 0 với 1 |
| 1 | (1,0) | −4 | Bản ghi đảo đầu mút, ID khác |
| 2 | (1,2) | −2 | Cạnh âm trong tam giác |
| 3 | (0,2) | −2 | Hòa với ID 2 |
| 4 | (2,3) | 1 | Hòa trọng số với ID 5 |
| 5 | (1,3) | 1 | Hòa trọng số với ID 4 |
| 6 | (3,4) | 2 | Hòa với ID 7 |
| 7 | (2,4) | 2 | Hòa với ID 6 |
| 8 | (0,4) | 10 | Đường nối đắt |
| 9 | (0,0) | −100 | Self-loop âm, **không hợp lệ trong cây** |
| 10 | (2,2) | −100 | Self-loop âm khác |
| 11 | (5,6) | −1 | Thành phần thứ hai |
| 12 | (5,6) | 3 | Cạnh song song đắt hơn |
  
Đỉnh **7 cô lập**. Các thành phần liên thông gốc:
- Cụm A: {0,1,2,3,4}.
- Cụm B: {5,6}.
- Cụm C: {7}.

Vậy **c=3** và một rừng khung phải chọn \(n-c=8-3=5\) cạnh.

### 8.1. Thứ tự Kruskal với tie-break (w,minEnd,maxEnd,ID)

Các cạnh được xét lần lượt theo ID:

~~~text
9, 10, 0, 1, 3, 2, 11, 5, 4, 7, 6, 12, 8
~~~

Hai self-loop âm −100 ở đầu danh sách **đều bị bỏ**, bởi find(0)==find(0) và find(2)==find(2).

| Bước có ý nghĩa | Cạnh | Hành động | Lý do |
|---|---|---|---|
| Đầu | #9 (0,0,−100) | Bỏ | Self-loop |
| Đầu | #10 (2,2,−100) | Bỏ | Self-loop |
| 1 | #0 (0,1,−4) | **Chọn** | Nối hai tập rời |
| 2 | #1 (1,0,−4) | Bỏ | Hai đầu đã chung tập |
| 3 | #3 (0,2,−2) | **Chọn** | Đưa 2 vào cụm 0,1 |
| 4 | #2 (1,2,−2) | Bỏ | Chu trình 0–1–2–0 |
| 5 | #11 (5,6,−1) | **Chọn** | Nối 5 và 6 |
| 6 | #5 (1,3,1) | **Chọn** | Đưa 3 vào cụm A |
| 7 | #4 (2,3,1) | Bỏ | Đã cùng cụm A |
| 8 | #7 (2,4,2) | **Chọn** | Đưa 4 vào cụm A |
| Còn lại | #6, #12, #8 | Bỏ | Tạo chu trình trong cụm tương ứng |

Các cạnh được chọn theo thứ tự:

~~~text
#0:0-1@-4
#3:0-2@-2
#11:5-6@-1
#5:1-3@1
#7:2-4@2
~~~

Tổng:

\[
-4+(-2)+(-1)+1+2=\boxed{-4}.
\]

**Rừng kết quả có 3 thành phần, không có cây khung của toàn đồ thị.** Đây là **MSF** với tổng −4, không phải “MST có ba cây” theo nghĩa có một cây khung chung.

### 8.2. Có những nghiệm tối ưu khác không?

Có. Chẳng hạn thay trong cụm A:
- Chọn cạnh #2 (1,2,−2) thay #3 (0,2,−2).
- Chọn cạnh #4 (2,3,1) thay #5 (1,3,1).
- Chọn cạnh #6 (3,4,2) thay #7 (2,4,2), miễn các cạnh vẫn tạo một cây.

Một nghiệm khác là các cạnh ID **[0,2,4,6,11]**, tổng vẫn:

\[
-4-2+1+2-1=-4.
\]

Hai nghiệm có cùng tổng nhỏ nhất; thuật toán Java chọn bộ theo tie-break đã công bố. Không phải mọi tổ hợp tùy tiện các cạnh hòa đều chắc chắn là một cây: phải kiểm tra **không chu trình và nối đủ đỉnh**.

### 8.3. Hai loại “trùng” trong cùng ví dụ

Cạnh #0 và #1 có cùng hai đầu mút và trọng số. Nếu chúng là **hai liên kết vật lý**, chọn #0 thay #1 cho ra hai nghiệm theo ID khác nhau. Nếu #1 chỉ là **bản ghi nhập lặp**, hệ thống có thể chuẩn hóa xóa bản ghi ấy trước, nhưng nên lưu lý do làm sạch nếu cần đối chiếu dữ liệu.

Cạnh #11 và #12 cùng hai đầu mút nhưng **trọng số khác nhau**: không phải “trùng hệt” và không thể đồng nhất như bản ghi lặp không điều kiện. Để tính chi phí MST, cạnh #11 rẻ hơn; cạnh #12 không thể tốt hơn khi chỉ cần nối 5 với 6.

## 9. Chương trình Java 17+: Kruskal với ID cạnh và DSU

Code độc lập thực hiện:
- **Trọng số long có thể âm**, kể cả giá trị −100 trên self-loop.
- **Cạnh nhập là cạnh vô hướng**, bất kể hai đầu mút được viết theo chiều nào.
- Mỗi cạnh có **ID theo chỉ số hàng input**, không tự xóa cạnh song song.
- Chuẩn hóa hai đầu mút thành **min/max** chỉ để sort và in cho nhất quán.
- Sắp theo **weight, u, v, ID** tăng dần bằng comparator an toàn, không dùng phép trừ.
- Dùng **DSU path compression + union by size** để tránh chu trình.
- Tính tổng với **Math.addExact** để phát hiện tràn long, kể cả khi tổng âm.
- Trả kết quả **rừng khung nhỏ nhất** khi đồ thị không liên thông; báo riêng **có cây khung toàn đồ thị không**.
- Chạy một số trường hợp biên: mọi cạnh hòa, chỉ có cạnh song song, self-loop âm, đỉnh cô lập, đồ thị rỗng, một đỉnh.

Lưu thành tệp **MstSpecialWeightsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public final class MstSpecialWeightsDemo {
    private MstSpecialWeightsDemo() {
    }

    private record Edge(int id, int u, int v, long weight) {
    }

    public record Result(
            long totalWeight,
            int components,
            List<String> chosenEdges,
            boolean hasSpanningTree) {
    }

    private static final class Dsu {
        private final int[] parent;
        private final int[] size;
        private int components;

        Dsu(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;

            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]]; // Path compression.
                x = parent[x];
            }
            return x;
        }

        boolean union(int x, int y) {
            int rootX = find(x);
            int rootY = find(y);

            if (rootX == rootY) {
                return false; // Chu trình hoặc self-loop.
            }

            if (size[rootX] < size[rootY]) {
                int tmp = rootX;
                rootX = rootY;
                rootY = tmp;
            }

            parent[rootY] = rootX;
            size[rootX] += size[rootY];
            components--;
            return true;
        }

        int componentCount() {
            return components;
        }
    }

    public static Result minimumSpanningForest(
            int vertexCount, long[][] inputEdges) {
        if (vertexCount < 0 || inputEdges == null) {
            throw new IllegalArgumentException("Invalid graph");
        }

        Edge[] edges = new Edge[inputEdges.length];

        for (int id = 0; id < inputEdges.length; id++) {
            long[] row = inputEdges[id];

            if (row == null || row.length != 3) {
                throw new IllegalArgumentException(
                        "Each edge requires u, v, weight");
            }

            long u = row[0];
            long v = row[1];
            long w = row[2];

            if (u < 0 || v < 0
                    || u >= vertexCount || v >= vertexCount) {
                throw new IllegalArgumentException(
                        "Vertex out of range");
            }

            // Đồ thị vô hướng: chuẩn hóa hai đầu mút.
            int a = (int) Math.min(u, v);
            int b = (int) Math.max(u, v);
            edges[id] = new Edge(id, a, b, w);
        }

        Arrays.sort(edges, Comparator
                .comparingLong(Edge::weight)
                .thenComparingInt(Edge::u)
                .thenComparingInt(Edge::v)
                .thenComparingInt(Edge::id));

        Dsu dsu = new Dsu(vertexCount);
        long total = 0L;
        List<String> chosen = new ArrayList<>();

        for (Edge edge : edges) {
            if (!dsu.union(edge.u(), edge.v())) {
                continue;
            }

            total = Math.addExact(total, edge.weight());
            chosen.add("#" + edge.id() + ":"
                    + edge.u() + "-" + edge.v()
                    + "@" + edge.weight());
        }

        int components = dsu.componentCount();
        boolean hasTree = vertexCount > 0 && components == 1;

        return new Result(
                total, components, List.copyOf(chosen), hasTree);
    }

    private static void show(
            String label, int n, long[][] edges) {
        Result r = minimumSpanningForest(n, edges);
        System.out.println(label
                + ": total=" + r.totalWeight()
                + ", components=" + r.components()
                + ", edges=" + r.chosenEdges());
    }

    public static void main(String[] args) {
        long[][] mainEdges = {
                {0, 1, -4}, {1, 0, -4},
                {1, 2, -2}, {0, 2, -2},
                {2, 3, 1}, {1, 3, 1},
                {3, 4, 2}, {2, 4, 2},
                {0, 4, 10},
                {0, 0, -100}, {2, 2, -100},
                {5, 6, -1}, {5, 6, 3}
        };

        Result main = minimumSpanningForest(8, mainEdges);
        System.out.println("Main: total=" + main.totalWeight()
                + ", components=" + main.components()
                + ", edges=" + main.chosenEdges());
        System.out.println("Main spanning tree: "
                + main.hasSpanningTree());

        long[][] square = {
                {0, 1, 1}, {1, 2, 1},
                {2, 3, 1}, {3, 0, 1},
                {0, 2, 1}
        };

        Result equal = minimumSpanningForest(4, square);
        System.out.println("Square: total=" + equal.totalWeight()
                + ", components=" + equal.components()
                + ", edges=" + equal.chosenEdges());
        System.out.println("Square spanning tree: "
                + equal.hasSpanningTree());

        show("Parallel", 2, new long[][] {
                {0, 1, 5}, {1, 0, 5}
        });

        show("Negative and loop", 2, new long[][] {
                {0, 0, -10}, {0, 1, -5}, {0, 1, -5}
        });

        show("Only isolated", 3, new long[][] {});
        show("Empty", 0, new long[][] {});
        show("Single self-loop", 1, new long[][] {
                {0, 0, -3}
        });

        show("Unique weights", 3, new long[][] {
                {0, 1, -3}, {1, 2, 0}, {0, 2, 4}
        });
    }
}
~~~

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

~~~bash
javac -encoding UTF-8 MstSpecialWeightsDemo.java
java MstSpecialWeightsDemo
~~~

**Stdout chính xác:**

~~~text
Main: total=-4, components=3, edges=[#0:0-1@-4, #3:0-2@-2, #11:5-6@-1, #5:1-3@1, #7:2-4@2]
Main spanning tree: false
Square: total=3, components=1, edges=[#0:0-1@1, #4:0-2@1, #3:0-3@1]
Square spanning tree: true
Parallel: total=5, components=1, edges=[#0:0-1@5]
Negative and loop: total=-5, components=1, edges=[#1:0-1@-5]
Only isolated: total=0, components=3, edges=[]
Empty: total=0, components=0, edges=[]
Single self-loop: total=0, components=1, edges=[]
Unique weights: total=-3, components=1, edges=[#0:0-1@-3, #1:1-2@0]
~~~

### 9.1. Vì sao kết quả có ID nhưng vẫn chuẩn hóa u và v?

Mỗi hàng input được đánh số ID=0,1,... riêng. Khi là đồ thị **vô hướng**, hai dòng (0,1,w) và (1,0,w) kết nối cùng một cặp đỉnh; chuẩn hóa u=min và v=max chỉ giúp so sánh, hiển thị nhất quán.

**ID không bị xóa hoặc nhập nhằng.** Đó là thông tin để phân biệt hai cạnh song song nếu chúng thật sự là hai liên kết độc lập. Với trọng số bằng nhau, ID là khóa tie-break cuối sau hai đầu mút.

### 9.2. Vì sao self-loop âm vẫn bị bỏ?

Khi xét cạnh u==v, DSU thấy find(u)==find(v) và union trả false. Điều kiện này không liên quan đến dấu w. Vì vậy các self-loop −100 và −10 không đi vào rừng kết quả, dù được xét rất sớm vì trọng số âm lớn.

### 9.3. Vì sao tổng trọng số có thể âm?

Sau mỗi union thành công, cộng trọng số cạnh với Math.addExact. Ví dụ âm −4, −2 và −1 có thể làm tổng giảm; đó là điều hoàn toàn hợp lệ với hàm mục tiêu **tối thiểu hóa tổng**, không có thao tác cắt giá trị âm thành 0.

Math.addExact phát hiện khi tổng vượt khả năng biểu diễn của long. Nếu dữ liệu có tổng vượt miền long, dùng BigInteger hoặc quy tắc số học phù hợp thay vì để overflow âm/dương làm sai kết quả.

### 9.4. Ý nghĩa hasSpanningTree

Chương trình quy định:
- n>0 và components==1 → đồ thị có cây khung; với n=1, cây rỗng cạnh trên một đỉnh cũng là cây khung.
- components>1 → không có một cây khung nối **toàn bộ** đồ thị; kết quả là MSF.
- n=0 → trả rừng rỗng, đặt hasSpanningTree=false theo quy ước API minh họa.

Không nhầm **MSF hợp lệ** của đồ thị không liên thông với “thuật toán thất bại”. Thuật toán đã tối ưu hóa đầy đủ trong từng thành phần.

### 9.5. Comparator và tính tái lập

Arrays.sort dùng Comparator.comparingLong rồi các khóa int. Không dùng phép trừ w1−w2 để tạo comparator vì trọng số long âm/dương lớn có thể tràn và phá quan hệ thứ tự.

Nếu thay khóa phụ, **tổng MST vẫn đúng** nhưng danh sách ID chọn trong nhóm trọng số hòa có thể đổi. Java PriorityQueue không cần thiết trong Kruskal vì ta sắp toàn bộ cạnh rồi duyệt theo thứ tự.

## 10. Đổi thứ tự khi hòa có thể đổi cây, không đổi tổng

Trong ví dụ chính, cạnh #3 (0,2,−2) được xét trước #2 (1,2,−2) vì cặp đầu mút (0,2) nhỏ hơn (1,2). Sau khi chọn #3, #2 tạo chu trình và bị bỏ.

Nếu đổi thứ tự hai cạnh −2, có thể chọn #2 thay #3 mà tổng vẫn giữ −4. Tương tự, cạnh trọng số 1 và 2 có nhiều lựa chọn cấu thành một cây rừng tối ưu.

Điều này minh họa hai khái niệm:

**Tính đúng về giá trị:** tất cả kết quả của Kruskal hợp lệ phải đạt cùng tổng tối ưu.

**Tính xác định của danh sách cạnh:** nếu cần so sánh bằng unit test chính xác tới từng ID, phải cố định cả:
- Quy ước cạnh vô hướng (chuẩn hóa hai đầu).
- Thứ tự sắp trọng số tăng.
- Khóa tie-break giữa cạnh bằng trọng số.
- Quy ước ID cạnh trong input.

Không được viết bài kiểm thử yêu cầu luôn có đúng một bộ cạnh khi đặc tả chỉ yêu cầu **giá trị tối ưu** hoặc **một MST bất kỳ**.

Nếu cần **MST thứ hai**, **đếm MST**, **tất cả MST**, hoặc MST **duy nhất**, đó là các yêu cầu nâng cao khác; không thể chỉ dựa trên một lần chạy Kruskal rồi suy ra toàn bộ.

## 11. So sánh Kruskal và Prim khi trọng số âm hoặc bằng nhau

**Prim** xây dần một cây từ một đỉnh khởi đầu: ở mỗi bước chọn cạnh nhẹ nhất nối tập đỉnh đã lấy với một đỉnh chưa lấy. Tính chất lát cắt cũng chứng minh Prim đúng **dù có cạnh âm**.

| Đặc điểm | Kruskal | Prim |
|---|---|---|
| Chiến lược | Chọn các cạnh tăng dần trọng số toàn cục | Mở rộng một cây qua cạnh nhẹ nhất trên biên |
| Cấu trúc chính | Sắp cạnh + DSU | Hàng đợi ưu tiên + đánh dấu đỉnh trong cây |
| Trọng số âm | Hợp lệ | Hợp lệ |
| Cạnh bằng trọng số | Có thể có nhiều MST; tie-break | Có thể có nhiều MST; tie-break |
| Cạnh song song | DSU từ chối cạnh tạo chu trình | Chọn cạnh biên tốt nhất; bỏ cạnh tới đỉnh đã nằm trong cây |
| Self-loop | DSU.union(u,u) trả false | Không giúp mở rộng cây, bị bỏ |
| Không liên thông | Tự tạo MSF khi xét toàn bộ cạnh | Phải khởi động Prim từ mỗi đỉnh chưa thăm để tạo MSF |

**Cảnh báo:** với Prim, không được chỉ chạy từ đỉnh 0 rồi tuyên bố đã có rừng khung của **mọi** thành phần. Nếu đồ thị không liên thông, một lượt Prim đơn nguồn chỉ chạm thành phần chứa đỉnh 0.

Khi chọn Prim với PriorityQueue, có thể tồn tại các bản ghi cạnh/khóa lỗi thời. Cần kiểm tra đỉnh đã thuộc cây hay chưa và chính sách cập nhật phù hợp. Nhưng đó là cơ chế của **Prim**, không phải lý do phải cấm trọng số âm.

### Tại sao không thể “thêm hằng số để hết trọng số âm” một cách tùy tiện?

Với đồ thị liên thông có n đỉnh, **mọi cây khung đều có đúng n−1 cạnh**. Nếu cộng cùng hằng số C vào **mọi cạnh**, trọng số mỗi cây tăng đúng \((n-1)C\), nên thứ tự tổng chi phí cây khung không đổi.

Tương tự, trong đồ thị có c thành phần, mọi **rừng khung đầy đủ** đều có n−c cạnh, nên cộng cùng hằng số vào mọi cạnh cũng cộng một hằng số chung \((n-c)C\) vào tổng MSF. Đây là một **phép biến đổi toán học hợp lệ** nếu giữ nguyên cấu trúc và không tràn kiểu số.

Tuy vậy, Kruskal/Prim **không cần** phép biến đổi này; việc cộng C có thể gây tràn số và làm khó giải thích dữ liệu gốc. Không dùng cách dịch trọng số để “sửa” một thuật toán thực chất đã sai ở bước kiểm tra chu trình.

## 12. Độ phức tạp

Gọi n là số đỉnh, m là số cạnh vô hướng **tính cả cạnh song song và self-loop**.

Trong Java:
1. Kiểm tra và chuẩn hóa từng cạnh: **O(m)**.
2. Sắp cạnh theo bộ khóa trọng số, hai đầu mút và ID: **O(m log m)**.
3. Khởi tạo DSU: **O(n)**.
4. Duyệt m cạnh, mỗi cạnh gọi find/union khấu hao **O(α(n))**: tổng **O(mα(n))**.
5. Ghi các cạnh đã chọn và tính tổng: O(n), vì MSF chọn tối đa n−c≤n−1 cạnh với n≥1.

Tổng thời gian:

\[
\boxed{O(m\log m+m\alpha(n)+n).}
\]

Với m≥2 và đồ thị đủ lớn, phần sắp xếp thường chi phối; cách viết quen thuộc là **O(m log m)** cộng chi phí DSU.

Bộ nhớ:
- Mảng bản sao cạnh để sort: O(m).
- DSU parent/size: O(n).
- Danh sách cạnh được chọn: O(n).
- Tổng **O(m+n)**; không bao gồm không gian tạm của thư viện sort nếu phải tính chi tiết cấu hình JVM.

**Trọng số âm không làm thay đổi độ phức tạp.** Cạnh trùng và cạnh song song tăng m nên tăng thời gian sắp/duyệt; nhưng DSU vẫn bỏ cạnh tạo chu trình trong thời gian khấu hao gần hằng số.

## 13. Kiểm chứng độc lập bằng brute force số cạnh nhỏ

Muốn kiểm tra Kruskal trên n nhỏ, có thể **liệt kê mọi tập con cạnh** và tìm chi phí rừng khung tối thiểu theo đúng định nghĩa.

Trước hết xác định số thành phần liên thông gốc \(c\) của G **bỏ qua trọng số**. Một tập cạnh F là rừng khung hợp lệ khi:
1. F chỉ chứa cạnh của đồ thị đầu vào.
2. F không có chu trình (DSU kiểm tra khi duyệt từng cạnh F).
3. F có đúng \(n-c\) cạnh.
4. Các thành phần trong F **trùng với các thành phần liên thông gốc** (có thể kiểm tra số thành phần bằng c cùng với tính không chu trình và tập cạnh con của G).

Với mỗi tập F hợp lệ, tính tổng trọng số. **Giá trị nhỏ nhất** trong tất cả F là đáp án oracle.

~~~text
baseComponents = countComponents(G ignoring weights)
best = +INF

for every subset F of edge IDs:
    if size(F) != n - baseComponents:
        continue

    dsu = new DSU(n)
    total = 0
    valid = true

    for each edge e in F:
        if not dsu.union(e.u, e.v):
            valid = false      // Chu trình, kể cả self-loop.
            break
        total += e.weight

    if valid and dsu.componentCount == baseComponents:
        best = min(best, total)

compare(best, kruskalTotal)
~~~

Với 13 cạnh trong ví dụ chính, có \(2^{13}=8192\) tập cạnh cần xét tối đa — đủ nhỏ để làm bộ tham chiếu kiểm thử. Cách này chậm theo **m**, không dùng trên dữ liệu lớn.

**Quan trọng:** brute force phải **giữ ID cạnh** nếu dữ liệu là đa đồ thị. Xóa “các dòng trùng đầu mút” trước khi tạo oracle có thể làm sai phép đếm MST theo ID, dù giá trị tối ưu đôi khi không đổi.

### Kiểm tra các bất biến ngay trên output

- Mỗi cạnh chọn có ID hợp lệ, và một ID xuất hiện tối đa một lần.
- Không có cạnh chọn dạng u==v.
- Các cạnh chọn không tạo chu trình; DSU union đều thành công.
- Số cạnh chọn bằng **n−components** sau cùng.
- Tổng trọng số các cạnh chọn **bằng totalWeight**, kể cả nếu âm.
- Nếu hasSpanningTree=true và n>0, selected có n−1 cạnh.
- Nếu n=0, kết quả là rừng rỗng theo quy ước đã nêu.
- Sắp lại các cạnh input theo thứ tự khác **không làm thay đổi giá trị tối ưu**; ID và tập cạnh tie có thể khác.

## 14. Các lỗi phổ biến

1. **Cấm trọng số âm vì nhầm với Dijkstra.** Kruskal và Prim vẫn đúng với trọng số âm; chứng minh dựa trên lát cắt.
2. **Chọn mọi cạnh âm rồi mới bỏ cạnh dương.** Có thể tạo chu trình âm và không còn cây khung.
3. **Chọn self-loop âm vì nó rẻ nhất.** Self-loop luôn tạo chu trình, không giúp nối hai đỉnh.
4. **Khử mọi cạnh trùng hai đầu mút mà không xem trọng số.** Nếu một cạnh giá 5 và một cạnh −1, xóa nhầm cạnh rẻ có thể làm sai MST.
5. **Khử bản ghi trùng hoàn toàn khi bài yêu cầu đếm nghiệm theo ID.** Có thể làm mất những lựa chọn cạnh vật lý khác nhau.
6. **Xem (u,v) và (v,u) là hai loại cạnh khác nhau trong đồ thị vô hướng** khi mục tiêu là khử bản ghi lặp; cần chuẩn hóa hai đầu.
7. **Nhầm bản ghi lặp với hai cạnh song song thật.** Quy tắc làm sạch dữ liệu phải dựa trên ngữ nghĩa đầu vào.
8. **Không kiểm tra chu trình bằng DSU trước khi thêm cạnh.** Cạnh song song thứ hai có thể tạo chu trình độ dài 2.
9. **Chỉ sort theo trọng số nhưng test đòi đúng bộ ID cạnh** dù không quy định tie-break. Cần quy tắc tái lập hoặc test theo tính hợp lệ/tổng.
10. **Tin rằng có cạnh cùng trọng số thì chắc chắn có nhiều MST.** Nhiều đồ thị vẫn có MST duy nhất.
11. **Tin rằng comparator có tie-break tạo ra MST duy nhất về mặt toán học.** Nó chỉ chọn một nghiệm nhất định.
12. **Dùng phép trừ long trong comparator**, có thể overflow và xếp cạnh âm/dương sai.
13. **Khởi tạo tổng bằng 0 rồi không cho phép giảm xuống âm**, gây sai bài tối thiểu hóa có cạnh âm.
14. **Bỏ qua đồ thị không liên thông** và tuyên bố có cây khung toàn đồ thị. Phải trả MSF hoặc báo không có MST toàn cục.
15. **Dừng Kruskal khi chọn n−1 cạnh bất chấp đồ thị không liên thông.** Với c>1, MSF chỉ có n−c cạnh; cần xét đầy đủ hoặc biết c trước.
16. **Coi rừng rỗng là MSF tối ưu chỉ vì trọng số tổng nhỏ hơn rừng đầy đủ.** MSF phải khung toàn bộ mỗi thành phần gốc.
17. **Coi một đầu mút của cạnh âm là đặc biệt.** Chi phí cạnh quyết định thứ tự, nhưng DSU quyết định có được thêm hay không.
18. **Nhầm cây khung nhỏ nhất với cây đường đi ngắn nhất.** Hai bài toán dùng mục tiêu khác nhau.
19. **Không kiểm tra đường hợp lệ của một cây n=1.** Cây khung một đỉnh có 0 cạnh, tổng 0, dù có self-loop.
20. **Dùng int cho tổng khi trọng số có thể lớn/âm**, dễ overflow; dùng long và cân nhắc Math.addExact/BigInteger.
21. **Giữ cạnh theo chiều nhập mà dùng tie-break không nhất quán.** Chuẩn hóa min/max cho đồ thị vô hướng.
22. **Không xử lý ID cạnh khi có nhiều cạnh giống hệt nhau** và muốn khôi phục hoặc kiểm tra đúng cạnh được chọn.
23. **Chỉ kiểm thử đồ thị liên thông với trọng số dương khác nhau.** Bỏ qua hầu hết lỗi về âm, song song, tie và rừng.
24. **Coi MST có tổng âm là lỗi.** Giá trị âm hoàn toàn hợp lệ nếu tổng trọng số các cạnh được chọn âm.

## 15. Các trường hợp nên kiểm thử

| Dữ liệu | Điều cần xác minh |
|---|---|
| Ba đỉnh với trọng số −3, 0, 4 | MST gồm −3 và 0, tổng −3 |
| Hai đỉnh có hai cạnh cùng trọng số | Chọn đúng một; tổng bằng trọng số đó |
| Hai đỉnh có hai cạnh −1 và 3 | Chọn cạnh −1 |
| Self-loop trọng số −100 | Không bao giờ chọn |
| Chu trình ba cạnh đều âm | Chỉ chọn hai cạnh, không lấy cả chu trình |
| Hình vuông cạnh bằng 1 | Nhiều MST, mỗi MST có 3 cạnh, tổng 3 |
| Một đường mà các cạnh bằng nhau | Có thể vẫn có MST duy nhất |
| Đồ thị không cạnh với n=3 | MSF có 3 cây đơn, 0 cạnh, tổng 0 |
| Đồ thị rỗng n=0 | 0 thành phần, 0 cạnh; không có cây khung theo quy ước API |
| Một đỉnh có self-loop âm | MST gồm một đỉnh, 0 cạnh, tổng 0 |
| Cụm có cạnh âm và đỉnh cô lập | MSF tối ưu từng thành phần, không có MST chung |
| Đảo thứ tự dòng input | Tổng không đổi; ID có thể đổi |
| Nhiều cạnh bằng trọng số trong chu trình | Bộ cạnh chọn phụ thuộc tie-break, tổng phải như nhau |
| Tổng cạnh vượt miền long | Phát hiện overflow, không trả tổng sai |

Nếu có thể, kiểm tra Kruskal bằng **hai oracle độc lập**: **Prim** trên cùng dữ liệu và **brute force** trên đồ thị rất nhỏ. So sánh tổng và tính hợp lệ của rừng, không ép các thuật toán có cùng danh sách ID trong trường hợp hòa.

### Bài tập suy luận nhanh

**Câu 1.** Kruskal có cần mọi trọng số không âm không?

**Đáp án:** Không. Chỉ cần thứ tự so sánh trọng số và phép chọn cạnh an toàn qua lát cắt. Cạnh âm hợp lệ.

**Câu 2.** Nếu self-loop nặng −100 xuất hiện đầu danh sách, có phải chọn không?

**Đáp án:** Không. Hai đầu cùng một đỉnh nên DSU.union(u,u) không thể nối hai thành phần; self-loop không thuộc cây.

**Câu 3.** Hai cạnh song song u--v có trọng số −2 và 5 thì cạnh nào có thể được chọn trước?

**Đáp án:** Kruskal xét −2 trước và chọn nếu u,v còn ở hai thành phần rời nhau. Cạnh 5 sau đó bị bỏ nếu chúng đã được nối.

**Câu 4.** Hai cạnh trùng hoàn toàn có thể được đưa cùng một lúc vào MST không?

**Đáp án:** Không nếu chúng nối cùng hai đỉnh của đồ thị vô hướng. Khi một cạnh đã nối hai tập DSU, cạnh kia tạo chu trình và bị bỏ.

**Câu 5.** Nếu tất cả cạnh của hình vuông đều có trọng số 1, tổng MST là bao nhiêu?

**Đáp án:** 3, vì cần ba cạnh để nối bốn đỉnh và mỗi cạnh có trọng số 1. Có nhiều bộ cạnh khác nhau cùng tổng 3.

**Câu 6.** Có hai cạnh cùng trọng số thì MST chắc chắn không duy nhất?

**Đáp án:** Không. Đồ thị đường thẳng có đúng n−1 cạnh thì mọi cạnh đều bắt buộc, kể cả nếu bằng trọng số.

**Câu 7.** Với đồ thị 8 đỉnh có 3 thành phần trong ví dụ, MSF có bao nhiêu cạnh?

**Đáp án:** n−c=8−3=**5**; tổng tối ưu là **−4**.

**Câu 8.** Điều gì giúp Kruskal trả kết quả theo ID giống nhau giữa các lần chạy?

**Đáp án:** Cố định khóa sort (trọng số, hai đầu chuẩn hóa, ID), cùng quy ước đánh số ID cạnh và cùng cách xử lý cạnh song song.

**Câu 9.** Dùng Prim từ một đỉnh trên đồ thị không liên thông có đủ để tìm MSF không?

**Đáp án:** Không. Phải khởi chạy lại trên các thành phần chưa thăm hoặc thiết kế biến thể xử lý mọi đỉnh.

**Câu 10.** Có thể khử trùng các bản ghi cùng u,v,w trước khi tính giá trị MST không?

**Đáp án:** Nếu đó chỉ là bản sao về chi phí/kết nối, **giá trị tối ưu** không đổi. Nhưng không được làm vậy khi ID cạnh và số nghiệm vật lý là yêu cầu của bài toán.

**Câu 11.** Tại sao phải dùng Math.addExact cho tổng trọng số dài?

**Đáp án:** Để phát hiện khi tổng vượt miền long. Tràn số có thể đổi âm thành dương hoặc ngược lại, khiến báo cáo chi phí không chính xác.

**Câu 12.** Nếu chọn một cạnh nhẹ nhất qua lát cắt có trọng số −7, chứng minh trao đổi còn đúng không?

**Đáp án:** Có. Chỉ cần so sánh −7≤w(f); việc thay cạnh f bằng cạnh không nặng hơn không làm tăng tổng. Dấu âm không ảnh hưởng lập luận.

**Ghi nhớ:** Cây khung nhỏ nhất yêu cầu **nối đủ mỗi thành phần nhưng không có chu trình**. **Trọng số âm không làm Kruskal/Prim sai**. **Cạnh song song và cạnh nhập trùng** cần được hiểu theo ID/ý nghĩa dữ liệu; **self-loop luôn bị loại**. **Cạnh đồng trọng số có thể tạo nhiều MST** nên phải phân biệt **giá trị tối ưu**, **tính duy nhất của nghiệm** và **quy tắc tie-break để xuất kết quả ổn định**.
