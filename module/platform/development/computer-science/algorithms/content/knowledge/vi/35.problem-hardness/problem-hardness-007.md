# Nhận diện các mô hình như SAT, Clique và tập phủ

## 1. Vì sao phải nhận diện mô hình độ khó?

Trong bài toán thực tế, đề bài hiếm khi nói thẳng: “Đây là SAT”, “hãy giải Clique”, hoặc “hãy giải Set Cover”. Nó thường kể một tình huống: lựa chọn các phương án có ràng buộc logic, tìm nhiều đối tượng đôi một tương thích, loại bỏ những đối tượng gây xung đột, hay chọn ít tài nguyên nhất để đáp ứng tất cả yêu cầu. **Nhận diện mô hình** nghĩa là xác định đối tượng, ràng buộc, mục tiêu và sau đó ánh xạ chúng vào một bài toán chuẩn có lý thuyết/thuật toán tương ứng.

Ba nhóm quan trọng trong lý thuyết độ khó:

- **SAT / 3SAT:** Có tồn tại phép gán TRUE/FALSE cho các biến sao cho tất cả ràng buộc logic đều đúng?
- **CLIQUE:** Có tồn tại ít nhất k đỉnh trong đồ thị mà **mọi cặp** giữa chúng đều nối cạnh?
- **SET COVER (tập phủ):** Có thể chọn không quá k tập con để **mọi phần tử** trong vũ trụ được bao phủ?

Hai mô hình đồ thị liên hệ chặt chẽ là **INDEPENDENT SET (tập độc lập)** — không có cạnh giữa bất cứ hai đỉnh được chọn — và **VERTEX COVER (phủ đỉnh)** — mỗi cạnh có ít nhất một đầu mút được chọn. Tên “tập phủ” trong nhiều bài tiếng Việt thường chỉ **Set Cover**, không nên âm thầm đồng nhất với **Vertex Cover**.

**Điều cần xác định trước khi lập mô hình:** bài hỏi **có/không** (decision), tìm một cấu hình thỏa mãn (search), đếm số cấu hình (counting) hay tìm cấu hình tốt nhất (optimization)? Dạng quyết định là dạng chuẩn khi phân loại NP-complete; dạng tối ưu thường được gọi là NP-hard.

## 2. Phân biệt P, NP, NP-hard và NP-complete

**P** là lớp các bài toán quyết định có thuật toán giải thời gian đa thức theo kích thước đầu vào. **NP** là lớp các bài toán quyết định có thể kiểm tra một *chứng chỉ* (certificate/witness) hợp lệ trong thời gian đa thức; NP không có nghĩa “non-polynomial”.

Một bài toán **NP-hard** nếu mọi bài toán trong NP có thể quy giảm đa thức tới nó. Một bài toán quyết định **NP-complete** khi (i) thuộc NP và (ii) NP-hard. Các bài toán quyết định SAT, 3SAT, CLIQUE, VERTEX COVER, SET COVER đều NP-complete.

Các dạng tối ưu **maximum clique**, **minimum vertex cover**, **minimum set cover** là NP-hard. Không gọi một bài toán tối ưu là “NP-complete” mà không xác định phiên bản quyết định hoặc một định nghĩa lớp phức tạp phù hợp.

Bài toán kiểm tra một phép gán SAT, một clique, một phủ đỉnh hay một bộ tập con được chọn đều có thuật toán đa thức. **Kiểm chứng một cấu hình dễ** không có nghĩa **tìm một cấu hình** cũng dễ.

### 2.1. Chứng chỉ có thể kiểm tra

| Bài toán quyết định | Chứng chỉ | Kiểm tra thời gian đa thức |
|---|---|---|
| SAT: công thức có thỏa? | Giá trị của mỗi biến | Tính giá trị công thức |
| 3SAT: tất cả clause có đúng? | Gán TRUE/FALSE | Mỗi clause có ≥1 literal đúng |
| CLIQUE(G,k) | Danh sách k đỉnh | Kiểm tra mọi cặp có cạnh |
| INDEPENDENT SET(G,k) | Danh sách k đỉnh | Kiểm tra mọi cặp không có cạnh |
| VERTEX COVER(G,k) | Tập ≤k đỉnh | Mỗi cạnh có đầu mút trong tập |
| SET COVER(U,S,k) | Chỉ số ≤k tập được chọn | Hợp các tập chứa U |

Khi viết chứng chỉ, phải tính cả kích thước biểu diễn. Chẳng hạn nếu số tập được liệt kê tường minh, một danh sách chỉ số tập có độ dài không quá số tập đầu vào là chứng chỉ đa thức.

### 2.2. Quy giảm đúng chiều

Viết `A ≤p B` khi có phép biến đổi từ một instance x của A thành instance f(x) của B trong thời gian đa thức và:

**x là YES của A khi và chỉ khi f(x) là YES của B.**

Do đó, nếu A đã NP-hard và A ≤p B thì B ít nhất khó như A. Không đảo chiều kết luận. Một thuật toán đa thức cho B sẽ kéo theo một thuật toán đa thức cho A bằng cách biến đổi rồi giải B.

Muốn chứng minh B NP-complete, thông thường phải chứng minh **B thuộc NP** và quy giảm **từ** một bài toán NP-complete đã biết **sang B**. Việc giảm B sang A đã khó không đủ chứng minh B cũng khó.

## 3. SAT và 3SAT: nhận ra ràng buộc logic

Một biến Boolean x nhận TRUE/FALSE. Literal là x hoặc phủ định ¬x. Một clause là phép OR các literal; một công thức CNF là phép AND các clause.

Ví dụ:

**F=(x₁∨x₂∨x₃) ∧ (¬x₁∨x₂∨¬x₃) ∧ (x₁∨¬x₂∨x₃).**

Đây là instance 3SAT vì mỗi clause có đúng ba vị trí literal. Gán x₁=TRUE, x₂=FALSE, x₃=FALSE làm tất cả clause đúng nên đây là YES.

Instance khác:

**(x₁∨x₁∨x₁) ∧ (¬x₁∨¬x₁∨¬x₁)**

là NO, vì clause đầu yêu cầu x₁=TRUE còn clause sau yêu cầu x₁=FALSE. Việc lặp literal trong một clause là một quy ước thường được cho phép khi chuyển sang dạng đúng ba vị trí; nếu đề yêu cầu **ba literal khác nhau**, phải dùng một phép biến đổi thích hợp khác.

### 3.1. Dấu hiệu nhận diện SAT trong đề thực tế

- “Mỗi tính năng được bật hoặc tắt”.
- “Nếu chọn A thì phải chọn B” → A⇒B, tương đương (¬A∨B).
- “Không chọn đồng thời A và B” → (¬A∨¬B).
- “Ít nhất một trong A,B,C phải được chọn” → (A∨B∨C).
- “Đúng một trong các phương án” → một clause “ít nhất một” cộng các clause “không cùng chọn”.
- “Tất cả quy tắc phải được thỏa mãn” → AND các ràng buộc.

