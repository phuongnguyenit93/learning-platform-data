# Boyer–Moore và các quy tắc dịch mẫu

**Boyer–Moore** là một thuật toán **tìm kiếm chuỗi con**: cho văn bản T dài n và mẫu P dài m, tìm những vị trí trong T mà đoạn liên tiếp bắt đầu ở đó bằng đúng P. Điểm khác biệt với so khớp ngây thơ là thuật toán thường **so mẫu từ phải sang trái**, rồi sau khi phát hiện khác biệt sẽ **dịch mẫu nhiều hơn một vị trí** nhờ thông tin đã tiền xử lý. Hai thành phần nổi tiếng nhất là **quy tắc ký tự xấu (bad-character rule)** và **quy tắc hậu tố tốt (good-suffix rule)**.

Bài thuộc nhóm **Tìm kiếm chuỗi** trong Computer Science Algorithms, tập trung trực tiếp vào **“Boyer–Moore và các quy tắc dịch mẫu”**. Nội dung phân biệt sự dịch mẫu sau mismatch và sau full match, xây bảng last occurrence, giải thích hậu tố đã khớp và tiền xử lý **strong good suffix**, chứng minh tại sao không bỏ qua vị trí khớp thật, xử lý các kết quả chồng lấn, đánh giá chi phí, và so sánh với KMP, Rabin–Karp, Horspool. Mã Java 17+ thực thi cả hai quy tắc, dùng chỉ số UTF-16 như String của Java, và đã so kết quả với phép đối chứng ngây thơ trên **129.921 cặp text/pattern vét cạn** cùng **3.000 cặp sinh ngẫu nhiên có seed**.

## 1. Phát biểu bài toán và ký hiệu

Văn bản T có n ký tự theo đơn vị được chọn, mẫu P có m ký tự. Ta cần tìm tất cả vị trí s thỏa:

~~~text
0 <= s <= n-m
T[s + j] == P[j] với mọi j = 0..m-1.
~~~

Giả sử đánh số vị trí từ **0**. Nếu không có kết quả, trả danh sách rỗng. Nếu có nhiều kết quả, có thể trả **tất cả vị trí**, kể cả các kết quả **chồng lấn**.

Ví dụ:

~~~text
T = "ABABA"
P = "ABA"
m = 3

Vị trí khớp:
s=0: T[0..3) = "ABA"
s=2: T[2..5) = "ABA"

Kết quả: [0,2].
~~~

Chương trình cuối bài dùng **độ dài và chỉ số String của Java**, tức số đơn vị UTF-16, không phải số grapheme người đọc nhìn thấy. Vì vậy khi mẫu chứa emoji gồm hai đơn vị UTF-16, chỉ số khớp cũng là **offset UTF-16**, đúng với cách String.indexOf báo vị trí.

## 2. Vì sao cách so khớp ngây thơ có thể chậm?

Thuật toán ngây thơ thử mọi vị trí bắt đầu s từ 0 tới n−m, so các ký tự của mẫu với đoạn văn bản tương ứng. Nếu mismatch, thường dịch s thêm đúng 1.

~~~text
for s = 0..n-m:
    kiểm tra T[s..s+m) có bằng P không
    nếu đúng: ghi s
~~~

Trong trường hợp xấu, mỗi vị trí thử có thể so gần m ký tự trước khi phát hiện mismatch, khiến tổng số phép so sánh tới **O(nm)**.

Một ví dụ dễ gây lặp:

~~~text
T = "AAAAAAAAAAAAAB"
P = "AAAAAB"
~~~

Ở nhiều vị trí, hàng loạt ký tự A khớp rồi mới gặp khác biệt gần cuối. Nếu không tận dụng thông tin “vừa so được gì” hoặc “mẫu có cấu trúc nào”, ta so lặp nhiều đoạn ký tự giống nhau.

Boyer–Moore không nhất thiết thắng ở mọi văn bản ngắn, nhưng thường có lợi khi mẫu đủ dài, bảng tiền xử lý được tái sử dụng, và các mismatch cho phép **bỏ qua nhiều vị trí bắt đầu không thể khớp**.

## 3. Cửa sổ căn chỉnh và so từ phải sang trái

Boyer–Moore đặt P bên dưới một đoạn dài m của T, ở vị trí căn chỉnh s. Sau đó so:

~~~text
P[m-1] với T[s+m-1],
P[m-2] với T[s+m-2],
...
P[0]   với T[s].
~~~

Nếu toàn bộ m ký tự bằng nhau, ta tìm được một occurrence tại s. Nếu mismatch tại chỉ số mẫu j, ta biết:

~~~text
P[j] != T[s+j]

và các ký tự ở bên phải đã khớp:
P[j+1..m) == T[s+j+1..s+m).
~~~

Thông tin **ký tự vừa gây mismatch** phục vụ quy tắc bad-character; thông tin **hậu tố mẫu đã khớp** phục vụ good-suffix. Hai quy tắc có thể đề xuất hai khoảng dịch khác nhau. Bản cài đặt sẽ chọn khoảng dịch **lớn hơn**, nhưng không nhỏ hơn 1, vì mỗi quy tắc được thiết kế để không bỏ qua một vị trí khớp hợp lệ.

## 4. Quy tắc ký tự xấu: tìm lần xuất hiện cuối

Tạo bảng **last[c]** là vị trí **cuối cùng (bên phải nhất)** mà ký tự c xuất hiện trong P, hoặc −1 nếu c không có trong P.

~~~text
P = "EXAMPLE"
index: 0 1 2 3 4 5 6
char : E X A M P L E

last['E'] = 6
last['X'] = 1
last['A'] = 2
last['M'] = 3
last['P'] = 4
last['L'] = 5
last['Z'] = -1
~~~

Khi đang căn mẫu ở s và mismatch tại P[j] đối với ký tự văn bản c=T[s+j], ứng viên khoảng dịch là:

~~~text
badShift = j - last[c]
badShift = max(1, badShift).
~~~

