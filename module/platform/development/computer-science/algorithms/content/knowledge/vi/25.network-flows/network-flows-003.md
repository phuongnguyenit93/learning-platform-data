# Định lý luồng cực đại–lát cắt cực tiểu

**Định lý luồng cực đại–lát cắt cực tiểu (Max-Flow Min-Cut Theorem)** là kết quả nền tảng của **luồng mạng (network flow)**. Nó phát biểu rằng **giá trị luồng lớn nhất có thể gửi từ nguồn s tới đích t đúng bằng dung lượng nhỏ nhất của một lát cắt ngăn s khỏi t**:

`max |f| = min_{(S,T)} c(S,T)`

Phát biểu này kết nối hai cách nhìn rất khác nhau: **luồng** là một phương án vận chuyển trên các cung, còn **lát cắt** là một giới hạn cấu trúc của mạng. Một luồng bất kỳ cho ta **cận dưới** đối với luồng cực đại; một lát cắt bất kỳ cho ta **cận trên**. Khi tìm được luồng và lát cắt **có cùng giá trị**, ta có **chứng chỉ tối ưu (optimality certificate)**, không cần tin vào thuật toán như một “hộp đen”.

Bài thuộc nhóm **Luồng mạng** của Computer Science Algorithms. Các phần sau đi từ định nghĩa công suất, bảo toàn dòng, lát cắt, mạng dư và đường tăng tới **chứng minh định lý**, thuật toán **Ford–Fulkerson / Edmonds–Karp**, cách lấy lát cắt cực tiểu sau khi tìm luồng cực đại, ví dụ giá trị **23**, những sai lầm với cung ngược, cạnh song song và dung lượng 0, mã **Java 17+** chạy độc lập, phép kiểm chứng bằng duyệt toàn bộ lát cắt ở đồ thị nhỏ, và bài tập tự luyện có lời giải.

## 1. Đặc tả mạng luồng

Một **mạng luồng** là một đồ thị **có hướng** `G=(V,E)`, có hai đỉnh phân biệt:

- `s` (*source*): nguồn phát luồng.
- `t` (*sink*): đích nhận luồng; yêu cầu `s≠t`.
- Mỗi cung `(u,v)` có **dung lượng (capacity)** không âm `c(u,v)≥0`.
- Có thể có nhiều cung song song từ u tới v; nếu mô hình giữ từng cung riêng, mỗi cung có dung lượng riêng.
- Có thể có cung u→v và v→u cùng tồn tại; đây là **hai cung gốc khác nhau**, không phải mặc nhiên là một cặp cạnh dư.
- Khuyên u→u không giúp vận chuyển ròng từ s tới t. Trong bài và mã minh họa, khuyên được chấp nhận nhưng không làm tăng luồng hay dung lượng lát cắt.

**Dung lượng** là số đơn vị tối đa có thể vận chuyển trên **một cung**, không phải lượng luồng đang thực sự đi qua cung đó. Nếu đường s→a có dung lượng 10 và a→t có dung lượng 3, ta không thể gửi 10 đơn vị đến t qua a; nút thắt a→t giới hạn tuyến này ở 3.

### Luồng hợp lệ (feasible flow)

Với mỗi **cung gốc** e, chọn một giá trị `f(e)` thỏa hai nhóm ràng buộc:

**(1) Dung lượng / không âm:**

`0 ≤ f(e) ≤ c(e)`

**(2) Bảo toàn tại mọi đỉnh trung gian v≠s,t:**

`Σ_{e đi vào v} f(e) = Σ_{e đi ra v} f(e)`

Tại nguồn và đích, ta cho phép có dòng ròng phát/nhận. Giá trị luồng là **lượng ròng phát từ s**:

`|f| = Σ_{e đi ra s} f(e) − Σ_{e đi vào s} f(e)`

Theo bảo toàn tại đỉnh trung gian, nó cũng bằng **lượng ròng đến t**:

`|f| = Σ_{e đi vào t} f(e) − Σ_{e đi ra t} f(e)`

**Mục tiêu max flow:** tìm luồng hợp lệ f có `|f|` lớn nhất.

### Vì sao dùng “ròng” chứ không chỉ cộng cung ra nguồn?

Nếu mạng có cung đi **về nguồn s**, một nghiệm tổng quát có thể có dòng trên cung đó. Lượng phát thực là **ra trừ vào**, không chỉ tổng dòng đi ra. Tương tự, phải lấy **vào trừ ra** tại đích. Các thuật toán tìm luồng đơn giản thường không tạo dòng về nguồn, nhưng định nghĩa toán học cần đúng cho mọi luồng hợp lệ.

Với cạnh song song, mỗi cạnh được tính độc lập trong tổng. Với khuyên u→u, lượng vào và ra ở cùng đỉnh triệt tiêu nhau; khuyên không vượt một lát cắt.

## 2. Lát cắt s–t và dung lượng của lát cắt

Một **lát cắt s–t (s–t cut)** là cách chia đỉnh thành hai tập:

`S ∪ T = V, S ∩ T = ∅, s∈S, t∈T`.

**Dung lượng của lát cắt** chỉ cộng dung lượng các **cung gốc đi từ S sang T**:

`c(S,T) = Σ_{u∈S, v∈T, e=(u,v)} c(e)`.

**Không cộng cung từ T trở lại S.** Đây là điểm đặc biệt quan trọng với mạng **có hướng**. Một cung T→S có thể hiện diện và mang dung lượng rất lớn, nhưng **không góp vào c(S,T)** theo định nghĩa.

**Lát cắt cực tiểu (minimum cut)** là lát cắt có dung lượng nhỏ nhất trong tất cả cách phân hoạch hợp lệ với s∈S và t∈T.

### Ví dụ nhỏ

~~~text
s --(5)--> a --(3)--> t
 \----------------(2)--> t

Cung s->a dung lượng 5
Cung a->t dung lượng 3
Cung s->t dung lượng 2
~~~

Nếu chọn `S={s,a}`, `T={t}`, các cung đi từ S sang T là a→t (3) và s→t (2), nên:

`c(S,T)=3+2=5`.

Nếu chọn `S={s}`, `T={a,t}`, các cung đi ra S là s→a (5) và s→t (2), nên `c(S,T)=7`.

Ta có thể gửi 3 đơn vị theo s→a→t và 2 đơn vị theo s→t, tổng **5**. Đây là luồng cực đại vì đã đạt cận trên của lát cắt dung lượng 5.

**Không nhầm “số cạnh bị cắt” với “tổng dung lượng cạnh bị cắt”.** Cắt hai cung dung lượng 3 và 2 có giá trị 5, không phải 2.

## 3. Bất đẳng thức nền tảng: mọi luồng không vượt mọi lát cắt

Với **bất kỳ luồng hợp lệ f** và **bất kỳ lát cắt (S,T)**, bảo toàn tại các đỉnh thuộc S trừ nguồn cho:

`|f| = Σ_{u∈S,v∈T} f(u,v) − Σ_{u∈T,v∈S} f(u,v)`.

Đây gọi là **luồng ròng qua lát cắt**. Các cung có hai đầu cùng ở S triệt tiêu khi cộng lượng vào/ra của toàn bộ S; chỉ còn những cung đi qua biên.

Vì `f(u,v)≤c(u,v)` trên các cung S→T, và `f(u,v)≥0` trên các cung T→S, ta suy ra:

`|f| ≤ Σ_{S→T} f(e) ≤ Σ_{S→T} c(e) = c(S,T)`.

Vậy:

`|f| ≤ c(S,T)` với **mọi** luồng hợp lệ và lát cắt hợp lệ.

Lấy giá trị lớn nhất ở vế trái và nhỏ nhất ở vế phải:

`maxflow ≤ mincut`.

Đây là **chiều dễ** của định lý. Nó cho thấy một lát cắt có dung lượng K là chứng cứ **không thể** gửi nhiều hơn K đơn vị từ s tới t.

Để chứng minh **dấu bằng**, ta cần chỉ ra một luồng f và một lát cắt có `|f|=c(S,T)`. Công cụ để làm điều này là **mạng dư (residual network)**.

## 4. Mạng dư và ý nghĩa của cung ngược

Giả sử cung gốc `e=(u,v)` có dung lượng c và đang chở f.

**Cung dư thuận u→v** có dung lượng:

`r_forward = c−f`

