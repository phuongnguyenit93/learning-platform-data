# Thuật toán Kosaraju

**Thuật toán Kosaraju (Kosaraju–Sharir)** tìm **các thành phần liên thông mạnh** (*strongly connected components*, viết tắt **SCC**) của một **đồ thị có hướng**. Hai đỉnh thuộc cùng SCC khi mỗi đỉnh đều có một đường đi có hướng tới đỉnh kia. Kosaraju thực hiện **hai lượt duyệt DFS**: lượt đầu thu thứ tự **kết thúc** của đỉnh, lượt sau duyệt trên **đồ thị chuyển vị** (đảo chiều mọi cạnh) theo thứ tự kết thúc giảm dần. Mỗi lần bắt đầu một DFS mới trong lượt hai sẽ thu được **đúng một SCC**.

Đây là thuật toán tuyến tính theo quy mô đồ thị: **O(V+E)** thời gian với danh sách kề, gồm V đỉnh và E cạnh. Nó khác việc tìm thành phần liên thông trong đồ thị vô hướng: quan hệ đi tới trong đồ thị có hướng không đối xứng. Cũng không nên lẫn SCC với những đỉnh chỉ **cùng được truy cập từ một đỉnh gốc**.

Bài thuộc chủ đề **Cấu trúc đồ thị**. Ta sẽ giải thích định nghĩa SCC, đồ thị chuyển vị, lý do phải ghi đỉnh lúc DFS **kết thúc**, ví dụ hai lượt duyệt, chứng minh bằng **đồ thị co SCC** (condensation DAG), cài đặt Java 17+ **không dùng DFS đệ quy** để giảm rủi ro tràn ngăn xếp, cách dựng DAG các thành phần, độ phức tạp, ca biên, ứng dụng và kiểm thử độc lập.

**Mục tiêu:** tự phân nhóm SCC, hiểu thứ tự finishing time và transpose; chứng minh từng lượt DFS thứ hai không lọt sang SCC khác; cài đúng cả đỉnh chưa có cạnh, khuyên dùng adjacency list và visited riêng cho mỗi lượt; kiểm tra output bằng tính khả đạt hai chiều trên đồ thị nhỏ.

## 1. Liên thông mạnh nghĩa là gì?

Với đồ thị có hướng `G=(V,E)`, ta viết `u ⇝ v` khi tồn tại đường đi **theo chiều mũi tên** từ u tới v. Hai đỉnh u,v **liên thông mạnh** nếu:

**`u ⇝ v` và `v ⇝ u`.**

Một **thành phần liên thông mạnh** là một tập đỉnh lớn nhất theo quan hệ này: mọi cặp đỉnh trong tập đi tới nhau theo cả hai chiều, và không thể thêm đỉnh nào từ bên ngoài mà vẫn giữ tính chất đó.

Quan hệ “liên thông mạnh” là quan hệ tương đương:

- **Phản xạ:** mỗi đỉnh đạt tới chính nó bằng đường đi độ dài 0.
- **Đối xứng:** định nghĩa đòi hai chiều.
- **Bắc cầu:** nếu u đi tới v và ngược lại, v đi tới w và ngược lại, ghép đường đi cho u tới w và w tới u.

Vì vậy các SCC **phân hoạch** V: mỗi đỉnh thuộc **đúng một** SCC, các SCC không giao nhau, và hợp của chúng bằng toàn bộ V.

### Ví dụ cơ bản

Xét cạnh có hướng:

~~~text
0 -> 1 -> 2
^         |
|_________|

2 -> 3 -> 4 -> 5
     ^         |
     |_________|

5 -> 6 <-> 7
~~~

Hiểu các chu trình theo danh sách cạnh đầy đủ:

- `0→1, 1→2, 2→0` tạo SCC **{0,1,2}**.
- `3→4, 4→5, 5→3` tạo SCC **{3,4,5}**.
- `6→7, 7→6` tạo SCC **{6,7}**.
- Cạnh `2→3` và `5→6` đi **giữa** các SCC, không có cạnh/đường đi ngược hoàn chỉnh đưa các SCC này hợp lại.

Kết quả: **[[0,1,2],[3,4,5],[6,7]]** (được sắp theo tên đỉnh để dễ đọc). Một đỉnh có self-loop vẫn có thể là SCC một đỉnh; một đỉnh cô lập cũng là SCC một đỉnh theo đường đi độ dài 0.

### Trường hợp không được nhầm

Nếu chỉ có cạnh `0→1`:

- 0 tới được 1, nhưng 1 không tới được 0.
- Kết quả phải là hai SCC **{0}** và **{1}**, **không phải {0,1}**.
- Độ liên thông yếu (*weak connectivity*) bỏ qua hướng cạnh nên có thể xem hai đỉnh cùng một thành phần yếu; đó là định nghĩa khác.

Trong đồ thị vô hướng, mỗi cạnh có thể đi hai chiều, nên thành phần liên thông vô hướng tương ứng SCC nếu biểu diễn mỗi cạnh bằng hai cung ngược nhau; nhưng Kosaraju chủ yếu được thiết kế để giải bài toán đồ thị **có hướng**.

## 2. Tại sao không dùng một lần DFS rồi gom mọi đỉnh đã thăm?

Một DFS từ u tìm **tập các đỉnh u có thể đi tới**, không bảo đảm mỗi đỉnh trong tập quay trở lại u. Trong ví dụ `0→1`, DFS từ 0 thăm cả 0 và 1, nhưng chúng không cùng SCC.

Một cách đúng nhưng tốn kém là, với từng đỉnh, tính tập đỉnh có thể đạt tới; sau đó u,v cùng SCC khi **cả u tới v lẫn v tới u**. Chạy DFS/BFS từ mọi đỉnh có thể mất **O(V(V+E))** trong cách thông thường.

Kosaraju tận dụng cấu trúc giữa các SCC để tránh lặp toàn bộ phép duyệt từ mọi đỉnh, chỉ cần **hai lượt DFS tổng thể**.

## 3. Đồ thị chuyển vị là gì?

**Đồ thị chuyển vị** `Gᵀ` có **cùng tập đỉnh** với G, nhưng mỗi cạnh `u→v` trong G được thay bằng cạnh **`v→u`** trong Gᵀ.

Ví dụ:

