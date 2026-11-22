# Sparse table cho truy vấn tĩnh với phép toán phù hợp

**Chủ đề:** Computer Science Algorithms · Truy vấn và ngoại tuyến

## 1. Bài toán: một mảng không đổi, rất nhiều câu hỏi về đoạn

Cho một mảng \(a[0..n-1]\). Sau khi xây cấu trúc dữ liệu, cần trả lời nhiều truy vấn trên **đoạn liên tiếp** \(a[l..r]\), với chỉ số **0-based, hai đầu đều bao gồm**.

Một số ví dụ:

- **Range Minimum Query (RMQ):** giá trị nhỏ nhất trên đoạn.
- **Range Maximum Query:** giá trị lớn nhất trên đoạn.
- **Range GCD Query:** ước chung lớn nhất của các phần tử.
- **Range Bitwise AND/OR:** kết hợp bit của mọi phần tử.
- **Range Sum/XOR:** tổng hoặc XOR của mọi phần tử.

Nếu mỗi truy vấn đều duyệt từ l đến r thì chi phí là O(r−l+1), xấu nhất **O(n)**. Khi mảng không đổi và số truy vấn Q lớn, tổng chi phí có thể gần **O(nQ)**.

**Sparse table** dùng tiền xử lý các đoạn có chiều dài là lũy thừa của 2. Với các phép toán phù hợp, nó giúp mỗi truy vấn lấy đáp án trong **O(1)** sau **O(n log n)** tiền xử lý và bộ nhớ.

Tuy nhiên điều kiện **“phép toán phù hợp” rất quan trọng**:

- Phép **kết hợp được (associative)** cho phép gộp những đoạn liên tiếp mà không phụ thuộc cách đặt ngoặc.
- Phép **lũy đẳng (idempotent)** cho phép một phần dữ liệu bị lấy lặp mà không làm đổi kết quả.
- Truy vấn O(1) bằng **hai khối chồng lấn** của sparse table cổ điển đòi điều kiện phù hợp, điển hình là **associative + idempotent**.
- Với **sum/XOR**, hai khối chồng lấn có thể đếm phần tử nhiều lần, nên cách truy vấn ấy **sai**. Vẫn có thể dùng bảng lũy thừa 2 với phân rã thành các khối **không giao nhau** trong O(log n), hoặc dùng **disjoint sparse table** cho phép kết hợp associative với truy vấn O(1).

Bài học triển khai cả ba hướng, nêu chứng minh đúng và một chương trình **Java 17 hoàn chỉnh**.

## 2. Phép toán nào tương thích?

Giả sử muốn tính:

\[
a[l]\circ a[l+1]\circ\cdots\circ a[r].
\]

Để việc kết hợp những đoạn con có nghĩa, phép \(\circ\) cần có **tính kết hợp**:

\[
(x\circ y)\circ z=x\circ(y\circ z).
\]

Khi đó ta có thể xây sẵn kết quả cho một nửa đoạn và gộp với kết quả nửa còn lại.

### 2.1. Tính lũy đẳng

Một phép \(\circ\) là **idempotent** khi:

\[
\boxed{x\circ x=x}
\]

với mọi giá trị kết quả trung gian thuộc miền đã chọn.

Ví dụ:
- min(x,x)=x.
- max(x,x)=x.
- gcd(x,x)=x với gcd được chuẩn hóa thành số không âm.
- x AND x=x.
- x OR x=x.

Phép cộng không idempotent, vì thường x+x khác x. XOR không idempotent theo nghĩa trên, vì x XOR x=0. Phép nhân số nguyên cũng không idempotent trên toàn miền.

### 2.2. Bảng lựa chọn

| Phép toán | Associative? | Idempotent? | Hai khối chồng lấn O(1)? |
|---|---|---|---|
| Minimum | Có | Có | **Đúng** |
| Maximum | Có | Có | **Đúng** |
| GCD chuẩn hóa | Có | Có | **Đúng** |
| Bitwise AND | Có | Có | **Đúng** |
| Bitwise OR | Có | Có | **Đúng** |
| Sum số nguyên toán học | Có | Không | **Sai nếu khối trùng** |
| XOR | Có | Không | **Sai nếu khối trùng** |
| Product | Có | Không nói chung | **Sai nếu khối trùng** |
| Ghép chuỗi theo thứ tự | Có | Không nói chung | Không dùng hai khối chồng lấn |
| Phép trừ | **Không** | Không | Không xây/gộp theo công thức associative |
| Trung bình cộng của hai số | **Không** nói chung | Có với x=x | Không đủ điều kiện |

**Một điều kiện chưa đủ:** phép average(x,y)=(x+y)/2 có average(x,x)=x nhưng không associative; do đó không thể kết hợp những khoảng dài tùy ý theo cách này. Muốn tính average của đoạn, hãy lưu **(sum,count)** và chia sau; đó là một đối tượng kết hợp khác.

**Commutativity** (x◦y=y◦x) thường đúng với min/max/gcd/AND/OR, nhưng không phải điều kiện bắt buộc về mặt đại số cho chứng minh hai khối chồng lấn nếu phép đã **associative + idempotent** và ta giữ thứ tự kết hợp đúng. Chẳng hạn một phép trên các đối tượng có thứ tự có thể associative/idempotent nhưng không giao hoán. Khi triển khai, luôn tách bạch **tính kết hợp, tính lũy đẳng và tính giao hoán**.

### 2.3. Chi phí mỗi phép kết hợp

Các độ phức tạp O(1) của truy vấn giả định \(\circ\) tính trong **O(1)** trên mô hình dữ liệu. Ví dụ min của hai long là O(1) trên máy có word size phù hợp.

Nếu \(\circ\) là **ghép hai chuỗi và trả nguyên chuỗi**, số phép gộp có thể O(1), nhưng bản thân việc tạo chuỗi kết quả có chi phí theo **độ dài đầu ra**. Không được gọi toàn bộ truy vấn là O(1) theo thời gian vật lý trong trường hợp đó.

Với Java long và phép cộng toán học, cần chú ý **overflow**: bản demo dùng Math.addExact để không âm thầm tạo tổng sai. Nếu tổng thật vượt long, cần BigInteger hoặc điều kiện đầu vào đủ chặt.

## 3. Xây sparse table cổ điển

Định nghĩa:

\[
\boxed{st[k][i]=
a[i]\circ a[i+1]\circ\cdots\circ a[i+2^k-1]}.
\]

Nó lưu kết quả của đoạn bắt đầu ở i có chiều dài \(2^k\), chỉ khi đoạn còn nằm trong mảng.

Trường hợp cơ sở:

\[
st[0][i]=a[i].
\]

Bước chuyển:

\[
\boxed{
st[k][i]=
st[k-1][i]\circ st[k-1][i+2^{k-1}]
}.
\]

Hai nửa liên tiếp đều có độ dài \(2^{k-1}\), không chồng lấn. Vì vậy **xây bảng** cần phép associative, chưa cần idempotent.

### 3.1. Minh họa với mảng 8 phần tử

Xét:

~~~text
index   0  1  2  3  4  5  6  7
value   5  2  7  2  9  1  4  6
~~~

