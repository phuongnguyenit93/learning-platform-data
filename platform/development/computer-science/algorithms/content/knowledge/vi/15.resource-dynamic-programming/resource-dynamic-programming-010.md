# Kiểm soát giới hạn bộ nhớ và lưu vết khi tối ưu bảng

**Tối ưu bộ nhớ trong quy hoạch động (dynamic programming, DP)** là việc giảm số trạng thái cần lưu đồng thời mà **không thay đổi giá trị của đáp án**. Nhưng khi bài toán còn yêu cầu **lưu vết (traceback/reconstruction)** để trả một phương án cụ thể — chẳng hạn những món được chọn trong ba lô, một dãy con chung hoặc đường đi trên lưới — việc nén bảng có thể xóa mất thông tin về các lựa chọn trước đó.

Vì thế, một thiết kế DP tốt phải giải **hai yêu cầu riêng biệt**: (1) tính đúng giá trị tối ưu trong giới hạn thời gian và RAM; (2) có đủ thông tin để khôi phục nghiệm nếu đề bài yêu cầu. Không nên mặc định rằng thuật toán giá trị dùng O(W) bộ nhớ thì thuật toán xuất toàn bộ danh sách lựa chọn cũng dùng O(W) bộ nhớ.

Bài học thuộc phần **Quy hoạch động tài nguyên**, tập trung vào cách tính ngân sách bộ nhớ, nén bảng theo phụ thuộc, lưu quyết định bằng bit, tái tính theo khối, đổi không gian lấy thời gian, và kiểm chứng việc truy vết khi nén trạng thái. Ví dụ chính là **0/1 knapsack**; các ví dụ bổ sung gồm LCS, đường đi lưới và DP theo khoảng.

**Mục tiêu:** phân biệt “chỉ cần giá trị” với “phải xuất một nghiệm”; tính số ô và byte gần đúng trước khi cấp phát; chứng minh hướng duyệt khi nén 2D thành 1D; nhận biết sai lầm của parent pointer gắn trực tiếp lên DP bị ghi đè; cài đặt Java 17+ dùng `long[]` cho giá trị và `BitSet[]` cho quyết định; giải thích khi nào tái tính/checkpoint hoặc Hirschberg phù hợp; đưa ra bộ thử đối chiếu với lời giải vét cạn.

## 1. Xác định đầu ra trước khi tối ưu bộ nhớ

Giả sử bài toán yêu cầu chọn các món với ràng buộc tổng trọng lượng không vượt sức chứa W. Có ít nhất ba hợp đồng đầu ra khác nhau:

1. **Chỉ giá trị tốt nhất:** ví dụ kết quả `11`. Chỉ cần tính tối ưu, không phải kể ra món nào được chọn.
2. **Giá trị và một nghiệm:** ví dụ tổng giá trị `11`, chọn những món có chỉ số `[0,2]`. Thuật toán phải giữ hoặc tái dựng lịch sử lựa chọn.
3. **Tất cả nghiệm tối ưu / số nghiệm tối ưu:** còn nhiều thông tin hơn; một đường truy vết không thể đại diện cho mọi phương án.

Ba yêu cầu này **không tương đương về bộ nhớ**. Mã dùng một mảng `dp[c]` có thể đủ để tìm giá trị, nhưng không tự suy ra được mọi quyết định của từng món. Mặt khác, nếu đề chỉ yêu cầu giá trị, tạo ma trận quyết định có thể là sự lãng phí lớn.

### Bảng phân loại

| Yêu cầu | Dữ liệu cần bảo toàn | Kỹ thuật tham khảo |
|---|---|---|
| Giá trị tối ưu | Các trạng thái mà công thức chuyển còn cần | Rolling array, 1D DP |
| Một phương án | Đường đi từ trạng thái đích về cơ sở hoặc khả năng tính lại đường ấy | Bảng parent/take, checkpoint, divide and conquer |
| Đếm số phương án | Số cách đến mỗi trạng thái; quy tắc tránh đếm trùng | DP đếm, có thể cần modulo/BigInteger |
| Liệt kê tất cả phương án | Thông tin phân nhánh và không gian đầu ra lớn | DAG truy vết, backtracking có kiểm soát |

**Quan trọng:** có thể có nhiều nghiệm cùng giá trị; thuật toán phải xác định quy tắc chọn một nghiệm hoặc chấp nhận trả bất kỳ nghiệm tối ưu hợp lệ. “Trả đúng giá trị” không đủ để xác minh một danh sách món được đưa ra là đúng.

## 2. Ước lượng RAM bằng số ô, kiểu dữ liệu và overhead

Giả sử có n món và sức chứa W. Bảng DP 2D đầy đủ thường có `(n+1)(W+1)` trạng thái. Nếu dùng `long` 8 byte/giá trị, **chỉ phần tử** trong bảng chiếm xấp xỉ:

**`8·(n+1)·(W+1) bytes`.**

Trong Java, `long[][]` là mảng của các tham chiếu tới mảng con, nên còn overhead của mảng ngoài, từng hàng, alignment và tham chiếu. Con số trên **không phải lượng heap chính xác**. Với `boolean[][]` cũng không được mặc nhiên cho rằng Java chỉ dùng một bit cho mỗi boolean.

Nếu chỉ giữ một hàng `long[W+1]`, phần tử chiếm xấp xỉ:

**`8·(W+1) bytes`**.

Nếu cần lưu một quyết định có/không cho mỗi cặp (món, sức chứa), dùng cấu trúc bit nén như `BitSet[]` có thể cần khoảng:

**`n·(W+1)/8 bytes`** ở mức lý tưởng (làm tròn tới số từ máy và cộng overhead).

### Ví dụ quy mô lớn

Với `n=4.000`, `W=100.000`:

- Bảng `long[][]` đầy đủ cần khoảng `8×4001×100001 ≈ 3,20 GB` **chỉ riêng phần tử**.
- Mảng giá trị một chiều cần `8×100001 ≈ 0,80 MB`.
- Lưu một bit quyết định cho mỗi (món,c) cần khoảng `4000×100001/8 ≈ 50,0 MB` dữ liệu bit thô, chưa gồm làm tròn, headers và các cấu trúc khác.

Một ma trận `boolean[][]` không tương đương với ma trận bit nén: số byte mỗi ô và overhead phụ thuộc biểu diễn Java; `BitSet` là lựa chọn rõ ràng khi muốn lưu quyết định dạng bit.

**Đổi đơn vị:** 1 MB thập phân = 1.000.000 byte; 1 MiB = 1.048.576 byte. Đừng nhầm hai đơn vị khi so giới hạn heap. Ngoài bảng DP, cần tính mảng đầu vào, trạng thái truy vết, đối tượng Java, bộ đệm, stack và phần heap khác mà chương trình sử dụng.

### Kiểm tra tràn số khi tính kích thước

Không viết:

~~~java
// Có thể tràn int trước khi kiểm tra.
int numberOfCells = (n + 1) * (capacity + 1);
~~~

Hãy dùng kiểu đủ rộng và kiểm tra trước khi cấp phát:

~~~java
long valueCells = (long) capacity + 1L;
long decisionCells = (long) n * valueCells;
if (capacity < 0 || capacity == Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Invalid capacity");
}
if (decisionCells > 40_000_000L) {
    throw new IllegalArgumentException("Trace budget exceeded");
}
~~~

**Điều kiện kiểm tra chỉ mang tính minh họa:** 40 triệu bit tương đương khoảng 5 MB bit thô; mảng `BitSet[]` và các đối tượng khác dùng thêm RAM. Với hệ thống thực, ngưỡng phải dựa trên ngân sách heap, lượng bộ nhớ đã dùng, số luồng và việc dự phòng cho GC. Không hứa chắc rằng vượt qua ngưỡng sẽ không bao giờ thiếu bộ nhớ.

Đặc biệt, `new long[capacity+1]` có thể tràn khi capacity là `Integer.MAX_VALUE`. Cần kiểm tra ràng buộc **trước** khi tính `capacity+1` ở kiểu int hoặc trước khi tạo mảng.

## 3. Phụ thuộc nào cho phép nén bảng?

Việc tối ưu bộ nhớ bắt đầu từ **đồ thị phụ thuộc trạng thái**:

- Nếu `dp[i]` chỉ đọc `dp[i−1]` và `dp[i−2]`, như Fibonacci, chỉ giữ hai biến.
- Nếu `dp[r][c]` chỉ đọc hàng r−1 và vị trí c−1 của hàng hiện tại, như số đường đi lưới chỉ phải/xuống, có thể dùng một hàng và duyệt c **tăng**.
- Nếu `dp[i][c]` của 0/1 knapsack chỉ đọc **hàng i−1**, có thể dùng một hàng nhưng phải duyệt c **giảm**.
- Nếu `dp[i][j]` của LCS chỉ đọc hàng i−1 và ô trái cùng hàng, có thể dùng hai hàng để tính **độ dài**.

**Quy tắc:** xóa một lớp trạng thái chỉ khi không còn công thức nào cần đọc lớp ấy; đồng thời cần tách riêng câu hỏi “muốn giữ **giá trị** hay muốn truy vết **đường đi**?”.

### Ví dụ hướng duyệt trái ngược

Đối với đếm đường đi lưới, tại thời điểm tính `ways[c]`:

- `ways[c]` cũ là số cách từ **trên**.
- `ways[c−1]` mới là số cách từ **trái** của hàng hiện tại.

Vì cần cột trái **mới**, duyệt c tăng.

Với 0/1 knapsack tại món i và sức chứa c:

- `dp[c]` cũ là giá trị tối ưu **không chọn** món i.
- `dp[c−w[i]]` cũ là giá trị trước khi xét món i, để thêm món i **chỉ một lần**.

Vì cần ô chỉ số nhỏ hơn **chưa được cập nhật**, duyệt c giảm. Hai thứ tự khác nhau xuất phát từ hai định nghĩa trạng thái, không phải từ quy ước đặt tên mảng.

## 4. Trường hợp nghiên cứu: 0/1 knapsack

Cho n món hàng, mỗi món i có trọng lượng nguyên **dương** `w[i]` và giá trị nguyên **không âm** `v[i]`. Mỗi món chọn **tối đa một lần**. Với sức chứa W≥0, tìm giá trị lớn nhất của một tập món có tổng trọng lượng ≤W.

### Định nghĩa trạng thái 2D

**`DP[i][c]` = tổng giá trị tối đa khi chỉ được dùng i món đầu tiên, với sức chứa không vượt c.**

Miền `0≤i≤n`, `0≤c≤W`. Cơ sở `DP[0][c]=0` vì không có món nào để chọn.

Với món thứ i (đánh số từ 1, trọng lượng `w[i−1]`, giá trị `v[i−1]`):

- Nếu `w[i−1]>c`: `DP[i][c]=DP[i−1][c]`.
- Ngược lại:

**`DP[i][c] = max(DP[i−1][c], DP[i−1][c−w[i−1]]+v[i−1])`.**

Hai nhánh là bỏ món cuối hoặc lấy món cuối đúng một lần. Cả hai chỉ được đọc **hàng trước**, không đọc kết quả đã sử dụng cùng món.

### Bảng ví dụ

Cho:

`weights=[2,3,4]`, `values=[4,5,7]`, `W=6`.

