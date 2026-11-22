# Quy hoạch động trên đoạn và lựa chọn điểm tách

Trong **quy hoạch động cấu trúc (structural dynamic programming)**, nhiều bài toán không chọn từng phần tử độc lập mà cần tìm **cách tổ chức một đoạn**: nên đặt dấu ngoặc ở đâu, cắt một vật thể tại đâu, ghép hai phần nào trước hoặc chọn phần tử nào làm gốc. Khi một lựa chọn đầu tiên chia đoạn hiện tại thành hai đoạn nhỏ, ta có thể dùng **quy hoạch động trên đoạn (interval DP)** để tránh giải lặp lại vô số bài toán con.

Mô hình điển hình: đặt dp[l][r] là giá trị tối ưu khi giải một đoạn từ l tới r. Thử các điểm tách k hợp lệ, kết hợp kết quả tối ưu của các đoạn con, chọn phương án tốt nhất. Phần khó nhất không nằm ở việc viết ba vòng for, mà là xác định rõ **ý nghĩa trạng thái, điều kiện cơ sở, miền điểm tách, chi phí khi kết hợp và thứ tự tính**.

Bài học thuộc nhóm **Quy hoạch động cấu trúc** của Computer Science Algorithms, với trọng tâm **“Quy hoạch động trên đoạn và lựa chọn điểm tách”**. Hai ví dụ xuyên suốt là **nhân chuỗi ma trận (Matrix Chain Multiplication)** và **cắt một thanh với chi phí tối thiểu**. Chúng có công thức gần giống nhau nhưng **điểm tách mang ý nghĩa khác nhau**; học đúng sự khác biệt sẽ giúp tránh áp dụng máy móc một mẫu code cho mọi đề.

## 1. Khi nào một bài toán có cấu trúc đoạn?

Các dấu hiệu hữu ích:

- Đầu vào là một **dãy có thứ tự cố định**, ví dụ chuỗi ma trận A1, A2, ..., An hoặc danh sách các vị trí cắt trên một thanh.
- Cần tối ưu cách **đặt dấu ngoặc, chia một khoảng, chọn điểm cắt hoặc xác định phần tử làm gốc**.
- Sau khi chọn một điểm tách, phần công việc còn lại phân rã thành hai bài toán con nằm trong **những đoạn nhỏ hơn**.
- Lời giải của nhiều bài toán lớn cùng dùng lại chi phí tối ưu của một đoạn con giống nhau.
- Giá trị tối ưu của đoạn cha có thể tính từ **giá trị của hai con và chi phí ghép/tách**.

Không phải cứ có một dãy và hai chỉ số là dùng interval DP. Nếu kết quả chỉ phụ thuộc vài phần tử kề trước, DP một chiều có thể đủ. Nếu việc chọn điểm tách khiến hai nửa vẫn tương tác qua thông tin chưa lưu, trạng thái dp[l][r] **chưa đủ** và cần thêm tham số hoặc đổi cách mô hình hóa.

**Tư duy thiết kế:** sau khi cố định một lựa chọn k, hãy thử hỏi “hai đoạn con có thật sự độc lập nếu chỉ biết l, r và k không?”. Nếu có, tính tối ưu con là ứng viên tốt cho DP; nếu không, đừng vội viết dp hai chiều.

## 2. Quy ước đoạn đóng và đoạn nửa mở

Hai cách ký hiệu phổ biến:

| Quy ước | Các phần tử được xét | Độ dài | Trường hợp cơ sở thường gặp |
| --- | --- | --- | --- |
| Đoạn **đóng [l,r]** | l, l+1, ..., r | r−l+1 | l=r: một phần tử |
| Đoạn **nửa mở [l,r)** | l, l+1, ..., r−1 | r−l | r−l bằng 0 hoặc 1 tùy bài |
| Đoạn giữa **hai mốc biên** (l,r) | Các mốc tách ở chỉ số l+1..r−1 | r−l−1 mốc nội bộ | r=l+1: không còn điểm tách |

Bài **nhân chuỗi ma trận** ở phần dưới dùng [l,r] với l và r là **chỉ số ma trận** từ 0 tới n−1. Một điểm tách k chia thành [l,k] và [k+1,r] với l ≤ k < r.

Bài **cắt thanh** dùng hai biên l,r là **chỉ số trong mảng tọa độ đã sắp xếp**; chỉ những mốc k nằm giữa l và r mới là điểm cắt được phép chọn. Hai bài toán có bảng hai chiều nhưng **khác định nghĩa trạng thái và phạm vi k**.

Đây là nguồn lỗi off-by-one rất thường gặp: đoạn nửa mở và đoạn đóng không được thay qua lại mà giữ nguyên công thức split. Mọi khi triển khai nên viết ra bằng lời “đoạn này chứa phần tử nào” và kiểm tra với đoạn có đúng 1 hoặc 2 phần tử.

## 3. Khuôn cơ bản của interval DP

Với dạng tối thiểu hóa chi phí tách đoạn đóng, công thức minh họa là:

~~~text
dp[l][r] = min theo k hợp lệ của:
           dp[l][k] + dp[k+1][r] + combineCost(l,k,r).
~~~

Cách đọc:

1. **Trạng thái:** dp[l][r] là giá trị tối ưu cho bài toán con bao gồm các phần tử l..r.
2. **Base case:** đoạn một phần tử có lời giải trực tiếp, ví dụ 0 phép nhân để “nhân” một ma trận.
3. **Ứng viên:** với mỗi k trong [l,r−1], tạo hai đoạn con [l,k] và [k+1,r].
4. **Phép ghép:** cộng chi phí giải hai đoạn con và chi phí phát sinh khi kết hợp.
5. **Lấy tối ưu:** min nếu mục tiêu là ít chi phí nhất, max nếu mục tiêu là giá trị lớn nhất.
6. **Khôi phục:** lưu k tối ưu tại choice[l][r] nếu cần in cấu trúc thực tế.

**Tại sao chỉ lấy lời giải tối ưu của hai con?** Khi đã chọn k, nếu một con đang dùng lời giải tốn nhiều chi phí hơn một lời giải khác trên **chính cùng đoạn con** mà không ảnh hưởng đến phép ghép, ta có thể thay nó bằng lời giải tốt hơn. Vì vậy có thể giả sử hai con đều tối ưu.

Điều kiện cuối là yếu tố quan trọng: một số bài toán có chi phí kết hợp phụ thuộc vào chi tiết nội bộ của con, chứ không chỉ vào l,k,r. Khi đó việc chỉ lưu một số dp[l][r] có thể mất thông tin; cần làm rõ đặc tính cấu trúc tối ưu trước.

## 4. Vì sao phải duyệt theo độ dài đoạn tăng dần?

Một trạng thái dp[l][r] dùng hai đoạn con có độ dài **nhỏ hơn** đoạn cha. Vậy khi tính bottom-up, ta cần tính hết những đoạn ngắn hơn trước.

Ví dụ với n ma trận đánh số 0..n−1:

~~~text
for len = 2 .. n:
    for l = 0 .. n-len:
        r = l + len - 1
        dp[l][r] = +infinity
        for k = l .. r-1:
            xét dp[l][k] và dp[k+1][r]
~~~

