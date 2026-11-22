# Ba lô 0/1 và lựa chọn lấy hoặc bỏ

**Bài toán ba lô 0/1 (0/1 Knapsack)** là một ví dụ nền tảng của **quy hoạch động theo tài nguyên**. Có nhiều vật, mỗi vật mang một **trọng lượng** và một **giá trị**. Với sức chứa giới hạn, ta muốn chọn một tập vật có tổng trọng lượng không vượt quá sức chứa và **tổng giá trị lớn nhất**. Mỗi vật chỉ được chọn **đúng một lần hoặc không chọn lần nào**: đó chính là ý nghĩa của hai lựa chọn **lấy/bỏ** và ký hiệu *0/1*.

Bài toán giúp luyện ba kỹ năng cốt lõi: định nghĩa bài toán con đủ thông tin, chứng minh công thức chuyển trạng thái bằng cách phân chia mọi phương án theo **lấy hay bỏ vật cuối**, và nén bộ nhớ từ bảng hai chiều xuống một chiều mà **không dùng lại cùng vật**. Chi tiết cuối đặc biệt quan trọng: quét sức chứa sai chiều có thể khiến một chương trình trông hợp lý giải nhầm thành bài **ba lô không giới hạn số lượng**.

## 1. Đặc tả và các giả thiết phải nói rõ

Cho `n` vật được đánh số từ 0 đến n−1. Vật `i` có:

- Trọng lượng nguyên dương `w[i] > 0`.
- Giá trị nguyên không âm `v[i] >= 0`.

Có một ba lô sức chứa nguyên không âm `W >= 0`. Cần tìm các biến quyết định `x[i]` thỏa:

\[
x_i \in \{0,1\}, \qquad
\sum_{i=0}^{n-1} w_i x_i \le W,
\]

và **tối đa hóa**:

\[
\sum_{i=0}^{n-1} v_i x_i.
\]

Trong đó `x[i]=1` nghĩa là **lấy vật i**, còn `x[i]=0` là **bỏ vật i**. Ràng buộc trọng lượng là **không vượt quá W**, không phải bắt buộc bằng W. Nếu tất cả vật đều quá nặng hoặc W=0, ta được phép **không lấy vật nào**, giá trị tối ưu bằng 0.

Trong phạm vi chương trình Java 17 của bài:
- Trọng lượng của mọi vật **lớn hơn 0**, giá trị **không âm**, sức chứa **không âm**.
- Mỗi vật là một bản ghi riêng, cho dù hai vật có cùng trọng lượng và giá trị. Hai bản ghi giống nhau vẫn có thể là **hai vật khác nhau**, nhưng mỗi bản ghi chỉ được chọn tối đa một lần.
- Mục tiêu chính là **giá trị tối ưu**; khi cần, ta còn khôi phục **một tập vật đạt tối ưu**.
- Không có giới hạn phụ như tối đa k vật, phụ thuộc giữa các vật, thể tích thứ hai hoặc thứ tự chọn. Nếu đề có những ràng buộc này, trạng thái cần được thiết kế lại.
- Chấp nhận tập rỗng: không bắt buộc chọn ít nhất một vật.

Nếu đề yêu cầu **đúng W** thay vì **không quá W**, hoặc cho phép chọn mỗi loại vật **nhiều lần**, công thức và khởi tạo phải được xem xét lại. Không được áp một lời giải 0/1 cho bài toán khác chỉ vì đều có tên “ba lô”.

### Ví dụ cụ thể

| Vật | Trọng lượng | Giá trị | Tỷ lệ giá trị / trọng lượng |
| --- | ---: | ---: | ---: |
| A | 2 | 3 | 1,5 |
| B | 3 | 4 | 1,33… |
| C | 4 | 5 | 1,25 |
| D | 5 | 8 | 1,6 |

Nếu `W=5`, chọn D (trọng lượng 5, giá trị 8) tốt hơn chọn A+B (trọng lượng 5, giá trị 7). Đáp án tối ưu là **8**, chọn **[D]**.

Nếu `W=7`, chọn **A+D** có tổng trọng lượng 7 và tổng giá trị 11. Các lựa chọn khác như B+C cho giá trị 9, A+C cho 8 hay A+B cho 7 đều không tốt bằng. Đáp án tối ưu là **11**, với một tập vật đạt tối ưu là **[A,D]**.

Để tránh nhầm lẫn, các ví dụ tiếp theo sử dụng **đánh số vật từ 0**, còn chỉ số hàng DP `i` là **số vật đầu tiên đã được xét**, chạy từ 0 đến n.

## 2. Vì sao thử tất cả tập con rất tốn thời gian?

Mỗi vật có đúng hai quyết định: lấy hoặc bỏ. Với n vật, có **2^n** tập con tiềm năng. Cách brute force duyệt mọi bitmask, tính tổng trọng lượng và tổng giá trị, bỏ tập quá sức chứa rồi chọn giá trị lớn nhất.

Cách này đúng về mặt ngữ nghĩa vì xét toàn bộ phương án khả thi, nhưng với n lớn thì rất tốn thời gian. Nếu mỗi tập con được tính lại tổng trong O(n), tổng thời gian là **O(n·2^n)**; có các cách cập nhật hiệu quả hơn, nhưng số tập con vẫn tăng theo cấp số mũ trong cách duyệt cơ bản.

Quy hoạch động tận dụng thực tế rằng **rất nhiều chuỗi quyết định khác nhau dẫn đến cùng một bài toán con**. Chẳng hạn nếu đã xét cùng i vật và còn cùng sức chứa cho các vật tiếp theo, ta không cần giải lại bài toán tối ưu phần còn lại cho từng lịch sử đã đi qua.

Tư duy cốt lõi không phải “thử mọi cách bằng đệ quy”, mà là **định nghĩa trạng thái gom các lịch sử tương đương một cách an toàn** và dùng các kết quả đã biết để loại bỏ tính toán trùng.

## 3. Định nghĩa trạng thái DP hai chiều

Ta dùng:

\[
dp[i][c] =
\text{giá trị lớn nhất chọn được từ i vật đầu tiên, với sức chứa tối đa c}.
\]

