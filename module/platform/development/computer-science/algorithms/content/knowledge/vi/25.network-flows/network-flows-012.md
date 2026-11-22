# Luồng chi phí nhỏ nhất với các đường tăng

**Luồng chi phí nhỏ nhất với các đường tăng** (*minimum-cost flow by successive shortest augmenting paths*) tìm cách gửi một lượng hàng/đơn vị luồng qua **mạng có hướng**, vừa tuân thủ **giới hạn sức chứa**, **bảo toàn luồng**, vừa làm **tổng chi phí thấp nhất**. Một cách giải nền tảng là liên tục tìm **đường đi s→t có tổng chi phí nhỏ nhất trong mạng dư**, tăng luồng theo nút thắt và cập nhật cả cạnh thuận lẫn cạnh ngược.

Khác với bài **maximum flow** chỉ muốn gửi *được nhiều nhất*, bài **min-cost flow** phân biệt **số đơn vị gửi được** và **chi phí phải trả**. Ta có thể hỏi:
- **Gửi đúng F đơn vị nếu có thể:** trong các luồng có giá trị F, chọn luồng chi phí nhỏ nhất.
- **Min-cost max-flow:** trước tiên đạt *giá trị luồng lớn nhất* từ s tới t, rồi trong các nghiệm đạt giá trị đó, chọn chi phí nhỏ nhất.
- **Gửi tối đa F đơn vị với ưu tiên lượng gửi trước chi phí:** nếu F không đạt được, gửi nhiều nhất có thể nhưng không quá F; tối thiểu chi phí tại **giá trị luồng thực tế đó**. Đây là quy ước mà chương trình Java của bài thực hiện.

Bài thuộc nhóm **Luồng mạng** trong Computer Science Algorithms. Nội dung đi từ định nghĩa, ràng buộc, cạnh dư chi phí âm và khả năng hủy luồng, đến thuật toán đường tăng chi phí nhỏ nhất bằng **Bellman–Ford**, tối ưu hóa bằng **potential + Dijkstra**, điều kiện đúng về **chu trình chi phí âm**, ví dụ tính tay, chương trình **Java 17** chạy độc lập, kiểm thử vét cạn và bài tập.

## 1. Mô hình: sức chứa khác chi phí

Một mạng gồm các đỉnh `V`, các cạnh **có hướng** `E`, **nguồn s** và **đích t** phân biệt. Mỗi cạnh thật e=(u,v) có ba đại lượng riêng:

| Ký hiệu | Ý nghĩa | Điều kiện |
| --- | --- | --- |
| `U(e)` | **Sức chứa** (*capacity*): tối đa bao nhiêu đơn vị có thể gửi qua e | `U(e)\ge0` |
| `a(e)` | **Chi phí một đơn vị luồng** (*unit cost*) trên e | Có thể âm, 0 hoặc dương |
| `x(e)` | **Lượng luồng thật** đang gửi trên e | `0\le x(e)\le U(e)` |

Chi phí của một cấu hình luồng là:

\[
\boxed{Cost(x)=\sum_{e\in E}x(e)\,a(e).}
\]

Đừng nhầm **chi phí** với **sức chứa**. Ví dụ cạnh `1→2` capacity 7, cost −3 nghĩa là có thể gửi từ 0 đến 7 đơn vị; *mỗi đơn vị* làm tổng chi phí giảm 3. Nó **không** có sức chứa âm và không cho phép gửi luồng thật âm.

Đây là mô hình **chi phí tuyến tính theo đơn vị luồng**: gửi k đơn vị trên cùng cạnh tốn k×cost. Nếu có **chi phí mở tuyến cố định** hoặc chi phí thay đổi phi tuyến theo số lượng, cần mô hình khác; không thể tự dùng cùng công thức rồi kỳ vọng chính xác.

### Điều kiện khả thi

**Capacity constraint** cho mỗi cạnh thật e:

\[
\boxed{0\le x(e)\le U(e).}
\]

**Flow conservation** ở mọi đỉnh trung gian v, tức `v\ne s,t`:

\[
\boxed{\sum_{e:\,to(e)=v}x(e)=
\sum_{e:\,from(e)=v}x(e).}
\]

Một đỉnh trung gian không tự sinh hoặc làm mất luồng. Nguồn được phép có luồng ròng đi ra và đích được phép có luồng ròng đi vào.

**Giá trị luồng** là:

\[
|x|=\sum_{e:\,from(e)=s}x(e)-
\sum_{e:\,to(e)=s}x(e).
\]

Tương đương:

\[
|x|=\sum_{e:\,to(e)=t}x(e)-
\sum_{e:\,from(e)=t}x(e).
\]

Nếu nguồn có cạnh thật đi vào hoặc đích có cạnh thật đi ra, phải tính **giá trị ròng**, không được lấy riêng tổng đi ra ở s hay tổng đi vào ở t.

### Tối ưu hóa theo giá trị F

Với `F\ge0`, bài **minimum-cost flow of value F** là:

\[
\min_x\ \sum_{e\in E}x(e)a(e)
\]

với những ràng buộc:
- `0\le x(e)\le U(e)` cho mọi cạnh;
- bảo toàn tại mọi đỉnh ngoài s,t;
- `|x|=F`.

**Luồng 0 là luồng khả thi**, nhưng không phải luôn là **luồng rẻ nhất có giá trị 0** nếu mạng cho phép **chu trình chi phí âm**: gửi một lượng tuần hoàn quanh chu trình âm có thể giảm tổng chi phí mà không thay đổi `|x|`. Đây là lý do thuật toán đơn giản bắt đầu từ 0 cần nêu rõ giả thiết về chu trình âm.

## 2. Vì sao không dùng đường có ít cạnh nhất hoặc đường chỉ xét cạnh thật?

Đường tăng **rẻ nhất** là đường có tổng **chi phí cạnh dư** nhỏ nhất, không phải đường có ít cạnh nhất.

Ví dụ:
- Đường s→a→t gồm hai cạnh, tổng chi phí 9.
- Đường s→b→c→t gồm ba cạnh, tổng chi phí 4.

Nếu cả hai còn capacity, để gửi một đơn vị rẻ nhất phải chọn đường ba cạnh chi phí 4. **BFS** theo số cạnh không giải min-cost flow khi chi phí khác nhau.

Cũng không thể cứ tìm đường rẻ nhất trên **các cạnh thật còn trống**. Sau một lần gửi, ta có thể cần **hủy một quyết định cũ** và chuyển một phần luồng sang đường khác để giảm tổng chi phí. Việc đó đòi hỏi **mạng dư có cạnh ngược chi phí đối dấu**.

### Dijkstra có dùng trực tiếp được không?

Không nói chung. Dù **chi phí cạnh thật ban đầu không âm**, mỗi cạnh đã mang luồng tạo một cạnh dư ngược có **chi phí âm**. Dijkstra thông thường đòi **trọng số không âm**, nên có thể trả sai nếu chạy trực tiếp trên mạng dư có cạnh âm.

Hai lựa chọn chuẩn:
1. Dùng **Bellman–Ford** trên mạng dư cho từng đường tăng; đơn giản, chấp nhận cạnh âm, nhưng chậm hơn.
2. Dùng **Johnson potentials** để đổi **chi phí giảm** (*reduced costs*) thành không âm rồi chạy Dijkstra; nhanh hơn trên mạng lớn khi bảo đảm bất biến potentials.

Chương trình đầy đủ trong bài chọn **Bellman–Ford**, kèm bước kiểm tra chu trình chi phí âm, để người học dễ đối chiếu từng phép tính.

## 3. Mạng dư và cạnh ngược có chi phí âm

Với một **cạnh thật** e=u→v, capacity U, unit cost a, flow hiện tại x, cặp cạnh dư là:

**Cạnh dư thuận u→v:**
- `residual=U-x`;
- `cost=+a`;
- thể hiện có thể gửi thêm trên cạnh thật.

**Cạnh dư ngược v→u:**
- `residual=x`;
- `cost=-a`;
- thể hiện có thể **hủy bớt** luồng đã gửi trên cạnh thật u→v.

Nếu tăng `\Delta` qua cạnh dư thuận, x tăng \Delta và chi phí thật tăng `\Delta a`. Nếu tăng `\Delta` qua cạnh dư ngược, x giảm \Delta và chi phí thật giảm `\Delta a`, tương đương cộng `\Delta(-a)`. Vì vậy **cạnh dư ngược có unit cost âm của cạnh gốc**, bất kể chi phí gốc dương hay âm.

Với mỗi cặp residual gắn với một cạnh thật:

\[
res_f+res_r=U,\quad
x=U-res_f=res_r.
\]

Phép cập nhật khi đi qua bất kỳ cạnh dư z với bottleneck \Delta:

~~~text
z.residual         -= delta
z.reverse.residual += delta
~~~

Cập nhật này đúng cho cả z thuận và z ngược. Nếu z là cạnh dư ngược, nó tự động rút bớt luồng thật trên cạnh gốc.

