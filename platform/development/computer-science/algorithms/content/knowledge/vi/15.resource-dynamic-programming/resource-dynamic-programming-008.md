# Trạng thái theo sức chứa và trạng thái theo tổng giá trị

## 1. Hai trục trạng thái trong quy hoạch động tài nguyên

Khi áp dụng **quy hoạch động (dynamic programming, DP)**, cùng một bài toán tối ưu có thể được mô hình hóa bằng những **trạng thái khác nhau**. Đối với bài toán ba lô 0/1, có hai hướng rất hữu ích:

- **DP theo sức chứa (capacity-indexed):** nếu giới hạn trọng lượng là c, **giá trị lớn nhất** của một tập món hợp lệ là bao nhiêu?
- **DP theo tổng giá trị (value-indexed):** nếu muốn đạt **đúng giá trị v**, **trọng lượng nhỏ nhất** phải mang là bao nhiêu?

Hai câu hỏi không giống nhau, nhưng có thể dùng để giải cùng mục tiêu: **tối đa hóa tổng giá trị với tổng trọng lượng không vượt quá W**. Đổi trục trạng thái không chỉ là đổi tên mảng; nó thay đổi **ý nghĩa ô, phép tối ưu, giá trị khởi tạo, điều kiện lấy đáp án và cách truy vết**.

Việc chọn trục thường nhằm giảm số trạng thái: nếu W nhỏ, trục sức chứa thuận lợi; nếu W rất lớn nhưng tổng giá trị các món nhỏ, trục giá trị thường hiệu quả hơn.

## 2. Bài toán ba lô 0/1 và hợp đồng dữ liệu

Có n món hàng, đánh số từ 0 tới n−1. Món i có:
- Trọng lượng nguyên dương \(w_i>0\).
- Giá trị nguyên không âm \(v_i\ge0\).
- Có thể chọn **tối đa một lần**.

Ba lô có sức chứa nguyên \(W\ge0\). Tìm một tập chỉ số S sao cho:

\[
\sum_{i\in S}w_i\le W
\]

và tối đa hóa:

\[
\operatorname{value}(S)=\sum_{i\in S}v_i.
\]

Tập rỗng luôn hợp lệ, giá trị 0, trọng lượng 0. Đầu vào có thể không có món nào. Nếu có nhiều tập có cùng giá trị tối ưu, đề có thể chấp nhận bất kỳ tập nào hoặc đưa thêm tiêu chí phụ; ta phải xác định điều đó khi xây dựng thuật toán truy vết.

**Ví dụ xuyên suốt:**

| Chỉ số món | Trọng lượng | Giá trị |
|---|---:|---:|
| 0 | 2 | 3 |
| 1 | 3 | 4 |
| 2 | 4 | 5 |
| 3 | 5 | 8 |

Với W=8, chọn các món **1 và 3** được trọng lượng 3+5=8 và giá trị 4+8=12. Đây là **giá trị tối ưu**; cả hai hướng DP đều phải ra 12.

**Phạm vi:** các công thức và mã Java bên dưới là cho **0/1 knapsack**. Với ba lô được dùng mỗi món không giới hạn, trọng lượng âm, giá trị âm hoặc nhiều ràng buộc tài nguyên, cần thiết kế lại hợp đồng và trạng thái, không sao chép nguyên xi công thức.

## 3. DP theo sức chứa: tối đa giá trị dưới một ngưỡng tài nguyên

### 3.1. Định nghĩa trạng thái

Đặt:

\[
C[i][c]=\text{giá trị lớn nhất chọn từ i món đầu, với tổng trọng lượng KHÔNG QUÁ c}.
\]

Miền \(0\le i\le n,\;0\le c\le W\).

Từ “**không quá c**” rất quan trọng: một tập nặng 6 vẫn hợp lệ ở trạng thái c=8. Không được nhầm C[i][c] là giá trị cao nhất của tập **nặng đúng c**, vì bài toán đó có cơ sở và trạng thái không thể đạt khác.

### 3.2. Khởi tạo

Không có món thì giá trị tốt nhất bằng 0 dù sức chứa là bao nhiêu:

\[
C[0][c]=0.
\]

Do các món có trọng lượng dương, sức chứa 0 không thể chứa món nào:

\[
C[i][0]=0.
\]

Một bảng long[][] trong Java mặc định bằng 0 nên cơ sở này thuận tiện, với điều kiện cách định nghĩa trạng thái vẫn là **không quá sức chứa**.

### 3.3. Công thức truy hồi

Xét món thứ i theo cách đánh số 1-based của công thức, có trọng lượng w_i và giá trị v_i. Mọi tập hợp lệ thuộc đúng một trong hai trường hợp:

1. **Bỏ món i:** dùng i−1 món đầu, giá trị tối đa \(C[i-1][c]\).
2. **Lấy món i:** chỉ hợp lệ khi \(w_i\le c\); phần còn lại là lời giải cho i−1 món và sức chứa \(c-w_i\), giá trị \(v_i+C[i-1][c-w_i]\).

Do đó:

\[
C[i][c]=
\begin{cases}
C[i-1][c],&w_i>c,\\
\max\bigl(C[i-1][c],\,v_i+C[i-1][c-w_i]\bigr),&w_i\le c.
\end{cases}
\]

Đáp án:

\[
\boxed{C[n][W]}.
\]

Cả hai nhánh đều phải dựa trên **hàng i−1**. Nếu nhánh lấy dùng C[i][c−w_i], ta có thể lấy món i lần thứ hai, làm sai bài toán 0/1.

### 3.4. Chứng minh cấu trúc con tối ưu

Giả sử một lời giải tối ưu của trạng thái (i,c):
- Nếu **không lấy** món i mà tập các món trước đó không tối ưu cho C[i−1][c], ta có thể thay nó bằng một tập tốt hơn, vẫn hợp lệ và cải thiện tổng giá trị. Mâu thuẫn với tối ưu.
- Nếu **có lấy** món i, khi bỏ món này phần còn lại nặng không quá c−w_i. Nếu phần còn lại chưa tối ưu cho C[i−1][c−w_i], thay bằng phần tối ưu hơn rồi thêm lại món i sẽ tạo lời giải hợp lệ tốt hơn. Cũng mâu thuẫn.

Hai trường hợp bao phủ mọi tập có thể chọn, nên lấy max là đúng. Điều kiện cơ sở đúng; bằng quy nạp theo i, toàn bảng C được tính đúng.

### 3.5. Bảng minh họa W=8

| Sau khi xét | c=0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 món | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Món 0: (2,3) | 0 | 0 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Món 1: (3,4) | 0 | 0 | 3 | 4 | 4 | 7 | 7 | 7 | 7 |
| Món 2: (4,5) | 0 | 0 | 3 | 4 | 5 | 7 | 8 | 9 | 9 |
| Món 3: (5,8) | 0 | 0 | 3 | 4 | 5 | 8 | 8 | 11 | **12** |

Ví dụ C[4][8]=max(C[3][8],8+C[3][3])=max(9,8+4)=12.

**Truy vết:** đi từ (i=n,c=W) về hàng 0. Nếu C[i][c] bằng C[i−1][c], có thể bỏ món i−1; nếu khác, nhánh lấy là bắt buộc để giữ giá trị tối ưu, ghi món i−1 rồi giảm c đi trọng lượng của món đó. Đi tiếp về i−1. Sau khi kết thúc, đảo danh sách chỉ số đã chọn. Quy tắc ưu tiên **bỏ món khi hai nhánh hòa** là một tie-break hợp lệ.

## 4. DP theo tổng giá trị: tối thiểu trọng lượng để đạt đúng giá trị

### 4.1. Đổi câu hỏi và trục chỉ số

Đặt tổng giá trị của tất cả món:

\[
V=\sum_{i=0}^{n-1}v_i.
\]

Với giá trị nguyên không âm, tổng giá trị của một tập món nằm trong khoảng 0..V. Đặt:

\[
M[i][v]=\text{trọng lượng NHỎ NHẤT để đạt ĐÚNG tổng giá trị v bằng i món đầu}.
\]

Nếu không thể đạt đúng v, gán M[i][v]=**INF** (vô cùng/không đạt được).

**Sự khác biệt trọng tâm:**
- C hỏi **max value** khi tài nguyên dùng **không quá c**.
- M hỏi **min weight** để đạt **đúng v**.

Nếu đổi “đúng v” thành “ít nhất v”, ý nghĩa trạng thái đã khác và phải tự chứng minh lại công thức; không được trộn lẫn hai định nghĩa.

### 4.2. Khởi tạo: INF là thiết yếu

Khi chưa có món nào, chỉ giá trị 0 có thể đạt:

\[
M[0][0]=0,\qquad
M[0][v>0]=INF.
\]

Không khởi tạo cả hàng bằng 0 như capacity DP! Nếu M[0][5]=0 thì bảng sẽ giả vờ có thể tạo giá trị 5 với trọng lượng 0 mà không chọn món nào.

INF chỉ biểu thị **không thể đạt trạng thái**. Khi lập trình, phải **kiểm tra trạng thái nguồn khác INF trước khi cộng trọng lượng** để tránh overflow.

### 4.3. Công thức truy hồi

Ở món thứ i (theo công thức 1-based), xét hai trường hợp:

- **Không lấy:** trọng lượng tốt nhất để đạt đúng v từ i−1 món trước là M[i−1][v].
- **Có lấy:** nếu v≥v_i và M[i−1][v−v_i] đạt được, trọng lượng là \(w_i+M[i-1][v-v_i]\).

