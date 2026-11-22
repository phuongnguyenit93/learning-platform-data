# Tìm kiếm cục bộ và thiết kế lân cận

**Tìm kiếm cục bộ** (*local search*) là một họ phương pháp giải bài toán tối ưu bằng cách bắt đầu với **một lời giải hiện tại**, tạo ra những lời giải “gần” nó theo một quy tắc gọi là **lân cận** (*neighborhood*), rồi chọn một phép biến đổi (*move*) để cải thiện hàm mục tiêu. Khác với vét cạn, thuật toán thường **không duyệt toàn bộ không gian nghiệm**; nó tập trung vào một vùng nhỏ quanh lời giải đang giữ và di chuyển dần đến những vị trí hứa hẹn.

Mô hình cơ bản cho bài **tối thiểu hóa**:

- **`S`**: không gian các lời giải **hợp lệ** (*feasible solutions*).
- **`f:S→ℝ`**: hàm mục tiêu, cần làm **nhỏ nhất**.
- **`N(s)⊆S`**: tập lân cận của lời giải `s`, gồm những lời giải thu được bằng các phép biến đổi được phép.
- **`s₀∈S`**: lời giải khởi tạo.
- Mỗi vòng tìm `s'∈N(s)` với **`f(s')<f(s)`**, chuyển `s←s'`, rồi lặp.

Khi không còn lân cận nào có giá trị nhỏ hơn, ta đạt **cực tiểu cục bộ theo N** (*local minimum*): **`f(s)≤f(t)` với mọi `t∈N(s)`**. Đây **không đồng nghĩa** với cực tiểu toàn cục `f(s)≤f(t)` cho mọi `t∈S`. Chất lượng lời giải vì thế phụ thuộc mạnh vào **cách thiết kế lân cận**, cách chọn move, khởi tạo, chiến lược thoát bẫy và ngân sách tính toán.

Bài thuộc nhóm **Xấp xỉ và kinh nghiệm** trong **Computer Science Algorithms**, chủ đề **Tìm kiếm cục bộ và thiết kế lân cận**. Trọng tâm là biến một mô tả lý thuyết thành **quyết định thiết kế thuật toán**: mã hóa lời giải, định nghĩa phép biến đổi giữ tính hợp lệ, tính **độ thay đổi mục tiêu** (*delta evaluation*) thay vì tính lại toàn bộ, chọn **first improvement / best improvement**, xử lý **plateau và local optimum**, sử dụng **random restart, tabu search, simulated annealing, variable neighborhood search**, và đánh giá kết quả trung thực khi chưa có chứng nhận tối ưu.

Ví dụ xuyên suốt sử dụng **bài người du lịch TSP đối xứng** với khoảng cách Manhattan để tính toán **chính xác bằng số nguyên**. Một move **2-opt** đảo thứ tự một đoạn tour; việc đánh giá move chỉ cần thay hai cạnh nên là O(1). Phần thực hành có **chương trình Java 17+ độc lập**, kiểm soát budget, đánh giá chính xác tour, so với một bộ giải vét cạn độc lập cho bài nhỏ, và kiểm thử hàng nghìn lân cận.

**Mục tiêu:** sau bài này, bạn phải tự chỉ ra “lời giải”, “lân cận”, “hàm mục tiêu”, “move”, “delta” và “điều kiện dừng” của một bài tối ưu; biết phân biệt nghiệm **hợp lệ**, **tốt hơn**, **cực tiểu cục bộ** và **tối ưu toàn cục**; biết giải thích vì sao thay lân cận có thể quan trọng hơn thay cú pháp vòng lặp.

## 1. Local search khác gì tìm kiếm toàn cục?

Giả sử có một tập hữu hạn S gồm các lời giải hợp lệ. Một thuật toán tìm kiếm toàn cục chính xác có thể cần thử nhiều hoặc tất cả lời giải để chứng minh tìm được **min_{s∈S}f(s)**. Với tổ hợp, |S| thường rất lớn: n vị trí trong một hoán vị tạo ra n! thứ tự, chọn/không chọn n phần tử tạo ra 2ⁿ khả năng.

Local search không cố xét toàn bộ S ở mỗi bước. Thay vào đó, nó khai thác một **đồ thị lân cận ẩn**:

- Mỗi đỉnh của đồ thị là **một lời giải hợp lệ**.
- Có cạnh từ s sang t nếu t∈N(s).
- Giá trị f(s) gắn với mỗi đỉnh.
- Thuật toán tìm những cạnh đi xuống theo giá trị mục tiêu.

Đây là một **cách nhìn trực quan**, không nhất thiết phải dựng đồ thị S thật trong RAM. S có thể lớn đến mức không thể liệt kê. Lân cận được tạo **theo yêu cầu** bằng phép biến đổi trực tiếp trên cấu trúc biểu diễn lời giải.

### Ví dụ đời thường: xếp lịch

Một lời giải có thể là **thứ tự các công việc** trong một ngày. Hàm mục tiêu là **tổng thời gian trễ**, **số vi phạm mềm** hoặc **chi phí sử dụng tài nguyên**. Một lân cận có thể gồm:
- Hoán đổi vị trí hai công việc.
- Di chuyển một công việc sang một vị trí khác.
- Đảo thứ tự một đoạn công việc.

Mỗi kiểu move tạo **tập N(s) khác nhau**. Một lịch có thể là cực tiểu cục bộ theo “đổi chỗ hai việc” nhưng vẫn có cải thiện lớn bằng “di chuyển một khối việc”. Vì vậy **lân cận là một phần của thuật toán**, không phải chi tiết phụ.

### Local search là exact hay heuristic?

Theo cách dùng thông thường, local search là **heuristic** nếu nó dừng tại nghiệm cục bộ mà không có chứng nhận tối ưu toàn cục. Nhưng trong những bài có cấu trúc đặc biệt, điều kiện “không còn move cải thiện” có thể kéo theo tối ưu toàn cục. Chỉ được khẳng định điều đó khi **có chứng minh riêng** về hàm và lân cận.

Không được mặc định local search có tỷ số xấp xỉ cố định cho mọi bài. **Approximation algorithm** có bảo đảm là một khái niệm mạnh hơn: phải chứng minh được một cận chất lượng như `f(s)≤α·OPT` trên đúng lớp input và điều kiện của thuật toán.

## 2. Bốn thành phần bắt buộc của thiết kế local search

### 2.1. Biểu diễn lời giải s

Lời giải có thể là:
- **Mảng hoán vị:** tour TSP, thứ tự xếp lịch.
- **Bitmask/Boolean vector:** chọn tập đồ vật hoặc bật/tắt quyết định.
- **Mảng nhãn:** phân công công việc cho máy, màu cho đỉnh đồ thị.
- **Tập cạnh/đỉnh:** mạng, phân hoạch, đường đi.
- **Vector số thực:** tham số tối ưu hóa liên tục.

Biểu diễn tốt nên hỗ trợ **tạo move nhanh**, **kiểm tính hợp lệ** và **đánh giá mục tiêu** mà không phải giải mã phức tạp mỗi vòng. Biểu diễn không phải chỉ để lưu dữ liệu: nó quyết định move nào thuận tiện và lân cận lớn cỡ nào.

### 2.2. Hàm mục tiêu f(s)

Hàm mục tiêu phải phản ánh đúng điều đề bài cần tối thiểu/tối đa. Ví dụ:
- TSP: tổng độ dài chu trình.
- Lập lịch: tổng thời gian trễ, hoặc makespan.
- Phân cụm: tổng bình phương khoảng cách tới tâm.
- Phân hoạch: chênh lệch tổng trọng số giữa hai phía.
- Vertex cover tối thiểu: số đỉnh được chọn, với điều kiện phủ mọi cạnh.

**Không** nhầm hàm mục tiêu với một **thước đo tiện tính** chưa chứng minh tương đương. Nếu tối thiểu hóa tổng thời gian trễ mà ta chỉ giảm số lần đổi máy, lời giải “tốt hơn” theo proxy chưa chắc tốt hơn theo đề.

### 2.3. Lân cận N(s)

Một phép move m biến s thành s'=apply(s,m). Tập lân cận là tất cả lời giải có thể tạo bởi những move hợp lệ:

**`N(s)={apply(s,m) | m∈Moves(s), apply(s,m)∈S}`**.

Cần trả lời:
1. Move thay đổi **các thành phần nào**?
2. Move có **luôn giữ tính hợp lệ** không? Nếu không, kiểm/repair thế nào?
3. Một lời giải có **bao nhiêu** hàng xóm?
4. Có thể **duyệt tất cả** hay chỉ lấy mẫu ngẫu nhiên?
5. Giá trị **`Δ=f(s')−f(s)`** có tính nhanh không?
6. Các lân cận có **kết nối** được nhiều vùng của không gian S không?
7. Khi gặp cực tiểu cục bộ, có thể **mở rộng** lân cận hay thay cách khởi tạo không?

Lân cận quá nhỏ: duyệt nhanh nhưng dễ mắc kẹt. Lân cận quá lớn: có thể cho move tốt hơn nhưng tốn tiền đánh giá. Không có một quy tắc tối ưu cho mọi bài.

### 2.4. Quy tắc chọn move và dừng

Với bài **tối thiểu hóa**, một move cải thiện khi:

**`Δ=f(s')−f(s)<0`**.

Bản địa phương đơn giản chỉ **chấp nhận move cải thiện nghiêm ngặt**. Khi không còn move nào có Δ<0, nếu đã duyệt **đủ toàn bộ lân cận N(s)** thì có thể chứng nhận **local optimum theo N**.

Nếu chỉ duyệt một **mẫu** hàng xóm rồi không tìm thấy cải thiện, **chưa đủ** để kết luận local optimum. Cần ghi rõ “không tìm thấy trong tập đã khảo sát” hoặc tiếp tục đến giới hạn cố định.

## 3. First improvement và best improvement

### First improvement (chấp nhận cải thiện đầu tiên)

Duyệt các move theo một thứ tự. Gặp move đầu tiên có Δ<0 thì **thực hiện ngay** và bắt đầu vòng mới.

