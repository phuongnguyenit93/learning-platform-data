# Phép quay có thứ tự từ điển nhỏ nhất và thuật toán Booth

## 1. Bài toán: tìm phép quay nhỏ nhất của một chuỗi

Cho chuỗi S gồm n ký hiệu, một **phép quay vòng (cyclic rotation)** tại vị trí i là chuỗi tạo bởi cách lấy đoạn từ i tới cuối rồi nối đoạn từ đầu tới i−1:

~~~text
rotation(S, i) = S[i..n-1] + S[0..i-1]
0 <= i < n
~~~

Ví dụ với S = "baca":

| i (0-based) | rotation(S,i) |
| ---: | --- |
| 0 | baca |
| 1 | acab |
| 2 | caba |
| 3 | abac |

So sánh từ điển, **"abac"** nhỏ nhất, nên phép quay tối thiểu bắt đầu tại **i=3**.

Bài toán **minimum lexicographic rotation** yêu cầu tìm:

~~~text
argmin_i rotation(S,i), 0 <= i < n
~~~

Trong đó argmin là **chỉ số bắt đầu**, không phải chỉ giá trị chuỗi. Khi có nhiều i cho cùng một chuỗi tối thiểu, bài này quy ước **trả chỉ số nhỏ nhất**. Nếu cần chuỗi, dựng từ chỉ số ấy.

**Phép quay không phải đảo ngược chuỗi** và không phải hoán vị tùy ý: thứ tự tuần hoàn của các ký hiệu vẫn được giữ. Mỗi phép quay là một cách chọn điểm xuất phát trên vòng tròn.

### Đầu vào và đầu ra

- Đầu vào: dãy S có n ký hiệu được sắp thứ tự hoàn toàn, có thể là ký tự, số hoặc token.
- Đầu ra chính: chỉ số i nhỏ nhất sao cho rotation(S,i) bé nhất theo thứ tự từ điển.
- Đầu ra tùy chọn: chính chuỗi được quay.
- Với n=0, quy ước duy nhất là chỉ số 0, chuỗi kết quả rỗng.
- Với n=1, chỉ số 0 và kết quả bằng đầu vào.
- Với chuỗi tuần hoàn, có thể có nhiều chỉ số tạo cùng phép quay tối thiểu.

Bài này tập trung vào **thuật toán Booth O(n)** và các điều kiện để áp dụng đúng, không dùng sort tất cả n phép quay.

## 2. Thứ tự từ điển và quy ước ký hiệu

Hai chuỗi cùng độ dài được so sánh từ trái sang phải: ở **vị trí đầu tiên khác nhau**, chuỗi có ký hiệu nhỏ hơn theo thứ tự đã chọn sẽ đứng trước.

~~~text
"abac" < "acab"  vi tai vi tri thu 1: b < c
"abac" < "baca"  vi tai vi tri thu 0: a < b
"abab" = "abab"  neu moi ky hieu tuong ung bang nhau
~~~

Vì các phép quay của S đều dài n, ta không cần quy tắc xử lý khi một chuỗi là tiền tố thực sự ngắn hơn chuỗi kia. Mọi phép so sánh chỉ nhìn tối đa n ký hiệu.

**Phải quyết định chính xác đơn vị ký hiệu.** Với bảng chữ cái ASCII thường, Java char và Unicode code point cho cùng kết quả. Với Unicode nói chung, không phải lúc nào cũng vậy:

- `String.compareTo` trong Java so sánh theo **đơn vị mã UTF-16 (char)**.
- Thứ tự theo **Unicode code point** so sánh các giá trị Unicode vô hướng/số nguyên của từng code point.
- **Thứ tự ngôn ngữ theo locale (collation)** là một hợp đồng khác; không được gọi là thứ tự Unicode mặc định.
- **Grapheme cluster** (ký tự người dùng nhìn thấy) có thể gồm nhiều code point: quay theo code point có thể tách dấu khỏi chữ nền.

Bài Java bên dưới cung cấp **hai API riêng**: phép quay theo UTF-16 code units tương thích thứ tự tự nhiên của `String.compareTo`, và phép quay theo Unicode code points. Chỉ số của hai API **không cùng đơn vị**.

### Ví dụ UTF-16 và code point có thể khác nhau

Xét chuỗi gồm một ký hiệu U+1F600 (emoji) rồi U+E000 (ký hiệu vùng dùng riêng). Về code point:

~~~text
U+E000  <  U+1F600
~~~

Do đó phép quay theo code point nhỏ nhất bắt đầu ở **code-point index 1**.

Nhưng emoji được mã hóa thành cặp UTF-16 surrogate `D83D DE00`; còn U+E000 là một đơn vị `E000`. Vì `D83D < E000`, phép quay theo **UTF-16 code units** nhỏ nhất lại bắt đầu tại **UTF-16 index 0**.

Đây không phải lỗi Booth: thứ tự ký hiệu ở hai bài toán là khác nhau. Nếu đầu vào chứa các surrogate không ghép cặp hợp lệ, phải có chính sách dữ liệu rõ ràng trước khi khẳng định xử lý Unicode chính xác.

## 3. Cách đơn giản: thử tất cả phép quay

Phương pháp dễ nghĩ nhất là:

1. Khởi tạo best=0.
2. Với mỗi i từ 1 tới n−1, so rotation(S,i) với rotation(S,best) từ trái qua phải.
3. Nếu rotation(S,i) nhỏ hơn, cập nhật best=i; nếu bằng thì giữ best cũ để ưu tiên chỉ số nhỏ.
4. Trả best.

Có thể so hai phép quay **mà không cần tạo String mới**:

~~~text
compareRotations(S,i,j):
    for offset = 0..n-1:
        a = S[(i+offset) mod n]
        b = S[(j+offset) mod n]
        if a < b: return -1
        if a > b: return +1
    return 0
~~~

