# Tìm kiếm chi phí đều và quan hệ với Dijkstra

**Tìm kiếm chi phí đều** (*Uniform-Cost Search*, UCS) là thuật toán tìm một **trạng thái đích có tổng chi phí đường đi nhỏ nhất** từ trạng thái bắt đầu. Trong bài toán tìm kiếm trạng thái, mỗi hành động thay đổi cấu hình hiện tại và có một chi phí. UCS không mở rộng theo số bước ít nhất như BFS, cũng không ưu tiên theo cảm giác “gần đích” như greedy best-first search: UCS luôn chọn trạng thái có **chi phí tích lũy từ đầu nhỏ nhất** trong hàng đợi ưu tiên.

Tên “uniform-cost” rất dễ gây hiểu nhầm. UCS **không đòi mọi hành động có cùng chi phí**. Chi phí có thể là 0, 1, 5, 100…; giả thiết cốt lõi là chúng **không âm**. Điều “đều” ở đây là **quy tắc dùng một thước đo chi phí tích lũy g** cho mọi trạng thái.

Bài học thuộc nhóm **Tìm kiếm trạng thái**, tập trung vào:

- Xây mô hình không gian trạng thái, hành động, chi phí, trạng thái bắt đầu và mục tiêu.
- Tìm kiếm theo `g(state)` bằng min-heap, relax và phục hồi đường đi.
- Dừng khi **lấy mục tiêu ra khỏi hàng đợi** ở nhãn tối ưu, không khi vừa sinh mục tiêu.
- Chứng minh UCS tối ưu và chỉ rõ quan hệ thuật toán với **Dijkstra**.
- Phân biệt UCS/Dijkstra với BFS, 0–1 BFS, A* có `h=0`, và greedy search.
- Xử lý trạng thái lặp, bản ghi stale, cạnh chi phí 0, mục tiêu không tới được, nhiều mục tiêu, không gian vô hạn và tràn số.
- Cài đặt **Java 17+ chạy độc lập**: UCS tổng quát trên trạng thái ẩn; Dijkstra tất cả đỉnh; BFS đối chứng; 400 đồ thị nhỏ kiểm thử ngẫu nhiên.

## 1. Mô hình bài toán và cách chuyển sang đồ thị

Một bài toán tìm kiếm trạng thái có:

| Thành phần | Ký hiệu | Ý nghĩa |
| --- | --- | --- |
| Trạng thái bắt đầu | `s` | Cấu hình xuất phát |
| Tập trạng thái | `S` | Mọi cấu hình hợp lệ |
| Bộ sinh hành động | `expand(u)` | Các bước chuyển từ u tới trạng thái mới |
| Chi phí một bước | `w(u,v)` | Giá phải trả khi chuyển u→v |
| Điều kiện mục tiêu | `goal(u)` | u có đáp ứng yêu cầu kết thúc không? |
| Đường giải | `π` | Chuỗi hành động/trạng thái từ s đến một mục tiêu |
| Tổng chi phí | `C(π)` | Tổng w trên tất cả các bước của π |

Cho một đường:

```text
π = (s = v0, v1, v2, ..., vk = g)

C(π) =
    w(v0,v1) + w(v1,v2) + ... + w(v(k-1),vk)
```

Nếu trạng thái bắt đầu đã là mục tiêu, đường rỗng có cost 0. Trong bài này, mọi w phải là **số nguyên không âm**; mã dùng kiểu long cho mỗi bước và tổng đường đi.

### 1.1. Trạng thái phải chứa đủ thông tin cho tương lai

Ví dụ bài đi trong mê cung có khóa:

```text
State = (row, col, keyMask)
```

Nếu chỉ lưu (row,col), hai lần đến cùng ô nhưng mang tập chìa khóa khác nhau bị gộp thành một trạng thái. Hành động tương lai của chúng có thể khác nhau: một cấu hình mở được cửa, cấu hình kia không. Khi ấy UCS trên state key thiếu thông tin có thể trả đáp án sai, dù cách dùng PriorityQueue hoàn toàn đúng.

Một trạng thái nên biểu diễn **đầy đủ những yếu tố ảnh hưởng tập bước đi và chi phí tương lai**. Ví dụ:

- Vị trí, hướng và năng lượng của robot.
- Cấu hình bàn cờ, số thao tác và các thuộc tính có tác động về sau.
- Đỉnh hiện tại và bitmask các vật phẩm đã nhặt.
- Trạng thái thời gian nếu đường đi phụ thuộc một chu kỳ.
- Một số nguyên x khi hành động là +1, ×2, trừ, đổi chữ số…

Trong Java, có thể dùng record bất biến như `record State(int row,int col,int mask) {}` làm key của HashMap/HashSet. Với dữ liệu kiểu mảng có thể thay đổi, cần cẩn thận vì equals/hashCode của array mặc định so tham chiếu, không so nội dung.

### 1.2. Đồ thị tường minh và không gian trạng thái ẩn

Nếu trạng thái là đỉnh 0..n−1 và các cung đã được liệt kê sẵn, ta có một **đồ thị tường minh** (*explicit graph*) và dễ dùng mảng dist[].

Nếu trạng thái sinh theo hành động, ta có thể **không biết trước toàn bộ đồ thị**. Thay vì dựng mọi cạnh, viết:

```text
expand(u) -> danh sách Move:
    (nextState, stepCost, actionName)
```

và chỉ gọi expand khi UCS thực sự mở rộng u. Phương pháp này tiết kiệm công khi chỉ một phần nhỏ không gian trạng thái liên quan đến đích.

UCS và Dijkstra đều có thể chạy trên đồ thị tường minh hoặc ẩn. Việc thường giới thiệu UCS với hàm sinh láng giềng, còn Dijkstra với adjacency list, là khác biệt **cách sử dụng và giao diện**, không phải giới hạn toán học bắt buộc.

## 2. UCS làm việc như thế nào?

Ký hiệu:

```text
best[v] = chi phí nhỏ nhất của một đường
          từ start tới v đã được phát hiện
```

Ban đầu:

```text
best[start] = 0
best[trạng thái khác] = chưa biết

PriorityQueue = {(start, g=0)}
settled = tập rỗng
```

Vòng lặp:

1. Lấy bản ghi `(u,g)` có g nhỏ nhất.
2. Nếu `g != best[u]`, đó là bản ghi lỗi thời (*stale*): bỏ qua.
3. Nếu u đã được chốt (*settled*), bỏ qua.
4. **Chốt u** tại g; với trọng số không âm, g là chi phí tối ưu từ start đến u.
5. Nếu `goal(u)` đúng, trả g và đường đi phục hồi theo parent.
6. Nếu chưa là đích, sinh mọi chuyển u→v với bước cost≥0.
7. Tính `candidate=g+cost`. Nếu v chưa có nhãn hoặc candidate nhỏ hơn best[v], cập nhật best[v], parent[v], action[v] và chèn bản ghi mới vào heap.

Khi heap hết mà vẫn chưa lấy được goal, trong **không gian trạng thái hữu hạn đã khám phá hết** không tồn tại mục tiêu tới được từ start.

### Giả mã

```text
UCS(start, goal, expand):
    best[start] = 0
    parent[start] = NONE
    PQ.push((start, 0))
    settled = empty set

    while PQ not empty:
        (u, g) = PQ.popMin()

        if g != best[u]:
            continue

        if u in settled:
            continue

        settled.add(u)

        if goal(u):
            return (g, reconstruct(parent, u))

        for move (v, w, action) in expand(u):
            require w >= 0
            candidate = g + w

            if v not in best OR candidate < best[v]:
                best[v] = candidate
                parent[v] = u
                parentAction[v] = action
                PQ.push((v, candidate))

    return NO_SOLUTION
```