Không phải mọi bài toán dùng Boolean đều tự động là SAT khó. **2SAT**, khi mỗi clause có nhiều nhất hai literal, giải được thời gian đa thức (chẳng hạn đồ thị suy diễn và thành phần liên thông mạnh). **3SAT** tổng quát NP-complete. Số literal trên mỗi clause và cấu trúc ràng buộc thay đổi bản chất độ khó.

### 3.2. Điều gì là biến, clause, nghiệm?

Cần chỉ rõ: một quyết định Boolean ứng với một biến; mỗi quy tắc được chuyển chính xác thành clause hoặc nhóm clause; phép gán thỏa tất cả clause là nghiệm. Một mô hình sai có thể quá chặt (cấm nghiệm hợp lệ) hoặc quá lỏng (cho nghiệm vi phạm yêu cầu). Luôn kiểm tra hai chiều: cấu hình hợp lệ ⇒ gán thỏa, và gán thỏa ⇒ cấu hình hợp lệ.

## 4. CLIQUE: mọi cặp cùng tương thích

Cho đồ thị vô hướng đơn G=(V,E). Một tập C⊆V là **clique** khi với mọi hai đỉnh phân biệt u,v trong C, cạnh {u,v} thuộc E. Dạng quyết định CLIQUE(G,k) hỏi có clique kích thước **ít nhất k** không.

Ví dụ, G có V={0,1,2,3} và E={(0,1),(1,2),(2,3),(3,0),(0,2)}. Các đỉnh {0,1,2} tạo clique kích thước 3 vì cả ba cạnh (0,1), (0,2), (1,2) đều tồn tại. Không có clique 4 vì cặp (1,3) không nối cạnh.

Độ khó của CLIQUE không đến từ kiểm một nhóm đã cho: kiểm k đỉnh bằng O(k²) cặp rất dễ. Khó ở chỗ phải chọn nhóm nào trong số các tập con ứng viên.

### 4.1. Khi nào dùng Clique?

Nếu cạnh biểu diễn **hai đối tượng tương thích và có thể cùng chọn**, yêu cầu chọn một nhóm mà mọi cặp cùng tương thích → clique. Ví dụ tìm k nhà nghiên cứu mà mọi cặp đã từng cộng tác, hoặc chọn k cấu hình sao cho mọi cặp không xung đột.

Nếu cạnh biểu diễn **xung đột**, chọn k đối tượng không có xung đột lại là **Independent Set**, không phải Clique trên cùng đồ thị. Có thể đổi sang **đồ thị bù** rồi tìm Clique.

### 4.2. Đồ thị bù

Đồ thị bù `Ḡ` có cùng V; với u≠v, cạnh {u,v} thuộc Ḡ **khi và chỉ khi** không thuộc G. Không thêm self-loop.

- C là clique trong G ⇔ C là independent set trong Ḡ.
- C là independent set trong G ⇔ C là clique trong Ḡ.

Đồ thị bù không phải đảo hướng cạnh; ta đang dùng đồ thị vô hướng và **bổ sung mọi cạnh còn thiếu** giữa các đỉnh phân biệt.

## 5. INDEPENDENT SET và VERTEX COVER

**Independent Set**: một tập S mà không có cạnh nào nối hai đỉnh trong S. **Vertex Cover**: một tập T mà mọi cạnh đều có ít nhất một đầu mút ở T.

Điều kiện quan trọng:

**T là vertex cover của G ⇔ V\\T là independent set của G.**

Chứng minh: nếu V\\T có cạnh uv thì cả u,v đều không ở T, nên cạnh uv chưa được phủ. Ngược lại, nếu tồn tại cạnh uv chưa có đầu mút trong T thì u,v cùng thuộc V\\T, khiến nó không độc lập.

Vì vậy:

- `INDEPENDENT SET(G,k) ⇔ VERTEX COVER(G, |V|-k)`.
- Nếu α(G) là kích thước independent set lớn nhất và τ(G) là kích thước vertex cover nhỏ nhất, **α(G)+τ(G)=|V|**.

Từ CLIQUE kết hợp đồ thị bù:

**CLIQUE(G,k) ⇔ VERTEX COVER(Ḡ, |V|-k).**

Đây là quy giảm rất ngắn và đúng chiều từ Clique sang Vertex Cover: dựng đồ thị bù, đổi ngưỡng k thành n-k. **Không** suy luận sai rằng clique trong G tương đương vertex cover n-k trên chính G.

### 5.1. Mô hình cần bỏ ít đối tượng nhất

Nếu mỗi cạnh là một cặp đối tượng **không thể cùng giữ**, muốn xóa ít đối tượng nhất để không còn cặp xung đột: chọn vertex cover tối thiểu của đồ thị xung đột. Những đỉnh còn lại tạo independent set cực đại về số lượng.

Nếu cạnh là cặp “cần ít nhất một nhân viên giám sát”, chọn ít nhân viên nhất sao cho mỗi cạnh có một người ở đầu mút cũng là Vertex Cover.

### 5.2. Vì sao maximal không phải maximum?

Một independent set **maximal** là tập không thể thêm đỉnh mới nào mà vẫn độc lập. Một independent set **maximum** có kích thước lớn nhất trong mọi independent set. Tương tự, một clique maximal không nhất thiết là clique maximum. Thuật toán tham lam dừng khi không thêm được nữa thường chỉ cho maximal, **không** bảo đảm optimal.

## 6. SET COVER: phủ mọi yêu cầu bằng ít tập nhất

Cho vũ trụ U gồm các phần tử cần được bao phủ và họ tập con S₁,S₂,...,S_m của U. Bài toán quyết định SET COVER(U,S,k) hỏi có thể chọn **không quá k tập** sao cho hợp của chúng bằng U không?

Ví dụ thực tế: các kỹ năng {Java, SQL, Docker, Testing, Security} cần có trong một đội. Mỗi ứng viên có một nhóm kỹ năng. Chọn ít ứng viên nhất để cả năm kỹ năng đều được bao phủ: **Set Cover**. Không cần mọi ứng viên được chọn phải tương thích từng cặp trừ khi đề còn có ràng buộc khác.

### 6.1. Ví dụ Greedy không tối ưu

Chọn U={1,2,3,4,5,6} và ba tập:

- A={1,2,3,4}
- B={1,2,5}
- C={3,4,6}

Hợp B∪C=U, nên chỉ cần **2 tập**. Nhưng greedy chọn tập phủ nhiều phần tử chưa phủ nhất sẽ lấy A trước (4 phần tử), sau đó cần B để phủ 5 và C để phủ 6, tổng **3 tập**. Đây là ví dụ cụ thể cho việc “chọn tập lớn nhất trước” không phải thuật toán exact.

### 6.2. Greedy và hệ số xấp xỉ

