# Bảo đảm xấp xỉ cho bài toán cực tiểu và cực đại

Một **thuật toán xấp xỉ có bảo đảm (approximation algorithm with guarantee)** là thuật toán tạo ra lời giải khả thi và có một **cận toán học về chất lượng lời giải** so với giá trị tối ưu của bài toán. Thuật toán có thể không tìm ra nghiệm tốt nhất, nhưng chứng minh cho biết lời giải **không tệ hơn mức đã cam kết** trên mọi đầu vào thỏa giả thiết.

Điểm dễ nhầm nhất là **chiều bất đẳng thức phụ thuộc mục tiêu**:

- Với **cực tiểu (minimization)**, kết quả khả thi ALG thường **không nhỏ hơn** OPT. Bảo đảm hệ số ρ≥1 có dạng **OPT≤ALG≤ρ·OPT**, khi hàm mục tiêu và điều kiện tỷ số cho phép.
- Với **cực đại (maximization)**, kết quả khả thi ALG thường **không lớn hơn** OPT. Bảo đảm theo phần giữ lại β∈(0,1] có dạng **β·OPT≤ALG≤OPT**, khi các giá trị mục tiêu không âm.
- Nếu muốn dùng cùng một hệ số ρ≥1 cho cực đại, có thể viết **OPT/ρ≤ALG≤OPT**, tương đương β=1/ρ trên các instance có OPT>0.

Bảo đảm xấp xỉ **khác với quan sát benchmark** rằng nghiệm thường “khá tốt”. Nó cũng **khác với tính gần đúng số thực**: một thuật toán xấp xỉ có thể tính chính xác mọi phép toán số học nhưng chủ động chọn nghiệm tối ưu gần đúng để tiết kiệm thời gian.

Bài thuộc nhóm **Xấp xỉ và kinh nghiệm**, trình bày: định nghĩa chính thức, chiều tỷ số cho min/max, trường hợp OPT=0 hoặc âm, bảo đảm cộng/tương đối, chứng minh qua cận dưới/cận trên, hai thuật toán minh họa cổ điển (**2-approximation Vertex Cover** và **greedy Maximum Coverage**), các lớp PTAS/FPTAS, heuristic, randomized approximation, cách kiểm thử với oracle tối ưu và mã **Java 17+ độc lập**.

## 1. Trước hết phải định nghĩa bài toán tối ưu

Bài toán tối ưu không chỉ là một hàm số. Một đặc tả đầy đủ gồm:

1. **Tập dữ liệu đầu vào hợp lệ** I.
2. **Tập nghiệm khả thi** F(I) đối với mỗi input I.
3. **Hàm mục tiêu** c(I,s) được tính với nghiệm s∈F(I).
4. **Chiều tối ưu:** cực tiểu hoặc cực đại.

Đối với cực tiểu:

**OPT(I)=min{c(I,s):s∈F(I)}**.

Đối với cực đại:

**OPT(I)=max{c(I,s):s∈F(I)}**.

Giả sử cực trị hữu hạn và đạt được; nếu không, bài cần mô tả riêng trường hợp không có nghiệm, unbounded hoặc chỉ có infimum/supremum.

Thuật toán A nhận I và trả một nghiệm **s_A(I)∈F(I)**. Giá trị được gọi là:

**ALG(I)=c(I,s_A(I))**.

**Bảo đảm xấp xỉ chỉ có ý nghĩa nếu nghiệm trả về khả thi.** Một nghiệm cực tiểu có chi phí thấp bất thường vì bỏ qua ràng buộc không được coi là nghiệm gần tối ưu.

### Ví dụ bài toán phủ đỉnh

Cho đồ thị vô hướng G=(V,E), tìm tập đỉnh C sao cho **mỗi cạnh (u,v) có u∈C hoặc v∈C**, và cực tiểu hóa |C|. Đây là **Minimum Vertex Cover**.

Một tập rất nhỏ nhưng bỏ sót cạnh là **không khả thi**, dù giá trị |C| thấp hơn tối ưu.

### Ví dụ bài toán phủ tối đa

Cho một tập vũ trụ U, các tập con S₀,...,Sₘ₋₁ và ngân sách k, chọn tối đa k tập sao cho **số phần tử khác nhau được phủ là lớn nhất**. Đây là **Maximum Coverage với cardinality budget**.

Chọn k+1 tập có thể phủ nhiều phần tử hơn, nhưng **vi phạm ngân sách** và không phải nghiệm hợp lệ.

## 2. Bảo đảm cho cực tiểu: hệ số càng gần 1 càng tốt

Với bài toán min có **OPT>0**, tỷ số lời giải:

**r_min(I)=ALG(I)/OPT(I)**.

Vì ALG là giá trị một nghiệm khả thi và OPT là nhỏ nhất:

**r_min(I)≥1**.

Thuật toán có **bảo đảm ρ-approximation** nếu trên mọi instance hợp lệ trong phạm vi xét:

**ALG(I)≤ρ·OPT(I)**,

với **ρ≥1**.

Ví dụ nếu OPT=10:

- ALG=10 ⇒ tỷ số 1, đạt tối ưu.
- ALG=12 ⇒ tỷ số 1.2.
- ALG=20 ⇒ tỷ số 2.
- ALG=100 ⇒ tỷ số 10, không thỏa bảo đảm 2.

**Bảo đảm 2-approx** nghĩa là **ALG không vượt quá hai lần giá trị tối ưu**, không có nghĩa lỗi là “2 đơn vị” hay “2%”.

### Trường hợp cực tiểu hóa chi phí

Nếu mục tiêu là chi phí giao hàng, số đỉnh phủ, tổng trọng số hay số lượng máy, hệ số lớn hơn 1 cho phép trả lời lời giải “cao hơn tối ưu” ở mức giới hạn.

Không được đảo chiều thành ALG≥ρ·OPT rồi gọi đó là bảo đảm: chiều ấy thường chỉ nói nghiệm đang tệ.

## 3. Bảo đảm cho cực đại: phần giữ lại càng gần 1 càng tốt

Với bài toán max có **OPT>0** và giá trị nghiệm không âm:

**r_max(I)=ALG(I)/OPT(I)**.

Vì ALG≤OPT:

**0≤r_max(I)≤1**.

Thuật toán là **β-approximation theo phần giữ lại** nếu:

**ALG(I)≥β·OPT(I)**,

với **0<β≤1**.

Ví dụ nếu OPT=100:

- ALG=100 ⇒ 100% tối ưu.
- ALG=90 ⇒ giữ được 90% giá trị.
- ALG=75 ⇒ giữ được 75% giá trị.
- ALG=60 ⇒ không đạt bảo đảm β=0.75.

Một quy ước khác dùng **hệ số ρ≥1** cho cả min và max:

**OPT(I)≤ρ·ALG(I)**.

Khi ALG>0, điều này tương đương:

**OPT/ALG≤ρ**.

Ví dụ β=0.5 tương đương ρ=2. Vì các tài liệu có thể dùng hai quy ước, khi viết “2-approx cho bài max” phải **nêu công thức**, tránh người đọc hiểu nhầm.

## 4. Bảng nhớ nhanh chiều bất đẳng thức

| Loại bài | Quan hệ mọi nghiệm khả thi | Bảo đảm nhân thông dụng | Ý nghĩa |
| --- | --- | --- | --- |
| Cực tiểu | ALG≥OPT | ALG≤ρ·OPT, ρ≥1 | Nghiệm không đắt quá ρ lần tối ưu |
| Cực đại | ALG≤OPT | ALG≥β·OPT, 0<β≤1 | Thu được ít nhất β phần giá trị tối ưu |
| Cực đại, quy ước ρ | ALG≤OPT | ALG≥OPT/ρ, ρ≥1 | Chênh không quá hệ số ρ |
| Cực tiểu, bảo đảm cộng | ALG≥OPT | ALG≤OPT+ε | Không đội quá ε đơn vị |
| Cực đại, bảo đảm cộng | ALG≤OPT | ALG≥OPT−ε | Không hụt quá ε đơn vị |

**Bảo đảm nhân và bảo đảm cộng không tự thay thế được nhau.** Một chênh lệch 5 đơn vị có thể lớn khi OPT=1, nhưng rất nhỏ khi OPT=1.000.000.

### Khi bài dùng “approximation ratio”

Có hai thông lệ phổ biến:

1. **Tỷ số luôn ≥1:** max{ALG/OPT,OPT/ALG}, nếu hai giá trị dương.
2. **Chất lượng đạt được ở bài max:** ALG/OPT∈[0,1], gọi là tỷ lệ bảo toàn.

Vì vậy cần đọc **định nghĩa trong giáo trình hoặc đề bài**, không chỉ tên “ratio”.

## 5. Trường hợp OPT bằng 0, âm hoặc có nghiệm vô hạn

Tỷ số **ALG/OPT** không xác định nếu OPT=0. Một số bài vẫn có một **bất đẳng thức xấp xỉ có nghĩa** tại OPT=0, nhưng không được viết 0/0=1.

Ví dụ **Minimum Vertex Cover** trên đồ thị không có cạnh:

- OPT=0.
- Thuật toán phủ đỉnh đúng cần có thể trả tập rỗng C=∅, ALG=0.
- Bất đẳng thức ALG≤2OPT trở thành 0≤0, **đúng**.
- Tuy nhiên tỷ số ALG/OPT là 0/0, **không định nghĩa**.

