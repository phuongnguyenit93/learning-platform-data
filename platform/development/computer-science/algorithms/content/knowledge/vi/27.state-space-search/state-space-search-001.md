# Mô hình trạng thái, hành động và chi phí chuyển

## 1. Tại sao phải mô hình hóa trước khi tìm kiếm?

Nhiều bài toán không cho sẵn một đồ thị với các đỉnh và cạnh. Thay vào đó, đề bài mô tả một **cấu hình ban đầu**, các **thao tác được phép**, và một **mục tiêu**: di chuyển robot, giải trò chơi, quản lý công việc, chọn hành động để mở cửa hoặc chuyển tài nguyên. Để giải, ta biến bài toán thành một **không gian trạng thái (state space)** rồi tìm một chuỗi thao tác hợp lệ.

Ví dụ:

- Robot trong kho cần biết vị trí, hướng, hàng đang cầm và pin còn lại.
- Người đi trên bản đồ cần biết tọa độ và những chìa khóa đã nhặt.
- Bài đi qua các trạm phụ thuộc loại vé, thời gian và tiền còn lại.
- Trò chơi xếp ô số cần biết vị trí tất cả quân, không chỉ vị trí ô trống.
- Lập kế hoạch công việc cần biết những bước đã hoàn tất và tài nguyên có sẵn.

Bài **tìm kiếm trạng thái** hỏi: từ cấu hình xuất phát, có thể thực hiện những hành động nào, dẫn tới cấu hình nào, tốn bao nhiêu, và làm thế nào tìm một cấu hình thỏa mục tiêu?

Một mô hình hình thức cho bài toán xác định thường viết:

~~~text
Problem = (S, s0, A, T, c, Goal)

S         tập các trạng thái hợp lệ
s0        trạng thái bắt đầu
A(s)      tập hành động có thể thực hiện từ s
T(s,a)    trạng thái mới sau hành động a tại s
c(s,a)    chi phí thực hiện bước chuyển ấy
Goal(s)   true nếu s là trạng thái đích
~~~

Nếu hành động xác định duy nhất trạng thái kế tiếp, T là một hàm. Với bài có kết quả ngẫu nhiên hoặc thông tin ẩn, phải dùng mô hình phức tạp hơn; bài này tập trung vào **trạng thái xác định, quan sát đầy đủ, chi phí cộng theo bước**.

Một lời giải là một đường đi:

~~~text
s0 --a1/c1--> s1 --a2/c2--> ... --ak/ck--> sk
~~~

Trong đó mỗi hành động đều hợp lệ và Goal(sk)=true. Tổng chi phí của đường bằng c1+c2+...+ck. Nếu đề muốn **ít bước nhất**, ta tối ưu k; nếu muốn **tổng chi phí thấp nhất**, ta tối ưu tổng c_i. Hai mục tiêu có thể cho những đường khác nhau.

## 2. State là thông tin đủ để quyết định tương lai

**State (trạng thái)** là tập thông tin cần có tại một thời điểm để xác định:

1. Hành động nào hợp lệ?
2. Thực hiện một hành động sẽ dẫn tới trạng thái nào?
3. Chi phí của hành động ấy là bao nhiêu?
4. Trạng thái hiện tại đã thỏa goal chưa?

Nguyên tắc quan trọng là **tính chất Markov**: hai lịch sử khác nhau dẫn tới **cùng state** phải có cùng các khả năng và chi phí trong tương lai. Khi đó thuật toán có thể gộp những đường tới cùng state mà không cần ghi nhớ toàn bộ quá khứ.

Ví dụ bản đồ có cửa cần chìa khóa. Hai tình huống:

~~~text
A = (row=2,col=2,hasKey=false)
B = (row=2,col=2,hasKey=true)
~~~

có cùng tọa độ nhưng **khả năng hành động khác nhau**: B có thể đi qua cửa, A không thể. Vì thế nếu state chỉ là (row,col), mô hình bị thiếu thông tin.

Với Java 17, một cách biểu diễn rõ ràng là:

~~~java
record State(int row, int col, boolean hasKey) {}
~~~

Record tự có equals và hashCode theo cả ba trường, thích hợp làm khóa trong HashMap và HashSet. Hãy dùng giá trị **bất biến** để một khóa không bị thay đổi sau khi đã thêm vào map.

### State khác gì một node của thuật toán tìm kiếm?

Một **state** biểu diễn cấu hình thực tế. Một **search node** biểu diễn một lần đi tới state bằng một đường cụ thể, có thể kèm:

~~~text
state      cấu hình
g          chi phí đã đi từ start tới state
parent     node/state trước trên đường đang xét
action     bước từ parent đến state
priority   khóa dùng trong priority queue
~~~

Hai đường khác nhau có thể tới cùng state. Với bài tối thiểu hóa chi phí không âm, ta thường giữ chi phí tốt nhất đã biết cho state đó trong dist[state], thay vì coi mỗi đường lịch sử là một state mới.

## 3. Chọn các trường state: đủ nhưng không thừa

Các trường state cần phản ánh **mọi đặc tính ảnh hưởng bước kế tiếp**, không nhất thiết phản ánh toàn bộ lịch sử:

| Luật bài toán | State phù hợp |
| --- | --- |
| Chỉ đi trong mê cung không có vật phẩm | (row,col) |
| Cửa cần một chìa khóa | (row,col,hasKey) |
| Có k loại chìa khóa | (row,col,keyMask) |
| Được phá tường một lần | (row,col,usedBreak) |
| Robot có bốn hướng quay | (row,col,direction) |
| Có pin hữu hạn | (row,col,remainingBattery) |
| Cửa mở theo chu kỳ p | (row,col,timeModP) |
| Trò TSP phải ghé các thành phố | (currentCity,visitedMask) |
| Có n công tắc độc lập | (position,switchMask) |

Nếu trạng thái phải chứa bitmask k khóa, chỉ riêng mặt nạ đã có tối đa 2^k giá trị. Cần ước lượng không gian này trước khi chọn thuật toán và cấu trúc lưu trữ.

**Sai lầm thiếu state:** chỉ ghi vị trí mà bỏ chìa khóa, nhiên liệu hoặc thời gian nên gộp hai tương lai khác nhau.

