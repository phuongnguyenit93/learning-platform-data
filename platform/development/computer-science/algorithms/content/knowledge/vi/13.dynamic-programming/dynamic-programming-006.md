# Chọn thứ tự tính theo quan hệ phụ thuộc

**Quy hoạch động** (*dynamic programming – DP*) không chỉ là việc viết một công thức truy hồi rồi đưa vào vòng lặp. Mỗi trạng thái thường cần kết quả của **những trạng thái khác**. Nếu tính trạng thái mới trước khi dữ liệu nó phụ thuộc đã sẵn sàng, chương trình có thể đọc giá trị mặc định, dùng nhầm phiên bản cũ/mới của mảng hoặc đưa ra kết quả sai dù công thức truy hồi hoàn toàn đúng.

**Chọn thứ tự tính theo quan hệ phụ thuộc** nghĩa là tìm một thứ tự xử lý sao cho **mọi trạng thái cần thiết cho một trạng thái đều đã được tính trước trạng thái đó**. Có thể hình dung các trạng thái tạo thành một **đồ thị phụ thuộc có hướng**: mỗi cạnh đi từ trạng thái được dùng tới trạng thái sử dụng nó. Nếu đồ thị này không có chu trình, một **thứ tự tô-pô** (*topological order*) cho phép tính bottom-up chính xác.

Bài học đi từ cách nhận diện cạnh phụ thuộc, xác định trạng thái cơ sở, chọn vòng lặp, đến các ví dụ quan trọng: DP một chiều, đường đi trên lưới, ba lô 0/1 với chiều duyệt dung lượng, DP trên DAG, DP theo độ dài đoạn và theo tập con. Điểm nhấn là **sắp thứ tự theo dữ liệu cần dùng, không theo cảm giác về cách đánh chỉ số**.

## 1. Trạng thái, công thức truy hồi và quan hệ phụ thuộc

Một mô hình DP thường gồm:

1. **Trạng thái:** ký hiệu \(dp[s]\), chứa câu trả lời của một bài toán con được xác định bởi \(s\).
2. **Trạng thái cơ sở:** những giá trị biết trực tiếp, không cần các bài toán con chưa giải.
3. **Chuyển trạng thái:** công thức lấy các trạng thái nhỏ hơn hoặc đã có để tính trạng thái mới.
4. **Thứ tự tính:** bảo đảm các giá trị ở vế phải đã đúng trước khi thực hiện phép tính ở vế trái.
5. **Đầu ra:** một hoặc nhiều trạng thái cần đọc sau khi hoàn tất.

Viết tổng quát:

\[
dp[s]=G_s\bigl(dp[p_1],dp[p_2],\ldots,dp[p_t],input\bigr).
\]

Ta gọi \(p_1,\ldots,p_t\) là **tiền nhiệm** (*dependencies*) của \(s\). Nếu có cạnh \(p\to s\), thứ tự tính phải xếp \(p\) **trước** \(s\).

Ví dụ Fibonacci:

\[
F(0)=0,\quad F(1)=1,\quad F(i)=F(i-1)+F(i-2)\quad (i\ge2).
\]

Để tính \(F(5)\), phải tính đúng \(F(3)\) và \(F(4)\); để tính \(F(4)\), cần \(F(2)\) và \(F(3)\). Thứ tự đơn giản là:

~~~text
F[0], F[1], F[2], F[3], F[4], F[5]
~~~

Duyệt \(i\) tăng từ 2 tới n thỏa quan hệ phụ thuộc. Duyệt \(i\) **giảm từ n về 2** với mảng chưa tính không đúng: nhiều trạng thái ở vế phải còn chưa có giá trị.

**Quan hệ phụ thuộc quyết định thứ tự**, không phải tên biến hay việc một trạng thái có “chỉ số lớn hơn”. Với công thức \(dp[i]=dp[i+1]+cost[i]\), các phụ thuộc đi từ chỉ số lớn sang nhỏ, nên **duyệt i giảm** mới phù hợp.

## 2. Đồ thị phụ thuộc và thứ tự tô-pô

Tạo một đỉnh cho mỗi trạng thái DP; thêm cạnh:

\[
u\rightarrow v
\]

khi công thức tính \(dp[v]\) cần \(dp[u]\).

Nếu đồ thị phụ thuộc là **DAG** (*directed acyclic graph – đồ thị có hướng không chu trình*), luôn có ít nhất một thứ tự tô-pô: danh sách các đỉnh sao cho **mọi cạnh \(u\to v\) đều đặt u trước v**.

Ví dụ đồ thị phụ thuộc cho các trạng thái Fibonacci từ F[0] tới F[4]:

~~~text
F[0] -> F[2]
F[1] -> F[2], F[3]
F[2] -> F[3], F[4]
F[3] -> F[4]
~~~

Một thứ tự tô-pô hợp lệ là F[0], F[1], F[2], F[3], F[4]. Trong một đồ thị khác, có thể có nhiều thứ tự hợp lệ; các trạng thái **không phụ thuộc lẫn nhau** có thể đổi chỗ.

Một nguyên tắc kiểm tra rất thực dụng:

> Trước khi viết vòng lặp, hãy hỏi: **Để tính ô này, chính xác những ô nào phải đúng trước?** Sau đó chọn chiều duyệt khiến mọi ô đó có mặt.

Thứ tự tô-pô không nhất thiết phải được tính bằng một thuật toán đồ thị. Đối với DP theo chỉ số, lưới hay khoảng, nó thường được **mã hóa trong thứ tự các vòng for**. Chỉ khi quan hệ phụ thuộc phức tạp hoặc được cung cấp bằng danh sách cạnh thì mới cần dùng thuật toán sắp xếp tô-pô tổng quát.

### Bảng chọn nhanh thứ tự theo công thức

