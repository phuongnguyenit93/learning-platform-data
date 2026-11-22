# Cây Fenwick cho tổng tiền tố và các phép biến đổi truy vấn

## 1. Bài toán và tư duy dùng tổng tiền tố

Trong chủ đề **Truy vấn và ngoại tuyến**, một dạng bài căn bản là duy trì dãy số a[0..n−1] và thực hiện nhiều thao tác hỏi hoặc cập nhật:

- **Point add:** tăng một phần tử a[i] thêm một lượng delta.
- **Point set:** đặt a[i] thành giá trị mới.
- **Prefix sum:** tính tổng các phần tử từ đầu mảng đến một điểm.
- **Range sum:** tính tổng trên đoạn đóng [L,R].
- **Range add:** tăng đồng loạt mọi phần tử thuộc đoạn đóng [L,R].
- **Point get:** hỏi giá trị hiện tại tại đúng một vị trí.
- **Prefix lower bound:** tìm vị trí đầu tiên có tổng tiền tố đạt một ngưỡng, trong các tình huống tổng tiền tố đơn điệu.

Nếu mảng **không thay đổi**, prefix sum tĩnh là đủ:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]

sum(L,R) = prefix[R+1] - prefix[L]
~~~

Xây prefix một lần O(n), hỏi đoạn O(1). Nhưng khi cập nhật a[i], nhiều prefix phía sau thay đổi. Nếu mỗi lần sửa lại tất cả prefix, có thể phải tốn O(n) cho một update.

**Cây Fenwick (Fenwick Tree, Binary Indexed Tree, BIT)** là cấu trúc gọn nhẹ cho các tổng nhóm động, hỗ trợ cập nhật điểm và tổng tiền tố trong **O(log n)** thời gian, với **O(n)** bộ nhớ.

Điểm quan trọng của bài này không chỉ là thuộc hai vòng lặp `i += i & -i` và `i -= i & -i`: chúng ta còn học **phép biến đổi truy vấn bằng mảng sai phân**, cho phép cùng ý tưởng Fenwick giải ba mô hình:

| Cập nhật | Truy vấn | Công cụ |
| --- | --- | --- |
| Cộng một điểm | Tổng một đoạn | Một BIT trên a |
| Cộng một đoạn | Giá trị một điểm | Một BIT trên sai phân d |
| Cộng một đoạn | Tổng một đoạn | Hai BIT trên sai phân có trọng số |
| Đặt một điểm | Tổng một đoạn | Một BIT trên a và mảng giá trị hiện tại |
| Không có cập nhật | Tổng một đoạn | Prefix sum tĩnh có thể đơn giản hơn |

Cần chọn **mô hình thao tác chính xác** trước khi áp dụng công thức. Một BIT tổng thông thường **không tự động** hỗ trợ range add/range sum nếu không chuyển đổi trạng thái.

## 2. Fenwick Tree là gì?

Fenwick Tree lưu các **tổng của những khối liên tiếp** trong mảng. Nó thường được cài bằng một mảng một chiều tên `bit`, không cần tạo các đối tượng nút cây hay con trỏ.

Cấu trúc nội bộ dùng **chỉ số 1-based**. Với một số nguyên dương i:

~~~text
lowbit(i) = i & (-i)
~~~

`lowbit(i)` giữ lại bit 1 thấp nhất trong biểu diễn nhị phân của i. Ví dụ:

| i | Nhị phân | lowbit(i) | Đoạn do bit[i] lưu (1-based) |
| ---: | --- | ---: | --- |
| 1 | 0001 | 1 | [1,1] |
| 2 | 0010 | 2 | [1,2] |
| 3 | 0011 | 1 | [3,3] |
| 4 | 0100 | 4 | [1,4] |
| 5 | 0101 | 1 | [5,5] |
| 6 | 0110 | 2 | [5,6] |
| 7 | 0111 | 1 | [7,7] |
| 8 | 1000 | 8 | [1,8] |

**Bất biến lưu trữ**:

~~~text
bit[i] = sum of a[j] for
         j = i-lowbit(i)+1 .. i
         using 1-based a
~~~

Khi sử dụng `int[]` hay `long[]` của Java, ta vẫn nhận chỉ số ngoài **0-based**, rồi cộng 1 trước khi đi vào BIT. Việc tách hai hệ chỉ số này cần được nói rõ để tránh lỗi off-by-one.

### Vì sao mỗi điểm chỉ liên quan O(log n) khối?

Các khối có kích thước theo lũy thừa của hai. Một tổng tiền tố được tách thành tối đa O(log n) khối không giao nhau. Khi cập nhật một phần tử, ta đi qua tối đa O(log n) khối chứa phần tử đó.

Số khối không phụ thuộc vào giá trị của các phần tử, nên số âm và số dương đều xử lý được đối với bài toán tổng thông thường.

### BIT không chỉ là “cây nhị phân tìm kiếm”

Fenwick Tree không sắp xếp khóa như BST. Nó là một cách tổ chức **các tổng tiền tố** theo cấu trúc bit của chỉ số, thích hợp khi phép gộp có thuộc tính cần thiết cho loại truy vấn đang dùng.

## 3. Quy ước 0-based và prefixExclusive

Để chương trình dễ sử dụng, toàn bộ API bài học dùng:

~~~text
a[0], a[1], ..., a[n-1]

prefixExclusive(end) = a[0]+...+a[end-1]
                       (end tu 0 den n)

sumInclusive(L,R)   = a[L]+...+a[R]
                       (0 <= L <= R < n)
~~~

Do đó:

~~~text
sumInclusive(L,R)
    = prefixExclusive(R+1)
    - prefixExclusive(L)
~~~

Tổng tiền tố rỗng có end=0 bằng 0. Tổng cả mảng có end=n.

### Đổi chỉ số vào Fenwick

Để cập nhật a[index] ở API 0-based, vị trí BIT đầu tiên cần sửa là:

~~~text
i = index + 1
~~~

Để lấy prefixExclusive(end), ta bắt đầu từ:

~~~text
i = end
~~~

Không cần cộng 1 khi hỏi tổng với đầu cuối **exclusive**, bởi `end` chính là số phần tử đầu tiên cần gộp.

### Tại sao điều kiện biên quan trọng?

- n=0: `prefixExclusive(0)=0` hợp lệ; không có điểm nào hợp lệ để cập nhật hay hỏi đoạn không rỗng.
- `sumInclusive(0,0)` hợp lệ khi n≥1.
- `sumInclusive(L,R)` với L>R bị từ chối trong demo; nếu bài cho phép đoạn rỗng, phải định nghĩa lại API và trả 0 một cách nhất quán.
- `prefixExclusive(n)` hợp lệ, nhưng `prefixExclusive(n+1)` không hợp lệ.
- `[L,R]` là đoạn đóng, không được quên R+1 khi tính tổng.

## 4. Cộng một điểm và hỏi tổng tiền tố

Mỗi lần tăng a[index] một lượng delta, ta phải tăng cùng delta cho **mọi khối Fenwick chứa a[index]**.

Giả mã cập nhật:

~~~text
add(index, delta):
    require 0 <= index < n

    i = index + 1
    while i <= n:
        bit[i] += delta
        i += lowbit(i)
~~~

Giả mã tổng tiền tố:

~~~text
prefixExclusive(end):
    require 0 <= end <= n

    answer = 0
    i = end
    while i > 0:
        answer += bit[i]
        i -= lowbit(i)

    return answer
~~~

### Giải thích bước nhảy khi cập nhật

Từ một chỉ số BIT i, bước `i += lowbit(i)` chuyển tới một khối lớn hơn cũng chứa phần tử vừa sửa. Tiếp tục cho đến khi i>n.

### Giải thích bước nhảy khi lấy prefix

Bước `i -= lowbit(i)` loại bỏ chính khối `[i-lowbit(i)+1, i]` đã cộng vào kết quả, rồi tiếp tục với phần tiền tố còn lại. Các khối cộng lại không chồng nhau và phủ đúng `[1,end]`.

