# Phát hiện chu trình âm có thể đạt từ nguồn

Trong bài toán **đường đi ngắn nhất trên đồ thị có hướng, có trọng số**, một **chu trình âm** (*negative-weight cycle*) là một chu trình có tổng trọng số các cạnh nhỏ hơn 0. Khi có thể đi từ nguồn s tới chu trình âm, ta có thể đi vòng quanh chu trình nhiều lần để giảm tổng trọng số của một hành trình. Nhưng tác động của chu trình âm không tự động lan tới toàn bộ đồ thị: nó chỉ ảnh hưởng đến những đỉnh mà ta có thể tiếp tục đi tới **từ chu trình âm đó**.

Vì vậy, trong bài toán đường đi ngắn nhất **từ một nguồn s**, cần phân biệt ba trạng thái của một đỉnh v:

- **UNREACHABLE**: không có đường đi có hướng từ s tới v, thường ký hiệu khoảng cách `+∞`.
- **Khoảng cách hữu hạn**: có đường đi từ s tới v, nhưng không có chu trình âm nào vừa đạt được từ s vừa có đường đi tới v.
- **-INF**: có chu trình âm C sao cho `s⇝C⇝v`; tổng trọng số các walk s→v có thể giảm không giới hạn, nên khoảng cách được mô tả bằng `−∞`.

Phương pháp kinh điển để phát hiện chu trình âm **có thể đạt từ nguồn** là **Bellman–Ford**. Sau tối đa `V−1` lượt nới lỏng mọi cạnh, thuật toán thực hiện thêm **lượt thứ V**. Nếu vẫn có cập nhật xuất phát từ đỉnh đã đạt được, ta đã chứng minh có chu trình âm mà nguồn đi tới được. Một chu trình làm chứng có thể phục dựng qua mảng `predecessor`, còn tập **tất cả** các đỉnh có khoảng cách `−∞` phải được tìm bằng cách lan truyền theo các cạnh có hướng từ mọi đỉnh còn được cập nhật trong lượt cuối.

Bài thuộc chủ đề **Đường đi ngắn nhất**, tập trung vào câu hỏi **Phát hiện chu trình âm có thể đạt từ nguồn** — khác với phát hiện chu trình âm ở bất kỳ vị trí nào của đồ thị. Bài sẽ giải thích định nghĩa, bất biến, chứng minh đúng, ví dụ thủ công, trạng thái không đạt, phục dựng chu trình, vùng ảnh hưởng, giới hạn số học, Java 17+ hoàn chỉnh, kiểm thử ngẫu nhiên độc lập và những lỗi thường gặp.

## 1. Mô hình đồ thị, đường đi và chu trình âm

Cho đồ thị có hướng `G=(V,E)` với n đỉnh, đánh số từ 0 đến n−1. Một cạnh `(u,v,w)` đi **từ u tới v**, có trọng số nguyên w có thể âm, bằng 0 hoặc dương. Đồ thị có thể có cạnh song song và self-loop.

Một **walk** từ s tới t là chuỗi cạnh có hướng nối tiếp nhau, **được phép lặp đỉnh và cạnh**. Trọng số walk là tổng trọng số các cạnh. Nếu mọi walk s→t đều có chi phí lớn hơn hoặc bằng một số hữu hạn và có walk đạt số ấy, ta gọi số ấy là khoảng cách ngắn nhất `d(s,t)`.

Nếu walk có thể đi qua chu trình C tổng trọng số `W(C)<0`, bằng cách lặp C đúng k lần:

**`cost_k=A+k·W(C)+B`**,

trong đó A là chi phí đi từ s tới C, còn B là chi phí từ C tới t. Khi k tăng không giới hạn, `cost_k→−∞`. Vì vậy **không có đường đi ngắn nhất hữu hạn**, dù mỗi walk cụ thể vẫn có tổng trọng số hữu hạn.

**Điều kiện chính xác:** tồn tại chu trình âm C với đường từ **s tới C** và từ **C tới t**. Chỉ cần có một chu trình âm đâu đó trong đồ thị là **chưa đủ**.

### Cạnh âm không phải chu trình âm

Giả sử có cạnh `0→1` trọng số −5 và `1→2` trọng số +2, không có cạnh quay về. Với nguồn 0, `d(0,1)=−5` và `d(0,2)=−3` đều là số hữu hạn. Không có chu trình âm nào.

Ngược lại, nếu có `1→2` trọng số +2 và `2→1` trọng số −4, chu trình `1→2→1` có tổng **−2**. Nếu s tới được 1, ta có thể lặp chu trình để làm giảm chi phí đến 1,2 và mọi đỉnh đạt được từ chúng.

### Thành phần tách biệt và chiều cạnh

Nếu chu trình âm chỉ nằm trong một vùng **nguồn không đi tới**, Bellman–Ford từ nguồn không được báo có chu trình âm đạt được. Cạnh chỉ đi **từ chu trình về s** cũng chưa đủ: điều ta cần là **s đi tới chu trình**, không phải điều ngược lại.

Nếu bài hỏi “đồ thị có chu trình âm ở bất kỳ đâu không?”, có thể thêm **siêu nguồn** nối tới mọi đỉnh bằng cạnh 0, hoặc dùng một biến thể khởi tạo mọi dist bằng 0. Nhưng cách ấy **không phù hợp** khi đề yêu cầu chu trình âm **đạt được từ một nguồn s đã cho**.

## 2. Ví dụ ba loại khoảng cách

Xét đồ thị 6 đỉnh có nguồn 0 và các cạnh:

| Từ | Đến | Trọng số |
|---:|---:|---:|
| 0 | 1 | +1 |
| 1 | 2 | +2 |
| 2 | 1 | −4 |
| 2 | 3 | +2 |
| 3 | 4 | +2 |
| 0 | 5 | +10 |

Chu trình `1→2→1` có trọng số `2−4=−2`. Nguồn 0 đi tới chu trình qua cạnh `0→1`, và từ chu trình đi tiếp được tới 3,4. Nhưng chu trình không có đường tới 0 hay 5.

Kết luận:

- Đỉnh 0: `d(0,0)=0`, vì không có đường từ chu trình quay lại 0.
- Các đỉnh 1,2: nằm trên chu trình âm, khoảng cách là **−∞**.
- Các đỉnh 3,4: ở phía **sau chu trình**, cũng có khoảng cách **−∞**.
- Đỉnh 5: chỉ nhận đường `0→5` trọng số 10, nên khoảng cách vẫn **10**, không phải −∞.

Phân loại theo thứ tự đỉnh 0..5:

~~~text
[0, -INF, -INF, -INF, -INF, 10]
~~~

Một lỗi phổ biến là thấy chu trình âm đạt được rồi lập tức ghi `-INF` cho **mọi đỉnh nguồn có thể tới**; cách đó sai với đỉnh 5.

### Ví dụ chu trình âm không đạt được

Giữ nguồn 0, với các cạnh:

`0→1` (+4), `0→2` (+5), `1→2` (−2), `2→3` (+3), `4→5` (−10), `5→4` (+1).

Chu trình `4→5→4` có trọng số −9, nhưng không có đường từ 0 tới 4 hoặc 5. Vì thế kết quả từ nguồn 0 là:

~~~text
[0, 4, 2, 5, UNREACHABLE, UNREACHABLE]
~~~

và kết quả kiểm tra **chu trình âm có thể đạt từ nguồn 0** là **false**.

## 3. Relaxation: phép chuyển cốt lõi của Bellman–Ford

Với mỗi cạnh có hướng `u→v` trọng số w, nếu biết một walk từ nguồn s tới u có tổng `dist[u]`, ta có thể nối thêm cạnh ấy để tạo walk từ s tới v với chi phí:

**`candidate=dist[u]+w`.**

Nếu v chưa có walk nào được phát hiện, hoặc candidate nhỏ hơn giá trị đang có, cập nhật:

**`dist[v]=candidate`**.

Khi muốn phục dựng chứng cứ, lưu thêm:

- `predecessor[v]=u`;
- `predecessorWeight[v]=w` hoặc ID của cạnh u→v **thực sự được dùng**.

Pseudocode:

~~~text
relax(u, v, w):
    if dist[u] is UNREACHABLE:
        return false
    candidate = dist[u] + w
    if dist[v] is UNREACHABLE or candidate < dist[v]:
        dist[v] = candidate
        predecessor[v] = u
        predecessorWeight[v] = w
        return true
    return false
~~~

**Chỉ nới lỏng từ đỉnh đã đạt được.** Nếu dùng số rất lớn `INF` để biểu diễn chưa đạt rồi cứ tính `INF+w`, với w âm phép so sánh có thể tạo ra một khoảng cách giả dù không hề có đường đi từ s tới u. Đây là lỗi làm phát hiện nhầm chu trình âm trong những thành phần tách biệt.

Mã Java của bài dùng `BigInteger[] dist`, trong đó `null` nghĩa là chưa đạt, nên không bao giờ cộng một “vô cùng giả” với trọng số.

### Phân biệt relaxation và việc đảo cạnh

Một cạnh u→v chỉ cho phép chuyển từ dist[u] sang dist[v]. Nếu không có cạnh ngược v→u, tuyệt đối không thể nới lỏng ngược. Nhầm hướng cạnh có thể tự tạo thêm chu trình âm giả.

## 4. Tại sao dùng n−1 lượt?

Một đường đi đơn trên n đỉnh có tối đa **n−1 cạnh**. Nếu một walk từ s tới t có lặp đỉnh nhưng tất cả chu trình nằm trên walk đều có tổng trọng số không âm, ta có thể bỏ chúng để không tăng chi phí. Do đó khi khoảng cách tới t **hữu hạn**, có một đường đi đơn đạt khoảng cách tối ưu.

Bellman–Ford khởi tạo `dist[s]=0`, các đỉnh khác chưa đạt, rồi duyệt **toàn bộ E cạnh** tối đa n−1 lượt. Sau lượt k, những đường đi tối ưu dùng tối đa k cạnh đã có cơ hội được truyền tới đỉnh cuối. Vì thế n−1 lượt đủ để tìm mọi khoảng cách ngắn nhất hữu hạn nếu không có chu trình âm ảnh hưởng.

Trong triển khai **in-place**, một giá trị vừa được cập nhật ở đầu lượt có thể được sử dụng tiếp ở cuối lượt, nên đôi khi một lượt đã truyền qua nhiều cạnh. Điều này không làm thuật toán sai: mọi giá trị mới vẫn là trọng số của một walk hợp lệ từ s. Cận n−1 lượt vẫn đúng.

Nếu có một lượt duyệt hết cạnh mà **không giảm bất kỳ khoảng cách nào**, có thể dừng sớm; giá trị đã đạt điểm cố định. Trái lại, khi có chu trình âm đạt được, mỗi lượt quét đủ các cạnh của chu trình sau khi đã đạt nó sẽ còn cơ hội giảm.

### Tại sao không phát hiện chỉ vì có cập nhật trong n−1 lượt?

Một đồ thị không có chu trình âm vẫn có các cập nhật trong các lượt đầu vì thuật toán đang phát hiện các đường đi ngày càng tốt hơn. Cập nhật **trước khi đủ n−1 lượt** không phải bằng chứng về chu trình âm. Tín hiệu đặc biệt chỉ xuất hiện khi đã quét đủ số lượt dành cho mọi đường đi đơn mà **vẫn** còn cải thiện.

## 5. Lượt thứ n: tiêu chuẩn phát hiện

Sau tối đa n−1 lượt, quét các cạnh **thêm một lượt** (lượt thứ n). Với mỗi cạnh u→v, chỉ xét nếu dist[u] đã đạt được, và kiểm tra:

**`dist[u]+w < dist[v]`**,

hoặc v chưa được phát hiện. Nếu có cập nhật nào, đồ thị chứa **chu trình âm có thể đạt từ s**.

~~~text
changedOnNth = empty set

for each edge (u, v, w):
    if dist[u] is UNREACHABLE:
        continue
    candidate = dist[u] + w
    if dist[v] is UNREACHABLE or candidate < dist[v]:
        dist[v] = candidate
        predecessor[v] = u
        predecessorWeight[v] = w
        changedOnNth.add(v)

hasReachableNegativeCycle = not changedOnNth.empty
~~~

