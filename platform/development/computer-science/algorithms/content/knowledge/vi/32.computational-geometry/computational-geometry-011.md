# Calip quay và đường kính của bao lồi

**Đường kính của một tập điểm** trong hình học tính toán là khoảng cách Euclid lớn nhất giữa hai điểm thuộc tập. Với n điểm trong mặt phẳng, cách trực tiếp duyệt mọi cặp để lấy khoảng cách lớn nhất cần O(n²) thời gian. Khi n lớn, ta có thể cải thiện bằng hai ý tưởng quan trọng:

1. **Chỉ cần xét các đỉnh của bao lồi (convex hull)**, bởi một cặp điểm xa nhất có thể chọn ở các điểm cực biên.
2. Trên bao lồi có h đỉnh theo thứ tự ngược chiều kim đồng hồ, dùng kỹ thuật **calip quay (rotating calipers)** để tìm đường kính với **O(h)** thời gian sau khi đã có bao lồi.

Bài **“Calip quay và đường kính của bao lồi”** thuộc nhóm **Hình học tính toán** trong Computer Science Algorithms, tập trung vào cơ chế các cặp điểm đối cực (*antipodal pairs*), phép nhân có hướng để xác định đỉnh xa cạnh, cách dịch con trỏ đối cực theo góc quay của cạnh, xử lý cạnh song song và trường hợp diện tích bằng nhau, các cấu hình suy biến và an toàn số nguyên.

Phần cuối có chương trình **Java 17+ chạy độc lập**, xây bao lồi bằng **monotone chain**, rồi dùng **rotating calipers** để tính bình phương đường kính. Mã đã được kiểm tra đối chiếu với phép duyệt **tất cả cặp điểm** trên 512 tập con của lưới 3×3, 1.536 biến thể thứ tự/trùng lặp và 5.000 tập điểm sinh bằng seed cố định. Bài sử dụng tọa độ nguyên trong khoảng [−10⁹,10⁹] để mọi phép nhân có hướng và bình phương khoảng cách đều vừa kiểu long.

## 1. Phát biểu bài toán chính xác

Cho tập hữu hạn các điểm P={p₀,p₁,...,pₙ₋₁} trong mặt phẳng. Mỗi điểm p có tọa độ (x,y). Khoảng cách Euclid giữa hai điểm a,b:

~~~text
dist(a,b) = sqrt((a.x-b.x)^2 + (a.y-b.y)^2).
~~~

Đường kính:

~~~text
diameter(P) = max dist(a,b), với a,b thuộc P.

diameterSquared(P)
    = max [(a.x-b.x)^2 + (a.y-b.y)^2].
~~~

Nếu chỉ cần tìm **cặp điểm xa nhất** hoặc so sánh các khoảng cách, ta không cần lấy căn bậc hai: vì sqrt tăng đơn điệu trên số không âm, cặp tối ưu của khoảng cách Euclid cũng tối ưu của **bình phương khoảng cách**.

Trong chương trình:

- Nếu tập điểm **rỗng**, không có cặp để tối ưu và trả **Optional.empty**.
- Nếu chỉ có **một điểm phân biệt**, trả chính điểm đó ở hai đầu với khoảng cách bình phương **0**.
- Điểm trùng nhau được phép xuất hiện trong input, nhưng được loại khi xây bao lồi.
- Nếu có nhiều cặp cùng khoảng cách tối đa, chọn **cặp theo thứ tự từ điển nhỏ nhất** để kết quả xác định.
- Mỗi tọa độ nguyên phải nằm trong **[−1.000.000.000,1.000.000.000]**.

Quy ước này được dùng nhất quán từ thuật toán tới code, tránh tranh luận mơ hồ về trường hợp 0 hoặc 1 điểm.

## 2. Vì sao cách vét cạn O(n²)?

Cách đơn giản thử mọi cặp điểm a,b:

~~~text
best = 0
for i=0..n-1:
    for j=i+1..n-1:
        best = max(best, squaredDistance(p[i],p[j]))
~~~

Có n(n−1)/2 cặp phân biệt, nên cần **O(n²)** phép tính và O(1) bộ nhớ bổ sung. Với n nhỏ như vài chục điểm, cách này rất hữu ích vì đơn giản và dễ kiểm tra.

Tuy nhiên, với n=100.000 thì có xấp xỉ 5 tỷ cặp, quá đắt. Tối ưu chính là khai thác **hình dạng hình học của tập điểm** thay vì xét từng cặp tùy ý.

Vẫn cần giữ thuật toán vét cạn làm **oracle độc lập** khi kiểm thử cài đặt calip quay: nếu cùng hai phương pháp trả một cặp điểm và bình phương khoảng cách giống nhau cho hàng nghìn tập điểm nhỏ, ta có bằng chứng thực nghiệm tốt về logic của thuật toán mới.

## 3. Bao lồi là gì?

**Bao lồi** của tập điểm P là tập lồi nhỏ nhất chứa toàn bộ P. Trong trường hợp có ít nhất ba điểm không thẳng hàng, biên của bao lồi là một đa giác lồi, các đỉnh là những điểm cực biên lấy từ P.

Ví dụ gồm:

~~~text
P = {(0,0), (3,0), (3,2), (0,2), (1,1), (3,0)}.

Bao lồi:
(0,0) -> (3,0) -> (3,2) -> (0,2) -> (0,0).

(1,1) nằm trong hình chữ nhật nên bị bỏ khỏi danh sách đỉnh.
(3,0) xuất hiện trùng hai lần nên chỉ giữ một lần.
~~~

Với một tập điểm hoàn toàn **thẳng hàng**, bao lồi theo nghĩa hình học là **một đoạn thẳng**; chương trình chỉ giữ **hai đầu mút** nếu có ít nhất hai tọa độ phân biệt.

Chính việc chỉ giữ đỉnh cực biên là cơ sở giảm số lượng ứng viên: mọi điểm ở trong hoặc trên một cạnh đều không cần xét riêng để đạt đường kính tối đa, trừ trường hợp tập chỉ có một điểm duy nhất.

## 4. Tại sao đường kính đạt ở các đỉnh bao lồi?

Xét một điểm x nằm trong bao lồi và một điểm b cố định. Hàm **bình phương khoảng cách** f(x)=|x−b|² là hàm lồi theo tọa độ x.

Nếu x là tổ hợp lồi của các đỉnh v₁,...,vₕ, ta có:

~~~text
x = λ₁v₁ + ... + λₕvₕ,
λₖ>=0, Σλₖ=1.
~~~

Theo tính lồi (hoặc bất đẳng thức tam giác và tính chất cực đại), có ít nhất một đỉnh vₖ không gần b hơn x:

~~~text
|x-b| <= max_k |v_k-b|.
~~~

Thay x bằng một đỉnh không làm giảm khoảng cách. Sau đó có thể áp dụng lập luận tương tự cho b để thay b bằng một đỉnh khác. Do đó **một cặp điểm xa nhất có thể được chọn trong các đỉnh của bao lồi**.

Đây là lập luận tồn tại, không nói mọi cặp đỉnh đều xa nhất. Cũng không có nghĩa chỉ cần lấy hai đỉnh có độ chênh x lớn nhất: một cặp tạo đường chéo có thể xa hơn các cặp theo riêng từng trục.

## 5. Hướng quay và tích có hướng

Với ba điểm a,b,c, định nghĩa **tích có hướng trong mặt phẳng**:

~~~text
cross(a,b,c)
    = (b.x-a.x)*(c.y-a.y)
      - (b.y-a.y)*(c.x-a.x).
~~~

Giá trị này bằng **hai lần diện tích có hướng** của tam giác a,b,c.

- cross(a,b,c)>0: c nằm bên **trái** hướng từ a đến b, ba điểm quay **ngược chiều kim đồng hồ (CCW)**.
- cross(a,b,c)<0: c nằm bên **phải**, quay theo chiều kim đồng hồ.
- cross(a,b,c)=0: a,b,c **thẳng hàng**.

Độ lớn |cross| cho biết diện tích hình bình hành tạo bởi hai vector. Khi cạnh a→b được giữ cố định, độ lớn này tỷ lệ với **khoảng cách vuông góc từ c đến đường thẳng qua cạnh**, vì chiều dài cạnh là một hằng số.

Với đa giác lồi được liệt kê **CCW**, tất cả đỉnh nằm bên trái hoặc trên đường thẳng chứa mỗi cạnh có hướng, nên **cross(a,b,c)≥0** khi a,b là hai đỉnh kề theo hướng CCW. Do đó trong calip quay ta có thể so **cross trực tiếp** mà không cần lấy trị tuyệt đối.

## 6. Xây bao lồi bằng monotone chain

Một cách cài đặt bao lồi phổ biến là **Andrew’s monotone chain**:

1. Sắp điểm theo thứ tự từ điển **x tăng, nếu bằng x thì y tăng**.
2. Xóa tọa độ trùng.
3. Quét trái qua phải để xây **lower hull**. Mỗi khi ba điểm cuối không tạo góc trái nghiêm ngặt (cross≤0), bỏ điểm ở giữa.
4. Quét ngược phải qua trái để xây **upper hull**, dùng cùng điều kiện cross≤0.
5. Bỏ điểm cuối bị lặp ở hai chuỗi rồi ghép lower+upper.

Pseudo-code phần lower:

~~~text
lower = []
for p theo thứ tự x,y tăng:
    while lower.size >= 2
          and cross(lower[-2], lower[-1], p) <= 0:
        pop lower[-1]
    push p
~~~

Upper tương tự nhưng quét theo thứ tự ngược. Khi ghép kết quả, với ít nhất ba điểm không thẳng hàng, ta có các đỉnh theo **thứ tự CCW**, không lặp điểm đầu ở cuối.

Cả hai lần quét đều O(n), vì mỗi điểm được thêm một lần và loại nhiều nhất một lần trong một stack. Bước **sắp xếp O(n log n)** chi phối tổng thời gian.

## 7. Vì sao điều kiện cross≤0 quan trọng?

Trong monotone chain, khi có ba điểm a,b,c liên tiếp mà cross(a,b,c)<0, đường đi đang rẽ sang phải, không phù hợp với phần đang xây của bao lồi. Bỏ b là cần thiết.

Khi cross=0, ba điểm thẳng hàng. Nếu giữ mọi điểm thẳng hàng trên cạnh, kết quả có thể chứa nhiều đỉnh liên tiếp tạo cross=0. Thuật toán calip quay đơn giản trong bài dựa trên đa giác lồi có **các bước rẽ trái nghiêm ngặt**, nên ta chọn xóa **điểm nằm giữa** khi cross=0.

Ví dụ:

~~~text
P = {(-3,-3),(-1,-1),(0,0),(5,5)}.
~~~

Tất cả thẳng hàng. Hull chỉ còn **(-3,-3) và (5,5)**. Bình phương đường kính:

~~~text
(5-(-3))^2 + (5-(-3))^2
= 8^2 + 8^2
= 128.
~~~

Nếu chỉ kiểm tra cross<0 thay vì cross≤0, nhiều điểm thẳng hàng nằm trên cạnh còn lại; về lý thuyết vẫn có thể tìm đường kính bằng phiên bản calip phù hợp, nhưng phải xử lý các cạnh zero-angle khác. Bản code hiện tại cố ý giữ hull **không có các điểm thẳng hàng trung gian**.

## 8. Cặp điểm đối cực (antipodal pair)

Khi hình dung một đa giác lồi bị kẹp giữa **hai đường thẳng song song**, ta có thể quay hai đường thẳng kẹp quanh đa giác. Các điểm tiếp xúc với hai đường thẳng là những **điểm cực biên theo hai hướng đối nhau**, dẫn đến khái niệm cặp điểm **đối cực**.

Một định lý nền tảng của rotating calipers: **cặp đỉnh tạo đường kính của đa giác lồi là một cặp đối cực**, tức tồn tại các đường đỡ song song của bao lồi tiếp xúc với hai đỉnh đó.

Không nhất thiết phải sinh toàn bộ cặp đỉnh. Khi cố định một cạnh có hướng, ta tìm đỉnh đối diện có **độ cao vuông góc lớn nhất** so với đường thẳng chứa cạnh. Khi cạnh quay dần quanh bao lồi, đỉnh ở phía đối diện chỉ cần dịch tiếp **theo chiều CCW**, không phải quay lại đầu cho mỗi cạnh.

Đây là trực giác hình học khiến hai con trỏ i và j cho tổng O(h) bước trên hull, khác O(h²) của việc thử mọi cặp đỉnh.

## 9. Từ độ cao tới so sánh cross

Với cạnh e=(H[i],H[i+1]) của hull CCW, và một đỉnh H[j] ở phía đối diện, độ cao từ H[j] xuống đường thẳng của e bằng:

~~~text
height(j) = cross(H[i],H[i+1],H[j])
            / length(H[i],H[i+1]).
~~~

Vì cạnh e đang cố định, mẫu số không thay đổi. Do đó:

~~~text
height(nextJ)>height(j)
tương đương
cross(H[i],H[i+1],H[nextJ])
  > cross(H[i],H[i+1],H[j]).
~~~

Không cần phép chia, căn bậc hai hay số thực. Mã so **hai giá trị long chính xác**.

