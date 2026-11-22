# Phép quy giảm và chiều lập luận về độ khó

## Mục tiêu học tập

Trong nhóm **Độ khó bài toán**, một câu hỏi rất quan trọng không chỉ là "thuật toán của mình chạy bao lâu?" mà còn là "**làm sao chứng minh một bài toán ít nhất khó bằng một bài toán khác?**". Công cụ trung tâm là **phép quy giảm** (*reduction*).

Một phép quy giảm từ bài toán quyết định A sang bài toán quyết định B là cách biến mỗi đầu vào x của A thành đầu vào f(x) của B sao cho **câu trả lời CÓ/KHÔNG được bảo toàn theo cả hai chiều**. Nếu phép biến đổi chạy trong thời gian đa thức, ta viết:

\[
\boxed{A\le_p B.}
\]

Cách đọc: "**A quy giảm được về B trong thời gian đa thức**" hoặc "**A không khó hơn B theo kiểu quy giảm này**".

Đây là chỗ rất dễ nhầm: để chứng minh **B là NP-hard**, ta thường lấy **một bài toán A đã biết NP-hard** và xây:

\[
\boxed{A\le_p B,}
\]

**không phải** B≤pA.

Sau bài này, bạn cần hiểu:

1. Phân biệt **bài toán quyết định**, bài toán tìm nghiệm và bài toán tối ưu.
2. Nêu định nghĩa chính xác của quy giảm nhiều-một thời gian đa thức (*polynomial-time many-one / Karp reduction*).
3. Hiểu tại sao điều kiện **"nếu và chỉ nếu"** và thời gian dựng f đều bắt buộc.
4. Đọc đúng mũi tên A≤pB, suy luận đúng bài toán nào **ít nhất khó bằng** bài toán nào.
5. Phân biệt **P**, **NP**, **NP-hard**, **NP-complete**, và hai bước riêng để chứng minh NP-complete.
6. Áp dụng tính **bắc cầu** của quy giảm.
7. Theo dõi một phép quy giảm chuẩn, đầy đủ chứng minh: **3-SAT ≤p CLIQUE**.
8. Kiểm tra ví dụ bằng Java 17+, gồm xây đồ thị, xác minh clique và oracle vét cạn cho trường hợp nhỏ.
9. Biết thêm quy giảm **CLIQUE ≤p INDEPENDENT SET ≤p VERTEX COVER**.
10. Nhận biết các ngụy biện thường gặp, nhất là **đảo chiều**, chỉ chứng minh một chiều, hoặc suy ra P≠NP như đã được chứng minh.

---

## 1. Bài toán quyết định và cách mã hóa đầu vào

Lý thuyết NP-completeness thường phát biểu trên **bài toán quyết định**, có đáp án thuộc:

```text
YES / NO
CÓ / KHÔNG
```

Ví dụ:

**CLIQUE (quyết định):** cho đồ thị vô hướng G và số nguyên k, hỏi liệu G có một tập ít nhất k đỉnh sao cho **mọi cặp đỉnh trong tập đều kề nhau** không?

**3-SAT (quyết định):** cho công thức Boolean dạng CNF, mỗi mệnh đề có ba vị trí literal (cho phép lặp để đệm), hỏi có phép gán biến làm công thức **đúng** không?

**VERTEX COVER (quyết định):** cho G và k, hỏi có tập **không quá k đỉnh** sao cho mọi cạnh của G có ít nhất một đầu mút trong tập không?

### 1.1. Khác với bài toán tối ưu

**MAX-CLIQUE tối ưu:** tìm kích thước clique lớn nhất và/hoặc chính clique đó.

**CLIQUE quyết định:** chỉ hỏi có clique kích thước **ít nhất k** hay không.

Nếu có thuật toán tối ưu nhanh cho MAX-CLIQUE, ta có thể trả lời CLIQUE quyết định nhanh bằng cách so kích thước tối ưu với k. Nhưng chiều ngược lại cần mô tả thêm một cơ chế dùng oracle quyết định, thường là tìm kiếm nhị phân theo k để biết kích thước, và **self-reduction** nếu cần khôi phục nghiệm cụ thể.

Không được phát biểu kết luận về độ khó tìm nghiệm/tối ưu mà không làm rõ cách liên hệ với phiên bản quyết định.

### 1.2. Dùng ngôn ngữ của tập chuỗi

Trong lý thuyết độ phức tạp, một bài toán quyết định có thể được coi là một ngôn ngữ:

\[
A\subseteq\{0,1\}^*.
\]

Một chuỗi đầu vào x có đáp án YES khi và chỉ khi:

\[
x\in A.
\]

Đồ thị, công thức Boolean, số k hay các cấu trúc khác đều cần một cách **mã hóa hữu hạn** thành chuỗi bit. Ký hiệu |x| là **độ dài mã hóa đầu vào**, không đơn thuần là số đỉnh hoặc độ lớn giá trị của một số.

Khi tuyên bố thuật toán chạy thời gian đa thức, cần hiểu là đa thức theo **độ dài mã hóa**. Ví dụ một số N được viết nhị phân chỉ cần O(log N) bit, nên thuật toán O(N) vòng lặp là **giả đa thức**, không nhất thiết đa thức theo độ dài input.

### 1.3. Đầu vào không hợp lệ

Khi bài toán được định nghĩa là ngôn ngữ, thường quy ước các mã hóa không hợp lệ không thuộc ngôn ngữ hoặc có cách xử lý rõ. Trong phép quy giảm, cần bảo đảm f tạo ra **đầu vào hợp lệ** của bài B hoặc quy định đầu vào không hợp lệ một cách nhất quán.

Một quy giảm đúng không chỉ hoạt động cho vài ví dụ được chọn; nó phải hoạt động trên **mọi đầu vào thuộc miền của bài A**.

---

## 2. Định nghĩa quy giảm nhiều-một thời gian đa thức

Ta viết:

\[
\boxed{A\le_p B}
\]

nếu tồn tại một hàm f có thể **tính được trong thời gian đa thức theo |x|** và với **mọi** đầu vào x:

\[
\boxed{
x\in A\iff f(x)\in B.
}
\]

Hai yêu cầu không thể thiếu:

1. **Tính được nhanh:** dựng f(x) trong thời gian O(|x|^c) cho một hằng số c.
2. **Bảo toàn đáp án YES/KHÔNG:** x là YES của A **khi và chỉ khi** f(x) là YES của B.

### 2.1. Điều kiện hai chiều

Đẳng thức logic:

\[
x\in A\iff f(x)\in B
\]

tương đương **hai mệnh đề**:

- **Chiều thuận:** nếu x là YES của A thì f(x) là YES của B.
- **Chiều đảo:** nếu f(x) là YES của B thì x là YES của A.

Hoặc diễn đạt phía NO:

- Nếu x là NO của A thì f(x) phải là NO của B.

Nếu chỉ chứng minh chiều thuận, có thể một x là NO lại bị biến thành f(x) là YES. Khi ấy thuật toán giải B có thể trả YES sai cho A, nên phép biến đổi **không phải** quy giảm nhiều-một đúng.

### 2.2. Hàm f không được "giải A trước"

Quy giảm được phép xử lý cấu trúc input, nhưng phải dựng f(x) **trong thời gian đa thức**. Một thủ thuật như:

```text
Nếu x thuộc A: xuất một YES-instance của B.
Nếu x không thuộc A: xuất một NO-instance của B.
```

không phải là chứng minh hữu ích khi bước "x thuộc A?" chính là bài toán khó cần giải và chưa có thuật toán đa thức.

Một quy giảm phải mô tả **cách biến đổi đầu vào cụ thể và tính được nhanh**, độc lập với việc biết trước đáp án của A.

### 2.3. Kích thước đầu ra

Nếu f(x) được xuất ra từng bit trong mô hình tính toán thông thường và chạy thời gian đa thức, độ dài đầu ra không thể vượt thời gian đó, nên:

\[
|f(x)|\le\operatorname{poly}(|x|).
\]

