# A* với heuristic chấp nhận được và nhất quán

Trong nhóm **Tìm kiếm trạng thái** của Computer Science Algorithms, A* (đọc là “A-star”) là một thuật toán tìm đường đi có chi phí nhỏ nhất, kết hợp chi phí đã trả từ điểm xuất phát với một **ước lượng** chi phí còn lại đến mục tiêu. Sức mạnh của A* không đến từ việc “đoán đúng đường” một cách thần kỳ: nó dựa trên điều kiện toán học chính xác của **heuristic**. Hai tính chất cần hiểu rõ là **chấp nhận được (admissible)** và **nhất quán (consistent/monotone)**.

Bài học **“A* với heuristic chấp nhận được và nhất quán”** đi từ mô hình không gian trạng thái, biểu thức **f(n)=g(n)+h(n)**, cách tổ chức open/closed, điều kiện dừng khi lấy goal khỏi hàng đợi ưu tiên, đến chứng minh bảo đảm tối ưu. Trọng tâm đặc biệt là khác biệt: *admissible* không nhất thiết *consistent*, vì vậy nếu đóng vĩnh viễn trạng thái với heuristic không nhất quán thì có thể trả lời sai; bản A* an toàn trong trường hợp đó phải hỗ trợ **mở lại trạng thái** khi tìm thấy g tốt hơn.

Có hai ví dụ đối chiếu: một đồ thị bốn đỉnh trong đó thuật toán **không mở lại** trả chi phí 5 thay vì tối ưu 4, và một bản đồ đi bốn hướng có vật cản, trong đó Manhattan h(start)=4 nhưng đường ngắn nhất có chi phí 8. Chương trình Java 17+ độc lập ở cuối bài kiểm chứng cả hai và kiểm tra A* với Bellman–Ford trên **4.113 đồ thị nhỏ vét cạn và 700 đồ thị sinh có seed**.

## 1. Bài toán tìm kiếm trạng thái và đường đi chi phí nhỏ nhất

Ta mô hình hóa bài toán thành đồ thị có hướng G=(V,E). Mỗi **đỉnh** đại diện cho một trạng thái; mỗi **cạnh có hướng** u→v là một phép chuyển trạng thái hợp lệ với chi phí c(u,v). Cho trạng thái xuất phát s và trạng thái mục tiêu t, cần tìm một chuỗi chuyển hợp lệ có **tổng chi phí nhỏ nhất**.

Trong phạm vi bài và chương trình mẫu:

- Số trạng thái **hữu hạn** và có thể lưu với chỉ số từ 0 tới n−1.
- Chi phí cạnh **không âm**, bao gồm khả năng bằng 0.
- Một trạng thái xuất phát và một mục tiêu cố định.
- Nếu không có đường s→t, trả **INF** (không thể tới).
- Nếu s=t, đường đi dài 0 cạnh có chi phí 0.

A* không mặc định phù hợp với đồ thị có cạnh âm. Nếu có cạnh âm hoặc chu trình âm, cần xem lại định nghĩa bài toán và chọn thuật toán phù hợp, như Bellman–Ford trong các trường hợp cho phép. Trạng thái trong ứng dụng có thể là một vị trí bản đồ, một cấu hình puzzle, một trạng thái robot hoặc một bước trong trò chơi; **cạnh phải phản ánh chính xác hành động được phép**.

## 2. Ba đại lượng g, h và f

Với mỗi trạng thái v:

~~~text
g(v) = chi phí của đường đi s → v tốt nhất
       mà thuật toán hiện biết.

h(v) = ước lượng chi phí từ v → t
       do người thiết kế heuristic cung cấp.

f(v) = g(v) + h(v).
~~~

A* đặt trong **hàng đợi ưu tiên (open set)** các trạng thái có thể mở rộng, ưu tiên trạng thái có **f nhỏ nhất**. g là chi phí thực của một đường đã biết; h là dự báo tương lai; f là đánh giá tổng chi phí của đường qua v.

**Đừng nhầm g(v) với g*(v):** g*(v) là chi phí tối ưu thật từ s đến v, thường chưa biết. Trong khi chạy, g(v) có thể lớn hơn g*(v) và về sau được giảm khi phát hiện đường tốt hơn. Tương tự, h*(v)=d(v,t) là chi phí nhỏ nhất thật sự còn lại; heuristic chỉ cần thỏa những tính chất nhất định chứ không nhất thiết bằng h*(v).

Với bản A* graph search dùng parent, mỗi lần tìm được đường mới đến v tốt hơn trước:

~~~text
tentative = g(u) + c(u,v).

Nếu tentative < g(v):
    g(v) = tentative.
    parent(v) = u.
    đưa v vào open với khóa f(v)=g(v)+h(v).
~~~

Việc giảm **g** phải kéo theo cập nhật **f** và parent. Không được lấy **h** làm trọng số cạnh hoặc cập nhật h bằng tổng đường đi; h là một hàm ước lượng được xác định theo trạng thái.

## 3. Heuristic chấp nhận được (admissible)

Heuristic là **chấp nhận được** khi nó **không bao giờ ước lượng cao hơn chi phí tối ưu còn lại**:

~~~text
h(v) <= h*(v) = d(v,t)
              với mọi v có đường tới t.

h(t) = 0 trong quy ước thông dụng.
~~~

Với trạng thái không thể tới t, h*(v)=INF nên một giá trị h(v) hữu hạn, không âm luôn là một lower bound theo quy ước này.

**Ý nghĩa:** h không được quá lạc quan theo nghĩa ngôn ngữ thông thường? Thực tế, heuristic chấp nhận được phải **lạc quan về chi phí**: dự đoán có thể *thấp hơn*, nhưng không được *cao hơn* chi phí tối ưu. Một heuristic 0 ở mọi đỉnh luôn admissible nếu chi phí không âm, nhưng h=0 không tận dụng được thông tin về mục tiêu.

Ví dụ một trạng thái A có chi phí thật để đến t là 2:

~~~text
h(A)=0: admissible, dự đoán yếu.
h(A)=1: admissible.
h(A)=2: admissible, chính xác.
h(A)=3: không admissible, đã ước lượng quá cao.
~~~

Phải xác định **hướng của chi phí**: trong đồ thị có hướng, d(v,t) không nhất thiết bằng d(t,v). Lấy khoảng cách theo chiều ngược mà không chứng minh quan hệ lower bound có thể phá tính admissible.

## 4. Heuristic nhất quán (consistent/monotone)

Heuristic là **nhất quán** khi với **mọi cạnh chuyển trạng thái** u→v có chi phí c(u,v):

~~~text
h(u) <= c(u,v) + h(v).

Kèm điều kiện h(t)=0.
~~~

Đây là một bất đẳng thức giống **bất đẳng thức tam giác**: dự đoán từ u không được lớn hơn chi phí bước đầu u→v cộng với dự đoán từ v.

Ta có thể kiểm tra consistency **cục bộ qua từng cạnh**, trong O(|E|) thời gian nếu tất cả trạng thái/cạnh đã hiện hữu. Không cần biết đường đi ngắn nhất thực sự. Hàm isConsistent trong chương trình Java kiểm tra h(t)=0, miền h, rồi duyệt từng cạnh để kiểm tra điều kiện trên.

Ví dụ khi c(u,v)=1:

~~~text
h(u)=4, h(v)=3  => 4 <= 1+3: đúng.
h(u)=4, h(v)=4  => 4 <= 1+4: đúng.
h(u)=4, h(v)=2  => 4 <= 1+2: sai.
~~~