**Sai lầm thừa state:** đưa toàn bộ chuỗi đường đã đi vào khóa của mỗi node, dù tương lai chỉ phụ thuộc vị trí và khóa. Điều này làm khó phát hiện state lặp, và không gian tìm kiếm có thể tăng cấp số mũ theo độ sâu.

### Chi phí đã đi có phải là một phần của state?

Thông thường **không**. Với một bài tối thiểu hóa tổng cost, g là chi phí tốt nhất đã biết để tới state, lưu trong dist[state]. Hai đường tới cùng state với chi phí 6 và 10 có cùng tương lai; đường 10 không thể tốt hơn nếu mọi bước tương lai phụ thuộc state như nhau.

Nhưng nếu chi phí đã dùng quyết định **tính hợp lệ của các bước sau**, ví dụ còn tối đa 10 đơn vị pin, thì cần lưu **remainingBattery** hoặc nhiều nhãn tài nguyên. Nếu một state có nhiều tiêu chí (thời gian, tiền, năng lượng), có thể phải giữ nhiều **nhãn Pareto** không bị chi phối; không nên tùy tiện giảm về một dist[position].

## 4. Action, precondition, transition và effect

**Action (hành động)** là thao tác được cân nhắc tại state s. Mỗi hành động phải có:

- **Precondition:** điều kiện cho phép hành động.
- **Effect/transition:** state mới khi hành động được thực hiện.
- **Cost:** đại lượng cần cộng vào chi phí đường đi.

Ví dụ hành động RIGHT của robot:

~~~text
Action RIGHT
Precondition:
    col+1 nam trong ban do
    o dich khong la tuong
    neu o dich la cua D thi phai co khoa

Effect:
    col <- col+1
    neu vao o K thi hasKey <- true

Cost:
    4 neu o dich la o bun M
    1 trong cac truong hop hop le khac
~~~

Tốt nhất là hàm sinh láng giềng chỉ trả **transition hợp lệ**:

~~~text
neighbors(state):
    for action in allActions:
        if precondition(state,action) is false:
            continue
        next = transition(state,action)
        w = stepCost(state,action,next)
        emit (next,action,w)
~~~

Lúc đó BFS, Dijkstra và A* có thể dùng **cùng một hàm neighbors**, nhờ vậy luật bài toán không bị viết lặp thành ba phiên bản có thể bất nhất.

### Hiệu ứng xảy ra ở thời điểm nào?

Trong ví dụ của bài, **bước vào ô K tự động nhặt khóa**. Không có hành động PICK_UP riêng; hasKey chuyển thành true ngay khi bước vào K, và cost của bước vào K vẫn bằng 1.

Nếu đề nói phải đứng ở K rồi thực hiện PICK_UP tốn 1 lượt, phải mô hình thành một action độc lập với cost và effect khác. Không được tự chọn thời điểm nhặt vật tùy ý.

Tương tự, nếu mở cửa làm thay đổi cấu hình cửa vĩnh viễn, một biến openedDoor hoặc mask có thể cần thiết. Nếu cửa luôn cho phép đi qua khi hasKey=true và không có thay đổi độc lập, chỉ cần hasKey.

## 5. Xác định đúng chi phí chuyển

Với transition hợp lệ từ s qua a tới s', đặt c(s,a,s') là chi phí. Tổng chi phí của một đường P:

~~~text
Cost(P) = sum of c(s_i,a_i,s_{i+1})
          for i=0..k-1
~~~

Điều quan trọng là định nghĩa cost phải **phản ánh câu hỏi**:

- Mỗi bước cost=1 → tìm đường **ít hành động**.
- Thời gian mỗi bước khác nhau → tìm **tổng thời gian nhỏ nhất**.
- Đường có phí → tìm **tổng tiền** nhỏ nhất.
- Năng lượng khác nhau → tìm **tổng năng lượng** nhỏ nhất.
- Có bước cost 0 hoặc 1 → có thể dùng **0–1 BFS**.
- Có nhiều tiêu chí → cần xác định so sánh tổng hợp, thứ tự ưu tiên hoặc giải pháp nhiều nhãn.

**Chi phí ô đích hay ô nguồn?** Hai cách có thể cho đáp án khác nhau. Bài này tính **chi phí khi bước vào ô đích**. Ô bùn M tốn cost 4 tại bước vừa vào M, không tốn thêm 4 khi rời M.

### Chi phí âm và giới hạn của các thuật toán

BFS đếm số cạnh, không giải shortest weighted cost khi các cạnh có trọng số khác nhau. Dijkstra yêu cầu **mọi chi phí chuyển không âm**, cho phép cạnh 0. A* cần heuristic phù hợp, đặc biệt admissible và consistent cho biến thể dừng đơn giản. Nếu state graph hữu hạn có cạnh âm, có thể xét Bellman–Ford và phân tích **chu trình âm** nếu chúng reachable và có thể dẫn tới goal.

Không được xem tổng chi phí âm là một điều “Dijkstra sẽ tự xử lý” chỉ bằng cách dùng long. Với chu trình âm có thể lặp rồi tới goal, đôi khi không có giá trị cực tiểu hữu hạn.

### Overflow

Nhiều bước có cost vừa trong int nhưng tổng có thể vượt int hoặc long. Code dùng long và Math.addExact để phát hiện overflow thay vì âm thầm tràn số. Khi đề có tổng vượt long, cân nhắc BigInteger cho chi phí và priority queue.

## 6. Ví dụ xuyên suốt: bản đồ bùn, chìa khóa và cửa

Xét bản đồ ba hàng, năm cột:

~~~text
S . M # G
. # K # .
. . . D .
~~~

Mã hóa:

~~~java
static final String[] GRID = {
    "S.M#G",
    ".#K#.",
    "...D."
};
~~~

Quy tắc:

- **S** ở (0,0): bắt đầu.
- **G** ở (0,4): mục tiêu.
- **.**: ô trống, chi phí bước vào là 1.
- **M** ở (0,2): ô bùn, chi phí bước vào là 4.
- **#**: tường, không được đi vào.
- **K** ở (1,2): nhặt chìa khóa tự động khi đi vào, cost 1.
- **D** ở (2,3): cửa, chỉ được đi vào nếu đã có khóa, cost 1.
- Hành động: R (phải), D (xuống), L (trái), U (lên), mỗi lần một ô; không đi chéo.
- Không mất chìa khóa sau khi qua cửa.
- Goal test chỉ cần tọa độ (0,4), không yêu cầu cụ thể hasKey; nhưng mọi đường hợp lệ tới goal trên bản đồ này đều phải qua cửa sau khi nhặt khóa.

