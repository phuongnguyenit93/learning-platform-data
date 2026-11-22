# Tìm đường đi Euler bằng thuật toán Hierholzer

**Đường đi Euler (Euler trail)** trong một đồ thị là một **hành trình sử dụng mỗi cạnh đúng một lần**. Hành trình được phép đi qua **một đỉnh nhiều lần**, nhưng **không được dùng lại một cạnh**. Nếu hành trình bắt đầu và kết thúc tại cùng một đỉnh, ta gọi đó là **chu trình Euler (Euler circuit / Euler tour)**.

**Thuật toán Hierholzer** xây dựng đường đi hoặc chu trình Euler bằng cách liên tục đi qua những cạnh chưa sử dụng, ghép các vòng khi cần, rồi xuất dãy đỉnh theo **thứ tự quay lui**. Với danh sách kề và đánh dấu **ID cạnh**, ta có thể cài đặt trong **O(n+m)** thời gian cho đồ thị n đỉnh, m cạnh, kể cả đồ thị có **cạnh song song và khuyên tự nối**.

Nội dung bài học tập trung vào:

1. Phân biệt **đường đi Euler**, **chu trình Euler**, **đường đi đơn** và **đường đi Hamilton**.
2. Điều kiện tồn tại trong **đồ thị vô hướng** và **đồ thị có hướng**.
3. Chọn **đỉnh bắt đầu** đúng và xử lý đỉnh cô lập.
4. Cơ chế đi theo cạnh chưa sử dụng, **đưa đỉnh vào kết quả khi hết cạnh**, rồi đảo ngược.
5. Quản lý **cạnh bằng ID riêng**, không chỉ đánh dấu đỉnh đã thăm.
6. Chứng minh tính đúng, phân tích O(n+m), code **Java 17+ chạy độc lập** và kiểm thử bằng vét cạn.

## 1. Euler trail và Euler circuit là gì?

Cho đồ thị G=(V,E). Một **walk** (hành trình) là dãy đỉnh:

**v₀, v₁, ..., vₖ**,

trong đó với mọi i, có một cạnh nối vᵢ với vᵢ₊₁ theo đúng hướng nếu graph có hướng.

Một **trail** là walk **không lặp cạnh**. Các đỉnh có thể lặp lại.

Một **Euler trail** là trail sử dụng **toàn bộ m cạnh đúng một lần**. Do đó nó có:

- **m cạnh được đi qua**;
- **m+1 vị trí đỉnh** trong dãy đường đi, khi m>0.

Một **Euler circuit** là Euler trail có **v₀=vₘ**.

Ví dụ đồ thị vô hướng có các cạnh:

~~~text
(1,2), (2,3), (3,1), (3,4), (4,5), (5,3)
~~~

Một chu trình Euler:

~~~text
1 -> 2 -> 3 -> 4 -> 5 -> 3 -> 1
~~~

Cạnh lần lượt là:

~~~text
1-2, 2-3, 3-4, 4-5, 5-3, 3-1
~~~

Ta đi qua đỉnh 3 **hai lần**, nhưng mỗi cạnh đúng một lần. Đó là Euler circuit hoàn toàn hợp lệ.

### Phân biệt với đường đi đơn và Hamilton

| Khái niệm | Ràng buộc chính | Được lặp đỉnh? | Phải đi hết mọi cạnh? |
| --- | --- | --- | --- |
| Walk | Mỗi cặp đỉnh liên tiếp có cạnh tương ứng | Có | Không |
| Trail | Không lặp cạnh | Có | Không |
| Euler trail | Dùng mọi cạnh đúng một lần | Có | **Có** |
| Euler circuit | Euler trail khép kín | Có | **Có** |
| Simple path (đường đi đơn) | Không lặp đỉnh (trừ quy ước vòng đơn) | Không | Không |
| Hamilton path | Thăm mọi đỉnh đúng một lần | Không | Không |

**Euler quan tâm đến cạnh; Hamilton quan tâm đến đỉnh.** Không thể dùng thuật toán Hierholzer để giải trực tiếp bài Hamilton path.

### Đỉnh cô lập

Đỉnh có bậc 0 không thuộc cạnh nào. Đường đi Euler chỉ phải sử dụng **mọi cạnh**, không bắt buộc ghé qua từng đỉnh cô lập. Vì vậy một đồ thị gồm một chu trình Euler và vài đỉnh cô lập **vẫn có Euler circuit** trên thành phần chứa cạnh.

## 2. Điều kiện tồn tại trong đồ thị vô hướng

Với đồ thị vô hướng có **ít nhất một cạnh**, điều kiện cần và đủ để tồn tại Euler trail là:

**(A) Mọi đỉnh có bậc khác 0 thuộc cùng một thành phần liên thông.**

**(B) Số đỉnh có bậc lẻ bằng đúng 0 hoặc 2.**

Khi đó:

- **0 đỉnh bậc lẻ:** tồn tại **Euler circuit**, có thể bắt đầu tại bất kỳ đỉnh nào có bậc dương.
- **2 đỉnh bậc lẻ:** tồn tại Euler trail **mở**, bắt đầu ở một đỉnh bậc lẻ và kết thúc ở đỉnh bậc lẻ còn lại.
- **1, 3, 4, ... đỉnh bậc lẻ:** không có Euler trail. Theo định lý bắt tay, số đỉnh bậc lẻ luôn **chẵn**, nên trường hợp 1 hoặc 3 không thể xuất hiện trong đồ thị vô hướng hợp lệ.

Điều kiện (A) chỉ xét các đỉnh **có cạnh**. Nếu buộc toàn bộ V liên thông, ta sẽ loại sai những đồ thị có đỉnh cô lập.

### Vì sao phải có 0 hoặc 2 đỉnh bậc lẻ?

Xét một Euler trail từ s đến t:

- Mỗi lần hành trình **đi vào** một đỉnh bên trong, nó phải **đi ra** bằng một cạnh khác; các cạnh ở đỉnh ấy ghép thành từng cặp.
- Nếu s=t (chu trình), ngay cả ở đỉnh xuất phát, cạnh đi ra đầu tiên cũng được ghép với cạnh đi vào cuối cùng. Mọi bậc đều chẵn.
- Nếu s≠t, đỉnh s thừa **một cạnh đi ra** và đỉnh t thừa **một cạnh đi vào**; hai đỉnh đó có bậc lẻ. Các đỉnh khác bậc chẵn.

Đây là **điều kiện cần**. Điều kiện về liên thông cộng với số bậc lẻ phù hợp còn là **điều kiện đủ**, và thuật toán Hierholzer cung cấp cách xây dựng.

### Ví dụ các bậc

Đồ thị đường thẳng:

~~~text
1 -- 2 -- 3 -- 4

degree = [1,2,2,1]
~~~

Có hai đỉnh lẻ 1 và 4, nên đường đi Euler có thể là:

**1 → 2 → 3 → 4**.

Đồ thị hình vuông:

~~~text
1 -- 2
|    |
4 -- 3

degree = [2,2,2,2]
~~~

Mọi bậc chẵn và các đỉnh có cạnh liên thông, nên có chu trình Euler:

**1 → 2 → 3 → 4 → 1**.

Đồ thị hình sao với tâm 1 và ba lá 2,3,4 có bốn đỉnh bậc lẻ: tâm bậc 3, ba lá bậc 1. Không có Euler trail.

## 3. Cẩn thận: chỉ đếm bậc lẻ là chưa đủ

Xét hai tam giác **tách rời nhau**:

~~~text
1 -- 2          4 -- 5
 \  /            \  /
  3               6