Khi viết chứng minh, vẫn nên kiểm tra **số đỉnh, số cạnh, số biến, số mệnh đề, số bit** của instance được dựng là đa thức theo độ dài instance ban đầu.

Nếu phép biến đổi tạo ra dữ liệu dài theo hàm mũ, nó không phải quy giảm thời gian đa thức.

### 2.4. Sơ đồ sử dụng quy giảm

```text
Input x của A
    |
    | f(x): biến đổi trong thời gian đa thức
    v
Input y=f(x) của B
    |
    | Thuật toán / oracle giải B
    v
Đáp án YES/NO của B
    |
    | Chính là đáp án YES/NO của A
    v
Kết quả cho A
```

Như vậy, **nếu giải được B nhanh thì giải được A nhanh** bằng cách tiền xử lý x→f(x) rồi dùng thuật toán cho B.

---

## 3. Cách đọc đúng chiều A≤pB

Từ:

\[
A\le_p B
\]

ta biết **A không khó hơn B** theo quy giảm đang dùng. Có thể hiểu B đủ sức biểu diễn mọi instance của A sau một bước chuyển đổi đa thức.

**Câu nên học thuộc:**

> Để chứng minh bài toán B khó, hãy biến bài toán A **đã biết khó** thành B: A≤pB.

### 3.1. Suy luận về thuật toán nhanh

Nếu:

\[
A\le_p B,\qquad B\in P,
\]

thì:

\[
\boxed{A\in P}.
\]

Vì ta có thể xây f(x) nhanh, giải f(x) bằng thuật toán đa thức cho B, rồi nhận đáp án của A.

Đây là chiều truyền **dễ**:

```text
B dễ  ==>  A dễ
khi A <=p B
```

### 3.2. Suy luận về độ khó

Nếu:

\[
A\text{ là NP-hard},\qquad A\le_p B,
\]

thì:

\[
\boxed{B\text{ là NP-hard}.}
\]

Lý do: với mọi L∈NP, vì A NP-hard nên L≤pA. Kết hợp A≤pB và tính bắc cầu:

\[
L\le_p A\le_p B.
\]

Do đó mọi bài toán NP đều quy giảm được về B.

Đây là chiều truyền **khó**:

```text
A khó  ==>  B khó
khi A <=p B
```

### 3.3. Không được đảo mũi tên

Từ `A≤pB` **không được tự suy ra `B≤pA`**.

Tương tự:

- Từ A∈P và A≤pB **không** suy ra B∈P.
- Từ B NP-hard và A≤pB **không** suy ra A NP-hard.
- Từ A NP-hard và B≤pA **không** suy ra B NP-hard.

Một bài toán rất dễ cũng có thể quy giảm được về một bài rất khó. Vì thế mũi tên **rất quan trọng**.

### 3.4. Bảng suy luận đúng và sai

| Biết | Kết luận hợp lệ |
| --- | --- |
| `A≤pB`, B∈P | A∈P |
| `A≤pB`, B∈NP | A∈NP |
| `A≤pB`, A NP-hard | B NP-hard |
| `A≤pB`, A NP-complete | B NP-hard |
| `A≤pB`, A NP-complete, B∈NP | B NP-complete |
| `A≤pB`, A∈P | **Không** suy ra B∈P |
| `A≤pB`, B NP-hard | **Không** suy ra A NP-hard |
| `A≤pB`, A NP-hard | **Không** suy ra B∈NP |
| `A≤pB` | **Không** suy ra `B≤pA` |

Dòng "B∈NP ⇒ A∈NP" đúng vì có thể lấy chứng chỉ NP cho f(x) và dùng thuật toán kiểm tra chứng chỉ ấy sau bước f(x), vốn là đa thức.

---

## 4. Nhắc lại P, NP, NP-hard và NP-complete

### 4.1. Lớp P

P là lớp các bài toán **quyết định** có thuật toán xác định chạy thời gian đa thức theo độ dài input.

Ví dụ trên biểu diễn thông thường: kiểm tra hai đỉnh có nối bởi đường đi trong đồ thị vô hướng có thể thực hiện bằng DFS/BFS trong thời gian đa thức.

### 4.2. Lớp NP

NP là lớp bài toán quyết định có thể **kiểm chứng một chứng chỉ YES** trong thời gian đa thức, với chứng chỉ có độ dài đa thức theo input.

Với CLIQUE(G,k), chứng chỉ là **k đỉnh**. Kiểm tra các đỉnh khác nhau và tất cả:

\[
\binom{k}{2}
\]

cặp có cạnh là một thủ tục đa thức.

**NP không có nghĩa "not polynomial".** NP là *nondeterministic polynomial time*. Ta biết:

\[
\boxed{P\subseteq NP}.
\]

Việc P=NP hay P≠NP vẫn là một câu hỏi mở trong lý thuyết độ phức tạp hiện đại.

### 4.3. NP-hard

Một bài B là **NP-hard** theo quy giảm nhiều-một thời gian đa thức nếu:

\[
\boxed{\forall L\in NP,\quad L\le_p B.}
\]

Định nghĩa này **không yêu cầu B∈NP**. Bài toán NP-hard có thể nằm ngoài NP; với các bài toán không phải quyết định cần làm rõ loại quy giảm/định nghĩa đang dùng.

### 4.4. NP-complete

Một bài B là **NP-complete** nếu:

\[
\boxed{B\in NP}
\]

và:

\[
\boxed{B\text{ NP-hard}.}
\]

Để chứng minh một bài toán mới B là NP-complete, có **hai việc riêng biệt**:

1. **Chứng minh B∈NP:** chỉ ra chứng chỉ YES và thuật toán kiểm chứng đa thức.
2. **Chứng minh B NP-hard:** lấy bài A đã biết NP-complete (hoặc NP-hard) và dựng `A≤pB`.

Chỉ chứng minh NP-hard mà chưa chứng minh B∈NP thì **chưa đủ** để kết luận NP-complete.

### 4.5. Không tự chứng minh P≠NP

Nếu một bài toán NP-hard B thuộc P, ta sẽ có P=NP. Do đó khi chứng minh B NP-hard, ta thường nói:

> Nếu B có thuật toán đa thức thì P=NP.

**Không** được nói vô điều kiện “B không thể có thuật toán đa thức” chỉ từ NP-hard, vì điều đó đòi giả định hoặc chứng minh P≠NP.

---

## 5. Công thức chung cho chứng minh một bài NP-complete

Giả sử mục tiêu là chứng minh **B NP-complete** và ta đã biết **A NP-complete**.

### Bước 1 — Xác định phiên bản quyết định của B

Phải có câu hỏi YES/NO chính xác, input và cách mã hóa rõ ràng. Ví dụ “có tồn tại nghiệm có chi phí ≤K?” khác với “tìm nghiệm tối ưu” nếu chưa chuyển đổi.

### Bước 2 — Chứng minh B∈NP

Đề xuất một chứng chỉ ngắn và thuật toán kiểm chứng:

```text
Input instance I
Certificate C (độ dài đa thức)
Verify(I,C) chạy thời gian đa thức
Verify chấp nhận khi và chỉ khi I là YES-instance
```

Với bài toán tồn tại cấu trúc, chứng chỉ thường là chính cấu trúc đó.

### Bước 3 — Chọn bài toán nguồn A đã biết khó

Một số bài chuẩn: SAT, 3-SAT, CLIQUE, INDEPENDENT SET, VERTEX COVER, 3-COLORING, HAMILTONIAN CYCLE, SUBSET SUM (cần định nghĩa chính xác từng phiên bản).

Chọn bài **có cấu trúc gần B** để việc biến đổi tự nhiên và dễ chứng minh.

### Bước 4 — Xây f từ A sang B

Với mọi instance x của A, dựng f(x) là một instance của B. Không gọi thuật toán giải A ở bước xây.

### Bước 5 — Chứng minh hai chiều

\[
x\in A\Rightarrow f(x)\in B
\]

