# Thuật toán Manacher cho các đoạn đối xứng

**Đoạn đối xứng** (*palindromic substring*) là một đoạn liên tiếp của chuỗi đọc từ trái sang phải cũng giống như đọc từ phải sang trái. Ví dụ `"aba"`, `"abba"`, `"racecar"` đều đối xứng; `"abca"` không đối xứng vì hai ký tự ở giữa không khớp.

Nếu chỉ hỏi một đoạn cụ thể có đối xứng hay không, ta có thể dùng hai con trỏ đi từ hai đầu với thời gian O(độ dài đoạn). Nhưng khi cần **đoạn đối xứng dài nhất**, **đếm mọi đoạn đối xứng**, hoặc kiểm tra rất nhiều đoạn trên cùng một chuỗi, thử từng đoạn sẽ tốn thời gian. **Manacher** là thuật toán tính thông tin đối xứng quanh **mọi tâm** trong **O(n) thời gian**, với n là chiều dài chuỗi.

Thay vì dùng một cấu trúc chuỗi biến đổi với ký tự phân cách, bài học này chọn phiên bản **hai mảng bán kính**:

- `odd[i]` (còn gọi `d1[i]`): số bán kính đối xứng **lẻ** tại tâm là ký tự i; **bao gồm chính ký tự tâm**.
- `even[i]` (còn gọi `d2[i]`): số cặp đối xứng **chẵn** quanh khe ngay **trước** ký tự i.

Từ hai mảng này ta lấy được **đoạn đối xứng dài nhất**, **tổng số lần xuất hiện các đoạn đối xứng** và trả lời truy vấn **một đoạn [L,R) có đối xứng không?** trong O(1), sau bước tiền xử lý O(n).

Bài học đi từ định nghĩa, cách mở rộng quanh tâm O(n²), cơ chế tái sử dụng kết quả qua **tâm phản chiếu** trong Manacher, các công thức ranh giới dễ lệch một đơn vị, chứng minh O(n), mã **Java 17+ chạy độc lập**, ví dụ đầu ra, Unicode/UTF-16, kiểm thử vét cạn và các câu hỏi tự luyện.

## 1. Định nghĩa đoạn đối xứng và bài toán cần giải

Cho chuỗi S có n đơn vị ký tự, chỉ số từ 0 tới n−1. Một đoạn `S[L,R)` dùng quy ước **nửa mở**: chứa các vị trí L,L+1,...,R−1 và có độ dài:

\[
len=R-L.
\]

Đoạn này là đối xứng khi:

\[
\boxed{\forall k\in[0,\lfloor len/2\rfloor):
S[L+k]=S[R-1-k].}
\]

Các ký tự ở hai đầu được so đối xứng quanh tâm. Nếu có một cặp khác nhau, đoạn không đối xứng.

Ví dụ với S=`"abacaba"`:

- `S[0,7)="abacaba"`: đối xứng, dài 7.
- `S[1,6)="bacab"`: đối xứng, dài 5.
- `S[2,5)="aca"`: đối xứng, dài 3.
- `S[0,4)="abac"`: không đối xứng.
- `S[0,0)=""`: theo quy ước toán học, đoạn rỗng đối xứng; tuy nhiên khi **đếm các đoạn đối xứng xuất hiện**, thông thường chỉ đếm **đoạn không rỗng**.

Có ba nhiệm vụ thường bị gộp tên nhưng khác đầu ra:

1. **Longest palindromic substring:** tìm một đoạn đối xứng có độ dài lớn nhất. Nếu nhiều đoạn dài bằng nhau, ta có thể chọn đoạn bắt đầu **sớm nhất**.
2. **Count palindromic substrings:** đếm **tất cả các vị trí xuất hiện** của đoạn đối xứng không rỗng, kể cả cùng nội dung ở nhiều vị trí.
3. **Palindrome range query:** sau khi tiền xử lý S, kiểm tra một đoạn `[L,R)` cụ thể có đối xứng hay không.

Manacher giải cả ba nhiệm vụ từ cùng hai mảng bán kính. Nó **không tự tính số đoạn đối xứng phân biệt về nội dung**: đếm số chuỗi con khác nhau cần thêm cơ chế loại trùng, ví dụ palindromic tree/eertree hay cấu trúc phù hợp.

## 2. Hai kiểu tâm đối xứng: lẻ và chẵn

Một đoạn đối xứng có thể có:

- **Độ dài lẻ:** tâm là **một ký tự**. Ví dụ `"aba"`, tâm ở ký tự `b`.
- **Độ dài chẵn:** tâm nằm ở **khe giữa hai ký tự**. Ví dụ `"abba"`, tâm ở khe giữa hai ký tự `b`.

Nếu chỉ kiểm tra tâm tại các ký tự, ta sẽ bỏ sót mọi đoạn đối xứng độ dài chẵn.

### Bán kính lẻ odd[i]

Định nghĩa `odd[i]` là **số mức bán kính** mà đối xứng vẫn đúng quanh ký tự i, **bao gồm bán kính 1 cho chính ký tự tâm**:

\[
\boxed{
odd[i]=\max\{k\ge1\mid
S[i-k+1,i+k)\text{ đối xứng}\}.
}
\]

Vì một ký tự luôn đối xứng với chính nó, với mọi i hợp lệ:

\[
odd[i]\ge1.
\]

Từ `odd[i]=k`, đoạn đối xứng lẻ dài nhất ở tâm i có:

\[
\boxed{L=i-k+1,\quad R=i+k,\quad len=2k-1}.
\]

Chú ý R là **đầu mút loại trừ**. Nếu muốn lưu hai đầu mút **bao gồm**, chúng là `i-k+1` và `i+k-1`.

Ví dụ `"abacaba"` có tâm i=3 là `c`; đoạn đối xứng dài nhất là toàn bộ chuỗi với k=4:

~~~text
S:       a b a c a b a
index:   0 1 2 3 4 5 6
                 ^
                i=3

odd[3]=4
L=3-4+1=0
R=3+4=7
length=2*4-1=7
~~~

### Bán kính chẵn even[i]

Định nghĩa `even[i]` là **số cặp ký tự đối xứng** quanh khe **giữa i−1 và i**:

\[
\boxed{
even[i]=\max\{k\ge0\mid
S[i-k,i+k)\text{ đối xứng}\}.
}
\]

Nếu hai ký tự sát khe không bằng nhau, `even[i]=0`: **không có đoạn chẵn không rỗng** tại khe ấy.

Từ `even[i]=k>0`, đoạn chẵn dài nhất có:

\[
\boxed{L=i-k,\quad R=i+k,\quad len=2k}.
\]

Ví dụ với S=`"abba"`, khe giữa hai ký tự b là i=2:

~~~text
S:       a b | b a
index:   0 1 | 2 3
              ^
             i=2

even[2]=2
L=2-2=0
R=2+2=4
length=4
~~~

Cách đánh chỉ số `even[i]` tại khe **trước i** là một quy ước rất phổ biến. Nếu tài liệu khác đánh khe **sau i**, công thức truy vấn sẽ thay đổi. Không được trộn hai quy ước.

## 3. Ba ví dụ mảng bán kính đầy đủ