E = {(1,2),(2,3),(3,1),
     (4,5),(5,6),(6,4)}
~~~

Mọi đỉnh đều có bậc 2, nên số đỉnh bậc lẻ bằng 0. Nhưng không thể có **một hành trình** dùng cả sáu cạnh: không có cạnh để chuyển từ tam giác thứ nhất sang tam giác thứ hai.

Do đó **m=6, mọi bậc chẵn chưa đủ**. Cần các đỉnh có bậc dương thuộc **cùng một thành phần liên thông**.

Có hai cách xử lý:

1. **Kiểm tra liên thông trước** bằng BFS/DFS trên các đỉnh có bậc dương, sau đó chạy Hierholzer.
2. Dùng **độ dài kết quả hoặc số ID cạnh đã sử dụng** sau khi chạy Hierholzer: nếu chưa dùng đủ m cạnh, kết luận không tồn tại Euler trail toàn graph.

Chương trình Java ở dưới dùng cách thứ hai: kiểm tra điều kiện bậc, chọn gốc hợp lệ, chạy Hierholzer rồi xác nhận **đã tiêu thụ chính xác m cạnh** và đường đi có **m+1 đỉnh**. Việc đọc kết quả này không phải một heuristic; nó là một **kiểm tra đầy đủ** nhằm phát hiện các thành phần chứa cạnh bị bỏ sót.

### Trường hợp không có cạnh

Khi m=0:

- Nếu n>0, có thể trả đường đi tầm thường gồm **một đỉnh**, chẳng hạn [1]. Không cạnh nào bị dùng và mọi ràng buộc được thỏa.
- Nếu n=0, bài học chọn quy ước trả **dãy rỗng []** như một Euler trail rỗng.

Một số đề thi yêu cầu ít nhất một cạnh, hoặc định nghĩa riêng cho đồ thị rỗng. Cần đọc đúng quy ước đầu ra của đề. Đây là **ca cơ sở** của chương trình, không cần kiểm tra độ lẻ.

## 4. Điều kiện tồn tại trong đồ thị có hướng

Với graph có hướng, phải phân biệt:

- **indegree[v]**: số cung đi vào v.
- **outdegree[v]**: số cung đi ra từ v.

Mỗi cung u→v chỉ được đi **theo chiều u đến v**. Không thể tự xem nó như cạnh vô hướng.

Với ít nhất một cung, để tồn tại **Euler circuit có hướng** cần:

1. **indegree[v]=outdegree[v]** cho mọi đỉnh v.
2. Mọi đỉnh **có bậc vào hoặc ra dương** nằm trong cùng một thành phần liên thông **khi bỏ hướng cạnh**.

Với các điều kiện bậc cân bằng, điều kiện liên thông yếu của phần chứa cạnh thực tế đã đủ cho một Euler circuit; không cần áp đặt thêm một điều kiện mạnh hơn mà không cần thiết.

Để tồn tại **Euler trail mở có hướng**, cần:

1. Có đúng **một đỉnh s** thỏa **outdegree[s]=indegree[s]+1** (điểm bắt đầu).
2. Có đúng **một đỉnh t** thỏa **indegree[t]=outdegree[t]+1** (điểm kết thúc).
3. Mọi đỉnh khác có **indegree=outdegree**.
4. Mọi đỉnh có cung thuộc cùng **một thành phần liên thông yếu** (nếu bỏ hướng).

Không tồn tại trường hợp chỉ có một đỉnh lệch +1 mà không có đỉnh lệch −1: tổng outdegree bằng tổng indegree bằng m, nên tổng các sai lệch luôn bằng 0.

### Ví dụ Euler trail có hướng

~~~text
Các cung:
1 -> 2
2 -> 3
3 -> 1
1 -> 4
~~~

Bậc:

| Đỉnh | In | Out | Out−In |
| ---: | ---: | ---: | ---: |
| 1 | 1 | 2 | +1 |
| 2 | 1 | 1 | 0 |
| 3 | 1 | 1 | 0 |
| 4 | 1 | 0 | −1 |

Vì các đỉnh có cung liên thông yếu và sai lệch đúng quy tắc, một Euler trail là:

**1 → 2 → 3 → 1 → 4**.

Đồ thị này **không liên thông mạnh**: từ 4 không có đường quay lại 1. Nhưng nó vẫn có Euler trail mở. Vì vậy yêu cầu “toàn bộ đỉnh có cạnh phải nằm trong một SCC” cho mọi Euler trail sẽ **quá mạnh và sai**.

### Vì sao điều kiện liên thông yếu đủ cùng với bậc?

Đối với circuit cân bằng, có thể co các thành phần liên thông mạnh thành một DAG. Nếu tồn tại hơn một SCC có cung và phần đồ thị chứa cạnh liên thông yếu, DAG co sẽ có một SCC nguồn với cung ra nhưng không có cung vào; điều đó mâu thuẫn với tổng indegree=outdegree trong SCC ấy. Do đó phần chứa cung cân bằng và liên thông yếu thực ra thuộc một SCC.

Với trail mở s→t, thêm một **cung t→s** làm bậc ở mọi đỉnh cân bằng, mà không phá liên thông yếu. Bài circuit mới có thể được duyệt bằng Hierholzer; cắt ngay tại cung giả sẽ cho trail mở từ s đến t. Chương trình không cần thực sự thêm cung này: nó bắt đầu tại s và chạy Hierholzer trực tiếp.

## 5. Khuyên tự nối và cạnh song song ảnh hưởng thế nào?

### Đồ thị vô hướng: self-loop tính bậc **hai lần**

Một khuyên {u,u} chạm vào u ở hai đầu, nên đóng góp **2** vào degree[u]. Ví dụ graph chỉ có một đỉnh 1 và một khuyên:

~~~text
(1,1)
degree[1]=2
Euler circuit: 1 -> 1
~~~

Nếu vô tình chỉ tăng bậc của u một lần cho self-loop, chương trình sẽ đánh giá bậc lẻ sai.

### Đồ thị có hướng: self-loop cộng một in và một out

Cung u→u làm:

**indegree[u] += 1** và **outdegree[u] += 1**.

Nó không tạo sai lệch out−in, nên không tự phá điều kiện Euler.

### Cạnh song song là những **cạnh riêng biệt**

Ví dụ graph vô hướng có hai cạnh song song giữa 1 và 2:

~~~text
edge ID 0: 1 -- 2
edge ID 1: 1 -- 2

Euler circuit: 1 -> 2 -> 1
~~~

Mặc dù hai cạnh có cùng cặp đầu mút, phải đi qua **cả hai ID**. Nếu chỉ lưu một boolean cho cặp (1,2), ta sẽ không phân biệt được hai cạnh.

Đây là lý do **dùng ID cạnh**, không chỉ đánh dấu đỉnh visited hoặc cặp đỉnh.

### Quy tắc tạo adjacency

Với mỗi **cạnh vô hướng** có ID e và hai đầu u,v:

- Thêm **Arc(v,e)** vào adjacency[u].
- Thêm **Arc(u,e)** vào adjacency[v].
- Nếu u=v, hai Arc được thêm vào **cùng một danh sách**; vẫn chỉ là **một cạnh thực**, vì cả hai Arc dùng **chung ID e**.

Với mỗi **cung có hướng** u→v mang ID e:

- Chỉ thêm **Arc(v,e)** vào adjacency[u].
- Không thêm cung ngược, trừ khi input có **một cung ngược khác với ID riêng**.

