# Quét sự kiện kết hợp nén tọa độ và cấu trúc truy vấn

Trong nhiều bài thuật toán, đầu vào chứa **hàng trăm nghìn điểm, đoạn, khoảng thời gian hoặc sự kiện**, đi kèm rất nhiều câu hỏi: có bao nhiêu điểm nằm trước một ngưỡng, có bao nhiêu điểm thuộc một hình chữ nhật, tại thời điểm t có bao nhiêu đối tượng đang hoạt động, hoặc tổng trọng số trong một vùng tọa độ là bao nhiêu. Nếu kiểm tra từng phần tử cho từng truy vấn, độ phức tạp thường là O(nq) và không đủ nhanh.

Một mẫu thiết kế rất mạnh là **quét sự kiện (event sweep / sweep line)** kết hợp **nén tọa độ (coordinate compression)** và **cấu trúc truy vấn (Fenwick Tree hoặc Segment Tree)**. Ta biến bài toán nhiều chiều hoặc nhiều thời điểm thành một trình tự sự kiện có thứ tự; trong lúc quét, duy trì đúng các đối tượng đã trở nên “có hiệu lực” bằng cấu trúc dữ liệu, rồi trả lời những truy vấn đúng tại thời điểm yêu cầu.

Bài **“Quét sự kiện kết hợp nén tọa độ và cấu trúc truy vấn”** thuộc nhóm **Truy vấn và ngoại tuyến** của Computer Science Algorithms. Nội dung đi từ bản chất offline, định nghĩa sự kiện và thứ tự ưu tiên khi tọa độ bằng nhau, nén trục truy vấn, cập nhật và tổng tiền tố với Fenwick, tới ví dụ đếm điểm thỏa x≤X và y≤Y, rồi mở rộng sang đếm điểm trong **hình chữ nhật đóng** bằng bốn sự kiện inclusion–exclusion. Ví dụ Java 17+ có xử lý đầy đủ tọa độ âm, trùng lặp, Long.MIN_VALUE/Long.MAX_VALUE và truy vấn rỗng, kèm kiểm chứng độc lập trên 7.381 dãy điểm vét cạn, 1.500 tập có seed và bộ dữ liệu 20.000 điểm.

## 1. Bối cảnh: truy vấn và xử lý ngoại tuyến

Giả sử ta biết trước tập điểm và danh sách q truy vấn. **Offline** nghĩa là được phép sắp xếp lại thứ tự xử lý để tăng tốc, miễn là trả kết quả về **đúng thứ tự truy vấn gốc**. Khác với truy vấn online, người dùng không đòi phải có đáp án tức thì trước khi đưa câu hỏi tiếp theo.

Ví dụ điểm:

~~~text
(-2,5), (0,-1), (0,5), (0,5), (3,2), (3,9)
~~~

Hỏi có bao nhiêu điểm với x≤0 và y≤5. Ta nhận **4** vì gồm điểm (-2,5), (0,-1) và **hai bản sao** (0,5). Nếu có 100.000 điểm và 100.000 câu hỏi, một vòng lặp quét hết điểm cho từng câu hỏi gây khoảng 10^10 phép kiểm tra.

Vì các truy vấn được biết trước, ta có thể sắp điểm và truy vấn theo x rồi tiến dần từ trái sang phải, **không xử lý lại các điểm cũ**. Tại mỗi câu hỏi x=X, chỉ những điểm có x phù hợp đã được thêm vào cấu trúc theo y.

## 2. Ba thành phần và vai trò riêng

Một lời giải sweep + compression + query structure thường có ba phần:

1. **Quét sự kiện:** chọn một trục thời gian/tọa độ để sắp tất cả sự kiện. Ví dụ x tăng dần.
2. **Nén tọa độ:** biến các tọa độ y rất lớn, âm hoặc thưa thành các chỉ số 1..m bảo toàn thứ tự.
3. **Cấu trúc truy vấn:** hỗ trợ cập nhật khi gặp điểm và truy vấn tổng/count trên một đoạn hoặc tiền tố của các chỉ số nén.

~~~text
Tọa độ x: quyết định điểm nào đã có hiệu lực.
Tọa độ y: quyết định điểm nào thỏa điều kiện thứ hai.
Fenwick: giữ số điểm đã có hiệu lực ở từng y nén.
Query: đọc số điểm có y <= Y trong tập hiện có.
~~~

Việc **tách hai chiều** rất quan trọng: dùng thứ tự sự kiện giải quyết một bất đẳng thức x; dùng Fenwick giải quyết bất đẳng thức y. Nhờ đó ta tránh dựng một bảng hai chiều theo toàn bộ miền tọa độ.

## 3. Bài toán mẫu: đếm dominance hai chiều

Cho n điểm P_i=(x_i,y_i). Mỗi truy vấn Q=(X,Y) yêu cầu:

~~~text
answer(X,Y)
 = số chỉ số i sao cho:
       x_i <= X
   và  y_i <= Y.
~~~

Đây là bài **2D dominance counting**. Dấu `<=` nghĩa là **bao gồm cả biên**. Nếu nhiều phần tử có tọa độ giống nhau, mỗi phần tử trong input vẫn đóng góp một lần vào số đếm; không được dùng Set để loại bản sao nếu bài hỏi số điểm.

Bài có thể thay số đếm bằng tổng trọng số w_i, miễn đổi thao tác cập nhật Fenwick từ +1 thành +w_i và chọn kiểu số đủ lớn. Nhưng chương trình Java trước mắt là **đếm điểm không trọng số** để giải thích cơ chế và chứng minh rõ ràng.

## 4. Lời giải trực tiếp O(nq)

Cách đơn giản nhất:

~~~text
for mỗi query (X,Y):
    count = 0
    for mỗi point (x,y):
        if x<=X and y<=Y:
            count++
    answer[query.id] = count
~~~

Nếu có n điểm và q truy vấn, thời gian O(nq), bộ nhớ bổ sung O(q). Cách này rất dễ hiểu và vẫn tốt khi n,q nhỏ; vì vậy nó cũng là **oracle độc lập** để kiểm thử lời giải tối ưu.

Mục tiêu của kỹ thuật sweep không phải thay đổi nghĩa của answer mà là **chia sẻ công việc giữa các truy vấn**. Khi X tăng từ câu hỏi này sang câu khác, không cần xóa các điểm có x nhỏ hơn: các điểm thỏa điều kiện x≤X trước đó vẫn thỏa với X lớn hơn.

## 5. Thiết kế hai loại sự kiện

Từ mỗi điểm (x_i,y_i), tạo sự kiện:

~~~text
POINT at x=x_i:
    Fenwick.add(compressed(y_i), +1).
~~~

Từ mỗi truy vấn (X,Y,id), tạo sự kiện:

~~~text
QUERY at x=X:
    answer[id] = Fenwick.prefixCount(y <= Y).
~~~

Sắp tất cả sự kiện theo x tăng. Sau khi xử lý các điểm có x≤X, Fenwick chứa chính xác những điểm mà điều kiện theo x đã thỏa. Truy vấn y≤Y chỉ cần đọc **tổng tiền tố**.

