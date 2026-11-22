# Tập phủ tham lam và ý nghĩa của bảo đảm xấp xỉ

## 1. Từ bài toán chọn tài nguyên đến Set Cover

Giả sử một công ty phải đáp ứng mọi yêu cầu {A, B, C, D, E, F}. Mỗi gói dịch vụ đáp ứng một tập con yêu cầu. Ta muốn mua **ít gói nhất**, hoặc tổng **chi phí nhỏ nhất**, nhưng vẫn đáp ứng **tất cả** yêu cầu. Đây là **Set Cover (tập phủ)**.

Biểu diễn tổng quát:

- **Vũ trụ (universe)** U: tất cả n phần tử phải được bao phủ.
- **Họ tập con** S₀, S₁, …, S_(m−1), với S_i ⊆ U.
- Mỗi tập có chi phí c_i **dương**; bản không trọng số có c_i=1 cho mọi i.
- Chọn tập chỉ số I ⊆ {0,…,m−1} sao cho **hợp các S_i với i∈I bằng U**, và tổng chi phí \(\sum_{i\in I}c_i\) là nhỏ nhất.

**Bản quyết định:** Có thể chọn không quá k tập (hoặc chi phí không vượt B) để phủ U không? **Bản tối ưu:** Chi phí nhỏ nhất là bao nhiêu và chọn những tập nào?

Set Cover tổng quát là bài toán tối ưu **NP-hard**; bản quyết định là **NP-complete**. Với đầu vào lớn, việc duyệt mọi nhóm tập có thể không khả thi. Vì thế ta thường muốn một thuật toán chạy nhanh, tạo được lời giải hợp lệ và có **bảo đảm xấp xỉ** định lượng.

Bài này tập trung vào thuật toán **greedy** (tham lam), cả không trọng số và có trọng số, chứng minh cận hài hòa, so với tối ưu exact trên ví dụ nhỏ, và cách đọc đúng ý nghĩa của hệ số xấp xỉ.

## 2. Định nghĩa chính xác nghiệm và giá trị OPT

Một tập chỉ số I là **nghiệm khả thi** nếu mọi u∈U nằm trong ít nhất một S_i với i∈I. Trong bài toán không trọng số, chi phí lời giải là số tập được chọn |I|. Với trọng số, chi phí là tổng c_i.

Gọi **OPT** là chi phí nhỏ nhất trong các nghiệm khả thi. Nếu không có nghiệm nào (ví dụ có phần tử không thuộc tập con nào), bài toán **không khả thi**: OPT không phải 0, cũng không phải −1 dưới nghĩa toán học; chương trình có thể dùng −1 như một **mã lỗi** nhưng không được đem nó vào bất đẳng thức xấp xỉ.

Nếu U=∅, chọn 0 tập là tối ưu và OPT=0. Khi ấy tỷ số cost/OPT là 0/0, **không định nghĩa**, nên phải xử lý như trường hợp suy biến thay vì in “ratio=1.0” một cách tùy tiện.

Nếu có phần tử thuộc nhiều tập, nó vẫn chỉ cần được phủ **ít nhất một lần**. Set Cover khác **Exact Cover** (phủ đúng một lần), và khác **Vertex Cover** (chọn các đỉnh để mỗi cạnh có ít nhất một đầu mút được chọn). Bài toán **Maximum Coverage** với ngân sách k tập hỏi phủ được **nhiều phần tử nhất**, không phải phủ hết với **ít tập nhất**; hai mục tiêu có định lý xấp xỉ khác nhau.

## 3. Thuật toán tham lam cho Set Cover không trọng số

Duy trì tập các phần tử **chưa được phủ** R, ban đầu R=U. Ở mỗi bước, chọn tập S_i làm giảm R nhiều nhất, tức có **gain** lớn nhất:

**gain_i = |S_i ∩ R|**.

Sau khi chọn i, cập nhật R ← R \ S_i. Lặp cho tới khi R=∅. Nếu R còn phần tử mà mọi tập có gain=0, ta biết dữ liệu **không có phủ đầy đủ**, trả trạng thái “IMPOSSIBLE”.

```text
R = U
chosen = []
while R chưa rỗng:
    i = tập có |S_i ∩ R| lớn nhất
    nếu mọi gain đều bằng 0:
        return IMPOSSIBLE
    chosen.add(i)
    R = R \ S_i
return chosen
```

**Vì sao chọn “phần tử mới”?** Một tập rất lớn nhưng gần như toàn bộ phần tử của nó đã được phủ có thể chỉ giúp thêm 1 yêu cầu. Tính bằng kích thước |S_i| ban đầu ở mọi vòng là sai; cần tính lại |S_i∩R| sau mỗi lần chọn.

**Xử lý hòa:** khi nhiều tập cùng gain, chọn tập có chỉ số nhỏ nhất là một quy ước tất định dễ kiểm thử. Định lý xấp xỉ vẫn đúng với bất kỳ lựa chọn hòa nào đạt gain tối đa, nhưng nghiệm cụ thể có thể khác nhau.

### 3.1. Ví dụ greedy không đạt tối ưu

Cho U={1,2,3,4,5,6} và ba tập:

| Tập | Các phần tử | Gain ban đầu |
|---|---|---:|
| A | {1,2,3,4} | 4 |
| B | {1,2,5} | 3 |
| C | {3,4,6} | 3 |

Greedy chọn **A** trước vì gain 4 lớn nhất. Khi đó R={5,6}; B chỉ thêm 5, C chỉ thêm 6 nên phải chọn **cả B và C**. Kết quả greedy: **3 tập**.

Nhưng **B∪C=U**, nên chỉ cần **2 tập**. Vì không tập riêng lẻ nào phủ cả U, OPT=2. Đây là phản ví dụ:

**cost(greedy)=3, OPT=2, ratio=3/2=1,5.**

Nó chứng minh greedy Set Cover **không phải thuật toán exact**. Tuy nhiên “không luôn tối ưu” không đồng nghĩa “không có giá trị”: bảo đảm xấp xỉ cho biết nó có thể tệ tới đâu theo một công thức đúng cho mọi instance hợp lệ.

### 3.2. Một ví dụ greedy thành công

U={A,B,C,D}; S₀={A,B}, S₁={C,D}, S₂={A,C}. Greedy có thể chọn S₀ trước khi hòa, rồi S₁ để phủ toàn bộ, chi phí 2. Không có tập nào phủ bốn phần tử, nên OPT=2. Lưu ý ví dụ thành công không phải bằng chứng greedy luôn exact.

