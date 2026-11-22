# Truy vấn nhiều nguồn, nhiều đích và toàn bộ các cặp

Bài toán **đường đi ngắn nhất (shortest path)** thường được dạy trước tiên dưới dạng: “Cho một đỉnh s, hãy tìm khoảng cách ngắn nhất từ s tới mọi đỉnh khác”. Nhưng trong ứng dụng thực tế, bộ dữ liệu có thể cần trả **hàng nghìn cặp nguồn–đích**, tìm **điểm gần nhất trong nhiều nguồn**, hoặc tính **khoảng cách giữa mọi cặp đỉnh**. Những yêu cầu này có quan hệ nhưng **không tương đương**, vì vậy lựa chọn thuật toán và lượng tiền xử lý cần dựa vào đúng hình thức truy vấn.

Bài thuộc nhóm **Đường đi ngắn nhất** trong Computer Science Algorithms, tập trung vào **“Truy vấn nhiều nguồn, nhiều đích và toàn bộ các cặp”**. Ta sẽ phân biệt các kiểu bài; xét tính có hướng, cạnh không âm/âm, đỉnh không thể tới và chu trình âm; sử dụng **BFS, Dijkstra, Bellman–Ford, Floyd–Warshall và Johnson** đúng giả thiết; tận dụng **đảo chiều cạnh** cho nhiều nguồn–một đích; dùng **nhiều nguồn khởi tạo cùng lúc** khi chỉ cần khoảng cách tới nguồn gần nhất; và chọn phương án xử lý nhiều truy vấn theo số nguồn/đích phân biệt.

Mã Java 17+ độc lập ở cuối bài thực hiện bốn hướng xử lý: **Floyd–Warshall**, **Johnson**, **multi-source Dijkstra**, và **gom truy vấn theo nguồn hoặc theo đích trên đồ thị đảo cạnh**. Code có truy vết đường đi của Floyd–Warshall và bộ kiểm thử đối chiếu độc lập trên **4.113 đồ thị nhỏ vét cạn** cùng **700 đồ thị có seed**.

## 1. Mô hình đồ thị và câu hỏi cần trả lời

Đặt G=(V,E) là đồ thị có n=|V| đỉnh, m=|E| cạnh. Mỗi cạnh (u,v,w) có trọng số w; khi **đồ thị có hướng**, ta chỉ được đi từ u tới v. Đường đi từ s tới t có tổng trọng số là tổng w của các cạnh trên đường.

Ký hiệu d(s,t) là **chi phí nhỏ nhất** trong các đường từ s tới t:

- Nếu s=t và không có chu trình âm ảnh hưởng, d(s,s)=0 (đường đi rỗng).
- Nếu không có đường từ s tới t, d(s,t)=**INF** (không thể đến).
- Nếu có thể đi từ s tới một **chu trình âm**, lặp nó tùy ý rồi vẫn đến t, không có khoảng cách hữu hạn nhỏ nhất; giá trị lý thuyết giảm vô hạn về −∞.

**Trước khi code**, phân biệt ít nhất năm yêu cầu:

| Kiểu truy vấn | Đầu vào thường có | Kết quả |
| --- | --- | --- |
| Một nguồn, nhiều đích (SSSP) | s, toàn bộ V hoặc một số đích | d(s,v) theo v |
| Nhiều nguồn, **nguồn gần nhất** | Tập S | min với s thuộc S của d(s,v) cho mỗi v |
| Nhiều nguồn, một đích cố định | Nhiều s, một t | d(s,t) theo từng s |
| Nhiều cặp tùy ý | Q cặp (s_i,t_i) | Q giá trị d(s_i,t_i) theo thứ tự truy vấn |
| Toàn bộ các cặp (APSP) | Mọi s,t thuộc V | Ma trận D[s][t]=d(s,t) kích thước n×n |

**Bẫy quan trọng:** multi-source Dijkstra với tất cả nguồn khởi tạo bằng 0 cho **một khoảng cách nhỏ nhất** tới nguồn gần nhất, **không** trả đủ d(s,v) cho từng s. Nếu đề yêu cầu một ma trận khoảng cách của k nguồn, thường phải chạy SSSP riêng cho từng nguồn hoặc xử lý APSP.

## 2. Kiểu trọng số quyết định thuật toán

| Tình huống | Công cụ tự nhiên | Điều kiện và nhận xét |
| --- | --- | --- |
| Mọi cạnh có giá bằng nhau, thường 1 | BFS | O(n+m), không cần heap |
| Trọng số chỉ bằng 0 hoặc 1 | 0–1 BFS | Dùng deque, O(n+m) |
| Trọng số **không âm** bất kỳ | Dijkstra + priority queue | O((n+m)log n) theo cận heap đơn giản |
| Có cạnh **âm** nhưng không có chu trình âm liên quan | Bellman–Ford | O(nm) cho mỗi nguồn, xử lý cạnh âm |
| APSP, đồ thị tương đối nhỏ hoặc dày | Floyd–Warshall | O(n³), O(n²), chấp nhận cạnh âm nếu không có chu trình âm |
| APSP, đồ thị thưa, cạnh âm có thể có | Johnson | Bellman–Ford lấy potential rồi n lần Dijkstra |
| Rất nhiều truy vấn từ ít nguồn | Cache các lần chạy SSSP | Chỉ tính lại khi xuất hiện nguồn mới |
| Rất nhiều nguồn tới ít đích | Đảo cạnh và SSSP từ từng đích | Khai thác d_G(s,t)=d_reverse(t,s) |

Không dùng Dijkstra trực tiếp khi có trọng số âm. Nếu đồ thị vô hướng có một **cạnh âm** và cho phép đi qua cạnh hai chiều, việc đi u→v→u có tổng 2w âm tạo chu trình âm theo cách tính đường đi kiểu walk, nên bài ngắn nhất tổng quát có thể trở nên không xác định hữu hạn. Java demo xử lý **đồ thị có hướng**; để biểu diễn cạnh vô hướng, thêm **hai cạnh có hướng** tương ứng, nhưng cần chú ý cảnh báo cạnh âm nêu trên.

## 3. Một nguồn → nhiều đích: tái sử dụng một lần SSSP

Nếu các truy vấn là (s,t1),(s,t2),... từ **cùng s**, không nên chạy lại Dijkstra từ s mỗi lần hỏi một đích. Chạy **một lần** và giữ mảng:

~~~text
dist[v] = d(s,v).

Mỗi truy vấn (s,t):
    trả dist[t] trong O(1).
~~~

Trên đồ thị cạnh không âm, Dijkstra với heap nhị phân và danh sách kề đạt O((n+m)log n) cho một lượt trong cách phân tích cận trên đơn giản. Với Q truy vấn cùng nguồn, tổng O((n+m)log n + Q), thay vì Q lần làm việc gần như giống hệt.

Với cạnh âm không có chu trình âm từ nguồn, dùng Bellman–Ford hoặc phương pháp phù hợp hơn thay vì “cố dùng Dijkstra rồi sửa”. Cần lưu ý **chu trình âm chỉ là vấn đề cho các cặp có thể đi qua nó**; một yêu cầu APSP hữu hạn thường phải kiểm tra toàn đồ thị và từ chối khi có chu trình âm ở bất cứ thành phần nào.

## 4. Nhiều nguồn → nguồn gần nhất: khởi tạo đồng thời

Cho tập S={s1,s2,...,sk}; yêu cầu là:

~~~text
nearest[v] = min_{s thuộc S} d(s,v).
~~~

Đối với trọng số không âm, **multi-source Dijkstra** chỉ khác bản một nguồn ở bước khởi tạo:

~~~text
dist[v] = INF cho mọi v.

for s in S:
    dist[s] = 0
    push (distance=0, vertex=s) vào priority queue.