Với phép min:

- st[0] lưu từng giá trị.
- st[1][i] là min của các đoạn chiều dài 2.
- st[2][i] là min của các đoạn chiều dài 4.
- st[3][0] là min của cả 8 phần tử.

Bảng những ô hợp lệ:

| k | Độ dài 2^k | Kết quả của các đoạn có điểm bắt đầu hợp lệ |
|---:|---:|---|
| 0 | 1 | 5, 2, 7, 2, 9, 1, 4, 6 |
| 1 | 2 | 2, 2, 2, 2, 1, 1, 4 |
| 2 | 4 | 2, 2, 1, 1, 1 |
| 3 | 8 | 1 |

Ví dụ:
- st[1][2]=min(7,2)=2.
- st[2][2]=min(7,2,9,1)=1.
- st[3][0]=1.

Với n>0, số tầng là \(\lfloor\log_2 n\rfloor+1\). Mỗi tầng lưu tối đa n kết quả, nên:

\[
\boxed{\text{Tiền xử lý } O(n\log n),\quad\text{bộ nhớ }O(n\log n)}.
\]

Một cách cài đặt gọn chỉ cấp phát cho mỗi tầng \(n-2^k+1\) ô hợp lệ thay vì n ô. Bản Java chọn cách đó cho hai bảng cổ điển.

## 4. Truy vấn O(1) khi phép toán associative + idempotent

Cho đoạn truy vấn [l,r] có chiều dài:

\[
L=r-l+1.
\]

Chọn:

\[
k=\lfloor\log_2 L\rfloor,\qquad s=2^k.
\]

Do \(s\le L<2s\), hai đoạn có chiều dài s:

\[
A=[l,l+s-1],
\qquad
B=[r-s+1,r]
\]

**bao phủ toàn bộ [l,r]**, mặc dù chúng có thể **chồng lấn**. Khi phép idempotent, lặp dữ liệu không đổi kết quả.

Do đó:

\[
\boxed{
answer(l,r)=st[k][l]\circ st[k][r-s+1]
}.
\]

Chỉ cần **hai phép đọc bảng và một phép gộp**: O(1) mỗi truy vấn.

### 4.1. Chứng minh đúng chi tiết, không chỉ học thuộc công thức

Hai đoạn A và B bao phủ [l,r]. Gọi:
- P là đoạn chỉ nằm ở phía trái.
- T là **phần giao** của A và B.
- S là đoạn chỉ nằm ở phía phải.

Kết quả của A có dạng P◦T, kết quả của B có dạng T◦S; khi một phần rỗng, bỏ phần ấy trong biểu diễn.

Ghép hai kết quả theo thứ tự:

\[
(P\circ T)\circ(T\circ S)
=P\circ(T\circ T)\circ S.
\]

Tính **kết hợp** cho phép chuyển dấu ngoặc; tính **lũy đẳng** cho \(T\circ T=T\), trong đó T ở đây là **kết quả đã gộp** của phần giao.

Vậy:

\[
P\circ T\circ S
\]

chính là kết quả của đoạn [l,r].

**Hai điều kiện đều quan trọng:** tính kết hợp để xây/gộp đoạn; tính lũy đẳng để loại hiệu ứng tính lại phần giao.

### 4.2. Một đoạn độ dài đúng 2^k

Khi L=s, hai khối [l,l+s−1] và [r−s+1,r] **trùng nhau hoàn toàn**. Công thức trả \(x\circ x=x\). Điều này vẫn đúng với min/max/gcd nhưng làm tổng bị nhân đôi. Không được nghĩ “chỉ khi hai khối trùng một phần mới sai”; trùng **toàn bộ** cũng sai cho sum.

### 4.3. Truy vấn RMQ trong ví dụ

Với mảng [5,2,7,2,9,1,4,6]:
- min[0,7]=1.
- min[1,4]=2.
- min[2,5]=1.
- min[3,3]=2.
- min[5,7]=1.

Với [2,5], L=4 nên k=2, hai khối chiều dài 4 trùng nhau: min(st[2][2],st[2][2])=1, đúng.

Với [0,2], L=3, k=1, hai khối [0,1] và [1,2] cùng chứa chỉ số 1. min(min(5,2),min(2,7))=2 vẫn đúng do min idempotent.

## 5. Tiền xử lý log để truy vấn thật sự O(1)

Không cần tính log bằng hàm số thực mỗi query. Dùng mảng:

\[
lg[1]=0,\qquad
lg[i]=lg[\lfloor i/2\rfloor]+1\quad(i\ge2).
\]

Khi đó lg[i] bằng \(\lfloor\log_2 i\rfloor\) và được tính trong **O(n)** trước các truy vấn.

Ví dụ:

| i | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lg[i] | 0 | 1 | 1 | 2 | 2 | 2 | 2 | 3 |

Cần nhớ:
- L=r−l+1, **không phải r−l**.
- Không có truy vấn r<l trong API bài này.
- Không dùng lg[0] để đại diện một đoạn rỗng; code từ chối empty range.
- Một số triển khai lấy k bằng 31−Integer.numberOfLeadingZeros(L), cũng là O(1) trên int dương trong Java.

## 6. Vì sao không dùng hai khối chồng lấn cho SUM?

Xét đoạn:

~~~text
a[0..2] = [5, 2, 7]
True sum = 5 + 2 + 7 = 14
~~~

Chiều dài L=3, chọn k=1 nên mỗi khối có độ dài 2:
- Khối trái [0,1]: tổng 5+2=7.
- Khối phải [1,2]: tổng 2+7=9.

Nếu áp công thức RMQ:

\[
7+9=16
\]

thì phần tử a[1]=2 bị tính **hai lần**.

\[
\boxed{16\ne14}.
\]

Tình huống tương tự:
- XOR: phần tử chồng lấn bị XOR hai lần nên **bị triệt tiêu**.
- Product: các phần tử chồng lấn bị **nhân lặp**.
- Phép ghép chuỗi: phần nội dung giao được lặp lại.

Tính associative **chưa đủ** cho cách truy vấn bằng hai khối có giao. Đây là một lỗi thiết kế thường gặp khi đem code RMQ min đổi Math.min thành phép cộng mà không sửa phần query.

### 6.1. “Sum cũng dùng sparse table được không?”

**Có**, nhưng phải thay cách truy vấn:
1. Vẫn xây bảng st[k][i] cho các đoạn độ dài 2^k vì cộng associative.
2. Tách đoạn [l,r] thành **các khối lũy thừa 2 không chồng lấn**.
3. Cộng kết quả của từng khối **một lần**.

Số khối tối đa O(log L), vì đó là số bit 1 trong biểu diễn nhị phân của L. Độ phức tạp truy vấn O(log n), không còn O(1) theo hai-block RMQ.

## 7. Phân rã nhị phân không chồng lấn cho phép associative

Cho đoạn [l,r] độ dài L. Duyệt từ trái sang phải:
1. Lấy k=floor(log2 L), kích thước lớn nhất s=2^k≤L.
2. Gộp st[k][currentStart].
3. Tăng currentStart thêm s; giảm L đi s.
4. Lặp đến khi L=0.