Tham lam Set Cover chọn ở mỗi bước tập phủ được nhiều phần tử **chưa** phủ nhất, cập nhật tập còn thiếu, đến khi phủ hết hoặc không thể tiến triển. Với bài toán Set Cover không trọng số, thuật toán có bảo đảm hệ số xấp xỉ **H_|U| ≤ 1+ln |U|** trong mô hình chuẩn (khi tồn tại lời giải). Đây là bảo đảm tỷ lệ giữa số tập greedy và optimum, không phải bảo đảm luôn bằng optimum.

Nếu mỗi tập có chi phí khác nhau, biến thể weighted set cover thường chọn theo tỷ lệ chi phí / số phần tử mới được phủ; không lấy ngay tập có nhiều phần tử nếu bỏ qua chi phí.

### 6.3. Set Cover khác Vertex Cover

- **Set Cover:** phần tử của U là **yêu cầu**, mỗi lựa chọn là một tập các yêu cầu được đáp ứng.
- **Vertex Cover:** phần tử cần phủ là **cạnh**, mỗi lựa chọn là **đỉnh** và “phủ” những cạnh kề nó.

Vertex Cover là một trường hợp đặc biệt có thể biểu diễn thành Set Cover: lấy U=E, và mỗi đỉnh v tương ứng tập những cạnh kề v. Vì vậy **VERTEX COVER ≤p SET COVER**. Nhưng tùy bài, biểu diễn trực tiếp dạng graph có thể cho thuật toán chuyên biệt hiệu quả hơn, chẳng hạn xấp xỉ hệ số 2 bằng maximal matching.

### 6.4. Set Cover, Exact Cover, Hitting Set

**Set Cover** cho phép các tập được chọn chồng lấn; chỉ yêu cầu mọi phần tử được phủ **ít nhất một lần**. **Exact Cover** yêu cầu mỗi phần tử được phủ **đúng một lần**. **Hitting Set** chọn một nhóm phần tử chạm vào mỗi tập trong họ; nó là dạng đối ngẫu bằng chuyển ma trận incidence, nhưng đừng hoán đổi vai trò phần tử và tập khi không làm phép biến đổi.

## 7. Quy giảm 3SAT → Clique: cấu trúc xây dựng

Đây là một phép quy giảm kinh điển để chứng minh CLIQUE NP-hard.

Đầu vào là công thức 3CNF với m clause C₀,...,C_(m-1), **mỗi clause có đúng ba vị trí literal** (có thể trùng). Dựng đồ thị:

1. Với mỗi vị trí literal trong mỗi clause, tạo một đỉnh. Tổng cộng **3m đỉnh**.
2. **Không nối cạnh** giữa các đỉnh thuộc cùng clause.
3. Giữa hai đỉnh thuộc **hai clause khác nhau**, nối cạnh khi và chỉ khi hai literal **không mâu thuẫn** nhau (không có cặp x và ¬x).
4. Hỏi đồ thị có clique kích thước **m** hay không.

Chúng ta gọi một cặp literal **tương thích** khi không đối nhau. Cặp literal cùng dấu hoặc thuộc biến khác nhau thì tương thích; ví dụ x₁ và x₁ là tương thích, x₁ và ¬x₁ là không.

### 7.1. Chứng minh chiều “SAT ⇒ Clique”

Nếu công thức thỏa, ở mỗi clause có ít nhất một literal TRUE. Chọn **một đỉnh** tương ứng với một literal TRUE ở từng clause. Hai literal TRUE dưới cùng một phép gán không thể đối nhau, nên mọi cặp đỉnh đã chọn được nối cạnh. Do đó chúng tạo thành clique m đỉnh.

### 7.2. Chứng minh chiều “Clique ⇒ SAT”

Do **không có cạnh nội bộ một clause**, một clique chứa nhiều nhất một đỉnh mỗi clause. Clique kích thước m trong đồ thị có m clause buộc phải chọn **đúng một literal từ mỗi clause**. Tất cả literal được chọn đôi một không đối nhau; gán chúng TRUE nhất quán, rồi gán tùy ý cho các biến còn lại. Mỗi clause có một literal TRUE nên công thức thỏa.

Vì xây 3m đỉnh và kiểm các cặp thuộc các clause khác nhau, thời gian và kích thước đồ thị là đa thức theo kích thước đầu vào. Mệnh đề **có/không** được bảo toàn chính xác.

### 7.3. Vì sao không nối đỉnh trong cùng clause?

Nếu nối các literal cùng clause với nhau, một clique cỡ m có thể chọn nhiều literal từ một clause và bỏ hẳn clause khác; khi đó clique không còn đại diện cho phép chọn **một literal thỏa từ mỗi clause**. Đó là lỗi phổ biến khi tự dựng reduction.

### 7.4. Ví dụ công thức không thỏa

F=(x₁∨x₁∨x₁) ∧ (¬x₁∨¬x₁∨¬x₁).

Có m=2 và 6 đỉnh, ba đỉnh cho mỗi clause. Không có cạnh giữa các clause vì mọi cặp literal đều là x₁ đối với ¬x₁; trong cùng clause cũng không có cạnh. Clique lớn nhất chỉ có kích thước 1, vì thế câu hỏi CLIQUE(G,2) là NO, khớp với SAT là NO.

### 7.5. Trường hợp không có clause

Công thức là AND của tập clause rỗng thì đúng theo quy ước logic (TRUE). Đồ thị reduction có 0 đỉnh và ta hỏi clique kích thước 0; tập rỗng là clique kích thước 0. Nếu một API không cho k=0, cần xử lý riêng ở bước tiền xử lý để giữ nguyên kết quả YES.

## 8. Ghép phép quy giảm: 3SAT → Clique → Vertex Cover → Set Cover

Sơ đồ logic của các phép biến đổi:

```text
3SAT (m clause, mỗi clause 3 literal)
    | tạo 3m đỉnh literal và cạnh tương thích
    v
CLIQUE(G, m)
    | lấy đồ thị bù G' và đổi ngưỡng n-m
    v
VERTEX COVER(G', n-m)
    | U = E(G'); mỗi đỉnh ứng với tập cạnh kề
    v
SET COVER(U, {Inc(v)}, n-m)
```

Mỗi mũi tên là phép biến đổi **đa thức** bảo toàn YES/NO. Vì 3SAT NP-complete, dãy reduction này cho thấy các bài toán phía sau NP-hard; kết hợp việc thuộc NP của phiên bản quyết định để có NP-complete.

**Lưu ý ngưỡng:** trong phép biến đổi CLIQUE(G,k) sang VERTEX COVER(Ḡ,n-k), n là số **đỉnh của G**, không phải số clause, trừ khi tình cờ cùng giá trị. Với 3SAT reduction trên 3m đỉnh, ngưỡng phủ đỉnh của **đồ thị bù** là 3m−m=2m.

## 9. Nhận diện bằng câu hỏi “Tôi đang chọn gì?”