Điều kiện chọn **dấu >** là chủ ý: chỉ tăng j khi đỉnh kế có **độ cao lớn hơn**. Nếu độ cao bằng nhau, hai đỉnh có thể là hai điểm chạm của một cạnh trên đường đỡ song song; phải xét cả hai như ứng viên thay vì lặng lẽ bỏ một.

## 10. Công thức hai con trỏ quay

Giả sử hull H có h≥3 đỉnh theo CCW, không có điểm trung gian thẳng hàng; sử dụng chỉ số modulo h.

~~~text
j = 1
best = chưa có cặp

for i = 0..h-1:
    nextI = (i+1) % h

    while cross(H[i],H[nextI],H[(j+1)%h])
          > cross(H[i],H[nextI],H[j]):
        j = (j+1) % h

    xét cặp (H[i],H[j])
    xét cặp (H[nextI],H[j])

    nextJ = (j+1)%h
    if cross(edge, H[nextJ]) == cross(edge, H[j]):
        xét cặp (H[i],H[nextJ])
        xét cặp (H[nextI],H[nextJ])
~~~

Ở mỗi cạnh, j dừng tại một đỉnh có độ cao cực đại theo hướng cạnh hiện tại. Bởi đa giác lồi và cạnh lần lượt quay theo một chiều, j có thể tiếp tục tiến từ vị trí đạt được trước đó. **Không được đặt lại j=0 ở mọi i** nếu muốn giữ O(h).

Hàm chọn cặp luôn so **bình phương khoảng cách**. Ứng viên có giá trị lớn hơn thay thế best; nếu bằng nhau, dùng quy tắc phá hòa theo thứ tự từ điển để kết quả tái hiện được.

## 11. Vì sao xét cả i và i+1?

Một cạnh hiện tại e có **hai đầu** là H[i] và H[i+1]. Đỉnh đối diện j đạt cực đại cross so với đường thẳng chứa cạnh.

Cặp đường đỡ song song có thể đi qua một **đỉnh** ở phía đối diện và một **cạnh** ở phía này. Nếu cặp tạo đường kính gắn với đầu **i+1** thay vì i, chỉ thử (H[i],H[j]) sẽ có nguy cơ không nhận diện đúng sự kiện đối cực trong cách duyệt hiện tại.

Vì vậy mỗi lần xác định đỉnh đối diện, bản code xét cả:

~~~text
(H[i], H[j])
(H[i+1], H[j])
~~~

Chi phí thêm vẫn O(1) cho mỗi cạnh. Trong nhiều cách trình bày calipers có thể chỉ xét một số cặp trên điều kiện bất biến khác, nhưng việc xét hai đầu mút ở đây giúp mô tả đối cực và tránh lỗi bỏ ứng viên quan trọng.

## 12. Diện tích bằng nhau và các cạnh song song

Đây là một tình huống dễ gây lỗi. Giả sử cạnh e ở đáy của hình chữ nhật. Hai đỉnh ở cạnh trên có cùng độ cao so với đường thẳng chứa e.

Ví dụ hình chữ nhật:

~~~text
H[0]=(0,0)
H[1]=(3,0)
H[2]=(3,2)
H[3]=(0,2)

Cạnh e = H[0] -> H[1].

cross(H[0],H[1],H[2]) = 6.
cross(H[0],H[1],H[3]) = 6.
~~~

Nếu j đã tới H[2], H[3] là đỉnh kế có **diện tích bằng nhau**, chứ không lớn hơn. Vì vậy vòng while dùng dấu > dừng lại, nhưng nhánh **tie** vẫn thử H[3].

Hai đường chéo đều có bình phương khoảng cách **3²+2²=13**. Bản code chọn cặp với thứ tự từ điển nhỏ nhất: **(0,0) và (3,2)**.

Trên bao lồi không có ba đỉnh liên tiếp thẳng hàng, tập đỉnh có độ cao cực đại đối với một cạnh có thể gồm một đỉnh, hoặc **hai đỉnh kề nhau** tạo thành một cạnh song song. Do đó thử j và j+1 ở trường hợp bằng nhau là đủ cho plateau này.

## 13. Chạy tay hình chữ nhật

Input gồm các điểm:

~~~text
(0,0), (3,0), (3,2), (0,2),
(1,1) là điểm trong,
(3,0) được nhập trùng.
~~~

Sau lọc và monotone chain:

~~~text
Hull CCW = [
  (0,0),
  (3,0),
  (3,2),
  (0,2)
].
~~~

Xét cạnh đáy:

~~~text
e = (0,0)->(3,0).
Cross với (3,0) = 0.
Cross với (3,2) = 6.
Cross với (0,2) = 6.
~~~

Con trỏ j tiến tới (3,2). Cạnh trên có độ cao bằng nhau nên nhánh tie còn xét (0,2). Ta cập nhật các khoảng cách bình phương.

Hai đường chéo:

~~~text
dist²((0,0),(3,2)) = 3²+2² = 13.
dist²((3,0),(0,2)) = (-3)²+2² = 13.
~~~

Hai cạnh dài có bình phương 9, các cạnh ngắn có bình phương 4. Do đó đường kính có bình phương **13**, độ dài thực là sqrt(13), khoảng 3,60555. Chương trình trả chính xác 13, không dùng double để quyết định cặp tối ưu.

## 14. Chứng minh vì sao các cặp đối cực đủ để tìm đường kính

Gọi a,b là một cặp điểm trên đa giác lồi làm cực đại khoảng cách. Xét các đường đỡ đi qua a và b theo hai hướng đối nhau, vuông góc với vector nối a,b.

Nếu tồn tại điểm khác nằm vượt đường đỡ ở phía ngoài gần a theo chiều ra xa b, khi đó khoảng cách của nó tới b sẽ lớn hơn khoảng cách a–b, mâu thuẫn với tính tối ưu. Tương tự ở b. Vì thế tồn tại **hai đường đỡ song song** chạm đa giác tại a và b: chúng là cặp **đối cực**.

Khi xoay cặp đường đỡ quanh đa giác, các điểm tiếp xúc thay đổi tại các góc tương ứng với cạnh. Mỗi lần có một cạnh làm đường đỡ, ta có thể chọn đỉnh/cạnh đối diện cực đại diện tích (độ cao). Vì vậy các sự kiện calipers khi quét hết các cạnh sẽ bao phủ những cặp đối cực cần thiết để đạt đường kính.

Trong trường hợp một đường đỡ chạm **một cạnh** thay vì một đỉnh, cần xét cả hai đầu mút; trường hợp hai đỉnh phía đối diện cùng độ cao phải xét nhánh tie. Đó là lý do bản pseudo-code không chỉ cập nhật một cặp tại mỗi cạnh.