Vì mục tiêu của bảng này là **trọng lượng nhỏ nhất**, công thức là:

\[
M[i][v]=\min\Bigl(
 M[i-1][v],\;
 M[i-1][v-v_i]+w_i
\Bigr),
\]

với nhánh lấy được coi là INF nếu v<v_i hoặc M[i−1][v−v_i]=INF.

Lưu ý cả hai nhánh dựa trên **i−1**, vì một món chỉ được chọn một lần. Mỗi ô lưu trọng lượng nhỏ nhất cho **tổng giá trị chính xác v**, không lưu giá trị lớn nhất.

### 4.4. Từ M trở lại mục tiêu sức chứa W

Giá trị v đạt được trong sức chứa W **khi và chỉ khi**:

\[
M[n][v]\le W.
\]

Do đó đáp án ban đầu là:

\[
\boxed{v^*=\max\{v\in[0,V]\mid M[n][v]\le W\}}.
\]

Có thể duyệt v từ V xuống 0 và lấy giá trị đầu tiên thỏa điều kiện. V=0 luôn khả thi qua tập rỗng nên phép tìm có kết quả.

**Không trả M[n][V]**: ô đó là **trọng lượng nhỏ nhất để lấy đúng tổng giá trị của tất cả món**, không phải giá trị tối ưu dưới W. Nó có thể lớn hơn W.

### 4.5. Chứng minh tính đúng

Mọi tập món đạt đúng v trong i món đầu phải thuộc một trong hai nhóm:
1. Không lấy món i: trọng lượng ít nhất M[i−1][v].
2. Có lấy món i: bỏ món i ra sẽ đạt đúng v−v_i bằng i−1 món trước; phần còn lại phải nhẹ nhất có thể, nếu không ta thay bằng phần nhẹ hơn mà không làm đổi giá trị v và cải thiện tổng trọng lượng.

Chọn min của hai nhóm cho trọng lượng nhỏ nhất để đạt v. Cơ sở đúng, nên quy nạp theo i cho M chính xác. Mà một giá trị v đạt được dưới W tương đương trọng lượng nhỏ nhất của nó không vượt W, nên:

\[
\boxed{C[n][W]=\max\{v\mid M[n][v]\le W\}}.
\]

Hai hướng có **cùng giá trị tối ưu cuối cùng**, dù bảng lưu hai loại kết quả khác nhau.

### 4.6. Truy vết trên trục giá trị

Đầu tiên tìm v*. Bắt đầu tại (i=n, v=v*):
- Nếu M[i][v]==M[i−1][v], có thể bỏ món i−1 mà vẫn giữ trọng lượng nhỏ nhất.
- Nếu khác, nhánh lấy tạo giá trị tối ưu cho trạng thái, ghi món i−1 và cập nhật v←v−v_{i−1}.
- Mỗi bước giảm i; cuối cùng v phải trở về 0 khi i=0. Đảo danh sách chỉ số để xuất theo thứ tự tăng.

Khác với capacity DP, truy vết ở đây **giảm giá trị còn cần đạt**, không giảm sức chứa. Nếu có nhiều tập cùng giá trị tốt nhất nhưng trọng lượng khác nhau, hướng M sẽ khôi phục một tập có **trọng lượng nhỏ nhất** để đạt v*, còn hướng C chỉ cần bảo đảm giá trị cao nhất trong W.

## 5. Ví dụ các trạng thái M cho cùng dữ liệu

Với w=[2,3,4,5], v=[3,4,5,8], W=8, V=20, một số giá trị ở hàng M[4][v] là:

| Giá trị v chính xác | Tập món ví dụ | M[4][v] | Thỏa W=8? |
|---|---|---:|---|
| 0 | {} | 0 | Có |
| 1 | Không có | INF | Không |
| 3 | {0} | 2 | Có |
| 4 | {1} | 3 | Có |
| 5 | {2} | 4 | Có |
| 7 | {0,1} | 5 | Có |
| 8 | {3} | 5 | Có |
| 9 | {1,2} | 7 | Có |
| 11 | {0,3} | 7 | Có |
| 12 | {1,3} | 8 | **Có — tối ưu** |
| 13 | {2,3} | 9 | Không |
| 17 | {1,2,3} | 12 | Không |
| 20 | {0,1,2,3} | 14 | Không |

Đây là **các trạng thái tiêu biểu**, không phải toàn bộ hàng. M[4][17]=12 vì tổng giá trị 4+5+8=17 cần các món 1,2,3, nặng 3+4+5=12. Tập {0,1,3} chỉ có giá trị 3+4+8=15, **không** được nhầm thành 17.

Tìm từ v=20 xuống cho tới giá trị thỏa M[4][v]≤8; giá trị lớn nhất như vậy là **12**. C[4][8] cũng bằng 12.

### Tại sao không giữ tất cả các tập đạt cùng giá trị?

