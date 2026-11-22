# So khớp trực tiếp và các tình huống tốn nhiều phép so sánh

**So khớp chuỗi trực tiếp (naive / brute-force string matching)** là cách tìm một mẫu `P` trong một văn bản `T` bằng việc **thử từng vị trí bắt đầu có thể**, rồi so sánh các ký tự của mẫu theo thứ tự cho tới khi gặp sai khác hoặc khớp đủ mẫu. Cách tiếp cận này ngắn gọn, dễ kiểm chứng và phù hợp làm thuật toán nền để hiểu KMP, Z-algorithm hay những kỹ thuật bỏ qua vị trí của Boyer–Moore. Nhưng nếu văn bản và mẫu có **nhiều tiền tố giống nhau trước khi sai khác**, nó có thể thực hiện **rất nhiều phép so sánh lặp lại**.

Bài học thuộc nhóm **Tìm kiếm chuỗi** của Computer Science Algorithms. Ta sẽ làm rõ định nghĩa một lần so sánh và một vị trí căn chỉnh, thuật toán tìm **lần đầu** và **tất cả** lần xuất hiện, khớp **chồng lấn**, công thức đếm chính xác số ký tự được kiểm tra, các tình huống gây cận xấu nhất, cách phân biệt cận trên với chi phí thực, chứng minh đúng, phân tích thời gian/bộ nhớ, lưu ý Java 17 và Unicode, cùng chương trình kiểm thử độc lập cho hàng trăm đầu vào.

## 1. Đặc tả bài toán tìm kiếm mẫu

Cho hai chuỗi:

- **Văn bản (text)** `T` có độ dài `n`.
- **Mẫu (pattern)** `P` có độ dài `m`.
- Đánh số chỉ mục bắt đầu từ **0**.

Ta muốn tìm chỉ số `s` sao cho toàn bộ mẫu trùng với đoạn văn bản bắt đầu tại đó:

`T[s + j] == P[j]` với mọi `j = 0, 1, …, m−1`.

Một lần xuất hiện hợp lệ có chỉ số đầu `s` thỏa:

`0 ≤ s ≤ n−m`.

Với `m>0` và `m≤n`, số **vị trí căn chỉnh có thể thử** là:

`q = n−m+1`.

Trong bài, **một phép so sánh ký tự** là một lần thuật toán kiểm tra hai đơn vị ký tự `T[s+j]` và `P[j]` có bằng nhau hay không. Đếm **phép so sánh thực sự** khác đếm số vị trí thử, số vòng lặp hay thời gian thực trên đồng hồ.

### Tìm vị trí đầu tiên hay tìm tất cả?

Hai nhiệm vụ gần nhau nhưng chi phí có thể khác rất nhiều:

1. **Find first:** trả chỉ số bắt đầu nhỏ nhất của lần xuất hiện, hoặc `-1` nếu không có. Có thể **dừng ngay** khi gặp một lần khớp hoàn toàn.
2. **Find all:** trả mọi vị trí bắt đầu có khớp, theo thứ tự tăng dần. Phải tiếp tục xem các vị trí còn lại, kể cả sau khi đã tìm được lần khớp đầu tiên.

Ví dụ:

~~~text
T = "bananana"
P = "ana"

Các đoạn khớp bắt đầu tại: 1, 3, 5
Find first: 1
Find all:   [1, 3, 5]
~~~

Các lần xuất hiện có thể **chồng lấn** nhau. Nếu tìm tất cả, không được tự nhảy từ một lần khớp qua `m` vị trí trừ khi đề yêu cầu **chỉ các lần khớp không giao nhau**.

### Quy ước mẫu rỗng

Cần nêu hợp đồng rõ ràng vì mẫu `P=""` không chứa ký tự để so sánh. Trong bài và chương trình Java:

- Mẫu rỗng khớp tại **mọi ranh giới** của chuỗi, tức các vị trí `0,1,…,n` (tổng `n+1` vị trí).
- `findFirst(T,"") = 0`.
- Số **phép so sánh ký tự** của hai biến thể bằng **0**.

Ví dụ `T="abc"`, `P=""` ⇒ `findAll=[0,1,2,3]`, 0 phép so sánh ký tự. Nếu `T=""` và `P=""`, tập kết quả là `[0]`. Đây là một **quy ước được công bố**, không phải mặc nhiên đúng cho mọi hệ thống tìm kiếm. Với ứng dụng khác, mẫu rỗng có thể được xem là đầu vào không hợp lệ; khi đó cần kiểm tra và báo lỗi ngay.

### Nếu mẫu dài hơn văn bản

Khi `m>n`, không có đủ `m` ký tự liên tiếp để chứa mẫu. Do đó `findAll=[]`, `findFirst=-1`, và **0 phép so sánh ký tự** nếu ta kiểm tra độ dài trước vòng lặp.

Với mẫu không rỗng dài đúng bằng văn bản (`m=n`), chỉ có **một** vị trí căn chỉnh `s=0`; chưa chắc phải so đủ `m` ký tự vì có thể sai ngay ở ký tự đầu.

## 2. Thuật toán so khớp trực tiếp

Ý tưởng: đặt mẫu `P` dưới văn bản `T` tại mỗi vị trí `s=0,1,...,n−m`; so sánh từ trái qua phải.

~~~text
T = a b c a b c a
P =     a b c

Ở s=0: so a với a, rồi b với b, rồi c với c → khớp.
Ở s=1: so b với a → sai ngay, dừng kiểm tra s=1.
Ở s=2: so c với a → sai ngay.
Ở s=3: so a,b,c với a,b,c → khớp.
...
~~~

### Giả mã tìm tất cả vị trí

~~~text
DIRECT_MATCH_ALL(T, P):
    n = length(T)
    m = length(P)
    result = empty list

    IF m == 0:
        RETURN [0, 1, ..., n]
    IF m > n:
        RETURN []

    FOR shift = 0 TO n-m:
        j = 0
        WHILE j < m:
            IF T[shift+j] != P[j]:
                BREAK
            j = j+1

        IF j == m:
            APPEND shift TO result

    RETURN result
~~~

Vì `shift` tăng **đúng 1** mỗi lượt, thuật toán không bỏ mất lần khớp chồng lấn. Nó không tạo các bản sao substring mới; chỉ đọc ký tự tại hai chỉ số.

### Giả mã tìm lần đầu

~~~text
DIRECT_MATCH_FIRST(T, P):
    n = length(T)
    m = length(P)

    IF m == 0: RETURN 0
    IF m > n:  RETURN -1

    FOR shift = 0 TO n-m:
        j = 0
        WHILE j < m AND T[shift+j] == P[j]:
            j = j+1
        IF j == m:
            RETURN shift

    RETURN -1
~~~

Điểm khác nhau quan trọng: `findFirst` trả kết quả **ngay** ở vị trí khớp đầu tiên, còn `findAll` bắt buộc tiếp tục các vị trí sau đó.

