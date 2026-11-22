# Co giãn giá trị cho lược đồ xấp xỉ bài toán ba lô

**Co giãn giá trị** (*value scaling*, *profit scaling*) là một kỹ thuật quan trọng để thiết kế **lược đồ xấp xỉ thời gian đa thức đầy đủ** (*Fully Polynomial-Time Approximation Scheme — FPTAS*) cho **bài toán ba lô 0/1** (*0/1 Knapsack*). Ý tưởng là **giữ nguyên trọng lượng và sức chứa**, nhưng thay các giá trị lợi ích lớn bằng những giá trị nguyên nhỏ hơn sau khi **chia cho một hệ số K rồi lấy phần nguyên xuống**. Nhờ vậy, thay vì quy hoạch động theo tổng lợi ích rất lớn, ta làm quy hoạch động trên miền lợi ích đã co giãn, được chặn bởi đa thức theo số vật phẩm n và \(1/\varepsilon\).

Đây không chỉ là một thủ thuật giảm RAM: một FPTAS cần đồng thời thỏa mãn hai yêu cầu:

1. **Tính khả thi:** nghiệm trả về không vượt sức chứa W.
2. **Bảo đảm xấp xỉ:** với mọi \(\varepsilon\in(0,1]\), nếu OPT là giá trị tối ưu và ALG là giá trị của nghiệm trả về, thì:

\[
\boxed{(1-\varepsilon)\,OPT\le ALG\le OPT.}
\]

Ngoài ra, thời gian chạy phải **đa thức theo độ dài đầu vào và \(1/\varepsilon\)**. Đó là điểm phân biệt FPTAS với một thuật toán gần đúng không có bảo đảm hoặc một thuật toán giả đa thức phụ thuộc trực tiếp vào giá trị số của các lợi ích.

Bài học này trình bày đúng phạm vi **bài toán ba lô 0/1 với trọng lượng và giá trị không âm**, chứng minh bảo đảm \(1-\varepsilon\), giải thích cách chọn hệ số K dựa trên **giá trị vật phẩm khả thi lớn nhất**, cài **DP theo tổng lợi ích đã co giãn**, kiểm soát trường hợp làm tròn về 0, các bẫy về số thực và tràn số, rồi xây dựng chương trình **Java 17+ chạy độc lập** dùng số học phân số chính xác bằng `BigInteger`. Các ví dụ được đối chiếu với nghiệm tối ưu tính bằng vét cạn ở dữ liệu nhỏ, cùng bộ kiểm chứng nhiều trường hợp có hạt giống ngẫu nhiên cố định.

## 1. Nhắc lại bài toán ba lô 0/1

Cho n vật phẩm, vật phẩm i có:

- **Trọng lượng** \(w_i\ge0\).
- **Giá trị/lợi ích** \(v_i\ge0\).
- **Sức chứa ba lô** \(W\ge0\).

Mỗi vật phẩm được **chọn tối đa một lần**. Ta cần chọn một tập chỉ số \(S\subseteq\{0,\ldots,n-1\}\) sao cho:

\[
\sum_{i\in S}w_i\le W
\]

và tối đa hóa:

\[
\boxed{V(S)=\sum_{i\in S}v_i.}
\]

Giá trị tối ưu:

\[
\boxed{OPT=\max_{\sum_{i\in S}w_i\le W}\sum_{i\in S}v_i.}
\]

Đây là bài toán **tối ưu**, không phải bài toán quyết định “có tập con tổng bằng S hay không”. Mọi nghiệm hợp lệ đều có giá trị \(\le OPT\).

### Phân biệt 0/1, unbounded và fractional knapsack

| Biến thể | Được lấy một vật phẩm bao nhiêu lần? | Có thể lấy một phần vật phẩm? | Ghi chú |
|---|---|---|---|
| **0/1 Knapsack** | 0 hoặc 1 | Không | Đối tượng chính của bài |
| **Unbounded Knapsack** | Nhiều lần | Không | Công thức trạng thái khác; không áp dụng nguyên xi chứng minh |
| **Fractional Knapsack** | Có thể lấy một phần | Có | Có thuật toán tham lam theo tỉ số giá trị/trọng lượng trong giả thiết chuẩn |

Nếu lấy nhầm thuật toán cho **fractional** rồi áp dụng cho **0/1**, nghiệm có thể yêu cầu lấy “0,4 vật phẩm”, trái yêu cầu nguyên vẹn của bài.

## 2. Vì sao bài toán cần xấp xỉ?

Ba lô 0/1 có một thuật toán quy hoạch động kinh điển theo **sức chứa** W:

\[
dpWeight[c]=\text{giá trị lớn nhất đạt được với tổng trọng lượng không vượt }c.
\]

Thời gian với ma trận đặc là \(O(nW)\), bộ nhớ có thể \(O(W)\).

Một cách khác là **DP theo tổng giá trị**. Đặt:

\[
dpValue[p]=\text{trọng lượng nhỏ nhất để đạt đúng tổng lợi ích }p.
\]

Nếu \(V=\sum_i v_i\), thuật toán cần xét p từ 0 tới V:

\[
\boxed{\text{Thời gian }O(nV),\quad\text{bộ nhớ }O(V).}
\]

Cả hai cách có thể **rất nhanh khi tham số số học nhỏ**, nhưng W hoặc V chỉ cần khoảng \(\Theta(\log W)\), \(\Theta(\log V)\) bit để được mã hóa bằng nhị phân. Nếu W hay V lớn, tạo mảng tỉ lệ với giá trị đó trở nên không thực tế.

**Ví dụ:** một vật phẩm có giá trị \(10^{12}\) chỉ cần khoảng 40 bit để lưu giá trị, nhưng mảng DP theo lợi ích \(0,\ldots,10^{12}\) cần hơn một nghìn tỷ trạng thái. Thuật toán **O(nV)** là **giả đa thức**, không phải đa thức theo số bit của V.

Giải pháp FPTAS: thay \(v_i\) bằng \(v_i'\) nhỏ hơn sao cho tổng các \(v_i'\) chỉ khoảng \(O(n^2/\varepsilon)\), đồng thời chứng minh phần giá trị thật mất đi không quá \(\varepsilon OPT\).

## 3. Định nghĩa FPTAS

Với bài toán **tối đa hóa**, một thuật toán có tham số \(\varepsilon\in(0,1]\) là một **FPTAS** nếu:

- Với mọi input hợp lệ, luôn trả một nghiệm **khả thi**.
- Giá trị nghiệm ALG thỏa:

\[
\boxed{ALG\ge(1-\varepsilon)OPT.}
\]

- Thời gian là đa thức theo **kích thước mã hóa của input** và theo **\(1/\varepsilon\)**.

### So sánh các lớp thuật toán

**Heuristic:** quy tắc kinh nghiệm có thể cho lời giải tốt, nhưng nếu không có chứng minh thì **không được tự nhận bảo đảm tỉ lệ**.

**Constant-factor approximation:** cho tỉ lệ cố định, chẳng hạn ≥1/2 OPT, độc lập với một tham số tùy ý.

**PTAS:** với mỗi \(\varepsilon>0\) cố định, chạy đa thức theo input, nhưng bậc của đa thức có thể phụ thuộc \(1/\varepsilon\). Ví dụ về mặt hình thức, thời gian \(n^{1/\varepsilon}\) là đa thức theo n khi \(\varepsilon\) cố định, nhưng **không đa thức theo \(1/\varepsilon\)**.

**FPTAS:** thêm điều kiện chạy đa thức theo \(1/\varepsilon\), ví dụ \(O(n^3/\varepsilon)\) phép toán số học với cỡ số trung gian được kiểm soát đa thức.

Điểm quan trọng: \(\varepsilon\) càng nhỏ thì chất lượng bảo đảm càng sát OPT, nhưng **thời gian và bộ nhớ có thể tăng mạnh**. Không nên đọc “FPTAS” thành “cực nhanh với mọi độ chính xác”.

## 4. Nền tảng: DP theo giá trị thật

Trước khi co giãn, xét trạng thái:

\[
D_i[p]=\text{trọng lượng nhỏ nhất để chọn từ i vật phẩm đầu và đạt đúng giá trị }p.
\]

Quy ước:

- \(D_0[0]=0\).
- \(D_0[p>0]=+\infty\), nghĩa là chưa thể đạt p.
- Với vật phẩm i có \((w_i,v_i)\):

\[
\boxed{D_{i+1}[p]=
\min\left(D_i[p],\,D_i[p-v_i]+w_i\right)}
\]

nếu \(p\ge v_i\); nếu p nhỏ hơn \(v_i\), chỉ có nhánh không chọn.

Kết quả là p lớn nhất có \(D_n[p]\le W\).

### Diễn giải trạng thái

Ở cùng một tổng lợi ích p, một nghiệm có trọng lượng 5 luôn **không kém** một nghiệm khác trọng lượng 7, vì nó để lại nhiều chỗ hơn cho các vật phẩm tiếp theo. Do đó chỉ cần giữ **trọng lượng nhỏ nhất** cho mỗi p.

Đây là lý do DP theo lợi ích là một kỹ thuật tự nhiên để tối ưu giá trị: nó giữ đúng thông tin cần thiết để kiểm điều kiện trọng lượng sau này.

### Tối ưu bộ nhớ xuống một chiều

