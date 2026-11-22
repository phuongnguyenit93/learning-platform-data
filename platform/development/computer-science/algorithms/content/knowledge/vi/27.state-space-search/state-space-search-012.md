# Tìm đường trên lưới với chướng ngại và luật di chuyển

Một bản đồ gồm các ô vuông trông có vẻ đơn giản, nhưng bài **tìm đường trên lưới** (*grid pathfinding*) có thể đổi hoàn toàn đáp án khi ta đổi **luật di chuyển**, **giá bước**, **trạng thái tài nguyên** hay **cách xử lý chướng ngại**. Một ô tường có thể bị cấm đi qua, có thể phá đúng k lần, hoặc có thể chỉ chặn trong những thời điểm nhất định. Bước chéo có thể được phép, bị cấm, hoặc chỉ hợp lệ nếu không “cắt góc” qua hai bức tường. Vì vậy, trước khi chọn BFS, Dijkstra hay A*, cần **mô hình hóa chính xác một trạng thái và mọi phép chuyển hợp lệ**.

Bài thuộc nhóm **Tìm kiếm trạng thái**, tập trung vào **Tìm đường trên lưới với chướng ngại và luật di chuyển**. Ta sẽ học cách biến bản đồ thành **đồ thị ngầm**, chứng minh khi nào **BFS** tìm ít bước nhất, phân biệt lưới bốn hướng và tám hướng, kiểm tra **diagonal corner-cutting**, dùng **Dijkstra** khi ô có chi phí khác nhau, dùng **A*** với heuristic tương thích, mở rộng trạng thái khi được phá tối đa k tường, truy vết đường đi và nhận diện “không có đường”. Phần thực hành gồm chương trình **Java 17+ chạy độc lập** với bốn chế độ: BFS bốn hướng, BFS tám hướng có/không cấm cắt góc, Dijkstra theo chi phí ô đích, và BFS có ngân sách vượt tường. Cuối bài có ví dụ chính xác, phân tích độ phức tạp, kiểm thử độc lập và các lỗi phổ biến.

**Mục tiêu:** từ mô tả bài toán tự đặt được khóa trạng thái đúng, xác định cạnh chuyển hợp lệ, chọn thuật toán theo loại trọng số, xử lý cạnh góc đúng yêu cầu, dùng mảng visited/dist/parent tương ứng, và giải thích vì sao một đường được trả là **ngắn nhất theo hàm mục tiêu của đề**, không chỉ là một đường bất kỳ.

## 1. Từ ô vuông sang đồ thị trạng thái

Cho lưới có R hàng, C cột. Một ô có tọa độ **`(r,c)`**, đánh số **0-based** với `0≤r<R` và `0≤c<C`. Trong bài cơ bản:

- `S`: ô xuất phát (*start*).
- `G`: ô đích (*goal*).
- `.`: ô trống có thể đi.
- `#`: tường/chướng ngại không thể đi.
- Các chữ số `1..9`: ô có chi phí **đi vào** bằng số đó trong biến thể địa hình có trọng số.

Nếu mỗi trạng thái chỉ cần vị trí, đặt **`state=(r,c)`**. Một **cạnh của đồ thị ngầm** từ (r,c) tới (nr,nc) tồn tại khi phép chuyển ấy:

1. Thuộc **bộ hướng di chuyển** được cho phép.
2. Không đi ra ngoài lưới.
3. Có ô đích hợp lệ theo quy tắc tường/tài nguyên.
4. Thỏa mọi **điều kiện bổ sung**, ví dụ cấm cắt góc, hướng một chiều, khóa/chìa hoặc thời điểm.

**Đồ thị ngầm** nghĩa là không cần xây sẵn danh sách cạnh cho mọi ô: khi xử lý một trạng thái, ta sinh tối đa bốn hoặc tám ô kề theo luật. Điều này tiết kiệm bộ nhớ và làm trực tiếp trên ma trận.

### Chọn mục tiêu tối ưu trước khi chọn thuật toán

Có nhiều câu hỏi khác nhau:

- **Ít bước nhất:** mỗi bước hợp lệ có giá **1**, dù đi qua ô nào.
- **Tổng chi phí nhỏ nhất:** bước vào ô đắt hoặc rẻ tùy trọng số địa hình.
- **Ít lần phá tường nhất:** chi phí ưu tiên số lần phá, không nhất thiết ít bước.
- **Ít bước nhất trong giới hạn k lần phá:** tối ưu số bước, nhưng trạng thái cần ghi số lượt phá đã dùng.
- **Ít thời gian nhất khi có luật quay đầu/đợi đèn:** chi phí phụ thuộc hướng hoặc thời điểm.
- **Tối ưu đa mục tiêu:** ví dụ ít nguy hiểm nhất, rồi trong các đường ít nguy hiểm chọn ít bước nhất.

Không được mặc định “đường ngắn nhất” luôn là **ít cạnh nhất**. Thuật toán thích hợp phải tối ưu đúng đại lượng đề yêu cầu.

## 2. Bốn hướng: lưới có bậc tối đa 4

Với di chuyển theo trục, bộ hướng là:

~~~text
up:    (-1,  0)
right: ( 0, +1)
down:  (+1,  0)
left:  ( 0, -1)
~~~

Từ ô (r,c), một bước thử tới `(r+dr,c+dc)`. Trước khi vào queue, kiểm tra:

**`0≤nr<R ∧ 0≤nc<C ∧ grid[nr][nc]≠'#'`.**

Nếu mỗi bước có chi phí 1, khoảng cách của một đường chính là số bước; **BFS** trả đường ít bước nhất. Không cần kiểm tra “đường chéo cắt góc”, vì không có bước chéo.

Ví dụ lưới mở:

~~~text
S..
...
..G
~~~

S=(0,0), G=(2,2), cần ít nhất hai bước sang phải và hai bước xuống ⇒ ít nhất **4** bước. BFS tìm được một đường như:

**`(0,0)→(0,1)→(0,2)→(1,2)→(2,2)`**,

độ dài 4. Có nhiều đường tối ưu khác; thứ tự xét các hướng quyết định **đường cụ thể** được in, không thay đổi khoảng cách tối ưu.

### Tại sao BFS đúng?

Hàng đợi FIFO duyệt trạng thái theo **số bước không giảm** từ S. Trạng thái ở khoảng cách d chỉ sinh các hàng xóm mới ở khoảng cách d+1. Khi một ô được thăm **lần đầu** trong BFS đơn vị, ta đã tìm được đường ít bước nhất tới ô ấy. Vì vậy đánh dấu visited ngay **khi đưa ô vào queue** là an toàn và ngăn thêm trùng.

Nếu ô đích G được **lấy ra khỏi queue**, dist[G] là số bước nhỏ nhất; có thể kết thúc sớm. Trong BFS đúng với chi phí unit, cũng có thể dừng ngay khi **lần đầu phát hiện** G nếu đã gán dist; chương trình minh họa dùng quy tắc pop để các số đếm expanded dễ theo dõi.

## 3. Tám hướng: cho phép đi chéo nhưng phải định nghĩa góc

Bộ tám hướng gồm bốn hướng thẳng cộng bốn bước chéo:

~~~text
(-1, 0)   (0,+1)   (+1, 0)   (0,-1)
(-1,+1)   (+1,+1)  (+1,-1)   (-1,-1)
~~~

Bước chéo tới `(r+dr,c+dc)` có `|dr|=|dc|=1`.

**Hai quy tắc khác nhau** cần tách bạch:

1. **Cho phép cắt góc (corner cutting allowed):** chỉ cần ô đích không phải tường; một bước chéo có thể đi qua “khe góc” của hai ô chặn ở cạnh bên.
2. **Cấm cắt góc nghiêm ngặt (corner cutting forbidden):** khi đi chéo, **cả hai ô kề theo trục** `(r+dr,c)` và `(r,c+dc)` đều phải đi được. Nếu **một trong hai** là tường, bước chéo ấy không hợp lệ.

Cả hai quy tắc đều có thể xuất hiện trong đề bài/game engine; không có quy tắc nào là mặc định phổ quát. Phải đọc nguyên văn luật. Chương trình Java cho phép chọn cả hai để so sánh.

### Ví dụ quyết định: một bước hay không thể đi?

~~~text
S#
#G
~~~

S=(0,0), G=(1,1), hai ô bên cạnh đều là tường.