## 4. Set Cover có trọng số: chi phí trên một phần tử mới

Khi mỗi tập S_i có chi phí c_i>0, chọn tập có gain lớn nhất **bất kể chi phí** có thể quá tốn kém. Greedy đúng cho phiên bản có trọng số chọn tập có tỷ lệ **nhỏ nhất**:

**score_i = c_i / |S_i ∩ R|**, chỉ xét gain_i>0.

Tương đương chọn **gain_i/c_i lớn nhất**. Đây là chi phí cần trả để phủ thêm trung bình một phần tử chưa phủ, chứ không phải chi phí chia cho kích thước gốc của S_i.

```text
R = U
chosen = []
while R không rỗng:
    xét mọi i với gain_i = |S_i ∩ R| > 0
    chọn i có c_i/gain_i nhỏ nhất
    nếu không có i: return IMPOSSIBLE
    thêm i; R = R \ S_i
return chosen
```

Nếu mọi c_i=1, tối thiểu c_i/gain_i chính là tối đa gain_i; vì vậy thuật toán weighted trên toàn bộ chi phí 1 là đúng thuật toán unweighted.

### 4.1. Ví dụ weighted thay đổi quyết định

Sử dụng lại U={1,…,6}, các tập A,B,C ở mục 3 nhưng đặt c_A=10, c_B=c_C=3.

Tại đầu:

- A: cost/gain = 10/4 = 2,5.
- B: cost/gain = 3/3 = 1.
- C: cost/gain = 3/3 = 1.

Chọn B khi hòa do chỉ số, sau đó C phủ đúng ba phần tử còn lại. Chi phí greedy **6**, bằng OPT **6**. Trong khi đó nếu chỉ chọn tập có gain lớn nhất sẽ lấy A và cuối cùng tốn 10+3+3=16.

### 4.2. Weighted greedy cũng có thể không tối ưu

U={1,2,3,4}; A={1,2,3}, c_A=4; B={1,2}, c_B=3; C={3,4}, c_C=3.

Greedy chọn A trước vì 4/3 < 3/2. Sau A chỉ còn phần tử 4, nên phải chọn C: tổng **7**. Nhưng B∪C=U với tổng **6**, là tối ưu. Tỷ số **7/6 > 1**. Việc sử dụng ratio là một **heuristic có bảo đảm**, không phải phương pháp exact.

### 4.3. So sánh score mà không cần chia số thực

Nếu chi phí là các số nguyên dương, so c_i/g_i với c_j/g_j bằng tích chéo:

**c_i·g_j < c_j·g_i**.

Với Java và c_i<=1_000_000, g_i là int dương, tích hai số này dưới khoảng 2,15·10¹⁵ nên nằm trong signed long. Mã minh họa dùng long cho tích chéo và kiểm ràng buộc chi phí; nếu dùng chi phí số nguyên rất lớn/không giới hạn, cần số học nguyên chính xác như BigInteger để không tràn.

Với chi phí thực, cần cân nhắc sai số khi so tỷ lệ và một chính sách giải quyết tie rõ ràng. Với chi phí âm, “chọn để giảm chi phí” trở thành bài toán khác; bài này quy định **chi phí dương**.

## 5. Hệ số xấp xỉ là gì?

Một thuật toán cho bài toán **minimization** được gọi là thuật toán **α-approximation** (α≥1) nếu, cho **mọi instance khả thi** thuộc phạm vi định lý, thuật toán chạy trong thời gian đa thức, trả lời giải khả thi với chi phí ALG thỏa:

**OPT ≤ ALG ≤ α · OPT.**

Bất đẳng thức trái đúng vì OPT là nhỏ nhất. Bất đẳng thức phải mới là **bảo đảm hiệu năng**. Với Set Cover greedy, α được biểu diễn bằng một số hài hòa phụ thuộc kích thước instance.

**Không nhầm:**

- Hệ số α=2 **không** có nghĩa “đáp án đúng với xác suất 50%”, “sai đúng 2 phần tử” hay “tốn thêm chính xác hai tập”. Nó có nghĩa **tổng chi phí không vượt quá hai lần chi phí tối ưu**.
- Bảo đảm α là **cận trên cho mọi instance khả thi**, không phải kết quả trung bình của 100 lần thử.
- ALG/OPT trên **một instance** có thể nhỏ hơn nhiều α và có thể bằng 1; α không nói mọi lần greedy đều tệ đến mức đó.
- Tỷ lệ xấp xỉ **multiplicative** khác bảo đảm **additive** kiểu ALG≤OPT+K.
- Nghiệm phải phủ toàn bộ U. Một lựa chọn rẻ nhưng bỏ thiếu phần tử **không** được tính là nghiệm xấp xỉ của Set Cover chuẩn.

### 5.1. Số hài hòa H_d

Đặt **d = max_i |S_i|**, kích thước tập lớn nhất trong input, và:

**H_d = 1 + 1/2 + … + 1/d** cho d≥1.

Một số giá trị:

| d | H_d gần đúng |
|---:|---:|
| 1 | 1,0000 |
| 2 | 1,5000 |
| 3 | 1,8333 |
| 4 | 2,0833 |
| 5 | 2,2833 |
| 6 | 2,4500 |
| 10 | 2,92897 |

Với d≥1: **H_d ≤ 1+ln d ≤ 1+ln n**, vì mọi S_i⊆U. Với U rỗng thì OPT=0 và trả kết quả rỗng trực tiếp; không cố tính hệ số H_0 dưới dạng ratio.

**Định lý:** Với Set Cover khả thi, các c_i>0, phiên bản weighted greedy chọn tỷ lệ c_i/gain_i nhỏ nhất có:

**ALG ≤ H_d · OPT.**

Điều này cũng đúng cho unweighted greedy vì mọi c_i=1. Nhiều tài liệu phát biểu dạng **H_n** hoặc **1+ln n** cho gọn; cận dùng d có thể mạnh hơn đáng kể nếu mỗi tập rất nhỏ so với U.

### 5.2. Đọc cận trên ví dụ sáu phần tử

Ở ví dụ A={1,2,3,4}, B={1,2,5}, C={3,4,6}, ta có d=4; H₄=25/12≈2,0833.

Greedy=3, OPT=2, ratio thực tế 1,5. Định lý cho phép ALG≤H₄·OPT≈4,1667, nghĩa là cận đúng nhưng **không chặt** cho instance này. Nó **không** dự đoán greedy sẽ chọn 4,1667 tập; chi phí số tập là số nguyên và thực tế greedy chọn 3.