Trước vòng len=2, mọi dp[i][i] đã được khởi tạo bằng 0. Với len=2, hai con có độ dài 1. Với len=3, con dài nhất có độ dài 2, đã được tính. Theo quy nạp trên len, mọi trạng thái cần dùng đều sẵn sàng.

**Không được mặc định duyệt l tăng rồi r tăng là đủ:** một trạng thái có thể cần dp[l+1][r], khi l+1 chưa được tính nếu thứ tự duyệt chưa hợp lý. Duyệt theo độ dài là cách dễ giải thích và dễ chứng minh với những bài toán mà cả hai chiều biên đều thay đổi.

Với **top-down memoization**, thứ tự được tạo bởi đệ quy; phải có base case, lời gọi con nhỏ hơn và bộ nhớ kết quả. Dù top-down và bottom-up có thể cùng O(n³), top-down còn dùng stack theo độ sâu gọi.

## 5. Bài toán nhân chuỗi ma trận: cấu trúc và mục tiêu

Cho n ma trận A1,...,An, tất cả đều phải được nhân theo **thứ tự ban đầu**:

~~~text
A1 x A2 x ... x An
~~~

Phép nhân ma trận có tính kết hợp, nghĩa là (A1×A2)×A3 và A1×(A2×A3) cho cùng kết quả số học khi kích thước hợp lệ, nhưng số phép nhân vô hướng cần thực hiện **có thể khác nhau rất lớn**.

Đặt mảng dims có n+1 số nguyên dương:

~~~text
A1 có kích thước dims[0] x dims[1]
A2 có kích thước dims[1] x dims[2]
...
An có kích thước dims[n-1] x dims[n].
~~~

Nhân một ma trận kích thước a×b với ma trận b×c theo thuật toán cơ bản mất **a×b×c phép nhân vô hướng**, và tạo ma trận kết quả kích thước a×c.

**Mục tiêu:** chọn cách **đặt dấu ngoặc** để tổng phép nhân vô hướng nhỏ nhất. Không được đổi thứ tự các ma trận. Bài toán là **tối ưu cấu trúc tính toán**, không phải thực hiện phép nhân ma trận thực tế.

Trường hợp n=1, chỉ có một ma trận nên chi phí nhân hai ma trận là **0** và biểu thức là A1. Mảng dims phải có ít nhất hai số dương; kích thước 0 hoặc âm không thuộc hợp đồng.

## 6. Trạng thái và công thức chuyển của Matrix Chain Multiplication

Đánh chỉ số ma trận từ 0 tới n−1 trong code Java. Định nghĩa:

~~~text
dp[l][r] = số phép nhân vô hướng tối thiểu để tính
           tích Al ... Ar (chỉ số ma trận trong code là 0-based).

dp[l][l] = 0.

Nếu l < r:
dp[l][r] = min_{l <= k < r} {
              dp[l][k]
            + dp[k+1][r]
            + dims[l] * dims[k+1] * dims[r+1]
           }.
~~~

Vì sao số hạng nhân cuối là dims[l] × dims[k+1] × dims[r+1]?

- Tích nhóm **bên trái** từ l tới k có kích thước dims[l] × dims[k+1].
- Tích nhóm **bên phải** từ k+1 tới r có kích thước dims[k+1] × dims[r+1].
- Nhân hai kết quả đó tốn dims[l] × dims[k+1] × dims[r+1] phép nhân vô hướng.

Các ma trận bên trong từng nhóm có thể được nhân theo những cách khác nhau, nhưng **kích thước của kết quả nhóm là cố định**, chỉ phụ thuộc hai đầu của nhóm. Điều này làm cho chi phí kết hợp chỉ cần l,k,r, không cần lưu thêm hình dạng cây tính toán của từng con khi tính chi phí.

**Bộ nhớ:** một bảng dp[n][n] lưu chi phí, và một bảng split[n][n] lưu k tối ưu nếu cần in dấu ngoặc. Mỗi bảng có O(n²) ô.

## 7. Ví dụ ba ma trận: phép tách quyết định chi phí

Cho dims = [10,30,5,60], tương ứng:

- A1 kích thước 10×30.
- A2 kích thước 30×5.
- A3 kích thước 5×60.

Có hai cách đặt dấu ngoặc:

~~~text
Cách 1: (A1 x A2) x A3
  A1 x A2: 10 × 30 × 5 = 1,500
  (A1 x A2) x A3: 10 × 5 × 60 = 3,000
  Tổng = 4,500.

Cách 2: A1 x (A2 x A3)
  A2 x A3: 30 × 5 × 60 = 9,000
  A1 x (A2 x A3): 10 × 30 × 60 = 18,000
  Tổng = 27,000.
~~~

**Đáp án tối ưu là 4.500**, nhỏ hơn 27.000 tới sáu lần. Thứ tự **A1,A2,A3 không đổi**; chỉ có thứ tự thực hiện phép nhân phụ thuộc vào dấu ngoặc.

Bảng các trạng thái (0-based):

| Trạng thái | Giá trị tối ưu | Diễn giải |
| --- | ---: | --- |
| dp[0][0], dp[1][1], dp[2][2] | 0 | Một ma trận chưa cần nhân |
| dp[0][1] | 1.500 | Nhân A1 với A2 |
| dp[1][2] | 9.000 | Nhân A2 với A3 |
| dp[0][2] | 4.500 | Chọn k=1, sau khi xét cả k=0 và k=1 |

Trong code Java, k=1 nghĩa là đoạn trái [0,1] chứa A1,A2 và đoạn phải [2,2] chứa A3; k=0 tương ứng A1 kết hợp với (A2×A3).

## 8. Chứng minh đúng đắn của MCM bằng quy nạp theo độ dài

**Cơ sở:** với một ma trận, không có phép nhân cần thực hiện nên dp[l][l]=0 đúng.

**Giả thiết:** với mọi đoạn có ít hơn len ma trận, dp đã lưu chi phí nhỏ nhất.

**Bước quy nạp:** xét đoạn [l,r] dài len≥2. Một cách đặt dấu ngoặc hợp lệ luôn có **phép nhân cuối cùng**, kết hợp tích của hai nhóm liên tiếp [l,k] và [k+1,r] với một k thỏa l≤k<r. Điều này đúng vì không được thay đổi thứ tự các ma trận.

Chi phí của bất kỳ cách đặt dấu ngoặc có phép nhân cuối tại k bằng:

~~~text
chi phí nhóm trái + chi phí nhóm phải
+ dims[l] * dims[k+1] * dims[r+1].
~~~

Theo giả thiết quy nạp, không nhóm nào có thể rẻ hơn dp của đoạn tương ứng. Ngược lại, chọn lời giải tối ưu của hai con rồi nhân kết quả lại tạo **một cách đặt dấu ngoặc hợp lệ** có đúng chi phí ứng viên đó. Vậy chi phí tốt nhất đối với k đúng bằng công thức ứng viên.

Mọi biểu thức hợp lệ có một k cuối cùng nào đó; lấy min trên tất cả k sẽ cho tối ưu toàn đoạn. Do đó dp[l][r] đúng với mọi len, đặc biệt dp[0][n−1].

**Đây không phải chứng minh “tham lam”**: không chọn ngay điểm tách có chi phí phép nhân hiện tại thấp nhất. Ta thử **tất cả k hợp lệ** và lấy kết quả dựa trên lời giải tối ưu của hai con.

