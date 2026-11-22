# Phương pháp đẩy–đổi nhãn (push–relabel)

**Push–relabel** (còn gọi là **preflow–push**, tiếng Việt thường viết **đẩy–đổi nhãn**) là một thuật toán tìm **luồng cực đại** (*maximum flow*) trên mạng có hướng và dung lượng cạnh không âm. Khác với Ford–Fulkerson hoặc Edmonds–Karp liên tục tìm **đường tăng luồng đầy đủ từ nguồn s tới đích t**, push–relabel cho phép một trạng thái trung gian gọi là **tiền luồng (preflow)**: các đỉnh ở giữa có thể tạm thời nhận nhiều luồng hơn lượng đã gửi đi. Thuật toán từng bước **đẩy lượng dư** qua các cạnh trong **đồ thị dư**, và nếu không thể đẩy theo các cạnh thích hợp thì **nâng nhãn độ cao** của đỉnh để mở đường đẩy mới.

Khi các đỉnh trung gian không còn lượng dư, preflow trở thành **luồng khả thi**. Đồng thời hệ nhãn độ cao bảo đảm **không còn đường tăng trong mạng dư từ s tới t**, nên luồng ấy là **cực đại** theo định lý **max-flow min-cut**.

Bài thuộc nhóm **Luồng mạng**, tập trung vào **Phương pháp đẩy–đổi nhãn (push–relabel)**. Nội dung gồm mô hình luồng và đồ thị dư, các bất biến của preflow/height, thao tác push và relabel, hàng đợi FIFO cùng discharge/current arc, ví dụ tính tay, chứng minh kết thúc và tối ưu, độ phức tạp, cắt cực tiểu làm chứng, cấu trúc cạnh ngược trong Java 17+, cạnh song song/đối hướng/self-loop, rủi ro tràn số, kiểm thử độc lập và các biến thể thực tiễn.

**Mục tiêu:** hiểu được vì sao cho phép excess ở các đỉnh trung gian vẫn dẫn đến kết quả đúng; áp dụng chính xác điều kiện **cạnh dư có thể đẩy** `height[u]=height[v]+1`; chỉ relabel một đỉnh đang active khi không còn cạnh đẩy thích hợp; quản lý năng lực cạnh dư thuận/ngược; dựng một max flow và min cut có **cùng giá trị**; phân biệt push–relabel với augmenting-path algorithms.

## 1. Mô hình mạng luồng

Cho đồ thị có hướng `G=(V,E)` với `n=|V|≥2` đỉnh, nguồn **s** và đích **t**, `s≠t`. Mỗi cạnh có hướng `e=(u,v)` có **dung lượng không âm** `c(e)≥0`. Đồ thị có thể có nhiều cạnh cùng hai đầu mút (**parallel edges**), và có thể có hai cạnh hướng ngược nhau `u→v` và `v→u` (antiparallel edges). Trong mô hình bài này, self-loop không giúp đưa luồng từ nguồn tới đích nên có thể bỏ qua khi xây residual graph.

Một luồng khả thi `f` cần thỏa:

1. **Giới hạn dung lượng:** trên cạnh gốc e, `0≤f(e)≤c(e)`.
2. **Bảo toàn luồng:** ở mọi đỉnh `v≠s,t`, tổng luồng đi vào bằng tổng luồng đi ra.
3. **Giá trị luồng:** tổng luồng thực đi ra khỏi s trừ luồng đi vào s, bằng tổng đi vào t trừ tổng đi ra t.

Mục tiêu là **tối đa hóa** giá trị luồng:

**`|f| = Σ_{(s,v)∈E} f(s,v) − Σ_{(u,s)∈E} f(u,s)`.**

Một ví dụ nhỏ:

~~~text
s(0) --(5)--> a(1) --(3)--> t(2)
~~~

Giá trị luồng cực đại là **3**, vì cạnh a→t chỉ có dung lượng 3. Đẩy 5 vào a rồi phải đưa 2 đơn vị trở về s là một ví dụ trực giác của trạng thái **preflow** và thao tác đẩy ngược qua cạnh dư.

### Luồng cực đại không phải tổng dung lượng cạnh ra khỏi nguồn

Tổng các dung lượng rời nguồn chỉ là **cận trên** của max flow. Các nút trung gian hoặc cạnh vào đích có thể tạo nút thắt. Ví dụ trên, nguồn có thể phát 5 nhưng chỉ 3 tới được t; thuật toán phải **hoàn trả hoặc chuyển hướng** 2 đơn vị dư chứ không được công bố kết quả 5.

Nếu t không đạt được từ s theo các cạnh dung lượng dương, giá trị cực đại là **0**. Nếu có nhiều luồng tối ưu, giá trị tối ưu vẫn là một số duy nhất, nhưng cách phân phối cụ thể trên cạnh có thể khác nhau.

## 2. Đồ thị dư: chìa khóa để sửa luồng

Với một cạnh gốc `u→v` dung lượng c và luồng hiện tại f, ta có:

- **Cạnh dư thuận u→v:** `residualForward=c−f`; biểu diễn lượng có thể đẩy thêm theo hướng gốc.
- **Cạnh dư ngược v→u:** `residualReverse=f`; biểu diễn lượng có thể **hoàn tác** khỏi phần luồng đã đẩy trước đó.

Hai cạnh dư được lưu thành **một cặp liên kết**. Khi đẩy `Δ` theo một cung dư u→v:

**`residual(u→v) -= Δ`** và **`residual(reverse) += Δ`**.

Đẩy theo cung dư ngược không làm tăng một luồng gốc ngược bất hợp lệ; đó là **giảm bớt lượng luồng đang dùng** trên cạnh gốc tương ứng. Nếu đồ thị gốc thật sự có thêm cạnh v→u, cạnh ấy phải được lưu bằng **một cặp residual riêng**.

### Ví dụ cạnh ngược

Một cạnh gốc 0→1 dung lượng 8, vừa đẩy 5:

~~~text
Original: 0 --capacity 8--> 1

Residual:
0 --3--> 1
0 <--5-- 1
~~~

Nếu sau đó đẩy 2 trên cung dư ngược 1→0, luồng gốc còn 3, residual thuận tăng thành 5 và residual ngược giảm còn 3.

**Không xóa cạnh ngược!** Nếu không có chúng, thuật toán không thể hoàn tác lựa chọn ban đầu và có thể mắc kẹt ở một luồng không tối ưu.

### Cạnh song song và cạnh đối hướng

Giả sử có hai cạnh gốc `0→1` với dung lượng 5 và 4. Chúng là **hai cạnh riêng**, mỗi cạnh có **cặp reverse riêng**. Tổng khả năng mang luồng của chúng là 9.

Nếu đồng thời có một cạnh gốc `1→0` dung lượng 7, nó là một **cạnh thuận riêng theo chiều ngược**, không được nhầm với cạnh residual ngược của hai cạnh trước.

Trong cài đặt adjacency list, cách an toàn là mỗi `Edge` có:

- `to`: đỉnh đầu kia.
- `rev`: **chỉ số** của cạnh dư ngược trong danh sách kề của `to`.
- `residual`: dung lượng dư hiện thời.

Khi đẩy, truy cập trực tiếp `graph[e.to].get(e.rev)` để cập nhật đúng cạnh đối ứng. **Không tìm cạnh ngược chỉ bằng hai endpoint** vì có thể có nhiều cạnh cùng cặp đỉnh.