| Dấu hiệu trong đề | Mô hình đáng thử | Cần xác minh |
|---|---|---|
| Biến bật/tắt, quy tắc nếu-thì, OR/AND | SAT/3SAT | Có thể biểu diễn clause tương đương? |
| Chọn k người mà **mọi cặp hợp nhau** | Clique | Cạnh thật sự mang nghĩa tương thích? |
| Chọn k người mà **không cặp nào xung đột** | Independent Set | Cạnh mang nghĩa xung đột? |
| Loại ít đỉnh nhất để không còn cạnh xung đột | Vertex Cover | Mỗi cạnh có ít nhất một đầu bị loại? |
| Chọn ít tài nguyên nhất bao phủ mọi yêu cầu | Set Cover | Mỗi yêu cầu xuất hiện trong ít nhất một tập? |
| Chọn các tập không giao nhau, phủ đúng mỗi mục một lần | Exact Cover | Có điều kiện “đúng một lần”? |
| Chọn phần tử để chạm vào mọi nhóm ràng buộc | Hitting Set | Chọn phần tử hay chọn cả tập? |

### 9.1. Quy trình mô hình hóa từ ngôn ngữ tự nhiên

1. Gạch chân những **đối tượng có thể chọn**, những **ràng buộc phải đúng**, và **mục tiêu** (ít nhất k, nhiều nhất k, tối thiểu, tối đa).
2. Đặt biến/đỉnh/phần tử/tập và quy định ý nghĩa của chúng.
3. Chuyển ràng buộc sang công thức Boolean hoặc quan hệ cạnh/quan hệ phủ.
4. Chứng minh hai chiều: một lời giải gốc hợp lệ sinh lời giải mô hình, và lời giải mô hình khôi phục được lời giải gốc hợp lệ.
5. Kiểm ví dụ nhỏ, ca rỗng, khóa trùng và dấu bất đẳng thức của ngưỡng.
6. Sau khi nhận diện, chọn thuật toán tùy kích thước và nhu cầu exact hay gần đúng; **không** luôn chạy brute force chỉ vì bài toán NP-complete.

### 9.2. Một đề có thể mang nhiều ràng buộc

Ví dụ: chọn ít nhà cung cấp để bao phủ đủ mặt hàng **nhưng** hai nhà cung cấp cạnh tranh không được chọn cùng nhau. Đây không chỉ là Set Cover thuần túy; cần thêm ràng buộc xung đột. Có thể dùng SAT/Integer Programming hoặc biến thể Set Cover có xung đột. Nhận diện một phần cấu trúc không có nghĩa được bỏ phần còn lại của đề.

## 10. Từ nhận diện đến thuật toán phù hợp

Với instance nhỏ, có thể dùng brute force để xác nhận hoặc xây một oracle: SAT duyệt 2^n phép gán; Clique duyệt 2^|V| tập đỉnh; Vertex Cover duyệt 2^|V| tập đỉnh; Set Cover duyệt 2^m tập con các tập.

Với input lớn hơn:

- **SAT:** DPLL/CDCL, propagation, học clause, SAT solver chuyên dụng. 2SAT có thể giải bằng SCC theo thời gian tuyến tính theo kích thước công thức.
- **CLIQUE:** branch-and-bound, pruning bằng tô màu/cận trên, thuật toán maximum clique chuyên dụng; xấu nhất vẫn mũ.
- **VERTEX COVER:** với k nhỏ, có thuật toán tham số hóa, ví dụ rẽ nhánh theo một cạnh (u,v): một phủ đỉnh phải chứa u **hoặc** v; sâu tối đa k, sinh O(2^k) nhánh, cộng xử lý đa thức.
- **SET COVER:** greedy xấp xỉ, branch-and-bound, quy hoạch nguyên, rẽ nhánh theo phần tử chưa phủ, và các solver chuyên dụng.
- **Khi cần nghiệm gần đúng:** Vertex Cover có thuật toán xấp xỉ hệ số 2 từ một maximal matching; Set Cover greedy có hệ số O(log |U|). Với Clique tổng quát, không tự gán cho một heuristic đơn giản hệ số xấp xỉ mạnh.

### 10.1. Trường hợp nhỏ và cấu trúc đặc biệt

Việc một bài tổng quát NP-complete **không có nghĩa mọi instance đều khó**, cũng không có nghĩa P≠NP đã được chứng minh. Ta có thể tận dụng đồ thị cây, độ rộng cây nhỏ, ràng buộc dạng Horn, số biến ít, k nhỏ, hoặc một oracle thời gian mũ trên n nhỏ. Cần phân biệt **worst-case của cả họ bài toán** với **độ khó của một instance cụ thể**.

### 10.2. Tối ưu khác quyết định

Ví dụ CLIQUE(G,k) hỏi YES/NO, còn maximum clique yêu cầu tìm kích thước lớn nhất. Với một thuật toán quyết định, có thể tìm optimum bằng gọi nhiều ngưỡng k (và truy vết lời giải nếu solver cung cấp witness) với overhead đa thức. Nhưng thuật toán tối ưu chưa vì thế thuộc NP dưới định nghĩa chuẩn của các lớp quyết định.

## 11. Kiểu dữ liệu và quy mô của demo Java

Mã Java 17 trong bài dùng `int` bitmask để minh họa các oracle **chính xác** cho dữ liệu nhỏ:

- SAT có tối đa 18 biến; literal mã hóa bằng số nguyên có dấu: `+i` cho x_i, `-i` cho ¬x_i (i bắt đầu từ 1).
- Mỗi clause của 3SAT có **đúng 3 vị trí literal**, trùng lặp có thể có; có tối đa 6 clause để đồ thị reduction không quá 18 đỉnh.
- Đồ thị vô hướng đơn có tối đa 18 đỉnh, được kiểm qua ma trận kề.
- Set Cover có tối đa 18 phần tử và 18 tập; bit j của int biểu diễn phần tử j (0-based). Tập rỗng hợp lệ nhưng không giúp phủ.
- Chương trình trả -1 cho Set Cover **không thể phủ**; quyết định k≤... phải diễn giải -1 là NO, không so -1<=k một cách mù quáng.

Những giới hạn nhỏ này nhằm bảo đảm brute-force oracle chạy nhanh, **không** phải giới hạn của mô hình lý thuyết. Khi bài toán có n lớn hơn, cần solver/thuật toán chuyên biệt.



## 12. Java 17 hoàn chỉnh: kiểm tra SAT, Clique, Vertex Cover, Set Cover

Chương trình sau có bốn bộ giải **exact cho instance nhỏ**: duyệt phép gán SAT, duyệt tập đỉnh Clique, duyệt tập đỉnh Vertex Cover và duyệt họ tập Set Cover. Ngoài ra, nó dựng đồ thị phép quy giảm 3SAT → Clique và dựng đồ thị bù để kiểm định hai tương đương NP-hard. Với Set Cover, mã dùng **một oracle độc lập bằng quy hoạch động trên mặt nạ phần tử đã phủ**, thay vì chỉ so hai bản duyệt tập giống nhau.

