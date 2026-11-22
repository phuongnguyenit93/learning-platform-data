# Lựa chọn tham lam trên matroid và các điều kiện áp dụng

## 1. Vì sao có những bài toán tham lam luôn đúng?

Một thuật toán **tham lam (greedy)** thường quyết định theo cách: tại mỗi bước, chọn phần tử đang được ưu tiên nhất mà vẫn giữ được điều kiện hợp lệ, và không quay lại sửa những lựa chọn đã có. Cách làm này thường đơn giản và nhanh, nhưng không phải lúc nào cũng tối ưu.

Ví dụ, khi muốn chọn một tập cạnh không có chu trình, ta có thể ưu tiên cạnh có trọng số cao nhất và bỏ qua những cạnh gây chu trình. Vì sao phương pháp ấy tìm được một **rừng khung trọng số lớn nhất**? Để trả lời, cần nhiều hơn trực giác “lấy cạnh tốt trước”: ta cần tính chất **trao đổi (exchange)** của tập các lời giải hợp lệ.

**Matroid** là cấu trúc toán học trừu tượng hóa chính tính chất đó. Với một matroid hữu hạn và trọng số được xác định cho từng phần tử, quy tắc “duyệt từ trọng số lớn xuống, thêm nếu vẫn độc lập” tìm được **cơ sở có tổng trọng số lớn nhất**. Nếu mục tiêu là một tập độc lập bất kỳ, không bắt buộc là cơ sở, cần chú ý đặc biệt khi có trọng số âm.

Bài này giải thích định nghĩa matroid, cách chứng minh một hệ thống lựa chọn thuộc matroid, chứng minh greedy theo nguyên lý trao đổi, triển khai trên **graphic matroid** bằng thuật toán Kruskal, và các trường hợp không thể áp dụng định lý.

## 2. Định nghĩa hình thức: tập nền và họ tập độc lập

Một matroid hữu hạn là cặp **M = (E, I)**:

- **E** là tập nền hữu hạn (*ground set*) gồm những phần tử có thể chọn.
- **I** là một họ các tập con của E, gọi là **tập độc lập** (*independent sets*).

Họ I phải thỏa ba tiên đề:

**(M1) Không rỗng:** tập rỗng là độc lập.

~~~text
∅ ∈ I
~~~

**(M2) Di truyền (hereditary):** bỏ bớt phần tử khỏi một tập độc lập không làm tập đó mất tính độc lập.

~~~text
Nếu B ∈ I và A ⊆ B thì A ∈ I.
~~~

**(M3) Trao đổi/tăng cường (exchange/augmentation):** nếu A và B đều độc lập, B có nhiều phần tử hơn A, thì tồn tại **ít nhất một** phần tử của B chưa thuộc A mà có thể thêm vào A mà vẫn độc lập.

~~~text
Nếu A, B ∈ I và |A| < |B|,
thì tồn tại e ∈ B \ A sao cho A ∪ {e} ∈ I.
~~~

Điều kiện (M3) là điểm khác biệt then chốt. Mọi matroid đều là một **hệ độc lập có tính di truyền**, nhưng không phải mọi hệ độc lập có tính di truyền đều là matroid.

### Thuật ngữ liên quan

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Independent set | Tập S thuộc I |
| Dependent set | Tập S không thuộc I |
| Basis / cơ sở | Tập độc lập **cực đại theo phép thêm phần tử** từ E |
| Rank r(F) | Số phần tử lớn nhất của một tập độc lập chứa trong F ⊆ E |
| Circuit | Tập phụ thuộc tối tiểu: bỏ bất kỳ phần tử nào thì độc lập |
| Independence oracle | Phép kiểm tra một tập có độc lập hay không |
| Weight w(e) | Trọng số hoặc lợi ích gắn với từng phần tử e |

“Cực đại” không phải “lớn nhất” trong mọi hệ tập tùy ý. Nhưng nhờ tiên đề trao đổi, **mọi cơ sở của một matroid có cùng số phần tử r(E)**. Nếu có hai cơ sở A, B với |A|<|B|, tiên đề trao đổi cho phép thêm một phần tử của B vào A, mâu thuẫn A là cực đại. Đây là lý do có thể so sánh trọng số các cơ sở mà không phải lo một cơ sở có ít phần tử hơn cơ sở khác.

## 3. Ba loại matroid tiêu biểu

### 3.1. Uniform matroid: chọn tối đa k phần tử

Cho E gồm n phần tử và số nguyên 0 ≤ k ≤ n. Xét:

~~~text
I = {S ⊆ E : |S| ≤ k}
~~~

Rõ ràng tập rỗng hợp lệ; bỏ phần tử giữ hợp lệ. Nếu |A|<|B|≤k thì lấy bất kỳ phần tử thuộc B\A thêm vào A vẫn được vì |A|+1≤k. Vì vậy đây là một matroid.

- Muốn chọn **đúng k phần tử** có tổng trọng số lớn nhất: lấy k phần tử có trọng số cao nhất, kể cả phần tử cuối có trọng số âm.
- Muốn chọn **tối đa k phần tử** có tổng trọng số lớn nhất: chỉ cần lấy các phần tử có trọng số **dương** theo thứ tự giảm; có thể bỏ phần tử trọng số 0 mà không giảm tổng.