Phạm vi:
- `0 <= i <= n`: số vật đầu tiên được phép xét.
- `0 <= c <= W`: sức chứa có thể dùng.

**Cách hiểu quan trọng:** `dp[i][c]` là giá trị tối ưu khi **chỉ được chọn trong các vật 0..i−1** và **tổng trọng lượng không vượt c**. `c` không nhất thiết là trọng lượng đã dùng, cũng không yêu cầu phải lấp đầy chính xác c.

### Trạng thái cơ sở

Nếu không có vật nào, giá trị tối đa là 0 với mọi sức chứa:

\[
dp[0][c] = 0 \qquad (0 \le c \le W).
\]

Nếu `c=0` và mọi trọng lượng đều dương, không thể chọn vật nào:

\[
dp[i][0] = 0 \qquad (0 \le i \le n).
\]

Các giá trị cơ sở này phù hợp vì **được chọn tập rỗng** và **không bắt buộc dùng hết sức chứa**. Trong Java, một mảng `long[][]` mới được khởi tạo với tất cả ô bằng 0, nên ta có thể dùng chính đặc điểm ấy cho bài toán đã định nghĩa.

**Không sử dụng khởi tạo toàn 0 một cách máy móc** nếu bài toán yêu cầu tổng trọng lượng **đúng bằng c**, hoặc có ràng buộc phải chọn ít nhất một vật. Khi đó phải phân biệt trạng thái **không thể đạt** với trạng thái có giá trị 0, chẳng hạn dùng giá trị `-INF` cho các sức chứa không thể đạt đúng.

## 4. Công thức chuyển trạng thái: “bỏ” hoặc “lấy”

Xét trạng thái `dp[i][c]` với `i >= 1`, tức đã có quyền chọn trong i vật đầu tiên. Đặt vật cuối đang xét là vật `i−1`, có trọng lượng `wi` và giá trị `vi`.

Mọi lời giải khả thi cho trạng thái này rơi vào **đúng một trong hai trường hợp**:

**Trường hợp 1 — bỏ vật i−1.** Ta chỉ chọn trong i−1 vật trước, nên giá trị tốt nhất là:

\[
skip = dp[i-1][c].
\]

**Trường hợp 2 — lấy vật i−1.** Chỉ hợp lệ khi `wi <= c`. Sau khi dùng `wi` sức chứa và nhận `vi` giá trị, các vật còn lại được chọn từ **i−1 vật trước**, với sức chứa `c−wi`:

\[
take = dp[i-1][c-w_i] + v_i.
\]

Vì mọi phương án hoặc lấy hoặc bỏ vật cuối, công thức tối ưu là:

\[
dp[i][c] =
\begin{cases}
dp[i-1][c], & w_i > c,\\[3pt]
\max\big(dp[i-1][c],\,dp[i-1][c-w_i]+v_i\big),&w_i\le c.
\end{cases}
\]

**Điểm mấu chốt:** cả hai nhánh đều đọc **hàng i−1**. Nhánh lấy vật không được quay lại `dp[i][c−wi]` của cùng hàng, vì như thế có thể tái sử dụng chính vật i−1 nhiều lần. Chỉ số i là phần thông tin ngăn một vật được chọn lại.

### Giả mã bottom-up

~~~text
dp[0][c] = 0, với mọi c từ 0 đến W

for i = 1 .. n:
    wi = weight[i-1]
    vi = value[i-1]

    for c = 0 .. W:
        dp[i][c] = dp[i-1][c]           // bỏ vật
        if wi <= c:
            dp[i][c] = max(
                dp[i][c],
                dp[i-1][c-wi] + vi       // lấy vật đúng một lần
            )

answer = dp[n][W]
~~~

Với mỗi trạng thái, ta chỉ cần xét hai lựa chọn hợp lệ và lấy giá trị lớn hơn. Kết quả chỉ là **giá trị tối ưu**; phần khôi phục vật được chọn sẽ xét riêng.

## 5. Lập bảng bằng tay cho bộ dữ liệu A, B, C, D

Ta xây bảng với các vật:

~~~text
A: weight=2, value=3
B: weight=3, value=4
C: weight=4, value=5
D: weight=5, value=8
~~~

Trước hết, xét `W=5`. Mỗi hàng là giá trị tối đa dùng **tối đa** c đơn vị sức chứa sau khi được phép chọn thêm vật ở tên hàng.

| Đã xét | c=0 | c=1 | c=2 | c=3 | c=4 | c=5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Không có vật | 0 | 0 | 0 | 0 | 0 | 0 |
| A | 0 | 0 | 3 | 3 | 3 | 3 |
| A,B | 0 | 0 | 3 | 4 | 4 | 7 |
| A,B,C | 0 | 0 | 3 | 4 | 5 | 7 |
| A,B,C,D | 0 | 0 | 3 | 4 | 5 | **8** |

Diễn giải một số ô:

- `dp[1][2]=3`: lấy A có trọng lượng 2, giá trị 3.
- `dp[2][5]=7`: so **bỏ B** nhận 3 với **lấy B** nhận `dp[1][2]+4 = 3+4=7`, chọn lấy.
- `dp[3][4]=5`: vật C trọng lượng 4, giá trị 5 tốt hơn phương án bỏ C giá trị 4.
- `dp[3][5]=7`: vật C không cải thiện phương án A+B (7); nếu lấy C chỉ còn c=1, được 5.
- `dp[4][5]=8`: so bỏ D `dp[3][5]=7` với lấy D `dp[3][0]+8=8`; chọn D.

Vậy kết quả `dp[4][5]=8`, tương ứng **lấy D**. Không thể lấy D và một vật khác trong W=5 vì D đã dùng hết sức chứa.

### Khi sức chứa tăng lên W=7

Lúc này ta thêm hai cột c=6 và c=7. Bảng đầy đủ:

| Đã xét | c=0 | c=1 | c=2 | c=3 | c=4 | c=5 | c=6 | c=7 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Không có vật | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| A | 0 | 0 | 3 | 3 | 3 | 3 | 3 | 3 |
| A,B | 0 | 0 | 3 | 4 | 4 | 7 | 7 | 7 |
| A,B,C | 0 | 0 | 3 | 4 | 5 | 7 | 8 | 9 |
| A,B,C,D | 0 | 0 | 3 | 4 | 5 | 8 | 8 | **11** |

