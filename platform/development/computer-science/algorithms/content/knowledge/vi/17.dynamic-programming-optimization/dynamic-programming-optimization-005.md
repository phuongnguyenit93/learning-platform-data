# Dùng biểu thức đại số để tách phần phụ thuộc từng chỉ số

Trong **tối ưu quy hoạch động (DP optimization)**, một công thức chuyển có thể trông như buộc phải duyệt toàn bộ trạng thái trước đó để tính mỗi dp[i]. Nhưng rất nhiều công thức chứa các thành phần có thể **tách theo chỉ số hiện tại i và chỉ số chuyển từ j**. Biến đổi đại số đúng cách sẽ giúp ta thay một vòng lặp xét mọi j bằng **một giá trị cực trị duy trì sẵn**, hoặc biến bài toán thành **truy vấn giá trị nhỏ nhất của các đường thẳng**.

Trọng tâm của bài học là nhận dạng **phần chỉ phụ thuộc i**, **phần chỉ phụ thuộc j**, và **phần tương tác giữa i và j**, sau đó chọn cấu trúc dữ liệu thích hợp. Đây là kỹ thuật rất thực tế trong nhóm **Tối ưu quy hoạch động**: từ O(n²) có thể giảm xuống O(n), O(n log n) hoặc mức khác, **nhưng chỉ khi đẳng thức biến đổi bảo toàn đúng mọi ứng viên và điều kiện chọn j**.

Ta sẽ đi qua hai mẫu hoàn chỉnh: (1) chi phí tuyến tính theo khoảng cách chỉ số, rút về **prefix minimum** và O(n); (2) chi phí bình phương chênh lệch tọa độ, rút về **các hàm tuyến tính** và cấu trúc Li Chao cho O(n log n). Mỗi mẫu có chứng minh, ví dụ tính tay, Java 17+ chạy được và kiểm thử độc lập với phiên bản DP vét cạn.

## 1. Nút thắt thực sự của một công thức chuyển DP

Xét một họ trạng thái theo thứ tự 0,1,...,n:

~~~text
dp[0] = 0
dp[i] = min_{0 <= j < i} (dp[j] + cost(i,j)), i = 1..n.
~~~

Có n+1 trạng thái. Nếu mỗi dp[i] thử toàn bộ i chỉ số j trước đó, số ứng viên cần xét là:

~~~text
1 + 2 + ... + n = n(n+1)/2 = Θ(n²).
~~~

Khi mỗi ứng viên được tính O(1), thuật toán trực tiếp mất **Θ(n²) thời gian**, dù bảng kết quả chỉ cần O(n) bộ nhớ. Đó là hai đại lượng khác nhau: **số trạng thái** và **chi phí chuyển trên mỗi trạng thái**.

Trước khi tối ưu, phải xác định:

- Tập j hợp lệ có đúng là 0≤j<i, hay còn điều kiện khác (cửa sổ, thứ tự, trọng số, phân nhóm)?
- dp[j] đã được tính xong ở lúc tính dp[i] chưa?
- Công thức cost(i,j) có tách được theo i và j không?
- Có cần biết **giá trị tối ưu** hay còn cần **chỉ số j tối ưu** để truy vết?
- Số học là số nguyên chính xác, modulo hay số thực, và có khả năng tràn số không?

Tối ưu **không được thay đổi tập ứng viên hợp lệ**. Nếu phép biến đổi vô tình cho phép dùng j=i, hoặc dùng một trạng thái tương lai j>i, ta đã giải một bài toán khác.

## 2. Khuôn tách đại số: một phần của i và một phần của j

Giả sử chi phí chuyển có dạng:

~~~text
cost(i,j) = A(i) + B(j).
~~~

Khi đó:

~~~text
dp[i]
 = min_{j<i} (dp[j] + A(i) + B(j))
 = A(i) + min_{j<i} (dp[j] + B(j)).
~~~

Vì A(i) **không phụ thuộc j**, ta có thể kéo nó ra ngoài phép min. Gọi:

~~~text
bestBefore(i) = min_{0<=j<i} (dp[j] + B(j)).
~~~

Ta chỉ cần tính dp[i] = A(i) + bestBefore(i). Sau khi tính xong dp[i], cập nhật best cho lượt tiếp:

~~~text
bestBefore(i+1) = min(bestBefore(i), dp[i] + B(i)).
~~~

Thay vì duyệt i ứng viên ở lượt i, mỗi lượt chỉ còn một phép đọc best và một phép cập nhật min. Tổng có thể là **O(n)** thời gian.

Đây không phải “mẹo lập trình” không có cơ sở: phép biến đổi dựa vào tính chất của phép min và hạng tử hằng theo j. Điều kiện cần kiểm tra là **tập j được mở rộng đúng một phần tử** khi i tăng, và không có phần tử cũ phải bị loại bỏ.

## 3. Ví dụ tuyến tính: chi phí phụ thuộc khoảng cách i−j

Cho một bảng chi phí bắt đầu chuyển startPenalty[0..n] và một hằng số rate. Đặt:

~~~text
dp[0] = 0.
dp[i] = min_{0<=j<i} {
           dp[j] + startPenalty[j] + rate*(i-j)
        }, với i=1..n.
~~~

Có thể hiểu dp[i] là chi phí ít nhất để đến mốc i nếu lần chuyển cuối bắt đầu từ một mốc j<i; ta trả chi phí đã có dp[j], một phụ phí tại mốc xuất phát startPenalty[j], và chi phí tuyến tính theo độ dài bước nhảy rate*(i−j).

Trong bài học, rate và penalty được phép âm để làm rõ **phép biến đổi đại số không phụ thuộc vào điều kiện chi phí không âm**. Vì mọi chuyển đều đi từ chỉ số nhỏ hơn tới lớn hơn, đồ thị phụ thuộc không có chu trình; số bước chuyển hữu hạn. Nếu muốn mô hình chi phí thực tế luôn không âm, có thể bổ sung giới hạn riêng.

Mảng startPenalty có n+1 phần tử, nhưng startPenalty[n] **không được dùng để tính dp[n]**, vì không có chuyển đi từ n tới trạng thái nào lớn hơn trong miền đang xét. Hiện thực tối ưu sẽ không tính ứng viên mới từ n sau khi đã có kết quả cuối.

Bản trực tiếp có n trạng thái cần tính; với mỗi i thử j từ 0 tới i−1. Thời gian Θ(n²), bộ nhớ O(n).

