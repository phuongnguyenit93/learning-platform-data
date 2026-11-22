# Lập bảng theo hướng từ dưới lên

**Lập bảng theo hướng từ dưới lên (bottom-up tabulation)** là phương pháp triển khai **quy hoạch động (dynamic programming, DP)**: xác định các bài toán con, khởi tạo những trường hợp cơ sở, sau đó tính các trạng thái phức tạp theo một thứ tự bảo đảm rằng **mọi giá trị cần dùng đã được tính đúng**. Thay vì gọi đệ quy rồi ghi nhớ kết quả, bottom-up thường sử dụng vòng lặp để điền một bảng hoặc một số lớp trạng thái.

Chất lượng lời giải không nằm ở việc đặt tên mảng `dp` mà ở **ý nghĩa của trạng thái**, **công thức chuyển**, **trường hợp cơ sở**, **hướng điền bảng**, **cách lấy/truy vết đáp án** và **giới hạn tài nguyên**. Đặc biệt, việc nén mảng hai chiều thành một chiều có thể vô tình làm thay đổi bài toán nếu vòng lặp đọc những ô đã bị ghi đè.

Bài học giới thiệu nguyên tắc tổng quát, chứng minh tính đúng bằng quy nạp, các mẫu thứ tự thường gặp, so sánh với ghi nhớ đệ quy (*top-down memoization*) và các ví dụ Fibonacci, đường đi trên lưới, 0/1 knapsack, dãy con chung dài nhất (LCS), đổi tiền ít đồng. Phần Java 17+ hoàn chỉnh minh họa đúng công thức, biên và kết quả đầu ra.

**Mục tiêu:** tự lập bảng từ công thức truy hồi, xác định thứ tự hợp lệ theo đồ thị phụ thuộc, tính đúng độ phức tạp số trạng thái × chi phí chuyển, biết khi nào có thể nén bộ nhớ, truy vết nghiệm và kiểm tra bằng lời giải vét cạn.

## 1. Bản chất của DP và bảng trạng thái

Một bài toán thích hợp với DP thường có các **bài toán con chồng lặp** và một cách kết hợp lời giải bài toán con để cho lời giải lớn hơn. Mỗi bài toán con được mô tả bằng một **trạng thái**. Khi đã có giá trị của trạng thái, ta lưu nó để không tính lại.

Ví dụ Fibonacci:

`F(0)=0, F(1)=1` và `F(i)=F(i−1)+F(i−2)` với `i≥2`.

Tính F(6) bằng đệ quy thuần tạo nhiều lần tính lại F(3), F(2). Bottom-up định nghĩa `dp[i]=F(i)` và lần lượt điền:

| `i` | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dp[i]` | 0 | 1 | 1 | 2 | 3 | 5 | 8 |

Mỗi ô được tính sau hai ô có chỉ số nhỏ hơn, vì vậy không có lời gọi lặp lại. Nhưng mảng chỉ là **cách lưu trạng thái**: nếu chỉ cần F(n), có thể giữ hai giá trị gần nhất mà không lưu cả bảng.

### Sáu thành phần phải xác định

1. **Định nghĩa trạng thái:** mỗi `dp[i]` hoặc `dp[i][j]` là đáp án của bài toán con nào? Ví dụ “`dp[i][c]` là giá trị lớn nhất khi chỉ dùng i món đầu, sức chứa không vượt c”.
2. **Miền trạng thái:** chỉ số nào hợp lệ; có cần cả hàng 0, cột 0 hoặc trạng thái rỗng không?
3. **Cơ sở:** những giá trị đã biết ngay, ví dụ `dp[0]=0` của Fibonacci hoặc số cách đến ô xuất phát bằng 1 nếu ô không chặn.
4. **Công thức chuyển:** trạng thái mới được tính từ những trạng thái nào? Vì sao mọi trường hợp của bài toán đã được bao phủ?
5. **Thứ tự điền:** các phụ thuộc phải được giải trước ô hiện tại; đây là điều kiện đặc trưng của bottom-up.
6. **Kết quả:** trả `dp[n]`, `dp[m][n]`, một max qua nhiều ô, hay cả đường đi/chuỗi/tập món được truy vết?

Nếu thiếu một thành phần, đặc biệt **ý nghĩa trạng thái** hoặc **thứ tự điền**, không thể chứng minh mã đúng chỉ bằng việc nhìn các vòng lặp.

## 2. Thứ tự điền bảng là thứ tự của phụ thuộc

Hình dung mỗi trạng thái là một đỉnh trong đồ thị. Có cạnh `u→v` nếu tính trạng thái v phải đọc trạng thái u. Muốn tính mỗi trạng thái **một lần** từ dưới lên, ta cần một **thứ tự tô-pô** của đồ thị phụ thuộc: mọi đỉnh u phải xuất hiện trước v.

- Fibonacci: `i−1→i`, `i−2→i` nên i tăng là hợp lệ.
- Đường đi lưới chỉ xuống/phải: `(r−1,c)→(r,c)` và `(r,c−1)→(r,c)`. Duyệt hàng từ trên xuống, trong mỗi hàng từ trái sang phải, là hợp lệ.
- LCS: `(i−1,j)`, `(i,j−1)` và `(i−1,j−1)` đều xuất hiện trước `(i,j)` nếu i, j tăng.
- Bài toán theo đoạn: `dp[l][r]` có thể phụ thuộc vào những đoạn ngắn hơn, nên điền theo **độ dài đoạn tăng dần** thay vì chỉ tăng l hoặc r tùy tiện.

~~~text
Fibonacci:
dp[i-2] ------\
               > dp[i]
dp[i-1] ------/

Lưới chỉ đi phải/xuống:
    dp[r-1][c]
         |
         v
    dp[r][c]  <- dp[r][c-1]

Ba lô 0/1:
    dp[i-1][c] -------------\
                             > dp[i][c]
    dp[i-1][c-w] ----------/
~~~

Nếu đồ thị có một **chu trình phụ thuộc thực sự**, không thể chỉ điền bảng theo bất kỳ thứ tự nào rồi coi như đã giải. Có thể phải đổi trạng thái, rút gọn quan hệ, dùng phương pháp giải hệ khác, hoặc lặp hội tụ với chứng minh riêng. Bottom-up kiểu một lượt dựa vào quan hệ phụ thuộc **không chu trình**.

### Pseudocode chung

~~~text
định nghĩa trạng thái và miền chỉ số
khởi tạo những trạng thái cơ sở
for state theo thứ tự mà mọi phụ thuộc đã có:
    if state không phải cơ sở:
        dp[state] = kết hợp các đáp án của những phụ thuộc
đọc ô kết quả; truy vết nếu bài cần một phương án cụ thể
~~~

Cụm “kết hợp” phải được giải thích riêng trong mỗi bài: có thể là **cộng số cách**, **lấy min số thao tác**, **lấy max giá trị** hoặc **chọn một trạng thái khả thi**. Không được dùng một giá trị mặc định 0 cho mọi phép toán vì “0” có ý nghĩa khác nhau trong những bài khác nhau.

## 3. Quy trình thiết kế bottom-up từng bước

**Bước 1: Phát biểu bài toán con bằng một câu chính xác.** Ví dụ đối với ba lô: “Xét **i món đầu tiên**, mỗi món chọn tối đa một lần, với **sức chứa tối đa c**”. Phân biệt “tổng trọng lượng đúng bằng c” với “không vượt c”: hai định nghĩa dẫn đến cơ sở và sentinel khác nhau.

**Bước 2: Chỉ ra tất cả lựa chọn của lời giải con.** Chẳng hạn với món thứ i: không chọn hoặc chọn nếu đủ sức chứa. Chứng minh không còn lựa chọn thứ ba.

**Bước 3: Viết công thức chỉ dùng bài toán con nhỏ hơn.** Công thức không được tham chiếu đến một kết quả chưa có hoặc không giảm về kích thước/trật tự cần thiết.

**Bước 4: Đặt cơ sở và trạng thái không thể đạt.** Đếm số cách thường bắt đầu từ 0 cách hoặc 1 cách ở điểm xuất phát. Tối thiểu hóa có thể dùng sentinel INF; không được vô tình cộng 1 vào INF rồi tràn.

**Bước 5: Điền bảng theo đồ thị phụ thuộc.** Có thể dùng chỉ số tăng, thứ tự theo hàng, độ dài đoạn hoặc topological order trên DAG.

**Bước 6: Xác định câu trả lời và chi phí.** Đáp án có thể là một ô, nhiều ô hoặc đường truy vết. Đếm số trạng thái, số chuyển cho mỗi ô, bộ nhớ cần giữ và nguy cơ tràn số.

**Nguyên tắc chứng minh:** trước lúc tính một trạng thái, **mọi trạng thái nó cần đã đúng**. Công thức đúng trên những giá trị đúng thì ô hiện tại đúng. Quy nạp theo thứ tự điền đưa ra tính đúng của toàn bảng.

## 4. Ví dụ 1: Fibonacci từ dưới lên

Định nghĩa `dp[i] = F(i)`, cơ sở `dp[0]=0` và `dp[1]=1` khi n≥1. Điền:

~~~java
// Phương thức minh họa, cần đặt trong một lớp Java.
static long fibonacciTable(int n) {
    if (n < 0 || n > 92) {
        throw new IllegalArgumentException("n out of range");
    }
    long[] dp = new long[n + 1];
    if (n == 0) return 0;
    dp[1] = 1;
    for (int i = 2; i <= n; i++) {
        dp[i] = dp[i - 1] + dp[i - 2];
    }
    return dp[n];
}
~~~

**Thứ tự:** đi i tăng vì i−1 và i−2 đều nhỏ hơn i. **Chứng minh:** hai cơ sở đúng; nếu các ô trước i đúng, công thức Fibonacci cho kết quả đúng ở i. **Chi phí:** Θ(n) thời gian và Θ(n) bộ nhớ bảng; nếu chỉ cần F(n), dùng hai biến có thể giảm xuống O(1) bộ nhớ.

**Giới hạn `long`:** F(92)=7540113804746346429 còn vừa `long`, F(93)=12200160415121876738 vượt `Long.MAX_VALUE`. Vì vậy mã giới hạn n≤92. Nếu dùng `BigInteger` để tính n lớn hơn, chi phí cộng phụ thuộc độ dài bit của kết quả, không còn mặc định O(1) theo mô hình bit.

**Ca biên:** n=0 phải trả 0 **trước** khi đọc dp[1]; n=1 trả 1; n=2 trả 1.

## 5. Ví dụ 2: Đếm đường đi trong lưới có chướng ngại

Cho lưới R×C. Mỗi bước chỉ được **đi sang phải** hoặc **đi xuống**, không đi qua ô bị chặn. Đếm số cách đi từ (0,0) tới (R−1,C−1).

Đặt `dp[r][c]` là số đường đi hợp lệ tới ô (r,c). Cơ sở và chuyển:

- Nếu `(r,c)` bị chặn, `dp[r][c]=0`.
- Nếu `(0,0)` không bị chặn, `dp[0][0]=1`.
- Với ô trống khác: `dp[r][c]=(r>0 ? dp[r−1][c] : 0)+(c>0 ? dp[r][c−1] : 0)`.

Vì một đường đi đến (r,c) chỉ có thể đến từ phía trên hoặc từ trái, hai nhóm trường hợp đó không chồng lấn; cộng chúng là đúng.

Lưới 3×3 bị chặn ở tâm:

~~~text
Lưới:          Bảng dp:
. . .           1 1 1
. # .           1 0 1
. . .           1 1 2
~~~

Có **2** đường đi. Nếu không chặn:

~~~text
1 1 1
1 2 3
1 3 6
~~~

có **6** đường đi. Duyệt r tăng, c tăng là hợp lệ vì ô phía trên thuộc hàng đã hoàn tất và ô bên trái thuộc cột trước của hàng hiện tại.

### Nén còn một hàng

Dùng `long[] ways` dài C. Với mỗi r, duyệt c từ trái sang phải:

- Nếu ô bị chặn: `ways[c]=0`.
- Nếu ô là điểm xuất phát trống: `ways[0]=1`.
- Nếu ô khác và c>0: `ways[c]=ways[c]+ways[c−1]`.
- Nếu c=0 và không bị chặn: giữ `ways[0]` từ hàng trước.

Trước cập nhật, `ways[c]` là số cách từ ô phía **trên**; `ways[c−1]` đã là số cách từ **trái** của hàng hiện tại. Nếu duyệt c **giảm**, giá trị bên trái chưa được cập nhật đúng, công thức một chiều không còn giữ bất biến.

**Chi phí:** toàn bảng Θ(RC) thời gian/bộ nhớ; bản nén Θ(RC) thời gian và Θ(C) bộ nhớ. Lưới rỗng, lưới không cột, ô xuất phát bị chặn hoặc ô đích bị chặn trả 0. Số đường đi có thể vượt `long`; có thể dùng `Math.addExact` để phát hiện tràn hoặc `BigInteger` nếu đề cần đáp án lớn chính xác.

## 6. Ví dụ 3: Ba lô 0/1 và hướng duyệt sức chứa

Cho n món, mỗi món i có trọng lượng **dương** `w[i]` và giá trị **không âm** `v[i]`. Mỗi món chỉ chọn **tối đa một lần**. Với sức chứa W, tìm tổng giá trị lớn nhất có thể đạt được khi tổng trọng lượng ≤W.

Định nghĩa:

**`dp[i][c]` = giá trị tối ưu khi chỉ xét i món đầu, sức chứa tối đa c.**

Đặt `dp[0][c]=0`. Với món i (đánh số 1-based) có trọng lượng w và giá trị v:

- Nếu w>c: `dp[i][c]=dp[i−1][c]`.
- Nếu w≤c: **`dp[i][c]=max(dp[i−1][c],dp[i−1][c−w]+v)`**.

Nhánh thứ nhất bỏ món, nhánh thứ hai chọn món. Cả hai đều tham chiếu **hàng i−1**, nên không món nào được chọn quá một lần.

Ví dụ `weights=[2,3,4]`, `values=[4,5,7]`, `W=6`:

| Số món đã xét / c | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1: w=2,v=4 | 0 | 0 | 4 | 4 | 4 | 4 | 4 |
| 2: thêm w=3,v=5 | 0 | 0 | 4 | 5 | 5 | 9 | 9 |
| 3: thêm w=4,v=7 | 0 | 0 | 4 | 5 | 7 | 9 | 11 |

Đáp án **11** tại `dp[3][6]`: chọn món w=2 và món w=4, tổng trọng lượng 6, tổng giá trị 4+7. Mã có thể lưu bảng 2D để truy vết chọn món nào hoặc nén thành một chiều nếu chỉ cần giá trị.

### Vì sao nén 1D phải duyệt giảm?

Dùng `dp[c]`, với mỗi món:

~~~java
// Mảnh mã trong vòng lặp xử lý một món weight/value.
for (int c = capacity; c >= weight; c--) {
    dp[c] = Math.max(dp[c], dp[c - weight] + value);
}
~~~

Khi xử lý c theo thứ tự **giảm dần**, `dp[c−weight]` (chỉ số nhỏ hơn c) **chưa bị cập nhật bởi món hiện tại**. Nó còn là giá trị của hàng i−1 như công thức 2D yêu cầu.

Nếu duyệt c **tăng**, có thể đọc giá trị vừa tạo từ cùng món, vô tình dùng món nhiều lần. Phản ví dụ: chỉ có một món trọng lượng 2, giá trị 4, sức chứa 6. Đúng 0/1 cho đáp án **4**; duyệt c tăng sẽ lần lượt suy ra 4 ở c=2, 8 ở c=4 và 12 ở c=6, tức dùng món ba lần — **sai bài toán 0/1**.

Nếu đề là **unbounded knapsack** (được chọn một món nhiều lần), việc đọc giá trị mới trong cùng lượt lại có thể là chủ đích và duyệt tăng có thể đúng. Vì vậy hướng duyệt xuất phát từ **định nghĩa trạng thái**, không phải quy tắc thuộc lòng.

**Độ phức tạp:** bảng 2D có Θ(nW) trạng thái và Θ(nW) bộ nhớ. Bản 1D vẫn Θ(nW) thời gian nhưng dùng Θ(W) bộ nhớ. Đây là thuật toán **giả đa thức** (*pseudo-polynomial*) theo giá trị số W: W có thể rất lớn dù chỉ cần O(log W) bit để biểu diễn. Nếu cần tập món cụ thể, bảng 2D cho phép truy vết từ trạng thái cuối; bản 1D có thể cần lưu thêm thông tin.

## 7. Ví dụ 4: Dãy con chung dài nhất (LCS)

**Longest Common Subsequence** là dãy ký tự xuất hiện đúng thứ tự trong cả hai chuỗi, **không nhất thiết liên tiếp**. Không được nhầm với **Longest Common Substring**, vốn yêu cầu ký tự liên tục.

Cho a độ dài m, b độ dài n. Định nghĩa:

**`dp[i][j]` = độ dài LCS của i ký tự đầu của a và j ký tự đầu của b.**

Cơ sở `dp[0][j]=dp[i][0]=0`. Nếu `a[i−1]==b[j−1]`:

**`dp[i][j]=dp[i−1][j−1]+1`.**

Nếu khác nhau:

**`dp[i][j]=max(dp[i−1][j],dp[i][j−1])`.**

Duyệt i từ 1..m, với mỗi i duyệt j từ 1..n. Tất cả phụ thuộc nằm **phía trên**, **phía trái** hoặc **chéo trên-trái**, nên đã có kết quả. Độ dài tối ưu nằm tại `dp[m][n]`.

### Truy vết một LCS

Bắt đầu ở (m,n):

1. Nếu hai ký tự cuối bằng nhau, đưa ký tự ấy vào kết quả rồi đi chéo lên-trái.
2. Nếu khác, so `dp[i−1][j]` và `dp[i][j−1]`: đi về phía còn có độ dài tối ưu; nếu hòa, chọn một quy tắc nhất quán.
3. Các ký tự được thêm từ cuối về đầu, nên đảo ngược để có chuỗi kết quả.

Ví dụ `a="ABCBDAB"` và `b="BDCABA"` có độ dài LCS bằng **4**. Với quy tắc đi lên khi hai hướng hòa, chương trình bên dưới trả **`"BCBA"`**. Có những LCS khác cùng độ dài, do đó chỉ kiểm tra một chuỗi cụ thể khi đề có quy tắc phá hòa rõ ràng.

**Thời gian Θ(mn), bộ nhớ Θ(mn)** cho bảng đầy đủ. Nếu chỉ cần độ dài, có thể dùng hai hàng O(n) bộ nhớ, hoặc O(min(m,n)) nếu đặt chuỗi ngắn hơn ở chiều cột. Nếu cần truy vết, việc xóa các hàng cũ sẽ làm mất thông tin trừ khi có thiết kế tái dựng riêng.

**Lưu ý Java:** `charAt` và `String.length()` hoạt động theo **đơn vị mã UTF-16**. Nếu yêu cầu LCS theo Unicode code point hoặc ký tự hiển thị/grapheme, phải định nghĩa và chuyển biểu diễn tương ứng. Các ví dụ ASCII không gặp sự khác biệt này.

## 8. Ví dụ 5: Đổi tiền ít đồng nhất

Có các mệnh giá **nguyên dương** và mỗi mệnh giá được dùng **không giới hạn lần**. Hỏi cần ít nhất bao nhiêu đồng để tạo **đúng** số tiền amount≥0; nếu không tạo được, trả -1.

Định nghĩa `dp[x]` là số đồng ít nhất để đạt đúng tổng x. Đặt `dp[0]=0`; với x>0 chưa biết, dùng một giá trị đặc biệt **INF** biểu diễn không thể đạt.

Công thức:

**`dp[x]=min(dp[x−coin]+1)`**, xét các coin≤x sao cho `dp[x−coin]` đạt được.

Vì coin>0, mọi x−coin đều nhỏ hơn x; duyệt x **tăng** từ 1 tới amount bảo đảm phụ thuộc sẵn sàng.

Với `coins=[1,3,4]` và amount=6:

| x | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dp[x]` | 0 | 1 | 2 | 1 | 1 | 2 | 2 |

