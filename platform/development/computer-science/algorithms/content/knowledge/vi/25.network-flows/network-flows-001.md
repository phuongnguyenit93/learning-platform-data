# Mạng luồng, sức chứa và điều kiện bảo toàn

**Mạng luồng** (*flow network*) là một **đồ thị có hướng** có sức chứa trên các cạnh. Ta muốn vận chuyển một lượng tài nguyên — nước, hàng hóa, dữ liệu hoặc đơn vị công việc — từ một **nguồn s** (*source*) tới một **đích t** (*sink*) mà không vượt quá khả năng vận chuyển của từng cạnh. Điều quan trọng là: ở mọi đỉnh trung gian, tổng luồng **đi vào phải bằng tổng luồng đi ra**. Một gán giá trị cho các cạnh chỉ là **luồng hợp lệ** (*feasible flow*) nếu đồng thời thỏa **giới hạn sức chứa** và **bảo toàn luồng**.

Đây là nền tảng để học các thuật toán **Ford–Fulkerson, Edmonds–Karp, Dinic, min-cut, ghép cặp hai phía** và bài toán vận chuyển có ràng buộc. Bài thuộc nhóm **Luồng mạng** trong Computer Science Algorithms và trình bày kỹ ý nghĩa của luồng, những công thức kiểm tra, mạng dư với cạnh ngược, cách tăng luồng và một chương trình Java 17 kiểm chứng tính đúng.

## 1. Mô hình toán học

Một mạng luồng tiêu chuẩn gồm:

- Tập đỉnh `V` và tập **cạnh có hướng** `E`.
- Hai đỉnh phân biệt: **nguồn s** và **đích t**, `s\ne t`.
- **Sức chứa** `c(e)\ge0` cho mỗi cạnh `e\in E`. Sức chứa cho biết **giới hạn trên** của lượng tài nguyên đi theo cạnh đó.
- **Luồng** `f(e)` trên mỗi cạnh, thể hiện lượng tài nguyên **thực sự được gửi** qua cạnh.

Trong bài và chương trình, `c(e)` là **số nguyên không âm kiểu long**; các thuật toán dựa trên mạng dư vẫn áp dụng cho một số mô hình sức chứa thực với điều kiện số học và dừng thuật toán phải được xem xét phù hợp. Với sức chứa nguyên, mọi bước tăng theo bottleneck nguyên và nghiệm tối ưu có thể nhận **giá trị nguyên**.

**Sức chứa khác luồng.** Cạnh `u\to v` có sức chứa 10 không có nghĩa đã gửi 10 đơn vị: có thể gửi 0, 3 hoặc 10, miễn toàn mạng thỏa các ràng buộc.

### Hướng cạnh có ý nghĩa

Nếu dữ liệu có cạnh `u\to v`, ta được gửi luồng **theo chiều u sang v**. Không được tự suy diễn một cạnh thật `v\to u` có sức chứa tương đương. Trong thuật toán sẽ có một **cạnh ngược của mạng dư** dùng để **hủy luồng đã gửi**, nhưng cạnh đó **không phải** một tuyến vận chuyển mới được cấp sức chứa thật trong dữ liệu đầu vào.

Nếu đầu vào có cả `u\to v` và `v\to u`, đó là **hai cạnh thật độc lập**, mỗi cạnh có sức chứa và luồng riêng. Nếu có nhiều cạnh song song `u\to v`, cũng phải xử lý chúng như các cạnh riêng biệt, hoặc gộp sức chứa một cách có chủ đích và an toàn số học.

## 2. Hai điều kiện của một luồng hợp lệ

Ta dùng mô hình **luồng theo cạnh** `f(e)` cho mỗi cạnh thật e. Một mạng có thể có cạnh song song, nên ký hiệu tổng phải hiểu là **cộng theo từng cạnh**, không đơn thuần theo từng cặp đỉnh.

### Điều kiện 1 — Giới hạn sức chứa (capacity constraint)

Với mọi cạnh thật `e`:

\[
\boxed{0\le f(e)\le c(e).}
\]

Ví dụ cạnh `1\to3` có `c=5`:
- `f=0` hợp lệ theo sức chứa, dù toàn mạng còn phải kiểm tra bảo toàn.
- `f=4` hợp lệ theo sức chứa.
- `f=5` là **bão hòa** (*saturated*).
- `f=6` vi phạm sức chứa.
- `f=-1` vi phạm mô hình luồng theo cạnh thật.

Nếu cạnh `c=0` thì bắt buộc `f=0`; cạnh này không thể vận chuyển tài nguyên. Nếu có self-loop `u\to u`, lượng vào và ra tại cùng đỉnh bằng nhau; nó không góp phần tăng luồng ròng từ s tới t. Chương trình mẫu chấp nhận self-loop nhưng BFS mạng dư không dùng nó để tiến sang một đỉnh khác.

### Điều kiện 2 — Bảo toàn tại đỉnh trung gian (flow conservation)

Với mọi đỉnh `v\notin\{s,t\}`:

\[
\boxed{\sum_{e:\,to(e)=v} f(e)
=\sum_{e:\,from(e)=v} f(e).}
\]

Tức **tổng luồng vào = tổng luồng ra**. Một đỉnh trung gian không được tự sinh thêm hoặc làm mất tài nguyên.

Ví dụ ở đỉnh 3:
- Nhận 2 đơn vị từ 1 và 3 đơn vị từ 2, tổng vào 5.
- Phải gửi ra tổng 5, chẳng hạn 4 sang 4 và 1 sang t.
- Nếu chỉ gửi ra 4 thì cấu hình **không phải luồng hợp lệ**, dù không cạnh nào vượt sức chứa.

**Bảo toàn không có nghĩa các cạnh riêng lẻ đều mang lượng bằng nhau.** Một đỉnh có thể tách dòng hoặc gộp dòng. Chỉ **tổng** vào và **tổng** ra phải bằng nhau.

### Hai đỉnh đặc biệt s và t

Nguồn s được phép có **luồng ròng đi ra**; đích t được phép có **luồng ròng đi vào**. Không nên chỉ lấy tổng luồng đi ra khỏi s khi s có cạnh đi vào thật, hoặc chỉ lấy tổng luồng đi vào t khi t có cạnh đi ra thật.

Định nghĩa **giá trị luồng**:

\[
\boxed{|f|=
\sum_{e:\,from(e)=s}f(e)
-\sum_{e:\,to(e)=s}f(e).}
\]

Đồng thời, từ bảo toàn ở các đỉnh khác:

\[
\boxed{|f|=
\sum_{e:\,to(e)=t}f(e)
-\sum_{e:\,from(e)=t}f(e).}
\]

Để hiểu công thức, định nghĩa `balance[v] = outflow(v)-inflow(v)`. Khi đó:

| Đỉnh | Điều kiện |
| --- | --- |
| Nguồn s | `balance[s]=|f|` |
| Đích t | `balance[t]=−|f|` |
| Mọi đỉnh khác | `balance[v]=0` |

Ta thường quan tâm luồng từ s tới t có `|f|\ge0`. Trạng thái ban đầu **tất cả f(e)=0** luôn là một luồng hợp lệ, có giá trị 0.

### Vì sao luồng ròng ở s bằng luồng ròng ở t?

Trong tổng:

\[
\sum_{v\in V}\big(outflow(v)-inflow(v)\big),
\]

mỗi cạnh e đóng góp một lần `+f(e)` ở đầu đi và một lần `−f(e)` ở đầu đến, nên tổng bằng 0. Tất cả đỉnh trung gian có balance 0, suy ra `balance[s]+balance[t]=0`, tức hai công thức giá trị luồng bằng nhau.