Một heuristic có thể admissible tại cả u và v nhưng vẫn **không consistent** trên cạnh u→v. Sự khác biệt này quyết định có thể đóng vĩnh viễn một trạng thái sau lần mở rộng đầu tiên hay không.

## 5. Chứng minh consistency suy ra admissibility

Giả sử h(t)=0 và với mọi cạnh u→v, h(u)≤c(u,v)+h(v). Xét một đường bất kỳ:

~~~text
v0 → v1 → v2 → ... → vk=t.
~~~

Lặp bất đẳng thức consistency:

~~~text
h(v0) <= c(v0,v1) + h(v1)
      <= c(v0,v1) + c(v1,v2) + h(v2)
      ...
      <= Σ c(vi,vi+1) + h(t)
       = tổng chi phí của đường đang xét.
~~~

Vì h(v0) nhỏ hơn hoặc bằng **chi phí của mọi đường từ v0 tới t**, nó nhỏ hơn hoặc bằng **chi phí nhỏ nhất**:

~~~text
h(v0) <= h*(v0).
~~~

Vậy **consistent + h(goal)=0 ⇒ admissible**. Điều ngược lại **không đúng**: h có thể không vượt h* ở từng đỉnh mà vẫn giảm quá mạnh giữa hai đầu một cạnh, vi phạm h(u)≤c+h(v).

Đối với những đỉnh không có đường tới goal, không có đường để áp dụng chuỗi bất đẳng thức; mọi h hữu hạn không âm đều thỏa upper-bound INF theo quy ước. Mã dùng h hữu hạn ở mọi đỉnh để giữ ưu tiên f trong miền long.

## 6. Vì sao consistency khiến f không giảm dọc đường?

Nếu từ u đến v qua cạnh c(u,v) trong một quá trình mở rộng đường đi, chi phí đường theo cạnh là g(v)=g(u)+c(u,v). Khi đó:

~~~text
f(v) = g(u)+c(u,v)+h(v).

Consistency: h(u) <= c(u,v)+h(v).

Suy ra:
f(v) >= g(u)+h(u) = f(u).
~~~

Với một đường đi được kéo dài **theo các cạnh và chi phí g của chính đường đó**, giá trị f là **không giảm**. Đây là tính chất **monotonicity**, cũng là lý do thuật toán dùng heuristic nhất quán có thể xử lý trạng thái theo hướng “chốt” một lần.

**Lưu ý về cách diễn đạt:** trong code, g(v) toàn cục có thể được cải thiện bởi một đường đến v khác, khiến bản ghi ưu tiên cũ trở nên lỗi thời. Vì thế mệnh đề f không giảm nói về **các bước nối dài một đường dưới một heuristic nhất quán**, không có nghĩa mọi bản ghi được push vào heap đều phải có f lớn hơn mọi bản ghi push trước đó.

## 7. A* graph search với open, closed và parent

Một cách cài phổ biến lưu:

- **g[v]**: chi phí tốt nhất đã biết từ s tới v; ban đầu g[s]=0, đỉnh khác INF.
- **h[v]**: lower bound cho chi phí v→t, theo đúng hợp đồng heuristic.
- **parent[v]**: đỉnh ngay trước v trên đường tốt nhất đang biết để khôi phục đường.
- **open**: priority queue sắp theo f=g+h, có thể chứa nhiều bản ghi của cùng v.
- **closed[v]**: v đã được mở rộng với bản g hiện tại.
- **reopened**: số lần một đỉnh closed bị mở lại khi tìm thấy g nhỏ hơn.

Pseudo-code cho bản **consistent**:

~~~text
g[s] = 0, parent[s] = -1, push (s, f=h[s]).
while open không rỗng:
    lấy bản ghi có f nhỏ nhất
    nếu bản ghi cũ (không còn bằng g[v]): bỏ qua
    nếu v đã closed: bỏ qua

    đánh dấu closed[v]
    nếu v == goal: trả g[v] và đường parent

    với mỗi cạnh v -> w:
        nếu w đã closed: bỏ qua (chỉ an toàn nếu h consistent)
        tentative = g[v] + cost(v,w)
        nếu tentative < g[w]:
            g[w] = tentative
            parent[w] = v
            push (w, f=g[w]+h[w])

Nếu open rỗng: không có đường, trả INF.
~~~

Khi heuristic consistent, việc không mở lại closed được bảo đảm đúng. Với heuristic chỉ admissible, cần dùng biến thể ở mục 10: cho phép cải thiện g[w] **ngay cả khi w đã closed** và đặt closed[w]=false để w được mở rộng lại.

## 8. Vì sao chỉ dừng khi lấy goal ra khỏi open?

Một lỗi thường gặp là **dừng ngay khi phát hiện goal là hàng xóm** của đỉnh đang mở rộng. Khi mới tìm ra một đường tới goal, đường ấy chỉ là một ứng viên; có thể tồn tại đường khác rẻ hơn vẫn đang chờ trong open.

Điều kiện dừng tiêu chuẩn cho graph search đúng giả thiết là:

~~~text
Lấy một bản ghi hợp lệ của goal
ra khỏi priority queue với f nhỏ nhất,
sau khi loại các bản ghi g lỗi thời.
~~~

Vì h(goal)=0, với goal ta có f(goal)=g(goal). Khi heuristic admissible và thuật toán hỗ trợ reopen nếu cần, nếu còn một đường tối ưu tốt hơn thì trên đường đó sẽ có một trạng thái biên chưa được xử lý với **f không vượt giá trị tối ưu C***. Bản goal mang chi phí lớn hơn C* không thể là bản có f nhỏ nhất hợp lệ ở thời điểm đó.

Với heuristic consistent, điều kiện còn mạnh hơn: **lần đầu lấy một đỉnh khỏi open để mở rộng, g của đỉnh ấy đã là tối ưu**. Khi goal được lấy ra, ta chắc chắn tìm được đường ngắn nhất. Không được dùng điều kiện dừng “vừa push goal thì xong”, trừ khi có một chứng minh riêng của bài đặc biệt.

## 9. Bất biến và chứng minh A* với heuristic consistent

Giả sử tất cả cạnh có chi phí không âm, h(t)=0 và h consistent.

**Bất biến khi mở rộng:** một đỉnh đã được lấy khỏi open bằng bản g hợp lệ và chốt closed sẽ có g đúng bằng **chi phí tối ưu thật** từ s tới đỉnh đó.

Phác thảo chứng minh phản chứng. Giả sử u là đỉnh đầu tiên bị chốt với g(u)>g*(u). Xét một đường tối ưu s→...→u; vì u chưa được đi tới theo chi phí tối ưu, tồn tại một đỉnh x đầu tiên trên đường ấy chưa được chốt, trong khi tiền nhiệm của nó đã được chốt với chi phí tối ưu. Bước relax đã đưa x vào open với chi phí đúng g*(x) (hoặc tốt hơn).

Do h consistent, khi so f của x với bất kỳ đường đi qua các đỉnh tiếp theo trên đường tối ưu tới u, h(x) bị chặn bởi chi phí phần đường x→u cộng h(u). Do đó:

~~~text
f(x)=g*(x)+h(x)
    <= g*(u)+h(u)
    <  g(u)+h(u)=f(u).
~~~

Vậy x có ưu tiên nhỏ hơn u, mâu thuẫn với việc u được lấy ra để chốt trước x. Bất biến giữ cho mọi lần mở rộng.

**Hệ quả:** khi consistent, một đỉnh không cần được mở lại vì một đường rẻ hơn; thuật toán có thể dùng closed như tập chốt vĩnh viễn. Khi goal được lấy ra, g(goal)=g*(goal), nên tối ưu.

## 10. Admissible nhưng không consistent: phải cho phép reopen

