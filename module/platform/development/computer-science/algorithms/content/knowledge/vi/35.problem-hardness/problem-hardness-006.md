# P, NP, NP-hard và NP-complete ở mức lựa chọn lời giải

**Độ khó tính toán** (*computational complexity*) giúp trả lời một câu hỏi rất thực tế khi giải thuật: **với kích thước và cấu trúc dữ liệu đã cho, nên tìm thuật toán đa thức, quy hoạch động, tìm kiếm chính xác theo hàm mũ, xấp xỉ hay heuristic?** Không thể trả lời câu hỏi này chỉ bằng cách nhìn một bài toán có vẻ “khó”. Ta cần phân biệt *bài toán quyết định* với *bài toán tối ưu*, biết thế nào là có **thuật toán đa thức**, thế nào là **kiểm chứng lời giải trong thời gian đa thức**, và hiểu ý nghĩa chính xác của các lớp **P, NP, NP-hard, NP-complete**.

Bài thuộc nhóm **Độ khó bài toán** trong **Computer Science Algorithms**, với đề bài **P, NP, NP-hard và NP-complete ở mức lựa chọn lời giải**. Trọng tâm là **dùng kiến thức độ phức tạp để chọn hướng giải phù hợp**, không chỉ thuộc một danh sách định nghĩa. Các khái niệm được giải thích trên bài toán quyết định, sau đó liên hệ lại những yêu cầu quen thuộc như tối ưu đường đi, lập lịch, chọn tập con hoặc tìm một cấu hình tốt nhất.

**Thông điệp quan trọng:** `P⊆NP`, còn việc **`P=NP?`** là một bài toán mở; **không ai đã chứng minh `P≠NP`**. Một bài toán NP-complete không có nghĩa “đã chứng minh không thể giải đa thức” mà có nghĩa: **nếu có thuật toán đa thức cho một bài toán NP-complete bất kỳ thì mọi bài toán trong NP cũng có thuật toán đa thức**. Đây là lý do người làm thuật toán không nên tùy tiện cam kết một lời giải chính xác, đa thức, chạy nhanh cho **mọi** input lớn của một bài toán NP-complete tổng quát.

Mục tiêu sau bài: hiểu và dùng đúng bốn thuật ngữ; không nhầm giảm đa thức với thuật toán tìm nghiệm; biết đọc chiều giảm `A≤ₚB`; phân biệt DP **giả đa thức** và đa thức theo **độ dài mã hóa đầu vào**; biết xây chiến lược theo `n`, giới hạn số, cấu trúc đặc biệt, yêu cầu chính xác và ngân sách thời gian; có thể giải thích vì sao một bài NP-complete vẫn có thể giải nhanh khi **tham số nhỏ**, **giá trị mục tiêu nhỏ** hoặc **dữ liệu thực tế dễ**.

## 1. Trước hết: “bài toán” và “một input” là hai chuyện khác nhau

Một **bài toán tính toán** là một họ vô hạn các trường hợp đầu vào (*instances*). Ví dụ:

- **SUBSET SUM (quyết định):** cho các số nguyên không âm `a₁,...,aₙ` và mục tiêu `T`, có tồn tại một tập chỉ số sao cho tổng các số được chọn bằng T không?
- **SAT:** cho công thức Boolean, có tồn tại phép gán true/false làm toàn bộ công thức đúng không?
- **CLIQUE:** cho đồ thị G và số k, có tồn tại k đỉnh mà mọi cặp trong đó có cạnh nối không?
- **TSP quyết định:** cho đồ thị/trọng số và ngưỡng L, có một chu trình Hamilton với tổng chi phí ≤L không?

Cùng một bài toán có thể có **input nhỏ và rất dễ**, hoặc input lớn và khó. Ví dụ SUBSET SUM với `a=[3,5,8],T=8` có đáp án YES ngay; nhưng trên một họ input khác, việc tìm một tập con đúng mục tiêu có thể đòi hỏi tìm kiếm phức tạp.

**NP-complete là tính chất của bài toán tổng quát**, không phải một nhãn “input cụ thể này chắc chắn tốn rất nhiều thời gian”. Một trường hợp bất kỳ có thể có giải pháp tức thì, còn phát biểu NP-complete nói về khả năng giải **mọi trường hợp** của bài toán theo tiêu chuẩn độ phức tạp.

### Kích thước đầu vào phải là số bit của cách mã hóa

Nếu bài toán có một số nguyên T, cách lưu thông thường dưới dạng nhị phân cần **`Θ(log₂(T+1))` bit**, không phải T ký tự.

Ví dụ T=1.000.000.000 chỉ cần khoảng 30 bit, không cần một tỷ phần bộ nhớ tỷ lệ với một tỷ. Vì vậy một thuật toán `O(nT)` có thể cực nhanh khi T=100 nhưng cực chậm khi T=10⁹, dù độ dài nhị phân của T chỉ tăng từ khoảng 7 lên 30 bit.

Khi nói **“thuật toán đa thức”**, điều được hiểu là đa thức theo **độ dài mô tả input tính bằng bit** (hoặc kích thước mã hóa tương đương hợp lý), chứ không phải đa thức theo **giá trị số của một tham số được viết bằng nhị phân**.

### Mô hình tính toán và cách mã hóa

Trong lý thuyết chuẩn, các lớp P/NP được xác định trên các **ngôn ngữ quyết định** và phép tính có độ phức tạp theo chiều dài chuỗi input. Có thể dùng máy Turing xác định/không xác định như một định nghĩa hình thức. Trong lập trình, ta thường nói gọn “đa thức theo n”, nhưng phải biết n đang là số đỉnh, số chữ số, độ dài chuỗi hay số bit của tất cả số nguyên.

Không được tận dụng việc **thay biểu diễn nhị phân bằng unary** để gọi một thuật toán giả đa thức thành đa thức cho bài toán nguyên bản. Biểu diễn unary có thể làm độ dài input tăng rất lớn; đó là một **mô hình đầu vào khác**.

## 2. Bài toán quyết định, tìm kiếm và tối ưu

**Bài toán quyết định (decision problem)** có đầu ra **YES hoặc NO**.

Ví dụ SUBSET SUM:

~~~text
Input:
numbers = [3, 34, 4, 12, 5, 2]
target = 9

Question:
Is there a subset whose sum is exactly 9?

Output:
YES   // one witness: {4, 5}
~~~

**Bài toán tìm kiếm (search problem)** yêu cầu **xuất một lời giải thỏa điều kiện** nếu có. Với ví dụ trên, cần trả chỉ số của hai phần tử 4 và 5, không chỉ YES.

**Bài toán tối ưu (optimization problem)** yêu cầu giá trị/lời giải **tốt nhất**, ví dụ:
- Tìm chu trình du lịch có tổng độ dài **nhỏ nhất** (TSP tối ưu).
- Chọn các đồ vật trong giới hạn trọng lượng để có **tổng lợi ích lớn nhất** (0/1 knapsack tối ưu).
- Tìm tập đỉnh phủ mọi cạnh có **kích thước nhỏ nhất** (minimum vertex cover).
- Tìm tập con có tổng không vượt T nhưng **gần T nhất**.

Các lớp P, NP và định nghĩa NP-complete **về hình thức áp dụng trực tiếp cho bài toán quyết định**. Khi nói “TSP tối ưu là NP-hard”, ta đang nói về **độ khó của bài tối ưu**, không phải tự động gọi phiên bản tối ưu là “NP-complete” mà không chuyển sang dạng YES/NO.

### Chuyển tối ưu sang quyết định bằng ngưỡng

Nếu có thuật toán tìm chính xác giá trị tối ưu của TSP, ta có thể trả lời bài quyết định “có tour dài ≤L không?” chỉ bằng cách so tối ưu với L. Điều này giải thích tại sao phiên bản tối ưu **ít nhất không dễ hơn** phiên bản quyết định theo một nghĩa reduction phù hợp.

Tương tự, nếu có thuật toán tìm **maximum clique** trong đa thức, có thể kiểm clique kích thước ≥k bằng cách so kích thước tối ưu với k.

Ngược lại, đi từ **oracle quyết định** sang việc **khôi phục lời giải tối ưu** thường cần thêm ý tưởng, số lần gọi hoặc điều kiện miền giá trị; không mặc định rằng bản YES/NO và bản tối ưu là *cùng một API*.

## 3. Lớp P: có thuật toán quyết định đa thức

**P (Polynomial time)** là tập các bài toán quyết định mà một **máy tính xác định** có thể giải cho **mọi input** trong thời gian bị chặn trên bởi một đa thức của độ dài input.

Ví dụ thường gặp:

- Một đường đi từ s tới t có tồn tại trong đồ thị hay không? Dùng BFS/DFS `O(V+E)`.
- Đồ thị có chu trình hay không? Dùng DFS/DSU tùy loại đồ thị.
- Có đường đi s→t với số cạnh ≤k trong đồ thị không trọng số? Tính khoảng cách BFS và so k.
- Kiểm một số nguyên có phải số nguyên tố? Có thuật toán xác định đa thức theo **số bit**.
- Quyết định có một luồng s→t giá trị ít nhất K trong mạng dung lượng nguyên không âm? Có thuật toán maximum flow đa thức.

