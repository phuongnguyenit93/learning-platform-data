# Mô hình hóa phân công bằng ghép cặp hoặc luồng

## 1. Từ bài toán phân công sang đồ thị

Một bài toán **phân công (assignment)** yêu cầu ghép người, máy, ca làm, dự án, phòng, nhiệm vụ hoặc tài nguyên sao cho mỗi đối tượng nhận được những lựa chọn hợp lệ và các giới hạn sử dụng được tôn trọng.

Ví dụ: có một tập nhân viên và một tập công việc. Không phải nhân viên nào cũng làm được mọi việc. Ta cần phân công càng nhiều nhân viên càng tốt, mỗi nhân viên nhiều nhất một việc và mỗi việc nhiều nhất một nhân viên. Đây là bài toán **ghép cặp hai phía (bipartite matching)**.

Nếu mỗi lựa chọn hợp lệ được biểu diễn bằng một cạnh, bài toán trở thành tìm tập cạnh không chung đầu mút lớn nhất. Nếu mỗi đối tượng có thể nhận nhiều nhiệm vụ hoặc mỗi nhiệm vụ cần nhiều chỗ, ta mở rộng sang **luồng cực đại (maximum flow)** với sức chứa trên các cạnh.

Khi còn chi phí, lợi nhuận hoặc điểm ưu tiên cho mỗi cặp, bài toán chuyển sang **phân công có trọng số (weighted assignment)**: tối ưu tổng chi phí/lợi ích, thường dùng Hungarian algorithm hoặc min-cost max-flow.

Bài học xây dựng một quy trình mô hình hóa có thể dùng lại:

1. Xác định hai tập đối tượng và quan hệ đủ điều kiện.
2. Phân biệt phân công tối đa, phân công đầy đủ và phân công tối ưu chi phí.
3. Biểu diễn điều kiện bằng cạnh và capacity.
4. Chọn matching, max-flow, min-cost flow hoặc thuật toán phù hợp.
5. Chứng minh tính đúng bằng bất biến và định lý luồng.
6. Kiểm thử với đồ thị rỗng, thiếu lựa chọn, cạnh trùng, capacity và oracle brute force.

## 2. Matching hai phía: định nghĩa chính xác

Một đồ thị hai phía là \(G=(L,R,E)\), trong đó:

- L là tập đỉnh bên trái, ví dụ nhân viên.
- R là tập đỉnh bên phải, ví dụ công việc.
- E là tập cạnh nối một đỉnh L với một đỉnh R; cạnh (u,v) tồn tại khi u đủ điều kiện nhận v.

**Matching** là tập cạnh sao cho không có hai cạnh cùng chia sẻ một đỉnh. Như vậy một nhân viên không nhận hai việc trong mô hình matching đơn vị và một công việc không giao cho hai nhân viên.

Các đại lượng quan trọng:

- **Matching size:** số cạnh trong matching.
- **Maximum matching:** matching có số cạnh lớn nhất.
- **Perfect matching:** matching phủ tất cả đỉnh ở cả hai phía; thường chỉ có thể có nếu |L|=|R|.
- **Left-perfect matching:** matching phủ mọi đỉnh L; có thể tồn tại khi |L|≤|R|.
- **Unmatched vertex:** nhân viên hoặc công việc không được ghép.

Cần dùng đúng thuật ngữ theo yêu cầu. Nếu có 5 nhân viên và 8 công việc, phân công tất cả nhân viên là left-perfect matching, không phải perfect matching phủ cả hai phía.

### 2.1. Ví dụ nhỏ

Có 4 nhân viên W0..W3 và 4 việc J0..J3:

```text
W0 có thể làm: J0, J1
W1 có thể làm: J0
W2 có thể làm: J1, J2
W3 có thể làm: J2, J3
```

Một matching có đủ 4 cặp:

```text
W0 -> J1
W1 -> J0
W2 -> J2
W3 -> J3
```

Không có nhân viên hay công việc nào xuất hiện hai lần. Đây là matching size 4, nên mọi nhân viên đều được phân công.

### 2.2. Vì sao không thể tham lam chọn cạnh đầu tiên?

Nếu gán W0→J0 trước, W1 chỉ còn J0 và bị bỏ lỡ. Một thuật toán tham lam có thể kết luận chỉ phân công được 3 người, mặc dù có matching size 4 ở trên. Cần có khả năng **đảo lựa chọn cũ** để tìm augmenting path.

Đây là khác biệt cốt lõi giữa “lần lượt chọn một cạnh trống” và thuật toán matching đúng.

## 3. Quy trình mô hình hóa một đề phân công

Trước khi viết code, trả lời các câu hỏi:

**Ai được phân công?** Đây là tập L. Một phần tử có thể là người, máy, lớp học, đơn hàng hoặc ca trực.

**Tài nguyên/công việc là gì?** Đây là tập R. Phân biệt một nhiệm vụ với một slot: nếu một nhiệm vụ có 3 chỗ, có thể tạo 3 slot hoặc dùng capacity 3.

**Khi nào một cặp hợp lệ?** Tạo cạnh u→v nếu mọi điều kiện cục bộ cho cặp đó đều thỏa: kỹ năng, lịch, vị trí, quyền truy cập, thời lượng, ngân sách đơn lẻ.

**Mỗi bên được dùng bao nhiêu lần?** Nếu mỗi bên tối đa một lần, matching đơn vị. Nếu một người làm tối đa 4 việc, nguồn→người có capacity 4. Nếu một việc cần 3 người, việc→đích có capacity 3, nhưng phải xem có cần đúng 3 hay chỉ tối đa 3.

**Mục tiêu là gì?** Tối đa số cặp, phải ghép tất cả, tối thiểu chi phí, tối đa điểm, hay đạt một quota? Những mục tiêu này không đồng nghĩa.

**Điều gì là ràng buộc toàn cục?** Ví dụ “W0 và W1 không được cùng nhận ca đêm”, “mỗi nhóm phải có ít nhất một trưởng nhóm”, “nếu nhận dự án A thì không nhận B”. Những điều kiện liên kết nhiều quyết định có thể không biểu diễn được bằng matching hai phía đơn giản.

