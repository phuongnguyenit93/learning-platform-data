# Chọn xử lý trực tuyến hay sắp xếp lại truy vấn ngoại tuyến

## 1. Bài toán: câu hỏi đến lần lượt hay biết trước toàn bộ?

Trong **thiết kế thuật toán truy vấn**, có hai cách tổ chức rất khác nhau:

- **Trực tuyến (online):** khi một truy vấn đến, thuật toán phải xử lý và có thể cần trả kết quả **ngay**, trước khi biết truy vấn tiếp theo. Các truy vấn sau còn có thể phụ thuộc vào câu trả lời trước.
- **Ngoại tuyến (offline):** toàn bộ truy vấn trong một **lô (batch)** đã được biết trước. Thuật toán có thể **sắp xếp lại thứ tự xử lý**, nhóm các truy vấn, quét dữ liệu một lần hoặc thực hiện preprocessing theo lô, miễn kết quả trả cho **đúng từng truy vấn gốc**.

Sự khác biệt không nằm ở việc có Internet hay không. “Online” và “offline” ở đây nói về **thời điểm biết các truy vấn và quyền thay đổi thứ tự xử lý**, không phải kết nối mạng.

### Một ví dụ dễ hình dung

Cho mảng cố định:

~~~text
a = [1, 2, 1, 3, 2, 1]
~~~

Có các truy vấn đếm số **giá trị phân biệt** trong đoạn đóng [L,R]:

~~~text
Query 0: [3,5] -> 3  (3,2,1)
Query 1: [0,2] -> 2  (1,2,1)
Query 2: [0,5] -> 3
Query 3: [2,2] -> 1
Query 4: [1,4] -> 3  (2,1,3,2)
~~~

Nếu biết trước toàn bộ truy vấn, ta có thể **sắp xếp theo R tăng dần** để quét mảng từ trái sang phải một lần. Sau đó đặt các đáp án vào vị trí chỉ số truy vấn ban đầu:

~~~text
answer[0..4] = [3,2,3,1,3]
~~~

Nếu truy vấn thứ hai chỉ được sinh sau khi người dùng xem câu trả lời truy vấn thứ nhất, ta **không biết toàn bộ batch từ đầu**, nên không thể đơn giản áp dụng đúng quy trình offline này.

### Mục tiêu bài học

Hiểu cách xác định **điều kiện cho phép** xử lý ngoại tuyến, chọn cấu trúc dữ liệu cho online, bảo toàn thứ tự kết quả và phân tích đánh đổi về thời gian, bộ nhớ và độ trễ. Ví dụ chính là:

1. **Online:** cập nhật một phần tử và lấy tổng đoạn bằng **Fenwick Tree**.
2. **Offline:** đếm số phần tử phân biệt trong đoạn của **mảng tĩnh**, xử lý truy vấn theo đầu phải R với **last occurrence + Fenwick Tree**.

Hai ví dụ cố ý có **yêu cầu khác nhau**: ví dụ thứ nhất có cập nhật và cần trả ngay, còn ví dụ thứ hai dùng một batch truy vấn trên mảng không đổi. Không được lấy thuật toán offline thứ hai rồi cho rằng tự động hỗ trợ mọi dạng update.

## 2. Online: câu trả lời phải có trước truy vấn tiếp theo

Hãy tưởng tượng một hệ thống duy trì một mảng điểm và nhận chuỗi thao tác:

~~~text
SUM(0,5)
SET(2,5)
SUM(1,3)
SET(0,4)
SUM(0,2)
~~~

Các `SUM` phải nhìn thấy mọi cập nhật **đã xảy ra trước nó** và không được nhìn thấy cập nhật trong tương lai. Thứ tự thao tác là một phần ngữ nghĩa của bài toán.

Với mảng ban đầu `[1,2,1,3,2,1]`:

~~~text
SUM(0,5) = 10
SET(2,5)    -> [1,2,5,3,2,1]
SUM(1,3) = 10
SET(0,4)    -> [4,2,5,3,2,1]
SUM(0,2) = 11
~~~

Không thể tùy ý đưa `SET(2,5)` lên trước `SUM(0,5)` rồi vẫn mong nhận được 10. Làm vậy đã thay đổi **trạng thái dữ liệu mà truy vấn nhìn thấy**.

### Truy vấn thích nghi (adaptive queries)

Một dạng online còn nghiêm ngặt hơn: truy vấn mới được tạo từ kết quả trước.

~~~text
answer1 = query(2,7)
L2 = answer1 % n
answer2 = query(L2, n-1)
~~~

Trước khi biết `answer1`, chưa thể xác định `L2`. Do đó không thể có sẵn toàn bộ bộ truy vấn để sắp xếp.

Các đề thi đôi khi dùng cơ chế XOR với đáp án trước:

~~~text
L = inputL XOR lastAnswer
R = inputR XOR lastAnswer
~~~

Lúc đó, dù toàn bộ **dòng dữ liệu mã hóa** đã đọc vào bộ nhớ, các truy vấn thực sự vẫn phụ thuộc kết quả trước và cần xử lý theo thứ tự. Chỉ nhìn thấy cả file input không làm nó trở thành một batch ngoại tuyến hợp lệ.

### Online không có nghĩa không được tiền xử lý

Online vẫn có thể xây một cấu trúc từ dữ liệu ban đầu: prefix sums, Fenwick Tree, segment tree, sparse table hoặc persistent structures. Điều kiện là **không phải biết các truy vấn tương lai** mới xây được cấu trúc và mỗi câu trả lời phải có ở thời điểm yêu cầu.

## 3. Offline: được đổi thứ tự xử lý, không được đổi ý nghĩa truy vấn

Giả sử toàn bộ q truy vấn `(L_i,R_i)` đã biết trước và cùng hỏi trên một mảng **cố định**. Khi đó ta có thể:

1. Gắn mỗi truy vấn với **ID ban đầu**.
2. Sắp xếp các truy vấn theo khóa hữu ích (ví dụ R, L, ngưỡng giá trị, kích thước đoạn).
3. Chuyển một trạng thái dữ liệu từ truy vấn này sang truy vấn tiếp theo một cách tiết kiệm.
4. Ghi `answer[id] = result`.
5. Xuất `answer[0],answer[1],...,answer[q-1]` theo thứ tự gốc.

Ví dụ:

~~~text
Original order:
 id0:[3,5]  id1:[0,2]  id2:[0,5]  id3:[2,2]  id4:[1,4]

Order by R:
 id1:[0,2]  id3:[2,2]  id4:[1,4]  id0:[3,5]  id2:[0,5]
~~~

Lưu ý **chỉ đổi thứ tự tính toán**. Ta không được đổi `L_i,R_i`, không thay mảng gốc, không làm kết quả của một truy vấn phụ thuộc vào truy vấn khác một cách sai.

### Đáp án theo ID khác với thứ tự xử lý

Lỗi rất phổ biến:

~~~text
for query in sortedQueries:
    print(compute(query)) // sai thu tu cau tra loi
~~~

Trong ví dụ, in ngay khi xử lý sẽ xuất:

~~~text
2, 1, 3, 3, 3
~~~

nhưng bộ đáp án được yêu cầu theo thứ tự ban đầu là:

~~~text
3, 2, 3, 1, 3
~~~

**Luôn gắn ID** nếu kết quả cần khớp đúng thứ tự input.

### Offline chỉ hợp lệ khi các thao tác đủ độc lập để đổi thứ tự

Nếu các truy vấn chỉ đọc **cùng một ảnh chụp (snapshot) của dữ liệu**, thứ tự tính toán không ảnh hưởng giá trị. Nếu có cập nhật, truy vấn thời gian hoặc phụ thuộc lẫn nhau, cần giữ đúng mốc thời gian; vẫn có những thuật toán offline hỗ trợ update, nhưng phải đưa **thời gian** vào mô hình, không chỉ sort tùy ý.

## 4. Checklist chọn online hay offline

Trước khi chọn thuật toán, trả lời các câu hỏi:

