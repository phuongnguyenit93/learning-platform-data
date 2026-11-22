# Thế năng và đổi trọng số trong bài toán luồng chi phí

## 1. Bối cảnh: tại sao min-cost flow cần thế năng?

Một mạng luồng có **dung lượng** và **chi phí trên mỗi đơn vị luồng**. Cùng một giá trị luồng từ nguồn tới đích, ta có thể phân phối qua những đường khác nhau với **tổng chi phí khác nhau**. Bài toán **luồng chi phí nhỏ nhất** (*minimum-cost flow*) yêu cầu vừa đáp ứng lượng luồng cần gửi, vừa tối thiểu hóa chi phí; biến thể **minimum-cost maximum-flow** trước hết tối đa hóa giá trị luồng, sau đó trong các luồng cực đại chọn luồng có chi phí nhỏ nhất.

Khó khăn xuất hiện khi triển khai thuật toán **đường tăng luồng ngắn nhất** (*successive shortest augmenting path*, SSP):

- Mạng dư chứa **cạnh thuận** và **cạnh ngược**.
- Cạnh ngược có **chi phí đối dấu** với cạnh thuận gốc, nên ngay cả khi chi phí đầu vào không âm, mạng dư sau một lần tăng có thể có **cung chi phí âm**.
- Dijkstra chuẩn **không bảo đảm đúng** nếu áp dụng trực tiếp trên các cung có chi phí âm.
- Dùng Bellman–Ford để tìm đường ở **mọi lần tăng** có thể chậm.

Giải pháp là gán cho mỗi đỉnh một **thế năng** `\pi[v]` (*potential*) và dùng **chi phí đã đổi trọng số** (*reduced cost*):

\[
\boxed{c_{\pi}(u,v)=c(u,v)+\pi[u]-\pi[v].}
\]

Nếu duy trì `c_{\pi}(u,v)\ge0` trên mọi **cung dư có dung lượng dương**, ta được quyền dùng Dijkstra để tìm đường tăng theo **chi phí đã đổi**, nhưng thứ tự tối ưu của các đường `s\to t` theo **chi phí gốc** vẫn không đổi.

**Trọng tâm bài học:** thế năng không thay đổi bài toán luồng, không làm mất chi phí âm gốc, và không phải “phí bổ sung” phải cộng vào nghiệm. Nó là một phép biến đổi đại số để tìm đường ngắn nhất nhanh hơn, trong khi tổng chi phí cuối cùng vẫn phải tính theo **chi phí gốc trên từng cạnh vật lý**.

Bài học trình bày công thức, chứng minh bất biến, Bellman–Ford khởi tạo thế năng, Dijkstra trên mạng dư, cập nhật thế năng sau mỗi lần tăng, vai trò cạnh ngược, các giới hạn khi có chu trình âm, ví dụ **Java 17+ chạy độc lập** và kiểm thử đối chứng vét cạn.

## 2. Mô hình toán học và hai biến thể mục tiêu

Xét mạng có hướng `G=(V,E)`, nguồn `s`, đích `t`, `s\ne t`. Mỗi cạnh gốc `e=(u,v)` có:

- **Dung lượng** `cap_e\ge0`.
- **Chi phí đơn vị** `cost_e`, có thể âm, bằng `0` hoặc dương.
- **Luồng gốc** `f_e` thỏa `0\le f_e\le cap_e`.

Mỗi đơn vị gửi qua cạnh gốc `e` đóng góp `cost_e` vào tổng chi phí:

\[
\boxed{Cost(f)=\sum_{e\in E}f_e\,cost_e.}
\]

Luồng phải thỏa **bảo toàn** tại mọi đỉnh khác `s,t`:

\[
\sum_{e:\,to(e)=v}f_e
=
\sum_{e:\,from(e)=v}f_e.
\]

Giá trị luồng là lượng ròng rời nguồn:

\[
|f|=\sum_{e:\,from(e)=s}f_e
-\sum_{e:\,to(e)=s}f_e.
\]

### 2.1. Min-cost flow với lượng yêu cầu F

Cho một giá trị yêu cầu `F\ge0`, cần tìm luồng khả thi thỏa `|f|=F` và có **`Cost(f)` nhỏ nhất**. Nếu mạng không đủ dung lượng, **không có lời giải cho yêu cầu đúng `F`**, dù ta vẫn có thể tìm luồng tối ưu cho lượng nhỏ hơn.

Trong API mẫu, tham số `limit=F` có nghĩa “gửi **nhiều nhất `F`** theo cách tối ưu”. Nếu thuật toán chỉ gửi được `x<F`, trả `flow=x` và trạng thái **không đáp ứng đủ yêu cầu**; không được nói đã giải xong bài toán *exact-F*.

### 2.2. Minimum-cost maximum-flow

Đây là tối ưu từ điển theo hai tiêu chí:

1. Tối đa hóa `|f|`.
2. Trong các luồng có giá trị lớn nhất ấy, tối thiểu hóa `Cost(f)`.

Không phải chỉ tìm luồng có **chi phí tổng nhỏ nhất bất kể lượng**. Nếu mọi cạnh có chi phí dương, luồng `0` có chi phí `0`, nhưng không phải max flow.

Chương trình dùng `limit=null` để gửi tới khi không còn đường tăng luồng, từ đó tìm **min-cost max-flow**. Nếu có giới hạn `F`, chương trình dừng khi đã gửi đủ hoặc không còn đường.

### 2.3. Bài toán chi phí trên đường khác đường ngắn nhất đơn thuần

Một đường có chi phí đơn vị nhỏ nhất chưa đủ mô tả nghiệm cuối. Khi gửi `\Delta` đơn vị trên đường `P`, tổng chi phí thay đổi:

\[
\Delta Cost=\Delta\sum_{a\in P}cost(a).
\]

Thuật toán có thể phải chọn **nhiều đường tăng**, và một đường tăng có thể chứa **cạnh ngược để hoàn tác luồng cũ**. Mỗi lần phải tìm đường ngắn nhất trong **mạng dư hiện tại**, không phải mãi trên đồ thị gốc.

## 3. Mạng dư với cả dung lượng và chi phí

Với mỗi cạnh gốc có hướng `e=(u,v)`, dung lượng `cap_e`, chi phí đơn vị `cost_e` và luồng `f_e`, tạo **hai cung dư riêng**.

**Cung dư thuận** `u\to v`:

\[
r_{\mathrm{forward}}(e)=cap_e-f_e,
\qquad c_{\mathrm{forward}}(e)=cost_e.
\]

**Cung dư ngược** `v\to u`:

\[
r_{\mathrm{reverse}}(e)=f_e,
\qquad c_{\mathrm{reverse}}(e)=-cost_e.
\]

Khi tăng `\Delta` trên cung dư thuận, luồng gốc `f_e` **tăng** `\Delta` và chi phí tăng `\Delta\,cost_e`.

Khi tăng `\Delta` trên cung dư ngược, luồng gốc `f_e` **giảm** `\Delta` và chi phí thay đổi:

\[
\Delta Cost=-\Delta\,cost_e.
\]

Điều này giải thích vì sao **chi phí ngược phải là đối dấu** chứ không phải `0` hay cùng dấu.

### 3.1. Ví dụ cạnh chi phí âm

Cạnh gốc `A\to B` có dung lượng `5` và chi phí `-4`/đơn vị. Nếu đã gửi `3` đơn vị:

```text
Cạnh gốc A -> B:
  capacity = 5, flow = 3, unit cost = -4

Cung dư A -> B:
  residual = 2, unit cost = -4

Cung dư B -> A:
  residual = 3, unit cost = +4
```

Dùng cung ngược `B\to A` với `\Delta=2` làm luồng trên cạnh gốc giảm `3\to1`, nên tổng chi phí tăng `2\cdot4=8` (bớt đi hai đơn vị lợi ích chi phí âm). Đó là cách tính **đúng** theo chi phí gốc.

### 3.2. Cạnh ngược dư không phải cạnh gốc ngược chiều

Nếu đầu vào có cả `u\to v` và `v\to u` như **hai cạnh vật lý độc lập**, mỗi cạnh vẫn tạo **một cặp cung dư riêng**. Không được lấy cạnh gốc `v\to u` làm đối tượng reverse của cạnh gốc `u\to v`.

Ví dụ:

```text
ID 0: u -> v, cap 5, cost 2
ID 1: v -> u, cap 7, cost 9
```

Ta có tổng cộng **4 đối tượng cung dư**:

- ID 0 thuận: `u\to v` chi phí `+2`; ID 0 ngược: `v\to u` chi phí `-2`.
- ID 1 thuận: `v\to u` chi phí `+9`; ID 1 ngược: `u\to v` chi phí `-9`.

Cùng hướng `v\to u` có thể xuất hiện hai cung khác nhau với **chi phí `-2` và `+9`**. Nếu gộp theo cặp đỉnh, ta có thể làm hỏng cả dung lượng, chi phí và thao tác hoàn tác.

### 3.3. Bất biến của một cặp cung dư

Với mỗi cạnh vật lý:

\[
r_{\mathrm{forward}}+r_{\mathrm{reverse}}=cap_e.
\]

Hai chi phí gốc của cặp có tổng bằng `0`:

\[
c_{\mathrm{forward}}+c_{\mathrm{reverse}}=0.
\]

Công thức thứ hai cũng đúng **sau đổi trọng số**, vì:

\[
[c+\pi[u]-\pi[v]]
+[-c+\pi[v]-\pi[u]]=0.
\]

Do đó nếu một cung dư thuận và cung ngược **đều có dư dương**, không thể đòi **cả hai reduced cost đều dương nghiêm ngặt**. Nếu ta duy trì **cả hai không âm**, chúng buộc phải cùng bằng `0`. Đây là một tính chất quan trọng của nghiệm luồng tối ưu cho lượng hiện tại.

## 4. Thế năng đỉnh và reduced cost

Chọn một số `\pi[v]` cho mỗi đỉnh `v`. Với **mỗi cung dư** `a=(u,v)` (thuận hoặc ngược), định nghĩa:

\[
\boxed{c_{\pi}(a)=c(a)+\pi[u]-\pi[v].}
\]

Có tài liệu chọn quy ước dấu ngược:

\[
c'_{\pi}(u,v)=c(u,v)-\pi[u]+\pi[v].
\]

**Cả hai đều có thể đúng**, nhưng công thức cập nhật thế năng phải dùng đúng **cùng một quy ước**. Bài này thống nhất:

\[
\color{#333}{c_{\pi}=c+\pi[\mathrm{from}]-\pi[\mathrm{to}].}
\]

Vì thế, cập nhật ở phần sau là **`\pi[v]\gets\pi[v]+dist_{\pi}(s,v)`**, không phải trừ khoảng cách.

### 4.1. Tại sao đổi trọng số không thay đường ngắn nhất?

Xét một đường dư `P` từ `s=v_0` tới `t=v_k`. Tổng reduced cost:

\[
\begin{aligned}
c_{\pi}(P)
&=\sum_{i=0}^{k-1}\bigl(
 c(v_i,v_{i+1})+\pi[v_i]-\pi[v_{i+1}]
\bigr)\\
&=c(P)+\pi[s]-\pi[t].
\end{aligned}
\]

Các thế năng trung gian **triệt tiêu theo dạng tổng telescoping**. Suy ra:

\[
\boxed{c(P)=c_{\pi}(P)-\pi[s]+\pi[t].}
\]

Với **mọi đường cùng bắt đầu ở `s` và kết thúc ở `t`**, lượng điều chỉnh `\pi[s]-\pi[t]` là **hằng số**. Vì vậy:

\[
\operatorname*{arg\,min}_{P:s\to t} c(P)
=
\operatorname*{arg\,min}_{P:s\to t} c_{\pi}(P).
\]

Đây là lý do ta có thể tìm đường tăng luồng theo reduced cost mà vẫn chọn **đúng đường có chi phí gốc nhỏ nhất**.

**Không kết luận** rằng `c_{\pi}(P)=c(P)`; chúng khác nhau một hằng phụ thuộc hai đầu đường. Khi cộng chi phí nghiệm, phải dùng **`c(P)` gốc** hoặc đổi ngược bằng công thức trên.

### 4.2. Ví dụ đổi trọng số một đường

Giả sử đường có ba cung:

```text
s -> a : cost  4
a -> b : cost -6
b -> t : cost  5

Thế năng:
pi[s] = 0, pi[a] = 2, pi[b] = -3, pi[t] = 1
```

Reduced cost từng cung:

\[
c_{\pi}(s,a)=4+0-2=2,
\]

\[
c_{\pi}(a,b)=-6+2-(-3)=-1,
\]

\[
c_{\pi}(b,t)=5+(-3)-1=1.
\]

Tổng reduced cost là `2-1+1=2`, còn tổng gốc `4-6+5=3`. Công thức telescoping cho:

\[
2=3+\pi[s]-\pi[t]=3+0-1.
\]

**Ví dụ này chỉ minh họa tính bảo toàn thứ tự đường.** Thế năng tùy chọn ở đây tạo một cung reduced cost âm, nên **chưa đủ điều kiện dùng Dijkstra**. Ta cần thế năng **khả thi** ở phần tiếp theo.

## 5. Thế năng khả thi (feasible potential)

Một thế năng `\pi` được gọi là **khả thi cho mạng dư đang xét** nếu với **mọi cung dư có dung lượng dương**:

\[
\boxed{c(a)+\pi[from(a)]-\pi[to(a)]\ge0.}
\]

Viết tương đương:

\[
\pi[v]\le\pi[u]+c(u,v)
\]

cho mọi cung dư dương `u\to v`.

Đây chính là hệ **bất đẳng thức khoảng cách ngắn nhất**. Khi thỏa mãn, mọi reduced cost có thể dùng trong Dijkstra đều **không âm**.

### 5.1. Điều kiện chỉ áp dụng cho cung dư dương

Mạng dư luôn lưu cả cung thuận/ngược của mỗi cạnh gốc, nhưng một số cung có **dung lượng dư bằng `0`**. Những cung ấy **không được dùng** trong đường tăng và không cần bảo đảm reduced cost không âm ở thời điểm đó.

Ví dụ lúc `f_e=0`, cung ngược có dư `0`; chi phí ngược có thể âm nhưng **không được Dijkstra đi qua**. Khi một lần tăng tạo dư dương cho cung ngược, cách cập nhật thế năng phải bảo đảm reduced cost của cung mới dùng được vẫn không âm.

### 5.2. Vì sao thế năng khả thi liên quan chu trình âm?

Tổng các hiệu `\pi[u]-\pi[v]` trên một chu trình bằng `0`. Bởi vậy:

\[
c_{\pi}(C)=c(C)
\]

với mọi chu trình `C`.

Nếu mạng dư có một **chu trình chi phí âm**, tổng reduced cost trên chu trình vẫn âm. Không thể có mọi reduced cost của các cung trên chu trình đều không âm. Vậy:

\[
\boxed{\text{Có chu trình âm trong mạng dư}
\implies\text{không tồn tại thế năng khả thi toàn cục}.}
\]

Ngược lại, nếu mạng dư hữu hạn **không có chu trình âm**, có thể xây thế năng khả thi bằng **khoảng cách ngắn nhất từ một siêu nguồn** có cạnh chi phí `0` tới mọi đỉnh. Bellman–Ford là một cách tìm các khoảng cách đó.

### 5.3. Gắn thế năng với đối ngẫu của bài toán

Có thể xem `\pi[v]` là biến **đối ngẫu (dual variable)** gắn với điều kiện bảo toàn luồng tại đỉnh. Reduced cost đóng vai trò đo chi phí biên sau khi đã điều chỉnh theo các thế năng đỉnh.

- Nếu một cung dư có reduced cost âm, thay đổi luồng theo hướng ấy có thể là dấu hiệu của một khả năng cải thiện chi phí mà biểu diễn thế năng hiện tại chưa xử lý đúng.
- Nếu **mọi cung dư dương đều có reduced cost không âm**, mạng dư không có chu trình âm; vì thế luồng hiện tại là **chi phí nhỏ nhất cho giá trị luồng đang gửi**.
- Các cung có reduced cost bằng `0` là những hướng có thể đổi luồng mà không làm tăng chi phí sau điều chỉnh thế năng, đặc biệt xuất hiện khi tạo cung ngược của đường tăng ngắn nhất.

Không nên nói đơn giản rằng “mọi reduced cost bằng `0` mới tối ưu”. Các cung dư không được dùng hoàn toàn có thể có reduced cost dương; chỉ cần **không có reduced cost âm trên cung dư dương** để bảo đảm tính tối ưu theo giá trị luồng cố định.

## 6. Khởi tạo thế năng bằng Bellman–Ford

### 6.1. Trường hợp mọi chi phí gốc không âm

Khi khởi tạo luồng `f=0`, các cung dư dương duy nhất là những cung thuận của cạnh gốc có dung lượng dương.

Nếu tất cả cạnh gốc có chi phí `\ge0`, đặt:

\[
\boxed{\pi[v]=0\text{ cho mọi }v}
\]

là thế năng khả thi ngay. Không cần Bellman–Ford khởi tạo.

Sau lần tăng đầu, cung ngược có thể có chi phí gốc âm; nhưng nếu cập nhật thế năng đúng, **reduced cost** của nó vẫn không âm.

### 6.2. Nếu có cạnh gốc chi phí âm

Nếu đặt mọi `\pi=0`, reduced cost bằng chi phí gốc; Dijkstra có thể sai nếu một cung có chi phí âm.

Cách thường gặp: chạy **Bellman–Ford từ nguồn `s`** trên mạng dư ban đầu để lấy `dist(s,v)` và đặt `\pi[v]=dist(s,v)` cho các đỉnh tới được. Với các đỉnh không tới được, cần một quy ước và chứng minh riêng nếu muốn duy trì reduced cost không âm **toàn cục**.

Trong chương trình mẫu, ta chọn một cách rõ ràng và mạnh hơn:

> Thêm một **siêu nguồn tưởng tượng** `q`, nối `q\to v` với chi phí `0` tới **mọi đỉnh** `v`. Chạy Bellman–Ford từ `q` để lấy thế năng `\pi[v]`.

Không cần tạo đỉnh/cạnh siêu nguồn thật trong mã. Ta chỉ việc khởi tạo:

```text
pi[v] = 0 cho mọi v
lặp thư giãn các cạnh gốc có capacity > 0
```

Vì mỗi đỉnh đã có đường chi phí `0` từ siêu nguồn, mọi đỉnh có khoảng cách hữu hạn; cạnh có chi phí âm có thể kéo thế năng của đỉnh xuống dưới `0`.

### 6.3. Bất biến Bellman–Ford

Với mạng ban đầu không chứa chu trình chi phí âm trên các cung dư dương:

\[
\pi[v]\le\pi[u]+c(u,v)
\]

trên mọi cung dư dương, tức:

\[
c_{\pi}(u,v)\ge0.
\]

Vì thế, sau khi khởi tạo thế năng, ta có thể gọi Dijkstra cho lần tăng luồng đầu tiên.

### 6.4. Nếu Bellman–Ford phát hiện chu trình âm

Chương trình minh họa **từ chối** một mạng có chu trình chi phí âm với dung lượng dương **ở trạng thái luồng ban đầu**. Đây là **giới hạn có chủ đích** của biến thể SSP sử dụng thế năng khả thi toàn cục.

Tại sao không cứ bỏ qua chu trình âm?

Ví dụ `s=0,t=3`, có một chu trình âm `1\to2\to1` không nằm trên bất kỳ đường `s\to t` nào. Nếu mô hình cho phép **circulation** (luồng chạy vòng và không làm thay đổi giá trị luồng), ta có thể gửi lượng tối đa cho phép quanh chu trình âm để giảm tổng chi phí mà không đổi `|f|`. Một thuật toán chỉ thêm các đường `s\to t` và không xử lý chu trình âm có thể bỏ lỡ nghiệm min-cost toàn cục.

Có các kỹ thuật khác như **cycle canceling** hoặc các biến thể min-cost circulation để xử lý bài toán tổng quát hơn. Chương trình này không tự nhận đã giải trường hợp đó; nó báo lỗi rõ.

**Cạnh chi phí âm đơn lẻ không phải lý do từ chối.** Một DAG có thể có nhiều cạnh âm mà không chứa chu trình, và Bellman–Ford vẫn khởi tạo được thế năng khả thi.

## 7. Dijkstra trên mạng dư đã đổi trọng số

Sau khi có thế năng khả thi, mỗi lần cần tìm đường tăng từ `s` tới `t`:

1. Chỉ xét **cung dư `r(a)>0`**.
2. Tính reduced cost của cung ấy:

\[
c_{\pi}(a)=c(a)+\pi[from]-\pi[to].
\]

3. Chạy **Dijkstra** với trọng số `c_{\pi}(a)\ge0`.
4. Lưu **đối tượng cung cha cụ thể** `parentArc[v]` cho mỗi đỉnh `v`.
5. Nếu `t` không tới được, không còn đường tăng luồng.
6. Nếu `t` tới được, lần ngược `parentArc` lấy đường `P` có chi phí **gốc nhỏ nhất** trong mạng dư hiện tại.

### 7.1. Vì sao parentArc không chỉ là parentVertex?

Mạng có thể có:

- Nhiều cạnh gốc song song cùng chiều.
- Một cạnh gốc theo chiều `u\to v` và một cạnh gốc khác `v\to u`.
- Cung dư ngược của một cạnh có cùng hướng với cung dư thuận của cạnh khác.

Chỉ lưu đỉnh cha `parentVertex[v]` không nói được **cung cụ thể** nào được chọn và cần điều chỉnh dung lượng của cặp nào.

Mẫu Java lưu cả `from` trong mỗi cung dư và `parentArc[to]`, nên truy vết đúng đối tượng, đúng chi phí và đúng cặp reverse.

### 7.2. Dijkstra phải chạy tới hết những đỉnh tới được

Trong nhiều bài đường đi ngắn nhất, có thể dừng Dijkstra ngay khi lấy đỉnh `t` ra khỏi hàng đợi ưu tiên. Nhưng ở cách cập nhật thế năng trong bài này, ta cần **khoảng cách tới mọi đỉnh còn tới được từ `s`**, không chỉ `t`.

Do đó, chương trình **không dừng sớm tại `t`**. Nó tính trọn mảng `dist_{\pi}[v]` để dùng trong cập nhật thế năng **toàn cục**.

Nếu dừng sớm rồi dùng những khoảng cách còn **chưa chốt**, có thể phá bất biến reduced cost không âm ở một số cung dư, khiến lần Dijkstra kế tiếp không còn hợp lệ.

## 8. Cập nhật thế năng sau Dijkstra

Gọi `d[v]` là khoảng cách từ `s` tới `v` bằng **reduced cost hiện tại** trong mạng dư, đối với những đỉnh còn tới được.

Đối với đỉnh tới được, cập nhật cơ bản:

\[
\boxed{\pi_{\mathrm{new}}[v]
=\pi_{\mathrm{old}}[v]+d[v].}
\]

Với quy ước `c_{\pi}=c+\pi[u]-\pi[v]`, **cộng** `d[v]` là đúng dấu.

### 8.1. Chứng minh reduced cost mới không âm trên cung tới được

Với một cung dư dương `u\to v` mà cả hai đỉnh đều tới được từ `s`, tính chất đường đi ngắn nhất cho:

\[
d[v]\le d[u]+c_{\pi_{\mathrm{old}}}(u,v).
\]

Vì thế:

\[
\begin{aligned}
c_{\pi_{\mathrm{new}}}(u,v)
&=c_{\pi_{\mathrm{old}}}(u,v)+d[u]-d[v]\\
&\ge0.
\end{aligned}
\]

Vậy sau khi cộng các khoảng cách Dijkstra, reduced cost trên các cung có thể được dùng từ vùng tới được vẫn không âm.

### 8.2. Đỉnh không tới được: một bẫy khi cài đặt

Một cách cài phổ biến chỉ cập nhật:

```text
if dist[v] hữu hạn:
    pi[v] += dist[v]
```

Điều này đủ trong một số chứng minh và thiết kế **chỉ yêu cầu reduced cost không âm ở vùng tới được từ s**. Nhưng nó không tự bảo đảm mọi cung dư dương trên **toàn đồ thị** đều có reduced cost không âm, đặc biệt cung từ vùng không tới được vào vùng tới được.

Để có một bất biến **toàn cục**, mã trong bài dùng một quy tắc đồng nhất:

Đặt:

\[
M=\max_{\{v:d[v]\text{ hữu hạn}\}}d[v].
\]

Vì các reduced cost không âm, `d[s]=0`, nên `M\ge0`. Cập nhật:

\[
\boxed{
\pi_{\mathrm{new}}[v]=
\begin{cases}
\pi_{\mathrm{old}}[v]+d[v],
&v\text{ tới được},\\
\pi_{\mathrm{old}}[v]+M,
&v\text{ không tới được}.
\end{cases}
}
\]

### 8.3. Vì sao cách cập nhật cả đỉnh không tới được giữ tính khả thi?

Xét một cung dư dương `u\to v`. Có bốn trường hợp:

1. **Cả `u,v` tới được:** nhờ bất đẳng thức tam giác của Dijkstra, reduced cost mới không âm.
2. **Cả `u,v` không tới được:** cả hai thế năng đều cộng `M`, nên reduced cost **không đổi**.
3. **`u` không tới được, `v` tới được:** reduced cost mới bằng reduced cost cũ cộng `M-d[v]\ge0`. Do cả hai hạng không âm, vẫn hợp lệ.
4. **`u` tới được, `v` không tới được:** **không thể tồn tại cung dư dương như vậy**. Nếu có, từ nguồn đi tới `u` rồi qua cung đó sẽ tới được `v`, mâu thuẫn với việc `v` không tới được.

Vậy sau khi cập nhật theo quy tắc `M`, **tất cả cung dư đang có dung lượng dương** vẫn có reduced cost không âm.

### 8.4. Cung ngược được kích hoạt sau khi tăng thì sao?

Một đường tăng `P` do Dijkstra tìm được gồm các cung đang có dung lượng dư dương. Với mỗi cung `u\to v` nằm trên **đường ngắn nhất** theo cây cha:

\[
d[v]=d[u]+c_{\pi_{\mathrm{old}}}(u,v).
\]

Sau khi cập nhật thế năng:

\[
c_{\pi_{\mathrm{new}}}(u,v)
=c_{\pi_{\mathrm{old}}}(u,v)+d[u]-d[v]=0.
\]

Khi ta tăng luồng, dung lượng dư của cung này giảm và dung lượng của **cung ngược** tăng. Vì hai reduced cost của một cặp cung đối nhau, **cung ngược vừa được kích hoạt cũng có reduced cost bằng `0`**.

Đây là lý do việc tạo các cung ngược có **chi phí gốc âm** không phá Dijkstra: điều mà Dijkstra nhìn thấy ở vòng kế tiếp là **reduced cost không âm**, không phải chi phí gốc.

### 8.5. Trình tự đúng trong một lần tăng

```text
1. Dijkstra trên residual hiện tại theo reduced cost.
2. Nếu sink unreachable: kết thúc.
3. Lấy đường cha, bottleneck và tổng chi phí gốc đường.
4. Cập nhật potential dùng tất cả khoảng cách Dijkstra.
5. Trừ delta khỏi residual các cung trên đường.
6. Cộng delta vào residual của cung reverse.
7. flow += delta
8. totalCost += delta * originalPathCost
```

Có thể hoán đổi một số thao tác nếu chứng minh tương đương, nhưng không được dùng **khoảng cách Dijkstra đã lỗi thời** sau khi sửa mạng dư hoặc tính chi phí nghiệm bằng reduced cost mà quên bù thế năng.

## 9. Một ví dụ có cạnh âm và cần hoàn tác luồng

Xét mạng bốn đỉnh `s=0`, `a=1`, `b=2`, `t=3`, mỗi cạnh có dung lượng `1`:

| ID | Cạnh gốc | Dung lượng | Chi phí đơn vị |
|---:|---|---:|---:|
| 0 | `0\to1` | 1 | 0 |
| 1 | `0\to2` | 1 | 0 |
| 2 | `1\to2` | 1 | -2 |
| 3 | `1\to3` | 1 | 0 |
| 4 | `2\to3` | 1 | 0 |

Mạng cho phép gửi tổng cộng **2 đơn vị**, vì có hai cạnh đi ra nguồn và hai cạnh đi vào đích, mỗi cạnh capacity `1`.

### 9.1. Thế năng ban đầu bằng Bellman–Ford

Khởi tạo khoảng cách siêu nguồn `0` tới mọi đỉnh bằng `0` rồi relax cạnh có chi phí âm `1\to2`:

```text
pi[0]=0, pi[1]=0, pi[2]=-2, pi[3]=-2.
```

Giá trị `pi[3]=-2` đến từ đường `1\to2\to3` sau khi siêu nguồn tưởng tượng nối chi phí `0` tới `1`.

Reduced cost các cạnh gốc đang có dư:

| ID | Chi phí gốc | Reduced cost |
|---:|---:|---:|
| 0: `0→1` | 0 | `0+0-0=0` |
| 1: `0→2` | 0 | `0+0-(-2)=2` |
| 2: `1→2` | -2 | `-2+0-(-2)=0` |
| 3: `1→3` | 0 | `0+0-(-2)=2` |
| 4: `2→3` | 0 | `0+(-2)-(-2)=0` |

Tất cả reduced cost đều **không âm**, nên Dijkstra hợp lệ.

### 9.2. Đường tăng đầu: chi phí âm

Dijkstra tìm:

\[
P_1=0\to1\to2\to3,
\]

với tổng reduced cost `0`, nhưng **tổng chi phí gốc**:

\[
c(P_1)=0+(-2)+0=-2.
\]

Theo công thức đổi trọng số:

\[
c(P_1)=c_{\pi}(P_1)-\pi[0]+\pi[3]
=0-0-2=-2.
\]

Bottleneck `\Delta_1=1`, nên:

\[
flow=1,\qquad totalCost=-2.
\]

Cạnh ID 2 `1\to2` bão hòa và tạo **cung dư ngược `2\to1` chi phí gốc `+2`**.

### 9.3. Đường tăng thứ hai: dùng cạnh ngược

Sau lần đầu, để tăng thêm, đường dư còn khả thi là:

\[
P_2=0\to2\to1\to3,
\]

trong đó bước **`2\to1` là cung dư ngược của ID 2**, có chi phí gốc `+2`.

Tổng chi phí gốc:

\[
c(P_2)=0+(+2)+0=+2.
\]

Tăng thêm `\Delta_2=1`:

\[
flow=2,\qquad totalCost=-2+2=0.
\]

Luồng cuối trên các cạnh gốc là:

```text
ID 0 (0->1): 1
ID 1 (0->2): 1
ID 2 (1->2): 0   <- đã hoàn tác
ID 3 (1->3): 1
ID 4 (2->3): 1

Tổng giá trị luồng = 2
Tổng chi phí gốc = 0
```

Thực tế hai đơn vị luồng cuối đi:

```text
0 -> 1 -> 3 : 1 đơn vị, chi phí 0
0 -> 2 -> 3 : 1 đơn vị, chi phí 0
```

Không thể tiếp tục giữ đường chi phí `-2` và vẫn gửi thêm đơn vị thứ hai, vì `1\to2` chiếm mất khả năng phân phối giữa hai nhánh. Cung ngược cho phép **đổi lại một phần lựa chọn cũ** để tối đa hóa lượng.

### 9.4. Thế năng sau lần tăng thứ hai

Sau lần đầu, thế năng vẫn là `[0,0,-2,-2]`. Trong lần Dijkstra thứ hai, các khoảng cách reduced cost từ nguồn là:

```text
d[0]=0, d[2]=2, d[1]=2, d[3]=4.
```

Cập nhật:

\[
\pi_{\mathrm{new}}=[0,2,0,2].
\]

Cung ngược `2\to1` đã được dùng trong đường tăng có reduced cost bằng `0` theo thế năng mới. Tất cả cung dư dương còn lại tiếp tục có reduced cost không âm.

### 9.5. Vì sao chi phí tổng có thể tăng khi tăng lượng luồng?

Hàm chi phí tối ưu theo lượng `F` không nhất thiết giảm theo `F`. Ví dụ:

| Lượng gửi | Chi phí nhỏ nhất cho đúng lượng đó |
|---:|---:|
| 0 | 0 |
| 1 | -2 |
| 2 | 0 |

Đường tăng thứ hai có chi phí biên `+2`. Như vậy muốn đạt max flow `2`, ta phải chấp nhận tổng cost tăng từ `-2` lên `0`. Đừng nhầm mục tiêu **min-cost max-flow** với việc “dừng khi đường tăng có chi phí dương” — làm vậy có thể chỉ tìm được một luồng rẻ nhưng **chưa cực đại**.

## 10. Bất biến tối ưu theo lượng và chứng minh thuật toán SSP

### 10.1. Bất biến của mạng dư

Sau mỗi lần tăng:

1. Luồng gốc hợp lệ: `0\le f_e\le cap_e`.
2. Bảo toàn luồng tại mọi đỉnh trung gian.
3. Cặp cung dư của mỗi cạnh có `r_{\rm forward}=cap_e-f_e` và `r_{\rm reverse}=f_e`.
4. Chi phí ngược của mỗi cung là đối dấu với cung thuận; chi phí đã đổi của cặp cũng đối nhau.
5. Thế năng khả thi: mọi cung dư dương có `c_{\pi}\ge0`.
6. Trong số các luồng có **cùng giá trị đã gửi**, luồng đang có **chi phí nhỏ nhất**.

Bất biến (6) mạnh hơn khả thi đơn thuần, và là mục tiêu chính của min-cost flow.

### 10.2. Cơ sở tại luồng 0

Bài này giả định **mạng ban đầu không có chu trình chi phí âm với dung lượng dương**, nên luồng `0` có chi phí `0` là tối ưu trong số các luồng giá trị `0`. Nếu có một circulation chi phí âm, luồng giá trị `0` có thể đạt tổng chi phí âm bằng cách gửi vòng; do đó giả định “không có chu trình âm” là quan trọng.

Bellman–Ford từ siêu nguồn tìm một thế năng khả thi. Không có cung dư âm theo reduced cost, nên bất biến khởi đầu được thiết lập.

### 10.3. Bước tăng bằng đường ngắn nhất

Giả sử luồng hiện tại tối ưu cho giá trị `F` và ta muốn tăng thêm `\Delta`. Mạng dư biểu diễn mọi thay đổi hợp lệ của luồng, gồm gửi thêm trên cạnh gốc và hoàn tác trên cung ngược.

Dijkstra theo reduced cost tìm đường `s\to t` có **chi phí gốc nhỏ nhất** (do tổng các hiệu thế năng triệt tiêu). Tăng `\Delta` bằng bottleneck, hoặc ít hơn nếu đã gần đạt lượng yêu cầu.

Cập nhật thế năng bằng khoảng cách Dijkstra giữ mọi reduced cost dương ở mức không âm; các cung ngược mới kích hoạt trên đường ngắn nhất có reduced cost `0`. Do đó mạng dư sau tăng **không có chu trình chi phí âm**.

Một định lý chuẩn về min-cost flow phát biểu:

\[
\boxed{
f\text{ tối ưu cho một lượng cố định}
\iff
\text{mạng dư của }f
\text{ không chứa chu trình chi phí âm}.
}
\]

**Chiều ⇒:** nếu có chu trình âm với dư dương, đẩy một lượng dương quanh chu trình không thay giá trị luồng, nhưng giảm chi phí, mâu thuẫn tối ưu.

**Chiều ⇐:** giả sử có luồng khác `g` cùng giá trị mà rẻ hơn. Hiệu `g-f` biểu diễn một **circulation trong mạng dư** của `f`, có thể phân rã thành các chu trình có hướng với lượng không âm. Nếu chi phí tổng hiệu âm, phải có ít nhất một chu trình âm, mâu thuẫn.

Nhờ duy trì thế năng khả thi, mạng dư sau mỗi lần tăng không có chu trình âm, nên luồng mới tối ưu cho lượng `F+\Delta`.

### 10.4. Dừng khi không còn đường dư

Nếu không còn đường tăng luồng `s\to t` trong mạng dư, theo định lý **max-flow/min-cut**, giá trị hiện tại là **max flow**.

Kết hợp:

- Không còn đường tăng ⇒ **giá trị cực đại**.
- Không còn chu trình chi phí âm ⇒ **chi phí nhỏ nhất trong các luồng có giá trị đó**.

Vì vậy, nghiệm cuối là **min-cost maximum-flow**.

Nếu dừng chỉ vì đã gửi đủ `limit=F`, ta có luồng **min-cost cho đúng `F`** trong điều kiện đã gửi được đủ, nhưng không được tuyên bố nó là max flow khi chưa xác minh không còn đường dư.

## 11. Mã Java 17+ hoàn chỉnh: Dijkstra, thế năng và cạnh ngược

Chương trình bên dưới thực hiện một biến thể **successive shortest augmenting path với feasible potentials toàn cục**:

- Mỗi cạnh gốc có **một cặp Arc thuận/ngược riêng**, bao gồm cạnh song song, cạnh ngược chiều thật và khuyên.
- Dung lượng đầu vào là `long\ge0`; đơn giá đầu vào là `long` có dấu.
- Dùng **`BigInteger`** cho dung lượng dư, thế năng, khoảng cách, bottleneck, chi phí đường và tổng chi phí. Cách này tránh tràn khi tổng luồng vượt `Long.MAX_VALUE` hoặc khi tạo chi phí ngược của `Long.MIN_VALUE`.
- Bellman–Ford với mọi `\pi[v]=0` tương đương siêu nguồn nối tất cả đỉnh chi phí `0`; từ chối chu trình chi phí âm ban đầu.
- Dijkstra dùng `c_{\pi}\ge0` và tính khoảng cách tới **mọi đỉnh tới được**, không dừng sớm ở đích.
- Cập nhật `\pi[v]` bằng `d[v]` cho đỉnh tới được và `M=\max d[v]` cho đỉnh không tới được, duy trì feasible potentials **toàn cục**.
- Khi tăng, ghi lịch sử đường với ký hiệu **F** (forward) và **R** (reverse), ID cạnh gốc và chi phí đơn vị gốc của đường.
- Sau mỗi lần tăng, kiểm tra reduced cost không âm; cuối thuật toán kiểm tra dung lượng, bảo toàn và tổng chi phí tính lại từ cạnh gốc.
- Khi hết đường tăng, trích xuất min-cut từ tập nguồn tới được, kiểm tra `flow=cutCapacity`. Khi dừng sớm ở `limit`, **không** tự khẳng định đã cực đại.
- Có oracle vét cạn trên mạng nhỏ để đối chiếu cả **giá trị luồng** lẫn **chi phí nhỏ nhất**.

**Hợp đồng:** `n\ge2`, `s,t` hợp lệ và khác nhau; capacity không âm; tổng cost không bị giới hạn trong `long`. Nếu đầu vào có chu trình cost âm với capacity dương, solver **ném ngoại lệ** để tránh giải sai trường hợp yêu cầu cycle canceling. `limit=null` có nghĩa tìm min-cost max-flow; `limit=F\ge0` có nghĩa gửi tối đa `F` đơn vị, ưu tiên đạt lượng lớn nhất trong giới hạn rồi tối ưu chi phí.

Tên tệp **`MinCostFlowPotentialsDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Random;

public final class MinCostFlowPotentialsDemo {
    private MinCostFlowPotentialsDemo() {
    }

    public record InputEdge(
            int from, int to, long capacity, long unitCost) {
    }

    public record Step(
            int from, int to, int edgeId, boolean reverse) {
    }

    public record Augment(
            BigInteger delta,
            BigInteger pathUnitCost,
            List<Step> path) {
        public Augment {
            path = List.copyOf(path);
        }
    }

    public record Result(
            BigInteger flow,
            BigInteger totalCost,
            List<BigInteger> edgeFlows,
            List<Augment> history,
            List<BigInteger> finalPotential,
            boolean maximal,
            List<Integer> sourceSide,
            BigInteger cutCapacity) {
        public Result {
            edgeFlows = List.copyOf(edgeFlows);
            history = List.copyOf(history);
            finalPotential = List.copyOf(finalPotential);
            sourceSide = List.copyOf(sourceSide);
        }
    }

    private static final class Arc {
        final int from;
        final int to;
        final int edgeId;
        final boolean original;
        final BigInteger cost;
        BigInteger residual;
        Arc reverse;

        Arc(int from, int to, int edgeId,
                boolean original,
                BigInteger residual, BigInteger cost) {
            this.from = from;
            this.to = to;
            this.edgeId = edgeId;
            this.original = original;
            this.residual = residual;
            this.cost = cost;
        }
    }

    private record State(int vertex, BigInteger distance) {
    }

    private record Search(BigInteger[] dist, Arc[] parent) {
    }

    private static void validate(
            int n, List<InputEdge> input,
            int s, int t, BigInteger limit) {
        Objects.requireNonNull(input, "input");
        if (n < 2 || s < 0 || s >= n
                || t < 0 || t >= n || s == t) {
            throw new IllegalArgumentException(
                "invalid source, sink or vertex count"
            );
        }
        if (limit != null && limit.signum() < 0) {
            throw new IllegalArgumentException(
                "flow limit must be nonnegative"
            );
        }
        for (InputEdge e : input) {
            Objects.requireNonNull(e, "input edge");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n
                    || e.capacity() < 0) {
                throw new IllegalArgumentException(
                    "invalid edge endpoint or capacity"
                );
            }
        }
    }

    // Tương đương Bellman-Ford từ siêu nguồn q
    // với cạnh q->v chi phí 0 tới mọi đỉnh.
    private static BigInteger[] initialPotential(
            int n, List<Arc> originals) {
        BigInteger[] pi = new BigInteger[n];
        Arrays.fill(pi, BigInteger.ZERO);

        for (int pass = 0; pass < n; pass++) {
            boolean changed = false;

            for (Arc a : originals) {
                if (a.residual.signum() == 0) {
                    continue;
                }
                BigInteger candidate =
                    pi[a.from].add(a.cost);

                if (candidate.compareTo(pi[a.to]) < 0) {
                    pi[a.to] = candidate;
                    changed = true;
                }
            }

            if (!changed) {
                return pi;
            }
            if (pass == n - 1) {
                throw new IllegalArgumentException(
                    "negative-cost cycle in initial network"
                );
            }
        }
        return pi;
    }

    private static BigInteger reducedCost(
            Arc a, BigInteger[] pi) {
        return a.cost
            .add(pi[a.from])
            .subtract(pi[a.to]);
    }

    // Đảm bảo mọi cung dư dương đều có reduced cost >= 0.
    private static void assertFeasiblePotential(
            List<List<Arc>> graph, BigInteger[] pi) {
        for (List<Arc> arcs : graph) {
            for (Arc a : arcs) {
                if (a.residual.signum() > 0
                        && reducedCost(a, pi).signum() < 0) {
                    throw new IllegalStateException(
                        "negative reduced cost on usable arc"
                    );
                }
            }
        }
    }

    private static Search dijkstra(
            List<List<Arc>> graph, int source,
            BigInteger[] pi) {
        int n = graph.size();
        BigInteger[] dist = new BigInteger[n];
        Arc[] parent = new Arc[n];

        Comparator<State> byDistance = (a, b) -> {
            int cmp =
                a.distance().compareTo(b.distance());
            return cmp != 0
                ? cmp
                : Integer.compare(a.vertex(), b.vertex());
        };

        PriorityQueue<State> pq =
            new PriorityQueue<>(byDistance);
        dist[source] = BigInteger.ZERO;
        pq.add(new State(source, BigInteger.ZERO));

        // Không dừng sớm tại sink: cần mọi dist[v] hữu hạn.
        while (!pq.isEmpty()) {
            State current = pq.poll();
            int u = current.vertex();

            if (!current.distance().equals(dist[u])) {
                continue;
            }

            for (Arc a : graph.get(u)) {
                if (a.residual.signum() <= 0) {
                    continue;
                }
                BigInteger w = reducedCost(a, pi);
                if (w.signum() < 0) {
                    throw new IllegalStateException(
                        "Dijkstra requires nonnegative weights"
                    );
                }

                BigInteger candidate = dist[u].add(w);
                if (dist[a.to] == null
                        || candidate.compareTo(
                            dist[a.to]) < 0) {
                    dist[a.to] = candidate;
                    parent[a.to] = a;
                    pq.add(new State(a.to, candidate));
                }
            }
        }
        return new Search(dist, parent);
    }

    private static boolean[] reachable(
            List<List<Arc>> graph, int source) {
        boolean[] seen = new boolean[graph.size()];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        seen[source] = true;
        q.addLast(source);

        while (!q.isEmpty()) {
            int u = q.removeFirst();
            for (Arc a : graph.get(u)) {
                if (a.residual.signum() > 0
                        && !seen[a.to]) {
                    seen[a.to] = true;
                    q.addLast(a.to);
                }
            }
        }
        return seen;
    }

    public static Result solve(
            int n, List<InputEdge> input,
            int s, int t, BigInteger limit) {
        validate(n, input, s, t, limit);

        List<List<Arc>> graph = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            graph.add(new ArrayList<>());
        }

        List<Arc> originals = new ArrayList<>();
        for (int id = 0; id < input.size(); id++) {
            InputEdge e = input.get(id);
            BigInteger cost =
                BigInteger.valueOf(e.unitCost());

            Arc forward = new Arc(
                e.from(), e.to(), id, true,
                BigInteger.valueOf(e.capacity()), cost
            );
            Arc backward = new Arc(
                e.to(), e.from(), id, false,
                BigInteger.ZERO, cost.negate()
            );

            forward.reverse = backward;
            backward.reverse = forward;
            graph.get(e.from()).add(forward);
            graph.get(e.to()).add(backward);
            originals.add(forward);
        }

        BigInteger[] pi = initialPotential(
            n, originals
        );
        assertFeasiblePotential(graph, pi);

        BigInteger flow = BigInteger.ZERO;
        BigInteger totalCost = BigInteger.ZERO;
        List<Augment> history = new ArrayList<>();
        boolean maximal = false;

        while (limit == null
                || flow.compareTo(limit) < 0) {
            Search search = dijkstra(graph, s, pi);

            if (search.dist()[t] == null) {
                maximal = true;
                break;
            }

            BigInteger delta = null;
            BigInteger pathUnitCost = BigInteger.ZERO;
            List<Step> reverseOrder = new ArrayList<>();

            for (int v = t; v != s; ) {
                Arc a = search.parent()[v];
                if (a == null) {
                    throw new IllegalStateException(
                        "missing parent arc"
                    );
                }

                if (delta == null
                        || a.residual.compareTo(delta) < 0) {
                    delta = a.residual;
                }
                pathUnitCost =
                    pathUnitCost.add(a.cost);
                reverseOrder.add(new Step(
                    a.from, a.to, a.edgeId, !a.original
                ));
                v = a.from;
            }

            if (delta == null || delta.signum() <= 0) {
                throw new IllegalStateException(
                    "invalid bottleneck"
                );
            }
            if (limit != null) {
                BigInteger remaining = limit.subtract(flow);
                if (remaining.compareTo(delta) < 0) {
                    delta = remaining;
                }
            }

            // Kiểm tra quy tắc telescoping trước khi
            // thay đổi thế năng.
            BigInteger fromReduced =
                search.dist()[t]
                    .subtract(pi[s]).add(pi[t]);
            if (!pathUnitCost.equals(fromReduced)) {
                throw new IllegalStateException(
                    "wrong reduced-cost conversion"
                );
            }

            // Cập nhật toàn cục: đỉnh unreachable cộng M.
            BigInteger maxDistance = BigInteger.ZERO;
            for (BigInteger d : search.dist()) {
                if (d != null
                        && d.compareTo(maxDistance) > 0) {
                    maxDistance = d;
                }
            }

            for (int v = 0; v < n; v++) {
                BigInteger shift = search.dist()[v] != null
                    ? search.dist()[v] : maxDistance;
                pi[v] = pi[v].add(shift);
            }

            Collections.reverse(reverseOrder);
            for (int v = t; v != s; ) {
                Arc a = search.parent()[v];
                a.residual = a.residual.subtract(delta);
                a.reverse.residual =
                    a.reverse.residual.add(delta);
                v = a.from;
            }

            flow = flow.add(delta);
            totalCost = totalCost.add(
                delta.multiply(pathUnitCost)
            );
            history.add(new Augment(
                delta, pathUnitCost, reverseOrder
            ));

            assertFeasiblePotential(graph, pi);
        }

        List<BigInteger> edgeFlows = new ArrayList<>();
        BigInteger[] net = new BigInteger[n];
        Arrays.fill(net, BigInteger.ZERO);
        BigInteger recomputedCost = BigInteger.ZERO;

        for (int id = 0; id < input.size(); id++) {
            InputEdge e = input.get(id);
            Arc a = originals.get(id);
            BigInteger f = a.reverse.residual;
            BigInteger cap =
                BigInteger.valueOf(e.capacity());

            if (f.signum() < 0 || f.compareTo(cap) > 0) {
                throw new IllegalStateException(
                    "capacity invariant violated"
                );
            }
            edgeFlows.add(f);
            net[e.from()] = net[e.from()].add(f);
            net[e.to()] = net[e.to()].subtract(f);

            recomputedCost = recomputedCost.add(
                f.multiply(BigInteger.valueOf(e.unitCost()))
            );
        }

        for (int v = 0; v < n; v++) {
            BigInteger expected = v == s
                ? flow
                : v == t ? flow.negate() : BigInteger.ZERO;
            if (!net[v].equals(expected)) {
                throw new IllegalStateException(
                    "flow conservation violated"
                );
            }
        }
        if (!recomputedCost.equals(totalCost)) {
            throw new IllegalStateException(
                "total cost does not match original edges"
            );
        }

        List<Integer> sourceSide = new ArrayList<>();
        BigInteger cutCapacity = null;

        if (maximal) {
            boolean[] seen = reachable(graph, s);
            if (seen[t]) {
                throw new IllegalStateException(
                    "sink still reachable"
                );
            }

            cutCapacity = BigInteger.ZERO;
            for (int v = 0; v < n; v++) {
                if (seen[v]) {
                    sourceSide.add(v);
                }
            }
            for (InputEdge e : input) {
                if (seen[e.from()] && !seen[e.to()]) {
                    cutCapacity = cutCapacity.add(
                        BigInteger.valueOf(e.capacity())
                    );
                }
            }
            if (!flow.equals(cutCapacity)) {
                throw new IllegalStateException(
                    "max-flow/min-cut mismatch"
                );
            }
        }

        return new Result(
            flow, totalCost, edgeFlows, history,
            Arrays.asList(pi.clone()),
            maximal, sourceSide, cutCapacity
        );
    }

    private static String pathText(List<Step> path) {
        List<String> parts = new ArrayList<>();
        for (Step step : path) {
            parts.add(
                step.from() + "->" + step.to()
                + "[" + (step.reverse() ? "R" : "F")
                + step.edgeId() + "]"
            );
        }
        return String.join(" ", parts);
    }

    // Oracle độc lập cho dữ liệu cực nhỏ: duyệt toàn bộ
    // cách gán flow nguyên lên các cạnh vật lý.
    private static void enumerate(
            int id, List<InputEdge> edges,
            long[] net, long cost,
            int s, int t, Map<Long, Long> best) {
        if (id == edges.size()) {
            long value = net[s];
            if (value < 0 || net[t] != -value) {
                return;
            }
            for (int v = 0; v < net.length; v++) {
                if (v != s && v != t && net[v] != 0) {
                    return;
                }
            }
            best.merge(value, cost, Math::min);
            return;
        }

        InputEdge e = edges.get(id);
        for (int f = 0; f <= e.capacity(); f++) {
            net[e.from()] += f;
            net[e.to()] -= f;

            enumerate(
                id + 1, edges, net,
                cost + f * e.unitCost(), s, t, best
            );

            net[e.from()] -= f;
            net[e.to()] += f;
        }
    }

    private static Map<Long, Long> bruteCosts(
            int n, List<InputEdge> edges, int s, int t) {
        if (edges.size() > 8) {
            throw new IllegalArgumentException(
                "brute force: at most 8 edges"
            );
        }
        for (InputEdge e : edges) {
            if (e.capacity() > 2) {
                throw new IllegalArgumentException(
                    "brute force: capacity <= 2"
                );
            }
        }
        Map<Long, Long> best = new HashMap<>();
        enumerate(
            0, edges, new long[n], 0L, s, t, best
        );
        return best;
    }

    public static void main(String[] args) {
        List<InputEdge> main = List.of(
            new InputEdge(0, 1, 1, 0),  // ID 0
            new InputEdge(0, 2, 1, 0),  // ID 1
            new InputEdge(1, 2, 1, -2), // ID 2
            new InputEdge(1, 3, 1, 0),  // ID 3
            new InputEdge(2, 3, 1, 0)   // ID 4
        );

        Result full = solve(4, main, 0, 3, null);
        System.out.println(
            "Main: flow=" + full.flow()
            + " cost=" + full.totalCost()
            + " maximal=" + full.maximal()
        );
        for (int i = 0; i < full.history().size(); i++) {
            Augment a = full.history().get(i);
            System.out.println(
                "Augment " + (i + 1)
                + ": delta=" + a.delta()
                + " pathCost=" + a.pathUnitCost()
                + " path=" + pathText(a.path())
            );
        }
        System.out.println(
            "Main edge flows: " + full.edgeFlows()
        );
        System.out.println(
            "Main final potential: " + full.finalPotential()
        );
        System.out.println(
            "Main min-cut side: " + full.sourceSide()
        );
        System.out.println(
            "Main min-cut capacity: " + full.cutCapacity()
        );

        Result one = solve(
            4, main, 0, 3, BigInteger.ONE
        );
        System.out.println(
            "Limit 1: flow=" + one.flow()
            + " cost=" + one.totalCost()
        );

        Result needThree = solve(
            4, main, 0, 3, BigInteger.valueOf(3)
        );
        System.out.println(
            "Demand 3: flow=" + needThree.flow()
            + " cost=" + needThree.totalCost()
            + " complete=" + needThree.flow().equals(
                BigInteger.valueOf(3)
            )
        );

        List<InputEdge> mixed = List.of(
            new InputEdge(0, 1, 2, 5),
            new InputEdge(0, 1, 1, -1),
            new InputEdge(1, 2, 3, 2),
            new InputEdge(2, 1, 4, 7),
            new InputEdge(1, 1, 1, 0)
        );
        Result mixedResult = solve(3, mixed, 0, 2, null);
        System.out.println(
            "Mixed: flow=" + mixedResult.flow()
            + " cost=" + mixedResult.totalCost()
        );
        System.out.println(
            "Mixed edge flows: " + mixedResult.edgeFlows()
        );

        List<InputEdge> huge = List.of(
            new InputEdge(0, 1, Long.MAX_VALUE, -3),
            new InputEdge(0, 1, Long.MAX_VALUE, -3)
        );
        Result big = solve(2, huge, 0, 1, null);
        System.out.println(
            "Huge: flow=" + big.flow()
            + " cost=" + big.totalCost()
        );

        Result empty = solve(
            3, List.of(), 0, 2, null
        );
        System.out.println(
            "Empty: flow=" + empty.flow()
            + " cost=" + empty.totalCost()
            + " maximal=" + empty.maximal()
        );

        boolean cycleRejected = false;
        try {
            solve(3, List.of(
                new InputEdge(0, 1, 1, -4),
                new InputEdge(1, 0, 1, 1)
            ), 0, 2, null);
        } catch (IllegalArgumentException expected) {
            cycleRejected = true;
        }
        System.out.println(
            "Negative cycle rejected: " + cycleRejected
        );

        boolean capacityRejected = false;
        try {
            solve(2, List.of(
                new InputEdge(0, 1, -1, 0)
            ), 0, 1, null);
        } catch (IllegalArgumentException expected) {
            capacityRejected = true;
        }
        System.out.println(
            "Invalid capacity rejected: " + capacityRejected
        );

        // 280 mạng nhỏ: DAG có cost âm và mạng tổng quát
        // có thế năng đảm bảo không có chu trình âm.
        Random random = new Random(339L);
        int checked = 0;

        for (int trial = 0; trial < 280; trial++) {
            int n = 2 + random.nextInt(4);
            int m = random.nextInt(8);
            int[] presetPotential = new int[n];
            for (int v = 0; v < n; v++) {
                presetPotential[v] =
                    random.nextInt(9) - 4;
            }

            List<InputEdge> edges = new ArrayList<>();
            for (int id = 0; id < m; id++) {
                int u, v;
                long cost;
                if (trial % 3 == 0) {
                    // DAG: có thể có chi phí âm bất kỳ.
                    u = random.nextInt(n - 1);
                    v = u + 1 + random.nextInt(n - u - 1);
                    cost = random.nextInt(11) - 5L;
                } else if (trial % 3 == 1) {
                    u = random.nextInt(n);
                    v = random.nextInt(n);
                    cost = random.nextInt(7);
                } else {
                    u = random.nextInt(n);
                    v = random.nextInt(n);
                    long nonnegative = random.nextInt(7);
                    cost = nonnegative
                        + presetPotential[v]
                        - presetPotential[u];
                    // Tổng cost trên chu trình bằng tổng
                    // 'nonnegative', nên không có chu trình âm.
                }

                long cap = random.nextInt(3);
                edges.add(new InputEdge(u, v, cap, cost));
            }

            Map<Long, Long> oracle =
                bruteCosts(n, edges, 0, n - 1);
            long bestFlow =
                Collections.max(oracle.keySet());

            Result got = solve(
                n, edges, 0, n - 1, null
            );
            if (!got.flow().equals(
                        BigInteger.valueOf(bestFlow))
                    || !got.totalCost().equals(
                        BigInteger.valueOf(
                            oracle.get(bestFlow)))
                    || !got.maximal()) {
                throw new AssertionError(
                    "max flow/min cost mismatch trial=" + trial
                );
            }

            for (int requested = 0; requested <= 3;
                    requested++) {
                long want = Math.min(bestFlow, requested);
                Result limited = solve(
                    n, edges, 0, n - 1,
                    BigInteger.valueOf(requested)
                );
                if (!limited.flow().equals(
                            BigInteger.valueOf(want))
                        || !limited.totalCost().equals(
                            BigInteger.valueOf(
                                oracle.get(want)))) {
                    throw new AssertionError(
                        "limited min-cost mismatch trial="
                        + trial + ", limit=" + requested
                    );
                }
            }
            checked++;
        }
        System.out.println(
            "Random exhaustive checks: " + checked
        );
    }
}
```

Biên dịch và chạy với **JDK 17+**:

```bash
javac -encoding UTF-8 MinCostFlowPotentialsDemo.java
java MinCostFlowPotentialsDemo
```

**Đầu ra chuẩn** với mã và thứ tự cạnh nêu trên:

```text
Main: flow=2 cost=0 maximal=true
Augment 1: delta=1 pathCost=-2 path=0->1[F0] 1->2[F2] 2->3[F4]
Augment 2: delta=1 pathCost=2 path=0->2[F1] 2->1[R2] 1->3[F3]
Main edge flows: [1, 1, 0, 1, 1]
Main final potential: [0, 2, 0, 2]
Main min-cut side: [0]
Main min-cut capacity: 2
Limit 1: flow=1 cost=-2
Demand 3: flow=2 cost=0 complete=false
Mixed: flow=3 cost=15
Mixed edge flows: [2, 1, 3, 0, 0]
Huge: flow=18446744073709551614 cost=-55340232221128654842
Empty: flow=0 cost=0 maximal=true
Negative cycle rejected: true
Invalid capacity rejected: true
Random exhaustive checks: 280
```

### 11.1. Vì sao main có chi phí 0 dù đường đầu tiên cost -2?

Vì mục tiêu với `limit=null` là **max flow trước**, chứ không phải dừng ở luồng `1` rẻ nhất. Luồng `2` bắt buộc cần điều chỉnh lựa chọn đường đầu tiên. Cung dư ngược `2\to1` hoàn tác ID 2, làm chi phí tăng `2`. Tổng `-2+2=0` là nhỏ nhất trong các luồng cực đại lượng `2`.

### 11.2. Ý nghĩa ký hiệu F/R

```text
1->2[F2]  : dùng cung thuận của cạnh gốc ID 2.
2->1[R2]  : dùng cung ngược của chính ID 2.
```

Hai bước xuất hiện ở **hai lần tăng khác nhau**. `R2` làm giảm luồng gốc ID 2, không tạo cạnh vật lý mới trong mạng đầu vào.

### 11.3. Vì sao finalPotential được in là [0,2,0,2]?

Khi Dijkstra lần đầu thấy đường cost âm, Bellman–Ford đã đổi chi phí để các cung dư dương có trọng số giảm `\ge0`. Sau lần tăng đầu, khoảng cách reduced của các đỉnh cần dùng để tìm đường thứ hai thay đổi. Cộng các khoảng cách ở lần hai cho thế năng `[0,2,0,2]`.

Không cần các thế năng “trông giống chi phí gốc”. Thế năng chỉ là một hệ số đổi trọng số; mọi đường `s\to t` đều nhận **cùng hiệu `\pi[s]-\pi[t]`**, và nghiệm vẫn được tính chi phí gốc.

### 11.4. Tại sao mã kiểm tra pathUnitCost?

Mã tính tổng **chi phí gốc** của các Arc nằm trên đường tăng:

```java
pathUnitCost = pathUnitCost.add(a.cost);
```

Đồng thời, từ khoảng cách Dijkstra reduced:

```java
fromReduced = dist[t] - pi[s] + pi[t];
```

Hai giá trị phải bằng nhau theo phép triệt tiêu thế năng. Nếu khác, rất có thể đang cộng nhầm dấu ở cạnh reverse hoặc nhầm dấu thế năng.

### 11.5. Vì sao các số lớn vẫn chính xác?

Trong mẫu `huge` có hai cạnh song song từ `0` tới `1`, mỗi cạnh capacity `Long.MAX_VALUE` và cost `-3`. Giá trị max flow là:

\[
2\cdot 9223372036854775807
=18446744073709551614.
\]

Tổng chi phí gốc là:

\[
-3\cdot18446744073709551614
=-55340232221128654842.
\]

Cả hai đều vượt phạm vi `long` có dấu. Mã dùng `BigInteger` cho lượng luồng và chi phí, vì vậy không xảy ra tràn số.

Ngoài ra, nếu cost gốc là `Long.MIN_VALUE`, cung reverse có chi phí `-Long.MIN_VALUE`, cũng vượt `Long.MAX_VALUE`. Mã gọi `BigInteger.valueOf(cost).negate()` thay vì `-cost` trên `long`.

### 11.6. Vì sao không dùng reduced cost để cộng totalCost?

Đường đã đổi chi phí có tổng:

\[
c_{\pi}(P)=c(P)+\pi[s]-\pi[t].
\]

Nếu cộng `c_{\pi}(P)` trực tiếp vào totalCost, kết quả thường sai vì thế năng thay đổi giữa các lần tăng. Mã sử dụng **`pathUnitCost` gốc** nhân `\Delta`, rồi đối chiếu tổng cuối với:

\[
\sum_e f_e\,cost_e.
\]

Đây là một bước QA rất hữu ích cho mọi cài đặt min-cost flow.

### 11.7. Ý nghĩa maximal và giới hạn luồng

- `maximal=true`: lần tìm đường dư đã xác nhận **không còn đường `s\to t`**, nên có chứng chỉ min-cut.
- `maximal=false`: chương trình có thể chỉ dừng vì đã đạt `limit`. Không được tự suy ra rằng tổng flow đã là cực đại.
- `Demand 3: flow=2 ... complete=false`: mạng chỉ có khả năng gửi tối đa `2`, không thể đáp ứng yêu cầu chính xác `3`.

## 12. Chi phí âm, chu trình âm và phạm vi của thuật toán

### 12.1. Có cung cost âm vẫn hoàn toàn bình thường

Một cạnh gốc chi phí `-2` trong DAG có thể là lựa chọn rẻ. Sau Bellman–Ford khởi tạo thế năng, reduced cost của nó có thể bằng `0`. Dijkstra chạy trên reduced cost không âm, nên xử lý chính xác cạnh âm mà không cần bỏ cạnh.

Điểm cần tránh là **chạy Dijkstra trực tiếp trên cost âm gốc**, rồi giả định kết quả luôn đúng.

### 12.2. Chu trình âm và min-cost circulation

Một chu trình dư có **tổng cost âm** nghĩa là có thể đẩy một lượng dương quanh chu trình đó và giảm tổng chi phí **mà không đổi giá trị luồng**. Vì thế, để một luồng đang có là tối ưu cho giá trị hiện tại, mạng dư không được còn chu trình âm.

Ví dụ:

```text
0 -> 1 : cap 1, cost -4
1 -> 0 : cap 1, cost +1

Chu trình 0->1->0 có tổng cost -3.
```

Có thể gửi một đơn vị quanh chu trình và giảm tổng chi phí `3` mà không tạo thêm luồng ròng ở nguồn/đích. Chỉ tìm đường `s\to t` không đủ để xét thay đổi này.

Chương trình **từ chối** input ban đầu có chu trình cost âm với capacity dương. Đây là giới hạn minh bạch, không phải khẳng định mọi bài min-cost flow có chu trình âm đều “không có nghiệm”.

**Quan trọng:** khác với bài toán shortest walk trên chu trình âm có thể lặp vô hạn, ở min-cost flow các cạnh có **capacity hữu hạn**, nên bài toán tối ưu có thể vẫn có nghiệm hữu hạn. Cách giải có thể cần **cycle canceling** hoặc giảm về **min-cost circulation**, không thể đơn giản báo `-\infty` chỉ vì có chu trình âm hữu hạn dung lượng.

### 12.3. Negative cycle sau các lần tăng?

Nếu khởi tạo luồng tối ưu cho lượng `0` và mỗi lần tăng theo đường ngắn nhất với thế năng được cập nhật đúng, mạng dư sau mỗi lần tăng có thế năng khả thi. Vì tổng chi phí reduced của mọi chu trình bằng tổng cost gốc và mọi cung dư dương có reduced cost không âm, **không có chu trình âm** được tạo ra trong mạng dư còn sử dụng được.

Nếu công cụ kiểm tra thấy một cung dư dương có reduced cost âm sau cập nhật, đây là tín hiệu **bug cài đặt hoặc giả định đầu vào bị vi phạm**, không được tiếp tục chạy Dijkstra một cách mù.

### 12.4. Bài toán có lower bound, nhiều nguồn/đích, hoặc balance tại đỉnh

Mô hình trong chương trình có `0\le f_e\le cap_e` và một cặp `s,t`. Nếu bài yêu cầu **cận dưới `low_e\le f_e\le cap_e`**, cung–cầu tại nhiều đỉnh, hoặc min-cost feasible circulation, cần biến đổi ràng buộc, cập nhật balance và xây mạng phụ thích hợp. Không thể chỉ thay `capacity` bằng `capacity-low` mà quên yêu cầu cân bằng dòng tại các đỉnh.

Thế năng/reduced cost vẫn là công cụ hữu ích trong các thuật toán liên quan, nhưng API này không tuyên bố giải trực tiếp tất cả các biến thể đó.

## 13. Độ phức tạp thực tế của thuật toán

Đặt `V=|V|`, `E=|E|` (cạnh vật lý ban đầu), `A` là số lần tăng luồng thành công.

- Xây cặp cung dư: **`O(V+E)`** thời gian và bộ nhớ.
- Khởi tạo Bellman–Ford từ siêu nguồn: **`O(VE)`** phép relax; chỉ dùng cung dư dương của cạnh gốc khi flow `0`.
- Một Dijkstra bằng binary heap trên `2E` cung dư: **`O((V+E)\log V)`** phép toán hàng đợi/cạnh.
- Cập nhật thế năng: **`O(V)`**.
- Cập nhật đường tăng: tối đa **`O(V)`** cho một đường đơn.
- Kiểm tra feasible potentials trong ví dụ: **`O(E)`** mỗi lần tăng.
- Tổng thời gian theo các phép toán chuẩn:

\[
\boxed{O(VE+A(V+E)\log V).}
\]

Nếu mọi capacity là số nguyên và mỗi lần tăng có `\Delta\ge1`, số lần tăng `A` không vượt **giá trị luồng đã gửi** `F`. Khi `F` cực lớn, cận này phụ thuộc độ lớn số học của capacity, không tự động là một thuật toán đa thức mạnh theo kích thước mã hóa input. Thuật toán **successive shortest path** rất hữu ích cho mạng vừa/nhỏ hoặc khi lượng luồng cần gửi không quá lớn, nhưng có thể không phù hợp nhất cho mọi dữ liệu quy mô cực lớn.

Bộ nhớ cốt lõi:

\[
\boxed{O(V+E)}
\]

cho đồ thị, thế năng, khoảng cách, parent và priority queue (bỏ qua các bản ghi trùng lặp tạm trong heap vẫn có thể lên `O(E)`). Nếu **lưu toàn bộ lịch sử `A` đường tăng**, cần thêm tối đa `O(AV)` mục Step. Chương trình cố tình lưu history để minh họa.

Khi dùng `BigInteger`, phép cộng/trừ/nhân và so sánh có chi phí phụ thuộc độ dài bit của các số. Các cận trên đếm thao tác cấu trúc, không phải chi phí bit chính xác với giá trị số nguyên không giới hạn.

### Khi nào nên cân nhắc thuật toán khác?

- Chỉ cần **max flow không quan tâm cost**: Edmonds–Karp, Dinic hoặc push–relabel có thể phù hợp hơn.
- Chỉ cần **shortest path tĩnh**: Dijkstra/Bellman–Ford, không cần quản lý residual flow.
- Mạng min-cost flow rất lớn hoặc có nhiều ràng buộc: xét các kỹ thuật nâng cao như capacity scaling, cost scaling, primal–dual hoặc giải min-cost circulation.
- Có **chu trình cost âm ban đầu**: cần một thuật toán cho phạm vi tổng quát hơn, thay vì gọi trực tiếp solver này.

## 14. Oracle độc lập: vét cạn mọi cách gán luồng trên cạnh nhỏ

Một cách kiểm thử min-cost flow thật sự độc lập là **không dùng Dijkstra, thế năng hay đường tăng** để tính đáp án dự kiến.

Giả sử mạng nhỏ có tối đa `8` cạnh, capacity mỗi cạnh `0,1,2`. Ta duyệt mọi tổ hợp:

\[
f_e\in\{0,1,\ldots,cap_e\}.
\]

Với mỗi tổ hợp:

1. Kiểm tra mọi `0\le f_e\le cap_e`.
2. Tính **net outflow** tại từng đỉnh.
3. Chỉ giữ tổ hợp có bảo toàn ở các đỉnh trung gian và `net[s]=-net[t]\ge0`.
4. Ghi lại `F=net[s]` và `Cost=\sum_e f_e\,cost_e`.
5. Với mỗi `F`, lấy **chi phí nhỏ nhất** trong mọi tổ hợp hợp lệ.
6. Chọn `F` lớn nhất để có min-cost max-flow; hoặc chọn `\min(F,F_{\rm limit})` để đối chiếu biến thể giới hạn.

Bằng cách này, ta kiểm tra đồng thời:

- Luồng giá trị lớn nhất.
- Chi phí tối ưu **trong cùng một lượng luồng**.
- Đúng dấu cạnh reverse, vì solver có thể sai cost dù tìm đúng giá trị flow.
- Các mạng có cạnh song song, khuyên, cạnh gốc ngược chiều, cost âm hợp lệ và capacity `0`.

### 14.1. Sinh mạng không có chu trình âm nhưng vẫn có cost âm

Không chỉ nên sinh mạng toàn cost không âm; như vậy sẽ ít thử được phần Bellman–Ford và reduced cost.

Ba nhóm dữ liệu hữu ích:

1. **DAG với cost âm tùy ý:** sinh cạnh `u\to v` với `u<v`. Vì không có chu trình, không thể có chu trình cost âm, dù có cạnh âm.
2. **Đồ thị tổng quát có cost không âm:** có thể có khuyên, cạnh song song và chu trình nhưng tổng cost chu trình không âm.
3. **Đồ thị có hướng tổng quát với cost âm được kiểm soát:** chọn trước một thế năng giả `h[v]` tùy ý, sau đó đặt:

\[
cost(u,v)=base(u,v)+h[v]-h[u]
\]

với `base(u,v)\ge0`. Trên mọi chu trình, tổng các hiệu `h[v]-h[u]` triệt tiêu, nên tổng cost bằng tổng `base\ge0`. Như vậy sinh được mạng có **cạnh âm, cả chu trình có hướng** nhưng **không có chu trình cost âm**.

Đây là một kỹ thuật kiểm thử mạnh vì không cần dựa vào chính hàm Bellman–Ford của solver để xác nhận tiền điều kiện.

### 14.2. Kiểm thử giới hạn lượng

Với mỗi mạng, hãy gọi solver:

```text
limit = null    -> min-cost max-flow
limit = 0       -> flow 0, cost 0 (nếu không có negative cycle)
limit = 1       -> gửi tối đa 1 đơn vị, chi phí tối ưu
limit = 2       -> gửi tối đa 2 đơn vị, chi phí tối ưu
limit > maxFlow -> chỉ gửi được maxFlow, báo không đủ
```

Oracle vét cạn lưu **minimum cost của từng lượng luồng**, nên có thể xác minh cả các trường hợp dừng sớm mà không đánh đồng với nghiệm max-flow.

### 14.3. Kiểm tra bất biến giữa các lần tăng

Ngoài so đáp án cuối, nên kiểm tra:

- Mọi `Arc.residual\ge0`.
- `forward.residual+reverse.residual=capacity` cho mỗi cạnh vật lý.
- Chi phí reverse đúng bằng **đối dấu** chi phí forward.
- Mọi cung dư dương có reduced cost **không âm**.
- Nếu cung nằm trên đường ngắn nhất, reduced cost sau cập nhật thế năng bằng `0`.
- Mỗi đường tăng có bottleneck dương và `delta\le bottleneck`.
- `flow` tăng đúng `delta`, tổng chi phí tăng đúng `delta\cdot originalPathCost`.
- Tổng chi phí tính lại từ từng edge flow bằng tổng tích lũy theo history.
- Kết thúc max-flow: `flow=cutCapacity` trên một min-cut tìm được từ residual reachable.

Chương trình Java kiểm tra nhiều bất biến này trong `assertFeasiblePotential`, phần cập nhật đường và phần tính lại `recomputedCost`.

## 15. Những lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng Dijkstra trực tiếp trên cost gốc có cạnh âm | Có thể tìm sai đường tăng ngắn nhất | Khởi tạo và duy trì feasible potentials, dùng reduced cost |
| Dùng `c+\pi[v]-\pi[u]` nhưng cập nhật theo quy ước `c+\pi[u]-\pi[v]` | Reduced cost có thể âm, thuật toán sai | Chốt **một quy ước dấu duy nhất** |
| Lấy reduced cost làm totalCost gốc | Báo sai chi phí nghiệm | Dùng cost gốc hoặc bù `-\pi[s]+\pi[t]` |
| Không tạo reverse arc | Không thể hoàn tác và điều chỉnh luồng | Mỗi cạnh gốc tạo cặp cung dư thuận–ngược |
| Reverse arc có cost bằng `0` hoặc cùng dấu cost thuận | Sai mức thay đổi chi phí khi hủy luồng | Reverse cost `=-original cost` |
| Gộp cung ngược với cạnh gốc ngược chiều thật | Làm sai dữ liệu và flow/cost từng cạnh | Cặp Arc riêng cho mỗi ID cạnh vật lý |
| Gộp nhiều cạnh song song thành một cờ | Mất capacity hoặc nhầm cost | Giữ mỗi cạnh và cặp reverse riêng |
| Cho Dijkstra đi qua cung residual bằng `0` | Đường tăng giả, bottleneck `0` | Chỉ xét residual `>0` |
| Chỉ lưu đỉnh cha khi có cạnh song song | Không biết phải cập nhật cặp Arc nào | Lưu **parentArc** cụ thể |
| Đọc `dist[v]` của đỉnh không tới được như `0` | Làm hỏng cập nhật thế năng | Dùng null/INF và quy tắc `M` đã chứng minh |
| Dừng Dijkstra sớm ở `t` rồi cập nhật toàn bộ thế năng | Khoảng cách các đỉnh khác chưa chốt, có thể phá feasible invariant | Chạy Dijkstra tới hết reachable |
| Cập nhật thế năng không đồng nhất ở vùng không tới được nhưng vẫn đòi khả thi toàn cục | Có thể xuất hiện reduced cost âm trên cung U→R | Chứng minh phạm vi invariant hoặc dùng `M=max reachable distance` |
| Cập nhật potential sau khi sửa mạng rồi dùng lại dist cũ không có chứng minh | Có thể phá bất biến | Thống nhất thứ tự rõ ràng |
| Quên reverse arcs mới có reduced cost 0 sau cập nhật | Khó giải thích tính đúng | Dùng tính chất đường ngắn nhất và telescoping |
| Không kiểm tra cost âm của chu trình ban đầu | Có thể không có feasible potential toàn cục | Bellman–Ford từ siêu nguồn, hoặc chọn thuật toán xử lý negative cycle |
| Tự kết luận chu trình cost âm ⇒ cost `-\infty` | Sai khi capacity hữu hạn | Xét min-cost circulation/cycle canceling; không mặc định vô hạn |
| Chỉ tối thiểu hóa cost mà bỏ qua giá trị max flow | Dừng quá sớm ở luồng rẻ | Min-cost max-flow tối đa hóa flow **trước** |
| Dừng khi path cost dương trong bài min-cost max-flow | Có thể chưa đạt max flow | Tiếp tục tăng nếu còn đường s→t |
| Nói đạt limit nghĩa là max flow toàn cục | Sai khi còn đường dư | Phân biệt dừng vì limit và dừng vì hết đường |
| Không kiểm tra net flow tại các đỉnh trung gian | Có thể trả flow không khả thi | Tính lại conservation |
| Cộng chi phí bằng `long` với cap lớn | Tràn tích `flow*cost` hoặc tổng | Dùng `BigInteger`, `Math.multiplyExact` hoặc giới hạn có chứng minh |
| Viết `-cost` trên `long` khi cost=Long.MIN_VALUE | Bị tràn, reverse cost sai | Chuyển sang BigInteger **trước** khi negate |
| Dùng oracle cùng thuật toán SSP | Có thể đồng ý với một bug chung | Vét cạn cách gán flow/cost trên mạng nhỏ |
| Nhầm min-cost flow với shortest path | Không xét dung lượng và hoàn tác | Phân biệt đường tăng trong mạng dư |
| Nhầm min-cost flow với max-flow thuần | Tối ưu sai tiêu chí | Phân biệt value và cost |
| Nghĩ mọi thế năng hợp lệ đều là khoảng cách thật từ `s` | Không đúng sau thay đổi/gốc | Thế năng chỉ cần thỏa reduced cost không âm trên cung dư dương |

## 16. Bài tập tự luyện có đáp án

**Bài 1 — Reduced cost.** Cho cung dư `u\to v` chi phí gốc `7`, `\pi[u]=-2`, `\pi[v]=3`. Tính reduced cost.

*Đáp án:* `7+(-2)-3=2`. Cung có reduced cost không âm nên hợp lệ đối với Dijkstra nếu tất cả các cung sử dụng được khác cũng không âm.

**Bài 2 — Dấu của thế năng.** Với quy ước `c_{\pi}=c+\pi[u]-\pi[v]`, sau Dijkstra có `d[v]=5`. Cập nhật `\pi[v]` bằng cộng hay trừ?

*Đáp án:* **cộng** `5`, tức `\pi_{\rm new}[v]=\pi_{\rm old}[v]+5`.

**Bài 3 — Telescoping.** Đường `s\to a\to t` có chi phí gốc tổng `9`, `\pi[s]=3` và `\pi[t]=-1`. Tổng reduced cost là bao nhiêu?

*Đáp án:* `9+3-(-1)=13`. Mọi đường `s\to t` đều được cộng cùng hiệu `4`, nên thứ tự đường ngắn nhất không thay.

**Bài 4 — Công thức ngược.** Nếu Dijkstra trả `dist_{\pi}[t]=8` và `\pi[s]=2,\pi[t]=-3`, chi phí gốc của đường là bao nhiêu?

*Đáp án:* `8-2+(-3)=3`.

**Bài 5 — Reverse cost.** Một cạnh gốc `A\to B` cost `-5` đang có flow `2`. Chi phí của cung dư `B\to A` là bao nhiêu và dư ngược bằng bao nhiêu?

*Đáp án:* cost ngược `+5`, dung lượng dư ngược `2`.

**Bài 6 — Tăng qua reverse.** Nếu tăng `1` trên cung ngược ở bài 5, flow gốc đổi thế nào và totalCost đổi thế nào?

*Đáp án:* flow gốc giảm `2\to1`; totalCost tăng `5` (bớt một đơn vị cost âm `-5`).

**Bài 7 — Dijkstra có cạnh gốc âm.** Mạng ban đầu có cost âm nhưng không có chu trình cost âm. Có dùng Dijkstra trên cost gốc ngay được không?

*Đáp án:* không có bảo đảm; chạy Bellman–Ford để lấy feasible potentials rồi dùng Dijkstra trên reduced cost không âm.

**Bài 8 — Siêu nguồn.** Vì sao khởi tạo `\pi[v]=0` cho mọi đỉnh rồi Bellman–Ford relax các cạnh gốc tương đương thêm một siêu nguồn nối chi phí `0` tới mọi đỉnh?

*Đáp án:* từ siêu nguồn, mỗi đỉnh ban đầu có một đường chi phí `0`. Bellman–Ford tìm các đường rẻ hơn (có thể âm) qua cạnh gốc và bảo đảm `\pi[v]\le\pi[u]+cost(u,v)`.

**Bài 9 — Cạnh âm vs chu trình âm.** Một DAG có cạnh cost `-10` có bắt buộc bị solver từ chối không?

*Đáp án:* không. DAG không có chu trình nào; Bellman–Ford vẫn tạo được feasible potential.

**Bài 10 — Cập nhật unreachable.** Sau Dijkstra, `d` hữu hạn bằng `[0,3,7]` trên ba đỉnh tới được, còn đỉnh `x` không tới được. Theo quy tắc trong bài, thế năng `x` được cộng bao nhiêu?

*Đáp án:* cộng `M=\max(0,3,7)=7`. Quy tắc này giữ reduced cost không âm cả trên cung dư từ vùng không tới được sang vùng tới được.

**Bài 11 — Cung mới kích hoạt.** Vì sao cung reverse được tạo dư dương sau khi tăng trên một đường ngắn nhất có reduced cost `0`?

*Đáp án:* mỗi cung của đường ngắn nhất thỏa `d[v]=d[u]+c_\pi(u,v)`, nên sau cập nhật `c_{\pi_{\rm new}}(u,v)=0`. Cung reverse có reduced cost đối dấu, cũng bằng `0`.

**Bài 12 — Lượng 1 và 2.** Với mạng ở phần 9, chi phí tối ưu khi gửi `1` và `2` đơn vị lần lượt là bao nhiêu?

*Đáp án:* `-2` và `0`.

**Bài 13 — Tại sao đường thứ hai dùng R2?** Trong mạng phần 9, sau đường `0\to1\to2\to3`, đường tăng tiếp theo là gì và vì sao?

*Đáp án:* `0\to2\to1\to3`; bước `2\to1` là reverse ID 2, hoàn tác flow `1\to2` để phân phối lại hai đơn vị qua hai nhánh đến đích.

**Bài 14 — Chi phí tổng.** Hai cạnh song song s→t mỗi capacity `Long.MAX_VALUE`, cost `-3`. Tính max flow và min cost.

*Đáp án:* flow `18446744073709551614`, cost `-55340232221128654842`, vượt `long` có dấu.

**Bài 15 — Chu trình âm có capacity hữu hạn.** Có một chu trình cost âm và capacity hữu hạn. Có thể mặc định kết quả min-cost là `-\infty` không?

*Đáp án:* không. Capacity hạn chế lượng đi vòng; một nghiệm hữu hạn có thể tồn tại. Nhưng SSP chỉ tăng đường s-t chưa đủ để xử lý circulation cost âm; cần thuật toán tương ứng hoặc từ chối theo hợp đồng.

**Bài 16 — Chứng minh.** Tại sao mọi đường từ `s` tới `t` được cộng cùng một giá trị khi đổi trọng số?

*Đáp án:* trên đường, tổng các thế năng trung gian triệt tiêu, chỉ còn `\pi[s]-\pi[t]`. Vì vậy thứ tự chi phí giữa các đường không đổi.

**Bài 17 — Giới hạn lượng.** Nếu nhu cầu `F=5` nhưng max flow chỉ bằng `3`, chương trình nên báo thế nào?

*Đáp án:* báo đã gửi `3` và **không đáp ứng đủ `F=5`**. Không được gọi kết quả đó là nghiệm exact-F.

**Bài 18 — Oracle.** Hãy tạo mạng nhỏ `m\le8`, capacity `0..2`, cost có dấu nhưng không có chu trình âm; liệt kê mọi cách gán luồng cạnh, kiểm tra conservation và ghi min cost cho từng flow.

*Đáp án mong đợi:* min-cost flow qua SSP phải khớp min cost vét cạn cho **mỗi lượng khả thi**, không chỉ khớp max-flow value.

**Bài 19 — Phân biệt thuật toán.** Dijkstra có thể dùng sau khi mạng dư xuất hiện một cung cost gốc âm không?

*Đáp án:* có, **nếu reduced cost của mọi cung dư dương mà Dijkstra sẽ xét không âm** nhờ feasible potentials. Không chạy trực tiếp trên cost gốc.

**Bài 20 — Chứng chỉ kết thúc.** Nếu `limit=null` và Dijkstra không tới được đích, còn thế năng khả thi, ta kết luận gì?

*Đáp án:* luồng có **giá trị cực đại** vì hết đường tăng, và **chi phí tối thiểu ở giá trị cực đại ấy** vì không có chu trình cost âm trong residual. Đây là min-cost max-flow.

## 17. Checklist áp dụng trong bài thi và hệ thống thực tế

1. Bài yêu cầu **đúng F**, “nhiều nhất F”, hay **min-cost max-flow**? Chốt rõ mục tiêu và điều kiện không đáp ứng đủ.
2. Mạng là **có hướng**? Dung lượng có **không âm**? Chi phí có thể âm?
3. Có **cạnh gốc song song, cạnh ngược chiều thật, khuyên**? Mỗi ID cạnh gốc có cặp Arc dư riêng?
4. Với mỗi cạnh gốc, đã đặt `forward residual=cap-flow` và `reverse residual=flow`?
5. Chi phí cung ngược có đúng **`-cost gốc`**, tính bằng kiểu số không tràn?
6. Quy ước reduced cost là `c+\pi[u]-\pi[v]` hay quy ước dấu ngược? Cách cập nhật pi có đồng nhất không?
7. Nếu cost gốc âm, đã **khởi tạo feasible potential** (Bellman–Ford hoặc cách có chứng minh) trước Dijkstra?
8. Mạng ban đầu có **chu trình chi phí âm** không? Solver có thực sự hỗ trợ cycle canceling hay cần từ chối?
9. Dijkstra có **chỉ đi cung dư dương**, dùng **reduced cost không âm**, và lưu **Arc cha cụ thể**?
10. Có tính đủ mọi `d[v]` cần cho cập nhật thế năng, không dừng sớm khiến dist chưa chốt?
11. Với unreachable, có quy tắc cập nhật thế năng được chứng minh, ví dụ **cộng `M=maxDist`** để giữ khả thi toàn cục?
12. Mọi cung trên đường ngắn nhất có reduced cost mới bằng `0` trước khi kích hoạt reverse?
13. Bottleneck có đúng min residual? Nếu gần đạt limit, có giới hạn `\Delta` theo phần còn thiếu?
14. Mỗi lần tăng có cập nhật **cả hai residual** của cặp Arc?
15. Có cộng **chi phí gốc** `\Delta\cdot pathUnitCost`, không cộng nhầm reduced cost?
16. Có kiểm tra `0\le f_e\le cap_e`, conservation, totalCost tính lại từ từng cạnh?
17. Khi hết đường, có chứng chỉ min-cut cho giá trị max-flow? Khi dừng vì limit có phân biệt chưa chứng nhận max?
18. Trọng số `long`, cost ngược và tích `flow\cdot cost` có thể tràn không? Có dùng `BigInteger`/cận đúng?
19. Có kiểm thử mạng gây **reverse rerouting**, mạng có cost âm nhưng không chu trình âm, mạng trống và capacity cực lớn?
20. Có **oracle vét cạn độc lập** trên mạng nhỏ, so cả **giá trị luồng lẫn chi phí tối ưu**?

## Ghi nhớ

Trong mạng dư min-cost flow, mỗi cạnh gốc `e=(u,v)` sinh:

\[
\boxed{
r_f=cap_e-f_e,\quad c_f=cost_e;\qquad
r_r=f_e,\quad c_r=-cost_e.
}
\]

Với quy ước thế năng `\pi` của bài:

\[
\boxed{
c_{\pi}(u,v)=c(u,v)+\pi[u]-\pi[v].
}
\]

Tổng trên một đường `s\to t` đổi theo hằng số:

\[
\boxed{c_{\pi}(P)=c(P)+\pi[s]-\pi[t],}
\]

nên **đường ngắn nhất không thay**.

Khi thế năng khả thi làm **mọi reduced cost của cung dư dương không âm**, ta dùng **Dijkstra**. Sau mỗi lượt, cập nhật `\pi[v]` bằng khoảng cách reduced ngắn nhất `d[v]` cho đỉnh tới được; nếu cần khả thi toàn cục, có thể cộng `M=\max d` cho đỉnh không tới được như đã chứng minh.

Đi qua cung dư reverse nghĩa là **giảm luồng gốc và trả lại chi phí tương ứng**, không tạo một cạnh vật lý mới. Tăng đường ngắn nhất và cập nhật thế năng đúng sẽ giữ mạng dư không có chu trình chi phí âm, vì vậy **luồng luôn có chi phí tối thiểu cho lượng hiện tại**.

**Luồng chi phí nhỏ nhất không chỉ là tìm đường ngắn nhất. Thế năng biến chi phí để tìm đường nhanh, cạnh ngược cho phép sửa luồng cũ, và bất biến reduced cost không âm bảo đảm mỗi lần tăng vẫn dẫn đến nghiệm chi phí tối ưu.**