**Output cần gì?** Chỉ cần số lượng, cần cặp cụ thể, cần báo lý do không khả thi, hay cần tổng chi phí và danh sách tối ưu?

Một mô hình đúng phải giữ nguyên ý nghĩa của đề bài. Nếu chuyển mỗi công việc thành một slot, phải đảm bảo các slot thật sự tương đương và không tạo thêm lựa chọn giả.

## 4. Giải matching bằng đường tăng cường

Giả sử ta đã có một matching hiện tại M. Một **augmenting path** là đường đi bắt đầu từ một đỉnh L chưa được ghép, kết thúc ở một đỉnh R chưa được ghép, và luân phiên:

- Cạnh chưa thuộc matching.
- Cạnh đang thuộc matching.
- Cạnh chưa thuộc matching.
- ... kết thúc bằng cạnh chưa thuộc matching.

Khi đảo trạng thái tất cả cạnh trên đường này (cạnh thuộc M bị bỏ, cạnh chưa thuộc M được thêm), matching vẫn hợp lệ nhưng tăng size đúng 1.

Ví dụ:

```text
Trước:
W0 -- J0       (đang ghép)
W1 -- J0       (chưa ghép)
W0 -- J1       (chưa ghép)

Đường tăng cường:
W1 -> J0 -> W0 -> J1

Sau khi đảo:
W1 -- J0
W0 -- J1
```

Matching tăng từ 1 lên 2. Cạnh W0–J0 được giải phóng để W1 nhận J0.

### 4.1. Định lý augmenting-path

**Định lý Berge:** một matching là maximum khi và chỉ khi không tồn tại augmenting path đối với matching đó.

- Nếu có augmenting path, đảo đường làm matching tăng, nên matching hiện tại chưa maximum.
- Nếu matching chưa maximum, xét matching maximum M*. Trong đồ thị đối xứng sai khác giữa M và M*, các thành phần là đường đi hoặc chu trình xen kẽ cạnh của hai matching. Vì M* có nhiều cạnh hơn, phải tồn tại một thành phần là đường xen kẽ có nhiều cạnh M* hơn M; đó là augmenting path cho M.

Do đó, tìm và đảo các đường tăng cường cho tới khi không còn đường nào là cách xác định maximum matching.

### 4.2. Thuật toán Kuhn DFS

Một cách cơ bản là duyệt từng đỉnh trái và tìm đường tăng cường bằng DFS:

```text
tryMatch(u):
    nếu u đã thăm trong lượt DFS này: return false
    đánh dấu u đã thăm
    với mỗi v kề u:
        nếu v chưa có người ghép
           hoặc tryMatch(matchRight[v]) thành công:
            matchRight[v] = u
            matchLeft[u] = v
            return true
    return false

answer = 0
với mỗi u bên trái:
    reset visitedLeft
    nếu tryMatch(u): answer++
```

Mỗi lần DFS thành công, matching tăng một. Với adjacency list, cách cài đặt phổ biến có cận O(|L|·|E|) trong worst case; nó dễ hiểu, hợp với đồ thị nhỏ và là lựa chọn tốt cho bản đầu tiên.

**Đừng reset visited cho mỗi nhánh trong cùng một lần DFS.** Nếu làm vậy, một chu trình xen kẽ có thể bị duyệt lặp không cần thiết hoặc recursion khó kết thúc. Visited phải được dùng chung trong một lượt augmenting search.

## 5. Hopcroft–Karp cho matching lớn

Khi đồ thị lớn và sparse, **Hopcroft–Karp** tìm nhiều augmenting path ngắn nhất trong cùng một phase:

1. BFS phân lớp các đỉnh theo khoảng cách tới đỉnh phải tự do gần nhất.
2. DFS chỉ tìm các đường tăng cường tuân thủ lớp ngắn nhất.
3. Đảo nhiều đường tăng cường **không chung đỉnh** trong phase.
4. Lặp tới khi BFS không còn đường.

Độ phức tạp là **O(E√V)** với V=|L|+|R| và E là số cạnh. Cách này thường hiệu quả hơn DFS Kuhn O(|L|E) khi matching có quy mô lớn.

Các chi tiết triển khai cần cẩn thận:

- BFS phải xác định **độ dài ngắn nhất** tới đỉnh phải tự do.
- DFS chỉ được theo đúng các lớp BFS và không chấp nhận đường dài hơn ngắn nhất trong phase.
- Khi một đỉnh thất bại trong DFS, đánh dấu distance của nó là vô cực trong phase để tránh lặp tìm kiếm vô ích.
- Phải reset pairLeft/pairRight về −1 lúc khởi tạo.
- Đồ thị không có cạnh hoặc một bên rỗng phải trả matching size 0.

Code Java ở cuối bài sử dụng Dinic trên mạng luồng để minh họa cách mô hình hóa và trích xuất matching; Hopcroft–Karp là lựa chọn chuyên biệt khi cần tối ưu matching hai phía lớn.

## 6. Quy đổi matching thành maximum flow

Một matching đơn vị có thể biến thành mạng luồng:

- Thêm source s và sink t.
- Cạnh s→u cho mọi u∈L, capacity 1.
- Cạnh u→v cho mỗi quan hệ đủ điều kiện (u,v)∈E, capacity 1.
- Cạnh v→t cho mọi v∈R, capacity 1.

```text
             capacity 1                 capacity 1
source ----------------> Worker ----------------> Job ----------------> sink
                         (left)      eligible       (right)
```

Mọi đường s→t đi qua đúng một worker và một job. Capacity 1 ở source→worker ngăn worker nhận nhiều việc; capacity 1 ở job→sink ngăn job được gán nhiều lần. Cạnh worker→job chỉ tồn tại nếu cặp hợp lệ.

**Một đơn vị flow tương ứng một cặp được ghép.** Vì vậy:

**Maximum matching size = maximum flow value.**

### 6.1. Vì sao flow nguyên tạo matching?

Các capacity đều là số nguyên. Thuật toán max-flow trên capacity nguyên có thể duy trì flow nguyên trong từng cạnh. Mỗi worker có tổng flow đi ra tối đa 1 và mỗi job có tổng flow đi vào tối đa 1. Các cạnh worker→job có flow 1 xác định matching hợp lệ.

Ngược lại, từ một matching hợp lệ, gửi 1 đơn vị trên đường s→worker→job→t cho từng cặp; các capacity không bị vi phạm. Vì thế mọi matching tương ứng với một flow có cùng giá trị. Hai chiều này chứng minh giá trị tối ưu bằng nhau.

### 6.2. Kiểm tra phân công đầy đủ

Nếu có n worker cần phân công và maximum flow bằng n, tất cả worker được ghép. Nếu flow<n, không tồn tại cách ghép tất cả theo các cạnh đủ điều kiện.

**Ví dụ:** ba người cùng chỉ đủ điều kiện cho một công việc J0, trong khi có thể có thêm J1 nhưng không ai khác đủ điều kiện. Flow tối đa 1; không thể ép phân công đủ ba người bằng cách thay đổi thứ tự greedy.

Nếu |L|=|R| và flow=|L| thì ta có perfect matching phủ cả hai phía. Nếu |L|<|R| và flow=|L| thì đó là left-perfect matching.

## 7. Định lý Hall và chẩn đoán không thể phân công đủ

Với matching phủ mọi đỉnh L, **định lý Hall** nói rằng matching như vậy tồn tại khi và chỉ khi với mọi tập con X⊆L:

**|N(X)| ≥ |X|**,

trong đó N(X) là tập tất cả đỉnh R kề ít nhất một đỉnh trong X.

Trực giác: bất kỳ nhóm k người nào cũng phải có ít nhất k lựa chọn công việc khác nhau. Nếu ba người chỉ có hai việc chung, chắc chắn một người không được phân công.

Không cần liệt kê tất cả 2^|L| tập con để chạy thuật toán. Max-flow/matching tìm được kết quả đa thức; Hall hữu ích để hiểu vì sao thiếu khả năng và giải thích bottleneck.

Một minimum cut trong mạng flow cũng có thể chỉ ra nhóm cạnh/capacity tạo thành nút thắt. Nếu cần báo lý do nghiệp vụ, có thể phân tích reachable set trong residual graph sau max flow, nhưng phải định nghĩa cách diễn giải cut thành thông báo cho người dùng.

## 8. Dinic và residual graph

**Residual graph** ghi lại khả năng tăng hoặc hoàn tác flow:

- Cạnh gốc u→v có residual capacity còn có thể gửi.
- Cạnh ngược v→u có capacity bằng lượng flow đã gửi, cho phép đổi quyết định cũ.

Dinic lặp hai bước:

1. BFS dựng **level graph** chỉ chứa cạnh residual capacity dương và đi từ level d sang d+1.
2. DFS gửi một **blocking flow** trong level graph, dùng con trỏ cạnh hiện tại để tránh thử lại những cạnh đã cạn/không dùng được.

Khi BFS không còn tới sink, flow hiện tại là maximum theo định lý max-flow/min-cut.

### 8.1. Cận độ phức tạp

Với mạng tổng quát, Dinic có cận O(V²E). Với mạng matching hai phía dạng **unit network** như reduction trên, có cận tốt hơn O(E√V), cùng bậc với Hopcroft–Karp. Một số cận phụ thuộc cấu trúc mạng/loại capacity; không áp dụng cận unit-network cho mọi mạng có capacity tùy ý.

Mạng reduction có V=|L|+|R|+2 và E'=|L|+|R|+|E| cạnh thuận, cộng cạnh residual ngược. Với input sparse, adjacency list giúp lưu O(V+E').

Code mẫu dùng DFS đệ quy trong Dinic để dễ theo dõi; với mạng rất sâu hoặc số node cực lớn, cần cân nhắc iterative DFS, stack và memory. Đừng suy ra mã demo tự động phù hợp mọi kích thước production.

## 9. Capacity: khi một người nhận nhiều việc hoặc một việc có nhiều slot

Matching đơn vị giới hạn mỗi đỉnh tối đa một cặp. Network flow cho phép nới capacity:

- s→worker i có capacity c_i: người i nhận tối đa c_i nhiệm vụ.
- worker i→job j có capacity 1: cặp i,j chỉ xuất hiện tối đa một lần.
- job j→t có capacity d_j: nhiệm vụ j có tối đa d_j slot.

Một đơn vị flow vẫn là một phân công. Tổng flow là tổng số assignment.

Ví dụ có 3 nhân viên với sức chứa [2,1,1], và 2 dự án có capacity [2,2]. Nếu cạnh hợp lệ cho phép, maximum flow có thể đạt 4, trong khi matching đơn vị chỉ đạt tối đa min(3,2)=2.

### 9.1. Exactly, at most và at least

- **At most k:** capacity k trên cạnh thích hợp.
- **Exactly k:** vừa cần upper bound k vừa cần lower bound k; flow thường có thể ép bằng việc yêu cầu tổng flow hoặc dùng circulation có lower bounds.
- **At least k:** kiểm tra flow đạt tối thiểu k; nếu còn các ràng buộc lower bound khác, cần biến đổi circulation.
- **Optional assignment:** cho phép một worker không có flow; nếu mọi worker bắt buộc nhận việc, kiểm flow bằng số worker cần gán.

Với cạnh có lower bound l và upper bound c, biến đổi capacity thành c−l, cập nhật demand ở hai đầu và thêm super-source/super-sink để kiểm feasible circulation. Không được chỉ đặt capacity c rồi cho rằng đã đảm bảo ít nhất l.

### 9.2. Slot hay capacity?