Ý tưởng: nếu c có thể xuất hiện trong một lần khớp kế tiếp và còn vị trí tương ứng về bên trái mismatch, ta có thể căn c với một lần xuất hiện phù hợp ở mẫu. Nếu c **không có trong mẫu**, cần dịch đủ xa để c không còn nằm trong vị trí vừa mismatch của mẫu.

Bản cài dùng **vị trí cuối cùng trên toàn mẫu**, không phải chỉ tìm ở tiền tố P[0..j). Nếu last[c]>j, biểu thức có thể âm; ta chặn dưới bằng 1. Điều này có thể kém mạnh hơn bảng last phụ thuộc j nhưng vẫn **an toàn** và rất dễ tiền xử lý.

## 5. Bad-character: ví dụ nhảy ba vị trí

Xét:

~~~text
T = "ZZZABC"
P = "ABC"

s=0:
text:    Z Z Z A B C
pattern: A B C
             ^ mismatch ngay tại j=2
~~~

Tại j=2, P[2]='C' khác T[2]='Z'. Z không xuất hiện trong P nên last['Z']=−1.

~~~text
badShift = j - last['Z']
         = 2 - (-1)
         = 3.
~~~

Vì vậy dịch mẫu từ **s=0 sang s=3**, thay vì thử s=1 và s=2. Tại s=3, P khớp trọn đoạn "ABC".

~~~text
Vị trí tìm được: [3].
Số lần căn chỉnh thực sự kiểm tra: 2.
~~~

Ví dụ này làm rõ lợi ích chủ yếu của Boyer–Moore: **không cần đọc/so những cửa sổ đã được chứng minh không thể khớp**. Tuy nhiên nếu văn bản có nhiều ký tự xuất hiện thường xuyên gần cuối mẫu, bad-character có thể chỉ gợi ý dịch 1.

## 6. Cách xây last occurrence trong Java

Một vòng lặp trên P từ trái sang phải đủ để ghi lại vị trí cuối cùng:

~~~text
last = map từ ký tự -> chỉ số.

for i = 0..m-1:
    last[P[i]] = i.
~~~

Mỗi lần gán ghi đè vị trí trước đó, nên sau vòng lặp last[c] là chỉ số lớn nhất có P[index]=c.

Bản Java dùng **HashMap<Character,Integer>** để không cấp phát một bảng lớn cho toàn bộ 65.536 đơn vị UTF-16 nếu mẫu chỉ chứa vài ký tự. Khi gặp ký tự c chưa xuất hiện trong mẫu:

~~~text
last.getOrDefault(c,-1) = -1.
~~~

Trong mô hình HashMap thông thường, tiền xử lý cần thời gian và bộ nhớ kỳ vọng **O(m)**. Nếu bảng chữ cái nhỏ và đã biết, có thể dùng mảng last[Σ] được khởi tạo −1, chi phí **O(m+Σ)** thời gian và O(Σ) bộ nhớ.

## 7. Quy tắc hậu tố tốt: dùng phần đã khớp

Giả sử quá trình so từ phải sang trái đã khớp một hậu tố không rỗng:

~~~text
P[j+1..m) đã bằng T[s+j+1..s+m),
nhưng P[j] khác T[s+j].
~~~

Gọi S=P[j+1..m) là **good suffix**. Ta không muốn căn mẫu mới ở những vị trí khiến S không thể khớp với đoạn văn bản vừa biết là S. Có hai khả năng hữu ích:

1. Trong P có một **lần xuất hiện khác của S về phía trái**. Ta thử căn lần xuất hiện ấy tới đoạn văn bản đã khớp. Trong phiên bản **strong good suffix**, còn xét ký tự đứng trước lần xuất hiện đó để không chọn một căn chỉnh mà ký tự vừa gây mismatch chắc chắn lại không khớp.
2. Nếu không có lần xuất hiện nguyên S phù hợp, căn **hậu tố dài nhất của S** đồng thời là **tiền tố của P** tới cuối đoạn văn bản đã khớp; phần S còn lại nằm ngoài cửa sổ mẫu mới.

Như vậy quy tắc good-suffix tận dụng **cấu trúc tự lặp của mẫu**, thay vì chỉ dùng ký tự văn bản tại mismatch. Nó có ích ngay cả khi ký tự gây mismatch vốn xuất hiện ở nhiều nơi trong P.

## 8. Border, prefix và suffix là gì?

Một **prefix** của chuỗi là đoạn bắt đầu ở vị trí 0; **suffix** là đoạn kết thúc ở vị trí m−1. **Border** là một chuỗi vừa là prefix vừa là suffix; khi nói **proper border**, border không được bằng toàn bộ chuỗi.

Ví dụ:

~~~text
P = "ABAB"

Các proper border:
"A..."?  "A" không phải suffix của "ABAB".
"AB" là prefix và cũng là suffix.

Longest proper border = "AB", độ dài 2.
~~~

Khi vừa tìm được một full match của P="ABAB", ta có thể dịch mẫu **m−2=2** vị trí để suffix "AB" của lần khớp cũ thẳng hàng với prefix "AB" của lần kế. Điều này giữ lại cơ hội xuất hiện trùng phần:

~~~text
T = "ABABAB"
P = "ABAB"

Khớp tại s=0 và s=2.
~~~

Nếu sau full match luôn dịch đúng m=4, ta **bỏ lỡ** occurrence tại s=2. Ngược lại, nếu mẫu không có proper border, dịch đủ m sau full match vẫn an toàn vì không có cách chồng lấn thành một full match mới.

## 9. Quy tắc good-suffix mạnh (strong good suffix)

Khi mismatch tại j, ta biết phần S=P[j+1..m) khớp. Nếu tìm thấy một bản sao của S nằm trước vị trí j+1 trong mẫu, ứng viên dịch có thể mang phần S ấy trùng với văn bản đã khớp.

Nhưng nếu **ký tự đứng trước bản sao S ấy bằng P[j]**, thì lần căn chỉnh mới sẽ đối chiếu cùng một ký tự mẫu với ký tự văn bản đã biết khác P[j]. Căn chỉnh đó cũng chắc chắn mismatch ngay và có thể **bỏ qua**.