## 4. Tách biểu thức tuyến tính và đặt đại lượng cần duy trì

Khai triển hạng tử khoảng cách:

~~~text
dp[j] + startPenalty[j] + rate*(i-j)

= rate*i + (dp[j] + startPenalty[j] - rate*j).
~~~

Đặt:

~~~text
key[j] = dp[j] + startPenalty[j] - rate*j.

bestBefore(i) = min_{0<=j<i} key[j].
~~~

Suy ra:

~~~text
dp[i] = rate*i + bestBefore(i).
~~~

Với dp[0]=0, ban đầu:

~~~text
bestBefore(1) = key[0] = startPenalty[0].
~~~

Tại lượt i, dùng best của các j<i để tính dp[i]. Sau đó **nếu còn lượt tiếp**, tính key[i] rồi cập nhật best. Nếu cập nhật key[i] trước khi tính dp[i], sẽ cho phép j=i; với rate=0 và penalty âm, chuyển giả đó có thể thay đổi kết quả.

Công thức sau khi tách chứa đúng **một số hạng phụ thuộc i** và **một cực trị tích lũy phụ thuộc các j đã hoàn tất**. Đây là trường hợp dễ nhất và mạnh nhất của tối ưu bằng biểu thức đại số.

## 5. Bất biến vòng lặp: vì sao prefix minimum là đúng?

Tại **đầu lượt i**, duy trì bất biến:

~~~text
best = min_{0<=j<i} (dp[j] + startPenalty[j] - rate*j).
~~~

**Khởi tạo:** ở lượt i=1 chỉ có j=0; best=startPenalty[0] vì dp[0]=0.

**Duy trì:** giả sử bất biến đúng. Dùng công thức đã biến đổi:

~~~text
dp[i] = rate*i + best
~~~

cho đúng min trên mọi j<i. Sau đó, nếu i<n, thêm key[i] vào tập ứng viên cho lượt i+1:

~~~text
best = min(best, dp[i] + startPenalty[i] - rate*i).
~~~

Vậy best mới đúng bằng min trên 0≤j≤i, chính là bất biến của lượt tiếp.

**Kết thúc:** sau lượt n, dp[n] đã đúng; không cần thêm key[n]. Như vậy chỉ số trước–sau được kiểm soát chặt chẽ, không cần lưu từng giá trị key[j] riêng nếu chỉ muốn chi phí.

Chứng minh này gồm **đẳng thức của công thức chuyển** và **bất biến về tập ứng viên**. Chỉ có một trong hai là chưa đủ để chứng minh thuật toán tối ưu đúng.

## 6. Tính tay một ví dụ chi phí tuyến tính

Chọn:

~~~text
rate = 3
startPenalty = [8, -4, 7, -5, 3, 0]
n = 5
dp[0] = 0
~~~

Ta có key[0] = 8. Diễn biến:

| i | best trước lượt | rate×i | dp[i] = rate×i + best | key[i] (nếu còn lượt) | best sau cập nhật |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8 | 3 | 11 | 11−4−3 = 4 | 4 |
| 2 | 4 | 6 | 10 | 10+7−6 = 11 | 4 |
| 3 | 4 | 9 | 13 | 13−5−9 = −1 | −1 |
| 4 | −1 | 12 | 11 | 11+3−12 = 2 | −1 |
| 5 | −1 | 15 | 14 | Không cần | −1 |

Do đó:

~~~text
dp = [0, 11, 10, 13, 11, 14].
~~~

Để đối chiếu dp[4] theo cách trực tiếp, xét j=0..3. Ứng viên từ j=3 có chi phí dp[3]+startPenalty[3]+3*(4−3)=13−5+3=11. Các ứng viên khác không nhỏ hơn 11, nên kết quả đúng là dp[4]=11.

**Điều thú vị:** dp[i] không bắt buộc tăng khi i tăng; ở ví dụ này dp[4]=11 nhỏ hơn dp[3]=13. Việc dùng một cực trị prefix **không đòi dp phải đơn điệu**, chỉ đòi tập các j hợp lệ là prefix tăng dần.

## 7. Độ phức tạp của mẫu tách hoàn toàn

Bản trực tiếp:

- n+1 trạng thái dp.
- Θ(n²) lượt xét ứng viên j.
- O(n) bộ nhớ cho kết quả dp.

Bản tối ưu:

- n lượt tính dp[i], mỗi lượt O(1) phép toán số nguyên.
- O(n) thời gian để trả toàn bộ dp[0..n].
- O(n) bộ nhớ cho mảng kết quả.
- Nếu chỉ cần dp[n], có thể giữ trạng thái cuối và best trong O(1) **bộ nhớ làm việc**, với điều kiện bài toán không cần xuất toàn bộ bảng hoặc truy vết.

Nếu phải trả về **mốc j được chọn** ở mỗi i, hãy lưu cả argmin tương ứng với best. Khi một key mới nhỏ hơn best, cập nhật cả giá trị min và chỉ số j. Quy tắc xử lý hòa (giữ chỉ số sớm hơn hay mới hơn) phải căn theo đặc tả; nếu chỉ yêu cầu một lời giải tối ưu bất kỳ thì cả hai có thể hợp lệ.

Không nên dùng trực tiếp công thức mới trong mọi bài có i−j: nếu cost còn chứa phần phi tuyến hoặc phụ thuộc cả i và j mà không tách được, best một số duy nhất có thể không đủ.

## 8. Khi tập j không còn là toàn bộ prefix

Giả sử một công thức chỉ cho phép j trong đoạn [i−K, i−1]. Sau khi tách:

~~~text
dp[i] = A(i) + min_{max(0,i-K)<=j<i} B'(j),
với B'(j) = dp[j] + B(j).
~~~

Lúc này một ứng viên cũ sẽ **hết hạn** khi i tăng, nên không thể duy trì một minimum prefix đơn giản: giá trị nhỏ nhất toàn bộ quá khứ có thể thuộc một j không còn hợp lệ.

Cấu trúc phù hợp thường là **deque đơn điệu** để giữ cực trị trên một cửa sổ trượt, nếu ứng viên được thêm theo thứ tự chỉ số và xóa từ đầu cửa sổ. Mỗi chỉ số thường được thêm/xóa không quá một lần, cho thời gian O(n).