Mỗi lần so có thể xem n ký hiệu; có n phép quay, nên tổng thời gian xấu nhất **O(n²)**. Trên chuỗi nhiều ký hiệu giống nhau, các so sánh thường phải đi rất xa mới gặp khác biệt, nên đây là một worst case thật.

Bộ nhớ phụ chỉ O(1) nếu so bằng chỉ số modulo; nếu tạo s+s thì cần O(n) bộ nhớ thêm. Nếu tạo và giữ tất cả n rotation, bộ nhớ có thể O(n²). Sort n rotation còn tốn nhiều phép so sánh và không phải lời giải mong muốn khi n rất lớn.

### Ví dụ tại sao cách brute-force có vẻ hợp lý

Với S="baca", ta so:

~~~text
best=0: baca
i=1:  acab < baca -> best=1
i=2:  caba > acab -> best=1
i=3:  abac < acab -> best=3
~~~

Kết quả best=3. Tuy nhiên với chuỗi dài một triệu ký hiệu, O(n²) là không chấp nhận được. Booth giải đúng cùng bài toán trong **O(n)** bằng cách loại hàng loạt vị trí ứng viên sau một lần so sánh.

## 4. Ý tưởng Booth: hai ứng viên và độ dài tiền tố khớp

Một biến thể phổ biến của **thuật toán Booth** dùng ba chỉ số:

~~~text
i : vi tri bat dau cua ung vien quay thu nhat
j : vi tri bat dau cua ung vien quay thu hai
k : so ky hieu lien tiep da so bang nhau
~~~

Khởi tạo:

~~~text
i=0, j=1, k=0
~~~

Ở mỗi bước, so hai ký hiệu:

~~~text
a = S[(i+k) mod n]
b = S[(j+k) mod n]
~~~

Nếu a==b, tăng k và tiếp tục so ký hiệu sau. Nếu có khác biệt:

- **a>b:** rotation bắt đầu ở i tệ hơn rotation bắt đầu ở j. Các vị trí từ i tới i+k cũng bị loại bởi một lập luận **loại ứng viên theo đoạn**, nên dời i tới i+k+1; nếu i chạm hoặc vượt j thì dời i tới j+1 để hai ứng viên khác nhau.
- **a<b:** làm tương tự với phía j: dời j tới j+k+1; nếu j chạm/vượt i thì dời j tới i+1.
- Sau mỗi mismatch, đặt k=0.

Dừng khi i hoặc j ra khỏi miền [0,n−1], hoặc khi k=n nghĩa là hai phép quay bằng nhau hoàn toàn. Trả **min(i,j)**. Với n=0, trả 0 ngay và không truy cập modulo n.

### Giả mã chuẩn

~~~text
booth(S):
    n = length(S)
    if n == 0:
        return 0

    i = 0
    j = 1
    k = 0

    while i < n and j < n and k < n:
        x = S[(i+k) mod n]
        y = S[(j+k) mod n]

        if x == y:
            k = k+1
            continue

        if x > y:
            i = i+k+1
            if i <= j:
                i = j+1
        else:
            j = j+k+1
            if j <= i:
                j = i+1

        k = 0

    return min(i,j)
~~~

Đây là **biến thể hai ứng viên** của Booth, không phải phiên bản dùng một mảng failure function/KMP trong một số tài liệu. Cả hai có thể tìm phép quay từ điển nhỏ nhất với thời gian tuyến tính; bài này đi sâu vào phiên bản ba chỉ số vì dễ thấy cơ chế loại ứng viên.

### Tại sao phải kiểm `k < n`?

Nếu mọi ký hiệu của hai phép quay đều bằng nhau trong suốt n vị trí, ta đã xác nhận **hai rotation bằng nhau**. Tiếp tục so quá n có thể lặp vô hạn trên cấu trúc vòng. Vì vậy k=n là điều kiện dừng chủ động; tie được xử lý theo chỉ số nhỏ hơn.

### Tại sao phải giữ i khác j?

Nếu một chỉ số đuổi kịp chỉ số kia, thuật toán sẽ so **một rotation với chính nó** và có thể mất ý nghĩa loại ứng viên. Hai câu lệnh điều chỉnh i<=j và j<=i loại tình trạng trùng ứng viên. Khi một chỉ số chạm n, vòng lặp kết thúc và ứng viên còn lại là kết quả.

## 5. Mô phỏng Booth trên chuỗi "baca"

S="baca", n=4, đánh chỉ số:

~~~text
Index:   0 1 2 3
Symbol:  b a c a

R0 = baca
R1 = acab
R2 = caba
R3 = abac
~~~

Trace biến i,j,k **trước khi so ký hiệu**:

| Lượt | i | j | k | S[(i+k)%4] | S[(j+k)%4] | Xử lý |
| ---: | ---: | ---: | ---: | --- | --- | --- |
| 1 | 0 | 1 | 0 | b | a | b>a → i=2 |
| 2 | 2 | 1 | 0 | c | a | c>a → i=3 |
| 3 | 3 | 1 | 0 | a | a | k=1 |
| 4 | 3 | 1 | 1 | b | c | b<c → j=4 |

Vì j=n=4, dừng và trả **min(3,4)=3**, rotation tối thiểu là **"abac"**.

Ở lượt 3, hai rotation cùng có ký hiệu đầu 'a'. Thuật toán không chỉ so ký hiệu đầu: nó tăng k rồi tìm **vị trí khác đầu tiên**. Khi nhận thấy 'b'<'c', Booth biết có thể loại một **đoạn ứng viên** phía j.

### Trace khác: "banana"

Với S="banana" (n=6), phép quay nhỏ nhất là:

~~~text
i=5 -> abanan
~~~

Những rotation bắt đầu ở vị trí 1 và 3 cũng bắt đầu bằng 'a' nhưng lần lượt là "ananab" và "anaban". Ta phải so sâu hơn ký tự đầu mới phân biệt được:

~~~text
abanan < anaban < ananab
~~~

Booth trả chỉ số **5** mà không cần tạo hoặc lưu tất cả sáu chuỗi quay.

## 6. Vì sao có thể loại cả đoạn i..i+k?

Đây là ý tưởng đúng đắn cốt lõi của Booth.

Giả sử tại một bước ta có:

~~~text
S[i+t] == S[j+t] voi moi t=0..k-1
S[i+k] >  S[j+k]
~~~

Các chỉ số truy cập được hiểu theo modulo n. Nghĩa là hai rotation tại i và j có chung k ký hiệu đầu, nhưng tại ký hiệu thứ k rotation tại i lớn hơn.

Xét một vị trí dịch thêm t với 0≤t≤k. So rotation bắt đầu ở **i+t** với rotation bắt đầu ở **j+t**:

- Chúng vẫn khớp trong **k−t ký hiệu đầu**, do phần tiền tố khớp ban đầu.
- Ký hiệu tiếp theo lần lượt là S[i+k] và S[j+k].
- Vì S[i+k]>S[j+k], rotation tại i+t **lớn hơn** rotation tại j+t.

Vậy mỗi ứng viên bắt đầu ở i,i+1,...,i+k đều có một rotation khác nhỏ hơn nó; **không thể là lời giải tối thiểu**. Ta được phép bỏ qua cả đoạn và chuyển i tới i+k+1. Trường hợp S[i+k]<S[j+k] đối xứng: bỏ j..j+k.

Điểm quan trọng là **bỏ k+1 vị trí sau khi chỉ cần so tới mismatch ở độ lệch k**, chứ không lần lượt so từng rotation từ đầu. Những bước điều chỉnh để i và j không trùng nhau vẫn giữ một đại diện ứng viên còn lại; không làm hồi sinh ứng viên đã bị chứng minh là tệ hơn.

### Trường hợp các rotation bằng nhau

Nếu k=n, hai rotation giống nhau ở đủ n ký hiệu. Cả hai cùng đạt cùng giá trị; quy tắc argmin ưu tiên **chỉ số nhỏ**. Cách `return min(i,j)` phù hợp với tie-breaking này. Với chuỗi tuần hoàn, Booth vẫn trả chỉ số xuất hiện sớm nhất trong những rotation tối thiểu; có thể xác minh bằng vét cạn các trường hợp nhỏ.

### Tính đúng dưới mọi bảng chữ cái

Lập luận chỉ sử dụng **so sánh thứ tự toàn phần giữa các ký hiệu** và tính tuần hoàn. Nó không phụ thuộc ký hiệu là chữ cái Latin, số nguyên hay code point. Điều kiện thiết yếu là comparator nhất quán, không thay đổi trong lúc thuật toán chạy.

## 7. Phân tích thời gian O(n) bằng thế năng

Nhìn vòng while, ta có thể lo ngại việc k trở lại 0 nhiều lần gây O(n²). Nhưng cả i và j chỉ **tăng** và mỗi mismatch dời ít nhất một ứng viên vượt qua toàn bộ phần đã khớp.

Đặt thế năng:

~~~text
Phi = i + j + k
~~~

- Nếu hai ký hiệu bằng nhau, k tăng 1, nên Phi tăng 1.
- Nếu khác nhau, giả sử i được cập nhật: i tăng **ít nhất k+1**, rồi k trở về 0. Độ tăng của Phi ít nhất (k+1)−k=1. Trường hợp cập nhật j tương tự.
- Việc điều chỉnh i=j+1 hoặc j=i+1 chỉ có thể tăng thêm ứng viên, không giảm thế năng.

Trong suốt thời gian còn chạy, i,j≤n và k≤n; vì vậy Phi bị chặn bởi O(n). Mỗi vòng lặp làm Phi tăng ít nhất 1, nên số vòng lặp **O(n)**. Mỗi vòng chỉ thực hiện O(1) phép đọc/so sánh/cộng và modulo, nên tổng thời gian **O(n)**.

### Bộ nhớ phụ

Với đầu vào đã cho phép truy cập ký hiệu O(1) theo chỉ số:

- Thuật toán hai con trỏ chỉ dùng i,j,k và vài biến tạm: **O(1) bộ nhớ phụ**.
- Không cần xây chuỗi S+S nếu dùng modulo.
- Nếu tạo S+S để thuận tiện truy cập, thời gian/bộ nhớ xây chuỗi là O(n), và bộ nhớ phụ tăng lên O(n).
- Nếu chuyển String Java sang mảng `int[]` Unicode code points, việc chuyển đó cần **O(n) bộ nhớ**; bản thân vòng Booth vẫn O(1) ngoài mảng.
- Nếu cần trả ra chuỗi quay dài n, riêng đầu ra cần O(n) ký hiệu; không thể coi toàn bộ công việc có bộ nhớ O(1) nếu tính cả kết quả.

### Chú ý với chỉ số lớn

Trong Java, i,j,k là int. Biểu thức i+k có thể vượt int nếu n rất lớn gần giới hạn. Chương trình dùng phép cộng long trước khi modulo và chặn chỉ số ứng viên vào n để tránh tràn int. Đó là một chi tiết triển khai; không thay đổi thuật toán hay độ phức tạp.

## 8. Chuỗi tuần hoàn và nhiều phép quay tối thiểu

Một chuỗi có thể có nhiều điểm bắt đầu tạo **cùng một rotation nhỏ nhất**. Ví dụ:

| S | Các vị trí nhỏ nhất | Rotation nhỏ nhất |
| --- | --- | --- |
| aaaa | 0,1,2,3 | aaaa |
| abab | 0,2 | abab |
| baba | 1,3 | abab |
| abcabc | 0,3 | abcabc |
| caba | 1 | abac |
| banana | 5 | abanan |

