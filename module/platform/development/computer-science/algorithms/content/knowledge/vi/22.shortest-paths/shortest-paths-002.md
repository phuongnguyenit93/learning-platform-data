# Đường đi ngắn nhất trên đồ thị có hướng không chu trình

**Đồ thị có hướng không chu trình** (*Directed Acyclic Graph*, viết tắt **DAG**) cho phép giải bài toán đường đi ngắn nhất từ một nguồn tới mọi đỉnh trong **O(V+E)** bằng cách **sắp xếp topo rồi thư giãn mỗi cạnh một lần**. Đây là một trường hợp đặc biệt rất mạnh: trọng số cạnh **được phép âm**, miễn đồ thị thực sự **không có chu trình có hướng** và các phép tính số không bị tràn.

Bài học thuộc nhóm **Đường đi ngắn nhất** của Computer Science Algorithms. Trọng tâm là: vì sao thứ tự topo thay thế được hàng đợi ưu tiên, cách triển khai đúng với cạnh âm và đỉnh không thể đến, cách khôi phục đường đi, chứng minh tính đúng, các bẫy liên quan đến chu trình và số học, cùng chương trình Java 17 độc lập.

## 1. Bài toán và hợp đồng đầu vào

Cho một đồ thị có hướng `G=(V,E)` với n đỉnh đánh số từ `0` tới `n−1`. Mỗi cạnh `u→v` có trọng số `w(u,v)`, là một số nguyên có thể dương, bằng 0 hoặc âm. Cho một đỉnh nguồn `s` hợp lệ.

**Yêu cầu:** với mỗi đỉnh v, tìm chi phí nhỏ nhất của một đường đi có hướng từ s đến v:

\[
d[v]=\min_{\text{đường đi có hướng }s\leadsto v}
\sum_{e\text{ trên đường}}w(e).
\]

Nếu không có đường đi từ s tới v, ta ghi `INF` hoặc “không thể đến”, chứ **không** gán giá trị 0 vì 0 có thể là một khoảng cách hợp lệ.

Đường đi độ dài 0 từ s tới chính nó có tổng trọng số **0**, nên `d[s]=0`. Với DAG, một đường đi không thể lặp đỉnh: nếu lặp một đỉnh thì phần giữa hai lần xuất hiện tạo một chu trình có hướng, trái với giả thiết.

### Điều kiện áp dụng

- Đồ thị **có hướng** và **không có chu trình có hướng** ở **toàn bộ đồ thị** theo hợp đồng chương trình.
- Đỉnh nguồn `s` thuộc miền `0..n−1`. Đồ thị n=0 vẫn là DAG, nhưng **không có nguồn hợp lệ** để truy vấn đường đi.
- Trọng số cạnh có thể âm, dương hoặc bằng 0; không yêu cầu tính không âm của từng cạnh.
- Với chương trình dùng `long`, **mọi phép cộng ứng viên được thực hiện** phải nằm trong miền 64-bit có dấu. Nếu dữ liệu có thể vượt miền này, dùng `BigInteger` hoặc một mô hình số học an toàn hơn.
- Có thể có cạnh song song cùng chiều; khi đó mỗi cạnh là một ứng viên độc lập. Có thể có đỉnh không tới được từ s.
- Bất kỳ **self-loop** `u→u` đều là chu trình, nên không thể thuộc DAG hợp lệ.

**Phân biệt:** một **cạnh âm** không phải là **chu trình âm**. DAG hoàn toàn không có chu trình; do đó không thể có chu trình âm, nhưng vẫn có thể có nhiều cạnh trọng số âm.

## 2. Kiến thức nền: đường đi và DAG

Với đường đi:

~~~text
s = v0 -> v1 -> ... -> vk = t
~~~

trọng số của đường là tổng trọng số **các cạnh**, không phải số đỉnh. Nếu một đường gồm 5 đỉnh thì có 4 cạnh; trọng số của nó có thể âm ngay cả khi có nhiều cạnh dương.

### Thứ tự topo (topological order)

Một **thứ tự topo** là danh sách gồm tất cả n đỉnh, mỗi đỉnh đúng một lần, sao cho với mọi cạnh `u→v`, u đứng **trước** v. Ví dụ:

~~~text
0 → 2 → 1 → 3
    \       \
     → 5     → 4
~~~

Đồ thị có thể có nhiều thứ tự topo; không cần thứ tự được sắp theo số nhãn đỉnh.

Tính chất quan trọng:

\[
G \text{ là DAG}\quad\Longleftrightarrow\quad
\text{tồn tại thứ tự topo của toàn bộ đỉnh}.
\]

Nếu có chu trình `a→b→c→a` thì thứ tự phải đặt a trước b, b trước c và c trước a — điều bất khả thi.

### Vì sao topo đặc biệt hữu ích cho đường đi ngắn nhất?

Nếu u→v là một cạnh, **u luôn được xử lý trước v** trong topo. Bởi vậy khi tới lượt v, **mọi đỉnh có cạnh đi trực tiếp vào v** đã được xử lý xong. Các phương án đi tới v thông qua từng đỉnh trước đó đều đã được xét.

Điều này đúng **bất kể trọng số âm hay dương**. Trong đồ thị có chu trình, một đỉnh có thể phụ thuộc trở lại chính nó qua một chuỗi cạnh, làm quy trình duyệt mỗi đỉnh một lần không còn bảo đảm. DAG cắt đứt sự phụ thuộc vòng tròn ấy.

## 3. Thuật toán: topo rồi thư giãn cạnh

Dùng các mảng:

- `reachable[v]`: đã tìm được **ít nhất một đường hợp lệ** từ s tới v.
- `dist[v]`: tổng trọng số tốt nhất đã biết, **chỉ có ý nghĩa khi reachable[v]=true**.
- `parent[v]`: đỉnh đứng ngay trước v trong đường đang được chọn để đạt `dist[v]`; nguồn có parent = −1.

Khởi tạo:

~~~text
reachable[*] = false
dist[*] = 0          // giá trị tại đỉnh chưa reachable chỉ là chỗ chứa
parent[*] = -1
reachable[s] = true
dist[s] = 0
~~~

Việc dùng một mảng boolean riêng tránh nhầm một giá trị khoảng cách thực bằng `Long.MAX_VALUE` với ký hiệu `INF`. Không được dùng `dist[v]=0` ở ô chưa reachable như một khoảng cách sẵn có.

### Thư giãn (relaxation)

Xét cạnh `u→v` có trọng số w. Chỉ khi **u reachable**, ta mới có một phương án hợp lệ đi tới v qua u:

\[
candidate=dist[u]+w(u,v).
\]

Nếu v chưa reachable hoặc `candidate<dist[v]`:

~~~text
reachable[v] = true
dist[v] = candidate
parent[v] = u
~~~

