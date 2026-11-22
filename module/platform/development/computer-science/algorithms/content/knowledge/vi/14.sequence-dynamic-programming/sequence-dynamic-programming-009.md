# Đan xen hai chuỗi để tạo chuỗi đích

**Đan xen hai chuỗi (interleaving strings)** là bài toán quyết định liệu có thể tạo ra chuỗi đích bằng cách lấy lần lượt các ký tự từ hai chuỗi nguồn, sao cho **thứ tự tương đối của các ký tự trong từng chuỗi nguồn được giữ nguyên**. Ở mỗi bước, ta chọn **một ký tự kế tiếp** từ nguồn thứ nhất hoặc nguồn thứ hai; không được đảo thứ tự trong một nguồn, bỏ ký tự, hoặc dùng lại ký tự đã lấy.

Đây là ví dụ điển hình của **quy hoạch động trên dãy (sequence DP)**: lựa chọn tại một vị trí có thể mơ hồ khi hai chuỗi chứa ký tự giống nhau. Thử tham lam lấy ký tự khớp đầu tiên từ một nguồn có thể đưa tới ngõ cụt dù một cách lựa chọn khác thành công. Quy hoạch động ghi nhớ trạng thái đã tiêu thụ bao nhiêu ký tự của mỗi nguồn, nhờ đó tránh tính lại các nhánh trùng lặp.

**Mục tiêu học tập:** phát biểu đúng điều kiện đan xen; định nghĩa trạng thái `dp[i][j]`, cơ sở và chuyển trạng thái; giải thích thứ tự điền bảng và chứng minh tính đúng; cài đặt bản hai chiều để truy vết một cách đan xen và bản một chiều để giảm bộ nhớ; phân biệt kiểm tra tồn tại với đếm số cách; xử lý trường hợp rỗng, trùng ký tự, dữ liệu Unicode và giới hạn bộ nhớ; chạy ví dụ Java 17+ có đầu ra được kiểm chứng.

## 1. Định nghĩa chính xác bài toán

Cho ba chuỗi `s1`, `s2` và `target`. Đặt `m=s1.length()` và `n=s2.length()`. Hỏi có cách nào tạo ra `target` bằng một chuỗi gồm đúng m ký tự lấy theo thứ tự từ s1 và đúng n ký tự lấy theo thứ tự từ s2 không?

Một cách mô tả tương đương là dùng hai con trỏ:

- Ban đầu `i=0` trên s1, `j=0` trên s2; chưa tạo ký tự nào.
- Để tạo ký tự tiếp theo, có thể lấy `s1[i]` rồi tăng i, hoặc `s2[j]` rồi tăng j, nếu nguồn tương ứng còn ký tự.
- Lựa chọn phải khớp ký tự tiếp theo của target.
- Thành công khi đã tạo **toàn bộ target** và đồng thời `i=m`, `j=n`.

Điều kiện độ dài là:

**`target.length() = m + n`.**

Đây là **điều kiện cần nhưng không đủ**. Đúng độ dài không có nghĩa là thứ tự hoặc các ký tự cũng đúng. Với Java, nên kiểm tra bằng phép cộng kiểu rộng như `(long)m+n` khi cần tránh tràn số nguyên trong biểu thức tính tổng độ dài.

### Ví dụ hợp lệ

`s1="ab"`, `s2="cd"`, `target="acbd"`.

Có thể tạo target theo thứ tự:

| Bước | Ký tự lấy | Nguồn | Đã dùng s1 | Đã dùng s2 |
|---:|---|---|---:|---:|
| 1 | a | s1 | 1 | 0 |
| 2 | c | s2 | 1 | 1 |
| 3 | b | s1 | 2 | 1 |
| 4 | d | s2 | 2 | 2 |

Chuỗi lựa chọn nguồn là **`ABAB`** (A đại diện s1, B đại diện s2). Các ký tự của s1 vẫn có thứ tự a rồi b; của s2 vẫn c rồi d. Vì vậy kết quả là **true**.

### Ví dụ không hợp lệ

`s1="ab"`, `s2="cd"`, `target="adbc"`.

Ba chuỗi có tổng độ dài đúng và **cùng số lượng mỗi ký tự** như nhau, nhưng target yêu cầu d xuất hiện trước c. Trong s2, c phải đứng trước d, nên **không có cách đan xen hợp lệ**. Kết quả là **false**.

Điều này cho thấy kiểm tra bảng tần suất ký tự hay sắp xếp ký tự của ba chuỗi chỉ có thể loại một số trường hợp sai, **không chứng minh được thứ tự**.

### Phân biệt với các bài toán gần tên

- **Interleaving:** dùng tất cả ký tự của mỗi nguồn đúng một lần và giữ nguyên thứ tự trong từng nguồn.
- **Subsequence:** được phép bỏ ký tự trong một dãy nhưng vẫn giữ thứ tự của các ký tự còn lại.
- **Substring:** đoạn ký tự liên tiếp, không được bỏ ký tự ở giữa.
- **Anagram:** có cùng multiset ký tự nhưng không bảo toàn thứ tự từng nguồn.
- **Shuffle/interleave với đảo thứ tự tự do:** nếu cho phép hoán vị trong mỗi nguồn, đó là một bài toán khác.

Thậm chí điều kiện “s1 và s2 đều là subsequence của target” cũng chưa đủ, vì hai subsequence có thể cùng dùng một vị trí của target. Ví dụ `s1="a"`, `s2="a"`, `target="ab"`: riêng từng nguồn đều là subsequence của target, nhưng chỉ có một ký tự a trong target nên không thể dùng cho **cả hai** nguồn.

## 2. Vì sao chọn tham lam có thể sai?

Khi ký tự kế tiếp của **cả hai nguồn** cùng khớp ký tự kế tiếp của target, có hai lựa chọn. Một lựa chọn có thể thành công còn lựa chọn kia thất bại sau vài bước. Nếu thử một lựa chọn rồi **không quay lại**, thuật toán có thể báo false quá sớm.

Ví dụ:

`s1="ab"`, `s2="ac"`, `target="acab"`.