| Câu hỏi | Nghiêng về online | Nghiêng về offline |
| --- | --- | --- |
| Truy vấn tiếp theo phụ thuộc đáp án hiện tại? | Có | Không |
| Phải phản hồi ngay từng câu hỏi? | Có | Có thể chờ xử lý cả batch |
| Toàn bộ truy vấn đã biết trước? | Không | Có |
| Dữ liệu thay đổi giữa các truy vấn? | Cần cấu trúc cập nhật | Cần xử lý mốc thời gian/thuật toán chuyên biệt |
| Được phép thay thứ tự tính toán? | Thường không | Có, nếu bảo toàn ngữ nghĩa |
| Q rất lớn và sort giúp quét một chiều? | Có thể vẫn online | Offline thường hấp dẫn |
| Bộ nhớ để lưu q truy vấn hạn chế? | Có thể streaming | Cần cân nhắc O(q) bộ nhớ |
| Latency mỗi truy vấn là yêu cầu cứng? | Ưu tiên online | Batch có thể không phù hợp |
| Chỉ cần một lần trả kết quả cuối? | Có thể online nhưng không bắt buộc | Dễ tận dụng offline |
| Có thể xử lý phần sau dựa trên phần trước? | Phải giữ phụ thuộc | Không được đảo phụ thuộc |

### Một quy tắc thực dụng

**Không chọn offline chỉ vì nhìn thấy nhiều truy vấn.** Đầu tiên phải chứng minh việc sắp xếp lại không làm thay đổi tập kết quả. Sau đó mới so tổng chi phí của hai phương án.

Nếu tất cả truy vấn là tổng đoạn trên mảng **tĩnh**, một prefix sum O(n) xây một lần, trả mỗi truy vấn O(1), có thể **nhanh và đơn giản hơn** việc lưu/sort q truy vấn offline.

Nếu có cập nhật điểm xen giữa tổng đoạn, Fenwick hoặc Segment Tree online thường tự nhiên hơn.

Nếu truy vấn là **số giá trị phân biệt trên đoạn** và mảng không thay đổi, sắp xếp theo R cùng Fenwick/last occurrence là một phương án offline rất hiệu quả.

## 5. Online tổng đoạn: prefix sums và Fenwick Tree

### Trường hợp mảng tĩnh

Định nghĩa prefix sum:

~~~text
prefix[0] = 0
prefix[i+1] = prefix[i] + a[i]

sumInclusive(L,R) = prefix[R+1] - prefix[L]
~~~

Xây prefix O(n), mỗi truy vấn tổng đoạn O(1) và dùng O(n) bộ nhớ. Nếu không có cập nhật, đây là baseline rất mạnh.

### Khi có cập nhật SET(index,value)

Một lệnh SET làm thay đổi nhiều prefix từ index+1 về sau. Nếu cập nhật trực tiếp vào toàn bộ prefix array, mỗi cập nhật có thể tốn O(n). Ta có thể dùng:

- **Fenwick Tree (Binary Indexed Tree):** cập nhật một điểm O(log n), tổng tiền tố O(log n), tổng đoạn O(log n).
- **Segment Tree:** tổng đoạn và cập nhật điểm O(log n), dễ mở rộng sang nhiều phép gộp/biến thể lazy propagation nhưng chi phí cài đặt/nhớ lớn hơn.
- **Sqrt decomposition:** cân bằng theo khối trong một số bài, thường O(√n) mỗi thao tác nếu thiết kế phù hợp.

Ví dụ chuỗi thao tác online:

~~~text
a = [1,2,1,3,2,1]

SUM(0,5) -> 10
SET(2,5)
SUM(1,3) -> 10
SET(0,4)
SUM(0,2) -> 11
SUM(0,5) -> 17
SUM(4,5) -> 3
~~~

Fenwick chỉ cần giữ các tổng nhóm được cập nhật khi một phần tử thay đổi. Nó không cần biết `SUM` tiếp theo sẽ hỏi ở đâu.

## 6. Fenwick Tree: cách cập nhật và hỏi tổng

Trong Fenwick Tree 1-index, đặt:

~~~text
lowbit(i) = i & (-i)
~~~

`bit[i]` chứa tổng của đoạn:

~~~text
[i-lowbit(i)+1, i]  (theo chi so 1-based)
~~~

Ví dụ:

~~~text
bit[1] -> a[1]
bit[2] -> a[1]+a[2]
bit[3] -> a[3]
bit[4] -> a[1]+a[2]+a[3]+a[4]
~~~

Ở đây `a[1]` của ví dụ Fenwick là phần tử 1-based, khác `a[0]` của mảng Java. Trong code Java, dữ liệu gốc dùng 0-based, Fenwick nội bộ cộng 1 vào chỉ số.

### Cập nhật tăng một điểm

Muốn tăng a[index] một lượng `delta`:

~~~text
i = index + 1
while i <= n:
    bit[i] += delta
    i += lowbit(i)
~~~

Vì mỗi bước tiến lên nút cha tích lũy lớn hơn, có O(log n) nút bị cập nhật.

### Tổng tiền tố

Muốn tính tổng đoạn `[0,endExclusive)`:

~~~text
i = endExclusive
sum = 0

while i > 0:
    sum += bit[i]
    i -= lowbit(i)

return sum
~~~

Do đó:

~~~text
sumInclusive(L,R)
    = prefixExclusive(R+1)
    - prefixExclusive(L)
~~~

**R là inclusive**, nên phải truyền R+1 vào prefixExclusive.

### SET thay vì ADD

Nếu API là `SET(index,newValue)`, ta cần biết giá trị hiện tại để tính:

~~~text
delta = newValue - oldValue
~~~

Sau đó Fenwick được cập nhật bằng delta và lưu giá trị mới vào mảng. Nếu chỉ cộng `newValue` vào Fenwick mà không trừ `oldValue`, ta đã triển khai **ADD** chứ không phải **SET**.

### Tính toán với giá trị âm

Fenwick cộng tổng vẫn đúng với số âm. Nhưng nếu dùng Fenwick để tìm vị trí tiền tố theo ngưỡng bằng binary lifting, thường cần điều kiện đơn điệu của prefix, ví dụ các tần suất không âm. Không tự suy ra mọi thuật toán “tìm chỉ số theo prefix” vẫn đúng khi giá trị có thể âm.

### `long` cho tổng

Dù mỗi phần tử là `int`, tổng nhiều phần tử có thể vượt `Integer.MAX_VALUE`. Java demo lưu Fenwick bằng `long`, tính delta bằng ép `(long)` trước khi trừ để tránh overflow.

## 7. Offline đếm phần tử phân biệt: phát biểu chính xác

Cho **mảng tĩnh** gồm n số nguyên `a[0..n−1]` và q truy vấn:

~~~text
distinct(L,R)
= so gia tri khac nhau xuat hien
  trong a[L], a[L+1],...,a[R]
~~~

Các chỉ số **0-based**, đoạn **đóng** `[L,R]`, điều kiện:

~~~text
0 <= L <= R < n
~~~

Một cách đơn giản là duyệt mỗi đoạn, chèn vào HashSet và trả kích thước. Tổng thời gian O(Σ(R−L+1)) trung bình theo hash; tệ nhất có thể xấp xỉ O(nq).

Nếu biết trước các truy vấn, ta có thể sắp xếp theo R và dùng Fenwick để trả:

~~~text
O(n log n + q log n + q log q)  (expected hash operations)
~~~

đồng thời bộ nhớ O(n+q).

### Ý tưởng không phải lưu tần suất mọi giá trị trong mọi đoạn

Thay vì tính lại tập distinct cho từng truy vấn, ta quét tiền tố `[0..R]` và đánh dấu **duy nhất một vị trí** cho mỗi giá trị đã xuất hiện: vị trí **xuất hiện cuối cùng không vượt R**.

Tại thời điểm quét đến R, đánh dấu:

~~~text
mark[i] = 1
    iff i la lan xuat hien cuoi cua a[i]
        trong a[0..R]
mark[i] = 0 trong cac truong hop con lai
~~~

Như vậy, tổng `mark[L..R]` chính là số giá trị khác nhau trong `[L,R]`.

### Tại sao cần xử lý theo R tăng dần?

Khi R tăng một đơn vị, ta chỉ thêm giá trị mới a[R], có thể phải xóa đánh dấu ở lần xuất hiện trước của chính giá trị đó. Đây là một trạng thái có thể cập nhật **từng bước**, không cần khởi tạo lại từ đầu cho mỗi truy vấn.