Ví dụ **Maximum Coverage** với k=0:

- Chỉ chọn được 0 tập.
- OPT=ALG=0.
- Bất đẳng thức ALG≥βOPT đúng với mọi β≤1, nhưng 0/0 vẫn không dùng làm số đo thực nghiệm.

### Giá trị âm làm tỷ số trở nên nguy hiểm

Nếu OPT<0, phép chia có thể đổi chiều dấu và tỷ lệ không còn phản ánh chất lượng như dự kiến. Với min, nhân OPT âm với ρ>1 còn cho ngưỡng **nhỏ hơn OPT**, mâu thuẫn với tính khả thi. Với max, việc nói “giữ lại 80% một lợi nhuận âm” cũng mơ hồ.

Cần một định nghĩa đã hiệu chỉnh: ví dụ **bảo đảm cộng**, chênh lệch chuẩn hóa, dịch mục tiêu với cận có chứng minh hoặc một mô hình nonnegative chính xác. **Không tự cộng một hằng số vào mục tiêu rồi giữ nguyên tuyên bố hệ số cũ.**

## 6. Nhân và cộng hằng số với hàm mục tiêu

### Nhân với hằng số dương

Nếu mọi chi phí của bài min được nhân với λ>0, cả ALG và OPT được nhân với λ. Khi OPT>0:

**(λALG)/(λOPT)=ALG/OPT**.

Vì vậy tỷ số nhân giữ nguyên khi đổi đơn vị bằng một hệ số dương chung.

### Cộng cùng một hằng số

Nếu cộng C vào mọi nghiệm:

**ALG'=ALG+C**.

**OPT'=OPT+C**.

Khi đó:

**(ALG+C)/(OPT+C)** thường **khác ALG/OPT**.

Ví dụ bài min:

- OPT=1, ALG=2 ⇒ tỷ số 2.
- Cộng 100 vào mọi chi phí ⇒ OPT'=101, ALG'=102, tỷ số ≈1.0099.

Thuật toán chưa tìm được nghiệm tốt hơn về mặt lựa chọn, nhưng tỷ số mới trông gần 1 hơn.

Tương tự, với bài max OPT=10, ALG=5 thì ALG/OPT=0.5; cộng 100 cho mọi lời giải làm tỷ số thành 105/110≈0.9545.

**Kết luận:** bảo đảm nhân không bất biến dưới phép tịnh tiến giá trị mục tiêu. Khi thiết kế một approximation metric, phải xem giá trị 0 có ngữ nghĩa tự nhiên và dữ liệu có nonnegative không.

## 7. Bảo đảm cho mọi instance khác chất lượng trung bình

Một phát biểu **worst-case 2-approx** có nghĩa:

**Với mọi instance I hợp lệ, ALG(I)≤2OPT(I)**.

Nó không nói rằng phần lớn instance có tỷ số đúng 2. Trên nhiều input, thuật toán có thể trả đúng tối ưu hoặc gần tối ưu hơn nhiều.

Ngược lại, nếu chạy 10.000 input ngẫu nhiên và thấy **tỷ số trung bình 1.03**, đây là bằng chứng **thực nghiệm** về chất lượng trên một phân phối test, không phải chứng minh tỷ số luôn ≤1.03.

### Best-case và worst-case approximation quality

Tỷ số có thể thay đổi theo instance. **Hệ số bảo đảm** là cận cho tình huống bất lợi nhất trong lớp input đã định nghĩa. Một trường hợp đúng tối ưu không làm yếu tố bảo đảm worst-case tự biến thành 1.

### Đừng quên thời gian chạy

Một thuật toán trả lời giải đúng tối ưu có hệ số 1, nhưng nếu tốn **2^n** thời gian thì thường không được gọi là **thuật toán xấp xỉ đa thức hữu ích** trong bối cảnh tối ưu tổ hợp khó.

Trong nghiên cứu approximation algorithms, người ta thường quan tâm **tính đa thức** của thuật toán đồng thời với bảo đảm chất lượng.

## 8. Cận dưới và cận trên như công cụ chứng minh

Nhiều chứng minh xấp xỉ **không cần tính OPT thật** vì OPT có thể rất khó tìm.

Với bài **min**, nếu tìm được một cận dưới LB sao cho:

**LB≤OPT≤ALG**,

và chứng minh:

**ALG≤ρ·LB**,

thì suy ra:

**ALG≤ρ·OPT**.

Với bài **max**, nếu có cận trên UB sao cho:

**ALG≤OPT≤UB**,

và chứng minh:

**ALG≥β·UB**,

thì suy ra:

**ALG≥β·OPT**.

### Chứng nhận sau khi chạy

Cho instance cụ thể, nếu thuật toán min cho ALG=20 và ta biết LB=15, thì:

**ALG/OPT≤20/15=4/3**, miễn LB>0.

Nếu thuật toán max cho ALG=70 và biết UB=80, thì:

**ALG/OPT≥70/80=0.875**, miễn UB>0.

Những cận này có thể chặt hơn hệ số bảo đảm tổng quát của thuật toán.

### Đâu là vai trò của relaxation?

Một **relaxation** mở rộng tập nghiệm khả thi hoặc làm dễ bài toán:

- Với min: tối ưu của relaxation thường là một **lower bound**.
- Với max: tối ưu của relaxation thường là một **upper bound**.

Ví dụ có thể dùng LP relaxation, SDP hoặc các cận tổ hợp đơn giản. Nhưng **không phải mọi relaxation đều dễ giải**; và việc có một LB/UB còn cần một cách làm tròn/khôi phục nghiệm nguyên để xây thuật toán xấp xỉ.

## 9. Ví dụ 1 — Minimum Vertex Cover

Cho đồ thị vô hướng đơn G=(V,E), một **vertex cover** là tập C⊆V sao cho mỗi cạnh e=(u,v) có ít nhất một đầu mút thuộc C.

Mục tiêu:

**minimize |C|**.

Ví dụ đồ thị hình sao:

~~~text
        1
        |
    2 --0-- 3
~~~

Các cạnh:

**(0,1), (0,2), (0,3)**.

Tập {0} phủ cả ba cạnh, nên:

**OPT=1**.

Tập {0,1} cũng phủ được mọi cạnh, nhưng dùng 2 đỉnh:

**ALG=2**, tỷ số **ALG/OPT=2**.

Bài toán Minimum Vertex Cover tổng quát là NP-hard, nên một lời giải đa thức có cận bảo đảm là lựa chọn hữu ích khi không cần tối ưu tuyệt đối.

### Không nhầm vertex cover với edge cover

Vertex cover **chọn đỉnh để phủ cạnh**. Edge cover **chọn cạnh để phủ đỉnh**. Hai bài có định nghĩa, nghiệm và thuật toán khác nhau.

## 10. Thuật toán 2-approx bằng ghép cặp cực đại

Ý tưởng:

1. Khởi tạo C=∅.
2. Duyệt từng cạnh (u,v).
3. Nếu **cả u và v đều chưa được chọn** vào C, đưa **cả hai** vào C.
4. Sau khi duyệt hết cạnh, trả C.

Các cạnh làm phát sinh thao tác thêm cả hai đầu mút tạo thành một **matching** M: không có hai cạnh đã chọn nào chung đỉnh.

Vì sau khi chọn một cạnh, hai đầu của nó đã thuộc C, mọi cạnh được chọn sau đó có hai đầu mút chưa từng được chọn, nên các cạnh trong M đôi một không chung đỉnh.

### Pseudocode

~~~text
APPROX_VERTEX_COVER(V, E):
    chosen[0..V-1] = false
    matchingSize = 0

    for each edge (u,v):
        if not chosen[u] and not chosen[v]:
            chosen[u] = true
            chosen[v] = true
            matchingSize++

    return {v | chosen[v]}, matchingSize
~~~

Trong cấu trúc này M là một **maximal matching**: không thể thêm cạnh nào nữa mà vẫn không chung đỉnh, bởi khi kết thúc, mọi cạnh có ít nhất một đầu mút đã được chọn bởi M.

**Maximal không đồng nghĩa maximum.** Ta không cần matching lớn nhất để chứng minh hệ số 2.

## 11. Chứng minh tính khả thi của thuật toán phủ đỉnh

Xét một cạnh bất kỳ (u,v). Khi vòng lặp kiểm tra cạnh đó, có hai khả năng:

- **Ít nhất một đầu u hoặc v đã được chọn:** cạnh đã được phủ và không bao giờ mất trạng thái phủ.
- **Cả hai đầu chưa được chọn:** thuật toán thêm cả u và v, nên cạnh được phủ.

Vì xét mọi cạnh, khi kết thúc:

**Mọi cạnh có ít nhất một đầu mút trong C**.

Do đó **C là một vertex cover khả thi**.

Đây là một bước chứng minh độc lập với chất lượng xấp xỉ. Nếu bỏ qua feasibility, một tập có |C| nhỏ cũng có thể không hợp lệ.

### Với đồ thị không có cạnh

Nếu E=∅, vòng lặp không chọn đỉnh nào:

**C=∅**, **ALG=0**, **OPT=0**.

Chứng minh hệ số dạng bất đẳng thức vẫn đúng, nhưng không tính tỷ số 0/0.

