# Hàm ước lượng (heuristic) và cận cho chi phí còn lại

Trong **tìm kiếm trạng thái**, ta thường không muốn duyệt tất cả trạng thái có thể đạt trước khi biết trạng thái nào đáng mở rộng. Với một trạng thái hiện tại s, ta đã chi một phần chi phí để đi tới s, nhưng **phần chi phí còn lại** để hoàn thành lời giải vẫn chưa biết. Một **hàm ước lượng (heuristic)** giúp đánh giá phần chưa biết ấy. Nếu hàm còn có tính chất **không bao giờ lớn hơn chi phí tối ưu thật sự còn lại**, nó trở thành một **cận dưới hợp lệ (admissible lower bound)** để chứng minh tính tối ưu và loại bỏ nhánh tìm kiếm an toàn.

Bài thuộc nhóm **Tìm kiếm trạng thái**, tập trung vào **Hàm ước lượng (heuristic) và cận cho chi phí còn lại**. Ta sẽ phân biệt heuristic bất kỳ với cận dưới đã chứng minh, xây hai thuật toán ứng dụng: **A\*** tìm đường đi ngắn nhất trên lưới bằng Manhattan distance, và **branch-and-bound** cho bài phân công tối thiểu tổng chi phí bằng phép nới lỏng ràng buộc. Bài còn giải thích tính **admissible** và **consistent**, chứng minh tại sao A* dừng đúng với heuristic thích hợp, trình bày upper bound từ lời giải khả thi, phân biệt mức độ cắt nhánh theo yêu cầu một hay mọi nghiệm, xử lý chi phí âm ở bài phân công, các lỗi phổ biến, và chương trình **Java 17+ chạy độc lập** có kết quả đầu ra kiểm chứng được.

**Mục tiêu học tập:** từ một trạng thái đang xét, tách được `g(s)` (chi phí đã đi) và `h(s)` (cận/ước lượng phần còn lại); chứng minh một cận bằng bài toán nới lỏng; hiểu điều kiện admissible và consistent không đồng nghĩa; sử dụng `f=g+h` để ưu tiên A* hoặc cắt nhánh tối ưu; dùng nghiệm khả thi tạo upper bound; kiểm nghiệm bằng oracle độc lập thay vì chỉ dựa vào tốc độ chạy.

## 1. Chi phí đã trả, chi phí còn lại và chi phí tối ưu

Xét một bài toán **tối thiểu hóa tổng chi phí** trên không gian trạng thái. Có trạng thái bắt đầu s₀, tập trạng thái đích G và những phép chuyển `s→s'` có chi phí `c(s,s')`. Ở một trạng thái s trong một đường đi đang xây dựng, đặt:

- **`g(s)`:** chi phí **đã trả** để đi từ s₀ đến s theo đường được xây/đường tốt nhất đã biết.
- **`h*(s)`:** chi phí tối ưu **thật sự còn lại** từ s đến một đích, nếu có. Đây là đại lượng chưa biết mà ta muốn ước lượng; nếu không có đường đến đích, có thể ký hiệu `h*(s)=+∞`.
- **`h(s)`:** ước lượng dựa trên thông tin dễ tính từ s, không được tùy tiện đồng nhất với h*.
- **`f(s)=g(s)+h(s)`:** tổng “đã trả + ước lượng còn lại”, dùng để xếp thứ tự hoặc làm **cận dưới** khi h được chứng minh admissible.

Nếu chi phí các bước không âm và `h(s)=0` cho mọi s, tìm kiếm theo f chính là **uniform-cost search/Dijkstra** theo g. Nếu h chứa thông tin đúng đắn, thuật toán có thể ưu tiên các trạng thái hứa hẹn hơn rất nhiều.

### Ước lượng không nhất thiết là cận an toàn

Ví dụ một người đặt heuristic “số bước còn lại ước khoảng 10” vì trực giác. Nếu thực tế có đường kết thúc trong 6 bước, h=10 **đánh giá quá cao** và không được dùng để loại bỏ nhánh khi cần nghiệm tối ưu. Nó vẫn có thể hữu ích cho tìm kiếm gần đúng, nhưng **không** có chứng minh tối ưu dựa vào h ấy.

Ngược lại, nếu chứng minh mọi lời giải từ s cần ít nhất 4 đơn vị chi phí, thì h(s)=4 là một **cận dưới an toàn**, cho dù chi phí thật là 4,7 hay 100.

**Phân biệt ba câu hỏi:**

1. “Trạng thái nào có vẻ hứa hẹn?” — có thể dùng **heuristic không bảo đảm**.
2. “Tôi có thể kết luận không bỏ sót nghiệm tối ưu không?” — cần **cận có chứng minh** và thuật toán xử lý đúng.
3. “Tôi đã có một lời giải hoàn chỉnh tốt tới đâu?” — cần **upper bound từ nghiệm khả thi**, không phải chỉ là ước lượng trên trạng thái chưa hoàn tất.

## 2. Admissible: điều kiện cốt lõi của cận dưới

Với bài **minimization**, h gọi là **admissible** khi:

**`h(s)≤h*(s)` đối với mọi trạng thái s liên quan.**

Trong các bài đường đi với chi phí cạnh không âm, ta thường chọn **`h(s)≥0`** và **`h(goal)=0`**. Hàm h=0 luôn admissible nếu chi phí còn lại không âm, nhưng gần như không hướng dẫn thêm so với Dijkstra.

Với trạng thái s có đường tới đích, ví dụ `h*(s)=8`:

| Heuristic | Admissible? | Ý nghĩa |
|---|---|---|
| `h(s)=0` | Có | Rất lỏng, không tận dụng thông tin |
| `h(s)=5` | Có | Cận dưới, còn ít nhất 5 |
| `h(s)=8` | Có | Chính xác tại s |
| `h(s)=10` | Không | Lớn hơn optimum 8, có thể loại nhầm |

Admissibility là tính chất **đối với mọi trạng thái**, không phải chỉ với trạng thái bắt đầu hoặc những ví dụ quen thuộc. Một hàm đúng trên lưới trống nhưng sai khi có **cổng dịch chuyển giá rẻ** có thể làm A* mất bảo đảm tối ưu.

### Một lower bound mạnh hơn có ích hơn thế nào?

Giả sử hai cận dưới admissible `h₁(s)` và `h₂(s)`. Nếu `h₂(s)≥h₁(s)` cho mọi trạng thái, thì `h₂` được gọi là **chi phối** (*dominates*) h₁; nó cho cận gần chi phí thật hơn hoặc bằng. Trong cùng mô hình tìm kiếm và chi phí tính h như nhau, một cận mạnh thường giúp hạn chế trạng thái cần xét.

Nhưng **chi phí tính h cũng là chi phí thuật toán**. Một lower bound rất chặt nhưng cần hàng giây để tính cho mỗi node có thể kém một cận hơi lỏng nhưng tính trong O(1).

Nếu cả h₁ và h₂ đều admissible, thì **`max(h₁,h₂)` cũng admissible**, vì cả hai đều không vượt h*. Ngược lại, **`h₁+h₂` không tự động admissible**: hai cận có thể đếm **trùng** phần chi phí bắt buộc.

## 3. Consistent (monotone): cận tương thích với phép chuyển

Trên đồ thị đường đi có chi phí cạnh không âm, một heuristic gọi là **consistent** khi với **mọi cạnh s→v**:

**`h(s)≤c(s,v)+h(v)`**, và `h(goal)=0`.

Đây là bất đẳng thức tam giác giữa “ước lượng tại s” và “đi một bước rồi ước lượng ở v”.

Nếu h consistent:

**`f(v)=g(s)+c(s,v)+h(v)≥g(s)+h(s)=f(s)`**

khi v được sinh từ s theo đường đi đã biết. Nghĩa là **f không giảm dọc theo một đường tìm kiếm**. Trong A* graph search với h consistent, khi một trạng thái được lấy khỏi hàng đợi ưu tiên ở **g tốt nhất**, nó có thể được **đóng (closed)** mà không phải mở lại: điều này cho phép một cách cài đặt đơn giản và hiệu quả.

### Consistent suy ra admissible

Giả sử h(goal)=0 và có một đường từ s tới đích với chi phí các cạnh c₁,...,c_k. Áp điều kiện consistent lần lượt:

`h(s)≤c₁+h(s₁)≤c₁+c₂+h(s₂)≤...≤Σ_i c_i+h(goal)=Σ_i c_i`.

Lấy minimum qua các đường từ s đến đích, suy ra **`h(s)≤h*(s)`**. Vì vậy với đích được chuẩn hóa h=0:

**consistent ⇒ admissible.**

Nhưng chiều ngược **không đúng**: có heuristic admissible mà vẫn inconsistent. Đây là điểm quan trọng khi dùng **closed set** để tránh xét lại trạng thái.