Đối với bài hỏi x<X hoặc hình chữ nhật đóng, cần cẩn trọng ở trường hợp x của điểm bằng x của query. Bản code tổng quát hóa thành ba **phase** riêng thay vì dùng thủ thuật trừ một đơn vị x.

## 6. Thứ tự hòa khi x bằng nhau

Đây là một trong các lỗi thường gặp nhất của sweep line: sắp đúng theo x nhưng **không định nghĩa thứ tự các sự kiện cùng x**.

Bản Java dùng phase:

~~~text
phase 0: QUERY với điều kiện x < X.
phase 1: POINT tại x = X.
phase 2: QUERY với điều kiện x <= X.
~~~

Thứ tự `(x tăng, phase tăng)` nghĩa là:

~~~text
Ở đúng tọa độ X:
    các query x<X chạy trước,
    sau đó thêm toàn bộ POINT tại X,
    cuối cùng các query x<=X chạy sau.
~~~

Như vậy khi gặp truy vấn đóng `x≤X`, **mọi điểm trên biên x=X đều đã được thêm**. Khi gặp truy vấn mở `x<X`, **không có điểm x=X nào đã được thêm**.

Nếu chỉ sort theo x và để thứ tự giữa các phần tử có x bằng nhau tùy ý, kết quả có thể phụ thuộc thứ tự sort và sai đúng ở các trường hợp biên.

## 7. Ví dụ hòa sự kiện có nhiều điểm trùng x

Xét ba điểm:

~~~text
(0,5), (0,5), (0,-1).
~~~

Câu hỏi `x≤0, y≤5` có đáp án **3**. Với phase2, sự kiện query xuất hiện sau cả ba POINT tại x=0, nên Fenwick đã cộng đủ ba lần.

Câu hỏi `x<0, y≤5` có đáp án **0**, vì phase0 xuất hiện trước các POINT cùng x=0. Một query `x≤0, y<5` lại có đáp án **1**, chỉ gồm (0,-1); trường hợp thứ ba do **quy tắc lowerBound của y** quyết định.

Kỹ thuật phase giải quyết dấu `<`/`≤` trên trục quét; binary search cho nén tọa độ giải quyết dấu `<`/`≤` trên trục cấu trúc dữ liệu.

## 8. Nén tọa độ y vì sao cần thiết?

Tọa độ y có thể là -10^12, 0, +10^12 hoặc Long.MAX_VALUE. Nếu Fenwick cần mảng đánh chỉ số tới giá trị y, không thể cấp phát; với tọa độ âm còn không thể dùng trực tiếp làm chỉ số.

Lấy các y cần **cập nhật** (ở đây chỉ y của các điểm), sắp tăng và loại trùng:

~~~text
Point y: [5, -1, 5, 5, 2, 9].

Sorted unique:
[-1, 2, 5, 9].

Fenwick 1-based index:
-1 -> 1
 2 -> 2
 5 -> 3
 9 -> 4
~~~

Nén chỉ giữ **thứ tự và quan hệ bằng nhau**, không giữ khoảng cách số học giữa hai tọa độ. Với count và tổng tiền tố theo thứ tự, đó chính là thông tin ta cần.

## 9. Khi truy vấn y không xuất hiện trong dữ liệu

Không phải mọi ngưỡng Y đều bằng một tọa độ điểm. Ví dụ tập y nén `[-1,2,5,9]`, hỏi y≤4 thì phải lấy hai tọa độ -1 và 2, dù **4 không nằm trong mảng**.

Định nghĩa:

~~~text
lowerBound(sorted,Y)
 = số phần tử phân biệt có tọa độ < Y.

upperBound(sorted,Y)
 = số phần tử phân biệt có tọa độ <= Y.
~~~

Đối với `y<Y`, Fenwick.prefix(lowerBound(Y)). Đối với `y≤Y`, Fenwick.prefix(upperBound(Y)).

Các hàm trả số lượng **tọa độ phân biệt** nằm trước/vượt mốc, tương ứng độ dài tiền tố trong mảng nén. Fenwick lưu số lượng **điểm thực** ở mỗi chỉ số, nên giá trị prefix cộng đủ bội số của các điểm trùng y.

Không cần thêm mọi Y của query vào mảng nén nếu chỉ update tại y điểm; binary search trên tập y update đã đủ để xác định số vị trí cần lấy.

## 10. Fenwick Tree (Binary Indexed Tree)

Fenwick duy trì mảng tần suất `freq[1..m]` với hai thao tác:

~~~text
add(i, delta):
    freq[i] += delta.

prefix(k):
    trả sum(freq[1..k]).
    prefix(0)=0.
~~~

Fenwick tổ chức các khối tổng theo bit thấp nhất `i & -i`:

~~~java
for (int i=oneBased; i<tree.length; i+=i&-i) {
    tree[i]+=delta;
}

for (int i=k; i>0; i-=i&-i) {
    result+=tree[i];
}
~~~

Mỗi thao tác thời gian O(log m), bộ nhớ O(m). Việc `oneBased` phải ít nhất 1: gọi add(0,...) gây vòng lặp không tiến vì `0 & -0 = 0`. Với m=0, không có điểm để add, nhưng `prefix(0)` vẫn hợp lệ và trả 0.

Trong Java, mỗi nút Fenwick là `long`, tránh tràn int khi n hoặc tổng trọng số lớn; khi n là kích thước List int thì count không vượt n, nhưng kiểu long giúp mở rộng.

## 11. Chuyển từ y thật sang chỉ số Fenwick

Lúc thêm điểm có y đã nằm trong mảng nén:

~~~text
index = lowerBound(ys, point.y) + 1.
Fenwick.add(index, 1).
~~~

Ví dụ point.y=5, mảng y `[-1,2,5,9]` thì lowerBound=2, chỉ số 1-based là 3. Hai điểm khác nhau có y=5 đều được add(3,+1), nên Fenwick.freq[3] có thể bằng 2 hoặc hơn.

Khi query y≤5:

~~~text
prefixLength = upperBound(ys, 5) = 3.
answer = Fenwick.prefix(3).
~~~

Khi query y<5:

~~~text
prefixLength = lowerBound(ys, 5) = 2.
answer = Fenwick.prefix(2).
~~~

Đừng gán `lowerBound` trực tiếp làm update index 1-based, cũng đừng cộng +1 vào prefixLength một cách máy móc: đây là hai hệ chỉ số có mục đích khác nhau.

## 12. Giả mã thuật toán dominance

~~~text
countDominance(points, queries):
    ys = sort(unique(all point.y)).
    fenwick = Fenwick(ys.length).

    events = []
    for p in points:
        add Event(p.x, phase=1, point=p).

    for (X,Y,id) in queries:
        add Event(X, phase=2, query=(Y,id)).

    sort events by (x asc, phase asc).
    ans[q] = 0.

    for event in events:
        if POINT:
            i=lowerBound(ys, event.y)+1.
            fenwick.add(i,+1).
        else:
            k=upperBound(ys, event.Y).
            ans[id]=fenwick.prefix(k).

    return ans in original query order.
~~~