- Ban đầu cả `s1[0]` và `s2[0]` đều bằng 'a'.
- Nếu ưu tiên lấy 'a' từ **s1**, trạng thái sau đó còn s1="b", s2="ac", target còn "cab". Ký tự cần tiếp là c, nhưng cả đầu của s1='b' và s2='a' đều không khớp ⇒ ngõ cụt.
- Nếu lấy 'a' từ **s2**, rồi 'c' từ s2, tiếp theo 'a','b' từ s1 thì tạo được `acab`.

Vậy một cách hợp lệ là **`BBAA`**. Suy luận “cứ lấy s1 nếu s1 khớp” là sai, dù mỗi bước đơn lẻ đều chọn một ký tự đang khớp.

**Kết luận:** phải xét cả hai nhánh khi cả hai khả thi, hoặc lưu đủ thông tin để biết một nhánh có thể dẫn tới lời giải. Dùng DP giúp xử lý các trạng thái lặp mà không tạo cây đệ quy bùng nổ.

## 3. Chọn trạng thái DP theo hai tiền tố

Đặt:

**`dp[i][j] = true` nếu có thể tạo chính xác `target[0..i+j)` bằng cách đan xen `s1[0..i)` và `s2[0..j)`.**

Ở đây `[l,r)` là đoạn chỉ số nửa mở: bao gồm l, không bao gồm r. Hai chỉ số i và j cho biết **số ký tự đã lấy** từ từng nguồn, không phải vị trí ký tự cuối cùng.

- `0≤i≤m`.
- `0≤j≤n`.
- Số ký tự đã tạo từ hai nguồn là i+j.
- Ký tự tiếp theo có chỉ số i+j trong target.
- Ký tự **cuối** của tiền tố target dài i+j (khi i+j>0) có chỉ số **i+j−1**.

### Trạng thái cơ sở

**`dp[0][0]=true`**, bởi hai chuỗi rỗng tạo được tiền tố đích rỗng. Đây là cơ sở quan trọng: nếu đặt false, nhiều trạng thái đầu tiên sẽ không thể trở thành true.

Hàng đầu `dp[0][j]` chỉ được lấy từ s2, vì chưa dùng ký tự nào của s1:

`dp[0][j] = dp[0][j−1] && (s2[j−1] == target[j−1])`.

Cột đầu `dp[i][0]` chỉ được lấy từ s1:

`dp[i][0] = dp[i−1][0] && (s1[i−1] == target[i−1])`.

Có thể dùng cùng một công thức tổng quát kèm điều kiện `i>0`, `j>0` để tự điền hàng và cột biên; không nhất thiết phải viết hai vòng riêng.

### Công thức chuyển trạng thái

Giả sử `i+j>0`, ký tự cuối của tiền tố đích đang xét là:

`wanted = target[i+j−1]`.

Có hai cách để ký tự cuối được tạo ra:

1. **Lấy từ s1:** cần `i>0`, `s1[i−1]==wanted` và phần tiền tố còn lại có thể tạo từ `(i−1,j)`, tức `dp[i−1][j]=true`.
2. **Lấy từ s2:** cần `j>0`, `s2[j−1]==wanted` và phần còn lại có thể tạo từ `(i,j−1)`, tức `dp[i][j−1]=true`.

Công thức:

**`dp[i][j] = (i>0 && dp[i−1][j] && s1[i−1]==wanted) || (j>0 && dp[i][j−1] && s2[j−1]==wanted)`.**

Hai nhánh nối bằng **OR** vì bài toán chỉ hỏi **có tồn tại ít nhất một cách**. Nếu cùng đúng, kết quả vẫn true; không cần phân biệt hai cách trong bảng boolean.

**Đáp án cuối:** `dp[m][n]`. Trả `dp[m][n]` chỉ sau khi bảo đảm target có đúng m+n ký tự. Nếu độ dài khác thì trả false trước khi tạo bảng.

## 4. Thứ tự điền bảng từ dưới lên

`dp[i][j]` chỉ phụ thuộc vào:

- `dp[i−1][j]` ở **hàng trên**, khi i>0.
- `dp[i][j−1]` ở **cột bên trái**, khi j>0.

Vì vậy duyệt **i tăng từ 0 tới m**, bên trong duyệt **j tăng từ 0 tới n** là một thứ tự tô-pô hợp lệ của đồ thị phụ thuộc. Khi cần tính (i,j), cả ô ở hàng trên và ô bên trái đã được tính. Bỏ qua `(0,0)` do nó là cơ sở.

Pseudocode:

~~~text
if length(target) != length(s1) + length(s2):
    return false

create dp[0..m][0..n] initially false
dp[0][0] = true

for i from 0 to m:
    for j from 0 to n:
        if i == 0 and j == 0:
            continue
        wanted = target[i + j - 1]
        fromA = (i > 0) AND dp[i - 1][j] AND s1[i - 1] == wanted
        fromB = (j > 0) AND dp[i][j - 1] AND s2[j - 1] == wanted
        dp[i][j] = fromA OR fromB

return dp[m][n]
~~~

Lưu ý **short-circuit**: khi i=0 không được truy cập `s1[i−1]` hoặc `dp[i−1][j]`; khi j=0 không được truy cập `s2[j−1]`. Trong Java, toán tử `&&` đánh giá từ trái sang phải và dừng khi một toán hạng false, nên biểu thức có kiểm tra `i>0` hoặc `j>0` trước sẽ tránh truy cập chỉ số âm.

## 5. Điền bảng trên một ví dụ nhỏ

Xét lại:

- `s1="ab"`, m=2.
- `s2="cd"`, n=2.
- `target="acbd"`, dài 4.

Bảng `dp[i][j]` có 3 hàng và 3 cột:

| Đã lấy từ s1 / s2 | j=0 | j=1 | j=2 |
|---|---|---|---|
| i=0 | T | F | F |
| i=1 | T | T | F |
| i=2 | F | T | T |

Trong đó T=true, F=false.

Giải thích lần lượt:

- `dp[0][0]=T`: hai tiền tố rỗng tạo được tiền tố rỗng.
- `dp[0][1]=F`: nếu chỉ dùng s2, ký tự đầu là 'c', nhưng target bắt đầu bằng 'a'.
- `dp[1][0]=T`: lấy 'a' từ s1 tạo được target tiền tố "a".
- `dp[1][1]=T`: từ `dp[1][0]=T` lấy 'c' của s2 tạo tiền tố "ac".
- `dp[2][0]=F`: nếu chỉ dùng s1, tiền tố "ab" không bằng tiền tố "ac" của target.
- `dp[2][1]=T`: từ `dp[1][1]=T` lấy 'b' của s1 tạo "acb".
- `dp[2][2]=T`: từ `dp[2][1]=T` lấy 'd' của s2 tạo "acbd".

Các ô còn lại là F. Đường đi tới đích:

`(0,0) → (1,0) → (1,1) → (2,1) → (2,2)`.

Mỗi bước tăng i ứng với lấy từ **A=s1**, mỗi bước tăng j ứng với lấy từ **B=s2**, nên chuỗi nguồn là `ABAB`.

Điều quan trọng là **không xét tất cả 2⁴ chuỗi lựa chọn một cách riêng rẽ**. Những đường đi dẫn tới cùng một trạng thái (i,j) đều có cùng câu hỏi “tiền tố target dài i+j có tạo được không?”, nên chỉ cần ghi một giá trị boolean cho trạng thái đó.

## 6. Chứng minh tính đúng đắn của quy hoạch động

Chứng minh theo thứ tự tăng của `i+j`, hoặc quy nạp theo thứ tự điền bảng. Giả sử target có m+n ký tự.

**Bất biến:** sau khi tính `dp[i][j]`, ô này bằng true **khi và chỉ khi** tiền tố target dài i+j là một phép đan xen hợp lệ của hai tiền tố nguồn dài i và j.

**Cơ sở:** `dp[0][0]=true` chính xác vì hai tiền tố nguồn đều rỗng và tiền tố đích rỗng. Không có cách nào khác cần xét.

**Bước quy nạp:** với i+j>0, bất kỳ phép đan xen hợp lệ nào của hai tiền tố phải có ký tự cuối được lấy từ **s1 hoặc s2**. Nếu từ s1 thì i>0, ký tự ấy phải bằng target[i+j−1], và phần trước phải là phép đan xen hợp lệ của (i−1,j); theo giả thiết quy nạp điều này tương đương `dp[i−1][j]` đúng. Tương tự cho nhánh lấy từ s2 và trạng thái (i,j−1). Hai loại bao phủ mọi khả năng, nên nối bằng OR là **cần và đủ**.

**Duy trì thứ tự:** trạng thái (i−1,j) và (i,j−1) có tổng chỉ số nhỏ hơn i+j, nên được tính trước trong thứ tự đã chọn. Không có phụ thuộc tương lai hoặc chu trình.

**Kết thúc:** `dp[m][n]` đúng khi và chỉ khi có thể dùng trọn vẹn m ký tự của s1 và n ký tự của s2 để tạo target, đúng yêu cầu bài toán. Nếu tổng độ dài khác nhau, không thể dùng hết hai chuỗi mà tạo ra target, nên trả false là đúng.

Chứng minh này cũng giải thích vì sao **không được thử một nhánh rồi kết luận false ngay** khi nhánh đó đi vào ngõ cụt: giá trị của trạng thái là OR của **tất cả nhánh cuối hợp lệ**, không phải chỉ một nhánh được chọn theo trực giác.

## 7. Phân tích thời gian và bộ nhớ

Bảng có `(m+1)(n+1)` ô. Mỗi ô kiểm tra tối đa hai chuyển trạng thái, mỗi chuyển chỉ làm một số hữu hạn phép so sánh ký tự và đọc ô boolean.

- **Thời gian xấu nhất:** `O((m+1)(n+1))`, thường viết **O(mn)** khi m,n đều dương và đủ lớn.
- **Bộ nhớ:** `Θ((m+1)(n+1))` cho bảng `boolean[][]`, ngoài bộ nhớ của ba chuỗi đầu vào.
- **Trường hợp m=0 hoặc n=0:** bảng có một hàng/cột, công việc tỷ lệ với độ dài chuỗi còn lại. Đây là lý do biểu thức `(m+1)(n+1)` chính xác hơn ký hiệu mn nếu có chuỗi rỗng.
- **Kiểm tra độ dài:** chỉ cần O(1) thao tác để biết độ dài String trong Java (không cần quét lại nội dung), nên có thể trả false ngay nếu độ dài không khớp.
- **Trường hợp có nhiều ký tự giống nhau:** vẫn có tối đa một giá trị boolean cho mỗi cặp (i,j), vì vậy số trạng thái không bùng nổ theo số cách đan xen.

**Không nhầm công thức bộ nhớ lý thuyết với số byte Java:** `boolean[][]` chứa nhiều mảng con và overhead đối tượng; lượng RAM thực có thể lớn hơn `(m+1)(n+1)` byte. Với chuỗi nguồn rất dài, bảng 2D có thể vượt heap; bản nén ở phần sau giúp giảm bộ nhớ.

### Vì sao không chọn đệ quy thuần khi m,n lớn?

Một cách thử trực tiếp cả hai nguồn tại mỗi bước có thể sinh rất nhiều nhánh, nhất là khi các ký tự trùng nhau và nhiều tiền tố cùng khớp. Các đường khác nhau có thể dẫn về cùng trạng thái (i,j), khiến bài toán con bị giải lặp.

Ghi nhớ kết quả của cặp (i,j) trong **top-down memoization** cũng giảm số trạng thái phải giải xuống O((m+1)(n+1)), nhưng còn dùng stack đệ quy có thể sâu tới m+n. Bottom-up dùng vòng lặp rõ thứ tự; nó có thể tính cả những ô không cần tới đáp án, song không có nguy cơ tràn stack do đệ quy.

## 8. Nén bảng 2D còn một chiều

Để chỉ kiểm tra tồn tại, không cần giữ toàn bộ bảng. Công thức `dp[i][j]` chỉ đọc:

- `dp[i−1][j]`: ô ở hàng trước **cùng cột**.
- `dp[i][j−1]`: ô đã tính ở hàng hiện tại **cột trái**.

Dùng mảng một chiều `reachable[j]`. Duyệt i tăng và với mỗi i duyệt j **tăng từ trái sang phải**.

