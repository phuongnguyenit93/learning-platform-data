# Cây khung lớn nhất và thay đổi tiêu chí lựa chọn

**Cây khung lớn nhất (maximum spanning tree – MaxST)** là một cây dùng các cạnh của đồ thị vô hướng liên thông để nối tất cả đỉnh, không tạo chu trình, đồng thời làm **tổng trọng số được chọn lớn nhất**. Nó đối ngẫu với **cây khung nhỏ nhất (minimum spanning tree – MST)**, nơi tổng trọng số cần nhỏ nhất.

Nếu đồ thị không liên thông, không có một cây phủ toàn đồ thị. Khi đó ta tìm **rừng khung lớn nhất (maximum spanning forest – MaxSF)**: mỗi thành phần liên thông gốc được nối bằng một cây có tổng trọng số tối đa. Cả MaxST và MaxSF đều giải được bằng **Kruskal với cạnh theo trọng số giảm dần** hoặc **Prim với hàng đợi ưu tiên cạnh nặng nhất**.

Tuy nhiên, thay đổi tiêu chí lựa chọn không phải lúc nào cũng chỉ là đảo comparator. Bài này phân biệt rõ việc đổi từ **minimum sum sang maximum sum** với việc thêm ràng buộc bậc đỉnh, ngân sách, hướng cạnh, bottleneck hoặc mục tiêu nhiều cấp; các thay đổi ấy có thể làm chứng minh greedy không còn hiệu lực.

Bài học thuộc nhóm **Cây khung**. Bạn sẽ có khái niệm đầy đủ, ví dụ chứa cạnh âm/cạnh trùng/self-loop/đỉnh cô lập, chứng minh tính đúng bằng lát cắt và phép thay cạnh, triển khai **Java 17+ độc lập**, kiểm tra rừng khung, tìm maximum bottleneck path và đối chiếu Kruskal–Prim với oracle vét cạn trên **4.166 đồ thị vô hướng có trọng số**.

## 1. Định nghĩa và yêu cầu khung

Cho một đồ thị vô hướng `G=(V,E)` có `n` đỉnh, `m` cạnh và hàm trọng số `w:E→ℤ`. Có thể có cạnh âm, trọng số 0 hoặc cạnh song song.

Một **cây khung** `T⊆E` của đồ thị **liên thông** phải thỏa cả ba tính chất:

1. Mọi đỉnh thuộc cùng một thành phần liên thông trong `(V,T)`.
2. `T` không tạo chu trình.
3. Khi `n≥1`, `T` có đúng `n−1` cạnh.

Điều kiện 1 và 2 đã kéo theo điều kiện 3 với đồ thị hữu hạn; điều kiện 3 là một cách kiểm tra nhanh. Mục tiêu:

```text
maximize sum(weight(e)) over all valid spanning trees T
```

Đối với một đồ thị không liên thông có `c` thành phần gốc, rừng khung hợp lệ phải có đúng **`n−c` cạnh**, không chứa chu trình và bảo toàn **cùng phân hoạch liên thông** như graph gốc. MaxSF tối đa tổng trọng số trong tập những rừng như vậy.

Một thành phần chỉ có một đỉnh được biểu diễn bằng cây **không có cạnh**, tổng đóng góp 0. Với `n=0`, có thể quy ước rừng rỗng có 0 thành phần, 0 cạnh và tổng 0.

### Quan trọng: spanning khác rừng tùy ý

Đồ thị hai đỉnh 0,1 chỉ có cạnh trọng số `−5`. Cây khung của nó bắt buộc nhận cạnh này; tổng là `−5`. Trả hai đỉnh cô lập với tổng 0 không phải MaxST, vì nó **không nối được hai đỉnh vốn liên thông trong graph gốc**.

Do đó không được có quy tắc “dừng Kruskal khi trọng số ≤0” cho bài MaxST/MaxSF chuẩn. Nếu đề cho phép bỏ hẳn kết nối âm vì lợi nhuận, đó là một **bài toán chọn rừng khác** với yêu cầu spanning đã được thay đổi.

## 2. Đồ thị ví dụ có tất cả tình huống thường gặp

Xét graph `n=8` đỉnh 0..7, với cạnh vô hướng được cấp ID theo thứ tự xuất hiện:

| Edge ID | Hai đầu | Weight | Ghi chú |
| ---: | --- | ---: | --- |
| 0 | `0–1` | 8 | Cạnh mạnh |
| 1 | `0–2` | 8 | Cạnh mạnh |
| 2 | `1–2` | 6 | Có thể tạo chu trình |
| 3 | `1–3` | −2 | Trọng số âm |
| 4 | `2–3` | 7 | Nối đỉnh 3 |
| 5 | `2–4` | 4 | Nối đỉnh 4 |
| 6 | `3–4` | 0 | Trọng số bằng 0 |
| 7 | `0–4` | 3 | Cạnh thay thế |
| 8 | `0–1` | 8 | Song song ID 0 |
| 9 | `4–4` | 100 | Self-loop rất nặng |
| 10 | `5–6` | −5 | Cạnh bắt buộc cho 5 và 6 |
| 11 | `5–6` | −7 | Song song nhưng kém hơn ID 10 |

Đỉnh `7` không có cạnh nên là **đỉnh cô lập**. Graph gốc có ba thành phần:

```text
{0, 1, 2, 3, 4}
{5, 6}
{7}
```

Với `n=8,c=3`, rừng khung phải có `8−3=5` cạnh. Một lời giải MaxSF tối ưu:

```text
ID 0: 0--1, w= 8
ID 1: 0--2, w= 8
ID 4: 2--3, w= 7
ID 5: 2--4, w= 4
ID 10:5--6, w=-5

Total = 8 + 8 + 7 + 4 - 5 = 22
```

Cạnh tự khép `4–4` mang trọng số **100**, nhưng vẫn không được chọn vì nó tạo chu trình. Cạnh `5–6` trọng số âm **−5** lại bắt buộc, vì nếu bỏ nó thì hai đỉnh 5,6 không còn liên thông trong rừng.

Nếu đổi sang **minimum spanning forest** bằng thứ tự cạnh tăng dần, một lời giải là:

```text
IDs [11, 3, 6, 7, 5]
Weights [-7, -2, 0, 3, 4]

Minimum total = -7 -2 +0 +3 +4 = -2
```

Hai rừng cùng hợp lệ nhưng tối ưu cho **hai mục tiêu ngược nhau**: maximum tổng 22 và minimum tổng −2.

## 3. Kruskal lớn nhất: thay thứ tự ưu tiên, giữ DSU

**Kruskal** khởi đầu với rừng không cạnh. Nó xét các cạnh theo một thứ tự, chỉ nhận cạnh nối **hai nhóm chưa liên thông** trong rừng đã chọn. Để tìm MaxST/MaxSF, dùng **trọng số giảm dần**.

```text
maximumSpanningForest(graph):
    edges = sort by weight DESCENDING
    DSU = n singleton sets
    chosen = []
    total = 0

    for (u,v,w) in edges:
        if DSU.union(u,v) succeeds:
            chosen.add((u,v,w))
            total += w

    return chosen, total, DSU.componentCount
```

