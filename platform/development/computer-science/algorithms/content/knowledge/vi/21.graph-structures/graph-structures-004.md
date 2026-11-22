# Thành phần liên thông mạnh và đồ thị thu gọn

## 1. Vì sao cần phân tích cấu trúc liên thông trong đồ thị có hướng?

Trong đồ thị **vô hướng**, hai đỉnh được gọi là liên thông nếu có một đường đi giữa chúng; quan hệ này chia các đỉnh thành các **thành phần liên thông**. Trong đồ thị **có hướng**, việc đi được từ u đến v **không** đảm bảo đi ngược từ v về u. Vì thế cần khái niệm chặt chẽ hơn: **thành phần liên thông mạnh (Strongly Connected Component – SCC)**.

Hai đỉnh u và v được coi là **liên thông mạnh** nếu:

- Có một đường đi theo đúng hướng cạnh từ u tới v.
- Đồng thời có một đường đi theo đúng hướng cạnh từ v tới u.

Một SCC là **tập tối đại các đỉnh đôi một liên thông mạnh**. Tối đại nghĩa là không thể thêm một đỉnh khác vào tập mà vẫn giữ tính chất ấy.

Ví dụ:

~~~text
0 -> 1 -> 2
^         |
|_________|

2 -> 3 -> 4
     ^    |
     |____|

4 -> 5
~~~

Các đỉnh 0,1,2 có đường đi cả hai chiều giữa mọi cặp, nên tạo một SCC. Các đỉnh 3,4 tạo SCC khác. Nếu không có đường từ 5 quay về 4, thì 5 thuộc SCC riêng, dù có đường đi 0→...→5. **Khả năng tới được một chiều không đủ để nhập hai SCC**.

SCC đặc biệt hữu ích để hiểu **vòng phụ thuộc**, các nhóm trạng thái có thể quay trở lại nhau, và cấu trúc thứ tự giữa những nhóm mà ta không thể sắp thẳng từng đỉnh do có chu trình.

Các ứng dụng thường gặp:

- Phát hiện các nhóm module/phần mềm có quan hệ phụ thuộc vòng.
- Tìm những trạng thái trong hệ thống mà có thể đi qua lại bằng các chuyển trạng thái có hướng.
- Phân nhóm trang/đỉnh có thể truy cập lẫn nhau rồi phân tích luồng chuyển giữa nhóm.
- Rút gọn một bài toán reachability lớn thành các quan hệ giữa **những thành phần**.
- Chuẩn bị cho quy hoạch động trên **DAG của các SCC**, phân tích nguồn/đích hay chuỗi phụ thuộc.

Kết quả quan trọng: sau khi nén mỗi SCC thành **một siêu đỉnh**, đồ thị thu gọn luôn là **DAG – đồ thị có hướng không chu trình**, dù đồ thị gốc có thể chứa rất nhiều chu trình.

## 2. Định nghĩa chính xác và tính chất của SCC

Cho đồ thị có hướng G=(V,E). Viết u⇝v nếu tồn tại đường đi có hướng từ u đến v. Cho phép **đường đi độ dài 0** từ một đỉnh tới chính nó: u⇝u luôn đúng. Định nghĩa:

~~~text
u ~ v khi va chi khi (u ⇝ v) AND (v ⇝ u).
~~~

Quan hệ ~ là một **quan hệ tương đương**:

1. **Phản xạ:** mỗi u đi tới chính nó bằng đường đi độ dài 0, nên u~u.
2. **Đối xứng:** nếu u⇝v và v⇝u thì đổi chỗ hai vế vẫn đúng, nên u~v suy ra v~u.
3. **Bắc cầu:** nếu u~v và v~w thì ghép đường u⇝v với v⇝w được u⇝w; chiều ngược w⇝v⇝u cũng tồn tại, nên u~w.

Vì là quan hệ tương đương, nó phân hoạch **toàn bộ tập đỉnh V** thành các lớp không giao nhau. Mỗi lớp tương đương chính là một SCC. Từ đó:

- Mỗi đỉnh thuộc **đúng một** SCC.
- Hai SCC khác nhau không có chung đỉnh.
- Hợp tất cả các SCC là V.
- Mỗi SCC khác rỗng.
- Nếu hai đỉnh ở cùng SCC, ta có thể đi qua lại giữa chúng.
- Nếu hai đỉnh ở các SCC khác nhau, chúng **không thể** cùng lúc đi tới nhau theo cả hai chiều.

### Một đỉnh đứng riêng cũng là một SCC

Ngay cả một đỉnh cô lập v không có cạnh nào vẫn tạo SCC **{v}**, vì có đường đi độ dài 0 từ v tới v. Đỉnh v có self-loop v→v cũng có thể tạo SCC một đỉnh **{v}** nếu không thể ghép với đỉnh khác thành nhóm liên thông mạnh lớn hơn.

**Self-loop là chu trình**, nhưng **không làm SCC một đỉnh trở thành SCC nhiều đỉnh**. Nếu một bài yêu cầu “SCC có chu trình”, cần phân biệt:

- SCC có **từ hai đỉnh trở lên** chắc chắn chứa một chu trình.
- SCC có **một đỉnh** chứa chu trình có hướng nếu có **self-loop**.
- SCC một đỉnh **không có self-loop** không chứa chu trình có độ dài cạnh dương, dù đỉnh đó được xem là liên thông mạnh với chính nó theo đường độ dài 0.

### Mạnh, yếu và không liên thông

Đồ thị có hướng còn có khái niệm **thành phần liên thông yếu**: tạm bỏ hướng các cạnh, rồi tìm thành phần liên thông vô hướng.

Ví dụ 0→1→2:

~~~text
SCC:  {0}, {1}, {2}
Weak connected component: {0,1,2}
~~~

Dù 0 đi được tới 2, 2 không quay lại 0, nên không được gom cả ba thành một SCC. Một BFS/DFS thường từ 0 có thể thăm cả ba nhưng kết quả thăm ấy **không phải một SCC**.

## 3. Ví dụ chính: năm SCC trong đồ thị chín đỉnh

Ta dùng đồ thị có hướng gồm các đỉnh 0..8 với những cạnh:

~~~text
0 -> 1
1 -> 2
2 -> 0          (chu trinh 0,1,2)

2 -> 3
0 -> 3          (hai canh khac nhau tu nhom A sang nhom B)
3 -> 4
4 -> 3          (chu trinh 3,4)

4 -> 5
3 -> 5          (hai canh tu B sang C)

2 -> 6
6 -> 7
7 -> 6          (chu trinh 6,7)
7 -> 5

5 -> 8
~~~

Các SCC chính xác là:

~~~text
A = {0,1,2}
B = {3,4}
C = {5}
D = {6,7}
E = {8}
~~~

Vì sao?

- Trong A, các đỉnh 0→1→2→0 tạo một vòng; mọi đỉnh có thể đi tới mọi đỉnh.
- Trong B, có cả 3→4 và 4→3.
- Trong D, có cả 6→7 và 7→6.
- C={5} và E={8} là các SCC một đỉnh, vì không có đường ngược đủ để ghép với nhóm khác.
- Từ A đi tới B hoặc D, từ B và D đều có đường tới C, rồi C tới E; nhưng **không có cạnh quay từ các nhóm sau về A**. Vì thế không được gộp các nhóm thành SCC lớn hơn.

Một cách tóm tắt quan hệ giữa nhóm:

~~~text
A ----> B ----> C ----> E
 \               ^
  \----> D ------|
~~~

Mọi mũi tên ở hình nhóm là **cạnh của đồ thị thu gọn**. Hình không mô tả tất cả cạnh bên trong từng SCC mà chỉ giữ những cạnh **giữa các nhóm khác nhau**.

