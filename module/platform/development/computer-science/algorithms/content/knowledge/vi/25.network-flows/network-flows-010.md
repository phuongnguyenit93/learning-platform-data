# Ràng buộc sức chứa trên đỉnh và kỹ thuật tách đỉnh

Trong bài toán **luồng mạng (network flow)** thông thường, mỗi **cung** u→v có sức chứa c(u,v): lượng luồng đi qua cung không được vượt c(u,v). Tuy nhiên, nhiều tình huống thực tế còn giới hạn tổng lượng luồng có thể **đi qua một đỉnh**: trạm trung chuyển chỉ xử lý được 3 đơn vị mỗi giờ, máy chủ chỉ tiếp nhận được 10 yêu cầu đồng thời, hoặc mỗi vị trí trung gian chỉ được một đường đi sử dụng.

**Kỹ thuật tách đỉnh (vertex splitting / node splitting)** chuyển một ràng buộc sức chứa trên đỉnh thành **một cạnh có sức chứa**, để tiếp tục dùng thuật toán luồng cực đại quen thuộc như Edmonds–Karp, Dinic hoặc Push–Relabel mà không phải sửa định lý max-flow/min-cut.

Tư tưởng cốt lõi:

- Thay mỗi đỉnh v bằng hai nút **v_in** và **v_out**.
- Thêm cung **v_in → v_out** có sức chứa bằng giới hạn tại đỉnh v.
- Thay mỗi cung gốc **u → v** thành cung **u_out → v_in**, **giữ nguyên sức chứa cạnh**.
- Chọn nguồn/đích của mạng đã tách theo đúng yêu cầu có hay không giới hạn sức chứa ở hai đầu.
- Chạy max flow trên mạng mới. Giá trị nhận được chính là luồng cực đại thỏa **đồng thời** các ràng buộc cạnh và đỉnh của mạng gốc.

Bài học này tập trung vào mô hình **đồ thị có hướng, sức chứa không âm**, chứng minh biến đổi tương đương, cách chọn nguồn/đích, xây dựng đường đi rời nhau qua đỉnh, giải thích min-cut, ví dụ và chương trình **Java 17+ dùng Dinic**. Phần cuối có bộ kiểm thử độc lập bằng **liệt kê mọi cut** trên mạng đã tách và **vét cạn phân phối luồng nguyên** trên đồ thị gốc nhỏ.

## 1. Mô hình luồng mạng và ràng buộc tại đỉnh

Cho đồ thị có hướng G=(V,E), nguồn s và đích t với s≠t.

Mỗi cung e=(u,v) có sức chứa **c_e ≥ 0**. Luồng f(e) phải thỏa:

**0 ≤ f(e) ≤ c_e.**

Với mỗi **đỉnh trung gian** v không phải s,t, điều kiện bảo toàn luồng là:

**tổng luồng đi vào v = tổng luồng đi ra v.**

Giá trị luồng bằng:

**|f| = tổng luồng ra s − tổng luồng vào s**,

và cũng bằng tổng luồng vào t trừ tổng luồng ra t.

Trong mạng có sức chứa **trên đỉnh**, mỗi v còn có giới hạn **b_v ≥ 0**. Với một đỉnh trung gian v, ta yêu cầu:

**tổng luồng đi vào v ≤ b_v**.

Do bảo toàn, điều kiện này tương đương:

**tổng luồng đi ra v ≤ b_v**.

Đây là giới hạn **tổng lưu lượng** qua v, không phải giới hạn **riêng từng cạnh kề**.

### Ví dụ nút nghẽn

~~~text
           cap(1->2)=10
      1 ----------------> 2 ----------------> 4
      s                 capVertex[2]=3         t
                        cap(2->4)=10
~~~

Hai cung có sức chứa 10, nhưng đỉnh 2 chỉ xử lý được 3 đơn vị. Vì vậy đáp án đúng là **3**, không phải 10.

Nếu chỉ chạy max flow thông thường và bỏ qua sức chứa đỉnh, thuật toán sẽ trả 10, vi phạm yêu cầu.

### Có thể có cạnh âm hoặc sức chứa âm?

Trong **max flow chuẩn**, sức chứa **không âm**. Trọng số âm thường xuất hiện ở bài **min-cost flow** dưới dạng **chi phí**, không phải sức chứa. Nếu đề cho chi phí trên cạnh, cần giữ riêng đại lượng cost với đại lượng capacity.

Kỹ thuật tách đỉnh xử lý sức chứa. Nó không tự giải bài toán chi phí nhỏ nhất, và chương trình minh họa từ chối sức chứa âm.

## 2. Tại sao không thể chỉ sửa sức chứa từng cung kề?

Giả sử v nhận luồng từ hai đỉnh a,b và gửi luồng ra c:

~~~text
a --(5)--> v --(10)--> c
b --(5)--> v
vertexCapacity[v] = 6
~~~

Nếu thay sức chứa **mỗi cung đi vào v** thành min(cung,6), ta vẫn có thể gửi 5 từ a và 5 từ b, tổng 10 qua v, vượt giới hạn 6.

Nếu thay sức chứa **mỗi cung đi ra v** thành min(cung,6), tổng của nhiều cung đi ra cũng vẫn có thể vượt 6.

Ràng buộc trên đỉnh là **một ràng buộc chung** đối với mọi cung kề, không phải ràng buộc độc lập cho từng cung. Ta cần tạo một **điểm nghẽn duy nhất** mà mọi đơn vị đi qua v đều phải vượt qua.

**Cung v_in → v_out chính là điểm nghẽn duy nhất ấy.**

## 3. Biến đổi v thành v_in và v_out

Với mỗi đỉnh gốc v, tạo hai nút mới:

**v_in** — nơi các cung đi vào đỉnh v kết thúc.

**v_out** — nơi các cung đi ra đỉnh v bắt đầu.

Thêm cung nội bộ:

**v_in → v_out, capacity = b_v.**

Với mỗi cung gốc (u,v,c), thay bằng:

**u_out → v_in, capacity = c.**

Minh họa:

~~~text
Mang goc:

s --(8)--> v --(9)--> t
            b_v = 3

Sau khi tach:

s_out --(8)--> v_in --(3)--> v_out --(9)--> t_in
                       ^
             cung gioi han suc chua dinh
~~~

Toàn bộ luồng muốn đi từ các cung vào v sang các cung ra v phải đi qua **v_in→v_out**, nên tổng không vượt 3.

Nếu một đỉnh không có giới hạn sức chứa, có thể đặt cung nội bộ **v_in→v_out** có dung lượng **INF an toàn**, lớn hơn mọi giá trị luồng khả thi cần xét.

### Số nút và số cung sau biến đổi

Nếu mạng gốc có n đỉnh và m cung:

- Mạng tách có **2n nút**.
- Có **n cung nội bộ** v_in→v_out.
- Có **m cung mô phỏng các cung gốc** u_out→v_in.
- Tổng **n+m cung trước khi thêm cạnh ngược residual**.

