# Khoảng cách chỉnh sửa giữa hai chuỗi

**Khoảng cách chỉnh sửa (edit distance)** đo chi phí nhỏ nhất để biến một chuỗi thành chuỗi khác bằng các phép biến đổi đã quy định. Trong phiên bản phổ biến nhất, **Levenshtein distance**, có ba phép với chi phí **1** cho mỗi lần thực hiện:

- **Chèn (insert):** thêm một ký tự vào chuỗi hiện tại.
- **Xóa (delete):** bỏ một ký tự khỏi chuỗi hiện tại.
- **Thay thế (substitute/replace):** đổi một ký tự thành ký tự khác.

Giữ nguyên một ký tự giống nhau có chi phí **0**. Đáp án là **tổng chi phí tối thiểu**, không phải số ký tự khác nhau tại cùng vị trí, cũng không nhất thiết là một dãy thao tác duy nhất.

Bài học thuộc nhóm **Quy hoạch động dãy**. Ta sẽ thiết kế trạng thái trên **hai tiền tố**, suy ra công thức quy hoạch động, chứng minh tính đúng, truy vết một phương án chỉnh sửa tối ưu, giảm bộ nhớ xuống hai hàng, xử lý các trường hợp đặc biệt của Java/Unicode và xây dựng chương trình **Java 17+ chạy độc lập** với kiểm thử toàn diện trên bộ dữ liệu nhỏ.

## 1. Xác định rõ phép toán và mục tiêu

Cho hai chuỗi `source` và `target` có độ dài lần lượt là `m` và `n` (theo đơn vị “ký tự” đã thống nhất). Cần tính số phép chèn, xóa hoặc thay thế ít nhất để biến `source` thành `target`, mỗi phép tốn một đơn vị.

Ví dụ kinh điển:

```text
source = kitten
target = sitting

kitten  -- thay k thành s --> sitten
sitten  -- thay e thành i --> sittin
sittin  -- chèn g ở cuối --> sitting

Tổng cộng 3 phép.
```

Kết quả `3` là tối ưu, không chỉ là một cách thực hiện hợp lệ. Phần chứng minh ở mục 4 sẽ cho biết vì sao công thức DP không bỏ sót phương án tốt hơn.

| Cặp chuỗi | Khoảng cách Levenshtein | Lý do |
| --- | ---: | --- |
| `"cat"` → `"cut"` | `1` | Thay `a` thành `u` |
| `"abc"` → `"abc"` | `0` | Không cần sửa |
| `""` → `"abc"` | `3` | Chèn ba ký tự |
| `"abc"` → `""` | `3` | Xóa ba ký tự |
| `"flaw"` → `"lawn"` | `2` | Xóa `f`, chèn `n` |
| `"kitten"` → `"sitting"` | `3` | Hai thay thế, một chèn |
| `"ab"` → `"ba"` | `2` | Hai thay thế, hoặc một xóa và một chèn |

**Quan trọng:** Với Levenshtein chuẩn, việc **đổi chỗ hai ký tự kề nhau không phải một phép có sẵn**. Bởi vậy `"ab"` → `"ba"` mất `2` phép. Một biến thể cho phép *transposition* với chi phí 1 có thể cho kết quả khác; phải phân biệt khi đọc đề.

### Các giả định dùng xuyên suốt

1. Mỗi chèn, xóa, thay thế có chi phí **1** và chi phí giữ ký tự bằng nhau là **0**.
2. Phép biến đổi áp dụng trên một dãy ký hiệu có thứ tự; trong Java, ví dụ chính dùng **Unicode code point**, không mặc định `String.length()` là số ký tự người dùng nhìn thấy.
3. Chỉ cần trả **giá trị nhỏ nhất** trừ khi đề yêu cầu dựng lại các thao tác.
4. Chuỗi đầu vào có thể rỗng, chứa dấu tiếng Việt hoặc ký tự ngoài BMP; Java `null` là đầu vào không hợp lệ trong API ví dụ.
5. Không yêu cầu tìm tất cả các phương án tối ưu; có thể có **nhiều kịch bản chỉnh sửa cùng chi phí**.

## 2. Vì sao so sánh từng vị trí hoặc tham lam thường không đủ?

Một ý tưởng sai là đếm số vị trí khác nhau rồi cộng chênh lệch độ dài:

```text
source = abcde
target = bcde
```

Chỉ cần **xóa ký tự a ở đầu**, chi phí đúng là **1**. Nếu so sánh các ký tự theo chỉ số như hai mảng bằng độ dài, bốn cặp đầu đều lệch do toàn bộ nội dung đã dịch một vị trí. Một phép chèn/xóa có thể làm lệch mọi vị trí phía sau; do đó **Hamming distance** chỉ thích hợp cho bài toán khác, thường là hai chuỗi có **cùng độ dài** và chỉ cho phép thay thế.

Tương tự, một lựa chọn tham lam như “hễ hai ký tự hiện tại khác thì luôn thay thế” có thể bỏ qua phương án chèn/xóa tốt hơn. Khi hai tiền tố không khớp, có đến **ba hướng** cần cân nhắc. Quy hoạch động giúp so sánh đúng tổng chi phí của mọi hướng mà không tính lại vô số bài toán con.

Một cách nghĩ tự nhiên: khi quan sát **ký tự cuối** của hai tiền tố, phương án chỉnh sửa cuối cùng thuộc một trong ba nhóm (xóa, chèn, thay thế/giữ). Đây chính là lý do bài toán có **cấu trúc con tối ưu (optimal substructure)**.

## 3. Định nghĩa trạng thái trên hai tiền tố

Cho:

- `A` là chuỗi nguồn với `m` đơn vị ký tự.
- `B` là chuỗi đích với `n` đơn vị ký tự.
- `A[0..i)` là **i ký tự đầu tiên** của nguồn.
- `B[0..j)` là **j ký tự đầu tiên** của đích.

Đặt:

```text
dp[i][j] = số phép chỉnh sửa ít nhất để biến
           A[0..i) thành B[0..j)

0 <= i <= m
0 <= j <= n
```

Mỗi ô được gắn với **hai độ dài tiền tố**, vì đáp án phụ thuộc vào cả phần nguồn đã xét và phần đích cần tạo. Chỉ lưu `i` hoặc chỉ lưu `j` là không đủ để phân biệt các bài toán con.

### Trường hợp cơ sở

Khi một tiền tố rỗng:

```text
dp[0][0] = 0
dp[i][0] = i      // xóa i ký tự
dp[0][j] = j      // chèn j ký tự
```

Giải thích:

