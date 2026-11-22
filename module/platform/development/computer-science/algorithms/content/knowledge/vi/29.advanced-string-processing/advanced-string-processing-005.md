# Truy vấn đoạn chung bằng LCP và cực tiểu trên đoạn

Trong **xử lý chuỗi nâng cao**, nhiều bài toán hỏi hai đoạn của cùng một chuỗi giống nhau bao nhiêu ký tự ở phần đầu, hoặc hai hậu tố bắt đầu ở hai vị trí bất kỳ có **tiền tố chung dài nhất** (*Longest Common Prefix – LCP*) dài bao nhiêu. Nếu so ký tự từ đầu cho từng truy vấn, một câu hỏi có thể tốn O(n) thời gian; với hàng chục nghìn câu hỏi, tổng chi phí có thể rất lớn.

Một cách giải nền tảng là xây **mảng hậu tố** (*suffix array – SA*), tính **LCP của hai hậu tố kề nhau trong thứ tự từ điển**, rồi giải bài toán cực tiểu trên một đoạn (**Range Minimum Query – RMQ**). Công thức then chốt:

~~~text
Cho hai vị trí bắt đầu i,j khác nhau:
ri = rank[i], rj = rank[j].
a = min(ri,rj), b = max(ri,rj).

LCE(i,j) = min LCP[k] với k = a+1 .. b.
~~~

Trong đó LCE (*Longest Common Extension*) là độ dài tiền tố chung của hai suffix bất kỳ. Nếu dùng **sparse table** cho RMQ, mỗi truy vấn có thể trả lời **O(1)** sau bước tiền xử lý. Đây là bài Knowledge trực tiếp **“Truy vấn đoạn chung bằng LCP và cực tiểu trên đoạn”** thuộc nhóm **Xử lý chuỗi nâng cao** trong Computer Science Algorithms.

Bài sẽ giải thích công thức và chứng minh, các quy ước chỉ số dễ nhầm, cách dựng SA bằng **doubling**, tính LCP kề nhau bằng **Kasai**, dựng sparse table RMQ, ứng dụng cho hai đoạn hữu hạn, so sánh đoạn con, số lượng substring phân biệt và substring lặp dài nhất. Phần Java 17+ có thể chạy độc lập, đối chiếu với oracle ngây thơ trên **9.841 chuỗi vét cạn và 800 chuỗi có seed**, cùng kiểm tra chuỗi lặp 5.000 đơn vị và Unicode UTF-16.

## 1. Phát biểu hai kiểu truy vấn thường gặp

Giả sử S có độ dài n, đánh chỉ số 0-based.

**Kiểu A – hai hậu tố:** cho i,j trong [0,n), hỏi bao nhiêu ký tự đầu tiên của S[i..n) và S[j..n) bằng nhau.

~~~text
LCE(i,j) = max k sao cho
S[i..i+k) == S[j..j+k).

0 <= k <= min(n-i, n-j).
~~~

**Kiểu B – hai đoạn hữu hạn:** cho [a,a+lenA) và [b,b+lenB), hỏi chúng có bao nhiêu ký tự đầu giống nhau. Khi đó không được so quá cuối một trong hai đoạn:

~~~text
CommonPrefixSegments =
    min(LCE(a,b), lenA, lenB).
~~~

**Truy vấn bằng nhau:** hai đoạn cùng độ dài len có cùng nội dung khi và chỉ khi LCE(a,b)≥len, sau khi đã kiểm tra các đoạn nằm trong S.

Ví dụ S="banana": hai suffix bắt đầu ở 1 và 3 là "anana" và "ana", có phần đầu chung "ana" dài 3. Nhưng nếu hỏi hai đoạn [1,3)="an" và [3,6)="ana", tiền tố chung của **hai đoạn hữu hạn** chỉ dài 2.

## 2. Hậu tố, tiền tố và thứ tự từ điển

Một **suffix/hậu tố** tại vị trí i là đoạn S[i..n). Với n>0 có đúng n hậu tố **không rỗng**, bắt đầu lần lượt ở 0..n−1. Có thể xét thêm hậu tố rỗng S[n..n), nhưng bài này quy định rõ **không đưa hậu tố rỗng vào suffix array**.

Ví dụ S="banana":

~~~text
i=0: banana
i=1: anana
i=2: nana
i=3: ana
i=4: na
i=5: a
~~~

Thứ tự **từ điển (lexicographic)** so ký tự đầu tiên khác nhau; nếu một chuỗi là tiền tố của chuỗi kia, chuỗi ngắn hơn đứng trước. Theo thứ tự từ điển trên đơn vị char UTF-16 của Java, các suffix của "banana" sắp như sau:

~~~text
a
ana
anana
banana
na
nana
~~~

Tính đúng của công thức RMQ sẽ dựa chính vào việc **tất cả chuỗi có cùng một tiền tố cố định tạo thành một khoảng liên tiếp** khi sắp theo từ điển.

## 3. Suffix array lưu điều gì?

**Suffix array SA** là hoán vị của các vị trí 0..n−1, trong đó SA[r] là **vị trí bắt đầu suffix đứng thứ r** theo thứ tự từ điển.

Với "banana":

| Rank r | SA[r] | Suffix S[SA[r]..n) |
| ---: | ---: | --- |
| 0 | 5 | a |
| 1 | 3 | ana |
| 2 | 1 | anana |
| 3 | 0 | banana |
| 4 | 4 | na |
| 5 | 2 | nana |

Do đó:

~~~text
SA = [5,3,1,0,4,2].
~~~

**Rank array** là hoán vị ngược của SA:

~~~text
rank[SA[r]] = r.
rank[i] = vị trí của suffix S[i..n) trong SA.

Với banana:
rank = [3,2,5,1,4,0].
~~~

Khi truy vấn hai vị trí gốc i,j, ta tra rank[i],rank[j] trong **O(1)** để biết chúng nằm ở đâu trong dãy các suffix đã sắp.

## 4. Dựng SA bằng thuật toán doubling

Mã Java sử dụng phương pháp **doubling** dễ kiểm chứng. Ban đầu ta biết thứ tự của suffix theo ký tự đầu tiên (nhóm có cùng ký tự được gán cùng lớp/rank tạm). Với bước độ dài d=1,2,4,8,..., so hai vị trí i,j bằng **cặp lớp**:

~~~text
(class[i], class[i+d] nếu i+d<n, ngược lại -1)
so với
(class[j], class[j+d] nếu j+d<n, ngược lại -1).
~~~

Cặp này biểu diễn thứ tự của hai chuỗi con có độ dài tới **2d**. Sau khi sắp, nén lại thành lớp mới 0,1,2...; mỗi vòng làm độ dài phân biệt được **gấp đôi**. Khi mọi suffix có lớp riêng (n lớp) thì dừng sớm.

Tại sao dùng giá trị **−1** cho vị trí ngoài cuối chuỗi? Vì suffix ngắn hơn phải đứng trước nếu phần trước đã giống nhau. Mọi mã UTF-16 của ký tự thật không âm, nên sentinel −1 được xếp trước ký tự thật.