Nếu candidate bằng dist[v], có thể giữ parent cũ; điều này không làm sai giá trị khoảng cách, nhưng ảnh hưởng **đường đi cụ thể** được in ra. Bài học và mã Java dùng so sánh **nghiêm ngặt** `<`: khi hòa, giữ đường đã tìm trước.

### Toàn bộ giải thuật

~~~text
DAG-Shortest-Paths(graph, source):
    topo = topologicalSort(graph)
    nếu topo không gồm đủ n đỉnh:
        từ chối vì graph không phải DAG

    reachable[*] = false
    dist[*] = 0
    parent[*] = -1
    reachable[source] = true
    dist[source] = 0

    for u in topo:
        if not reachable[u]:
            continue
        for every directed edge (u,v,w):
            candidate = dist[u] + w
            if not reachable[v] or candidate < dist[v]:
                reachable[v] = true
                dist[v] = candidate
                parent[v] = u

    return reachable, dist, parent, topo
~~~

**Không có vòng lặp thư giãn n−1 lần như Bellman–Ford.** Mỗi cạnh được xét **một lần** khi tới đỉnh đầu u của nó trong thứ tự topo. Nhờ không có chu trình, sau khi xử lý xong u thì khoảng cách tới u đã tối ưu.

## 4. Tạo thứ tự topo bằng thuật toán Kahn

Để triển khai rõ ràng, trước hết dùng **Kahn**:

1. Tính `indegree[v]` bằng số **cạnh đi vào** v.
2. Cho tất cả đỉnh có `indegree==0` vào hàng đợi.
3. Lấy u ra, thêm u vào kết quả topo.
4. Với **mỗi cạnh u→v**, trừ `indegree[v]` một lần; nếu vừa bằng 0, thêm v vào hàng đợi.
5. Nếu lấy được đúng n đỉnh, có thứ tự topo. Nếu ít hơn n, đồ thị có chu trình và **không được chạy** thuật toán đường đi DAG như thể đây là DAG.

### Vì sao phải kiểm tra toàn bộ đồ thị?

Ví dụ:

~~~text
Nguồn s=0:       0 → 1

Một phần khác:   2 → 3 → 2
~~~

Phần tới được từ s có thể không có vòng, nhưng toàn bộ đồ thị **không phải DAG**. Theo hợp đồng bài này, phải **từ chối** thay vì chỉ kiểm tra phần nguồn có thể đến.

Một bài toán khác có thể yêu cầu chỉ tìm đường trên tiểu đồ thị khả đạt từ s; khi ấy giả thiết và cách xác minh phải được định nghĩa lại. Không được âm thầm đổi phạm vi khi chương trình cam kết đầu vào là DAG.

### Cạnh song song trong Kahn

Nếu `adj[0]` chứa hai cạnh khác nhau đều tới 1, `indegree[1]` phải tăng 2 và khi lấy 0 ra phải giảm 2. Một cạnh trùng **không phải** chu trình; chỉ khi còn đường có hướng quay về đỉnh đã xuất phát mới có chu trình.

### Chi phí của bước topo

Kahn tính indegree và duyệt mỗi cạnh một lần, đưa mỗi đỉnh vào hàng đợi tối đa một lần:

\[
T_{\text{topo}}=O(V+E),\qquad M_{\text{phụ}}=O(V).
\]

Bản DFS topo khác cũng có thể dùng, nhưng phải phát hiện cạnh tới đỉnh đang GRAY. Với bài đường đi, sử dụng Kahn giúp làm rõ **kiểm tra DAG trước khi thư giãn** và tránh phụ thuộc ngăn xếp đệ quy.

## 5. Mô phỏng một DAG có cạnh âm

Xét 6 đỉnh và các cạnh:

| Cạnh | Trọng số |
| --- | ---: |
| 0→1 | 4 |
| 0→2 | 2 |
| 2→1 | −5 |
| 1→3 | 3 |
| 2→3 | 10 |
| 1→4 | 6 |
| 3→4 | 1 |
| 2→5 | 12 |
| 4→5 | −2 |

Đỉnh nguồn `s=0`. Đây là DAG; lưu ý cạnh `2→1` buộc **2 đứng trước 1**, dù nhãn 2 lớn hơn nhãn 1.

Kahn theo thứ tự đỉnh ban đầu 0..5 và thứ tự cạnh trong bảng cho:

~~~text
indegree = [0,2,1,2,2,2]
topo = [0,2,1,3,4,5]
~~~

Khoảng cách ban đầu: chỉ d[0]=0 reachable; các đỉnh khác chưa có đường tới.

### Từng bước relax

**Xử lý 0:**
- 0→1 (4): `d[1]=4`, parent[1]=0.
- 0→2 (2): `d[2]=2`, parent[2]=0.

**Xử lý 2:**
- 2→1 (−5): candidate = 2−5=**−3**, cải thiện d[1] từ 4 xuống −3; parent[1]=2.
- 2→3 (10): d[3]=12; parent[3]=2.
- 2→5 (12): d[5]=14; parent[5]=2.

**Xử lý 1:** d[1] đã được chốt ở −3.
- 1→3 (3): candidate = −3+3=0, cải thiện d[3] từ 12 xuống **0**; parent[3]=1.
- 1→4 (6): d[4]=3; parent[4]=1.

**Xử lý 3:**
- 3→4 (1): candidate = 0+1=**1**, cải thiện d[4] từ 3 xuống 1; parent[4]=3.

**Xử lý 4:**
- 4→5 (−2): candidate = 1−2=**−1**, cải thiện d[5] từ 14 xuống −1; parent[5]=4.

**Xử lý 5:** không có cạnh đi ra.

Kết quả:

| Đỉnh v | dist[v] | parent[v] | Một đường ngắn nhất từ 0 |
| ---: | ---: | ---: | --- |
| 0 | 0 | −1 | 0 |
| 1 | −3 | 2 | 0→2→1 |
| 2 | 2 | 0 | 0→2 |
| 3 | 0 | 1 | 0→2→1→3 |
| 4 | 1 | 3 | 0→2→1→3→4 |
| 5 | −1 | 4 | 0→2→1→3→4→5 |

Đường tới 5 có tổng:

\[
2+(-5)+3+1+(-2)=\boxed{-1}.
\]

Không có chu trình âm nào; khoảng cách âm xuất hiện do **cạnh âm** trên đường từ nguồn.

### Một điều không thể làm

Nếu duyệt đỉnh theo nhãn `0,1,2,3,4,5`, ta có thể xử lý 1 **trước khi** cạnh 2→1 hạ d[1] xuống −3. Những cạnh đi ra từ 1 khi ấy đã được thư giãn bằng giá trị **cũ**, và thuật toán một lượt có thể trả sai. Thứ tự topo `0,2,1,3,4,5` là điều kiện quyết định.

## 6. Đỉnh không tới được và nhiều nghiệm hòa

### Không tới được khác khoảng cách bằng 0