và:

\[
f(x)\in B\Rightarrow x\in A.
\]

Chỉ có một chiều là chưa đủ.

### Bước 6 — Chứng minh thời gian/kích thước đa thức

Đếm rõ cấu trúc được tạo và công việc xây dựng. Ví dụ số đỉnh O(m), số cạnh O(m²) ⇒ xây bảng kề trong O(m²).

### Bước 7 — Kết luận theo đúng chiều

Vì A NP-hard và A≤pB, suy ra B NP-hard. Kết hợp B∈NP, suy ra:

\[
\boxed{B\text{ NP-complete}.}
\]

---

## 6. Ví dụ chuẩn: 3-SAT ≤p CLIQUE

Đây là một phép quy giảm kinh điển, giải thích rõ **chiều lập luận về độ khó**.

Ta đã biết 3-SAT là một bài toán NP-complete theo các kết quả cơ sở của lý thuyết NP-completeness. Mục tiêu của ví dụ này là chứng minh **CLIQUE NP-hard**, rồi chứng minh CLIQUE∈NP để kết luận NP-complete.

### 6.1. Định nghĩa 3-SAT

Một công thức dạng 3-CNF:

\[
F=C_1\land C_2\land\cdots\land C_m,
\]

mỗi mệnh đề `C_i` là phép OR của **đúng ba vị trí literal**:

\[
C_i=(\ell_{i,1}\lor\ell_{i,2}\lor\ell_{i,3}).
\]

Một literal là biến x hoặc phủ định ¬x. Việc một literal xuất hiện lặp trong một mệnh đề vẫn có thể được cho phép khi đệm mệnh đề ít hơn ba literal.

Câu hỏi: có cách gán true/false cho các biến làm F đúng không?

### 6.2. Định nghĩa CLIQUE

Đầu vào là đồ thị vô hướng đơn `G=(V,E)` và số nguyên k.

Một clique có k đỉnh là tập:

\[
S\subseteq V,\quad |S|=k
\]

sao cho mọi hai đỉnh phân biệt trong S đều có cạnh nối.

Phiên bản quyết định hỏi có clique kích thước **ít nhất k** không. Nếu có clique lớn hơn k, lấy bất kỳ k đỉnh trong nó cũng là clique kích thước k, nên có thể chứng minh bằng đúng k đỉnh.

### 6.3. Xây đồ thị từ công thức F

Với m mệnh đề, tạo **ba đỉnh cho mỗi mệnh đề**, tương ứng ba vị trí literal:

\[
v_{i,1},v_{i,2},v_{i,3}.
\]

Tổng:

\[
\boxed{|V|=3m}.
\]

Tạo cạnh giữa `v_{i,a}` và `v_{j,b}` **khi và chỉ khi**:

1. `i\ne j`: hai đỉnh thuộc **hai mệnh đề khác nhau**.
2. Hai literal tương ứng **không phải cặp phủ định nhau**.

Tức không nối x và ¬x, và **không nối hai đỉnh cùng mệnh đề**.

Đặt ngưỡng clique:

\[
\boxed{k=m}.
\]

Hàm f gửi công thức F đến:

\[
f(F)=(G_F,m).
\]

### 6.4. Ý nghĩa của cạnh

Nếu hai literal đến từ hai mệnh đề khác nhau và không mâu thuẫn, chúng có thể đồng thời được gán true trong ít nhất một phép gán phù hợp với hai literal đó.

Đồ thị chỉ nối những lựa chọn **tương thích**. Một clique kích thước m sẽ chọn các literal tương thích ở m mệnh đề khác nhau.

### 6.5. Ví dụ cụ thể

Cho:

\[
F=
(x_1\lor x_2\lor x_3)
\land
(\neg x_1\lor x_2\lor x_3)
\land
(\neg x_2\lor\neg x_3\lor x_1).
\]

Có m=3, nên tạo 9 đỉnh và hỏi đồ thị có clique kích thước k=3 không.

Đánh số đỉnh từ 0:

| ID | Mệnh đề | Literal |
| ---: | ---: | --- |
| 0 | C1 | x1 |
| 1 | C1 | x2 |
| 2 | C1 | x3 |
| 3 | C2 | ¬x1 |
| 4 | C2 | x2 |
| 5 | C2 | x3 |
| 6 | C3 | ¬x2 |
| 7 | C3 | ¬x3 |
| 8 | C3 | x1 |

Có 27 cặp đỉnh giữa các mệnh đề khác nhau, trong đó 6 cặp literal bổ sung đối nghịch nên không có cạnh; đồ thị còn:

\[
\boxed{21\text{ cạnh}.}
\]

Một phép gán thỏa F:

```text
x1=true
x2=true
x3=false
```

Ta chọn:

- v0 = x1 từ C1.
- v4 = x2 từ C2.
- v8 = x1 từ C3.

Các literal này cùng có thể đúng, thuộc ba mệnh đề khác nhau và không có cặp phủ định nhau. Vì vậy:

\[
\boxed{\{0,4,8\}\text{ là clique kích thước }3}.
\]

### 6.6. Ví dụ NO

Cho:

\[
F_{\mathrm{NO}}=
(x_1\lor x_1\lor x_1)
\land
(\neg x_1\lor\neg x_1\lor\neg x_1).
\]

Công thức này tương đương `x_1\land\neg x_1` nên **vô nghiệm**.

Đồ thị có sáu đỉnh, mục tiêu k=2. Không có cạnh nào giữa hai mệnh đề vì mọi literal ở mệnh đề đầu là x1, mọi literal ở mệnh đề sau là ¬x1 — luôn mâu thuẫn.

Vậy:

\[
|V|=6,\quad |E|=0,\quad k=2,
\]

không tồn tại clique kích thước 2. Hai phía đều cho **NO**.

---

## 7. Chứng minh đúng cho 3-SAT ≤p CLIQUE

Cần chứng minh chính xác:

\[
\boxed{
F\text{ thỏa được}
\iff
G_F\text{ có clique kích thước }m.
}
\]

### 7.1. Chiều thuận: SAT ⇒ CLIQUE

Giả sử tồn tại phép gán biến làm F đúng.

Vì:

\[
F=C_1\land\cdots\land C_m
\]

đúng, **mỗi mệnh đề có ít nhất một literal đúng**.

Với mỗi C_i, chọn **một literal đúng** và đỉnh tương ứng v_(i,a). Ta có m đỉnh được chọn.

Hai đỉnh bất kỳ:

- Thuộc hai mệnh đề khác nhau vì mỗi mệnh đề chỉ chọn một.
- Không thể là x và ¬x, vì một phép gán không thể làm cả x và ¬x cùng đúng.

Do cách xây cạnh, **mọi cặp đỉnh được chọn đều kề nhau**. Vậy chúng tạo clique kích thước m.

### 7.2. Chiều đảo: CLIQUE ⇒ SAT

Giả sử G_F có clique S kích thước m.

Vì **không có cạnh giữa các đỉnh cùng mệnh đề**, clique không thể chứa hai đỉnh từ cùng một mệnh đề.

Có đúng m mệnh đề và S gồm m đỉnh, suy ra **S chứa đúng một đỉnh từ mỗi mệnh đề**.

Những literal tương ứng không có cặp x và ¬x, vì nếu có một cặp bổ sung nhau, hai đỉnh ấy **không có cạnh**, trái với việc S là clique.

Do đó tập literal được chọn **nhất quán**. Ta xây phép gán:

- Nếu literal x_i được chọn, đặt x_i=true.
- Nếu literal ¬x_i được chọn, đặt x_i=false.
- Các biến chưa bị ràng buộc có thể gán tùy ý.

Không có x_i và ¬x_i cùng được chọn, nên phép gán này hợp lệ. Mỗi mệnh đề có một literal được chọn và được gán true. Vậy tất cả các mệnh đề đều đúng, tức F thỏa được.

### 7.3. Tính đa thức của phép xây

Với m mệnh đề:

- Tạo 3m đỉnh: **O(m)**.
- Xét tối đa:
  \[
  \binom{3m}{2}=O(m^2)
  \]
  cặp để quyết định có cạnh hay không.
- Mỗi lần so hai literal theo biến và dấu là thao tác hữu hạn trên biểu diễn đã cho.
- Kích thước danh sách/bảng kề tối đa O(m²), là đa thức theo kích thước công thức đầu vào.

Do đó f được xây **trong thời gian đa thức**.

### 7.4. Kết luận về độ khó

Vì 3-SAT NP-complete, đặc biệt là NP-hard, và:

\[
3\text{-SAT}\le_p\text{CLIQUE},
\]

nên:

\[
\boxed{\text{CLIQUE là NP-hard}.}
\]

Nhưng muốn kết luận CLIQUE **NP-complete**, vẫn cần thêm CLIQUE∈NP.

### 7.5. CLIQUE thuộc NP

Chứng chỉ YES là danh sách k đỉnh.

Thuật toán kiểm chứng:

1. Kiểm tra tất cả ID tồn tại và không trùng.
2. Với mọi hai ID trong danh sách, kiểm tra chúng có cạnh.
3. Chấp nhận khi đủ k đỉnh và mọi cặp đều kề nhau.

Có O(k²) phép kiểm tra cạnh nếu dùng ma trận kề, và độ dài chứng chỉ là O(k log|V|) bit; vì k≤|V| trong một instance YES, thủ tục kiểm chứng là đa thức.

Suy ra:

\[
\boxed{\text{CLIQUE}\in NP}.
\]

Kết hợp:

\[
\boxed{\text{CLIQUE là NP-complete}.}
\]

---

## 8. Java 17+: dựng phép quy giảm 3-SAT → CLIQUE

Mã dưới đây minh họa **cả phép biến đổi và các bước kiểm chứng**. Phần quy giảm chỉ xây đồ thị từ công thức, không tìm lời giải SAT.

Mã cũng có hai **oracle vét cạn**, chỉ dùng với instance nhỏ để kiểm tra ví dụ:

- `bruteSat`: duyệt tối đa 2^v phép gán.
- `bruteClique`: tìm clique đích bằng quay lui.

**Hai oracle không thuộc thuật toán quy giảm**, có thời gian tệ nhất hàm mũ và không được dùng làm bằng chứng cho việc xây f trong thời gian đa thức.

Tệp: **`ThreeSatToCliqueDemo.java`**.

```java
import java.util.Arrays;
import java.util.Objects;

public final class ThreeSatToCliqueDemo {

    // Variables are numbered from 0 to variables-1.
    public record Literal(int variable, boolean positive) {
        public boolean valueUnder(boolean[] assignment) {
            boolean value = assignment[variable];
            return positive ? value : !value;
        }
    }

    // Exactly three literal occurrences per clause.
    public record Formula(int variables, Literal[][] clauses) {
    }

    public record Vertex(
            int clauseIndex,
            int literalIndex,
            Literal literal) {
    }

    public record CliqueInstance(
            Vertex[] vertices,
            boolean[][] edges,
            int target) {
    }

    private static Literal pos(int variable) {
        return new Literal(variable, true);
    }

    private static Literal neg(int variable) {
        return new Literal(variable, false);
    }

    private static boolean complementary(
            Literal a, Literal b) {

        return a.variable() == b.variable()
                && a.positive() != b.positive();
    }

    // Polynomial-time reduction: 3-SAT -> CLIQUE.
    public static CliqueInstance reduce(Formula formula) {
        Objects.requireNonNull(formula, "formula");

        if (formula.variables() < 1
                || formula.clauses() == null
                || formula.clauses().length < 1) {
            throw new IllegalArgumentException(
                    "Need variables and nonempty clauses");
        }

        for (Literal[] clause : formula.clauses()) {
            if (clause == null || clause.length != 3) {
                throw new IllegalArgumentException(
                        "Every clause must have exactly 3 literals");
            }

            for (Literal literal : clause) {
                if (literal == null
                        || literal.variable() < 0
                        || literal.variable() >= formula.variables()) {
                    throw new IllegalArgumentException(
                            "Invalid literal");
                }
            }
        }

        int m = formula.clauses().length;

        if (m > Integer.MAX_VALUE / 3) {
            throw new IllegalArgumentException(
                    "Too many clauses for array indexing");
        }

        Vertex[] vertices = new Vertex[3 * m];
        int out = 0;

        for (int c = 0; c < m; c++) {
            for (int p = 0; p < 3; p++) {
                vertices[out++] =
                        new Vertex(c, p, formula.clauses()[c][p]);
            }
        }

        boolean[][] edge = new boolean[vertices.length]
                                      [vertices.length];

        for (int i = 0; i < vertices.length; i++) {
            for (int j = i + 1; j < vertices.length; j++) {
                Vertex a = vertices[i];
                Vertex b = vertices[j];

                boolean compatible =
                        a.clauseIndex() != b.clauseIndex()
                        && !complementary(
                                a.literal(), b.literal());

                edge[i][j] = compatible;
                edge[j][i] = compatible;
            }
        }

        return new CliqueInstance(vertices, edge, m);
    }

    public static boolean satisfies(
            Formula formula,
            boolean[] assignment) {

        if (assignment.length != formula.variables()) {
            throw new IllegalArgumentException(
                    "Assignment length must match variables");
        }

        for (Literal[] clause : formula.clauses()) {
            boolean clauseTrue = false;

            for (Literal literal : clause) {
                if (literal.valueUnder(assignment)) {
                    clauseTrue = true;
                    break;
                }
            }

            if (!clauseTrue) {
                return false;
            }
        }

        return true;
    }

    // Polynomial-time verification of a clique certificate.
    public static boolean isClique(
            CliqueInstance graph, int[] selected) {

        if (selected == null
                || selected.length != graph.target()) {
            return false;
        }

        int n = graph.vertices().length;

        for (int i = 0; i < selected.length; i++) {
            int a = selected[i];

            if (a < 0 || a >= n) {
                return false;
            }

            for (int j = 0; j < i; j++) {
                int b = selected[j];

                if (a == b || !graph.edges()[a][b]) {
                    return false;
                }
            }
        }

        return true;
    }

    public static int countEdges(CliqueInstance graph) {
        int count = 0;
        int n = graph.vertices().length;

        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                if (graph.edges()[i][j]) {
                    count++;
                }
            }
        }

        return count;
    }

    // Exponential oracle: SMALL examples only.
    private static boolean bruteSat(Formula formula) {
        int variables = formula.variables();

        if (variables > 20) {
            throw new IllegalArgumentException(
                    "Brute SAT demo limited to 20 variables");
        }

        boolean[] assignment = new boolean[variables];
        int combinations = 1 << variables;

        for (int mask = 0; mask < combinations; mask++) {
            for (int v = 0; v < variables; v++) {
                assignment[v] = (mask & (1 << v)) != 0;
            }

            if (satisfies(formula, assignment)) {
                return true;
            }
        }

        return false;
    }

    // Exponential oracle: SMALL graphs only.
    private static boolean bruteClique(
            CliqueInstance graph) {

        int[] chosen = new int[graph.target()];
        return searchClique(graph, 0, chosen, 0);
    }

    private static boolean searchClique(
            CliqueInstance graph,
            int start,
            int[] chosen,
            int depth) {

        if (depth == chosen.length) {
            return true;
        }

        int n = graph.vertices().length;
        int stillNeeded = chosen.length - depth;

        for (int v = start; v <= n - stillNeeded; v++) {
            boolean valid = true;

            for (int i = 0; i < depth; i++) {
                if (!graph.edges()[chosen[i]][v]) {
                    valid = false;
                    break;
                }
            }

            if (valid) {
                chosen[depth] = v;

                if (searchClique(
                        graph, v + 1, chosen, depth + 1)) {
                    return true;
                }
            }
        }

        return false;
    }

    public static void main(String[] args) {
        // F = (x1|x2|x3) & (!x1|x2|x3)
        //   & (!x2|!x3|x1).
        Formula yes = new Formula(3, new Literal[][] {
                {pos(0), pos(1), pos(2)},
                {neg(0), pos(1), pos(2)},
                {neg(1), neg(2), pos(0)}
        });

        CliqueInstance graph = reduce(yes);
        boolean[] assignment = {true, true, false};
        int[] selected = {0, 4, 8};

        System.out.println(
                "Assignment satisfies: "
                        + satisfies(yes, assignment));
        System.out.println(
                "Graph vertices: " + graph.vertices().length);
        System.out.println(
                "Graph edges: " + countEdges(graph));
        System.out.println(
                "Target clique size: " + graph.target());
        System.out.println(
                "Selected vertices: " + Arrays.toString(selected));
        System.out.println(
                "Selected is clique: " + isClique(graph, selected));
        System.out.println(
                "YES SAT oracle: " + bruteSat(yes));
        System.out.println(
                "YES CLIQUE oracle: " + bruteClique(graph));

        // (x1|x1|x1) & (!x1|!x1|!x1).
        Formula no = new Formula(1, new Literal[][] {
                {pos(0), pos(0), pos(0)},
                {neg(0), neg(0), neg(0)}
        });

        CliqueInstance noGraph = reduce(no);

        System.out.println(
                "NO graph vertices: "
                        + noGraph.vertices().length);
        System.out.println(
                "NO graph edges: " + countEdges(noGraph));
        System.out.println(
                "NO target clique size: " + noGraph.target());
        System.out.println(
                "NO SAT oracle: " + bruteSat(no));
        System.out.println(
                "NO CLIQUE oracle: " + bruteClique(noGraph));

        boolean invalidClauseRejected = false;

        try {
            reduce(new Formula(2, new Literal[][] {
                    {pos(0), pos(1)}
            }));
        } catch (IllegalArgumentException ex) {
            invalidClauseRejected = true;
        }

        System.out.println(
                "Invalid clause rejected: "
                        + invalidClauseRejected);
    }
}
```