- Biến chuỗi rỗng thành chuỗi gồm `j` ký tự cần **j phép chèn**; không có lựa chọn nào dùng ít phép hơn vì mỗi lần chèn chỉ thêm tối đa một ký tự.
- Biến chuỗi gồm `i` ký tự thành rỗng cần **i phép xóa**.
- Hai chuỗi rỗng không tốn phép nào.

Đây là lý do bảng có kích thước **`(m+1)×(n+1)`**, bao gồm hàng và cột đại diện cho tiền tố rỗng.

### Công thức chuyển trạng thái

Với `i>0` và `j>0`, xét hai ký tự cuối `A[i−1]` và `B[j−1]`.

Nếu bằng nhau, ta có thể giữ nguyên chúng:

```text
dp[i][j] = dp[i-1][j-1]          nếu A[i-1] == B[j-1]
```

Nếu khác nhau, cần lấy lựa chọn nhỏ nhất trong ba khả năng:

```text
dp[i][j] = 1 + min(
    dp[i-1][j],       // xóa ký tự cuối của tiền tố A
    dp[i][j-1],       // chèn ký tự cuối của tiền tố B
    dp[i-1][j-1]      // thay ký tự cuối của A thành của B
)
```

Có thể viết chung bằng **chi phí thay thế** `cost=(A[i−1]==B[j−1] ? 0 : 1)`:

```text
dp[i][j] = min(
    dp[i-1][j]   + 1,      // DELETE
    dp[i][j-1]   + 1,      // INSERT
    dp[i-1][j-1] + cost    // KEEP / SUBSTITUTE
)
```

Công thức chung đặc biệt hữu ích khi triển khai vì cùng xử lý trường hợp bằng nhau và khác nhau, không cần tách hai nhánh. Với hai ký tự bằng nhau, đi chéo với chi phí 0 luôn là một phương án tối ưu; không cần tăng chi phí khi giữ nguyên.

## 4. Chứng minh công thức DP đúng

**Mệnh đề:** `dp[i][j]` đúng bằng chi phí Levenshtein tối thiểu để biến tiền tố `A[0..i)` thành `B[0..j)`.

**Cơ sở:** Nếu `i=0`, chỉ có thể tạo `j` ký tự đích từ chuỗi rỗng bằng các phép chèn, nên chi phí ít nhất `j` và có cách đạt đúng `j`. Nếu `j=0`, cần xóa `i` ký tự, chi phí ít nhất `i` và có cách đạt được. Vì thế công thức biên đúng.

**Bước quy nạp:** Giả sử mọi trạng thái có tổng chỉ số nhỏ hơn `i+j` đều đã được tính đúng. Một kịch bản chỉnh sửa tối ưu có thể được chuẩn hóa theo cách căn chỉnh các ký tự cuối, với ba dạng kết thúc:

1. Ký tự cuối nguồn bị **xóa**: trước thao tác đó phải biến `A[0..i−1)` thành `B[0..j)`, tốn ít nhất `dp[i−1][j]`, rồi xóa thêm một ký tự.
2. Ký tự cuối đích được **chèn**: trước đó biến `A[0..i)` thành `B[0..j−1)`, tốn ít nhất `dp[i][j−1]`, rồi chèn một ký tự.
3. Hai ký tự cuối được **ghép cặp**: nếu bằng nhau thì giữ, nếu khác thì thay thế, sau khi đã biến `A[0..i−1)` thành `B[0..j−1)`, tốn `dp[i−1][j−1]+cost`.

Mỗi trường hợp tạo ra một kịch bản hợp lệ đạt đúng chi phí ứng viên tương ứng; ngược lại, mọi kịch bản tối ưu có thể mô tả bằng một đường đi hợp lệ trên lưới các tiền tố gồm ba bước đó. Chọn **min** của các ứng viên vì thế không thể lớn hơn tối ưu thực tế, cũng không thể nhỏ hơn một kịch bản hợp lệ. Hai giá trị bằng nhau.

**Thứ tự tính:** Mọi ô `(i,j)` chỉ phụ thuộc ô phía trên `(i−1,j)`, trái `(i,j−1)` và chéo trên-trái `(i−1,j−1)`. Duyệt `i` tăng từ `1..m` và trong mỗi hàng duyệt `j` tăng từ `1..n` bảo đảm các ô cần thiết đều đã có đáp án. Kết quả cuối là **`dp[m][n]`**.

**Tính kết thúc:** Có hữu hạn `(m+1)(n+1)` ô, mỗi ô giải đúng một lần trong hai vòng lặp hữu hạn. Không có chu trình phụ thuộc vì mỗi bước về ô con làm giảm `i+j`.

### Góc nhìn đường đi ngắn nhất trên lưới

Xem mỗi ô `(i,j)` là một đỉnh. Từ `(i−1,j)` đến `(i,j)` là xóa, từ `(i,j−1)` đến `(i,j)` là chèn, từ `(i−1,j−1)` đến `(i,j)` là giữ/thay với trọng số 0 hoặc 1. Mọi cạnh đều tăng chỉ số nên tạo một đồ thị **không chu trình (DAG)**. `dp[i][j]` chính là độ dài đường đi ngắn nhất từ `(0,0)` đến `(i,j)`. Đây là một cách hiểu tổng quát vì sao DP chọn min của ba tiền nhiệm.

## 5. Ví dụ điền bảng: "cat" → "cut"

Đặt `A="cat"` (nguồn) và `B="cut"` (đích). Bảng có 4 hàng và 4 cột vì mỗi bên dài 3.

| Tiền tố nguồn \ Đích | `""` | `"c"` | `"cu"` | `"cut"` |
| --- | ---: | ---: | ---: | ---: |
| `""` | 0 | 1 | 2 | 3 |
| `"c"` | 1 | 0 | 1 | 2 |
| `"ca"` | 2 | 1 | 1 | 2 |
| `"cat"` | 3 | 2 | 2 | **1** |

Diễn giải:

- `dp[1][1]=0` vì cả hai tiền tố chỉ chứa `c`.
- `dp[2][2]=1` vì `"ca"` → `"cu"` chỉ cần thay `a` thành `u`.
- `dp[3][3]=1` vì có thể giữ ký tự `t` ở cuối sau khi đã biến `"ca"` thành `"cu"`.

Đường chỉnh sửa tối ưu là:

```text
cat  -- thay a thành u --> cut
```

Bảng cho thấy số nhỏ nhất tại ô cuối, nhưng một **bảng số** chưa tự mô tả hết chuỗi thao tác. Để xây các phép chỉnh sửa, cần **truy vết ngược** từ `(m,n)` theo các tiền nhiệm đã tạo giá trị tối ưu, sau đó đảo thứ tự bước.

