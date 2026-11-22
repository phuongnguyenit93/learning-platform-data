# Ảnh hưởng của thứ tự duyệt và độ chặt của cận

## 1. Một bài toán tối ưu, nhiều cây tìm kiếm khác nhau

**Nhánh và cận (branch and bound, B&B)** là phương pháp tìm nghiệm tối ưu bằng cách phân nhánh các lựa chọn và dùng **cận có chứng minh** để loại những nhánh không thể cải thiện nghiệm tốt nhất đang có. Khác với quay lui chỉ dùng tính hợp lệ để cắt nhánh, B&B còn khai thác **giá trị mục tiêu**.

Hai yếu tố thường quyết định hiệu quả thực tế:

1. **Thứ tự duyệt nhánh:** thử lựa chọn nào trước để nhanh tìm được một **nghiệm khả thi có giá trị tốt** (incumbent); nghiệm này sẽ giúp cắt những nhánh còn lại.
2. **Độ chặt của cận:** tính **giới hạn tốt nhất có thể đạt** từ mỗi trạng thái sát tới đâu; cận càng chặt mà vẫn đúng thì càng dễ chứng minh một nhánh không thể vượt incumbent.

Cần phân biệt rõ: thứ tự duyệt là **chiến lược tìm kiếm**, còn cận là **chứng cứ loại nhánh**. Thay đổi một trong hai có thể làm số nút duyệt chênh lệch rất lớn, nhưng nếu cận hợp lệ và thuật toán thực hiện đúng thì **giá trị tối ưu cuối cùng không đổi**.

Bài dùng **ba lô 0/1** làm ví dụ hoàn chỉnh, sau đó rút ra nguyên tắc chung cho các bài tối ưu khác.

## 2. Những thuật ngữ bắt buộc hiểu

Giả sử mục tiêu là **tối đa hóa** hàm F.

- **Nghiệm khả thi (feasible solution):** thỏa mọi ràng buộc. Chỉ nghiệm khả thi mới được dùng để cập nhật giá trị tốt nhất.
- **Incumbent / best:** giá trị của nghiệm khả thi tốt nhất đã tìm thấy tính tới thời điểm hiện tại. Với tối đa hóa, đây là **cận dưới toàn cục** cho giá trị tối ưu thật.
- **Cận trên của một nút (upper bound, UB):** giá trị mà **mọi nghiệm hoàn chỉnh từ nút ấy không thể vượt**. UB có thể lớn hơn giá trị thực sự đạt được.
- **Phân nhánh (branch):** tạo các trạng thái con bằng các lựa chọn như “lấy” hoặc “không lấy” một món.
- **Cắt nhánh (prune):** bỏ toàn bộ cây con khi đã chứng minh không cần xét tiếp.
- **Độ chặt (tightness):** mức độ gần của UB với giá trị tốt nhất thực sự có thể đạt trong cây con. UB nhỏ hơn thường **chặt hơn** đối với bài tối đa hóa, miễn vẫn là cận trên hợp lệ.
- **Thứ tự duyệt (branch/node order):** quy tắc chọn nhánh con hoặc nút mở nào được xử lý trước.

Đối với **tối đa hóa và chỉ cần một nghiệm tối ưu**:

\[
\boxed{UB(node)\le best\quad\Longrightarrow\quad \text{cắt toàn bộ cây con}.}
\]

Bởi không có nghiệm nào trong cây con vượt best, nên bỏ cây con này không thể làm mất **một nghiệm có giá trị tốt hơn**.

Nếu đề yêu cầu **tất cả nghiệm đồng tối ưu**, điều kiện cắt khi bằng nhau phải được xét lại: UB=best vẫn có thể chứa những nghiệm khác cũng đạt best. Với trường hợp ấy, chỉ cắt chắc chắn khi UB<best (hoặc khi có chứng cứ mạnh hơn không chứa nghiệm mới cần xuất).

**Chưa có incumbent hữu ích?** Trên bài tối đa hóa có nghiệm rỗng hợp lệ giá trị 0, ta có thể đặt best=0. Với bài không có nghiệm khả thi rõ ràng từ đầu, không được tự khởi tạo best thành một giá trị như thể đã có nghiệm; phải dùng trạng thái “chưa có incumbent” hoặc khởi tạo bằng một nghiệm khả thi thật.

## 3. Đặc tả ba lô 0/1

Có n món hàng, mỗi món i có:
- Trọng lượng nguyên **w[i]>0**.
- Giá trị nguyên **v[i]≥0**.
- Chỉ được lấy **tối đa một lần**.

Ba lô có sức chứa nguyên **W≥0**. Tìm tập chỉ số S thỏa:

\[
\sum_{i\in S}w_i\le W
\]

để tối đa hóa:

\[
\sum_{i\in S}v_i.
\]

**Tập rỗng luôn hợp lệ**, trọng lượng 0, giá trị 0. Đây là lý do có thể khởi tạo best=0 trong chương trình minh họa.

Ví dụ dùng xuyên suốt (chỉ số món theo dữ liệu gốc, 0-based):

| ID | Trọng lượng w | Giá trị v | Mật độ v/w |
|---:|---:|---:|---:|
| 0 | 2 | 3 | 1,500 |
| 1 | 3 | 4 | 1,333 |
| 2 | 4 | 5 | 1,250 |
| 3 | 5 | 8 | 1,600 |
| 4 | 9 | 10 | 1,111 |
| 5 | 7 | 9 | 1,286 |
| 6 | 6 | 11 | 1,833 |
| 7 | 3 | 3 | 1,000 |

Sức chứa W=**15**, tổng giá trị tất cả món là **53**. Một nghiệm tối ưu là các món **[2,3,6]**, trọng lượng 4+5+6=15 và giá trị 5+8+11=**24**.

Giá trị tối ưu bằng 24 sẽ được tìm thấy trong cả bốn cấu hình bên dưới. **Thứ tự duyệt không thay đổi bài toán**, chỉ thay đổi trình tự gặp các nghiệm và khả năng cắt nhánh.

## 4. Cây quyết định và trạng thái tìm kiếm

Trong bài ba lô, tại mỗi tầng ta quyết định đối với một món:
- **TAKE:** chọn món ấy nếu trọng lượng còn lại đủ.
- **SKIP:** không chọn món ấy.

Để thuận lợi khi tính cận fractional, các món được **sắp theo mật độ giá trị/trọng lượng v/w giảm dần**. Với ví dụ, thứ tự ID sau sắp là:

~~~text
[6, 3, 0, 1, 5, 2, 4, 7]
~~~

Đây là thứ tự **xét món**, không phải thứ tự của đáp án theo ID gốc. Khi xuất tập món, có thể sắp chỉ số gốc tăng dần để kiểm tra dễ dàng.