Với một giá trị v cố định, nếu tập A nặng 6 còn tập B nặng 9, thì A luôn ít nhất cũng thuận lợi bằng B khi ta chỉ còn điều kiện giới hạn trọng lượng. Vì thế chỉ cần giữ **trọng lượng nhỏ nhất** của mỗi v; đó là nguyên lý loại những trạng thái bị thống trị trong mô hình này.

Nếu còn một điều kiện khác như số món, màu sắc hay giới hạn từng nhóm, chỉ giữ trọng lượng nhỏ nhất có thể **không đủ**. Khi đó trạng thái phải bao gồm thông tin ràng buộc bổ sung; không áp dụng mô hình này ngoài phạm vi đã đặc tả.

## 6. So sánh số trạng thái và tiêu chí chọn hướng

Có n món, sức chứa W và tổng giá trị V=Σv_i. Với **bảng hai chiều**:

| Hướng | Trục thứ hai | Nội dung mỗi ô | Thời gian | Bộ nhớ bảng |
|---|---|---|---|---|
| Sức chứa | c=0..W | Max value với trọng lượng ≤c | O(nW) | O(nW) |
| Tổng giá trị | v=0..V | Min weight đạt đúng v | O(nV) | O(nV) |

Ví dụ đang xét:
- Capacity: (n+1)(W+1)=5×9=**45 ô**.
- Value: (n+1)(V+1)=5×21=**105 ô**.

Ở đây trục sức chứa ngắn hơn.

Một ví dụ ngược lại:
- Trọng lượng [400,600,700].
- Giá trị [5,6,7].
- W=1000; V=18.

Hướng capacity dùng (3+1)(1000+1)=**4004 ô**; hướng value dùng (3+1)(18+1)=**76 ô**. Hướng giá trị tiết kiệm hơn rất nhiều. Đáp án tối ưu là chọn món [0,1], trọng lượng 1000, giá trị 5+6=**11**.

**Cách chọn:**
1. Nếu **W vừa phải**, thường chọn capacity DP vì công thức đơn giản, trực tiếp.
2. Nếu **W rất lớn nhưng tổng V nhỏ**, chọn value DP vì số cột theo V+1 thay vì W+1.
3. Nếu cần danh sách món, tính cả **chi phí truy vết**; không chỉ nhìn độ dài mảng nén 1D.
4. Nếu cả W và V đều rất lớn, cả hai hướng có thể quá tốn kém; xem thêm meet-in-the-middle nếu n nhỏ, các trạng thái Pareto, thuật toán xấp xỉ hoặc cấu trúc riêng của bài toán.

**Không nhầm V với giá trị lớn nhất của một món:** V là **tổng giá trị tất cả món**. Dãy có nhiều món cùng giá trị nhỏ vẫn có thể tạo V lớn.

### Vì sao gọi là giả đa thức?

O(nW) và O(nV) là thời gian **giả đa thức (pseudo-polynomial)**. Nếu các số được ghi bằng nhị phân, W cần O(log W) bit để biểu diễn nhưng thuật toán theo sức chứa có thể lặp O(W) lần trên mỗi món. Tương tự, tổng giá trị V có thể rất lớn so với số bit của các v_i.

Không được khẳng định thuật toán là đa thức theo **độ dài biểu diễn nhị phân** trong mọi trường hợp. Tuy vậy, nếu W hoặc V nhỏ theo ràng buộc đầu vào, chúng rất thực dụng.

## 7. Tối ưu bộ nhớ còn một chiều: phải duyệt giảm

Hai hướng đều có các chuyển trạng thái chỉ sử dụng **hàng trước i−1**. Nếu chỉ cần giá trị tối ưu cuối, có thể dùng một mảng 1D, nhưng thứ tự duyệt là điểm dễ sai nhất.

### 7.1. Nén hướng sức chứa

Khởi tạo best[c]=0 với 0≤c≤W, sau đó với từng món (w,v):

~~~text
for c = W down to w:
    best[c] = max(best[c], best[c-w] + v)
~~~

**Tại sao giảm dần?** Khi đang cập nhật best[c], chỉ số c−w<c chưa được sửa trong vòng duyệt giảm của món hiện tại. Do đó best[c−w] vẫn đại diện cho các món **trước** món đang xét, không tạo việc dùng món đó hai lần.

Phản ví dụ nếu duyệt tăng: chỉ một món (w=2,v=3), W=4. Sau khi ghi best[2]=3, vòng tăng tới c=4 có thể tính best[4]=best[2]+3=6, tức lấy một món hai lần. Đáp án đúng của ba lô 0/1 là 3.

### 7.2. Nén hướng tổng giá trị

Khởi tạo minWeight[0]=0, minWeight[v>0]=INF. Với mỗi món (w, value):