### Tại sao nên lưu đối tượng cạnh thay vì chỉ hai đỉnh?

Nếu có **hai cạnh song song** u→v mang capacity và cost khác nhau, chúng có hai cặp dư riêng. Nếu có cả cạnh thật v→u, cặp dư của cạnh thật ấy **không phải** cặp dư của u→v.

Cài đặt an toàn tạo **hai đối tượng Edge** được nối với nhau qua trường `reverse` cho **mỗi cạnh thật**, rồi lưu đúng **parent edge** khi tìm đường. Chỉ lưu `parentVertex[v]=u` sẽ không đủ để biết đã chọn cạnh nào trong mạng đa cạnh.

### Self-loop và capacity 0

Cạnh `u→u` có thể có capacity và cost; nếu là **chu trình chi phí âm** với capacity dương, nó làm hỏng giả thiết không có chu trình âm của thuật toán đường tăng đơn giản. Cạnh self-loop có unit cost không âm không giúp tăng giá trị s–t; một đường s→t đơn không cần đi qua self-loop.

Cạnh capacity 0 **không có cạnh dư thuận dương** và không vận chuyển được gì, dù unit cost âm.

## 4. Đường tăng rẻ nhất: phép tính một lượt

Giả sử mạng dư hiện tại có một đường `P:s\leadsto t` và tất cả các cạnh trên đó đều có residual dương.

**Chi phí một đơn vị của đường:**

\[
unitCost(P)=\sum_{z\in P}cost(z).
\]

**Nút thắt (bottleneck):**

\[
bottleneck(P)=\min_{z\in P}residual(z).
\]

Nếu còn cần gửi `remaining=F-sent` đơn vị, chỉ tăng:

\[
\boxed{\Delta=\min(bottleneck(P),remaining).}
\]

**Chi phí tăng thêm:**

\[
\boxed{\Delta Cost=\Delta\cdot unitCost(P).}
\]

Đơn vị chi phí đường **có thể âm**, vì mạng dư có cạnh âm hoặc cạnh thật có chi phí âm. Tổng chi phí của luồng theo các lần tăng có thể tăng hoặc giảm; không được áp đặt điều kiện `totalCost\ge0`.

### Hai loại giá trị cần theo dõi riêng

- `sent` tăng thêm đúng \Delta đơn vị ở mỗi đường s–t.
- `totalCost` tăng thêm đúng `\Delta\cdot unitCost(P)`.

Tăng được 3 đơn vị không nói gì trực tiếp về chi phí nếu chưa biết unit cost của đường. Tương tự, một đường unit cost âm **không đồng nghĩa gửi thêm lượng vô hạn**, vì residual/capacity vẫn có giới hạn.

## 5. Ví dụ phải dùng cạnh ngược chi phí −4

Xét mạng 6 đỉnh, nguồn 0, đích 5, mọi capacity đều bằng 1:

| Cạnh thật | Capacity | Chi phí/đơn vị |
| --- | ---: | ---: |
| 0→1 | 1 | 0 |
| 0→2 | 1 | 0 |
| 1→3 | 1 | 4 |
| 1→4 | 1 | 5 |
| 2→3 | 1 | 6 |
| 3→5 | 1 | 0 |
| 4→5 | 1 | 0 |

Mục tiêu: gửi **F=2** đơn vị với chi phí nhỏ nhất.

### Đường tăng thứ nhất

Đường rẻ nhất ban đầu là:

~~~text
0 → 1 → 3 → 5
chi phí đơn vị = 0 + 4 + 0 = 4
bottleneck = 1
~~~

Gửi một đơn vị. Kết quả:
- `sent=1`, `totalCost=4`.
- Cạnh thật 1→3 mang flow=1 nên cạnh dư ngược **3→1 có residual=1 và cost=−4**.
- Đường đi qua 1→4 chưa dùng, 2→3 chưa dùng.

### Đường tăng thứ hai trong mạng dư

Đường rẻ nhất tiếp theo là:

~~~text
0 → 2 → 3 → 1 → 4 → 5
            ^
      cạnh 3→1 là cạnh DƯ NGƯỢC của 1→3

cost = 0 + 6 + (-4) + 5 + 0 = 7
bottleneck = 1
~~~

Gửi một đơn vị theo đường dư này:
- f(0→2) tăng 0→1.
- f(2→3) tăng 0→1.
- f(1→3) **giảm 1→0** do đi qua cạnh dư 3→1.
- f(1→4) tăng 0→1.
- f(4→5) tăng 0→1.
- f(3→5) vẫn bằng 1.

Sau hai đường tăng:

\[
sent=1+1=2,\quad totalCost=4+7=\boxed{11}.
\]

### Luồng thật cuối và chi phí

| Cạnh thật | f/capacity | Đóng góp chi phí |
| --- | --- | ---: |
| 0→1 | 1/1 | 0 |
| 0→2 | 1/1 | 0 |
| 1→3 | **0/1** | **0** |
| 1→4 | 1/1 | 5 |
| 2→3 | 1/1 | 6 |
| 3→5 | 1/1 | 0 |
| 4→5 | 1/1 | 0 |
| **Tổng** | **sent=2** | **11** |

Một cách phân rã thành đường thật là:
- `0→1→4→5`, một đơn vị, chi phí 5.
- `0→2→3→5`, một đơn vị, chi phí 6.

Tổng là 11. **Đường tăng thứ hai không phải đường thật** vì có bước 3→1 dư ngược; nó chính là thao tác **chuyển luồng cũ**.

### Với các mức yêu cầu khác nhau

| Demand F | Thực gửi | Chi phí tối thiểu ứng với lượng thực gửi | Đạt yêu cầu? |
| ---: | ---: | ---: | --- |
| 1 | 1 | 4 | Có |
| 2 | 2 | 11 | Có |
| 3 | 2 | 11 | **Không** |

Lý do F=3 không đạt được: tổng sức chứa hai cạnh rời nguồn 0 là 1+1=2, nên giá trị luồng tối đa chỉ bằng 2. Chi phí 11 vẫn tối ưu trong các luồng gửi **đúng 2 đơn vị**, nhưng không thể gọi đây là nghiệm cho yêu cầu gửi đúng 3 đơn vị.

### Chứng chỉ về lượng và về chi phí khác nhau

Sau khi gửi 2:
- Luồng đạt giá trị tối đa 2, được chứng nhận bởi lát cắt nguồn `S=\{0\}` có capacity 2.
- Chi phí là nhỏ nhất **trong các luồng giá trị 2**, được chứng nhận bởi tính chất **không có chu trình chi phí âm trong mạng dư** của nghiệm.

**Max-flow min-cut chỉ chứng minh gửi được nhiều nhất**, không tự chứng minh phân phối đó có **chi phí nhỏ nhất**. Hai mục tiêu cần hai lập luận riêng.

## 6. Thuật toán Successive Shortest Augmenting Path (SSP)

**SSP** bắt đầu từ luồng 0, lặp:
1. Tìm đường chi phí nhỏ nhất từ s tới t trong mạng dư với cạnh residual dương.
2. Nếu không còn đường s→t, dừng: không gửi thêm được.
3. Lấy bottleneck trên đường; nếu có demand F, giới hạn thêm bởi `F-sent`.
4. Tăng luồng qua từng cạnh dư và cập nhật reverse.
5. Cộng \Delta vào sent, cộng \Delta×unitCost vào totalCost.
6. Lặp tới khi đạt F hoặc hết đường tăng.

~~~text
minCostUpTo(graph, s, t, F):
    residual = các cặp cạnh thuận/ngược từ input
    assert input capacity >= 0
    assert s != t
    assert residual ban đầu KHÔNG có chu trình chi phí âm

    sent = 0
    totalCost = 0

    while sent < F:
        P = shortestCostPath(residual, s, t)
        if P không tồn tại:
            break

        bottleneck = min residual(z) trên P
        delta = min(bottleneck, F - sent)

        for z in P:
            z.residual -= delta
            z.reverse.residual += delta

        sent += delta
        totalCost += delta * unitCost(P)

    return sent, totalCost, (sent == F)
~~~

**Giả thiết bắt buộc của bản SSP đơn giản trong bài:** mạng dư ban đầu **không có chu trình có tổng chi phí âm** ở bất kỳ thành phần nào còn capacity dương. Điều này tự đúng nếu mọi chi phí cạnh thật ban đầu **không âm**, nhưng bài vẫn cho phép **cạnh thật chi phí âm** miễn không tạo chu trình âm. Nếu có chu trình âm ban đầu, phải dùng thuật toán hỗ trợ **cycle canceling**, xây luồng khả thi và tối ưu hóa phù hợp, hoặc chuyển mô hình; không được âm thầm chạy SSP như thể giả thiết vẫn đúng.

### Vì sao kiểm tra chu trình âm toàn cục?