Vì vậy kích thước đầu vào sau biến đổi vẫn **O(n+m)**. Kỹ thuật này chỉ tăng kích thước mạng theo hệ số tuyến tính, không phải O(n²).

### Đánh chỉ số bằng mảng 0-based

Với nhãn đỉnh gốc v từ 1 đến n, có thể mã hóa:

**in(v) = 2·(v−1)**

**out(v) = 2·(v−1)+1**.

Ví dụ:

| Đỉnh gốc | in(v) | out(v) |
| ---: | ---: | ---: |
| 1 | 0 | 1 |
| 2 | 2 | 3 |
| 3 | 4 | 5 |
| 4 | 6 | 7 |

Việc dùng hai chỉ số tách biệt giúp tránh nhầm **sức chứa cạnh gốc** với **sức chứa đỉnh** khi viết code.

## 4. Mạng tách xử lý đồng thời sức chứa cạnh và đỉnh

Xét mạng:

~~~text
s=1            2 (vertex cap=2)
  \           / \ 
   \(edge 5) /   \ (edge 5)
    -------> 2     -------> t=4

   \(edge 5)       (edge 5)
    -------> 3     -------> t=4
               (vertex cap=1)
~~~

Các cung gốc:

~~~text
1 -> 2 capacity 5
1 -> 3 capacity 5
2 -> 4 capacity 5
3 -> 4 capacity 5
~~~

Giới hạn tại các đỉnh trung gian:

**b_2=2**, **b_3=1**.

Không có giới hạn tại nguồn/đích theo quy ước hiện tại.

Mạng tách gồm:

~~~text
1_out -> 2_in    cap 5
2_in  -> 2_out   cap 2
2_out -> 4_in    cap 5

1_out -> 3_in    cap 5
3_in  -> 3_out   cap 1
3_out -> 4_in    cap 5
~~~

Có thể gửi:

- 2 đơn vị theo 1→2→4.
- 1 đơn vị theo 1→3→4.

Tổng **3**. Không thể gửi hơn vì mọi đường từ 1 đến 4 đều qua 2 hoặc 3, tổng sức chứa hai đỉnh là **2+1=3**.

Nếu bỏ qua vertex capacities, sức chứa cạnh cho phép tổng **10**. Đây là một ví dụ cho thấy **bottleneck tại đỉnh khác với bottleneck tại cạnh**.

## 5. Nguồn và đích có bị giới hạn không?

Đây là lựa chọn mô hình rất quan trọng.

Trong nhiều đề max flow, các ràng buộc trên **đỉnh trung gian** chỉ áp dụng cho v≠s,t. Nguồn s và đích t thường **không bị giới hạn sức chứa đỉnh**, trừ khi đề nói rõ.

### Trường hợp A: s và t không bị giới hạn đỉnh

Chọn nguồn/đích trong mạng tách:

**source' = s_out**.

**sink' = t_in**.

Mọi đường từ s_out tới t_in phải đi qua các cung nội bộ của **các đỉnh trung gian**; không bị buộc đi qua s_in→s_out hoặc t_in→t_out ở hai đầu.

Ta vẫn có thể tạo hai cung nội bộ của s,t với INF, nhưng việc chọn nguồn s_out và đích t_in khiến chúng không giới hạn lưu lượng đầu cuối trên một đường s–t.

### Trường hợp B: s và t cũng có sức chứa riêng

Nếu đề yêu cầu cả nguồn s chỉ cung cấp tối đa b_s và đích t chỉ tiếp nhận tối đa b_t, chọn:

**source' = s_in**.

**sink' = t_out**.

Khi đó mọi luồng s→t đi qua s_in→s_out và t_in→t_out, nên bị giới hạn ở cả hai đầu.

### Ví dụ hai cách chọn trả đáp án khác nhau

~~~text
1 -> 2 cap 10
2 -> 3 cap 10

b_1 = 2, b_2 = 5, b_3 = 1
s=1, t=3
~~~

- Nếu **miễn giới hạn s,t**, bottleneck là đỉnh 2: max flow = **5**.
- Nếu **áp dụng giới hạn s,t**, bottleneck là đỉnh 3: max flow = **1**.

Không thể tự động trả 1 hay 5 mà không đọc xem đề có giới hạn hai đỉnh đầu cuối không.

### Chú ý khi có cung đi vào s hoặc đi ra t

Một mạng có thể có các cung đi vào nguồn hoặc đi ra đích. Chúng không làm thay đổi định nghĩa max flow: giá trị luồng là **luồng ra ròng tại s**, hoặc **luồng vào ròng tại t**.

Trong một lời giải max flow s–t, có thể loại các chu trình luồng và biểu diễn giá trị bằng các đường s→t. Vì vậy việc chọn endpoint trong mạng tách như trên vẫn mô hình hóa đúng mục tiêu, dù input có những cung quay vòng quanh nguồn/đích.

## 6. Dung lượng INF: phải đủ lớn nhưng không được tràn số

Khi một đỉnh không có giới hạn, ta muốn cung **v_in→v_out** có dung lượng lớn đến mức nó **không thể là nút thắt** của bài toán.

Không nên máy móc đặt INF=10^9, vì tổng luồng hợp lệ có thể lớn hơn 10^9. Cũng không nên cộng vào **Long.MAX_VALUE** mà không kiểm tra overflow.

Với một bài max flow có các cung gốc dung lượng nguyên không âm, có thể lấy:

**B = 1 + tổng sức chứa của mọi cung gốc**.

Giá trị max flow không thể lớn hơn tổng dung lượng tất cả các cung gốc; vì vậy **B lớn hơn mọi giá trị max flow khả thi**. Các cung đỉnh không giới hạn có capacity B là đủ.

### Điều kiện số học để dùng long

Nếu dùng kiểu long, phép cộng tính B phải an toàn:

- Mỗi c_e ≥ 0.
- Tổng sức chứa mọi cung gốc cộng thêm 1 không vượt **Long.MAX_VALUE**.
- Nếu tổng vượt miền long, dùng số nguyên lớn, giới hạn dữ liệu chặt hơn hoặc biểu diễn thuật toán khác.

Code Java bên dưới dùng **Math.addExact** khi cộng để **ném lỗi rõ ràng** thay vì âm thầm tạo INF sai. Như vậy tính đúng được bảo vệ bởi một **điều kiện đầu vào minh bạch**.

### Có nhất thiết cần B+1 thay vì B?

Nếu B được chọn bằng tổng c_e+1, mọi cung “không giới hạn” chắc chắn lớn hơn bất kỳ max flow thực. Có thể dùng một cận trên khác nếu đã chứng minh nó đủ an toàn. Đừng dùng một hằng số ngẫu nhiên mà không nắm cận của dữ liệu.

### Nếu m=0

Tổng sức chứa cung gốc bằng 0; B=1. Không tồn tại đường đi s→t, nên max flow bằng 0. Vẫn có thể thêm cung nội bộ capacity 1 mà không tạo đường đi từ nguồn tới đích.

## 7. Chứng minh phép biến đổi bảo toàn bài toán