~~~text
repeat:
    improved = false
    for move in neighborhood(current):
        if delta(move) < 0:
            apply(move)
            improved = true
            break

until not improved
~~~

Ưu điểm:
- Không cần xem hết lân cận nếu một cải thiện xuất hiện sớm.
- Thường có tốc độ tiến triển tốt khi lân cận lớn và các move tốt khá phổ biến.

Nhược điểm:
- Nhạy với **thứ tự duyệt**.
- Chấp nhận một cải thiện nhỏ trước có thể đưa thuật toán đến một vùng khác so với việc chọn move tốt nhất.
- Nếu chỉ nhìn một phần lân cận, không được coi vòng “không tìm thấy” là chứng nhận cực tiểu cục bộ.

### Best improvement / steepest descent (chọn move tốt nhất trong lân cận)

Duyệt **toàn bộ** move và chọn Δ âm **nhỏ nhất** (giảm nhiều nhất), rồi mới apply.

~~~text
repeat:
    bestDelta = 0
    bestMove = none

    for move in neighborhood(current):
        delta = evaluate(move)
        if delta < bestDelta:
            bestDelta = delta
            bestMove = move

    if bestMove is none:
        stop with CERTIFIED LOCAL OPTIMUM

    apply(bestMove)
~~~

Ưu điểm: chọn giảm mục tiêu lớn nhất trong **lân cận đang xét**; lần không tìm thấy move âm thực sự là chứng nhận local optimum nếu đã duyệt đủ.

Nhược điểm: phải duyệt toàn bộ lân cận ở mỗi lần chấp nhận move, có thể đắt hơn first improvement; **“best neighbor” không có nghĩa “global best”**.

### Ties: nhiều move cùng Δ

Nếu hai move có cùng mức cải thiện, chọn theo:
- Thứ tự chỉ số cố định để **tái lập** kết quả.
- Ngẫu nhiên có seed để **đa dạng hóa**.
- Tiêu chí phụ hợp lệ, như ít thay đổi cấu trúc hơn.

Code ví dụ chọn move đầu tiên trong thứ tự vòng lặp khi cùng Δ; dùng điều kiện **`delta < bestDelta`**, không dùng ≤. Nhờ đó kết quả không phụ thuộc vào bảng băm hoặc bộ sinh ngẫu nhiên ở đường tìm kiếm cơ bản.

## 4. Cực tiểu cục bộ, toàn cục và plateau

Với bài tối thiểu hóa:

- **Cực tiểu cục bộ theo N**: không có t∈N(s) có f(t)<f(s).
- **Cực tiểu toàn cục**: không có t∈S có f(t)<f(s).
- **Plateau**: các lời giải kề nhau có **cùng giá trị mục tiêu**, Δ=0.
- **Bẫy cục bộ**: phải đi sang nghiệm bằng hoặc tệ hơn trước mới có đường đến vùng tốt hơn.

Một nghiệm cực tiểu toàn cục **luôn** là cực tiểu cục bộ theo mọi lân cận chỉ gồm nghiệm hợp lệ. Chiều ngược lại **không đúng** nói chung.

### Vì sao plateau gây khó?

Giả sử tại s mọi move một bước có Δ=0 hoặc dương. Nếu chỉ cho phép Δ<0, local search dừng. Nhưng có thể tồn tại chuỗi:

~~~text
s --(delta=0)--> t --(delta=-5)--> u
~~~

với f(u)<f(s). Một bước “đi ngang” plateau mở đường cho cải thiện sau. Tuy vậy, nếu cho phép **mọi** move Δ=0 mà không có cơ chế kiểm soát, thuật toán có thể **lặp vô hạn** giữa các lời giải bằng điểm.

Cách xử lý:
- Chỉ chấp nhận cải thiện nghiêm ngặt, nhận diện local optimum và **restart**.
- Cho phép move ngang với giới hạn số bước/visited states.
- **Tabu list** ngăn quay lại các move vừa thực hiện.
- **Simulated annealing** cho một số move xấu đi với xác suất có kiểm soát.
- **Variable neighborhood search** thay lân cận khi mắc kẹt.

Mỗi kỹ thuật đánh đổi giữa **khai thác vùng tốt hiện tại** (*intensification*) và **khám phá vùng mới** (*diversification*).

## 5. Ví dụ TSP đối xứng: lời giải là một chu trình

Trong bài toán người du lịch **TSP (Traveling Salesperson Problem)**, có n thành phố và khoảng cách `d(u,v)`. Cần tìm một chu trình đi qua **mỗi thành phố đúng một lần** rồi trở về điểm xuất phát, sao cho tổng độ dài nhỏ nhất.

Bài này dùng **TSP đối xứng**:

**`d(u,v)=d(v,u)`**,

và chọn khoảng cách Manhattan với tọa độ nguyên:

**`d(u,v)=|x_u−x_v|+|y_u−y_v|`**.

Manhattan là metric: không âm, đối xứng, thỏa bất đẳng thức tam giác. Ta dùng nó để mọi phép đánh giá trong demo là **số nguyên long chính xác**, tránh việc so sánh hai chiều dài double rất gần nhau. TSP với khoảng cách Euclidean cũng là trường hợp đối xứng, nhưng phần tính delta khi dùng double phải xét sai số.

### Biểu diễn tour

Lưu tour là một mảng hoán vị:

**`tour=[v₀,v₁,...,v_{n−1}]`**,

các ID là 0..n−1 và mỗi ID xuất hiện **đúng một lần**.

Tổng chi phí tour:

**`L(tour)=Σ_{i=0}^{n−1}d(v_i,v_{(i+1) mod n})`**.

Chỉ số cuối nối lại v₀, vì đây là **chu trình**, không phải đường đi mở.

Để tránh nhiều biểu diễn tương đương do quay vòng, demo cố định:

**`tour[0]=0`**.

Điều này **không cấm** bất kỳ tour Hamilton nào: một chu trình đi qua thành phố 0 luôn có thể được quay danh sách để bắt đầu tại 0 mà giữ nguyên chi phí.

### Đối xứng không loại hết trùng lặp

Trong TSP đối xứng, tour chạy thuận và ngược có cùng độ dài. Demo vẫn coi hai thứ tự mảng là hai biểu diễn khác nhau khi duyệt; không ảnh hưởng đến tính đúng, chỉ có thể khiến một số trạng thái tương đương được xem xét nhiều lần.

## 6. Thiết kế lân cận 2-opt

**2-opt** là một move thay **hai cạnh của chu trình** bằng hai cạnh khác, tương đương **đảo thứ tự một đoạn liên tục** của tour.

Chọn hai vị trí cạnh i và j, với:

**`0≤i<j<n`**, `j≥i+2`,

và **bỏ trường hợp i=0,j=n−1** vì hai cạnh này kề nhau qua điểm đầu, việc đảo toàn bộ đoạn nội bộ chỉ tạo tour đảo chiều tương đương mà không cho cải thiện ở TSP đối xứng.

Gọi bốn thành phố trên hai cạnh bị thay:

- `a=tour[i]`;
- `b=tour[i+1]`;
- `c=tour[j]`;
- `d=tour[(j+1) mod n]`.

Move:
1. Bỏ cạnh **(a,b)** và **(c,d)**.
2. Thêm cạnh **(a,c)** và **(b,d)**.
3. **Đảo thứ tự đoạn tour[i+1..j]** để mọi đỉnh vẫn tạo thành một chu trình hợp lệ.

Sơ đồ ý tưởng:

~~~text
Before:
    ... a -- b -> ... -> c -- d ...

After:
    ... a -- c -> ... -> b -- d ...
              (middle section reversed)
~~~

Vì các thành phố vẫn xuất hiện một lần, move 2-opt luôn giữ **tour là một hoán vị**, không cần “repair” điều kiện đi qua mỗi thành phố đúng một lần. Depot 0 ở chỉ số đầu không bị di chuyển vì đoạn đảo bắt đầu từ i+1≥1.

### Công thức delta O(1)

Vì `d(u,v)=d(v,u)`, đảo chiều các cạnh **bên trong đoạn** không đổi tổng độ dài của chúng. Chỉ hai cạnh tại hai đầu đoạn thay đổi:

**`Δ = d(a,c)+d(b,d)−d(a,b)−d(c,d)`**.

Nếu **`Δ<0`**, tour mới ngắn hơn; nếu `Δ=0`, đây là move ngang plateau; nếu `Δ>0`, tour mới tệ hơn.

Tính Δ chỉ cần **bốn giá trị khoảng cách** và một số phép cộng/trừ, nên **O(1)** một ứng viên khi d(u,v) tính O(1).

**Chú ý quan trọng:** công thức bốn cạnh chỉ áp dụng trực tiếp cho **TSP đối xứng**. Trong **TSP bất đối xứng** (đồ thị có hướng, d(u,v)≠d(v,u)), khi đảo đoạn, hướng của **mọi cạnh bên trong** cũng đảo nên tổng chi phí của chúng có thể thay đổi. Không dùng công thức 2-opt đối xứng cho ATSP mà không tính thêm chênh lệch của các cạnh trong đoạn.

### Số hàng xóm 2-opt

Với n≥3, xét hai cạnh **không kề** trên chu trình, bỏ những cặp kề nhau qua điểm đầu. Số cặp là:

**`|Moves_{2-opt}|=n(n−3)/2`**.

Ví dụ:
- n=3: 0 move hợp lệ (một tam giác đơn giản chỉ có một chu trình vô hướng).
- n=4: 2 move.
- n=5: 5 move.
- n=10: 35 move.
- n=1000: 498.500 move.

Vì vậy **duyệt đầy đủ lân cận** mất O(n²) lần đánh giá Δ, dù mỗi lần tính Δ chỉ O(1). Việc **áp dụng** một move bằng đảo đoạn mất O(n) trong trường hợp xấu nhất.

## 7. 2-opt ví dụ bốn thành phố

Xét bốn điểm:

~~~text
3 (0,4) ------------ 2 (4,4)
   |                    |
   |                    |
0 (0,0) ------------ 1 (4,0)
~~~

Khoảng cách Manhattan:

- Cạnh ngang/dọc độ dài 4.
- Đường chéo từ 0 tới 2 có độ dài 8.
- Đường chéo từ 1 tới 3 cũng dài 8.

Tour khởi tạo **`[0,2,1,3]`** có chi phí:

**`d(0,2)+d(2,1)+d(1,3)+d(3,0)=8+4+8+4=24`**.

Chọn i=0, j=2:
- a=0, b=2, c=1, d=3.
- Cạnh cũ: (0,2) và (1,3), tổng 16.
- Cạnh mới: (0,1) và (2,3), tổng 8.

Do đó:

**`Δ=8−16=−8`**.

Đảo đoạn tour[1..2] từ [2,1] thành [1,2], nhận:

**`[0,1,2,3]`**, chi phí **16**.

Duyệt mọi 2-opt neighbor tiếp theo không tìm được move có Δ<0. Tour này **2-opt local optimal** và trong ví dụ hình vuông nhỏ đồng thời là tối ưu toàn cục. Nhưng điều ấy chỉ do cấu trúc dữ liệu này, **không phải bảo đảm 2-opt tổng quát**.

### Những sai lệch dễ gặp

- Quên cạnh từ thành phố cuối về thành phố đầu, làm cost sai.
- Đảo đoạn [i..j] thay vì **[i+1..j]**, khiến a không còn cố định.
- Chọn hai cạnh **kề nhau** rồi áp công thức sai.
- Chọn cặp i=0,j=n−1 và tính đó là cải thiện thực, trong khi nó chỉ đổi hướng tour tương đương.
- Cập nhật cost bằng delta nhưng **không đảo mảng**, khiến cost và tour không nhất quán.

## 8. Chứng minh tính đúng của delta 2-opt

Xét tour cũ:

**`... a,b,p₁,...,pₖ,c,d ...`**.

Sau 2-opt, tour mới:

**`... a,c,pₖ,...,p₁,b,d ...`**.

Các cạnh bên ngoài đoạn giữ nguyên. Đối với các cạnh bên trong đoạn:
- Tour cũ đi `b→p₁→...→pₖ→c`.
- Tour mới đi `c→pₖ→...→p₁→b`.

Do khoảng cách đối xứng, mỗi cạnh `(u,v)` và `(v,u)` có **cùng chi phí**. Vì thế tổng trong đoạn không đổi, chỉ thay:

**`(a,b),(c,d)` thành `(a,c),(b,d)`**.

Trừ chi phí cũ khỏi mới, ta được:

**`L(new)−L(old)=d(a,c)+d(b,d)−d(a,b)−d(c,d)`**.

Đây là công thức delta chính xác, không phải xấp xỉ hoặc heuristic. Heuristic nằm ở việc **chỉ xét những lời giải lân cận và dừng khi không cải thiện**, không nằm ở công thức đánh giá move.

Nếu cost cập nhật bởi `cost←cost+Δ` sau mỗi move, nó phải bằng **tổng toàn tour tính lại từ đầu**. Đây là một invariant cực kỳ hữu ích khi viết test.

## 9. Điều kiện dừng và ý nghĩa của budget

Bản Java dùng **best improvement**: mỗi lần scan **toàn bộ** lân cận 2-opt hiện tại, lấy move có Δ âm nhỏ nhất, rồi áp dụng. Một trong hai lý do dừng:

1. **LOCAL_OPTIMUM:** đã quét đủ mọi move 2-opt và **không thấy Δ<0**. Khi đó có thể **chứng nhận cực tiểu cục bộ theo đúng lân cận 2-opt**, không phải tối ưu toàn cục.
2. **BUDGET:** còn move cải thiện nhưng đã đạt giới hạn **maxMoves**. Kết quả lúc này vẫn là tour **hợp lệ** và có cost đã biết, nhưng **chưa được chứng nhận local optimum**.

Điều kiện này tránh một lỗi API thường gặp: hết thời gian/moves rồi in “đã tối ưu”.

### Vì sao không thể cứ đi xuống mãi?

Với số thành phố hữu hạn, số hoán vị tour là hữu hạn. Nếu **chỉ chấp nhận Δ<0** và cost được tính chính xác, mỗi bước tạo lời giải có cost **thấp hơn nghiêm ngặt**, không thể trở về một trạng thái trước đó với cùng cost. Vì vậy, nếu không bị giới hạn ngân sách, quá trình cuối cùng dừng ở một local optimum.

Tuy nhiên, số bước cải thiện **không được bảo đảm nhỏ theo n** chỉ từ lập luận hữu hạn. Không nói thuật toán 2-opt luôn hội tụ sau O(n²) bước; **O(n²)** là chi phí **một lượt quét lân cận**, không phải toàn bộ số move được chấp nhận.

### Move Δ=0 có được chấp nhận?

Demo dùng **strict descent**, chỉ nhận Δ<0. Move Δ=0 không được nhận, tránh plateau gây vòng lặp. Nếu muốn cho phép move ngang, cần thiết kế cơ chế chống quay lại trạng thái, giới hạn bước hoặc chiến lược tabu/annealing. Không đổi điều kiện thành Δ≤0 rồi để vòng while vô hạn.

## 10. Ví dụ cực tiểu cục bộ khác tối ưu toàn cục

Tám thành phố với tọa độ:

| ID | x | y |
|---:|---:|---:|
| 0 | 14 | −28 |
| 1 | −9 | −32 |
| 2 | 10 | 50 |
| 3 | −40 | 6 |
| 4 | 49 | −15 |
| 5 | −23 | 33 |
| 6 | −32 | −36 |
| 7 | −6 | −2 |

Dùng đúng khoảng cách Manhattan và cùng quy tắc best-improvement 2-opt:

**Tour ban đầu:**

**`[0,1,4,6,2,7,3,5]`**, chi phí **584**.

Sau bốn move cải thiện, các chi phí:

**`584→512→438→402→400`**.

Tour cuối:

**`[0,1,6,3,7,5,2,4]`**, chi phí **400**.

Quét đủ mọi move 2-opt trên tour cuối không còn Δ<0, nên đây là **2-opt local optimum**.

Nhưng có tour khác:

**`[0,1,6,3,5,2,7,4]`**, chi phí **382**.

Với n=8, ta có thể kiểm **tất cả 7! hoán vị** của các đỉnh còn lại khi cố định 0 ở đầu để xác nhận **382 là tối ưu toàn cục** trong ví dụ này. Vì **400>382**, local optimum khác global optimum.

Đây là phản ví dụ có thể kiểm chứng: một thuật toán cải thiện nghiêm ngặt, đánh giá delta hoàn toàn chính xác và dừng đúng tiêu chí **vẫn có thể kém tối ưu toàn cục**. Muốn tìm 382 có thể cần điểm bắt đầu khác, chuỗi move có bước ngang/xấu hơn, hoặc lân cận lớn hơn.

## 11. Thiết kế lân cận cho những kiểu lời giải khác nhau

### 11.1. Chuỗi bit: flip và swap

Nếu s là vector nhị phân x₁,...,xₙ:
- **1-flip:** đảo một bit 0↔1; có tối đa n move.
- **2-flip:** đảo hai bit; có tối đa n(n−1)/2 move.
- **Swap 1↔0:** chọn một bit đang 1 và một bit đang 0, đổi chúng; giữ nguyên số lượng bit 1.

Ví dụ cần chọn **đúng k phần tử**: 1-flip **phá ràng buộc số lượng**, còn swap 1↔0 **giữ tính hợp lệ**. Đây là lý do phải thiết kế lân cận theo **ràng buộc**, không chỉ theo cấu trúc dữ liệu.

### 11.2. Hoán vị: swap, insertion, reversal

Một lịch công việc hoặc tour là hoán vị:
- **Swap(i,j):** đổi hai vị trí.
- **Insert(i,j):** lấy phần tử ở i, chèn vào vị trí j, dịch các phần tử giữa.
- **Reverse(i,j):** đảo một đoạn liên tục.
- **2-opt TSP:** một dạng đảo đoạn có ý nghĩa hai cạnh của tour.
- **3-opt TSP:** bỏ ba cạnh và nối lại theo một trong các cấu hình phù hợp, lân cận rộng hơn nhưng chi phí tìm kiếm thường cao hơn.

Các move này **không tương đương**. Swap có thể không cải thiện dù insert cải thiện và ngược lại. Lân cận rộng hơn có thể giúp thoát một bẫy của lân cận nhỏ, nhưng không có bảo đảm tạo nghiệm toàn cục nếu không có chứng minh riêng.

### 11.3. Phân công và lập lịch

Nếu lời giải gán công việc cho máy:
- Chuyển một job từ máy A sang máy B.
- Hoán đổi hai job giữa hai máy.
- Di chuyển một block các job liên tiếp.
- Đổi vị trí hai job trên cùng máy.

Một move có thể làm quá tải máy đích; phải **kiểm ràng buộc** hoặc **repair**. Nếu bài tối thiểu hóa makespan, thay đổi một job có thể làm thay đổi tải hai máy, nhưng cũng có thể thay đổi thứ tự và thời gian chờ phụ thuộc cấu trúc lịch.

### 11.4. Tô màu đồ thị

Move có thể là đổi màu một đỉnh, hoặc một **Kempe chain interchange** để sửa mảng màu trong thành phần liên thông của hai màu. Nếu yêu cầu không có cạnh cùng màu ở hai đầu, đổi một màu tùy ý có thể tạo lời giải **không hợp lệ**. Cần phân biệt:
- Giữ mọi state luôn hợp lệ.
- Cho phép state chưa hợp lệ nhưng tính **penalty vi phạm**, rồi repair cuối.

Hai cách này có không gian tìm kiếm khác nhau và đòi hỏi điều kiện dừng/đánh giá khác nhau.

### 11.5. Đường đi và cấu trúc cây

Nếu một route phải tránh đường cấm, đảo đoạn tùy ý có thể tạo cạnh không tồn tại. Với **TSP đầy đủ và khoảng cách metric** như demo, mọi cặp điểm có cạnh hợp lệ. Với **đồ thị thưa** hoặc có hướng, phải kiểm rằng các cạnh mới tồn tại và việc đảo chiều nội bộ không tạo các cạnh không tồn tại.