Ngay cả chu trình âm **không reachable từ s** cũng có thể chở một **luồng tuần hoàn** làm giảm chi phí trong khi giá trị s–t không đổi. Ví dụ có cạnh 0→3 cost5 để gửi một đơn vị, còn thành phần rời `1→2 cost−3`, `2→1 cost0`, mỗi cạnh capacity1. Một luồng giá trị1 có thể thêm tuần hoàn 1 đơn vị chi phí −3, tổng giảm từ 5 thành 2. Nếu chỉ tìm các đường s→t và bỏ thành phần rời, thuật toán sẽ không tối ưu theo mô hình luồng tổng quát.

Chương trình vì vậy dùng Bellman–Ford kiểu **siêu nguồn ảo** (gán dist ban đầu bằng 0 ở mọi đỉnh) để phát hiện chu trình âm trong **toàn bộ mạng dư**, không chỉ phần reachable từ s. Nếu phát hiện, chương trình **từ chối** đầu vào theo hợp đồng được công bố; không ghi một đáp án min-cost thiếu bảo đảm.

### Khi F không đạt được

Nếu demand F>giá trị max-flow:
- Thuật toán dừng khi không còn đường dư s→t.
- Trả số đơn vị **thực gửi** và chi phí nhỏ nhất cho **giá trị đó**.
- Trả `metDemand=false`, báo rằng yêu cầu gửi **đúng F** là bất khả thi.

Không được gọi chi phí của luồng gửi ít hơn F là chi phí cho một nghiệm đúng F. Nếu đề yêu cầu nhất thiết đủ F, phía gọi phải xử lý trạng thái không đạt được (ví dụ báo “infeasible”).

## 7. Bellman–Ford tìm đường dư rẻ nhất

Mạng dư sau một vài bước thường có cạnh **âm** do reverse cost=−cost. Bellman–Ford xử lý được trọng số âm khi **không có chu trình âm reachable từ nguồn**.

Trên mỗi lần tìm đường:
- Đặt `dist[s]=0`, các đỉnh còn lại unreachable.
- Lặp tối đa `V−1` lượt relax qua mọi cạnh dư `residual>0`.
- Với cạnh dư u→v chi phí a: nếu u reachable và `dist[u]+a` cải thiện dist[v], cập nhật.
- Nếu t unreachable sau khi relax, không còn đường tăng.
- Nếu tìm thấy t, `dist[t]` là **chi phí đơn vị tối thiểu** của một đường dư s→t.

Chi phí cạnh âm không làm Bellman–Ford sai **nếu không có chu trình âm**, nhưng dùng Dijkstra trực tiếp sẽ không được bảo đảm.

### Chi tiết cài đặt parent an toàn

Sau khi tính dist, chương trình **không bắt buộc tin vào chuỗi parent có thể bị ảnh hưởng bởi thứ tự relax**. Thay vào đó, BFS thêm một lượt qua những cạnh **tight**:

\[
dist[u]+cost(u,v)=dist[v],\quad residual(u,v)>0.
\]

Mỗi cạnh tight nằm trên một khả năng bảo toàn giá trị đường ngắn nhất. Vì đã biết t reachable và không có chu trình âm, tồn tại đường s→t gồm các cạnh tight. BFS trên đồ thị cạnh tight tìm một **đường đơn** và lưu **đối tượng cạnh đã chọn**, kể cả khi có chu trình chi phí 0 trong residual.

Tại sao không chỉ dựa vào `parentVertex`? Trong mạng có cạnh song song, cùng u,v có thể có cost khác nhau và cần cập nhật đúng **cặp cạnh residual** được dùng. `Edge[] parent` giữ được đối tượng cụ thể, trong khi BFS visited tránh vòng trong đường tăng.

### Kiểm tra không còn chu trình âm sau mỗi lần tăng

Thuật toán SSP đúng chuẩn duy trì tính tối ưu về chi phí cho lượng đã gửi, nên không tạo ra chu trình dư âm nếu khởi đầu không có. Chương trình minh họa thực hiện thêm **kiểm tra Bellman–Ford toàn cục** sau từng lần tăng, vừa làm rõ bất biến vừa giúp phát hiện lỗi cài đặt.

Việc kiểm tra này có cùng cấp chi phí `O(VE)` như một lần Bellman–Ford tìm đường, không đổi Big-O của bản hiện thực dùng Bellman–Ford.

## 8. Chứng minh tính đúng và giới hạn

### A. Mỗi lần tăng giữ luồng khả thi

Xét một cạnh thật u→v capacity U, flow x. Cặp residual được bảo toàn:

\[
res_f=U-x,\quad res_r=x.
\]

Khi tăng một lượng \Delta không vượt bottleneck:
- Nếu đường dùng cạnh dư thuận, x tăng \Delta nhưng không quá U.
- Nếu đường dùng cạnh dư ngược, x giảm \Delta nhưng không âm.

Do đó **0≤x≤U** giữ nguyên. Tại mỗi đỉnh trung gian trên đường dư đơn, một lượng \Delta đi vào và \Delta đi ra theo nghĩa luồng ròng; điều này bảo toàn tổng vào bằng tổng ra. Nguồn tăng luồng ròng đi ra \Delta, đích tăng luồng ròng đi vào \Delta.

### B. Chi phí tính qua đường dư khớp chi phí trên cạnh thật

Một bước qua cạnh dư thuận cost +a làm luồng thật x tăng \Delta, chi phí thật tăng \Delta a. Một bước qua cạnh dư ngược cost −a làm x giảm \Delta, chi phí thật thay đổi −\Delta a. Vậy cộng \Delta lần chi phí trên mọi cạnh dư của đường đúng bằng thay đổi của:

\[
Cost(x)=\sum_{e\in E}x(e)a(e).
\]

Điều này vẫn đúng nếu một đường tăng **hủy một cạnh** để chuyển luồng và vẫn giữ tổng giá trị tăng \Delta.

### C. Vì sao đường dư ngắn nhất tối ưu hóa chi phí ở giá trị mới?

Với một luồng khả thi x có giá trị cố định k, nếu mạng dư tồn tại **chu trình chi phí âm**, có thể đẩy một lượng dương quanh chu trình để **giảm chi phí** mà không đổi giá trị k. Ngược lại, nếu x không tối ưu, hiệu giữa x và một luồng cùng giá trị nhưng rẻ hơn có thể phân rã thành các chu trình trong mạng dư, phải chứa ít nhất một chu trình âm. Do đó:

\[
\boxed{x\text{ chi phí nhỏ nhất ở giá trị }k
\iff \text{residual của }x\text{ không có chu trình chi phí âm}.}
\]

Bắt đầu từ luồng 0 và giả thiết không có chu trình âm toàn cục, điều kiện được thỏa. Khi tăng trên **đường dư chi phí nhỏ nhất** từ s tới t, ta duy trì điều kiện không có chu trình âm (lập luận dùng chi phí giảm/reduced costs và tính tight của đường tăng); vì thế luồng mới có chi phí tối ưu ứng với **giá trị mới**.

Đây là cơ sở của SSP. Nếu từ đầu có chu trình dư âm, thuật toán chỉ tìm đường s→t mà không xử lý tuần hoàn có thể mất tính tối ưu, nên code **từ chối trường hợp đó**.

### D. Vì sao đạt max-flow khi không còn đường s→t?

Việc không tìm thấy đường tăng trong residual là điều kiện dừng của thuật toán tăng luồng; theo định lý **max-flow min-cut**, luồng khi ấy đạt **giá trị cực đại**. SSP còn duy trì tối ưu chi phí ở mỗi giá trị đạt được, nên kết quả là **min-cost max-flow** nếu tiếp tục tăng tới khi không còn đường s→t.

Nếu dừng sớm vì đã đạt demand F, kết quả **min-cost ở giá trị F**, nhưng không nhất thiết là max-flow toàn mạng.

### E. Tính nguyên

Với capacity nguyên, residual khởi tạo nguyên; bottleneck và demand nguyên nên mọi \Delta nguyên. Do đó flow trên mọi cạnh duy trì nguyên. Đây là ưu điểm thực dụng cho bài số lượng hàng/người/công việc nguyên; thuật toán không cần dùng số thực và tránh được sai số so sánh nhỏ.

## 9. Cập nhật nhanh hơn với Johnson potentials và Dijkstra

Bellman–Ford mỗi lần O(VE). Với mạng lớn, một kỹ thuật chuẩn là gán **thế đỉnh** `\pi[v]` để thay chi phí a(u,v) bằng **chi phí giảm**:

\[
\boxed{a_\pi(u,v)=a(u,v)+\pi[u]-\pi[v].}
\]

Nếu potentials hợp lệ trên những cạnh residual có thể được duyệt từ s, ta có `a_\pi(u,v)\ge0`. Khi đó có thể dùng **Dijkstra** tìm đường có **tổng reduced cost nhỏ nhất**.

### Vì sao đổi chi phí mà không đổi đường tối ưu?

Với đường P từ s tới t:

\[
\sum_{(u,v)\in P}a_\pi(u,v)
=\sum_{(u,v)\in P}a(u,v)+\pi[s]-\pi[t].
\]