- Nếu **cho phép cắt góc**, bước chéo S→G hợp lệ ⇒ khoảng cách **1**.
- Nếu **cấm cắt góc**, hai ô bên cạnh không đi được ⇒ S hoàn toàn không có lối ra ⇒ **không có đường**.

Đây không phải lỗi BFS: **đồ thị trạng thái đã thay đổi vì quy tắc chuyển khác nhau**.

### 4 hướng, 8 hướng và các metric hình học

Trong **lưới trống** với bước có chi phí 1:

- Bốn hướng: khoảng cách **Manhattan** `d₄=|Δr|+|Δc|`.
- Tám hướng, cho phép chéo giá 1: khoảng cách **Chebyshev** `d₈=max(|Δr|,|Δc|)`.
- Tám hướng, bước thẳng giá 1 và chéo giá √2: khoảng cách **octile** trên lưới trống là `max(dx,dy)+(√2−1)min(dx,dy)`.

**Có tường:** các công thức trong lưới trống thường chỉ còn là **cận dưới** của khoảng cách thật, bởi chướng ngại hạn chế lựa chọn. Khi cấm cắt góc, khoảng cách thực có thể lớn hơn Chebyshev hoặc không đạt được.

**Quan trọng:** nếu bước chéo có giá **√2**, bài là **đường đi có trọng số**: BFS không còn tối ưu tổng chi phí. Cần Dijkstra/A* với trọng số thực sự và heuristic thích hợp. BFS tám hướng trong mã này chủ động quy ước **mọi bước, kể cả chéo, có giá đúng 1**.

## 4. Tường và đường vòng: heuristic không phải đáp án

Xét:

~~~text
S..#G
...#.
.....
~~~

Nếu đi bốn hướng, từ S=(0,0) đến G=(0,4), khoảng cách Manhattan bằng 4. Nhưng tường tại cột 3, hàng 0 và 1 buộc đường đi vòng xuống hàng 2:

~~~text
(0,0) -> (0,1) -> (0,2) -> (1,2)
      -> (2,2) -> (2,3) -> (2,4)
      -> (1,4) -> (0,4)
~~~

Đường này có **8** bước, và BFS xác nhận không có đường ngắn hơn. Manhattan **4 không phải** khoảng cách thực 8; nó là lower bound có thể dùng trong A*.

Một heuristic như Manhattan có giá trị để **sắp thứ tự ưu tiên**, nhưng không thể thay thế việc kiểm tra chướng ngại và sinh cạnh đi được.

## 5. BFS bốn/tám hướng: triển khai chuẩn

Dữ liệu chính:

- `dist[r][c]`: số bước nhỏ nhất đã tìm tới ô; ban đầu **−1** nghĩa là chưa thăm.
- `parentR[r][c], parentC[r][c]`: tọa độ ô đi trước trên đường tìm được.
- Queue FIFO chứa các tọa độ mới được khám phá.
- Mảng `dirs` chứa bốn hoặc tám độ lệch tọa độ.

Pseudocode:

~~~text
dist[start] = 0
queue.add(start)

while queue is not empty:
    u = queue.removeFirst()
    if u == goal:
        reconstruct path from parent
        return dist[u]

    for direction in selected movement rules:
        v = u + direction
        if v outside grid or blocked:
            continue
        if diagonal and forbidCornerCut:
            if either adjacent side-cell is blocked:
                continue
        if dist[v] != -1:
            continue

        dist[v] = dist[u] + 1
        parent[v] = u
        queue.addLast(v)

return unreachable
~~~

Khi **không có đường**, queue rỗng mà chưa gặp G. Trả một ký hiệu rõ ràng như **distance = −1** và path rỗng, thay vì trả Manhattan hoặc số bước tạm từ ô gần nhất.

### Tại sao parent đủ để dựng đường?

Mỗi ô v được đưa vào queue lần đầu bởi một ô u đã có dist. Lưu `parent[v]=u`; nếu v≠S, lặp từ G về parent cho tới S rồi đảo thứ tự. Mỗi bước parent giảm dist đúng 1, nên không tạo chu trình parent và số cạnh trong path bằng dist[G].

**Chỉ một đường tối ưu** được chọn khi có nhiều cách đi; yêu cầu đếm mọi đường ngắn nhất cần thêm DP/counting trên DAG các lớp BFS, không thể suy số lượng từ một parent duy nhất.

## 6. Ô địa hình có chi phí khác nhau: phải dùng Dijkstra

Trong nhiều game/bản đồ, đi vào ô cát mất 5, đi vào ô bằng phẳng mất 1. Bài toán lúc này tối ưu **tổng chi phí**, không phải số bước. Nếu dùng queue FIFO và visited khi lần đầu gặp ô, BFS có thể giữ một đường có ít bước nhưng **đắt hơn** một đường dài hơn.

Ví dụ:

~~~text
S91G
1111
~~~

Quy ước:

- `S` có chi phí khởi tạo **0** (không trả tiền để đứng sẵn ở nguồn).
- Bước **đi vào** ô chữ số 1..9 có chi phí bằng chữ số.
- Bước đi vào `.` hoặc `G` có chi phí 1.
- `#` không được đi qua.
- Chỉ đi **bốn hướng**.

Đường theo hàng trên cùng có ba bước:

`S→9→1→G`, chi phí **9+1+1=11**.

Nhưng đường vòng có năm bước:

**`(0,0)→(1,0)→(1,1)→(1,2)→(0,2)→(0,3)`**,

chi phí **1+1+1+1+1=5**.

Vậy câu trả lời đúng là **min total cost=5**, dù đường tối ưu có **nhiều bước hơn** đường thẳng.

### Dijkstra trên lưới

Với mọi chi phí cạnh **không âm**, Dijkstra dùng priority queue ưu tiên **`dist` nhỏ nhất**:

1. Khởi tạo `dist[S]=0`, ô khác +∞.
2. Pop ô có chi phí tạm nhỏ nhất, bỏ entry cũ/stale.
3. Khi ô được pop lần đầu với chi phí tốt nhất, có thể đánh dấu **settled/closed**.
4. Với mỗi bước hợp lệ tới v, thử `newCost=dist[u]+enterCost(v)`.
5. Nếu nhỏ hơn dist[v], cập nhật và lưu parent rồi thêm entry mới vào queue.
6. Dừng khi G được pop ở chi phí tối ưu.

Bởi các chi phí 1..9 đều dương, Dijkstra bảo đảm đường đầu tiên được chốt tới G là đường tổng chi phí nhỏ nhất. Trên lưới R×C, mỗi ô tối đa bốn hàng xóm ⇒ thời gian `O(RC log(RC))` và bộ nhớ `O(RC)` cho phiên bản priority queue thông thường.

### Khi nào chọn thuật toán khác?

- Mọi cạnh giá **1**: BFS đạt `O(V+E)`.
- Mọi cạnh giá **0 hoặc 1**: **0–1 BFS** dùng deque, đẩy trước cạnh 0 và đẩy cuối cạnh 1, thường đạt `O(V+E)`.
- Cạnh có giá không âm bất kỳ: **Dijkstra**, hoặc A* nếu có heuristic admissible/consistent và xử lý đúng.
- Có giá âm: Dijkstra **không** còn được bảo đảm đúng; phải phân tích loại bài, chu trình âm và dùng phương pháp phù hợp.
- Bài tối ưu nhiều tiêu chí: phải định nghĩa thứ tự ưu tiên và trọng số, có thể dùng state mở rộng hoặc một thuật toán đa mục tiêu.

**Không cộng chiều dài hình học của đường thay cho quy tắc enterCost.** Nếu đề nói trả chi phí rời ô, hoặc phí theo cạnh thay vì ô đến, phải thay công thức cộng đúng.

## 7. A* trên lưới: tối ưu nếu heuristic hợp lệ

A* lưu:

**`g(s)` = chi phí đã biết từ start đến s**,  
**`h(s)` = cận dưới ước lượng chi phí còn lại tới goal**,  
**`f(s)=g(s)+h(s)`**.

Priority queue ưu tiên f nhỏ nhất; giống Dijkstra nhưng tận dụng thông tin đích. Nếu **h=0**, A* trở về Dijkstra trong mô hình thông thường.

### Heuristic theo luật chuyển