Đây là các **bài toán quyết định** có thuật toán đã biết, không có nghĩa bất kỳ biến thể nào tên nghe gần giống đều ở P.

Ví dụ:
- “Có đường đi từ s tới t?” ở P.
- “Có đường đi **đơn** từ s tới t qua **tất cả đỉnh**?” liên quan Hamiltonian path, NP-complete trong mô hình tổng quát.
- “Tìm đường đi ngắn nhất” với trọng số phù hợp có thuật toán đa thức; “Tìm đường đi đơn dài nhất” có thể NP-hard.

**Chỉ thêm một điều kiện trong yêu cầu có thể đổi lớp độ khó.**

### P không có nghĩa lúc nào cũng chạy nhanh trong thực tế

Đa thức `O(n¹⁰)` không được xem là thực dụng với n=10⁵. Một thuật toán `O(2^{n/2})` lại có thể thực dụng khi n≤40. P/NP là cách phân loại **khả năng tiệm cận** trên input tổng quát, còn khi chọn lời giải phải xem **hệ số, bộ nhớ, hằng số, phân bố input và thời gian cho phép**.

## 4. Lớp NP: một đáp án YES có chứng nhận kiểm nhanh

**NP (Nondeterministic Polynomial time)** có định nghĩa phổ biến qua **chứng nhận** (*certificate/witness*):

Một bài toán quyết định thuộc NP nếu, với mọi input có đáp án **YES**, tồn tại một chuỗi chứng nhận có **độ dài đa thức theo độ dài input** để một thuật toán xác định có thể **kiểm tra đúng/sai trong thời gian đa thức**.

Quan trọng:
- **NP không viết tắt của “Non-Polynomial”.**
- NP **không có nghĩa** mọi input đều khó hoặc không thể giải nhanh.
- NP **không đòi** có thuật toán đa thức để **tìm chứng nhận**.
- Chứng nhận chỉ cần tồn tại cho trường hợp **YES** và kiểm được nhanh.
- Với input NO, người kiểm không thể chấp nhận một chứng nhận giả; định nghĩa NP không tự bảo đảm có **chứng nhận NO** dễ kiểm trong mọi bài.

### Ví dụ: chứng nhận cho CLIQUE

Cho G và k, một chứng nhận YES là **danh sách k đỉnh**. Kiểm:
1. Đủ k đỉnh phân biệt và đều thuộc G.
2. Với mọi cặp đỉnh được chọn, có cạnh nối trong G.

Có O(k²) cặp cần kiểm nếu có cấu trúc tra cạnh phù hợp. Việc **kiểm chứng** một clique được cung cấp là đa thức. Nhưng việc **tìm** clique kích thước k trong một đồ thị tùy ý là bài toán khó hơn.

### Ví dụ: chứng nhận cho SUBSET SUM

Cho `a₁,...,aₙ,T`, chứng nhận là một **bitmask n bit** hoặc tập chỉ số được chọn. Kiểm:
- Chỉ số hợp lệ, không lặp nếu dùng danh sách.
- Tính tổng các giá trị đã chọn bằng số học đủ chính xác.
- So sánh tổng với T.

Số phép cộng ≤n, mỗi số có số bit phụ thuộc input nên quá trình kiểm vẫn đa thức theo độ dài input.

### Ví dụ: SAT

Chứng nhận là phép gán true/false cho các biến. Duyệt công thức và đánh giá mỗi mệnh đề để xác nhận toàn bộ đúng. Tìm ra phép gán có thể khó, nhưng **kiểm tra phép gán đưa sẵn** thì nhanh.

### Vì sao P⊆NP?

Nếu một bài toán đã có thuật toán quyết định đa thức, người kiểm có thể **tự chạy thuật toán ấy** và không cần dùng chứng nhận nào. Vì vậy mọi bài trong P cũng thuộc NP:

**`P⊆NP`**.

Việc bao hàm này có nghiêm ngặt hay không, tức **`P≠NP`**, hiện **chưa được chứng minh**. Không được viết “P là các bài dễ, NP là các bài khó” như hai tập không giao nhau.

## 5. NP-hard: khó ít nhất bằng mọi bài trong NP

**NP-hard** là một tính chất được xác định qua **phép giảm** (*reduction*).

Nói một bài toán quyết định B là NP-hard theo **giảm many-one đa thức**, tức với **mọi bài A∈NP**, có một hàm tính được trong thời gian đa thức `f` biến input x của A thành input f(x) của B sao cho:

**`x∈A ⇔ f(x)∈B`**.

Viết gọn:

**`A≤ₚB`**.

Ý nghĩa: nếu B giải được nhanh, thì A cũng giải được nhanh bằng cách:
1. Tính f(x) trong thời gian đa thức.
2. Gọi thuật toán giải B trên f(x).
3. Trả YES/NO tương ứng.

Vì vậy **B ít nhất khó bằng A** theo kiểu phép giảm đã chỉ định.

### NP-hard không bắt buộc thuộc NP

Một bài NP-hard có thể:
- Thuộc NP, nếu bài quyết định có witness YES kiểm nhanh.
- **Không** thuộc NP, hoặc thậm chí là bài toán không quyết định được, tùy định nghĩa và loại reduction được xét.

Do đó, từ **“B NP-hard” không thể suy ngay “B NP-complete”**. Muốn kết luận NP-complete, bắt buộc chứng minh thêm **B∈NP**.

Các bài **tối ưu** thường được gọi NP-hard vì nếu giải chính xác bài tối ưu, ta có thể trả lời một bài quyết định NP-hard liên quan. Điều này **không tự biến** bài tối ưu thành một bài toán quyết định thuộc NP.

### Hướng mũi tên reduction rất dễ nhầm

Để chứng minh bài mới B **NP-hard**, ta chọn **một bài A đã biết NP-hard/NP-complete** và xây:

**`A≤ₚB`**, không phải `B≤ₚA`.

Nếu chỉ có `B≤ₚA` với A là NP-complete, ta mới chứng minh B **không khó hơn** A theo kiểu giảm này; điều đó **không chứng minh B NP-hard**.

Ví dụ muốn chứng minh CLIQUE khó, ta giảm một bài đã biết khó như **3-SAT tới CLIQUE**. Không dùng một reduction CLIQUE→3-SAT để kết luận CLIQUE là NP-hard.

## 6. NP-complete: vừa thuộc NP, vừa NP-hard

Một bài toán quyết định B là **NP-complete** khi **đồng thời**:

1. **`B∈NP`**: có witness YES dài đa thức và thuật toán kiểm chứng đa thức.
2. **`B NP-hard`**: mọi bài thuộc NP có thể giảm nhiều-một đa thức về B.

Viết:

**`NP-complete = NP ∩ NP-hard`**,

khi hai thuật ngữ được hiểu trên cùng mô hình bài toán quyết định và reduction tiêu chuẩn.

Các ví dụ kinh điển:
- **SAT**, **3-SAT** (trên công thức Boolean dạng phù hợp).
- **CLIQUE** dạng quyết định “có clique kích thước ≥k?”.
- **VERTEX COVER** dạng quyết định “có tập phủ đỉnh ≤k?”.
- **HAMILTONIAN CYCLE** trong đồ thị tổng quát.
- **SUBSET SUM** với các số nguyên được mã hóa nhị phân.
- **0/1 KNAPSACK quyết định** với ràng buộc trọng lượng và ngưỡng giá trị.
- **TSP quyết định** với định nghĩa đồ thị/chi phí/ngưỡng phù hợp.

### Kết luận điều kiện quan trọng

Nếu **một** bài NP-complete có thuật toán đa thức cho **mọi input**, thì mọi bài A∈NP giảm về nó và cũng có thuật toán đa thức. Khi ấy **`P=NP`**.

Ngược lại, nếu **`P≠NP`** (một giả thuyết được tin rộng rãi nhưng **chưa được chứng minh**), thì không bài NP-complete nào thuộc P.

**Không** khẳng định “NP-complete đã được chứng minh không có thuật toán đa thức”. Đây là một lỗi kiến thức nghiêm trọng. Phát biểu đúng: **chưa biết thuật toán đa thức tổng quát cho các bài NP-complete; có thuật toán như vậy sẽ giải quyết P vs NP**.

### Bảng phân biệt bốn nhãn

| Nhãn | Ý nghĩa chuẩn | Điều được phép kết luận |
|---|---|---|
| **P** | Có thuật toán quyết định đa thức | Thuộc NP; có thể chọn lời giải đa thức |
| **NP** | YES có witness kiểm đa thức | Không có nghĩa bài không nằm trong P |
| **NP-hard** | Mọi bài NP giảm đa thức về nó | Không bắt buộc là bài quyết định hay thuộc NP |
| **NP-complete** | Vừa thuộc NP vừa NP-hard | Bài quyết định “khó nhất” trong NP theo reduction; chưa biết lời giải đa thức tổng quát |

Một sơ đồ tư duy đúng:

~~~text
                 Decision problems
                        |
           +------------+------------+
           |                         |
          P subset NP             NP-hard
           |                         |
           +---- NP-complete --------+
                = NP ∩ NP-hard

Not established: whether P = NP.
NP-hard is NOT required to be inside NP.
Optimization problems are discussed separately.
~~~