## 15. Chứng minh con trỏ j quay tổng O(h)

Với một cạnh cố định của đa giác lồi CCW, diện tích có hướng của tam giác tạo bởi cạnh ấy và các đỉnh còn lại **tăng dần rồi giảm dần** theo trình tự đi quanh đa giác, nếu hiểu vùng có cùng độ cao là plateau gồm tối đa hai đỉnh kề nhau sau khi bỏ các điểm thẳng hàng trung gian.

Khi cạnh hỗ trợ xoay từ H[i]→H[i+1] tới H[i+1]→H[i+2], hướng pháp tuyến ngoài của cạnh cũng quay theo một chiều. Đỉnh cực đại của **hàm tuyến tính theo pháp tuyến** (support function) vì thế thay đổi theo **thứ tự tuần hoàn**, không phải quay ngược tùy ý.

Do đó, nếu giữ j từ cạnh trước và chỉ tăng khi cross của đỉnh tiếp theo **lớn hơn**, j sẽ gặp vị trí cực đại tương ứng của cạnh mới. Trên toàn bộ một vòng quay của các cạnh, j đi qua mỗi đỉnh tối đa một số lần hằng số, nên tổng số lần tăng **O(h)**.

Mỗi lần i tăng đúng một đơn vị, chạy h bước; ngoài vòng while, chỉ có O(1) phép cross và so khoảng cách. Tổng chi phí calipers là **O(h)**.

Phân tích này dựa vào **tính lồi và thứ tự CCW**. Nếu đưa đa giác lõm hoặc dãy đỉnh xáo trộn vào vòng calipers, hàm diện tích không còn dạng đơn đỉnh cần thiết và kết quả/cận thời gian không được bảo đảm.

## 16. Tại sao không dùng căn bậc hai để so cặp?

Cần cực đại:

~~~text
dist(a,b) = sqrt(dx²+dy²).
~~~

Vì sqrt tăng trên [0,+∞), cực đại của dist và của **distSquared** là cùng cặp. Vì vậy mã so:

~~~text
dx = a.x-b.x.
dy = a.y-b.y.
d² = dx*dx + dy*dy.
~~~

Lợi ích:

- Không cần Math.sqrt ở mỗi lần so.
- Không có việc hai khoảng cách nguyên khác nhau bị **làm tròn thành cùng một double**.
- Có thể kiểm tra chính xác tie khi bình phương khoảng cách bằng nhau.
- Cấu trúc Diameter lưu **long distanceSquared** phù hợp bài toán tối ưu.

Nếu người dùng chỉ cần giá trị khoảng cách thực cuối cùng, có thể lấy Math.sqrt((double) best.distanceSquared) **sau khi đã tìm xong cặp**. Khi đó cần chấp nhận phần biểu diễn số thực làm tròn cho kết quả hiển thị; không dùng nó để quyết định vị trí tối ưu.

## 17. Kiểm soát tràn số khi tọa độ nguyên lớn

Trong chương trình, mọi tọa độ thỏa:

~~~text
-1_000_000_000 <= x,y <= 1_000_000_000.
~~~

Do đó:

~~~text
|dx| <= 2_000_000_000.
|dy| <= 2_000_000_000.

dx² + dy² <= 8_000_000_000_000_000_000
             < Long.MAX_VALUE
             = 9_223_372_036_854_775_807.
~~~

Từng tích trong phép cross có trị tuyệt đối tối đa **4·10^18**; hiệu của hai tích có trị tuyệt đối không quá **8·10^18**, cũng nhỏ hơn Long.MAX_VALUE. Vì vậy tất cả phép cross và dist² trong code đều an toàn trên **long**, kể cả điểm ở bốn góc của hình vuông có biên ±10^9.

Ví dụ đường chéo từ (−10^9,−10^9) tới (10^9,10^9) có:

~~~text
dx=2_000_000_000.
dy=2_000_000_000.
d²=4·10^18+4·10^18
  =8_000_000_000_000_000_000.
~~~

**Không đổi phép tính trên long về int**. Giá trị 8·10^18 không thể biểu diễn bằng int. Nếu đầu bài cho tọa độ long **bất kỳ** tới ±9·10^18, ngay cả hiệu hai tọa độ cũng có thể tràn long; khi đó cần BigInteger hoặc một cách hình học số nguyên có độ rộng đủ lớn, không được sử dụng bản cài này như thể không có giới hạn.

## 18. Cách phá hòa để có một đáp án duy nhất

Một hình chữ nhật có hai đường chéo cùng độ dài. Một đa giác đều có thể có nhiều cặp đỉnh đối diện cùng đường kính.

Nếu bài chỉ hỏi giá trị lớn nhất, mọi cặp xa nhất đều là đáp án. Nhưng để tiện kiểm thử và tái hiện, bản Java quy định:

1. Trong mỗi cặp, sắp hai điểm **theo x tăng rồi y tăng**.
2. Chọn cặp có **distanceSquared lớn hơn**.
3. Nếu distanceSquared bằng nhau, chọn cặp có thứ tự từ điển **nhỏ nhất** khi so first rồi second.

~~~text
Đường chéo rectangle:
((0,0),(3,2)) có d²=13.
((0,2),(3,0)) cũng d²=13.

Cặp được chọn: ((0,0),(3,2)).
~~~

Điều này không làm thay đổi độ phức tạp: mỗi lần cập nhật ứng viên chỉ cần so vài số nguyên O(1). Quy tắc tie càng hữu ích khi oracle vét cạn và calipers được kiểm tra **bằng cả cặp điểm**, chứ không chỉ bằng khoảng cách.

## 19. Tập rỗng, một điểm, hai điểm và thẳng hàng

Không nên đưa mọi trường hợp vào vòng calipers h≥3.

**Không điểm:** không xác định khoảng cách lớn nhất giữa hai điểm. Chương trình trả Optional.empty, không giả vờ có hai điểm (0,0).

**Một điểm phân biệt:** chỉ có một vị trí. Quy ước trả cặp (p,p) với distanceSquared=0. Nếu input có nhiều bản sao cùng tọa độ, sau khử trùng vẫn là một điểm.

**Hai điểm phân biệt:** đường kính là khoảng cách giữa chúng. Không cần tính cross với ba đỉnh.

**Tất cả điểm thẳng hàng:** monotone chain loại các điểm giữa, hull chỉ gồm hai đầu mút. Ví dụ:

~~~text
(-3,-3), (-1,-1), (0,0), (5,5).
Hull=[(-3,-3),(5,5)].
Diameter² = 128.
~~~

**Điểm lặp, điểm nội bộ, điểm trên cạnh:** khử trùng hoặc loại khỏi hull. Việc loại này không làm mất một cặp có thể đạt đường kính cao hơn cặp đỉnh cực biên.