Đây là khác biệt trực giác giữa bản **strong** và bản good-suffix “yếu”: phiên bản mạnh tránh một số căn chỉnh thừa bằng cách xét ký tự đứng trước occurrence của suffix.

Nếu không có bản sao phù hợp, lựa chọn an toàn là căn **một suffix của S trùng prefix của P**. Các giá trị dịch có thể được tiền xử lý thành bảng **shift[0..m]** để lúc tìm kiếm truy cập O(1).

~~~text
Mismatch tại chỉ số j:
    goodShift = shift[j+1].

Khớp toàn bộ mẫu:
    fullMatchShift = shift[0].
~~~

Chỉ số **j+1** là rất quan trọng: hậu tố đã khớp bắt đầu tại vị trí j+1, không phải j. Truy cập shift[j] thay cho shift[j+1] là một lỗi off-by-one dễ làm bỏ qua occurrence.

## 10. Tiền xử lý good-suffix bằng border positions

Bản Java dùng một kỹ thuật phổ biến của **strong good-suffix preprocessing**, gồm hai mảng:

~~~text
border[i] : vị trí bắt đầu border kế tiếp phù hợp
            với suffix bắt đầu tại i, hoặc sentinel m+1.

shift[i]  : khoảng dịch an toàn đã tính cho
            trường hợp hậu tố bắt đầu ở i.
~~~

**Pha 1:** đi từ phải sang trái, xây liên kết border, và khi một border không thể tiếp tục mở rộng vì ký tự không khớp, gán khoảng dịch strong good-suffix vào shift[j] nếu ô đó chưa có giá trị.

~~~text
i = m; j = m+1
border[m] = m+1

while i > 0:
    while j <= m && P[i-1] != P[j-1]:
        if shift[j] == 0:
            shift[j] = j-i
        j = border[j]
    i--
    j--
    border[i] = j
~~~

**Pha 2:** các giá trị shift còn bằng 0 được lấp bằng dịch chuyển theo **proper border** thích hợp, tức khớp suffix của văn bản đã xác nhận với prefix của P.

~~~text
j = border[0]

for k = 0..m:
    if shift[k] == 0:
        shift[k] = j
    if k == j:
        j = border[j]
~~~

Pha 1 tìm cơ hội phù hợp khi có bản sao good suffix khác ở bên trái; pha 2 xử lý trường hợp còn lại và full match. Với m>0, mọi shift[k] cuối cùng là **số nguyên dương**, không có bước dịch 0. Hai pha sử dụng border-chain để tránh so đi so lại suffix từ đầu; tiền xử lý **O(m)** theo phân tích amortized tiêu chuẩn.

## 11. Kết hợp hai quy tắc dịch mẫu

Khi mismatch tại j, sau khi đã so khớp phần P[j+1..m), ta tính:

~~~text
badShift  = j - last[T[s+j]].
goodShift = shift[j+1].

nextShift = max(1, badShift, goodShift).

s = s + nextShift.
~~~

Nếu ký tự T[s+j] chưa xuất hiện trong mẫu, last=-1. Nếu đã khớp toàn bộ P thì **không còn mismatch j** và phải dùng nhánh riêng:

~~~text
Ghi nhận vị trí s.
s = s + shift[0].
~~~

Một lưu ý tinh tế: **badShift và goodShift đều là khoảng dịch an toàn theo điều kiện riêng của chúng**; khi một quy tắc chứng minh không thể có full match ở các vị trí trước bước dịch của nó, chọn bước lớn hơn sẽ không bỏ qua match hợp lệ. Bản Java thêm max với 1 để tránh lặp vô hạn do badShift≤0.

Đừng cộng badShift và goodShift. Cộng hai khoảng dịch **không được chứng minh an toàn** và có thể nhảy qua một occurrence thật. Cũng không được dùng chỉ goodShift khi full match mà mặc định bằng m, vì mẫu tự chồng lấn như "ABA" cần bước dịch ngắn hơn.

## 12. So sánh hành vi với các ví dụ

| Văn bản T | Mẫu P | Vị trí khớp | Lý do đáng chú ý |
| --- | --- | --- | --- |
| HERE IS A SIMPLE EXAMPLE | EXAMPLE | [17] | Trường hợp tìm chuỗi kinh điển |
| ABABA | ABA | [0,2] | Hai occurrence chồng lấn |
| AAAAAA | AAA | [0,1,2,3] | Border dài, dịch 1 sau full match |
| ZZZABC | ABC | [3] | Bad-character cho bước nhảy 3 |
| BANANANA | ANA | [1,3,5] | Nhiều kết quả chồng lấn |
| Chuỗi rỗng | A | [] | Mẫu dài hơn văn bản |
| ab | Mẫu rỗng | [0,1,2] | Quy ước mỗi ranh giới là một kết quả |

Các vị trí là **0-based UTF-16 offsets**. Chương trình in trực tiếp một số ví dụ và kiểm tra những ví dụ còn lại bằng oracle ngây thơ.

**Đặc biệt với mẫu toàn ký tự trùng nhau:** mẫu "AAA" có proper border "AA", nên shift[0]=1. Nếu dùng dịch 3 sau mỗi lần khớp, ta sẽ bỏ sót các match tại s=1,2,3.

## 13. Chứng minh trực giác của bad-character shift

Giả sử tại căn chỉnh s, ký tự văn bản c=T[s+j] khác P[j]. Muốn có một lần khớp hoàn toàn ở căn chỉnh mới s+d, với d>0, nếu vị trí văn bản s+j vẫn nằm trong cửa sổ mẫu mới (tức d≤j), ký tự c phải được mẫu mới đặt vào vị trí j−d.

Vậy nếu P không có c ở bất kỳ vị trí nào phía **trái j** đủ gần, các dịch d nhỏ sẽ không thể đem lại full match. Việc đặt d≥j−last[c] là an toàn với bảng last occurrence toàn mẫu; nếu last[c]>j thì bước biểu thức không dương và ta chỉ dịch 1.