Đáp án **2**, dùng hai đồng 3. Greedy lấy đồng lớn nhất sẽ chọn 4+1+1 (3 đồng), chứng tỏ greedy không phải luôn tối ưu.

Với `coins=[2,4]`, amount=7 không thể tạo, trả **-1**. Nếu mặc định những số tiền chưa đạt được có `dp[x]=0`, phép min sẽ sai vì 0 trông như lời giải miễn phí. Phải kiểm tra INF trước khi cộng 1 để tránh sai số hoặc tràn.

Bài này cho phép dùng lại một mệnh giá, **khác** 0/1 knapsack. Cách đặt vòng lặp và khởi tạo phải khớp điều kiện dùng một đối tượng một lần hay nhiều lần.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sử dụng các phương thức độc lập:

- `fibonacciTable`: DP một chiều với n=0..92.
- `gridPaths`: lưới chữ nhật, đếm đường đi khi chỉ được sang phải/xuống dưới, bộ nhớ O(C).
- `knapsack01`: mỗi món chọn tối đa một lần, trọng lượng dương, giá trị không âm; dùng 1D duyệt sức chứa giảm.
- `lcs`: điền bảng 2D rồi truy vết một LCS xác định theo quy tắc đi lên nếu hòa.
- `minCoins`: số đồng tối thiểu, được dùng mệnh giá nhiều lần, trả -1 khi không thể đạt.