## 12. Chứng minh hệ số 2 từ cận dưới matching

Gọi M là matching gồm các cạnh đã kích hoạt việc chọn cả hai đầu mút.

Do các cạnh trong M không chung đỉnh, bất kỳ vertex cover khả thi nào cũng phải lấy **ít nhất một đầu mút riêng** cho từng cạnh của M.

Vì vậy:

**OPT≥|M|**.

Thuật toán chọn **chính hai đầu mút** cho mỗi cạnh trong M, không trùng nhau giữa các cạnh matching:

**ALG=|C|=2|M|**.

Suy ra:

**ALG=2|M|≤2OPT**.

Đây là chứng minh **2-approximation** cho Minimum Vertex Cover không trọng số.

### Tại sao hệ số 2 có thể đạt tới?

Với đồ thị sao có tâm 0 và lá 1,2,3, nếu duyệt cạnh (0,1) đầu tiên:

- Matching M chứa (0,1), |M|=1.
- Thuật toán chọn C={0,1}, ALG=2.
- Tối ưu chỉ cần {0}, OPT=1.
- Tỷ số đúng **2**.

Vì vậy không thể chỉ dựa trên thuật toán này mà tuyên bố có một bảo đảm worst-case tốt hơn 2 cho mọi đồ thị.

### Không áp dụng nguyên chứng minh cho trọng số

Nếu mỗi đỉnh có trọng số khác nhau và mục tiêu cực tiểu hóa **tổng trọng số**, thao tác chọn cả hai đầu của matching không còn đảm bảo tỷ số 2 theo cùng phép đếm |M|. Bài toán Weighted Vertex Cover có cách xấp xỉ riêng, ví dụ qua LP rounding hoặc primal-dual.

Giả thiết **unweighted, vô hướng, không có self-loop** là một phần của phát biểu đang chứng minh.

## 13. Thời gian và bộ nhớ của 2-approx Vertex Cover

Nếu đồ thị có n=|V| đỉnh, m=|E| cạnh được đưa dưới dạng danh sách:

- Khởi tạo boolean chosen: **O(n)**.
- Duyệt mỗi cạnh đúng một lần: **O(m)**.
- Trích danh sách đỉnh đã chọn: **O(n)**.

Tổng:

**O(n+m) thời gian**, **O(n) bộ nhớ phụ và output**, không tính lưu edges input.

### Cận lower bound từ kết quả

Sau khi chạy, thuật toán biết |M| và |C|.

Ta có một chứng nhận rất dễ kiểm tra:

**|M|≤OPT≤|C|=2|M|**.

Ví dụ đồ thị sao: 1≤OPT≤2, còn brute-force nhỏ cho thấy OPT thật là 1.

### Đồ thị có nhiều cạnh trùng

Nếu input chứa một cạnh nhiều lần, thuật toán vẫn có thể phủ tất cả các bản sao và chứng minh bằng matching vẫn hoạt động theo bản chất phủ cạnh. Nhưng bài minh họa dùng đồ thị đơn, vì đó là dạng đặc tả dễ học và tránh mơ hồ về self-loop.

## 14. Ví dụ 2 — Maximum Coverage

Cho một vũ trụ các phần tử:

**U={0,1,...,u−1}**.

Cho m tập con S₀,...,Sₘ₋₁⊆U và ngân sách số tập **k**, với 0≤k≤m.

Chọn một họ chỉ số C gồm **không quá k tập** sao cho giá trị:

**f(C)=|∪_{i∈C} S_i|**

là lớn nhất.

Đây là bài **cực đại**. Vì f(C)≥0, có thể dùng bảo đảm theo phần giữ lại:

**ALG≥βOPT**.

### Vì sao tính theo hợp tập?

Một phần tử xuất hiện trong 3 tập được chọn chỉ được tính **một lần** trong số phần tử phủ.

Ví dụ:

~~~text
S0 = {0,1,2}
S1 = {2,3}
S2 = {3,4,5}
k = 2
~~~

Chọn S0 và S2 phủ:

**{0,1,2,3,4,5}**, tổng **6** phần tử.

Cộng kích thước từng tập cũng là 3+3=6 trong ví dụ này, nhưng trong trường hợp chồng lấp, phép cộng kích thước có thể lớn hơn số phần tử phân biệt. Phải tính **marginal gain** trên những phần tử **chưa được phủ**.

## 15. Thuật toán greedy Maximum Coverage

Ý tưởng lặp tối đa k lần:

1. Bắt đầu với không phần tử nào được phủ.
2. Trong những tập chưa chọn, tìm tập có **số phần tử chưa được phủ lớn nhất**.
3. Chọn tập ấy, đánh dấu các phần tử mới.
4. Nếu mọi tập còn lại có marginal gain bằng 0, có thể dừng sớm.

Pseudocode:

~~~text
GREEDY_MAX_COVERAGE(U, sets, k):
    covered = empty set
    chosen = empty list

    repeat at most k times:
        bestSet = none
        bestGain = 0

        for each unchosen set S:
            gain = count of elements in S not in covered
            if gain > bestGain:
                bestGain = gain
                bestSet = S

        if bestGain == 0:
            break

        add bestSet to chosen
        add all elements of bestSet to covered

    return chosen, |covered|
~~~

**Tie-break:** nếu nhiều tập có cùng gain, có thể chọn tập có chỉ số nhỏ nhất để kết quả thực thi xác định. Hệ số bảo đảm không phụ thuộc tie-break nếu mọi lần chọn một tập đạt **marginal gain tối đa**.

### Chi phí của việc đánh giá gain

Nếu tổng số lần xuất hiện phần tử trong tất cả các tập là L=Σ|S_i|, một vòng quét các tập có thể tốn O(L). Với tối đa k vòng:

**O(kL + u + m)** trong mô hình đánh dấu phần tử O(1) và dữ liệu đã chuẩn hóa, chưa tính tiền xử lý input.

Bộ nhớ bổ sung cho covered, selected/used thường O(u+m+k). Các cấu trúc hỗ trợ lazy updates có thể giảm chi phí trong trường hợp thực tế nhưng cần phân tích riêng.

## 16. Max Coverage là ví dụ điển hình về tính dưới-mô-đun

Hàm:

**f(C)=|∪_{i∈C} S_i|**

có hai tính chất:

**Đơn điệu (monotone):** nếu A⊆B thì f(A)≤f(B).

**Dưới-mô-đun (submodular):** lợi ích biên giảm dần. Với A⊆B và tập x chưa chọn:

**f(A∪{x})−f(A) ≥ f(B∪{x})−f(B)**.

Lý do: khi đã chọn nhiều tập hơn, có nhiều phần tử được phủ sẵn hơn, nên một tập bổ sung không thể tạo thêm **nhiều phần tử mới hơn** so với khi ta chưa có chúng.

### Cần phân biệt tổng gain và tổng cardinality

Nếu S mới chứa 10 phần tử nhưng 9 phần tử đã được phủ, gain thực tế chỉ bằng 1. Greedy chọn theo **gain**, không chọn theo kích thước gốc |S| của tập.

Nếu chỉ chọn các tập lớn nhất theo cardinality rồi bỏ qua giao nhau, chất lượng có thể xấu mà không được bảo đảm 1−1/e.

## 17. Chứng minh bảo đảm 1−(1−1/k)^k

Giả sử **k≥1** và OPT là số phần tử tối đa có thể phủ bằng **không quá k tập**.

Gọi:

- C_t là họ tập greedy chọn sau t bước.
- F_t=f(C_t) là số phần tử đã phủ.
- C* là một họ tối ưu gồm không quá k tập, f(C*)=OPT.

Trong các phần tử được C* phủ nhưng chưa được C_t phủ, số phần tử nhiều nhất là:

**OPT−F_t**.

Một phần tử có thể nằm trong nhiều tập tối ưu, nhưng tổng lợi ích biên của **k tập tối ưu** đối với C_t không nhỏ hơn số phần tử của C* chưa được C_t phủ.

Bởi nguyên lý trung bình, tồn tại một tập trong C* có marginal gain ít nhất:

**(OPT−F_t)/k**.

Greedy chọn tập có gain lớn nhất nên:

**F_{t+1}−F_t ≥ (OPT−F_t)/k**.

Sắp xếp:

**OPT−F_{t+1} ≤ (1−1/k)(OPT−F_t)**.

Bắt đầu F₀=0. Sau k bước:

**OPT−F_k ≤ (1−1/k)^k·OPT**.

Do đó:

**F_k ≥ [1−(1−1/k)^k]·OPT**.

Vì:

**(1−1/k)^k≤1/e**,

suy ra:

**F_k≥(1−1/e)·OPT≈0.63212·OPT**.

### Điều kiện và việc dừng sớm

Nếu ở một vòng không còn tập nào có gain dương, đã phủ hết những phần tử có thể được phủ bởi bất kỳ tập đầu vào nào. Khi đó không thêm tập cũng không làm giảm giá trị; bound vẫn đúng. Với k=0, OPT=ALG=0, không dùng biểu thức 1/k.

### Không áp dụng bảo đảm ngoài phạm vi

Chứng minh này dùng tính đơn điệu, submodularity và ngân sách **chọn tối đa k tập** (cardinality constraint). Nếu có chi phí khác nhau cho mỗi tập, ràng buộc knapsack, các điều kiện phụ, hàm mục tiêu không đơn điệu hoặc giá trị có dấu, không tự áp dụng nguyên thuật toán và hệ số này.