Hai bài toán có cùng cấu trúc độc lập nhưng **khác hợp đồng đầu ra**. Nếu k=2, các trọng số [7, −1, −3], cơ sở tối ưu có tổng 6 (chọn 7 và −1), trong khi tập độc lập tối ưu là {7}, tổng 7.

### 3.2. Partition matroid: giới hạn lựa chọn theo nhóm

Chia E thành các nhóm không giao nhau E₁, E₂, ..., Eₜ. Mỗi nhóm i có hạn mức cᵢ không âm. Một tập S độc lập nếu:

~~~text
|S ∩ Eᵢ| ≤ cᵢ  với mọi i.
~~~

Ví dụ, trong một chương trình học có nhiều nhóm chủ đề, chỉ cho chọn tối đa hai mục ở nhóm A và tối đa một mục ở nhóm B. Đây là matroid: tập rỗng hợp lệ và bỏ bớt mục không vi phạm giới hạn; nếu hai tập độc lập A, B có |A|<|B|, tồn tại ít nhất một nhóm mà B có nhiều phần tử hơn A, nên lấy một mục trong B\A ở nhóm đó thêm vào A vẫn không vượt hạn mức.

Greedy theo điểm đánh giá có thể chọn các mục điểm cao nhất còn phù hợp quota nếu mục tiêu là tối đa tổng điểm của một **cơ sở** hoặc theo quy tắc xử lý trọng số của bài toán tập độc lập.

Không được mặc nhiên dùng định lý nếu các nhóm **chồng lên nhau** và phần tử phải tuân nhiều quota không tạo thành một partition matroid như trên. Khi đó phải chứng minh riêng tiên đề trao đổi.

### 3.3. Graphic matroid: các tập cạnh không tạo chu trình

Cho một đồ thị vô hướng G=(V,E). Tập nền E là tập **các cạnh** của đồ thị, còn:

~~~text
I = {F ⊆ E : (V,F) không có chu trình}
~~~

Mỗi F độc lập là một **rừng** (*forest*). Một cơ sở là rừng khung (*spanning forest*): trong từng thành phần liên thông của đồ thị gốc, các cạnh được chọn nối tất cả đỉnh của thành phần đó nhưng không tạo chu trình.

- Tập rỗng không có chu trình.
- Bỏ cạnh khỏi rừng không tạo chu trình.
- Nếu A, B đều là rừng và |A|<|B|, phải tồn tại một cạnh trong B nối **hai thành phần liên thông khác nhau của (V,A)**. Nếu mọi cạnh B chỉ nối các đỉnh vốn nằm trong cùng một thành phần của A, mỗi thành phần có s đỉnh chứa tối đa s−1 cạnh B vì B cũng là rừng; cộng lại suy ra |B|≤|A|, mâu thuẫn. Thêm cạnh nối hai thành phần A không tạo chu trình.

Vậy graphic matroid thỏa (M3). **Kruskal** là cách thực thi greedy trên graphic matroid bằng bộ cấu trúc hợp nhất–tìm kiếm (*disjoint-set union*, DSU).

Vòng tự khép (*self-loop*) không độc lập dù đứng một mình, vì tạo chu trình độ dài 1. Các cạnh song song có thể được xét riêng nhưng không thể chọn đồng thời hai cạnh nối cùng một cặp đỉnh nếu chúng tạo chu trình độ dài 2 trong đa đồ thị. Điều này vẫn phù hợp với graphic matroid.

### 3.4. Linear matroid: độc lập tuyến tính

Cho một tập hữu hạn các vector trên một trường số học cố định. Một tập con vector độc lập nếu các vector ấy **độc lập tuyến tính**. Bỏ vector khỏi tập độc lập vẫn độc lập; định lý trao đổi tuyến tính bảo đảm (M3). Vì vậy các tập vector độc lập tạo matroid.

Trong triển khai, independence oracle có thể dùng khử Gauss/kiểm tra hạng. Chi phí của oracle không còn là O(1), và khi dùng số thực cần quản lý sai số: tính độc lập tuyến tính trên một trường chính xác khác với phép kiểm tra gần bằng 0 trên floating point. Matroid bảo đảm **lựa chọn tối ưu nếu oracle đúng**, không tự bảo đảm oracle số học làm việc chính xác.

## 4. Greedy tối ưu cơ sở trọng số trên matroid

Giả sử E hữu hạn, ta có matroid M=(E,I), hàm trọng số w:E→ℝ hoặc những giá trị so sánh được chính xác, và mục tiêu:

~~~text
Tìm cơ sở B ∈ I sao cho tổng w(e), e∈B, lớn nhất.
~~~

Thuật toán tổng quát:

~~~text
G = ∅
Sắp xếp mọi e ∈ E theo w(e) giảm dần.

for each e theo thứ tự đã sắp:
    if G ∪ {e} ∈ I:
        G = G ∪ {e}

return G
~~~