### Giả mã đếm phép so sánh

Nếu cần thống kê, đếm ngay trước mỗi lần đối chiếu ký tự:

~~~text
comparisons = 0
FOR shift = 0 TO n-m:
    j = 0
    WHILE j < m:
        comparisons += 1
        IF T[shift+j] != P[j]:
            BREAK
        j += 1
    IF j == m:
        REPORT_MATCH(shift)
~~~

**Không tăng biến so sánh** khi chỉ đang kiểm tra điều kiện `j<m`, tăng `shift`, thêm kết quả vào danh sách hoặc duyệt vòng for. Đó là những thao tác thuật toán khác, không phải `T[shift+j] == P[j]`. Muốn đo tổng thời gian thực, phải xét cả overhead này; bảng trong bài chỉ thống kê phép **so sánh ký tự**.

## 3. Một lần căn chỉnh tốn bao nhiêu phép so sánh?

Ở vị trí `s`, xét tiền tố chung dài nhất của mẫu và đoạn văn bản bắt đầu tại `s`. Gọi `L_s` là số ký tự đầu tiên trùng nhau (tối đa `m`).

- Nếu `L_s=m`, mẫu khớp hoàn toàn; đã so sánh **m** ký tự.
- Nếu `L_s<m`, các ký tự `0..L_s−1` trùng, còn ký tự tại `L_s` **khác nhau**; phải thực hiện **L_s+1** phép so sánh để phát hiện sai khác.

Viết gọn:

`C_s = min(m, L_s+1)`.

Tổng số phép so sánh của `findAll` khi `1≤m≤n` là:

`C_all = Σ_{s=0}^{n−m} C_s`.

Vì `1≤C_s≤m`, ta có:

`n−m+1 ≤ C_all ≤ m(n−m+1)`.

Đây là **cận cho số phép so sánh ký tự**. Với mẫu rỗng, quy tắc riêng ở mục 1 cho `C_all=0`; không áp công thức có `m=0` rồi suy ra phải thực hiện phép đối chiếu.

### Khi nào dừng sớm có ích?

Nếu `P[0]` khác ngay `T[s]` ở mọi vị trí `s`, thì **mỗi vị trí chỉ tốn 1** phép so sánh. Nếu hầu hết căn chỉnh sai ở ký tự thứ hai, chi phí gần `2q`, thay vì `mq`.

Ngược lại, nếu rất nhiều căn chỉnh cùng có tiền tố dài `m−1` với mẫu nhưng sai ở ký tự cuối, mỗi vị trí sẽ tốn đúng **m** phép so sánh, dù **không có khớp nào**.

## 4. Trường hợp xấu nhất: rất nhiều ký tự giống nhau

Ví dụ trực quan nhất:

~~~text
T = "aaaaaaaa"    n=8
P = "aaab"        m=4
q = n-m+1 = 5
~~~

Thử mỗi vị trí:

| shift | Đoạn T dài 4 | So sánh lần 1 | 2 | 3 | 4 | Kết quả |
| ---: | --- | --- | --- | --- | --- | --- |
| 0 | `aaaa` | a=a | a=a | a=a | a≠b | Sai ở j=3 |
| 1 | `aaaa` | a=a | a=a | a=a | a≠b | Sai ở j=3 |
| 2 | `aaaa` | a=a | a=a | a=a | a≠b | Sai ở j=3 |
| 3 | `aaaa` | a=a | a=a | a=a | a≠b | Sai ở j=3 |
| 4 | `aaaa` | a=a | a=a | a=a | a≠b | Sai ở j=3 |

Tổng:

`C_all = 5 × 4 = 20` phép so sánh.

`findAll=[]` và `findFirst=-1` vì mẫu có chữ `b` cuối trong khi văn bản không có `b`. Cả hai phương pháp vẫn phải kiểm tra **mọi vị trí** và **tới ký tự cuối**.

### Tổng quát hóa

Lấy `T = a^n` (n ký tự `a`) và `P = a^(m−1)b` với `b≠a`, `1≤m≤n` (riêng `m=1` thì mẫu là `b`).

Mỗi căn chỉnh chứa `m−1` ký tự `a` trùng mẫu trước khi so sánh ký tự cuối `a` với `b` và thất bại. Do đó:

`C_all = C_first = m(n−m+1)`.

**Đây là trường hợp xấu nhất chính xác** của thuật toán trực tiếp khi xét n, m cụ thể, không chỉ là cận O(nm).

Ví dụ lớn để thấy sức nặng: với `n=2 000 000`, `m=2 000`, số căn chỉnh là `1 998 001`, nên có thể cần:

`1 998 001 × 2 000 = 3 996 002 000` phép so sánh ký tự.

Con số này vượt giới hạn của `int` có dấu 32 bit trong Java, vì vậy thống kê nên dùng **long**. Đây chỉ là **ước tính số phép so sánh theo công thức**, không phải thời gian thực tế đo bằng mili giây.

### Vì sao chuỗi lặp gây hại?

Các vị trí gần nhau dùng lại phần lớn vùng văn bản. Thuật toán trực tiếp **không lưu lại** kiến thức “đã có một tiền tố trùng nhau” để tận dụng ở lần dịch mẫu kế tiếp. Vì vậy, với văn bản lặp `aaaaaaaa...`, mỗi lần dịch thêm 1 vị trí lại so từ đầu chuỗi mẫu.

Các thuật toán như **KMP** phân tích trước cấu trúc tiền tố/hậu tố để tránh so lại những đoạn đã biết; đây là động cơ nghiên cứu thuật toán tuyến tính, không phải lý do thay đổi định nghĩa của direct matching.

## 5. Nhiều khớp cũng có thể đạt chi phí tối đa

Chi phí cực đại **không nhất thiết do thất bại**.

~~~text
T = "aaaaaaaa"  n=8
P = "aaaa"      m=4
~~~

Có 5 lần khớp tại `[0,1,2,3,4]`. Vì ở mỗi vị trí phải xác nhận cả 4 ký tự, `findAll` dùng:

`5 × 4 = 20` phép so sánh.

Nhưng `findFirst` tìm thấy ngay tại s=0, chỉ cần **4** phép so sánh và dừng.

Đây là phản ví dụ cho suy nghĩ “nhiều lần xuất hiện khiến so khớp trực tiếp chạy nhanh hơn”. Đối với **findAll**, những lần khớp hoàn toàn lại yêu cầu so đủ mẫu tại từng vị trí.

### Khớp chồng lấn

~~~text
T = "ababa"
P = "aba"

Match s=0: T[0..2] = "aba"
Match s=2: T[2..4] = "aba"

Find all = [0,2]
~~~

Nếu sau khi khớp ở s=0 lại nhảy sang s=3, thuật toán sẽ **bỏ sót vị trí 2**. Với tìm tất cả lần xuất hiện, thuật toán trực tiếp tăng shift từng 1 ngay cả sau một khớp.