### Ví dụ có chèn/xóa làm lệch vị trí

Với `"abcde"` → `"bcde"`:

- Khi xóa `a` đầu tiên, bốn ký tự sau giữ nguyên.
- Khoảng cách là 1 chứ không phải 4 hay 5.
- Một thuật toán chỉ so sánh cùng chỉ số không nhìn thấy phép biến đổi “dịch” này.

Bởi vậy DP đặc biệt phù hợp khi cần xét **căn chỉnh (alignment)** giữa hai dãy.

## 6. Triển khai dùng bảng đầy đủ

Ý tưởng Java cho hai mảng ký hiệu `a[]`, `b[]`:

```java
int m = a.length, n = b.length;
int[][] dp = new int[m + 1][n + 1];

for (int i = 0; i <= m; i++) dp[i][0] = i;
for (int j = 0; j <= n; j++) dp[0][j] = j;

for (int i = 1; i <= m; i++) {
    for (int j = 1; j <= n; j++) {
        int cost = a[i - 1] == b[j - 1] ? 0 : 1;
        dp[i][j] = Math.min(
            dp[i - 1][j] + 1,
            Math.min(
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost));
    }
}

int distance = dp[m][n];
```

*Đây là lõi DP trên mảng ký hiệu đã khai báo, không phải một chương trình độc lập. Chương trình Java đầy đủ ở mục 11.*

Với `m` và `n` là số ký hiệu của hai chuỗi:

- **Thời gian:** `Θ(mn)` cho cả bảng khi `m,n≥1`; tính cả trường hợp chuỗi rỗng là `O((m+1)(n+1))`.
- **Bộ nhớ bảng:** `Θ((m+1)(n+1))` ô số nguyên; thường gọi gọn là `O(mn)` khi cả hai độ dài dương.
- **Truy vết:** Nếu giữ cả bảng, có thể dựng một đường tối ưu trong **`O(m+n)` bước**, vì mỗi bước giảm `i`, `j` hoặc cả hai.
- **Không sửa input:** Chuỗi Java là bất biến; DP tạo bảng mới. Nếu chuyển đầu vào thành mảng code point, việc chuyển đổi còn sử dụng bộ nhớ riêng.

Nếu bài chỉ yêu cầu một con số và `m,n` có thể lớn, cấp phát cả bảng có thể không cần thiết. Hãy xét phiên bản **hai hàng** ở mục kế tiếp.

## 7. Tối ưu bộ nhớ bằng hai hàng (rolling array)

Để tính `dp[i][j]`, ta chỉ cần:

- Hàng trước: `dp[i−1][j]` và `dp[i−1][j−1]`.
- Ô bên trái của **hàng hiện tại**: `dp[i][j−1]`.

Vì vậy chỉ cần hai mảng một chiều:

```text
previous[j] = dp[i-1][j]
current[j]  = dp[i][j]

current[0] = i

current[j] = min(
    previous[j] + 1,                    // xóa
    current[j-1] + 1,                   // chèn
    previous[j-1] + (a[i-1] != b[j-1]) // giữ/thay
)
```

Sau mỗi hàng, hoán đổi **tham chiếu** `previous` và `current` thay vì sao chép từng phần tử. Trong hàng tiếp theo, `current[0]` và mọi `current[j]` sẽ được ghi đè theo thứ tự trái sang phải, nên không cần `Arrays.fill` toàn mảng mỗi vòng.

### Chọn chiều ngắn hơn cho cột

Khoảng cách Levenshtein **đối xứng** khi chi phí chèn và xóa đều bằng 1:

```text
distance(A,B) = distance(B,A)
```

Một chuỗi thao tác biến `A` thành `B` có thể được đảo ngược (chèn ↔ xóa; thay thế ↔ thay thế), cùng chi phí. Nhờ đó, nếu một chuỗi dài hơn, ta dùng chuỗi dài ở hàng và **chuỗi ngắn ở cột**, để hai mảng DP chỉ dài `min(m,n)+1`:

- **Bộ nhớ phụ cho phần bảng DP:** `O(min(m,n))`.
- **Thời gian:** vẫn `Θ(mn)` nếu cả hai không rỗng, vì vẫn tính một ô cho mỗi cặp ký hiệu.
- **Hạn chế:** chỉ còn con số cuối; không còn đủ thông tin để truy vết một kịch bản tối ưu bằng cách đơn giản như với bảng đầy đủ.

**Đánh đổi:** Nếu cần *cả* độ dài và trình tự thao tác, giữ bảng `O(mn)` thường là lựa chọn dễ hiểu. Có kỹ thuật như **Hirschberg** dùng chia để trị để dựng căn chỉnh với bộ nhớ tuyến tính, nhưng triển khai phức tạp hơn và phải xác định rõ các phép edit/tiêu chí tie-break.

### Một chi tiết dễ bị bỏ sót về Java và Unicode

Nếu cài đặt chuyển cả hai `String` thành hai mảng `int[]` bằng `codePoints().toArray()`, bản thân hai mảng đó dùng **`O(m+n)` bộ nhớ**, ngay cả khi bảng rolling chỉ dùng `O(min(m,n))`. Vì thế:

- Phát biểu “hai hàng DP chiếm `O(min(m,n))`” là **đúng cho cấu trúc bảng**.
- Phát biểu “toàn bộ phương thức Java dùng `O(min(m,n))` bộ nhớ” là **sai với đúng cài đặt có hai mảng code point**.
- Tổng bộ nhớ phụ của bản Java rolling mẫu là **`O(m+n)`** do lưu hai mảng ký hiệu, cộng `O(min(m,n))` cho các hàng; còn bảng đầy đủ dùng thêm `O(mn)`.

Sự phân biệt này đặc biệt quan trọng khi phân tích bộ nhớ thực thay vì chỉ nêu công thức quy hoạch động trừu tượng.

## 8. Truy vết một dãy thao tác chỉnh sửa

Nếu cần hướng dẫn cách biến chuỗi này thành chuỗi kia, không chỉ trả số, dùng bảng đầy đủ và bắt đầu từ `(m,n)`.

Ở mỗi ô:

1. Nếu hai ký tự cuối bằng nhau **và** `dp[i][j]=dp[i−1][j−1]`, ghi **KEEP**, giảm cả `i,j`.
2. Nếu có thể đến ô hiện tại từ ô chéo `dp[i−1][j−1]+1`, ghi **SUBSTITUTE**, giảm cả hai.
3. Nếu có thể đến từ phía trên `dp[i−1][j]+1`, ghi **DELETE**, giảm `i`.
4. Nếu có thể đến từ bên trái `dp[i][j−1]+1`, ghi **INSERT**, giảm `j`.