## 9. Lưu điểm tách để khôi phục thứ tự nhân

Nếu chỉ cần chi phí tối thiểu, bảng dp là đủ. Nếu cần **cấu trúc phép nhân**, cần lưu lại điểm tách:

~~~text
split[l][r] = chỉ số k mang đến chi phí nhỏ nhất cho [l,r].
~~~

Khi có nhiều k hòa về chi phí, có thể chọn k đầu tiên khi duyệt từ trái qua phải; không có yêu cầu mặc định phải trả dấu ngoặc “đẹp nhất” theo một thứ tự riêng.

Để in cách đặt ngoặc, dùng một hàm đệ quy:

~~~text
print(l,r):
    nếu l=r: in tên ma trận Al
    nếu không:
        k = split[l][r]
        in "("
        print(l,k)
        in " x "
        print(k+1,r)
        in ")"
~~~

Ví dụ split[0][2]=1, split[0][1]=0 thì nhận **((A1 x A2) x A3)**. Số ma trận giữ nguyên, mỗi ma trận xuất hiện đúng một lần và theo thứ tự cũ.

Hàm dựng chuỗi trong bài mẫu dùng nối String để ngắn gọn. Một chuỗi ngoặc kết quả có độ dài O(n) ký tự nếu nhãn ma trận được coi có độ dài hằng số, hoặc O(n log n) khi tính số chữ số của các chỉ số. Dùng StringBuilder nếu muốn tránh tạo nhiều chuỗi trung gian khi n lớn; tổng thời gian DP O(n³) vẫn là khoản chi phối trong ví dụ.

## 10. Bài toán thứ hai: cắt một thanh với tổng chi phí nhỏ nhất

Cho một thanh dài **L > 0** và m vị trí cắt phân biệt, mỗi vị trí là một tọa độ nguyên c thỏa 0<c<L. Ta phải thực hiện **tất cả** vết cắt. Khi cắt một đoạn thanh hiện tại dài x, chi phí lần cắt đó bằng **x**, bất kể tọa độ vết cắt bên trong.

Điểm quyết định là **thứ tự thực hiện vết cắt**. Cắt toàn thanh ở một mốc đầu tiên tạo ra hai đoạn nhỏ; các lần cắt tiếp theo trên hai đoạn có thể thực hiện độc lập.

Ví dụ L=7, cuts={1,3,4,5}. Chọn thứ tự cắt:

~~~text
Cắt tại 3 trên thanh (0,7): chi phí 7.
Cắt tại 1 trên đoạn (0,3): chi phí 3.
Cắt tại 5 trên đoạn (3,7): chi phí 4.
Cắt tại 4 trên đoạn (3,5): chi phí 2.

Tổng chi phí = 7 + 3 + 4 + 2 = 16.
~~~

Mục tiêu là tìm **tổng chi phí nhỏ nhất** qua mọi thứ tự thực hiện các vết cắt. Không đủ nếu chỉ sắp các tọa độ cắt theo thứ tự tăng/giảm; mỗi quyết định làm thay đổi **độ dài đoạn được cắt** trong tương lai.

**Khác biệt quan trọng so với MCM:** trong nhân ma trận, điểm tách k biểu thị **phép nhân cuối**; trong cắt thanh, điểm tách k biểu thị **vết cắt đầu tiên** của đoạn hiện tại. Công thức hai con giống về hình dạng, nhưng thứ tự diễn giải và khôi phục không giống.

## 11. Chuẩn hóa tọa độ: thêm hai biên 0 và L

Bài cắt thanh sử dụng **vị trí trên trục độ dài**, không phải trực tiếp chỉ số đầu vào. Đầu tiên:

1. Clone danh sách cuts để không sửa mảng người gọi.
2. Sắp xếp các tọa độ vết cắt tăng dần.
3. Kiểm tra không có vết cắt trùng, không có tọa độ ≤0 hoặc ≥L.
4. Tạo mảng position = [0, các cuts đã sắp, L], có m+2 tọa độ.

Ví dụ:

~~~text
L = 7
cuts đầu vào = [5,1,4,3]
cuts sau sắp = [1,3,4,5]
position = [0,1,3,4,5,7]
chỉ số =    0 1 2 3 4 5
~~~

Đặt dp[l][r] là **chi phí nhỏ nhất để thực hiện tất cả các vết cắt nằm giữa position[l] và position[r]**, khi ta đang có một đoạn thanh với hai đầu đó.

Các mốc l,r chính là **biên đã có** của đoạn xét; một vết cắt cần làm tiếp phải có chỉ số k sao cho **l<k<r**.

Nếu r=l+1, không còn mốc cắt ở giữa, do đó **dp[l][r]=0**. Đây là trường hợp cơ sở riêng của bài cắt thanh, khác với dp[i][i]=0 của nhân chuỗi ma trận.

## 12. Công thức chọn vết cắt đầu tiên

Khi r≥l+2, đoạn còn ít nhất một vết cắt nội bộ. Chọn một mốc position[k] đầu tiên, l<k<r. Lần cắt đầu tiên trên đoạn dài position[r]−position[l] có chi phí bằng đúng độ dài đó.

Sau khi cắt, hai đoạn mới sẽ chứa các vết cắt còn lại độc lập:

- Bên trái: từ position[l] đến position[k].
- Bên phải: từ position[k] đến position[r].

Do đó:

~~~text
dp[l][r] = 0, nếu r=l+1.

Nếu r>=l+2:
dp[l][r] = min_{l < k < r} {
      (position[r] - position[l])
    + dp[l][k]
    + dp[k][r]
}.
~~~

**Vì sao không dùng dp[l][k−1] và dp[k+1][r]?** Trong bài này l,k,r biểu thị **tọa độ hai biên của đoạn sau cắt**. Vết cắt tại k trở thành biên cho **cả hai đoạn mới**, nên hai trạng thái con dùng [l,k] và [k,r] theo chỉ số biên. Nó không được tính là một vết cắt nội bộ ở con nữa.

**Chọn k là vết cắt đầu tiên, không phải “vết cắt cuối”**: chi phí position[r]−position[l] được trả ngay khi tách đoạn cha, trước khi xử lý hai nửa. Điều này làm cho phép truy vết thứ tự cắt có thể thực hiện bằng preorder (k trước, trái sau, phải sau).

## 13. Thứ tự tính DP cho bài cắt thanh

Với m vết cắt, position có m+2 điểm. Một trạng thái [l,r] chỉ phụ thuộc vào [l,k] và [k,r], có **khoảng cách chỉ số nhỏ hơn r−l**. Vì vậy có thể duyệt khoảng cách gap=r−l tăng dần.

~~~text
for gap = 2 .. m+1:
    for l sao cho l+gap <= m+1:
        r = l+gap
        dp[l][r] = +infinity
        for k = l+1 .. r-1:
            cập nhật chi phí chọn k đầu tiên
~~~

Các trạng thái gap=1 (hai biên kề nhau, không có vết cắt) được khởi tạo bằng 0. Với gap=2, có đúng một vết cắt nội bộ và hai bài toán con cơ sở. Với gap lớn hơn, mọi con đã được tính ở một khoảng cách nhỏ hơn.