Một trạng thái DFS gồm:
- **index:** sắp quyết định món ở vị trí index trong dãy đã sắp; các món trước index đã quyết định.
- **usedWeight:** tổng trọng lượng của những món đã TAKE.
- **currentValue:** tổng giá trị những món đã TAKE.
- **chosen:** các món đã TAKE để có thể khôi phục nghiệm.
- **bestValue:** giá trị tốt nhất của một tập món **đã biết chắc khả thi**.

Bất biến khi vào mỗi lời gọi dfs(index,usedWeight,currentValue): selected biểu diễn chính xác các món đã lấy trong **index món đầu**, tổng trọng lượng không vượt W và currentValue là tổng giá trị của chúng.

Dù các món phía sau chưa quyết định, **tập selected hiện tại đã là một nghiệm khả thi**: chỉ cần SKIP toàn bộ phần còn lại. Vì vậy chương trình được phép cập nhật bestValue **ngay tại một nút trong**, không cần chờ tới lá. Điều này thường giúp có incumbent tốt sớm hơn.

Mỗi nhánh TAKE chỉ được tạo khi:

\[
usedWeight+w[index]\le W.
\]

Nhánh SKIP luôn hợp lệ. Vì mỗi món được quyết định đúng một lần, cây không chứa cách lấy cùng một món nhiều lần.

## 5. Cận trên phải an toàn trước khi bàn đến độ chặt

Một cận trên U(s) của trạng thái s được gọi là **hợp lệ/admissible** nếu:

\[
\forall x\in Completions(s),\quad F(x)\le U(s).
\]

Nếu tính cận **quá thấp** so với một nghiệm hoàn chỉnh có thể đạt, thuật toán có thể cắt nhánh chứa nghiệm tối ưu và trả **kết quả sai**. Ngược lại, cận quá cao vẫn đúng, nhưng thường cắt được ít hơn.

Có hai lỗi đối nghịch:
- **Cận yếu nhưng hợp lệ:** giảm hiệu quả, **không làm sai** kết quả.
- **Cận “chặt” bằng cách ước lượng thiếu:** có thể nhanh hơn nhưng **không còn bảo đảm tối ưu**.

Độ chặt chỉ có ý nghĩa khi cận vẫn đáp ứng bất đẳng thức an toàn. Tính nhanh bằng một heuristic/greedy rồi lấy **giá trị của nghiệm tham lam** làm cận trên cho bài tối đa hóa thường **sai**: nghiệm tham lam là nghiệm khả thi, nên giá trị của nó chỉ là một **cận dưới** cho tối ưu, không phải cận trên.

Ví dụ đơn giản: ba lô W=10 với các món (w=9,v=19), (w=5,v=10), (w=5,v=10). Chọn món có mật độ cao nhất trước có thể đạt 19, nhưng chọn hai món nặng 5 đạt **20**. Không được cắt mọi nhánh có giá trị “không quá 19” nếu 19 chỉ là giá trị của nghiệm tham lam, không phải một cận trên đã chứng minh.

## 6. Cận A: tổng mọi giá trị còn lại — dễ tính nhưng lỏng

Với trạng thái đã lấy currentValue và đang xét món thứ index, giả sử suffixValue[index] là **tổng giá trị tất cả món chưa quyết định**:

\[
suffixValue[index]=\sum_{j=index}^{n-1}v_j.
\]

Một cận trên đơn giản:

\[
\boxed{UB_{\text{suffix}}=currentValue+suffixValue[index].}
\]

Đây là cận hợp lệ khi **mọi giá trị v≥0**: dù không thể lấy hết tất cả món do giới hạn sức chứa, tổng giá trị thêm của một tập con không bao giờ vượt tổng giá trị của tất cả món còn lại.

**Ưu điểm:** tính O(1) tại mỗi nút nếu đã tiền xử lý suffixValue, rất rẻ; không cần xem trọng lượng tại thời điểm tính cận.

**Nhược điểm:** bỏ qua sức chứa còn lại. Khi phần lớn món quá nặng, cận này vẫn giả sử lấy được toàn bộ, nên có thể **rất lỏng**.

Ở nút gốc của dữ liệu ví dụ:

\[
UB_{\text{suffix}}=0+(3+4+5+8+10+9+11+3)=\boxed{53}.
\]

Trong khi tối ưu thật chỉ bằng 24. Nếu đã tìm được incumbent=24, cận 53 tại gốc chưa đủ để loại nhánh; ở các nút con, suffix có thể tiếp tục quá cao.

**Giới hạn áp dụng:** công thức này dựa vào v≥0. Nếu đầu vào cho giá trị âm mà vẫn cộng **mọi** giá trị còn lại, tổng ấy có thể thấp hơn giá trị của một lời giải bỏ các món âm, làm cận không hợp lệ. Khi cho giá trị âm phải điều chỉnh công thức (ví dụ cộng chỉ phần dương) và phân tích lại; chương trình minh họa đơn giản chọn **từ chối giá trị âm**.

## 7. Cận B: thư giãn ba lô thành bài toán được lấy phần món

### 7.1. Vì sao fractional knapsack tạo cận trên hợp lệ?

Trong bài ba lô 0/1 thật, mỗi món chỉ được lấy trọn hoặc bỏ. Để tính cận, ta tạm **nới lỏng**: với những món chưa quyết định, được phép lấy **một phần** của món cuối để vừa dung lượng còn lại.

Khi đã cố định các món trước index, bài toán “fractional knapsack” của các món phía sau có **tập lựa chọn rộng hơn** bài toán 0/1. Vì vậy:

\[
OPT_{\text{0/1 còn lại}}\le OPT_{\text{fractional còn lại}}.
\]

Nếu các món được sắp theo tỉ lệ v/w giảm dần, thuật toán lấy các món mật độ cao nhất cho đến khi hết sức chứa, rồi lấy **một phần** của món tiếp theo, đạt đúng tối ưu của bài toán fractional có giá trị không âm.

Do đó:

\[
UB_{\text{fractional}}
=currentValue+OPT_{\text{fractional còn lại}}
\]

là **cận trên hợp lệ** của mọi nghiệm 0/1 thuộc cây con hiện tại.

**Cực kỳ quan trọng:** bước lấy phần món **chỉ diễn ra trong phép tính cận**, không phải lựa chọn thật. Nhánh TAKE của DFS vẫn lấy **cả món hoặc không lấy**.

### 7.2. Cách tính từ một nút

Giả sử dung lượng còn lại:

\[
remaining=W-usedWeight.
\]