Để tránh quét R từ 0 tới n−1 cho từng query, ta **sort cả batch theo R**, giữ con trỏ đang quét.

## 8. Bất biến “lần xuất hiện cuối” và các thao tác

Duy trì:

~~~text
lastSeen[value] = index xuat hien gan nhat
                  trong tien to da quet
~~~

và một Fenwick trên mảng đánh dấu 0/1.

Khi quét tới vị trí R:

~~~text
value = a[R]

if value da duoc thay truoc do:
    old = lastSeen[value]
    fenwick.add(old, -1)    // bo danh dau cu

fenwick.add(R, +1)         // danh dau lan moi nhat
lastSeen[value] = R
~~~

Sau cập nhật, tất cả giá trị đã xuất hiện trong `[0,R]` đều có **đúng một vị trí đánh dấu 1**: vị trí xuất hiện cuối cùng. Mọi vị trí khác có mark 0.

Khi cần trả truy vấn `(L,R)` tại đúng thời điểm đã quét tới R:

~~~text
answer = fenwick.sumInclusive(L,R)
~~~

### Chứng minh một giá trị được đếm đúng một lần

Xét một giá trị bất kỳ x.

- Nếu x **không xuất hiện** trong `[L,R]`, thì vị trí lastSeen[x] trong tiền tố `[0,R]` hoặc không tồn tại, hoặc nằm **trước L**. Không có đánh dấu 1 cho x trong `[L,R]`.
- Nếu x **có xuất hiện** trong `[L,R]`, vị trí xuất hiện cuối của x trong tiền tố `[0,R]` phải nằm trong `[L,R]`. Fenwick có đúng một đánh dấu 1 cho x ở vị trí ấy.

Do vậy mỗi giá trị phân biệt trong đoạn đóng góp đúng 1 vào tổng, và giá trị ngoài đoạn không đóng góp. Tổng Fenwick trả đúng số distinct.

### Lưu ý quan trọng

- Có thể dùng `HashMap<Integer,Integer>` làm lastSeen; giá trị âm, 0 hoặc rất lớn đều hợp lệ.
- Nếu miền giá trị nhỏ, có thể dùng mảng lastSeen và khởi tạo sentinel −1; phải ánh xạ chỉ số đúng và đủ bộ nhớ.
- **Coordinate compression** thay giá trị nguyên bằng ID 0..d−1 giúp sử dụng mảng tần suất/lastSeen; có thêm chi phí sort và lập ánh xạ.
- Nếu a[R] từng xuất hiện tại vị trí 0, `old=0` là vị trí **hợp lệ**; không được nhầm với “chưa thấy”.
- Update phải thực hiện **xóa đánh dấu cũ rồi thêm đánh dấu mới**, không được chỉ thêm +1 vì sẽ đếm trùng các lần xuất hiện cùng giá trị.

## 9. Mô phỏng đầy đủ trên mảng sáu phần tử

Cho:

~~~text
a = [1,2,1,3,2,1]
~~~

Ta quét R từ 0 đến 5. Ký hiệu `active` là những chỉ số đang được đánh dấu 1 trong Fenwick:

| R sau xử lý | a[R] | Đánh dấu cũ bị xóa | Active positions | Giá trị tại active |
| ---: | ---: | ---: | --- | --- |
| 0 | 1 | Không | {0} | {1} |
| 1 | 2 | Không | {0,1} | {1,2} |
| 2 | 1 | 0 | {1,2} | {2,1} |
| 3 | 3 | Không | {1,2,3} | {2,1,3} |
| 4 | 2 | 1 | {2,3,4} | {1,3,2} |
| 5 | 1 | 2 | {3,4,5} | {3,2,1} |

Queries ban đầu (không được sort khi xuất):

~~~text
id0 [3,5] -> 3
id1 [0,2] -> 2
id2 [0,5] -> 3
id3 [2,2] -> 1
id4 [1,4] -> 3
~~~

Bộ xử lý sort theo R:

~~~text
R=2: id1 [0,2], id3 [2,2]
R=4: id4 [1,4]
R=5: id0 [3,5], id2 [0,5]
~~~

Tại R=2, active {1,2} nên:

~~~text
distinct(0,2) = 2
distinct(2,2) = 1
~~~

Tại R=4, active {2,3,4} nên `distinct(1,4)=3`. Tại R=5, active {3,4,5} nên `distinct(3,5)=3` và `distinct(0,5)=3`.

Ghi lại theo ID:

~~~text
answer[0] = 3
answer[1] = 2
answer[2] = 3
answer[3] = 1
answer[4] = 3

Result = [3,2,3,1,3]
~~~

### Vì sao không mất thông tin khi bỏ đánh dấu ở vị trí 0?

Ở R=2, giá trị 1 đã xuất hiện tại 0 và 2. Đánh dấu tại 0 được bỏ vì **vị trí 2 đại diện cho giá trị 1** trong mọi đoạn có đầu phải R=2. Nếu một đoạn chứa 0 nhưng **không** chứa 2, ví dụ [0,0], nó phải được xử lý ở **R=0**, không phải R=2. Đó chính là lý do xử lý offline theo R tăng dần bảo toàn kết quả.

## 10. Chứng minh tính đúng của thuật toán offline

Ta chứng minh với số học nguyên chính xác trong Fenwick.

**Bất biến sau khi xử lý chỉ số R:** với mỗi giá trị x có mặt trong tiền tố `[0,R]`, Fenwick có đúng một dấu 1 tại `lastSeen[x]`; các vị trí khác thuộc giá trị ấy có dấu 0.

**Cơ sở R=0:** chưa có vị trí nào được đánh dấu. Xử lý a[0] bằng `add(0,+1)`, lastSeen[a[0]]=0. Bất biến đúng.

**Bước quy nạp:** giả sử đúng sau R−1. Tại R, với x=a[R]:

- Nếu x chưa xuất hiện, thêm dấu 1 tại R; mọi giá trị cũ giữ đại diện cuối cùng.
- Nếu x đã xuất hiện, bỏ dấu 1 cũ ở lastSeen[x], thêm dấu 1 tại R. Giá trị x tiếp tục có đúng một đại diện và đó là vị trí mới nhất. Các giá trị khác không đổi.

Bất biến đúng sau R.

**Tính đúng của truy vấn:** với query `[L,R]`, mỗi giá trị x xuất hiện trong đoạn được đếm đúng một lần bởi dấu 1 tại lần xuất hiện cuối của x trong `[0,R]`, vốn nằm trong `[L,R]`. Các giá trị không xuất hiện trong đoạn không có dấu trong đoạn. Fenwick tính tổng các dấu này nên trả chính xác số distinct.

**Thứ tự trả kết quả:** sort chỉ quyết định thời điểm xử lý; giá trị được đặt vào `answer[query.originalIndex]`, nên thứ tự output không bị thay đổi. Do đó toàn bộ thuật toán đúng cho mọi mảng tĩnh và batch truy vấn hợp lệ.

### Điểm không được suy rộng sai

Chứng minh trên dùng **một snapshot của mảng**. Nếu một cập nhật đổi a[i] giữa hai truy vấn, invariant “lastSeen của các giá trị trong tiền tố đã quét” có thể không còn phản ánh trạng thái tại thời điểm query. Không được áp dụng trực tiếp cùng sweep một lần cho chuỗi thao tác có update.

## 11. Sắp xếp truy vấn, chỉ số và bộ nhớ

Cấu trúc một truy vấn ngoại tuyến thường cần:

~~~text
Query {
    left
    right
    originalIndex
}
~~~

Ta sắp xếp theo:

~~~text
(right ASC, originalIndex ASC)
~~~

`originalIndex` dùng để đưa đáp án về đúng vị trí; tie-break theo ID làm thứ tự xử lý xác định khi hai truy vấn có cùng R. Tính đúng **không phụ thuộc** việc dùng sort stable hay unstable nếu mỗi query vẫn giữ ID.

### Những quy ước cần thống nhất