Xét bốn đỉnh:

~~~text
0 --(3)--> 1       2 --(-4)--> 3
s=0
~~~

Đồ thị có hai phần tách biệt. Kết quả từ 0:

~~~text
reachable = [true,true,false,false]
dist hiển thị = [0,3,INF,INF]
path tới 3 = none
~~~

Cạnh âm 2→3 không làm khoảng cách từ 0 tới 3 bằng −4; vì **không có đường từ 0 tới 2**, không được bắt đầu thư giãn từ 2. Khi tới u không reachable trong thứ tự topo, thuật toán **bỏ qua mọi cạnh đi ra của u**.

Nếu dùng `Long.MAX_VALUE` làm INF và cộng trọng số âm vào INF, có thể tạo một “khoảng cách” rất lớn nhưng hữu hạn cho đỉnh không thể đến. Nếu cộng dương còn có nguy cơ tràn. Cách dùng `boolean[] reachable` riêng tránh cả hai sự nhầm lẫn đó.

### Nhiều đường cùng có giá trị nhỏ nhất

Với các cạnh:

~~~text
0→1 (1), 0→2 (1), 1→3 (1), 2→3 (1)
~~~

Có hai đường ngắn nhất tới 3, đều có trọng số 2:
- 0→1→3.
- 0→2→3.

Nếu topo và thứ tự cạnh khiến 1 được xét trước 2 và code chỉ cập nhật khi `candidate<dist[v]`, parent[3] giữ bằng 1, đường trả về là `0→1→3`. Kết quả **2** luôn đúng dù cách xử lý hòa khác.

Nếu đề yêu cầu **đường có thứ tự từ điển nhỏ nhất**, **ít cạnh nhất khi bằng trọng số**, hoặc **đếm số đường ngắn nhất**, cần thiết kế thêm trạng thái và quy tắc phá hòa; không thể suy ra những yêu cầu này chỉ từ mảng dist.

## 7. Đường đi ngắn nhất khác thuật toán BFS, Dijkstra, Bellman–Ford ở đâu?

| Phương pháp | Lớp đồ thị/trọng số | Thời gian thường gặp | Ghi chú |
| --- | --- | --- | --- |
| **BFS** | Cạnh có chi phí bằng nhau, thường quy ước 1 | O(V+E) | Ít **số cạnh**, không tối thiểu tổng trọng số tùy ý |
| **Dijkstra** | Trọng số cạnh **không âm** | O((V+E) log V) với heap thường dùng | Không bảo đảm đúng khi có cạnh âm |
| **Bellman–Ford** | Đồ thị tổng quát, cạnh có thể âm | O(VE) | Có thể phát hiện chu trình âm khả đạt từ nguồn |
| **DAG shortest paths** | Đồ thị có hướng **không chu trình**, cạnh có thể âm | **O(V+E)** | Topo trước, mỗi cạnh relax một lần |

Độ phức tạp nêu trên giả định phép cộng/so sánh trọng số có chi phí O(1) và danh sách kề. Trường hợp đồ thị không có cạnh, O(V+E) tương đương O(V).

### Phản ví dụ cho Dijkstra với cạnh âm

Xét một DAG khác:

~~~text
0→1 (2)
0→2 (5)
2→1 (-10)
1→3 (1)
~~~

Từ nguồn 0, đường tốt nhất tới 1 là 0→2→1 có giá trị **−5**; tới 3 là 0→2→1→3 có giá trị **−4**.

Một cách triển khai Dijkstra chuẩn **chốt đỉnh 1 khi tạm thấy khoảng cách 2** trước khi xử lý 2 (khoảng cách 5). Nó có thể xử lý cạnh 1→3 với giá 2+1=3 rồi không xét lại cạnh ấy khi 2→1 về sau cải thiện d[1] thành −5. Kết quả d[3]=3 khi ấy **sai**; đáp án là −4.

Vì là DAG, topo bắt buộc đặt 2 trước 1: `[0,2,1,3]`. Relax theo topo tính đúng dù có cạnh −10.

**Không phải cứ có cạnh âm là phải dùng Bellman–Ford.** Trước hết kiểm tra tính DAG. Nếu là DAG, phương pháp topo thường nhanh hơn và đơn giản hơn. Nếu có chu trình, không được dùng công thức một lượt DAG; hãy chọn thuật toán tổng quát phù hợp với trọng số và mục tiêu, xét thêm nguy cơ chu trình âm.

### Khi nào BFS vẫn đúng?

Nếu mọi cạnh cùng trọng số 1, số bước ít nhất cũng là tổng trọng số ít nhất; BFS giải đúng. Nhưng nếu cạnh có giá 2, 5, −10 hoặc các giá khác nhau, BFS chỉ tối thiểu số cạnh, không đáp ứng tổng trọng số.

### Chu trình âm là vấn đề khác

Trong đồ thị tổng quát, nếu tồn tại chu trình âm **khả đạt từ nguồn** và từ đó đi tới đích, có thể lặp vòng để làm chi phí đi tới đích giảm không giới hạn; khi ấy không có một khoảng cách nhỏ nhất hữu hạn cho đích đó. DAG không chứa bất kỳ chu trình nào, nên **không thể có tình huống này**.

## 8. Vì sao thuật toán topo–relax đúng? Chứng minh

**Bất biến trước khi xử lý u trong topo:** với mọi đỉnh x đứng trước u trong topo, nếu x có thể tới từ s thì `dist[x]` là khoảng cách ngắn nhất thực sự từ s tới x; nếu không thì `reachable[x]=false`. Các cạnh đi ra từ những đỉnh đã xử lý đã được xét đúng một lần.

### Cơ sở

Đỉnh s có đường rỗng trọng số 0. Trong DAG, không thể có một đường từ s quay về s với ít nhất một cạnh, vì như vậy có chu trình. Do đó `d[s]=0`.

Nếu một đỉnh đứng trước s trong topo, nó **không thể đạt được từ s**: mọi cạnh trên bất kỳ đường từ s tới nó đều phải tiến **theo chiều tăng của vị trí topo**. Vì vậy mọi đỉnh tiền nhiệm của s trong topo được đánh dấu không reachable từ s.

### Bước quy nạp

Xét đỉnh v trong topo. Mọi cạnh đi vào v có dạng u→v với **u đứng trước v**. Theo giả thiết quy nạp, khoảng cách tại u (nếu reachable) đã tối ưu khi nó được xử lý.

Mọi đường từ s tới v với ít nhất một cạnh đều kết thúc bằng **một cạnh u→v**. Giá trị tối ưu của đường ấy là:

\[
d[v]=\min_{(u,v)\in E,\ u\text{ reachable}}
(d[u]+w(u,v)).
\]

Thuật toán đã xét **mọi cạnh đi vào v** khi xử lý từng u trước v. Nó đã so sánh mọi ứng viên bằng phép relax, nên khi đến lượt v, `dist[v]` chính là giá trị min này. Nếu không có u reachable đi vào, không có đường từ s tới v và reachable[v] vẫn false.