### S = "abacaba"

~~~text
i:       0 1 2 3 4 5 6
S[i]:    a b a c a b a
odd:     1 2 1 4 1 2 1
even:    0 0 0 0 0 0 0
~~~

Giải thích:

- Mọi tâm ký tự đều có đoạn dài 1 ⇒ odd tối thiểu 1.
- Ở i=1, `"aba"` dài 3 ⇒ odd[1]=2.
- Ở i=3, `"abacaba"` dài 7 ⇒ odd[3]=4.
- Không có hai ký tự kề nhau nào bằng nhau ⇒ even toàn 0.

### S = "abba"

~~~text
i:       0 1 2 3
S[i]:    a b b a
odd:     1 1 1 1
even:    0 0 2 0
~~~

Tâm chẵn i=2 có hai cặp đối xứng: `b-b` và `a-a`, nên even[2]=2, đoạn dài nhất `"abba"` dài 4.

### S = "aaaa"

~~~text
i:       0 1 2 3
S[i]:    a a a a
odd:     1 2 2 1
even:    0 1 2 1
~~~

Chuỗi này đặc biệt hữu ích để kiểm tra lỗi lệch chỉ số: **mọi đoạn liên tiếp không rỗng đều đối xứng**.

Với n=4, tổng số đoạn không rỗng là:

\[
1+2+3+4=10.
\]

Manacher cũng phải đếm được đúng 10; điều này kiểm tra đồng thời cả odd lẫn even.

## 4. Cách đơn giản: mở rộng quanh từng tâm O(n²)

Trước Manacher, nên hiểu cách **expand around center**.

Đối với mỗi tâm lẻ i:

~~~text
left=i, right=i
while left>=0 and right<n and S[left]==S[right]:
    record a palindrome
    left--
    right++
~~~

Đối với mỗi tâm chẵn là khe i:

~~~text
left=i-1, right=i
while left>=0 and right<n and S[left]==S[right]:
    record a palindrome
    left--
    right++
~~~

Có n tâm lẻ và n−1 khe chẵn nội bộ. Trong trường hợp S gồm toàn ký tự giống nhau, mỗi tâm có thể mở rộng tới O(n) bước, tạo:

\[
\boxed{O(n^2)\text{ thời gian xấu nhất}.}
\]

Nếu chỉ cần biết có đoạn đối xứng hay không, mở rộng quanh tâm đủ cho dữ liệu nhỏ. Nếu cần số đoạn đối xứng và n lớn, cách này có thể tốn hàng tỷ lần so sánh.

### Vấn đề của cách O(n²)

Xét chuỗi `"aaaaaaaaaa..."`. Khi xử lý tâm gần giữa, thuật toán lặp lại nhiều phép so sánh đã được chứng minh đối xứng khi xử lý một tâm trước đó. **Manacher tái sử dụng thông tin từ tâm phản chiếu** để tránh lặp lại các phép so sánh nằm trọn trong vùng đối xứng lớn nhất đã biết.

## 5. Ý tưởng Manacher: vùng đối xứng đang vươn xa nhất

Ta duyệt các tâm từ trái sang phải, duy trì một đoạn đối xứng `[left,right]` với **hai đầu mút bao gồm**, là đoạn đã biết vươn xa nhất sang phải trong những đoạn được xét tới thời điểm hiện tại.

Trong thuật toán mảng odd:

- Nếu i nằm **ngoài** đoạn `[left,right]`, ta chưa có thông tin đối xứng hữu ích ở tâm i; bán kính lẻ khởi đầu là **1**.
- Nếu i nằm **trong** đoạn, dùng **tâm phản chiếu** của i qua tâm đoạn `[left,right]`.

Công thức tâm phản chiếu cho **odd**:

\[
\boxed{mirror=left+right-i}.
\]

Tương đương \(mirror=left+(right-i)\), cách viết này giảm nguy cơ cộng hai chỉ số lớn trước khi trừ.

Vì `[left,right]` đối xứng, phần đối xứng quanh mirror **nằm hoàn toàn trong đoạn đã biết** có thể được phản chiếu sang tâm i. Vì vậy bán kính khởi đầu tại i là:

\[
\boxed{
k=\min(odd[mirror],\ right-i+1)
}
\]

nếu i≤right. Phần `right-i+1` là mức bán kính tối đa của một đoạn lẻ tâm i **không đi vượt biên phải**.

Nếu i>right, khởi đầu:

\[
k=1.
\]

Sau đó chỉ so sánh các ký tự **ngay bên ngoài** bán kính k đã biết, bằng vòng `while`, và mở rộng nếu chúng bằng nhau.

Khi tìm được bán kính `odd[i]=k`, đoạn tương ứng có:

\[
newLeft=i-k+1,\qquad newRight=i+k-1.
\]

Nếu `newRight>right`, cập nhật vùng đang giữ.

### Ba tình huống với tâm phản chiếu

Giả sử i ở trong vùng đối xứng `[left,right]` và mirror là tâm phản chiếu:

1. **odd[mirror] hoàn toàn nằm trong vùng**: có thể sao chép bán kính tới i mà không so sánh lại.
2. **odd[mirror] vượt qua biên trái của vùng**: tại i ta chỉ dám tin tới biên phải `right`; bán kính khởi đầu bị chặn bởi `right-i+1`.
3. **odd[mirror] vừa chạm biên**: phần bên trong chắc chắn đối xứng, nhưng phần tiếp theo **chưa biết**; vòng `while` có thể mở rộng vượt khỏi vùng cũ.

Mục tiêu của `min` là **không suy ra tính đối xứng ở những vị trí chưa có chứng cứ**. Tái sử dụng thông tin quá xa có thể trả về bán kính lớn hơn thực tế.

## 6. Manacher cho tâm lẻ: công thức không lệch một đơn vị

Thuật toán chuẩn:

~~~text
odd = int[n] initialized to 0
left=0, right=-1    // vùng đối xứng đã biết hiện rỗng

for i=0..n-1:
    if i>right:
        k=1
    else:
        mirror = left + (right-i)
        k = min(odd[mirror], right-i+1)

    while i-k>=0 AND i+k<n
          AND S[i-k]==S[i+k]:
        k++

    odd[i]=k

    if i+k-1>right:
        left=i-k+1
        right=i+k-1
~~~

**Giải thích cẩn thận điều kiện while:**

Khi k=1, ký tự tâm `S[i]` đã được tính là đoạn đối xứng dài 1. Cặp cần kiểm đầu tiên là `S[i-1]` và `S[i+1]`. Vì vậy hai chỉ số so sánh là `i-k` và `i+k`, không phải `i-k+1` và `i+k-1`.

Khi đã mở rộng thành công, k tăng thêm 1. Đoạn có độ dài `2*k-1` và hai đầu `i-k+1`, `i+k-1`.

Nếu dùng `k=0` làm bán kính lẻ khởi tạo mà vẫn giữ nguyên các công thức của bài này, sẽ dễ đếm thiếu chính ký tự tâm.

### Biên trái phải và vùng rỗng ban đầu