- **0-based hay 1-based?** Java demo nhận 0-based, cả L và R đều inclusive.
- **Đoạn đóng hay nửa mở?** Demo dùng `[L,R]`, nên Fenwick tính `prefix(R+1)-prefix(L)`.
- **Query trống có hợp lệ không?** Demo **không hỗ trợ query L>R**; cần từ chối trước khi sort.
- **Mảng rỗng?** Có thể có **0 query**, trả mảng đáp án rỗng. Không có đoạn không rỗng hợp lệ trên n=0.
- **L hoặc R ngoài mảng?** Từ chối ngay, không tự cắt cận.
- **Truy vấn trùng nhau?** Hợp lệ; các ID vẫn nhận cùng đáp án.
- **Giá trị âm / trùng / cực trị int?** HashMap hỗ trợ như các khóa bình thường.

### Có cần sort chính mảng giá trị a không?

**Không.** Ta chỉ sort danh sách truy vấn theo R, không sort mảng. Sort a làm thay đổi các đoạn theo vị trí và câu hỏi đã đặt. Đây là một trong những lỗi nghiêm trọng nhất khi mới học offline queries.

### Ghi mọi đáp án trước rồi xuất theo input

Khi yêu cầu output lần lượt, thuật toán nên trả `int[] answer` có kích thước q. Nếu q rất lớn và bộ nhớ hạn chế, có thể cần chia batch hoặc giải pháp streaming; nhưng **không được** chia batch tùy tiện khi chiến lược cần biết tất cả truy vấn để tối ưu thứ tự.

## 12. Phân tích độ phức tạp và đánh đổi chính

Gọi n là số phần tử mảng, q là số truy vấn, d là số giá trị khác nhau.

### Online point update + range sum bằng Fenwick

| Thao tác | Thời gian | Ghi chú |
| --- | ---: | --- |
| Khởi tạo bằng n lần add | O(n log n) | Có thể build Fenwick O(n) bằng kỹ thuật riêng |
| SET một phần tử | O(log n) | Dùng delta mới−cũ |
| SUM đoạn | O(log n) | Hai prefix sums |
| Bộ nhớ | O(n) | Mảng gốc + Fenwick |

Đáp án trả ngay sau từng thao tác. Tổng runtime phụ thuộc số cập nhật và truy vấn, không có chi phí sort q truy vấn.

### Offline distinct theo R + Fenwick

| Công việc | Thời gian | Bộ nhớ |
| --- | ---: | ---: |
| Gắn ID cho q queries | O(q) | O(q) |
| Sort queries theo R | O(q log q) | Phụ thuộc cài sort; có thể O(q) bộ đệm |
| Quét n vị trí | O(n) thao tác vòng ngoài | O(n) Fenwick |
| Mỗi vị trí xóa/thêm dấu | O(log n) | lastSeen O(d) |
| Mỗi query lấy tổng đoạn | O(log n) | answer O(q) |
| Tổng kỳ vọng với HashMap | O(q log q+(n+q)log n) | O(n+q+d) |

Dùng `HashMap<Integer,Integer>` nghĩa là thao tác ánh xạ lastSeen có thời gian **kỳ vọng** O(1) trong giả thiết hashing phù hợp. Nếu cần cận xác định cho mọi input, có thể **coordinate-compress** giá trị trước, rồi dùng mảng lastSeen; chi phí thêm khoảng O(n log n) cho sắp xếp/ánh xạ.

### Khi nào không nên dùng offline?

Nếu q rất ít, chi phí sort và cấu trúc bổ sung có thể không đáng so với xử lý mỗi truy vấn trực tiếp. Nếu dữ liệu quá lớn để lưu batch hoặc cần phản hồi ở độ trễ thấp, online phù hợp hơn. Nếu cần trả kết quả cho những query không thể biết trước, offline một batch không đáp ứng yêu cầu.

### So đúng đơn vị độ phức tạp

Không nên so trực tiếp “O(log n) online” với “O((n+q)log n) offline” mà bỏ qua rằng chúng giải **loại truy vấn khác nhau** trong ví dụ. Muốn quyết định phương án thực tế, phải đặt chúng trên **cùng chức năng, cùng mô hình cập nhật và cùng ràng buộc**.

## 13. Những kỹ thuật ngoại tuyến khác và điều kiện áp dụng

Sắp xếp theo R chỉ là một mẫu chung của thuật toán offline. Tùy bài, có thể chọn khóa sort khác.

### Sweep line theo tọa độ

Ví dụ đếm số điểm trong các truy vấn về tọa độ hoặc số khoảng chứa một điểm. Nếu sự kiện và query có tọa độ, sort tất cả theo tọa độ, rồi cập nhật một cấu trúc khi đi qua từng sự kiện.

**Tie order** rất quan trọng: với đoạn đóng `[L,R]`, query tại đúng L/R cần xử lý sự kiện thêm/xóa ở thời điểm phù hợp; nếu sort ties sai, điểm biên có thể bị đếm thiếu hoặc thừa.

### Sort theo ngưỡng

Với câu hỏi “có bao nhiêu phần tử trong đoạn [L,R] lớn hơn K?”, có thể sort phần tử theo giá trị và sort query theo ngưỡng K, rồi dùng Fenwick đánh dấu các vị trí thỏa điều kiện. Cần thống nhất `>` hay `>=` vì cách xử lý các giá trị bằng K khác nhau.

### Offline connectivity và DSU

Nếu một bài chỉ **xóa cạnh** qua thời gian và hỏi liên thông, có thể đảo thời gian: biến các thao tác xóa thành **thêm cạnh** và dùng DSU, vì DSU hỗ trợ gộp thành phần rất tốt. Nhưng khi đảo, phải giữ đúng trạng thái cuối, những cạnh thực sự đang tồn tại và thứ tự câu hỏi gốc.

Nếu có cả thêm và xóa cạnh tùy ý, có thể cần **DSU rollback + segment tree trên thời gian**; không được coi DSU thông thường là có phép “ungroup” tự nhiên.

### Parallel binary search

Nhiều query cùng tìm ngưỡng nhỏ nhất thỏa một tính chất đơn điệu có thể dùng **parallel binary search**: nhóm các query theo mid, quét cập nhật/kiểm tra theo lô, lặp nhiều vòng. Nó chỉ đúng khi điều kiện monotone và trạng thái được reset/rebuilt phù hợp giữa các vòng.

### CDQ divide-and-conquer

Trong một số bài đếm cặp/truy vấn nhiều chiều, có thể chia theo thời gian hoặc chỉ số, giải đóng góp từ nửa trước sang nửa sau bằng sort+Fenwick. Đây là thuật toán offline dựa trên cấu trúc phụ thuộc, chứ không đơn giản là “sort hết mọi truy vấn”.

### Nhận xét chung

Thuật toán ngoại tuyến thường biến **nhiều query độc lập** thành một trình tự trạng thái biến đổi có tính đơn điệu hoặc chỉ cần chi phí cập nhật nhỏ giữa hai query liên tiếp. Bản chất là **tận dụng việc biết trước câu hỏi để chọn thứ tự tính toán rẻ hơn**.

## 14. Mo's algorithm: một ví dụ offline khác

**Mo's algorithm** xử lý các truy vấn đoạn trên **mảng tĩnh** bằng cách chọn thứ tự sao cho vị trí L và R giữa các query kế tiếp dịch chuyển ít.

Thường chọn kích thước block B≈√n, sort theo:

~~~text
block(L) = floor(L / B)
then R (tang hoac dan xen giam theo block)
~~~

Duy trì cửa sổ hiện tại `[curL,curR]`. Khi chuyển đến `[L,R]`, lần lượt thêm hoặc xóa phần tử tại hai đầu cho tới khi hai đoạn trùng nhau.

~~~text
while curL > L: add(--curL)
while curR < R: add(++curR)
while curL < L: remove(curL++)
while curR > R: remove(curR--)
answer[id] = currentStatistic
~~~

Nếu statistic có thể cập nhật O(1) khi thêm/xóa một phần tử, tổng thời gian thường được chặn bởi **O(n√n + q√n)** cho khối kích thước √n (cộng chi phí sort), với giả thiết phù hợp và q truy vấn.

### Mo's khác sweep theo R ở đâu?