Nếu tập j hợp lệ theo nhiều khoảng không liên tục hoặc có thao tác thêm/xóa tùy ý, có thể cần **segment tree, balanced tree hoặc cấu trúc khác**. **Bước tách đại số vẫn đúng**, nhưng cách duy trì tập ứng viên phải phản ánh đúng ràng buộc ban đầu.

Đừng đánh đồng “đã tách được A(i)+B(j)” với “chắc chắn O(n)” khi miền j phức tạp. Mức tăng tốc là kết quả kết hợp giữa **đẳng thức đại số và cấu trúc của tập chỉ số hợp lệ**.

## 9. Khi hạng tử là tích của một phần i và một phần j

Một lớp biểu thức rộng hơn là:

~~~text
dp[i] = A(i) + min_{j<i} {
           U(i)*V(j) + W(j)
        }.
~~~

Nếu U(i) là một biến x, mỗi j xác định một **đường thẳng** theo x:

~~~text
line_j(x) = V(j)*x + W(j).
dp[i] = A(i) + min_{j<i} line_j(U(i)).
~~~

Đối với U(i) thay đổi theo i, ta không thể dùng một giá trị best cố định; **đường nào nhỏ nhất phụ thuộc vào điểm truy vấn x=U(i)**. Ví dụ hai đường có thể giao nhau: đường thắng khi x nhỏ có thể thua khi x lớn.

Khi V(j) có dạng đặc biệt và U(i) theo thứ tự đơn điệu, có thể cân nhắc **Convex Hull Trick (CHT)** với deque. Với truy vấn x không đơn điệu hoặc các đường được thêm không theo thứ tự slope thuận tiện, cấu trúc **Li Chao tree** là một lựa chọn thường dễ áp dụng hơn, với O(log M) cho mỗi lần chèn/truy vấn trên miền M tọa độ rời rạc.

Đây là ý nghĩa then chốt của việc tách biến: **biến một vòng thử mọi j thành một bài toán dữ liệu đã biết** — query giá trị nhỏ nhất của tập đường thẳng.

## 10. Ví dụ bình phương: dp[i] dựa trên chênh lệch tọa độ

Cho dãy tọa độ x[0..n], không nhất thiết tăng dần, và chi phí cố định fee cho mỗi lần chuyển. Đặt:

~~~text
dp[0] = 0.

dp[i] = min_{0<=j<i} {
           dp[j] + (x[i] - x[j])^2 + fee
        }, i = 1..n.
~~~

Mỗi bước chuyển từ một mốc j<i tới i trả tổng chi phí đã có, bình phương chênh lệch tọa độ và fee. Có thể cho fee âm; vì chỉ có cạnh j<i, công thức vẫn có thứ tự phụ thuộc hợp lệ, không có chu trình giữa các trạng thái.

Bản trực tiếp có n(n+1)/2 ứng viên, thời gian Θ(n²). Trong nhiều bài toán phân đoạn theo tổng tiền tố, tọa độ x[i] chính là tổng tiền tố S[i]. Nếu các phần tử gốc có thể âm, S[i] **không nhất thiết tăng**. Vì thế chọn một kỹ thuật đòi x đơn điệu mà chưa kiểm tra giả thiết có thể dẫn tới sai kết quả.

Mục tiêu của bước tối ưu là giảm thời gian xử lý min trên j, **không đổi ý nghĩa dp[i]** và không thay thế điều kiện j<i.

## 11. Khai triển bình phương để xuất hiện đường thẳng

Áp dụng hằng đẳng thức:

~~~text
(x[i] - x[j])^2 = x[i]^2 - 2*x[i]*x[j] + x[j]^2.
~~~

Thay vào công thức:

~~~text
dp[i]
= min_{j<i} {
      dp[j] + x[i]^2 - 2*x[i]*x[j] + x[j]^2 + fee
  }

= x[i]^2 + fee
  + min_{j<i} {
      (-2*x[j])*x[i] + (dp[j] + x[j]^2)
    }.
~~~

Định nghĩa cho mỗi trạng thái j đã tính xong:

~~~text
m_j = -2*x[j]                        (slope)
b_j = dp[j] + x[j]^2                 (intercept)
line_j(t) = m_j*t + b_j.
~~~

Khi tính dp[i], đặt t=x[i] và hỏi:

~~~text
bestLine = min_{0<=j<i} line_j(x[i]).
dp[i] = x[i]^2 + fee + bestLine.
~~~

Vậy bài toán DP đã chuyển từ duyệt O(i) trạng thái j thành **truy vấn min của các hàm tuyến tính**. Đây là một biến đổi đại số **chính xác** trên số nguyên toán học, không phải xấp xỉ bình phương.

Điều kiện bắt buộc: **chỉ chèn line_j sau khi biết dp[j]**, và khi tính dp[i] chỉ truy vấn những line đã chèn từ j<i. Nếu chèn line_i trước khi query, có thể chọn chính trạng thái hiện tại và tạo vòng phụ thuộc vô nghĩa.

## 12. Tính tay ví dụ bình phương và đường thẳng

Chọn:

~~~text
x = [0, 3, 1, 4]
fee = 2
dp[0] = 0
~~~

Bước i=1, x[1]=3:

- Chỉ có j=0: dp[1]=0+(3−0)²+2=11.
- Line của j=0 là m=0, b=0, tức line_0(t)=0.
- Sau khi tính dp[1], thêm line_1(t)=−6t+20 vì m_1=−2×3=−6, b_1=11+3²=20.

Bước i=2, x[2]=1:

- line_0(1)=0, line_1(1)=14 → bestLine=0.
- dp[2]=1²+2+0=3.
- Thêm line_2(t)=−2t+4.

Bước i=3, x[3]=4:

- line_0(4)=0.
- line_1(4)=−24+20=−4.
- line_2(4)=−8+4=−4.
- bestLine=−4; dp[3]=4²+2−4=14.

Kết quả:

~~~text
dp = [0, 11, 3, 14].
~~~

Ở bước cuối có **hai điểm xuất phát j=1 hoặc j=2 cùng cho chi phí 14**. Nếu đề chỉ yêu cầu chi phí, không cần phân biệt. Nếu phải dựng chuỗi điểm chuyển, cấu trúc dữ liệu cần giữ thêm ID của đường để biết j nào được chọn, và phải định nghĩa rõ quy tắc hòa.

Ví dụ x không tăng: x đi 0→3→1→4. Vì vậy đây cũng là một phép thử chống lại việc vô tình giả định truy vấn tới hull luôn có x tăng dần.