Ví dụ last[c]=−1: với mọi 1≤d≤j, ký tự c vẫn nằm bên dưới một ký tự nào đó của P, nhưng P không có c ở đâu cả; không thể khớp. Vì vậy có thể dịch j+1.

Cơ chế chứng minh không dựa vào việc “ký tự xấu nên nhảy xa” như một mẹo thuộc lòng, mà dựa vào **loại bỏ mọi căn chỉnh không thể thỏa ký tự đã biết**. Các bước lớn hơn cũng không bỏ qua nghiệm vì chúng chỉ vượt qua những điểm bắt đầu vừa được loại trừ.

## 14. Chứng minh trực giác của strong good-suffix shift

Giả sử P[j+1..m) đã khớp với đoạn văn bản bên phải, nhưng tại j có mismatch. Bất cứ căn chỉnh nào dịch ít hơn khoảng do good-suffix chọn mà vẫn định tạo full match sẽ phải **căn một phần của hậu tố vừa biết** với các vị trí trong P.

Nếu căn đủ cả S, phần trùng mẫu cần là một occurrence khác của S ở phía trái. Trong **strong rule**, bản sao có ký tự đứng trước giống P[j] cũng bị loại vì ký tự văn bản tại mismatch đã khác P[j]. Nếu không còn bản sao đầy đủ phù hợp, chỉ có thể giữ một **suffix của S** làm prefix của P tại căn chỉnh mới. Border-chain giúp tìm phần suffix/prefix dài nhất có thể.

Do đó các vị trí căn chỉnh nhỏ hơn goodShift đều mâu thuẫn với **nội dung đã khớp hoặc ký tự mismatch**. Không có match thật nào bị bỏ qua. Sau full match, cùng lập luận dùng **longest proper border** để cho phép các match chồng lấn.

Lưu ý đây là giải thích cấu trúc của quy tắc; **tính đúng của bảng shift** dựa trên bất biến của quá trình tiền xử lý border và strong shift, và được kiểm thử độc lập nhiều trường hợp trong mã. Không nên tự hoán đổi công thức shift của hai biến thể good-suffix khác nhau khi chưa kiểm chứng lại các bất biến.

## 15. Tại sao dùng cả bad-character và good-suffix?

Hai quy tắc sử dụng **hai loại chứng cứ khác nhau**:

- Bad-character biết **ký tự c tại vị trí mismatch** có ở đâu trong mẫu.
- Good-suffix biết **một đoạn dài ở cuối mẫu đã khớp** và mẫu có những border/occurrence nào.

Có trường hợp c hoàn toàn không nằm trong P nên badShift lớn; có trường hợp c xuất hiện nhiều nơi nên badShift nhỏ nhưng goodShift lại lớn nhờ cấu trúc hậu tố. Ngược lại, goodShift đôi khi chỉ là 1 còn bad-character giúp bỏ qua một đoạn lớn.

Kết hợp max của hai dịch chuyển tận dụng quy tắc mạnh hơn tại từng mismatch. **Không có bảo đảm mỗi bước sẽ dịch nhiều hơn 1**: với mẫu tự lặp hoặc chuỗi chứa ký tự rất thường xuyên, có thể dịch 1 nhiều lần.

Cần phân biệt **tổng số phép so ký tự**, **số lần căn chỉnh cửa sổ** và **chi phí tiền xử lý**. Boyer–Moore có thể có rất ít alignments nhưng tại mỗi alignment vẫn phải so nhiều ký tự từ phải sang trái.

## 16. Độ phức tạp: điều gì được bảo đảm?

Gọi n=độ dài văn bản, m=độ dài mẫu, k=số occurrence được trả.

**Tiền xử lý:**

~~~text
last occurrence với HashMap:
  thời gian kỳ vọng O(m), bộ nhớ O(m).

Strong good-suffix preprocessing:
  thời gian O(m), bộ nhớ O(m).
~~~

**Tìm kiếm:** mỗi bước tăng start ít nhất 1, nên số alignments nhiều nhất n−m+1 khi 1≤m≤n. Tại mỗi alignment, có thể phải so tối đa m ký tự, dẫn tới **cận trên dễ chứng minh O(nm)** cho bản cài đặt đơn giản này; cộng thêm O(k) để lưu k vị trí kết quả. Trên dữ liệu thuận lợi, mỗi mismatch xảy ra ngay ký tự cuối và khoảng dịch có thể lớn gần m, số lần căn chỉnh ít, thường **sublinear theo n** về số ký tự thật sự đem so.

Tổng bộ nhớ của matcher (không kể văn bản đầu vào) là O(m) cho bảng bad-character, border và shift, cộng O(k) cho kết quả. Bộ đếm alignments và comparisons là long.

Có những phân tích cận chặt hơn cho các biến thể Boyer–Moore hoàn chỉnh, bao gồm xử lý khi mẫu tự lặp và kỹ thuật **Galil** để tránh so lại đoạn đã biết. Vì bản Java ở đây **không** cài Galil rule, ta chỉ sử dụng **cận trên O(nm) an toàn** thay vì khẳng định vô điều kiện rằng mọi cài Boyer–Moore đều đạt O(n+m) trên mọi input.

## 17. Boyer–Moore so với KMP, Horspool và Rabin–Karp

| Thuật toán | Ý tưởng chính | Ưu điểm / điều cần biết |
| --- | --- | --- |
| Naive | Thử mọi s, so trực tiếp mẫu | Cài dễ, không tiền xử lý, O(nm) worst-case |
| KMP | Prefix-function/failure links giữ tiến bộ so khớp | O(n+m) worst-case, đọc văn bản tiến từng ký tự |
| Boyer–Moore đầy đủ | So từ phải sang trái, dùng bad-character và good-suffix | Thường bỏ qua nhiều alignments, có tiền xử lý và code phức tạp hơn |
| Boyer–Moore–Horspool | Chủ yếu dùng dịch dựa trên ký tự ở cuối cửa sổ | Đơn giản, thực tế phổ biến, không phải cùng bảng strong good-suffix |
| Rabin–Karp | Hash các cửa sổ và so lại khi hash bằng | Hữu ích cho nhiều mẫu/cửa sổ, cần xử lý collision |
| Aho–Corasick | Automaton trie với failure links | Phù hợp tìm nhiều mẫu đồng thời, khác bài một mẫu |