- Sweep theo R với last occurrence chỉ cần quét **R tăng**, biết cách mã hóa câu trả lời distinct bằng các vị trí cuối.
- Mo's cho phép L/R dịch chuyển **theo cả hai hướng**, thường dùng các hàm statistic có thao tác add/remove hiệu quả.
- Với **distinct count mảng tĩnh**, sweep last occurrence+Fenwick thường có độ phức tạp tiệm cận tốt hơn Mo's.
- Với statistic khó biểu diễn bằng một phép sweep nhưng dễ duy trì cửa sổ, Mo's có thể hữu ích.

### Mo's có tự hỗ trợ cập nhật không?

Phiên bản Mo's cơ bản dùng **mảng tĩnh**. Có biến thể **Mo's with modifications/time dimension** để xử lý update offline, nhưng cần đưa **thời điểm** của query/update vào trạng thái, áp dụng/rollback update cẩn thận và phân tích chi phí khác. Không được áp dụng code Mo's tĩnh hoặc code last occurrence trên snapshot rồi mong nó hiểu các lần cập nhật xen giữa.

## 15. Java 17: cả xử lý online và offline trong một chương trình

Chương trình sau chạy trực tiếp với JDK 17, không cần thư viện ngoài JDK.

**API trực tuyến**:

- `OnlineRangeSum` nhận `int[]`, giữ bản sao và Fenwick chứa tổng kiểu `long`.
- `set(index,value)` thay đúng giá trị ở một vị trí, dùng delta rồi cập nhật.
- `sum(left,right)` trả tổng đoạn đóng theo trạng thái hiện tại.
- Input nguyên vẹn khi người gọi tạo `OnlineRangeSum`.

**API ngoại tuyến**:

- `RangeQuery(left,right)` là một đoạn đóng trên mảng gốc.
- `offlineDistinctCounts(int[] values, RangeQuery[] queries)` nhận toàn bộ batch, validate mọi đoạn, gắn ID, sort theo R, quét lastSeen, trả đáp án theo **thứ tự truy vấn ban đầu**.
- Mảng giá trị và mảng query của người gọi **không bị sắp xếp hay sửa**.
- Hỗ trợ giá trị âm, trùng, cả `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.

**Kiểm thử**:

- So offline distinct với `HashSet` vét cạn trên mọi mảng dài 0..6 có phần tử trong {−1,0,1}, tổng **1.093 mảng và 19.956 truy vấn đoạn**.
- So online Fenwick với cách cộng trực tiếp trên mọi mảng dài 0..5, sau những cập nhật SET xác định: **364 mảng và 26.655 phép kiểm tổng đoạn**.
- Kiểm mảng rỗng, giá trị nguyên cực trị, truy vấn ngoài cận và SET ngoài cận.

**Lưu nguyên chương trình vào tệp `QueryChoiceDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class QueryChoiceDemo {

    public record RangeQuery(int left, int right) {}
    private record IndexedQuery(int left, int right, int id) {}

    // Internal Fenwick works with 0-based API indices.
    // Prefix endpoint is exclusive.
    private static final class Fenwick {
        private final long[] bit;

        Fenwick(int n) {
            if (n < 0) {
                throw new IllegalArgumentException("negative size");
            }
            this.bit = new long[n + 1];
        }

        int size() {
            return bit.length - 1;
        }

        void add(int index, long delta) {
            if (index < 0 || index >= size()) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            for (int i = index + 1; i < bit.length;
                    i += i & -i) {
                bit[i] += delta;
            }
        }

        long prefixExclusive(int end) {
            if (end < 0 || end > size()) {
                throw new IllegalArgumentException(
                        "prefix out of bounds");
            }
            long total = 0;
            for (int i = end; i > 0; i -= i & -i) {
                total += bit[i];
            }
            return total;
        }

        long sumInclusive(int left, int right) {
            if (left < 0 || right >= size() || left > right) {
                throw new IllegalArgumentException(
                        "range out of bounds");
            }
            return prefixExclusive(right + 1)
                    - prefixExclusive(left);
        }
    }

    // Online: point SET and range SUM, current array state.
    public static final class OnlineRangeSum {
        private final int[] values;
        private final Fenwick fenwick;

        public OnlineRangeSum(int[] initial) {
            Objects.requireNonNull(initial, "initial");
            this.values = initial.clone();
            this.fenwick = new Fenwick(initial.length);
            for (int i = 0; i < values.length; i++) {
                fenwick.add(i, values[i]);
            }
        }

        public void set(int index, int newValue) {
            if (index < 0 || index >= values.length) {
                throw new IllegalArgumentException(
                        "index out of bounds");
            }
            // Cast BEFORE subtraction to avoid int overflow.
            long delta = (long) newValue - values[index];
            fenwick.add(index, delta);
            values[index] = newValue;
        }

        public long sum(int left, int right) {
            return fenwick.sumInclusive(left, right);
        }
    }

    // Offline: immutable array, all queries available up front.
    public static int[] offlineDistinctCounts(
            int[] values, RangeQuery[] queries) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(queries, "queries");
        int n = values.length;
        int q = queries.length;

        IndexedQuery[] sorted = new IndexedQuery[q];
        for (int i = 0; i < q; i++) {
            RangeQuery query = Objects.requireNonNull(
                    queries[i], "query");
            int left = query.left();
            int right = query.right();
            if (left < 0 || left > right || right >= n) {
                throw new IllegalArgumentException(
                        "range out of bounds");
            }
            sorted[i] = new IndexedQuery(left, right, i);
        }

        Arrays.sort(sorted,
                Comparator.comparingInt(IndexedQuery::right)
                          .thenComparingInt(IndexedQuery::id));

        Fenwick marks = new Fenwick(n);
        Map<Integer, Integer> lastSeen = new HashMap<>();
        int[] answers = new int[q];
        int nextQuery = 0;

        for (int right = 0; right < n; right++) {
            Integer old = lastSeen.put(values[right], right);
            if (old != null) {
                marks.add(old, -1L);
            }
            marks.add(right, 1L);

            // Every query whose right endpoint is 'right'.
            while (nextQuery < q
                    && sorted[nextQuery].right() == right) {
                IndexedQuery query = sorted[nextQuery++];
                answers[query.id()] = Math.toIntExact(
                        marks.sumInclusive(
                                query.left(), query.right()));
            }
        }

        if (nextQuery != q) {
            throw new AssertionError("unprocessed query");
        }
        return answers;
    }

    // Oracle independent of the last-occurrence sweep.
    private static int naiveDistinct(
            int[] values, int left, int right) {
        Set<Integer> unique = new HashSet<>();
        for (int i = left; i <= right; i++) {
            unique.add(values[i]);
        }
        return unique.size();
    }

    private static int checkAllOnlineRanges(
            OnlineRangeSum online, int[] expected) {
        int count = 0;
        for (int left = 0; left < expected.length; left++) {
            long direct = 0;
            for (int right = left;
                    right < expected.length; right++) {
                direct += expected[right];
                if (online.sum(left, right) != direct) {
                    throw new AssertionError(
                            "online sum mismatch");
                }
                count++;
            }
        }
        return count;
    }

    private static int[] verifyOnlineExhaustive() {
        int arrays = 0;
        int rangeChecks = 0;

        for (int n = 0; n <= 5; n++) {
            int cases = 1;
            for (int i = 0; i < n; i++) {
                cases *= 3;
            }

            for (int code = 0; code < cases; code++) {
                int[] values = new int[n];
                int value = code;
                for (int i = 0; i < n; i++) {
                    values[i] = value % 3 - 1;
                    value /= 3;
                }

                int[] original = values.clone();
                int[] expected = values.clone();
                OnlineRangeSum online = new OnlineRangeSum(values);
                rangeChecks += checkAllOnlineRanges(
                        online, expected);

                // Update each index to 2, one by one.
                for (int index = 0; index < n; index++) {
                    online.set(index, 2);
                    expected[index] = 2;
                    rangeChecks += checkAllOnlineRanges(
                            online, expected);
                }

                if (!Arrays.equals(values, original)) {
                    throw new AssertionError(
                            "input array was mutated");
                }
                arrays++;
            }
        }

        if (arrays != 364 || rangeChecks != 26655) {
            throw new AssertionError(
                    "online exhaustive count mismatch");
        }
        return new int[] {arrays, rangeChecks};
    }

    private static int[] verifyOfflineExhaustive() {
        int arrays = 0;
        int rangeChecks = 0;

        for (int n = 0; n <= 6; n++) {
            int cases = 1;
            for (int i = 0; i < n; i++) {
                cases *= 3;
            }

            for (int code = 0; code < cases; code++) {
                int[] values = new int[n];
                int value = code;
                for (int i = 0; i < n; i++) {
                    values[i] = value % 3 - 1;
                    value /= 3;
                }

                List<RangeQuery> queries = new ArrayList<>();
                for (int left = 0; left < n; left++) {
                    for (int right = left;
                            right < n; right++) {
                        queries.add(
                                new RangeQuery(left, right));
                    }
                }

                int[] original = values.clone();
                RangeQuery[] batch =
                        queries.toArray(new RangeQuery[0]);
                int[] answers = offlineDistinctCounts(
                        values, batch);

                if (answers.length != batch.length) {
                    throw new AssertionError(
                            "answer count mismatch");
                }

                for (int i = 0; i < batch.length; i++) {
                    RangeQuery query = batch[i];
                    int expected = naiveDistinct(
                            values, query.left(), query.right());
                    if (answers[i] != expected) {
                        throw new AssertionError(
                                "offline distinct mismatch");
                    }
                    rangeChecks++;
                }

                if (!Arrays.equals(values, original)) {
                    throw new AssertionError(
                            "offline input was mutated");
                }
                arrays++;
            }
        }

        if (arrays != 1093 || rangeChecks != 19956) {
            throw new AssertionError(
                    "offline exhaustive count mismatch");
        }
        return new int[] {arrays, rangeChecks};
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 1, 3, 2, 1};
        OnlineRangeSum online = new OnlineRangeSum(input);

        System.out.println(
                "online initial [0,5] = " + online.sum(0, 5));
        online.set(2, 5);
        System.out.println(
                "online after index2=5 [1,3] = "
                + online.sum(1, 3));
        online.set(0, 4);
        System.out.println(
                "online after index0=4 [0,2] = "
                + online.sum(0, 2));
        System.out.println(
                "online final [0,5] = " + online.sum(0, 5));
        System.out.println(
                "online final [4,5] = " + online.sum(4, 5));
        System.out.println(
                "input unchanged = "
                + Arrays.equals(input,
                        new int[] {1, 2, 1, 3, 2, 1}));

        RangeQuery[] batch = {
                new RangeQuery(3, 5),
                new RangeQuery(0, 2),
                new RangeQuery(0, 5),
                new RangeQuery(2, 2),
                new RangeQuery(1, 4)
        };
        System.out.println(
                "offline answers (original query order) = "
                + Arrays.toString(
                        offlineDistinctCounts(input, batch)));

        System.out.println(
                "offline no queries on empty = "
                + Arrays.toString(offlineDistinctCounts(
                        new int[0], new RangeQuery[0])));

        OnlineRangeSum wide = new OnlineRangeSum(
                new int[] {
                    Integer.MAX_VALUE,
                    Integer.MAX_VALUE,
                    Integer.MIN_VALUE
                });
        System.out.println(
                "wide long sum [0,1] = "
                + wide.sum(0, 1));
        System.out.println(
                "wide long sum [0,2] = "
                + wide.sum(0, 2));

        try {
            offlineDistinctCounts(input,
                    new RangeQuery[] {
                        new RangeQuery(4, 6)
                    });
        } catch (IllegalArgumentException error) {
            System.out.println("invalid offline query: "
                    + error.getMessage());
        }

        try {
            online.set(6, 1);
        } catch (IllegalArgumentException error) {
            System.out.println("invalid online index: "
                    + error.getMessage());
        }

        int[] offlineTest = verifyOfflineExhaustive();
        int[] onlineTest = verifyOnlineExhaustive();
        System.out.println(
                "exhaustive offline arrays = "
                + offlineTest[0]);
        System.out.println(
                "exhaustive offline queries = "
                + offlineTest[1]);
        System.out.println(
                "exhaustive online arrays = "
                + onlineTest[0]);
        System.out.println(
                "exhaustive online sum checks = "
                + onlineTest[1]);
        System.out.println("all checks passed = true");
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac QueryChoiceDemo.java
java QueryChoiceDemo
~~~