Lập luận này vẫn đúng khi mạng có cạnh song song, cạnh đi ngược chiều nguồn/đích, hoặc self-loop.

## 3. Phân biệt “có thể đi qua” và “luồng hợp lệ”

Một người mới học có thể chỉ kiểm tra `0\le f(e)\le c(e)` trên từng cạnh rồi kết luận đúng. Điều này **chưa đủ** vì các cạnh còn bị ràng buộc **qua đỉnh trung gian**.

Ví dụ:

~~~text
s=0 --(capacity 5)--> 1 --(capacity 3)--> t=2
~~~

Nếu đặt `f(0\to1)=5` và `f(1\to2)=3`:
- Cả hai cạnh không vượt sức chứa.
- Nhưng đỉnh 1 nhận vào 5, chỉ gửi ra 3: **vi phạm bảo toàn**.

Một luồng hợp lệ có thể đặt **cả hai cạnh cùng bằng 3** và có giá trị 3. Tổng lượng có thể gửi từ s đến t bị giới hạn bởi cạnh hẹp nhất trên đường.

### Đường đi và nút thắt (bottleneck)

Nếu có một đường tăng `P` mà mọi cạnh dư trên P còn sức chứa, ta chỉ có thể tăng luồng theo đường với lượng:

\[
\Delta=\min_{e\in P}c_f(e).
\]

`\Delta` gọi là **bottleneck**. Nếu trên đường có sức chứa dư [7,4,5], bottleneck bằng 4; không thể tăng 5 hoặc 7 vì cạnh thứ hai chỉ còn 4.

Điều kiện bảo toàn giải thích vì sao ta tăng **cùng một lượng \Delta** dọc theo toàn đường từ s tới t: ở mỗi đỉnh trung gian trên đường, một lượng đi vào được bù bởi đúng lượng đi ra.

## 4. Bài toán luồng cực đại (maximum flow)

Sau khi hiểu một luồng hợp lệ, ta mới hỏi bài toán tối ưu:

> Trong các gán luồng thỏa sức chứa và bảo toàn, tìm một luồng có **giá trị |f| lớn nhất** từ s tới t.

**Một luồng hợp lệ chưa chắc là cực đại.** Chẳng hạn lúc bắt đầu f=0 luôn hợp lệ; nếu có đường từ s tới t còn sức chứa dương, ta có thể tăng giá trị.

Trong mạng đơn `s\to1` sức chứa 5, `1\to t` sức chứa 3:
- Luồng 0 hợp lệ.
- Luồng 2 hợp lệ nhưng **chưa cực đại**.
- Luồng 3 hợp lệ và **cực đại**.

Câu hỏi “tối đa bao nhiêu?” khác câu hỏi “mỗi cạnh được phép chở bao nhiêu?”; chỉ có sức chứa mà không có cấu hình luồng thì chưa thể kiểm tra bảo toàn.

### Có thể có luồng tuần hoàn

Luồng khả thi trong mạng tổng quát có thể bao gồm những vòng tuần hoàn (**circulation**) với các đỉnh trung gian vẫn bảo toàn. Những luồng tuần hoàn không nhất thiết tăng giá trị s–t; chẳng hạn gửi 1 đơn vị quanh vòng a→b→c→a làm balance cả ba đỉnh bằng 0.

Thuật toán đường tăng bắt đầu từ luồng 0 thường không cần chủ động tạo vòng luồng; nhưng khi định nghĩa tập luồng khả thi, không được tự cho rằng mọi cạnh mang luồng dương đều thuộc một đường đơn từ s tới t.

## 5. Mạng dư (residual network) — khả năng điều chỉnh luồng

Đây là khái niệm quyết định để vừa giữ điều kiện hợp lệ vừa có thể **điều chỉnh một quyết định cũ**.

Với mỗi **cạnh thật** e = u→v sức chứa c và luồng hiện tại f, tạo hai **cạnh dư**:

1. **Chiều thuận u→v**, sức chứa dư:

\[
c_f^{forward}(u,v)=c-f.
\]

   Đây là lượng tối đa còn có thể **tăng thêm** trên cạnh thật.

2. **Chiều ngược v→u**, sức chứa dư:

\[
c_f^{reverse}(v,u)=f.
\]

   Đây là lượng tối đa có thể **hủy bớt** luồng đã gửi trên cạnh thật u→v.

**Ban đầu f=0:** residual thuận bằng c, residual ngược bằng 0. Khi tăng một lượng \Delta qua cạnh dư thuận, luồng thật f tăng \Delta; khi tăng qua cạnh dư ngược, luồng thật f giảm \Delta.

### Hai phép cập nhật cặp cạnh dư

Giả sử một cạnh dư `e` được dùng trên đường tăng với lượng \Delta:

~~~text
e.residual -= delta
e.reverse.residual += delta
~~~

Điều này áp dụng cho cả cạnh dư thuận **và** cạnh dư ngược. Đặc biệt, nếu e là cạnh ngược của một cạnh thật, cập nhật trên sẽ tự động **giảm luồng thật** của cạnh gốc.

Với một cặp cạnh gắn với cạnh thật ban đầu có sức chứa c:

\[
residual_{forward}+residual_{reverse}=c.
\]

Ta suy ra:

\[
f=c-residual_{forward}=residual_{reverse}.
\]

Hai vế luôn không âm khi ta chỉ tăng trên cạnh dư có `residual>0` và không vượt bottleneck.

### Cạnh dư ngược không phải cạnh đầu vào thật

Nếu mạng **không có cạnh thật v→u**, residual vẫn có thể có cạnh v→u sau khi gửi luồng trên u→v. Nó **không cho phép vận chuyển hàng tự do theo một tuyến mới**; chỉ biểu diễn quyền **rút lại** một phần luồng đã gửi.

Nếu mạng **có cả hai cạnh thật u→v và v→u**, cần phân biệt:
- cạnh dư thuận của cạnh thật u→v;
- cạnh dư ngược của cạnh thật u→v;
- cạnh dư thuận của cạnh thật v→u;
- cạnh dư ngược của cạnh thật v→u.

Một cách cài đặt an toàn là tạo **cặp đối tượng liên kết reverse riêng cho mỗi cạnh thật**, không dựa vào việc tìm một cạnh đối diện duy nhất theo hai đỉnh. Nhờ vậy có thể hỗ trợ cạnh song song và cạnh thật ngược chiều mà không nhầm sức chứa.

## 6. Ví dụ buộc phải dùng cạnh ngược để phân phối lại

Xét mạng 6 đỉnh, s=0 và t=5:

~~~text
0 → 1 (1) → 3 (1) → 5 (1)
|     \
|      → 4 (1) → 5 (1)
↓
2 (1) → 3 (1)
~~~

Tập cạnh thật theo đúng thứ tự thêm vào:

| Cạnh | Sức chứa |
| --- | ---: |
| 0→1 | 1 |
| 0→2 | 1 |
| 1→3 | 1 |
| 1→4 | 1 |
| 2→3 | 1 |
| 3→5 | 1 |
| 4→5 | 1 |

### Đường tăng thứ nhất

BFS trên mạng dư tìm một đường ngắn nhất theo số cạnh:

~~~text
0 → 1 → 3 → 5
~~~

Bottleneck = 1. Gửi một đơn vị:
- f(0→1)=1.
- f(1→3)=1.
- f(3→5)=1.

Giá trị luồng hiện tại là **1**. Cấu hình này thỏa sức chứa và bảo toàn, nhưng chưa cực đại.