### 8.1. Biên dịch và chạy

Sử dụng **JDK 17+**:

```bash
javac ThreeSatToCliqueDemo.java
java ThreeSatToCliqueDemo
```

**Stdout kỳ vọng:**

```text
Assignment satisfies: true
Graph vertices: 9
Graph edges: 21
Target clique size: 3
Selected vertices: [0, 4, 8]
Selected is clique: true
YES SAT oracle: true
YES CLIQUE oracle: true
NO graph vertices: 6
NO graph edges: 0
NO target clique size: 2
NO SAT oracle: false
NO CLIQUE oracle: false
Invalid clause rejected: true
```

### 8.2. Định nghĩa đỉnh và cạnh trong code

Mỗi `Vertex` giữ:

- `clauseIndex`: thuộc mệnh đề nào.
- `literalIndex`: vị trí thứ mấy trong mệnh đề.
- `literal`: biến và dấu phủ định.

Đỉnh ID được cấp theo thứ tự mệnh đề, ba ID liên tiếp cho một mệnh đề.

Hàm `complementary` trả true khi hai literal dùng cùng biến nhưng trái dấu.

Trong `reduce`:

```java
boolean compatible =
        a.clauseIndex() != b.clauseIndex()
        && !complementary(a.literal(), b.literal());
```

Hai điều kiện phải xuất hiện **đồng thời**. Nếu quên ràng buộc khác mệnh đề, clique có thể chọn nhiều literal từ một mệnh đề, làm hỏng chiều "clique ⇒ một literal cho mỗi mệnh đề". Nếu quên tránh literal phủ định, clique có thể chọn các lựa chọn mâu thuẫn.

### 8.3. Quy giảm không gọi oracle

Hàm `reduce` chỉ:

1. Kiểm tra input đúng 3 literal mỗi mệnh đề.
2. Tạo 3m đỉnh.
3. Dựng cạnh cho các cặp giữa mệnh đề khác nhau, không mâu thuẫn.
4. Trả ngưỡng k=m.

**Nó không gọi `bruteSat` hay `bruteClique`.** Hai phương thức vét cạn chỉ được gọi trong `main` để minh họa kết quả và kiểm thử.

Việc chương trình minh họa có cả oracle hàm mũ **không** làm thay đổi kết luận: **bản thân phép quy giảm vẫn chạy thời gian đa thức**.

### 8.4. Kiểm chứng chứng chỉ CLIQUE

`isClique` nhận graph và đúng k ID:

- Từ chối ID ngoài phạm vi.
- Từ chối ID trùng.
- Từ chối khi có hai đỉnh không có cạnh.

Đây là thuật toán **kiểm chứng chứng chỉ**, không phải thuật toán tìm clique. Vì số cặp chứng chỉ là O(k²), nó chứng minh tính kiểm tra được trong thời gian đa thức.

### 8.5. Hạn chế và hợp đồng

- Mã chỉ chấp nhận công thức **có ít nhất một mệnh đề**, ít nhất một biến, mỗi mệnh đề có đúng **ba vị trí literal**; trường hợp 3-CNF cho phép mệnh đề ngắn hơn có thể đệm literal trước khi gọi.
- Literal chứa ID biến thuộc `0..variables−1`.
- Dữ liệu demo dùng m nhỏ. `boolean[3m][3m]` cần O(m²) bộ nhớ và có thể không vừa RAM nếu m khổng lồ, nhưng đó là vấn đề tài nguyên thực tế, không phủ nhận cận đa thức.
- `bruteSat` giới hạn 20 biến để tránh phép liệt kê khổng lồ. Nó chỉ phục vụ kiểm thử và không phải phần của phép giảm.
- `bruteClique` là quay lui theo tập chọn, tệ nhất hàm mũ; không phải thuật toán đa thức.
- Java `record` giữ các tham chiếu đến mảng, nên nếu dùng như thư viện tổng quát cần phòng vệ thêm trước mutation mảng. Demo xây đồ thị, không sửa mảng sau khi giảm.
- Phiên bản CLIQUE dùng đồ thị vô hướng đơn, không có self-loop trong ma trận kề.

---

## 9. Quy giảm tiếp: CLIQUE → INDEPENDENT SET → VERTEX COVER

Một phép quy giảm khác cũng dễ hình dung và giúp luyện mũi tên.

### 9.1. Định nghĩa independent set

Tập I là **independent set** nếu không có hai đỉnh khác nhau trong I được nối bằng cạnh.

Bài toán quyết định **INDEPENDENT SET** hỏi: đồ thị G có independent set kích thước **ít nhất k** không?

### 9.2. Đồ thị bù

Với đồ thị đơn vô hướng G=(V,E), **đồ thị bù** `\overline G` có cùng đỉnh V và cạnh giữa u≠v **khi và chỉ khi G không có cạnh ấy**.

Nếu S là clique trong G, mọi cặp đỉnh của S có cạnh ở G, nên **không có cạnh** trong `\overline G`; S là independent set của đồ thị bù.

Chiều ngược lại cũng đúng.

Do đó:

\[
\boxed{
(G,k)\in\text{CLIQUE}
\iff
(\overline G,k)\in\text{INDEPENDENT SET}.
}
\]

Phép tạo đồ thị bù mất O(|V|²) nếu duyệt mọi cặp, nên:

\[
\boxed{
\text{CLIQUE}\le_p\text{INDEPENDENT SET}.
}
\]

Chú ý phải giữ **k** và chỉ bù cạnh giữa hai đỉnh **phân biệt**, không thêm self-loop.

### 9.3. Independent set và vertex cover

Một **vertex cover** C là tập đỉnh mà mọi cạnh của G có ít nhất một đầu mút thuộc C.

Với cùng đồ thị G, tập I independent nếu và chỉ nếu phần bù đỉnh `V\setminus I` là vertex cover.

Chứng minh:

- Nếu I independent, không có cạnh với cả hai đầu mút đều nằm trong I. Vậy mỗi cạnh có ít nhất một đầu mút trong `V\setminus I`, nên đó là vertex cover.
- Nếu C là vertex cover, không có cạnh với hai đầu mút cùng trong `V\setminus C`, nên `V\setminus C` independent.

Với `N=|V|`:

\[
\boxed{
(G,k)\in\text{INDEPENDENT SET}
\iff
(G,N-k)\in\text{VERTEX COVER},
}
\]

trong phạm vi k hợp lệ (hoặc quy ước thống nhất khi k<0/k>N).

Phép giảm chỉ cần giữ G và đổi tham số k thành N−k:

\[
\boxed{
\text{INDEPENDENT SET}
\le_p
\text{VERTEX COVER}.
}
\]

### 9.4. Chuỗi mũi tên độ khó

```text
3-SAT
  |
  | polynomial reduction
  v
CLIQUE
  |
  | complement graph, keep k
  v
INDEPENDENT SET
  |
  | same graph, new threshold |V|-k
  v
VERTEX COVER
```

Vì 3-SAT NP-hard và quy giảm bắc cầu:

\[
3\text{-SAT}\le_p
\text{CLIQUE}\le_p
\text{INDEPENDENT SET}\le_p
\text{VERTEX COVER},
\]

nên cả ba bài đồ thị ở sau đều NP-hard. Để gọi từng bài là NP-complete, còn cần chỉ ra chúng **thuộc NP**; chứng chỉ clique/independent set/vertex cover đều dễ kiểm tra trong thời gian đa thức.

---

## 10. Tính bắc cầu và tính tương đương

### 10.1. Bắc cầu

Nếu:

\[
A\le_p B
\]

qua hàm f, và:

\[
B\le_p C
\]

qua hàm g, thì:

\[
\boxed{A\le_p C}
\]

qua hàm:

\[
h(x)=g(f(x)).
\]

Vì f và g đều tính được trong thời gian đa thức và kích thước f(x) cũng chỉ tăng đa thức, hợp thành h vẫn tính được trong thời gian đa thức.

Về đáp án:

\[
x\in A
\iff f(x)\in B
\iff g(f(x))\in C.
\]

### 10.2. Tại sao kích thước trung gian quan trọng?

Giả sử |f(x)|≤|x|^a và g chạy thời gian O(|y|^b), khi y=f(x), chi phí g theo |x| là O(|x|^{ab}). Tổng với chi phí f vẫn là đa thức.

Nếu f tạo đầu ra dài theo hàm mũ, lập luận này không còn đúng. Do đó yêu cầu **f polytime** là thiết yếu.

### 10.3. Hai chiều quy giảm

Nếu:

\[
A\le_p B
\quad\text{và}\quad
B\le_p A,
\]

thì hai bài toán tương đương theo quy giảm nhiều-một đa thức, thường ký hiệu:

\[
A\equiv_p B.
\]

Đây là hai chứng minh **riêng**. Một chiều không đủ để khẳng định tương đương.

### 10.4. Reductions đến lớp P và NP

Khi A≤pB:

- Nếu B∈P thì A∈P.
- Nếu B∈NP thì A∈NP.
- Nếu B NP-hard và ta chỉ biết A≤pB, không thể kết luận A NP-hard.
- Nếu A NP-hard thì B NP-hard, bất kể B có thuộc NP hay không.

Một cách nhớ: quy giảm A→B tạo **đường giải A thông qua B**; vì vậy **độ dễ kéo ngược**, còn **độ khó đẩy xuôi**.

---

## 11. Quy giảm nhiều-một khác quy giảm Turing

Trong bài chứng minh NP-completeness phổ thông, ký hiệu `≤p` thường chỉ **Karp / many-one reduction**:

- Tạo **một** instance f(x) của B.
- Đáp án của B trên f(x) chính là đáp án của A trên x.
- Bước chuyển đổi chạy thời gian đa thức.

Một loại khác là **polynomial-time Turing reduction**, ký hiệu ví dụ:

\[
A\le_T^p B.
\]

Thuật toán giải A có thể hỏi một **oracle B nhiều lần, thích ứng với câu trả lời**, nhưng tổng thời gian ngoài oracle vẫn đa thức.

Đây là khái niệm mạnh hơn về khả năng truy cập B. Không được âm thầm dùng một chứng minh chỉ có **Turing reduction** rồi khẳng định đã thiết lập NP-hard theo chuẩn **many-one** nếu định nghĩa bài/giáo trình yêu cầu Karp reduction.

### 11.1. Khi thuật toán B trả thông tin hơn YES/NO

Bài toán **tìm nghiệm** có thể được dùng như oracle để giải bài quyết định, nhưng nếu chứng minh NP-hard cho bài quyết định B cần nêu rõ cách chuyển oracle tìm nghiệm thành một điều kiện YES/NO hoặc xây phiên bản quyết định tương ứng.

### 11.2. Khi có giả thiết phụ trong đầu vào

Một quy giảm đến bài **bị giới hạn đặc biệt** phải đảm bảo mọi f(x) thỏa giới hạn của bài đích. Ví dụ nếu bài B chỉ nhận đồ thị có bậc đỉnh ≤3, phép quy giảm 3-SAT→CLIQUE ở trên **không tự động** cho đồ thị bậc ≤3. Không thể dùng ngay chứng minh ấy cho phiên bản hạn chế nếu không có gadget/phép giảm mới.

### 11.3. Quy giảm bảo toàn tối ưu

Một số bài toán xấp xỉ hoặc tối ưu cần quy giảm giữ tỉ lệ xấp xỉ hay cấu trúc nghiệm. Quy giảm many-one cho **bài quyết định YES/NO** chưa đủ để suy ra mọi kết quả về xấp xỉ của bài tối ưu.

---

## 12. Các sai lầm logic phổ biến

### 12.1. Đảo chiều mũi tên

Muốn chứng minh B NP-hard, nhưng lại chứng minh:

\[
B\le_p A
\]

với A đã biết NP-hard. Điều đó chỉ nói B có thể được giải bằng A; **không** nói B khó.

**Đúng:** chứng minh `A≤pB`, với A NP-hard.

### 12.2. Chỉ chứng minh chiều YES

Dựng f sao cho:

\[
x\in A\Rightarrow f(x)\in B,
\]

nhưng không chứng minh chiều ngược. Có thể các đầu vào NO của A cũng bị biến thành YES của B. Đây là chứng minh thiếu.

**Đúng:** phải có `x∈A⇔f(x)∈B`.

### 12.3. Chỉ chứng minh NP-hard rồi tuyên bố NP-complete

Nếu chưa chứng minh B∈NP, kết luận B NP-complete **chưa đủ cơ sở**. Bài NP-hard có thể không thuộc NP.

### 12.4. Dùng thuật toán hàm mũ trong bước chuyển đổi

Một phép biến đổi f chỉ được gọi là quy giảm đa thức nếu **thời gian xây f** là đa thức theo kích thước input. Không thể giải SAT bằng vét cạn rồi xuất một instance YES hoặc NO tương ứng mà gọi đó là chứng minh NP-hard hợp lệ.

### 12.5. Phát biểu “NP-hard nghĩa là không giải được nhanh”

NP-hard nghĩa là mọi bài toán NP quy giảm được về nó. Nếu một bài NP-hard trong P thì P=NP. Vì P≠NP chưa được chứng minh, không nên tuyên bố tuyệt đối rằng **không có thuật toán đa thức** cho bài NP-hard.

### 12.6. Không phân biệt "đúng k" với "ít nhất k"

CLIQUE thường hỏi clique **ít nhất k**. Nếu tìm được clique lớn hơn k, ta có thể chọn k đỉnh làm clique kích thước k. Đây là lý do trong chứng minh dùng chọn đúng k đỉnh không tạo mâu thuẫn.

Đối với những bài toán khác, đổi giữa "đúng", "ít nhất" và "không quá" cần chứng minh lại, không mặc nhiên tương đương.

