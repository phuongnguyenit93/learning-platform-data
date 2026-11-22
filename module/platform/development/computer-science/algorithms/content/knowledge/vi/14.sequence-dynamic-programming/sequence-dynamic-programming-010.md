# Khớp chuỗi với ký tự đại diện và ngữ nghĩa mẫu

**Khớp chuỗi với ký tự đại diện** (*wildcard matching*) là bài toán xác định một chuỗi văn bản có phù hợp với một **mẫu** (*pattern*) chứa các ký hiệu đặc biệt hay không. Đây là ví dụ điển hình của **quy hoạch động trên dãy** (*sequence DP*): kết quả so khớp hai tiền tố được suy ra từ kết quả so khớp những tiền tố ngắn hơn.

Điều quan trọng nhất là **định nghĩa chính xác ngữ nghĩa của mẫu trước khi viết thuật toán**. Ký hiệu **?** có thể có nghĩa “đúng một ký tự”, **\*** có thể có nghĩa “không hoặc nhiều ký tự”; nhưng trong các ngôn ngữ mẫu khác nhau, cùng ký hiệu có thể mang ý nghĩa hoàn toàn khác. Chỉ sau khi chốt các quy tắc đó, ta mới thiết kế công thức chuyển trạng thái, chọn thứ tự tính, chứng minh kết quả và kiểm tra mã Java.