Nó cho biết còn có thể **tăng** bao nhiêu đơn vị trên cung gốc.

**Cung dư ngược v→u** có dung lượng:

`r_reverse = f`

Nó cho biết có thể **hủy/giảm** bao nhiêu luồng đã gửi trước đó qua cung gốc, để phân phối lại cho một tuyến tốt hơn.

Một cung dư là **khả dụng** khi dung lượng dư của nó **lớn hơn 0**. Các cung dư có dung lượng 0 không thể đi qua trong đường tăng.

### Ví dụ một cung đơn lẻ

~~~text
Cung gốc:       u -- capacity 9 --> v
Đang gửi:       f = 4

Trong mạng dư:
u -- residual 5 --> v
v -- residual 4 --> u
~~~

Nếu tăng thêm 3 qua cung thuận, f trở thành 7; dư thuận còn 2 và dư ngược trở thành 7.

Nếu đi qua cung **dư ngược** với lượng 2, luồng gốc giảm từ 4 xuống 2; dư thuận tăng lên 7, dư ngược giảm còn 2. Cung ngược **không đồng nghĩa** đã xuất hiện một cung gốc v→u mới: nó là thao tác **hoàn tác** phần luồng trên cung u→v.

**Nếu đồ thị gốc còn có cung v→u riêng**, mạng dư phải chứa đồng thời các cặp dư ứng với **hai cung gốc riêng biệt**. Khi cài đặt, hãy liên kết mỗi cung thuận với **đúng cung ngược dư** của nó; không gộp sai các cung antiparallel.

### Tại sao cung dư ngược là thiết yếu?

Xét bốn đỉnh s,a,b,t, mỗi cung có dung lượng 1:

~~~text
s -> a
s -> b
a -> b
a -> t
b -> t
~~~

Nếu một cách tìm đường tăng **chọn trước** `s→a→b→t`, nó gửi 1 đơn vị và làm cạnh a→b đầy. Nếu chỉ cho phép tăng trên các cung gốc thuận, ta có thể lầm tưởng không còn cách gửi thêm một đơn vị.

Nhưng trong mạng dư xuất hiện cung **b→a** dư ngược của a→b. Đường tăng tiếp theo là:

`s→b→a→t`

Dùng b→a **hủy** dòng trước đây trên a→b, đồng thời gửi qua s→b và a→t. Kết quả cuối cùng là hai tuyến:

- s→a→t: 1 đơn vị.
- s→b→t: 1 đơn vị.

Tổng luồng tối ưu **2**, không phải 1.

Ví dụ này minh họa tính cần thiết của cung ngược với **phương pháp đường tăng nói chung**. BFS Edmonds–Karp có thể chọn những đường đi ngắn hơn ngay từ đầu trên đồ thị nhỏ này; **không** khẳng định thuật toán BFS nhất thiết đi theo thứ tự “sai” vừa mô tả.

## 5. Đường tăng và lượng nút thắt

Một **đường tăng (augmenting path)** là đường đi từ s đến t trong mạng dư, trên đó **mọi cung dư có dung lượng >0**.

Với một đường tăng P, lượng tăng tối đa trên đường là:

`Δ = min_{e∈P} residual(e)`

Đây gọi là **bottleneck capacity (dung lượng nút thắt)**.

Tăng luồng thêm Δ bằng cách, với **mỗi cung dư e trên P**:

~~~text
e.residual         -= delta
e.reverse.residual += delta
~~~

Hai thao tác này thống nhất cho cả cung dư thuận lẫn cung dư ngược. Nếu e là cung ngược dư, giảm residual(e) và tăng residual(e.reverse) tương đương **giảm luồng gốc đã đi trước**.

### Ba bất biến sau mỗi phép tăng

1. **Giới hạn dung lượng:** mỗi cung gốc vẫn có `0≤f(e)≤c(e)`.
2. **Bảo toàn tại các đỉnh trung gian:** P đi qua một cung vào và một cung ra của mỗi đỉnh trung gian, nên thay đổi dòng ròng bằng 0 tại đỉnh ấy.
3. **Giá trị luồng tăng đúng Δ:** tại s có thêm Δ dòng ròng phát; tại t có thêm Δ dòng ròng nhận.

Như vậy, bắt đầu từ **luồng 0**, mỗi phép tăng hợp lệ tạo ra một luồng hợp lệ mới với giá trị lớn hơn. Nếu dung lượng là **số nguyên**, Δ là số nguyên dương và mọi luồng sau tăng giữ nguyên tính nguyên.

**Lưu ý:** một đường tăng trong mạng dư có thể dùng các cung ngược, nên đường tìm thấy không nhất thiết trùng một đường đi hoàn toàn bằng cung gốc. Nó mô tả **phương án điều chỉnh luồng**, không chỉ vận chuyển trên một tuyến mới.

## 6. Định lý luồng cực đại–lát cắt cực tiểu

### Phát biểu đầy đủ

Cho mạng có hướng, dung lượng không âm hữu hạn, nguồn s và đích t phân biệt. Với một luồng hợp lệ f, ba mệnh đề sau **tương đương**:

1. **f là luồng cực đại.**
2. **Không có đường tăng s→t trong mạng dư của f.**
3. **Tồn tại một lát cắt (S,T) sao cho `|f|=c(S,T)`.**

Hệ quả trực tiếp:

`max_{f hợp lệ} |f| = min_{S∋s, t∉S} c(S,V∖S)`.

### Chứng minh chiều (3) ⇒ (1)

Nếu có một luồng f và một lát cắt dung lượng K với `|f|=K`, mà theo bất đẳng thức ở mục 3 **mọi luồng** đều ≤K, thì không thể có luồng giá trị lớn hơn f. Do đó f cực đại và lát cắt ấy cực tiểu.

Đây là cách **xác minh nghiệm** cực kỳ hữu ích: chỉ cần so hai số và kiểm tra nghiệm/lát cắt hợp lệ.

### Chứng minh chiều (2) ⇒ (3): dựng lát cắt từ mạng dư

Giả sử không còn đường tăng từ s đến t. Xét tập:

`S = {v∈V : có đường đi từ s tới v qua các cung dư dương}`.

Đặt `T=V∖S`. Nguồn s thuộc S vì đi 0 cạnh là được; đích t **không** thuộc S do giả thiết không có đường tăng. Vì vậy (S,T) là một lát cắt s–t hợp lệ.

**Xét một cung gốc u→v với u∈S và v∈T.** Nếu dung lượng dư thuận `c−f>0`, từ s ta có thể đi tới u rồi đi tiếp u→v, làm v thuộc S — mâu thuẫn. Vì thế `c−f=0`, tức **f=c**: mọi cung gốc đi **từ S sang T** đều **bão hòa**.

**Xét một cung gốc v→u với v∈T và u∈S.** Nếu nó mang dòng `f>0`, thì trong mạng dư tồn tại cung ngược u→v có dung lượng f>0; từ s tới u rồi tới v cũng làm v thuộc S — mâu thuẫn. Vì thế **mọi cung gốc từ T sang S có f=0**.

Giá trị luồng ròng qua lát cắt thỏa:

`|f| = Σ_{S→T} f(e) − Σ_{T→S} f(e)`

`= Σ_{S→T} c(e) − 0 = c(S,T)`.

Từ chiều (3) ⇒ (1), f cực đại và (S,T) cực tiểu. Đây chính là cách **truy xuất lát cắt cực tiểu sau khi tính max flow**: BFS/DFS trong mạng dư từ s, chỉ đi qua cung còn dung lượng dư dương.

### Chứng minh chiều (1) ⇒ (2)

Nếu còn đường tăng P với bottleneck Δ>0, ta có thể tăng giá trị luồng từ `|f|` lên `|f|+Δ` mà vẫn hợp lệ (mục 5), mâu thuẫn với việc f đã cực đại. Vì vậy luồng cực đại không thể còn đường tăng.

Kết hợp ba chiều: **tối ưu luồng ⇔ không còn đường tăng ⇔ luồng bằng dung lượng một lát cắt**.

### Điều kiện bão hòa trên lát cắt cực tiểu

Khi f cực đại và (S,T) là lát cắt cực tiểu:

- Mọi cung gốc S→T phải **bão hòa**: `f(e)=c(e)`.
- Mọi cung gốc T→S phải có **dòng 0**.
- Cung nội bộ S→S hoặc T→T không ảnh hưởng trực tiếp đến dung lượng cắt.