Có thể dùng một mảng D[p] và cập nhật **p từ lớn xuống nhỏ** để mỗi vật phẩm chỉ được dùng một lần:

~~~text
D[0]=0
D[p>0]=INF

for each item (weight w, value v):
    for p from totalValue down to v:
        D[p] = min(D[p], D[p-v] + w)
~~~

Nếu duyệt p tăng dần, một trạng thái vừa tạo từ vật phẩm hiện tại có thể được dùng tiếp trong cùng lượt, vô tình biến bài toán 0/1 thành bài cho dùng vật phẩm lặp lại.

**Hạn chế:** miền p có độ dài \(V=\sum v_i\), có thể rất lớn dù input nhị phân ngắn. Co giãn giá trị giải quyết chính vấn đề này.

## 5. Chuẩn bị: lọc vật phẩm không cần thiết

Trước khi co giãn, giả sử ta có các **trọng lượng và giá trị không âm**.

Có thể bỏ:

1. Vật phẩm có \(w_i>W\): không thể nằm trong bất kỳ nghiệm khả thi nào vì trọng lượng các vật phẩm khác đều không âm.
2. Vật phẩm có \(v_i=0\): không làm tăng mục tiêu, nên bỏ đi không làm giảm giá trị tối ưu. Điều này đúng cả khi trọng lượng bằng 0.

Gọi **m** là số vật phẩm **còn lại**. Khi ấy mỗi vật phẩm được giữ có:

\[
0\le w_i\le W,\qquad v_i>0.
\]

Nếu m=0 thì không có vật phẩm lợi ích dương nào khả thi. Tập rỗng có giá trị 0 và là nghiệm tối ưu, nên trả **0** ngay.

### Vì sao lọc trước lại quan trọng cho chứng minh?

Ta đặt:

\[
\boxed{P=\max_{1\le i\le m}v_i.}
\]

Vì từng vật phẩm giữ lại đều **tự nó vừa ba lô**, nên có ít nhất một nghiệm khả thi là **chọn riêng vật phẩm có giá trị P**. Do đó:

\[
\boxed{0<P\le OPT.}
\]

Bất đẳng thức \(P\le OPT\) là cầu nối quan trọng để chuyển một cận lỗi dựa trên P thành cận lỗi dựa trên OPT.

**Sai lầm nguy hiểm:** nếu chọn P là giá trị của **một vật phẩm quá nặng và không thể chọn**, có thể xảy ra P≫OPT; khi ấy cận \(\varepsilon P\) không còn bảo đảm nhỏ hơn \(\varepsilon OPT\). Vì vậy trong cách chọn K của bài, **P phải lấy trên các vật phẩm khả thi riêng lẻ**.

## 6. Chọn hệ số co giãn K

Với m>0 và \(\varepsilon\in(0,1]\), đặt:

\[
\boxed{K=\frac{\varepsilon P}{m}.}
\]

Định nghĩa **giá trị sau co giãn**:

\[
\boxed{q_i=\left\lfloor\frac{v_i}{K}\right\rfloor.}
\]

Mỗi \(q_i\) là số nguyên không âm. Ta giải một bài toán ba lô 0/1 **mới** có:

- **Trọng lượng giữ nguyên** \(w_i\).
- **Lợi ích dùng cho DP** là \(q_i\).

Sau khi tìm một tập con có tổng q lớn nhất dưới ràng buộc trọng lượng, ta **đánh giá kết quả bằng tổng giá trị thật \(\sum v_i\)** của các vật phẩm đã chọn, chứ không coi tổng q là giá trị tiền/lợi ích gốc.

### Phân biệt q_i và v_i

Ví dụ nếu K=2, giá trị gốc 17 sẽ thành:

\[
q_i=\lfloor17/2\rfloor=8.
\]

Nếu K=3, giá trị gốc 17 thành:

\[
q_i=\lfloor17/3\rfloor=5.
\]

Con số q chỉ là **điểm lợi ích đã chuẩn hóa** để DP; nó không còn cùng đơn vị với v.

### Vì sao dùng floor, không làm tròn gần nhất?

Với floor:

\[
\boxed{Kq_i\le v_i<K(q_i+1).}
\]

Hay:

\[
\boxed{v_i-K<v_i^\text{scaled}\cdot K\le v_i}
\]

với \(v_i^\text{scaled}=q_i\). Như vậy lỗi giảm của mỗi vật phẩm là **nhỏ hơn K**, dễ cộng dồn để chứng minh mất mát tối đa mK.

Nếu thay floor bằng round hoặc ceil mà không thay lập luận, các bất đẳng thức dùng trong chứng minh có thể không còn đúng. Một FPTAS phải gắn **quy tắc làm tròn** với **chứng minh bảo đảm**.

## 7. Co giãn làm tổng lợi ích DP nhỏ đi thế nào?

Với mỗi vật phẩm giữ lại:

\[
v_i\le P.
\]

Do đó:

\[
q_i=\left\lfloor\frac{v_i}{K}\right\rfloor
\le \frac P K
=\frac{m}{\varepsilon}.
\]

Tổng giá trị đã co giãn:

\[
Q=\sum_{i=1}^{m}q_i.
\]

Suy ra:

\[
\boxed{Q\le\frac{m^2}{\varepsilon}.}
\]

Đây là ý tưởng trung tâm của FPTAS: **Q không phụ thuộc trực tiếp vào độ lớn của các v_i**, mà bị chặn bởi m và \(1/\varepsilon\).

Nếu chạy DP theo tổng q:

\[
\boxed{T=O(mQ)=O(m^3/\varepsilon)}
\]

và dùng mảng một chiều:

\[
\boxed{M=O(Q)=O(m^2/\varepsilon).}
\]

Cận này chưa tính chi phí bit của phép toán số lớn, nhưng với cách tính số nguyên đa độ chính xác hợp lý thì tổng thể vẫn đa thức theo kích thước input và \(1/\varepsilon\).

### Ví dụ về số lượng trạng thái

Nếu m=100 và \(\varepsilon=0.1\), cận tổng quát là:

\[
Q\le100^2/0.1=100\,000.
\]

Nếu các giá trị gốc là cỡ \(10^{12}\) hoặc \(10^{15}\), **cận trên Q này không vì thế tăng lên \(10^{15}\)**. Giá trị thật chỉ ảnh hưởng chi phí số học, còn **số trạng thái DP** được khống chế bởi m và ε.

Cần hiểu đây là **cận trên**, không phải dự báo rằng mọi input sẽ dùng đúng 100.000 trạng thái; Q thật có thể nhỏ hơn nhiều.

## 8. DP theo lợi ích đã co giãn

Gọi:

\[
D[s]=\text{trọng lượng nhỏ nhất của một tập con có tổng lợi ích co giãn đúng }s.
\]

Khởi tạo:

\[
D[0]=0,\qquad D[s>0]=+\infty.
\]

Với mỗi vật phẩm \((w_i,q_i)\), cập nhật:

\[
\boxed{
D_{\text{mới}}[s]
=\min\!\left(D_{\text{cũ}}[s],D_{\text{cũ}}[s-q_i]+w_i\right)
}
\]

khi \(s\ge q_i\).

Dùng mảng một chiều, duyệt s **giảm dần**:

~~~text
D[0] = 0
D[s>0] = unreachable

for item i:
    for s descending from currentMax + q_i to q_i:
        if D[s-q_i] is reachable:
            candidateWeight = D[s-q_i] + w_i

            if candidateWeight <= W:
                D[s] = min(D[s], candidateWeight)

answerScaled = largest s with D[s] <= W
~~~

Ở đây có thể **bỏ qua các trạng thái vượt W** ngay từ đầu, vì trọng lượng đều không âm: thêm vật phẩm sau sẽ không giảm trọng lượng. Điều này vẫn giữ nguyên tính đúng.

### Trường hợp q_i=0

Một vật phẩm có giá trị thật v_i>0 nhưng quá nhỏ so với K có thể trở thành:

\[
q_i=0.
\]

Trong mã minh họa, các vật phẩm như vậy được **bỏ qua ở pha DP**. Điều này không vi phạm đảm bảo xấp xỉ: mỗi vật phẩm bị giảm chưa tới K giá trị, và chứng minh sai số tổng đã tính cả khả năng này.

Nếu bạn muốn đạt chất lượng tốt hơn, có thể thiết kế tie-break bổ sung để giữ những vật phẩm q=0 (nhất là trọng lượng 0), nhưng khi đó phải cẩn thận giữ tính đúng của trạng thái và không tăng chi phí ngoài mức phân tích.

Mã demo chọn **quy tắc đơn giản, dễ chứng minh**: bỏ qua vật phẩm q=0. Điều này có thể khiến lời giải xấp xỉ **không đạt OPT ngay cả khi ba lô còn chỗ**, nhưng vẫn thỏa cận \(1-\varepsilon\).

## 9. Chứng minh bảo đảm xấp xỉ 1−ε

Đây là phần quan trọng nhất của bài. Ta chỉ xét m>0; trường hợp m=0 đã giải tối ưu bằng tập rỗng.

Ký hiệu:

- \(S^\star\) là một tập con tối ưu của các vật phẩm đã lọc.
- \(OPT=V(S^\star)=\sum_{i\in S^\star}v_i\).
- \(q(S)=\sum_{i\in S}q_i\).
- \(S_A\) là tập con khả thi có **tổng q lớn nhất** do DP theo lợi ích co giãn xác định.
- \(ALG=V(S_A)\) là **giá trị thật** của nghiệm đó.

