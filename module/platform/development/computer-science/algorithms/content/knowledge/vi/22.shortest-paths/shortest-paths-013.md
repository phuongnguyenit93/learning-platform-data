# Đường đi dài nhất trên đồ thị có hướng không chu trình

**Đường đi dài nhất trên đồ thị có hướng không chu trình** (*Longest Path in a Directed Acyclic Graph — DAG*) là bài toán tìm một đường có **tổng trọng số cạnh lớn nhất** trong đồ thị có hướng, không chứa chu trình. Nhờ cấu trúc DAG, ta có thể dùng **thứ tự topo + quy hoạch động + thư giãn cạnh theo phép lấy lớn nhất** để giải trong **O(V+E)** thời gian.

Bài này thuộc nhóm **Đường đi ngắn nhất** vì sử dụng cùng khung biểu diễn đồ thị, thư giãn cạnh và khôi phục đường đi, nhưng chuyển mục tiêu từ **min** sang **max**. Điều kiện DAG quan trọng hơn dấu trọng số: cạnh có thể âm, bằng 0 hoặc dương. Nếu đề chỉ hỏi **đường có nhiều cạnh nhất** trên DAG không trọng số, gán mỗi cạnh trọng số 1 sẽ đưa về đúng mô hình này.

Cần phân biệt ba yêu cầu:
- **Từ nguồn s đến mọi đỉnh v:** giá trị dài nhất `best[v]` chỉ có nghĩa khi v có thể tới từ s. Đỉnh không tới được là `−INF`/“không có đường”, không phải 0.
- **Toàn bộ DAG, bắt buộc có ít nhất một cạnh:** tìm đường dài nhất bắt đầu và kết thúc ở bất cứ đâu, kể cả khi đáp án âm.
- **Toàn bộ DAG, cho phép đường không cạnh:** một đường gồm một đỉnh có trọng số 0; với đồ thị có ít nhất một đỉnh, kết quả toàn cục không thể nhỏ hơn 0.

Bài học giải thích bất biến topo, xây thuật toán nguồn và toàn cục, chứng minh tính đúng, xử lý cạnh âm/đỉnh không tới được/đường hòa, khôi phục đường chứng cứ và mã Java 17 hoàn chỉnh có oracle kiểm thử.

## 1. Định nghĩa và điều kiện áp dụng

Cho đồ thị có hướng `G=(V,E)`, mỗi cạnh `u→v` có trọng số `w(u,v)`. Một đường đi có hướng:

\[
P=v_0\to v_1\to\cdots\to v_k
\]

có **k cạnh**, **k+1 đỉnh**, tổng trọng số:

\[
W(P)=\sum_{i=0}^{k-1}w(v_i,v_{i+1}).
\]

Với nguồn s, tìm:

\[
L_s(v)=\max_{P:s\leadsto v}W(P).
\]

Nếu không có đường từ s đến v, không có một đáp án hữu hạn; dùng ký hiệu `−∞` trong phân tích. Đường `s` gồm **0 cạnh** có trọng số 0, vì vậy `L_s(s)=0`.

**DAG** (*Directed Acyclic Graph*) không có bất kỳ chu trình có hướng nào:
- Cạnh tự khép `u→u` là một chu trình, không được phép.
- Cặp cạnh `u→v, v→u` tạo chu trình hai cạnh, không được phép.
- Hai cạnh song song **cùng chiều** u→v không tự tạo chu trình; mỗi cạnh có thể có trọng số khác nhau.
- Có thể có nhiều thành phần không liên thông, đỉnh cô lập, cạnh âm hoặc bằng 0.
- Đồ thị n=0 không có chu trình nhưng **không có nguồn hợp lệ** cho bài từ nguồn.

### Tại sao trọng số âm vẫn hợp lệ?

Trong DAG, không thể đi quanh một chu trình để tăng tổng trọng số không giới hạn. Mọi đường có hướng đều đi qua các đỉnh phân biệt, dài tối đa `V−1` cạnh. Một cạnh âm có thể nằm trên đường tối ưu vì sau nó còn những cạnh dương lớn.

Trái lại, đồ thị tổng quát có **chu trình dương** và cho phép lặp đỉnh có thể có trọng số đường đi không bị chặn trên. Nếu chỉ cho đường đơn trong đồ thị tổng quát, bài dài nhất khó hơn nhiều (NP-hard trong trường hợp tổng quát). Vì thế **không dùng DAG-DP trên đồ thị có chu trình**, bất kể chu trình nặng dương hay âm.

### Nhiều cách hiểu của “dài nhất”

Nếu đề yêu cầu **nhiều cạnh nhất**, đặt `w=1` cho mọi cạnh. Nếu yêu cầu **nhiều đỉnh nhất**, một đường gồm k cạnh có k+1 đỉnh. Nếu yêu cầu **tổng trọng số lớn nhất**, phải cộng chính các trọng số đã cho; không thể đồng nhất số cạnh với trọng số khi các cạnh có trọng số khác nhau.

Nếu đề nói tìm đường toàn cục nhưng không rõ **có bắt buộc đi qua một cạnh** không, hai lời giải có thể khác nhau trên đồ thị toàn cạnh âm. Bài này sẽ trình bày và cài đặt biến thể **bắt buộc ít nhất một cạnh**.

## 2. Thứ tự topo — cấu trúc quyết định

**Thứ tự topo** là một hoán vị của toàn bộ đỉnh sao cho với mọi cạnh `u→v`, u đứng **trước** v. Một đồ thị có hướng hữu hạn **có thứ tự topo khi và chỉ khi nó là DAG**.

Ví dụ có cạnh `0→1, 0→2, 2→1` thì thứ tự `[0,1,2]` **không hợp lệ** do 2→1; thứ tự `[0,2,1]` hợp lệ.

Đặc điểm quan trọng: khi xử lý đỉnh v trong topo, **mọi đỉnh có cạnh đi vào v đều đã xử lý**. Bởi vậy mọi đường ứng viên tới v đã có cơ hội cập nhật. Không còn cạnh nào từ đỉnh đứng sau quay ngược về v.

Nếu duyệt đỉnh theo thứ tự nhãn 0,1,2... mà thứ tự đó không phải topo, có thể xử lý cạnh đi ra từ v **trước khi best[v] được cải thiện bởi một đỉnh khác**; nếu không quay lại v, kết quả sai.

### Tạo topo bằng thuật toán Kahn

1. Đếm `indegree[v]` là số **cạnh đi vào v**, kể cả cạnh song song.
2. Đưa tất cả đỉnh có bậc vào 0 vào hàng đợi.
3. Lấy một đỉnh u ra, ghi vào `order`.
4. Với từng cạnh u→v, giảm `indegree[v]`; khi về 0, đưa v vào queue.
5. Nếu `order.size()<V`, đồ thị **có chu trình**, phải từ chối. Nếu bằng V, `order` là topo hợp lệ.

Mỗi đỉnh vào queue một lần, mỗi cạnh giảm indegree một lần: **O(V+E)** thời gian và O(V) bộ nhớ phụ.