## 18. Ví dụ greedy không tối ưu nhưng vẫn đạt bảo đảm

Cho U={0,1,2,3,4,5,6,7} và ba tập:

~~~text
S0 = {0,1,2,3,4}    size 5
S1 = {0,1,2,5}      size 4
S2 = {3,4,6,7}      size 4

k = 2
~~~

**Bước 1:** greedy chọn S0 vì gain=5 là lớn nhất.

**Bước 2:** sau S0:

- Gain(S1)=1, chỉ thêm 5.
- Gain(S2)=2, thêm 6,7.

Greedy chọn S2, phủ tất cả trừ phần tử 5:

**ALG=7**.

Nhưng chọn **S1 và S2** phủ đủ 8 phần tử:

**OPT=8**.

Tỷ lệ đạt được:

**ALG/OPT=7/8=0.875**.

Bảo đảm tổng quát với k=2:

**β₂=1−(1−1/2)²=3/4=0.75**.

Ta thấy:

**0.875≥0.75**.

### Bảo đảm không phải dự đoán chính xác output

Thuật toán có thể tốt hơn cận đã chứng minh. Bảo đảm 0.75 cho k=2 **không** nói rằng greedy luôn trả đúng 75% của tối ưu.

Tương tự, bảo đảm 1−1/e là cận chung theo k, không có nghĩa mọi instance thật đều chỉ đạt khoảng 63.2%.

## 19. So sánh hai chứng minh min và max

| Bài | Mục tiêu | Chiến lược | Bảo đảm | Chứng cứ |
| --- | --- | --- | --- | --- |
| Minimum Vertex Cover (không trọng số) | min số đỉnh | Lấy hai đầu mỗi cạnh trong một matching cực đại tham lam | **ALG≤2OPT** | Matching rời nhau tạo lower bound | 
| Maximum Coverage, ≤k tập | max số phần tử phủ | Thêm tập có marginal gain cao nhất | **ALG≥[1−(1−1/k)^k]OPT** | Submodularity và tiến triển của residual |

Cả hai đều không cần tìm đúng OPT để **chứng minh** hệ số.

**Vertex Cover:** dùng một **cận dưới** |M| cho bài min.

**Maximum Coverage:** dùng **lập luận giảm dần phần giá trị còn thiếu** so với OPT, không phải chỉ một test mẫu.

### Một cách kiểm tra nhanh chiều dấu

- Nếu một công thức tuyên bố min ALG≤0.5OPT trên instance OPT>0, mâu thuẫn với feasibility vì ALG≥OPT.
- Nếu một công thức tuyên bố max ALG≥2OPT trên instance OPT>0, cũng mâu thuẫn vì ALG≤OPT.

Những kiểm tra dấu này bắt nhiều lỗi ghi nhầm factor.

## 20. Bảo đảm cộng và trường hợp mục tiêu quy mô nhỏ

**Additive approximation** có thể được phát biểu:

- Min: **ALG≤OPT+δ**, với δ≥0.
- Max: **ALG≥OPT−δ**.

Ví dụ nếu thời gian tối ưu 100 ms và thuật toán trả 103 ms, bảo đảm cộng δ=5 ms cho phép nghiệm này. Nhưng nếu tối ưu 1 ms mà thuật toán trả 6 ms, cùng δ=5 ms là khoảng cách tương đối rất lớn.

Ngược lại, hệ số ρ=1.1 cho bài min cho phép:

- OPT=100 ⇒ ALG≤110, chênh tối đa 10.
- OPT=1 ⇒ ALG≤1.1, chênh tối đa 0.1.

### Additive ε đôi khi được chuẩn hóa

Với bài cực đại giá trị trong [0,1], người ta có thể ghi:

**ALG≥OPT−ε**,

trong đó ε là lỗi tuyệt đối theo thang chuẩn hóa.

Với một đại lượng có quy mô U, có thể gặp:

**ALG≥OPT−εU**.

Hai mệnh đề không giống nhau. Phải nêu rõ đơn vị và ý nghĩa của ε.

## 21. Bài toán có nhiều mục tiêu: bicriteria approximation

Một số bài toán có cả mục tiêu và ràng buộc:

- Cực tiểu tổng chi phí.
- Không dùng quá B đơn vị bộ nhớ.
- Không vi phạm độ trễ tối đa.
- Đảm bảo chất lượng dịch vụ.

**Bicriteria approximation** có thể cho phép làm gần đúng cả **hàm mục tiêu và một giới hạn ràng buộc**, ví dụ:

**Cost(ALG)≤ρOPT** và **Resource(ALG)≤γB**.

Nếu γ>1, nghiệm trả về có thể **vi phạm hạn mức gốc B**. Khi đó nó không phải một nghiệm khả thi của bài gốc theo nghĩa tuyệt đối; cần gọi đúng là **bảo đảm hai tiêu chí** và nêu rõ phạm vi nới lỏng.

Không được chỉ báo hệ số chi phí rồi che giấu sự vi phạm ràng buộc còn lại.

### Ứng dụng

Trong lập lịch, định tuyến hoặc phân bổ máy, một giải pháp có chi phí tốt nhưng cần thêm 10% capacity có thể hữu ích nếu người dùng đồng ý nới ràng buộc. Tuy nhiên đó là một **bài toán/kiểu cam kết khác** so với trả nghiệm khả thi 100% theo hạn mức cứng.

## 22. Thuật toán xấp xỉ với nghiệm ngẫu nhiên

Một thuật toán randomized có thể đưa ra bảo đảm dạng:

**E[ALG]≥βOPT** cho bài max,

hoặc:

**E[ALG]≤ρOPT** cho bài min,

trong đó kỳ vọng tính trên ngẫu nhiên nội bộ của thuật toán với input cố định.

Cần phân biệt với:

**P(ALG≥βOPT)≥1−δ**,

là bảo đảm **xác suất cao**.

### Expected không đồng nghĩa mọi lần đều tốt

Một thuật toán có expected performance tốt có thể có một số run kém. Để suy ra cam kết high probability, cần phân tích tập trung xác suất, lặp độc lập và lấy nghiệm tốt nhất, hoặc kỹ thuật amplification có điều kiện phù hợp.

### Feasibility vẫn quan trọng

Nghiệm của mỗi run có thể cần phải khả thi với xác suất 1 (Las Vegas-style) hoặc bài cần định nghĩa xác suất chấp nhận nghiệm sai/vi phạm. **Một kỳ vọng tốt của hàm mục tiêu không tự sửa nghiệm không khả thi.**

## 23. PTAS và FPTAS

**PTAS (Polynomial-Time Approximation Scheme)** là họ thuật toán được tham số hóa bởi ε>0 sao cho với **mỗi ε cố định**, thời gian là đa thức theo input size, và chất lượng tiến sát tối ưu.

Ví dụ các dạng bảo đảm thường gặp với OPT không âm:

- Min: **ALG≤(1+ε)OPT**.
- Max: **ALG≥(1−ε)OPT**, với 0<ε<1.

Độ phức tạp của PTAS có thể có dạng:

**n^{O(1/ε)}**,

nên khi ε nhỏ, số mũ của n có thể rất lớn.

**FPTAS (Fully Polynomial-Time Approximation Scheme)** yêu cầu thêm thời gian **đa thức cả theo kích thước input lẫn 1/ε**.

Ví dụ một dạng thời gian phù hợp:

**O(n³/ε²)**,

nếu đơn vị phép toán và mã hóa input được xử lý đúng.

### Ví dụ kinh điển

Bài **0/1 Knapsack cực đại hóa tổng giá trị không âm** có các kỹ thuật FPTAS dựa trên scale/round các giá trị (profits) với những giả thiết mã hóa chuẩn. Không được coi mọi biến thể Knapsack đều có FPTAS mà không xem điều kiện.

### Không nhầm ε và xác suất sai

ε trong PTAS/FPTAS mô tả **mức mất chất lượng**, không phải xác suất thất bại. δ thường được dùng cho xác suất thất bại trong randomized schemes, nhưng tên biến không phải chuẩn bắt buộc.

## 24. APX, giới hạn xấp xỉ và bất khả xấp xỉ

Trong tối ưu tổ hợp, **APX** thường dùng cho lớp bài toán tối ưu có thuật toán đa thức với một **hệ số xấp xỉ hằng số**, theo định nghĩa hình thức phù hợp.

Một bài NP-hard vẫn có thể có thuật toán xấp xỉ tốt. **NP-hard không có nghĩa không xấp xỉ được.**

Ngược lại, một số bài có **giới hạn hardness of approximation**: nếu tồn tại thuật toán đa thức tốt hơn một tỷ số nào đó thì sẽ kéo theo những hệ quả độ phức tạp rất mạnh, thường dưới giả thiết P≠NP hoặc giả thiết khác.

### Cần phát biểu đúng phạm vi

Ví dụ Maximum Coverage có greedy với bảo đảm **1−1/e**. Những kết quả hardness về việc vượt ngưỡng tương ứng cần đi cùng **mô hình, giả thiết reduction và định nghĩa bài toán cụ thể**. Không được biến một bảo đảm thuật toán thành một phát biểu bất khả vượt qua nếu chưa có chứng minh hardness.