Phải chứng minh hai chiều: mọi luồng hợp lệ trên mạng gốc ánh xạ sang luồng hợp lệ trên mạng tách; và mọi luồng hợp lệ trên mạng tách ánh xạ trở lại mạng gốc mà không vi phạm sức chứa cạnh/đỉnh.

### Chiều 1: luồng gốc → luồng tách

Giả sử f là một luồng s–t hợp lệ trên graph gốc.

- Với mỗi cung gốc e=(u,v), đặt luồng trên cung mô phỏng **u_out→v_in** bằng **f(e)**. Vì f(e)≤c_e, giới hạn cung mô phỏng được thỏa.
- Với mỗi đỉnh trung gian v, đặt luồng trên **v_in→v_out** bằng tổng luồng gốc đi vào v. Theo bảo toàn tại v, tổng này bằng tổng luồng gốc đi ra v.
- Nếu vertex capacity là b_v thì tổng ấy ≤b_v, nên cung nội bộ hợp lệ.

Tại v_in, tổng luồng từ các cung gốc đi vào bằng luồng chuyển sang v_out. Tại v_out, luồng nhận từ v_in bằng tổng luồng đi ra các cung gốc. Vậy điều kiện bảo toàn tại các nút mới thỏa.

Tại hai đầu s,t, xử lý theo cách chọn source'/sink' ở mục 5. Trong cách không giới hạn s,t, có thể dùng phân rã luồng thành các đường s→t và các chu trình; loại chu trình không cần thiết mà không thay đổi giá trị luồng, sau đó ánh xạ các đường s→t.

Suy ra mỗi giá trị luồng khả thi ở mạng gốc cũng khả thi ở mạng tách.

### Chiều 2: luồng tách → luồng gốc

Giả sử f' là một luồng hợp lệ trên mạng tách.

- Với mỗi cung gốc (u,v), lấy luồng trên **u_out→v_in** làm luồng f(u,v) của graph gốc.
- Nó không vượt c_e vì cung mô phỏng có đúng capacity c_e.
- Với mỗi đỉnh trung gian v, mọi luồng từ các cung gốc đi vào v_in phải đi qua cung duy nhất **v_in→v_out** trước khi rời sang các cung gốc đi ra.
- Vì cung nội bộ này có capacity b_v, tổng luồng qua v không vượt b_v.
- Bảo toàn tại v_in và v_out kéo theo bảo toàn tại v gốc.

Suy ra mọi luồng khả thi trên mạng tách tương ứng một luồng khả thi ở graph gốc với **cùng giá trị s–t**.

### Kết luận

Hai miền nghiệm có cùng tập **giá trị luồng khả thi** (xét giá trị tối ưu và không cần giữ các chu trình luồng vô ích). Do đó:

**maxFlow(network gốc có vertex capacities) = maxFlow(network sau tách đỉnh).**

Vì mạng sau tách là một mạng flow thông thường, ta có thể áp dụng **định lý max-flow/min-cut** và các thuật toán max flow đã biết.

## 8. Cung ngược trong mạng dư và sức chứa đỉnh

Khi dùng Dinic hoặc Edmonds–Karp, mỗi cung đã thêm vào mạng tách có:

- **Cung thuận residual** với capacity ban đầu.
- **Cung ngược residual** với capacity ban đầu 0.

Nếu gửi x đơn vị trên cung thuận, capacity dư thuận giảm x, capacity dư ngược tăng x. Cung ngược cho phép **hủy hoặc điều chỉnh** quyết định gửi luồng trước đó khi tìm đường tăng luồng mới.

Điều này áp dụng cho **cả cung nội bộ v_in→v_out** lẫn cung mô phỏng cạnh gốc.

### Không được tạo cung ngược ban đầu có cùng capacity

Một cung gốc u→v có capacity c chỉ cho phép di chuyển luồng theo chiều u→v. Nếu ta thêm một cung độc lập v→u cũng có capacity c mà input không có cung ấy, ta đã **thay đổi bài toán có hướng**.

Cung ngược residual có capacity ban đầu **0**, không phải một cung vật lý ngược được cấp sẵn sức chứa c.

### Tách đỉnh không thay thế residual graph

Vertex splitting chỉ tạo mạng mới. Thuật toán max flow vẫn phải quản lý residual capacities đúng chuẩn, kể cả reverse-edge index. Nếu bỏ bước residual, thuật toán tham lam chọn các đường một lần có thể bị kẹt ở một phương án không tối ưu.

## 9. Ví dụ kết hợp nút thắt cạnh và đỉnh

Xét graph:

~~~text
1 -> 2 cap 5
1 -> 3 cap 2
2 -> 4 cap 2
2 -> 3 cap 3
3 -> 4 cap 4

s=1, t=4
b_2=4, b_3=3
s,t khong gioi han dinh
~~~

Ta có thể gửi:

- **2** đơn vị theo 1→2→4.
- **2** đơn vị theo 1→2→3→4.
- **1** đơn vị theo 1→3→4.

Tổng là **5**.

Giới hạn đỉnh 2 là 4 (2+2), giới hạn đỉnh 3 là 3 (2+1), đều thỏa. Cung 3→4 cho phép 4 nhưng tại đỉnh 3 chỉ có tổng 3.

Vì toàn bộ luồng tới 4 đi qua cung 2→4 (capacity 2) hoặc qua đỉnh 3 (capacity 3), giá trị không thể vượt **2+3=5**. Do đã xây được một luồng 5, đáp án tối ưu chính xác là **5**.

Ví dụ này cho thấy **max flow có thể bị chặn đồng thời bởi một cung gốc và một đỉnh**, không nhất thiết chỉ bởi một loại.

## 10. Minimum cut sau khi tách đỉnh có ý nghĩa gì?

Trong mạng tách, min cut là một tập cung đi từ phía nguồn S sang phía đích T có tổng capacity nhỏ nhất. Các cung crossing có thể gồm:

1. **Cung nội bộ v_in→v_out**: tương ứng với việc cắt khả năng đi qua **đỉnh v**.
2. **Cung mô phỏng u_out→v_in**: tương ứng với việc cắt **cung gốc u→v**.

Vì vậy, với bài toán có **đồng thời sức chứa cạnh và đỉnh**, một min cut có thể pha trộn **sức chứa nút** và **sức chứa cung**.

### Ví dụ chỉ cắt đỉnh trung gian

Trong graph có hai đường s→2→t và s→3→t, các cung gốc capacity 5, còn b_2=2, b_3=1, cắt hai cung nội bộ:

~~~text
2_in -> 2_out cap 2
3_in -> 3_out cap 1
~~~

đủ ngăn mọi đường từ nguồn tới đích, với tổng capacity 3. Min cut có giá trị 3, bằng max flow.

### Không được tự coi mọi cut là một tập đỉnh

Nếu một cung gốc u→v có capacity 1 còn các đỉnh đều có capacity lớn, min cut có thể cắt **cung ấy**, không phải một đỉnh. Khi bài yêu cầu **minimum vertex cut** thuần túy, cần thiết kế sức chứa các cung gốc đủ lớn để cut hữu hạn ưu tiên cắt đỉnh, và xử lý chính xác hai terminal.