Không nên đánh giá lát cắt bằng “mỗi cung qua biên đã từng được dùng hay chưa”; các cung từ **T sang S** đóng góp theo dấu **trừ** trong luồng ròng nhưng **không** được cộng vào dung lượng lát cắt.

## 7. Ví dụ chuẩn: giá trị cực đại 23

Xét mạng có hướng gồm 6 đỉnh `0..5`; nguồn `s=0`, đích `t=5`. Mỗi bộ `u→v:capacity` là một cung **có hướng**:

| Cung | Dung lượng | Cung | Dung lượng |
| --- | ---: | --- | ---: |
| 0→1 | 16 | 0→2 | 13 |
| 1→2 | 10 | 2→1 | 4 |
| 1→3 | 12 | 3→2 | 9 |
| 2→4 | 14 | 4→3 | 7 |
| 3→5 | 20 | 4→5 | 4 |

**Đừng gộp** cung 1→2 với cung 2→1: chúng là hai cung gốc độc lập.

Với Edmonds–Karp (BFS trên mạng dư) và thứ tự danh sách kề đúng như bảng input của chương trình ở dưới, ba lần tăng có thể diễn ra như sau:

| Lần tăng | Đường tăng | Bottleneck Δ | Tổng luồng |
| ---: | --- | ---: | ---: |
| 1 | 0→1→3→5 | 12 | 12 |
| 2 | 0→2→4→5 | 4 | 16 |
| 3 | 0→2→4→3→5 | 7 | 23 |

Sau cùng, không còn đường tăng 0→5. Trong mạng dư, những đỉnh vẫn **tới được từ 0** là:

`S={0,1,2,4}`.

Phần còn lại:

`T={3,5}`.

Các cung gốc đi **từ S sang T** là:

~~~text
1 -> 3    capacity 12
4 -> 3    capacity 7
4 -> 5    capacity 4
------------------------
cut capacity       23
~~~

Cung `3→2` đi từ T trở về S, nên **không được cộng** dung lượng 9 của nó vào lát cắt. Tất cả các cung S→T đều bão hòa, và luồng ròng qua lát cắt là 23.

Vì đã xây được **luồng hợp lệ giá trị 23** và **lát cắt dung lượng 23**, định lý xác nhận:

`maxflow(0,5)=mincut(0,5)=23`.

Một lịch sử tăng khác có thể cho **phân bố luồng trên từng cạnh** khác nhau. Tổng max flow luôn bằng 23; lát cắt cực tiểu cũng có thể không duy nhất khi dung lượng hòa. **Không nhất thiết có một nghiệm luồng duy nhất.**

## 8. Ford–Fulkerson và Edmonds–Karp

### Ford–Fulkerson: khung đường tăng

Phương pháp Ford–Fulkerson bắt đầu bằng **luồng 0**, liên tục:

1. Dựng/duy trì mạng dư.
2. Tìm **bất kỳ** đường tăng từ s tới t.
3. Tính bottleneck Δ và cập nhật dư thuận/ngược.
4. Dừng khi không còn đường tăng.

Với **dung lượng nguyên** và lựa chọn đường tăng tùy ý, mỗi lần tăng làm tổng luồng tăng ít nhất 1 đơn vị, nên thuật toán kết thúc; một chặn thường nêu là **O(E·|f*|)** nếu mỗi lần tìm đường tốn O(E) và giá trị cực đại `|f*|` được tính bằng số nguyên đơn vị. Đây là chặn **giả đa thức**: phụ thuộc giá trị số của đáp án, không chỉ độ dài biểu diễn đầu vào. Với dung lượng thực/phi hữu tỉ và lựa chọn đường không thích hợp, phương pháp tùy ý có những vấn đề về số lần tăng, nên cần quy tắc cụ thể.

### Edmonds–Karp: luôn chọn đường tăng ngắn nhất theo số cung dư

**Edmonds–Karp** là cách triển khai Ford–Fulkerson bằng **BFS** trên các cung dư có dung lượng dương. Mỗi đường tăng được chọn có **ít số cung dư nhất**, không phải có bottleneck lớn nhất hay tổng dung lượng lớn nhất.

~~~text
EDMONDS_KARP(G, s, t)
    REQUIRE s != t
    initialize residual network: forward=c, reverse=0
    totalFlow <- 0

    LOOP
        parentEdge <- BFS from s using residual edges > 0
        IF t was not discovered:
            BREAK

        delta <- min residual over recovered s->t path
        FOR each residual arc e along the path:
            e.residual -= delta
            e.reverse.residual += delta

        totalFlow += delta
    END LOOP

    reachable <- BFS from s using final residual arcs > 0
    S <- all reachable vertices
    T <- all other vertices
    cutCapacity <- sum capacity of original arcs S->T

    ASSERT totalFlow == cutCapacity
    RETURN totalFlow, S, T, cutCapacity
END
~~~

**Đánh dấu visited ngay khi enqueue trong *một lần BFS tìm đường tăng*.** Điều này khác việc đánh dấu một đỉnh vĩnh viễn trên toàn bộ thuật toán: qua các lần tăng, mạng dư **thay đổi**, và mỗi vòng cần BFS mới với mảng visited/parent mới.

**Phải nhớ cạnh cha dưới dạng tham chiếu tới cung dư cụ thể**, không chỉ nhớ đỉnh cha, vì có thể có cạnh song song với dung lượng khác nhau và cung ngược dư. Sau khi tìm t, lần ngược từng đối tượng cung để cập nhật đúng cặp dư.

### Phân tích độ phức tạp

Một BFS tìm đường tăng trên mạng dư có **O(V+E)** thời gian. Edmonds–Karp có **O(VE)** lần tăng, do độ dài đường tăng BFS theo số cung không giảm, và một cung chỉ có thể trở thành “cung nút thắt” hữu hạn O(V) lần với sự tăng độ dài thích hợp.

Suy ra chặn tổng thường ghi:

`O(VE²)` **thời gian** cho Edmonds–Karp (với E là số cung gốc, chặn tính cả các trường hợp đồ thị đủ cạnh để có đường). Bộ nhớ mạng dư, parent, queue là **O(V+E)**.

Nếu quan tâm hiệu năng trên mạng lớn, **Dinic** dùng BFS dựng đồ thị lớp và DFS/gửi luồng chặn theo lớp, thường có chặn tổng quát **O(V²E)**; với một số lớp mạng có chặn tốt hơn. **Push–relabel** là họ phương pháp khác. Nhưng **định lý max-flow min-cut** không phụ thuộc bạn chọn thuật toán nào; nó là tính chất của mọi mạng luồng hợp lệ.

### Vì sao có thể dừng?

Khi BFS không tìm được t từ s trong mạng dư, tập S đã xác định. Chứng minh mục 6 lập tức tạo lát cắt có dung lượng bằng tổng luồng. Đó là **điều kiện dừng được chứng minh là tối ưu**, không phải một ngưỡng heuristic.

## 9. Java 17+ — tính luồng cực đại và xuất chứng chỉ lát cắt

Chương trình sau triển khai Edmonds–Karp với **hai đối tượng cung dư được liên kết trực tiếp**. Cách này hỗ trợ rõ ràng:

- **Cung song song**: mỗi bộ input tạo một cặp dư riêng.
- **Cung đối hướng**: cung gốc v→u có cặp dư riêng, không ghi đè cung gốc u→v.
- **Khuyên và dung lượng 0**: được cho phép; BFS chỉ qua cung dư >0, khuyên không tạo đường tăng và không vượt lát cắt.
- **Dung lượng long không âm**; tổng luồng và tổng dung lượng lát cắt tính bằng `Math.addExact` để không âm thầm tràn số.
- **Nguồn và đích phải phân biệt và hợp lệ**; constructor nhận n≥2.
- Sau khi tìm max flow, truy vấn toàn bộ các đỉnh **còn tới được trong mạng dư** và in `S`, `T`, các cung gốc cắt từ S→T cùng dung lượng.
- Kiểm tra **bảo toàn dòng, capacity bounds, residual consistency** và chứng chỉ maxflow=mincut.
- Trên đồ thị nhỏ, **liệt kê hết các phân hoạch S/T** để có một oracle khác hoàn toàn thuật toán đường tăng.

