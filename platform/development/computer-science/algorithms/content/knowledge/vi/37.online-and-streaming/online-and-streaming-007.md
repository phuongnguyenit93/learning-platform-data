# Theo dõi ứng viên chiếm đa số và phần tử xuất hiện thường xuyên

Trong bài toán **dữ liệu trực tuyến và luồng** (*online algorithms and data streams*), các bản ghi đến lần lượt. Ta muốn phát hiện những nhãn, ID hoặc sự kiện xuất hiện nhiều lần mà không giữ toàn bộ luồng trong bộ nhớ. Hai câu hỏi gần nhau nhưng **không đồng nhất** là:

1. Có phần tử nào **chiếm đa số nghiêm ngặt** (*strict majority*) — xuất hiện **nhiều hơn một nửa** tổng số bản ghi?
2. Có những phần tử nào **xuất hiện thường xuyên** (*frequent items/heavy hitters*) — xuất hiện **nhiều hơn \(n/k\)** lần, với tham số nguyên \(k\ge2\)?

Đối với câu hỏi thứ nhất, thuật toán **Boyer–Moore Majority Vote** duy trì **một ứng viên và một số đếm**, dùng O(1) bộ nhớ phụ, O(n) thời gian. Đối với câu hỏi thứ hai, thuật toán **Misra–Gries** duy trì tối đa **k−1 ứng viên có đếm**, dùng O(k) bộ nhớ phụ và bảo đảm **không bỏ sót bất kỳ phần tử nào có tần suất thật lớn hơn n/k**.

Có một phân biệt quyết định:

> **Tìm ứng viên không đồng nghĩa chứng minh ứng viên thực sự vượt ngưỡng.**

Boyer–Moore hoặc Misra–Gries có thể để lại **ứng viên giả**. Muốn **tần suất chính xác và kết quả đúng tuyệt đối**, thường cần **duyệt lại nguồn lần hai** hoặc có khả năng truy cập lại dữ liệu. Nếu nguồn chỉ đi qua một lần và không thể phát lại, ta có thể báo **ứng viên và bảo đảm sai số**, nhưng không được tùy ý khẳng định “đây chắc chắn là tất cả các heavy hitters với tần suất chính xác”.

Bài học xây dựng hai thuật toán, chứng minh chúng từ phép **loại bỏ các nhóm phần tử phân biệt**, giải thích giới hạn khi dữ liệu không thể phát lại, so sánh với bộ đếm chính xác bằng hash map, và cung cấp **chương trình Java 17+ độc lập** với kiểm thử exhaustive trên hàng nghìn luồng nhỏ cùng các kiểm thử ngẫu nhiên.

## 1. Mô hình luồng và cách đếm tần suất

Cho luồng hữu hạn gồm n bản ghi:

\[
a_1,a_2,\ldots,a_n.
\]

Mỗi bản ghi có một **nhãn khóa** (*key*). Trong ví dụ ta dùng số nguyên, nhưng thuật toán áp dụng cho chuỗi, ID và đối tượng có phép so sánh bằng nhau ổn định.

Tần suất **thật** của một khóa x là:

\[
\boxed{f(x)=|\{i\in\{1,\ldots,n\}:a_i=x\}|.}
\]

Phân biệt:

- **Chiều dài luồng n:** tổng số bản ghi, **kể cả bản ghi lặp**.
- **Số khóa phân biệt d:** số giá trị x khác nhau.
- **Tần suất f(x):** số bản ghi có khóa x.
- **Ngưỡng tần suất:** chẳng hạn n/2 hoặc n/k, thường dùng dấu **lớn hơn nghiêm ngặt**.
- **Ứng viên:** một khóa do thuật toán tóm tắt chỉ ra, có thể cần xác minh.
- **Kết quả đã xác minh:** khóa thực sự thỏa điều kiện bằng phép đếm chính xác.

Ví dụ:

~~~text
stream = [A, B, A, C, A, B, A]
n = 7

f(A) = 4
f(B) = 2
f(C) = 1
~~~

A là phần tử chiếm đa số vì \(4>7/2=3.5\). Nếu xét ngưỡng \(n/3\), A cũng là phần tử thường xuyên vì \(4>7/3\); B không thỏa vì \(2\not>7/3\).

### Không đánh đồng nhãn với vị trí

Một bản ghi có thể xuất hiện nhiều lần với cùng khóa. Ví dụ:

~~~text
(index=0, key=A), (index=1, key=A)
~~~

được tính là **hai lần xuất hiện** của khóa A. Không được dùng `Set` của các khóa để tính n, vì làm mất thông tin lặp.

### Kết quả cần trả có thể khác nhau

Bài toán có thể yêu cầu:

- Chỉ xác định **có tồn tại đa số hay không**.
- Trả **khóa** chiếm đa số.
- Trả tất cả khóa có \(f(x)>n/k\).
- Trả khóa **cùng tần suất chính xác**.
- Trả **xấp xỉ tần suất** khi không thể đọc lại luồng.

Các yêu cầu này cần chiến lược bộ nhớ, số lượt đọc và điều kiện kiểm chứng khác nhau.

## 2. Đếm chính xác bằng Map: cách đối chiếu đơn giản

Nếu đủ bộ nhớ, có thể lưu tần suất của **mọi khóa phân biệt**:

~~~text
frequency = empty hash map

for each key x in stream:
    frequency[x]++

return keys where frequency[x] > n/k
~~~

Với `HashMap` có thao tác tra cứu/trong bảng băm kỳ vọng O(1):

- Thời gian kỳ vọng: O(n).
- Bộ nhớ: O(d), với d là số khóa phân biệt.
- Có thể trả kết quả **chính xác chỉ sau một lượt đọc**.

Vậy vì sao cần Boyer–Moore và Misra–Gries?

Khi luồng có hàng triệu hoặc hàng tỷ khóa phân biệt, O(d) bộ nhớ có thể quá lớn. **Thuật toán tóm tắt luồng** đổi một ít thông tin về tần suất lấy **bộ nhớ độc lập với d**:

- Boyer–Moore dùng **O(1)**.
- Misra–Gries dùng **O(k)**.

Đổi lại, trạng thái thu gọn thường **không chứa đủ tần suất thật** để kết luận chính xác trong mọi trường hợp mà không đọc lại dữ liệu.

## 3. Định nghĩa phần tử chiếm đa số

Một khóa M là **đa số nghiêm ngặt** nếu:

\[
\boxed{f(M)>n/2.}
\]

Tương đương với số đếm nguyên:

\[
\boxed{f(M)>\lfloor n/2\rfloor.}
\]

Vì tổng tần suất của tất cả khóa bằng n, **không thể có hai khóa cùng có tần suất lớn hơn n/2**. Nếu có hai khóa M và N khác nhau đều quá n/2, tổng tần suất của chúng sẽ lớn hơn n, mâu thuẫn.

Do đó câu trả lời có tối đa **một** phần tử.

### Các ví dụ cần phân biệt

~~~text
[2, 2, 1, 1, 1, 2, 2]
n=7, f(2)=4, f(1)=3
2 chiếm đa số (4 > 3.5)

[1, 2, 3, 1, 2, 3]
n=6, mỗi khóa xuất hiện 2 lần
không có đa số (2 không > 3)

[1, 1, 2, 2]
n=4, f(1)=f(2)=2
không có đa số vì 2 không > 2

[]
n=0
không có đa số
~~~

Đặc biệt, **bằng n/2 là không đủ**. Nếu đề bài yêu cầu **ít nhất n/2** thay vì **nhiều hơn n/2**, đó là một điều kiện khác và có thể xuất hiện hai nhãn cùng đạt ngưỡng.

## 4. Boyer–Moore: chỉ một ứng viên và một số đếm

Ý tưởng cốt lõi của thuật toán Boyer–Moore là **loại bỏ từng cặp bản ghi có khóa khác nhau**. Nếu một khóa M thực sự có tần suất lớn hơn một nửa, việc xóa một cặp khác khóa không thể loại hết M trước những khóa còn lại.

Thuật toán duy trì:

- `candidate`: khóa ứng viên hiện tại hoặc “chưa có”.
- `balance`: số đếm dư **không âm**.
- `seen`: tổng bản ghi đã đọc, để kiểm tra thống kê hoặc ngưỡng sau này.

Quy tắc khi nhận phần tử x:

~~~text
if balance == 0:
    candidate = x
    balance = 1
else if x == candidate:
    balance += 1
else:
    balance -= 1
    if balance == 0:
        candidate = none
~~~

Sau khi đọc hết, `candidate` là **ứng viên** nếu `balance>0`, không phải chứng chỉ rằng \(f(candidate)>n/2\).