Tại thời điểm xử lý cột j trong hàng i:

- `reachable[j]` **trước khi ghi đè** chứa `dp[i−1][j]`.
- `reachable[j−1]` **đã cập nhật** chứa `dp[i][j−1]`.

Vì vậy công thức một chiều đúng là:

`newReachable[j] = (oldReachable[j] && s1[i−1]==wanted) || (newReachable[j−1] && s2[j−1]==wanted)`.

Cần xử lý hàng i=0, cột j=0 tách khỏi các ô nội bộ.

~~~java
// Phương thức minh họa, cần đặt bên trong một lớp Java.
static boolean canInterleave1D(String s1, String s2, String target) {
    if ((long) s1.length() + s2.length() != target.length()) {
        return false;
    }

    int m = s1.length(), n = s2.length();
    boolean[] reachable = new boolean[n + 1];
    reachable[0] = true;

    // Hàng 0: chỉ lấy từ s2.
    for (int j = 1; j <= n; j++) {
        reachable[j] = reachable[j - 1]
                && s2.charAt(j - 1) == target.charAt(j - 1);
    }

    for (int i = 1; i <= m; i++) {
        // Cột 0: chỉ lấy từ s1.
        reachable[0] = reachable[0]
                && s1.charAt(i - 1) == target.charAt(i - 1);

        for (int j = 1; j <= n; j++) {
            char wanted = target.charAt(i + j - 1);
            boolean fromFirst = reachable[j]
                    && s1.charAt(i - 1) == wanted;
            boolean fromSecond = reachable[j - 1]
                    && s2.charAt(j - 1) == wanted;
            reachable[j] = fromFirst || fromSecond;
        }
    }
    return reachable[n];
}
~~~

Kết quả chính xác như bản 2D nếu dùng cùng định nghĩa trạng thái. **Thời gian O((m+1)(n+1))**, **bộ nhớ O(n+1)**. Vì bài toán kiểm tra tồn tại là đối xứng theo hai nguồn, có thể **hoán đổi vai trò s1 và s2** sao cho chiều làm cột là chuỗi ngắn hơn; khi đó bộ nhớ **O(min(m,n)+1)**. Mã độc lập ở phần 11 thực hiện phép hoán đổi này.

### Vì sao cột phải đi từ trái sang phải?

Nếu đi từ phải sang trái, `reachable[j−1]` có thể còn là **giá trị hàng cũ**, không phải `dp[i][j−1]` của hàng hiện tại. Công thức khi ấy dùng sai phiên bản trạng thái.

Phản ví dụ cho một cách cập nhật một chiều đi **j giảm** nhưng vẫn dùng công thức trên:

`s1="x"`, `s2="b"`, `target="ab"`.

Không có cách nào tạo 'a' đầu tiên, nên đáp án đúng là false. Sau khi khởi tạo hàng 0, `reachable[0]=true` và `reachable[1]=false`. Nếu cập nhật j=1 trước j=0, phép đọc **`reachable[0]=true` của hàng 0** có thể làm nhánh “lấy b từ s2” thành true cho ô (1,1), dù ở hàng i=1, cột 0 thực ra phải là false. Duyệt đúng **j tăng** sẽ tính cột 0 trước và không mắc lỗi ấy.

**Quy tắc tổng quát:** khi nén một bảng DP, phải biết mỗi ô đọc giá trị của **lớp cũ hay lớp mới**. Hướng duyệt không phải chi tiết trang trí; nó là một phần của chứng minh tính đúng.

## 9. Truy vết một cách đan xen hợp lệ

Nếu đề yêu cầu không chỉ true/false mà còn **nguồn của từng ký tự**, bảng 2D rất thuận tiện. Từ `(m,n)` khi `dp[m][n]=true`, ta đi ngược về `(0,0)`:

1. Với ký tự `wanted=target[i+j−1]`, nếu `i>0`, `s1[i−1]==wanted` và `dp[i−1][j]=true`, ta có thể nói ký tự cuối được lấy từ s1. Ghi 'A' rồi giảm i.
2. Nếu nhánh A không hợp lệ mà `j>0`, `s2[j−1]==wanted` và `dp[i][j−1]=true`, ghi 'B' rồi giảm j.
3. Tiếp tục đến `(0,0)`; sau đó **đảo ngược** chuỗi A/B đã ghi.

Mỗi bước đi ngược giảm i+j đúng một đơn vị. Vì chỉ chọn một **tiền nhiệm có dp=true**, đường đi luôn duy trì tính khả thi. Sau đúng m+n bước, ta tới cơ sở.

**Khi cả hai nhánh đúng:** có thể chọn bất kỳ nhánh nào để lấy **một** cách hợp lệ. Mã ví dụ ưu tiên A khi truy vết **từ cuối về đầu**. Kết quả là xác định với đầu vào cho trước, nhưng **không được khẳng định nó là chuỗi A/B nhỏ nhất theo thứ tự từ điển theo chiều thuận**. Muốn có đường đi ưu tiên A từ đầu tới cuối mà vẫn bảo đảm hoàn thành, nên tính thêm thông tin khả thi từ trạng thái hiện tại tới đích, rồi tham lam theo thứ tự đó.

Ví dụ `s1="ab"`, `s2="cd"`, `target="acbd"`, truy vết cho `ABAB`. Với `s1="aa"`, `s2="aa"`, `target="aaaa"`, các ký tự nguồn giống nhau nên nhiều cách hợp lệ. Quy tắc ưu tiên A khi **truy vết ngược** trong chương trình sẽ chọn `BBAA`, không phải vì các ký tự A/B của target có thứ tự duy nhất.

**Đánh đổi bộ nhớ:** để truy vết đơn giản, bảng 2D dùng O(mn) ô và chuỗi lựa chọn dài m+n. Nếu dùng bản 1D chỉ lưu boolean của hàng hiện tại, những tiền nhiệm thuộc hàng cũ đã bị ghi đè; không thể tùy tiện đi ngược bằng mảng một chiều. Có thể lưu thêm hướng đi, tính lại một phần bảng hoặc dùng kỹ thuật truy vết tiết kiệm bộ nhớ có thiết kế riêng.