Hình trên mang tính minh họa quan hệ logic; không vẽ P và NP-complete như hai vùng **được chứng minh không giao nhau**, vì điều ấy tương đương giải quyết một phần câu hỏi P vs NP.

## 7. Giảm đa thức thật sự gồm những gì?

Muốn chứng minh `A≤ₚB`, cần đủ ba điều:

1. **Dựng được phép biến đổi f(x)** trong thời gian đa thức theo độ dài x.
2. **Bảo toàn đáp án YES và NO:** x là YES của A **khi và chỉ khi** f(x) là YES của B.
3. **Kích thước output của f** không phình lên siêu đa thức; điều này thường theo ngay thời gian dựng f vì không thể in nhiều hơn thời gian đã chạy.

Không đủ nếu chỉ nói “hai bài trông giống nhau”, “có thể thử hết”, hay “đổi tên biến” mà không chỉ cách dựng input B. Cũng không đủ nếu chỉ chứng minh một chiều YES→YES, nhưng có input NO của A lại thành YES của B.

### Quy trình chuẩn chứng minh một bài B NP-complete

- **Bước A — Chứng minh B∈NP:** mô tả witness YES và thuật toán kiểm nhanh.
- **Bước B — Chọn A đã biết NP-complete:** chẳng hạn 3-SAT, CLIQUE, VERTEX COVER.
- **Bước C — Xây A≤ₚB:** cho mỗi input của A tạo một input của B bằng thuật toán đa thức.
- **Bước D — Chứng minh tương đương:** A YES ⇔ B YES.
- **Bước E — Kiểm độ phức tạp tạo input:** thời gian và độ dài output đa thức.

Khi xong mới được kết luận B NP-complete. Chỉ tìm một thuật toán quay lui rất chậm cho B **không phải bằng chứng** B NP-hard: có thể tồn tại thuật toán khác đa thức mà ta chưa biết.

## 8. Ví dụ reduction: 3-SAT ≤ₚ CLIQUE

Đây là ví dụ điển hình giúp hiểu **hướng giảm và cách bảo toàn YES/NO**.

### Đầu vào 3-SAT

Một công thức dạng hội các mệnh đề:

**`F=C₁∧C₂∧...∧Cₘ`**,

mỗi mệnh đề Cᵢ là tuyển của **không quá hoặc đúng ba literal** theo một quy ước 3-CNF thích hợp. Literal là biến x hoặc phủ định ¬x.

Ví dụ:

**`F=(x∨y∨¬z)∧(¬x∨z∨y)∧(x∨¬y∨z)`**.

Câu hỏi: có phép gán biến sao cho **mỗi mệnh đề** có ít nhất một literal true?

### Xây đồ thị cho CLIQUE

- Với **mỗi lần xuất hiện của một literal trong một clause**, tạo một đỉnh mang cặp (clause, literal). Hai literal giống nhau ở hai clause vẫn là **hai đỉnh khác nhau**.
- Nối hai đỉnh bằng cạnh nếu chúng đến từ **hai clause khác nhau** và **không mâu thuẫn**: literal tại đỉnh này không phải phủ định trực tiếp của literal tại đỉnh kia.
- Đặt ngưỡng clique **`k=m`**, số clause.

Cách dựng có O(m) hoặc O(3m) đỉnh nếu mỗi clause có tối đa ba literal; xét mọi cặp đỉnh cần tối đa O(m²) phép so sánh, nên là **đa thức**.

### Chứng minh nếu F thỏa được thì có clique m đỉnh

Nếu F có phép gán thỏa, với mỗi clause Cᵢ chọn một literal nhận true. Những literal đã chọn không thể gồm đồng thời x và ¬x vì cùng một phép gán không thể làm cả hai true. Chúng đến từ các clause khác nhau, nên mọi cặp đỉnh được nối cạnh. Chúng tạo thành một **clique kích thước m**.

### Chứng minh nếu có clique m đỉnh thì F thỏa được

Vì không có cạnh giữa hai đỉnh cùng clause, một clique kích thước m chứa **tối đa một đỉnh từ mỗi clause**; với m clause, nó phải chứa **đúng một đỉnh từ mỗi clause**. Mọi cặp được nối cạnh nên không có hai literal đã chọn mâu thuẫn nhau. Ta có thể gán các biến sao cho tất cả literal được chọn đều true, và gán tùy ý những biến còn lại. Mỗi clause có một literal true, nên F thỏa được.

Vậy:

**`F satisfiable ⇔ graph has a clique of size m`**,

và phép dựng đa thức. Kết hợp với `CLIQUE∈NP`, cùng nguồn 3-SAT đã biết NP-complete, ta suy **CLIQUE NP-complete**.

### Phần dễ nhầm

Reduction **không** chỉ tạo một đỉnh cho mỗi biến: phải dùng **literal occurrence per clause** để bảo đảm clique kích thước m chọn được một chứng nhận cho **mỗi clause**.

Một clique m đỉnh ở đồ thị dựng không cần đi qua mọi literal; nó chọn **đúng một đại diện tương thích** từ mỗi clause. Hai literal x và ¬x không được nối cạnh dù xuất hiện ở hai clause khác nhau.

Một mô hình kiểm thử logic độc lập có thể tạo công thức 3-CNF nhỏ, duyệt mọi phép gán rồi so với việc tồn tại clique ở đồ thị dựng. Trên **1.600 công thức nhỏ ngẫu nhiên**, cách dựng ở trên đã cho kết quả SAT và CLIQUE tương đương.

## 9. Từ nhãn độ khó sang chiến lược giải bài

Biết “NP-complete” là **điểm bắt đầu của chiến lược**, không phải lý do bỏ cuộc. Hãy hỏi tuần tự:

1. Đề yêu cầu **YES/NO**, **một witness**, **giá trị tối ưu**, hay **nghiệm gần đúng**?
2. Giới hạn thật của **n**, số bit trọng số/giá trị, số cạnh, số biến, cấu trúc đồ thị, số chiều, số thao tác truy vấn là bao nhiêu?
3. Có **trường hợp đặc biệt** đã biết đa thức không? Ví dụ đồ thị là cây/DAG, kích thước phía nhỏ, các số nhỏ, hoặc ràng buộc sắp thứ tự.
4. Cần **đúng tuyệt đối** với mọi input hay được phép **xấp xỉ/heuristic**?
5. Có thể cho phép **thời gian hàm mũ theo tham số nhỏ k** không?
6. Có **ngân sách thời gian/nhớ**, điểm dừng và cách báo UNKNOWN nếu chưa giải được không?
7. Có thể chứng minh cận dưới/cận trên, tính khả thi của output, hoặc dùng solver đáng tin (SAT/ILP/CP-SAT) không?

Từ câu trả lời, chọn phương án. Không dựa duy nhất vào “O(2^n) nghe lớn” hay “O(nT) trông đa thức”.

### Hướng 1: thuật toán đa thức chuyên biệt

Nếu input là một họ đặc biệt, bài NP-hard tổng quát có thể trở thành dễ hơn. Ví dụ nhiều bài tối ưu đồ thị khó trên đồ thị tổng quát có lời giải DP theo cây khi input là **cây**, hoặc DP theo **treewidth** nếu độ rộng nhỏ và có decomposition phù hợp.

Điều quan trọng là phải chứng minh điều kiện đặc biệt **thật sự luôn được thỏa** trong đề. Không thể nhận một graph bất kỳ rồi mặc định nó là DAG để dùng thuật toán đường đi dài nhất trên DAG.

### Hướng 2: vét cạn có cắt tỉa/nhánh cận

Với n nhỏ, thử tất cả tập con `2^n` hoặc hoán vị `n!` có thể đủ. Có thể thêm:
- **Backtracking** và ràng buộc cắt nhánh.
- **Branch-and-bound** với cận tối ưu hiện tại.
- Bitmask và tiền xử lý.
- Thứ tự xét biến giúp sớm tìm nghiệm/cắt nhánh tốt.

Cận xấu nhất có thể vẫn hàm mũ, nhưng nhiều trường hợp thực tế chạy nhanh. Nói “solver này hay nhanh trong benchmark” không tương đương “đã có thuật toán đa thức cho bài NP-complete”.

### Hướng 3: meet-in-the-middle

Chia n phần tử thành hai nửa, liệt kê tổng tập con của từng nửa. Số tổng ở mỗi phía khoảng **`2^{n/2}`** thay vì 2^n. Sau khi sort một phía, tìm cặp tổng có target bằng binary search.

Với n≈40, khoảng 2²⁰≈1,05 triệu tổng mỗi nửa thường có thể quản lý trong bộ nhớ cho một bài minh họa; 2^40≈1,10 nghìn tỷ tập con sẽ khó vét cạn trực tiếp.

Meet-in-the-middle vẫn **hàm mũ theo n**, không mâu thuẫn với NP-complete. Nó chỉ hạ bậc mũ từ n xuống n/2 và đánh đổi bộ nhớ.

### Hướng 4: quy hoạch động giả đa thức

Với SUBSET SUM có trọng số không âm và mục tiêu nguyên T, một DP theo tổng có thể đạt:

**`O(nT)` thời gian và `O(T)` bộ nhớ**.