Cách minh họa này dùng Integer[] và Arrays.sort với comparator so cặp lớp, mỗi vòng O(n log n) và số vòng O(log n). Vì vậy tổng thời gian dựng SA của **bản cài cụ thể** là O(n log² n), không phải O(n log n). Các bản dùng counting/radix sort trên lớp nguyên có thể xây SA theo O(n log n); có thuật toán sâu hơn đạt O(n) trong những mô hình thích hợp.

## 5. Mảng LCP kề nhau: quy ước cực quan trọng

Sau khi có SA, định nghĩa:

~~~text
LCP[0] = 0.

Với r = 1..n-1:
LCP[r] = LCP của suffix SA[r-1] và SA[r].
~~~

Nghĩa là **LCP[r] đứng giữa suffix tại rank r−1 và rank r**. Không dùng LCP[r] cho hai suffix tại rank r và rank r+1 trong quy ước bài này.

Với "banana":

| r | Suffix trước | Suffix hiện tại | LCP[r] |
| ---: | --- | --- | ---: |
| 0 | Không có | a | 0 |
| 1 | a | ana | 1 |
| 2 | ana | anana | 3 |
| 3 | anana | banana | 0 |
| 4 | banana | na | 0 |
| 5 | na | nana | 2 |

~~~text
LCP = [0,1,3,0,0,2].
~~~

Có tài liệu dùng mảng khác với LCP[r] so SA[r] và SA[r+1]. **Cả hai cách đều hợp lệ**, nhưng công thức vùng RMQ phải thay đổi tương ứng. Trong chương trình này, luôn dùng **LCP[0]=0, LCP[r]=lcp(SA[r−1],SA[r])**.

## 6. Kasai tính mảng LCP trong O(n)

Cách đơn giản là so từng cặp suffix kề nhau từ đầu, nhưng có thể mất O(n²) nếu chuỗi có nhiều ký tự giống nhau. Thuật toán **Kasai** tận dụng phần đã khớp giữa các vị trí bắt đầu liên tiếp.

Ý tưởng:

~~~text
h = 0

for i = 0..n-1:
    r = rank[i]

    if r == 0:
        h = 0
        continue

    j = SA[r-1]
    while i+h < n && j+h < n && S[i+h] == S[j+h]:
        h++

    LCP[r] = h

    if h > 0: h--
~~~

Mỗi vòng bắt đầu từ vị trí văn bản i thay vì đi tuần tự theo rank trong SA. Mảng rank giúp tìm ngay suffix đứng trước S[i..n) trong thứ tự từ điển.

**Giải thích h--:** khi bỏ ký tự đầu tiên của hai suffix bắt đầu ở i và j, nếu chúng từng khớp h ký tự thì các suffix bắt đầu ở i+1 và j+1 còn khớp ít nhất h−1 ký tự. Tiền nhiệm theo từ điển của suffix i+1 (nếu có) cung cấp cận dưới không tệ hơn trong lập luận Kasai; vì vậy không cần so lại toàn bộ h−1 ký tự ở mỗi bước.

## 7. Chứng minh tính tuyến tính của Kasai

Trong vòng lặp ngoài có n vị trí i. Biến h chỉ tăng khi phép so trong while thành công và giảm nhiều nhất 1 ở cuối mỗi vòng. Vì h luôn không âm và không vượt n, tổng số lần tăng h trên toàn bộ n vòng là O(n): trực giác là mỗi lần tăng có thể “trả” bằng một lần giảm ở vòng sau hoặc phần tăng cuối cùng còn lại tối đa n.

Mỗi lần while thất bại tạo tối đa một phép so bổ sung cho mỗi i. Phần ngoài while chỉ truy cập mảng O(1). Do đó **tổng thời gian Kasai O(n)**, thêm O(n) bộ nhớ cho rank và LCP.

Điểm then chốt không phải mọi cặp suffix kề nhau chỉ cần O(1) phép so **riêng lẻ**. Một suffix cụ thể vẫn có thể so nhiều ký tự, nhưng tổng phần so thêm sau khi tái sử dụng h qua toàn bộ vòng chạy là tuyến tính.

Nếu rank[i]=0, suffix tại i đứng đầu thứ tự, không có suffix kề trước; quy ước LCP[0]=0 và đặt h=0. Không nên truy cập SA[−1] hay giữ h cũ ở trường hợp ấy.

## 8. Định lý cầu nối: LCE bất kỳ thành RMQ trên LCP

Giả sử hai hậu tố cần so bắt đầu ở i và j, khác nhau. Đặt:

~~~text
a = min(rank[i], rank[j]).
b = max(rank[i], rank[j]).
a < b.
~~~

Định lý:

~~~text
LCE(i,j) = min(LCP[a+1], LCP[a+2], ..., LCP[b]).
~~~

Ký hiệu **min trên đoạn [a+1,b] bao gồm cả hai đầu**, trong khi các đoạn substring của Java thường là **nửa mở [start,end)**. Cần ghi rõ quy ước để không sai một ô.

Nếu i=j thì hai suffix giống hệt, vì vậy:

~~~text
LCE(i,i) = n-i.
~~~

Trường hợp này **không dùng RMQ trên đoạn rỗng**. Nếu hai vị trí có rank bằng nhau trong một SA là hoán vị, chúng chính là cùng một vị trí i=j. Phải kiểm tra riêng, nếu không việc lấy log2(0) hoặc đọc sparse table sẽ sai.

## 9. Vì sao lấy cực tiểu của nhiều LCP kề nhau?

Đặt k là độ dài tiền tố chung của **hai suffix ở hai đầu** SA[a] và SA[b]. Trong thứ tự từ điển, mọi suffix nằm giữa chúng phải có cùng k ký tự đầu ấy: nếu một suffix trung gian khác ở một ký tự trước vị trí k, nó buộc phải nằm **ngoài khoảng** sắp xếp giữa hai đầu, mâu thuẫn.

Vì thế mọi cặp suffix kề nhau từ rank a tới b cùng khớp **ít nhất k ký tự**; suy ra:

~~~text
min LCP[a+1..b] >= k.
~~~

Ngược lại, gọi q là giá trị nhỏ nhất trong các LCP kề nhau đó. Vì **mỗi** cặp suffix liên tiếp trong chuỗi rank a,a+1,...,b có chung **ít nhất q ký tự đầu**, ta có thể suy theo tính bắc cầu của “cùng q ký tự đầu”: tất cả suffix trong khoảng đều cùng một prefix dài q. Đặc biệt hai suffix ở hai đầu khớp ít nhất q ký tự:

~~~text
k >= min LCP[a+1..b].
~~~

Kết hợp hai bất đẳng thức, k bằng đúng **cực tiểu LCP trong đoạn rank**. Đây là lý do **Range Minimum Query**, chứ không phải maximum hay tổng LCP, trả kết quả LCE.

## 10. Truy vết công thức trên "banana"

Ta có:

~~~text
SA  = [5,3,1,0,4,2].
LCP = [0,1,3,0,0,2].

rank[1] = 2 ("anana").
rank[3] = 1 ("ana").
~~~

Đoạn LCP cần lấy là:

~~~text
a=1, b=2.
LCP[a+1..b] = LCP[2..2] = [3].
LCE(1,3) = 3 ("ana").
~~~