**Phân biệt bài toán:** nếu đề hỏi các lần xuất hiện **không giao nhau**, ta có thể cần chính sách lựa chọn như “lấy khớp trái nhất rồi nhảy qua m ký tự”. Đó là một đầu ra khác; đừng vô tình áp dụng khi đề cần mọi vị trí.

## 6. Khớp gần hết rồi thành công rất muộn

Xét:

~~~text
T = "aaaaaab"    n=7
P = "aaab"       m=4
~~~

Có 4 vị trí bắt đầu `s=0..3`. Ở ba vị trí đầu, các ký tự `a,a,a` đều trùng và khác ở ký tự cuối; tại s=3, toàn bộ `aaab` khớp.

| s | Số phép so sánh | Kết quả |
| ---: | ---: | --- |
| 0 | 4 | Sai ở ký tự cuối |
| 1 | 4 | Sai ở ký tự cuối |
| 2 | 4 | Sai ở ký tự cuối |
| 3 | 4 | Khớp |

Vì thế:

`findAll=[3], C_all=16`.

`findFirst=3, C_first=16`.

Ngay cả khi **cuối cùng có khớp**, thuật toán `findFirst` vẫn có thể tốn số phép so sánh gần cận xấu nhất nếu lần khớp đầu tiên nằm cuối vùng tìm kiếm, sau rất nhiều phép so tiền tố thất bại muộn.

## 7. Những mẫu có cấu trúc dễ làm so lại

Không chỉ `aaaa...` mới gây tốn thời gian.

### 7.1. Tiền tố lặp dài

Mẫu có tiền tố rất dài giống nhiều đoạn văn bản, ví dụ `"aaa...aaab"` với văn bản `"aaa...aaaa"`, gây sai khác ở cuối mẫu trên hàng loạt shift.

### 7.2. Chu kỳ ngắn

Văn bản `"abababab"` và mẫu `"abab"` có các lần khớp tại `[0,2,4]`. Những shift chẵn so đủ 4 ký tự; shift lẻ thường sai ngay đầu:

~~~text
shift 0: 4 phép, khớp
shift 1: 1 phép, sai
shift 2: 4 phép, khớp
shift 3: 1 phép, sai
shift 4: 4 phép, khớp
Tổng: 14 phép so sánh
~~~

Mẫu có chu kỳ ngắn làm xuất hiện nhiều **tiền tố/hậu tố trùng nhau**, nền tảng của khái niệm border/prefix-function trong KMP.

### 7.3. Nhiều đoạn đầu giống nhau nhưng không có match

Nếu mẫu bắt đầu bằng đoạn rất phổ biến trong văn bản nhưng kết thúc bằng một ký tự hiếm/không xuất hiện, số lần khớp có thể bằng 0 trong khi phép so sánh rất lớn.

### 7.4. Văn bản và mẫu giống hệt nhau

Khi `n=m` và `T=P`, chỉ có một shift và tốn `m` phép so sánh; không nên gọi đây là Θ(nm) theo nghĩa hai tham số tự do, vì `q=1`. Công thức chặt hơn `m(n−m+1)` giúp tránh diễn giải mơ hồ.

### 7.5. Mẫu rất ngắn

Với `m=1` và `n≥1`, mọi shift chỉ cần **một** so sánh: `C_all=n`. Dù ký tự có xuất hiện rất nhiều, **không thể có độ phức tạp bậc hai** chỉ vì mẫu dài 1.

## 8. Độ phức tạp thời gian và bộ nhớ

Cho `1≤m≤n`, thuật toán xét `q=n−m+1` vị trí. Mỗi vị trí tối đa m phép so sánh:

`T_all(n,m)=O(m(n−m+1))`.

Cận đơn giản thường gặp:

`O(nm)`.

Trong trường hợp xấu được xây dựng ở mục 4, mỗi vị trí tốn m phép so sánh, do đó:

`T_all(n,m)=Θ(m(n−m+1))` theo **trường hợp xấu nhất cho n,m đó**.

### Trường hợp tốt nhất

Với **findAll** và mẫu không rỗng, n≥m:

- Mỗi shift có ít nhất một phép so sánh.
- Nếu sai ngay ký tự đầu ở mọi shift (và `m≥2` hoặc mẫu không xuất hiện), đúng q phép so sánh.
- Vì vậy chi phí ký tự nhỏ nhất là `q`; thời gian vòng quét ít nhất Θ(q).

Với **findFirst**, nếu khớp ngay shift0, cần **m** phép so sánh để xác nhận toàn bộ mẫu; nhưng nếu không có match và tất cả shift sai ngay ký tự đầu, chi phí ký tự chỉ q. Vì thế **không có một câu “best case = O(m)” chuẩn cho mọi đầu vào n,m** mà không nói rõ best case xét cả đầu vào không khớp hay yêu cầu có khớp. Cách an toàn nhất là phân tích theo **vị trí lần khớp đầu và độ dài tiền tố trùng ở mỗi shift**.

**Nếu m>n**, so sánh ký tự bằng 0 sau kiểm tra độ dài. **Nếu m=0**, quy ước trả n+1 vị trí và không cần so ký tự.

### Bộ nhớ

- **Find first:** có thể dùng O(1) bộ nhớ phụ (các chỉ số `shift,j` và bộ đếm), không kể hai chuỗi đầu vào.
- **Find all:** dùng O(k) bộ nhớ để lưu `k` vị trí tìm được, ngoài O(1) biến; trong trường hợp mẫu rỗng hoặc mẫu xuất hiện ở mọi shift, `k` có thể là Θ(n).
- Nếu muốn **phát trực tiếp từng vị trí** qua callback/stream thay vì lưu danh sách, có thể giữ bộ nhớ phụ O(1), tùy API đầu ra.

### Mức đếm nào là Θ(nm)?

Khi m xấp xỉ một tỉ lệ cố định của n, ví dụ m≈n/2, ta có `m(n−m+1)=Θ(n²)` ở đầu vào xấu. Khi m cố định nhỏ, số phép so sánh tối đa chỉ Θ(n). Khi m=n, chỉ có một shift và chi phí tối đa Θ(n). Nói **O(nm)** đúng như cận trên thô, nhưng không mô tả hết sự phụ thuộc vào số shift.

## 9. Chứng minh thuật toán trực tiếp đúng

Ta chứng minh cho biến thể `findAll` với `1≤m≤n`.

### Bất biến của vòng kiểm tra tại shift s

Trước khi kiểm tra chỉ số j, các ký tự mẫu ở vị trí `0..j−1` đã được kiểm chứng trùng đoạn văn bản tương ứng:

`P[k] = T[s+k]` với mọi `0≤k<j`.