### Nếu chỉ nhìn cạnh thuận đang trống

Sau bước đầu, cạnh 0→2 còn sức chứa 1 và cạnh 2→3 cũng còn 1, nhưng 3→5 đã bão hòa. Nếu ta **không cho phép hủy/điều chỉnh** luồng ở 1→3, có vẻ không tìm được thêm đường từ 0 tới 5.

Đây là lý do thuật toán **không thể chỉ xóa những sức chứa đã dùng rồi đi tiếp**. Phải xây mạng dư có cạnh ngược.

### Đường tăng thứ hai

Vì f(1→3)=1, tồn tại **cạnh dư ngược 3→1 có sức chứa dư 1**. BFS tiếp theo tìm:

~~~text
0 → 2 → 3 → 1 → 4 → 5
             ^
      3→1 là cạnh dư NGƯỢC của 1→3
~~~

Bottleneck = 1. Tăng dọc đường:
- Luồng thật f(0→2) tăng từ 0 thành 1.
- f(2→3) tăng từ 0 thành 1.
- Đi qua cạnh dư ngược **3→1** làm f(1→3) **giảm từ 1 thành 0**.
- f(1→4) tăng từ 0 thành 1.
- f(4→5) tăng từ 0 thành 1.

Cạnh thật 3→5 giữ luồng 1. Luồng được **định tuyến lại**, không hề tạo ra luồng âm trên cạnh thật 1→3.

### Cấu hình luồng cuối

| Cạnh thật | f/c sau hai lần tăng |
| --- | --- |
| 0→1 | 1/1 |
| 0→2 | 1/1 |
| 1→3 | 0/1 |
| 1→4 | 1/1 |
| 2→3 | 1/1 |
| 3→5 | 1/1 |
| 4→5 | 1/1 |

Có hai đường mang luồng:
- `0→1→4→5`: 1 đơn vị.
- `0→2→3→5`: 1 đơn vị.

Tổng giá trị từ s là **2**. Tại mọi đỉnh trung gian 1,2,3,4, luồng vào = luồng ra = 1. Nguồn 0 có outflow 2, đích 5 có inflow 2.

Tổng sức chứa cạnh rời nguồn 0 bằng `1+1=2`, nên không thể có luồng lớn hơn 2. Vì đã đạt 2, đây là **luồng cực đại**.

### Điểm không được hiểu sai

Đường tăng thứ hai `0→2→3→1→4→5` là **đường trong mạng dư**, không phải một đường vận chuyển thực ban đầu. Cạnh 3→1 trong đó **chỉ hủy luồng trên cạnh thật 1→3**. Luồng cuối có thể phân tích thành hai đường thực như trên và hoàn toàn thỏa hai điều kiện hợp lệ.

## 7. Tăng luồng theo đường dư và tính bảo toàn

Giả sử f ban đầu là luồng khả thi. Chọn một đường có hướng trong mạng dư từ s tới t với tất cả sức chứa dư dương. Đặt:

\[
\Delta=\min\{residual(e):e\text{ nằm trên đường}\}>0.
\]

Cập nhật mỗi cặp cạnh dư được đi qua bằng cách trừ \Delta ở cạnh sử dụng và cộng \Delta ở cạnh đối ứng.

**Giữ sức chứa:** vì \Delta không lớn hơn sức chứa dư của bất kỳ cạnh sử dụng nào, residual mới của cạnh ấy không âm. Cặp residual thuận/ngược vẫn có tổng c, nên luồng thật vẫn trong `[0,c]`.

**Giữ bảo toàn:** tại mỗi đỉnh trung gian trên đường tăng, có đúng một cạnh của đường đi vào và một cạnh của đường đi ra (nếu BFS lấy đường đơn). Tác động ròng tại đỉnh là 0, kể cả khi một bước qua cạnh dư ngược tương ứng với **giảm** luồng thật. Nguồn tăng net outflow \Delta, đích tăng net inflow \Delta.

**Tăng giá trị:** sau một lần augment:

\[
|f_{new}|=|f_{old}|+\Delta.
\]

Từ luồng ban đầu 0, mọi bước duy trì tính hợp lệ. Điều này giúp giải thích thuật toán tăng luồng mà không phải kiểm tra lại toàn bộ các đỉnh trong mỗi bước; tuy vậy kiểm tra sau khi hoàn tất vẫn rất hữu ích để bắt lỗi cài đặt.

## 8. Lát cắt s–t và giới hạn trên của mọi luồng

Một **lát cắt s–t** (*s–t cut*) là cách chia đỉnh thành hai tập rời `S` và `T=V\setminus S` sao cho `s\in S` và `t\in T`.

**Sức chứa lát cắt**:

\[
\boxed{c(S,T)=\sum_{\substack{e=(u,v)\in E\\u\in S,\,v\in T}}c(e).}
\]

**Chỉ đếm cạnh thật đi từ S sang T.** Không cộng cạnh đi từ T về S khi tính capacity của lát cắt. Self-loop không thể đi qua ranh giới nên không góp sức chứa cắt.

Ví dụ mạng hai đường 0→1 và 0→2 ở phần 6, chọn:
- `S=\{0\}`,
- `T=\{1,2,3,4,5\}`.

Chỉ có hai cạnh thật 0→1 và 0→2 đi từ S sang T, mỗi cạnh sức chứa 1, nên **c(S,T)=2**.

### Vì sao mọi luồng đều bị chặn bởi một lát cắt?

Tổng luồng ròng đi từ S sang T:

\[
|f|=\sum_{e:S\to T}f(e)-\sum_{e:T\to S}f(e).
\]

Mọi luồng thật không âm nên:

\[
|f|\le\sum_{e:S\to T}f(e)
\le\sum_{e:S\to T}c(e)=c(S,T).
\]

Do đó:

\[
\boxed{|f|\le c(S,T)\text{ với mọi lát cắt }s-t.}
\]

Đây là **giới hạn trên toàn cục**, không phụ thuộc vào cách chọn đường tăng. Một luồng hợp lệ đạt được sức chứa của **một lát cắt** chắc chắn là cực đại.

### Định lý max-flow min-cut

Trong mạng có sức chứa không âm:

\[
\boxed{\max\{|f|:f\text{ khả thi}\}
=\min\{c(S,T):(S,T)\text{ là lát cắt }s-t\}.}
\]

Không phải chỉ vì “không tìm thấy đường thuận”; điều kiện dừng đúng là **không còn đường tăng từ s tới t trong toàn bộ mạng dư**, bao gồm cả cạnh ngược.

Khi không còn đường tăng, đặt S là tập đỉnh **còn tới được từ s bằng các cạnh dư dương**, T là phần còn lại. Đích t thuộc T. Với mỗi cạnh thật từ S sang T, residual thuận phải bằng 0, nên cạnh đó **bão hòa**. Với mỗi cạnh thật từ T sang S, nếu còn luồng dương thì residual ngược từ S sang T sẽ dương, mâu thuẫn với cách dựng S; vì vậy những cạnh này có luồng 0. Do đó:

\[
|f|=c(S,T).
\]

Kết hợp giới hạn trên của mọi lát cắt, f là luồng cực đại và (S,T) là một lát cắt cực tiểu. Đây là chứng chỉ tối ưu có thể kiểm tra trực tiếp.

## 9. Từ khái niệm sang thuật toán Edmonds–Karp

**Edmonds–Karp** là một hiện thực của phương pháp Ford–Fulkerson, luôn dùng **BFS để chọn đường tăng ngắn nhất theo số cạnh trong mạng dư**.

Quy trình:

1. Khởi tạo mọi luồng thật bằng 0. Với mỗi cạnh thật có sức chứa c, tạo residual thuận c và residual ngược 0.
2. BFS từ s qua các cạnh dư có `residual>0`, lưu **cạnh dư đã dùng để đến từng đỉnh** (*parent edge*), không chỉ lưu đỉnh cha.
3. Nếu BFS không tới được t, dừng.
4. Truy vết từ t về s theo parent edge, lấy bottleneck nhỏ nhất trên đường.
5. Với mỗi cạnh dư e trên đường: `e.residual-=bottleneck`, `e.reverse.residual+=bottleneck`.
6. Cộng bottleneck vào giá trị luồng, sau đó BFS lại.
7. Khi dừng, tìm các đỉnh reachable từ s trong mạng dư. Đó là tập S của một **min-cut**.

### Tại sao lưu parent edge thay vì chỉ parent vertex?

Vì có thể có **nhiều cạnh song song** cùng `u→v` với sức chứa riêng. Mỗi cạnh dư có một đối tượng reverse riêng. Lưu chính **đối tượng cạnh** cho phép cập nhật đúng cặp residual khi tăng; chỉ biết `parent[v]=u` là chưa đủ để xác định đã dùng cạnh nào.

Trong mạng có cả **hai cạnh thật u→v và v→u**, lưu parent edge còn tránh nhầm cạnh thật ngược chiều với **cạnh dư ngược**.

### Độ phức tạp

Một lần BFS trên danh sách kề tốn `O(V+E)`. Định lý Edmonds–Karp bảo đảm số lần tăng luồng là `O(VE)`, nên:

\[
\boxed{T_{\text{Edmonds–Karp}}=O(VE^2)}
\]

trong cách viết chuẩn cho đồ thị có V đỉnh và E cạnh (tính cả mạng dư theo hệ số hằng). Bộ nhớ lưu mạng dư, hàng đợi và parent là **O(V+E)**.

Con số `O(VE^2)` khác với bản Ford–Fulkerson chọn đường tùy ý, thường có chặn `O(E|f^*|)` với sức chứa nguyên khi mỗi lần tăng tối thiểu một đơn vị. Việc dùng BFS giúp Edmonds–Karp có bảo đảm đa thức **không phụ thuộc vào giá trị số của sức chứa**. Với mạng rất lớn, có thể học tiếp **Dinic** hoặc thuật toán **push–relabel**.

## 10. Java 17: mạng dư có cặp cạnh liên kết, có kiểm tra bảo toàn

Mã sau là **một chương trình độc lập**:

- Mỗi cạnh thật tạo **hai đối tượng Edge** liên kết qua trường `reverse`. Những cạnh thật ngược chiều hoặc song song **không bị nhập nhằng**.
- Lưu riêng danh sách `original` gồm các cạnh **thật** để tính luồng thực tế, kiểm tra sức chứa và tính min-cut.
- BFS trong residual chỉ đi qua cạnh có `residual>0`. Mảng `parentEdge[]` lưu đối tượng cạnh dư cụ thể.
- Sau khi tìm max flow, dựng tập `sourceSide` gồm những đỉnh còn reachable từ s trong residual và tính capacity lát cắt.
- `validFlow` kiểm tra `0<=f<=c` với từng cạnh thật, điều kiện bảo toàn tại mọi đỉnh, giá trị nguồn/đích và chứng chỉ min-cut.
- Thử cả ví dụ cần hủy luồng, cạnh thật hai chiều, cạnh song song, self-loop, đồ thị không có đường s–t, sức chứa âm, nguồn trùng đích.
- Bộ kiểm thử nhỏ đối chiếu max-flow với **oracle min-cut bằng vét cạn mọi tập S**.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.StringJoiner;

public class FlowCapacityConservationDemo {
    static final class Edge {
        final int from;
        final int to;
        final long capacity;
        final boolean original;
        long residual;
        Edge reverse;

        Edge(int from, int to, long capacity,
                long residual, boolean original) {
            this.from = from;
            this.to = to;
            this.capacity = capacity;
            this.residual = residual;
            this.original = original;
        }
    }

    record Result(long value, long cutCapacity,
            boolean[] sourceSide, List<String> steps) {}

    static final class Network {
        final int n;
        final List<List<Edge>> adj;
        final List<Edge> original = new ArrayList<>();

        Network(int n) {
            if (n <= 0) {
                throw new IllegalArgumentException(
                        "Network needs vertices");
            }
            this.n = n;
            this.adj = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                adj.add(new ArrayList<>());
            }
        }

        void addArc(int from, int to, long capacity) {
            if (from < 0 || from >= n
                    || to < 0 || to >= n) {
                throw new IllegalArgumentException("Invalid vertex");
            }
            if (capacity < 0) {
                throw new IllegalArgumentException(
                        "Capacity must be nonnegative");
            }

            Edge forward = new Edge(
                    from, to, capacity, capacity, true);
            Edge backward = new Edge(
                    to, from, 0, 0, false);
            forward.reverse = backward;
            backward.reverse = forward;

            // Ke ca self-loop va cap canh song song.
            adj.get(from).add(forward);
            adj.get(to).add(backward);
            original.add(forward);
        }

        void checkTerminals(int s, int t) {
            if (s < 0 || s >= n || t < 0 || t >= n) {
                throw new IllegalArgumentException(
                        "Invalid source or sink");
            }
            if (s == t) {
                throw new IllegalArgumentException(
                        "Source and sink must differ");
            }
        }

        Edge[] bfsParent(int s, int t) {
            Edge[] parent = new Edge[n];
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();

            seen[s] = true;
            queue.addLast(s);
            while (!queue.isEmpty() && !seen[t]) {
                int u = queue.removeFirst();
                for (Edge e : adj.get(u)) {
                    if (e.residual <= 0 || seen[e.to]) {
                        continue;
                    }
                    seen[e.to] = true;
                    parent[e.to] = e;
                    queue.addLast(e.to);
                    if (e.to == t) break;
                }
            }
            return seen[t] ? parent : null;
        }

        boolean[] reachableInResidual(int s) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.addLast(s);
            seen[s] = true;

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

        Result maxFlow(int s, int t) {
            checkTerminals(s, t);
            long value = 0;
            List<String> steps = new ArrayList<>();

            while (true) {
                Edge[] parent = bfsParent(s, t);
                if (parent == null) break;

                long delta = Long.MAX_VALUE;
                List<Integer> reversedPath = new ArrayList<>();
                List<String> reversedBackwardSteps =
                        new ArrayList<>();
                reversedPath.add(t);

                for (int v = t; v != s; ) {
                    Edge e = parent[v];
                    delta = Math.min(delta, e.residual);
                    if (!e.original) {
                        reversedBackwardSteps.add(
                                e.from + "->" + e.to);
                    }
                    v = e.from;
                    reversedPath.add(v);
                }
                Collections.reverse(reversedPath);
                Collections.reverse(reversedBackwardSteps);

                for (int v = t; v != s; ) {
                    Edge e = parent[v];
                    e.residual =
                            Math.subtractExact(e.residual, delta);
                    e.reverse.residual = Math.addExact(
                            e.reverse.residual, delta);
                    v = e.from;
                }
                value = Math.addExact(value, delta);

                steps.add("path=" + showPath(reversedPath)
                        + " delta=" + delta + " reverse="
                        + (reversedBackwardSteps.isEmpty()
                           ? "none"
                           : String.join(",", reversedBackwardSteps)));
            }

            boolean[] side = reachableInResidual(s);
            long cutCapacity = 0;
            for (Edge e : original) {
                if (side[e.from] && !side[e.to]) {
                    cutCapacity = Math.addExact(
                            cutCapacity, e.capacity);
                }
            }
            return new Result(
                    value, cutCapacity, side, List.copyOf(steps));
        }