**Tạo tệp `MaxFlowMinCutDemo.java`**, lưu đúng tên vì class công khai cùng tên:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class MaxFlowMinCutDemo {
    static final class Edge {
        final int from;
        final int to;
        long residual;
        Edge reverse;

        Edge(int from, int to, long residual) {
            this.from = from;
            this.to = to;
            this.residual = residual;
        }
    }

    record Original(int from, int to, long capacity, Edge forward) {}

    static final class Graph {
        final int n;
        final List<List<Edge>> adjacency = new ArrayList<>();
        final List<Original> originals = new ArrayList<>();

        Graph(int n, long[][] arcs) {
            Objects.requireNonNull(arcs, "arcs");
            if (n < 2) {
                throw new IllegalArgumentException(
                        "Require at least two vertices");
            }
            this.n = n;
            for (int v = 0; v < n; v++) {
                adjacency.add(new ArrayList<>());
            }

            for (long[] arc : arcs) {
                if (arc == null || arc.length != 3) {
                    throw new IllegalArgumentException(
                            "Expected {from,to,capacity}");
                }
                long u = arc[0], v = arc[1], c = arc[2];
                if (u < 0 || u >= n || v < 0 || v >= n || c < 0) {
                    throw new IllegalArgumentException(
                            "Invalid endpoint or negative capacity");
                }
                addArc((int) u, (int) v, c);
            }
        }

        private void addArc(int u, int v, long capacity) {
            Edge forward = new Edge(u, v, capacity);
            Edge backward = new Edge(v, u, 0L);
            forward.reverse = backward;
            backward.reverse = forward;

            adjacency.get(u).add(forward);
            adjacency.get(v).add(backward);

            originals.add(new Original(u, v, capacity, forward));
        }
    }

    record Result(
            long maxFlow,
            long cutCapacity,
            List<Integer> sourceSide,
            List<Integer> sinkSide,
            List<String> cutEdges,
            int augmentations) {}

    private static Edge[] bfsAugmentingPath(
            Graph graph, int source, int sink) {
        Edge[] parent = new Edge[graph.n];
        boolean[] visited = new boolean[graph.n];
        ArrayDeque<Integer> queue = new ArrayDeque<>();

        visited[source] = true;
        queue.addLast(source);

        while (!queue.isEmpty() && !visited[sink]) {
            int u = queue.removeFirst();
            for (Edge edge : graph.adjacency.get(u)) {
                int v = edge.to;
                if (edge.residual <= 0 || visited[v]) {
                    continue;
                }
                visited[v] = true;
                parent[v] = edge;
                queue.addLast(v);
                if (v == sink) {
                    break;
                }
            }
        }
        return visited[sink] ? parent : null;
    }

    private static boolean[] residualReachable(
            Graph graph, int source) {
        boolean[] visited = new boolean[graph.n];
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        visited[source] = true;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (Edge edge : graph.adjacency.get(u)) {
                if (edge.residual > 0 && !visited[edge.to]) {
                    visited[edge.to] = true;
                    queue.addLast(edge.to);
                }
            }
        }
        return visited;
    }

    public static Result edmondsKarp(
            Graph graph, int source, int sink) {
        Objects.requireNonNull(graph, "graph");
        if (source < 0 || source >= graph.n
                || sink < 0 || sink >= graph.n
                || source == sink) {
            throw new IllegalArgumentException(
                    "Distinct valid source and sink required");
        }

        long totalFlow = 0L;
        int augmentations = 0;

        while (true) {
            Edge[] parent = bfsAugmentingPath(
                    graph, source, sink);
            if (parent == null) {
                break;
            }

            long delta = Long.MAX_VALUE;
            for (int v = sink; v != source; ) {
                Edge edge = parent[v];
                delta = Math.min(delta, edge.residual);
                v = edge.from;
            }

            for (int v = sink; v != source; ) {
                Edge edge = parent[v];
                edge.residual -= delta;
                edge.reverse.residual = Math.addExact(
                        edge.reverse.residual, delta);
                v = edge.from;
            }

            totalFlow = Math.addExact(totalFlow, delta);
            augmentations++;
        }

        boolean[] inSourceSide =
                residualReachable(graph, source);

        List<Integer> sourceSide = new ArrayList<>();
        List<Integer> sinkSide = new ArrayList<>();
        for (int v = 0; v < graph.n; v++) {
            if (inSourceSide[v]) {
                sourceSide.add(v);
            } else {
                sinkSide.add(v);
            }
        }

        long cutCapacity = 0L;
        List<String> cutEdges = new ArrayList<>();
        for (Original edge : graph.originals) {
            if (inSourceSide[edge.from()]
                    && !inSourceSide[edge.to()]) {
                cutCapacity = Math.addExact(
                        cutCapacity, edge.capacity());
                cutEdges.add(edge.from() + "->" + edge.to()
                        + "(" + edge.capacity() + ")");
            }
        }

        if (inSourceSide[sink] || totalFlow != cutCapacity) {
            throw new AssertionError("Invalid maxflow/mincut");
        }

        return new Result(totalFlow, cutCapacity,
                List.copyOf(sourceSide), List.copyOf(sinkSide),
                List.copyOf(cutEdges), augmentations);
    }

    private static void verifyCertificate(
            Graph graph, int source, int sink, Result result) {
        long[] incoming = new long[graph.n];
        long[] outgoing = new long[graph.n];

        for (Original edge : graph.originals) {
            long used = Math.subtractExact(
                    edge.capacity(), edge.forward().residual);

            if (used < 0 || used > edge.capacity()
                    || edge.forward().reverse.residual != used) {
                throw new AssertionError("Capacity/residual mismatch");
            }

            outgoing[edge.from()] = Math.addExact(
                    outgoing[edge.from()], used);
            incoming[edge.to()] = Math.addExact(
                    incoming[edge.to()], used);
        }

        for (int v = 0; v < graph.n; v++) {
            long net = Math.subtractExact(
                    outgoing[v], incoming[v]);
            long expected = v == source ? result.maxFlow()
                    : v == sink ? -result.maxFlow() : 0L;

            if (net != expected) {
                throw new AssertionError(
                        "Flow conservation failed");
            }
        }

        boolean[] reachable = residualReachable(graph, source);
        List<Integer> expectedSourceSide = new ArrayList<>();
        long actualCut = 0L;
        List<String> expectedEdges = new ArrayList<>();

        for (int v = 0; v < graph.n; v++) {
            if (reachable[v]) {
                expectedSourceSide.add(v);
            }
        }

        for (Original edge : graph.originals) {
            if (reachable[edge.from()] && !reachable[edge.to()]) {
                actualCut = Math.addExact(
                        actualCut, edge.capacity());
                expectedEdges.add(edge.from() + "->" + edge.to()
                        + "(" + edge.capacity() + ")");
                if (edge.forward().residual != 0) {
                    throw new AssertionError(
                            "Crossing arc not saturated");
                }
            } else if (!reachable[edge.from()]
                    && reachable[edge.to()]
                    && edge.forward().reverse.residual != 0) {
                throw new AssertionError(
                        "Reverse crossing carries flow");
            }
        }

        if (!expectedSourceSide.equals(result.sourceSide())
                || !expectedEdges.equals(result.cutEdges())
                || actualCut != result.cutCapacity()
                || result.maxFlow() != actualCut) {
            throw new AssertionError("Bad cut certificate");
        }
    }

    // Oracle vét cạn: duyệt mọi S chứa source, không chứa sink.
    // Chỉ dùng cho n <= 10 trong kiểm thử.
    private static long bruteMinCut(
            Graph graph, int source, int sink) {
        if (graph.n > 10) {
            throw new IllegalArgumentException(
                    "Brute cut only for small graphs");
        }

        long best = Long.MAX_VALUE;
        int masks = 1 << graph.n;

        for (int mask = 0; mask < masks; mask++) {
            if ((mask & (1 << source)) == 0
                    || (mask & (1 << sink)) != 0) {
                continue;
            }

            long capacity = 0L;
            for (Original edge : graph.originals) {
                boolean fromS =
                        (mask & (1 << edge.from())) != 0;
                boolean toS =
                        (mask & (1 << edge.to())) != 0;
                if (fromS && !toS) {
                    capacity = Math.addExact(
                            capacity, edge.capacity());
                }
            }
            best = Math.min(best, capacity);
        }
        return best;
    }

    private static void show(
            String name, int n, long[][] arcs, int source,
            int sink) {
        Graph graph = new Graph(n, arcs);
        Result result = edmondsKarp(graph, source, sink);

        verifyCertificate(graph, source, sink, result);
        if (result.maxFlow() != bruteMinCut(
                graph, source, sink)) {
            throw new AssertionError("Wrong optimum in " + name);
        }

        System.out.println(name
                + " flow=" + result.maxFlow()
                + " cut=" + result.cutCapacity()
                + " S=" + result.sourceSide()
                + " T=" + result.sinkSide()
                + " cutEdges=" + result.cutEdges()
                + " augmentations=" + result.augmentations());
    }

    private static void randomCrossCheck() {
        Random random = new Random(2026L);
        for (int test = 0; test < 300; test++) {
            int n = 2 + random.nextInt(7); // 2..8 vertices.
            int m = random.nextInt(2 * n * n + 1);
            long[][] arcs = new long[m][3];

            for (int i = 0; i < m; i++) {
                arcs[i][0] = random.nextInt(n);
                arcs[i][1] = random.nextInt(n);
                arcs[i][2] = random.nextInt(21);
            }

            int source = random.nextInt(n);
            int sink = random.nextInt(n - 1);
            if (sink >= source) {
                sink++;
            }

            Graph graph = new Graph(n, arcs);
            Result result = edmondsKarp(
                    graph, source, sink);

            verifyCertificate(graph, source, sink, result);
            if (result.maxFlow() != bruteMinCut(
                    graph, source, sink)) {
                throw new AssertionError(
                        "Random mismatch at " + test);
            }
        }
        System.out.println("randomCrossCheck=PASS (300 networks)");
    }

    public static void main(String[] args) {
        show("classic", 6, new long[][]{
            {0,1,16}, {0,2,13}, {1,2,10}, {2,1,4},
            {1,3,12}, {3,2,9}, {2,4,14}, {4,3,7},
            {3,5,20}, {4,5,4}
        }, 0, 5);

        show("parallel", 3, new long[][]{
            {0,1,5}, {0,1,4}, {1,2,6},
            {0,2,2}, {1,1,100}, {1,0,3}
        }, 0, 2);

        show("diamond", 4, new long[][]{
            {0,1,3}, {0,2,2}, {1,3,2},
            {2,3,4}, {1,2,1}
        }, 0, 3);

        show("bottleneck", 4, new long[][]{
            {0,1,10}, {1,3,1},
            {0,2,2}, {2,3,2}
        }, 0, 3);

        show("disconnected", 5, new long[][]{
            {0,1,8}, {1,2,3}, {3,4,9}
        }, 0, 4);

        show("zero", 3, new long[][]{
            {0,1,0}, {0,2,0}, {1,2,5}
        }, 0, 2);

        show("singleEdge", 2, new long[][]{
            {0,1,7}
        }, 0, 1);

        show("noEdges", 2, new long[0][3], 0, 1);

        show("bigCapacity", 2, new long[][]{
            {0,1,5_000_000_000L}
        }, 0, 1);

        try {
            new Graph(2, new long[][]{{0,1,-1}});
            throw new AssertionError("Expected rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("negativeCapacity=rejected");
        }

        try {
            edmondsKarp(new Graph(2, new long[0][3]), 0, 0);
            throw new AssertionError("Expected rejection");
        } catch (IllegalArgumentException expected) {
            System.out.println("sameSourceSink=rejected");
        }

        randomCrossCheck();
    }
}
~~~