Có thể cập nhật dist **ngay trong lượt này**. Tập `changedOnNth` nên chứa **tất cả đỉnh được giảm trong lượt n**, không chỉ một đỉnh cuối cùng, nếu cần xác định mọi đỉnh có khoảng cách −∞.

### Vì sao dấu nhỏ hơn phải nghiêm ngặt?

Một chu trình tổng trọng số **0** có thể tạo vô số walk bằng nhau nhưng không làm chi phí giảm không giới hạn. Việc cập nhật khi `candidate==dist[v]` sẽ nhầm các trường hợp hòa với cải thiện và có thể làm sai tín hiệu chu trình âm. Chỉ tính là cập nhật khi **thật sự nhỏ hơn** (hoặc trạng thái trước đó chưa đạt).

### n=1 vẫn phải kiểm tra

Nếu chỉ có một đỉnh s=0 với self-loop `0→0` trọng số −1, số lượt chuẩn n−1 bằng 0, nhưng lượt thứ n bằng 1 vẫn phải nới lỏng cạnh và phát hiện chu trình âm. Nếu self-loop có trọng số 0 hay dương, không có cập nhật nghiêm ngặt ở lượt đó.

## 6. Chứng minh hai chiều của tiêu chuẩn Bellman–Ford

**Chiều A: không có chu trình âm đạt từ s ⇒ lượt n không giảm.**

Nếu không có chu trình âm đạt được từ s, các đường đi có tổng tối ưu hữu hạn có thể chọn không lặp đỉnh: bỏ mỗi chu trình có trọng số không âm khỏi một walk sẽ không làm tổng tăng. Một đường đi đơn có không quá n−1 cạnh. Vì vậy sau n−1 lượt, mọi dist hữu hạn đã là ngắn nhất. Không thể nới lỏng để tìm walk tốt hơn ở lượt thứ n. Những đỉnh không đạt từ s vẫn bị bỏ qua vì không có dist[u] hữu hạn để nối cạnh.

**Chiều B: có chu trình âm đạt từ s ⇒ lượt n phải giảm.**

Xét chu trình `v₀→v₁→…→v_{k−1}→v₀` có tổng `W<0`. Tất cả đỉnh trên chu trình đều đạt được từ s, nên sau đủ lượt chúng có dist hữu hạn. Nếu một lượt quét tất cả cạnh của chu trình mà không có cập nhật nào trên chúng, ta sẽ có tất cả bất đẳng thức:

`dist[v_{i+1}] ≤ dist[v_i]+w_i`.

Cộng k bất đẳng thức vòng quanh chu trình, các dist triệt tiêu và ta suy ra `0≤Σw_i=W`, mâu thuẫn với `W<0`. Vì thế chu trình bắt buộc còn gây cập nhật ở lượt thứ n.

Kết hợp hai chiều:

**Có cải thiện ở lượt n từ một đỉnh đạt được ⇔ tồn tại chu trình âm mà nguồn s đi tới được.**

Điều kiện “u đạt được” là thiết yếu: bỏ nó sẽ biến phép kiểm tra theo nguồn thành phép kiểm tra sai trên cả vùng không có đường từ s.

## 7. Những đỉnh nào bị ảnh hưởng bởi chu trình âm?

Giả sử thuật toán tìm được một chu trình âm C đạt từ s. Một đỉnh t có khoảng cách −∞ **khi và chỉ khi** có thể đi từ C tới t (đối với ít nhất một chu trình âm đạt từ s).

Lý do là ta có thể đi `s⇝C`, lặp chu trình âm k lần, rồi đi `C⇝t`. Khi k tăng, tổng trọng số giảm không giới hạn. Ngược lại, một đỉnh không đạt được từ bất kỳ chu trình âm nào đạt từ s chỉ có thể có khoảng cách ngắn nhất hữu hạn nếu bản thân nó đạt từ s.

### Lan truyền vùng -INF

Tập các đỉnh được giảm ở lượt n là những **hạt giống**. Dùng BFS hoặc DFS theo các **cạnh gốc u→v** từ tất cả hạt giống để đánh dấu `affected[v]`.

~~~text
queue = all vertices changed on the n-th pass
affected[each seed] = true

while queue not empty:
    u = queue.remove()
    for each original edge u -> v:
        if not affected[v]:
            affected[v] = true
            queue.add(v)

for each vertex v:
    if dist[v] is UNREACHABLE:
        status[v] = "UNREACHABLE"
    else if affected[v]:
        status[v] = "-INF"
    else:
        status[v] = dist[v]  // exact finite shortest distance
~~~

**Không** chỉ BFS từ nhân chứng chu trình đầu tiên khi muốn phân loại mọi đỉnh. Có thể có nhiều chu trình âm ở các vùng khác nhau, đều đạt được từ s. Một nhân chứng chỉ chứng minh **sự tồn tại**, còn tập `changedOnNth` chứa tín hiệu từ các vùng ảnh hưởng khác nhau.

### Vì sao khởi tạo BFS từ mọi đỉnh được giảm là đủ?

Mỗi chu trình âm đạt được làm một số cạnh của nó tiếp tục cải thiện trong lượt n; các cập nhật ấy tạo hạt giống nằm trên hoặc chịu ảnh hưởng từ chu trình. Mọi đỉnh đi tới được từ chu trình âm sẽ đi tới được từ ít nhất một hạt giống liên quan, nên BFS bao phủ cả vùng có −∞.

Mặt khác, một đỉnh bị đánh dấu chỉ vì có đường từ hạt giống sẽ có thể nhận walk với tổng chi phí nhỏ không giới hạn theo chu trình âm ở phía trước. BFS theo hướng cạnh gốc, không phải transpose, là đúng chiều lan truyền ảnh hưởng.

## 8. Phục dựng một chu trình âm làm chứng

Để xuất một chu trình thực, lưu `predecessor[v]` mỗi khi dist[v] giảm. Tiền nhiệm của v là u với cạnh **u→v**. Trong đồ thị có **cạnh song song**, lưu thêm `predecessorWeight[v]` hoặc ID của cạnh được dùng: chỉ biết cặp đỉnh u,v không đủ để tính tổng trọng số của một chu trình cụ thể.

Giả sử lượt n có đỉnh `x` được giảm cuối cùng. x có thể ở **phía sau** chu trình âm, nên không thể mặc định x nằm ngay trên chu trình.