Muốn trích một chứng chỉ cut, sau max flow chạy BFS trong **mạng dư** từ source'. Một cung thuận crossing nếu đầu của nó reachable trong residual mà đầu kia unreachable. Với cung nội bộ v_in→v_out crossing, có thể xem v là một đỉnh của vertex cut, **nếu mô hình đã bảo đảm cut chỉ cắt cung đỉnh**.

**Lưu ý:** cung có capacity 0 cũng có thể nằm trên một cut giá trị 0. Nếu chỉ liệt kê các cung crossing có capacity dương, có thể mất thông tin về những đỉnh/cung bị chặn hoàn toàn.

## 11. Ứng dụng: nhiều đường đi không chung đỉnh trung gian

Một ứng dụng nổi tiếng của tách đỉnh là tìm **số đường đi từ s đến t không sử dụng chung các đỉnh trung gian** (internally vertex-disjoint paths).

Cách xây dựng với graph có hướng:

- Với mỗi đỉnh trung gian v, đặt sức chứa **v_in→v_out = 1**.
- Nguồn s và đích t **không giới hạn đỉnh**.
- Với mỗi cung gốc, cho sức chứa **1** nếu một cung chỉ được một đường sử dụng; mỗi cạnh song song là một cung riêng.
- Chạy max flow từ s_out tới t_in.

Do sức chứa nguyên, định lý tính nguyên của max flow bảo đảm có nghiệm luồng nguyên. Có thể phân rã luồng tối ưu thành các đường s→t, với mỗi đỉnh trung gian được **tối đa một đường** sử dụng.

### Ví dụ

~~~text
s=1

1 -> 2 -> 5
1 -> 3 -> 5
1 -> 4 -> 5

t=5
~~~

Với b_2=b_3=b_4=1 và capacity của mỗi cung bằng 1, có thể gửi 3 đơn vị và tương ứng 3 đường đi không chung đỉnh trung gian.

Nếu thêm hai đường đều bắt buộc qua đỉnh 2 thì tổng số đường độc lập qua 2 vẫn tối đa **1**, dù có nhiều cạnh tới/ra khỏi 2.

### Phân biệt với edge-disjoint paths

Nếu chỉ cần các đường **không chung cạnh**, không cần đặt vertex capacity=1 trên các đỉnh trung gian. Một đỉnh có thể nằm trên nhiều đường, miễn các cạnh không trùng.

Nếu cần **không chung đỉnh trung gian**, đặt capacity=1 ở các nút trung gian mới là giới hạn quyết định.

### Lưu ý về định lý Menger

Trong dạng không kề nhau của s,t, định lý Menger liên hệ số đường nội bộ không chung đỉnh với số đỉnh trung gian tối thiểu cần loại để tách s khỏi t.

Nếu có một **cung trực tiếp s→t**, không có tập đỉnh trung gian nào cắt được chính cung trực tiếp ấy. Vì vậy không được phát biểu máy móc “minimum internal vertex cut = số đường độc lập” khi s,t kề nhau mà không nêu điều kiện hoặc quy ước bổ sung.

Dùng **capacity 1 cho từng cung trực tiếp** cũng giúp mô hình tính đúng số đường theo **các cạnh riêng biệt** trong bài có hướng với cạnh song song.

## 12. Khi nào có thể bỏ các cung không cần thiết?

Tách đỉnh đôi khi tạo hai nút cho cả s và t. Nếu hai terminal không bị giới hạn và ta dùng source'=s_out, sink'=t_in, các cung s_in→s_out và t_in→t_out có thể được đặt INF.

Trong một mạng chỉ cần tìm max flow s–t, ta cũng có thể loại khỏi biểu diễn các cung không thể nằm trên một đường tăng luồng s_out→t_in sau khi chuẩn hóa chu trình, nhưng cách này dễ gây lỗi khi input có cung quay về source hoặc đi ra sink.

Cách đơn giản, dễ chứng minh hơn là **giữ đủ 2n nút và n+m cung**, chỉ thay nguồn/đích theo mục 5. Chi phí vẫn O(n+m), thường không đáng đánh đổi độ rõ ràng để tiết kiệm vài nút.

### Đỉnh b_v = 0

Nếu v là đỉnh trung gian với capacity 0, cung v_in→v_out không thể truyền đơn vị luồng nào. Về mặt đường s–t có positive flow, v hoạt động như đỉnh bị chặn.

Nếu v là s hoặc t và đề **miễn giới hạn terminal**, b_v=0 không được áp dụng tại endpoint nên không chặn luồng. Nếu đề **giới hạn terminal**, b_v=0 khiến max flow bằng 0.

Đây là một testcase quan trọng để phát hiện **chọn source' / sink' sai**.

## 13. Code Java 17+ hoàn chỉnh: tách đỉnh rồi chạy Dinic

Chương trình sau hiện thực:

1. Kiểm tra n, s,t, sức chứa đỉnh và cung.
2. Mỗi đỉnh v thành cặp **in(v), out(v)**.
3. Cung nội bộ có capacity b_v, hoặc INF khi không giới hạn.
4. Mỗi cung gốc chuyển thành **out(u)→in(v)** đúng capacity.
5. Chọn source'/sink' theo cờ **limitTerminals**.
6. Dùng **Dinic** tìm max flow trên mạng 2n nút.
7. Xuất các kết quả mẫu có lời giải đã kiểm tra.

**Hợp đồng API:** các đỉnh đánh số 1..n, n≥2, s≠t; mảng vertexCap có đúng n phần tử; giá trị **−1** có nghĩa “không giới hạn tại đỉnh”, các giá trị khác phải không âm; mỗi cung có capacity≥0. Để sử dụng long an toàn, **1 + tổng capacity các cung gốc phải nằm trong phạm vi long**. Nếu không, chương trình báo ArithmeticException từ Math.addExact và cần phiên bản hỗ trợ số nguyên lớn.