### Biên dịch và chạy

Dùng **JDK 17 trở lên**:

~~~bash
javac MaxFlowMinCutDemo.java
java MaxFlowMinCutDemo
~~~

**Đầu ra xác định** — danh sách theo định dạng mặc định của `List.toString()` trong Java:

~~~text
classic flow=23 cut=23 S=[0, 1, 2, 4] T=[3, 5] cutEdges=[1->3(12), 4->3(7), 4->5(4)] augmentations=3
parallel flow=8 cut=8 S=[0, 1] T=[2] cutEdges=[1->2(6), 0->2(2)] augmentations=3
diamond flow=5 cut=5 S=[0] T=[1, 2, 3] cutEdges=[0->1(3), 0->2(2)] augmentations=3
bottleneck flow=3 cut=3 S=[0, 1] T=[2, 3] cutEdges=[1->3(1), 0->2(2)] augmentations=2
disconnected flow=0 cut=0 S=[0, 1, 2] T=[3, 4] cutEdges=[] augmentations=0
zero flow=0 cut=0 S=[0] T=[1, 2] cutEdges=[0->1(0), 0->2(0)] augmentations=0
singleEdge flow=7 cut=7 S=[0] T=[1] cutEdges=[0->1(7)] augmentations=1
noEdges flow=0 cut=0 S=[0] T=[1] cutEdges=[] augmentations=0
bigCapacity flow=5000000000 cut=5000000000 S=[0] T=[1] cutEdges=[0->1(5000000000)] augmentations=1
negativeCapacity=rejected
sameSourceSink=rejected
randomCrossCheck=PASS (300 networks)
~~~

### Đọc kết quả và kiểm chứng

**classic:** có ba lần tăng theo BFS, tổng luồng 23. Lát cắt cuối cùng `S=[0,1,2,4]`, `T=[3,5]` có đúng ba cung cắt được liệt kê, dung lượng 12+7+4=23. Cung ngược gốc 3→2 không được tính vào dung lượng lát cắt.

**parallel:** có hai cung 0→1 với dung lượng 5 và 4; chúng phải được quản lý riêng. Cạnh 1→2 dung lượng 6 cộng cạnh 0→2 dung lượng 2 tạo lát cắt 8. Khuyên 1→1 dung lượng 100 không đóng góp, và cung gốc 1→0 là cung đối hướng hợp lệ riêng.

**diamond:** các đường s→t khác nhau có tổng luồng cực đại 5; lát cắt nhỏ nhất ngay sau nguồn là 3+2=5. Những cạnh nằm bên trong phía T không được cộng.

**bottleneck:** tổng dung lượng cạnh ra khỏi nguồn là 12, nhưng lát cắt `S={0,1}`, `T={2,3}` chỉ dung lượng 1+2=3; không thể gửi quá 3 vì hai nút thắt nhỏ hơn.

**disconnected:** không có đường từ 0 tới 4 với dung lượng dư dương, nên max flow bằng 0 và tồn tại min cut dung lượng 0. **Lát cắt rỗng về cạnh cắt** là trường hợp hoàn toàn hợp lệ.

**zero:** có những cung gốc từ S sang T với dung lượng **0**. Chương trình vẫn liệt kê chúng trong `cutEdges`, nhưng dung lượng cắt và luồng đều 0. Mạng dư không đi qua các cung dung lượng 0.

**singleEdge, noEdges:** giá trị cực đại lần lượt bằng 7 và 0; chúng minh họa trường hợp cơ sở.

**bigCapacity:** dung lượng 5 tỷ vượt giới hạn `int`, nhưng kiểu `long` lưu được. Đây là lý do dùng `long` cho dung lượng và tổng luồng thay vì int.

**randomCrossCheck:** chạy 300 mạng nhỏ với nguồn/đích ngẫu nhiên, dung lượng nguyên 0..20, có thể có khuyên, cung trùng và cung đối hướng. Mỗi lần so kết quả Edmonds–Karp với một oracle **vét cạn mọi tập S chứa nguồn, không chứa đích** và kiểm tra bảo toàn dòng. Nếu có lỗi sẽ ném `AssertionError`; PASS chỉ xuất hiện khi toàn bộ kiểm tra thành công.

**Lưu ý API:** `edmondsKarp` cập nhật **mạng dư ngay trong đối tượng Graph được truyền vào**. Nếu muốn giải lại cùng một input với nguồn/đích khác, phải tạo **Graph mới từ danh sách cung gốc**, không tái sử dụng Graph đã chạy như thể nó còn trạng thái ban đầu. Không gọi hai lần hàm này trên cùng Graph để “lấy lại” max flow; lần hai bắt đầu từ mạng dư đã biến đổi.

## 10. Kiểm chứng nghiệm như một chứng chỉ độc lập

Để tin một kết quả max flow, nên kiểm tra **hai mặt**:

### Phía luồng