**Bất biến:** Mọi best[v] đã lưu đều là giá của một đường **thực sự tồn tại** tới v. Mỗi khi một bản ghi tối ưu của u được pop từ min-heap dưới giả thiết cost không âm, nhãn ấy không thể được cải thiện bởi một đường đi sau này.

### 2.1. Vì sao không dừng khi vừa sinh ra đích?

Cho đồ thị:

```text
s -> goal      cost 9
s -> a         cost 1
a -> b         cost 1
b -> goal      cost 1
```

Nếu dừng ngay lúc mở rộng s và sinh ra goal, thuật toán trả cost9. Nhưng đường s→a→b→goal có cost3.

UCS cho goal(9) và a(1) vào heap. Vì 1 nhỏ hơn 9, lấy a trước; tiếp theo b(2); rồi goal(3). **Chỉ khi goal(3) được pop**, ta có thể kết luận đường đó tối ưu. Bản ghi goal(9) là stale và không được dùng.

Quy tắc trọng yếu: **goal khi được phát hiện không chắc tối ưu; goal khi được lấy ra ở nhãn tốt nhất mới có chứng minh tối ưu**.

### 2.2. Phát hiện và chốt là hai trạng thái khác nhau

- `best[v]` tồn tại nghĩa là đã **tìm thấy một đường** tới v.
- `settled[v]=true` nghĩa là đã **xác nhận chi phí tối ưu** tới v nhờ pop ở g nhỏ nhất.

Trong BFS đơn vị trọng số, thường đánh dấu visited khi enqueue là an toàn vì BFS tìm số cạnh ít nhất theo từng lớp. Trong UCS trọng số không đều, đánh dấu “xong” ngay khi enqueue đầu tiên sẽ chặn các đường rẻ hơn phát hiện sau; đây là lỗi phổ biến.

## 3. Ví dụ UCS có trọng số không đều

Đồ thị sáu đỉnh, nguồn 0, đích 4; đỉnh 5 không tới được:

```text
0 -> 1 : 2
0 -> 2 : 5
1 -> 2 : 1
1 -> 3 : 5
2 -> 3 : 1
2 -> 4 : 6
3 -> 4 : 1
0 -> 4 : 20
```

Một số đường từ 0 đến 4:

```text
0 -> 4                  20
0 -> 2 -> 3 -> 4         7
0 -> 1 -> 3 -> 4         8
0 -> 1 -> 2 -> 4         9
0 -> 1 -> 2 -> 3 -> 4    5    <-- tối ưu
```

### Trình tự pop

| Lượt | Pop | g | Relax quan trọng |
| ---: | ---: | ---: | --- |
| 1 | 0 | 0 | best[1]=2,best[2]=5,best[4]=20 |
| 2 | 1 | 2 | best[2] giảm xuống3,best[3]=7 |
| 3 | 2 | 3 | best[3] giảm xuống4,best[4] giảm xuống9 |
| 4 | 3 | 4 | best[4] giảm xuống5 |
| 5 | 4 | 5 | **Lấy đích tối ưu, dừng** |

Các bản ghi cũ như (2,5), (3,7), (4,20) có thể còn trong heap; chúng không làm đáp án sai nếu kiểm tra stale khi pop.

Nếu goal predicate cho phép **đỉnh 3 hoặc 4**, ta sẽ dừng ở 3 với chi phí 4, không nhất thiết đến 4. Nếu cần tất cả khoảng cách từ nguồn, Dijkstra tiếp tục đến khi heap cạn, trả:

```text
[0, 2, 3, 4, 5, INF]
```

### Quy tắc phá hòa

Khi nhiều trạng thái có cùng g, mọi lựa chọn pop ở g thấp nhất đều giữ bảo đảm **giá trị chi phí tối ưu**. Tuy nhiên, thứ tự này có thể ảnh hưởng số trạng thái mở rộng và đường đi cụ thể khi nhiều đường hòa.

Mã Java dùng số `sequence` tăng theo lần chèn làm tiêu chí phụ: g nhỏ hơn trước, bằng g thì bản ghi được chèn trước. Cách này tái lập stdout với cùng thứ tự sinh láng giềng. Nó **không tự chứng minh** đường đi trả về là nhỏ nhất theo thứ tự từ điển; mục tiêu thứ hai đó cần thiết kế bổ sung.

## 4. UCS và Dijkstra: một lõi thuật toán

Hai thuật toán đều dùng công thức **relax**:

```text
candidate = dist[u] + weight(u,v)

if candidate < dist[v]:
    dist[v] = candidate
```

Đồng thời đều ưu tiên trạng thái/đỉnh có **nhãn tổng chi phí từ nguồn nhỏ nhất**. Dưới điều kiện mọi cạnh không âm, khi một đỉnh u được pop ở nhãn nhỏ nhất còn đúng, nhãn ấy đã bằng khoảng cách ngắn nhất thật `d(s,u)`.

| Khía cạnh | UCS thường dùng | Dijkstra thường dùng |
| --- | --- | --- |
| Dữ liệu | Trạng thái tổng quát và hàm expand | Đỉnh đánh số, danh sách kề |
| Khóa hàng đợi | `g(state)` | `dist[vertex]` |
| Phép relax | `g+w` nếu tốt hơn | `dist+w` nếu tốt hơn |
| Trọng số | Không âm | Không âm |
| Điều kiện dừng | Goal predicate sau pop | Hết heap hoặc một đích cụ thể đã pop |
| Kết quả | Đích tối ưu và đường hành động | Thường toàn bộ dist hoặc đường tới đích |
| Nền tảng đúng | Định lý chốt đỉnh | Cùng định lý |

**Kết luận:** Dijkstra dừng sớm khi pop một đích cố định chính là UCS đối với một đích đó. Một UCS chạy đến hết heap mà lưu đủ nhãn đạt các khoảng cách như Dijkstra. Hai tên gọi làm nổi bật **bài toán tìm đích trong không gian trạng thái** và **bài toán đường đi ngắn nhất một nguồn**, không phải hai tiêu chí tối ưu khác nhau.

### 4.1. Chứng minh tính đúng của nhãn khi pop

Giả sử u là đỉnh đầu tiên bị chốt với best[u] lớn hơn khoảng cách tối ưu d(s,u). Lấy một đường tối ưu từ s đến u. Trên đường ấy, chọn x là trạng thái đầu tiên **chưa được chốt** ngay trước khi u được lấy ra. Trạng thái đứng trước x trên đường (nếu tồn tại) đã được chốt đúng vì u là trường hợp sai đầu tiên.

Khi mở rộng trạng thái đứng trước x, thuật toán relax đến x nên:

```text
best[x] <= d(s,x)
```

Mặt khác best[x] luôn là giá của một đường thật, nên best[x]≥d(s,x). Do đó best[x]=d(s,x).

Vì mọi trọng số sau x tới u đều không âm:

```text
d(s,x) <= d(s,u) < best[u]
```

Heap phải có một bản ghi còn hợp lệ của x với khóa **nhỏ hơn best[u]**. Điều này trái với việc u được chọn popMin để chốt. Suy ra best[u]=d(s,u).