Hai đỉnh s,t cố định nên `\pi[s]-\pi[t]` là cùng một hằng số cho mọi đường. Vì vậy đường rẻ nhất theo reduced cost **cũng là** đường rẻ nhất theo chi phí gốc.

### Quy trình tối ưu thường dùng

1. **Khởi tạo potentials** bằng Bellman–Ford khi mạng ban đầu có chi phí âm (hoặc một phương pháp xác minh phù hợp). Với tiền xử lý từ siêu nguồn ảo và không có chu trình âm, có thể chọn potentials để những cạnh residual dương ban đầu có reduced cost không âm.
2. Chạy Dijkstra trên mạng dư với reduced costs.
3. Với mỗi đỉnh reachable trong lần Dijkstra, cập nhật `\pi[v]\gets\pi[v]+distReduced[v]`.
4. Tăng luồng trên đường được chọn, cập nhật cặp residual; cạnh dư ngược mới có reduced cost bằng 0 trên những cạnh đường tight.
5. Lặp đến khi đạt demand hoặc hết đường tăng.

Điểm dễ sai là **cập nhật potentials cho đỉnh unreachable** hoặc tính lại giá đường từ reduced cost sai. Cần xử lý cẩn thận những đỉnh unreachable; nhiều hiện thực chỉ cộng distReduced cho các đỉnh reachable. Các cạnh từ vùng unreachable tới reachable có thể không duy trì reduced cost không âm **toàn cục**, nhưng Dijkstra từ s không duyệt được chúng cho tới khi phạm vi reachable thay đổi theo quy trình. Đừng dùng một phép biến đổi potentials chưa được chứng minh đúng.

Nếu dùng heap nhị phân và cập nhật đúng potentials, mỗi lần tìm đường thường có chi phí `O(E\log V)` (cộng các hạng phụ O(V)), sau bước khởi tạo thích hợp. Với K lần tăng, chi phí có thể diễn đạt là **O(VE+K(E+V)\log V)** trong một hiện thực thông dụng, thay vì O(KVE) của Bellman–Ford từng vòng.

**Chương trình bên dưới không cài potentials**, để tránh trộn hai chứng minh/cấu trúc trong cùng ví dụ. Muốn tối ưu hiệu năng, trước tiên phải giữ được tất cả bất biến về residual và đường tăng, sau đó mới chuyển shortest-path engine sang potentials + Dijkstra.

## 10. Java 17: chương trình độc lập

Chương trình minh họa có đặc điểm:
- Mỗi cạnh thật là một đối tượng `Edge` có capacity, cost, residual; có một cạnh ngược liên kết `reverse` với **cost đối dấu**. Có thể có cạnh song song, hai cạnh thật ngược chiều, self-loop và capacity 0.
- `checkNoNegativeCycle` chạy Bellman–Ford với khoảng cách bắt đầu bằng 0 ở **mọi đỉnh** (tương đương siêu nguồn nối tới mọi đỉnh bằng cạnh cost0). Chỉ xét cạnh dư có residual dương.
- `shortestPath` dùng Bellman–Ford tìm cost nhỏ nhất từ s đến mọi đỉnh reachable, sau đó BFS trên **cạnh tight** để dựng đường tăng đơn và lưu `parent Edge[]`.
- `minCostUpTo` chỉ chạy **một lần trên Network mới**; trả `flow` thực gửi, `cost`, `metDemand` và `maximal`.
- `validSolution` kiểm tra capacity, bảo toàn, giá trị luồng, cost tính từ **cạnh thật**, và capacity min-cut nếu đạt max-flow.
- Bộ kiểm thử `verifySmallNetworks` dùng oracle vét cạn **mọi lượng luồng cạnh** trong mạng nhỏ, kiểm tra nhiều mức demand.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.StringJoiner;

public class MinCostAugmentingPathsDemo {
    static final class Edge {
        final int from;
        final int to;
        final long capacity;
        final long unitCost;
        final boolean original;
        long residual;
        Edge reverse;

        Edge(int from, int to, long capacity,
                long unitCost, long residual, boolean original) {
            this.from = from;
            this.to = to;
            this.capacity = capacity;
            this.unitCost = unitCost;
            this.residual = residual;
            this.original = original;
        }
    }

    record Shortest(Edge[] parent, long unitCost) {}

    record Result(
            long requested, long flow, long cost,
            boolean metDemand, boolean maximal,
            boolean[] sourceSide, List<String> steps) {}

    static final class Network {
        final int n;
        final List<List<Edge>> adj;
        final List<Edge> original = new ArrayList<>();
        boolean used;

        Network(int n) {
            if (n <= 0) {
                throw new IllegalArgumentException(
                        "Network needs vertices");
            }
            this.n = n;
            this.adj = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                adj.add(new ArrayList<>());
            }
        }