Admissible chỉ yêu cầu h(v)≤h*(v), không ép chênh lệch h giữa hai đầu cạnh bị giới hạn. Vì vậy một đỉnh u có thể bị mở rộng theo đường **chưa tối ưu**, rồi sau đó có một đường khác đi qua v làm g(u) giảm.

Nếu code **đóng vĩnh viễn u**, bỏ qua mọi đường tốt hơn tới u khi u đã closed, nó có thể không gửi cải thiện đó tới các đỉnh tiếp theo và trả goal với chi phí sai.

Bản A* hỗ trợ **reopen** dùng:

~~~text
Nếu tentative < g[w]:
    g[w] = tentative
    parent[w] = v

    nếu closed[w]:
        closed[w] = false
        reopened++

    push (w, g[w]+h[w]).
~~~

Mỗi lần giảm g mới có quyền mở lại, không phải cứ gặp cạnh tới closed là mở lại. Trong đồ thị hữu hạn có chi phí không âm và heuristic admissible, phiên bản này giữ khả năng lan truyền những đường tốt hơn và có thể dừng đúng lúc goal được lấy ra hợp lệ.

**Phạm vi bảo đảm:** nếu h **không admissible**, reopen cũng **không tự cứu** tính tối ưu; heuristic có thể đẩy những nhánh của đường tối ưu về sau goal sai. Vì vậy điều kiện chấp nhận được và cơ chế reopen là **hai vấn đề khác nhau**.

## 11. Phản ví dụ bốn đỉnh có thể chạy tay

Xét đồ thị có hướng s=0, a=1, b=2, t=3:

~~~text
Các cạnh:
s -> a: 3
s -> b: 1
b -> a: 1
a -> t: 2
b -> t: 10

Chi phí tối ưu thật tới goal:
h*(s)=4, h*(a)=2, h*(b)=3, h*(t)=0.

Đường tối ưu:
s -> b -> a -> t
tổng = 1+1+2 = 4.
~~~

Heuristic thứ nhất:

~~~text
h(s)=4, h(a)=0, h(b)=3, h(t)=0.
~~~

Nó **admissible**, vì ở mọi đỉnh đều h≤h*. Nhưng nó **inconsistent**:

~~~text
Cạnh s -> a có cost=3:
h(s)=4 > 3+h(a)=3.

Cạnh b -> a có cost=1:
h(b)=3 > 1+h(a)=1.
~~~

Với h này, A* từ s đưa a vào open với g(a)=3, f(a)=3; b với g(b)=1, f(b)=4. A* chọn **a trước b**, dù đường tốt nhất đến a phải đi qua b.

## 12. Vết mở rộng: closed sai và reopen đúng

Sau khi a được mở rộng với g=3, thuật toán tìm được t theo đường s→a→t chi phí **5**. Lúc này t có f=5, còn b có f=4 nên b vẫn được mở rộng trước t.

Từ b ta phát hiện đường tốt hơn tới a:

~~~text
g mới của a = g(b)+cost(b,a) = 1+1 = 2
< g cũ của a = 3.
~~~

**Nếu không cho mở lại a**: vì a đã closed, cải thiện bị bỏ qua. Cuối cùng t được pop với g=5, sai vì đường s→b→a→t có chi phí 4.

**Nếu cho reopen a**: cập nhật g(a)=2, parent[a]=b, closed[a]=false và push a với f=2. A được mở rộng lại và cải thiện g(t) từ 5 xuống 4. T được pop với g=4, đúng.

| Sự kiện | g(a) | g(t) | Kết quả |
| --- | ---: | ---: | --- |
| Pop s, phát hiện a,b | 3 | INF | a có f=3, b có f=4 |
| Pop a lần đầu | 3 | 5 | a từng bị chốt non |
| Pop b | 2 nếu reopen; giữ 3 nếu không | 5 | Cạnh b→a tạo đường rẻ hơn |
| Pop a lần hai (reopen) | 2 | 4 | Truyền cải thiện tới t |
| Pop t | 2 | 4 | Đường [0,2,1,3] tối ưu |

Vậy **admissible không đủ** để dùng closed vĩnh viễn. Trong code, ví dụ không reopen **cố tình đặt tên unsafeNoReopenForDemonstration**, là một trường hợp sai được đưa vào riêng cho mục đích giáo dục; không dùng nó làm API giải bài toán với heuristic bất nhất.

## 13. Cùng đồ thị, heuristic consistent

Với cùng đồ thị, chọn h đúng bằng chi phí thật còn lại:

~~~text
h(s)=4, h(a)=2, h(b)=3, h(t)=0.
~~~

Kiểm tra mọi cạnh:

~~~text
s->a: 4 <= 3+2 đúng.
s->b: 4 <= 1+3 đúng.
b->a: 3 <= 1+2 đúng.
a->t: 2 <= 2+0 đúng.
b->t: 3 <=10+0 đúng.
~~~

Heuristic consistent và admissible. Sau khi mở rộng s:

~~~text
b: g=1, h=3, f=4.
a: g=3, h=2, f=5.
~~~

B được chọn trước a, phát hiện đường tốt hơn s→b→a, giảm g(a)=2 và f(a)=4 **trước khi a được closed**. Khi a mở rộng, nó tạo t với g=4. Kết quả tối ưu, và **reopened=0**.

Trong thực tế, nếu đã biết chính xác h*(v) cho mọi v thì chi phí tính h có thể lớn tương đương giải bài ngắn nhất từ mọi đỉnh; đây là ví dụ lý thuyết để chứng minh tính chất, không phải khuyến nghị “luôn tính h chính xác bằng thuật toán tốn kém”.

## 14. Manhattan cho lưới bốn hướng

Xét trạng thái là ô (r,c) trên lưới, chỉ được đi **lên, xuống, trái, phải** mỗi bước chi phí 1; ô cản không được đi qua. Goal ở (rg,cg).

Heuristic **Manhattan distance**:

~~~text
h(r,c) = |r-rg| + |c-cg|.
~~~

**Admissible:** để tới goal, dù có vật cản hay không, ta phải thay đổi tổng cộng ít nhất |r−rg| hàng và |c−cg| cột bằng các bước đơn vị. Vật cản chỉ có thể làm đường dài **hơn**, không thể làm đường hợp lệ ngắn hơn lower bound đó.

**Consistent:** một bước bốn hướng chi phí 1 làm Manhattan thay đổi nhiều nhất 1. Vì thế h(u)≤1+h(v) trên mọi cạnh đi được; h(goal)=0. Loại bỏ các cạnh bị tường cản không thể phá một bất đẳng thức từng đúng trên tất cả bước hợp lệ.

Manhattan **không tự động admissible** nếu cho phép nhảy qua nhiều ô, đi chéo cùng chi phí 1, dịch chuyển tức thời hoặc có cạnh chi phí nhỏ hơn bước dịch chuyển mà heuristic giả định. Luôn gắn heuristic với **phép chuyển hợp lệ và đơn vị chi phí** của bài.

## 15. Ví dụ lưới có vật cản buộc đi vòng

Đồ thị ô 3 hàng × 5 cột:

~~~text
S . # . G
. . # . .
. . . . .

S ở (0,0), G ở (0,4).
# là ô cấm.
Mỗi bước bốn hướng có giá 1.
~~~

Khoảng Manhattan từ S tới G là 4. Nhưng hai ô tường tại (0,2) và (1,2) chặn đường đi gần như thẳng. Để sang phải, phải xuống hàng 2 rồi đi ngược lên hàng 0.

Một đường hợp lệ ngắn nhất dài **8 bước**:

~~~text
(0,0) → (0,1) → (1,1) → (2,1)
→ (2,2) → (2,3) → (1,3) → (0,3) → (0,4).

ID mỗi ô = r*5+c:
[0,1,6,11,12,13,8,3,4].
~~~

Ở đây h(S)=4 và d(S,G)=8 nên h **đánh giá thấp** chi phí thật nhưng vẫn admissible và consistent. Đây chính là tình huống thường gặp: heuristic bỏ qua một số ràng buộc như tường cản để tạo **cận dưới** nhanh và an toàn.

Bản Java xây lưới thành đồ thị có hướng hai chiều giữa các ô kề hợp lệ, dùng A* với Manhattan và kiểm tra lại bằng Bellman–Ford. Nó chỉ in một đường tối ưu; trong trường hợp có nhiều đường đồng chi phí, thứ tự tie-break của heap có thể chọn đường khác nhưng tổng chi phí phải bằng 8.

## 16. Chọn heuristic nào cho bài của mình?

**Bài lưới bốn hướng với giá 1:** Manhattan là lựa chọn mặc định, vì cả admissible lẫn consistent.

**Lưới tám hướng, đi chéo giá 1:** Manhattan thường **ước lượng cao hơn chi phí thật**; ví dụ từ (0,0) tới (1,1), Manhattan=2 nhưng đi chéo một bước giá 1. Lựa chọn lower bound phù hợp là **Chebyshev** max(|Δr|,|Δc|) khi mọi bước tám hướng giá 1.

**Lưới tám hướng, chéo giá √2, ngang/dọc giá 1:** dùng khoảng **octile**: max(dx,dy)+(√2−1)min(dx,dy), dưới những giả thiết chuẩn về bước di chuyển.

**Đồ thị tọa độ Euclidean:** khoảng cách đường thẳng là lower bound khi **chi phí mỗi cạnh không nhỏ hơn độ dài hình học của cạnh** theo cùng đơn vị. Khi ấy bất đẳng thức tam giác của khoảng cách hình học đem lại consistency.

**Puzzle và trạng thái tổ hợp:** có thể lấy lời giải **bài toán thư giãn** (bỏ bớt ràng buộc) làm heuristic. Vì bài thư giãn cho nhiều lựa chọn hơn, đáp án tối ưu thư giãn thường là lower bound của bài thật. Tuy nhiên phải chứng minh theo chính định nghĩa trạng thái/chuyển chi phí, không chỉ thấy số dự báo “có vẻ hợp lý”.

**Thận trọng với làm tròn:** làm tròn **lên** một khoảng cách thực có thể biến một lower bound thành overestimate. Tùy kiểu dữ liệu, dùng giới hạn chính xác, làm tròn xuống được chứng minh hoặc biểu diễn phù hợp.

## 17. So sánh h=0, h tốt, h quá cao và h không nhất quán

| Heuristic | Có admissible? | Có consistent? | Hành vi cần lưu ý |
| --- | --- | --- | --- |
| h(v)=0 mọi đỉnh (cạnh không âm) | Có | Có | A* tương đương Dijkstra theo thứ tự g, khác tie-break có thể ảnh hưởng số mở rộng |
| h(v)=h*(v) khi xác định được | Có | Có (với goal=0 và cạnh hợp lệ) | Heuristic hoàn hảo nhưng thường đắt để biết trước |
| Manhattan trên lưới bốn hướng giá≥1/ô, không shortcut | Có | Có | Bỏ qua tường cản, vẫn là lower bound |
| Một h≤h* nhưng vi phạm triangle condition | Có | Không | Muốn tối ưu phải cho phép **reopen** |
| Một h>h* ở trạng thái liên quan | Không | Có thể có/không, nhưng nếu consistent và h(goal)=0 thì không thể >h* | Không có bảo đảm tối ưu của A* tiêu chuẩn |
| w·h với w>1 | Không được bảo đảm | Không được bảo đảm | Weighted A* đánh đổi tốc độ/chất lượng; không coi là A* tối ưu thông thường |

Một heuristic càng gần h* có thể hướng việc tìm kiếm tốt hơn, nhưng **không thể khẳng định số đỉnh mở rộng sẽ luôn ít hơn** trong mọi trường hợp và mọi quy tắc xử lý hòa f, đặc biệt khi các heuristic có tính chất khác nhau hoặc có nhiều đường đồng chi phí.

Khái niệm **domination**: h2 dominates h1 nếu với mọi v, h2(v)≥h1(v) mà h2 vẫn admissible. Điều đó biểu thị h2 là lower bound nhiều thông tin hơn, nhưng cần xét điều kiện của bài và tie-breaking trước khi đưa ra kết luận tuyệt đối về số lần mở rộng thực tế.

## 18. Priority queue, stale entry và tie-break

Java PriorityQueue không có sẵn thao tác giảm khóa (*decrease-key*) hiệu quả cho từng phần tử. Một kỹ thuật phổ biến là **push thêm** bản ghi mới khi g giảm, và bỏ qua bản ghi cũ lúc pop.

Trong code:

~~~text
Khi relax tốt hơn:
    best[v] = newG
    push(State(v, newG, newG+h[v])).

Khi pop State(u, recordedG, recordedF):
    nếu recordedG != best[u]:
        đây là bản cũ, bỏ qua.
    nếu closed[u]:
        bỏ qua bản ghi đã chốt tương ứng.
~~~

Comparator ưu tiên theo f nhỏ nhất, sau đó g nhỏ nhất và ID nhỏ nhất để kết quả demo có thể lặp lại. Nhưng **tie-break không thay thế điều kiện admissible/consistent**. Hai cách tie-break có thể làm khác số đỉnh mở rộng hoặc một đường tối ưu được chọn, không được biến một A* sai thành bảo đảm đúng.

Trong bản reopen, khi phát hiện g tốt hơn cho một đỉnh closed, phải **đặt closed[v]=false** trước khi push bản mới, nếu không bản tốt hơn cũng sẽ bị bỏ qua ngay lúc pop. Tránh dùng điều kiện cập nhật g mới **<=** g cũ khi có cạnh cost=0, vì xử lý đường bằng nhau có thể tạo nhiều bản ghi thừa hoặc làm parent lặp. Mã chỉ cập nhật khi **newG < oldG**.

## 19. Khôi phục đường đi và kiểm tra kết quả

Mỗi lần giảm g(v), ghi parent[v]=u với cạnh đang relax u→v. Khi goal được pop đúng điều kiện:

~~~text
pathReversed = []
current = goal
while current != -1:
    append current vào pathReversed
    current = parent[current]

đảo ngược pathReversed.
~~~

Đường bắt đầu tại s và kết thúc tại t. Nếu s=t, parent[s]=−1 và đường trả [s], chi phí 0. Nếu goal không thể tới, trả **INF và danh sách đường rỗng**.

Với đồ thị có **cạnh song song cùng đầu mút**, để kiểm chứng chi phí đường một cách chính xác trong một hệ thống lưu lịch sử cạnh, có thể lưu **ID cạnh cha** thay vì chỉ parent vertex. Bản demo dùng chi phí rẻ nhất của một cặp u→v khi kiểm chứng, vì mọi g cải thiện theo các cạnh không âm đều được relax, và matching đường ngắn nhất không cần chọn cạnh song song đắt hơn nếu có cạnh rẻ hơn.

Một bài production nên bổ sung kiểm tra **tràn số**, đường đi chứa cạnh thật, tổng trọng số bằng g(goal), và giao kèo rõ khi không có đường.

## 20. Phân tích độ phức tạp

Với **đồ thị hữu hạn đã hiện ra**, n=|V| đỉnh, m=|E| cạnh:

- Kiểm tra consistency bằng cách duyệt các cạnh: **O(m)**.
- Trường hợp heuristic consistent và A* có closed chốt một lần: mỗi đỉnh được mở rộng tối đa một lần, quét tối đa m cạnh. Bản heap có thể chứa bản ghi cũ khi giảm g, nên cận đơn giản thời gian **O((n+m)log(n+m))**, bộ nhớ **O(n+m)** nếu đếm cả cạnh và các entry heap có thể đọng lại.
- Với heuristic admissible nhưng không consistent và cho phép reopen, một đỉnh có thể được mở rộng **nhiều lần**. Không được tự gán cận “mỗi đỉnh đúng một lần” hay cận O((n+m)log n) của trường hợp consistent; số lần reopen phụ thuộc dữ liệu và có thể rất lớn.
- Khi h=0, A* về cơ bản là Dijkstra trên đồ thị chi phí không âm (đổi các chi tiết tie-break/kiểm tra h).
- Với **cây tìm kiếm trạng thái được sinh động**, số trạng thái duyệt có thể tăng theo cấp số mũ với độ sâu lời giải; A* có thể sử dụng nhiều bộ nhớ vì giữ frontier và best g, ngay cả khi heuristic tốt.

**Chi phí đánh giá heuristic cũng quan trọng:** nếu h(v) rất tốn kém và được tính lại nhiều lần, cộng thêm phần này vào thời gian. Với heuristic từ tọa độ, h thường O(1); với một bài thư giãn phức tạp, cần lưu cache hoặc cân nhắc chi phí tính h.

## 21. Java 17+: hai phiên bản an toàn và một đối chứng cố ý sai

Lưu chương trình dưới đây thành **AStarHeuristicLesson.java**. Code thể hiện trực tiếp những khác biệt về điều kiện toán học:

- **aStarConsistent(g,s,t,h):** xác nhận consistency trên mọi cạnh và goal h=0, sau đó dùng closed **không mở lại**.
- **aStarReopen(g,s,t,h):** dành cho heuristic **đã được chứng minh admissible**, cho phép mở lại closed nếu g giảm. Code không tự chứng nhận admissibility của h đầu vào vì điều đó có thể cần giải chính bài shortest path.
- **unsafeNoReopenForDemonstration:** hàm **private và cố ý không an toàn**, chỉ dùng cho phản ví dụ để thấy kết quả 5 thay vì 4.
- **bellmanFordOracle:** bộ tính khoảng cách tham chiếu độc lập trên đồ thị trọng số không âm, dùng cho kiểm thử.
- **exactFiniteHeuristic:** lấy khoảng cách thật tới goal bằng BF trên đồ thị đảo; với những đỉnh không thể tới goal, dùng max hữu hạn thay vì INF để giữ consistency trong demo.
- **validateWitness:** kiểm tra endpoints, cạnh thật và tổng chi phí đường tái hiện khớp đáp án.
- **grid():** tạo đồ thị 3×5 gồm các ô hợp lệ và bốn hướng, thử Manhattan.

**Miền đầu vào demo:** n từ 1 đến 500; cạnh có hướng chi phí nguyên trong [0,1.000.000]; heuristic là long không âm và không vượt 10^12, h(goal)=0; start/goal là ID hợp lệ. INF dùng Long.MAX_VALUE/4; với giới hạn trên, chi phí một đường ngắn nhất đơn không vượt 499×1.000.000, nên cách dùng INF an toàn cho kết quả chuẩn. Mã dùng Math.addExact khi cộng chi phí mở rộng và h để không âm thầm tràn long.

**Quan trọng:** h(goal)=0 và tất cả h≥0 được kiểm tra, nhưng **aStarReopen không thể biết h có admissible thật hay không**. Khi dùng API này, người gọi cần có chứng minh lower bound. Nếu không có heuristic đáng tin, dùng h=0 (Dijkstra) hoặc xây heuristic hợp lệ theo mô hình.

~~~java
import java.util.*;

public final class AStarHeuristicLesson {
    static final long INF = Long.MAX_VALUE / 4;

    record Edge(int from, int to, int cost) {}
    record State(int vertex, long g, long f) {}
    record Result(long distance, List<Integer> path, int expanded, int reopened) {
        Result { path = List.copyOf(path); }
    }

    static final class Graph {
        final int n;
        final List<List<Edge>> adj;
        final List<Edge> edges = new ArrayList<>();

        Graph(int n) {
            if (n < 1 || n > 500) throw new IllegalArgumentException("n out of range");
            this.n = n;
            adj = new ArrayList<>();
            for (int v = 0; v < n; v++) adj.add(new ArrayList<>());
        }

        void add(int from, int to, int cost) {
            if (from < 0 || from >= n || to < 0 || to >= n ||
                    cost < 0 || cost > 1_000_000) {
                throw new IllegalArgumentException("invalid nonnegative edge");
            }
            Edge e = new Edge(from, to, cost);
            adj.get(from).add(e);
            edges.add(e);
        }

        Graph reverse() {
            Graph reversed = new Graph(n);
            for (Edge e : edges) reversed.add(e.to(), e.from(), e.cost());
            return reversed;
        }
    }

    private static void validateHeuristic(Graph g, int goal, long[] h) {
        if (h == null || h.length != g.n || goal < 0 || goal >= g.n ||
                h[goal] != 0) {
            throw new IllegalArgumentException("invalid heuristic or goal");
        }
        for (long estimate : h) {
            if (estimate < 0 || estimate > 1_000_000_000_000L) {
                throw new IllegalArgumentException("heuristic out of range");
            }
        }
    }

    static boolean isConsistent(Graph g, int goal, long[] h) {
        validateHeuristic(g, goal, h);
        for (Edge e : g.edges) {
            if (h[e.from()] > (long) e.cost() + h[e.to()]) {
                return false;
            }
        }
        return true;
    }

    private static Result run(Graph g, int start, int goal, long[] h,
                              boolean reopenClosed) {
        if (start < 0 || start >= g.n) {
            throw new IllegalArgumentException("invalid start");
        }
        validateHeuristic(g, goal, h);

        long[] best = new long[g.n];
        Arrays.fill(best, INF);
        int[] parent = new int[g.n];
        Arrays.fill(parent, -1);
        boolean[] closed = new boolean[g.n];
        PriorityQueue<State> open = new PriorityQueue<>(
                Comparator.comparingLong(State::f)
                        .thenComparingLong(State::g)
                        .thenComparingInt(State::vertex));
        best[start] = 0;
        open.add(new State(start, 0, h[start]));
        int expanded = 0, reopened = 0;

        while (!open.isEmpty()) {
            State current = open.poll();
            int u = current.vertex();
            if (current.g() != best[u] || closed[u]) continue;
            closed[u] = true;
            expanded++;

            if (u == goal) {
                ArrayList<Integer> reversed = new ArrayList<>();
                for (int v = goal, hops = 0; v != -1; v = parent[v]) {
                    if (++hops > g.n) throw new AssertionError("parent cycle");
                    reversed.add(v);
                }
                Collections.reverse(reversed);
                if (reversed.get(0) != start) {
                    throw new AssertionError("broken path");
                }
                return new Result(best[goal], reversed, expanded, reopened);
            }

            for (Edge e : g.adj.get(u)) {
                int v = e.to();
                if (!reopenClosed && closed[v]) continue;
                long alternative = Math.addExact(best[u], e.cost());
                if (alternative < best[v]) {
                    if (closed[v]) {
                        closed[v] = false;
                        reopened++;
                    }
                    best[v] = alternative;
                    parent[v] = u;
                    open.add(new State(v, alternative,
                            Math.addExact(alternative, h[v])));
                }
            }
        }
        return new Result(INF, List.of(), expanded, reopened);
    }