## 3. Preflow và excess: khác gì luồng khả thi?

Một **preflow** vẫn tôn trọng dung lượng cạnh nhưng cho phép tại các đỉnh trung gian:

**`inflow(v) ≥ outflow(v)`**.

Đặt **lượng dư (excess)**:

**`excess(v)=inflow(v)−outflow(v)`.**

Đối với đỉnh trung gian v, preflow yêu cầu `excess(v)≥0`. Nếu `excess(v)>0`, v được gọi là **active** (đang có lượng dư cần xử lý). Nguồn s có thể có excess **âm** do đã phát luồng, còn đích t được phép tích luồng dư và không bị discharge.

Các đại lượng:

| Khái niệm | Ý nghĩa |
|---|---|
| `capacity(e)` | Dung lượng cạnh gốc, không âm |
| `residual(e)` | Lượng có thể đẩy thêm theo một cung dư |
| `excess(v)` | Luồng vào trừ luồng ra tại v |
| `height(v)` | Nhãn độ cao nguyên không âm của v |
| Active v | `v≠s,t` và `excess(v)>0` |
| Admissible residual edge | Cung u→v có residual>0 và `height(u)=height(v)+1` |
| Discharge(v) | Lặp push/relabel đến khi `excess(v)=0` |

Khi kết thúc, nếu **mọi đỉnh trung gian đều có excess=0**, preflow thỏa bảo toàn ở những đỉnh ấy và trở thành **luồng khả thi**. Excess ở đích chính là lượng luồng thu được (giá trị max flow sau khi thuật toán hoàn tất).

### Tại sao preflow có ích?

Trong augmenting-path algorithms, trước mỗi lần tăng luồng ta phải tìm một đường dư **từ s tới t**. Push–relabel không đợi toàn bộ đường: nó đẩy lượng cục bộ từ một đỉnh đang dư, ngay cả khi chưa biết lượng ấy có thể tới đích hay phải quay lại nguồn.

Cách làm ấy tạo ra nhiều thao tác cục bộ, dễ kết hợp heuristic và phù hợp với một số bài toán mạng lớn. Nhưng phải duy trì đúng **nhãn độ cao** để các thao tác không chạy vòng tùy tiện.

## 4. Nhãn độ cao (height) và bất biến hợp lệ

Thuật toán duy trì nhãn nguyên `h(v)≥0`, với:

- **`h(s)=n`**.
- **`h(t)=0`**.
- Với mọi **cung dư u→v có residual>0**, bất biến:

**`h(u)≤h(v)+1`.**

Đây là bất biến **valid labeling**. Nó không nói h(v) đúng bằng khoảng cách ngắn nhất từ v tới t; giá trị height là một **chứng nhận tương đối** cho hướng đẩy. Nếu xét một đường dư từ u đi tới t, bất biến suy ra chiều dài đường ít nhất h(u) khi h(t)=0; do đó nếu h(u) lớn hơn số cạnh của một đường đơn có thể có, u không thể còn đường dư tới t.

Một cung dư `u→v` được gọi là **admissible** khi:

**`residual(u→v)>0` và `h(u)=h(v)+1`.**

Chỉ đẩy dọc cung admissible. Ta thường mô tả trực giác là luồng “chảy **xuống một bậc**” theo nhãn cao độ.

### Vì sao h(s)=n?

Để sau bước khởi tạo, ta có thể bão hòa các cung dư đi ra nguồn mà vẫn giữ valid labeling. Ban đầu tất cả đỉnh khác có h=0; sau khi bão hòa mọi cạnh gốc ra nguồn, các cạnh dư thuận từ nguồn có residual=0, còn cạnh dư ngược từ hàng xóm về nguồn có h(hàng xóm)=0 và h(s)=n, thỏa h(u)≤h(v)+1. Các cạnh khác có hai đầu height=0.

Quan trọng hơn, nếu sau này còn đường dư `s⇝t`, lấy đường đơn có không quá n−1 cạnh. Trên từng cung dư, `h(u)≤h(v)+1`, cộng theo đường sẽ cho:

**`h(s)≤h(t)+(n−1)=n−1`**,

trái với `h(s)=n`. Vì vậy **một valid labeling với h(s)=n,h(t)=0 tự chứng minh không có đường dư s→t**.

Tuy nhiên lúc còn excess ở đỉnh trung gian, ta chưa có **luồng khả thi**. Điều kiện kết thúc cần **cả** preflow không còn active và valid labeling, chứ không chỉ dựa vào một câu về đường dư.

## 5. Khởi tạo preflow: bão hòa nguồn

Bước khởi tạo của push–relabel:

1. Đặt `h(s)=n` và `h(v)=0` cho mọi v khác.
2. Đặt `excess(v)=0` cho tất cả.
3. Với **mỗi cạnh gốc đi ra s** có dung lượng c>0 và đầu kia khác s, **đẩy toàn bộ c**.
4. Cập nhật các cung dư thuận/ngược và excess của hai đầu.
5. Đưa mọi đỉnh trung gian có excess>0 vào hàng đợi active.

Ví dụ nguồn 0 có hai cung:

`0→1` dung lượng 16 và `0→2` dung lượng 13.

Sau khởi tạo:

- `h(0)=n`; các height khác 0.
- Cả hai cung dư thuận của nguồn bão hòa.
- `excess(0)=−29`.
- `excess(1)=16`, `excess(2)=13`.
- Đỉnh 1 và 2 active; các đỉnh khác chưa có excess.

**Chú ý:** 29 ở đây **chưa phải max flow**. Đích có thể chỉ nhận 23, và 6 đơn vị có thể được đẩy ngược về nguồn sau những relabel phù hợp.

Các cung gốc **đi vào s** tạo ra cung residual đi vào s (dung lượng ban đầu của cạnh) và cung đảo từ s có residual=0. Bước khởi tạo chỉ bão hòa những cung **dư có residual>0 đang đi ra nguồn**; trong mô hình cài đặt, đó là những cạnh gốc đi ra nguồn có dung lượng dương, còn các reverse từ cạnh đi vào nguồn ban đầu bằng 0.

### Giới hạn số học khi bão hòa

Tổng dung lượng của những cạnh đi ra nguồn có thể rất lớn. Nếu dùng `long` để lưu excess, tổng ấy phải vừa long, hoặc phải dùng kiểu số rộng hơn. Mã Java bên dưới **kiểm tra trước** tổng dung lượng dương đi ra nguồn và từ chối đầu vào nếu tổng vượt `Long.MAX_VALUE`. Điều này là một **hợp đồng kỹ thuật** của bản minh họa, không phải hạn chế toán học của max flow.

## 6. Thao tác PUSH: đẩy lượng dư qua cung admissible

Giả sử u active, và có cung dư e=(u,v) thỏa:

**`e.residual>0`, `h(u)=h(v)+1`.**

Đặt:

**`Δ=min(excess(u),e.residual)`.**

Cập nhật:

~~~text
e.residual -= Δ
reverse(e).residual += Δ
excess[u] -= Δ
excess[v] += Δ
if v is a new active intermediate vertex:
    enqueue(v)
~~~

`Δ` luôn dương do u active và cung dư có dung lượng dương. Có hai khả năng:

- **Saturating push:** `Δ=e.residual` trước khi đẩy; cung e bị bão hòa, residual thuận về 0.
- **Non-saturating push:** `Δ=excess(u)` và Δ nhỏ hơn residual trước đó; u hết dư và có thể ngừng discharge.

Push trên **cung dư ngược** hoàn tác một phần luồng đã gửi trước đây; thao tác vẫn hợp lệ vì cặp reverse được liên kết rõ ràng.

### Excess bảo toàn như thế nào?

Với một push u→v:

- u mất Δ đơn vị excess.
- v nhận Δ đơn vị excess.
- Tổng excess trên tất cả đỉnh **không đổi**.

Tại đỉnh trung gian u, ta chọn Δ≤excess[u], nên excess[u] không âm; các đỉnh khác chỉ nhận thêm, nên bất biến preflow tiếp tục đúng.

Nếu v là **đích**, lượng Δ tích vào excess[t] và không bị đẩy tiếp. Nếu v là **nguồn**, excess[s] tăng, nghĩa là đã trả lại một phần lượng preflow khởi tạo.

### Push có thể làm thay đổi cạnh nào trong đồ thị dư?

Một push chỉ thay đổi **cặp cung residual của đúng đối tượng cạnh**: cung đang đẩy giảm Δ, cung reverse tăng Δ. Khi cho phép antiparallel edge, ví dụ có cả cạnh gốc u→v lẫn cạnh gốc v→u, chúng có **hai cặp riêng**; không tự nhập các cung chỉ vì trùng endpoint.

## 7. Thao tác RELABEL: nâng nhãn khi hết cạnh đẩy hợp lệ

Nếu u vẫn active nhưng **không có cung dư admissible**, ta nâng height của u lên:

**`h(u)=1+min{h(v): residual(u→v)>0}`.**

Chỉ xét **cung dư có dung lượng dương**; không đưa cạnh bão hòa vào phép min. Không relabel s hoặc t.

Tại sao công thức đúng?

- Trước relabel, với mọi cung dư u→v, valid labeling đã có `h(u)≤h(v)+1`.
- Sau relabel, ta chọn h(u) bằng 1 cộng height nhỏ nhất trong những hàng xóm còn cung dư. Vì vậy với mọi cung dư u→v:

  `h(u)=1+min h(neighbor)≤h(v)+1`.

- Các cạnh dư **đi vào u** cũng không vi phạm bất biến vì h(u) **tăng**, làm vế phải trong bất đẳng thức của chúng lớn hơn.
- Nếu không có cung admissible khi u còn excess, bước relabel làm xuất hiện ít nhất một cung admissible theo hướng hàng xóm đạt min height.

### Nếu không còn cung dư dương từ u?

Trong một preflow hợp lệ, đỉnh trung gian active phải có ít nhất một cung dư để hoàn trả hoặc chuyển excess, chẳng hạn cạnh ngược của một cung đã mang luồng tới u. Vì vậy ở trạng thái đúng, tập min không rỗng. Mã Java ném ngoại lệ nếu điều này bị phá vỡ — đó là dấu hiệu bug trong residual/excess, không phải một tình huống bình thường để âm thầm bỏ excess.

### Relabel chỉ tăng height

Khi gọi relabel vì không còn cung admissible và vẫn có excess, công thức không làm height giảm; trong thuật toán chuẩn, height tăng. Height có thể vượt n cho các đỉnh cần **trả excess về nguồn**, vì nguồn được cố định height n. Một đỉnh trung gian cần h=n+1 mới có thể đẩy vào nguồn qua cung dư.

Đừng giới hạn height của mọi đỉnh về n−1 như BFS distance ngược từ đích. Điều đó sẽ làm mất khả năng đẩy lượng dư không thể tới t trở lại s.

## 8. DISCHARGE và chiến lược hàng đợi FIFO

`discharge(u)` xử lý một đỉnh trung gian đang active cho tới khi `excess[u]=0`.

Pseudocode:

~~~text
discharge(u):
    while excess[u] > 0:
        if currentEdge[u] == outResidual[u].size:
            relabel(u)
            currentEdge[u] = 0
        else:
            e = outResidual[u][currentEdge[u]]
            if e.residual > 0 and h[u] == h[e.to] + 1:
                push(u, e)
            else:
                currentEdge[u]++
~~~

Trong đó `currentEdge[u]` là **con trỏ cạnh hiện đang xem** (current arc). Nếu cạnh hiện tại không dùng được, chuyển tới cạnh kế. Khi đã quét hết mà u còn excess, relabel rồi bắt đầu xem lại từ đầu vì độ cao của u đã thay đổi.

### FIFO active queue

Chiến lược minh họa:

1. Khi một đỉnh trung gian v nhận excess dương và chưa có trong hàng đợi, đưa v vào cuối hàng.
2. Lấy đỉnh đầu hàng u; bỏ cờ inQueue[u], gọi `discharge(u)`.
3. Khi push làm một đỉnh khác trở thành active, nó được thêm vào cuối hàng.
4. Lặp đến khi hàng đợi rỗng.

Mỗi đỉnh active có nhiều nhất **một bản sao trong queue**, nhờ mảng `inQueue[]`. Không bao giờ enqueue nguồn hay đích; chúng không được discharge.

**Không có đường tăng s→t không phải điều kiện dừng trực tiếp của FIFO.** Thuật toán dừng khi **không còn active intermediate vertex**, tức excess tất cả đỉnh giữa bằng 0. Lúc ấy ta có luồng khả thi và chứng nhận tối ưu từ valid labeling.

### Current arc không phải con trỏ cập nhật flow

`currentEdge[u]` chỉ là vị trí duyệt trên danh sách residual arcs của u. Nó không đổi thứ tự cạnh, không phải ID của cạnh đang mang flow lớn nhất, và không phải “next vertex” trên một đường s→t. Sau khi relabel u, reset về 0; khi một push làm u hết excess, discharge trả về. Khi u trở lại active, con trỏ có thể tiếp tục ở vị trí cũ; vẫn giữ tính đúng dù đôi lúc phải quét lại sau một relabel khác.

## 9. Ví dụ chuẩn CLRS có giá trị luồng 23

Mạng có n=6, nguồn 0, đích 5. Các cạnh gốc:

| Từ | Đến | Dung lượng |
|---:|---:|---:|
| 0 | 1 | 16 |
| 0 | 2 | 13 |
| 1 | 2 | 10 |
| 2 | 1 | 4 |
| 1 | 3 | 12 |
| 2 | 4 | 14 |
| 3 | 2 | 9 |
| 4 | 3 | 7 |
| 3 | 5 | 20 |
| 4 | 5 | 4 |

Đây là mạng có cả cạnh **đối hướng** 1→2 và 2→1, cũng như các đường qua 3,4.

### Khởi tạo

Đặt `h(0)=6`, các height khác 0. Đẩy hết 16 qua 0→1 và 13 qua 0→2. Kết quả:

- `excess(0)=−29`.
- `excess(1)=16`.
- `excess(2)=13`.
- Các đỉnh khác excess=0.

Mỗi lần discharge, đỉnh active đẩy theo cung dư admissible hoặc relabel nếu không có. Khi một phần 29 đơn vị ban đầu không thể đi tới đích, residual ngược cho phép đưa nó trở lại nguồn.

### Kết quả

Thuật toán trả:

- **Giá trị luồng cực đại: 23**.
- Tập đỉnh nguồn đạt được trong **mạng dư cuối**: `S={0,1,2,4}`.
- Phần còn lại: `T={3,5}`.

Các cạnh gốc **từ S sang T** là:

- 1→3 có dung lượng 12.
- 4→3 có dung lượng 7.
- 4→5 có dung lượng 4.

Vì vậy dung lượng cut:

**`c(S,T)=12+7+4=23`**.

Tập các cạnh **từ T trở về S** như 3→2 không được cộng vào dung lượng cut S→T. Sự bằng nhau **flow=23=cutCapacity** vừa cho một cận trên bằng giá trị đạt được, vừa chứng minh tối ưu theo định lý max-flow min-cut.

### Không cần in mọi bước push/relabel

Trình tự đẩy cụ thể phụ thuộc thứ tự cạnh, FIFO queue, current arc và chính sách phá hòa. Hai cài đặt hợp lệ có thể thực hiện số lần push khác nhau nhưng cuối cùng vẫn cho **max flow = 23**. Mã bên dưới cố định thứ tự input để kết quả `sourceSide` tái lập được; chứng nhận cốt lõi là **giá trị luồng bằng dung lượng cut**, không phải một danh sách bước cập nhật phải giống nhau ở mọi solver.

## 10. Định lý max-flow min-cut và chứng minh push–relabel đúng

### 10.1. Bất biến preflow

Ban đầu sau khi bão hòa nguồn, mọi đỉnh trung gian nhận luồng nhưng chưa cần gửi đi, nên `excess(v)≥0`. Trong mỗi push, `Δ≤excess(u)` và các đỉnh khác chỉ nhận thêm. Do đó mọi đỉnh trung gian luôn có excess không âm, đáp ứng điều kiện preflow.

Khi hàng đợi active rỗng và mọi đỉnh trung gian có excess=0, ta đạt **bảo toàn luồng** ở các đỉnh giữa. Các residual pairs tiếp tục đảm bảo ràng buộc dung lượng của từng cạnh gốc. Preflow đã trở thành **luồng khả thi**.

### 10.2. Bất biến valid labeling

Sau khởi tạo nguồn, mọi cung dư dương thỏa `h(u)≤h(v)+1`. Push theo một cung admissible u→v có `h(u)=h(v)+1`; cung ngược v→u trở nên dương nhưng cũng thỏa `h(v)≤h(u)+1`. Mọi cung khác không đổi. Relabel đặt h(u) ở 1 cộng min neighbor height nên duy trì bất biến cho các cung đi ra u, đồng thời làm các bất đẳng thức của cung đi vào u dễ thỏa hơn. Height[s]=n và height[t]=0 không đổi.

### 10.3. Không có đường dư từ nguồn tới đích

Giả sử có một đường dư **đơn** từ s tới t dài k cạnh, `k≤n−1`. Áp dụng valid labeling trên từng cung của đường:

`h(s)≤h(t)+k≤n−1`.

Nhưng `h(s)=n` và `h(t)=0`, mâu thuẫn. Do đó **không còn đường dư s→t**.

### 10.4. Tối ưu

Khi thuật toán kết thúc, luồng khả thi và không có đường tăng s→t trong đồ thị dư. Theo định lý luồng cực đại–lát cắt cực tiểu, đây là **luồng cực đại**.

Ta cũng có thể tự tạo chứng nhận: BFS/DFS trong mạng dư cuối từ s qua các cung residual>0. Gọi tập đạt được là S. Vì t không đạt được, `s∈S`, `t∉S`. Mọi cạnh gốc từ S sang V\S đã **bão hòa** (nếu còn residual thuận dương, phía kia sẽ đạt được), và mọi luồng gốc đi từ V\S về S có giá trị 0 trong cách biểu diễn đúng của lát cắt tối ưu. Do đó:

**`|f|=c(S,V\S)`**.

Mọi luồng khả thi đều ≤ dung lượng của một cut. Luồng tìm được đạt cut này nên là max flow; cut là min cut.

### 10.5. Thuật toán có kết thúc không?

Height của đỉnh trung gian **không giảm** và bị chặn bởi một cận theo n trong thuật toán push–relabel chuẩn; các phép relabel làm height tăng và không thể tiếp diễn vô hạn. Push được chia thành những lần làm bão hòa cung hoặc làm hết excess ở u; số thao tác được phân tích bị chặn đa thức khi dùng các chiến lược discharge hợp lệ. Vì thế không thể chạy vô hạn chỉ bằng cách đẩy qua lại tùy tiện như một thuật toán không có height.

**Lưu ý:** tính đúng của giá trị luồng không phụ thuộc vào việc cụ thể FIFO cho ra bao nhiêu lần relabel; nhưng chứng minh cận thời gian cần đúng phiên bản quản lý active, current arc và chính sách chọn đỉnh.

## 11. Độ phức tạp và các biến thể

Đặt `V=n`, `E=m`, dùng adjacency list và DSU không cần thiết vì đây là bài flow chứ không phải cây khung.

Với **push–relabel tổng quát**, một cận kinh điển là **`O(V²E)`** thời gian ở mức thao tác trên mạng dư; nó có thể được làm tốt hơn bằng các chiến lược chọn đỉnh, cấu trúc dữ liệu và heuristic. Phiên bản **FIFO** với quản lý discharge/current arc như mã minh họa có những phân tích tinh hơn trong tài liệu về preflow–push, thường được báo cáo cận O(V³) cho FIFO selection dưới các giả thiết chuẩn. Để có một cận bảo thủ không nhầm giữa các biến thể, có thể dùng **O(V²E)** cho thuật toán tổng quát, cộng chi phí khởi tạo O(V+E). Đừng áp nguyên cận của **highest-label** hay biến thể dùng **dynamic trees** cho phiên bản FIFO không triển khai chúng.

| Hạng mục | Tác động |
|---|---|
| Xây adjacency list và reverse arcs | O(V+E) thời gian, O(V+E) bộ nhớ |
| Khởi tạo source preflow | O(outdegree(s)) |
| FIFO push, relabel, discharge | Thuộc lớp đa thức; dùng cận bảo thủ O(V²E) |
| BFS trên residual graph để lấy source side | O(V+E) |
| Tính dung lượng cut từ danh sách cạnh gốc | O(E) |
| Dữ liệu height, excess, current arc, queue | O(V) |
| Tổng bộ nhớ gồm residual arcs | **O(V+E)** |

Khi E=0 vẫn phải khởi tạo O(V) bộ nhớ/đỉnh, nên có thể viết tổng thời gian bảo thủ **O(V²E+V+E)** để phản ánh đồ thị không cạnh.

### Heuristic thường dùng

**Highest-label:** thay FIFO bằng ưu tiên đỉnh active có height cao nhất để xử lý. Có thể giúp nhanh trên nhiều mạng, nhưng cần cấu trúc chọn active khác và cận lý thuyết tương ứng.

**Global relabeling:** thỉnh thoảng chạy BFS từ t trên **đồ thị dư đảo chiều** để đặt lại height gần với khoảng cách dư đến t. Phải giữ các ràng buộc hợp lệ, xử lý đúng các đỉnh không còn đường tới t và bảo đảm không thay đổi h(s)=n. Mã ví dụ không triển khai heuristic này để tránh che mất bất biến push/relabel cơ bản.