        void addArc(int u, int v, long capacity, long cost) {
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "Invalid endpoint");
            }
            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "Capacity must be nonnegative");
            }
            long reverseCost = Math.negateExact(cost);
            Edge forward = new Edge(
                    u, v, capacity, cost, capacity, true);
            Edge backward = new Edge(
                    v, u, 0, reverseCost, 0, false);
            forward.reverse = backward;
            backward.reverse = forward;
            adj.get(u).add(forward);
            adj.get(v).add(backward);
            original.add(forward);
        }

        // Bellman-Ford voi sieu nguon ao:
        // dist=0 tai MOI dinh, khong can them dinh ao.
        // Chi xet canh du residual>0.
        void checkNoNegativeCycle() {
            long[] dist = new long[n];
            for (int pass = 0; pass < n; pass++) {
                boolean changed = false;
                for (int u = 0; u < n; u++) {
                    for (Edge e : adj.get(u)) {
                        if (e.residual <= 0) continue;
                        long candidate = Math.addExact(
                                dist[u], e.unitCost);
                        if (candidate < dist[e.to]) {
                            dist[e.to] = candidate;
                            changed = true;
                            if (pass == n - 1) {
                                throw new IllegalArgumentException(
                                        "Negative-cost cycle");
                            }
                        }
                    }
                }
                if (!changed) break;
            }
        }

        Shortest shortestPath(int s, int t) {
            long[] dist = new long[n];
            boolean[] reachable = new boolean[n];
            reachable[s] = true;

            // Bellman-Ford: toi da n-1 luot.
            for (int pass = 1; pass < n; pass++) {
                boolean changed = false;
                for (int u = 0; u < n; u++) {
                    if (!reachable[u]) continue;
                    for (Edge e : adj.get(u)) {
                        if (e.residual <= 0) continue;
                        long candidate = Math.addExact(
                                dist[u], e.unitCost);
                        if (!reachable[e.to]
                                || candidate < dist[e.to]) {
                            reachable[e.to] = true;
                            dist[e.to] = candidate;
                            changed = true;
                        }
                    }
                }
                if (!changed) break;
            }
            if (!reachable[t]) return null;

            // Lay mot duong DON bang BFS tren canh tight.
            Edge[] parent = new Edge[n];
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[s] = true;
            queue.addLast(s);

            while (!queue.isEmpty() && !seen[t]) {
                int u = queue.removeFirst();
                for (Edge e : adj.get(u)) {
                    if (e.residual <= 0
                            || !reachable[e.to] || seen[e.to]) {
                        continue;
                    }
                    long candidate = Math.addExact(
                            dist[u], e.unitCost);
                    if (candidate != dist[e.to]) continue;

                    seen[e.to] = true;
                    parent[e.to] = e;
                    queue.addLast(e.to);
                    if (e.to == t) break;
                }
            }
            if (!seen[t]) {
                throw new IllegalStateException(
                        "No tight shortest path");
            }
            return new Shortest(parent, dist[t]);
        }

        boolean[] reachableResidual(int s) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[s] = true;
            queue.addLast(s);
            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Edge e : adj.get(u)) {
                    if (e.residual > 0 && !seen[e.to]) {
                        seen[e.to] = true;
                        queue.addLast(e.to);
                    }
                }
            }
            return seen;
        }

        static String showPath(List<Integer> path) {
            StringJoiner out = new StringJoiner("->");
            for (int v : path) out.add(Integer.toString(v));
            return out.toString();
        }

        Result minCostUpTo(int s, int t, long requested) {
            if (s < 0 || s >= n || t < 0 || t >= n
                    || s == t) {
                throw new IllegalArgumentException(
                        "Invalid source/sink");
            }
            if (requested < 0) {
                throw new IllegalArgumentException(
                        "Requested flow must be nonnegative");
            }
            if (used) {
                throw new IllegalStateException(
                        "Network already solved");
            }
            used = true;
            checkNoNegativeCycle();

            long sent = 0, totalCost = 0;
            List<String> steps = new ArrayList<>();

            while (sent < requested) {
                Shortest sp = shortestPath(s, t);
                if (sp == null) break;

                long delta = Math.subtractExact(requested, sent);
                List<Integer> pathReverse = new ArrayList<>();
                List<String> reverseSteps = new ArrayList<>();
                pathReverse.add(t);

                for (int v = t; v != s; ) {
                    Edge e = sp.parent()[v];
                    delta = Math.min(delta, e.residual);
                    if (!e.original) {
                        reverseSteps.add(e.from + "->" + e.to);
                    }
                    v = e.from;
                    pathReverse.add(v);
                }
                java.util.Collections.reverse(pathReverse);
                java.util.Collections.reverse(reverseSteps);

                // Tinh chi phi TRUOC khi mutate residual,
                // phat hien overflow cua candidate.
                long newCost = Math.addExact(
                        totalCost,
                        Math.multiplyExact(delta, sp.unitCost()));
                long newSent = Math.addExact(sent, delta);

                for (int v = t; v != s; ) {
                    Edge e = sp.parent()[v];
                    e.residual =
                            Math.subtractExact(e.residual, delta);
                    e.reverse.residual = Math.addExact(
                            e.reverse.residual, delta);
                    v = e.from;
                }

                sent = newSent;
                totalCost = newCost;
                steps.add("path=" + showPath(pathReverse)
                        + " delta=" + delta
                        + " unitCost=" + sp.unitCost()
                        + " reverse=" + (reverseSteps.isEmpty()
                           ? "none" : String.join(",", reverseSteps)));

                // Giu bat bien toi uu theo gia tri sent.
                checkNoNegativeCycle();
            }

            boolean[] sourceSide = reachableResidual(s);
            boolean maximal = !sourceSide[t];
            return new Result(
                    requested, sent, totalCost,
                    sent == requested, maximal,
                    sourceSide, List.copyOf(steps));
        }

        boolean validSolution(int s, int t, Result r) {
            long[] balance = new long[n];
            long computedCost = 0;
            for (Edge e : original) {
                long flow = Math.subtractExact(
                        e.capacity, e.residual);
                if (flow < 0 || flow > e.capacity
                        || e.reverse.reverse != e
                        || e.reverse.residual != flow) {
                    return false;
                }
                balance[e.from] =
                        Math.addExact(balance[e.from], flow);
                balance[e.to] =
                        Math.subtractExact(balance[e.to], flow);
                computedCost = Math.addExact(
                        computedCost,
                        Math.multiplyExact(flow, e.unitCost));
            }

            if (computedCost != r.cost()
                    || balance[s] != r.flow()
                    || balance[t] != -r.flow()
                    || r.metDemand() != (r.flow() == r.requested())) {
                return false;
            }
            for (int u = 0; u < n; u++) {
                if (u != s && u != t && balance[u] != 0) {
                    return false;
                }
            }

            if (r.maximal()) {
                long cutCapacity = 0;
                for (Edge e : original) {
                    if (r.sourceSide()[e.from]
                            && !r.sourceSide()[e.to]) {
                        cutCapacity = Math.addExact(
                                cutCapacity, e.capacity);
                    }
                }
                if (cutCapacity != r.flow()) return false;
            }
            return !r.maximal() || !r.sourceSide()[t];
        }

        String realArcs() {
            StringJoiner out = new StringJoiner(
                    ", ", "[", "]");
            for (Edge e : original) {
                long flow = Math.subtractExact(
                        e.capacity, e.residual);
                out.add(e.from + "->" + e.to
                        + ":" + flow + "/" + e.capacity
                        + "@" + e.unitCost);
            }
            return out.toString();
        }
    }

    static Network network(int n, long[][] arcs) {
        Network net = new Network(n);
        for (long[] a : arcs) {
            net.addArc((int) a[0], (int) a[1], a[2], a[3]);
        }
        return net;
    }

    static String showSide(boolean[] side) {
        StringJoiner out = new StringJoiner(
                ", ", "[", "]");
        for (int u = 0; u < side.length; u++) {
            if (side[u]) out.add(Integer.toString(u));
        }
        return out.toString();
    }

    static void report(String label, Result r) {
        System.out.println(label
                + " flow=" + r.flow()
                + " cost=" + r.cost()
                + " met=" + r.metDemand()
                + " maximal=" + r.maximal());
    }

    // Oracle doc lap: THU MOI LUONG f(e)=0..capacity
    // tren tung canh that, khong dung residual/shortest path.
    static Map<Long, Long> enumerateFlows(
            int n, List<long[]> arcs, int s, int t) {
        Map<Long, Long> bestByValue = new HashMap<>();
        long[] balance = new long[n];
        enumerateRec(arcs, 0, balance, 0,
                s, t, bestByValue);
        return bestByValue;
    }

    static void enumerateRec(
            List<long[]> arcs, int at, long[] balance,
            long cost, int s, int t,
            Map<Long, Long> bestByValue) {
        if (at == arcs.size()) {
            if (balance[s] < 0 || balance[s] != -balance[t]) {
                return;
            }
            for (int u = 0; u < balance.length; u++) {
                if (u != s && u != t && balance[u] != 0) {
                    return;
                }
            }
            bestByValue.merge(balance[s], cost, Math::min);
            return;
        }

        long[] e = arcs.get(at);
        int u = (int) e[0], v = (int) e[1];
        long capacity = e[2], unitCost = e[3];
        for (long f = 0; f <= capacity; f++) {
            balance[u] += f;
            balance[v] -= f;
            enumerateRec(arcs, at + 1, balance,
                    cost + f * unitCost, s, t, bestByValue);
            balance[u] -= f;
            balance[v] += f;
        }
    }

    static boolean inputNegativeCycle(
            int n, List<long[]> arcs) {
        Network net = new Network(n);
        for (long[] e : arcs) {
            net.addArc((int) e[0], (int) e[1], e[2], e[3]);
        }
        try {
            net.checkNoNegativeCycle();
            return false;
        } catch (IllegalArgumentException ex) {
            if (!"Negative-cost cycle".equals(ex.getMessage())) {
                throw ex;
            }
            return true;
        }
    }

    static Network build(int n, List<long[]> arcs) {
        Network net = new Network(n);
        for (long[] e : arcs) {
            net.addArc((int) e[0], (int) e[1], e[2], e[3]);
        }
        return net;
    }

    static int rngState = 20261110;

    // Deterministic unsigned 32-bit LCG.
    static int randomInt(int bound) {
        rngState = rngState * 1664525 + 1013904223;
        return (int) (Integer.toUnsignedLong(rngState) % bound);
    }

    record Checks(
            int networks, int accepted, int rejected, int demands) {}

    static final class Counter {
        int networks, accepted, rejected, demands;
    }

    static void checkCase(
            int n, List<long[]> arcs, Counter c) {
        c.networks++;

        if (inputNegativeCycle(n, arcs)) {
            c.rejected++;
            try {
                build(n, arcs).minCostUpTo(0, n - 1, 1);
                throw new AssertionError("Negative cycle accepted");
            } catch (IllegalArgumentException ex) {
                if (!"Negative-cost cycle".equals(ex.getMessage())) {
                    throw ex;
                }
            }
            return;
        }

        c.accepted++;
        Map<Long, Long> oracle =
                enumerateFlows(n, arcs, 0, n - 1);

        for (int limit = 0; limit <= 3; limit++) {
            Network net = build(n, arcs);
            Result actual = net.minCostUpTo(0, n - 1, limit);

            long desiredFlow = -1;
            long desiredCost = 0;
            for (Map.Entry<Long, Long> entry
                    : oracle.entrySet()) {
                long value = entry.getKey();
                if (value <= limit && value > desiredFlow) {
                    desiredFlow = value;
                    desiredCost = entry.getValue();
                }
            }
            if (actual.flow() != desiredFlow
                    || actual.cost() != desiredCost
                    || !net.validSolution(0, n - 1, actual)) {
                throw new AssertionError(
                        "Mismatch n=" + n
                        + " demand=" + limit
                        + " flow=" + actual.flow()
                        + " cost=" + actual.cost()
                        + " expected=" + desiredFlow
                        + "/" + desiredCost);
            }
            c.demands++;
        }
    }

    static Checks verifySmallNetworks() {
        Counter c = new Counter();

        // n=2,3: moi canh co huong u!=v co 3 lua chon:
        // vang mat; cap=1,cost=-1; cap=2,cost=2.
        for (int n = 2; n <= 3; n++) {
            int directedPairs = n * (n - 1);
            int total = 1;
            for (int j = 0; j < directedPairs; j++) {
                total *= 3;
            }
            for (int code = 0; code < total; code++) {
                List<long[]> arcs = new ArrayList<>();
                int x = code;
                for (int u = 0; u < n; u++) {
                    for (int v = 0; v < n; v++) {
                        if (u == v) continue;
                        int k = x % 3;
                        x /= 3;
                        if (k > 0) {
                            arcs.add(new long[]{
                                u, v, k, k == 1 ? -1 : 2
                            });
                        }
                    }
                }
                checkCase(n, arcs, c);
            }
        }

        // n=4 DAG: moi canh u<v co 4 lua chon:
        // vang mat; cap=1/cost=-2,0,3.
        int[] costs = {0, -2, 0, 3};
        for (int code = 0; code < 4096; code++) {
            List<long[]> arcs = new ArrayList<>();
            int x = code;
            for (int u = 0; u < 4; u++) {
                for (int v = u + 1; v < 4; v++) {
                    int k = x % 4;
                    x /= 4;
                    if (k > 0) {
                        arcs.add(new long[]{u, v, 1, costs[k]});
                    }
                }
            }
            checkCase(4, arcs, c);
        }

        // 700 mang n=2..5, 1..6 canh, cap=0..2,
        // cost=-3..3, co the co self-loop/song song.
        for (int test = 0; test < 700; test++) {
            int n = 2 + randomInt(4);
            int m = 1 + randomInt(6);
            List<long[]> arcs = new ArrayList<>();
            for (int i = 0; i < m; i++) {
                arcs.add(new long[]{
                    randomInt(n), randomInt(n),
                    randomInt(3), randomInt(7) - 3
                });
            }
            checkCase(n, arcs, c);
        }

        return new Checks(c.networks, c.accepted,
                c.rejected, c.demands);
    }

    public static void main(String[] args) {
        long[][] rerouteEdges = {
            {0,1,1,0}, {0,2,1,0},
            {1,3,1,4}, {1,4,1,5}, {2,3,1,6},
            {3,5,1,0}, {4,5,1,0}
        };
        Network reroute = network(6, rerouteEdges);
        Result r = reroute.minCostUpTo(0, 5, 2);
        report("reroute", r);
        for (int i = 0; i < r.steps().size(); i++) {
            System.out.println("reroute step" + (i + 1)
                    + " " + r.steps().get(i));
        }
        System.out.println("reroute arcs=" + reroute.realArcs());
        System.out.println("reroute sourceSide="
                + showSide(r.sourceSide()));
        System.out.println("reroute valid="
                + reroute.validSolution(0, 5, r));

        report("reroute1",
                network(6, rerouteEdges).minCostUpTo(0, 5, 1));
        report("reroute3",
                network(6, rerouteEdges).minCostUpTo(0, 5, 3));

        long[][] negativeEdges = {
            {0,1,2,-3}, {1,3,2,2},
            {0,2,2,2}, {2,3,2,0}
        };
        report("negative3",
                network(4, negativeEdges).minCostUpTo(0, 3, 3));
        report("negative4",
                network(4, negativeEdges).minCostUpTo(0, 3, 4));

        long[][] parallelEdges = {
            {0,1,2,2}, {0,1,1,1},
            {1,2,2,0}, {0,2,2,5}
        };
        report("parallel3",
                network(3, parallelEdges).minCostUpTo(0, 2, 3));
        report("parallel4",
                network(3, parallelEdges).minCostUpTo(0, 2, 4));

        report("antiparallel3",
                network(3, new long[][]{
                    {0,1,2,1}, {1,0,1,2},
                    {1,2,2,1}, {0,2,1,5}
                }).minCostUpTo(0, 2, 3));

        report("disconnected1",
                network(4, new long[][]{
                    {0,1,3,1}, {2,3,4,1}
                }).minCostUpTo(0, 3, 1));

        report("selfLoop1",
                network(3, new long[][]{
                    {0,0,3,1}, {0,1,1,0}, {1,2,1,2}
                }).minCostUpTo(0, 2, 1));

        try {
            network(3, new long[][]{
                {0,1,1,1}, {1,0,1,-3}, {0,2,1,5}
            }).minCostUpTo(0, 2, 1);
            throw new AssertionError("Negative cycle accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negativeCycleRejected="
                    + ex.getMessage());
        }

        try {
            network(4, new long[][]{
                {0,3,1,5}, {1,2,1,-3}, {2,1,1,0}
            }).minCostUpTo(0, 3, 1);
            throw new AssertionError(
                    "Disconnected negative cycle accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("disconnectedNegativeCycleRejected="
                    + ex.getMessage());
        }

        Checks checked = verifySmallNetworks();
        System.out.println("testedNetworks=" + checked.networks());
        System.out.println("acceptedNetworks=" + checked.accepted());
        System.out.println("rejectedNetworks=" + checked.rejected());
        System.out.println("testedDemands=" + checked.demands());
    }
}
~~~