Lưu vào tệp `SatCliqueCoverDemo.java`. Chạy Java 17 trở lên; không cần thư viện ngoài JDK.

```java
import java.util.Arrays;
import java.util.Random;

public final class SatCliqueCoverDemo {
    private SatCliqueCoverDemo() {}

    static final class Graph {
        final boolean[][] edge;

        Graph(int n) {
            if (n < 0 || n > 18) {
                throw new IllegalArgumentException("graph n must be 0..18");
            }
            edge = new boolean[n][n];
        }

        int n() {
            return edge.length;
        }

        void addEdge(int u, int v) {
            if (u < 0 || v < 0 || u >= n() || v >= n() || u == v) {
                throw new IllegalArgumentException("invalid edge");
            }
            edge[u][v] = edge[v][u] = true;
        }

        Graph complement() {
            Graph other = new Graph(n());
            for (int u = 0; u < n(); u++) {
                for (int v = u + 1; v < n(); v++) {
                    if (!edge[u][v]) other.addEdge(u, v);
                }
            }
            return other;
        }
    }

    // Literal = +i or -i, referring to 1-based Boolean variable i.
    // Return one satisfying assignment mask or -1 if UNSAT.
    static int findSatAssignment(int variables, int[][] clauses) {
        if (variables < 0 || variables > 18 || clauses == null) {
            throw new IllegalArgumentException("invalid SAT domain");
        }
        for (int[] clause : clauses) {
            if (clause == null) {
                throw new IllegalArgumentException("null clause");
            }
            for (int literal : clause) {
                if (literal == 0 || literal == Integer.MIN_VALUE
                        || Math.abs(literal) > variables) {
                    throw new IllegalArgumentException("invalid literal");
                }
            }
        }

        for (int assignment = 0; assignment < (1 << variables);
                assignment++) {
            boolean all = true;

            for (int[] clause : clauses) {
                boolean any = false;
                for (int literal : clause) {
                    int bit = Math.abs(literal) - 1;
                    boolean value = (assignment & (1 << bit)) != 0;
                    if (literal < 0) value = !value;
                    if (value) {
                        any = true;
                        break;
                    }
                }
                if (!any) {
                    all = false;
                    break;
                }
            }
            if (all) return assignment;
        }
        return -1;
    }

    // 3SAT -> CLIQUE: three vertices for each clause.
    static Graph from3Sat(int variables, int[][] clauses) {
        if (variables < 0 || variables > 18
                || clauses == null || clauses.length > 6) {
            throw new IllegalArgumentException("invalid 3SAT size");
        }

        for (int[] clause : clauses) {
            if (clause == null || clause.length != 3) {
                throw new IllegalArgumentException(
                    "each clause must contain 3 literal positions"
                );
            }
            for (int lit : clause) {
                if (lit == 0 || lit == Integer.MIN_VALUE
                        || Math.abs(lit) > variables) {
                    throw new IllegalArgumentException("invalid literal");
                }
            }
        }

        Graph g = new Graph(3 * clauses.length);
        for (int a = 0; a < clauses.length; a++) {
            for (int b = a + 1; b < clauses.length; b++) {
                for (int i = 0; i < 3; i++) {
                    for (int j = 0; j < 3; j++) {
                        if (clauses[a][i] != -clauses[b][j]) {
                            g.addEdge(3 * a + i, 3 * b + j);
                        }
                    }
                }
            }
        }
        return g;
    }

    // Exact maximum clique size by exhaustive vertex subsets.
    static int maxCliqueSize(Graph g) {
        int n = g.n(), best = 0;
        for (int mask = 0; mask < (1 << n); mask++) {
            int count = Integer.bitCount(mask);
            if (count <= best) continue;

            boolean valid = true;
            for (int u = 0; u < n && valid; u++) {
                if ((mask & (1 << u)) == 0) continue;
                for (int v = u + 1; v < n; v++) {
                    if ((mask & (1 << v)) != 0 && !g.edge[u][v]) {
                        valid = false;
                        break;
                    }
                }
            }
            if (valid) best = count;
        }
        return best;
    }

    // Exact minimum vertex cover size by exhaustive subsets.
    static int minVertexCoverSize(Graph g) {
        int n = g.n(), best = n;
        for (int mask = 0; mask < (1 << n); mask++) {
            if (Integer.bitCount(mask) >= best) continue;

            boolean valid = true;
            for (int u = 0; u < n && valid; u++) {
                for (int v = u + 1; v < n; v++) {
                    if (g.edge[u][v]
                            && (mask & (1 << u)) == 0
                            && (mask & (1 << v)) == 0) {
                        valid = false;
                        break;
                    }
                }
            }
            if (valid) best = Integer.bitCount(mask);
        }
        return best;
    }

    private static void checkCoverInput(int universeSize, int[] sets) {
        if (universeSize < 0 || universeSize > 18
                || sets == null || sets.length > 18) {
            throw new IllegalArgumentException("invalid cover size");
        }
        int full = (1 << universeSize) - 1;
        for (int set : sets) {
            if (set < 0 || (set & ~full) != 0) {
                throw new IllegalArgumentException("set outside universe");
            }
        }
    }

    // Exact Set Cover optimum, -1 if no covering family exists.
    static int minSetCoverSize(int universeSize, int[] sets) {
        checkCoverInput(universeSize, sets);
        int full = (1 << universeSize) - 1;
        int best = sets.length + 1;

        for (int selection = 0; selection < (1 << sets.length);
                selection++) {
            int chosen = Integer.bitCount(selection);
            if (chosen >= best) continue;

            int covered = 0;
            for (int i = 0; i < sets.length; i++) {
                if ((selection & (1 << i)) != 0) {
                    covered |= sets[i];
                }
            }
            if (covered == full) best = chosen;
        }
        return best == sets.length + 1 ? -1 : best;
    }

    // Independent Set Cover oracle: DP on the COVERED universe mask.
    static int minSetCoverDp(int universeSize, int[] sets) {
        checkCoverInput(universeSize, sets);
        int full = (1 << universeSize) - 1;
        int infinity = sets.length + 1;
        int[] dp = new int[1 << universeSize];
        Arrays.fill(dp, infinity);
        dp[0] = 0;

        for (int set : sets) {
            int[] next = dp.clone();
            for (int covered = 0; covered <= full; covered++) {
                if (dp[covered] == infinity) continue;
                int combined = covered | set;
                next[combined] = Math.min(
                    next[combined], dp[covered] + 1
                );
            }
            dp = next;
        }
        return dp[full] == infinity ? -1 : dp[full];
    }

    // Greedy picks the set covering most currently uncovered items.
    static int greedySetCoverSize(int universeSize, int[] sets) {
        checkCoverInput(universeSize, sets);
        int full = (1 << universeSize) - 1;
        int covered = 0, chosen = 0;

        while (covered != full) {
            int best = -1, maxGain = 0;
            for (int i = 0; i < sets.length; i++) {
                int gain = Integer.bitCount(
                    sets[i] & (full & ~covered)
                );
                if (gain > maxGain) {
                    maxGain = gain;
                    best = i;
                }
            }
            if (best < 0) return -1;
            covered |= sets[best];
            chosen++;
        }
        return chosen;
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        int[][] yes = {
            {1, 2, 3},
            {-1, 2, -3},
            {1, -2, 3}
        };
        int[][] no = {
            {1, 1, 1},
            {-1, -1, -1}
        };

        System.out.println(
            "3SAT satisfiable: " +
            (findSatAssignment(3, yes) >= 0)
        );
        System.out.println(
            "3SAT-to-Clique k=3: " +
            (maxCliqueSize(from3Sat(3, yes)) >= 3)
        );
        System.out.println(
            "UNSAT satisfiable: " +
            (findSatAssignment(1, no) >= 0)
        );
        System.out.println(
            "UNSAT-to-Clique k=2: " +
            (maxCliqueSize(from3Sat(1, no)) >= 2)
        );

        Graph g = new Graph(4);
        g.addEdge(0, 1);
        g.addEdge(1, 2);
        g.addEdge(2, 3);
        g.addEdge(3, 0);
        g.addEdge(0, 2);

        System.out.println("Graph max clique: " + maxCliqueSize(g));
        System.out.println(
            "Graph min vertex cover: " +
            minVertexCoverSize(g)
        );
        System.out.println(
            "Complement min VC: " +
            minVertexCoverSize(g.complement())
        );

        // Universe 1..6: A={1,2,3,4}, B={1,2,5},
        // C={3,4,6}. B + C cover all, while greedy takes 3.
        int[] sets = {0b001111, 0b010011, 0b101100};
        System.out.println(
            "Set cover optimum: " + minSetCoverSize(6, sets)
        );
        System.out.println(
            "Set cover greedy: " + greedySetCoverSize(6, sets)
        );

        Random rng = new Random(465L);

        for (int trial = 0; trial < 650; trial++) {
            int vars = 1 + rng.nextInt(5);
            int m = rng.nextInt(5);
            int[][] clauses = new int[m][3];

            for (int c = 0; c < m; c++) {
                for (int j = 0; j < 3; j++) {
                    int literal = 1 + rng.nextInt(vars);
                    clauses[c][j] = rng.nextBoolean()
                        ? literal : -literal;
                }
            }

            boolean sat = findSatAssignment(vars, clauses) >= 0;
            boolean clique = maxCliqueSize(
                from3Sat(vars, clauses)
            ) >= m;

            check(sat == clique,
                "3SAT reduction trial=" + trial);
        }

        for (int trial = 0; trial < 800; trial++) {
            int n = rng.nextInt(9);
            Graph randomGraph = new Graph(n);
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    if (rng.nextBoolean()) {
                        randomGraph.addEdge(u, v);
                    }
                }
            }

            Graph complement = randomGraph.complement();
            check(
                maxCliqueSize(randomGraph)
                    + minVertexCoverSize(complement) == n,
                "clique -> complement VC trial=" + trial
            );
            check(
                minVertexCoverSize(randomGraph)
                    + maxCliqueSize(complement) == n,
                "vertex cover <-> independent trial=" + trial
            );
        }

        for (int trial = 0; trial < 650; trial++) {
            int universe = rng.nextInt(9);
            int count = rng.nextInt(10);
            int full = 1 << universe;
            int[] candidateSets = new int[count];

            for (int i = 0; i < count; i++) {
                candidateSets[i] = rng.nextInt(full);
            }

            int optimum = minSetCoverSize(
                universe, candidateSets
            );
            int dpOptimum = minSetCoverDp(
                universe, candidateSets
            );
            int greedy = greedySetCoverSize(
                universe, candidateSets
            );
            check(optimum == dpOptimum,
                "SetCover DP trial=" + trial);
            check(
                optimum == -1
                    ? greedy == -1
                    : greedy >= optimum,
                "SetCover greedy trial=" + trial
            );
        }

        System.out.println(
            "3SAT-to-Clique tests: 650 PASS"
        );
        System.out.println(
            "Clique/complement-VC tests: 800 PASS"
        );
        System.out.println(
            "SetCover exact-vs-DP tests: 650 PASS"
        );
    }
}
```