Nó không cần backtrack. Mỗi lần chỉ nhận phần tử nếu giữ được tính độc lập. Vì xét hết E, tập cuối **cực đại**: những phần tử từng bị từ chối vì tạo phụ thuộc với tập chọn tại thời điểm ấy không thể bỗng hợp lệ khi thêm nhiều phần tử hơn, do tính di truyền. Vì vậy G là một **cơ sở**.

### Những điều kiện bắt buộc trước khi gọi định lý

1. Hệ tập con hợp lệ thực sự thỏa cả (M1), (M2), (M3), không chỉ “có thể kiểm tra hợp lệ”.
2. Trọng số đóng góp **cộng độc lập theo phần tử**: tổng của một tập là ∑w(e), không phụ thuộc thứ tự chọn hoặc tương tác phi tuyến giữa các phần tử.
3. Mục tiêu là **cơ sở tối ưu**; nếu chỉ cần tập độc lập bất kỳ, phải xử lý trọng số âm theo mục 6.
4. Mọi phần tử thuộc một **tập nền hữu hạn xác định**; phép kiểm tra độc lập trả kết quả đúng.
5. Quy tắc ưu tiên là trọng số **không tăng**. Khi bằng trọng số có thể chọn thứ tự bất kỳ; tổng tối ưu vẫn được bảo đảm dù bộ phần tử được chọn có thể khác.
6. Mục tiêu là **tối đa hóa** tổng trọng số. Với tối thiểu hóa, có thể đảo chiều sắp xếp hoặc đổi dấu trọng số tương ứng, nhưng vẫn cần matroid.

Không nhất thiết tất cả trọng số phải dương để tìm **cơ sở**: cơ sở yêu cầu đủ hạng r(E), nên phải chọn cả một số phần tử có trọng số âm nếu cần để hoàn thành cơ sở.

## 5. Vì sao greedy trên matroid đúng: tính chất trao đổi

Có thể chứng minh bằng ý tưởng thay thế từng bước hoặc bằng hạng của các tiền tố. Cách nhìn qua **hạng tiền tố** rất rõ ràng.

Sắp E theo trọng số không tăng:

~~~text
w(e₁) ≥ w(e₂) ≥ ... ≥ w(eₘ)
Fⱼ = {e₁, e₂, ..., eⱼ}
~~~

Sau khi greedy xem xong Fⱼ, tập Gⱼ được chọn là **một tập độc lập cực đại trong Fⱼ**. Mọi phần tử bị loại trước đó không thể thêm lại vì phụ thuộc chỉ tăng khi tập chọn lớn hơn. Trong matroid, mọi tập độc lập cực đại trong Fⱼ đều có cùng kích thước r(Fⱼ), do tiên đề trao đổi. Vậy:

~~~text
|G ∩ Fⱼ| = r(Fⱼ)   với mọi j.
~~~

Với bất kỳ cơ sở B khác, B∩Fⱼ cũng độc lập, do đó:

~~~text
|B ∩ Fⱼ| ≤ r(Fⱼ) = |G ∩ Fⱼ|.
~~~

Mặt khác, mọi cơ sở đều có kích thước r(E). Có thể tách tổng trọng số của một cơ sở S theo các tiền tố:

~~~text
w(S) = w(eₘ)·r(E)
     + Σ[j=1..m-1] (w(eⱼ) - w(eⱼ₊₁)) · |S ∩ Fⱼ|.
~~~

Công thức là phép cộng dồn theo hiệu trọng số: mỗi phần tử eᵢ được tính từ w(eₘ) và các hiệu từ i tới m−1. Vì thứ tự giảm dần nên mọi hiệu w(eⱼ)−w(eⱼ₊₁) **không âm**. Thành phần w(eₘ)·r(E) giống nhau với mọi cơ sở. Mọi số lượng tiền tố của G không nhỏ hơn B, nên:

~~~text
w(G) ≥ w(B) với mọi cơ sở B.
~~~

Đây là chứng minh greedy tạo cơ sở có tổng trọng số **lớn nhất**, kể cả khi có trọng số âm. Điểm toán học quan trọng chính là (M3), vì nó bảo đảm tập cực đại của mọi tiền tố đạt hạng của tiền tố.

Một cách giải thích tương đương là **lập luận trao đổi**: nếu cơ sở tối ưu ban đầu chưa chứa phần tử mà greedy vừa chọn, có thể thay một phần tử khác bằng lựa chọn tham lam mà không làm tổng trọng số giảm, đồng thời giữ tính độc lập và số lượng phần tử; lặp tới khi thu được cơ sở khớp với greedy.

**Không được dùng riêng câu “greedy chọn tốt nhất ở mỗi bước” làm chứng minh:** nếu thiếu tính chất trao đổi, bước chọn tốt nhất cục bộ có thể chặn một tổ hợp có tổng lợi ích lớn hơn.

## 6. Phân biệt cơ sở tối ưu và tập độc lập tối ưu khi có trọng số âm

Xét hai bài toán:

- **Maximum-weight basis:** phải trả một **cơ sở** của matroid, nên số phần tử bằng r(E). Greedy duyệt **toàn bộ E**, thêm mọi phần tử còn giữ được độc lập, kể cả có trọng số âm.
- **Maximum-weight independent set:** trả bất kỳ tập độc lập S, không yêu cầu cực đại. Nếu trọng số âm, **không nên thêm phần tử âm**, vì bỏ nó sẽ giữ độc lập và tăng tổng.