- Mỗi cung gốc có lượng dùng `f(e)=c(e)−residualForward(e)` nằm trong `[0,c(e)]`.
- Các đỉnh không phải s,t thỏa **tổng vào = tổng ra**.
- **Lượng ròng phát nguồn** bằng **lượng ròng nhận ở đích**.
- Giá trị luồng không âm và khớp số được báo cáo.

### Phía lát cắt

- S và T là phân hoạch toàn bộ V, s∈S và t∈T.
- Dung lượng cắt được tính **chỉ từ các cung gốc S→T**.
- Các cung gốc S→T bão hòa, còn các cung gốc T→S không mang dòng.
- Giá trị luồng bằng dung lượng lát cắt.

Nếu cả hai đều đúng, kết quả tối ưu **theo định lý**, ngay cả khi không biết chương trình tìm nghiệm như thế nào.

### Tại sao oracle vét cạn là độc lập?

Với n đỉnh và s,t cố định, có **2^(n−2)** cách gán mỗi đỉnh còn lại vào S hoặc T. Với mỗi lát cắt, cộng dung lượng cung gốc S→T rồi lấy min. Cách này không dùng đường tăng, BFS mạng dư hay định lý dừng để **tính** đáp án oracle, nên có ích để phát hiện lỗi triển khai.

Nhược điểm: thời gian **O(2^n·E)**, không phù hợp mạng lớn. Vì thế chương trình chỉ dùng brute-force khi n≤10, trên 300 mạng sinh với n≤8.

**Không nhầm brute force với thuật toán giải chính:** Edmonds–Karp vẫn có thời gian đa thức; việc liệt kê lát cắt chỉ phục vụ unit test.

## 11. Tính nguyên của luồng tối ưu

Nếu mọi dung lượng là **số nguyên không âm**, bắt đầu luồng 0 và mỗi lần tăng trên bottleneck nguyên dương sẽ giữ mọi giá trị luồng nguyên. Edmonds–Karp trả một luồng cực đại **nguyên**.

Đây là **tính nguyên (integrality theorem)** của bài toán max flow. Nó rất hữu ích khi một đơn vị luồng đại diện **một vật thể nguyên**, như một lượt giao hàng, một đơn vị công việc hoặc một cặp ghép.

**Không được hiểu rằng nghiệm tối ưu duy nhất**: có thể có nhiều luồng cực đại nguyên khác nhau, và cũng có thể tồn tại các luồng tối ưu phân số nếu cho phép luồng liên tục. Tính nguyên đảm bảo **tồn tại một nghiệm nguyên**, không bảo đảm tất cả nghiệm tối ưu đều nguyên.

Với dung lượng thực không nguyên, định lý max-flow min-cut vẫn đúng trên phạm vi toán học phù hợp, nhưng triển khai số thực cần xử lý sai số, điều kiện gần 0 và tính dừng; chương trình Java ở trên **chỉ nhận long nguyên** để tránh vấn đề xấp xỉ.

## 12. Một lát cắt không phải chỉ là “đường chặn” ít cạnh

Lát cắt là **phân hoạch đỉnh**, không phải đường đi và cũng không phải danh sách vài cạnh chọn tùy ý. Tập các cung bị cắt được xác định **từ S sang T** bởi phân hoạch ấy.

Nếu chỉ chọn một số cạnh có tổng dung lượng nhỏ nhưng xóa chúng **không ngăn được mọi đường s→t**, đó **không** phải lát cắt s–t hợp lệ.

Nếu chỉ đếm số cung bị cắt, đang giải bài **minimum-cardinality cut**, khác minimum-capacity cut trừ trường hợp tất cả dung lượng đồng nhất.

### Một ví dụ về số lượng cạnh so với dung lượng

~~~text
Cách cắt A: một cung duy nhất dung lượng 100
Cách cắt B: ba cung dung lượng 2,2,2
~~~

Nếu cả hai là lát cắt s–t hợp lệ của cùng một mạng, lát cắt B có **tổng dung lượng 6**, tốt hơn A có dung lượng 100, dù phải cắt nhiều cung hơn. Giá trị max flow bị chặn bởi **6**, không bởi số cung 3.

Với dung lượng bằng 1 trên mọi cung, max-flow min-cut trở thành cầu nối đến những kết quả liên quan **số đường đi tách biệt theo cạnh**, nhưng cần xác định rõ loại “độc lập” và cách mô hình hóa.

## 13. Ứng dụng và phép chuyển đổi mô hình

### 13.1. Số đường đi độc lập theo cạnh

Nếu mọi cung gốc có dung lượng 1, mỗi đơn vị luồng nguyên có thể phân rã theo các đường s→t. Luồng cực đại liên quan đến **số đường đi từ s tới t không dùng chung cung**, và dung lượng lát cắt là số cung cần cắt tối thiểu để chặn tất cả đường đó.

**Cẩn thận với cung vô hướng:** nếu mỗi cạnh vô hướng chỉ được dùng **một lần tổng cộng**, không nên tự động thay nó bằng hai cung độc lập mỗi cung dung lượng 1 rồi diễn giải mọi đại lượng như hai tài nguyên riêng. Trong nhiều mục tiêu s–t, có phép chuyển hợp lệ, nhưng phải kiểm chứng mô hình năng lực dùng chung (đặc biệt nếu có nhiều luồng hoặc nhiều loại nhu cầu).

### 13.2. Matching hai phía (bipartite matching)

Cho hai tập L và R, nối siêu nguồn s→mỗi đỉnh L dung lượng 1, mỗi cạnh tương thích L→R dung lượng 1, và mỗi đỉnh R→t dung lượng 1. Mỗi đơn vị luồng nguyên ứng với một cặp ghép; bảo toàn và dung lượng bảo đảm một đỉnh ghép không quá một lần.

`maximumMatchingSize = maxflow` trong mạng chuyển đổi ấy. Định lý min cut còn giúp diễn giải chứng chỉ tối ưu liên quan đến cấu trúc phủ đỉnh ở đồ thị hai phía khi khai thác thêm tính chất riêng.

### 13.3. Nhiều nguồn và nhiều đích

Thêm **siêu nguồn** nối đến các nguồn gốc và/hoặc **siêu đích** nhận từ các đích gốc, với dung lượng đủ lớn để không vô tình bóp nghẹt bài toán.

**Không tự đặt “INF=10^9”** nếu tổng dung lượng thực tế có thể lớn hơn. Cần chọn một cận an toàn theo input và kiểm soát tràn số, hoặc thiết kế lại mô hình. Khi có giới hạn riêng từng nguồn/đích, dung lượng cung siêu nguồn/siêu đích phải biểu diễn đúng những giới hạn đó, không nhất thiết vô hạn.

### 13.4. Dung lượng trên đỉnh

Nếu một đỉnh trung gian v chỉ được xử lý tối đa k đơn vị, thay nó bằng **v_in→v_out** có dung lượng k, chuyển các cung đi vào v tới v_in và các cung đi ra từ v_out. Đây là kỹ thuật **tách đỉnh (vertex splitting)**.

Nếu đích/source cũng có hạn mức, phải xử lý chúng theo đặc tả riêng. Lát cắt trong mạng chuyển đổi có thể đi qua cạnh v_in→v_out, tương ứng với việc “cắt” một đỉnh.

### 13.5. Bài toán tối thiểu chi phí khác max flow

Max flow tối ưu **lượng vận chuyển**, không tối ưu **chi phí trên mỗi đơn vị luồng**. Nếu cung còn có một giá tiền cho mỗi đơn vị, bài toán **min-cost max-flow** hoặc **minimum-cost flow** đòi thêm biến mục tiêu và thuật toán khác.

Tương tự, **lát cắt cực tiểu theo dung lượng** khác **đường đi ngắn nhất** theo trọng số: một lát cắt phân hoạch các đỉnh, còn đường đi chọn một dãy cung nối s→t.

## 14. Các tình huống biên cần xử lý

### 14.1. Không có đường từ s tới t

Nếu t không thể tới từ s bằng cung có dung lượng **dương**, max flow là **0**. Trong mạng dư ban đầu, S là các đỉnh tới được từ s; sẽ không có cung gốc S→T có dung lượng dương, nên dung lượng lát cắt là 0. S có thể chứa nhiều đỉnh, không nhất thiết chỉ là nguồn.

### 14.2. Dung lượng 0