**Gap heuristic:** nếu một mức height không có đỉnh nào (trong những điều kiện thích hợp), các đỉnh ở các mức cao hơn có thể được đẩy lên mức biểu diễn không còn đường tới t, giúp hoàn trả excess sớm. Cần cài cẩn thận vì xử lý sai gap có thể phá valid labeling.

**Current arc:** giữ vị trí cạnh đã quét ở mỗi đỉnh để tránh xem đi xem lại quá nhiều cạnh vô ích trong một discharge.

Các heuristic giúp **tăng tốc**, nhưng không được làm thay đổi định nghĩa residual/excess hoặc coi một preflow chưa bảo toàn là luồng khả thi.

## 12. Java 17+ hoàn chỉnh: FIFO push–relabel và min cut

Chương trình dưới đây dùng **Java 17 trở lên**, một class chính `PushRelabelDemo` với các lớp/record lồng bên trong. API:

**`solve(n, source, sink, InputEdge...)`** trả:

- `maxFlow`: giá trị luồng cực đại dưới dạng long.
- `sourceSide`: các đỉnh đạt được từ s qua cung dư có dung lượng dương, hiển thị theo ID tăng dần.
- `cutCapacity`: tổng dung lượng các cạnh gốc đi từ sourceSide sang phần còn lại.

Chương trình kiểm tra `maxFlow==cutCapacity` trước khi trả kết quả, tạo một chứng nhận độc lập ở mức trạng thái cuối.

**Hợp đồng input:**

- `n≥2`, `0≤source,sink<n` và `source≠sink`.
- `InputEdge(from,to,capacity)` có endpoint hợp lệ, capacity kiểu long **không âm**.
- Cho phép cạnh song song, cạnh antiparallel, cạnh dung lượng 0. **Self-loop bị bỏ qua khi xây mạng dư** vì không thể cải thiện max flow.
- Để `long[] excess` không tràn, chương trình **từ chối** nếu tổng dung lượng dương của các cạnh gốc **đi ra nguồn và không phải self-loop** vượt `Long.MAX_VALUE`. Với đầu vào hợp đồng này, tổng lượng preflow ban đầu có thể biểu diễn bằng long, tổng excess của các đỉnh ngoài nguồn không vượt quá lượng ấy, và các cung ngược cùng cặp residual không vượt dung lượng cạnh gốc. Những phép cộng nhạy cảm còn dùng `Math.addExact` để phát hiện vi phạm giới hạn.
- Nếu cần xử lý các mạng có tổng dung lượng nguồn vượt 64 bit, phải mở rộng số học cho excess/flow hoặc áp dụng một phiên bản có phân tích giới hạn khác; không tự bỏ các kiểm tra tràn.

**Thiết kế:**

- `Edge.to`, `Edge.reverseIndex` và `Edge.residual` cho mạng dư.
- `height[]`, `excess[]`, `currentEdge[]`, `inQueue[]` và `ArrayDeque<Integer> activeQueue`.
- `enqueue(v)` chỉ nhận các đỉnh v≠source,sink đang có excess dương và chưa nằm trong queue.
- `initializePreflow()` bão hòa cạnh ra nguồn.
- `discharge(u)` lặp admissible push hoặc relabel.
- `sourceSide()` BFS trên residual graph cuối.
- Kết quả in giá trị max flow và một min cut, không cần in ma trận flow của mọi cạnh.