DSU (*Disjoint Set Union*, hay *Union-Find*) có:

- `find(x)`: trả đại diện nhóm đỉnh x;
- `union(u,v)`: gộp hai nhóm nếu chúng khác nhau, trả `true` khi thật sự có gộp;
- **Path compression** và **union by size**: giúp chi phí thao tác gần hằng số amortized (`O(α(n))`).

Nếu `find(u)==find(v)`, đã có đường trong rừng đang chọn từ u tới v. Thêm cạnh mới sẽ khép một chu trình, nên phải bỏ qua, bất kể trọng số.

### Chi tiết khác với MST nhỏ nhất

| Thành phần | Minimum Kruskal | Maximum Kruskal |
| --- | --- | --- |
| Thứ tự xét cạnh | Weight tăng dần | Weight giảm dần |
| Kiểm tra cycle | DSU không nhận cạnh cùng nhóm | **Giống hệt** |
| Số cạnh khi có c nhóm gốc | `n−c` | **`n−c`** |
| Cạnh có trọng số âm | Có thể chọn | Có thể chọn, kể cả bắt buộc |
| Độ phức tạp | `O(m log m)` chi phối | **Như nhau** |

Không cần thay DSU thành một cấu trúc mới. Sự khác biệt nằm ở **chiều chọn cạnh tốt nhất** theo mục tiêu tổng.

### Trọng số bằng nhau và ID cạnh

Khi hai cạnh có weight bằng nhau, có thể xét theo ID tăng để **đầu ra ổn định**:

```text
weight DESC;
when tied, edgeID ASC.
```

Kruskal với tie-break ấy tạo một kết quả xác định đối với cùng input. Nhưng điều đó **không chứng minh cây tối ưu là duy nhất**. Graph mẫu có hai cạnh `0–1` weight 8, ID 0 và 8, tạo **hai bộ edge ID tối ưu** khác nhau.

## 4. Prim lớn nhất bằng max-priority queue

**Prim** xây một cây bằng cách duy trì tập đỉnh đã nhận `S` và chọn cạnh **nặng nhất đi từ S ra ngoài S** (cạnh băng qua lát cắt). Thêm đầu đỉnh chưa nhận, rồi mở rộng frontier.

```text
maxPrimForest(graph):
    visited[0..n-1] = false
    selected = []

    for root = 0..n-1:
        if visited[root]: continue

        visited[root] = true
        PQ = max-heap of candidate edges from root

        while PQ not empty:
            e=(u,v,w) = pop maximum weight

            if both endpoints visited:
                continue  // stale edge; would create a cycle

            if exactly one endpoint visited:
                next = unvisited endpoint
                mark next visited
                selected.add(e)
                push edges from next to unvisited neighbors
```

Vòng `for root` là bắt buộc khi graph có thể **không liên thông**. Queue của thành phần hiện tại cạn trước khi chuyển sang root mới. Với đỉnh cô lập, thành phần được nhận nhưng không có cạnh.

### Cạm bẫy max-heap Java

`PriorityQueue` mặc định là min-heap. Với trọng số `long` có thể gần biên, **không** viết comparator:

```java
return (int) (b.weight() - a.weight());
```

Vì phép trừ overflow và phép ép int làm sai thứ tự. Cách an toàn:

```java
Comparator<Edge> MAX_ORDER = (a, b) -> {
    int c = Long.compare(b.weight(), a.weight());
    return c != 0 ? c : Integer.compare(a.id(), b.id());
};
```

Dấu đảo đối số trong `Long.compare(b.weight(),a.weight())` tạo thứ tự **nặng nhất trước**. Không dùng `-weight` vì `-Long.MIN_VALUE` không biểu diễn được trong `long`.

### Đừng chọn “cạnh nặng nhất quanh mỗi đỉnh” độc lập

Prim chọn cạnh tốt nhất **băng qua cut toàn bộ tập S đang xây**, chứ không chọn một cạnh nặng nhất riêng cho từng đỉnh rồi nối tùy ý. Chính cut mới giữ tính đúng toàn cục; lựa chọn độc lập theo từng đỉnh có thể tạo cycle hoặc một cấu trúc không tối ưu.

## 5. Chứng minh tối ưu bằng cut property

**Cut (lát cắt)** phân chia đỉnh thành hai phía `S` và `V\S`. Một cạnh có một đầu ở mỗi phía được gọi là **băng qua cut**.

**Maximum cut property:** Nếu cạnh `e` có trọng số **lớn nhất** trong các cạnh băng qua một cut, và cut phù hợp với các cạnh đã chọn trong quá trình dựng rừng, e là một **lựa chọn an toàn**: tồn tại cây/rừng khung tối ưu chứa các cạnh đã chọn và cả e.

### Chứng minh bằng phép thay cạnh

Giả sử `T` là một MaxST đang tối ưu và chưa chứa e. Thêm `e=(u,v)` vào T tạo đúng một **chu trình**. Trên chu trình có một cạnh khác `f` băng qua cut của e. Vì e là cạnh nặng nhất qua cut:

```text
w(e) >= w(f)
```

Bỏ f khỏi chu trình và giữ e tạo cây mới:

```text
T' = T + e - f
weight(T') = weight(T) + w(e) - w(f)
           >= weight(T)
```

Vì T đã đạt tổng lớn nhất, T' cũng tối ưu. Do đó thay cạnh không làm mất cơ hội đạt MaxST; ta được phép nhận e.

### Vì sao Kruskal chọn cạnh an toàn?

Khi Kruskal xem xét e nối hai nhóm DSU khác nhau, các cạnh có weight **lớn hơn** đã được xét. Một cạnh nặng hơn đang băng qua cut của nhóm chứa một đầu e đáng lẽ đã gộp hai nhóm khi được xét. Vì các nhóm vẫn khác nhau, e có thể được xem như cạnh tốt nhất còn phù hợp cho cut ấy và được nhận an toàn.

Lặp phép chọn này và không bao giờ nhận cạnh cùng DSU tạo một rừng có thể mở rộng thành tối ưu. Khi mọi cạnh đã xét, từng thành phần gốc đã được nối đủ thành cây, nên kết quả là MaxSF.

### Vì sao Prim cũng an toàn?

Ở Prim, `S` là tập đỉnh đã visited trong cây hiện tại. Max-heap chọn cạnh có trọng số lớn nhất nối S tới một đỉnh chưa visited. Đó là cạnh nặng nhất băng qua cut, nên an toàn theo cùng chứng minh. Khi một thành phần hết frontier, thuật toán bắt đầu cây mới ở thành phần khác.

**Chứng minh dựa trên tổng trọng số cộng theo cạnh và ràng buộc cây khung chuẩn.** Nếu đề thêm điều kiện về bậc, loại cạnh, số cạnh đặc biệt hay mục tiêu phi tuyến, không được tự dùng lại lập luận khi chưa kiểm tra.

## 6. Cycle property: cạnh nhẹ nhất duy nhất của chu trình