Giá trị `right=-1` biểu thị chưa có vùng nào được ghi nhận. Mỗi i≥0 đều thỏa i>right ở thời điểm đầu tiên. Sau xử lý i=0, `odd[0]=1`, cập nhật `left=0,right=0`, đúng đoạn một ký tự.

Với chuỗi rỗng n=0, vòng lặp không chạy; odd là mảng rỗng, không cố truy cập `S[0]`.

## 7. Manacher cho tâm chẵn: khe trước i

Tâm chẵn nằm **giữa i−1 và i**, nên bán kính khởi đầu khi chưa có thông tin là **0** (chưa có cặp đối xứng nào).

Công thức phản chiếu trong phiên bản chẵn phải dịch một vị trí so với odd:

\[
\boxed{mirror=left+right-i+1}.
\]

Với i nằm trong vùng đã biết:

\[
\boxed{k=\min(even[mirror],\ right-i+1)}.
\]

Nếu i>right thì k=0.

Vòng mở rộng:

~~~text
while i-k-1>=0 AND i+k<n
      AND S[i-k-1]==S[i+k]:
    k++
~~~

Sau đó `even[i]=k` và đoạn chẵn lớn nhất tại khe i có biên **bao gồm**:

\[
leftNew=i-k,\qquad rightNew=i+k-1.
\]

Cập nhật vùng khi `rightNew>right`.

### Mã giả đầy đủ

~~~text
even = int[n] initialized to 0
left=0, right=-1

for i=0..n-1:
    if i>right:
        k=0
    else:
        mirror=left+(right-i)+1
        k=min(even[mirror],right-i+1)

    while i-k-1>=0 AND i+k<n
          AND S[i-k-1]==S[i+k]:
        k++

    even[i]=k

    if i+k-1>right:
        left=i-k
        right=i+k-1
~~~

Sự khác biệt đáng nhớ:

| Thành phần | Tâm lẻ odd | Tâm chẵn even |
|---|---|---|
| Tâm | Ký tự i | Khe trước i |
| k ban đầu ngoài vùng | **1** | **0** |
| Mirror | `left+right-i` | `left+right-i+1` |
| Cặp so sánh | `S[i-k]` và `S[i+k]` | `S[i-k-1]` và `S[i+k]` |
| Biên trái của đoạn mới | `i-k+1` | `i-k` |
| Biên phải (bao gồm) | `i+k-1` | `i+k-1` |
| Độ dài lớn nhất | `2*k-1` | `2*k` |

**Lỗi +1/−1 ở chẵn là lỗi kinh điển.** Hai mảng có nhiều công thức tương tự nhưng không giống hệt nhau, vì tâm lẻ là ký tự còn tâm chẵn là khe.

## 8. Mô phỏng kỹ hai trường hợp

### Tâm lẻ với "abacaba"

Tại i=0, odd[0]=1. Ở i=1, cặp S[0] và S[2] cùng là `a`, nên odd[1]=2 và vùng đã biết tiến tới [0,2]. Ở i=2, vị trí mirror trong vùng cho k=1, tránh so sánh lại phần đã chứng minh.

Tại i=3, mở rộng qua ba cặp:

~~~text
S[2] == S[4]   a == a
S[1] == S[5]   b == b
S[0] == S[6]   a == a
~~~

Do đã tính tâm với k=1, sau ba lần mở rộng thành công k=4, odd[3]=4 và đoạn vươn xa tới [0,6]. Các tâm tiếp theo nằm trong đoạn đối xứng lớn này; nhiều bán kính có thể được suy ra nhờ phản chiếu.

Kết quả:

~~~text
odd = [1,2,1,4,1,2,1]
even = [0,0,0,0,0,0,0]
longest = "abacaba", start=0, length=7
~~~

### Tâm chẵn với "abba"

Ở khe i=2, ban đầu k=0. So sánh:

~~~text
i=2, k=0: S[1] == S[2]  => b == b
i=2, k=1: S[0] == S[3]  => a == a
i=2, k=2: vượt biên trái
~~~

Vậy even[2]=2, biểu diễn đoạn `S[0,4)="abba"` dài 4. Mọi odd[i]=1 vì không có đoạn lẻ dài hơn một ký tự trong ví dụ.

~~~text
odd = [1,1,1,1]
even = [0,0,2,0]
longest = "abba", start=0, length=4
~~~

### Trường hợp ký tự giống nhau

Với S=`"aaaa"`, giá trị:

~~~text
odd  = [1,2,2,1]
even = [0,1,2,1]
~~~

Tâm lẻ ở i=1 và i=2 đều có đoạn dài 3, nhưng tâm chẵn ở i=2 có đoạn dài 4. Khi tìm đoạn dài nhất, **phải xét cả odd và even**; chỉ lấy odd sẽ trả sai là dài 3.

## 9. Chứng minh vì sao thuật toán chạy O(n)

Một cách mở rộng quanh từng tâm tốn O(n²) trong trường hợp xấu nhất vì lặp lại so sánh các cặp trong vùng đối xứng đã biết. Manacher tránh việc này bằng ba nhận xét.

**Thứ nhất:** khi tâm i nằm trong `[left,right]`, phần đối xứng của mirror nằm trọn vùng có thể sao chép, không phải so sánh lại từ đầu. Công thức k=`min(radius[mirror],right-i+1)` xác định bán kính chắc chắn đúng.

**Thứ hai:** khi vòng `while` mở rộng **thành công** từ biên ngoài vùng đã biết, chỉ số biên phải `right` tăng. Trong mỗi lượt chạy riêng odd hoặc even, `right` chỉ có thể tăng từ -1 tới tối đa n−1, nên có **O(n)** lần mở rộng thành công vượt biên.

**Thứ ba:** mỗi tâm chỉ có một số hữu hạn lần kiểm tra thất bại khi hết khả năng mở rộng (sai ký tự hoặc chạm biên), nên tổng số kiểm tra thất bại là **O(n)**. Các thao tác tra mirror, lấy min, ghi bán kính và cập nhật biên là O(1) mỗi tâm.

Vì vậy:

\[
\boxed{\text{Odd Manacher}=O(n)}
\]

và:

\[
\boxed{\text{Even Manacher}=O(n).}
\]

Hai lượt cộng lại vẫn O(n), dùng hai mảng bán kính O(n) phần tử:

\[
\boxed{\text{Thời gian }O(n),\quad \text{bộ nhớ }O(n).}
\]

### Điều kiện để áp dụng lập luận

Lập luận cần đúng quy tắc **khởi tạo từ mirror rồi chỉ mở rộng ngoài phần đã biết**. Một phiên bản gọi `expand` từ bán kính 0 ở **mọi** tâm, dù vẫn đặt tên Manacher, không đạt bảo đảm O(n).

Cũng không được chạy vòng lặp kiểm tra toàn đoạn `S[L,R)` cho mọi truy vấn và gọi đó là truy vấn O(1): O(1) chỉ đúng khi **đã có odd/even** và so sánh một bán kính phù hợp.

## 10. Tìm đoạn đối xứng dài nhất trong O(n)

Với mỗi tâm i, ta có hai ứng viên:

\[
lenOdd_i=2\cdot odd[i]-1,
\quad startOdd_i=i-odd[i]+1;
\]