Ở ô cuối:
- **Bỏ D:** `dp[3][7]=9` (có thể chọn B+C).
- **Lấy D:** `dp[3][7−5]+8 = dp[3][2]+8 = 3+8=11` (chọn A+D).

Suy ra `dp[4][7]=11`, với một nghiệm là **[A,D]**. Đây là ví dụ rõ ràng rằng DP cần xét **toàn bộ phương án lấy/bỏ**, không chỉ chọn vật có trọng lượng nhỏ nhất hay tỷ lệ giá trị/trọng lượng lớn nhất ở mỗi bước.

## 6. Chứng minh tính đúng đắn bằng quy nạp

Đặt mệnh đề `P(i)`: với mọi sức chứa c từ 0 đến W, `dp[i][c]` là giá trị lớn nhất của mọi tập con gồm các vật trong **i vật đầu**, có tổng trọng lượng không quá c.

**Khởi tạo `i=0`:** không có vật để lấy, chỉ có tập rỗng, tổng trọng lượng 0 và giá trị 0. Vì c≥0, `dp[0][c]=0` đúng với mọi c.

**Giả thiết quy nạp:** giả sử `dp[i−1][c]` đúng với mọi c.

**Bước quy nạp:** xét một tập vật tối ưu của i vật đầu tại sức chứa c. Nó hoặc **không chứa vật i−1**, hoặc **có chứa vật i−1**. Nếu không chứa, giá trị không vượt `dp[i−1][c]` theo giả thiết quy nạp. Nếu chứa, phải có `wi≤c` và phần còn lại là tập con của i−1 vật đầu với sức chứa c−wi, nên giá trị không vượt `dp[i−1][c−wi]+vi`. Ngược lại, mỗi nhánh của công thức đều xây được một tập hợp lệ bằng cách giữ nghiệm tối ưu của i−1 vật và (nếu cần) thêm vật mới. Lấy max hai nhánh do đó đúng bằng giá trị tối ưu.

**Kết luận:** `dp[n][W]` là giá trị tối ưu cho toàn bộ n vật và sức chứa W.

Cần kiểm tra cả **hai chiều** của lập luận: mọi nghiệm hợp lệ thuộc một nhánh (không bị bỏ sót), và mỗi phương án tạo bởi một nhánh đều hợp lệ (không dùng vật hai lần). Đó là nền tảng của tính đúng đắn; việc chạy đúng vài bảng dữ liệu chỉ đóng vai trò kiểm thử.

## 7. Khôi phục một danh sách vật đã lấy

Bảng DP hai chiều cho phép **lần ngược** lựa chọn từ `(i=n,c=W)` về trạng thái cơ sở.

Quy tắc khi các giá trị đều không âm, trọng lượng dương:
1. Nếu `dp[i][c] == dp[i−1][c]`, có một phương án tối ưu **bỏ vật i−1**. Ta có thể chọn **bỏ** trong trường hợp hòa để kết quả xác định.
2. Nếu `dp[i][c] > dp[i−1][c]`, nhánh lấy vật i−1 là nhánh đã cải thiện kết quả. Thêm vật ấy vào danh sách, giảm c đi `w[i−1]`.
3. Giảm i và tiếp tục tới i=0.
4. Danh sách thu được theo thứ tự ngược, nên đảo lại nếu muốn xuất theo thứ tự đầu vào.

Đối với W=7:
- `dp[4][7]=11 > dp[3][7]=9`: lấy D, còn c=2.
- `dp[3][2]=3 == dp[2][2]=3`: bỏ C.
- `dp[2][2]=3 == dp[1][2]=3`: bỏ B.
- `dp[1][2]=3 > dp[0][2]=0`: lấy A.
- Đảo danh sách đã chọn `[D,A]` thành **[A,D]**.

### Có nhiều nghiệm tối ưu thì sao?

Nếu `dp[i][c]==dp[i−1][c]`, có thể **cả nhánh lấy và nhánh bỏ đều tối ưu**; quy tắc trên ưu tiên bỏ. Đây là một **chính sách phá hòa** nhằm trả về *một* nghiệm, không khẳng định nghiệm là duy nhất hoặc có ít vật nhất.

Nếu đề yêu cầu **tất cả nghiệm tối ưu**, **số nghiệm tối ưu**, hoặc **ít vật nhất trong các nghiệm có cùng giá trị**, phải bổ sung dữ liệu và/hoặc quy tắc so sánh phụ. Đếm nghiệm có thể rất lớn, không thể suy ra bằng cách chỉ đếm số lần hai nhánh hòa.

Nếu chỉ dùng một mảng DP một chiều rồi ghi đè theo vật, **không thể áp dụng trực tiếp** phép so sánh giữa hai hàng `dp[i]` và `dp[i−1]`, vì các hàng cũ không còn lưu. Muốn truy vết từ 1D cần thêm dữ liệu ghi nhận quyết định có bảo đảm đúng, hoặc lưu bảng 2D/bảng bit quyết định theo từng giai đoạn.

## 8. Nén bộ nhớ thành một chiều O(W)

Để tính **chỉ giá trị tối ưu**, không cần giữ tất cả hàng của bảng. Mỗi `dp[i][c]` chỉ dùng hàng `i−1`. Ta có thể dùng mảng `best[c]` và xử lý vật lần lượt:

~~~text
best[c] = 0 cho mọi c từ 0 đến W

for each item (weight=wi, value=vi):
    for c from W down to wi:
        best[c] = max(best[c], best[c-wi] + vi)

answer = best[W]
~~~

**Tại sao phải duyệt c giảm dần?** Vì `wi>0` nên `c−wi<c`. Khi ta duyệt từ W xuống wi, ô có chỉ số nhỏ hơn `c−wi` **chưa được cập nhật bởi vật hiện tại**, nên nó vẫn là kết quả của **giai đoạn trước**. Nhánh lấy vì vậy chỉ sử dụng các vật đã xử lý trước đó, còn vật hiện tại được thêm đúng một lần.