### 12.7. Không kiểm tra kích thước gadget

Một phép quy giảm xây thêm cấu trúc cho từng phần tử đầu vào cần tính được số đỉnh/cạnh/biến mới là đa thức. Chỉ nói "xây dễ dàng" mà không đếm kích thước có thể bỏ qua trường hợp số lượng gadget nở theo hàm mũ.

### 12.8. Không xử lý trường hợp đặc biệt

Công thức rỗng, đồ thị rỗng, ngưỡng k không hợp lệ, mệnh đề có literal lặp, đồ thị có self-loop hoặc biểu diễn không thống nhất có thể làm định nghĩa thay đổi. Có thể đặt hợp đồng đầu vào chuẩn và nêu rõ cách xử lý; không nên lờ đi khiến hai chiều chỉ đúng cho dữ liệu "đẹp".

### 12.9. Dùng phép giảm sai lớp

Không được khẳng định chuẩn NP-completeness many-one khi mới có một phép giảm Turing đa thức, trừ khi định nghĩa cụ thể cho phép và hệ quả được chứng minh phù hợp.

### 12.10. Trộn bài toán quyết định với tối ưu

Một chứng minh NP-hard cho phiên bản quyết định thường cho hệ quả về bài tối ưu qua một phép biến đổi đơn giản, nhưng phải **viết ra quan hệ ngưỡng và cách dùng lời giải tối ưu**. Không được tự coi hai phiên bản là đồng nhất về input/output.

---

## 13. Checklist kiểm tra phép quy giảm

Trước khi công bố A≤pB, hãy trả lời đủ các câu hỏi:

1. **A và B là gì?** Cả hai có input và câu hỏi YES/NO rõ không?
2. **A đã biết khó đến mức nào?** NP-hard/NP-complete đã được xác lập hay chỉ phỏng đoán?
3. **Tôi đang muốn chứng minh bài nào khó?** Mũi tên có hướng vào **bài mục tiêu** không?
4. **f(x) có được định nghĩa cho mọi x hợp lệ của A?**
5. **f có dùng lời giải A hoặc B bên trong không?** Nếu có, phải chứng minh chi phí vẫn đa thức.
6. **YES ⇒ YES đã được chứng minh đầy đủ chưa?**
7. **YES đích ⇒ YES nguồn đã được chứng minh chưa?**
8. **NO ⇒ NO có theo từ hai chiều không?**
9. **Kích thước f(x) có đa thức theo |x| không?**
10. **Thời gian dựng f(x) có đa thức không?**
11. **Instance đích có thỏa mọi điều kiện giới hạn của B không?**
12. **Nếu kết luận NP-complete, đã chứng minh B∈NP riêng chưa?**
13. **Có vô tình dựa vào P≠NP như một định lý đã chứng minh không?**
14. **Có nhầm Karp reduction với Turing reduction không?**
15. **Có kiểm thử các trường hợp YES/NO nhỏ để phát hiện lỗi gadget không?**

Nếu thiếu một trong các bước có ảnh hưởng tính đúng, chứng minh có thể chỉ là một **ý tưởng quy giảm** chứ chưa phải chứng minh hoàn chỉnh.

---

## 14. Kiểm thử và phản ví dụ

### 14.1. Kiểm tra quy giảm bằng oracle độc lập

Với những instance 3-CNF nhỏ, có thể thử:

1. Duyệt mọi phép gán biến để xác định F có thỏa được không.
2. Dựng G_F và k=m bằng `reduce`.
3. Duyệt các tập đỉnh kích thước k để xác định G_F có clique hay không.
4. So hai kết quả Boolean.

Ta cần:

```text
bruteSat(F) == bruteClique(reduce(F))
```

cho mọi test.

**Điều kiện cần cho một phép giảm đúng** là tương đương với mọi instance, không phải chỉ vài trăm test. Vét cạn chỉ giúp phát hiện bug cài đặt; **chứng minh hai chiều** mới bảo đảm mọi đầu vào.

### 14.2. Các test quan trọng

| Trường hợp | Kỳ vọng |
| --- | --- |
| Công thức SAT với nhiều mệnh đề | G có clique kích thước m |
| Công thức NO như `x∧¬x` đã đệm | G không có clique kích thước m |
| Một mệnh đề có literal lặp | Vẫn xây ba đỉnh tương ứng ba vị trí |
| Một mệnh đề tự chứa x và ¬x | Không tự xóa mệnh đề; xây đúng quy tắc |
| Hai literal thuộc cùng mệnh đề | **Không** tạo cạnh giữa chúng |
| Hai literal đối nghịch thuộc hai mệnh đề | **Không** tạo cạnh |
| Hai literal tương thích thuộc hai mệnh đề | Có cạnh |
| Mệnh đề không đủ ba vị trí với API ví dụ | Từ chối hoặc đệm trước theo hợp đồng |
| Ngưỡng CLIQUE từ m mệnh đề | Chính xác k=m |

### 14.3. Một phản ví dụ nếu quên ràng buộc khác mệnh đề

Nếu nối hai đỉnh **cùng mệnh đề**, một clique kích thước m có thể chọn nhiều đỉnh trong một mệnh đề mà không chọn literal nào ở mệnh đề khác. Chiều đảo "clique ⇒ mỗi mệnh đề được thỏa" hỏng.

Đây là lý do quy tắc cạnh cần đồng thời hai điều kiện **khác mệnh đề** và **không mâu thuẫn**.

### 14.4. Một phản ví dụ nếu quên kiểm tra literal đối nghịch

Nếu nối cả x và ¬x ở hai mệnh đề khác nhau, một clique có thể chọn hai literal không thể cùng true. Khi đó không suy ra được phép gán thỏa.

### 14.5. Giới hạn của random test

Random test có thể có xu hướng tạo công thức dễ SAT (nhiều literal, ít mệnh đề) hoặc dễ NO tùy phân phối. Nên bổ sung các trường hợp NO được xây chắc chắn, literal lặp, biến không xuất hiện, mệnh đề có cả x và ¬x, và những công thức vừa đủ ràng buộc.

---

## 15. Câu hỏi thường gặp về chiều quy giảm

### “A≤pB nghĩa là B dễ hơn A?”

**Không.** Nó nghĩa là A có thể chuyển sang B nhanh. Nếu B có thuật toán đa thức, A cũng có. Vì thế theo hướng suy luận độ khó, **B ít nhất khó bằng A**.

### “Muốn chứng minh B NP-hard, biến B thành 3-SAT đúng không?”

**Sai chiều.** Phải biến **3-SAT hoặc một bài NP-hard khác sang B**:

\[
3\text{-SAT}\le_p B.
\]

### “Nếu B đã NP-hard, chỉ cần chứng minh B≤pC để C NP-hard?”

**Đúng**, nếu phép giảm B≤pC là many-one đa thức và bảo toàn YES/NO hai chiều. Khi ấy mọi bài NP giảm sang B rồi sang C.

### “Nếu A≤pB và A có thuật toán đa thức, B có phải đa thức?”

**Không thể kết luận.** A có thể đơn giản hơn rất nhiều so với B.

### “Nếu A≤pB và B∈NP, A có thuộc NP?”

**Có.** Tính f(x) đa thức rồi dùng chứng chỉ NP của f(x) để kiểm chứng input A.

### “Chứng minh B NP-hard đã đủ gọi B NP-complete chưa?”

**Chưa.** Cần B∈NP.

### “Nếu chứng minh B NP-complete thì đã chứng minh B không có thuật toán đa thức?”

**Chưa.** Kết luận chính xác: nếu B có thuật toán đa thức thì P=NP.

### “Có thể giảm bằng cách tạo nhiều instance của B và hỏi oracle nhiều lần?”

Đó có thể là **Turing reduction**. Nó không tự động là phép giảm **many-one** dùng trong định nghĩa NP-complete chuẩn.

---

## 16. Bài tập tự kiểm tra

### Bài 1 — Định nghĩa
Phát biểu chính xác hai điều kiện cần cho A≤pB.