Với bài toán tập độc lập tùy ý, một cách đúng là chỉ xét các phần tử có **trọng số dương**, theo thứ tự không tăng, thêm nếu độc lập. Các phần tử 0 có thể bỏ vì không cải thiện mục tiêu; nếu muốn một nghiệm tối ưu khác, có thể chấp nhận số 0 nhưng cần nêu rõ quy ước. Lý do: khi hạn chế tập nền về các phần tử dương, ta vẫn có matroid (matroid restriction); trên miền này mọi phần tử được thêm đều tăng tổng, và có thể mở rộng một tập độc lập tối ưu thành cơ sở của matroid giới hạn mà không giảm trọng số.

### Ví dụ uniform matroid

E={a,b,c}, chỉ được chọn nhiều nhất 2 phần tử (uniform matroid hạng 2):

~~~text
w(a)=7, w(b)=-1, w(c)=-3
~~~

- Cơ sở trọng số lớn nhất: {a,b}, tổng 6, vì cần đúng 2 phần tử.
- Tập độc lập trọng số lớn nhất: {a}, tổng 7, vì không buộc chọn đủ hạng.
- Nếu một thuật toán tìm cơ sở dừng khi gặp −1, nó trả **không phải cơ sở**. Nếu một thuật toán tìm tập độc lập chọn −1 chỉ để “cho đủ”, nó trả **không tối ưu**.

Với **graphic matroid**, maximum-weight basis tương ứng rừng khung trọng số lớn nhất, có thể chứa cạnh âm để nối đủ mỗi thành phần của đồ thị gốc. Maximum-weight independent set chỉ là rừng không chu trình có tổng trọng số cao nhất và **có thể không nối đủ**, đặc biệt khi cạnh nối thêm mang trọng số âm.

## 7. Graphic matroid và Kruskal theo thứ tự giảm

Định lý matroid cho một phiên bản **maximum spanning forest** của Kruskal:

1. Liệt kê mọi cạnh trong đồ thị vô hướng, bao gồm cạnh âm, cạnh song song và self-loop nếu có.
2. Sắp xếp cạnh theo trọng số **giảm dần**.
3. Duy trì tập cạnh đã chọn không có chu trình.
4. Xét từng cạnh (u,v); chọn nếu u và v đang thuộc **hai thành phần khác nhau** của rừng đã chọn, bỏ qua nếu cùng thành phần.
5. Kết thúc sau khi xét hết cạnh; kết quả là một **rừng khung** trong từng thành phần liên thông gốc, có tổng trọng số lớn nhất trong các rừng khung.

Để tối thiểu tổng trọng số, đổi thành thứ tự **tăng dần**: đó là minimum spanning forest/một dạng thuật toán Kruskal quen thuộc.

### DSU làm independence oracle

Disjoint Set Union (Union-Find) hỗ trợ:

- find(u): tìm đại diện thành phần chứa u.
- union(u,v): hợp nhất hai thành phần nếu khác nhau; trả true khi thêm cạnh không tạo chu trình, false nếu có chu trình.

Nhờ nén đường đi và union-by-size/rank, mỗi thao tác DSU có chi phí khấu hao gần hằng số, chuẩn hơn là **O(α(n))** theo ký hiệu inverse Ackermann. Thuật toán cần thêm một lần sắp xếp cạnh.

Khi đồ thị không liên thông, kết quả là **rừng**, không phải một cây bao phủ tất cả n đỉnh. Nếu đồ thị có n đỉnh và c thành phần liên thông (tính cả đỉnh cô lập), mỗi cơ sở graphic matroid có đúng n−c cạnh.

### Tại sao không chọn self-loop dù trọng số lớn?

Cạnh (v,v) tự tạo chu trình, nên không thuộc bất kỳ tập độc lập nào của graphic matroid. Greedy phải **loại** cạnh ấy ngay cả khi nó là cạnh có trọng số cao nhất. Tương tự, cạnh nối hai đỉnh đã liên thông qua các cạnh được chọn tạo chu trình và phải bị loại.

Điều kiện chọn là “**giữ độc lập**”, không phải “trọng số cao thì luôn lấy”.

## 8. Ví dụ chạy tay: có cạnh âm và vòng tự khép

Đồ thị có 5 đỉnh V={0,1,2,3,4} và các cạnh:

| Tên | Hai đỉnh | Trọng số |
| --- | --- | ---: |
| loop | (4,4) | 12 |
| AB | (0,1) | 9 |
| AC | (0,2) | 8 |
| BC | (1,2) | 7 |
| BD | (1,3) | 6 |
| CD | (2,3) | 5 |
| DE | (3,4) | −2 |
| CE | (2,4) | −4 |

Duyệt trọng số giảm dần:

| Lượt | Cạnh | Lựa chọn | Giải thích |
| ---: | --- | --- | --- |
| 1 | loop, 12 | Bỏ | (4,4) là self-loop, luôn tạo chu trình |
| 2 | AB, 9 | Chọn | Nối 0 và 1, trước đó độc lập |
| 3 | AC, 8 | Chọn | Nối thêm đỉnh 2 vào thành phần của 0 |
| 4 | BC, 7 | Bỏ | 1 và 2 đã liên thông qua 0 |
| 5 | BD, 6 | Chọn | Nối đỉnh 3 vào thành phần đã chọn |
| 6 | CD, 5 | Bỏ | 2 và 3 đã liên thông |
| 7 | DE, −2 | Chọn | Nối đỉnh 4; dù âm vẫn cần cho cơ sở |
| 8 | CE, −4 | Bỏ | 2 và 4 đã liên thông |

Kết quả:

~~~text
Chosen edges: [AB, AC, BD, DE]
Total = 9 + 8 + 6 - 2 = 21
Selected edge count = 4 = n - c = 5 - 1
~~~

Đồ thị gốc liên thông, nên cơ sở có 4 cạnh. Nếu bỏ DE chỉ vì trọng số âm, tập còn lại vẫn độc lập nhưng không phải cơ sở (đỉnh 4 chưa được kết nối), nên **không đáp ứng mục tiêu rừng khung**.

Một cây khung khác là [AB, AC, BD, CE] có tổng 9+8+6−4=19, thấp hơn 21. Không cần thử tất cả cây bằng thuật toán chính: matroid bảo đảm greedy tối ưu. Tuy nhiên, với đồ thị nhỏ, **liệt kê tất cả rừng khung** là một cách kiểm thử độc lập tốt.

## 9. Java 17+: chương trình maximum spanning forest hoàn chỉnh

Ví dụ bên dưới sắp xếp các cạnh theo trọng số giảm dần; khi đồng trọng số, dùng tên cạnh tăng dần để kết quả minh họa có thứ tự xác định. DSU kiểm tra tính độc lập. Các giá trị âm vẫn được xem xét vì mục tiêu là **cơ sở**.

Hợp đồng:

- n là số đỉnh, đánh số từ 0 đến n−1; cho phép n=0 khi không có cạnh.
- edges là danh sách không null; mỗi cạnh và tên cạnh không null; hai đầu mút phải nằm trong [0,n).
- Đồ thị vô hướng; cho phép self-loop và cạnh song song nhưng chúng có thể bị loại bởi DSU.
- Trả một danh sách cạnh mới bất biến về cấu trúc, tổng trọng số kiểu long và số thành phần cuối.
- Danh sách đầu vào không bị sắp xếp hoặc sửa.
- n<0 hoặc đầu mút sai gây IllegalArgumentException; null gây NullPointerException; nếu tổng trọng số vượt giới hạn long, Math.addExact báo ArithmeticException thay vì âm thầm tràn.