Từ định nghĩa floor:

\[
q_i=\left\lfloor\frac{v_i}{K}\right\rfloor
\ge\frac{v_i}{K}-1.
\]

Nhân hai vế với K:

\[
\boxed{Kq_i\ge v_i-K.}
\]

Cộng cho các vật phẩm thuộc \(S^\star\):

\[
Kq(S^\star)\ge
\sum_{i\in S^\star}v_i-|S^\star|K.
\]

Vì \(|S^\star|\le m\):

\[
\boxed{Kq(S^\star)\ge OPT-mK.}
\]

DP chọn nghiệm có tổng q lớn nhất trong các tập khả thi, nên:

\[
q(S_A)\ge q(S^\star).
\]

Mặt khác, do làm tròn xuống:

\[
v_i\ge Kq_i,
\]

suy ra:

\[
ALG=V(S_A)\ge Kq(S_A).
\]

Ghép ba bất đẳng thức:

\[
ALG\ge Kq(S_A)
\ge Kq(S^\star)
\ge OPT-mK.
\]

Thế \(K=\varepsilon P/m\):

\[
ALG\ge OPT-\varepsilon P.
\]

Do **P≤OPT**:

\[
OPT-\varepsilon P\ge OPT-\varepsilon OPT.
\]

Vậy:

\[
\boxed{ALG\ge(1-\varepsilon)OPT.}
\]

Đồng thời vì \(S_A\) vẫn là tập con thỏa sức chứa, luôn có:

\[
\boxed{ALG\le OPT.}
\]

**Kết luận:** thuật toán trả nghiệm khả thi và có bảo đảm xấp xỉ **tối thiểu \(1-\varepsilon\) lần tối ưu**.

### Chứng minh không yêu cầu các giá trị gần nhau

Các giá trị \(v_i\) có thể chênh lệch rất lớn. Điều kiện thiết yếu là **P được lấy từ vật phẩm khả thi**, **K chọn đúng**, **floor chính xác**, và DP giải đúng bài tối ưu theo q trên cùng trọng lượng và sức chứa W.

### Bảo đảm là cận xấu nhất, không phải giá trị kỳ vọng

Đây là **bảo đảm tất định**, áp dụng cho mọi đầu vào trong mô hình, không dựa vào xác suất. Nếu ε=0.2, ta có ALG≥0.8 OPT, không phải “trung bình trên các lần chạy đạt 80% OPT”.

## 10. Ví dụ tính tay: co giãn nhưng vẫn tối ưu

Cho:

| Vật phẩm | Trọng lượng w | Giá trị v |
|---|---:|---:|
| A | 4 | 7 |
| B | 5 | 8 |
| C | 6 | 9 |
| D | 3 | 4 |

Sức chứa \(W=10\). Chọn \(\varepsilon=1/2\).

Cả bốn vật phẩm đều vừa riêng lẻ, nên m=4 và:

\[
P=9,\qquad K=\frac{(1/2)\cdot9}{4}=\frac98=1.125.
\]

Tính q:

\[
\begin{aligned}
q_A&=\lfloor7/(9/8)\rfloor=\lfloor56/9\rfloor=6,\\
q_B&=\lfloor8/(9/8)\rfloor=\lfloor64/9\rfloor=7,\\
q_C&=\lfloor9/(9/8)\rfloor=8,\\
q_D&=\lfloor4/(9/8)\rfloor=\lfloor32/9\rfloor=3.
\end{aligned}
\]

Bảng sau co giãn:

| Vật phẩm | w gốc | v gốc | q đã co giãn |
|---|---:|---:|---:|
| A | 4 | 7 | 6 |
| B | 5 | 8 | 7 |
| C | 6 | 9 | 8 |
| D | 3 | 4 | 3 |

Tổng q của mọi vật phẩm là \(Q=6+7+8+3=24\), nên DP chỉ cần 25 trạng thái \([0,24]\).

Các cặp đáng xét:

- A+B: trọng lượng 9, giá trị thật 15, tổng q=13.
- A+C: trọng lượng 10, giá trị thật 16, tổng q=14.
- B+D: trọng lượng 8, giá trị thật 12, tổng q=10.
- C+D: trọng lượng 9, giá trị thật 13, tổng q=11.
- B+C: trọng lượng 11, không khả thi.

Nghiệm tốt nhất là **A+C**, có:

\[
\boxed{ALG=16,\quad\text{weight}=10,\quad q=14.}
\]

Trong ví dụ này:

\[
OPT=16
\]

nên thuật toán xấp xỉ **tình cờ đạt tối ưu thật**. FPTAS chỉ cam kết ≥8 khi ε=1/2 và OPT=16; không hứa rằng mọi instance sẽ tối ưu.

## 11. Ví dụ làm tròn gây mất giá trị thật

Xét một input khác:

~~~text
weights = [6, 1, 2, 5]
values  = [23, 2, 16, 10]
capacity = 4
epsilon = 1/2
~~~

Vật phẩm trọng lượng 6 và 5 **quá nặng**, được bỏ trước. Chỉ còn:

~~~text
weight: [1,2]
value:  [2,16]
~~~

Do đó:

\[
m=2,\qquad P=16,\qquad K=(1/2)\cdot16/2=4.
\]

Giá trị co giãn:

\[
q=[\lfloor2/4\rfloor,\lfloor16/4\rfloor]=[0,4].
\]

Vì vật phẩm giá trị 2 bị làm tròn thành q=0, cách triển khai trong bài bỏ qua nó ở DP. Thuật toán chọn vật phẩm có:

\[
\boxed{ALG=16,\qquad weight=2,\qquad q=4.}
\]

Nhưng nghiệm tối ưu thật là chọn **cả hai vật phẩm khả thi**, tổng trọng lượng 3≤4, giá trị:

\[
\boxed{OPT=2+16=18.}
\]

Vậy đây là một ví dụ thật sự **không đạt tối ưu**:

\[
ALG=16<18=OPT.
\]

Tuy nhiên với ε=1/2, cận yêu cầu chỉ là:

\[
(1-\varepsilon)OPT=9,
\]

và 16≥9 nên vẫn đúng bảo đảm. Trên thực tế tỉ lệ của ví dụ là:

\[
ALG/OPT=16/18\approx0.8889.
\]

Cần phân biệt **cận xấu nhất đã chứng minh** với **tỉ lệ thực tế** trên một input.

### Vì sao không tự cộng thêm vật phẩm q=0?

Về mặt ý tưởng, nếu đã có nghiệm tốt nhất theo q và còn sức chứa, có thể đôi lúc thêm một vật phẩm có q=0 mà tăng lợi ích thật. Nhưng muốn thuật toán giữ các trạng thái tổng quát và có chứng minh, cần quản lý cách tái tạo nghiệm/tie-break và cấu trúc DP nhất quán.

Bản demo ưu tiên quy tắc **bỏ qua q=0** để làm nổi bật kỹ thuật làm tròn và cận mất mát. Điều này không phải bug, mà là một lựa chọn thiết kế đã được chứng minh.

## 12. Chọn P và K sai có thể phá bảo đảm

### P phải dựa trên các vật phẩm khả thi

Giả sử một vật phẩm có giá trị \(10^9\) nhưng trọng lượng \(10^9\), trong khi ba lô chỉ chứa được 10; các vật phẩm thực tế vừa ba lô có giá trị 5–20.

Nếu lấy P=\(10^9\) từ **toàn input** thay vì lọc vật phẩm quá nặng, ta sẽ chọn K rất lớn, làm q của hầu hết vật phẩm khả thi thành 0. Cận mất mát \(\varepsilon P\) trở nên vô ích vì P không còn ≤OPT.

**Cách đúng:** loại những vật phẩm có w>W rồi lấy P lớn nhất từ các vật phẩm còn lại với v>0.

### Không được làm tròn K lên một cách tùy tiện

Với công thức:

\[
K=\varepsilon P/m,
\]

nếu tự thay K bằng \(\max(1,\lfloor K\rfloor)\), có thể làm K **lớn hơn** giá trị mong muốn khi \(K<1\). Khi đó mK có thể vượt εP, làm hỏng bước chứng minh:

\[
mK\le\varepsilon P.
\]

Làm tròn K theo hướng khác cũng phải được phân tích riêng. Cách an toàn của bài là **không làm tròn K về số nguyên**: dùng **phân số chính xác** khi tính \(q_i\).

### Tránh sai số double làm đổi floor

Nếu K là phân số như \(9/8\), công thức \(\lfloor v_i/K\rfloor\) có thể được tính đúng bằng **số nguyên**.

Nếu ε được nhập dưới dạng phân số \(p/q\), với \(0<p\le q\), thì:

\[
K=\frac{pP}{qm}.
\]

Vì vậy:

\[
\boxed{
q_i=\left\lfloor\frac{v_i\,q\,m}{p\,P}\right\rfloor.
}
\]

Tử số và mẫu số đều là **số nguyên**, và phép chia nguyên cho số dương chính là floor.

Bản Java dùng `BigInteger` để tính các tích:

~~~java
BigInteger numerator =
    BigInteger.valueOf(value)
        .multiply(BigInteger.valueOf(epsilonDenominator))
        .multiply(BigInteger.valueOf(m));

BigInteger denominator =
    BigInteger.valueOf(epsilonNumerator)
        .multiply(BigInteger.valueOf(P));