| i món / c | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 món | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Sau món 0 (2,4) | 0 | 0 | 4 | 4 | 4 | 4 | 4 |
| Sau món 1 (3,5) | 0 | 0 | 4 | 5 | 5 | 9 | 9 |
| Sau món 2 (4,7) | 0 | 0 | 4 | 5 | 7 | 9 | 11 |

**Giá trị tối ưu:** `DP[3][6]=11`, đạt được khi chọn món có chỉ số **0 và 2**, tổng trọng lượng 2+4=6, tổng giá trị 4+7=11.

Với W=5, đáp án là **9**, chọn món **0 và 1**. Nếu hai tập món có cùng tổng giá trị tối ưu, có thể trả một trong các tập ấy trừ khi đề yêu cầu phá hòa cụ thể.

## 5. Tối ưu thành một mảng để chỉ lấy giá trị

Dùng `dp[c]` biểu diễn giá trị tốt nhất với sức chứa c sau khi đã xử lý số món hiện tại. Khởi tạo tất cả bằng 0. Với mỗi món i, duyệt c **giảm từ W xuống w[i]**:

~~~java
// Mảnh mã trong vòng lặp các món, dùng long[] dp.
for (int c = capacity; c >= weight; c--) {
    dp[c] = Math.max(dp[c], dp[c - weight] + (long) value);
}
~~~

**Bất biến:** trước khi bắt đầu một lượt món, mọi `dp[c]` là `DP[i−1][c]`. Khi xử lý c theo thứ tự giảm, `dp[c−weight]` chưa bị thay trong lượt này vì `c−weight<c`. Như vậy phép cập nhật dùng đúng hàng trước, tạo `DP[i][c]` cho từng c. Sau lượt món, `dp` là hàng i.

### Phản ví dụ cho hướng duyệt sai

Chỉ có **một món** `(w=2,v=4)` và sức chứa W=6.

- Đáp án 0/1 đúng là **4** (không thể dùng món một lần mà có giá trị 8 hay 12).
- Duyệt c **tăng** có thể làm `dp[2]=4`, rồi đọc lại nó để cho `dp[4]=8`, rồi `dp[6]=12` trong **cùng lượt món**.
- Đây là hành vi của bài **unbounded knapsack** (cho phép dùng lại món), không phải 0/1.

**Thời gian:** O(n(W+1)) trong trường hợp xấu; **bộ nhớ:** Θ(W+1) cho mảng giá trị. Nếu W được biểu diễn nhị phân, đây là thuật toán **giả đa thức** (*pseudo-polynomial*), không phải đa thức theo số bit mô tả W.

**Giới hạn:** mảng một chiều trả giá trị `dp[W]`. Nó không tự nói cho ta rằng món thứ i có được chọn ở một sức chứa c nào đó trong một bước trước hay không; bảng đã bị ghi đè qua các lượt.

## 6. Vì sao parent pointer ngây thơ trên 1D DP có thể sai?

Một cách dễ nghĩ nhưng nguy hiểm là đặt `parent[c]=i` mỗi khi món i cải thiện `dp[c]`, rồi lần từ c=W theo các parent pointer để thu món được chọn. Điều này **không luôn đúng** bởi một pointer có thể trỏ tới trạng thái `dp[c−w[i]]` **ở thời điểm trước**, trong khi parent của trạng thái ấy sau đó bị các món khác ghi đè.

Ví dụ với ba món:

`weights=[2,1,1]`, `values=[3,2,2]`, `W=2`.

- Sau món 0: `dp[2]=3` (chọn món 0).
- Sau món 1: `dp[2]` vẫn 3; `dp[1]=2` (chọn món 1).
- Sau món 2: tại c=2, `dp[2]` cải thiện thành 4 nhờ dùng món 2 cộng với `dp[1]=2` **trước lượt món 2**. Vì vậy giá trị 4 ứng với **món 1 và món 2**.
- Nhưng đến c=1 trong cùng lượt món 2, `dp[1]=2` hòa nên không đổi theo quy tắc `candidate>dp[c]`. Trong ví dụ này pointer còn bảo toàn đúng món 1. Tuy nhiên nếu thay đổi cách phá hòa và cập nhật pointer khi bằng nhau, pointer ở c=1 có thể bị đổi thành **món 2** sau khi `dp[2]` đã sử dụng chính món 2. Truy vết `parent[2]→2` rồi `parent[1]→2` sẽ dùng món 2 **hai lần** và vi phạm 0/1.

Vấn đề gốc không chỉ là dấu `>` hay `>=`: con trỏ `parent[c]` **không có chiều thời gian i**, nên không biểu diễn chính xác quyết định tại trạng thái `DP[i][c]`. Có thể thiết kế các dạng parent bền vững hoặc chuỗi nút bất biến, nhưng cách đơn giản nhất để chứng minh đúng là lưu **quyết định theo cả (i,c)** hoặc tái tính những hàng đã mất.

**Kết luận:** đừng cộng tác dụng “truy vết chính xác” cho một mảng chỉ vốn được chứng minh đúng về **giá trị**. Cần một bất biến riêng cho cấu trúc lưu vết.

## 7. Lưu quyết định bằng BitSet: giá trị 1D + truy vết đúng

Để giảm bộ nhớ so với bảng `long[][]` nhưng vẫn trả được món đã chọn, lưu:

- Một mảng giá trị `long[] dp`, dài W+1.
- Một `BitSet` cho mỗi lượt món i, gọi là `take[i]`. Bit c được bật nếu khi xử lý món i tại sức chứa c, **nhánh lấy món i cải thiện nghiêm ngặt giá trị** so với nhánh bỏ.

Cụ thể, trong lượt món i (c giảm):

`candidate = dp[c−w[i]] + v[i]`.