### Thời gian

Số bước tăng hoặc giảm chỉ số hữu hạn và tăng theo O(log n). Với n=1, mỗi thao tác chỉ cần một khối. Khi n lớn, BIT thường có hằng số nhỏ và bộ nhớ gọn.

### Một vòng lặp sai nguy hiểm

Nếu dùng chỉ số BIT **1-based** nhưng gọi `add(0,delta)` và viết:

~~~java
for (int i = 0; i <= n; i += i & -i) {
    // i van bang 0, khong bao gio tien
}
~~~

thì `lowbit(0)=0`, vòng lặp không tiến. Vì vậy code ngoài dùng 0-based nhưng luôn chuyển sang `i=index+1`.

## 5. Mô phỏng BIT với một mảng nhỏ

Cho:

~~~text
a = [2, -1, 3, 0, 4]
n = 5
~~~

Các khối Fenwick:

~~~text
bit[1] = a[0]                       = 2
bit[2] = a[0]+a[1]                  = 1
bit[3] = a[2]                       = 3
bit[4] = a[0]+a[1]+a[2]+a[3]       = 4
bit[5] = a[4]                       = 4
~~~

Tổng tiền tố độc quyền:

~~~text
prefixExclusive(0) = 0
prefixExclusive(1) = 2
prefixExclusive(2) = 1
prefixExclusive(3) = 4
prefixExclusive(4) = 4
prefixExclusive(5) = 8
~~~

Tổng đoạn `[1,3]`:

~~~text
a[1]+a[2]+a[3] = -1+3+0 = 2

prefixExclusive(4) - prefixExclusive(1)
= 4 - 2
= 2
~~~

Nếu cập nhật **SET(2,7)**, giá trị a[2] tăng từ 3 lên 7, tức delta=4:

~~~text
a = [2, -1, 7, 0, 4]

sumInclusive(1,3) = -1+7+0 = 6
sumInclusive(0,4) = 12
~~~

Sau đó **ADD(0,−2)**:

~~~text
a = [0, -1, 7, 0, 4]
sumInclusive(0,4) = 10
~~~

Cả hai loại thao tác chỉ sửa O(log n) khối, không cần xây lại toàn bộ cây.

## 6. Xây Fenwick: O(n log n) và O(n)

Một cách đơn giản để xây BIT ban đầu là:

~~~text
fenwick = empty BIT(n)

for i = 0..n-1:
    fenwick.add(i, a[i])
~~~

Do mỗi `add` O(log n), tổng là **O(n log n)**. Cách này dễ hiểu và phù hợp khi n không quá lớn.

Tuy nhiên có thể **build tuyến tính O(n)**. Đầu tiên lưu a[i−1] tại bit[i], rồi truyền tổng của mỗi khối tới khối cha theo thứ tự chỉ số tăng:

~~~text
for i = 1..n:
    bit[i] += a[i-1]

    parent = i + lowbit(i)
    if parent <= n:
        bit[parent] += bit[i]
~~~

**Bất biến của build tuyến tính:** khi xét i, `bit[i]` đã gom các đóng góp của những chỉ số nhỏ hơn có khối chuyển đến i. Đưa `bit[i]` lên `parent` giúp tổng ở parent tăng đủ một nhóm con; các nhóm được lan truyền theo i tăng dần.

Ví dụ n=5, sau khi build:

~~~text
bit = [unused, 2, 1, 3, 4, 4]
~~~

Việc so sánh `prefixExclusive(end)` giữa bản build O(n) và bản thêm từng phần tử O(n log n) cho mọi end là một test tốt.

### Khi nào cách build tuyến tính không áp dụng trực tiếp?

Cách trên giả định ta đã có **giá trị của mảng trạng thái Fenwick cần đại diện** tại mọi chỉ số. Nếu trạng thái là một mảng sai phân hoặc dữ liệu đã biến đổi, phải build từ **mảng biến đổi đúng**, không lấy mảng gốc theo thói quen.

Với trường hợp hai BIT ở phần sau, có thể xây nhanh từ sai phân d và mảng j·d[j], nhưng mã demo cố ý dùng các cập nhật cơ sở để dễ giải thích.

## 7. POINT SET, POINT ADD và sự khác biệt

Một BIT chuẩn chỉ biết cộng delta vào các tổng khối. Nếu đề yêu cầu:

~~~text
SET(index, newValue)
~~~

thì phải biết giá trị a[index] hiện hành:

~~~text
delta = newValue - a[index]
fenwick.add(index, delta)
a[index] = newValue
~~~

Nếu chỉ gọi `fenwick.add(index,newValue)`, chương trình thực hiện **cộng thêm** newValue chứ không phải **thay bằng** newValue.

### Ví dụ

~~~text
Ban dau a[2]=3
SET(2,7)

delta = 7-3 = 4
~~~

Điều này tương đương `ADD(2,4)` nhưng **không** tương đương `ADD(2,7)`.

### Bộ nhớ

Để hỗ trợ SET tiện lợi, ta lưu thêm **mảng giá trị hiện hành** bên cạnh BIT. Tổng vẫn O(n) bộ nhớ.

### Tràn số khi tính delta

Nếu `newValue` và `oldValue` là `int`, phải ép sang `long` **trước phép trừ**:

~~~java
long delta = (long) newValue - oldValue;
~~~

Nếu viết `(long)(newValue - oldValue)`, phép trừ đã có thể overflow trong `int` trước khi ép.

Mã dưới dùng `long` cho cả giá trị và tổng. Nó giả định kết quả mọi phép cộng/trừ/nhân vẫn nằm trong miền `long`; với dữ liệu có thể vượt 64-bit, cần kiểm tràn hoặc dùng kiểu số rộng hơn theo yêu cầu.

## 8. Mảng sai phân: biến cộng đoạn thành cộng điểm

Một phép biến đổi rất quan trọng là **difference array (mảng sai phân)**.

Với a[0..n−1], định nghĩa:

~~~text
d[0] = a[0]

d[i] = a[i] - a[i-1],  i >= 1
~~~

Từ đó:

~~~text
a[i] = d[0] + d[1] + ... + d[i]
     = prefixInclusive(d,i)
~~~

Nói cách khác, **giá trị tại một điểm của a** chính là **tổng tiền tố của d**.

### Phép cộng cả đoạn

Muốn tăng tất cả a[i] với i∈[L,R] thêm delta:

~~~text
d[L] += delta

if R+1 < n:
    d[R+1] -= delta
~~~

Tại mọi vị trí i:

- Nếu i<L, tổng tiền tố của d không thêm gì.
- Nếu L≤i≤R, tổng tiền tố có +delta nhưng chưa gặp −delta.
- Nếu i>R, cả +delta và −delta đã xuất hiện, triệt tiêu nhau.

Đó chính là hiệu ứng range add mong muốn.

### Ý nghĩa đối với Fenwick

Nếu BIT lưu **d** chứ không phải a:

~~~text
rangeAdd(L,R,delta):
    bitD.add(L,+delta)
    if R+1 < n:
        bitD.add(R+1,-delta)

pointGet(i):
    return bitD.prefixExclusive(i+1)
~~~

Mỗi rangeAdd dùng nhiều nhất hai thao tác điểm, mỗi pointGet dùng một tổng tiền tố, nên cả hai đều **O(log n)**.

### Đây là trạng thái khác BIT thông thường

BIT trên a: lấy prefix để ra **tổng của a**.

BIT trên d: lấy prefix để ra **một giá trị a[i]**.

Nếu hỏi tổng đoạn của a bằng `BIT(d).sumInclusive(L,R)`, ta đang cộng các **sai phân**, không phải cộng các giá trị gốc, nên sẽ nhận đáp án sai.

## 9. Mô phỏng cộng đoạn – hỏi điểm

Lấy lại:

~~~text
a = [2, -1, 3, 0, 4]
~~~

Sai phân:

~~~text
d = [2, -3, 4, -3, 4]
~~~