Các khối liên tiếp **không giao nhau** và phủ đúng đoạn.

Ví dụ sum[1,5] trên mảng minh họa:
- Đoạn [1,5] có 5 phần tử.
- Tách thành khối [1,4] độ dài 4 và khối [5,5] độ dài 1.
- Sum[1,4]=2+7+2+9=20.
- Sum[5,5]=1.
- Kết quả 21.

Với [0,2], phân thành [0,1] độ dài 2 và [2,2] độ dài 1, thu 7+7=**14**. Không có phần tử nào bị cộng hai lần.

Tại mỗi vòng, bỏ bit cao nhất của độ dài còn lại, nên có O(log n) vòng.

### 7.1. Không cần tính giao hoán nếu giữ thứ tự

Nếu phép \(\circ\) associative nhưng **không commutative** (ví dụ nhân ma trận kích thước cố định), ta cần gộp các khối **đúng thứ tự từ trái sang phải**. Đảo thứ tự khối có thể tạo kết quả sai.

Phân rã nhị phân bằng con trỏ currentStart bảo đảm thứ tự. Nó không dựa vào tính giao hoán, chỉ dùng **tính kết hợp**.

### 7.2. Nếu phép có phần tử đơn vị

Với sum, bắt đầu accumulator=0 vì 0+x=x+0=x. Với min, phần tử đơn vị có thể được coi như +∞ nếu miền chấp nhận. Với một **semigroup associative không có identity rõ ràng**, có thể bắt đầu bằng kết quả khối đầu rồi gộp các khối tiếp theo, thay vì tự chọn một identity sai.

## 8. Với SUM, Prefix Sum còn tốt hơn

Dù có thể tính sum từ sparse table bằng O(log n) khối, **prefix sum** thường đơn giản và hiệu quả hơn khi chỉ cần truy vấn tổng trên mảng tĩnh.

Đặt:

\[
prefix[0]=0,
\qquad
prefix[i+1]=prefix[i]+a[i].
\]

Khi đó:

\[
\boxed{
sum(l,r)=prefix[r+1]-prefix[l]
}.
\]

- Tiền xử lý O(n).
- Bộ nhớ O(n).
- Truy vấn O(1).

Tại sao làm được? Phép cộng số nguyên có **phép nghịch đảo là trừ**. Phần tiền tố 0..l−1 được khử khỏi tiền tố 0..r.

Với XOR, có cách tương tự vì x XOR x=0; prefix XOR cho truy vấn O(1).

Nhưng với **min/max**, không có phép nghịch đảo thích hợp để khử một tiền tố tùy ý; từ min(a[0..r]) và min(a[0..l−1]) không suy ra min(a[l..r]). Đó là lý do sparse table min vẫn có vai trò quan trọng.

### 8.1. Prefix sum và overflow

Nếu dùng long, một tổng prefix có thể vượt Long.MAX_VALUE ngay cả khi một truy vấn con nhất định vẫn nằm trong miền long. Bản Java dùng **Math.addExact** và **Math.subtractExact** để báo rõ khi đầu vào vượt giới hạn biểu diễn thay vì im lặng trả sai số nguyên toán học.

Với dữ liệu có tổng lớn, cần BigInteger hoặc một mô hình tính tổng modulo rõ ràng. Đặc biệt, phép cộng số thực double không hoàn toàn associative về **bit kết quả** do rounding; phải xét mục tiêu độ chính xác trước khi dùng các chứng minh đại số tuyệt đối.

## 9. Disjoint Sparse Table: associative, truy vấn O(1)

**Disjoint Sparse Table (DST)** là biến thể hữu ích khi phép toán associative nhưng **không idempotent**, hoặc khi không có phép nghịch đảo dễ dùng như prefix sum.

Ý tưởng khác sparse table cổ điển:
- Dựng trước các **prefix và suffix aggregate** bên trong những block lũy thừa 2.
- Với mỗi query [l,r], chọn một level mà l và r nằm **ở hai nửa khác nhau của cùng block**.
- Nối suffix từ l đến giữa với prefix từ giữa+1 đến r.
- Hai phần **không chồng lấn** và bao phủ toàn bộ [l,r].

Nếu phép gộp O(1), chỉ cần một lần tìm level và một phép gộp: **O(1)** mỗi query, sau O(n log n) dựng bảng và O(n log n) bộ nhớ.

### 9.1. Cấu trúc tại level k

Với k≥0, chia chỉ số thành các block bắt đầu tại b và có độ rộng tối đa:

\[
B=2^{k+1}.
\]

Giữa block là:

\[
mid=b+2^k.
\]

Mỗi block có nửa trái [b,mid−1], nửa phải [mid,b+B−1], cắt tại n nếu block cuối không đủ chiều dài.

Tiền xử lý:
- Ở **nửa trái**, lưu suffix aggregate từ mỗi i tới mid−1.
- Ở **nửa phải**, lưu prefix aggregate từ mid tới mỗi i.
- Không lưu giá trị cho vị trí không nằm trong một nửa hợp lệ cần dùng; việc cấp mảng toàn n có thể có vài ô thừa.

Pseudocode cho phép associative:

~~~text
for each level k:
    half = 2^k
    blockLength = 2^(k+1)

    for each block [start, end):
        mid = min(start + half, n)
        end = min(start + blockLength, n)

        if mid == end:
            continue

        suffix[mid - 1] = a[mid - 1]
        for i from mid - 2 down to start:
            suffix[i] = a[i] combine suffix[i + 1]

        prefix[mid] = a[mid]
        for i from mid + 1 up to end - 1:
            prefix[i] = prefix[i - 1] combine a[i]
~~~

**Thứ tự là quan trọng:** suffix phải là a[i]◦a[i+1]◦..., còn prefix là ...◦a[i]. Không tự đảo nếu phép không commutative.

### 9.2. Cách chọn level từ hai đầu mút

Với **l<r**, lấy:

\[
\boxed{
k=\lfloor\log_2(l\operatorname{XOR}r)\rfloor
}.
\]

Điều này lấy **vị trí bit cao nhất nơi hai chỉ số khác nhau**.

- Các bit cao hơn k của l và r bằng nhau ⇒ chúng thuộc cùng block độ rộng \(2^{k+1}\).
- Bit k khác nhau. Vì l<r, l nằm ở **nửa trái**, r ở **nửa phải** của block đó.
- Do vậy có thể lấy suffix của l và prefix của r tại level k.

Truy vấn:

\[
\boxed{
answer(l,r)=suffix[k][l]\circ prefix[k][r]
}.
\]

Hai đoạn một phía đi tới mid−1, phía còn lại bắt đầu ở mid, nên **không có phần tử bị tính hai lần**.

Trường hợp **l=r** phải trả ngay a[l] — không tính highest set bit của \(l\operatorname{XOR}r=0\).

### 9.3. Ví dụ trên [5,2,7,2,9,1,4,6]

Truy vấn sum[0,2]:
- l XOR r = 0 XOR 2 = 2 (nhị phân 10).
- Bit cao nhất khác nhau là k=1.
- Block độ rộng 2^(1+1)=4, chia [0,1] và [2,3].
- Suffix từ l=0 đến mid−1=1: 5+2=7.
- Prefix từ mid=2 đến r=2: 7.
- Gộp: 7+7=**14**.