State:

~~~text
(row, col, hasKey)
start = (0,0,false)
goal(s) = (s.row == 0 && s.col == 4)
~~~

Hàm neighbors kiểm tra biên, tường và cửa rồi tạo trạng thái mới. Nếu ô đích K, hasKey trở thành true. Cùng vị trí (2,2) có hai state khác nhau:

~~~text
(2,2,false) -> không thể đi R vào D
(2,2,true)  -> có thể đi R vào D
~~~

Nếu visited chỉ chứa (row,col), mô hình sẽ bỏ lỡ sự khác nhau này.

### Lý do ví dụ không thể giải bằng “mỗi ô visited một lần”

Có đường tới (2,2) từ hàng dưới **chưa có khóa** với cost 4. Sau khi đi lên K rồi trở xuống, robot ở **cùng tọa độ** nhưng đã có khóa, tổng cost 6. Nếu Dijkstra dùng dist[row][col], record cost4 tại (2,2) có thể loại record cost6; nhưng record cost6 có hành động đi qua D mà record cost4 không có.

Vì vậy yêu cầu state đầy đủ **quan trọng hơn** việc tối ưu thuật toán.

## 7. BFS và Dijkstra cho hai đường khác nhau

### BFS: số bước ít nhất

BFS dùng queue FIFO và coi **mọi transition hợp lệ là một bước**. Với thứ tự thử hướng R,D,L,U, BFS tìm được:

~~~text
Actions:
R, R, D, D, R, R, U, U

States:
(0,0,0) -> (0,1,0) -> (0,2,0)
-> (1,2,1) -> (2,2,1) -> (2,3,1)
-> (2,4,1) -> (1,4,1) -> (0,4,1)

Moves = 8
Cost  = 1+4+1+1+1+1+1+1 = 11
~~~

Đường này ngắn về **số cạnh**, nhưng phải qua ô M có cost4.

### Dijkstra: tổng chi phí thấp nhất

Dijkstra so đường theo tổng cost, vì mọi bước có cost1 hoặc cost4 (không âm). Nó chọn đường vòng dưới để **tránh bùn**:

~~~text
Actions:
D, D, R, R, U, D, R, R, U, U

States:
(0,0,0) -> (1,0,0) -> (2,0,0)
-> (2,1,0) -> (2,2,0) -> (1,2,1)
-> (2,2,1) -> (2,3,1) -> (2,4,1)
-> (1,4,1) -> (0,4,1)

Moves = 10
Cost  = 10
~~~

Bước vào K tự động đổi hasKey thành true. Sau đó robot quay lại (2,2) **với state khác** để mở cửa D.

| Thuật toán | Tối ưu theo | Số bước | Tổng chi phí |
| --- | --- | ---: | ---: |
| BFS | Số action | 8 | 11 |
| Dijkstra | Tổng cost | 10 | 10 |
| A* với heuristic Manhattan hợp lệ | Tổng cost | 10 | 10 |

**BFS không sai**: nó đang tối thiểu hóa một mục tiêu khác. Nếu đề hỏi chi phí năng lượng ít nhất, dùng BFS mà bỏ qua cost sẽ trả lời sai.

## 8. Đồ thị trạng thái ngầm (implicit state graph)

Ta không cần tạo trước danh sách của mọi state. Mỗi khi thuật toán đang xét một state, nó gọi:

~~~text
neighbors(state)
    -> List<Transition(nextState, action, cost)>
~~~

Đây là **implicit graph search**. Các đỉnh là state có thể phân biệt bằng equals/hashCode; các cạnh là transition hợp lệ.

Ưu điểm:

- Chỉ sinh state khi thật sự cần, không phải liệt kê toàn bộ cấu hình.
- Luật bài toán tập trung trong một hàm neighbors.
- Có thể thay đổi thuật toán BFS/Dijkstra/A* mà không viết lại transition.
- HashMap/HashSet khử những trạng thái lặp do đi trái–phải hoặc đi vòng.
- Có thể lưu parent để dựng một lời giải khi tìm thấy goal.

Với H×W ô và một boolean hasKey, số state lý thuyết tối đa là:

~~~text
2 * H * W
~~~

Ở bản đồ 3×5, cận trên là 30 state, trước khi loại tường và state không reachable. Mỗi state có tối đa bốn candidate actions, nên số transition ngầm O(4N)=O(N) đối với bản đồ này.

### Graph search khác tree search

Một search tree có thể chứa nhiều node cùng state, vì có nhiều đường đi tới state đó. Một đồ thị trạng thái có thể có chu trình (đi từ ô A sang B rồi quay lại A). Nếu thuật toán chỉ phát triển cây tìm kiếm mà không khử trùng state, nó có thể mở rộng vô hạn trên chu trình.

Graph search dùng visited khi phù hợp, hoặc dist[state] khi có chi phí, để quản lý sự trùng lặp **theo state đầy đủ**.

## 9. BFS, DFS, 0–1 BFS, Dijkstra và A*: chọn đúng thuật toán

| Bài toán | Công cụ phù hợp | Điều kiện quan trọng |
| --- | --- | --- |
| Chỉ hỏi có tới goal không | BFS hoặc DFS | Phải khử state lặp để kết thúc trên graph hữu hạn |
| Ít hành động nhất | BFS | Mỗi action tính một bước như nhau |
| Tổng cost chỉ gồm 0 và 1 | 0–1 BFS | Dùng deque, đẩy cost0 trước |
| Tổng cost không âm | Dijkstra | Relax và priority queue theo g |
| Có heuristic là cận dưới phù hợp | A* | h admissible/consistent theo chiến lược triển khai |
| Graph hữu hạn có cạnh âm | Bellman–Ford hoặc kỹ thuật phù hợp | Phân tích chu trình âm |
| State graph là DAG | Topological DP | Cần xác định thứ tự topo |
| Tất cả hành động chọn ngẫu nhiên | MDP/search stochastic | Cần transition xác suất, không phải path deterministic |