int scaled = numerator.divide(denominator).intValueExact();
~~~

**Lợi ích:** tránh lỗi `double` nằm sát ranh giới nguyên và tránh tràn khi nhân nhiều `long`. Chính sách budget phải được kiểm **trước** khi ép kết quả BigInteger sang int.

## 13. Tại sao trong DP phải giữ trọng lượng nhỏ nhất?

Sau co giãn, nhiều tập vật phẩm khác nhau có thể có cùng tổng q.

Ví dụ:

~~~text
Subset X: scaled sum = 15, weight = 8
Subset Y: scaled sum = 15, weight = 6
~~~

Đối với các vật phẩm chưa xét, **Y chiếm ít chỗ hơn**, nên mọi phần mở rộng khả thi từ X cũng có thể mở rộng từ Y (với trọng lượng không âm). Vì vậy chỉ cần giữ nghiệm có **trọng lượng nhỏ nhất** cho cùng s.

Mã còn lưu một trường `actualValue[s]` đi kèm trọng lượng đại diện. Khi có hai nghiệm cùng s **và cùng trọng lượng**, mã ưu tiên nghiệm có giá trị thật lớn hơn. Điều này có thể làm kết quả thực tế tốt hơn, nhưng **không cần thiết** cho chứng minh tỉ lệ FPTAS.

### Vì sao chỉ lưu actualValue không đủ?

Nếu chỉ tối đa hóa lợi ích gốc trong mỗi trạng thái s mà bỏ qua trọng lượng, một nghiệm có lợi ích gốc lớn hơn nhưng quá nặng có thể chặn nghiệm nhẹ hơn cần thiết cho việc ghép các vật phẩm sau.

**Ưu tiên đúng của trạng thái:** trước hết **minWeight[s]**, sau đó mới dùng giá trị thật làm tie-break khi trọng lượng bằng nhau.

### Tính khả thi được bảo toàn

Khi thử thêm vật phẩm i vào trạng thái s cũ, ta chỉ chấp nhận khi:

\[
minWeight[s]+w_i\le W.
\]

Vì các trọng lượng không âm, không có chuyện một trạng thái vượt W ở hiện tại trở thành khả thi bằng cách thêm vật phẩm ở tương lai. Do đó có thể bỏ trạng thái vượt W.

Để tránh phép cộng `long` bị tràn, dùng kiểm tra:

~~~java
if (minWeight[old] > capacity - item.weight()) {
    continue;
}
long candidateWeight = minWeight[old] + item.weight();
~~~

Điều này an toàn vì item.weight() đã được kiểm \(\le capacity\) và cả hai đều không âm. Nếu không có điều kiện trước, `minWeight+weight` có thể wrap-around sang âm rồi bị coi là nhẹ một cách sai lầm.

## 14. Trình tự triển khai tổng quát

Với n vật phẩm, capacity W và ε=p/q:

**Bước 1.** Kiểm input: hai mảng cùng độ dài, \(w_i,v_i\ge0\), \(W\ge0\), \(0<p\le q\).

**Bước 2.** Bỏ vật phẩm \(w_i>W\) hoặc \(v_i=0\). Nếu không còn vật phẩm, trả nghiệm rỗng giá trị 0.

**Bước 3.** Tính m số vật phẩm giữ lại và \(P=\max v_i\) trên chúng.

**Bước 4.** Tính chính xác:

\[
q_i=\left\lfloor\frac{v_iqm}{pP}\right\rfloor
\]

bằng số học nguyên không tràn, không dùng phép làm tròn gần nhất.

**Bước 5.** Tính tổng trạng thái:

\[
Q=\sum_i q_i.
\]

Kiểm Q nằm trong ngân sách RAM/thời gian nếu là chương trình thực tế.

**Bước 6.** Khởi tạo `reachable[0]=true`, `minWeight[0]=0`, `actualValue[0]=0`; các s khác chưa thể đạt.

**Bước 7.** Duyệt từng vật phẩm có q>0, cập nhật s **giảm dần** từ tổng q đã xét tới q_i, chỉ nhận trạng thái có trọng lượng ≤W. Nếu cùng s chọn trọng lượng thấp nhất; nếu trọng lượng bằng nhau có thể chọn giá trị gốc cao hơn.

**Bước 8.** Lấy s lớn nhất có `reachable[s]=true`. Trả **giá trị thật và trọng lượng** được lưu ở trạng thái đó.

### Dữ liệu chương trình trả ra

Mã Java minh họa trả:

- `value`: tổng lợi ích **thật** của một nghiệm khả thi;
- `weight`: tổng trọng lượng của **cùng nghiệm đó**;
- `scaledProfit`: tổng q của nghiệm;
- `stateCount`: số vị trí DP đã cấp phát;
- `eligibleItems`: số vật phẩm còn lại sau lọc.

Nó **không trả danh sách chỉ số vật phẩm đã chọn**. Để truy hồi tập vật phẩm cụ thể, cần bổ sung cấu trúc truy vết sao cho những trạng thái bị ghi đè không làm hỏng chuỗi predecessor; ví dụ dùng bảng DP theo lớp O(mQ) bộ nhớ hoặc một thiết kế truy hồi tương đương. Không được suy diễn chỉ số vật phẩm từ riêng giá trị kết quả.

## 15. Java 17+: FPTAS với phân số ε chính xác

Chương trình **KnapsackValueScalingFptasDemo.java** triển khai FPTAS theo profit scaling và kèm kiểm thử độc lập. Điểm chủ ý của thiết kế:

- Nhập \(\varepsilon=p/q\) bằng **hai số nguyên dương**, \(0<p\le q\).
- Dùng `BigInteger` để tính đúng floor của \(\frac{v_iqm}{pP}\).
- Không thay đổi trọng lượng gốc, không dùng `double` để làm tròn q.
- Giải DP theo q bằng ba mảng một chiều: `reachable`, `minWeight` và `actualValue`; dùng **duyệt giảm dần**.
- Đặt `MAX_SCALED_SUM=150_000` làm **giới hạn tài nguyên bản demo**. Nếu vượt, ném lỗi **thay vì trả một nghiệm giả**; đây không phải giới hạn lý thuyết của FPTAS.
- Dùng `Math.addExact` ở phép cộng giá trị gốc để phát hiện tràn `long`.
- Có oracle vét cạn cho **n≤20**, kiểm chính xác OPT và kiểm rằng cặp `(weight,value)` trả ra thực sự đến từ ít nhất một tập con.
- Kiểm giới hạn bảo đảm bằng **số nguyên BigInteger**, tránh sai số floating point trong so sánh \((1-\varepsilon)OPT\).
- Gồm ví dụ đạt tối ưu, ví dụ mất lợi ích do rounding, vật phẩm trọng lượng 0, đầu vào rỗng, giới hạn RAM và test ngẫu nhiên.