Một vị trí trả về là đủ để dựng **giá trị rotation tối thiểu**. Nhưng nếu đề yêu cầu **mọi chỉ số** đạt cực tiểu, cần xử lý tính chu kỳ.

### Chu kỳ nguyên thủy p

Đặt p là **chu kỳ lặp ngắn nhất chia hết n** sao cho S gồm n/p lần lặp của một khối độ dài p. Nếu chuỗi không phải lặp của khối ngắn hơn, p=n.

Các rotation bắt đầu tại i và i+p (mod n) là như nhau. Nếu r là chỉ số Booth, tập vị trí sinh **cùng rotation tối thiểu** là:

~~~text
{(r + t*p) mod n | t=0..n/p-1}
~~~

Sắp xếp tập này nếu yêu cầu trả indices tăng dần.

Ví dụ "baba": p=2, r=1, tập {1,3}. "aaaa": p=1,r=0, tập {0,1,2,3}.

Có thể tìm p bằng prefix-function của KMP:

~~~text
q = n - pi[n-1]
if n mod q == 0:
    p=q
else:
    p=n
~~~

Với n=0, không áp dụng biểu thức pi[n-1]; xử lý riêng. Đây là bổ trợ khi cần **mọi vị trí** hoặc phát hiện chuỗi tuần hoàn, không phải yêu cầu bắt buộc của Booth khi chỉ cần một chỉ số.

### Giá trị tối thiểu khác với chỉ số tối thiểu

Hai chuỗi "abab" và "baba" có cùng **giá trị phép quay tối thiểu** là "abab", nhưng **chỉ số trả về** lần lượt là 0 và 1. Đừng so hai chuỗi theo chỉ số Booth như một mã định danh: chỉ số phụ thuộc cách nhập chuỗi ban đầu.

## 9. Chọn kiểu chỉ số: UTF-16 hay Unicode code points?

Trong Java, `String.length()` trả số **đơn vị mã UTF-16**, không nhất thiết là số ký tự người dùng nhìn thấy. Một code point ngoài BMP thường chiếm hai `char`.

### Thứ tự UTF-16 giống String.compareTo

Nếu đề xác định thứ tự như `String.compareTo` trong Java, có thể dùng:

~~~java
int n = s.length();
int value = s.charAt(index);
~~~

Chạy Booth trên các giá trị char này. Chỉ số kết quả là **UTF-16 offset**, dùng được với `substring(index)`.

Một phép quay theo code unit có thể bắt đầu **ở giữa một cặp surrogate** nếu chuỗi có emoji; khi đó kết quả chưa chắc là một chuỗi Unicode well-formed, dù phép so sánh UTF-16 vẫn có nghĩa ở mức code units. Đừng âm thầm gọi đó là quay theo Unicode code points.

### Thứ tự theo Unicode code point

Nếu đơn vị bài toán là Unicode code point, dùng:

~~~java
int[] cp = s.codePoints().toArray();
~~~

Chạy Booth trên mảng int này và dựng kết quả bằng `StringBuilder.appendCodePoint`. Chỉ số trả về là **vị trí trong mảng code points**, không phải UTF-16 offset. API `codePoints()` xử lý những surrogate được ghép cặp thành code point; với dữ liệu Unicode lỗi có surrogate lẻ, cần chính sách tiền xử lý rõ ràng.

### Locale và grapheme clusters

Nếu bài yêu cầu thứ tự từ điển theo tiếng Việt có dấu, alphabet hóa theo ngôn ngữ có thể khác thứ tự mã số Unicode. Phải **định nghĩa comparator/ngữ nghĩa token** trước khi chạy thuật toán. Tương tự, nếu muốn giữ nguyên các grapheme cluster (chữ + dấu kết hợp), hãy tách thành token theo quy tắc Unicode grapheme segmentation, rồi so token theo tiêu chí đã định; quay code points trực tiếp có thể tách một cụm.

Thuật toán Booth hoạt động trên **dãy token có thứ tự toàn phần**; nó không tự giải quyết normalization NFC/NFD hoặc collation locale.

## 10. Java 17: cài đặt Booth chạy độc lập

Chương trình minh họa hai kiểu so sánh:

- `smallestUtf16Start(s)`: trả offset UTF-16 của phép quay nhỏ nhất theo char order; không cấp phát mảng ký hiệu.
- `minimalUtf16Rotation(s)`: dựng chuỗi kết quả từ offset.
- `smallestCodePointStart(s)`: trả index theo Unicode code points.
- `minimalCodePointRotation(s)`: dựng chuỗi bằng appendCodePoint, không tách surrogate pair hợp lệ.
- `bruteIndex(a)`: oracle độc lập O(n²) cho dãy số nguyên.
- `exhaustiveCheck()`: so Booth với brute force trên **88.573 chuỗi** độ dài 0–10 thuộc bảng chữ cái ba ký hiệu.

Không cần thư viện ngoài JDK 17. Hàm core nhận một accessor `IntUnaryOperator`, nên dùng được cho UTF-16 charAt hoặc mảng code point mà không lặp mã Booth.

**Lưu toàn bộ mã vào `MinimalRotationBoothDemo.java`:**

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.IntUnaryOperator;

public class MinimalRotationBoothDemo {

    // Return the smallest start index among the least rotations.
    // The symbol accessor must be stable and offer random access.
    private static int boothBy(int n, IntUnaryOperator symbolAt) {
        if (n < 0) {
            throw new IllegalArgumentException("negative length");
        }
        Objects.requireNonNull(symbolAt, "symbolAt");
        if (n == 0) {
            return 0;
        }

        int i = 0;
        int j = 1;
        int k = 0;

        while (i < n && j < n && k < n) {
            // Long arithmetic avoids int overflow in i+k or j+k.
            int ai = (int) (((long) i + k) % n);
            int bj = (int) (((long) j + k) % n);
            int a = symbolAt.applyAsInt(ai);
            int b = symbolAt.applyAsInt(bj);

            if (a == b) {
                k++;
                continue;
            }

            if (a > b) {
                // Drop candidates i through i+k.
                i = (int) Math.min((long) n, (long) i + k + 1);
                if (i <= j) {
                    i = j + 1;
                }
            } else {
                // Drop candidates j through j+k.
                j = (int) Math.min((long) n, (long) j + k + 1);
                if (j <= i) {
                    j = i + 1;
                }
            }
            k = 0;
        }

        return Math.min(i, j);
    }