while queue chưa rỗng:
    lấy đỉnh u với khoảng cách nhỏ nhất
    relax mọi cạnh u -> v như Dijkstra thông thường.
~~~

Cách hiểu chính xác là ta thêm một **siêu nguồn q** và cạnh q→s trọng số 0 cho mọi s thuộc S, sau đó chạy Dijkstra từ q. Mọi đường q→v bắt buộc bắt đầu bằng một nguồn nào đó trong S, nên d(q,v)=min_s d(s,v). Để tránh cấp thêm đỉnh/cạnh thật, ta đưa tất cả nguồn vào heap với khoảng cách 0 từ đầu.

**Ví dụ:**

~~~text
Nguồn được chọn S = {0,2}.
Từ 0 có d(0,4)=7.
Từ 2 có d(2,4)=6.

nearest[4] = min(7,6) = 6.
~~~

Nếu S rỗng, không có nguồn nào để đi từ đó: theo quy ước của mã minh họa, mọi phần tử nearest[v] giữ nguyên INF. Nguồn trùng lặp không thay đổi kết quả. Trường hợp muốn biết **nguồn nào gần nhất**, hãy truyền nhãn origin qua mỗi lần relax và quy định rõ tie-break khi có nhiều nguồn hòa.

**Đừng áp dụng cho bài yêu cầu từng nguồn:** khoảng cách tới nguồn gần nhất làm mất các giá trị còn lại. Ví dụ nearest[4]=6 **không** nói d(0,4)=7 nếu chỉ lưu nearest.

## 5. Nhiều nguồn tới cùng một đích: đảo hướng cạnh

Trong đồ thị **có hướng**, giả sử nhiều truy vấn hỏi d(s,t) với **t cố định** và s thay đổi. Thay vì chạy một lần SSSP cho mỗi s, dựng đồ thị đảo chiều G^R bằng cách đổi **mỗi cạnh**:

~~~text
G:   (u -> v, trọng số w)
G^R: (v -> u, trọng số w)
~~~

Mỗi đường s→...→t trong G tương ứng chính xác với đường đảo t→...→s trong G^R, với **cùng tổng trọng số**. Vì vậy:

~~~text
d_G(s,t) = d_(G^R)(t,s).
~~~

Chỉ cần **một lần Dijkstra từ t trên G^R** nếu trọng số không âm, ta có toàn bộ khoảng cách từ mọi s tới t trong G.

Lưu ý phải đảo **cạnh**, không chỉ đổi chỗ các tham số nguồn/đích trên cùng đồ thị. Trong đồ thị có hướng thường d(s,t) khác d(t,s), thậm chí một chiều có đường nhưng chiều kia không có. Với đồ thị vô hướng, G^R thực chất là chính G nếu hai hướng mang cùng trọng số.

Nếu trọng số âm, phép tương ứng đường đi khi đảo cạnh vẫn đúng, nhưng thuật toán SSSP trên đồ thị đảo vẫn phải xử lý cạnh âm bằng Bellman–Ford hoặc cách phù hợp; **đảo cạnh không biến cạnh âm thành không âm**.

## 6. Q truy vấn (s,t): gom theo nguồn hoặc theo đích

Giả sử có Q cặp truy vấn, nhưng chỉ **S nguồn phân biệt** và **T đích phân biệt**. Với trọng số không âm, có hai chiến lược đơn giản:

**A. Cache theo nguồn:**

~~~text
Mỗi nguồn s xuất hiện lần đầu:
    chạy Dijkstra từ s trên G -> distFrom[s].

Trả query(s,t) bằng distFrom[s][t].
~~~

Chi phí thời gian khoảng O(S·(n+m)log n + Q), bộ nhớ lưu cache O(Sn) số khoảng cách.

**B. Cache theo đích:**

~~~text
Đảo G thành G^R một lần.
Mỗi đích t xuất hiện lần đầu:
    chạy Dijkstra từ t trên G^R -> distTo[t].

Trả query(s,t) bằng distTo[t][s].
~~~

Chi phí thời gian O(n+m + T·(n+m)log n + Q); cache O(Tn).

Nếu S≤T, bản theo nguồn thường rẻ hơn; nếu T<S, bản theo đích thường rẻ hơn. Chương trình Java dùng **đúng quy tắc lựa chọn theo số nguồn/đích phân biệt**, tính kết quả theo thứ tự truy vấn gốc. Nó không tự giải quyết truy vấn trên đồ thị có cạnh âm bằng Dijkstra.

**Ghi nhớ:** Q có thể rất lớn nhưng S hoặc T nhỏ. Lúc đó thời gian xử lý không tỷ lệ với Q lần thuật toán đồ thị, mà với số **đầu mối khác nhau** đã gom. Nếu Q nhỏ, thậm chí một lần SSSP cho một vài truy vấn là đủ; không cần tốn O(n²) bộ nhớ để dựng toàn bộ ma trận APSP.

## 7. Khi nào nên tính toàn bộ các cặp?

**All-Pairs Shortest Paths (APSP)** yêu cầu n×n khoảng cách:

~~~text
D[i][j] = d(i,j).
~~~

Kết quả có n² phần tử, vì vậy nếu lưu toàn bộ ma trận dày đặc, **bộ nhớ ít nhất Ω(n²)**. Ngay cả với thuật toán rất nhanh, việc **xuất tất cả n² giá trị** cũng cần Ω(n²) thời gian riêng cho đầu ra.

Có ba lựa chọn điển hình:

1. **Chạy SSSP từ mọi đỉnh:** nếu trọng số không âm, n lần Dijkstra; thích hợp đồ thị thưa khi heap hoạt động hiệu quả.
2. **Floyd–Warshall:** quy hoạch động ba vòng for, O(n³) thời gian, O(n²) bộ nhớ; thường thuận tiện khi n không lớn, đồ thị dày, hoặc cần xử lý cạnh âm (không có chu trình âm).
3. **Johnson:** chạy Bellman–Ford một lần để đổi trọng số sang không âm, rồi chạy Dijkstra n lần; hữu ích với đồ thị thưa có cạnh âm nhưng **không có chu trình âm**.

Nếu chỉ một phần nhỏ trong ma trận được hỏi, tính tất cả có thể lãng phí. Nếu sau tiền xử lý có hàng triệu truy vấn mọi cặp và n vừa phải, ma trận APSP cho phép trả d(s,t) **O(1) mỗi truy vấn**, đổi lại tiền xử lý và bộ nhớ lớn.

## 8. Floyd–Warshall: trạng thái quy hoạch động

Đánh số đỉnh từ 0 tới n−1. Đặt D^(k)[i][j] là chi phí đường đi nhỏ nhất từ i tới j mà các đỉnh **trung gian** được phép lấy từ tập {0,...,k}; đỉnh đầu/cuối không chịu ràng buộc đó.

Khởi tạo trước khi cho phép đỉnh trung gian:

~~~text
dist[i][i] = 0.
dist[u][v] = min(trọng số các cạnh trực tiếp u->v).
dist[i][j] = INF nếu không có cạnh và i!=j.
~~~

Nếu có nhiều cạnh song song u→v, phải lấy **trọng số nhỏ nhất** làm cạnh trực tiếp tốt nhất; không được để cạnh nhập sau ghi đè cạnh rẻ hơn.

Tại bước k, một đường tốt nhất hoặc:

- **Không đi qua k ở vai trò trung gian**: giữ dist[i][j] cũ.
- **Có đi qua k**: chia thành đường i→k và k→j, cho ứng viên dist[i][k]+dist[k][j].

Vì vậy công thức:

~~~text
dist[i][j] = min(dist[i][j],
                 dist[i][k] + dist[k][j]).

for k = 0..n-1:
    for i = 0..n-1:
        for j = 0..n-1:
            nếu hai phần dist[i][k] và dist[k][j] khác INF:
                relax dist[i][j].