Khi sử dụng cạnh ID e, đánh dấu **used[e]=true**. Trong graph vô hướng, hai bản ghi adjacency của e sẽ được nhận diện là đã dùng, nên không thể vô tình đi e lần thứ hai theo chiều ngược.

## 6. Tư duy Hierholzer: tạo vòng rồi ghép vòng

Trước hết xét Euler circuit trong đồ thị vô hướng liên thông trên các đỉnh có cạnh và mọi bậc chẵn.

Bắt đầu từ một đỉnh s có cạnh:

1. Chọn một **cạnh chưa sử dụng** nối từ đỉnh hiện tại, đi qua cạnh ấy và đánh dấu đã dùng.
2. Tiếp tục đi cho đến khi không thể đi thêm cạnh chưa dùng.
3. Do mọi bậc chẵn, hành trình không thể bị kẹt ở một đỉnh **khác s** khi vẫn đang xây một vòng; nó sẽ khép lại ở s.
4. Nếu còn cạnh chưa dùng trong đồ thị, từ điều kiện liên thông có một đỉnh trên vòng hiện tại vẫn còn cạnh chưa dùng. Bắt đầu một vòng mới từ đó và **ghép vòng mới vào vòng cũ**.
5. Tiếp tục tới khi sử dụng hết mọi cạnh.

Điều quan trọng là **một đỉnh trên vòng cũ có thể xuất hiện lại nhiều lần** sau khi ghép vòng. Không được đánh dấu visited theo đỉnh để cấm quay lại.

### Ví dụ cần ghép hai vòng

~~~text
          2
         / \
        1---3
            / \
           4---5

Cac canh:
(1,2),(2,3),(3,1),(3,4),(4,5),(5,3)
~~~

Có hai chu trình cùng đi qua đỉnh 3:

- Vòng thứ nhất: 1→2→3→1.
- Vòng thứ hai: 3→4→5→3.

Ghép vòng thứ hai tại đỉnh 3 của vòng thứ nhất:

**1→2→3→4→5→3→1**.

Nếu chỉ tìm một vòng rồi dừng, ta bỏ sót các cạnh ở vòng còn lại. Hierholzer xử lý việc ghép bằng **cơ chế stack và thứ tự ghi kết quả khi quay lui**, nên không phải duy trì cấu trúc nối danh sách phức tạp.

### Đường đi mở

Nếu có đúng hai đỉnh bậc lẻ trong graph vô hướng, chọn một đỉnh lẻ làm s. Khi đi dọc các cạnh chưa dùng, hành trình cuối cùng có thể kết thúc ở đỉnh lẻ t còn lại. Tư duy ghép vòng vẫn áp dụng cho phần các vòng phát sinh.

Với graph có hướng, thay lập luận cặp cạnh vào/ra bằng **cân bằng indegree/outdegree**; ở đường đi mở có đúng một đỉnh thừa out làm s và một đỉnh thừa in làm t.

## 7. Phiên bản stack: thêm đỉnh khi không còn cạnh chưa dùng

Cách cài phổ biến tránh thao tác ghép vòng trực tiếp.

Duy trì:

- **stack**: những đỉnh trên hành trình đang xây.
- **used[e]**: cạnh ID e đã dùng hay chưa.
- **next[u]**: vị trí trong adjacency[u] của cạnh kế tiếp cần kiểm tra.
- **reversed**: các đỉnh đã hết cạnh để tiếp tục, ghi theo thứ tự **quay lui**.

Pseudocode:

~~~text
stack.push(start)
usedEdges = 0
reversed = []

while stack not empty:
    u = stack.top()

    bo qua cac adjacency[u][next[u]] co ID da used

    if da het canh chua dung tai u:
        reversed.push(stack.pop())
    else:
        (v, id) = adjacency[u][next[u]]
        next[u] += 1
        used[id] = true
        usedEdges += 1
        stack.push(v)

reverse(reversed)

if usedEdges != m or length(reversed) != m+1:
    return NO

return reversed
~~~

### Vì sao phải đảo ngược kết quả?

Một đỉnh chỉ được đưa vào reversed khi **mọi cạnh đi tiếp từ đỉnh ấy đã bị dùng**. Đây là thứ tự hoàn tất (postorder) theo đường đi đang xây, không phải thứ tự xuất phát.

Ví dụ đường đi vô hướng:

~~~text
1 -- 2 -- 3 -- 4
~~~

Nếu bắt đầu từ 1 và liên tục đi qua cạnh chưa dùng, stack lần lượt là:

~~~text
[1]
[1,2]
[1,2,3]
[1,2,3,4]
~~~

Đỉnh 4 hết cạnh nên bị pop trước, sau đó 3,2,1. Ta thu:

~~~text
reversed = [4,3,2,1]
~~~

Đảo ngược mới cho Euler trail **[1,2,3,4]**.

Với graph có vòng lồng nhau, chính cơ chế “pop khi hết cạnh” tự động đặt các vòng phụ đúng vị trí trong hành trình cuối.

### Bất biến của stack

Mỗi lần push v từ u qua một cạnh ID e:

- e **chưa dùng** ở thời điểm push;
- used[e] được đặt true **trước khi** push;
- stack được nối thêm v với một cạnh đã được tiêu thụ.

Mỗi lần pop u:

- Không còn Arc nào ở adjacency[u] với ID chưa dùng;
- u được ghi vào reversed để hình thành thứ tự Euler sau khi đảo.

Nhờ những bất biến này, một cạnh không được dùng hai lần, và việc quay lui không làm mất thông tin cần ghép vòng.

## 8. Vì sao cần next[u] thay vì quét lại từ đầu?

Nếu mỗi lần đứng tại u lại duyệt adjacency[u] **từ vị trí 0** để tìm cạnh chưa dùng, có thể phải kiểm tra các cạnh đã dùng lặp đi lặp lại.

Một đỉnh bậc d lớn có thể bị ghé nhiều lần, làm số lần quét danh sách của nó lên tới O(d²). Với graph dạng sao hoặc các vòng gặp nhau tại một đỉnh trung tâm, đây là nguồn gây chậm đáng kể.

Để giữ O(n+m), dùng con trỏ:

**next[u] = chỉ số Arc đầu tiên chưa được kiểm tra vĩnh viễn trong adjacency[u]**.

Khi quét:

- Nếu ID đã dùng, tăng next[u].
- Nếu ID chưa dùng, lấy Arc, tăng next[u] và dùng cạnh đó.
- Không bao giờ giảm next[u].

Mỗi vị trí adjacency chỉ được **xét tối đa một lần** qua con trỏ của đỉnh chứa nó. Trong graph vô hướng có tối đa 2m Arc; graph có hướng có m Arc.

Do đó, ngoài bước xây adjacency, phần di chuyển con trỏ là **O(m)**, không O(m²).

### Dùng index trong Java

Trong mã Java dưới đây:

~~~java
while (next[u] < out.size()
        && used[out.get(next[u]).id()]) {
    next[u]++;
}
~~~

Khi còn Arc chưa dùng:

~~~java
Arc arc = out.get(next[u]++);
used[arc.id()] = true;
stack.push(arc.to());
~~~

Đoạn này là **trích dẫn minh họa**, không chạy riêng; chương trình đầy đủ ở mục 12 có mọi khai báo cần thiết.

## 9. Chọn đỉnh bắt đầu đúng