Các cạnh v→x chỉ đi tới đỉnh x **sau v**, vì vậy khi xử lý v, có thể thư giãn cạnh đi ra một lần mà không cần quay lại v.

### Kết luận

Theo quy nạp trên thứ tự topo, tất cả khoảng cách được tính đúng. **Trọng số âm không làm hỏng chứng minh:** điều mấu chốt là các cạnh luôn đi từ đỉnh trước tới đỉnh sau topo, không phải trọng số cạnh không âm.

Nếu thay topo bằng thứ tự nhãn đỉnh hoặc bất kỳ thứ tự nào không tôn trọng tất cả cạnh, giả thiết “mọi tiền nhiệm đã được xử lý” không còn đúng.

## 9. Phân tích thời gian, bộ nhớ và khả năng mở rộng

Đặt n=|V| và m=|E|.

- **Tạo danh sách kề:** O(n+m) thời gian/bộ nhớ nếu đầu vào là m cạnh.
- **Kahn:** tính indegree O(n+m), hàng đợi và giảm indegree O(n+m).
- **Relax theo topo:** mỗi đỉnh duyệt một lần, mỗi cạnh kiểm tra ứng viên một lần: O(n+m).
- **Khôi phục một đường:** lần theo parent tối đa n đỉnh trong DAG, O(n) thời gian cho một truy vấn đường.
- **Tổng:** \(\boxed{O(n+m)}\) cho toàn bộ khoảng cách từ **một nguồn**.

Bộ nhớ lưu đồ thị O(n+m); các mảng topo/indegree/queue/reachable/dist/parent O(n), nên bộ nhớ **phụ O(n)** ngoài biểu diễn đồ thị. Với Java, các đối tượng danh sách và `Edge` có overhead, nhưng không đổi Big-O.

**Nhiều nguồn truy vấn:** topo của cùng DAG có thể được tính một lần và tái sử dụng. Tuy nhiên bảng `dist`, `reachable` và `parent` cần khởi tạo lại cho mỗi nguồn; không được dùng dist cũ của nguồn khác. Nếu có S nguồn và đều cần toàn bộ khoảng cách, chi phí thường O(n+m+S(n+m)) khi tận dụng topo đã có.

**Tràn số:** `Math.addExact(dist[u],weight)` ném `ArithmeticException` nếu một phép cộng ứng viên vượt miền long. Điều này giúp **không âm thầm tạo số sai**, nhưng cũng có nghĩa chương trình có thể báo lỗi dù một đường tối ưu khác vẫn nằm trong miền long. Cần bảo đảm **mọi ứng viên được đánh giá** có thể biểu diễn chính xác, hoặc chuyển cả thuật toán sang `BigInteger`. Khi dùng BigInteger, số phép relax vẫn O(n+m), nhưng thời gian mỗi phép số học còn phụ thuộc độ dài số.

## 10. Java 17: chương trình độc lập, có kiểm tra DAG

Chương trình bên dưới:
1. Tạo danh sách kề của đồ thị có hướng, cho phép trọng số âm và cạnh song song.
2. Dùng Kahn để lấy topo; nếu phát hiện chu trình **ở bất kỳ thành phần nào**, ném `IllegalArgumentException` trước khi tính khoảng cách.
3. Dùng `boolean[] reachable` riêng, không lấy `Long.MAX_VALUE` làm INF để cộng một cách nguy hiểm.
4. Relax mỗi cạnh đúng một lần theo topo, dùng `Math.addExact` cho trọng số và parent để khôi phục đường.
5. Minh họa một DAG có cạnh âm, các đỉnh không tới được, ví dụ Dijkstra không áp dụng được, trường hợp hòa, chu trình và self-loop.
6. Đối chiếu bằng oracle độc lập trên **66.067 đồ thị có hướng nhỏ**, với **2.254 lượt nguồn** nằm trong các DAG.

Các mảng bên trong record kết quả được xem là **chỉ đọc theo hợp đồng ví dụ**; record trong Java không tự sao chép sâu mảng. Nếu đưa API vào thư viện công khai và muốn ngăn người gọi sửa kết quả, hãy trả bản sao phòng vệ hoặc dùng kiểu dữ liệu bất biến.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.StringJoiner;

public class DagShortestPathsDemo {
    record Arc(int to, long weight) {}

    record Answer(
            int source, List<Integer> topo,
            boolean[] reachable, long[] dist, int[] parent) {}

    record Oracle(boolean[] reachable, long[] dist) {}
    record Counts(int graphs, int sources) {}

    static List<List<Arc>> graph(int n, long[][] edges) {
        if (n < 0 || edges == null) {
            throw new IllegalArgumentException("Invalid graph");
        }

        List<List<Arc>> g = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            g.add(new ArrayList<>());
        }