    static Result aStarConsistent(Graph g, int start, int goal, long[] h) {
        if (!isConsistent(g, goal, h)) {
            throw new IllegalArgumentException("heuristic is inconsistent");
        }
        return run(g, start, goal, h, false);
    }

    static Result aStarReopen(Graph g, int start, int goal, long[] h) {
        return run(g, start, goal, h, true);
    }

    private static Result unsafeNoReopenForDemonstration(
            Graph g, int start, int goal, long[] h) {
        return run(g, start, goal, h, false);
    }

    private static long[] bellmanFordOracle(Graph g, int start) {
        long[] dist = new long[g.n];
        Arrays.fill(dist, INF);
        dist[start] = 0;
        for (int iteration = 0; iteration < g.n - 1; iteration++) {
            boolean changed = false;
            for (Edge e : g.edges) {
                if (dist[e.from()] == INF) continue;
                long alt = dist[e.from()] + e.cost();
                if (alt < dist[e.to()]) {
                    dist[e.to()] = alt;
                    changed = true;
                }
            }
            if (!changed) break;
        }
        return dist;
    }

    private static long[] exactFiniteHeuristic(Graph g, int goal) {
        long[] toGoal = bellmanFordOracle(g.reverse(), goal);
        long maxFinite = 0;
        for (long d : toGoal) {
            if (d != INF) maxFinite = Math.max(maxFinite, d);
        }
        for (int v = 0; v < g.n; v++) {
            if (toGoal[v] == INF) toGoal[v] = maxFinite;
        }
        if (!isConsistent(g, goal, toGoal)) {
            throw new AssertionError("reverse shortest distances inconsistent");
        }
        return toGoal;
    }

    private static void validateWitness(Graph g, int start, int goal,
                                        Result answer, long expected) {
        if (answer.distance() != expected) {
            throw new AssertionError("wrong distance");
        }
        if (expected == INF) {
            if (!answer.path().isEmpty()) {
                throw new AssertionError("unreachable but returned path");
            }
            return;
        }
        List<Integer> path = answer.path();
        if (path.isEmpty() || path.get(0) != start ||
                path.get(path.size() - 1) != goal ||
                path.size() > g.n) {
            throw new AssertionError("invalid path endpoints/size");
        }
        long cost = 0;
        for (int i = 1; i < path.size(); i++) {
            int u = path.get(i - 1), v = path.get(i);
            int cheapest = Integer.MAX_VALUE;
            for (Edge e : g.adj.get(u)) {
                if (e.to() == v) cheapest = Math.min(cheapest, e.cost());
            }
            if (cheapest == Integer.MAX_VALUE) {
                throw new AssertionError("path uses non-edge");
            }
            cost += cheapest;
        }
        if (cost != answer.distance()) {
            throw new AssertionError("path cost mismatch");
        }
    }

    private static void checkGraph(Graph g, Random rng) {
        for (int goal = 0; goal < g.n; goal++) {
            long[] exact = exactFiniteHeuristic(g, goal);
            long[] zero = new long[g.n];
            long[] admissible = new long[g.n];
            long[] real = bellmanFordOracle(g.reverse(), goal);
            for (int v = 0; v < g.n; v++) {
                if (real[v] != INF) {
                    admissible[v] = Math.min(real[v], rng.nextInt(6));
                }
            }
            for (int start = 0; start < g.n; start++) {
                long trueDistance = bellmanFordOracle(g, start)[goal];
                validateWitness(g, start, goal,
                        aStarConsistent(g, start, goal, zero), trueDistance);
                validateWitness(g, start, goal,
                        aStarConsistent(g, start, goal, exact), trueDistance);
                validateWitness(g, start, goal,
                        aStarReopen(g, start, goal, admissible), trueDistance);
            }
        }
    }

    private static Graph grid() {
        String[] rows = {"S.#.G", "..#..", "....."};
        int height = rows.length, width = rows[0].length();
        Graph g = new Graph(height * width);
        int[][] directions = {{1,0},{-1,0},{0,1},{0,-1}};
        for (int r = 0; r < height; r++) {
            for (int c = 0; c < width; c++) {
                if (rows[r].charAt(c) == '#') continue;
                for (int[] d : directions) {
                    int rr = r + d[0], cc = c + d[1];
                    if (rr >= 0 && rr < height && cc >= 0 && cc < width
                            && rows[rr].charAt(cc) != '#') {
                        g.add(r * width + c, rr * width + cc, 1);
                    }
                }
            }
        }
        return g;
    }

    private static void expectInvalid(Runnable call) {
        try {
            call.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        Random rng = new Random(3592026L);
        int exhaustive = 0;
        int[] values = {-1, 0, 1, 2};
        for (int n = 1; n <= 3; n++) {
            ArrayList<int[]> arcs = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = 0; v < n; v++) {
                    if (u != v) arcs.add(new int[] {u, v});
                }
            }
            int cases = 1;
            for (int k = 0; k < arcs.size(); k++) cases *= 4;
            for (int code = 0; code < cases; code++) {
                Graph g = new Graph(n);
                int rest = code;
                for (int[] e : arcs) {
                    int cost = values[rest % 4];
                    rest /= 4;
                    if (cost >= 0) g.add(e[0], e[1], cost);
                }
                checkGraph(g, rng);
                exhaustive++;
            }
        }

        int seeded = 0;
        for (int n = 2; n <= 8; n++) {
            for (int trial = 0; trial < 100; trial++) {
                Graph g = new Graph(n);
                int m = rng.nextInt(3 * n + 5);
                for (int e = 0; e < m; e++) {
                    g.add(rng.nextInt(n), rng.nextInt(n), rng.nextInt(11));
                }
                checkGraph(g, rng);
                seeded++;
            }
        }

        Graph crafted = new Graph(4);
        crafted.add(0, 1, 3);
        crafted.add(0, 2, 1);
        crafted.add(2, 1, 1);
        crafted.add(1, 3, 2);
        crafted.add(2, 3, 10);
        long[] inconsistent = {4, 0, 3, 0};
        if (isConsistent(crafted, 3, inconsistent)) {
            throw new AssertionError("counterexample should be inconsistent");
        }
        if (aStarReopen(crafted, 0, 3, inconsistent).distance() != 4 ||
                unsafeNoReopenForDemonstration(crafted, 0, 3,
                        inconsistent).distance() != 5 ||
                aStarReopen(crafted, 0, 3, inconsistent).reopened() != 1) {
            throw new AssertionError("reopen counterexample failed");
        }
        expectInvalid(() -> aStarConsistent(crafted, 0, 3, inconsistent));
        expectInvalid(() -> aStarReopen(crafted, 0, 3,
                                      new long[] {0, 0, 0}));
        expectInvalid(() -> aStarReopen(crafted, 0, 3,
                                      new long[] {0, -1, 0, 0}));
        expectInvalid(() -> aStarReopen(crafted, -1, 3,
                                      new long[] {0, 0, 0, 0}));
        expectInvalid(() -> new Graph(0));
        expectInvalid(() -> crafted.add(0, 3, -1));

        Graph grid = grid();
        long[] manhattan = new long[15];
        for (int v = 0; v < manhattan.length; v++) {
            manhattan[v] = Math.abs(v / 5) + Math.abs(v % 5 - 4);
        }
        Result gridAStar = aStarConsistent(grid, 0, 4, manhattan);
        if (gridAStar.distance() != 8 || manhattan[0] != 4 ||
                bellmanFordOracle(grid, 0)[4] != 8) {
            throw new AssertionError("grid Manhattan test failed");
        }