Cung dung lượng 0 là một cung **hợp lệ trong input**, nhưng không có ích cho đường tăng. Nó có thể nằm trên ranh giới một lát cắt và được liệt kê như một cung cắt **giá trị 0**, không làm thay đổi tổng. Nếu bạn bỏ những cung này khi tính đường đi dư vẫn đúng, nhưng khi muốn báo cáo mọi cung gốc vượt lát cắt thì có thể giữ chúng.

### 14.3. Khuyên tự nối

Khuyên u→u không thể giúp dòng ròng di chuyển từ s tới t; nó luôn nằm **nội bộ** của mọi lát cắt và không làm tăng max flow. Trong cài đặt dùng cặp đối tượng dư liên kết trực tiếp, một khuyên vẫn tạo được cặp thuận/ngược hợp lệ và tự bị BFS bỏ qua vì u đã được đánh dấu trong chính lượt duyệt.

### 14.4. Cung song song và cung đối hướng

Đừng giả định `capacity[u][v]` là một số duy nhất nếu input có nhiều cung song song và bạn cần truy vết từng cung. Có thể **cộng dung lượng** song song để tính max flow nếu không cần ID riêng, nhưng khi báo cáo cạnh cắt/luồng riêng, nên giữ từng cung với ID.

Cung gốc u→v và cung gốc v→u phải được ghi nhận như **hai nhu cầu vận chuyển/công suất độc lập**, ngoài các cung ngược dư của từng cung.

### 14.5. Nguồn bằng đích hoặc thiếu nguồn/đích

Phát biểu max-flow s–t chuẩn giả định **s≠t**. Nếu s=t, khái niệm “dòng ròng phát và nhận” đòi quy ước khác; không chạy thuật toán tăng từ một đỉnh tới chính nó. Mã Java **ném lỗi**. Với mạng n<2, không có cặp nguồn/đích phân biệt hợp lệ theo API.

### 14.6. Dung lượng rất lớn và tràn số

Một cung có thể lớn hơn giới hạn `int`; vì thế mã dùng `long`. Nhưng **tổng nhiều cung** vẫn có thể vượt `Long.MAX_VALUE`. Khi đó `Math.addExact` ném `ArithmeticException`; cần dùng kiểu số lớn như `BigInteger` hoặc bảo đảm tổng/giá trị trong giới hạn. **Không được im lặng tràn long** khiến tổng luồng âm hoặc sai cut.

### 14.7. Nhiều luồng cực đại hoặc nhiều lát cắt cực tiểu

Định lý bảo đảm **giá trị tối ưu**, không bảo đảm duy nhất nghiệm. Hai luồng có thể phân bố khác nhau trên những chu trình/nút trung gian nhưng có cùng |f|; các lát cắt cũng có thể có nhiều phân hoạch khác nhau cùng dung lượng tối thiểu.

Khi so hai cài đặt, hãy so **giá trị max flow**, **dung lượng min cut** và tính hợp lệ của từng nghiệm; không bắt buộc mọi cung mang đúng cùng một lượng hoặc tập S phải y hệt nếu đề không quy định chọn nghiệm.

### 14.8. Đồ thị vô hướng

Mạng luồng ở bài này có hướng. Khi đề mô tả một cạnh **vô hướng có công suất dùng chung**, cần xác định rõ nó cho phép dòng ròng theo hai chiều như thế nào. Một cách mô hình hóa phù hợp với bài s–t single-commodity là dùng hai cung đối hướng có dung lượng c và phân tích luồng ròng; nhưng với những biến thể tài nguyên/chia sẻ công suất khác cần kiểm tra ràng buộc. **Không áp dụng quy tắc cộng dung lượng lát cắt của mạng có hướng mà không xác định ánh xạ.**

## 15. Sai lầm phổ biến

1. **Đếm số cung qua cắt thay vì cộng dung lượng**.
2. **Cộng cả cung T→S** vào c(S,T), sai vì lát cắt có hướng chỉ cộng S→T.
3. **Định nghĩa |f| bằng tổng cung đi ra nguồn mà quên trừ cung đi vào**.
4. **Quên bảo toàn luồng ở đỉnh trung gian**; tổng vận chuyển trên các cung chưa chắc là luồng khả thi.
5. **Cho phép f(e)>c(e)** và vẫn gọi là luồng hợp lệ.
6. **Cho phép f(e)<0 trên một cung gốc** dù mô hình quy định f không âm.
7. **Đồng nhất cung ngược dư với cung đối hướng gốc**, dễ ghi đè/đếm sai khi có hai chiều.
8. **Không tạo cung ngược dư**, khiến thuật toán không thể hủy cách phân bổ luồng trước đó.
9. **Không cập nhật cả hai phía residual sau tăng**, làm invariant `forward+reverse=capacity` sai.
10. **Cho đường tăng đi qua cung dư có residual=0**, tạo phép tăng Δ=0 và dễ lặp vô hạn.
11. **Lấy bottleneck là dung lượng lớn nhất**, trong khi phải là **nhỏ nhất** trên đường tăng.
12. **Tăng mỗi cung cùng một lượng nhưng không xử lý hướng dư ngược**, phá ràng buộc của luồng gốc.
13. **Khẳng định một đường tăng đã là tối ưu**, không kiểm tra còn đường tăng khác.
14. **Dừng ngay khi số cạnh từ nguồn bão hòa một phần**, không có chứng chỉ lát cắt.
15. **Dùng visited chung cho tất cả vòng BFS tăng**, bỏ lỡ đường mới mở khi mạng dư thay đổi.
16. **Chỉ lưu parent là đỉnh** khi có cung song song, không biết phải cập nhật cung nào.
17. **Tính min cut bằng cạnh dư trong đồ thị sau chạy** thay vì dung lượng **cung gốc S→T**.
18. **Lấy S là mọi đỉnh tới được trong đồ thị gốc** thay vì mạng dư cuối cùng.
19. **Cho rằng một cung đi qua S→T chưa bão hòa mà t vẫn không tới được**, mâu thuẫn tính đạt được của S.
20. **Cho rằng Ford–Fulkerson chọn đường tùy ý luôn đa thức theo V,E**, sai với chặn giả đa thức phụ thuộc |f*|.
21. **Lấy BFS theo dung lượng lớn nhất** rồi gọi Edmonds–Karp; Edmonds–Karp dùng đường ít **cung** nhất.
22. **Kết luận maxflow=mincut chỉ vì hai số bằng nhau mà chưa xác minh luồng và lát cắt hợp lệ**.
23. **Nhầm dung lượng đường s→t là min của các cạnh thành max flow toàn mạng**, chỉ đúng nếu mạng có đúng một tuyến và không còn đường song song/khác.
24. **Lấy đường s→t ngắn nhất làm đường tối ưu luồng**, hai mục tiêu khác nhau.
25. **Bỏ cung dung lượng 0 khi in toàn bộ tập cung gốc cắt** mà không nói rõ quy ước báo cáo.
26. **Không xử lý khuyên và cạnh song song** khi tạo cặp cung dư.
27. **Gọi lại solve trên mạng dư đã biến đổi như input mới**, dẫn đến mất ý nghĩa phép đo từ luồng 0.
28. **Không xử lý nguồn bằng đích**, có thể tạo vòng lặp hoặc kết quả vô nghĩa.
29. **Dùng int cho tổng dòng** khi tổng dung lượng rất lớn.
30. **Thử hết mọi lát cắt trên đồ thị lớn** như thuật toán chính, dẫn đến thời gian mũ.
31. **Nhầm cut capacity với min-cost flow**, trong khi min cut là tổng *công suất* qua ranh giới.
32. **Xem mọi cạnh của một min cut có thể bị xóa mà không cần quan tâm chiều**, trong mạng có hướng phải theo phân hoạch S→T.

## 16. Bài tập có lời giải

**Bài 1.** Định lý luồng cực đại–lát cắt cực tiểu phát biểu điều gì? **Đáp án:** giá trị lớn nhất của luồng s–t bằng dung lượng nhỏ nhất của một lát cắt s–t.

**Bài 2.** Nếu tìm được một luồng hợp lệ giá trị 11 và một lát cắt hợp lệ dung lượng 11, cần tìm tiếp không? **Đáp án:** không; bất đẳng thức |f|≤c(S,T) cùng dấu bằng chứng minh cả hai tối ưu.

**Bài 3.** Cho lát cắt có cung S→T dung lượng 3 và 7, cung T→S dung lượng 100. Dung lượng lát cắt là bao nhiêu? **Đáp án:** 3+7=10, không cộng 100.