### Phản ví dụ admissible nhưng không consistent

Đồ thị có hướng với các cạnh và trọng số:

~~~text
S -> A  (3)       A -> G  (2)
S -> B  (1)       B -> A  (1)
                   B -> G  (100)
~~~

Tối ưu là **S→B→A→G**, tổng **4**. Đặt:

- `h(G)=0`.
- `h(A)=0`, trong khi `h*(A)=2`.
- `h(B)=3`, bằng chi phí thật từ B qua A tới G.
- `h(S)=0`.

Tất cả giá trị h đều **admissible**, nhưng ở cạnh B→A trọng số 1:

**`h(B)=3 > 1+h(A)=1`**, vi phạm consistent.

A* ban đầu mở A với g=3,f=3 và B với g=1,f=4; có thể **đóng A trước** khi tìm ra đường tốt hơn qua B. Nếu khi xử lý B, thuật toán phát hiện g(A)=2 nhưng **bỏ qua vì A đã closed**, nó sẽ giữ đường S→A→G tổng **5** và có thể trả đáp án sai.

**Cách sửa:** với heuristic **admissible nhưng inconsistent**, triển khai A* graph search cho phép **reopen** một trạng thái closed khi tìm thấy g mới **nhỏ hơn nghiêm ngặt**. Hoặc dùng heuristic consistent để đóng vĩnh viễn an toàn. Việc “h chỉ không vượt h*” **chưa đủ** cho bản A* closed-only.

## 4. A*: ưu tiên f=g+h và dừng ở đích

A* dùng một **priority queue** chứa các trạng thái được phát hiện, ưu tiên khóa:

**`f(s)=g(s)+h(s)`**.

Với mô hình cạnh không âm, h admissible, và cài đúng trạng thái trùng/đóng/mở lại, A* có thể tìm lời giải tối ưu. Bản code ở bài sử dụng **h Manhattan consistent** trên lưới bốn hướng, nên mỗi ô được closed nhiều nhất một lần.

### Vòng lặp A* cơ bản

~~~text
g[start] = 0
push(start, priority = g[start] + h(start))

while priority queue not empty:
    take state x with smallest f
    if x is a stale queue entry:
        continue
    if x is already safely CLOSED (consistent h):
        continue

    mark x CLOSED
    if x is goal:
        reconstruct path and return g[x]

    for each valid successor y of x with cost c(x,y):
        candidate = g[x] + c(x,y)
        if y not closed and candidate < g[y]:
            g[y] = candidate
            parent[y] = x
            push(y, priority = candidate + h(y))

return NO_PATH
~~~

**Quan trọng:** dòng “không xét lại y đã closed” chỉ an toàn với h **consistent** và những giả thiết tương ứng. Nếu h chỉ admissible, phải cho phép cập nhật g[y] tốt hơn và **mở lại y**; khi ấy việc bỏ qua closed vô điều kiện có thể sai như phản ví dụ mục 3.

### Vì sao không dừng ngay khi thấy goal ở hàng xóm?

Mục tiêu không chỉ là **tìm được** đường, mà là tìm **đường tối ưu**. Đường đến goal đầu tiên vừa được phát hiện có thể đắt; cần để priority queue quyết định khi nào nó là ứng viên nhỏ nhất đáng xét. Với giả thiết chuẩn, A* kết thúc khi **goal được lấy ra khỏi hàng đợi** (*popped/expanded*) ở trạng thái g tối ưu, không phải lúc mới được đưa vào queue.

### Tại sao có thể đưa cùng một trạng thái vào queue nhiều lần?

Java `PriorityQueue` không hỗ trợ decrease-key trực tiếp cho một bản ghi. Khi tìm thấy `g[y]` nhỏ hơn, ta có thể **đẩy một bản ghi mới** thay vì sửa phần tử cũ. Khi pop, bỏ bản ghi **stale** có g không bằng bestG[y] hiện tại. Cách này đúng khi kiểm tra đủ điều kiện cập nhật và h consistent cho closed-only; bộ nhớ queue có thể chứa tạm các mục cũ.

### Heuristic không phải trọng số đường đã đi

Một lỗi dễ gặp là cập nhật:

`g[y]=g[x]+h(y)`

thay vì dùng **chi phí cạnh thật** `c(x,y)`. Khi đó g không còn là chi phí của một đường hợp lệ; mọi chứng minh A* thất bại. **Heuristic chỉ thêm vào f để ưu tiên**, không được cộng thay cho chi phí chuyển trạng thái.

## 5. Manhattan distance: cận dưới cho lưới bốn hướng

Với lưới ô vuông, mỗi bước hợp lệ đi **lên, xuống, trái, phải** một ô với chi phí **1** và có thể bị chặn bởi tường `#`. Cho ô hiện tại v=(r,c) và đích goal=(r_g,c_g):

**`h_M(v)=|r−r_g|+|c−c_g|`.**

Đây là khoảng cách Manhattan.

### Chứng minh admissible

Mỗi bước bốn hướng thay đổi **tối đa một đơn vị** của một tọa độ. Để từ (r,c) tới (r_g,c_g), dù không có vật cản, ta phải thay đổi tổng cộng ít nhất:

`|r−r_g|+|c−c_g|`

đơn vị tọa độ. Tường chỉ có thể **kéo dài hoặc chặn** đường đi, không thể tạo đường ít bước hơn Manhattan. Vì vậy:

**`h_M(v)≤h*(v)`.**

Nếu không còn đường do tường, `h*(v)=+∞` và một Manhattan hữu hạn vẫn là cận dưới hợp lệ.

### Chứng minh consistent

Giữa hai ô kề nhau u→v, một bước làm thay đổi Manhattan distance **chính xác ±1** hoặc không thay đổi trong các biến thể khác, nên luôn:

`h_M(u)≤1+h_M(v)`.

Chi phí cạnh là 1, do đó h_M consistent. Tường chỉ loại bớt cạnh hợp lệ nên không thể phá bất đẳng thức trên những cạnh còn lại.

### Ví dụ không có đường đi thẳng vì vật cản

~~~text
S..#G
...#.
.....
~~~

S ở (0,0), goal ở (0,4). Heuristic tại S là **4**, vì chênh lệch cột bằng 4. Nhưng bức tường tại cột 3 ở hàng 0 và 1 buộc đường đi vòng xuống hàng 2 rồi quay lên, nên chi phí thật tối ưu là **8**. Đây là ví dụ **admissible nhưng không chính xác**:

**`h_M(S)=4≤h*(S)=8`.**

Một đường tối ưu:

~~~text
(0,0) -> (0,1) -> (0,2) -> (1,2)
      -> (2,2) -> (2,3) -> (2,4)
      -> (1,4) -> (0,4)
~~~

Có đúng 8 cạnh. A* cần xét một số trạng thái không nằm trên lời giải, nhưng vẫn cho kết quả đúng.

### Khi nào Manhattan không còn an toàn?

- **Di chuyển chéo** mỗi bước chi phí 1: từ (0,0) tới (1,1) chỉ cần **1 bước**, nhưng Manhattan =2 ⇒ **overestimate**.
- Có **teleport/portal** đi xa với giá 1 hay 0: Manhattan có thể lớn hơn chi phí thật.
- Có một số bước với chi phí nhỏ hơn 1 trên lưới: Manhattan tính theo số bước không còn là cận dưới cho **chi phí tiền tệ**.
- Có các bước chuyển trạng thái tùy ý không bị ràng buộc bởi thay đổi tọa độ 1: chứng minh cận phải được làm lại.

Một heuristic tốt phụ thuộc vào **quy tắc chuyển thật của bài toán**, không phải chỉ vào hình dạng dữ liệu.

## 6. Những cách xây lower bound có chứng minh

Một cách có hệ thống để tạo h admissible là giải **bài toán nới lỏng** (*relaxed problem*) từ trạng thái s. Ta cho phép thêm lựa chọn hoặc bỏ bớt ràng buộc, làm bài toán **dễ hơn** cho người tối ưu. Vì thế optimum của bài nới lỏng **không thể lớn hơn** optimum của bài gốc với mục tiêu minimization.

Nếu `F_original(s)` là tập lời giải hoàn chỉnh có thể từ s, và `F_relaxed(s)⊇F_original(s)`, thì:

**`min_{x∈F_relaxed(s)}cost(x)≤min_{x∈F_original(s)}cost(x)=h*(s)`.**

Do đó nghiệm tối ưu của bài nới lỏng là một **lower bound admissible**.

### Những ví dụ nới lỏng quen thuộc