**Stdout dự kiến chính xác từ ví dụ và phép đếm exhaustive:**

~~~text
online initial [0,5] = 10
online after index2=5 [1,3] = 10
online after index0=4 [0,2] = 11
online final [0,5] = 17
online final [4,5] = 3
input unchanged = true
offline answers (original query order) = [3, 2, 3, 1, 3]
offline no queries on empty = []
wide long sum [0,1] = 4294967294
wide long sum [0,2] = 2147483646
invalid offline query: range out of bounds
invalid online index: index out of bounds
exhaustive offline arrays = 1093
exhaustive offline queries = 19956
exhaustive online arrays = 364
exhaustive online sum checks = 26655
all checks passed = true
~~~

### Ý nghĩa từng phần của stdout

- Các truy vấn SUM phản ánh **trạng thái sau đúng những cập nhật SET đã xảy ra**, không được reorder.
- `input unchanged=true` xác nhận `OnlineRangeSum` sao chép mảng khởi tạo.
- Đáp án offline `[3,2,3,1,3]` khớp **thứ tự query gốc**, dù nội bộ sort theo R.
- Mảng rỗng với **0 query** là hợp lệ; không cố tạo một đoạn có đầu phải âm.
- Tổng của hai `Integer.MAX_VALUE` là 4.294.967.294, vượt `int` nhưng nằm trong `long`.
- Các truy vấn sai cận bị từ chối thay vì ngầm sửa khoảng.
- Bộ exhaustive kiểm tra hai phương án bằng oracle độc lập, không chỉ tự so một kết quả do cùng thuật toán tính ra.

### Giới hạn của demo

`OnlineRangeSum` **không trả số distinct**; nó trả **tổng** với update online. `offlineDistinctCounts` **không hỗ trợ update**; nó đếm distinct của mảng snapshot ban đầu. Hai API minh họa **hai mô hình và hai cách tổ chức truy vấn**, không phải hai đáp án thay thế cho cùng một workload.

Đối với số nguyên `int` và kích thước mảng Java thực tế, tổng các phần tử được tính bằng `long` để tránh overflow 32-bit. Với miền số rộng hơn hoặc phép tích lũy có thể vượt `long`, cần cân nhắc `BigInteger` hoặc kiểm tràn theo yêu cầu dữ liệu.

## 16. Kiểm thử độc lập: không dùng lại thuật toán đang kiểm

### Offline: vét cạn bằng HashSet

Tạo tất cả mảng độ dài n=0..6 với mỗi phần tử thuộc `{−1,0,1}`. Số mảng tổng cộng:

~~~text
3^0 + 3^1 + 3^2 + 3^3
+ 3^4 + 3^5 + 3^6
= 1093
~~~

Với mỗi mảng độ dài n, có `n(n+1)/2` đoạn đóng `[L,R]`. Số lần đối chiếu tổng cộng:

~~~text
n=0:   1*0  =     0
n=1:   3*1  =     3
n=2:   9*3  =    27
n=3:  27*6  =   162
n=4:  81*10 =   810
n=5: 243*15 =  3645
n=6: 729*21 = 15309

Total = 19956
~~~

Oracle cho mỗi đoạn **duyệt trực tiếp các phần tử**, thêm vào `HashSet`, rồi so kích thước. Oracle này không sử dụng `lastSeen`, không sắp xếp queries theo R và không cần Fenwick; nhờ vậy có thể phát hiện lỗi thuật toán offline.

### Online: cộng trực tiếp sau từng SET

Tạo tất cả mảng có n=0..5, giá trị cũng trong `{−1,0,1}`:

~~~text
Total arrays = 3^0+...+3^5 = 364
~~~

Với mỗi mảng:

1. Xây Fenwick từ mảng gốc.
2. Kiểm mọi đoạn `[L,R]` bằng cách cộng trực tiếp từ L tới R.
3. Lần lượt SET từng vị trí i thành 2.
4. Sau mỗi SET, kiểm **lại tất cả các đoạn** bằng cộng trực tiếp.

Số phép kiểm được xác định:

~~~text
SUM_{n=0..5}
    (3^n) * (n+1) * n*(n+1)/2