**Tư duy phân tích:** bên trong một SCC có thể có nhiều cách đi vòng, nhưng giữa các SCC không thể có vòng khép kín. Chính điều này giúp biến một đồ thị có chu trình thành một cấu trúc DAG dễ phân tích hơn.

## 4. Cách giải chậm và động cơ cần thuật toán O(V+E)

Một ý tưởng trực tiếp là chạy DFS hoặc BFS từ **từng đỉnh** để tính khả năng đi tới:

~~~text
reachable[u][v] = true neu u co duong di toi v

u va v cung SCC
    khi reachable[u][v] AND reachable[v][u].
~~~

Với đồ thị nhỏ, ta có thể tính mọi cặp reachability rồi gom theo quan hệ tương đương. Nhưng chạy BFS/DFS từ từng đỉnh có thể tốn O(V×(V+E)) thời gian và O(V²) bộ nhớ nếu lưu ma trận reachable. Floyd–Warshall cũng có thể xác định reachability với O(V³), không phù hợp với đồ thị lớn.

Có hai thuật toán kinh điển **O(V+E)** để tìm SCC trên danh sách kề:

- **Kosaraju:** hai lần DFS, lần thứ hai trên **đồ thị chuyển vị (transpose)** và theo thứ tự giảm thời điểm hoàn tất.
- **Tarjan:** một lần DFS, duy trì chỉ số thăm và **low-link**, sử dụng stack để tách SCC tại các điểm gốc thích hợp.

Bài sẽ giải thích cả hai, triển khai Java 17 **Kosaraju** để có code rõ ràng; sau đó dựng **đồ thị thu gọn** và sắp thứ tự topo trên đồ thị này. Không cần chạy một DFS từ mọi đỉnh như phương án chậm.

## 5. Đồ thị chuyển vị (transpose) và vì sao cần đảo cạnh

Với G=(V,E), **đồ thị chuyển vị Gᵀ** giữ nguyên tập đỉnh V nhưng **đảo chiều tất cả các cạnh**:

~~~text
Neu G co canh  u -> v
thi G^T co canh v -> u.
~~~

Ví dụ:

~~~text
G:    0 -> 1 -> 2
G^T:  0 <- 1 <- 2
~~~

Nếu G có hai cạnh song song u→v thì Gᵀ có hai cạnh v→u; nếu G có self-loop u→u thì khi đảo vẫn là u→u.

### Hai tính chất quan trọng

1. **SCC không đổi khi đảo tất cả các cạnh.** Nếu u⇝v và v⇝u trong G, đảo hướng các đường ấy cho ta v⇝u và u⇝v trong Gᵀ. Quan hệ liên thông mạnh vẫn như cũ.
2. **Chiều cạnh giữa các SCC đảo lại.** Nếu có cạnh từ SCC A tới SCC B trong G, sẽ có cạnh từ B tới A trong Gᵀ.

Vì vậy Gᵀ làm cho việc đi ra khỏi một SCC theo hướng không mong muốn trở nên dễ kiểm soát khi ta duyệt SCC theo đúng thứ tự. Đây là lý do Kosaraju dùng transpose ở lượt DFS thứ hai.

### Cách dựng bằng danh sách kề

~~~text
transpose = list of V empty lists

for u from 0 to V-1:
    for v in adj[u]:
        transpose[v].add(u)
~~~

Tốn O(V+E) thời gian và bộ nhớ O(V+E) cho graph chuyển vị.

**Lưu ý:** không thể đảo cạnh chỉ bằng cách đảo thứ tự phần tử trong danh sách kề của từng đỉnh. Phải đổi **đỉnh đầu và đỉnh cuối** của mỗi cạnh.

## 6. Kosaraju – hai lần DFS để xác định các SCC

Kosaraju hoạt động theo ba bước chính.

### Bước 1: DFS trên G và lưu thứ tự hoàn tất

Duyệt mọi đỉnh chưa thăm trên G bằng DFS. Khi đã duyệt **xong mọi cạnh đi ra và mọi hậu duệ**, mới thêm đỉnh u vào danh sách finishOrder.

~~~text
dfsFinish(u):
    visited[u] = true
    for v in adj[u]:
        if not visited[v]:
            dfsFinish(v)
    finishOrder.add(u)  // Postorder: sau khi xu ly xong.
~~~

Vòng ngoài:

~~~text
for u from 0 to V-1:
    if not visited[u]:
        dfsFinish(u)
~~~

**Phải thêm đỉnh khi thoát DFS**, không phải khi mới vào. Thứ tự vào (preorder) nói đỉnh nào được khám phá trước; thuật toán Kosaraju cần **thứ tự giảm thời điểm hoàn tất**.

Trên ví dụ 9 đỉnh, với thứ tự cạnh đã liệt kê và DFS bắt đầu từ đỉnh 0, một danh sách hoàn tất có thể là:

~~~text
finishOrder = [8,5,4,3,7,6,2,1,0]
~~~

Do đó lượt 2 xét các đỉnh theo chiều ngược:

~~~text
[0,1,2,6,7,3,4,5,8]
~~~

Không phải dữ liệu nào cũng cho finishOrder như trên; nó phụ thuộc thứ tự xét đỉnh/cạnh. Nhưng khi triển khai đúng, **phân hoạch SCC không phụ thuộc thứ tự ấy**.

### Bước 2: Dựng Gᵀ

Đảo mọi cạnh của đồ thị ban đầu. Đặt lại visited toàn false cho lượt thứ hai. Không được dùng lại mảng visited từ lượt 1 mà không reset, vì lượt 1 đã thăm tất cả đỉnh.

### Bước 3: DFS trên Gᵀ theo thứ tự giảm hoàn tất

Lấy lần lượt các đỉnh trong finishOrder **từ cuối về đầu**. Nếu một đỉnh chưa visited ở lượt 2, chạy DFS trên Gᵀ từ đó; **toàn bộ các đỉnh gom được trong một lần DFS chính là một SCC**.

~~~text
clear visited
components = []

for i from finishOrder.size()-1 down to 0:
    u = finishOrder[i]
    if visited[u]:
        continue

    currentComponent = []
    dfsCollectOnTranspose(u, currentComponent)
    components.add(currentComponent)
~~~

**Kết quả:** components là một phân hoạch toàn bộ đỉnh thành các SCC. Mỗi đỉnh chỉ được DFS thăm một lần trên mỗi lượt. Tính cả dựng Gᵀ, thời gian O(V+E).

### Vì sao thứ tự giảm hoàn tất rất quan trọng?

Xét đồ thị 0→1 không có cạnh ngược. Hai SCC là {0} và {1}. Khi DFS trên G từ 0, ta hoàn tất 1 trước rồi mới 0, nên thứ tự giảm hoàn tất bắt đầu ở 0.

Trong Gᵀ có cạnh 1→0. Bắt đầu lượt 2 ở 0, DFS không thể đi tới 1 nên thu đúng {0}; lượt sau thu {1}. Nếu bắt đầu sai ở 1, DFS trên Gᵀ đi được tới 0 và có thể **gộp sai cả hai thành một nhóm**.

Quy tắc giảm thời điểm hoàn tất chính là điều ngăn DFS lượt 2 vượt sang một SCC khác chưa được tách.

## 7. Tại sao Kosaraju đúng?

Xét **đồ thị thu gọn theo SCC** (sẽ định nghĩa đầy đủ ở phần 10). Đồ thị ấy luôn là DAG; trong G, một cạnh giữa SCC A và SCC B tạo cung A→B.

**Quan sát:** trong DFS lượt 1, với một cung A→B giữa hai SCC khác nhau, thời điểm hoàn tất **lớn nhất** của A lớn hơn thời điểm hoàn tất lớn nhất của B. Lập luận xét hai tình huống:

- Nếu DFS đi vào A trước khi duyệt B, từ A có thể đi tới B; toàn bộ phần thuộc B được hoàn tất trước khi đóng lời gọi DFS chứa A.
- Nếu DFS đi vào B trước, do không có đường từ B quay lại A (nếu có thì hai nhóm liên thông mạnh và phải gộp), B sẽ được hoàn tất trước; sau đó A được duyệt, nên vẫn hoàn tất muộn hơn B.

Vì vậy trên DAG của các SCC, một SCC có thể được chọn theo thứ tự **giảm thời điểm hoàn tất** sao cho nó là **nguồn** của phần DAG còn chưa xử lý.

Khi đảo toàn bộ cạnh thành Gᵀ, SCC nguồn đó trở thành SCC **không có cạnh đi ra** tới những SCC chưa tách trong đồ thị chuyển vị. Do đó DFS ở lượt 2 bắt đầu từ một đỉnh thuộc SCC ấy **không thể thoát ra ngoài SCC chưa xử lý**, nhưng vì các đỉnh bên trong SCC đi được lẫn nhau, DFS sẽ thăm **hết các đỉnh trong SCC**.

Sau khi đánh dấu xong SCC ấy, chọn đỉnh có thời điểm hoàn tất lớn tiếp theo chưa được thăm và lặp lại lập luận trên đồ thị còn lại. Cuối cùng mọi SCC được lấy ra đúng một lần.

Đây là lý do cả **transpose** và **thứ tự giảm hoàn tất** đều bắt buộc. Nếu thiếu một trong hai, DFS có thể vượt qua một cạnh giữa các SCC và trộn chúng, hoặc tách nhầm một SCC.

**Cần phân biệt:** đây là trực giác chứng minh cho thứ tự DFS trong Kosaraju trên SCC condensation DAG, không nói thứ tự các đỉnh in ra là một thứ tự topo của **đồ thị gốc**. Đồ thị gốc có thể có chu trình, nên không có topo ở mức từng đỉnh; chỉ đồ thị thu gọn mới là DAG.

## 8. Tarjan – một lượt DFS với discovery time và low-link

**Tarjan** là thuật toán SCC O(V+E) khác, chỉ cần một lượt DFS trên đồ thị G, **không cần xây Gᵀ**. Tarjan duy trì:

- index[u] / discovery[u]: thứ tự thời điểm u được khám phá; ban đầu -1.
- low[u]: chỉ số khám phá nhỏ nhất có thể đạt tới theo các quy tắc đường DFS liên quan tới các đỉnh **vẫn đang ở trên stack SCC**.
- stack: lưu các đỉnh đã khám phá nhưng **chưa được gán vào SCC hoàn tất**.
- onStack[u]: u hiện thuộc stack SCC hay không.

Giả mã:

~~~text
dfsTarjan(u):
    index[u] = low[u] = nextIndex++
    stack.push(u)
    onStack[u] = true

    for v in adj[u]:
        if index[v] == -1:
            dfsTarjan(v)
            low[u] = min(low[u], low[v])
        else if onStack[v]:
            low[u] = min(low[u], index[v])

    if low[u] == index[u]:
        start a new SCC
        repeat:
            v = stack.pop()
            onStack[v] = false
            add v to SCC
        until v == u
~~~

Vòng ngoài chạy dfsTarjan trên mọi đỉnh chưa thăm.

### Hai dạng cập nhật low-link không giống nhau

Nếu v là đỉnh **chưa khám phá**, DFS đi xuống v rồi dùng **low[v]** để đưa kết quả của cây con ngược lên u.

Nếu v đã khám phá và **vẫn trên stack**, có cạnh u→v nối tới một đỉnh đang xét trong phần chưa tách SCC. Lúc ấy dùng **index[v]** để cập nhật low[u], không đơn giản thay bằng low[v] ở mọi trường hợp.

Nếu v đã khám phá nhưng **không còn trên stack**, SCC chứa v đã được chốt. Không dùng cạnh u→v để giảm low[u], vì làm vậy có thể gộp nhầm các SCC đã hoàn tất.

Khi low[u]==index[u], u là đỉnh gốc của một SCC trong cấu trúc DFS hiện tại. Pop từ stack cho tới u sẽ thu đúng các đỉnh thuộc SCC đó.

### Kosaraju hay Tarjan?

| Khía cạnh | Kosaraju | Tarjan |
| --- | --- | --- |
| Số lượt DFS | Hai | Một |
| Cần đồ thị chuyển vị | Có | Không |
| Trạng thái chính | visited, finishOrder, transpose | index, low, stack, onStack |
| Tính giải thích | Trực quan qua đảo cạnh và postorder | Gọn hơn về số lượt nhưng low-link tinh tế |
| Độ phức tạp | O(V+E) | O(V+E) |
| Độ sâu đệ quy | Có thể tới O(V) | Có thể tới O(V) |
| Dùng khi | Dễ triển khai, dễ kiểm từng bước | Không muốn dựng transpose, cần một lượt DFS |

Trong Java 17 demo của bài, dùng **Kosaraju** để dễ thấy ranh giới giữa tìm SCC và xây đồ thị thu gọn. Tarjan được giới thiệu đầy đủ về cơ chế để người học biết chọn kỹ thuật phù hợp khi cần tối ưu bộ nhớ của transpose.

## 9. Đánh số SCC một cách ổn định

Các thuật toán SCC thường trả về **đúng tập các nhóm**, nhưng **thứ tự nhóm và thứ tự đỉnh bên trong nhóm không cố định**. Chẳng hạn hai kết quả sau biểu diễn **cùng một phân hoạch**:

~~~text
[[0,1,2],[3,4],[5],[6,7],[8]]
[[8],[7,6],[5],[4,3],[2,1,0]]
~~~

Không nên kiểm thử tính đúng bằng cách so nguyên văn thứ tự các nhóm nếu thuật toán không quy định thứ tự.

Để có output dễ tái lập, mã Java sẽ **chuẩn hóa**:

1. Sắp các đỉnh **tăng dần** trong mỗi SCC.
2. Sắp danh sách SCC theo **đỉnh nhỏ nhất** trong nhóm tăng dần.
3. Gán id thành phần từ 0 tới K-1 theo thứ tự chuẩn hóa.
4. Dựng mảng componentOf[v] = id của SCC chứa v.

Với đồ thị 9 đỉnh ở phần 3:

~~~text
components = [[0,1,2],[3,4],[5],[6,7],[8]]
componentOf = [0,0,0,1,1,2,3,3,4]
~~~

Cách chuẩn hóa làm cho componentOf và thứ tự in ra dễ kiểm chứng, **không phải phần bắt buộc để Kosaraju đúng**. Nếu cần tối ưu thời gian tuyến tính thuần túy, có thể giữ id SCC tùy thứ tự phát hiện và không sắp xếp.

### Độ phức tạp của chuẩn hóa

Bản Kosaraju cơ bản O(V+E). Việc sắp thứ tự các đỉnh trong các nhóm có thể tốn thêm O(V log V) trong trường hợp xấu, và sắp K nhóm có thể tốn O(K log K). Trong phần dựng condensation bằng TreeSet ở mã demo, có thêm chi phí O(E log(K+1)) theo cận trên. Đây là **chi phí cho tính dễ đọc/tất định của ví dụ**, không phải độ phức tạp bắt buộc của việc tìm SCC.

## 10. Đồ thị thu gọn (condensation graph) là gì?

Giả sử đã có K SCC: C0,C1,...,C(K-1). **Đồ thị thu gọn** H được tạo như sau:

- Mỗi SCC Ci trở thành **một siêu đỉnh (super-vertex)** i của H.
- Với mỗi cạnh gốc u→v, đặt a=componentOf[u], b=componentOf[v].
- Nếu a==b: cạnh nằm **bên trong SCC**, **không thêm self-loop** vào đồ thị thu gọn.
- Nếu a!=b: thêm cạnh có hướng a→b vào H.
- Nếu nhiều cạnh gốc tạo cùng một cặp a→b, thường **gộp thành một cạnh duy nhất** cho bài toán cấu trúc/reachability.

~~~text
for each SCC id c:
    condensation[c] = empty set

for each original edge u -> v:
    a = componentOf[u]
    b = componentOf[v]

    if a != b:
        condensation[a].add(b)
~~~

**Không nên thêm cạnh a→a khi a==b**: trong đồ thị gốc, một SCC thường chứa chu trình, nhưng ta cố ý nén toàn bộ các bước đi trong SCC thành **một siêu đỉnh**. Nếu giữ self-loop nội bộ, đồ thị thu gọn không còn là DAG theo định nghĩa thông thường.

### Kết quả với ví dụ 9 đỉnh

Với quy ước id được chuẩn hóa ở phần 9:

~~~text
SCC 0 = {0,1,2}  (A)
SCC 1 = {3,4}    (B)
SCC 2 = {5}      (C)
SCC 3 = {6,7}    (D)
SCC 4 = {8}      (E)
~~~

Cạnh giữa các SCC là:

~~~text
0 -> 1
0 -> 3
1 -> 2
3 -> 2
2 -> 4
~~~

Danh sách kề của condensation, đã gộp cạnh trùng và sắp id tăng dần:

~~~text
0: [1,3]
1: [2]
2: [4]
3: [2]
4: []
~~~

Đồ thị này **không có chu trình**. Một thứ tự topo hợp lệ, khi dùng thuật toán Kahn với queue FIFO và thứ tự láng giềng tăng dần, là:

~~~text
[0,1,3,2,4]
~~~

Ta có thể làm một công việc tương ứng với SCC 0 trước, rồi SCC 1 và SCC 3 theo một thứ tự phù hợp; cả SCC 1 và SCC 3 phải xong trước SCC 2, SCC 2 phải xong trước SCC 4.

**Ý nghĩa của thứ tự topo:** thứ tự này đúng cho **các SCC như một đơn vị**, không tuyên bố các đỉnh bên trong SCC 0, SCC 1 hay SCC 3 có thể xếp topo với mọi cạnh nội bộ. Những SCC có chu trình vốn không có thứ tự topo nội bộ hợp lệ nếu yêu cầu thỏa tất cả cạnh.

## 11. Vì sao đồ thị thu gọn luôn là DAG?

Đây là định lý cấu trúc quan trọng nhất khi học SCC.

**Giả sử ngược lại** condensation H có chu trình gồm các SCC khác nhau:

~~~text
C0 -> C1 -> C2 -> ... -> Ck -> C0
~~~

Với mỗi cạnh Ci→Ci+1 của H, tồn tại ít nhất một cạnh gốc u→v đi từ một đỉnh thuộc Ci tới một đỉnh thuộc Ci+1. **Bên trong mỗi SCC**, mọi cặp đỉnh có đường đi cả hai chiều, nên ta có thể di chuyển từ bất kỳ đỉnh nào của Ci tới điểm đầu của cạnh ra tiếp theo.

Ghép các đường đi **nội bộ SCC** với các cạnh **giữa SCC** dọc chu trình H, ta được đường đi có hướng từ mọi SCC trong chu trình tới SCC tiếp theo và cuối cùng quay về SCC ban đầu. Đi theo chu trình hướng ngược về mặt vị trí cũng có thể được thực hiện bằng việc tiếp tục đi xuôi qua đủ các cung để trở lại đỉnh cần đến.

Do vậy mọi đỉnh thuộc các SCC C0,...,Ck đều có đường đi cả hai chiều với nhau. Theo định nghĩa, chúng phải nằm trong **cùng một SCC lớn hơn**, trái với giả định chúng là những SCC khác nhau **tối đại**.

Mâu thuẫn chứng minh **H không thể có chu trình có hướng**. Vì vậy condensation luôn là DAG, và luôn có ít nhất một thứ tự topo.

### Ba hệ quả ứng dụng

1. **Có thể chạy quy hoạch động trên condensation.** Vì H là DAG, ta có thể xử lý các thành phần theo thứ tự topo hoặc theo chiều ngược, tùy công thức DP.
2. **Có thể xem SCC như đơn vị vòng lặp tối đại.** Chu trình nằm trong SCC; sự di chuyển giữa các SCC không bao giờ tạo vòng quay lại SCC đã rời nếu chỉ đi theo hướng cạnh.
3. **Có thể phân tích các thành phần nguồn/đích.** SCC nguồn là siêu đỉnh indegree=0 trên H; SCC đích là siêu đỉnh outdegree=0. Một DAG hữu hạn không rỗng luôn có ít nhất một nguồn và ít nhất một đích.

**Điểm hay bị nhầm:** condensation là DAG **bất kể** đồ thị gốc có bao nhiêu chu trình. Nói “đồ thị gốc có chu trình nên topo condensation không tồn tại” là sai. Đồ thị gốc và đồ thị thu gọn là hai mức độ mô hình khác nhau.

## 12. Reachability được bảo toàn ở cấp thành phần

Dùng componentOf[u] để ánh xạ từ đỉnh gốc u sang SCC c của nó. Với hai đỉnh u,v:

> Tồn tại đường đi có hướng u⇝v trong G **khi và chỉ khi** có đường đi componentOf[u]⇝componentOf[v] trong H.

Hiểu rằng nếu u,v cùng SCC thì một đường đi độ dài 0 từ c đến chính c là đủ cho phát biểu ở cấp thành phần, còn trong G mọi đỉnh của SCC thực sự đi được tới nhau.

**Chiều thuận:** mỗi cạnh trên một đường từ u tới v hoặc nằm trong cùng SCC (không đổi siêu đỉnh), hoặc đi từ SCC a sang SCC b và tạo cạnh a→b trong H. Bỏ qua các bước nội bộ, ta được đường đi giữa hai SCC trong H.

**Chiều ngược:** với một đường đi giữa các SCC C0→C1→...→Ct trên H, mỗi cung tương ứng với một cạnh gốc giữa hai SCC. Nhờ tính liên thông mạnh bên trong mỗi SCC, ta có thể nối các cạnh gốc bằng đường đi nội bộ để đi từ u ở C0 tới v ở Ct.

Vì vậy, nếu có rất nhiều truy vấn reachability trên một đồ thị tĩnh, ta có thể phân tích SCC một lần rồi chạy các thuật toán thích hợp trên DAG H. Nhưng **không phải lúc nào** việc nén SCC cũng giảm mọi truy vấn về O(1): nếu hai đỉnh thuộc SCC khác nhau, vẫn phải kiểm tra có đường đi trong condensation hay không.

### Cùng SCC không có nghĩa chỉ có một đường đi ngắn nhất

Hai đỉnh trong cùng SCC đi tới nhau hai chiều, nhưng khoảng cách ngắn nhất giữa chúng có thể khác theo hai hướng; và việc nén cả SCC thành một đỉnh sẽ làm mất thông tin chi tiết về số cạnh/chi phí nội bộ.

Do đó **condensation bảo toàn reachability**, không tự bảo toàn **độ dài đường đi ngắn nhất giữa các đỉnh gốc**. Nếu bài yêu cầu đường ngắn nhất có trọng số, cần giữ thông tin cạnh/chi phí nội bộ hoặc dùng một mô hình khác thay vì coi mỗi siêu đỉnh là một bước có chi phí 0.

### Ví dụ ứng dụng trên graph mẫu