| Loại graph | Điều kiện bậc | Start cần chọn |
| --- | --- | --- |
| Vô hướng, circuit | Tất cả bậc chẵn | Một đỉnh có degree>0 |
| Vô hướng, trail mở | Đúng 2 đỉnh bậc lẻ | Một trong 2 đỉnh bậc lẻ |
| Có hướng, circuit | In=Out ở mọi đỉnh | Một đỉnh có outdegree>0 |
| Có hướng, trail mở | Một đỉnh Out−In=+1 và một đỉnh Out−In=−1 | Chính đỉnh có Out−In=+1 |
| Không cạnh | m=0 | Một đỉnh bất kỳ nếu n>0, hoặc [] nếu n=0 |

Không được luôn chọn **đỉnh 1** nếu đỉnh 1 cô lập còn graph có những cạnh ở đỉnh khác. Ví dụ:

~~~text
n=5
edges={(2,3),(3,4)}
vertex 1 isolated
~~~

Đường Euler là **2→3→4**, không thể bắt đầu ở 1 để đi qua những cạnh ấy.

Khi graph vô hướng có đúng hai đỉnh lẻ, bắt đầu ở một đỉnh **bậc chẵn** có thể khiến thuật toán quay lui ra một thứ tự không phải Euler trail đúng và/hoặc thất bại khi kiểm tra toàn bộ cạnh. Phải tuân theo điều kiện đầu mút.

Ở graph có hướng, bắt đầu tại đỉnh thừa **một cung đi vào** thay vì thừa cung đi ra sẽ sai hướng; điểm xuất phát của đường đi mở nhất thiết có **Out−In=+1**.

## 10. Kiểm tra tính hợp lệ sau khi xây đường đi

Cho graph có m cạnh, chương trình Hierholzer cần xác nhận:

1. **Số ID cạnh đã dùng bằng m**.
2. **Dãy đỉnh cuối có m+1 phần tử** nếu m>0.
3. Mỗi bước giữa hai đỉnh liên tiếp tương ứng với một cạnh/cung thật **chưa được dùng trước đó** (được bảo đảm bởi cơ chế ID và quá trình stack khi tiền điều kiện Euler thỏa).

Nếu bước 1 hoặc 2 thất bại, graph không có **một Euler trail bao phủ tất cả các cạnh** theo điều kiện bậc và gốc đã chọn.

Một cách kiểm thử độc lập tốt hơn là đi qua từng cặp đỉnh liên tiếp trong kết quả, lấy đúng **một cạnh ID còn chưa tiêu thụ** phù hợp cặp ấy. Với graph vô hướng, so cặp không thứ tự; với graph có hướng, so **đúng chiều**. Sau cùng phải dùng hết mỗi ID đúng một lần.

### Vì sao không chỉ kiểm tra m+1 đỉnh?

Nếu cài đặt sai quy tắc used ID hoặc ghi kết quả sai thứ tự, một dãy có m+1 phần tử **chưa chắc hợp lệ**. Trong chương trình đúng, chiều dài m+1 chỉ là một phần của điều kiện hậu kiểm; chứng minh tính đúng còn dựa trên cách mỗi bước sử dụng ID thật và cách Hierholzer ghép các vòng.

### Không nên kiểm tra visitedVertexCount==n

Một graph có Euler trail có thể có đỉnh cô lập không nằm trong trail. Số đỉnh được ghé không cần bằng n; điều kiện là **mọi cạnh** được sử dụng.

## 11. Mã Java 17+ hoàn chỉnh cho cả graph vô hướng và có hướng

Chương trình dưới đây nhận:

- **n**: số đỉnh không âm.
- **edges**: mảng gồm các cặp {u,v}, nhãn đỉnh **1..n**.
- Với **undirected**, mỗi cặp là cạnh vô hướng có ID riêng, dù hai cặp giống nhau.
- Với **directed**, mỗi cặp là cung u→v.
- Không cấm **cạnh song song** hoặc **self-loop**.
- Trả một record gồm **possible**, **route** (dãy đỉnh Euler nếu có), và **reason** (nguyên nhân nếu không có).

Mã dùng **ArrayDeque** làm stack, không gọi đệ quy; vì vậy không gặp StackOverflowError khi hành trình dài. Trạng thái next[u], used[e] khiến mỗi Arc được xét tối đa một lần.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public class HierholzerEulerDemo {

    record Arc(int to, int id) {}

    record Result(boolean possible, List<Integer> route,
                  String reason) {}

    private static Result yes(List<Integer> route) {
        return new Result(true, List.copyOf(route), "");
    }

    private static Result no(String reason) {
        return new Result(false, List.of(), reason);
    }

    private static List<List<Arc>> newAdj(int n) {
        List<List<Arc>> adj = new ArrayList<>(n);
        for (int u = 0; u < n; u++) {
            adj.add(new ArrayList<>());
        }
        return adj;
    }

    private static void validate(int n, int[][] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        Objects.requireNonNull(edges, "edges");

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException(
                        "Each edge must have two endpoints");
            }
            if (edge[0] < 1 || edge[0] > n
                    || edge[1] < 1 || edge[1] > n) {
                throw new IllegalArgumentException(
                        "Endpoint is outside 1..n");
            }
        }
    }

    // A graph with no edges has a trivial empty-edge trail.
    private static Result noEdges(int n) {
        return yes(n == 0 ? List.of() : List.of(1));
    }

    // Iterative Hierholzer over adjacency with shared edge IDs.
    private static Result traverse(
            List<List<Arc>> adj, int start, int edgeCount) {

        int n = adj.size();
        int[] next = new int[n];
        boolean[] used = new boolean[edgeCount];
        int usedCount = 0;

        Deque<Integer> stack = new ArrayDeque<>();
        List<Integer> reversed = new ArrayList<>(edgeCount + 1);
        stack.push(start);

        while (!stack.isEmpty()) {
            int u = stack.peek();
            List<Arc> out = adj.get(u);

            // Skip adjacency entries whose edge ID was used.
            while (next[u] < out.size()
                    && used[out.get(next[u]).id()]) {
                next[u]++;
            }

            if (next[u] == out.size()) {
                // Finish u only when all its edges are consumed.
                reversed.add(stack.pop() + 1);
            } else {
                Arc arc = out.get(next[u]++);
                used[arc.id()] = true;
                usedCount++;
                stack.push(arc.to());
            }
        }

        // Reject other components that contain unused edges.
        if (usedCount != edgeCount
                || reversed.size() != edgeCount + 1) {
            return no("not all edges lie on one Euler trail");
        }

        Collections.reverse(reversed);
        return yes(reversed);
    }

    // Undirected multigraph, including loops and parallel edges.
    static Result findUndirected(int n, int[][] edges) {
        validate(n, edges);
        int m = edges.length;
        if (m == 0) {
            return noEdges(n);
        }

        List<List<Arc>> adj = newAdj(n);
        int[] degree = new int[n];

        for (int id = 0; id < m; id++) {
            int u = edges[id][0] - 1;
            int v = edges[id][1] - 1;

            // A self-loop contributes TWO to undirected degree.
            degree[u]++;
            degree[v]++;

            // Both entries share the SAME edge ID.
            adj.get(u).add(new Arc(v, id));
            adj.get(v).add(new Arc(u, id));
        }

        int oddCount = 0;
        int start = -1;

        for (int u = 0; u < n; u++) {
            if ((degree[u] & 1) != 0) {
                oddCount++;
                if (start == -1) {
                    start = u;
                }
            }
        }

        if (oddCount != 0 && oddCount != 2) {
            return no("undirected graph needs 0 or 2 odd vertices");
        }

        // If all degrees are even, start at a nonisolated vertex.
        if (start == -1) {
            for (int u = 0; u < n; u++) {
                if (degree[u] > 0) {
                    start = u;
                    break;
                }
            }
        }

        return traverse(adj, start, m);
    }

    // Directed multigraph: edge {u,v} means u -> v.
    static Result findDirected(int n, int[][] edges) {
        validate(n, edges);
        int m = edges.length;
        if (m == 0) {
            return noEdges(n);
        }

        List<List<Arc>> adj = newAdj(n);
        int[] indegree = new int[n];
        int[] outdegree = new int[n];

        for (int id = 0; id < m; id++) {
            int u = edges[id][0] - 1;
            int v = edges[id][1] - 1;

            adj.get(u).add(new Arc(v, id));
            outdegree[u]++;
            indegree[v]++;
        }

        int plusOne = 0;
        int minusOne = 0;
        int start = -1;

        for (int u = 0; u < n; u++) {
            int delta = outdegree[u] - indegree[u];

            if (delta == 1) {
                plusOne++;
                start = u;
            } else if (delta == -1) {
                minusOne++;
            } else if (delta != 0) {
                return no("invalid directed in/out-degree differences");
            }
        }

        if (!((plusOne == 0 && minusOne == 0)
                || (plusOne == 1 && minusOne == 1))) {
            return no("invalid directed in/out-degree differences");
        }

        // Euler circuit: all degrees balanced.
        // Use a vertex with an outgoing arc, not an isolated vertex.
        if (start == -1) {
            for (int u = 0; u < n; u++) {
                if (outdegree[u] > 0) {
                    start = u;
                    break;
                }
            }
        }

        return traverse(adj, start, m);
    }

    static void print(String label, Result result) {
        if (result.possible()) {
            System.out.println(label + ": YES; route="
                    + result.route());
        } else {
            System.out.println(label + ": NO; "
                    + result.reason());
        }
    }

    public static void main(String[] args) {
        print("U circuit", findUndirected(5, new int[][] {
                {1, 2}, {2, 3}, {3, 1},
                {3, 4}, {4, 5}, {5, 3}
        }));

        print("U open", findUndirected(4, new int[][] {
                {1, 2}, {2, 3}, {3, 1}, {3, 4}
        }));

        print("U loop and parallel",
                findUndirected(2, new int[][] {
                        {1, 1}, {1, 2}, {1, 2}
                }));

        print("U disconnected",
                findUndirected(6, new int[][] {
                        {1, 2}, {2, 3}, {3, 1},
                        {4, 5}, {5, 6}, {6, 4}
                }));

        print("U too many odd",
                findUndirected(4, new int[][] {
                        {1, 2}, {1, 3}, {1, 4}
                }));

        print("D circuit", findDirected(3, new int[][] {
                {1, 2}, {2, 3}, {3, 1}
        }));

        print("D open", findDirected(4, new int[][] {
                {1, 2}, {2, 3}, {3, 1}, {1, 4}
        }));

        print("D loop", findDirected(2, new int[][] {
                {1, 1}, {1, 2}, {2, 1}
        }));

        print("D disconnected",
                findDirected(4, new int[][] {
                        {1, 2}, {2, 1},
                        {3, 4}, {4, 3}
                }));

        print("D bad degrees", findDirected(3, new int[][] {
                {1, 2}, {1, 3}
        }));

        print("Isolated start", findUndirected(5,
                new int[][] {{2, 3}, {3, 4}}));

        print("No edges", findUndirected(3, new int[][] {}));
        print("Empty graph", findDirected(0, new int[][] {}));
    }
}
~~~