Truy vấn sum[2,5]:
- 2 XOR 5 = 7 (nhị phân 111).
- k=2 ⇒ block độ rộng 8, chia tại mid=4.
- Suffix [2,3]=7+2=9.
- Prefix [4,5]=9+1=10.
- Gộp 9+10=**19**.

Truy vấn sum[0,7]:
- k=2, suffix [0,3]=5+2+7+2=16.
- Prefix [4,7]=9+1+4+6=20.
- Tổng = **36**.

### 9.4. Chứng minh đúng và độ phức tạp

Mỗi level chia mảng thành các block liên tiếp. Tại block có hai nửa, suffix được xây bởi phép associative từ trái sang phải theo **đúng thứ tự gốc**, prefix cũng như vậy. Do tính chất bit XOR, query l<r chọn đúng level mà l thuộc nửa trái và r thuộc nửa phải của cùng block.

Khi đó:

\[
[l,r]=[l,mid-1]\;\cup\;[mid,r]
\]

và hai đoạn **rời nhau**. Kết quả tính bằng một phép gộp của suffix[k][l] và prefix[k][r] là aggregate của toàn [l,r]. Không cần idempotence, không cần phép nghịch đảo.

Ở mỗi level, tổng số phần tử được quét để tạo các suffix/prefix là **O(n)**; có O(log n) level. Vì vậy tiền xử lý và bộ nhớ là **O(n log n)**. Query l<r chỉ cần highest differing bit và một phép gộp O(1), nên **O(1)** nếu phép gộp O(1).

### 9.5. Trường hợp n không là lũy thừa hai

Block cuối một level có thể bị cắt ở cuối mảng:
- Nếu không đủ phần nửa phải, không có cặp query nào tại level đó cần ghép hai nửa của block ấy.
- Nếu có cả hai nửa, dùng ranh giới mid và end đã cắt tại n.
- Mọi query l<r vẫn có một highest differing bit k, và tiền xử lý tại level k chứa cả suffix[k][l] lẫn prefix[k][r].

Không cần padding bằng các giá trị giả. Điều này đặc biệt quan trọng với phép không có identity phù hợp.

## 10. Sparse Table cổ điển, DST và prefix: dùng cái nào?

| Phương pháp | Tiền xử lý | Truy vấn | Bộ nhớ | Điều kiện đáng nhớ |
|---|---|---|---|---|
| Duyệt đoạn | Không | O(n) xấu nhất | O(1) | Bất kỳ phép tính hợp lệ |
| Sparse Table 2 khối chồng lấn | O(n log n) | **O(1)** | O(n log n) | Associative + idempotent, combine O(1) |
| Sparse Table phân rã khối rời | O(n log n) | **O(log n)** | O(n log n) | Associative, combine O(1) |
| Disjoint Sparse Table | O(n log n) | **O(1)** | O(n log n) | Associative, combine O(1) |
| Prefix Sum | O(n) | **O(1)** | O(n) | Sum có phép trừ đúng, chú ý overflow |
| Prefix XOR | O(n) | **O(1)** | O(n) | XOR và tự nghịch đảo |
| Segment Tree | O(n) | O(log n) | O(n) | Associative, hỗ trợ cập nhật O(log n) |

**Khuyến nghị:** với bài **RMQ min/max tĩnh**, sparse table hai khối thường là lựa chọn tốt. Với **sum tĩnh**, prefix sum thường đơn giản hơn và ít bộ nhớ hơn cả DST. Với phép associative khó xử lý bằng prefix inverse, nhưng cần query O(1), **DST** có thể phù hợp. Với cập nhật xen kẽ, dùng segment tree hoặc cấu trúc động tương ứng.

Sparse table không tự động là lựa chọn nhanh nhất cho mảng rất nhỏ hay số query Q ít, vì chi phí tiền xử lý và cache có thể lớn hơn việc duyệt đoạn trực tiếp.

## 11. Mảng có cập nhật thì sao?

Mọi ô của sparse table phụ thuộc vào một đoạn của mảng gốc. Nếu a[i] thay đổi, nhiều ô table từng chứa i có thể trở nên sai.

Một cách chính xác là **dựng lại toàn bộ bảng**, mất O(n log n) cho mỗi đợt thay đổi. Đây thường không phù hợp với luồng thao tác cập nhật liên tục.

**Segment tree** với phép associative cho:
- Xây cây O(n).
- Query khoảng O(log n).
- Cập nhật một phần tử O(log n).
- Bộ nhớ O(n) trong cài đặt phổ biến.

**Fenwick tree** thường phù hợp với tổng/prefix sum có cập nhật; range sum qua hiệu hai prefix, O(log n) cho update và range query. Không được bê nguyên Fenwick sum sang min với phép trừ nghịch đảo không tồn tại.

Nếu toàn bộ thao tác là **offline** và được phép sắp/xử lý lại thứ tự truy vấn, có thể cân nhắc thêm các kỹ thuật khác. Nhưng không cần thuật toán offline đặc biệt khi mảng tĩnh và min query đã có O(1).

## 12. Java 17 hoàn chỉnh: MIN, SUM theo khối rời, DST và prefix

Lưu thành **StaticSparseTableDemo.java**. Không cần thư viện ngoài, một public class và các nested class.

Code gồm:
- **MinSparseTable:** xây st[k][i] bằng min, truy vấn hai khối chồng lấn **O(1)**.
- **SumSparseTable:** xây st[k][i] bằng Math.addExact, query phân rã thành các đoạn lũy thừa 2 **không giao nhau**, O(log n).
- **DisjointSumTable:** xây suffix/prefix theo block và query bằng highest differing bit, **O(1)**.
- **PrefixSum:** O(n) build và O(1) query, là lựa chọn tối giản cho sum tĩnh.
- **differentialTest:** sinh mảng ngắn có số âm, so cả bốn cấu trúc với oracle duyệt trực tiếp trên mọi đoạn con.
- Test mảng đơn, mảng âm, mảng rỗng, khoảng không hợp lệ và cộng long tràn.