Một phát biểu đối ngẫu hữu ích:

> Trong một chu trình của graph vô hướng, nếu có một cạnh có trọng số **nhỏ nhất duy nhất**, cạnh ấy không thể thuộc một MaxST.

Nếu một MaxST chứa cạnh nhẹ nhất duy nhất `e` của chu trình, bỏ e sẽ chia cây thành hai phần. Một cạnh `f` khác trong chu trình phải nối hai phần ấy. Vì `w(f)>w(e)`, thay e bằng f tăng tổng, mâu thuẫn tối ưu.

Nếu có **nhiều cạnh cùng nhẹ nhất**, không được kết luận tất cả chúng bị cấm trong mọi MaxST. Ví dụ chu trình ba cạnh weight 5,5,5 có thể bỏ bất kỳ một cạnh và chọn hai cạnh còn lại.

Kruskal tự loại những cạnh khép chu trình với các cạnh đã nhận có weight **lớn hơn hoặc bằng**. Đây là một cách nhìn trực tiếp về tại sao ta không thể nhận mọi cạnh nặng, mà phải giữ yêu cầu không chu trình.

## 7. Trọng số âm, bằng 0, tự khép và đa cạnh

**Cạnh âm:** Không được loại chỉ vì âm. Trong thành phần gồm hai đỉnh có cạnh `−5` và `−7`, MaxST phải chọn `−5`, vì `−5>−7`. Nếu không chọn cạnh nào, không còn spanning.

**Cạnh trọng số 0:** Nếu nó cần để nối hai nhóm, vẫn phải chọn. Một cạnh trọng số 0 không giúp tăng tổng nhưng có thể là lựa chọn duy nhất để hoàn thành khung.

**Self-loop `u–u`:** Không nối hai đỉnh khác nhau. Trong Kruskal `union(u,u)` luôn thất bại; trong Prim cả hai đầu đã visited khi u được thăm, nên không phải cạnh băng qua cut. Self-loop weight cực lớn vẫn không hợp lệ.

**Cạnh song song:** Với hai cạnh cùng endpoint, sau khi chọn một cạnh thì cạnh còn lại nối các đỉnh đã cùng nhóm (Kruskal) hoặc có cả hai đầu visited (Prim). Khi hai cạnh có cùng weight tối ưu nhưng ID khác, ta có thể có **hai tập cạnh tối ưu khác nhau theo ID**.

**Đỉnh cô lập:** Là một thành phần có đúng một đỉnh và 0 cạnh. Đừng chỉ liệt kê các đỉnh xuất hiện trong danh sách cạnh; graph phải biết `n` ngay cả khi mọi cạnh đều vắng.

**Graph không liên thông:** Nếu đề yêu cầu MaxSF, tạo một cây riêng cho mỗi thành phần gốc. Nếu đề yêu cầu **một cây phủ toàn bộ**, phải báo không tồn tại khi `c>1`. Đừng trả MaxSF dưới tên một cây đơn nhất mà không nói rõ.

**Graph rỗng:** Với `n=0`, rừng rỗng có tổng 0 và 0 thành phần. Với `n=3` và `m=0`, có 3 thành phần, không có cạnh, tổng 0.

## 8. Nhiều nghiệm tối ưu và vai trò tie-break

Nếu tất cả trọng số cạnh **phân biệt**, cây khung tối ưu của graph liên thông là duy nhất. Nếu có trọng số bằng nhau, **có thể** có nhiều MaxST, nhưng việc hai cạnh bằng weight **không bắt buộc** tạo nhiều nghiệm.

Ví dụ tam giác với ba cạnh đều weight 5: chọn bất kỳ hai cạnh tạo cây tổng 10, nên có **ba** tập cạnh tối ưu.

Trong graph mẫu, ID 0 và 8 cùng nối 0–1 weight 8. Chọn ID 0 hoặc ID 8 cùng các cạnh khác đều cho tổng 22. Vét cạn xác minh có chính xác **2 maximum spanning forests theo bộ ID cạnh** trong ví dụ này.

Phân biệt:

- **Giá trị tối ưu:** một số (22 ở ví dụ).
- **Một nghiệm cụ thể:** một tập ID cạnh hoặc danh sách ID đã chọn.
- **Số nghiệm khác nhau theo ID cạnh:** đếm các tập con của `E` cùng tối ưu.
- **Số cấu trúc nối cặp đỉnh khác nhau:** có thể ít hơn nếu cạnh song song cùng endpoint được coi là tương đương.

Kruskal/Prim giải bài toán tối ưu giá trị và trả **một** nghiệm. Hai thuật toán có thể trả **hai bộ cạnh khác nhau** khi có hòa; chỉ so mảng edge ID không phải cách chứng minh một thuật toán sai. Cần kiểm tra rừng hợp lệ và tổng tối ưu.

Đếm toàn bộ MaxST/MaxSF trên graph lớn là bài toán riêng; không lấy số lần union hay số cạnh cùng weight làm số nghiệm. Có thể cần các kỹ thuật đếm cây với nhóm trọng số, trong khi brute force `2^m` chỉ thích hợp input rất nhỏ.

## 9. Maximum bottleneck: tính chất đường trên MaxST

Ngoài tối đa **tổng trọng số toàn cây**, MaxST còn hỗ trợ truy vấn **đường có năng lực nhỏ nhất trên đường là lớn nhất** (*widest path*, *maximum bottleneck path*).

Với một đường `P`, định nghĩa:

```text
bottleneck(P) = min(weight(e) for every edge e on P)

widest(u,v) = max over all u-v paths P of bottleneck(P)
```

**Định lý:** Nếu T là MaxST, đường duy nhất giữa `u` và `v` trên T có bottleneck đúng bằng `widest(u,v)` trong graph gốc. Với MaxSF, điều này đúng cho hai đỉnh cùng một thành phần gốc.

### Vì sao?

Chọn cạnh nhẹ nhất `e` trên đường T từ u tới v, có trọng số `b`. Bỏ e tách T thành hai phía chứa u và v riêng biệt. Bất kỳ đường u–v nào trong graph gốc đều phải băng qua cut ấy. Nếu có đường mà **mọi cạnh đều nặng hơn b**, trên đường đó có cạnh `f` băng qua cut với `w(f)>b`. Thay e bằng f sẽ tăng tổng MaxST, mâu thuẫn tối ưu. Vậy không đường nào có bottleneck vượt b; đường trên T đạt b nên tối ưu.

Ví dụ trong graph mẫu, đường T từ 1 tới 4 là `1–0–2–4` với các trọng số `8,8,4`. Bottleneck là **4**, và đó cũng là giá trị lớn nhất trong mọi đường giữa 1 và 4 của graph gốc.

### Maximum bottleneck spanning tree khác maximum total spanning tree

Một MaxST cũng là một **maximum bottleneck spanning tree** theo ý nghĩa tối đa trọng số nhỏ nhất trong cây. Nhưng chiều ngược **không luôn đúng**.