~~~

Phải đặt vòng **k ngoài cùng** để bất biến “chỉ cho phép thêm đỉnh trung gian k” được duy trì. Nếu đổi k thành vòng trong cùng, ta không còn áp dụng trực tiếp chứng minh quy hoạch động chuẩn, và một số thứ tự vòng có thể trả sai.

Trong cài đặt in-place, cập nhật khi k cố định là hợp lệ nếu không có chu trình âm, vì những đường tốt nhất không cần lặp đỉnh trung gian k; trạng thái D^(k−1) và D^(k) được sử dụng phù hợp qua bất biến.

## 9. Chứng minh Floyd–Warshall bằng quy nạp

**Cơ sở:** trước k=0, đường hợp lệ không có đỉnh trung gian là đường rỗng i=j hoặc một cạnh trực tiếp i→j. Khởi tạo d=0 trên đường chéo, min trọng số các cạnh song song, INF nếu không có đường là đúng.

**Bước quy nạp:** giả sử dist lưu đáp án tối ưu với đỉnh trung gian thuộc {0,...,k−1}. Xét đường tối ưu với tập được mở rộng thêm k:

- Nếu không dùng k ở giữa, chi phí không nhỏ hơn trạng thái cũ và có ứng viên chính dist[i][j].
- Nếu dùng k, trong trường hợp không có chu trình âm có thể xét một đường ngắn nhất không cần lặp k làm đỉnh trung gian; chia đường tại k thành i→k và k→j, mỗi nửa chỉ cần những đỉnh trung gian cũ. Tổng chi phí chính là ứng viên dist[i][k]+dist[k][j] theo giả thiết quy nạp.

Vì lấy min của **hai trường hợp phủ hết** các đường hợp lệ, kết quả sau k là tối ưu. Sau k=n−1, mọi đỉnh đều được phép làm trung gian; ta có d(i,j) cho toàn bộ các cặp nếu không có chu trình âm.

Khi có chu trình âm, ý nghĩa “độ dài ngắn nhất hữu hạn” có thể mất, và công thức không được dùng để tự nhận giá trị hữu hạn cho cặp bị ảnh hưởng. Code **từ chối toàn bộ bài APSP** nếu phát hiện một đỉnh v với dist[v][v]<0 sau khi xử lý.

## 10. Floyd–Warshall: khôi phục đường đi với next

Nếu chỉ cần khoảng cách, bảng dist là đủ. Khi cần in một đường đi tối ưu, duy trì bảng **next[i][j]**, tức đỉnh tiếp theo cần tới khi bắt đầu từ i để đi tới j theo đường ngắn nhất đang biết.

Khởi tạo:

~~~text
next[i][i] = i.
Có cạnh trực tiếp i->j rẻ nhất: next[i][j] = j.
Không có đường: next[i][j] = -1.
~~~

Khi một đường qua k **cải thiện nghiêm ngặt** dist[i][j], cập nhật:

~~~text
dist[i][j] = dist[i][k] + dist[k][j].
next[i][j] = next[i][k].
~~~

Để khôi phục đường từ s tới t, bắt đầu tại s, liên tục lấy next[current][t] cho đến t. Nếu d(s,t)=INF, trả danh sách rỗng. Nếu s=t và không có chu trình âm, đường rỗng có thể được biểu diễn bằng danh sách một đỉnh [s].

Ví dụ:

~~~text
Các cạnh:
0->1 trọng số 2; 0->2 trọng số 9;
1->2 trọng số -3; 1->3 trọng số 4;
2->3 trọng số 2; 3->4 trọng số 1;
0->4 trọng số 20.

Đường ngắn nhất 0->4:
0 -> 1 -> 2 -> 3 -> 4
Tổng = 2 + (-3) + 2 + 1 = 2.
~~~

Bảng next chỉ có ý nghĩa sau khi xác nhận không có chu trình âm theo hợp đồng demo. Trong code, hàm path giới hạn số bước truy vết; nếu một lỗi logic làm truy vết vòng lặp, hàm ném AssertionError thay vì lặp vô hạn.

## 11. INF, cặp không thể đến và chu trình âm

Có ba khái niệm **không được trộn**:

- **Khoảng cách hữu hạn:** tồn tại đường đi tốt nhất với tổng trọng số xác định.
- **Không thể đến (INF):** không tồn tại đường từ s tới t.
- **Chu trình âm liên quan (−∞):** tồn tại đường s tới một chu trình tổng trọng số âm và từ chu trình vẫn tới t, nên có thể đi quanh chu trình nhiều lần để giảm tổng không giới hạn.

**INF không phải một cạnh có trọng số rất lớn.** Nó là trạng thái “không có đường”. Vì vậy trong Floyd–Warshall cần bỏ qua phép cộng nếu một vế INF; phép cộng INF+w có thể tràn số hoặc tạo kết quả vô nghĩa.

Để tìm chu trình âm bằng Floyd, sau khi chạy xét các phần tử đường chéo: nếu có dist[v][v]<0, có một đường đi đóng âm liên quan tới v. APSP hữu hạn cho **tất cả** cặp không tồn tại theo cách thông thường; chương trình minh họa ném IllegalArgumentException cho cả kết quả APSP.

Trong những bài truy vấn s,t riêng lẻ, một chu trình âm nằm ở thành phần không thể đi tới từ s hoặc không tới được t **không nhất thiết ảnh hưởng** d(s,t). Khi đó cần thuật toán kiểm tra ảnh hưởng theo từng nguồn/đích, chứ không buộc mọi API phải từ chối tất cả cặp. Chính sách code trong bài là chính sách rõ ràng của **APSP toàn cục**.

## 12. Johnson: tái trọng số để dùng Dijkstra

Johnson giải APSP trong đồ thị có thể có cạnh âm **nhưng không có chu trình âm**.

Bước 1: thêm **siêu nguồn q** với cạnh q→v trọng số 0 cho mọi v, rồi chạy Bellman–Ford từ q. Đặt h[v]=d(q,v). Vì q nối tới mọi đỉnh, mọi h[v] hữu hạn; nếu Bellman–Ford phát hiện chu trình âm thì không dùng Johnson.

Bước 2: với mỗi cạnh u→v trọng số w, định nghĩa trọng số mới:

~~~text
w'(u,v) = w(u,v) + h[u] - h[v].
~~~

Từ bất đẳng thức đường ngắn nhất:

~~~text
h[v] <= h[u] + w(u,v)
=> w(u,v) + h[u] - h[v] >= 0.
~~~

Do đó **mọi trọng số mới đều không âm**, điều kiện Dijkstra cần.

Bước 3: chạy Dijkstra trên đồ thị tái trọng số từ **mọi nguồn s**. Nếu khoảng cách mới là d'(s,t), đổi về khoảng cách cũ bằng:

~~~text
d(s,t) = d'(s,t) - h[s] + h[t].
~~~

Nếu t không tới được từ s, vẫn trả INF. Việc tái trọng số không tạo hoặc hủy đường đi; nó chỉ đổi trọng số của từng cạnh.

**Hiện thực Java:** thay vì xây thật đỉnh q, khởi tạo h[v]=0 cho mọi v. Điều này tương đương Bellman–Ford với siêu nguồn q có cạnh 0 tới tất cả đỉnh, vì ban đầu mỗi đỉnh đã có khoảng cách 0. Sau đó dùng dijkstraCore trên trọng số tái tính từ potential.

## 13. Chứng minh Johnson bảo toàn đường đi ngắn nhất

Xét đường P: s=v0→v1→...→vk=t. Tổng trọng số tái định nghĩa:

~~~text
w'(P)
= Σ [w(vi,vi+1) + h[vi] - h[vi+1]]
= Σ w(vi,vi+1) + h[s] - h[t]
= w(P) + h[s] - h[t].
~~~