0 và 2 cùng SCC 0 nên có đường đi cả hai hướng. 2 và 5 khác SCC (0 và 2); ta có đường đi 2→3→5 hoặc 2→6→7→5, nhưng không có đường đi từ 5 về 2. Do đó 2 và 5 **không** liên thông mạnh.

Ở condensation có đường đi 0→1→2 hoặc 0→3→2, nên mọi đỉnh thuộc SCC 0 đều có đường đi tới SCC 2. Tuy nhiên, do H là DAG không có đường từ 2 quay về 0 nên không thể nhập hai SCC đó.

## 13. Topo và quy hoạch động trên đồ thị thu gọn

Khi đã có condensation H và K siêu đỉnh, ta có thể dùng **Kahn**:

1. Tính indegree của mỗi siêu đỉnh.
2. Đưa tất cả đỉnh có indegree=0 vào queue.
3. Lần lượt lấy một đỉnh, ghi vào thứ tự, xóa ảnh hưởng của các cạnh đi ra.
4. Kết quả phải chứa đủ K siêu đỉnh, vì H luôn là DAG.

Ví dụ H:

~~~text
0 -> 1 -> 2 -> 4
 \         ^
  -> 3 ---|
~~~

Topo theo thứ tự FIFO ở bài là [0,1,3,2,4]. Trong một bài toán “mỗi SCC có trọng số”, có thể dùng topo để tính các giá trị động.

**Ví dụ minh họa – số thành phần lớn nhất trên một đường đi:** đặt dp[c] là số **siêu đỉnh** nhiều nhất trên một đường đi kết thúc tại c; ban đầu dp[c]=1. Khi xét cạnh c→v theo thứ tự topo:

~~~text
dp[v] = max(dp[v], dp[c] + 1)
~~~

Trên ví dụ, đường 0→1→2→4 có 4 siêu đỉnh; đường 0→3→2→4 cũng có 4 siêu đỉnh. Đây là bài đếm **số SCC** trên đường đi trong condensation, không phải số đỉnh/cạnh tối đa trên một đường đi **đơn** trong đồ thị gốc.

Nếu mỗi SCC có trọng số w[c] là số đỉnh trong nhóm hoặc tổng điểm của nhóm, có thể thay công thức thành:

~~~text
dp[v] = max(dp[v], dp[c] + w[v])
~~~

với dp[c] khởi tạo theo các nguồn phù hợp với ý nghĩa bài. Chỉ dùng cách này khi có quyền coi mỗi SCC như một **đơn vị điểm** có thể thu được trọn vẹn. Với một bài chỉ cho đường đi **đơn** không lặp đỉnh, không thể mặc định rằng vào một SCC sẽ đi qua tất cả đỉnh trong SCC mà không lặp.

### Nhiều topo hợp lệ

Kahn có thể cho nhiều thứ tự topo tùy thứ tự ưu tiên giữa các SCC hiện cùng indegree=0. Kết quả đó không ảnh hưởng tính DAG hoặc khả năng xử lý dependency; khi cần output tất định, sắp xếp danh sách kề/ưu tiên id nhỏ nhất.

Một số hệ thống yêu cầu “tính công việc theo vòng phụ thuộc”: SCC giúp **phát hiện** nhóm phụ thuộc vòng; không có nghĩa tự động có thứ tự chạy bên trong nhóm. Cần quy tắc xử lý chu trình hoặc cách sửa dependency trước khi thực thi từng công việc trong SCC ấy.

## 14. Java 17 – Kosaraju, đồ thị thu gọn và topo chạy độc lập

Chương trình hoàn chỉnh bên dưới:

- Tạo **đồ thị có hướng** từ danh sách cạnh, kiểm tra miền đỉnh.
- Tìm SCC bằng **hai lượt DFS Kosaraju**, lượt thứ hai trên đồ thị chuyển vị.
- Chuẩn hóa đỉnh trong mỗi SCC và thứ tự nhóm để kết quả ổn định.
- Gán mảng componentOf cho mọi đỉnh gốc.
- Dựng condensation, **bỏ cạnh nội bộ** và **gộp cạnh trùng** bằng TreeSet.
- Dùng **Kahn** tìm topo các SCC.
- Thử thêm self-loop, cạnh song song, đỉnh cô lập, đồ thị rỗng và cạnh sai phạm vi.

Lưu toàn bộ mã trong tệp **SccCondensationDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.TreeSet;

public class SccCondensationDemo {

    record SccResult(
            List<List<Integer>> components,
            int[] componentOf,
            List<List<Integer>> condensation,
            List<Integer> topoOrder) {}