~~~text
for v = V down to value:
    if minWeight[v - value] != INF:
        minWeight[v] = min(
            minWeight[v],
            minWeight[v - value] + w
        )
~~~

Cũng duyệt **giảm dần** để không dùng món hiện tại nhiều lần. Với value=0 và w>0, lấy món chỉ tăng trọng lượng mà không tăng giá trị, nên nhánh lấy không thể cải thiện minWeight[v] và bỏ món là hợp lý.

Không cộng vào INF khi thực hiện phép chuyển. Nếu dùng Long.MAX_VALUE làm INF, phép cộng Long.MAX_VALUE+w có thể tràn sang âm trong Java nếu không kiểm tra.

### 7.3. Nén bảng không tự giữ được thông tin truy vết

Bảng 1D liên tục **ghi đè** giá trị của các lớp i trước đó. Nếu chỉ còn mảng cuối, không thể áp dụng nguyên thuật toán so sánh hàng i với hàng i−1 để tìm món được lấy.

Muốn in tập món, cần:
- Giữ bảng 2D để truy vết rõ ràng; hoặc
- Lưu quyết định/nguồn gốc theo các lớp trạng thái bằng một thiết kế đúng; hoặc
- Chấp nhận tính lại một số trạng thái khi khôi phục nghiệm.

**Đừng ghi “O(W) bộ nhớ và truy vết được trực tiếp”** chỉ vì đã nén bảng. O(W) hay O(V) là bộ nhớ cho **giá trị DP**, chưa tính thông tin bổ sung nếu bài yêu cầu khôi phục tập món.

## 8. Java 17+ độc lập: cài đặt cả hai hướng

Chương trình dưới đây cài đặt **hai bảng 2D** để minh họa phép chuyển và truy vết chính xác. Nó trả về:
- Giá trị tối ưu.
- Tổng trọng lượng của tập món khôi phục.
- Danh sách chỉ số món đã chọn (0-based, tăng dần).

Trong trường hợp hòa, mã ưu tiên **bỏ món xét sau** nếu có thể đạt cùng mục tiêu nhờ các món trước. Số long được sử dụng cho giá trị tích lũy và trọng lượng tối ưu, có kiểm tra tràn bằng Math.addExact. Ví dụ vẫn giả định kích thước bảng đủ nhỏ để cấp phát trong RAM.

Lưu thành **KnapsackStateAxesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public final class KnapsackStateAxesDemo {
    private KnapsackStateAxesDemo() {
    }

    record Solution(long value, long weight, List<Integer> items) {
    }

    private static void validate(int[] weights, int[] values,
                                 int capacity) {
        if (weights == null || values == null
                || weights.length != values.length || capacity < 0) {
            throw new IllegalArgumentException("Invalid knapsack input");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException("Invalid item at " + i);
            }
        }
    }

    public static Solution byCapacity(int[] weights, int[] values,
                                      int capacity) {
        validate(weights, values, capacity);
        if (capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Capacity table too large");
        }

        int n = weights.length;
        long[][] best = new long[n + 1][capacity + 1];

        for (int i = 1; i <= n; i++) {
            for (int c = 0; c <= capacity; c++) {
                long skip = best[i - 1][c];
                long current = skip;
                if (weights[i - 1] <= c) {
                    long take = Math.addExact(
                            best[i - 1][c - weights[i - 1]],
                            (long) values[i - 1]);
                    current = Math.max(skip, take);
                }
                best[i][c] = current;
            }
        }

        List<Integer> picks = new ArrayList<>();
        long usedWeight = 0;
        int c = capacity;
        for (int i = n; i > 0; i--) {
            if (best[i][c] != best[i - 1][c]) {
                picks.add(i - 1);
                c -= weights[i - 1];
                usedWeight += weights[i - 1];
            }
        }

        Collections.reverse(picks);
        return new Solution(best[n][capacity], usedWeight,
                            List.copyOf(picks));
    }

    public static Solution byValue(int[] weights, int[] values,
                                   int capacity) {
        validate(weights, values, capacity);

        long sum = 0;
        for (int v : values) {
            sum = Math.addExact(sum, (long) v);
        }
        if (sum >= Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Value table too large");
        }

        int n = weights.length;
        int totalValue = (int) sum;
        long inf = Long.MAX_VALUE;
        long[][] minWeight = new long[n + 1][totalValue + 1];

        for (long[] row : minWeight) {
            Arrays.fill(row, inf);
        }
        minWeight[0][0] = 0L;

        for (int i = 1; i <= n; i++) {
            int weight = weights[i - 1];
            int value = values[i - 1];

            for (int v = 0; v <= totalValue; v++) {
                long current = minWeight[i - 1][v];

                if (v >= value
                        && minWeight[i - 1][v - value] != inf) {
                    long take = Math.addExact(
                            minWeight[i - 1][v - value],
                            (long) weight);
                    current = Math.min(current, take);
                }
                minWeight[i][v] = current;
            }
        }

        int bestValue = 0;
        for (int v = totalValue; v >= 0; v--) {
            if (minWeight[n][v] <= capacity) {
                bestValue = v;
                break;
            }
        }

        List<Integer> picks = new ArrayList<>();
        int remainingValue = bestValue;
        for (int i = n; i > 0; i--) {
            if (minWeight[i][remainingValue]
                    != minWeight[i - 1][remainingValue]) {
                picks.add(i - 1);
                remainingValue -= values[i - 1];
            }
        }

        Collections.reverse(picks);
        return new Solution(bestValue, minWeight[n][bestValue],
                            List.copyOf(picks));
    }

    private static void show(String label, Solution result) {
        System.out.println(label + ": value=" + result.value()
                + ", weight=" + result.weight()
                + ", items=" + result.items());
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5};
        int[] values = {3, 4, 5, 8};

        show("By capacity", byCapacity(weights, values, 8));
        show("By value", byValue(weights, values, 8));

        show("Large capacity", byValue(
                new int[] {400, 600, 700},
                new int[] {5, 6, 7},
                1000));

        show("Zero capacity", byValue(weights, values, 0));
        show("Tie, skip later item", byCapacity(
                new int[] {2, 2},
                new int[] {3, 3},
                2));

        show("Zero-value item", byValue(
                new int[] {1, 2},
                new int[] {0, 5},
                2));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 KnapsackStateAxesDemo.java