- Ban đầu j=0, mệnh đề đúng hiển nhiên vì chưa có ký tự nào cần kiểm tra.
- Nếu ký tự thứ j trùng, tăng j lên 1 và bất biến vẫn đúng.
- Nếu ký tự thứ j khác, đoạn `T[s..s+m−1]` **không thể** bằng P; việc bỏ shift này là an toàn.
- Nếu j=m, mọi m ký tự đều bằng nhau, nên s đúng là một vị trí xuất hiện.

### Không bỏ sót và không trả sai

Vòng ngoài xét **tất cả shift từ 0 tới n−m**, không bỏ qua vị trí nào. Một match hợp lệ phải bắt đầu trong đoạn chỉ số ấy và sẽ được vòng trong xác nhận đầy đủ. Ngược lại, mỗi vị trí được đưa vào kết quả chỉ khi toàn bộ m ký tự bằng nhau.

Do vậy kết quả chứa **đúng và đủ** mọi vị trí khớp, theo thứ tự tăng dần, mỗi vị trí đúng một lần.

Với `findFirst`, vòng ngoài cũng xét theo thứ tự tăng dần và trả về shift đầu tiên khớp hoàn toàn; vì vậy kết quả đúng là vị trí nhỏ nhất. Khi không có vị trí nào khớp, trả -1.

Trường hợp m=0 và m>n được tách khỏi vòng kiểm tra nên không gây truy cập ngoài phạm vi và tuân thủ quy ước đã công bố.

## 10. Phân biệt chi phí thuật toán và thời gian chạy thật

**Số phép so sánh ký tự** là một thước đo lý thuyết có thể tái lập, hữu ích để xác định tình huống xấu. Nó **không** bằng số nanosecond hay số lệnh máy:

- Một phép so `char` trên hai chuỗi có thể liên quan đến đọc bộ nhớ và kiểm tra biên.
- JVM có JIT, tối ưu hóa vòng lặp, GC và các cơ chế biểu diễn `String`; kết quả đo thời gian phụ thuộc phiên bản/máy/hệ điều hành.
- Bộ nhớ cache và vị trí của dữ liệu cũng ảnh hưởng kết quả.
- `String.indexOf` của thư viện Java có hợp đồng trả chỉ số đúng, nhưng **không nên khẳng định nó luôn sử dụng thuật toán naive hoặc KMP**, vì chi tiết triển khai có thể thay đổi.

Để benchmark công bằng cần warm-up, input có kiểm soát, không trộn I/O vào vùng đo và công cụ như JMH nếu cần kết quả nghiêm túc. Trong bài học, ta **không đo thời gian bằng `System.nanoTime()` rồi gọi đó là bằng chứng độ phức tạp**; ta đếm đúng những phép so mà thuật toán thực hiện.

## 11. Java 17 và Unicode: “ký tự” là đơn vị nào?

Trong Java, `String.length()` là **số đơn vị mã UTF-16 (UTF-16 code units)**, không nhất thiết là số ký tự mà người dùng nhìn thấy.

- `String.charAt(i)` trả một **char UTF-16** ở chỉ số i.
- Nhiều ký tự ngoài Basic Multilingual Plane, ví dụ một emoji, được biểu diễn bằng **hai `char`** (surrogate pair).
- Do đó chỉ số mà thuật toán `charAt` trả về tương thích với chỉ số `String.indexOf` của Java, **không phải chỉ số code point hoặc grapheme cluster**.

Ví dụ:

~~~text
T = "A🙂B🙂"
P = "🙂"

T.length() = 6 đơn vị UTF-16
T.codePointCount(0, T.length()) = 4 code points
Match theo chỉ số UTF-16: [1, 4]
Vị trí code point tương ứng: [1, 3]
~~~

Lần khớp tại offset 4 là **đúng theo API Java**, dù người dùng đếm “ký tự hiển thị” có thể gọi emoji thứ hai là vị trí 3 (đánh số từ 0 theo code point). Nếu API yêu cầu vị trí code point, cần chuyển đổi chỉ số hoặc duyệt theo `codePoints()`; nếu yêu cầu **grapheme cluster** (ký tự hiển thị có dấu ghép/emoji nhiều code point), cần cơ chế phân đoạn riêng.

### Chuẩn hóa Unicode

Hai chuỗi nhìn giống nhau có thể khác mã:

- `"é"` là một code point U+00E9.
- `"e\u0301"` là chữ e và combining acute accent U+0301.

Phép so khớp `charAt` nguyên bản **không xem chúng bằng nhau**. Nếu bài toán đòi tương đương theo chuẩn Unicode, có thể cân nhắc `java.text.Normalizer` với NFC/NFD trước khi tìm kiếm. Nhưng chuẩn hóa có thể đổi **số đơn vị và vị trí**, nên không thể tùy tiện trả chỉ số trên chuỗi đã chuẩn hóa như chỉ số trên **bản gốc** khi API yêu cầu offset gốc.

Tương tự, mặc định đây là so khớp **phân biệt chữ hoa/chữ thường**, chính xác từng đơn vị UTF-16. Chuyển chữ thường theo locale hay xử lý Unicode case folding cần đặc tả riêng; không tự thay đổi văn bản/mẫu trong thuật toán cơ bản.

## 12. Java 17+ chạy độc lập và đếm đúng phép so sánh

Chương trình dưới đây cung cấp:

1. `findAll`: duyệt tất cả shift, trả `List<Integer>` và số phép so sánh `long`.
2. `findFirst`: dừng tại lần xuất hiện đầu, trả chỉ số và số phép so sánh của riêng biến thể này.
3. `trace`: in từng shift, số phép đã so và vị trí sai khác hoặc MATCH.
4. `referenceAll`: dùng `String.indexOf` làm **oracle độc lập về vị trí khớp**, tăng `fromIndex` **1** để không bỏ mất khớp chồng lấn.
5. `oracleComparisonCount` và `oracleFirstComparisons`: dùng `String.regionMatches` trên các **tiền tố độ dài tăng dần** để xác minh số phép so ký tự ở mọi shift, không tái sử dụng vòng `charAt` của bản giải.
6. `checkCase`: so kết quả và bộ đếm với oracle, kiểm tra cận chính xác `q≤C≤qm` trên các trường hợp thích hợp.
7. `randomCrossCheck`: kiểm thử **400 cặp chuỗi ASCII ngẫu nhiên** với seed cố định, gồm cả văn bản/mẫu rỗng và `m>n`.
8. Bộ ví dụ cố định về gần khớp thất bại ở cuối, khớp mọi vị trí, lặp chu kỳ, mẫu rỗng, pattern dài hơn, so khớp case-sensitive và chỉ số UTF-16.

**Tạo tệp `DirectStringMatchingDemo.java`** và chạy trên JDK 17+:

~~~java
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public class DirectStringMatchingDemo {
    record AllResult(List<Integer> positions, long comparisons) {}
    record FirstResult(int index, long comparisons) {}

    static AllResult findAll(String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();
        List<Integer> positions = new ArrayList<>();

        if (m == 0) {
            for (int i = 0; i <= n; i++) {
                positions.add(i);
            }
            return new AllResult(List.copyOf(positions), 0L);
        }
        if (m > n) {
            return new AllResult(List.of(), 0L);
        }

        long comparisons = 0L;
        for (int shift = 0; shift <= n - m; shift++) {
            int j = 0;
            while (j < m) {
                comparisons++;
                if (text.charAt(shift + j) != pattern.charAt(j)) {
                    break;
                }
                j++;
            }
            if (j == m) {
                positions.add(shift);
            }
        }
        return new AllResult(List.copyOf(positions), comparisons);
    }

    static FirstResult findFirst(String text, String pattern) {
        Objects.requireNonNull(text, "text");
        Objects.requireNonNull(pattern, "pattern");

        int n = text.length();
        int m = pattern.length();
        if (m == 0) {
            return new FirstResult(0, 0L);
        }
        if (m > n) {
            return new FirstResult(-1, 0L);
        }

        long comparisons = 0L;
        for (int shift = 0; shift <= n - m; shift++) {
            int j = 0;
            while (j < m) {
                comparisons++;
                if (text.charAt(shift + j) != pattern.charAt(j)) {
                    break;
                }
                j++;
            }
            if (j == m) {
                return new FirstResult(shift, comparisons);
            }
        }
        return new FirstResult(-1, comparisons);
    }

    static void trace(String text, String pattern) {
        if (pattern.isEmpty() || pattern.length() > text.length()) {
            throw new IllegalArgumentException(
                    "trace requires 1 <= m <= n");
        }
        int m = pattern.length();
        for (int shift = 0;
                shift <= text.length() - m; shift++) {
            int j = 0;
            long compared = 0L;
            while (j < m) {
                compared++;
                if (text.charAt(shift + j) != pattern.charAt(j)) {
                    break;
                }
                j++;
            }
            String outcome = j == m
                    ? "MATCH" : "mismatchAt=" + j;
            System.out.println("shift=" + shift
                    + " compared=" + compared + " " + outcome);
        }
    }

    // Reference for offsets: String.indexOf, with fromIndex+1
    // to retain overlapping matches.
    static List<Integer> referenceAll(
            String text, String pattern) {
        List<Integer> answer = new ArrayList<>();
        if (pattern.isEmpty()) {
            for (int i = 0; i <= text.length(); i++) {
                answer.add(i);
            }
            return answer;
        }

        int start = 0;
        while (start <= text.length() - pattern.length()) {
            int found = text.indexOf(pattern, start);
            if (found < 0) break;
            answer.add(found);
            start = found + 1;
        }
        return answer;
    }

    // Separate oracle for comparison counts:
    // regionMatches checks increasingly long prefixes.
    // This is only for small TEST inputs, not production.
    static long oracleComparisonCount(
            String text, String pattern) {
        int n = text.length(), m = pattern.length();
        if (m == 0 || m > n) return 0L;

        long count = 0L;
        for (int shift = 0; shift <= n - m; shift++) {
            for (int width = 1; width <= m; width++) {
                count++;
                if (!text.regionMatches(
                        shift, pattern, 0, width)) {
                    break;
                }
            }
        }
        return count;
    }

    static long oracleFirstComparisons(
            String text, String pattern) {
        int n = text.length(), m = pattern.length();
        if (m == 0 || m > n) return 0L;

        long count = 0L;
        for (int shift = 0; shift <= n - m; shift++) {
            for (int width = 1; width <= m; width++) {
                count++;
                if (!text.regionMatches(
                        shift, pattern, 0, width)) {
                    break;
                }
                if (width == m) {
                    return count;
                }
            }
        }
        return count;
    }

    static void checkCase(String text, String pattern) {
        AllResult all = findAll(text, pattern);
        FirstResult first = findFirst(text, pattern);
        List<Integer> expected = referenceAll(text, pattern);
        int expectedFirst = text.indexOf(pattern);

        if (!all.positions().equals(expected)
                || first.index() != expectedFirst
                || all.comparisons() !=
                        oracleComparisonCount(text, pattern)
                || first.comparisons() !=
                        oracleFirstComparisons(text, pattern)
                || first.comparisons() > all.comparisons()) {
            throw new AssertionError("Matching/oracle mismatch");
        }

        int n = text.length(), m = pattern.length();
        if (m > 0 && m <= n) {
            long shifts = (long) n - m + 1L;
            if (all.comparisons() < shifts
                    || all.comparisons() > shifts * m) {
                throw new AssertionError("Comparison bound");
            }
        } else if (all.comparisons() != 0
                || first.comparisons() != 0) {
            throw new AssertionError("Boundary comparison count");
        }
    }

    static String randomString(Random random, int length) {
        String alphabet = "abc";
        StringBuilder answer = new StringBuilder(length);
        for (int i = 0; i < length; i++) {
            answer.append(alphabet.charAt(
                    random.nextInt(alphabet.length())));
        }
        return answer.toString();
    }

    static void randomCrossCheck() {
        Random random = new Random(2026L);
        for (int test = 0; test < 400; test++) {
            int n = random.nextInt(24);
            int m = random.nextInt(10);
            String text = randomString(random, n);
            String pattern = randomString(random, m);
            checkCase(text, pattern);
        }
        System.out.println("randomCrossCheck=PASS (400 cases)");
    }

    static void show(String name, String text, String pattern) {
        checkCase(text, pattern);
        AllResult all = findAll(text, pattern);
        FirstResult first = findFirst(text, pattern);

        System.out.println(name
                + " positions=" + all.positions()
                + " comparisons=" + all.comparisons()
                + " first=" + first.index()
                + " firstComparisons=" + first.comparisons());
    }

    public static void main(String[] args) {
        show("nearMiss", "aaaaaaaa", "aaab");
        show("allOverlaps", "aaaaaaaa", "aaaa");
        show("bananana", "bananana", "ana");
        show("earlyAndLate", "aaaaaab", "aaab");
        show("alternating", "abababab", "abab");
        show("noFirstChar", "xyzxyz", "abc");
        show("longerPattern", "abc", "abcd");
        show("emptyPattern", "abc", "");
        show("emptyBoth", "", "");
        show("emptyText", "", "a");
        show("unicode", "A🙂B🙂", "🙂");
        show("caseSensitive", "AbCabc", "abc");
        show("oneChar", "aaaa", "a");

        System.out.println("trace=earlyAndLate");
        trace("aaaaaab", "aaab");

        String unicode = "A🙂B🙂";
        System.out.println("utf16Length=" + unicode.length()
                + " codePoints=" + unicode.codePointCount(
                        0, unicode.length()));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        boolean rawEqual = composed.equals(decomposed);
        boolean nfcEqual = Normalizer.normalize(
                composed, Normalizer.Form.NFC).equals(
                Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC));
        System.out.println("normalization rawEqual=" + rawEqual
                + " nfcEqual=" + nfcEqual);

        if (findAll("aaaaaaaa", "aaab").comparisons() != 20
                || findAll("aaaaaaaa", "aaaa")
                        .comparisons() != 20
                || findFirst("aaaaaaaa", "aaaa")
                        .comparisons() != 4) {
            throw new AssertionError("Worst-case/count sanity");
        }

        randomCrossCheck();
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac DirectStringMatchingDemo.java
java DirectStringMatchingDemo
~~~

**Đầu ra dự kiến chính xác**, trong đó danh sách theo định dạng mặc định của Java:

~~~text
nearMiss positions=[] comparisons=20 first=-1 firstComparisons=20
allOverlaps positions=[0, 1, 2, 3, 4] comparisons=20 first=0 firstComparisons=4
bananana positions=[1, 3, 5] comparisons=12 first=1 firstComparisons=4
earlyAndLate positions=[3] comparisons=16 first=3 firstComparisons=16
alternating positions=[0, 2, 4] comparisons=14 first=0 firstComparisons=4
noFirstChar positions=[] comparisons=4 first=-1 firstComparisons=4
longerPattern positions=[] comparisons=0 first=-1 firstComparisons=0
emptyPattern positions=[0, 1, 2, 3] comparisons=0 first=0 firstComparisons=0
emptyBoth positions=[0] comparisons=0 first=0 firstComparisons=0
emptyText positions=[] comparisons=0 first=-1 firstComparisons=0
unicode positions=[1, 4] comparisons=7 first=1 firstComparisons=3
caseSensitive positions=[3] comparisons=6 first=3 firstComparisons=6
oneChar positions=[0, 1, 2, 3] comparisons=4 first=0 firstComparisons=1
trace=earlyAndLate
shift=0 compared=4 mismatchAt=3
shift=1 compared=4 mismatchAt=3
shift=2 compared=4 mismatchAt=3
shift=3 compared=4 MATCH
utf16Length=6 codePoints=4
normalization rawEqual=false nfcEqual=true
randomCrossCheck=PASS (400 cases)
~~~

### Giải thích các kết quả nổi bật

**nearMiss:** mẫu `aaab` liên tục trùng ba ký tự `a` rồi sai chữ cuối tại cả 5 shift. Không có match, nhưng mất **20** phép so sánh.

**allOverlaps:** mẫu `aaaa` khớp tại 5 vị trí chồng lấn. `findAll` tốn 20, còn `findFirst` chỉ tốn 4 nhờ dừng sau lần khớp đầu.

**bananana:** các vị trí `[1,3,5]` chồng lấn; chương trình trả đầy đủ thay vì nhảy quá m ký tự sau mỗi match.

**earlyAndLate:** lần khớp đầu ở shift3 và cả 3 vị trí trước sai muộn, nên `findFirst` vẫn mất 16 phép so sánh.

**alternating:** ba shift chẵn khớp, hai shift lẻ sai ngay đầu; tổng `4+1+4+1+4=14`.

**noFirstChar:** tại mọi shift, `T[s]` khác `P[0]`, chỉ 4 phép so sánh — chi phí rẻ hơn rất nhiều so với cận trên `4×3=12`.

**longerPattern:** m>n, không có shift hợp lệ, 0 so sánh. **emptyPattern** và **emptyBoth** minh họa mẫu rỗng khớp ở các ranh giới, vẫn 0 so sánh ký tự. **emptyText** với mẫu không rỗng trả -1.

**unicode:** emoji chiếm 2 `char` trong UTF-16, nên offset khớp là 1 và 4, khác cách đếm code point. **normalization** cho thấy chuỗi nhìn giống nhau chưa chắc tương đương trước khi chuẩn hóa.

**randomCrossCheck:** dùng **400 bộ đầu vào nhỏ** với độ dài văn bản từ 0 đến 23, độ dài mẫu từ 0 đến 9, alphabet `abc`, seed `2026`. Mỗi bộ so vị trí với `String.indexOf` và so **số phép so sánh** với phương pháp dùng `String.regionMatches` trên các tiền tố, độc lập với vòng `charAt` của thuật toán chính. Nếu bất kỳ kết quả nào sai, chương trình ném `AssertionError`; dòng PASS chỉ xuất hiện khi toàn bộ kiểm thử thành công.

### Vì sao oracle đếm so sánh độc lập là có ích?

Nếu chỉ kiểm tra các vị trí khớp, code có thể trả **đúng** vị trí nhưng bộ đếm sai do:

- Không đếm phép so cuối gây mismatch.
- Vẫn tăng bộ đếm sau khi đã break.
- Đếm điều kiện vòng lặp `j<m` thay vì lần đối chiếu ký tự.
- Đếm nhầm các phép kiểm tra khi mẫu rỗng.

Oracle `regionMatches` kiểm tra những **tiền tố có độ dài 1,2,...**; lần đầu tiền tố không còn trùng chỉ ra chính xác số ký tự đã cần kiểm tra ở shift đó. Vì dùng API khác với `charAt` từng ký tự, nó phát hiện nhiều lỗi đếm độc lập với kiểm tra kết quả `indexOf`.

**Giới hạn:** oracle mở rộng tiền tố lặp lại có thể rất chậm khi chuỗi dài vì nó kiểm tra lại prefix nhiều lần. Nó **chỉ nằm trong mã demo/kiểm thử trên chuỗi nhỏ**, không phải thuật toán thay thế cho production.

## 13. Đặc biệt với dữ liệu nhiều truy vấn

Nếu cần tìm **một mẫu** trong **một văn bản ngắn**, thuật toán trực tiếp có thể là lựa chọn hợp lý: dễ cài, ít trạng thái, không cần tiền xử lý.

Nếu cần tìm **nhiều mẫu** trong cùng văn bản, hoặc cùng một mẫu được tìm trong **nhiều văn bản**, chi phí lặp lại có thể đáng kể. Một số lựa chọn:

| Bài toán | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Một mẫu, dữ liệu nhỏ, cần logic đơn giản | Direct matching | Có thể mất `m(n−m+1)` phép so |
| Một mẫu, muốn bảo đảm tuyến tính | KMP hoặc Z-algorithm | Thường `O(n+m)` thời gian theo mô hình ký tự |
| Dữ liệu thực tế và muốn API tiện dụng | `String.indexOf` hoặc `String.contains` | Bảo đảm *ngữ nghĩa*, đừng tự đoán thuật toán nội bộ |
| Tìm nhiều mẫu đồng thời | Aho–Corasick | Cấu trúc trie/automaton tùy tập mẫu |
| Tìm theo giá trị hash nhiều cửa sổ | Rabin–Karp | Cần xác minh match để tránh collision nếu yêu cầu đúng tuyệt đối |
| Tìm mẫu có thể skip nhiều vị trí | Boyer–Moore và biến thể | Hiệu năng phụ thuộc alphabet/pattern, bảo đảm tùy biến thể |

**Không xem bảng như lời khuyên đổi thuật toán theo mọi trường hợp.** Thuật toán tốt nhất phụ thuộc số truy vấn, kích thước dữ liệu, tính ổn định hiệu năng, bảng ký tự và yêu cầu về Unicode/chuẩn hóa.

### KMP tránh so lặp theo nguyên lý nào?

KMP xây **prefix function / LPS** cho mẫu: sau khi trùng `j` ký tự rồi gặp sai khác, nó dùng thông tin về **tiền tố cũng là hậu tố** để xác định phần nào đã biết là khớp. Nó không nhất thiết dịch sang shift+1 và bắt đầu lại hoàn toàn từ j=0 như naive.

Ví dụ với chuỗi nhiều `a` và mẫu kết thúc bằng `b`, naive so gần hết mẫu ở mọi shift; KMP giữ trạng thái độ dài tiền tố phù hợp và đạt thời gian tuyến tính theo n+m.

**Lưu ý:** KMP chỉ cải thiện độ phức tạp khi thực hiện đúng tiền xử lý và cập nhật trạng thái; việc thêm một mảng LPS nhưng vẫn thử mọi shift từ đầu **không tự động** làm chương trình tuyến tính.

## 14. Những sai lầm thường gặp

1. **Duyệt tới `s<n−m`** thay vì `s≤n−m`, bỏ sót vị trí cuối.
2. **Không kiểm tra `m>n`** trước khi đọc `T[s+j]`, có thể truy cập sai biên.
3. **Quên m=0** làm vòng kiểm tra không rõ nghĩa hoặc trả vị trí khác hợp đồng.
4. **Tự nhảy `m` sau khi tìm thấy match**, bỏ sót khớp chồng lấn khi yêu cầu findAll.
5. **Trả về ngay match đầu** dù đề yêu cầu tất cả vị trí.
6. **Không dừng sau match đầu** khi đề chỉ yêu cầu findFirst, tốn thêm phép so không cần thiết.
7. **Dùng `i<n` cho mọi vị trí căn chỉnh** ngay cả khi không còn đủ m ký tự.
8. **Đếm số shift bằng n** thay vì `n−m+1` với mẫu không rỗng và n≥m.
9. **Đếm điều kiện vòng while như phép so ký tự**, thổi phồng số thống kê.
10. **Không đếm phép so sai cuối cùng**, khiến ví dụ `aaab` báo 3 thay vì 4 mỗi shift.
11. **Đếm đủ m tại mọi shift** dù có thể sai ngay ở ký tự đầu.
12. **Cho rằng không có match thì thuật toán phải nhanh**, bị phản ví dụ gần khớp tới ký tự cuối.
13. **Cho rằng có nhiều match thì thuật toán nhanh**, trong findAll mỗi match đầy đủ mất m phép so.
14. **Gọi O(nm) là luôn Θ(nm)** mà bỏ qua trường hợp m=n chỉ có một shift.
15. **Dùng int lưu bộ đếm** khi số phép so có thể vượt 2,1 tỷ.
16. **Lẫn thời gian JIT/microbenchmark với số phép so ký tự**, hai đại lượng khác nhau.
17. **Cắt substring mới tại mỗi shift** rồi so, vô tình thêm chi phí sao chép/cấp phát mà pseudocode không mô tả.
18. **Không thử dữ liệu có tiền tố lặp dài**, bỏ sót trường hợp xấu nhất.
19. **Cho rằng String.indexOf của mọi JDK luôn dùng một thuật toán cụ thể**, phụ thuộc triển khai.
20. **Không phân biệt UTF-16 code unit với code point**, dễ hiểu sai offset của emoji.
21. **Tìm mẫu theo chữ có dấu mà không làm rõ normalization**, có thể báo không tìm thấy chuỗi hiển thị giống nhau.
22. **Tự chuyển lowercase nhưng trả offset của chuỗi biến đổi như offset gốc**, sai nếu phép biến đổi thay đổi chiều dài.
23. **Tuyên bố O(1) bộ nhớ cho findAll trả danh sách k vị trí**, phải kể O(k) đầu ra.
24. **So sánh Unicode theo `char` rồi gọi là so grapheme cluster**, không đúng.
25. **Dùng mốc `n−m+1` khi m=0** và coi n+1 kết quả là n+1 phép so ký tự, dù không đối chiếu ký tự nào.
26. **Không kiểm tra match ở s=0 và s=n−m** trong test.
27. **Không kiểm tra mẫu dài 1**, trường hợp mọi shift đúng 1 phép so.
28. **Nhầm vị trí bắt đầu khớp với vị trí kết thúc**, sai lệch m−1.
29. **Chỉ test văn bản chữ khác nhau**, chưa test `aaaa...` và `abab...`.
30. **Chọn thuật toán tuyến tính mà không cần thiết với dữ liệu nhỏ**, tăng độ phức tạp triển khai mà không rõ lợi ích.

## 15. Bài tập có lời giải

**Bài 1.** Với văn bản độ dài n=12 và mẫu độ dài m=5, có bao nhiêu shift hợp lệ? **Đáp án:** `12−5+1=8`, từ 0 tới 7.

**Bài 2.** Vì sao shift cuối là n−m? **Đáp án:** vì ký tự cuối của mẫu nằm ở chỉ số `s+m−1`, phải không vượt `n−1`.

**Bài 3.** Với `T="aaaaaaaa"`, `P="aaab"`, có bao nhiêu match? **Đáp án:** 0.

**Bài 4.** Cùng dữ liệu, tìm tất cả phải dùng bao nhiêu so sánh ký tự? **Đáp án:** `5×4=20`.

**Bài 5.** Tại sao ở bài 4 mỗi shift phải so 4 ký tự dù không có match? **Đáp án:** ba ký tự `a` đầu đều trùng, chỉ khác ký tự cuối `b`.

**Bài 6.** Với `T="aaaaaaaa"`, `P="aaaa"`, những offset khớp? **Đáp án:** `[0,1,2,3,4]`.

**Bài 7.** Ở bài 6, `findAll` có bao nhiêu so sánh? **Đáp án:** 20.

**Bài 8.** Ở bài 6, `findFirst` có bao nhiêu so sánh? **Đáp án:** 4, vì tìm ngay shift0.

**Bài 9.** Với `T="ababa"`, `P="aba"`, có những khớp nào? **Đáp án:** offset 0 và 2, **có chồng lấn**.

**Bài 10.** Nếu sau khớp tại s=0 bài 9 nhảy thẳng s=3, lỗi gì? **Đáp án:** bỏ sót khớp tại s=2.

**Bài 11.** Với `T="aaaaaab"` và `P="aaab"`, vị trí đầu? **Đáp án:** 3.

**Bài 12.** Cùng dữ liệu, `findFirst` đã dùng bao nhiêu so sánh? **Đáp án:** 16.

**Bài 13.** Với `T="xyzxyz"` và `P="abc"`, có bao nhiêu so sánh ký tự? **Đáp án:** 4 shift và sai ngay ký tự đầu mỗi shift ⇒ 4 phép.

**Bài 14.** Nếu `m>n` và đã kiểm tra độ dài trước vòng lặp, có bao nhiêu so sánh ký tự? **Đáp án:** 0.

**Bài 15.** Nếu `T="abc"`, `P=""` theo quy ước bài, `findAll` là gì? **Đáp án:** `[0,1,2,3]` và 0 so sánh.

**Bài 16.** Nếu cả hai chuỗi rỗng, `findAll` trả gì? **Đáp án:** `[0]`.

**Bài 17.** Với `n=2 000 000`, `m=2 000`, cận xấu nhất chính xác về số so ký tự? **Đáp án:** `3 996 002 000`.

**Bài 18.** Vì sao cần `long` cho bộ đếm? **Đáp án:** cận xấu nhất có thể vượt `Integer.MAX_VALUE`.

**Bài 19.** Cận trên chi tiết hơn O(nm)? **Đáp án:** `O(m(n−m+1))` với 1≤m≤n.

**Bài 20.** Nếu mẫu chỉ có một ký tự và n≥1, findAll so bao nhiêu ký tự? **Đáp án:** đúng n, mỗi shift một so sánh.

**Bài 21.** Công thức chi phí tại shift s theo tiền tố chung dài `L_s`? **Đáp án:** `C_s=min(m,L_s+1)`, với m≥1.

**Bài 22.** Điều kiện để một matching tại shift s hoàn toàn hợp lệ? **Đáp án:** `T[s+j]=P[j]` cho mọi j từ 0 đến m−1.

**Bài 23.** Vòng for shift tăng 1 có ích gì cho findAll? **Đáp án:** không bỏ sót các lần khớp chồng lấn.

**Bài 24.** Vì sao `String.length()` của `"A🙂B🙂"` bằng 6 chứ không phải 4? **Đáp án:** mỗi emoji cần hai UTF-16 code units.

**Bài 25.** Với mẫu `"🙂"` trong văn bản bài 24, offset Java theo UTF-16? **Đáp án:** 1 và 4.

**Bài 26.** `"é"` và `"e\u0301"` có luôn bằng nhau dưới so khớp `charAt`? **Đáp án:** không; mã UTF-16 khác nhau; có thể chuẩn hóa Unicode nếu đặc tả yêu cầu.

**Bài 27.** Vì sao `String.indexOf` không được tự động dùng để kết luận naive đang chạy O(nm)? **Đáp án:** API bảo đảm kết quả, không cố định chi tiết thuật toán nội bộ của mọi JDK.

**Bài 28.** KMP cải thiện điều gì so với naive? **Đáp án:** dùng cấu trúc tiền tố/hậu tố để tránh so lại phần đã biết, đạt O(n+m) theo mô hình phù hợp.

**Bài 29.** Nếu chỉ muốn vị trí đầu tiên và nó khớp ngay shift0, số phép so tối thiểu cho match ấy? **Đáp án:** m phép để xác nhận đủ mẫu không rỗng.

**Bài 30.** Nếu có k kết quả và API trả danh sách, bộ nhớ kết quả tốn bao nhiêu? **Đáp án:** O(k); nếu phát lần lượt có thể không cần lưu toàn bộ.

**Bài 31.** Vì sao một chuỗi lặp `ababab...` có thể tốn nhiều so sánh ở một số shift? **Đáp án:** nhiều shift có tiền tố trùng dài hoặc khớp hoàn toàn; mỗi lần lại kiểm tra từ đầu.

**Bài 32.** Có nên kết luận `findFirst` luôn rẻ hơn `findAll` một bậc độ phức tạp? **Đáp án:** không; khi không có match hoặc khớp ở vị trí cuối, cả hai có thể cùng đạt cận xấu nhất.

## 16. Checklist áp dụng

1. **Mục tiêu là find first hay find all?** Có yêu cầu khớp chồng lấn không?
2. **Chỉ số bắt đầu từ 0 hay 1?** Có cần trả offset UTF-16, code point hay grapheme không?
3. **Mẫu rỗng** được phép và trả giá trị gì? Hợp đồng phải rõ.
4. **m>n** đã được tách trước vòng lặp chưa?
5. **Shift cuối có được xét** tại `s=n−m` không?
6. **Dừng tại mismatch ngay** hay đang so thừa ký tự?
7. **Với find all, có tiếp tục shift+1 sau một match** để tìm phần chồng lấn không?
8. **Với find first, có dừng ngay** khi tìm thấy lần xuất hiện đầu không?
9. **Đã đếm phép so ký tự ở đúng chỗ**, kể cả lần sai cuối chưa?
10. **Đã thử text `a^n`, pattern `a^(m−1)b`**, để thấy `m(n−m+1)` phép so chưa?
11. **Đã thử text và pattern đều toàn `a`**, để thấy nhiều match cũng có thể tối đa chưa?
12. **Đã thử `banana`/`ana`, P4 lặp và dữ liệu chu kỳ ngắn**, để kiểm tra chồng lấn chưa?
13. **Đã thử m=1, m=n, m>n, m=0, n=0** chưa?
14. **Có dùng long cho số so sánh** nếu n,m lớn không?
15. **Phân tích theo số shift q và tiền tố trùng thực tế**, không chỉ lặp câu O(nm) chưa?
16. **Có tính O(k) bộ nhớ đầu ra cho find all** chưa?
17. **Có phân biệt chi phí ký tự với thời gian benchmark thật** chưa?
18. **Nếu có emoji/chữ có dấu, đã làm rõ UTF-16 và normalization** chưa?
19. **Nếu bài cần nhiều truy vấn/quy mô lớn, đã cân nhắc KMP/Z/Boyer–Moore** chưa?
20. **Có kiểm tra bằng oracle `indexOf` và phép đo độc lập trên test nhỏ** chưa?

**Ghi nhớ:** thuật toán so khớp trực tiếp **thử tất cả vị trí căn chỉnh** và ở mỗi vị trí so từ đầu mẫu đến khi gặp mismatch hoặc khớp đủ. Nó đơn giản, đúng và có thể nhanh khi sai sớm, nhưng trên các chuỗi lặp hoặc gần khớp kéo dài sẽ so lại cùng kiểu tiền tố ở rất nhiều vị trí, tốn tới **`m(n−m+1)` phép so sánh ký tự**. Phân biệt **find first** với **find all**, luôn xét khớp **chồng lấn** khi cần, và quy định rõ ý nghĩa của **mẫu rỗng** cùng hệ **chỉ số UTF-16 của Java**.