**Bài 4.** Cung gốc u→v có capacity 12 và flow 5. Dung lượng dư thuận/ngược? **Đáp án:** thuận 7, ngược 5.

**Bài 5.** Nếu đi qua cung ngược dư 3 đơn vị ở bài 4, flow gốc còn bao nhiêu? **Đáp án:** 2, vì đi ngược dư tương đương hủy 3 đơn vị flow trước đó.

**Bài 6.** Một đường tăng có dung lượng dư lần lượt `[8,4,6]`. Δ lớn nhất để tăng cùng lượng trên đường? **Đáp án:** 4, là bottleneck nhỏ nhất.

**Bài 7.** Vì sao không được dùng đường tăng có một cung residual=0? **Đáp án:** bottleneck sẽ 0 nên không tăng được giá trị luồng.

**Bài 8.** Trong mạng chuẩn 6 đỉnh, max flow là bao nhiêu? **Đáp án:** 23.

**Bài 9.** Lát cắt cuối `S={0,1,2,4}`, `T={3,5}` có dung lượng bao nhiêu? **Đáp án:** `12+7+4=23`.

**Bài 10.** Cung 3→2 dung lượng 9 có cộng vào cut ở bài 9 không? **Đáp án:** không; nó đi từ T về S.

**Bài 11.** Vì sao tập đỉnh tới được từ nguồn trong **mạng dư cuối** cho min cut? **Đáp án:** không còn cung dư dương S→T; cung gốc S→T bão hòa, cung gốc T→S không mang dòng; net flow bằng cut capacity.

**Bài 12.** Trong mã, BFS dùng cung có residual bằng 0 không? **Đáp án:** không; chỉ đi qua residual>0.

**Bài 13.** Khi nào Edmonds–Karp dừng? **Đáp án:** khi BFS không còn tìm thấy đường tăng từ s đến t.

**Bài 14.** Độ phức tạp thời gian Edmonds–Karp thường viết thế nào? **Đáp án:** O(VE²), với O(V+E) bộ nhớ.

**Bài 15.** Nếu mạng có hai cung song song 0→1 với capacity 5 và 4, có thể có luồng tổng 9 qua chúng không nếu phần sau đủ công suất? **Đáp án:** có; hai cung là tài nguyên riêng, tổng capacity 9.

**Bài 16.** Nếu cung 1→2 chỉ capacity 6 và cung trực tiếp 0→2 capacity 2, còn lại như ví dụ parallel, max flow bằng bao nhiêu? **Đáp án:** 8, được chứng nhận bởi lát cắt gồm 1→2 (6) và 0→2 (2).

**Bài 17.** Một khuyên s→s capacity 1000 có làm tăng max flow tới t không? **Đáp án:** không; nó không đưa dòng ròng qua một lát cắt hay tới đích.

**Bài 18.** Nếu không có đường s→t nào có các cung dư dương từ đầu, max flow bằng bao nhiêu? **Đáp án:** 0.

**Bài 19.** Vì sao cần lưu reference tới đúng cung dư làm parent khi có nhiều cung song song? **Đáp án:** vì mỗi cung có residual và cung reverse riêng; chỉ biết đỉnh cha không xác định được cần cập nhật cung nào.

**Bài 20.** Có phải mọi cung S→T của min cut sau max flow đều bão hòa? **Đáp án:** có với luồng cực đại và min cut hợp lệ, vì nếu còn dư dương sẽ làm net flow nhỏ hơn cut capacity.

**Bài 21.** Tại sao một cung gốc T→S phải mang luồng 0 trên min cut sau max flow? **Đáp án:** luồng ngược qua biên làm giảm net flow, nên để bằng cut capacity nó phải 0.

**Bài 22.** Edmonds–Karp có cần capacities nguyên mới kết thúc? **Đáp án:** không; số lần tăng có chặn đa thức theo cấu trúc đồ thị nhờ BFS đường ngắn nhất, khác phương pháp chọn đường tùy ý. Mã Java ở đây dùng long nguyên cho biểu diễn chính xác.

**Bài 23.** Nếu mọi capacity nguyên, có tồn tại nghiệm max flow nguyên? **Đáp án:** có, vì bắt đầu từ luồng 0 nguyên và mỗi bottleneck nguyên.

**Bài 24.** Với n đỉnh, s,t cố định, có bao nhiêu tập S ứng viên khi liệt kê toàn bộ lát cắt? **Đáp án:** `2^(n−2)`, vì s luôn ở S, t luôn ở T và n−2 đỉnh còn lại được chọn độc lập.

**Bài 25.** Một chương trình in flow=9, cut=9 nhưng vi phạm bảo toàn tại đỉnh trung gian. Có chứng minh được tối ưu chưa? **Đáp án:** chưa; “flow” đó chưa phải luồng hợp lệ, nên không dùng được định lý.

**Bài 26.** Muốn giới hạn lưu lượng qua một đỉnh trung gian ở mức k thì làm sao? **Đáp án:** tách v thành v_in và v_out, nối v_in→v_out dung lượng k, rồi định tuyến cung gốc qua cặp đỉnh mới.

**Bài 27.** Max flow và min-cost max-flow có cùng mục tiêu không? **Đáp án:** không; một bài tối đa lượng, bài kia còn tối ưu chi phí trong các luồng thỏa yêu cầu.

**Bài 28.** Nếu sau max flow ta lấy S là các đỉnh tới được từ s trong **đồ thị gốc** thay vì mạng dư, có luôn được min cut không? **Đáp án:** không. Phải dùng **các cung dư dương sau cùng** mới bảo đảm các cung S→T đã bão hòa.

## 17. Checklist áp dụng định lý và cài đặt

1. **Đồ thị có hướng và capacities không âm?** Nếu là vô hướng hay có lower bounds, mô hình hóa lại đúng yêu cầu.
2. **Nguồn s và đích t khác nhau và trong phạm vi đỉnh?**
3. **Có phân biệt capacity c với flow f trên từng cung không?**
4. **Có bảo toàn flow tại mọi đỉnh khác s,t không?**
5. **Có định nghĩa value bằng dòng ròng phát nguồn, không chỉ tổng cung ra?**
6. **Lát cắt S/T có chứa s ở S và t ở T không?**
7. **Dung lượng cắt chỉ cộng cung gốc S→T, không cộng T→S?**
8. **Có tạo một cung dư thuận và một cung dư ngược gắn cặp cho mỗi cung gốc?**
9. **Cung song song/cung đối hướng có được giữ độc lập và cập nhật đúng cặp reverse?**
10. **BFS tìm đường tăng chỉ qua residual>0 và reset visited sau mỗi lần tăng?**
11. **Bottleneck có lấy min trên các cung dư của đúng đường tăng không?**
12. **Khi tăng, có trừ residual của cung trên đường và cộng vào reverse?**
13. **Chỉ dừng khi không còn đường tăng, không dừng tùy tiện?**
14. **Sau dừng, S có được lấy từ BFS/DFS trong mạng dư dương không?**
15. **Có tính lại cut từ capacities gốc và xác nhận maxFlow=cutCapacity?**
16. **Có kiểm chứng flow capacity/conservation cùng cut valid trước khi khẳng định tối ưu?**
17. **Đã thử n nhỏ, không có đường, capacity=0, parallel, antiparallel, self-loop, nguồn/đích sai và capacity lớn chưa?**
18. **Đã cân nhắc độ phức tạp O(VE²), bộ nhớ O(V+E) và tràn số long chưa?**
19. **Nếu có nhiều nguồn/đích hoặc hạn mức đỉnh, đã chuyển đổi bằng siêu nguồn/đích hoặc tách đỉnh đúng công suất chưa?**
20. **Có phân biệt bài toán max flow với shortest path, min cut theo số cạnh và min-cost flow không?**

**Ghi nhớ:** mọi **luồng hợp lệ** luôn không vượt dung lượng của **bất kỳ lát cắt s–t**. Sau khi tăng luồng qua các đường trong **mạng dư** cho tới khi **không còn đường tăng**, tập đỉnh tới được từ nguồn trong mạng dư tạo **lát cắt cực tiểu**, có dung lượng **bằng đúng luồng cực đại**. Cung dư ngược cho phép sửa lựa chọn trước đó; lát cắt được đo bằng **dung lượng cung gốc S→T**, không phải đếm cạnh hay cộng cung ngược T→S.