**Không chỉ kiểm tra thành phần reachable từ nguồn.** Nếu thành phần của s không có vòng nhưng một phần khác có chu trình, đồ thị toàn cục không phải DAG. Theo hợp đồng chương trình dưới đây, Kahn **từ chối toàn bộ** trước khi tìm đường.

Ví dụ `0→1` và `2→3→2`: mặc dù không thể tới 2 từ nguồn 0, thứ tự topo toàn cục vẫn **không tồn tại**.

## 3. Max-relax: thư giãn cạnh theo phép lấy lớn nhất

Cho cạnh `u→v` có trọng số w. Nếu đã có một đường từ nguồn s tới u với tổng lớn nhất đã biết `best[u]`, việc thêm cạnh tạo ứng viên:

\[
candidate=best[u]+w(u,v).
\]

Nếu v chưa có đường nào hoặc candidate lớn hơn best[v], cập nhật:

~~~text
reachable[v] = true
best[v] = candidate
parent[v] = u
~~~

Với bài đường **ngắn** nhất, ta so bằng `candidate<dist[v]`. Với bài đường **dài** nhất, ta so bằng `candidate>best[v]`.

### Trạng thái chuẩn cho một nguồn

- `reachable[v]`: đã có đường có hướng từ s tới v hay chưa.
- `best[v]`: trọng số lớn nhất của các đường đã biết, chỉ có nghĩa nếu reachable[v] là true.
- `parent[v]`: đỉnh đứng trước v trên đường đang được chọn.
- `order`: thứ tự topo đã được kiểm chứng.

Khởi tạo:

~~~text
reachable[*] = false
best[*] = 0       // chỉ là vùng chứa; không đọc best nếu unreachable
parent[*] = -1
reachable[s] = true
best[s] = 0
~~~

Ký hiệu toán học `−INF` không nhất thiết phải được lưu bằng một giá trị số sentinel. **Không dùng `Long.MIN_VALUE` rồi cộng vô điều kiện**, vì một phép cộng có thể tạo giá trị giả cho đỉnh unreachable, làm tràn long, hoặc nhầm với một tổng hợp lệ đúng bằng Long.MIN_VALUE.

### Giữ parent khi hòa

Nếu candidate **bằng** best[v], nhiều đường có thể cùng dài nhất. Ví dụ chương trình chỉ cập nhật khi **lớn hơn nghiêm ngặt** nên giữ parent của phương án tìm thấy trước. Nếu đề yêu cầu đường đồng tối ưu ít cạnh nhất hoặc thứ tự từ điển nhỏ nhất, cần thêm tiêu chí phá hòa.

## 4. Thuật toán đường dài nhất từ một nguồn

~~~text
longestFrom(graph, source):
    order = topoOrThrow(graph)  // từ chối nếu không phải DAG
    reachable[*] = false
    best[*] = 0
    parent[*] = -1
    reachable[source] = true
    best[source] = 0

    for u in order:
        if not reachable[u]:
            continue

        for (u,v,w) trong adjacency[u]:
            candidate = best[u] + w
            if not reachable[v] or candidate > best[v]:
                reachable[v] = true
                best[v] = candidate
                parent[v] = u

    return order, reachable, best, parent
~~~

Ở đây **mỗi cạnh chỉ cần relax một lần**, vì topo bảo đảm tất cả tiền nhiệm của u đã hoàn thành khi ta xử lý u.

### Tại sao phải bỏ qua đỉnh không tới được?

Nếu u unreachable thì không có đường từ s tới u. Dù cạnh u→v có trọng số +1000, nó **không tạo được đường từ s tới v**, nên không được xem `best[u]+1000` là một ứng viên.

Nếu đánh dấu tất cả đỉnh reachable ban đầu với best=0, ta đã thay bài **từ nguồn** bằng bài cho phép bắt đầu ở **mọi đỉnh** — đó là bài toán khác.

### Khôi phục đường đi

Khi best[v] cải thiện bởi cạnh u→v, đặt parent[v]=u. Với đích t reachable:
1. Bắt đầu từ t, lần theo parent tới −1.
2. Đảo dãy đỉnh để được đường từ s tới t.
3. Xác minh đỉnh đầu là s và mỗi cặp liên tiếp có cạnh đúng chiều.

Đường tới chính s là `[s]` và có tổng 0. Nếu t unreachable, trả `none`, không cố truy parent.

Trong DAG, parent luôn chỉ tới một đỉnh đứng trước theo topo, nên chuỗi parent **không thể tạo vòng**. Mã vẫn có kiểm tra độ dài tối đa n để phát hiện trạng thái hỏng ngoài ý muốn.

## 5. Mô phỏng có trọng số âm

Cho DAG 7 đỉnh, nguồn s=0, các cạnh:

| Cạnh | Trọng số |
| --- | ---: |
| 0→1 | 3 |
| 0→2 | 2 |
| 1→3 | 4 |
| 2→3 | 6 |
| 1→4 | −5 |
| 3→4 | −2 |
| 3→5 | 2 |
| 4→5 | 7 |
| 2→6 | −3 |
| 5→6 | 1 |

Kahn với thứ tự cạnh như bảng cho:

~~~text
indegree ban đầu = [0,1,1,2,2,2,2]
topo = [0,1,2,3,4,5,6]
~~~

Mô phỏng max-relax:

**Xử lý đỉnh 0:** best[1]=3, best[2]=2.

**Xử lý đỉnh 1:** qua cạnh 1→3 (4), best[3]=7; qua 1→4 (−5), best[4]=−2. Giá trị −2 vẫn là một đường **hợp lệ**.

**Xử lý đỉnh 2:** qua 2→3 (6), cải thiện best[3] từ 7 thành **8**; qua 2→6 (−3), best[6]=−1.

**Xử lý đỉnh 3:** qua 3→4 (−2), cải thiện best[4] thành 8−2=**6**; qua 3→5 (2), best[5]=10.

**Xử lý đỉnh 4:** qua 4→5 (7), cải thiện best[5] thành 6+7=**13**.

**Xử lý đỉnh 5:** qua 5→6 (1), cải thiện best[6] thành 13+1=**14**.

**Đỉnh 6:** không có cạnh đi ra.

| Đỉnh v | best[v] | parent[v] | Đường chọn từ nguồn 0 |
| ---: | ---: | ---: | --- |
| 0 | 0 | −1 | 0 |
| 1 | 3 | 0 | 0→1 |
| 2 | 2 | 0 | 0→2 |
| 3 | 8 | 2 | 0→2→3 |
| 4 | 6 | 3 | 0→2→3→4 |
| 5 | 13 | 4 | 0→2→3→4→5 |
| 6 | **14** | 5 | **0→2→3→4→5→6** |

Tổng trọng số:

\[
2+6+(-2)+7+1=\boxed{14}.
\]

Cạnh **3→4 = −2** vẫn nằm trên đường dài nhất tới 6; bỏ tất cả cạnh âm theo trực giác tham lam có thể bỏ mất nghiệm.

### Đường dài nhất không đồng nghĩa chọn cạnh tốt nhất trước mắt