Tất cả phương thức đều có kiểm tra điều kiện thiết yếu, không sửa đầu vào. Lưu thành **`BottomUpDpDemo.java`**:

~~~java
public final class BottomUpDpDemo {
    static long fibonacciTable(int n) {
        if (n < 0 || n > 92) {
            throw new IllegalArgumentException("Fibonacci n must be 0..92");
        }
        long[] dp = new long[n + 1];
        if (n == 0) {
            return 0;
        }
        dp[1] = 1;
        for (int i = 2; i <= n; i++) {
            dp[i] = dp[i - 1] + dp[i - 2];
        }
        return dp[n];
    }

    // true là ô bị chặn; chỉ đi phải hoặc xuống.
    static long gridPaths(boolean[][] blocked) {
        if (blocked == null) {
            throw new IllegalArgumentException("Null grid");
        }
        int rows = blocked.length;
        if (rows == 0) {
            return 0;
        }
        if (blocked[0] == null) {
            throw new IllegalArgumentException("Null row");
        }
        int cols = blocked[0].length;
        for (boolean[] oneRow : blocked) {
            if (oneRow == null || oneRow.length != cols) {
                throw new IllegalArgumentException("Non-rectangular grid");
            }
        }
        if (cols == 0) {
            return 0;
        }

        long[] ways = new long[cols];
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                if (blocked[r][c]) {
                    ways[c] = 0;
                } else if (r == 0 && c == 0) {
                    ways[c] = 1;
                } else if (c > 0) {
                    ways[c] = Math.addExact(ways[c], ways[c - 1]);
                }
                // c==0: ways[0] là số cách từ phía trên.
            }
        }
        return ways[cols - 1];
    }

    // 0/1 knapsack: mỗi món được dùng tối đa một lần.
    static long knapsack01(
            int[] weights, int[] values, int capacity) {
        if (weights == null || values == null
                || weights.length != values.length
                || capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid knapsack input");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Positive weights and nonnegative values required");
            }
        }

        long[] dp = new long[capacity + 1];
        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            int value = values[i];
            for (int c = capacity; c >= weight; c--) {
                dp[c] = Math.max(
                        dp[c], dp[c - weight] + (long) value);
            }
        }
        return dp[capacity];
    }

    // Theo đơn vị mã UTF-16 của chuỗi Java.
    static String lcs(String a, String b) {
        if (a == null || b == null) {
            throw new IllegalArgumentException("Null string");
        }
        int m = a.length();
        int n = b.length();
        int[][] dp = new int[m + 1][n + 1];

        for (int i = 1; i <= m; i++) {
            for (int j = 1; j <= n; j++) {
                if (a.charAt(i - 1) == b.charAt(j - 1)) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;
                } else {
                    dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
                }
            }
        }

        StringBuilder reversed = new StringBuilder();
        int i = m;
        int j = n;
        while (i > 0 && j > 0) {
            if (a.charAt(i - 1) == b.charAt(j - 1)) {
                reversed.append(a.charAt(i - 1));
                i--;
                j--;
            } else if (dp[i - 1][j] >= dp[i][j - 1]) {
                i--;
            } else {
                j--;
            }
        }
        return reversed.reverse().toString();
    }

    // Dùng số đồng ít nhất, cho phép dùng mệnh giá nhiều lần.
    static int minCoins(int[] coins, int amount) {
        if (coins == null || amount < 0
                || amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid amount or coins");
        }
        for (int coin : coins) {
            if (coin <= 0) {
                throw new IllegalArgumentException("Coin must be positive");
            }
        }

        int inf = amount + 1;
        int[] dp = new int[amount + 1];
        java.util.Arrays.fill(dp, inf);
        dp[0] = 0;

        for (int x = 1; x <= amount; x++) {
            for (int coin : coins) {
                if (coin <= x && dp[x - coin] != inf) {
                    dp[x] = Math.min(dp[x], dp[x - coin] + 1);
                }
            }
        }
        return dp[amount] == inf ? -1 : dp[amount];
    }

    public static void main(String[] args) {
        System.out.println("Fibonacci(10): " + fibonacciTable(10));
        System.out.println("Fibonacci(0): " + fibonacciTable(0));

        boolean[][] blockedCenter = {
            {false, false, false},
            {false, true,  false},
            {false, false, false}
        };
        boolean[][] noBlocks = {
            {false, false, false},
            {false, false, false},
            {false, false, false}
        };
        System.out.println("Grid center blocked: "
                + gridPaths(blockedCenter));
        System.out.println("Grid without blocks: "
                + gridPaths(noBlocks));

        int[] weights = {2, 3, 4};
        int[] values = {4, 5, 7};
        System.out.println("Knapsack 0/1: "
                + knapsack01(weights, values, 6));

        String subsequence = lcs("ABCBDAB", "BDCABA");
        System.out.println("LCS: " + subsequence
                + " (length=" + subsequence.length() + ")");

        System.out.println("Min coins for 6: "
                + minCoins(new int[] {1, 3, 4}, 6));
        System.out.println("Min coins for 7 with {2,4}: "
                + minCoins(new int[] {2, 4}, 7));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac BottomUpDpDemo.java
java BottomUpDpDemo
~~~

**Kết quả đầu ra chuẩn:**

~~~text
Fibonacci(10): 55
Fibonacci(0): 0
Grid center blocked: 2
Grid without blocks: 6
Knapsack 0/1: 11
LCS: BCBA (length=4)
Min coins for 6: 2
Min coins for 7 with {2,4}: -1
~~~

### Giải thích từng dòng đầu ra

Fibonacci(10)=55 và Fibonacci(0)=0 theo cơ sở/truy hồi. Lưới 3×3 chặn ô giữa có 2 đường đi, còn lưới trống có 6 đường đi. Ba lô có sức chứa 6, chọn món trọng lượng 2 và 4, tổng giá trị 11; không được dùng một món lặp lại. LCS của hai chuỗi ví dụ có độ dài 4 và chuỗi được chọn theo cách truy vết là **BCBA**. Đổi tiền 6 với các mệnh giá 1,3,4 cần hai đồng 3; số 7 không tạo được từ những đồng 2 và 4 nên trả -1.

**Giới hạn và hợp đồng:** các hàm bỏ qua những kích thước quá lớn không thể cấp phát trong heap JVM; knapsack từ chối capacity=Integer.MAX_VALUE và minCoins từ chối amount=Integer.MAX_VALUE để tránh tràn khi tạo mảng dài thêm 1, nhưng các giá trị nhỏ hơn vẫn có thể làm thiếu bộ nhớ. Lưới đếm đường đi dùng `Math.addExact` để ném `ArithmeticException` khi tổng vượt phạm vi long. Đổi tiền dùng `INF=amount+1` vì mọi mệnh giá ≥1, nên nếu có lời giải với amount>0 thì số đồng tối ưu không vượt amount; phải kiểm tra `dp[x−coin]!=INF` trước khi cộng 1.

## 10. Chứng minh tính đúng bằng bất biến vòng lặp

**Bất biến tổng quát:** trước khi điền trạng thái v, những trạng thái mà công thức của v dùng đều đã được điền **đúng theo định nghĩa**.

**Khởi tạo:** các cơ sở đúng do điều kiện bài toán, chẳng hạn `F(0)=0`, `dp[0][c]=0` của 0/1 knapsack, hoặc `dp[0][0]=1` cho ô xuất phát trống.

**Duy trì:** xét một trạng thái chưa điền. Thứ tự đã chọn bảo đảm mọi trạng thái phụ thuộc được tính trước. Công thức chuyển đã chứng minh bao phủ mọi trường hợp hợp lệ (lấy min/max, cộng số cách hoặc chọn/bỏ), nên giá trị mới đúng.

**Kết thúc:** khi điền xong các trạng thái cần thiết, ô kết quả có ý nghĩa đúng như trạng thái mục tiêu đã định nghĩa; nếu cần một phương án, quá trình truy vết theo những lựa chọn bảo toàn giá trị tối ưu.

Với bảng 1D nén từ 2D, bất biến phải nói rõ **giá trị trước hay sau cập nhật**. Ví dụ trong knapsack 0/1, `dp[c−w]` phải là của lượt món trước, nên c giảm. Trong đếm đường đi lưới, `ways[c−1]` cần là của hàng hiện tại, nên c tăng. Hai hướng khác nhau không mâu thuẫn: chúng đáp ứng **hai đồ thị phụ thuộc khác nhau**.

## 11. Độ phức tạp: số trạng thái × chi phí chuyển

Có thể ước lượng:

**Thời gian ≈ số trạng thái được tính × chi phí chuyển tại một trạng thái**, cộng phần khởi tạo, truy vết và xuất kết quả.

| Bài toán | Số trạng thái | Chuyển/ô | Thời gian | Bộ nhớ |
|---|---:|---:|---:|---:|
| Fibonacci tới n | Θ(n) | O(1) | Θ(n) | Θ(n), nén O(1) |
| Đường đi lưới R×C | Θ(RC) | O(1) | Θ(RC) | Θ(RC), nén Θ(C) |
| Ba lô 0/1 n món, sức chứa W | Θ(nW) | O(1) | Θ(nW) | Θ(nW), nén Θ(W) |
| LCS chuỗi dài m,n | Θ(mn) | O(1) | Θ(mn) | Θ(mn), chỉ độ dài có thể nén |
| Đổi tiền amount A, k mệnh giá | Θ(A) | O(k) | O(Ak) | Θ(A) |

Độ phức tạp ở bảng dành cho những miền đầu vào thông thường, không có nghĩa rằng mọi phép toán với số nguyên tùy ý đều O(1). Với `BigInteger`, chi phí cộng phụ thuộc số bit. Việc cấp phát `int[A+1]` cũng không thực tế khi A quá lớn.

**Nén bảng có điều kiện:** chỉ loại bỏ lớp trạng thái khi chắc chắn không còn phụ thuộc nào cần đến nó và không cần dùng nó để truy vết. Nếu đề yêu cầu **giá trị tối ưu**, bảng một chiều có thể đủ. Nếu đề cần **danh sách món, đường đi hoặc chuỗi**, phải lưu thêm thông tin hoặc có kế hoạch tái dựng.

## 12. So sánh bottom-up và top-down memoization

Cả hai có thể dùng **cùng định nghĩa trạng thái, cơ sở và công thức chuyển**. Khác biệt chủ yếu ở cách duyệt trạng thái:

| Tiêu chí | Top-down có ghi nhớ | Bottom-up lập bảng |
|---|---|---|
| Bắt đầu từ đâu? | Gọi trạng thái đích, đệ quy tới các phụ thuộc | Bắt đầu từ cơ sở, điền theo thứ tự phụ thuộc |
| Thăm những trạng thái nào? | Những trạng thái phát sinh từ lời gọi thực sự | Có thể điền toàn bộ bảng, kể cả trạng thái không dùng |
| Bộ nhớ ngăn xếp | Có độ sâu đệ quy | Thường không dùng stack đệ quy |
| Thứ tự | Thể hiện gián tiếp qua lời gọi | Phải thiết kế tường minh |
| Nén bộ nhớ | Đôi khi khó | Dễ phát hiện phụ thuộc lớp/hàng |
| Bẫy | Tràn stack, memo sai sentinel, chu trình | Điền sai hướng, ghi đè giá trị cũ |

**Không mặc định bottom-up luôn nhanh hơn.** Top-down có thể chỉ chạm một phần nhỏ của không gian trạng thái nếu nhiều ô không liên quan tới đích. Bottom-up tránh stack và có thể tăng tính cục bộ truy cập, nhưng nếu điền nhiều ô không dùng thì có thể mất lợi thế. Nếu cả hai thăm cùng số trạng thái và cùng số chuyển, độ phức tạp tiệm cận thường giống nhau.

Khi chuyển từ đệ quy sang bottom-up, hãy viết ra quan hệ phụ thuộc trước. **Đổi lời gọi `f(i)` thành `dp[i]` mà không sửa thứ tự tính toán không đảm bảo đúng.**

## 13. Các thứ tự thường gặp ngoài ví dụ

### 13.1. Chỉ số tăng

Dùng khi `dp[i]` phụ thuộc vào những trạng thái có chỉ số nhỏ hơn i, như Fibonacci, minCoins với mệnh giá dương hoặc số cách lên cầu thang.

### 13.2. Hàng tăng, cột tăng

Dùng khi trạng thái 2D phụ thuộc vào hàng trên và cột trái: LCS, chỉnh sửa xâu (edit distance) dạng bảng hoặc số đường đi lưới.

### 13.3. Độ dài đoạn tăng

Với interval DP, `dp[l][r]` thường dùng các đoạn **ngắn hơn**. Duyệt length=1..n, rồi liệt kê mọi (l,r) có r=l+length−1. Không chắc đúng nếu chỉ tăng l/r mà trạng thái phụ thuộc vào một ô chưa điền.

~~~text
for length from 1 to n:
    for left from 0 while left+length <= n:
        right = left + length - 1
        dp[left][right] = g(các đoạn ngắn hơn)
~~~

### 13.4. Thứ tự tô-pô của DAG

Nếu các trạng thái không tạo thành lưới đơn giản nhưng quan hệ phụ thuộc là DAG, có thể lập thứ tự tô-pô để điền dần. Mỗi khi xử lý một trạng thái, bảo đảm các nguồn đóng góp đã được giải. Không thể dùng một lượt topo với quan hệ có chu trình chưa được xử lý.

### 13.5. Hướng duyệt khi nén

- Đếm đường đi lưới: c **tăng**, vì cần ô bên trái **đã cập nhật**.
- Ba lô 0/1: capacity **giảm**, vì cần giá trị sức chứa nhỏ hơn **chưa cập nhật** của lượt món trước.
- Ba lô không giới hạn món: trong một cách lập bảng 1D, capacity **tăng** để cho phép dùng lại món.
- Fibonacci: không cần cả bảng nếu chỉ cần hai giá trị cuối.
- LCS: nếu chỉ lấy độ dài có thể giữ hai hàng, nhưng để truy vết cần dữ liệu phù hợp.

Điểm chung là **giữ đúng phiên bản của trạng thái phụ thuộc**; hướng duyệt chỉ là hệ quả.

## 14. Lỗi phổ biến và cách kiểm thử

1. **Không định nghĩa trạng thái:** không rõ dp biểu diễn “đúng bằng” hay “không vượt”, “số cách” hay “giá trị tối ưu”.
2. **Khởi tạo sai:** dùng 0 cho trạng thái min không thể đạt, bỏ quên cơ sở hoặc quên bài toán rỗng.
3. **Điền sai thứ tự:** đọc trạng thái chưa được tính hoặc đã ghi đè.
4. **Knapsack 0/1 duyệt capacity tăng:** một món bị chọn lại nhiều lần.
5. **Nhầm 0/1 với unbounded:** hai bài gần giống nhưng số lần dùng một món khác nhau.
6. **Đếm đường đi sai biên:** bỏ quên ô chặn, hàng/cột đầu hoặc ô xuất phát.
7. **Nhầm subsequence với substring:** LCS cho phép ký tự không liền kề.
8. **Không lưu dữ liệu truy vết:** chỉ có giá trị tối ưu nhưng đề cần cụ thể đường đi/chuỗi/tập món.
9. **Cộng INF:** dùng `dp[x−coin]+1` khi dp cũ không thể đạt có thể tràn hoặc tạo kết quả giả.
10. **Tràn số:** Fibonacci, số đường đi và số cách tổ hợp có thể vượt int/long.
11. **Đếm sai độ phức tạp:** n trạng thái nhưng mỗi trạng thái xét k lựa chọn thì có O(nk), không phải O(n).
12. **Bỏ qua tính giả đa thức:** W hoặc amount rất lớn dù chuỗi bit đầu vào ngắn.
13. **Nén trước khi chứng minh:** xóa mất lớp thông tin mà chuyển trạng thái cần.
14. **Cho rằng top-down luôn kém:** top-down có thể bỏ qua nhiều trạng thái không liên quan.

### Bộ thử biên nên có

| Bài | Dữ liệu thử | Kết quả |
|---|---|---|
| Fibonacci | n=0,1,2,6,10 | 0,1,1,8,55 |
| Fibonacci | n=92 | 7540113804746346429 |
| Lưới | một ô trống; một ô chặn | 1; 0 |
| Lưới | 3×3 trống; chặn tâm | 6; 2 |
| Ba lô 0/1 | một món w=2,v=4,W=6 | 4, không phải 12 |
| Ba lô 0/1 | weights=[2,3,4], values=[4,5,7], W=6 | 11 |
| LCS | một chuỗi rỗng | chuỗi rỗng |
| LCS | ABCBDAB và BDCABA | độ dài 4 |
| Đổi tiền | [1,3,4], amount=6 | 2 |
| Đổi tiền | [2,4], amount=7 | -1 |
| Đổi tiền | amount=0 | 0 |
| Đổi tiền | danh sách mệnh giá rỗng, amount>0 | -1 |

**Kiểm thử đối chiếu:** với ba lô n≤15, liệt kê tất cả `2^n` tập con để tính đáp án thật; với LCS chuỗi ngắn, liệt kê subsequence và so độ dài; với đổi tiền amount nhỏ, dùng BFS trên tổng 0..amount; với lưới nhỏ, đếm mọi đường đi bằng quay lui. Tạo các ca có 0, phần tử trùng, dữ liệu rỗng, không thể đạt tới, và một ca chứng minh hướng duyệt một chiều sai.

### Checklist trước khi hoàn tất

- Định nghĩa từng ô dp chính xác, có miền chỉ số rõ không?
- Trường hợp cơ sở và trạng thái không thể đạt đã đúng chưa?
- Công thức đã xét hết các lựa chọn hợp lệ chưa?
- Mọi phụ thuộc có được tính **trước** khi điền ô hiện tại không?
- Nếu nén 1D, giá trị đọc là **hàng cũ** hay **hàng mới** đúng theo công thức?
- Có phân biệt dùng một lần và nhiều lần không?
- Đáp án nằm ở ô nào, có cần truy vết lựa chọn không?
- Thời gian đã nhân số trạng thái với số phép chuyển mỗi trạng thái chưa?
- Kiểu dữ liệu và bộ nhớ có chứa được giá trị/kích thước yêu cầu không?
- Đã đối chiếu ca nhỏ với một lời giải độc lập chưa?

**Kết luận:** bottom-up DP giải các bài toán con theo **một thứ tự hợp lệ của quan hệ phụ thuộc**. Cách làm đáng tin cậy là *định nghĩa trạng thái → chứng minh chuyển → khởi tạo cơ sở → sắp thứ tự điền → đọc và truy vết đáp án → kiểm tra biên và tài nguyên*. Hiểu **vì sao một ô được phép đọc những ô khác** quan trọng hơn việc thuộc một mẫu vòng lặp duy nhất.