Ví dụ tam giác có cạnh weight 9,8,8. Cây 9+8 có tổng 17, bottleneck 8; cây 8+8 có tổng 16 nhưng bottleneck cũng 8. Vì vậy một cây tối ưu bottleneck chưa chắc tối ưu tổng.

Nếu đề yêu cầu **một đường widest giữa hai đỉnh**, có thể dùng đường trên MaxST hoặc một biến thể Dijkstra theo phép max-min. Nếu đề yêu cầu **một cây tối đa tổng**, phải dùng đúng mục tiêu MaxST; đừng chỉ tối đa cạnh yếu nhất rồi cho rằng tổng tự tối ưu.

## 10. Thay đổi tiêu chí lựa chọn: ba nhóm bài toán

### A. Chỉ đổi chiều tối ưu tổng trọng số

Tập nghiệm vẫn là **mọi cây khung vô hướng hợp lệ**; chỉ đổi:

```text
maximize sum(weight(e))
```

thành:

```text
minimize sum(weight(e))
```

Khi đó đủ thay thứ tự cạnh:

- **MaxST/MaxSF:** Kruskal sắp **giảm dần**, Prim max-heap.
- **MinST/MinSF:** Kruskal sắp **tăng dần**, Prim min-heap.

Phép chứng minh cut/exchange đổi “heaviest crossing cut” thành “lightest crossing cut”. Trong Java nên **đảo comparator** chứ không cần tính `−w`: với `Long.MIN_VALUE`, phép đổi dấu bị overflow.

### B. Thay hàm điểm cố định của từng cạnh

Nếu đề gán điểm `score(e)` độc lập cho mỗi cạnh rồi tối ưu `sum(score(e))` trên **cùng tập cây khung**, Kruskal/Prim vẫn có thể sắp theo score. Ví dụ score biểu diễn năng lực, mức quan trọng hoặc chất lượng kết nối được định nghĩa từ trước.

Nhưng nếu mục tiêu là **tích** các độ tin cậy xác suất, tổng xác suất không tương đương tích. Khi mô hình xác suất độc lập phù hợp, có thể chuyển tích các xác suất dương thành tổng log; phải giải thích và xác minh giả định trước. Nếu score của một cạnh thay đổi theo những cạnh đã chọn, mục tiêu **không còn cộng độc lập**, cut property chuẩn không tự chứng minh đúng.

Với **đa mục tiêu** như ưu tiên số cạnh loại A trước rồi mới tổng weight, không tự gộp vào một số bằng “hệ số thật lớn” nếu chưa chứng minh giới hạn dữ liệu, tránh overflow và bảo đảm thứ tự ưu tiên chính xác.

### C. Thay đổi tập nghiệm hợp lệ

Nếu thêm điều kiện:

- Bậc của mỗi đỉnh ≤2;
- Một đỉnh được phép có đúng một cạnh;
- Bắt buộc chọn/loại những nhóm cạnh cụ thể;
- Ngân sách hoặc hạn ngạch về loại cạnh;
- Cạnh có hướng và yêu cầu cây hướng từ root;

thì không còn bài MaxST chuẩn. Một comparator mới không sửa được việc **greedy có thể không còn an toàn**.

Ví dụ cây khung nối n đỉnh và có bậc mọi đỉnh ≤2 phải là **một đường Hamilton**; bài này phức tạp hơn nhiều so với MaxST không giới hạn bậc. Nếu graph có hướng, cần thuật toán **maximum arborescence** thay vì mặc định Kruskal/Prim vô hướng.

**Quy tắc chọn phương pháp:** Xác định trước **tập lời giải hợp lệ**, sau đó mới định nghĩa **hàm mục tiêu**, rồi mới lựa chọn/điều chỉnh thuật toán.

## 11. Độ phức tạp và bộ nhớ

Gọi n là số đỉnh, m là số cạnh vô hướng được lưu, kể cả cạnh trùng/self-loop.

| Thuật toán | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Kruskal với sort + DSU | `O(n+m log(m+1)+mα(n))` | `O(n+m)` nếu tạo bản sao cạnh để sort |
| Prim với adjacency list + max-heap | `O(n+m log(m+1))` | `O(n+m)` |
| Brute force mọi tập con cạnh | `O(2^m·poly(n,m))` | Phụ thuộc cách kiểm tra, chỉ dùng n,m rất nhỏ |
| Floyd max-min mọi cặp để test bottleneck | `O(n³)` | `O(n²)` |

Trong Kruskal, `α(n)` là nghịch đảo hàm Ackermann, tăng cực chậm. Sort cạnh thường là phần chi phối. Với Prim trên danh sách kề, mỗi cạnh vô hướng được lưu ở tối đa hai danh sách kề, và với cách chỉ push cạnh có một đầu chưa visited trong code, tối đa một bản ghi ứng viên hữu ích được tạo cho mỗi cạnh.

**Không dùng brute force trên graph lớn**: ngay m=40 đã có khoảng `2^40` tập con cạnh.

### Số cạnh đúng là n−c

DSU khởi tạo n nhóm, mỗi lần nhận một cạnh khác nhóm giảm số nhóm đi đúng 1. Sau khi xét toàn bộ cạnh, số nhóm bằng c của graph gốc, nên số cạnh nhận là **n−c**. Đây là bất biến kiểm tra nhanh nhưng chưa đủ: vẫn cần kiểm tra kết nối và chu trình.

### Tổng trọng số có thể overflow long

Ngay cả khi từng `w(e)` lưu được bằng `long`, tổng nhiều cạnh có thể không lưu được. Code mẫu dùng `Math.addExact` để báo `ArithmeticException` nếu tổng trung gian vượt miền số học. Khi bài yêu cầu tổng lớn hơn giới hạn, cần dùng `BigInteger` hoặc kiểu dữ liệu phù hợp, không im lặng wrap dấu.

Cũng không dùng `-Long.MIN_VALUE` hoặc phép trừ hai weight để viết comparator, vì có thể overflow. `Long.compare` giữ thứ tự đúng kể cả khi weight có giá trị cực tiểu/cực đại.

## 12. Java 17+ đầy đủ: maximum/minimum Kruskal, Prim và oracle

Lưu chương trình dưới đây thành **MaximumSpanningForestDemo.java**. Nó gồm:

- `Graph` vô hướng có n đỉnh và các cạnh `Edge(id,u,v,weight)`, cho phép cạnh song song, self-loop, weight âm/0.
- `DSU` có path compression và union-by-size.
- `kruskal(g,true)` tìm MaxSF; `kruskal(g,false)` tìm MinSF; comparator an toàn bằng `Long.compare`.
- `primMaximum` mở rộng theo cạnh biên nặng nhất và xử lý mọi thành phần, kể cả đỉnh cô lập.
- `verifyForest` kiểm chứng tập cạnh đã chọn không có chu trình, có đúng n−c cạnh, giữ connectivity gốc và tổng trọng số.
- `bruteMaximum` thử mọi tập con cạnh khi m≤20, trả tổng tối ưu và số bộ ID cạnh tối ưu.
- Hai oracle cho tính chất bottleneck: **Floyd max-min** trên graph gốc và bottleneck trên đường duy nhất trong rừng đã chọn.
- Bộ sinh **4.166 đồ thị vô hướng đơn có trọng số n≤4**, kiểm chứng Kruskal, Prim, brute và bottleneck; graph mẫu đa cạnh/self-loop được kiểm riêng.