\[
lenEven_i=2\cdot even[i],
\quad startEven_i=i-even[i].
\]

So sánh ứng viên để giữ đoạn dài nhất. Nếu hai ứng viên dài bằng nhau, bài này chọn **vị trí bắt đầu nhỏ hơn** (leftmost tie-break) để kết quả xác định.

Cách này thêm một lượt O(n), không làm thay đổi tổng thời gian.

### Ví dụ nhiều nghiệm dài nhất

S=`"babad"` có:

~~~text
"bab" at [0,3)
"aba" at [1,4)
~~~

Cả hai đều dài 3. Nếu dùng tie-break chọn vị trí bắt đầu sớm nhất, kết quả là `"bab"` tại start 0.

Nếu chỉ dùng điều kiện `len>bestLen`, kết quả phụ thuộc thứ tự duyệt odd/even và thứ tự các tâm. Nếu đề yêu cầu chính xác **lời giải sớm nhất**, phải xử lý tie rõ ràng.

### Chuỗi rỗng

Khi n=0, không có đoạn đối xứng **không rỗng**. Chương trình trả:

~~~text
longest="", start=0, length=0
totalOccurrences=0
~~~

Đây là quy ước API, không phải tìm thấy một lần xuất hiện có độ dài dương.

### Không nhất thiết duy nhất

Một chuỗi có thể có nhiều đoạn đối xứng dài nhất bằng độ dài nhưng khác vị trí hoặc nội dung. Nếu đề chỉ yêu cầu “một đoạn dài nhất”, bất kỳ đoạn tối ưu nào đều đúng. Nếu đề cần **tất cả** các đoạn dài nhất, có thể thu thập mọi tâm có độ dài tối ưu trong một lượt sau khi biết bestLen.

## 11. Đếm tất cả các đoạn đối xứng không rỗng

Đối với tâm lẻ i với `odd[i]=k`, có đúng k đoạn đối xứng lẻ khác nhau ở tâm i, lần lượt có độ dài:

\[
1,3,5,\ldots,2k-1.
\]

Đối với tâm chẵn tại khe i với `even[i]=k`, có đúng k đoạn đối xứng chẵn khác nhau ở tâm đó, độ dài:

\[
2,4,6,\ldots,2k.
\]

Vì **mỗi đoạn đối xứng không rỗng có đúng một tâm và một bán kính**, cộng các giá trị bán kính cho số lần xuất hiện:

\[
\boxed{
total=\sum_{i=0}^{n-1}odd[i]
+\sum_{i=0}^{n-1}even[i].
}
\]

Đây là số **đoạn theo vị trí [L,R)**, không phải số **nội dung chuỗi phân biệt**.

### Ví dụ "aaaa"

~~~text
odd sum  = 1+2+2+1 = 6
even sum = 0+1+2+1 = 4
total    = 10
~~~

Thực tế `"aaaa"` có:

- 4 đoạn dài 1;
- 3 đoạn dài 2;
- 2 đoạn dài 3;
- 1 đoạn dài 4.

Tổng = 4+3+2+1=10. Nhưng **nội dung khác nhau** chỉ là `"a"`, `"aa"`, `"aaa"`, `"aaaa"` — **4 nội dung**, không phải 10.

### Tại sao nên dùng long ở Java?

Số đoạn con không rỗng của chuỗi dài n là:

\[
\frac{n(n+1)}2.
\]

Nếu mọi ký tự giống nhau, tất cả đều là đoạn đối xứng và total đạt cận trên này. Khi n khoảng 100.000, tổng vượt giới hạn `int` 32-bit; vì vậy mã dùng `long` cho tổng số lần xuất hiện, dù từng bán kính vẫn dùng `int`.

Với kiểu `String` của Java và n giới hạn bởi mảng, tổng này nằm trong miền `long`, nhưng thực tế bộ nhớ sẽ giới hạn n trước khi gần tới giới hạn kiểu.

## 12. Trả lời truy vấn đoạn [L,R) trong O(1)

Giả sử đã tính xong odd và even. Với một truy vấn `S[L,R)`, đặt:

\[
len=R-L.
\]

Nếu len=0 hoặc len=1, theo quy ước bài, đoạn đối xứng ngay lập tức.

Nếu len lẻ:

\[
center=L+\lfloor len/2\rfloor.
\]

Đoạn có bán kính \((len+1)/2\). Vì vậy:

\[
\boxed{isPalindrome(L,R)
\iff odd[center]\ge (len+1)/2}.
\]

Nếu len chẵn:

\[
center=L+len/2
\]

là **chỉ số ký tự ngay sau khe tâm**; cần bán kính len/2:

\[
\boxed{isPalindrome(L,R)
\iff even[center]\ge len/2}.
\]

Ví dụ S=`"abacaba"`:

~~~text
[0,7): "abacaba" -> true
[1,6): "bacab"   -> true
[0,4): "abac"    -> false
[0,0): ""        -> true (quy ước truy vấn)
~~~

Với S=`"abba"`:

~~~text
[0,4): "abba" -> true, even[2] = 2 >= 2
[1,3): "bb"   -> true, even[2] = 2 >= 1
[0,3): "abb"  -> false
~~~

**Không trừ 1** khỏi `len/2` khi lấy tâm chẵn. Khe cần kiểm chính là giữa các ký tự `center-1` và `center`.

### Cần kiểm tra ranh giới truy vấn

Hợp lệ khi `0<=L<=R<=n`. Nếu L âm, R lớn hơn n, hoặc L>R, đây là lỗi hợp đồng; chương trình ném `IllegalArgumentException`.

Truy vấn O(1) là sau tiền xử lý, không kể chi phí đưa mảng từ storage vào bộ nhớ. Nếu chỉ có một truy vấn đơn lẻ, dùng hai con trỏ trực tiếp thường đơn giản hơn.

## 13. Java 17+: triển khai Manacher đầy đủ

Chương trình **ManacherPalindromeDemo.java** sau thực hiện:

1. Tính `odd[]` và `even[]` bằng hai lượt Manacher O(n).
2. Xác định đoạn dài nhất, có quy tắc **hòa thì chọn start nhỏ hơn**.
3. Tính tổng số đoạn đối xứng **không rỗng** bằng `long`.
4. Trả lời `isPalindrome(from,toExclusive)` O(1).
5. Liệt kê các vị trí bắt đầu của **đoạn đối xứng có độ dài xác định** bằng `startsOfLength(length)`.
6. Chạy ví dụ gồm chuỗi rỗng, tâm lẻ, tâm chẵn, ký tự lặp, nhiều đoạn cùng độ dài và Unicode theo **đơn vị UTF-16**.
7. Kiểm tra độc lập từng đoạn trên các mẫu nhỏ bằng hai con trỏ để phát hiện lỗi thuật toán.