Dù không còn viết chỉ số `i` trên mảng, **vòng ngoài theo từng vật vẫn mang ý nghĩa giai đoạn i**. Nén 2D → 1D là một tối ưu **lưu trữ**, không xóa ràng buộc 0/1 khỏi mô hình.

### Phản ví dụ nếu duyệt sai chiều

Chỉ có **một** vật A với trọng lượng 2, giá trị 3, sức chứa W=4. Đáp án 0/1 đúng là **3**: không thể lấy A hai lần.

Nếu cập nhật **tăng** c từ 2 đến 4:
1. Tại c=2, `best[2]` trở thành 3.
2. Tại c=4, phép tính `best[4]=max(best[4],best[2]+3)` đọc **best[2] đã được cập nhật trong cùng lượt**.
3. Kết quả sai `best[4]=6`, tương đương lấy A hai lần.

Khi cập nhật **giảm** từ 4 xuống 2:
1. Tại c=4, `best[2]` của giai đoạn trước vẫn bằng 0, nên `best[4]` chỉ thành 3.
2. Sau đó mới cập nhật `best[2]=3`.
3. `best[4]` giữ đúng giá trị tối ưu 3.

| Cách duyệt sức chứa cho một vật A(2,3), W=4 | best[4] | Ý nghĩa |
| --- | ---: | --- |
| Giảm từ 4 xuống 2 | **3** | 0/1: A chỉ dùng một lần |
| Tăng từ 2 lên 4 | **6** | Đã vô tình cho phép A hai lần |

**Đừng chỉ học thuộc “giảm là 0/1, tăng là unbounded”.** Hãy nêu lý do sâu hơn: phép đọc phải lấy từ **giai đoạn trước** hay được phép lấy từ **giai đoạn hiện tại**? Chính định nghĩa bài toán quyết định chiều cập nhật.

### So sánh với ba lô không giới hạn

Trong **unbounded knapsack**, mỗi loại vật có thể lấy nhiều lần. Khi chọn vật có trọng lượng wi, ta được phép cộng giá trị của trạng thái **đã dùng chính vật ấy** trong cùng giai đoạn. Với trọng lượng dương, vòng c **tăng dần** hiện thực hóa việc tái sử dụng ấy.

Với **0/1 knapsack**, việc đọc cập nhật cùng giai đoạn làm sai ràng buộc dùng tối đa một lần. Nếu chọn duyệt tăng, phải dùng hai mảng `previous[]` và `current[]` tách biệt, thay vì đọc và ghi cùng một mảng.

## 9. Java 17 hoàn chỉnh: bảng 2D, nén 1D và kiểm thử

Chương trình dưới đây được thiết kế tự chứa:
- `Item` lưu ID, trọng lượng và giá trị; trong ví dụ cho phép **trọng lượng nguyên dương** và **giá trị không âm**.
- `solve2D` trả về **giá trị tối ưu** và **một danh sách ID được chọn**, theo quy tắc bỏ khi hòa.
- `solve1D` chỉ tính giá trị tối ưu và quét sức chứa **giảm** để bảo toàn 0/1.
- `brute` là oracle xét mọi tập con trên mẫu nhỏ.
- `verifySmall` kiểm tra **15.080 trường hợp** để phát hiện sai khác giữa DP 2D, DP 1D và brute force.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ZeroOneKnapsackDemo {
    record Item(String id, int weight, long value) {
        Item {
            if (id == null || id.isBlank() || weight <= 0 || value < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }
    }

    record Solution(long maxValue, List<String> chosenIds) {}

    static void checkInput(Item[] items, int capacity) {
        if (items == null || capacity < 0
                || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid input");
        }
        for (Item item : items) {
            if (item == null) {
                throw new IllegalArgumentException("Null item");
            }
        }
    }

    // O(nW) thời gian, O(nW) bộ nhớ; hỗ trợ truy vết.
    static Solution solve2D(Item[] items, int capacity) {
        checkInput(items, capacity);
        int n = items.length;
        long[][] dp = new long[n + 1][capacity + 1];

        for (int i = 1; i <= n; i++) {
            Item item = items[i - 1];
            int weight = item.weight();
            long value = item.value();

            for (int c = 0; c <= capacity; c++) {
                long best = dp[i - 1][c]; // bỏ vật
                if (weight <= c) {
                    long take = Math.addExact(
                            dp[i - 1][c - weight], value);
                    best = Math.max(best, take);
                }
                dp[i][c] = best;
            }
        }

        List<String> reversed = new ArrayList<>();
        int remaining = capacity;
        for (int i = n; i >= 1; i--) {
            Item item = items[i - 1];

            // Khi hòa giá trị tối ưu, ưu tiên bỏ vật.
            if (dp[i][remaining] > dp[i - 1][remaining]) {
                reversed.add(item.id());
                remaining -= item.weight();
            }
        }
        Collections.reverse(reversed);
        return new Solution(dp[n][capacity], reversed);
    }

    // O(nW) thời gian, O(W) bộ nhớ; chỉ trả giá trị.
    static long solve1D(Item[] items, int capacity) {
        checkInput(items, capacity);
        long[] best = new long[capacity + 1];

        for (Item item : items) {
            for (int c = capacity; c >= item.weight(); c--) {
                long take = Math.addExact(
                        best[c - item.weight()], item.value());
                best[c] = Math.max(best[c], take);
            }
        }
        return best[capacity];
    }

    // Oracle vét cạn, chỉ dùng cho mẫu n rất nhỏ.
    static long brute(Item[] items, int capacity) {
        int n = items.length;
        if (n > 20) {
            throw new IllegalArgumentException("Too many items");
        }
        long answer = 0;

        for (int mask = 0; mask < (1 << n); mask++) {
            long totalWeight = 0;
            long totalValue = 0;
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    totalWeight += items[i].weight();
                    totalValue += items[i].value();
                }
            }
            if (totalWeight <= capacity) {
                answer = Math.max(answer, totalValue);
            }
        }
        return answer;
    }

    static int verifySmall() {
        int checked = 0;

        // Mỗi vật có 12 cấu hình:
        // weight thuộc {1,2,3}, value thuộc {0,1,2,3}.
        for (int n = 0; n <= 3; n++) {
            int patterns = 1;
            for (int i = 0; i < n; i++) {
                patterns *= 12;
            }

            for (int code = 0; code < patterns; code++) {
                int remaining = code;
                Item[] items = new Item[n];

                for (int i = 0; i < n; i++) {
                    int choice = remaining % 12;
                    remaining /= 12;
                    items[i] = new Item(
                            "T" + i, 1 + choice / 4, choice % 4);
                }

                for (int capacity = 0; capacity <= 7; capacity++) {
                    long expected = brute(items, capacity);
                    long actual2D = solve2D(
                            items, capacity).maxValue();
                    long actual1D = solve1D(items, capacity);
                    if (actual2D != expected
                            || actual1D != expected) {
                        throw new AssertionError(
                                "items=" + Arrays.toString(items)
                                + " capacity=" + capacity
                                + " expected=" + expected
                                + " 2D=" + actual2D
                                + " 1D=" + actual1D);
                    }
                    checked++;
                }
            }
        }
        return checked;
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item("A", 2, 3),
            new Item("B", 3, 4),
            new Item("C", 4, 5),
            new Item("D", 5, 8)
        };

        Solution c5 = solve2D(items, 5);
        Solution c7 = solve2D(items, 7);

        System.out.println("capacity5=" + c5.maxValue()
                + " picks=" + c5.chosenIds());
        System.out.println("capacity7=" + c7.maxValue()
                + " picks=" + c7.chosenIds());
        System.out.println("dp1D5=" + solve1D(items, 5));
        System.out.println("dp1D7=" + solve1D(items, 7));
        System.out.println("verified=" + verifySmall());
    }
}
~~~