KMP có bảo đảm tuyến tính đơn giản hơn để trình bày, còn Boyer–Moore thường có hiệu quả tốt khi mẫu dài và bảng chữ cái đa dạng. Nếu chỉ tìm **một lần** trong Java, phương thức String.indexOf có thể được tối ưu sâu bởi JDK và đáng dùng thay vì tự viết, trừ khi bài tập yêu cầu chính thuật toán Boyer–Moore hoặc cần các thống kê/cơ chế riêng.

Đừng nhầm **Horspool** với việc “cài Boyer–Moore nhưng bỏ hẳn good-suffix” mà vẫn giữ nguyên mọi công thức; Horspool có quy tắc dịch và chỉ số xét ký tự văn bản **cụ thể** của nó.

## 18. Các trường hợp biên cần quyết định từ đầu

**Mẫu rỗng:** về mặt chuỗi, mẫu rỗng xuất hiện tại mọi **ranh giới** từ 0 đến n; bản Java quy định trả [0,1,...,n]. Vì số kết quả là n+1, có thể rất lớn khi văn bản dài; một API production có thể chọn chỉ trả số lượng hoặc streaming kết quả.

**Văn bản rỗng, mẫu khác rỗng:** không có cửa sổ s hợp lệ, trả []. Mẫu dài hơn văn bản cũng trả [] mà không cần đọc text.

**Mẫu có dấu hoặc chữ hoa/thường:** so khớp **chính xác từng đơn vị UTF-16**; 'A' khác 'a', 'é' khác 'e', và dạng Unicode tổ hợp có thể khác dạng dựng sẵn ngay cả khi nhìn giống nhau. Nếu nghiệp vụ cần không phân biệt hoa/thường hoặc chuẩn hóa Unicode, hãy chuẩn hóa **cả text và pattern** và hiểu rằng việc chuẩn hóa có thể làm thay đổi offset cần báo về chuỗi gốc.

**Emoji và surrogate pair:** Java String.length đếm đơn vị UTF-16; emoji như 😊 thường chiếm hai char. Trong ví dụ "A😊B😊", hai occurrence của mẫu "😊" có offset **[1,4]** theo UTF-16. Nếu cần trả số lượng Unicode code points hoặc grapheme clusters, phải thay đổi mô hình ký tự/đánh chỉ số, không đơn giản diễn giải offset char thành offset code point.

**Overlaps:** "ABABA"/"ABA" trả [0,2], không chỉ [0]. **Mẫu toàn một ký tự:** "AAAAAA"/"AAA" trả [0,1,2,3]. Hai bài này phát hiện lỗi full-match shift hay xảy ra.

## 19. Mã Java 17+ có thể chạy độc lập

Chương trình **BoyerMooreShifts.java** bao gồm:

- Constructor nhận mẫu String không null, tạo bảng **last occurrence** và hai mảng **border/shift** của strong good-suffix.
- **preprocessStrongGoodSuffix** với hai pha xây border và bù các dịch chuyển còn trống.
- **search(text)**: duyệt cửa sổ căn chỉnh; so từ cuối mẫu, chọn max(1,badShift,goodShift) khi mismatch; dùng shift[0] sau full match.
- **SearchResult**: danh sách vị trí và hai bộ đếm **alignments / comparisons**, đều được ghi từ quá trình tìm kiếm, giúp phân biệt số cửa sổ và số phép so.
- **naive**: oracle hoàn toàn độc lập, thử từng vị trí bằng String.regionMatches thay vì dùng bảng dịch.
- **verify**: vét cạn cặp text/pattern trên bảng chữ cái nhị phân, random seed, Unicode, overlaps, input rỗng và null.
- **Bảo vệ tràn chỉ số start:** trước khi cộng một khoảng dịch vào start, so với số vị trí cửa sổ còn lại; nếu bước nhảy vượt maxStart thì dừng. Do đó không cộng start quá giới hạn int trong phép dịch.

**Hợp đồng:** so khớp phân biệt chữ hoa/thường, chính xác các đơn vị UTF-16; vị trí trả 0-based; kết quả gồm toàn bộ occurrences có thể chồng lấn; null bị từ chối bằng IllegalArgumentException. Kết quả trả danh sách bất biến qua List.copyOf. Constructor và search có thể được gọi với mẫu rỗng, khi ấy trả mọi biên 0..n theo quy ước đã chốt.

Mã **không** dùng regex, không cài đặt Aho–Corasick hay chỉ gọi String.indexOf để lấy đáp án; hai quy tắc Boyer–Moore được hiện thực trực tiếp.

~~~java
import java.util.*;

public final class BoyerMooreShifts {
    public record SearchResult(List<Integer> positions,
                               long alignments, long comparisons) {
        public SearchResult {
            positions = List.copyOf(positions);
        }
    }

    private final String pattern;
    private final int m;
    private final Map<Character, Integer> last = new HashMap<>();
    private final int[] shift;
    private final int[] border;

    public BoyerMooreShifts(String pattern) {
        if (pattern == null) {
            throw new IllegalArgumentException("null pattern");
        }
        this.pattern = pattern;
        this.m = pattern.length();
        this.shift = new int[m + 1];
        this.border = new int[m + 1];
        for (int i = 0; i < m; i++) {
            last.put(pattern.charAt(i), i);
        }
        if (m == 0) {
            shift[0] = 1;
        } else {
            preprocessStrongGoodSuffix();
        }
    }