**Mã chạy độc lập trên Java 17 trở lên:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class ManacherPalindromeDemo {
    record Result(
        String text,
        int[] odd,
        int[] even,
        long totalOccurrences,
        int longestStart,
        int longestLength
    ) {
        String longest() {
            return text.substring(
                longestStart, longestStart + longestLength
            );
        }

        // Query a half-open UTF-16 interval [from, toExclusive).
        boolean isPalindrome(int from, int toExclusive) {
            int n = text.length();
            if (from < 0 || from > toExclusive
                    || toExclusive > n) {
                throw new IllegalArgumentException(
                    "invalid substring range"
                );
            }
            int len = toExclusive - from;
            if (len <= 1) {
                return true;
            }

            if ((len & 1) != 0) {
                int center = from + len / 2;
                return odd[center] >= len / 2 + 1;
            }

            int center = from + len / 2; // Gap BEFORE center.
            return even[center] >= len / 2;
        }

        // Enumerate nonempty palindromic windows of one length.
        List<Integer> startsOfLength(int length) {
            if (length <= 0 || length > text.length()) {
                return List.of();
            }

            List<Integer> result = new ArrayList<>();
            for (int start = 0; start <= text.length() - length;
                    start++) {
                if (isPalindrome(start, start + length)) {
                    result.add(start);
                }
            }
            return List.copyOf(result);
        }
    }

    static Result analyze(String text) {
        Objects.requireNonNull(text, "text");
        int n = text.length();
        int[] odd = new int[n];
        int[] even = new int[n];

        // Odd-length palindromes, center at character i.
        int left = 0;
        int right = -1;
        for (int i = 0; i < n; i++) {
            int k;
            if (i > right) {
                k = 1;
            } else {
                int mirror = left + (right - i);
                k = Math.min(odd[mirror], right - i + 1);
            }

            while (i - k >= 0 && i + k < n
                    && text.charAt(i - k) == text.charAt(i + k)) {
                k++;
            }

            odd[i] = k;
            if (i + k - 1 > right) {
                left = i - k + 1;
                right = i + k - 1;
            }
        }

        // Even-length palindromes, center in gap before i.
        left = 0;
        right = -1;
        for (int i = 0; i < n; i++) {
            int k;
            if (i > right) {
                k = 0;
            } else {
                int mirror = left + (right - i) + 1;
                k = Math.min(even[mirror], right - i + 1);
            }

            while (i - k - 1 >= 0 && i + k < n
                    && text.charAt(i - k - 1)
                       == text.charAt(i + k)) {
                k++;
            }

            even[i] = k;
            if (i + k - 1 > right) {
                left = i - k;
                right = i + k - 1;
            }
        }

        long total = 0L;
        int bestStart = 0;
        int bestLength = 0;

        for (int i = 0; i < n; i++) {
            total += (long) odd[i] + even[i];

            int oddLength = 2 * odd[i] - 1;
            int oddStart = i - odd[i] + 1;
            if (oddLength > bestLength
                    || (oddLength == bestLength
                        && oddStart < bestStart)) {
                bestLength = oddLength;
                bestStart = oddStart;
            }

            int evenLength = 2 * even[i];
            int evenStart = i - even[i];
            if (evenLength > 0
                    && (evenLength > bestLength
                        || (evenLength == bestLength
                            && evenStart < bestStart))) {
                bestLength = evenLength;
                bestStart = evenStart;
            }
        }

        return new Result(
            text, odd, even, total, bestStart, bestLength
        );
    }

    static boolean brutePalindrome(
        String text, int from, int toExclusive
    ) {
        int left = from;
        int right = toExclusive - 1;
        while (left < right) {
            if (text.charAt(left) != text.charAt(right)) {
                return false;
            }
            left++;
            right--;
        }
        return true;
    }

    // Independent O(n^3) oracle for small strings only.
    static void verifyWithBrute(String text) {
        Result r = analyze(text);
        long count = 0;
        int bestStart = 0;
        int bestLength = 0;

        for (int from = 0; from <= text.length(); from++) {
            for (int end = from; end <= text.length(); end++) {
                boolean expected = brutePalindrome(text, from, end);
                if (r.isPalindrome(from, end) != expected) {
                    throw new AssertionError(
                        "range mismatch at " + from + ":" + end
                    );
                }

                int len = end - from;
                if (len > 0 && expected) {
                    count++;
                    if (len > bestLength
                            || (len == bestLength
                                && from < bestStart)) {
                        bestLength = len;
                        bestStart = from;
                    }
                }
            }
        }

        if (r.totalOccurrences() != count
                || r.longestStart() != bestStart
                || r.longestLength() != bestLength) {
            throw new AssertionError(
                "count or longest palindrome mismatch"
            );
        }
    }

    static void show(String text) {
        Result r = analyze(text);
        System.out.println(
            "text=\"" + text + "\" -> longest=\""
            + r.longest() + "\", start=" + r.longestStart()
            + ", length=" + r.longestLength()
            + ", total=" + r.totalOccurrences()
        );
        System.out.println("  odd=" + Arrays.toString(r.odd()));
        System.out.println("  even=" + Arrays.toString(r.even()));
    }

    public static void main(String[] args) {
        String[] samples = {
            "abacaba", "abba", "aaaa", "banana",
            "babad", "cbbd", "", "a😀a"
        };
        for (String s : samples) {
            show(s);
            verifyWithBrute(s);
        }
        System.out.println("Brute-force checks: PASS");

        Result odd = analyze("abacaba");
        System.out.println("abacaba [0,7): "
            + odd.isPalindrome(0, 7));
        System.out.println("abacaba [1,6): "
            + odd.isPalindrome(1, 6));
        System.out.println("abacaba [0,4): "
            + odd.isPalindrome(0, 4));
        System.out.println("abacaba length-3 starts: "
            + odd.startsOfLength(3));

        Result even = analyze("abba");
        System.out.println("abba [0,4): "
            + even.isPalindrome(0, 4));
        System.out.println("abba [0,3): "
            + even.isPalindrome(0, 3));

        Result empty = analyze("");
        System.out.println("empty [0,0): "
            + empty.isPalindrome(0, 0));

        System.out.println("ten a's total: "
            + analyze("a".repeat(10)).totalOccurrences());

        try {
            odd.isPalindrome(-1, 2);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid range rejected: "
                + e.getMessage());
        }
    }
}
~~~

**Lệnh biên dịch và chạy** (JDK 17 trở lên, mã nguồn UTF-8):

~~~bash
javac -encoding UTF-8 ManacherPalindromeDemo.java
java ManacherPalindromeDemo
~~~

**Stdout dự kiến chính xác** với thứ tự và quy tắc tie-break của mã:

~~~text
text="abacaba" -> longest="abacaba", start=0, length=7, total=12
  odd=[1, 2, 1, 4, 1, 2, 1]
  even=[0, 0, 0, 0, 0, 0, 0]
text="abba" -> longest="abba", start=0, length=4, total=6
  odd=[1, 1, 1, 1]
  even=[0, 0, 2, 0]
text="aaaa" -> longest="aaaa", start=0, length=4, total=10
  odd=[1, 2, 2, 1]
  even=[0, 1, 2, 1]
text="banana" -> longest="anana", start=1, length=5, total=10
  odd=[1, 1, 2, 3, 2, 1]
  even=[0, 0, 0, 0, 0, 0]
text="babad" -> longest="bab", start=0, length=3, total=7
  odd=[1, 2, 2, 1, 1]
  even=[0, 0, 0, 0, 0]