### Bảng chạy tay

Luồng:

~~~text
[2, 2, 1, 1, 1, 2, 2]
~~~

| Bước | Giá trị x | Ứng viên sau bước | Balance | Diễn giải |
|---:|---:|---:|---:|---|
| 1 | 2 | 2 | 1 | Chưa có ứng viên, nhận 2 |
| 2 | 2 | 2 | 2 | Trùng ứng viên, tăng |
| 3 | 1 | 2 | 1 | Khác ứng viên, hủy một cặp |
| 4 | 1 | rỗng | 0 | Hủy nốt một cặp |
| 5 | 1 | 1 | 1 | Bắt đầu ứng viên mới |
| 6 | 2 | rỗng | 0 | Hủy một cặp |
| 7 | 2 | 2 | 1 | Nhận 2 làm ứng viên cuối |

Kết thúc có `candidate=2`, `balance=1`.

Đếm thật trong **lượt hai**:

\[
f(2)=4>7/2.
\]

Vậy trả kết quả đã kiểm **2**.

### Balance không phải tần suất thật

Trong ví dụ trên, balance cuối là **1** nhưng f(2)=**4**. Balance chỉ đếm phần dư sau phép hủy các cặp khác khóa, không phải số lần 2 xuất hiện trong luồng.

Nếu in “ứng viên 2 xuất hiện 1 lần” bằng balance, thông tin tần suất là **sai**.

## 5. Chứng minh Boyer–Moore không bỏ sót đa số thật

Giả sử M là khóa có:

\[
f(M)>n/2.
\]

Mỗi lần balance giảm do gặp khóa khác ứng viên, ta có thể xem như **xóa một cặp hai bản ghi khác khóa** khỏi một mô hình trừu tượng của luồng.

Khi loại một cặp có hai khóa khác nhau:

- Nếu cặp chứa M, chỉ mất **một** lần xuất hiện của M và **một** bản ghi không phải M.
- Nếu cặp không chứa M, số bản ghi không phải M giảm hai, M không giảm.

Ban đầu:

\[
f(M)>n-f(M).
\]

Số M lớn hơn tổng số tất cả bản ghi không phải M. Qua mỗi phép hủy cặp khác khóa, chênh lệch có lợi cho M **không giảm** theo nghĩa khiến M bị ít hơn hoặc bằng tất cả khóa khác cộng lại.

Vì vậy sau mọi cặp bị hủy, nếu còn phần tử thì khóa M **vẫn phải xuất hiện** trong phần dư. Thuật toán chỉ giữ một loại khóa ở phần dư đại diện bởi candidate và balance, nên nếu M thực sự chiếm đa số, ứng viên cuối phải là **M**.

**Hệ quả quan trọng:**

\[
\boxed{\text{Có đa số thật}\ \Longrightarrow\
\text{Boyer–Moore sẽ trả đúng khóa đó làm ứng viên}.}
\]

Chiều ngược lại **không đúng**: Boyer–Moore có thể để lại ứng viên dù không ai chiếm đa số.

### Phản ví dụ ứng viên giả

~~~text
stream = [1, 2, 3]
~~~

Diễn biến:

- 1 → candidate=1, balance=1.
- 2 → balance=0, hủy cặp.
- 3 → candidate=3, balance=1.

Ứng viên cuối là 3, nhưng:

\[
f(3)=1,\qquad n/2=1.5.
\]

Do đó **3 không phải đa số**. Một lần đếm xác minh là bắt buộc nếu đề không bảo đảm luôn có phần tử đa số.

## 6. Boyer–Moore và lượt thứ hai

Để giải chính xác bài toán “có ai chiếm đa số không?” khi **không có giả thiết tồn tại**, dùng hai pha:

**Pha 1 — tìm ứng viên.**

~~~text
candidate = boyerMoore(firstPass)
~~~

**Pha 2 — đếm ứng viên thật.**

~~~text
occurrences = 0
for each x in stream:
    if x == candidate:
        occurrences++

if occurrences > floor(n/2):
    return candidate
else:
    return none
~~~

Nếu pha 1 không có ứng viên, chắc chắn không thể tồn tại đa số thật theo chứng minh trên; không cần lượt hai.

### Độ phức tạp

- Mỗi lượt đọc O(n).
- Tổng hai lượt O(n).
- Bộ nhớ phụ O(1), không tính bộ dữ liệu nguồn.

Khi input là **mảng đã có sẵn**, việc duyệt hai lượt rất đơn giản.

Khi input là **luồng mạng một chiều, không thể phát lại**, cần lưu hoặc truy vấn lại dữ liệu ở nơi khác nếu muốn xác minh tần suất chính xác. Không được nói “hai lượt O(1) bộ nhớ” rồi bỏ qua giả định **luồng có thể phát lại**.

### Trường hợp đề bảo đảm có đa số

Một số bài lập trình **cho trước đảm bảo** tồn tại một khóa với f>n/2. Trong trường hợp đó, có thể trả ứng viên ngay sau pha 1, vì chiều “đa số thật ⇒ ứng viên đúng” đã được chứng minh.

Nếu đề không có đảm bảo, **đừng tự giả định** nó.

## 7. Từ đa số tới phần tử thường xuyên n/k

Để tìm nhiều phần tử xuất hiện thường xuyên, chọn **tham số nguyên k≥2** và quan tâm tập:

\[
\boxed{H_k=\{x:f(x)>n/k\}.}
\]

Một số tính chất:

- Với k=2, \(H_2\) là tập chứa tối đa một **đa số nghiêm ngặt**.
- Với k=3, mỗi khóa phải xuất hiện nhiều hơn **một phần ba** luồng.
- Với k=4, mỗi khóa phải xuất hiện nhiều hơn **một phần tư** luồng.
- Nếu k>n, ngưỡng n/k nhỏ hơn 1, nên **mọi khóa đã xuất hiện ít nhất một lần** đều thỏa điều kiện.

### Tại sao có tối đa k−1 khóa nặng?

Nếu có k khóa phân biệt cùng thỏa:

\[
f(x)>n/k,
\]

thì tổng số lần xuất hiện của k khóa ấy lớn hơn:

\[
k\cdot(n/k)=n,
\]

mâu thuẫn với luồng chỉ có n bản ghi.

Vì vậy:

\[
\boxed{|H_k|\le k-1.}
\]

Đây là lý do tự nhiên để cố gắng giải bài toán bằng **k−1 bộ đếm ứng viên**, thay vì phải giữ mọi khóa phân biệt.

### Ngưỡng nghiêm ngặt

Với số đếm nguyên:

\[
\boxed{f(x)>n/k\iff f(x)>\lfloor n/k\rfloor.}
\]

Ví dụ n=9,k=3:

- f=3: **không** thỏa, vì 3 không lớn hơn 9/3.
- f=4: **có** thỏa.

Phải xác định dấu `>`, không được tự biến thành `>=`.

## 8. Misra–Gries: tối đa k−1 ứng viên

**Misra–Gries** là thuật toán theo luồng xác định, duy trì bảng tối đa **k−1 khóa**, mỗi khóa gắn với một bộ đếm dương.

Với mỗi bản ghi x:

1. **x đã có trong bảng:** tăng bộ đếm của x.
2. **x chưa có và còn ô trống:** thêm x với bộ đếm 1.
3. **x chưa có và bảng đã đủ k−1 khóa:** giảm **tất cả k−1 bộ đếm đi 1**; x vừa đến **không được thêm**, xóa mọi bộ đếm giảm về 0.

Mã giả:

~~~text
MisraGries(stream, k):
    require k >= 2
    counters = empty map with at most k-1 keys

    for each x in stream:
        if counters contains x:
            counters[x]++
        else if counters.size < k-1:
            counters[x] = 1
        else:
            for each key y in counters:
                counters[y]--
                if counters[y] == 0:
                    remove y

    return counters.keys
~~~

**Đầu ra là một tập ứng viên**, không phải tập heavy hitters đã kiểm. Các giá trị bộ đếm có thể **nhỏ hơn tần suất thật** vì đã bị giảm trong những lượt hủy nhóm.

### Ba thao tác có ý nghĩa khác nhau

- **Tăng:** ghi nhận một bản ghi của khóa đang theo dõi.
- **Chèn:** bắt đầu theo dõi một khóa mới vì còn chỗ.
- **Giảm đồng loạt:** nếu không thể theo dõi khóa mới mà vẫn giữ ≤k−1 khóa, hủy một nhóm gồm **k khóa phân biệt**: khóa x vừa đến và một bản ghi đại diện của từng khóa đang có.