Sắp lại query không làm thay đổi thứ tự kết quả vì mỗi query mang một **id** của vị trí gốc. Sự khác biệt giữa offline và online nằm ở **thứ tự xử lý nội bộ**, không phải ở thứ tự trả kết quả.

## 13. Chạy tay với sáu điểm mẫu

Cho n=6:

~~~text
P0=(-2,5)
P1=(0,-1)
P2=(0,5)
P3=(0,5)
P4=(3,2)
P5=(3,9)
~~~

Các tọa độ y phân biệt `[-1,2,5,9]`.

| Sau khi quét x | Tập điểm đã có hiệu lực | Prefix y≤5 |
| --- | --- | ---: |
| x<-2 | Rỗng | 0 |
| x=-2 sau POINT | (-2,5) | 1 |
| x=0 sau POINT | thêm (0,-1),(0,5),(0,5) | 4 |
| x=3 sau POINT | thêm (3,2),(3,9) | 5 |

Tại x=3, có tất cả 6 điểm trong Fenwick nhưng query y≤5 chỉ đếm 5 vì điểm (3,9) nằm ngoài tiền tố. Câu hỏi x≤0,y≤4 chỉ trả 1 vì trong các điểm có x≤0, chỉ (0,-1) có y≤4.

Kết quả theo thứ tự các query mẫu:

~~~text
(X,Y)=(-3,100) -> 0.
(X,Y)=(-2,5)   -> 1.
(X,Y)=(0,5)    -> 4.
(X,Y)=(0,4)    -> 1.
(X,Y)=(3,5)    -> 5.
(X,Y)=(3,9)    -> 6.
(X,Y)=(0,-2)   -> 0.
~~~

## 14. Mở rộng: đếm điểm trong hình chữ nhật đóng

Bài toán mạnh hơn: với mỗi hình chữ nhật trục song song:

~~~text
[x1,x2] x [y1,y2]
trong đó x1<=x2, y1<=y2.
~~~

Cần đếm số điểm (x,y) thỏa:

~~~text
x1 <= x <= x2
và
y1 <= y <= y2.
~~~

Ta không thể dùng một dominance query x≤X,y≤Y trực tiếp, nhưng có thể **cộng trừ bốn prefix**. Đây là inclusion–exclusion ở hai chiều.

Đặt H(A,B) = số điểm x≤A và y≤B. Biểu thức quen thuộc với tọa độ nguyên là:

~~~text
rectangleCount =
    H(x2,y2)
  - H(x1-1,y2)
  - H(x2,y1-1)
  + H(x1-1,y1-1).
~~~

Tuy nhiên cách viết x1-1, y1-1 có thể **tràn** nếu x1 hoặc y1 là Long.MIN_VALUE. Hơn nữa nếu tọa độ thực hoặc không rời rạc, khái niệm “trước x1 đúng một đơn vị” là không phù hợp.

## 15. Không trừ 1: dùng prefix đóng và prefix mở

Thay vì dùng x1-1, hãy định nghĩa bốn loại prefix theo dấu biên:

~~~text
F(<= X, <= Y).
F(<  X, <= Y).
F(<= X, <  Y).
F(<  X, <  Y).
~~~

Khi đó chính xác:

~~~text
count([x1,x2] x [y1,y2]) =
    F(x<=x2, y<=y2)
  - F(x< x1, y<=y2)
  - F(x<=x2, y< y1)
  + F(x< x1, y< y1).
~~~

Dùng `phase=0` cho truy vấn x<X và `phase=2` cho x≤X. Dùng `lowerBound` cho y<Y và `upperBound` cho y≤Y. Các tọa độ X,Y được giữ **nguyên gốc**, không tính X−1 hay Y−1.

Đây là một mẫu chuyển đổi rất quan trọng: **đổi phép trừ mốc thành kiểu bất đẳng thức**, vừa giữ đúng ngữ nghĩa open/closed, vừa tránh overflow ở miền cực trị.

## 16. Bốn sự kiện cho mỗi rectangle

Với hình chữ nhật r=(x1,y1,x2,y2) và id gốc, phát ra:

| Hệ số | Biên x | Biên y | Ý nghĩa |
| ---: | --- | --- | --- |
| +1 | x≤x2 | y≤y2 | Prefix phía trên/phải |
| -1 | x<x1 | y≤y2 | Loại miền bên trái |
| -1 | x≤x2 | y<y1 | Loại miền phía dưới |
| +1 | x<x1 | y<y1 | Bù giao đã trừ hai lần |

Mỗi probe mang `coefficient=+1/-1` và `answerIndex=id`. Khi quét tới probe, tính số điểm ở tiền tố y tương ứng rồi **cộng coefficient × giá trị** vào answer[id].

Do mỗi rectangle sinh bốn probe, số sự kiện O(n+4q), vẫn O(n+q) theo ký hiệu Big-O. Không cần xử lý x1/x2 riêng bằng hai lần quét hay nhân bốn số lượt sắp xếp; một danh sách sự kiện duy nhất đủ.

## 17. Ví dụ rectangle biên đóng

Với sáu điểm ở mục 13:

~~~text
Rectangle A:
    x in [-2,0], y in [5,5].
    Gồm (-2,5), (0,5), (0,5).
    count=3.

Rectangle B:
    x in [0,3], y in [-1,5].
    Gồm (0,-1), (0,5), (0,5), (3,2).
    count=4.

Rectangle C:
    x in [0,0], y in [5,5].
    Gồm hai bản sao (0,5).
    count=2.

Rectangle D:
    mọi long x/y.
    count=6.

Rectangle E:
    x in [1,2], y in [-100,100].
    count=0.
~~~

Điểm có x=x1 hoặc x=x2, y=y1 hoặc y=y2 đều phải được tính vì rectangle **đóng**. Nếu nhầm một phase hoặc một lowerBound/upperBound, những rectangle độ rộng/chiều cao bằng 0 thường lộ lỗi đầu tiên.

## 18. Chứng minh bất biến của sweep

Sắp sự kiện theo (x,phase), phase 0 trước 1 trước 2. Khi xử lý một sự kiện tại x=X:

- **Ở phase 0:** chưa thêm điểm có x=X, nhưng đã thêm tất cả điểm có x<X. Fenwick biểu diễn đúng tập cần cho prefix mở x<X.
- **Ở phase 1:** thêm mỗi điểm có x=X đúng một lần vào chỉ số y tương ứng.
- **Ở phase 2:** mọi điểm có x≤X đã được thêm, và chưa có điểm có x>X. Fenwick biểu diễn đúng tập cần cho prefix đóng x≤X.

Chứng minh quy nạp theo thứ tự sự kiện: ban đầu Fenwick rỗng và chưa có điểm ở bên trái. Chỉ các POINT làm thay đổi Fenwick; query không sửa trạng thái. Mỗi POINT được duyệt đúng một lần sau mọi sự kiện x nhỏ hơn và trước mọi sự kiện x lớn hơn, nên hai bất biến trên đúng tại từng phase.

Sau đó Fenwick.prefix(k) cộng chính xác những điểm đã có hiệu lực có y thuộc k tọa độ nén đầu tiên. Theo định nghĩa lowerBound/upperBound, k là đúng số chỉ số y thỏa dấu biên đã chọn. Vì vậy mỗi probe trả đúng **prefix hai chiều**.