Kiểm tra:

~~~text
prefix(d,0) = 2
prefix(d,1) = -1
prefix(d,2) = 3
prefix(d,3) = 0
prefix(d,4) = 4
~~~

Cộng +5 vào đoạn `[1,3]`:

~~~text
d[1] += 5
d[4] -= 5

a = [2, 4, 8, 5, 4]

pointGet(2) = 8
pointGet(4) = 4
~~~

Sau đó cộng −2 vào **toàn mảng** `[0,4]`:

~~~text
d[0] -= 2
R+1 = 5 == n => khong co vi tri de tru phia sau

a = [0, 2, 6, 3, 2]

pointGet(0) = 0
pointGet(3) = 3
~~~

Bước không ghi dấu −delta tại n là chủ ý: mảng chỉ có các vị trí 0..n−1, hiệu ứng ngoài cuối mảng không cần lưu.

### Vì sao không thể bớt một đầu cập nhật?

Nếu chỉ cộng `d[L]+=delta` mà quên trừ `d[R+1]`, các phần tử **sau R** cũng tăng. Đây là lỗi “range add bị lan tới cuối mảng” rất thường gặp.

## 10. Hai Fenwick: cộng đoạn và hỏi tổng đoạn

Mô hình khó hơn:

~~~text
rangeAdd(L,R,delta)
rangeSum(L,R)
~~~

Cả hai thao tác đều tác động hoặc đọc **một đoạn**. BIT đơn trên a không cập nhật đoạn nhanh; BIT đơn trên d chỉ trả **pointGet** nhanh. Ta cần một phép biến đổi sâu hơn dùng **hai BIT**.

### Dẫn xuất từ sai phân

Với d như phần trước:

~~~text
a[i] = SUM_{j=0..i} d[j]
~~~

Gọi P(e) là tổng **e phần tử đầu** của a:

~~~text
P(e) = SUM_{i=0..e-1} a[i]
     = SUM_{i=0..e-1} SUM_{j=0..i} d[j]
~~~

Đổi thứ tự tổng: mỗi d[j] với j<e xuất hiện trong a[j],...,a[e−1], tức **e−j lần**:

~~~text
P(e) = SUM_{j=0..e-1} (e-j)*d[j]

     = e * SUM_{j=0..e-1} d[j]
       - SUM_{j=0..e-1} j*d[j]
~~~

Ta xây:

~~~text
B1: BIT luu d[j]
B2: BIT luu j*d[j]    // j la chi so 0-based

prefixExclusive(e)
    = e * B1.prefixExclusive(e)
      - B2.prefixExclusive(e)
~~~

Và từ đó:

~~~text
sumInclusive(L,R)
    = prefixExclusive(R+1)
      - prefixExclusive(L)
~~~

### Biến đổi rangeAdd vào hai BIT

Một thao tác cộng delta trên a[L..R] thay đổi sai phân ở tối đa hai vị trí:

~~~text
d[L] += delta
d[R+1] -= delta  (neu R+1<n)
~~~

Nên cập nhật:

~~~text
B1.add(L, +delta)
B2.add(L, +delta*L)

if R+1 < n:
    B1.add(R+1, -delta)
    B2.add(R+1, -delta*(R+1))
~~~

**Đây là công thức 0-based.** Nếu đọc tài liệu viết nội bộ 1-based, nhiều công thức sẽ dùng `(L−1)` hoặc `R` ở BIT thứ hai; các phiên bản đó có thể tương đương sau đổi hệ chỉ số, nhưng **không được trộn hai công thức**.

### Độ phức tạp

- Cập nhật đoạn: tối đa bốn `BIT.add`, O(log n).
- Tổng tiền tố: hai `BIT.prefix`, O(log n).
- Tổng đoạn: hai tiền tố, O(log n).
- Bộ nhớ: hai mảng BIT mỗi mảng n+1, vẫn **O(n)**.

### Điều kiện số học

B2 chứa các tích `j*d[j]`; P(e) chứa tích `e*prefix(B1)`. Tổng trung gian có thể lớn hơn từng phần tử và thậm chí lớn hơn đáp án cuối. Nếu ràng buộc đầu vào cho phép vượt 64-bit, phải xem xét **overflow trong tính toán trung gian**, không chỉ overflow của đáp án. Bài Java giả định mọi phép tính trung gian nằm trong `long`.

## 11. Ví dụ số cho hai BIT

Khởi tạo:

~~~text
a = [2, -1, 3, 0, 4]
total = 8
~~~

Cập nhật:

~~~text
rangeAdd(1,3,+5)
~~~

Sau update:

~~~text
a = [2,4,8,5,4]

sumInclusive(0,4) = 23
sumInclusive(1,3) = 17
~~~

Kiểm qua công thức sai phân:

~~~text
d = [2, 2, 4, -3, -1]
j*d[j] = [0, 2, 8, -9, -4]

P(5) = 5*(2+2+4-3-1) - (0+2+8-9-4)
     = 5*4 - (-3)
     = 23

P(4) = 4*(2+2+4-3) - (0+2+8-9)
     = 4*5 - 1
     = 19

P(1) = 1*2 - 0 = 2
sumInclusive(1,3) = P(4)-P(1) = 17
~~~

Sau đó:

~~~text
rangeAdd(0,4,-2)

a = [0,2,6,3,2]

sumInclusive(0,4) = 13
sumInclusive(0,2) = 8
sumInclusive(3,4) = 5
~~~

Một đoạn chạm ranh giới cuối `[0,n−1]` vẫn hợp lệ: chỉ cập nhật sai phân ở L vì R+1 ngoài mảng. Đoạn chỉ có một điểm `[i,i]` cũng hợp lệ và tương đương cộng một điểm.

### Nếu chỉ cần range add/point get

Không nên tự động dùng hai BIT khi bài chỉ hỏi pointGet. Một BIT sai phân ở phần 8 đơn giản hơn và tiết kiệm hằng số/bộ nhớ.

## 12. Tìm vị trí đầu tiên có tổng tiền tố đủ lớn

Một ứng dụng nâng cao của Fenwick: mảng a chứa **tần suất hoặc trọng số không âm**, và muốn tìm vị trí nhỏ nhất `i` thỏa:

~~~text
a[0] + ... + a[i] >= target
~~~

Đây là thao tác kiểu **order statistic / find kth** cho các tần suất, ví dụ tìm phần tử thứ k trong multiset được lưu theo chỉ số đã nén.

### Điều kiện tiên quyết

Tất cả giá trị đóng góp phải **không âm** để tổng tiền tố không giảm. Nếu có giá trị âm, tổng tiền tố có thể tăng rồi giảm, thuật toán đi theo khối kiểu binary lifting không còn bảo đảm tìm vị trí đầu tiên thỏa ngưỡng.

Giả sử:

~~~text
freq = [0,2,0,3,1]
prefix inclusive = [0,2,2,5,6]
~~~

Kết quả:

| target | Chỉ số 0-based đầu tiên với prefix ≥ target |
| ---: | ---: |
| 1 | 1 |
| 2 | 1 |
| 3 | 3 |
| 5 | 3 |
| 6 | 4 |
| 7 | Không tồn tại |

Mã demo trả `−1` nếu `target > tổng tần suất` và từ chối `target≤0`. Điều kiện target dương giúp định nghĩa rõ thứ tự phần tử thứ k.

### Binary lifting trên các khối BIT

Duy trì một prefix đã chắc chắn có tổng **nhỏ hơn target**. Thử nhảy các lũy thừa hai từ lớn xuống nhỏ; nếu nối thêm khối mới mà tổng vẫn nhỏ hơn target, chấp nhận bước nhảy và trừ tổng khối khỏi ngưỡng còn lại.

~~~text
position = 0    // so luong phan tu da bo qua
remaining = target

for jump = highest power of two <= n; jump > 0; jump /= 2:
    next = position + jump

    if next <= n AND bit[next] < remaining:
        position = next
        remaining -= bit[next]