Lưu tệp **MatroidGreedyExample.java**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class MatroidGreedyExample {
    private MatroidGreedyExample() {}

    public record Edge(String name, int u, int v, long weight) {}

    public record Forest(
            List<Edge> chosen, long totalWeight, int components) {}

    private static final class DSU {
        private final int[] parent;
        private final int[] size;
        private int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            while (x != parent[x]) {
                parent[x] = parent[parent[x]];
                x = parent[x];
            }
            return x;
        }

        boolean union(int a, int b) {
            int rootA = find(a);
            int rootB = find(b);

            if (rootA == rootB) {
                return false;
            }
            if (size[rootA] < size[rootB]) {
                int temp = rootA;
                rootA = rootB;
                rootB = temp;
            }

            parent[rootB] = rootA;
            size[rootA] += size[rootB];
            components--;
            return true;
        }

        int components() {
            return components;
        }
    }

    /**
     * Maximum-weight spanning forest of an undirected graph.
     * Considers negative edges when needed to complete a basis.
     * Supports parallel edges and self-loops.
     */
    public static Forest maximumSpanningForest(
            int vertices, List<Edge> edges) {
        if (vertices < 0) {
            throw new IllegalArgumentException("vertices < 0");
        }
        Objects.requireNonNull(edges, "edges");

        List<Edge> ordered = new ArrayList<>(edges);
        for (Edge e : ordered) {
            Objects.requireNonNull(e, "edge");
            Objects.requireNonNull(e.name(), "edge.name");
            if (e.u() < 0 || e.u() >= vertices
                    || e.v() < 0 || e.v() >= vertices) {
                throw new IllegalArgumentException("invalid endpoint");
            }
        }

        ordered.sort(
                Comparator.comparingLong(Edge::weight)
                        .reversed()
                        .thenComparing(Edge::name));

        DSU dsu = new DSU(vertices);
        List<Edge> chosen = new ArrayList<>();
        long total = 0L;

        for (Edge e : ordered) {
            if (dsu.union(e.u(), e.v())) {
                chosen.add(e);
                total = Math.addExact(total, e.weight());
            }
        }

        return new Forest(
                List.copyOf(chosen), total, dsu.components());
    }

    private static List<String> names(Forest forest) {
        return forest.chosen().stream()
                .map(Edge::name)
                .toList();
    }

    public static void main(String[] args) {
        List<Edge> graph = List.of(
                new Edge("loop", 4, 4, 12),
                new Edge("AB", 0, 1, 9),
                new Edge("AC", 0, 2, 8),
                new Edge("BC", 1, 2, 7),
                new Edge("BD", 1, 3, 6),
                new Edge("CD", 2, 3, 5),
                new Edge("DE", 3, 4, -2),
                new Edge("CE", 2, 4, -4));

        Forest result = maximumSpanningForest(5, graph);
        System.out.println("Selected: " + names(result));
        System.out.println("Total weight: " + result.totalWeight());
        System.out.println("Components: " + result.components());
        System.out.println("Original edge count: " + graph.size());

        List<Edge> negative = List.of(
                new Edge("X", 0, 1, -2),
                new Edge("Y", 1, 2, -3),
                new Edge("Z", 0, 2, -4));
        Forest neg = maximumSpanningForest(3, negative);
        System.out.println("Negative basis edges: " + names(neg));
        System.out.println("Negative basis weight: " + neg.totalWeight());

        Forest empty = maximumSpanningForest(0, List.of());
        System.out.println("Empty graph components: "
                + empty.components());

        try {
            maximumSpanningForest(
                    2, List.of(new Edge("bad", 0, 2, 3)));
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid endpoint: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac MatroidGreedyExample.java
java MatroidGreedyExample
~~~

Stdout chính xác:

~~~text
Selected: [AB, AC, BD, DE]
Total weight: 21
Components: 1
Original edge count: 8
Negative basis edges: [X, Y]
Negative basis weight: -5
Empty graph components: 0
Invalid endpoint: IllegalArgumentException
~~~

Trong đồ thị có ba cạnh âm, thuật toán vẫn chọn [X,Y] để nối đủ ba đỉnh. Tổng −5 là tối ưu **trong các cây khung** của đồ thị ấy; tập rỗng với tổng 0 có lợi hơn nếu mục tiêu là **tập cạnh độc lập trọng số lớn nhất**, không phải cây khung. Đây là một phép thử trực tiếp cho sự khác biệt giữa hai hợp đồng.

Danh sách kết quả được tạo mới bằng List.copyOf; code không sắp xếp hoặc sửa List<Edge> đầu vào. Các bản ghi Edge là record bất biến. Tên cạnh chỉ phục vụ hiển thị và giải quyết thứ tự hòa, không ảnh hưởng điều kiện độc lập.

## 10. Phân tích độ phức tạp và giả thiết máy tính

Gọi n=|V| và m=|E|:

| Công đoạn | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Sao chép/kiểm tra danh sách cạnh | O(m) | O(m) |
| Sắp xếp các cạnh | O(m log m) | Phụ thuộc thư viện sắp xếp và cấu trúc dữ liệu |
| Khởi tạo DSU | O(n) | O(n) |
| m lần kiểm tra/hợp nhất bằng DSU | O(m α(n)) khấu hao | O(n) cho cấu trúc DSU |
| Lưu tập cạnh kết quả | O(m) chỗ tối đa | O(m) |
| Tổng | O(m log m + m α(n) + n) | O(m+n) |

Với n,m nhỏ như 0 hoặc 1, có thể viết O(m log(m+1)+m α(n+1)+n) để tránh diễn giải log 0. Trong trường hợp đồ thị thông thường, bước sắp xếp thường chi phối thời gian. Nếu các cạnh đã được cung cấp đúng thứ tự giảm và không cần sao chép để sắp xếp, có thể bỏ chi phí sort khỏi giai đoạn greedy, nhưng vẫn phải giữ DSU.

**Independence oracle quyết định chi phí thực tế.** Thuật toán greedy matroid tổng quát xét O(|E|) phần tử sau khi sort; mỗi lần thử độc lập có thể tốn nhiều thời gian hơn DSU, ví dụ kiểm tra hạng ma trận đối với linear matroid. Không nên khẳng định một thuật toán trên mọi matroid đều có độ phức tạp chính xác O(m log m) nếu chưa nói rõ chi phí oracle.

Nếu có m cạnh và phải lưu tất cả để sắp xếp, bộ nhớ O(m) là tự nhiên. Nếu trọng số rất lớn, code dùng Math.addExact để bắt tràn long; thuật toán toán học làm việc với tổng chính xác, còn triển khai số nguyên hữu hạn cần có chính sách tràn rõ ràng. Với yêu cầu tổng vượt long, có thể chuyển sang BigInteger và tính thêm chi phí số học.

## 11. Phản ví dụ: 0/1 knapsack thường không phải matroid

Xét bài toán chọn vật phẩm có **trọng lượng** và tổng trọng lượng không vượt sức chứa 4:

| Vật phẩm | Trọng lượng | Giá trị |
| --- | ---: | ---: |
| a | 3 | 4 |
| b | 2 | 3 |
| c | 2 | 3 |

Họ các tập chọn hợp lệ có tập rỗng và tính di truyền. Nhưng lấy:

~~~text
A = {a}     : trọng lượng 3, |A|=1
B = {b,c}   : trọng lượng 4, |B|=2
~~~

Cả A, B đều hợp lệ, nhưng không thể thêm b hoặc c vào A: trọng lượng 3+2=5 vượt 4. Không có e∈B\A mà A∪{e} hợp lệ. Vậy **tiên đề trao đổi thất bại**, nên hệ tập này không phải matroid.

Nếu greedy chỉ ưu tiên **giá trị vật phẩm giảm dần**, nó chọn a trước (giá trị 4), rồi không chọn được b/c, tổng 4. Nghiệm tốt hơn là {b,c}, tổng 6. Không thể dùng “greedy đúng trên matroid” làm chứng minh cho bài toán này.

Ngay cả tham lam theo **giá trị/trọng lượng** cũng không giải đúng mọi 0/1 knapsack: sức chứa 50, các vật phẩm (trọng lượng, giá trị)=(10,60),(20,100),(30,120). Theo tỷ lệ giảm, lấy (10,60) và (20,100), tổng 160; chọn hai vật phẩm (20,100),(30,120) cho tổng 220. Quy tắc tỷ lệ tối ưu cho **fractional knapsack** trong mô hình cho phép lấy một phần vật phẩm, không tự áp dụng cho knapsack 0/1.

## 12. Phản ví dụ: lịch trình khoảng thời gian và ranh giới của matroid

Cho các khoảng nửa mở:

~~~text
a = [0,4)
b = [0,2)
c = [2,4)
~~~

Quy ước các khoảng không giao nhau có thể được chọn cùng. Họ các tập lịch trình không xung đột có tính di truyền. Xét:

~~~text
A = {a},          |A| = 1
B = {b, c},       |B| = 2
~~~

Cả hai tập hợp lệ. Nhưng thêm b vào A xung đột với a; thêm c vào A cũng xung đột với a. Vậy **vi phạm tiên đề trao đổi** và không phải matroid.

Dù vậy, quy tắc **chọn công việc có thời điểm kết thúc sớm nhất** vẫn tối ưu cho bài toán chọn **nhiều khoảng không chồng lặp nhất** với trọng số bằng nhau. Đây là một thuật toán tham lam đúng nhờ **chứng minh trao đổi riêng cho bài toán**, chứ không nhờ hệ tập lịch trình là matroid.

Nếu mỗi công việc có trọng số khác nhau và muốn tối đa tổng trọng số, việc chọn chỉ theo thời điểm kết thúc sớm nhất thường sai; bài toán **weighted interval scheduling** kinh điển dùng quy hoạch động sau khi sắp xếp theo thời điểm kết thúc. Bài học: **không là matroid không có nghĩa mọi thuật toán greedy đều sai**, nhưng không được viện dẫn định lý matroid mà thiếu tiên đề.

## 13. Các điều kiện khác làm greedy không còn được bảo đảm

Ngoài việc thiếu (M3), còn các nguồn sai lệch:

### Trọng số có tương tác

Nếu “lợi ích của nhóm” không phải tổng các w(e) cố định, ví dụ chọn hai phần tử cùng nhau tạo hiệu ứng cộng hưởng hoặc triệt tiêu, định lý maximum-weight basis tuyến tính không trực tiếp áp dụng. Cần biểu diễn đúng hàm mục tiêu và tìm một định lý khác nếu muốn dùng greedy.

### Nhiều ràng buộc matroid cùng lúc

Một tập độc lập phải thuộc **giao của hai matroid** không nhất thiết tạo một matroid mới. Có thuật toán chuyên biệt cho **matroid intersection**; không thể mặc nhiên áp dụng đúng một lượt greedy của matroid đơn lẻ cho mọi bài toán giao hai ràng buộc.

### Independence oracle sai

Nếu kiểm tra chu trình sai, ví dụ chỉ kiểm tra cạnh hiện tại có cùng hai đầu với một cạnh trước mà không kiểm tra đường đi qua nhiều cạnh, thuật toán có thể chọn chu trình. Nếu dùng tính độc lập tuyến tính trên số thực với tolerance không phù hợp, oracle có thể đánh dấu độc lập sai. Định lý chỉ áp dụng khi điều kiện độc lập được kiểm tra chính xác.

### Đầu vào thay đổi trong khi chạy

Matroid được định nghĩa trên một tập nền và họ I cố định. Nếu các cạnh/giới hạn quota/trọng số thay đổi sau một số lựa chọn mà thuật toán không cập nhật lại mô hình, chứng minh tham lam cho bài toán ban đầu không còn mô tả mục tiêu mới.

### Trọng số bằng nhau

Thứ tự hòa có thể làm **tập nghiệm** khác nhau nhưng tổng trọng số tối ưu không đổi. Nếu yêu cầu “nghiệm từ điển nhỏ nhất” hoặc một quy tắc phụ cụ thể, phải thiết kế tie-break phù hợp và chứng minh nó đáp ứng mục tiêu bổ sung. Trong Java ví dụ dùng tên tăng dần để kết quả có thể tái lập, không khẳng định đó là nghiệm duy nhất.

## 14. Kiểm thử và cách xác minh độc lập

### 14.1. Các tình huống bắt buộc

| Đầu vào hoặc mô hình | Điều cần xác nhận |
| --- | --- |
| Đồ thị mẫu 5 đỉnh, 8 cạnh | Chọn [AB,AC,BD,DE], tổng 21 |
| Có self-loop trọng số cao | Không chọn self-loop |
| Có cạnh tạo chu trình | Loại nếu hai đầu đã liên thông |
| Cạnh trọng số âm cần nối hai thành phần | Vẫn chọn cho rừng khung |
| Ba cạnh âm trên tam giác | Chọn hai cạnh −2,−3; tổng −5 cho **cơ sở** |
| Đồ thị không liên thông | Trả rừng, số cạnh n−c |
| Đồ thị n=0, m=0 | Danh sách chọn rỗng, 0 thành phần |
| Đỉnh cô lập | Giữ một thành phần riêng, không tự tạo cạnh |
| Cạnh song song | Không chọn hai cạnh tạo chu trình |
| Hai cạnh bằng trọng số | Tổng đúng; tập chọn có thể khác tùy tie-break |
| Đầu mút ngoài [0,n) | IllegalArgumentException |
| edges hoặc một Edge null | NullPointerException |
| Tổng trọng số long bị tràn | ArithmeticException do Math.addExact |
| Uniform matroid hạng 2 với trọng số [7,−1,−3] | Cơ sở tối ưu tổng 6; tập độc lập tối ưu tổng 7 |

### 14.2. Oracle liệt kê toàn bộ cho đồ thị nhỏ

Để thử Kruskal một cách độc lập, với m cạnh đủ nhỏ có thể liệt kê 2^m tập con:

1. Tìm số thành phần liên thông c của **đồ thị gốc** (bỏ qua self-loop khi nối thành phần).
2. Với từng tập con F, kiểm tra F không có chu trình.
3. Chỉ giữ những F có đúng **n−c cạnh**; đó là những cơ sở của graphic matroid.
4. Tính tổng trọng số của từng cơ sở và lấy giá trị lớn nhất.
5. So sánh với tổng của lời giải Kruskal; đồng thời kiểm tra các cạnh được chọn không có chu trình và số cạnh đúng n−c.

Với m lớn, không dùng cách này vì thời gian tăng theo 2^m; đây là **oracle kiểm thử cho đầu vào nhỏ**, không phải lời giải sản xuất.

Có thể kiểm tra thêm maximum-weight independent set bằng cách liệt kê **tất cả** tập cạnh không có chu trình (không ép số cạnh n−c), so sánh với greedy chỉ xét cạnh có trọng số dương. Hai mục tiêu này có thể cho tổng khác nhau khi có cạnh âm.

### 14.3. Kiểm thử tiên đề trao đổi trên tập nền nhỏ

Nếu xây dựng một họ I mới và nghi nó là matroid, với tập nền nhỏ:

- Kiểm tra ∅ thuộc I.
- Với mọi B độc lập và mọi A⊆B, kiểm tra A độc lập.
- Với mọi A,B độc lập có |A|<|B|, tìm ít nhất một e∈B\A sao cho A∪{e} độc lập.

Kiểm thử hữu hạn không thay thế chứng minh tổng quát cho mọi kích thước, nhưng có thể tìm phản ví dụ sớm. Nếu tìm được **một cặp A,B vi phạm (M3)**, đã đủ kết luận mô hình ấy **không phải matroid**.

## 15. Checklist áp dụng greedy matroid

- [ ] Đã xác định chính xác tập nền E và điều kiện độc lập I?
- [ ] ∅ có hợp lệ và tính di truyền có đúng?
- [ ] Đã chứng minh hoặc có cơ sở rõ ràng cho tiên đề **trao đổi**?
- [ ] Mục tiêu là **cơ sở tối ưu** hay **tập độc lập tối ưu**?
- [ ] Nếu là cơ sở, có xét cả phần tử trọng số âm cần thiết để đủ hạng?
- [ ] Nếu là tập độc lập bất kỳ, đã xử lý trọng số âm/0 phù hợp?
- [ ] Hàm mục tiêu thực sự là tổng trọng số từng phần tử cố định?
- [ ] Đã sắp thứ tự tăng hay giảm đúng với tối thiểu/tối đa?
- [ ] Independence oracle kiểm tra đúng dưới dữ liệu đầu vào được bảo toàn?
- [ ] Đã tính chi phí sắp xếp và kiểm tra độc lập trong độ phức tạp?
- [ ] Nếu là đồ thị, đã xử lý self-loop, cạnh song song, đồ thị không liên thông và cạnh âm?
- [ ] Nếu hệ tập không là matroid, đã tránh suy diễn định lý greedy mà chưa có chứng minh riêng?
- [ ] Đã kiểm thử cả ví dụ thành công lẫn một phản ví dụ trao đổi?

**Kết luận:** sức mạnh của lựa chọn tham lam trên matroid đến từ **tính di truyền và tiên đề trao đổi**, không chỉ từ việc chọn phần tử có điểm cao. Trên một matroid, duyệt phần tử theo trọng số giảm và thêm khi còn độc lập cho **cơ sở có tổng trọng số lớn nhất**. Muốn tìm tập độc lập tùy ý, phải xét tác động của trọng số âm; muốn áp dụng cho ràng buộc khác như knapsack hay lịch trình khoảng, phải kiểm chứng tiên đề hoặc xây dựng chứng minh riêng thay vì mặc định greedy luôn đúng.