    // Java String.compareTo uses UTF-16 code unit order.
    public static int smallestUtf16Start(String s) {
        Objects.requireNonNull(s, "s");
        return boothBy(s.length(), s::charAt);
    }

    public static String minimalUtf16Rotation(String s) {
        Objects.requireNonNull(s, "s");
        int i = smallestUtf16Start(s);
        return s.substring(i) + s.substring(0, i);
    }

    // The index here counts Unicode code points, not UTF-16 chars.
    public static int smallestCodePointStart(String s) {
        Objects.requireNonNull(s, "s");
        int[] cp = s.codePoints().toArray();
        return boothBy(cp.length, index -> cp[index]);
    }

    public static String minimalCodePointRotation(String s) {
        Objects.requireNonNull(s, "s");
        int[] cp = s.codePoints().toArray();
        int n = cp.length;
        if (n == 0) {
            return "";
        }
        int start = boothBy(n, index -> cp[index]);
        StringBuilder result = new StringBuilder(s.length());
        for (int t = 0; t < n; t++) {
            int at = (int) (((long) start + t) % n);
            result.appendCodePoint(cp[at]);
        }
        return result.toString();
    }

    // Deliberately independent O(n^2) reference implementation.
    private static int bruteIndex(int[] a) {
        int n = a.length;
        int best = 0;
        for (int start = 1; start < n; start++) {
            for (int offset = 0; offset < n; offset++) {
                int x = a[(start + offset) % n];
                int y = a[(best + offset) % n];
                if (x < y) {
                    best = start;
                    break;
                }
                if (x > y) {
                    break;
                }
            }
        }
        return best;
    }

    // All arrays of length 0..10 over alphabet {0,1,2}.
    private static long exhaustiveCheck() {
        long tested = 0;
        for (int n = 0; n <= 10; n++) {
            int possibilities = 1;
            for (int t = 0; t < n; t++) {
                possibilities *= 3;
            }

            for (int encoding = 0;
                    encoding < possibilities; encoding++) {
                int[] a = new int[n];
                int value = encoding;
                for (int p = 0; p < n; p++) {
                    a[p] = value % 3;
                    value /= 3;
                }

                int booth = boothBy(n, index -> a[index]);
                int brute = bruteIndex(a);
                if (booth != brute) {
                    throw new AssertionError(
                            "Mismatch n=" + n
                            + " encoding=" + encoding
                            + " Booth=" + booth
                            + " brute=" + brute);
                }
                tested++;
            }
        }
        return tested;
    }

    public static void main(String[] args) {
        List<String> cases = List.of(
                "", "a", "baca", "banana", "baba",
                "aaaa", "bbaaccaadd", "abcab");

        for (String s : cases) {
            System.out.println("[" + s + "] -> index "
                    + smallestUtf16Start(s)
                    + ", rotation ["
                    + minimalUtf16Rotation(s) + "]");
        }

        String mixed = "\uD83D\uDE00\uE000";
        System.out.println("mixed UTF-16 index = "
                + smallestUtf16Start(mixed));
        System.out.println("mixed code-point index = "
                + smallestCodePointStart(mixed));
        System.out.println("mixed code-point count = "
                + mixed.codePointCount(0, mixed.length()));

        System.out.println(
                "exhaustive test cases = " + exhaustiveCheck());
    }
}
~~~

**Biên dịch và chạy:**

~~~bash
javac MinimalRotationBoothDemo.java
java MinimalRotationBoothDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
[] -> index 0, rotation []
[a] -> index 0, rotation [a]
[baca] -> index 3, rotation [abac]
[banana] -> index 5, rotation [abanan]
[baba] -> index 1, rotation [abab]
[aaaa] -> index 0, rotation [aaaa]
[bbaaccaadd] -> index 2, rotation [aaccaaddbb]
[abcab] -> index 3, rotation [ababc]
mixed UTF-16 index = 0
mixed code-point index = 1
mixed code-point count = 2
exhaustive test cases = 88573
~~~

### Giải thích tính độc lập và độ phức tạp của mã

`smallestUtf16Start` sử dụng `s::charAt`, không tạo S+S hay mảng ký hiệu, nên riêng việc **tìm chỉ số** có O(n) thời gian và O(1) bộ nhớ phụ đối với String đầu vào.

`smallestCodePointStart` tạo `int[] cp` có m phần tử, m là số code point: O(m) thời gian/bộ nhớ để chuẩn bị dữ liệu, rồi Booth O(m) thời gian, O(1) phụ ngoài mảng. `minimalCodePointRotation` tạo StringBuilder và kết quả dài m code points.

Mã tránh việc cộng i+k bằng int khi chuỗi rất dài: `(long)i+k` được modulo rồi ép về int; khi tăng chỉ số ứng viên, dùng `Math.min(n, ...)` để không vượt miền int. Bản chất thuật toán tuyến tính không đổi.

**Không đánh đồng chỉ số:** `smallestUtf16Start` và `smallestCodePointStart` có thể khác nhau ngay cả khi cùng một String. Khi cần dùng `substring`, chỉ truyền UTF-16 offset; nếu có code-point index, hãy chuyển offset bằng `s.offsetByCodePoints(0,index)` hoặc dựng bằng mảng code point.

### Kiểm brute-force độc lập