| Luật di chuyển | Heuristic cận dưới thường dùng |
|---|---|
| Bốn hướng, mỗi bước giá 1 | `Manhattan=|Δr|+|Δc|` |
| Tám hướng, mọi bước giá 1 | `Chebyshev=max(|Δr|,|Δc|)` |
| Tám hướng, bước thẳng 1, chéo √2 | `Octile=max(dx,dy)+(√2−1)min(dx,dy)` |
| Bốn hướng, mỗi bước vào ô có giá ít nhất m≥0 | `m·Manhattan` |
| Tám hướng có giá ít nhất m cho mỗi bước | `m·Chebyshev` |
| Có cổng teleport chi phí rất rẻ, luật đặc biệt | Cần chứng minh cận khác; `h=0` luôn an toàn nếu chi phí còn lại không âm |

Các công thức phải được xét lại nếu luật đổi: bước chéo giá 1 khiến Manhattan **đánh giá quá cao** chi phí từ (0,0) tới (1,1) là 2 trong khi chỉ cần 1 bước. Heuristic quá cao không thể dùng làm chứng nhận tối ưu A*.

### Admissible và consistent

**Admissible:** `h(s)≤h*(s)`, không bao giờ lớn hơn chi phí tối ưu thật còn lại.

**Consistent:** với mỗi phép chuyển u→v có chi phí c, **`h(u)≤c(u,v)+h(v)`**, và `h(goal)=0`.

Heuristic consistent đảm bảo f không giảm dọc theo đường đi; khi một state được pop ở g tốt nhất, có thể **closed** vĩnh viễn. Manhattan trên lưới bốn hướng giá 1 vừa admissible vừa consistent; cấm một số bước vì tường không phá các bất đẳng thức trên cạnh **còn hợp lệ**.

Nếu heuristic chỉ admissible nhưng **không consistent**, A* dạng graph search cần cho phép **reopen** khi tìm đường mới có g tốt hơn tới một state đã closed. Bản Dijkstra Java trong bài dùng h=0, không có bất cập này.

### Với được phá k tường, heuristic nào?

Nếu vẫn chỉ đi bốn hướng, mỗi bước tiêu tốn 1, ngay cả khi có thể vượt tường một số lần thì **Manhattan vẫn là cận dưới**: mọi đường vẫn phải thay đủ tọa độ. Heuristic “khoảng cách BFS trên bản đồ chưa cho phá tường” có thể là **cận trên hoặc vô hạn** so với đường có quyền vượt tường, nên không được dùng làm lower bound nếu chưa chứng minh.

## 8. Vượt tối đa k tường: phải mở rộng trạng thái

Cho phép một người đi qua tối đa k ô tường trong cả hành trình, với chi phí **một lượt tài nguyên** mỗi lần **bước vào ô `#`**. Mọi bước bốn hướng tiêu tốn **1 đơn vị thời gian**, dù vào tường hay ô trống.

Một trạng thái chỉ là `(r,c)` không còn đủ: hai đường cùng tới ô (r,c) nhưng đã tiêu tốn số lượt vượt tường khác nhau có **các khả năng đi tiếp khác nhau**.

Ta cần:

**`state=(r,c,used)`**,

với `used` là số lượt vượt tường đã tiêu hao, `0≤used≤k`.

Khi từ (r,c,used) sang (nr,nc):

- Nếu ô kế là `.`, `S`, `G` hoặc ô số: `newUsed=used`.
- Nếu ô kế là `#`: `newUsed=used+1`.
- Bỏ bước nếu `newUsed>k`.
- Chi phí mỗi bước vẫn =1, nên **BFS trên không gian trạng thái mở rộng** tìm ít bước nhất.

### Ví dụ dễ thấy

~~~text
S#G
~~~

- `k=0`: không thể qua ô tường, kết quả **−1**.
- `k=1`: đi S→#→G, **2 bước**, đã dùng 1 lượt.

Với:

~~~text
S##G
~~~

- `k=1`: không thể đi xuyên cả hai tường trên lưới một hàng.
- `k=2`: đường S→#→#→G, **3 bước**, đã dùng 2 lượt.

### Vì sao visited phải có chiều thứ ba?

Giả sử cùng ô x được tới qua:

- `state₁=(x,used=0)` sau 6 bước.
- `state₂=(x,used=1)` sau 4 bước.

State₂ tới sớm hơn nhưng có ít tài nguyên hơn. Không thể bỏ state₁ chỉ vì tọa độ x đã thăm: khi về sau có tường cần vượt, state₁ có thể hoàn thành còn state₂ thì không.

Do đó mảng đúng là:

**`visited[r][c][used]`**, và parent phải lưu **toàn bộ state trước đó**, không chỉ (r,c).

BFS đánh dấu mỗi bộ ba khi enqueue. Không gian tối đa **`R·C·(k+1)` trạng thái**, nên thời gian và bộ nhớ **`O(RC(k+1))`** với bốn hướng. Trên bản đồ lớn, k có thể làm tăng nhu cầu RAM rất mạnh.

### Cắt k về số tường

Nếu có W ô tường và chỉ cần **một đường ngắn nhất**, có thể xét `effectiveK=min(k,W)`. Một đường ngắn nhất theo số bước **không cần lặp lại một tọa độ** (nếu lặp, bỏ chu trình rút ngắn đường), nên không thể bước vào nhiều hơn W ô tường khác nhau trên một đường tối ưu. Việc giảm chiều k như vậy vẫn bảo toàn đáp án.

**Ngữ nghĩa chính xác của mã:** một lượt tài nguyên bị trừ **mỗi lần bước vào ô tường**, không mô hình hóa việc tường bị phá **vĩnh viễn cho mọi lần qua về sau**. Với đường ngắn nhất không chu trình, khác biệt thường không làm đổi đáp án; nhưng nếu đề yêu cầu trạng thái phá tường tồn tại vĩnh viễn để dùng lại hoặc có nhiều tác nhân đi qua, phải mô hình hóa thêm **tập tường đã phá**, không được tự đồng nhất hai bài toán.

### Có thể ưu tiên đường ít phá tường hơn trong các đường ít bước không?

BFS với queue FIFO bảo đảm **số bước nhỏ nhất**. Nếu yêu cầu phụ “trong số các đường ít bước nhất, phá ít tường nhất”, cần thêm tiêu chí giải hòa hoặc xử lý tối ưu theo cặp **(steps,breaks)**. Không được suy rằng state goal đầu tiên được pop luôn dùng ít lượt phá nhất trong tất cả các đường cùng số bước; nó phụ thuộc thứ tự duyệt.

## 9. Khi state còn phải chứa nhiều thông tin hơn

Mở rộng state là nguyên tắc tổng quát, không chỉ dùng cho k tường.

| Luật chuyển | State phù hợp | Lý do không thể chỉ dùng vị trí |
|---|---|---|
| Đi theo ô trống cố định | `(r,c)` | Chi phí tương lai chỉ phụ thuộc vị trí |
| Phá tối đa k tường | `(r,c,used)` | Ngân sách còn lại ảnh hưởng đường sau |
| Chìa khóa/mở cửa | `(r,c,keyMask)` | Cửa đi qua được hay không phụ thuộc chìa đang có |
| Phí rẽ trái/rẽ phải | `(r,c,direction)` | Chi phí quay phụ thuộc hướng vừa đến |
| Bản đồ thay đổi theo chu kỳ p | `(r,c,time mod p)` | Cùng ô nhưng thời điểm khác nhau cho lối khác |
| Có quyền dịch chuyển một lần | `(r,c,usedTeleport)` | Quyền còn hay hết ảnh hưởng trạng thái sau |
| Tối đa b lần dùng nhiên liệu | `(r,c,fuel)` | Tài nguyên phụ thuộc lịch sử |
| Hai nhân vật cùng di chuyển | `(r1,c1,r2,c2,...)` | Luật va chạm/vị trí người thứ hai quan trọng |

Một **state hợp lệ** phải chứa đủ thông tin sao cho: **các phép chuyển và chi phí tương lai chỉ phụ thuộc state hiện tại**, không phụ thuộc lịch sử ngoài phần đã mã hóa. Đây là điều kiện thực tế để visited/bestDistance có nghĩa đúng.

### Ví dụ tính phí đổi hướng

Nếu tiếp tục cùng hướng tốn 1, nhưng đổi hướng tốn thêm 5, hai đường tới cùng ô nhưng có hướng đến khác nhau có thể cho chi phí tiếp theo khác. Dijkstra chỉ lưu `dist[r][c]` sẽ loại mất một hướng tốt trong tương lai. Phải dùng `dist[r][c][direction]` và khởi tạo hướng “chưa có” tại S hoặc thêm state đặc biệt.