Thử hai suffix khác:

~~~text
i=1 ("anana"), rank=2.
j=5 ("a"),     rank=0.

a=0,b=2.
LCP[1..2] = [1,3].
min = 1.
LCE(1,5) = 1 ("a").
~~~

Thử các suffix "nana" và "na":

~~~text
i=2, rank=5.
j=4, rank=4.

LCP[5] = 2.
LCE(2,4)=2 ("na").
~~~

Việc **tra rank rồi lấy min** thay cho so từng ký tự theo hai suffix là bước biến đổi quan trọng nhất của bài.

## 11. RMQ là gì và chọn cấu trúc nào?

**RMQ (Range Minimum Query)** nhận một mảng A cố định và trả:

~~~text
RMQ(l,r) = min(A[l], A[l+1], ..., A[r]), l<=r.
~~~

Các cấu trúc thường gặp:

| Cấu trúc | Tiền xử lý | Truy vấn min | Khi nào thích hợp |
| --- | --- | --- | --- |
| Quét trực tiếp | O(1) | O(r−l+1) | Ít truy vấn, bài nhỏ |
| Prefix min thông thường | O(n) | Không đủ cho đoạn bất kỳ | Prefix min không thể “trừ” để ra min đoạn |
| Segment tree | O(n) | O(log n) | Cần cập nhật giá trị |
| Sparse table | O(n log n) | **O(1)** | Mảng cố định, phép min idempotent |
| Cartesian tree + RMQ chuyên dụng | Có thể O(n) | Có thể O(1) | Các triển khai nâng cao cần tối ưu bộ nhớ/thời gian |

Ở bài này S cố định, SA và LCP cố định, không có yêu cầu cập nhật ký tự. Vì vậy **sparse table** là giải pháp đơn giản để đạt O(1) cho nhiều truy vấn. Nếu thay đổi ký tự trong S, cả SA và các LCP có thể thay đổi trên diện rộng, nên **chỉ cập nhật segment tree trên LCP cũ là không đủ** để giữ index đúng.

## 12. Dựng sparse table cực tiểu

Đặt:

~~~text
st[k][i] =
    min của LCP[i..i+2^k-1].
~~~

Chỉ lưu những ô mà đoạn dài 2^k **nằm trọn trong [0,n)**.

Khởi tạo:

~~~text
st[0][i] = LCP[i].
~~~

Chuyển tiếp:

~~~text
st[k][i] =
    min(st[k-1][i],
        st[k-1][i+2^(k-1)]).
~~~

Mỗi khối dài 2^k là hợp của **hai nửa liên tiếp** dài 2^(k−1), nên công thức đúng. Với k=1, ta có min của hai phần tử; với k=2, min của bốn; v.v.

Số mức khoảng floor(log2(n))+1 khi n>0; mỗi mức có O(n) ô, nên tiền xử lý **O(n log n)** thời gian và **O(n log n)** bộ nhớ.

Mã Java tính thêm log2[len] bằng:

~~~text
log2[1] = 0.
log2[len] = log2[len/2]+1 với len>=2.
~~~

Giá trị này là floor(log2(len)) mà không cần gọi log số thực, tránh sai số khi len là một lũy thừa 2.

## 13. Trả RMQ trong O(1) bằng hai khối phủ

Cho đoạn [l,r] **bao gồm hai đầu**, len=r−l+1>0. Đặt k=floor(log2(len)), block=2^k.

Hai khối:

~~~text
Khối 1: [l, l+block-1].
Khối 2: [r-block+1, r].
~~~

Mỗi khối dài block và **hợp hai khối phủ cả đoạn [l,r]**. Hai khối có thể **chồng lên nhau**, nhưng phép min có tính chất idempotent: min(x,x)=x, nên việc một phần tử được xét hai lần không làm thay đổi đáp án.

Công thức:

~~~text
RMQ(l,r) =
    min(st[k][l], st[k][r-block+1]).
~~~

Không được áp dụng thủ thuật hai khối chồng nhau cho **tổng đoạn** một cách trực tiếp: cộng hai khối sẽ đếm trùng các phần tử nằm trong vùng chồng, trong khi min không bị vấn đề ấy.

LCE(i,j) với i≠j dùng RMQ(lowRank+1, highRank), nên sau xây SA, LCP và sparse table, **mỗi truy vấn LCE mất O(1)**.

## 14. Quy ước chỉ số nửa mở và inclusive

Trong String Java và mô tả substring, dùng:

~~~text
S[start..end) có các vị trí start, ..., end-1.
Chiều dài = end-start.
~~~

Trong RMQ nội bộ của chương trình, dùng:

~~~text
rangeMinimum(left,right)
bao gồm left và right.
Chiều dài = right-left+1.
~~~

Do LCP[r] là LCP giữa SA[r−1] và SA[r], với low<high:

~~~text
LCE = min LCP[low+1 .. high], inclusive.
Số phần tử = high-low.
~~~

Một lỗi rất phổ biến là gọi RMQ(low,high−1) do quen quy ước LCP[r] so SA[r] với SA[r+1] ở tài liệu khác. Công thức đó **không đúng với mảng của bài này**. Hãy thử ngay "banana" với rank(1)=2, rank(3)=1, LCP[2]=3 để phát hiện việc lệch một vị trí.

Đặc biệt, suffix tại vị trí n là **suffix rỗng** và được API lce hỗ trợ để tiện xử lý biên, nhưng **không xuất hiện trong SA/rank**. Nếu i=n hoặc j=n, tiền tố chung bằng 0; nếu cùng i=j=n, kết quả cũng 0.

## 15. Truy vấn LCE(i,j) từng bước

Sau tiền xử lý một lần:

~~~text
function LCE(i,j):
    yêu cầu 0<=i,j<=n.

    if i == j:
        return n-i.

    if i==n or j==n:
        return 0.

    ri = rank[i]; rj=rank[j].
    low = min(ri,rj).
    high = max(ri,rj).

    return RMQ(low+1,high).
~~~

Giải thuật này **không so trực tiếp ký tự** trong mỗi truy vấn. Thời gian chỉ gồm hai lần tra rank, một lần lấy min/max, một lần tra log2 và hai ô sparse table.

Đối với API chỉ nhận suffix **không rỗng**, có thể giới hạn i,j trong [0,n−1] và xóa hai nhánh n. Chương trình minh họa chọn phép mở rộng hợp lý cho suffix rỗng vì truy vấn các đoạn hữu hạn thường gặp [n,n).

**Đoạn khi i=j:** LCE(i,i)=n−i. Nếu quên trường hợp đó và dùng RMQ(low+1,high) với low=high, đoạn rỗng sẽ gây lỗi log2(0), truy cập vùng không hợp lệ hoặc trả một giá trị vô nghĩa.

## 16. Hai đoạn hữu hạn có tiền tố chung dài bao nhiêu?

Giả sử hai đoạn được biểu diễn bằng **vị trí đầu và độ dài**:

~~~text
A = S[a .. a+lenA).
B = S[b .. b+lenB).
~~~

Cho dù các suffix S[a..) và S[b..) khớp rất dài, chúng ta **không được vượt qua cuối một đoạn hữu hạn**. Vì vậy:

~~~text
CommonPrefixSegments(a,lenA,b,lenB)
    = min(LCE(a,b), lenA, lenB).
~~~

Ví dụ S="banana":

~~~text
A = S[1..5) = "anan", lenA=4.
B = S[3..6) = "ana",  lenB=3.

LCE(1,3)=3.
CommonPrefixSegments=min(3,4,3)=3.
~~~

Nếu đổi A thành [1,3)="an", kết quả còn min(3,2,3)=2.

Mã kiểm tra **a,lenA,b,lenB hợp lệ** bằng điều kiện position∈[0,n], length≥0 và length≤n−position. Trừ n−position trước khi so tránh nguy cơ overflow của biểu thức position+length khi đối số là số nguyên không đáng tin.

## 17. Truy vấn hai đoạn bằng nhau

Hai đoạn cùng độ dài d, bắt đầu ở a,b, bằng nhau chính xác khi:

~~~text
S[a..a+d) == S[b..b+d)
⇔ LCE(a,b) >= d.
~~~

Điều kiện cần là **cả hai đoạn hợp lệ**, tức a+d≤n và b+d≤n.

Ví dụ:

~~~text
S = "banana".
a=1, b=3, d=3.

S[1..4)="ana".
S[3..6)="ana".
LCE(1,3)=3>=3.
=> true.
~~~

Nếu d=4 cho b=3 thì đoạn [3,7) vượt độ dài n=6, vì vậy **input không hợp lệ**, chứ không phải trả false do không khớp.

Với d=0, cả hai đoạn rỗng nên luôn bằng nhau nếu vị trí hợp lệ. Trên API, d=0 được cho phép kể cả a=n hay b=n. Kiểu truy vấn này đặc biệt hữu ích trong những bài toán cần so hai substring nhiều lần mà vẫn muốn **kết quả chính xác**, không phụ thuộc xác suất va chạm như rolling hash.

## 18. Ứng dụng: substring lặp dài nhất

Một substring xuất hiện **ít nhất hai lần** khi tồn tại hai hậu tố có chung một tiền tố bằng substring đó. Vì mọi cặp suffix có chung prefix dài k sẽ có một cặp suffix kề nhau trong đoạn rank liên quan có LCP≥k, độ dài substring lặp dài nhất bằng:

~~~text
max(LCP[r]) với r=1..n-1.
~~~

Nếu n<2 hoặc mọi LCP bằng 0, không có substring không rỗng nào lặp lại; hàm demo trả chuỗi rỗng.

Với "banana":

~~~text
LCP = [0,1,3,0,0,2].
max=3.
Longest repeated substring = "ana".
Nó có ở vị trí 1 và 3.
~~~

Hai lần xuất hiện **được phép chồng lấn**. Chẳng hạn "aaaaa" có substring "aaaa" xuất hiện ở vị trí 0 và 1; đó là hai occurrence hợp lệ theo định nghĩa này dù chúng chia sẻ ký tự.

Nếu bài yêu cầu hai occurrence **không chồng lấn**, lấy max LCP là **chưa đủ**; phải thêm điều kiện về khoảng cách hai vị trí và thường cần phương pháp khác, chẳng hạn tìm kiếm nhị phân độ dài kết hợp kiểm tra vị trí suffix. Không áp dụng công thức trên sai phạm vi.

## 19. Ứng dụng: đếm các substring phân biệt

Chuỗi độ dài n có tổng cộng n(n+1)/2 đoạn con **không rỗng** khi tính cả trùng nội dung: với độ dài 1 có n đoạn, độ dài 2 có n−1 đoạn,..., độ dài n có 1 đoạn.

Sau khi sắp suffix, suffix SA[r] có độ dài n−SA[r], tạo ra ngần ấy prefix (tức substring bắt đầu tại vị trí SA[r]). Tuy nhiên **LCP[r] prefix đầu tiên** của suffix này đã xuất hiện như prefix của suffix đứng trước trong thứ tự từ điển.

Vậy số substring **mới** do suffix SA[r] đóng góp là:

~~~text
(n - SA[r]) - LCP[r].
~~~

Cộng mọi suffix:

~~~text
DistinctNonemptySubstrings
    = n(n+1)/2 - Σ LCP[r], r=0..n-1.
~~~

Với "banana": n=6, tổng tất cả substring có vị trí là 6·7/2=21. Tổng LCP=0+1+3+0+0+2=6, nên số **substring có nội dung phân biệt** bằng 21−6=15.

Cần dùng kiểu **long** cho n(n+1)/2 vì kết quả có thể vượt int khi n đủ lớn. Mã ép (long)n trước phép nhân.

## 20. Chứng minh công thức đếm không đếm trùng nhiều lần

Tại rank r, xét những prefix của suffix SA[r] theo chiều dài tăng dần 1,2,...,n−SA[r]. Các substring có tiền tố dài ≤LCP[r] trùng với các prefix của suffix ngay trước; vì suffix được sắp theo từ điển, mọi substring đã xuất hiện trong những suffix ở rank <r mà là prefix của suffix hiện tại sẽ có mặt trong **suffix kề trước** ít nhất đến chiều dài ấy.

Nếu tồn tại suffix rank q<r có tiền tố chung với suffix r dài k, định lý RMQ cho:

~~~text
LCE(SA[q],SA[r])
    = min(LCP[q+1..r])
    <= LCP[r].
~~~

Vậy không suffix đứng trước nào có thể chia sẻ **nhiều ký tự đầu hơn LCP[r]** với suffix hiện tại. Tất cả prefix dài hơn LCP[r] là nội dung mới, còn toàn bộ prefix ngắn hơn hoặc bằng độ dài ấy đã được đếm.

Do đó đóng góp mới chính xác bằng (n−SA[r])−LCP[r], không chỉ là một phép trừ đoán mò. Chứng minh dựa trực tiếp vào tính chất **LCE của cặp bất kỳ là cực tiểu trên đoạn LCP**, liên hệ hai ứng dụng quan trọng của bài.

## 21. Độ phức tạp của toàn bộ pipeline

Gọi n là số **đơn vị UTF-16** của văn bản cố định và Q là số truy vấn.

| Thành phần | Thời gian | Bộ nhớ bổ sung |
| --- | --- | --- |
| SA doubling + Arrays.sort comparator | O(n log² n) | O(n) cho các lớp, chỉ số và sort |
| Rank đảo | O(n) | O(n) |
| Kasai adjacent LCP | O(n) | O(n) |
| Sparse table RMQ | O(n log n) | O(n log n) |
| Một LCE(i,j) | **O(1)** | O(1) ngoài dữ liệu đã lưu |
| Một common-prefix hai đoạn hữu hạn | **O(1)** | O(1) |
| So hai đoạn cùng độ dài bằng nhau | **O(1)** | O(1) |
| Đếm substring phân biệt | O(n) khi duyệt LCP | O(1) |
| Tìm substring lặp dài nhất | O(n) quét LCP, thêm chi phí tạo String | O(1) ngoài kết quả |

Vì vậy tổng tiền xử lý của **chương trình giáo khoa này** là O(n log² n), bộ nhớ O(n log n), còn Q truy vấn LCE tốn **O(Q)** sau tiền xử lý. Không nên tuyên bố toàn pipeline là O(n log n) nếu phần SA vẫn dùng sort comparator O(n log n) **mỗi vòng**.