Khi T nhỏ hoặc vừa, DP cực hữu dụng, ngay cả n lớn. Nhưng nếu T được mã hóa **nhị phân**, O(nT) **không phải đa thức theo độ dài input**. Đây là **pseudo-polynomial time**, không chứng minh SUBSET SUM thuộc P.

### Hướng 5: tham số hóa (parameterized algorithms)

Một thuật toán **fixed-parameter tractable (FPT)** theo tham số k có dạng:

**`f(k)·poly(|input|)`**.

Nếu k nhỏ, f(k) có thể chấp nhận được dù hàm mũ hoặc lớn. Ví dụ một số bài trên graph có DP theo **treewidth k** với thời gian tăng mạnh theo k nhưng đa thức theo số đỉnh khi k cố định. Không suy mọi bài NP-hard đều FPT theo mọi tham số; phải tìm đúng tham số và thuật toán.

### Hướng 6: xấp xỉ có bảo đảm

Với một bài **tối ưu**, nếu không cần nghiệm tốt nhất tuyệt đối, có thể dùng **approximation algorithm** và chứng minh tỷ số so với tối ưu trong các giả thiết cụ thể.

Ví dụ:
- Minimum vertex cover có thuật toán **2-approximation** dựa trên matching cực đại.
- Metric TSP (chi phí là metric, có bất đẳng thức tam giác) có thuật toán xấp xỉ dựa trên MST với tỷ số 2, và còn những thuật toán tốt hơn cho trường hợp phù hợp.
- Set cover có thuật toán greedy với đảm bảo xấp xỉ logarithmic theo mô hình chuẩn.

**Không** áp bảo đảm metric TSP cho TSP tổng quát với trọng số tùy ý không thỏa bất đẳng thức tam giác.

### Hướng 7: heuristic/metaheuristic và solver

Greedy, local search, simulated annealing, genetic algorithms, SAT/SMT/ILP/CP-SAT solvers đều có chỗ đứng. Phải phân biệt:

- **Heuristic:** có thể cho nghiệm tốt nhanh, **không bảo đảm tối ưu** trên mọi input.
- **Exact solver:** có thể chứng minh tối ưu hoặc không khả thi khi kết thúc chứng minh; có thể phải chạy rất lâu.
- **Anytime optimization:** báo nghiệm khả thi hiện tại, cận tối ưu và gap; kết thúc vì time limit chưa nhất thiết có nghiệm tối ưu.
- **SAT solver:** khi trả SAT với phép gán, có thể kiểm witness; khi trả UNSAT cần dựa trên tính đúng của solver hoặc chứng minh/proof log phù hợp.

**UNKNOWN/timeout không đồng nghĩa NO/UNSAT.** Một thuật toán do ngân sách tài nguyên chỉ giải được một số trường hợp phải biểu diễn trạng thái này tách biệt.

## 10. Bảng lựa chọn theo tình huống

| Tình huống | Hướng thường cân nhắc | Cần kiểm |
|---|---|---|
| Bài chứng minh thuộc P, input lớn | BFS/DP/flow/sort/thuật toán đa thức đúng bài | Độ phức tạp thật, bộ nhớ |
| SUBSET SUM n≤20, T rất lớn | Vét cạn/bitmask | O(2^n), tràn tổng |
| SUBSET SUM n≈40, T lớn | **Meet-in-the-middle** | O(2^{n/2}) bộ nhớ và thời gian |
| SUBSET SUM n lớn, **T nhỏ** | **DP theo tổng** | O(nT), T là giá trị, không phải số bit |
| SUBSET SUM n lớn, T lớn, input tổng quát | Solver exact có giới hạn; tận dụng cấu trúc; heuristic khi được phép | Không cam kết luôn nhanh/chính xác nếu timeout |
| Graph có treewidth nhỏ | DP tham số hóa theo treewidth | Có decomposition đúng |
| 0/1 knapsack tối ưu, cần gần tối ưu | FPTAS/approximation phù hợp | Ý nghĩa ε và bảo đảm |
| Vertex cover, được phép nghiệm gần tối ưu | 2-approximation | Đúng mô hình graph |
| TSP metric | Metric approximation | Bất đẳng thức tam giác |
| Bài SAT với số biến thực tế vừa phải | SAT solver, propagation, learning | SAT/UNSAT/UNKNOWN và chứng nhận |
| Dữ liệu nhỏ nhưng deadline nghiêm | DP/branch-and-bound/hybrid | Time budget, early stopping |

Bảng là **gợi ý lựa chọn**, không phải công thức cứng: hai input cùng n và T có thể khác đáng kể về mật độ, cấu trúc, số phần tử trùng và giới hạn bộ nhớ. Cần ước lượng số phép toán và lượng cấp phát thật, sau đó benchmark trên dữ liệu đại diện.

## 11. SUBSET SUM: ví dụ xuyên suốt cho lựa chọn lời giải

SUBSET SUM quyết định:

**`∃S⊆{1,...,n}: Σ_{i∈S}aᵢ=T?`**,

với `aᵢ,T` là số nguyên không âm được mã hóa nhị phân. Bài này là **NP-complete theo nghĩa yếu (weakly NP-complete)**: có thuật toán DP **giả đa thức** nhưng vẫn chưa có thuật toán đa thức tổng quát theo độ dài bit của input.

### Tại sao thuộc NP?

Chứng nhận là n bit chọn/không chọn. Cộng những số được chọn bằng số học đủ rộng rồi so T; kiểm trong thời gian đa thức theo tổng số bit input.

### Tại sao ví dụ này đáng học?

Nó minh họa rất rõ sự khác nhau giữa:
- **Khó trong trường hợp tổng quát** (NP-complete).
- **Có thuật toán exact chạy nhanh trên một miền tham số**: DP nếu T nhỏ.
- **Có thuật toán exact khác nhanh hơn vét cạn**: meet-in-the-middle nếu n≤40 và T lớn.
- **Greedy có thể cho kết luận sai**, dù nhìn hợp lý.
- **Không thể đổi “không tìm được trong ngân sách” thành NO**.

### Một input YES

~~~text
numbers = [3,34,4,12,5,2]
target  = 9

A valid subset: 4 + 5 = 9
Answer: YES
~~~

### Một input NO

Cùng dãy trên, target=30. Giá trị 34 lớn hơn T và không thể chọn nếu các số đều không âm. Tổng các số còn lại `3+4+12+5+2=26<30`, nên đáp án **NO**.

### Greedy sai

~~~text
numbers = [8,7,6]
target  = 13

Greedy largest-first:
  take 8 -> remaining 5
  7 and 6 do not fit -> returns NO

Exact:
  7 + 6 = 13 -> YES
~~~

Một thuật toán greedy tuy đơn giản nhưng **không chứng minh được** khi báo NO; mục tiêu của bài đòi hỏi exact, nên không thể dùng nó thay cho DP/MITM mà không có thêm điều kiện chứng minh.

### Zero và empty subset

Nếu T=0 và cho phép tập con rỗng, câu trả lời **luôn YES** (chọn không phần tử), kể cả mảng số rỗng. Nếu input rỗng và T>0, câu trả lời NO. Các số 0 có thể được chọn hoặc bỏ mà không thay đổi tổng; chúng **không gây unbounded reuse**, vì mỗi phần tử vẫn được xét tối đa một lần.

## 12. DP 0/1 SUBSET SUM theo tổng mục tiêu

Dùng mảng Boolean:

**`reachable[s]`** có nghĩa: “đã có một tập con từ các phần tử **đã xét** với tổng đúng bằng s”.

Khởi tạo:

**`reachable[0]=true`**, các tổng dương khác false.

Khi đọc một giá trị x≥0, công thức:

**`newReachable[s] = reachable[s] OR (s≥x AND reachable[s−x])`**.

Để tiết kiệm bộ nhớ, cập nhật **trực tiếp từ phải sang trái**:

~~~text
reachable[0] = true
for each x in numbers:
    for s from target down to x:
        reachable[s] = reachable[s] OR reachable[s - x]
return reachable[target]
~~~

### Vì sao phải duyệt s giảm dần?

Nếu cập nhật từ trái sang phải, một giá trị x vừa được dùng để tạo tổng s có thể lại được dùng trong **cùng lượt** để tạo tổng s+x, biến bài 0/1 thành **unbounded subset sum**.

Ví dụ chỉ có một phần tử 3, target=6:
- Nếu duyệt tăng, đặt reachable[3]=true rồi có thể tiếp tục đặt reachable[6]=true dựa trên reachable[3] mới, sai vì chỉ có **một** số 3.
- Duyệt giảm, khi xét s=6, reachable[3] vẫn là giá trị từ lượt trước, false. Kết quả NO đúng.

Với x=0, cập nhật không làm đổi tập tổng; có thể bỏ qua x để tiết kiệm thời gian. Nếu x>T và mọi số không âm, nó không thể là thành viên của một tập con có tổng đúng T, nên có thể bỏ qua x mà không mất nghiệm.

### Độ phức tạp

Với n phần tử, target T:

**`O(nT)` thời gian, `O(T)` bộ nhớ.**

Khi T=100.000, có thể dùng mảng 100.001 ô Boolean (chưa tính overhead JVM), khá gọn. Khi T=2.000.000.000, tạo mảng theo T là không hợp lý hoặc không thể. Vì vậy code minh họa chỉ tự dùng DP khi **`T≤200.000`**, một **ngưỡng tài nguyên tùy chọn của chương trình**, không phải ranh giới lý thuyết.