Lưu thành tệp **ZeroOneKnapsackDemo.java**; với **JDK 17 trở lên**, chạy:

~~~bash
javac ZeroOneKnapsackDemo.java
java ZeroOneKnapsackDemo
~~~

**Đầu ra dự kiến chính xác:**

~~~text
capacity5=8 picks=[D]
capacity7=11 picks=[A, D]
dp1D5=8
dp1D7=11
verified=15080
~~~

### Tại sao ví dụ Java dùng long cho giá trị?

Tổng giá trị có thể vượt miền 32-bit `int` khi có nhiều vật, dù từng vật có giá trị nhỏ. Mảng `long[][]` và `long[]` làm tăng miền biểu diễn, còn `Math.addExact` sẽ báo lỗi nếu kết quả vẫn vượt `long`, tránh tràn im lặng trong bước chuyển. Điều này không có nghĩa Java có thể chứa mọi giá trị vô hạn: với số liệu cực lớn phải dùng kiểu số hoặc ràng buộc phù hợp.

`capacity` và trọng lượng vẫn là `int`, vì dùng làm chỉ số mảng theo tài nguyên nguyên. Chương trình từ chối `Integer.MAX_VALUE` để tránh phép `capacity+1` tràn int, nhưng ngay cả W nhỏ hơn giới hạn ấy vẫn có thể **quá lớn để cấp mảng**. Cần kiểm tra giới hạn bộ nhớ của bài và môi trường chạy thực tế.

### Vì sao kiểm thử đúng 15.080 trường hợp?

Mỗi vật được sinh từ 3 lựa chọn trọng lượng và 4 lựa chọn giá trị, nên có **12 cấu hình**. Với n từ 0 đến 3, số dãy cấu hình là:

\[
12^0+12^1+12^2+12^3=1+12+144+1728=1885.
\]

Mỗi dãy được thử với sức chứa từ 0 đến 7, tức **8** giá trị. Tổng số phép đối chiếu là **1885 × 8 = 15.080**. Với mỗi ca, `brute` thử mọi tập con, còn hai lời giải DP trả giá trị; nếu khác nhau sẽ ném `AssertionError`.

Các ca này bao phủ tập rỗng, một vài vật, giá trị bằng 0, vật quá nặng, nhiều vật cùng trọng lượng/giá trị và các trường hợp chính xác ở biên sức chứa. Kiểm thử vét cạn trên miền nhỏ là công cụ QA mạnh, **không thay thế chứng minh quy nạp** cho mọi n và W hợp lệ.

### Tập vật khôi phục có đúng thứ tự không?

`solve2D` duyệt ngược từ vật cuối và ghi ID của những vật thực sự được lấy, rồi gọi `Collections.reverse`. Vì vậy danh sách `chosenIds` có thứ tự như danh sách vật đầu vào. Ví dụ capacity7 được khôi phục là `[A,D]`, không phải `[D,A]`.

Nếu các vật có **ID trùng nhau**, danh sách ID có thể không phân biệt được từng vật; giá trị tối ưu vẫn đúng vì thuật toán dùng **chỉ số mảng**. Nếu cần audit chính xác từng vật trong hệ thống thực, hãy dùng một định danh duy nhất hoặc trả chỉ số ban đầu.

## 10. Phân tích thời gian và bộ nhớ: O(nW) là giả đa thức

Với n vật và sức chứa nguyên W:
- Có **(n+1)(W+1)** ô DP 2D. Mỗi ô xét tối đa hai phương án trong O(1), nên thời gian **O(nW)** nếu n,W đủ lớn.
- Bộ nhớ bảng 2D **O(nW)**; thêm tối đa O(n) ID được chọn trong kết quả.
- Mảng nén 1D có **W+1** ô, dùng **O(W)** bộ nhớ phụ và vẫn **O(nW)** thời gian.
- Brute force duyệt 2^n tập con và xét n vật mỗi lần, nên bản minh họa có **O(n2^n)** thời gian.

Dù trông như một đa thức theo n và W, **O(nW) được gọi là giả đa thức** (*pseudo-polynomial*). Lý do: nếu W được nhập dạng nhị phân, số chữ số cần để biểu diễn W chỉ là O(log W). Khi W rất lớn, duyệt mọi sức chứa 0..W có thể tốn thời gian/memory khổng lồ so với kích thước đầu vào đo bằng số bit.