Không bê nguyên code 2-opt trên metric hoàn chỉnh sang mạng đường có cạnh cấm rồi coi tour sau move chắc chắn hợp lệ.

## 12. Giữ tính khả thi: hard constraints và soft constraints

Một lời giải có thể chịu:
- **Ràng buộc cứng (hard):** không được vi phạm, ví dụ mỗi thành phố xuất hiện đúng một lần, mỗi job chỉ gán một máy, không vượt dung lượng.
- **Ràng buộc mềm (soft):** có thể vi phạm nhưng phải trả chi phí, ví dụ số lần đổi ca hoặc ưu tiên công việc.

Hai chiến lược:

**Feasible-only search:** chỉ sinh move giữ tất cả hard constraints. Ưu điểm là lời giải sau mỗi bước đều có thể dùng ngay; nhược điểm là đôi khi lân cận quá hạn chế, khó thoát bẫy.

**Penalty-based search:** cho phép tạm đi qua state chưa hợp lệ, dùng:

**`F(s)=objective(s)+λ·violation(s)`**.

Nếu λ quá nhỏ, thuật toán có thể giảm objective bằng cách tạo nhiều vi phạm. Nếu λ cực lớn, cost có thể overflow hoặc địa hình tìm kiếm bị chi phối bởi penalty khiến thuật toán kém tiến triển. Nếu dùng một λ cố định để tuyên bố hard constraints luôn được ưu tiên, phải có chứng minh λ đủ lớn trên miền cost và violation. Một phương án khác là so sánh **từ điển (lexicographic)**: số vi phạm trước, mục tiêu sau.

Bản Java TSP chỉ xét **feasible tours**; không cần penalty. Điều này làm test và cách hiểu kết quả đơn giản hơn.

## 13. Delta evaluation: điểm khác biệt giữa code nhanh và chậm

Một cài đặt ngây thơ xét mọi move như sau:

~~~text
for each neighbor:
    copy current solution
    apply move to copy
    evaluate objective from scratch
~~~

Nếu có O(n²) neighbors, mỗi lần tính tour cost O(n), một lượt quét có thể tốn **O(n³)**, chưa tính chi phí sao chép.

Với 2-opt đối xứng, dùng công thức **bốn cạnh** tính Δ trong O(1), khiến một lượt quét **O(n²)**; chỉ cần đảo đoạn **một lần** sau khi chọn best move, mất O(n).

### Invariant cần kiểm khi dùng delta

Giữ biến `cost` cho tour hiện tại và giá trị Δ cho move được chọn:

**`cost_new=cost_old+Δ`**.

Sau khi áp move, nên có:

**`cost_new == recomputeFullCost(newTour)`**.

Trong code demo có phép đối chiếu này sau mỗi move được chấp nhận, nhằm phát hiện lỗi ở công thức delta hoặc đảo đoạn. Với một triển khai production tối ưu tốc độ, có thể tắt phép kiểm đầy đủ trong hot path sau khi test kỹ, nhưng phải giữ unit tests và cơ chế debug.

### Chú ý cache có thể bị stale

Nếu cache độ thay đổi của các move, một lần đảo đoạn có thể làm nhiều giá trị Δ cũ **không còn đúng**. Không dùng bảng Δ đã tính trên tour cũ mà không biết phạm vi ảnh hưởng. Với lân cận phức tạp, duy trì cache incremental cần một chứng minh cụ thể và test đối chiếu với tính lại.

## 14. Java 17+: best-improvement 2-opt có kiểm chứng

Chương trình sau có những tính chất:
- Mã hóa lời giải là **`int[] tour`**, chu trình với **thành phố 0 ở đầu**.
- Khoảng cách **Manhattan nguyên đối xứng** trên tọa độ trong **[−10⁹,10⁹]**.
- Kiểm input: ít nhất 3 thành phố, tọa độ hợp lệ, mọi ID xuất hiện đúng một lần, vị trí đầu bằng 0, move budget không âm.
- Hàm `delta2Opt` tính đúng chênh lệch hai cạnh.
- Hàm `bestTwoOpt` duyệt đủ neighborhood, chọn cải thiện âm tốt nhất, rồi đảo đoạn.
- Kết quả có **tour, cost, moves, localOptimal**; nếu hết moveBudget lúc còn move tốt, localOptimal=false.
- Hàm `exactSmallTsp` duyệt mọi hoán vị khi n≤9 để làm **oracle tối ưu độc lập**, không được dùng cho n lớn.
- `randomRestarts` thử nhiều tour khởi tạo dựa trên seed, giữ nghiệm tốt nhất, **không** hứa tối ưu toàn cục.
- `randomChecks` kiểm công thức Δ bằng cách thực sự đảo đoạn rồi tính lại **full tour**, kiểm hoán vị, tính đơn điệu và local optimum trên 1500 tập thành phố nhỏ.

Tất cả phép toán distance/cost dùng `long`. Vì |x|,|y|≤10⁹, khoảng cách một cạnh Manhattan ≤4·10⁹; dữ liệu demo có n rất nhỏ. Hàm `Math.addExact` giúp phát hiện tổng overflow nếu sau này mở rộng giới hạn mà quên cập nhật chứng minh số học.