Ở đỉnh 3, cạnh 3→5 trọng số +2 trông có vẻ tốt hơn 3→4 trọng số −2. Nhưng chọn 3→4 rồi 4→5 (+7) có tổng tăng thêm **5**, lớn hơn đi thẳng 3→5 (+2). Vì vậy cần nhìn **toàn bộ phần đường đi**, không chỉ từng cạnh riêng.

## 6. Đỉnh unreachable và nhiều thành phần

Xét:

~~~text
0 --(-3)--> 1         2 --(8)--> 3
s=0
~~~

Từ nguồn s=0:
- best[0]=0.
- best[1]=−3.
- 2 và 3 **không có đường từ s**, phải in `−INF` hoặc `none`.
- Cạnh 2→3 dù rất tốt **không được** dùng để cập nhật best[3] của bài từ nguồn 0.

Kết quả:

~~~text
source=[0, -3, -INF, -INF]
pathTo3=none
~~~

Nếu hỏi **đường dài nhất trên toàn bộ đồ thị có ít nhất một cạnh**, đáp án lại là **2→3** trọng số 8. Điều đó hợp lệ vì bài toàn cục cho phép bắt đầu tại 2, không bị ràng buộc bởi nguồn 0.

### Giá trị 0 và giá trị âm đều hợp lệ

Một đường từ s tới v có thể có tổng **0** hoặc **âm**. Không dùng điều kiện `best[v]==0` để suy ra unreachable. Mảng `reachable[]` riêng giải quyết hoàn toàn sự nhầm lẫn giữa **không có đường** và **đường có trọng số 0/âm**.

## 7. Biến thể toàn cục bắt buộc ít nhất một cạnh

Một cách thường thấy là khởi tạo `best[v]=0` cho **mọi v** rồi max-relax topo. Điều đó tìm đường tốt nhất khi **cho phép đường rỗng cạnh**: mỗi đỉnh tự nó là một đường trọng số 0.

Nếu **bắt buộc có ít nhất một cạnh**, khởi tạo như vậy sẽ trả sai khi mọi cạnh âm: kết quả 0 không phải trọng số của bất cứ đường hợp lệ nào có cạnh.

### Quy hoạch động tại đích

Định nghĩa:
- `hasEdge[v]`: có tồn tại đường có ít nhất một cạnh kết thúc ở v.
- `globalBest[v]`: trọng số lớn nhất trong những đường ấy.
- `globalParent[v]`: đỉnh trước v trên đường đang chọn.
- `globalStart[v]`: điểm bắt đầu của đường đang chọn.

Với **mỗi cạnh u→v trọng số w**, có đúng hai dạng ứng viên:

**1. Bắt đầu mới ngay tại u** — đường chỉ gồm một cạnh:

\[
candidate_1=w(u,v).
\]

Nếu tốt hơn giá trị ở v, đặt:

~~~text
hasEdge[v] = true
globalBest[v] = w
globalParent[v] = u
globalStart[v] = u
~~~

**2. Nối tiếp đường tốt nhất có ít nhất một cạnh đến u**, chỉ khi hasEdge[u] là true:

\[
candidate_2=globalBest[u]+w(u,v).
\]

Nếu tốt hơn ở v, đặt:

~~~text
globalBest[v] = candidate_2
globalParent[v] = u
globalStart[v] = globalStart[u]
~~~

Duyệt các đỉnh u theo topo. Kết thúc, chọn đỉnh end với globalBest[end] lớn nhất trong những đỉnh hasEdge. Nếu **không có đỉnh hasEdge**, đồ thị không có cạnh và kết quả là **none**.

### Vì sao phải lưu globalStart?

Giả sử phương án tốt nhất kết thúc tại v là **bắt đầu mới** bằng cạnh u→v. Bản thân u có thể có một đường dài nhất khác kết thúc tại u, nhưng **đường ấy không thuộc phương án bắt đầu mới**.

Nếu truy parent từ v mãi tới −1, ta có thể vô tình nối tiền tố của u làm chứng cứ **không đúng trọng số globalBest[v]**.

Cần lưu `globalStart[end]` và truy parent **từ end tới đúng start ấy**, rồi dừng và đảo danh sách. Các parent trước start, nếu có, không thuộc đường đang tìm.

### Phân biệt khi mọi cạnh âm

~~~text
0→1 (-5)
0→2 (-2)
1→2 (-4)
~~~

- Từ nguồn 0: `best=[0,-5,-2]`.
- Toàn cục **phải có ít nhất một cạnh**: đường **0→2**, tổng **−2**.
- Toàn cục **cho phép đường không cạnh**, với ít nhất một đỉnh: chọn một đỉnh và không đi qua cạnh, tổng **0**.
- Đồ thị **không cạnh**: biến thể bắt buộc một cạnh trả **none**, không được tự in 0.

Nếu cho phép đường không cạnh, khi đồ thị có ít nhất một đỉnh, đáp án toàn cục là max của 0 và đáp án có cạnh (nếu có). Với đồ thị rỗng n=0, không tồn tại cả một đỉnh để làm đường không cạnh; cần định nghĩa xử lý riêng.

## 8. Chứng minh tính đúng bằng topo

### Định lý cho một nguồn s

**Bất biến:** khi sắp xử lý đỉnh v trong topo, mọi đỉnh đứng trước v đã có giá trị dài nhất đúng từ nguồn s (hoặc được xác nhận unreachable); các cạnh đi ra từ chúng đã được thư giãn.

**Cơ sở:** đường gồm riêng s có trọng số 0. Một đường có hướng từ s quay lại s bằng cạnh sẽ tạo chu trình, nên không thể có phương án khác đến s. Những đỉnh đứng trước s trong topo không thể reachable từ s vì một đường có hướng luôn tiến về phía sau topo.

**Bước quy nạp:** mọi đường từ s tới v có ít nhất một cạnh đều có cạnh cuối `u→v`, với u đứng trước v. Giá trị tốt nhất của các đường kết thúc bằng cạnh này là `best[u]+w(u,v)`, nếu u reachable. Theo quy nạp, best[u] đã tối ưu khi u được xử lý. Thuật toán đã xét **tất cả cạnh đi vào v** từ những u trước v, nên đã lấy max của mọi ứng viên. Không còn tiền nhiệm sau v để cải thiện giá trị. Nếu không có u reachable vào v, v unreachable.

Do đó khi đến lượt v, best[v] đã đúng. Quy nạp qua toàn bộ topo cho **kết quả đúng với mọi đỉnh**. Trọng số âm không làm hỏng lập luận vì điều cần là **mọi cạnh đều hướng tới đỉnh đứng sau**.

### Định lý cho đường toàn cục có ít nhất một cạnh

Mọi đường có ít nhất một cạnh kết thúc tại v đều có cạnh cuối u→v. Phần trước cạnh cuối hoặc:
- không có cạnh nào: đường chỉ có cạnh u→v, trọng số w;
- có ít nhất một cạnh tới u: trọng số lớn nhất là globalBest[u], nối cạnh cuối cho globalBest[u]+w.