DFS có thể tìm được một lời giải nhưng **không** bảo đảm số bước hoặc tổng cost tốt nhất. BFS bảo đảm số bước ít nhất, còn Dijkstra bảo đảm tổng cost ít nhất với cost không âm. A* dùng heuristic để dẫn tìm kiếm, nhưng tối ưu chỉ được bảo đảm dưới các giả định của heuristic.

## 10. Dijkstra trên state graph và cơ chế relax

Dijkstra lưu chi phí tốt nhất đã biết:

~~~text
dist[state] = best known cost from start to state
parent[state] = previous state and transition
~~~

Với state hiện tại s có g=dist[s], mỗi transition s→t cost w sẽ cho ứng viên:

~~~text
candidate = g + w

if candidate < dist[t]:
    dist[t] = candidate
    parent[t] = (s, action, w)
    push (t, candidate) into priority queue
~~~

Hãy bắt đầu dist[start]=0. Lấy state có g nhỏ nhất từ priority queue; nếu g khác dist[state] hiện tại thì đó là bản ghi **stale** (đã bị một đường tốt hơn thay thế), bỏ qua.

Trong Java, PriorityQueue không hỗ trợ decrease-key trực tiếp. Cách thông dụng là thêm một bản ghi mới khi tìm dist tốt hơn và kiểm stale lúc pop.

**Không đánh dấu hoàn tất ngay khi push vào queue.** Với trọng số khác nhau, có thể tìm thấy một state ban đầu qua đường cost20 rồi sau đó qua đường cost6. Chỉ khi lấy state từ hàng đợi ưu tiên với g hợp lệ nhỏ nhất mới có thể coi nó đã được chốt theo bất biến Dijkstra.

Với nhiều goal states thỏa Goal(s), Dijkstra có thể dừng ở **goal hợp lệ đầu tiên được pop**, vì khi cost không âm, đó là một goal có tổng cost tối thiểu.

### Bài toán không có lời giải

Nếu priority queue rỗng mà không có goal reachable, trả trạng thái NO_SOLUTION hoặc Optional.empty(). Không trả một đường đi giả và không coi dist[goal] chưa có là 0.

## 11. Heuristic A* và điều kiện tối ưu

A* ưu tiên state theo:

~~~text
f(s) = g(s) + h(s)

g(s): cost đã biết từ start
h(s): ước lượng cost còn lại tới goal
~~~

Một heuristic **admissible** không bao giờ lớn hơn chi phí tối ưu thật sự từ state tới goal. Một heuristic **consistent** thỏa:

~~~text
h(goal) = 0
h(s) <= cost(s,t) + h(t)
~~~

với mọi transition s→t. Với heuristic consistent và cost không âm, cách cài đặt graph search có thể dừng khi goal hợp lệ được pop.

### Manhattan là cận dưới hợp lệ ở ví dụ

Goal ở (0,4), robot chỉ di chuyển một ô lên/xuống/trái/phải, và mỗi bước cost≥1:

~~~text
h(row,col,hasKey)
    = abs(row-0) + abs(col-4)
~~~

Một đường đi hợp lệ phải mất ít nhất Manhattan bước nếu chỉ di chuyển từng ô. Bùn, tường, khóa và cửa chỉ có thể giữ nguyên hoặc tăng chi phí thật, không làm h vượt mức tối ưu. Vì thế h admissible.

Mỗi bước giảm Manhattan nhiều nhất 1, còn cost≥1, nên h consistent:

~~~text
h(s) <= 1 + h(next) <= cost(s,next) + h(next)
~~~

A* trên bản đồ này cho cost10, cùng Dijkstra, nhưng có thể mở rộng ít state hơn.

Với thứ tự hướng và tie-breaking cụ thể của chương trình ở phần 12:

~~~text
BFS expanded      = 19
Dijkstra expanded = 18
A* expanded       = 13
~~~

Số expanded phụ thuộc cách phá hòa trong queue và thứ tự sinh transition; không có định lý rằng mọi lần A* đều mở rộng ít hơn Dijkstra.

### Khi Manhattan không còn hợp lệ

Nếu thêm teleport di chuyển nhiều ô với cost nhỏ hoặc bước cost0 giúp giảm Manhattan, heuristic Manhattan nhân 1 có thể **ước lượng vượt** chi phí còn lại. Khi đó phải thay h bằng một lower bound mới, hoặc h=0 để A* trở thành Dijkstra.

Nếu heuristic không consistent, thuật toán A* có thể cần xử lý **mở lại state** và quy tắc dừng cẩn thận; không được chỉ dựa vào trực giác “gần goal nên tốt hơn”.

## 12. Java 17 – BFS, Dijkstra và A* cùng một mô hình transition

Chương trình dùng record bất biến để biểu diễn State và Transition. Nó lưu một parent map riêng để dựng lại path, dùng long cho tổng cost và Math.addExact khi cộng. Cả ba thuật toán chia sẻ **một hàm neighbors**: đây là phần quan trọng nhất để tách **mô hình bài toán** khỏi **chiến lược tìm kiếm**.

Lưu toàn bộ mã thành **StateSpaceSearchDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.PriorityQueue;
import java.util.Set;

public class StateSpaceSearchDemo {

    private static final String[] GRID = {
            "S.M#G",
            ".#K#.",
            "...D."
    };

    private static final int GOAL_ROW = 0;
    private static final int GOAL_COL = 4;

    // Direction order R, D, L, U makes output reproducible.
    private static final int[] DR = {0, 1, 0, -1};
    private static final int[] DC = {1, 0, -1, 0};
    private static final String[] ACTION = {"R", "D", "L", "U"};

    record State(int row, int col, boolean hasKey) {}

    record Transition(State next, String action, int cost) {}

    record Parent(State previous, String action, int cost) {}

    record Node(State state, long g, long priority, long serial) {}

    record Result(
            long totalCost,
            List<String> actions,
            List<State> states,
            int expanded) {

        int moves() {
            return actions.size();
        }
    }

    private static final State START =
            new State(0, 0, false);

    private static boolean isGoal(State s) {
        return s.row() == GOAL_ROW && s.col() == GOAL_COL;
    }