~~~java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class KnapsackValueScalingFptasDemo {
    static final int MAX_SCALED_SUM = 150_000;

    record Item(long weight, long value) {}

    record Approximation(
        long value,
        long weight,
        int scaledProfit,
        int stateCount,
        int eligibleItems
    ) {}

    static void checkInput(
        long[] weights, long[] values, long capacity,
        int epsilonNumerator, int epsilonDenominator
    ) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");

        if (weights.length != values.length || capacity < 0) {
            throw new IllegalArgumentException(
                "weights/values length mismatch or negative capacity"
            );
        }
        if (epsilonNumerator <= 0
                || epsilonDenominator <= 0
                || epsilonNumerator > epsilonDenominator) {
            throw new IllegalArgumentException(
                "epsilon must satisfy 0 < numerator <= denominator"
            );
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] < 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                    "weights and values must be nonnegative"
                );
            }
        }
    }

    // Guaranteed (1-epsilon)*OPT <= result.value <= OPT
    // if this method completes without a resource/arithmetic error.
    static Approximation approximate(
        long[] weights, long[] values, long capacity,
        int epsilonNumerator, int epsilonDenominator
    ) {
        checkInput(
            weights, values, capacity,
            epsilonNumerator, epsilonDenominator
        );

        List<Item> eligible = new ArrayList<>();
        long maxFeasibleValue = 0L;

        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= capacity && values[i] > 0) {
                eligible.add(new Item(weights[i], values[i]));
                maxFeasibleValue =
                    Math.max(maxFeasibleValue, values[i]);
            }
        }

        int m = eligible.size();
        if (m == 0) {
            return new Approximation(0L, 0L, 0, 1, 0);
        }

        // K = (epsilonNumerator * P) /
        //     (epsilonDenominator * m)
        // scaled_i = floor(value_i / K), exactly.
        BigInteger numerator = BigInteger
            .valueOf(epsilonNumerator)
            .multiply(BigInteger.valueOf(maxFeasibleValue));
        BigInteger denominator = BigInteger
            .valueOf(epsilonDenominator)
            .multiply(BigInteger.valueOf(m));

        int[] scaled = new int[m];
        int totalScaled = 0;
        BigInteger budget = BigInteger.valueOf(MAX_SCALED_SUM);

        for (int i = 0; i < m; i++) {
            BigInteger exactScaled = BigInteger
                .valueOf(eligible.get(i).value())
                .multiply(denominator)
                .divide(numerator);

            if (exactScaled.compareTo(budget) > 0) {
                throw new IllegalArgumentException(
                    "scaled DP exceeds demo budget (150000)"
                );
            }

            int q = exactScaled.intValueExact();
            if (q > MAX_SCALED_SUM - totalScaled) {
                throw new IllegalArgumentException(
                    "scaled DP exceeds demo budget (150000)"
                );
            }
            scaled[i] = q;
            totalScaled += q;
        }

        // Three arrays of length totalScaled+1, not capacity+1.
        boolean[] reachable = new boolean[totalScaled + 1];
        long[] minWeight = new long[totalScaled + 1];
        long[] actualValue = new long[totalScaled + 1];
        reachable[0] = true;

        int currentMax = 0;
        for (int i = 0; i < m; i++) {
            Item item = eligible.get(i);
            int q = scaled[i];

            // Discard q=0 items. The rounding-loss proof covers them.
            if (q == 0) {
                continue;
            }

            currentMax += q;

            // Descending => current item used at most once.
            for (int score = currentMax; score >= q; score--) {
                int previous = score - q;

                if (!reachable[previous]) {
                    continue;
                }

                // Avoid long overflow and reject overweight subsets.
                if (minWeight[previous]
                        > capacity - item.weight()) {
                    continue;
                }

                long candidateWeight =
                    minWeight[previous] + item.weight();
                long candidateValue = Math.addExact(
                    actualValue[previous], item.value()
                );

                if (!reachable[score]
                        || candidateWeight < minWeight[score]
                        || (candidateWeight == minWeight[score]
                            && candidateValue > actualValue[score])) {
                    reachable[score] = true;
                    minWeight[score] = candidateWeight;
                    actualValue[score] = candidateValue;
                }
            }
        }

        // Largest reachable scaled score is optimal for scaled problem.
        for (int score = totalScaled; score >= 0; score--) {
            if (reachable[score]) {
                return new Approximation(
                    actualValue[score],
                    minWeight[score],
                    score,
                    totalScaled + 1,
                    m
                );
            }
        }
        throw new AssertionError("empty subset unexpectedly absent");
    }

    // Oracle: only for n<=20, exponential in number of items.
    static long bruteOptimum(
        long[] weights, long[] values, long capacity
    ) {
        if (weights.length > 20) {
            throw new IllegalArgumentException(
                "brute oracle only supports <=20 items"
            );
        }

        long best = 0L;
        int possibilities = 1 << weights.length;
        for (int mask = 0; mask < possibilities; mask++) {
            long weight = 0L;
            long value = 0L;
            boolean fits = true;

            for (int i = 0; i < weights.length; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                if (weights[i] > capacity - weight) {
                    fits = false;
                    break;
                }
                weight += weights[i];
                value = Math.addExact(value, values[i]);
            }

            if (fits) {
                best = Math.max(best, value);
            }
        }
        return best;
    }

    // Independent witness oracle: verify value AND weight match
    // an actual subset, not merely two unrelated possible totals.
    static boolean bruteHasWitness(
        long[] weights, long[] values, long capacity,
        long requiredWeight, long requiredValue
    ) {
        if (weights.length > 20) {
            throw new IllegalArgumentException(
                "brute oracle only supports <=20 items"
            );
        }

        int possibilities = 1 << weights.length;
        for (int mask = 0; mask < possibilities; mask++) {
            long weight = 0L;
            long value = 0L;
            boolean fits = true;

            for (int i = 0; i < weights.length; i++) {
                if ((mask & (1 << i)) == 0) {
                    continue;
                }
                if (weights[i] > capacity - weight) {
                    fits = false;
                    break;
                }
                weight += weights[i];
                value = Math.addExact(value, values[i]);
            }

            if (fits && weight == requiredWeight
                    && value == requiredValue) {
                return true;
            }
        }
        return false;
    }

    static void checkCertificate(
        long[] weights, long[] values, long capacity,
        int epsilonNumerator, int epsilonDenominator
    ) {
        Approximation answer = approximate(
            weights, values, capacity,
            epsilonNumerator, epsilonDenominator
        );
        long optimum = bruteOptimum(weights, values, capacity);

        // exact integer form:
        // answer.value * q >= optimum * (q-p).
        BigInteger lhs = BigInteger
            .valueOf(answer.value())
            .multiply(BigInteger.valueOf(epsilonDenominator));
        BigInteger rhs = BigInteger
            .valueOf(optimum)
            .multiply(BigInteger.valueOf(
                epsilonDenominator - epsilonNumerator
            ));

        if (answer.value() > optimum
                || answer.weight() > capacity
                || lhs.compareTo(rhs) < 0
                || !bruteHasWitness(
                    weights, values, capacity,
                    answer.weight(), answer.value()
                )) {
            throw new AssertionError(
                "FPTAS feasibility/ratio/witness check failed"
            );
        }
    }

    static void verifyRandomCases() {
        Random rng = new Random(475L);
        int cases = 600;
        int[] denominators = {2, 4, 5, 10};

        for (int test = 0; test < cases; test++) {
            int n = rng.nextInt(11); // 0..10
            long[] w = new long[n];
            long[] v = new long[n];
            for (int i = 0; i < n; i++) {
                w[i] = rng.nextInt(13); // 0..12, includes zero
                v[i] = rng.nextInt(26); // 0..25, includes zero
            }
            long capacity = rng.nextInt(32); // 0..31
            int denominator =
                denominators[test % denominators.length];

            checkCertificate(w, v, capacity, 1, denominator);
        }
        System.out.println(
            "Random feasibility/ratio/witness checks: PASS ("
            + cases + " cases)"
        );
    }

    static void verifyExhaustiveTinyCases() {
        int checks = 0;

        // For n=0,1,2,3, each item chooses:
        // weight in {0,1,2}, value in {0,1,2,3}
        // => 12^n combinations, all capacities 0..6.
        for (int n = 0; n <= 3; n++) {
            int patterns = 1;
            for (int i = 0; i < n; i++) {
                patterns *= 12;
            }

            for (int code = 0; code < patterns; code++) {
                int state = code;
                long[] w = new long[n];
                long[] v = new long[n];

                for (int i = 0; i < n; i++) {
                    int digit = state % 12;
                    state /= 12;
                    w[i] = digit % 3;
                    v[i] = digit / 3;
                }

                for (int capacity = 0; capacity <= 6; capacity++) {
                    checkCertificate(w, v, capacity, 1, 2);
                    checks++;
                }
            }
        }

        System.out.println(
            "Exhaustive tiny cases: PASS (" + checks + " cases)"
        );
    }

    static void show(
        String name, long[] weights, long[] values,
        long capacity, int p, int q
    ) {
        Approximation a = approximate(
            weights, values, capacity, p, q
        );
        long optimum = bruteOptimum(weights, values, capacity);

        System.out.println(
            name + ": value=" + a.value()
            + ", weight=" + a.weight()
            + ", scaled=" + a.scaledProfit()
            + ", exact=" + optimum
        );
    }

    public static void main(String[] args) {
        show(
            "Example A",
            new long[] {4, 5, 6, 3},
            new long[] {7, 8, 9, 4},
            10, 1, 2
        );
        show(
            "Example B",
            new long[] {6, 1, 2, 5},
            new long[] {23, 2, 16, 10},
            4, 1, 2
        );
        show(
            "Zero-weight items",
            new long[] {0, 0},
            new long[] {5, 7},
            0, 1, 2
        );
        show(
            "Empty input",
            new long[] {},
            new long[] {},
            0, 1, 2
        );

        verifyRandomCases();
        verifyExhaustiveTinyCases();

        try {
            approximate(
                new long[] {1}, new long[] {1},
                1, 0, 2
            );
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid epsilon rejected: " + e.getMessage()
            );
        }

        try {
            approximate(
                new long[] {1}, new long[] {1},
                1, 1, 200_000
            );
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Scaled DP budget rejected: " + e.getMessage()
            );
        }

        try {
            approximate(
                new long[] {-1}, new long[] {2},
                10, 1, 2
            );
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Negative weight rejected: " + e.getMessage()
            );
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên** (tệp trùng tên lớp public):

~~~bash
javac -encoding UTF-8 KnapsackValueScalingFptasDemo.java
java KnapsackValueScalingFptasDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
Example A: value=16, weight=10, scaled=14, exact=16
Example B: value=16, weight=2, scaled=4, exact=18
Zero-weight items: value=12, weight=0, scaled=6, exact=12
Empty input: value=0, weight=0, scaled=0, exact=0
Random feasibility/ratio/witness checks: PASS (600 cases)
Exhaustive tiny cases: PASS (13195 cases)
Invalid epsilon rejected: epsilon must satisfy 0 < numerator <= denominator
Scaled DP budget rejected: scaled DP exceeds demo budget (150000)
Negative weight rejected: weights and values must be nonnegative
~~~

### Đọc đúng các con số trong output

**Example A:** ε=1/2, K=9/8, các q là [6,7,8,3], Q=24. DP đạt tổng q=14 với trọng lượng 10 và lợi ích thật 16, đúng OPT=16.

**Example B:** vật phẩm quá nặng bị lọc, còn q=[0,4]; DP bỏ q=0 và chọn vật phẩm lợi ích 16. Nghiệm tốt nhất thật là 18, minh họa trường hợp **xấp xỉ nhưng không tối ưu**.

**Zero-weight items:** hai vật phẩm trọng lượng 0 có lợi ích dương 5 và 7, tổng giá trị 12; DP có thể chọn cả hai mà không vượt sức chứa W=0. Trọng lượng 0 hợp lệ theo giả thiết bài.