Nếu UCS lấy mục tiêu đầu tiên g ra, d(s,g) đã tối ưu. Nếu tồn tại một đích khác có d nhỏ hơn, nó phải được lấy ra trước; mâu thuẫn. Vậy UCS trả **mục tiêu có tổng chi phí nhỏ nhất**.

**Chứng minh dựa vào không âm.** Có cạnh âm thì bất đẳng thức d(s,x)≤d(s,u) có thể sai.

### 4.2. Trọng số âm làm hỏng UCS như thế nào?

Phản ví dụ:

```text
s -> goal   cost  2
s -> a      cost  5
a -> goal   cost -10
```

UCS chưa kiểm tra cạnh âm sẽ pop goal(2) trước a(5) và dừng, dù đường s→a→goal có tổng `5−10=−5`. Đây là lỗi **giả thiết toán học**, không phải thiếu một dòng heap.

Trên đồ thị hữu hạn có trọng số âm, cần thuật toán phù hợp như Bellman–Ford hoặc biến đổi trọng số được chứng minh đúng. Nếu có chu trình âm tới được nằm trên đường tới goal và cho phép lặp, có thể không tồn tại một giá trị tối ưu hữu hạn.

Trong mã mẫu, đồ thị **tường minh** được xác thực toàn bộ chi phí không âm trước khi chạy. Với trạng thái **ngầm**, các bước chưa được sinh không thể kiểm tra trước, nên bản thân **bộ sinh bước chuyển** phải tuân thủ hợp đồng không âm trên toàn không gian liên quan.

## 5. Các thuật toán liên quan

| Thuật toán | Ưu tiên | Miền chi phí | Khi phù hợp |
| --- | --- | --- | --- |
| **BFS** | FIFO theo **số cạnh** | Mỗi cạnh có cùng cost dương nếu tối ưu tổng cost | Ít bước nhất |
| **0–1 BFS** | Deque: cạnh0 vào đầu, cạnh1 vào cuối | Chỉ 0 hoặc 1 | Shortest path O(V+E) |
| **UCS** | Min-heap theo tổng g | Không âm | Một mục tiêu hoặc tập mục tiêu |
| **Dijkstra** | Min-heap theo dist | Không âm | Một nguồn đến nhiều đỉnh |
| **Greedy best-first** | Heuristic h | Không tự bảo đảm tối ưu g | Tìm hướng có vẻ hứa hẹn |
| **A\*** | `f=g+h` | Giả thiết heuristic/chi phí phù hợp | Tận dụng ước lượng tới đích |
| **Bellman–Ford** | Relax theo lượt | Cho phép âm | Đường đi ngắn nhất có cạnh âm |

### 5.1. Khi BFS và UCS tương đương

Nếu mỗi cạnh có cùng chi phí dương c, đường k cạnh có tổng cost k×c. Tối ưu số cạnh tương đương tối ưu tổng chi phí. BFS không cần heap, chỉ O(V+E).

Nếu các cạnh không đều, sự tương đương mất đi. Ví dụ:

```text
0 -> 3  cost 9          // chỉ một cạnh
0 -> 1  cost 1
1 -> 2  cost 1
2 -> 3  cost 1          // ba cạnh
```

BFS chọn đường [0,3], ít cạnh nhất nhưng cost9. UCS chọn [0,1,2,3] với cost3. Bài hỏi **tổng chi phí thấp nhất** thì UCS đúng.

Nếu mọi cạnh có cùng cost0, tất cả các đường tới được đều có cost0; BFS vẫn tối thiểu hóa số cạnh như một tiêu chí phụ, nhưng không nhất thiết lấy cùng đường với UCS.

### 5.2. 0–1 BFS

Nếu mọi trọng số chỉ là **0 hoặc 1**, có thể dùng ArrayDeque:

```text
Nếu relax qua cạnh trọng số 0:
    pushFront(next)

Nếu relax qua cạnh trọng số 1:
    pushBack(next)
```

Kèm dist và xử lý bản ghi cũ/đã chốt đúng, 0–1 BFS là lựa chọn O(V+E). UCS vẫn chạy đúng trên trọng số0/1 nhưng cần heap. **Không** áp dụng quy tắc deque cho cạnh cost2 trở lên nếu chưa có biến đổi phù hợp.

### 5.3. A* và UCS

A* ưu tiên `f(u)=g(u)+h(u)`. Nếu `h(u)=0` mọi nơi, f=g: A* trở thành UCS về khóa ưu tiên. Tie-break và cách quản lý closed set có thể khác, nhưng quy tắc chi phí cốt lõi giống nhau.

Nếu h khác0, muốn bảo đảm tối ưu cần những giả thiết đúng về **admissibility/consistency**, dừng và khả năng mở lại trạng thái nếu heuristic không consistent. Một heuristic tùy ý không có quyền kế thừa tự động chứng minh tối ưu của UCS.

Greedy best-first chỉ nhìn h, có thể mở rộng trạng thái trông gần goal nhưng đường đi đến nó quá đắt. UCS nhìn g, tức chi phí đã thực trả.

## 6. Trạng thái lặp, heap stale và tính ổn định

Một trạng thái có thể được phát hiện qua nhiều đường:

```text
0 -> 1  cost 10
0 -> 2  cost  1
2 -> 1  cost  1
1 -> 3  cost  0
```

Sau khi mở rộng0, best[1]=10. Khi mở rộng2, best[1] giảm xuống2. PriorityQueue có thể chứa đồng thời:

```text
(1, 10)  // bản ghi cũ
(1,  2)  // bản ghi mới
```

Không sửa trực tiếp đối tượng (1,10) đã nằm trong Java PriorityQueue: heap **không tự xây lại** khi key của đối tượng đổi. Thay vào đó, chèn bản ghi mới, và khi pop kiểm tra:

```java
Long recorded = best.get(item.state());
if (recorded == null || item.g() != recorded) {
    continue;
}
```

Kèm Set `settled`, mỗi trạng thái chỉ được mở rộng tối đa một lần trên đồ thị hữu hạn đúng giả thiết.

### 6.1. Chỉ cập nhật khi tốt hơn nghiêm ngặt

Điều kiện:

```text
candidate < best[v]
```

giữ parent và heap ổn định khi có nhiều đường **bằng chi phí**. Nếu đổi thành `candidate<=best[v]` mà không có chiến lược chặt chẽ, chu trình chi phí0 có thể dẫn tới thay parent và enqueue trùng vô hạn trong bản cài đặt thiếu kiểm soát.

Khi nhiều đường cùng tối ưu, UCS có thể trả một đường bất kỳ trong số chúng. Nếu yêu cầu **số đường tối ưu** hoặc **đường từ điển nhỏ nhất**, đó là phần mở rộng riêng, không phải kết quả tự động của một comparator g.

### 6.2. So sánh g an toàn

Không so bằng:

```java
(a, b) -> (int) (a.g() - b.g())
```

vì phép trừ có thể tràn hoặc ép int làm mất bit. Dùng:

```java
int c = Long.compare(a.g(), b.g());
```

Khi bằng chi phí, mã dùng sequence để ưu tiên bản ghi chèn trước; cần có thứ tự sinh move xác định nếu muốn stdout xác định.

### 6.3. State key ổn định

Với HashMap/HashSet, hai trạng thái logic bằng nhau phải có equals/hashCode giống nhau. Nếu object dùng làm key bị thay đổi sau khi chèn, cấu trúc có thể không tìm lại được nó. Nếu dùng array trong state, phải bọc bằng cấu trúc so nội dung hoặc mã hóa state, không mặc nhiên dựa vào array.equals.