Nếu Q rất nhỏ, xây sparse table O(n log n) có thể không đáng; dùng segment tree O(n) build và O(log n) query, hoặc thậm chí so trực tiếp cho bài nhỏ, có thể tiết kiệm thời gian thực và bộ nhớ.

Nếu n lớn và Q lớn, mảng hậu tố/ LCP/ RMQ trở thành một chỉ mục hữu ích. Tuy nhiên O(n log n) **số nguyên** cho sparse table có thể chiếm nhiều RAM; khi cần bộ nhớ chặt hơn nên cân nhắc RMQ tuyến tính hoặc các cấu trúc chuyên dụng.

## 22. Chi tiết Java và quy ước Unicode

Java String lưu văn bản bằng chuỗi **đơn vị UTF-16**; String.length và charAt đều làm việc ở cấp **char**. Vì vậy SA và rank cũng đánh số bằng offset UTF-16. Một ký tự hiển thị như emoji 😊 thường chiếm **hai** char (surrogate pair), nên một suffix có thể bắt đầu tại **nửa sau** của cặp surrogate. Điều này hợp lệ theo mô hình chuỗi char của mã, nhưng không phải mô hình “mỗi đỉnh là một Unicode code point” trong một ứng dụng xử lý ngôn ngữ tự nhiên.

Ví dụ:

~~~text
S = "A😊B😊".
Các offset UTF-16: 
A ở 0; emoji thứ nhất bắt đầu 1 (chiếm 1,2);
B ở 3; emoji thứ hai bắt đầu 4 (chiếm 4,5).

LCE(1,4)=2 đơn vị UTF-16.
~~~

Nếu cần chỉ số code point/grapheme, hãy chuyển văn bản thành mảng Unicode code point và dùng phép so của loại phần tử đó, rồi duy trì ánh xạ offset về String gốc nếu cần. Không nên lấy kết quả LCE theo UTF-16 và gọi nó là số **ký tự người dùng nhìn thấy**.

Các chuỗi hiển thị giống nhau do **Unicode normalization** khác nhau (ví dụ ký tự é dựng sẵn so với e + dấu tổ hợp) không bắt buộc có chung các đơn vị UTF-16. Nếu bài yêu cầu so theo dạng chuẩn hóa, phải **chuẩn hóa trước khi xây index**, nêu cách diễn giải offset sau chuẩn hóa, và tái xây index khi văn bản thay đổi.

## 23. Java 17+: chương trình hoàn chỉnh

Lưu mã dưới đây vào file **SuffixLcpRmq.java** và chạy với **JDK 17+**. Chương trình thực hiện:

1. **buildSuffixArray:** doubling và Arrays.sort theo hai lớp rank của các đoạn dài d.
2. **buildKasaiLcp:** xây LCP[r] giữa SA[r−1] và SA[r] trong O(n).
3. **Sparse table min:** tiền xử lý RMQ trên mảng LCP cố định; không có cập nhật.
4. **lce(i,j):** tra rank, lấy RMQ của LCP từ low+1 tới high, xử lý i=j và suffix rỗng.
5. **commonPrefixOfSegments:** trả min(LCE,lenA,lenB), sau khi xác nhận hai đoạn nằm trong chuỗi.
6. **equalSegments:** kiểm tra LCE≥len cho hai đoạn cùng độ dài, gồm đoạn rỗng.
7. **countDistinctNonemptySubstrings:** công thức n(n+1)/2−ΣLCP bằng long.
8. **longestRepeatedSubstring:** chọn một cặp suffix kề có LCP lớn nhất rồi lấy substring tương ứng.
9. **Bộ QA:** so với các oracle độc lập: sắp suffix bằng String.substring().compareTo(), so LCP từng ký tự, đếm distinct bằng HashSet substring, và tìm độ dài lặp lớn nhất bằng thử mọi cặp vị trí.

**Hợp đồng input:** constructor chỉ nhận String không null; vị trí query i,j trong **[0,n]**, với vị trí n đại diện suffix rỗng và không thuộc SA; độ dài đoạn không âm, không vượt n−vị trí. Không hỗ trợ chỉnh sửa S sau khi xây. Mảng SA và LCP trả qua bản sao để người gọi không vô tình thay đổi trạng thái index.

**Mô hình trùng lặp:** longestRepeatedSubstring cho phép occurrence chồng lấn. Nếu không có nội dung lặp không rỗng, trả ""; nếu text rỗng, SA/LCP rỗng và lce(0,0)=0. Mã thực thi chính xác trên các **đơn vị UTF-16**, gồm cả chuỗi có emoji và dấu tổ hợp.

~~~java
import java.util.*;

public final class SuffixLcpRmq {
    private final String text;
    private final int n;
    private final int[] suffixArray;
    private final int[] rank;
    private final int[] lcp;
    private final int[] log2;
    private final int[][] sparseMin;

    public SuffixLcpRmq(String text) {
        if (text == null) throw new IllegalArgumentException("null text");
        this.text = text;
        this.n = text.length();
        suffixArray = buildSuffixArray();
        rank = new int[n];
        for (int r = 0; r < n; r++) rank[suffixArray[r]] = r;
        lcp = buildKasaiLcp();
        log2 = new int[n + 1];
        for (int i = 2; i <= n; i++) log2[i] = log2[i / 2] + 1;
        int levels = n == 0 ? 0 : log2[n] + 1;
        sparseMin = new int[levels][];
        if (n > 0) {
            sparseMin[0] = lcp.clone();
            for (int k = 1; k < levels; k++) {
                int length = 1 << k;
                sparseMin[k] = new int[n - length + 1];
                for (int i = 0; i + length <= n; i++) {
                    sparseMin[k][i] = Math.min(
                        sparseMin[k - 1][i],
                        sparseMin[k - 1][i + (length >> 1)]);
                }
            }
        }
    }

    private static int comparePair(int a, int b,
                                   int[] rank, int gap, int n) {
        int first = Integer.compare(rank[a], rank[b]);
        if (first != 0) return first;
        int nextA = a + gap < n ? rank[a + gap] : -1;
        int nextB = b + gap < n ? rank[b + gap] : -1;
        return Integer.compare(nextA, nextB);
    }

    private int[] buildSuffixArray() {
        if (n == 0) return new int[0];
        Integer[] order = new Integer[n];
        int[] classes = new int[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
            classes[i] = text.charAt(i);
        }
        for (int gap = 1; gap < n; gap <<= 1) {
            final int d = gap;
            final int[] current = classes;
            Arrays.sort(order,
                (a, b) -> comparePair(a, b, current, d, n));
            int[] next = new int[n];
            next[order[0]] = 0;
            for (int i = 1; i < n; i++) {
                next[order[i]] = next[order[i - 1]] +
                    (comparePair(order[i - 1], order[i],
                                 current, d, n) == 0 ? 0 : 1);
            }
            classes = next;
            if (classes[order[n - 1]] == n - 1) break;
        }
        int[] result = new int[n];
        for (int i = 0; i < n; i++) result[i] = order[i];
        return result;
    }