| Quan hệ truy hồi | Trạng thái phải tính trước | Thứ tự thường phù hợp |
|---|---|---|
| \(dp[i]\leftarrow dp[i-1],dp[i-2]\) | Chỉ số nhỏ hơn | i **tăng** |
| \(dp[i]\leftarrow dp[i+1]\) | Chỉ số lớn hơn | i **giảm** |
| \(dp[i][j]\leftarrow dp[i-1][j],dp[i][j-1]\) | Ô phía trên và bên trái | Hàng tăng, cột tăng |
| \(dp[l][r]\leftarrow dp[l][m],dp[m+1][r]\) | Đoạn con ngắn hơn | **Độ dài đoạn tăng** |
| \(dp[mask]\leftarrow dp[mask\setminus\{b\}]\) | Tập con thực sự | Số bit hoặc số nguyên mask tăng, nếu cách đánh chỉ số phù hợp |
| \(dp[v]\leftarrow dp[u]\) với cạnh \(u\to v\) trong DAG | Các đỉnh tiền nhiệm | **Thứ tự tô-pô** |
| DP 0/1 ba lô nén bộ nhớ | Lớp trạng thái của **đồ vật trước** | Duyệt dung lượng **giảm** cho từng đồ vật |

Bảng này là định hướng. Với mỗi bài cụ thể, phải **chứng minh bất biến của thứ tự vòng lặp**, đặc biệt khi cập nhật **tại chỗ** và dùng chung một mảng cho nhiều lớp DP.

## 3. Chọn thứ tự bottom-up: bắt đầu từ cơ sở

Trong **bottom-up DP**, ta tính từ những trạng thái có thể biết trước đến trạng thái cần xuất ra.

Các bước thiết kế:

1. **Định nghĩa dp[s]:** giải thích rõ nó biểu diễn kết quả gì.
2. **Liệt kê các trạng thái phụ thuộc:** đọc công thức và xác định mọi trạng thái ở vế phải.
3. **Đặt cơ sở:** mọi trạng thái không thể suy ra từ trạng thái nhỏ hơn phải được khởi tạo rõ ràng.
4. **Chọn một thứ tự bảo đảm phụ thuộc được tính trước:** có thể là i tăng/giảm, theo tổng chỉ số, theo độ dài, theo số bit hoặc tô-pô.
5. **Chứng minh bằng bất biến vòng lặp:** trước bước tính s, tất cả các dp[p] cần thiết đã đúng.
6. **Đọc kết quả:** sau khi các trạng thái cần thiết đã được xử lý.

Ví dụ tìm tổng lớn nhất theo một chiều:

\[
dp[0]=a[0],\qquad dp[i]=\max(a[i],dp[i-1]+a[i]).
\]