    // Moi canh int[]{u,v} mang nghia co huong u -> v.
    static List<List<Integer>> directedGraph(
            int n, int[][] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> graph = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            graph.add(new ArrayList<>());
        }
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException("invalid edge");
            }
            int u = edge[0], v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException("vertex out of range");
            }
            graph.get(u).add(v);
        }
        return graph;
    }

    // Luot DFS 1: ghi dinh SAU khi xu ly xong hau due.
    private static void dfsFinish(
            int u, List<List<Integer>> graph,
            boolean[] visited, List<Integer> finishOrder) {
        visited[u] = true;
        for (int v : graph.get(u)) {
            if (!visited[v]) {
                dfsFinish(v, graph, visited, finishOrder);
            }
        }
        finishOrder.add(u);
    }

    // Luot DFS 2 tren transpose: thu thap mot SCC.
    private static void dfsCollect(
            int u, List<List<Integer>> transpose,
            boolean[] visited, List<Integer> members) {
        visited[u] = true;
        members.add(u);
        for (int v : transpose.get(u)) {
            if (!visited[v]) {
                dfsCollect(v, transpose, visited, members);
            }
        }
    }

    // Kahn tren DAG condensation.
    private static List<Integer> topoOfDag(
            List<List<Integer>> dag) {
        int k = dag.size();
        int[] indegree = new int[k];
        for (List<Integer> outgoing : dag) {
            for (int v : outgoing) {
                indegree[v]++;
            }
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int c = 0; c < k; c++) {
            if (indegree[c] == 0) {
                queue.addLast(c);
            }
        }

        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int c = queue.removeFirst();
            order.add(c);
            for (int v : dag.get(c)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }
        return List.copyOf(order);
    }

    static SccResult analyze(List<List<Integer>> graph) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.size();

        // B1. DFS thu tu HOAN TAT tren graph goc.
        boolean[] visited = new boolean[n];
        List<Integer> finishOrder = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            if (!visited[u]) {
                dfsFinish(u, graph, visited, finishOrder);
            }
        }

        // B2. Dung transpose: dao tat ca cac canh.
        List<List<Integer>> transpose = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            transpose.add(new ArrayList<>());
        }
        for (int u = 0; u < n; u++) {
            for (int v : graph.get(u)) {
                transpose.get(v).add(u);
            }
        }

        // B3. DFS tren transpose, theo giam finish time.
        Arrays.fill(visited, false);
        List<List<Integer>> components = new ArrayList<>();
        for (int i = finishOrder.size() - 1; i >= 0; i--) {
            int start = finishOrder.get(i);
            if (visited[start]) {
                continue;
            }

            List<Integer> members = new ArrayList<>();
            dfsCollect(start, transpose, visited, members);
            Collections.sort(members);
            components.add(List.copyOf(members));
        }

        // Chuan hoa id SCC theo dinh nho nhat.
        components.sort((a, b) ->
                Integer.compare(a.get(0), b.get(0)));
        int k = components.size();
        int[] componentOf = new int[n];
        Arrays.fill(componentOf, -1);
        for (int c = 0; c < k; c++) {
            for (int v : components.get(c)) {
                componentOf[v] = c;
            }
        }

        // B4. Nen SCC: chi giu canh GIUA cac SCC.
        // TreeSet loai canh trung va sap tang id.
        List<TreeSet<Integer>> nextSets = new ArrayList<>();
        for (int c = 0; c < k; c++) {
            nextSets.add(new TreeSet<>());
        }
        for (int u = 0; u < n; u++) {
            for (int v : graph.get(u)) {
                int a = componentOf[u];
                int b = componentOf[v];
                if (a != b) {
                    nextSets.get(a).add(b);
                }
            }
        }

        List<List<Integer>> condensation = new ArrayList<>();
        for (TreeSet<Integer> outgoing : nextSets) {
            condensation.add(List.copyOf(outgoing));
        }

        // B5. Topo cua cac SCC. Condensation luon la DAG.
        List<Integer> topo = topoOfDag(condensation);
        if (topo.size() != k) {
            throw new IllegalStateException(
                    "condensation must be a DAG");
        }

        return new SccResult(
                List.copyOf(components),
                componentOf,
                List.copyOf(condensation),
                topo);
    }

    public static void main(String[] args) {
        List<List<Integer>> graph = directedGraph(9,
                new int[][]{
                        {0,1}, {1,2}, {2,0},
                        {2,3}, {0,3},
                        {3,4}, {4,3},
                        {4,5}, {3,5},
                        {2,6}, {6,7}, {7,6},
                        {7,5}, {5,8}
                });
        SccResult result = analyze(graph);

        System.out.println("SCCs = " + result.components());
        System.out.println("componentOf = " +
                Arrays.toString(result.componentOf()));
        System.out.println("condensation = " +
                result.condensation());
        System.out.println("component topo = " +
                result.topoOrder());

        System.out.println("same SCC 0,2 = " +
                (result.componentOf()[0] == result.componentOf()[2]));
        System.out.println("same SCC 2,5 = " +
                (result.componentOf()[2] == result.componentOf()[5]));

        SccResult isolated = analyze(
                directedGraph(4, new int[0][2]));
        System.out.println("isolated SCCs = " +
                isolated.components());

        SccResult parallel = analyze(
                directedGraph(3,
                        new int[][]{{0,1}, {0,1}, {1,2}}));
        System.out.println("parallel condensed = " +
                parallel.condensation());

        SccResult selfLoop = analyze(
                directedGraph(3,
                        new int[][]{{0,0}, {1,1}}));
        System.out.println("self-loop SCCs = " +
                selfLoop.components());

        SccResult empty = analyze(
                directedGraph(0, new int[0][2]));
        System.out.println("empty SCCs = " + empty.components());

        try {
            directedGraph(2, new int[][]{{0,2}});
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid edge: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac SccCondensationDemo.java
java SccCondensationDemo
~~~

**Stdout chính xác** với thứ tự cạnh trong mã và quy tắc chuẩn hóa:

~~~text
SCCs = [[0, 1, 2], [3, 4], [5], [6, 7], [8]]
componentOf = [0, 0, 0, 1, 1, 2, 3, 3, 4]
condensation = [[1, 3], [2], [4], [2], []]
component topo = [0, 1, 3, 2, 4]
same SCC 0,2 = true
same SCC 2,5 = false
isolated SCCs = [[0], [1], [2], [3]]
parallel condensed = [[1], [2], []]
self-loop SCCs = [[0], [1], [2]]
empty SCCs = []
invalid edge: vertex out of range
~~~

### Đọc từng phần kết quả

- **SCCs:** có 5 nhóm chính, đúng với A={0,1,2}, B={3,4}, C={5}, D={6,7}, E={8}.
- **componentOf:** mỗi đỉnh gốc được ánh xạ vào đúng một id SCC; đặc biệt 0 và 2 cùng id 0, 2 và 5 khác id.
- **condensation:** chỉ còn 5 siêu đỉnh, các cạnh giữa SCC được nén; hai cạnh A→B trong dữ liệu gốc chỉ tạo **một cung 0→1**, tương tự hai cạnh B→C chỉ tạo một cung 1→2.
- **component topo:** [0,1,3,2,4] thỏa các cạnh trong condensation.
- **isolated SCCs:** khi không có cạnh nào, mỗi đỉnh đứng riêng thành một SCC.
- **parallel condensed:** hai cạnh 0→1 song song được TreeSet gộp thành một cung.
- **self-loop SCCs:** self-loop không bắt buộc ghép đỉnh với đỉnh khác.
- **empty SCCs:** đồ thị không đỉnh có 0 SCC và 0 siêu đỉnh; không có lỗi.
- **invalid edge:** builder từ chối đầu mút 2 khi đồ thị có n=2 (id hợp lệ chỉ là 0,1).

### Một số giới hạn của API ví dụ

**Đồ thị phải có hướng.** Hàm directedGraph không tự thêm cạnh ngược; khi bài có tên đỉnh là chuỗi ký tự, cần ánh xạ mỗi tên thành id và giữ map ngược để in.

**Đầu vào phải nhất quán.** analyze nhận một danh sách kề do người gọi truyền; demo tạo qua directedGraph có kiểm tra đầu mút. Nếu nhận adjacency list từ bên ngoài, hãy xác thực từng chỉ số v thuộc [0,n), danh sách kề không null và dữ liệu không bị sửa đồng thời.

**Sắp xếp chỉ là để in ổn định.** Danh sách SCC có thể trả theo thứ tự khác nếu bỏ bước chuẩn hóa; đừng giả định component id là một thứ tự topo. Trong ví dụ, id SCC 2 cần đến sau id 3 trong topo, dù 2 nhỏ hơn 3.

**Kết quả có mảng int[]:** record SccResult chứa mảng componentOf; mảng Java vẫn mutable dù record là kiểu đóng gói. Ví dụ chỉ đọc mảng. Muốn API bất biến sâu, sao chép mảng khi lưu/trả hoặc chuyển sang một cấu trúc chỉ đọc phù hợp.

**DFS đệ quy sâu:** Kosaraju demo dễ đọc nhưng khi đồ thị có đường đi rất dài, Java có thể ném StackOverflowError. Có thể thay hai DFS bằng **stack frame tường minh**; việc thay thế phải giữ thứ tự hoàn tất thực sự (postorder) ở lượt 1, chứ không chỉ đảo một thứ tự thăm thông thường.

## 15. Phân tích độ phức tạp chuẩn và biến thể chuẩn hóa

Đặt V là số đỉnh, E là số cạnh có hướng của G, K là số SCC và A là số cạnh phân biệt giữa SCC sau khi nén. Ta có 0≤K≤V và 0≤A≤E.

**Kosaraju cơ bản:**

- DFS lượt 1: O(V+E).
- Dựng transpose: O(V+E) thời gian và O(V+E) bộ nhớ.
- DFS lượt 2: O(V+E).
- Gán id thành phần: O(V).
- Nếu không chuẩn hóa thứ tự và dùng tập hash để khử cạnh trùng, dựng condensation có thể đạt **O(V+E) kỳ vọng**.

Vì thế **chi phí tìm SCC bằng Kosaraju là O(V+E)** thời gian và O(V+E) bộ nhớ phụ nếu tính cả transpose; DFS đệ quy có stack sâu tối đa O(V).

**Java demo có thêm hai công việc để output ổn định:**

1. Sắp các đỉnh bên trong từng SCC và sắp nhóm theo đỉnh nhỏ nhất: tổng cận trên O(V log V).
2. TreeSet để vừa khử cạnh trùng vừa sắp id đích: tối đa E lần chèn với chi phí O(log(K+1)) mỗi lần, nên O(E log(K+1)) cận trên.

Kahn trên condensation tốn O(K+A). Vì vậy độ phức tạp toàn bộ demo có thể viết:

~~~text
Time:
    O(V + E + V log(V+1) + E log(K+1) + K + A)

Space:
    O(V+E+K+A) including transpose and condensation,
    plus recursion stack O(V).
~~~

Có thể rút gọn thành O(V log(V+1)+E log(K+1)) trong nhiều trường hợp có cạnh, nhưng cách viết tách hạng tử giúp thấy rõ **phần tuyến tính của SCC và overhead chuẩn hóa**.

**Tarjan cơ bản:** O(V+E) thời gian, O(V) trạng thái stack/mảng phụ ngoài danh sách kề. Không cần transpose nên thường tiết kiệm bộ nhớ cho một số triển khai.

### Trường hợp nhiều query

Nếu có hàng nghìn truy vấn hỏi hai đỉnh có cùng SCC không, ta chỉ cần tính SCC **một lần**, rồi so sánh componentOf[u]==componentOf[v] trong O(1) mỗi truy vấn. Nếu hỏi reachability giữa **hai SCC khác nhau**, phải có thêm tìm đường hoặc tiền xử lý reachability trên DAG; việc chỉ có componentOf chưa đủ.

Nếu đồ thị thay đổi cạnh liên tục, SCC/condensation có thể thay đổi rất lớn sau một cạnh mới. Ví dụ chỉ cần thêm một cạnh đi từ SCC đích trở về SCC nguồn có thể gộp nhiều SCC dọc đường thành một. Không được dùng mảng componentOf cũ sau khi sửa đồ thị mà chưa có cơ chế cập nhật hợp lệ.

## 16. Các lỗi thường gặp khi tìm SCC và xây DAG

| Lỗi | Hệ quả | Cách tránh |
| --- | --- | --- |
| Dùng một BFS từ nguồn để gọi tập reachable là SCC | Gộp đỉnh chỉ có đường một chiều | Đòi reachability hai chiều hoặc dùng SCC algorithm |
| Lấy weak connected component thay SCC | Bỏ mất thông tin hướng | Chỉ bỏ hướng khi đề hỏi liên thông yếu |
| Quên duyệt mọi đỉnh ở cả hai lượt Kosaraju | Thiếu SCC ở thành phần khác | Có vòng ngoài trên mọi đỉnh chưa thăm |
| Dùng DFS preorder ở lượt 1 | Thứ tự lượt 2 sai | Ghi finishOrder lúc thoát DFS |
| Duyệt finishOrder từ đầu tới cuối | Có thể gộp sai các SCC | Duyệt giảm thời điểm hoàn tất |
| Không reset visited giữa hai lượt | Lượt 2 không thu được nhóm | Reset visited sau lượt 1 |
| Dùng G ở lượt 2 thay vì Gᵀ | Có thể trộn các SCC | Xây transpose và duyệt trên nó |
| Chỉ đảo danh sách láng giềng | Không phải transpose | Đổi mỗi u→v thành v→u |
| Tarjan dùng low[v] cho mọi đỉnh visited | Gộp SCC đã hoàn tất | Chỉ dùng index[v] nếu v còn onStack |
| Không pop hết tới gốc SCC | Tách nhóm sai | Khi low[u]==index[u], pop đến u |
| Thêm cạnh nội bộ a→a vào condensation | Condensation xuất hiện self-loop giả | Bỏ khi componentOf[u]==componentOf[v] |
| Cộng nhiều cạnh trùng mà không nhất quán | Kahn indegree sai hoặc DAG dư cung | Gộp hoặc giữ nhất quán khi tính indegree |
| Tưởng id SCC luôn là topo order | Xử lý DP sai thứ tự | Chạy topo thật trên condensation |
| Tưởng mọi SCC có ít nhất hai đỉnh | Thiếu singleton/isolated | Mỗi đỉnh thuộc đúng một SCC |
| Tưởng singleton có self-loop sẽ nhập SCC khác | Gộp sai | Kiểm tra đường hai chiều tới đỉnh khác |
| Tưởng condensation giữ khoảng cách đường ngắn nhất | Sai chi phí/path | Chỉ dùng bảo toàn reachability |
| So chuỗi output nhóm thay vì tập đỉnh | Test báo sai giả | Chuẩn hóa hoặc so phân hoạch |
| Dùng đệ quy trên chuỗi cực dài | StackOverflowError | DFS lặp hoặc giải pháp thay thế |
| Quên invalidate SCC sau khi sửa cạnh | Cache thành phần stale | Tính lại hoặc dùng cập nhật SCC động |
| Coi SCC là một thứ tự thực thi nội bộ | Không giải được vòng dependency bên trong | SCC để chẩn đoán nhóm, không thay lịch nội bộ |

**Một phép kiểm rất mạnh:** sau khi nén, chạy Kahn trên condensation. Nếu không lấy được đủ K siêu đỉnh, gần như chắc chắn có bug trong kết quả componentOf hoặc bước xây cạnh condensation (nếu input là đồ thị có hướng hợp lệ). Theo định lý, condensation đúng **phải luôn là DAG**.

## 17. Kiểm thử tính đúng bằng tính chất và đối chứng

### Những bất biến của kết quả SCC

- Mỗi đỉnh gốc xuất hiện trong **đúng một** danh sách thành phần.
- Tổng kích thước mọi danh sách SCC đúng bằng V.
- Không có SCC rỗng.
- componentOf[v] thuộc [0,K) với mọi v khi V>0.
- Với mọi cặp u,v có cùng component id, u⇝v và v⇝u trong graph.
- Với mọi cặp u,v có component id khác nhau, **không đồng thời** có đường đi cả hai chiều.
- Nếu có cạnh u→v giữa hai SCC khác nhau, condensation phải có cạnh componentOf[u]→componentOf[v].
- Nếu condensation có cạnh a→b, phải có ít nhất một cạnh gốc nối đỉnh thuộc SCC a tới SCC b.
- Condensation **không có self-loop**, không có cạnh trùng nếu đặc tả dùng một cạnh cho mỗi cặp thành phần.
- Kahn trên condensation phải xử lý được **đủ K** siêu đỉnh.

### Đối chứng độc lập khi V nhỏ

Đối với V≤8, có thể chạy BFS/DFS từ **mỗi đỉnh** để dựng ma trận reachability. Gom u và v vào cùng nhóm khi reachable[u][v] và reachable[v][u] đều true, rồi so với SCC của Kosaraju/Tarjan.

Đây là oracle độc lập với thứ tự DFS của Kosaraju, đủ mạnh để phát hiện các lỗi thường gặp như duyệt sai Gᵀ hoặc quên đảo finishOrder.

Kiểm tiếp reachability condensation:

~~~text
for every u, v:
    G has path u -> v
        iff H has path componentOf[u] -> componentOf[v]
~~~

Đối chiếu bằng BFS trên graph gốc và trên H, tính cả trường hợp u,v ở cùng SCC (đường độ dài 0 ở H). **Không so khoảng cách nhỏ nhất**, vì nén SCC không bảo toàn chiều dài đường đi giữa các đỉnh.

### Các trường hợp biên

| Input | SCC mong đợi |
| --- | --- |
| V=0, E=0 | [] |
| V=1, E=0 | [[0]] |
| V=1, self-loop 0→0 | [[0]] |
| V=4, không cạnh | [[0],[1],[2],[3]] |
| 0→1→2 nhưng không có cạnh ngược | [[0],[1],[2]] |
| 0→1→2→0 | [[0,1,2]] |
| Hai cạnh song song 0→1, có 1→2 | [[0],[1],[2]]; condensation chỉ một 0→1 |
| 0↔1 và 2↔3, 4 đứng riêng | [[0,1],[2,3],[4]] |
| Graph chính 9 đỉnh | [[0,1,2],[3,4],[5],[6,7],[8]] |
| Graph có chu trình trong một thành phần tách biệt | SCC vòng phải được phát hiện |
| Input chứa cạnh ngoài miền | Từ chối trước khi chạy SCC |

### Kiểm thử ngẫu nhiên và metamorphic

1. **Hoán đổi thứ tự cạnh:** sắp lại danh sách kề; phân hoạch SCC vẫn giống nhau dù thứ tự nội bộ DFS khác.
2. **Thêm cạnh song song u→v:** không thay đổi SCC và condensation nếu đã khử trùng cung liên nhóm.
3. **Đảo mọi cạnh:** SCC của G và Gᵀ phải **giống phân hoạch**, còn condensation đảo chiều các cung liên nhóm.
4. **Đổi tên đỉnh bằng một hoán vị:** SCC thay id nhưng cấu trúc nhóm tương đương sau khi map ngược tên.
5. **Thêm một đỉnh cô lập:** tăng đúng một SCC singleton và một siêu đỉnh không cạnh.
6. **Thêm self-loop vào một đỉnh:** không đổi phân hoạch SCC vì không tạo khả năng đi tới một đỉnh khác.
7. **Thêm cạnh nối hai SCC:** có thể giữ nguyên hoặc gộp SCC nếu cạnh mới tạo vòng; không được giả định luôn giữ nguyên.
8. **Chạy cả Kosaraju và Tarjan:** kết quả phân hoạch phải tương đương trên cùng một graph.
9. **Kiểm topo condensation:** với mọi cung a→b, vị trí a trong topo nhỏ hơn vị trí b.
10. **Kiểm phiên bản dữ liệu:** thay đổi input thì kết quả cũ phải được cập nhật hoặc tính lại, không tái sử dụng cache cũ.

## 18. Bài tập tự luyện

1. Với G có cạnh 0→1,1→2,2→0,2→3, xác định mọi SCC. Vì sao 3 không thuộc SCC {0,1,2} dù 2 đi tới 3?
2. Với graph 9 đỉnh của bài, giải thích vì sao A={0,1,2}, B={3,4}, C={5}, D={6,7}, E={8} là các SCC **tối đại**, không chỉ là các tập con liên thông mạnh.
3. Tự dựng Gᵀ cho graph 9 đỉnh. Chạy DFS lượt 1 trên G, ghi finishOrder khi **thoát** lời gọi, rồi chạy lượt 2 trên Gᵀ theo chiều đảo finishOrder.
4. Dùng graph 0→1 và không có 1→0 để chỉ ra hậu quả nếu Kosaraju xét finishOrder **từ đầu về cuối** trong lượt 2.
5. Viết code Tarjan với index,low,onStack. Với chu trình 0→1→2→0, theo dõi low qua từng lần quay về DFS và mô tả thời điểm pop SCC.
6. Với một DAG có các cạnh 0→1,0→2,1→3,2→3, xác định SCC. Vì sao mỗi đỉnh là một singleton dù toàn đồ thị có các đường đi giữa nhiều cặp?
7. Bổ sung một cạnh 8→0 vào graph chính. Dự đoán những SCC nào có thể nhập lại, sau đó chạy Kosaraju và giải thích bằng các đường đi hai chiều.
8. Thêm hai cạnh song song từ SCC A sang B. Viết bước nén đúng để condensation chỉ có **một** cung A→B, nhưng vẫn bảo toàn reachability.
9. Với condensation 0→1,0→3,1→2,3→2,2→4, hãy chạy Kahn và ghi một thứ tự topo. Có thể đặt 2 trước 3 không? Vì sao?
10. Viết hàm sameComponent(u,v) dùng componentOf để trả O(1) mỗi truy vấn sau tiền xử lý. Phân tích tổng thời gian cho Q truy vấn trên graph không đổi.
11. Viết chương trình đối chứng: trên mọi đồ thị có hướng nhỏ V≤6, so sánh Kosaraju với phân nhóm bằng ma trận reachable từ BFS từng nguồn.
12. Kiểm chứng rằng SCC của graph gốc và transpose giống nhau, còn **cạnh giữa SCC** đổi hướng. Thử trên graph không đối xứng có nhiều SCC.
13. Với hai đỉnh thuộc SCC khác nhau, thiết kế hàm reachableComponents(a,b) chạy BFS trên condensation. Tại sao chỉ so componentOf không giải được câu hỏi reachability này?
14. Chứng minh condensation không thể có chu trình bằng giả định có một vòng giữa các siêu đỉnh rồi ghép đường đi nội bộ của từng SCC.
15. Với bài toán “đi được nhiều SCC nhất từ một nguồn”, xây DP trên DAG theo topo. Phân biệt việc đếm **số SCC** và đếm **số đỉnh riêng biệt của đường đi đơn**.
16. Tìm một bài toán dùng SCC để phát hiện nhóm phụ thuộc vòng trong build system. Nêu cách hiển thị nhóm lỗi, cách xác định những module nằm **sau** nhóm lỗi nhưng không thuộc chính chu trình.
17. Viết phiên bản Kosaraju **không đệ quy** bằng stack frame với chỉ số cạnh đang xét. Chỉ ghi finishOrder lúc frame đã duyệt hết cạnh.
18. Ước lượng chi phí sắp SCC và khử trùng cạnh TreeSet trong Java demo. Nếu ưu tiên tốc độ O(V+E), bạn sẽ bỏ chuẩn hóa hoặc đổi cấu trúc dữ liệu như thế nào?

## 19. Tổng kết và checklist thiết kế

Khi gặp một bài toán đồ thị có hướng với nhiều vòng liên thông, hãy tự hỏi:

- Đề hỏi **đi tới được một chiều**, **liên thông mạnh hai chiều**, hay **liên thông yếu** sau khi bỏ hướng?
- Có cần **từng SCC**, hay chỉ biết số lượng SCC, hay biết hai đỉnh có cùng SCC không?
- Đã bao phủ **mọi đỉnh**, bao gồm đỉnh cô lập và các thành phần tách biệt, hay mới chỉ chạy từ một nguồn?
- Chọn **Kosaraju** (hai DFS, transpose, finishOrder) hay **Tarjan** (một DFS, index/low/onStack)?
- Khi nén SCC, đã **bỏ cạnh nội bộ a→a** và xử lý cạnh trùng giữa các nhóm theo đúng yêu cầu chưa?
- Mảng componentOf có gán **đúng một id** cho mọi đỉnh và ổn định nếu bài cần output tất định không?
- Đã kiểm condensation bằng topo để chắc chắn là **DAG** chưa?
- Nếu dùng DP trên condensation, đại lượng DP thực sự là gì? Có đang nhầm đếm SCC với độ dài/chi phí path trên đồ thị gốc không?
- Có cần tính lại SCC khi input thêm/bớt cạnh hay không?
- Đã kiểm các ca self-loop, không cạnh, cạnh song song, graph rỗng và DFS sâu?

**Kết luận:** SCC là **những nhóm đỉnh tối đại có đường đi hai chiều giữa mọi cặp**, tạo thành một phân hoạch duy nhất của tập đỉnh. Kosaraju tìm SCC bằng hai lượt DFS theo thứ tự hoàn tất và transpose; Tarjan dùng discovery time/low-link và stack trong một lượt DFS. Khi **thu gọn mỗi SCC thành một siêu đỉnh**, bỏ các cạnh nội bộ và giữ các cung liên nhóm, ta luôn thu được một **DAG**, phù hợp để sắp topo, phân tích nguồn–đích và làm DP trên cấu trúc phụ thuộc giữa nhóm. Phép nén bảo toàn **reachability ở cấp SCC**, nhưng không tự bảo toàn chi phí hay đường ngắn nhất giữa từng đỉnh gốc.