Dùng giá trị H₆≈2,45 cũng hợp lệ nhưng lỏng hơn vì d=4. Khi nói một bảo đảm, luôn ghi rõ d hay n để người đọc không áp nhầm công thức.

## 6. Chứng minh bảo đảm H_d bằng phương pháp “tính phí”

Đây là cách chứng minh quan trọng để hiểu **vì sao greedy có bảo đảm**, chứ không chỉ nhớ một công thức.

### 6.1. Tính phí cho từng phần tử

Giả sử tại một vòng, greedy chọn tập S có **g phần tử chưa phủ** và chi phí c(S). Ta gán “phí”:

**price(u) = c(S)/g** cho mỗi phần tử u **mới được phủ** ở vòng ấy.

Mỗi phần tử U được phủ đúng lần đầu tiên, nên bị tính phí đúng một lần. Tổng phí trên U bằng chính tổng chi phí các tập greedy đã chọn:

**ALG = ∑_{u∈U} price(u).**

Không tính phí lặp cho phần tử đã phủ ở các vòng sau. Đó là lý do gain phải tính bằng số phần tử **mới**.

### 6.2. Xét một tập bất kỳ T của nghiệm tối ưu

Chọn T∈OPT, có t=|T|≤d và chi phí c(T). Xét các thời điểm những phần tử của T được greedy phủ lần đầu. Khi còn **r** phần tử của T chưa phủ, chính T là một ứng viên có gain≥r (bằng đúng r nếu xét T∩R). Vì greedy chọn tỷ lệ cost/gain nhỏ nhất, tỷ lệ của tập greedy được chọn ở vòng ấy thỏa:

**c(S_greedy)/gain(S_greedy) ≤ c(T)/r.**

Vậy mỗi phần tử của T mới được phủ ở vòng ấy nhận phí ≤c(T)/r. Nếu một vòng phủ nhiều phần tử của T cùng lúc, gán cho chúng cùng mức phí và so tổng phí đó với các số hạng tương ứng của chuỗi 1/t + … + 1/1. Kết quả:

**∑_{u∈T} price(u) ≤ c(T)·H_t ≤ c(T)·H_d.**

Không cần các tập tối ưu rời nhau để lập luận này đúng.

### 6.3. Cộng phí mà không đếm hai lần

Các tập trong nghiệm tối ưu có thể giao nhau. Để tránh đếm phí một phần tử nhiều lần, **gán mỗi phần tử u∈U cho một tập tối ưu T chứa nó**, theo một quy tắc bất kỳ. Tổng phí của những phần tử được gán cho T không vượt tổng phí toàn T, vì tất cả phí đều không âm.

Từ đó:

**ALG = ∑_u price(u) ≤ ∑_{T∈OPT} c(T)·H_|T| ≤ H_d∑_{T∈OPT}c(T) = H_d·OPT.**

Đây là chứng minh cho cả bản weighted và unweighted. Yếu tố mấu chốt là **tập tối ưu bất kỳ vẫn là ứng viên** ở mỗi bước, nên greedy không thể có tỷ lệ tệ hơn tỷ lệ của chính tập ấy trên những phần tử còn thiếu.

### 6.4. Tại sao H_d có dạng logarithm?

Ta có H_d ≤ 1 + ∫₁ᵈ (1/x)dx = 1+ln d. Trực giác là khi một tập tối ưu chỉ còn r phần tử chưa phủ, “giá hợp lý” trên mỗi phần tử có thể tăng tới c(T)/r; tổng qua r=t,t−1,…,1 tạo dãy điều hòa.

Khi d cố định nhỏ, H_d là một hằng số. Khi d tăng, H_d tăng chậm, xấp xỉ ln d+γ. Tuy nhiên “tăng chậm” vẫn khác với bảo đảm hằng số độc lập kích thước trên mọi Set Cover tổng quát.

### 6.5. Điều kiện của định lý

- Phải tồn tại phủ đầy đủ.
- Chi phí phải dương (bản unweighted chi phí 1).
- Greedy phải chọn **đúng tỷ lệ cost/new-gain nhỏ nhất** ở mỗi vòng, hoặc gain lớn nhất khi mọi cost=1.
- Tập S_i được biểu diễn/đánh giá gain đúng, không bỏ sót lựa chọn.
- Nếu dùng heuristic “chọn tập lớn nhất theo size ban đầu”, hoặc thêm ràng buộc xung đột/budget mà không xét lại chứng minh, **không** được tự nhận bảo đảm H_d này.

## 7. Ý nghĩa thực tiễn của bảo đảm so với heuristic

Một **heuristic** là quy tắc chọn có thể hiệu quả trong thực tế nhưng không nhất thiết đi kèm một cận gần-optimum cho mọi instance. Một **approximation algorithm** có thể cũng dùng heuristic tham lam, nhưng nó được đặt trong một bài toán/mô hình đủ rõ để chứng minh **đầu ra khả thi và tỷ lệ chi phí**.

Ví dụ: greedy ratio là xấp xỉ H_d, nhưng “thử 10 lần rồi lấy nghiệm nhỏ nhất” chỉ là kỹ thuật thực nghiệm nếu không có chứng minh riêng. Số vòng thử nhiều không tự tạo ra bảo đảm đúng trên mọi input.

Giữa hai thuật toán, một thuật toán có bảo đảm α thấp hơn về lý thuyết có thể vẫn chạy chậm hơn trên một loại dữ liệu cụ thể. **Hệ số xấp xỉ** và **thời gian chạy** là hai thước đo khác nhau. Cần cân nhắc kích thước n,m, bộ nhớ, cách sinh tập, chi phí truy cập dữ liệu và yêu cầu exact.

### 7.1. Upper bound và lower bound khi đánh giá chất lượng

Một lời giải greedy khả thi cho **upper bound** của OPT: OPT≤ALG. Một cận dưới hợp lệ LB≤OPT có thể giúp đánh giá chất lượng trên instance đang chạy: nếu biết LB>0, ta có ALG/OPT≤ALG/LB. Với bài nhỏ, dùng solver exact tìm OPT để biết tỷ lệ thực tế; với bài lớn, có thể dùng relaxation hoặc dual fitting để tạo LB có chứng minh.