## 19. Chứng minh inclusion–exclusion của rectangle

Cho một điểm p bất kỳ. Trong biểu thức bốn prefix:

~~~text
I[x<=x2 & y<=y2]
- I[x<x1  & y<=y2]
- I[x<=x2 & y<y1]
+ I[x<x1  & y<y1].
~~~

Trong đó I[điều kiện] bằng 1 nếu đúng, 0 nếu sai. Tách nhân:

~~~text
(I[x<=x2] - I[x<x1])
*
(I[y<=y2] - I[y<y1]).
~~~

Với x1≤x2, thừa số thứ nhất bằng 1 **khi và chỉ khi x1≤x≤x2**, ngược lại bằng 0. Thừa số thứ hai tương tự cho y1≤y≤y2. Tích bằng 1 đúng khi điểm thuộc rectangle đóng.

Cộng giá trị đó trên mọi điểm (kể cả các bản sao trùng tọa độ) thu đúng số điểm trong rectangle. Đây là chứng minh bằng **hàm chỉ báo** nên cũng dễ mở rộng từ count sang **tổng trọng số** nếu thao tác cộng/trừ hợp lệ.

## 20. Vì sao nén chỉ y của điểm là đủ?

Fenwick cần tạo chỉ số cho **vị trí được cập nhật**, tức các y của POINT. Các ngưỡng y1,y2,Y của query chỉ dùng để hỏi có bao nhiêu chỉ số y update nằm bên dưới một mốc.

Ví dụ `ys=[-1,2,5,9]` và query y≤4, upperBound(4)=2; không có y=4 trong mảng cũng không sao. Nếu thêm mọi y query vào compression thì vẫn có thể đúng, nhưng tạo nhiều ô Fenwick không chứa điểm, tăng bộ nhớ mà không giúp thuật toán đơn giản hơn.

Một số bài toán khác **phải** nén cả tọa độ sự kiện và biên query, ví dụ khi thực hiện range add trên các mốc hoặc cần đếm độ dài phủ. Lựa chọn tập tọa độ cần nén phải xuất phát từ thao tác **update** thực tế.

## 21. Nén tọa độ bảo toàn quan hệ gì?

Nếu a<b thì compressed(a)<compressed(b), và nếu a=b thì compressed(a)=compressed(b). Những quan hệ này đủ cho truy vấn theo thứ tự, chọn tiền tố, đếm số phần tử nằm dưới ngưỡng.

Nhưng nén **không bảo toàn khoảng cách**:

~~~text
Tọa độ thật: [10, 11, 1_000_000].
Chỉ số nén: [1, 2, 3].
~~~

Khoảng cách thật từ 11 tới 1_000_000 rất lớn, trong khi khoảng chỉ số chỉ bằng 1. Nếu bài hỏi **tổng chiều dài đoạn được phủ** hoặc diện tích hợp các hình chữ nhật, Segment Tree phải lưu chiều dài thật giữa các mốc gốc, không được dùng hiệu hai index nén làm độ dài.

Đây là lý do cần phân biệt bài **đếm điểm** của README với các bài **quét hình học đo chiều dài/diện tích**: cả hai có thể dùng sweep và compression, nhưng thông tin lưu trong node khác nhau.

## 22. Độ phức tạp của lời giải

Gọi n là số điểm, q là số dominance query hoặc rectangle query, m là số tọa độ y phân biệt của điểm, m≤n. Số event:

~~~text
Dominance: n+q.
Rectangle: n+4q.
~~~

Các bước:

1. Sort và distinct y của điểm: **O(n log(n+1))**.
2. Tạo sự kiện: O(n+q).
3. Sort event theo x/phase: **O((n+q) log(n+q+1))**.
4. Mỗi POINT: lowerBound O(log(m+1)) và Fenwick.add O(log(m+1)).
5. Mỗi QUERY probe: lower/upperBound và Fenwick.prefix O(log(m+1)).
6. Ghi answer về id gốc: O(1) mỗi probe.

Do đó tổng thời gian thường viết gọn **O((n+q) log(n+q+1))**; bộ nhớ phụ **O(n+q)** cho mảng y, Fenwick, event, probe và câu trả. Khi m=0, mọi query trả 0 mà không cần cập nhật Fenwick.

Với rectangle, hệ số bốn chỉ là hằng số nên vẫn là O((n+q) log(n+q+1)). Brute oracle O(nq) không nằm trong thuật toán chính và chỉ dùng cho các test nhỏ.

## 23. Lưu ý về số học và so sánh tọa độ

Tọa độ được lưu bằng `long`; có thể âm và có thể bằng Long.MIN_VALUE/Long.MAX_VALUE. Không so sánh x bằng `(int)(a.x-b.x)` hoặc `a.x-b.x`: hiệu long có thể tràn và phá thứ tự sort. Dùng:

~~~java
Comparator.comparingLong(Event::x)
          .thenComparingInt(Event::phase)
~~~

và binary search so trực tiếp `a[mid]<value` hoặc `a[mid]<=value`. Không tính x1-1, y1-1 trong rectangle.

Kết quả đếm dùng `long`. Với tổng số điểm n bị giới hạn bởi List kích thước int, số count thật nằm trong [0,n]. Nếu thay count bằng tổng trọng số, cần phân tích riêng khả năng overflow khi tổng các w_i không vừa long.

## 24. Khi nào chọn Segment Tree thay Fenwick?

**Fenwick** rất phù hợp cho bài này vì mỗi POINT chỉ **cộng 1 tại một vị trí** và query chỉ cần **tổng tiền tố**. Hai thao tác đều O(log m) và code ngắn, ít memory overhead.

**Segment Tree** hữu ích hơn khi cấu trúc truy vấn cần:

- Min/max trên một đoạn y tùy ý.
- Tích hợp nhiều loại thống kê và phép gộp phức tạp.
- Range add hoặc range assign với lazy propagation.
- Đếm độ dài được phủ bởi các đoạn y để tính diện tích union của rectangles.
- Khôi phục phần tử thứ k theo tổng tần suất trong những biến thể có dữ liệu động.

Không nên dùng Segment Tree chỉ vì bài có hai chiều: **một chiều đã được sweep**. Cấu trúc trên chiều còn lại mới phải đáp ứng thao tác cụ thể. Khi chỉ có point-add + prefix-sum, Fenwick thường là lựa chọn tối giản.

## 25. Các biến thể cùng mẫu tư duy

Ngoài dominance và rectangle count, có thể áp dụng cách phân tích này cho:

- **Đếm số đoạn chứa điểm t:** sự kiện mở đoạn, query ở t, đóng đoạn; tie rule quyết định khoảng đóng/mở.
- **Đếm nghịch thế trong mảng:** đi từ trái sang phải, nén giá trị a_i, Fenwick đếm các phần tử trước lớn hơn hiện tại (hoặc quét ngược để đếm nhỏ hơn).
- **Đếm cặp với điều kiện thời gian và giá trị:** sort sự kiện theo thời gian, dùng Fenwick giữ tần suất theo giá trị.
- **Truy vấn tổng có trọng số trong rectangle:** cộng trọng số thay vì +1 và áp inclusion–exclusion.
- **Truy vấn số điểm có x trong đoạn và y trong đoạn:** chính là bốn probe rectangle đã cài.
- **Offline threshold queries:** sort các đối tượng theo threshold độ lớn, kích hoạt khi đạt ngưỡng và dùng Segment Tree/Fenwick để trả truy vấn theo vị trí gốc.

Mẫu chung là: **chọn một thứ tự quét để chuyển một điều kiện thành trạng thái; chuyển điều kiện còn lại thành thao tác truy vấn trên một cấu trúc duy trì gia tăng**.

## 26. Khi nào không thể dùng thẳng sweep offline?

Nếu query đến liên tục và phải trả ngay, không biết trước các event tương lai, không thể sort lại toàn bộ query rồi quét một lượt offline như ví dụ. Khi ấy cần cấu trúc hỗ trợ **online dynamic queries** hoặc thiết kế batch.

Nếu có **xóa** điểm hoặc cập nhật tọa độ sau khi đã xử lý, trạng thái Fenwick chỉ-cộng không còn phù hợp; cần thêm sự kiện xóa với dấu -1, hoặc xử lý time dimension bằng một phương pháp khác.

Nếu bài có nhiều triệu event, việc sort và lưu toàn bộ event cũng là một chi phí bộ nhớ đáng kể. Có thể dùng external sort hoặc kỹ thuật streaming có thứ tự khi đầu vào đã được sắp phù hợp, nhưng phải duy trì đúng thứ tự tie.

Nếu cần top-k theo các điều kiện phức tạp, truy vấn tối thiểu hoặc hình học có đoạn giao nhau, chỉ Fenwick count không đủ. Phải thiết kế lại nội dung lưu ở node và bất biến của sweep.

## 27. Java 17+: cấu trúc và hợp đồng API

Chương trình mẫu dùng `record` và thư viện chuẩn Java 17 trở lên:

- `Point(x,y)`: một quan sát, kể cả các bản sao có tọa độ giống nhau.
- `DominanceQuery(X,Y)`: hỏi số điểm x≤X và y≤Y.
- `Rectangle(x1,y1,x2,y2)`: biên đóng; constructor từ chối x1>x2 hoặc y1>y2.
- `Probe`: một câu hỏi prefix hai chiều, có cờ `includeX/includeY`, hệ số ±1 và id câu trả.
- `Event`: chứa x, phase 0/1/2 và payload POINT/Probe.
- `Fenwick`: point-add và prefix-sum kiểu long.
- `lowerBound`, `upperBound`: xác định độ dài tiền tố y với biên mở/đóng.
- `sweep`: một engine dùng chung, sắp sự kiện và trả mảng kết quả theo id gốc.
- `dominance` và `rectangles`: tạo probe theo loại truy vấn, không tự triển khai lại logic sweep.
- `bruteDominance` và `bruteRectangles`: oracle độc lập O(nq).
- `verify`: vét cạn, random, extreme long, bài stress và input lỗi.

**Hợp đồng:** input List có thể rỗng, nhưng không được null hoặc chứa phần tử null. Hình chữ nhật có diện tích 0 vẫn hợp lệ nếu x1=x2 hoặc y1=y2. Query không làm thay đổi input; chương trình tạo event và kết quả riêng.

## 28. Chương trình Java 17+ hoàn chỉnh

Lưu nguyên mã dưới đây thành **SweepCompressionFenwick.java**. Code không cần thư viện ngoài; phần `verify` chỉ là kiểm thử, còn hai phương thức công khai `dominance` và `rectangles` là thuật toán offline thực sự.

~~~java
import java.util.*;

public final class SweepCompressionFenwick {
    private SweepCompressionFenwick() { }

    public record Point(long x, long y) { }
    public record DominanceQuery(long x, long y) { }
    public record Rectangle(long x1, long y1, long x2, long y2) {
        public Rectangle {
            if (x1 > x2 || y1 > y2) {
                throw new IllegalArgumentException("invalid inclusive rectangle");
            }
        }
    }

    private record Probe(long x, boolean includeX,
                         long y, boolean includeY,
                         int coefficient, int answerIndex) { }
    private record Event(long x, int phase, Point point, Probe probe) { }

    private static final class Fenwick {
        private final long[] tree;
        Fenwick(int size) { tree = new long[size + 1]; }
        void add(int oneBased, long delta) {
            if (oneBased <= 0 || oneBased >= tree.length) {
                throw new IllegalArgumentException("bad compressed index");
            }
            for (int i = oneBased; i < tree.length; i += i & -i) {
                tree[i] += delta;
            }
        }
        long prefix(int size) {
            if (size < 0 || size >= tree.length) {
                throw new IllegalArgumentException("bad prefix size");
            }
            long result = 0;
            for (int i = size; i > 0; i -= i & -i) {
                result += tree[i];
            }
            return result;
        }
    }