## 13. Trừu tượng hóa bài toán thành thêm đường và hỏi min

Sau biến đổi, thuật toán tối ưu có dạng:

~~~text
chèn line_0(t) = -2*x[0]*t + dp[0] + x[0]^2

for i = 1..n:
    best = min_line_value_at(x[i])
    dp[i] = x[i]^2 + fee + best
    nếu i < n:
        chèn line_i(t) = -2*x[i]*t + dp[i] + x[i]^2
~~~

Công thức này có một **bất biến trạng thái** rất rõ:

> Ngay trước truy vấn ở i, cấu trúc chứa đúng các đường line_j cho j=0,1,...,i−1, và giá trị thấp nhất của chúng tại x[i] bằng min của phần phụ thuộc j trong công thức DP.

**Cơ sở:** trước i=1, chỉ có line_0, đúng với j<1.  
**Bước quy nạp:** query trên tập j<i cho đúng cực tiểu. Từ đó tính được dp[i]; nếu còn bước tiếp theo, thêm line_i làm tập thành j≤i, đúng với lượt i+1.

Bất biến trên độc lập với cách cài đặt cấu trúc: Li Chao, segment tree các đường hay CHT chỉ là các cách hỗ trợ **cùng hai thao tác** addLine và queryMin.

Phải phân biệt **thứ tự thời gian thêm đường** (theo i) với **thứ tự tọa độ x** (có thể tùy ý). Bản Java dùng nén tọa độ truy vấn trước để tổ chức cây, nhưng việc chèn line vẫn tuân theo thứ tự i để không dùng trạng thái tương lai.

## 14. Li Chao tree rời rạc hoạt động như thế nào?

Với mọi tọa độ x[i] sẽ được query đã biết từ đầu, ta có thể:

1. Sao chép toàn bộ x[0..n], sắp xếp và loại tọa độ trùng; được m tọa độ phân biệt tăng dần.
2. Dựng **Li Chao tree rời rạc** trên các vị trí 0..m−1. Các tọa độ gốc có thể âm, trùng hoặc không theo thứ tự thời gian; cây chỉ cần biết **trật tự giá trị x**.
3. Với mỗi đường mới f(t)=mt+b, so sánh với đường hiện có tại **đầu trái** và **điểm giữa** của một đoạn cây; giữ đường tốt hơn ở giữa, đẩy đường còn lại xuống đúng nhánh có thể còn tốt hơn.
4. Với một truy vấn tại tọa độ t trong tập đã nén, xét các đường lưu ở những nút trên đường từ gốc tới lá tương ứng và lấy min.

Cơ sở đúng đắn: **hiệu của hai đường thẳng là hàm bậc nhất**, nên đổi dấu nhiều nhất một lần trên trục số. Sau khi giữ đường tốt hơn tại điểm giữa, phần còn lại chỉ có thể cần xét tiếp **một nửa** đoạn. Đây là lý do phép chèn không phải thăm mọi lá.

Ở mỗi lần thêm đường, số mức cây O(log m); với mỗi query theo một tọa độ, số nút từ gốc tới lá cũng O(log m). Trên miền m≤n+1 tọa độ phân biệt, quá trình có **O(n log n) thời gian** gồm cả nén tọa độ, thêm đường và truy vấn, và **O(n) bộ nhớ** cho tọa độ, DP và cây.

**Đường bằng nhau/hòa:** việc chỉ thay khi giá trị mới nhỏ hơn (không bắt buộc thay khi bằng nhau) vẫn bảo toàn **giá trị minimum**, nhưng có thể cho cách lựa chọn ID khác. Mã trong bài chỉ trả mảng chi phí, không tự nhận là khôi phục được điểm xuất phát tối ưu khi hòa.

## 15. Vì sao nén tọa độ không làm sai thứ tự trạng thái?

Nén tọa độ ở đây **không sắp xếp lại các trạng thái DP**. Mảng x ban đầu được giữ nguyên; i vẫn chạy từ 1 tới n và j vẫn phải nhỏ hơn i.

Ví dụ x = [4,4,4] có ba trạng thái thời gian nhưng chỉ **một tọa độ truy vấn** sau nén. Dù ba giá trị x bằng nhau, dp[1] và dp[2] vẫn là hai trạng thái khác nhau; không được gộp các trạng thái DP chỉ vì cùng tọa độ. Cây có thể lưu các đường được thêm từ nhiều chỉ số cùng x, và query lấy giá trị min.

Sự khác biệt:

- **Nén tọa độ:** gom các giá trị x giống nhau thành một vị trí để tra cứu cấu trúc, không xóa bước thời gian.
- **Gộp trạng thái DP:** khẳng định hai bộ tham số cho cùng lời giải con, phải có chứng minh riêng; không thể chỉ dựa vào cùng x[i].

Với fee=0 và x=[4,4,4], mọi lần chuyển giữa tọa độ bằng nhau có chi phí bình phương 0, nên dp=[0,0,0]. Đây là ca biên rất tốt để kiểm tra thuật toán không đếm nhầm số trạng thái hay truy vấn tại tọa độ nén bị trùng.

## 16. So sánh CHT, Li Chao và duy trì cực trị một số

| Dạng biểu thức | Cấu trúc phù hợp | Giả thiết đáng kiểm tra | Thời gian điển hình |
| --- | --- | --- | --- |
| A(i) + min B(j), j<i | Một running minimum | Không xóa ứng viên cũ; mỗi j chỉ thêm một lần | O(n) |
| A(i) + min B(j), j trong cửa sổ | Monotonic deque | Cửa sổ trượt và ứng viên theo thứ tự | O(n) |
| A(i) + min [U(i)V(j)+W(j)] | Convex Hull Trick | Thứ tự slope/query, xử lý slope trùng và các phép so sánh | Có thể O(n) hoặc O(n log n) tùy biến thể |
| Cùng dạng tuyến tính, x query bất kỳ | Li Chao tree | Hàm là đường thẳng, miền truy vấn được xác định | O(n log M) |
| Tập ứng viên thêm/xóa phức tạp | Cấu trúc dữ liệu động khác | Ràng buộc loại bỏ, thứ tự, miền truy vấn | Tùy bài |

Không phải cứ thấy x² là tự động chạy Li Chao. Phải thật sự khai triển được công thức thành **hằng theo i + hàm tuyến tính theo x[i] của từng j**. Nếu cost còn có hệ số phụ thuộc đồng thời vào i,j không tách được, các đường định nghĩa từ j có thể không còn cố định qua mọi i.