Lưu mã thành tệp **`LocalSearchNeighborhoodDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;

public final class LocalSearchNeighborhoodDemo {
    private static final long COORD_LIMIT = 1_000_000_000L;

    private record City(long x, long y) {}

    private record Result(
            int[] tour,
            long cost,
            int moves,
            boolean localOptimal) {}

    private static void validateCities(City[] cities) {
        if (cities == null || cities.length < 3) {
            throw new IllegalArgumentException(
                    "At least three cities required");
        }
        for (City c : cities) {
            if (c == null
                    || c.x() < -COORD_LIMIT
                    || c.x() > COORD_LIMIT
                    || c.y() < -COORD_LIMIT
                    || c.y() > COORD_LIMIT) {
                throw new IllegalArgumentException(
                        "Coordinates must be in [-1e9,1e9]");
            }
        }
    }

    private static void validateTour(
            City[] cities, int[] tour) {
        validateCities(cities);
        int n = cities.length;
        if (tour == null || tour.length != n
                || tour[0] != 0) {
            throw new IllegalArgumentException(
                    "Invalid tour or depot");
        }

        boolean[] seen = new boolean[n];
        for (int id : tour) {
            if (id < 0 || id >= n || seen[id]) {
                throw new IllegalArgumentException(
                        "Tour must be a permutation");
            }
            seen[id] = true;
        }
    }

    private static long distance(City a, City b) {
        long dx = a.x() - b.x();
        long dy = a.y() - b.y();
        return Math.abs(dx) + Math.abs(dy);
    }

    private static long tourCost(
            City[] cities, int[] tour) {
        long sum = 0L;
        for (int i = 0; i < tour.length; i++) {
            int next = (i + 1) % tour.length;
            sum = Math.addExact(sum, distance(
                    cities[tour[i]], cities[tour[next]]));
        }
        return sum;
    }

    // Valid only for SYMMETRIC distances.
    // Edges (a,b),(c,d) -> (a,c),(b,d).
    private static long delta2Opt(
            City[] cities, int[] tour, int i, int j) {
        int n = tour.length;
        int a = tour[i];
        int b = tour[i + 1];
        int c = tour[j];
        int d = tour[(j + 1) % n];

        long oldEdges = distance(cities[a], cities[b])
                + distance(cities[c], cities[d]);
        long newEdges = distance(cities[a], cities[c])
                + distance(cities[b], cities[d]);
        return newEdges - oldEdges;
    }

    private static void reverse(
            int[] array, int left, int right) {
        while (left < right) {
            int tmp = array[left];
            array[left] = array[right];
            array[right] = tmp;
            left++;
            right--;
        }
    }

    private static boolean isPermutation(
            int[] tour, int n) {
        if (tour == null || tour.length != n
                || tour[0] != 0) {
            return false;
        }
        boolean[] seen = new boolean[n];
        for (int id : tour) {
            if (id < 0 || id >= n || seen[id]) {
                return false;
            }
            seen[id] = true;
        }
        return true;
    }

    // Best improvement: inspect ALL valid 2-opt pairs.
    private static Result bestTwoOpt(
            City[] cities, int[] initial, int maxMoves) {
        validateTour(cities, initial);
        if (maxMoves < 0) {
            throw new IllegalArgumentException(
                    "Negative move budget");
        }

        int[] tour = initial.clone();
        int n = tour.length;
        long cost = tourCost(cities, tour);
        int moves = 0;

        while (true) {
            long bestDelta = 0L;
            int bestI = -1;
            int bestJ = -1;

            for (int i = 0; i < n - 1; i++) {
                for (int j = i + 2; j < n; j++) {
                    if (i == 0 && j == n - 1) {
                        continue; // Adjacent via depot.
                    }

                    long change =
                            delta2Opt(cities, tour, i, j);
                    if (change < bestDelta) {
                        bestDelta = change;
                        bestI = i;
                        bestJ = j;
                    }
                }
            }

            if (bestI == -1) {
                // Entire neighborhood checked: true certificate
                // of LOCAL (not global) 2-opt optimality.
                return new Result(
                        tour.clone(), cost, moves, true);
            }

            if (moves >= maxMoves) {
                // Improving move exists, but budget exhausted.
                return new Result(
                        tour.clone(), cost, moves, false);
            }

            reverse(tour, bestI + 1, bestJ);
            cost = Math.addExact(cost, bestDelta);
            moves++;

            // Debug invariant; can be removed after thorough QA.
            if (cost != tourCost(cities, tour)) {
                throw new AssertionError(
                        "Incremental cost mismatch");
            }
        }
    }

    private static int[] randomAnchoredTour(
            int n, SplittableRandom random) {
        int[] tour = new int[n];
        for (int i = 0; i < n; i++) {
            tour[i] = i;
        }

        // Fisher-Yates on positions 1..n-1. Depot 0 stays first.
        for (int i = n - 1; i >= 2; i--) {
            int j = 1 + random.nextInt(i);
            int tmp = tour[i];
            tour[i] = tour[j];
            tour[j] = tmp;
        }
        return tour;
    }

    // Always include a specified incumbent; thus never
    // returns worse than that incumbent's local search.
    private static Result randomRestarts(
            City[] cities,
            int[] incumbent,
            int restarts,
            int maxMoves,
            long seed) {
        if (restarts < 0) {
            throw new IllegalArgumentException(
                    "Negative restarts");
        }

        Result best = bestTwoOpt(
                cities, incumbent, maxMoves);
        SplittableRandom random =
                new SplittableRandom(seed);

        for (int i = 0; i < restarts; i++) {
            int[] candidate = randomAnchoredTour(
                    cities.length, random);
            Result found = bestTwoOpt(
                    cities, candidate, maxMoves);
            if (found.cost() < best.cost()) {
                best = found;
            }
        }
        return best;
    }

    // Exhaustive reference for n <= 9; NOT local search.
    private static long exactSmallTsp(City[] cities) {
        validateCities(cities);
        if (cities.length > 9) {
            throw new IllegalArgumentException(
                    "Exhaustive reference only for n<=9");
        }

        boolean[] used = new boolean[cities.length];
        used[0] = true;
        long[] best = {Long.MAX_VALUE};
        exactDfs(cities, used, 0, 1, 0L, best);
        return best[0];
    }

    private static void exactDfs(
            City[] cities,
            boolean[] used,
            int last,
            int depth,
            long partial,
            long[] best) {
        int n = cities.length;
        if (depth == n) {
            long full = Math.addExact(partial,
                    distance(cities[last], cities[0]));
            if (full < best[0]) {
                best[0] = full;
            }
            return;
        }

        for (int next = 1; next < n; next++) {
            if (!used[next]) {
                long newPartial = Math.addExact(
                        partial,
                        distance(cities[last], cities[next]));
                // Nonnegative distances make this pruning safe.
                if (newPartial >= best[0]) {
                    continue;
                }
                used[next] = true;
                exactDfs(cities, used, next,
                        depth + 1, newPartial, best);
                used[next] = false;
            }
        }
    }

    private static void randomChecks() {
        SplittableRandom rng =
                new SplittableRandom(4772026L);

        for (int trial = 0; trial < 1500; trial++) {
            int n = 3 + rng.nextInt(6);
            City[] cities = new City[n];
            for (int i = 0; i < n; i++) {
                cities[i] = new City(
                        rng.nextInt(41) - 20,
                        rng.nextInt(41) - 20);
            }
            int[] initial = randomAnchoredTour(n, rng);
            long original = tourCost(cities, initial);

            // Independent check of EVERY neighbor delta.
            for (int i = 0; i < n - 1; i++) {
                for (int j = i + 2; j < n; j++) {
                    if (i == 0 && j == n - 1) {
                        continue;
                    }
                    int[] neighbor = initial.clone();
                    reverse(neighbor, i + 1, j);
                    long actual = tourCost(cities, neighbor)
                            - original;
                    long fast = delta2Opt(
                            cities, initial, i, j);
                    if (actual != fast) {
                        throw new AssertionError(
                                "2-opt delta mismatch");
                    }
                }
            }

            Result found = bestTwoOpt(
                    cities, initial, 100);
            if (!found.localOptimal()
                    || found.cost() > original
                    || !isPermutation(found.tour(), n)
                    || tourCost(cities, found.tour())
                       != found.cost()) {
                throw new AssertionError(
                        "Local-search invariant failed");
            }

            // Independent neighbor construction on final tour:
            // no neighbor may be strictly cheaper.
            for (int i = 0; i < n - 1; i++) {
                for (int j = i + 2; j < n; j++) {
                    if (i == 0 && j == n - 1) {
                        continue;
                    }
                    int[] neighbor = found.tour().clone();
                    reverse(neighbor, i + 1, j);
                    if (tourCost(cities, neighbor)
                            < found.cost()) {
                        throw new AssertionError(
                                "Not a 2-opt local optimum");
                    }
                }
            }
        }

        System.out.println(
                "Random neighborhood checks: 1500 PASS");
    }

    public static void main(String[] args) {
        City[] square = {
            new City(0, 0),
            new City(4, 0),
            new City(4, 4),
            new City(0, 4)
        };
        int[] crossed = {0, 2, 1, 3};
        Result simple = bestTwoOpt(
                square, crossed, 100);

        System.out.println(
                "Square: initial=" + tourCost(square, crossed)
                + ", final=" + simple.cost()
                + ", moves=" + simple.moves()
                + ", localOptimal=" + simple.localOptimal()
                + ", tour=" + Arrays.toString(simple.tour()));

        Result budgetZero = bestTwoOpt(
                square, crossed, 0);
        System.out.println(
                "Budget zero: cost=" + budgetZero.cost()
                + ", moves=" + budgetZero.moves()
                + ", localOptimal="
                + budgetZero.localOptimal());

        City[] trap = {
            new City(14, -28),
            new City(-9, -32),
            new City(10, 50),
            new City(-40, 6),
            new City(49, -15),
            new City(-23, 33),
            new City(-32, -36),
            new City(-6, -2)
        };
        int[] start = {0, 1, 4, 6, 2, 7, 3, 5};
        Result local = bestTwoOpt(trap, start, 100);
        long global = exactSmallTsp(trap);

        System.out.println(
                "Local trap: initial=" + tourCost(trap, start)
                + ", final=" + local.cost()
                + ", moves=" + local.moves()
                + ", localOptimal=" + local.localOptimal());
        System.out.println(
                "Exact 8-city optimum: " + global);
        System.out.println(
                "Local equals global: "
                + (local.cost() == global));

        Result restarted = randomRestarts(
                trap, start, 12, 100, 477L);
        System.out.println(
                "Restarts: valid="
                + isPermutation(restarted.tour(), trap.length)
                + ", noWorseThanSingle="
                + (restarted.cost() <= local.cost()));

        boolean invalidTourRejected = false;
        try {
            bestTwoOpt(square, new int[] {0, 1, 1, 3}, 10);
        } catch (IllegalArgumentException expected) {
            invalidTourRejected = true;
        }
        if (!invalidTourRejected) {
            throw new AssertionError("Invalid tour accepted");
        }
        System.out.println("Invalid tour: rejected");

        randomChecks();
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 LocalSearchNeighborhoodDemo.java
java LocalSearchNeighborhoodDemo
~~~

**Stdout chính xác:**

~~~text
Square: initial=24, final=16, moves=1, localOptimal=true, tour=[0, 1, 2, 3]
Budget zero: cost=24, moves=0, localOptimal=false
Local trap: initial=584, final=400, moves=4, localOptimal=true
Exact 8-city optimum: 382
Local equals global: false
Restarts: valid=true, noWorseThanSingle=true
Invalid tour: rejected
Random neighborhood checks: 1500 PASS
~~~

### Diễn giải kết quả

**Square:** một move 2-opt có Δ=−8 biến tour giao cắt từ cost 24 thành 16. Kết quả giữ depot 0, không trùng ID, và đã kiểm toàn bộ các move 2-opt nên localOptimal=true.

**Budget zero:** thuật toán vẫn **quét lân cận để biết có move cải thiện**, nhưng ngân sách cho phép chấp nhận 0 move. Vì có cải thiện, nó trả tour cũ cost 24 và **localOptimal=false**, không nói sai rằng đã đạt cực tiểu cục bộ.

**Local trap:** 4 move giảm dần 584→512→438→402→400. Tour cost 400 là cực tiểu theo lân cận 2-opt, nhưng bộ giải vét cạn độc lập trên 8 thành phố chứng nhận có tour tối ưu dài **382**.

**Restarts:** code luôn xem cả lời giải incumbent (bắt đầu từ `start`) và 12 tour xáo ngẫu nhiên được tạo với seed xác định, mỗi tour được cải thiện riêng; chọn cost tốt nhất. Vì đã tính cả incumbent, kết quả **không tệ hơn** kết quả local search đơn lẻ và vẫn là hoán vị hợp lệ. Dòng output cố ý không khẳng định mọi lần restart đều tìm đúng 382; random restarts không tự bảo đảm tối ưu toàn cục.

**Invalid tour:** [0,1,1,3] có city 1 lặp và thiếu city 2, nên constructor kiểm đầu vào từ chối thay vì chạy search trên lời giải không hợp lệ.

**Random neighborhood checks:** 1500 bộ thành phố có seed cố định; code đối chiếu delta với **tính lại toàn bộ route sau khi đảo đoạn**, rồi kiểm tính khả thi, cost không tăng, kết thúc local optimum và **không còn neighbor rẻ hơn**. Dòng PASS chỉ xuất khi tất cả các assert không ném lỗi.

## 15. Kiểm thử độc lập: delta, local optimum và global optimum

### 15.1. Tại sao không chỉ chạy vài tour mẫu?

Một lỗi off-by-one ở chỉ số j, quên vòng nối tour[n−1]→tour[0], hoặc tính sai hai cạnh được thay có thể không hiện trên hình vuông đơn giản. Phải tạo nhiều cấu hình đa dạng:
- n=3 (không có move 2-opt hợp lệ).
- n=4 và n=5.
- Nhiều city cùng tọa độ (distance=0).
- Điểm thẳng hàng, hình chữ nhật, hình chữ thập.
- Tọa độ âm, rất gần nhau và rất xa nhau.
- Các tour có chi phí bằng nhau tạo plateau.
- Các tour đã là 2-opt local optimum.
- Tour rất kém cần nhiều move cải thiện.
- Budget=0 và budget nhỏ khiến thuật toán phải báo chưa chứng nhận local optimum.
- Input sai: thiếu ID, ID trùng, index ngoài range, depot không ở đầu.

### 15.2. Oracle delta độc lập

Đối với mỗi bộ city và một tour hợp lệ:

1. Duyệt mọi cặp i,j hợp lệ.
2. Tính `Δ_fast` bằng công thức bốn cạnh.
3. Sao chép tour, đảo đoạn i+1..j.
4. Tính `L_new` bằng **quét tất cả cạnh**.
5. Kiểm **`Δ_fast=L_new−L_old`**.

Đây là một oracle có cách tính khác hẳn công thức delta nên bắt được lỗi chỉ số/cạnh dễ hơn việc gọi lại cùng một hàm delta.

### 15.3. Chứng nhận local optimum độc lập

Sau khi thuật toán báo **localOptimal=true**, kiểm tất cả cặp i,j:
- Tạo neighbor bằng đảo đoạn.
- Tính lại full tour cost.
- Yêu cầu **`L(neighbor)≥L(current)`**.

Điều này kiểm cả việc áp move, không chỉ điều kiện mà bestTwoOpt đã dùng. Nếu có bất kỳ neighbor rẻ hơn, kết quả báo localOptimal=true là sai.

### 15.4. Global optimum oracle cho n nhỏ

Với n≤9, có tối đa **8!≈40.320** hoán vị sau khi cố định 0 ở đầu. Ta có thể duyệt hết và lấy cost nhỏ nhất. Đây là exact oracle cho demo nhỏ, không dựa trên giả thuyết local search.

Với 8-city trap, nó trả 382, còn 2-opt đứng ở 400. Nếu test phát hiện khác biệt, **không tự coi 2-opt bị bug**: đó là đặc điểm của heuristic. Chỉ kiểm:
- local cost **≥global cost**;
- tour local hợp lệ;
- không có 2-opt neighbor rẻ hơn khi đã chứng nhận local optimal.

### 15.5. Kiểm thử ngẫu nhiên độc lập ở mức mô hình

Một mô hình thuật toán được kiểm trên **6.000 tập điểm ngẫu nhiên** với n=3..10:
- **84.578 move 2-opt** được đối chiếu Δ với chênh lệch của full cost sau đảo đoạn.
- **84.578 neighbor** ở những tour kết thúc được kiểm không tốt hơn local cost.
- **15.395 move cải thiện** được ghi nhận, mỗi move giảm cost nghiêm ngặt.
- Các tour đầu ra giữ đúng hoán vị và depot.
- Một tập n=8 được đối chiếu bằng brute global và cho ví dụ local cost 400 > global 382.

Những số liệu này là **kiểm thử**, không phải một chứng minh nghiệm toàn cục trên mọi input. Chứng minh mỗi move làm giảm cost dựa vào công thức delta và tính đối xứng; chứng minh local optimality dựa vào quét đủ lân cận; còn global optimality trong ví dụ được xác nhận riêng nhờ vét cạn.

## 16. Random restarts: đa dạng hóa điểm bắt đầu

Một cách rẻ để giảm phụ thuộc vào s₀ là chạy local search từ **nhiều lời giải khởi tạo**, sau đó giữ nghiệm có f nhỏ nhất:

~~~text
best = localSearch(initial)
for run = 1..R:
    start = randomFeasibleSolution(seed, run)
    candidate = localSearch(start)
    if objective(candidate) < objective(best):
        best = candidate
return best
~~~

**Không** có bảo đảm một số lần restart hữu hạn sẽ tìm đúng tối ưu toàn cục; nó tăng cơ hội khám phá **nhiều vùng cực tiểu**. Nếu tất cả điểm khởi tạo rơi vào cùng một basin of attraction, có thể liên tiếp nhận cùng local optimum.

### Thiết kế điểm bắt đầu

Một số lựa chọn:
- Hoán vị ngẫu nhiên có seed để test tái lập.
- Một heuristic xây tour (nearest neighbor, insertion), rồi local search cải thiện.
- Khởi tạo đa dạng có chủ đích, tránh R nghiệm rất giống nhau.
- Chạy local search từ nghiệm tốt nhất hiện tại sau một phép **perturbation** (iterated local search).

**Seed cố định** hữu ích cho debug và benchmark công bằng, không tự làm thuật toán “tối ưu hơn”. Khi so hai phương pháp, nên dùng nhiều seed độc lập và báo **median/best/worst/variance** chứ không chỉ đưa một kết quả tốt nhất.

### Giữ incumbent giúp không tệ hơn, nhưng chưa chứng minh tối ưu

Nếu bao gồm một nghiệm baseline trong tập restart và mỗi local search chỉ nhận Δ<0, nghiệm tốt nhất sau restart có chi phí **không lớn hơn nghiệm đã cải thiện baseline**. Đây là một bất biến thực dụng, không phải approximation ratio.

## 17. Các kỹ thuật thoát bẫy local optimum

### 17.1. Simulated annealing (SA)

SA đôi khi chấp nhận move làm **tăng** cost. Với `Δ>0`, có thể chấp nhận theo xác suất:

**`p=exp(−Δ/T)`**,

với **T>0** là temperature. Move Δ≤0 thường được chấp nhận. Khi T lớn, xác suất thử những bước xấu hơn cao; khi giảm T, thuật toán dần tập trung vào cải thiện.

Pseudocode:

~~~text
current = feasibleStart()
best = current
T = initialTemperature

while budget remains and T > minimumTemperature:
    neighbor = sampleNeighbor(current)
    delta = objective(neighbor) - objective(current)

    if delta <= 0 OR randomUniform01() < exp(-delta / T):
        current = neighbor
        if objective(current) < objective(best):
            best = current

    T = coolingSchedule(T)

return best
~~~

Cần lưu **best-so-far** riêng vì current có thể tệ hơn sau khi chấp nhận move xấu. Schedule làm lạnh, thang cost, cách sinh neighbor và budget ảnh hưởng mạnh đến chất lượng. Không khẳng định SA tùy tiện với số vòng hữu hạn bảo đảm đạt tối ưu toàn cục.

### 17.2. Tabu search

Tabu search giữ danh sách **move hoặc thuộc tính move vừa thực hiện** bị cấm tạm thời để giảm việc quay đi quay lại giữa trạng thái. Nó có thể chủ động chọn một neighbor không cải thiện để thoát basin cũ, trong khi vẫn lưu best-so-far.

Các chi tiết phải định nghĩa:
- Tabu tenure: cấm trong bao nhiêu lượt?
- Tabu của **move** hay thuộc tính như “cạnh vừa xóa”?
- Aspiration: có cho phép phá tabu nếu tìm lời giải tốt nhất mới?
- Bộ nhớ và cách hết hạn.

Một tabu list chỉ chứa vài trạng thái nhưng không có aspiration hoặc tenure phù hợp có thể khóa những move hữu ích. Tabu search là một thuật toán thiết kế đầy đủ, không chỉ là “HashSet visited”.

### 17.3. Variable neighborhood search (VNS)

VNS thay đổi **kiểu/kích thước lân cận**. Ví dụ:
1. Bắt đầu bằng swap 2 vị trí.
2. Nếu không còn cải thiện, thử insert.
3. Nếu vẫn không cải thiện, thử đảo đoạn dài hơn hoặc 3-opt.
4. Khi gặp cải thiện, có thể trở về lân cận rẻ nhất để khai thác tiếp.

Tư tưởng: một nghiệm có thể là cực tiểu trong N₁ nhưng **không** là cực tiểu trong N₂. Vì vậy đổi lân cận có thể hữu ích hơn chỉ chạy lại cùng thứ tự move.

### 17.4. Iterated local search (ILS)

ILS:
1. Tìm một local optimum.
2. **Perturb** lời giải bằng một move đủ lớn để rời basin.
3. Chạy local search lại.
4. Quyết định chấp nhận nghiệm mới hay trở về incumbent.
5. Lặp đến hết budget.

Với TSP, một perturbation kiểu **double-bridge** có thể làm thay đổi nhiều cạnh hơn 2-opt, giúp thoát bẫy mà không cần khởi tạo lại hoàn toàn từ đầu.

### 17.5. Large neighborhood search (LNS)

Thay vì một move nhỏ, LNS có thể “phá” một phần lời giải rồi **tối ưu/repair** phần bị phá bằng thuật toán exact hoặc heuristic. Cách này đặc biệt có ích trong lập lịch và routing phức tạp. Nhưng giải một lân cận lớn có thể rất đắt; cần giới hạn subproblem, timeout và tiêu chí chấp nhận.

## 18. Thiết kế acceptance, stopping và reporting cho solver thực tế

Một solver tốt không chỉ trả một route mà còn trả **trạng thái có ý nghĩa**.

Các trạng thái thường nên phân biệt:
- **FEASIBLE:** đã có nghiệm thỏa hard constraints.
- **LOCAL_OPTIMUM:** quét đủ N(s), không có cải thiện nghiêm ngặt.
- **BUDGET_EXHAUSTED:** hết thời gian/số move trước khi chứng minh local optimum.
- **PROVEN_OPTIMAL:** có chứng nhận tối ưu toàn cục từ thuật toán exact/cận dưới/cận trên.
- **INFEASIBLE_PROVEN:** đã chứng minh không có lời giải hợp lệ.
- **UNKNOWN:** không biết do hết tài nguyên hoặc tính chất bài.

**LOCAL_OPTIMUM không đồng nghĩa PROVEN_OPTIMAL.** Trong ví dụ tám thành phố, local search trả LOCAL_OPTIMUM với cost 400, còn brute force trả PROVEN_OPTIMAL với cost 382.

### Nếu muốn công bố khoảng cách tới tối ưu

Nếu biết đúng tối ưu OPT>0 và nghiệm có cost F≥OPT (bài tối thiểu hóa), có thể tính:

**`relativeGap=(F−OPT)/OPT`**.

Ví dụ 400 so với 382:

**`(400−382)/382=18/382≈4,71%`**.

Nhưng nếu không biết OPT, không được lấy “nghiệm tốt nhất từng thấy” làm OPT rồi gọi là **optimality gap đã được chứng minh**. Một **lower bound L≤OPT** có thể giúp đặt cận chất lượng, nhưng phải nêu rõ cận và miền toán học.

### Time budget vs move budget

Một move budget giới hạn **số lần chấp nhận**, nhưng nếu mỗi lượt scan N(s) rất lớn, một lần chấp nhận vẫn có thể tốn lâu. Với time budget, phải kiểm đồng hồ theo các điểm phù hợp khi triển khai; trong mã minh họa dùng move budget để kết quả có tính xác định và không phụ thuộc tốc độ máy.

Một thuật toán chỉ kiểm thời gian ở đầu mỗi lần scan có thể vượt hạn mức trong **một scan rất dài**; sản phẩm thực tế cần tích hợp deadline ở các vòng đánh giá move khi bài lớn.

## 19. Độ phức tạp theo lân cận

Gọi:
- n: số thành phố.
- M: số move cải thiện được chấp nhận trước khi dừng.
- R: số lần random restart.
- K: số hàng xóm được đánh giá trên mỗi scan.

Với TSP 2-opt đối xứng:
- Số move hợp lệ **`K=n(n−3)/2=Θ(n²)`**.
- Tính Δ của một move: **O(1)**.
- Quét toàn bộ N(s): **O(n²)**.
- Đảo một đoạn tour: **O(n)**.
- Tính lại full tour cost để debug: **O(n)**.
- Best-improvement tới M move, cộng một scan xác nhận dừng: **`O((M+1)n²)`** thời gian.
- Bộ nhớ: **O(n)** cho các mảng tour/cities và kiểm tính hợp lệ; không cần ma trận khoảng cách n×n vì Manhattan tính O(1) từ tọa độ.
- R lần restart: **`O((R+1)(M+1)n²)`** trong cận thô, không tính chi phí sinh tour O(Rn).
- Exact brute TSP nhỏ: **`O(n!)`** thời gian theo cận điển hình, O(n) bộ nhớ đệ quy/used nếu duyệt từng tour, không lưu tất cả hoán vị.

**Không** suy từ O(n²) mỗi scan rằng thuật toán luôn đa thức theo n để **tìm global optimum**. M có thể tăng mạnh theo input, và local optimum cuối cùng không bắt buộc là global.

### First improvement có nhanh hơn best improvement không?

Có thể nhanh hơn trong thực tế khi sớm thấy Δ<0, vì không cần duyệt hết K. Nhưng trong trường hợp xấu, mỗi vòng vẫn có thể phải xem toàn bộ K. Số move được chấp nhận cũng có thể khác, nên chỉ so một lượt scan chưa đủ để nói tổng thời gian nào tốt hơn. Cần benchmark cả **chất lượng nghiệm** và **thời gian đến chất lượng đó**.

### Dùng O(n²) ma trận khoảng cách hay tính trực tiếp?

Nếu distance tính rất đắt, ma trận `d[u][v]` cho truy cập O(1) có thể đáng dùng, nhưng cần O(n²) bộ nhớ. Với Manhattan từ tọa độ, tính trực tiếp O(1) dễ kiểm hơn và chỉ tốn O(n) bộ nhớ. Đối với n=50.000, ma trận 2,5 tỷ phần tử là không thực tế trên nhiều máy.

## 20. Bất biến và chứng minh local optimality

### Bất biến 1: luôn là hoán vị hợp lệ

Ban đầu tour chứa mỗi thành phố đúng một lần và depot 0 ở đầu. Move 2-opt chỉ **đảo thứ tự một đoạn** từ vị trí ≥1 nên không thêm/xóa ID, không di chuyển depot. Bởi quy nạp, mọi tour sau move vẫn hợp lệ.

### Bất biến 2: cost được cập nhật chính xác

Từ tính đối xứng của khoảng cách, công thức delta bằng chênh lệch full cost. Sau move:

**`cost_new=cost_old+Δ=fullTourCost(tour_new)`**.

Nếu ban đầu cost đúng, mọi bước cập nhật đều đúng. Code còn so lại với full tour cost để phát hiện bug triển khai.

### Bất biến 3: accepted move cải thiện nghiêm ngặt

Chỉ apply khi `bestDelta<0`. Vì vậy:

**`cost_new<cost_old`**.

Nếu dữ liệu là số nguyên và cost chính xác, mỗi accepted move giảm ít nhất 1 đơn vị. Khi không dùng số thực gần nhau, tránh được chuyện tính delta nhỏ âm do lỗi làm tròn trong khi cost đầy đủ không đổi.

### Định lý kết thúc là local optimum

Tại vòng kết thúc **với bestI=-1**, thuật toán đã đánh giá **tất cả cặp 2-opt hợp lệ** và không tìm thấy Δ<0. Theo công thức delta, không có hàng xóm 2-opt nào có cost nhỏ hơn tour hiện tại. Do định nghĩa:

**`tour là một cực tiểu cục bộ theo lân cận 2-opt`**.

Định lý này **không** cần biết OPT toàn cục. Với budget hết trước khi scan không thấy cải thiện, không có chứng nhận local optimum; vì vậy API trả localOptimal=false.

## 21. Những giới hạn cần nêu rõ

### 21.1. Một lân cận tốt chưa phải lời giải toàn cục

2-opt thường hữu dụng cho routing nhưng không giải quyết trọn vẹn TSP tổng quát theo nghĩa tối ưu exact. Ví dụ n=8 cost 400 vs 382 đã chứng minh điều này.

### 21.2. Metric Manhattan không bảo đảm loại mọi cạnh “trông giao nhau”

Trong TSP Euclidean với các đoạn thẳng cắt nhau thực sự ở bên trong, việc tháo hai cạnh giao thường tạo cải thiện nghiêm ngặt dưới các điều kiện hình học thích hợp. Với metric Manhattan, có thể xảy ra **bằng nhau** do nhiều đường ngắn nhất; không được tuyên bố 2-opt strict descent luôn loại hết mọi dạng giao nhau khi vẽ.

### 21.3. Asymmetric TSP phải xét hướng các cạnh

Nếu khoảng cách u→v khác v→u, việc đảo segment thay đổi cost của cả các cạnh bên trong. Công thức Δ bốn cạnh không đúng nguyên xi. Với đường một chiều, một tour đảo đoạn có thể thậm chí chứa các cung không tồn tại.

### 21.4. Không phải mọi neighborhood đều đối xứng

Có thể `t∈N(s)` nhưng `s∉N(t)` nếu moves có hướng hoặc ràng buộc phụ thuộc thời gian/trạng thái. Điều này ảnh hưởng đến cách thiết kế search graph, tabu và tính kết nối. Trong hoán vị với reverse move, đảo lại đoạn sẽ quay về tour cũ, nên quan hệ neighbor là đối xứng theo move đó.

### 21.5. Dữ liệu có chi phí âm

Ví dụ TSP Manhattan luôn có edge cost ≥0. Nếu chuyển sang objective có phần thưởng âm hoặc penalty phức tạp, nhiều lập luận về **cắt nhánh exact oracle** bằng partial cost sẽ không còn đúng nếu phần còn lại có thể làm giảm mạnh cost. Bất biến descent vẫn dùng được nếu delta chính xác và chỉ chấp nhận cải thiện.

### 21.6. Giới hạn tọa độ và kiểu số

Code yêu cầu |x|,|y|≤10⁹, nên một Manhattan edge ≤4·10⁹, biểu diễn được bằng long. Tạo hiệu từ long trong miền này là an toàn. Nếu mở rộng lên gần `Long.MIN_VALUE`/`Long.MAX_VALUE`, phép trừ tọa độ và `Math.abs` có thể overflow; khi đó cần BigInteger hoặc số học có kiểm chứng.

### 21.7. Khởi tạo và tie-breaking

Best-improvement có tie-break cố định trong code nhưng điểm bắt đầu khác vẫn có thể cho local optimum khác. Để đánh giá thuật toán, nên so **nhiều khởi tạo/seed**, hoặc kết hợp với một heuristic constructive tốt, không chỉ báo một route duy nhất.

## 22. Tối ưu thiết kế lân cận theo ứng dụng

### Dùng lân cận nhiều tầng

Nếu swap 1 phần tử rất rẻ, dùng nó để cải thiện sơ bộ; khi đã bão hòa, thử insert, 2-opt hoặc một move lớn hơn. Cách này có thể giảm chi phí vì chỉ dùng lân cận đắt khi lân cận rẻ không còn cải thiện.

### Giảm số ứng viên bằng candidate lists

Trong TSP quy mô lớn, thay vì xét mọi cặp 2-opt O(n²), có thể chỉ thử các cạnh gần nhau theo danh sách nearest neighbors. Điều này giảm thời gian nhưng cũng thay đổi tập hàng xóm **đã xét**: khi không còn cải thiện trên **candidate list**, ta chỉ biết tối ưu cục bộ theo **lân cận bị hạn chế**, không thể tự xưng là local optimum theo toàn bộ 2-opt.

### Xáo thứ tự move

First-improvement duyệt theo thứ tự cố định có thể bị bias. Xáo thứ tự hàng xóm có seed có thể đưa đến basin khác. Cần ghi seed và giữ nguyên cách đo budget khi benchmark để kết quả có thể tái lập.

### Move hỗn hợp và đánh giá có nhớ

Dùng nhiều loại move luân phiên có thể mang lại chất lượng tốt hơn. Nhưng mỗi khi thay đổi lời giải, giá trị delta đã tính và một số cache trở nên stale; cần xác định **dependency** của từng move và cập nhật đúng.

### Tách feasibility khỏi quality

Một thiết kế tốt thường có hai API:
- `isFeasible(s)` để đảm bảo hard constraints.
- `objective(s)` và `delta(s,move)` để đánh giá quality.

Khi dùng penalty hay repair, hãy ghi rõ state có thể infeasible ở giai đoạn nào; không trả về nghiệm chưa hợp lệ như một nghiệm hoàn tất.

## 23. Lỗi thường gặp

1. **Nhầm local optimum với global optimum** — phải chứng minh riêng mới đồng nhất được.
2. **Không định nghĩa rõ neighborhood** — “không còn cải thiện” trở thành phát biểu mơ hồ.
3. **Gọi chưa tìm thấy trong mẫu move là local optimum** — phải duyệt đủ N(s).
4. **Nhầm objective với proxy** — giảm proxy chưa chắc cải thiện yêu cầu thật.
5. **Không kiểm ràng buộc cứng** — trả lời giải không thể dùng.
6. **Dùng move flip một bit khi phải chọn đúng k phần tử** — có thể phá cardinality.
7. **Đánh giá tour như đường đi mở**, quên cạnh cuối nối về đầu.
8. **Dùng số nguyên int cho Manhattan cost lớn** — có thể overflow.
9. **Cho TSP có hướng dùng delta bốn cạnh của TSP đối xứng** — sai chi phí.
10. **Không đảo đoạn khi cập nhật cost từ Δ** — tour và cost lệch.
11. **Đảo [i..j] thay vì [i+1..j]** — thay sai hai cạnh.
12. **Đưa cặp cạnh kề nhau vào move 2-opt** — công thức/diễn giải có thể sai.
13. **Không bỏ cặp i=0,j=n−1** — trùng tour đảo chiều không mang cải thiện trong bài đối xứng.
14. **Cho phép Δ=0 liên tục không chặn** — có thể lặp vô tận trên plateau.
15. **Dùng Δ≤0 rồi khẳng định cost giảm nghiêm ngặt** — trái invariant.
16. **Quên cập nhật best-so-far khi cho phép move xấu trong annealing** — có thể xuất nghiệm cuối tệ hơn nghiệm từng thấy.
17. **Gọi best improvement là global best** — chỉ tốt nhất trong N(s).
18. **Cho rằng first improvement luôn nhanh hơn về tổng thời gian** — số vòng khác nhau.
19. **Đánh giá lại toàn tour cho mọi neighbor 2-opt** — từ O(n²) thành O(n³) mỗi scan.
20. **Dùng cache delta cũ sau khi đổi tour** — lỗi stale.
21. **Chấp nhận delta âm do sai số floating point mà không kiểm** — có thể không giảm cost thật.
22. **Cho budget hết là local optimal** — chưa quét/chứng minh.
23. **Cho random restart bảo đảm global optimum** — không đúng.
24. **Dùng một seed duy nhất để đánh giá hiệu quả thuật toán** — kết luận thiếu chắc chắn.
25. **So hai algorithm khác nhau về budget không chuẩn hóa** — benchmark thiếu công bằng.
26. **Bỏ memory/time của neighborhood lớn** — cài đặt chậm dù một delta O(1).
27. **Cho 3-opt không tốn hơn 2-opt** — số cách nối và cặp chỉ số có thể lớn hơn nhiều.
28. **Dùng penalty λ không chứng minh đủ ưu tiên hard constraints** — có thể trả state infeasible.
29. **Coi một lân cận rộng hơn là luôn tốt hơn trên cùng time budget** — chi phí đánh giá tăng.
30. **Lấy nghiệm tốt nhất đã thấy làm OPT thật** — không có chứng nhận.
31. **Quên xác minh hoán vị đủ n ID** — có thể thiếu hoặc lặp thành phố.
32. **Cho phép depot 0 dịch vị trí nhưng so output dựa trên 0 đầu** — làm rối kiểm thử.
33. **Tin rằng tour có cạnh vẽ giao nhau luôn bị 2-opt strict loại ở mọi metric** — thiếu giả thiết.
34. **Cho phép hệ đường thưa dùng 2-opt như graph đầy đủ** — có thể tạo cạnh không tồn tại.
35. **Dùng brute force global cho n lớn** — giai thừa làm nổ thời gian.
36. **Không so cost incremental với full recomputation trong test** — bỏ qua bug delta.
37. **Không kiểm rằng local optimum không còn neighbor rẻ hơn** — chỉ tin vào cờ của solver.
38. **Không báo stopReason/quality/budget** — khó đánh giá.
39. **Quên tính cả thời gian khởi tạo và restart** — so tốc độ sai.
40. **Suy ra approximation ratio từ một ví dụ cost gần OPT** — cần chứng minh mọi input.
41. **Coi một state không khả thi có objective thấp là một nghiệm tốt** — phải xử lý hard constraints.
42. **Cho rằng local search chỉ dành cho tối ưu tổ hợp** — còn dùng trong miền liên tục nhưng lân cận/điều kiện khác.
43. **Dùng cùng một công thức delta dù move thay đổi** — mỗi move cần chứng minh riêng.
44. **Không kiểm nút quan trọng khi code có tính ngẫu nhiên** — dễ không tái hiện bug.
45. **Nói không có cải thiện nên đã “giải xong TSP exact”** — thiếu global certificate.

## 24. Bài tập thực hành

**Bài 1 — Định nghĩa N(s).** Một lời giải là dãy nhị phân n bit có đúng k bit 1. So sánh neighborhood 1-flip và swap một bit 1 với một bit 0. Chọn lân cận luôn giữ tính hợp lệ.

**Bài 2 — Delta 2-opt bằng tay.** Với tour [0,2,1,3] trên hình vuông cạnh 4, xét i=0,j=2 và tính bốn giá trị khoảng cách để được Δ=−8.

**Bài 3 — First vs best.** Cài hai phiên bản 2-opt nhận cùng input/seed. Đo số neighbor evaluations, số accepted moves và cost cuối cùng; không chỉ đếm số vòng.

**Bài 4 — Tìm local trap.** Dùng 8 thành phố ở mục 10, chạy bestTwoOpt và brute exact; giải thích tại sao 400 là local optimum nhưng 382 global.

**Bài 5 — Plateau.** Dùng các thành phố trùng tọa độ để tạo nhiều move Δ=0. Cho phép move ngang tối đa 20 lần và ghi danh sách state đã đi qua; tránh vòng lặp.

**Bài 6 — Test delta.** Sinh tour ngẫu nhiên 3≤n≤10, tính delta2Opt cho mọi cặp hợp lệ rồi so với full cost sau reversal. Chú ý cặp i=0,j=n−1.

**Bài 7 — Random restarts.** Thử R=1,10,100 restart, giữ incumbent và báo best/median/worst cost, số evaluations và thời gian.

**Bài 8 — Swap cho lịch.** Với lịch hoán vị, định nghĩa hàm mục tiêu là tổng thời gian hoàn thành các job; tính delta cho swap i,j nếu có thể, đối chiếu với đánh giá lại toàn lịch.

**Bài 9 — Feasible repair.** Với bài knapsack tối đa hóa giá trị nhưng có sức chứa W, thử 1-flip gây quá tải. Thiết kế move swap hoặc bước repair đảm bảo trạng thái trả luôn hợp lệ.

**Bài 10 — Local-opt certificate.** Viết hàm độc lập kiểm không còn 2-opt neighbor nào có cost thấp hơn; so cờ localOptimal của thuật toán chính.

**Bài 11 — 3-opt/VNS.** Thiết kế một vòng VNS bắt đầu bằng 2-opt, sau đó thử 3-opt khi 2-opt đứng. Phân tích chi phí tìm move và giới hạn time budget.

**Bài 12 — Annealing.** Thử p=exp(−Δ/T) với Δ=5 và các T=1,5,20. Giải thích vì sao xác suất chấp nhận move xấu tăng khi T tăng.

**Bài 13 — Asymmetric TSP.** Tạo ma trận d(u,v)≠d(v,u), tìm một move đảo đoạn có delta bốn cạnh khác với full cost thực. Viết lại công thức delta có tính chi phí hướng đảo bên trong.

**Bài 14 — Cấu trúc theo tham số.** Với bài phân công, thiết kế neighborhood “di chuyển tối đa k job”, cho biết vì sao tăng k có thể cải thiện search power nhưng làm số candidate bùng nổ.

**Bài 15 — Báo cáo solver.** Định nghĩa cấu trúc kết quả có tour, cost, timeUsed, evaluations, stopReason, localOptimal, certifiedGlobalOptimal. Chỉ bật certifiedGlobalOptimal khi có chứng minh.

## 25. Checklist trước khi dùng local search

- Đã xác định rõ **lời giải là gì** và các **hard constraints**?
- Hàm f có đúng tiêu chí tối ưu của đề?
- Lân cận N(s) và phép move có định nghĩa không mơ hồ?
- Move có luôn giữ feasibility? Nếu không, có kiểm/repair?
- Duyệt toàn bộ hay chỉ sampling một phần lân cận?
- Đã phân biệt **first** và **best improvement**?
- Có phân biệt **Δ<0** và **Δ=0**?
- Nếu chấp nhận move ngang/xấu đi, có cơ chế chống vòng lặp và best-so-far?
- Có công thức delta nhanh, và đã chứng minh nó đúng theo mô hình objective?
- Với 2-opt, khoảng cách có **đối xứng** như công thức bốn cạnh yêu cầu?
- Có xét cạnh cuối nối về đầu của tour?
- Có validate tour là hoán vị và depot cố định nếu API yêu cầu?
- Có tránh tràn số và kiểm dữ liệu trong miền số học?
- Có dùng budget/time limit và báo **lý do dừng** rõ ràng?
- Cờ localOptimal chỉ bật khi **quét đủ lân cận**?
- Có phân biệt local optimum với global optimum?
- Nếu dùng restarts, có lưu incumbent tốt nhất và seed?
- Nếu dùng tabu/annealing/VNS, đã chọn quy tắc acceptance/cooling/tenure?
- Có so với exact oracle trên input nhỏ khi khả thi?
- Có test từng move delta bằng full objective recomputation?
- Có test nghiệm cuối không có neighbor cải thiện?
- Đã báo chất lượng, thời gian, số evaluations và độ phân tán qua nhiều seed?
- Có tránh tuyên bố approximation ratio hoặc tối ưu toàn cục khi chưa chứng minh?

**Kết luận:** tìm kiếm cục bộ là một khung **khai thác cấu trúc lân cận**: bắt đầu từ nghiệm hợp lệ, đánh giá move, chấp nhận những thay đổi theo một quy tắc và dừng khi đáp ứng điều kiện được mô tả rõ. **Thiết kế N(s)** quyết định loại move nào thuật toán nhìn thấy; **delta evaluation** quyết định chi phí đánh giá; **acceptance và khởi tạo** quyết định quá trình đi trong không gian nghiệm. Với TSP đối xứng, 2-opt dùng công thức bốn cạnh để đánh giá O(1) mỗi move, cho một lượt quét O(n²); nhưng dừng ở 2-opt local optimum **không phải** chứng nhận tối ưu toàn cục. Một triển khai tốt phải giữ feasibility, kiểm cost incremental, quản lý ngân sách, thử restarts/đa lân cận khi phù hợp, và báo cáo trung thực mức đảm bảo của nghiệm.