    private int[] buildKasaiLcp() {
        int[] adjacent = new int[n];
        int matched = 0;
        for (int position = 0; position < n; position++) {
            int r = rank[position];
            if (r == 0) {
                matched = 0;
                continue;
            }
            int previous = suffixArray[r - 1];
            while (position + matched < n && previous + matched < n
                   && text.charAt(position + matched)
                   == text.charAt(previous + matched)) {
                matched++;
            }
            adjacent[r] = matched;
            if (matched > 0) matched--;
        }
        return adjacent;
    }

    public int[] suffixArray() { return suffixArray.clone(); }
    public int[] adjacentLcp() { return lcp.clone(); }

    private void checkPosition(int position) {
        if (position < 0 || position > n) {
            throw new IllegalArgumentException("position outside [0,n]");
        }
    }

    private void checkSegment(int position, int length) {
        checkPosition(position);
        if (length < 0 || length > n - position) {
            throw new IllegalArgumentException("invalid segment");
        }
    }

    private int rangeMinimum(int left, int right) {
        int width = right - left + 1;
        int k = log2[width];
        int block = 1 << k;
        return Math.min(sparseMin[k][left],
                        sparseMin[k][right - block + 1]);
    }

    public int lce(int positionA, int positionB) {
        checkPosition(positionA);
        checkPosition(positionB);
        if (positionA == positionB) return n - positionA;
        if (positionA == n || positionB == n) return 0;
        int a = rank[positionA], b = rank[positionB];
        int low = Math.min(a, b);
        int high = Math.max(a, b);
        return rangeMinimum(low + 1, high);
    }

    public int commonPrefixOfSegments(int a, int lengthA,
                                      int b, int lengthB) {
        checkSegment(a, lengthA);
        checkSegment(b, lengthB);
        return Math.min(lce(a, b), Math.min(lengthA, lengthB));
    }

    public boolean equalSegments(int a, int b, int length) {
        checkSegment(a, length);
        checkSegment(b, length);
        return lce(a, b) >= length;
    }

    public long countDistinctNonemptySubstrings() {
        long count = (long) n * (n + 1) / 2;
        for (int value : lcp) count -= value;
        return count;
    }

    public String longestRepeatedSubstring() {
        int bestLength = 0, bestStart = 0;
        for (int r = 1; r < n; r++) {
            if (lcp[r] > bestLength) {
                bestLength = lcp[r];
                bestStart = suffixArray[r];
            }
        }
        return text.substring(bestStart, bestStart + bestLength);
    }

    private static int naiveLcp(String text, int a, int b) {
        int common = 0;
        while (a + common < text.length()
                && b + common < text.length()
                && text.charAt(a + common) == text.charAt(b + common)) {
            common++;
        }
        return common;
    }

    private static int[] naiveSuffixArray(String text) {
        Integer[] positions = new Integer[text.length()];
        for (int i = 0; i < positions.length; i++) positions[i] = i;
        Arrays.sort(positions, (a, b) ->
            text.substring(a).compareTo(text.substring(b)));
        int[] result = new int[positions.length];
        for (int i = 0; i < result.length; i++) result[i] = positions[i];
        return result;
    }

    private static long naiveDistinctCount(String text) {
        Set<String> pieces = new HashSet<>();
        for (int i = 0; i < text.length(); i++) {
            for (int j = i + 1; j <= text.length(); j++) {
                pieces.add(text.substring(i, j));
            }
        }
        return pieces.size();
    }

    private static int naiveMaxRepeatLength(String text) {
        int best = 0;
        for (int i = 0; i < text.length(); i++) {
            for (int j = i + 1; j < text.length(); j++) {
                best = Math.max(best, naiveLcp(text, i, j));
            }
        }
        return best;
    }

    private static void check(String text) {
        SuffixLcpRmq index = new SuffixLcpRmq(text);
        int n = text.length();
        int[] sa = index.suffixArray();
        int[] adjacent = index.adjacentLcp();
        if (!Arrays.equals(sa, naiveSuffixArray(text))) {
            throw new AssertionError("suffix array order incorrect");
        }
        if (n > 0 && adjacent[0] != 0) {
            throw new AssertionError("lcp[0] must be zero");
        }
        for (int r = 1; r < n; r++) {
            if (adjacent[r] != naiveLcp(text, sa[r - 1], sa[r])) {
                throw new AssertionError("adjacent LCP incorrect");
            }
        }
        for (int a = 0; a <= n; a++) {
            for (int b = 0; b <= n; b++) {
                int correct = naiveLcp(text, a, b);
                if (index.lce(a, b) != correct ||
                    index.commonPrefixOfSegments(a, n-a, b, n-b)
                        != correct) {
                    throw new AssertionError("RMQ LCE incorrect");
                }
                int testLength = Math.min(2, Math.min(n-a, n-b));
                if (index.equalSegments(a, b, testLength)
                    != (correct >= testLength)) {
                    throw new AssertionError("segment equality incorrect");
                }
            }
        }
        if (index.countDistinctNonemptySubstrings()
                    != naiveDistinctCount(text)) {
            throw new AssertionError("distinct substring count incorrect");
        }
        String repeated = index.longestRepeatedSubstring();
        if (repeated.length() != naiveMaxRepeatLength(text)) {
            throw new AssertionError("longest repeated length incorrect");
        }
        if (!repeated.isEmpty()) {
            int first = text.indexOf(repeated);
            int second = text.indexOf(repeated, first + 1);
            if (first < 0 || second < 0) {
                throw new AssertionError("repeated witness incorrect");
            }
        }
        if (n > 0) {
            int original = sa[0];
            sa[0] = -100;
            if (index.suffixArray()[0] != original) {
                throw new AssertionError("suffix array leaked internal state");
            }
        }
    }

    private static String ternaryWord(int mask, int n) {
        char[] result = new char[n];
        for (int i = 0; i < n; i++) {
            result[i] = (char) ('a' + mask % 3);
            mask /= 3;
        }
        return new String(result);
    }

    private static void expectInvalid(Runnable call) {
        try {
            call.run();
        } catch (IllegalArgumentException correct) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        int exhaustive = 0;
        for (int n = 0; n <= 8; n++) {
            int count = 1;
            for (int i = 0; i < n; i++) count *= 3;
            for (int mask = 0; mask < count; mask++) {
                check(ternaryWord(mask, n));
                exhaustive++;
            }
        }

        Random rng = new Random(3832026L);
        char[] alphabet = {'a','b','X','é','0'};
        int seeded = 0;
        for (int trial = 0; trial < 800; trial++) {
            int n = rng.nextInt(36);
            StringBuilder s = new StringBuilder(n);
            for (int k = 0; k < n; k++) {
                s.append(alphabet[rng.nextInt(alphabet.length)]);
            }
            check(s.toString());
            seeded++;
        }

        check("banana");
        check("mississippi");
        check("aaaaa");
        check("A\uD83D\uDE0AB\uD83D\uDE0A");
        check("e\u0301e\u0301");
        check("\uD83D\uDE0A\uD83D\uDE0A");

        SuffixLcpRmq repeated = new SuffixLcpRmq("a".repeat(5000));
        if (repeated.lce(0, 1) != 4999 ||
            repeated.countDistinctNonemptySubstrings() != 5000 ||
            repeated.longestRepeatedSubstring().length() != 4999) {
            throw new AssertionError("long repeated stress failed");
        }

        expectInvalid(() -> new SuffixLcpRmq(null));
        SuffixLcpRmq one = new SuffixLcpRmq("abc");
        expectInvalid(() -> one.lce(-1, 0));
        expectInvalid(() -> one.lce(0, 4));
        expectInvalid(() -> one.commonPrefixOfSegments(1, 3, 0, 0));
        expectInvalid(() -> one.commonPrefixOfSegments(0, -1, 0, 1));
        expectInvalid(() -> one.equalSegments(0, 2, 2));
        expectInvalid(() -> one.equalSegments(0, 3, -1));

        System.out.println("Exhaustive ternary strings: " +
                           exhaustive + " PASS");
        System.out.println("Seeded UTF-16 strings: " + seeded + " PASS");
        System.out.println("Long repeated string n=5000: PASS");
        System.out.println("Unicode and invalid-index checks: PASS");
    }