**Không** lấy “một nghiệm từ thuật toán khác” làm lower bound; nghiệm khả thi bất kỳ cũng là upper bound. Cũng không dùng kết quả greedy để tự chứng minh greedy tối ưu.

## 8. Kiểm tra tính khả thi trước khi chạy

Nếu tồn tại u∈U không thuộc bất kỳ S_i, không có cách chọn tập nào phủ U. Kiểm tra **hợp của toàn bộ họ tập** có bằng U hay không là điều kiện cần và đủ cho tính khả thi của Set Cover chuẩn khi được phép chọn tất cả các tập: nếu hợp toàn bộ không đủ thì bất khả thi; nếu đủ thì chọn toàn bộ là một nghiệm.

Các trường hợp phải xử lý rõ:

| Trường hợp | Kết quả |
|---|---|
| U=∅ | Có nghiệm, chi phí 0, chọn 0 tập |
| U≠∅, không có tập nào | Không thể phủ |
| Có phần tử không xuất hiện trong bất kỳ tập | Không thể phủ |
| Các tập rỗng | Gain 0, bỏ qua khi còn phần tử chưa phủ |
| Các tập bị trùng nội dung | Vẫn có thể chọn, nhưng greedy chỉ cần lựa chọn giúp phủ mới |
| Một tập bằng U | Nếu chi phí phù hợp, greedy có thể chọn ngay; optimum có thể khác trong bản weighted |
| Tất cả tập có chi phí bằng 1 | Weighted greedy trở thành unweighted |
| Chi phí 0 hoặc âm | Ngoài hợp đồng c_i>0 của chương trình/định lý ở đây |
| Đầu vào có phần tử ngoài U | Phải từ chối hoặc chuẩn hóa rõ ràng, không âm thầm bỏ qua |

**Tie-breaking:** nếu hai tập có cùng score, có thể chọn chỉ số nhỏ hơn để có stdout xác định. Không cần bảo đảm thuật toán luôn sinh cùng tập khi đầu vào đổi thứ tự; chỉ cần bảo đảm tập chọn phủ U và chi phí thỏa định lý.

## 9. Độ phức tạp của một cài đặt đơn giản

Giả sử n=|U|, m số tập, w kích thước từ máy khi dùng bitset. Mỗi vòng greedy tính lại gain bằng giao với tập chưa phủ, tốn khoảng O(n/w) thao tác trên từng tập khi biểu diễn bitset; quét m tập mất O(m·n/w). Mỗi vòng chọn tập có ít nhất một phần tử chưa phủ, nên có tối đa min(n,m) vòng.

Thời gian cài đặt **quét lại toàn bộ** là khoảng **O(m·min(n,m)·⌈n/w⌉)** phép toán theo từ máy, cộng chi phí quản lý đối tượng và bitset. Bộ nhớ lưu các tập là O(m·⌈n/w⌉) từ, cộng O(n/w) cho tập chưa phủ.

Khi m hoặc n lớn, có thể dùng inverted index từ phần tử sang các tập chứa nó, cấu trúc ưu tiên với cập nhật gain/lazy reevaluation, hoặc xử lý dữ liệu thưa để tránh quét lại mọi tập. Khi cập nhật score, phải giữ đúng tỷ lệ cost/gain **hiện tại**; heap lưu gain cũ mà không kiểm lại có thể mất tính greedy chuẩn và không còn chứng minh H_d.

### 9.1. Exact brute force và exact DP trên input nhỏ

Duyệt mọi nhóm tập có 2^m lựa chọn; mỗi lựa chọn kiểm hợp tập và tổng cost, nên thời gian mũ theo m. Với n nhỏ, có DP mặt nạ phần tử:

**dp[mask] = chi phí thấp nhất để phủ được ít nhất các phần tử trong mask**.

Khởi tạo dp[0]=0; lần lượt xét mỗi tập S_i, cho phép bỏ qua hoặc chọn nó một lần, cập nhật:

**next[mask ∪ S_i] = min(next[mask ∪ S_i], dp[mask]+c_i).**

Sau khi xét hết m tập, dp[full] là OPT nếu hữu hạn. Độ phức tạp O(m·2^n) thời gian, O(2^n) bộ nhớ bằng hai lớp mảng. Vì n≤18 trong mã kiểm thử, DP đủ nhanh để làm **oracle độc lập** cho brute force theo nhóm tập.

### 9.2. Greedy và solver exact có vai trò khác nhau

Greedy tạo lời giải nhanh và có cận α cho mọi instance hợp lệ; solver exact dành cho dữ liệu đủ nhỏ/có cấu trúc phù hợp hoặc cần chứng minh optimum. Có thể dùng chi phí greedy làm **upper bound** để branch-and-bound cắt tỉa, nhưng cần một lower bound hợp lệ mới được loại nhánh.

## 10. Tập phủ có chi phí và thực tế dữ liệu

Trong những bài ứng dụng, chi phí mua một tài nguyên có thể không cộng độc lập hoặc một nhà cung cấp có ràng buộc loại trừ với nhà khác. Nếu “chọn A thì phải chọn B”, hoặc “A và B không được cùng chọn”, bài toán đã **khác Set Cover chuẩn** và định lý H_d không tự áp dụng.

Đôi khi phần tử của U có **mức độ quan trọng khác nhau**; nếu chỉ cần phủ một phần U dưới ngân sách, mô hình gần với weighted Maximum Coverage/budgeted coverage, không phải min-cost Set Cover. Bảo đảm greedy chuẩn của Maximum Coverage theo ràng buộc số tập là **1−1/e** cho bài toán tối đa hóa thích hợp, khác với bảo đảm **H_d** của Set Cover tối thiểu hóa. Không tráo hai con số.

Khi phần tử có thể được phủ nhiều lần để tăng độ tin cậy, hoặc cần phủ **ít nhất r lần**, ta đang ở các biến thể Set Multicover; cần phân tích và thuật toán tương ứng, không âm thầm dùng chứng minh Set Cover một lần.

## 11. Ví dụ phân tích bằng phương pháp “tính phí”

Trở lại U={1,…,6} với A,B,C chi phí 1. Greedy chọn A (gain 4), gán phí 1/4 cho các phần tử 1,2,3,4. Sau đó B (gain 1) gán phí 1 cho phần tử 5, và C (gain 1) gán phí 1 cho phần tử 6:

| Phần tử | Tập đầu tiên phủ | Phí |
|---:|---|---:|
| 1 | A | 1/4 |
| 2 | A | 1/4 |
| 3 | A | 1/4 |
| 4 | A | 1/4 |
| 5 | B | 1 |
| 6 | C | 1 |