## 13. Meet-in-the-middle cho n vừa phải, T rất lớn

Giả sử n≤40. Chia dãy thành hai nửa A và B, mỗi nửa có tối đa 20 phần tử. Mọi tập con S của toàn bộ dãy có thể tách **duy nhất** thành `S_A` trong A và `S_B` trong B, nên:

**`sum(S)=sum(S_A)+sum(S_B)`**.

Tiến hành:
1. Sinh tất cả `2^{|A|}` tổng tập con của A.
2. Sinh tất cả `2^{|B|}` tổng tập con của B.
3. Sort danh sách tổng phía B.
4. Với mỗi tổng x của A, tìm bằng binary search tổng **T−x** trong danh sách B.
5. Nếu thấy, trả YES; nếu hết, trả NO.

Vì input không âm, có thể bỏ qua x>T trong vòng tìm để giảm việc không cần thiết.

### Ví dụ

~~~text
numbers = [100000, 900000, 600000, 400000]
target = 1000000

Left half:  [100000, 900000]
Right half: [600000, 400000]

Left subset sum 100000
Right subset sum 900000? no, that is left half.

Another option:
Left subset sum 100000+900000 = 1000000
Right subset sum 0
=> YES

Or split:
Left subset sum 0
Right subset sum 600000+400000 = 1000000
=> YES
~~~

Ở đây T=1.000.000 vượt ngưỡng DP minh họa 200.000, nhưng n=4 rất nhỏ, nên meet-in-the-middle thuận tiện. Nó không yêu cầu một mảng dài T ô.

### Cận độ phức tạp

Số tổng mỗi nửa ≤`2^{⌈n/2⌉}`. Việc sinh tổng, sort và binary search cho:

- Thời gian **`O(n·2^{n/2})`** theo cận thông dụng, bỏ qua chênh lệch lẻ n.
- Bộ nhớ **`O(2^{n/2})`** để giữ các tổng nửa.

Với n=40, mỗi phía có khoảng 1,05 triệu tổng; nếu mỗi tổng là `long` 8 byte, một danh sách thô chiếm khoảng 8 MiB chưa tính overhead; hai danh sách ~16 MiB. JVM cần thêm bộ nhớ sort và các đối tượng khác. Với n=60, mỗi nửa khoảng `2³⁰` tổng, thường **không khả thi** trong một bài thi thông thường.

### Tràn số khi cộng tổng tập con

Trong ví dụ Java, mỗi giá trị là **int không âm** và n≤40. Tổng lớn nhất không vượt `40·(2³¹−1) < 2⁶³−1`, nên tính tổng của mỗi nửa bằng `long` là **an toàn**.

Nếu cho phép n lớn hơn, giá trị long tùy ý, hoặc số âm, cần chứng minh lại miền trung gian. Code không sử dụng `int` cho tổng các tập con, kể cả khi `target` là int.

## 14. Java 17+ chạy được: chọn thuật toán theo giới hạn

Đây là một chương trình **minh họa quyết định chọn lời giải**, không phải solver NP-complete có thể xử lý mọi input lớn. Nó thực hiện:

- Kiểm input: chỉ nhận mảng `int[]` có giá trị không âm và `target≥0`.
- Nếu target=0: trả YES ngay vì tập con rỗng.
- Nếu target≤200.000: chọn **DP 0/1** `O(nT)`.
- Nếu target>200.000 nhưng n≤40: chọn **meet-in-the-middle** `O(n2^{n/2})`.
- Nếu target>200.000 và n>40: **từ chối do chính sách tài nguyên**, không in NO/UNSAT.
- Có phương pháp `bruteForce` dùng làm **oracle độc lập** trên test n nhỏ.
- Có heuristic chọn số lớn trước để minh họa **phản ví dụ greedy**.
- Không âm thầm đổi mục tiêu hoặc tính xấp xỉ khi người dùng yêu cầu exact.

Đầu ra từ `solve` là một cặp **`(possible, strategy)`** khi thuật toán exact đã chạy và kết luận. Khi input thuộc vùng không được hỗ trợ, hàm ném **`UnsupportedOperationException`**. Đây là một lựa chọn API quan trọng: **“chưa giải trong giới hạn này” khác hoàn toàn “NO”**.