Đặc biệt, ở nhánh giảm đồng loạt, **không thêm x với đếm 1**. Nếu vừa giảm đồng loạt vừa thêm x mà không có một thiết kế khác được chứng minh, phép hủy nhóm k khóa và giới hạn bộ nhớ sẽ không còn đúng như mô hình này.

## 9. Chạy tay Misra–Gries với k=3

Khi k=3, bảng giữ **tối đa 2 khóa**. Xét luồng:

~~~text
[A, B, A, C, A, B, D]
~~~

Các bước:

| Bước | x | Bảng sau bước | Giải thích |
|---:|---|---|---|
| 1 | A | {A:1} | Chèn A |
| 2 | B | {A:1,B:1} | Chèn B |
| 3 | A | {A:2,B:1} | Tăng A |
| 4 | C | {A:1} | Bảng đầy, C mới: giảm A và B, xóa B |
| 5 | A | {A:2} | Tăng A |
| 6 | B | {A:2,B:1} | Còn chỗ, chèn B |
| 7 | D | {A:1} | Bảng đầy, D mới: giảm cả hai, xóa B |

Tần suất thật:

\[
f(A)=3,\quad f(B)=2,\quad f(C)=1,\quad f(D)=1,\quad n=7.
\]

Ngưỡng n/3≈2.333. **Chỉ A** là heavy hitter, và A vẫn xuất hiện trong bảng ứng viên cuối.

Bộ đếm cuối của A là 1, dù tần suất thật là 3: các lần hủy nhóm đã làm bộ đếm giảm.

**Không dùng `counters[A]=1` làm kết quả f(A)=1.** Muốn tần suất thật, cần xác minh bằng lượt quét thứ hai.

## 10. Ví dụ k=4 có hai heavy hitters

Xét luồng 20 phần tử:

~~~text
1,1,1,1,1,1,1,
2,2,2,2,2,2,
3,3,3,3,
4,5,6
~~~

Tần suất:

\[
f(1)=7,\quad f(2)=6,\quad f(3)=4,\quad f(4)=f(5)=f(6)=1.
\]

Với k=4, ngưỡng:

\[
n/k=20/4=5.
\]

Do đó tập đáp án chính xác là:

\[
\boxed{H_4=\{1,2\}}.
\]

Sau một lượt Misra–Gries giữ tối đa 3 khóa, ví dụ này cho bảng cuối (sắp tăng để dễ đọc):

~~~text
{1=4, 2=3, 3=1}
~~~

Các số đếm **4,3,1** là các số đếm **còn lại sau hủy nhóm**. Trong quá trình có **3 lần hủy nhóm bốn khóa phân biệt**.

Kiểm:

\[
20=(4+3+1)+4\cdot3=8+12.
\]

Lượt thứ hai chỉ cần đếm lại các ứng viên {1,2,3}:

~~~text
1 -> 7  (>5, giữ)
2 -> 6  (>5, giữ)
3 -> 4  (không >5, loại)
~~~

Kết quả đúng:

~~~text
{1=7, 2=6}
~~~

### Vì sao ví dụ này quan trọng?

Nó cho thấy đồng thời:

- Tất cả heavy hitters thật 1 và 2 đều nằm trong **ứng viên**.
- Ứng viên 3 có thể xuất hiện dù **không đạt ngưỡng**.
- Bộ đếm MG không bằng tần suất thật.
- Cần **xác minh** để bỏ ứng viên giả và thu tần suất chính xác.

## 11. Bất biến “hủy nhóm k khóa phân biệt”

Đây là bất biến giúp chứng minh Misra–Gries.

Ở mỗi lần gặp khóa x chưa có và bảng đã đủ k−1 khóa, ta có:

- k−1 khóa trong bảng là **phân biệt**.
- x cũng khác tất cả khóa trong bảng (vì x chưa có).
- Do đó có thể coi hành động giảm k−1 bộ đếm và bỏ qua x là **loại đi đúng k bản ghi có các khóa đôi một phân biệt**.

Gọi D là số lần xảy ra hành động giảm đồng loạt.

Nếu sau khi xử lý n bản ghi, tổng các bộ đếm còn lại là:

\[
R=\sum_{\text{khóa trong bảng}}counter(x),
\]

thì bất biến bảo toàn số lượng bản ghi là:

\[
\boxed{n=R+kD.}
\]

Lý do:

- Với nhánh tăng/chèn: n tăng 1, R tăng 1, D giữ nguyên.
- Với nhánh giảm: n tăng 1 (nhận bản ghi mới), R giảm k−1, D tăng 1; vế phải đổi \(-(k-1)+k=+1\).
- Ban đầu n=R=D=0.

Suy ra:

\[
\boxed{D\le\lfloor n/k\rfloor.}
\]

Đây là số lượng **lượt loại bỏ nhóm**, không phải số lượng khóa bị xóa khỏi bảng; một lần giảm có thể xóa từ 0 đến k−1 khóa tùy giá trị đếm của chúng.

## 12. Chứng minh không bỏ sót phần tử có f(x)>n/k

Xét một khóa x có tần suất thật f(x).

Trong mỗi lần hủy nhóm k khóa phân biệt, **tối đa một** bản ghi có khóa x có thể bị loại, vì mọi khóa trong nhóm là khác nhau.

Nếu toàn bộ thuật toán hủy D nhóm, tổng số bản ghi x bị hủy nhiều nhất là D.

Như vậy số bản ghi x còn lại trong “phần dư” sau các phép hủy ít nhất:

\[
f(x)-D.
\]

Nếu x không có trong bảng cuối, tất cả bản ghi x đã được hủy, nên:

\[
f(x)\le D\le\lfloor n/k\rfloor.
\]

Lấy phản chứng: nếu \(f(x)>n/k\), thì f(x)>D, không thể có chuyện x vắng mặt trong bảng cuối.

Suy ra:

\[
\boxed{f(x)>n/k\Longrightarrow x\in\text{candidates}.}
\]

Đây là **bảo đảm không bỏ sót** (*no false negatives*) đối với ngưỡng **nghiêm ngặt**. Nó **không bảo đảm không có ứng viên giả** (*no false positives*).

### Hệ quả về số phần tử phải kiểm lại

Vì bảng chứa tối đa k−1 khóa:

- Chỉ cần kiểm tần suất thật của **tối đa k−1 ứng viên**.
- Nếu có thể đọc lại luồng, một lượt hai đếm riêng các khóa ấy.
- Sau lượt hai, lọc chính xác theo \(f(x)>n/k\).

Nhờ vậy bộ nhớ vẫn **O(k)**, ngay cả khi số khóa phân biệt d của luồng rất lớn.

## 13. Sai số của bộ đếm Misra–Gries

Đặt:

\[
\hat f(x)=
\begin{cases}
counter(x),&\text{nếu x còn trong bảng},\\
0,&\text{nếu không còn}.
\end{cases}
\]

Giá trị \(\hat f(x)\) là một **cận dưới** cho tần suất thật, vì các phép giảm chỉ xóa bớt bản ghi trong mô hình hủy nhóm; chúng không tự tạo thêm lần xuất hiện của x.

Mỗi nhóm bị hủy chứa tối đa một bản ghi x, nên:

\[
\boxed{\hat f(x)\le f(x)\le\hat f(x)+D.}
\]

Và vì \(D\le\lfloor n/k\rfloor\):

\[
\boxed{0\le f(x)-\hat f(x)\le D\le\lfloor n/k\rfloor.}
\]

Đây là một bảo đảm **tất định** (*deterministic error guarantee*) của Misra–Gries.

### Cách đọc chính xác

Nếu MG trả:

~~~text
x -> 4
D = 3
~~~

thì:

\[
4\le f(x)\le7.
\]

Không thể tự kết luận f(x)=4 hay f(x)=7; chỉ biết tần suất thuộc khoảng được bảo đảm.

Nếu x **không nằm trong bảng**, \(\hat f(x)=0\), nên:

\[
f(x)\le D\le n/k.
\]

Do đó x chắc chắn **không phải** heavy hitter của ngưỡng >n/k.

### Hai hướng suy luận an toàn

- Nếu \(\hat f(x)>n/k\), thì \(f(x)\ge\hat f(x)>n/k\): **có thể chứng nhận ngay** x là heavy hitter dù chưa đọc lại.
- Nếu x không là ứng viên, chắc chắn **không đạt ngưỡng**.
- Nếu x là ứng viên nhưng \(\hat f(x)\le n/k\), chỉ riêng bộ đếm không đủ kết luận; cần đếm lại hoặc chấp nhận nhãn “ứng viên chưa xác minh”.