return position   // chi so 0-based
~~~

Trước đó phải kiểm `target<=total`; nếu vượt, trả −1.

Thuật toán không gọi `prefixExclusive` O(log n) ở mỗi bước tìm kiếm, mà tận dụng trực tiếp các tổng khối `bit[next]`, nên tìm được trong **O(log n)**, sau khi đã biết tổng hiện tại của cây.

### Khác với binary search trên prefix

Một cách khác là binary search chỉ số và gọi `prefixExclusive(mid)`, mất O(log² n). Binary lifting Fenwick có thể đạt O(log n). Cả hai vẫn đòi tổng tiền tố đơn điệu.

## 13. Khi phép biến đổi áp dụng được và khi không

Fenwick cho tổng dựa trên các tính chất của phép cộng:

- Kết hợp: `(a+b)+c=a+(b+c)`.
- Phần tử đơn vị 0.
- Có phép nghịch đảo của cộng: để lấy tổng đoạn từ hai tổng tiền tố, ta **trừ** được.
- Khi update, có thể lan truyền lượng thay đổi delta vào các khối liên quan.

Với phép **XOR**, các ý tưởng tổng tiền tố và nghịch đảo cũng có biến thể tương tự vì XOR tự nghịch đảo. Nhưng công thức **hai BIT cho range add/range sum** trong bài được dẫn xuất cho **phép cộng số học** và trọng số chỉ số; không được tự thay `+` bằng XOR trong mọi công thức.

### Vì sao range minimum khác range sum?

Nếu chỉ lưu min của các prefix, bạn không thể lấy min(L,R) bằng cách trừ hai min prefix. Với phép min, không tồn tại nghịch đảo tương ứng cho kiểu truy vấn này.

Có những biến thể BIT đặc biệt hỗ trợ các loại min/monotone update, nhưng chúng có điều kiện riêng; một BIT tổng cơ bản **không cho range min với point assignment tùy ý**.

### Khi nên dùng Segment Tree

Segment Tree thích hợp hơn nếu bài yêu cầu:

- Range min/max với point set.
- Range assign + range sum.
- Range add + range min/max.
- Các truy vấn gộp phức tạp cần lưu nhiều thông tin.
- Lazy propagation với các loại update không biến đổi thành hai phép add trên sai phân một cách đơn giản.

**Không nên** ưu tiên BIT chỉ vì code ngắn nếu trạng thái cần duy trì không phù hợp.

## 14. Chọn cấu trúc theo bảng thao tác

| Dữ liệu và thao tác | Cấu trúc tự nhiên | Chi phí chính |
| --- | --- | --- |
| Mảng tĩnh, chỉ hỏi tổng đoạn | Prefix sum | Build O(n), query O(1) |
| Point add + prefix sum | Một BIT | Mỗi thao tác O(log n) |
| Point set + range sum | BIT + mảng hiện hành | Update/query O(log n) |
| Range add + point get | BIT trên sai phân | Update/query O(log n) |
| Range add + range sum | Hai BIT | Update/query O(log n) |
| Point add + range min | Segment Tree phù hợp hơn | O(log n) |
| Range assign + range sum | Segment Tree lazy | O(log n) thường gặp |
| Static range minimum | Sparse Table cho RMQ | Tiền xử lý, query O(1) với min |
| Thêm/bớt tần suất theo khóa nén, hỏi phần tử thứ k | BIT tần suất | Update và find kth O(log n) |
| Truy vấn theo tọa độ lớn nhưng số vị trí ít | Coordinate compression + BIT | Nén rồi dùng BIT |
| Đếm phần tử theo ngưỡng, batch biết trước | Sort offline + BIT | Phụ thuộc số sự kiện/query |

Không phải công cụ nào có O(log n) cũng giống nhau. So cả **hợp đồng thao tác**, độ phức tạp bộ nhớ, khả năng online, kích thước code, cách xử lý dữ liệu âm và nhu cầu khôi phục trạng thái.

## 15. Java 17: các biến thể BIT trong một chương trình độc lập

Chương trình `FenwickTransformDemo.java` bao gồm:

1. `Fenwick`: point add, prefixExclusive, rangeInclusive, build tuyến tính, lowerBound trên tần suất không âm.
2. `PointSetRangeSum`: giữ bản sao mảng và hỗ trợ point SET, point ADD, range SUM.
3. `RangeAddPointGet`: một BIT trên sai phân, cộng đoạn và hỏi điểm.
4. `RangeAddRangeSum`: hai BIT, cộng đoạn và lấy tổng đoạn.
5. Một demo có giá trị âm, đoạn chạm hai đầu, SET/ADD, find kth và các trường hợp invalid.
6. Bộ test vét cạn độc lập trên mảng nhỏ và tần suất, không cần thư viện bên ngoài Java 17.

**Quy ước thống nhất**: tất cả chỉ số API 0-based; `prefixExclusive(end)` không lấy phần tử tại `end`; các đoạn `[left,right]` là đoạn đóng. Giá trị và tổng dùng `long` trong những miền không gây overflow ở kết quả **và phép tính trung gian**.