    private static int lowerBound(long[] a, long value) {
        int low = 0, high = a.length;
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (a[mid] < value) low = mid + 1;
            else high = mid;
        }
        return low;
    }

    private static int upperBound(long[] a, long value) {
        int low = 0, high = a.length;
        while (low < high) {
            int mid = low + (high - low) / 2;
            if (a[mid] <= value) low = mid + 1;
            else high = mid;
        }
        return low;
    }

    private static void validatePoints(List<Point> points) {
        if (points == null || points.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("null points");
        }
    }

    private static long[] sweep(List<Point> points,
                                List<Probe> probes, int answersCount) {
        validatePoints(points);
        if (probes == null || answersCount < 0) {
            throw new IllegalArgumentException("invalid events");
        }

        long[] ys = points.stream()
                .mapToLong(Point::y)
                .sorted().distinct().toArray();
        Fenwick fenwick = new Fenwick(ys.length);
        ArrayList<Event> events = new ArrayList<>();
        for (Point point : points) {
            events.add(new Event(point.x(), 1, point, null));
        }
        for (Probe probe : probes) {
            if (probe == null || probe.answerIndex() < 0
                    || probe.answerIndex() >= answersCount
                    || (probe.coefficient() != -1
                        && probe.coefficient() != 1)) {
                throw new IllegalArgumentException("invalid probe");
            }
            events.add(new Event(probe.x(),
                    probe.includeX() ? 2 : 0, null, probe));
        }

        // At equal x: exclusive-prefix probes, then points,
        // then inclusive-prefix probes.
        events.sort(Comparator.comparingLong(Event::x)
                .thenComparingInt(Event::phase));
        long[] answers = new long[answersCount];
        for (Event event : events) {
            if (event.phase() == 1) {
                int index = lowerBound(ys, event.point().y()) + 1;
                fenwick.add(index, 1);
            } else {
                Probe probe = event.probe();
                int prefixLength = probe.includeY()
                        ? upperBound(ys, probe.y())
                        : lowerBound(ys, probe.y());
                long partial = fenwick.prefix(prefixLength);
                answers[probe.answerIndex()] +=
                        probe.coefficient() * partial;
            }
        }
        return answers;
    }

    public static long[] dominance(List<Point> points,
                                   List<DominanceQuery> queries) {
        validatePoints(points);
        if (queries == null || queries.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("null queries");
        }
        ArrayList<Probe> probes = new ArrayList<>();
        for (int i = 0; i < queries.size(); i++) {
            DominanceQuery query = queries.get(i);
            probes.add(new Probe(query.x(), true, query.y(), true, 1, i));
        }
        return sweep(points, probes, queries.size());
    }

    public static long[] rectangles(List<Point> points,
                                    List<Rectangle> rectangles) {
        validatePoints(points);
        if (rectangles == null || rectangles.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("null rectangles");
        }
        ArrayList<Probe> probes = new ArrayList<>();
        for (int i = 0; i < rectangles.size(); i++) {
            Rectangle r = rectangles.get(i);
            // Four terms, with no x1-1 or y1-1 overflow.
            probes.add(new Probe(r.x2(), true, r.y2(), true, 1, i));
            probes.add(new Probe(r.x1(), false, r.y2(), true, -1, i));
            probes.add(new Probe(r.x2(), true, r.y1(), false, -1, i));
            probes.add(new Probe(r.x1(), false, r.y1(), false, 1, i));
        }
        return sweep(points, probes, rectangles.size());
    }

    private static long[] bruteDominance(List<Point> points,
                                         List<DominanceQuery> queries) {
        long[] answers = new long[queries.size()];
        for (int i = 0; i < queries.size(); i++) {
            DominanceQuery q = queries.get(i);
            for (Point p : points) {
                if (p.x() <= q.x() && p.y() <= q.y()) answers[i]++;
            }
        }
        return answers;
    }

    private static long[] bruteRectangles(List<Point> points,
                                          List<Rectangle> rectangles) {
        long[] answers = new long[rectangles.size()];
        for (int i = 0; i < rectangles.size(); i++) {
            Rectangle r = rectangles.get(i);
            for (Point p : points) {
                if (r.x1() <= p.x() && p.x() <= r.x2()
                        && r.y1() <= p.y() && p.y() <= r.y2()) {
                    answers[i]++;
                }
            }
        }
        return answers;
    }

    private static void check(List<Point> points,
                              List<DominanceQuery> dom,
                              List<Rectangle> rect) {
        long[] fastDom = dominance(points, dom);
        long[] slowDom = bruteDominance(points, dom);
        long[] fastRect = rectangles(points, rect);
        long[] slowRect = bruteRectangles(points, rect);
        if (!Arrays.equals(fastDom, slowDom)
                || !Arrays.equals(fastRect, slowRect)) {
            throw new AssertionError("oracle mismatch points=" + points
                    + " fastD=" + Arrays.toString(fastDom)
                    + " slowD=" + Arrays.toString(slowDom)
                    + " fastR=" + Arrays.toString(fastRect)
                    + " slowR=" + Arrays.toString(slowRect));
        }
        for (long x : fastDom) {
            if (x < 0 || x > points.size()) {
                throw new AssertionError("dominance answer out of range");
            }
        }
        for (long x : fastRect) {
            if (x < 0 || x > points.size()) {
                throw new AssertionError("rectangle answer out of range");
            }
        }
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    public static void verify() {
        List<DominanceQuery> gridQueries = new ArrayList<>();
        for (int x = -2; x <= 2; x++) {
            for (int y = -2; y <= 2; y++) {
                gridQueries.add(new DominanceQuery(x, y));
            }
        }
        List<Rectangle> gridRects = new ArrayList<>();
        for (int x1 = -1; x1 <= 1; x1++) {
            for (int x2 = x1; x2 <= 1; x2++) {
                for (int y1 = -1; y1 <= 1; y1++) {
                    for (int y2 = y1; y2 <= 1; y2++) {
                        gridRects.add(new Rectangle(x1, y1, x2, y2));
                    }
                }
            }
        }

        List<Point> positions = new ArrayList<>();
        for (int x = -1; x <= 1; x++) {
            for (int y = -1; y <= 1; y++) {
                positions.add(new Point(x, y));
            }
        }

        int exhaustive = 0;
        for (int length = 0; length <= 4; length++) {
            int cases = 1;
            for (int j = 0; j < length; j++) cases *= positions.size();
            for (int mask = 0; mask < cases; mask++) {
                int code = mask;
                List<Point> points = new ArrayList<>();
                for (int j = 0; j < length; j++) {
                    points.add(positions.get(code % positions.size()));
                    code /= positions.size();
                }
                check(points, gridQueries, gridRects);
                exhaustive++;
            }
        }

        Random rng = new Random(5062026L);
        long[] coordinates = {
                Long.MIN_VALUE, -100, -1, 0, 0, 1, 5, 100,
                Long.MAX_VALUE
        };
        int seeded = 0;
        for (int test = 0; test < 1500; test++) {
            int n = rng.nextInt(41), q = rng.nextInt(41);
            List<Point> points = new ArrayList<>();
            List<DominanceQuery> dom = new ArrayList<>();
            List<Rectangle> rect = new ArrayList<>();
            for (int i = 0; i < n; i++) {
                points.add(new Point(
                        coordinates[rng.nextInt(coordinates.length)],
                        coordinates[rng.nextInt(coordinates.length)]));
            }
            for (int i = 0; i < q; i++) {
                long x = coordinates[rng.nextInt(coordinates.length)];
                long y = coordinates[rng.nextInt(coordinates.length)];
                dom.add(new DominanceQuery(x, y));

                long x1 = coordinates[rng.nextInt(coordinates.length)];
                long x2 = coordinates[rng.nextInt(coordinates.length)];
                long y1 = coordinates[rng.nextInt(coordinates.length)];
                long y2 = coordinates[rng.nextInt(coordinates.length)];
                rect.add(new Rectangle(
                        Math.min(x1, x2), Math.min(y1, y2),
                        Math.max(x1, x2), Math.max(y1, y2)));
            }
            check(points, dom, rect);
            seeded++;
        }

        List<Point> large = new ArrayList<>();
        for (int i = 0; i < 20000; i++) {
            large.add(new Point(i, i));
        }
        List<DominanceQuery> largeQueries = new ArrayList<>();
        for (int i = -5; i < 20050; i += 11) {
            largeQueries.add(new DominanceQuery(i, i));
        }
        long[] largeResults = dominance(large, largeQueries);
        for (int i = 0; i < largeQueries.size(); i++) {
            long xy = largeQueries.get(i).x();
            long expected = Math.max(0, Math.min(20000, xy + 1));
            if (largeResults[i] != expected) {
                throw new AssertionError("large analytical mismatch");
            }
        }
        long[] largeRect = rectangles(large,
                List.of(new Rectangle(100, 200, 999, 800),
                        new Rectangle(Long.MIN_VALUE, Long.MIN_VALUE,
                                      Long.MAX_VALUE, Long.MAX_VALUE),
                        new Rectangle(2, 20001, 500, 30000)));
        if (!Arrays.equals(largeRect, new long[]{601, 20000, 0})) {
            throw new AssertionError("large rectangle mismatch");
        }

        expectInvalid(() -> dominance(null, List.of()));
        expectInvalid(() -> rectangles(null, List.of()));
        expectInvalid(() -> dominance(List.of(), null));
        expectInvalid(() -> rectangles(List.of(), null));
        expectInvalid(() -> dominance(Arrays.asList((Point)null),
                                      List.of()));
        expectInvalid(() -> rectangles(List.of(),
                      Arrays.asList((Rectangle)null)));
        expectInvalid(() -> dominance(List.of(),
                      Arrays.asList((DominanceQuery)null)));
        expectInvalid(() -> new Rectangle(2, 0, 1, 1));
        expectInvalid(() -> new Rectangle(0, 2, 1, 1));

        System.out.println("Exhaustive point streams: " + exhaustive + " PASS");
        System.out.println("Seeded extreme-coordinate cases: " + seeded + " PASS");
        System.out.println("Large diagonal n=20000: PASS");
        System.out.println("Boundary ordering and invalid inputs: PASS");
    }

    public static void main(String[] args) {
        List<Point> points = List.of(
                new Point(-2, 5), new Point(0, -1),
                new Point(0, 5), new Point(0, 5),
                new Point(3, 2), new Point(3, 9));
        List<DominanceQuery> dom = List.of(
                new DominanceQuery(-3, 100),
                new DominanceQuery(-2, 5),
                new DominanceQuery(0, 5),
                new DominanceQuery(0, 4),
                new DominanceQuery(3, 5),
                new DominanceQuery(3, 9),
                new DominanceQuery(0, -2));
        List<Rectangle> rect = List.of(
                new Rectangle(-2, 5, 0, 5),
                new Rectangle(0, -1, 3, 5),
                new Rectangle(0, 5, 0, 5),
                new Rectangle(Long.MIN_VALUE, Long.MIN_VALUE,
                              Long.MAX_VALUE, Long.MAX_VALUE),
                new Rectangle(1, -100, 2, 100));
        System.out.println("Dominance counts: "
                + Arrays.toString(dominance(points, dom)));
        System.out.println("Inclusive rectangle counts: "
                + Arrays.toString(rectangles(points, rect)));
        verify();
    }
}
~~~