Đáp án là dp[0][m+1], vì hai biên ngoài cùng là 0 và L. Nếu m=0, position chỉ gồm [0,L], dp[0][1]=0 và kết quả là 0: **không cắt thì không tốn chi phí**.

## 14. Khôi phục thứ tự cắt và kiểm tra tính hợp lệ

Lưu choice[l][r] là chỉ số k tối ưu của đoạn [l,r]. Để tạo một thứ tự cắt thật:

~~~text
reconstruct(l,r):
    nếu không có k nằm giữa l và r: return
    k = choice[l][r]
    thêm position[k] vào danh sách kết quả
    reconstruct(l,k)
    reconstruct(k,r)
~~~

Vết cắt cha phải diễn ra **trước** mọi vết cắt thuộc hai đoạn con. Một trình tự khác có thể vẫn tối ưu, nhưng preorder là cách dựng đơn giản, trực tiếp từ ý nghĩa “k đầu tiên”.

Trong ví dụ L=7, position=[0,1,3,4,5,7], một lời giải được code trả về là **[3,1,5,4]**. Kiểm lại bằng mô phỏng chi phí các đoạn hiện hành:

| Bước | Vết cắt | Hai biên của đoạn được cắt | Chi phí |
| ---: | ---: | --- | ---: |
| 1 | 3 | 0 và 7 | 7 |
| 2 | 1 | 0 và 3 | 3 |
| 3 | 5 | 3 và 7 | 4 |
| 4 | 4 | 3 và 5 | 2 |
| **Tổng** | | | **16** |

Khi kiểm tra một danh sách cutOrder, không chỉ so độ dài mảng. Cần xác nhận mọi vị trí cắt đầu vào xuất hiện **đúng một lần**, nằm giữa hai biên hiện hành và tổng chi phí mô phỏng bằng dp[0][m+1].

Code Java có hàm validateCutOrder làm đúng việc đó bằng cách xét các vết cắt đã thực hiện. Nó được dùng trong bộ kiểm thử, không cần gọi lại để tính giá trị tối ưu trong phiên bản sản xuất.

## 15. Chứng minh công thức cắt thanh đúng

Ta quy nạp theo **số vết cắt nằm giữa hai biên**:

**Cơ sở:** không có vết cắt nội bộ nên chi phí tối ưu bằng 0.

**Bước quy nạp:** xét một đoạn có ít nhất một vết cắt. Trong bất kỳ thứ tự thực hiện hợp lệ nào, sẽ có một **vết cắt đầu tiên** tại một mốc k nằm giữa hai biên. Vì chưa cắt đoạn này lần nào, chi phí của bước đầu là **position[r]−position[l]**.

Sau bước đầu tiên, các vết cắt còn lại thuộc một trong hai đoạn con, và chi phí thực hiện các vết cắt trong một nửa **không phụ thuộc vào thứ tự thao tác ở nửa kia**. Theo giả thiết quy nạp, chi phí còn lại tối thiểu của hai nửa là dp[l][k] và dp[k][r].

Vậy mọi thứ tự có vết cắt đầu k tốn ít nhất:

~~~text
position[r]-position[l] + dp[l][k] + dp[k][r].
~~~

Ngược lại, chọn k rồi thực hiện hai thứ tự tối ưu của hai nửa là một lịch cắt hợp lệ đạt đúng chi phí đó. Mỗi lời giải có một vết cắt đầu k nào đó, nên lấy min trên tất cả k là tối ưu. Từ đó suy ra dp[0][m+1] đúng.

Chứng minh giống MCM ở **optimal substructure**, nhưng khác ở “thao tác đầu hay cuối” và cách chia biên. Chính mô hình chi phí của đề quyết định công thức, không phải hình thức hai chỉ số của bảng.

## 16. So sánh hai mẫu interval DP

| Đặc trưng | Nhân chuỗi ma trận | Cắt thanh tối thiểu |
| --- | --- | --- |
| Một trạng thái dp[l][r] | Chi phí nhân nhóm ma trận l..r | Chi phí xử lý các vết cắt giữa hai biên l,r |
| Các chỉ số l,r | Chỉ số ma trận | Chỉ số của mốc trong position |
| Base case | l=r → 0 | r=l+1 → 0 |
| Điểm tách k | l≤k<r | l<k<r |
| Con trái | [l,k] | (l,k) theo hai mốc biên |
| Con phải | [k+1,r] | (k,r) theo hai mốc biên |
| Ý nghĩa k | Phép nhân **cuối cùng** | Vết cắt **đầu tiên** |
| Chi phí kết hợp | dims[l]×dims[k+1]×dims[r+1] | position[r]−position[l] |
| Dữ liệu cần lưu để dựng lời giải | split[l][r] | choice[l][r] |
| Trả về | Cách đặt ngoặc / chi phí | Thứ tự cắt / chi phí |
| Thời gian | O(n³) với n ma trận | O(m³) với m vết cắt, cộng sắp xếp O(m log m) |
| Bộ nhớ phụ | O(n²) cho bảng | O(m²) cho bảng |

Điểm tương đồng là mỗi đoạn cha tối ưu qua các cách tách hợp lệ, có hai đoạn con nhỏ hơn và có thể memoize. Điểm khác biệt là **ngữ nghĩa của trạng thái**. Không được sao chép máy móc k+1 sang bài cắt thanh vì sẽ bỏ mất mốc biên cần có trong cả hai đoạn.

## 17. Phân tích thời gian bằng tổng số điểm tách

Với n ma trận, mỗi đoạn độ dài len≥2 có n−len+1 vị trí bắt đầu. Mỗi đoạn đó thử len−1 điểm tách:

~~~text
T(n) theo số ứng viên:
sum_{len=2..n} (n-len+1) × (len-1).

Đổi biến t=len-1:
sum_{t=1..n-1} (n-t) × t
= n(n-1)(n+1) / 6
= (n^3 - n) / 6.
~~~

Vì mỗi ứng viên cần O(1) phép tính số học (trong mô hình đơn vị chi phí cho kiểu số cố định), thời gian tính DP là **Θ(n³)** với n≥2 và bộ nhớ **Θ(n²)** cho hai bảng khi n lớn. Tiền xử lý/kiểm tra dims tốn O(n), còn truy vết có n lá và n−1 nút phép nhân.

Với m vết cắt, position có m+2 mốc; mỗi cặp biên cách nhau gap≥2 thử gap−1 điểm cắt. Tổng số ứng viên là:

~~~text
sum_{gap=2..m+1} (m+2-gap) × (gap-1)
= m(m+1)(m+2)/6
= Θ(m^3).
~~~

Như vậy:

- **Nhân ma trận:** O(n³) thời gian, O(n²) bộ nhớ.
- **Cắt thanh:** O(m log m) sắp xếp + O(m³) DP, O(m²) bộ nhớ.
- **Khôi phục:** O(n) nút cấu trúc ở MCM (không tính chi phí nối chuỗi) hoặc O(m) lần cắt với mảng kết quả.
- **Top-down:** cùng số đoạn và ứng viên trong trường hợp xấu nhất, cộng thêm call stack chiều sâu O(n) hoặc O(m).