Nếu **`candidate > dp[c]`**, đặt `dp[c]=candidate` và bật `take[i].set(c)`. Nếu bằng nhau, giữ nhánh **bỏ món i** và bit vẫn false. Đây là quy tắc phá hòa của ví dụ; nó tạo đường đi xác định nhưng **không cam kết** danh sách chỉ số nhỏ nhất theo thứ tự từ điển cho mọi đầu vào.

### Truy vết từ món cuối

Sau khi xử lý tất cả n món, bắt đầu `c=W`. Duyệt i từ n−1 về 0:

- Nếu `take[i].get(c)` là true, món i nằm trong **một lời giải tối ưu đã ghi nhận** tại trạng thái (i+1,c). Thêm i vào danh sách, giảm `c -= w[i]`.
- Nếu bit false, trạng thái (i+1,c) lấy giá trị từ hàng trước mà không chọn món i; giữ nguyên c.
- Sau n bước, đảo ngược danh sách vì đã đi từ món cuối về đầu.

Khi chọn món i ở sức chứa c, bit được bật từ công thức đọc **hàng trước** tại c−w[i]. Sau khi giảm c và i, truy vết đúng trạng thái tiền nhiệm tương ứng. Như vậy mỗi món chỉ được xét một lần và không có lỗi dùng lại món.

### Minh họa

Với `weights=[2,3,4]`, `values=[4,5,7]`, W=6:

1. Bắt đầu sau món 2 tại c=6, `take[2].get(6)=true`: chọn món 2, giảm c=2.
2. Sang món 1 tại c=2, trọng lượng 3 quá lớn: không chọn.
3. Sang món 0 tại c=2, `take[0].get(2)=true`: chọn món 0, giảm c=0.

Đảo danh sách thu **`[0,2]`**, trọng lượng 6, giá trị 11.

### Bộ nhớ BitSet

`BitSet` lưu các bit trong những từ 64 bit; `BitSet[]` theo món cần khoảng `n·ceil((W+1)/64)` từ 64 bit nếu cấp phát đủ chiều, cộng overhead từng mảng và đối tượng. Tổng phần lưu giữ:

**`O(W+1 + n·(W+1)/wordBits)`** từ máy, hoặc nói đơn giản là **O(W) giá trị long + O(nW) bit quyết định**.

Nếu quy đổi tất cả về byte, bit nén vẫn có chi phí tăng theo nW, không phải bộ nhớ O(W) cho toàn bộ thuật toán trả nghiệm. Khi n và W cùng lớn, số bit vẫn có thể vượt ngân sách; lúc ấy cần phương án khác.

## 8. Phương án lưu bảng đầy đủ và trade-off

Một cách dễ truy vết hơn là giữ `DP[i][c]` cho tất cả i,c. Sau khi điền, đi lùi:

- Nếu `DP[i][c]==DP[i−1][c]` thì có một nghiệm tối ưu **bỏ món i**; theo quy tắc phá hòa bỏ món khi hòa, chọn nhánh này.
- Ngược lại, nếu món i vừa sức, phải có `DP[i][c]==DP[i−1][c−w[i]]+v[i]`; chọn món i và giảm c.

Bảng này đơn giản để kiểm tra bằng tay và debug, nhưng phải trả chi phí **Θ(nW) ô số**, thường rất lớn.

| Phương án | Lấy giá trị | Trả một nghiệm | Bộ nhớ chính | Thời gian điền |
|---|---|---|---|---|
| Bảng `long[n+1][W+1]` | Có | Có, truy ngược bảng | Θ(nW) số long | O(nW) |
| Rolling `long[W+1]` | Có | Không tự có đường đi | Θ(W) số long | O(nW) |
| Rolling + `BitSet[n]` | Có | Có, truy theo bit (i,c) | Θ(W) long + Θ(nW) bit | O(nW) |
| Snapshot/checkpoint theo khối | Có | Có bằng tái tính | Phụ thuộc kích thước khối | O(nW) với hệ số tăng do tái tính |

Bảng trên xét trường hợp W và n đủ lớn; nếu W=0 hoặc n=0, các mảng/kết quả có thể đơn giản hơn. Đồng thời, mọi phương án cần ít nhất không gian để lưu **đầu vào hoặc đầu ra** tương ứng nếu tính vào tổng bộ nhớ ứng dụng.

## 9. Checkpoint và tái tính: giảm RAM bằng cách làm thêm việc

Nếu bảng quyết định n×W bit vẫn quá lớn, có thể không lưu mọi quyết định. Thay vào đó, chia n món thành các khối có **B món**.

**Lượt tiến:**

1. Chạy DP một chiều qua các món.
2. Lưu **bản sao mảng dp** tại ranh giới giữa những khối, ví dụ sau 0, B, 2B, ... món.
3. Giữ giá trị tối ưu ở cuối để làm điểm bắt đầu truy vết.

**Lượt lùi (theo khối):**

1. Chọn khối cuối cùng chưa truy vết.
2. Từ checkpoint của **đầu khối**, tái tính DP cho tối đa B món trong khối bằng một bảng cục bộ có đủ các hàng.
3. Truy ngược các quyết định trong khối tại sức chứa c hiện tại. Mỗi lần chọn món, giảm c; khi hết khối, chuyển về checkpoint/khối trước.
4. Bỏ bảng cục bộ và tiếp tục khối kế tiếp.

Chỉ khôi phục **một khối tại một thời điểm**, nên không cần bảng 2D cho cả n món.

### Chi phí

- Có khoảng `ceil(n/B)` checkpoint, mỗi checkpoint gồm W+1 giá trị.
- Bảng cục bộ có tối đa `(B+1)(W+1)` giá trị.
- Bộ nhớ bổ sung tính theo số ô số học khoảng:

**`O((W+1)·(ceil(n/B)+B))`**,

cộng đầu vào và danh sách món đã chọn.