Biên dịch bằng JDK 17 trở lên và chạy:

~~~bash
javac SweepCompressionFenwick.java
java SweepCompressionFenwick
~~~

**Stdout chính xác quan sát được trong lần chạy thực tế:**

~~~text
Dominance counts: [0, 1, 4, 1, 5, 6, 0]
Inclusive rectangle counts: [3, 4, 2, 6, 0]
Exhaustive point streams: 7381 PASS
Seeded extreme-coordinate cases: 1500 PASS
Large diagonal n=20000: PASS
Boundary ordering and invalid inputs: PASS
~~~

Dòng `[0,1,4,1,5,6,0]` lần lượt tương ứng bảy dominance query theo thứ tự input. Dòng `[3,4,2,6,0]` tương ứng năm rectangle đóng. Các dòng PASS được in sau khi `verify` đối chiếu thuật toán nhanh với oracle độc lập và các kiểm thử biên.

## 29. Kiểm thử vét cạn 7.381 dãy điểm

Để kiểm tra tính đúng của từng sự kiện, bộ test sinh mọi **dãy điểm theo thứ tự** dài L từ 0 tới 4, mỗi điểm nằm trong ô lưới:

~~~text
x thuộc {-1,0,1}.
y thuộc {-1,0,1}.
Số vị trí tọa độ phân biệt: 3*3=9.
~~~

Với độ dài L có 9^L dãy, cho phép cùng tọa độ xuất hiện nhiều lần. Tổng:

~~~text
sum_(L=0)^4 9^L
 = 1+9+81+729+6561
 = 7381.
~~~

Với mỗi dãy điểm, `check` đối chiếu:

- 25 dominance query: X,Y đều lần lượt từ -2 đến 2.
- 36 rectangle đóng: các biên chọn trong {-1,0,1} và thỏa x1≤x2, y1≤y2.
- Hai oracle duyệt trực tiếp mọi điểm cho từng truy vấn.
- Mỗi kết quả nhanh phải trùng chính xác oracle.
- Mọi kết quả nằm trong [0,n].

Việc duyệt tất cả các dãy (không chỉ tập điểm phân biệt) rất quan trọng vì nó tạo ra **điểm trùng và trật tự input khác nhau**. Kết quả đã chạy: **7.381 dãy PASS**.

## 30. Kiểm thử ngẫu nhiên, tọa độ cực trị và trường hợp lớn

Bộ test thứ hai tạo **1.500 input có seed** `Random(5062026L)`, mỗi input có n từ 0 tới 40 điểm và q từ 0 tới 40 truy vấn mỗi loại. Tọa độ lấy từ:

~~~text
Long.MIN_VALUE, -100, -1, 0, 0, 1, 5, 100, Long.MAX_VALUE.
~~~

Giá trị 0 được lặp trong danh sách sinh để tăng xác suất trùng. Rectangle được chuẩn hóa biên bằng min/max, nhưng truy vấn không yêu cầu một tọa độ nằm sẵn trong tập điểm. Các câu trả đều được so với brute oracle; **1.500 trường hợp PASS**.

Bài stress tạo **20.000 điểm trên đường chéo** `(i,i)`, i=0..19999. Với dominance query `(t,t)`, đáp án theo công thức:

~~~text
answer(t,t) = clamp(t+1, 0, 20000).
~~~

Các query được lấy ở nhiều t; lời giải nhanh phải trùng công thức trên mà không phải duyệt n điểm mỗi câu hỏi.

Rectangle `[100,999] × [200,800]` chứa chính xác các điểm `(i,i)` với 200≤i≤800, tức **601 điểm**. Rectangle toàn bộ miền long chứa 20.000 điểm; rectangle có y>20000 trả 0. Bộ test cũng từ chối input null và rectangle sai thứ tự biên.

## 31. Những lỗi triển khai phổ biến