    private void preprocessStrongGoodSuffix() {
        int i = m;
        int j = m + 1;
        border[i] = j;
        while (i > 0) {
            while (j <= m &&
                    pattern.charAt(i - 1) != pattern.charAt(j - 1)) {
                if (shift[j] == 0) {
                    shift[j] = j - i;
                }
                j = border[j];
            }
            i--;
            j--;
            border[i] = j;
        }
        j = border[0];
        for (int k = 0; k <= m; k++) {
            if (shift[k] == 0) {
                shift[k] = j;
            }
            if (k == j) {
                j = border[j];
            }
        }
        for (int k = 0; k <= m; k++) {
            if (shift[k] <= 0) {
                throw new AssertionError("nonpositive good-suffix shift");
            }
        }
    }

    public SearchResult search(String text) {
        if (text == null) {
            throw new IllegalArgumentException("null text");
        }
        int n = text.length();
        List<Integer> positions = new ArrayList<>();
        if (m == 0) {
            for (int i = 0; i <= n; i++) {
                positions.add(i);
            }
            return new SearchResult(positions, (long) n + 1, 0);
        }
        int start = 0;
        int maxStart = n - m;
        long alignments = 0, comparisons = 0;
        while (start <= maxStart) {
            alignments++;
            int j = m - 1;
            while (j >= 0) {
                comparisons++;
                if (pattern.charAt(j) != text.charAt(start + j)) {
                    break;
                }
                j--;
            }
            int distance;
            if (j < 0) {
                positions.add(start);
                distance = shift[0];
            } else {
                char bad = text.charAt(start + j);
                int badCharacter = j - last.getOrDefault(bad, -1);
                int goodSuffix = shift[j + 1];
                distance = Math.max(1, Math.max(badCharacter, goodSuffix));
            }
            if (distance > maxStart - start) {
                break;
            }
            start += distance;
        }
        return new SearchResult(positions, alignments, comparisons);
    }

    private static List<Integer> naive(String text, String pattern) {
        List<Integer> result = new ArrayList<>();
        int m = pattern.length();
        for (int start = 0; start + m <= text.length(); start++) {
            if (text.regionMatches(start, pattern, 0, m)) {
                result.add(start);
            }
        }
        return result;
    }

    private static void check(String text, String pattern) {
        BoyerMooreShifts matcher = new BoyerMooreShifts(pattern);
        SearchResult actual = matcher.search(text);
        List<Integer> expected = naive(text, pattern);
        if (!actual.positions().equals(expected)) {
            throw new AssertionError("mismatch text=" + text +
                    " pattern=" + pattern +
                    " actual=" + actual.positions() +
                    " expected=" + expected);
        }
        for (int start : expected) {
            if (!text.startsWith(pattern, start)) {
                throw new AssertionError("invalid occurrence");
            }
        }
        if (actual.alignments() < 0 || actual.comparisons() < 0) {
            throw new AssertionError("invalid counters");
        }
    }

    private static String binaryWord(int mask, int length) {
        char[] chars = new char[length];
        for (int i = 0; i < length; i++) {
            chars[i] = ((mask >>> i) & 1) == 0 ? 'A' : 'B';
        }
        return new String(chars);
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid argument accepted");
    }

    private static void verify() {
        int exhaustive = 0;
        for (int n = 0; n <= 9; n++) {
            for (int t = 0; t < (1 << n); t++) {
                String text = binaryWord(t, n);
                for (int m = 0; m <= 6; m++) {
                    for (int p = 0; p < (1 << m); p++) {
                        check(text, binaryWord(p, m));
                        exhaustive++;
                    }
                }
            }
        }

        Random random = new Random(3722026L);
        char[] alphabet = {'a', 'b', 'Z', 'é', '0'};
        int seeded = 0;
        for (int trial = 0; trial < 3000; trial++) {
            int n = random.nextInt(61);
            int m = random.nextInt(19);
            StringBuilder t = new StringBuilder(n);
            StringBuilder p = new StringBuilder(m);
            for (int i = 0; i < n; i++) {
                t.append(alphabet[random.nextInt(alphabet.length)]);
            }
            for (int i = 0; i < m; i++) {
                p.append(alphabet[random.nextInt(alphabet.length)]);
            }
            check(t.toString(), p.toString());
            seeded++;
        }

        check("A\uD83D\uDE0AB\uD83D\uDE0A", "\uD83D\uDE0A");
        check("café café", "fé");
        check("aAaAA", "AA");
        check("BANANANA", "ANA");
        check("AAAAAA", "AAA");
        check("ABABABAB", "ABAB");
        check("", "");
        check("", "A");
        check("A", "");
        check("ab", "abcdef");
        check("ZZZABC", "ABC");

        expectInvalid(() -> new BoyerMooreShifts(null));
        expectInvalid(() -> new BoyerMooreShifts("A").search(null));

        System.out.println("Exhaustive binary text/pattern pairs: " +
                exhaustive + " PASS");
        System.out.println("Seeded UTF-16 text/pattern pairs: " +
                seeded + " PASS");
        System.out.println("Overlaps, Unicode, empty and invalid cases: PASS");
    }

    public static void main(String[] args) {
        System.out.println("EXAMPLE: " +
                new BoyerMooreShifts("EXAMPLE")
                        .search("HERE IS A SIMPLE EXAMPLE").positions());
        System.out.println("ABA overlaps: " +
                new BoyerMooreShifts("ABA").search("ABABA").positions());
        System.out.println("AAA repeats: " +
                new BoyerMooreShifts("AAA").search("AAAAAA").positions());
        SearchResult jump =
                new BoyerMooreShifts("ABC").search("ZZZABC");
        System.out.println("Bad-character jump: " + jump.positions() +
                ", alignments=" + jump.alignments());
        System.out.println("Emoji UTF-16 offsets: " +
                new BoyerMooreShifts("\uD83D\uDE0A")
                        .search("A\uD83D\uDE0AB\uD83D\uDE0A")
                        .positions());
        System.out.println("Empty pattern in ab: " +
                new BoyerMooreShifts("").search("ab").positions());
        verify();
    }
}
~~~

Lưu mã trên thành tệp **BoyerMooreShifts.java**, sau đó chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac BoyerMooreShifts.java
java BoyerMooreShifts
~~~

**Stdout chính xác quan sát được khi chương trình chạy thành công:**