        for (long[] edge : edges) {
            if (edge == null || edge.length != 3
                    || edge[0] < 0 || edge[0] >= n
                    || edge[1] < 0 || edge[1] >= n) {
                throw new IllegalArgumentException("Invalid edge");
            }
            int from = (int) edge[0];
            int to = (int) edge[1];
            g.get(from).add(new Arc(to, edge[2]));
        }
        return g;
    }

    // Kahn: kiem tra DAG tren TOAN BO do thi.
    static List<Integer> topoOrder(List<List<Arc>> g) {
        int n = g.size();
        int[] indegree = new int[n];

        for (int u = 0; u < n; u++) {
            for (Arc e : g.get(u)) {
                indegree[e.to()]++;
            }
        }

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        for (int u = 0; u < n; u++) {
            if (indegree[u] == 0) {
                queue.addLast(u);
            }
        }

        List<Integer> order = new ArrayList<>();
        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            order.add(u);
            for (Arc e : g.get(u)) {
                int v = e.to();
                indegree[v]--;
                if (indegree[v] == 0) {
                    queue.addLast(v);
                }
            }
        }

        if (order.size() != n) {
            throw new IllegalArgumentException("Graph is not a DAG");
        }
        return List.copyOf(order);
    }

    // O(V+E) thoi gian, O(V) bo nho phu.
    static Answer shortestPaths(
            List<List<Arc>> g, int source) {
        if (source < 0 || source >= g.size()) {
            throw new IllegalArgumentException("Invalid source");
        }

        // Tu choi chu trinh o bat ky thanh phan nao.
        List<Integer> topo = topoOrder(g);
        int n = g.size();
        boolean[] reached = new boolean[n];
        long[] dist = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        reached[source] = true;
        dist[source] = 0;

        for (int u : topo) {
            if (!reached[u]) continue;

            for (Arc e : g.get(u)) {
                int v = e.to();
                long candidate =
                        Math.addExact(dist[u], e.weight());

                if (!reached[v] || candidate < dist[v]) {
                    reached[v] = true;
                    dist[v] = candidate;
                    parent[v] = u;
                }
            }
        }
        return new Answer(source, topo, reached, dist, parent);
    }

    static List<Integer> pathTo(Answer a, int target) {
        if (target < 0 || target >= a.dist().length) {
            throw new IllegalArgumentException("Invalid target");
        }
        if (!a.reachable()[target]) return List.of();

        List<Integer> reversed = new ArrayList<>();
        int n = a.parent().length;
        for (int v = target; v != -1; v = a.parent()[v]) {
            reversed.add(v);
            if (reversed.size() > n) {
                throw new IllegalStateException("Broken parent");
            }
        }

        Collections.reverse(reversed);
        if (reversed.get(0) != a.source()) {
            throw new IllegalStateException("Wrong source");
        }
        return List.copyOf(reversed);
    }

    static String showPath(List<Integer> path) {
        if (path.isEmpty()) return "none";
        StringJoiner out = new StringJoiner("->");
        for (int v : path) {
            out.add(Integer.toString(v));
        }
        return out.toString();
    }

    static String showDistances(Answer a) {
        StringJoiner out = new StringJoiner(", ", "[", "]");
        for (int v = 0; v < a.dist().length; v++) {
            out.add(a.reachable()[v]
                    ? Long.toString(a.dist()[v]) : "INF");
        }
        return out.toString();
    }

    // Oracle khac: kiem tra chu trinh bang bao dong kha dat.
    // Khong khoi tao reach[i][i] = true.
    static boolean oracleCycle(List<List<Arc>> g) {
        int n = g.size();
        boolean[][] reach = new boolean[n][n];

        for (int u = 0; u < n; u++) {
            for (Arc e : g.get(u)) {
                reach[u][e.to()] = true;
            }
        }
        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) {
                    if (reach[i][k] && reach[k][j]) {
                        reach[i][j] = true;
                    }
                }
            }
        }
        for (int u = 0; u < n; u++) {
            if (reach[u][u]) return true;
        }
        return false;
    }

    // Oracle duong di: Bellman-Ford doc lap tren DAG nho.
    static Oracle oracleBellman(
            List<List<Arc>> g, int source) {
        int n = g.size();
        boolean[] reached = new boolean[n];
        long[] dist = new long[n];
        reached[source] = true;

        for (int pass = 1; pass < n; pass++) {
            boolean changed = false;
            for (int u = 0; u < n; u++) {
                if (!reached[u]) continue;

                for (Arc e : g.get(u)) {
                    int v = e.to();
                    long candidate =
                            Math.addExact(dist[u], e.weight());
                    if (!reached[v] || candidate < dist[v]) {
                        reached[v] = true;
                        dist[v] = candidate;
                        changed = true;
                    }
                }
            }
            if (!changed) break;
        }
        return new Oracle(reached, dist);
    }

    static boolean validTopo(
            List<List<Arc>> g, List<Integer> topo) {
        int n = g.size();
        if (topo.size() != n) return false;

        int[] pos = new int[n];
        Arrays.fill(pos, -1);
        for (int i = 0; i < n; i++) {
            int v = topo.get(i);
            if (v < 0 || v >= n || pos[v] != -1) return false;
            pos[v] = i;
        }

        for (int u = 0; u < n; u++) {
            for (Arc e : g.get(u)) {
                if (pos[u] >= pos[e.to()]) return false;
            }
        }
        return true;
    }

    // Kiem tra duong cha phai co tung canh cung huong,
    // va tong tron tung buoc bang dist cua dinh con.
    static boolean validPath(
            List<List<Arc>> g, Answer a, int target) {
        List<Integer> path = pathTo(a, target);
        if (!a.reachable()[target]) return path.isEmpty();

        if (path.isEmpty() || path.get(0) != a.source()
                || path.get(path.size() - 1) != target) {
            return false;
        }

        boolean[] seen = new boolean[g.size()];
        for (int i = 0; i < path.size(); i++) {
            int v = path.get(i);
            if (seen[v]) return false;
            seen[v] = true;

            if (i > 0) {
                int u = path.get(i - 1);
                if (a.parent()[v] != u) return false;

                boolean edgeMatches = false;
                for (Arc e : g.get(u)) {
                    if (e.to() == v
                            && Math.addExact(
                                    a.dist()[u], e.weight())
                               == a.dist()[v]) {
                        edgeMatches = true;
                        break;
                    }
                }
                if (!edgeMatches) return false;
            }
        }
        return true;
    }

    // Moi do thi don co huong n=0..4, co self-loop.
    // Trong DAG: thu moi nguon va doi chieu Bellman-Ford.
    static Counts verifySmallGraphs() {
        int checkedGraphs = 0;
        int checkedSources = 0;

        for (int n = 0; n <= 4; n++) {
            int total = 1 << (n * n);

            for (int mask = 0; mask < total; mask++) {
                List<List<Arc>> g = new ArrayList<>();
                for (int u = 0; u < n; u++) {
                    g.add(new ArrayList<>());
                }
                for (int u = 0; u < n; u++) {
                    for (int v = 0; v < n; v++) {
                        if ((mask & (1 << (u * n + v))) != 0) {
                            long weight =
                                    (u * 7 + v * 3) % 7 - 3;
                            g.get(u).add(new Arc(v, weight));
                        }
                    }
                }

                boolean cycle = oracleCycle(g);
                List<Integer> topo = null;
                boolean rejected = false;
                try {
                    topo = topoOrder(g);
                } catch (IllegalArgumentException e) {
                    rejected = true;
                }

                if (rejected != cycle
                        || (!cycle && !validTopo(g, topo))) {
                    throw new AssertionError(
                            "Cycle mismatch n=" + n
                            + " mask=" + mask);
                }

                if (!cycle) {
                    for (int source = 0; source < n; source++) {
                        Answer actual = shortestPaths(g, source);
                        Oracle oracle = oracleBellman(g, source);

                        for (int v = 0; v < n; v++) {
                            if (actual.reachable()[v]
                                    != oracle.reachable()[v]
                                    || (actual.reachable()[v]
                                        && actual.dist()[v]
                                           != oracle.dist()[v])
                                    || !validPath(g, actual, v)) {
                                throw new AssertionError(
                                        "Distance mismatch n=" + n
                                        + " mask=" + mask
                                        + " source=" + source
                                        + " target=" + v);
                            }
                        }
                        checkedSources++;
                    }
                }
                checkedGraphs++;
            }
        }
        return new Counts(checkedGraphs, checkedSources);
    }

    public static void main(String[] args) {
        List<List<Arc>> main = graph(6, new long[][]{
            {0,1,4}, {0,2,2}, {2,1,-5},
            {1,3,3}, {2,3,10}, {1,4,6},
            {3,4,1}, {2,5,12}, {4,5,-2}
        });
        Answer a = shortestPaths(main, 0);
        System.out.println("mainTopo=" + a.topo());
        System.out.println("mainDist=" + showDistances(a));
        System.out.println("mainPath5="
                + showPath(pathTo(a, 5)));
        System.out.println("mainPath0="
                + showPath(pathTo(a, 0)));

        List<List<Arc>> disconnected = graph(4,
                new long[][]{{0,1,3}, {2,3,-4}});
        Answer b = shortestPaths(disconnected, 0);
        System.out.println("unreachableDist="
                + showDistances(b));
        System.out.println("unreachablePath3="
                + showPath(pathTo(b, 3)));

        List<List<Arc>> negative = graph(4,
                new long[][]{
                    {0,1,2}, {0,2,5}, {2,1,-10}, {1,3,1}
                });
        Answer c = shortestPaths(negative, 0);
        System.out.println("negativeTopo=" + c.topo());
        System.out.println("negativeDist=" + showDistances(c));
        System.out.println("negativePath3="
                + showPath(pathTo(c, 3)));

        List<List<Arc>> tie = graph(4,
                new long[][]{
                    {0,1,1}, {0,2,1}, {1,3,1}, {2,3,1}
                });
        Answer d = shortestPaths(tie, 0);
        System.out.println("tiePath3="
                + showPath(pathTo(d, 3)));

        try {
            shortestPaths(graph(3,
                    new long[][]{{0,1,1},{1,2,1},{2,0,1}}), 0);
            throw new AssertionError("Cycle not rejected");
        } catch (IllegalArgumentException e) {
            System.out.println("cycleRejected=" + e.getMessage());
        }

        try {
            shortestPaths(graph(1,
                    new long[][]{{0,0,-5}}), 0);
            throw new AssertionError("Self-loop not rejected");
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "selfLoopRejected=" + e.getMessage());
        }

        System.out.println("emptyTopo="
                + topoOrder(graph(0, new long[0][0])));

        Counts checks = verifySmallGraphs();
        System.out.println("verifiedGraphs=" + checks.graphs());
        System.out.println("verifiedSources=" + checks.sources());
    }
}
~~~