text="cbbd" -> longest="bb", start=1, length=2, total=5
  odd=[1, 1, 1, 1]
  even=[0, 0, 1, 0]
text="" -> longest="", start=0, length=0, total=0
  odd=[]
  even=[]
text="a😀a" -> longest="a", start=0, length=1, total=4
  odd=[1, 1, 1, 1]
  even=[0, 0, 0, 0]
Brute-force checks: PASS
abacaba [0,7): true
abacaba [1,6): true
abacaba [0,4): false
abacaba length-3 starts: [0, 2, 4]
abba [0,4): true
abba [0,3): false
empty [0,0): true
ten a's total: 55
Invalid range rejected: invalid substring range
~~~

### Phân tích cách hoạt động của chương trình

**`analyze`** chạy hai lượt Manacher độc lập. Lượt lẻ giữ vùng `[left,right]` và dùng `mirror=left+(right-i)`; lượt chẵn **reset left/right về 0/-1** rồi dùng `mirror=left+(right-i)+1`.

**Cặp `while`** của hai lượt khác nhau: lẻ so `i-k` và `i+k`; chẵn so `i-k-1` và `i+k`. Chỉ cần sai dấu `-1` là `"abba"` hoặc `"aaaa"` sẽ ra bán kính sai.

**`totalOccurrences`** dùng `long` và cộng bán kính tại từng tâm: một đoạn xuất hiện ở hai vị trí được tính **hai lần**.

**`longest`** lấy substring theo `longestStart,longestLength` sau khi xét cả hai kiểu tâm, với tie-break đầu trái nhỏ nhất.

**`isPalindrome`** chỉ truy cập **một giá trị odd hoặc even**, nên O(1). Nó từ chối khoảng sai; riêng đoạn rỗng và đoạn một ký tự trả true.

**`startsOfLength`** quét mọi vị trí hợp lệ để liệt kê các đoạn đối xứng có đúng độ dài yêu cầu, dùng truy vấn O(1) tại mỗi vị trí. Thời gian O(n), bộ nhớ O(k) cho k vị trí kết quả. Với length≤0, mã trả danh sách rỗng vì chỉ liệt kê **các đoạn không rỗng**.

**`verifyWithBrute`** là oracle độc lập, dùng hai con trỏ trực tiếp cho từng khoảng [from,end). Mã này chỉ nên chạy cho **chuỗi nhỏ**; nếu chạy trên văn bản lớn, kiểm hết mọi khoảng sẽ có chi phí O(n³), làm mất lợi ích tuyến tính của Manacher.

**API record và mảng:** record `Result` trong demo chứa `int[]` có thể truy cập qua accessor. Nếu xây API công khai yêu cầu **bất biến tuyệt đối**, cần tạo bản sao phòng vệ cho hai mảng khi xây/trả kết quả; demo không làm để tránh che khuất trọng tâm thuật toán.

## 14. Unicode và đơn vị chỉ số: lưu ý đặc biệt trong Java

Mã Java dùng `String.length()` và `String.charAt(i)`, tức xét **đơn vị UTF-16** (*UTF-16 code unit*), không nhất thiết là một **Unicode code point** hay một ký tự hiển thị.

Ví dụ `"a😀a"` có **3 Unicode code points** (`a`, emoji, `a`) nhưng **4 UTF-16 code units**, vì emoji ngoài BMP chiếm **hai đơn vị**. Nếu xét theo code point, chuỗi này đối xứng. Nhưng theo thứ tự code units:

~~~text
a, high-surrogate, low-surrogate, a
~~~

nó **không đối xứng**, vì hai đơn vị surrogate ở giữa không bằng nhau. Bởi vậy mã `charAt` minh họa trả **đoạn dài nhất "a"** theo UTF-16, không trả toàn bộ `"a😀a"`.

Điều này là **khác biệt ngữ nghĩa**, không phải lỗi vòng lặp Manacher. Thậm chí một đoạn đối xứng theo code units có thể cắt giữa cặp surrogate và tạo một `String` không biểu diễn nguyên vẹn ký tự Unicode.

### Muốn đếm theo Unicode code point

Chuyển chuỗi thành `int[] symbols=text.codePoints().toArray()`, rồi áp dụng **chính xác cùng công thức Manacher** nhưng so sánh `symbols[left]==symbols[right]`. Khi đó:

- n là số code points;
- odd/even và start/length tính theo **code-point index**;
- muốn lấy `substring` từ Java `String` gốc, cần ánh xạ vị trí code point sang offset UTF-16 (ví dụ `offsetByCodePoints` hoặc bảng prefix offsets).

**Code point cũng chưa chắc là một ký tự mắt người thấy.** Một grapheme cluster có thể gồm chữ cái, dấu kết hợp hoặc chuỗi emoji với ZWJ. Nếu yêu cầu đối xứng theo **grapheme cluster**, phải phân đoạn thành những đơn vị grapheme trước khi chạy thuật toán.

### So sánh có chuẩn hóa

Ký tự `é` trong dạng ghép sẵn có thể khác về code points so với `e` cộng dấu kết hợp; tiếng Việt cũng có các dạng mã hóa tương đương. Manacher chỉ kiểm tra **bằng nhau theo đơn vị dữ liệu được đưa vào**, không tự chuẩn hóa văn bản hoặc bỏ qua hoa/thường.

Nếu bài muốn coi các dạng Unicode tương đương là một, phải **chuẩn hóa nhất quán** trước khi tính bán kính. Nếu cần trả offset về văn bản gốc, phải bảo toàn **ánh xạ chỉ số** qua bước chuẩn hóa, bởi chiều dài có thể thay đổi.

## 15. Các trường hợp biên quan trọng

| Trường hợp | Hành vi đúng |
|---|---|
| S rỗng | odd/even rỗng, total=0, longest="" |
| S dài 1 | odd=[1], even=[0], total=1 |
| S gồm các ký tự khác nhau, không palindrome dài hơn 1 | odd toàn 1, even toàn 0 |
| S="abba" | even[2]=2, longest="abba" |
| S="aba" | odd[1]=2, longest="aba" |
| S="aaaa" | odd=[1,2,2,1], even=[0,1,2,1], total=10 |
| S="babad" | Có hai lời giải dài 3; chọn start nhỏ nhất => "bab" |
| Mọi ký tự giống nhau | Mọi đoạn không rỗng đối xứng, total=n(n+1)/2 |
| Độ dài chẵn | Tâm là khe **trước i**, không phải ký tự i |
| Truy vấn [L,R) với L=R | true theo quy ước kiểm đoạn rỗng |
| Truy vấn L<0 hoặc R>n hoặc L>R | Ném `IllegalArgumentException` |
| `startsOfLength(0)` | Trả danh sách rỗng theo API liệt kê đoạn không rỗng |
| Cần số nội dung palindrome khác nhau | Tổng odd+even **không phải** kết quả cần |
| Unicode emoji | Chỉ số đang là UTF-16, không phải grapheme |
| Cần xử lý chuỗi thay đổi liên tục | Manacher tĩnh phải tính lại; cần mô hình động khác |
| Có rất nhiều truy vấn palindrome | Tiền xử lý O(n), mỗi truy vấn O(1) |
| Chỉ có một truy vấn đoạn nhỏ | Hai con trỏ trực tiếp có thể đơn giản hơn |