## 10. Phân biệt kiểm tra tồn tại và đếm số cách

Bài toán boolean hỏi **có ít nhất một cách** tạo target hay không. Một mở rộng khác hỏi **bao nhiêu chuỗi lựa chọn A/B** tạo được target.

Định nghĩa `ways[i][j]` là số cách phân bổ i+j vị trí đầu của target cho i ký tự đầu của s1 và j ký tự đầu của s2. Cơ sở:

`ways[0][0]=1` — có đúng một cách dùng hai tiền tố rỗng để tạo chuỗi rỗng.

Với i+j>0:

**`ways[i][j] = (s1[i−1]==wanted ? ways[i−1][j] : 0) + (s2[j−1]==wanted ? ways[i][j−1] : 0)`**,

trong đó mỗi nhánh chỉ xét khi chỉ số nguồn hợp lệ. Đây là **phép cộng**, không phải OR. Nếu cả hai nhánh cho kết quả hợp lệ, cả hai đóng góp số cách.

### Trùng ký tự và khác biệt giữa cách gán nguồn và chuỗi đích

Ví dụ `s1="aa"`, `s2="aa"`, `target="aaaa"`:

- Kết quả boolean: **true**.
- Số cách chọn 2 trong 4 vị trí đích cho s1 là `C(4,2)=6`, nên số **chuỗi nguồn A/B** hợp lệ là **6**.
- Nhưng chỉ có **một chuỗi đích cụ thể** là "aaaa". Đếm cách gán nguồn **không đồng nghĩa** đếm số chuỗi đích khác nhau.

Nếu cần số cách chính xác cho chuỗi dài, kết quả có thể rất lớn; dùng `BigInteger` hoặc một modulo theo hợp đồng bài. Đếm bằng long có thể tràn. Khi dùng `BigInteger`, số trạng thái vẫn O((m+1)(n+1)) nhưng **chi phí phép cộng** phụ thuộc số bit của số cách, không được mặc định là thời gian O(1) theo mô hình bit.

**Không đổi boolean thành đếm bằng cách cộng true/false rồi kết luận cùng bài toán.** Đếm số cách thường cần giữ cả hai nhánh, kể cả khi đã tìm thấy một cách thành công; còn để kiểm tra tồn tại, chỉ một nhánh true đã đủ cho trạng thái.

## 11. Java 17+ hoàn chỉnh: bảng 2D, truy vết, nén 1D và đếm

Chương trình dưới đây có ba hàm chính:

- `interleaveWithPath`: dùng bảng 2D, trả `possible` và chuỗi lựa chọn A/B khi có lời giải. Ưu tiên nhánh A khi truy vết ngược.
- `canInterleaveCompact`: chỉ kiểm tra tồn tại, dùng mảng boolean 1D; hoán đổi hai nguồn về mặt nội bộ để chiều cột ngắn hơn. Vì chỉ trả boolean nên việc hoán đổi không làm thay đổi kết quả.
- `countAssignments`: đếm số cách gán nguồn bằng `BigInteger`, không làm mất các cách khác nhau khi hai ký tự bằng nhau.

**Hợp đồng:** ba chuỗi không được null; nếu null, hàm ném `IllegalArgumentException`. Mọi kiểm tra ký tự dùng `String.charAt` và `String.length`, tức **đơn vị mã UTF-16**. Chuỗi rỗng hợp lệ. Khi độ dài target không bằng tổng độ dài nguồn, kết quả tồn tại false hoặc số cách 0 được trả ngay.