Một số bài DP có thể dùng **divide-and-conquer optimization, Knuth optimization hoặc Monge** thay vì line hull, nhưng chỉ khi có điều kiện toán học đặc thù. Tên “DP optimization” không phải giấy phép áp đặt một cận O(n log n) cho mọi công thức có min.

## 17. Java 17+ hoàn chỉnh, gồm hai bản tối ưu và hai bản đối chiếu

Chương trình **AlgebraicDpOptimization.java** trình bày bốn hàm:

- **linearBrute:** duyệt j<i đúng công thức chi phí tuyến tính, Θ(n²).
- **linearFast:** tách rate×i và duy trì minimum của phần theo j, O(n).
- **quadraticBrute:** duyệt j<i với chi phí bình phương, Θ(n²).
- **quadraticFast:** khai triển bình phương và dùng Li Chao rời rạc, O(n log n).

Cả bốn đều trả **mảng long[] đầy đủ gồm dp[0..n]**, không sửa mảng đầu vào. Đầu vào phải khác null và chứa ít nhất một phần tử cho trạng thái 0; mảng chỉ có một phần tử là trường hợp n=0, trả [0].

Hai biến thể fast dùng **cùng công thức toán học** với brute và chỉ khác cách tìm cực trị qua j. Java dùng Math.addExact, Math.subtractExact, Math.multiplyExact nhằm từ chối tình huống phép tính trung gian vượt long thay vì trả giá trị sai vì overflow. Với giá trị dữ liệu cực lớn, nếu yêu cầu tính đúng trong mọi trường hợp trên số nguyên toán học, cần dùng BigInteger hoặc một chiến lược số học khác; chương trình học giới hạn ở các trường hợp mà **mọi phép toán trung gian nó thực hiện** nằm trong long.

Phần thử nghiệm sinh cả dữ liệu âm, trùng, không đơn điệu và nhiều mức rate/fee, đối chiếu **toàn bộ mảng DP** giữa bản trực tiếp và bản tối ưu.

~~~java
import java.util.Arrays;

public final class AlgebraicDpOptimization {
    private AlgebraicDpOptimization() {
    }

    private static void check(long[] a) {
        if (a == null || a.length == 0) {
            throw new IllegalArgumentException("nonempty array required");
        }
    }

    public static long[] linearBrute(long[] startPenalty, long rate) {
        check(startPenalty);
        int n = startPenalty.length - 1;
        long[] dp = new long[n + 1];
        for (int i = 1; i <= n; i++) {
            long best = Long.MAX_VALUE;
            for (int j = 0; j < i; j++) {
                long distanceCost = Math.multiplyExact(rate, i - j);
                long candidate = Math.addExact(
                        Math.addExact(dp[j], startPenalty[j]),
                        distanceCost);
                best = Math.min(best, candidate);
            }
            dp[i] = best;
        }
        return dp;
    }

    public static long[] linearFast(long[] startPenalty, long rate) {
        check(startPenalty);
        int n = startPenalty.length - 1;
        long[] dp = new long[n + 1];
        long minimumBase = startPenalty[0];

        for (int i = 1; i <= n; i++) {
            long iTerm = Math.multiplyExact(rate, i);
            dp[i] = Math.addExact(iTerm, minimumBase);
            if (i < n) {
                long candidateBase = Math.subtractExact(
                        Math.addExact(dp[i], startPenalty[i]), iTerm);
                minimumBase = Math.min(minimumBase, candidateBase);
            }
        }
        return dp;
    }

    private record Line(long slope, long intercept) {
        long valueAt(long x) {
            return Math.addExact(
                    Math.multiplyExact(slope, x), intercept);
        }
    }

    private static final class DiscreteLiChao {
        private final long[] coordinates;
        private final Line[] tree;

        DiscreteLiChao(long[] queryPoints) {
            long[] sorted = queryPoints.clone();
            Arrays.sort(sorted);
            int distinct = 0;
            for (long x : sorted) {
                if (distinct == 0 || sorted[distinct - 1] != x) {
                    sorted[distinct++] = x;
                }
            }
            coordinates = Arrays.copyOf(sorted, distinct);
            tree = new Line[4 * distinct];
        }

        void addLine(Line line) {
            insert(line, 1, 0, coordinates.length - 1);
        }

        private void insert(Line incoming, int node, int left, int right) {
            Line current = tree[node];
            if (current == null) {
                tree[node] = incoming;
                return;
            }

            int middle = left + (right - left) / 2;
            boolean betterLeft =
                    incoming.valueAt(coordinates[left])
                    < current.valueAt(coordinates[left]);
            boolean betterMiddle =
                    incoming.valueAt(coordinates[middle])
                    < current.valueAt(coordinates[middle]);

            if (betterMiddle) {
                tree[node] = incoming;
                incoming = current;
            }
            if (left == right) {
                return;
            }
            if (betterLeft != betterMiddle) {
                insert(incoming, node * 2, left, middle);
            } else {
                insert(incoming, node * 2 + 1, middle + 1, right);
            }
        }

        long minimumAt(long x) {
            int index = Arrays.binarySearch(coordinates, x);
            if (index < 0) {
                throw new IllegalArgumentException("unregistered x");
            }
            return query(1, 0, coordinates.length - 1, index, x);
        }

        private long query(int node, int left, int right,
                           int index, long x) {
            long answer = tree[node] == null
                    ? Long.MAX_VALUE : tree[node].valueAt(x);
            if (left == right) {
                return answer;
            }
            int middle = left + (right - left) / 2;
            long other = index <= middle
                    ? query(node * 2, left, middle, index, x)
                    : query(node * 2 + 1, middle + 1, right, index, x);
            return Math.min(answer, other);
        }
    }

    public static long[] quadraticBrute(long[] x, long fee) {
        check(x);
        long[] dp = new long[x.length];
        for (int i = 1; i < x.length; i++) {
            long best = Long.MAX_VALUE;
            for (int j = 0; j < i; j++) {
                long difference = Math.subtractExact(x[i], x[j]);
                long square = Math.multiplyExact(difference, difference);
                long candidate = Math.addExact(
                        Math.addExact(dp[j], square), fee);
                best = Math.min(best, candidate);
            }
            dp[i] = best;
        }
        return dp;
    }