### Ví dụ chướng ngại di động

Nếu ô bị chặn tại các thời điểm khác nhau, đi từ (r,c) tới ô kế có thể hợp lệ ở t=2 nhưng không ở t=3. Nếu chu kỳ p, gói state theo `t mod p`; nếu cần **đợi tại chỗ**, thêm một phép chuyển `(r,c,t)→(r,c,t+1)` với chi phí thời gian tương ứng. Tránh mô hình hóa t nguyên mãi nếu có thể chứng minh tính chu kỳ và thu gọn.

## 10. Phân biệt BFS, 0–1 BFS, Dijkstra và A* trong một bảng

| Đặc điểm đề bài | Thuật toán thường chọn | Vì sao |
|---|---|---|
| Mọi bước bằng 1, không tài nguyên | **BFS** | Queue theo số bước, O(V+E) |
| Mọi bước bằng 1, có trạng thái tài nguyên hữu hạn | **BFS trên state mở rộng** | Mọi chuyển vẫn chi phí 1 |
| Mỗi chuyển giá 0 hoặc 1 | **0–1 BFS** | Deque ưu tiên cạnh giá 0 |
| Mỗi chuyển có giá không âm | **Dijkstra** | Pop theo chi phí thật nhỏ nhất |
| Có heuristic admissible và phù hợp | **A\*** | Ưu tiên g+h, có thể mở ít trạng thái hơn |
| Cần đi tới nhiều đích gần nhất từ nhiều nguồn | **Multi-source BFS/Dijkstra** | Đưa nhiều nguồn vào queue/PQ ban đầu |
| Có cạnh âm | Phân tích Bellman–Ford/biến thể thích hợp | Dijkstra không bảo đảm đúng |
| Chỉ hỏi có đường, không cần tối ưu | BFS/DFS | Reachability không nhất thiết cần PQ |
| Bản đồ/luật thay đổi liên tục | Cần tính lại hoặc dùng thuật toán dynamic/path planning | Tiền xử lý cũ có thể hết hiệu lực |

**Không chọn thuật toán theo “grid” hay “graph” một cách máy móc**: lưới chỉ là cách mã hóa trạng thái. Điều quyết định là **luật chuyển, chi phí và ràng buộc**.

## 11. Java 17+ hoàn chỉnh: bốn chế độ tìm đường

Chương trình minh họa dùng một **bản đồ tĩnh**. Nó kiểm tra:

- Lưới không rỗng, **hình chữ nhật**, mọi hàng cùng độ dài.
- Đúng một `S` và đúng một `G`; hai ký tự đại diện hai ô khác nhau.
- Chỉ nhận `S`, `G`, `.`, `#` và chữ số `1..9`.
- Chỉ số tọa độ 0-based.
- Không đi ra khỏi lưới.
- Bản đồ được coi là tĩnh; các thuật toán **không chỉnh sửa ô tường**.
- Trong BFS unit-cost, chữ số là **ô đi được, vẫn giá một bước**.
- Trong Dijkstra, chi phí bước vào ô số bằng số đó; bước vào `.` hoặc `G` là 1; chi phí bắt đầu tại S là 0.
- Trong BFS phá tường, **bước vào một ô `#`** tiêu tốn một lượt phá và **một bước thời gian**. Với ngân sách k≥0, chương trình trả ít bước nhất trong mọi đường dùng không quá k lượt.
- Khi không có đường, `distance/cost=-1` và `path=[]`. Với BFS phá tường, `broken=-1` khi không có lời giải.

Mỗi kết quả in **expanded**, là số trạng thái thực sự được lấy khỏi queue/PQ và xử lý; nó **không** phải tổng số đỉnh có trong bản đồ, cũng không phải số bước của đường. Con số này phụ thuộc thứ tự hướng và quy tắc tie-break của priority queue.