**Quy ước:** truy vấn dùng [l,r] **inclusive, 0-based**, l≤r. Đầu vào mảng rỗng bị từ chối. Với phép cộng, Math.addExact ném ArithmeticException nếu một tổng trung gian không biểu diễn được bằng long; đây là lựa chọn có chủ đích để **không xuất một tổng sai**.

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public final class StaticSparseTableDemo {
    private StaticSparseTableDemo() {
    }

    private static long[] checkedCopy(long[] input) {
        Objects.requireNonNull(input, "array");
        if (input.length == 0) {
            throw new IllegalArgumentException(
                    "Array must not be empty");
        }
        return input.clone();
    }

    private static void validateRange(
            int n, int left, int right) {
        if (left < 0 || right < left || right >= n) {
            throw new IllegalArgumentException(
                    "Invalid inclusive range");
        }
    }

    private static int[] buildLogs(int n) {
        int[] log = new int[n + 1];
        for (int i = 2; i <= n; i++) {
            log[i] = log[i >>> 1] + 1;
        }
        return log;
    }

    // Idempotent min: two OVERLAPPING blocks give O(1) RMQ.
    public static final class MinSparseTable {
        private final int n;
        private final int[] log;
        private final long[][] table;

        public MinSparseTable(long[] input) {
            long[] a = checkedCopy(input);
            n = a.length;
            log = buildLogs(n);
            table = new long[log[n] + 1][];
            table[0] = a;

            for (int k = 1; k < table.length; k++) {
                int length = 1 << k;
                int half = length >>> 1;
                table[k] = new long[n - length + 1];

                for (int i = 0; i < table[k].length; i++) {
                    table[k][i] = Math.min(
                            table[k - 1][i],
                            table[k - 1][i + half]);
                }
            }
        }

        public long query(int left, int right) {
            validateRange(n, left, right);
            int k = log[right - left + 1];
            int length = 1 << k;

            return Math.min(
                    table[k][left],
                    table[k][right - length + 1]);
        }
    }

    // Associative sum: build the same power-of-two blocks,
    // but query uses DISJOINT blocks in O(log n).
    public static final class SumSparseTable {
        private final int n;
        private final int[] log;
        private final long[][] table;

        public SumSparseTable(long[] input) {
            long[] a = checkedCopy(input);
            n = a.length;
            log = buildLogs(n);
            table = new long[log[n] + 1][];
            table[0] = a;

            for (int k = 1; k < table.length; k++) {
                int length = 1 << k;
                int half = length >>> 1;
                table[k] = new long[n - length + 1];

                for (int i = 0; i < table[k].length; i++) {
                    table[k][i] = Math.addExact(
                            table[k - 1][i],
                            table[k - 1][i + half]);
                }
            }
        }

        public long query(int left, int right) {
            validateRange(n, left, right);
            int start = left;
            int remaining = right - left + 1;
            long answer = 0;

            while (remaining > 0) {
                int k = log[remaining];
                int length = 1 << k;

                answer = Math.addExact(
                        answer, table[k][start]);
                start += length;
                remaining -= length;
            }
            return answer;
        }
    }

    // Associative sum WITHOUT overlap: O(1) query.
    // General idea also handles other associative operations
    // when their combine costs O(1).
    public static final class DisjointSumTable {
        private final int n;
        private final long[] values;
        private final long[][] partial;

        public DisjointSumTable(long[] input) {
            values = checkedCopy(input);
            n = values.length;

            // For n == 1, levels == 0; only singleton query.
            int levels = 32 - Integer.numberOfLeadingZeros(n - 1);
            partial = new long[levels][n];

            for (int k = 0; k < levels; k++) {
                long half = 1L << k;
                long width = half << 1;

                for (long start = 0; start < n; start += width) {
                    int lo = (int) start;
                    int mid = (int) Math.min(start + half, n);
                    int end = (int) Math.min(start + width, n);

                    if (mid >= end) {
                        continue; // No right half at this level.
                    }

                    // Left half: suffix from each index to mid-1.
                    partial[k][mid - 1] = values[mid - 1];
                    for (int i = mid - 2; i >= lo; i--) {
                        partial[k][i] = Math.addExact(
                                values[i], partial[k][i + 1]);
                    }

                    // Right half: prefix from mid to each index.
                    partial[k][mid] = values[mid];
                    for (int i = mid + 1; i < end; i++) {
                        partial[k][i] = Math.addExact(
                                partial[k][i - 1], values[i]);
                    }
                }
            }
        }

        public long query(int left, int right) {
            validateRange(n, left, right);

            if (left == right) {
                return values[left];
            }

            int differingBits = left ^ right;
            int k = 31 - Integer.numberOfLeadingZeros(
                    differingBits);

            return Math.addExact(
                    partial[k][left], partial[k][right]);
        }
    }

    // Sum-specific alternative: O(n) build, O(1) query.
    public static final class PrefixSum {
        private final int n;
        private final long[] prefix;

        public PrefixSum(long[] input) {
            long[] a = checkedCopy(input);
            n = a.length;
            prefix = new long[n + 1];

            for (int i = 0; i < n; i++) {
                prefix[i + 1] = Math.addExact(
                        prefix[i], a[i]);
            }
        }

        public long query(int left, int right) {
            validateRange(n, left, right);
            return Math.subtractExact(
                    prefix[right + 1], prefix[left]);
        }
    }

    private static void require(boolean ok, String reason) {
        if (!ok) {
            throw new AssertionError(reason);
        }
    }

    // Test every [left,right] against an independent scan.
    // 500 reproducible arrays with negatives, zero, duplicates,
    // odd lengths, and sizes that are/not powers of two.
    private static int differentialTest() {
        Random rng = new Random(5032026L);

        for (int test = 0; test < 500; test++) {
            int n = 1 + rng.nextInt(32);
            long[] a = new long[n];

            for (int i = 0; i < n; i++) {
                a[i] = rng.nextInt(201) - 100;
            }

            MinSparseTable min = new MinSparseTable(a);
            SumSparseTable sums = new SumSparseTable(a);
            DisjointSumTable disjoint = new DisjointSumTable(a);
            PrefixSum prefix = new PrefixSum(a);

            for (int left = 0; left < n; left++) {
                long expectedMin = Long.MAX_VALUE;
                long expectedSum = 0;

                for (int right = left; right < n; right++) {
                    expectedMin = Math.min(
                            expectedMin, a[right]);
                    expectedSum = Math.addExact(
                            expectedSum, a[right]);

                    require(
                            min.query(left, right) == expectedMin,
                            "Min mismatch");
                    require(
                            sums.query(left, right) == expectedSum,
                            "Sum blocks mismatch");
                    require(
                            disjoint.query(left, right) == expectedSum,
                            "Disjoint table mismatch");
                    require(
                            prefix.query(left, right) == expectedSum,
                            "Prefix sum mismatch");
                }
            }
        }
        return 500;
    }

    public static void main(String[] args) {
        long[] a = {5, 2, 7, 2, 9, 1, 4, 6};
        MinSparseTable min = new MinSparseTable(a);
        SumSparseTable sums = new SumSparseTable(a);
        DisjointSumTable disjoint = new DisjointSumTable(a);
        PrefixSum prefix = new PrefixSum(a);

        System.out.println("Array: " + Arrays.toString(a));
        System.out.println("Min [0,7]: " + min.query(0, 7));
        System.out.println("Min [1,4]: " + min.query(1, 4));
        System.out.println("Min [2,5]: " + min.query(2, 5));
        System.out.println("Min [3,3]: " + min.query(3, 3));

        System.out.println("Sum blocks [0,7]: "
                + sums.query(0, 7));
        System.out.println("Sum disjoint [0,7]: "
                + disjoint.query(0, 7));
        System.out.println("Sum prefix [0,7]: "
                + prefix.query(0, 7));

        System.out.println("Sum blocks [0,2]: "
                + sums.query(0, 2));
        System.out.println("Sum disjoint [0,2]: "
                + disjoint.query(0, 2));
        System.out.println("Sum prefix [0,2]: "
                + prefix.query(0, 2));

        // ANTI-PATTERN: the overlapping a[1] is counted twice!
        long wrongOverlap =
                (a[0] + a[1]) + (a[1] + a[2]);
        System.out.println("Wrong overlap [0,2]: "
                + wrongOverlap);

        System.out.println("Sum [2,5]: "
                + disjoint.query(2, 5));
        System.out.println("Sum [5,7]: "
                + disjoint.query(5, 7));
        System.out.println("Singleton disjoint [3,3]: "
                + disjoint.query(3, 3));

        long[] signed = {-5, 0, 8, -2, 3};
        System.out.println("Negative min [0,4]: "
                + new MinSparseTable(signed).query(0, 4));
        System.out.println("Negative sum [0,4]: "
                + new DisjointSumTable(signed).query(0, 4));

        long[] one = {42};
        System.out.println("One-element min: "
                + new MinSparseTable(one).query(0, 0));
        System.out.println("One-element disjoint sum: "
                + new DisjointSumTable(one).query(0, 0));

        try {
            new MinSparseTable(new long[0]);
            System.out.println("Empty rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Empty rejected: true");
        }

        try {
            min.query(4, 2);
            System.out.println("Out-of-range rejected: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Out-of-range rejected: true");
        }

        try {
            new SumSparseTable(
                    new long[]{Long.MAX_VALUE, 1});
            System.out.println("Overflow detected: false");
        } catch (ArithmeticException expected) {
            System.out.println("Overflow detected: true");
        }

        System.out.println(
                "Differential test: "
                + differentialTest() + " arrays PASS");
    }
}
~~~