Nếu 5 ghế trong cùng một lớp học hoàn toàn tương đương, capacity 5 trên job→sink thường gọn hơn tạo 5 node slot. Nếu từng slot có điều kiện khác nhau (ví dụ ca sáng/ca tối hoặc vị trí khác nhau), tách slot thành node riêng để không làm mất tính đủ điều kiện.

Việc nhân bản node chỉ đúng khi các bản sao **thực sự tương đương** về mọi ràng buộc.

## 10. Phân công có chi phí: min-cost max-flow

Khi mỗi cặp worker-job có chi phí c_ij, chỉ tối đa hóa số assignment là chưa đủ. Có thể muốn phân công F cặp với tổng chi phí nhỏ nhất.

Mạng min-cost flow:

- s→worker i: capacity 1, cost 0.
- worker i→job j nếu hợp lệ: capacity 1, cost c_ij.
- job j→t: capacity 1, cost 0.
- Yêu cầu gửi đúng F đơn vị flow với tổng cost nhỏ nhất.

```text
cost của một flow =
    sum(cost(edge) * flow(edge))

Mục tiêu:
    min total cost
    subject to flow value = F
```

Nếu mọi worker phải nhận đúng một việc, đặt F=n. Nếu F nhỏ hơn n, thuật toán chỉ tìm F cặp chi phí nhỏ nhất trong các phương án khả thi; phải ghi rõ worker không được gán là có chấp nhận được hay không.

### 10.1. Tối đa hóa điểm thay vì tối thiểu hóa chi phí

Nếu score s_ij càng cao càng tốt, đặt c_ij = C−s_ij với C là một hằng không nhỏ hơn score lớn nhất trên các cạnh hợp lệ. Với F cố định:

**sum(C−s_ij) = F·C − sum(s_ij)**,

nên min cost tương đương max tổng score. Dùng kiểu long và kiểm overflow khi trừ/tính tổng.

Có thể dùng cost=−score, nhưng cạnh cost âm đòi thuật toán shortest-path khởi tạo phù hợp. Không đưa Dijkstra thường trực tiếp vào mạng có negative edge mà không dùng potential hoặc xử lý Bellman–Ford.

### 10.2. Successive shortest augmenting path và potential

Một cách phổ biến là gửi từng đơn vị flow theo đường ngắn nhất trong residual network. Khi có cạnh cost âm, dùng **node potential** để tạo reduced cost không âm:

```text
reducedCost(u,v) = cost(u,v) + potential[u] - potential[v]
```

Sau khi tìm đường ngắn nhất bằng Dijkstra, cập nhật potential cho các node reachable, rồi augment. Nếu cost ban đầu âm, cần khởi tạo potential hợp lệ (ví dụ Bellman–Ford) hoặc biến đổi cost để đảm bảo điều kiện. Cạnh residual ngược có cost âm đối xứng với cạnh thuận, nên cần cập nhật đúng khi gửi flow.

Cận phổ biến với successive shortest path + Dijkstra/potential là O(F·E log V) sau khi có potential hợp lệ, tùy cách cài đặt và chi phí khởi tạo. Nếu F lớn hoặc graph lớn, cân nhắc thuật toán min-cost flow khác.

## 11. Hungarian algorithm hay min-cost flow?

**Hungarian algorithm** giải bài toán assignment trọng số trên ma trận chi phí, thường dạng n×n; với ma trận vuông, cận kinh điển O(n³), biến thể chữ nhật n≤m thường O(n²m). Nó rất phù hợp khi mỗi hàng/cột được gán tối đa một lần và ma trận chi phí khá dày.

**Min-cost max-flow** linh hoạt hơn khi:

- Cạnh chỉ tồn tại với cặp đủ điều kiện (sparse eligibility).
- Có capacity khác 1.
- Cần ghép F cặp thay vì buộc perfect assignment.
- Mô hình có thêm tầng nhóm/slot có thể biểu diễn bằng network flow.
- Có cost và ràng buộc luồng.

**Hopcroft–Karp** dành cho matching hai phía không trọng số, khi mục tiêu là số cặp tối đa.

**Dinic** giải maximum flow tổng quát và minh họa reduction rõ; với matching hai phía lớn, Hopcroft–Karp thường là lựa chọn chuyên biệt đơn giản hơn. Với assignment có trọng số, dùng Hungarian hoặc min-cost flow thay vì chỉ max-flow.

Không chọn thuật toán theo tên quen thuộc; chọn theo **ngữ nghĩa** và cấu trúc ràng buộc.

## 12. Các ràng buộc nào không còn là matching đơn giản?

Mô hình flow hai phía xử lý tốt những giới hạn có thể diễn đạt thành capacity và conservation. Nhưng một số ràng buộc kết hợp nhiều quyết định không biểu diễn bằng mạng flow đơn giản:

- Nếu A nhận task X thì B không được nhận task Y.
- Một task cần đồng thời một kỹ sư và một phiên dịch, trong đó hai người phải làm cùng một nhóm.
- Mỗi nhóm kỹ năng phải có ít nhất một đại diện, nhưng các lựa chọn còn liên kết với nhau.
- Chi phí cố định phát sinh một lần nếu một nhân viên được dùng bất kỳ nhiệm vụ nào.
- Có bonus/penalty phụ thuộc vào cặp hoặc bộ ba assignment.
- Chọn một trong hai cấu hình toàn cục, mỗi cấu hình thay đổi tập cạnh còn lại.

Khi đó có thể cần integer linear programming (ILP), constraint programming, SAT/SMT, hoặc thuật toán tổ hợp khác. **Không cố ép mọi bài phân công thành flow** nếu phải làm mất điều kiện toàn cục.

## 13. Cách lấy assignment từ flow

Sau khi maximum flow kết thúc, các cạnh worker→job có flow 1 là các cặp được chọn. Với cạnh thuận capacity ban đầu 1, residual capacity còn 0 khi đang mang một đơn vị flow; nếu flow bị hoàn tác, residual capacity được phục hồi về 1.

Mã mẫu giữ tham chiếu tới từng cạnh worker-job khi tạo mạng, rồi đọc residual capacity để khôi phục assignment:

- Mỗi worker có tối đa một job.
- Mỗi job xuất hiện tối đa một lần.
- Mỗi cặp xuất ra phải có eligibility edge.
- Số cặp trích xuất phải bằng flow value.

Đây là bước quan trọng: chỉ in **số flow** thì chưa đủ nếu ứng dụng cần danh sách cặp. Cũng không nên đọc các cạnh ngược như thể đó là assignment; chỉ đọc các cạnh gốc đã lưu tham chiếu.

## 14. Ví dụ Java 17: Dinic reduction thành bipartite matching

Chương trình dưới đây nhận ma trận boolean `eligible[worker][job]`. Giá trị true nghĩa là cặp hợp lệ. Mỗi worker và job có capacity 1; do đó đây là maximum-cardinality bipartite matching.

Mã có các thành phần:

- Dinic với adjacency list và residual edges.
- Xây source→worker→job→sink.
- Trích assignment từ residual capacity của cạnh worker-job gốc.
- Brute-force oracle cho graph nhỏ.
- Vét cạn mọi bipartite graph tới 3 worker và 3 job.
- Random có seed để so Dinic với oracle.
- Ca rỗng, không có job và graph không thể phân công đầy đủ.



import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

public final class AssignmentFlowDemo {
    private AssignmentFlowDemo() {}

    private static final class Edge {
        final int to;
        final int reverseIndex;
        long capacity;

        Edge(int to, int reverseIndex, long capacity) {
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.capacity = capacity;
        }
    }

    private static final class Dinic {
        private final List<Edge>[] graph;
        private final int[] level;
        private final int[] nextEdge;

        @SuppressWarnings("unchecked")
        Dinic(int nodeCount) {
            graph = (List<Edge>[]) new List<?>[nodeCount];
            for (int i = 0; i < nodeCount; i++) {
                graph[i] = new ArrayList<>();
            }
            level = new int[nodeCount];
            nextEdge = new int[nodeCount];
        }

        Edge addEdge(int from, int to, long capacity) {
            if (capacity < 0) {
                throw new IllegalArgumentException("negative capacity");
            }
            Edge forward = new Edge(to, graph[to].size(), capacity);
            Edge reverse = new Edge(from, graph[from].size(), 0);
            graph[from].add(forward);
            graph[to].add(reverse);
            return forward;
        }

        private boolean buildLevels(int source, int sink) {
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            level[source] = 0;
            queue.add(source);

            while (!queue.isEmpty()) {
                int u = queue.remove();
                for (Edge edge : graph[u]) {
                    if (edge.capacity > 0 && level[edge.to] == -1) {
                        level[edge.to] = level[u] + 1;
                        queue.add(edge.to);
                    }
                }
            }
            return level[sink] != -1;
        }

        private long sendFlow(int u, int sink, long pushed) {
            if (pushed == 0) return 0;
            if (u == sink) return pushed;

            for (; nextEdge[u] < graph[u].size(); nextEdge[u]++) {
                Edge edge = graph[u].get(nextEdge[u]);
                if (edge.capacity == 0
                        || level[edge.to] != level[u] + 1) {
                    continue;
                }

                long sent = sendFlow(
                    edge.to, sink, Math.min(pushed, edge.capacity));
                if (sent == 0) continue;

                edge.capacity -= sent;
                graph[edge.to].get(edge.reverseIndex).capacity += sent;
                return sent;
            }
            return 0;
        }

        long maxFlow(int source, int sink) {
            long total = 0;
            while (buildLevels(source, sink)) {
                Arrays.fill(nextEdge, 0);
                long sent;
                while ((sent = sendFlow(
                        source, sink, Long.MAX_VALUE)) > 0) {
                    total = Math.addExact(total, sent);
                }
            }
            return total;
        }
    }

    record Matching(int size, int[] jobForWorker) {}

    static Matching maximumMatching(
            boolean[][] eligible, int workers, int jobs) {
        if (eligible == null) {
            throw new NullPointerException("eligible");
        }
        if (eligible.length != workers) {
            throw new IllegalArgumentException("worker count mismatch");
        }
        for (boolean[] row : eligible) {
            if (row == null || row.length != jobs) {
                throw new IllegalArgumentException("job count mismatch");
            }
        }

        int source = 0;
        int firstWorker = 1;
        int firstJob = firstWorker + workers;
        int sink = firstJob + jobs;
        Dinic network = new Dinic(sink + 1);

        for (int i = 0; i < workers; i++) {
            network.addEdge(source, firstWorker + i, 1);
        }
        for (int j = 0; j < jobs; j++) {
            network.addEdge(firstJob + j, sink, 1);
        }

        Edge[][] assignmentEdges = new Edge[workers][jobs];
        for (int i = 0; i < workers; i++) {
            for (int j = 0; j < jobs; j++) {
                if (eligible[i][j]) {
                    assignmentEdges[i][j] =
                        network.addEdge(firstWorker + i, firstJob + j, 1);
                }
            }
        }

        long flow = network.maxFlow(source, sink);
        int[] jobForWorker = new int[workers];
        Arrays.fill(jobForWorker, -1);
        boolean[] usedJob = new boolean[jobs];
        int count = 0;

        for (int i = 0; i < workers; i++) {
            for (int j = 0; j < jobs; j++) {
                Edge edge = assignmentEdges[i][j];
                if (edge != null && edge.capacity == 0) {
                    if (jobForWorker[i] != -1 || usedJob[j]) {
                        throw new IllegalStateException(
                            "flow did not encode a matching");
                    }
                    jobForWorker[i] = j;
                    usedJob[j] = true;
                    count++;
                }
            }
        }
        if (count != flow) {
            throw new IllegalStateException(
                "extracted matching size differs from flow");
        }
        return new Matching(Math.toIntExact(flow), jobForWorker);
    }