    public static void main(String[] args) {
        SuffixLcpRmq banana = new SuffixLcpRmq("banana");
        System.out.println("banana SA: " +
                           Arrays.toString(banana.suffixArray()));
        System.out.println("banana LCP: " +
                           Arrays.toString(banana.adjacentLcp()));
        System.out.println("banana LCE(1,3): " + banana.lce(1, 3));
        System.out.println("banana common[1,5),[3,6): " +
                           banana.commonPrefixOfSegments(1, 4, 3, 3));
        System.out.println("banana equal[1,4),[3,6): " +
                           banana.equalSegments(1, 3, 3));
        System.out.println("banana distinct substrings: " +
                           banana.countDistinctNonemptySubstrings());
        System.out.println("banana longest repeat: " +
                           banana.longestRepeatedSubstring());
        SuffixLcpRmq repeated = new SuffixLcpRmq("aaaaa");
        System.out.println("aaaaa LCE(0,1): " + repeated.lce(0, 1));
        System.out.println("aaaaa distinct: " +
                           repeated.countDistinctNonemptySubstrings());
        System.out.println("empty LCE(0,0): " +
                           new SuffixLcpRmq("").lce(0, 0));
        SuffixLcpRmq emoji = new SuffixLcpRmq(
                "A\uD83D\uDE0AB\uD83D\uDE0A");
        System.out.println("emoji UTF-16 LCE(1,4): " + emoji.lce(1, 4));
        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SuffixLcpRmq.java
java SuffixLcpRmq
~~~

**Stdout chính xác quan sát được từ chương trình Java:**

~~~text
banana SA: [5, 3, 1, 0, 4, 2]
banana LCP: [0, 1, 3, 0, 0, 2]
banana LCE(1,3): 3
banana common[1,5),[3,6): 3
banana equal[1,4),[3,6): true
banana distinct substrings: 15
banana longest repeat: ana
aaaaa LCE(0,1): 4
aaaaa distinct: 5
empty LCE(0,0): 0
emoji UTF-16 LCE(1,4): 2
Exhaustive ternary strings: 9841 PASS
Seeded UTF-16 strings: 800 PASS
Long repeated string n=5000: PASS
Unicode and invalid-index checks: PASS
~~~

Chú ý dòng SA/LCP của "banana" cùng các truy vấn LCE, common-prefix đoạn hữu hạn, equality, distinct count và longest repeat. Các dòng PASS cuối là kết quả so sánh với oracle trên hàng nghìn chuỗi, không chỉ một bản in giá trị mẫu.

## 24. Bộ kiểm thử độc lập và vét cạn

Để phát hiện lỗi chỉ số, Kasai và sparse table, chương trình **không** so một phiên bản RMQ khác của cùng bảng rồi kết luận đúng. Nó so với các hàm **brute force dùng trực tiếp chuỗi gốc**:

- **SA oracle:** sắp các vị trí theo phép String.substring(i).compareTo(String.substring(j)).
- **LCP oracle:** so hai suffix từng đơn vị char cho tới mismatch hoặc hết chuỗi.
- **Distinct oracle:** duyệt tất cả substring không rỗng, đưa vào HashSet, đếm số phần tử khác nhau.
- **Longest repeat oracle:** so tất cả cặp vị trí i<j, lấy max của naive LCP.
- **Path/segment:** với mọi cặp i,j hợp lệ, kiểm tra lce và commonPrefixOfSegments với đoạn dài tới cuối chuỗi; kiểm tra equality cho một độ dài nhỏ hợp lệ.
- **Biên:** kiểm tra bản sao SA không bị sửa từ bên ngoài; vị trí âm, vị trí vượt n, đoạn dài quá cuối, độ dài âm phải bị từ chối.

Sinh tất cả chuỗi trên bảng chữ cái {a,b,c}, với độ dài n=0..8:

~~~text
Số chuỗi = Σ 3^n với n từ 0 tới 8
         = (3^9-1)/(3-1)
         = (19683-1)/2
         = 9841.
~~~

Mỗi chuỗi được kiểm tra toàn bộ cặp vị trí [0,n]×[0,n], nên bao phủ i=j, một vị trí là n, suffix kề rank, suffix xa nhau và chuỗi rỗng. Tập vét cạn gồm chuỗi toàn một ký tự, chuỗi xen kẽ, không có ký tự trùng, và cấu trúc lặp nhiều cấp.

## 25. Bộ thử có seed và dữ liệu biên

Chương trình dùng **Random(3832026L)** tạo 800 chuỗi độ dài 0..35 trên bảng ký tự {'a','b','X','é','0'}. Với mỗi chuỗi, lặp lại toàn bộ phép so với oracle như trên, không dựa vào kết quả một lần chạy của chính index để làm đáp án tham chiếu.

Các trường hợp bổ sung:

- "banana": SA, LCP, LCE, substring trùng và số substring phân biệt.
- "mississippi": nhiều hậu tố có tiền tố chung.
- "aaaaa": LCE(0,1)=4, count distinct=5, substring lặp dài nhất được phép chồng lấn.
- "A😊B😊": hai suffix ở offset UTF-16 1 và 4 khớp dài 2 đơn vị.
- "e" kết hợp dấu Unicode: kiểm tra quy ước char thay vì tự chuẩn hóa.
- Chuỗi emoji lặp.
- **"a" lặp 5.000 lần:** LCE(0,1)=4.999, số substring phân biệt=5.000, độ dài substring lặp lớn nhất=4.999.
- Constructor null, vị trí ngoài [0,n], đoạn vượt cuối và độ dài âm đều bị từ chối.

Kết quả test được in nguyên văn trong stdout. Dù kiểm thử 9.841+800 chuỗi có thể phát hiện lỗi tinh vi trong SA/Kasai/RMQ, tính đúng tổng quát vẫn dựa vào **chứng minh** về thứ tự suffix, Kasai và cực tiểu trên đoạn, không phải chỉ dựa vào số lượng mẫu PASS.

## 26. Những lỗi dễ gặp và cách phòng tránh

1. **Nhầm suffix array với mảng vị trí theo thứ tự văn bản:** SA sắp suffix theo nội dung, không sắp index tăng dần.
2. **Không tạo rank ngược:** phải tra rank[i] và rank[j] trước khi tìm đoạn trên LCP.
3. **Dùng mảng LCP theo quy ước sai:** LCP[r] ở đây nối SA[r−1] với SA[r], LCP[0]=0.
4. **Lấy RMQ trên [low,high−1]** thay vì [low+1,high] với đúng quy ước vừa nêu.
5. **Lấy maximum LCP trong đoạn rank** thay vì minimum; công thức cốt lõi là **cực tiểu**.
6. **Không xử lý i=j:** lce(i,i)=n−i, không được truy vấn đoạn RMQ rỗng.
7. **Lấy prefix chung của hai đoạn hữu hạn bằng LCE trực tiếp:** phải chặn thêm lenA và lenB.
8. **Không kiểm tra đoạn nằm trong chuỗi** trước khi trả equalSegments, làm truy cập vượt n.
9. **Dùng prefix minimum rồi trừ hai đầu** như prefix sum; phép min không có phép trừ như vậy.
10. **Dùng hai khối sparse table chồng nhau cho phép sum** mà không bù trừ, đếm lặp vùng giao.
11. **Không dùng sentinel nhỏ hơn mọi ký tự thật** trong doubling, sắp suffix ngắn sai vị trí.
12. **Comparator so rank[] đang bị thay đổi trong lúc sort:** cần chụp biến currentRank ổn định cho mỗi vòng.
13. **Quên nén lớp sau từng vòng doubling**, khiến lớp cũ không phản ánh thứ tự đoạn 2d.
14. **Quên đặt h=0 khi rank[i]=0** trong Kasai.
15. **Không giảm h tối đa 1 ở cuối vòng Kasai**, có thể làm sai LCP và phá cận tuyến tính.
16. **Dùng int cho n(n+1)/2** trong distinct count dù kết quả lớn.
17. **Tính longest repeat bằng max LCP mà khẳng định hai occurrence không chồng lấn**; định nghĩa trong bài cho phép overlap.
18. **Không hỗ trợ chuỗi rỗng/suffix rỗng theo hợp đồng**; truy cập sparse[0] khi n=0.
19. **Nhầm offset UTF-16 với code point hay grapheme**, nhất là emoji và dấu tổ hợp.
20. **Cho rằng normalize Unicode không ảnh hưởng vị trí**, trong khi chuẩn hóa có thể đổi độ dài char.
21. **Cập nhật S nhưng giữ nguyên SA/LCP/RMQ**, làm mọi truy vấn về sau không còn đáng tin.
22. **Gọi String.substring để so trực tiếp trong mỗi query** dù đã xây index; đó là bỏ qua lợi ích O(1).
23. **Báo O(n log n) cho SA dùng Arrays.sort comparator mỗi vòng**, bỏ mất một nhân tử log n.
24. **Không thử chuỗi toàn ký tự trùng**, nơi adjacent LCP dài và index dễ sai.
25. **Kiểm tra chỉ SA mà không so mọi cặp LCE với oracle**; lỗi RMQ có thể tồn tại dù SA đúng.
26. **Coi trả về một substring lặp dài nhất là duy nhất**; có thể có nhiều chuỗi khác nhau cùng độ dài tối ưu.

## 27. Bài tập tự luyện

**Bài 1:** Với S="banana", tự sắp sáu hậu tố, viết SA và rank. Đối chiếu SA=[5,3,1,0,4,2].

**Bài 2:** Tính LCP[r] cho từng cặp suffix kề nhau, dùng quy ước LCP[0]=0. Kiểm tra [0,1,3,0,0,2].

**Bài 3:** Dùng rank và RMQ trả LCE(1,3), LCE(1,5), LCE(2,4), LCE(0,0). Giải thích tại sao truy vấn cuối không dùng RMQ.

**Bài 4:** Với hai đoạn [1,5) và [3,6) của "banana", tính tiền tố chung dài nhất. Thử rút ngắn đoạn đầu thành [1,3) để thấy công thức min(LCE,lenA,lenB).

**Bài 5:** Kiểm tra S[1..4) và S[3..6) bằng nhau bằng cách dùng LCE≥3. Nêu điều kiện input nếu độ dài yêu cầu vượt cuối văn bản.

**Bài 6:** Xây sparse table cho LCP "banana" ở mức k=0,1,2. Thử RMQ(1,2) bằng hai khối dài 2; thử RMQ(1,3) bằng hai khối dài 2 có chồng lấn.

**Bài 7:** Chứng minh lại định lý LCE(SA[a],SA[b])=min LCP[a+1..b] bằng tính chất khoảng liên tiếp của các chuỗi có cùng prefix trong thứ tự từ điển.

**Bài 8:** Với "aaaaa", tính SA, LCP, LCE(0,1), số substring phân biệt và substring lặp dài nhất. Giải thích các occurrence chồng lấn.

**Bài 9:** Từ công thức n(n+1)/2−ΣLCP, tự tính distinct substring count của "banana" là 15. Chứng minh vì sao LCP[r] chính là số prefix bị trùng với các suffix đứng trước.

**Bài 10:** Đổi sparse table sang segment tree RMQ. So O(n) build/O(log n) query với sparse O(n log n) build/O(1) query khi số truy vấn Q nhỏ và rất lớn.

**Bài 11:** Viết oracle naiveLcp so char từng ký tự, sinh mọi chuỗi trên {a,b,c} với n≤8 và thử tất cả cặp vị trí. So với SA+Kasai+RMQ.

**Bài 12:** Giải thích chỉ số UTF-16 cho "A😊B😊", so suffix tại offset 1 và 4. Nếu ứng dụng yêu cầu code-point positions, nêu bước cần thay đổi khi tạo index.

**Bài 13:** Xây SA bằng doubling dùng counting sort theo hai lớp rank để cải thiện từ O(n log² n) về O(n log n). Giữ nguyên Kasai và sparse table rồi so toàn bộ đáp án cũ.

**Bài 14:** Thiết kế một hệ thống nhiều truy vấn so sánh substring; nêu rõ chuỗi có được cập nhật không, ký tự tính theo UTF-16 hay code point, và ngưỡng bộ nhớ cho sparse table. Chỉ sau đó mới chọn kiến trúc.

**Kết luận:** Để trả lời **tiền tố chung dài nhất của hai hậu tố bất kỳ**, ta không cần so từng ký tự cho mỗi truy vấn. Hãy sắp suffix bằng **SA**, xây **rank**, tính **LCP của hai suffix kề nhau** bằng Kasai, rồi dùng định lý **LCE(i,j)=RMQ-min của LCP giữa hai rank**. Với sparse table, một truy vấn chỉ cần O(1). Cho đoạn hữu hạn, chặn kết quả bởi hai độ dài; để so hai đoạn bằng nhau, kiểm tra LCE≥len. Cùng nền tảng ấy còn tính được substring lặp dài nhất và số substring phân biệt. Các quy ước **inclusive/nửa mở**, suffix rỗng và **UTF-16 offsets** cần được ghi rõ để tránh sai dù công thức cốt lõi đúng.