Lưu thành tệp **MinCostAugmentingPathsDemo.java**. Chạy bằng **JDK 17 trở lên**:

~~~bash
javac MinCostAugmentingPathsDemo.java
java MinCostAugmentingPathsDemo
~~~

**Đầu ra dự kiến với thứ tự cạnh trong mã:**

~~~text
reroute flow=2 cost=11 met=true maximal=true
reroute step1 path=0->1->3->5 delta=1 unitCost=4 reverse=none
reroute step2 path=0->2->3->1->4->5 delta=1 unitCost=7 reverse=3->1
reroute arcs=[0->1:1/1@0, 0->2:1/1@0, 1->3:0/1@4, 1->4:1/1@5, 2->3:1/1@6, 3->5:1/1@0, 4->5:1/1@0]
reroute sourceSide=[0]
reroute valid=true
reroute1 flow=1 cost=4 met=true maximal=false
reroute3 flow=2 cost=11 met=false maximal=true
negative3 flow=3 cost=0 met=true maximal=false
negative4 flow=4 cost=2 met=true maximal=true
parallel3 flow=3 cost=8 met=true maximal=false
parallel4 flow=4 cost=13 met=true maximal=true
antiparallel3 flow=3 cost=9 met=true maximal=true
disconnected1 flow=0 cost=0 met=false maximal=true
selfLoop1 flow=1 cost=2 met=true maximal=true
negativeCycleRejected=Negative-cost cycle
disconnectedNegativeCycleRejected=Negative-cost cycle
testedNetworks=5534
acceptedNetworks=5141
rejectedNetworks=393
testedDemands=20564
~~~

### Đọc các trường kết quả

- `flow` là số đơn vị thực gửi, **không mặc định bằng demand**.
- `cost` là tổng `sum(flowOnRealEdge × unitCost)` của **từng cạnh thật**.
- `met` là yêu cầu được đáp ứng hoàn toàn `flow==requested`.
- `maximal` nghĩa là **không còn đường s→t trong mạng dư** của nghiệm cuối; trường này có thể false khi ta cố ý dừng sớm vì đã đủ demand.
- `sourceSide` là tập đỉnh còn tới được từ s trong residual cuối. Khi maximal=true, nó xác định một min-cut và capacity của cut bằng `flow`.
- `step path` là **đường trong mạng dư**, có thể bao gồm cạnh ngược không tồn tại trong đồ thị đầu vào.
- `reverse=3->1` trong bước hai là **hủy luồng trên cạnh thật 1→3**, không vận chuyển một đơn vị trên tuyến 3→1 thực.
- `cost` có thể âm; ví dụ `negative3` gửi hai đơn vị qua đường unit cost −1 và một đơn vị qua đường unit cost 2, nên tổng −2+2=0.
- `parallel3` và `parallel4` kiểm tra hai cạnh thật 0→1 khác cost; chương trình giữ chúng là hai cặp residual riêng.
- `selfLoop1` có self-loop cost dương không tác động giá trị s–t; nếu self-loop cost âm và capacity dương, thuật toán **từ chối** do tạo chu trình âm.

### Giới hạn API một lượt và overflow

`Network` minh họa chỉ hỗ trợ **một lần gọi `minCostUpTo` trên cùng đối tượng**. Mạng dư bị thay đổi sau khi tính; gọi lại mà khởi tạo `sent=0` sẽ trộn trạng thái cũ và báo sai tổng luồng/cost. Mã dùng trường `used` để chặn lỗi sử dụng này. Muốn giải một demand khác, tạo Network mới với **cùng danh sách cạnh thật ban đầu**.

Chi phí có thể là số nguyên âm, nhưng `Math.negateExact(cost)` từ chối `Long.MIN_VALUE` vì số đối dấu của nó không biểu diễn được trong long. Các phép cộng và nhân dùng `Math.addExact` và `Math.multiplyExact` để **phát hiện tràn** thay vì âm thầm làm sai tối ưu. Với giá trị quá lớn, dùng kiểu số chính xác hơn (ví dụ `BigInteger`) và điều chỉnh thuật toán số học. Nếu một lỗi số học xảy ra giữa cập nhật residual, chương trình minh họa **không tự rollback** toàn bộ trạng thái; không tiếp tục dùng object ấy như một kết quả hợp lệ.

## 11. Kiểm thử độc lập bằng vét cạn mọi cấu hình luồng

Bộ `verifySmallNetworks` không dựa vào việc so chi phí với một thuật toán SSP giống hệt. Nó dùng **oracle độc lập**, gán thử mọi lượng luồng trên từng **cạnh thật** trong phạm vi `0..capacity` và kiểm tra trực tiếp:
- từng flow nằm trong `[0,capacity]`;
- conservation tại tất cả đỉnh ngoài s,t;
- giá trị ròng ở nguồn/đích;
- tổng chi phí = tổng `flow×unitCost`;
- với từng giá trị có thể gửi, chi phí nhỏ nhất là bao nhiêu.