    // Exponential oracle, used only when the number of jobs is small.
    static int bruteForce(
            boolean[][] eligible, int workers, int jobs,
            int worker, int usedJobsMask) {
        if (worker == workers) return 0;

        int best = bruteForce(
            eligible, workers, jobs, worker + 1, usedJobsMask);
        for (int j = 0; j < jobs; j++) {
            if (eligible[worker][j]
                    && (usedJobsMask & (1 << j)) == 0) {
                best = Math.max(best, 1 + bruteForce(
                    eligible, workers, jobs,
                    worker + 1, usedJobsMask | (1 << j)));
            }
        }
        return best;
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static void verifyMatching(
            boolean[][] eligible, int workers, int jobs,
            Matching matching) {
        boolean[] used = new boolean[jobs];
        int count = 0;
        for (int i = 0; i < workers; i++) {
            int j = matching.jobForWorker()[i];
            if (j == -1) continue;
            check(j >= 0 && j < jobs, "job index out of range");
            check(eligible[i][j], "ineligible assignment");
            check(!used[j], "job assigned more than once");
            used[j] = true;
            count++;
        }
        check(count == matching.size(), "matching count mismatch");
    }

    static void verifyAgainstOracle(
            boolean[][] eligible, int workers, int jobs) {
        Matching actual = maximumMatching(eligible, workers, jobs);
        int expected = bruteForce(
            eligible, workers, jobs, 0, 0);
        check(actual.size() == expected,
            "max-flow vs brute-force mismatch");
        verifyMatching(eligible, workers, jobs, actual);
    }

    static long exhaustiveGraphs() {
        long tested = 0;
        for (int workers = 0; workers <= 3; workers++) {
            for (int jobs = 0; jobs <= 3; jobs++) {
                int possibleEdges = workers * jobs;
                int graphCount = 1 << possibleEdges;
                for (int mask = 0; mask < graphCount; mask++) {
                    boolean[][] eligible =
                        new boolean[workers][jobs];
                    for (int bit = 0; bit < possibleEdges; bit++) {
                        if ((mask & (1 << bit)) != 0) {
                            int i = bit / jobs;
                            int j = bit % jobs;
                            eligible[i][j] = true;
                        }
                    }
                    verifyAgainstOracle(eligible, workers, jobs);
                    tested++;
                }
            }
        }
        return tested;
    }

    public static void main(String[] args) {
        boolean[][] eligible = {
            {true,  true,  false, false},
            {true,  false, false, false},
            {false, true,  true,  false},
            {false, false, true,  true}
        };
        Matching sample = maximumMatching(eligible, 4, 4);
        check(sample.size() == 4, "sample should be fully assigned");
        verifyMatching(eligible, 4, 4, sample);
        System.out.println(
            "Sample maximum assignments: " + sample.size());
        for (int i = 0; i < 4; i++) {
            System.out.println(
                "Worker " + i + " -> Job "
                + sample.jobForWorker()[i]);
        }

        boolean[][] limited = {
            {true, false},
            {true, false},
            {false, true}
        };
        Matching partial = maximumMatching(limited, 3, 2);
        check(partial.size() == 2, "limited graph should match two");
        verifyMatching(limited, 3, 2, partial);
        System.out.println(
            "Limited graph maximum assignments: " + partial.size());
        System.out.println(
            "All 3 workers assigned: " + (partial.size() == 3));

        boolean[][] empty = new boolean[0][0];
        check(maximumMatching(empty, 0, 0).size() == 0,
            "empty graph");
        boolean[][] noJobs = new boolean[3][0];
        check(maximumMatching(noJobs, 3, 0).size() == 0,
            "no available jobs");
        System.out.println("Empty graph matching size: 0");

        long exhaustive = exhaustiveGraphs();
        check(exhaustive == 689, "unexpected exhaustive graph count");
        System.out.println(
            "Exhaustive bipartite graphs (n,m<=3): "
            + exhaustive + " PASS");

        Random random = new Random(556L);
        for (int trial = 0; trial < 500; trial++) {
            int workers = random.nextInt(8);
            int jobs = random.nextInt(8);
            boolean[][] graph = new boolean[workers][jobs];
            for (int i = 0; i < workers; i++) {
                for (int j = 0; j < jobs; j++) {
                    graph[i][j] = random.nextInt(100) < 45;
                }
            }
            verifyAgainstOracle(graph, workers, jobs);
        }
        System.out.println("Random graphs vs brute force: 500 PASS");
        System.out.println("All assignment checks: PASS");
    }
}

## 15. Biên dịch và kết quả chương trình

Lưu mã trên thành `AssignmentFlowDemo.java`. Biên dịch bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AssignmentFlowDemo.java
java AssignmentFlowDemo
```

**Stdout xác định:**

```text
Sample maximum assignments: 4
Worker 0 -> Job 1
Worker 1 -> Job 0
Worker 2 -> Job 2
Worker 3 -> Job 3
Limited graph maximum assignments: 2
All 3 workers assigned: false
Empty graph matching size: 0
Exhaustive bipartite graphs (n,m<=3): 689 PASS
Random graphs vs brute force: 500 PASS
All assignment checks: PASS
```

### 15.1. Giải thích chương trình

**`Dinic`:** mỗi cạnh thuận lưu chỉ số cạnh ngược và residual capacity. Khi gửi flow, capacity thuận giảm và capacity ngược tăng. BFS tạo level graph; DFS gửi blocking flow theo level.

**`maximumMatching`:** dựng node source, worker, job và sink. Chỉ các ô `eligible[i][j]` true mới tạo cạnh. Capacity 1 ở cả ba lớp bảo đảm matching đơn vị.

**Trích cặp:** code lưu tham chiếu `Edge` của từng cạnh worker→job. Sau max flow, cạnh gốc capacity còn 0 là một assignment đang được dùng. Nó kiểm thêm không worker/job nào lặp và số cạnh trích ra bằng flow value.

**`bruteForce`:** với đồ thị nhỏ, thử hai lựa chọn cho mỗi worker: bỏ không ghép hoặc ghép với một job chưa dùng. Đây là oracle độc lập có độ phức tạp mũ, không dùng được cho graph lớn nhưng rất hữu ích để kiểm Dinic.

**Exhaustive:** xét mọi graph hai phía có n,m≤3. Tổng số graph là:

```text
sum(2^(n*m)) for n=0..3, m=0..3
= 4 + 15 + 85 + 585
= 689
```

**Random:** 500 graph với n,m từ 0..7, mỗi cạnh xuất hiện theo seed 556 và xác suất 45%. Mỗi kết quả max flow được so với brute force.

### 15.2. Giới hạn của bản demo

Code chỉ giải **maximum cardinality matching không trọng số**, mỗi worker/job tối đa một lần. Nó không tự giải min-cost assignment, lower-bound circulation, multi-skill team formation hay các ràng buộc liên kết nhiều cặp.

DFS trong Dinic là đệ quy; với mạng rất sâu, cần đánh giá stack hoặc dùng bản iterative. Brute force chỉ chạy trên đồ thị nhỏ; không dùng nó cho production. Đối với matching hai phía cực lớn, xem xét Hopcroft–Karp; đối với weighted assignment, dùng Hungarian/min-cost flow theo cấu trúc chi phí.

## 16. Những lỗi mô hình hóa và cài đặt thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Nối mọi worker với mọi job | Tạo lựa chọn không đủ điều kiện | Chỉ thêm cạnh hợp lệ |
| Nhầm worker và job cùng một phía | Matching có thể sai ngữ nghĩa | Chia hai tập rời nhau |
| Dùng greedy cạnh đầu tiên | Bỏ lỡ augmenting path | Dùng matching/max-flow |
| Không có cạnh residual ngược | Không đảo được quyết định cũ | Thêm reverse edge |
| Quên cập nhật capacity ngược | Flow sau không thể đổi matching | Cập nhật cả hai chiều |
| Dùng capacity vô hạn cho worker/job | Một node có thể được gán nhiều lần | Capacity theo hợp đồng |
| Chỉ đếm flow nhưng cần danh sách cặp | Không biết ai nhận việc nào | Giữ reference cạnh và trích matching |
| Đọc cả cạnh residual ngược như assignment | Xuất cặp giả | Chỉ xét cạnh gốc worker→job |
| Dùng perfect matching khi hai phía lệch size | Đặt yêu cầu không thể đạt | Dùng left-perfect nếu chỉ phủ L |
| Không kiểm flow==số worker | Tuyên bố phân công đủ sai | Kiểm số assignment thực tế |
| Đưa cạnh duplicate như thêm slot | Có thể hiểu sai capacity/ngữ nghĩa | Deduplicate eligibility hoặc mô hình slot thật |
| Nhầm set với multiset | Đếm sai bản sao | Xác định multiplicity |
| Dùng Dinic general bound cho mọi graph | Ước lượng hiệu năng sai | Phân biệt unit network và graph tổng quát |
| Dùng Dijkstra với cost âm trực tiếp | Đường ngắn nhất sai | Bellman-Ford/potential |
| Max flow khi mục tiêu là min cost | Tìm nhiều cặp nhưng chi phí không tối ưu | Min-cost max-flow/Hungarian |
| Biến score thành cost mà F không cố định | Có thể đổi ưu tiên số lượng/điểm | Chốt cardinality trước hoặc dùng objective kết hợp |
| Dùng capacity c khi cần exactly c | Chỉ bảo đảm at most c | Lower bound/circulation |
| Ép slot khi slot không tương đương | Mất điều kiện cục bộ | Tách node chỉ khi semantics đúng |
| Cố mô hình side constraints bằng flow thường | Thiếu điều kiện toàn cục | ILP/CP-SAT/constraint programming |
| Không xử lý graph rỗng | Lỗi node/array/loop | Kiểm n=0,m=0 |
| Không test một phía rỗng | Sai khởi tạo/điều kiện kết thúc | n=0 hoặc m=0 |
| Không test không có cạnh | Kết luận flow sai | Graph rời hoàn toàn |
| Không test một node degree lớn | Bỏ lỗi cạnh lặp/đếm | Star graph, all-to-one |
| DFS không kiểm trạng thái thăm | Đệ quy vô hạn | Visited/level graph đúng |
| BFS/DFS dùng node index sai | Truy cập ngoài mảng | Offset source/worker/job rõ ràng |
| Brute-force oracle dùng cùng flow | Không độc lập | Enumerate assignment trực tiếp |

## 17. Bài tập thực hành có đáp án

**Bài 1.** Matching là gì? *Đáp án:* tập cạnh không có hai cạnh chung đầu mút.

**Bài 2.** Maximum matching khác perfect matching thế nào? *Đáp án:* maximum tối đa số cặp; perfect phủ mọi đỉnh ở cả hai phía.

**Bài 3.** Có 5 worker, 8 job và flow=5 nghĩa gì? *Đáp án:* có left-perfect matching phủ cả 5 worker, không nhất thiết phủ 8 job.

**Bài 4.** Vì sao greedy chọn cạnh đầu tiên có thể sai? *Đáp án:* lựa chọn sớm có thể chặn một worker chỉ có ít lựa chọn; augmenting path cần đổi cặp cũ.

**Bài 5.** Augmenting path làm matching size đổi bao nhiêu? *Đáp án:* tăng đúng 1.

**Bài 6.** Định lý Berge phát biểu gì? *Đáp án:* matching maximum khi và chỉ khi không còn augmenting path.

**Bài 7.** Trong flow reduction, capacity s→worker bằng bao nhiêu cho matching đơn vị? *Đáp án:* 1.

**Bài 8.** Capacity job→sink? *Đáp án:* 1 trong matching đơn vị.

**Bài 9.** Một cạnh worker→job chỉ tạo khi nào? *Đáp án:* cặp đó hợp lệ theo đề.

**Bài 10.** Giá trị maximum flow bằng đại lượng nào? *Đáp án:* kích thước maximum matching.

**Bài 11.** Vì sao flow nguyên cho matching nguyên? *Đáp án:* integer capacities cho phép thuật toán max-flow duy trì integer flow; mỗi cạnh assignment có flow 0/1.

**Bài 12.** Hall condition? *Đáp án:* mọi X⊆L có |N(X)|≥|X| để có matching phủ L.

**Bài 13.** Ba worker chỉ có hai job chung có thể ghép hết không? *Đáp án:* không.

**Bài 14.** Residual reverse edge dùng làm gì? *Đáp án:* hoàn tác flow cũ để đổi matching.

**Bài 15.** Hopcroft–Karp có cận nào? *Đáp án:* O(E√V).

**Bài 16.** Kuhn DFS cơ bản thường có cận nào? *Đáp án:* O(|L|E) trong cách cài đặt phổ biến.

**Bài 17.** Dinic tổng quát có cận nào? *Đáp án:* O(V²E).

**Bài 18.** Với matching unit network, Dinic có cận tốt hơn nào? *Đáp án:* O(E√V).

**Bài 19.** Worker có thể làm tối đa 3 việc thì chỉnh gì? *Đáp án:* capacity source→worker bằng 3.

**Bài 20.** Job có 4 slot tương đương thì chỉnh gì? *Đáp án:* capacity job→sink bằng 4.

**Bài 21.** Capacity 4 có đảm bảo ít nhất 4 không? *Đáp án:* không, chỉ at most 4.

**Bài 22.** Exactly 4 cần thêm gì? *Đáp án:* yêu cầu flow/lower-bound đúng 4, có thể dùng circulation với lower bound.

**Bài 23.** Khi có cost trên mỗi cặp, cần thuật toán nào? *Đáp án:* min-cost max-flow hoặc Hungarian tùy cấu trúc.

**Bài 24.** Score càng cao càng tốt có thể chuyển thành cost thế nào nếu F cố định? *Đáp án:* cost=C−score với C hằng đủ lớn.

**Bài 25.** Dijkstra thường có dùng trực tiếp với cạnh cost âm? *Đáp án:* không; cần potential/Bellman-Ford hoặc biến đổi hợp lệ.

**Bài 26.** Hungarian thường phù hợp trường hợp nào? *Đáp án:* assignment trọng số dạng ma trận, mỗi hàng/cột tối đa một lần.

**Bài 27.** Hai slot có điều kiện khác nhau có nên gộp capacity? *Đáp án:* không nếu gộp làm mất eligibility; tách node slot.

**Bài 28.** Điều kiện “nếu nhận A thì không nhận B” luôn biểu diễn được bằng flow hai phía không? *Đáp án:* không; có thể cần ILP/CP-SAT.

**Bài 29.** Vì sao phải giữ reference cạnh worker-job? *Đáp án:* trích đúng cặp từ residual flow sau khi tối ưu.

**Bài 30.** Graph rỗng có matching size bao nhiêu? *Đáp án:* 0.

**Bài 31.** Một phía rỗng thì maximum matching size? *Đáp án:* 0.

**Bài 32.** Nếu maximum flow nhỏ hơn số worker bắt buộc gán? *Đáp án:* không tồn tại phân công đầy đủ theo các eligibility/capacity hiện có.

**Bài 33.** Một graph có 4 worker, 3 job có thể có perfect matching? *Đáp án:* không thể phủ cả hai phía vì số đỉnh lệch; có thể phủ toàn bộ 3 job hoặc một tập phía nhỏ hơn tùy định nghĩa.

**Bài 34.** Brute-force matching oracle phù hợp cỡ nào? *Đáp án:* graph nhỏ vì số trạng thái tăng theo 2^m hoặc tổ hợp assignment.

**Bài 35.** Vì sao test graph không cạnh? *Đáp án:* kiểm đúng case không có eligibility, flow phải bằng 0.

**Bài 36.** Nếu có duplicate eligibility record cho cùng cặp worker-job, có tự tăng capacity không? *Đáp án:* không; cùng một cặp là một cạnh logic, trừ khi đề mô hình các slot khác nhau riêng biệt.

## 18. Checklist giải bài phân công

1. Xác định chính xác hai tập L và R.
2. Tạo cạnh chỉ khi cặp đủ điều kiện.
3. Ghi rõ mỗi node được dùng tối đa/mỗi tối thiểu bao nhiêu lần.
4. Phân biệt maximum cardinality, left-perfect/perfect và weighted objective.
5. Chọn Kuhn, Hopcroft–Karp, Dinic, Hungarian hay min-cost flow theo cấu trúc.
6. Nếu dùng flow, vẽ source→L→R→sink và đặt capacity đúng.
7. Kiểm reverse edges và residual updates.
8. Dùng Hall/min-cut để hiểu bottleneck.
9. Trích cặp từ cạnh gốc, kiểm mỗi node không vượt capacity.
10. Nếu bắt buộc ghép mọi worker, kiểm flow đạt đủ yêu cầu.
11. Với capacity lower bound, dùng circulation transformation.
12. Với cost âm, xử lý shortest path/potential đúng.
13. Xác minh constraints toàn cục có thật sự biểu diễn được bằng flow.
14. Kiểm graph rỗng, một phía rỗng, không cạnh, một lựa chọn và nhiều lựa chọn.
15. So với brute force trên graph nhỏ và random có seed.
16. Đo số node/cạnh, memory, thời gian và worst-case graph shape.

**Kết luận:** bài toán phân công thường trở nên rõ ràng khi tách thành hai tập đối tượng và cạnh đủ điều kiện giữa chúng. **Bipartite matching** giải phân công một-một; **maximum flow** mở rộng sức chứa; **min-cost flow/Hungarian** xử lý chi phí và tối ưu điểm. Điều quan trọng nhất là giữ đúng semantics: số lượng cần ghép, capacity, lower bound, lựa chọn hợp lệ và những ràng buộc toàn cục. Chọn thuật toán sau khi mô hình hóa, rồi xác minh bằng augmenting-path reasoning, residual network và oracle độc lập.