Trạng thái dp[i] chỉ cần dp[i-1], vì thế vòng lặp \(i=1,\ldots,n-1\) hợp lệ. Nếu muốn tiết kiệm bộ nhớ, ta có thể thay dp[i-1] bằng một biến \`previous\` vì ngay sau khi đã chuyển sang i, trạng thái trước đó không cần giữ cho những trạng thái xa hơn ngoài i+1.

Tuy nhiên không phải mọi DP đều dễ nén: nếu công thức phụ thuộc nhiều trạng thái cũ không thể tái tạo, bỏ chúng đi sẽ làm hỏng phép tính tiếp theo.

## 4. Ví dụ lưới: thứ tự hàng và cột

Cho lưới số nguyên \(cost[i][j]\). Từ ô trên-trái (0,0), chỉ được đi **xuống** hoặc **sang phải** để tới ô dưới-phải. Tính tổng chi phí nhỏ nhất, tính cả ô bắt đầu và kết thúc.

Đặt:

\[
dp[i][j]=\text{tổng chi phí nhỏ nhất để đến ô }(i,j).
\]

Trạng thái cơ sở:

\[
dp[0][0]=cost[0][0].
\]

Với các ô không nằm ở hàng/cột đầu tiên:

\[
dp[i][j]=cost[i][j]+\min(dp[i-1][j],dp[i][j-1]).
\]

Ở hàng 0, chỉ có thể đi từ bên trái; ở cột 0, chỉ có thể đi từ phía trên.

**Hai cạnh phụ thuộc đi từ trên và trái tới ô hiện tại.** Một thứ tự hợp lệ là:

~~~text
for i = 0 .. rows-1:
    for j = 0 .. cols-1:
        tính dp[i][j] từ ô trên và ô trái đã được xử lý
~~~

Xét lưới:

~~~text
cost =  1  3  1
        1  5  1
        4  2  1
~~~

Bảng DP đúng sau khi tính là:

| Hàng \ Cột | 0 | 1 | 2 |
|---|---:|---:|---:|
| 0 | 1 | 4 | 5 |
| 1 | 2 | 7 | 6 |
| 2 | 6 | 8 | **7** |

Một đường đi tối ưu là \((0,0)\to(0,1)\to(0,2)\to(1,2)\to(2,2)\), có tổng \(1+3+1+1+1=7\).

Nếu dùng công thức trên nhưng bắt đầu tính ô (2,2) trước ô (1,2) và (2,1), ta sẽ đọc các giá trị chưa được tính đúng. **Trật tự duyệt không đúng dù mỗi phép \`min\` và phép cộng đều hợp lệ.**

### Có thể duyệt cột trước hàng không?

Có, miễn là **cả hàng và cột đều tăng**:

~~~text
for j = 0 .. cols-1:
    for i = 0 .. rows-1:
        tính dp[i][j]
~~~

Khi đó ô trên (i-1,j) đã được xử lý trong cùng cột; ô trái (i,j-1) đã được xử lý trong cột trước. Như vậy cả **hàng-ngoài/cột-trong** và **cột-ngoài/hàng-trong** đều hợp lệ, vì cả hai tạo ra một thứ tự tô-pô của lưới phụ thuộc.

Đây là ví dụ cho thấy **không có một thứ tự duy nhất**. Tiêu chuẩn đúng sai là quan hệ phụ thuộc, không phải thói quen chọn vòng for ngoài.

## 5. Nén bảng lưới: thứ tự còn quyết định phiên bản dữ liệu

Bảng lưới có \(rows\times cols\) trạng thái, nhưng dp[i][j] chỉ dùng:

- dp[i-1][j]: **cùng cột ở hàng trước**;
- dp[i][j-1]: **cột trước ở hàng hiện tại**.

Có thể dùng **một mảng \`dp[j]\`** dài cols:

- **Trước khi cập nhật j** ở hàng i, \`dp[j]\` vẫn là kết quả của **hàng trước** ở cột j.
- **Sau khi cập nhật j-1**, \`dp[j-1]\` đã là kết quả của **hàng hiện tại** ở cột trước.

Vì vậy khi duyệt j **tăng**, ta có:

\[
dp[j]\leftarrow cost[i][j]+\min(
\underbrace{dp[j]}_{\text{hàng trước}},
\underbrace{dp[j-1]}_{\text{hàng hiện tại}}
).
\]

Nếu đảo j sang giảm nhưng vẫn dùng đúng biểu thức trên, \`dp[j-1]\` còn chứa giá trị của **hàng trước**, không phải ô trái của hàng hiện tại. Chương trình sẽ dùng **sai phiên bản trạng thái**.

Nén bộ nhớ không chỉ là thay mảng hai chiều bằng một chiều. Phải ghi rõ **mỗi ô trước và sau cập nhật biểu diễn lớp trạng thái nào**, rồi chọn thứ tự để tránh ghi đè phụ thuộc còn cần dùng.

## 6. Trường hợp dễ sai nhất: ba lô 0/1 và chiều duyệt dung lượng

Cho các đồ vật có trọng lượng \(w_i>0\), giá trị \(v_i\ge0\) và sức chứa C. Mỗi đồ vật có thể được chọn **tối đa một lần**.

Định nghĩa:

\[
F_i(c)=\text{giá trị tối đa với dung lượng }\le c
\text{ khi chỉ xét }i\text{ đồ vật đầu}.
\]

Với đồ vật i có trọng lượng w, giá trị v:

\[
F_i(c)=
\begin{cases}
F_{i-1}(c),&c<w,\\
\max(F_{i-1}(c),F_{i-1}(c-w)+v),&c\ge w.
\end{cases}
\]

**Cả hai trạng thái ở vế phải đều thuộc lớp \(i-1\)**, tức chưa dùng đồ vật hiện tại.

### Nén từ hai chiều xuống một chiều

Ta dùng \`dp[c]\` để lưu lần lượt các lớp đồ vật, nhưng phải duyệt sức chứa **giảm từ C về w**:

~~~text
for mỗi đồ vật (w, v):
    for c = C .. w:
        dp[c] = max(dp[c], dp[c-w] + v)
~~~

Tại thời điểm xử lý dung lượng c:

- \`dp[c]\` trước phép gán là **lớp cũ**, chưa dùng vật hiện tại;
- vì c-w < c và ta đang duyệt **giảm**, \`dp[c-w]\` **chưa bị cập nhật** trong lượt của vật hiện tại;
- do đó \`dp[c-w]+v\` lấy vật hiện tại **đúng một lần**.

Nếu duyệt dung lượng **tăng** từ w tới C, \`dp[c-w]\` có thể vừa được cập nhật bằng **chính đồ vật đang xét**. Khi cộng thêm v, một vật có thể bị chọn nhiều lần – sai với bài toán 0/1.

### Ví dụ phát hiện lỗi

Đồ vật:

| Vật | Trọng lượng | Giá trị |
|---|---:|---:|
| A | 2 | 4 |
| B | 3 | 5 |
| C | 4 | 7 |

Dung lượng **C=6**.

- **0/1 knapsack:** chọn A+C, tổng trọng lượng 6, giá trị **11**. Không thể chọn ba bản sao A.
- **Unbounded knapsack:** cho phép dùng không giới hạn số bản sao mỗi loại; chọn A ba lần, trọng lượng 6, giá trị **12**.

Hai bài toán có **mô hình phụ thuộc khác nhau** dù biểu thức cập nhật \`max(dp[c],dp[c-w]+v)\` trông giống hệt nhau.

Với **unbounded knapsack**, lớp hiện tại **được phép** dùng tiếp vật i, nên duyệt c **tăng** là đúng:

~~~text
for mỗi loại đồ vật (w, v):
    for c = w .. C:
        dp[c] = max(dp[c], dp[c-w] + v)
~~~

Lần này \`dp[c-w]\` **có thể đã được cập nhật ở lớp hiện tại**, chính là điều cần thiết để cho phép chọn nhiều bản sao.

**Quy tắc cần nhớ:** với cập nhật 1D từ \`c-w\` sang \`c\`, **0/1 → duyệt c giảm** để không dùng vật hai lần; **unbounded → duyệt c tăng** để cho phép dùng nhiều lần. Đây là hệ quả của **quan hệ phụ thuộc giữa các lớp trạng thái**, không phải mẹo cần học thuộc mà không hiểu.

## 7. Top-down với memoization tự tìm thứ tự khi cần

Trong **top-down DP có ghi nhớ** (*memoization*), ta không chọn trước một vòng for tổng thể. Thay vào đó, khi cần giá trị \`solve(s)\`:

1. Nếu s là cơ sở, trả giá trị cơ sở.
2. Nếu s đã có trong cache, trả ngay.
3. Gọi đệ quy \`solve(p)\` cho mọi trạng thái tiền nhiệm p.
4. Khi mọi lời gọi tiền nhiệm đã trả lời, tính \`dp[s]\`, lưu cache rồi trả về.

Điều này tạo thứ tự tính theo kiểu **duyệt sâu và tính khi quay lui** (*DFS postorder*). Nó vẫn tôn trọng cùng quan hệ phụ thuộc: mọi trạng thái p phải được tính **trước** khi hoàn tất s.

Memoization hữu ích nếu:

- Chỉ một phần nhỏ của không gian trạng thái có thể đi đến từ đáp án cần tính.
- Quan hệ phụ thuộc phức tạp, khó viết sẵn thứ tự vòng lặp.
- Cài đặt đệ quy tự nhiên hơn so với dựng danh sách tất cả trạng thái.

Nhưng cần lưu ý:

- Nếu bỏ cache, cùng một bài toán con có thể bị tính lặp nhiều lần.
- Đệ quy sâu có thể gây **StackOverflowError** trong Java, kể cả khi số trạng thái chỉ tuyến tính.
- Nếu có **chu trình thực sự** trong quan hệ phụ thuộc mà không có cơ chế đặc biệt, lời gọi đệ quy có thể quay vòng mãi. Có thể đánh dấu trạng thái **UNVISITED/VISITING/DONE** để phát hiện chu trình.
- Memoization **không biến mọi công thức truy hồi có chu trình thành DP hợp lệ**; có thể cần đổi trạng thái, dùng bước thời gian hoặc giải phương trình/thuật toán đồ thị khác.

Bottom-up và top-down không phải hai lý thuyết độc lập. Chúng là hai cách **lập lịch tính toán các trạng thái với cùng những cạnh phụ thuộc**.

## 8. DP trên DAG: cần thứ tự tô-pô tổng quát

Không phải quan hệ phụ thuộc nào cũng đi theo chỉ số 1D hoặc một lưới. Giả sử có đồ thị có hướng **không chu trình**, mỗi đỉnh là một trạng thái, mỗi cạnh \(u\to v\) cho phép chuyển kết quả từ u sang v.

Ví dụ **đếm số đường đi từ đỉnh nguồn 0 tới mỗi đỉnh** trên DAG:

\[
ways[0]=1,\qquad
ways[v]=\sum_{u\to v} ways[u]
\quad (v\ne0),
\]

với cách hiểu số đường đi độ dài 0 từ nguồn tới chính nó là 1. Công thức yêu cầu **mọi tiền nhiệm u được tính trước v**.

Đồ thị mẫu:

~~~text
0 -> 1
0 -> 2
1 -> 3
2 -> 3
1 -> 4
3 -> 4
~~~

Có ba đường đi từ 0 tới 4:

~~~text
0 -> 1 -> 4
0 -> 1 -> 3 -> 4
0 -> 2 -> 3 -> 4
~~~

Một thứ tự tô-pô hợp lệ là **0,1,2,3,4**; một thứ tự khác có thể đổi chỗ 1 và 2 nếu không có cạnh phụ thuộc trực tiếp giữa chúng.

### Thuật toán Kahn tạo thứ tự

1. Đếm **indegree[v]**: số cạnh đi vào v.
2. Đưa tất cả đỉnh indegree=0 vào hàng đợi.
3. Lấy một đỉnh u khỏi hàng đợi; vì mọi tiền nhiệm đã xử lý, **trạng thái ở u đã hoàn tất**.
4. Chuyển thông tin từ u đến từng v kề (\`ways[v] += ways[u]\`), sau đó giảm indegree[v].
5. Khi indegree[v] trở thành 0, mọi tiền nhiệm của v đã được xử lý, nên có thể đưa v vào hàng đợi.
6. Nếu xử lý **ít hơn số đỉnh** thì còn chu trình, không có thứ tự tô-pô cho toàn bộ đồ thị.

Trong cách triển khai **đẩy kết quả xuôi theo cạnh**, \`ways[v]\` có thể được **cộng dần** từ nhiều tiền nhiệm, nhưng **chỉ được coi là hoàn tất khi mọi cạnh đi vào v đã được xử lý**. Không nên đưa v ra làm nguồn chuyển tiếp khi vẫn còn tiền nhiệm chưa đóng góp.

Phần này khái quát các vòng for từ những ví dụ trước: thay vì dựa vào thứ tự số học của chỉ số, Kahn dựa trực tiếp vào **số lượng phụ thuộc chưa hoàn thành**.

## 9. Java 17+: ba nhóm phụ thuộc trong một chương trình chạy được

Ví dụ dưới đây gồm ba dạng thứ tự:

- **Đường đi tối thiểu trên lưới:** duyệt ô trên/trái trước, đối chiếu bảng 2D với mảng 1D cập nhật trái sang phải.
- **Ba lô 0/1 và unbounded:** cùng dữ liệu nhưng duyệt dung lượng giảm/tăng tương ứng.
- **Đếm đường đi trên DAG:** dùng thứ tự tô-pô tạo bằng Kahn.

Lưu dưới tên **DpDependencyOrderDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DpDependencyOrderDemo {
    static void validateGrid(int[][] cost) {
        Objects.requireNonNull(cost, "cost");
        if (cost.length == 0 || cost[0] == null
                || cost[0].length == 0) {
            throw new IllegalArgumentException("nonempty grid required");
        }
        int cols = cost[0].length;
        for (int[] line : cost) {
            if (line == null || line.length != cols) {
                throw new IllegalArgumentException("grid must be rectangular");
            }
        }
    }

    static long minPath2D(int[][] cost) {
        validateGrid(cost);
        int rows = cost.length;
        int cols = cost[0].length;
        long[][] dp = new long[rows][cols];

        for (int i = 0; i < rows; i++) {
            for (int j = 0; j < cols; j++) {
                if (i == 0 && j == 0) {
                    dp[i][j] = cost[i][j];
                } else if (i == 0) {
                    dp[i][j] = dp[i][j - 1] + cost[i][j];
                } else if (j == 0) {
                    dp[i][j] = dp[i - 1][j] + cost[i][j];
                } else {
                    dp[i][j] = Math.min(dp[i - 1][j],
                                        dp[i][j - 1]) + cost[i][j];
                }
            }
        }
        return dp[rows - 1][cols - 1];
    }

    static long minPathRolling(int[][] cost) {
        validateGrid(cost);
        int cols = cost[0].length;
        long[] dp = new long[cols];

        for (int i = 0; i < cost.length; i++) {
            for (int j = 0; j < cols; j++) {
                if (i == 0 && j == 0) {
                    dp[j] = cost[i][j];
                } else if (i == 0) {
                    dp[j] = dp[j - 1] + cost[i][j];
                } else if (j == 0) {
                    dp[j] = dp[j] + cost[i][j];
                } else {
                    // dp[j] = previous row; dp[j-1] = current row.
                    dp[j] = Math.min(dp[j], dp[j - 1]) + cost[i][j];
                }
            }
        }
        return dp[cols - 1];
    }

    static void validateItems(int[] weight, int[] value, int capacity) {
        Objects.requireNonNull(weight, "weight");
        Objects.requireNonNull(value, "value");
        if (weight.length != value.length || capacity < 0) {
            throw new IllegalArgumentException("invalid item arrays/capacity");
        }
        for (int i = 0; i < weight.length; i++) {
            if (weight[i] <= 0 || value[i] < 0) {
                throw new IllegalArgumentException(
                    "weights must be positive; values nonnegative"
                );
            }
        }
    }

    static long knapsack01(int[] weight, int[] value, int capacity) {
        validateItems(weight, value, capacity);
        long[] dp = new long[capacity + 1];

        for (int item = 0; item < weight.length; item++) {
            int w = weight[item];
            int v = value[item];
            // Descending: dp[c-w] still belongs to the PREVIOUS layer.
            for (int c = capacity; c >= w; c--) {
                dp[c] = Math.max(dp[c], dp[c - w] + v);
            }
        }
        return dp[capacity];
    }

    static long knapsackUnbounded(
        int[] weight, int[] value, int capacity
    ) {
        validateItems(weight, value, capacity);
        long[] dp = new long[capacity + 1];

        for (int item = 0; item < weight.length; item++) {
            int w = weight[item];
            int v = value[item];
            // Ascending: dp[c-w] may belong to the CURRENT layer.
            for (int c = w; c <= capacity; c++) {
                dp[c] = Math.max(dp[c], dp[c - w] + v);
            }
        }
        return dp[capacity];
    }

    static long countDagPaths(
        int vertices, int[][] edges, int source, int target
    ) {
        Objects.requireNonNull(edges, "edges");
        if (vertices <= 0 || source < 0 || source >= vertices
                || target < 0 || target >= vertices) {
            throw new IllegalArgumentException("invalid graph or endpoints");
        }

        List<List<Integer>> next = new ArrayList<>();
        for (int v = 0; v < vertices; v++) {
            next.add(new ArrayList<>());
        }
        int[] indegree = new int[vertices];
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2 ||
                    edge[0] < 0 || edge[0] >= vertices ||
                    edge[1] < 0 || edge[1] >= vertices) {
                throw new IllegalArgumentException("invalid directed edge");
            }
            next.get(edge[0]).add(edge[1]);
            indegree[edge[1]]++;
        }

        ArrayDeque<Integer> ready = new ArrayDeque<>();
        for (int v = 0; v < vertices; v++) {
            if (indegree[v] == 0) {
                ready.addLast(v);
            }
        }

        long[] ways = new long[vertices];
        ways[source] = 1;
        int processed = 0;

        while (!ready.isEmpty()) {
            int u = ready.removeFirst();
            processed++;

            for (int v : next.get(u)) {
                ways[v] += ways[u];
                if (--indegree[v] == 0) {
                    ready.addLast(v);
                }
            }
        }

        if (processed != vertices) {
            throw new IllegalArgumentException("dependency graph has a cycle");
        }
        return ways[target];
    }

    public static void main(String[] args) {
        int[][] grid = {
            {1, 3, 1},
            {1, 5, 1},
            {4, 2, 1}
        };
        System.out.println("Grid 2D: " + minPath2D(grid));
        System.out.println("Grid rolling: " + minPathRolling(grid));

        int[] weights = {2, 3, 4};
        int[] values = {4, 5, 7};
        System.out.println("0/1 knapsack: "
            + knapsack01(weights, values, 6));
        System.out.println("Unbounded knapsack: "
            + knapsackUnbounded(weights, values, 6));

        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3},
            {2, 3}, {1, 4}, {3, 4}
        };
        System.out.println("DAG paths 0 -> 4: "
            + countDagPaths(5, edges, 0, 4));
        System.out.println("Empty knapsack capacity: "
            + knapsack01(new int[0], new int[0], 0));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac DpDependencyOrderDemo.java
java DpDependencyOrderDemo
~~~

**Stdout chính xác:**

~~~text
Grid 2D: 7
Grid rolling: 7
0/1 knapsack: 11
Unbounded knapsack: 12
DAG paths 0 -> 4: 3
Empty knapsack capacity: 0
~~~

### Vì sao mã tuân theo các quan hệ phụ thuộc?

**Lưới 2D:** \`minPath2D\` duyệt i tăng và j tăng. Khi tính \`dp[i][j]\`, ô phía trên và bên trái đã hoàn tất. Hai biên i=0 hoặc j=0 được xử lý riêng để không truy cập chỉ số âm.

**Lưới 1D:** \`minPathRolling\` duyệt j tăng. Trước cập nhật \`dp[j]\` là giá trị ô ngay trên, còn \`dp[j-1]\` đã là giá trị ô bên trái ở hàng hiện tại. Đảo chiều j mà không đổi phép chuyển sẽ làm mất điều kiện đúng.

**Ba lô 0/1:** \`knapsack01\` duyệt c giảm, để \`dp[c-w]\` là giá trị của **lớp đồ vật trước**; mỗi đồ vật chỉ được tính một lần.

**Ba lô vô hạn:** \`knapsackUnbounded\` duyệt c tăng, để \`dp[c-w]\` có thể phản ánh việc đã dùng vật hiện tại và tiếp tục dùng nó lần nữa.

**DAG:** \`countDagPaths\` dùng hàng đợi các đỉnh có indegree bằng 0. Mỗi đỉnh chỉ phát đóng góp sang đỉnh sau khi tất cả cạnh dẫn vào nó đã được xử lý. Nếu xử lý được ít hơn V đỉnh, tồn tại chu trình; hàm từ chối dữ liệu vì không có thứ tự tô-pô cho toàn bộ đồ thị.

**Chi phí số học:** mã dùng \`long\` cho tổng đường đi lưới, giá trị knapsack và số đường đi DAG nhằm tăng miền giá trị so với int. Với DAG có cực nhiều đường đi, **long vẫn có thể tràn**; khi đó cần \`BigInteger\` hoặc phép tính theo modulo nếu đặc tả cho phép. Với capacity = Integer.MAX_VALUE, phép \`capacity+1\` để cấp mảng cũng có thể vượt int hoặc vượt RAM; chương trình này dành cho dung lượng thực tế có thể cấp phát.

## 10. DP theo đoạn: duyệt độ dài tăng

Một dạng phụ thuộc không thể giải bằng cách luôn tăng một chỉ số riêng lẻ là **DP theo đoạn** (*interval DP*).

Giả sử \(dp[l][r]\) biểu thị chi phí tối ưu cho đoạn liên tiếp từ l tới r, và có chuyển trạng thái:

\[
dp[l][r]=\min_{l\le m<r}
\bigl(dp[l][m]+dp[m+1][r]+cost(l,r,m)\bigr).
\]

Các trạng thái \(dp[l][m]\) và \(dp[m+1][r]\) đều có **độ dài ngắn hơn** đoạn [l,r]. Do đó cần tính theo:

~~~text
for length = 1 .. n:
    for l = 0 .. n-length:
        r = l + length - 1

        if length == 1:
            dp[l][r] = giá trị cơ sở
        else:
            tính dp[l][r] từ những đoạn con ngắn hơn
~~~

Nếu chỉ duyệt l tăng rồi r tăng, các đoạn con như \([m+1,r]\) có l lớn hơn chưa chắc đã được tính; sai phụ thuộc có thể xuất hiện. **Độ dài đoạn** là thước đo giảm theo các cạnh truy hồi, nên tính độ dài tăng sẽ tạo thứ tự tô-pô.

Những bài toán thường dùng mẫu này gồm: chi phí ghép đoạn, nhân chuỗi ma trận (*matrix-chain multiplication*), và một số bài toán phân tích chuỗi. Mỗi bài phải đặt cơ sở và công thức \`cost(l,r,m)\` theo đặc tả riêng; vòng lặp trên chỉ minh họa **thứ tự phụ thuộc**, chưa phải một chương trình hoàn chỉnh cho mọi bài toán DP đoạn.

## 11. DP theo tập con: xét tập nhỏ trước tập lớn

Nếu trạng thái được mã hóa bằng **bitmask** \`mask\`, và để tính một tập S ta cần các tập **bỏ đi một phần tử**, quan hệ phụ thuộc có dạng:

\[
dp[S]\leftarrow dp[S\setminus\{x\}].
\]

Vì tập con thực sự có **ít phần tử hơn**, có thể chọn thứ tự:

- Số bit được bật (*popcount*) tăng dần; hoặc
- \`mask\` tăng dần từ 0 đến \(2^n-1\) khi mọi phụ thuộc chỉ bỏ bit, vì xóa một bit đang bật làm giá trị số nguyên của mask nhỏ đi.

Ví dụ đếm số cách sắp xếp một số phần tử với điều kiện phụ thuộc theo tập đã chọn, trạng thái mask có thể nhận đóng góp từ \`maskWithoutX\` trước đó. Phải kiểm tra rằng **mỗi cạnh thực sự bỏ bit**; nếu công thức còn phụ thuộc vào tập lớn hơn hoặc trạng thái cùng số bit, thứ tự này không tự động hợp lệ.

Cách biểu diễn bitmask hữu ích khi n tương đối nhỏ, vì số trạng thái là \(2^n\) và có thể có thêm hệ số n cho số chuyển trạng thái. Đây là một ví dụ rằng “thứ tự tô-pô đúng” **không làm biến mất độ phức tạp lớn của chính số trạng thái**.

## 12. Khi quan hệ phụ thuộc có chu trình

Một đồ thị phụ thuộc có các cạnh:

~~~text
A -> B
B -> C
C -> A
~~~

không có thứ tự tô-pô: nếu A phải xong trước B, B trước C và C trước A, không thể thỏa đồng thời cả ba.

Với một công thức DP tự phụ thuộc trực tiếp hoặc qua chu trình, **không thể chỉ đảo vòng for để giải quyết**. Cần xem xét mô hình:

1. **Định nghĩa trạng thái có sai không?** Có thể trạng thái đang phụ thuộc chính nó vì đã bỏ sót biến thời gian, số bước hoặc số phần tử đã xử lý.
2. **Có thể tách lớp theo thời gian/bước không?** Ví dụ \`dp[t][v]\` phụ thuộc \`dp[t-1][u]\`: dù đồ thị trạng thái v có chu trình, đồ thị **các trạng thái kèm t** không có cạnh đi ngược thời gian nếu t tăng.
3. **Có đang giải bài toán đồ thị tổng quát?** Bài toán đường đi ngắn nhất trên đồ thị có chu trình có thể cần Dijkstra, Bellman–Ford hoặc kỹ thuật phù hợp, tùy trọng số, chứ không phải luôn một lượt DP tô-pô.
4. **Có cần tìm điểm cố định của hệ phương trình không?** Những bài toán này đòi hỏi điều kiện hội tụ hoặc phương pháp riêng.

Một điều tinh tế: **đồ thị đầu vào có chu trình không đồng nghĩa mọi DP xây trên đó có chu trình**. Quan trọng là các cạnh giữa **trạng thái DP thực sự**. Nếu thêm biến bước t, cạnh phụ thuộc có thể luôn đi từ t-1 tới t, tạo DAG dù cạnh của đồ thị gốc tạo vòng.

## 13. Độ phức tạp: thứ tự đúng không thay thế việc đếm trạng thái

Với \(S\) trạng thái có thể tính và \(T\) lượt chuyển trạng thái cần xét, một DP bottom-up thông thường có chi phí gần:

\[
O(S+T)
\]

nếu mỗi lượt chuyển dùng O(1) công việc và chi phí truy cập/khởi tạo được tính vào mô hình. Với quan hệ phụ thuộc lưu bằng DAG tường minh, sắp tô-pô bằng Kahn cũng mất **\(O(V+E)\)** thời gian và bộ nhớ \(O(V+E)\) cho danh sách kề/indegree nếu tự dựng từ dữ liệu cạnh.

| Bài toán | Thứ tự hợp lệ | Thời gian | Bộ nhớ DP |
|---|---|---:|---:|
| Fibonacci đến n | i tăng | O(n) | O(n), hoặc O(1) nếu chỉ giữ hai trạng thái |
| Tổng đường đi nhỏ nhất lưới r×c | i/j đều tăng | O(rc) | O(rc), hoặc O(c) với rolling row |
| Ba lô 0/1 n đồ vật, dung lượng C | Đồ vật tăng; c giảm khi nén | O(nC) | O(C) với mảng 1D |
| Ba lô vô hạn | Loại vật tăng; c tăng khi nén | O(nC) | O(C) |
| Đếm đường đi trên DAG | Thứ tự tô-pô | O(V+E) | O(V+E) nếu tính cả danh sách kề |
| DP đoạn với mọi điểm chia | Độ dài đoạn tăng | Thường O(n³) | O(n²) |
| DP tập con với tối đa n lựa chọn chuyển | Theo số bit/mask phù hợp | Có thể O(n2^n) | O(2^n) |

**O(nC)** trong knapsack là **giả đa thức** (*pseudo-polynomial*) theo giá trị số C: nếu C được mã hóa trong số bit \(\log C\), thời gian không nhất thiết là đa thức theo độ dài biểu diễn đầu vào.

Nếu dùng memoization, thời gian phụ thuộc **số trạng thái thật sự được thăm** và tổng chuyển trạng thái của chúng, nhưng cần thêm bộ nhớ cache và độ sâu đệ quy. Nếu bottom-up phải tính nhiều trạng thái không cần cho câu trả lời, top-down đôi khi tiết kiệm công việc. Nếu top-down gặp đệ quy quá sâu, bottom-up tô-pô thường dễ kiểm soát stack hơn.

Khi **nén bộ nhớ**, cận không gian nhỏ hơn không bảo đảm code đúng: phải chứng minh các dữ liệu bị ghi đè **không còn cần cho phần tiếp theo của cùng lớp DP**.

## 14. Quy trình chọn thứ tự khi gặp bài toán mới

Một cách làm thực hành có thể dùng trước khi gõ code:

1. **Viết rõ ý nghĩa dp[s].** Tránh đặt \`dp[i]\` rồi bỏ qua câu hỏi “kết quả này thuộc những phần tử/đồ vật/thời điểm nào?”.
2. **Viết công thức chuyển và cơ sở.** Liệt kê mọi đối số \`dp[p]\` ở vế phải.
3. **Vẽ vài cạnh phụ thuộc đại diện.** Ví dụ \((i-1,j)\to(i,j)\), \((i,j-1)\to(i,j)\).
4. **Tìm một đại lượng luôn tăng dọc theo cạnh.** Có thể là chỉ số i, tổng i+j, độ dài đoạn, số bit, số đồ vật đã xét hoặc thời gian t.
5. **Chọn vòng lặp hoặc sắp tô-pô.** Bảo đảm đại lượng/quan hệ đó được tôn trọng cho tất cả cạnh.
6. **Nếu nén trạng thái, ghi rõ lớp cũ và lớp mới.** Kiểm tra một phép cập nhật có đọc giá trị đã bị thay trong cùng lượt hay chưa.
7. **Chứng minh tiến triển và kết quả.** Sau mỗi bước, những trạng thái đã đánh dấu hoàn tất phải có giá trị đúng.
8. **Thử một phản ví dụ nhỏ.** Với knapsack 0/1, một đồ vật (w=2,v=4), C=4: duyệt c tăng sai có thể cho giá trị 8; đáp án 0/1 đúng chỉ là 4.
9. **Kiểm tra biên.** Mảng rỗng, một trạng thái, dung lượng 0, lưới 1×1, đỉnh không tới được, nhiều tiền nhiệm cùng một đỉnh và đồ thị có chu trình.
10. **Đếm trạng thái, chuyển trạng thái và bộ nhớ.** Chọn cách tính phù hợp với giới hạn thời gian/RAM của đầu vào.

### Bất biến vòng lặp mẫu

Với thứ tự tô-pô \(s_1,\ldots,s_m\), có thể dùng phát biểu:

> Trước khi xử lý trạng thái \(s_k\), mọi trạng thái \(s_1,\ldots,s_{k-1}\) đã có giá trị đúng. Vì mọi phụ thuộc trực tiếp của \(s_k\) nằm trong tập trạng thái đã xử lý hoặc là dữ liệu cơ sở, công thức truy hồi tính được giá trị đúng cho \(s_k\).

Chứng minh theo quy nạp trên k cho ta tính đúng của toàn bộ DP. Với cập nhật in-place, bất biến phải bổ sung rõ **những giá trị chưa bị ghi đè thuộc lớp nào**; chỉ biết thứ tự các chỉ số là chưa đủ.

## 15. Những lỗi thường gặp

1. **Có công thức đúng nhưng duyệt sai chiều**: ví dụ Fibonacci tính giảm và đọc trạng thái chưa có.
2. **Lấy thứ tự vòng lặp từ thói quen** thay vì vẽ quan hệ phụ thuộc.
3. **Không khởi tạo trạng thái cơ sở**, khiến giá trị 0 mặc định của Java bị hiểu nhầm là một đáp án hợp lệ.
4. **Dùng 0 để đại diện cho không thể tới**, dù 0 cũng có thể là chi phí hoặc số cách hợp lệ; cần sentinel, boolean hoặc cấu trúc biểu diễn trạng thái rõ ràng.
5. **Thay đổi chiều duyệt khi nén DP** mà không kiểm tra sự khác biệt giữa lớp cũ và lớp hiện tại.
6. **Duyệt c tăng trong knapsack 0/1**, vô tình cho phép dùng một đồ vật nhiều lần.
7. **Duyệt c giảm trong unbounded knapsack**, cấm dùng lại vật trong cùng lượt và làm sai bài toán.
8. **Tính DP đoạn theo thứ tự chỉ số không tôn trọng độ dài**, làm đọc đoạn con chưa có.
9. **Nhầm thứ tự tô-pô với thứ tự số hiệu đỉnh** trên DAG: số hiệu đỉnh không bảo đảm phản ánh hướng cạnh.
10. **Trong Kahn, phát kết quả từ một đỉnh quá sớm** khi vẫn còn tiền nhiệm chưa đóng góp.
11. **Giả định đồ thị luôn không có chu trình** và không kiểm tra số đỉnh xử lý.
12. **Lặp đệ quy không có cache**, tính lại cùng trạng thái nhiều lần.
13. **Dùng memoization không phát hiện chu trình** khi công thức tự phụ thuộc.
14. **Sao chép mảng nén bộ nhớ mà không xác định phiên bản dữ liệu**, dễ dùng nhầm giá trị cùng lớp.
15. **Không tách tính đúng khỏi tối ưu thời gian**: một thứ tự đúng vẫn có thể tính quá nhiều trạng thái không cần thiết hoặc thực hiện chuyển trạng thái đắt.
16. **Quên lỗi tràn số/chi phí cấp phát**: số đường đi có thể vượt long, DP theo capacity C quá lớn không đủ bộ nhớ.
17. **Kết luận một đồ thị đầu vào có chu trình thì mọi cách làm DP đều vô hiệu**: cần xem đúng đồ thị phụ thuộc của trạng thái, có thể kèm bước thời gian.

## 16. Tự luyện tập

**Bài 1 — Chọn chiều i.** Nếu \`dp[i] = dp[i+2] + a[i]\` và đã biết cơ sở \`dp[n]\`, \`dp[n+1]\`, nên duyệt i theo chiều nào?

*Đáp án:* Duyệt **giảm** từ n-1 về 0. Hai trạng thái dp[i+2] và (nếu có chuyển khác) dp[i+1] đều có chỉ số lớn hơn nên phải được tính trước.

**Bài 2 — Lưới nén bộ nhớ.** Trong mã tính tổng đường đi nhỏ nhất bằng mảng một chiều, trước khi cập nhật \`dp[j]\` ở hàng i, \`dp[j]\` và \`dp[j-1]\` có ý nghĩa gì khi j tăng?

*Đáp án:* \`dp[j]\` là chi phí từ **hàng trước** ở cột j; \`dp[j-1]\` đã được cập nhật thành chi phí ở **hàng hiện tại** tại cột j-1.

**Bài 3 — Ba lô 0/1.** Có đúng một đồ vật nặng 2 và giá trị 4, C=4. Nếu duyệt c tăng cho công thức \`dp[c]=max(dp[c],dp[c-2]+4)\`, kết quả sai có thể là bao nhiêu?

*Đáp án:* **8** vì c=2 cập nhật dp[2]=4 trước khi c=4 sử dụng dp[2] và cộng thêm 4. Đúng theo quy tắc 0/1 phải là **4**; duyệt c giảm ngăn sử dụng vật hiện tại lần thứ hai.

**Bài 4 — DP theo đoạn.** Nếu trạng thái [l,r] cần các đoạn con [l,m] và [m+1,r] với l<=m<r, vì sao duyệt độ dài tăng hợp lệ?

*Đáp án:* Mọi đoạn con ở vế phải đều **ngắn hơn** [l,r], nên đã được tính khi xử lý các độ dài nhỏ hơn trước đó.

**Bài 5 — DAG.** Đồ thị có cạnh 0→2, 1→2, 2→3. Có thể tính dp[2] sau dp[0] nhưng trước dp[1] không, nếu công thức dp[2] cần cả hai?

*Đáp án:* **Không.** dp[2] chỉ hoàn tất sau **cả dp[0] và dp[1]**. Một thứ tự hợp lệ là 0,1,2,3 hoặc 1,0,2,3.

**Bài 6 — Chu trình.** Nếu dp[A] cần dp[B] và dp[B] cần dp[A], chỉ đảo thứ tự A/B có giải quyết được không?

*Đáp án:* **Không.** Quan hệ phụ thuộc có chu trình; cần thay đổi mô hình, thêm lớp/bước, hoặc dùng một thuật toán chuyên biệt khác.

**Bài 7 — Đếm đường đi.** Với DAG gồm 0→1, 0→2, 1→3, 2→3, 1→4, 3→4, có bao nhiêu đường đi từ 0 tới 4?

*Đáp án:* **3**, ứng với 0-1-4, 0-1-3-4 và 0-2-3-4. Đỉnh 4 chỉ được hoàn tất sau khi nhận đóng góp từ cả đỉnh 1 lẫn đỉnh 3.

**Tổng kết:** DP đúng cần cả **định nghĩa trạng thái**, **chuyển trạng thái** và **lịch tính hợp lệ theo phụ thuộc**. Hãy coi mỗi trạng thái là đỉnh, mỗi quan hệ “cần kết quả trước” là cạnh và chọn một thứ tự tô-pô. Với bảng nhiều chiều, thứ tự có thể hiện ra qua các vòng for; với mảng nén, phải theo dõi **phiên bản lớp cũ/lớp mới**; với DAG tổng quát, có thể dùng Kahn hoặc DFS postorder. **Chỉ tính một trạng thái sau khi toàn bộ dữ liệu nó cần đã đúng** là nguyên tắc xuyên suốt mọi dạng quy hoạch động.