## 20. Mã Java 17+ chạy độc lập

Chương trình **RotatingCalipersDiameter.java** dùng Java record cho Point và Diameter, List và Optional. API chính:

- **convexHull(input):** trả List<Point> bất biến, gồm các đỉnh CCW của bao lồi, không lặp điểm đầu ở cuối, không giữ điểm thẳng hàng trung gian.
- **diameter(input):** trả Optional<Diameter>. Với input rỗng trả empty; với một điểm trả cặp trùng; với ≥2 điểm tìm cặp xa nhất bằng calipers sau convexHull.
- **cross:** dấu và diện tích có hướng trong long.
- **squaredDistance:** bình phương khoảng cách nguyên chính xác trong long với miền tọa độ đã chốt.
- **choose:** chọn ứng viên có d² lớn hơn, phá hòa theo thứ tự từ điển.
- **bruteDiameter:** oracle độc lập duyệt mọi cặp từ input gốc.
- **validateHull:** xác nhận hull có hướng CCW nghiêm ngặt và mọi điểm đầu vào nằm bên trong hoặc trên biên từng cạnh; xử lý riêng hull có 0,1,2 đỉnh.
- **verify:** 512 tập con của lưới 3×3, biến thể đảo input/trùng điểm, 5.000 bộ random với seed, tọa độ giới hạn và input không hợp lệ.

Hàm Point kiểm tra mỗi tọa độ thuộc [−10^9,10^9] ngay khi tạo. Nếu null list/null point, thuật toán chủ động ném IllegalArgumentException. Kết quả chứa các Point bất biến và một giá trị long bình phương khoảng cách.

Đây là chương trình **độc lập và hoàn chỉnh**, không chỉ là pseudo-code. Lưu đúng tên file tương ứng public class:

~~~java
import java.util.*;

public final class RotatingCalipersDiameter {
    private static final long LIMIT = 1_000_000_000L;
    private static final Comparator<Point> LEX =
            Comparator.comparingLong(Point::x).thenComparingLong(Point::y);

    private RotatingCalipersDiameter() {}

    public record Point(long x, long y) {
        public Point {
            if (x < -LIMIT || x > LIMIT || y < -LIMIT || y > LIMIT) {
                throw new IllegalArgumentException("coordinate outside [-10^9,10^9]");
            }
        }
    }

    public record Diameter(Point first, Point second, long distanceSquared) {}

    private static int compare(Point a, Point b) {
        return LEX.compare(a, b);
    }

    private static long cross(Point a, Point b, Point c) {
        long abx = b.x() - a.x(), aby = b.y() - a.y();
        long acx = c.x() - a.x(), acy = c.y() - a.y();
        return abx * acy - aby * acx;
    }

    private static long squaredDistance(Point a, Point b) {
        long dx = a.x() - b.x(), dy = a.y() - b.y();
        return dx * dx + dy * dy;
    }

    public static List<Point> convexHull(List<Point> input) {
        if (input == null) throw new IllegalArgumentException("null list");
        for (Point p : input) {
            if (p == null) throw new IllegalArgumentException("null point");
        }

        List<Point> sorted = new ArrayList<>(input);
        sorted.sort(LEX);
        List<Point> unique = new ArrayList<>();
        for (Point p : sorted) {
            if (unique.isEmpty() ||
                    !unique.get(unique.size() - 1).equals(p)) {
                unique.add(p);
            }
        }
        int n = unique.size();
        if (n < 2) return List.copyOf(unique);

        List<Point> lower = new ArrayList<>();
        for (Point p : unique) {
            while (lower.size() >= 2 && cross(
                    lower.get(lower.size() - 2),
                    lower.get(lower.size() - 1), p) <= 0) {
                lower.remove(lower.size() - 1);
            }
            lower.add(p);
        }

        List<Point> upper = new ArrayList<>();
        for (int i = n - 1; i >= 0; i--) {
            Point p = unique.get(i);
            while (upper.size() >= 2 && cross(
                    upper.get(upper.size() - 2),
                    upper.get(upper.size() - 1), p) <= 0) {
                upper.remove(upper.size() - 1);
            }
            upper.add(p);
        }

        lower.remove(lower.size() - 1);
        upper.remove(upper.size() - 1);
        lower.addAll(upper);
        return List.copyOf(lower);
    }

    private static Diameter choose(Diameter best, Point x, Point y) {
        Point a = x, b = y;
        if (compare(a, b) > 0) {
            a = y;
            b = x;
        }
        long distance = squaredDistance(a, b);
        if (best == null || distance > best.distanceSquared()) {
            return new Diameter(a, b, distance);
        }
        if (distance == best.distanceSquared() &&
                (compare(a, best.first()) < 0 ||
                (compare(a, best.first()) == 0 &&
                 compare(b, best.second()) < 0))) {
            return new Diameter(a, b, distance);
        }
        return best;
    }

    public static Optional<Diameter> diameter(List<Point> input) {
        List<Point> hull = convexHull(input);
        int h = hull.size();
        if (h == 0) return Optional.empty();
        if (h == 1) {
            Point p = hull.get(0);
            return Optional.of(new Diameter(p, p, 0));
        }
        if (h == 2) {
            return Optional.of(choose(null, hull.get(0), hull.get(1)));
        }

        Diameter best = null;
        int j = 1;
        for (int i = 0; i < h; i++) {
            int nextI = (i + 1) % h;
            while (cross(hull.get(i), hull.get(nextI),
                         hull.get((j + 1) % h)) >
                   cross(hull.get(i), hull.get(nextI),
                         hull.get(j))) {
                j = (j + 1) % h;
            }

            best = choose(best, hull.get(i), hull.get(j));
            best = choose(best, hull.get(nextI), hull.get(j));

            int nextJ = (j + 1) % h;
            if (cross(hull.get(i), hull.get(nextI), hull.get(nextJ)) ==
                cross(hull.get(i), hull.get(nextI), hull.get(j))) {
                best = choose(best, hull.get(i), hull.get(nextJ));
                best = choose(best, hull.get(nextI), hull.get(nextJ));
            }
        }
        return Optional.of(best);
    }

    private static Optional<Diameter> bruteDiameter(List<Point> points) {
        if (points.isEmpty()) return Optional.empty();
        Diameter best = null;
        for (Point a : points) {
            for (Point b : points) {
                best = choose(best, a, b);
            }
        }
        return Optional.of(best);
    }