### Bài 2 — Chiều
Muốn chứng minh B NP-hard từ A NP-complete, mũi tên phải là A≤pB hay B≤pA?

### Bài 3 — Dễ kéo ngược
Từ A≤pB và B∈P, suy ra điều gì về A?

### Bài 4 — Khó đẩy xuôi
Từ A NP-hard và A≤pB, suy ra điều gì về B?

### Bài 5 — NP membership
Từ A≤pB và B∈NP, có thể kết luận A∈NP không?

### Bài 6 — Thiếu thông tin
Từ A≤pB và B NP-hard, có thể kết luận A NP-hard không?

### Bài 7 — NP-complete
Cần hai phần nào để chứng minh B NP-complete?

### Bài 8 — P vs NP
Nếu một bài NP-complete có thuật toán đa thức, suy ra điều gì?

### Bài 9 — Điều kiện iff
Tại sao chỉ chứng minh A YES ⇒ B YES là chưa đủ?

### Bài 10 — Kích thước
Vì sao số gadget sinh theo hàm mũ làm phép giảm không còn polynomial-time?

### Bài 11 — Bắc cầu
Nếu A≤pB và B≤pC, kết luận gì?

### Bài 12 — Công thức 3-SAT
3-CNF có m mệnh đề, xây bao nhiêu đỉnh trong quy giảm sang CLIQUE?

### Bài 13 — Ngưỡng
Ngưỡng clique k đặt bằng bao nhiêu trong quy giảm 3-SAT?

### Bài 14 — Cạnh
Khi nào nối hai đỉnh biểu diễn literal?

### Bài 15 — SAT ⇒ CLIQUE
Giải thích cách chọn clique từ một phép gán thỏa.

### Bài 16 — CLIQUE ⇒ SAT
Vì sao clique kích thước m phải có đúng một đỉnh từ mỗi mệnh đề?

### Bài 17 — Mâu thuẫn
Vì sao các literal của một clique không chứa đồng thời x và ¬x?

### Bài 18 — Chi phí
Với 3m đỉnh, vì sao việc dựng cạnh bằng cách xét mọi cặp là đa thức?

### Bài 19 — Chứng chỉ
Một chứng chỉ YES cho CLIQUE là gì và kiểm chứng ra sao?

### Bài 20 — Ví dụ YES
Với công thức ba mệnh đề ở mục 6, tập `{0,4,8}` có phải clique không?

### Bài 21 — Ví dụ NO
Với `(x∨x∨x)∧(¬x∨¬x∨¬x)`, đồ thị có clique kích thước 2 không?

### Bài 22 — Complement
CLIQUE(G,k) quy giảm sang INDEPENDENT SET bằng phép biến đổi nào?

### Bài 23 — Vertex cover
Tại sao independent set kích thước ≥k tương đương vertex cover kích thước ≤|V|−k?

### Bài 24 — Quy giảm ngược
Biết CLIQUE≤pINDEPENDENT SET có tự suy ra INDEPENDENT SET≤pCLIQUE không?

### Bài 25 — Turing reduction
Điểm khác biệt chính giữa Karp reduction và Turing reduction là gì?

### Bài 26 — Bài tối ưu
Vì sao cần nói rõ bài tối ưu hay bài quyết định khi chứng minh NP-hard?

### Bài 27 — Từ giả đa thức
Thuật toán O(N) với N nhập ở dạng nhị phân có nhất thiết là thời gian đa thức theo input không?

### Bài 28 — Restriction
Vì sao quy giảm 3-SAT→CLIQUE ở trên chưa chứng minh CLIQUE NP-hard trên đồ thị có bậc ≤3?

### Bài 29 — Kiểm thử
Nêu một oracle độc lập để kiểm tra quy giảm 3-SAT→CLIQUE trên instance nhỏ.

### Bài 30 — Phản ví dụ
Nếu xây cạnh giữa hai đỉnh cùng mệnh đề, bước nào của chứng minh bị ảnh hưởng?

### Đáp án gợi ý

1. Có f tính được trong thời gian đa thức và `x∈A⇔f(x)∈B` với mọi x.
2. `A≤pB`. Mũi tên **đi vào bài cần chứng minh khó**.
3. A∈P.
4. B NP-hard.
5. Có, A∈NP qua tính f và chứng chỉ cho f(x).
6. Không; hướng đó chỉ cho biết A không khó hơn B.
7. B∈NP và B NP-hard.
8. P=NP; không phải một mâu thuẫn đã được chứng minh.
9. Vì một NO-instance của A có thể bị biến thành YES-instance của B.
10. Chi phí ghi/tạo output đã theo hàm mũ theo độ dài input.
11. `A≤pC` qua hợp thành hai phép giảm.
12. `3m` đỉnh.
13. `k=m`.
14. Khác mệnh đề **và** hai literal không phủ định nhau.
15. Chọn một literal true từ mỗi mệnh đề; các literal true không mâu thuẫn nên tạo clique.
16. Không có cạnh giữa đỉnh cùng mệnh đề và có m mệnh đề, clique có m đỉnh.
17. Một cặp literal đối nghịch không được nối cạnh theo cách dựng.
18. Tối đa O(m²) cặp đỉnh; kiểm tra tương thích cho mỗi cặp.
19. Danh sách k ID đỉnh; kiểm tra phân biệt và mọi cặp có cạnh trong O(k²).
20. Có; ba literal x1, x2, x1 đều tương thích và thuộc ba mệnh đề.
21. Không; đồ thị có sáu đỉnh và không có cạnh chéo, nên không có clique kích thước 2.
22. Lấy đồ thị bù `\overline G`, giữ k.
23. Phần bù đỉnh của independent set là vertex cover và ngược lại.
24. Không suy ra tự động; có thể chứng minh chiều ngược riêng bằng cách lấy đồ thị bù lần nữa.
25. Karp tạo **một** instance đích, Turing có thể hỏi oracle nhiều lần một cách thích ứng.
26. Vì đầu ra khác nhau; cần quy định cách chuyển một thuật toán tối ưu/tìm nghiệm thành bộ giải YES/NO.
27. Không; độ dài biểu diễn nhị phân chỉ O(log N).
28. Đồ thị được tạo có thể có đỉnh bậc lớn hơn 3, không thỏa hạn chế đầu vào.
29. Vét cạn tất cả phép gán Boolean của công thức và tất cả tập k đỉnh của đồ thị, so hai kết quả Boolean.
30. Chiều "clique ⇒ chọn đúng một literal mỗi mệnh đề" có thể sai.

---

## Tóm tắt cần nhớ

**Định nghĩa:** A≤pB nếu tồn tại phép biến đổi f tính được trong thời gian đa thức sao cho:

\[
\boxed{x\in A\iff f(x)\in B.}
\]

**Đọc đúng chiều:**

```text
A <=p B

Nếu B dễ (thuộc P), thì A dễ.
Nếu A khó (NP-hard), thì B khó.
```

**Muốn chứng minh B NP-complete:**

1. Chứng minh **B∈NP** bằng chứng chỉ và thuật toán kiểm chứng đa thức.
2. Chọn A đã biết NP-hard, dựng **A≤pB**.
3. Chứng minh **YES⇔YES** cả hai chiều và f chạy **thời gian đa thức**.
4. Kết luận B NP-hard, kết hợp B∈NP để có B NP-complete.

Ví dụ chuẩn:

\[
\boxed{
3\text{-SAT}\le_p\text{CLIQUE}
\le_p\text{INDEPENDENT SET}
\le_p\text{VERTEX COVER}.
}
\]

**Những điều không được quên:** không đảo mũi tên; không chỉ chứng minh một chiều; không dùng thuật toán giải A bên trong f khi chưa chứng minh đa thức; không gọi NP-hard là NP-complete nếu chưa chỉ ra thuộc NP; không tự khẳng định P≠NP đã được chứng minh; và không nhầm quy giảm many-one với quy giảm Turing.