Với một số ô có nhiều tiền nhiệm cùng đạt min, ta cần **quy tắc phá hòa (tie-break)**. Chương trình Java chọn thứ tự ưu tiên **KEEP → SUBSTITUTE → DELETE → INSERT**. Đây là chính sách xác định **một** phương án tối ưu, không tuyên bố đó là phương án tối ưu duy nhất.

Vì đi từ ô cuối về ô đầu, các bước thu được ở **thứ tự ngược**; gọi `Collections.reverse(steps)` trước khi trình bày chuỗi thao tác từ nguồn đến đích.

Ví dụ cho `"kitten"` → `"sitting"`:

```text
SUB(k->s)
KEEP(i)
KEEP(t)
KEEP(t)
SUB(e->i)
KEEP(n)
INS(g)
```

Có 7 bước căn chỉnh, trong đó **4 KEEP** có chi phí 0, **2 SUB** và **1 INS** mỗi bước tốn 1. Tổng chi phí = **3**.

### Cách tự xác minh truy vết

Với mỗi bước:

- **KEEP:** tiêu thụ một ký tự nguồn, sinh cùng ký tự đích.
- **SUB:** tiêu thụ một ký tự nguồn, sinh ký tự đích khác.
- **DEL:** tiêu thụ một ký tự nguồn, không sinh ký tự đích.
- **INS:** không tiêu thụ ký tự nguồn, sinh một ký tự đích.

Nối các ký tự **được tiêu thụ** phải tái tạo đúng `source`; nối các ký tự **được sinh ra** phải tái tạo đúng `target`. Đếm số bước khác KEEP phải bằng `dp[m][n]`.

Đó là một phép kiểm tra mạnh hơn việc chỉ thấy chuỗi kết quả “trông có vẻ giống”. Nó phát hiện lỗi như thiếu một INSERT, đảo thứ tự bước hoặc nhầm DELETE với SUBSTITUTE.

**Lưu ý về vị trí chỉnh sửa:** Chuỗi bước được hiểu là một **alignment từ trái sang phải**, không phải danh sách các thao tác với chỉ số cố định trong chuỗi gốc. Nếu API yêu cầu tọa độ sửa tại từng thời điểm, chỉ số thay đổi sau INSERT/DELETE và cần được tính theo trạng thái chuỗi **hiện tại**.

## 9. Unicode, dấu tiếng Việt và ý nghĩa của “một ký tự”

Với Java, thuật ngữ “ký tự” không chỉ có một cách đếm:

| Đơn vị | Ví dụ Java | Ý nghĩa |
| --- | --- | --- |
| **UTF-16 code unit** | `s.length()`, `charAt` | Mỗi `char` là 16 bit; ký tự ngoài BMP thường dùng **hai** code unit (surrogate pair) |
| **Unicode code point** | `s.codePoints()` | Một giá trị mã Unicode; ký tự emoji ngoài BMP thường tính là **một** code point |
| **Grapheme cluster (ký tự người dùng nhìn thấy)** | Cần thuật toán phân đoạn văn bản | Có thể gồm nhiều code point, ví dụ chữ cái + dấu kết hợp, emoji ghép bằng ZWJ |

Ví dụ:

```text
"😀" là một Unicode code point, nhưng có String.length() == 2
(theo UTF-16 code unit).

"e" + U+0301 (dấu sắc kết hợp) thường hiển thị giống "é"
(U+00E9) nhưng hai chuỗi có code point khác nhau.
```

Một thuật toán DP trên `char[]` có thể đếm khác với DP trên `int[] codePoints`, đặc biệt ở trường hợp chèn/xóa emoji. Nếu đề nói “độ dài là số code point”, cài đặt trên `String.length()` có thể sai.

Chương trình Java ở đây dùng `codePoints().toArray()`. Khi so sánh hai chuỗi có biểu diễn Unicode **khác nhau nhưng tương đương về mặt chuẩn hóa**, cần thống nhất tiền xử lý, ví dụ:

```java
String normalized =
    java.text.Normalizer.normalize(
        original, java.text.Normalizer.Form.NFC);
```

*Đây là đoạn minh họa; biến `original` phải được khai báo trước.*

Với `"e\u0301"` và `"\u00E9"`, khoảng cách theo code point **trước chuẩn hóa** là `2`, nhưng sau khi cả hai được chuẩn hóa `NFC` là **0**. Đây không phải lỗi DP: **đầu vào sau biến đổi tiền xử lý đã khác**. Tùy ứng dụng, có thể yêu cầu giữ nguyên khác biệt code point hoặc coi chúng tương đương.

**NFC không phải thuật toán phân đoạn grapheme.** Một emoji ghép nhiều code point hoặc một chữ có nhiều dấu kết hợp vẫn có thể là một grapheme cluster. Nếu định nghĩa khoảng cách theo ký tự hiển thị, cần phân đoạn grapheme đúng chuẩn trước khi chạy DP. Cũng phải quyết định có phân biệt chữ hoa/chữ thường, dấu, khoảng trắng và dấu câu không; mọi bước `lowercase` hoặc chuẩn hóa đều **thay đổi định nghĩa khoảng cách**.

### Đối với tiếng Việt

Một chữ tiếng Việt có thể có biểu diễn dựng sẵn hoặc gồm chữ cơ sở và dấu kết hợp. Với so khớp tên người, dữ liệu nhập từ nhiều nguồn hoặc tìm kiếm gần đúng, quy trình có thể là:

1. Chuẩn hóa Unicode hai chuỗi về cùng một form nếu hợp đồng cho phép.
2. Quyết định có hay không chuyển chữ hoa thành chữ thường theo `Locale` phù hợp.
3. Quyết định so sánh theo code point hay grapheme cluster.
4. Chỉ sau đó tính edit distance.

Không nên tự xóa dấu tiếng Việt nếu bài toán cần phân biệt `ma`, `má`, `mà`. Xóa dấu có thể cải thiện tìm kiếm gần đúng trong một ứng dụng, nhưng không phải ngữ nghĩa mặc định của Levenshtein.

## 10. Tính chất, biến thể và lựa chọn thuật toán

### Ba tính chất quan trọng

Với chi phí đơn vị không âm và cùng kiểu ký hiệu:

- **Không âm và bằng 0 khi giống nhau:** `d(A,B)≥0`; `d(A,A)=0`. Với phép toán đã cho, `d(A,B)=0` đồng nghĩa hai dãy ký hiệu bằng nhau.
- **Đối xứng:** `d(A,B)=d(B,A)` vì đảo ngược từng phép chèn/xóa/thay thế được với cùng chi phí.
- **Bất đẳng thức tam giác:** `d(A,C)≤d(A,B)+d(B,C)` vì ghép một kịch bản từ A đến B với một kịch bản từ B đến C tạo kịch bản hợp lệ từ A đến C.

Một **cận dưới rất rẻ** là:

```text
distance(A,B) >= abs(m - n)
```

Vì chỉ chèn/xóa mới thay đổi độ dài, và mỗi lần chỉ thay đổi tối đa một đơn vị. Nếu chỉ muốn biết khoảng cách có **không vượt quá k** hay không, mà `abs(m-n)>k`, có thể trả **false ngay** mà không dựng bảng.

### Không phải lúc nào cũng cần bảng DP đầy đủ

| Nhu cầu | Hướng xử lý | Lưu ý |
| --- | --- | --- |
| Hai chuỗi ngắn, cần số khoảng cách | DP hai hàng | Dễ triển khai, `O(mn)` thời gian |
| Cần cả một kịch bản sửa tối ưu | DP bảng đầy đủ + backtrack | `O(mn)` bộ nhớ bảng; có thể nhiều kịch bản cùng tối ưu |
| Chỉ quan tâm `distance≤k` với `k` nhỏ | DP trong dải quanh đường chéo (*banded DP*) | Chỉ các ô có `abs(i−j)≤k` mới cần xét cho kịch bản chi phí ≤ k; phải xử lý biên/cắt ngưỡng đúng |
| Chuỗi dài, số chữ cái/bitset phù hợp | Các thuật toán tối ưu bằng bit-parallel | Cần hiểu giả định, số bit/máy và bảng mã; không mặc định mọi input đều nhanh hơn |
| Rất nhiều truy vấn gần đúng | Chỉ mục, lọc cận dưới, BK-tree khi metric phù hợp | Tính cả chi phí tạo chỉ mục, cập nhật, độ dài và phân bố dữ liệu |
| Cần căn chỉnh với bộ nhớ tuyến tính | Chia để trị kiểu Hirschberg | Phức tạp hơn truy vết trên bảng đầy đủ |
| Có phép **đổi chỗ ký tự kề** | Biến thể Damerau–Levenshtein | Phải nêu rõ biến thể và công thức; không dùng nguyên DP ba phép rồi cộng tùy ý |

Với **banded DP** cho ngưỡng `k`, nếu khoảng cách thật sự `≤k`, mọi đường chỉnh sửa tối ưu không thể đi quá xa đường chéo `abs(i−j)>k` vì chênh lệch độ dài tiền tố đòi ít nhất ngần ấy insert/delete. Chỉ cần xét vùng băng phù hợp, có thể giảm công việc xuống bậc `O(k·max(m,n))` trong một số cách triển khai (kể cả chi phí xử lý biên) khi `k` nhỏ; việc trả khoảng cách **chính xác nếu lớn hơn k** không được bảo đảm từ bảng cắt băng này.

### Hai biến thể dễ nhầm

**Damerau–Levenshtein:** Có thêm thao tác đổi chỗ hai ký tự **kề**. Với `"ab"` → `"ba"`, Levenshtein chuẩn cho `2`, còn biến thể cho phép transposition đơn vị có thể cho `1`. Có nhiều mô hình transposition (ví dụ restricted/OSA và unrestricted Damerau), nên phải xác định thuật toán và điều kiện kết hợp thao tác, không dùng lẫn công thức.

**Khoảng cách chỉ chèn và xóa:** Nếu **cấm SUBSTITUTE**, chi phí tối ưu với chèn/xóa đơn vị là:

```text
distance_insert_delete(A,B) = m + n - 2 * LCS(A,B)
```

Trong đó `LCS` là độ dài dãy con chung dài nhất. Công thức này **không đúng tổng quát** cho Levenshtein có SUBSTITUTE giá 1. Ví dụ `"a"` → `"b"`: Levenshtein bằng `1` (thay thế), còn khoảng cách chỉ chèn/xóa bằng `2`.

### Phép chỉnh sửa có trọng số

Nếu đề quy định phí chèn `c_ins`, xóa `c_del` và thay `c_sub`, công thức có thể thay:

```text
dp[i][j] = min(
    dp[i-1][j] + c_del,
    dp[i][j-1] + c_ins,
    dp[i-1][j-1] + (A[i-1] == B[j-1] ? 0 : c_sub)
)
```

Cần thay cả biên `dp[i][0]=i*c_del` và `dp[0][j]=j*c_ins`. Nếu `c_ins!=c_del`, khoảng cách có thể **không còn đối xứng**. Nếu thay thế đắt hơn xóa rồi chèn, phương án tối ưu có thể chọn hai thao tác thay vì SUBSTITUTE. Với chi phí âm hoặc chi phí phụ thuộc ngữ cảnh, các giả định thông thường về metric và truy hồi cần được xem xét lại.

## 11. Java 17+ — bảng đầy đủ, hai hàng và truy vết

Chương trình **EditDistanceDemo.java** dưới đây triển khai:

- `fullDistance`: bảng `dp` đầy đủ và trả `dp[m][n]`.
- `rollingDistance`: chỉ dùng hai hàng DP, chọn chiều cột ngắn hơn để giảm **bộ nhớ bảng**, nhưng vẫn lưu hai mảng code point của chuỗi.
- `trace`: trả một dãy `KEEP/SUB/DEL/INS` có chi phí tối ưu; ưu tiên cố định `KEEP → SUB → DEL → INS` khi có nhiều đường cùng tốt.
- `verifyTrace`: ghép lại các ký hiệu nguồn/đích từ dãy thao tác, kiểm tra số phép khác KEEP bằng khoảng cách đã trả.
- `testAllSmallPairs`: sinh mọi chuỗi độ dài 0 đến 4 từ bảng chữ cái `{a,b,c}`, kiểm tra mọi **14.641 cặp** bằng ba cách, xác thực tính đối xứng và đường truy vết.

Đơn vị là **Unicode code point**. Để đơn giản, phép in một code point dùng `Character.toChars`; không có thao tác chỉnh sửa trực tiếp chuỗi bất biến của caller.

### Toàn bộ mã nguồn

Lưu trong tệp **EditDistanceDemo.java**:

```java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class EditDistanceDemo {
    record Step(String op, String from, String to) {
        @Override
        public String toString() {
            return switch (op) {
                case "KEEP" -> "KEEP(" + from + ")";
                case "SUB" -> "SUB(" + from + "->" + to + ")";
                case "DEL" -> "DEL(" + from + ")";
                case "INS" -> "INS(" + to + ")";
                default -> throw new AssertionError("unknown op");
            };
        }
    }

    record Trace(int distance, List<Step> steps) {}

    static int[] points(String s) {
        return Objects.requireNonNull(s, "string")
                      .codePoints().toArray();
    }

    static int[][] table(int[] a, int[] b) {
        int m = a.length;
        int n = b.length;
        int[][] dp = new int[m + 1][n + 1];

        for (int i = 0; i <= m; i++) {
            dp[i][0] = i;
        }
        for (int j = 0; j <= n; j++) {
            dp[0][j] = j;
        }

        for (int i = 1; i <= m; i++) {
            for (int j = 1; j <= n; j++) {
                int cost = a[i - 1] == b[j - 1] ? 0 : 1;
                dp[i][j] = Math.min(
                    dp[i - 1][j] + 1,
                    Math.min(
                        dp[i][j - 1] + 1,
                        dp[i - 1][j - 1] + cost));
            }
        }
        return dp;
    }

    static int fullDistance(String source, String target) {
        int[] a = points(source);
        int[] b = points(target);
        int[][] dp = table(a, b);
        return dp[a.length][b.length];
    }

    static int rollingDistance(String source, String target) {
        int[] a = points(source);
        int[] b = points(target);

        // Dùng chuỗi ngắn hơn làm cột DP.
        // Với đơn giá insert/delete giống nhau, distance đối xứng.
        if (b.length > a.length) {
            int[] swap = a;
            a = b;
            b = swap;
        }

        int[] previous = new int[b.length + 1];
        int[] current = new int[b.length + 1];
        for (int j = 0; j <= b.length; j++) {
            previous[j] = j;
        }

        for (int i = 1; i <= a.length; i++) {
            current[0] = i;
            for (int j = 1; j <= b.length; j++) {
                int cost = a[i - 1] == b[j - 1] ? 0 : 1;
                current[j] = Math.min(
                    previous[j] + 1,
                    Math.min(
                        current[j - 1] + 1,
                        previous[j - 1] + cost));
            }
            int[] swap = previous;
            previous = current;
            current = swap;
        }

        return previous[b.length];
    }

    static String symbol(int codePoint) {
        return new String(Character.toChars(codePoint));
    }

    static Trace trace(String source, String target) {
        int[] a = points(source);
        int[] b = points(target);
        int[][] dp = table(a, b);
        int i = a.length, j = b.length;

        List<Step> reversed = new ArrayList<>();
        while (i > 0 || j > 0) {
            // Ưu tiên 1: giữ ký tự khớp.
            if (i > 0 && j > 0
                    && a[i - 1] == b[j - 1]
                    && dp[i][j] == dp[i - 1][j - 1]) {
                String x = symbol(a[i - 1]);
                reversed.add(new Step("KEEP", x, x));
                i--;
                j--;
            // Ưu tiên 2: thay thế ký tự khác.
            } else if (i > 0 && j > 0
                    && dp[i][j] == dp[i - 1][j - 1] + 1) {
                reversed.add(new Step(
                    "SUB", symbol(a[i - 1]), symbol(b[j - 1])));
                i--;
                j--;
            // Ưu tiên 3: xóa ký tự nguồn.
            } else if (i > 0
                    && dp[i][j] == dp[i - 1][j] + 1) {
                reversed.add(new Step(
                    "DEL", symbol(a[i - 1]), ""));
                i--;
            // Ưu tiên 4: chèn ký tự đích.
            } else if (j > 0
                    && dp[i][j] == dp[i][j - 1] + 1) {
                reversed.add(new Step(
                    "INS", "", symbol(b[j - 1])));
                j--;
            } else {
                throw new AssertionError("bad DP backtrace");
            }
        }

        Collections.reverse(reversed);
        return new Trace(dp[a.length][b.length], reversed);
    }

    static boolean verifyTrace(String source, String target,
                               Trace trace) {
        Objects.requireNonNull(trace, "trace");
        StringBuilder consumed = new StringBuilder();
        StringBuilder produced = new StringBuilder();
        int edits = 0;

        for (Step step : trace.steps()) {
            if (!step.op().equals("INS")) {
                consumed.append(step.from());
            }
            if (!step.op().equals("DEL")) {
                produced.append(step.to());
            }
            if (!step.op().equals("KEEP")) {
                edits++;
            }
        }

        return consumed.toString().equals(source)
            && produced.toString().equals(target)
            && edits == trace.distance();
    }

    static List<String> smallWords() {
        List<String> all = new ArrayList<>();
        all.add("");
        for (int length = 1; length <= 4; length++) {
            int variations = 1;
            for (int i = 0; i < length; i++) {
                variations *= 3;
            }
            for (int encoded = 0; encoded < variations; encoded++) {
                int code = encoded;
                StringBuilder word = new StringBuilder();
                for (int i = 0; i < length; i++) {
                    word.append((char) ('a' + code % 3));
                    code /= 3;
                }
                all.add(word.toString());
            }
        }
        return all;
    }

    static int testAllSmallPairs() {
        List<String> words = smallWords();
        int cases = 0;

        for (String source : words) {
            for (String target : words) {
                int full = fullDistance(source, target);
                int rolling = rollingDistance(source, target);
                int symmetric = rollingDistance(target, source);
                Trace script = trace(source, target);

                if (full != rolling
                        || full != symmetric
                        || script.distance() != full
                        || !verifyTrace(source, target, script)) {
                    throw new AssertionError(
                        "Mismatch: " + source + " -> " + target);
                }
                cases++;
            }
        }
        return cases;
    }

    public static void main(String[] args) {
        System.out.println("kitten -> sitting: "
                           + fullDistance("kitten", "sitting"));
        System.out.println("flaw -> lawn: "
                           + rollingDistance("flaw", "lawn"));
        System.out.println("ab -> ba: "
                           + rollingDistance("ab", "ba"));
        System.out.println("empty -> cat: "
                           + rollingDistance("", "cat"));

        Trace script = trace("kitten", "sitting");
        System.out.println("Trace: " + script.steps());
        System.out.println("Trace valid: "
                           + verifyTrace("kitten", "sitting", script));

        String decomposed = "e\u0301";
        String composed = "\u00E9";
        System.out.println("Accent raw: "
                           + rollingDistance(decomposed, composed));
        System.out.println("Accent NFC: "
                           + rollingDistance(
                               Normalizer.normalize(
                                   decomposed, Normalizer.Form.NFC),
                               Normalizer.normalize(
                                   composed, Normalizer.Form.NFC)));
        System.out.println("Emoji -> empty: "
                           + rollingDistance("😀", ""));

        System.out.println("Exhaustive: "
                           + testAllSmallPairs() + " pairs OK");
    }
}
```