Với mỗi mức demand L, oracle chọn **giá trị luồng lớn nhất không vượt L**, sau đó lấy **chi phí nhỏ nhất trong các luồng có đúng giá trị đó**. Đây chính là hợp đồng `minCostUpTo`, kể cả khi L không thể đạt.

### Những bộ dữ liệu được kiểm tra

| Nhóm | Số mạng |
| --- | ---: |
| n=2, hai cặp cạnh có hướng u≠v, mỗi cặp có ba trạng thái | 9 |
| n=3, sáu cặp cạnh có hướng u≠v, mỗi cặp có ba trạng thái | 729 |
| n=4 DAG, sáu cặp u<v, mỗi cặp có bốn trạng thái | 4.096 |
| Mạng xác định giả ngẫu nhiên n=2..5, có thể có self-loop/song song | 700 |
| **Tổng** | **5.534** |

Với n=2,3, ba trạng thái mỗi cặp là: không có cạnh; có cạnh capacity1 cost−1; hoặc capacity2 cost2. Với n=4 DAG, bốn trạng thái là: không có cạnh; capacity1 cost−2; capacity1 cost0; capacity1 cost3.

Nhóm 700 mạng bổ sung có số cạnh 1..6, capacity 0..2, unit cost −3..3, sinh bằng bộ tạo số xác định. Nhóm này có thể có cạnh song song, cạnh hai chiều thật hoặc self-loop.

Trước khi so oracle, cả mô hình và chương trình đều **phân loại chu trình chi phí âm** trong mạng dư ban đầu. Những mạng có chu trình âm được **từ chối theo hợp đồng**, không bị tính nhầm thành một kết quả min-cost của SSP đơn giản.

Kết quả đối chiếu độc lập:

- **5.534** cấu hình được xem xét.
- **5.141** cấu hình thỏa giả thiết không có chu trình chi phí âm.
- **393** cấu hình có chu trình chi phí âm và được từ chối.
- Với mỗi cấu hình hợp lệ, thử demand `L=0,1,2,3`, tổng **20.564 truy vấn demand**, giá trị luồng và chi phí đều khớp oracle.

Kiểm thử còn xác minh trên mỗi kết quả: residual thuận/ngược còn hợp lệ, conservation theo từng đỉnh, total cost tính lại từ cạnh thật và chứng chỉ min-cut khi maximal=true.

**Vì sao vẫn cần chứng minh?** Vét cạn mạng nhỏ giúp tìm lỗi code, nhất là **cạnh ngược âm**, **chu trình 0**, **capacity 0**, **mạng không liên thông**, **demand không đạt** và **chi phí âm**. Nhưng 5.534 mạng hữu hạn không thể thay thế lập luận bảo toàn, tính tối ưu của đường ngắn nhất và định lý không có chu trình dư âm cho mạng bất kỳ.

## 12. So sánh với các bài toán gần nhau

| Bài toán | Mục tiêu | Điểm khác với SSP min-cost |
| --- | --- | --- |
| **Max-flow** | Tối đa hóa lượng luồng | Không quan tâm chi phí |
| **Min-cut** | Tìm lát cắt có capacity nhỏ nhất | Chứng minh giá trị max-flow, không tự giải min cost |
| **Shortest path** | Tìm một đường rẻ nhất | Không tự xử lý nhiều đơn vị, bottleneck, reroute |
| **Min-cost flow fixed demand** | Gửi đúng F, tổng chi phí nhỏ nhất | Báo bất khả thi nếu max-flow < F |
| **Min-cost max-flow** | Giá trị luồng cực đại, chi phí nhỏ nhất trong số đó | Tiếp tục đường tăng tới khi hết đường s→t |
| **Circulation** | Bảo toàn ở mọi đỉnh, thường không có s,t riêng | Có thể tối ưu qua chu trình, cần xét thêm ràng buộc |
| **Flow có lower bound** | Mỗi cạnh có cả giới hạn dưới và trên | Phải biến đổi bài toán và cân bằng nhu cầu |
| **Assignment / matching có trọng số** | Ghép các đối tượng để tối thiểu chi phí | Có thể mô hình thành min-cost flow, hoặc dùng Hungarian... |

### Khi nào nên chọn SSP?

SSP khá trực quan khi:
- mạng không quá lớn;
- cần hiểu rõ từng quyết định gửi thêm luồng;
- capacity nguyên và số đường tăng không quá nhiều;
- có thể bảo đảm không có chu trình âm trong residual ban đầu hoặc xử lý/loại trường hợp đó theo bài toán.

Với mạng lớn và nhiều lần tăng, bản Bellman–Ford mỗi vòng có thể chậm; potentials + Dijkstra, cost-scaling và các thuật toán chuyên biệt có thể tốt hơn. Với bài chỉ muốn max-flow không có cost, dùng Dinic/Edmonds–Karp sẽ đơn giản hơn.

## 13. Trường hợp biên và lỗi thường gặp

| Trường hợp | Cách xử lý |
| --- | --- |
| Demand F=0 | Gửi 0, cost 0 **trong giả thiết không có chu trình âm ban đầu** |
| Không có đường s→t | Gửi 0, met=false nếu F>0, maximal=true |
| Demand vượt max-flow | Gửi max-flow, chi phí min cho giá trị thực gửi, met=false |
| Cạnh capacity 0 | Không được dùng để tăng, kể cả cost âm |
| Cạnh cost 0 | Tính bình thường, có thể có nhiều đường hòa |
| Cạnh cost âm nhưng không có chu trình âm | Bellman–Ford xử lý hợp lệ |
| Chu trình cost âm có capacity dư dương | Phiên bản SSP này **từ chối** |
| Chu trình cost âm ở thành phần không tới từ s | Vẫn từ chối để không bỏ sót luồng tuần hoàn làm giảm cost |
| Self-loop cost âm và capacity dương | Chu trình âm, từ chối |
| Self-loop cost không âm | Không giúp tăng s–t, có thể bỏ qua trong đường tăng |
| Hai cạnh song song | Lưu/cập nhật riêng từng Edge và reverse |
| Có cạnh thật cả u→v và v→u | Không nhầm với cạnh dư ngược của cạnh khác |
| Chi phí cực lớn | Phát hiện overflow bằng Math.addExact/multiplyExact |
| Cost=Long.MIN_VALUE | NegateExact không biểu diễn được cạnh đảo trong long |
| Gọi solver hai lần trên residual đã thay đổi | Phải reset có chủ đích hoặc tạo Network mới |
| Nguồn trùng đích | Từ chối theo hợp đồng s–t flow |
| Dijkstra khi residual còn cost âm | Sai nếu không reweight |
| Đạt demand trước khi đạt max-flow | met=true nhưng maximal có thể false |
| Không còn đường dư | maximal=true, có thể dựng min-cut để kiểm chứng lượng |

Các lỗi điển hình:
1. **Nhầm unit cost với capacity**, cho phép cost âm nhưng lại từ chối capacity âm không nhất quán.
2. **Chọn đường ít cạnh nhất thay vì rẻ nhất** theo tổng chi phí.
3. **Dùng Dijkstra trực tiếp** khi residual chứa cạnh chi phí âm.
4. **Quên cạnh dư ngược hoặc đặt cost ngược không đối dấu**.
5. **Cập nhật residual thuận nhưng không cập nhật reverse**, không thể hủy luồng cũ.
6. **Lưu parent vertex thay vì parent edge**, cập nhật sai trong mạng đa cạnh.
7. **Không giới hạn delta bởi demand còn lại**, gửi vượt F.
8. **Lấy tổng chi phí đường nhưng quên nhân bottleneck**, sai khi delta>1.
9. **Coi đường tăng có cạnh dư ngược là đường thật**, dẫn tới giải thích sai.
10. **Không kiểm tra conservation** khi xác minh cấu hình luồng.
11. **Không phân biệt tổng cost và tổng lượng gửi**, hoặc báo met=true khi chỉ gửi một phần.
12. **Không xét chu trình âm ban đầu**, nên bỏ sót khả năng giảm cost qua tuần hoàn.
13. **Chỉ phát hiện chu trình âm reachable từ s**, bỏ qua chu trình âm ở thành phần khác.
14. **Tưởng min-cut chứng minh min-cost**, trong khi cut chỉ chứng minh giá trị max-flow.
15. **Tính total cost từ residual reverse như cạnh thật**, làm đếm trùng chi phí.
16. **Gộp cạnh thật ngược chiều với cạnh đảo dư**, phá ý nghĩa hủy luồng.
17. **Không xử lý overflow chi phí tích capacity×cost**, gây đổi dấu tổng chi phí.
18. **Gọi lại solver trên residual đã mutate mà sent vẫn bắt đầu từ 0**, tạo kết quả không nhất quán.
19. **Coi mọi chi phí phải không âm**, bỏ qua mạng có lợi nhuận/chiết khấu.
20. **Tin parent từ một lượt relax có thể bị ảnh hưởng bởi vòng cost0 mà không xác minh đường**, thay vì dựng đường đơn từ cạnh tight.

## 14. Bài tập tự luyện có hướng dẫn