Đây là cách sử dụng Misra–Gries có trách nhiệm trong luồng chỉ đọc một lượt.

## 14. Trường hợp bằng đúng n/k

Định nghĩa bài là:

\[
f(x)>n/k,
\]

không phải \(f(x)\ge n/k\).

Ví dụ:

~~~text
stream = [1,1,1,2,2,2,3,4,5]
n = 9
k = 3
~~~

Ta có f(1)=f(2)=3, bằng đúng n/k=3, nên **không** có khóa nào thỏa \(f(x)>3\).

Trong ví dụ này MG có thể hủy đủ các nhóm và trả bảng rỗng; ngay cả nếu một lần triển khai với thứ tự khác để lại ứng viên, lượt xác minh cuối vẫn phải **loại cả các khóa có f=3**.

### Vì sao chứng minh dùng dấu >?

Từ bất biến, x có thể mất **D≤n/k** bản ghi. Nếu f(x) chỉ **bằng** n/k, trong trường hợp xấu toàn bộ số lần xuất hiện có thể bị hủy; không có bảo đảm x còn làm ứng viên.

Do đó thay `>` bằng `>=` mà vẫn giữ k−1 bộ đếm có thể làm **hỏng tính đầy đủ** đối với những khóa nằm đúng tại ngưỡng.

Nếu yêu cầu là “ít nhất t lần”, hãy phân tích lại từ **ngưỡng t nguyên** và số lượng ứng viên/bộ đếm cần thiết, không mượn nguyên một phát biểu cho dấu >.

## 15. Với k=2, Misra–Gries liên hệ Boyer–Moore thế nào?

Nếu đặt k=2, Misra–Gries duy trì tối đa **một bộ đếm**.

- Khi gặp cùng khóa đang theo dõi: tăng.
- Khi chưa có khóa: chèn với đếm 1.
- Khi gặp khóa khác mà bảng đang đầy: giảm bộ đếm đang có đi 1; bỏ qua khóa mới.

Đó chính là cơ chế ứng viên và balance của **Boyer–Moore**.

Với các quy ước giống nhau về việc xóa ứng viên khi đếm về 0:

\[
\boxed{\text{Misra–Gries với }k=2
\text{ là cùng nguyên lý hủy cặp của Boyer–Moore}.}
\]

Tuy nhiên cả hai vẫn chỉ tạo **ứng viên**. Một bảng một khóa cuối luồng không tự chứng minh phần tử ấy có hơn n/2 số lần xuất hiện.

## 16. Tính trực tuyến: cập nhật, bộ nhớ và thời gian

### Boyer–Moore

Mỗi bản ghi cập nhật một ứng viên và một biến balance:

\[
\boxed{O(1)\text{ thời gian mỗi bản ghi},\quad O(1)\text{ bộ nhớ phụ}.}
\]

Toàn luồng n bản ghi:

\[
\boxed{O(n)\text{ thời gian}.}
\]

### Misra–Gries cơ bản

Với bảng tối đa k−1 khóa:

- Trùng khóa: một thao tác tra cứu và tăng đếm.
- Còn chỗ: thêm khóa.
- Đầy và gặp khóa mới: phải đi qua toàn bộ tối đa k−1 bộ đếm để giảm.

Nếu dùng `HashMap` hoặc `LinkedHashMap` với thao tác tra cứu kỳ vọng O(1), và triển khai **giảm đồng loạt bằng cách duyệt tất cả khóa**, cận thời gian an toàn là:

\[
\boxed{O(nk)\text{ trong trường hợp xấu}.}
\]

Bộ nhớ:

\[
\boxed{O(k).}
\]

Có các cấu trúc dữ liệu và cách cài đặt tối ưu hóa việc giảm đồng loạt, nhưng **không được gọi bản Java duyệt tất cả bộ đếm là O(n) cho mọi k tùy ý**. Nếu k là một hằng số nhỏ cố định, O(nk)=O(n).

### Xác minh các ứng viên

Sau pha tóm tắt, có tối đa k−1 khóa cần kiểm.

- Duyệt lại luồng, dùng HashMap đếm **chỉ những ứng viên**: O(n) kỳ vọng.
- Sắp kết quả tăng theo khóa để in ổn định: thêm O(k log k).
- Bộ nhớ đếm xác minh: O(k).

Tổng thời gian bản đơn giản:

\[
\boxed{O(nk+n+k\log k)}
\]

theo mô hình thao tác bảng băm kỳ vọng O(1); với k cố định, đây là O(n).

## 17. Phương án một lượt và hai lượt trong hệ thống thật

### Một lượt, chỉ cần danh sách ứng viên

Misra–Gries đủ để tạo một **tập ứng viên không bỏ sót heavy hitters**, kèm bộ đếm cận dưới và số lượt hủy D.

Nếu mục tiêu là **giám sát sơ bộ**, ta có thể:

- Hiển thị tối đa k−1 nhãn đáng theo dõi.
- Gửi cảnh báo có tính chất “ứng viên có khả năng nặng”.
- Báo khoảng đếm \([\hat f(x),\hat f(x)+D]\) thay vì tần suất giả chính xác.
- Xác nhận trực tiếp những ứng viên có \(\hat f(x)>n/k\) như một kết luận an toàn.

Nhưng không được ghi tất cả ứng viên là **heavy hitters đã chứng nhận**.

### Hai lượt, cần kết quả exact

Nếu dữ liệu là mảng, tệp có thể đọc lại hoặc luồng có cơ chế replay:

1. Lượt đầu chạy MG để tạo tối đa k−1 ứng viên.
2. Lượt hai đếm **tần suất thật** của những ứng viên ấy.
3. Tính n trong lượt đầu hoặc lượt hai nhất quán.
4. Chỉ giữ những khóa có \(f(x)>\lfloor n/k\rfloor\).

Kết quả lúc này chính xác hoàn toàn.

### Nếu luồng không thể phát lại

Với một luồng một chiều và miền khóa rất lớn, không thể mặc nhiên vừa dùng O(k) nhớ vừa biết **chính xác** tần suất của các khóa chỉ được đưa vào bảng ứng viên ở gần cuối luồng. Một khóa có thể đã xuất hiện nhiều lần trước khi được theo dõi, và các lần hủy nhóm làm mất thông tin đếm chính xác.

Các lựa chọn thực tế gồm:

- Cho phép **replay** hoặc lưu dữ liệu vào log.
- Dùng một hệ thống đếm toàn bộ khóa, tốn O(d) nhớ/bộ nhớ ngoài.
- Chấp nhận **ước lượng/tóm tắt** có bảo đảm sai số.
- Dùng mô hình/ngữ nghĩa bài toán khác với cấu trúc dữ liệu chuyên dụng.

Không được coi `n` hoặc bộ đếm ứng viên là phép màu khôi phục tần suất thật của các sự kiện đã bị quên.

## 18. Vì sao Misra–Gries không phải top-k?

Tên “heavy hitter” đôi khi gây nhầm với bài **lấy k khóa có tần suất cao nhất** (*top-k frequent items*).

Hai mục tiêu khác nhau:

- **Heavy hitters theo ngưỡng:** mọi khóa có \(f(x)>n/k\).
- **Top-k:** k khóa có tần suất cao nhất, kể cả khi **không khóa nào** đạt n/k; còn phải định nghĩa tie-break khi nhiều khóa cùng tần suất.

Một bảng MG chứa **k−1 ứng viên** chỉ bảo đảm bao phủ những khóa có tần suất >n/k. Nó **không bảo đảm** rằng các khóa ấy là đúng “top k−1” theo mọi cách diễn giải.

Ví dụ nếu n=1000 và có 200 khóa mỗi khóa xuất hiện 5 lần, với k=10:

\[
n/k=100.
\]

Không khóa nào đạt >100, nên tập heavy hitters rỗng. Nhưng bài top-10 vẫn phải chọn ra mười khóa theo quy tắc xử lý hòa; Misra–Gries không cung cấp kết quả ấy.

Nếu đề yêu cầu đúng **k phần tử nhiều nhất**, không được thay bằng việc lấy k−1 ứng viên của MG mà không có chứng minh bổ sung.

## 19. So sánh với các thuật toán liên quan