Biên dịch và chạy trên **JDK 17+** bằng đúng tên tệp/class:

```bash
javac -encoding UTF-8 EditDistanceDemo.java
java EditDistanceDemo
```

Stdout dự kiến:

```text
kitten -> sitting: 3
flaw -> lawn: 2
ab -> ba: 2
empty -> cat: 3
Trace: [SUB(k->s), KEEP(i), KEEP(t), KEEP(t), SUB(e->i), KEEP(n), INS(g)]
Trace valid: true
Accent raw: 2
Accent NFC: 0
Emoji -> empty: 1
Exhaustive: 14641 pairs OK
```

### Đọc kết quả, không suy diễn quá mức

- `"kitten"` → `"sitting"` có khoảng cách 3 theo đúng ba phép đơn vị.
- `"ab"` → `"ba"` có khoảng cách 2 trong **Levenshtein chuẩn**. Nếu một thư viện trả 1, cần kiểm tra có hỗ trợ đổi chỗ hay không.
- `trace` liệt kê cả bước **KEEP** để tái dựng căn chỉnh. Chỉ SUB/DEL/INS có chi phí 1, tổng bằng 3.
- Chuỗi gốc **không bị sửa**; mọi bảng, mảng code point và danh sách bước đều là dữ liệu mới.
- `"e\u0301"` và `"\u00E9"` được xử lý theo code point; Unicode normalization **NFC** làm hai chuỗi tương đương về canonical form trở nên đồng nhất cho ví dụ này.
- Khoảng cách `"😀"` → `""` bằng **1** vì emoji là một code point; so trực tiếp bằng độ dài UTF-16 code unit có thể nhận kết quả khác.
- Tập từ có `1+3+9+27+81=121` chuỗi, tính cả chuỗi rỗng. Kiểm thử chạy mọi **121×121=14.641 cặp**, xác minh bảng đầy đủ khớp hai hàng, tính đối xứng, script có chi phí đúng và các ký tự được tiêu thụ/sinh ra tái tạo nguyên vẹn đầu vào/đầu ra. Đây là kiểm thử hữu ích nhưng **không thay cho chứng minh quy hoạch động** ở mục 4.

**Giới hạn cài đặt:** Bảng DP tiêu thụ bộ nhớ theo tích hai độ dài và có thể không vừa heap với chuỗi rất dài. Hai mảng code point cùng chiếm bộ nhớ tuyến tính. Với dữ liệu chứa chuỗi rất dài cần giới hạn kích thước, ngưỡng tối đa hoặc thuật toán phù hợp hơn. Giá trị độ dài/chi phí dùng `int` có giới hạn của kiểu số và kích thước mảng Java.

## 12. Lỗi thường gặp khi giải edit distance

**1. Nhầm với Hamming distance.** Nếu chỉ đếm ký tự khác ở cùng chỉ số, không xử lý đúng sự dịch vị trí sau chèn/xóa. Hamming thường xét chuỗi cùng độ dài và không dùng insert/delete.

**2. Quên trường hợp chuỗi rỗng.** Hàng `dp[0][j]=j` và cột `dp[i][0]=i` phải được điền đầy đủ trước các ô trong, kể cả `dp[0][0]=0`.

**3. Dùng chỉ số sai.** `dp[i][j]` đại diện **độ dài tiền tố** `i,j`; ký tự cuối tương ứng là `A[i−1]` và `B[j−1]`, không phải `A[i]` hay `B[j]`.

**4. Tính công thức ở chiều sai.** Với DP hai hàng, `current[j−1]` phải đã được tính trước, nên vòng `j` đi **từ trái sang phải**. Đổi sang phải→trái mà không thay chiến lược lưu gây đọc giá trị cũ.

**5. Trộn vai trò insert/delete trong mô tả.** `dp[i−1][j]+1` là xóa ký tự khỏi **nguồn**; `dp[i][j−1]+1` là chèn ký tự để tạo **đích**. Đối với chi phí đều 1, nhầm tên có thể không làm sai giá trị số nhưng sẽ làm sai truy vết.

**6. Không đảo ngược chuỗi thao tác sau backtrack.** Truy vết từ `dp[m][n]` về `dp[0][0]` tạo thứ tự ngược thời gian; muốn áp dụng từ đầu đến cuối phải reverse.

**7. Cho rằng có duy nhất một kịch bản tối ưu.** Nhiều tiền nhiệm có thể cùng min. Quy tắc tie-break chỉ chọn một trong những phương án tối ưu, không tạo ra khái niệm “phương án chuẩn” cho mọi đề.

**8. Nhầm chi phí KEEP.** Ký tự bằng nhau đi chéo có chi phí 0; không được tính mọi bước đường đi là một phép edit có chi phí 1.

**9. Khẳng định rolling DP dùng `O(1)` hoặc toàn bộ chương trình `O(min(m,n))`.** Hai hàng cần bộ nhớ tuyến tính theo chiều ngắn hơn; nếu đã lưu hai mảng code point, tổng bộ nhớ phương thức vẫn tuyến tính theo `m+n`.

**10. Dùng `String.length()` như số ký tự Unicode thực.** Java `length()` đếm code unit UTF-16. Một code point ngoài BMP có thể chiếm hai code unit; grapheme cluster lại là khái niệm khác.

**11. Không nêu chính sách chuẩn hóa.** Hai chuỗi nhìn giống nhau có thể có code point khác nhau; quyết định NFC/case folding/giữ dấu phải được nêu trong hợp đồng trước khi so sánh.

**12. Tự thêm phép đổi chỗ mà không đổi thuật toán.** Levenshtein chuẩn không có transposition. Nếu thêm phép này, phải dùng công thức của biến thể đã chọn và hiểu các giới hạn của nó.

**13. Khẳng định công thức LCS đúng cho mọi edit distance.** `m+n−2·LCS` chỉ dành cho bài **chèn/xóa đơn vị không cho thay thế** hoặc một mô hình chi phí tương đương, không áp nguyên cho Levenshtein có substitution đơn vị.

**14. Không kiểm tra trường hợp chi phí có trọng số.** Đổi chi phí một phép đòi sửa cả biên và công thức. Phép đối xứng có thể mất khi phí chèn và xóa khác nhau.