Lưu thành **`PushRelabelDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class PushRelabelDemo {
    private record InputEdge(int from, int to, long capacity) {}

    private record Result(
            long maxFlow, List<Integer> sourceSide, long cutCapacity) {}

    private static final class Edge {
        final int to;
        final int reverseIndex;
        long residual;

        Edge(int to, int reverseIndex, long residual) {
            this.to = to;
            this.reverseIndex = reverseIndex;
            this.residual = residual;
        }
    }

    private static final class Solver {
        private final int n;
        private final int source;
        private final int sink;
        private final List<Edge>[] graph;
        private final int[] height;
        private final int[] currentEdge;
        private final long[] excess;
        private final boolean[] inQueue;
        private final ArrayDeque<Integer> activeQueue =
                new ArrayDeque<>();

        @SuppressWarnings("unchecked")
        Solver(int n, int source, int sink) {
            this.n = n;
            this.source = source;
            this.sink = sink;
            graph = (List<Edge>[]) new List[n];
            for (int v = 0; v < n; v++) {
                graph[v] = new ArrayList<>();
            }
            height = new int[n];
            currentEdge = new int[n];
            excess = new long[n];
            inQueue = new boolean[n];
        }

        void addEdge(int u, int v, long capacity) {
            // A self-loop cannot cross an s-t cut;
            // zero-capacity edges do not affect max flow.
            if (u == v || capacity == 0L) {
                return;
            }

            // Record indices BEFORE adding either residual arc.
            Edge forward =
                    new Edge(v, graph[v].size(), capacity);
            Edge reverse = new Edge(u, graph[u].size(), 0L);
            graph[u].add(forward);
            graph[v].add(reverse);
        }

        private void enqueue(int v) {
            if (v != source && v != sink
                    && excess[v] > 0 && !inQueue[v]) {
                inQueue[v] = true;
                activeQueue.addLast(v);
            }
        }

        void initializePreflow() {
            height[source] = n;

            // Reverse arcs of ORIGINAL incoming edges to source
            // initially have zero residual and are skipped.
            for (Edge edge : graph[source]) {
                if (edge.residual == 0L) {
                    continue;
                }
                long delta = edge.residual;
                edge.residual = 0L;
                Edge reverse = graph[edge.to]
                        .get(edge.reverseIndex);
                reverse.residual =
                        Math.addExact(reverse.residual, delta);

                excess[source] =
                        Math.subtractExact(excess[source], delta);
                excess[edge.to] =
                        Math.addExact(excess[edge.to], delta);
                enqueue(edge.to);
            }
        }

        private void push(int u, Edge edge) {
            long delta = Math.min(excess[u], edge.residual);
            if (delta <= 0) {
                throw new IllegalStateException("Nonpositive push");
            }

            edge.residual -= delta;
            Edge reverse = graph[edge.to]
                    .get(edge.reverseIndex);
            reverse.residual =
                    Math.addExact(reverse.residual, delta);

            excess[u] -= delta;
            excess[edge.to] =
                    Math.addExact(excess[edge.to], delta);
            enqueue(edge.to);
        }

        private void relabel(int u) {
            int minHeight = Integer.MAX_VALUE;
            for (Edge edge : graph[u]) {
                if (edge.residual > 0) {
                    minHeight = Math.min(
                            minHeight, height[edge.to]);
                }
            }
            if (minHeight == Integer.MAX_VALUE) {
                throw new IllegalStateException(
                        "Active vertex has no residual exit");
            }
            height[u] = minHeight + 1;
        }

        private void discharge(int u) {
            while (excess[u] > 0) {
                if (currentEdge[u] == graph[u].size()) {
                    relabel(u);
                    currentEdge[u] = 0;
                } else {
                    Edge edge = graph[u].get(currentEdge[u]);
                    if (edge.residual > 0
                            && height[u] == height[edge.to] + 1) {
                        push(u, edge);
                    } else {
                        currentEdge[u]++;
                    }
                }
            }
        }

        void run() {
            initializePreflow();
            while (!activeQueue.isEmpty()) {
                int u = activeQueue.removeFirst();
                inQueue[u] = false;
                discharge(u);
            }
        }

        List<Integer> sourceSide() {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[source] = true;
            queue.addLast(source);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Edge edge : graph[u]) {
                    if (edge.residual > 0 && !seen[edge.to]) {
                        seen[edge.to] = true;
                        queue.addLast(edge.to);
                    }
                }
            }

            List<Integer> vertices = new ArrayList<>();
            for (int v = 0; v < n; v++) {
                if (seen[v]) {
                    vertices.add(v);
                }
            }
            return List.copyOf(vertices);
        }

        long flowValue() {
            return excess[sink];
        }
    }

    static Result solve(
            int n, int source, int sink, InputEdge... input) {
        if (n < 2 || source < 0 || source >= n
                || sink < 0 || sink >= n || source == sink
                || input == null) {
            throw new IllegalArgumentException(
                    "Invalid vertices/source/sink");
        }

        Solver solver = new Solver(n, source, sink);
        long sourceCapacityBound = 0L;
        for (InputEdge edge : input) {
            if (edge == null
                    || edge.from() < 0 || edge.from() >= n
                    || edge.to() < 0 || edge.to() >= n
                    || edge.capacity() < 0) {
                throw new IllegalArgumentException(
                        "Invalid directed capacity edge");
            }

            if (edge.from() == source
                    && edge.to() != source
                    && edge.capacity() > 0) {
                try {
                    sourceCapacityBound = Math.addExact(
                            sourceCapacityBound, edge.capacity());
                } catch (ArithmeticException exception) {
                    throw new IllegalArgumentException(
                            "Total source capacity exceeds long",
                            exception);
                }
            }
            solver.addEdge(
                    edge.from(), edge.to(), edge.capacity());
        }

        solver.run();
        List<Integer> sourceSide = solver.sourceSide();
        boolean[] inSourceSide = new boolean[n];
        for (int v : sourceSide) {
            inSourceSide[v] = true;
        }

        long cutCapacity = 0L;
        for (InputEdge edge : input) {
            if (inSourceSide[edge.from()]
                    && !inSourceSide[edge.to()]) {
                cutCapacity = Math.addExact(
                        cutCapacity, edge.capacity());
            }
        }

        long maxFlow = solver.flowValue();
        if (maxFlow != cutCapacity) {
            throw new IllegalStateException(
                    "Max-flow / min-cut certificate mismatch");
        }
        return new Result(maxFlow, sourceSide, cutCapacity);
    }

    private static void show(
            String name, int n, int source,
            int sink, InputEdge... edges) {
        Result result = solve(n, source, sink, edges);
        System.out.println(
                name + ": flow=" + result.maxFlow()
                + ", sourceSide=" + result.sourceSide()
                + ", cutCapacity=" + result.cutCapacity());
    }

    public static void main(String[] args) {
        show("CLRS", 6, 0, 5,
                new InputEdge(0, 1, 16),
                new InputEdge(0, 2, 13),
                new InputEdge(1, 2, 10),
                new InputEdge(2, 1, 4),
                new InputEdge(1, 3, 12),
                new InputEdge(2, 4, 14),
                new InputEdge(3, 2, 9),
                new InputEdge(4, 3, 7),
                new InputEdge(3, 5, 20),
                new InputEdge(4, 5, 4));

        show("Parallel", 3, 0, 2,
                new InputEdge(0, 1, 5),
                new InputEdge(0, 1, 4),
                new InputEdge(1, 2, 8));

        show("Antiparallel", 3, 0, 2,
                new InputEdge(0, 1, 5),
                new InputEdge(1, 0, 4),
                new InputEdge(1, 2, 3));

        show("Disconnected", 4, 0, 3,
                new InputEdge(0, 1, 7),
                new InputEdge(2, 3, 5));

        show("Zero capacity", 3, 0, 2,
                new InputEdge(0, 1, 0),
                new InputEdge(1, 2, 6));

        show("Self loops", 3, 0, 2,
                new InputEdge(0, 0, 100),
                new InputEdge(0, 1, 5),
                new InputEdge(1, 1, 7),
                new InputEdge(1, 2, 3));

        show("Two paths", 4, 0, 3,
                new InputEdge(0, 1, 10),
                new InputEdge(0, 2, 5),
                new InputEdge(1, 2, 15),
                new InputEdge(1, 3, 10),
                new InputEdge(2, 3, 10));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac PushRelabelDemo.java
java PushRelabelDemo
~~~

**Kết quả chuẩn của chương trình:**

~~~text
CLRS: flow=23, sourceSide=[0, 1, 2, 4], cutCapacity=23
Parallel: flow=8, sourceSide=[0, 1], cutCapacity=8
Antiparallel: flow=3, sourceSide=[0, 1], cutCapacity=3
Disconnected: flow=0, sourceSide=[0, 1], cutCapacity=0
Zero capacity: flow=0, sourceSide=[0], cutCapacity=0
Self loops: flow=3, sourceSide=[0, 1], cutCapacity=3
Two paths: flow=15, sourceSide=[0], cutCapacity=15
~~~

### Giải thích output

**CLRS:** max flow 23 và min cut `S={0,1,2,4}` có capacity 23. Đúng bằng giá trị chuẩn cho mạng này.

**Parallel:** hai cạnh 0→1 có tổng dung lượng 9, nhưng 1→2 chỉ 8. Max flow 8; trong mạng dư còn khả năng 0→1 nhưng không còn đường qua 1→2. Cut S={0,1}, dung lượng 8.

**Antiparallel:** cạnh gốc 1→0 dung lượng 4 **không** làm tăng luồng có thể tới 2; cổ chai 1→2 chỉ 3. Max flow 3. Cạnh thực 1→0 được giữ như một cặp residual khác, không bị nhầm với reverse của 0→1.

**Disconnected:** có đường 0→1 nhưng không có đường từ vùng {0,1} tới đích 3. Lượng preflow đưa vào 1 cuối cùng được trả về nguồn, max flow 0, source side {0,1}.

**Zero capacity:** cạnh 0→1 dung lượng 0 không truyền được luồng; đích không đạt từ nguồn trong mạng dung lượng dương, max flow 0. Source side chỉ có {0}.

**Self loops:** các cạnh 0→0,1→1 không thể góp phần vào luồng s→t; bỏ chúng vẫn cho max flow 3 qua 0→1→2.

**Two paths:** nguồn có hai cạnh dung lượng 10 và 5 nên `|f|≤15`; có thể gửi tổng 15 đến đích theo hai nhánh. Max flow 15 và cut `S={0}` có dung lượng 10+5=15.

### Tại sao chương trình đếm cut theo cạnh gốc?

Đồ thị dư chứa cả cạnh gốc đã thay dung lượng lẫn các cung reverse nhân tạo. Nếu cộng nhầm residual capacities hoặc cộng cả cạnh từ T về S, ta không còn định nghĩa dung lượng cut. Chương trình tính cut bằng **danh sách InputEdge ban đầu**:

**`cutCapacity=Σ capacity(e)`** với **`e.from∈S` và `e.to∉S`.

Với đa cạnh, từng cạnh gốc băng qua cut đều được cộng riêng. Self-loop không thể băng qua cut; cạnh dung lượng 0 cộng 0.

### Vì sao kiểm tra sourceCapacityBound trước khi xây đầy đủ?

Trong cài đặt `long`, bước khởi tạo có thể làm `excess[source]` bằng **âm tổng các dung lượng rời nguồn**; nếu tổng vượt 2⁶³−1 sẽ tràn. Chương trình kiểm tra và từ chối **trước khi chạy solver**. Đây là một hạn chế rõ ràng và an toàn của phiên bản hướng dẫn; bài toán max flow toán học không bị giới hạn như vậy.

### Vì sao không dùng DFS đệ quy?

Các thao tác push/relabel và BFS sourceSide đều dùng vòng lặp/hàng đợi. Không có DFS đệ quy trên đường mạng có thể rất sâu, tránh loại `StackOverflowError` do chiều sâu đệ quy tuyến tính. Đổi lại, thuật toán có thể thực hiện nhiều vòng discharge, nên vẫn phải tính độ phức tạp và giới hạn kích thước mạng phù hợp.

## 13. Đúng trên các trường hợp biên nào?

| Tình huống | Hành vi chính xác |
|---|---|
| Không có cạnh | Max flow 0, source side có ít nhất s |
| t không đạt từ s | Max flow 0, có thể hoàn trả excess về s |
| Chỉ có một đường dung lượng dương | Max flow bằng dung lượng nhỏ nhất trên đường |
| Nhiều cạnh song song | Giữ từng cặp residual riêng, cộng dung lượng phù hợp |
| Hai cạnh đối hướng cùng endpoint | Mỗi cạnh gốc tạo một cặp residual khác nhau |
| Self-loop | Bỏ qua khi xây residual, không đổi max flow/cut |
| Dung lượng 0 | Bỏ qua trong residual; vẫn có thể xuất hiện trong dữ liệu gốc |
| s có cạnh đi vào | Không bão hòa cạnh ngược nhân tạo có residual ban đầu 0 |
| Có cạnh âm | Không hợp lệ: capacities phải không âm |
| s=t | Không thuộc hợp đồng mã; bị từ chối |
| n<2 | Không thuộc hợp đồng mã; bị từ chối |
| InputEdge có endpoint ngoài [0,n−1] | Bị từ chối |
| Một nguồn có nhiều cạnh ra rất lớn | Tổng phải vừa long hoặc chọn kiểu rộng hơn |
| Mạng có nhiều min cut | Trả một source side hợp lệ trong residual cuối |
| Nhiều luồng max khác nhau | Giá trị giống nhau; phân phối dòng có thể khác |
| Chỉ hỏi giá trị luồng | Có thể bỏ bước xuất min cut, nhưng nên giữ trong kiểm thử |

### Đồ thị vô hướng và luồng hai chiều

Nếu bài cho một cạnh **vô hướng** dung lượng c và cho phép truyền luồng theo cả hai chiều theo một mô hình nhất định, phải chuyển mô hình sang các cung có hướng **đúng với định nghĩa dung lượng chung hay riêng**. Không được mặc định chỉ cần thêm hai InputEdge đối hướng là luôn giống mọi định nghĩa “cạnh vô hướng có dung lượng c”. Với capacity dùng chung, cần mô hình hóa/giải thích đúng ràng buộc gốc. Bản Java nhận **mạng có hướng**.

### Nguồn, đích nằm trong đồ thị có cạnh đối hướng

Trong residual graph, một reverse arc có thể đi ngược hướng cạnh gốc; điều đó **không** có nghĩa ta đã đổi đồ thị đầu vào. Chỉ là phép hoàn tác một phần luồng. Việc cập nhật đúng cặp reverseIndex giữ nguyên ý nghĩa mọi cạnh ngay cả khi nguồn có cạnh đi vào và đích có cạnh đi ra.

## 14. Kiểm thử độc lập: Edmonds–Karp và liệt kê min cut

Một bài max flow có thể có nhiều phân phối luồng đúng, nên so sánh **cạnh nào mang bao nhiêu luồng** giữa hai thuật toán không phải cách kiểm thử tốt. Thay vào đó, so:

- **Giá trị max flow**.
- **Dung lượng min cut**.
- **Bảo toàn** tại các đỉnh trung gian khi kết thúc.
- **Không có đường dư s→t**.
- **Không có residual âm** hoặc reverse pair bị hỏng.

### 14.1. Oracle Edmonds–Karp

Edmonds–Karp là biến thể Ford–Fulkerson dùng **BFS tìm đường tăng** s→t trong residual graph. Mỗi lần:

1. BFS tìm đường có tất cả cung dư dương.
2. Lấy `bottleneck=min residual` trên đường.
3. Giảm residual của các cung thuận theo đường, tăng residual reverse.
4. Cộng bottleneck vào tổng luồng.

Khi BFS không còn đường s→t, kết quả là max flow. Edmonds–Karp có cận **O(VE²)** trên mạng có hướng theo mô hình số học thông thường. Nó khác hẳn cơ chế preflow/excess/height của push–relabel, nên thích hợp làm **oracle độc lập** khi dữ liệu nhỏ.

### 14.2. Oracle bằng liệt kê mọi s–t cut

Với n≤8, có thể xét tất cả tập con `S⊆V` thỏa **`s∈S`, `t∉S`**. Có đúng `2^(n−2)` cách chọn các đỉnh còn lại.

Cho mỗi S, tính:

**`c(S,V\S)=Σ_{(u,v)∈E, u∈S, v∉S}c(u,v)`.**

Lấy min qua các cut; theo định lý max-flow min-cut, giá trị này phải bằng max flow. Oracle này hoàn toàn **không cần giả lập các thao tác push/relabel**, nên đặc biệt hữu ích để bắt lỗi cắt cạnh đối hướng hoặc bỏ quên cạnh song song.

### 14.3. Test ngẫu nhiên

Sinh n từ 2..8, chọn s,t khác nhau, sinh m từ 0..24 cạnh có hướng và dung lượng nguyên 0..14. Cho phép:

- Cạnh lặp cùng endpoint.
- Cạnh đối hướng.
- Self-loop.
- Dung lượng 0.
- Nguồn hoặc đích có nhiều cạnh vào/ra.
- Đích không đạt được.
- Nhiều cut cùng dung lượng tối ưu.

Với mỗi mạng, kiểm tra:

1. Push–relabel trả giá trị bằng Edmonds–Karp.
2. Giá trị ấy bằng **min trên mọi cut** liệt kê.
3. Source side thu từ residual cuối chứa s, không chứa t.
4. Dung lượng cut của source side đúng bằng max flow.
5. Mọi đỉnh v≠s,t có excess=0 khi queue rỗng.
6. Mọi residual ≥0 và hai cung của mỗi cặp cập nhật nhất quán.
7. Đổi thứ tự cạnh input không đổi **giá trị tối ưu**, dù số lần push và source side cụ thể có thể khác trong mạng nhiều min cut.

Cũng kiểm tra những mạng chỉ có một nguồn đi tới một đỉnh không có đường về t: push–relabel phải có cách **đẩy dư về nguồn**, chứ không kẹt vĩnh viễn ở đỉnh active.

### 14.4. Kiểm tra nhãn ở thời điểm chạy

Để tìm bug khó, trong phiên bản debug có thể sau mỗi push/relabel kiểm tra:

- `h(s)=n`, `h(t)=0`.
- Mọi cung residual>0 có `h(u)≤h(v)+1`.
- Excess ở đỉnh trung gian không âm.
- Nếu `currentEdge[u]` ở cuối mà u còn excess, relabel tìm được hàng xóm có residual>0.
- Khi kết thúc, mọi excess trung gian bằng 0.

Việc kiểm tra toàn mạng sau **mỗi** thao tác làm chạy test chậm hơn, nên dùng cho đồ thị nhỏ hoặc debug, không bật vô điều kiện trong solver sản xuất.

## 15. Những lỗi rất thường gặp

1. **Nhầm preflow với luồng khả thi ở mọi thời điểm:** excess tại đỉnh trung gian có thể dương trong lúc chạy.
2. **Lấy tổng dung lượng nguồn đã bão hòa làm max flow:** một phần excess có thể phải quay về nguồn.
3. **Không xây reverse arc:** không thể hoàn tác flow, dễ mắc kẹt ở phương án chưa tối ưu.
4. **Dùng chỉ số reverse sai:** cập nhật nhầm cạnh, nhất là khi có parallel/antiparallel edges.
5. **Gộp mọi cạnh giữa cùng hai đỉnh không xem xét mô hình:** làm sai khả năng ghi luồng riêng, ID cạnh và chứng cứ.
6. **Nhầm reverse residual với một cạnh gốc đối hướng:** hai đối tượng riêng có ý nghĩa khác nhau.
7. **Cho phép push qua residual=0:** dẫn đến Δ=0 và vòng lặp vô ích.
8. **Đẩy không kiểm tra `h(u)=h(v)+1`:** phá valid labeling và chứng minh kết thúc/tối ưu.
9. **Relabel dựa trên cả cạnh dư bão hòa:** chọn min height không còn cung đẩy thật, có thể đứng yên.
10. **Relabel luôn bằng h(u)+1:** không nhất thiết tạo cung admissible; công thức chuẩn là min height của hàng xóm dư +1.
11. **Cho phép relabel nguồn hoặc đích:** phá nhãn cố định dùng trong chứng minh.
12. **Đặt h(s)=0 khi khởi tạo:** các bất biến chuẩn của preflow–push không còn đúng.
13. **Quên đẩy luồng ngược về s:** có thể kết thúc sai hoặc kẹt ở một đỉnh không tới t.
14. **Xem queue rỗng khi chưa enqueue một active mới:** preflow chưa khả thi nhưng thuật toán dừng.
15. **Đưa cùng đỉnh active vào queue nhiều lần mà không quản lý:** làm phát sinh nhiều discharge dư thừa và khó lý giải trạng thái.
16. **Quên reset currentEdge sau relabel:** không xét lại những cung vừa trở nên admissible.
17. **Quên giảm excess[u] hoặc tăng excess[v] khi push:** phá bảo toàn tổng và có thể trả flow > cut.
18. **Kiểm tra luồng cực đại chỉ bằng height mà chưa xóa hết excess ở giữa:** chưa có luồng khả thi.
19. **Lấy min cut từ cạnh gốc còn capacity dương thay vì residual graph:** tập reachable có thể sai.
20. **Tính dung lượng cut bằng các cung residual hoặc đếm cả T→S:** không đúng định nghĩa min cut.
21. **Không xét cả cạnh song song trong cut capacity:** chứng nhận flow=cut có thể bị lệch.
22. **Chấp nhận capacity âm:** phá toàn bộ mô hình và bất biến.
23. **Dùng long mà không kiểm tra tổng dung lượng nguồn và phép cộng:** tràn số tạo residual/excess âm giả.
24. **Cho rằng nguồn/đích luôn không có cạnh vào/ra đối hướng:** mạng thực có thể chứa các cạnh như vậy.
25. **Tuyên bố FIFO có cùng số bước như highest-label:** lịch xử lý active khác nhau, kết quả trung gian khác nhau.
26. **Quên xử lý s=t hoặc n=1 trong API:** bản minh họa chủ động từ chối để tránh định nghĩa luồng s→s không rõ.
27. **Bỏ mọi cạnh dung lượng 0 khỏi cut bằng cách nhầm chúng là lỗi:** chúng hợp lệ, chỉ không đóng góp.
28. **Cho rằng residual reachability source side luôn duy nhất:** min cut có thể không duy nhất, dù giá trị tối ưu là một.
29. **Không test disconnected sink:** lượng dư cần được hoàn trả, không phải tự biến mất.
30. **Nghĩ push–relabel là shortest-path algorithm:** height là nhãn để hướng push, không phải output đường đi ngắn nhất.

## 16. Checklist thiết kế và nộp bài

- Mạng là **có hướng**, dung lượng không âm, source và sink khác nhau?
- Cạnh gốc và cung residual được biểu diễn bằng **cặp liên kết reverseIndex chính xác**?
- Có phân biệt cạnh gốc ngược chiều với reverse residual của cạnh khác?
- Mỗi push có `Δ=min(excess[u],residual)` và chỉ đi qua cung admissible?
- Mọi cập nhật dư có đồng thời giảm cung đang push, tăng cung reverse, trừ excess[u], cộng excess[v]?
- Trước discharge, u có phải active intermediate và có còn excess?
- Relabel chỉ xảy ra khi quét hết cạnh nhưng còn excess, dùng `1+min height` của hàng xóm có residual>0?
- Height nguồn là n, height đích là 0, và valid labeling có được bảo toàn?
- Khi một đỉnh trở thành active, có đưa nó vào queue đúng một lần?
- Sau discharge, excess[u] có bằng 0, và khi queue rỗng mọi intermediate excess đều 0?
- Có xử lý hoàn trả excess về nguồn qua reverse residual khi t không đạt?
- Nếu dùng long, tổng dung lượng ra nguồn và mọi tổng trung gian có được kiểm soát tràn?
- Min cut có được lấy bằng BFS/DFS **trên residual graph cuối từ s**, chỉ qua residual>0?
- Cut capacity có tính **cạnh gốc từ S sang T**, không tính cung ngược residual hoặc cạnh T→S?
- Giá trị maxFlow có bằng cutCapacity không?
- Đã thử CLRS=23, parallel edges, antiparallel edges, self-loop, zero capacity và disconnected sink?
- Đã so max flow với **Edmonds–Karp** hoặc **liệt kê s–t cuts** trên các đồ thị nhỏ chưa?
- Đã nêu rõ đây là **FIFO push–relabel**, khác các biến thể highest-label/global relabel/gap?
- Có phân biệt **giá trị luồng duy nhất** với **phân phối cạnh/min cut có thể không duy nhất** không?

**Kết luận:** push–relabel đạt max flow bằng các thao tác **địa phương** trên mạng dư: bão hòa cạnh nguồn để tạo **preflow**, đẩy excess dọc các cung thỏa `h(u)=h(v)+1` và relabel khi không có cung admissible. Khi mọi đỉnh trung gian hết excess, ta có luồng khả thi; nhãn nguồn n và đích 0 cùng valid labeling chứng minh không còn đường tăng. Một phép BFS trên residual graph cuối cho **min cut**, có dung lượng bằng đúng giá trị max flow. Cấu trúc reverse arcs chính xác, hàng đợi active và kiểm soát số học là những chi tiết cài đặt cần đặc biệt chú ý.