Lưu đoạn mã vào tệp **HierholzerEulerDemo.java** (UTF-8). Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 HierholzerEulerDemo.java
java HierholzerEulerDemo
~~~

**Đầu ra chính xác** theo thứ tự cạnh đã liệt kê trong chương trình:

~~~text
U circuit: YES; route=[1, 2, 3, 4, 5, 3, 1]
U open: YES; route=[3, 2, 1, 3, 4]
U loop and parallel: YES; route=[1, 1, 2, 1]
U disconnected: NO; not all edges lie on one Euler trail
U too many odd: NO; undirected graph needs 0 or 2 odd vertices
D circuit: YES; route=[1, 2, 3, 1]
D open: YES; route=[1, 2, 3, 1, 4]
D loop: YES; route=[1, 1, 2, 1]
D disconnected: NO; not all edges lie on one Euler trail
D bad degrees: NO; invalid directed in/out-degree differences
Isolated start: YES; route=[2, 3, 4]
No edges: YES; route=[1]
Empty graph: YES; route=[]
~~~

Nếu thay **thứ tự cạnh trong input**, thuật toán vẫn trả một Euler trail hợp lệ nhưng có thể khác về dãy đỉnh. Bài toán không yêu cầu tuyến đường theo thứ tự từ điển; mã ưu tiên Arc xuất hiện sớm trong mỗi danh sách kề.

### Phần cốt lõi của chương trình

**ID cạnh chung cho hai Arc** ngăn một cạnh vô hướng bị đi hai lần. Đối với khuyên tự nối, hai Arc nằm trong cùng danh sách nhưng vẫn có chung ID.

**next[u]** tăng đơn điệu, nên một vị trí adjacency không được quét lại vô hạn. Mã không xóa các phần tử khỏi ArrayList trong lúc duyệt.

**stack** lưu hành trình đang đi; **reversed** chỉ nhận đỉnh khi không còn cạnh chưa sử dụng. Đảo reversed ở cuối để có thứ tự đầu đến cuối.

**findUndirected** đếm bậc đúng với self-loop và chọn gốc là đỉnh lẻ nếu có hai đỉnh lẻ; nếu không thì chọn một đỉnh bậc dương.

**findDirected** chọn gốc có Out−In=+1 nếu trail mở, hoặc đỉnh có outgoing arc nếu circuit.

**traverse** hậu kiểm số cạnh đã dùng và số đỉnh đầu ra, phát hiện graph có những thành phần cạnh không thể nối vào cùng một hành trình.

## 12. Chứng minh tính đúng của Hierholzer

Chứng minh có ba phần: **không lặp cạnh**, **đường đi nối đúng**, và **dùng đủ cạnh** khi điều kiện Euler thỏa.

### 12.1. Không một cạnh nào bị dùng quá một lần

Mỗi cạnh có ID e duy nhất. Trước khi đi qua Arc của e, thuật toán kiểm tra **used[e]**. Ngay lúc chọn e, đặt used[e]=true. Các Arc khác của cùng ID sau đó đều bị bỏ qua.

Vậy trong suốt thuật toán, mỗi ID được đi qua **tối đa một lần**. Với graph vô hướng, việc lưu hai Arc cùng ID không tạo ra hai cạnh thực.

### 12.2. Vì sao thứ tự pop tạo một hành trình liên tục?

Khi có thể đi qua cạnh chưa dùng từ u đến v, thuật toán push v trên stack. Khi không còn cạnh từ u, ta pop u vào reversed.

Hãy xem mỗi lần push như một cạnh của **hành trình đang mở**, còn mỗi lần pop là việc **chốt đỉnh ở vị trí cuối** của một đoạn đã không thể mở rộng thêm. Khi gặp vòng phụ, các đỉnh của vòng được pop và đi vào reversed ngay **trước khi** những đỉnh trên vòng cha được chốt. Đảo thứ tự pop tự động ghép vòng phụ vào đúng vị trí trước/sau cạnh dẫn đến vòng đó.

Đây là cách cài đặt của chứng minh ghép vòng: các tour phụ có thể được tạo tại đỉnh của tour cũ và **splice** vào tour chính. Vì điều kiện bậc bảo đảm không mắc kẹt ở đầu mút sai, việc ghép không tạo lỗ hổng giữa các cạnh.