Lưu tệp **`InterleavingStringsDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public final class InterleavingStringsDemo {
    record Answer(boolean possible, String choices) {}

    private static void requireStrings(String a, String b, String target) {
        if (a == null || b == null || target == null) {
            throw new IllegalArgumentException("Null string");
        }
    }

    // Bản 2D: kiểm tra tồn tại và trả một chuỗi nguồn A/B.
    static Answer interleaveWithPath(
            String a, String b, String target) {
        requireStrings(a, b, target);
        int m = a.length();
        int n = b.length();
        if ((long) m + n != target.length()) {
            return new Answer(false, "");
        }

        boolean[][] dp = new boolean[m + 1][n + 1];
        dp[0][0] = true;

        for (int i = 0; i <= m; i++) {
            for (int j = 0; j <= n; j++) {
                if (i == 0 && j == 0) {
                    continue;
                }

                char wanted = target.charAt(i + j - 1);
                boolean fromA = i > 0
                        && dp[i - 1][j]
                        && a.charAt(i - 1) == wanted;
                boolean fromB = j > 0
                        && dp[i][j - 1]
                        && b.charAt(j - 1) == wanted;
                dp[i][j] = fromA || fromB;
            }
        }

        if (!dp[m][n]) {
            return new Answer(false, "");
        }

        StringBuilder reverseChoices = new StringBuilder();
        int i = m, j = n;
        while (i > 0 || j > 0) {
            char wanted = target.charAt(i + j - 1);
            if (i > 0 && dp[i - 1][j]
                    && a.charAt(i - 1) == wanted) {
                reverseChoices.append('A');
                i--;
            } else if (j > 0 && dp[i][j - 1]
                    && b.charAt(j - 1) == wanted) {
                reverseChoices.append('B');
                j--;
            } else {
                throw new AssertionError("Broken DP predecessor");
            }
        }
        return new Answer(true, reverseChoices.reverse().toString());
    }

    // Bản 1D: chỉ kiểm tra tồn tại, bộ nhớ O(min(m,n)+1).
    static boolean canInterleaveCompact(
            String a, String b, String target) {
        requireStrings(a, b, target);
        if ((long) a.length() + b.length() != target.length()) {
            return false;
        }

        // Chỉ trả boolean nên đổi vai hai nguồn không đổi đáp án.
        if (b.length() > a.length()) {
            String temporary = a;
            a = b;
            b = temporary;
        }

        int m = a.length();
        int n = b.length();
        boolean[] reachable = new boolean[n + 1];
        reachable[0] = true;

        // i=0: chỉ dùng b.
        for (int j = 1; j <= n; j++) {
            reachable[j] = reachable[j - 1]
                    && b.charAt(j - 1) == target.charAt(j - 1);
        }

        for (int i = 1; i <= m; i++) {
            reachable[0] = reachable[0]
                    && a.charAt(i - 1) == target.charAt(i - 1);

            for (int j = 1; j <= n; j++) {
                char wanted = target.charAt(i + j - 1);
                boolean fromA = reachable[j]
                        && a.charAt(i - 1) == wanted;
                boolean fromB = reachable[j - 1]
                        && b.charAt(j - 1) == wanted;
                reachable[j] = fromA || fromB;
            }
        }
        return reachable[n];
    }

    // Đếm những cách gán vị trí đích cho nguồn A/B.
    static BigInteger countAssignments(
            String a, String b, String target) {
        requireStrings(a, b, target);
        int m = a.length();
        int n = b.length();
        if ((long) m + n != target.length()) {
            return BigInteger.ZERO;
        }

        BigInteger[][] ways = new BigInteger[m + 1][n + 1];
        for (BigInteger[] eachRow : ways) {
            Arrays.fill(eachRow, BigInteger.ZERO);
        }
        ways[0][0] = BigInteger.ONE;

        for (int i = 0; i <= m; i++) {
            for (int j = 0; j <= n; j++) {
                if (i == 0 && j == 0) {
                    continue;
                }

                char wanted = target.charAt(i + j - 1);
                BigInteger total = BigInteger.ZERO;
                if (i > 0 && a.charAt(i - 1) == wanted) {
                    total = total.add(ways[i - 1][j]);
                }
                if (j > 0 && b.charAt(j - 1) == wanted) {
                    total = total.add(ways[i][j - 1]);
                }
                ways[i][j] = total;
            }
        }
        return ways[m][n];
    }

    private static void show(
            String label, String a, String b, String target) {
        Answer full = interleaveWithPath(a, b, target);
        boolean compact = canInterleaveCompact(a, b, target);
        if (full.possible() != compact) {
            throw new AssertionError("2D and 1D disagree");
        }

        String choices = full.possible() ? full.choices() : "-";
        System.out.printf(
                "%s: %s | choices=\"%s\" | compact=%s%n",
                label, full.possible(), choices, compact);
    }

    public static void main(String[] args) {
        show("Classic valid", "aabcc", "dbbca", "aadbbcbcac");
        show("Classic invalid", "aabcc", "dbbca", "aadbbbaccc");
        show("Alternating", "ab", "cd", "acbd");
        show("Order violated", "ab", "cd", "adbc");
        show("Repeated chars", "aa", "aa", "aaaa");
        show("Both empty", "", "", "");
        show("Second only", "", "abc", "abc");
        show("Length mismatch", "ab", "cd", "abc");

        System.out.println("Repeated chars assignments: "
                + countAssignments("aa", "aa", "aaaa"));
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac InterleavingStringsDemo.java
java InterleavingStringsDemo
~~~

**Đầu ra chuẩn (chính xác các dòng và thứ tự):**

~~~text
Classic valid: true | choices="AABBBBAABA" | compact=true
Classic invalid: false | choices="-" | compact=false
Alternating: true | choices="ABAB" | compact=true
Order violated: false | choices="-" | compact=false
Repeated chars: true | choices="BBAA" | compact=true
Both empty: true | choices="" | compact=true
Second only: true | choices="BBB" | compact=true
Length mismatch: false | choices="-" | compact=false
Repeated chars assignments: 6
~~~

### Đọc kết quả và kiểm chứng

- **Classic valid:** `s1="aabcc"`, `s2="dbbca"`, `target="aadbbcbcac"`. Có cách hợp lệ với chuỗi chọn nguồn `AABBBBAABA`: dùng mọi ký tự của mỗi nguồn đúng thứ tự, tạo đúng target.
- **Classic invalid:** `"aadbbbaccc"` không thể tạo bởi cùng hai nguồn mà giữ thứ tự của từng nguồn; cả hai cách kiểm tra trả false.
- **Alternating:** `"ab"` và `"cd"` tạo `"acbd"` bằng `ABAB`.
- **Order violated:** `"adbc"` buộc 'd' của nguồn s2 đứng trước 'c', trái thứ tự nguồn; kết quả false.
- **Repeated chars:** cả hai nguồn `"aa"` có các ký tự như nhau. Bản 2D trả một đường đi `BBAA` do ưu tiên A trong quá trình **truy vết ngược**. Bản 1D chỉ cần trả true. Hàm đếm cho 6 cách gán nguồn, không phải 6 target khác nhau.
- **Both empty:** hai nguồn rỗng tạo target rỗng, có một cách gán nguồn rỗng; chuỗi choices cũng rỗng.
- **Second only:** với s1 rỗng và s2="abc", phải chọn cả ba ký tự từ nguồn B, nên choices là `BBB`.
- **Length mismatch:** 2+2 khác 3, nên cả hai cách trả false trước khi cấp phát bảng.

**Độ phức tạp của mã:** bản 2D dùng `O((m+1)(n+1))` thời gian và bộ nhớ, cộng O(m+n) cho truy vết/chuỗi choices. Bản compact dùng thời gian cùng bậc và **O(min(m,n)+1)** bộ nhớ. Bản countAssignments cũng có `(m+1)(n+1)` trạng thái và bộ nhớ chứa những số nguyên lớn; tổng chi phí số học phụ thuộc độ dài bit của số cách.

## 12. Trường hợp biên quan trọng

| Trường hợp | s1, s2, target | Kết quả | Giải thích |
|---|---|---|---|
| Cả hai nguồn rỗng, đích rỗng | `"","", ""` | true | Cơ sở `dp[0][0]` |
| Một nguồn rỗng | `"","abc","abc"` | true | Đích phải trùng hẳn nguồn còn lại |
| Một nguồn rỗng nhưng đích khác | `"","abc","acb"` | false | Không được đảo thứ tự |
| Độ dài không bằng tổng | `"ab","cd","abc"` | false | Không dùng hết hai nguồn |
| Đan xen luân phiên | `"ab","cd","acbd"` | true | Lựa chọn `ABAB` |
| Tập ký tự đúng nhưng thứ tự sai | `"ab","cd","adbc"` | false | 'd' đứng trước 'c' của nguồn s2 |
| Nhiều nguồn cùng khớp một ký tự | `"aa","aa","aaaa"` | true | Có 6 chuỗi gán nguồn |
| Cần chọn đúng nhánh khi hòa | `"ab","ac","acab"` | true | BBAA hợp lệ; tham lam A trước thất bại |
| Hai nguồn mỗi nguồn một ký tự giống | `"a","a","aa"` | true | Có 2 chuỗi nguồn AB hoặc BA |
| Có một ký tự dùng không đủ lần | `"a","a","ab"` | false | Đích thiếu một chữ 'a' |
| Một nguồn có ký tự lặp | `"aaa","b","abaa"` | true | Chọn A, B, A, A |
| Đích chỉ là đảo thứ tự của một nguồn | `"abc","","cba"` | false | Không được đảo nguồn |
| Tất cả chỉ là chữ số/Unicode code unit | `"12","34","1324"` | true | Thuật toán không giới hạn bảng chữ cái |
| Chuỗi rất dài | Độ dài lớn bất kỳ | Phụ thuộc RAM | Bảng 2D có tích kích thước rất lớn |

**Phân biệt điều kiện cần và đủ:** đúng tổng độ dài, cùng tần suất ký tự toàn cục và mỗi nguồn là subsequence của target đều là những dấu hiệu có thể dùng để loại trừ một số đầu vào. Nhưng để xác nhận có một cách phân bổ **không chồng lấn** bảo toàn thứ tự cả hai nguồn, cần lời giải đúng như DP hoặc một phương pháp tương đương.

## 13. Kiểm thử độc lập và kiểm thử ngẫu nhiên

Một chiến lược kiểm thử có giá trị là so sánh ba cách tiếp cận cho các chuỗi ngắn:

1. **Vét cạn:** từ trạng thái (i,j), thử lấy ký tự kế tiếp từ s1 hoặc s2 nếu khớp, đến khi dùng hết cả hai. Không memo hóa để thuật toán tham chiếu có cấu trúc khác bản tabulation, nhưng chỉ áp dụng cho chuỗi rất ngắn vì số nhánh tăng nhanh.
2. **DP hai chiều:** dùng công thức chuẩn và kiểm tra giá trị `dp[m][n]`.
3. **DP một chiều:** kiểm tra kết quả boolean bằng bảng nén, đặc biệt với m=0, n=0 hoặc một nguồn dài hơn nguồn kia.

Sau khi bản 2D trả choices, **tái tạo target** từ choices và hai con trỏ nguồn để xác nhận:

- Choices có đúng m chữ A và n chữ B.
- Các chữ A đọc từ s1 theo thứ tự; chữ B đọc từ s2 theo thứ tự.
- Chuỗi vừa tạo đúng target, không thiếu hay thừa ký tự.

Với n,m nhỏ (ví dụ mỗi nguồn có độ dài 0..5), có thể sinh nhiều chuỗi trên bảng chữ cái `{a,b}` để tạo những tình huống trùng ký tự và hòa lựa chọn. Nên cố tình sinh cả target có độ dài sai, target có multiset đúng nhưng thứ tự sai, và target thực sự tạo bằng một đường đi A/B ngẫu nhiên.

Để kiểm chứng hàm **đếm**, với chuỗi ngắn có thể liệt kê mọi chuỗi nguồn A/B gồm m ký tự A, n ký tự B, dựng chuỗi đích tương ứng, đếm bao nhiêu chuỗi nguồn khớp target, rồi so với `ways[m][n]`. Với `"aa","aa","aaaa"` phải đếm đúng 6.

**Không dùng sự đồng ý của hai phiên bản DP làm chứng minh duy nhất.** Nếu cả hai cùng dùng công thức sai, chúng có thể cùng trả một đáp án sai. Một bộ kiểm thử tham chiếu độc lập hoặc chứng minh quy nạp sẽ tạo bằng chứng mạnh hơn.

## 14. Những lỗi phổ biến và cách tránh

1. **Chỉ kiểm tra độ dài hoặc tần suất:** đúng tập ký tự không có nghĩa thứ tự trong mỗi nguồn được bảo toàn.
2. **Chọn tham lam khi hai nguồn cùng khớp:** thử nguồn thứ nhất trước rồi bỏ luôn nguồn thứ hai có thể thất bại sai.
3. **Định nghĩa dp mơ hồ:** i và j là số ký tự đã dùng; tiền tố target có độ dài i+j, không phải i hoặc j riêng lẻ.
4. **Sai chỉ số ký tự đích:** ký tự cuối của tiền tố dài i+j ở chỉ số `i+j−1`, không phải i+j.
5. **Đọc chỉ số âm ở hàng/cột biên:** kiểm tra `i>0` trước khi đọc s1[i−1], `j>0` trước khi đọc s2[j−1].
6. **Đặt `dp[0][0]=false`:** làm mất cơ sở của mọi đường đi.
7. **Dùng AND thay vì OR:** chỉ cần **một** nhánh hợp lệ để chứng minh sự tồn tại.
8. **Quên trường hợp hai nhánh cùng khớp:** chỉ thử một nhánh gây báo sai nếu nhánh đó dẫn tới ngõ cụt.
9. **Nén 1D rồi duyệt j giảm:** `reachable[j−1]` có thể là hàng cũ, phá bất biến.
10. **Ghi đè 1D không kiểm soát:** đọc nguồn “phía trên” và “phía trái” phải dùng đúng phiên bản hàng.
11. **Truy vết khi `dp[m][n]=false`:** không có đường đi tới cơ sở; không cố dựng choices.
12. **Không đảo choices khi truy vết ngược:** chuỗi A/B đã ghi từ ký tự cuối tới ký tự đầu phải đảo lại.
13. **Tưởng ưu tiên A lúc truy vết ngược là tối ưu từ điển:** không suy ra được tính nhỏ nhất theo chiều thuận.
14. **Đếm số cách bằng OR:** OR chỉ cho tồn tại; muốn đếm phải cộng hai số cách (và chú ý số rất lớn).
15. **Nhầm số cách gán nguồn với số target khác nhau:** nhiều đường đi A/B có thể sinh cùng một target nếu ký tự trùng.
16. **Không tính RAM của bảng 2D:** với m,n lớn, số ô và overhead của Java có thể vượt giới hạn.
17. **Không định nghĩa đơn vị ký tự:** `charAt` xử lý UTF-16 code unit; nếu đề yêu cầu code point hoặc grapheme, cần thuật toán trên biểu diễn tương ứng.
18. **Đổi chỗ nguồn khi vẫn cần nhãn gốc:** hoán đổi A/B trong bản compact chỉ an toàn vì bản đó trả boolean; nếu trả đường đi gắn nhãn hai nguồn, phải giữ hoặc khôi phục ánh xạ nguồn.

## 15. Những mở rộng cần hiểu đúng

### 15.1. Tìm đường đi ưu tiên A theo chiều thuận

Bảng `dp[i][j]` của bài học mô tả khả thi **từ đầu tới (i,j)**. Khi đi ngược từ (m,n), chọn A trước ở mỗi lần hòa không đồng nghĩa với chọn A sớm nhất ở vị trí đầu của target.

Nếu muốn lựa chọn nguồn theo thứ tự từ điển với A<B, có thể xây `good[i][j]` biểu diễn khả năng tạo **phần còn lại** của target từ hai hậu tố `s1[i..m)` và `s2[j..n)`:

- `good[m][n]=true`.
- Duyệt i từ m về 0, j từ n về 0.
- Ở trạng thái (i,j), thử lấy `s1[i]` nếu i<m và khớp ký tự `target[i+j]`, chuyển tới `good[i+1][j]`; hoặc lấy `s2[j]` nếu j<n, chuyển tới `good[i][j+1]`.
- Chỉ chọn một bước nếu trạng thái sau bước ấy còn có thể đi tới đích.

Sau khi tính bảng hậu tố này, đi **từ (0,0)** và ưu tiên nhánh A nếu nó vẫn dẫn tới đích; như vậy có thể dựng một chuỗi A/B nhỏ nhất theo thứ tự từ điển theo chiều thuận. Bộ nhớ cho bảng hậu tố là O(mn) nếu lưu đầy đủ.

### 15.2. Đếm modulo và số lớn

Nếu chỉ yêu cầu số cách modulo M>0, thay `BigInteger` bằng phép cộng modulo sau mỗi bước, cẩn thận tràn số trước phép modulo. Nếu cần số cách **chính xác**, dùng BigInteger hoặc chứng minh cận đủ cho long. Số cách tối đa khi mọi ký tự khớp là `C(m+n,m)`, có thể tăng rất nhanh.

### 15.3. Thêm chuỗi nguồn thứ ba

Nếu có ba nguồn và phải bảo toàn thứ tự trong từng nguồn, trạng thái tự nhiên là `dp[i][j][k]`. Một trạng thái có thể đến từ ba tiền nhiệm (giảm một chỉ số và so ký tự tương ứng), với độ dài đích bằng `m+n+p`. Số trạng thái có thể là `(m+1)(n+1)(p+1)`, làm chi phí tăng mạnh. Đây là sự mở rộng tự nhiên của ý tưởng DP nhưng không nhất thiết thực tế khi số nguồn lớn.

### 15.4. Thêm trọng số hoặc tối ưu hóa

Nếu mỗi lựa chọn nguồn có chi phí và muốn chi phí nhỏ nhất trong các cách đan xen hợp lệ, có thể thay boolean bằng một giá trị tối ưu, dùng INF cho trạng thái không đạt tới và phép min ở hai nhánh. Nhưng phải định nghĩa rõ **chi phí của mỗi bước**, trạng thái và điều kiện cơ sở. Không tự dùng công thức boolean cho một bài toán tối ưu hóa mà chưa sửa phép gộp.

## 16. Checklist giải bài

- Ba chuỗi có null không? Độ dài target có bằng tổng độ dài nguồn không?
- Mỗi nguồn phải giữ nguyên thứ tự và dùng **toàn bộ** ký tự đúng một lần chứ?
- `dp[i][j]` đã được định nghĩa là tính khả thi của **hai tiền tố** với tiền tố đích dài i+j chưa?
- `dp[0][0]` và hàng/cột biên đã khởi tạo đúng chưa?
- Mỗi chuyển có kiểm tra ký tự cuối target tại **i+j−1** và trạng thái tiền nhiệm không?
- Nếu cả hai nguồn đều khớp, đã giữ **cả hai khả năng** qua phép OR chưa?
- Thứ tự vòng lặp có tính được ô trên và ô trái trước ô hiện tại không?
- Khi nén 1D, đã duyệt **j tăng** và hiểu bản cũ/bản mới của reachable chưa?
- Nếu cần một chuỗi A/B, đã giữ bảng để truy vết, kiểm tra tiền nhiệm đúng và đảo chuỗi sau khi truy vết chưa?
- Nếu cần đếm số cách, đã dùng phép cộng và kiểu số/modulo phù hợp chưa?
- Đã thử hai nguồn rỗng, một nguồn rỗng, sai độ dài, trùng ký tự, trường hợp hòa và sai thứ tự chưa?
- Độ phức tạp thời gian/bộ nhớ có tính đúng `(m+1)(n+1)`, kể cả trường hợp một nguồn rỗng chưa?
- “Ký tự” trong bài được hiểu là UTF-16 code unit, Unicode code point hay ký tự hiển thị? Mã đang dùng cùng cách hiểu không?

**Kết luận:** bài toán đan xen hai chuỗi là một DP trên **hai số lượng ký tự đã dùng**. Mỗi trạng thái `(i,j)` chỉ cần xét hai cách tạo **ký tự cuối** từ s1 hoặc s2; kiểm tra một trạng thái khả thi là **OR** của các tiền nhiệm hợp lệ. Bảng 2D cho phép chứng minh và truy vết dễ dàng; bản 1D giữ đúng sự phụ thuộc **hàng cũ/hàng mới** để giảm bộ nhớ; bản đếm thay OR bằng phép cộng. Cốt lõi của lời giải là **bảo toàn thứ tự từng nguồn và không bỏ sót nhánh khi lựa chọn mơ hồ**.