        // Chi duyet CANH THAT, khong tinh canh du 2 lan.
        boolean validFlow(int s, int t, Result result) {
            long[] balance = new long[n];
            for (Edge e : original) {
                long f = Math.subtractExact(
                        e.capacity, e.residual);
                if (f < 0 || f > e.capacity
                        || e.reverse.reverse != e
                        || e.reverse.residual != f) {
                    return false;
                }
                balance[e.from] = Math.addExact(
                        balance[e.from], f);
                balance[e.to] = Math.subtractExact(
                        balance[e.to], f);
            }

            for (int v = 0; v < n; v++) {
                if (v != s && v != t && balance[v] != 0) {
                    return false;
                }
            }
            return balance[s] == result.value()
                    && balance[t] == -result.value()
                    && !result.sourceSide()[t]
                    && result.cutCapacity() == result.value();
        }

        String originalFlows() {
            StringJoiner out = new StringJoiner(
                    ", ", "[", "]");
            for (Edge e : original) {
                long f = Math.subtractExact(
                        e.capacity, e.residual);
                out.add(e.from + "->" + e.to
                        + ":" + f + "/" + e.capacity);
            }
            return out.toString();
        }
    }

    static String showSide(boolean[] side) {
        StringJoiner out = new StringJoiner(
                ", ", "[", "]");
        for (int v = 0; v < side.length; v++) {
            if (side[v]) out.add(Integer.toString(v));
        }
        return out.toString();
    }

    // Oracle min-cut doc lap: thu tat ca tap S chua s,
    // khong chua t. Dung chi cho mang nho n <= 7.
    static long minCutOracle(
            Network net, int s, int t) {
        long best = Long.MAX_VALUE;
        for (int mask = 0; mask < (1 << net.n); mask++) {
            if ((mask & (1 << s)) == 0
                    || (mask & (1 << t)) != 0) {
                continue;
            }
            long cut = 0;
            for (Edge e : net.original) {
                boolean insideU =
                        (mask & (1 << e.from)) != 0;
                boolean insideV =
                        (mask & (1 << e.to)) != 0;
                if (insideU && !insideV) {
                    cut = Math.addExact(cut, e.capacity);
                }
            }
            best = Math.min(best, cut);
        }
        return best;
    }

    static int randomState = 20261110;

    // LCG xac dinh, tinh theo so nguyen 32-bit khong dau.
    static int randomInt(int bound) {
        randomState = randomState * 1664525 + 1013904223;
        return (int) (Integer.toUnsignedLong(randomState)
                % bound);
    }

    static int verifySmallNetworks() {
        int checked = 0;

        // n=2,3: moi canh u->v (u!=v) co cap 0,1,2.
        // n=4: tat ca 2^12 tap canh, cap duong
        // duoc chon xac dinh tu hai dau mut.
        for (int n = 2; n <= 4; n++) {
            int pairs = n * (n - 1);
            int base = n <= 3 ? 3 : 2;
            int total = 1;
            for (int i = 0; i < pairs; i++) total *= base;

            for (int code = 0; code < total; code++) {
                Network net = new Network(n);
                int x = code;
                for (int u = 0; u < n; u++) {
                    for (int v = 0; v < n; v++) {
                        if (u == v) continue;
                        int digit = x % base;
                        x /= base;
                        int capacity = n <= 3
                                ? digit
                                : digit * (1 + (u * 7 + v * 3) % 4);
                        if (capacity > 0) {
                            net.addArc(u, v, capacity);
                        }
                    }
                }

                Result actual = net.maxFlow(0, n - 1);
                if (!net.validFlow(0, n - 1, actual)
                        || actual.value()
                           != minCutOracle(net, 0, n - 1)) {
                    throw new AssertionError(
                            "Mismatch n=" + n + " code=" + code);
                }
                checked++;
            }
        }

        // Them 1.600 mang xac dinh, co cap 0,
        // self-loop, canh song song va canh nguoc chieu.
        for (int test = 0; test < 1600; test++) {
            int n = 2 + randomInt(6);
            int m = randomInt(24);
            Network net = new Network(n);
            for (int i = 0; i < m; i++) {
                int u = randomInt(n);
                int v = randomInt(n);
                int capacity = randomInt(13);
                net.addArc(u, v, capacity);
            }

            Result actual = net.maxFlow(0, n - 1);
            if (!net.validFlow(0, n - 1, actual)
                    || actual.value()
                       != minCutOracle(net, 0, n - 1)) {
                throw new AssertionError(
                        "Random mismatch test=" + test);
            }
            checked++;
        }
        return checked;
    }

    static Network make(int n, long[][] arcs) {
        Network net = new Network(n);
        for (long[] arc : arcs) {
            net.addArc((int) arc[0], (int) arc[1], arc[2]);
        }
        return net;
    }

    static Result report(String name, Network net,
            int s, int t) {
        Result result = net.maxFlow(s, t);
        System.out.println(name + " maxFlow=" + result.value()
                + " cut=" + result.cutCapacity()
                + " sourceSide=" + showSide(result.sourceSide()));
        System.out.println(name + " valid="
                + net.validFlow(s, t, result));
        return result;
    }

    public static void main(String[] args) {
        Network reroute = make(6, new long[][]{
            {0,1,1}, {0,2,1}, {1,3,1}, {1,4,1},
            {2,3,1}, {3,5,1}, {4,5,1}
        });
        Result first = report("reroute", reroute, 0, 5);
        for (int i = 0; i < first.steps().size(); i++) {
            System.out.println("reroute augment" + (i + 1)
                    + " " + first.steps().get(i));
        }
        System.out.println("reroute arcs="
                + reroute.originalFlows());

        report("antiparallel", make(4, new long[][]{
            {0,1,5}, {0,2,3}, {1,2,2}, {2,1,4},
            {1,3,4}, {2,3,4}, {0,3,0}
        }), 0, 3);

        report("parallel", make(3, new long[][]{
            {0,1,2}, {0,1,3}, {1,2,4}, {0,2,1}
        }), 0, 2);

        report("selfLoop", make(3, new long[][]{
            {0,0,99}, {0,1,3}, {1,2,2}, {0,2,1}
        }), 0, 2);

        report("disconnected", make(4, new long[][]{
            {0,1,4}, {2,3,7}, {1,0,9}
        }), 0, 3);

        try {
            Network invalid = new Network(2);
            invalid.addArc(0, 1, -1);
            throw new AssertionError("Negative cap accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negativeRejected=" + ex.getMessage());
        }

        try {
            Network invalid = new Network(1);
            invalid.maxFlow(0, 0);
            throw new AssertionError("Same s/t accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("sameEndpointRejected="
                    + ex.getMessage());
        }

        System.out.println(
                "testedNetworks=" + verifySmallNetworks());
    }
}
~~~

Lưu thành tệp **FlowCapacityConservationDemo.java**. Chạy bằng **JDK 17 trở lên**:

~~~bash
javac FlowCapacityConservationDemo.java
java FlowCapacityConservationDemo
~~~

**Đầu ra chính xác theo thứ tự cạnh trong mã:**