Bắt đầu với bound=currentValue, rồi xét các món chưa quyết định theo mật độ giảm dần:
- Nếu món j vừa remaining, cộng toàn bộ v[j], giảm remaining đi w[j].
- Nếu món j nặng hơn remaining, cộng **remaining·v[j]/w[j]** rồi dừng.
- Nếu remaining=0, không cộng gì nữa.

Giá trị fractional có thể không nguyên. Vì mọi nghiệm 0/1 có **giá trị nguyên**, ta có thể lấy **phần nguyên xuống** của cận fractional mà vẫn an toàn:

\[
OPT_{\text{0/1}}\le UB_{\text{fractional thực}}
\Rightarrow
OPT_{\text{0/1}}\le
\left\lfloor UB_{\text{fractional thực}}\right\rfloor.
\]

Vì phần của những món đã lấy trọn là số nguyên, trong code có thể dùng phép chia nguyên **floor(remaining·v[j]/w[j])** ở món lấy một phần, không cần double. Điều này tránh lỗi làm tròn số thực khiến cận bị thấp hơn một đơn vị ngoài dự kiến.

Với dữ liệu mẫu, ngay tại nút gốc W=15, thứ tự mật độ là [6,3,0,1,5,2,4,7]. Thư giãn lấy:
- Món 6: w=6, v=11; còn 9.
- Món 3: w=5, v=8; còn 4.
- Món 0: w=2, v=3; còn 2.
- Chỉ còn 2 đơn vị, lấy 2/3 món 1 (w=3,v=4), thu thêm 8/3.

Do đó:

\[
UB_{\text{fractional thực}}
=11+8+3+\frac{2\cdot4}{3}
=24+\frac23.
\]

Vì nghiệm thật có giá trị nguyên:

\[
\boxed{UB_{\text{fractional nguyên}}=24.}
\]

So với cận suffix **53**, cận fractional **24** rất chặt — bằng giá trị tối ưu thật trong ví dụ này.

### 7.3. Chứng minh fractional chặt không hơn cận suffix

Trong trường hợp giá trị không âm, bài toán fractional vẫn chỉ được lấy nhiều nhất 100% mỗi món còn lại. Tổng giá trị thu thêm không vượt tổng giá trị của tất cả các món ấy. Vì vậy tại mọi nút:

\[
UB_{\text{fractional}}\le UB_{\text{suffix}}.
\]

Một cận fractional đúng có khả năng cắt mạnh hơn cận suffix với cùng incumbent. Tuy vậy, nó **tốn thêm chi phí tính toán**: nếu mỗi lần gọi quét các món còn lại, mất O(n) thay vì O(1) của suffix.

Do đó **cận chặt hơn không mặc nhiên làm chương trình chạy nhanh hơn** trên mọi đầu vào. Nó thường giảm số nút, nhưng phải so cả chi phí **tính cận**. Khi cây nhỏ hoặc cận rẻ đã cắt rất nhiều, việc tính cận đắt có thể không đáng.

## 8. Thứ tự duyệt: TAKE trước và SKIP trước

Với mỗi món ở vị trí index có hai nhánh con:
- **TAKE-first:** thử lấy món trước (nếu vừa sức chứa), rồi thử không lấy.
- **SKIP-first:** thử không lấy món trước, rồi thử lấy.

Hai chế độ **không thay đổi tập nghiệm** hay điều kiện cắt, chỉ thay đổi **thứ tự tìm thấy các nghiệm khả thi** và mức bestValue tại những thời điểm thăm các nút.

### TAKE-first

Nếu món được ưu tiên có giá trị cao/mật độ cao, TAKE-first thường tạo nghiệm có giá trị tốt sớm, làm incumbent tăng nhanh. Khi incumbent cao, nhiều nút khác có UB≤best và bị cắt.

Tuy nhiên, đây là **heuristic**: lấy món có mật độ cao sớm chưa chắc tạo nghiệm 0/1 tối ưu vì các món có kích thước không khớp sức chứa. Một món lớn có thể chặn bộ món nhỏ cho tổng giá trị cao hơn.

### SKIP-first

SKIP-first ban đầu thử nhiều tập ít món hoặc tập rỗng; incumbent có thể tăng chậm hơn. Khi best còn thấp, điều kiện UB≤best khó đạt, nên nhiều nút được thăm trước khi tìm thấy nghiệm tốt.

Nhưng SKIP-first **không luôn tệ**. Tùy dữ liệu, bỏ qua một món kém phù hợp trước có thể đưa thuật toán đến nghiệm tối ưu sớm hơn TAKE-first. Hiệu quả phụ thuộc cả **thứ tự sắp món**, **thứ tự nhánh**, **cận**, **nghiệm khởi tạo** và đặc trưng đầu vào.

### Sắp món và chọn nhánh là hai trục điều khiển khác nhau

- Sắp món theo mật độ thay đổi **món nào được xét ở tầng nào**. Điều này cũng làm phép tính fractional bound rẻ hơn vì thứ tự mật độ đã sẵn sàng.
- TAKE-first/SKIP-first quyết định **nhánh con nào đi trước** khi đã chọn món tại tầng đó.
- Tìm nghiệm tham lam trước DFS để làm incumbent ban đầu là **một lựa chọn thứ ba**. Nếu dùng, phải kiểm tra nghiệm tham lam thực sự hợp lệ trước khi đưa giá trị của nó vào best.

Không được đánh đồng “tham lam” với “B&B”: tham lam có thể giúp tìm incumbent, còn B&B chứng minh tối ưu nhờ **khám phá đủ nhánh hoặc cắt bằng cận hợp lệ**.

## 9. So sánh bốn cấu hình trên cùng một bộ dữ liệu

Dùng W=15, w=[2,3,4,5,9,7,6,3], v=[3,4,5,8,10,9,11,3], và **cùng thứ tự sắp món theo mật độ**.

Giữ cố định:
- Nghiệm ban đầu là tập rỗng, best=0.
- DFS đi theo các món đã sắp.
- Cập nhật incumbent ngay khi **currentValue>best** ở bất kỳ nút khả thi.
- Cắt khi **UB≤best**, vì chỉ cần **một** nghiệm tối ưu.
- Ghi kết quả theo chỉ số ID ban đầu đã sắp tăng.
- Nhánh TAKE không vừa sức chứa **không tạo lời gọi dfs**, và chỉ số thống kê visited chỉ tăng khi thật sự vào dfs.

| Cận | Nhánh ưu tiên | Nút DFS đã thăm | Nút bị cắt | Lá hoàn chỉnh | Lần cải thiện best | Kết quả |
|---|---|---:|---:|---:|---:|---|
| Tổng giá trị còn lại (suffix) | TAKE trước | **122** | 32 | 5 | 5 | 24 |
| Tổng giá trị còn lại (suffix) | SKIP trước | **167** | 23 | 29 | 12 | 24 |
| Fractional relaxation | TAKE trước | **21** | 4 | 2 | 5 | 24 |
| Fractional relaxation | SKIP trước | **93** | 20 | 17 | 12 | 24 |