### 12.1. Biên dịch và chạy

Dùng **JDK 17 hoặc mới hơn**, lưu đúng tên file StaticSparseTableDemo.java:

~~~bash
javac -encoding UTF-8 StaticSparseTableDemo.java
java StaticSparseTableDemo
~~~

**Stdout dự kiến:**

~~~text
Array: [5, 2, 7, 2, 9, 1, 4, 6]
Min [0,7]: 1
Min [1,4]: 2
Min [2,5]: 1
Min [3,3]: 2
Sum blocks [0,7]: 36
Sum disjoint [0,7]: 36
Sum prefix [0,7]: 36
Sum blocks [0,2]: 14
Sum disjoint [0,2]: 14
Sum prefix [0,2]: 14
Wrong overlap [0,2]: 16
Sum [2,5]: 19
Sum [5,7]: 11
Singleton disjoint [3,3]: 2
Negative min [0,4]: -5
Negative sum [0,4]: 4
One-element min: 42
One-element disjoint sum: 42
Empty rejected: true
Out-of-range rejected: true
Overflow detected: true
Differential test: 500 arrays PASS
~~~

### 12.2. Từng phần của mã có ý nghĩa gì?

**MinSparseTable:** mỗi table[k][i] là min trên đoạn độ dài 2^k. Khi query, dùng hai đoạn độ dài s có thể trùng/chồng lấn. Vì min associative+idempotent, kết quả luôn đúng.

**SumSparseTable:** bảng được xây bằng hai nửa **không chồng lấn**, hoàn toàn hợp lệ vì cộng associative. Query không dùng hai block giống RMQ; nó tách độ dài thành những khối lũy thừa 2 **rời nhau** từ trái sang phải, trả tổng đúng trong O(log n).

**DisjointSumTable:** mỗi level xây suffix của nửa trái và prefix của nửa phải. Khi l<r, bit khác nhau cao nhất xác định ranh giới giữa hai nửa; hai phần được ghép là rời nhau và bao phủ [l,r]. Khi l=r, trả trực tiếp phần tử gốc vì l XOR r=0.

**PrefixSum:** tiền xử lý tổng từ đầu mảng, dùng phép trừ để tính sum(l,r) trong O(1). Nó không cần sparse table; với range sum trên mảng tĩnh, thường là lựa chọn gọn hơn.

**Mảng đầu vào được clone:** sau khi tạo cấu trúc, sửa mảng nguồn không làm bảng bị thay đổi một phần. Đây là cách giữ hợp đồng **static array** minh bạch.

**Các mảng không là lũy thừa hai:** code DST dùng blockStart và min(...,n) khi dựng, nên block cuối bị cắt nhưng vẫn đúng cho mọi query hợp lệ.

**Math.addExact/subtractExact:** không cho cộng/trừ long tràn im lặng. Ví dụ bảng sum cho [Long.MAX_VALUE,1] ném ArithmeticException tại bước dựng một đoạn độ dài 2. Bảo đảm “range sum toán học đúng” chỉ có nghĩa khi mọi phép toán trung gian được biểu diễn hoặc ta dùng BigInteger.

**Differential test:** 500 mảng ngẫu nhiên tái lập, n từ 1 đến 32, giá trị trong [-100,100]. Mỗi test so **tất cả đoạn con** với oracle quét trực tiếp, thay vì chỉ so hai thuật toán bảng với nhau.

### 12.3. Các cận trong mã

- MinSparseTable: O(n log n) dựng; **O(1)** query; O(n log n) memory.
- SumSparseTable: O(n log n) dựng; **O(log n)** query; O(n log n) memory.
- DisjointSumTable: O(n log n) dựng; **O(1)** query; O(n log n) memory.
- PrefixSum: **O(n)** dựng; **O(1)** query; O(n) memory.
- Oracle scan: O(r−l+1) cho mỗi đoạn.
- DifferentialTest: chỉ là QA trên mảng nhỏ, **không nằm trong API query production**.

Các cận này áp dụng cho phép min/cộng long theo số học được biểu diễn chính xác trong miền đã chọn, với phép kết hợp có chi phí O(1).

## 13. Chứng minh bất biến và những điểm biên

### 13.1. Bất biến khi dựng bảng sparse

Ở tầng 0, table[0][i] chứa đúng a[i]. Giả sử mọi table[k−1][i] chứa aggregate của \(2^{k-1}\) phần tử liên tiếp. Hai đoạn \([i,i+2^{k-1}-1]\) và \([i+2^{k-1},i+2^k-1]\) không giao nhau và phủ chính xác đoạn dài \(2^k\). Tính kết hợp của phép toán chứng minh table[k][i] đúng. Quy nạp theo k hoàn tất.

### 13.2. Bất biến truy vấn min

Hai khối dài \(s=2^{\lfloor\log_2L\rfloor}\) phủ [l,r]. Phần giao bị gộp hai lần nhưng phép min idempotent, nên kết quả vẫn là min của cả đoạn. Cùng chứng minh cho max/gcd/AND/OR.

### 13.3. Bất biến truy vấn sum bằng khối rời

Mỗi bước xử lý đúng một block bắt đầu ở currentStart. Các block nối tiếp, không giao nhau; phép cộng associative nên tổng của các aggregate bằng tổng toàn đoạn. Khi remaining=0, mọi phần tử đã được tính đúng một lần.

### 13.4. Bất biến DST