## 7. Điều kiện kết thúc trong không gian hữu hạn và vô hạn

**Trên đồ thị hữu hạn:** Nếu số trạng thái tới được hữu hạn, mỗi trạng thái sinh hữu hạn bước chuyển, các cost không âm, và dùng strict improvement + settled set, UCS xử lý hữu hạn lần. Chu trình cost0 không làm lặp vô tận vì bản ghi cùng chi phí không cải thiện best.

**Trên không gian vô hạn:** Trọng số không âm **chưa đủ** để bảo đảm tìm được goal. Giả sử từ số nguyên x có hành động x→x+1 cost0, sinh vô hạn trạng thái có g=0, đồng thời tồn tại một goal có g=1. UCS có thể liên tục mở rộng các trạng thái g=0 và **không bao giờ lấy goal(1)**.

Một điều kiện đủ quen thuộc:

- Mỗi trạng thái có **số hành động hữu hạn**;
- Có ε>0 sao cho mọi cost của một bước **ít nhất ε**;
- Có một goal với tổng chi phí tối ưu hữu hạn C*.

Vì mọi đường có cost≤C* có không quá C*/ε bước, và branching hữu hạn, số nút có thể nằm dưới ngưỡng chi phí ấy là hữu hạn. UCS sẽ lấy ra goal tối ưu sau hữu hạn lần mở rộng nếu các thao tác khác cũng kết thúc.

**Không có mục tiêu:** Với đồ thị hữu hạn, heap hết và trả NO_SOLUTION. Với không gian vô hạn, có thể không kết thúc. Dừng vì giới hạn thời gian/bộ nhớ/chặn số trạng thái chỉ có nghĩa “chưa tìm được trong giới hạn”, không chứng minh vô nghiệm.

**Có cạnh chi phí âm:** Không chỉ ảnh hưởng kết thúc mà còn phá chứng minh chốt đỉnh. Không được gộp hai vấn đề này thành một.

## 8. An toàn số: INF và overflow

Một đường thật có thể có chi phí đúng bằng `Long.MAX_VALUE`. Nếu dùng nó làm sentinel INF mà không có giới hạn đầu vào, ta không phân biệt được “không tới được” với “tới được, chi phí bằng Long.MAX_VALUE”.

Bản UCS dùng Map:

```java
Map<State, Long> best = new HashMap<>();
```

Nghĩa là:

- **Chưa có key**: chưa tìm được đường tới state.
- **Key tồn tại, value=0**: có đường chi phí0.
- **Key tồn tại, value=Long.MAX_VALUE**: có đường thật chi phí đúng bằng max.

Bản Dijkstra trên mảng dùng `boolean[] reached` riêng với `long[] dist`.

Phép cộng `g+w` có thể vượt long. Mã dùng:

```java
long candidate = Math.addExact(g, w);
```

Nếu vượt miền, Math.addExact ném ArithmeticException thay vì tạo số âm giả. Đó là **chính sách fail-fast**, không phải bằng chứng không có đường. Muốn hỗ trợ tổng nguyên lớn hơn long, dùng BigInteger hoặc mô hình có chứng minh cận.

Ngoài g+w, phải kiểm soát cả các phép tính trong bộ sinh trạng thái. Ví dụ khi nhân x×2, nếu x có thể lớn gần giới hạn int, kiểm tra x≤limit/2 trước khi nhân (nếu miền không âm) hoặc dùng Math.multiplyExact; Math.addExact chỉ bảo vệ **chi phí**, không bảo vệ tự động việc tạo state.

## 9. Ví dụ trạng thái ngầm: biến đổi số

Trạng thái là số x trong [1,10]. Bắt đầu tại x=1, goal là x=10. Có hai phép:

```text
x -> x+1 : cost 3, nếu x+1<=10
x -> 2*x : cost 1, nếu 2*x<=10
```

Từ x=1, hai hành động đều cho next=2 nhưng chi phí khác nhau:

```text
Move(next=2, cost=3, action="+1")
Move(next=2, cost=1, action="*2")
```

UCS phải giữ phương án tới2 với g thấp hơn. Lời giải tối ưu:

```text
1 --*2/1--> 2 --*2/1--> 4
  --+1/3--> 5 --*2/1--> 10

states  = [1,2,4,5,10]
actions = [*2,*2,+1,*2]
cost    = 1+1+3+1 = 6
```

Đây là ví dụ cho thấy UCS **không nhất thiết phải dựng trước đồ thị**: chỉ cần hàm nhận x và trả danh sách Move hợp lệ theo điều kiện trạng thái.

## 10. Chương trình Java 17+ hoàn chỉnh

Mã **UniformCostSearchDemo.java** chứa:

- UCS tổng quát `ucs(start,isGoal,expand)` với kiểu trạng thái S tùy ý, Map best, Set settled và PriorityQueue theo tổng g.
- Kết quả `Solution<S>` gồm goal, cost, danh sách trạng thái, hành động và số trạng thái được mở rộng.
- Dijkstra trên đồ thị id đỉnh, tính khoảng cách đến **mọi đỉnh**, dùng mảng reached[] để tránh sentinel INF.
- BFS tìm đường **ít cạnh nhất** để so sánh với UCS trên một đồ thị chi phí không đều.
- Các ca kiểm thử: nhiều mục tiêu, unreachable, start=goal, stale-entry, cạnh0 và self-loop0, đường cost đúng Long.MAX_VALUE, overflow, cạnh âm bị từ chối.
- 400 đồ thị nhỏ ngẫu nhiên có cạnh song song, self-loop, cost0, so UCS và Dijkstra cả bài **một mục tiêu** và **hai mục tiêu**.

Tất cả phép chuyển trong UCS được yêu cầu cost≥0. Với đồ thị tường minh, hàm adjacency xác thực toàn bộ cạnh trước khi chạy. Với hàm sinh move ngầm, bản cài đặt chỉ kiểm tra **những move đã được gọi expand sinh ra**; hợp đồng không có cạnh âm trên toàn mô hình vẫn thuộc trách nhiệm người định nghĩa bài toán.

### 10.1. Mã Java