Các h ở đỉnh nội bộ **triệt tiêu từng cặp**. Với s,t cố định, phần chênh h[s]−h[t] là **hằng số đối với mọi đường** từ s tới t. Vì vậy đường nào nhỏ nhất theo w cũng nhỏ nhất theo w', và ngược lại.

Bởi mọi cạnh w' không âm, Dijkstra tính được d'(s,t) chính xác. Đảo phép biến đổi cho d(s,t). Bellman–Ford trên siêu nguồn bảo đảm h hợp lệ và phát hiện chu trình âm toàn cục trước khi chạy Dijkstra.

**Nếu quên phục hồi h:** kết quả trả sẽ là khoảng cách của đồ thị tái trọng số, không phải khoảng cách gốc. **Nếu bỏ Bellman–Ford:** có thể tồn tại w' âm, khiến Dijkstra không còn được bảo đảm đúng.

## 14. Phân tích thời gian Floyd, Johnson và lặp Dijkstra

| Phương án | Thời gian tiền xử lý toàn bộ | Bộ nhớ để lưu toàn bộ kết quả |
| --- | --- | --- |
| Floyd–Warshall | O(n³) | O(n²) |
| n lần Dijkstra, w≥0 | O(n(n+m)log n) với heap nhị phân | O(n²) |
| Johnson, không có chu trình âm | O(nm + n(n+m)log n) | O(n²) |
| SSSP từ S nguồn phân biệt | O(S(n+m)log n) nếu w≥0 | O(Sn) nếu cache mọi hàng |
| SSSP đảo từ T đích phân biệt | O(n+m + T(n+m)log n) nếu w≥0 | O(Tn) nếu cache |
| Multi-source nearest, w≥0 | O((n+m)log n) một lượt | O(n+m) gồm đồ thị và kết quả |

Các công thức thời gian với Dijkstra dùng cách cài heap binary có thể chứa nhiều bản ghi của cùng đỉnh và bỏ bản ghi cũ; cận O((n+m)log n) là đủ cho mục đích chọn hướng giải trong miền n,m thông thường.

**Chọn theo mật độ:** với đồ thị dày có m≈n² và n vừa phải, Floyd O(n³) thường hấp dẫn hơn Johnson cài Dijkstra n lần với yếu tố log. Với đồ thị thưa m≈n và cần APSP có cạnh âm, Johnson cho phép tận dụng heap sau một lần Bellman–Ford. Với Q nhỏ, chạy trực tiếp hoặc gom các truy vấn hiếm khi cần toàn bộ ma trận.

Đừng bỏ quên bộ nhớ O(n²): ngay cả khi thuật toán xử lý cạnh thưa, **ma trận APSP đầy đủ** vẫn có n² giá trị. Nếu chỉ cần một vài cặp, cache các hàng cần thiết sẽ tiết kiệm hơn nhiều.

## 15. Hai ví dụ để tránh nhầm nguồn và đích

**Ví dụ A — có cạnh âm nhưng không có chu trình âm**:

~~~text
0 -> 1:  2
0 -> 2:  9
1 -> 2: -3
1 -> 3:  4
2 -> 3:  2
3 -> 4:  1
0 -> 4: 20
~~~

Đồ thị có hướng này không có chu trình. Floyd–Warshall và Johnson cùng cho hàng nguồn 0:

~~~text
d(0,*) = [0, 2, -1, 1, 2].
Đường 0->4: [0,1,2,3,4], tổng trọng số 2.
Đường từ 4 về 0 không tồn tại => INF.
~~~

Việc có cạnh 1→2 trọng số −3 **không làm một đường đi âm trở thành vô hiệu**; chỉ **chu trình âm** mới gây vấn đề không có cực tiểu hữu hạn. Dijkstra trực tiếp không được dùng ở đây vì có cạnh âm.

**Ví dụ B — tất cả trọng số không âm**, các cạnh:

~~~text
0->1:4, 0->2:1, 2->1:2,
1->3:1, 2->3:7, 3->4:3, 2->4:20.
~~~

Từ nguồn 0, đường rẻ nhất tới 4 là 0→2→1→3→4 với tổng 1+2+1+3=7. Từ nguồn 2 tới 4 là 2→1→3→4, tổng 2+1+3=6.

Nếu tập nguồn S={0,2}, multi-source nearest cho:

~~~text
nearest(*) = [0, 2, 0, 3, 6].
~~~

Nếu nhiều người hỏi đến cùng đích 4, chạy Dijkstra từ 4 trên **đồ thị đảo** cho:

~~~text
d(*,4) = [7, 4, 6, 3, 0].
~~~

Hai mảng trên có ý nghĩa **hoàn toàn khác nhau**. Đặc biệt nearest[1]=2 còn d(1,4)=4; không được lấy mảng thứ nhất để trả câu hỏi thứ hai.

## 16. Java 17+: bốn chiến lược trong một chương trình hoàn chỉnh

Lưu mã dưới đây vào **ManyShortestPaths.java**. Chương trình thực hiện:

- **floydWarshall(Graph):** ma trận khoảng cách và bảng next để khôi phục một đường đi.
- **johnson(Graph):** tính potential bằng Bellman–Ford kiểu siêu nguồn, tái trọng số và chạy Dijkstra từ mọi đỉnh.
- **multiSourceNearest(Graph,int[]):** đưa nhiều nguồn vào heap với dist=0, trả min từ bất kỳ nguồn.
- **distancesToTarget(Graph,int):** đảo cạnh và chạy Dijkstra từ đích.
- **answerQueries(Graph,List<Query>):** đếm số nguồn và đích phân biệt; cache theo phía ít phần tử hơn.
- **verify():** đối chiếu nhiều đồ thị nhỏ với Bellman–Ford theo từng nguồn, kiểm tra Floyd và Johnson về chu trình âm, kiểm tra đường khôi phục và các truy vấn.

**Phạm vi của code:** đồ thị **có hướng**, tối đa 500 đỉnh, trọng số nguyên trong [−1.000.000,1.000.000] để các phép tính trung gian của ví dụ nằm xa giới hạn của long và sentinel INF=Long.MAX_VALUE/4. Đầu vào ngoài hợp đồng bị từ chối. Trong bản production không có giới hạn miền số tương tự, cần phân tích cẩn thận bound cho mọi đường đi hoặc dùng số học phù hợp hơn; **không được tự coi Long.MAX_VALUE là vô cực toán học**.

Các API Dijkstra và truy vấn theo nguồn/đích **từ chối cạnh âm**, kể cả khi cạnh âm không nằm trên đường truy vấn, vì đó là hợp đồng đơn giản và rõ ràng của bản minh họa. Floyd và Johnson chấp nhận cạnh âm nếu không có chu trình âm; cả hai từ chối khi phát hiện một chu trình âm bất kỳ.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.StringJoiner;

public final class ManyShortestPaths {
    private static final long INF = Long.MAX_VALUE / 4;

    public record Edge(int from, int to, long weight) { }
    public record Query(int from, int to) { }
    private record State(int vertex, long distance) { }

    public static final class Graph {
        private final int n;
        private final List<Edge> edges;
        private final List<List<Edge>> adj;

        public Graph(int n, List<Edge> input) {
            if (n < 0 || n > 500 || input == null) {
                throw new IllegalArgumentException("demo requires 0<=n<=500");
            }
            for (Edge e : input) {
                if (e == null || e.from() < 0 || e.from() >= n
                        || e.to() < 0 || e.to() >= n
                        || e.weight() < -1_000_000L
                        || e.weight() > 1_000_000L) {
                    throw new IllegalArgumentException("invalid edge");
                }
            }
            this.n = n;
            this.edges = List.copyOf(input);
            adj = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                adj.add(new ArrayList<>());
            }
            for (Edge e : edges) {
                adj.get(e.from()).add(e);
            }
        }