Với graph có hướng, mỗi push là một **cung đi đúng chiều**; với graph vô hướng, push qua đúng một ID cạnh theo một trong hai chiều có thể đi. Kết quả cuối là hành trình theo đúng loại graph.

### 12.3. Vì sao dùng hết cạnh khi điều kiện tồn tại thỏa?

Trong graph vô hướng liên thông trên đỉnh có cạnh với 0 hoặc 2 đỉnh lẻ, từ gốc thích hợp có thể tiếp tục dùng cạnh chưa sử dụng và ghép các vòng như mô tả; nếu còn một cạnh không dùng thuộc cùng thành phần, phải có một điểm trên hành trình đã xây nối tới phần cạnh chưa dùng, trái với việc đã hoàn tất mọi cạnh đi ra ở những điểm ấy.

Trong graph có hướng với điều kiện indegree/outdegree phù hợp và phần có cung liên thông yếu, lập luận tương tự áp dụng cho những đường đi theo hướng và các vòng ghép vào một tour, hoặc có thể bổ sung cung t→s để quy về trường hợp circuit cân bằng.

Do đó, khi các điều kiện tồn tại thỏa, Hierholzer sử dụng **toàn bộ m cạnh**. Khi điều kiện bậc thỏa nhưng graph có nhiều thành phần chứa cạnh, bắt đầu ở một thành phần không thể dùng cạnh ở phần khác, và hậu kiểm **usedCount!=m** phát hiện trường hợp ấy.

Kết hợp ba phần, kết quả YES là **một Euler trail hợp lệ**, và kết quả NO sau kiểm tra bậc/hậu kiểm biểu thị không có Euler trail theo mô hình.

## 13. Phân tích độ phức tạp

Gọi n=|V| và m=|E| (mỗi ID cạnh đếm một lần).

### Thời gian

- Khởi tạo n danh sách kề: **O(n)**.
- Duyệt m cạnh đầu vào, tạo Arc: **O(m)**.
- Đếm bậc, tìm gốc: **O(n+m)**.
- Trong Hierholzer, mỗi vị trí adjacency được xử lý tối đa một lần qua next[u]. Đồ thị vô hướng có 2m Arc, có hướng có m Arc: **O(m)**.
- Mỗi cạnh thực được push tối đa một lần; mỗi đỉnh trên stack được pop tương ứng với một phần tử đầu ra, tối đa m+1 lần: **O(m)**.
- Đảo dãy kết quả: **O(m)**.

Tổng:

**O(n+m) thời gian**.

### Bộ nhớ

- Adjacency: **O(n+m)**.
- degree hoặc indegree/outdegree: **O(n)**.
- next[]: **O(n)**.
- used[]: **O(m)**.
- Stack và đường đi có tối đa m+1 phần tử: **O(m)**.

Tổng:

**O(n+m) bộ nhớ**.

Độ phức tạp không phụ thuộc vào việc một đỉnh được xuất hiện trong đường Euler nhiều lần. Mỗi lần lặp đỉnh phải tương ứng với một cạnh mới đã được đánh dấu ID, nên tổng lượt xử lý vẫn tuyến tính theo số cạnh.

### Nếu cài DFS đệ quy?

Có thể có phiên bản Hierholzer đệ quy chạy theo cạnh rồi thêm đỉnh khi quay lui. Nhưng với một đường Euler dài m, độ sâu đệ quy có thể là **O(m)**, dễ gây **StackOverflowError** trong Java. Stack tường minh như code trên tránh giới hạn ngăn xếp lời gọi JVM.

### Nếu sắp thứ tự cạnh để có đường Euler nhỏ nhất theo từ điển?

Sắp adjacency có thể tốn thêm O(m log m). Việc tìm **Euler trail nhỏ nhất theo từ điển** còn cần phân tích đúng thứ tự chọn cạnh, nhất là với graph có hướng hoặc yêu cầu bắt đầu cố định. Thuật toán đơn giản ở đây **không tuyên bố trả tuyến đường nhỏ nhất từ điển**.

## 14. Kiểm thử độc lập bằng vét cạn trên đồ thị nhỏ

Với m nhỏ, có thể xây một bộ kiểm thử đối chứng **không dùng công thức Euler và không dùng Hierholzer**:

1. Coi mỗi cạnh input có ID riêng từ 0 đến m−1.
2. Thử tất cả đỉnh xuất phát có thể.
3. DFS trạng thái **(đỉnh hiện tại, tập ID cạnh đã dùng)**.
4. Với graph vô hướng, được sử dụng cạnh e nếu đỉnh hiện tại là một trong hai đầu; bước tiếp theo là đầu còn lại.
5. Với graph có hướng, chỉ được sử dụng cung e nếu đỉnh hiện tại đúng bằng **đầu đi ra**.
6. Nếu đã dùng đủ m ID, tồn tại Euler trail.
7. So kết quả tồn tại của bộ vét cạn với findUndirected hoặc findDirected.

Với m≤9, cách này thường đủ nhanh để thử nhiều graph ngẫu nhiên nhỏ. Nó tốn thời gian tăng theo số cách đi cạnh nên **không thích hợp cho input lớn**.

### Kiểm tra một tuyến đường đã trả về

Một tuyến đường hợp lệ cần thỏa:

- Dài đúng m+1 khi m>0.
- Mỗi cặp đỉnh liền kề trong tuyến đường khớp với **một cạnh ID chưa dùng**.
- Graph có hướng: cặp phải khớp **đúng chiều**.
- Graph vô hướng: có thể dùng cạnh theo cả hai chiều.
- Sau khi lần lượt tiêu thụ các cạnh khớp, **không còn ID nào chưa được sử dụng**.
- Với graph không cạnh, tuyến tầm thường theo quy ước là [] nếu n=0 hoặc [1] nếu n>0.

Kiểm thử chỉ dùng cặp đỉnh mà **không tiêu thụ theo ID** sẽ không phát hiện được lỗi tái sử dụng cùng một cạnh trong graph có cạnh song song.

### Bộ trường hợp nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| n=0,m=0 | YES, [] theo quy ước |
| n>0,m=0 | YES, một đỉnh, chẳng hạn [1] |
| Một cạnh vô hướng | YES, trail mở |
| Một khuyên vô hướng | YES, circuit qua khuyên |
| Hai cạnh song song giữa 1 và 2 | YES, 1→2→1 |
| Đường thẳng | YES, bắt đầu ở đỉnh lẻ |
| Tam giác vô hướng | YES, circuit |
| Hình sao ba lá | NO, có bốn đỉnh lẻ |
| Hai tam giác rời nhau | NO, không liên thông trên phần có cạnh |
| Có đỉnh cô lập bên cạnh một chu trình | YES, bỏ qua đỉnh cô lập |
| Cung đơn 1→2 | YES, trail mở |
| Cung 1→2, 2→1 | YES, circuit có hướng |
| Hai chu trình có hướng tách rời | NO |
| Đỉnh có Out−In=2 | NO |
| Graph có nhiều cung trùng chiều | Phân biệt từng ID |

**Không chỉ tin công thức bậc sau khi code.** Một lỗi nhỏ trong đánh dấu ID hoặc đảo reversed có thể khiến code trả YES và m+1 đỉnh nhưng sai một cạnh; kiểm tra độc lập theo ID giúp phát hiện.

## 15. Euler trail trên đồ thị có hướng và kiểm tra liên thông