- Lượt tiến tính `O(n(W+1))`.
- Mỗi khối tái tính tối đa B hàng, tổng số hàng tái tính trên tất cả khối là O(n), nên truy vết bằng tái tính vẫn dùng **O(n(W+1))** thời gian tổng thể với hệ số hằng tăng (không phải O(n²W) nếu quản lý checkpoint đúng).

Chọn B xấp xỉ `sqrt(n)` làm cho biểu thức `n/B+B` có cùng bậc O(sqrt(n)), giúp đạt khoảng **O(W sqrt(n))** ô trong mô hình trên. Đây là đánh đổi **thời gian và độ phức tạp triển khai** lấy RAM. Nếu một bảng cục bộ cũng quá lớn, có thể tiếp tục chia khối theo nhiều cấp hoặc chọn phương pháp tái dựng khác.

**Cảnh báo:** không chỉ lưu giá trị tối ưu cuối của mỗi khối. Để tái dựng cho **sức chứa c có thể thay đổi** trong lúc đi lùi, checkpoint phải giữ **bảng giá trị cho mọi c** cần đến. Mỗi khối được tái tính đúng từ trạng thái của toàn bộ các món **trước khối**, không được bắt đầu lại bằng tất cả số 0.

## 10. LCS và chiến lược chia để trị để lưu vết

Với hai chuỗi dài m,n, bảng LCS thông thường có `(m+1)(n+1)` ô, công thức:

`LCS[i][j] = LCS[i−1][j−1]+1` nếu hai ký tự cuối bằng nhau, ngược lại lấy `max(LCS[i−1][j], LCS[i][j−1])`.

Nếu **chỉ cần độ dài**, ta có thể lưu hai hàng O(n), hoặc O(min(m,n)) khi chọn chiều cột là chuỗi ngắn hơn. Nhưng để trả chính **chuỗi LCS**, việc bỏ những hàng cũ làm mất chỉ dẫn đi ngược.

Một kỹ thuật kinh điển là **Hirschberg**:

1. Chia một chuỗi tại vị trí giữa.
2. Dùng hai lượt LCS chỉ lưu một hàng: tính điểm LCS cho nửa đầu với mọi tiền tố của chuỗi kia, rồi điểm cho nửa sau với mọi hậu tố của chuỗi kia (có thể tính theo chiều ngược).
3. Chọn một vị trí tách của chuỗi kia sao cho **tổng điểm của hai nửa là lớn nhất**.
4. Đệ quy truy vết LCS cho hai cặp nửa nhỏ, rồi ghép kết quả.

Với cách triển khai cẩn thận, Hirschberg tìm **một LCS** trong **O(mn)** thời gian và khoảng **O(min(m,n))** bộ nhớ làm việc cho các hàng DP (ngoài dữ liệu đầu ra và phần quản lý đệ quy). Không miễn phí: mã phức tạp hơn bảng đầy đủ và phải tính lại nhiều bảng con. Nếu buộc phải tối ưu mọi byte của stack, mảng tạm và kết quả, cần tính thêm phần phụ trợ ấy chứ không chỉ hai hàng DP.

**Điểm chuyển giao:** nén bảng để lấy **giá trị**, rồi dùng một kế hoạch tái tính có cấu trúc để dựng **nghiệm**. Cách này không riêng LCS; ý tưởng tương tự cũng xuất hiện trong checkpoint của 0/1 knapsack và nhiều DP theo dãy.

## 11. Bài toán đường đi lưới: số cách và một đường đi

Với lưới chỉ cho phép đi sang phải hoặc xuống dưới:

- Nếu **chỉ đếm số cách**, có thể cập nhật một mảng `ways[c]` theo hàng, dùng O(C) bộ nhớ.
- Nếu cần **một đường đi hợp lệ** tới đích, việc chỉ lưu số cách của hàng cuối không tự bảo toàn thông tin đường đi trước đó.
- Có thể giữ một bit hướng tiền nhiệm cho mỗi ô có thể đạt tới (ví dụ từ trái hay từ trên) và truy ngược từ đích; hoặc lưu bảng khả thi để truy vết.
- Nếu lưới có chướng ngại, các bit/hướng phải tôn trọng tính khả thi; không được chỉ chọn “đi lên” vì nó đứng trước trong thứ tự mong muốn mà không kiểm tra ô tiền nhiệm có thể đạt tới không.

Với một đường đi trên lưới R×C, đầu ra có thể dài tới R+C−2 bước. **Bộ nhớ đầu ra** này phải được tính riêng nếu đề yêu cầu lưu cả đường đi trong RAM. Có những thuật toán có thể xuất từng bước theo luồng, nhưng cần một chiến lược xác định bước kế tiếp hợp lệ trước khi xuất.

**Đếm nhiều đường đi** khác với **in ra tất cả đường đi**. Số đường đi có thể rất lớn; không thể tuyên bố bộ nhớ/thời gian luôn O(RC) nếu yêu cầu phải liệt kê mọi đường đi.

## 12. Java 17+ hoàn chỉnh: rolling DP và BitSet cho lưu vết

Chương trình sau minh họa hai API riêng:

- `bestValueOnly`: trả **giá trị tối ưu** bằng một mảng `long[]`; không lưu lịch sử.
- `solveWithTrace`: trả giá trị, tổng trọng lượng và **danh sách chỉ số món** (0-based). Dùng cùng công thức một chiều nhưng lưu quyết định tại từng (món,c) bằng `BitSet[]`.

Để tránh gây thiếu bộ nhớ ngoài ý muốn trong bài thực hành, mã có chính sách minh họa: `capacity≤1_000_000` và tổng số bit theo trạng thái `n·(W+1)≤40_000_000` khi lưu vết. **Đây là giới hạn của ví dụ**, không phải giới hạn toán học của DP và không thay thế cấu hình heap thực tế. Hàm giá trị không cần kiểm tra ngân sách bit truy vết vì không cấp phát BitSet[].