Hàm brute so từng rotation bằng modulo, không dùng logic i,j,k của Booth, nên là oracle hợp lý trên chuỗi nhỏ. Có 3^n chuỗi với bảng chữ cái ba ký hiệu ở độ dài n; tổng n=0..10 là:

~~~text
1 + 3 + 9 + ... + 3^10
= (3^11 - 1)/2
= 88573
~~~

Chương trình so cả **chỉ số** (không chỉ giá trị rotation) của Booth với brute, nên nó kiểm luôn tie-breaking ở chuỗi lặp như "aaaa" và "baba". Nếu sai, chương trình ném `AssertionError` với n/encoding và hai chỉ số; nếu đúng, in số ca đã kiểm.

## 11. Chứng minh kết quả thuật toán

Chứng minh dựa trên ba ý chính: (1) mỗi lần loại một đoạn ứng viên đều an toàn, (2) các con trỏ tiến tới khi chỉ còn một ứng viên phù hợp, (3) tổng số lần so tuyến tính.

**Bước 1 – Loại ứng viên an toàn.** Với hai rotation tại i và j có k ký hiệu đầu bằng nhau, nếu ký hiệu sau đó của i lớn hơn, mọi rotation bắt đầu từ i đến i+k đều lớn hơn một rotation tương ứng bắt đầu từ j+t. Không có ứng viên nào trong đoạn ấy là **giá trị nhỏ nhất**. Trường hợp đối xứng loại đoạn j..j+k.

**Bước 2 – Không mất ứng viên tối ưu.** Mỗi lần tăng i hoặc j chỉ bỏ một đoạn đã được chứng minh tệ hơn một rotation khác. Việc điều chỉnh để hai con trỏ không trùng nhau giữ hai vị trí ứng viên khác nhau và không làm một vị trí đã loại trở nên tối ưu. Khi một con trỏ đạt n, chỉ còn ứng viên tối ưu ở phía kia; khi k=n, hai rotation đang so bằng nhau nên chọn chỉ số nhỏ hơn. Mọi cập nhật luôn tiến về phía trước.

**Bước 3 – Chi phí tuyến tính.** Thế năng i+j+k tăng ít nhất 1 mỗi lượt, bị chặn O(n), nên O(n) so sánh. Vì mỗi so và cập nhật là O(1), tổng thời gian O(n).

**Kết luận:** với n>0 và thứ tự ký hiệu nhất quán, Booth trả chỉ số nhỏ nhất của phép quay có thứ tự từ điển nhỏ nhất, dùng O(n) thời gian và O(1) biến bổ sung. Với n=0 quy ước trả 0 được xử lý trực tiếp.

### Tại sao kiểm thử vét cạn vẫn hữu ích?

Chứng minh nêu lý do toán học. Kiểm thử vét cạn kiểm **cài đặt cụ thể** có sai chỉ số, tie-break, reset k hoặc modulo không. Hai việc bổ sung cho nhau: kiểm thử 88.573 ca nhỏ không phải chứng minh tổng quát, nhưng rất hiệu quả để phát hiện lỗi off-by-one.

## 12. Những lỗi triển khai hay gặp

| Lỗi | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| So ký hiệu đầu thay vì toàn rotation | Sai trên chuỗi nhiều ký hiệu đầu giống nhau | So tới mismatch qua k |
| Sau mismatch chỉ tăng i/j một đơn vị | Dễ thành O(n²) | Bỏ cả k+1 ứng viên |
| Quên reset k=0 sau mismatch | So sai tiền tố mới | Reset ngay mỗi lần dời |
| Không kiểm k<n | Có thể so lặp mãi khi rotation bằng nhau | Dừng khi k=n |
| Để i và j trở thành cùng vị trí | So một rotation với chính nó | Điều chỉnh i<=j hoặc j<=i |
| Không xử lý n=0 | Modulo 0 hoặc truy cập ngoài mảng | Trả 0 trước vòng lặp |
| Trả chỉ số 1-based khi đề yêu cầu 0-based | Sai đầu ra | Công bố chỉ số 0-based |
| Không quy ước tie | Kết quả không ổn định trên chuỗi tuần hoàn | Chọn vị trí nhỏ nhất |
| Dùng `s.substring(i)` với code-point index | Cắt sai/giữa surrogate | Dùng offsetByCodePoints hoặc appendCodePoint |
| Xem `String.length()` là số Unicode ký tự | Sai với emoji | Dùng codePoints nếu cần |
| So theo UTF-16 nhưng nói theo Unicode code points | Sai ngữ nghĩa thứ tự | Chọn đơn vị trước |
| Quên normalization NFC/NFD | Hai biểu diễn hiển thị giống nhau nhưng khác ký hiệu | Chuẩn hóa nếu hợp đồng yêu cầu |
| Dùng comparator locale không nhất quán | So không ổn định | Chốt so sánh toàn phần |
| Tạo tất cả n rotation rồi sort | O(n²) bộ nhớ/thời gian lớn | Dùng Booth |
| Bắt đầu k=1 | Bỏ qua ký hiệu đầu khác nhau | k=0 |
| Dùng i+k kiểu int gần giới hạn | Có thể overflow chỉ số | Dùng phép cộng long |
| Tự nối s+s ở n rất lớn | Tốn bộ nhớ và có thể tràn kích thước | Truy cập modulo |
| Dùng thuật toán trên chuỗi thay đổi khi đang chạy | So sánh không còn nhất quán | Dữ liệu bất biến |
| Nhầm rotation với đảo ngược | Bài toán khác | Chỉ nối hậu tố + tiền tố |
| Dùng chỉ số Booth làm khóa đại diện lớp quay | Hai đầu vào cùng lớp có chỉ số khác | Dùng giá trị rotation tối thiểu |

## 13. Các trường hợp biên cần kiểm

### Chuỗi rỗng và một ký hiệu

~~~text
S=""      -> index 0, rotation ""
S="a"     -> index 0, rotation "a"
~~~