Ví dụ, n=100 nhưng W=10^9 làm bảng một chiều cần khoảng một tỷ ô, không khả thi với nhiều giới hạn bộ nhớ thông thường. Khi W lớn nhưng **tổng giá trị nhỏ**, đôi khi có thể đổi chiều DP: lưu **trọng lượng nhỏ nhất để đạt một tổng giá trị**. Khi n nhỏ, có thể cân nhắc phương pháp chia đôi tập (*meet-in-the-middle*); khi bài cho phép xấp xỉ, có các kỹ thuật điều chỉnh/thu nhỏ giá trị. Mỗi hướng cần chứng minh và đánh đổi riêng, không phải chỉ thay tên biến rồi áp dụng nguyên mọi công thức.

### Đếm thao tác cần chú ý

Nếu w[i]>W, vật i không thể được lấy trong bất kỳ sức chứa nào tới W. Bản 1D không vào vòng cập nhật của vật đó; bản 2D vẫn sao chép giá trị hàng trước. Các tối ưu bỏ qua vật quá nặng có thể cải thiện hằng số, nhưng không thay đổi cận tổng quát O(nW).

Nếu chỉ cần giá trị tối ưu, 1D thường tiết kiệm nhiều RAM. Nếu cần khôi phục tập vật, bảng 2D đơn giản để giải thích và tin cậy hơn; không nên cố lấy lại vật chỉ từ mảng `best[c]` cuối cùng khi không lưu dữ liệu đủ cho từng giai đoạn.

## 11. Vì sao không thể dùng greedy chung cho 0/1 knapsack?

Một chiến lược trực giác là **ưu tiên vật có tỷ lệ giá trị/trọng lượng cao nhất**. Đây là quy tắc tối ưu cho **fractional knapsack** với giá trị tuyến tính và **được phép lấy một phần vật**, nhưng nói chung **không tối ưu cho 0/1** vì vật không chia nhỏ được.

Phản ví dụ:

| Vật | Trọng lượng | Giá trị | Mật độ |
| --- | ---: | ---: | ---: |
| P | 10 | 60 | 6 |
| Q | 20 | 100 | 5 |
| R | 30 | 120 | 4 |

Với W=50, greedy theo mật độ chọn P rồi Q, dùng 30 đơn vị sức chứa, tổng giá trị **160**. Không còn chỗ để lấy R nguyên vật (trọng lượng 30). Nhưng lựa chọn **Q+R** dùng đúng 50, có giá trị **220**, tốt hơn.

Vì mỗi vật chỉ có hai lựa chọn 0/1, không thể “đổi một phần P thành một phần R” như trong chứng minh tối ưu của fractional knapsack. Các chiến lược ưu tiên **giá trị lớn nhất**, **trọng lượng nhẹ nhất** hoặc **mật độ tốt nhất** đều không có bảo đảm tối ưu chung cho mọi dữ liệu 0/1.

Quy hoạch động không khẳng định mọi tập vật đều cần xét tường minh. Nó dùng nguyên lý **tối ưu của bài toán con** để ghép hai phương án lấy/bỏ và tránh giải lặp cùng trạng thái (i,c). Đây là lý do 0/1 knapsack là một bài mẫu điển hình của DP theo tài nguyên.

## 12. Phân biệt 0/1, unbounded, bounded và fractional

| Biến thể | Mỗi vật/loại có thể lấy | Phương pháp đặc trưng | Điều cần chú ý |
| --- | --- | --- | --- |
| **0/1 knapsack** | Vật i: 0 hoặc 1 lần | DP `dp[i][c]` với lấy/bỏ; 1D quét c giảm | Không được dùng lại vật |
| **Unbounded knapsack** | Mỗi loại: không giới hạn số lần | DP có thể đọc cùng giai đoạn; 1D quét c tăng | Giá trị/weight phải đủ điều kiện để bài toán có nghĩa |
| **Bounded knapsack** | Mỗi loại có số lượng giới hạn | DP theo số lượng; có thể tách nhị phân số lượng | Phải mã hóa giới hạn riêng từng loại |
| **Fractional knapsack** | Lấy phần tỷ lệ từ 0 đến 1 | Greedy theo mật độ giá trị/weight | Giá trị thay đổi tuyến tính theo lượng lấy |

Trong bài **bounded**, nếu một loại có 5 bản sao, đó không phải tự động giống một vật 0/1 có trọng lượng w và giá trị v; ta có thể tạo các bản sao riêng hoặc biểu diễn số lượng bằng nhóm 1,2,2 rồi giải 0/1 trên nhóm, nhưng cách chia nhóm phải **bảo toàn mọi số lượng cho phép**.

Trong bài **unbounded**, nếu có vật trọng lượng 0 và giá trị dương, mục tiêu có thể **không bị chặn trên**, vì có thể lấy vô hạn lần mà không dùng thêm sức chứa. Với bài 0/1, vật có trọng lượng 0 và giá trị dương vẫn chỉ được lấy một lần; thuật toán có thể mở rộng để xử lý nhưng chương trình này chủ động **yêu cầu weight>0** để giữ công thức và các vòng lặp dễ kiểm soát.

## 13. Trường hợp “đúng sức chứa” và trạng thái không thể đạt

Điều kiện của bài chính là `sum(weight) <= W`. Nhưng một số đề yêu cầu `sum(weight) == W`, thường là **exact-fill knapsack**. Khi ấy, `dp[i][c]` có thể được định nghĩa là giá trị lớn nhất để đạt **chính xác** tổng trọng lượng c.

Điểm khác biệt nằm ở khởi tạo:

~~~text
dpExact[0][0] = 0
dpExact[0][c > 0] = -INF   // chưa có cách đạt chính xác c
~~~

Khi chuyển, phải kiểm tra trạng thái nguồn không phải `-INF` trước khi cộng giá trị, nếu không có thể tạo nghiệm giả hoặc làm tràn số. Trong bài này, vì cho phép **không dùng hết sức chứa**, mọi `dp[i][c]` đều có ít nhất nghiệm tập rỗng nên cơ sở toàn 0 là đúng.