~~~text
EXAMPLE: [17]
ABA overlaps: [0, 2]
AAA repeats: [0, 1, 2, 3]
Bad-character jump: [3], alignments=2
Emoji UTF-16 offsets: [1, 4]
Empty pattern in ab: [0, 1, 2]
Exhaustive binary text/pattern pairs: 129921 PASS
Seeded UTF-16 text/pattern pairs: 3000 PASS
Overlaps, Unicode, empty and invalid cases: PASS
~~~

Dòng "Bad-character jump" cho thấy chỉ có **hai lần căn chỉnh** ở s=0 và s=3 trong T="ZZZABC" với P="ABC". Các dòng PASS được in sau khi toàn bộ so sánh với oracle ngây thơ đã hoàn tất.

## 20. Kiểm thử vét cạn 129.921 cặp text/pattern

Tạo mọi chuỗi nhị phân gồm các ký tự 'A' và 'B', với:

~~~text
Độ dài text n = 0..9:
  số text = 2^0 + ... + 2^9
          = 2^10 - 1
          = 1023.

Độ dài pattern m = 0..6:
  số pattern = 2^0 + ... + 2^6
             = 2^7 - 1
             = 127.

Số cặp test = 1023 * 127 = 129921.
~~~

Mọi cặp được chạy bằng:

1. **BoyerMooreShifts** dùng cả bảng last và strong good-suffix.
2. **Oracle naive** duyệt tất cả vị trí, kiểm tra chính xác bằng String.regionMatches.

Hai danh sách kết quả phải **bằng nhau hoàn toàn**, gồm số lượng, thứ tự và các vị trí overlap. Nhờ có cả pattern rỗng và text rỗng, phép vét cạn kiểm tra phần lớn tình huống biên của mô hình chỉ số UTF-16. Nhiều chuỗi lặp như "AAAAAA" cũng nằm trong tập test.

Thử vét cạn nhỏ **không phải chứng minh toán học** cho mọi mẫu dài vô hạn, nhưng là một công cụ QA tốt vì phát hiện các lỗi dịch quá xa, border sai hoặc xử lý full match thiếu overlap mà vài ví dụ đơn lẻ dễ bỏ qua.

## 21. Kiểm thử 3.000 cặp ngẫu nhiên và trường hợp Unicode

Chương trình dùng **Random(3722026L)** tạo 3.000 cặp:

~~~text
text length ngẫu nhiên 0..60;
pattern length ngẫu nhiên 0..18;
alphabet = {'a','b','Z','é','0'}.
~~~

Cách sinh này kiểm tra:

- Văn bản dài/ngắn khác nhau, kể cả text ngắn hơn pattern.
- Chữ hoa và chữ thường, chữ có dấu.
- Ký tự lặp nhiều, các border xuất hiện ngẫu nhiên.
- Mẫu không nằm trong text hoặc xuất hiện nhiều lần.
- Overlaps và bad-character trùng/không trùng mẫu.

Ngoài ra các ca biên được thử trực tiếp: emoji với UTF-16 surrogate pair, chuỗi "café café", pattern có chữ hoa phân biệt, "BANANANA"/"ANA", "AAAAAA"/"AAA", "ABABABAB"/"ABAB", text rỗng, pattern rỗng, mẫu dài hơn text và đối số null.

Mỗi test so danh sách vị trí của Boyer–Moore với **oracle naive**, đồng thời dùng String.startsWith ở các kết quả oracle để xác nhận mỗi vị trí thực sự tạo một occurrence. Bộ đếm alignments/comparisons phải không âm.

## 22. Chứng minh tính đúng toàn thuật toán

Bất biến tại đầu mỗi vòng lặp: **mọi vị trí bắt đầu nhỏ hơn start đã được xét hoặc loại trừ bằng một quy tắc dịch an toàn**; mọi kết quả khớp ở các vị trí đó đã được ghi.

- Nếu so hết m ký tự, đoạn T[start..start+m) khớp P nên ghi start. shift[0] dựa trên proper border ngăn bỏ lỡ các occurrence chồng lấn.
- Nếu mismatch tại j, bad-character và strong good-suffix đều dựa trên chứng cứ đã biết (ký tự mismatch và hậu tố đã khớp) để loại các vị trí tiếp theo không thể là full match. Chọn khoảng dịch an toàn lớn hơn và ít nhất 1 bảo toàn bất biến.
- Mỗi vòng tăng start ít nhất 1, nên quá trình kết thúc sau hữu hạn alignments (với m>0, tối đa n−m+1 căn chỉnh).
- Khi start vượt n−m, không còn vị trí bắt đầu hợp lệ chưa xử lý; các vị trí đã ghi chính xác là mọi occurrence của P trong T.

Trường hợp m=0 được xử lý riêng theo quy ước match mọi ranh giới 0..n, nên thuật toán không truy cập P[m−1] với m=0. Trường hợp m>n bỏ qua vòng lặp và trả [].

**Phần cần chứng minh kỹ nhất** khi tự cài biến thể mới chính là an toàn của bảng good-suffix. Nếu thay công thức tiền xử lý, nhất thiết phải kiểm tra bất biến border và những vị trí được bỏ qua; không nên suy luận rằng “chọn dịch lớn nhất” luôn đúng với **mọi bảng dịch tùy ý**.

## 23. Lỗi phổ biến khi viết Boyer–Moore