    private static Line makeLine(long x, long dpValue) {
        long slope = Math.multiplyExact(-2L, x);
        long intercept = Math.addExact(
                dpValue, Math.multiplyExact(x, x));
        return new Line(slope, intercept);
    }

    public static long[] quadraticFast(long[] x, long fee) {
        check(x);
        long[] dp = new long[x.length];
        DiscreteLiChao hull = new DiscreteLiChao(x);
        hull.addLine(makeLine(x[0], 0L));

        for (int i = 1; i < x.length; i++) {
            long square = Math.multiplyExact(x[i], x[i]);
            long minimumLineValue = hull.minimumAt(x[i]);
            dp[i] = Math.addExact(
                    Math.addExact(square, fee), minimumLineValue);
            if (i + 1 < x.length) {
                hull.addLine(makeLine(x[i], dp[i]));
            }
        }
        return dp;
    }

    private static void verify() {
        long[] alphabet = {-2L, 0L, 3L};
        long[] rates = {-2L, 0L, 4L};
        long[] fees = {-1L, 0L, 2L};
        int checkedLinear = 0;
        int checkedQuadratic = 0;

        for (int n = 0; n <= 6; n++) {
            int combinations = 1;
            for (int i = 0; i <= n; i++) {
                combinations *= alphabet.length;
            }
            for (int code = 0; code < combinations; code++) {
                int rest = code;
                long[] values = new long[n + 1];
                for (int i = 0; i <= n; i++) {
                    values[i] = alphabet[rest % alphabet.length];
                    rest /= alphabet.length;
                }
                long[] original = values.clone();
                for (long rate : rates) {
                    if (!Arrays.equals(linearBrute(values, rate),
                            linearFast(values, rate))) {
                        throw new AssertionError("linear mismatch: "
                                + Arrays.toString(values) + ", rate=" + rate);
                    }
                    checkedLinear++;
                }
                for (long fee : fees) {
                    if (!Arrays.equals(quadraticBrute(values, fee),
                            quadraticFast(values, fee))) {
                        throw new AssertionError("quadratic mismatch: "
                                + Arrays.toString(values) + ", fee=" + fee);
                    }
                    checkedQuadratic++;
                }
                if (!Arrays.equals(values, original)) {
                    throw new AssertionError("input was modified");
                }
            }
        }

        long[] largeLinear = {2_000_000_000L, -5L, 7L};
        if (!Arrays.equals(linearBrute(largeLinear, 3L),
                linearFast(largeLinear, 3L))) {
            throw new AssertionError("large penalty mismatch");
        }
        long[] largeQuadratic = {0, 1_000_000L, -1_000_000L};
        if (!Arrays.equals(quadraticBrute(largeQuadratic, 5L),
                quadraticFast(largeQuadratic, 5L))) {
            throw new AssertionError("large coordinate mismatch");
        }
        try {
            quadraticFast(new long[] {Long.MAX_VALUE, 0}, 0);
            throw new AssertionError("overflow should be rejected");
        } catch (ArithmeticException expected) {
        }
        try {
            linearFast(new long[] {Long.MAX_VALUE, 0}, 1);
            throw new AssertionError("overflow should be rejected");
        } catch (ArithmeticException expected) {
        }

        System.out.println("Verified " + checkedLinear
                + " linear cases: PASS");
        System.out.println("Verified " + checkedQuadratic
                + " quadratic cases: PASS");
        System.out.println("Large-value and overflow checks: PASS");
    }

    public static void main(String[] args) {
        long[] penalties = {8, -4, 7, -5, 3, 0};
        System.out.println("Linear brute: "
                + Arrays.toString(linearBrute(penalties, 3)));
        System.out.println("Linear fast: "
                + Arrays.toString(linearFast(penalties, 3)));

        long[] positions = {0, 3, 1, 4};
        System.out.println("Quadratic brute: "
                + Arrays.toString(quadraticBrute(positions, 2)));
        System.out.println("Quadratic fast: "
                + Arrays.toString(quadraticFast(positions, 2)));
        System.out.println("Repeated coordinates: "
                + Arrays.toString(quadraticFast(
                        new long[] {4, 4, 4}, 0)));
        System.out.println("Zero transitions: "
                + Arrays.toString(linearFast(new long[] {8}, 3)));

        verify();
    }
}
~~~

Lưu tệp như tên lớp công khai, sau đó chạy:

~~~bash
javac AlgebraicDpOptimization.java
java AlgebraicDpOptimization
~~~

Đầu ra stdout chính xác của chương trình:

~~~text
Linear brute: [0, 11, 10, 13, 11, 14]
Linear fast: [0, 11, 10, 13, 11, 14]
Quadratic brute: [0, 11, 3, 14]
Quadratic fast: [0, 11, 3, 14]
Repeated coordinates: [0, 0, 0]
Zero transitions: [0]
Verified 9837 linear cases: PASS
Verified 9837 quadratic cases: PASS
Large-value and overflow checks: PASS
~~~

**Diễn giải:** hai phương án tuyến tính đều trả [0,11,10,13,11,14]; hai phương án bình phương đều trả [0,11,3,14]. Ca tọa độ lặp và ca chỉ có trạng thái dp[0] cũng cho kết quả đúng theo hợp đồng. Các dòng PASS là đối chiếu độc lập được mô tả ở phần kế tiếp.

## 18. Kiểm thử đầy đủ trên miền nhỏ và kiểm tra độ an toàn số học

Bộ verify sinh mọi dãy độ dài n+1 với n từ 0 tới 6, lấy từng phần tử từ {-2,0,3}. Tổng số dãy là:

~~~text
3^1 + 3^2 + 3^3 + 3^4 + 3^5 + 3^6 + 3^7
= 3 + 9 + 27 + 81 + 243 + 729 + 2187
= 3279 dãy.
~~~

**Đối với tuyến tính:** mỗi dãy chạy ba rate {-2,0,4}; tổng 3279×3 = **9.837 trường hợp**. Chương trình so **từng dp[i]** của linearBrute với linearFast, không chỉ so dp[n].

**Đối với bình phương:** mỗi dãy chạy ba fee {-1,0,2}; tổng cũng là **9.837 trường hợp**. Chương trình so toàn bộ mảng DP của quadraticBrute với quadraticFast. Do dãy x có thể xuất hiện lại cùng giá trị và các x không được sắp theo thời gian, những trường hợp này kiểm tra cả cấu trúc Li Chao và việc nén tọa độ.

Chương trình còn kiểm tra:

- Mảng đầu vào giữ nguyên sau khi gọi các hàm.
- Penalty lớn và tọa độ cỡ một triệu vẫn cho kết quả trùng với bản trực tiếp.
- Phép toán vượt long bị báo lỗi ArithmeticException, không âm thầm wrap.

Bản brute được tính trực tiếp bằng vòng j<i, không dùng cực trị đã tách hoặc Li Chao; đây là **oracle thực thi khác con đường tối ưu**, rất hữu ích để phát hiện sai chỉ số và lỗi cập nhật cấu trúc. Tuy nhiên, kiểm thử hữu hạn không thay thế chứng minh đại số và bất biến đối với mọi đầu vào hợp lệ.

## 19. Độ phức tạp: số trạng thái không đổi, chi phí chuyển thay đổi

| Phương án | Số trạng thái DP | Tìm min cho mỗi i | Thời gian tổng | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Tuyến tính brute | n+1 | Duyệt i ứng viên | Θ(n²) | O(n) |
| Tuyến tính running min | n+1 | O(1) | O(n) | O(n) cho mảng DP |
| Bình phương brute | n+1 | Duyệt i ứng viên | Θ(n²) | O(n) |
| Bình phương Li Chao | n+1 | Query O(log n), thêm line O(log n) | O(n log n) | O(n) cho DP, tọa độ và cây |

Điểm cải tiến **không phải số trạng thái giảm**. Vẫn có n+1 ô dp, nhưng phép tìm min qua j được gói trong một cấu trúc hỗ trợ truy vấn nhanh. Đây là một mô thức tối ưu quan trọng: **nhận dạng đại số của biểu thức chuyển → thay đổi cách tính chuyển → giữ nguyên giá trị trạng thái**.

Trong bản Li Chao rời rạc, sorting/nén m tọa độ mất O(n log n), mỗi lần query/add O(log m), m≤n+1. Khi n=0, chỉ có dp[0] và không có vòng chuyển. Khi n đủ lớn, giới hạn bộ nhớ cấp phát và overflow của số học vẫn cần được kiểm tra riêng, không được suy ra an toàn từ Big-O.

## 20. Tính đúng đắn của tối ưu bình phương: hai tầng chứng minh

Có **hai phần** cần chứng minh, và không thể thay thế nhau:

**Tầng 1 — Đại số và tập ứng viên:** với mỗi j<i, chi phí gốc dp[j]+(x[i]−x[j])²+fee bằng x[i]²+fee+line_j(x[i]). Hằng x[i]²+fee không phụ thuộc j nên lấy ra ngoài min; vì cấu trúc chỉ chứa các đường từ j<i, tập ứng viên sau biến đổi **giống hệt** tập ứng viên trước biến đổi.

**Tầng 2 — Cấu trúc dữ liệu:** Li Chao tree phải trả đúng giá trị min trong tập các đường hiện có tại một tọa độ query. Mỗi cặp đường chỉ có tối đa một giao điểm; khi chèn, giữ đại diện tốt ở giữa và đưa đường còn lại xuống nhánh có khả năng còn tốt hơn, bảo toàn minimum trên mọi tọa độ rời rạc được đăng ký. Query xét các đại diện trên đường đi tới lá và lấy min.

Kết hợp hai tầng: query của Li Chao bằng min của phần phụ thuộc j trong công thức gốc; cộng lại hằng theo i cho dp[i] đúng. Sau khi tính xong dp[i], thêm line_i tạo đúng tập đường cho bước i+1. Đây là một quy nạp theo i.

**Nếu chỉ chứng minh đẳng thức khai triển bình phương mà cài cấu trúc sai**, kết quả vẫn sai. **Nếu cấu trúc Li Chao chạy đúng nhưng thêm đường từ j chưa được tính**, cũng sai. Vì vậy mỗi lớp trừu tượng cần một bất biến riêng.

## 21. Số học nguyên và giới hạn của tối ưu đại số

Trên số nguyên toán học, việc khai triển (x[i]−x[j])² là một đẳng thức. Nhưng phép toán trên **long** có miền biểu diễn hữu hạn; các biểu thức tương đương toán học có thể **khác nhau về khả năng tránh overflow khi tính từng trung gian**.

Ví dụ, một tích slope×x hoặc tổng intercept có thể vượt long **trước khi** một số hạng âm khác triệt tiêu nó, ngay cả khi chi phí gốc (hiệu tọa độ)² vẫn nhỏ. Bởi vậy chương trình ví dụ chủ động dùng Math.*Exact và ném ArithmeticException nếu không thể biểu diễn **bất kỳ phép trung gian** cần thiết. Nó không cố chứng minh rằng một đáp án toán học nằm trong long sẽ luôn được tính được bằng mọi biểu thức tương đương trong long.

Trong sản phẩm thực tế, có thể cần:

- Giới hạn |x[i]|, |rate|, |penalty[i]| và n để đảm bảo mọi phép toán trung gian an toàn.
- Dùng BigInteger cho cả dp, slope, intercept và kết quả đánh giá đường, rồi điều chỉnh việc so sánh.
- Với số thực, xác định sai số, so sánh hòa và độ chính xác của giao điểm; không giả sử phép số thực có tính kết hợp tuyệt đối.
- Khi tối ưu trên miền modulo, **không tự áp dụng phép min vào các giá trị đã lấy modulo**: thứ tự thông thường của số nguyên không được bảo toàn qua phép modulo.

**Một lưu ý nữa:** không dùng Long.MAX_VALUE làm “vô cực” tùy tiện khi sau đó còn cộng chi phí lên giá trị sentinel. Trong code minh họa, Long.MAX_VALUE chỉ là giá trị khởi tạo best khi đã biết chắc mỗi i≥1 có ít nhất một j<i, và phép toán trên ứng viên được kiểm tra. Với bài có trạng thái không đạt tới, cần mô hình hóa “không có lời giải” rõ ràng.

## 22. Những lỗi phổ biến khi cố tách phần phụ thuộc từng chỉ số