= 26655
~~~

Công thức có `(n+1)` đợt kiểm cho mỗi mảng độ dài n: một đợt trước update và n đợt sau từng SET.

### Kiểm các trường hợp biên

- Mảng n=0, batch q=0 phải trả `[]`.
- Query `[i,i]` phải trả 1 distinct khi i hợp lệ.
- Mảng toàn giá trị giống nhau có distinct=1 cho mọi đoạn không rỗng.
- Mảng toàn giá trị khác nhau có distinct=R−L+1.
- Các giá trị âm, 0 và cực trị int không làm hỏng HashMap lastSeen.
- Query có R=n, L<0, L>R đều phải bị từ chối.
- UPDATE index ngoài `[0,n−1]` bị từ chối.
- Trùng query phải cho đáp án giống nhau ở những ID khác nhau.
- Có thể thêm một bộ query bị đảo thứ tự để chắc chắn code trả lời theo **ID gốc**, không theo R đã sort.
- Sau mỗi online update, mảng gốc của người gọi vẫn phải không đổi nếu API đã hứa copy.

### Test dùng giá trị ngẫu nhiên không đủ để chứng minh đúng

Các test random trên input lớn rất hữu ích cho hiệu năng và lỗi hiếm, nhưng với n nhỏ, **exhaustive + oracle khác ý tưởng** cho khả năng kiểm độc lập rõ ràng hơn. Chứng minh bất biến vẫn cần thiết để khẳng định đúng cho mọi n.

## 17. So sánh các lựa chọn cho các dạng truy vấn phổ biến

| Workload | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| Range sum, mảng tĩnh | Prefix sum online | O(n) build, O(1) query |
| Range sum + point SET | Fenwick/Segment Tree online | O(log n) mỗi thao tác |
| Range min/max tĩnh | Sparse table cho RMQ phù hợp | Preprocess trước, query nhanh; tùy phép toán |
| Range min/max + update | Segment Tree online | Hỗ trợ cập nhật và gộp |
| Distinct count tĩnh, biết cả batch | Offline sweep theo R + BIT | O((n+q) log(n+q)) gần đúng |
| Distinct count tĩnh, query đến dần | Persistent structure hoặc cách online khác | Không được reorder truy vấn tương lai |
| Statistic có add/remove O(1) | Mo's offline cho batch tĩnh | Sắp xếp giảm di chuyển cửa sổ |
| Đếm phần tử >K trên đoạn | Offline sort theo K + Fenwick | Dùng trạng thái đánh dấu theo ngưỡng |
| Query liên thông sau chỉ xóa cạnh | Offline đảo thời gian + DSU | Đổi xóa thành gộp |
| Dynamic connectivity có thêm/xóa | Offline segment tree thời gian + rollback DSU, nếu biết batch | Giữ interval hiệu lực của cạnh |
| Query phụ thuộc `lastAnswer` | Online hoặc thuật toán giữ được thứ tự | Không biết query sau trước khi trả lời |
| Q rất ít, N nhỏ | Brute force có thể tốt hơn | Tránh overhead không cần thiết |

### Online distinct với mảng tĩnh có khả thi không?

Có những cấu trúc dữ liệu tĩnh dùng **persistent segment tree**, wavelet-like structures hoặc các tiền xử lý chuyên biệt để trả lời distinct query **không cần biết trước query**. Một cách là xây phiên bản persistent theo các prefix với đánh dấu ở lần xuất hiện cuối rồi truy vấn trên phiên bản R.

Điểm khác biệt:

- Offline sweep chỉ giữ **một trạng thái hiện tại** và sort truy vấn để khớp trạng thái R.
- Persistent versions giữ nhiều **ảnh chụp lịch sử**, cho phép query R bất kỳ khi nó đến, đổi lại thêm bộ nhớ và chi phí xây dựng.

Việc cần online **không có nghĩa** mọi phép đếm distinct phải O(n) mỗi query; nó chỉ nghĩa ta phải chọn cấu trúc hỗ trợ trả lời mà không đợi toàn bộ batch.

## 18. Độ trễ, bộ nhớ và tính đúng khi có cập nhật

### Tổng thời gian khác độ trễ mỗi câu trả lời

Một thuật toán offline có thể có **tổng runtime tốt**, nhưng phải chờ nhận q query rồi mới xử lý; người dùng tương tác có thể thấy độ trễ không chấp nhận được.

Ngược lại, một API online với Fenwick trả từng query trong O(log n), nhưng tổng thời gian cho q thao tác vẫn O(q log n). Khi so phương án sản phẩm, cần đo cả:

- **Latency** một truy vấn cần bao nhiêu lâu để có câu trả lời.
- **Throughput** xử lý được bao nhiêu truy vấn mỗi giây.
- **Batch waiting time** tích lũy trước khi chạy offline.
- **Peak memory** để giữ queries, IDs, answers và cấu trúc.
- **Update visibility** truy vấn phải nhìn thấy những thay đổi nào.
- **Reproducibility** khi sort có tie và dữ liệu nhận dạng query.

### Một chuỗi update và query không thể sort tùy ý

Xét:

~~~text
a = [5, 5]
Q1 distinct(0,1) = 1
SET(1,7)
Q2 distinct(0,1) = 2
~~~

Nếu sort `Q1,Q2` theo cùng R=1 rồi chạy trên **một snapshot duy nhất**, hai đáp án sẽ giống nhau, sai yêu cầu.

Thuật toán offline có update phải biểu diễn thêm thời điểm, ví dụ mỗi query có `(L,R,T)` với T là số update trước nó. Mo's with modifications hoặc các cấu trúc timeline/rollback xử lý ba chiều này; đó là bài nâng cao khác.

### Các phép cập nhật có giao hoán không?

Hai phép `ADD` vào những vị trí khác nhau có thể giao hoán về trạng thái cuối, nhưng **không nhất thiết được đảo qua một truy vấn SUM ở giữa**. Bảo toàn trạng thái cuối không đủ để bảo toàn câu trả lời trung gian.

Tương tự, nếu query có side effect như tiêu thụ một item, đặt giữ chỗ hoặc làm thay đổi bộ đếm, việc sắp xếp lại chỉ hợp lệ khi có chứng minh tính giao hoán/độc lập tương ứng.

### Bộ nhớ với batch rất lớn

Offline distinct lưu q query và q answers, thường O(q) ngoài mảng/bit. Nếu q vượt giới hạn RAM, có thể cân nhắc phân batch, sort bên ngoài (external sorting) hoặc giải pháp online/persistent; nhưng cần phân tích lại tổng chi phí I/O và điều kiện đúng. Không coi việc “đủ thời gian CPU” là đủ nếu bộ nhớ không đáp ứng.

## 19. Lỗi phổ biến và cách nhận biết