1. **So từ trái qua phải** nhưng lại áp dụng công thức dịch của bản so phải qua trái, khiến lập luận chứng minh không còn đúng.
2. **Dùng nhầm last[c] là lần xuất hiện đầu** chứ không phải cuối.
3. **Dùng last[c]=0 cho ký tự không tồn tại**, khiến bad-character dịch ít hơn và dễ rối với ký tự ở index 0.
4. **Tính badShift từ vị trí trong text** s+j thay vì chỉ số mẫu j.
5. **Không chặn dưới 1** khi last[c]>j, khiến bước dịch âm hoặc 0 và lặp vô hạn.
6. **Tính goodShift=shift[j]** thay vì shift[j+1] tại mismatch.
7. **Cộng badShift và goodShift** thay vì lấy max của hai khoảng dịch đã được chứng minh an toàn.
8. **Không phân biệt hậu tố đã khớp với hậu tố còn chưa so**, làm bảng good-suffix mất ý nghĩa.
9. **Không xét ký tự đứng trước occurrence của suffix trong strong rule**, tạo bảng dịch yếu hơn hoặc xử lý sai khi ghép công thức.
10. **Không lấp các ô shift=0** ở pha border thứ hai.
11. **Sau full match luôn dịch m**, bỏ sót occurrences chồng lấn.
12. **Sau full match luôn dịch 1**, đúng về kết quả nhưng bỏ phí dữ liệu border và làm yếu hiệu quả.
13. **Không xét pattern rỗng**, gây charAt(-1) hoặc vòng lặp vô hạn.
14. **Không xét pattern dài hơn text**, gây index out of bounds.
15. **Mặc định một char là một code point Unicode**, khiến offset emoji bị diễn giải sai.
16. **Nhầm chữ hoa/thường và Unicode normalization**, tạo kết quả không đúng yêu cầu sản phẩm.
17. **Coi hash map last là luôn O(1) worst-case tuyệt đối**, bỏ qua giả thiết amortized/trung bình.
18. **Khẳng định mọi biến thể Boyer–Moore luôn O(n+m)** mà không nêu thuật toán cụ thể, quy tắc phụ và điều kiện.
19. **Chỉ thử mẫu không lặp**, không phát hiện bug của border/overlap.
20. **Kiểm tra chỉ ví dụ có một match**, bỏ qua nhiều match và no match.
21. **Lấy String.indexOf làm phần lõi rồi tuyên bố đã cài Boyer–Moore**, dù không hề áp dụng các quy tắc dịch.
22. **Không kiểm chứng bằng oracle độc lập**, khiến một lỗi trong bảng dịch có thể im lặng bỏ qua kết quả.
23. **Không giữ nguyên mẫu dùng lại cho nhiều văn bản**, khiến tốn tiền xử lý lặp nếu mẫu cố định trong một hệ thống tìm kiếm.
24. **Không phân biệt match position và alignment count**, hiểu sai tối ưu hiệu năng từ vài kết quả in ra.

## 24. Bài tập thực hành và mở rộng

**Bài 1 — Last occurrence:** với mẫu "EXAMPLE", lập bảng last cho tất cả ký tự của mẫu và ký tự Z không có trong mẫu. Xác định badShift khi mismatch tại j=5 đối với X và đối với Z.

**Bài 2 — Nhảy bad-character:** chạy tay "ZZZABC"/"ABC": ghi từng lần căn chỉnh, mismatch tại j và độ dịch. Vì sao vị trí 1 và 2 chắc chắn không phải match?

**Bài 3 — Overlap:** với "ABABA"/"ABA", giải thích longest proper border của mẫu và vì sao fullMatchShift=2. Với "AAAAAA"/"AAA", giải thích fullMatchShift=1.

**Bài 4 — Good suffix:** thử một mẫu có lặp hậu tố như "ABAB". Liệt kê các proper border; giải thích trường hợp sau full match và một mismatch xảy ra sau khi đã khớp suffix.

**Bài 5 — Strong vs weak:** tạo một mẫu mà suffix S có nhiều occurrence về trái nhưng ký tự đứng trước một occurrence giống ký tự P[j] vừa mismatch. Vì sao strong rule có thể loại căn chỉnh ấy?

**Bài 6 — Cài độc lập:** tự viết last occurrence bằng int[65536] chứa −1, so với HashMap<Character,Integer>. Ghi rõ thời gian khởi tạo và bộ nhớ; kiểm thử cặp chuỗi nhiều dấu tiếng Việt.

**Bài 7 — Oracle:** sinh mọi text n≤9 và mẫu m≤6 trên bảng chữ cái {A,B}; đối chiếu danh sách match của Boyer–Moore với brute force. Tính chính xác số cặp test.

**Bài 8 — Chỉ một kết quả:** sửa search trả vị trí đầu tiên thay vì danh sách; so với String.indexOf của Java. Giải thích tại sao một API trả “tất cả match” có thể cần bộ nhớ O(k).

**Bài 9 — Unicode:** tìm emoji "😊" trong "A😊B😊", nêu rõ offset UTF-16 [1,4] và cách đổi sang chỉ số code point nếu ứng dụng yêu cầu; kiểm tra các dấu Unicode dạng tổ hợp.

**Bài 10 — So sánh hiệu năng:** đo alignments và comparisons trên văn bản ngẫu nhiên với bảng chữ cái lớn và văn bản rất nhiều A. So với naive và KMP, thử nhiều n,m/seed thay vì kết luận từ một mẫu.

**Bài 11 — Horspool:** cài riêng bản Boyer–Moore–Horspool với bảng shift thích hợp và giải thích sự khác biệt so với strong good-suffix. Tránh lấy nguyên bảng shift[j+1] từ chương trình này để thay vào Horspool.

**Bài 12 — Galil:** tìm hiểu ý tưởng ghi nhớ phần đoạn văn bản đã chứng minh khớp khi mẫu tự lặp. Giải thích vì sao có thể tránh so lại một số ký tự sau những bước dịch liên tiếp.

**Kết luận:** Boyer–Moore tìm kiếm mẫu bằng cách so **từ phải sang trái**, dùng **bad-character** để tận dụng ký tự gây mismatch và **good-suffix** để tận dụng phần cuối mẫu đã khớp. Hai khoảng dịch an toàn được kết hợp bằng **max**, còn sau full match phải dùng **shift[0]** thay vì luôn nhảy m để không bỏ sót overlap. Tính đúng dựa trên chứng minh không thể có occurrence ở các vị trí bị loại; hiệu năng phụ thuộc mẫu và văn bản. Khi triển khai Java cần nhất quán **UTF-16 offsets**, xử lý chuỗi rỗng và kiểm thử trên nhiều mẫu có border, chồng lấn, ký tự lặp và Unicode.