1. **Đưa một hạng tử còn phụ thuộc j ra ngoài min.** Chỉ thành phần thật sự không đổi theo j mới được kéo ra.
2. **Làm mất dấu âm khi khai triển bình phương.** Hạng tử tương tác chính xác là −2*x[i]*x[j], không phải +2*x[i]*x[j].
3. **Quên phí cố định fee.** Một hằng số theo i có thể lấy ra ngoài min nhưng vẫn phải được cộng lại đúng một lần.
4. **Dùng best chứa cả j=i.** Phải query trước khi thêm ứng viên từ trạng thái vừa tính.
5. **Không xử lý base case.** dp[0]=0 và tập j<i không rỗng với i≥1; mảng độ dài 1 chỉ trả [0].
6. **Trộn chỉ số i với giá trị x[i].** i tăng theo thứ tự DP, còn x[i] có thể giảm, âm hoặc trùng.
7. **Dùng prefix minimum khi ứng viên cũ hết hạn.** Nếu j chỉ thuộc cửa sổ, cần hỗ trợ loại bỏ hoặc giới hạn query.
8. **Dùng CHT deque với x không đơn điệu mà không chứng minh điều kiện.** Chỉ số thời gian tăng không làm tọa độ truy vấn tăng.
9. **Gộp trạng thái trùng tọa độ.** Cùng x không có nghĩa dp[i] và dp[j] là cùng một trạng thái.
10. **Sai slope/intercept của một đường.** Với cost bình phương, m_j=−2*x[j], b_j=dp[j]+x[j]².
11. **Thêm đường bằng dp[j] chưa hoàn tất.** Phải tính xong trạng thái j trước khi cấu trúc sử dụng đường của nó.
12. **Chỉ lấy giá trị min nhưng đề yêu cầu truy vết.** Cần lưu ID của đường/argmin và predecessor, không thể đoán lại chỉ từ giá trị chi phí.
13. **Sai số học khi vượt long.** Hai biểu thức tương đương toán học không đảm bảo mọi intermediate đều an toàn trong long.
14. **Không tính chi phí sorting/nén tọa độ.** Tổng của Li Chao vẫn O(n log n), không phải O(n) trong hiện thực này.
15. **Gọi O(n²) là do n trạng thái.** Đúng hơn là n trạng thái, mỗi trạng thái xét tới O(n) ứng viên.
16. **Bỏ qua quy tắc hòa.** Nhiều j cho cùng chi phí tối ưu; nếu output yêu cầu một j cụ thể, cần quy ước và kiểm tra.
17. **Thử tối ưu khi chưa có bản đúng.** Hãy tạo oracle O(n²) cho các n nhỏ và kiểm tra toàn bộ bảng trước.

## 23. Checklist và bài tập áp dụng

Khi gặp một công thức chuyển có hai chỉ số i,j:

1. **Viết chính xác trạng thái và miền j.** Ví dụ j<i, j trong cửa sổ hoặc một tập ứng viên có ràng buộc.
2. **Khai triển và nhóm hạng tử.** Chỉ ra A(i), B(j), U(i)V(j) và những thành phần không tách được.
3. **Giữ nguyên tập ứng viên.** Quyết định rõ khi nào một j mới được thêm, khi nào một j cũ bị xóa.
4. **Chọn phép truy vấn.** Prefix min, deque, segment tree, CHT, Li Chao, hay vẫn cần duyệt trực tiếp.
5. **Viết bất biến của dữ liệu duy trì.** Cấu trúc đang lưu chính xác những ứng viên nào?
6. **Chứng minh đẳng thức và cấu trúc.** Giá trị mỗi ứng viên sau biến đổi phải bằng trước biến đổi; query phải tìm đúng min/max.
7. **Xử lý chỉ số và hòa.** Base case, cập nhật sau khi query, cặp chỉ số gốc nếu cần dựng phương án.
8. **Đếm toàn bộ chi phí.** Thời gian dựng/nén dữ liệu, thêm ứng viên, query, và bộ nhớ.
9. **Kiểm soát overflow/precision.** Hằng đẳng thức toán học không tự bảo đảm tính an toàn của kiểu máy.
10. **Kiểm thử đối chiếu.** Viết bản O(n²) đáng tin, sinh ca nhỏ gồm số âm, giá trị trùng, x không đơn điệu, n=0 và giới hạn số.

**Bài tập 1 — Tách tuyến tính:** với dp[i]=min_{j<i}(dp[j]+5(i−j)+w[j]), hãy định nghĩa key[j], best, viết bất biến và tính dp trên w=[2,−1,4,0]. Giải thích tại sao phải cập nhật key[i] sau khi đã tính dp[i].

**Bài tập 2 — Cửa sổ giới hạn:** chỉ cho phép i−3≤j<i trong công thức bài 1. Hãy chỉ ra phản ví dụ làm prefix minimum sai khi một j cũ hết hạn; đề xuất deque đơn điệu để duy trì min hợp lệ.

**Bài tập 3 — Bình phương tổng tiền tố:** cho a=[2,−3,4,−1], tạo x[i]=tổng tiền tố tới i. Dùng dp[i]=min_{j<i}(dp[j]+(x[i]−x[j])²+2). Hãy lập các đường m_j,b_j và kiểm tra vì sao x không đơn điệu.

**Bài tập 4 — Khôi phục trạng thái trước:** mở rộng Line thành (slope,intercept,originIndex) và query trả cả giá trị lẫn j thắng. Hãy lưu parent[i] và dựng dãy mốc chuyển từ n về 0; định nghĩa tie-break nhỏ nhất theo j để kết quả ổn định.

**Bài tập 5 — Hai chiều max/min:** với công thức dp[i]=A(i)+min_j U(i)B(j), xét riêng U(i)≥0, U(i)<0 và U(i)=0. Hãy giải thích khi nào chỉ cần min B, khi nào cần max B, và vì sao tập j phải được duy trì đúng theo thời gian.

**Bài tập 6 — Kiểm chứng tính phức tạp:** đếm chính xác số ứng viên của bản brute trên n=1000, so với số lần thêm/query của bản chạy O(n) và Li Chao O(n log n). Chú ý sự khác nhau giữa thời gian khởi tạo, số trạng thái và thời gian xử lý mỗi trạng thái.

**Kết luận:** kỹ thuật **dùng biểu thức đại số để tách phần phụ thuộc từng chỉ số** là bước từ một công thức chuyển DP nhiều vòng lặp sang một bài toán cực trị có cấu trúc. Với A(i)+B(j), thường có thể duy trì một min theo prefix; với A(i)+U(i)V(j)+W(j), có thể biến mỗi j thành một đường thẳng và dùng CHT/Li Chao theo đúng điều kiện. Sự tối ưu là đáng tin khi **đẳng thức đại số đúng, tập ứng viên được bảo toàn, cấu trúc trả đúng cực trị và phép tính số học an toàn**.