Bài này chọn một hợp đồng **wildcard đơn giản, khớp toàn bộ chuỗi**. Nó **không phải** cú pháp biểu thức chính quy (*regular expression – regex*) của Java, không tự có cú pháp escape và không có quy tắc phân cách thư mục đặc biệt. Để tránh nhập nhằng với emoji và các ký tự bổ sung Unicode, ví dụ Java 17+ định nghĩa “một ký tự” theo **Unicode code point**, không phải đơn vị UTF-16 \`char\`.

## 1. Chốt ngữ nghĩa trước khi giải

Cho văn bản \`text\` và mẫu \`pattern\`. Ta định nghĩa ba loại thành phần mẫu:

| Thành phần mẫu | Ý nghĩa trong bài này | Số ký tự văn bản được khớp |
|---|---|---|
| Ký tự thông thường, ví dụ \`a\`, \`.\`, \`[\` | Phải trùng **chính xác** ký tự đó | **Đúng 1** |
| \`?\` | Khớp **bất kỳ một** Unicode code point | **Đúng 1** |
| \`*\` | Khớp **bất kỳ chuỗi** Unicode code point, kể cả rỗng | **Từ 0 trở lên** |

Một mẫu được coi là khớp **chỉ khi toàn bộ mẫu giải thích được toàn bộ chuỗi văn bản**, không phải chỉ tìm thấy một đoạn con ở giữa.

**Ví dụ về cách hiểu:**

- \`a?c\` khớp \`abc\`, \`axc\`, nhưng **không** khớp \`ac\`, vì \`?\` không được khớp chuỗi rỗng.
- \`a*c\` khớp \`ac\` (dấu sao khớp rỗng), \`abc\`, \`abbbc\`.
- \`*.txt\` khớp \`file.txt\` nhưng không khớp \`file.TXT\` nếu giữ phân biệt chữ hoa/thường.
- \`*\` khớp cả chuỗi rỗng \`""\`.
- \`*?*\` yêu cầu **ít nhất một ký tự**, vì hai dấu sao có thể khớp rỗng nhưng \`?\` không thể.
- Mẫu rỗng \`""\` chỉ khớp văn bản rỗng.
- \`abc\` không khớp \`xabc\` hoặc \`abcd\` vì bài toán yêu cầu khớp **toàn bộ**.

**Một ký hiệu mẫu không mặc nhiên “ăn” tất cả.** Ví dụ \`a*c\` với văn bản \`abbbc\`: có thể cho \`*\` khớp \`bbb\` để phần \`c\` còn lại đúng; không thể cứ cho sao ăn đến cuối rồi kết luận thất bại. Thuật toán DP xem xét khả năng phân chia một cách hệ thống.

### Các giả định khác phải được công bố

Trong bài này:

1. **Phân biệt chữ hoa/thường:** \`A\` khác \`a\`; không chuẩn hóa chuỗi tự động.
2. **Toàn chuỗi, không phải tìm đoạn con:** cần tiêu thụ hết cả text và pattern.
3. **Dấu gạch chéo cũng là ký tự bình thường:** \`*\` có thể khớp \`/\` trong \`a/b\`. Đây **không** phải mọi loại glob đường dẫn của hệ điều hành.
4. **Không có cú pháp escape:** dấu \`*\` và \`?\` luôn là toán tử. Dấu gạch chéo ngược \`\\\` được hiểu là ký tự thông thường, không tự chuyển \`\\*\` thành dấu sao theo nghĩa chữ.
5. **Đơn vị ký tự là Unicode code point:** \`?\` khớp một code point, có thể được Java biểu diễn bằng một hoặc hai đơn vị \`char\` UTF-16.
6. **Không tự chuẩn hóa Unicode:** hai chuỗi hiển thị giống nhau nhưng có biểu diễn code point khác nhau có thể không khớp.

Nếu đề bài thật yêu cầu dấu sao **không** vượt qua dấu \`/\`, cho phép escape, dùng so khớp không phân biệt hoa/thường hoặc cần **tìm đoạn con**, phải thay đổi đặc tả và thuật toán tương ứng. Không được giữ nguyên lời giải rồi giả định rằng nó tự đáp ứng các ngữ nghĩa mới.

## 2. Phân biệt wildcard đơn giản, glob và regex

Cần tránh một nguồn nhầm lẫn phổ biến: ký hiệu \`?\` và \`*\` **không có ý nghĩa giống nhau trong tất cả các hệ thống mẫu**.

| Cú pháp | Ý nghĩa điển hình |
|---|---|
| Wildcard của bài học: \`?\` | Bất kỳ **đúng một** code point |
| Wildcard của bài học: \`*\` | Bất kỳ **0 hoặc nhiều** code point |
| Regex Java: \`.\` | Một ký tự theo quy tắc dấu chấm regex và chế độ dòng |
| Regex Java: \`.*\` | Lặp ký hiệu \`.\` từ 0 lần trở lên |
| Regex Java: \`x?\` | Phần tử **x** ngay trước dấu hỏi là tùy chọn |
| Regex Java: \`x*\` | Lặp phần tử **x** ngay trước dấu sao từ 0 lần trở lên |

Chẳng hạn mẫu wildcard \`a*b\` cho phép **bất kỳ dãy ký tự nào** nằm giữa a và b. Trong regex, \`a*b\` lại cho phép lặp **chữ a** rồi tới b; đó là hai ngôn ngữ mẫu khác nhau.

Lệnh Java \`String.matches(...)\` nhận **regex**, không trực tiếp nhận wildcard trong bài này. Không nên gọi \`"abc".matches("a*c")\` rồi coi kết quả là kiểm thử của mẫu wildcard \`a*c\`: regex \`a*c\` nói đến việc lặp chữ a, không phải một dãy ký tự tùy ý.

Các **glob** cho tên file/đường dẫn cũng không có một tiêu chuẩn thống nhất: một số API xử lý \`*\`, \`**\`, dấu \`/\`, dấu \`\\\` hoặc dấu chấm đầu tên file theo quy tắc riêng. Mẫu ở đây là **ngôn ngữ nhỏ do bài toán định nghĩa**, không tự kế thừa hành vi của \`PathMatcher\`, shell hoặc regex.

## 3. Định nghĩa trạng thái DP trên hai tiền tố

Gọi:

- \(T\) là dãy code point của văn bản, dài \(n\).
- \(P\) là dãy code point của mẫu, dài \(m\).
- \(dp[i][j]\) là **true** nếu **i code point đầu tiên của T** khớp toàn bộ **j code point đầu tiên của P**, và **false** nếu không.

Chỉ số:

\[
0\le i\le n,\qquad 0\le j\le m.
\]

Ta dùng \(T[i-1]\) và \(P[j-1]\) cho ký tự cuối của những tiền tố không rỗng. Giá trị cần trả về là:

\[
\boxed{dp[n][m]}.
\]

Cách định nghĩa này đặc biệt hữu ích vì cho phép các tiền tố rỗng \(i=0\) hoặc \(j=0\) xuất hiện tự nhiên trong bảng, giúp tránh nhiều điều kiện biên khó.

### Trạng thái cơ sở

Hai tiền tố rỗng luôn khớp nhau:

\[
dp[0][0]=true.
\]

Một mẫu rỗng **không** khớp một văn bản không rỗng:

\[
dp[i][0]=false\qquad(i>0).
\]

Văn bản rỗng chỉ có thể khớp mẫu gồm **toàn dấu sao** (mỗi sao chọn khớp rỗng). Do đó:

\[
dp[0][j]=
\begin{cases}
dp[0][j-1], & P[j-1]=*,\\
false, & \text{ngược lại}.
\end{cases}
\quad(j>0).
\]

Vì vậy:

~~~text
text = ""
pattern = ""       -> true
pattern = "*"      -> true
pattern = "**"     -> true
pattern = "*?*"    -> false
pattern = "a*"     -> false
~~~

**Không khởi tạo cả hàng 0 thành true.** Chỉ các tiền tố mẫu gồm toàn dấu sao mới khớp văn bản rỗng. Đặc biệt, \`?\` luôn đòi đúng một code point, nên \`dp[0][j]\` phải false khi mẫu chứa dấu hỏi hoặc ký tự thường chưa được tiêu thụ.

## 4. Công thức chuyển trạng thái theo ký hiệu cuối của mẫu

Giả sử \(i>0,j>0\). Xét code point cuối \(p=P[j-1]\) của tiền tố mẫu.

### Trường hợp 1: p là ký tự thông thường

Nó phải bằng code point cuối của tiền tố văn bản. Đồng thời, hai tiền tố còn lại phải khớp:

\[
dp[i][j]
=
(T[i-1]=p)\land dp[i-1][j-1].
\]

Ví dụ \`abc\` khớp \`abc\` vì ký tự c cuối trùng và tiền tố \`ab\` khớp \`ab\`. Ngược lại, \`abx\` không thể khớp \`abc\`, vì ký tự cuối khác nhau.

### Trường hợp 2: p là dấu hỏi \`?\`

Dấu hỏi thay thế **đúng một** code point bất kỳ. Sau khi tiêu thụ code point cuối của văn bản, hai tiền tố trước đó phải khớp:

\[
dp[i][j]=dp[i-1][j-1].
\]

Không cần so sánh giá trị \(T[i-1]\) vì dấu hỏi chấp nhận mọi code point. Tuy nhiên trường hợp \(i=0\) đã được xử lý riêng: dấu hỏi **không** khớp rỗng.

### Trường hợp 3: p là dấu sao \`*\`

Dấu sao chấp nhận chuỗi rỗng **hoặc** chuỗi không rỗng. Có hai khả năng:

1. **Sao khớp 0 ký tự:** bỏ dấu sao cuối mẫu, giữ nguyên i. Trạng thái cần kiểm tra là \(dp[i][j-1]\).
2. **Sao khớp ít nhất 1 ký tự:** cho sao tiêu thụ code point cuối của văn bản, nhưng **giữ dấu sao** trong mẫu để nó có thể khớp thêm các code point trước đó. Trạng thái cần kiểm tra là \(dp[i-1][j]\).

Do đó:

\[
\boxed{dp[i][j]=dp[i][j-1]\lor dp[i-1][j]\quad\text{khi }P[j-1]=*.}
\]

Đây là điểm quan trọng nhất của thuật toán. Nhánh **dp[i][j-1]** tương ứng \`*\` ăn rỗng; nhánh **dp[i-1][j]** tương ứng \`*\` ăn thêm một code point. Phải dùng **OR** vì chỉ cần tồn tại một cách phân chia làm toàn chuỗi khớp.

**Lỗi rất phổ biến:** viết \`dp[i-1][j-1]\` cho dấu sao, khiến dấu sao bị giới hạn đúng một ký tự, gần như trùng vai trò \`?\`. Một lỗi khác là chỉ dùng \`dp[i-1][j]\`, khiến \`*\` không còn khớp rỗng. Hai lỗi đều trái với hợp đồng ở phần 1.

### Tổng hợp chuyển trạng thái

Với \(i,j>0\):

\[
dp[i][j]=
\begin{cases}
dp[i][j-1]\lor dp[i-1][j], & P[j-1]=*,\\
dp[i-1][j-1], & P[j-1]=?,\\
dp[i-1][j-1]\land(T[i-1]=P[j-1]), & \text{ký tự thường}.
\end{cases}
\]

Nhìn vào các trạng thái phụ thuộc:

- **Trên:** \(dp[i-1][j]\).
- **Trái:** \(dp[i][j-1]\).
- **Chéo trên-trái:** \(dp[i-1][j-1]\).

Vì vậy khi tính **hàng i tăng và cột j tăng**, mọi trạng thái cần thiết đều đã được tính trước. Đây chính là một ví dụ của việc **chọn thứ tự tính theo quan hệ phụ thuộc** trong DP dãy.

## 5. Mô phỏng bảng: văn bản "ab", mẫu "a*"

Đặt các hàng tương ứng tiền tố của \`text="ab"\`, các cột tương ứng tiền tố của \`pattern="a*"\`.

| Tiền tố text \ Tiền tố pattern | \`""\` | \`"a"\` | \`"a*"\` |
|---|---|---|---|
| \`""\` | **T** | F | F |
| \`"a"\` | F | **T** | **T** |
| \`"ab"\` | F | F | **T** |

Giải thích từng ô cần chú ý:

- **dp[0][0]=true**: hai tiền tố rỗng khớp nhau.
- **dp[0][1]=false**: chữ a không thể khớp văn bản rỗng.
- **dp[0][2]=false**: dù mẫu kết thúc bằng sao, tiền tố trước nó là chữ a nên không thể chỉ dùng sao để khớp rỗng.
- **dp[1][1]=true**: chữ a khớp chính xác chữ a.
- **dp[1][2]=true**: dấu sao khớp rỗng, vì \(dp[1][1]=true\).
- **dp[2][1]=false**: chỉ mẫu a không thể tiêu thụ toàn bộ ab.
- **dp[2][2]=true**: dấu sao khớp thêm chữ b, vì \(dp[1][2]=true\).

Từ đó \`"ab"\` khớp \`"a*"\`. Nếu sửa mẫu thành \`"a?"\`, \`"ab"\` vẫn khớp nhưng \`"a"\` **không** khớp, vì \`?\` không được rỗng.

### Sao liên tiếp và nhiều cách khớp

Hai dấu sao liền nhau **có ngữ nghĩa tương đương một dấu sao** trong hợp đồng này, vì cả hai đều chấp nhận một chuỗi có độ dài bất kỳ:

~~~text
"*"       ~ "**"
"a*b"     ~ "a**b"
"**?**"   ~ "*?*"
~~~

Dấu \`~\` ở đây biểu thị **hai mẫu chấp nhận cùng một tập văn bản**, không phải ký hiệu có trong ngôn ngữ mẫu. Có thể **gộp các dấu sao liên tiếp** thành một dấu sao để giảm độ dài mẫu trước khi chạy DP; đó là tối ưu tùy chọn, không phải yêu cầu về tính đúng.

Một mẫu có thể có **nhiều cách phân chia ký tự** cho các dấu sao. DP chỉ cần trả true/false, nên không cần chọn xem dấu sao nào “tham lam” khớp nhiều nhất hoặc khớp ít nhất. Nếu bài toán cần **trích xuất chuỗi mà từng dấu sao đã khớp**, ta phải bổ sung quy tắc chọn lời giải và dữ liệu truy vết; không thể suy ra duy nhất từ một giá trị boolean.

## 6. Chứng minh DP khớp đúng ngữ nghĩa mẫu

Ta chứng minh bằng quy nạp theo tổng \(i+j\) rằng **dp[i][j] đúng khi và chỉ khi tiền tố văn bản dài i khớp tiền tố mẫu dài j**.

**Cơ sở.** Khi i=j=0, hai chuỗi rỗng khớp. Khi j=0 nhưng i>0, mẫu không có thành phần nào để tiêu thụ văn bản nên không khớp. Khi i=0, chỉ các dấu sao có thể tiêu thụ rỗng; quy tắc \(dp[0][j]=dp[0][j-1]\) cho sao và false cho ký hiệu khác xác định đúng mọi trường hợp.

**Bước quy nạp.** Giả sử các trạng thái nhỏ hơn theo tổng chỉ số đã chính xác. Với i,j>0:

- Nếu ký tự mẫu cuối là ký tự thường c, một khớp toàn phần tồn tại **khi và chỉ khi** ký tự văn bản cuối bằng c **và** hai tiền tố trước chúng khớp. Đó chính là công thức chéo.
- Nếu mẫu cuối là \`?\`, nó bắt buộc tiêu thụ đúng một code point cuối của văn bản; các phần trước phải khớp. Đó là công thức chéo không cần so c.
- Nếu mẫu cuối là \`*\`, trong mọi khớp hợp lệ, sao cuối hoặc tiêu thụ **0** code point (khi ấy bỏ sao giữ văn bản) hoặc tiêu thụ **ít nhất 1** code point (khi ấy bỏ một code point cuối của văn bản và giữ sao). Hai khả năng chính là hai trạng thái bên trái và phía trên. Ngược lại, nếu một trong hai trạng thái ấy đúng, ta luôn mở rộng được thành một khớp hợp lệ của hai tiền tố hiện tại.

Do đó công thức DP bao quát **đủ và chỉ** những trường hợp mà mẫu cho phép. Suy ra \`dp[n][m]\` là kết quả đúng của bài toán **khớp toàn bộ chuỗi**.

Một điểm cần để ý: cạnh phụ thuộc của ô sao **dp[i][j-1]** nằm bên trái trong cùng hàng, còn **dp[i-1][j]** ở hàng trước; cả hai có tổng chỉ số nhỏ hơn. Vì vậy thứ tự duyệt **hàng tăng, cột tăng** không có phụ thuộc vòng, và mã bottom-up có thể hoàn tất mọi trạng thái.

## 7. Độ phức tạp và kích thước trạng thái

Đặt \(n\) là số **Unicode code point** trong văn bản và \(m\) là số **Unicode code point** trong mẫu.

Bảng DP có **\((n+1)(m+1)\)** ô. Mỗi ô được xác định bằng tối đa hai trạng thái đã có, phép so sánh và phép OR/AND, đều tốn O(1). Vì vậy:

\[
T(n,m)=O((n+1)(m+1)).
\]

Thường viết ngắn gọn **O(nm)** khi cả n và m dương. **Bộ nhớ của bảng 2D** là \(O((n+1)(m+1))\).

Các trường hợp n=0 hoặc m=0 cũng đã được tính đúng trong công thức đầy đủ, không nên dùng biểu thức O(nm) một cách máy móc để suy luận rằng đầu vào một chiều rỗng thì thuật toán không tốn thời gian.

Nếu chuỗi có độ dài hàng chục nghìn code point, bảng 2D có thể quá lớn, dù công thức DP đúng. Có thể **nén bộ nhớ xuống một hàng** vì chỉ cần hàng trước và phần đã tính của hàng hiện tại. Phần tiếp theo giải thích cách giữ đúng quan hệ phụ thuộc khi làm như vậy.

**Lưu ý tiền xử lý Unicode trong Java:** chuyển một String thành mảng \`int[]\` code point bằng \`codePoints().toArray()\` cũng tốn O(n) hoặc O(m) thời gian và bộ nhớ. Do đó triển khai dùng mảng code point có thêm O(n+m) bộ nhớ ngoài bảng DP; khi đánh giá bộ nhớ cần tính cả phần này. Mã rolling sử dụng **O(m) cho trạng thái boolean**, nhưng toàn bộ chương trình vẫn có hai mảng code point O(n+m).

## 8. Nén DP từ 2D xuống một hàng

Quan sát một ô:

\[
dp[i][j]\leftarrow dp[i][j-1],\ dp[i-1][j],\ dp[i-1][j-1].
\]

Ta có thể lưu một mảng \`row[j]\`, ban đầu biểu diễn **hàng i=0**. Mỗi lần chuyển sang ký tự văn bản thứ i, duyệt **j tăng** từ 1 tới m.

Tại thời điểm cập nhật \`row[j]\`:

- \`row[j]\` **trước cập nhật** là \(dp[i-1][j]\) – giá trị **phía trên**.
- \`row[j-1]\` **đã cập nhật** là \(dp[i][j-1]\) – giá trị **bên trái**.
- Một biến \`previousDiagonal\` giữ \(dp[i-1][j-1]\) – giá trị **chéo trên-trái** được lưu từ trước.

Thuật toán nén:

~~~text
row[0] = true
for j = 1..m:
    row[j] = (pattern[j-1] là '*') AND row[j-1]

for i = 1..n:
    previousDiagonal = row[0]   // dp[i-1][0]
    row[0] = false              // dp[i][0], vì text hiện không rỗng

    for j = 1..m:               // BẮT BUỘC DUYỆT j TĂNG
        above = row[j]          // dp[i-1][j], chưa ghi đè

        if pattern[j-1] là '*':
            row[j] = row[j-1] OR above
        else if pattern[j-1] là '?':
            row[j] = previousDiagonal
        else:
            row[j] = previousDiagonal
                     AND (text[i-1] == pattern[j-1])

        previousDiagonal = above

return row[m]
~~~

Đặt \`previousDiagonal = above\` **sau** khi tính ô hiện tại giúp biến này trở thành \(dp[i-1][j]\), tức chéo của cột j+1 tiếp theo.

**Tại sao duyệt j tăng?** Với \`*\`, giá trị \`row[j-1]\` phải là trạng thái **cùng hàng hiện tại** \(dp[i][j-1]\). Nếu duyệt giảm, nó vẫn là trạng thái hàng trước, làm sai công thức. Với dấu hỏi và ký tự thường, cần lưu giá trị chéo từ hàng trước trước khi ghi đè \`row[j]\`.

Đây là bài học quan trọng của **DP dãy có nén bộ nhớ**: không chỉ chọn hướng lặp sao cho các chỉ số nhìn có vẻ hợp lý, mà phải kiểm tra **phiên bản của từng trạng thái** trước và sau phép cập nhật.

## 9. Java 17+: hai cách DP cho cùng một ngữ nghĩa

Chương trình sau triển khai đồng thời:

- **matches2D:** bảng boolean hai chiều, trực tiếp theo công thức.
- **matchesRolling:** mảng boolean một chiều, giữ biến giá trị chéo.

Hai hàm dùng chung một định nghĩa: \`?\` khớp đúng một **Unicode code point**, \`*\` khớp không hoặc nhiều code point; các ký tự còn lại là ký tự thường; so khớp **toàn bộ** chuỗi; phân biệt chữ hoa/thường; **không hỗ trợ escape**. Đầu vào null bị từ chối.

Lưu tệp **WildcardDpDemo.java**:

~~~java
import java.util.Objects;

public class WildcardDpDemo {
    static boolean matches2D(String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int[] t = text.codePoints().toArray();
        int[] p = pattern.codePoints().toArray();
        int n = t.length;
        int m = p.length;

        boolean[][] dp = new boolean[n + 1][m + 1];
        dp[0][0] = true;

        // Empty text matches only a prefix made entirely of '*'.
        for (int j = 1; j <= m; j++) {
            dp[0][j] = p[j - 1] == '*' && dp[0][j - 1];
        }

        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= m; j++) {
                int token = p[j - 1];
                if (token == '*') {
                    // '*' consumes nothing, or one/more code points.
                    dp[i][j] = dp[i][j - 1] || dp[i - 1][j];
                } else if (token == '?') {
                    // Exactly one code point.
                    dp[i][j] = dp[i - 1][j - 1];
                } else {
                    dp[i][j] = (t[i - 1] == token)
                        && dp[i - 1][j - 1];
                }
            }
        }
        return dp[n][m];
    }

    static boolean matchesRolling(String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int[] t = text.codePoints().toArray();
        int[] p = pattern.codePoints().toArray();
        int m = p.length;

        boolean[] row = new boolean[m + 1];
        row[0] = true;

        for (int j = 1; j <= m; j++) {
            row[j] = p[j - 1] == '*' && row[j - 1];
        }

        for (int i = 1; i <= t.length; i++) {
            boolean previousDiagonal = row[0];
            row[0] = false;

            for (int j = 1; j <= m; j++) {
                boolean above = row[j]; // old dp[i-1][j]
                int token = p[j - 1];

                if (token == '*') {
                    // Left is current row; above is previous row.
                    row[j] = row[j - 1] || above;
                } else {
                    row[j] = previousDiagonal
                        && (token == '?' || token == t[i - 1]);
                }
                previousDiagonal = above;
            }
        }
        return row[m];
    }

    public static void main(String[] args) {
        String[][] examples = {
            {"", ""},
            {"", "*"},
            {"", "**"},
            {"", "?"},
            {"a", ""},
            {"abc", "a?c"},
            {"ac", "a*c"},
            {"abbbc", "a*c"},
            {"abc", "a*d"},
            {"file.txt", "*.txt"},
            {"file.txt", "*.TXT"},
            {"猫😊", "??"},
            {"a/b", "a*b"},
            {"abc", "*?*"},
            {"", "*?*"},
            {"abc", "a*c?"},
            {"abc", ".*"}
        };

        for (String[] sample : examples) {
            String text = sample[0];
            String pattern = sample[1];
            boolean byTable = matches2D(text, pattern);
            boolean byRolling = matchesRolling(text, pattern);
            if (byTable != byRolling) {
                throw new AssertionError("DP implementations disagree");
            }
            System.out.println("\"" + text + "\" ~ \""
                + pattern + "\" = " + byTable);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac WildcardDpDemo.java
java WildcardDpDemo
~~~

**Stdout chính xác:**

~~~text
"" ~ "" = true
"" ~ "*" = true
"" ~ "**" = true
"" ~ "?" = false
"a" ~ "" = false
"abc" ~ "a?c" = true
"ac" ~ "a*c" = true
"abbbc" ~ "a*c" = true
"abc" ~ "a*d" = false
"file.txt" ~ "*.txt" = true
"file.txt" ~ "*.TXT" = false
"猫😊" ~ "??" = true
"a/b" ~ "a*b" = true
"abc" ~ "*?*" = true
"" ~ "*?*" = false
"abc" ~ "a*c?" = false
"abc" ~ ".*" = false
~~~

### Đọc kết quả và những điểm dễ hiểu nhầm

- **\`"" ~ "**"\` là true:** cả hai sao cùng chọn khớp rỗng.
- **\`"ac" ~ "a*c"\` là true:** dấu sao có thể khớp **0** code point, nên a ngay cạnh c vẫn hợp lệ.
- **\`"abbbc" ~ "a*c"\` là true:** dấu sao có thể khớp cả ba chữ b.
- **\`"file.txt" ~ "*.TXT"\` là false:** ví dụ không bật quy tắc bỏ qua khác biệt hoa/thường.
- **\`"猫😊" ~ "??"\` là true:** chuỗi gồm hai Unicode code point (chữ 猫 và emoji 😊). Một cách dùng \`char\` UTF-16 có thể đếm emoji thành hai đơn vị và cho kết quả khác; mã này đã chốt code point làm đơn vị.
- **\`"a/b" ~ "a*b"\` là true:** sao khớp dấu gạch chéo vì bài học **không có quy tắc tách thành phần đường dẫn**.
- **\`"abc" ~ ".*"\` là false:** dấu chấm là ký tự thường trong wildcard này, không phải dấu chấm của regex.
- **\`"abc" ~ "a*c?"\` là false:** sau khi đã đặt chữ c để khớp ký tự c của mẫu, dấu hỏi vẫn cần thêm một code point nhưng văn bản đã hết.

Chương trình không biến đổi dữ liệu đầu vào. Hai bản thực thi được so sánh với nhau cho mọi ví dụ: nếu có sai khác, chương trình ném AssertionError thay vì in một kết quả khó phát hiện. Đối với tập kiểm thử thực tế, vẫn nên **đối chiếu với một oracle độc lập** hoặc exhaustive tests trên chuỗi ngắn, vì hai triển khai có thể cùng chia sẻ một lỗi thiết kế nếu ngữ nghĩa được hiểu sai.

## 10. Thử nhiều ca biên theo ngữ nghĩa

| Văn bản | Mẫu | Khớp? | Lý do |
|---|---|---|---|
| \`""\` | \`""\` | True | Hai chuỗi rỗng |
| \`""\` | \`"***"\` | True | Mọi sao khớp rỗng |
| \`""\` | \`"?*"\` | False | Hỏi cần đúng một ký tự |
| \`"a"\` | \`"*"\` | True | Sao khớp một ký tự |
| \`"abc"\` | \`"a?c"\` | True | Hỏi khớp b |
| \`"ac"\` | \`"a?c"\` | False | Thiếu một ký tự cho hỏi |
| \`"ac"\` | \`"a*c"\` | True | Sao khớp rỗng |
| \`"abbbc"\` | \`"a*c"\` | True | Sao khớp bbb |
| \`"abc"\` | \`"a*d"\` | False | Ký tự d ở cuối không khớp |
| \`"abc"\` | \`"abc*"\` | True | Sao cuối khớp rỗng |
| \`"abc"\` | \`"*bc"\` | True | Sao đầu khớp a |
| \`"xabc"\` | \`"abc"\` | False | Chỉ khớp đoạn cuối, không khớp toàn bộ |
| \`"abcx"\` | \`"abc"\` | False | Còn ký tự x chưa tiêu thụ |
| \`"aaa"\` | \`"a*a"\` | True | Sao khớp một chữ a |
| \`"aba"\` | \`"a*a"\` | True | Sao khớp b |
| \`"😊"\` | \`"?"\` | True | Emoji là một code point |
| \`"😊"\` | \`"??"\` | False | Chỉ có một code point |
| \`"a/b"\` | \`"a*b"\` | True | Sao được khớp dấu / trong hợp đồng này |

Một bảng kiểm thử tốt nên bao gồm: mẫu rỗng, văn bản rỗng, nhiều sao liên tiếp, sao ở đầu/cuối/giữa, nhiều dấu hỏi, khóa chữ thường có phân biệt hoa/thường, Unicode, và các trường hợp **chỉ khớp một đoạn con**.

### Một khác biệt Unicode cần biết

Trong Java, \`String.length()\` đếm **đơn vị mã hóa UTF-16**, không phải số Unicode code point hay số “ký tự nhìn thấy được” (*grapheme cluster*). Emoji 😊 thường chiếm **hai** đơn vị \`char\` nhưng **một** code point. Do đó \`"?":\` theo code point có thể khớp 😊.

Mặt khác, một ký tự nhìn thấy được có thể gồm **nhiều code point**. Ví dụ chữ e + dấu sắc kết hợp (một chữ e và một dấu kết hợp riêng) có thể chiếm hai code point dù hiển thị như **é**. Nếu mẫu \`?\` có nghĩa “một grapheme cluster theo cảm nhận người dùng”, dùng \`codePoints()\` **chưa đủ**: phải phân đoạn grapheme theo quy tắc Unicode phù hợp và cân nhắc chuẩn hóa. Bài học **chủ động chọn code point**, không ngầm cam kết mọi khái niệm “ký tự” đều tương đương nhau.

## 11. Vì sao không thể chỉ dùng tìm kiếm tham lam đơn giản?

Một cách nghĩ tự nhiên khi gặp dấu sao là cho nó khớp **nhiều ký tự nhất** rồi so phần còn lại. Nhưng điều đó có thể thất bại dù tồn tại một cách khớp khác.

Ví dụ:

~~~text
text    = "abbbc"
pattern = "a*c"
~~~

Nếu \`*\` lập tức tiêu thụ toàn bộ đoạn \`bbbc\`, mẫu còn chữ c nhưng văn bản đã hết, dẫn đến thất bại giả. Cách khớp đúng là để sao tiêu thụ \`bbb\` và giữ chữ c cuối cho ký tự c của mẫu.

Có những thuật toán **tham lam kết hợp quay lui có kiểm soát** (*greedy with remembered star*) giải bài toán wildcard đơn giản này bằng ít bộ nhớ hơn, nhưng không thể khẳng định mọi biến thể đều chạy O(n+m) trong trường hợp xấu nhất. Phải phân tích hành vi quay lui trên đầu vào đối kháng.

DP ưu tiên **tính đúng dễ kiểm chứng**: mỗi cặp tiền tố được xét tối đa một lần, không cần đoán dấu sao phải tiêu thụ bao nhiêu ký tự. Khi chỉ cần yes/no, bản rolling dùng ít bộ nhớ trạng thái; khi cần truy vết cách khớp, bảng 2D có thể tiện hơn.

### Top-down với memoization cũng hợp lệ

Có thể định nghĩa hàm \`match(i,j)\` trả lời **hai hậu tố** bắt đầu ở i và j có khớp hay không:

- Nếu j đã tới cuối mẫu, chỉ đúng khi i cũng tới cuối văn bản.
- Nếu ký hiệu hiện tại là sao, thử **bỏ sao** hoặc **ăn một ký tự và giữ sao**.
- Nếu là hỏi hoặc ký tự thường phù hợp, tiến đồng thời i+1, j+1.

Ghi nhớ kết quả cho mỗi cặp (i,j) giúp tránh tính lặp vô số nhánh giống nhau, tạo cận **O((n+1)(m+1))** trạng thái. Nhưng đệ quy có thể sâu và gây StackOverflowError trên văn bản dài; bottom-up hoặc rolling DP phù hợp hơn khi cần kiểm soát ngăn xếp. Với top-down, cần bảo đảm mỗi lời gọi chuyển sang cặp chỉ số có tiến triển, thay vì gọi lại chính trạng thái.

## 12. Mở rộng đặc tả: escape, tìm đoạn con và glob đường dẫn

Các yêu cầu dưới đây **khác** bài toán đã cài; nếu đề bài thực tế cần, phải bổ sung ngữ nghĩa và kiểm thử riêng.

### 12.1. Muốn khớp dấu sao hoặc hỏi theo nghĩa chữ

Ngôn ngữ mẫu hiện tại **không có escape**: dấu sao và hỏi luôn là toán tử. Muốn mẫu biểu thị **dấu sao literal**, có thể thiết kế cú pháp escape, ví dụ một dấu gạch chéo ngược đứng trước \`*\` khiến nó thành ký tự thường.

Khi đó nên **phân tích mẫu thành token trước khi DP**, ví dụ:

~~~text
LITERAL('*')
LITERAL('?')
ANY_ONE
ANY_MANY
LITERAL('a')
~~~

Mỗi token mang **loại** riêng, không chỉ code point. Lúc này một token LITERAL('*') phải được xử lý như ký tự thường dù hình dạng ký hiệu giống dấu sao. Cần quy định escape dấu gạch chéo ngược, escape ở cuối mẫu, và các chuỗi escape không hợp lệ. Không được đơn giản xóa dấu \`\\\` rồi tiếp tục coi dấu \`*\` sau nó là wildcard.

### 12.2. Muốn tìm mẫu ở bất kỳ đoạn con nào

Khớp **toàn bộ** văn bản với pattern khác với câu hỏi “có tồn tại một đoạn con khớp pattern không?”.

Ví dụ văn bản \`"xabcx"\` và mẫu \`"abc"\`:

- **Full match:** false.
- **Substring search:** true, vì đoạn con từ chỉ số 1 đến 3 theo vị trí code point khớp.

Có thể thiết kế DP cho tìm đoạn con, dùng thuật toán tìm kiếm phù hợp hoặc bao pattern bằng dấu sao **nếu hợp đồng cho phép sao khớp mọi ký tự**. Nhưng thao tác biến đổi đó không phải quy tắc tự động khi mẫu dùng regex hoặc glob đường dẫn.

### 12.3. Muốn khớp đường dẫn có dấu phân cách

Một số glob đường dẫn dùng \`*\` để khớp ký tự **trong cùng một thành phần đường dẫn** còn \`**\` có thể khớp qua nhiều thành phần. Trong bài học này cả \`*\` và \`**\` đều khớp một dãy code point bất kỳ, kể cả \`/\`. Vì thế:

~~~text
text = "a/b"
pattern = "a*b"
result = true
~~~

Nếu dùng trong hệ thống file, cần định nghĩa rõ dấu phân cách, cách xử lý đường dẫn tuyệt đối/tương đối, chữ hoa/thường, escape và cấu trúc thư mục; không nên tái sử dụng nguyên xi hàm ở trên mà không thay hợp đồng.

### 12.4. Muốn chuẩn hóa Unicode hoặc bỏ phân biệt hoa/thường

Hai chuỗi có thể trông giống nhau nhưng khác biểu diễn Unicode (ví dụ một code point dựng sẵn so với chữ cái cộng dấu kết hợp). Nếu ứng dụng cần coi chúng tương đương, hãy công bố quy tắc chuẩn hóa, áp dụng nhất quán cho **văn bản và phần literal của mẫu** mà không làm thay đổi ý nghĩa wildcard; lưu ý việc case folding/normalization trong Unicode có thể làm thay đổi số lượng code point. Không nên áp dụng một phép chuyển chuỗi rồi khẳng định nó giữ nguyên mọi quy tắc về \`?\` nếu chưa xét ảnh hưởng tới đơn vị khớp.

## 13. Chi phí thực tế và các lựa chọn triển khai

| Cách giải | Thời gian | Bộ nhớ trạng thái DP | Ưu điểm / giới hạn |
|---|---|---|---|
| DP hai chiều | O((n+1)(m+1)) | **O((n+1)(m+1))** | Rõ ràng, dễ truy vết và chứng minh |
| DP một chiều | O((n+1)(m+1)) | **O(m+1)** | Hợp với trả true/false; cần nắm rõ giá trị hàng cũ/mới |
| Top-down + memo | O((n+1)(m+1)) trạng thái | O(nm) cache + stack | Chỉ duyệt trạng thái cần tới, nhưng có nguy cơ stack sâu |
| Greedy có nhớ dấu sao | Phụ thuộc cài đặt; cần phân tích riêng | Có thể O(1) biến trạng thái | Hữu ích khi cần rất ít bộ nhớ, nhưng dễ sai khi quay lui |

Các dòng DP trên còn có chi phí lưu \`int[]\` code point **O(n+m)** trong ví dụ Java; cột bộ nhớ trạng thái DP **chưa bao gồm** mảng chuyển Unicode. Nếu cần tiết kiệm hơn, có thể thay đổi cách lặp qua văn bản/mẫu mà vẫn đảm bảo truy cập code point đúng cách, nhưng phải giữ bất biến chỉ số và chú ý UTF-16.

Có thể tối ưu thêm bằng cách **gộp sao liên tiếp** trước khi tính, hoặc sớm từ chối nếu mẫu chứa nhiều token không-sao hơn số code point văn bản: mỗi token không-sao tiêu thụ đúng một code point, nên nếu số đó lớn hơn n thì chắc chắn không khớp. Đây là các tối ưu **không thay đổi ngữ nghĩa** trong hợp đồng đã chọn, nhưng không cần thiết để thuật toán cơ bản đúng.

Không nên đánh giá “DP chậm” chỉ dựa trên độ dài String Java: số **code point** có thể khác String.length(), và số trạng thái phụ thuộc n,m sau khi thống nhất đơn vị. Với dữ liệu quá lớn, cần ước lượng \((n+1)(m+1)\) trước khi cấp phát bảng 2D.

## 14. Các lỗi thường gặp

1. **Không định nghĩa \`?\` và \`*\`** mà mặc nhiên hiểu theo regex, glob hoặc shell khác nhau.
2. **Dùng \`String.matches(pattern)\` của Java** cho wildcard đơn giản và mong \`*\` tự khớp mọi chuỗi: \`String.matches\` dùng regex.
3. **Quên yêu cầu khớp toàn bộ:** trả true khi chỉ một đoạn con khớp.
4. **Cho \`?\` khớp rỗng:** làm sai các mẫu như \`?*\` trên văn bản rỗng.
5. **Cho \`*\` bắt buộc khớp ít nhất một ký tự:** làm \`ac\` không khớp \`a*c\`.
6. **Viết sai chuyển sao thành chéo trên-trái:** dấu sao sẽ hành xử gần như dấu hỏi, không thể khớp nhiều ký tự.
7. **Chỉ thử nhánh sao ăn một ký tự** mà quên nhánh sao ăn 0 ký tự.
8. **Dùng AND thay OR cho hai nhánh sao:** đòi cả hai cách phân chia cùng đúng, trong khi chỉ cần một cách.
9. **Khởi tạo sai hàng dp[0][j]:** chỉ tiền tố pattern toàn dấu sao mới khớp text rỗng.
10. **Khởi tạo dp[i][0] thành true khi i>0:** làm mẫu rỗng khớp chuỗi khác rỗng.
11. **Nhầm chỉ số tiền tố với chỉ số ký tự:** dp[i][j] dùng T[i-1],P[j-1] ở công thức không rỗng.
12. **Duyệt rolling DP theo cột giảm:** nhánh sao cần giá trị **bên trái ở hàng hiện tại**, không phải hàng trước.
13. **Ghi đè dp[j] trước khi lưu giá trị chéo:** mất dp[i-1][j] cần cho cột tiếp theo.
14. **Coi Java \`char\` luôn là một Unicode code point:** emoji bổ sung có thể gồm cặp surrogate UTF-16.
15. **Nhầm code point với grapheme nhìn thấy:** một chữ có dấu kết hợp có thể gồm nhiều code point.
16. **Mặc nhiên hỗ trợ escape hoặc phân cách thư mục:** nếu chưa định nghĩa trong ngôn ngữ mẫu, chương trình không có các quy tắc đó.
17. **Không kiểm thử trường hợp chỉ khớp đoạn con:** ví dụ \`"xabc"\` với \`"abc"\` phải false trong full matching.
18. **Khẳng định thời gian O(n+m) cho DP hai tiền tố:** số cặp trạng thái lên đến \((n+1)(m+1)\).
19. **Không kiểm tra null đầu vào:** có thể gây lỗi khó hiểu hoặc ngầm thay đổi hợp đồng.
20. **Gộp quá nhiều tính năng ngoài đặc tả** (nhóm regex, escape, dấu ngoặc, tính hoa/thường) khiến công thức chuyển không còn tương ứng với ngữ nghĩa được chứng minh.

## 15. Bài tập tự kiểm tra

**Bài 1 — Sao khớp rỗng.** Văn bản \`"ac"\` có khớp mẫu \`"a*c"\` không? Trong bảng DP, chọn nhánh nào cho dấu sao?

*Đáp án:* **Có.** Dấu sao tiêu thụ **0** code point, nên dùng nhánh bỏ sao \`dp[i][j-1]\` tại thời điểm thích hợp.

**Bài 2 — Dấu hỏi bắt buộc một ký tự.** Mẫu \`"*?*"\` có khớp chuỗi rỗng không? Có khớp \`"x"\` không?

*Đáp án:* **Không** khớp rỗng, vì dấu hỏi cần đúng một code point. **Có** khớp \`"x"\`, vì hai dấu sao khớp rỗng và dấu hỏi khớp x.

**Bài 3 — Công thức dấu sao.** Giải thích hai trạng thái cần dùng khi token cuối của mẫu là \`*\`.

*Đáp án:* **dp[i][j-1]** là trường hợp sao ăn 0 ký tự; **dp[i-1][j]** là trường hợp sao ăn thêm ít nhất một ký tự cuối của văn bản và vẫn còn có thể ăn tiếp. Hai nhánh kết hợp bằng **OR**.

**Bài 4 — Duyệt bảng.** Vì sao duyệt i tăng, j tăng là một thứ tự hợp lệ để tính bảng DP?

*Đáp án:* Mỗi ô chỉ phụ thuộc **trên**, **trái** hoặc **chéo trên-trái**, đều đã hoàn tất trước khi tới ô hiện tại theo thứ tự đó.

**Bài 5 — Nén hàng.** Trong rolling DP, ngay trước khi cập nhật row[j] ở hàng i, ba giá trị tương ứng ô trên, trái, chéo là gì?

*Đáp án:* Ô **trên** là row[j] cũ; ô **trái** là row[j-1] vừa cập nhật; ô **chéo** là biến previousDiagonal giữ giá trị hàng trước ở cột j-1. Sau cập nhật phải đưa row[j] cũ vào previousDiagonal cho bước kế tiếp.

**Bài 6 — Regex và wildcard.** \`"abc"\` có khớp wildcard \`".*"\` trong hợp đồng bài này không? Vì sao khác regex?

*Đáp án:* **Không.** Dấu chấm wildcard ở đây là ký tự literal, nên chuỗi phải bắt đầu bằng dấu chấm mới có thể khớp mẫu đó. Trong regex, \`.\` mang ý nghĩa đặc biệt khác.

**Bài 7 — Unicode.** Vì sao \`"😊"\` khớp \`"?"\` với mã Java trong bài, trong khi \`String.length()\` của emoji có thể bằng 2?

*Đáp án:* Mã chuyển String thành **Unicode code point** trước khi DP; 😊 là một code point nhưng được Java biểu diễn bằng hai đơn vị UTF-16 \`char\`. Dấu hỏi trong hợp đồng đòi một **code point**, không phải một đơn vị \`char\`.

**Bài 8 — Thiết kế escape.** Nếu cần mẫu khớp dấu sao literal, có thể giữ nguyên cách nhận dạng \`*\` trong DP không?

*Đáp án:* **Không.** Phải bổ sung cú pháp escape hoặc token hóa mẫu để phân biệt **LITERAL('*')** với toán tử **ANY_MANY**. Sau đó mỗi token được xử lý theo đúng ngữ nghĩa của nó.

**Ghi nhớ:** Bắt đầu bằng **đặc tả ngôn ngữ mẫu**, không bắt đầu bằng vòng lặp. Với full-match wildcard \`?\` = đúng một code point, \`*\` = không hoặc nhiều code point, đặt **dp[i][j] = hai tiền tố dài i và j khớp nhau**. Ký tự thường và hỏi phụ thuộc ô chéo; sao phụ thuộc **ô trái OR ô trên**. Tính bảng theo **hàng tăng, cột tăng** để tôn trọng phụ thuộc; có thể nén xuống một hàng nếu giữ đúng giá trị trên/trái/chéo. Tính đúng đến từ việc **ngữ nghĩa mẫu và công thức chuyển trạng thái nhất quán với nhau**.