1. **Sắp sự kiện theo x nhưng bỏ phase**, dẫn tới sai khi POINT và QUERY cùng x.
2. **Xử lý query x≤X trước POINT x=X**, vô tình giải x<X.
3. **Xử lý query x<X sau POINT x=X**, vô tình giải x≤X.
4. **Dùng lowerBound cho y≤Y** thay vì upperBound.
5. **Dùng upperBound cho y<Y** thay vì lowerBound.
6. **Lấy tọa độ y nguyên gốc làm Fenwick index**, sai với âm hoặc giá trị rất lớn.
7. **Quên +1 khi update chỉ số nén 1-based**, gây add(0) không tiến.
8. **Cộng +1 sai vào prefixLength**, khiến đếm luôn thêm một tọa độ.
9. **Gộp điểm trùng bằng Set**, bỏ các quan sát cần đếm riêng.
10. **Chỉ nén y điểm nhưng yêu cầu query Y phải có trong mảng nén**, dù binary search giải được.
11. **Dùng `x1-1` khi x1=Long.MIN_VALUE**, gây underflow.
12. **Dùng `y1-1` khi y1=Long.MIN_VALUE**, gây underflow.
13. **Quên hệ số +1 ở giao của hai miền bị trừ**, làm inclusion–exclusion sai.
14. **Dùng đúng bốn prefix nhưng trả về thứ tự sự kiện thay vì id query gốc**.
15. **Sắp tọa độ bằng phép trừ `a-b`**, có nguy cơ overflow.
16. **Nhầm số entry Fenwick với giá trị tọa độ lớn nhất**.
17. **Không xử lý n=0** và Fenwick rỗng.
18. **Không hỗ trợ rectangle độ rộng/chiều cao 0**, dù biên đóng hoàn toàn hợp lệ.
19. **Bỏ kiểm tra hình chữ nhật x1≤x2 và y1≤y2**, làm công thức không còn cùng mô hình.
20. **Dùng long weights rồi cộng vào int**, dẫn tới overflow khi mở rộng tính tổng.
21. **Dùng compression index làm chiều dài thật**, sai với quét hợp đoạn.
22. **Nói Fenwick là cấu trúc hai chiều**, dù một chiều x đã xử lý bằng sweep.
23. **Gọi thuật toán offline là online**, khi toàn bộ query phải biết trước để sort.
24. **Quên rằng query không được thay đổi trạng thái Fenwick**.
25. **Cập nhật tất cả điểm ngay từ đầu**, khiến điều kiện x của query mất ý nghĩa.
26. **Dùng mảng nén không distinct**, làm mapping y và số index không đúng như dự định.
27. **Không kiểm thử tọa độ cùng x/y**, bỏ lỡ phần dễ sai nhất.
28. **Chỉ so số lượng query đầu tiên**, bỏ lỗi id và ordering các câu hỏi sau.
29. **Nhầm O((n+q) log(n+q)) với O(nq)** của brute oracle.
30. **Áp công thức rectangle đóng cho rectangle nửa mở mà không đổi phase/lowerBound**.
31. **Nhầm phép nén tọa độ với việc làm tròn giá trị số**, trong khi compression chỉ là thay nhãn thứ tự.
32. **Tối ưu bằng cách song song hóa vòng quét mà không giữ đúng thứ tự event**, phá bất biến Prefix.

## 32. Bài tập tự luyện

**Bài 1 — Chạy tay:** dùng sáu điểm mẫu, tính câu trả cho (X,Y)=(0,5) và (3,5), chỉ ra điểm nào bị loại bởi điều kiện x hay y.

**Bài 2 — Tie rule:** có ba điểm cùng x=0, hãy xếp phase0, POINT, phase2 và tính query x<0 so với x≤0.

**Bài 3 — Nén tọa độ:** với y `[-10,100,100,5,-10]`, lập mảng unique sorted và xác định lowerBound/upperBound của 0,5,100,101.

**Bài 4 — Fenwick:** mô phỏng add(1,+1), add(3,+2), prefix(0), prefix(2), prefix(3) với m=4.

**Bài 5 — Bất biến:** chứng minh Fenwick tại phase0 chỉ chứa điểm x<X, còn tại phase2 chứa điểm x≤X.

**Bài 6 — Rectangle:** viết bốn prefix của rectangle [0,0]×[5,5] và giải thích vì sao hai điểm (0,5) trùng vẫn được đếm 2.

**Bài 7 — Overflow:** với x1=y1=Long.MIN_VALUE, trình bày vì sao dùng biên mở thay cho x1−1/y1−1 là đúng và an toàn.

**Bài 8 — Oracle:** viết brute dominance và brute rectangle, sinh các dãy điểm độ dài ≤4 trên lưới 3×3 và so mọi query.

**Bài 9 — Complexity:** đếm n+q event dominance và n+4q event rectangle, suy ra độ phức tạp khi sort event và dùng Fenwick.

**Bài 10 — Truy vấn tổng:** đổi Point thành (x,y,w), cập nhật Fenwick bằng w và giải thích điều kiện để inclusion–exclusion vẫn đúng.

**Bài 11 — Xử lý đoạn:** một đoạn thời gian [l,r] có sự kiện start/end. Hãy xây thứ tự sự kiện khi hỏi số đoạn hoạt động tại t, phân biệt đoạn đóng và nửa mở.

**Bài 12 — Nghịch thế:** ứng dụng compression + Fenwick đếm cặp i<j, a_i>a_j trong một dãy có số âm và bản sao.

**Bài 13 — Segment Tree:** nếu thay sum bằng min hoặc cần range add, tại sao Fenwick đơn giản không còn phù hợp? Chọn cấu trúc thay thế.

**Bài 14 — Độ dài hình học:** với tọa độ [10,11,1000000], giải thích vì sao hiệu chỉ số nén không thể làm độ dài hợp đoạn.

**Bài 15 — Stress:** chạy bài trên điểm đường chéo n=20.000 và query `(t,t)` để so với công thức clamp(t+1,0,n).

**Bài 16 — Thiết kế riêng:** cho một bài có time, score và query đếm score≤Y tại thời điểm T, xác định trục quét, trục compression và Fenwick operation.

## 33. Checklist cuối bài và kết luận

Khi nhận một bài **quét sự kiện kết hợp nén tọa độ và cấu trúc truy vấn**, hãy lần lượt hỏi:

- **Có thể làm offline không?** Nếu biết trước query, sort các sự kiện để chia sẻ công việc.
- **Quét theo trục nào?** Chọn một tọa độ/threshold mà trạng thái biến đổi đơn điệu.
- **Điểm nào được coi là active?** Viết bất biến rõ ràng trước khi code.
- **Dấu `<` hay `≤` trên biên?** Định nghĩa thứ tự hòa ở cùng tọa độ.
- **Tọa độ nào phải nén?** Ít nhất cần mọi tọa độ update của cấu trúc.
- **Truy vấn cần loại tổng nào?** Prefix sum đếm/tổng dùng Fenwick; min/max, lazy/range update có thể cần Segment Tree.
- **Làm sao giữ thứ tự đáp án gốc?** Mỗi probe phải mang query id.
- **Rectangle đóng/mở?** Dùng inclusion–exclusion với phase và lower/upperBound đúng, tránh phép trừ 1 gây tràn.
- **Có giá trị trùng, âm, cực trị, n=0?** Kiểm thử các trường hợp ấy trước khi tối ưu.
- **Có oracle độc lập nhỏ?** Duyệt trực tiếp từng điểm cho từng query để đối chiếu toàn bộ tập test.

**Kết luận:** Quét sự kiện đưa một điều kiện vào **thứ tự xử lý**, nén tọa độ đưa trục còn lại vào miền chỉ số nhỏ, và Fenwick/Segment Tree duy trì **thống kê của các đối tượng đang có hiệu lực**. Khi ba phần được gắn với một bất biến rõ ràng, ta biến bài đếm điểm hai chiều O(nq) thành lời giải ngoại tuyến khoảng **O((n+q) log(n+q))**, xử lý đúng cả trùng lặp và biên đóng/mở. Bài học quan trọng nhất không chỉ là nhớ Fenwick, mà là **thiết kế event, quy tắc tie và ý nghĩa chính xác của prefix đang được truy vấn**.