```java
import java.util.*;
import java.util.function.*;

public class UniformCostSearchDemo {
    record Edge(int from, int to, long weight) {}
    record Move<S>(S next, long cost, String action) {}
    record QueueItem<S>(S state, long g, long sequence) {}
    record Solution<S>(S goal, long cost, List<S> states,
                       List<String> actions, int expanded) {}
    record Distances(boolean[] reached, long[] cost) {}
    record IntItem(int vertex, long distance) {}

    static <S> Optional<Solution<S>> ucs(
            S start, Predicate<S> isGoal,
            Function<S, ? extends Iterable<Move<S>>> expand) {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(isGoal, "isGoal");
        Objects.requireNonNull(expand, "expand");

        Map<S, Long> best = new HashMap<>();
        Map<S, S> parent = new HashMap<>();
        Map<S, String> action = new HashMap<>();
        Set<S> settled = new HashSet<>();

        PriorityQueue<QueueItem<S>> pq =
                new PriorityQueue<>((a, b) -> {
                    int c = Long.compare(a.g(), b.g());
                    return c != 0 ? c
                            : Long.compare(a.sequence(), b.sequence());
                });

        long sequence = 0;
        int expanded = 0;
        best.put(start, 0L);
        pq.add(new QueueItem<>(start, 0L, sequence));

        while (!pq.isEmpty()) {
            QueueItem<S> item = pq.remove();
            S u = item.state();
            Long recorded = best.get(u);

            if (recorded == null
                    || item.g() != recorded.longValue()
                    || !settled.add(u)) {
                continue;
            }

            expanded++;
            // Chot dich KHI LAY RA, khong phai khi sinh ra.
            if (isGoal.test(u)) {
                List<S> states = new ArrayList<>();
                List<String> actions = new ArrayList<>();
                S at = u;

                while (!at.equals(start)) {
                    states.add(at);
                    String step = action.get(at);
                    S p = parent.get(at);
                    if (p == null || step == null) {
                        throw new AssertionError("broken parent chain");
                    }
                    actions.add(step);
                    at = p;
                }
                states.add(start);
                Collections.reverse(states);
                Collections.reverse(actions);

                return Optional.of(new Solution<>(
                        u, item.g(), List.copyOf(states),
                        List.copyOf(actions), expanded));
            }

            Iterable<Move<S>> moves =
                    Objects.requireNonNull(
                            expand.apply(u), "neighbors");
            for (Move<S> move : moves) {
                Objects.requireNonNull(move, "move");
                S v = Objects.requireNonNull(
                        move.next(), "next state");
                Objects.requireNonNull(
                        move.action(), "action");

                if (move.cost() < 0) {
                    throw new IllegalArgumentException(
                            "edge cost must be nonnegative");
                }

                long candidate = Math.addExact(
                        item.g(), move.cost());
                Long old = best.get(v);
                if (old == null || candidate < old) {
                    best.put(v, candidate);
                    parent.put(v, u);
                    action.put(v, move.action());
                    sequence = Math.addExact(sequence, 1L);
                    pq.add(new QueueItem<>(
                            v, candidate, sequence));
                }
            }
        }
        return Optional.empty();
    }

    static List<List<Move<Integer>>> adjacency(
            int n, List<Edge> edges) {
        if (n < 1) {
            throw new IllegalArgumentException(
                    "n must be positive");
        }
        Objects.requireNonNull(edges, "edges");
        List<List<Move<Integer>>> adj = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            adj.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }
            if (e.weight() < 0) {
                throw new IllegalArgumentException(
                        "edge cost must be nonnegative");
            }
            adj.get(e.from()).add(new Move<>(
                    e.to(), e.weight(),
                    e.from() + "->" + e.to()));
        }
        return adj;
    }

    static Distances dijkstraAll(
            int n, List<Edge> edges, int source) {
        List<List<Move<Integer>>> adj = adjacency(n, edges);
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                    "source out of range");
        }
        boolean[] reached = new boolean[n];
        boolean[] settled = new boolean[n];
        long[] dist = new long[n];

        PriorityQueue<IntItem> pq =
                new PriorityQueue<>((a, b) -> {
                    int c = Long.compare(
                            a.distance(), b.distance());
                    return c != 0 ? c
                            : Integer.compare(
                                    a.vertex(), b.vertex());
                });

        reached[source] = true;
        dist[source] = 0;
        pq.add(new IntItem(source, 0));

        while (!pq.isEmpty()) {
            IntItem item = pq.remove();
            int u = item.vertex();
            if (!reached[u]
                    || item.distance() != dist[u]
                    || settled[u]) {
                continue;
            }
            settled[u] = true;
            for (Move<Integer> move : adj.get(u)) {
                int v = move.next();
                long candidate = Math.addExact(
                        dist[u], move.cost());
                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    pq.add(new IntItem(v, candidate));
                }
            }
        }
        return new Distances(reached, dist);
    }

    static String format(Distances result) {
        StringJoiner out = new StringJoiner(", ", "[", "]");
        for (int v = 0; v < result.cost().length; v++) {
            out.add(result.reached()[v]
                    ? Long.toString(result.cost()[v])
                    : "INF");
        }
        return out.toString();
    }

    // BFS chi toi uu SO CANH, khong toi uu tong cost.
    static List<Integer> bfsFewestEdges(
            int n, List<Edge> edges,
            int source, int target) {
        List<List<Move<Integer>>> adj = adjacency(n, edges);
        if (source < 0 || source >= n
                || target < 0 || target >= n) {
            throw new IllegalArgumentException(
                    "source or target out of range");
        }
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        boolean[] seen = new boolean[n];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        seen[source] = true;
        q.addLast(source);

        while (!q.isEmpty()) {
            int u = q.removeFirst();
            for (Move<Integer> move : adj.get(u)) {
                int v = move.next();
                if (!seen[v]) {
                    seen[v] = true;
                    parent[v] = u;
                    q.addLast(v);
                }
            }
        }

        if (!seen[target]) {
            return List.of();
        }
        List<Integer> path = new ArrayList<>();
        for (int v = target; v != -1; v = parent[v]) {
            path.add(v);
        }
        Collections.reverse(path);
        return path;
    }

    static void randomizedCrossCheck() {
        Random rng = new Random(20261110L);

        for (int trial = 0; trial < 400; trial++) {
            int n = 1 + rng.nextInt(11);
            int m = rng.nextInt(n * n + 1);
            List<Edge> edges = new ArrayList<>();
            for (int i = 0; i < m; i++) {
                edges.add(new Edge(
                        rng.nextInt(n),
                        rng.nextInt(n),
                        rng.nextInt(9)));
            }

            int source = rng.nextInt(n);
            int target = rng.nextInt(n);
            int otherGoal = rng.nextInt(n);
            List<List<Move<Integer>>> adj =
                    adjacency(n, edges);
            Distances all = dijkstraAll(n, edges, source);

            Optional<Solution<Integer>> one =
                    ucs(source, v -> v == target, adj::get);
            if (one.isPresent() != all.reached()[target]) {
                throw new AssertionError(
                        "reachability mismatch trial " + trial);
            }
            if (one.isPresent()
                    && one.get().cost() != all.cost()[target]) {
                throw new AssertionError(
                        "cost mismatch trial " + trial);
            }

            Optional<Solution<Integer>> any = ucs(
                    source,
                    v -> v == target || v == otherGoal,
                    adj::get);
            boolean reachable = false;
            long minimum = 0;
            for (int g : new int[]{target, otherGoal}) {
                if (all.reached()[g]
                        && (!reachable
                            || all.cost()[g] < minimum)) {
                    reachable = true;
                    minimum = all.cost()[g];
                }
            }

            if (any.isPresent() != reachable
                    || (any.isPresent()
                        && any.get().cost() != minimum)) {
                throw new AssertionError(
                        "multi-goal mismatch trial " + trial);
            }
        }
        System.out.println(
                "Random cross-check: PASS (400 graphs)");
    }

    public static void main(String[] args) {
        List<Edge> weighted = List.of(
                new Edge(0, 1, 2),
                new Edge(0, 2, 5),
                new Edge(1, 2, 1),
                new Edge(1, 3, 5),
                new Edge(2, 3, 1),
                new Edge(2, 4, 6),
                new Edge(3, 4, 1),
                new Edge(0, 4, 20));

        List<List<Move<Integer>>> graph =
                adjacency(6, weighted);

        Solution<Integer> to4 = ucs(
                0, v -> v == 4, graph::get).orElseThrow();
        System.out.println(
                "Weighted goal 4: cost=" + to4.cost()
                + " path=" + to4.states()
                + " actions=" + to4.actions());

        Solution<Integer> any = ucs(
                0, v -> v == 3 || v == 4,
                graph::get).orElseThrow();
        System.out.println(
                "Weighted goals {3,4}: goal=" + any.goal()
                + " cost=" + any.cost()
                + " path=" + any.states());

        System.out.println(
                "Dijkstra from 0: "
                + format(dijkstraAll(6, weighted, 0)));

        System.out.println("Unreachable goal 5: "
                + (ucs(0, v -> v == 5, graph::get)
                        .isPresent() ? "FOUND" : "NONE"));

        Solution<Integer> startGoal = ucs(
                0, v -> v == 0, graph::get).orElseThrow();
        System.out.println(
                "Start is goal: cost=" + startGoal.cost()
                + " path=" + startGoal.states());

        List<Edge> stale = List.of(
                new Edge(0, 1, 10),
                new Edge(0, 2, 1),
                new Edge(2, 1, 1),
                new Edge(1, 3, 0),
                new Edge(2, 3, 9));
        Solution<Integer> fixed = ucs(
                0, v -> v == 3,
                adjacency(4, stale)::get).orElseThrow();
        System.out.println(
                "Stale entry: cost=" + fixed.cost()
                + " path=" + fixed.states());

        List<Edge> zero = List.of(
                new Edge(0, 1, 0),
                new Edge(1, 2, 0),
                new Edge(0, 2, 5),
                new Edge(2, 3, 1),
                new Edge(0, 3, 8),
                new Edge(1, 1, 0));
        Solution<Integer> zeroSol = ucs(
                0, v -> v == 3,
                adjacency(4, zero)::get).orElseThrow();
        System.out.println(
                "Zero-cost edges: cost=" + zeroSol.cost()
                + " path=" + zeroSol.states());

        List<Edge> bfsTrap = List.of(
                new Edge(0, 3, 9),
                new Edge(0, 1, 1),
                new Edge(1, 2, 1),
                new Edge(2, 3, 1));
        System.out.println(
                "BFS fewest edges: "
                + bfsFewestEdges(4, bfsTrap, 0, 3)
                + " (one edge, cost 9)");
        Solution<Integer> weightedBest = ucs(
                0, v -> v == 3,
                adjacency(4, bfsTrap)::get).orElseThrow();
        System.out.println(
                "UCS cheapest route: cost="
                + weightedBest.cost()
                + " path=" + weightedBest.states());

        Function<Integer, List<Move<Integer>>> puzzle =
                x -> {
                    List<Move<Integer>> moves =
                            new ArrayList<>();
                    if (x + 1 <= 10) {
                        moves.add(new Move<>(
                                x + 1, 3, "+1"));
                    }
                    if (x * 2 <= 10) {
                        moves.add(new Move<>(
                                x * 2, 1, "*2"));
                    }
                    return moves;
                };
        Solution<Integer> puzzleSol = ucs(
                1, v -> v == 10, puzzle).orElseThrow();
        System.out.println(
                "Implicit puzzle: cost=" + puzzleSol.cost()
                + " states=" + puzzleSol.states()
                + " actions=" + puzzleSol.actions());

        Solution<Integer> maximum = ucs(
                0, v -> v == 2,
                adjacency(3, List.of(
                        new Edge(0, 1, Long.MAX_VALUE),
                        new Edge(1, 2, 0)))::get)
                .orElseThrow();
        System.out.println(
                "Reachable Long.MAX_VALUE: " + maximum.cost());

        try {
            ucs(0, v -> v == 2,
                    adjacency(3, List.of(
                            new Edge(0, 1, Long.MAX_VALUE),
                            new Edge(1, 2, 1)))::get);
        } catch (ArithmeticException ex) {
            System.out.println(
                    "Overflow detected: " + ex.getMessage());
        }

        try {
            adjacency(3, List.of(
                    new Edge(0, 1, 2),
                    new Edge(0, 2, 5),
                    new Edge(2, 1, -10)));
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Negative edge rejected: "
                    + ex.getMessage());
        }

        randomizedCrossCheck();
    }
}
```