Trường hợp rỗng không có n vị trí hợp lệ theo định nghĩa thông thường, nhưng nhiều API quy ước trả 0 cho chuỗi rỗng để hoạt động nhất quán. Hãy ghi rõ quy ước nếu đề thực tế khác.

### Tất cả ký hiệu giống nhau

~~~text
S="aaaa" -> index 0, rotation "aaaa"
~~~

Mọi vị trí là tối ưu; trả vị trí nhỏ nhất. k có thể tăng tới n. Nếu bỏ điều kiện k<n, vòng so có thể không kết thúc.

### Chuỗi tuần hoàn

~~~text
S="abab"   -> index 0, rotation "abab"
S="baba"   -> index 1, rotation "abab"
S="abcabc" -> index 0, rotation "abcabc"
~~~

Nhiều vị trí cho cùng rotation, nhưng trả chỉ số xuất hiện sớm nhất.

### Chuỗi không tuần hoàn

~~~text
S="baca"       -> index 3, rotation "abac"
S="banana"     -> index 5, rotation "abanan"
S="bbaaccaadd" -> index 2, rotation "aaccaaddbb"
S="abcab"      -> index 3, rotation "ababc"
~~~

Đặc biệt ở "banana", nhiều vị trí bắt đầu bằng 'a'. Thuật toán phải so sâu, không chọn 'a' đầu tiên một cách máy móc.

### Ký hiệu lạ và Unicode

- Chữ hoa và chữ thường: theo mã số ASCII/Unicode, 'A'<'a'; không tự chuyển về chữ thường nếu đề không yêu cầu.
- Khoảng trắng và dấu câu là ký hiệu hợp lệ nếu đầu vào chứa chúng.
- NUL hoặc ký hiệu 0 trong dãy số không phải ký tự kết thúc khi dùng độ dài n tường minh.
- Unicode emoji có thể chiếm hai UTF-16 `char`; phải chọn API chính xác.
- Chuỗi chuẩn hóa Unicode khác nhau có thể hiển thị giống nhau mà dãy code points khác; làm rõ trước khi so.
- Grapheme clusters có thể gồm ký hiệu nền và dấu kết hợp; quay theo code point có thể tách cụm.

## 14. Kiểm thử bằng oracle và thuộc tính

### Oracle O(n²)

Trên chuỗi nhỏ, liệt kê mỗi vị trí i, so rotation(S,i) với rotation(S,best) từng ký hiệu bằng modulo. Nếu rotation ứng viên **nhỏ hơn**, cập nhật best; nếu bằng, giữ vị trí cũ. Sau khi xét xong, best là chỉ số nhỏ nhất trong các phép quay tối thiểu.

### Các thuộc tính đáng kiểm

1. Nếu n=0, trả 0; nếu n>0, kết quả thuộc [0,n−1].
2. Rotation được trả có đúng n ký hiệu và cùng multiset ký hiệu với S.
3. Với mọi i, rotation(S,best)≤rotation(S,i).
4. Nếu có nhiều i tạo giá trị tối thiểu, best là **i nhỏ nhất**.
5. Kết quả của Booth trùng oracle trên tất cả chuỗi nhỏ đã sinh.
6. Nếu S tuần hoàn theo p, các rotation tại best+tp modulo n tạo cùng giá trị.
7. Nếu chỉ quay đầu vào một bước, **giá trị tối thiểu** không đổi, dù best index có thể đổi.
8. Nếu áp dụng Booth vào chính chuỗi rotation tối thiểu, best index là 0.
9. So theo UTF-16 code units phải trùng thứ tự `String.compareTo` trên các rotation được dựng từ code units.
10. So theo Unicode code points phải trùng comparator trên mảng code points.
11. Đầu vào không bị sửa bởi API; kết quả có thể dựng lại đúng từ index.
12. Các chuỗi có ký hiệu giống nhau dài phải hoàn thành trong thời gian tuyến tính, không rơi về O(n²).

### Sinh trường hợp ngẫu nhiên

Sinh các chuỗi độ dài 0..100 từ alphabet kích thước 2,3,5, kể cả các khối lặp dài, xen kẽ, và ký hiệu nhỏ nhất nằm gần cuối. Với n≤100, dùng oracle O(n²) để đối chiếu. Với n lớn, so cả invariant và thời gian chạy, nhưng đừng lấy benchmark làm thay chứng minh độ phức tạp.

Thử riêng Unicode code points ngoài BMP, đầu vào có dấu kết hợp và những cặp surrogate không hợp lệ theo chính sách dữ liệu. Không so code-point index trực tiếp với UTF-16 index, vì khác đơn vị.

## 15. Ứng dụng trong thuật toán chuỗi nâng cao

### Chuẩn hóa chuỗi tuần hoàn

Nếu hai chuỗi được xem là tương đương khi một chuỗi là **phép quay** của chuỗi kia, có thể tính minimal rotation cho từng chuỗi và so **giá trị** chuẩn hóa.

~~~text
S1="abab"
S2="baba"

minRotation(S1)="abab"
minRotation(S2)="abab"

=> S1 va S2 tuong duong duoi phep quay
~~~

Đây là ý tưởng xây **canonical representation** cho những chuỗi vòng, ví dụ dữ liệu vòng tròn, mô tả chuỗi DNA vòng ở mức mô hình hoặc mẫu tuần hoàn. Khi áp dụng, ký hiệu, chiều dài và tiêu chí so phải thống nhất.

### Phân loại lớp tương đương

Với tập nhiều chuỗi cùng độ dài, tính giá trị minimal rotation rồi nhóm theo kết quả. Các chuỗi cùng lớp quay sẽ có cùng giá trị đại diện, bất kể cách chọn điểm bắt đầu.

Chi phí cho mỗi chuỗi độ dài n là O(n) để tìm index và O(n) để dựng canonical string. Nếu dùng hash để nhóm, phải xử lý va chạm theo ngữ nghĩa bằng cách so chuỗi khi cần; bản thân Booth không phải hàm băm.