**Empty input:** không có vật phẩm giữ lại; tập rỗng có giá trị 0, trọng lượng 0, tổng q=0.

**Random checks:** 600 bộ input nhỏ theo seed 475 và các ε=1/2,1/4,1/5,1/10 được đối chiếu với vét cạn. Mỗi bộ kiểm: không vượt capacity, không vượt OPT, đạt bất đẳng thức tỉ lệ và **tồn tại tập con có đúng cặp `(weight,value)` được báo**.

**Exhaustive tiny cases:** thử tất cả 12^n cấu hình của n từ 0 đến 3, mỗi vật phẩm có trọng lượng 0..2 và lợi ích 0..3, với 7 mức capacity từ 0 tới 6. Số ca:

\[
7(12^0+12^1+12^2+12^3)
=7(1+12+144+1728)
=\boxed{13\,195}.
\]

Đây là phép kiểm bao phủ toàn bộ **không gian nhỏ đã định nghĩa**, khác với random test chỉ lấy một số mẫu input.

## 16. Giải thích những quyết định triển khai quan trọng

### Tại sao dùng BigInteger ngay khi tính q?

Biểu thức \(v_iqm\) có thể vượt `long` ngay cả khi \(v_i\), q và m riêng lẻ vừa `int`/`long`. Nếu tính bằng long rồi mới ép BigInteger, overflow có thể xảy ra **trước khi BigInteger được tạo**.

Mã xây các toán hạng BigInteger **trước** phép nhân; phép chia `divide` với hai số nguyên dương thực hiện đúng floor:

\[
\left\lfloor\frac{v_iqm}{pP}\right\rfloor.
\]

Như vậy **giá trị q** dùng trong bảo đảm được tính chính xác theo phân số ε đã cung cấp. Giới hạn `MAX_SCALED_SUM` được so với BigInteger trước khi chuyển thành int.

### Tại sao không cần BigInteger cho mỗi ô DP?

Mã chọn `long` cho trọng lượng và tổng giá trị thật. Nó chỉ **chấp nhận nghiệm khi trọng lượng không vượt capacity**, và dùng `Math.addExact` cho tổng lợi ích để phát hiện overflow. Đây là giới hạn thiết kế minh họa, không phải chứng minh có thể lưu mọi bài Knapsack có lợi ích tùy ý trong long.

Nếu input cần tổng lợi ích lớn hơn `Long.MAX_VALUE`, phải đổi `actualValue` thành số học đa độ chính xác và xem lại ngân sách RAM/thời gian. Phương pháp toán học FPTAS không phụ thuộc vào việc giá trị thật phải vừa một long.

### Ba mảng 1 chiều dùng chung một trạng thái

Với mỗi s đạt được:

- `reachable[s]` báo trạng thái tồn tại.
- `minWeight[s]` là trọng lượng thấp nhất trong các nghiệm có tổng q=s.
- `actualValue[s]` đi kèm chính nghiệm đang đại diện ở `minWeight[s]`.

Khi cập nhật state s từ s−q, **cả trọng lượng và lợi ích thật** đều được ghi từ **cùng một ứng viên**. Nhờ thế cặp `(weight,value)` có một witness khả thi, không phải ghép trọng lượng của nghiệm A với giá trị của nghiệm B.

### Bảo đảm không lặp vật phẩm

Đối với mỗi q>0, vòng `for (score=currentMax;score>=q;score--)` đi từ lớn xuống nhỏ. Trạng thái `score-q` có chỉ số nhỏ hơn `score`, nên chưa bị cập nhật bởi cùng vật phẩm ở lượt hiện tại. Đây là cách cài 0/1 đúng.

Nếu q=0, mã **skip**, không chạy vòng cập nhật. Điều này tránh lỗi tự đọc/ghi cùng trạng thái và giữ quy tắc rounding-loss đã chứng minh.

### Khi vượt ngân sách thì sao?

Nếu tổng q được tính có nguy cơ vượt 150.000, chương trình ném `IllegalArgumentException` với thông báo ngân sách. **Nó không trả một approximation value khi vượt ngân sách.** Do đó không được gọi kết quả lỗi là nghiệm gần đúng hoặc suy ra bài toán vô nghiệm.

Trong phân tích lý thuyết, ta có thể cấp phát O(m²/ε) trạng thái; trong phần mềm thực tế, luôn phải đối chiếu với RAM/time budget. Để giải dữ liệu vượt budget có thể cân nhắc giảm độ chính xác ε (tăng ε), dùng bộ nhớ ngoài, thuật toán xấp xỉ khác hoặc triển khai DP tối ưu hơn.

## 17. Độ phức tạp đầy đủ

Gọi m là số vật phẩm giữ lại sau lọc, m≤n. Giả sử m>0.

Tổng điểm co giãn:

\[
Q=\sum_i q_i\le m^2/\varepsilon.
\]

**Tiền xử lý và tính q:**

- Lọc vật phẩm: O(n).
- Tìm P: O(m).
- Tính m phép nhân/chia số nguyên để lấy q: O(m) **phép toán số lớn**, mỗi phép tốn thời gian đa thức theo số bit các toán hạng.

**DP:**

- Có Q+1 trạng thái.
- Mỗi vật phẩm cập nhật tối đa O(Q) trạng thái.
- Tổng O(mQ).

Vì vậy, trong mô hình đếm phép toán số học:

\[
\boxed{T=O(n+m^3/\varepsilon).}
\]

Nếu n=m (không lọc gì), thường viết ngắn:

\[
\boxed{T=O(n^3/\varepsilon).}
\]

**Bộ nhớ của ba mảng DP:**

\[
\boxed{M=O(Q)=O(m^2/\varepsilon)}
\]

ô nhớ, cộng O(m) cho các vật phẩm giữ lại và mảng q. Nếu xét số **bit** để lưu các trọng lượng và giá trị, mỗi ô có thể dùng số bit phụ thuộc độ dài input, nhưng cận tổng vẫn đa thức theo bit-size input và \(1/\varepsilon\) khi dùng phép toán số học chính xác phù hợp.

### Có thể tối ưu hơn không?

Có những FPTAS cho Knapsack với độ phức tạp tốt hơn tùy giả định và kỹ thuật, chẳng hạn giảm số trạng thái, nhóm các vật phẩm theo quy mô lợi ích, hoặc kết hợp những thuật toán gần đúng sơ bộ. Bài này cố ý trình bày **sơ đồ scaling + DP đơn giản** với chứng minh ngắn, dễ cài và dễ kiểm.

Không được suy luận rằng **mọi** FPTAS cho Knapsack đều cần O(n³/ε); đó chỉ là cận của cách cài được học ở đây.

## 18. Các tình huống biên

| Trường hợp | Xử lý |
|---|---|
| Không có vật phẩm | Trả giá trị 0, trọng lượng 0 |
| W=0 | Vật phẩm trọng lượng 0, lợi ích dương vẫn có thể chọn |
| Mọi vật phẩm đều quá nặng | Không có nghiệm lợi ích dương, trả 0 |
| Mọi lợi ích đều 0 | Trả 0; chọn rỗng là tối ưu |
| Có vật phẩm lợi ích âm | Mã từ chối; bảo đảm được chứng minh cho \(v_i\ge0\) |
| Có trọng lượng âm | Mã từ chối; bỏ trạng thái vượt W không còn có cơ sở |
| ε=1/2 hoặc ε=1/10 | Hợp lệ, lần lượt bảo đảm ≥50% và ≥90% OPT |
| ε=1 | Hợp lệ, nhưng cận \(1-\varepsilon=0\) không có sức mạnh định lượng |
| ε=0 | Không có K>0 theo công thức; dùng thuật toán exact nếu muốn tối ưu |
| Vật phẩm lợi ích nhỏ làm q=0 | Có thể bị bỏ trong DP, đã tính trong cận rounding loss |
| q_i rất lớn | Chặn trước khi ép BigInteger sang int/cấp phát |
| Tổng q vượt ngân sách | Trả lỗi tài nguyên, không báo “vô nghiệm” |
| Hai vật phẩm cùng trọng lượng/giá trị | Vẫn là hai vị trí 0/1 khác nhau |
| Tổng lợi ích thật vượt long | `Math.addExact` báo lỗi; cần BigInteger nếu hỗ trợ |
| Sức chứa rất lớn | DP theo q không cần mảng dài W |
| Yêu cầu liệt kê chỉ số vật phẩm | Cần phần truy vết bổ sung, không tự suy ra từ value/weight |
| Sửa ε từ 1/2 thành 1/10 | Có thể tăng số trạng thái và chi phí đáng kể |
| Bài toán nhiều ràng buộc | Không tự áp công thức cho single-constraint Knapsack |

### Trọng lượng 0 và lợi ích dương

Một vật phẩm có \(w_i=0\), \(v_i>0\) là hoàn toàn hợp lệ trong 0/1 Knapsack. Nó có thể được chọn mà không làm tăng tổng trọng lượng.

Trong ví dụ:

~~~text
weights=[0,0]
values =[5,7]
capacity=0
~~~

Tối ưu là 12, không phải 0. Mã giữ hai vật phẩm này trong danh sách đủ điều kiện và DP có thể nhận cả hai, vì điểm q của chúng dương trong ví dụ.