Ở mỗi block của level k, suffix/prefix đã lưu đúng aggregate trong thứ tự gốc. Với l<r, bit cao nhất khác nhau của l và r chỉ ra đúng một block có l ở bên trái và r ở bên phải. Suffix(l..mid−1) và prefix(mid..r) rời nhau và hợp lại là [l,r], nên phép kết hợp là đáp án đúng. Không sử dụng tính lũy đẳng.

### 13.5. Các trường hợp biên

- **n=1:** log[1]=0, sparse table chỉ có tầng 0; DST không cần level nào vì mọi query hợp lệ là singleton.
- **n không là lũy thừa hai:** bảng cổ điển chỉ lưu ô hợp lệ; DST xử lý block cuối bị cắt.
- **l=r:** min query vẫn đúng; DST phải trả a[l] trực tiếp.
- **l=0, r=n−1:** truy vấn toàn mảng.
- **Mảng âm/giá trị 0:** min và sum vẫn đúng nếu không overflow.
- **Giá trị trùng nhau:** min lũy đẳng; sum phải tính từng vị trí dù cùng giá trị.
- **Mảng rỗng:** API từ chối, không có đoạn [l,r] hợp lệ.
- **l<0, r≥n hoặc l>r:** API từ chối.
- **Giá trị rất lớn:** phải kiểm khả năng overflow hoặc dùng BigInteger.
- **Thay đổi dữ liệu nguồn:** các bảng đã dựng giữ snapshot, không tự phản ánh update.

## 14. Kiểm thử bằng oracle độc lập

Một test đơn giản mạnh hơn việc xem vài stdout: với mảng n nhỏ, duyệt tất cả \(n(n+1)/2\) đoạn [l,r], dùng vòng lặp trực tiếp lấy min/sum làm **oracle** và so với từng cấu trúc.

### 14.1. Tập trường hợp cần có

1. n=1, chỉ một query [0,0].
2. n=2, đầy đủ ba đoạn [0,0],[1,1],[0,1].
3. n=3 để bắt lỗi sum overlap [0,2].
4. n=7,8,9 để kiểm block DST sát ranh giới lũy thừa hai.
5. Mảng tăng, giảm, toàn bằng nhau.
6. Mảng gồm nhiều số âm và 0.
7. Mảng có nhiều min bằng nhau, min nằm đầu/giữa/cuối.
8. Mỗi đoạn độ dài \(2^k\), \(2^k-1\), \(2^k+1\).
9. Query băng qua ranh giới block DST; l XOR r có bit cao k khác nhau.
10. Query singleton DST để không lấy highestSetBit(0).
11. Range bất hợp lệ, mảng rỗng và null.
12. Tổng long overflow, để bảo đảm không tạo kết quả im lặng sai.

### 14.2. Tại sao phải có oracle khác thuật toán?

Nếu chỉ so SumSparseTable và DisjointSumTable, cả hai có thể mắc **cùng một lỗi** về chỉ số hoặc độ dài. Oracle trực tiếp duyệt mảng có cấu trúc đơn giản, độc lập với tiền xử lý bảng.

Test tăng độ dài từ 1 đến 32, dùng nhiều seed/ngẫu nhiên; khi lỗi, lưu array, l, r, kỳ vọng và giá trị thực tế. Một phản ví dụ nhỏ có thể làm lộ:
- Sai off-by-one trong r+1.
- Chọn k=lg[r-l] thay vì lg[r-l+1].
- Đọc st[k][r−s] thay vì st[k][r−s+1].
- Shift nhầm 1<<k hoặc đặc biệt n=1.
- DST trả từ một ô chưa dựng do chọn sai level.
- Sum dùng overlap thay vì decomposition.
- Nhầm thứ tự ghép trong phép associative không commutative.

### 14.3. Kiểm tính không giao hoán ở DST

Mã Java minh họa DST bằng sum, một phép commutative. Để kiểm bản **generic associative** thực sự, nên thêm test với phép **nhân ma trận 2×2 theo modulo một số nguyên tố nhỏ**, vốn associative nhưng không commutative.

Dùng oracle nhân lần lượt ma trận từ l tới r; kiểm DST trả đúng cho mọi đoạn. Nếu vô ý đổi thứ tự suffix/prefix hoặc build theo chiều ngược, test sẽ phát hiện. Với chuỗi, phép ghép cũng associative nhưng vật liệu hóa output có chi phí theo chiều dài, nên không nên dùng để khẳng định thời gian thực O(1).

## 15. Sai lầm phổ biến

1. **Gọi mọi sparse table query là O(1)** mà không xét phép toán.
2. **Dùng hai block chồng lấn cho sum** và làm phần giao bị cộng hai lần.
3. **Thay min bằng XOR** nhưng vẫn giữ query hai-block.
4. **Cho rằng associative đồng nghĩa idempotent**.
5. **Cho rằng idempotent một mình là đủ**, dù phép có thể không associative.
6. **Nhầm commutative với associative**; tính đổi thứ tự và đổi dấu ngoặc là hai khái niệm khác nhau.
7. **Không tôn trọng thứ tự** khi phép associative không commutative.
8. **Tính k=log2(r−l)** thay vì log2(r−l+1).
9. **Chọn log từ double** mà không kiểm biên lũy thừa hai.
10. **Đọc block phải ở r−2^k** thay vì r−2^k+1.
11. **Cố đọc st[k][i] khi đoạn dài 2^k vượt n**.
12. **Không khởi tạo tầng 0 từ mảng gốc**.
13. **Đảo hai nửa trong bước chuyển** với phép không commutative.
14. **Dùng identity sai** để khởi tạo accumulator của semigroup không có phần tử đơn vị.
15. **Không xử lý singleton** trong DST; l XOR l=0.
16. **Dùng bit thấp khác nhau của l XOR r** thay vì bit cao nhất.
17. **Nhầm highest set bit với số lượng bit set**.
18. **Xây DST suffix theo thứ tự phải◦trái** không phù hợp.
19. **Xây DST prefix theo thứ tự mới◦cũ** không phù hợp với phép không commutative.
20. **Sai ranh giới mid** trong block cuối không đủ \(2^{k+1}\) phần tử.
21. **Bỏ qua mảng n=1** khi số tầng DST bằng 0.
22. **Nhầm truy vấn [l,r] inclusive với [l,r) exclusive**.
23. **Không kiểm l≤r hoặc r<n** và để Java ném lỗi mảng khó hiểu.
24. **Tin rằng sửa a[i] sẽ tự cập nhật sparse table**.
25. **Dùng bảng O(n log n) chỉ để truy vấn sum** dù prefix sum O(n) thường tốt hơn.
26. **Dùng prefix min như prefix sum**, dù không có phép khử min của tiền tố.
27. **Không dự trù RAM O(n log n)** cho nhiều mảng/bộ dữ liệu.
28. **Giả định phép combine luôn O(1)** khi kết quả là chuỗi/mảng dài.
29. **Cho rằng cộng double associative chính xác** dù rounding gây khác biệt bit.
30. **Cho long overflow im lặng**, làm sai kết quả tính tổng toán học.
31. **Không thử số âm/trùng/0**, bỏ những ca khiến lỗi lộ rõ.
32. **Chỉ kiểm một truy vấn toàn mảng**, không thử độ dài 3 và các biên DST.
33. **So hai triển khai bảng nhưng thiếu oracle độc lập**, không bắt lỗi cùng nguyên nhân.
34. **Nhầm sparse table với segment tree** về khả năng cập nhật.
35. **Khẳng định O(1) trên phép concat tạo chuỗi dài**, quên độ lớn output.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Sparse table cổ điển tiền xử lý những đoạn có độ dài nào?