        public int vertexCount() {
            return n;
        }

        public boolean hasNegativeEdge() {
            for (Edge e : edges) {
                if (e.weight() < 0) {
                    return true;
                }
            }
            return false;
        }

        public Graph reverse() {
            List<Edge> reversed = new ArrayList<>();
            for (Edge e : edges) {
                reversed.add(new Edge(e.to(), e.from(), e.weight()));
            }
            return new Graph(n, reversed);
        }
    }

    public static final class FloydResult {
        private final long[][] dist;
        private final int[][] next;

        private FloydResult(long[][] dist, int[][] next) {
            this.dist = dist;
            this.next = next;
        }

        public long distance(int from, int to) {
            if (from < 0 || from >= dist.length
                    || to < 0 || to >= dist.length) {
                throw new IllegalArgumentException("invalid vertex");
            }
            return dist[from][to];
        }

        public long[] row(int source) {
            if (source < 0 || source >= dist.length) {
                throw new IllegalArgumentException("invalid source");
            }
            return dist[source].clone();
        }

        public List<Integer> path(int from, int to) {
            if (distance(from, to) == INF) {
                return List.of();
            }
            List<Integer> result = new ArrayList<>();
            result.add(from);
            int cursor = from;
            for (int hops = 0; cursor != to && hops < dist.length; hops++) {
                cursor = next[cursor][to];
                if (cursor < 0) {
                    throw new AssertionError("broken successor matrix");
                }
                result.add(cursor);
            }
            if (cursor != to) {
                throw new AssertionError("successor loop");
            }
            return List.copyOf(result);
        }
    }

    private ManyShortestPaths() { }

    public static FloydResult floydWarshall(Graph g) {
        int n = g.n;
        long[][] dist = new long[n][n];
        int[][] next = new int[n][n];
        for (int i = 0; i < n; i++) {
            Arrays.fill(dist[i], INF);
            Arrays.fill(next[i], -1);
            dist[i][i] = 0;
            next[i][i] = i;
        }
        for (Edge e : g.edges) {
            if (e.weight() < dist[e.from()][e.to()]) {
                dist[e.from()][e.to()] = e.weight();
                next[e.from()][e.to()] = e.to();
            }
        }
        for (int k = 0; k < n; k++) {
            for (int i = 0; i < n; i++) {
                if (dist[i][k] == INF) {
                    continue;
                }
                for (int j = 0; j < n; j++) {
                    if (dist[k][j] == INF) {
                        continue;
                    }
                    long candidate = Math.addExact(dist[i][k], dist[k][j]);
                    if (candidate < dist[i][j]) {
                        dist[i][j] = candidate;
                        next[i][j] = next[i][k];
                    }
                }
            }
        }
        for (int v = 0; v < n; v++) {
            if (dist[v][v] < 0) {
                throw new IllegalArgumentException("negative cycle");
            }
        }
        return new FloydResult(dist, next);
    }

    private static long[] dijkstraCore(Graph g, int[] sources,
                                        long[] potential) {
        long[] dist = new long[g.n];
        Arrays.fill(dist, INF);
        PriorityQueue<State> queue =
                new PriorityQueue<>(Comparator.comparingLong(State::distance));
        for (int source : sources) {
            checkVertex(g, source);
            if (dist[source] != 0) {
                dist[source] = 0;
                queue.add(new State(source, 0));
            }
        }
        while (!queue.isEmpty()) {
            State current = queue.remove();
            int u = current.vertex();
            if (current.distance() != dist[u]) {
                continue;
            }
            for (Edge e : g.adj.get(u)) {
                long weight = e.weight();
                if (potential != null) {
                    weight = Math.subtractExact(
                            Math.addExact(weight, potential[u]),
                            potential[e.to()]);
                }
                if (weight < 0) {
                    throw new IllegalArgumentException(
                            "Dijkstra requires nonnegative edges");
                }
                long candidate = Math.addExact(dist[u], weight);
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    queue.add(new State(e.to(), candidate));
                }
            }
        }
        return dist;
    }

    private static void checkVertex(Graph g, int vertex) {
        if (vertex < 0 || vertex >= g.n) {
            throw new IllegalArgumentException("invalid vertex");
        }
    }

    private static void requireNonnegative(Graph g) {
        if (g.hasNegativeEdge()) {
            throw new IllegalArgumentException("negative edge not allowed");
        }
    }

    public static long[] dijkstra(Graph g, int source) {
        requireNonnegative(g);
        return dijkstraCore(g, new int[] {source}, null);
    }

    public static long[] multiSourceNearest(Graph g, int[] sources) {
        if (sources == null) {
            throw new IllegalArgumentException("null sources");
        }
        requireNonnegative(g);
        return dijkstraCore(g, sources, null);
    }

    public static long[] distancesToTarget(Graph g, int target) {
        requireNonnegative(g);
        checkVertex(g, target);
        return dijkstra(g.reverse(), target);
    }

    public static long[] answerQueries(Graph g, List<Query> queries) {
        if (queries == null) {
            throw new IllegalArgumentException("null queries");
        }
        requireNonnegative(g);
        boolean[] sourceUsed = new boolean[g.n];
        boolean[] targetUsed = new boolean[g.n];
        int sourceCount = 0, targetCount = 0;
        for (Query q : queries) {
            if (q == null) {
                throw new IllegalArgumentException("null query");
            }
            checkVertex(g, q.from());
            checkVertex(g, q.to());
            if (!sourceUsed[q.from()]) {
                sourceUsed[q.from()] = true;
                sourceCount++;
            }
            if (!targetUsed[q.to()]) {
                targetUsed[q.to()] = true;
                targetCount++;
            }
        }

        long[] answers = new long[queries.size()];
        long[][] cache = new long[g.n][];
        if (sourceCount <= targetCount) {
            for (int k = 0; k < queries.size(); k++) {
                Query q = queries.get(k);
                if (cache[q.from()] == null) {
                    cache[q.from()] = dijkstra(g, q.from());
                }
                answers[k] = cache[q.from()][q.to()];
            }
        } else {
            Graph reversed = g.reverse();
            for (int k = 0; k < queries.size(); k++) {
                Query q = queries.get(k);
                if (cache[q.to()] == null) {
                    cache[q.to()] = dijkstra(reversed, q.to());
                }
                answers[k] = cache[q.to()][q.from()];
            }
        }
        return answers;
    }

    public static long[][] johnson(Graph g) {
        int n = g.n;
        long[] potential = new long[n];
        for (int iteration = 0; iteration < n; iteration++) {
            boolean changed = false;
            for (Edge e : g.edges) {
                long candidate = Math.addExact(
                        potential[e.from()], e.weight());
                if (candidate < potential[e.to()]) {
                    potential[e.to()] = candidate;
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
            if (iteration == n - 1) {
                throw new IllegalArgumentException("negative cycle");
            }
        }
        long[][] result = new long[n][n];
        for (int source = 0; source < n; source++) {
            long[] reweighted = dijkstraCore(g,
                    new int[] {source}, potential);
            for (int target = 0; target < n; target++) {
                if (reweighted[target] == INF) {
                    result[source][target] = INF;
                } else {
                    result[source][target] = Math.addExact(
                            Math.subtractExact(reweighted[target],
                                    potential[source]),
                            potential[target]);
                }
            }
        }
        return result;
    }

    private static long[] bellmanFordReference(Graph g, int source) {
        long[] dist = new long[g.n];
        Arrays.fill(dist, INF);
        dist[source] = 0;
        for (int iteration = 1; iteration < g.n; iteration++) {
            boolean changed = false;
            for (Edge e : g.edges) {
                if (dist[e.from()] == INF) {
                    continue;
                }
                long candidate = Math.addExact(
                        dist[e.from()], e.weight());
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    changed = true;
                }
            }
            if (!changed) {
                break;
            }
        }
        return dist;
    }

    private static boolean hasNegativeCycleReference(Graph g) {
        long[] dist = new long[g.n];
        for (int iteration = 0; iteration < g.n; iteration++) {
            boolean changed = false;
            for (Edge e : g.edges) {
                long candidate = Math.addExact(
                        dist[e.from()], e.weight());
                if (candidate < dist[e.to()]) {
                    dist[e.to()] = candidate;
                    changed = true;
                }
            }
            if (!changed) {
                return false;
            }
            if (iteration == g.n - 1) {
                return true;
            }
        }
        return false;
    }

    private static void checkPaths(Graph g, FloydResult f) {
        for (int source = 0; source < g.n; source++) {
            for (int target = 0; target < g.n; target++) {
                List<Integer> path = f.path(source, target);
                if (f.distance(source, target) == INF) {
                    if (!path.isEmpty()) {
                        throw new AssertionError("unreachable path is nonempty");
                    }
                    continue;
                }
                if (path.size() == 0 || path.size() > g.n + 1
                        || path.get(0) != source
                        || path.get(path.size() - 1) != target) {
                    throw new AssertionError("invalid path endpoints/size");
                }
                long weight = 0;
                for (int i = 0; i + 1 < path.size(); i++) {
                    int u = path.get(i), v = path.get(i + 1);
                    long minimum = INF;
                    for (Edge e : g.edges) {
                        if (e.from() == u && e.to() == v) {
                            minimum = Math.min(minimum, e.weight());
                        }
                    }
                    if (minimum == INF) {
                        throw new AssertionError("path uses absent arc");
                    }
                    weight += minimum;
                }
                if (weight != f.distance(source, target)) {
                    throw new AssertionError("path cost mismatch");
                }
            }
        }
    }

    private static void compare(Graph g) {
        boolean negativeCycle = hasNegativeCycleReference(g);
        FloydResult floyd = null;
        long[][] johnson = null;
        boolean floydRejected = false, johnsonRejected = false;
        try {
            floyd = floydWarshall(g);
        } catch (IllegalArgumentException expected) {
            floydRejected = true;
        }
        try {
            johnson = johnson(g);
        } catch (IllegalArgumentException expected) {
            johnsonRejected = true;
        }
        if (negativeCycle) {
            if (!floydRejected || !johnsonRejected) {
                throw new AssertionError("negative cycle not rejected");
            }
            return;
        }
        if (floydRejected || johnsonRejected) {
            throw new AssertionError("false negative-cycle rejection");
        }
        checkPaths(g, floyd);
        for (int source = 0; source < g.n; source++) {
            long[] baseline = bellmanFordReference(g, source);
            if (!Arrays.equals(baseline, floyd.row(source))
                    || !Arrays.equals(baseline, johnson[source])) {
                throw new AssertionError("APSP mismatch");
            }
        }
        if (!g.hasNegativeEdge() && g.n > 0) {
            for (int source = 0; source < g.n; source++) {
                if (!Arrays.equals(dijkstra(g, source), floyd.row(source))) {
                    throw new AssertionError("Dijkstra mismatch");
                }
            }
            int[] sources = {0, g.n - 1, 0};
            long[] nearest = multiSourceNearest(g, sources);
            for (int target = 0; target < g.n; target++) {
                long expected = Math.min(floyd.distance(0, target),
                        floyd.distance(g.n - 1, target));
                if (nearest[target] != expected) {
                    throw new AssertionError("multi-source mismatch");
                }
            }
            long[] toLast = distancesToTarget(g, g.n - 1);
            for (int source = 0; source < g.n; source++) {
                if (toLast[source] != floyd.distance(source, g.n - 1)) {
                    throw new AssertionError("reverse-graph mismatch");
                }
            }
            List<Query> oneSource = new ArrayList<>();
            List<Query> oneTarget = new ArrayList<>();
            for (int vertex = 0; vertex < g.n; vertex++) {
                oneSource.add(new Query(0, vertex));
                oneTarget.add(new Query(vertex, g.n - 1));
            }
            long[] sourceResults = answerQueries(g, oneSource);
            long[] targetResults = answerQueries(g, oneTarget);
            for (int i = 0; i < g.n; i++) {
                if (sourceResults[i] != floyd.distance(0, i)
                        || targetResults[i] != floyd.distance(i, g.n - 1)) {
                    throw new AssertionError("batched-query mismatch");
                }
            }
        }
    }

    private static void verify() {
        int exhaustiveCases = 0;
        long[] choices = {-2, 0, 3};
        for (int n = 1; n <= 3; n++) {
            List<int[]> candidateArcs = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = 0; v < n; v++) {
                    if (u != v) {
                        candidateArcs.add(new int[] {u, v});
                    }
                }
            }
            int combinations = 1;
            for (int i = 0; i < candidateArcs.size(); i++) {
                combinations *= 4;
            }
            for (int code = 0; code < combinations; code++) {
                int rest = code;
                List<Edge> edges = new ArrayList<>();
                for (int[] arc : candidateArcs) {
                    int choice = rest % 4;
                    rest /= 4;
                    if (choice > 0) {
                        edges.add(new Edge(arc[0], arc[1],
                                choices[choice - 1]));
                    }
                }
                compare(new Graph(n, edges));
                exhaustiveCases++;
            }
        }

        Random random = new Random(2962026L);
        int seededCases = 0;
        for (int n = 2; n <= 8; n++) {
            for (int trial = 0; trial < 100; trial++) {
                List<Edge> edges = new ArrayList<>();
                int m = random.nextInt(2 * n + 3);
                for (int i = 0; i < m; i++) {
                    edges.add(new Edge(random.nextInt(n),
                            random.nextInt(n), random.nextInt(9) - 3));
                }
                compare(new Graph(n, edges));
                seededCases++;
            }
        }
        compare(new Graph(0, List.of()));

        try {
            floydWarshall(new Graph(2, List.of(
                    new Edge(0, 1, -2), new Edge(1, 0, 1))));
            throw new AssertionError("negative cycle accepted");
        } catch (IllegalArgumentException expected) {
        }
        try {
            multiSourceNearest(new Graph(2, List.of(
                    new Edge(0, 1, -1))), new int[] {0});
            throw new AssertionError("negative edge accepted by Dijkstra");
        } catch (IllegalArgumentException expected) {
        }
        try {
            dijkstra(new Graph(2, List.of()), 2);
            throw new AssertionError("invalid source accepted");
        } catch (IllegalArgumentException expected) {
        }

        System.out.println("Verified " + exhaustiveCases
                + " exhaustive small directed graphs: PASS");
        System.out.println("Verified " + seededCases
                + " seeded directed graphs: PASS");
        System.out.println("Path, multi-source and query checks: PASS");
    }

    private static String format(long[] distances) {
        StringJoiner joiner = new StringJoiner(", ", "[", "]");
        for (long distance : distances) {
            joiner.add(distance == INF ? "INF" : Long.toString(distance));
        }
        return joiner.toString();
    }

    public static void main(String[] args) {
        Graph negativeEdges = new Graph(5, List.of(
                new Edge(0, 1, 2), new Edge(0, 2, 9),
                new Edge(1, 2, -3), new Edge(1, 3, 4),
                new Edge(2, 3, 2), new Edge(3, 4, 1),
                new Edge(0, 4, 20)));
        FloydResult floyd = floydWarshall(negativeEdges);
        long[][] johnson = johnson(negativeEdges);
        System.out.println("Negative-edge Floyd row 0: "
                + format(floyd.row(0)));
        System.out.println("Negative-edge Johnson row 0: "
                + format(johnson[0]));
        System.out.println("Floyd path 0 to 4: " + floyd.path(0, 4));
        System.out.println("Unreachable 4 to 0: "
                + format(new long[] {floyd.distance(4, 0)}));

        Graph nonnegative = new Graph(5, List.of(
                new Edge(0, 1, 4), new Edge(0, 2, 1),
                new Edge(2, 1, 2), new Edge(1, 3, 1),
                new Edge(2, 3, 7), new Edge(3, 4, 3),
                new Edge(2, 4, 20)));
        System.out.println("Multi-source {0,2}: "
                + format(multiSourceNearest(nonnegative,
                        new int[] {0, 2})));
        System.out.println("Distances to target 4: "
                + format(distancesToTarget(nonnegative, 4)));
        long[] answer = answerQueries(nonnegative, List.of(
                new Query(0, 4), new Query(2, 3),
                new Query(1, 4), new Query(4, 0),
                new Query(0, 3), new Query(2, 1)));
        System.out.println("Query answers: " + format(answer));

        boolean negativeCycleRejected = false;
        try {
            johnson(new Graph(2, List.of(
                    new Edge(0, 1, -2), new Edge(1, 0, 1))));
        } catch (IllegalArgumentException expected) {
            negativeCycleRejected = true;
        }
        System.out.println("Negative cycle rejected: "
                + negativeCycleRejected);
        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ManyShortestPaths.java
java ManyShortestPaths
~~~

**Stdout chính xác** của chương trình:

~~~text
Negative-edge Floyd row 0: [0, 2, -1, 1, 2]
Negative-edge Johnson row 0: [0, 2, -1, 1, 2]
Floyd path 0 to 4: [0, 1, 2, 3, 4]
Unreachable 4 to 0: [INF]
Multi-source {0,2}: [0, 2, 0, 3, 6]
Distances to target 4: [7, 4, 6, 3, 0]
Query answers: [7, 3, 4, INF, 4, 2]
Negative cycle rejected: true
Verified 4113 exhaustive small directed graphs: PASS
Verified 700 seeded directed graphs: PASS
Path, multi-source and query checks: PASS
~~~

Kết quả trình bày rõ cả truy vấn một cặp không thể tới (INF), đường cụ thể 0→4, multi-source nearest, distances-to-target, và một danh sách câu hỏi pha trộn. Nếu thay đổi thứ tự các cạnh có cùng trọng số, **đường đi được truy vết** có thể khác nhưng khoảng cách ngắn nhất phải giữ nguyên.

## 17. Đối chiếu độc lập với Bellman–Ford theo nguồn

Để kiểm chứng Floyd và Johnson, mã không chỉ so chúng với **nhau**. Khi đồ thị **không có chu trình âm**, chương trình còn tính một mảng tham chiếu cho từng nguồn bằng Bellman–Ford:

~~~text
dist[s] = 0; dist[v khác s] = INF.
Lặp tối đa n-1 lượt:
    với mỗi cạnh u->v trọng số w:
        nếu dist[u] hữu hạn:
            dist[v] = min(dist[v], dist[u]+w).
~~~

Với không có chu trình âm, mọi cặp reachable đều có đường đi ngắn nhất đơn, dùng nhiều nhất n−1 cạnh. Sau n−1 vòng relax, Bellman–Ford khôi phục đúng giá trị; đối chiếu **từng phần tử** với hàng tương ứng của Floyd và Johnson.

Để tìm chu trình âm ở **bất kỳ thành phần nào**, bộ thử còn thực hiện bước Bellman–Ford với mọi dist[v]=0 (tương đương một siêu nguồn nối tới tất cả đỉnh). Nếu lượt thứ n vẫn relax được một cạnh, đồ thị có chu trình âm; khi đó kiểm tra **cả Floyd và Johnson đều từ chối**, thay vì buộc chúng trả một ma trận hữu hạn sai.

Kiểm thử cụ thể còn xem **mỗi đường truy vết bằng next** có bắt đầu và kết thúc đúng đỉnh, các bước có cạnh thật, tổng chi phí bằng dist, và không đi vào vòng lặp giả. Đây là kiểm thử **chứng cứ thực tế**, không chỉ kiểm tra một giá trị số.

## 18. Kiểm thử vét cạn 4.113 đồ thị có hướng nhỏ

Bộ kiểm thử sinh các đồ thị có n=1,2,3; với mỗi cung có hướng u→v, u khác v, có **4 khả năng**:

~~~text
0: không có cạnh.
1: có cạnh trọng số -2.
2: có cạnh trọng số 0.
3: có cạnh trọng số 3.
~~~

Có n(n−1) cặp có hướng u≠v, nên số cấu hình theo từng n:

~~~text
n=1: 4^0 =    1
n=2: 4^2 =   16
n=3: 4^6 = 4096

Tổng = 1+16+4096 = 4113 đồ thị.
~~~

Các trường hợp bao gồm cạnh âm, cạnh bằng 0, không liên thông, chu trình âm, và nhiều đường có cùng chi phí. Với từng đồ thị:

1. Kiểm tra sự tồn tại chu trình âm bằng oracle Bellman–Ford kiểu siêu nguồn.
2. Nếu có chu trình âm: cả Floyd và Johnson phải từ chối.
3. Nếu không có chu trình âm: so **mọi d(s,t)** giữa Floyd, Johnson và Bellman–Ford từ từng s.
4. Kiểm tra tính hợp lệ và chi phí của các đường đi mà Floyd trả.
5. Nếu mọi cạnh không âm: so thêm Dijkstra, multi-source nearest và cả hai hướng cache truy vấn.

Như vậy mã được kiểm tra trên đủ **tổ hợp đồ thị nhỏ**, không chỉ một vài ví dụ đẹp.

## 19. Kiểm thử ngẫu nhiên 700 đồ thị có seed

Sau phần vét cạn, chương trình sinh 100 đồ thị cho mỗi kích cỡ n từ 2 tới 8, tổng:

~~~text
7 kích cỡ x 100 lượt = 700 đồ thị có hướng.
~~~

Với seed Random(2962026L), số cạnh được chọn trong [0,2n+2], hai đầu là những đỉnh độc lập (vì thế có **self-loop và cạnh song song**), trọng số nguyên từ −3 tới 5. Các chu trình âm được nhận ra và từ chối bởi Floyd/Johnson; các đồ thị không có chu trình âm được so với Bellman–Ford.

Bộ thử còn xử lý một đồ thị rỗng n=0, một chu trình âm 0→1 trọng số −2 và 1→0 trọng số +1, từ chối Dijkstra khi có cạnh âm, và từ chối chỉ số nguồn vượt n−1.

**Lưu ý về phạm vi:** 4.113+700=4.813 cấu hình được sinh theo hai nhóm, ngoài một số ca biên. Các kết quả PASS không thay thế chứng minh của Floyd, Johnson hoặc tính chất đảo cạnh; chúng giúp phát hiện lỗi hiện thực, off-by-one, sentinel, mất trường hợp INF, hoặc cập nhật next sai.

## 20. Lựa chọn thuật toán theo bài toán thực tế

Một quy trình lựa chọn ngắn gọn:

1. **Xác định hướng cạnh:** directed hay undirected; có phải thêm cả hai hướng không?
2. **Xác định miền trọng số:** 1, {0,1}, không âm, có âm, có khả năng chu trình âm?
3. **Xác định đầu ra:** một cặp; một nguồn; nhiều nguồn gần nhất; nhiều nguồn nhưng cần từng mảng; một đích; nhiều cặp; hay APSP?
4. **Đếm số nguồn/đích phân biệt** trong Q truy vấn.
5. Nếu chỉ cần min tới một tập nguồn và w≥0, dùng **một lần multi-source Dijkstra**.
6. Nếu nhiều nguồn cùng tới một đích và w≥0, dùng **Dijkstra trên đồ thị đảo**.
7. Nếu truy vấn có ít nguồn phân biệt, cache các hàng SSSP; nếu ít đích phân biệt, cache trên đồ thị đảo.
8. Nếu cần tất cả n² cặp, chọn **n lần SSSP**, **Floyd** hoặc **Johnson** theo độ thưa, trọng số và bộ nhớ.
9. Nếu có cạnh âm, **không dùng Dijkstra trực tiếp**; nếu có chu trình âm ảnh hưởng, cần chính sách rõ về −∞ hoặc từ chối APSP.
10. Nếu cần xuất đường đi, lưu **parent/predecessor** trong SSSP hoặc **next** trong Floyd; giá trị khoảng cách không đủ tự tái hiện đường.
11. Kiểm tra trường hợp **không thể tới**, nhiều cạnh song song, đường đi có trọng số 0, self-loop và tràn số.
12. Dùng oracle nhỏ để đối chiếu nhiều kiểu truy vấn trước khi tối ưu số lần chạy.

**Đừng tối ưu nhầm bài toán:** câu hỏi “từ các kho hàng gần nhất tới mọi điểm” chỉ cần min qua kho, còn câu hỏi “mỗi kho tới mọi điểm” cần giữ nhãn của từng kho. Một phép khởi tạo nhiều nguồn cùng 0 chỉ giải bài thứ nhất.

## 21. Những lỗi phổ biến

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chạy multi-source Dijkstra rồi coi là từng hàng nguồn | Đã lấy min và làm mất danh tính nguồn | Chạy SSSP mỗi nguồn hoặc APSP |
| Đảo nguồn và đích mà không đảo cạnh | Trong đồ thị có hướng, d(s,t) thường khác d(t,s) | Dựng đồ thị đảo G^R |
| Dùng Dijkstra với cạnh âm | Điều kiện chốt đỉnh không còn bảo đảm | Bellman–Ford / Johnson / Floyd |
| Chạy Johnson mà không tính potential | Cạnh tái trọng số có thể âm | Bellman–Ford từ siêu nguồn |
| Quên đổi d' về d sau Dijkstra | Trả chi phí của đồ thị đổi trọng số | d = d' - h[s] + h[t] |
| Đảo thứ tự vòng Floyd tùy tiện | Mất bất biến đỉnh trung gian | Để k là vòng ngoài |
| Không khởi tạo dist[i][i]=0 | Làm sai đường đi rỗng | Điền 0 trên đường chéo |
| Không min các cạnh song song | Có thể giữ cạnh trực tiếp đắt hơn | Lấy min khi nhập cạnh |
| Cộng INF như số thường | Tràn/ra kết quả giả | Chỉ cộng khi hai phần hữu hạn |
| Bỏ qua kiểm tra chu trình âm | Không còn d hữu hạn cho các cặp bị ảnh hưởng | Xét dist[v][v]<0 hoặc Bellman–Ford |
| Cache theo mọi truy vấn riêng lẻ | Lặp lại cùng một nguồn/đích nhiều lần | Gom theo đầu mối phân biệt |
| Không giữ next/parent nhưng đòi in đường | Chỉ có số khoảng cách | Lưu thông tin truy vết |
| Đếm thiếu chi phí trả n² kết quả APSP | Output bản thân có n² số | Dành bộ nhớ/thời gian Ω(n²) |
| Nhầm directed với undirected | Thiếu hoặc thừa cạnh ngược | Mô hình đúng theo đề |
| Cho rằng đồ thị có cạnh âm luôn sai | Cạnh âm không đồng nghĩa chu trình âm | Dùng thuật toán hỗ trợ cạnh âm |
| Không thử n=0, đỉnh cô lập, cạnh 0 | Có thể lỗi chỉ số hoặc INF | Kiểm tra hợp đồng và ca biên |

## 22. Bài tập thực hành

**Bài 1 — Phân biệt hai nghĩa nhiều nguồn:** với đồ thị có hướng 0→1 giá 4, 0→2 giá 1, 2→1 giá 2, 1→3 giá 1, 2→3 giá 7, 3→4 giá 3, 2→4 giá 20, hãy tính d(0,*) và d(2,*). Sau đó tính nearest(*) với S={0,2}. Giải thích vì sao chỉ mảng nearest chưa đủ để trả mọi câu hỏi từ nguồn 0.

**Bài 2 — Một đích cố định:** dùng đồ thị bài 1, dựng tất cả cạnh của G^R rồi chạy Dijkstra từ 4. Kiểm tra d_G(0,4)=7, d_G(1,4)=4, d_G(2,4)=6.

**Bài 3 — Quyết định cache:** cho 20.000 truy vấn nhưng chỉ có 7 nguồn và 600 đích phân biệt. Viết biểu thức thời gian cache theo nguồn; đổi giả thiết thành 600 nguồn và 7 đích, chứng minh vì sao đảo cạnh thường hợp lý hơn khi w≥0.

**Bài 4 — Floyd theo từng k:** với ba đỉnh và cạnh 0→1 giá 2, 1→2 giá −3, 0→2 giá 9, khởi tạo dist; chạy vòng k=0,1,2; ghi thay đổi ở dist[0][2] và dựng đường [0,1,2].

**Bài 5 — Johnson tái trọng số:** trên một đồ thị có cạnh âm không có chu trình âm, tự tính h bằng siêu nguồn, tính từng w' và kiểm chứng w'≥0. Tính d'(s,t) rồi đổi lại bằng d=d'−h[s]+h[t].

**Bài 6 — Chu trình âm và INF:** xây một đồ thị có một chu trình âm nằm trong thành phần không liên thông với s. Phân biệt câu hỏi d(s,t) riêng lẻ với yêu cầu APSP hữu hạn cho toàn bộ cặp; giải thích chính sách từ chối toàn cục của code.

**Bài 7 — Truy vết:** bổ sung predecessor khi chạy Dijkstra, dựng một đường từ s tới t, kiểm chứng tổng các trọng số trên đường bằng dist[t]. Nếu có nhiều đường hòa, hãy định nghĩa quy tắc chọn đường ổn định.

**Bài 8 — Đồ thị vô hướng:** chuyển bài 1 sang vô hướng bằng cách thêm hai cạnh có hướng cho mỗi cạnh vật lý. So sánh ma trận d(s,t) có còn bất đối xứng không. Thử đưa một cạnh âm và lý giải vì sao có thể tạo chu trình âm do đi hai chiều.

**Bài 9 — Benchmark:** sinh đồ thị thưa m≈n và dày m≈n² cho các n vừa phải. Đo chi phí Floyd, n lần Dijkstra và Johnson (khi không có chu trình âm). Đừng quên thời gian dựng đồ thị và bộ nhớ n² của APSP.

**Bài 10 — Trường hợp biên:** thử đồ thị không cạnh; hai cạnh song song cùng hướng nhưng trọng số khác nhau; self-loop bằng 0; đường đi rỗng s=t; danh sách nguồn rỗng; và truy vấn không thể tới. Mỗi trường hợp phải có kết quả được xác định trước khi chạy code.

**Kết luận:** giải **nhiều nguồn, nhiều đích và toàn bộ các cặp** không phải một phép lặp vô điều kiện của Dijkstra. Nếu chỉ cần nguồn gần nhất, khởi tạo nhiều nguồn; nếu cần nhiều nguồn tới một đích, đảo cạnh; nếu có nhiều cặp, cache theo số nguồn/đích phân biệt; nếu cần APSP, cân nhắc Floyd–Warshall, n lần Dijkstra hoặc Johnson theo mật độ và trọng số. Điều kiện **không âm**, **chu trình âm**, **INF**, bộ nhớ n² và khả năng **truy vết đường đi** là các yếu tố quyết định thuật toán đúng với đề và hoạt động đáng tin.