### Vật phẩm quá nặng có lợi ích rất lớn

Nếu có vật phẩm w>W nhưng v cực lớn, phải **lọc trước khi chọn P**. Nếu không, K có thể lớn đến mức các vật phẩm khả thi bị co giãn về 0 và bảo đảm xấp xỉ theo OPT bị phá.

Đây là một trong những trường hợp test quan trọng nhất của mọi triển khai profit scaling.

## 19. Kiểm chứng một FPTAS như thế nào?

Một chương trình có thể in giá trị nghe hợp lý nhưng vẫn sai ở chứng minh, khả thi hoặc cách chọn trạng thái. Vì vậy nên kiểm ít nhất **bốn mặt**.

### A. Tính khả thi

Đối với nghiệm được trả, phải có:

\[
\boxed{weight\le W.}
\]

Nếu có danh sách vật phẩm, phải xác nhận không vật phẩm nào được chọn hai lần. Bản demo không trả chỉ số; nó dùng một oracle độc lập trên input nhỏ để chứng minh **tồn tại ít nhất một tập con** cho đúng cặp `(weight,value)`.

### B. Cận trên bởi tối ưu

Trên n nhỏ, vét cạn mọi tập con để tìm OPT. Bắt buộc:

\[
\boxed{ALG\le OPT.}
\]

Nếu ALG>OPT, chắc chắn có lỗi: thuật toán đã vượt sức chứa, dùng vật phẩm hơn một lần hoặc tính sai lợi ích.

### C. Cận dưới theo ε

Dùng số học nguyên để kiểm:

\[
ALG\ge(1-\varepsilon)OPT.
\]

Với ε=p/q, biến đổi để không dùng số thực:

\[
\boxed{ALG\cdot q\ge OPT\cdot(q-p).}
\]

Trong Java, `BigInteger` được dùng cho hai vế để tránh overflow. Đây là cách kiểm chính xác cận tỉ lệ trên dữ liệu test nguyên.

### D. Phân phối trường hợp kiểm

Ngoài vài ví dụ thủ công, nên thử:

- Ma trận trọng lượng/giá trị toàn 0.
- Nhiều vật phẩm không vừa riêng lẻ.
- Có vật phẩm trọng lượng 0, lợi ích dương.
- Có vật phẩm q=0 sau scaling.
- Hai hay nhiều tập có cùng tổng q nhưng khác trọng lượng.
- Nhiều tập có cùng q và cùng trọng lượng nhưng giá trị thật khác nhau.
- W rất nhỏ hoặc bằng 0.
- ε nhỏ và tổng q gần ngưỡng bộ nhớ.
- Giá trị gần `Long.MAX_VALUE`, kiểm phép nhân số lớn và cộng giá trị thật.
- n=1, n=2, n=0.
- Các trường hợp quá budget để chắc chắn chương trình **báo lỗi tài nguyên** thay vì trả false hoặc nghiệm giả.

Mã dùng **600 trường hợp ngẫu nhiên có seed 475L**, cùng **13.195 trường hợp liệt kê đầy đủ** ở n≤3, trọng lượng 0..2, giá trị 0..3, capacity 0..6. Các test nhỏ còn giúp phát hiện sai khi làm tròn K hoặc duyệt DP theo thứ tự không phù hợp.

### Vì sao brute force chỉ dùng cho dữ liệu nhỏ?

Vét cạn xét tối đa \(2^n\) tập con, nên chi phí tăng hàm mũ theo n. Trong mã, oracle từ chối n>20. Đây là **công cụ kiểm thử độc lập**, không phải phương pháp chính cho các input mà FPTAS hướng tới.

## 20. Những lỗi thường gặp khi triển khai value scaling

1. **Nhầm mục tiêu của 0/1 Knapsack**, dùng công thức cho bài không giới hạn số lần chọn.
2. **Co giãn trọng lượng thay vì giá trị** rồi vẫn dùng chứng minh tương tự, có thể vi phạm sức chứa.
3. **Quên lọc vật phẩm w>W trước khi chọn P**, làm mất điều kiện P≤OPT.
4. **Đặt P bằng tổng giá trị mọi vật phẩm** mà không đổi chứng minh, dẫn đến K quá lớn.
5. **Chọn K=εP rồi bỏ chia m**, khiến lỗi cộng dồn có thể là mεP.
6. **Làm tròn K lên 1 khi K<1**, làm mK>εP và mất cận bảo đảm.
7. **Lấy ceil hoặc round cho q_i nhưng dùng chứng minh floor**, bất đẳng thức không đúng.
8. **Tính \(v_iqm\) bằng long rồi mới tạo BigInteger**, tràn trước khi dùng số lớn.
9. **Dùng double và floor mà không phân tích sai số tại ranh giới nguyên**, kết quả q có thể lệch.
10. **Dùng q_i như giá trị lợi ích thật**, quên phải báo tổng v của nghiệm được chọn.
11. **Lấy trạng thái s lớn nhất bất kể trọng lượng**, có thể chọn nghiệm vượt W.
12. **Giữ nghiệm có giá trị thật cao nhất cho mỗi s nhưng bỏ qua trọng lượng**, phá tính thống trị.
13. **Duyệt DP theo s tăng dần**, dùng một vật phẩm hai lần trong bài 0/1.
14. **Không xử lý q_i=0 rõ ràng**, có thể tự cập nhật cùng một ô và làm sai thiết kế.
15. **Kết luận q=0 nghĩa là vật phẩm không có giá trị thật**, trong khi v vẫn dương.
16. **Không giữ actualValue và minWeight gắn với cùng một nghiệm**, trả cặp không khả thi.
17. **Dùng sentinel `Long.MAX_VALUE` mà quên xử lý trường hợp trọng lượng thật có thể bằng Long.MAX_VALUE**, phân biệt trạng thái không tới được bằng boolean sẽ an toàn hơn.
18. **Không kiểm tràn `minWeight+weight`**, có thể biến nghiệm quá nặng thành số âm.
19. **Không kiểm tràn `actualValue+value`**, in lợi ích âm/sai khi vượt long.
20. **Tự giảm epsilon quá nhỏ nhưng vẫn cấp phát mảng Q lớn**, gặp lỗi RAM.
21. **Bắt lỗi vượt ngân sách rồi trả nghiệm 0 như thể có bảo đảm**, sai nếu tồn tại nghiệm giá trị lớn.
22. **Tưởng kết quả xấp xỉ luôn bằng OPT với ví dụ nhỏ**, không kiểm trường hợp rounding mất lợi ích.
23. **Quên rằng ε là độ chính xác, không phải xác suất thành công**, FPTAS ở đây tất định.
24. **Tuyên bố FPTAS chỉ vì có heuristic nhanh**, thiếu chứng minh tỉ lệ và thời gian theo \(1/\varepsilon\).
25. **Chỉ kiểm kết quả ≤OPT nhưng không kiểm ≥(1−ε)OPT**, không phát hiện nghiệm quá kém.
26. **Chỉ kiểm tỉ lệ mà không kiểm khả thi**, một nghiệm vượt W có thể có lợi ích rất lớn.
27. **Kiểm cận bằng double sát ngưỡng**, có thể báo sai qua sai số dấu phẩy động.
28. **Bỏ bước lấy P từ các vật phẩm có lợi ích dương**, dẫn tới chia cho 0 khi toàn bộ lợi ích bằng 0.
29. **Cho phép giá trị âm mà vẫn dùng chứng minh V≥Kq**, định nghĩa và tính đơn điệu phải xem lại.
30. **Nhầm O(m³/ε) với O(m³·ε)**, sai xu hướng khi ε giảm.
31. **Cho rằng mọi FPTAS Knapsack đều có cùng độ phức tạp**, không phân biệt các cải tiến thuật toán.
32. **Không chỉ rõ kết quả trả về là giá trị hay danh sách vật phẩm**, khiến người dùng tưởng đã có lời giải truy vết.
33. **Không dùng oracle độc lập**, lỗi trạng thái có thể chỉ lộ ở những tập con rất nhỏ.
34. **Đồng nhất “có lược đồ xấp xỉ” với “bài toán dễ theo nghĩa exact”**, dù Knapsack 0/1 vẫn NP-khó khi mã hóa nhị phân.
35. **Không phân biệt lợi ích 0 với lợi ích bị co giãn thành q=0**, hai trường hợp có vai trò khác nhau trong chứng minh.

## 21. So sánh với các kỹ thuật ba lô khác

| Cách giải | Kết quả | Thời gian điển hình | Phụ thuộc tham số | Khi nào phù hợp |
|---|---|---|---|---|
| Vét cạn | Tối ưu chính xác | O(n2^n) nếu tính tổng trực tiếp | n | n rất nhỏ; oracle |
| DP theo trọng lượng | Tối ưu chính xác | O(nW) | Giá trị sức chứa W | W nhỏ |
| DP theo giá trị thật | Tối ưu chính xác | O(nV) | Tổng lợi ích V | V nhỏ |
| Meet-in-the-middle | Tối ưu chính xác | O(n2^(n/2)) hoặc gần cận đó | n | n nhỏ/vừa, W,V lớn |
| Tham lam theo v/w | Không bảo đảm tối ưu 0/1 | O(n log n) | n | Heuristic hoặc bài fractional |
| **Scaling + DP** | **≥(1−ε)OPT** | **O(n³/ε)** (bản cơ bản) | n,1/ε | Cần lời giải gần tối ưu, có bảo đảm |
| Lược đồ xấp xỉ tối ưu hơn | ≥(1−ε)OPT | Phụ thuộc thuật toán | n,1/ε | Bài lớn đòi hiệu năng cao |