### Vấn đề đếm chuỗi phân biệt

S=`"aaaa"` có 10 đoạn đối xứng **theo vị trí**, nhưng chỉ có 4 **nội dung** đối xứng phân biệt. Nếu bài yêu cầu `distinct palindromic substrings`, không được dùng \(\sum odd+\sum even\).

Một cấu trúc như **palindromic tree (eertree)** có thể hỗ trợ các bài đếm đoạn đối xứng phân biệt. Manacher mạnh ở **bán kính quanh mọi tâm**, kiểm tra đoạn và đếm số lần xuất hiện.

### Manacher không phải công cụ cho mọi câu hỏi palindrome

Manacher được thiết kế cho **một chuỗi tĩnh**. Nếu mỗi truy vấn thay đổi ký tự ở vị trí bất kỳ rồi hỏi lại tính đối xứng, các mảng odd/even có thể bị ảnh hưởng trên phạm vi rộng; tính lại O(n) sau mỗi sửa không nhất thiết hiệu quả.

Nếu cần truy vấn palindrome trên chuỗi động hoặc so sánh đoạn với nhiều bản cập nhật, có thể cân nhắc hashing hai chiều, segment tree lưu hash hoặc cấu trúc dữ liệu khác, với phân tích rủi ro va chạm và cập nhật riêng. Đây là một bài toán khác với Manacher tĩnh.

## 16. Những lỗi thường gặp khi cài Manacher

1. **Chỉ xử lý tâm lẻ**, làm mất `"abba"`, `"noon"`, `"aabbaa"`.
2. **Khởi tạo odd k=0** nhưng vẫn dùng công thức độ dài `2*k-1` của bán kính bao gồm tâm.
3. **Khởi tạo even k=1**, mặc định hai ký tự quanh khe luôn khớp.
4. **Dùng mirror odd cho even**, thiếu `+1` ở `left+right-i+1`.
5. **Dùng cặp so sánh odd cho even**, so `i-k` thay vì `i-k-1`.
6. **Sai điều kiện ranh giới**, truy cập `charAt(-1)` hoặc `charAt(n)`.
7. **Không giới hạn bán kính từ mirror bởi biên phải**, sao chép palindrome vượt ngoài vùng đã được chứng minh.
8. **Quên cập nhật vùng [left,right] khi mở rộng xa hơn**, mất tính chất tuyến tính hoặc sai bán kính sau.
9. **Nhầm biên bao gồm với biên loại trừ**, làm độ dài bị lệch một đơn vị.
10. **Không reset left/right giữa hai lượt odd/even**, dùng sai đoạn đối xứng của kiểu tâm trước.
11. **Nhầm odd[i] với độ dài palindrome**, trong khi độ dài lẻ là `2*odd[i]-1`.
12. **Nhầm even[i] với độ dài palindrome**, trong khi độ dài chẵn là `2*even[i]`.
13. **Đếm số palindrome bằng `sum(2*odd-1)`**, trong khi số đoạn lẻ quanh tâm chỉ là `odd[i]`.
14. **Quên cộng even vào tổng**, gây thiếu đoạn độ dài chẵn.
15. **Dùng int cho tổng số đoạn** khi n lớn, có thể tràn 32-bit.
16. **Không kiểm đoạn rỗng/truy vấn sai phạm vi**, dễ ném lỗi ngoài dự tính.
17. **Không xử lý quy tắc tie-break**, khiến đáp án không đúng yêu cầu “đoạn sớm nhất”.
18. **Coi mảng odd/even tính theo ký tự Unicode nhìn thấy**, trong khi Java charAt dùng code unit.
19. **Chuẩn hóa chuỗi nhưng giữ chỉ số cũ**, trả substring sai.
20. **Coi tổng bán kính là số palindrome phân biệt**, trong khi trùng nội dung ở hai vị trí được tính hai lần.
21. **Tuyên bố O(n) nhưng mở rộng lại từ k=0 ở mỗi tâm**, thực tế trở thành O(n²).
22. **Dùng substring trong mỗi bước mở rộng**, phát sinh chi phí sao chép/so sánh không cần thiết.
23. **Chỉ test ví dụ đối xứng lẻ**, bỏ sót những lỗi đặc trưng của even.
24. **Không thử chuỗi toàn một ký tự**, trường hợp dễ làm bộc lộ lỗi bán kính và đếm.
25. **Không thử chuỗi rỗng hoặc một ký tự**, làm sai quy ước kết quả.
26. **Không đối chiếu với oracle vét cạn độc lập**, khó phát hiện việc hai công thức sai nhưng cho một số ví dụ đúng.
27. **Không kiểm mọi [L,R)**, chỉ kiểm đoạn dài nhất, nên lỗi truy vấn O(1) vẫn ẩn.
28. **Trả về mảng bán kính rồi để người dùng sửa dữ liệu tùy ý**, phá tính đúng của các truy vấn về sau.
29. **Áp dụng kết quả Manacher cũ sau khi thay đổi nội dung S**, khi bán kính không còn phản ánh chuỗi hiện tại.
30. **Đếm đoạn rỗng như một lần xuất hiện khi tổng odd+even**, trong khi công thức này cố ý chỉ đếm đoạn không rỗng.

## 17. Kiểm thử độc lập với thuật toán hai con trỏ

Một cách QA tốt là viết oracle duyệt **mọi đoạn [L,R)** của một chuỗi nhỏ, kiểm trực tiếp hai đầu và đếm số đoạn đối xứng không rỗng. Cách làm này không sử dụng mirror, bán kính hay invariant của Manacher nên có khả năng phát hiện lỗi công thức.

### Oracle kiểm palindrome

~~~text
brutePalindrome(S,L,R):
    i=L
    j=R-1
    while i<j:
        if S[i]!=S[j]: return false
        i++, j--
    return true
~~~

### Oracle kiểm bán kính

Với tâm lẻ i, thử k=1,2,... cho tới khi đoạn `[i-k+1,i+k)` không còn hợp lệ hoặc không đối xứng; bán kính lớn nhất là odd[i].

Với tâm chẵn khe i, thử k=0,1,2,... cho tới khi đoạn `[i-k,i+k)` không hợp lệ hoặc không đối xứng; bán kính lớn nhất là even[i].

### Oracle kiểm tổng và đoạn dài nhất

Duyệt mọi cặp:

\[
0\le L<R\le n.
\]

Nếu đoạn [L,R) đối xứng, tăng bộ đếm và cập nhật đoạn dài nhất; hòa thì chọn L nhỏ hơn. Kết quả phải khớp:

\[
\sum_i odd[i]+\sum_i even[i]
\]

và `longestStart/longestLength` của Manacher.

### Bộ test tiêu biểu