        System.out.println("Exhaustive directed graphs: " +
                exhaustive + " PASS");
        System.out.println("Seeded directed graphs: " + seeded + " PASS");
        System.out.println("Admissible/consistent/reopening and paths: PASS");
        System.out.println("Grid Manhattan heuristic: PASS");
        System.out.println("Invalid-input cases: PASS");
    }

    public static void main(String[] args) {
        Graph g = new Graph(4);
        g.add(0, 1, 3);
        g.add(0, 2, 1);
        g.add(2, 1, 1);
        g.add(1, 3, 2);
        g.add(2, 3, 10);
        long[] consistent = {4, 2, 3, 0};
        long[] admissibleInconsistent = {4, 0, 3, 0};

        Result good = aStarConsistent(g, 0, 3, consistent);
        Result repaired = aStarReopen(g, 0, 3, admissibleInconsistent);
        Result wrong = unsafeNoReopenForDemonstration(
                g, 0, 3, admissibleInconsistent);

        System.out.println("Consistent A*: distance=" + good.distance()
                + " path=" + good.path() + " reopened=" + good.reopened());
        System.out.println("Inconsistent with reopen: distance="
                + repaired.distance() + " path=" + repaired.path()
                + " reopened=" + repaired.reopened());
        System.out.println("Unsafe no-reopen: distance=" + wrong.distance()
                + " path=" + wrong.path());
        System.out.println("Inconsistent heuristic accepted as consistent: "
                + isConsistent(g, 3, admissibleInconsistent));

        Graph grid = grid();
        long[] manhattan = new long[15];
        for (int v = 0; v < manhattan.length; v++) {
            manhattan[v] = Math.abs(v / 5) + Math.abs(v % 5 - 4);
        }
        Result gAStar = aStarConsistent(grid, 0, 4, manhattan);
        System.out.println("Grid Manhattan(start)=" + manhattan[0]
                + " shortest=" + gAStar.distance());
        System.out.println("Grid A* path=" + gAStar.path());
        verify();
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac AStarHeuristicLesson.java
java AStarHeuristicLesson
~~~

**Stdout chính xác quan sát được:**

~~~text
Consistent A*: distance=4 path=[0, 2, 1, 3] reopened=0
Inconsistent with reopen: distance=4 path=[0, 2, 1, 3] reopened=1
Unsafe no-reopen: distance=5 path=[0, 1, 3]
Inconsistent heuristic accepted as consistent: false
Grid Manhattan(start)=4 shortest=8
Grid A* path=[0, 1, 6, 11, 12, 13, 8, 3, 4]
Exhaustive directed graphs: 4113 PASS
Seeded directed graphs: 700 PASS
Admissible/consistent/reopening and paths: PASS
Grid Manhattan heuristic: PASS
Invalid-input cases: PASS
~~~

Dòng **Unsafe no-reopen: distance=5** là kết quả **sai có chủ ý** của bản đối chứng để minh họa điều kiện cần; không phải đầu ra được coi là tối ưu. Hai bản an toàn trả 4. Các dòng PASS ở cuối đến từ việc thử thuật toán với oracle độc lập.

## 22. Kiểm thử vét cạn 4.113 đồ thị nhỏ

Bộ kiểm thử tạo các đồ thị có hướng đơn với n=1,2,3; với mỗi cung u→v khác self-loop, có bốn lựa chọn:

~~~text
1. Không có cạnh.
2. Có cạnh cost 0.
3. Có cạnh cost 1.
4. Có cạnh cost 2.
~~~

Với n đỉnh có n(n−1) cặp u≠v có hướng, nên số cấu hình:

~~~text
n=1: 4^0 =    1.
n=2: 4^2 =   16.
n=3: 4^6 = 4096.

Tổng = 4113 đồ thị.
~~~

Cho **từng cặp start,goal** trong mỗi đồ thị, chương trình so A* với kết quả **Bellman–Ford** tính độc lập. Ba nhánh A* được thử:

1. h=0, consistent, không reopen.
2. h từ **khoảng cách thật tới goal**, có điều chỉnh hữu hạn ở trạng thái không tới goal, consistent, không reopen.
3. h≤h*(v) theo cách sinh ngẫu nhiên bị chặn, admissible nhưng không bắt buộc consistent, **có reopen**.

Bộ test cũng xác minh đường mà A* trả thực sự nối start tới goal, chỉ dùng cạnh có thật, tổng chi phí bằng đáp án và không dài bất thường. Nếu start=goal, đường một đỉnh và chi phí 0; nếu không thể tới goal, đường phải rỗng.

Điểm mạnh của phép thử là sử dụng **Bellman–Ford**, không dùng một bản A* khác làm oracle; nhờ đó kiểm tra được những lỗi logic thuộc riêng cơ chế ưu tiên/closed/reopen.

## 23. Kiểm thử 700 đồ thị có seed và trường hợp biên

Mã dùng Random(3592026L), tạo **100 đồ thị cho mỗi n=2..8**, tổng 700 đồ thị có hướng. Số cạnh được chọn ngẫu nhiên, hai đầu cạnh chọn độc lập nên có cả **self-loop và cạnh song song**; trọng số nguyên trong [0,10], bao gồm cạnh cost=0.

Với mỗi graph, mỗi đích và mỗi nguồn, so A* với Bellman–Ford cho ba họ heuristic như phần vét cạn. Đường đi được kiểm chứng bằng thuật toán duyệt cạnh, tách biệt với các bước relax của A*.

Các ca đặc biệt bổ sung:

- **Phản ví dụ h admissible nhưng inconsistent:** reopen trả 4, no-reopen trả 5; kiểm tra đúng một lần reopen trong demo.
- **Kiểm tra consistency:** bản aStarConsistent từ chối h không nhất quán bằng IllegalArgumentException.
- **Lưới Manhattan:** h(start)=4, chi phí thật=8, đường A* khớp.
- **Input lỗi:** graph n=0, cạnh âm, start âm, h âm, độ dài h sai.
- **Đồ thị không liên thông:** nhiều trường hợp INF được kiểm tra trong tập vét cạn và seeded.
- **Đường cost=0:** những cạnh giá 0 và self-loop không được tạo vòng lặp parent do chỉ relax khi giảm g nghiêm ngặt.

Các PASS không thay thế chứng minh tính tối ưu, nhưng tăng độ tin cậy của hiện thực trên nhiều cấu trúc trạng thái khác nhau. Nếu cần đưa vào ứng dụng cụ thể, hãy thêm kiểm thử về đơn vị chi phí, ràng buộc chuyển trạng thái, giới hạn n và những heuristic tự thiết kế.

## 24. Hạn chế, mở rộng và câu hỏi thiết kế

**Nhiều goal:** nếu có tập mục tiêu T, có thể đặt h(v) là lower bound tới **bất kỳ goal nào** và bảo đảm h(goal)=0 với mọi goal; điều kiện dừng thường là khi pop một trạng thái nằm trong T. Không nên giữ h(goal)=0 chỉ cho một goal nếu thuật toán được kỳ vọng nhận một tập khác.

**Heuristic tính động:** nếu giá trị h(v) phụ thuộc lịch sử đường đi chứ không chỉ trạng thái v, nó không còn là một hàm của state đúng nghĩa. Có thể cần **mở rộng trạng thái** (ví dụ vị trí và lượng nhiên liệu) để bảo đảm quan hệ chuyển và đánh giá trạng thái hợp lệ.

**Weighted A*:** dùng f=g+w·h, w>1 có thể ưu tiên hướng goal hơn, nhưng **không còn thuộc bảo đảm tối ưu tiêu chuẩn** của heuristic admissible h không trọng số. Một số biến thể có cận chất lượng khi thỏa điều kiện riêng, không nên coi mọi bản nhân h đều có bảo đảm như nhau.

**Bidirectional A*:** tìm kiếm từ hai phía cần định nghĩa điều kiện dừng và heuristic phù hợp hơn là chỉ mở hai heap A* độc lập rồi dừng khi gặp đỉnh đầu tiên.

**Memory-bounded search:** A* có thể dùng nhiều RAM vì giữ open, closed, best và parent. IDA* hoặc các biến thể giới hạn bộ nhớ có thể hữu ích, nhưng thay đổi cách duyệt, lặp và phân tích.

**Tìm kiếm trong môi trường thay đổi:** nếu chi phí cạnh hoặc chướng ngại thay đổi giữa lúc chạy, các g, closed và heuristic cũ có thể không còn đúng; cần tái lập hoặc áp dụng thuật toán incremental search với hợp đồng riêng.

## 25. Các lỗi thường gặp

1. Chọn heuristic “gần goal” theo trực giác nhưng không chứng minh **h≤h***.
2. Nhầm **admissible** với **consistent**; hai tính chất không tương đương.
3. Cho rằng admissible tự đủ để **không reopen** mọi closed state.
4. Quên yêu cầu **h(goal)=0** trong phiên bản chứng minh và API đang dùng.
5. Dùng Manhattan cho lưới có bước chéo cost 1, gây overestimate.
6. Dùng khoảng cách Euclidean nhưng cạnh có chi phí rẻ hơn độ dài hình học mà không có hệ số phù hợp.
7. Dùng heuristic trên đơn vị mét trong khi g đo giây, cộng đại lượng khác đơn vị.
8. Dừng khi **vừa nhìn thấy goal**, thay vì khi bản ghi hợp lệ của goal được pop.
9. Bỏ qua residual? A* không dùng khái niệm residual của bài luồng; chỉ cần **đồ thị chuyển trạng thái với cạnh có chi phí** và relax đúng. Không nên trộn thuật toán khác vào mô hình.
10. Khi best g giảm, chỉ cập nhật g mà không cập nhật parent hoặc f.
11. Dùng closed trước khi loại **stale heap entry**, dẫn tới bỏ qua bản đúng hoặc mở rộng lại bản sai.
12. Với heuristic không nhất quán, thấy đường tốt hơn tới closed mà không đặt closed=false.
13. Không xét trường hợp s=t và trạng thái không thể tới goal.
14. Không xử lý cạnh song song hoặc self-loop giá 0, tạo parent cycle do cập nhật khi bằng nhau.
15. Cộng INF với một cạnh hoặc h như số hữu hạn, gây tràn số.
16. Giả định A* có O(E log V) cho mọi heuristic admissible, kể cả khi reopen nhiều lần.
17. Giả định heuristic trội hơn luôn giảm số expanded trong mọi trường hợp và tie-break.
18. Lấy đường không có trong graph vì parent lưu đỉnh nhưng không xác nhận cạnh.
19. Không phân biệt **trạng thái** và **lịch sử** khi chi phí/điều kiện chuyển phụ thuộc lịch sử.
20. Lấy kết quả h=0 làm bằng chứng heuristic khác chắc chắn admissible.
21. Dùng heuristic không nhất quán nhưng API cấm reopen, rồi tin rằng kết quả vẫn đúng do các ví dụ nhỏ tình cờ PASS.
22. Kiểm thử chỉ một bản đồ dễ, không có vật cản, không unreachable hay cost 0.
23. So hai bản A* với nhau mà không có oracle shortest path độc lập.
24. Không nêu rõ goal đơn hay nhiều, directed hay undirected, và giới hạn miền chi phí.

## 26. Bài tập tự luyện

**Bài 1 — Tính f:** với đồ thị bốn đỉnh s,a,b,t ở mục 11 và heuristic [4,0,3,0], ghi bảng g,h,f của các đỉnh sau mỗi lần pop. Giải thích vì sao a được mở rộng trước b ở lần đầu.

**Bài 2 — Reopen:** chạy lại ví dụ bằng tay với và không với cơ chế reopen. Ở bước nào g(a) giảm từ 3 xuống 2? Vì sao nếu không mở lại a, goal có thể bị pop với chi phí 5?

**Bài 3 — Kiểm tra bất đẳng thức:** với h=[4,2,3,0], kiểm tra h(u)≤cost(u,v)+h(v) cho mọi cạnh. Dùng tính chất consistency để chứng minh h≤h*.

**Bài 4 — Tự tạo heuristic sai:** trên một đồ thị đơn giản có đường A→G cost 2, thử h(A)=3. Phân biệt lỗi admissibility với lỗi consistency khi h(G)=0.

**Bài 5 — Bản đồ:** với lưới S.#.G / ..#.. / ....., tính Manhattan và tìm đường ngắn nhất theo bốn hướng. Vì sao độ dài thực tế 8 dù heuristic start chỉ bằng 4?

**Bài 6 — Bước chéo:** xây lưới 8 hướng cost 1, chứng minh Manhattan có thể overestimate bằng cặp (0,0)→(1,1). Thử heuristic Chebyshev và tự kiểm tra consistency trên từng bước.

**Bài 7 — Dijkstra:** đặt h=0 trong A*, chạy trên đồ thị ví dụ, so đường và số expanded với h chính xác; giải thích vai trò tie-break khi có nhiều bản ghi cùng f.

**Bài 8 — Đồ thị không liên thông:** thêm một goal không reachable, xác nhận thuật toán trả INF và path rỗng. Kiểm tra sự cần thiết của phép so g với INF trước khi cộng.

**Bài 9 — Oracle:** viết Bellman–Ford độc lập rồi sinh tất cả đồ thị 3 đỉnh có cung absent hoặc cost 0/1/2. So ba phiên bản A* và kiểm tra đường trả có chi phí đúng.

**Bài 10 — Parent:** với một đường có cạnh song song, sửa code lưu cả edge ID làm predecessor. So chi phí của đường tái hiện với bestG[goal].

**Bài 11 — Heuristic thư giãn:** chọn một trò chơi trạng thái, bỏ một ràng buộc để tạo bài dễ hơn. Chứng minh khoảng cách tối ưu của bài thư giãn là lower bound, kiểm tra consistency theo phép chuyển cụ thể.

**Bài 12 — So chi phí:** đo số expanded và thời gian của h=0, Manhattan, và một heuristic mạnh hơn trong nhiều bản đồ có tường. Không kết luận từ một mẫu duy nhất; giữ cố định quy tắc tie-break và kiểm soát thời gian tính h.

**Kết luận:** A* dùng **f=g+h** để ưu tiên những trạng thái có chi phí đã trả thấp và ước lượng tới goal thấp. Heuristic **admissible** không bao giờ vượt chi phí thật còn lại; heuristic **consistent** còn thỏa bất đẳng thức qua từng cạnh, suy ra admissible và giúp chốt closed vĩnh viễn. Nếu heuristic **admissible nhưng inconsistent**, muốn giữ tính tối ưu trong graph search phải **reopen** khi g được cải thiện. Một cách thiết kế heuristic an toàn là xuất phát từ **cận dưới được chứng minh** theo mô hình chuyển trạng thái, như Manhattan trên lưới bốn hướng. Kết hợp chứng minh, vết chạy phản ví dụ, kiểm tra đường và oracle độc lập là cách học A* vững chắc hơn việc chỉ học thuộc công thức f=g+h.