| Thuật toán | Mục tiêu | Bộ nhớ phụ | Cần lượt hai để trả đúng? | Bản chất |
|---|---|---|---|---|
| HashMap đếm mọi khóa | Tần suất chính xác mọi khóa | O(d) | Không | Exact |
| Boyer–Moore | Ứng viên đa số >n/2 | O(1) | Có nếu không bảo đảm tồn tại | Tất định, hủy cặp |
| Misra–Gries | Ứng viên chứa mọi khóa >n/k | O(k) | Có nếu muốn lọc/tần suất exact | Tất định, hủy k khóa |
| Space-Saving | Theo dõi khóa nặng với bộ đếm xấp xỉ | O(k) | Tùy yêu cầu | Thường dùng thay khóa có đếm nhỏ nhất |
| Count–Min Sketch | Ước lượng tần suất qua các mảng băm | Theo tham số sai số/độ tin cậy | Không để lấy ước lượng; exact cần dữ liệu khác | Ngẫu nhiên, sai số một phía tùy thiết kế |
| Top-k exact bằng map + heap | k khóa có tần suất cao nhất | O(d+k) | Không nếu lưu mọi khóa | Exact, khác yêu cầu >n/k |

### Space-Saving không giống Misra–Gries

Trong **Space-Saving** đơn giản, nếu bảng đầy và gặp khóa mới, thuật toán có thể **thay** khóa có bộ đếm nhỏ nhất bằng khóa mới và tăng bộ đếm theo quy tắc riêng. Trong **Misra–Gries**, nếu bảng đầy, khóa mới bị bỏ và mọi bộ đếm hiện có **cùng giảm một đơn vị**.

Không được lấy bất biến \(n=R+kD\) của Misra–Gries rồi gắn cho Space-Saving nếu không chứng minh lại quy tắc cập nhật.

### Count–Min Sketch không tự liệt kê mọi heavy hitters

Count–Min Sketch chủ yếu hỗ trợ truy vấn **một khóa đã biết** để ước lượng tần suất. Nếu miền khóa rất lớn, chỉ có cấu trúc sketch mà không duy trì tập ứng viên, ta **không tự suy ra được danh sách đầy đủ các khóa cần hỏi**.

Có thể kết hợp sketch với cách tạo ứng viên, nhưng đó là một thiết kế khác, không phải tính năng tự động của sketch.

## 20. Java 17+: Boyer–Moore và Misra–Gries cùng oracle kiểm chứng

Chương trình hoàn chỉnh **StreamMajorityAndHeavyHittersDemo.java** dưới đây sử dụng khóa kiểu `int` và có thể chạy trực tiếp.

Các thành phần:

1. `MajorityVote.accept(int)` xử lý từng bản ghi, cập nhật ứng viên/balance.
2. `exactMajority(int[])` chạy Boyer–Moore rồi đếm lại ứng viên để trả `OptionalInt`.
3. `MisraGries.accept(int)` giữ tối đa k−1 khóa, giảm đồng loạt khi đầy, ghi số nhóm bị hủy D.
4. `exactFrequent(int[],k)` chạy MG rồi quét lại dữ liệu để trả **tần suất thật** của đúng các khóa có \(f>n/k\).
5. `checkOne` dùng **HashMap oracle** trên toàn bộ mảng test nhỏ, kiểm candidate coverage, kết quả lọc exact, bất biến \(n=R+kD\) và cận \(0\le f-\hat f\le D\).
6. `exhaustiveTinyStreams` liệt kê mọi dãy độ dài 0..6 trên bảng chữ cái bốn khóa, với k=2..5.
7. `randomStreams` chạy 1.600 trường hợp giả ngẫu nhiên có seed cố định, gồm khóa âm và luồng rỗng.
8. In các ví dụ cho thấy **ứng viên giả**, **ngưỡng nghiêm ngặt**, và **sự khác nhau giữa bộ đếm dư và tần suất thật**.

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.Random;
import java.util.SortedMap;
import java.util.TreeMap;

public class StreamMajorityAndHeavyHittersDemo {

    // One candidate + one balance. Strict majority must survive.
    static final class MajorityVote {
        private Integer candidate = null;
        private long balance = 0L;
        private long seen = 0L;

        void accept(int value) {
            seen = Math.addExact(seen, 1L);

            if (balance == 0L) {
                candidate = value;
                balance = 1L;
            } else if (candidate.intValue() == value) {
                balance++;
            } else {
                balance--;
                if (balance == 0L) {
                    candidate = null;
                }
            }
        }

        OptionalInt candidate() {
            return candidate == null
                ? OptionalInt.empty()
                : OptionalInt.of(candidate);
        }

        long balance() {
            return balance;
        }

        long seen() {
            return seen;
        }
    }

    // First pass finds a candidate; second pass checks exact count.
    static OptionalInt exactMajority(int[] data) {
        Objects.requireNonNull(data, "data");

        MajorityVote vote = new MajorityVote();
        for (int value : data) {
            vote.accept(value);
        }

        OptionalInt candidate = vote.candidate();
        if (candidate.isEmpty()) {
            return OptionalInt.empty();
        }

        int key = candidate.getAsInt();
        long occurrences = 0L;
        for (int value : data) {
            if (value == key) {
                occurrences++;
            }
        }

        return occurrences > (long) data.length / 2
            ? OptionalInt.of(key)
            : OptionalInt.empty();
    }

    // k-1 counters for frequencies strictly greater than n/k.
    static final class MisraGries {
        private final int k;
        private final LinkedHashMap<Integer, Long> counters =
            new LinkedHashMap<>();
        private long seen = 0L;
        private long cancelledGroups = 0L;

        MisraGries(int k) {
            if (k < 2) {
                throw new IllegalArgumentException("k must be >= 2");
            }
            this.k = k;
        }

        void accept(int value) {
            seen = Math.addExact(seen, 1L);

            Long old = counters.get(value);
            if (old != null) {
                counters.put(value, old + 1L);
                return;
            }

            if (counters.size() < k - 1) {
                counters.put(value, 1L);
                return;
            }

            // There are k-1 distinct tracked keys, all != value.
            // Delete one occurrence of each plus incoming value.
            Iterator<Map.Entry<Integer, Long>> it =
                counters.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<Integer, Long> entry = it.next();
                long after = entry.getValue() - 1L;
                if (after == 0L) {
                    it.remove();
                } else {
                    entry.setValue(after);
                }
            }
            cancelledGroups = Math.addExact(cancelledGroups, 1L);
        }

        SortedMap<Integer, Long> snapshot() {
            return new TreeMap<>(counters);
        }

        long seen() {
            return seen;
        }

        long cancelledGroups() {
            return cancelledGroups;
        }