Ví dụ với chỉ một vật trọng lượng 3, W=5:
- **At-most capacity:** giá trị tối ưu bằng giá trị của vật 3 vì tổng trọng lượng 3 ≤5.
- **Exact fill:** không có cách dùng các vật để đạt đúng trọng lượng 5, nên trạng thái là không thể đạt.

Không được dùng một công thức/khởi tạo chỉ vì cùng có chữ “knapsack” mà bỏ qua sự khác biệt `<=` với `==`.

## 14. Các trường hợp biên cần kiểm tra

| Đầu vào / tình huống | Kết quả hoặc chính sách đúng |
| --- | --- |
| n=0, W≥0 | Chọn tập rỗng, giá trị 0 |
| W=0, mọi weight>0 | Không thể lấy vật nào, giá trị 0 |
| Một vật nhẹ hơn W | Có thể lấy vật đó nếu đem lại giá trị tốt |
| Một vật weight>W | Vật không thể được lấy |
| Hai vật cùng weight và value | Vẫn là hai vật khác nhau; có thể lấy cả hai nếu vừa túi |
| Vật có value=0 | Thường không cần lấy; quy tắc phá hòa của ví dụ ưu tiên bỏ |
| Vật có weight=0 | Ngoài hợp đồng ví dụ; cần xử lý có chủ đích nếu cho phép |
| W âm hoặc weight âm | Không hợp lệ theo định nghĩa hiện tại |
| Một vật có value rất lớn | Dùng long và kiểm tra tràn tổng |
| Nhiều nghiệm cùng giá trị tối ưu | Trả một nghiệm theo chính sách hòa đã định nghĩa |
| Chỉ có một vật A(2,3), W=4 | Giá trị đúng 3, không được lấy A hai lần |
| W lớn tới hàng tỷ | DP theo W có thể không phù hợp bộ nhớ/thời gian |

### Những lỗi cài đặt phổ biến

**1. Nhầm i với chỉ số vật.** Hàng `dp[i]` biểu diễn **i vật đầu tiên**, nên vật mới có chỉ số `i−1`. Truy cập `items[i]` khi i=n sẽ vượt mảng.

**2. Dùng cùng hàng trong nhánh lấy.** Viết `dp[i][c-w]+v` thay vì `dp[i-1][c-w]+v` có thể dùng cùng vật nhiều lần, giải thành một biến thể khác.

**3. Nén 1D rồi quét c tăng.** Với vật A(2,3), W=4, thuật toán sai trả 6 thay vì 3. Phải quét giảm để đọc các giá trị của giai đoạn trước.

**4. Khởi tạo 0 cho bài yêu cầu exact fill.** Từ trạng thái trọng lượng c không thể đạt, 0 có thể bị hiểu sai thành một nghiệm hợp lệ. Dùng đánh dấu không thể đạt và kiểm tra trước phép cộng.

**5. Quên trường hợp không lấy vật.** Nếu vật hiện tại quá nặng hoặc không có lợi, đáp án có thể giữ `dp[i-1][c]`. Không được luôn cộng giá trị vật đang xét.

**6. Greedy theo tỷ lệ rồi khẳng định tối ưu.** Phản ví dụ P,Q,R với W=50 bác bỏ mệnh đề cho ba lô 0/1.

**7. Dùng kiểu int cho tổng giá trị lớn.** Tổng có thể tràn; dùng long, `Math.addExact` hoặc chính sách số học phù hợp.

**8. Truy vết từ DP 1D cuối cùng như thể còn các hàng trước.** Dữ liệu lịch sử đã bị ghi đè; muốn khôi phục cần lưu quyết định hoặc trạng thái theo từng giai đoạn.

**9. Cho rằng `dp[c]` luôn là giá trị của túi dùng đúng c.** Trong bài at-most, `dp[c]` là tối ưu với sức chứa **tối đa c**; trọng lượng thực có thể nhỏ hơn.

**10. Suy diễn O(nW) là đa thức theo số bit đầu vào.** Đây là chi phí giả đa thức, W quá lớn vẫn không thể cấp mảng.

**11. Quên bản ghi/ID gốc.** Nếu kết quả cần tên hoặc vị trí vật, phải lưu metadata khi định nghĩa vật; danh sách chỉ các giá trị tối ưu không đủ để tái tạo bản ghi nếu không có thông tin phù hợp.

**12. Đếm mọi tập vật tối ưu chỉ bằng một đường truy vết.** Một đường chỉ trả một phương án; đếm tất cả nghiệm tối ưu là bài toán bổ sung và có thể yêu cầu cỡ số lớn.

## 15. Tự kiểm toán công thức và cách kiểm thử

Một cách kiểm toán chất lượng cho bài knapsack:
1. Viết chính xác **`dp[i][c]` nghĩa là gì**, và điều kiện `<=c` hay `==c`.
2. Chứng minh mọi tập vật thuộc **một trong hai nhánh** lấy/bỏ vật i−1.
3. Chỉ cho phép nhánh lấy khi `wi<=c`.
4. Kiểm tra nhánh lấy dùng **i−1 vật trước**, không dùng lại i.
5. Liệt kê các trạng thái cơ sở và miền c hợp lệ.
6. Nếu nén mảng, kiểm tra **chiều duyệt c**; nếu quét tăng cho 0/1, thử ngay vật A(2,3), W=4.
7. Chạy brute force trên n nhỏ để đối chiếu giá trị tối ưu, đặc biệt với vật trùng, value=0, capacity=0, vật quá nặng và nhiều phương án hòa.
8. Nếu khôi phục vật, xác nhận **tổng trọng lượng ≤W**, tổng giá trị đúng `dp[n][W]`, và không lặp chỉ số vật.
9. Kiểm tra kiểu số và bộ nhớ khi W lớn; tránh kết luận từ một dữ liệu mẫu.
10. Ghi rõ mục tiêu tối ưu, phạm vi input và chính sách hòa.

### Kiểm thử brute force độc lập

Với n≤20, ta có thể liệt kê mọi `mask` từ 0 tới `2^n−1`; bit i bằng 1 nghĩa là lấy vật i. Với từng mask:
- Tính `sumWeight` và `sumValue`.
- Chỉ xét nếu `sumWeight<=W`.
- Cập nhật giá trị lớn nhất của những mask hợp lệ.