Các bước chuẩn:

1. Đặt `start=x`; thực hiện `n` lần `start=predecessor[start]`. Sau n bước trong một đồ thị n đỉnh, start nằm trên một vòng của chuỗi tiền nhiệm.
2. Từ start đi tiếp predecessor cho tới khi quay về start, ghi các đỉnh. Chuỗi này chạy **ngược chiều** các cạnh đồ thị gốc.
3. Thêm start lần nữa để khép chu trình, rồi **đảo thứ tự** để có dãy đi đúng theo cạnh gốc.
4. Có thể xoay dãy sao cho đỉnh nhỏ nhất đứng đầu nhằm tạo kết quả ổn định.
5. Tính trọng số chu trình bằng **đúng các cạnh tiền nhiệm đã chọn**, kiểm tra tổng **âm**.

Ví dụ `1→2` (+2) và `2→1` (−4) có chu trình hiển thị:

~~~text
cycle = [1, 2, 1]
cycleWeight = -2
~~~

Một self-loop âm `1→1` (−1) cho nhân chứng `[1,1]`, tổng −1.

### Vì sao phải đi ngược n bước?

Đỉnh x được giảm ở lượt n có thể chỉ là hậu duệ của chu trình âm, ví dụ `cycle→a→b→x`. Chuỗi predecessor từ x lần theo nguồn của cập nhật, rồi rơi vào vòng lặp. Vì có n đỉnh, đi ít nhất n tiền nhiệm loại đoạn “đuôi” trước vòng, đặt ta ở một đỉnh trên vòng.

**Đừng xây đường đi về s vô hạn từ một đỉnh −INF**: predecessor chứa chu trình, nên vòng lặp tìm nguồn có thể không dừng. Cần chủ động tìm và khép chu trình.

### Nhân chứng và tập đỉnh -INF khác nhau

Một lần lấy `lastUpdated` có thể dựng **một** chu trình âm. Nhưng để đánh dấu đầy đủ −INF, dùng **mọi hạt giống** từ lượt n. Đừng coi một cycle witness là danh sách đầy đủ các chu trình âm, hoặc coi mọi đỉnh từ nguồn đạt tới là −INF.

## 9. Ví dụ một nhánh không bị ảnh hưởng

Nguồn 0; các cạnh:

`0→1` (+1), `1→2` (+1), `2→1` (−3), `0→3` (+5), `3→4` (+1).

Chu trình `1→2→1` có trọng số −2, đạt từ nguồn qua 0→1. Từ chu trình **không có đường** tới 3 và 4. Vì vậy:

~~~text
hasReachableNegativeCycle = true
cycle = [1, 2, 1]
distanceStatus = [0, -INF, -INF, 5, 6]
~~~

Đường đi tốt nhất từ 0 tới 3 vẫn có chi phí 5; từ 0 tới 4 có chi phí 6. Nếu câu hỏi chỉ liên quan đến đích t=4, đáp án vẫn hữu hạn **mặc dù đồ thị có chu trình âm đạt được từ s**.

Với đích t cụ thể, cần kiểm tra cả hai điều kiện:

- Có chu trình âm nguồn đi tới được.
- Chu trình âm ấy đi tới được t.

Không kết luận khoảng cách đến **mọi** t là −∞ chỉ từ boolean phát hiện chu trình âm.

## 10. Số học an toàn: không dùng INF như số thật

Cài đặt phổ biến nhưng nguy hiểm:

~~~java
// Sai nếu dist[u] là INF giả và phép cộng vẫn được thực hiện.
if (dist[u] + weight < dist[v]) {
    dist[v] = dist[u] + weight;
}
~~~

Với `INF=1_000_000_000`, một cạnh trọng số −5 từ u chưa đạt tới v có thể khiến `INF−5<INF`, tạo khoảng cách giả. Khi số rất lớn, `dist[u]+weight` còn có thể **tràn long**, đảo dấu và gây phát hiện sai chu trình âm.

**Có ba cách tiếp cận đúng:**

1. Dùng trạng thái đạt được tách biệt với số (ví dụ `boolean[] reachable` và `long[] dist`), chỉ cộng khi reachable[u], đồng thời **chứng minh mọi phép cộng không tràn**.
2. Dùng `Math.addExact` để phát hiện tràn và xử lý/từ chối đầu vào. Lựa chọn này không tự giải quyết được nhu cầu biểu diễn mọi tổng toán học lớn hơn 64 bit.
3. Dùng **BigInteger** hoặc kiểu số chính xác đủ rộng. Bài này dùng `BigInteger[] dist` và `null` làm dấu chưa đạt, nên tổng chi phí không bị tràn long.

Mã Java nhận trọng số cạnh kiểu `long` nhưng dùng `BigInteger.valueOf(weight)` để cộng chính xác. Trọng số một walk qua nhiều lượt có thể vượt long; BigInteger vẫn biểu diễn chính xác. Đổi lại, chi phí của phép cộng/so sánh BigInteger phụ thuộc độ dài bit của số, nên khi nói thời gian O(VE) cần hiểu đó là **số phép toán số học**.

**Không đặt `-INF` như một số nguyên cực nhỏ rồi tiếp tục cộng cạnh.** Trong bài này -INF chỉ là trạng thái được kết luận **sau khi đánh dấu vùng ảnh hưởng**, không phải một khoảng cách hữu hạn dùng trong phép relax.

## 11. Java 17+ hoàn chỉnh: phát hiện và phân loại khoảng cách

Chương trình dưới đây sử dụng:

- Record `Edge(from,to,weight)` cho cạnh có hướng, trọng số long.
- `BigInteger[] dist` với null biểu diễn **UNREACHABLE**.
- Bellman–Ford tối đa n−1 lượt, có dừng sớm nếu toàn lượt không đổi.
- Lượt n ghi **mọi đỉnh giảm thêm** làm seed cho BFS.
- Mảng predecessor và predecessorWeight để dựng **một chu trình âm** đúng hướng, có tổng trọng số âm.
- BFS theo cạnh gốc để phân loại các đỉnh **-INF**.
- Danh sách kết quả theo thứ tự đỉnh, in `UNREACHABLE`, `-INF` hoặc số nguyên hữu hạn.
- Chấp nhận self-loop và cạnh song song, nhưng yêu cầu `n≥1` và source hợp lệ. Đồ thị n=0 không có nguồn nên API này từ chối nó.