### Toàn bộ mã nguồn

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class MaximumSpanningForestDemo {
    record Edge(int id, int u, int v, long weight) {}

    record Forest(long totalWeight, int components,
                  List<Edge> chosen) {}

    record Brute(long weight, long ways, int components) {}

    static final class Graph {
        final int n;
        final List<Edge> edges = new ArrayList<>();

        Graph(int n) {
            if (n < 0) {
                throw new IllegalArgumentException("n must be >= 0");
            }
            this.n = n;
        }

        void addEdge(int u, int v, long weight) {
            if (u < 0 || v < 0 || u >= n || v >= n) {
                throw new IllegalArgumentException("invalid endpoint");
            }
            edges.add(new Edge(edges.size(), u, v, weight));
        }
    }

    static final class DSU {
        final int[] parent, size;
        int parts;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            parts = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (parent[x] != x) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean unite(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }
            if (size[a] < size[b]) {
                int temp = a;
                a = b;
                b = temp;
            }
            parent[b] = a;
            size[a] += size[b];
            parts--;
            return true;
        }
    }

    static final Comparator<Edge> MAX_ORDER = (a, b) -> {
        int cmp = Long.compare(b.weight(), a.weight());
        return cmp != 0 ? cmp : Integer.compare(a.id(), b.id());
    };

    static final Comparator<Edge> MIN_ORDER = (a, b) -> {
        int cmp = Long.compare(a.weight(), b.weight());
        return cmp != 0 ? cmp : Integer.compare(a.id(), b.id());
    };

    // maximum=true: MaxSF; false: MinSF.
    static Forest kruskal(Graph graph, boolean maximum) {
        ArrayList<Edge> ordered = new ArrayList<>(graph.edges);
        ordered.sort(maximum ? MAX_ORDER : MIN_ORDER);

        DSU dsu = new DSU(graph.n);
        ArrayList<Edge> picked = new ArrayList<>();
        long total = 0;
        for (Edge e : ordered) {
            if (dsu.unite(e.u(), e.v())) {
                picked.add(e);
                total = Math.addExact(total, e.weight());
            }
        }
        return new Forest(total, dsu.parts, List.copyOf(picked));
    }

    static Forest primMaximum(Graph graph) {
        List<List<Edge>> adjacent = new ArrayList<>();
        for (int i = 0; i < graph.n; i++) {
            adjacent.add(new ArrayList<>());
        }
        for (Edge e : graph.edges) {
            adjacent.get(e.u()).add(e);
            if (e.u() != e.v()) {
                adjacent.get(e.v()).add(e);
            }
        }

        boolean[] visited = new boolean[graph.n];
        ArrayList<Edge> picked = new ArrayList<>();
        int components = 0;
        long total = 0;

        for (int root = 0; root < graph.n; root++) {
            if (visited[root]) {
                continue;
            }

            components++;
            visited[root] = true;
            PriorityQueue<Edge> frontier =
                new PriorityQueue<>(MAX_ORDER);

            for (Edge e : adjacent.get(root)) {
                int other = e.u() == root ? e.v() : e.u();
                if (!visited[other]) {
                    frontier.add(e);
                }
            }

            while (!frontier.isEmpty()) {
                Edge e = frontier.remove();
                boolean uSeen = visited[e.u()];
                boolean vSeen = visited[e.v()];

                if (uSeen == vSeen) {
                    // Both visited => stale; cannot join the cut.
                    continue;
                }

                int next = uSeen ? e.v() : e.u();
                visited[next] = true;
                picked.add(e);
                total = Math.addExact(total, e.weight());

                for (Edge out : adjacent.get(next)) {
                    int other = out.u() == next ? out.v() : out.u();
                    if (!visited[other]) {
                        frontier.add(out);
                    }
                }
            }
        }
        return new Forest(total, components, List.copyOf(picked));
    }

    static List<Integer> chosenIds(Forest forest) {
        ArrayList<Integer> ids = new ArrayList<>();
        for (Edge e : forest.chosen()) {
            ids.add(e.id());
        }
        return List.copyOf(ids);
    }

    // Structural oracle: chosen edges must span every original
    // component, be acyclic, and sum to recorded total.
    static void verifyForest(Graph graph, Forest forest) {
        DSU original = new DSU(graph.n);
        for (Edge e : graph.edges) {
            original.unite(e.u(), e.v());
        }

        if (forest.components() != original.parts
                || forest.chosen().size() != graph.n - original.parts) {
            throw new AssertionError("wrong forest edge count");
        }

        DSU selected = new DSU(graph.n);
        boolean[] used = new boolean[graph.edges.size()];
        long total = 0;

        for (Edge e : forest.chosen()) {
            if (e.id() < 0 || e.id() >= graph.edges.size()
                    || used[e.id()]
                    || !graph.edges.get(e.id()).equals(e)) {
                throw new AssertionError("bad edge ID");
            }
            used[e.id()] = true;
            if (!selected.unite(e.u(), e.v())) {
                throw new AssertionError("cycle");
            }
            total = Math.addExact(total, e.weight());
        }

        if (total != forest.totalWeight()) {
            throw new AssertionError("incorrect total");
        }
        for (int u = 0; u < graph.n; u++) {
            for (int v = 0; v < graph.n; v++) {
                if ((original.find(u) == original.find(v))
                        != (selected.find(u) == selected.find(v))) {
                    throw new AssertionError("does not span component");
                }
            }
        }
    }

    // Independent exhaustive oracle; m <= 20 edges only.
    static Brute bruteMaximum(Graph graph) {
        int m = graph.edges.size();
        if (m > 20) {
            throw new IllegalArgumentException("too many edges");
        }

        DSU original = new DSU(graph.n);
        for (Edge e : graph.edges) {
            original.unite(e.u(), e.v());
        }
        int required = graph.n - original.parts;

        boolean found = false;
        long best = 0;
        long ways = 0;
        for (int mask = 0; mask < (1 << m); mask++) {
            if (Integer.bitCount(mask) != required) {
                continue;
            }

            DSU chosen = new DSU(graph.n);
            boolean cycle = false;
            long total = 0;
            for (int i = 0; i < m; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                Edge e = graph.edges.get(i);
                if (!chosen.unite(e.u(), e.v())) {
                    cycle = true;
                    break;
                }
                total = Math.addExact(total, e.weight());
            }

            if (cycle || chosen.parts != original.parts) {
                continue;
            }
            boolean sameGroups = true;
            for (int u = 0; u < graph.n && sameGroups; u++) {
                for (int v = 0; v < graph.n; v++) {
                    if ((original.find(u) == original.find(v))
                            != (chosen.find(u) == chosen.find(v))) {
                        sameGroups = false;
                        break;
                    }
                }
            }
            if (!sameGroups) {
                continue;
            }

            if (!found || total > best) {
                found = true;
                best = total;
                ways = 1;
            } else if (total == best) {
                ways++;
            }
        }

        if (!found) {
            throw new AssertionError("no spanning forest found");
        }
        return new Brute(best, ways, original.parts);
    }

    // Floyd max-min oracle for widest bottleneck paths.
    // null represents unreachable; diagonal is +infinity.
    static Long[][] widestAllPairs(Graph graph) {
        Long[][] capacity = new Long[graph.n][graph.n];
        for (int v = 0; v < graph.n; v++) {
            capacity[v][v] = Long.MAX_VALUE;
        }

        for (Edge e : graph.edges) {
            int u = e.u(), v = e.v();
            if (u == v) {
                continue;
            }
            if (capacity[u][v] == null
                    || e.weight() > capacity[u][v]) {
                capacity[u][v] = e.weight();
                capacity[v][u] = e.weight();
            }
        }

        for (int k = 0; k < graph.n; k++) {
            for (int i = 0; i < graph.n; i++) {
                for (int j = 0; j < graph.n; j++) {
                    if (capacity[i][k] == null
                            || capacity[k][j] == null) {
                        continue;
                    }
                    long via = Math.min(
                        capacity[i][k], capacity[k][j]);
                    if (capacity[i][j] == null
                            || via > capacity[i][j]) {
                        capacity[i][j] = via;
                    }
                }
            }
        }
        return capacity;
    }

    // Independent bottleneck traversal over the selected forest.
    static Long[][] treeBottlenecks(int n, List<Edge> chosen) {
        List<List<Edge>> adj = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            adj.add(new ArrayList<>());
        }
        for (Edge e : chosen) {
            adj.get(e.u()).add(e);
            adj.get(e.v()).add(e);
        }

        Long[][] result = new Long[n][n];
        for (int root = 0; root < n; root++) {
            boolean[] seen = new boolean[n];
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            seen[root] = true;
            result[root][root] = Long.MAX_VALUE;
            queue.addLast(root);

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (Edge e : adj.get(u)) {
                    int v = e.u() == u ? e.v() : e.u();
                    if (!seen[v]) {
                        seen[v] = true;
                        result[root][v] = Math.min(
                            result[root][u], e.weight());
                        queue.addLast(v);
                    }
                }
            }
        }
        return result;
    }

    static void verifyGraph(Graph graph) {
        Forest a = kruskal(graph, true);
        Forest b = primMaximum(graph);
        Brute expected = bruteMaximum(graph);

        verifyForest(graph, a);
        verifyForest(graph, b);

        if (a.totalWeight() != expected.weight()
                || b.totalWeight() != expected.weight()
                || a.components() != expected.components()
                || b.components() != expected.components()) {
            throw new AssertionError("wrong maximum total");
        }

        Long[][] widest = widestAllPairs(graph);
        Long[][] onTree = treeBottlenecks(
            graph.n, a.chosen());
        for (int u = 0; u < graph.n; u++) {
            for (int v = 0; v < graph.n; v++) {
                if (!Objects.equals(widest[u][v], onTree[u][v])) {
                    throw new AssertionError("wrong widest bottleneck");
                }
            }
        }
    }

    // All simple undirected weighted graphs n=0..4.
    // Each pair u<v: absent, weight -2, 0, or 3.
    static int verifyAllSmallGraphs() {
        int checked = 0;
        for (int n = 0; n <= 4; n++) {
            ArrayList<int[]> pairs = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    pairs.add(new int[]{u, v});
                }
            }

            int variants = 1;
            for (int i = 0; i < pairs.size(); i++) {
                variants *= 4;
            }

            for (int code = 0; code < variants; code++) {
                Graph graph = new Graph(n);
                int remaining = code;
                for (int[] pair : pairs) {
                    int kind = remaining % 4;
                    remaining /= 4;
                    if (kind != 0) {
                        long weight = kind == 1 ? -2L
                                    : kind == 2 ? 0L : 3L;
                        graph.addEdge(pair[0], pair[1], weight);
                    }
                }
                verifyGraph(graph);
                checked++;
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        Graph sample = new Graph(8);
        long[][] edgeData = {
            {0,1,8}, {0,2,8}, {1,2,6}, {1,3,-2},
            {2,3,7}, {2,4,4}, {3,4,0}, {0,4,3},
            {0,1,8}, {4,4,100}, {5,6,-5}, {5,6,-7}
        };
        for (long[] e : edgeData) {
            sample.addEdge((int) e[0], (int) e[1], e[2]);
        }

        Forest maximum = kruskal(sample, true);
        Forest prim = primMaximum(sample);
        Forest minimum = kruskal(sample, false);
        Brute brute = bruteMaximum(sample);

        System.out.println(
            "Max Kruskal: weight=" + maximum.totalWeight()
            + ", components=" + maximum.components()
            + ", ids=" + chosenIds(maximum));
        System.out.println(
            "Max Prim: weight=" + prim.totalWeight()
            + ", components=" + prim.components()
            + ", ids=" + chosenIds(prim));
        System.out.println(
            "Min Kruskal: weight=" + minimum.totalWeight()
            + ", ids=" + chosenIds(minimum));
        System.out.println(
            "Optimal edge-ID forests (brute): " + brute.ways());
        System.out.println(
            "Widest bottleneck 1 to 4: "
            + widestAllPairs(sample)[1][4]);

        Graph empty = new Graph(0);
        System.out.println(
            "Empty graph: weight=" + kruskal(empty, true).totalWeight()
            + ", components=" + primMaximum(empty).components());

        Graph isolated = new Graph(3);
        System.out.println(
            "No edges n=3: components="
            + kruskal(isolated, true).components());

        Graph extreme = new Graph(2);
        extreme.addEdge(0, 1, Long.MIN_VALUE);
        System.out.println(
            "Long.MIN_VALUE edge retained: "
            + (kruskal(extreme, true).totalWeight()
               == Long.MIN_VALUE));

        verifyGraph(sample);
        System.out.println(
            "Exhaustive weighted graphs n<=4: "
            + verifyAllSmallGraphs() + " OK");
    }
}
```

### Lệnh biên dịch và chạy

Cần **JDK 17 hoặc mới hơn** vì ví dụ dùng `record`.

```bash
javac -encoding UTF-8 MaximumSpanningForestDemo.java
java MaximumSpanningForestDemo
```

**Stdout dự kiến:**

```text
Max Kruskal: weight=22, components=3, ids=[0, 1, 4, 5, 10]
Max Prim: weight=22, components=3, ids=[0, 1, 4, 5, 10]
Min Kruskal: weight=-2, ids=[11, 3, 6, 7, 5]
Optimal edge-ID forests (brute): 2
Widest bottleneck 1 to 4: 4
Empty graph: weight=0, components=0
No edges n=3: components=3
Long.MIN_VALUE edge retained: true
Exhaustive weighted graphs n<=4: 4166 OK
```

### Giải thích stdout

- **Max Kruskal** và **Max Prim** đều đạt tổng 22 và nhận 5 cạnh. Trong ví dụ có quy tắc ID và root tăng dần, chúng tình cờ chọn cùng danh sách ID `[0,1,4,5,10]`. Trên input khác có hòa, danh sách có thể khác mà vẫn đúng.
- **Min Kruskal** có tổng −2 do đổi chiều trọng số, không phải do lỗi DSU.
- **Brute 2:** có hai bộ ID cạnh MaxSF tối ưu, khác lựa chọn ID 0/8 có cùng endpoint và weight.
- **Widest 4:** đường trên MaxST giữa 1 và 4 có cạnh yếu nhất weight 4, trùng kết quả Floyd max-min độc lập.
- **Empty graph** có 0 thành phần, trong khi graph 3 đỉnh không cạnh có 3 thành phần.
- **Long.MIN_VALUE** vẫn có thể là cạnh bắt buộc của cây khung hai đỉnh; code không phủ định weight.
- **Exhaustive 4166** xác minh cấu trúc forest, tổng so với brute, và widest bottleneck cho mọi cặp đỉnh trong từng graph nhỏ.

## 13. Kiểm thử độc lập: tại sao cần hơn một thuật toán?

Để kiểm tra một kết quả MaxSF, việc Kruskal và Prim cho **cùng tổng** chưa đủ chắc chắn nếu cả hai cùng triển khai sai một giả định. Code vì thế có oracle **bruteMaximum** không dùng thứ tự Kruskal hoặc frontier Prim để tính optimum.

### Brute force đúng theo tập nghiệm gốc

Với m cạnh nhỏ, liệt kê các tập con của E:

```text
for each subset of edges:
    if edgeCount != n - originalComponentCount:
        skip
    if subset contains a cycle:
        skip
    if subset fails to connect each original component:
        skip

    maximize totalWeight(subset)