Tổng phí = 4·(1/4)+1+1=3, chính là tổng số tập greedy. Với tập tối ưu B={1,2,5} có t=3, tổng phí trên B là 1/4+1/4+1=1,5≤H₃·1≈1,8333. Với C={3,4,6}, tổng phí cũng 1,5≤H₃.

Tổng phí của B và C bằng 3, đúng bằng ALG ở ví dụ này vì hai tập tối ưu rời nhau. Trong trường hợp có giao nhau, tổng phí từng tập tối ưu sẽ đếm đôi các phần tử giao; để chứng minh tổng quát, ta gán mỗi u cho một tập tối ưu chứa nó như mục 6.3.

## 12. Phân biệt những câu hỏi thường bị đánh đồng

**“Greedy có bảo đảm H_d thì có luôn tốt trong thực tế không?”** Định lý nói **không vượt quá H_d lần OPT**; đó là mức trần lý thuyết, không phải dự đoán phân phối chất lượng trên dữ liệu thực.

**“Tỷ số 1,5 ở một ví dụ có chứng minh greedy là 1,5-approximation?”** Không. Phải chứng minh tỷ lệ ≤1,5 trên **mọi instance** của lớp bài toán; một hoặc nhiều ví dụ chỉ là quan sát.

**“H_n và H_d có mâu thuẫn?”** Không. Vì d≤n nên H_d≤H_n. Bảo đảm H_n yếu hơn nhưng vẫn đúng.

**“Greedy có thể chọn một tập hai lần không?”** Một tập đã chọn không còn gain mới; chọn lại không giúp phủ thêm gì và chỉ tăng chi phí dương. Cài đặt đúng bỏ qua gain=0.

**“Có thể kết luận một nghiệm là tối ưu từ bảo đảm H_d?”** Không. Cận chỉ là ALG≤H_d·OPT; để xác nhận optimality, cần một chứng chỉ lower bound khớp ALG hoặc solver exact/định lý cấu trúc riêng.

**“Cận có áp dụng khi một phần tử không phủ được không?”** Không. Trường hợp bất khả thi phải trả trạng thái riêng; không có OPT hữu hạn để lấy tỷ số.

## 13. Phác thảo pseudocode tích hợp weighted/unweighted

```text
greedySetCover(U, sets, cost):
    remaining = U
    choice = []
    total = 0
    while remaining not empty:
        best = NONE
        for i in 0 .. m-1:
            gain_i = size(sets[i] ∩ remaining)
            if gain_i == 0: continue
            if best is NONE or cost[i]/gain_i < cost[best]/gain_best:
                best = i
        if best is NONE:
            return IMPOSSIBLE
        choice.append(best)
        total += cost[best]
        remaining -= sets[best]
    return (choice,total)

unweighted:
    mọi cost[i] = 1
    => score nhỏ nhất <=> gain lớn nhất
```

Tùy yêu cầu, có thể loại tập rỗng và các tập trùng để tối ưu. Nhưng khi tập trùng có chi phí khác nhau, không được chỉ xóa bản trùng tùy ý rồi giữ bản **đắt hơn**; một tiền xử lý đúng phải giữ tối thiểu bản rẻ hoặc chứng minh một tập bị thống trị (dominated) trước khi bỏ.



## 14. Java 17 hoàn chỉnh: greedy, oracle exact và kiểm bảo đảm

Chương trình một tệp dưới đây cài **greedy chung cho cả bản không trọng số và có trọng số**, sử dụng `java.util.BitSet` cho tập phần tử, so sánh score chi phí/gain bằng tích chéo `long`, trả `IMPOSSIBLE` dưới dạng kết quả `possible=false` khi không thể phủ.

Nó còn có **hai oracle exact độc lập** cho instance nhỏ: duyệt toàn bộ nhóm tập (`2^m`) và DP trên mặt nạ phần tử đã phủ (`m·2^n`). Cuối cùng chương trình kiểm trên dữ liệu ngẫu nhiên rằng greedy tạo lời giải khả thi với chi phí từ OPT đến H_d·OPT, không áp tỷ số khi U rỗng hoặc vô nghiệm.

Lưu mã nguồn với tên `GreedySetCoverDemo.java`, biên dịch bằng JDK 17 trở lên:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.Locale;
import java.util.Random;

public final class GreedySetCoverDemo {
    private GreedySetCoverDemo() {}

    // Domain: elements 0..universeSize-1, integer costs 1..1e6.
    static final class Instance {
        final int n;
        final BitSet[] sets;
        final int[] cost;

        Instance(int universeSize, BitSet[] input, int[] weights) {
            if (universeSize < 0 || universeSize > 2000
                    || input == null || weights == null
                    || input.length != weights.length) {
                throw new IllegalArgumentException("invalid instance");
            }
            n = universeSize;
            sets = new BitSet[input.length];
            cost = weights.clone();

            for (int i = 0; i < input.length; i++) {
                if (input[i] == null || input[i].length() > n
                        || cost[i] < 1 || cost[i] > 1_000_000) {
                    throw new IllegalArgumentException(
                        "invalid set or positive cost"
                    );
                }
                sets[i] = (BitSet) input[i].clone();
            }
        }
    }

    record Solution(boolean possible, int[] selected, long totalCost) {}

    static BitSet bits(int... indices) {
        BitSet b = new BitSet();
        for (int x : indices) {
            if (x < 0) throw new IllegalArgumentException("negative item");
            b.set(x);
        }
        return b;
    }

    static boolean coverable(Instance in) {
        BitSet union = new BitSet(in.n);
        for (BitSet set : in.sets) union.or(set);
        return union.cardinality() == in.n;
    }

    // Exact weighted greedy: minimize cost[i]/newlyCoveredCount.
    // Compare positive ratios by long cross multiplication.
    static Solution greedy(Instance in) {
        BitSet uncovered = new BitSet(in.n);
        uncovered.set(0, in.n);
        ArrayList<Integer> picks = new ArrayList<>();
        long totalCost = 0;

        while (!uncovered.isEmpty()) {
            int best = -1, bestGain = 0;

            for (int i = 0; i < in.sets.length; i++) {
                BitSet newItems = (BitSet) in.sets[i].clone();
                newItems.and(uncovered);
                int gain = newItems.cardinality();
                if (gain == 0) continue;

                if (best == -1 ||
                    (long) in.cost[i] * bestGain
                      < (long) in.cost[best] * gain) {
                    best = i;
                    bestGain = gain;
                }
                // Equal ratio keeps the first index: deterministic tie.
            }

            if (best == -1) {
                return new Solution(false, new int[0], -1);
            }
            picks.add(best);
            totalCost += in.cost[best];
            uncovered.andNot(in.sets[best]);
        }

        int[] selected = new int[picks.size()];
        for (int i = 0; i < picks.size(); i++) {
            selected[i] = picks.get(i);
        }
        return new Solution(true, selected, totalCost);
    }