1. **Lưới có tường:** bỏ mọi tường, chỉ còn khoảng cách Manhattan khi đi bốn hướng chi phí 1.
2. **8-puzzle:** tổng khoảng cách Manhattan của **các quân không phải ô trống** tới vị trí đích, khi mỗi bước đổi chỗ ô trống với đúng một quân và chi phí mỗi bước 1. Mỗi phép di chuyển chỉ đẩy một quân đi một ô, nên tổng Manhattan giảm nhiều nhất 1 mỗi bước. Đây là cận dưới cho số bước còn lại.
3. **Phân công một–một:** với các công việc còn lại, tạm bỏ ràng buộc “mỗi người/cột chỉ được chọn một lần” để mỗi hàng độc lập chọn cột rẻ nhất còn khả dụng. Tổng minima của từng hàng không lớn hơn chi phí của một phép gán thực sự.
4. **Đường đi trên đồ thị:** bỏ một số chướng ngại/giới hạn cạnh để có chi phí đường đi rẻ hơn; phải kiểm tra việc “bỏ giới hạn” thật sự làm tập lời giải nới rộng chứ không đổi bài toán thành một tối ưu khác.
5. **Bài xếp lịch:** bỏ một số xung đột tài nguyên để giải bài nhỏ hơn; tổng chi phí tối ưu sau nới lỏng là cận dưới nếu các chi phí và mục tiêu được giữ nhất quán.
6. **Bài ghép cặp có chi phí:** bỏ một số ràng buộc ghép làm tăng tập phương án có thể cho cận dưới, nhưng phải phân biệt “tối thiểu chi phí khi mọi công việc đều được gán” với “có thể chọn 0 cặp”: nếu nới lỏng cả nghĩa vụ thực hiện nhiệm vụ, cận có thể đúng nhưng gần như vô dụng.

### Kết hợp các cận

Nếu h₁,h₂ đều chứng minh admissible, có thể dùng:

**`h(s)=max(h₁(s),h₂(s))`**.

Vì mỗi h_i≤h*, max vẫn không vượt h*. Nhưng không cộng trực tiếp h₁+h₂ nếu hai cận **tính trùng chi phí**. Phép cộng chỉ an toàn khi có **cost partitioning** hoặc lập luận rõ các thành phần chi phí bắt buộc là độc lập/không trùng.

### Cận mạnh và chi phí tính cận

Heuristic h=0 thường O(1) nhưng gần như không giúp. Nới lỏng ràng buộc có thể tốn O(n²), O(n³) hoặc hơn cho mỗi trạng thái. Lợi ích thực tế phụ thuộc vào:

- Số trạng thái bớt mở rộng.
- Chi phí tính h ở mỗi trạng thái.
- Chi phí lưu bảng/memoization.
- Mức độ gần đúng của h so với h*.
- Tần suất trạng thái lặp và cách quản lý closed/dominance.

Một thuật toán tìm kiếm tốt không nhất thiết chọn **lower bound mạnh nhất có thể**, mà chọn cận đủ mạnh với **giá tính hợp lý**.

## 7. Branch-and-bound: dùng cận để loại nhánh

**Branch-and-bound** giải các bài tối ưu bằng cách giữ một **lời giải khả thi tốt nhất đã biết**, gọi là **incumbent**, và dùng cận cho những nhánh chưa xét hết.

Với bài **minimization**:

- **`UB` (upper bound)** = chi phí của **một lời giải hoàn chỉnh khả thi** đang giữ. Vì tối ưu C* không lớn hơn chi phí bất kỳ lời giải khả thi, `C*≤UB`.
- **`LB(node)` (lower bound)** = chi phí thấp nhất **có thể** đạt từ một trạng thái/nút theo cận đã chứng minh, `LB(node)≤chi phí optimum trong nhánh node`.
- Nếu **`LB(node)≥UB`**, không nhánh con nào có thể tạo lời giải **tốt hơn nghiêm ngặt** incumbent, nên có thể **cắt nhánh** khi chỉ cần **một nghiệm tối ưu**.

Thường:

**`LB(node)=g(node)+h_LB(node)`**,

trong đó g là chi phí đã cố định ở những quyết định của nhánh, còn h_LB là cận dưới cho phần chi phí còn lại.

### Vì sao cần upper bound khả thi?

Nếu UB=20 từ một lời giải thật, còn LB(node)=25, chắc chắn node không chứa nghiệm có chi phí nhỏ hơn 20. Nhưng nếu “UB=20” chỉ là **ước lượng phỏng đoán không có nghiệm**, việc cắt là **không có căn cứ**.

Có thể khởi tạo UB=+∞ và cập nhật khi gặp lời giải khả thi đầu tiên. Để cắt sớm hơn, tìm một lời giải **greedy hoàn chỉnh** rồi giữ chi phí của nó làm UB. Dù greedy có thể không tối ưu, giá trị của nó vẫn là **cận trên đúng** miễn nghiệm greedy thỏa mọi ràng buộc.

### Dấu ≥ hay > khi cắt?

- **Chỉ cần một nghiệm tối ưu:** nếu `LB≥UB`, không thể **cải thiện nghiêm ngặt** UB ⇒ cắt được.
- **Muốn liệt kê hoặc đếm mọi nghiệm có cùng chi phí tối ưu:** không thể cắt những nhánh có `LB=UB` chỉ vì đã có một nghiệm; nhánh ấy có thể chứa **nghiệm tối ưu khác**. Lúc đó thường cắt khi `LB>UB`, đồng thời quản lý việc đếm/duyệt đúng.

Đây là lý do trình phân công Java dưới đây chỉ trả **một** assignment tối ưu và có thể cắt ở dấu bằng.

### Bài toán tối đa hóa thì đảo chiều

Nếu mục tiêu **maximization** (ví dụ tối đa hóa phần thưởng), một nhánh cần **upper bound cho giá trị đạt được tối đa**; incumbent giữ **lower bound** từ một nghiệm khả thi. Có thể cắt khi upper bound nhánh ≤ giá trị khả thi tốt nhất. Không được bê nguyên điều kiện `LB≥UB` của minimization sang tối đa hóa.

## 8. Cận dưới cho bài phân công n×n

Có n người và n công việc. Mỗi người r được gán **đúng một** công việc c; mỗi công việc cũng được dùng **đúng một lần**. Chi phí gán là `cost[r][c]`, có thể là số âm (chẳng hạn xem chi phí âm là lợi ích). Mục tiêu:

**`min Σ_{r=0}^{n−1}cost[r][assign[r]]`**

với `assign` là một **hoán vị** của `0..n−1`.

### Trạng thái tìm kiếm

Ta gán người theo thứ tự hàng:

- `row` là chỉ số người tiếp theo cần gán.
- `used[c]` cho biết công việc c đã dùng trong prefix.
- `g` là tổng chi phí của những người `0..row−1` đã gán.
- `current[r]` ghi cột đang chọn cho mỗi r đã gán.
- `best` là chi phí của một hoán vị **hoàn chỉnh khả thi** đã tìm được.

Nhánh chọn một cột c chưa dùng cho người row:

**`g' = g + cost[row][c]`**, đặt used[c]=true rồi xét row+1.

Nếu chỉ dùng DFS thuần túy, trong trường hợp xấu có **n!** phép gán hoàn chỉnh. Branch-and-bound cố tìm cách chứng minh một số prefix không thể tốt hơn best để không duyệt hậu duệ.

### Lower bound bằng bỏ ràng buộc không trùng cột giữa các hàng còn lại

Với tập cột chưa dùng `U={c:used[c]=false}`, đặt:

**`h_LB(row,used)=Σ_{r=row}^{n−1} min_{c∈U} cost[r][c]`.**

Điểm quan trọng: **mỗi hàng tương lai tự lấy minimum trong cùng U**, nên phép nới lỏng **cho phép nhiều hàng cùng chọn một cột**. Điều đó **không** phải lời giải hợp lệ, nhưng nó tạo **cận dưới**.

Chứng minh: trong mọi phép gán hoàn chỉnh thật từ trạng thái hiện tại, mỗi hàng r≥row phải chọn một cột `a_r∈U` và các a_r đôi một khác nhau. Với mỗi r:

**`min_{c∈U}cost[r][c]≤cost[r][a_r]`**.

Cộng mọi hàng còn lại:

**`h_LB≤Σ_{r≥row}cost[r][a_r]`**.

Thêm chi phí prefix g:

**`LB=g+h_LB≤tổng chi phí của mọi nghiệm hoàn chỉnh thuộc nhánh`.**

Đây là chứng minh **admissible trực tiếp**, không dựa vào thử nghiệm. Phép chứng minh vẫn đúng khi một số cost[r][c] **âm**; không được tự thay số âm bằng 0 vì như vậy có thể làm cận lớn hơn chi phí thật.

### Ví dụ ma trận phân công