java KnapsackStateAxesDemo
~~~

Stdout:

~~~text
By capacity: value=12, weight=8, items=[1, 3]
By value: value=12, weight=8, items=[1, 3]
Large capacity: value=11, weight=1000, items=[0, 1]
Zero capacity: value=0, weight=0, items=[]
Tie, skip later item: value=3, weight=2, items=[0]
Zero-value item: value=5, weight=2, items=[1]
~~~

### Diễn giải kết quả

**By capacity** và **By value** đều cho giá trị 12 từ món 1 và 3. Đó là nghiệm duy nhất đạt giá trị lớn nhất trong bộ mẫu nên cả hai hướng truy vết cùng ra chỉ số [1,3].

**Large capacity** cho 11 với món [0,1], tổng trọng lượng 1000. Đây là ví dụ nên chọn trục tổng giá trị khi V nhỏ hơn W rất nhiều.

**Zero capacity** chỉ chọn được tập rỗng vì mọi món nặng dương.

**Tie, skip later item** có hai món giống nhau nhưng sức chứa chỉ cho phép một món. Khi truy vết, bỏ món cuối nếu hàng trước vẫn cho cùng giá trị, nên chọn [0].

**Zero-value item** không có lý do chọn món nặng 1 mà giá trị 0 trong bảng trọng lượng tối thiểu; chỉ món chỉ số 1 được chọn, đạt giá trị 5 với trọng lượng 2.

### Chi tiết cần chú ý trong code

- Hàm validate từ chối đầu vào null, độ dài không bằng nhau, sức chứa âm, trọng lượng không dương hoặc giá trị âm. Mảng rỗng được phép.
- Bảng capacity khởi tạo toàn 0 **phù hợp với trạng thái không quá c**. Bảng value dùng Arrays.fill(inf) và chỉ đặt M[0][0]=0.
- Hàm byValue **không cộng vào INF**. Nó xét nhánh lấy chỉ khi M[i−1][v−value] khác inf.
- Math.addExact báo lỗi nếu phép cộng long tràn, thay vì âm thầm cho kết quả sai.
- Vòng truy vết byCapacity giảm c khi lấy món, còn byValue giảm remainingValue; cả hai luôn giảm i.
- Các danh sách được đảo về thứ tự chỉ số tăng và trả dưới dạng List.copyOf.
- Trường hợp tổng giá trị quá lớn so với chỉ số int được từ chối. Tuy nhiên ngay cả một bảng có số cột nằm trong int vẫn có thể **không vừa RAM**: mã học thuật này không hứa cấp phát thành công cho mọi kích thước.

## 9. Bất biến và chứng minh truy vết

### Truy vết C

Ở trạng thái (i,c), ta cần dựng một tập trong i món đầu đạt đúng **giá trị tối ưu C[i][c]**, dùng không quá c trọng lượng.

- Nếu C[i][c]=C[i−1][c], bỏ món cuối vẫn đạt cùng giá trị, nên giảm i là an toàn.
- Nếu khác, theo công thức thì nhánh lấy món cuối phải đạt giá trị tối ưu. Ghi món i−1, giảm c đi trọng lượng món và giảm i.
- Với i=0, chỉ còn tập rỗng; các món đã ghi từ lớn tới nhỏ được đảo lại.

Chỉ số món giảm ở mỗi bước, không một món nào được lấy hai lần; tổng trọng lượng không vượt W và tổng giá trị bằng C[n][W].