Lưu thành tệp **DagShortestPathsDemo.java** và chạy bằng **JDK 17 trở lên**:

~~~bash
javac DagShortestPathsDemo.java
java DagShortestPathsDemo
~~~

**Đầu ra chính xác:**

~~~text
mainTopo=[0, 2, 1, 3, 4, 5]
mainDist=[0, -3, 2, 0, 1, -1]
mainPath5=0->2->1->3->4->5
mainPath0=0
unreachableDist=[0, 3, INF, INF]
unreachablePath3=none
negativeTopo=[0, 2, 1, 3]
negativeDist=[0, -5, 5, -4]
negativePath3=0->2->1->3
tiePath3=0->1->3
cycleRejected=Graph is not a DAG
selfLoopRejected=Graph is not a DAG
emptyTopo=[]
verifiedGraphs=66067
verifiedSources=2254
~~~

### Giải thích chính sách kết quả

**Kết quả cho đỉnh không tới được:** `reachable[v]==false`. Mảng dist vẫn có ô chứa long mặc định 0, nhưng **chỉ showDistances** quyết định in `INF`; không được dùng dist[v] để tính hay so sánh ở trạng thái unreachable.

**Khôi phục đường:** bắt đầu ở t rồi lần `parent[t]`, `parent[parent[t]]` cho tới −1. Đảo danh sách để có đường từ s tới t. Vì DAG không có chu trình và parent chỉ được đặt bởi các cạnh đi từ trước tới sau topo, chuỗi parent sẽ kết thúc. Mã còn có kiểm tra độ dài để phát hiện một chuỗi parent hỏng nếu dữ liệu bị sửa bên ngoài.

**Phá hòa:** so sánh candidate **nhỏ hơn** chứ không nhỏ hơn hoặc bằng. Khi hai đường có tổng trọng số bằng nhau, đường được tìm thấy trước theo topo/thứ tự cạnh vẫn là kết quả.

**Kiểm tra DAG trước relax:** `shortestPaths` gọi `topoOrder` và từ chối chu trình **ngay cả ở thành phần không tới được từ nguồn**. Điều đó phù hợp với đầu vào cam kết là **DAG toàn cục**.

**Lỗi số học:** `Math.addExact` có thể ném `ArithmeticException`. Đây là hành vi chủ động phát hiện đầu vào ngoài miền số nguyên của lời giải, không được âm thầm sửa giá trị thành MAX hoặc cho tràn tự nhiên.

## 11. Giải thích oracle kiểm thử 66.067 đồ thị

Bộ kiểm thử tạo **mọi đồ thị đơn có hướng** với n từ 0 đến 4. Với n đỉnh, mỗi cặp có thứ tự `(u,v)` gồm cả trường hợp u=v có thể có hoặc không có cạnh; vậy số đồ thị là `2^(n²)`.

| Số đỉnh | Số đồ thị |
| ---: | ---: |
| n=0 | 1 |
| n=1 | 2 |
| n=2 | 16 |
| n=3 | 512 |
| n=4 | 65.536 |
| **Tổng** | **66.067** |

Trọng số cho cạnh có mặt được gán **xác định** bởi:

\[
w(u,v)=((7u+3v)\bmod 7)-3,
\]

cho những giá trị nguyên nhỏ có thể âm. Việc kiểm thử chỉ chọn mỗi cặp `u→v` tối đa một lần; **cạnh song song** đã được giải thích về mặt thuật toán nhưng không thuộc miền vét cạn này.

### Kiểm thử thứ nhất: một đồ thị có chu trình không?

Đây là phép đối chiếu **độc lập với Kahn**. Dùng ma trận boolean `reach[u][v]`, ban đầu chỉ đánh dấu những cạnh thực tế tồn tại (không mặc định `reach[u][u]=true`). Sau đó dùng bao đóng đường đi kiểu Warshall để tìm các đường độ dài dương.

Nếu tồn tại u với `reach[u][u]=true`, đồ thị có một đường có hướng từ u về chính nó với ít nhất một cạnh: **có chu trình**. Kahn phải **từ chối** đúng những đồ thị ấy; với DAG, topo trả về phải chứa đủ đỉnh và mọi cạnh đều đi từ trước tới sau.

### Kiểm thử thứ hai: khoảng cách có ngắn nhất thật không?

Với mỗi DAG và mỗi nguồn s hợp lệ, tính giá trị chuẩn bằng **Bellman–Ford**, thư giãn tất cả cạnh trong nhiều lượt (tối đa n−1 lượt là đủ cho đường đi đơn tối đa n−1 cạnh). Sau đó đối chiếu:
- Cờ reachable của từng đỉnh.
- Khoảng cách số học của mọi đỉnh reachable.
- Đường parent được trả có nguồn/đích phù hợp, không lặp đỉnh, đi qua các cạnh có hướng thực sự tồn tại và độ dài tích lũy khớp dist.