Tương tự, thuật toán 2-approx Vertex Cover không có nghĩa **2 là ngưỡng tốt nhất có thể** theo mọi mô hình tính toán hay mọi giả thiết độ phức tạp. Nó chỉ là hệ số đã chứng minh cho thuật toán đang xét.

## 25. Xấp xỉ khác heuristic và metaheuristic

**Heuristic** là quy tắc thực dụng tạo nghiệm có thể tốt nhưng không nhất thiết có **bảo đảm worst-case** được chứng minh.

Ví dụ:

- Chọn đỉnh bậc cao nhất rồi loại cạnh đã phủ để giải Vertex Cover.
- Local search đổi một phần lời giải hiện tại để cải thiện chi phí.
- Simulated annealing, genetic algorithms hoặc tabu search với cách thiết lập tổng quát.

Các kỹ thuật ấy có thể rất mạnh trên phân phối dữ liệu thực tế, nhưng nếu không có chứng minh, không nên gắn nhãn **2-approx** hay **0.9-approx** chỉ từ thử nghiệm.

### Approximation algorithm có thể cũng là greedy

Thuật toán 2-approx Vertex Cover và greedy Maximum Coverage đều là **tham lam**, nhưng được gọi là approximation algorithms **vì có chứng minh**.

Vì vậy **greedy không tự đồng nghĩa heuristic vô bảo đảm**, cũng không tự đồng nghĩa có bảo đảm. Phải xét quy tắc, bài toán, giả thiết và proof.

### Local search và bảo đảm

Có những local search có thể chứng minh factor cho các lớp input cụ thể. Tên “local search” không quyết định trước rằng có hoặc không có guarantee.

## 26. Mã Java 17+ độc lập: hai bài toán, hai chiều bảo đảm

Chương trình sau triển khai:

1. **2-approx Minimum Vertex Cover** trên đồ thị vô hướng không có self-loop.
2. **Greedy Maximum Coverage** với ngân sách chọn tối đa k tập.
3. **Brute-force exact optimum** cho các instance nhỏ, chỉ dùng để kiểm chứng ví dụ.
4. Kiểm tra **feasibility và bất đẳng thức bảo đảm** trước khi in kết quả.
5. Các ca biên: đồ thị không cạnh, đồ thị 0 đỉnh, ngân sách k=0, universe rỗng, các tập con giống nhau, trường hợp greedy không tối ưu nhưng vẫn đạt guarantee.

Hai thuật toán xấp xỉ đều **không cần brute-force** để hoạt động. Hàm exact chỉ xuất hiện trong chương trình demo để công khai so sánh ALG với OPT trên input nhỏ. Không được đưa chi phí exponential của exact vào nhãn thời gian của hai thuật toán xấp xỉ khi dùng riêng.