### 12.1. Biên dịch và chạy

```bash
javac -encoding UTF-8 SatCliqueCoverDemo.java
java SatCliqueCoverDemo
```

**Đầu ra chuẩn:**

```text
3SAT satisfiable: true
3SAT-to-Clique k=3: true
UNSAT satisfiable: false
UNSAT-to-Clique k=2: false
Graph max clique: 3
Graph min vertex cover: 2
Complement min VC: 1
Set cover optimum: 2
Set cover greedy: 3
3SAT-to-Clique tests: 650 PASS
Clique/complement-VC tests: 800 PASS
SetCover exact-vs-DP tests: 650 PASS
```

### 12.2. Bảng đọc mã

| Thành phần | Chức năng | Điều kiện/giới hạn |
|---|---|---|
| `findSatAssignment` | Tìm một phép gán SAT, -1 nếu không có | Tối đa 18 biến; O(2^n × số literal) |
| `from3Sat` | Dựng 3m đỉnh từ m clause, nối literal tương thích của **hai clause khác nhau** | Đúng ba vị trí literal mỗi clause, tối đa 6 clause |
| `maxCliqueSize` | Duyệt mọi tập đỉnh để tìm clique lớn nhất | Tối đa 18 đỉnh |
| `minVertexCoverSize` | Duyệt mọi tập đỉnh phủ tất cả cạnh | Tối đa 18 đỉnh |
| `Graph.complement` | Bổ sung các cạnh không có giữa hai đỉnh khác nhau | Không sinh self-loop |
| `minSetCoverSize` | Duyệt mọi lựa chọn tập, trả số tập tối thiểu hoặc -1 | U và số tập ≤18 |
| `minSetCoverDp` | Oracle quy hoạch động theo phần tử đã được phủ | Đếm mỗi tập tối đa một lần |
| `greedySetCoverSize` | Chọn tập có gain mới lớn nhất cho đến khi đủ U | Không bảo đảm optimum |

### 12.3. Ý nghĩa các bộ kiểm thử

Mã thử **650** công thức 3CNF ngẫu nhiên với 0..4 clause, 1..5 biến; mỗi clause có ba vị trí literal có thể lặp. Nó so **kết quả SAT trực tiếp** với **CLIQUE(G,m)** trên đồ thị được dựng từ công thức. Trường hợp m=0 cũng được kiểm chứng theo quy ước clause rỗng trong phép AND.

Tiếp theo, **800** đồ thị ngẫu nhiên có 0..8 đỉnh được kiểm bằng hai đẳng thức:

- `maxClique(G)+minVertexCover(Ḡ)=n`.
- `minVertexCover(G)+maxClique(Ḡ)=n`.

Cuối cùng, **650** instance Set Cover có vũ trụ 0..8 phần tử và 0..9 tập con được so **brute force chọn tập** với **DP mask các phần tử đã phủ**. Nếu phủ được, greedy không được trả lời nhỏ hơn optimum; nếu không thể phủ, cả hai phải phát hiện không có nghiệm.

Các test này nhằm phát hiện lỗi xây cạnh, lấy đồ thị bù, dấu ngưỡng và mặt nạ bit. Kết quả ngẫu nhiên **không phải bằng chứng NP-complete**; chứng minh reduction ở mục 7–8 mới đảm nhiệm việc đó.

### 12.4. Mặt nạ bit và một số bẫy Java

Trong thuật toán SAT, bit số i−1 của `assignment` ứng với biến x_i. Một literal −i có giá trị TRUE khi bit ấy **bằng 0**. Khi varCount=0 và không có clause, phép gán rỗng là nghiệm nên trả 0, không phải -1.

Trong đồ thị, bit i của `mask` cho biết đỉnh i có được chọn; khi kiểm Clique phải kiểm **mọi cặp đỉnh khác nhau**, còn Vertex Cover phải kiểm **mọi cạnh có đầu mút được chọn**. Đây là hai điều kiện khác nhau và không thể tráo.

Trong Set Cover, bit j là phần tử j của U; OR các bitmask tập được chọn tạo mặt nạ `covered`. Chỉ khi `covered==full` mới bao phủ đầy đủ. Chương trình cho phép U=∅; khi đó chọn **0 tập** là tối ưu. Khi không thể phủ, trả -1 và **không** hiểu -1 là một kích thước nhỏ hơn ngưỡng k.

Để tránh tràn `1<<n`, chương trình giới hạn n≤18; mọi phép dịch bit trong khoảng an toàn cho int. Với bài lớn hơn, có thể dùng `BitSet`, nhưng chỉ đổi biểu diễn không làm bài toán NP-hard thành dễ.

## 13. Các chứng minh ngắn và lỗi quy giảm thường gặp

**Sai chiều quy giảm:** nếu tìm được A ≤p B và A đã NP-complete, điều này giúp chứng minh B NP-hard. Không kết luận A NP-hard chỉ vì B khó, cũng không kết luận B∈NP khi chưa đưa ra chứng chỉ có thể xác minh đa thức.

**Sai điều kiện trong Clique:** một đỉnh nối với nhiều đỉnh khác không đồng nghĩa cả nhóm là clique. Clique yêu cầu **mọi cặp**; bài tìm một đỉnh phủ nhiều đối tượng có thể là bài khác.

**Nhầm cạnh xung đột với tương thích:** nếu cạnh trong G là quan hệ xung đột, chọn một nhóm không xung đột là Independent Set, tương đương Clique trong Ḡ, chứ không phải Clique trong G.

**Sai ngưỡng complement:** Clique(G,k) tương đương Vertex Cover(Ḡ,n−k). Không được sử dụng n+k, k hay n−k trên G khi chưa chứng minh.

**Sai định nghĩa phủ:** Vertex Cover phủ **các cạnh bằng đỉnh**; Set Cover phủ **các phần tử của vũ trụ bằng tập con**. Trong phép giảm VC → SC, mỗi cạnh là phần tử vũ trụ và mỗi đỉnh tạo một tập gồm cạnh kề.

**Nhầm “at most k” với “exactly k”:** Clique thường hỏi ≥k; Vertex Cover/Set Cover thường hỏi ≤k. Với một clique lớn hơn k, có thể lấy bất kỳ k đỉnh để tạo clique k. Với phủ ≤k, không cần chọn thêm cho đủ k; phép biến đổi dùng đúng quan hệ ngưỡng, không ép nghiệm có đúng k phần tử nếu bài không yêu cầu.

**Greedy bị xem là exact:** Set Cover greedy có thể mất ba tập khi optimum chỉ hai tập. Nếu đề cần lời giải tối ưu đúng, phải dùng phương pháp exact hoặc chứng minh tính đúng riêng cho cấu trúc đặc biệt.

**Quá tin vào brute force:** một chương trình duyệt 2^n đúng với n nhỏ nhưng không thích hợp n=100. Phân tích độ phức tạp và chọn thuật toán theo giới hạn đầu vào.

## 14. Một số đề luyện nhận diện nhanh

1. Có 30 tính năng bật/tắt và các quy tắc “nếu A thì B”, “không chọn A cùng C”. **Gợi ý:** SAT; nếu mọi clause có tối đa hai literal, xem xét 2SAT.
2. Có đồ thị bạn bè, chọn ít nhất 10 người mà mọi cặp quen nhau. **Gợi ý:** Clique(G,10).
3. Có đồ thị xung đột lịch, giữ nhiều công việc nhất sao cho không cạnh xung đột nào nối hai việc được giữ. **Gợi ý:** Maximum Independent Set.
4. Vẫn đồ thị xung đột, hủy ít công việc nhất để không còn cặp xung đột. **Gợi ý:** Minimum Vertex Cover; số giữ tối đa = n−số hủy tối thiểu.
5. Có 12 yêu cầu, mỗi phần mềm giải quyết một tập yêu cầu, muốn dùng tối đa ba phần mềm phủ hết. **Gợi ý:** Set Cover(U,S,3).
6. Chọn mỗi nhiệm vụ đúng một người và mỗi người làm tối đa một nhiệm vụ. **Gợi ý:** matching/assignment; không tự chuyển ngay sang NP-complete nếu cấu trúc là ghép cặp hai phía.
7. Một công thức CNF chỉ có clause kích thước 2. **Gợi ý:** 2SAT, có thuật toán đa thức; không đánh đồng với 3SAT tổng quát.
8. Chọn nhóm nhân viên mà mỗi cặp **không** mâu thuẫn, cạnh là “không mâu thuẫn”. **Gợi ý:** Clique trên đồ thị tương thích.
9. Muốn mỗi ràng buộc được thỏa **đúng một lần**, không chấp nhận chồng lấn. **Gợi ý:** Exact Cover, khác Set Cover.
10. Hai mô hình cùng là NP-complete nhưng kích thước instance khác nhau. **Gợi ý:** chọn mô hình biểu diễn gọn và ràng buộc dễ lan truyền hơn; NP-completeness không so trực tiếp hằng số thực thi giữa solver.

## 15. Bài tập có đáp án

**Bài 1.** SAT hỏi gì? *Đáp án:* có một phép gán Boolean làm công thức đúng hay không.

**Bài 2.** Clique hỏi gì? *Đáp án:* có tập ít nhất k đỉnh mà mọi cặp đều có cạnh.

**Bài 3.** Set Cover quyết định hỏi gì? *Đáp án:* có thể chọn không quá k tập để phủ hết U.