**Cách đọc bảng:**
- Giữ cận suffix, đổi **SKIP→TAKE** làm số nút thăm giảm từ 167 xuống 122 trên dữ liệu này.
- Giữ thứ tự TAKE-first, đổi **suffix→fractional** làm số nút giảm từ 122 xuống 21.
- Giữ thứ tự SKIP-first, đổi cận suffix→fractional làm số nút giảm từ 167 xuống 93.
- **Cả bốn đều trả giá trị 24**, một tập món tối ưu [2,3,6].

**Không so sánh “số nút bị cắt” một cách đơn lẻ.** Cận fractional TAKE-first chỉ báo 4 nút bị cắt, ít hơn 32 của suffix TAKE-first, nhưng tổng số nút thăm **ít hơn rất nhiều**: nhiều nhánh đã bị cắt cao trong cây nên các nút phía dưới **không hề được thăm** và không thể được đếm thêm là “nút cắt”.

**Không nhầm visited với thời gian chạy thực tế:** mỗi nút dùng cận suffix mất O(1) cho bound, còn fractional có thể mất O(n) cho bound. Bảng đo **các nút**, không phải milliseconds; muốn kết luận hiệu năng tuyệt đối cần benchmark thời gian trên bộ dữ liệu và môi trường cụ thể.

**Không nhầm leaves với số nghiệm hợp lệ:** chương trình có thể cập nhật incumbent ở **nút trong**, và có thể cắt nhánh khi UB==best trước khi đi tới lá. Vì vậy “số lá đã đến” không phải số nghiệm được xét và thậm chí có thể bằng 0 trong một bài có nghiệm tối ưu đã biết.

## 10. Thuật toán DFS kết hợp incumbent và cận

Giả mã cho bài tối đa hóa:

~~~text
search(index, usedWeight, currentValue):
    visited++

    // Tập các món đã lấy là một nghiệm khả thi.
    if currentValue > bestValue:
        bestValue = currentValue
        bestChoice = snapshot(selected)

    if index == n:
        leaves++
        return

    upper = computeUpperBound(index, usedWeight, currentValue)
    if upper <= bestValue:
        pruned++
        return

    if order == TAKE_FIRST:
        tryTake(index)
        trySkip(index)
    else:
        trySkip(index)
        tryTake(index)
~~~

Trong tryTake, chỉ đi sâu khi món vừa dung lượng còn lại; khi đi sâu, đánh dấu selected[index]=true, gọi search(index+1,...), rồi **hoàn tác**. Trong trySkip, selected[index] vẫn false và gọi search(index+1,...).

**Bất biến:** ở đầu mọi lời gọi, bestValue là giá trị của một nghiệm khả thi đã tìm được; do đó bestValue **không bao giờ giảm**. Nếu cắt vì UB≤bestValue, không có nghiệm chưa xét trong cây con có thể tăng bestValue. Vì vậy cắt nhánh là an toàn cho mục tiêu tìm **một nghiệm tối ưu**.

### Vì sao cập nhật ở nút trong không sai?

Tập đã chọn từ các món trước index luôn có thể hoàn tất thành nghiệm bằng cách **bỏ toàn bộ món chưa xét**. Vì vậy currentValue là giá trị của một nghiệm **đầy đủ theo nghĩa tập món khả thi**, dù quyết định skip còn lại chưa được tạo thành các lời gọi riêng. Nếu bài toán khác bắt buộc **phải chọn đủ k phần tử** hoặc phải thỏa ràng buộc ở lá, không được cập nhật incumbent tại mọi nút trong theo cách này.

### Điều kiện cắt tương đương trong bài toán tối thiểu hóa

Nếu mục tiêu là **tối thiểu hóa**, incumbent best là **cận trên toàn cục** của giá trị tối ưu, còn tại nút phải tính một **cận dưới LB** cho mọi nghiệm hoàn chỉnh:

\[
LB(node)\ge best\ \Longrightarrow\ \text{cắt}.
\]

Không dùng công thức UB≤best của bài tối đa hóa một cách máy móc cho bài tối thiểu hóa. “Cận chặt hơn” lúc này thường nghĩa là **LB cao hơn nhưng vẫn không vượt mức tối ưu có thể đạt trong cây con**.

## 11. Java 17+ hoàn chỉnh: thay hai lựa chọn mà giữ thuật toán đúng

Chương trình sau dùng:
- **Enum Order:** TAKE_FIRST và SKIP_FIRST.
- **Enum Bound:** SUFFIX và FRACTIONAL.
- **Item** có ID nguyên gốc, trọng lượng và giá trị.
- **Stats** ghi giá trị tốt nhất, chỉ số món, số nút đã thăm, cắt, lá và số lần best được cải thiện.
- Một **Solver** chung cho cả bốn cấu hình, nên các con số có cùng định nghĩa để so sánh công bằng.

Mảng đầu vào **không bị thay đổi**. Mã sắp bản sao Item theo mật độ giảm bằng **nhân chéo số nguyên long**, tránh sai thứ tự do phép chia double. Nhân hai số int không âm tối đa khoảng 2,147 tỉ vẫn vừa long khi ép kiểu trước nhân.

Đối với fractional bound, mã dùng \(\lfloor remaining\cdot value/weight\rfloor\) ở món lấy một phần; do các giá trị đều nguyên và không âm, đây là cận nguyên an toàn như đã chứng minh, **không phải một lựa chọn lấy phần món của nghiệm thật**.

Lưu tệp **BranchBoundOrderAndBoundsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class BranchBoundOrderAndBoundsDemo {
    private BranchBoundOrderAndBoundsDemo() {
    }

    enum Order {
        TAKE_FIRST, SKIP_FIRST
    }

    enum Bound {
        SUFFIX, FRACTIONAL
    }

    record Item(int id, int weight, int value) {
    }

    record Stats(long best, List<Integer> items,
                 long visited, long pruned,
                 long leaves, long updates) {
    }

    static final class Solver {
        private final Item[] items;
        private final int capacity;
        private final Order order;
        private final Bound boundKind;
        private final long[] suffix;
        private final boolean[] selected;

        private long best = 0;
        private List<Integer> bestItems = List.of();
        private long visited = 0;
        private long pruned = 0;
        private long leaves = 0;
        private long updates = 0;

        Solver(int[] weights, int[] values, int capacity,
               Order order, Bound boundKind) {
            if (weights == null || values == null
                    || weights.length != values.length
                    || capacity < 0 || order == null
                    || boundKind == null) {
                throw new IllegalArgumentException("Invalid input");
            }

            this.capacity = capacity;
            this.order = order;
            this.boundKind = boundKind;

            items = new Item[weights.length];
            for (int i = 0; i < weights.length; i++) {
                if (weights[i] <= 0 || values[i] < 0) {
                    throw new IllegalArgumentException(
                            "Weights must be positive, values nonnegative");
                }
                items[i] = new Item(i, weights[i], values[i]);
            }

            // Ratio a.v/a.w cao hơn đứng trước, không dùng double.
            Arrays.sort(items, (a, b) -> {
                long av = (long) a.value() * b.weight();
                long bv = (long) b.value() * a.weight();
                int cmp = Long.compare(bv, av);
                return cmp != 0
                        ? cmp : Integer.compare(a.id(), b.id());
            });

            selected = new boolean[items.length];
            suffix = new long[items.length + 1];
            for (int i = items.length - 1; i >= 0; i--) {
                suffix[i] = Math.addExact(suffix[i + 1],
                                           (long) items[i].value());
            }
        }

        private void rememberIfBetter(long currentValue) {
            if (currentValue <= best) {
                return;
            }
            best = currentValue;
            updates++;

            List<Integer> ids = new ArrayList<>();
            for (int j = 0; j < items.length; j++) {
                if (selected[j]) {
                    ids.add(items[j].id());
                }
            }
            ids.sort(Integer::compareTo);
            bestItems = List.copyOf(ids);
        }

        // Cận lỏng: coi như có thể lấy toàn bộ giá trị còn lại.
        private long suffixUpper(int index, long currentValue) {
            return Math.addExact(currentValue, suffix[index]);
        }

        // Cận chặt hơn: giải thư giãn fractional cho các món còn lại.
        // Chi phí và giá trị đều nguyên, nên floor(cận thực) an toàn.
        private long fractionalUpper(int index, int usedWeight,
                                     long currentValue) {
            int remaining = capacity - usedWeight;
            long upper = currentValue;

            for (int j = index; j < items.length && remaining > 0; j++) {
                Item item = items[j];

                if (item.weight() <= remaining) {
                    upper = Math.addExact(upper,
                                           (long) item.value());
                    remaining -= item.weight();
                } else {
                    long numerator = (long) remaining * item.value();
                    upper = Math.addExact(upper,
                                         numerator / item.weight());
                    break;
                }
            }
            return upper;
        }

        private void tryTake(int index, int usedWeight,
                             long currentValue) {
            Item item = items[index];
            if (item.weight() > capacity - usedWeight) {
                return;
            }

            selected[index] = true;
            dfs(index + 1, usedWeight + item.weight(),
                Math.addExact(currentValue, (long) item.value()));
            selected[index] = false;
        }

        private void trySkip(int index, int usedWeight,
                             long currentValue) {
            dfs(index + 1, usedWeight, currentValue);
        }

        private void dfs(int index, int usedWeight, long currentValue) {
            visited++;
            rememberIfBetter(currentValue);

            if (index == items.length) {
                leaves++;
                return;
            }

            long upper = (boundKind == Bound.SUFFIX)
                    ? suffixUpper(index, currentValue)
                    : fractionalUpper(index, usedWeight, currentValue);

            // Chỉ cần một nghiệm tối ưu; không cần tìm nghiệm hòa.
            if (upper <= best) {
                pruned++;
                return;
            }

            if (order == Order.TAKE_FIRST) {
                tryTake(index, usedWeight, currentValue);
                trySkip(index, usedWeight, currentValue);
            } else {
                trySkip(index, usedWeight, currentValue);
                tryTake(index, usedWeight, currentValue);
            }
        }

        Stats solve() {
            dfs(0, 0, 0L);
            return new Stats(best, bestItems,
                             visited, pruned, leaves, updates);
        }
    }

    private static Stats solve(int[] weights, int[] values,
                               int capacity, Order order, Bound bound) {
        return new Solver(weights, values, capacity, order, bound)
                .solve();
    }

    private static void show(String label, Stats s) {
        System.out.println(label
                + ": best=" + s.best()
                + ", items=" + s.items()
                + ", visited=" + s.visited()
                + ", pruned=" + s.pruned()
                + ", leaves=" + s.leaves()
                + ", updates=" + s.updates());
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5, 9, 7, 6, 3};
        int[] values = {3, 4, 5, 8, 10, 9, 11, 3};
        int capacity = 15;

        show("Suffix + TAKE", solve(weights, values, capacity,
                Order.TAKE_FIRST, Bound.SUFFIX));
        show("Suffix + SKIP", solve(weights, values, capacity,
                Order.SKIP_FIRST, Bound.SUFFIX));
        show("Fractional + TAKE", solve(weights, values, capacity,
                Order.TAKE_FIRST, Bound.FRACTIONAL));
        show("Fractional + SKIP", solve(weights, values, capacity,
                Order.SKIP_FIRST, Bound.FRACTIONAL));

        show("Empty", solve(new int[] {}, new int[] {}, 0,
                Order.TAKE_FIRST, Bound.FRACTIONAL));
        show("Zero capacity", solve(new int[] {5},
                new int[] {10}, 0,
                Order.TAKE_FIRST, Bound.FRACTIONAL));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 BranchBoundOrderAndBoundsDemo.java
java BranchBoundOrderAndBoundsDemo
~~~

Stdout (các thống kê phụ thuộc chính xác vào thứ tự/cách đếm trong mã):

~~~text
Suffix + TAKE: best=24, items=[2, 3, 6], visited=122, pruned=32, leaves=5, updates=5
Suffix + SKIP: best=24, items=[2, 3, 6], visited=167, pruned=23, leaves=29, updates=12
Fractional + TAKE: best=24, items=[2, 3, 6], visited=21, pruned=4, leaves=2, updates=5
Fractional + SKIP: best=24, items=[2, 3, 6], visited=93, pruned=20, leaves=17, updates=12
Empty: best=0, items=[], visited=1, pruned=0, leaves=1, updates=0
Zero capacity: best=0, items=[], visited=1, pruned=1, leaves=0, updates=0
~~~

### Giải thích thống kê

- **visited:** tăng khi **bắt đầu một lời gọi dfs**. Một nhánh TAKE không vừa trọng lượng không tạo lời gọi, nên không tính visited.
- **pruned:** tăng tại các lời gọi dfs mà cận trên không vượt best; sau đó **không** tạo con.
- **leaves:** tăng khi index==n. Số lá này **không** nhất thiết là số nghiệm khả thi đã được dùng làm incumbent.
- **updates:** tăng mỗi lần currentValue **lớn hơn nghiêm ngặt** best và được ghi lại. Nghiệm cùng giá trị không thay best.
- **items:** ID gốc, sắp tăng để hiển thị; các món thực tế được xét theo mật độ giảm, vì vậy dãy chỉ số xuất ra không phải thứ tự thử.
- **Empty:** không có món; dfs gốc đồng thời là lá, best=0 và có một nghiệm là tập rỗng.
- **Zero capacity:** còn một món nặng 5 nhưng W=0; cận fractional bằng 0 ngay ở gốc, nên gốc bị cắt. Tập rỗng vẫn là nghiệm tối ưu giá trị 0, dù chương trình không đi tới lá.

### Phân biệt giới hạn học thuật với hệ thống thật

Mã dùng DFS đệ quy và các mảng trong RAM. Với n rất lớn, số nút có thể tăng theo cấp số mũ và độ sâu stack O(n), gây tốn thời gian hoặc tràn stack; thực tế có thể cần biểu diễn lặp hoặc quản lý ngân sách tìm kiếm.

Math.addExact giúp phát hiện tràn long ở tổng giá trị. Trong khi đó, tích của hai số int dương trong phép so mật độ và khi tính một phần fractional được chuyển sang long **trước phép nhân**, tránh tràn int. Với dữ liệu số học ngoài miền long hoặc biến thể giá trị thực, cần kiểu số/cận số học khác và chứng minh lại tính an toàn.

Chương trình chỉ bảo đảm một nghiệm tối ưu dưới hợp đồng w>0, v≥0, W≥0; nó **không** liệt kê mọi nghiệm đồng tối ưu, không nhận giá trị âm và không tạo cơ chế hủy giữa chừng.

## 12. Vì sao mã trên vẫn tìm đúng nghiệm tối ưu?

Có thể chứng minh bằng bất biến và cắt nhánh an toàn.

### 12.1. Tính hợp lệ của incumbent

Ban đầu best=0 đại diện tập rỗng, hợp lệ khi W≥0. Mọi lời gọi dfs chỉ được tạo từ:
- SKIP không tăng trọng lượng.
- TAKE chỉ khi w[index]≤W−usedWeight.

Vì thế mọi tập selected tại nút là hợp lệ, với currentValue đúng bằng tổng giá trị các món đã lấy. Hàm rememberIfBetter chỉ cập nhật best bằng currentValue của một tập hợp lệ. Do đó best luôn là **giá trị của một nghiệm khả thi**, không vượt giá trị tối ưu thật.

### 12.2. Tính hợp lệ của cận suffix

Với các món giá trị không âm, mọi cách chọn các món còn lại có giá trị thêm không vượt tổng giá trị của tất cả món còn lại. Vì vậy UB_suffix là cận trên của mọi nghiệm hoàn chỉnh từ nút.

### 12.3. Tính hợp lệ của cận fractional

Mọi tập 0/1 còn lại là một phương án hợp lệ của bài toán fractional khi cho phép mức chọn từng món trong [0,1]. Tối ưu fractional tính bằng cách ưu tiên mật độ cao, nên không thấp hơn tối ưu 0/1. Làm tròn xuống một cận thực vẫn bảo toàn bất đẳng thức với **mục tiêu nguyên**, vì nếu tối ưu nguyên không vượt một số thực thì nó không vượt phần nguyên xuống của số đó.

### 12.4. Không bỏ sót một nghiệm có thể cải thiện best

Nếu một nút **không bị cắt**, thuật toán thử TAKE (khi vừa sức chứa) và SKIP theo một trong hai thứ tự. Hai nhánh bao trùm mọi tập con của những món còn lại. Vì vậy mọi lựa chọn hợp lệ hoặc được thăm, hoặc thuộc cây con đã bị cắt.

Nếu một cây con bị cắt, tất cả nghiệm trong đó có giá trị không vượt UB≤best. Chúng không thể cải thiện best. Khi DFS hoàn thành, không còn nghiệm chưa xét nào có thể tốt hơn incumbent, nên best là **giá trị tối ưu toàn cục**.

**Tại sao thứ tự không ảnh hưởng tính đúng?** TAKE-first và SKIP-first chỉ đảo thứ tự xét hai nhánh, không loại nhánh nào mà chưa có chứng cứ UB≤best. Khi duyệt hoàn tất, cả hai giữ được lập luận bao phủ toàn bộ không gian lời giải.

### 12.5. Tính đúng của danh sách món

Mỗi lần best cải thiện, chương trình chụp lại các ID gốc của selected, không dùng tham chiếu mutable đến trạng thái đang quay lui. Các ID không lặp vì mỗi món được quyết định đúng một lần, và tổng trọng lượng của chúng không vượt W. Vì mỗi lần cập nhật lưu danh sách tương ứng với currentValue mới, danh sách bestItems cuối có đúng giá trị best.

Trên bộ mẫu, best=24 và items=[2,3,6] cho tổng trọng lượng 4+5+6=15, tổng giá trị 5+8+11=24 — vừa thỏa sức chứa vừa tối ưu.

## 13. Khi nào cận fractional thực sự đáng giá?

Một cận đáng dùng khi **lợi ích giảm nút duyệt** lớn hơn **chi phí tính cận và tiền xử lý**.

### Trường hợp thuận lợi

- **Sức chứa chặt** so với tổng trọng lượng của nhiều món: cận suffix giả định lấy mọi món, nên rất lỏng.
- **Dữ liệu phân biệt rõ mật độ:** fractional relaxation nhanh chóng nhận ra chỉ vài món có thể lấp đầy dung lượng với giá trị cao nhất.
- **Nhiều nhánh sâu có cấu hình gần giống nhau:** cắt sớm tại một nút giúp loại cả cây con lớn.
- **Đã có incumbent tốt:** cận chặt càng dễ tạo UB≤best.

### Trường hợp lợi ích ít

- **W đủ lớn để chứa mọi món:** hai cận thường bằng tổng giá trị, và bài toán có thể giải trực tiếp bằng cách lấy tất cả món giá trị không âm.
- **Đầu vào n rất nhỏ:** việc quét O(n) món cho fractional tại mỗi nút có thể tốn hơn lợi ích giảm vài nút.
- **Cận suffix đã sát:** chẳng hạn chỉ còn rất ít món hoặc phần còn lại toàn món vừa sức chứa, fractional và suffix không khác biệt nhiều.
- **Bài có điều kiện phụ không nằm trong relaxation:** cận fractional vẫn có thể hợp lệ nếu relaxation thật sự nới lỏng mọi ràng buộc; nhưng nó có thể lỏng vì bỏ qua những điều kiện khác.

Cần benchmark trên nhiều lớp đầu vào thực tế, không chỉ một trường hợp mẫu. Khi báo kết quả đo, ghi rõ **số nút, số lần tính bound, thời gian chạy, bộ dữ liệu, thứ tự nhánh và incumbent khởi tạo**, vì các số liệu không thể so sánh nếu điều kiện đo khác nhau.

## 14. DFS, best-first và chiến lược chọn nút mở

Ví dụ Java dùng **DFS** nên độ sâu trạng thái hoạt động O(n). Có thể thay chiến lược lấy nút trong hàng đợi:
- **DFS:** xử lý sâu một nhánh rồi quay lại; dùng stack đệ quy hoặc stack tường minh. Có thể tìm một nghiệm hoàn chỉnh sớm và dùng ít bộ nhớ tìm kiếm.
- **Best-first:** ưu tiên nút có **cận trên lớn nhất** trong bài tối đa hóa, thường dùng hàng đợi ưu tiên. Ý tưởng là khám phá nút có tiềm năng cao nhất trước để tăng best và giảm số nút cần mở.
- **Breadth-first:** xét theo độ sâu; dễ mô tả nhưng có thể giữ rất nhiều nút chưa xử lý trong RAM.

**Best-first không phải phép bảo đảm thần kỳ:** nó có thể cần giữ nhiều nút mở trong priority queue và có chi phí O(log M) cho thao tác heap với M nút đang mở. Một cận không chặt cũng khiến priority queue ưu tiên sai những nút nhìn có vẻ hứa hẹn. Đổi thứ tự node bằng heuristic không thay được yêu cầu **cận hợp lệ**.

Khi dùng best-first, có thể có điều kiện kết thúc mạnh: nếu incumbent≥cận trên lớn nhất của mọi nút còn mở, đã chứng minh không có nhánh nào cải thiện incumbent. Nhưng phải xét đầy đủ các nút mở, dùng cận có chứng minh và xử lý tie đúng theo yêu cầu đầu ra.

Trong bài minimization, best-first thường ưu tiên **nút có cận dưới nhỏ nhất**; lại phải đổi hướng bất đẳng thức tương ứng.

## 15. Những sai lầm phá hỏng tính đúng hoặc làm sai số đo

1. **Lấy giá trị của nghiệm tham lam làm upper bound trong bài maximization.** Nghiệm tham lam chỉ là một cận dưới; dùng làm UB có thể cắt nghiệm tốt hơn.
2. **Tính fractional bound trên các món chưa được sắp đúng mật độ**, nhưng vẫn dùng thuật toán “lấy món theo thứ tự” và tưởng đó là tối ưu fractional. Một nghiệm fractional bất kỳ **không** phải cận trên an toàn cho bài 0/1.
3. **Dùng số thực rồi làm tròn sai chiều** khiến UB thấp hơn tối ưu có thể đạt. Với giá trị nguyên không âm, phép chia nguyên floor trong code có chứng minh riêng.
4. **Quên cộng currentValue** vào UB, chỉ tính phần giá trị có thể thêm. Khi đó cận có thể quá thấp và cắt sai.
5. **Quên trừ usedWeight** khi xác định sức chứa còn lại. Cận tính sai không gian lựa chọn; có thể quá cao hoặc quá thấp tùy công thức.
6. **Tính suffixValue trên tập món sai** (ví dụ chỉ số index trong mảng gốc nhưng DFS theo mảng đã sắp).
7. **Không kiểm tra tính khả thi của incumbent:** best cao do một tập overweight có thể khiến thuật toán cắt nhầm tất cả nhánh hợp lệ.
8. **Cập nhật incumbent ở nút trong khi tập hiện tại chưa phải nghiệm khả thi** của một bài toán yêu cầu đủ k phần tử hoặc ràng buộc toàn cục.
9. **Cắt khi UB≥best** trong bài maximization, tức đảo chiều bất đẳng thức; loại ngay các nhánh còn có tiềm năng.
10. **Dừng DFS ngay khi gặp nghiệm đầu tiên** trong một bài tối ưu; đó chỉ là find-first, không phải branch-and-bound chứng minh tối ưu.
11. **Hiểu UB==best là chắc chắn không có nghiệm đồng tối ưu khác.** Đúng để bỏ nhánh khi chỉ cần một nghiệm, không đủ nếu cần liệt kê tất cả.
12. **Không hoàn tác selected sau TAKE**, làm trạng thái nhánh SKIP mang theo món từ nhánh trước.
13. **Không chụp lại bestItems khi best tăng** hoặc dùng tham chiếu tới mảng selected mutable, làm lời giải cuối không khớp best.
14. **Không xử lý n=0 hoặc W=0:** tập rỗng là nghiệm hợp lệ; cận có thể cắt ở gốc mà vẫn đúng.
15. **Dùng giá trị âm với cận suffix/fractional không thiết kế cho số âm.** Định nghĩa và relaxation cần được điều chỉnh; ví dụ từ chối v<0.
16. **Dùng int cho phép nhân chéo mật độ** và gây overflow; ép long trước khi nhân.
17. **Nhầm số pruned lớn là thuật toán tốt hơn** mà không tính các cây con bị loại gián tiếp và số visited thực tế.
18. **So thời gian chạy giữa các phiên bản khác thứ tự sắp món hoặc incumbent ban đầu** rồi quy chênh lệch hoàn toàn cho một yếu tố.
19. **Coi visited là số trạng thái lá/nghiệm:** visited đếm mọi lời gọi, cả nút trong và nút bị cắt.
20. **Coi số nút ít hơn luôn nhanh hơn:** một cận chặt có thể quá đắt để tính, nhất là ở n nhỏ.
21. **Nhầm “cận chặt” với “cắt mạnh bất kể tính đúng”.** Cận chỉ được dùng để loại nhánh khi là một giới hạn có chứng minh.
22. **Tuyên bố đạt tối ưu khi bị timeout hoặc hủy trước khi duyệt/cắt hết cây.** Khi chưa có chứng chỉ kết thúc, chỉ có incumbent tốt nhất hiện tại, không chắc tối ưu.

## 16. Kiểm thử và đối chiếu độc lập

Với n nhỏ, có thể duyệt toàn bộ \(2^n\) tập con bằng bitmask, tính tổng trọng lượng và giá trị, lấy giá trị lớn nhất trong các tập có trọng lượng≤W. Đây là **oracle kiểm thử** cho B&B.

Bộ test nên xác minh:
1. Cả bốn tổ hợp **SUFFIX/FRACTIONAL × TAKE_FIRST/SKIP_FIRST** trả cùng giá trị tối ưu.
2. bestItems không có ID trùng, mọi ID nằm trong miền [0,n), tổng trọng lượng≤W và tổng giá trị bằng best.
3. Khi có n=0 hoặc W=0, đáp án 0 với tập rỗng.
4. Với W chứa được tất cả món, giá trị tối ưu bằng tổng giá trị tất cả món (v≥0).
5. Khi tất cả món đều nặng hơn W, tập rỗng tối ưu; fractional bound ở gốc có thể 0 nếu W=0.
6. Với nhiều món có cùng mật độ, tie-break sắp ID ổn định; kết quả tối ưu không được phụ thuộc vào việc sort có ổn định hay không.
7. Khi chỉ có món giá trị 0, best=0 là tối ưu; không nhất thiết liệt kê tất cả tập có giá trị 0.
8. Với các bộ nhỏ ngẫu nhiên, so B&B với brute force để phát hiện cắt sai do bound.
9. Số nút thống kê được đo theo định nghĩa nhất quán, không trộn “nút được tạo” với “nút đã vào dfs”.
10. Nếu dùng dữ liệu lớn có thể gây overflow, phải phát hiện hoặc dùng kiểu số đủ lớn, không chấp nhận kết quả âm bất thường.

**Một phép kiểm nhỏ để thấy cần cận đúng:** với W=10 và ba món (9,19), (5,10), (5,10), thuật toán tham lam có thể chọn 19, nhưng brute force xác nhận 20. Nếu một “cận” sai khiến DFS cắt nhánh chứa hai món 5 thì kết quả 19 là **sai**, dù chương trình chạy nhanh.

**Kiểm tra kết quả thực nghiệm:** bảng thống kê ở mục 9 là phép đo của **đúng chương trình Java** với dữ liệu và chính sách đã định. Khi thay một chi tiết như cập nhật best tại lá thay vì nút trong, số visited/pruned/leaves/updates có thể khác; điều đó không có nghĩa phiên bản mới sai nếu nghiệm tối ưu và cận hợp lệ vẫn đúng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Trong bài maximization, incumbent và upper bound khác nhau thế nào?

**Đáp án:** Incumbent là giá trị của **một nghiệm khả thi đã biết**, nên không vượt tối ưu toàn cục. Upper bound tại nút là **giới hạn trên** của mọi nghiệm hoàn chỉnh từ nút ấy. Có thể cắt khi UB≤incumbent nếu chỉ cần một nghiệm tối ưu.

**Câu 2.** Vì sao thử TAKE trước có thể giảm số nút DFS?

**Đáp án:** Nó có thể tạo nghiệm có giá trị cao sớm, làm incumbent tăng. Nhiều nhánh sau có UB≤incumbent nên bị cắt. Nhưng không bảo đảm TAKE luôn tốt hơn SKIP trên mọi dữ liệu.

**Câu 3.** Cận suffix 53 ở nút gốc ví dụ có đúng không?

**Đáp án:** Đúng vì mọi v≥0 nên không tập con nào vượt tổng giá trị tất cả món 53. Nó **rất lỏng**, vì phần lớn tổ hợp không vừa W=15.

**Câu 4.** Vì sao fractional relaxation tạo UB hợp lệ cho ba lô 0/1?

**Đáp án:** Bài fractional cho phép lấy một phần món, có tập nghiệm rộng hơn 0/1. Tối ưu fractional vì vậy không nhỏ hơn tối ưu 0/1 còn lại. Sau khi sort theo mật độ, chọn trọn các món tốt nhất rồi một phần món kế tiếp cho tối ưu fractional.

**Câu 5.** Tại nút gốc ví dụ, cận fractional nguyên bằng mấy?

**Đáp án:** Lấy các món [6,3,0] được 22 giá trị, còn 2 đơn vị trọng lượng và lấy 2/3 món 1 thêm 8/3. Cận thực 24+2/3; vì giá trị 0/1 nguyên, cận nguyên **24**.

**Câu 6.** Cận fractional nhỏ hơn suffix có bảo đảm chạy nhanh hơn không?

**Đáp án:** Không tuyệt đối. Nó thường làm giảm số nút được mở, nhưng phải tốn thời gian O(n) cho mỗi lần tính cận trong bản đơn giản, so với O(1) của suffix.

**Câu 7.** Vì sao trong bảng thống kê số nút pruned của cấu hình fractional TAKE nhỏ hơn suffix TAKE dù tốt hơn?

**Đáp án:** Fractional cắt sớm ở các nút cao, nên nhiều nút phía dưới **không bao giờ được thăm** và không thể được đếm là pruned. Nên đánh giá visited và thời gian thay vì chỉ pruned.

**Câu 8.** Nếu phải liệt kê tất cả nghiệm cùng giá trị tối ưu, có được cắt khi UB==best không?

**Đáp án:** Không thể mặc định, vì cây con có thể chứa nghiệm khác cũng đạt best. Điều kiện cắt phải được điều chỉnh để không mất những nghiệm đồng tối ưu cần xuất.

**Câu 9.** Cách khôi phục danh sách món trong DFS cần lưu gì?

**Đáp án:** Trạng thái selected hiện tại và **bản sao ID các món** khi best cải thiện. Chỉ lưu tham chiếu mutable rồi quay lui có thể làm danh sách nghiệm đã ghi bị thay đổi.

**Câu 10.** Với bài minimization, điều kiện cắt tương đương là gì?

**Đáp án:** Tính **lower bound** cho mọi nghiệm trong cây con và cắt khi LB≥best, trong đó best là chi phí của một nghiệm khả thi đã biết.

**Câu 11.** Việc sort theo mật độ và TAKE-first có chứng minh nghiệm đầu tiên tối ưu không?

**Đáp án:** Không. Ba lô 0/1 có thể có bộ món khác ghép vừa sức chứa hơn; mật độ chỉ là heuristic tìm nhanh và là cơ sở của fractional bound, không phải chứng minh nghiệm 0/1 tối ưu.

**Câu 12.** Nếu quá giới hạn thời gian tìm kiếm, có thể báo best hiện tại là tối ưu không?

**Đáp án:** Chỉ khi đã có chứng cứ rằng mọi nút chưa xét không thể cải thiện best, ví dụ mọi UB≤best. Nếu còn nhánh mở có UB>best, best chỉ là **nghiệm tốt nhất đã biết**, chưa chắc tối ưu.

**Ghi nhớ:** Nhánh và cận thắng nhờ **nghiệm khả thi tốt được tìm sớm** cộng với **cận đúng và chặt**. Thứ tự nhánh quyết định khi nào incumbent tăng; độ chặt của cận quyết định nhánh nào có thể được loại một cách có chứng minh. Cùng một thuật toán đúng có thể thăm rất khác số nút, nhưng không được đánh đổi **tính an toàn của cận** lấy tốc độ rồi vẫn tuyên bố tối ưu.