    private static void validateHull(List<Point> points, List<Point> hull) {
        if (points.isEmpty()) {
            if (!hull.isEmpty()) throw new AssertionError("empty hull wrong");
            return;
        }
        if (hull.isEmpty()) throw new AssertionError("missing hull");
        for (Point vertex : hull) {
            if (!points.contains(vertex)) {
                throw new AssertionError("hull vertex not in input");
            }
        }
        int h = hull.size();
        if (h == 1) {
            for (Point p : points) {
                if (!p.equals(hull.get(0))) {
                    throw new AssertionError("one vertex hull invalid");
                }
            }
        } else if (h == 2) {
            Point a = hull.get(0), b = hull.get(1);
            if (compare(a, b) >= 0) {
                throw new AssertionError("wrong endpoint ordering");
            }
            for (Point p : points) {
                if (cross(a, b, p) != 0 ||
                    compare(p, a) < 0 || compare(p, b) > 0) {
                    throw new AssertionError("collinear hull invalid");
                }
            }
        } else {
            for (int i = 0; i < h; i++) {
                Point a = hull.get(i);
                Point b = hull.get((i + 1) % h);
                Point c = hull.get((i + 2) % h);
                if (cross(a, b, c) <= 0) {
                    throw new AssertionError("hull not strict CCW");
                }
                for (Point p : points) {
                    if (cross(a, b, p) < 0) {
                        throw new AssertionError("input outside hull");
                    }
                }
            }
        }
    }