### Chương trình tự chạy

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class VertexCapacitySplittingDemo {

    record Arc(int from, int to, long capacity) {}

    static final class Dinic {
        static final class ResidualEdge {
            final int to;
            final int rev;
            long cap;

            ResidualEdge(int to, int rev, long cap) {
                this.to = to;
                this.rev = rev;
                this.cap = cap;
            }
        }

        final List<List<ResidualEdge>> g;
        final int[] level;
        final int[] ptr;

        Dinic(int count) {
            g = new ArrayList<>(count);
            for (int i = 0; i < count; i++) {
                g.add(new ArrayList<>());
            }
            level = new int[count];
            ptr = new int[count];
        }

        void addEdge(int u, int v, long capacity) {
            if (u == v || capacity < 0) {
                throw new IllegalArgumentException(
                        "Invalid transformed edge");
            }

            ResidualEdge forward =
                    new ResidualEdge(v, g.get(v).size(),
                                     capacity);
            ResidualEdge reverse =
                    new ResidualEdge(u, g.get(u).size(), 0L);

            g.get(u).add(forward);
            g.get(v).add(reverse);
        }

        boolean bfs(int source, int sink) {
            Arrays.fill(level, -1);
            ArrayDeque<Integer> queue = new ArrayDeque<>();
            queue.addLast(source);
            level[source] = 0;

            while (!queue.isEmpty()) {
                int u = queue.removeFirst();
                for (ResidualEdge e : g.get(u)) {
                    if (e.cap > 0 && level[e.to] < 0) {
                        level[e.to] = level[u] + 1;
                        queue.addLast(e.to);
                    }
                }
            }
            return level[sink] >= 0;
        }

        long dfs(int u, int sink, long pushed) {
            if (pushed == 0) return 0;
            if (u == sink) return pushed;

            List<ResidualEdge> edges = g.get(u);
            while (ptr[u] < edges.size()) {
                ResidualEdge e = edges.get(ptr[u]);

                if (e.cap > 0 &&
                        level[e.to] == level[u] + 1) {
                    long sent = dfs(e.to, sink,
                            Math.min(pushed, e.cap));
                    if (sent > 0) {
                        e.cap -= sent;
                        g.get(e.to).get(e.rev).cap += sent;
                        return sent;
                    }
                }

                ptr[u]++;
            }
            return 0;
        }

        long maxFlow(int source, int sink, long inf) {
            long answer = 0;
            while (bfs(source, sink)) {
                Arrays.fill(ptr, 0);
                while (true) {
                    long sent = dfs(source, sink, inf);
                    if (sent == 0) break;
                    answer = Math.addExact(answer, sent);
                }
            }
            return answer;
        }
    }

    static int in(int vertex) {
        return 2 * (vertex - 1);
    }

    static int out(int vertex) {
        return in(vertex) + 1;
    }

    static long maxFlowWithVertexCap(
            int n, int source, int sink,
            long[] vertexCap, Arc[] arcs,
            boolean limitTerminals) {

        if (n < 2 || source < 1 || source > n
                || sink < 1 || sink > n
                || source == sink) {
            throw new IllegalArgumentException(
                    "Require n>=2 and distinct source/sink");
        }
        Objects.requireNonNull(vertexCap, "vertexCap");
        Objects.requireNonNull(arcs, "arcs");

        if (vertexCap.length != n) {
            throw new IllegalArgumentException(
                    "One vertex capacity per vertex");
        }
        for (long c : vertexCap) {
            if (c < -1) {
                throw new IllegalArgumentException(
                        "Vertex cap must be >=0 or -1");
            }
        }

        // Bound exceeds every feasible s-t flow value.
        long inf = 1L;
        for (Arc arc : arcs) {
            Objects.requireNonNull(arc, "arc");
            if (arc.from() < 1 || arc.from() > n
                    || arc.to() < 1 || arc.to() > n
                    || arc.capacity() < 0) {
                throw new IllegalArgumentException(
                        "Invalid original arc");
            }
            inf = Math.addExact(inf, arc.capacity());
        }

        Dinic dinic = new Dinic(2 * n);

        for (int v = 1; v <= n; v++) {
            boolean terminal = v == source || v == sink;
            long limit = vertexCap[v - 1];
            long effective = (limit == -1
                    || (terminal && !limitTerminals))
                    ? inf : limit;

            dinic.addEdge(in(v), out(v), effective);
        }

        // For original arc u -> v, keep its edge capacity.
        for (Arc arc : arcs) {
            dinic.addEdge(out(arc.from()), in(arc.to()),
                          arc.capacity());
        }

        int s2 = limitTerminals ? in(source) : out(source);
        int t2 = limitTerminals ? out(sink) : in(sink);

        return dinic.maxFlow(s2, t2, inf);
    }

    static void show(String label,
                     int n, int s, int t,
                     long[] vertexCap, boolean limitTerminals,
                     Arc... arcs) {

        long answer = maxFlowWithVertexCap(
                n, s, t, vertexCap, arcs, limitTerminals);
        System.out.println(label + ": " + answer);
    }

    public static void main(String[] args) {
        show("Two vertex bottlenecks", 4, 1, 4,
                new long[] {-1, 2, 1, -1}, false,
                new Arc(1, 2, 5),
                new Arc(1, 3, 5),
                new Arc(2, 4, 5),
                new Arc(3, 4, 5));

        show("Mixed edge and vertex", 4, 1, 4,
                new long[] {-1, 4, 3, -1}, false,
                new Arc(1, 2, 5),
                new Arc(1, 3, 2),
                new Arc(2, 4, 2),
                new Arc(2, 3, 3),
                new Arc(3, 4, 4));

        Arc[] chain = {
                new Arc(1, 2, 10),
                new Arc(2, 3, 10)
        };
        System.out.println("Terminals exempt: "
                + maxFlowWithVertexCap(3, 1, 3,
                    new long[] {2, 5, 1},
                    chain, false));
        System.out.println("Terminals enforced: "
                + maxFlowWithVertexCap(3, 1, 3,
                    new long[] {2, 5, 1},
                    chain, true));

        show("Zero internal capacity", 3, 1, 3,
                new long[] {-1, 0, -1}, false,
                new Arc(1, 2, 8),
                new Arc(2, 3, 8));

        show("Parallel and self loop", 3, 1, 3,
                new long[] {-1, 3, -1}, false,
                new Arc(1, 2, 2),
                new Arc(1, 2, 5),
                new Arc(2, 2, 100),
                new Arc(2, 3, 10));

        show("Direct bypass", 3, 1, 3,
                new long[] {-1, 0, -1}, false,
                new Arc(1, 3, 4),
                new Arc(1, 2, 7),
                new Arc(2, 3, 7));

        show("Disconnected", 4, 1, 4,
                new long[] {-1, 5, 5, -1}, false,
                new Arc(1, 2, 5),
                new Arc(3, 4, 5));

        show("Edge bottleneck", 4, 1, 4,
                new long[] {-1, 10, 10, -1}, false,
                new Arc(1, 2, 2),
                new Arc(1, 3, 6),
                new Arc(2, 4, 5),
                new Arc(3, 4, 1));

        show("No arcs", 2, 1, 2,
                new long[] {-1, -1}, false);
    }
}
~~~

Lưu mã vào tệp **VertexCapacitySplittingDemo.java** với UTF-8. Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 VertexCapacitySplittingDemo.java
java VertexCapacitySplittingDemo
~~~

Đầu ra của chương trình:

~~~text
Two vertex bottlenecks: 3
Mixed edge and vertex: 5
Terminals exempt: 5
Terminals enforced: 1
Zero internal capacity: 0
Parallel and self loop: 3
Direct bypass: 4
Disconnected: 0
Edge bottleneck: 3
No arcs: 0
~~~

**Mã được thiết kế để minh họa phép biến đổi và luồng cực đại**, không bao gồm giao diện đọc input từ stdin hoặc in danh sách từng đường phân rã. Các tác vụ ấy có thể thêm riêng theo định dạng của đề.