~~~text
          Job0 Job1 Job2 Job3
Person0      9    2    7    8
Person1      6    4    3    7
Person2      5    8    1    8
Person3      7    6    9    4
~~~

**Cận dưới ở gốc:** minimum từng hàng lần lượt là 2,3,1,4, nên:

**`LB(root)=2+3+1+4=10`.**

Nhưng các minimum này dùng Job2 cho cả Person1 lẫn Person2, nên **10 không nhất thiết khả thi**.

Một phép gán greedy theo hàng:

- Person0→Job1, chi phí 2.
- Person1→Job2, chi phí 3.
- Person2→Job0, chi phí 5.
- Person3→Job3, chi phí 4.

Tổng **14** là một **upper bound khả thi**.

Tìm kiếm tối ưu được phép cải thiện incumbent thành phép gán:

**`assign=[1,0,2,3]`**,

chi phí **`2+6+1+4=13`**. Vì mọi phương án tốt hơn 13 đã bị loại bởi cận/đã xét, kết quả tối ưu là **13**.

### Minh họa một nhánh có thể bị cắt

Giả sử đã tìm được incumbent UB=13, và prefix đã gán:

- Person0→Job1, chi phí 2.
- Person1→Job0, chi phí 6.
- Prefix g=8, cột còn lại U={Job2,Job3}.

Hai hàng còn lại có minima:

- Person2: min(1,8)=1.
- Person3: min(9,4)=4.

**`LB=8+1+4=13`.**

Nếu chỉ cần **một nghiệm tối ưu**, cắt được nhánh này vì không còn phương án **tốt hơn 13**; nó có thể chứa nghiệm bằng 13 nhưng không cần liệt kê mọi nghiệm.

Nếu mục tiêu là **đếm mọi assignment tối ưu**, phải xử lý dấu bằng khác như mục 7.

## 9. Những cách tăng sức mạnh cận cho phân công

Hàm “tổng minima từng hàng” dễ tính nhưng đôi lúc lỏng. Một số hướng cải thiện:

1. **Greedy completion UB:** thay vì chờ đến lá đầu tiên, xây ngay một assignment khả thi bằng chọn công việc rẻ nhất chưa dùng theo từng hàng. Đây là **upper bound**, không phải lower bound.
2. **Reorder branching:** thử trước các cột có chi phí nhỏ để nhanh tìm UB tốt; reorder thay đổi số node thực tế, không đổi chứng minh LB.
3. **Tighter assignment relaxation:** giải bài gán tối ưu còn lại giữa những hàng/cột chưa dùng bằng một thuật toán assignment chính xác. Giá trị ấy thậm chí là phần tối ưu thật trong phiên bản phân công thuần túy, rất chặt nhưng việc tính tại mỗi node có thể đắt.
4. **Kết hợp hai cận hợp lệ:** ví dụ một cận từ từng hàng và một cận độc lập từ từng cột có thể lấy **max** khi cả hai được chứng minh admissible. Không cộng cả hai vì dễ **đếm trùng** chi phí bắt buộc.
5. **Dominance/memoization:** nếu hai đường quyết định dẫn đến **cùng trạng thái tương lai** (chẳng hạn cùng row và mask used), giữ prefix có g nhỏ hơn; prefix g lớn hơn không thể tốt hơn trong tương lai vì các lựa chọn còn lại giống nhau. Điều này là một phép cắt khác với heuristic LB và cần quản lý trạng thái chính xác.

**Lưu ý:** nếu chi phí chỉ là ma trận phân công vuông không có ràng buộc bổ sung, các thuật toán assignment chuyên dụng như **Hungarian algorithm** thường phù hợp hơn vét cạn branch-and-bound cho n lớn. Ví dụ này dùng để dạy **cách chứng minh và khai thác cận dưới**, không đề nghị dùng factorial search thay Hungarian cho mọi bài thực tế.

## 10. Giá trị exact, ràng buộc âm và giới hạn tràn số

### Chi phí âm: chỗ A* và branch-and-bound khác nhau

Bản A* tiêu chuẩn trên đồ thị đường đi thường giả thiết **chi phí cạnh không âm**. Khi có cạnh âm hoặc chu trình âm, việc “lấy goal ra khỏi queue đầu tiên” và quy tắc đóng state cần được xem xét lại. Với chu trình âm đi tới đích, thậm chí có thể **không tồn tại đường đi ngắn nhất hữu hạn**.

Ngược lại, bài **assignment** có n quyết định, mỗi cột dùng một lần, nên không có chu trình vô hạn trong cây quyết định. Cost của một cặp có thể âm mà phép nới lỏng minima vẫn cho lower bound hợp lệ; tổng có thể âm như `−13`. Không được áp quy tắc “h≥0” từ bài đường đi không âm vào bài tối ưu có chi phí âm.

### Tràn số

Nếu chi phí lưu bằng long, các phép tính `g+cost`, `g+h` hoặc tổng các minima có thể vượt miền biểu diễn 64-bit. Java thực hiện phép cộng long thông thường bằng **wraparound** khi tràn, khiến so sánh cận sai và có thể cắt nghiệm tối ưu.

Bản minh họa:

- Dùng **long** cho chi phí/đáp án.
- Dùng **Math.addExact** khi cộng chi phí hoặc lower bound để phát hiện tràn và ném `ArithmeticException` thay vì âm thầm tính sai.
- Với lưới kích thước thực tế, chi phí bước là 1, nhưng vẫn dùng long cho g/f để rõ ràng.
- Nếu đầu vào cần tổng toán học lớn hơn long, phải thay kiểu số bằng **BigInteger** và điều chỉnh dữ liệu tương ứng; không được bỏ kiểm soát tràn rồi tin kết quả.

Một nhánh tính lower bound tràn có thể bị từ chối ngay cả khi nghiệm tối ưu thật nằm trong long: đó là **giới hạn của API** này, không phải kết luận bài toán bất khả thi. Với ma trận lớn, cần thiết kế số học cho toàn bộ miền chi phí có thể xuất hiện.

## 11. Java 17+ chạy độc lập: A* lưới và assignment branch-and-bound

Một chương trình duy nhất triển khai **hai trường hợp có chứng minh cận**. Đây là hai ví dụ mục tiêu khác nhau nhưng chung tư duy “chi phí đã biết + cận cho phần còn lại”:

- **Grid A\*:** các ký tự `S` (start), `G` (goal), `.` (ô đi được), `#` (tường); bước theo bốn hướng, mỗi bước có chi phí 1. Heuristic **Manhattan** vừa admissible vừa consistent. Trả **khoảng cách**, **danh sách tọa độ của một đường tối ưu**, và số ô thực sự được lấy ra xử lý `expanded`.
- **Assignment BnB:** ma trận vuông `long[][] cost`, tất cả cách gán người–việc đều được phép, mỗi người một việc và mỗi việc một người. Ban đầu tìm một nghiệm **greedy khả thi** để có upper bound. Dùng lower bound **tổng minima của các hàng chưa gán trên những cột còn trống** để cắt nhánh. Trả **chi phí tối ưu**, **các cột đã chọn theo hàng**, số node DFS `explored` và số node bị cắt `pruned`.

**Bản A\*** dùng `closed[][]` an toàn vì Manhattan consistent cho bốn hướng với chi phí 1; không dùng nguyên logic này cho heuristic admissible nhưng inconsistent. **Bản BnB** có thể có chi phí âm vì cây quyết định hữu hạn; chỉ dùng phép cộng có kiểm tra tràn. Với input không hợp lệ, chương trình ném `IllegalArgumentException`.