    // Exact oracle 1: enumerate all subfamilies (m<=18).
    static long exactBySubsets(Instance in) {
        if (in.sets.length > 18 || in.n > 18) {
            throw new IllegalArgumentException("small instances only");
        }
        long best = Long.MAX_VALUE;
        int totalMasks = 1 << in.sets.length;

        for (int mask = 0; mask < totalMasks; mask++) {
            BitSet covered = new BitSet(in.n);
            long sum = 0;

            for (int i = 0; i < in.sets.length; i++) {
                if ((mask & (1 << i)) == 0) continue;
                sum += in.cost[i];
                covered.or(in.sets[i]);
            }
            if (covered.cardinality() == in.n && sum < best) {
                best = sum;
            }
        }
        return best == Long.MAX_VALUE ? -1 : best;
    }

    // Exact oracle 2: DP indexed by covered-element masks.
    // Costs are positive, each set may be selected 0 or 1 time.
    static long exactByCoveredMaskDp(Instance in) {
        if (in.n > 18 || in.sets.length > 18) {
            throw new IllegalArgumentException("small instances only");
        }
        int states = 1 << in.n;
        int[] masks = new int[in.sets.length];

        for (int i = 0; i < in.sets.length; i++) {
            for (int x = in.sets[i].nextSetBit(0);
                    x >= 0; x = in.sets[i].nextSetBit(x + 1)) {
                masks[i] |= 1 << x;
            }
        }

        final long inf = Long.MAX_VALUE / 4;
        long[] dp = new long[states];
        Arrays.fill(dp, inf);
        dp[0] = 0;

        for (int i = 0; i < in.sets.length; i++) {
            long[] next = dp.clone();
            for (int covered = 0; covered < states; covered++) {
                if (dp[covered] == inf) continue;
                int newMask = covered | masks[i];
                next[newMask] = Math.min(
                    next[newMask], dp[covered] + in.cost[i]
                );
            }
            dp = next;
        }
        return dp[states - 1] == inf ? -1 : dp[states - 1];
    }

    static double harmonic(int d) {
        double sum = 0;
        for (int k = 1; k <= d; k++) sum += 1.0 / k;
        return sum;
    }

    static int maxSize(Instance in) {
        int max = 0;
        for (BitSet set : in.sets) {
            max = Math.max(max, set.cardinality());
        }
        return max;
    }

    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    static void verifyCertificate(Instance in, Solution answer) {
        if (!answer.possible()) {
            check(!coverable(in), "claimed impossible but cover exists");
            check(answer.totalCost() == -1,
                "impossible code is not -1");
            return;
        }

        boolean[] seen = new boolean[in.sets.length];
        BitSet union = new BitSet(in.n);
        long sum = 0;

        for (int index : answer.selected()) {
            check(index >= 0 && index < in.sets.length,
                "selected index out of range");
            check(!seen[index], "set selected twice");
            seen[index] = true;
            union.or(in.sets[index]);
            sum += in.cost[index];
        }
        check(union.cardinality() == in.n,
            "not all universe elements covered");
        check(sum == answer.totalCost(), "wrong reported cost");
    }

    static void verifyApproximation(Instance in) {
        long exact = exactBySubsets(in);
        long dp = exactByCoveredMaskDp(in);
        check(exact == dp, "two exact oracles disagree");

        Solution answer = greedy(in);
        verifyCertificate(in, answer);

        if (exact == -1) {
            check(!answer.possible(), "impossible case misclassified");
            return;
        }

        check(answer.possible(), "feasible case rejected");
        if (exact == 0) {
            check(in.n == 0 && answer.totalCost() == 0,
                "empty universe mishandled");
            return; // Do not divide 0/0 to make a ratio.
        }

        int d = maxSize(in);
        check(answer.totalCost() >= exact,
            "a feasible result beats the true optimum");
        check(answer.totalCost()
                <= harmonic(d) * exact + 1e-9,
            "harmonic approximation bound violated");
    }