Lưu mã vào tệp **`ComplexityDecisionDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Random;

public final class ComplexityDecisionDemo {
    // Example resource policy, NOT a complexity-theory bound.
    private static final int DP_LIMIT = 200_000;
    private static final int MITM_N_LIMIT = 40;

    private record Answer(boolean possible, String strategy) {}

    private static void validate(int[] values, int target) {
        if (values == null || target < 0) {
            throw new IllegalArgumentException(
                    "Null array or negative target");
        }
        for (int x : values) {
            if (x < 0) {
                throw new IllegalArgumentException(
                        "All values must be nonnegative");
            }
        }
    }

    // Exact 0/1 subset sum, O(n * target), O(target) memory.
    private static boolean subsetSumDP(
            int[] values, int target) {
        boolean[] reach = new boolean[target + 1];
        reach[0] = true;

        for (int x : values) {
            if (x == 0 || x > target) {
                continue;
            }
            // DESCENDING so this item is used at most once.
            for (int s = target; s >= x; s--) {
                if (reach[s - x]) {
                    reach[s] = true;
                }
            }
        }
        return reach[target];
    }

    // Generate every subset sum for a half of length <= 20.
    // Values are int >= 0; all sums fit in long.
    private static long[] halfSums(
            int[] values, int begin, int end) {
        int length = end - begin;
        int count = 1 << length; // length <= 20.
        long[] sums = new long[count];

        for (int mask = 1; mask < count; mask++) {
            int lowBit = Integer.numberOfTrailingZeros(mask);
            int previous = mask & (mask - 1);
            sums[mask] = sums[previous]
                    + values[begin + lowBit];
        }
        return sums;
    }

    // Exact subset sum, O(n * 2^(n/2)) time.
    private static boolean subsetSumMeetInMiddle(
            int[] values, int target) {
        if (values.length > MITM_N_LIMIT) {
            throw new UnsupportedOperationException(
                    "Meet-in-the-middle limit exceeded");
        }

        int middle = values.length / 2;
        long[] left = halfSums(values, 0, middle);
        long[] right = halfSums(values, middle, values.length);
        Arrays.sort(right);

        for (long sumLeft : left) {
            if (sumLeft > target) {
                continue; // Nonnegative input.
            }
            long wanted = (long) target - sumLeft;
            if (Arrays.binarySearch(right, wanted) >= 0) {
                return true;
            }
        }
        return false;
    }

    // Select an EXACT method under the chosen limits.
    private static Answer solve(
            int[] values, int target) {
        validate(values, target);

        if (target == 0) {
            return new Answer(true, "TRIVIAL");
        }
        if (target <= DP_LIMIT) {
            return new Answer(
                    subsetSumDP(values, target), "DP");
        }
        if (values.length <= MITM_N_LIMIT) {
            return new Answer(
                    subsetSumMeetInMiddle(values, target),
                    "MITM");
        }

        // Resource limit, not a proof of NO.
        throw new UnsupportedOperationException(
                "UNKNOWN under the current resource policy");
    }

    // Independent brute-force reference, used ONLY on small n.
    private static boolean bruteForce(
            int[] values, int index, long remaining) {
        if (remaining == 0L) {
            return true;
        }
        if (index == values.length) {
            return false;
        }

        if (bruteForce(values, index + 1, remaining)) {
            return true; // Skip current value.
        }
        return values[index] <= remaining
                && bruteForce(
                        values,
                        index + 1,
                        remaining - values[index]);
    }

    // Intentionally unreliable heuristic for illustration.
    private static boolean greedyLargestFirst(
            int[] values, int target) {
        int[] sorted = values.clone();
        Arrays.sort(sorted);
        long remaining = target;

        for (int i = sorted.length - 1; i >= 0; i--) {
            if (sorted[i] <= remaining) {
                remaining -= sorted[i];
            }
        }
        return remaining == 0L;
    }

    private static void show(
            String label, int[] values, int target) {
        Answer result = solve(values, target);
        System.out.println(
                label + ": " + result.possible()
                + " via " + result.strategy());
    }

    private static void randomChecks() {
        Random rng = new Random(4642026L);

        for (int trial = 0; trial < 1500; trial++) {
            int n = rng.nextInt(13);
            int[] values = new int[n];
            for (int i = 0; i < n; i++) {
                values[i] = rng.nextInt(25);
            }
            int target = rng.nextInt(150);

            boolean expected = bruteForce(
                    values, 0, target);
            boolean dp = subsetSumDP(values, target);
            boolean mitm = subsetSumMeetInMiddle(
                    values, target);
            boolean selected = solve(
                    values, target).possible();

            if (dp != expected || mitm != expected
                    || selected != expected) {
                throw new AssertionError(
                        "Mismatch at trial " + trial);
            }
        }
        System.out.println("Random checks: 1500 PASS");
    }

    public static void main(String[] args) {
        int[] numbers = {3, 34, 4, 12, 5, 2};
        show("Small YES", numbers, 9);
        show("Small NO", numbers, 30);

        int[] trap = {8, 7, 6};
        System.out.println(
                "Greedy trap: exact="
                + solve(trap, 13).possible()
                + ", greedy=" + greedyLargestFirst(trap, 13));

        show("Zero target", new int[] {0, 0}, 0);
        show("Large target",
                new int[] {100_000, 900_000, 600_000, 400_000},
                1_000_000);
        show("Near int limit",
                new int[] {
                    Integer.MAX_VALUE, Integer.MAX_VALUE, 1, 0
                }, Integer.MAX_VALUE);
        show("Empty NO", new int[] {}, 1);

        try {
            int[] many = new int[41];
            Arrays.fill(many, 1);
            solve(many, 300_000);
            throw new AssertionError(
                    "Resource guard was not triggered");
        } catch (UnsupportedOperationException expected) {
            System.out.println(
                    "Unsupported exact: UNKNOWN (policy)");
        }

        try {
            solve(new int[] {1, -2, 3}, 2);
            throw new AssertionError(
                    "Negative value must be rejected");
        } catch (IllegalArgumentException expected) {
            System.out.println("Negative input: rejected");
        }

        randomChecks();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ComplexityDecisionDemo.java
java ComplexityDecisionDemo
~~~

**Stdout chính xác** của chương trình:

~~~text
Small YES: true via DP
Small NO: false via DP
Greedy trap: exact=true, greedy=false
Zero target: true via TRIVIAL
Large target: true via MITM
Near int limit: true via MITM
Empty NO: false via DP
Unsupported exact: UNKNOWN (policy)
Negative input: rejected
Random checks: 1500 PASS
~~~

### Giải thích từng kết quả

**Small YES:** tập `[3,34,4,12,5,2]` có tập con `4+5=9`, nên DP trả true.

**Small NO:** mục tiêu 30 không đạt được. Số 34 lớn hơn T, các số còn lại có tổng 26, nên DP trả false.

**Greedy trap:** `[8,7,6],T=13` có nghiệm `7+6`; greedy largest-first chọn 8 rồi không thể bù 5, báo false. Đây là ví dụ cho thấy heuristic **không đủ để kết luận NO**.

**Zero target:** theo hợp đồng cho phép tập con rỗng, `T=0` luôn true, kể cả input toàn 0 hoặc rỗng. Code trả `TRIVIAL` mà không cấp mảng DP.

**Large target:** `T=1.000.000>200.000` nên code dùng MITM; `100.000+900.000=1.000.000`, hoặc `600.000+400.000=1.000.000`.

**Near int limit:** target=`Integer.MAX_VALUE`; một số riêng lẻ đã bằng target. Code dùng **long cho tổng các nửa**, tránh tràn khi cộng nhiều int trước khi so.

**Empty NO:** input rỗng và T=1, DP chỉ có reach[0] true, reach[1] false.

**Unsupported exact:** n=41 và T=300.000 vượt hai giới hạn được cấu hình. **UNKNOWN** nghĩa chương trình không thực hiện bài toán trong tài nguyên đã định, **không phải** chứng minh input vô nghiệm. Thực tế mảng 41 số 1 và target 300.000 là NO, nhưng chương trình chủ ý không suy luận thêm; nó phản ánh **API giới hạn phạm vi**.

**Negative input:** phiên bản quyết định này chỉ chấp nhận số nguyên không âm; âm bị từ chối. SUBSET SUM với số âm là biến thể khác, có thể xử lý bằng kỹ thuật khác, nhưng DP từ 0..T ở đây **không** áp nguyên xi.

**Random checks:** 1500 bộ số nguyên không âm nhỏ, đối chiếu **DP, meet-in-the-middle, bộ chọn tự động** với **vét cạn đệ quy độc lập**. Nếu một phương pháp trả khác, chương trình ném AssertionError; chỉ in PASS khi tất cả cùng kết quả.

### Định nghĩa chiến lược trong code là một chính sách minh họa

Ngưỡng `DP_LIMIT=200.000` và `MITM_N_LIMIT=40` là **quyết định kỹ thuật** để đảm bảo chương trình demo chạy hợp lý, không phải kết quả của định lý NP-complete. Nếu máy có nhiều RAM/CPU, giá trị có thể thay đổi. Một production solver nên xem thêm:
- `n·T` so với time budget, không chỉ T.
- Số phép cộng/đọc bộ nhớ và cách cấp phát mảng.
- Phân bố số lớn/nhỏ, khả năng giảm GCD.
- Tổng nhỏ hơn T (chứng nhận NO nhanh).
- Số phần tử có giá trị 0, trùng hoặc lớn hơn T.
- Có cần xuất **witness subset** hay chỉ YES/NO.
- Có cần kết quả UNKNOWN khi hết thời gian không.

## 15. Vì sao code này không “giải được NP-complete trong đa thức”?

Thuật toán `solve` có hai nhánh:

- Với target nhỏ: **`O(nT)`**, giả đa thức; T có thể lên đến 2³¹−1 trong int và quá lớn để cấp mảng.
- Với n nhỏ: **`O(n2^{n/2})`**, vẫn hàm mũ theo n.
- Với cả hai lớn: **không có lời giải tổng quát** trong chính sách demo, nên ném lỗi thay vì bịa NO.

Không hề có tuyên bố rằng `O(nT)` là đa thức theo số **bit** của T. Cũng không có tuyên bố `O(2^{n/2})` là đa thức theo n. Vì vậy đoạn code hoàn toàn tương thích với việc SUBSET SUM là NP-complete.

### “Giả đa thức” không có nghĩa “gần đa thức”

Thuật toán pseudo-polynomial có thời gian đa thức theo **giá trị số của một hoặc nhiều tham số** được viết bằng nhị phân. Nếu T thay từ 10⁵ lên 10⁹, DP O(nT) tăng 10.000 lần dù số bit của T chỉ tăng rất ít. Đó là khác biệt bản chất.

### Weakly NP-complete và strongly NP-complete

Một bài **weakly NP-complete** như SUBSET SUM (trên biểu diễn nhị phân chuẩn) có thể có thuật toán giả đa thức. Với các bài **strongly NP-complete** trong những điều kiện chuẩn, độ khó vẫn tồn tại ngay cả khi các giá trị số bị giới hạn theo đa thức của kích thước mô tả thích hợp, nên không kỳ vọng một thuật toán pseudo-polynomial tổng quát trừ khi P=NP.

Không áp phân loại weak/strong bừa bãi cho một bài **không có tham số số học tự nhiên** hoặc một biến thể khác chưa được định nghĩa chính xác. Đặc biệt, cùng tên bài nhưng khác ràng buộc (số không âm, số âm, encoded unary, cardinality, capacities) có thể đổi tính chất.

## 16. Kiểm thử sự đúng đắn của thuật toán chọn

### 16.1. Oracle độc lập bằng vét cạn

Trong `bruteForce`, tại mỗi phần tử có hai lựa chọn:
1. **Bỏ phần tử hiện tại**.
2. **Lấy phần tử hiện tại** nếu nó không vượt tổng còn cần.

Khi remaining=0, trả true. Khi hết phần tử mà remaining>0, trả false. Vì xét mọi tập con, thuật toán này **đúng tuyệt đối** cho số không âm, nhưng có cận xấu nhất O(2^n). Nên chỉ chạy trên n nhỏ trong unit test.

### 16.2. So ba hướng khác nhau

Cho mỗi input random nhỏ:
- Kết quả DP.
- Kết quả MITM.
- Kết quả brute force.
- Kết quả `solve` chọn tự động.

Tất cả phải giống nhau. Mỗi phương pháp có **cách thực hiện khác** nên có thể bắt lỗi ở cách duyệt DP, enumerate mask, binary search và quy tắc chọn phương pháp.

Một mô hình kiểm thử độc lập đã chạy **17.000 bộ SUBSET SUM ngẫu nhiên**, mỗi bộ có 0..15 phần tử và target nhỏ, đối chiếu DP, MITM, brute và auto; mọi kết quả khớp. Các trường hợp target=0, input rỗng, zero-only, gần Integer.MAX_VALUE và phản ví dụ greedy cũng được kiểm. Đây là kiểm chứng triển khai, không phải bằng chứng các bài NP-complete có thuật toán đa thức.

### 16.3. Kiểm chiều reduction độc lập

Với 3-SAT→CLIQUE, có thể:
- Duyệt mọi phép gán của công thức ít biến, đánh giá satisfiable.
- Dựng graph theo từng literal occurrence và cạnh giữa hai literal không mâu thuẫn thuộc hai clause khác nhau.
- Duyệt mọi tập k=m đỉnh trong đồ thị nhỏ để kiểm tồn tại clique.
- So hai kết quả trên hàng nghìn công thức nhỏ.

Kiểm logic dựng graph trên **1.600 công thức nhỏ** cho cùng kết quả YES/NO giữa SAT và CLIQUE. Những test này bắt được một số lỗi xây cạnh hoặc bỏ sót điều kiện “khác clause”, nhưng **không thay thế chứng minh hai chiều** của reduction.

### 16.4. Kiểm witness độc lập với thuật toán tìm

Nếu một solver trả tập con S:
- Kiểm mỗi chỉ số thuộc [0,n), không trùng.
- Cộng các giá trị với số học đủ rộng.
- So tổng đúng bằng T.

Nếu solver trả YES mà không có witness, muốn phát hiện bug có thể dùng oracle trên input nhỏ, hoặc sửa solver để truy vết DP/MITM. Nếu solver trả NO trên input lớn, việc chứng minh NO có thể khó hơn kiểm chứng một lời giải YES; đừng hiểu nhầm “không tìm thấy witness trong thời gian đã cấp” là chứng nhận NO.

## 17. Bài toán tối ưu: chính xác, cận và chất lượng

Giả sử bài 0/1 knapsack tối ưu yêu cầu **tối đa hóa tổng giá trị** với ràng buộc trọng lượng. Một lời giải greedy có thể đưa ra tập đồ vật **hợp lệ** và một giá trị. Nhưng:
- **Hợp lệ** khác **tối ưu**.
- Nếu không có cận tối ưu hay chứng minh xấp xỉ, không thể nói “gần tối ưu” chỉ vì điểm số có vẻ cao.
- Nếu solver branch-and-bound tìm được **upper bound U** và nghiệm khả thi **lower bound L** cho bài tối đa hóa, khoảng `U−L` giúp định lượng gap.
- Nếu `U=L`, đã chứng minh tối ưu (với tất cả tính toán/cận đúng).
- Nếu hết thời gian mà `U>L`, nên báo nghiệm tốt nhất được biết và gap, không báo đã tối ưu.

### Approximation ratio

Với bài tối thiểu hóa có tối ưu OPT>0, thuật toán α-approx có thể bảo đảm:

**`cost(solution)≤α·OPT`**, với α≥1.

Với bài tối đa hóa, dạng phát biểu bảo đảm thường là:

**`value(solution)≥OPT/α`**,

hoặc dùng `(1−ε)OPT` tùy khái niệm scheme. Cần nêu rõ chiều bất đẳng thức, miền OPT>0 và giả thiết của bài.

**FPTAS** (*fully polynomial-time approximation scheme*) có thời gian đa thức theo kích thước input **và 1/ε**, đạt sai số tương đối theo định nghĩa phù hợp. Một số biến thể của 0/1 knapsack có FPTAS, nhưng đây là kết quả về **bài tối ưu cụ thể**, không phải “mọi bài NP-hard đều có FPTAS”.

### Quy tắc nếu yêu cầu YES/NO chính xác

Nếu bài quyết định yêu cầu chứng minh YES hay NO, một heuristic phát hiện witness YES hợp lệ có thể báo YES ngay. Nhưng nếu heuristic **không** tìm được witness, nó chỉ được báo **UNKNOWN** trừ khi có chứng minh NO. Đây là một khác biệt rất thực dụng trong thiết kế API và chấm bài tự động.

## 18. Trường hợp đặc biệt và giảm kích thước trước khi chạy thuật toán khó

Trước khi chọn thuật toán exact cho bài khó, hãy tìm những **tiền xử lý bảo toàn nghiệm**:

### SUBSET SUM với số không âm

- T=0 ⇒ YES do tập rỗng.
- Nếu tổng tất cả số <T ⇒ NO, miễn là tổng được tính chính xác.
- Nếu một số x=T ⇒ YES.
- Nếu x>T ⇒ không thể chọn x trong một nghiệm tổng đúng T, có thể bỏ x.
- Nếu x=0 ⇒ không ảnh hưởng khả năng đạt T (nhưng ảnh hưởng số lượng witness).
- Nếu tất cả số và T có GCD g>1, có thể chia chính xác cho g. Nếu T không chia hết GCD của các số, có thể kết luận NO.

Các kiểm tra này **không đổi lớp độ phức tạp tổng quát**, nhưng có thể biến nhiều instance thực tế thành dễ.

### Đồ thị

- Với nhiều bài, xét đồ thị **liên thông hay không**, DAG hay không, là cây hay không, bậc đỉnh/độ rộng cây có bị chặn không.
- Một instance có thành phần nhỏ có thể giải theo từng thành phần rồi ghép, nếu bài toán cho phép phân rã như vậy.
- Các quy tắc kernelization có thể giảm n theo tham số k trước khi chạy nhánh cận, nhưng cần chứng minh bảo toàn đáp án.

**Không** áp dụng quy tắc “bỏ đỉnh” hoặc “chia thành thành phần” cho mọi bài tùy tiện: với một số ràng buộc toàn cục, lựa chọn ở các thành phần có thể liên quan qua mục tiêu.

## 19. Phân biệt độ phức tạp tệ nhất và hiệu năng thực nghiệm

Một thuật toán exact cho NP-hard vẫn có thể chạy rất tốt trên nhiều trường hợp thực. Nhưng benchmark phải ghi:
- Kích thước input, cách mã hóa số, mật độ cạnh, cấu trúc/khoảng giá trị.
- Phân phối **dễ/khó**, không chỉ random đơn giản.
- Trình biên dịch, CPU/RAM, thư viện hoặc solver version.
- Thời gian xây dữ liệu/tiền xử lý so với thời gian giải.
- Bộ nhớ cực đại và trường hợp out-of-memory.
- Giới hạn thời gian, tỷ lệ SAT/UNSAT/UNKNOWN và tỷ lệ chứng minh tối ưu.
- Với optimization: chất lượng nghiệm và gap chứng nhận.

**Không chứng minh P=NP bằng benchmark.** Dù một solver SAT xử lý hàng triệu công thức công nghiệp nhanh, điều đó không tạo thành **chặn đa thức cho mọi công thức SAT theo độ dài input**.

### NP-hard không có nghĩa mọi giải pháp đều exponential

Phát biểu “bài NP-hard chắc chắn phải O(2^n)” là sai. Một thuật toán exact có thể dùng `1,5^n`, `2^{n/2}`, branch-and-bound, DP tham số hóa, hoặc có hành vi rất khác nhau theo input. Chưa có định lý chung xác định rằng mọi bài NP-hard đều đòi **đúng** một cận exponential cố định trong mọi mô hình.

### P=NP chưa được giải quyết

Không phát biểu “không thể có thuật toán đa thức cho SAT” như một sự thật đã chứng minh. Những gì đã biết:
- SAT/3-SAT/CLIQUE/SUBSET SUM là NP-complete dưới các định nghĩa chuẩn.
- Một thuật toán đa thức cho **một bài NP-complete** sẽ kéo theo P=NP.
- Hiện chưa có chứng minh P=NP hoặc P≠NP được cộng đồng toán học chấp nhận.

Từ đó suy ra thái độ đúng trong thiết kế: **đừng cam kết tồn tại lời giải đa thức tổng quát chưa có bằng chứng**, nhưng luôn tìm **cấu trúc đặc biệt, tham số nhỏ hoặc mức xấp xỉ đủ dùng**.

## 20. Các lỗi tư duy thường gặp

1. **Đọc NP thành “non-polynomial”** — sai tên và sai ý nghĩa.
2. **Cho P và NP là hai tập rời nhau** — thực tế `P⊆NP`.
3. **Khẳng định đã chứng minh P≠NP** — đây vẫn là bài toán mở.
4. **Cho NP là lớp các bài “khó”** — NP bao gồm cả P.
5. **Nhầm tìm witness với kiểm witness** — NP chỉ yêu cầu kiểm YES nhanh.
6. **Cho NP nghĩa là chứng minh NO nhanh** — đây là chủ đề khác, không theo định nghĩa NP thông thường.
7. **Gọi bài tối ưu NP-complete mà không nói phiên bản quyết định** — thuật ngữ dùng sai ngữ cảnh.
8. **Nhầm NP-hard với NP-complete** — NP-hard không bắt buộc thuộc NP.
9. **Chỉ chứng minh B∈NP rồi kết luận B NP-complete** — thiếu NP-hard.
10. **Chỉ chứng minh B NP-hard rồi kết luận B NP-complete** — thiếu membership.
11. **Giảm B về bài khó A rồi kết luận B khó** — sai hướng reduction.
12. **Bảo toàn mỗi YES mà không chứng minh NO** — chưa có equivalence.
13. **Xây reduction mất thời gian siêu đa thức** — không đủ để chứng minh giảm đa thức.
14. **Dựng CLIQUE graph theo biến thay vì literal occurrence** — không đúng ví dụ 3-SAT.
15. **Nối hai literal mâu thuẫn trong graph reduction** — có thể sinh clique giả.
16. **Quên cấm cạnh trong cùng clause** — clique không buộc chọn đại diện từ các clause khác nhau.
17. **Cho bài NP-complete đã chứng minh vô phương giải đa thức** — không đúng trạng thái P vs NP.
18. **Cho NP-hard có nghĩa “mọi input đều khó”** — nhầm bài tổng quát với instance.
19. **Đánh giá chỉ bằng n mà bỏ qua số bit/giới hạn T** — chọn sai thuật toán.
20. **Gọi DP O(nT) là đa thức theo bit input** — đây là giả đa thức khi T nhị phân.
21. **Cho T=10⁹ chỉ là khoảng 30 nên DP nhỏ** — nhầm bit length với giá trị T.
22. **Duyệt DP 0/1 tăng dần tổng** — vô tình dùng phần tử nhiều lần.
23. **Dùng int để cộng tổng nhiều số int** — có thể tràn.
24. **Dùng MITM nhưng giữ tất cả 2^n tổng** — không đạt lợi ích chia đôi.
25. **Nhầm MITM O(2^{n/2}) là đa thức** — vẫn exponential.
26. **Cho greedy lớn trước giải chính xác subset sum** — phản ví dụ [8,7,6], T=13.
27. **Heuristic không tìm thấy nghiệm rồi in NO** — chỉ có quyền báo UNKNOWN.
28. **Time limit hết nhưng báo tối ưu** — chưa chứng minh gap=0.
29. **Áp 2-approx metric TSP cho TSP không metric** — thiếu giả thiết tam giác.
30. **Áp FPTAS cho mọi NP-hard optimization** — không có bảo đảm tổng quát.
31. **Cho nghiệm khả thi là nghiệm tối ưu** — thiếu so với cận hoặc chứng minh.
32. **Gọi n=40 “nhỏ” mà không tính 2^40** — vượt xa thực dụng nếu vét cạn trực tiếp.
33. **Bỏ qua RAM của MITM** — 2^{n/2} phần tử vẫn tốn bộ nhớ.
34. **Chọn DP vì T nhỏ mà không xét nT** — n có thể quá lớn.
35. **Cho mọi NP-hard có thuật toán FPT với mọi tham số** — không đúng.
36. **Áp DP theo cây cho đồ thị có chu trình không kiểm** — sai giả thiết cấu trúc.
37. **Dùng nhiều test random rồi coi đã chứng minh thuật toán đúng** — test không thay chứng minh.
38. **Chỉ test trường hợp YES** — bỏ qua bug báo YES sai trên trường hợp NO.
39. **Chỉ test n dương, quên input rỗng và target=0** — sai các biên.
40. **Dùng nguồn oracle cũng gọi DP nên lặp cùng bug** — nên brute độc lập cho n nhỏ.
41. **Không xác định bài cần YES/NO hay xuất witness** — output thiếu yêu cầu.
42. **Gọi bài có đáp án nhanh là thuộc P** — một instance không xác định lớp của cả bài.
43. **Dùng unary encoding để “chứng minh” SUBSET SUM nhị phân thuộc P** — đã đổi đầu vào.
44. **Tuyên bố SAT solver thực tế chạy tốt chứng minh P=NP** — benchmark không phải chặn tiệm cận.
45. **Không báo UNKNOWN khi resource limit** — khiến người dùng hiểu nhầm trạng thái.

## 21. Bài tập tự luyện

**Bài 1 — Nhận diện quyết định/tối ưu.** Với CLIQUE, VERTEX COVER, TSP và KNAPSACK, hãy viết mỗi bài theo dạng câu hỏi YES/NO có ngưỡng rồi viết lại dạng tối ưu tương ứng. Chỉ ra dạng nào được gán nhãn NP-complete theo định nghĩa.

**Bài 2 — Witness.** Cho đồ thị n đỉnh và k, mô tả chứng nhận cho CLIQUE cùng thuật toán kiểm O(k²) sau khi có phép tra cạnh. Giải thích vì sao điều ấy chưa cho thuật toán tìm clique đa thức.

**Bài 3 — Hướng giảm.** Muốn chứng minh bài B NP-hard dựa trên 3-SAT đã NP-complete, hãy chọn hướng đúng trong hai phương án `3-SAT≤ₚB` và `B≤ₚ3-SAT`; giải thích bằng thuật toán giả sử giải B nhanh.

**Bài 4 — Reduction 3-SAT→CLIQUE.** Với ba clause đã cho trong mục 8, tạo các đỉnh literal occurrence và cạnh giữa các literal ở hai clause khác nhau không mâu thuẫn. Tìm clique m=3 nếu công thức thỏa được.

**Bài 5 — Pseudo-polynomial.** So `T=10^5` và `T=10^9` trong DP O(nT), rồi so số bit biểu diễn hai giá trị. Giải thích vì sao thuật toán không chứng minh bài nhị phân ở P.

**Bài 6 — Greedy thất bại.** Với [8,7,6], target13, chạy greedy từ lớn xuống rồi đưa witness [7,6]. Đề xuất hai test khác làm greedy sai.

**Bài 7 — MITM.** Cho 10 số dương và target lớn, chia năm-năm, liệt kê tổng mỗi bên rồi tìm cặp đạt target. So với vét cạn 2¹⁰.

**Bài 8 — DP 0/1.** Với [3] và target6, chạy cập nhật tăng và giảm; xác định chính xác vì sao cập nhật tăng trả sai.

**Bài 9 — Lựa chọn chiến lược.** Đề cho n≤40 và mỗi số ≤10⁹; chọn giữa DP O(nT), vét cạn 2^n, MITM 2^{n/2}. Ước lượng bộ nhớ nếu dùng hai mảng long một triệu phần tử.

**Bài 10 — Ngưỡng chọn.** Thiết kế thuật toán chọn DP nếu nT trong giới hạn thời gian thật, MITM nếu n≤40, còn lại trả UNKNOWN hoặc gọi solver khác. Vì sao không nên gắn cứng việc T≤200.000 với mọi máy?

**Bài 11 — Chứng nhận tối ưu.** Trong bài tối đa hóa, một solver có nghiệm khả thi giá trị 95 và cận trên 100. Có chứng minh tối ưu chưa? Khi nào có thể báo đã tối ưu?

**Bài 12 — Nhiều biến.** Một SAT solver cho 100 biến trả SAT cùng assignment. Viết hàm verifier, giải thích sự khác nhau giữa kiểm chứng và tìm assignment.

**Bài 13 — Hạn chế cụ thể.** Chọn một bài NP-hard tổng quát và một trường hợp đặc biệt (ví dụ graph là cây hoặc T nhỏ). Tìm một thuật toán exact cho trường hợp đặc biệt và ghi rõ giả thiết.

**Bài 14 — Tỉ số xấp xỉ.** Với bài minimization có OPT=20, thuật toán 2-approx bảo đảm tối đa bao nhiêu? Nếu thuật toán cho nghiệm 35, điều này có mâu thuẫn không? Phân biệt xấp xỉ có bảo đảm và heuristic.

**Bài 15 — NP không phải non-polynomial.** Lấy một bài trong P như reachability, mô tả vì sao nó cũng nằm trong NP mặc dù đã có thuật toán giải đa thức.

## 22. Checklist chọn lời giải trong bài lập trình

- Đã phân biệt **decision**, **search** và **optimization**?
- Đã xác định kích thước **mã hóa bit** của các tham số số học?
- Đã biết nhãn P/NP-hard/NP-complete áp dụng cho **phiên bản chính xác nào** của bài?
- Đã nhớ **P⊆NP** và P vs NP vẫn mở?
- Nếu bài NP-complete, có ràng buộc đặc biệt nào làm bài dễ hơn?
- Nếu dùng reduction, đã chọn đúng hướng **bài khó đã biết → bài cần chứng minh**?
- Nếu nói NP-complete, đã có cả **membership in NP** lẫn **NP-hardness**?
- Nếu dùng DP theo giá trị, đã nhận ra **pseudo-polynomial**?
- Nếu dùng bitmask/vét cạn, đã tính đúng 2^n hoặc n! trên n tối đa?
- Nếu dùng MITM, đã tính cả số phần tử và RAM ~2^{n/2}?
- Nếu dùng parameterized DP, đã xác định tham số k và độ lớn f(k)?
- Nếu dùng xấp xỉ, có bảo đảm và giả thiết chính xác hay chỉ heuristic?
- Nếu dùng SAT/ILP solver, đã phân biệt SAT/UNSAT/UNKNOWN và giới hạn thời gian?
- Nếu cần exact NO, có chứng minh hoặc thuật toán exact kết thúc, không chỉ heuristic fail?
- Nếu cần nghiệm tối ưu, đã có chứng nhận tối ưu/gap phù hợp?
- Nếu chỉ cần witness YES, đã có verifier độc lập?
- Đã xử lý zero, negative values, overflow và empty input theo đúng contract?
- Đã test các trường hợp YES/NO và phản ví dụ greedy?
- Đã benchmark trên giới hạn và phân bố input thật, không chỉ vài mẫu nhỏ?
- Khi thuật toán hết nguồn lực, API có báo **UNKNOWN/UNSUPPORTED**, không giả NO?

**Kết luận:** **P** có thuật toán quyết định đa thức; **NP** có chứng nhận YES kiểm đa thức; **NP-hard** khó ít nhất bằng mọi bài NP theo giảm đa thức; **NP-complete** là các bài quyết định vừa thuộc NP vừa NP-hard. Điều này **không** chứng minh P≠NP. Khi chọn lời giải, cần nhìn đúng **phiên bản bài toán, độ dài input, giới hạn n, giá trị tham số, cấu trúc đặc biệt, yêu cầu chính xác và ngân sách tài nguyên**. Với SUBSET SUM, cùng một nhãn NP-complete nhưng T nhỏ gợi ý **DP giả đa thức**, n≈40 và T lớn gợi ý **meet-in-the-middle**, còn bài tổng quát quá lớn đòi thêm cấu trúc, solver có giới hạn hoặc thay đổi yêu cầu. Không biến “chưa tìm thấy” thành “không tồn tại”: đó là nguyên tắc kỹ thuật quan trọng nhất khi xử lý những bài toán khó.