Lưu thành **`ReachableNegativeCycleDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class ReachableNegativeCycleDemo {
    private record Edge(int from, int to, long weight) {}

    private record Analysis(
            boolean hasReachableNegativeCycle,
            List<Integer> cycle,
            BigInteger cycleWeight,
            List<String> distanceStatus) {}

    static Analysis analyze(int n, int source, List<Edge> edges) {
        if (n <= 0 || source < 0 || source >= n || edges == null) {
            throw new IllegalArgumentException("Invalid graph/source");
        }

        List<List<Integer>> outgoing = new ArrayList<>(n);
        for (int v = 0; v < n; v++) {
            outgoing.add(new ArrayList<>());
        }
        for (Edge e : edges) {
            if (e == null || e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException("Invalid directed edge");
            }
            outgoing.get(e.from()).add(e.to());
        }

        BigInteger[] dist = new BigInteger[n];
        int[] predecessor = new int[n];
        long[] predecessorWeight = new long[n];
        Arrays.fill(predecessor, -1);
        dist[source] = BigInteger.ZERO;

        // At most n-1 complete relaxation passes.
        for (int pass = 0; pass < n - 1; pass++) {
            boolean changed = false;
            for (Edge e : edges) {
                if (dist[e.from()] == null) {
                    continue;
                }
                BigInteger candidate = dist[e.from()].add(
                        BigInteger.valueOf(e.weight()));
                BigInteger old = dist[e.to()];
                if (old == null || candidate.compareTo(old) < 0) {
                    dist[e.to()] = candidate;
                    predecessor[e.to()] = e.from();
                    predecessorWeight[e.to()] = e.weight();
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
        }

        // Pass n: collect ALL changed vertices as BFS seeds.
        boolean[] changedOnNth = new boolean[n];
        int lastUpdated = -1;
        for (Edge e : edges) {
            if (dist[e.from()] == null) {
                continue;
            }
            BigInteger candidate = dist[e.from()].add(
                    BigInteger.valueOf(e.weight()));
            BigInteger old = dist[e.to()];
            if (old == null || candidate.compareTo(old) < 0) {
                dist[e.to()] = candidate;
                predecessor[e.to()] = e.from();
                predecessorWeight[e.to()] = e.weight();
                changedOnNth[e.to()] = true;
                lastUpdated = e.to();
            }
        }

        // Propagate -INF along ORIGINAL edge directions.
        boolean[] affected = new boolean[n];
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int v = 0; v < n; v++) {
            if (changedOnNth[v]) {
                affected[v] = true;
                queue.addLast(v);
            }
        }
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : outgoing.get(u)) {
                if (!affected[v]) {
                    affected[v] = true;
                    queue.addLast(v);
                }
            }
        }

        List<Integer> witness = List.of();
        BigInteger cycleWeight = null;
        if (lastUpdated != -1) {
            int start = lastUpdated;
            // Enter the predecessor cycle.
            for (int i = 0; i < n; i++) {
                start = predecessor[start];
                if (start < 0) {
                    throw new IllegalStateException(
                            "Broken negative-cycle predecessor chain");
                }
            }

            List<Integer> reversed = new ArrayList<>();
            int current = start;
            do {
                reversed.add(current);
                current = predecessor[current];
                if (current < 0 || reversed.size() > n) {
                    throw new IllegalStateException(
                            "Cannot close predecessor cycle");
                }
            } while (current != start);
            reversed.add(start);
            Collections.reverse(reversed);

            // Rotate to smallest vertex for reproducible display.
            int length = reversed.size() - 1;
            int first = 0;
            for (int i = 1; i < length; i++) {
                if (reversed.get(i) < reversed.get(first)) {
                    first = i;
                }
            }
            List<Integer> forward = new ArrayList<>(length + 1);
            for (int i = 0; i < length; i++) {
                forward.add(reversed.get((first + i) % length));
            }
            forward.add(forward.get(0));

            BigInteger sum = BigInteger.ZERO;
            for (int i = 1; i < forward.size(); i++) {
                int from = forward.get(i - 1);
                int to = forward.get(i);
                if (predecessor[to] != from) {
                    throw new IllegalStateException(
                            "Broken cycle orientation");
                }
                sum = sum.add(BigInteger.valueOf(
                        predecessorWeight[to]));
            }
            if (sum.signum() >= 0) {
                throw new IllegalStateException("Witness is not negative");
            }
            witness = List.copyOf(forward);
            cycleWeight = sum;
        }

        List<String> status = new ArrayList<>(n);
        for (int v = 0; v < n; v++) {
            if (dist[v] == null) {
                status.add("UNREACHABLE");
            } else if (affected[v]) {
                status.add("-INF");
            } else {
                status.add(dist[v].toString());
            }
        }

        return new Analysis(
                lastUpdated != -1, witness,
                cycleWeight, List.copyOf(status));
    }

    private static void show(
            String name, int n, int source, Edge... edges) {
        Analysis result = analyze(n, source, Arrays.asList(edges));
        System.out.println(
                name + ": cycle=" + result.hasReachableNegativeCycle()
                + ", witness=" + result.cycle()
                + ", weight=" + (result.cycleWeight() == null
                        ? "none" : result.cycleWeight()));
        System.out.println(name + ": dist=" + result.distanceStatus());
    }

    public static void main(String[] args) {
        show("Reachable", 6, 0,
                new Edge(0, 1, 1), new Edge(1, 2, 2),
                new Edge(2, 1, -4), new Edge(2, 3, 2),
                new Edge(3, 4, 2), new Edge(0, 5, 10));

        show("Disconnected", 6, 0,
                new Edge(0, 1, 4), new Edge(0, 2, 5),
                new Edge(1, 2, -2), new Edge(2, 3, 3),
                new Edge(4, 5, -10), new Edge(5, 4, 1));

        show("Self-loop", 3, 0,
                new Edge(0, 1, 2), new Edge(1, 1, -1),
                new Edge(1, 2, 4));

        show("Branch", 5, 0,
                new Edge(0, 1, 1), new Edge(1, 2, 1),
                new Edge(2, 1, -3), new Edge(0, 3, 5),
                new Edge(3, 4, 1));

        show("Negative edge", 3, 0,
                new Edge(0, 1, -5), new Edge(1, 2, 2),
                new Edge(0, 2, 10));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

~~~bash
javac ReachableNegativeCycleDemo.java
java ReachableNegativeCycleDemo
~~~

**Kết quả stdout chuẩn:**

~~~text
Reachable: cycle=true, witness=[1, 2, 1], weight=-2
Reachable: dist=[0, -INF, -INF, -INF, -INF, 10]
Disconnected: cycle=false, witness=[], weight=none
Disconnected: dist=[0, 4, 2, 5, UNREACHABLE, UNREACHABLE]
Self-loop: cycle=true, witness=[1, 1], weight=-1
Self-loop: dist=[0, -INF, -INF]
Branch: cycle=true, witness=[1, 2, 1], weight=-2
Branch: dist=[0, -INF, -INF, 5, 6]
Negative edge: cycle=false, witness=[], weight=none
Negative edge: dist=[0, -5, -3]
~~~

### Giải thích các ca mẫu

**Reachable:** chu trình `1→2→1` âm tổng −2, tác động đến 1,2 và các hậu duệ 3,4; không tác động đến 0,5. Chu trình làm chứng được xoay để bắt đầu ở đỉnh nhỏ nhất.

**Disconnected:** chu trình âm `4→5→4` không đạt từ 0, nên trả false. Khoảng cách tới 2 là min(5,4−2)=2; tới 3 là 2+3=5; 4,5 không đạt.

**Self-loop:** từ 0 có cạnh 0→1 (+2), đỉnh 1 có cạnh tự quay 1→1 (−1). Đỉnh 1 và hậu duệ 2 đều có −∞. Chu trình làm chứng `[1,1]` có tổng −1.

**Branch:** một chu trình âm đạt được từ s chỉ làm 1,2 thành −∞; 3,4 ở nhánh khác nên có khoảng cách hữu hạn 5,6.

**Negative edge:** có trọng số âm nhưng không có chu trình, khoảng cách hữu hạn là `[0,-5,-3]`.

### Vì sao cần lưu predecessorWeight?

Trong một đa đồ thị, có thể có nhiều cạnh u→v với trọng số khác nhau. `predecessor[v]=u` không lưu cạnh nào đã cải thiện dist[v]; việc lấy ngẫu nhiên một cạnh cùng hai endpoint có thể làm sai trọng số chứng cứ. Mã lưu `predecessorWeight[v]` của **đúng lần cập nhật**, rồi tính tổng trọng số chu trình từ những cạnh đã được chọn.

### Tại sao làm hai việc từ dữ liệu lượt n?

`lastUpdated` đủ để trỏ về **một** chu trình âm sau n bước predecessor. `changedOnNth` gồm **mọi** đỉnh còn giảm; BFS từ tập này xác định **tất cả** các đỉnh −∞, kể cả khi có nhiều chu trình âm đạt được từ nguồn nhưng tách biệt nhau.

## 12. Chứng minh đúng của phần phân loại

Ta cần chứng minh thuật toán đánh dấu đúng hai lớp đặc biệt, sau đó các giá trị số còn lại là hữu hạn chính xác.

**UNREACHABLE:** ban đầu chỉ s có dist. Mỗi lần gán dist[v] mới xuất phát từ một u đã có dist và một cạnh u→v thật, nên chỉ có thể đánh dấu v nếu tồn tại walk từ s tới v. Ngược lại, một đường đơn từ s tới v có không quá n−1 cạnh; Bellman–Ford qua n−1 lượt sẽ truyền reachability tới v. Vì vậy dist[v]==null đúng khi v không đạt được.

**-INF, chiều đủ:** nếu v nằm trên hoặc phía sau chu trình âm C đạt từ s, có thể lặp C tùy ý rồi tới v. Giá trị thấp nhất không bị chặn dưới. Lượt n bắt buộc có cải thiện liên quan tới C, và BFS từ các hạt giống cập nhật theo cạnh gốc sẽ lan tới v.

**-INF, chiều cần:** một hạt giống cập nhật ở lượt n chỉ có thể xuất hiện do tác động của chu trình âm đạt từ nguồn, bởi nếu không có chu trình âm trên vùng walk tới đỉnh thì đường đơn đã đạt optimum sau n−1 lượt. Theo các cạnh từ hạt giống, ảnh hưởng âm tiếp tục truyền tới mọi hậu duệ. Vì vậy không có đỉnh nào được đánh dấu −INF một cách không có căn cứ.

**Khoảng cách hữu hạn:** nếu dist[v] đã có và affected[v] false, không chu trình âm nào đạt từ s có đường tới v; do đó có một đường đi đơn tối ưu. Bellman–Ford sau n−1 lượt đã tìm được giá trị ấy. Lượt n không thể làm thay đổi giá trị của v ở vùng không ảnh hưởng, nên dist[v] cuối là khoảng cách hữu hạn đúng.

Ba trạng thái **loại trừ lẫn nhau** và bao phủ mọi đỉnh.

## 13. Độ phức tạp

Đặt `V=n` và `E=m`.

| Pha | Thời gian theo phép toán số học | Bộ nhớ |
|---|---|---|
| Kiểm tra cạnh, dựng danh sách kề | O(V+E) | O(V+E) |
| Tối đa V−1 lượt relaxation | O(VE) | O(V) ngoài danh sách cạnh |
| Lượt V tìm hạt giống | O(E) | O(V) |
| BFS lan truyền -INF | O(V+E) | O(V) |
| Phục dựng một chu trình | O(V) | O(V) |
| Trình bày V trạng thái | O(V) ô kết quả | O(V) |

Tổng thời gian **`O(VE+V+E)`**, thường được viết **`O(VE)`** khi V,E dương và không bị triệt tiêu. Bộ nhớ **`O(V+E)`** bao gồm danh sách cạnh và adjacency list, các mảng, BFS và chu trình làm chứng.

Với E=0, vẫn phải khởi tạo các mảng O(V); vì vậy biểu thức đầy đủ `O(VE+V+E)` phản ánh cả đồ thị không cạnh. Với n=1 và một self-loop âm, thuật toán vẫn phát hiện bằng đúng lượt n=1.

**BigInteger:** số phép cộng và so sánh là O(VE), nhưng mỗi phép BigInteger tốn thời gian phụ thuộc số bit của số đang xử lý. Nếu trọng số và tổng đã được chứng minh vừa kiểu long thì dùng long có thể nhanh hơn; không được đánh đổi tính chính xác để lấy tốc độ.

## 14. Kiểm thử độc lập bằng Floyd–Warshall

Để kiểm tra một thuật toán Bellman–Ford, không nên chỉ viết một phiên bản Bellman–Ford thứ hai có cùng logic rồi thấy output giống nhau. Trên đồ thị nhỏ, dùng một phép kiểm tra **khác về cấu trúc**: Floyd–Warshall và quan hệ khả đạt.

### 14.1. Ma trận reachability

Dựng `reach[u][v]` bằng DFS/BFS từ từng u hoặc boolean Floyd–Warshall. Khởi tạo đường chéo true (đường độ dài 0), đánh dấu các cạnh trực tiếp, rồi đóng bắc cầu:

~~~text
for k in vertices:
    for i in vertices:
        for j in vertices:
            reach[i][j] |= reach[i][k] && reach[k][j]
~~~

### 14.2. Ma trận trọng số thấp nhất

Khởi tạo `fw[i][i]=0`, `fw[u][v]` bằng cạnh nhỏ nhất từ u tới v, những cặp khác chưa có đường là không đạt. Cập nhật:

`fw[i][j]=min(fw[i][j],fw[i][k]+fw[k][j])`

khi cả hai đoạn có thể đi được. Với số học chính xác, `fw[k][k]<0` cho biết một chu trình âm có thể đạt từ k và trở về k.

Một đỉnh v có `d(s,v)=−∞` khi và chỉ khi tồn tại k:

**`reach[s][k] && fw[k][k]<0 && reach[k][v]`.**

Nếu `reach[s][v]` false thì kết quả là `UNREACHABLE`. Nếu reach true nhưng không có k thoả điều kiện âm, giá trị `fw[s][v]` là khoảng cách hữu hạn cần so với Bellman–Ford.

Floyd–Warshall tốn **O(V³)** thời gian và **O(V²)** RAM, thích hợp làm oracle cho V nhỏ chứ không thay thế giải pháp một nguồn trên đồ thị thưa lớn.

### 14.3. Kiểm tra nhân chứng

Nếu có một chu trình âm được xuất:

1. Danh sách `cycle` phải có đỉnh đầu trùng đỉnh cuối.
2. Mỗi cặp kế tiếp phải là cạnh **có hướng** hợp lệ của graph.
3. Nếu có đa cạnh, tổng phải dùng đúng cạnh predecessor hoặc ID/trọng số lưu cho nhân chứng.
4. Tổng trọng số chu trình phải **<0**.
5. Nguồn s phải có đường tới ít nhất một đỉnh của chu trình.
6. Mọi đỉnh đạt được từ chu trình phải có nhãn -INF.

Nếu không có chu trình âm đạt được thì chu trình làm chứng phải rỗng và không xuất hiện nhãn -INF.

### 14.4. Ca biên và sinh dữ liệu ngẫu nhiên

| Tình huống | Mong đợi |
|---|---|
| Một đỉnh không cạnh | [0], không có chu trình |
| Một đỉnh self-loop âm | Chu trình [0,0], khoảng cách [-INF] |
| Self-loop dương hoặc 0 | Không phải chu trình âm |
| Chu trình tổng đúng 0 | Không phát hiện chu trình âm |
| Một cạnh âm không chu trình | Khoảng cách âm hữu hạn có thể hợp lệ |
| Chu trình âm nằm ở vùng không đạt | Không được phát hiện từ nguồn |
| Chu trình âm đạt nguồn nhưng không tới đích | Đích vẫn có thể có số hữu hạn |
| Hai chu trình âm đạt nguồn ở hai nhánh | Đánh dấu -INF ở cả hai vùng ảnh hưởng |
| Có cạnh song song khác trọng số | Relax từng cạnh, lưu đúng trọng số khi phục dựng |
| Đỉnh cô lập | UNREACHABLE nếu không phải nguồn |
| Nhiều thứ tự liệt kê cạnh | Các nhãn trạng thái không đổi |
| Trọng số rất lớn trong long | BigInteger bảo toàn tổng chính xác |
| Source ngoài miền hoặc n≤0 | API từ chối đầu vào |
| Cạnh có endpoint ngoài miền | API từ chối đầu vào |

Với thử ngẫu nhiên, chọn n từ 1 đến 8, sinh cạnh hướng (u,v) với trọng số −9..9, bao gồm self-loop, đa cạnh và đỉnh cô lập. Chọn nguồn s ngẫu nhiên. Đối chiếu **từng trạng thái** của Bellman–Ford với oracle Floyd–Warshall, không chỉ boolean phát hiện chu trình. Thử thêm thứ tự cạnh khác vì cập nhật in-place có thể theo những bước trung gian khác nhau nhưng kết quả cuối về ba trạng thái phải giống nhau.

## 15. So với các thuật toán liên quan

**Bellman–Ford:** dùng được khi có cạnh âm, trả khoảng cách hữu hạn nếu không chịu ảnh hưởng chu trình âm, phát hiện chu trình âm đạt được ở lượt V. Cận O(VE), phù hợp với bài toán một nguồn và yêu cầu chứng minh rõ ràng.

**Dijkstra:** dùng được với trọng số **không âm** theo giả thiết chuẩn. Nếu có cạnh âm, thao tác chốt đỉnh của Dijkstra cổ điển có thể sai; không dùng nó thay cho phép kiểm tra chu trình âm.

**SPFA:** biến thể tối ưu trên hàng đợi của relaxation. Có các cách phát hiện chu trình âm bằng độ dài đường predecessor hoặc số cập nhật đã được chứng minh, nhưng cần cài và chứng minh cẩn thận; SPFA **có thời gian xấu nhất rất lớn**, không bảo đảm luôn nhanh hơn Bellman–Ford.

**Floyd–Warshall:** phù hợp với mọi cặp trên đồ thị nhỏ; có thể phát hiện các đỉnh k với `dist[k][k]<0`. Nhưng O(V³) thời gian, O(V²) bộ nhớ, và muốn phân loại −∞ theo s,t phải xét cả khả đạt s→k và k→t.

**Johnson:** tính đường đi ngắn nhất mọi cặp trên đồ thị phù hợp bằng cách chạy Bellman–Ford từ siêu nguồn để kiểm tra chu trình âm rồi đổi trọng số sang không âm trước khi dùng Dijkstra. Nó giải bài toán mọi cặp, còn bài học này tập trung vào chu trình âm **đạt được từ một nguồn s cụ thể**.

### Không nhầm phát hiện toàn đồ thị với phát hiện theo nguồn

Nếu thêm siêu nguồn nối tới tất cả đỉnh hoặc khởi tạo mọi dist=0, ta có thể phát hiện chu trình âm ở **bất kỳ đâu**. Đó là bài toán hợp lệ khác, nhưng không được dùng nó để trả lời câu hỏi “nguồn s có đi tới chu trình âm không?”. Muốn chứng minh tính đúng theo s, giữ **chỉ dist[s]=0** lúc khởi tạo.

## 16. Những lỗi thường gặp

1. **Xem cạnh âm là chu trình âm.** Một cạnh âm có thể nằm trên đường đi hữu hạn hoàn toàn bình thường.
2. **Không kiểm tra reachable[u] trước khi relax.** Dẫn tới khoảng cách giả từ INF+w.
3. **Khởi tạo mọi dist=0 khi đề đã cho nguồn.** Phát hiện nhầm chu trình ở thành phần không đạt.
4. **Kiểm tra sự thay đổi khi chưa đủ V−1 lượt.** Các cập nhật ban đầu chưa chứng minh chu trình âm.
5. **Quên lượt V với V=1.** Bỏ sót self-loop âm.
6. **Dùng candidate<=dist[v] thay vì candidate<dist[v].** Chu trình tổng 0 có thể gây dương tính giả.
7. **Quên hướng cạnh, xử lý như vô hướng.** Tạo đường hoặc chu trình giả.
8. **Dùng long không kiểm tra tràn.** Sai so sánh có thể làm cắt hoặc phát hiện nhầm.
9. **Coi dist sau lượt V ở vùng ảnh hưởng là shortest path hữu hạn.** Không có cực tiểu hữu hạn tại đó.
10. **Đi ngược predecessor cho tới nguồn một cách vô hạn.** Có thể bị kẹt trong chu trình âm.
11. **Không đi V lần predecessor trước khi thu vòng.** Đỉnh cập nhật cuối có thể nằm phía sau chu trình.
12. **Quên đảo chu trình predecessor để in đúng hướng.** Chuỗi in có thể không đi theo các cạnh gốc.
13. **Không lưu ID/trọng số cạnh predecessor khi có đa cạnh.** Tổng chu trình có thể bị tính sai.
14. **BFS chỉ từ một nhân chứng khi cần toàn bộ vùng -INF.** Bỏ sót các chu trình âm độc lập khác.
15. **BFS theo cạnh đảo để truyền ảnh hưởng.** -INF chỉ lan theo cạnh gốc từ chu trình tới hậu duệ.
16. **Đánh dấu mọi đỉnh nguồn đạt tới là -INF.** Nhánh không đạt từ chu trình vẫn hữu hạn.
17. **Nhầm nguồn đạt chu trình với chu trình đạt nguồn.** Hai chiều không tương đương.
18. **Không xử lý đỉnh cô lập hoặc thành phần không đạt.** Trả số 0 giả thay cho UNREACHABLE.
19. **Dùng một boolean cycle để trả lời mọi câu hỏi tới đích.** Phải biết chu trình âm có đường tới đích không.
20. **Tuyên bố tìm mọi chu trình âm khi chỉ xuất một witness.** Một nhân chứng là đủ cho kiểm tra tồn tại, không phải danh sách đầy đủ.

## 17. Checklist trước khi nộp

- [ ] Đồ thị có hướng, cạnh được lưu đúng chiều u→v, n và source hợp lệ.
- [ ] Chỉ nguồn có dist=0; đỉnh khác mang trạng thái **chưa đạt**, không dùng INF như số để cộng.
- [ ] Mỗi relax chỉ thực hiện khi u đã đạt, và dùng so sánh **giảm nghiêm ngặt**.
- [ ] Đã duyệt tối đa V−1 lượt đầy đủ, dừng sớm chỉ khi một lượt không cập nhật.
- [ ] Có lượt thứ V riêng để phát hiện còn cập nhật từ nguồn.
- [ ] Tổng trọng số không thể tràn kiểu số đang dùng.
- [ ] Nếu xuất chu trình, có đi ngược V predecessor, khép vòng, đảo về hướng cạnh gốc và kiểm tra tổng âm.
- [ ] Đa cạnh có lưu đúng ID hoặc trọng số cạnh predecessor.
- [ ] Nếu cần tất cả đỉnh -INF, có BFS từ **mọi đỉnh được cập nhật ở lượt V** theo cạnh gốc.
- [ ] Không nhầm UNREACHABLE, số hữu hạn và -INF.
- [ ] Đã thử chu trình âm tách biệt, chu trình tổng 0, self-loop âm, cạnh âm không chu trình và nhiều chu trình âm.
- [ ] Đã kiểm tra với oracle độc lập trên đồ thị nhỏ và thay đổi thứ tự cạnh.

**Kết luận:** phát hiện chu trình âm **có thể đạt từ nguồn s** phải bắt đầu bằng **reachability đúng**. Bellman–Ford thực hiện tối đa V−1 lượt relaxation, rồi dùng **lượt V** để chứng minh có chu trình âm đạt từ nguồn nếu vẫn còn cải thiện. Truy theo predecessor cho **một chu trình làm chứng**; lan truyền theo hướng cạnh từ **mọi đỉnh được cập nhật ở lượt V** để tìm toàn bộ vùng có khoảng cách **−∞**. Một chu trình âm không đạt từ s không liên quan đến khoảng cách của s; một nhánh đạt từ s nhưng không nhận được đường từ chu trình âm vẫn có khoảng cách hữu hạn.