```

Đây là phép kiểm tra trực tiếp đặc tả “rừng phủ đúng từng thành phần gốc, không chu trình, tổng lớn nhất”. Những cạnh song song có ID riêng được xem là **hai lựa chọn tập con khác nhau**.

### Tập exhaustive 4.166 graph

Với n đỉnh, có `n(n−1)/2` cặp vô hướng khác nhau. Mỗi cặp có bốn trạng thái: **không có cạnh, trọng số −2, trọng số 0, trọng số 3**. Vì thế số graph ở mỗi n là:

```text
n=0: 4^0 =    1
n=1: 4^0 =    1
n=2: 4^1 =    4
n=3: 4^3 =   64
n=4: 4^6 = 4096

Tổng:       4166 graph
```

Mỗi graph được kiểm bằng ba hướng:

1. **Kruskal giảm dần**;
2. **Prim max-heap**;
3. **Brute force** chọn tập con tốt nhất.

Sau đó code đối chiếu riêng **bottleneck của đường trên rừng Kruskal** với **Floyd max-min** trên graph gốc. Kết quả được so theo **giá trị và tính hợp lệ**, không ép hai thuật toán phải trả cùng bộ ID khi có hòa.

Tập exhaustive là **graph đơn** (không tự khép/không cạnh song song) để giới hạn số trường hợp. Graph mẫu có cạnh song song và self-loop được kiểm bằng brute riêng. Kiểm thử hữu hạn không thay thế chứng minh cut/exchange tổng quát, nhưng giúp phát hiện sai sót comparator, negative handling, component count, cycle và tie-break.

### Phân biệt oracle kiểm thử với thuật toán chạy thật

Brute force có `2^m` tập con và chỉ phù hợp input nhỏ (code giới hạn 20 cạnh). Floyd max-min dùng `O(n³)`, cũng chủ yếu để đối chiếu hoặc khi số đỉnh nhỏ. Với đồ thị lớn, lời giải chính là Kruskal/Prim có độ phức tạp gần `O(m log m)`.

Không dùng code brute trực tiếp trong hệ thống thật có hàng trăm nghìn cạnh.

## 14. Một số trường hợp biên và giới hạn API

**n=0:** Rừng rỗng, weight 0, components 0. Không có cây khung thông thường.

**n=1:** Một đỉnh là một cây 0 cạnh, weight 0. Nếu có self-loop trên nó, self-loop vẫn không được chọn.

**Không có cạnh:** Với n đỉnh, có n thành phần một đỉnh. Forest tối ưu có 0 cạnh, tổng 0.

**Graph chỉ có cạnh âm:** Nếu các đỉnh gốc liên thông qua cạnh âm, MaxSF vẫn phải dùng đủ cạnh để nối tất cả nhóm. Chọn phương án âm **ít thiệt hại nhất trong số các cây hợp lệ**, không bỏ toàn bộ cạnh.

**Cạnh song song khác weight:** Giữa hai đỉnh chỉ có cạnh −5 và −7, maximum chọn −5, minimum chọn −7. Nếu có nhiều nhóm/cycle khác, lựa chọn vẫn cần tuân theo quy tắc toàn cục.

**Self-loop cực lớn:** Không được nhận. Trong graph mẫu, edge ID 9 weight 100 bị loại, không làm weight tối ưu thành 122.

**Cùng tổng nhưng khác cạnh:** Không ép kết quả Kruskal/Prim giống nhau; kiểm nghiệm tổng và thuộc tính forest.

**Trọng số Long.MIN_VALUE:** Comparator phải an toàn, không dùng phép đổi dấu. Tổng có thể hợp lệ nếu chỉ một cạnh weight cực âm; khi cộng nhiều cạnh khiến overflow, `Math.addExact` từ chối.

**Tổng không chứa được trong long:** Đây là giới hạn biểu diễn; cần `BigInteger` nếu input cho phép tổng vượt miền. Không đánh dấu thuật toán graph sai chỉ vì kiểu số chọn chưa đủ.

**Graph có hướng:** Nếu hướng thực sự quan trọng, cây khung vô hướng không đúng bài toán; cần mô hình arborescence và thuật toán tương ứng.

**Input động:** Nếu thêm/xóa cạnh sau khi đã dựng MaxST, kết quả cũ có thể không tối ưu. Có thể tính lại Kruskal/Prim; cấu trúc dữ liệu động là hướng nghiên cứu riêng, không chỉ giữ DSU cũ rồi bỏ qua cập nhật.

## 15. Lỗi phổ biến

1. **Đổi max thành min trong comparator:** Kết quả tổng nhỏ nhất thay vì lớn nhất.
2. **Bỏ các cạnh âm:** Forest không còn phủ một thành phần gốc.
3. **Bỏ các cạnh 0:** Một nhóm có thể không được nối, dù tổng không tăng.
4. **Nhận self-loop weight lớn:** Vi phạm không chu trình.
5. **Chọn mọi cạnh rất nặng:** Có thể tạo cycle; DSU/visited vẫn là điều kiện cần.
6. **Dùng `n−1` cạnh khi graph không liên thông:** Forest đúng có `n−c` cạnh.
7. **Chỉ gọi Prim từ root 0:** Bỏ sót thành phần khác, đặc biệt đỉnh cô lập.
8. **Không bỏ stale edge trong Prim:** Chọn cạnh đã có cả hai đầu visited và gây cycle.
9. **Tưởng Prim chọn cạnh lớn nhất của từng đỉnh:** Cạnh phải băng qua **cut của tập đỉnh đã xây**, không phải chỉ là cực đại cục bộ tùy ý.
10. **So weight bằng phép trừ rồi ép int:** Có thể overflow và sai thứ tự.
11. **Dùng `−Long.MIN_VALUE` để tái sử dụng MinST:** Overflow số học.
12. **Không kiểm overflow tổng:** Có thể nhận kết quả âm giả từ tổng lớn dương.
13. **Đếm hai cạnh song song như một khi yêu cầu đếm bộ edge ID:** Làm sai số nghiệm.
14. **Đếm bộ edge ID như số cấu trúc nối các cặp đỉnh khác nhau:** Dễ đánh giá thừa số nghiệm.
15. **Bắt buộc Kruskal và Prim có cùng danh sách cạnh:** Với tie, nhiều cây khác nhau vẫn tối ưu.
16. **Cho rằng mọi maximum bottleneck tree cũng là maximum total tree:** Chiều ngược không đúng.
17. **Dùng greedy cây khung cho ràng buộc thêm:** Giới hạn bậc, màu, ngân sách có thể phá tính chất cut.
18. **Áp Kruskal vô hướng cho graph hướng:** Có thể bỏ qua những điều kiện định hướng thiết yếu.
19. **Chỉ kiểm số cạnh mà không kiểm liên thông/cycle:** Tổng có thể đúng tình cờ nhưng cấu trúc không hợp lệ.
20. **Không phân biệt “một cây” với “một rừng”:** Khi graph disconnected, bài toán đầu ra thay đổi đáng kể.

## 16. Bài tập thực hành

**Bài 1 — Tam giác:** Ba cạnh weight 9,8,1. Tìm maximum/minimum spanning tree và giải thích vì sao chúng dùng tập cạnh khác nhau.

**Bài 2 — Âm bắt buộc:** Hai đỉnh, một cạnh −5. Vì sao maximum tree có total −5, không phải 0?

**Bài 3 — Forest:** Graph gồm 5 đỉnh cùng nhóm, 2 đỉnh cùng nhóm và một đỉnh cô lập. Hãy xác định n, c, số cạnh một forest hợp lệ.

**Bài 4 — Kruskal trace:** Trên graph mục 2, sort cạnh giảm dần; ghi thứ tự DSU nhận/từ chối từng edge ID, đặc biệt self-loop 9 và cạnh âm 10.

**Bài 5 — Prim trace:** Bắt đầu từ 0, ghi frontier sau khi thăm từng đỉnh. Vì sao phải bỏ cạnh có cả hai đầu visited?

**Bài 6 — Tie:** Tìm hai edge-ID forests tối ưu trên graph mục 2 bằng cách thay ID 0 với ID 8. So tổng và số cách nếu coi các bản sao cạnh là tương đương.

**Bài 7 — Cut proof:** Chọn một cut của graph và chứng minh thay một cạnh nhẹ qua cut bằng cạnh nặng nhất vẫn giữ hoặc tăng tổng.

**Bài 8 — Cycle proof:** Chứng minh cạnh có weight nhỏ nhất duy nhất trên một chu trình không nằm trong MaxST. Nếu có nhiều cạnh cùng nhẹ nhất thì sao?

**Bài 9 — Bottleneck:** Tam giác 9,8,8 có hai cây cùng bottleneck 8 nhưng tổng khác nhau. Giải thích tối đa bottleneck không đồng nghĩa tối đa tổng.

**Bài 10 — Thay trọng số:** Nếu mỗi cạnh có capacity và latency, khi nào dùng MaxST theo capacity, khi nào dùng MinST theo latency? Vì sao không thể tự trộn hai mục tiêu mà không định nghĩa thứ tự ưu tiên?

**Bài 11 — Comparator:** Tạo graph có cạnh `Long.MIN_VALUE` và `Long.MAX_VALUE`; dùng `Long.compare` để xếp đúng, tránh đổi dấu/trừ.

**Bài 12 — Brute oracle:** Với n≤4, sinh đồ thị có trọng số −2,0,3; thử mọi tập con cạnh để đối chiếu tổng với Kruskal/Prim.

**Bài 13 — Widest path nhiều truy vấn:** Tiền xử lý cây MaxST bằng LCA/binary lifting, lưu min weight trên đường nhảy để trả bottleneck u–v; kiểm tra cùng thành phần trước.

**Bài 14 — Ràng buộc bậc:** Đưa ra graph mà MaxST có đỉnh bậc lớn hơn 2. Tại sao không thể chỉ chạy Kruskal rồi xóa cạnh vi phạm mà vẫn bảo đảm đáp án tối ưu?

**Bài 15 — Cạnh 0 và disconnected:** Dựng graph một thành phần chỉ nối được qua cạnh 0, cùng một đỉnh cô lập. So forest tối ưu với trường hợp bỏ cạnh 0 tùy tiện.

## 17. Checklist hoàn thành

1. Graph **vô hướng** hay có hướng?
2. Đề muốn **tree** (phải liên thông) hay **forest** khi graph disconnected?
3. Mục tiêu là **maximum sum**, minimum sum, bottleneck hay một điều kiện khác?
4. Có đủ n đỉnh, kể cả đỉnh cô lập?
5. Nếu MaxST/MaxSF, đã sort trọng số **giảm dần** hoặc dùng **max-heap**?
6. Có DSU/visited chống cycle, đặc biệt self-loop?
7. Cạnh âm và bằng 0 có được giữ khi bắt buộc để spanning?
8. Cạnh song song/tie có ID và quy tắc kết quả rõ ràng?
9. Nếu graph có c thành phần, số cạnh được chọn có bằng `n−c`?
10. Forest có đúng phân hoạch liên thông của graph gốc?
11. Tổng weight được tính bằng kiểu số đủ rộng, không overflow âm thầm?
12. Comparator có dùng `Long.compare` thay vì trừ weight/đổi dấu?
13. Có chứng minh lựa chọn bằng **cut/exchange property**?
14. Nếu đã thêm điều kiện mới, có kiểm tra giả thiết greedy còn đúng không?
15. Có phân biệt total maximum với maximum bottleneck?
16. Có test graph rỗng, không cạnh, nhiều thành phần, self-loop, cạnh trùng, âm, 0, tie và biên `long`?
17. Với input nhỏ, đã kiểm chứng tổng bằng oracle vét cạn và bottleneck bằng phương pháp độc lập?

**Tiêu chí hoàn thành:** Bạn có thể giải thích, chứng minh và cài đặt **maximum spanning tree/forest** bằng Kruskal giảm dần hoặc Prim max-heap; xử lý graph không liên thông, trọng số âm, bằng 0, self-loop và cạnh song song; hiểu khi nào **đổi tiêu chí** chỉ cần đảo comparator và khi nào thay đổi ràng buộc buộc phải dùng thuật toán khác; đồng thời hiểu vì sao đường trên MaxST mang tính chất **widest bottleneck path**.