Một số tài liệu trình bày điều kiện Euler circuit có hướng theo **liên thông mạnh trên các đỉnh có cung**. Đây là cách phát biểu đúng cho circuit cân bằng. Tuy nhiên, khi giải **Euler trail mở**, yêu cầu mạnh ấy là sai: đường đi có thể không có cung quay từ t về s.

Một cách thống nhất:

- Kiểm tra **điều kiện bậc** theo hướng.
- Kiểm tra **liên thông yếu** của mọi đỉnh có in+out>0, hoặc hậu kiểm đã dùng hết cung sau Hierholzer.
- Chọn **s** theo Out−In=+1 nếu trail mở.
- Trường hợp circuit chọn một đỉnh có Out>0.

Nếu đầu vào có **nhiều SCC** nhưng vẫn có trail mở (chẳng hạn 1→2, 2→3), thuật toán vẫn trả đúng. Nếu đầu vào là hai vòng có hướng tách nhau, bậc đều cân bằng nhưng hậu kiểm không đủ m cung, nên trả NO.

### Tại sao không đảo cung khi gặp nút cụt?

Trong graph có hướng, đường Euler phải tuân theo chiều cung. Nếu đang đứng tại u mà chỉ có một cung v→u chưa dùng, **không thể đi u→v** theo cung đó. Mã chỉ lưu cung trong **adjacency của đầu đi ra**, tránh lỗi này.

### Có thể chọn một đỉnh bắt đầu khác khi circuit?

Khi tất cả in=out và phần có cung liên thông yếu, mọi đỉnh có outdegree>0 đều là điểm bắt đầu hợp lệ của một Euler circuit. Việc chọn nhỏ nhất theo nhãn chỉ làm đầu ra **ổn định**, không thay đổi tính tồn tại.

## 16. Ứng dụng: xếp quân domino và khôi phục chuỗi

### 16.1. Xếp domino thành một chuỗi

Mỗi quân domino [a|b] có thể xem là **một cạnh vô hướng** nối hai giá trị a,b. Muốn xếp tất cả domino thành một hàng mà hai đầu kề nhau có cùng số, ta cần Euler trail trong **đa đồ thị** các giá trị.

Vì có thể có nhiều quân domino cùng số [a|b], phải tạo **ID riêng cho từng quân**, chính xác như mã Hierholzer.

Ví dụ:

~~~text
Domino: [1|2], [2|3], [3|1], [3|4]
Euler trail: 3 -> 2 -> 1 -> 3 -> 4
~~~

Từ tuyến đường suy ra thứ tự đặt domino:

~~~text
[3|2], [2|1], [1|3], [3|4]
~~~

Khi domino không có hướng, có thể lật quân để khớp chiều đi.

### 16.2. Khôi phục chuỗi từ k-mer (de Bruijn graph)

Trong bài phục dựng chuỗi, mỗi từ con độ dài k có thể được biểu diễn thành **một cung**:

- Đỉnh đầu là **prefix dài k−1**.
- Đỉnh cuối là **suffix dài k−1**.
- Mỗi k-mer là **một cung có ID riêng**, kể cả khi nhiều k-mer giống nhau.

Một Euler trail trên các cung tương ứng với cách xếp k-mer sao cho các phần chồng lấn khớp nhau. Sau khi tìm đường, có thể ghép ký tự cuối của mỗi đỉnh tiếp theo để phục hồi chuỗi, theo quy ước k>1 và nhãn đỉnh là chuỗi (k−1)-mer.

Lưu ý đây là **đồ thị có hướng**, và có thể có cung song song. Không được dùng phiên bản vô hướng hoặc gộp các k-mer trùng thành một cung.

### 16.3. Đi qua mọi tuyến đường đúng một lần

Nếu mỗi cạnh là một tuyến hoặc một công việc phải thực hiện đúng một lần, Euler trail cho lịch trình liên tục mà không lặp tuyến. Tuy nhiên, nếu mạng **không có Euler trail**, có thể phải **lặp một số cạnh** hoặc thêm đường để hoàn thành công việc. Đó là những bài khác, chẳng hạn **Chinese Postman Problem**, không phải Hierholzer trực tiếp trên graph gốc.

## 17. Những lỗi phổ biến

1. **Đánh dấu đỉnh visited thay vì cạnh used.** Đường Euler được phép quay lại đỉnh cũ.
2. **Không tạo ID riêng cho cạnh song song.** Hai cạnh cùng đầu mút có thể bị gộp nhầm.
3. **Lưu hai Arc của cạnh vô hướng nhưng cho hai ID khác nhau.** Mỗi cạnh sẽ bị đi hai lần.
4. **Đánh dấu cạnh chỉ sau khi quay lui.** Khi vẫn chưa đánh dấu, cùng cạnh có thể bị đi lại.
5. **Quên đảo danh sách đỉnh ghi khi pop.** Kết quả đảo chiều hoặc không đúng thứ tự.
6. **In thứ tự push như đáp án Euler.** Với các vòng ghép, thứ tự push đơn thuần không nhất thiết là tour hoàn chỉnh đúng.
7. **Quét adjacency từ đầu mỗi lần.** Có thể tăng lên O(m²) trên đỉnh bậc lớn.
8. **Không kiểm tra số đỉnh bậc lẻ ở graph vô hướng.** Có thể khởi động từ đỉnh không hợp lệ.
9. **Đếm self-loop như một bậc trong graph vô hướng.** Đúng là +2.
10. **Quên self-loop làm +1 in và +1 out trong graph có hướng.**
11. **Chọn start=1 kể cả khi đỉnh 1 cô lập.** Có thể trả sai không tồn tại.
12. **Với trail vô hướng có hai đỉnh lẻ, chọn start ở đỉnh chẵn.**
13. **Với trail có hướng, chọn điểm thiếu out thay vì điểm thừa out.**
14. **Kiểm tra degree mà quên connectivity.** Hai vòng rời nhau có mọi bậc chẵn nhưng không có một tour chung.
15. **Buộc toàn bộ đỉnh, kể cả đỉnh cô lập, phải liên thông.** Đây là điều kiện quá mạnh.
16. **Bắt graph có hướng trail mở phải liên thông mạnh.** Sai; chỉ cần điều kiện bậc + liên thông yếu phần có cung.
17. **Xem cung u→v như cạnh vô hướng.** Có thể tạo tuyến đi sai chiều.
18. **Không hậu kiểm đã tiêu thụ hết m ID.** Có thể bỏ sót thành phần có cạnh.
19. **Nhầm số đỉnh đường đi bằng m thay vì m+1.**
20. **Không xử lý graph không cạnh** khi n=0 hoặc n>0.
21. **Dùng DFS đệ quy trên tour rất dài**, dễ StackOverflowError.
22. **Xóa Arc khỏi ArrayList khi duyệt**; thao tác remove ở giữa có thể O(m), làm mất lợi thế tuyến tính.
23. **Tuyên bố thuật toán tìm được đường đi ngắn nhất**; Euler yêu cầu dùng hết cạnh, không tối thiểu hóa số cạnh.
24. **Nhầm Euler trail và Hamilton path**, rồi cấm lặp đỉnh.
25. **Coi mọi chu trình có hướng là đủ cho Euler**, bỏ qua điều kiện in/out và phần có cung.
26. **Dùng một boolean visited cho cặp (u,v) trong multigraph**, làm mất các cạnh trùng.
27. **Không kiểm tra endpoint nằm trong 1..n**, gây lỗi chỉ số.
28. **Không lưu đủ thông tin để xuất ID cạnh** nếu đề yêu cầu thứ tự cạnh thay vì dãy đỉnh.