    private static List<Transition> neighbors(State s) {
        List<Transition> out = new ArrayList<>();

        for (int d = 0; d < DR.length; d++) {
            int nr = s.row() + DR[d];
            int nc = s.col() + DC[d];

            if (nr < 0 || nr >= GRID.length
                    || nc < 0 || nc >= GRID[0].length()) {
                continue;
            }

            char tile = GRID[nr].charAt(nc);

            if (tile == '#') {
                continue;
            }
            if (tile == 'D' && !s.hasKey()) {
                continue;
            }

            boolean nextKey = s.hasKey() || tile == 'K';
            int cost = (tile == 'M') ? 4 : 1;

            out.add(new Transition(
                    new State(nr, nc, nextKey),
                    ACTION[d],
                    cost));
        }

        return out;
    }

    private static boolean canMove(State s, String action) {
        for (Transition tr : neighbors(s)) {
            if (tr.action().equals(action)) {
                return true;
            }
        }
        return false;
    }

    private static long manhattan(State s) {
        return Math.abs((long) s.row() - GOAL_ROW)
                + Math.abs((long) s.col() - GOAL_COL);
    }

    private static Result reconstruct(
            State goal,
            Map<State, Parent> parent,
            int expanded) {

        List<State> reverseStates = new ArrayList<>();
        List<String> reverseActions = new ArrayList<>();
        State current = goal;
        long totalCost = 0;

        while (true) {
            reverseStates.add(current);
            if (current.equals(START)) {
                break;
            }

            Parent p = parent.get(current);
            if (p == null) {
                throw new IllegalStateException(
                        "broken predecessor chain");
            }

            reverseActions.add(p.action());
            totalCost = Math.addExact(totalCost, p.cost());
            current = p.previous();
        }

        Collections.reverse(reverseStates);
        Collections.reverse(reverseActions);

        return new Result(
                totalCost,
                List.copyOf(reverseActions),
                List.copyOf(reverseStates),
                expanded);
    }

    // Minimizes the number of actions; ignores weight priority.
    static Optional<Result> bfsFewestMoves() {
        ArrayDeque<State> queue = new ArrayDeque<>();
        Set<State> seen = new HashSet<>();
        Map<State, Parent> parent = new HashMap<>();

        queue.addLast(START);
        seen.add(START);
        int expanded = 0;

        while (!queue.isEmpty()) {
            State s = queue.removeFirst();
            expanded++;

            if (isGoal(s)) {
                return Optional.of(reconstruct(
                        s, parent, expanded));
            }

            for (Transition tr : neighbors(s)) {
                State next = tr.next();
                if (seen.add(next)) {
                    parent.put(next,
                            new Parent(s, tr.action(), tr.cost()));
                    queue.addLast(next);
                }
            }
        }

        return Optional.empty();
    }

    // astar=false: Dijkstra. astar=true: A*.
    // Every transition costs at least 1 in this map.
    static Optional<Result> leastCost(boolean astar) {
        Map<State, Long> dist = new HashMap<>();
        Map<State, Parent> parent = new HashMap<>();

        PriorityQueue<Node> pq = new PriorityQueue<>(
                Comparator.comparingLong(Node::priority)
                        .thenComparingLong(Node::serial));

        long serial = 0;
        dist.put(START, 0L);
        pq.add(new Node(
                START,
                0L,
                astar ? manhattan(START) : 0L,
                serial++));

        int expanded = 0;

        while (!pq.isEmpty()) {
            Node entry = pq.poll();
            Long best = dist.get(entry.state());

            // Ignore an outdated queue entry.
            if (best == null || entry.g() != best) {
                continue;
            }

            State s = entry.state();
            expanded++;

            if (isGoal(s)) {
                return Optional.of(reconstruct(
                        s, parent, expanded));
            }

            for (Transition tr : neighbors(s)) {
                long candidate = Math.addExact(
                        entry.g(), tr.cost());
                State next = tr.next();

                Long previous = dist.get(next);
                if (previous == null || candidate < previous) {
                    dist.put(next, candidate);
                    parent.put(next,
                            new Parent(s, tr.action(), tr.cost()));

                    long priority = Math.addExact(
                            candidate,
                            astar ? manhattan(next) : 0L);
                    pq.add(new Node(
                            next, candidate, priority, serial++));
                }
            }
        }

        return Optional.empty();
    }

    private static String displayState(State s) {
        return "(" + s.row() + "," + s.col()
                + ",key=" + (s.hasKey() ? 1 : 0) + ")";
    }

    private static List<String> displayPath(
            List<State> states) {

        List<String> text = new ArrayList<>();
        for (State s : states) {
            text.add(displayState(s));
        }
        return List.copyOf(text);
    }