Lưu toàn bộ thành **`FenwickTransformDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class FenwickTransformDemo {

    private static void checkRange(int n, int left, int right) {
        if (left < 0 || left > right || right >= n) {
            throw new IllegalArgumentException(
                    "range out of bounds");
        }
    }

    private static final class Fenwick {
        private final int n;
        private final long[] bit;

        Fenwick(int n) {
            if (n < 0) {
                throw new IllegalArgumentException(
                        "negative size");
            }
            this.n = n;
            this.bit = new long[n + 1];
        }

        static Fenwick fromArrayLinear(long[] values) {
            Objects.requireNonNull(values, "values");
            Fenwick tree = new Fenwick(values.length);
            for (int i = 1; i <= values.length; i++) {
                tree.bit[i] += values[i - 1];
                int parent = i + (i & -i);
                if (parent <= tree.n) {
                    tree.bit[parent] += tree.bit[i];
                }
            }
            return tree;
        }

        void add(int index, long delta) {
            if (index < 0 || index >= n) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            for (int i = index + 1; i <= n; i += i & -i) {
                bit[i] += delta;
            }
        }

        long prefixExclusive(int end) {
            if (end < 0 || end > n) {
                throw new IllegalArgumentException(
                        "prefix out of bounds");
            }
            long result = 0L;
            for (int i = end; i > 0; i -= i & -i) {
                result += bit[i];
            }
            return result;
        }

        long rangeInclusive(int left, int right) {
            checkRange(n, left, right);
            return prefixExclusive(right + 1)
                    - prefixExclusive(left);
        }

        // Only valid if all represented frequencies are >= 0.
        // Find first zero-based index whose inclusive prefix
        // reaches target. -1 means target exceeds total.
        int lowerBound(long target) {
            if (target <= 0L) {
                throw new IllegalArgumentException(
                        "target must be positive");
            }
            if (target > prefixExclusive(n)) {
                return -1;
            }

            int position = 0;
            long remaining = target;
            int jump = Integer.highestOneBit(n);

            while (jump > 0) {
                long candidate = (long) position + jump;
                if (candidate <= n
                        && bit[(int) candidate] < remaining) {
                    position = (int) candidate;
                    remaining -= bit[position];
                }
                jump >>= 1;
            }
            return position;
        }
    }

    private static final class PointSetRangeSum {
        private final long[] values;
        private final Fenwick tree;

        PointSetRangeSum(long[] initial) {
            Objects.requireNonNull(initial, "initial");
            this.values = initial.clone();
            this.tree = Fenwick.fromArrayLinear(values);
        }

        void set(int index, long newValue) {
            if (index < 0 || index >= values.length) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            long delta = newValue - values[index];
            tree.add(index, delta);
            values[index] = newValue;
        }

        void add(int index, long delta) {
            if (index < 0 || index >= values.length) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            tree.add(index, delta);
            values[index] += delta;
        }

        long prefixExclusive(int end) {
            return tree.prefixExclusive(end);
        }

        long sum(int left, int right) {
            return tree.rangeInclusive(left, right);
        }
    }

    private static final class RangeAddPointGet {
        private final int n;
        private final Fenwick differences;

        RangeAddPointGet(long[] initial) {
            Objects.requireNonNull(initial, "initial");
            n = initial.length;
            long[] diff = new long[n];
            for (int i = 0; i < n; i++) {
                diff[i] = initial[i]
                        - (i == 0 ? 0L : initial[i - 1]);
            }
            differences = Fenwick.fromArrayLinear(diff);
        }

        void rangeAdd(int left, int right, long delta) {
            checkRange(n, left, right);
            differences.add(left, delta);
            if (right + 1 < n) {
                differences.add(right + 1, -delta);
            }
        }

        long pointGet(int index) {
            if (index < 0 || index >= n) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            return differences.prefixExclusive(index + 1);
        }
    }

    private static final class RangeAddRangeSum {
        private final int n;
        private final Fenwick first;
        private final Fenwick weighted;

        RangeAddRangeSum(long[] initial) {
            Objects.requireNonNull(initial, "initial");
            n = initial.length;
            first = new Fenwick(n);
            weighted = new Fenwick(n);

            // Simple initialization: a single-point range add.
            // Can also build both BITs linearly from differences.
            for (int i = 0; i < n; i++) {
                if (initial[i] != 0L) {
                    rangeAdd(i, i, initial[i]);
                }
            }
        }

        void rangeAdd(int left, int right, long delta) {
            checkRange(n, left, right);

            first.add(left, delta);
            weighted.add(left, delta * left);

            if (right + 1 < n) {
                first.add(right + 1, -delta);
                weighted.add(right + 1,
                        -delta * (right + 1));
            }
        }

        long prefixExclusive(int end) {
            if (end < 0 || end > n) {
                throw new IllegalArgumentException(
                        "prefix out of bounds");
            }
            return end * first.prefixExclusive(end)
                    - weighted.prefixExclusive(end);
        }

        long sum(int left, int right) {
            checkRange(n, left, right);
            return prefixExclusive(right + 1)
                    - prefixExclusive(left);
        }
    }

    private static long naiveSum(
            long[] values, int left, int right) {
        long total = 0L;
        for (int i = left; i <= right; i++) {
            total += values[i];
        }
        return total;
    }

    private static long verifyOnlineSums(
            PointSetRangeSum online, long[] expected) {
        long checked = 0;
        for (int left = 0; left < expected.length; left++) {
            long direct = 0L;
            for (int right = left;
                    right < expected.length; right++) {
                direct += expected[right];
                if (online.sum(left, right) != direct) {
                    throw new AssertionError(
                            "point-update BIT differs from naive");
                }
                checked++;
            }
        }
        return checked;
    }

    private record TestCounts(
            long arrays, long initialRanges,
            long onlineSumChecks, long rangeUpdates,
            long pointGetChecks, long dualSumChecks,
            long frequencyArrays, long rankChecks) {}

    private static TestCounts verifyExhaustive() {
        long arrays = 0L;
        long initialRanges = 0L;
        long onlineSumChecks = 0L;
        long rangeUpdates = 0L;
        long pointGetChecks = 0L;
        long dualSumChecks = 0L;

        // All arrays length 0..5, values in {-1,0,1}.
        for (int n = 0; n <= 5; n++) {
            int cases = 1;
            for (int i = 0; i < n; i++) {
                cases *= 3;
            }

            for (int code = 0; code < cases; code++) {
                long[] values = new long[n];
                int number = code;
                for (int i = 0; i < n; i++) {
                    values[i] = number % 3 - 1;
                    number /= 3;
                }

                // Compare linear build with point-add build
                // and independently computed prefix sums.
                Fenwick linear = Fenwick.fromArrayLinear(values);
                Fenwick iterative = new Fenwick(n);
                for (int i = 0; i < n; i++) {
                    iterative.add(i, values[i]);
                }

                long directPrefix = 0L;
                for (int end = 0; end <= n; end++) {
                    if (end > 0) {
                        directPrefix += values[end - 1];
                    }
                    if (linear.prefixExclusive(end)
                            != directPrefix
                            || iterative.prefixExclusive(end)
                               != directPrefix) {
                        throw new AssertionError(
                                "Fenwick construction mismatch");
                    }
                }

                PointSetRangeSum online =
                        new PointSetRangeSum(values);
                initialRanges += (long) n * (n + 1) / 2;
                onlineSumChecks += verifyOnlineSums(
                        online, values);

                long[] changed = values.clone();
                for (int index = 0; index < n; index++) {
                    online.set(index, 2L);
                    changed[index] = 2L;
                    onlineSumChecks += verifyOnlineSums(
                            online, changed);
                }

                // For every possible update interval, initialize
                // from original and add +2 just to that interval.
                for (int left = 0; left < n; left++) {
                    for (int right = left;
                            right < n; right++) {
                        RangeAddPointGet point =
                                new RangeAddPointGet(values);
                        RangeAddRangeSum dual =
                                new RangeAddRangeSum(values);
                        long[] after = values.clone();

                        point.rangeAdd(left, right, 2L);
                        dual.rangeAdd(left, right, 2L);
                        for (int i = left; i <= right; i++) {
                            after[i] += 2L;
                        }
                        rangeUpdates++;

                        for (int i = 0; i < n; i++) {
                            if (point.pointGet(i) != after[i]) {
                                throw new AssertionError(
                                        "range-add point-get mismatch");
                            }
                            pointGetChecks++;
                        }

                        for (int ql = 0; ql < n; ql++) {
                            for (int qr = ql; qr < n; qr++) {
                                if (dual.sum(ql, qr)
                                        != naiveSum(after, ql, qr)) {
                                    throw new AssertionError(
                                            "two-BIT range sum mismatch");
                                }
                                dualSumChecks++;
                            }
                        }
                    }
                }
                arrays++;
            }
        }

        long frequencyArrays = 0L;
        long rankChecks = 0L;

        // All nonnegative frequency arrays length 0..6,
        // each frequency in {0,1,2}.
        for (int n = 0; n <= 6; n++) {
            int cases = 1;
            for (int i = 0; i < n; i++) {
                cases *= 3;
            }

            for (int code = 0; code < cases; code++) {
                long[] frequency = new long[n];
                int number = code;
                long total = 0L;
                for (int i = 0; i < n; i++) {
                    frequency[i] = number % 3;
                    number /= 3;
                    total += frequency[i];
                }

                Fenwick fenwick =
                        Fenwick.fromArrayLinear(frequency);
                for (long target = 1;
                        target <= total + 1; target++) {
                    int expectedIndex = -1;
                    long prefix = 0L;
                    for (int i = 0; i < n; i++) {
                        prefix += frequency[i];
                        if (prefix >= target) {
                            expectedIndex = i;
                            break;
                        }
                    }

                    if (fenwick.lowerBound(target)
                            != expectedIndex) {
                        throw new AssertionError(
                                "Fenwick lowerBound mismatch");
                    }
                    rankChecks++;
                }
                frequencyArrays++;
            }
        }

        if (arrays != 364L
                || initialRanges != 4647L
                || onlineSumChecks != 26655L
                || rangeUpdates != 4647L
                || pointGetChecks != 22008L
                || dualSumChecks != 63831L
                || frequencyArrays != 1093L
                || rankChecks != 7108L) {
            throw new AssertionError(
                    "exhaustive count mismatch");
        }

        return new TestCounts(
                arrays, initialRanges, onlineSumChecks,
                rangeUpdates, pointGetChecks, dualSumChecks,
                frequencyArrays, rankChecks);
    }

    public static void main(String[] args) {
        long[] original = {2, -1, 3, 0, 4};

        PointSetRangeSum online =
                new PointSetRangeSum(original);

        System.out.println("initial prefix 5 = "
                + online.prefixExclusive(5));
        System.out.println("initial range [1,3] = "
                + online.sum(1, 3));

        online.set(2, 7L);
        System.out.println("after SET(2,7) [1,3] = "
                + online.sum(1, 3));

        online.add(0, -2L);
        System.out.println("after ADD(0,-2) total = "
                + online.sum(0, 4));
        System.out.println("original array unchanged = "
                + Arrays.equals(original,
                        new long[] {2, -1, 3, 0, 4}));

        Fenwick linear = Fenwick.fromArrayLinear(original);
        Fenwick iterative = new Fenwick(original.length);
        for (int i = 0; i < original.length; i++) {
            iterative.add(i, original[i]);
        }
        boolean equal = true;
        for (int end = 0; end <= original.length; end++) {
            if (linear.prefixExclusive(end)
                    != iterative.prefixExclusive(end)) {
                equal = false;
            }
        }
        System.out.println(
                "linear build equals point-add build = " + equal);

        RangeAddPointGet points =
                new RangeAddPointGet(original);
        points.rangeAdd(1, 3, 5L);
        System.out.println(
                "range-add/point after +5: index2="
                + points.pointGet(2)
                + ", index4=" + points.pointGet(4));
        points.rangeAdd(0, 4, -2L);
        System.out.println(
                "range-add/point after -2: index0="
                + points.pointGet(0)
                + ", index3=" + points.pointGet(3));

        RangeAddRangeSum dual =
                new RangeAddRangeSum(original);
        dual.rangeAdd(1, 3, 5L);
        System.out.println(
                "two BIT after +5: total="
                + dual.sum(0, 4)
                + ", range[1,3]=" + dual.sum(1, 3));
        dual.rangeAdd(0, 4, -2L);
        System.out.println(
                "two BIT after -2: total="
                + dual.sum(0, 4)
                + ", range[0,2]=" + dual.sum(0, 2)
                + ", range[3,4]=" + dual.sum(3, 4));

        Fenwick frequencies = Fenwick.fromArrayLinear(
                new long[] {0, 2, 0, 3, 1});
        System.out.println(
                "prefix lowerBound: 1->"
                + frequencies.lowerBound(1L)
                + ", 2->" + frequencies.lowerBound(2L)
                + ", 3->" + frequencies.lowerBound(3L)
                + ", 5->" + frequencies.lowerBound(5L)
                + ", 6->" + frequencies.lowerBound(6L)
                + ", 7->" + frequencies.lowerBound(7L));

        try {
            online.sum(4, 5);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid range: " + error.getMessage());
        }
        try {
            dual.rangeAdd(3, 2, 1L);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid update: " + error.getMessage());
        }
        try {
            frequencies.lowerBound(0L);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid rank: " + error.getMessage());
        }

        System.out.println(
                "empty prefix = "
                + new Fenwick(0).prefixExclusive(0));

        TestCounts counts = verifyExhaustive();
        System.out.println(
                "exhaustive arrays = " + counts.arrays());
        System.out.println(
                "exhaustive initial ranges = "
                + counts.initialRanges());
        System.out.println(
                "exhaustive online sum checks = "
                + counts.onlineSumChecks());
        System.out.println(
                "exhaustive range updates = "
                + counts.rangeUpdates());
        System.out.println(
                "exhaustive point-get checks = "
                + counts.pointGetChecks());
        System.out.println(
                "exhaustive two-BIT sum checks = "
                + counts.dualSumChecks());
        System.out.println(
                "exhaustive frequency arrays = "
                + counts.frequencyArrays());
        System.out.println(
                "exhaustive rank checks = "
                + counts.rankChecks());
        System.out.println("all checks passed = true");
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac FenwickTransformDemo.java
java FenwickTransformDemo
~~~

**Stdout được tính xác định từ các ví dụ và các vòng test exhaustive:**

~~~text
initial prefix 5 = 8
initial range [1,3] = 2
after SET(2,7) [1,3] = 6
after ADD(0,-2) total = 10
original array unchanged = true
linear build equals point-add build = true
range-add/point after +5: index2=8, index4=4
range-add/point after -2: index0=0, index3=3
two BIT after +5: total=23, range[1,3]=17
two BIT after -2: total=13, range[0,2]=8, range[3,4]=5
prefix lowerBound: 1->1, 2->1, 3->3, 5->3, 6->4, 7->-1
invalid range: range out of bounds
invalid update: range out of bounds
invalid rank: target must be positive
empty prefix = 0
exhaustive arrays = 364
exhaustive initial ranges = 4647
exhaustive online sum checks = 26655
exhaustive range updates = 4647
exhaustive point-get checks = 22008
exhaustive two-BIT sum checks = 63831
exhaustive frequency arrays = 1093
exhaustive rank checks = 7108
all checks passed = true
~~~

### Hợp đồng của mã demo

- Đây là chương trình **độc lập**, không phải các đoạn mã thiếu lớp.
- Mọi input dùng cho test nằm trong miền số nhỏ, đủ để các phép tính long không overflow.
- Những phương pháp private được gọi ngay từ `main` để xác nhận cơ chế, không cần thư viện test.
- Việc dùng `long[]` không có nghĩa các tích `index*delta` hay tổng nhóm không thể tràn; người dùng phải áp dụng ràng buộc dữ liệu phù hợp.
- Nếu một thao tác invalid, chương trình ném exception trước khi thay đổi các BIT của thao tác đó; các phép tính overflow ngoài hợp đồng thì không có cơ chế rollback transaction.
- `lowerBound` chỉ đúng khi tần suất không âm; code không kiểm tính không âm tại mỗi lời gọi vì đó là **tiền điều kiện thuật toán**.

## 16. Kiểm thử exhaustive bằng oracle khác ý tưởng

Một test đáng tin không chỉ chạy một ví dụ rồi nhìn tổng. Bài này xây **oracle** bằng phép cộng vòng lặp trực tiếp trên mảng thường, không dùng logic Fenwick để tính kết quả mong muốn.

### Bộ mảng tổng và cập nhật

Sinh mọi mảng độ dài n=0..5, mỗi phần tử lấy trong {−1,0,1}:

~~~text
3^0 + 3^1 + 3^2 + 3^3 + 3^4 + 3^5
= 1 + 3 + 9 + 27 + 81 + 243
= 364 arrays
~~~

Mỗi mảng độ dài n có:

~~~text
n*(n+1)/2
~~~

đoạn đóng không rỗng.

Các nhóm kiểm:

1. **Build tuyến tính** so với build add từng điểm trên mọi prefix.
2. **Point SET** tuần tự từng vị trí về 2, sau mỗi SET kiểm mọi tổng đoạn bằng phép cộng trực tiếp.
3. **Range add/point get:** với mọi [L,R] hợp lệ của mảng ban đầu, tạo cấu trúc riêng, cộng +2 trên đoạn, rồi so từng pointGet với mảng sửa bằng vòng lặp.
4. **Range add/range sum:** tương tự, với mỗi cập nhật đoạn, kiểm tổng của **mọi** đoạn hỏi sau cập nhật bằng phép cộng trực tiếp.

Số lượng được đếm độc lập:

| Chỉ tiêu | Số lần |
| --- | ---: |
| Mảng giá trị n≤5 | 364 |
| Đoạn gốc [L,R] | 4.647 |
| Tổng đoạn online trước và sau từng SET | 26.655 |
| Trường hợp cập nhật một đoạn | 4.647 |
| Giá trị một điểm sau cập nhật đoạn | 22.008 |
| Tổng đoạn hai BIT sau cập nhật đoạn | 63.831 |

Dù mảng ngắn, số trường hợp đủ đa dạng để phát hiện lỗi off-by-one, cập nhật nhầm đầu phải, dùng sai d thay vì a hoặc tính sai hệ số của BIT thứ hai.

### Bộ lowerBound tần suất

Sinh mọi mảng độ dài 0..6, mỗi tần suất thuộc {0,1,2}:

~~~text
1+3+9+27+81+243+729
= 1093 frequency arrays
~~~

Với mỗi mảng, kiểm mọi target từ 1 đến `total+1`, so `Fenwick.lowerBound` với một vòng duyệt prefix từ trái qua phải.

Tổng số phép đối chứng:

~~~text
7108 lowerBound comparisons
~~~

Nhờ có nhiều giá trị 0, test bao gồm các đoạn tổng tiền tố bằng nhau, là nơi binary lifting dễ mắc lỗi dùng `<=` thay vì `<`.

### Không nhầm exhaustive với một chứng minh tổng quát

Bộ test liệt kê toàn bộ dữ liệu có miền giá trị và độ dài nhỏ cụ thể; nó **không thể tự chứng minh** đúng trên mọi n hoặc không có overflow cho mọi giá trị long. Chứng minh tổng quát phải dựa trên các bất biến khối BIT và các phép biến đổi sai phân đã trình bày.

## 17. Độ phức tạp và yếu tố triển khai

Với n phần tử, m thao tác point update/query và q thao tác range update/query:

| Thành phần | Thời gian | Bộ nhớ |
| --- | ---: | ---: |
| Fenwick rỗng | O(n) để cấp phát và zero-initialize | O(n) |
| Build từ n lần point add | O(n log n) | O(n) |
| Build tuyến tính | O(n) | O(n) |
| Point add | O(log n) | O(1) phụ |
| Prefix sum | O(log n) | O(1) phụ |
| Range sum từ hai prefix | O(log n) | O(1) phụ |
| Range add + point get với một BIT sai phân | O(log n)/thao tác | O(n) |
| Range add + range sum với hai BIT | O(log n)/thao tác | O(n) |
| LowerBound bằng binary lifting | O(log n) | O(1) phụ |
| q query tổng trên mảng tĩnh bằng prefix | O(n+q) tổng | O(n) |

### Bộ nhớ ẩn

Phiên bản `PointSetRangeSum` giữ thêm bản sao mảng để hỗ trợ SET. `RangeAddPointGet` giữ BIT sai phân, không giữ bản sao mảng gốc. `RangeAddRangeSum` giữ hai BIT.

Cả ba đều O(n), nhưng **hằng số bộ nhớ khác nhau**. Nếu n cực lớn, lựa chọn cấu trúc và kiểu số (`int` hay `long`) có thể ảnh hưởng đáng kể đến RAM.

### Khi n=0

Build vẫn hợp lệ và tổng tiền tố 0 bằng 0. Nhưng không thể `add(0,...)`, `pointGet(0)` hoặc hỏi đoạn `[0,0]`. Việc xử lý n=0 rõ ràng tránh vòng lặp bất thường và truy cập ra ngoài mảng.

### Khi n quá lớn hoặc giá trị quá rộng

Mảng Java có giới hạn chỉ số và bộ nhớ; việc cấp phát `long[n+1]` có thể vượt RAM hoặc gây overflow biểu thức n+1 ở miền biên rất lớn. Trong các bài thuật toán tiêu chuẩn, n phải được giới hạn phù hợp với khả năng cấp phát; giải pháp sparse/coordinate compression có thể phù hợp khi miền tọa độ lớn nhưng số điểm cần lưu ít.

`long` cho tổng là lựa chọn phổ biến, nhưng **không thay thế kiểm tra overflow** nếu nghiệp vụ có đầu vào 64-bit cực trị. Khi cần, dùng `Math.addExact`, `Math.multiplyExact` cho các phép tính nguyên có điều kiện, hoặc `BigInteger` nếu miền số đòi hỏi.

## 18. Fenwick trong truy vấn ngoại tuyến và nén tọa độ

Fenwick là **cấu trúc dữ liệu online**, nghĩa là khi đã biết hệ chỉ số, nó có thể nhận update/query theo thứ tự thực tế. Nhưng nó cũng là **công cụ bên trong** rất nhiều thuật toán offline.

### Ví dụ đếm nghịch thế

Với mảng a, một cặp (i,j) là nghịch thế nếu i<j nhưng a[i]>a[j]. Quét từ trái sang phải, giữ số lần xuất hiện những giá trị đã thấy bằng BIT tần suất.

Tại a[i]:

~~~text
number of previous values > a[i]
    = totalPreviouslySeen
      - count(previous values <= a[i])
~~~

Vì giá trị có thể âm/lớn, trước đó nén tọa độ:

1. Lấy các giá trị phân biệt và sort.
2. Gán mỗi giá trị một rank 0..d−1.
3. Dùng BIT trên d rank để lưu tần suất.
4. Khi xử lý a[i], hỏi số giá trị nhỏ hơn/bằng hoặc lớn hơn theo rank, rồi `add(rank,1)`.

Tổng thời gian O(n log n), bộ nhớ O(n). Nếu dữ liệu đã nằm trong miền chỉ số nhỏ, có thể bỏ bước nén.

### Ví dụ đếm distinct trên đoạn offline

Nếu đã biết trước các query `[L,R]`, có thể sort query theo R rồi quét mảng. Duy trì đánh dấu 1 ở **lần xuất hiện cuối cùng** của mỗi giá trị, xóa dấu ở lần trước, rồi dùng BIT trả tổng các dấu trên `[L,R]`.

Đây là một kỹ thuật **sắp xếp lại thứ tự xử lý query** để tận dụng update điểm + tổng đoạn. BIT bản thân không biết các query sẽ đến theo R; chính thuật toán offline tạo thứ tự phù hợp.

### Phân biệt hai bước thiết kế

- **Phép biến đổi dữ liệu/truy vấn:** biến bài toán gốc về các update và prefix/range sum.
- **Cấu trúc Fenwick:** thực hiện nhanh các phép update và prefix sum sau biến đổi.

Nếu phép biến đổi không đúng, BIT cài hoàn hảo vẫn trả đáp án sai cho bài gốc.

## 19. Lỗi phổ biến và các giới hạn

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng BIT i=0 trong vòng cập nhật 1-based | Vòng lặp không tiến | Dùng index+1 |
| Nhầm `[L,R]` với `[L,R)` | Sai một phần tử | Dùng prefix(R+1)−prefix(L) |
| Xây BIT từ sai phân nhưng hỏi như BIT trên a | Đáp án không phải tổng a | Định nghĩa lại trạng thái |
| Range add chỉ cập nhật d[L] | Tăng cả phần sau R | Trừ d[R+1] nếu hợp lệ |
| Cập nhật d[n] khi R=n−1 | Vượt mảng | Bỏ cập nhật ngoài miền |
| Point SET bị viết thành ADD(newValue) | Cộng sai delta | Dùng newValue−oldValue |
| Build tuyến tính đảo thứ tự duyệt | Chưa gom đủ khối trước khi lan lên cha | Duyệt i tăng |
| Hai BIT trộn công thức 0/1-based | Sai hệ số | Dẫn xuất từ d[j] và j·d[j] |
| Bỏ hệ số j trong B2 | Tổng đoạn sai | B2 lưu j*d[j] |
| Hỏi prefix(e) khi e<0 hoặc e>n | Ngoài miền | Validate |
| Dùng lowerBound khi có tần suất âm | Prefix không đơn điệu | Yêu cầu mọi frequency≥0 |
| `lowerBound` dùng `<=` sai tại target bằng prefix | Bỏ qua vị trí đầu tiên | Giữ điều kiện `< target` |
| Tưởng một BIT tổng hỗ trợ min/max tùy ý | Thiếu phép nghịch đảo | Chọn Segment Tree |
| Dùng int cho tổng lớn | Overflow | Dùng long và ràng buộc |
| Tích index*delta vượt long | Overflow ở B2 | Kiểm miền hoặc kiểu lớn |
| Test mã bằng mã tự tính cùng trạng thái | Có thể cùng sai | Oracle brute bằng mảng thường |
| Sort mảng gốc để nén tọa độ | Thay đổi thứ tự của các query đoạn | Nén trên bản sao/phép ánh xạ |
| Dùng 2 BIT khi chỉ cần range add/point get | Phức tạp thừa | Một BIT sai phân đủ |
| Không xét giá trị bằng nhau trong tìm rank | Sai thứ tự xuất hiện | Nén đồng nhất giá trị |
| Cập nhật và hỏi nhầm snapshot thời gian | Kết quả cũ/mới lẫn lộn | Giữ đúng thứ tự thao tác |
| Claim O(1) mọi thao tác Fenwick | Sai chi phí | O(log n), ngoại trừ build đặc biệt O(n) |
| Tưởng biết trước mọi query là điều kiện bắt buộc của BIT | Nhầm thuật toán và cấu trúc | BIT hỗ trợ online |
| Dùng dữ liệu cực lớn mà không kiểm RAM | OutOfMemoryError | Chọn nén/sparse/thiết kế khác |

### Kiểm tra thường xuyên bằng bất biến

Khi debug một update, có thể tính lại một vài prefix bằng vòng lặp mảng gốc. Khi debug hai BIT, kiểm:

~~~text
P(e) = e*sum(B1,0..e-1) - sum(B2,0..e-1)
~~~

với e=0,1,n và các điểm biên update. Với n nhỏ, duyệt mọi `[L,R]` sau **mỗi** update sẽ phát hiện rất nhiều lỗi chuyển đổi.

## 20. Bài tập thực hành và tổng kết

### Bài tập

1. Giải thích vì sao prefix sum tĩnh không phù hợp khi có nhiều point update.
2. Tính lowbit(i) cho i từ 1 đến 16.
3. Vẽ phạm vi mỗi `bit[i]` của Fenwick khi n=8.
4. Chứng minh `bit[i]` lưu tổng đoạn `[i−lowbit(i)+1,i]` trong hệ 1-based.
5. Viết vòng `add(index,delta)` với API 0-based.
6. Giải thích tại sao raw 1-based update với i=0 có thể lặp vô hạn.
7. Viết `prefixExclusive(end)` và mô phỏng các bước trừ lowbit.
8. Tính các bit trên mảng `[2,-1,3,0,4]`.
9. Tính `prefixExclusive(5)` và `sumInclusive(1,3)`.
10. Mô phỏng SET(2,7) bằng delta=4.
11. Phân biệt point ADD và point SET.
12. Chứng minh việc build bằng n lần add có O(n log n).
13. Cài build Fenwick tuyến tính O(n) và đối chiếu mọi prefix.
14. Nêu bất biến lan truyền `bit[i]` lên `parent`.
15. Tạo mảng sai phân d cho `[2,-1,3,0,4]`.
16. Chứng minh `a[i]=prefixInclusive(d,i)`.
17. Thực hiện `rangeAdd(1,3,+5)` bằng hai điểm trên d.
18. Giải thích tại sao R+1=n không được ghi vào BIT.
19. Cài range add/point get bằng một BIT trên d.
20. Tìm phản ví dụ cho việc chỉ cập nhật d[L] mà không trừ d[R+1].
21. Dẫn xuất tổng P(e) bằng cách đổi thứ tự hai dấu tổng.
22. Chứng minh `P(e)=e*prefix(B1,e)-prefix(B2,e)` với B2 lưu j*d[j].
23. Cài range add/range sum với hai BIT cho chỉ số 0-based.
24. Giải thích hệ số L và R+1 trong các cập nhật B2.
25. Tính bằng tay tổng sau hai update `[1,3]+5`, `[0,4]−2`.
26. So một BIT sai phân và hai BIT về chức năng/bộ nhớ.
27. Trình bày tiền điều kiện không âm của Fenwick lowerBound.
28. Tìm chỉ số rank 1,2,3,5,6 của `[0,2,0,3,1]`.
29. Giải thích vì sao rank 7 không tồn tại.
30. Cài lowerBound bằng binary lifting trong O(log n).
31. So lowerBound Fenwick với binary search + prefix O(log² n).
32. Tạo phản ví dụ khi có giá trị âm làm prefix không đơn điệu.
33. Giải thích vì sao min prefix không cho range min bằng phép trừ.
34. Chọn cấu trúc cho range assign + range sum.
35. Mở rộng API mảng rỗng với chỉ prefixExclusive(0).
36. Thiết kế kiểm thử cho đoạn một phần tử và hai đầu mảng.
37. Duyệt mọi mảng độ dài 0..5 với giá trị −1,0,1.
38. Kiểm point SET và mọi tổng đoạn bằng oracle cộng trực tiếp.
39. Với mỗi đoạn của mảng nhỏ, cộng +2 rồi kiểm range-add point-get.
40. Với cùng input, kiểm mọi range sum qua hai BIT sau update.
41. Giải thích ý nghĩa các con số 364, 4.647, 26.655, 22.008, 63.831.
42. Duyệt tần suất không âm dài 0..6, kiểm 7.108 truy vấn lowerBound.
43. Nêu một bài đếm nghịch thế dùng nén tọa độ và BIT tần suất.
44. Nêu một bài distinct đoạn offline dùng lần xuất hiện cuối và BIT.
45. Khi update xảy ra xen giữa query, trình bày yêu cầu giữ đúng thời gian.
46. Thiết kế API trả exception cho chỉ số và đoạn không hợp lệ.
47. Chọn kiểu số/kiểm tràn cho `delta*index` trong hai BIT.
48. So Fenwick, prefix tĩnh, Segment Tree và Mo theo workload cụ thể.
49. Chứng minh tính đúng của point add/prefix bằng các khối không chồng nhau.
50. Chứng minh tính đúng của hai BIT từ d[j] cho mọi đoạn hợp lệ.

### Checklist cuối

- Bài yêu cầu **point add, point set, range add, point get hay range sum**?
- Mảng có update hay chỉ query tĩnh?
- API dùng **0-based** bên ngoài và **1-based** bên trong BIT chưa?
- Truy vấn đoạn là `[L,R]` hay `[L,R)`?
- Có dùng `prefixExclusive(R+1)-prefixExclusive(L)` đúng chưa?
- Trạng thái BIT đang lưu **a**, **d**, hay **j·d[j]**?
- Nếu point SET, đã dùng delta từ giá trị hiện hành chưa?
- Nếu rangeAdd, đã xử lý cả d[L] và d[R+1] khi hợp lệ chưa?
- Nếu hai BIT, công thức có phù hợp hệ chỉ số không?
- Nếu find kth, mọi tần suất có không âm và target>0 không?
- Đã xử lý n=0, đoạn một phần tử, cập nhật chạm cuối mảng chưa?
- Có biết bound số để tránh overflow ở BIT và tích trọng số?
- Đã thử exhaustive bằng mảng oracle đơn giản độc lập chưa?
- Với truy vấn ngoại tuyến, đã chứng minh cách sort/biến đổi không thay đổi đáp án chưa?

**Kết luận:** Cây Fenwick duy trì các tổng khối để thực hiện **cộng điểm và hỏi tổng tiền tố O(log n)**. Phép biến đổi **sai phân** đổi **cộng đoạn → hai cập nhật điểm**, từ đó một BIT hỗ trợ **cộng đoạn/hỏi điểm**. Dẫn xuất lại tổng tiền tố từ sai phân cho công thức:

~~~text
P(e) = e*prefix(B1,e) - prefix(B2,e)

B1 luu d[j]
B2 luu j*d[j]          // j = 0-based
~~~

giúp hai BIT hỗ trợ cả **cộng đoạn và hỏi tổng đoạn O(log n)**. Khi mảng tĩnh chỉ có truy vấn tổng, prefix sum O(1) mỗi query có thể tốt hơn. Khi thao tác cần min/max, range assignment hoặc trạng thái phức tạp, Segment Tree hay cấu trúc khác có thể hợp lý hơn. Điều quan trọng nhất không phải học thuộc mẫu vòng BIT, mà là **biết đang lưu đại lượng gì, chứng minh phép biến đổi truy vấn và thống nhất hệ chỉ số**.