    private static void check(List<Point> points) {
        List<Point> hull = convexHull(points);
        validateHull(points, hull);
        Optional<Diameter> actual = diameter(points);
        Optional<Diameter> expected = bruteDiameter(points);
        if (!actual.equals(expected)) {
            throw new AssertionError("diameter mismatch, input=" + points
                    + " hull=" + hull + " actual=" + actual
                    + " expected=" + expected);
        }
        if (actual.isPresent()) {
            Diameter d = actual.get();
            if (!points.contains(d.first()) ||
                    !points.contains(d.second()) ||
                    squaredDistance(d.first(), d.second()) != d.distanceSquared()) {
                throw new AssertionError("invalid endpoints");
            }
        }
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    private static void verify() {
        List<Point> grid = new ArrayList<>();
        for (long x = -1; x <= 1; x++) {
            for (long y = -1; y <= 1; y++) {
                grid.add(new Point(x, y));
            }
        }

        int subsets = 0, variants = 0;
        for (int mask = 0; mask < (1 << grid.size()); mask++) {
            List<Point> points = new ArrayList<>();
            for (int bit = 0; bit < grid.size(); bit++) {
                if ((mask & (1 << bit)) != 0) points.add(grid.get(bit));
            }
            check(points);
            variants++;
            Collections.reverse(points);
            check(points);
            variants++;
            if (!points.isEmpty()) {
                points.add(points.get(0));
            }
            check(points);
            variants++;
            subsets++;
        }

        Random random = new Random(4282026L);
        int seeded = 0;
        long[] extremes = {-LIMIT, -LIMIT + 1, -1, 0,
                            1, LIMIT - 1, LIMIT};
        for (int trial = 0; trial < 5000; trial++) {
            int n = random.nextInt(41);
            List<Point> points = new ArrayList<>();
            for (int k = 0; k < n; k++) {
                long x, y;
                if (trial % 7 == 0) {
                    x = extremes[random.nextInt(extremes.length)];
                    y = extremes[random.nextInt(extremes.length)];
                } else if (trial % 7 == 1) {
                    x = random.nextInt(2001) - 1000;
                    y = x;
                } else {
                    x = random.nextInt(2001) - 1000;
                    y = random.nextInt(2001) - 1000;
                }
                points.add(new Point(x, y));
            }
            check(points);
            seeded++;
        }

        check(List.of());
        check(List.of(new Point(7, 7)));
        check(List.of(new Point(3, 3), new Point(3, 3)));
        check(List.of(new Point(-3, -3), new Point(0, 0),
                      new Point(5, 5), new Point(-1, -1)));
        check(List.of(new Point(-LIMIT, -LIMIT),
                      new Point(-LIMIT, LIMIT),
                      new Point(LIMIT, LIMIT),
                      new Point(LIMIT, -LIMIT)));

        expectInvalid(() -> convexHull(null));
        expectInvalid(() -> diameter(Arrays.asList(new Point(0, 0), null)));
        expectInvalid(() -> new Point(LIMIT + 1, 0));
        expectInvalid(() -> new Point(0, -LIMIT - 1));

        System.out.println("Grid subsets: " + subsets + " PASS");
        System.out.println("Exhaustive order/duplicate variants: " + variants + " PASS");
        System.out.println("Seeded random point sets: " + seeded + " PASS");
        System.out.println("Hull, overflow-bound and invalid cases: PASS");
    }

    public static void main(String[] args) {
        List<Point> rectangle = List.of(
                new Point(0, 0), new Point(3, 0),
                new Point(3, 2), new Point(0, 2),
                new Point(1, 1), new Point(3, 0));
        System.out.println("Rectangle hull: " + convexHull(rectangle));
        System.out.println("Rectangle diameter: " + diameter(rectangle).orElseThrow());

        List<Point> collinear = List.of(
                new Point(-3, -3), new Point(0, 0),
                new Point(5, 5), new Point(5, 5));
        System.out.println("Collinear hull: " + convexHull(collinear));
        System.out.println("Collinear squared diameter: "
                + diameter(collinear).orElseThrow().distanceSquared());

        List<Point> extreme = List.of(
                new Point(-LIMIT, -LIMIT), new Point(LIMIT, LIMIT),
                new Point(-LIMIT, LIMIT), new Point(LIMIT, -LIMIT));
        System.out.println("Extreme squared diameter: "
                + diameter(extreme).orElseThrow().distanceSquared());
        System.out.println("Empty input: " + diameter(List.of()));
        verify();
    }
~~~

Lệnh biên dịch và chạy:

~~~bash
javac RotatingCalipersDiameter.java
java RotatingCalipersDiameter
~~~

**Stdout chính xác của phần main sau khi chạy kiểm thử thành công:**

~~~text
Rectangle hull: [Point[x=0, y=0], Point[x=3, y=0], Point[x=3, y=2], Point[x=0, y=2]]
Rectangle diameter: Diameter[first=Point[x=0, y=0], second=Point[x=3, y=2], distanceSquared=13]
Collinear hull: [Point[x=-3, y=-3], Point[x=5, y=5]]
Collinear squared diameter: 128
Extreme squared diameter: 8000000000000000000
Empty input: Optional.empty
Grid subsets: 512 PASS
Exhaustive order/duplicate variants: 1536 PASS
Seeded random point sets: 5000 PASS
Hull, overflow-bound and invalid cases: PASS
~~~

Ví dụ rectangle đã loại điểm nội bộ và trùng; collinear chỉ còn hai đầu; cực trị tọa độ cho d²=8·10^18 vẫn nằm trong long. Các dòng PASS chỉ in khi toàn bộ test tương ứng đã hoàn tất.

## 21. Phân tích tổng thời gian và bộ nhớ

Gọi n là số điểm input (bao gồm trùng), h là số đỉnh hull sau loại trùng/thẳng hàng.

| Giai đoạn | Thời gian | Bộ nhớ bổ sung |
| --- | --- | --- |
| Kiểm tra tọa độ và copy input | O(n) | O(n) |
| Sort theo x/y | O(n log n) | O(n) |
| Xóa điểm trùng | O(n) | O(n) |
| Monotone chain (lower+upper) | O(n) | O(n) |
| Rotating calipers trên h đỉnh | **O(h)** | O(1) ngoài hull |
| Tổng tìm diameter từ input | **O(n log n)** | **O(n)** |
| Vét cạn mọi cặp input | O(n²) | O(1) |

Trong trường hợp h≪n, phần calipers rất rẻ sau khi đã tính hull. Nếu một ứng dụng đã có hull CCW và cần nhiều truy vấn liên quan, có thể tái sử dụng hull thay vì sắp điểm lại.

Nếu input chỉ vài điểm, cách vét cạn có thể nhanh và ít phức tạp hơn trong thời gian thực dù có cận O(n²). Cận thời gian tốt hơn không có nghĩa luôn cần triển khai cấu trúc phức tạp cho mọi n.

## 22. Oracle và bất biến kiểm thử bao lồi

Bộ test không chỉ tự so diameter với một phép đo khác của cùng thuật toán. Nó có một **bruteDiameter độc lập** trên điểm input gốc, thử mọi cặp, không cần hull và không dùng calipers.

Đồng thời validateHull kiểm tra:

- Mọi đỉnh hull là một điểm có thật trong input.
- Với hull 0/1 đỉnh, cấu hình input tương ứng thật sự rỗng hoặc tất cả tọa độ bằng nhau.
- Với hull 2 đỉnh, tất cả điểm input thẳng hàng và nằm giữa hai đầu mút theo thứ tự từ điển.
- Với hull h≥3, mọi bộ ba đỉnh liên tiếp tạo **cross>0**; hull có hướng CCW nghiêm ngặt.
- Mọi điểm input nằm bên trái hoặc trên **mọi cạnh CCW** của hull (cross≥0).

Những kiểm tra trên đảm bảo đoạn bao của polygon là lồi và chứa tất cả điểm gốc; kết hợp đỉnh hull thuộc input cho thấy đó chính là bao lồi. Đồng thời, vì oracle duyệt mọi cặp input, lỗi bỏ mất điểm ứng viên sẽ lộ khi calipers trả cặp hoặc khoảng cách sai.

Khi so kết quả, bộ kiểm thử so **cả Optional<Diameter>** gồm hai đầu mút theo quy tắc phá hòa và distanceSquared, không chỉ so số d².

## 23. Kiểm thử vét cạn 512 tập con lưới 3×3

Xét lưới tọa độ nguyên:

~~~text
x ∈ {-1,0,1}.
y ∈ {-1,0,1}.

Tổng 9 điểm phân biệt.
~~~

Mỗi điểm được chọn hoặc bỏ, nên có:

~~~text
2^9 = 512 tập con.
~~~

Mỗi tập con thử ba biến thể:

1. Thứ tự chọn điểm ban đầu.
2. **Đảo ngược** toàn bộ thứ tự input.
3. Sau khi đảo, **thêm một bản sao của điểm đầu** nếu danh sách không rỗng.

Tổng:

~~~text
512*3 = 1536 biến thể input.
~~~

Mọi biến thể đều được chạy validateHull và so **diameter** với bruteDiameter. Tập này bao phủ rỗng, một điểm, hai điểm, nhiều điểm thẳng hàng, tam giác, tứ giác lồi, điểm trong, cạnh song song, cặp đường kính bằng nhau, thứ tự input đảo và điểm lặp.

Số 512 là số tập con **không phân biệt thứ tự**; số 1.536 là tổng lần chạy các biến thể có kiểm tra. Không nhân nhầm thành số cấu hình hình học độc lập.

## 24. Kiểm thử 5.000 tập điểm random có seed

Chương trình dùng **Random(4282026L)** tạo 5.000 tập input, mỗi tập có số điểm n ngẫu nhiên từ 0 tới 40. Các dạng được luân phiên:

- Một phần có tọa độ chọn từ các giá trị biên **−10^9, −10^9+1, −1, 0, 1, 10^9−1, 10^9**; giúp thử cross và dist² rất lớn.
- Một phần tạo các điểm trên đường thẳng y=x, cố ý có cấu hình suy biến.
- Phần còn lại lấy tọa độ nguyên ngẫu nhiên trong [−1000,1000] để tạo các polygon nhiều góc.

Mỗi tập được kiểm tra **hull CCW/bao chứa toàn bộ input**, sau đó so cặp đường kính từ calipers với kết quả brute-force. Với n≤40, oracle O(n²) còn đủ nhanh; sự độc lập của oracle quan trọng hơn tốc độ.

Bộ test cũng thử riêng input rỗng, một điểm, nhiều bản sao cùng điểm, collinear, bốn góc ±10^9 và đối số không hợp lệ (null list, null point, tọa độ ngoài giới hạn). Toàn bộ các trường hợp này đã trả PASS trong bản chạy Java.

## 25. Sai lầm phổ biến và cách tránh

1. **Duyệt mọi cặp input** rồi gọi đó là rotating calipers: đây vẫn là O(n²), chưa khai thác hình học.
2. **Không tính bao lồi trước:** điểm nội bộ làm hỏng tính đơn điệu của con trỏ j.
3. **Đưa hull chưa sắp CCW** vào thuật toán; so cross có thể đổi dấu không kiểm soát.
4. **Để trùng đỉnh đầu ở cuối hull**, tạo cạnh độ dài 0 làm sai bất biến.
5. **Giữ nhiều điểm thẳng hàng trung gian** nhưng dùng phiên bản xử lý plateau chỉ dành cho hull nghiêm ngặt.
6. **Dùng cross<0 thay vì cross≤0** trong monotone chain khi muốn loại các điểm giữa.
7. **Lấy trị tuyệt đối cross không cần thiết** trên hull CCW, che giấu lỗi hướng polygon.
8. **Tính cross bằng int** khi tọa độ tới 10^9; phép nhân có thể tràn.
9. **Tính dx*dx bằng int rồi ép sang long**; đã quá muộn để tránh tràn.
10. **Dùng long với tọa độ long tùy ý không kiểm chứng cận**, ngay cả phép trừ tọa độ có thể tràn.
11. **Lấy sqrt trước để so cặp**, gây mất chính xác khi tie hoặc khoảng cách lớn.
12. **Reset j về 0 ở mỗi cạnh**, có thể biến O(h) thành O(h²).
13. **Chỉ xét cặp (i,j)**, bỏ các ứng viên gắn với đầu i+1.
14. **Bỏ nhánh equal-area** khi hai đỉnh phía đối diện có cùng độ cao.
15. **Dùng điều kiện >= trong while mà không hiểu plateau**; có thể bỏ một ứng viên cần xét.
16. **Cho j quay vô hạn** nếu không có tính lồi hoặc dữ liệu lẫn điểm sai thứ tự.
17. **Nhầm cực đại khoảng cách với cực đại diện tích tam giác**; cross chỉ là tín hiệu để tiến j, không phải đại lượng tối ưu cuối.
18. **Nhầm diameter với chiều rộng tối thiểu**; đây là hai bài calipers khác nhau.
19. **Cho rằng hai điểm có x xa nhau nhất luôn xa nhất theo Euclid**; đường chéo có thể dài hơn.
20. **Không xử lý input rỗng, một điểm, hai điểm** trước vòng h≥3.
21. **Quên điểm trùng hoặc collinear**, gây đỉnh sai/độ dài sai.
22. **Chỉ so giá trị d² mà bỏ cặp đầu mút** khi test quy tắc tie.
23. **Không kiểm tra hull chứa tất cả điểm**, có thể tính đúng trên hull sai một cách ngẫu nhiên.
24. **Thay đổi quy tắc tie mà không đổi oracle**, tạo false alarm trong kiểm thử.
25. **Nhầm tổng O(h) với O(n)** khi chưa tính chi phí xây hull O(n log n).
26. **So khoảng cách bằng double** rồi tin rằng hoàn toàn chính xác ở các tọa độ biên.
27. **Không áp dụng modulo h khi lấy i+1 hoặc j+1**, truy cập vượt mảng.
28. **Không giới hạn tọa độ**, nhưng vẫn tuyên bố không có overflow.

## 26. Bài tập tự luyện

**Bài 1 — Hull hình chữ nhật:** cho các điểm (0,0),(3,0),(3,2),(0,2),(1,1) và một điểm (3,0) trùng. Dựng hull CCW và tính đường kính bình phương.

**Bài 2 — Cross:** tính cross((0,0),(3,0),(3,2)) và cross((0,0),(3,0),(0,2)). Vì sao cả hai bằng 6 và liên quan đến nhánh tie?

**Bài 3 — Cặp xa nhất:** chứng minh điểm cực đại của khoảng cách tới một điểm cố định có thể chọn là đỉnh hull bằng tính lồi của bình phương khoảng cách.

**Bài 4 — Monotone chain:** sắp các điểm (−3,−3),(−1,−1),(0,0),(5,5), theo dõi lower/upper và giải thích vì sao giữ hai đầu mút.

**Bài 5 — Vết calipers:** chạy tay i và j trên hull hình chữ nhật, ghi diện tích cross, các ứng viên xét và best sau mỗi cạnh.

**Bài 6 — Tie:** cho hình vuông có hai đường chéo bằng nhau. Đề xuất một quy tắc chọn cặp xác định và cài hàm choose tương ứng.

**Bài 7 — Trường hợp suy biến:** thiết kế đầu vào rỗng, một điểm, hai điểm, all-collinear, mọi điểm trùng; mô tả kết quả mong đợi cho từng trường hợp.

**Bài 8 — Tràn số:** với tọa độ ±10^9, chứng minh dx²+dy²≤8·10^18<Long.MAX_VALUE và cross theo công thức chương trình không vượt long.

**Bài 9 — Vét cạn:** sinh mọi tập con của lưới 3×3, so diameter từ calipers với brute-force trên input gốc.

**Bài 10 — Oracle hull:** kiểm tra mọi bộ ba đỉnh liên tiếp có cross>0 và mọi điểm input nằm bên trái mỗi cạnh CCW. Vì sao các bất biến này củng cố tính đúng?

**Bài 11 — So sánh thuật toán:** chạy thử dữ liệu n=50,500,5000 theo cả brute-force và hull+calipers, ghi thời gian và quan sát sự khác biệt.

**Bài 12 — Tọa độ rất lớn:** nếu tọa độ được phép tới Long.MAX_VALUE, hãy thay cross/dist² bằng BigInteger và phân tích chi phí số học đa độ chính xác.

**Bài 13 — Bài toán khác:** tìm **chiều rộng tối thiểu** hoặc **hình chữ nhật bao nhỏ nhất** của polygon lồi. Đánh dấu những phần có thể tái sử dụng từ rotating calipers và những bất biến mới cần chứng minh.

**Bài 14 — Đếm cặp đường kính:** nếu đề yêu cầu tất cả cặp đạt cực đại, không chỉ một cặp phá hòa, hãy bổ sung cơ chế thu tất cả sự kiện đối cực và xử lý tie bằng tập cặp không trùng.

## 27. Tổng kết: khi nào chọn rotating calipers?

Nếu bài yêu cầu **đường kính Euclid của một tập điểm trong mặt phẳng**, chiến lược tiêu chuẩn là:

~~~text
Điểm đầu vào (có thể trùng)
    ↓ Sắp theo tọa độ
Bao lồi CCW không giữ điểm thẳng hàng trung gian
    ↓ Duyệt cạnh i và đỉnh đối cực j quay một chiều
Các cặp ứng viên tại sự kiện calipers
    ↓ So bình phương khoảng cách nguyên chính xác
Một cặp đường kính và khoảng cách bình phương lớn nhất
~~~

Phần sắp và dựng hull tốn **O(n log n)**, trong khi calipers chỉ **O(h)**. Mỗi bước tăng j dựa trên việc **cross của đỉnh kế lớn hơn**, còn kết quả tối ưu dựa trên **bình phương khoảng cách**. Hai đại lượng không được nhầm cho nhau. Khi độ cao bằng nhau, xét thêm ứng viên bên cạnh để bảo toàn các tình huống cặp đối cực gắn với cạnh song song.

**Điểm ghi nhớ:** không phải mọi cặp điểm đều cần duyệt; cặp xa nhất có thể chọn trên bao lồi, và những cặp cần xét phát sinh từ chuyển động đơn điệu của các đường đỡ song song. Cần giữ đúng hướng CCW, loại trùng/thẳng hàng trung gian, xử lý số điểm nhỏ và chứng minh an toàn overflow cho miền tọa độ đã chọn. Với các điều kiện ấy, **hull + rotating calipers** là một lời giải O(n log n) chính xác, mạnh và dễ dùng lại cho hình học tính toán.