~~~text
reroute maxFlow=2 cut=2 sourceSide=[0]
reroute valid=true
reroute augment1 path=0->1->3->5 delta=1 reverse=none
reroute augment2 path=0->2->3->1->4->5 delta=1 reverse=3->1
reroute arcs=[0->1:1/1, 0->2:1/1, 1->3:0/1, 1->4:1/1, 2->3:1/1, 3->5:1/1, 4->5:1/1]
antiparallel maxFlow=8 cut=8 sourceSide=[0]
antiparallel valid=true
parallel maxFlow=5 cut=5 sourceSide=[0, 1]
parallel valid=true
selfLoop maxFlow=3 cut=3 sourceSide=[0, 1]
selfLoop valid=true
disconnected maxFlow=0 cut=0 sourceSide=[0, 1]
disconnected valid=true
negativeRejected=Capacity must be nonnegative
sameEndpointRejected=Source and sink must differ
testedNetworks=6434
~~~

### Cách đọc output

- `reroute augment2` chứa `reverse=3->1`: đây là bước **hủy một đơn vị luồng của cạnh thật 1→3**, không phải sử dụng một cạnh 3→1 ban đầu.
- `reroute arcs` in cho **từng cạnh thật** theo định dạng `from->to:flow/capacity`. Cạnh 1→3 có giá trị cuối 0/1, chứng minh luồng có thể được rút lại và định tuyến sang 1→4.
- `antiparallel` có cả hai cạnh thật 1→2 và 2→1; các cặp residual riêng hoạt động đúng. Max-flow 8 khớp hai cạnh đi ra từ nguồn tổng capacity 5+3.
- `parallel` giữ hai cạnh 0→1 riêng biệt; max-flow 5 và min-cut là 5. Tập reachable cuối `[0,1]` cho lát cắt với cạnh 1→2 sức chứa 4 và 0→2 sức chứa 1.
- `selfLoop` có cạnh 0→0 sức chứa 99 nhưng không thể tăng lượng s–t chỉ bằng self-loop; max-flow 3 nhờ các cạnh có hướng tới t.
- `disconnected` có nguồn và đích ở hai phần không nối được bằng cạnh dư dương; max-flow 0, min-cut 0 và tập reachable từ s là `[0,1]`.
- `valid=true` là kết quả kiểm tra sức chứa từng cạnh thật, conservation các đỉnh trung gian, balance tại nguồn/đích, và equality giữa giá trị luồng và capacity cut.
- Những phép kiểm tra chỉ dùng **số nguyên không âm đủ nhỏ** để không gặp overflow; nếu sức chứa đầu vào rất lớn, cần cân nhắc miền số và chính sách xử lý lỗi.

### Tại sao mã hỗ trợ cả self-loop, cạnh song song và cạnh ngược thật?

Với mỗi lần `addArc(u,v,c)`, mã tạo **hai đối tượng Edge khác nhau** liên kết trực tiếp với nhau qua `reverse`. Không tìm cạnh đối diện bằng cách tra `adj[v]` để đoán cặp.

Nếu u=v, hai đối tượng vẫn nằm trong cùng adjacency list của u nhưng **liên kết riêng**; BFS đã seen[u] nên không dùng self-loop để khám phá một đỉnh mới. Luồng thật của self-loop cuối cùng vẫn là 0 trong các ví dụ.

Nếu hai lần thêm `0→1`, mỗi cạnh có residual thuận, residual ngược riêng và xuất hiện một lần trong `original`. Thuật toán sẽ kiểm tra từng cạnh thật khi tính tổng và capacity cut.

Nếu thêm cả `u→v` và `v→u`, đó là **hai thao tác addArc độc lập** tạo bốn đối tượng residual. Một đối tượng residual ngược được dùng để hủy luồng của **đúng cạnh gốc nó tham chiếu**, không được gộp với đối tượng forward của cạnh thật ngược chiều.

### Lưu ý phạm vi API và số học

`maxFlow` được thiết kế cho **một lần chạy trên mạng mới khởi tạo luồng 0**. Gọi lần hai trên cùng một Network sau khi max-flow đã thay residual sẽ không trả lại tổng giá trị luồng của lần trước như một kết quả “tính lại từ đầu”: vòng tăng có thể không thêm gì và biến `value` mới bắt đầu lại từ 0. Nếu muốn chạy lại, **tạo Network mới** hoặc định nghĩa API tăng tiếp từ luồng hiện có và tính value ban đầu cho đúng.

`Math.addExact`/`subtractExact` phát hiện tràn 64-bit thay vì âm thầm quay dấu. Nếu một phép số học báo lỗi trong khi đang cập nhật, mã minh họa không bảo đảm rollback tự động; không nên tiếp tục dùng trạng thái đó mà không khôi phục. Với capacity/tổng luồng vượt khả năng của long, dùng kiểu số lớn hơn hoặc ràng buộc dữ liệu đầu vào.

Khi nguồn và đích trùng nhau, bài toán s–t max flow tiêu chuẩn không còn mang ý nghĩa tăng đường từ một đỉnh sang một đỉnh khác; chương trình từ chối rõ ràng bằng `IllegalArgumentException`. Một mạng chỉ có một đỉnh vẫn có thể được tạo, nhưng không có cặp nguồn–đích phân biệt hợp lệ.

## 11. Kiểm thử bằng oracle min-cut độc lập

Ngoài các ví dụ, phần `verifySmallNetworks` kiểm tra **6.434 mạng** nhỏ với giá trị capacity nguyên.

### Tập vét cạn

- **n=2**: có hai cặp có hướng khác đỉnh đầu/cuối; mỗi cạnh có capacity 0, 1 hoặc 2. Có `3^2=9` mạng.
- **n=3**: có sáu cặp có hướng khác nhau; mỗi cạnh capacity 0, 1 hoặc 2. Có `3^6=729` mạng.
- **n=4**: có 12 cặp có hướng khác nhau. Thử mọi tập cạnh có/không có `2^12=4096` cách; cạnh được chọn nhận capacity xác định `1+((7u+3v) mod 4)`.
- **1.600 mạng bổ sung** có n từ 2 tới 7, số cạnh và sức chứa nguyên được tạo bởi bộ sinh giả ngẫu nhiên xác định. Các mạng này cho phép cả cạnh capacity=0, self-loop, cạnh song song và cạnh thật hai chiều.

Tổng:

\[
9+729+4096+1600=\boxed{6434}.
\]

### Oracle kiểm tra cái gì?

Với n đỉnh nhỏ, liệt kê mọi tập con `S\subseteq V` sao cho `s\in S` và `t\notin S`. Tính capacity c(S,T) **chỉ từ các cạnh thật** đi từ S sang T, rồi lấy **giá trị nhỏ nhất**.

Đây là một cách kiểm chứng độc lập với việc BFS tìm đường tăng: **đi qua mọi lát cắt** thay vì mô phỏng chính thuật toán max-flow. Nó có chi phí mũ theo n nên chỉ phù hợp với dữ liệu nhỏ.

Mỗi lần kiểm thử còn xem:
1. Từng cạnh thật có `0<=f<=c`.
2. Residual thuận và ngược của cùng cạnh thật đối ứng đúng.
3. Mọi đỉnh trung gian có balance=0.
4. Nguồn có balance bằng value, đích có balance bằng âm value.
5. t không còn reachable từ s theo residual dương.
6. Capacity của lát cắt cuối bằng giá trị luồng.
7. Value khớp oracle vét cạn **mọi lát cắt**.

Việc đối chiếu 6.434 mạng nhỏ giúp bắt lỗi cập nhật cạnh ngược, đếm cạnh song song, self-loop, bảo toàn và tính min-cut. Nó **không thay thế** chứng minh định lý max-flow min-cut ở phần 8.

## 12. Những câu hỏi nền tảng thường bị nhầm

### Một cạnh bão hòa có chứng minh luồng cực đại không?