### Truy vết M

Trước tiên tìm v* lớn nhất có M[n][v*]≤W. Ở trạng thái (i,v), ta cần đạt **đúng v** với trọng lượng nhỏ nhất M[i][v] bằng i món đầu.

- Nếu M[i][v]=M[i−1][v], bỏ món cuối vẫn đạt v với trọng lượng nhỏ nhất.
- Nếu khác, nhánh lấy là phương án tốt nhất. Ghi món cuối, giảm v đi giá trị món đó.
- Khi i=0, v phải bằng 0 vì M[0][v>0]=INF.

Tập cuối có giá trị v*, trọng lượng đúng bằng M[n][v*] và không vượt W. Hướng M còn bảo đảm tập được khôi phục có **trọng lượng nhỏ nhất** trong những tập đạt giá trị v*; hướng C không cam kết thêm tiêu chí trọng lượng khi có nhiều tập tối ưu.

Đây là lý do **hai chương trình có thể in các tập món khác nhau nhưng vẫn cùng đúng** nếu chúng có cùng giá trị tối ưu và đều hợp lệ.

## 10. Kiểm thử độc lập và những trường hợp biên

Một cách kiểm thử hữu ích với n nhỏ là **brute force** qua tất cả \(2^n\) tập con:
1. Tính tổng trọng lượng và giá trị của từng tập.
2. Loại tập có trọng lượng >W.
3. Lấy giá trị lớn nhất của các tập còn lại.
4. Đối chiếu với C[n][W] và giá trị v lớn nhất có M[n][v]≤W.

Ngoài so **giá trị trả về**, hãy kiểm tra danh sách món được truy vết: mỗi chỉ số thuộc [0,n), không lặp, tổng trọng lượng ≤W và tổng giá trị bằng số tối ưu.

Các ca cần thử:
- **n=0**, W=0 và W>0: kết quả 0, danh sách rỗng.
- **W=0** với các món nặng dương: chỉ tập rỗng.
- **Một món vừa hoặc không vừa**: chọn hoặc bỏ chính xác.
- **Món có v=0**: hướng M không phải chọn nó khi trọng lượng dương.
- **Hai món cùng trọng lượng/giá trị**: kết quả tối ưu cho phép nhiều tập, nhưng không lặp một món.
- **W lớn, V nhỏ**: chọn hướng theo tổng giá trị.
- **W nhỏ, V lớn**: chọn hướng theo sức chứa.
- **Giá trị chính xác không đạt được**: M[i][v] phải INF, không bị khởi tạo nhầm bằng 0.
- **Số liệu lớn**: kiểm tra tràn cộng, kích thước cấp phát và tính giả đa thức.
- **Dữ liệu ngẫu nhiên nhỏ**: so cả hai DP với brute force để phát hiện lỗi chuyển trạng thái.

Thời gian brute force tăng theo hàm mũ nên chỉ dùng **kiểm thử và xác minh** khi n nhỏ, không phải thay thế hai thuật toán DP cho bộ dữ liệu lớn.

## 11. Khi cả W và V quá lớn

Việc đổi từ trục sức chứa sang trục giá trị **không** giải quyết mọi đầu vào. Nếu W và V đều rất lớn, có thể cân nhắc:
- **Meet-in-the-middle** khi n tương đối nhỏ: chia các món làm hai nhóm, liệt kê các tập con trong từng nhóm rồi phối hợp.
- **Pareto frontier** của các trạng thái trọng lượng–giá trị không bị trạng thái khác thống trị, nếu dữ liệu thực tế cho phép giảm số trạng thái.
- **FPTAS/xấp xỉ theo giá trị** trong một số phiên bản ba lô 0/1: làm tròn hoặc co tỉ lệ giá trị để giảm V, sau đó dùng value-indexed DP; đổi lại kết quả có sai số được giới hạn theo một chứng minh xấp xỉ. Không được khẳng định nó vẫn là nghiệm **chính xác** sau làm tròn.
- Quy tắc nhánh-cận hoặc khai thác cấu trúc riêng khi bài toán có thêm giới hạn.

Tất cả các lựa chọn này cần được phân tích theo chính n, W, V và yêu cầu chất lượng nghiệm; không có lời hứa rằng một phương pháp luôn tốt nhất.

## 12. Lỗi thường gặp