## 14. Giải thích các thành phần chính của code

### Hàm in và out

Với đỉnh v từ 1 đến n:

- in(v)=2(v−1).
- out(v)=2(v−1)+1.

Hai hàm giúp ánh xạ thống nhất giữa graph gốc và graph tách, tránh lỗi lệch 1 khi Java dùng chỉ số mảng 0-based.

### Tạo đúng cung nội bộ

~~~java
long effective = (limit == -1
        || (terminal && !limitTerminals))
        ? inf : limit;

dinic.addEdge(in(v), out(v), effective);
~~~

Nếu v không bị giới hạn, dùng inf. Nếu v là nguồn/đích và bài **miễn terminal**, cũng dùng inf.

Nếu bài yêu cầu terminal có sức chứa, dùng đúng vertexCap[v−1]. Ví dụ source cap2, sink cap1 khiến luồng qua chuỗi chỉ còn 1.

### Cung gốc giữ capacity

~~~java
dinic.addEdge(out(arc.from()),
              in(arc.to()),
              arc.capacity());
~~~

Đây là câu lệnh chuyển mô hình quan trọng nhất. Không được thay capacity gốc bằng capacity đỉnh, vì bài có thể giới hạn **đồng thời** cả hai.

### Mạng dư và reverse-edge index

Đối tượng ResidualEdge lưu:

- **to**: nút đích trong mạng tách.
- **rev**: chỉ số của cung dư ngược tại adjacency của to.
- **cap**: capacity dư hiện tại.

Khi gửi sent đơn vị, giảm cap cung thuận và tăng cap cung ngược. Do mạng tách chỉ thêm cung giữa **in và out của hai nút khác nhau**, hàm addEdge có thể từ chối self-loop tại cấp mạng đã tách.

**Lưu ý:** khuyên tự nối ở graph gốc v→v biến thành cung **v_out→v_in**, hai nút này khác nhau, nên vẫn là input hợp lệ. Khuyên đó tạo một vòng trong mạng tách nhưng không làm tăng max flow s–t; thuật toán luồng dư xử lý bình thường.

### Kiểm tra tràn số

Math.addExact khi cộng inf và khi tăng tổng flow sẽ ném **ArithmeticException** nếu miền long không đủ. Đây là hành vi cố ý để tránh kết quả sai do overflow.

**Giới hạn quan trọng:** hàm DFS của Dinic ở ví dụ dùng **đệ quy**. Với mạng cực sâu, mức đệ quy có thể tới O(2n) và gây StackOverflowError trong Java. Đối với giới hạn n rất lớn, có thể cài DFS tìm blocking flow bằng stack tường minh hoặc dùng chiến lược phù hợp với stack JVM. Không nên coi phiên bản demo này là miễn mọi giới hạn runtime khi n lên hàng triệu.

## 15. Độ phức tạp của biến đổi và của Dinic

Gọi n là số đỉnh và m là số cung ban đầu.

**Giai đoạn tạo mạng tách:**

- Tạo 2n nút: O(n).
- Thêm n cung nội bộ: O(n).
- Thêm m cung mô phỏng: O(m).
- Tổng O(n+m) thời gian và O(n+m) bộ nhớ, trước khi tính overhead cấu trúc Java.

**Giai đoạn max flow bằng Dinic:**

- Mỗi lần BFS dựng level graph: O(V'+E').
- Mỗi blocking-flow phase thực hiện O(E') thao tác duyệt cung dư (trong phân tích chuẩn).
- Với mạng capacity bất kỳ, cận tổng quát của Dinic là **O(V'²·E')**.

Thay V'=2n và E'=n+m:

**O(n²(n+m))** là cận xấu nhất theo mô hình đơn vị của thuật toán minh họa, bỏ qua hằng số.

**Bộ nhớ:** O(n+m) cho graph tách và residual edges, level[], ptr[]; thêm tối đa O(n) stack lời gọi DFS.

Trong những mạng có cấu trúc đặc biệt hoặc sức chứa đơn vị, Dinic có các cận tốt hơn. Không được tuyên bố rằng **vertex splitting tự làm max flow chạy O(n+m)**: nó chỉ tăng kích thước mạng tuyến tính, còn độ phức tạp max flow vẫn phụ thuộc thuật toán.

### So sánh nhanh Edmonds–Karp và Dinic

- **Edmonds–Karp:** dùng BFS tìm đường tăng ngắn nhất theo số cung, tổng quát O(V'E'²); dễ hiểu, có thể đủ cho mạng nhỏ.
- **Dinic:** BFS level graph và DFS blocking flow, cận tổng quát O(V'²E'); thường hiệu quả hơn khi cần nhiều lần tăng luồng.
- **Push–Relabel:** một lựa chọn khác cho max flow, có các cận và tính chất triển khai khác, nhưng vẫn dùng được mạng sau tách đỉnh.

Kỹ thuật tách đỉnh **độc lập** với thuật toán max flow cụ thể.

## 16. Kiểm thử độc lập bằng min-cut và vét cạn luồng

Để QA code, nên dùng **hai cách kiểm tra không dựa vào thuật toán Dinic**.

### 16.1. Liệt kê mọi cut của mạng tách (đồ thị rất nhỏ)

Với V'=2n nút, một cut s'–t' xác định bởi tập S chứa s' và không chứa t'. Có khoảng **2^(V'−2)** cách chọn các nút còn lại vào S.

Với mỗi cut, tính:

**cutCapacity(S) = tổng capacity của tất cả cung từ S sang phần bù của S.**

Lấy minimum trên mọi cut.

Theo định lý max-flow/min-cut, giá trị ấy phải bằng kết quả Dinic. Oracle này kiểm tra **mạng tách** và thao tác max flow mà không dùng chính Dinic.

Ví dụ graph hai đỉnh nghẽn có cut cắt hai cung nội bộ tại 2,3 với tổng 3. Mọi luồng không thể vượt 3, và Dinic tìm được 3.

### 16.2. Vét cạn phân phối luồng trên các cung gốc

Với n,m nhỏ và capacity nguyên rất nhỏ, có thể duyệt mọi cách chọn:

**f(e) ∈ {0,1,...,c_e}** cho mỗi cung e.

Với mỗi cách phân phối, kiểm tra:

1. Mọi cung không vượt sức chứa.
2. Tại mỗi đỉnh trung gian, tổng vào bằng tổng ra.
3. Tại mỗi đỉnh trung gian, tổng vào không vượt b_v (nếu đỉnh không giới hạn thì bỏ điều kiện).
4. Giá trị flow ròng tại s bằng giá trị flow ròng tại t và không âm.
5. Nếu terminal có giới hạn, giá trị s–t không vượt b_s,b_t.

Lấy giá trị lớn nhất. Vì sức chứa nguyên, max flow tối ưu có nghiệm nguyên nên oracle có thể so chính xác trong những test nhỏ.

Vét cạn primal trên graph gốc còn giúp phát hiện **lỗi biến đổi mô hình** mà một oracle min-cut dùng chính mạng tách có thể bỏ sót.