**Hợp đồng:** hai mảng trọng lượng và giá trị không null, cùng độ dài; mọi trọng lượng **dương**, mọi giá trị **không âm**; capacity≥0. Mỗi món chọn tối đa một lần. Kết quả của `solveWithTrace` chọn nhánh **bỏ món khi hai nhánh có cùng giá trị**, không cam kết nghiệm nhỏ nhất theo mọi tiêu chí khác.

Lưu tệp **`DpMemoryTraceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.BitSet;
import java.util.Collections;
import java.util.List;

public final class DpMemoryTraceDemo {
    private static final int MAX_CAPACITY = 1_000_000;
    private static final long MAX_TRACE_BITS = 40_000_000L;

    record Solution(
            long bestValue, int totalWeight, List<Integer> indices) {}

    private static void validate(
            int[] weights, int[] values, int capacity) {
        if (weights == null || values == null
                || weights.length != values.length
                || capacity < 0 || capacity > MAX_CAPACITY) {
            throw new IllegalArgumentException("Invalid input or budget");
        }
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weights positive, values nonnegative");
            }
        }
    }

    // Chỉ tính giá trị, không lưu được lịch sử chọn món.
    static long bestValueOnly(
            int[] weights, int[] values, int capacity) {
        validate(weights, values, capacity);
        long[] dp = new long[capacity + 1];

        for (int i = 0; i < weights.length; i++) {
            int weight = weights[i];
            int value = values[i];
            // 0/1: duyệt sức chứa giảm để không dùng món lặp.
            for (int c = capacity; c >= weight; c--) {
                long candidate = dp[c - weight] + value;
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                }
            }
        }
        return dp[capacity];
    }

    // Lưu một bit quyết định cho từng (món, sức chứa).
    static Solution solveWithTrace(
            int[] weights, int[] values, int capacity) {
        validate(weights, values, capacity);

        long bitBudget = (long) weights.length * (capacity + 1L);
        if (bitBudget > MAX_TRACE_BITS) {
            throw new IllegalArgumentException("Trace budget exceeded");
        }

        long[] dp = new long[capacity + 1];
        BitSet[] take = new BitSet[weights.length];

        for (int i = 0; i < weights.length; i++) {
            take[i] = new BitSet(capacity + 1);
            int weight = weights[i];
            int value = values[i];

            for (int c = capacity; c >= weight; c--) {
                long candidate = dp[c - weight] + value;
                // Nếu hòa, giữ nhánh không chọn món i.
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                    take[i].set(c);
                }
            }
        }

        int remaining = capacity;
        List<Integer> indices = new ArrayList<>();

        for (int i = weights.length - 1; i >= 0; i--) {
            if (take[i].get(remaining)) {
                indices.add(i);
                remaining -= weights[i];
            }
        }
        Collections.reverse(indices);

        int totalWeight = capacity - remaining;
        return new Solution(
                dp[capacity], totalWeight, List.copyOf(indices));
    }

    private static void show(String label,
            int[] weights, int[] values, int capacity) {
        Solution result = solveWithTrace(weights, values, capacity);
        long withoutTrace = bestValueOnly(weights, values, capacity);
        if (result.bestValue() != withoutTrace) {
            throw new AssertionError("Value and trace disagree");
        }
        System.out.printf(
                "%s: value=%d, weight=%d, items=%s%n",
                label, result.bestValue(),
                result.totalWeight(), result.indices());
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4};
        int[] values = {4, 5, 7};

        System.out.println("Value only (W=6): "
                + bestValueOnly(weights, values, 6));

        show("Trace (W=6)", weights, values, 6);
        show("Trace (W=5)", weights, values, 5);
        show("Tie (W=1)", new int[] {1, 1},
                new int[] {5, 5}, 1);
        show("Zero capacity", weights, values, 0);
        show("No items", new int[0], new int[0], 5);
    }
}
~~~

Biên dịch và chạy trên **JDK 17 trở lên**:

~~~bash
javac DpMemoryTraceDemo.java
java DpMemoryTraceDemo
~~~

**Đầu ra chính xác:**

~~~text
Value only (W=6): 11
Trace (W=6): value=11, weight=6, items=[0, 2]
Trace (W=5): value=9, weight=5, items=[0, 1]
Tie (W=1): value=5, weight=1, items=[0]
Zero capacity: value=0, weight=0, items=[]
No items: value=0, weight=0, items=[]
~~~

### Phân tích từng trường hợp

**W=6:** món 0 (2,4) và món 2 (4,7) đạt trọng lượng 6 và giá trị 11. Ở bước truy vết, món 2 được chọn tại c=6, rồi món 0 tại c=2, thu chỉ số tăng dần `[0,2]`.

**W=5:** chọn món 0 (2,4) và món 1 (3,5), tổng giá trị 9; món 2 có trọng lượng 4 và giá trị 7 thấp hơn phương án tối ưu.

**Tie:** với hai món `(w=1,v=5)`, W=1, sau món 0 có `dp[1]=5`. Khi xét món 1, candidate=5 bằng giá trị hiện tại nên **không cập nhật**; bit của món 1 tại c=1 giữ false, truy vết chọn món 0. Đây là lựa chọn hợp lệ theo quy tắc phá hòa “bỏ món mới khi hòa”.

**Zero capacity:** mọi món đều có trọng lượng dương, nên W=0 buộc tập chọn rỗng, giá trị 0.

**No items:** n=0, không có món nào để chọn. `BitSet[]` độ dài 0 và mảng dp vẫn hợp lệ; giá trị 0, danh sách rỗng.

### Chứng minh đúng của giải pháp lưu vết

**Giá trị:** tại lượt món i, duyệt c giảm làm `dp[c−w[i]]` mang giá trị của hàng trước, nên công thức chọn/bỏ đúng với 0/1 knapsack. Quy nạp theo số món cho thấy `dp[c]` sau lượt i bằng giá trị tối ưu của i+1 món đầu với sức chứa c.

**Quyết định:** bit `take[i][c]` được bật **chỉ khi** nhánh lấy món i cải thiện nghiêm ngặt giá trị so với nhánh bỏ. Nếu bit false, nhánh bỏ đạt tối ưu (hoặc hòa). Vì vậy mỗi bit mô tả một nhánh tối ưu có thể theo được trong trạng thái tương ứng của hàng i+1.

**Truy vết:** từ trạng thái `(n,W)`, nếu bit i,c true, chuyển về `(i,c−w[i])` và ghi món i; nếu false, chuyển về `(i,c)`. Mỗi bước giảm số món được xét, không có món nào lặp, và các chuyển giữ nguyên tổng giá trị tối ưu khi cộng giá trị món đã chọn. Kết thúc tại hàng 0; danh sách có tổng trọng lượng không vượt W và tổng giá trị đúng bằng `dp[W]`.

**Phá hòa:** dùng so sánh nghiêm ngặt `candidate > dp[c]` để giữ nhánh bỏ khi hòa. Không suy ra đây là cách cho số món ít nhất hay danh sách từ điển nhỏ nhất trong mọi trường hợp; nếu đề có điều kiện phá hòa khác, phải mở rộng trạng thái/so sánh và lưu vết tương ứng.

### Bộ nhớ và giới hạn riêng của mã

- `bestValueOnly`: dùng một `long[W+1]`, bộ nhớ phụ **Θ(W+1)**.
- `solveWithTrace`: ngoài dp, có một `BitSet` cho mỗi món. Bộ nhớ khoảng O(W+1) số long cộng O(n(W+1)) bit, với overhead Java.
- Thời gian hai hàm: **O(n(W+1))** xấu nhất; truy vết cuối thêm O(n).
- Danh sách chỉ số kết quả có nhiều nhất n phần tử và `List.copyOf` tạo bản danh sách không thay đổi qua API.
- Tổng trọng lượng được tính bằng `capacity−remaining`, không cần cộng lại trọng lượng từng món trong kiểu số có thể tràn. Vì remaining luôn từ 0 tới capacity, kết quả là số nguyên hợp lệ.

Giới hạn `MAX_CAPACITY` và `MAX_TRACE_BITS` là **chính sách thực hành**; chúng không phân tích toàn bộ heap. Nếu cần xử lý W lớn hơn, hãy lập ngân sách RAM thực tế trước khi tăng ngưỡng. Không coi `OutOfMemoryError` là cách xử lý bình thường để “thử xem có vừa” vì tiến trình có thể đã chịu áp lực bộ nhớ lớn.

## 13. Kiểm thử độc lập: không chỉ kiểm tra giá trị

Nếu kết quả phải có **danh sách món**, nên kiểm tra **cả giá trị và tính hợp lệ** của danh sách. Một kiểm thử chỉ so `dp[W]` với đáp án chuẩn sẽ không phát hiện được đường truy vết dùng trùng món hoặc vượt sức chứa.

### Các bất biến cần xác nhận

Với đầu ra `Solution(bestValue,totalWeight,indices)`:

1. Mỗi chỉ số thuộc `0..n−1`.
2. Danh sách có chỉ số tăng dần, không có món lặp.
3. Tổng trọng lượng của các món được chọn bằng `totalWeight` và **≤W**.
4. Tổng giá trị của các món được chọn bằng `bestValue`.
5. `bestValue` bằng đáp án tối ưu theo một lời giải độc lập cho đầu vào nhỏ.
6. Nếu n=0 hoặc W=0 với mọi trọng lượng dương, danh sách rỗng và giá trị 0.
7. Khi có giá trị bằng nhau ở hai nhánh, quy tắc “bỏ món đang xét” được phản ánh trong bit quyết định.

### Dùng vét cạn cho đầu vào nhỏ

Với n≤20, có thể liệt kê tối đa `2^n` tập con; mỗi tập con tính tổng trọng lượng và giá trị, bỏ tập vượt W, lấy giá trị lớn nhất. Đây là **oracle** độc lập với DP: cho n nhỏ, nó giúp kiểm chứng giá trị tối ưu.

Ví dụ:

~~~text
weights = [2,3,4]
values  = [4,5,7]
W = 6

Các tập con khả thi:
[] -> 0
[0] -> 4, trọng lượng 2
[1] -> 5, trọng lượng 3
[2] -> 7, trọng lượng 4
[0,1] -> 9, trọng lượng 5
[0,2] -> 11, trọng lượng 6
[1,2] -> vượt W
[0,1,2] -> vượt W

Tối ưu = 11, một nghiệm là [0,2].
~~~

Với n lớn, không dùng vét cạn để chạy sản phẩm vì thời gian tăng theo số tập con; nó chỉ phù hợp để kiểm thử logic trên dữ liệu nhỏ.

### Bộ kiểm thử biên

| Ca thử | Điều cần kỳ vọng |
|---|---|
| Không món nào | Giá trị 0, danh sách rỗng |
| W=0, mọi trọng lượng dương | Giá trị 0, không chọn món |
| Một món vừa sức | Giá trị và chỉ số món đúng |
| Một món quá nặng | Giá trị 0, không chọn |
| Nhiều món bằng giá trị | Tối ưu đúng, tie theo quy ước |
| Nhiều món giá trị 0 | Không bắt buộc chọn món vô ích |
| Món nặng hơn W | Bị bỏ qua mà không truy cập dp sai |
| Sức chứa rất nhỏ so với trọng lượng | Không cập nhật được giá trị |
| Mảng w/v khác độ dài hoặc null | Từ chối theo hợp đồng |
| Trọng lượng 0, âm hoặc giá trị âm | Từ chối theo hợp đồng ví dụ |
| W hoặc n quá lớn so với ngân sách | Kiểm tra trước khi cấp phát BitSet/tables |
| Giá trị lớn và nhiều món | Tổng dùng long, không nhân nhầm kiểu int |

**Kiểm thử ngẫu nhiên:** sinh các mảng có n từ 0 tới 10, trọng lượng 1..8, giá trị 0..12, sức chứa 0..20. Với từng trường hợp, đối chiếu `bestValueOnly` và `solveWithTrace` với vét cạn; kiểm tra tất cả chỉ số được chọn, tổng trọng lượng, tổng giá trị và tính không trùng. Đặc biệt sinh nhiều món có cùng trọng lượng/giá trị để thử quy tắc phá hòa.

## 14. Những ngộ nhận thường gặp

1. **“Nén bảng là vẫn truy vết được như cũ.”** Sai: các hàng cũ đã bị ghi đè; cần dữ liệu quyết định hoặc tái tính.
2. **“Parent[c] là đủ cho 0/1 knapsack.”** Không nói chung: parent không mang chiều thời gian, có thể trỏ tới trạng thái bị ghi đè sau này.
3. **“Chỉ cần dùng dp một chiều cho mọi bài.”** Sai: đồ thị phụ thuộc có thể cần nhiều hàng hoặc dữ liệu không nén được theo hướng ấy.
4. **“Vòng sức chứa đi hướng nào cũng đúng.”** Với 0/1 knapsack phải giảm; với biến thể được dùng lại món, chiều tăng có thể là chủ đích.
5. **“BitSet cho O(W) bộ nhớ cả khi lưu vết.”** Sai: n lượt món × W bit vẫn tăng theo nW.
6. **“boolean[][] tiết kiệm một bit mỗi ô.”** Không có bảo đảm đó trong Java; dùng cấu trúc bit nén khi cần.
7. **“Có giá trị đúng thì danh sách món chắc chắn hợp lệ.”** Sai: truy vết có thể lặp món, vượt sức chứa hoặc không đạt đúng giá trị.
8. **“Lưu một checkpoint chỉ gồm một con số cuối.”** Không đủ để khôi phục một DP ở **mọi sức chứa** trong một khối; cần snapshot các trạng thái có thể dùng.
9. **“Hirschberg chỉ bỏ bảng là tự có đường đi.”** Không: nó dùng các lượt DP xuôi/ngược và chọn điểm tách để tái dựng.
10. **“O(nW) luôn chạy được vì là đa thức.”** W có thể cực lớn dù được biểu diễn bằng vài chục bit; phải xét thời gian và RAM thật.
11. **“Cấp phát theo phép nhân int là an toàn.”** Không: `n*(W+1)` có thể tràn trước khi so ngưỡng; dùng long.
12. **“Giới hạn byte tính từ phần tử là kích thước heap chính xác.”** Không: còn header, alignment, tham chiếu, các đối tượng và bộ nhớ khác.
13. **“Lưu vết không tính vào đầu ra.”** Danh sách một nghiệm có thể dài Θ(n), phải tính chi phí chứa hoặc xuất nó.
14. **“Ties không quan trọng.”** Nếu đề yêu cầu một quy tắc phá hòa, phải mã hóa nó trong chuyển trạng thái và thông tin truy vết.
15. **“Bài đếm số cách và bài tìm một nghiệm có cùng yêu cầu.”** Bài đếm có thể cần giá trị lớn/modulo; một parent pointer không cho số cách.

## 15. Checklist quyết định trước khi triển khai

- Đề cần **giá trị**, **một nghiệm**, **số nghiệm** hay **mọi nghiệm**?
- Trạng thái DP được định nghĩa chính xác chưa? Hướng phụ thuộc của các ô là gì?
- Có thể nén hai chiều xuống một chiều mà vẫn đọc đúng **phiên bản cũ/mới** của ô không?
- Nếu cần nghiệm, ta lưu bảng đầy đủ, bit quyết định, checkpoint hay dùng chia để trị để tái tính?
- Cách truy vết có mang đầy đủ cả **lượt thời gian i** và chỉ số tài nguyên c không?
- Khi hòa, quy tắc chọn nhánh là gì? Cấu trúc lưu vết có giữ đúng quy tắc ấy không?
- Tổng số ô `(n+1)(W+1)`, byte và overhead được ước lượng bằng **long** chưa?
- Có giới hạn heap thực tế, số luồng và bộ nhớ phụ trợ để quyết định ngưỡng an toàn không?
- Đã tính thời gian cả **lượt điền** lẫn **tái tính/truy vết** chưa?
- Đã phân biệt O(nW) theo giá trị W với đa thức theo độ dài bit của W chưa?
- Đã kiểm tra danh sách món thật sự khả thi, không lặp, không quá cân và đạt giá trị tối ưu chưa?
- Với LCS/đường đi, nếu nén hàng để tính giá trị, đã có kế hoạch **dựng lại** chuỗi/đường đi chưa?

**Kết luận:** khi tối ưu bảng DP, phải coi **giá trị tối ưu** và **chứng cứ tạo ra giá trị đó** là hai loại dữ liệu khác nhau. Nén bảng xuống một chiều giúp giảm RAM cho phần giá trị; nếu đề yêu cầu một nghiệm, cần lưu quyết định theo trạng thái, tái tính theo checkpoint hoặc dùng chiến lược chia để trị phù hợp. Phương án đúng không chỉ đạt độ phức tạp đẹp mà còn **vừa bộ nhớ, có thể truy vết chính xác và được kiểm thử bằng một lời giải độc lập**.