Đó chính xác là hai ứng viên được xét khi duyệt cạnh u→v. Mọi u đứng trước v theo topo, nên globalBest[u] đã tối ưu. Lấy max cho từng v rồi lấy max trên các v trả đúng đường toàn cục.

Việc ghi parent và start không đổi giá trị tối ưu; nó chỉ bảo đảm chứng cứ được dựng đúng từ điểm bắt đầu đã chọn.

### Định lý cho Kahn

Mọi DAG hữu hạn không rỗng có ít nhất một đỉnh indegree=0. Nếu mọi đỉnh có cạnh đi vào, lần ngược theo một cạnh vào trong tập hữu hạn sẽ lặp đỉnh và tạo chu trình, mâu thuẫn DAG. Xóa đỉnh indegree=0 giữ phần còn lại là DAG, nên Kahn loại hết được.

Nếu có chu trình, không thể có **đỉnh đầu tiên trên chu trình** bị loại: nó vẫn nhận cạnh từ đỉnh trước trên vòng, nên indegree chưa bằng 0. Do đó Kahn không thể xóa đủ V đỉnh. Thuật toán từ chối đúng những đồ thị không phải DAG.

## 9. Chi phí và tính thực dụng

Đặt n=|V|, m=|E|. Với danh sách kề:

| Giai đoạn | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Tạo danh sách kề từ m cạnh | O(n+m) | O(n+m) để lưu đồ thị |
| Kahn kiểm tra DAG + topo | O(n+m) | O(n) |
| DP từ nguồn bằng max-relax | O(n+m) | O(n) |
| DP toàn cục có cạnh | O(n+m) | O(n) |
| Truy một đường parent | O(n) trường hợp xấu | O(n) |

**Tổng mỗi bài: O(V+E)** thời gian và O(V) bộ nhớ **phụ ngoài danh sách kề**. Chi phí in nhiều đường còn phụ thuộc tổng số đỉnh của các đường được in; không cần lưu mọi đường để có bảng giá trị DP.

### Tràn số và kiểu long

Java `long` có miền \([-2^{63},2^{63}-1]\). Dùng `Math.addExact(a,b)` để ném lỗi khi **một ứng viên đang được xét** vượt miền. Mã có thể báo lỗi ngay cả nếu đường tối ưu cuối cùng còn nằm trong miền long, bởi nó vẫn phải xét những ứng viên khác. Để hỗ trợ mọi tổng có thể lớn hơn 64 bit, dùng `BigInteger` (khi ấy mỗi phép tính số học không còn mặc định O(1) theo độ dài bit).

`Long.MIN_VALUE` có thể là một tổng thật sự, nên giữ cờ reachable/hasEdge riêng thay vì dùng nó làm sentinel duy nhất.

### Nhiều nguồn

Topo của một DAG không đổi có thể **tính một lần và tái sử dụng**. Với mỗi nguồn mới phải khởi tạo lại reachable, best và parent, rồi max-relax theo topo. Dùng nhầm trạng thái của nguồn trước sẽ đổi ý nghĩa bài toán.

### Có được dùng BFS hoặc Dijkstra không?

- BFS không trọng số tìm **ít cạnh nhất**, không giải bài **nhiều cạnh nhất** hoặc **tổng trọng số lớn nhất**.
- Dijkstra dùng cho đường **ngắn** nhất với trọng số cạnh không âm; đổi dấu trọng số và áp Dijkstra **không đúng tổng quát** vì trọng số đổi dấu có thể âm.
- Bellman–Ford giải đường **ngắn** nhất trên đồ thị có cạnh âm (với điều kiện về chu trình âm), nhưng không cần dùng thuật toán O(VE) khi topo-DP giải bài dài nhất DAG trong O(V+E).
- Thuật toán DFS vét cạn mọi đường có thể kiểm chứng đầu vào nhỏ nhưng số đường trên DAG vẫn có thể **tăng theo hàm mũ**, nên không dùng vét cạn cho dữ liệu lớn.

## 10. Chương trình Java 17 hoàn chỉnh

Chương trình cài cả **đường dài nhất từ nguồn** và **đường dài nhất toàn cục bắt buộc ít nhất một cạnh**. Bên cạnh đó có oracle độc lập dành cho đồ thị rất nhỏ để kiểm tra kết quả trên mọi đồ thị có hướng đơn từ 0 đến 4 đỉnh.

Giao diện:
- `graph` dựng danh sách kề, kiểm tra đầu mút cạnh; giữ cạnh song song.
- `topoOrThrow` kiểm tra DAG **toàn cục** bằng Kahn.
- `longestFrom` trả `reachable[]`, `best[]`, `parent[]`.
- `longestNonEmpty` trả kết quả toàn cục với `hasEdge[]`, `starts[]` và end.
- `pathFrom` và `pathGlobal` truy đường, không dùng parent của đỉnh start trong đường toàn cục.
- `oracleCycle` kiểm tra vòng bằng bao đóng khả đạt, `oracleFrom`/`oracleGlobal` vét cạn đường trên DAG nhỏ.
- `verifySmallGraphs` đối chiếu 66.067 cấu hình đồ thị (573 DAG, 2.254 lần chọn nguồn).

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.StringJoiner;

public class DagLongestPathsDemo {
    record Edge(int to, long weight) {}
    record FromResult(int source, List<Integer> order,
            boolean[] reachable, long[] best, int[] parent) {}
    record GlobalResult(List<Integer> order, boolean[] hasEdge,
            long[] best, int[] parent, int[] starts, int end) {}
    record OracleFrom(boolean[] reachable, long[] best) {}
    record GlobalOracle(boolean exists, long best) {}
    record Counts(int graphs, int dags, int sources) {}