Oracle này không dùng công thức DP, nên hữu ích để phát hiện lỗi ở DP 2D hoặc ở thứ tự cập nhật 1D. Chương trình Java đã dùng chính cách đối chiếu ấy cho 15.080 bộ kiểm thử nhỏ. Bên cạnh kiểm thử, chứng minh quy nạp bảo đảm tính đúng về mặt thuật toán trên mọi đầu vào hợp lệ trong mô hình số học thích hợp.

## 16. Bài tập tự luyện và đáp án định hướng

**Bài 1 — tính bằng tay.** Các vật A(2,3), B(3,4), C(4,5), D(5,8), sức chứa 5. Tính `dp[4][5]` và nêu các vật được chọn.

*Đáp án:* `dp[4][5]=max(dp[3][5],dp[3][0]+8)=max(7,8)=8`; lấy D.

**Bài 2 — tăng sức chứa.** Cùng dữ liệu, sức chứa 7. Phương án nào tối ưu?

*Đáp án:* Chọn A+D có trọng lượng 2+5=7 và giá trị 3+8=11. Tập B+C có giá trị 9 nên kém hơn.

**Bài 3 — chỉ rõ hai nhánh.** Trạng thái `dp[i][c]` của 0/1 knapsack dựa vào những trạng thái nào? Tại sao không được dùng `dp[i][c-wi]` khi lấy vật?

*Đáp án:* Bỏ dùng `dp[i−1][c]`; lấy (nếu wi≤c) dùng `dp[i−1][c−wi]+vi`. Nếu dùng cùng hàng i, vật i có thể tiếp tục được tính thêm nhiều lần.

**Bài 4 — phản ví dụ nén 1D sai.** Một vật có weight=2, value=3 và W=4. Tại sao duyệt c tăng cho kết quả 6 là sai?

*Đáp án:* Nó đọc `best[2]=3` vừa cập nhật từ chính vật ấy để tạo `best[4]=6`, tức lấy cùng vật hai lần; 0/1 chỉ cho lấy một lần nên đáp án đúng là 3.

**Bài 5 — kiểm tra độ phức tạp.** Với n=100 và W=10^6, bảng 2D và 1D có cỡ bao nhiêu phần tử?

*Đáp án:* Bảng 2D có `(100+1)(1,000,000+1)` ô, xấp xỉ 101 triệu; bảng 1D có `1,000,001` ô. Cả hai vẫn cần khoảng O(nW) thao tác, nhưng bộ nhớ rất khác.

**Bài 6 — đổi điều kiện mục tiêu.** Bài bắt buộc tổng trọng lượng **chính xác** bằng W, chỉ có một vật trọng lượng 3 và W=5. Khởi tạo tất cả trạng thái bằng 0 có đúng không?

*Đáp án:* Sai. Trạng thái exact-fill 5 không thể đạt phải mang dấu **không thể đạt**, không phải 0; cơ sở chỉ có `dp[0][0]=0`, các sức chứa dương không đạt.

**Bài 7 — so với greedy.** Có W=50, các vật P(10,60), Q(20,100), R(30,120). Greedy theo giá trị/trọng lượng trả giá trị bao nhiêu, còn tối ưu 0/1 là bao nhiêu?

*Đáp án:* Greedy lấy P+Q được 160; Q+R được 220 và là tối ưu trên ba vật này.

**Bài 8 — nhiều nghiệm tối ưu.** Có A(2,3), B(2,3), W=2. Giá trị tối ưu bằng bao nhiêu? Có bao nhiêu tập vật chỉ số khác nhau đạt tối ưu?

*Đáp án:* Giá trị tối ưu là 3. Hai tập khác nhau `{A}` và `{B}` đều tối ưu; hàm khôi phục trong ví dụ chỉ chọn một theo chính sách hòa. Nếu đề cần **đếm** nghiệm tối ưu, phải giải thêm bài đếm.

**Bài 9 — nén hay giữ bảng.** Khi nào 1D tốt hơn 2D, và khi nào giữ 2D thuận tiện hơn?

*Định hướng:* Chỉ cần giá trị và W tương đối lớn → 1D tiết kiệm bộ nhớ. Cần khôi phục vật hoặc kiểm tra từng giai đoạn → 2D dễ chứng minh và truy vết. Không dùng 1D để khôi phục tùy tiện khi thiếu lịch sử.

## Ghi nhớ

- **Ba lô 0/1:** mỗi vật chỉ được **lấy hoặc bỏ**, tối đa một lần; mục tiêu là tối đa tổng giá trị với tổng trọng lượng **không vượt quá W**.
- **Trạng thái:** `dp[i][c]` là giá trị tối ưu dùng **i vật đầu** và sức chứa tối đa c.
- **Chuyển:** bỏ vật `dp[i−1][c]`, hoặc lấy vật `dp[i−1][c−wi]+vi` nếu đủ sức chứa; chọn `max`.
- **Chứng minh:** mọi nghiệm thuộc một trong hai nhánh lấy/bỏ và các nhánh bảo toàn tính khả thi; quy nạp trên số vật.
- **Khôi phục:** so giá trị giữa hàng i và i−1 để biết có lấy vật hay không; phá hòa theo quy tắc đã nêu.
- **Nén 1D:** duyệt c **giảm dần**, nhờ vậy `best[c−wi]` còn là giá trị trước khi xử lý vật hiện tại. Duyệt tăng có thể biến thành unbounded knapsack.
- **Độ phức tạp:** O(nW) thời gian, O(nW) bộ nhớ khi giữ bảng hoặc O(W) khi nén. Đây là **giả đa thức** theo W.
- **Không dùng greedy chung:** 0/1 không cho chia nhỏ vật; cần chứng minh chứ không áp quy tắc mật độ của fractional knapsack.
- **Luôn kiểm tra đặc tả:** sức chứa “không vượt” khác “đúng bằng”, mỗi vật một lần khác mỗi loại vô hạn, và ID vật khác với chỉ số cột bảng.