**Đáp án:** Những đoạn liên tiếp độ dài \(2^k\), với k≥0 và đoạn không vượt n.

**Câu 2.** Công thức xây st[k][i]?

**Đáp án:** st[k−1][i]◦st[k−1][i+2^(k−1)].

**Câu 3.** Tính associative có nghĩa gì?

**Đáp án:** Có thể thay cách đặt ngoặc giữa các kết quả liên tiếp mà không đổi kết quả.

**Câu 4.** Tính idempotent là gì?

**Đáp án:** x◦x=x với mọi x trong miền kết quả.

**Câu 5.** Kể ba phép phù hợp với hai-block O(1)?

**Đáp án:** Min, max, gcd; cũng có bitwise AND và OR.

**Câu 6.** Vì sao hai block chồng lấn đúng với min?

**Đáp án:** Min associative và idempotent; phần giao được xét hai lần nhưng không đổi min.

**Câu 7.** Truy vấn [l,r] chọn k như thế nào?

**Đáp án:** k=floor(log2(r−l+1)).

**Câu 8.** Hai vị trí đọc bảng min?

**Đáp án:** st[k][l] và st[k][r−2^k+1].

**Câu 9.** Vì sao sum[0,2] của [5,2,7] không bằng 16?

**Đáp án:** Đáp án đúng là 14; hai block [0,1] và [1,2] cùng chứa a[1]=2, khiến phép cộng bị tính lặp.

**Câu 10.** Muốn dùng sparse table sum theo cách cổ điển cần sửa gì?

**Đáp án:** Query phải tách thành các block lũy thừa hai rời nhau; mỗi block được cộng đúng một lần.

**Câu 11.** Cận truy vấn sum bằng decomposition là bao nhiêu?

**Đáp án:** O(log n) phép gộp, sau O(n log n) tiền xử lý.

**Câu 12.** Dùng cách nào đơn giản hơn cho sum tĩnh?

**Đáp án:** Prefix sum, build O(n), query O(1) bằng prefix[r+1]−prefix[l].

**Câu 13.** Vì sao không dùng prefix min để suy ra range min?

**Đáp án:** Không có phép nghịch đảo khử min của tiền tố.

**Câu 14.** DST khác sparse table hai-block ra sao?

**Đáp án:** Nó dựng suffix/prefix rời nhau ở mỗi block và chọn level theo bit cao nhất khác nhau của l và r.

**Câu 15.** Level query DST với l<r?

**Đáp án:** k=floor(log2(l XOR r)).

**Câu 16.** DST xử lý l=r thế nào?

**Đáp án:** Trả ngay a[l], không tính bit khác nhau của 0.

**Câu 17.** DST có yêu cầu idempotent không?

**Đáp án:** Không, chỉ cần associative và chi phí combine phù hợp; hai phần được gộp không giao nhau.

**Câu 18.** Chi phí DST?

**Đáp án:** O(n log n) dựng và bộ nhớ, O(1) truy vấn nếu combine O(1).

**Câu 19.** Nếu mảng có nhiều updates thì nên dùng gì?

**Đáp án:** Segment tree cho phép associative, update và query O(log n); với sum còn có Fenwick.

**Câu 20.** n=1 có cần bảng DST không?

**Đáp án:** Không; mọi query hợp lệ là singleton, trả phần tử trực tiếp.

**Câu 21.** Để kiểm DST generic không commutative, nên thử phép nào?

**Đáp án:** Nhân ma trận kích thước cố định theo modulo hoặc phép associative có thứ tự khác.

**Câu 22.** Vì sao Math.addExact được dùng cho sum?

**Đáp án:** Để phát hiện overflow long thay vì âm thầm xuất tổng sai trong số học nguyên.

**Câu 23.** Nếu chỉ có 2 truy vấn rất ngắn, có cần tiền xử lý sparse table không?

**Đáp án:** Không nhất thiết; quét đoạn trực tiếp có thể đơn giản và rẻ hơn.

**Câu 24.** Khi code công bố O(1) query cần nói rõ giả thiết nào?

**Đáp án:** Phép combine O(1), tiền xử lý hoàn tất, dữ liệu tĩnh và các query hợp lệ.

## 17. Bài tập thực hành

**Bài 1 — GCD tĩnh:** thay Math.min trong MinSparseTable bằng gcd trên số nguyên không âm. Kiểm tính associative+idempotent; với đầu vào số âm, phải chuẩn hóa dấu và chú ý Long.MIN_VALUE.

**Bài 2 — XOR:** xây bảng XOR tương tự SumSparseTable và truy vấn bằng các block rời; chứng minh không thể dùng hai block overlap. So với prefix XOR.

**Bài 3 — Disjoint Table không giao hoán:** viết phiên bản generic cho ma trận 2×2 modulo một số nguyên tố. Kiểm mọi query với oracle nhân tuần tự để phát hiện sai thứ tự.

**Bài 4 — Một mảng n=9:** tự vẽ các block DST ở level k=0,1,2,3. Kiểm [0,8], [5,8], [8,8] và xác định level từ l XOR r.

**Bài 5 — Chọn cấu trúc theo Q:** với n=10^5 và Q=10^5, ước lượng số ô O(n log n) và chi phí quét O(nQ). Với Q rất nhỏ, thử so thời gian thực của quét trực tiếp.

**Bài 6 — Test sai số số thực:** dùng double cho sum và so kết quả theo thứ tự cộng khác nhau. Giải thích vì sao rounding có thể làm mất tính associative tuyệt đối trong biểu diễn máy.

**Bài 7 — Snapshot và update:** sau khi xây bảng, sửa mảng nguồn một phần tử. Chứng minh cấu trúc sparse không tự biết giá trị mới; quyết định rebuild hay chuyển sang segment tree.

## 18. Ghi nhớ

**Sparse table cổ điển** dựng kết quả cho những đoạn chiều dài \(2^k\), chi phí **O(n log n)**. Với phép **associative + idempotent**, hai khối có thể chồng lấn cho truy vấn **O(1)**; ví dụ min/max/gcd/AND/OR.

**Sum/XOR không idempotent**, nên nếu dùng hai block chồng lấn sẽ tính lặp dữ liệu và cho kết quả sai. Có thể truy vấn sparse table theo **các khối rời O(log n)**, dùng **prefix sum O(1)** riêng cho phép cộng, hoặc dựng **Disjoint Sparse Table O(1)** cho phép associative trong mô hình combine O(1).

Hãy phân biệt **tính chất phép toán**, **trạng thái tĩnh của mảng**, **cách định nghĩa [l,r]**, **chi phí bộ nhớ/tiền xử lý** và **khả năng overflow** trước khi chọn cấu trúc. Một công thức RMQ đúng với min **không tự động đúng với mọi phép gộp**.