    static List<List<Edge>> graph(int n, long[][] edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("Invalid graph");
        }
        List<List<Edge>> g = new ArrayList<>();
        for (int u = 0; u < n; u++) g.add(new ArrayList<>());
        for (long[] e : edges) {
            if (e == null || e.length != 3
                    || e[0] < 0 || e[0] >= n
                    || e[1] < 0 || e[1] >= n) {
                throw new IllegalArgumentException("Invalid edge");
            }
            g.get((int) e[0]).add(
                    new Edge((int) e[1], e[2]));
        }
        return g;
    }

    // Kahn: xac nhan TOAN BO do thi khong co chu trinh.
    static List<Integer> topoOrThrow(List<List<Edge>> g) {
        int n = g.size();
        int[] indegree = new int[n];
        for (int u = 0; u < n; u++) {
            for (Edge e : g.get(u)) indegree[e.to()]++;
        }
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int u = 0; u < n; u++) {
            if (indegree[u] == 0) queue.addLast(u);
        }
        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);
            for (Edge e : g.get(u)) {
                int v = e.to();
                indegree[v]--;
                if (indegree[v] == 0) queue.addLast(v);
            }
        }
        if (order.size() != n) {
            throw new IllegalArgumentException("Graph is not a DAG");
        }
        return List.copyOf(order);
    }

    static FromResult longestFrom(
            List<List<Edge>> g, int source) {
        if (source < 0 || source >= g.size()) {
            throw new IllegalArgumentException("Invalid source");
        }
        List<Integer> order = topoOrThrow(g);
        int n = g.size();
        boolean[] reached = new boolean[n];
        long[] best = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);
        reached[source] = true;
        best[source] = 0;

        for (int u : order) {
            if (!reached[u]) continue;
            for (Edge e : g.get(u)) {
                int v = e.to();
                long candidate =
                        Math.addExact(best[u], e.weight());
                if (!reached[v] || candidate > best[v]) {
                    reached[v] = true;
                    best[v] = candidate;
                    parent[v] = u;
                }
            }
        }
        return new FromResult(
                source, order, reached, best, parent);
    }

    // Duong dai nhat o BAT KY DAU, PHAI co >=1 canh.
    static GlobalResult longestNonEmpty(List<List<Edge>> g) {
        List<Integer> order = topoOrThrow(g);
        int n = g.size();
        boolean[] hasEdge = new boolean[n];
        long[] best = new long[n];
        int[] parent = new int[n];
        int[] starts = new int[n];
        Arrays.fill(parent, -1);
        Arrays.fill(starts, -1);

        for (int u : order) {
            for (Edge e : g.get(u)) {
                int v = e.to();
                long w = e.weight();

                // Ung vien bat dau moi bang canh u->v.
                if (!hasEdge[v] || w > best[v]) {
                    hasEdge[v] = true;
                    best[v] = w;
                    parent[v] = u;
                    starts[v] = u;
                }

                // Ung vien noi duong da co >=1 canh toi u.
                if (hasEdge[u]) {
                    long candidate = Math.addExact(best[u], w);
                    if (candidate > best[v]) {
                        hasEdge[v] = true;
                        best[v] = candidate;
                        parent[v] = u;
                        starts[v] = starts[u];
                    }
                }
            }
        }

        int end = -1;
        for (int v = 0; v < n; v++) {
            if (hasEdge[v]
                    && (end == -1 || best[v] > best[end])) {
                end = v;
            }
        }
        return new GlobalResult(
                order, hasEdge, best, parent, starts, end);
    }

    static List<Integer> pathFrom(
            FromResult result, int target) {
        if (target < 0 || target >= result.best().length) {
            throw new IllegalArgumentException("Invalid target");
        }
        if (!result.reachable()[target]) return List.of();

        List<Integer> reversed = new ArrayList<>();
        int n = result.parent().length;
        for (int v = target; v != -1; v = result.parent()[v]) {
            reversed.add(v);
            if (reversed.size() > n) {
                throw new IllegalStateException("Bad source parent");
            }
        }
        Collections.reverse(reversed);
        if (reversed.get(0) != result.source()) {
            throw new IllegalStateException("Wrong source");
        }
        return List.copyOf(reversed);
    }

    static List<Integer> pathGlobal(GlobalResult result) {
        if (result.end() == -1) return List.of();
        int start = result.starts()[result.end()];
        int v = result.end();
        List<Integer> reversed = new ArrayList<>();

        while (true) {
            if (v < 0 || reversed.size() > result.parent().length) {
                throw new IllegalStateException("Bad global parent");
            }
            reversed.add(v);
            if (v == start) break;
            v = result.parent()[v];
        }
        Collections.reverse(reversed);
        return List.copyOf(reversed);
    }

    static String showPath(List<Integer> path) {
        if (path.isEmpty()) return "none";
        StringJoiner out = new StringJoiner("->");
        for (int v : path) out.add(Integer.toString(v));
        return out.toString();
    }

    static String showFrom(FromResult result) {
        StringJoiner out = new StringJoiner(", ", "[", "]");
        for (int v = 0; v < result.best().length; v++) {
            out.add(result.reachable()[v]
                    ? Long.toString(result.best()[v]) : "-INF");
        }
        return out.toString();
    }

    static String showGlobal(GlobalResult result) {
        return result.end() == -1 ? "none"
                : Long.toString(result.best()[result.end()]);
    }

    // Oracle cycle doc lap: bao dong kha dat Warshall.
    static boolean oracleCycle(List<List<Edge>> g) {
        int n = g.size();
        boolean[][] reach = new boolean[n][n];
        for (int u = 0; u < n; u++) {
            for (Edge e : g.get(u)) reach[u][e.to()] = true;
        }
        // Khong mac dinh reach[u][u] = true.
        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    if (reach[i][k] && reach[k][j]) {
                        reach[i][j] = true;
                    }
                }
            }
        }
        for (int v = 0; v < n; v++) {
            if (reach[v][v]) return true;
        }
        return false;
    }

    // Oracle duyet moi duong tren DAG nho, khong dung topo.
    static void walkFrom(List<List<Edge>> g, int u, long sum,
            boolean[] reached, long[] best) {
        if (!reached[u] || sum > best[u]) {
            reached[u] = true;
            best[u] = sum;
        }
        for (Edge e : g.get(u)) {
            walkFrom(g, e.to(),
                    Math.addExact(sum, e.weight()), reached, best);
        }
    }

    static OracleFrom oracleFrom(
            List<List<Edge>> g, int source) {
        boolean[] reached = new boolean[g.size()];
        long[] best = new long[g.size()];
        walkFrom(g, source, 0, reached, best);
        return new OracleFrom(reached, best);
    }

    static final class Holder {
        boolean exists;
        long best;
    }

    static void walkGlobal(List<List<Edge>> g, int u,
            long sum, int usedEdges, Holder holder) {
        if (usedEdges > 0
                && (!holder.exists || sum > holder.best)) {
            holder.exists = true;
            holder.best = sum;
        }
        for (Edge e : g.get(u)) {
            walkGlobal(g, e.to(),
                    Math.addExact(sum, e.weight()),
                    usedEdges + 1, holder);
        }
    }

    static GlobalOracle oracleGlobal(List<List<Edge>> g) {
        Holder holder = new Holder();
        for (int s = 0; s < g.size(); s++) {
            walkGlobal(g, s, 0, 0, holder);
        }
        return new GlobalOracle(holder.exists, holder.best);
    }

    static boolean validTopo(
            List<List<Edge>> g, List<Integer> order) {
        int n = g.size();
        if (order.size() != n) return false;
        int[] pos = new int[n];
        Arrays.fill(pos, -1);
        for (int i = 0; i < n; i++) {
            int v = order.get(i);
            if (v < 0 || v >= n || pos[v] != -1) return false;
            pos[v] = i;
        }
        for (int u = 0; u < n; u++) {
            for (Edge e : g.get(u)) {
                if (pos[u] >= pos[e.to()]) return false;
            }
        }
        return true;
    }

    static boolean validFromPath(
            List<List<Edge>> g, FromResult a, int target) {
        List<Integer> path = pathFrom(a, target);
        if (!a.reachable()[target]) return path.isEmpty();
        if (path.isEmpty() || path.get(0) != a.source()
                || path.get(path.size() - 1) != target) {
            return false;
        }
        boolean[] seen = new boolean[g.size()];
        long sum = 0;
        for (int i = 0; i < path.size(); i++) {
            int v = path.get(i);
            if (seen[v]) return false;
            seen[v] = true;
            if (i == 0) continue;
            int u = path.get(i - 1);
            if (a.parent()[v] != u) return false;
            boolean found = false;
            for (Edge e : g.get(u)) {
                if (e.to() == v && Math.addExact(
                        a.best()[u], e.weight()) == a.best()[v]) {
                    sum = Math.addExact(sum, e.weight());
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }
        return sum == a.best()[target];
    }

    // Khong truy parent qua starts[end].
    static boolean validGlobalPath(
            List<List<Edge>> g, GlobalResult a) {
        List<Integer> path = pathGlobal(a);
        if (a.end() == -1) {
            if (!path.isEmpty()) return false;
            for (List<Edge> es : g) {
                if (!es.isEmpty()) return false;
            }
            return true;
        }
        if (path.size() < 2
                || path.get(0) != a.starts()[a.end()]
                || path.get(path.size() - 1) != a.end()) {
            return false;
        }

        boolean[] seen = new boolean[g.size()];
        long sum = 0;
        for (int i = 0; i < path.size(); i++) {
            int v = path.get(i);
            if (seen[v]) return false;
            seen[v] = true;
            if (i == 0) continue;
            int u = path.get(i - 1);
            if (a.parent()[v] != u) return false;
            boolean found = false;
            for (Edge e : g.get(u)) {
                if (e.to() != v) continue;
                long candidate = i == 1 ? e.weight()
                        : Math.addExact(a.best()[u], e.weight());
                if (candidate == a.best()[v]) {
                    sum = Math.addExact(sum, e.weight());
                    found = true;
                    break;
                }
            }
            if (!found) return false;
        }
        return sum == a.best()[a.end()];
    }

    static Counts verifySmallGraphs() {
        int graphs = 0, dags = 0, sources = 0;
        for (int n = 0; n <= 4; n++) {
            int total = 1 << (n * n);
            for (int mask = 0; mask < total; mask++) {
                List<List<Edge>> g = new ArrayList<>();
                for (int u = 0; u < n; u++) {
                    g.add(new ArrayList<>());
                }
                for (int u = 0; u < n; u++) {
                    for (int v = 0; v < n; v++) {
                        if ((mask & (1 << (u * n + v))) != 0) {
                            long w = (u * 5 + v * 3 + 2) % 9 - 4;
                            g.get(u).add(new Edge(v, w));
                        }
                    }
                }

                boolean cyc = oracleCycle(g);
                List<Integer> order = null;
                boolean rejected = false;
                try {
                    order = topoOrThrow(g);
                } catch (IllegalArgumentException ex) {
                    rejected = true;
                }
                if (cyc != rejected
                        || (!cyc && !validTopo(g, order))) {
                    throw new AssertionError(
                            "Cycle/topo n=" + n + " mask=" + mask);
                }

                if (!cyc) {
                    dags++;
                    GlobalResult glob = longestNonEmpty(g);
                    GlobalOracle refG = oracleGlobal(g);
                    if ((glob.end() != -1) != refG.exists()
                            || (refG.exists()
                                && glob.best()[glob.end()]
                                   != refG.best())
                            || !validGlobalPath(g, glob)) {
                        throw new AssertionError(
                                "Global n=" + n + " mask=" + mask);
                    }

                    for (int s = 0; s < n; s++) {
                        FromResult actual = longestFrom(g, s);
                        OracleFrom ref = oracleFrom(g, s);
                        for (int v = 0; v < n; v++) {
                            if (actual.reachable()[v]
                                    != ref.reachable()[v]
                                    || (actual.reachable()[v]
                                        && actual.best()[v]
                                           != ref.best()[v])
                                    || !validFromPath(g, actual, v)) {
                                throw new AssertionError(
                                        "Source n=" + n
                                        + " mask=" + mask
                                        + " s=" + s + " v=" + v);
                            }
                        }
                        sources++;
                    }
                }
                graphs++;
            }
        }
        return new Counts(graphs, dags, sources);
    }

    public static void main(String[] args) {
        List<List<Edge>> main = graph(7, new long[][]{
            {0,1,3}, {0,2,2}, {1,3,4}, {2,3,6},
            {1,4,-5}, {3,4,-2}, {3,5,2}, {4,5,7},
            {2,6,-3}, {5,6,1}
        });
        FromResult s = longestFrom(main, 0);
        GlobalResult glob = longestNonEmpty(main);
        System.out.println("sourceTopo=" + s.order());
        System.out.println("sourceDistances=" + showFrom(s));
        System.out.println("sourcePath6="
                + showPath(pathFrom(s, 6)));
        System.out.println("sourcePath0="
                + showPath(pathFrom(s, 0)));
        System.out.println("globalWeight=" + showGlobal(glob));
        System.out.println("globalPath="
                + showPath(pathGlobal(glob)));

        List<List<Edge>> disconnected = graph(4,
                new long[][]{{0,1,-3}, {2,3,8}});
        FromResult d = longestFrom(disconnected, 0);
        GlobalResult dg = longestNonEmpty(disconnected);
        System.out.println("unreachableDistances=" + showFrom(d));
        System.out.println("unreachablePath3="
                + showPath(pathFrom(d, 3)));
        System.out.println("unreachableGlobalWeight="
                + showGlobal(dg));
        System.out.println("unreachableGlobalPath="
                + showPath(pathGlobal(dg)));

        List<List<Edge>> negative = graph(3,
                new long[][]{{0,1,-5}, {0,2,-2}, {1,2,-4}});
        FromResult neg = longestFrom(negative, 0);
        GlobalResult ng = longestNonEmpty(negative);
        System.out.println("negativeSourceDistances="
                + showFrom(neg));
        System.out.println("negativeGlobalWeight="
                + showGlobal(ng));
        System.out.println("negativeGlobalPath="
                + showPath(pathGlobal(ng)));

        List<List<Edge>> tie = graph(4,
                new long[][]{
                    {0,1,2}, {0,2,1}, {1,3,0}, {2,3,1}
                });
        System.out.println("tieSourcePath3="
                + showPath(pathFrom(longestFrom(tie, 0), 3)));

        List<List<Edge>> parallel = graph(3,
                new long[][]{{0,1,3}, {0,1,8}, {1,2,2}});
        System.out.println("parallelDistances="
                + showFrom(longestFrom(parallel, 0)));

        try {
            longestFrom(graph(3,
                    new long[][]{{0,1,1}, {1,2,2}, {2,0,-3}}), 0);
            throw new AssertionError("Cycle accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("cycleRejected=" + ex.getMessage());
        }

        try {
            longestNonEmpty(graph(1,
                    new long[][]{{0,0,-5}}));
            throw new AssertionError("Self-loop accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("selfLoopRejected=" + ex.getMessage());
        }

        List<List<Edge>> empty = graph(0, new long[0][0]);
        System.out.println("emptyTopo=" + topoOrThrow(empty));
        System.out.println("emptyGlobalWeight="
                + showGlobal(longestNonEmpty(empty)));

        Counts checks = verifySmallGraphs();
        System.out.println("graphsChecked=" + checks.graphs());
        System.out.println("dagsChecked=" + checks.dags());
        System.out.println("sourcesChecked=" + checks.sources());
    }
}
~~~

Lưu thành tệp **DagLongestPathsDemo.java**, chạy bằng **JDK 17 trở lên**:

~~~bash
javac DagLongestPathsDemo.java
java DagLongestPathsDemo
~~~

**Đầu ra dự kiến:**

~~~text
sourceTopo=[0, 1, 2, 3, 4, 5, 6]
sourceDistances=[0, 3, 2, 8, 6, 13, 14]
sourcePath6=0->2->3->4->5->6
sourcePath0=0
globalWeight=14
globalPath=0->2->3->4->5->6
unreachableDistances=[0, -3, -INF, -INF]
unreachablePath3=none
unreachableGlobalWeight=8
unreachableGlobalPath=2->3
negativeSourceDistances=[0, -5, -2]
negativeGlobalWeight=-2
negativeGlobalPath=0->2
tieSourcePath3=0->1->3
parallelDistances=[0, 8, 10]
cycleRejected=Graph is not a DAG
selfLoopRejected=Graph is not a DAG
emptyTopo=[]
emptyGlobalWeight=none
graphsChecked=66067
dagsChecked=573
sourcesChecked=2254
~~~

### Giải thích kết quả

**Nguồn 0 trong main:** khoảng cách dài nhất tới 6 là 14, theo đường `0→2→3→4→5→6`. Cạnh âm 3→4 không làm đường sai; tổng cả tuyến mới quyết định.

**Toàn cục trong main:** dài nhất bắt buộc có cạnh cũng bằng 14, tình cờ bắt đầu tại 0. Trong đồ thị rời, biến thể từ nguồn 0 không tới được 3, nhưng đường toàn cục 2→3 có tổng 8.

**Chỉ có cạnh âm:** toàn cục với ít nhất một cạnh cho trọng số −2 theo 0→2; nếu đề cho đường 0 cạnh, một đường chỉ có một đỉnh sẽ cho giá trị 0 tốt hơn.

**Hòa trọng số:** đường 0→1→3 và 0→2→3 đều có tổng 2. Code chỉ cập nhật khi lớn hơn nên giữ đường phát hiện trước là 0→1→3.

**Cạnh song song:** hai cạnh 0→1 có giá 3 và 8; chọn cạnh 8, nối 1→2 giá 2, cho best[2]=10. Muốn in chính danh sách cạnh khi có song song, nên lưu thêm id của cạnh được chọn, không chỉ mảng parent đỉnh.

**Chu trình:** Kahn từ chối cả chu trình 3 đỉnh và self-loop; dấu tổng trọng số chu trình không thay đổi sự thật rằng đồ thị không phải DAG.

**Đồ thị rỗng:** n=0 có topo rỗng, nhưng không có nguồn hợp lệ; biến thể toàn cục bắt buộc có cạnh trả none.

## 11. Oracle kiểm thử 66.067 đồ thị nhỏ

Chương trình vét cạn mọi đồ thị **đơn có hướng** n=0..4. Với n đỉnh, mỗi cặp có thứ tự u→v (kể cả u=v) có hai khả năng: có hoặc không có cạnh. Vì vậy tổng số là `2^(n²)`.

| n | Đồ thị | DAG |
| ---: | ---: | ---: |
| 0 | 1 | 1 |
| 1 | 2 | 1 |
| 2 | 16 | 3 |
| 3 | 512 | 25 |
| 4 | 65.536 | 543 |
| **Tổng** | **66.067** | **573** |

Với mỗi cạnh có mặt, gán trọng số xác định `w(u,v)=((5u+3v+2) mod 9)−4`, gồm giá trị âm, 0 và dương. Bộ vét cạn không chứa hai cạnh song song cho cùng cặp u,v; ví dụ `parallel` trong `main` kiểm tra cạnh trùng riêng.

### Độc lập kiểm tra DAG

Dùng oracle bao đóng đường đi kiểu Warshall. Ban đầu `reach[u][v]` chỉ true khi có cạnh u→v, **không tự đặt reach[u][u]=true**. Khi cho phép các đỉnh trung gian, nếu tồn tại đường quay về u có độ dài dương thì reach[u][u] sẽ true, nghĩa là có chu trình. Kahn phải **từ chối đúng** những đồ thị oracle báo có vòng.

Với DAG, còn xác nhận order chứa đủ mỗi đỉnh đúng một lần và mọi cạnh u→v có vị trí u trước v.

### Độc lập kiểm tra giá trị dài nhất

Thay vì dùng DP, oracle **vét cạn mọi đường**:
- Với mỗi nguồn s của một DAG, đi qua tất cả chuỗi cạnh có hướng bắt đầu từ s và ghi trọng số lớn nhất tới từng v.
- Với biến thể toàn cục, thử tất cả đỉnh bắt đầu; chỉ ghi nhận đường nếu đã dùng **ít nhất một cạnh**.
- Đối chiếu cờ reachable, giá trị best, và kiểm tra từng parent của đường trả về tương ứng với cạnh thật và tổng đúng.
- Với global, kiểm tra đường đi thực sự dừng truy parent tại `starts[end]` và không vô tình ghép một tiền tố khác.

Trong 573 DAG, tổng số lựa chọn nguồn hợp lệ là **2.254**. Chương trình sẽ in `graphsChecked=66067`, `dagsChecked=573`, `sourcesChecked=2254` sau khi kiểm thử xong.

Các oracle dùng bao đóng O(n³) và vét cạn đường chỉ nên dùng cho **đồ thị nhỏ**. Kết quả kiểm thử không thay chứng minh; tính đúng tổng quát đến từ bất biến topo và hai dạng đường kết thúc bằng cạnh u→v.

## 12. Trường hợp biên và lỗi phổ biến

| Trường hợp | Kết quả đúng |
| --- | --- |
| n=0 | DAG rỗng; topo=[], không có nguồn s hợp lệ, global nonempty=none |
| Một đỉnh, không cạnh | Từ nguồn best[s]=0; global nonempty=none |
| Một đỉnh có self-loop | Từ chối vì có chu trình |
| Mọi cạnh âm | Đường từ s tới s vẫn là 0; global nonempty có thể âm |
| Nhiều thành phần | Từ nguồn chỉ xét reachable; global xét toàn đồ thị |
| Chu trình ở thành phần khác | Từ chối vì hợp đồng cần DAG toàn cục |
| Có đường trọng số đúng 0 | reachable=true, không phải unreachable |
| Cạnh song song khác trọng số | Relax cả hai, chọn kết quả lớn hơn |
| Hai đường đồng tối ưu | Giá trị như nhau, parent theo quy tắc hòa |
| Long.MIN_VALUE là giá trị thật | Dùng reachable riêng để tránh nhầm với sentinel |
| Tổng tràn long | Math.addExact báo lỗi, cần số học rộng hơn |
| Không cạnh, n>0 | Từ nguồn chỉ s reachable, global nonempty=none |
| Đề hỏi nhiều cạnh nhất | Đặt trọng số mỗi cạnh =1 |
| Đề cho phép đường 0 cạnh | Global tối đa không nhỏ hơn 0 nếu n>0 |

Các lỗi cần tránh:

1. Chạy max-relax một lượt khi đồ thị **có chu trình**.
2. Duyệt nhãn đỉnh tăng dần mà không kiểm tra **thứ tự topo**.
3. Dùng `best[v]=0` cho mọi đỉnh trong bài **từ một nguồn**, làm phát sinh đường từ nguồn khác.
4. Dùng `Long.MIN_VALUE` làm −INF rồi cộng trực tiếp, tạo đường giả hoặc tràn.
5. Bỏ qua cạnh âm vì tưởng đường dài nhất không dùng cạnh âm.
6. Áp thuật toán **tham lam chọn cạnh lớn nhất tiếp theo**.
7. Nhầm “nhiều cạnh nhất” với “tổng trọng số lớn nhất”.
8. Không phân biệt bài **toàn cục có ít nhất một cạnh** với bài cho phép 0 cạnh.
9. Truy parent toàn cục tới −1, vượt qua `globalStart[end]`.
10. Không cập nhật parent/start khi best cải thiện.
11. Quên giữ chính sách hòa xác định khi giá trị bằng nhau.
12. Bỏ qua cạnh song song khi tính indegree hoặc relax.
13. Không xét self-loop hoặc thành phần chứa chu trình tách biệt.
14. Dùng DFS vét cạn cho DAG lớn dù đã có DP O(V+E).
15. Không kiểm tra overflow trong phép cộng trọng số.
16. Quên rằng parent chỉ xác định **đỉnh**, không xác định **cạnh** trong đồ thị đa cạnh.
17. Dùng thuật toán Dijkstra sau khi đổi dấu trọng số mà không xem giả thiết cạnh âm.
18. Báo best=0 thay cho unreachable dù không có đường từ nguồn.
19. Coi “có đường tới s” là bằng một đường có cạnh quay lại s, điều bị cấm trong DAG.
20. Nói độ phức tạp chỉ O(V) mà bỏ qua số cạnh E.

## 13. Bài tập kèm đáp án

**Bài 1 — max-relax.** `0→1 (3),0→2 (2),1→3 (4),2→3 (6)`. Nguồn 0, best[3] là bao nhiêu?

*Đáp án:* `max(3+4,2+6)=8`, đường 0→2→3.

**Bài 2 — cạnh âm.** `0→1 (−7),1→2 (15),0→2 (4)`. Đường dài nhất từ 0 tới 2?

*Đáp án:* 0→1→2 có tổng 8, tốt hơn đường trực tiếp trọng số 4.

**Bài 3 — tách thành phần.** `0→1 (−3),2→3 (8)`, s=0. Đáp án tới 3 và đáp án toàn cục có cạnh?

*Đáp án:* Từ nguồn 0: 3 không tới được. Toàn cục có cạnh: 2→3 trọng số 8.

**Bài 4 — hai định nghĩa toàn cục.** DAG `0→1 (−5),0→2 (−2)`. Nếu bắt buộc có cạnh thì dài nhất bao nhiêu? Nếu cho phép 0 cạnh?

*Đáp án:* Bắt buộc có cạnh: −2. Cho phép 0 cạnh: 0.

**Bài 5 — topo.** Có cạnh `2→1`; thứ tự `[0,1,2]` có đúng không?

*Đáp án:* Không, vì 2 phải đứng trước 1. `[0,2,1]` hợp lệ nếu không có ràng buộc khác.

**Bài 6 — self-loop.** Một đỉnh 0 có cạnh `0→0 (−100)`. Có là DAG?

*Đáp án:* Không. Dù trọng số âm, vẫn là chu trình một cạnh.

**Bài 7 — nguồn đơn độc.** Nếu s không có cạnh đi ra, best[s] bằng bao nhiêu?

*Đáp án:* 0, tương ứng đường chỉ gồm s, 0 cạnh.

**Bài 8 — song song.** `0→1 (3),0→1 (8),1→2 (2)`. Từ 0, best[2]?

*Đáp án:* 10, chọn cạnh 0→1 trọng số 8 và 1→2 trọng số 2.

**Bài 9 — hòa.** `0→1 (2),0→2 (1),1→3 (0),2→3 (1)`. Nếu 1 xử lý trước 2 và chỉ cập nhật khi candidate>best, parent[3]?

*Đáp án:* 1, đường 0→1→3 trọng số 2. Đường 0→2→3 cũng có trọng số 2.

**Bài 10 — lý do đúng.** Vì sao mọi best[v] đã đúng khi v đến lượt theo topo?

*Đáp án:* Mọi cạnh đi vào v xuất phát từ u đứng trước v, nên mọi ứng viên qua tiền nhiệm u đã được relax khi best[u] tối ưu.

**Bài 11 — chứng cứ toàn cục.** Vì sao phải dừng truy parent tại start của đường đã chọn?

*Đáp án:* Một đường tối ưu có thể bắt đầu bằng cạnh mới từ u, dù u còn parent của đường khác. Đi quá u làm chứng cứ chứa tiền tố không thuộc tổng tối ưu.

**Bài 12 — nhiều nguồn.** Một DAG không thay đổi, có thể tái sử dụng topo cho 100 nguồn không?

*Đáp án:* Có. Tính topo một lần, khởi tạo lại reachable/best/parent rồi max-relax cho từng nguồn.

**Bài 13 — có chu trình dương.** Nếu cho phép lặp đỉnh và từ s có thể đi tới một vòng dương rồi tới t, đường dài nhất có giá trị hữu hạn không?

*Đáp án:* Không, có thể lặp vòng dương tùy ý để tăng tổng không giới hạn. Đó không phải bài DAG.

**Bài 14 — số cạnh.** Đường 0→2→3→4 có bao nhiêu cạnh và bao nhiêu đỉnh?

*Đáp án:* 3 cạnh và 4 đỉnh. Nếu mỗi cạnh gán trọng số 1 thì tổng trọng số là 3.

## Kết luận

**Đường đi dài nhất trên DAG giải được trong O(V+E)** vì thứ tự topo khiến mọi tiền nhiệm của một đỉnh được xử lý trước nó. Chỉ cần thay phép thư giãn **min** bằng **max**, dùng cờ reachable để phân biệt đường âm/0 với không có đường, và ghi parent khi có cải thiện.

Khi bài hỏi **đường dài nhất ở bất kỳ đâu**, phải làm rõ có cho phép **đường 0 cạnh** hay không; nếu bắt buộc có cạnh, DP cần xét cả “bắt đầu mới tại một cạnh” và “nối tiếp một đường đã có cạnh”, đồng thời lưu điểm bắt đầu để khôi phục chứng cứ chính xác. Trọng số âm không cản trở thuật toán; **chu trình có hướng mới là rào cản phải kiểm tra trước**.