### Cần kiểm thử các loại input nào?

| Tình huống | Điều cần xác minh |
| --- | --- |
| Một đỉnh trung gian capacity nhỏ | Luồng bị chặn đúng tại đỉnh |
| Các cung capacity nhỏ hơn vertex cap | Luồng bị chặn bởi cung |
| Có song song giữa cùng cặp đỉnh | Giữ từng cung riêng và đúng tổng |
| Có khuyên tự nối gốc | Không vô tình tạo thêm luồng từ s đến t |
| Vertex cap=0 | Không có luồng đi qua đỉnh ấy |
| s/t không bị giới hạn | Dùng s_out và t_in |
| s/t bị giới hạn | Dùng s_in và t_out |
| Có cung trực tiếp s→t | Có thể đi vòng qua giới hạn các đỉnh trung gian |
| Không có đường s→t | Max flow 0 |
| Tất cả cung capacity=0 | Max flow 0 |
| Đỉnh không có giới hạn (−1) | Dùng INF được chứng minh đủ lớn |
| Tổng capacity vượt long | Phải báo lỗi rõ hoặc dùng kiểu số lớn |

Không thể chỉ kiểm tra một đường đơn. Nhiều trường hợp đòi gửi luồng qua **nhiều đường song song**, điều chỉnh residual hoặc chia luồng qua các nút có giới hạn khác nhau.

## 17. Bài toán với sức chứa trên cạnh **và** chi phí đi qua đỉnh

Đôi khi một đỉnh vừa giới hạn bao nhiêu đơn vị có thể đi qua, vừa thu phí **mỗi đơn vị luồng**.

Có thể gắn:

- capacity b_v cho cung **v_in→v_out**;
- cost p_v cho cung nội bộ ấy;
- capacity c_e và cost k_e cho cung mô phỏng cạnh gốc.

Lúc đó ta được một mạng **min-cost flow / min-cost max-flow** thông thường trên các cung đã tách, nếu mục tiêu là tối ưu chi phí dưới các giới hạn đã nêu.

Tuy nhiên, **Dinic tối đa hóa giá trị luồng, không tối thiểu hóa tổng cost**. Không được đưa thêm trường cost vào Arc rồi tuyên bố Dinic tự giải bài min-cost flow.

### Sức chứa tối thiểu (lower bounds)

Nếu một đỉnh có ràng buộc **L_v ≤ flowThrough(v) ≤ U_v**, có thể đặt cung nội bộ với **lower bound L_v và upper bound U_v**. Nhưng max flow thông thường chỉ xử lý upper bound; muốn kiểm tra tính khả thi với lower bounds cần biến đổi **luồng có cận dưới**, tính nhu cầu ở các nút và thêm super source/sink theo quy tắc chuẩn.

Đây là một bước khác với tách đỉnh đơn thuần; không được coi lower bound là capacity bình thường.

## 18. Nhiều nguồn, nhiều đích và các loại đồ thị khác

### Nhiều nguồn, nhiều đích

Nếu nhiều đỉnh là nguồn hoặc đích, có thể thêm:

- **super source SS**, nối tới những nguồn gốc bằng các cung có capacity tương ứng.
- **super sink TT**, nhận các cung từ những đích gốc.

Vị trí nối vào **in(v)** hay **out(v)** phụ thuộc mục tiêu:

- Nếu muốn áp dụng sức chứa tại một nguồn gốc, nối SS→**in(v)** để luồng phải qua v_in→v_out.
- Nếu muốn miễn giới hạn nguồn gốc, nối SS→**out(v)**.
- Nếu muốn áp dụng sức chứa tại một đích gốc, nối **out(v)**→TT.
- Nếu muốn miễn giới hạn đích gốc, nối **in(v)**→TT.

Dung lượng các cung SS/TT cũng phải biểu diễn đúng giới hạn cung/cầu của từng nguồn/đích; một cung vô hạn ở đây có thể không phù hợp nếu từng terminal có giới hạn riêng.

### Đồ thị vô hướng

Đối với graph vô hướng, cần xác định **sức chứa trên cạnh vô hướng** có ý nghĩa gì:

- Nếu cho phép mỗi chiều là một cung riêng với capacity riêng, có thể tạo hai cung ngược nhau.
- Nếu một cạnh vật lý chỉ có **một ngân sách dùng chung** cho cả hai chiều, không được diễn giải ngay hai cung độc lập c và c thành ràng buộc dùng chung trong **mọi nghiệm luồng thô**. Với max flow một cặp s–t, các luồng ngược chiều có thể được triệt tiêu mà không đổi giá trị, nhưng nếu phải xuất một phân phối tuân thủ ngân sách vật lý dùng chung thì cần chuẩn hóa hoặc dùng **edge gadget**.

Tách đỉnh vẫn áp dụng được sau khi đã mô hình hóa đúng **cung/sức chứa** của bài.

### Đỉnh s=t

Bài max flow chuẩn thường yêu cầu nguồn và đích **phân biệt**. Nếu s=t, khái niệm “giá trị luồng gửi từ s tới t” cần quy ước khác, và một thuật toán augmenting path viết đơn giản có thể trả kết quả không mong muốn hoặc vòng lặp vô nghĩa. Vì vậy API ví dụ **từ chối s=t** thay vì âm thầm đoán định nghĩa.

## 19. Những lỗi thường gặp