Lưu ý rằng bộ nhớ O(n²) là **bộ nhớ phụ của bảng**, không phải số bộ tham số chỉ số đã cấp phát vật lý khi dùng HashMap memo. Nếu sử dụng mảng vuông, cả những ô ngoài miền l≤r cũng được cấp chỗ, nhưng vẫn cùng bậc O(n²).

## 18. Vì sao điểm tách tốt nhất không đơn giản là điểm giữa?

Một dự đoán tham lam phổ biến: “cắt ở giữa để cân bằng”, “nhân nhóm có số hàng nhỏ nhất trước”, hoặc “chọn k làm chi phí ghép trước mắt nhỏ nhất”. Những quy tắc này **không có bảo đảm tối ưu tổng thể** cho bài toán tổng quát.

Trong MCM, điểm tách quyết định **chi phí các phép nhân bên trong hai nhóm**; một phép nhân có vẻ rẻ ở bước hiện tại có thể làm xuất hiện kích thước ma trận trung gian bất lợi về sau. Ví dụ dims=[10,30,5,60] cho thấy hai vị trí k tạo chênh lệch lớn 4.500 so với 27.000; chỉ nhìn số phép nhân của bước cuối mà bỏ dp của hai con sẽ không đủ để chọn tối ưu.

Trong cắt thanh, chọn vết cắt gần giữa thường có ích ở những trường hợp đối xứng, nhưng chi phí tổng phụ thuộc **phân bố toàn bộ các vết cắt còn lại** trong từng nửa, không chỉ độ dài đoạn ngay sau cắt. Chính vì thế phải xét mọi k khi không có điều kiện cấu trúc bổ sung được chứng minh.

**Interval DP không đồng nghĩa “chia đôi”.** Phép chia của bài toán có thể rất lệch; chỉ yêu cầu hai bài toán con nhỏ hơn đoạn cha để có thứ tự phụ thuộc hợp lệ. Việc tối ưu k dựa trên chứng minh phụ thuộc cấu trúc, không phải trực giác hình học.

## 19. Khái quát sang các bài toán khác

Các mẫu liên quan:

1. **Minimum cost polygon triangulation:** chọn một đỉnh trung gian k để chia đa giác con thành hai phần và cộng chi phí của tam giác kết hợp. Trạng thái và base case phụ thuộc cách đánh chỉ số đỉnh.
2. **Optimal binary search tree:** chọn một khóa làm gốc cho đoạn khóa; hai đoạn con tương ứng cây trái và cây phải, chi phí thêm phụ thuộc tần suất tìm kiếm và độ sâu. Không lấy nguyên chi phí của MCM.
3. **Palindrome partitioning:** tách một chuỗi thành các đoạn palindrome; nếu chỉ cần số đoạn ít nhất và đã biết palindrome[l][r], có thể dùng DP theo tiền tố, không bắt buộc hai chiều điểm tách.
4. **Burst balloons:** chọn quả bóng **nổ cuối cùng** trong một đoạn để làm độc lập hai nửa; cần thêm hai phần tử biên giả và công thức cộng tích phụ thuộc các biên còn tồn tại. Chọn “nổ đầu tiên” thường làm hai nửa phụ thuộc lẫn nhau hơn.
5. **Minimum score triangulation:** các đoạn con có thể được kết hợp qua đỉnh k, chi phí theo ba đỉnh l,k,r.
6. **Parsing theo ngữ pháp phi ngữ cảnh:** trạng thái thường gồm khoảng l,r và ký hiệu ngữ pháp, thử điểm tách k; do có thêm ký hiệu, không thể chỉ lưu một số dp[l][r].

Trong các bài này, hai nguyên tắc không đổi là **nghĩa của trạng thái** và **tính độc lập sau khi chọn k**. Không phải đề nào cũng cho phép rút về đúng công thức cộng hai chi phí con; đôi khi phép ghép dùng min/max với trọng số hoặc bảng nhiều chiều.

## 20. Về các tối ưu O(n³) thành O(n²): phải có điều kiện riêng

Một số interval DP có thể tận dụng tính chất đặc biệt của chi phí để rút số điểm tách cần kiểm tra:

- **Knuth optimization** khai thác những điều kiện nhất định về bất đẳng thức tứ giác và tính đơn điệu của chỉ số điểm tách tối ưu, cho phép giới hạn miền k của một đoạn bằng các điểm tách tối ưu của đoạn lân cận.
- **Divide-and-conquer optimization** cho các công thức DP phù hợp có tính đơn điệu của vị trí tối ưu; nó không áp dụng tự động chỉ vì công thức chứa min.
- **Monge/convexity** và những giả thiết khác đôi khi dẫn tới thuật toán nhanh hơn, nhưng cần chứng minh đối với **hàm cost cụ thể**.

Không được suy luận rằng **mọi** bài MCM hoặc cắt thanh có thể rút từ O(n³) xuống O(n²) bằng “Knuth” chỉ vì đều là interval DP. Những điều kiện tối ưu hóa không đúng tổng quát cho chi phí dims[l]×dims[k+1]×dims[r+1] của MCM.

Bắt đầu bằng bản DP O(n³) đúng, giải thích rõ trạng thái và phép chuyển, dùng một oracle nhỏ để thử, rồi mới tìm cách giảm điểm tách theo **đặc tính đã được chứng minh**. Một tối ưu sai có thể cho kết quả đúng trên ví dụ nhỏ mà sai khi cấu trúc chi phí phức tạp.

## 21. Java 17+: hai bài toán, có khôi phục phương án

Chương trình bên dưới chứa hai lời giải đầy đủ:

- **matrixChain(dims):** trả số phép nhân vô hướng tối thiểu và cách đặt ngoặc. Kiểm tra dims khác null, có ít nhất hai số nguyên dương; dùng dp, split và truy vết.
- **minCostToCut(length,cuts):** trả chi phí tối thiểu và một thứ tự cắt hợp lệ. Kiểm tra length>0, cuts không null và mọi vết cắt là tọa độ nội bộ không trùng; clone/sort đầu vào trước khi xây bảng.
- **verify():** đối chiếu với các lời giải vét cạn nhỏ và mô phỏng lại thứ tự cắt để phát hiện sai lệch giữa bảng DP với hành động thực tế.

Để tránh im lặng tràn số nguyên ở chi phí ma trận, Java dùng **long** kết hợp Math.multiplyExact/Math.addExact. Khi gặp một phép nhân/cộng trung gian vượt long, hàm sẽ ném ArithmeticException thay vì trả số âm do wrap. Điều này cũng có nghĩa **một ứng viên chuyển không biểu diễn được có thể khiến hàm từ chối bài toán**, kể cả khi một thứ tự khác có tổng chi phí còn nằm trong long. Nếu đề cho phép kích thước/cost cực lớn và vẫn phải tìm nghiệm trong mọi trường hợp, cần cân nhắc BigInteger hoặc xử lý miền số khác, không xem việc ném exception là lời giải tối ưu.

Hàm record trong ví dụ trả về mảng int[] cho thứ tự cắt. Vì accessor của record trả tham chiếu mảng, người gọi có thể sửa mảng kết quả; trong API sản xuất cần bản sao phòng vệ hoặc cấu trúc bất biến nếu hợp đồng yêu cầu. Bài minh họa không thay đổi mảng dims hay cuts của người gọi.