    public static void main(String[] args) {
        BitSet[] sets = {
            bits(0, 1, 2, 3), // A = {1,2,3,4}
            bits(0, 1, 4),    // B = {1,2,5}
            bits(2, 3, 5)     // C = {3,4,6}
        };

        Instance unweighted = new Instance(
            6, sets, new int[] {1, 1, 1});
        Instance weighted = new Instance(
            6, sets, new int[] {10, 3, 3});

        Solution u = greedy(unweighted);
        Solution w = greedy(weighted);
        long optU = exactBySubsets(unweighted);
        long optW = exactBySubsets(weighted);

        System.out.println(
            "Unweighted greedy: " + Arrays.toString(u.selected())
                + ", cost=" + u.totalCost()
        );
        System.out.println("Unweighted optimum: " + optU);
        System.out.printf(Locale.ROOT,
            "Ratio greedy/OPT: %.3f%n",
            (double) u.totalCost() / optU);
        System.out.printf(Locale.ROOT,
            "H_4: %.3f%n", harmonic(4));

        System.out.println(
            "Weighted greedy: " + Arrays.toString(w.selected())
                + ", cost=" + w.totalCost()
        );
        System.out.println("Weighted optimum: " + optW);

        Instance impossible = new Instance(
            3, new BitSet[] {bits(0), bits(1)},
            new int[] {1, 1});
        System.out.println(
            "Impossible: " + !greedy(impossible).possible()
        );

        Instance empty = new Instance(
            0, new BitSet[0], new int[0]);
        System.out.println(
            "Empty universe cost: " + greedy(empty).totalCost()
        );

        verifyApproximation(unweighted);
        verifyApproximation(weighted);
        verifyApproximation(impossible);
        verifyApproximation(empty);

        Random random = new Random(473L);

        for (int trial = 0; trial < 900; trial++) {
            int n = random.nextInt(9);
            int m = random.nextInt(11);
            BitSet[] randomSets = new BitSet[m];
            int[] unweightedCosts = new int[m];
            int[] weightedCosts = new int[m];

            for (int i = 0; i < m; i++) {
                BitSet subset = new BitSet(n);
                for (int x = 0; x < n; x++) {
                    if (random.nextBoolean()) subset.set(x);
                }
                randomSets[i] = subset;
                unweightedCosts[i] = 1;
                weightedCosts[i] = 1 + random.nextInt(20);
            }

            verifyApproximation(new Instance(
                n, randomSets, unweightedCosts));
            verifyApproximation(new Instance(
                n, randomSets, weightedCosts));
        }

        System.out.println("Random unweighted: 900 PASS");
        System.out.println("Random weighted: 900 PASS");
    }
}
```

### 14.1. Lệnh chạy

```bash
javac -encoding UTF-8 GreedySetCoverDemo.java
java GreedySetCoverDemo
```

**Đầu ra xác định:**

```text
Unweighted greedy: [0, 1, 2], cost=3
Unweighted optimum: 2
Ratio greedy/OPT: 1.500
H_4: 2.083
Weighted greedy: [1, 2], cost=6
Weighted optimum: 6
Impossible: true
Empty universe cost: 0
Random unweighted: 900 PASS
Random weighted: 900 PASS
```

### 14.2. Cách đọc kết quả và tính đúng của mã

- Các chỉ số 0,1,2 trong dòng unweighted là A,B,C; greedy chọn A trước vì gain 4, sau đó B,C có gain 1 để hoàn tất. OPT chọn B,C: 2 tập.
- Với chi phí A=10,B=3,C=3, greedy weighted chọn B,C và tổng chi phí 6. Tính theo gain thuần túy trong ví dụ weighted sẽ chọn A trước; đó là sai quy tắc có chứng minh.
- Dòng `H_4: 2.083` chỉ biểu diễn cận hài hòa làm tròn ba chữ số. Nó **không** phải tỷ số đạt được; tỷ số instance unweighted là 1.5.
- `Impossible: true` cho trường hợp U={0,1,2}, tập {0} và {1}, phần tử 2 không thể phủ; không có OPT hữu hạn.
- `Empty universe cost: 0` là nghiệm rỗng; chương trình không in tỷ số 0/0.
- `verifyCertificate` tính lại hợp các tập được chọn, kiểm chỉ số, không lặp lựa chọn và tổng chi phí. Vì vậy “greedy” không chỉ kiểm một con số, mà phải tạo **phủ khả thi**.
- `verifyApproximation` so hai oracle exact. Với case có OPT>0, nó kiểm `OPT<=ALG<=H_d·OPT`. Cận được so bằng double với sai số rất nhỏ vì bộ thử có n,m và cost nhỏ; định lý thật được chứng minh ở mục 6, không dựa vào epsilon của test.

### 14.3. Kiểm thử ngẫu nhiên và oracle

Bộ thử dùng `Random(473L)` để tạo **900** cấu hình có vũ trụ 0..8 phần tử và 0..10 tập. Trên cùng mỗi cấu hình tập con, nó chạy một lần với toàn bộ chi phí 1 và một lần với chi phí nguyên ngẫu nhiên từ 1..20.

Như vậy có **900 ca unweighted** và **900 ca weighted**, bao gồm tập rỗng, vũ trụ rỗng, tập con chồng lấn, có thể bất khả thi và nhiều trường hợp có nhiều nghiệm tối ưu. Mỗi ca đối chiếu:

1. Kết quả exact chọn tập bằng brute force.
2. Kết quả exact DP trên các phần tử đã phủ.
3. Tính khả thi của lời giải greedy, chi phí được tính lại và giới hạn H_d nếu OPT>0.

**Phép kiểm ngẫu nhiên không thay thế chứng minh toán học**; nó có thể bắt lỗi implementation. Số ca kiểm cũng không nên hiểu là xác suất thất bại của bảo đảm xấp xỉ.

### 14.4. Giới hạn dữ liệu và tính bất biến

Trong mã Java, vũ trụ có thể có 0..2000 phần tử để minh họa sử dụng BitSet; chi phí mỗi tập là số nguyên trong 1..1_000_000. Mọi phần tử đặt bit trong BitSet phải nằm trong [0,n). Constructor **sao chép** mảng giá và clone các BitSet để tránh việc caller sửa nội dung instance giữa hai phép tính.

Chỉ hai solver exact mới yêu cầu n≤18, m≤18, vì chúng dùng 2^n/2^m và mặt nạ int. Greedy có thể chạy trên instance lớn hơn trong giới hạn cho phép. Không suy luận rằng giới hạn 18 của oracle là giới hạn của Set Cover lý thuyết.

Khi so tỷ lệ, mã không thực hiện phép chia double: nó dùng tích chéo có kiểm bound chi phí trước, tránh rounding quyết định chọn tập. Với m rất lớn, BitSet có kích thước n lớn, thời gian quét lại có thể đáng kể; đây là cài đặt sư phạm ưu tiên minh bạch thay vì thiết kế tốc độ cực đại.

## 15. Bài tập thực hành có đáp án

**Bài 1.** Nêu mục tiêu Set Cover không trọng số. *Đáp án:* chọn ít tập nhất sao cho hợp các tập được chọn là U.

**Bài 2.** Trong Set Cover weighted, hàm mục tiêu là gì? *Đáp án:* tối thiểu tổng chi phí các tập được chọn, với mọi phần tử của U được phủ.

**Bài 3.** Gain của S_i ở một bước là gì? *Đáp án:* |S_i∩R|, số phần tử trong S_i chưa được phủ.

**Bài 4.** Vì sao không chọn theo |S_i| ban đầu? *Đáp án:* nhiều phần tử có thể đã được phủ, không mang lợi ích mới.

**Bài 5.** Greedy không trọng số chọn theo tiêu chí nào? *Đáp án:* gain lớn nhất, bỏ gain=0.

**Bài 6.** Greedy có trọng số chọn theo tiêu chí nào? *Đáp án:* c_i/gain_i nhỏ nhất.

**Bài 7.** Khi toàn bộ chi phí bằng 1, hai quy tắc greedy quan hệ thế nào? *Đáp án:* tương đương.

**Bài 8.** Với U={1..6}, A={1,2,3,4}, B={1,2,5}, C={3,4,6}, greedy chọn đầu tiên tập nào? *Đáp án:* A.

**Bài 9.** Ví dụ đó greedy chọn bao nhiêu tập? *Đáp án:* 3 tập.

**Bài 10.** Nghiệm tối ưu ví dụ đó là tập nào? *Đáp án:* B và C, chi phí 2.

**Bài 11.** Tỷ số thực tế trong ví dụ unweighted? *Đáp án:* 3/2=1,5.

**Bài 12.** Với d=4, H_d bằng phân số nào? *Đáp án:* 1+1/2+1/3+1/4=25/12.

**Bài 13.** Ý nghĩa α-approximation cho minimization? *Đáp án:* OPT≤ALG≤α·OPT trên mọi instance khả thi thuộc phạm vi bảo đảm.

**Bài 14.** α=2 có nghĩa xác suất sai là 50% không? *Đáp án:* không, đó là cận tỷ lệ chi phí.

**Bài 15.** Tại sao H_d≤H_n? *Đáp án:* d=max |S_i|≤|U|=n và số hài hòa tăng theo d.

**Bài 16.** H_d tăng theo hàm gì khi d lớn? *Đáp án:* O(log d), cụ thể ≤1+ln d.

**Bài 17.** Trong chứng minh tính phí, phí mỗi phần tử mới phủ tại một vòng? *Đáp án:* cost của tập được chọn chia cho gain của vòng đó.

**Bài 18.** Tổng phí trên toàn U bằng gì? *Đáp án:* tổng chi phí greedy.

**Bài 19.** Vì sao ở một bước greedy score≤c(T)/r với một tập tối ưu T còn r phần tử? *Đáp án:* T là ứng viên hiện tại với gain r và greedy lấy score nhỏ nhất.

**Bài 20.** Khi các tập tối ưu giao nhau, tránh tính phí hai lần thế nào? *Đáp án:* gán mỗi phần tử cho một tập tối ưu chứa nó.

**Bài 21.** U rỗng có OPT bao nhiêu? *Đáp án:* 0 và không chọn tập nào.

**Bài 22.** Nếu một phần tử không thuộc tập nào thì trả gì? *Đáp án:* bất khả thi, không tính tỷ số xấp xỉ.

**Bài 23.** Tập đã chọn có thể được chọn lại để tăng phủ không? *Đáp án:* không, gain mới là 0.

**Bài 24.** Trong weighted ví dụ A=10 B=C=3, greedy chọn gì? *Đáp án:* B,C với tổng chi phí 6.

**Bài 25.** Trong ví dụ weighted A={1,2,3} cost4, B={1,2} cost3, C={3,4} cost3, greedy/OPT? *Đáp án:* 7/6.

**Bài 26.** Greedy ratio có chắc tìm được optimum nếu α gần 1? *Đáp án:* không, muốn xác nhận optimum cần lower bound hoặc exact solver.

**Bài 27.** Với Set Cover n nhỏ, DP mask tốn khoảng bao nhiêu trạng thái? *Đáp án:* 2^n.

**Bài 28.** Với m nhỏ, brute force chọn họ tập có bao nhiêu phương án? *Đáp án:* 2^m.

**Bài 29.** Greedy Set Cover và Maximum Coverage có cùng hệ số không? *Đáp án:* không; bài thứ hai có mục tiêu/giới hạn và định lý riêng.

**Bài 30.** Nếu bảng kết quả ghi greedy=12, một nghiệm khả thi khác cost=10, có chắc OPT=10? *Đáp án:* không, 10 là upper bound của OPT, có thể còn nghiệm tốt hơn.

## 16. Checklist triển khai và đánh giá

1. Xác định U, từng S_i, giá c_i và kiểm tính khả thi của việc phủ toàn bộ U.
2. Phân biệt Set Cover với Exact Cover, Vertex Cover, Maximum Coverage và Set Multicover.
3. Xác nhận mục tiêu không trọng số (ít tập) hay có trọng số (ít tổng cost).
4. Mỗi vòng tính gain bằng số phần tử **chưa phủ**, không dùng size ban đầu.
5. Weighted chọn tỷ lệ **cost/gain nhỏ nhất**, bỏ tập gain=0.
6. Có quy tắc hòa rõ ràng để dễ tái hiện/kiểm thử.
7. Không chọn cùng một tập nhiều lần và không bỏ thiếu phần tử U.
8. Với chi phí nguyên, so tỷ lệ bằng tích chéo đủ rộng, tránh overflow.
9. Nếu U=∅, trả nghiệm rỗng cost 0 và không lấy 0/0.
10. Nếu không thể phủ, trả trạng thái riêng và không tính approximation ratio.
11. Ghi rõ d=max |S_i|, tính H_d, tránh nhầm với H_n hoặc ln n.
12. Đánh giá **ALG/OPT** khi biết OPT exact, phân biệt với cận lý thuyết H_d.
13. Không gọi greedy “optimal” nếu chỉ có bảo đảm logarithmic.
14. Khi có chi phí/ràng buộc mới, kiểm lại điều kiện chứng minh approximation.
15. Kiểm bằng brute-force hoặc DP độc lập trên input nhỏ, gồm dữ liệu rỗng, bất khả thi và nhiều giá trị trùng.
16. Phân tích cả thời gian quét lại m tập lẫn bộ nhớ BitSet; tối ưu cấu trúc dữ liệu nếu n,m lớn.

## Kết luận

**Set Cover greedy** giải bài toán phủ mọi phần tử bằng cách chọn ở mỗi bước tập phủ được nhiều phần tử mới nhất (không trọng số), hoặc có **chi phí trên mỗi phần tử mới** thấp nhất (có trọng số). Đây là thuật toán nhanh, tạo lời giải khả thi khi bài toán khả thi, nhưng không luôn đạt optimum.

**Bảo đảm xấp xỉ H_d** có nghĩa tổng chi phí greedy **không lớn hơn H_d lần tối ưu** cho mọi instance hợp lệ, với d là kích thước tập lớn nhất. Chứng minh “tính phí” cho từng phần tử mới phủ giải thích tại sao tổng chi phí greedy bị chặn bởi tổng các số hài hòa trên các tập tối ưu.

Đừng đánh đồng bảo đảm xấp xỉ với tỷ lệ thực nghiệm, xác suất thành công hay tính tối ưu tuyệt đối. Khi yêu cầu lời giải exact, dùng solver exact/DP phù hợp; khi ưu tiên tốc độ trên dữ liệu lớn, dùng greedy cùng cận toán học và kiểm đầy đủ trạng thái rỗng, bất khả thi, chi phí và số lượng phần tử đã phủ.