## 18. Khi đề yêu cầu xuất thứ tự **ID cạnh**

Dãy đỉnh v₀,v₁,...,vₘ mô tả một Euler trail. Nhưng trong **đa đồ thị**, khi có nhiều cạnh song song giữa cùng hai đỉnh, dãy đỉnh **không xác định duy nhất ID cạnh nào** được dùng ở từng bước.

Nếu đề yêu cầu in **danh sách ID cạnh**, cần mở rộng cài đặt:

- Khi push từ u sang v theo Arc(to=v,id=e), lưu cả **ID e** đi kèm bước stack.
- Khi pop và ghi đường đi, ghi ID của **cạnh dùng để đến đỉnh ấy** vào một danh sách đảo, không ghi ID tại gốc.
- Đảo cả danh sách đỉnh và danh sách ID theo thứ tự tương ứng.

Một khung trạng thái phù hợp là:

~~~text
StackEntry = (vertex, incomingEdgeId)

rootEntry = (start, -1)

khi chon canh e tu u den v:
    stack.push((v, e))

khi pop entry (v, incomingId):
    reverseVertices.add(v)
    if incomingId != -1:
        reverseEdgeIds.add(incomingId)

dao reverseVertices
dao reverseEdgeIds
~~~

Sau khi đảo, **edgeIds[i]** chính là cạnh nối **vertices[i]→vertices[i+1]** trong đồ thị có hướng, hoặc một cạnh vô hướng nối hai đỉnh ấy. Việc lưu incomingEdgeId cần đi theo **entry của stack**, không chỉ theo đỉnh, vì cùng một đỉnh có thể xuất hiện nhiều lần trong tour.

Đây là đoạn **pseudocode mở rộng**; chương trình Java chạy độc lập ở mục 11 trả danh sách đỉnh, đúng với mục tiêu chính. Nếu bài muốn thứ tự quân domino riêng biệt, biến thể ghi edge IDs là cần thiết.

## 19. Bài tập tự kiểm tra

**Câu 1.** Đường Euler và đường Hamilton khác nhau ở điều kiện nào?  
**Đáp án:** Euler dùng **mọi cạnh đúng một lần**, có thể lặp đỉnh. Hamilton thăm **mọi đỉnh đúng một lần**, không cần đi hết mọi cạnh.

**Câu 2.** Graph vô hướng liên thông trên phần có cạnh, có 4 đỉnh bậc lẻ. Có Euler trail không?  
**Đáp án:** **Không**, chỉ 0 hoặc 2 đỉnh bậc lẻ là hợp lệ.

**Câu 3.** Graph vô hướng có đúng 2 đỉnh lẻ s,t. Cần bắt đầu ở đâu?  
**Đáp án:** **Một trong hai đỉnh lẻ**, và kết thúc ở đỉnh lẻ kia.

**Câu 4.** Có hai tam giác tách nhau, mọi bậc bằng 2. Vì sao không có Euler circuit toàn graph?  
**Đáp án:** Các đỉnh có cạnh thuộc **hai thành phần liên thông**; không thể dùng tất cả cạnh bằng một hành trình liên tục.

**Câu 5.** Một self-loop vô hướng ở u đóng góp bao nhiêu vào degree[u]?  
**Đáp án:** **Hai**.

**Câu 6.** Hai cạnh song song nối 1 và 2 có thể tạo Euler circuit không?  
**Đáp án:** Có, một circuit là **1→2→1**, dùng từng ID riêng.

**Câu 7.** Vì sao phải lưu ID cạnh trong Hierholzer?  
**Đáp án:** Để đánh dấu **mỗi cạnh thực đúng một lần** khi graph có hai bản ghi adjacency của một cạnh hoặc có nhiều cạnh trùng đầu mút.

**Câu 8.** Trong stack Hierholzer, khi nào thêm một đỉnh vào reversed?  
**Đáp án:** Khi tại đỉnh đó **không còn cạnh chưa dùng** có thể đi tiếp.

**Câu 9.** Tại sao phải reverse danh sách reversed sau thuật toán?  
**Đáp án:** Các đỉnh được ghi theo **thứ tự pop/quay lui**, ngược với thứ tự trail cần xuất.

**Câu 10.** Có thể luôn chọn đỉnh 1 làm start không?  
**Đáp án:** Không. Đỉnh 1 có thể cô lập hoặc không có bậc phù hợp cho trail mở.

**Câu 11.** Với graph có hướng, điểm đầu của Euler trail mở có quan hệ in/out thế nào?  
**Đáp án:** **outdegree = indegree+1**.

**Câu 12.** Graph có hướng 1→2 chỉ có một cung, không liên thông mạnh. Có Euler trail không?  
**Đáp án:** Có: **1→2**. Không cần liên thông mạnh cho trail mở.

**Câu 13.** Sau khi chạy Hierholzer trên graph m cạnh, phải kiểm tra gì?  
**Đáp án:** **Đã dùng đủ m ID cạnh** và dãy đỉnh có **m+1 phần tử**; các điều kiện bậc/start phải được áp dụng đúng.

**Câu 14.** Độ phức tạp Hierholzer với next[u] và adjacency list?  
**Đáp án:** **O(n+m)** thời gian và **O(n+m)** bộ nhớ.

**Câu 15.** Vì sao visited[vertex] không phù hợp để kiểm tra Euler?  
**Đáp án:** Một đỉnh có thể cần xuất hiện nhiều lần để đi hết những cạnh khác nhau.

**Câu 16.** Nếu đề yêu cầu in ID cạnh trên graph có nhiều cạnh song song, dãy đỉnh có đủ không?  
**Đáp án:** Chưa. Cần lưu **incomingEdgeId** cùng entry trong stack rồi đảo danh sách ID khi chốt tour.

## 20. Tổng kết

Để tìm **đường đi Euler bằng Hierholzer**, hãy làm đúng các bước sau:

1. **Xác định graph vô hướng hay có hướng.** Không áp dụng điều kiện bậc của loại này cho loại kia.
2. **Kiểm tra điều kiện bậc**:
   - Vô hướng: có **0 hoặc 2** đỉnh bậc lẻ.
   - Có hướng: mọi in=out cho circuit; hoặc đúng một đỉnh Out−In=+1 và một đỉnh Out−In=−1 cho trail mở.
3. **Chọn start đúng**, bỏ qua các đỉnh cô lập khi graph có cạnh.
4. **Mỗi cạnh có một ID**. Cạnh vô hướng được lưu hai Arc **cùng ID**, cung có hướng được lưu một Arc.
5. **Dùng stack**: còn cạnh chưa dùng thì đi và push; hết cạnh thì pop vào reversed.
6. **Đảo reversed** để thu dãy đỉnh theo thứ tự Euler.
7. **Hậu kiểm đã dùng hết m cạnh** và độ dài tuyến đường m+1, nhằm phát hiện những thành phần chứa cạnh không nối được.
8. **Sử dụng next[u]** để tránh quét lại adjacency, giữ tổng thời gian **O(n+m)**.

**Câu then chốt để không nhầm bài:** Euler bắt buộc **đi qua mọi cạnh đúng một lần**, không bắt buộc thăm mỗi đỉnh đúng một lần. Một khi điều kiện bậc và liên thông trên phần chứa cạnh được thỏa, Hierholzer xây dựng tuyến đường bằng việc **đi cạnh chưa dùng và ghép vòng qua thứ tự quay lui**, chứ không phải tìm đường ngắn nhất hoặc duyệt DFS visited theo đỉnh.