Lưu file **IntervalSplitDp.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class IntervalSplitDp {
    public record MatrixPlan(long cost, String parentheses) { }
    public record CutPlan(long cost, int[] cutOrder) { }

    private IntervalSplitDp() { }

    public static MatrixPlan matrixChain(int[] dims) {
        if (dims == null || dims.length < 2) {
            throw new IllegalArgumentException("at least one matrix required");
        }
        for (int d : dims) {
            if (d <= 0) {
                throw new IllegalArgumentException("positive dimensions required");
            }
        }

        int n = dims.length - 1;
        long[][] dp = new long[n][n];
        int[][] split = new int[n][n];
        for (int i = 0; i < n; i++) {
            Arrays.fill(split[i], -1);
        }

        for (int len = 2; len <= n; len++) {
            for (int left = 0; left + len <= n; left++) {
                int right = left + len - 1;
                long best = Long.MAX_VALUE;
                int bestSplit = -1;
                for (int k = left; k < right; k++) {
                    long product = Math.multiplyExact(
                        Math.multiplyExact((long) dims[left], dims[k + 1]),
                        dims[right + 1]);
                    long candidate = Math.addExact(
                        Math.addExact(dp[left][k], dp[k + 1][right]),
                        product);
                    if (bestSplit == -1 || candidate < best) {
                        best = candidate;
                        bestSplit = k;
                    }
                }
                dp[left][right] = best;
                split[left][right] = bestSplit;
            }
        }
        return new MatrixPlan(dp[0][n - 1],
                matrixExpression(0, n - 1, split));
    }

    private static String matrixExpression(int left, int right, int[][] split) {
        if (left == right) {
            return "A" + (left + 1);
        }
        int k = split[left][right];
        return "(" + matrixExpression(left, k, split) + " x "
                + matrixExpression(k + 1, right, split) + ")";
    }

    public static CutPlan minCostToCut(int length, int[] cuts) {
        if (length <= 0 || cuts == null) {
            throw new IllegalArgumentException("positive stick and cuts required");
        }

        int[] sorted = cuts.clone();
        Arrays.sort(sorted);
        for (int i = 0; i < sorted.length; i++) {
            if (sorted[i] <= 0 || sorted[i] >= length
                    || (i > 0 && sorted[i] == sorted[i - 1])) {
                throw new IllegalArgumentException("distinct interior cuts required");
            }
        }

        int m = sorted.length;
        int[] position = new int[m + 2];
        position[0] = 0;
        System.arraycopy(sorted, 0, position, 1, m);
        position[m + 1] = length;

        long[][] dp = new long[m + 2][m + 2];
        int[][] choice = new int[m + 2][m + 2];
        for (int gap = 2; gap < m + 2; gap++) {
            for (int left = 0; left + gap < m + 2; left++) {
                int right = left + gap;
                long best = Long.MAX_VALUE;
                int bestCut = -1;
                for (int k = left + 1; k < right; k++) {
                    long sum = Math.addExact(dp[left][k], dp[k][right]);
                    long candidate = Math.addExact(sum,
                            (long) position[right] - position[left]);
                    if (bestCut == -1 || candidate < best) {
                        best = candidate;
                        bestCut = k;
                    }
                }
                dp[left][right] = bestCut == -1 ? 0L : best;
                choice[left][right] = bestCut;
            }
        }

        int[] order = new int[m];
        int[] cursor = {0};
        reconstructCuts(0, m + 1, position, choice, order, cursor);
        return new CutPlan(dp[0][m + 1], order);
    }

    private static void reconstructCuts(int left, int right,
                                        int[] position, int[][] choice,
                                        int[] result, int[] cursor) {
        int k = choice[left][right];
        if (k <= left || k >= right) {
            return;
        }
        result[cursor[0]++] = position[k];
        reconstructCuts(left, k, position, choice, result, cursor);
        reconstructCuts(k, right, position, choice, result, cursor);
    }

    private static long bruteMatrix(int[] dims, int left, int right) {
        if (left == right) {
            return 0L;
        }
        long best = Long.MAX_VALUE;
        for (int k = left; k < right; k++) {
            long cost = bruteMatrix(dims, left, k)
                    + bruteMatrix(dims, k + 1, right)
                    + (long) dims[left] * dims[k + 1] * dims[right + 1];
            best = Math.min(best, cost);
        }
        return best;
    }

    private static long bruteCutOrders(int length, int[] cuts) {
        return enumerateOrders(length, cuts, new boolean[cuts.length], 0);
    }

    private static long enumerateOrders(int length, int[] cuts,
                                        boolean[] used, int done) {
        if (done == cuts.length) {
            return 0L;
        }

        long best = Long.MAX_VALUE;
        for (int i = 0; i < cuts.length; i++) {
            if (used[i]) {
                continue;
            }
            int left = 0;
            int right = length;
            for (int j = 0; j < cuts.length; j++) {
                if (used[j] && cuts[j] < cuts[i]) {
                    left = Math.max(left, cuts[j]);
                } else if (used[j] && cuts[j] > cuts[i]) {
                    right = Math.min(right, cuts[j]);
                }
            }
            used[i] = true;
            long candidate = (long) right - left
                    + enumerateOrders(length, cuts, used, done + 1);
            used[i] = false;
            best = Math.min(best, candidate);
        }
        return best;
    }

    private static void validateCutOrder(int length, int[] cuts, CutPlan plan) {
        if (plan.cutOrder().length != cuts.length) {
            throw new AssertionError("wrong number of cuts");
        }
        Set<Integer> expected = new HashSet<>();
        for (int cut : cuts) {
            expected.add(cut);
        }
        Set<Integer> performed = new HashSet<>();
        long total = 0L;
        for (int cut : plan.cutOrder()) {
            if (!expected.contains(cut) || !performed.add(cut)) {
                throw new AssertionError("invalid or duplicate cut");
            }
            int left = 0;
            int right = length;
            for (int previous : performed) {
                if (previous == cut) {
                    continue;
                }
                if (previous < cut) {
                    left = Math.max(left, previous);
                } else {
                    right = Math.min(right, previous);
                }
            }
            total += (long) right - left;
        }
        if (performed.size() != cuts.length || total != plan.cost()) {
            throw new AssertionError("cut order and cost disagree");
        }
    }

    private static void verify() {
        int[] options = {1, 2, 4};
        int matrixCases = 0;
        for (int n = 1; n <= 5; n++) {
            int combinations = 1;
            for (int i = 0; i <= n; i++) {
                combinations *= options.length;
            }
            for (int code = 0; code < combinations; code++) {
                int[] dims = new int[n + 1];
                int rest = code;
                for (int i = 0; i <= n; i++) {
                    dims[i] = options[rest % options.length];
                    rest /= options.length;
                }
                int[] original = dims.clone();
                MatrixPlan actual = matrixChain(dims);
                long expected = bruteMatrix(dims, 0, n - 1);
                if (actual.cost() != expected
                        || !Arrays.equals(original, dims)) {
                    throw new AssertionError("matrix mismatch "
                            + Arrays.toString(dims));
                }
                matrixCases++;
            }
        }

        int stickCases = 0;
        for (int length = 1; length <= 7; length++) {
            int choices = 1 << (length - 1);
            for (int mask = 0; mask < choices; mask++) {
                int count = Integer.bitCount(mask);
                int[] cuts = new int[count];
                int at = 0;
                for (int c = length - 1; c >= 1; c--) {
                    if ((mask & (1 << (c - 1))) != 0) {
                        cuts[at++] = c;
                    }
                }
                int[] original = cuts.clone();
                CutPlan actual = minCostToCut(length, cuts);
                long expected = bruteCutOrders(length, cuts);
                validateCutOrder(length, cuts, actual);
                if (actual.cost() != expected
                        || !Arrays.equals(original, cuts)) {
                    throw new AssertionError("cut mismatch");
                }
                stickCases++;
            }
        }

        try {
            matrixChain(new int[] {
                Integer.MAX_VALUE, Integer.MAX_VALUE, Integer.MAX_VALUE
            });
            throw new AssertionError("expected arithmetic overflow");
        } catch (ArithmeticException expected) {
            // Math.multiplyExact must reject an unrepresentable product.
        }
        try {
            minCostToCut(7, new int[] {3, 3});
            throw new AssertionError("expected duplicate-cut rejection");
        } catch (IllegalArgumentException expected) {
            // Duplicate cuts are outside the input contract.
        }

        System.out.println("Verified " + matrixCases
                + " matrix chains: PASS");
        System.out.println("Verified " + stickCases
                + " stick-cut instances: PASS");
        System.out.println("Boundary and overflow checks: PASS");
    }

    public static void main(String[] args) {
        MatrixPlan matrices = matrixChain(new int[] {10, 30, 5, 60});
        System.out.println("Matrix minimum cost: " + matrices.cost());
        System.out.println("Matrix order: " + matrices.parentheses());
        MatrixPlan single = matrixChain(new int[] {7, 11});
        System.out.println("Single matrix: " + single.parentheses()
                + ", cost=" + single.cost());

        CutPlan stick = minCostToCut(7, new int[] {5, 1, 4, 3});
        System.out.println("Stick minimum cost: " + stick.cost());
        System.out.println("Stick cut order: "
                + Arrays.toString(stick.cutOrder()));
        System.out.println("No cuts cost: "
                + minCostToCut(5, new int[0]).cost());

        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IntervalSplitDp.java
java IntervalSplitDp
~~~

Đầu ra chuẩn của chương trình:

~~~text
Matrix minimum cost: 4500
Matrix order: ((A1 x A2) x A3)
Single matrix: A1, cost=0
Stick minimum cost: 16
Stick cut order: [3, 1, 5, 4]
No cuts cost: 0
Verified 1089 matrix chains: PASS
Verified 127 stick-cut instances: PASS
Boundary and overflow checks: PASS
~~~

Dòng Matrix order cho thấy cách đặt ngoặc tối ưu; dòng Stick cut order cho thấy một thứ tự thực hiện cắt được khôi phục từ lựa chọn k của từng đoạn. Với các bài toán có nhiều lời giải hòa chi phí, biểu thức hoặc thứ tự trả về có thể khác mà vẫn đúng.

## 22. Kiểm thử so với lời giải tham chiếu độc lập

**MCM:** bộ kiểm thử sinh tất cả dãy dims có độ dài n+1 với n=1..5 ma trận và mỗi kích thước thuộc {1,2,4}. Số trường hợp:

~~~text
3^2 + 3^3 + 3^4 + 3^5 + 3^6
= 9 + 27 + 81 + 243 + 729
= 1089 chuỗi ma trận.
~~~

Hàm bruteMatrix dùng đệ quy **không memo**, xét mọi phép tách cho từng đoạn, nên vét cạn tất cả cấu trúc đặt ngoặc hợp lệ (các nhánh bị tính lại). Nó dùng cùng mô hình chi phí toán học nhưng không đọc bảng dp. Chương trình so kết quả tối ưu của brute với matrixChain, đồng thời kiểm tra mảng dims ban đầu không bị sửa.

**Cắt thanh:** với mỗi L=1..7, bộ kiểm thử duyệt mọi tập con của các tọa độ nguyên bên trong thanh. Thanh dài L có L−1 mốc nội bộ, nên số bộ dữ liệu tổng cộng:

~~~text
2^0 + 2^1 + 2^2 + 2^3 + 2^4 + 2^5 + 2^6
= 1 + 2 + 4 + 8 + 16 + 32 + 64
= 127 bộ dữ liệu.
~~~

Oracle bruteCutOrders **liệt kê mọi thứ tự vết cắt** bằng backtracking: mỗi lần chọn một vết cắt chưa làm, tìm hai biên của đoạn hiện tại từ các vết cắt đã thực hiện, cộng chi phí đoạn và đệ quy cho các vết còn lại. Đây là một đường kiểm thử khác cách tính bảng DP.

Ngoài so chi phí, validateCutOrder mô phỏng **đúng thứ tự cắt được trả về** và kiểm tra mọi vết cắt xuất hiện đúng một lần, tổng chi phí mô phỏng bằng giá trị đã công bố. Bộ kiểm thử còn xác nhận không làm thay đổi input cuts. Một số ca biên gồm không có vết cắt, một ma trận, vị trí cắt đầu vào không sắp và từ chối vị trí cắt trùng.

**Kiểm tra số học:** phép nhân kích thước Integer.MAX_VALUE ba lần vượt phạm vi long và bị Math.multiplyExact từ chối. Mục tiêu thử này là bảo đảm chương trình không âm thầm trả kết quả sai khi vượt miền biểu diễn, không phải chứng minh một kết quả tối ưu số lớn.

Vét cạn có chi phí rất cao khi n hoặc m tăng (số cách đặt ngoặc tăng theo Catalan; số thứ tự cắt là m!), nên chỉ dùng cho **đầu vào nhỏ**. Kết quả PASS không thay thế chứng minh cấu trúc tối ưu và quy nạp ở trên.

## 23. Sai lầm phổ biến và trường hợp biên

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Không chốt [l,r] hay [l,r) | Lệch chỉ số, mất phần tử | Ghi chính xác định nghĩa đoạn |
| MCM thử k=r | Một đoạn con không nhỏ hơn cha hoặc out-of-range | Dùng l≤k<r |
| Cắt thanh thử k=l hoặc k=r | Tách tại biên, không thực hiện vết cắt nội bộ | Dùng l<k<r |
| Nhầm k đầu/cuối | Khôi phục thứ tự cắt sai | MCM k là phép nhân cuối; thanh k là cắt đầu |
| Quên base case | Giá trị vô cực lan khắp bảng | dp[l][l]=0 hoặc dp[l][l+1]=0 theo bài |
| Duyệt sai thứ tự | Đọc trạng thái chưa tính | Duyệt theo độ dài hoặc khoảng cách biên tăng |
| Dùng chi phí của một đoạn sai | Có thể tối ưu một bài toán khác | Chứng minh công thức combine từ đề |
| Chọn điểm giữa theo cảm tính | Có thể bỏ nghiệm tối ưu | Duyệt mọi k nếu không có định lý tối ưu mạnh hơn |
| Không lưu choice | Chỉ có giá trị, không dựng được phương án | Lưu k mỗi khi cập nhật tối ưu |
| Dùng chỉ số mốc thay vì tọa độ thật | Tính sai chi phí cắt thanh | Dùng position[r]−position[l] |
| Không sort các tọa độ cắt | Hai đoạn con không còn đúng thứ tự tọa độ | Clone rồi sort và kiểm tra |
| Cho phép cắt trùng/ngoài thanh | Đặc tả vô hiệu | Từ chối 0, L, trùng và tọa độ ngoài |
| Chỉ tính với int | Chi phí MCM có thể tràn | Dùng long với phép toán kiểm tra overflow |
| Nêu O(n²) do bảng n² ô | Quên vòng thử k | Đếm tổng số điểm tách, thường O(n³) |
| Lấy max thay vì min | Tối ưu sai mục tiêu | Xác định min/max và giá trị khởi tạo |
| Kiểm tra chỉ cost, không kiểm tra cấu trúc | Có thể trả biểu thức hoặc thứ tự không hợp lệ | Dùng truy vết và mô phỏng lời giải |
| Không xét n=1 hoặc m=0 | Tạo vòng sai hoặc kết quả sai | Base case và khởi tạo rõ ràng |

Một số lỗi có thể xuất hiện ngay ở đoạn rất nhỏ:

- Hai ma trận: chỉ có một k, nên dễ xác minh phép nhân.
- Ba ma trận: có hai k, đủ để lộ sai công thức chi phí kết hợp.
- Thanh không có cuts: đáp án 0, không được cố đọc choice chưa tồn tại.
- Thanh có đúng một vết cắt: chi phí phải bằng L, vì lần cắt đầu diễn ra trên toàn bộ thanh.
- Thanh có nhiều vết cắt trùng nhau: không thuộc hợp đồng của ví dụ, phải báo lỗi chứ không tính chi phí lặp.

## 24. Quy trình thiết kế interval DP trong một bài mới

Trước khi code:

1. **Viết đặc tả:** lựa chọn cấu trúc nào, mục tiêu min/max, có cần in phương án hay chỉ giá trị?
2. **Định nghĩa đoạn:** [l,r], [l,r) hay cặp biên đã chuẩn hóa. L và R là chỉ số phần tử hay chỉ số tọa độ?
3. **Đặt ý nghĩa trạng thái:** dp[l][r] là chi phí tối ưu của đúng **đơn vị công việc nào** trong đoạn đó?
4. **Chọn thao tác quyết định:** k là phép ghép cuối, vết cắt đầu, gốc của cây hay điểm chia?
5. **Xác định con sau khi chọn k:** [l,k], [k+1,r] hay [l,k], [k,r] theo mốc biên? Có độc lập thật không?
6. **Tính chi phí của quyết định:** biểu thức combineCost đến từ đâu, có phụ thuộc lời giải chi tiết bên trong con không?
7. **Viết base case:** đoạn nhỏ nhất có chi phí/giá trị gì, mảng rỗng được chấp nhận không?
8. **Chứng minh có tiến độ:** mọi con nhỏ hơn cha để đệ quy dừng và bottom-up duyệt theo độ dài.
9. **Chứng minh đúng:** mỗi nghiệm có một k phân rã, và ghép hai nghiệm con tối ưu với k tạo nghiệm hợp lệ.
10. **Phân tích:** đếm số đoạn, tổng điểm tách, chi phí mỗi ứng viên, tiền xử lý và bộ nhớ.
11. **Thiết kế truy vết:** nếu cần in đáp án, lưu choice và viết thứ tự dựng đúng với ngữ nghĩa k.
12. **Tạo oracle:** vét cạn cấu trúc/hoán vị nhỏ, so giá trị và mô phỏng phương án, kiểm tra đầu vào biên.
13. **Chỉ tối ưu sau khi đúng:** nếu tìm cách giảm O(n³), chứng minh tính đơn điệu hoặc dạng bất đẳng thức cần thiết.

Checklist này giúp phân biệt bài toán có **optimal substructure thực sự** với bài chỉ trông giống DP vì có khoảng l,r và vài vòng lặp.

## 25. Bài tập thực hành

**Bài 1 — MCM bốn ma trận:** cho dims=[40,20,30,10,30]. Lập bảng dp theo độ dài 1..4, ghi split ứng với mỗi đoạn và dựng dấu ngoặc có chi phí nhỏ nhất. So với việc nhân hoàn toàn từ trái sang phải. Chú ý công thức kích thước hai nhóm khi chọn k.

**Bài 2 — Đếm điểm tách:** với n=5 ma trận, liệt kê mọi đoạn dài 2,3,4,5 và số k mỗi đoạn. Kiểm chứng tổng phép thử đúng bằng (n³−n)/6; phân biệt số trạng thái O(n²) với số ứng viên O(n³).

**Bài 3 — Cắt thanh:** cho L=9 và các điểm cắt [2,4,6,7]. Tạo position, dp, choice. Thử ít nhất hai điểm k cho đoạn [0,L], giải thích vì sao một điểm cắt ở giữa chưa chắc luôn tối ưu khi phân bố điểm cắt không đều.

**Bài 4 — Thay đổi chi phí cắt:** giả sử chi phí cắt một đoạn dài x không còn là x mà là x². Sửa biểu thức combineCost và phân tích liệu chứng minh quy hoạch động còn giữ được hay không. Nếu tính x² với x lớn, cần xử lý tràn số như thế nào?

**Bài 5 — Đếm số cấu trúc tối ưu:** mở rộng MCM để lưu số cách đặt ngoặc có chi phí nhỏ nhất bên cạnh cost. Khi hai k khác nhau cho cùng chi phí, cần cộng số cách của hai con như thế nào? Phân biệt **số cây phép nhân** với **một biểu thức minh họa**.

**Bài 6 — So sánh top-down và bottom-up:** triển khai MCM với memoization, thử tất cả k và so với bảng theo độ dài. Đếm số trạng thái thực sự được tính và độ sâu recursion; giải thích vì sao bộ nhớ stack cần xét riêng.

**Bài 7 — Phân tích mô hình:** cho bài tối ưu thứ tự ghép nhiều tệp, chi phí ghép hai nhóm bằng tổng kích thước của hai nhóm. Hãy kiểm tra bài toán có cho phép **đổi thứ tự các tệp** hay phải giữ nguyên thứ tự; nếu được đổi tự do, mô hình interval DP trên thứ tự ban đầu có thể là một hạn chế không đúng của đề.

**Câu hỏi tự kiểm tra:** Tại sao MCM chọn phép nhân cuối trong khi cắt thanh chọn vết cắt đầu? Tại sao dp[l][r] của thanh dùng hai *mốc biên* chứ không phải hai chỉ số phần tử được xử lý? Vì sao O(n²) bảng không đồng nghĩa O(n²) thời gian? Khi nào cần thêm tham số ngoài l,r để giữ tính độc lập sau khi chọn k?

**Kết luận:** quy hoạch động trên đoạn mạnh nhất khi mỗi lựa chọn k **chia bài toán cha thành các bài toán con độc lập và nhỏ hơn**, đồng thời chi phí ghép/tách được xác định đúng theo đặc tả. Hãy bắt đầu từ **nghĩa của dp[l][r] → trường hợp cơ sở → miền k → công thức combine → thứ tự theo độ dài → truy vết**. Công thức chỉ là hình thức; chính chứng minh cấu trúc tối ưu và khả năng khôi phục một lời giải hợp lệ mới quyết định thuật toán có đúng hay không.