1. **Chỉ thay capacity của từng cạnh kề** mà không tạo giới hạn chung tại đỉnh.
2. **Đảo cung nội bộ thành v_out→v_in**; chiều đúng là **v_in→v_out**.
3. **Đưa cung gốc u→v thành u_in→v_out**; chiều đúng khi tách là **u_out→v_in**.
4. **Quên giữ sức chứa cạnh gốc** khi tạo cung mô phỏng.
5. **Giới hạn s/t dù đề chỉ giới hạn đỉnh trung gian**, làm max flow nhỏ hơn đáp án.
6. **Bỏ qua giới hạn s/t khi đề yêu cầu**, làm max flow lớn hơn đáp án.
7. **Chọn s_in,t_out khi muốn miễn terminal**, hoặc ngược lại.
8. **Chọn INF quá nhỏ**, khiến đỉnh không bị giới hạn trở thành bottleneck giả.
9. **Dùng Long.MAX_VALUE rồi cộng/nhân không kiểm tra tràn số**.
10. **Đánh số in/out không nhất quán giữa các cung**, nối sai mạng.
11. **Quên tạo cung ngược residual**, khiến thuật toán không hủy được luồng cũ.
12. **Tạo cung vật lý ngược capacity c khi input chỉ có u→v**, làm thay đổi hướng graph.
13. **Cho sức chứa âm** trong mô hình max flow chuẩn.
14. **Nhầm capacity đỉnh với trọng số/chi phí đỉnh**, dùng Dinic như min-cost flow.
15. **Nhầm tổng luồng qua v với max của từng cung kề**, khiến nhiều luồng cộng lại vượt vertex cap.
16. **Cho rằng min cut trên mạng tách chỉ gồm cung đỉnh**, dù nó có thể cắt cả cung gốc.
17. **Áp dụng vertex-disjoint paths mà không giới hạn đỉnh trung gian bằng 1**.
18. **Không phân biệt edge-disjoint và vertex-disjoint**, chọn sai kiểu giới hạn.
19. **Phát biểu định lý Menger thiếu điều kiện cho s,t kề nhau**, gây kết luận về internal vertex cut không hợp lý.
20. **Không xử lý vertex cap=0**, khiến đỉnh đáng lẽ bị chặn vẫn truyền luồng.
21. **Gộp các cạnh song song nhưng cộng/sửa capacity không theo đề**, dẫn đến luồng sai.
22. **Coi self-loop gốc là một đường tăng luồng tới t**, dù nó không tạo kết nối mới.
23. **Không tính bộ nhớ của các cung residual**, ước lượng RAM quá thấp.
24. **Cho rằng tách đỉnh làm Dinic O(n+m)**, bỏ qua độ phức tạp thuật toán max flow.
25. **Bỏ qua giới hạn stack đệ quy** của DFS trên mạng cực sâu.
26. **Chỉ thử graph có một đường**, không thử hai nhánh cùng qua một đỉnh nghẽn.
27. **Với nhiều nguồn/đích, nối super source/sink sai phía in/out**.
28. **Quên rằng mỗi đỉnh gốc tạo hai nút và mỗi cung thêm có cung residual ngược**, cấp phát thiếu bộ nhớ.
29. **Dùng lower bound như upper capacity**, dù đó là ràng buộc khác cần biến đổi khả thi.
30. **Chỉ kiểm thử max flow của mạng tách với một code khác dùng cùng lỗi mô hình**, không đối chiếu luồng gốc khi có thể.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Một đỉnh v nhận luồng từ ba cung, tổng 12, nhưng vertex capacity b_v=7. Có hợp lệ không?  
**Đáp án:** Không. Tổng luồng qua v vượt 7, dù mỗi cung riêng lẻ có thể chưa vượt capacity.

**Câu 2.** Tách một đỉnh v thành các nút gì và thêm cung nào?  
**Đáp án:** v_in, v_out; cung **v_in→v_out** capacity b_v.

**Câu 3.** Cung gốc u→v capacity c thành cung gì?  
**Đáp án:** **u_out→v_in** capacity c.

**Câu 4.** Mạng n đỉnh m cung sau tách có bao nhiêu nút/cung thuận?  
**Đáp án:** 2n nút và n+m cung trước các cung residual ngược.

**Câu 5.** Nếu chỉ giới hạn các đỉnh trung gian, dùng source'/sink' nào?  
**Đáp án:** **s_out** và **t_in**.

**Câu 6.** Nếu cũng giới hạn s,t, dùng source'/sink' nào?  
**Đáp án:** **s_in** và **t_out**.

**Câu 7.** Một đỉnh trung gian capacity 0 có truyền được luồng dương không?  
**Đáp án:** Không, cung nội bộ có capacity 0.

**Câu 8.** Tại sao cần INF lớn hơn giá trị max flow khả thi?  
**Đáp án:** Để các đỉnh được khai báo “không giới hạn” không vô tình trở thành nút nghẽn.

**Câu 9.** Trong graph hai đường s→2→t và s→3→t, mỗi cạnh cap5, b_2=2,b_3=1, max flow là bao nhiêu?  
**Đáp án:** **3**.

**Câu 10.** Nếu mỗi đỉnh trung gian capacity 1 và mỗi cung capacity 1, luồng nguyên biểu diễn gì?  
**Đáp án:** Số đường đi có thể chọn mà các đỉnh trung gian không dùng chung (và mỗi cung chỉ được một đường sử dụng).

**Câu 11.** Min cut mạng tách có thể cắt những loại cung nào?  
**Đáp án:** Cả **cung nội bộ giới hạn đỉnh** và **cung mô phỏng cạnh gốc**, tùy capacity.

**Câu 12.** Tại sao không chỉ dùng một hằng INF=10^9?  
**Đáp án:** Vì max flow thật có thể lớn hơn 10^9, làm phát sinh bottleneck giả.

**Câu 13.** Tách đỉnh rồi chạy max flow có giải luôn min-cost flow không?  
**Đáp án:** Không. Tách đỉnh chỉ tạo mô hình capacity; phải dùng thuật toán phù hợp với mục tiêu chi phí.

**Câu 14.** Mạng tách dùng Dinic có worst-case complexity tổng quát bao nhiêu?  
**Đáp án:** Với V'=2n và E'=n+m, cận tổng quát O(V'²E') = O(n²(n+m)), cộng O(n+m) dựng mạng.

**Câu 15.** Nếu có nhiều nguồn, muốn áp dụng sức chứa một nguồn x, nối super source vào phía nào?  
**Đáp án:** Nối vào **x_in** để luồng đi qua cung nội bộ x_in→x_out.

**Câu 16.** Vì sao câu “có đường đi qua v nên flow tối đa bằng b_v” chưa luôn đúng?  
**Đáp án:** Nếu tồn tại đường s–t khác **không đi qua v**, luồng trên đường ấy không chịu b_v. b_v chỉ chặn tổng luồng thực sự đi qua v.

## 21. Tổng kết

**Tách đỉnh là phép biến đổi mô hình, không phải thuật toán max flow mới.**

Quy trình giải bài **sức chứa trên đỉnh**:

1. Xác định rõ mỗi đỉnh có giới hạn nào, và s,t **có bị giới hạn hay không**.
2. Tạo **v_in**, **v_out** cho mỗi đỉnh v.
3. Thêm **v_in→v_out** có capacity bằng b_v, hoặc một INF đã chứng minh đủ lớn khi không giới hạn.
4. Thay mỗi cung gốc **u→v** bằng **u_out→v_in**, giữ nguyên c(u,v).
5. Dùng **s_out→t_in** khi miễn giới hạn terminal; dùng **s_in→t_out** khi muốn giới hạn cả hai terminal.
6. Chạy một thuật toán max flow chuẩn trên mạng đã tách, ví dụ **Dinic**.
7. Dùng cut hoặc kiểm thử độc lập để xác minh kết quả; nhớ cut có thể bao gồm **cung đỉnh và cung gốc**.
8. Khi bài hỏi các đường đi **không chung đỉnh trung gian**, đặt vertex cap=1 ở các đỉnh trung gian và điều chỉnh edge capacity theo đúng định nghĩa đường đi.
9. Kiểm tra sức chứa không âm, overflow, số nút/cung sau tách và độ sâu DFS nếu dùng đệ quy.

**Câu then chốt:** Sức chứa **cung** giới hạn từng liên kết riêng lẻ; sức chứa **đỉnh** giới hạn **tổng** luồng qua điểm trung chuyển. Cung duy nhất **v_in→v_out** đưa ràng buộc tổng ấy trở về đúng khuôn khổ max flow truyền thống.