        int k() {
            return k;
        }
    }

    // Exact second pass only counts the at-most-(k-1) candidates.
    static SortedMap<Integer, Long> exactFrequent(
        int[] data, int k
    ) {
        Objects.requireNonNull(data, "data");
        MisraGries summary = new MisraGries(k);

        for (int value : data) {
            summary.accept(value);
        }

        Map<Integer, Long> counts = new HashMap<>();
        for (int key : summary.snapshot().keySet()) {
            counts.put(key, 0L);
        }

        for (int value : data) {
            Long old = counts.get(value);
            if (old != null) {
                counts.put(value, old + 1L);
            }
        }

        SortedMap<Integer, Long> result = new TreeMap<>();
        long floorThreshold = (long) data.length / k;
        for (Map.Entry<Integer, Long> entry : counts.entrySet()) {
            if (entry.getValue() > floorThreshold) {
                result.put(entry.getKey(), entry.getValue());
            }
        }
        return result;
    }

    // Oracle for tests: count EVERY distinct key, O(d) memory.
    static Map<Integer, Long> fullFrequency(int[] data) {
        Map<Integer, Long> frequency = new HashMap<>();
        for (int value : data) {
            frequency.merge(value, 1L, Long::sum);
        }
        return frequency;
    }

    static SortedMap<Integer, Long> oracleFrequent(
        int[] data, int k
    ) {
        SortedMap<Integer, Long> correct = new TreeMap<>();
        long floorThreshold = (long) data.length / k;

        for (Map.Entry<Integer, Long> entry :
                fullFrequency(data).entrySet()) {
            if (entry.getValue() > floorThreshold) {
                correct.put(entry.getKey(), entry.getValue());
            }
        }
        return correct;
    }

    static void require(boolean ok, String reason) {
        if (!ok) {
            throw new AssertionError(reason);
        }
    }

    // Checks algorithm result AND its mathematical invariants.
    static void checkOne(int[] data, int k) {
        MisraGries summary = new MisraGries(k);
        MajorityVote vote = new MajorityVote();

        for (int value : data) {
            summary.accept(value);
            vote.accept(value);
        }

        SortedMap<Integer, Long> tracked = summary.snapshot();
        Map<Integer, Long> actual = fullFrequency(data);

        require(summary.seen() == data.length,
            "wrong processed count");
        require(vote.seen() == data.length,
            "wrong majority processed count");
        require(tracked.size() <= k - 1,
            "too many Misra-Gries counters");

        long sumResidual = 0L;
        for (long count : tracked.values()) {
            require(count > 0L, "nonpositive counter");
            sumResidual += count;
        }

        require(
            sumResidual + (long) k * summary.cancelledGroups()
                == data.length,
            "n = residual + k * cancelledGroups failed"
        );

        // No false negatives above n/k and bounded error.
        for (Map.Entry<Integer, Long> entry : actual.entrySet()) {
            int key = entry.getKey();
            long trueCount = entry.getValue();
            long estimated = tracked.getOrDefault(key, 0L);

            require(0L <= estimated && estimated <= trueCount,
                "residual counter exceeds true frequency");
            require(trueCount - estimated
                    <= summary.cancelledGroups(),
                "Misra-Gries error bound violated");

            if (trueCount > (long) data.length / k) {
                require(tracked.containsKey(key),
                    "heavy hitter missing from candidate set");
            }
        }

        require(
            exactFrequent(data, k).equals(
                oracleFrequent(data, k)
            ),
            "verified heavy hitters differ from exact counts"
        );

        // Majority Vote candidate need not be a true majority.
        Long majorityCount = vote.candidate().isPresent()
            ? actual.getOrDefault(
                vote.candidate().getAsInt(), 0L
            )
            : 0L;

        OptionalInt expectedMajority = OptionalInt.empty();
        for (Map.Entry<Integer, Long> entry : actual.entrySet()) {
            if (entry.getValue() > (long) data.length / 2) {
                expectedMajority =
                    OptionalInt.of(entry.getKey());
                break;
            }
        }

        OptionalInt verifiedMajority = exactMajority(data);
        require(
            verifiedMajority.equals(expectedMajority),
            "Boyer-Moore majority verification failed"
        );
        if (expectedMajority.isPresent()) {
            require(vote.candidate().isPresent()
                    && vote.candidate().getAsInt()
                        == expectedMajority.getAsInt(),
                "majority not preserved as candidate");
        }
        if (vote.candidate().isPresent()) {
            require(majorityCount >= 1L,
                "candidate never appeared in input");
        }
    }

    static void exhaustiveTinyStreams() {
        long streams = 0L;
        long summaries = 0L;

        // Every sequence of length 0..6 over keys {0,1,2,3}.
        for (int n = 0; n <= 6; n++) {
            int possibilities = 1;
            for (int i = 0; i < n; i++) {
                possibilities *= 4;
            }

            for (int encoded = 0; encoded < possibilities;
                    encoded++) {
                int[] data = new int[n];
                int state = encoded;
                for (int i = 0; i < n; i++) {
                    data[i] = state % 4;
                    state /= 4;
                }

                for (int k = 2; k <= 5; k++) {
                    checkOne(data, k);
                    summaries++;
                }
                streams++;
            }
        }

        System.out.println(
            "Exhaustive small streams: PASS ("
            + streams + " streams, "
            + summaries + " k-parameter checks)"
        );
    }

    static void randomStreams() {
        Random random = new Random(489L);
        int cases = 1600;

        for (int test = 0; test < cases; test++) {
            int n = random.nextInt(80);
            int[] data = new int[n];

            for (int i = 0; i < n; i++) {
                data[i] = random.nextInt(12) - 6;
            }
            int k = 2 + random.nextInt(9);
            checkOne(data, k);
        }

        System.out.println(
            "Random stream invariants: PASS ("
            + cases + " cases)"
        );
    }

    public static void main(String[] args) {
        int[] majority = {2, 2, 1, 1, 1, 2, 2};
        MajorityVote vote = new MajorityVote();
        for (int value : majority) {
            vote.accept(value);
        }

        System.out.println(
            "Majority candidate: " + vote.candidate()
        );
        System.out.println(
            "Majority candidate balance: " + vote.balance()
        );
        System.out.println(
            "Verified majority: " + exactMajority(majority)
        );

        int[] noMajority = {1, 2, 3, 1, 2, 3};
        System.out.println(
            "No-majority stream: " + exactMajority(noMajority)
        );

        int[] heavy = {
            1, 1, 1, 1, 1, 1, 1,
            2, 2, 2, 2, 2, 2,
            3, 3, 3, 3,
            4, 5, 6
        };
        MisraGries top = new MisraGries(4);
        for (int value : heavy) {
            top.accept(value);
        }

        System.out.println(
            "k=4 stream length: " + heavy.length
        );
        System.out.println(
            "MG residual counters: " + top.snapshot()
        );
        System.out.println(
            "Cancelled groups: " + top.cancelledGroups()
        );
        System.out.println(
            "Verified >n/4: " + exactFrequent(heavy, 4)
        );

        int[] falsePositive = {
            9, 9, 9, 2, 3, 4, 5, 6, 7, 8, 9
        };
        MisraGries summary = new MisraGries(4);
        for (int value : falsePositive) {
            summary.accept(value);
        }
        System.out.println(
            "Candidates before verification: "
            + summary.snapshot()
        );
        System.out.println(
            "Candidates after verification: "
            + exactFrequent(falsePositive, 4)
        );

        int[] atThreshold = {
            1, 1, 1, 2, 2, 2, 3, 4, 5
        };
        System.out.println(
            "Exactly n/k does not qualify: "
            + exactFrequent(atThreshold, 3)
        );
        System.out.println(
            "Empty stream frequent keys: "
            + exactFrequent(new int[0], 3)
        );

        exhaustiveTinyStreams();
        randomStreams();
    }
}
~~~

Lưu tệp với tên **StreamMajorityAndHeavyHittersDemo.java**, dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 StreamMajorityAndHeavyHittersDemo.java
java StreamMajorityAndHeavyHittersDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
Majority candidate: OptionalInt[2]
Majority candidate balance: 1
Verified majority: OptionalInt[2]
No-majority stream: OptionalInt.empty
k=4 stream length: 20
MG residual counters: {1=4, 2=3, 3=1}
Cancelled groups: 3
Verified >n/4: {1=7, 2=6}
Candidates before verification: {8=1, 9=2}
Candidates after verification: {9=4}
Exactly n/k does not qualify: {}
Empty stream frequent keys: {}
Exhaustive small streams: PASS (5461 streams, 21844 k-parameter checks)
Random stream invariants: PASS (1600 cases)
~~~

### Ý nghĩa từng nhóm output

- **Majority:** khóa 2 xuất hiện 4 lần trên 7 bản ghi, vượt 1/2, dù balance cuối chỉ bằng 1.
- **No-majority:** dãy cân bằng nhiều khóa không có phần tử chiếm đa số. `OptionalInt.empty` biểu diễn “không có”, không dùng số đặc biệt như -1 vì **-1 có thể là khóa dữ liệu hợp lệ**.
- **Heavy k=4:** n=20, cần f>5. Khóa 1 có f=7, khóa 2 có f=6; khóa 3 chỉ có f=4 nên bị loại sau lượt xác minh.
- **Candidate false positive:** bảng trước xác minh chứa cả 8 (đếm dư 1) và 9 (đếm dư 2); tần suất thật của 8 là 1 trên 11, không vượt ngưỡng 11/4. Lượt hai chỉ giữ 9 (f=4).
- **Exactly threshold:** n=9, k=3, những khóa có f=3 **không** vượt ngưỡng 3 nên kết quả rỗng.
- **Empty stream:** không có khóa nào xuất hiện, dù ngưỡng toán học bằng 0.
- **Exhaustive:** mọi chuỗi độ dài 0..6 trên bảng chữ cái bốn giá trị được kiểm với k=2..5, tổng 5.461 luồng và 21.844 trường hợp tham số.
- **Random:** 1.600 luồng từ `Random(489L)`, chiều dài 0..79, khóa trong [-6,5], k từ 2 tới 10, kiểm độc lập bằng tần suất thật toàn bộ.

## 21. Kiểm thử đúng những bất biến nào?

Các bài toán luồng thường không có một **nghiệm số duy nhất** dễ quan sát, nên kiểm thử cần so cả **định nghĩa và bất biến**.

### Với Boyer–Moore

- Nếu một khóa có f>n/2, khóa ấy **phải trở thành ứng viên cuối**.
- Sau lượt xác minh, kết quả phải **trùng với kết quả đếm tần suất thật**.
- Nếu không ai chiếm đa số, hàm verified phải trả “không có” ngay cả khi `candidate` chưa rỗng.
- `balance` luôn không âm; nếu bằng 0 thì có thể xóa ứng viên hiện tại.

### Với Misra–Gries