**Bài 1 — capacity và cost.** Một cạnh có capacity 5, unit cost −2. Gửi 3 đơn vị qua cạnh có hợp lệ theo riêng capacity? Đóng góp cost là bao nhiêu?

*Đáp án:* Hợp lệ theo capacity vì 0≤3≤5; cost = 3×(−2)=**−6**. Toàn mạng vẫn phải bảo toàn luồng.

**Bài 2 — bảo toàn.** Đỉnh x nhận 2 đơn vị từ a, 3 từ b và gửi 4 sang c. Có phải luồng khả thi không?

*Đáp án:* Không. Inflow=5, outflow=4, thiếu 1 đơn vị.

**Bài 3 — bottleneck.** Đường dư có residual [8,3,5], demand còn 2. Tăng bao nhiêu?

*Đáp án:* Min(8,3,5,2)=**2**.

**Bài 4 — cost tăng thêm.** Đường dư có unit cost −4, tăng \Delta=3. Total cost thay đổi bao nhiêu?

*Đáp án:* 3×(−4)=**−12**.

**Bài 5 — cạnh ngược.** Cạnh thật 1→3 capacity1 cost4 đã có flow1. Residual thuận/ngược cùng cost là gì?

*Đáp án:* Thuận residual0 cost+4; ngược 3→1 residual1 cost−4. Đi ngược một đơn vị làm flow thật 1→3 về 0 và giảm cost 4.

**Bài 6 — ví dụ tái định tuyến.** Sau đường `0→1→3→5` cost4, tại sao đường thứ hai lại dùng `0→2→3→1→4→5` cost7?

*Đáp án:* Cạnh 3→1 là dư ngược cost−4, cho phép hủy flow 1→3 và chuyển sang 1→4. Tính tổng 0+6−4+5+0=7; giá trị luồng tăng thêm1.

**Bài 7 — cost cuối.** Với hai đường tăng unit cost4 và7, mỗi đường bottleneck1, totalCost?

*Đáp án:* 1×4+1×7=**11**. Có thể kiểm tra lại bằng hai đường thật 0→1→4→5 cost5 và0→2→3→5 cost6.

**Bài 8 — demand không đạt.** Nếu mạng chỉ gửi tối đa 2 đơn vị mà yêu cầu F=3, kết quả hợp đồng `minCostUpTo` là gì?

*Đáp án:* Trả `flow=2`, `met=false` và cost thấp nhất cho luồng giá trị2; không được coi là nghiệm gửi đúng3.

**Bài 9 — negative cost edge.** Cạnh thật chi phí −3 có nhất thiết làm bài không hợp lệ không?

*Đáp án:* Không. Chỉ cần giả thiết không có **chu trình chi phí âm với capacity dư dương** ở mạng ban đầu. Cạnh âm riêng lẻ được Bellman–Ford xử lý.

**Bài 10 — chu trình âm ngoài thành phần nguồn.** Có một vòng âm ở hai đỉnh không tới được từ s. Vì sao bài vẫn xem nó quan trọng?

*Đáp án:* Có thể đẩy luồng tuần hoàn trên vòng làm tổng cost giảm mà không đổi giá trị s–t. Solver đường tăng đơn giản không tự xử lý, nên phải từ chối hoặc có thuật toán cycle-canceling.

**Bài 11 — đường rẻ nhất.** Đường A có 2 cạnh total cost 9; đường B có 3 cạnh total cost 4. Cả hai đủ residual. Nên chọn đường nào để gửi thêm một đơn vị?

*Đáp án:* B, vì tổng **cost4** thấp hơn cost9; số cạnh không phải mục tiêu.

**Bài 12 — potentials.** Nếu `a_\pi(u,v)=a(u,v)+\pi[u]-\pi[v]`, tổng reduced cost trên đường s→t khác tổng cost thật bởi giá trị nào?

*Đáp án:* Hằng số `\pi[s]-\pi[t]`. Vì hằng số giống nhau cho mọi đường s→t, đường tối ưu vẫn được giữ.

**Bài 13 — min-cut.** Một luồng có value5 và có min-cut capacity5. Đã chắc nó có min-cost trong các luồng value5 chưa?

*Đáp án:* **Chưa**. Cut chứng minh lượng gửi đã tối đa, không chứng minh chi phí tối thiểu. Cần thêm điều kiện tối ưu chi phí như không có residual negative-cost cycle.

**Bài 14 — time complexity.** Nếu dùng Bellman–Ford O(VE) mỗi đường tăng và có K lần tăng, độ phức tạp là bao nhiêu?

*Đáp án:* O(KVE), cộng chi phí khởi tạo/kiểm tra. Với capacity nguyên và mỗi \Delta≥1, có thể chặn K≤F khi gửi tối đa F đơn vị, dẫn tới O(FVE) — đây là chặn theo **giá trị số**, không nhất thiết tốt với capacity rất lớn.

**Bài 15 — cạnh thật hai chiều.** Có hai cạnh thật u→v cost3 và v→u cost5. Cạnh dư ngược của u→v có cost bằng bao nhiêu?

*Đáp án:* **−3**, không phải +5. Cạnh thật v→u cost+5 là một cạnh **khác** với residual ngược v→u cost−3.

## 15. Checklist khi viết lời giải và đọc kết quả

1. **Xác định rõ mục tiêu:** gửi đúng F hay min-cost max-flow; khi F không đạt, yêu cầu trả infeasible hay trả luồng lớn nhất không vượt F.
2. **Phân biệt capacity, unit cost, actual flow**; capacity không âm nhưng chi phí có thể âm.
3. **Mô hình hóa conservation** tại mọi đỉnh trung gian và giá trị net flow tại s/t.
4. **Chốt giả thiết chu trình âm.** Nếu dữ liệu có residual negative-cost cycle ban đầu, thuật toán SSP từ luồng0 trong bài không đủ để bảo đảm tối ưu tổng quát.
5. **Tạo cặp residual Edge** với capacity thuận U, ngược0 và cost thuận +a, ngược −a.
6. **Tìm đường theo chi phí, không phải số cạnh.** Bellman–Ford xử lý cạnh âm; nếu dùng Dijkstra phải đảm bảo reduced costs hợp lệ.
7. **Lưu parent edge** và chọn một đường s→t đơn có residual dương trên mọi cạnh.
8. **Tính delta=min(bottleneck,F−sent)** và cập nhật cả residual lẫn reverse.
9. **Cộng sent và totalCost riêng**, trong đó `deltaCost=delta×unitCost(path)` có thể âm.
10. **Dừng khi đủ F hoặc hết đường dư s→t**, nêu rõ `metDemand` và `maximal` không đồng nghĩa.
11. **Tính lại cost từ cạnh thật**, kiểm tra 0≤flow≤capacity và conservation sau khi giải.
12. **Nếu đạt max-flow**, dùng cut từ residual để chứng nhận giá trị; dùng điều kiện residual không có chu trình âm để chứng nhận min-cost.
13. **Kiểm tra dữ liệu biên:** cap0, cost âm, self-loop, song song, hai chiều, không liên thông, F=0, F vượt max, overflow.
14. **Tách tối ưu chi phí khỏi tối ưu lượng gửi** trong báo cáo, tránh gọi luồng F' nhỏ hơn F là lời giải cho demand F.
15. **Dùng oracle vét cạn** cho đồ thị nhỏ, so cả value, cost và trạng thái feasible, thay vì chỉ so tổng lượng gửi.

## Ghi nhớ

- **Min-cost flow** tối ưu `sum(flow×unitCost)` với sức chứa và bảo toàn luồng; **min-cost max-flow** còn phải đạt giá trị luồng cực đại.
- **Mạng dư** cho phép cả tăng flow theo cạnh thuận lẫn **hủy flow** theo cạnh ngược có cost **đối dấu**.
- **Successive shortest augmenting path:** tìm đường s→t rẻ nhất trong residual, tăng `delta=min(bottleneck,remaining)`, điều chỉnh cặp cạnh dư, cập nhật `totalCost+=delta×pathCost`.
- **Bellman–Ford** dùng được với cạnh âm; **Dijkstra** chỉ nên dùng sau khi bảo đảm reduced costs không âm bằng potentials thích hợp.
- **Giả thiết quan trọng:** bản SSP bắt đầu ở flow0 này yêu cầu residual ban đầu **không có chu trình chi phí âm toàn cục**; chu trình âm có thể chứa tuần hoàn giúp giảm chi phí mà không đổi value.
- **Không còn đường s→t** chứng minh đạt max-flow; **không còn residual negative-cost cycle** chứng minh chi phí tối ưu tại value đang có. Min-cut **không tự chứng minh min-cost**.
- **Bottleneck quyết định lượng tăng**, còn **cost đường dư quyết định giá tăng thêm**, bao gồm cả những bước hủy luồng qua reverse.
- Với chương trình Java 17 dựa trên Bellman–Ford, thời gian O(KVE) cho K đường tăng; dùng potentials + Dijkstra khi cần cải thiện hiệu năng trên mạng lớn.