~~~text
G:                 G^T:
0 -> 1 -> 2        0 <- 1 <- 2
     |                  ^
     v                  |
     3                  3
~~~

Đảo cạnh không làm một SCC bị chia hay các SCC bị hợp:

**`u⇝v` trong G ⇔ `v⇝u` trong Gᵀ`**.

Do đó điều kiện khả đạt **hai chiều** giữa u,v được bảo toàn, nghĩa là **tập các SCC của G và Gᵀ giống nhau**. Điều thay đổi là **chiều các cạnh giữa SCC**.

### Xây transpose bằng danh sách kề

Nếu `graph[u]` chứa mọi v có cạnh u→v, thì:

~~~text
for every vertex u:
    for every v in graph[u]:
        transpose[v].add(u)
~~~

Với danh sách kề, cần **O(V+E)** thời gian và bộ nhớ để xây transpose. Các đỉnh không có cạnh vẫn phải xuất hiện trong cả graph và transpose; đừng chỉ tạo danh sách cho những đỉnh từng xuất hiện ở cạnh.

**Cẩn thận:** không được “đảo thứ tự các đỉnh trong danh sách kề” rồi xem đó là transpose. Phải **đảo chiều của từng cạnh**, tức thêm u vào danh sách của v, không đảo mảng `graph[u]`.

## 4. Đồ thị co SCC: nền tảng của chứng minh

Nếu co mỗi SCC thành một siêu đỉnh, và giữ cạnh `A→B` khi G có một cạnh từ một đỉnh của SCC A tới một đỉnh của SCC B (với A≠B), ta được **đồ thị co SCC (condensation graph)**.

Đồ thị co SCC **luôn là DAG** (*directed acyclic graph*, đồ thị có hướng không chu trình).

**Vì sao?** Nếu các SCC A,B,C,... tạo một chu trình có hướng A⇝B⇝...⇝A trong đồ thị co, mọi SCC trên chu trình có thể đi tới nhau theo cả hai chiều. Chúng phải là **cùng một SCC lớn**, trái giả thiết đã co thành những SCC khác nhau.

Với ví dụ ở mục 1, đồ thị co là:

~~~text
SCC 0: {0,1,2} -> SCC 1: {3,4,5} -> SCC 2: {6,7}
~~~

Trong DAG này, **SCC nguồn** (*source SCC*) là thành phần không có cạnh đi vào từ SCC khác. **SCC đích** (*sink SCC*) là thành phần không có cạnh đi ra SCC khác.

Kosaraju sử dụng **thứ tự kết thúc DFS** để chọn một SCC nguồn thích hợp của đồ thị gốc, rồi ở **đồ thị đảo cạnh** SCC đó không thể đi sang một SCC chưa xử lý khác. Vì vậy một lượt DFS trên transpose chỉ thu đúng một nhóm.

## 5. Lượt DFS đầu: ghi thứ tự kết thúc, không phải thứ tự phát hiện

Ta duyệt mọi đỉnh của **đồ thị gốc G**. Khi thăm v, DFS đi sâu theo các cạnh v→w tới những đỉnh chưa được thăm. Chỉ **sau khi đã xét hết các nhánh đi ra khỏi v**, ta mới đưa v vào danh sách `finishOrder`.

Điều này tạo **postorder DFS**:

~~~text
DFS1(v):
    mark v visited
    for each edge v -> u:
        if u not visited:
            DFS1(u)
    finishOrder.append(v)   // SAU khi xử lý các hàng xóm
~~~

Không được ghi v lúc vừa phát hiện: đó là **preorder**, không mang tính chất finishing time cần dùng cho Kosaraju.

### Vì sao phải bắt đầu DFS từ mọi đỉnh?

Đồ thị có thể không liên thông, hoặc có nhiều SCC mà không có đường đi từ một gốc cố định. Chạy một DFS từ 0 rồi dừng có thể bỏ cả những đỉnh không đạt được từ 0. Vì vậy:

~~~text
for v from 0 to V-1:
    if v not visited:
        DFS1(v)
~~~

Danh sách finishOrder phải có **đúng V đỉnh**, mỗi đỉnh xuất hiện một lần, kể cả đỉnh cô lập và đỉnh chỉ có cạnh đi vào.

### Ví dụ tính tay với sáu đỉnh

Xét `V={0,1,2,3,4,5}` và các cạnh đưa vào theo đúng thứ tự:

`0→1, 1→2, 2→0, 2→3, 3→4, 4→3`.

Đỉnh 5 cô lập.

Nếu duyệt đỉnh bắt đầu 0..5 và duyệt danh sách kề theo thứ tự trên:

- DFS từ 0 đi lần lượt `0→1→2→3→4`.
- Đỉnh 4 không có cạnh tới đỉnh chưa thăm ⇒ kết thúc 4.
- Quay về 3, rồi 2, rồi 1, rồi 0 ⇒ kết thúc lần lượt 3,2,1,0.
- Đỉnh 5 chưa được thăm ⇒ DFS riêng và kết thúc 5.

**`finishOrder=[4,3,2,1,0,5]`.**

Thứ tự dùng cho lượt hai là **đảo ngược**:

**`[5,0,1,2,3,4]`.**

Không cần tính số thời gian vào/ra tường minh; **danh sách append khi kết thúc** đã đủ. Nếu dùng stack, cũng có thể lần lượt pop theo thứ tự kết thúc giảm dần.

## 6. Lượt DFS thứ hai: transpose + thứ tự kết thúc giảm dần

Sau khi có finishOrder:

1. Tạo đồ thị chuyển vị **Gᵀ** (có thể tạo ngay lúc đọc cạnh).
2. Dùng một mảng visited **mới**, hoặc đặt lại tất cả cờ visited=false.
3. Duyệt các đỉnh trong **finishOrder từ cuối về đầu** (giá trị kết thúc lớn nhất trước).
4. Nếu đỉnh đang xét chưa được duyệt trong lượt hai, chạy DFS trên **Gᵀ** từ đỉnh ấy, gom mọi đỉnh tìm được thành **một SCC**.
5. Lặp cho tới hết danh sách.

Pseudocode:

~~~text
finishOrder = DFS_postorder_on_all_vertices(G)
GT = transpose(G)

clear visited
components = []

for index from finishOrder.size - 1 down to 0:
    start = finishOrder[index]
    if not visited[start]:
        group = DFS_collect_reachable(GT, start, visited)
        components.add(group)

return components
~~~

Điểm dễ nhầm là **đổi đúng một thứ nhưng không đổi thứ còn lại**:

- Lượt một: **G gốc**, ghi finishing order.
- Lượt hai: **Gᵀ**, duyệt **finishing order đảo ngược**.

Cũng tồn tại phương án tương đương: lượt một trên Gᵀ và lượt hai trên G, với thứ tự kết thúc tương ứng được tính từ Gᵀ. Nhưng **không được tự ý đảo đồ thị ở cả hai lượt** hoặc đổi orientation mà giữ nguyên một danh sách finishOrder không liên quan.

### Truy vết ví dụ sáu đỉnh

Với `finishOrder=[4,3,2,1,0,5]`, xét lần lượt `[5,0,1,2,3,4]` trên Gᵀ:

- **Bắt đầu 5:** không có cung nào, thu SCC **{5}**.
- **Bắt đầu 0:** ở Gᵀ có thể đi theo các cạnh đảo trong chu trình 0,1,2; thu SCC **{0,1,2}**. Không đi sang 3 hoặc 4 vì cạnh `2→3` ở G đã đảo thành `3→2` trong Gᵀ.
- **Bỏ qua 1,2** vì đã thuộc SCC vừa thu.
- **Bắt đầu 3:** duyệt qua 3 và 4 theo các cạnh đảo trong chu trình `3↔4`, thu SCC **{3,4}**.
- **Bỏ qua 4** vì đã xét.

Lượt hai phát hiện SCC theo thứ tự **{5}, {0,1,2}, {3,4}**. Nếu chỉ muốn hiển thị các nhóm theo **đỉnh nhỏ nhất**, có thể sắp lại thành:

**`[[0,1,2],[3,4],[5]]`.**

**Lưu ý:** thứ tự DFS tìm thấy SCC và thứ tự trình bày nhóm không bắt buộc giống nhau. Sắp theo đỉnh nhỏ nhất giúp output ổn định, nhưng **ID sau khi sắp không mặc nhiên là thứ tự tô-pô** của DAG các SCC.

## 7. Vì sao thứ tự kết thúc giúp cô lập một SCC?

Gọi `finish(C)` là **thời điểm kết thúc lớn nhất** trong những đỉnh của SCC C ở lượt DFS đầu trên G.

Nếu giữa hai SCC **khác nhau** có cạnh `C→D` trong đồ thị co, ta có tính chất:

**`finish(C)>finish(D)`.**

Trực giác:

- Nếu DFS lần đầu chạm **C trước D**, do các đỉnh trong C thông nhau và có cạnh tới D, DFS có thể đi từ C sang D; D sẽ kết thúc trước khi những đỉnh trong C kết thúc.
- Nếu DFS đã chạm **D trước C**, vì DAG co SCC **không có đường ngược từ D về C**, lượt DFS khởi đầu ở D không thể đi tới C. D kết thúc, rồi về sau một lượt DFS khác mới vào C và kết thúc muộn hơn.

Do đó một SCC có finishing time lớn nhất trong các SCC chưa xét sẽ là một **SCC nguồn của phần DAG co còn lại**: không SCC chưa xử lý nào có cạnh đi tới nó.

Khi chuyển sang **Gᵀ**, một SCC nguồn của G trở thành một SCC **không có cạnh đi ra** tới các SCC khác chưa xử lý. Bắt đầu DFS từ một đỉnh trong SCC ấy trên Gᵀ:

- Có thể tới **mọi đỉnh của chính SCC ấy**, vì đảo cạnh không làm mất liên thông mạnh.
- **Không thể lọt sang SCC chưa xử lý khác** qua một cạnh ra trong Gᵀ, vì đó sẽ tương ứng một cạnh đi vào SCC này trong G từ một SCC chưa xử lý.
- Có thể có cạnh trong Gᵀ tới SCC **đã được xử lý trước đó**, nhưng visited ngăn việc gom lại; những cạnh ấy không làm lẫn nhóm.

Vậy một DFS mới trên Gᵀ gom **đúng một SCC**. Loại SCC ấy và lặp lại lập luận theo thứ tự finish giảm dần để thu toàn bộ SCC.

Đây là khác biệt giữa Kosaraju và “duyệt được gì gom hết thành một nhóm”: **thứ tự đặc biệt bảo đảm DFS trên transpose không vượt biên SCC chưa xử lý**.

## 8. Chứng minh tính đúng một cách có hệ thống

**Mệnh đề 1: SCC không đổi khi đảo tất cả cạnh.** Hai đỉnh u,v ở cùng SCC của G khi và chỉ khi có cả đường u⇝v và v⇝u. Đảo toàn bộ cạnh đổi mỗi đường thành một đường theo chiều ngược, nên hai điều kiện vẫn cùng đúng ở Gᵀ.

**Mệnh đề 2: Đồ thị co SCC là DAG.** Nếu có chu trình qua các SCC khác nhau thì các thành phần trên chu trình đạt tới nhau theo hai chiều và phải gộp thành một SCC; mâu thuẫn.

**Mệnh đề 3: Với mỗi cạnh C→D giữa các SCC khác nhau, `finish(C)>finish(D)`.** Lập luận bằng thời điểm DFS đầu tiên khám phá C hoặc D, như mục 7, dựa vào việc không có đường từ D quay về C trong DAG co SCC.

**Bước quy nạp của lượt hai:** giả sử một số SCC đã được thu đúng. Chọn đỉnh chưa thăm có finishing time lớn nhất; gọi SCC của nó là C. Do mệnh đề 3, C không có cạnh đi vào từ bất kỳ SCC **chưa xử lý** nào của G. Vì thế trong Gᵀ, C không có cạnh đi ra tới SCC chưa xử lý. DFS trên Gᵀ bắt đầu ở C không thể chạm một SCC mới khác C, còn tính liên thông mạnh bảo đảm nó đi qua hết C. Nó chỉ thu đúng C.

**Kết thúc:** mỗi lượt gom làm giảm số đỉnh chưa xét ít nhất một, và mỗi đỉnh được thăm đúng một lần trong lượt hai. Tất cả đỉnh thuộc một và chỉ một SCC. Quy nạp bảo đảm kết quả là phân hoạch SCC thật sự của G.

**Điều kiện thuật toán:** đồ thị được biểu diễn đúng hướng cạnh; cả hai lượt duyệt phải bao phủ toàn bộ đỉnh; finishing order phải ghi **sau khi rời đỉnh**; phải đảo hướng cạnh giữa hai lượt.

## 9. Độ phức tạp thời gian và bộ nhớ

Với biểu diễn danh sách kề và V đỉnh, E cạnh:

| Pha | Thời gian | Bộ nhớ phụ chính |
|---|---|---|
| Đọc cạnh và dựng G | O(V+E) | O(V+E) |
| Dựng transpose Gᵀ | O(V+E) | O(V+E) |
| DFS lượt một, ghi finish | O(V+E) | O(V) visited, thứ tự, stack |
| DFS lượt hai trên Gᵀ | O(V+E) | O(V) visited/stack/ID |
| Gộp các SCC và mã hóa ID | O(V) | O(V) |
| Dựng cạnh DAG SCC | O(E) kỳ vọng nếu khử trùng bằng hash set | O(E) cạnh DAG phân biệt |

Tổng cho **thuật toán Kosaraju cốt lõi**:

**Thời gian `O(V+E)`; bộ nhớ `O(V+E)`** nếu tính cả hai danh sách kề.

Mỗi đỉnh được phát hiện một lần trong mỗi lượt; mỗi cạnh được xem số lần hằng định. Khi dùng DFS đệ quy, ngăn xếp hàm có thể sâu tới O(V). Mã Java ở phần 12 dùng **stack tường minh** và con trỏ cạnh để ghi postorder, tránh `StackOverflowError` do độ sâu DFS trên đồ thị dài; nhưng vẫn dùng bộ nhớ O(V) cho stack dữ liệu.

**Về cận của chương trình trình bày:** mã còn gán ID để mỗi SCC được hiển thị theo **đỉnh nhỏ nhất** bằng hai lượt quét tuyến tính, không gọi sort. Nó dùng `LinkedHashSet` để khử cạnh trùng giữa các SCC; thao tác hash có chi phí **O(1) kỳ vọng**, do đó tổng thời gian vẫn **O(V+E) kỳ vọng** cho cả phần hiển thị DAG (không khẳng định cận trường hợp xấu O(1) cho mọi hash set).

Nếu thay bằng `Collections.sort` trong từng nhóm hoặc `TreeSet` cho cạnh DAG, thời gian sẽ có thêm chi phí sắp xếp. Đó là chi phí phụ để trình bày/khử trùng, không phải bản chất của Kosaraju.

### Không nhầm số SCC với số đỉnh

Số SCC K thỏa `0≤K≤V`. Một DAG có V đỉnh và không có chu trình (không tính self-loop) có **V SCC đơn**; một đồ thị có hướng liên thông mạnh có thể chỉ có **1 SCC**, dù nhiều đỉnh/cạnh. Tất cả đỉnh cô lập tạo thành **V SCC đơn**, không phải một SCC chung.

## 10. Tại sao DFS iterative cần “đang duyệt cạnh nào”?

Một cách dùng stack dễ mắc lỗi là: khi pop một đỉnh từ stack, lập tức đưa nó vào `finishOrder`. Đó có thể chỉ là **thứ tự pop của một stack mô phỏng BFS/DFS**, không nhất thiết là **thời điểm DFS đệ quy thật sự hoàn thành tất cả nhánh con**.

Muốn mô phỏng chính xác postorder, mỗi khung stack cần biết:

- Đỉnh v đang xử lý.
- Vị trí **cạnh kế tiếp chưa xem** trong `graph[v]`.
- Chỉ pop và ghi finish(v) khi đã xử lý **tất cả các cạnh đi ra**.

Có thể dùng một class Frame(v,nextIndex), hoặc dùng:

- `ArrayDeque<Integer> stack` chứa các đỉnh của đường DFS hiện tại.
- `int[] nextEdge` chứa vị trí cạnh kế tiếp cần duyệt cho mỗi đỉnh.

Trong vòng while, nhìn đỉnh ở đầu stack:

1. Nếu còn cạnh chưa duyệt, lấy cạnh tiếp theo, tăng nextEdge[v], và push đỉnh mới nếu chưa visited.
2. Nếu đã hết cạnh, pop v rồi append v vào finishOrder.

Do vậy finishOrder đúng là postorder DFS với độ phức tạp O(V+E), không phải một heuristic đảo ngược thứ tự phát hiện.

### Duyệt DFS lượt hai đơn giản hơn

Lượt hai chỉ cần **gom các đỉnh đạt tới** trong transpose; không cần thời điểm kết thúc. Có thể dùng stack đơn giản, mỗi lần pop thì thêm đỉnh vào nhóm; đánh dấu visited **khi push** để mỗi đỉnh không bị push lặp lại.

Mọi đỉnh được duyệt tối đa một lần trong mỗi lượt; đa cạnh chỉ làm thêm vòng lặp xét cạnh, không tạo trùng đỉnh trong SCC vì visited đã bảo vệ.

## 11. Biểu diễn output và dựng DAG của các SCC

Các SCC vốn là **tập đỉnh**, không có thứ tự tự nhiên. Kết quả có thể biểu diễn dưới hai dạng:

1. **Danh sách nhóm:** `[[0,1,2],[3,4,5],[6,7]]`.
2. **Mảng ID theo đỉnh:** `componentOf[v]`, ví dụ `[0,0,0,1,1,1,2,2]`.

Mảng ID rất hữu ích để tạo đồ thị co SCC: với mỗi cạnh `u→v` của G:

- Nếu `componentOf[u]==componentOf[v]`, đây là cạnh **bên trong SCC**; không tạo cạnh DAG.
- Nếu khác, thêm cạnh `componentOf[u]→componentOf[v]` vào đồ thị co.
- Nếu đồ thị gốc có nhiều cạnh giữa cùng hai SCC, có thể loại trùng khi DAG yêu cầu **một cạnh đại diện**.

Cây DFS đầu không tự tạo DAG; DAG được suy ra từ mảng ánh xạ SCC.

### Về đánh số SCC trong mã mẫu

Các SCC được **đổi ID theo thứ tự đỉnh nhỏ nhất**. Ta làm vậy trong O(V): quét v từ 0 tới V−1 và đặt ID mới cho SCC của v lần đầu gặp; quét lại các đỉnh v tăng dần để đưa chúng vào nhóm mới. Kết quả có:

- Đỉnh trong từng nhóm **tăng dần**.
- Các nhóm hiển thị theo **đỉnh nhỏ nhất tăng dần**.
- ID nhất quán trong tất cả cạnh DAG.

**Nhưng ID này không phải topological order.** Nếu cần xử lý DP trên DAG các SCC, hãy chạy một thuật toán sắp xếp tô-pô như **Kahn** trên DAG sau khi co. Không dùng quy tắc “ID nhỏ hơn ⇒ đến trước” khi ID chỉ được chuẩn hóa để in đẹp.

### Ứng dụng của condensation DAG

Sau khi co SCC, các chu trình nội bộ biến thành một siêu đỉnh, và các cung giữa siêu đỉnh tạo DAG. Nhiều bài toán trên đồ thị có hướng trở nên dễ hơn:

- Đếm hoặc tìm **SCC nguồn/SCC đích** qua bậc vào/ra của DAG.
- Tính đường đi hoặc tối ưu trọng số thành phần bằng DP trên DAG.
- Nghiên cứu khả đạt giữa các thành phần mà không phải xử lý chu trình nội bộ.
- Phân rã hệ phụ thuộc thành các khối có quan hệ vòng.
- Giải hệ logic **2-SAT** qua đồ thị kéo theo với điều kiện một biến và phủ định của nó **không thuộc cùng SCC**.

## 12. Java 17+ hoàn chỉnh: hai lượt DFS không đệ quy

Mã dưới đây:

- Nhận số đỉnh `n≥0`, đánh số **0..n−1**, và mảng cạnh `int[][] edges`. Mỗi cạnh là cặp `{from,to}` theo hướng `from→to`.
- Kiểm tra `n`, `edges`, từng cạnh và endpoint. Không đọc ngoài phạm vi.
- Xây cả graph lẫn transpose ngay lúc đọc cạnh.
- Lượt một dùng **stack + nextEdge** để có finishing order thực sự.
- Lượt hai duyệt graph đảo chiều theo **finishing time giảm dần**, gán raw ID cho mỗi SCC.
- Chuẩn hóa ID theo đỉnh nhỏ nhất bằng các lượt quét O(V), không sắp xếp O(V log V).
- Tạo danh sách cạnh DAG không trùng qua `LinkedHashSet` theo thứ tự xuất hiện trong edges.
- Chấp nhận self-loop, cạnh song song, đỉnh cô lập và đồ thị rỗng.

Hợp đồng: nếu đầu vào không hợp lệ, ném `IllegalArgumentException`. Mã không sửa mảng cạnh của người gọi. Chương trình in danh sách nhóm và cạnh DAG dưới dạng `fromID->toID`. Các nhóm được đánh số phục vụ hiển thị, **không bảo đảm ID tô-pô**.

Lưu thành **`KosarajuDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public final class KosarajuDemo {
    private record Result(
            List<List<Integer>> components,
            List<String> condensationEdges) {}

    static Result findScc(int n, int[][] edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("Invalid graph size/edges");
        }

        List<List<Integer>> graph = new ArrayList<>(n);
        List<List<Integer>> reverse = new ArrayList<>(n);
        for (int v = 0; v < n; v++) {
            graph.add(new ArrayList<>());
            reverse.add(new ArrayList<>());
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[0] >= n
                    || edge[1] < 0 || edge[1] >= n) {
                throw new IllegalArgumentException("Invalid directed edge");
            }
            int from = edge[0];
            int to = edge[1];
            graph.get(from).add(to);
            reverse.get(to).add(from);
        }

        // Pass 1: finishing order on the ORIGINAL graph.
        boolean[] seen = new boolean[n];
        int[] nextEdge = new int[n];
        List<Integer> finished = new ArrayList<>(n);
        ArrayDeque<Integer> stack = new ArrayDeque<>();

        for (int start = 0; start < n; start++) {
            if (seen[start]) {
                continue;
            }

            seen[start] = true;
            stack.push(start);

            while (!stack.isEmpty()) {
                int v = stack.peek();
                if (nextEdge[v] < graph.get(v).size()) {
                    int to = graph.get(v).get(nextEdge[v]++);
                    if (!seen[to]) {
                        seen[to] = true;
                        stack.push(to);
                    }
                } else {
                    stack.pop();
                    finished.add(v); // POSTORDER, not discovery.
                }
            }
        }

        // Pass 2: reverse finishing order on the TRANSPOSE.
        int[] rawId = new int[n];
        Arrays.fill(rawId, -1);
        int rawCount = 0;

        for (int i = finished.size() - 1; i >= 0; i--) {
            int start = finished.get(i);
            if (rawId[start] != -1) {
                continue;
            }

            rawId[start] = rawCount;
            stack.push(start);

            while (!stack.isEmpty()) {
                int v = stack.pop();
                for (int to : reverse.get(v)) {
                    if (rawId[to] == -1) {
                        rawId[to] = rawCount;
                        stack.push(to);
                    }
                }
            }
            rawCount++;
        }

        // Normalize component IDs by the SMALLEST vertex.
        // This is not necessarily topological SCC order.
        int[] rename = new int[rawCount];
        Arrays.fill(rename, -1);
        int nextName = 0;
        for (int v = 0; v < n; v++) {
            int old = rawId[v];
            if (rename[old] == -1) {
                rename[old] = nextName++;
            }
        }

        List<List<Integer>> groups = new ArrayList<>(rawCount);
        for (int id = 0; id < rawCount; id++) {
            groups.add(new ArrayList<>());
        }

        int[] componentOf = new int[n];
        for (int v = 0; v < n; v++) {
            int id = rename[rawId[v]];
            componentOf[v] = id;
            groups.get(id).add(v);
        }

        List<List<Integer>> immutableGroups = new ArrayList<>();
        for (List<Integer> group : groups) {
            immutableGroups.add(List.copyOf(group));
        }

        // Deduplicated arcs of the condensation DAG.
        Set<String> arcs = new LinkedHashSet<>();
        for (int[] edge : edges) {
            int fromId = componentOf[edge[0]];
            int toId = componentOf[edge[1]];
            if (fromId != toId) {
                arcs.add(fromId + "->" + toId);
            }
        }

        return new Result(
                List.copyOf(immutableGroups),
                List.copyOf(arcs));
    }

    private static void show(String name, int n, int[][] edges) {
        Result result = findScc(n, edges);
        System.out.println(name + ": " + result.components());
        System.out.println(
                name + " condensation: " + result.condensationEdges());
    }

    public static void main(String[] args) {
        show("Chain SCCs", 8, new int[][] {
            {0, 1}, {1, 2}, {2, 0},
            {2, 3}, {3, 4}, {4, 5}, {5, 3},
            {5, 6}, {6, 7}, {7, 6},
            {2, 3}, {7, 7}  // parallel edge and self-loop
        });

        show("DAG", 4, new int[][] {
            {0, 1}, {0, 2}, {1, 3}, {2, 3}
        });

        show("Single SCC", 3, new int[][] {
            {0, 1}, {1, 2}, {2, 0}, {1, 1}
        });

        show("Isolated", 3, new int[][] {
            {0, 0}, {2, 2}
        });

        show("Empty", 0, new int[][] {});
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac KosarajuDemo.java
java KosarajuDemo
~~~

**Kết quả đầu ra chuẩn:**

~~~text
Chain SCCs: [[0, 1, 2], [3, 4, 5], [6, 7]]
Chain SCCs condensation: [0->1, 1->2]
DAG: [[0], [1], [2], [3]]
DAG condensation: [0->1, 0->2, 1->3, 2->3]
Single SCC: [[0, 1, 2]]
Single SCC condensation: []
Isolated: [[0], [1], [2]]
Isolated condensation: []
Empty: []
Empty condensation: []
~~~

### Giải thích kết quả

**Chain SCCs:** ba chu trình lần lượt tạo ba SCC. Cạnh `2→3` được khai báo hai lần nhưng trong condensation chỉ có **một** cạnh 0→1. Cạnh `7→7` là self-loop trong SCC, không tạo cạnh giữa các SCC. Cạnh từ nhóm {3,4,5} sang nhóm {6,7} thành 1→2.

**DAG:** mọi đỉnh là SCC đơn vì không có chu trình có hướng giữa hai đỉnh khác nhau. Các cạnh trong condensation trùng với cấu trúc DAG gốc theo ID nhóm.

**Single SCC:** chu trình `0→1→2→0` khiến ba đỉnh đạt tới nhau. Self-loop `1→1` không làm thay đổi phân nhóm.

**Isolated:** đỉnh 1 không có cạnh nào; các đỉnh 0,2 chỉ có self-loop. Không có đường đi giữa hai đỉnh khác nhau, nên có ba SCC đơn và DAG không có cạnh.

**Empty:** n=0 và edges rỗng thì có 0 SCC, không có cung condensation; không được truy cập đỉnh 0.

### Bốn điểm cần đọc kỹ trong mã

1. **Finishing order là postorder thật.** Mảng `nextEdge[v]` bảo đảm chưa pop v trước khi xử lý hết cạnh trong graph[v].
2. **Transpose được dựng đúng hướng:** khi nhận u→v, mã gọi `reverse.get(v).add(u)`.
3. **ID raw được gán ngay khi push:** trong lượt hai, đỉnh chỉ được push một lần, tránh duplicate do các cạnh chồng lặp.
4. **Chuẩn hóa ID không làm đổi SCC:** chỉ đổi tên nhóm cho dễ so sánh test và dựng DAG. Nó không bắt buộc bảo toàn thứ tự topo của raw SCC ID.

## 13. Các ca biên và hành vi quan trọng

| Tình huống | SCC mong đợi | Lưu ý |
|---|---|---|
| V=0, E=0 | Không có SCC | Hai lượt DFS không chạy |
| Một đỉnh, không cạnh | Một SCC {0} | Đường đi độ dài 0 là hợp lệ |
| Một đỉnh, self-loop | Một SCC {0} | Self-loop không tạo SCC mới |
| Hai đỉnh, một cạnh 0→1 | {0}, {1} | Không có đường về 0 |
| Hai đỉnh, hai cạnh 0→1 và 1→0 | {0,1} | Có đường hai chiều |
| Chu trình ba đỉnh | Một SCC ba đỉnh | Mọi đỉnh đi tới nhau |
| DAG không có chu trình | Mỗi đỉnh một SCC | Đồ thị co chính là DAG |
| Nhiều chu trình nối một chiều | Nhiều SCC | Cạnh một chiều không nhập SCC |
| Có đỉnh cô lập | SCC một đỉnh | Không bỏ đỉnh không có cạnh |
| Có cạnh trùng | Không đổi phân hoạch | Output condensation loại cạnh trùng |
| Có self-loop | Không tự hợp với đỉnh khác | SCC một đỉnh vẫn có thể có chu trình |
| Chỉ có các cạnh ngược chiều với DFS từ 0 | Vẫn phải xét mọi đỉnh | Không dừng ở một gốc |
| Đồ thị rất sâu | Dùng DFS iterative | Tránh stack đệ quy Java |
| Endpoint ngoài [0,V−1] | Từ chối | Mã ném IllegalArgumentException |
| Dữ liệu null, n âm, cạnh thiếu endpoint | Từ chối | Không dùng dữ liệu lỗi để tạo graph |

### Các tính chất kiểm thử

- Tổng kích thước các SCC đúng **V**.
- Mỗi đỉnh xuất hiện trong **chính xác một** nhóm.
- Trong một nhóm, mọi cặp đỉnh **đạt tới nhau theo hai chiều**.
- Hai đỉnh khác nhóm không thể đồng thời đạt tới nhau theo hai chiều.
- Đồ thị co giữa các nhóm phải **không có chu trình**.
- Đảo tất cả cạnh không thay đổi tập SCC, dù thứ tự DFS/ID trung gian có thể khác.
- Thêm self-loop hoặc một cạnh trùng với cạnh đã có không làm đổi SCC.
- Đồ thị rỗng, các đỉnh cô lập không được gây ngoại lệ bất ngờ.

## 14. Kiểm thử độc lập bằng khả đạt hai chiều

Với đồ thị nhỏ, một **oracle** dễ hiểu là tính reachability:

1. Với mỗi đỉnh s, chạy BFS/DFS trên G để biết s đạt tới những đỉnh nào. Hoặc dùng **Floyd–Warshall** trên ma trận boolean khi V rất nhỏ.
2. Với mọi u,v, kiểm tra `reach[u][v] && reach[v][u]`.
3. Đưa u,v vào cùng SCC nếu điều kiện trên đúng.
4. So tập các nhóm với output Kosaraju sau khi chuẩn hóa, không phụ thuộc thứ tự DFS.

Với BFS từ mỗi đỉnh, cách kiểm thử tốn O(V(V+E)) thời gian nhưng **độc lập với chứng minh finishing order của Kosaraju**. Trên V≤10, chi phí này thường nhỏ và rất hữu ích để bắt lỗi.

### Gợi ý kiểm thử ngẫu nhiên

Sinh V từ 0..10, với mỗi cặp có thứ tự (u,v) ngẫu nhiên quyết định có cạnh u→v hay không. Cho phép cả:

- Cạnh một chiều và cạnh hai chiều.
- Self-loop u→u.
- Cạnh song song.
- Đỉnh cô lập.
- Đồ thị dày và đồ thị rất thưa.

Mỗi lần thử, so các SCC với oracle reachability. Sau đó dựng condensation từ mảng component ID, xác nhận **mọi cạnh giữa nhóm được đại diện**, không có self-edge ở DAG và có thể topo-sort hết số nhóm.

Nếu muốn kiểm thử **thứ tự output**, trước hết phải định nghĩa **quy tắc chuẩn hóa**. Bản Java ở đây sắp nhóm theo đỉnh nhỏ nhất bằng quét tuyến tính và để các đỉnh trong nhóm tăng dần. Nhưng thứ tự các cạnh condensation được bảo toàn theo lần xuất hiện trong danh sách cạnh gốc, không phải thứ tự từ điển/sắp tăng bắt buộc.

### Oracle riêng cho condensation

Sau khi có ID nhóm chuẩn hóa, duyệt tất cả cạnh u→v của graph:

- Nếu componentOf[u]≠componentOf[v], tập cạnh DAG chuẩn phải chứa chính xác cặp ID đó.
- Nếu bằng nhau, không có cạnh liên SCC.
- Tập cạnh DAG không chứa duplicate dù graph có cạnh song song.
- Một chu trình trong DAG cho biết phân hoạch chưa phải SCC cực đại hoặc có lỗi dựng DAG.

Để xác nhận DAG, dùng Kahn: tính indegree của mỗi thành phần, lần lượt lấy nhóm indegree=0, giảm bậc vào của các nhóm kề. Nếu không xử lý được tất cả K nhóm, DAG vẫn có chu trình ⇒ kết quả sai.

## 15. Ứng dụng cụ thể của Kosaraju

### 15.1. Kiểm tra toàn đồ thị có liên thông mạnh không

Nếu V>0 và thuật toán trả **đúng một SCC có V đỉnh**, toàn đồ thị liên thông mạnh. Nếu V=0, cần định nghĩa riêng cho câu hỏi “toàn đồ thị có liên thông mạnh” vì nhiều đề bài không cho đồ thị rỗng.

### 15.2. Co đồ thị để xử lý chu trình

Một đồ thị tổng quát có thể chứa nhiều chu trình phức tạp. Co mỗi SCC thành một đỉnh biến quan hệ giữa các thành phần thành DAG. Có thể chạy DP theo tô-pô trên DAG đó, ví dụ tính đường đi giá trị lớn nhất khi mỗi SCC có trọng số được gộp thích hợp.

**Chú ý:** một đường đi qua SCC có thể dùng đến nhiều đỉnh khác nhau; gộp trọng số cả SCC là đúng hay không phụ thuộc điều kiện bài toán (có được thăm lại đỉnh/cạnh, tính điểm ra sao). Đừng mặc định cứ co SCC là được cộng tất cả trọng số cho mọi bài đường đi.

### 15.3. Bài toán 2-SAT

Với mỗi biến boolean x, biểu diễn hai literal x và ¬x thành hai đỉnh. Mệnh đề `(a∨b)` tương đương hai kéo theo:

`¬a→b` và `¬b→a`.

Bài 2-SAT vô nghiệm nếu có biến x mà x và ¬x thuộc **cùng một SCC** trong đồ thị kéo theo; khi đó mỗi literal suy ra literal đối ngược, tạo mâu thuẫn. Nếu không có biến nào như vậy, tồn tại một phép gán thỏa; thứ tự SCC trên condensation có thể giúp dựng một phép gán.

**Đừng** tự lấy ID SCC được **chuẩn hóa theo đỉnh nhỏ nhất** trong bài này để gán true/false: cần thứ tự tô-pô/phụ thuộc phù hợp, không phải chỉ số hiển thị.

### 15.4. Phân tích phụ thuộc và mạng trạng thái

Trong đồ thị phụ thuộc giữa công việc, module hay trạng thái, một SCC gồm những nút phụ thuộc vòng nhau. Co SCC cho một DAG có thể cho biết nhóm nào phải xử lý như một đơn vị. Với luồng điều khiển hoặc automaton, SCC thể hiện vùng trạng thái có khả năng quay lại lẫn nhau.

Không đồng nhất “có chu trình” với “SCC có hơn một đỉnh”: SCC một đỉnh có **self-loop** cũng tạo chu trình. Để nhận biết một SCC có chu trình, kiểm tra `size>1` **hoặc** một đỉnh có self-loop.

## 16. So sánh Kosaraju và Tarjan

| Tiêu chí | Kosaraju | Tarjan |
|---|---|---|
| Ý tưởng | Hai lượt DFS với finishing order và transpose | Một DFS với discovery index và low-link |
| Thời gian | O(V+E) | O(V+E) |
| Bộ nhớ | O(V+E), cần đồ thị đảo chiều trong cách thông thường | O(V+E) tính cả đồ thị, thêm stack/low-link |
| Số lượt | DFS trên G rồi trên Gᵀ | Một lượt DFS trên G |
| Dữ liệu phụ | visited, finish order, transpose | index, low-link, trạng thái trên stack |
| Dễ chứng minh | Dựa vào DAG SCC và thứ tự finish | Dựa vào low-link và stack thành phần |
| DFS iterative | Tương đối trực quan với nextEdge | Cần mô phỏng cập nhật low-link khi trả về |
| Trả thứ tự SCC | Phụ thuộc hướng pass và DFS | Phụ thuộc quá trình pop SCC |

Cả hai đều giải đúng bài SCC. Kosaraju có ưu điểm trực quan khi muốn dựng và hiểu đồ thị chuyển vị; Tarjan có thể tiết kiệm việc dựng transpose, nhưng cấu trúc low-link dễ cài sai hơn nếu chưa quen.

**Lựa chọn kỹ thuật:** nếu đã có graph và reverse sẵn, Kosaraju rất thuận tiện. Nếu hạn chế bộ nhớ dành cho danh sách cạnh đảo, có thể cân nhắc Tarjan hoặc một phương pháp thích hợp khác. Dùng DFS iterative khi chuỗi cạnh có thể tạo đường sâu tới hàng trăm nghìn đỉnh và recursion limit của ngôn ngữ gây rủi ro.

## 17. Các lỗi phổ biến cần tránh

1. **Dùng một DFS rồi gom tất cả đỉnh reachable:** reachable một chiều không phải SCC.
2. **Nhầm SCC với thành phần yếu:** bỏ chiều cạnh làm phân nhóm sai.
3. **Ghi finish khi phát hiện đỉnh:** đó là preorder, không dùng được thay postorder.
4. **Dùng stack iterative nhưng pop v quá sớm:** không tái tạo đúng finishing time của DFS.
5. **Chỉ DFS từ đỉnh 0:** bỏ đỉnh cô lập hoặc thành phần không đạt từ 0.
6. **Quên reset visited giữa hai lượt:** lượt hai không thể gom SCC vì tất cả đã visited.
7. **Quên chuyển vị:** lượt hai trên G với thứ tự sai có thể đi sang những SCC khác.
8. **Đảo thứ tự danh sách kề thay vì đảo chiều cạnh:** đó không phải transpose.
9. **Duyệt finishOrder từ đầu đến cuối:** chọn SCC sai và có thể gom nhiều SCC trên Gᵀ.
10. **Đảo đồ thị trước cả hai lượt mà vẫn dùng chứng minh của bản gốc:** phải đồng bộ thứ tự finish với hướng của lượt đầu.
11. **Quên một đỉnh không xuất hiện trong edges:** nó vẫn là một SCC nếu V bao gồm nó.
12. **Không chống duplicate:** cạnh song song có thể làm push đỉnh nhiều lần nếu visited đánh dấu quá muộn.
13. **Nhầm SCC đơn với đỉnh không có chu trình:** một đỉnh có self-loop vẫn là SCC đơn.
14. **Cho rằng ID in ra luôn topo:** sau chuẩn hóa theo đỉnh nhỏ nhất có thể không còn thứ tự topo.
15. **Dựng DAG còn self-edge:** cạnh nằm bên trong SCC không được biến thành cung liên SCC.
16. **Không khử duplicate DAG khi cần cạnh duy nhất:** nhiều cạnh gốc có thể nối cùng cặp SCC.
17. **Trả số SCC bằng số đỉnh đã duyệt ở lượt hai:** một DFS mới có thể thu nhiều đỉnh.
18. **Dùng đồ thị vô hướng thay G có hướng:** đảo mỗi cạnh thành hai cung có thể hợp sai SCC.
19. **DFS đệ quy trên đồ thị cực sâu mà bỏ qua stack:** Java có thể ném StackOverflowError.
20. **Tin rằng thứ tự SCC là duy nhất:** chỉ tập các nhóm là duy nhất; cách đánh số/thứ tự DFS có thể khác nhau.

## 18. Checklist khi tự giải bài Kosaraju

- Bài toán cần **SCC của đồ thị có hướng**, không phải thành phần liên thông vô hướng?
- Các đỉnh được đánh số thế nào? Có bao gồm đỉnh không xuất hiện ở bất kỳ cạnh nào?
- Mọi cạnh u→v có được lưu trong graph[u] và đảo thành v→u trong transpose[v] không?
- Lượt một có chạy DFS **mọi đỉnh**, và chỉ append vào finish khi **đã xử lý hết các cạnh đi ra** không?
- Nếu dùng iterative DFS, stack có lưu được con trỏ cạnh đang xét để có postorder thật không?
- Lượt hai có dùng **transpose** và **finishOrder giảm dần**, với visited/reset riêng không?
- Mỗi lượt DFS lượt hai có thu đúng một nhóm; mỗi đỉnh xuất hiện trong đúng một nhóm không?
- Đã phân biệt thứ tự DFS tìm SCC với quy tắc **đánh số SCC để in** chưa?
- Nếu dựng DAG, đã bỏ cạnh nội SCC và khử các cặp SCC trùng khi đề yêu cầu không?
- Condensation có thực sự là DAG, và có định dùng topological sort trước khi DP trên DAG không?
- Độ phức tạp đã tính cả dựng transpose, các lượt DFS và dữ liệu phụ thành **O(V+E)** chưa?
- Có tránh stack recursion quá sâu hoặc chọn biện pháp thích hợp cho V lớn không?
- Đã thử đồ thị rỗng, singleton, self-loop, multi-edge, chu trình, DAG, thành phần cô lập và cạnh chỉ một chiều chưa?
- Đã kiểm chứng trên đồ thị nhỏ bằng oracle **reach[u][v] && reach[v][u]** chưa?

**Kết luận:** Kosaraju phân rã đồ thị có hướng thành các SCC trong **O(V+E)** bằng hai lượt DFS. Lượt đầu trên G cung cấp **thứ tự kết thúc**, lượt sau trên Gᵀ theo thứ tự kết thúc giảm dần thu **một SCC mỗi lượt DFS mới**. Tính đúng đến từ việc đồ thị co SCC là DAG và finishing order đưa SCC nguồn của phần chưa xử lý lên trước, nên DFS trên transpose không chạy lọt sang một SCC chưa xử lý khác. Khi triển khai, cần đặc biệt chú ý **postorder, hướng đảo cạnh, reset visited và phạm vi tất cả đỉnh**.