### Tại sao có FPTAS không làm Knapsack 0/1 “hết khó”?

Bài tối ưu 0/1 Knapsack là bài toán **NP-khó** dưới mã hóa nhị phân; phiên bản quyết định phù hợp là **NP-đầy đủ yếu**. Thuật toán giả đa thức tồn tại nên ta có thể thiết kế FPTAS bằng co giãn lợi ích.

Nhưng FPTAS với ε>0 **không phải thuật toán exact cho mọi trường hợp**. Đặt ε tiến tới 0 có thể khiến \(1/\varepsilon\) tăng khổng lồ; không thể nói “chọn ε cực kỳ bé thì đã giải chính xác trong thời gian đa thức theo input” khi ε không còn được xem như một tham số nhỏ hợp lý.

### FPTAS khác thuật toán “làm tròn bừa”

Một phép làm tròn chỉ là thao tác số học. Để thành FPTAS, cần tất cả điều sau:

1. Chứng minh **lỗi mỗi vật phẩm**.
2. Cộng dồn lỗi và ràng buộc nó bằng εOPT.
3. Bảo đảm **nghiệm còn khả thi**.
4. Chứng minh số trạng thái và thời gian **đa thức theo \(1/\varepsilon\)**.
5. Triển khai đủ chính xác để những bất đẳng thức trong chứng minh thực sự áp dụng cho số đang dùng.

Đó là giá trị của cách chọn \(K=\varepsilon P/m\) thay vì chọn một hệ số scale theo cảm tính.

## 22. Câu hỏi tự luyện

**Bài 1.** Ba lô 0/1 cho phép chọn mỗi vật phẩm bao nhiêu lần?

*Đáp án:* Tối đa **một lần**.

**Bài 2.** Mục tiêu của bài toán ba lô 0/1 là gì?

*Đáp án:* Tối đa hóa tổng giá trị lợi ích trong khi tổng trọng lượng không vượt W.

**Bài 3.** Trong FPTAS tối đa hóa, cần bảo đảm tỉ lệ nào?

*Đáp án:* \(\boxed{ALG\ge(1-\varepsilon)OPT}\) với nghiệm khả thi.

**Bài 4.** FPTAS yêu cầu thời gian đa thức theo những đại lượng nào?

*Đáp án:* Theo **độ dài input** và **\(1/\varepsilon\)**.

**Bài 5.** DP theo tổng giá trị thật V có nhược điểm gì?

*Đáp án:* Cần O(V) trạng thái và O(nV) thời gian, là **giả đa thức** nếu V rất lớn.

**Bài 6.** Để tạo FPTAS theo scaling, giữ nguyên đại lượng nào?

*Đáp án:* Giữ nguyên **trọng lượng và sức chứa**; co giãn **giá trị lợi ích**.

**Bài 7.** Vì sao phải lọc vật phẩm có w>W trước?

*Đáp án:* Nó không thể thuộc nghiệm khả thi; nếu lấy P từ nó thì điều kiện P≤OPT có thể sai.

**Bài 8.** Với m vật phẩm hợp lệ và lợi ích lớn nhất P, K bằng bao nhiêu?

*Đáp án:* \(\boxed{K=\varepsilon P/m}\).

**Bài 9.** Giá trị co giãn của vật phẩm i là gì?

*Đáp án:* \(\boxed{q_i=\lfloor v_i/K\rfloor}\).

**Bài 10.** Tại sao dùng floor?

*Đáp án:* Mỗi vật phẩm mất dưới K đơn vị lợi ích khi so \(v_i\) với \(Kq_i\), tạo cận tổng ≤mK.

**Bài 11.** Tổng điểm co giãn Q lớn nhất theo bậc nào?

*Đáp án:* \(Q=O(m^2/\varepsilon)\).

**Bài 12.** DP cơ bản theo q có thời gian/bộ nhớ bao nhiêu?

*Đáp án:* \(O(m^3/\varepsilon)\) thời gian, \(O(m^2/\varepsilon)\) bộ nhớ trong mô hình đếm phép toán.

**Bài 13.** Tại cùng tổng q, DP giữ nghiệm có trọng lượng thế nào?

*Đáp án:* Nghiệm có **trọng lượng nhỏ nhất**.

**Bài 14.** Vì sao cập nhật s giảm dần?

*Đáp án:* Để mỗi vật phẩm không được sử dụng nhiều hơn một lần.

**Bài 15.** Nếu q_i=0 nhưng v_i>0, có được bỏ vật phẩm trong FPTAS cơ bản không?

*Đáp án:* Có; tổn thất đã nằm trong cận lỗi **<K mỗi vật phẩm**, nếu chứng minh dùng đúng K.

**Bài 16.** Nếu ε=1/10 thì bảo đảm chất lượng tối thiểu là bao nhiêu?

*Đáp án:* **90% của OPT**.

**Bài 17.** Nếu ε nhỏ đi 10 lần, cận O(m³/ε) thay đổi thế nào?

*Đáp án:* Cận trên theo tham số ε tăng tối đa khoảng **10 lần** nếu m giữ nguyên, bỏ qua hằng số và chi phí khác.

**Bài 18.** Trong ví dụ A, K bằng bao nhiêu?

*Đáp án:* **9/8**.

**Bài 19.** Trong ví dụ A, các q là gì?

*Đáp án:* **[6,7,8,3]**.

**Bài 20.** Ví dụ A cho ALG và OPT bao nhiêu?

*Đáp án:* **ALG=OPT=16**.

**Bài 21.** Trong ví dụ B, vì sao ALG=16 nhưng OPT=18?

*Đáp án:* Vật phẩm lợi ích 2 bị co giãn thành q=0 rồi bỏ qua; nghiệm thật tốt nhất chọn thêm vật phẩm ấy.

**Bài 22.** Nếu ε=p/q, có thể tính floor chính xác bằng công thức nào?

*Đáp án:* \(\lfloor v_iqm/(pP)\rfloor\), dùng số học nguyên đủ rộng.

**Bài 23.** Vì sao `BigInteger` cần được dùng **trước phép nhân**?

*Đáp án:* Nếu nhân các long trước, tràn có thể xảy ra trước khi chuyển sang BigInteger.

**Bài 24.** Trong nghiệm trả về, phải kiểm cặp nào cùng một tập con?

*Đáp án:* **Trọng lượng thật và lợi ích thật**.

**Bài 25.** Trên input nhỏ, muốn kiểm \((1-\varepsilon)OPT\) không dùng double thì làm sao?

*Đáp án:* Với ε=p/q, kiểm **ALG·q≥OPT·(q−p)** bằng số học nguyên.

**Bài 26.** Nếu tổng q vượt budget, có được trả 0 và coi là nghiệm FPTAS không?

*Đáp án:* **Không**. Phải báo lỗi tài nguyên hoặc chuyển sang phương pháp khác có bảo đảm.

**Bài 27.** Nếu không có vật phẩm lợi ích dương nào vừa ba lô, OPT là bao nhiêu?

*Đáp án:* **0**, chọn tập rỗng.

**Bài 28.** FPTAS này có trả tập chỉ số vật phẩm không?

*Đáp án:* Mã minh họa chỉ trả giá trị và trọng lượng của một nghiệm khả thi, không trả chỉ số; cần bổ sung truy vết để xuất tập vật phẩm.

**Bài 29.** Vì sao \(\varepsilon P\le\varepsilon OPT\)?

*Đáp án:* Vì P là giá trị một vật phẩm khả thi nên P≤OPT.

**Bài 30.** Lý do gì để coi profit scaling là kỹ thuật “có chứng minh”, không phải heuristic thuần túy?

*Đáp án:* Có **cận mất mát sau floor**, có DP tối ưu trên điểm đã co giãn, giữ khả thi và có cận thời gian đa thức theo n,1/ε.

**Tổng kết:** Co giãn giá trị tạo FPTAS cho **0/1 Knapsack** bằng cách giữ nguyên trọng lượng và sức chứa, lọc những vật phẩm không khả thi, chọn \(P\) là **giá trị vật phẩm khả thi lớn nhất**, đặt \(K=\varepsilon P/m\), rồi dùng \(q_i=\lfloor v_i/K\rfloor\) để giải DP theo tổng q. Do \(\sum q_i=O(m^2/\varepsilon)\), cách cài cơ bản chạy \(O(m^3/\varepsilon)\) thời gian và \(O(m^2/\varepsilon)\) bộ nhớ. Bất đẳng thức \(Kq_i>v_i-K\), cộng trên tối đa m vật phẩm, cùng với P≤OPT cho bảo đảm **\(ALG\ge(1-\varepsilon)OPT\)**. Chương trình Java 17 dùng `BigInteger` để tránh lỗi floor và overflow trong bước scaling, duyệt DP giảm dần để bảo đảm 0/1, kiểm chứng khả thi/tỉ lệ với oracle vét cạn và chủ động báo lỗi khi vượt ngân sách bộ nhớ. Khi ε giảm, chất lượng bảo đảm tăng nhưng tài nguyên cần dùng có thể tăng; luôn chọn ε và cách lưu trạng thái theo nhu cầu thực tế.