### 10.2. Chạy chương trình

```bash
javac UniformCostSearchDemo.java
java UniformCostSearchDemo
```

**Stdout chính xác:**

```text
Weighted goal 4: cost=5 path=[0, 1, 2, 3, 4] actions=[0->1, 1->2, 2->3, 3->4]
Weighted goals {3,4}: goal=3 cost=4 path=[0, 1, 2, 3]
Dijkstra from 0: [0, 2, 3, 4, 5, INF]
Unreachable goal 5: NONE
Start is goal: cost=0 path=[0]
Stale entry: cost=2 path=[0, 2, 1, 3]
Zero-cost edges: cost=1 path=[0, 1, 2, 3]
BFS fewest edges: [0, 3] (one edge, cost 9)
UCS cheapest route: cost=3 path=[0, 1, 2, 3]
Implicit puzzle: cost=6 states=[1, 2, 4, 5, 10] actions=[*2, *2, +1, *2]
Reachable Long.MAX_VALUE: 9223372036854775807
Overflow detected: long overflow
Negative edge rejected: edge cost must be nonnegative
Random cross-check: PASS (400 graphs)
```

### 10.3. Đọc output theo từng trường hợp

- **Weighted goal 4:** Đường 0→1→2→3→4 có tổng5, rẻ hơn cạnh trực tiếp 0→4 cost20.
- **Weighted goals {3,4}:** Mục tiêu3 được pop ở cost4, nên dừng trước mục tiêu4 cost5.
- **Dijkstra from0:** Trả khoảng cách tới mọi đỉnh, trong đó đỉnh5 không tới được và được in INF.
- **Unreachable:** Optional.empty, không báo cost0.
- **Start is goal:** Đường [0], cost0, không có hành động.
- **Stale entry:** Đỉnh1 ban đầu có g10, được cải thiện qua đỉnh2 thành g2; đường tới3 tối ưu là [0,2,1,3] cost2.
- **Zero-cost edges:** Đường qua các cạnh0 vẫn hợp lệ, self-loop cost0 không gây vòng lặp do strict improvement.
- **BFS vs UCS:** BFS ít cạnh nhất [0,3] có cost9; UCS nhiều bước hơn nhưng cost3.
- **Implicit puzzle:** [1,2,4,5,10] có chuỗi hành động ×2,×2,+1,×2 tổng6.
- **Long.MAX_VALUE:** Chi phí bằng số này **vẫn là một đường có thật**; Map không dùng sentinel để phân biệt.
- **Overflow:** Math.addExact báo lỗi khi cost toán học vượt miền long.
- **Negative edge rejected:** Đồ thị tường minh có cạnh âm bị từ chối trước tìm.
- **Random cross-check:** Sinh 400 đồ thị nhỏ có hướng, gồm tự khuyên, cạnh trùng và trọng số0, rồi kiểm tra cost/reachability UCS so với Dijkstra, kể cả bài có hai đích. Nếu mismatch, chương trình ném AssertionError thay vì in PASS.

## 11. Độ phức tạp

Cho đồ thị hữu hạn V đỉnh, E cung, heap chứa cả các bản ghi cũ do cải thiện best:

- Xây adjacency: O(V+E).
- Mỗi đỉnh được settled tối đa một lần, duyệt các cung ra của đỉnh đó.
- Mỗi lần tìm nhãn tốt hơn, chèn một bản ghi mới; có nhiều nhất O(E+1) lần chèn trong triển khai tường minh này.
- Mỗi thao tác heap tốn O(log(E+1)) trong trường hợp xấu.

Do đó tổng thời gian thường viết:

```text
O((V+E) * log(E+1))
```

Nếu đồ thị đơn và E≤O(V²), có thể diễn đạt thường gặp là **O((V+E)log V)**. Bộ nhớ O(V+E), gồm adjacency, dist/best, parent, settled và heap.

Với đồ thị sinh ngầm, gọi R là số trạng thái được phát hiện, M là số phép chuyển thực sự sinh từ các trạng thái đã mở rộng. Khi hash/equals và sinh mỗi move trung bình O(1), chi phí tương tự:

```text
O((R+M) * log(M+1))
```

Cần cộng thêm chi phí tạo/copy/hashing state phức tạp; trong không gian vô hạn không thể dùng V,E hữu hạn cho toàn bộ bài toán.

### Vì sao dừng ở goal có thể nhanh hơn chạy hết Dijkstra?

Nếu goal tối ưu được pop sớm, UCS không cần mở rộng tất cả trạng thái khác. Khi goal không tới được hoặc rất đắt so với phần lớn trạng thái, UCS vẫn có thể duyệt nhiều hoặc hầu hết các trạng thái có thể tới được. **Dừng sớm là lợi ích thực tiễn**, không bảo đảm giảm một bậc độ phức tạp trên mọi input.

Nếu chỉ cần tổng cost, không bắt buộc lưu parent. Nếu cần đường đi k hành động, lưu parent/action khi relax và phục hồi ngược mất O(k).

## 12. Lỗi thường gặp

1. **Cho rằng “chi phí đều” nghĩa là mọi bước cost1.** UCS chấp nhận cost không âm khác nhau.
2. **Dùng FIFO BFS khi trọng số không đều.** BFS tối ưu số bước, không tối ưu tổng cost.
3. **Dừng khi vừa sinh goal.** Có thể còn một đường rẻ hơn tới goal đang chờ.
4. **Đánh dấu settled khi push.** Lần gặp đầu tiên có thể không rẻ nhất.
5. **Sắp PriorityQueue theo cost của cạnh cuối.** Phải theo tổng g từ start.
6. **Sắp theo depth/số cạnh.** Đây là BFS chứ không phải UCS.
7. **Dùng greedy h thay cho g.** Không được thừa hưởng bảo đảm tối ưu của UCS.
8. **Quên stale-entry check.** Có thể mở rộng thừa hoặc xử lý nhãn không còn tốt nhất.
9. **Sửa key bên trong Java PriorityQueue.** Heap không tự sắp lại theo key đã đổi.
10. **Dùng phép trừ hai long trong comparator.** Có thể tràn hoặc bị ép int làm sai thứ tự.
11. **Relax cả khi candidate bằng best mà không có quy tắc xử lý hòa.** Chu trình0 có thể gây parent không ổn định.
12. **Dùng 0 làm dấu unreachable.** Có đường thật cost0.
13. **Dùng Long.MAX_VALUE làm INF vô điều kiện.** Đường cost đúng MAX là hợp lệ nhưng bị nhầm.
14. **Để phép cộng g+w tràn long.** Dùng Math.addExact hoặc BigInteger.
15. **Bắt ArithmeticException rồi in “NO_SOLUTION”.** Overflow không đồng nghĩa không có đường.
16. **Không kiểm tra start==goal.** Kết quả phải là cost0, đường một trạng thái.
17. **Bỏ mục tiêu không tới được và mặc định dist=0.** Cần Optional.empty hoặc reached riêng.
18. **Cho phép chi phí âm nhưng vẫn dừng UCS/Dijkstra khi pop goal.** Vi phạm định lý chốt.
19. **Cho rằng chu trình cost0 luôn gây lặp vô hạn.** Với đồ thị hữu hạn, closed set và strict improvement ngăn lặp.
20. **Cho rằng cost≥0 bảo đảm kết thúc trong mọi không gian vô hạn.** Có thể vô hạn trạng thái g=0 trước goal g=1.
21. **Không giới hạn số hành động sinh ra tại một trạng thái.** Một lần expand có thể không kết thúc.
22. **Dùng key chỉ gồm vị trí khi còn phụ thuộc keyMask/năng lượng/thời gian.** Gộp sai trạng thái.
23. **Dùng state mutable làm key HashMap.** Đổi key sau chèn có thể không tìm lại được.
24. **So sánh mảng state bằng equals tham chiếu.** Trạng thái nội dung giống nhau không được gộp.
25. **Không lưu parent/action khi cần phục hồi.** Chỉ có cost mà không có chuỗi lời giải.
26. **Cho rằng nghiệm tối ưu luôn duy nhất.** Có thể có nhiều đường bằng cost.
27. **Nhầm tie-break heap là bảo đảm đường từ điển nhỏ nhất.** Cần tối ưu tiêu chí thứ hai đúng cách.
28. **Trộn h vào g khi in chi phí.** h là ước lượng trong A*, không phải cost đã đi.
29. **Dùng 0–1 BFS cho cạnh cost2 trở lên.** Kỹ thuật deque 0/1 không còn đúng.
30. **Chỉ kiểm tra một goal mà quên predicate nhiều goal.** UCS có thể chọn đích tốt nhất trong một tập.
31. **Dùng int làm g cho đường dài.** Tổng chi phí có thể vượt int.
32. **Quên kiểm tra tràn trong hàm sinh trạng thái.** Math.addExact chỉ bảo vệ tổng cost.
33. **Cho rằng Dijkstra bắt buộc chạy đến hết đồ thị.** Có thể dừng khi đích được pop tối ưu.
34. **Cho rằng UCS bắt buộc dựng toàn bộ state graph.** Có thể sinh move khi cần.
35. **Chỉ kiểm thử cây không có chu trình.** Không phát hiện vấn đề stale và trạng thái lặp.
36. **Không đối chiếu với thuật toán tham chiếu trên test nhỏ.** Nên so với Dijkstra cho đồ thị có trọng số không âm.
37. **Coi kết quả bị ngắt do giới hạn tài nguyên là chứng minh vô nghiệm.** Đó chỉ là chưa tìm thấy trong giới hạn.
38. **Không phân biệt số bản ghi heap và số trạng thái khác nhau.** Một state có thể được chèn nhiều lần.
39. **Không kiểm tra edge endpoint/null move/chi phí âm ở lớp dữ liệu.** Lỗi input có thể làm hỏng logic.
40. **Tin rằng PriorityQueue tự bảo đảm tối ưu mà không cần giả thiết trọng số.** Chính điều kiện không âm và relax đúng mới cho định lý.

## 13. Bài tập có đáp án

**Bài 1.** UCS có yêu cầu mọi cạnh mang cost bằng nhau không?

**Đáp án:** Không. Chỉ yêu cầu không âm theo bản chuẩn; heap ưu tiên tổng g.

**Bài 2.** UCS và BFS khác nhau ở mục tiêu gì?

**Đáp án:** UCS tối thiểu hóa tổng chi phí; BFS tối thiểu hóa số cạnh. Tương đương về cost khi mọi cạnh cùng cost dương.

**Bài 3.** s→goal cost9; s→a cost1; a→b cost1; b→goal cost1. UCS phải trả gì?

**Đáp án:** s→a→b→goal, cost3; không dừng khi sinh goal cost9.

**Bài 4.** Vì sao goal phải được kiểm tra khi pop ở nhãn tốt nhất?

**Đáp án:** Chỉ lúc ấy định lý chốt đỉnh cho biết g(goal)=khoảng cách tối ưu; lúc sinh vẫn có thể cải thiện sau.