    public static void main(String[] args) {
        Result bfs = bfsFewestMoves().orElseThrow();
        Result dijkstra = leastCost(false).orElseThrow();
        Result aStar = leastCost(true).orElseThrow();

        System.out.println("BFS moves = " + bfs.moves());
        System.out.println("BFS cost = " + bfs.totalCost());
        System.out.println("BFS actions = " + bfs.actions());
        System.out.println("BFS expanded = " + bfs.expanded());

        System.out.println(
                "Dijkstra moves = " + dijkstra.moves());
        System.out.println(
                "Dijkstra cost = " + dijkstra.totalCost());
        System.out.println(
                "Dijkstra actions = " + dijkstra.actions());
        System.out.println(
                "Dijkstra expanded = " + dijkstra.expanded());
        System.out.println(
                "Dijkstra states = "
                + displayPath(dijkstra.states()));

        System.out.println("A* cost = " + aStar.totalCost());
        System.out.println("A* moves = " + aStar.moves());
        System.out.println("A* expanded = " + aStar.expanded());
        System.out.println(
                "A* agrees with Dijkstra = "
                + (aStar.totalCost() == dijkstra.totalCost()));

        State noKey = new State(2, 2, false);
        State hasKey = new State(2, 2, true);

        System.out.println(
                "without key can enter door = "
                + canMove(noKey, "R"));
        System.out.println(
                "with key can enter door = "
                + canMove(hasKey, "R"));
        System.out.println(
                "same coordinate different states = "
                + !noKey.equals(hasKey));
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac StateSpaceSearchDemo.java
java StateSpaceSearchDemo
~~~

**Stdout chính xác** với thứ tự R,D,L,U và priority-queue tie-breaking của chương trình:

~~~text
BFS moves = 8
BFS cost = 11
BFS actions = [R, R, D, D, R, R, U, U]
BFS expanded = 19
Dijkstra moves = 10
Dijkstra cost = 10
Dijkstra actions = [D, D, R, R, U, D, R, R, U, U]
Dijkstra expanded = 18
Dijkstra states = [(0,0,key=0), (1,0,key=0), (2,0,key=0), (2,1,key=0), (2,2,key=0), (1,2,key=1), (2,2,key=1), (2,3,key=1), (2,4,key=1), (1,4,key=1), (0,4,key=1)]
A* cost = 10
A* moves = 10
A* expanded = 13
A* agrees with Dijkstra = true
without key can enter door = false
with key can enter door = true
same coordinate different states = true
~~~

### Vì sao ví dụ Java tự chạy được?

- Một public class duy nhất StateSpaceSearchDemo, tên khớp tệp .java; không cần thư viện ngoài JDK.
- State là record bất biến, HashMap/HashSet phân biệt đủ row,col,hasKey.
- Transition có next,action,cost; các thuật toán dùng chung neighbors.
- BFS đánh dấu state khi enqueue, tìm số bước tối thiểu.
- Dijkstra/A* dùng priority queue và kiểm stale trước khi mở rộng.
- Parent được cập nhật **chỉ khi có đường cải thiện**, cho phép dựng một đường hợp lệ.
- Optional.empty() biểu diễn khi không có goal reachable; main dùng orElseThrow vì bản đồ mẫu có lời giải.
- Math.addExact phát hiện tràn long ở tổng chi phí; không âm thầm biến số dương thành số âm.
- Thứ tự sinh láng giềng được cố định để các đường và số expanded trong stdout có thể đối chiếu.

**Nhắc lại:** thay đổi thứ tự hướng có thể đổi đường được in trong trường hợp hòa và số expanded, nhưng không đổi số bước BFS tối thiểu hoặc tổng cost tối thiểu của Dijkstra/A* nếu mô hình và giả định vẫn đúng.

## 13. Chứng minh tính đúng: mô hình trước, thuật toán sau

### Soundness của transition

Mỗi transition do neighbors sinh ra chỉ đi sang một trong bốn ô kề, trong biên, không phải tường và không vi phạm khóa ở cửa. Khi vào K, hasKey được cập nhật đúng; cost phản ánh ô đích. Vì thế mọi transition trong graph ngầm là **một hành động hợp lệ thật sự** của bài toán.

### Completeness của transition

Bài chỉ cho phép bốn hướng. neighbors xét đủ bốn hướng và chỉ bỏ các action không hợp lệ. Vì vậy mọi hành động hợp lệ của bài đều có một transition tương ứng. Mọi chuỗi hành động hợp lệ do đó ánh xạ sang một đường trong state graph, và ngược lại.

### State đủ thông tin

Tọa độ xác định vị trí và các ô lân cận, hasKey quyết định việc vào cửa; không có thông tin lịch sử khác ảnh hưởng bước tiếp theo. Vì vậy mô hình thỏa Markov. Nếu bỏ hasKey, tính chất này hỏng ngay tại (2,2).

### BFS đúng cho số bước

BFS mở rộng state theo số cạnh tăng dần. Vì mỗi action tương ứng một cạnh, lần đầu pop một goal cho đường có số action ít nhất. Nó không tuyên bố tối thiểu hóa tổng chi phí trọng số.

### Dijkstra đúng cho tổng chi phí

Mọi cost trong bản đồ bằng 1 hoặc 4, không âm. Theo bất biến Dijkstra, khi pop một state với g hợp lệ nhỏ nhất, không đường chưa xét nào có thể làm g giảm. Vì vậy goal đầu tiên được pop có tổng cost tối ưu.

### A* đúng với heuristic cụ thể

Manhattan là cận dưới của số bước vì mỗi action dịch đúng một ô. Mỗi action tốn ít nhất 1, nên Manhattan không vượt chi phí thật. Với mỗi transition, Manhattan giảm tối đa 1 và cost≥1, do đó h consistent. A* dừng khi goal được pop với chi phí tối ưu.

### Đường được dựng lại có thật

Parent của mỗi state chỉ được ghi từ một transition hợp lệ. reconstruct truy ngược tới start, đảo lại thứ tự rồi cộng đúng cost bước. Mỗi cặp state liên tiếp trong lời giải do đó là một bước hợp lệ, và totalCost khớp tổng các bước.

## 14. Độ phức tạp: phụ thuộc số state thật, không chỉ kích thước map

Đặt N là số state reachable, M là số transition có thể sinh giữa các state reachable, b là số action ứng viên tối đa và d là độ dài lời giải.

| Thuật toán | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| BFS | O(N+M) | O(N) cho seen, queue, parent |
| DFS có khử trùng | O(N+M) | O(N) |
| 0–1 BFS | O(N+M) | O(N) |
| Dijkstra heap | O((N+M) log(N+1)) theo cận thường dùng | O(N+M) với duplicate queue entries |
| A* consistent | Phụ thuộc heuristic và số state mở rộng; worst-case có thể lớn | O(N+M) nếu giữ best, heap và parent |
| Bellman–Ford explicit | O(NM) | O(N), chưa tính lưu graph |

Với grid H×W, hasKey boolean, N≤2HW và M≤4N vì có tối đa bốn action đi một ô. Với k khóa độc lập, cận N≤HW·2^k, có thể quá lớn.

**Bộ nhớ Java:** HashMap<State,Long>, record, Node và PriorityQueue có overhead object/boxing. Nếu miền state nhỏ, có thể mã hóa stateId rồi dùng mảng primitive dist/parent, nhưng chỉ khi chứng minh mã hóa **không gộp hai state khác nhau**.

BFS/Dijkstra/A* có thể dừng sớm khi gặp goal theo đúng tiêu chuẩn của mỗi thuật toán. Không cần dựng toàn bộ graph nếu đã có lời giải tối ưu. Tuy nhiên một bài cần **đếm tất cả đường tối ưu** hoặc liệt kê mọi state reachable sẽ có yêu cầu khác và có thể cần xử lý hết.

## 15. Mở rộng mô hình theo thời gian và tài nguyên

### Thời gian theo chu kỳ

Nếu cửa mở ở những thời điểm có t mod p thuộc một tập nhất định, cùng vị trí ở hai pha khác nhau có thể có các bước hợp lệ khác nhau:

~~~text
State = (row, col, timeModP)
Next phase = (timeModP + actionDuration) mod p
~~~

Nếu chi phí thời gian phụ thuộc giờ tuyệt đối chứ không chỉ pha chu kỳ, timeModP có thể không đủ; phải chứng minh state vẫn quyết định được tương lai.

### Pin, nhiên liệu và hạn mức

Nếu robot có pin R, hành động tốn d pin chỉ hợp lệ khi remainingBattery≥d:

~~~text
State = (position, remainingBattery)
Next battery = remainingBattery - d
~~~

Đối với mục tiêu ít thời gian nhưng giới hạn pin, có thể cần nhiều nhãn (time,battery) tại cùng position. Không được chỉ giữ một dist[position] nếu nhãn có ít thời gian hơn nhưng ít pin hơn **không chi phối** nhãn kia.

### Công tắc và cửa thay đổi vĩnh viễn

Nếu có n công tắc bật/tắt, state có thể là (position,maskSwitches). Một hành động nhấn công tắc đổi một bit. Không gian tăng theo 2^n; cần xem n đủ nhỏ không và liệu có tính đối xứng hoặc quy tắc rút gọn nào.

### WAIT và cost 0

Một hành động WAIT có thể cần thiết nếu thời gian ảnh hưởng sự hợp lệ của chuyển động. Nếu WAIT không đổi bất kỳ trường state nào nhưng tốn cost dương, nó không cải thiện đường đi tối ưu. Nếu có vòng chuyển cost0, Dijkstra vẫn đúng với cost không âm và relax nghiêm ngặt sẽ không lặp vô hạn chỉ vì một state đã có dist bằng nhau.

Tuy nhiên bài **đếm tất cả đường tối ưu** có zero-cost cycles có thể có vô hạn walk; đây là vấn đề riêng.

### Hành động ngẫu nhiên

Nếu đi qua một ô có xác suất thất bại, transition không còn là một hàm xác định đơn giản. Có thể phải dùng MDP, policy và kỳ vọng chi phí. Không lấy một đường đơn tối thiểu chi phí rồi tự xem đó là lời giải tối ưu kỳ vọng.

## 16. Các lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| State chỉ có vị trí dù cần khóa | Gộp hai khả năng tương lai | Thêm hasKey/bitmask |
| Đưa toàn bộ path vào state | Nhiều state trùng ngữ nghĩa | Lưu parent riêng |
| Kiểm visited theo vị trí trên bài có tài nguyên | Bỏ đường hợp lệ | Hash theo state đầy đủ |
| Quên điều kiện vào cửa D | Đường đi không hợp lệ | Precondition rõ ràng |
| Quên cập nhật hasKey khi vào K | Có thể báo không có lời giải | Effect xảy ra ngay khi vào |
| Tính cost theo ô nguồn thay ô đích | Tổng chi phí lệch | Một quy ước nhất quán |
| Dùng BFS khi cost khác nhau | Ít bước nhưng đắt tiền | Dijkstra hoặc A* |
| Dijkstra đánh dấu visited khi push | Bỏ đường rẻ hơn tìm sau | Dùng dist và stale check |
| Dijkstra với cạnh âm | Không đảm bảo tối ưu | Bellman–Ford hoặc mô hình khác |
| A* dùng Manhattan khi có teleport rẻ | h overestimate | Thiết kế lại lower bound |
| A* dừng khi goal mới được enqueue | Có thể dừng quá sớm | Chỉ dừng khi goal được pop hợp lệ |
| Quên reset parent khi có đường tốt hơn | Path và dist không khớp | Cập nhật parent khi relax |
| Không phân biệt một goal với goal predicate | Bỏ các goal hợp lệ | Goal(s) theo đề |
| Hash không gồm tất cả trường quan trọng | Collision về ngữ nghĩa | equals/hashCode full state |
| Mutable key trong HashMap | Không tìm lại được state | Record immutable |
| Nhầm row/col, x/y | Điều hướng sai | Thống nhất thứ tự tọa độ |
| Không khử state lặp | Chu trình đi qua lại vô tận | Visited hoặc best dist |
| Không xác thực action hợp lệ | Sinh state ngoài miền | neighbors lọc ngay |
| Cộng cost bằng int khi bài dài | Overflow | long + addExact |
| Coi mọi state lý thuyết đều reachable | Đánh giá sai kích thước | Chỉ mở rộng state hợp lệ |
| Không lưu đủ transition cost trong parent | Không kiểm trace được | Parent chứa action/cost |
| Không kiểm no-solution | Crash hoặc path giả | Optional.empty |
| Đếm lời giải với zero-cost cycle như path hữu hạn | Có thể vô hạn walk tối ưu | Xác định rõ đường đơn/walk |

## 17. Kiểm thử luật trước khi kiểm thuật toán

Khi gặp một bài state search, trước tiên hãy test **hàm transition độc lập**. Nếu neighbors sai, BFS/Dijkstra/A* có thể nhất quán với nhau mà vẫn giải sai bài gốc.

### Các kiểm thử tay trên bản đồ

~~~text
State(0,0,false):
  R -> State(0,1,false), cost=1
  D -> State(1,0,false), cost=1

State(0,1,false):
  R -> State(0,2,false), cost=4
  D -> INVALID (wall)

State(2,2,false):
  R -> INVALID (door locked)
  U -> State(1,2,true), cost=1

State(2,2,true):
  R -> State(2,3,true), cost=1
~~~

### Các bất biến của đường trả về

Với Result có states và actions:

1. states.size()==actions.size()+1.
2. states đầu là START, states cuối thỏa Goal.
3. Mỗi transition (states[i],actions[i],states[i+1]) hợp lệ.
4. Tổng cost các bước đúng bằng totalCost.
5. Không state nào nằm trong tường hoặc vượt biên.
6. Chỉ vào cửa D khi đã có khóa.
7. hasKey đã true không trở lại false trong mô hình giữ khóa vĩnh viễn.
8. Không xuất hiện bước nhảy qua nhiều ô trong bản đồ chỉ cho phép bốn hướng.

### Oracle độc lập cho tổng cost

Với bản đồ 3×5 có tối đa 30 state lý thuyết, có thể liệt kê explicit state graph rồi chạy **Bellman–Ford** để xác định chi phí tối ưu. Kết quả phải bằng 10, trùng Dijkstra và A*. Đối với số bước, dùng explicit BFS và kiểm bằng 8.

Nên kiểm các transition bằng bảng tay ở trên trước khi dùng cùng hàm neighbors để sinh graph oracle, nếu không cả hai thuật toán có thể dùng chung một lỗi mô hình.

### Kiểm heuristic

Với mỗi transition s→t:

~~~text
h(goal)=0
h(s) <= cost(s,t) + h(t)
~~~

So Manhattan với khoảng cách chi phí thật từ state tới goal trên graph nhỏ để kiểm h≤exactRemainingCost. Nếu thêm chuyển cost0 hoặc teleport, phải chạy lại kiểm định; heuristic cũ có thể không còn hợp lệ.

### Thử các biến đổi dữ liệu

- Đổi M thành cost1: BFS và Dijkstra có thể đều đạt đường 8 bước, cost8.
- Tăng cost M: Dijkstra càng ưu tiên đường vòng; BFS vẫn chỉ đếm bước.
- Bỏ K: cửa D không mở được, bài có thể vô nghiệm.
- Đổi D thành ô trống: đường đi có thể không cần khóa, state có thể đơn giản hơn.
- Thêm khóa khác: phải mở rộng state thành bitmask.
- Thêm cost0: Dijkstra vẫn đúng, Manhattan có thể không admissible.
- Thêm teleport: số bước và cost đổi; kiểm lại heuristic.
- Đổi thứ tự hướng: tối ưu chi phí/số bước không đổi, nhưng path in và expanded có thể khác.
- Tạo bản đồ không có đường: phải trả Optional.empty().
- State có tài nguyên hoặc thời gian: test hai state cùng vị trí khác điều kiện tương lai.

## 18. Bài tập thực hành

1. Liệt kê state, action, precondition và effect của bản đồ 3×5.
2. Với (2,2,false) và (2,2,true), giải thích vì sao không thể gộp.
3. Mô phỏng BFS, ghi đường 8 bước và tổng cost11.
4. Mô phỏng Dijkstra, ghi đường 10 bước và tổng cost10.
5. Đổi cost của M thành 1 rồi chạy lại; BFS và Dijkstra có cùng đường tối ưu không?
6. Thêm action WAIT cost1. Vì sao nó không giúp trong bản đồ tĩnh không có luật thời gian?
7. Thêm action PICK_UP riêng tại K, có cost1; sửa state và transition.
8. Sửa D để tiêu hao chìa khóa khi đi qua; kiểm mô hình có còn đúng không.
9. Thêm hai loại khóa, dùng bitmask và ước lượng số state.
10. Viết hàm in các bước (from,action,to,cost) của Result.
11. Viết phiên bản không lưu parent khi chỉ cần chi phí tối ưu.
12. Chứng minh BFS chỉ visited[row][col] có thể sai nếu có khóa hoặc pin.
13. Tạo explicit state graph rồi dùng Bellman–Ford đối chứng Dijkstra.
14. Chứng minh Manhattan admissible/consistent khi mỗi bước dịch một ô cost≥1.
15. Thêm teleport từ start tới gần goal cost1 và tìm lỗi của heuristic cũ.
16. Thêm bước cost0, đổi A* về h=0 và so với Dijkstra.
17. Cài 0–1 BFS cho graph có trọng số chỉ 0 hoặc 1.
18. Thêm remainingBattery và precondition tiêu hao pin khi qua M.
19. Thêm timeMod3 cho cửa chỉ mở mỗi ba bước; cần action WAIT không?
20. Viết validator kiểm đường đi theo neighbors và tổng cost.
21. Mã hóa state (row,col,hasKey) thành id nguyên và chứng minh đơn ánh.
22. Đổi thứ tự R,D,L,U thành D,R,U,L; so path/expanded.
23. Vẽ state graph của mê cung 2×2 có khóa, so với search tree.
24. Thiết kế state cho bài lập lịch có nhiệm vụ hoàn tất (bitmask) và máy đang dùng.
25. Giải thích vì sao tối ưu thời gian có ràng buộc pin cần nhiều nhãn Pareto.
26. Đưa ra bài có hành động xác suất thất bại và lý giải vì sao cần policy thay vì path đơn.

## 19. Checklist áp dụng

- Đã định nghĩa **state đủ thông tin** cho mọi hành động tương lai chưa?
- Có tách state khỏi path và g cost chưa?
- Hành động được kiểm precondition và effect nhất quán chưa?
- Transition cost đo đúng đại lượng đề yêu cầu chưa?
- Đã phân biệt tối thiểu số bước với tối thiểu tổng cost chưa?
- Có những state cùng vị trí nhưng khác tài nguyên, khóa, thời gian không?
- Start và Goal(s) đã rõ, kể cả có nhiều goal states chưa?
- Với cost khác nhau, đã dùng Dijkstra/A* thay vì BFS chưa?
- Với A*, heuristic có thật sự là lower bound và consistent không?
- Dist/visited đã băm bằng **state đầy đủ** chưa?
- Parent được cập nhật khi có cải thiện và reconstruct đúng chưa?
- Đã tính cận kích thước state space và giới hạn bộ nhớ chưa?
- Đã kiểm đồ thị không có lời giải, cost0, overflow và các trường hợp biên chưa?
- Đã test transition bằng ví dụ tay và dùng oracle độc lập trên state graph nhỏ chưa?

## 20. Kết luận

Để giải một bài **tìm kiếm trạng thái**, cần mô hình chính xác trước khi chọn thuật toán. **State** chứa đủ thông tin quyết định tương lai; **action** là thao tác hợp lệ với precondition và effect; **transition cost** xác định đại lượng tối ưu. Những yếu tố này tạo ra đồ thị trạng thái ngầm, nơi BFS tối thiểu hóa **số hành động**, còn Dijkstra hoặc A* (với heuristic phù hợp) tối thiểu hóa **tổng chi phí không âm**.

Trên bản đồ có bùn, chìa khóa và cửa, BFS đi **8 bước, tốn 11**, trong khi Dijkstra và A* đi **10 bước, tốn 10**. Cùng tọa độ (2,2) **trước và sau khi nhặt khóa** là hai state khác nhau. Ví dụ ấy thể hiện hai quy tắc quan trọng nhất: **đừng đồng nhất số bước với tổng chi phí**, và **đừng gộp hai tình huống có khả năng hành động tương lai khác nhau vào cùng state**.