| S | Longest (start, length) | Tổng số lần xuất hiện |
|---|---|---:|
| `""` | `""` (0,0) | 0 |
| `"a"` | `"a"` (0,1) | 1 |
| `"abc"` | `"a"` (0,1) | 3 |
| `"abacaba"` | `"abacaba"` (0,7) | 12 |
| `"abba"` | `"abba"` (0,4) | 6 |
| `"aaaa"` | `"aaaa"` (0,4) | 10 |
| `"banana"` | `"anana"` (1,5) | 10 |
| `"babad"` | `"bab"` (0,3) | 7 |
| `"cbbd"` | `"bb"` (1,2) | 5 |
| `"aabbaa"` | `"aabbaa"` (0,6) | 11 |

Nên sinh hàng trăm chuỗi ngẫu nhiên ngắn trên bảng chữ cái nhỏ, kiểm:

- Mọi giá trị `odd[i]` và `even[i]` bằng bán kính oracle.
- Tất cả truy vấn [L,R), **kể cả đoạn rỗng**, trả đúng boolean.
- Tổng số đoạn và đoạn dài nhất bằng oracle.
- Độ dài trả về không vượt n và khôi phục đúng chuỗi con theo phạm vi.
- Các trường hợp `"a"*n` có tổng đúng `n*(n+1)/2`.
- Unicode code units được so sánh nhất quán với hợp đồng đang áp dụng.

Với chuỗi dài, không chạy oracle O(n³); chỉ dùng test mẫu và công thức tổng/cận. Chính thuật toán Manacher mới dành cho n lớn.

## 18. Câu hỏi tự luyện

**Bài 1 — Khái niệm.** Đoạn `"aba"` có tâm ở đâu?

*Đáp án:* Tâm lẻ ở ký tự `b`; nếu đánh chỉ số 0, tâm là i=1.

**Bài 2 — Tâm chẵn.** Trong `"abba"`, tâm của đoạn dài 4 nằm ở đâu?

*Đáp án:* Khe giữa hai ký tự `b`, tức khe ngay trước i=2.

**Bài 3 — Bán kính lẻ.** Nếu odd[5]=4, độ dài đoạn lẻ lớn nhất ở tâm 5 bằng bao nhiêu?

*Đáp án:* `2*4-1=7`.

**Bài 4 — Bán kính chẵn.** Nếu even[5]=4, độ dài đoạn chẵn lớn nhất ở khe trước 5 bằng bao nhiêu?

*Đáp án:* `2*4=8`.

**Bài 5 — Biên lẻ.** odd[5]=4 thì hai đầu nửa mở là gì?

*Đáp án:* `[5-4+1,5+4)=[2,9)`.

**Bài 6 — Biên chẵn.** even[5]=4 thì hai đầu nửa mở là gì?

*Đáp án:* `[5-4,5+4)=[1,9)`.

**Bài 7 — Mảng cho "abba".** odd và even bằng gì?

*Đáp án:* odd=[1,1,1,1], even=[0,0,2,0].

**Bài 8 — Mảng cho "aaaa".** odd và even bằng gì?

*Đáp án:* odd=[1,2,2,1], even=[0,1,2,1].

**Bài 9 — Tổng.** Với odd=[1,2,2,1], even=[0,1,2,1], có bao nhiêu lần xuất hiện đoạn đối xứng không rỗng?

*Đáp án:* `6+4=10`.

**Bài 10 — Phản chiếu odd.** Khi đang giữ [left,right] và xét tâm i bên trong, tâm đối xứng mirror là gì?

*Đáp án:* `left+right-i`.

**Bài 11 — Phản chiếu even.** Mirror cho tâm chẵn khe trước i là gì?

*Đáp án:* `left+right-i+1`.

**Bài 12 — Vì sao lấy min với right-i+1?**

*Đáp án:* Để chỉ sao chép phần đã được bảo đảm nằm trong vùng đối xứng cũ, không suy diễn vượt biên phải.

**Bài 13 — Truy vấn.** S=`"abba"`, hỏi [0,4) có đối xứng không. Kiểm mảng nào?

*Đáp án:* even[2]>=2, đúng vì even[2]=2.

**Bài 14 — Truy vấn lẻ.** S=`"abacaba"`, hỏi [1,6) có đối xứng không?

*Đáp án:* Có. Độ dài 5, tâm i=3, odd[3]=4≥3.

**Bài 15 — Longest tie.** Với `"babad"`, nếu cần đoạn dài nhất bắt đầu sớm nhất thì chọn gì?

*Đáp án:* `"bab"` bắt đầu ở 0; `"aba"` cũng dài 3 nhưng bắt đầu ở 1.

**Bài 16 — Chỉ đếm palindrome phân biệt.** Tổng odd+even có phải số nội dung palindrome khác nhau?

*Đáp án:* Không. Nó đếm **mọi lần xuất hiện theo vị trí**. Với `"aaaa"`, total=10 nhưng nội dung khác nhau chỉ 4.

**Bài 17 — Trường hợp rỗng.** Manacher trên chuỗi rỗng trả đoạn dài nhất và tổng số đoạn như thế nào?

*Đáp án:* `longest=""`, length=0, total=0; truy vấn [0,0) true theo quy ước.

**Bài 18 — Unicode.** Vì sao `"a😀a"` không đối xứng theo mã Java dùng `charAt`, dù đối xứng theo Unicode code points?

*Đáp án:* Emoji chiếm **hai UTF-16 code units** theo thứ tự high/low surrogate, không đối xứng khi đảo thứ tự code units. Muốn theo code point, phải chạy trên `int[]` code points.

**Bài 19 — Độ phức tạp.** Vì sao mở rộng quanh tâm trực tiếp có thể O(n²), còn Manacher O(n)?

*Đáp án:* Cách trực tiếp thử lại các cặp đã biết; Manacher phản chiếu bán kính trong vùng palindrome đã ghi và chỉ mở rộng ngoài biên, trong khi biên phải tăng O(n) lần.

**Bài 20 — Tính động.** Sau khi sửa một ký tự trong S, có thể tin mảng odd/even cũ không?

*Đáp án:* Không. Thay đổi ký tự có thể làm nhiều đoạn đối xứng biến mất/xuất hiện; cần tính lại hoặc dùng cấu trúc dữ liệu cho chuỗi động.

**Tổng kết:** Manacher xử lý toàn bộ các tâm đối xứng bằng **hai mảng bán kính odd/even** trong **O(n) thời gian và O(n) bộ nhớ**. Với tâm lẻ, bán kính k cho đoạn `[i-k+1,i+k)` dài `2k-1`; với tâm chẵn là khe trước i, bán kính k cho `[i-k,i+k)` dài `2k`. Duy trì vùng đối xứng vươn xa nhất **[left,right]**, dùng **tâm phản chiếu** để khởi tạo bán kính rồi chỉ kiểm tra phần nằm ngoài vùng, tránh công việc lặp lại. Từ odd/even có thể tìm đoạn dài nhất trong O(n), **đếm mọi lần xuất hiện đoạn đối xứng bằng tổng bán kính** và trả lời truy vấn đoạn **[L,R)** trong **O(1)**. Khi cài Java, cần phân biệt tâm lẻ/chẵn, biên nửa mở, cận kiểu `long` cho tổng và **ngữ nghĩa chỉ số UTF-16**; nếu bài yêu cầu code point hoặc grapheme, phải đổi đơn vị dữ liệu trước khi áp dụng thuật toán.