**Bài 5.** Quan hệ UCS và Dijkstra?

**Đáp án:** Cùng pop nhãn g/dist nhỏ nhất và relax trong đồ thị không âm. UCS thường dừng ở goal predicate và sinh trạng thái ngầm, Dijkstra thường tính mọi dist.

**Bài 6.** Với đồ thị phần 3, chi phí tối ưu từ0 đến4 là bao nhiêu?

**Đáp án:** 5 qua [0,1,2,3,4].

**Bài 7.** Nếu goal là 3 hoặc4 trong đồ thị đó?

**Đáp án:** Trả3, cost4, vì rẻ hơn goal4 cost5.

**Bài 8.** Đỉnh5 không tới được từ0, nên trả gì?

**Đáp án:** NO_SOLUTION/Optional.empty sau khi heap cạn trên đồ thị hữu hạn.

**Bài 9.** Nếu start đã là goal, đáp án?

**Đáp án:** cost0, states=[start], actions=[].

**Bài 10.** best[1]=2 nhưng heap có (1,10); xử lý thế nào?

**Đáp án:** Bỏ (1,10) vì stale, tiếp tục với bản ghi g=2.

**Bài 11.** Vì sao visited khi push có thể sai?

**Đáp án:** Một đường rẻ hơn tới cùng trạng thái có thể xuất hiện sau khi push lần đầu nhưng trước khi pop.

**Bài 12.** candidate==best[v] có buộc cập nhật parent không?

**Đáp án:** Không. Thường chỉ relax khi nhỏ hơn nghiêm ngặt.

**Bài 13.** Với đường trực tiếp một cạnh cost9 và đường ba cạnh cost3, BFS/UCS chọn gì?

**Đáp án:** BFS ít cạnh nhất chọn cost9; UCS tổng thấp nhất chọn cost3.

**Bài 14.** Nếu mọi cạnh cost7, BFS và UCS có cùng giá trị tối ưu không?

**Đáp án:** Có, vì cost=7×số cạnh.

**Bài 15.** Trọng số chỉ 0/1 nên cân nhắc thuật toán nào?

**Đáp án:** 0–1 BFS với deque, đẩy cost0 vào đầu và cost1 vào cuối.

**Bài 16.** A* có h=0 trở thành gì?

**Đáp án:** UCS về khóa ưu tiên f=g+h=g.

**Bài 17.** Phản ví dụ có cạnh âm khiến UCS dừng sai?

**Đáp án:** s→goal2,s→a5,a→goal−10: UCS dừng ở cost2 nhưng lời giải thật cost−5.

**Bài 18.** Đồ thị hữu hạn có chu trình cost0 làm UCS đúng bị kẹt không?

**Đáp án:** Không nếu dùng settled và chỉ relax khi tốt hơn nghiêm ngặt.

**Bài 19.** Vì sao không gian vô hạn với x→x+1 cost0 có thể làm UCS không đến goal cost1?

**Đáp án:** Có vô hạn trạng thái chi phí0 được ưu tiên trước goal cost1.

**Bài 20.** Điều kiện đủ quen thuộc để tìm được goal chi phí hữu hạn trong không gian vô hạn?

**Đáp án:** Branching hữu hạn, mỗi bước cost≥ε>0 và goal tối ưu có cost hữu hạn.

**Bài 21.** Từ1 đến10, +1 cost3, ×2 cost1. Đường tối ưu nào?

**Đáp án:** [1,2,4,5,10], actions=[×2,×2,+1,×2], tổng6.

**Bài 22.** Vì sao state key nên bất biến và có equals/hashCode đúng?

**Đáp án:** Để Map/Set nhận ra trạng thái logic giống nhau và không gộp các trạng thái khác nhau.

**Bài 23.** Tổng chi phí vượt Long.MAX_VALUE phải làm gì?

**Đáp án:** BigInteger/biểu diễn đủ miền; Math.addExact chỉ báo overflow.

**Bài 24.** Có thể dùng Long.MAX_VALUE làm INF vô điều kiện không?

**Đáp án:** Không, vì cost thực có thể bằng số đó. Dùng Map presence hoặc reached riêng.

**Bài 25.** Muốn phục hồi chuỗi thao tác thì cần lưu gì?

**Đáp án:** parent và action khi relax tốt hơn; khi pop goal, truy vết ngược.

**Bài 26.** Thời gian heap điển hình trên đồ thị hữu hạn V,E?

**Đáp án:** O((V+E)log(E+1)) với bản ghi cũ và thao tác O(1) trên cost/state; bộ nhớ O(V+E).

**Bài 27.** Nêu cách kiểm thử bản UCS mới.

**Đáp án:** Test cạnh0, self-loop0, nhiều đường tới cùng state, multiple goals, unreachable, start==goal, overflow, cạnh âm từ chối; so cost/reachability với Dijkstra trên đồ thị nhỏ ngẫu nhiên.

## 14. Bảng ghi nhớ

| Câu hỏi | Trả lời |
| --- | --- |
| UCS dùng khóa ưu tiên gì? | Tổng g từ start |
| Kiểm tra goal khi nào? | Sau pop bản ghi tốt nhất |
| Trọng số âm có được không? | Không trong UCS/Dijkstra chuẩn |
| Cạnh0 có được không? | Có |
| Khi nào settled? | Khi pop ở nhãn best hợp lệ |
| Khi nào relax? | `candidate<best[v]` |
| Có cần stale-entry? | Có nếu heap giữ nhiều bản ghi cùng state |
| Nhiều goal? | Dùng predicate, chọn goal được pop đầu tiên |
| Start là goal? | Cost0, đường một trạng thái |
| Không có đường? | Optional.empty/reached=false |
| Tổng vượt long? | Math.addExact báo lỗi hoặc BigInteger |
| Mọi cost bằng c>0? | BFS tối ưu tương đương về cost |
| Cost chỉ 0/1? | Có thể dùng 0–1 BFS |
| A* với h=0? | Tương đương UCS về khóa ưu tiên |
| Không gian trạng thái vô hạn? | Cần xét branching, cost ε và termination |
| Thời gian hữu hạn dùng heap? | O((V+E)log(E+1)) |

## Kết luận

**UCS chính là tư duy Dijkstra áp dụng trực tiếp vào tìm kiếm trạng thái:** luôn ưu tiên cấu hình đang biết có **tổng chi phí từ đầu nhỏ nhất**, kiểm tra mục tiêu **khi cấu hình ấy được lấy ra ở nhãn tốt nhất**, rồi thư giãn các phép chuyển với **chi phí không âm**.

Điều khác nhau chủ yếu là **bài toán và giao diện**: UCS thường dừng ở mục tiêu và có thể sinh đồ thị trạng thái khi cần, trong khi Dijkstra thường tính khoảng cách từ một nguồn đến nhiều đỉnh. Chứng minh tính đúng của cả hai dựa trên cùng một bất biến chốt đỉnh.

Khi áp dụng, hãy nhớ đồng thời ba lớp: **mô hình trạng thái phải đủ thông tin**, **min-heap/stale/settled phải đúng**, và **chi phí số học không được âm hay tràn**. Nếu tất cả các bước cùng cost dương, BFS đơn giản hơn; nếu chỉ có 0/1, cân nhắc 0–1 BFS; nếu có heuristic đã được chứng minh, xem xét A*; còn nếu có cạnh âm, cần rời UCS/Dijkstra chuẩn để dùng thuật toán phù hợp.