Không. Một cạnh duy nhất có thể bão hòa nhưng mạng còn đường khác từ s tới t. Chỉ khi **không còn đường tăng nào trong mạng dư** (hoặc có chứng chỉ cut đạt bằng value) mới kết luận cực đại.

### Nếu luồng không có cạnh nào vượt capacity, đã hợp lệ chưa?

Chưa. Phải kiểm tra **bảo toàn tại mọi đỉnh trung gian** và giá trị ròng tại s/t. Một mạng có thể có các cạnh độc lập đúng sức chứa nhưng vô tình “tạo” hoặc “mất” tài nguyên tại một đỉnh trung gian.

### Nếu không còn đường thật từ s tới t dùng các cạnh thuận chưa bão hòa, đã cực đại chưa?

Chưa chắc. Ví dụ phần 6 phải dùng cạnh **dư ngược 3→1** để hủy luồng 1→3, sau đó có thể tăng thêm một đơn vị. Phải tìm đường trong **toàn bộ mạng dư**, không chỉ cạnh thuận.

### Luồng và sức chứa có được âm không?

Mô hình chuẩn theo cạnh thật dùng `c(e)>=0` và `0<=f(e)<=c(e)`. Sức chứa âm là đầu vào **không hợp lệ**. Một đối tượng cạnh dư ngược có biến residual **không âm**; nó biểu diễn quyền hủy luồng gốc, không phải “luồng thật âm” trên một cạnh đầu vào.

Một số giáo trình dùng biến luồng `f(u,v)=-f(v,u)` theo mô hình **phản đối xứng**. Đó là một cách biểu diễn toán học khác; nếu dùng, phải áp dụng nhất quán các định nghĩa capacity và tổng vào/ra. Chương trình Java của bài dùng **luồng không âm theo từng cạnh thật**, đặc biệt phù hợp với đa cạnh.

### Có bắt buộc nguồn không có cạnh đi vào và đích không có cạnh đi ra?

Nhiều hình minh họa giả định như vậy cho dễ nhìn, nhưng công thức giá trị tổng quát **không yêu cầu**. Nguồn có thể nhận luồng đi vào, đích có thể có luồng đi ra; lúc đó **value được tính theo lượng ròng**, không dùng riêng tổng out(s) hoặc in(t).

### Luồng tối ưu có duy nhất không?

Không nhất thiết. Có thể có nhiều cách phân phối luồng thật cùng giá trị cực đại. Thuật toán phụ thuộc thứ tự cạnh và đường BFS có thể trả một nghiệm khác nhưng vẫn hợp lệ; **giá trị cực đại** và **sức chứa min-cut** vẫn khớp.

### Cạnh có trọng số chi phí thì sao?

Bài này tối ưu **giá trị luồng**, không tối ưu chi phí vận chuyển. Nếu mỗi cạnh có **chi phí** riêng và đề muốn tối thiểu tổng chi phí khi gửi một lượng luồng, đó là **min-cost flow**. Sức chứa, luồng và bảo toàn vẫn là nền tảng, nhưng phải bổ sung hàm mục tiêu và thuật toán thích hợp.

## 13. Trường hợp biên và lỗi phổ biến

| Tình huống | Cách hiểu/kiểm tra đúng |
| --- | --- |
| Không có cạnh | Luồng 0 hợp lệ và cực đại, cut 0 |
| Có cạnh capacity 0 | Luồng trên cạnh đó bắt buộc 0 |
| s và t không nối bằng đường dư | Max-flow 0 (nếu luồng khởi đầu 0) |
| Self-loop u→u | Không tăng value s–t; có thể tồn tại trong mạng |
| Hai cạnh song song u→v | Mỗi cạnh có capacity và flow riêng, có thể gộp có chủ đích |
| Hai cạnh thật đối chiều | Là hai cạnh độc lập; không nhầm với cạnh residual ngược |
| Sức chứa âm | Từ chối input |
| Nguồn trùng đích | Từ chối theo hợp đồng max-flow tiêu chuẩn |
| Đỉnh trung gian nhận 7, gửi 6 | Vi phạm bảo toàn dù từng cạnh không vượt sức chứa |
| Đỉnh trung gian nhận 7, gửi 7 | Đạt conservation, còn phải kiểm tra từng capacity |
| Có một cạnh bão hòa | Chưa đủ để kết luận max |
| BFS không tới t trong residual | Chứng cứ dừng Edmonds–Karp |
| Capacity cut bằng value | Chứng chỉ luồng cực đại |
| Cut gồm cạnh từ T→S | Các cạnh ấy **không** góp vào c(S,T) |
| Cạnh có trọng số/chi phí | Bài min-cost flow, không phải bài chỉ max-flow |
| Tổng capacity vượt long | Cần kiểu số rộng hoặc giới hạn đầu vào |

Những lỗi triển khai thường gặp:
1. **Chỉ kiểm tra giới hạn trên capacity mà bỏ conservation.**
2. **Dùng tổng out(s) thay net out(s)** khi có cạnh đi vào s.
3. **Dùng tổng in(t) thay net in(t)** khi có cạnh đi ra t.
4. **Chỉ cộng mỗi cặp đỉnh một lần**, vô tình bỏ cạnh song song.
5. **Tạo một cạnh ngược thật với capacity c** chỉ vì có cạnh u→v, thay đổi mạng đầu vào.
6. **Không tạo cạnh dư ngược**, không thể hủy/reroute luồng.
7. **Nhầm cạnh dư ngược với cạnh thật v→u** khi dữ liệu có cả hai chiều.
8. **Truy parent theo đỉnh rồi cập nhật một cạnh ngẫu nhiên** trong mạng đa cạnh.
9. **Tăng lớn hơn bottleneck**, làm residual âm hoặc vượt capacity.
10. **Quên trừ residual của cạnh đã dùng** khi augment.
11. **Quên cộng residual của cạnh đảo**, không thể thu hồi quyết định cũ.
12. **Đếm cả cạnh residual là cạnh thật** khi tính cut hoặc kiểm tra flow.
13. **Cộng cả cạnh T→S vào capacity cut**, khác định nghĩa min-cut.
14. **Cho rằng một cạnh bão hòa hoặc hết đường thuận là đạt max**.
15. **Không lọc residual>0 khi BFS**, đi qua cạnh không thể tăng.
16. **Quên kiểm tra s≠t**, có thể gây vòng xử lý vô nghĩa.
17. **Cho capacity âm là dữ liệu thường**, phá ràng buộc nền tảng.
18. **Không xét nhiều thành phần tách rời**, kết luận sai về reachable/cut.
19. **Chỉ in value không kiểm chứng flow/cut**, khó phát hiện lỗi cập nhật.
20. **Tính cộng dồn bằng int hoặc long mà không kiểm soát overflow**.
21. **Gọi lại maxFlow trên mạng dư đã bị thay đổi** như một lần chạy mới mà không khôi phục trạng thái.
22. **Tưởng rằng mọi đường tăng dư cũng là đường vận chuyển thật**, quên ý nghĩa hủy luồng của cạnh ngược.

## 14. Bài tập tự luyện có đáp án

**Bài 1 — sức chứa.** Cạnh `u→v` có capacity 8. Các giá trị luồng 0, 6, 8, 9, −1: giá trị nào thỏa riêng điều kiện sức chứa?

*Đáp án:* 0, 6, 8. Giá trị 9 vượt capacity; −1 vi phạm tính không âm của luồng thật.

**Bài 2 — bảo toàn.** Đỉnh trung gian x nhận 4 từ a và 3 từ b. Nó gửi 2 tới c, 4 tới d. Cấu hình có hợp lệ không?