**Lưu tệp: ApproximationGuaranteesDemo.java**

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ApproximationGuaranteesDemo {

    record Edge(int u, int v) {}
    record CoverResult(int[] vertices, int matchingSize) {}
    record CoverageResult(int[] selectedSets, int coveredCount) {}

    static void validateGraph(int n, Edge[] edges) {
        if (n < 0) {
            throw new IllegalArgumentException("negative n");
        }
        Objects.requireNonNull(edges, "edges");

        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n
                    || e.u() == e.v()) {
                throw new IllegalArgumentException(
                        "invalid undirected edge");
            }
        }
    }

    // O(V+E) time and O(V) memory.
    // Choose both endpoints of each new matching edge.
    static CoverResult approxVertexCover(
            int n, Edge[] edges) {

        validateGraph(n, edges);

        boolean[] chosen = new boolean[n];
        int matchingSize = 0;

        for (Edge e : edges) {
            int u = e.u();
            int v = e.v();

            if (!chosen[u] && !chosen[v]) {
                chosen[u] = true;
                chosen[v] = true;
                matchingSize++;
            }
        }

        int count = 0;
        for (boolean b : chosen) {
            if (b) count++;
        }

        int[] vertices = new int[count];
        int p = 0;

        for (int v = 0; v < n; v++) {
            if (chosen[v]) vertices[p++] = v;
        }

        return new CoverResult(vertices, matchingSize);
    }

    static boolean isVertexCover(
            int n, Edge[] edges, int[] vertices) {

        boolean[] present = new boolean[n];

        for (int v : vertices) {
            if (v < 0 || v >= n) return false;
            present[v] = true;
        }

        for (Edge e : edges) {
            if (!present[e.u()] && !present[e.v()]) {
                return false;
            }
        }

        return true;
    }

    // Exact oracle for small graphs only: exponential.
    static int exactVertexCoverSmall(
            int n, Edge[] edges) {

        validateGraph(n, edges);

        if (n > 20) {
            throw new IllegalArgumentException(
                    "exact oracle supports n <= 20");
        }

        int best = n + 1;
        int limit = 1 << n;

        for (int mask = 0; mask < limit; mask++) {
            int size = Integer.bitCount(mask);
            if (size >= best) continue;

            boolean coversAll = true;

            for (Edge e : edges) {
                boolean uChosen = (mask & (1 << e.u())) != 0;
                boolean vChosen = (mask & (1 << e.v())) != 0;

                if (!uChosen && !vChosen) {
                    coversAll = false;
                    break;
                }
            }

            if (coversAll) best = size;
        }

        return best;
    }

    static void validateCoverage(
            int universeSize, int[][] sets, int budget) {

        if (universeSize < 0) {
            throw new IllegalArgumentException(
                    "negative universe size");
        }

        Objects.requireNonNull(sets, "sets");

        if (budget < 0 || budget > sets.length) {
            throw new IllegalArgumentException(
                    "budget must be in [0,m]");
        }

        for (int[] set : sets) {
            Objects.requireNonNull(set, "set");

            Set<Integer> unique = new HashSet<>();

            for (int element : set) {
                if (element < 0 || element >= universeSize) {
                    throw new IllegalArgumentException(
                            "element outside universe");
                }

                if (!unique.add(element)) {
                    throw new IllegalArgumentException(
                            "duplicate element within a set");
                }
            }
        }
    }

    // Greedy cardinality-constrained Maximum Coverage.
    // O(k*L) selection work, L = sum of set sizes.
    static CoverageResult greedyMaxCoverage(
            int universeSize, int[][] sets, int budget) {

        validateCoverage(universeSize, sets, budget);

        boolean[] covered = new boolean[universeSize];
        boolean[] used = new boolean[sets.length];
        int[] selected = new int[budget];
        int chosenCount = 0;
        int coveredCount = 0;

        for (int step = 0; step < budget; step++) {
            int bestIndex = -1;
            int bestGain = 0;

            for (int i = 0; i < sets.length; i++) {
                if (used[i]) continue;

                int gain = 0;

                for (int element : sets[i]) {
                    if (!covered[element]) gain++;
                }

                // First index wins in a tie.
                if (gain > bestGain) {
                    bestGain = gain;
                    bestIndex = i;
                }
            }

            if (bestIndex < 0) break;

            used[bestIndex] = true;
            selected[chosenCount++] = bestIndex;

            for (int element : sets[bestIndex]) {
                if (!covered[element]) {
                    covered[element] = true;
                    coveredCount++;
                }
            }
        }

        return new CoverageResult(
                Arrays.copyOf(selected, chosenCount),
                coveredCount);
    }

    // Exact oracle for small set families only: exponential.
    static int exactMaxCoverageSmall(
            int universeSize, int[][] sets, int budget) {

        validateCoverage(universeSize, sets, budget);

        if (sets.length > 20) {
            throw new IllegalArgumentException(
                    "exact oracle supports m <= 20");
        }

        int best = 0;
        int limit = 1 << sets.length;

        for (int mask = 0; mask < limit; mask++) {
            if (Integer.bitCount(mask) > budget) continue;

            boolean[] covered = new boolean[universeSize];
            int total = 0;

            for (int i = 0; i < sets.length; i++) {
                if ((mask & (1 << i)) == 0) continue;

                for (int element : sets[i]) {
                    if (!covered[element]) {
                        covered[element] = true;
                        total++;
                    }
                }
            }

            if (total > best) best = total;
        }

        return best;
    }

    static void showCover(
            String label, int n, Edge[] edges) {

        CoverResult result = approxVertexCover(n, edges);
        int approx = result.vertices().length;
        int optimum = exactVertexCoverSmall(n, edges);

        if (!isVertexCover(n, edges, result.vertices())) {
            throw new AssertionError("cover infeasible");
        }

        if (approx != 2 * result.matchingSize()
                || result.matchingSize() > optimum
                || approx > 2 * optimum) {
            throw new AssertionError(
                    "2-approx guarantee violated");
        }

        System.out.println(label
                + ": approx=" + approx
                + ", opt=" + optimum
                + ", matching=" + result.matchingSize()
                + ", vertices="
                + Arrays.toString(result.vertices()));
    }

    static void showCoverage(
            String label, int universeSize,
            int[][] sets, int budget) {

        CoverageResult result =
                greedyMaxCoverage(universeSize, sets, budget);

        int optimum =
                exactMaxCoverageSmall(universeSize, sets, budget);

        if (result.selectedSets().length > budget
                || result.coveredCount() > optimum) {
            throw new AssertionError("coverage infeasible");
        }

        // Algebraic guarantee for k>0:
        // ALG >= [1-(1-1/k)^k]*OPT.
        if (budget > 0) {
            double factor =
                    1.0 - Math.pow(
                            1.0 - 1.0 / budget, budget);

            if (result.coveredCount() + 1e-9
                    < factor * optimum) {
                throw new AssertionError(
                        "greedy guarantee violated");
            }
        } else if (result.coveredCount() != 0
                || optimum != 0) {
            throw new AssertionError("k=0 must cover 0");
        }

        System.out.println(label
                + ": greedy=" + result.coveredCount()
                + ", opt=" + optimum
                + ", k=" + budget
                + ", sets="
                + Arrays.toString(result.selectedSets()));
    }

    public static void main(String[] args) {

        showCover("Star", 4, new Edge[] {
                new Edge(0, 1),
                new Edge(0, 2),
                new Edge(0, 3)
        });

        showCover("Triangle", 3, new Edge[] {
                new Edge(0, 1),
                new Edge(1, 2),
                new Edge(0, 2)
        });

        showCover("Disjoint", 4, new Edge[] {
                new Edge(0, 1),
                new Edge(2, 3)
        });

        showCover("Edgeless", 5, new Edge[] {});

        showCover("Path", 5, new Edge[] {
                new Edge(0, 1),
                new Edge(1, 2),
                new Edge(2, 3),
                new Edge(3, 4)
        });

        showCover("Single edge", 2, new Edge[] {
                new Edge(0, 1)
        });

        showCover("Zero vertices", 0, new Edge[] {});

        showCoverage("Suboptimal", 8, new int[][] {
                {0, 1, 2, 3, 4},
                {0, 1, 2, 5},
                {3, 4, 6, 7}
        }, 2);

        showCoverage("All covered", 6, new int[][] {
                {0, 1, 2},
                {2, 3},
                {3, 4, 5}
        }, 2);

        showCoverage("Budget zero", 5, new int[][] {
                {0, 1},
                {1, 2},
                {2, 3}
        }, 0);

        showCoverage("Empty", 0, new int[][] {}, 0);

        showCoverage("Repeated sets", 4, new int[][] {
                {0, 1},
                {0, 1},
                {2, 3}
        }, 3);

        showCoverage("One selection", 3, new int[][] {
                {0, 1},
                {1, 2}
        }, 1);

        showCoverage("Zero extra gain", 4, new int[][] {
                {0, 1},
                {0, 1}
        }, 2);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ApproximationGuaranteesDemo.java
java ApproximationGuaranteesDemo
~~~

**Đầu ra chính xác cho các ví dụ trên:**

~~~text
Star: approx=2, opt=1, matching=1, vertices=[0, 1]
Triangle: approx=2, opt=2, matching=1, vertices=[0, 1]
Disjoint: approx=4, opt=2, matching=2, vertices=[0, 1, 2, 3]
Edgeless: approx=0, opt=0, matching=0, vertices=[]
Path: approx=4, opt=2, matching=2, vertices=[0, 1, 2, 3]
Single edge: approx=2, opt=1, matching=1, vertices=[0, 1]
Zero vertices: approx=0, opt=0, matching=0, vertices=[]
Suboptimal: greedy=7, opt=8, k=2, sets=[0, 2]
All covered: greedy=6, opt=6, k=2, sets=[0, 2]
Budget zero: greedy=0, opt=0, k=0, sets=[]
Empty: greedy=0, opt=0, k=0, sets=[]
Repeated sets: greedy=4, opt=4, k=3, sets=[0, 2]
One selection: greedy=2, opt=2, k=1, sets=[0]
Zero extra gain: greedy=2, opt=2, k=2, sets=[0]
~~~

### Những quyết định thiết kế quan trọng

**Đồ thị vô hướng không self-loop:** Edge kiểm tra hai đầu u,v hợp lệ và khác nhau. Chương trình không gắn trọng số đỉnh, nên bảo đảm hai lần là với **số đỉnh** chứ không phải tổng trọng số.

**Chọn hai đầu theo matching:** Nếu cả hai đầu chưa selected, chọn cả hai. Mỗi cạnh matching mới không chung đỉnh với các cạnh matching đã chọn, nên |C|=2|M| là đẳng thức có thể kiểm tra.

**Độ lớn oracle:** exactVertexCoverSmall chỉ cho n≤20, exactMaxCoverageSmall chỉ cho m≤20 vì duyệt 2^n hoặc 2^m cách chọn. Chúng không phải thuật toán đa thức được quảng bá cho bài lớn.

**Set là tập hợp:** Mỗi tập input phải chứa phần tử **không lặp trong chính tập đó**; chương trình từ chối phần tử lặp và phần tử ngoài U. Các tập **khác nhau** được phép giống hệt nhau; ví dụ Repeated sets cho thấy greedy không đếm lại một phần tử đã phủ.

**Greedy dừng khi gain bằng 0:** Với mọi tập còn lại không tạo phần tử mới, việc tiếp tục chọn không tăng giá trị. Ràng buộc là **chọn tối đa k**, không yêu cầu đúng k tập.

**Tie-break:** chương trình chỉ thay bestIndex khi gain lớn hơn nghiêm ngặt, nên tập có chỉ số nhỏ hơn được giữ nếu đồng hạng.

**Không tính tỷ số 0/0:** Khi budget=0 hoặc OPT=0, chương trình kiểm tra bất đẳng thức bảo đảm thay vì in “ratio=NaN”.

**Validation và complexity:** Hàm validateCoverage dùng HashSet để từ chối phần tử lặp trong một tập, kỳ vọng O(L) cho validation theo mô hình hashing. Greedy selection dùng tối đa k lần quét toàn bộ các thành viên set, O(kL) theo biểu diễn incidence list.

## 27. Làm rõ chi phí thực sự của chương trình demo

Đây là một điểm rất dễ nhầm:

- **approxVertexCover** có O(V+E) thời gian và O(V) bộ nhớ phụ.
- **greedyMaxCoverage** có O(kL+u+m) thời gian theo mô hình phép đánh dấu/hashing thông dụng, và O(u+m+k) bộ nhớ phụ không tính input.
- **exactVertexCoverSmall** có thời gian **mũ theo V**; giới hạn V≤20.
- **exactMaxCoverageSmall** có thời gian **mũ theo m**; giới hạn m≤20.

Chương trình **showCover/showCoverage** có gọi exact oracle để in OPT, nên **toàn bộ demo** có chi phí mũ trên input nhỏ. Đó là lựa chọn giáo dục và kiểm thử, **không có nghĩa thuật toán xấp xỉ cần oracle tối ưu để đưa ra lời giải**.

Trong sản phẩm thật, cần tách phần approximate solver khỏi phần exact small-instance test. Nếu đưa n=100 vào exactVertexCoverSmall, chương trình chủ động từ chối thay vì tưởng rằng vẫn có thể chạy tức thời.

### Độ phức tạp của chương trình dùng dữ liệu lớn

Với đồ thị vài triệu cạnh, duyệt edge một lần có thể hiệu quả nếu có memory cho boolean[n].

Với Maximum Coverage, nếu số tập m và ngân sách k cùng lớn, mỗi vòng quét tất cả tập có thể tốn kL; cần xem xét lưu danh sách ngược element→sets, lazy greedy, incremental gains hoặc kỹ thuật chuyên biệt. Nhưng bất kỳ tối ưu implementation nào cũng cần giữ quy tắc chọn gain tối đa nếu muốn áp dụng nguyên chứng minh.

## 28. Kiểm chứng độc lập bằng vét cạn

Với Vertex Cover n nhỏ, duyệt **mọi bitmask đỉnh**:

1. Mỗi bitmask biểu diễn một tập C.
2. Kiểm tra từng cạnh (u,v) có ít nhất một đầu thuộc C.
3. Với các mask hợp lệ, lấy số bit 1 nhỏ nhất.
4. So giá trị nhỏ nhất với kết quả approximate và cận matching.

**Oracle** kiểm tra:

**C khả thi; |M|≤OPT; ALG=2|M|≤2OPT**.

Với Maximum Coverage m nhỏ:

1. Duyệt mọi bitmask chọn tập với **số bit 1≤k**.
2. Lấy hợp các phần tử trong các tập được chọn.
3. Ghi nhận số phần tử lớn nhất là OPT.
4. So với số phần tử greedy đã phủ và công thức β_k.

**Oracle** kiểm tra:

**0≤ALG≤OPT; số tập chọn≤k; ALG≥β_k OPT**.

### Tại sao brute-force là oracle hợp lý ở test nhỏ?

Bài toán tối ưu có thể khó trên input tổng quát nhưng **mọi tập nghiệm của n≤10 hoặc m≤10 đều có thể duyệt hết** trong số vòng thấp. Oracle xây theo cách độc lập với thuật toán approximation, phát hiện lỗi:

- Không phủ đủ cạnh.
- Đếm phần tử trùng trong Maximum Coverage.
- Chọn quá k tập.
- Đổi chiều bất đẳng thức.
- Sai khi ngân sách 0 hoặc đồ thị không cạnh.
- Sai do tie-break hoặc lặp lại cùng tập nhiều lần.

### Random test không thay thế chứng minh

1.000 hay 100.000 lần kiểm thử đều chỉ là bằng chứng thực nghiệm. Hệ số 2 và 1−1/e trong bài được bảo đảm bởi **chứng minh toán học cho tất cả instance thuộc phạm vi giả thiết**, không phải vì chạy random nhiều lần mà chưa thấy phản ví dụ.

## 29. Metamorphic testing và kiểm thử phản ví dụ

Ngoài oracle tối ưu, có thể áp dụng các phép biến đổi bảo toàn tính chất:

**Vertex Cover:**

- **Hoán vị thứ tự cạnh**: output C có thể khác, nhưng phải vẫn là vertex cover và vẫn thỏa 2-approx.
- **Đổi tên đỉnh** bằng hoán vị: giá trị OPT không đổi; lời giải vẫn cần khả thi.
- **Thêm một đỉnh cô lập**: OPT không đổi, vì đỉnh đó không tạo cạnh cần phủ.
- **Nhân bản một cạnh** nếu biểu diễn cho phép: tập đỉnh phủ tối ưu không đổi.

**Maximum Coverage:**

- **Hoán vị thứ tự các tập**: greedy có thể chọn các chỉ số khác do tie-break, nhưng ratio guarantee vẫn đúng.
- **Thêm một tập rỗng**: không tạo gain dương; OPT không tăng.
- **Nhân bản một tập**: không tăng OPT nếu ngân sách không đổi, vì chọn hai tập giống nhau không tăng hợp.
- **Hoán vị tên phần tử U**: giá trị tối ưu và giá trị số phần tử phủ không đổi.
- **Tăng ngân sách k** (trong 0..m): giá trị OPT không giảm. Giá trị greedy cũng không giảm khi cùng thứ tự tie-break và các lần lựa chọn trước được giữ nguyên.

### Phải phân biệt tính bất biến nghiệm và tính bất biến giá trị

Thay thứ tự cạnh có thể thay matching và tập đỉnh C mà thuật toán tạo ra. Không được đòi **danh sách đỉnh được chọn giống hệt** trên mọi hoán vị; cần kiểm tra bất biến đúng: feasibility và bound.

Tương tự, thêm duplicate set có thể thay cách chọn tie, nhưng không làm tăng số phần tử phân biệt có thể phủ với cùng budget.

## 30. Cách báo cáo chất lượng khi không biết OPT

Trên instance lớn, OPT thường khó tính chính xác. Khi đó không được tự điền một cột “OPT” bằng giá trị heuristic khác rồi coi ratio là tỷ số thật.

Các cách báo cáo trung thực:

**Min:** có ALG và lower bound LB>0 ⇒ chứng nhận:

**ALG/OPT≤ALG/LB**.

**Max:** có ALG và upper bound UB>0 ⇒ chứng nhận:

**ALG/OPT≥ALG/UB**.

### Chứng nhận riêng của Vertex Cover

Matching M là một **lower bound**:

**OPT≥|M|**.

Với thuật toán chọn cả hai đầu, **ALG=2|M|**, nên:

**ALG/OPT≤2**.

Nếu còn có lower bound khác lớn hơn |M|, có thể lấy LB=max(các lower bounds hợp lệ) để có chứng nhận tốt hơn cho một instance cụ thể.

### Chứng nhận riêng của Maximum Coverage

Một upper bound thô có thể lấy:

**UB=min(u, tổng k kích thước tập lớn nhất)**.

Vì hợp của k tập không thể nhiều hơn tổng kích thước riêng hoặc kích thước vũ trụ, UB≥OPT. Nếu UB>0:

**ALG/OPT≥ALG/UB**.

Trong ví dụ Suboptimal:

- u=8.
- Hai tập lớn nhất có kích thước 5 và 4 ⇒ tổng 9.
- UB=min(8,9)=8.
- ALG=7, nên chứng nhận ít nhất **7/8=0.875**.

Vì ở ví dụ đã biết OPT=8, chứng nhận này còn là tỷ lệ thực tế.

## 31. Bài toán cực tiểu trọng số và vấn đề scale

Trong các bài tối ưu thực tế, hàm mục tiêu có thể có trọng số:

**min Σ w_v·x_v**,

hoặc:

**max Σ p_e·y_e**.

Nếu trọng số không âm, một số dạng bảo đảm nhân vẫn có ý nghĩa. Nhưng thuật toán và chứng minh phải dùng **giá trị trọng số**, không chỉ số lượng đối tượng.

Ví dụ Vertex Cover không trọng số dùng:

**|C|=2|M|**.

Nếu một đầu mút có trọng số 1, đầu còn lại có trọng số 10^9, việc chọn cả hai đầu có chi phí 10^9+1 trong khi chọn đầu nhẹ có thể đủ cho một cạnh. Tỷ số có thể lớn tùy ý nếu áp dụng nguyên quy tắc không trọng số.

### Phản ví dụ hai đỉnh

Đồ thị một cạnh (0,1), với:

**w₀=1**, **w₁=M**.

Tối ưu chọn {0}, chi phí **1**.

Thuật toán chọn cả hai đầu {0,1}, chi phí **1+M**.

Khi M→∞, không có một hệ số cố định 2 nào bảo đảm chi phí ≤2OPT.

**Thay đổi hàm mục tiêu có thể làm mất bảo đảm của cùng một quy tắc greedy.**

## 32. Những lỗi phổ biến trong bài xấp xỉ

1. **Đảo chiều min/max**, viết ALG≤βOPT với β<1 cho bài min có OPT>0.
2. **Dùng ρ≥1 cho max nhưng quên đổi công thức**, báo sai hệ số.
3. **Tính ALG/OPT khi OPT=0**, nhận 0/0 và giả vờ đó là 1.
4. **Áp dụng tỷ số trên mục tiêu âm** mà không có định nghĩa phù hợp.
5. **Nhầm bảo đảm cộng với nhân**, coi 2-approx nghĩa là cộng thêm 2 đơn vị.
6. **Cộng hằng số vào mục tiêu rồi giữ nguyên tỷ số**, dù ratio thay đổi.
7. **Cho nghiệm không khả thi vào phép so chất lượng**, vi phạm định nghĩa.
8. **Nhầm thuật toán greedy bất kỳ với approximation có chứng minh**, suy luận từ tên.
9. **Thấy ratio trung bình tốt trong benchmark rồi tuyên bố worst-case guarantee**, không có proof.
10. **Tuyên bố hệ số 2 Vertex Cover khi dùng trọng số đỉnh**, trong khi proof chỉ đếm số đỉnh.
11. **Nhầm maximal matching với maximum matching**, đòi giải matching lớn nhất không cần thiết.
12. **Chọn một đầu thay vì cả hai đầu matching rồi lặp lại proof 2|M|**, không đúng với thuật toán ấy.
13. **Không kiểm tra mọi cạnh đã được phủ**, trả một tập nhỏ nhưng thiếu cạnh.
14. **Coi matching size là OPT luôn**, nó chỉ là lower bound.
15. **Dùng greedy Maximum Coverage chọn tập có size lớn nhất thay vì marginal gain**, không đúng thuật toán đã chứng minh.
16. **Đếm trùng phần tử ở nhiều set**, làm overestimate coverage.
17. **Chọn quá k tập** rồi báo ratio tốt, nghiệm không hợp lệ.
18. **Áp dụng 1−1/e cho ràng buộc không phải cardinality k**, thiếu proof.
19. **Cho rằng 1−1/e là tỷ lệ chính xác mỗi lần chạy**, nó chỉ là cận dưới.
20. **Tính β_k khi k=0**, chia cho 0.
21. **Không cho dừng sớm khi gain=0** dù bài cho phép ≤k.
22. **Chọn tập đã chọn lại và đếm gain cũ**, tạo kết quả sai.
23. **Nhầm guaranteed approximation với randomized expected approximation**, không phân biệt xác suất.
24. **Dùng expected guarantee như high-probability guarantee**, không có concentration.
25. **Nhầm PTAS với FPTAS**, bỏ điều kiện đa thức theo 1/ε.
26. **Coi ε là xác suất sai của PTAS**, lẫn với δ trong randomized.
27. **Gọi một heuristic không có chứng minh là 1.1-approx**, suy từ test.
28. **Tuyên bố NP-hard nên không thể xấp xỉ**, sai vì nhiều bài có approximation.
29. **Tuyên bố thuật toán 2-approx là không thể cải thiện**, chưa có kết quả hardness tương ứng.
30. **Dùng exact oracle exponential để phân tích chi phí của greedy**, lẫn demo QA với solver production.
31. **Báo ratio thật khi OPT chưa tính**, thay bằng lower/upper bound nhưng không ghi rõ.
32. **Dùng LB cho bài max và UB cho bài min để lấy ratio tự chứng nhận**, đảo vai trò.
33. **Quên kiểm tra các trường hợp rỗng**, OPT=ALG=0 gây NaN.
34. **Tuyên bố algo min đạt ALG≤ρOPT khi mục tiêu chứa cost âm**, bất đẳng thức có thể vô nghĩa.
35. **Nhầm guarantee cho toàn bộ bài với guarantee trên subset input**, ví dụ graph không trọng số với graph trọng số.
36. **Bỏ unit và scale trong additive ε**, làm sai ý nghĩa tolerance.
37. **Không tính memory**, greedy lưu covered/U và tập đã chọn.
38. **Không nêu tie-break**, chạy cùng dữ liệu nhưng output khác và khó QA.
39. **Không xét duplicate element bên trong một set**, đếm gain hai lần.
40. **Dùng proof theo average-case để khẳng định worst-case**, không đúng lượng từ.
41. **Tin random test chứng minh guarantee**, chỉ chứng minh qua bất biến/định lý.
42. **Bỏ qua chi phí biểu diễn input**, số set incidence có thể rất lớn.
43. **Nhầm “gần nghiệm tối ưu” với “gần giá trị mục tiêu tối ưu”**, bài có nhiều nghiệm khác xa nhau nhưng cùng cost.
44. **Không kiểm tra trường hợp trọng số rất lớn**, hệ số không trọng số có thể mất hoàn toàn.
45. **Bỏ dấu ≤ cho ngân sách “tối đa k”**, buộc chọn đúng k tập và thêm những tập gain0 không cần thiết.
46. **Không phân biệt approx factor với lower/upper bound chứng nhận cho instance**, mất thông tin về chất lượng đã chứng minh.

## 33. Bài tập tự luyện

**Bài 1 — Phân biệt dấu.** Nếu OPT_min=20, thuật toán trả ALG=31, có phải 1.5-approx không?  
**Đáp án:** Không, vì 31>1.5·20=30.

**Bài 2 — Cực đại.** Nếu OPT_max=80, ALG=64, tỷ lệ giữ lại?  
**Đáp án:** 64/80=0.8.

**Bài 3 — Quy ước ρ.** Một thuật toán max giữ ít nhất 0.4OPT, viết dưới dạng ρ≥1.  
**Đáp án:** ρ=1/0.4=2.5, tức ALG≥OPT/2.5.

**Bài 4 — OPT=0.** Đồ thị không cạnh, approxCover trả tập rỗng. Tính ratio ALG/OPT?  
**Đáp án:** Không định nghĩa 0/0; bất đẳng thức ALG≤2OPT vẫn đúng.

**Bài 5 — Matching.** Một matching có 7 cạnh rời nhau. Lower bound cho minimum vertex cover?  
**Đáp án:** OPT≥7.

**Bài 6 — Thuật toán 2-approx.** Nếu matching greedy có 7 cạnh, tập được chọn có bao nhiêu đỉnh?  
**Đáp án:** 14 đỉnh, nên ALG=14≤2OPT.

**Bài 7 — Ngôi sao.** Đồ thị sao với tâm 0 và ba lá, chọn cạnh (0,1) đầu tiên. Tỷ số?  
**Đáp án:** ALG=2, OPT=1, tỷ số 2.

**Bài 8 — Trọng số.** Một cạnh với hai đỉnh trọng số 1 và 1000; chọn cả hai có còn 2-approx không?  
**Đáp án:** Không; giá 1001 so với OPT=1.

**Bài 9 — Maximum Coverage.** Với U có 8 phần tử và tập ví dụ Suboptimal, greedy chọn những tập nào?  
**Đáp án:** S0 rồi S2, phủ 7 phần tử; OPT=8.

**Bài 10 — Bound k=2.** Tính 1−(1−1/k)^k.  
**Đáp án:** Với k=2, bằng 3/4.

**Bài 11 — Bound k=1.** Tính β₁.  
**Đáp án:** 1; chọn tập có gain lớn nhất chính là tối ưu khi ngân sách 1.

**Bài 12 — Budget 0.** Nếu k=0, được chọn mấy tập và có thể in ALG/OPT không?  
**Đáp án:** Chọn 0, ALG=OPT=0; ratio 0/0 không định nghĩa.

**Bài 13 — Marginal gain.** Một tập có 9 phần tử nhưng 7 đã phủ, gain bằng bao nhiêu?  
**Đáp án:** 2.

**Bài 14 — Submodularity.** Khi đã chọn thêm nhiều tập, marginal gain của một tập cố định có thể tăng không?  
**Đáp án:** Không, với hàm union cardinality đơn điệu submodular.

**Bài 15 — Lower bound.** Bài min có ALG=18, LB=12>0; certified ratio?  
**Đáp án:** ALG/OPT≤18/12=1.5.

**Bài 16 — Upper bound.** Bài max có ALG=40, UB=50>0; certified fraction?  
**Đáp án:** ALG/OPT≥40/50=0.8.

**Bài 17 — Additive.** Min ALG≤OPT+5 khác nhân như thế nào?  
**Đáp án:** Phụ thuộc đơn vị/thang đo; không có hệ số nhân cố định trên mọi OPT>0.

**Bài 18 — PTAS/FPTAS.** Một thuật toán có thời gian n^{1/ε} cho mỗi ε cố định; có chắc là FPTAS không?  
**Đáp án:** Không; số mũ của n phụ thuộc 1/ε, không chứng minh đa thức đồng thời theo n và 1/ε.

**Bài 19 — Randomized.** E[ALG]≥0.8OPT có nghĩa mọi run đạt ≥0.8OPT không?  
**Đáp án:** Không, kỳ vọng không bảo đảm từng run.

**Bài 20 — Heuristic.** Chạy 1000 bộ dữ liệu thấy nghiệm trung bình đạt 98% OPT; có thể tuyên bố 0.98-approx cho mọi input không?  
**Đáp án:** Không, cần chứng minh worst-case.

**Bài 21 — Chứng minh.** Tại sao Vertex Cover proof phải chứng minh output phủ mọi cạnh trước khi đánh giá |C|?  
**Đáp án:** Vì tỷ số chỉ so các nghiệm khả thi.

**Bài 22 — Ngân sách.** Nếu Maximum Coverage chọn k+1 tập và phủ toàn bộ U, có đạt guarantee không?  
**Đáp án:** Không, nghiệm vi phạm ràng buộc ≤k.

**Bài 23 — Lower/upper.** Với min cần bound loại nào để chứng nhận ratio, và max cần loại nào?  
**Đáp án:** Min cần lower bound, max cần upper bound.

**Bài 24 — Lập trình.** Viết brute-force small-instance cho hai bài để so random test.  
**Gợi ý:** Duyệt bitmask đỉnh cho Vertex Cover và bitmask tập cho Maximum Coverage; chỉ dùng trên n/m nhỏ.

## 34. Checklist áp dụng và kết luận

Trước khi dùng hoặc phát biểu một bảo đảm xấp xỉ:

1. **Xác định rõ bài min hay max**.
2. **Định nghĩa F(I) và hàm mục tiêu**, xử lý input vô nghiệm/unbounded khi cần.
3. **Kiểm tra nghiệm trả về khả thi**, không chỉ đánh giá cost.
4. **Viết OPT và ALG bằng ký hiệu riêng**, tránh thay lẫn.
5. **Chọn đúng chiều:** min ALG≤ρOPT; max ALG≥βOPT.
6. **Ghi rõ ρ≥1, β∈(0,1] và quy ước ratio**.
7. **Xử lý OPT=0**, không chia 0/0.
8. **Xử lý mục tiêu âm hoặc dịch gốc**, không áp dụng tỷ số nhân vô điều kiện.
9. **Phân biệt bảo đảm nhân, cộng, bicriteria và xác suất**.
10. **Chứng minh thuật toán tạo nghiệm hợp lệ** trên mọi input thuộc phạm vi.
11. **Tìm lower bound cho min hoặc upper bound cho max**, hoặc chứng minh tiến triển trực tiếp.
12. **Nêu giả thiết input**, ví dụ graph không trọng số, sets không có phần tử lặp, ngân sách cardinality k.
13. **Phân biệt maximal và maximum matching** trong proof Vertex Cover.
14. **Đếm marginal gain đúng** trong Maximum Coverage.
15. **Đừng dùng guarantee 1−1/e cho biến thể có constraints khác** khi chưa chứng minh.
16. **Phân biệt worst-case guarantee và chất lượng đo được**.
17. **Nếu randomized, nói rõ expectation hay high probability**.
18. **Nếu PTAS/FPTAS, ghi rõ độ phức tạp theo ε**.
19. **Không trộn chi phí brute-force oracle vào chi phí thuật toán xấp xỉ**.
20. **Kiểm thử rỗng, k=0, OPT=0, duplicate, đồ thị sao, tập chồng lấp và ca greedy suboptimal**.
21. **Đối chiếu ngẫu nhiên bằng exact oracle cho instance nhỏ**, nhưng không lấy random test làm proof.
22. **Khi OPT không biết, báo một cận được chứng nhận thay vì giả ratio thật**.
23. **Đánh giá bộ nhớ/thời gian và chất lượng cùng lúc**, phù hợp bài thực tế.
24. **Ghi rõ giới hạn của chứng minh**, không mở rộng sang input trọng số hoặc không đơn điệu.

**Kết luận:** một bảo đảm xấp xỉ là **cam kết toán học về chất lượng của nghiệm khả thi**. Với bài **cực tiểu**, kết quả phải không vượt quá một bội số của OPT; với bài **cực đại**, kết quả phải đạt ít nhất một phần OPT. Cách dựng cận dưới matching cho Vertex Cover và dùng marginal gain/submodularity cho Maximum Coverage cho thấy kỹ thuật xấp xỉ không chỉ là “tham lam chạy nhanh”, mà là **tham lam đi kèm chứng minh lượng hóa mức gần tối ưu**.