Lưu thành **`HeuristicBoundsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public final class HeuristicBoundsDemo {
    private record Cell(int row, int col, long g, long f) {}

    private record GridResult(
            long distance, List<String> path, int expanded) {}

    private record AssignmentResult(
            long cost, List<Integer> columns,
            long explored, long pruned) {}

    private static long manhattan(
            int row, int col, int goalRow, int goalCol) {
        return Math.abs((long) row - goalRow)
                + Math.abs((long) col - goalCol);
    }

    static GridResult aStar(String[] lines) {
        if (lines == null || lines.length == 0
                || lines[0] == null || lines[0].isEmpty()) {
            throw new IllegalArgumentException("Invalid grid");
        }

        int height = lines.length;
        int width = lines[0].length();
        char[][] grid = new char[height][width];
        int startRow = -1, startCol = -1;
        int goalRow = -1, goalCol = -1;
        int starts = 0, goals = 0;

        for (int r = 0; r < height; r++) {
            if (lines[r] == null || lines[r].length() != width) {
                throw new IllegalArgumentException(
                        "Grid must be rectangular");
            }
            for (int c = 0; c < width; c++) {
                char ch = lines[r].charAt(c);
                if (ch != '.' && ch != '#'
                        && ch != 'S' && ch != 'G') {
                    throw new IllegalArgumentException(
                            "Unknown grid character");
                }
                grid[r][c] = ch;
                if (ch == 'S') {
                    starts++;
                    startRow = r;
                    startCol = c;
                } else if (ch == 'G') {
                    goals++;
                    goalRow = r;
                    goalCol = c;
                }
            }
        }
        if (starts != 1 || goals != 1) {
            throw new IllegalArgumentException(
                    "Require exactly one S and one G");
        }

        long[][] bestG = new long[height][width];
        int[][] parentRow = new int[height][width];
        int[][] parentCol = new int[height][width];
        boolean[][] closed = new boolean[height][width];

        for (int r = 0; r < height; r++) {
            Arrays.fill(bestG[r], Long.MAX_VALUE);
            Arrays.fill(parentRow[r], -1);
            Arrays.fill(parentCol[r], -1);
        }

        Comparator<Cell> order = (a, b) -> {
            int x = Long.compare(a.f(), b.f());
            if (x != 0) return x;
            x = Long.compare(b.g(), a.g()); // Higher g on equal f.
            if (x != 0) return x;
            x = Integer.compare(a.row(), b.row());
            return x != 0 ? x
                    : Integer.compare(a.col(), b.col());
        };
        PriorityQueue<Cell> open = new PriorityQueue<>(order);

        bestG[startRow][startCol] = 0L;
        open.add(new Cell(startRow, startCol, 0L,
                manhattan(startRow, startCol, goalRow, goalCol)));

        int expanded = 0;
        int[][] moves = {
            {-1, 0}, {0, 1}, {1, 0}, {0, -1}
        };

        while (!open.isEmpty()) {
            Cell node = open.remove();
            int r = node.row(), c = node.col();

            // A new better g may have superseded this heap entry.
            if (node.g() != bestG[r][c] || closed[r][c]) {
                continue;
            }
            closed[r][c] = true;
            expanded++;

            if (r == goalRow && c == goalCol) {
                List<String> path = new ArrayList<>();
                int pr = r, pc = c;
                while (true) {
                    path.add("(" + pr + "," + pc + ")");
                    if (pr == startRow && pc == startCol) {
                        break;
                    }
                    int nr = parentRow[pr][pc];
                    int nc = parentCol[pr][pc];
                    if (nr < 0 || nc < 0) {
                        throw new IllegalStateException(
                                "Broken A* parent path");
                    }
                    pr = nr;
                    pc = nc;
                }
                Collections.reverse(path);
                return new GridResult(
                        node.g(), List.copyOf(path), expanded);
            }

            for (int[] move : moves) {
                int nr = r + move[0];
                int nc = c + move[1];
                if (nr < 0 || nr >= height
                        || nc < 0 || nc >= width
                        || grid[nr][nc] == '#'
                        || closed[nr][nc]) {
                    continue;
                }

                long newG = Math.addExact(node.g(), 1L);
                if (newG < bestG[nr][nc]) {
                    bestG[nr][nc] = newG;
                    parentRow[nr][nc] = r;
                    parentCol[nr][nc] = c;
                    long newF = Math.addExact(newG,
                            manhattan(nr, nc, goalRow, goalCol));
                    open.add(new Cell(nr, nc, newG, newF));
                }
            }
        }
        return new GridResult(-1L, List.of(), expanded);
    }

    private static final class AssignmentSolver {
        private final int n;
        private final long[][] cost;
        private final boolean[] used;
        private final int[] current;
        private final int[] bestColumns;
        private long best;
        private long explored;
        private long pruned;

        AssignmentSolver(long[][] input) {
            if (input == null || input.length == 0) {
                throw new IllegalArgumentException(
                        "Assignment matrix must be nonempty");
            }
            n = input.length;
            cost = new long[n][n];
            for (int r = 0; r < n; r++) {
                if (input[r] == null || input[r].length != n) {
                    throw new IllegalArgumentException(
                            "Require a square cost matrix");
                }
                cost[r] = input[r].clone();
            }
            used = new boolean[n];
            current = new int[n];
            bestColumns = new int[n];

            // A complete GREEDY assignment: a valid upper bound.
            boolean[] greedyUsed = new boolean[n];
            long initial = 0L;
            for (int r = 0; r < n; r++) {
                int chosen = -1;
                for (int c = 0; c < n; c++) {
                    if (!greedyUsed[c]
                            && (chosen == -1
                                || cost[r][c] < cost[r][chosen])) {
                        chosen = c;
                    }
                }
                greedyUsed[chosen] = true;
                bestColumns[r] = chosen;
                initial = Math.addExact(initial, cost[r][chosen]);
            }
            best = initial;
        }

        // Lower bound: allow remaining rows to reuse columns.
        // Reusing columns makes the relaxation CHEAPER (or equal).
        private long lowerBound(int row, long spent) {
            long result = spent;
            for (int r = row; r < n; r++) {
                boolean found = false;
                long minCost = 0L;
                for (int c = 0; c < n; c++) {
                    if (!used[c] && (!found
                            || cost[r][c] < minCost)) {
                        minCost = cost[r][c];
                        found = true;
                    }
                }
                if (!found) {
                    throw new IllegalStateException(
                            "No available column");
                }
                result = Math.addExact(result, minCost);
            }
            return result;
        }

        private void dfs(int row, long spent) {
            explored++;
            long bound = lowerBound(row, spent);
            if (bound >= best) {
                pruned++;
                return; // Only ONE optimum is required.
            }
            if (row == n) {
                best = spent;
                System.arraycopy(
                        current, 0, bestColumns, 0, n);
                return;
            }

            for (int c = 0; c < n; c++) {
                if (used[c]) {
                    continue;
                }
                used[c] = true;
                current[row] = c;
                dfs(row + 1,
                        Math.addExact(spent, cost[row][c]));
                used[c] = false;
            }
        }

        AssignmentResult run() {
            dfs(0, 0L);
            List<Integer> columns = new ArrayList<>();
            for (int col : bestColumns) {
                columns.add(col);
            }
            return new AssignmentResult(best,
                    List.copyOf(columns), explored, pruned);
        }
    }

    static AssignmentResult assign(long[][] cost) {
        return new AssignmentSolver(cost).run();
    }

    private static void showGrid(String name, String... grid) {
        GridResult r = aStar(grid);
        System.out.println(name + ": distance=" + r.distance()
                + ", path=" + r.path()
                + ", expanded=" + r.expanded());
    }

    private static void showAssignment(
            String name, long[][] cost) {
        AssignmentResult r = assign(cost);
        System.out.println(name + ": cost=" + r.cost()
                + ", columns=" + r.columns()
                + ", explored=" + r.explored()
                + ", pruned=" + r.pruned());
    }

    public static void main(String[] args) {
        showGrid("Open",
                "S...",
                ".##.",
                "...G");

        showGrid("Detour",
                "S..#G",
                "...#.",
                ".....");

        showGrid("Blocked",
                "S#G",
                "###",
                "...");

        showGrid("Direct", "S.G");

        showGrid("Narrow",
                "S#..G",
                ".#.#.",
                "...#.");

        showAssignment("Classic", new long[][] {
            {9, 2, 7, 8},
            {6, 4, 3, 7},
            {5, 8, 1, 8},
            {7, 6, 9, 4}
        });

        showAssignment("Negative", new long[][] {
            {-5, 4, 3},
            { 2,-6, 1},
            { 4, 3,-2}
        });

        showAssignment("Ties", new long[][] {
            {1, 1},
            {1, 1}
        });

        showAssignment("Single", new long[][] {
            {7}
        });

        showAssignment("Greedy trap", new long[][] {
            {1,   2},
            {2, 100}
        });

        showAssignment("Mixed", new long[][] {
            { 0, 3,-1},
            { 2,-2, 1},
            {-3, 4, 2}
        });
    }
}
~~~

Biên dịch/chạy với **JDK 17 hoặc mới hơn**:

~~~bash
javac HeuristicBoundsDemo.java
java HeuristicBoundsDemo
~~~

**Stdout chính xác** với thứ tự láng giềng lên–phải–xuống–trái và comparator `(f tăng, g giảm, row tăng, col tăng)` trong mã:

~~~text
Open: distance=5, path=[(0,0), (0,1), (0,2), (0,3), (1,3), (2,3)], expanded=6
Detour: distance=8, path=[(0,0), (0,1), (0,2), (1,2), (2,2), (2,3), (2,4), (1,4), (0,4)], expanded=11
Blocked: distance=-1, path=[], expanded=1
Direct: distance=2, path=[(0,0), (0,1), (0,2)], expanded=3
Narrow: distance=8, path=[(0,0), (1,0), (2,0), (2,1), (2,2), (1,2), (0,2), (0,3), (0,4)], expanded=9
Classic: cost=13, columns=[1, 0, 2, 3], explored=11, pruned=6
Negative: cost=-13, columns=[0, 1, 2], explored=1, pruned=1
Ties: cost=2, columns=[0, 1], explored=1, pruned=1
Single: cost=7, columns=[0], explored=1, pruned=1
Greedy trap: cost=4, columns=[1, 0], explored=4, pruned=1
Mixed: cost=-6, columns=[2, 1, 0], explored=1, pruned=1
~~~

### Đọc output A* như thế nào?

- **Open:** Manhattan từ S tới G là 5; tồn tại một đường hợp lệ dài 5 nên h chính xác ngay tại nguồn. A* mở 6 ô, tính cả start và goal.
- **Detour:** h tại start chỉ bằng 4 nhưng đường thực phải vòng qua hàng dưới, dài 8. Tường làm heuristic lỏng, không làm nó overestimate.
- **Blocked:** goal bị tách hoàn toàn; A* chỉ mở S và hết queue, trả distance=−1, path rỗng. **−1 là ký hiệu không có đường**, không phải chi phí âm.
- **Direct:** một hàng có S.G, cách nhau 2 bước, kết quả path chứa 3 ô.
- **Narrow:** hành lang bắt buộc đi xuống, vòng sang phải rồi lên; đường trả ra 8 bước. Lưu tọa độ parent khi g cải thiện giúp dựng đường đầy đủ.

Số `expanded` phụ thuộc vào cách phá hòa của priority queue, nên không phải đặc trưng bất biến của bài toán. Cả hai đường tối ưu khác nhau có thể có cùng distance; mã chỉ trả **một** đường theo thứ tự đã định.

### Đọc output branch-and-bound như thế nào?

- **Classic:** greedy trước tìm upper bound 14; DFS dùng LB để chứng minh cost tối ưu là **13** với phép gán [1,0,2,3].
- **Negative:** ba cặp đường chéo có chi phí −5, −6, −2, tổng **−13**. Greedy đã đạt tối ưu; lower bound ở gốc cũng −13 nên DFS có thể cắt ngay mà vẫn đúng.
- **Ties:** hai người và hai công việc đều có chi phí 1. Có **hai assignment tối ưu** cùng tổng 2, nhưng bài chỉ yêu cầu một nên cắt nhánh dấu bằng và in [0,1].
- **Single:** một người/một việc, nghiệm duy nhất có cost 7. Một node ở gốc đã đủ khi greedy và LB bằng nhau.
- **Greedy trap:** ma trận [[1,2],[2,100]]; greedy chọn 1 trước rồi bị buộc dùng 100 ⇒ **101**, trong khi assignment [1,0] có tổng **2+2=4**. Vì LB ở gốc <101, DFS khám phá và sửa được nghiệm ban đầu.
- **Mixed:** có chi phí âm, phép gán [2,1,0] cho tổng −1+(−2)+(−3)=**−6**.

Giá trị `explored` đếm mọi lần đi vào dfs, kể cả node lập tức bị cắt. `pruned` đếm node bị loại khi `LB≥best`; nó **không** phải số nghiệm hoàn chỉnh bị bỏ và không xác nhận có bao nhiêu lời giải tối ưu.

### Vì sao A* không cần reopen trong code?

Tính consistent của Manhattan trong lưới bốn hướng chi phí 1 bảo đảm mỗi ô được pop với g tối ưu trước khi closed. Nếu thay heuristic bằng thứ khác chỉ admissible mà inconsistent, phải sửa cả điều kiện closed và xử lý heap; không được chỉ thay hàm manhattan rồi giữ nguyên thuật toán.

### Vì sao solver assignment cắt ở gốc có thể là đúng?

Nếu greedy đã tìm nghiệm chi phí U, và lower bound tại gốc cũng bằng U, thì:

**`LB(root)≤C*≤UB=U`**.

Hai cận bằng nhau ⇒ `C*=U`. Không cần mở thêm node nào để chứng minh tối ưu. Điều này không có nghĩa greedy **luôn** tối ưu: ví dụ Greedy trap cho thấy upper bound ban đầu có thể rất lỏng.

## 12. Phân tích độ phức tạp

### A* trên lưới R×C bốn hướng

Số trạng thái tối đa **`V=R·C`**, mỗi ô có tối đa 4 cạnh nên **`E=O(V)`**.

Trong phiên bản Manhattan consistent:

- Mỗi ô được mở rộng nhiều nhất một lần; số cạnh xét O(E).
- Với `PriorityQueue` và bản ghi trùng/stale, có O(E) lần thêm, mỗi lần O(log E) trong cận tổng quát. Trên lưới, E=O(V).
- **Thời gian `O(RC·log(RC))`** trong cận xấu nhất của code.
- **Bộ nhớ `O(RC)`** cho grid, bestG, parent, closed và các mục heap.

Nếu heuristic h=0, trên lưới unit cost, có thể dùng **BFS** đơn giản với thời gian O(RC) để tìm khoảng cách ngắn nhất. Do đó A* không tự động tốt hơn BFS trên mọi lưới; lợi ích phụ thuộc số ô nó tránh mở rộng nhờ h.

Trên không gian trạng thái ngầm rất lớn (puzzle, planning), số trạng thái đạt được có thể tăng **theo hàm mũ** của độ sâu lời giải; O(E log E) chỉ mô tả chi phí theo **số trạng thái/cạnh thực sự được biểu diễn**, không có nghĩa A* luôn là thuật toán thời gian đa thức theo độ dài mô tả puzzle.

### Branch-and-bound phân công n×n

- Có n! phép gán đầy đủ nếu không cắt nhánh.
- Tại độ sâu row, cận `lowerBound` duyệt những hàng chưa gán và những cột chưa dùng, tốn tối đa O(n²).
- Số node DFS trong trường hợp xấu là `1+n+n(n−1)+...+n! = O(n!)` theo bậc tiệm cận.
- Do đó cận bảo thủ là **`O(n²·n!)`** thời gian (ngoài O(n²) sao chép/input/greedy).
- Bộ nhớ **`O(n²)`** lưu ma trận cộng O(n) cho used, current, bestColumns và đệ quy.

Branch-and-bound **không** có bảo đảm chạy nhanh cho mọi chi phí. Lower bound lỏng có thể khiến hầu như mọi node vẫn phải được xét. Trái lại, một bài mà LB gốc bằng nghiệm greedy sẽ được chứng minh ngay, như Negative/Ties/Single trong stdout.

### Chi phí tính h cũng phải tính

Nếu mỗi lần sinh node cần chạy một thuật toán O(n³) để tính heuristic mạnh hơn, thời gian total phải nhân theo số lần đánh giá h, không thể chỉ đếm số node bị cắt. Khi so hai heuristic, nên ghi cả **expanded nodes, time per bound, total runtime, peak memory** và xác nhận cả hai vẫn trả cùng optimum.

## 13. Dominance, duplicate states và memoization

### Trạng thái lặp trong A*

Hai đường khác nhau có thể dẫn tới **cùng một ô** hoặc cùng cấu hình puzzle. Nếu cùng state s được tới với g=10 và g=7, phần chi phí còn lại từ s **không phụ thuộc đường trước đó** (giả thiết Markov cho bài toán). Vì vậy đường có g=10 bị **dominated** bởi đường g=7: nó không thể tạo lời giải tốt hơn từ s nếu các hành động còn lại như nhau.

A* lưu **bestG[state]** để chỉ cập nhật khi gặp g nhỏ hơn. Với h consistent, khi state đã closed ở g tối ưu, bỏ mọi đường đi tới state về sau là an toàn.

Nếu bài toán có ràng buộc phụ thuộc **lịch sử** — ví dụ đã dùng một khóa chưa, còn bao nhiêu nhiên liệu, đã thăm một đỉnh đặc biệt hay chưa — chỉ lưu vị trí (r,c) **không đủ mô tả state**. Phải đưa thông tin ấy vào khóa trạng thái; nếu không phép loại trùng/dominance có thể cắt đường hợp lệ.

### Trạng thái lặp trong assignment

Hai thứ tự quyết định khác nhau có thể dẫn tới **cùng tập cột đã dùng** và cùng tập hàng còn lại, dù chi phí prefix khác nhau. Nếu định nghĩa state chỉ bằng `(row,usedMask)`, ta có thể memo hóa chi phí g tốt nhất đã tới state; một lần tới state với g lớn hơn bị dominated.

Trong ví dụ gán theo thứ tự **hàng tăng cố định**, mọi state (row, usedMask) có thể gặp nhiều cách gán các hàng trước đó. Memoization có thể giảm công việc, nhưng phải cài đúng bằng khóa gồm **tập cột đã dùng**; không thể chỉ dùng row.

**Không nhầm:** một cận LB thông tin thấp và một phép dominance có nguyên lý khác nhau. LB so nhánh với incumbent toàn cục; dominance so hai đường đến **cùng trạng thái tương lai**.

## 14. Chứng minh tính đúng của cắt nhánh và kết thúc

### Branch-and-bound

Giữ invariant: `best` là chi phí của **một phép gán hoàn chỉnh khả thi**, nên luôn `C*≤best`.

Ở node N, mọi lời giải trong nhánh đều có:

`totalCost≥LB(N)`.

Nếu `LB(N)≥best`, thì mọi lời giải trong nhánh có cost≥best, không thể cải thiện incumbent. Cắt nhánh **không bỏ sót nghiệm có cost nhỏ hơn best**.

Nếu không cắt, thuật toán thử mọi cột chưa dùng cho hàng hiện tại, nên không bỏ sót lựa chọn hợp lệ. Vì cây quyết định hữu hạn, DFS kết thúc. Khi không còn nhánh nào chưa xét, mọi nghiệm chưa được sinh đã bị chứng minh không thể tốt hơn incumbent. Do đó `best=C*`.

**Dấu bằng và nghiệm đồng hạng:** nếu cần **một optimum** thì cắt `LB≥best` hợp lệ. Nếu cần **mọi optimum**, chứng minh trên chỉ bảo đảm không bỏ sót nghiệm **tốt hơn**, không bảo đảm giữ lại nghiệm **bằng** best.

### A* với consistent h

Gọi C* là chi phí tối ưu tới goal. Trên mọi đường đi tối ưu từ start đến goal, với node x:

**`g_opt(x)+h(x)≤g_opt(x)+h*(x)≤C*`**,

nếu h admissible.

A* luôn pop node có f nhỏ nhất trong open. Với h consistent, khi node x được pop lần đầu và closed, g(x) là chi phí tối ưu để tới x; không có đường tốt hơn xuất hiện về sau. Khi goal được pop, h(goal)=0 nên `f(goal)=g(goal)`. Nếu g(goal)>C*, vẫn phải có một node trên đường tối ưu chưa mở rộng với f≤C*<g(goal), mâu thuẫn việc goal có f nhỏ nhất. Vì vậy g(goal)=C*.

Lập luận này phụ thuộc cả:

- **h admissible** để tạo f không vượt chi phí tối ưu trên đường đi.
- **h consistent** để cho phép permanently closed mà không reopen.
- **Chi phí cạnh không âm** và xử lý g/queue chính xác trong phiên bản tiêu chuẩn.
- **Mô hình trạng thái đầy đủ** sao cho cost-to-go chỉ phụ thuộc state.

## 15. Các tình huống dễ làm heuristic sai

### 15.1. Thay đổi luật di chuyển

Manhattan h đúng cho bước bốn hướng chi phí 1, nhưng nếu cho một bước chéo chi phí 1 thì h(0,0→1,1)=2 vượt optimum 1. Nếu đường chéo chi phí √2 và bước thẳng chi phí 1, có thể nghiên cứu **octile distance** làm cận thích hợp, nhưng phải chứng minh theo các phép chuyển hợp lệ; không bê nguyên công thức Manhattan.

### 15.2. Các đỉnh có thể không đạt đích

Heuristic hữu hạn vẫn có thể admissible trên trạng thái không có đường tới goal, vì h*=+∞. A* phải nhận biết **hàng đợi hết mà chưa pop goal** và báo “không có đường”, không lấy h lớn làm dấu hiệu tự suy ra không thể đạt.

### 15.3. Hàm h dự đoán bằng học máy

Một mô hình dự đoán learned heuristic có thể khá chính xác **trung bình** nhưng đôi lúc overestimate. Nếu cần nghiệm tối ưu, không được dùng trực tiếp nó làm **cận an toàn** khi chưa có chứng minh hoặc cơ chế hiệu chỉnh bảo đảm. Có thể dùng để **sắp thứ tự thử nhánh** trong branch-and-bound mà vẫn giữ một lower bound riêng để quyết định prune.

### 15.4. Nhầm “minima các hàng” với một assignment khả thi

Trong assignment, tổng minima từng hàng có thể lấy **cùng một cột nhiều lần**; nó chỉ là **relaxed lower bound**. Không được lấy danh sách lựa chọn theo row minima làm **incumbent upper bound** vì vi phạm ràng buộc “mỗi cột dùng một lần”. Muốn upper bound, phải xây **một hoán vị** hoàn chỉnh.

### 15.5. Cận cũ khi trạng thái thay đổi

Nếu bài toán có tài nguyên đã dùng, chi phí còn lại phụ thuộc vào chúng. Cận cho trạng thái trước khi dùng tài nguyên **không tự động** vẫn đúng cho trạng thái sau nếu không cập nhật miền lựa chọn. Trong assignment, phải tính minima trên **cột chưa dùng** tại node hiện tại; nếu lấy nhầm từ tập cột không phù hợp, cận có thể quá cao và cắt sai.

### 15.6. So sánh số thực với epsilon

Nếu chi phí/h là số thực, sai số tính toán có thể khiến LB hơi lớn hơn giá trị thật hoặc so sánh `LB≥UB` nhầm. Một chương trình đòi tối ưu chính xác nên dùng integer/rational có chứng minh, hoặc quy tắc làm tròn bảo thủ theo **chiều không làm tăng LB**; việc thêm epsilon tùy tiện cũng cần phân tích. Bản Java dùng long và `Math.addExact` để tránh sai số floating point, đổi lại có giới hạn miền số.

## 16. Kiểm thử độc lập: BFS và vét cạn hoán vị

Một cài heuristic có thể **rất nhanh nhưng sai**, nhất là khi lower bound vô tình overestimate khiến branch-and-bound cắt mất nhánh tối ưu. Vì vậy bài cần **oracle độc lập**.

### 16.1. Kiểm A* bằng BFS lưới không trọng số

Với lưới nhỏ có S,G và tường, chạy một thuật toán **BFS bình thường** từ S, không dùng h:

- Queue chứa các ô chưa thăm theo số bước.
- Mỗi ô hợp lệ bốn hướng có cost 1.
- Khi BFS tới goal, khoảng cách của goal là số bước tối thiểu.
- Nếu queue cạn không thấy goal, trả −1.

Đối chiếu:

**`AStarDistance == BFSDistance`**.

Ngoài số bước, kiểm:

- Path bắt đầu ở S, kết thúc ở G.
- Mỗi cặp ô liên tiếp là hàng xóm bốn hướng không bị tường.
- **`path.size()−1=distance`** nếu reachable.
- Nếu unreachable, path rỗng.
- Hệ thống bestG/closed không cho một ô mở rộng nhiều lần với consistent h.

Có thể sinh random lưới 1..9 hàng, 2..10 cột, tường với xác suất ~30%, chọn S,G khác nhau. Thử cả hành lang bắt buộc vòng dài, lưới trống, goal hoàn toàn bị chặn, và tie nhiều đường tối ưu.

### 16.2. Kiểm branch-and-bound bằng duyệt mọi hoán vị

Với ma trận n nhỏ (1..7), sinh mọi hoán vị `assign` và tính:

**`min_{permutation assign} Σ_r cost[r][assign[r]]`**.

Thuật toán brute-force này không dùng LB, heuristic hay greedy; nó chắc chắn xét mọi nghiệm khả thi. Kiểm:

- `BnBCost == BruteMinCost`.
- `columns` có đúng n phần tử, chứa mỗi cột 0..n−1 đúng một lần.
- Tổng chi phí của columns in ra bằng **BnBCost**.
- Kết quả đúng với chi phí âm, số 0 và nhiều nghiệm bằng nhau.
- Khi greedy trap, code phải cải thiện được upper bound ban đầu.
- Khi LB(root)==UB ban đầu, code có thể cắt ngay mà vẫn đúng.
- Với input không vuông hoặc null, code phải từ chối đúng hợp đồng.

Duyệt hoán vị n≤7 có tối đa **7!=5040** nghiệm mỗi test, phù hợp kiểm thử tự động ngẫu nhiên nhỏ.

### 16.3. Các invariant nên kiểm khi debug

**A\*:**

- `bestG[start]=0`.
- Mọi bản ghi heap đang xét có f=g+h, và h không âm trên lưới chuẩn.
- Không cập nhật g bằng h thay cho cost cạnh.
- Với h consistent, mỗi ô closed không cần reopen và không có đường tốt hơn xuất hiện sau.
- Khi goal được pop, path parent tạo chuỗi hợp lệ có đúng g bước.

**BnB:**

- `used[c]` đúng với prefix `current[0..row−1]`.
- `bestColumns` luôn là **hoán vị hoàn chỉnh khả thi**.
- `best` đúng bằng chi phí của bestColumns.
- `LB≤cost` của **mọi completion** trong nhánh, kiểm được bằng brute-force trên node nhỏ.
- Nếu prune vì `LB≥best`, không completion nào có cost<best.
- Sau mỗi lần quay lui, used được trả về trạng thái trước đó.
- Mọi phép cộng long có kiểm tra tràn.

## 17. Phân biệt những tên heuristic thường gặp

| Tên | Đặc điểm chính | Dùng khi nào |
|---|---|---|
| `h=0` | Cận yếu nhưng an toàn nếu chi phí còn lại không âm | Baseline A*/Dijkstra |
| Manhattan | Tổng chênh lệch hàng+cột; admissible và consistent trên lưới 4 hướng unit cost | Lưới tọa độ, 8-puzzle theo luật chuẩn |
| Euclidean | Khoảng cách đường thẳng; cần kiểm đơn vị chi phí cạnh | Di chuyển hình học có chi phí tối thiểu theo độ dài |
| Octile | Cận cho một số lưới 8 hướng với chi phí thẳng/chéo phù hợp | Lưới 8 hướng, khi đã chứng minh điều kiện |
| Pattern database | Lưu chi phí tối ưu của một bài toán trừu tượng/nới lỏng | Puzzle lớn, tiền xử lý và RAM cho phép |
| Row minima relaxation | Tổng chi phí rẻ nhất từng hàng còn lại, bỏ tính khác nhau giữa cột | Branch-and-bound assignment |
| Feasible greedy completion | Tạo lời giải thật hoàn chỉnh, là **upper bound** trong minimization | Khởi tạo incumbent để cắt sớm |
| Learned heuristic | Ước lượng dựa trên dữ liệu, có thể sai lệch | Tìm kiếm thực dụng; cần chứng minh nếu dùng để prune tối ưu |

**Không đánh giá “heuristic tốt” chỉ bằng việc cho số lớn.** Một lower bound càng gần h* càng mạnh **trong miền hợp lệ**, nhưng vượt h* dù ở một trạng thái cũng có thể phá cam kết tối ưu.

## 18. Lỗi phổ biến khi học cận còn lại

1. **Gọi mọi ước lượng là lower bound:** muốn prune tối ưu phải chứng minh `h≤h*`.
2. **Nhầm h với g:** h là phần chưa trả, g là chi phí đã trả.
3. **Cộng h vào g khi cập nhật g kế tiếp:** chi phí đường đi thật chỉ cộng **cost cạnh**.
4. **Dùng Manhattan cho bước chéo cost1:** heuristic có thể overestimate.
5. **Không xét vật cản là làm h sai:** vật cản chỉ có thể làm đường dài thêm; Manhattan vẫn là cận dưới trên lưới đúng luật.
6. **Cho rằng admissible tự động consistent:** phản ví dụ ở B→A đã chứng minh sai.
7. **Closed vĩnh viễn với h inconsistent mà không reopen:** có thể trả đường không tối ưu.
8. **Dừng A* khi goal mới được phát hiện:** phải theo quy tắc pop an toàn.
9. **Không bỏ heap entry stale:** có thể xét lại trạng thái theo g cũ.
10. **Dùng PriorityQueue nhưng giả định có decrease-key tự động:** Java không tự cập nhật vị trí phần tử khi giá trị ngoài heap thay đổi.
11. **Không đưa tài nguyên/quy tắc lịch sử vào state:** loại trùng sai vì hai trạng thái cùng vị trí nhưng khả năng tương lai khác nhau.
12. **Cộng hai admissible heuristic không có chứng minh disjoint:** có thể double-count chi phí.
13. **Tưởng relaxed minima là assignment hợp lệ:** nhiều hàng có thể chọn cùng cột trong cận.
14. **Dùng relaxed minima làm upper bound:** chưa phải lời giải khả thi.
15. **Dùng heuristic learned để prune mà không có guarantee:** có thể loại nghiệm tối ưu.
16. **Cắt branch-and-bound khi LB≤UB:** đây là trường hợp nhánh vẫn có thể cải thiện; đúng phải cắt khi LB≥UB cho một optimum.
17. **Cắt ở dấu bằng khi phải đếm tất cả optimum:** mất nghiệm đồng hạng.
18. **Quên rằng minimization và maximization đảo hướng cận:** prune sai.
19. **Ép h không âm trong assignment có cost âm:** có thể làm lower bound quá cao.
20. **Không khôi phục used khi backtrack:** các nhánh sau sai.
21. **Không khởi tạo incumbent bằng một nghiệm thật:** cắt không có chứng nhận.
22. **Không kiểm tra tràn long:** làm h hoặc g đảo dấu giả.
23. **Lấy g(goal) của một đường bất kỳ làm C* khi chưa chạy hết logic A*:** chưa có chứng minh tối ưu.
24. **Phân tích số node mà bỏ qua chi phí tính h:** thuật toán có thể chậm dù ít node.
25. **Dùng A* cho đồ thị âm như lưới chi phí dương:** giả thiết không còn.
26. **Đánh giá A* tốt nhất trên mọi grid:** BFS O(RC) có thể hiệu quả hơn khi h không hữu ích.
27. **Cho rằng BnB luôn nhanh hơn n!:** trong trường hợp xấu cận lỏng vẫn phải gần vét cạn.
28. **Chỉ kiểm output của thuật toán với chính nó:** cần oracle BFS và brute-force permutation.
29. **Không phân biệt heuristic ưu tiên với bound dùng prune:** một estimate không an toàn vẫn có thể dùng cho thứ tự nhưng không cho chứng minh tối ưu.
30. **Không chứng minh các phép nới lỏng giữ nguyên hướng bất đẳng thức:** bỏ ràng buộc trong minimization cho cận dưới; với maximization hướng khác.

## 19. Checklist trước khi nộp

- Đã mô tả chính xác **state**, hành động chuyển, cost thật và điều kiện goal?
- Đã phân biệt `g(s)`, `h(s)`, `h*(s)` và `f(s)=g+h`?
- Có chứng minh `h≤h*` cho mọi state khi cần tối ưu không?
- Heuristic có **consistent** nếu code dùng closed-only không reopen?
- Có kiểm tình huống đường rẻ hơn tới trạng thái đã thấy và heap stale?
- Chi phí cạnh A* có không âm theo giả thiết thuật toán?
- Có dừng khi goal được pop, không phải chỉ vừa sinh?
- Với lưới, heuristic Manhattan có đúng luật di chuyển bốn hướng unit cost?
- Path trả về có đi theo cạnh thật, có độ dài bằng distance?
- Với bài phân công, prefix đã dùng cột nào và hàng nào còn lại có được mã hóa đầy đủ?
- Lower bound có xuất phát từ **bài nới lỏng thật** và chứng minh không vượt completion tối ưu?
- Upper bound có đến từ **phép gán hoàn chỉnh hợp lệ**?
- Với minimization tìm một nghiệm, có prune chỉ khi `LB≥best`?
- Nếu phải đếm mọi optimum, có giữ nhánh `LB=best` khi cần?
- Có xử lý chi phí âm ở assignment mà không làm h tăng giả?
- Có kiểm soát overflow của tổng chi phí và LB?
- Có cân đối chi phí tính bound với số node tiết kiệm?
- Đã so A* với BFS trên grid nhỏ có tường/ngõ cụt?
- Đã so BnB với vét cạn mọi hoán vị cho n nhỏ?
- Đã thử tie, greedy trap, nghiệm âm, grid bị chặn và nhiều đường ngắn nhất?
- Khi bài đổi sang cost/quota/luật di chuyển khác, có **chứng minh lại** heuristic thay vì dùng theo thói quen?

**Kết luận:** heuristic là công cụ ước lượng **chi phí còn lại**, nhưng muốn giữ **tính tối ưu**, phải biến nó thành **cận có chứng minh**. Với A*, điều kiện **admissible** bảo đảm không overestimate, còn **consistent** cho phép triển khai closed-only không reopen an toàn; Manhattan là một ví dụ chặt chẽ trên lưới bốn hướng chi phí 1. Với branch-and-bound, **lower bound từ bài toán nới lỏng** cộng chi phí đã trả giúp loại nhánh, trong khi **upper bound phải là một nghiệm khả thi thật**. Dùng đúng chiều bất đẳng thức và dấu cắt nhánh, kết hợp kiểm thử bằng BFS/vét cạn độc lập, sẽ giúp chuyển từ “tìm kiếm có vẻ nhanh” sang “tìm kiếm có thể chứng minh kết quả tối ưu”.