| Sai lầm | Hậu quả | Khắc phục |
| --- | --- | --- |
| Hiểu “offline” là không kết nối mạng | Chọn sai mô hình | Dựa vào việc biết trước batch |
| Trả lời theo thứ tự đã sort | Output sai | Lưu ID và ghi `answer[id]` |
| Sort luôn mảng gốc | Thay câu hỏi trên các đoạn | Chỉ sort query/sự kiện |
| Reorder thao tác UPDATE và QUERY tùy ý | Sai trạng thái thời điểm | Giữ thời gian hoặc dùng thuật toán có time |
| Coi toàn bộ dòng input mã hóa là offline | Query có thể phụ thuộc lastAnswer | Kiểm tính thích nghi |
| Dùng Fenwick SUM để trả distinct | Sai phép toán | Chọn invariant phù hợp |
| Dùng offline distinct snapshot với update xen giữa | Đáp án cũ | Cần thuật toán hỗ trợ modifications |
| LastSeen không xóa vị trí cũ | Đếm trùng một giá trị | `add(old,-1)` trước `add(R,+1)` |
| Nhầm old=0 với chưa thấy | Sai khi lần xuất hiện cũ ở index0 | Dùng null/sentinel −1 rõ |
| Dùng `prefix(R)-prefix(L)` cho đoạn đóng | Bỏ a[R] | `prefix(R+1)-prefix(L)` |
| Nhầm 0-based với 1-based Fenwick | Off-by-one | Quy đổi API đúng |
| SET nhưng chỉ `add(newValue)` | Cộng chồng giá trị | Cập nhật `new-old` |
| Tính delta int trước khi ép long | Tràn số 32-bit | Ép `(long)` trước phép trừ |
| Query invalid mà tự cắt biên | Giấu lỗi input | Validate và từ chối |
| Mảng rỗng mà gọi sum(0,0) | Index ngoài cận | Zero-query hợp lệ, range không |
| Sort query nhưng dùng chỉ số sort làm ID | Ghi đáp án sai | Giữ originalIndex từ đầu |
| Không xét tie events ở sweep | Sai biên bằng tọa độ | Quy định thứ tự event/query |
| Nghĩ offline luôn nhanh hơn online | Overhead sort/memory | So cùng workload và constraint |
| Nghĩ một phép sweep xử lý mọi statistic | Không có invariant phù hợp | Cân nhắc Mo/persistent/segment tree |
| Giữ HashMap lastSeen sai khóa/kiểu | Mất phân biệt giá trị | Dùng int value nguyên bản/coordinate compression |
| Coi expected O(1) của HashMap là worst-case | Phân tích quá mạnh | Nêu giả định hashing |
| Test chỉ vài query không trùng | Bỏ lỗi last occurrence | Test duplicate, singleton, exhaustive |
| Kiểm bằng oracle dùng lại BIT | Lỗi chung không bị bắt | Dùng HashSet/cộng trực tiếp |
| Chỉ so runtime O notation và bỏ latency | Sai lựa chọn hệ thống | Đo cả thời gian chờ batch |
| Dùng Mo's tĩnh với update | State thiếu thời gian | Mo with modifications hoặc thiết kế khác |

### Câu hỏi phản biện

Đối với bất kỳ ý tưởng offline nào, thử hỏi: “Nếu đổi thứ tự tính toán của hai truy vấn liên tiếp, kết quả của từng truy vấn **vẫn y nguyên** chứ?” Nếu câu trả lời không chắc chắn, cần xác định thêm dependency, snapshot, thời gian hoặc hiệu ứng phụ trước khi sort.

## 20. Bài tập và tổng kết

### Bài tập từ cơ bản đến nâng cao

1. Phân biệt online và offline theo thời điểm biết query, không theo kết nối Internet.
2. Cho một hệ thống cần trả lời ngay mỗi câu hỏi, giải thích vì sao batch sort có thể không phù hợp.
3. Đặt ví dụ truy vấn sau phụ thuộc `lastAnswer`.
4. Viết checklist xét mảng tĩnh hay có cập nhật.
5. Tính prefix sums của `[1,2,1,3,2,1]`.
6. Dùng prefix trả tổng [1,4] khi không có update.
7. Giải thích vì sao SET phá nhiều prefix sums.
8. Viết `lowbit(i)=i&-i` cho i=1..8.
9. Tự vẽ những đoạn mà Fenwick bit[1],bit[2],bit[4] lưu.
10. Cài Fenwick `add` và `prefixExclusive`.
11. Giải thích công thức `sum(L,R)=prefix(R+1)-prefix(L)`.
12. Cài SET(index,value) bằng delta, không nhầm với ADD.
13. Cho giá trị `Integer.MAX_VALUE`, giải thích tại sao tổng cần long.
14. Định nghĩa distinct(L,R) cho đoạn đóng.
15. Tính distinct của mọi query trong ví dụ sáu phần tử.
16. Sort các query theo đầu phải R và ghi ID ban đầu.
17. Mô phỏng lastSeen sau mỗi R từ 0 tới 5.
18. Ghi các active positions sau R=2,4,5.
19. Chứng minh giá trị a[R] chỉ có một dấu đại diện cuối cùng.
20. Chứng minh tổng dấu trong [L,R] bằng số distinct.
21. Cài HashMap lastSeen dùng khóa int âm và cực trị.
22. Tạo query [0,0] và [n−1,n−1] rồi kiểm đáp án.
23. Viết input validation từ chối L>R, R≥n, L<0.
24. Viết chương trình in answers theo ID gốc sau khi sort.
25. Chứng minh complexity của offline sweep gồm cả sort queries.
26. Nếu q=1 và n nhỏ, so cách HashSet trực tiếp với offline sort.
27. Nếu query SUM trên mảng tĩnh, chứng minh prefix sum online O(1)/query.
28. Nếu có point SET, chọn giữa Fenwick và Segment Tree, giải thích.
29. Nêu một workload phù hợp với Mo's algorithm.
30. Trình bày bốn thao tác di chuyển cửa sổ `[curL,curR]` của Mo's.
31. Giải thích vì sao Mo's cơ bản không xử lý update thời gian.
32. Tạo ví dụ `Q1;SET;Q2` làm cả hai query cùng R nhưng khác đáp án.
33. Nêu một bài sweep sort theo ngưỡng K thay vì R.
34. Đề xuất offline đảo thời gian khi chỉ xóa cạnh và hỏi liên thông.
35. Giải thích cần thêm gì khi vừa thêm vừa xóa cạnh offline.
36. So bản snapshot với persistent versions khi cần distinct online.
37. Tự cài oracle offline distinct bằng HashSet.
38. Duyệt các mảng dài n≤4 với alphabet {−1,0,1}, kiểm mọi query.
39. Duyệt đầy đủ n≤6 và xác nhận 1.093 mảng, 19.956 query.
40. Duyệt n≤5 và các SET xác định, kiểm 26.655 tổng đoạn online.
41. Mô tả vì sao HashMap expected O(1) không phải cận worst-case tuyệt đối.
42. Thay HashMap bằng coordinate compression + mảng lastSeen.
43. Thiết kế nghiệm online query distinct bằng phiên bản persistent theo prefix.
44. Thiết kế test đảm bảo query array và input array không bị sửa.
45. So throughput, latency và peak memory trong hệ thống streaming vs batch.
46. Giải thích tại sao không được kết luận “offline luôn tốt hơn online” chỉ từ một ví dụ.
47. Xây bảng quyết định thuật toán cho một bộ dữ liệu có n, q, cập nhật và SLA cụ thể.
48. Tự chứng minh một ý tưởng sort/reorder mới bảo toàn ngữ nghĩa trước khi triển khai.

### Checklist cuối

- Đã biết **mọi query từ trước** hay chưa?
- Query mới có phụ thuộc **đáp án cũ** không?
- Các phép update có làm đổi ý nghĩa từng query theo **thời gian** không?
- Mỗi query có cần được trả **ngay** hay có thể chờ xử lý batch?
- Nếu offline, đã gắn **original ID** và xuất theo ID chưa?
- Nếu sweep, invariant có chứng minh đúng cho mọi trạng thái quét không?
- Nếu query là đoạn đóng, đã xử lý **R+1** đúng ở Fenwick?
- Có kiểm toàn bộ input, đoạn rỗng/sai, giá trị âm, trùng và giá trị lớn?
- Có tính chi phí preprocessing, sort, RAM, latency, updates và readback trong lựa chọn kỹ thuật?
- Có test độc lập bằng brute force trên các instance nhỏ?
- Có phân biệt giải đúng snapshot tĩnh với xử lý chuỗi thao tác thay đổi theo thời gian?
- Có lựa chọn baseline đơn giản như prefix sum trước khi dùng kỹ thuật offline phức tạp?

**Kết luận:** xử lý **online** phù hợp khi các câu hỏi đến dần, cần phản hồi ngay hoặc truy vấn sau phụ thuộc đáp án trước; xử lý **offline** mạnh khi toàn bộ batch đã biết, có thể sắp xếp tính toán mà không thay ngữ nghĩa. Với tổng đoạn có cập nhật điểm, Fenwick online trả mỗi thao tác trong **O(log n)**. Với đếm distinct trên **mảng tĩnh**, sắp xếp query theo R, đánh dấu **lần xuất hiện cuối cùng** của mỗi giá trị và lấy tổng Fenwick cho đúng **O(q log q + (n+q) log n)** kỳ vọng, trả theo ID gốc. Quyết định đúng không dựa vào nhãn “nhanh hơn” chung chung mà dựa vào **độc lập truy vấn, trạng thái dữ liệu, ngân sách thời gian/bộ nhớ và phép chứng minh đúng của từng phương án**.