**15. Dùng DP đầy đủ cho mọi chuỗi rất dài mà không dự toán RAM.** `(m+1)(n+1)` ô int có thể rất lớn. Nếu chỉ cần số khoảng cách, cân nhắc rolling; nếu chỉ cần biết khoảng cách `≤k`, xét cận dưới và thuật toán banded thích hợp.

## 13. Bài tập và gợi ý

**Bài 1 — Tự điền bảng.** Điền `dp` cho `"horse"` → `"ros"` với chèn/xóa/thay chi phí 1. Đáp án đúng là **3**. Viết ít nhất một kịch bản sửa hợp lệ và chứng minh không thể dùng ít hơn theo bảng.

**Bài 2 — Phân biệt Hamming.** Tính Hamming distance (khi áp dụng được) và Levenshtein distance của `"abcde"` và `"bcdea"`. Vì sao chỉ một dịch chuyển không được diễn tả bằng một SUBSTITUTE duy nhất?

**Bài 3 — Truy vết có nhiều cách.** Tính khoảng cách `"ab"` → `"ba"`. Nêu hai kịch bản tối ưu có chi phí 2, ví dụ hai SUBSTITUTE và một DELETE kèm một INSERT. Nếu chọn thứ tự tie-break khác, script có thể khác nhưng khoảng cách vẫn giống nhau.

**Bài 4 — Bộ nhớ hai hàng.** Viết lại công thức dùng `previous` và `current`. Vì sao `current[j−1]` là ô của hàng **hiện tại**, còn `previous[j]` là ô của hàng **trước**? Chứng minh sau mỗi lượt toàn bộ `previous[]` bằng hàng DP vừa tính.

**Bài 5 — Tiền tố rỗng.** Giải thích vì sao `d("", "abc")=3`, `d("abc","")=3` và `d("","")=0`; kiểm tra mã với chuỗi `null` và quyết định hợp đồng lỗi phù hợp.

**Bài 6 — Unicode.** Trong Java, so sánh độ dài `"😀".length()` với `"😀".codePointCount(0,"😀".length())`. Hai cách đo dẫn đến khác biệt gì khi tính khoảng cách từ emoji tới chuỗi rỗng? Vì sao code point chưa đồng nghĩa grapheme cluster?

**Bài 7 — Chuẩn hóa tiếng Việt.** Tạo chuỗi `"e\u0301"` và `"\u00E9"`, tính khoảng cách theo code point trước/sau NFC. Giải thích tại sao kết quả thay đổi và bài toán nào không nên tự chuẩn hóa.

**Bài 8 — Đổi chỗ.** Tại sao Levenshtein chuẩn cho `"ab"` → `"ba"` là 2? Nếu cho phép đổi chỗ kề tốn 1, hãy thiết kế một quy tắc bổ sung nhưng lưu ý rằng biến thể restricted và unrestricted không giống nhau.

**Bài 9 — Trọng số.** Cho `c_ins=2`, `c_del=2`, `c_sub=1`. Viết lại biên và công thức; tính khoảng cách `"a"` → `""`. Sau đó đặt `c_ins=1`, `c_del=3` và kiểm tra vì sao đối xứng có thể không còn.

**Bài 10 — Ngưỡng k.** Khi chỉ cần kiểm tra `d(A,B)≤2`, nếu độ dài hai chuỗi chênh 5 có cần tính DP không? Với `m≈n` rất lớn, phác thảo ý tưởng chỉ tính các ô trong băng `abs(i−j)≤2`.

**Bài 11 — Kiểm thử chuyển đổi.** Sinh mọi chuỗi từ bảng chữ cái nhỏ `{a,b}` có độ dài ≤ 4; đối chiếu bản đầy đủ, bản hai hàng và backtrack. Kiểm tra tính đối xứng, khoảng cách tới chuỗi rỗng và tổng chi phí thao tác.

**Bài 12 — Lựa chọn biến thể.** Một hệ thống sửa lỗi gõ nhanh thường gặp việc hoán vị hai ký tự kề; một hệ thống so sánh đoạn DNA chỉ cho phép chèn/xóa; một hệ thống kiểm tra chuỗi Unicode người dùng nhập. Với mỗi hệ thống, cần làm rõ những giả định nào trước khi dùng công thức edit distance?

## 14. Checklist hoàn thành

1. **Phép toán đúng chưa?** Bài dùng Levenshtein chuẩn (INSERT, DELETE, SUBSTITUTE), Hamming, Damerau hay chỉ INSERT/DELETE? Chi phí mỗi thao tác là bao nhiêu?
2. **Đơn vị ký hiệu là gì?** Code unit UTF-16, Unicode code point, grapheme hay token? Có normalize trước không?
3. **Trạng thái đủ thông tin chưa?** `dp[i][j]` phải ứng với hai tiền tố; ký tự cuối là `A[i−1]` và `B[j−1]`.
4. **Base case chính xác?** Có `dp[0][0]=0`, `dp[i][0]=i`, `dp[0][j]=j` theo chi phí đơn vị?
5. **Transition đầy đủ?** Đã xét cả ba lựa chọn và cho KEEP chi phí 0 nếu hai ký tự bằng nhau?
6. **Thứ tự tính đúng?** Mọi ô trên/trái/chéo đã có kết quả khi cần, không đọc giá trị chưa khởi tạo?
7. **Nếu cần script, backtrack đúng?** Chỉ theo cạnh tạo min, có tie-break, reverse các bước và kiểm tra consumed/produced?
8. **Độ phức tạp rõ ràng?** `O(mn)` thời gian, `O(mn)` bảng đầy đủ hoặc `O(min(m,n))` cho hai hàng; tính cả bộ nhớ chuyển chuỗi thành mảng ký hiệu.
9. **Input biên được xử lý?** Chuỗi rỗng, giống nhau, khác độ dài nhiều, chuỗi có lặp, emoji và chuỗi biểu diễn Unicode khác nhau.
10. **Đã kiểm chứng?** So bảng với rolling, thử kịch bản chuyển đổi tối ưu, đối chiếu cặp chuỗi nhỏ và các tính chất distance?

**Tiêu chí hoàn thành:** Bạn có thể tự thiết kế công thức Levenshtein từ hai tiền tố, chứng minh tính đúng bằng cấu trúc con tối ưu, triển khai Java 17+ cả bảng đầy đủ và hai hàng, truy vết một dãy thao tác hợp lệ có tổng chi phí tối ưu, và phân biệt đúng đơn vị Unicode cũng như các biến thể edit distance trước khi áp dụng.