1. **Nhầm C[i][c] là “dùng đúng c”** dù khởi tạo hàng 0 bằng 0. Trong bài này C cho tổng trọng lượng **không quá c**.
2. **Nhầm M[i][v] là “đạt ít nhất v”.** Công thức đã nêu dành cho **đúng v**.
3. **Khởi tạo mọi ô M bằng 0.** Giá trị dương không thể đạt khi chưa có món phải là INF.
4. **Cộng số vào INF** mà không kiểm tra, làm tràn số và chọn nhánh sai.
5. **Trả M[n][V] như đáp án.** Ô này là trọng lượng tối thiểu để đạt V, không phải giá trị tối ưu với W.
6. **Quên bước quét v lớn nhất** sao cho M[n][v]≤W.
7. **Dùng hàng i thay vì i−1 ở nhánh lấy**, vô tình cho phép dùng một món nhiều lần.
8. **Duyệt tăng khi nén 1D**, tạo ra unbounded knapsack thay vì 0/1.
9. **Dùng max(v_i) làm cận chỉ số M** thay vì \(\sum_i v_i\).
10. **So sánh giá trị mà quên kiểm tra trọng lượng** khi truy vết tập món.
11. **Cho rằng hai hướng phải khôi phục cùng một tập.** Chỉ **giá trị tối ưu** được bảo đảm bằng nhau nếu không có ràng buộc tie.
12. **Nén 1D nhưng vẫn đòi truy vết như có bảng 2D.** Thông tin của các hàng trước đã bị ghi đè.
13. **Không xét W=0, n=0 hoặc v_i=0.** Đây là những ca kiểm tra định nghĩa trạng thái/cơ sở.
14. **Cho phép trọng lượng hoặc giá trị ngoài hợp đồng** mà không sửa truy hồi và miền trạng thái.
15. **Coi O(nW), O(nV) là đa thức theo số bit** của mọi đầu vào.
16. **Không xét giới hạn RAM**, dù số phép tính và kiểu chỉ số trên lý thuyết vẫn hợp lệ.
17. **Dùng phép làm tròn cho value DP rồi tuyên bố kết quả chính xác.** Cần phân tích sai số nếu dùng xấp xỉ.
18. **Không tách tối ưu giá trị và tối ưu trọng lượng phụ.** Hướng C không tự tối ưu tie theo trọng lượng.

## 13. Tự kiểm tra

**Câu 1.** Hai trạng thái C[i][c] và M[i][v] khác nhau ở điểm nào?

**Đáp án:** C lưu **giá trị lớn nhất** với tổng trọng lượng **không quá c**. M lưu **trọng lượng nhỏ nhất** để đạt **đúng giá trị v**, hoặc INF khi không đạt được.

**Câu 2.** Vì sao C[0][5]=0 nhưng M[0][5]=INF?

**Đáp án:** Không có món nào thì giá trị tối ưu dưới sức chứa 5 là 0. Nhưng không thể đạt **đúng giá trị 5** khi chưa có món.

**Câu 3.** Đọc đáp án từ bảng M như thế nào?

**Đáp án:** Tìm v lớn nhất có M[n][v]≤W. Không được trả trọng lượng M[n][V] làm giá trị tối ưu.

**Câu 4.** Khi W=1.000.000 và V=200, bảng nào ít cột hơn?

**Đáp án:** Value-indexed có V+1=201 cột, capacity-indexed có W+1=1.000.001 cột. Nếu các điều kiện khác giống nhau, value-indexed là ứng viên tốt hơn về số trạng thái.

**Câu 5.** Vì sao vòng lặp mảng 1D phải đi từ chỉ số lớn xuống nhỏ trong bài 0/1?

**Đáp án:** Để nhánh lấy đọc **giá trị của trạng thái trước khi xử lý món hiện tại**, tránh sử dụng món ấy nhiều lần.

**Câu 6.** Nếu hai DP cùng trả giá trị 12 nhưng in hai tập món khác nhau thì đã chắc có lỗi chưa?

**Đáp án:** Chưa. Nếu cả hai tập hợp lệ và đều có giá trị 12 tối ưu, chúng có thể khác nhau do tie-break; yêu cầu chỉ một nghiệm tối ưu không buộc cùng tập.

**Câu 7.** Hai hướng có độ phức tạp gì với bảng đầy đủ?

**Đáp án:** Theo sức chứa O(nW) thời gian và O(nW) bộ nhớ; theo giá trị O(nV) thời gian và O(nV) bộ nhớ, với V là tổng giá trị tất cả món. Chúng có thể là giả đa thức.

**Câu 8.** Trường hợp nào nên cân nhắc phương pháp khác thay vì đổi trục?

**Đáp án:** Khi cả W và V đều lớn đến mức số trạng thái không vừa thời gian hoặc RAM, cần xem n và cân nhắc gặp ở giữa, các trạng thái Pareto, xấp xỉ hoặc cấu trúc riêng.

**Ghi nhớ:** Với **0/1 knapsack**, hướng sức chứa lưu **max value dưới ngưỡng c**, hướng tổng giá trị lưu **min weight đạt đúng v**, rồi tìm v lớn nhất không vượt W về trọng lượng. Chọn trục có **miền số học khả thi**, giữ đúng điều kiện cơ sở, không cộng vào INF và **duyệt giảm khi nén DP một chiều**.