**Bài 4.** Vertex Cover có phủ đỉnh hay phủ cạnh? *Đáp án:* chọn đỉnh để mỗi **cạnh** có đầu mút được chọn.

**Bài 5.** Tại sao Clique thuộc NP? *Đáp án:* chứng chỉ k đỉnh, kiểm mọi cặp trong O(k²).

**Bài 6.** NP có nghĩa là “không thể giải đa thức” không? *Đáp án:* không; nghĩa là có chứng chỉ kiểm đa thức.

**Bài 7.** Để chứng minh B NP-hard từ A NP-hard, cần chiều nào? *Đáp án:* A ≤p B.

**Bài 8.** 3SAT với m clause tạo bao nhiêu đỉnh ở reduction cổ điển? *Đáp án:* 3m.

**Bài 9.** Có cạnh giữa hai literal thuộc cùng clause trong reduction đó không? *Đáp án:* không.

**Bài 10.** Hai literal x và ¬x ở hai clause có cạnh không? *Đáp án:* không, vì mâu thuẫn.

**Bài 11.** Clique kích thước m trong đồ thị reduction nói gì? *Đáp án:* chọn được đúng một literal nhất quán từ mỗi clause, do đó công thức SAT.

**Bài 12.** Công thức (x∨x∨x)∧(¬x∨¬x∨¬x) thỏa không? *Đáp án:* không.

**Bài 13.** Đồ thị G có clique k thì đồ thị bù có vertex cover kích thước nào? *Đáp án:* n−k.

**Bài 14.** Independent Set kích thước k trong G tương đương phủ đỉnh bao nhiêu? *Đáp án:* có vertex cover kích thước n−k.

**Bài 15.** Nếu α(G)=7 và n=10, τ(G) bằng mấy? *Đáp án:* 3.

**Bài 16.** Clique maximal có nhất thiết maximum không? *Đáp án:* không.

**Bài 17.** Trong Set Cover ví dụ U={1..6}, B∪C phủ được U với mấy tập? *Đáp án:* hai tập.

**Bài 18.** Greedy ở ví dụ đó chọn A trước rồi cần bao nhiêu tập? *Đáp án:* ba tập.

**Bài 19.** Đổi Vertex Cover sang Set Cover, U gồm gì? *Đáp án:* các cạnh của đồ thị.

**Bài 20.** Một tập ứng với đỉnh v chứa gì? *Đáp án:* những cạnh kề v.

**Bài 21.** Một universe rỗng có min Set Cover bằng bao nhiêu? *Đáp án:* 0.

**Bài 22.** Khi tất cả tập hợp lại vẫn không phủ đủ U, trả lời quyết định Set Cover(U,S,k) là gì? *Đáp án:* NO với mọi k hợp lệ.

**Bài 23.** 2SAT và 3SAT tổng quát khác nhau ở độ khó nào? *Đáp án:* 2SAT thuộc P, 3SAT NP-complete.

**Bài 24.** Maximum Clique là dạng tối ưu hay quyết định? *Đáp án:* tối ưu; CLIQUE(G,k) là quyết định.

**Bài 25.** Thuật toán tham lam Set Cover có bảo đảm optimum không? *Đáp án:* không; có xấp xỉ logarithmic tổng quát.

**Bài 26.** Nếu cạnh biểu thị xung đột, chọn nhóm không xung đột là gì? *Đáp án:* Independent Set trên đồ thị đó.

**Bài 27.** Tại sao không ghép các đỉnh trong cùng clause khi giảm 3SAT sang Clique? *Đáp án:* để clique m đỉnh phải lấy một đỉnh từ mỗi clause.

**Bài 28.** Có thể suy ra SAT vô nghiệm chỉ vì chương trình greedy không tìm được Set Cover? *Đáp án:* không; cần reduction đúng và thuật toán giải đúng điều kiện quyết định.

## 16. Checklist nhận diện và kiểm chứng

1. Đề hỏi **quyết định**, tìm một nghiệm, đếm hay tối ưu?
2. Đối tượng chọn là biến Boolean, đỉnh, cạnh hay tập con?
3. Quan hệ cạnh nghĩa là tương thích hay xung đột?
4. Yêu cầu là “mọi cặp”, “không cặp nào”, “mọi cạnh”, hay “mọi phần tử”?
5. Bất đẳng thức ngưỡng là ≥k hay ≤k?
6. Đã phân biệt Clique, Independent Set, Vertex Cover và Set Cover?
7. CNF có clause dài tối đa 2 hay chứa clause dài 3?
8. Nếu quy giảm 3SAT→Clique, có đúng 3m đỉnh và chỉ nối literal **khác clause, không đối nhau**?
9. Nếu quy giảm Clique→VC, đã dùng **đồ thị bù** và ngưỡng n−k?
10. Nếu quy giảm VC→SC, vũ trụ là **tập cạnh** và mỗi tập là cạnh kề một đỉnh?
11. Đã chứng minh cả hai chiều YES⇔YES, không chỉ một chiều?
12. Đã kiểm tra chứng chỉ đa thức khi khẳng định một bài thuộc NP?
13. Dạng tối ưu đã được gọi NP-hard thay vì gán nhãn NP-complete sai ngữ cảnh?
14. Có xử lý vũ trụ rỗng, clause rỗng, nhiều giá trị lặp và cấu hình bất khả thi?
15. Có phân biệt greedy/heuristic với thuật toán exact?
16. Có xét giới hạn n,k, cấu trúc đặc biệt và tài nguyên trước khi chọn solver?
17. Nếu dùng brute bitmask Java, đã giới hạn kích thước bit và diễn giải -1 đúng?
18. Đã đối chiếu một oracle độc lập trên input nhỏ và kiểm các ví dụ phản chứng?

## Kết luận

**SAT** biểu diễn ràng buộc logic Boolean; **Clique** biểu diễn nhóm mà **mọi cặp** tương thích; **Independent Set** biểu diễn nhóm không có cạnh xung đột; **Vertex Cover** chọn ít đỉnh để chạm mọi cạnh; **Set Cover** chọn ít tập để phủ mọi yêu cầu.

Dãy quy giảm **3SAT → Clique → Vertex Cover trên đồ thị bù → Set Cover** là minh họa chuẩn cho cách chứng minh NP-hard. Quy giảm phải được xây đa thức và bảo toàn **cả hai chiều** tính thỏa mãn; việc nhận diện đúng mô hình không thay thế kiểm tính đúng của ánh xạ.

Đối với instance nhỏ, các bộ giải brute force và DP là oracle tốt. Đối với instance thực tế, dùng SAT solver, branch-and-bound, thuật toán tham số hóa hoặc xấp xỉ tùy mục tiêu. Mục đích của nhận diện mô hình là **chọn được ngôn ngữ toán học và công cụ giải phù hợp**, không phải kết luận mọi instance của bài toán NP-complete đều không thể xử lý.