Trong toàn bộ **66.067** đồ thị, có **573 DAG** tính cả đồ thị n=0; khi thử mọi nguồn s trong từng DAG có **2.254 lượt nguồn**. Các con số này có thể được đối chiếu bằng một chương trình độc lập khác; bài Java in `verifiedGraphs=66067` và `verifiedSources=2254`.

Đây là kiểm thử rất hữu ích để bắt lỗi thứ tự topo, skip unreachable, relax cạnh âm, trường hợp self-loop và khôi phục parent. Nó **không thay thế** chứng minh quy nạp trên topo; bài toán lớn vẫn dựa vào chứng minh và hợp đồng input.

### Vì sao không dùng oracle cho đồ thị lớn?

Warshall tốn O(n³) thời gian và O(n²) bộ nhớ; Bellman–Ford O(VE) trong trường hợp tổng quát. Chúng được dùng trên những đồ thị rất nhỏ như một **bộ đối chiếu độc lập**, không phải để thay thuật toán DAG O(V+E) trong sản phẩm.

## 12. Các trường hợp biên cần xử lý

| Trường hợp | Cách hiểu đúng |
| --- | --- |
| n=0 | Là DAG rỗng, có topo rỗng; **không có nguồn s hợp lệ** |
| n=1, không cạnh | d[s]=0; pathTo(s)=[s] |
| n=1, self-loop | Không phải DAG, phải từ chối |
| Chỉ có cạnh âm trên một DAG | Hợp lệ, có thể có d[v] âm |
| Cạnh âm từ thành phần không tới được | Không làm đỉnh ấy trở nên reachable |
| Có chu trình ở thành phần không tới được | Theo hợp đồng DAG toàn cục, **từ chối** |
| Có hai cạnh song song cùng chiều, trọng số khác | Relax cả hai; chọn ứng viên nhỏ hơn |
| Có hai đường cùng giá | Khoảng cách bằng nhau; parent phụ thuộc quy tắc hòa |
| Có đường chi phí 0 tới v≠s | reachable[v]=true và dist[v]=0, không phải INF |
| Đường với tổng đúng Long.MAX_VALUE | Vẫn có thể là khoảng cách hợp lệ khi có reachable riêng |
| Một phép cộng ứng viên vượt miền long | Math.addExact ném lỗi; cần kiểu số đủ lớn |
| Nhiều đỉnh độc lập, không cạnh | Chỉ nguồn reachable; các đỉnh khác INF |
| Nhãn đỉnh không theo thứ tự topo | Phải dùng topo thật, không duyệt 0..n−1 tùy tiện |
| Bài yêu cầu đường ngắn nhất đến một đích | Có thể tính toàn bộ rồi truy vết, O(V+E) |
| Bài yêu cầu mọi đường ngắn nhất | Cần thêm logic lưu các parent đồng tối ưu/đếm đường |

### Cạnh song song và self-loop

Cạnh song song `u→v` có thể mang trọng số khác nhau. Chúng đều xuất hiện trong adjacency, đều tăng indegree của v và được relax như những cạnh độc lập. Self-loop `u→u` không được phép vì tạo chu trình. Không được xóa self-loop chỉ để ép đồ thị hợp thức mà không có chỉ thị từ bài toán.

### Giá trị INF và tổng rất lớn

Đối với lời giải đúng tổng quát, cần phân biệt **không có đường** với **có đường nhưng tổng rất lớn**. Dùng `Long.MAX_VALUE` làm sentinal rồi so sánh hoặc cộng vô điều kiện có thể sai khi khoảng cách thật đúng bằng MAX, hoặc khi INF cộng trọng số âm. Bộ đôi `reachable[]` và `dist[]` trong Java tránh lỗi về trạng thái, còn `Math.addExact` xử lý kiểm soát tràn số.

## 13. Lỗi phổ biến và cách sửa

1. **Không xác minh đồ thị là DAG**, rồi relax một lần theo một thứ tự tùy ý: trả sai khi có vòng.
2. **Duyệt nhãn 0..n−1 thay topo**: cạnh 2→1 có thể yêu cầu xử lý đỉnh 2 trước 1.
3. **Áp Dijkstra cho cạnh âm** chỉ vì muốn chạy nhanh: không có bảo đảm tối ưu tổng trọng số.
4. **Dùng BFS khi trọng số khác nhau**: BFS tối ưu số cạnh chứ không phải tổng giá.
5. **Dùng Long.MAX_VALUE làm INF rồi cộng trực tiếp**: sai với cạnh âm hoặc tràn.
6. **Coi dist mặc định 0 của đỉnh unreachable là khoảng cách hợp lệ**: tạo phương án đường đi không tồn tại.
7. **Không kiểm tra reachable[u] trước khi relax**: mở rộng sai từ một đỉnh không có đường từ nguồn.
8. **Không lưu parent khi cải thiện dist**: không thể tái dựng đúng đường đi.
9. **Cập nhật parent khi hòa mà không có chính sách rõ ràng**: đường trả về thiếu tính xác định, dù giá trị vẫn đúng.
10. **Nhầm chiều cạnh**: u→v không tương đương v→u.
11. **Đếm cạnh song song theo một cách nhưng trừ indegree theo cách khác**: topo Kahn có thể kẹt sai.
12. **Không duyệt mọi đỉnh trong Kahn**: bỏ sót chu trình ở thành phần khác.
13. **Chỉ kiểm tra chu trình ở phần reachable dù API yêu cầu DAG toàn cục**: vi phạm hợp đồng dữ liệu.
14. **Không xử lý self-loop**: thực tế đồ thị đã có chu trình.
15. **Xem chu trình có trọng số dương là DAG**: DAG cấm **mọi** chu trình, không phân biệt dấu.
16. **Nhầm đường đơn với đường có thể lặp đỉnh**: trong DAG, lặp đỉnh tất yếu tạo chu trình, nên đường có hướng hợp lệ không lặp.
17. **Giả định chỉ có một thứ tự topo**: có thể có nhiều, nhưng đều cho đúng khoảng cách.
18. **Nói O(V) cho cả đồ thị mà quên E**: mỗi cạnh cần xử lý, thời gian là O(V+E).
19. **Không xét độ sâu stack** nếu dùng DFS topo đệ quy thay Kahn: có thể quá giới hạn stack Java.
20. **Cho rằng phát hiện chu trình âm là một phần của thuật toán DAG**: DAG không có chu trình nào; dữ liệu có vòng phải dùng thuật toán tổng quát thích hợp.

## 14. Bài tập tự luyện có hướng dẫn

**Bài 1 — tính topo.** Với các cạnh `0→1, 0→2, 2→1`, thứ tự `[0,1,2]` có hợp lệ không? Hãy cho một thứ tự hợp lệ.