*Đáp án:* Không. Tổng vào 7, tổng ra 6. Thiếu 1 đơn vị; phải điều chỉnh luồng trên các cạnh liên quan.

**Bài 3 — giá trị luồng.** Ở nguồn s, outflow=11 và inflow=2. Giá trị luồng là bao nhiêu?

*Đáp án:* `|f|=11−2=9`, không phải 11. Đích t phải có inflow−outflow bằng 9 nếu các đỉnh trung gian bảo toàn.

**Bài 4 — đỉnh t.** Đích t nhận 12, gửi ra 3. Giá trị ròng vào t là bao nhiêu?

*Đáp án:* 9.

**Bài 5 — bottleneck.** Đường tăng có các sức chứa dư [7,4,5]. Tăng nhiều nhất bao nhiêu?

*Đáp án:* 4. Tăng 5 sẽ làm cạnh giữa vượt khả năng dư.

**Bài 6 — cạnh dư ngược.** Cạnh thật 1→3 capacity 5 đang có flow 2. Residual thuận và ngược tương ứng bằng bao nhiêu?

*Đáp án:* Thuận 5−2=3; ngược 2. Đi một đơn vị trên residual 3→1 sẽ giảm flow thật 1→3 từ 2 xuống 1.

**Bài 7 — cấu hình sai.** Mạng s→x capacity 5, x→t capacity 3. Nếu f(s→x)=5 và f(x→t)=3, lỗi gì?

*Đáp án:* X vi phạm conservation: vào 5, ra 3. Một cấu hình tối đa hợp lệ là cả hai flow bằng 3.

**Bài 8 — tái định tuyến.** Trong mạng sáu đỉnh, vì sao cạnh dư 3→1 có residual 1 sau bước đầu?

*Đáp án:* Vì ta đã gửi một đơn vị trên cạnh thật 1→3. Cạnh dư ngược cho phép hủy tối đa một đơn vị; bước thứ hai dùng nó để chuyển luồng qua 1→4.

**Bài 9 — min-cut.** Chọn S={0} trong ví dụ chính. Những cạnh nào đóng vào capacity cut và giá trị cut?

*Đáp án:* Chỉ 0→1 capacity 1 và 0→2 capacity 1, nên cut=2. Các cạnh còn lại ở phía T hoặc không đi qua ranh giới.

**Bài 10 — chứng minh cực đại.** Đã có luồng hợp lệ value=2 và một cut capacity=2. Có cần thử mọi đường tăng khác để khẳng định cực đại không?

*Đáp án:* Không. Mọi luồng <= capacity của mọi cut; luồng hiện tại đạt cut=2 nên không thể cải thiện.

**Bài 11 — hai chiều.** Dữ liệu có cạnh thật u→v capacity 5 và v→u capacity 3. Có được dùng duy nhất một cặp residual để thay cả hai cạnh thật không?

*Đáp án:* Không nếu muốn lưu đầy đủ flow/capacity của từng cạnh. Mỗi cạnh thật cần một cặp residual riêng, hoặc phải thiết kế phép gộp tương đương có chứng minh.

**Bài 12 — cạnh song song.** Có hai cạnh thật s→x capacity 2 và 3. Tổng sức chứa của các cạnh này bằng bao nhiêu?

*Đáp án:* 5, nhưng luồng cực đại đến t còn bị hạn chế bởi những cạnh tiếp theo và các cut khác.

**Bài 13 — tự khép.** Cạnh u→u có capacity 100. Nó có thể tự làm tăng giá trị luồng s–t thêm 100 không?

*Đáp án:* Không. Nó đóng góp bằng nhau vào inflow và outflow của cùng u, không giúp vận chuyển từ s sang t.

**Bài 14 — mất đường tăng.** Nếu BFS trong mạng dư không còn tới được t từ s, đặt S là gì và suy ra điều gì?

*Đáp án:* S là tập những đỉnh còn reachable từ s qua cạnh dư dương. Cut (S,V\S) có capacity đúng bằng value luồng hiện tại; suy ra đạt max-flow=min-cut.

**Bài 15 — khái niệm.** Nếu một bài yêu cầu gửi đúng 10 đơn vị với tổng chi phí nhỏ nhất trên các cạnh có sức chứa, đó là max-flow thuần túy không?

*Đáp án:* Không. Cần mô hình **min-cost flow** với hàm mục tiêu chi phí ngoài các ràng buộc capacity và conservation.

## 15. Checklist giải bài luồng mạng

1. **Xác định mô hình:** các đỉnh, cạnh **có hướng**, capacity từng cạnh, nguồn s và đích t phải khác nhau.
2. **Phân biệt capacity và flow:** capacity là giới hạn, flow là lượng thực dùng.
3. **Xác minh feasibility:** `0<=f(e)<=c(e)` cho mỗi cạnh thật; `in(v)=out(v)` cho mọi v khác s,t.
4. **Tính đúng value bằng luồng ròng** ở s hoặc t, nhất là khi có cạnh vào s hoặc cạnh ra t.
5. **Khởi tạo residual thuận bằng capacity, ngược bằng 0**, liên kết rõ cặp cạnh gốc.
6. **Với cạnh song song hoặc hai chiều**, không đánh đồng các cạnh dư đối ứng của những cạnh thật khác nhau.
7. **Chọn đường tăng trong residual**, không chỉ đường theo cạnh thuận; tìm bottleneck và cập nhật cả hai chiều residual.
8. **Dùng BFS Edmonds–Karp khi cần bảo đảm đa thức**, lưu parent **edge** để biết chính xác cạnh đã chọn.
9. **Sau khi hết đường tăng**, dựng S reachable trong residual, tính capacity cut từ cạnh thật S→T.
10. **Kiểm tra chứng chỉ:** value=capacity cut, mọi đỉnh trung gian balance=0, mọi cạnh thật giữ 0<=f<=c.
11. **Xử lý biên:** capacity 0, self-loop, cạnh ngược, mạng rời, capacity lớn, nguồn/đích không hợp lệ.
12. **Chọn đúng biến thể bài toán:** max-flow, min-cut, circulation, matching, hay min-cost flow có ràng buộc chi phí.

## Ghi nhớ

- Một **luồng khả thi** phải thỏa **hai điều kiện độc lập**: giới hạn sức chứa `0<=f(e)<=c(e)` và **bảo toàn** `in(v)=out(v)` ở mỗi đỉnh trung gian.
- **Giá trị luồng** là **out(s)−in(s)=in(t)−out(t)**, không phải lúc nào cũng chỉ là tổng out(s).
- **Mạng dư** gồm khả năng tăng luồng theo cạnh thuận `c−f` và khả năng **hủy luồng theo cạnh ngược f`.
- **Đường tăng** phải nằm trong mạng dư; bottleneck là residual nhỏ nhất trên đường, và cập nhật cả hai cạnh đối ứng.
- Một **cạnh bão hòa** không chứng minh luồng cực đại. **Không còn đường tăng** trong mạng dư mới là điều kiện dừng đúng.
- **Mỗi lát cắt** chặn giá trị luồng từ trên: `|f|<=c(S,T)`. Sau khi Edmonds–Karp kết thúc, lát cắt reachable trong residual có capacity đúng bằng value luồng; đó là định lý **max-flow min-cut**.
- Khi dùng **Edmonds–Karp**, thời gian chặn trên `O(VE²)` với danh sách kề; chọn BFS và lưu parent edge để hỗ trợ cả **cạnh song song, cạnh thật hai chiều và residual ngược**.