### Mã nguồn: `GridPathRulesDemo.java`

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public final class GridPathRulesDemo {
    // Four cardinal directions first; four diagonals afterward.
    private static final int[][] DIRS = {
        {-1, 0}, {0, 1}, {1, 0}, {0, -1},
        {-1, 1}, {1, 1}, {1, -1}, {-1, -1}
    };

    private record Grid(
            char[][] cells, int rows, int cols,
            int startRow, int startCol,
            int goalRow, int goalCol, int wallCount) {

        static Grid parse(String... lines) {
            if (lines == null || lines.length == 0
                    || lines[0] == null || lines[0].isEmpty()) {
                throw new IllegalArgumentException("Invalid grid");
            }
            int rows = lines.length;
            int cols = lines[0].length();
            char[][] cells = new char[rows][cols];
            int starts = 0, goals = 0, walls = 0;
            int sr = -1, sc = -1, gr = -1, gc = -1;

            for (int r = 0; r < rows; r++) {
                if (lines[r] == null
                        || lines[r].length() != cols) {
                    throw new IllegalArgumentException(
                            "Grid must be rectangular");
                }
                for (int c = 0; c < cols; c++) {
                    char ch = lines[r].charAt(c);
                    if (ch != 'S' && ch != 'G'
                            && ch != '.' && ch != '#'
                            && !(ch >= '1' && ch <= '9')) {
                        throw new IllegalArgumentException(
                                "Unknown tile symbol");
                    }
                    cells[r][c] = ch;
                    if (ch == 'S') {
                        starts++;
                        sr = r;
                        sc = c;
                    } else if (ch == 'G') {
                        goals++;
                        gr = r;
                        gc = c;
                    } else if (ch == '#') {
                        walls++;
                    }
                }
            }

            if (starts != 1 || goals != 1) {
                throw new IllegalArgumentException(
                        "Exactly one S and G required");
            }
            return new Grid(
                    cells, rows, cols, sr, sc, gr, gc, walls);
        }
    }

    private record PathResult(
            long distance, List<String> path, int expanded) {}

    private record BreakResult(
            long distance, int broken,
            List<String> path, int expanded) {}

    private record Node(int row, int col, long cost) {}

    private record Walk(int row, int col, int used, int steps) {}

    private static boolean inside(Grid grid, int r, int c) {
        return r >= 0 && r < grid.rows()
                && c >= 0 && c < grid.cols();
    }

    private static boolean open(Grid grid, int r, int c) {
        return inside(grid, r, c)
                && grid.cells()[r][c] != '#';
    }

    // Forbid a diagonal if EITHER orthogonal side tile
    // is blocked; destination must also be open.
    private static boolean stepAllowed(
            Grid grid, int r, int c,
            int dr, int dc, boolean forbidCornerCut) {
        int nr = r + dr;
        int nc = c + dc;
        if (!open(grid, nr, nc)) {
            return false;
        }
        if (forbidCornerCut && dr != 0 && dc != 0) {
            return open(grid, r + dr, c)
                    && open(grid, r, c + dc);
        }
        return true;
    }

    private static List<String> reconstruct(
            Grid grid, int[][] prevRow, int[][] prevCol,
            int r, int c) {
        List<String> result = new ArrayList<>();
        while (true) {
            result.add("(" + r + "," + c + ")");
            if (r == grid.startRow()
                    && c == grid.startCol()) {
                break;
            }
            int pr = prevRow[r][c];
            int pc = prevCol[r][c];
            if (pr < 0 || pc < 0) {
                throw new IllegalStateException(
                        "Broken parent chain");
            }
            r = pr;
            c = pc;
        }
        Collections.reverse(result);
        return List.copyOf(result);
    }

    // Every move, including diagonal, costs exactly 1.
    static PathResult bfs(
            Grid grid, boolean allowDiagonal,
            boolean forbidCornerCut) {
        int rows = grid.rows(), cols = grid.cols();
        int[][] dist = new int[rows][cols];
        int[][] prevRow = new int[rows][cols];
        int[][] prevCol = new int[rows][cols];

        for (int r = 0; r < rows; r++) {
            Arrays.fill(dist[r], -1);
            Arrays.fill(prevRow[r], -1);
            Arrays.fill(prevCol[r], -1);
        }
        ArrayDeque<int[]> queue = new ArrayDeque<>();
        int sr = grid.startRow(), sc = grid.startCol();
        dist[sr][sc] = 0;
        queue.addLast(new int[] {sr, sc});
        int expanded = 0;
        int directions = allowDiagonal ? 8 : 4;

        while (!queue.isEmpty()) {
            int[] current = queue.removeFirst();
            int r = current[0], c = current[1];
            expanded++;

            if (r == grid.goalRow() && c == grid.goalCol()) {
                return new PathResult(dist[r][c],
                        reconstruct(
                                grid, prevRow, prevCol, r, c),
                        expanded);
            }

            for (int d = 0; d < directions; d++) {
                int dr = DIRS[d][0], dc = DIRS[d][1];
                if (!stepAllowed(
                        grid, r, c, dr, dc, forbidCornerCut)) {
                    continue;
                }
                int nr = r + dr, nc = c + dc;
                if (dist[nr][nc] != -1) {
                    continue; // First discovery is optimal in BFS.
                }
                dist[nr][nc] = dist[r][c] + 1;
                prevRow[nr][nc] = r;
                prevCol[nr][nc] = c;
                queue.addLast(new int[] {nr, nc});
            }
        }
        return new PathResult(-1, List.of(), expanded);
    }

    // Dijkstra: four directions, pay upon ENTERING a tile.
    static PathResult weighted(Grid grid) {
        int rows = grid.rows(), cols = grid.cols();
        long[][] best = new long[rows][cols];
        int[][] prevRow = new int[rows][cols];
        int[][] prevCol = new int[rows][cols];
        boolean[][] settled = new boolean[rows][cols];

        for (int r = 0; r < rows; r++) {
            Arrays.fill(best[r], Long.MAX_VALUE);
            Arrays.fill(prevRow[r], -1);
            Arrays.fill(prevCol[r], -1);
        }

        Comparator<Node> order = Comparator
                .comparingLong(Node::cost)
                .thenComparingInt(Node::row)
                .thenComparingInt(Node::col);
        PriorityQueue<Node> queue = new PriorityQueue<>(order);

        int sr = grid.startRow(), sc = grid.startCol();
        best[sr][sc] = 0;
        queue.add(new Node(sr, sc, 0));
        int expanded = 0;

        while (!queue.isEmpty()) {
            Node node = queue.remove();
            int r = node.row(), c = node.col();
            if (node.cost() != best[r][c] || settled[r][c]) {
                continue; // Skip stale heap entries.
            }
            settled[r][c] = true;
            expanded++;

            if (r == grid.goalRow() && c == grid.goalCol()) {
                return new PathResult(node.cost(),
                        reconstruct(
                                grid, prevRow, prevCol, r, c),
                        expanded);
            }

            for (int d = 0; d < 4; d++) {
                int dr = DIRS[d][0], dc = DIRS[d][1];
                if (!stepAllowed(grid, r, c, dr, dc, true)) {
                    continue;
                }
                int nr = r + dr, nc = c + dc;
                if (settled[nr][nc]) {
                    continue;
                }
                char tile = grid.cells()[nr][nc];
                int entering = tile >= '1' && tile <= '9'
                        ? tile - '0' : 1;
                long next = Math.addExact(node.cost(), entering);

                if (next < best[nr][nc]) {
                    best[nr][nc] = next;
                    prevRow[nr][nc] = r;
                    prevCol[nr][nc] = c;
                    queue.add(new Node(nr, nc, next));
                }
            }
        }
        return new PathResult(-1, List.of(), expanded);
    }

    // BFS over (row, col, number of walls entered).
    // Every move costs 1; entering '#' consumes one break.
    static BreakResult breakWalls(Grid grid, int maxBreaks) {
        if (maxBreaks < 0) {
            throw new IllegalArgumentException(
                    "Negative wall-break budget");
        }

        int rows = grid.rows(), cols = grid.cols();
        int limit = Math.min(maxBreaks, grid.wallCount());

        boolean[][][] seen =
                new boolean[rows][cols][limit + 1];
        Walk[][][] previous =
                new Walk[rows][cols][limit + 1];
        ArrayDeque<Walk> queue = new ArrayDeque<>();
        Walk start = new Walk(
                grid.startRow(), grid.startCol(), 0, 0);

        seen[start.row()][start.col()][0] = true;
        queue.addLast(start);
        int expanded = 0;

        while (!queue.isEmpty()) {
            Walk cur = queue.removeFirst();
            expanded++;

            if (cur.row() == grid.goalRow()
                    && cur.col() == grid.goalCol()) {
                List<String> path = new ArrayList<>();
                Walk w = cur;
                while (w != null) {
                    path.add("(" + w.row()
                            + "," + w.col() + ")");
                    w = previous[w.row()][w.col()][w.used()];
                }
                Collections.reverse(path);
                return new BreakResult(
                        cur.steps(), cur.used(),
                        List.copyOf(path), expanded);
            }

            for (int d = 0; d < 4; d++) {
                int nr = cur.row() + DIRS[d][0];
                int nc = cur.col() + DIRS[d][1];
                if (!inside(grid, nr, nc)) {
                    continue;
                }

                int nextUsed = cur.used()
                        + (grid.cells()[nr][nc] == '#' ? 1 : 0);
                if (nextUsed > limit
                        || seen[nr][nc][nextUsed]) {
                    continue;
                }

                Walk next = new Walk(
                        nr, nc, nextUsed, cur.steps() + 1);
                seen[nr][nc][nextUsed] = true;
                previous[nr][nc][nextUsed] = cur;
                queue.addLast(next);
            }
        }
        return new BreakResult(-1, -1, List.of(), expanded);
    }

    private static void showBfs(
            String name, Grid grid,
            boolean diagonal, boolean forbidCorners) {
        PathResult p = bfs(grid, diagonal, forbidCorners);
        System.out.println(name + ": distance=" + p.distance()
                + ", path=" + p.path()
                + ", expanded=" + p.expanded());
    }

    private static void showTerrain(String name, Grid grid) {
        PathResult p = weighted(grid);
        System.out.println(name + ": cost=" + p.distance()
                + ", path=" + p.path()
                + ", expanded=" + p.expanded());
    }

    private static void showBreaks(
            String name, Grid grid, int limit) {
        BreakResult p = breakWalls(grid, limit);
        System.out.println(name + ": distance=" + p.distance()
                + ", broken=" + p.broken()
                + ", path=" + p.path()
                + ", expanded=" + p.expanded());
    }

    public static void main(String[] args) {
        Grid open = Grid.parse("S..", "...", "..G");
        showBfs("Open 4", open, false, true);
        showBfs("Open 8", open, true, true);

        Grid corner = Grid.parse("S#", "#G");
        showBfs("Corner allowed", corner, true, false);
        showBfs("Corner forbidden", corner, true, true);

        Grid detour = Grid.parse("S..#G", "...#.", ".....");
        showBfs("Detour 4", detour, false, true);

        Grid blocked = Grid.parse("S#G", "###", "...");
        showBfs("Blocked 4", blocked, false, true);

        Grid terrain = Grid.parse("S91G", "1111");
        showTerrain("Terrain Dijkstra", terrain);

        Grid oneWall = Grid.parse("S#G");
        showBreaks("Break K=0", oneWall, 0);
        showBreaks("Break K=1", oneWall, 1);

        Grid twoWalls = Grid.parse("S##G");
        showBreaks("Break K=2", twoWalls, 2);
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac GridPathRulesDemo.java
java GridPathRulesDemo
~~~

**Stdout chính xác** với thứ tự hướng và tie-break như trong mã:

~~~text
Open 4: distance=4, path=[(0,0), (0,1), (0,2), (1,2), (2,2)], expanded=9
Open 8: distance=2, path=[(0,0), (1,1), (2,2)], expanded=9
Corner allowed: distance=1, path=[(0,0), (1,1)], expanded=2
Corner forbidden: distance=-1, path=[], expanded=1
Detour 4: distance=8, path=[(0,0), (0,1), (0,2), (1,2), (2,2), (2,3), (2,4), (1,4), (0,4)], expanded=13
Blocked 4: distance=-1, path=[], expanded=1
Terrain Dijkstra: cost=5, path=[(0,0), (1,0), (1,1), (1,2), (0,2), (0,3)], expanded=7
Break K=0: distance=-1, broken=-1, path=[], expanded=1
Break K=1: distance=2, broken=1, path=[(0,0), (0,1), (0,2)], expanded=3
Break K=2: distance=3, broken=2, path=[(0,0), (0,1), (0,2), (0,3)], expanded=5
~~~

### Giải thích từng nhóm output

**Open 4 vs Open 8.** Cùng lưới trống 3×3, đi bốn hướng cần 4 bước; đi tám hướng với giá chéo bằng 1 chỉ cần 2 bước chéo. Trong BFS tám hướng, số `expanded=9` vẫn có thể bằng số ô của cả lưới vì thứ tự khám phá/tie của FIFO, dù đường tối ưu ngắn; không nên đồng nhất “độ dài đường” và “số trạng thái mở rộng”.

**Corner allowed vs Corner forbidden.** Hai cấu hình có cùng S và G nhưng **khác đồ thị chuyển trạng thái**. Với corner cutting allowed, đi chéo thẳng qua góc được một bước. Với quy tắc nghiêm ngặt, cả hai ô cạnh bên là tường nên không thể đi: −1.

**Detour 4.** Tường buộc đi vòng xuống hàng 2, đường in có 8 bước. Manhattan S→G chỉ bằng 4 và không phải đáp án nếu có tường.

**Blocked 4.** G bị cách ly bởi tường trong lưới bốn hướng, không có đường; path rỗng, không bịa một đường đi “gần goal”.

**Terrain Dijkstra.** Đi trực tiếp từ S qua ô giá 9 tạo đường 3 bước nhưng chi phí 11; code tìm đường 5 bước giá 5, tránh ô chi phí cao. Parent từ Dijkstra ghi đường có **tổng chi phí nhỏ nhất**, không nhất thiết ít bước.

**Break K=0/K=1/K=2.** Quyền vượt tường phải nằm trong **state**. Với một tường giữa S và G, k=0 không có đường, k=1 có đường 2 bước tiêu một lượt. Với hai tường liên tiếp ở một hàng, k=2 có đường 3 bước dùng 2 lượt.

### Vì sao BFS phá tường có thể mở rộng hơn số ô?

Một tọa độ (r,c) có thể xuất hiện trong queue nhiều lần với **used khác nhau**. Mỗi bộ ba là một trạng thái hợp lệ riêng. Vì thế ở `Break K=2`, expanded=5 dù bản đồ chỉ có 4 ô: một ô có thể được khám phá với những mức tài nguyên khác nhau trước khi đích được pop. Đây không phải bug visited; nó cho thấy chiều trạng thái bổ sung thật sự tồn tại.

### Vì sao không dùng một tham số “diagonalCost” chung cho tất cả?

Trong code, hàm `bfs` đã quy ước **mỗi bước giá 1**. Nếu muốn bước chéo giá √2, hoặc mỗi ô có trọng số riêng, phải thay **toàn bộ cơ chế tối ưu** từ BFS sang Dijkstra/A* và định nghĩa lại trọng số của cạnh chuyển. Chỉ cộng thêm một biến diagonalCost rồi vẫn dùng visited-on-first-discovery là không đủ.

## 12. Chứng minh tính đúng của bốn chế độ

### 12.1. BFS unit-cost

BFS duyệt theo số bước tăng dần. Mọi cạnh có giá 1, nên lần đầu phát hiện một trạng thái x ta đã tìm được đường ít bước nhất đến x. Lưu dist và parent tại lần khám phá đầu tiên là an toàn. Khi G được pop, dist[G] tối ưu. Nếu queue rỗng, không còn trạng thái đạt được nào chưa xét, nên G không thể đạt được theo luật đã mô hình hóa.

### 12.2. BFS tám hướng và cắt góc

Quy tắc hợp lệ của mỗi bước được xử lý ngay ở `stepAllowed`. Khi cấm cắt góc, một bước chéo chỉ được thêm vào đồ thị nếu **hai ô theo trục cũng thông được**. Sau khi đã xây đúng tập cạnh, chứng minh BFS đơn vị giống bốn hướng. **Tính đúng phụ thuộc việc mô hình hóa luật**, không phụ thuộc riêng BFS.

### 12.3. Dijkstra có chi phí vào ô

Mọi bước vào ô trong phiên bản này có chi phí từ 1..9, nên không âm. Dijkstra luôn pop bản ghi chưa stale có khoảng cách nhỏ nhất. Giả sử một ô u được chốt với chi phí lớn hơn đường tốt hơn nào đó; trên đường tốt hơn, phải có một cạnh chuyển từ ô đã chốt sang ô chưa chốt với chi phí tạm không lớn hơn chi phí thật tốt hơn, mâu thuẫn việc u được pop ở khoảng cách nhỏ nhất. Vì thế khi chốt G, cost tối ưu.

**Không dùng dist==-1 làm sentinel chung cho Dijkstra** nếu có chi phí lớn; code dùng `Long.MAX_VALUE` đại diện vô cùng và `Math.addExact` để không âm thầm tràn khi cộng.

### 12.4. BFS state mở rộng với tài nguyên tường

Mỗi phép di chuyển được mã hóa thành cạnh từ **(r,c,used)** sang **(nr,nc,newUsed)** nếu newUsed≤k. Mỗi cạnh có giá 1. Vì luật tài nguyên tương lai hoàn toàn phụ thuộc vào bộ ba, lưới mở rộng là một **đồ thị trạng thái đầy đủ**. BFS tìm đường ít bước nhất trên đồ thị ấy, và đích là **bất kỳ trạng thái (goalR,goalC,used≤k)**. Đích đầu tiên được pop có số bước tối thiểu trên tất cả các giá trị used.

Điều này giải thích tại sao visited theo chỉ (r,c) là **sai**, và visited theo (r,c,used) là **đúng**.

## 13. Độ phức tạp theo bản đồ và luật

Đặt **N=R·C** số ô lưới.

| Thuật toán/luật | Số trạng thái tối đa | Thời gian | Bộ nhớ |
|---|---:|---:|---:|
| BFS bốn hướng, unit cost | N | **O(N)** | **O(N)** |
| BFS tám hướng, unit cost | N | **O(N)** | **O(N)** |
| Dijkstra bốn hướng, nonnegative terrain | N | **O(N log N)** | **O(N)** |
| A* với PQ, cùng lưới hữu hạn và heuristic đúng | N | Cận đồ thị ngầm thường **O(N log N)** trong mô hình này | **O(N)** |
| BFS với tối đa k lượt vượt tường | N·(k+1) | **O(N(k+1))** | **O(N(k+1))** |

Với lưới bốn hoặc tám hướng, số cạnh `E` là O(N), nên dạng tổng quát BFS O(V+E) trở thành O(N). Tương tự, heap Dijkstra với số mục stale O(E) vẫn có cận O(N log N) trên lưới bậc hữu hạn.

**Chi phí parent:** mảng trước đó của BFS/Dijkstra O(N), mảng `previous[r][c][used]` của BFS tài nguyên O(N(k+1)). Đầu ra đường đi có thể dài O(N) trong một đường đơn trên lưới cơ bản, nên vẫn phải tính thời gian O(length) để dựng output.

**Với chuỗi thao tác thời gian, hướng và keyMask**: thay V bằng **số trạng thái mở rộng thực**, ví dụ O(RC·2^p) với p chìa khóa nhị phân. Không được vẫn ghi O(RC) sau khi thêm một mask lớn.

### Giới hạn bộ nhớ trên Java

Một `boolean[R][C][k+1]` và `Walk[R][C][k+1]` không chỉ dùng một phần tử cho mỗi ô: chúng có **tích ba chiều** phần tử, cộng overhead của các mảng Java. Khi R,C,k lớn, có thể gây `OutOfMemoryError`. Cần ước lượng trước R·C·(k+1) bằng **long** và chọn giới hạn theo bộ nhớ thực tế; khi trạng thái thưa, cân nhắc `HashSet<Long>`/map parent theo trạng thái đạt được hoặc các phương pháp pruning có chứng minh.

**Không gian cần xét của ví dụ chỉ vừa phải**; chương trình minh họa giả định lưới và K phù hợp RAM, ngoài kiểm tra k≥0 và phép cắt K về số ô tường.

## 14. Những biến thể khó hơn

### 14.1. Đếm số đường ngắn nhất

Nếu mỗi bước có chi phí 1, sau khi BFS tính dist, có thể giữ `ways[state]`:

- `ways[start]=1`.
- Nếu lần đầu khám phá v ở dist[u]+1, gán ways[v]=ways[u].
- Nếu đã biết `dist[v]=dist[u]+1`, cộng `ways[v]+=ways[u]`.

Đếm số đường đi ngắn nhất theo dãy trạng thái; nếu kết quả có thể rất lớn, dùng modulo theo đề hoặc `BigInteger`. **Không cộng số đường vào một ô từ những state có dist khác tầng**, và không dùng mỗi parent đơn lẻ để suy số đường.

Với Dijkstra có trọng số **dương**, cũng có thể đếm số đường ngắn nhất theo dist với xử lý đúng thứ tự. Nếu cho cạnh trọng số 0, các cạnh bằng khoảng cách có thể tạo chu trình; việc đếm số đường đi cần định nghĩa rõ **đường đơn** hay **walk**, vì có thể có vô số walk tối ưu khi chu trình 0 tồn tại.

### 14.2. Nhiều nguồn hoặc nhiều đích

Nếu cùng một loại bước giá 1 và hỏi khoảng cách tới **nguồn gần nhất**, đưa **tất cả nguồn hợp lệ** vào queue ngay từ đầu với dist=0. BFS multi-source cho dist tới nguồn gần nhất với một lần duyệt. Tương tự Dijkstra có thể khởi tạo nhiều nguồn với cost0.

Nếu có nhiều đích và cần đến **một đích bất kỳ**, dừng khi pop đích đầu tiên tương ứng theo BFS/Dijkstra. Nếu cần đi qua **tất cả đích**, phải thêm trạng thái đã thăm các đích hoặc mô hình bài toán khác.

### 14.3. Bidirectional BFS

Trên lưới đơn vị có đúng một S và G, có thể BFS từ cả hai phía và gặp nhau để giảm số trạng thái mở rộng thực tế trong một số bản đồ. Nhưng việc phát hiện giao và dừng cần bảo đảm đã tối thiểu hóa **tổng khoảng cách hai phía**, nhất là khi mở rộng các frontier không cân đối. Nếu có trạng thái tài nguyên hoặc luật chuyển **có hướng**, duyệt ngược từ G cần định nghĩa **phép chuyển ngược hợp lệ**, không thể tùy tiện dùng cùng luật đi tiến.

### 14.4. Dịch chuyển/portal

Nếu có cổng đưa từ ô u sang ô v với chi phí 1, đó là **một cạnh thêm** của đồ thị. BFS vẫn đúng nếu mọi cạnh (kể cả portal) giá 1; nhưng Manhattan có thể **overestimate** chi phí còn lại và không còn admissible. Với portal giá 0 và ô thường giá 1, xem xét **0–1 BFS**; với portal có giá bất kỳ không âm, dùng Dijkstra hoặc heuristic đã chứng minh.

### 14.5. Luật theo hướng và đổi hướng

Nếu một phép di chuyển chỉ hợp lệ khi đang quay về phía nào, hoặc đổi hướng phải trả phí, trạng thái cần chứa **direction**. Tối ưu phí có thể dùng Dijkstra trên `(r,c,dir)`. Nếu mỗi lệnh “đi tới”, “quay trái”, “quay phải” đều giá 1, BFS trên state mở rộng có thể tối ưu **số lệnh**.

### 14.6. Thời điểm và ô chặn động

Nếu đèn mở mỗi p lượt, một state có thể gồm `(r,c,t mod p)`. Trong một vài bài cần bước **WAIT** (đứng yên đợi 1 đơn vị thời gian), phải thêm đúng một cạnh chuyển chờ. Nếu không bổ sung WAIT, thuật toán có thể báo không đường dù thực tế được phép đợi là đến được.

Với chướng ngại thay đổi tùy ý ngoài tính chu kỳ, tiền xử lý dist/parent từ bản đồ trước có thể hết giá trị; cần cập nhật hoặc tính lại theo yêu cầu.

### 14.7. Luật phá tường vĩnh viễn

Trong phiên bản mẫu, bước vào `#` là dùng một lượt tài nguyên và trạng thái chỉ nhớ **số lượt đã dùng**. Nếu một bức tường khi bị phá **biến thành ô trống vĩnh viễn**, và sau đó ta có thể quay lại qua nó không tốn lượt, trạng thái vật lý phải nhớ **tường nào đã phá**. Với p tường đặc biệt có thể cần `(r,c,mask)`; nếu p lớn, state sẽ tăng mũ. Không thể chỉ dùng used nếu lịch sử đập những tường nào có thể ảnh hưởng bước sau.

## 15. Những lỗi thường gặp

1. **Quên phân biệt ít bước với ít chi phí:** BFS không giải đường có ô nặng 9 nếu mục tiêu là tổng cost.
2. **Áp quy tắc di chuyển không có trong đề:** thêm bước chéo không được phép làm sai đáp án.
3. **Cho phép đi chéo xuyên góc tường mặc dù đề cấm:** đường ma không hợp lệ.
4. **Cấm cắt góc theo điều kiện sai:** chính sách nghiêm ngặt yêu cầu **cả hai ô bên cạnh mở**, không phải chỉ một trong hai.
5. **Kiểm ô bên cạnh trước khi kiểm biên của bước chéo:** có thể truy cập chỉ số ngoài mảng.
6. **Không kiểm tra ô đích là tường trước khi enqueue:** có đường xuyên chướng ngại.
7. **Quên kiểm chỉ số âm hoặc ≥R/C:** `ArrayIndexOutOfBoundsException`.
8. **Nhầm row và column:** chỉ số [r][c], không đảo thành [c][r].
9. **Coi ký tự chữ số trong bản đồ là không đi được:** phụ thuộc hợp đồng, ở đây chữ số là ô đi được có chi phí vào.
10. **Dùng visited-on-first-enqueue của BFS cho Dijkstra:** lần khám phá đầu tiên có thể đắt hơn đường tới sau.
11. **Đánh dấu closed Dijkstra khi mới push vào PQ:** phải chốt khi pop bản ghi cost nhỏ nhất hợp lệ.
12. **Không bỏ stale entries trong priority queue:** mở lại cùng trạng thái dư thừa và có thể xử lý sai parent.
13. **Tính chi phí của ô S khi đang đứng sẵn ở start:** theo hợp đồng này start cost 0.
14. **Quên tính phí vào ô G:** ở đây bước vào G có chi phí 1.
15. **Nhầm phí rời ô với phí vào ô:** phải theo đúng mô hình đề.
16. **Dùng Manhattan làm đáp án ngay khi có tường:** Manhattan là lower bound, không phải đường thực.
17. **Dùng Manhattan cho tám hướng giá1:** có thể overestimate; dùng Chebyshev hoặc h khác được chứng minh.
18. **Tuyên bố h admissible khi có portal rẻ mà chưa chứng minh:** có thể làm A* sai.
19. **Dùng closed-only A* với heuristic inconsistent:** cần reopen hoặc heuristic consistent.
20. **Dừng A* khi vừa nhìn thấy goal ở hàng xóm:** không bảo đảm tối ưu chung.
21. **Quên tài nguyên còn lại trong state:** cùng ô nhưng used khác nhau có tương lai khác nhau.
22. **Chỉ lưu parent theo (r,c) cho BFS phá tường:** không dựng đúng chuỗi state.
23. **Tính lượt phá tường ở ô đang đứng thay vì ô chuẩn bị bước vào:** có thể cộng sai cho start/goal.
24. **Bắt ép k không lớn hơn số tường theo mô hình không thích hợp:** trong mã, chỉ cắt vì đường tối ưu đơn không lặp; bài có cơ chế khác phải chứng minh lại.
25. **Gộp luật tường phá vĩnh viễn với ngân sách bước vào tường:** lịch sử trạng thái khác nhau.
26. **Tính số expanded bằng distance:** hai đại lượng khác nhau.
27. **Không trả -1 khi không tới goal:** tránh lấy trạng thái “gần goal” rồi gọi là đường tìm được.
28. **Cho phép hàng bản đồ có độ dài khác nhau:** tọa độ và mảng sẽ lỗi.
29. **Không kiểm tra đúng một S/G:** tình huống thiếu/nhân đôi đích bị hiểu sai.
30. **Sử dụng DFS thường rồi kết luận đường tìm được là ngắn nhất:** DFS không bảo đảm ít bước.
31. **Tràn int/long khi cộng chi phí hoặc tính size mở rộng:** kiểm số học và RAM.
32. **Quên rằng đổi thứ tự hướng có thể đổi path cụ thể:** nên so tối ưu bằng cost/distance và tính hợp lệ, không luôn cố định một path duy nhất.
33. **Truy vết parent nhưng không đảo ngược:** đường được in từ G về S.
34. **Đếm số đường ngắn nhất bằng một parent:** chỉ biết một đường, không phải tổng số.
35. **Bỏ WAIT trong bài được phép đợi:** đồ thị state bị thiếu cạnh.
36. **Dùng cùng tập cạnh đi tiến khi tìm từ G trên luật một chiều:** cần đồ thị ngược hợp lệ.

## 16. Kiểm thử độc lập và chứng nhận kết quả

Một triển khai có thể in path “trông hợp lý” nhưng vẫn không phải đường tối ưu. Vì vậy nên so với **oracle khác cơ chế** và kiểm từng bước path.

### Oracle cho BFS bốn/tám hướng

Trên lưới nhỏ, dựng các cạnh chuyển hợp lệ đúng luật rồi chạy **Bellman–Ford** hoặc một thuật toán đường đi khác, không dùng cùng queue FIFO. Vì mọi cạnh có giá 1, khoảng cách oracle phải bằng BFS. Với corner policy, kiểm riêng:

- Lưới 2×2 `S#/#G` với cho phép cắt góc ⇒ 1.
- Cùng bản đồ cấm cắt góc nghiêm ngặt ⇒ −1.
- Lưới trống 3×3 bốn hướng ⇒ 4; tám hướng giá1 ⇒ 2.
- Bức tường ép vòng ⇒ kết quả bằng đường vòng thật, không bằng Manhattan.

### Oracle cho Dijkstra địa hình

Trên lưới nhỏ có chi phí 1..9, dùng **Bellman–Ford relaxation** để tính khoảng cách thật theo quy tắc “trả phí khi **vào ô**”. So `DijkstraCost==OracleCost` và tính tổng chi phí thực của path theo từng ô đích. Tạo ca mà đường **nhiều bước hơn nhưng rẻ hơn**, như `S91G/1111`.

### Oracle cho phép vượt k tường

Dựng đồ thị mở rộng gồm các state `(r,c,used)` có `0≤used≤k`. Dùng một oracle relaxation khác BFS để tính ít bước nhất qua mọi trạng thái goal, rồi so với BFS mở rộng. Tạo riêng:

- k=0 với đường không có tường.
- k=0 khi mọi đường phải đi qua tường ⇒ −1.
- k=1 cho `S#G` ⇒ 2.
- k=2 cho `S##G` ⇒ 3.
- Có nhiều đường đến cùng ô với used khác nhau, để bắt lỗi visited chỉ theo tọa độ.

### Kiểm tra path như một chứng cứ

Với mỗi kết quả có đường:

1. Phần tử đầu là `S` và cuối là `G`.
2. Từng cặp ô liên tiếp phải đúng một trong các hướng cho phép.
3. Không ô nào ngoài biên.
4. Nếu không được phá tường, mọi ô trên path đều không phải `#`.
5. Nếu cấm cắt góc, mọi bước chéo phải có **hai ô cạnh bên mở**.
6. Với BFS unit, `path.size()−1=distance`.
7. Với Dijkstra terrain, tổng **phí đi vào từng ô sau S** bằng reported cost.
8. Với BFS phá tường, số lần bước vào `#` trên path bằng `broken` và không vượt k.

Nếu một đường có cùng cost tối ưu nhưng khác path oracle, **không nhất thiết sai**. Có thể có nhiều đường tối ưu; đối chiếu **giá trị và hợp lệ của từng bước**.

## 17. Bài tập mở rộng

**Bài 1 — Rook movement.** Được đi theo một hàng/cột bất kỳ trong **một nước**, miễn tất cả ô trung gian không có tường. Nếu mỗi lần di chuyển rook giá 1, state vẫn (r,c) nhưng **mỗi lượt có thể sinh nhiều ô cùng hàng/cột**, không chỉ bốn ô kề. BFS vẫn có thể đúng; độ phức tạp phụ thuộc cách tối ưu sinh các ô rook có thể đến.

**Bài 2 — Knight movement.** Quân mã đi theo `(±1,±2)` và `(±2,±1)`, không chịu quy tắc corner-cutting của vua đi chéo. Mỗi bước mã giá1, BFS đúng nếu chỉ cần số nước đi. Không dùng Manhattan trực tiếp làm chi phí thật.

**Bài 3 — Maze with key.** Có cửa A chỉ mở khi nhặt chìa a. State cần `(r,c,hasA)`. Hãy chứng minh vì sao visited[r][c] đơn thuần có thể cắt mất nghiệm khi quay lại cùng ô sau khi lấy chìa.

**Bài 4 — Tường có giá phá khác nhau.** Nếu bước vào tường A tốn 3, tường B tốn 1 và ô thường tốn 0, mà mục tiêu là **ít tiền phá nhất**, mô hình cạnh có trọng số 0,1,3 và dùng Dijkstra; không phải BFS theo số bước.

**Bài 5 — Đường đi ngắn nhất theo thứ tự ưu tiên.** Trước hết tối thiểu số tường đã phá, rồi mới tối thiểu số bước. Hãy xây một hàm chi phí theo cặp `(broken,steps)` với so sánh từ điển, hoặc chứng minh một phép biến đổi về chi phí một chiều với hằng số đủ lớn theo kích thước state hữu hạn.

**Bài 6 — Robot tính phí đổi hướng.** Robot đang quay mặt lên, mỗi lệnh quay trái/phải mất 1, đi thẳng một ô mất 1. State `(r,c,dir)`; BFS theo lệnh sẽ tối thiểu số lệnh, không phải chỉ tối thiểu số ô đã đi.

**Bài 7 — A* có portal.** Cổng nhảy từ một góc bản đồ sang gần goal với giá 1. Hãy chỉ ra vì sao Manhattan có thể overestimate và xây một heuristic luôn admissible, tối thiểu là h=0.

## 18. Checklist trước khi nộp

- Đề tối ưu **số bước**, **tổng chi phí**, **số tường phá** hay một thứ tự ưu tiên?
- Có đánh số row/column thống nhất, kiểm biên cho mọi bước?
- Đúng tập hướng 4, 8, rook, knight hay hành động riêng?
- Với bước chéo, đề có **cho phép cắt góc** không? Nếu cấm, đã kiểm **cả hai ô cạnh bên**?
- Ô tường có phải tuyệt đối không được đi, hay có quyền tiêu tài nguyên?
- Nếu có terrain, phí đặt ở ô **đến**, ô **đi** hay trên cạnh?
- Mọi bước giá1 thì dùng BFS; 0/1 dùng deque; không âm dùng Dijkstra/A*?
- Nếu dùng A*, heuristic có **admissible** và có consistent cho chính luật đi đang triển khai?
- State đã chứa **usedBreaks, direction, keyMask, time** khi chúng ảnh hưởng tương lai?
- visited có đúng số chiều theo khóa state, không hợp nhất trạng thái khác nhau?
- Khi dùng Dijkstra, có lưu best cost, bỏ stale entry và chỉ chốt khi pop?
- Khi không có đường, có trả một sentinel rõ ràng và path rỗng?
- Khi có đường, parent có hợp lệ, path có đi từ S tới G theo đúng cạnh hợp lệ?
- Với k tường, số lượt dùng có không vượt ngân sách? Có tách phá-vào-ô với phá-vĩnh-viễn?
- Chi phí path có khớp số báo cáo, đặc biệt phí vào goal?
- Thời gian/bộ nhớ đã tính theo **số state thực**, không chỉ số ô?
- Có lưu ý nguy cơ RAM khi dùng `R·C·(k+1)` mảng ba chiều?
- Đã thử ô trống, đường vòng, bức tường bít, góc 2×2, terrain đắt và nhiều mức k?
- Đã so với một oracle độc lập, không chỉ so các đường do cùng solver trả?

**Kết luận:** lưới là một cách biểu diễn **đồ thị trạng thái ngầm**; vấn đề quyết định không chỉ là chướng ngại nằm đâu mà là **từ một trạng thái được chuyển sang trạng thái nào, với chi phí bao nhiêu và cần nhớ thông tin gì**. Khi mọi bước cùng giá1, BFS theo luật chuyển đúng tìm ít bước nhất; với phí địa hình không âm, Dijkstra tìm tổng chi phí nhỏ nhất; với heuristic đã chứng minh, A* có thể ưu tiên hiệu quả mà vẫn tối ưu. Khi có ngân sách vượt tường hoặc điều kiện phụ thuộc lịch sử, mở rộng khóa state và mảng visited/parent tương ứng. Một bài pathfinding đáng tin không chỉ đưa ra số nhỏ nhất, mà còn phải chứng minh **đường có thật, mọi bước hợp lệ và giá trị phù hợp đúng luật của đề**.