- Bảng không bao giờ chứa quá k−1 khóa.
- Mọi bộ đếm được giữ đều **dương**.
- \(\boxed{n=\sum counter+kD}\).
- Với mỗi khóa x có mặt trong input:
  \[
  \boxed{0\le f(x)-\hat f(x)\le D}.
  \]
- Mọi x có f>n/k đều phải **có trong tập ứng viên**.
- Danh sách sau lượt xác minh phải đúng bằng tập mà `HashMap` đếm toàn bộ trả ra, cả khóa lẫn tần suất.

### Exhaustive khác random test

Với n≤6 và bảng chữ cái bốn khóa, số luồng có thể là:

\[
\sum_{n=0}^{6}4^n
=\frac{4^7-1}{4-1}
=\frac{16384-1}{3}
=\boxed{5461}.
\]

Thử mỗi luồng với k=2,3,4,5 tạo:

\[
5461\cdot4=\boxed{21844}
\]

trường hợp tham số Misra–Gries. Đây là **kiểm tra đầy đủ toàn bộ không gian nhỏ được xác định**, chứ không chỉ một số mẫu “trông có vẻ ngẫu nhiên”.

Kiểm ngẫu nhiên thêm độ dài luồng và nhiều âm/khóa khác nhau để bắt lỗi cài đặt mà không cần liệt kê tất cả các dãy lớn. Nhưng **bằng chứng đúng tổng quát** vẫn đến từ phép hủy cặp/hủy nhóm và các bất biến đã chứng minh.

### Vì sao không so bộ đếm MG bằng tần suất thật?

Nếu yêu cầu:

~~~text
counter[key] == fullFrequency[key]
~~~

cho mọi khóa ứng viên, nhiều trường hợp **đúng thuật toán sẽ thất bại kiểm thử**, vì MG cố ý giảm counter.

Điều cần so là:

~~~text
0 <= fullFrequency[key] - counter[key] <= cancelledGroups
~~~

và so **kết quả verified** với oracle exact sau khi dùng nguồn lần hai.

## 22. Các trường hợp biên và lỗi thường gặp

| Trường hợp | Boyer–Moore | Misra–Gries |
|---|---|---|
| n=0 | Không có ứng viên/đa số | Bảng rỗng |
| n=1 | Phần tử duy nhất là đa số | Với k≥2, phần tử duy nhất >1/k |
| Tất cả phần tử giống nhau | Ứng viên đúng, balance=n | Một bộ đếm n, D=0 |
| Mỗi phần tử khác nhau | Có thể còn ứng viên giả | Có thể còn ứng viên giả |
| Tần suất đúng n/2 | Không phải đa số | k=2 cũng không thỏa >n/2 |
| Tần suất đúng n/k | Không được suy ra tính nặng | Không bảo đảm nằm trong bảng |
| k=2 | Bài toán đa số | Tương ứng một bộ đếm BM |
| k>n | Không liên quan k | Mọi khóa xuất hiện đều là heavy |
| Dữ liệu có khóa âm | Hỗ trợ nếu so sánh int đúng | Hỗ trợ nếu Map cho phép |
| Không thể replay | Chỉ ứng viên, không luôn xác minh được | Ứng viên và sai số, không phải exact |
| Yêu cầu top-k | Không giải trực tiếp | Không thay thế top-k exact |
| Tần suất rất lớn | Dùng long thay int để đếm | Dùng long cho seen/counters/D |

### Danh sách lỗi cần tránh

1. **Nhầm “đã chọn ứng viên” với “đã chứng minh chiếm đa số”.**
2. **Dùng balance Boyer–Moore làm tần suất thật.**
3. **Quên lượt hai khi đề không bảo đảm có đa số.**
4. **Dùng `>=n/2` thay cho \(>n/2\)**, nhận sai trường hợp đúng một nửa.
5. **Dùng giá trị sentinel -1 để biểu diễn không có**, trong khi khóa -1 có thể hợp lệ.
6. **Khởi tạo balance bằng 1 trước khi đọc bất kỳ phần tử nào**, tạo ứng viên ma.
7. **Giảm balance khi không có ứng viên**, phá bất biến balance≥0.
8. **Không xóa candidate khi balance về 0 nhưng lại coi candidate cũ là hợp lệ**, gây hiểu sai API.
9. **Nhầm Misra–Gries dùng k bộ đếm với dạng chuẩn k−1 bộ đếm cho ngưỡng >n/k**.
10. **Khi bảng MG đầy, tự thêm khóa mới trước khi giảm**, khiến số bộ đếm vượt k−1 hoặc đổi ý nghĩa hủy nhóm.
11. **Chỉ giảm một bộ đếm thay vì tất cả k−1 bộ đếm**, không còn bất biến hủy k khóa phân biệt.
12. **Quên bỏ bản ghi mới trong nhánh giảm đồng loạt**, tính sai n và D.
13. **Không xóa bộ đếm về 0**, làm bảng bị chiếm bởi ứng viên không hoạt động.
14. **Gọi remove trực tiếp trên Map trong vòng for-each thay vì dùng Iterator.remove**, có thể gây `ConcurrentModificationException`.
15. **Tưởng counter MG là số lần xuất hiện thật**, dù nó chỉ là cận dưới.
16. **Lọc ứng viên theo counter mà không phân biệt điều kiện chứng nhận**, có thể bỏ heavy hitter có counter nhỏ nhưng f lớn.
17. **Tin mọi ứng viên MG đều vượt n/k**, chấp nhận false positive.
18. **Tự cho rằng k−1 ứng viên là k−1 khóa phổ biến nhất**, sai mục tiêu top-k.
19. **Tính n bằng số lượng khóa phân biệt**, làm ngưỡng n/k sai.
20. **Dùng chia nguyên n/k nhưng đổi dấu > thành >=**, sai trường hợp bằng ngưỡng.
21. **Không kiểm k≥2**, gây ngưỡng/khả năng chứa không hợp lệ.
22. **Cho k quá lớn mà không tính ngân sách O(k)**, dù phương pháp có thể hiệu quả về số lượt.
23. **Quảng cáo bản duyệt tất cả counter là O(n) độc lập k**, trong khi cận đơn giản là O(nk).
24. **Dùng HashMap như một phép băm “luôn O(1) trường hợp xấu”**, bỏ qua giả định kỳ vọng/triển khai.
25. **Dùng khóa có `equals/hashCode` thay đổi theo thời gian**, Map có thể không còn tra cứu đúng.
26. **Dùng đối tượng làm khóa nhưng không định nghĩa nhất quán equality**, khiến tần suất bị tách hoặc gộp sai.
27. **Cho rằng luồng chỉ đọc được một lần vẫn có thể quét lại mà không lưu/replay**, bỏ qua giả thiết dữ liệu.
28. **Trộn trạng thái từ các đoạn luồng bằng cách cộng counter cùng khóa mà không có bước rút gọn được chứng minh**, có thể vượt k−1 bộ đếm và mất bảo đảm.
29. **Dùng Misra–Gries nguyên dạng cho sliding window có loại bỏ dữ liệu cũ**, trong khi thuật toán mô tả chỉ cập nhật khi thêm và không duy trì phép xóa.
30. **Bỏ qua bản ghi âm/ID ngoài miền nhỏ**, khiến một số test không phát hiện lỗi sentinel.
31. **Dùng int cho số đếm khi tổng bản ghi có thể vượt 2^31−1**, dẫn đến tràn.
32. **Quên bảo đảm \(\hat f(x)\le f(x)\)**, một bộ đếm lớn hơn tần suất thật là dấu hiệu cài sai.
33. **Quên cận trên \(f(x)\le\hat f(x)+D\)**, bỏ sót công cụ QA quan trọng.
34. **Cho rằng bằng nhau của tần suất thật và residual counter là điều kiện bắt buộc**, đánh trượt thuật toán đúng.
35. **Dùng MG để tìm heavy hitters theo trọng số sự kiện mà không sửa chứng minh**, trong khi nhánh giảm mặc định chỉ hủy một đơn vị đếm trên mỗi bản ghi.
36. **Đổi định nghĩa >n/k thành top-k hoặc ≥t mà không sửa thuật toán/điều kiện kiểm**, gây lỗi ngữ nghĩa.
37. **Không xác định luồng có hữu hạn và đã kết thúc chưa**, nên không có n cuối để áp ngưỡng chính xác.
38. **Dùng bộ đếm nguyên của MG làm ước lượng có “sai số xác suất”**, trong khi bất biến chuẩn cho bộ đếm residual là cận tất định.
39. **Chỉ kiểm việc không vượt k−1 bộ đếm**, chưa đủ chứng minh tính đồng đều/sai số/coverage.
40. **Không kiểm đủ các trường hợp có ứng viên giả**, khiến bước xác minh bị bỏ quên.