### Rotation khác reversal

Nếu đề coi hai chuỗi tương đương dưới cả **quay và đảo ngược**, đó là lớp tương đương kiểu bracelet/dihedral, khác bài toán chỉ quay. Có thể so minimalRotation(S) với minimalRotation(reverse(S)) và chọn giá trị nhỏ hơn **theo đúng đơn vị ký hiệu**.

Không tự thêm đảo ngược nếu đề chỉ hỏi cyclic rotation, vì sẽ thay đổi tập ứng viên.

### Liên hệ với các thuật toán khác

- **KMP/prefix function:** hữu ích để tìm chu kỳ nguyên thủy p và liệt kê mọi vị trí tạo cùng phép quay.
- **Duval/Lyndon factorization:** một họ kỹ thuật khác liên quan thứ tự từ điển và chuỗi tuần hoàn; có biến thể tìm minimal rotation tuyến tính.
- **Suffix array:** có thể hỗ trợ bài toán phức tạp hơn về nhiều hậu tố/chuỗi con, nhưng không cần xây suffix array chỉ để tìm một minimal rotation.
- **String matching:** để kiểm S2 có phải rotation của S1, có thể tìm S2 như một chuỗi con dài n trong S1+S1; khi chỉ cần giá trị chuẩn hóa nhất quán, Booth là một lựa chọn tự nhiên.

## 16. Bài tập thực hành

1. Liệt kê mọi rotation của "baca" và kiểm index tối thiểu bằng tay.
2. Liệt kê mọi rotation của "banana"; xác nhận index5.
3. Mô phỏng bảng i,j,k của Booth trên "baca".
4. Mô phỏng i,j,k trên "bbaaccaadd"; đối chiếu index2.
5. Chứng minh tại mismatch sau k ký hiệu khớp, có thể loại k+1 vị trí ứng viên.
6. Viết lại chứng minh O(n) bằng thế năng i+j+k.
7. Cài brute-force O(n²) không tạo tất cả rotation.
8. Sinh toàn bộ chuỗi độ dài 0..8 từ alphabet {0,1,2}; so chỉ số Booth và brute.
9. Phân biệt so bằng giá trị rotation và tie-break chỉ số nhỏ nhất.
10. Xác định các chỉ số tối ưu của "aaaa", "baba" và "abcabc".
11. Dùng KMP prefix function tìm chu kỳ nguyên thủy của "abcabc" và "abab".
12. Với chu kỳ p, chứng minh các vị trí cách nhau p tạo cùng rotation.
13. Cài API trả mọi chỉ số minimal rotation theo p và Booth index.
14. Viết phiên bản Booth trên `int[]` gồm số âm và số dương, dùng thứ tự tăng dần.
15. Cài API theo UTF-16 charAt, kiểm khớp comparator `String.compareTo`.
16. Cài API theo Unicode code points và dựng StringBuilder appendCodePoint.
17. Tìm input có code-point index khác UTF-16 index; giải thích bằng surrogate.
18. Kiểm ký tự có dấu dưới NFC/NFD và giải thích vì sao cần hợp đồng chuẩn hóa.
19. Cài canonicalization của chuỗi modulo phép quay và nhóm 100 chuỗi theo lớp.
20. Mở rộng lớp tương đương cho phép đảo ngược, chỉ rõ đó không còn là bài Booth ban đầu.
21. Xử lý chuỗi dài một triệu ký hiệu mà không nối S+S; đo bộ nhớ phụ.
22. Kiểm all-equal n lớn để tránh vòng lặp vô hạn khi k tăng đến n.
23. Sửa lỗi thử nghiệm bỏ reset k=0 và tìm phản ví dụ.
24. Sửa lỗi để hai ứng viên i=j và tìm ca gây hành vi không đúng.
25. Giải thích vì sao indices của hai chuỗi cùng lớp quay không nhất thiết bằng nhau.
26. Nêu điều kiện đối với comparator để phép loại ứng viên vẫn đúng.

## 17. Checklist và tổng kết

Trước khi sử dụng Booth, hãy kiểm tra:

- Đề cần **giá trị** phép quay nhỏ nhất hay **chỉ số bắt đầu**?
- Chỉ số yêu cầu 0-based hay 1-based; với tie chọn chỉ số nào?
- Đơn vị ký hiệu là byte, UTF-16 char, Unicode code point hay token?
- Comparator có nhất quán và phản ánh đúng thứ tự từ điển của đề không?
- n=0, n=1, chuỗi all-equal và chuỗi tuần hoàn đã được xử lý chưa?
- Hai ứng viên i,j có luôn khác nhau, k có bị giới hạn dưới n không?
- Khi mismatch có bỏ trọn k+1 vị trí và reset k đúng không?
- Có tránh tràn i+k ở n rất lớn và tránh nhân đôi chuỗi không cần thiết không?
- Nếu cần dựng chuỗi kết quả, chỉ số đang dùng có cùng đơn vị với API dựng chuỗi không?
- Có kiểm chứng bằng oracle O(n²) trên chuỗi nhỏ và trên Unicode đặc biệt không?

**Kết luận:** thuật toán Booth tìm **phép quay có thứ tự từ điển nhỏ nhất** của một dãy trong **O(n) thời gian** và **O(1) bộ nhớ phụ** nếu có truy cập ký hiệu O(1). Sức mạnh nằm ở việc so hai phép quay đến ký hiệu khác đầu tiên rồi **loại cả một đoạn các điểm bắt đầu chắc chắn không tối ưu**, thay vì kiểm từng rotation từ đầu. Với Java, cần đặc biệt thống nhất ngữ nghĩa **UTF-16 code units** so với **Unicode code points**, xử lý chuỗi rỗng, tie của chuỗi tuần hoàn và xác minh bằng brute force trên các ca nhỏ.