*Đáp án:* Không, vì cạnh 2→1 đòi 2 trước 1. Thứ tự hợp lệ là `[0,2,1]`.

**Bài 2 — cạnh âm.** DAG có `0→1 (4), 0→2 (2), 2→1 (−5)`. Khoảng cách ngắn nhất từ 0 tới 1?

*Đáp án:* `min(4,2−5)=−3`, đi theo `0→2→1`.

**Bài 3 — chu trình.** Cạnh `0→1 (1),1→2 (1),2→0 (10)` có tổng chu trình dương. Có dùng DAG shortest paths không?

*Đáp án:* Không. DAG cấm mọi chu trình có hướng, bất kể tổng trọng số dương, âm hay 0.

**Bài 4 — đỉnh unreachable.** Với `0→1 (3)` và `2→3 (−4)`, nguồn 0. Giá trị ở đỉnh 3?

*Đáp án:* INF/unreachable. Cạnh 2→3 không giúp vì không có đường từ 0 đến 2.

**Bài 5 — hai đường hòa.** Có `0→1 (1), 0→2 (1),1→3 (1),2→3 (1)`. Khoảng cách d[3] và parent[3] là gì nếu 1 được xử lý trước 2, chỉ cập nhật khi candidate nhỏ hơn?

*Đáp án:* d[3]=2; parent[3]=1, đường `0→1→3`. Đường `0→2→3` cũng tối ưu.

**Bài 6 — vì sao cần topo?** Nếu xử lý u trước khi một cạnh có hướng v→u được relax, điều gì có thể sai?

*Đáp án:* Khoảng cách tại u có thể chưa tối ưu khi các cạnh u→x đã được xử lý. Sau đó u được cải thiện nhưng x không nhận cập nhật nữa, dẫn tới sai giá trị.

**Bài 7 — Dijkstra.** Với `0→1 (2),0→2 (5),2→1 (−10),1→3 (1)`, giá trị d[3] thực sự là gì?

*Đáp án:* −4, qua `0→2→1→3`. Dijkstra không có bảo đảm vì có cạnh âm.

**Bài 8 — giá trị nguồn.** Khoảng cách ngắn nhất từ s tới chính s trong DAG là gì?

*Đáp án:* 0, đường rỗng số cạnh. Vì DAG không có vòng, không có đường đi khác từ s về s bằng ít nhất một cạnh.

**Bài 9 — Kahn và nhiều thành phần.** Nếu phần reachable từ nguồn là DAG nhưng thành phần còn lại có chu trình, chương trình trong bài xử lý ra sao?

*Đáp án:* `topoOrder` kiểm tra toàn bộ đồ thị, thấy không lấy đủ n đỉnh và ném lỗi “Graph is not a DAG”. Không âm thầm chấp nhận.

**Bài 10 — độ phức tạp.** Vì sao tổng thời gian không phải O(VE) như Bellman–Ford?

*Đáp án:* Topo cho thứ tự bảo đảm mọi tiền nhiệm của đỉnh được xử lý trước, nên mỗi cạnh chỉ relax **một lần**, tổng O(V+E).

**Bài 11 — khôi phục đường.** Với parent[5]=4, parent[4]=3, parent[3]=1, parent[1]=2, parent[2]=0, parent[0]=−1, đường từ 0 tới 5?

*Đáp án:* Lần parent từ 5 nhận `[5,4,3,1,2,0]`; đảo thành `[0,2,1,3,4,5]`.

**Bài 12 — kiểm tra INF.** Một đỉnh v có đường đi trọng số đúng 0 từ s. Có được xem nó là unreachable do `dist[v]==0`?

*Đáp án:* Không. Phải dùng `reachable[v]` để phân biệt; zero có thể là một khoảng cách thật.

**Bài 13 — số lớn.** Nếu một candidate cộng long bị tràn, có thể âm thầm cho Java tràn và tiếp tục so sánh không?

*Đáp án:* Không. Kết quả tràn có thể đổi dấu và chọn đường sai. Dùng `Math.addExact` để phát hiện hoặc `BigInteger` để xử lý khi miền dữ liệu đòi hỏi.

**Bài 14 — cải tiến nhiều nguồn.** Một DAG không đổi, cần giải đường ngắn nhất từ nhiều nguồn. Có cần tính topo lại cho mỗi nguồn?

*Đáp án:* Không bắt buộc. Có thể lưu topo một lần, sau đó khởi tạo lại reachable/dist/parent và relax theo cùng topo cho từng nguồn.

## 15. Quy trình giải bài thi và triển khai sản phẩm

1. **Xác định chính xác mô hình:** đồ thị có hướng hay vô hướng, trọng số tính trên cạnh hay đỉnh, có n và m bao nhiêu, nguồn/đích hợp lệ không.
2. **Kiểm tra DAG toàn cục** bằng Kahn hoặc DFS ba màu. Nếu có vòng, phương pháp topo một lượt **không áp dụng**.
3. **Xây danh sách kề** có trọng số, giữ đúng chiều cạnh; xử lý cạnh song song theo đầu vào.
4. **Tạo thứ tự topo**, không tự thay bằng thứ tự nhãn đỉnh.
5. **Khởi tạo trạng thái nguồn và unreachable** tách bạch; dùng mảng reachable để tránh INF số học.
6. **Relax theo topo**: bỏ qua đỉnh chưa reachable, cộng trọng số an toàn, cập nhật parent khi có cải thiện nghiêm ngặt.
7. **Khôi phục đường nếu cần** bằng parent từ đích ngược về nguồn, rồi đảo thứ tự.
8. **Kiểm tra chứng cứ**: mỗi cạnh trên đường thật sự tồn tại đúng hướng và tổng trọng số bằng dist[đích].
9. **Đối chiếu với thuật toán chậm** trên DAG nhỏ, kể cả cạnh âm, hòa, self-loop không hợp lệ, thành phần không tới được, đỉnh nguồn và n=0.
10. **Phân tích tài nguyên** theo V+E và miền trọng số; nếu cần số học lớn, chi phí BigInteger thay đổi.

## Kết luận

**Đường đi ngắn nhất trên DAG** được giải bằng một ý tưởng đơn giản mà hiệu quả: **sắp xếp topo trước, thư giãn từng cạnh một lần từ trái sang phải trong thứ tự đó**. Vì mọi cạnh đều hướng tới một đỉnh đứng sau, khi một đỉnh được xử lý thì tất cả phương án đi vào nó đã được xét; điều này vẫn đúng khi trọng số cạnh âm.

Bảo đảm quan trọng nhất không phải “trọng số không âm”, mà là **không có chu trình có hướng**. Với Kahn để kiểm tra DAG, mảng reachable để tránh INF giả, phép cộng có kiểm soát và parent để khôi phục chứng cứ, ta có lời giải **O(V+E)** vừa đúng vừa có thể kiểm thử độc lập.