## 23. Hỏi đáp tự luyện

**Bài 1.** Định nghĩa phần tử chiếm đa số nghiêm ngặt là gì?

*Đáp án:* Một khóa M có \(f(M)>n/2\).

**Bài 2.** Có thể có hai khóa cùng chiếm đa số nghiêm ngặt không?

*Đáp án:* Không, vì tổng tần suất của chúng sẽ vượt n.

**Bài 3.** Boyer–Moore lưu bao nhiêu ứng viên và bộ đếm?

*Đáp án:* **Một ứng viên và một số đếm balance**, O(1) bộ nhớ.

**Bài 4.** Vì sao Boyer–Moore vẫn có thể trả ứng viên giả?

*Đáp án:* Phép hủy cặp chỉ bảo đảm đa số thật **sẽ sống sót**, không bảo đảm phần dư bất kỳ phải là đa số thật.

**Bài 5.** Khi nào có thể bỏ lượt xác minh Boyer–Moore?

*Đáp án:* Khi đề **bảo đảm tồn tại** đa số nghiêm ngặt và chỉ yêu cầu trả khóa ấy.

**Bài 6.** Với [2,2,1,1,1,2,2], đáp án đa số là gì?

*Đáp án:* **2**, tần suất 4 trên n=7.

**Bài 7.** Balance cuối của dãy trên là bao nhiêu?

*Đáp án:* **1**, khác tần suất thật 4.

**Bài 8.** Với n=9,k=3, một khóa xuất hiện 3 lần là heavy hitter không?

*Đáp án:* Không, vì **3 không lớn hơn 9/3**.

**Bài 9.** Có thể có tối đa bao nhiêu khóa với f>n/k?

*Đáp án:* **k−1 khóa**, do nguyên lý tổng tần suất.

**Bài 10.** Misra–Gries dùng bao nhiêu bộ đếm?

*Đáp án:* Tối đa **k−1 bộ đếm dương**.

**Bài 11.** Trong nhánh bảng đầy và khóa mới, MG làm gì?

*Đáp án:* Giảm tất cả k−1 bộ đếm đi một, xóa bộ đếm về 0 và bỏ bản ghi mới.

**Bài 12.** Một lần giảm đồng loạt tương ứng hủy bao nhiêu khóa phân biệt?

*Đáp án:* **k khóa**: khóa mới và k−1 khóa đang theo dõi.

**Bài 13.** Với n phần tử, D lần hủy nhóm và R tổng bộ đếm cuối, công thức đúng là gì?

*Đáp án:* \(\boxed{n=R+kD}\).

**Bài 14.** D bị chặn bởi đại lượng nào?

*Đáp án:* \(D\le\lfloor n/k\rfloor\).

**Bài 15.** Cận sai số của bộ đếm MG là gì?

*Đáp án:* \(0\le f(x)-\hat f(x)\le D\).

**Bài 16.** Tại sao heavy hitter thật không thể bị loại hết?

*Đáp án:* Mỗi nhóm hủy có tối đa một bản ghi của nó; f>n/k≥D nên vẫn còn ít nhất một bản ghi.

**Bài 17.** Một khóa không còn trong bảng MG có thể có f>n/k không?

*Đáp án:* **Không**, theo bảo đảm no false negatives.

**Bài 18.** Một khóa còn trong bảng MG có chắc f>n/k không?

*Đáp án:* **Không**; có thể là ứng viên giả.

**Bài 19.** Nếu counter MG của khóa đã lớn hơn n/k, có thể kết luận gì?

*Đáp án:* Khóa ấy chắc chắn là heavy hitter, vì f≥counter.

**Bài 20.** Với n=20,k=4 và tần suất [7,6,4,1,1,1], những khóa nào thỏa?

*Đáp án:* Những khóa có tần suất **7 và 6**, do ngưỡng >5.

**Bài 21.** Bảng MG cuối ví dụ n=20 có các counter nào?

*Đáp án:* **{1=4,2=3,3=1}**, với D=3.

**Bài 22.** Vì sao không được công bố bộ đếm MG là tần suất chính xác?

*Đáp án:* Những lần giảm đồng loạt đã hủy các lần xuất hiện thực; bộ đếm chỉ là **cận dưới**.

**Bài 23.** Độ phức tạp của Boyer–Moore là gì?

*Đáp án:* O(n) thời gian, O(1) bộ nhớ phụ.

**Bài 24.** Độ phức tạp của bản Misra–Gries duyệt tất cả counter khi giảm?

*Đáp án:* O(nk) thời gian trong trường hợp xấu, O(k) bộ nhớ phụ.

**Bài 25.** Khi có thể đọc lại nguồn, làm thế nào để lấy kết quả heavy hitters exact?

*Đáp án:* Quét lượt hai đếm tần suất của tối đa k−1 ứng viên, chỉ giữ khóa có f>n/k.

**Bài 26.** Misra–Gries có giải trực tiếp bài top-k exact không?

*Đáp án:* Không; **ngưỡng >n/k** và **top-k theo thứ hạng** là hai yêu cầu khác nhau.

**Bài 27.** Với k=2, Misra–Gries có liên hệ với thuật toán nào?

*Đáp án:* Cùng cơ chế hủy cặp như **Boyer–Moore**.

**Bài 28.** Khi luồng không replay được, có thể chắc chắn đếm đúng tần suất của ứng viên chỉ bằng residual counter không?

*Đáp án:* Không; phải có nguồn đếm bổ sung hoặc chấp nhận cận sai số.

**Bài 29.** Với khóa âm -1, cách biểu diễn “không có đa số” nên là gì?

*Đáp án:* Dùng kiểu kết quả tùy chọn như `OptionalInt.empty()`, không lấy -1 làm sentinel.

**Bài 30.** Tại sao cần kiểm không chỉ danh sách đáp án mà còn bất biến n=R+kD?

*Đáp án:* Bất biến phát hiện lỗi cập nhật xóa nhóm hoặc mất bản ghi mà một số ví dụ output có thể không cho thấy.

**Bài 31.** Vì sao k>n thì mọi khóa đã xuất hiện đều thỏa f>n/k?

*Đáp án:* Vì n/k<1, còn tần suất của khóa xuất hiện ít nhất là 1.

**Bài 32.** Nếu phải xử lý sliding window, có dùng nguyên hàm accept của MG để loại dữ liệu quá hạn không?

*Đáp án:* Không; hàm accept chỉ hỗ trợ **thêm**, không có phép xóa tương ứng được chứng minh cho các cửa sổ trượt.

**Bài 33.** Nếu muốn ứng viên có trọng số theo giá trị giao dịch, phải lưu ý gì?

*Đáp án:* Cần định nghĩa tần suất **có trọng số** và dùng biến thể/thuật toán phù hợp, không tự áp bằng chứng hủy từng bản ghi trọng số 1.

**Bài 34.** Một API chỉ trả ứng viên mà không trả “đã xác minh” có nên gọi kết quả là exact không?

*Đáp án:* Không. Tên API và mô tả phải phân biệt **candidate**, **lower-bound residual**, và **verified frequent items**.

**Tổng kết:** Boyer–Moore và Misra–Gries là hai kỹ thuật **tóm tắt luồng bằng bộ nhớ nhỏ** dựa trên phép loại bỏ các nhóm phần tử khác nhau. Boyer–Moore giữ **một ứng viên và balance**, bảo đảm đa số thật \(f>n/2\) không bị bỏ sót, O(n) thời gian/O(1) bộ nhớ. Misra–Gries giữ **tối đa k−1 bộ đếm**, bảo đảm tất cả khóa có \(f>n/k\) nằm trong tập ứng viên, sử dụng O(k) bộ nhớ và bản cập nhật đơn giản có cận O(nk). Với D lần giảm đồng loạt, \(n=\sum counter+kD\) và \(\hat f(x)\le f(x)\le\hat f(x)+D\): counter là **cận dưới**, không phải tần suất chính xác. Nếu có thể quét lại nguồn, duyệt lần hai để đếm ứng viên và lọc ngưỡng nghiêm ngặt là cách trả kết quả **exact**. Khi luồng không thể phát lại, cần nói rõ giới hạn và chỉ công bố **ứng viên/bảo đảm sai số** thích hợp. Java 17 minh họa thuật toán online, bước verify, kiểm soát ứng viên giả, các trường hợp biên và oracle exhaustively kiểm hàng nghìn chuỗi nhỏ để làm sáng tỏ tính đúng.
