Câu 1: Khi viết T(n) thuộc O(g(n)), điều nào được đảm bảo?
A. T(n) bằng chính xác g(n) với mọi kích thước đầu vào
B. T(n) luôn nhỏ hơn g(n) với mọi kích thước đầu vào
C. T(n) bị chặn trên bởi hằng số nhân g(n) khi n đủ lớn
D. T(n) có cận dưới chặt bằng g(n) khi n đủ lớn
Đáp án đúng: C

Câu 2: Ký hiệu Theta(g(n)) diễn tả kiểu cận nào?
A. Có cận trên nhưng chưa khẳng định cận dưới
B. Có cả cận trên và cận dưới cùng bậc tiệm cận
C. Có cận dưới nhưng chưa khẳng định cận trên
D. Có tốc độ luôn bằng nhau ở mọi giá trị n
Đáp án đúng: B

Câu 3: Khi viết T(n) thuộc Omega(g(n)), ta đang nêu điều gì?
A. Một cận trên tiệm cận cho chi phí thuật toán
B. Một thời gian trung bình đo được cho thuật toán
C. Một cận dưới tiệm cận cho chi phí thuật toán
D. Một dung lượng bộ nhớ chính xác của thuật toán
Đáp án đúng: C

Câu 4: Với T(n) = 3n^2 + 7n + 10, bậc tăng chặt là gì?
A. Theta(n)
B. Theta(log n)
C. Theta(n^3)
D. Theta(n^2)
Đáp án đúng: D

Câu 5: Vòng ngoài chạy i từ 1 đến n, vòng trong chạy i lần: tổng bước là bao nhiêu?
A. Theta(n log n)
B. Theta(n^2)
C. Theta(n sqrt n)
D. Theta(n^3)
Đáp án đúng: B

Câu 6: Vòng lặp tăng i gấp đôi từ 1 đến khi i >= n, độ phức tạp là gì?
A. Theta(n log n)
B. Theta(sqrt n)
C. Theta(log log n)
D. Theta(log n)
Đáp án đúng: D

Câu 7: Nghiệm của T(n) = T(n/2) + Theta(1) thường là gì?
A. Theta(log n)
B. Theta(n log n)
C. Theta(log log n)
D. Theta(sqrt n)
Đáp án đúng: A

Câu 8: Nghiệm của T(n) = 2T(n/2) + Theta(n) thường là gì?
A. Theta(n^1.5)
B. Theta(n log^2 n)
C. Theta(n^2 log n)
D. Theta(n log n)
Đáp án đúng: D

Câu 9: Quicksort luôn chọn pivot làm lệch phân hoạch thành 0 và n-1, thời gian xấu nhất?
A. Theta(n^2) do phải xử lý nhiều phân hoạch lệch
B. Theta(n log n) do mỗi phân hoạch được chia đều
C. Theta(log n) do chỉ xử lý một nhánh đệ quy
D. Theta(n) do chỉ cần một lần phân hoạch dữ liệu
Đáp án đúng: A

Câu 10: Đệ quy chia đôi đầu vào, xử lý tuần tự các nhánh, dùng bao nhiêu ô stack?
A. Theta(log n) ô stack theo độ sâu lời gọi
B. Theta(n) ô stack theo độ sâu lời gọi
C. Theta(n^2) ô stack theo độ sâu lời gọi
D. Theta(log log n) ô stack theo độ sâu lời gọi
Đáp án đúng: A

Câu 11: Muốn dùng loop invariant chứng minh vòng lặp đúng, cần điều gì?
A. Đúng sau bước đầu, giữ ở một nhánh và đủ kết luận
B. Đúng lúc đầu, giữ qua mỗi bước và đủ để kết luận
C. Đúng với vài đầu vào, giữ khi test và đủ kết luận
D. Đúng khi n nhỏ, giữ trên bản debug và đủ kết luận
Đáp án đúng: B

Câu 12: Điều kiện nào đủ để chứng minh một vòng lặp chắc chắn dừng?
A. Đại lượng nguyên không âm giảm nghiêm ngặt mỗi vòng
B. Đại lượng nguyên không âm tăng nghiêm ngặt mỗi vòng
C. Đại lượng thực giảm nhưng không có cận dưới rõ ràng
D. Đại lượng không đổi dù số phép tính có thể giảm
Đáp án đúng: A

Câu 13: Theo phân tích truy hồi, T(n) = 4T(n/2) + Theta(n) có bậc nào?
A. Tăng tuyến tính nhân log: Theta(n log n)
B. Tăng bậc hai theo n: Theta(n^2)
C. Tăng bậc ba theo n: Theta(n^3)
D. Tăng bậc hai nhân log: Theta(n^2 log n)
Đáp án đúng: B

Câu 14: Với mảng động tăng gấp đôi dung lượng, chi phí khấu hao mỗi append là gì?
A. O(n) ở mọi lần thêm kể cả khi còn dung lượng
B. O(log n) ở mọi lần thêm kể cả khi còn dung lượng
C. O(n log n) trên chuỗi thao tác dù không sao chép
D. O(1) trên chuỗi thao tác dù có lần sao chép O(n)
Đáp án đúng: D

Câu 15: Thực hiện m lần append vào mảng động tăng gấp đôi có tổng chi phí bậc nào?
A. Theta(m log m) thao tác tổng cộng
B. Theta(m^2) thao tác tổng cộng
C. Theta(m) thao tác tổng cộng
D. Theta(m sqrt m) thao tác tổng cộng
Đáp án đúng: C

Câu 16: Trong phương pháp thế năng của phân tích khấu hao, ý tưởng chính là gì?
A. Dự trữ thế năng tùy ý để xóa mọi chi phí tệ nhất
B. Dự trữ thế năng cố định thay cho đo lường thực nghiệm
C. Dự trữ thế năng không âm để chi trả thao tác tốn kém
D. Dự trữ thế năng bằng số bước để bỏ qua mọi truy hồi
Đáp án đúng: C

Câu 17: Quicksort chọn pivot ngẫu nhiên có chi phí kỳ vọng và xấu nhất ra sao?
A. Kỳ vọng Theta(n log n), tệ nhất Theta(n^2)
B. Kỳ vọng Theta(n^2), xấu nhất Theta(n log n)
C. Kỳ vọng Theta(n), xấu nhất Theta(n log n)
D. Kỳ vọng Theta(log n), xấu nhất Theta(n^2)
Đáp án đúng: A

Câu 18: Thuật toán ngẫu nhiên loại Las Vegas được đặc trưng bởi điều gì?
A. Luôn chạy số bước cố định, kết quả có thể ngẫu nhiên
B. Luôn trả kết quả gần đúng, thời gian chạy cố định
C. Luôn trả kết quả đúng, thời gian chạy có thể ngẫu nhiên
D. Luôn dùng bộ nhớ hằng số, thời gian chạy ngẫu nhiên
Đáp án đúng: C

Câu 19: Cận dưới Omega(n log n) cho sắp xếp dựa trên so sánh đến từ đâu?
A. Cây quyết định phải phân biệt n! hoán vị đầu vào
B. Cây quyết định chỉ cần phân biệt n hoán vị đầu vào
C. Cây quyết định có tối đa n^2 lá với mọi giá trị n
D. Cây quyết định chỉ cần một phép so để phân biệt
Đáp án đúng: A

Câu 20: Với work W, span S, p bộ xử lý, cận dưới thời gian song song là gì?
A. T_p >= min(W/p, S) vì chỉ cần đáp ứng một cận riêng
B. T_p >= max(W/p, S) vì bị chặn bởi work và span
C. T_p <= max(W/p, S) với mọi lịch chạy hợp lệ
D. T_p = W/p + S với mọi lịch chạy hợp lệ
Đáp án đúng: B

Câu 21: Theo định luật Amdahl, nếu 10% tác vụ bắt buộc tuần tự, tăng tốc tối đa là gì?
A. Giới hạn tăng tốc xấp xỉ 100 lần
B. Giới hạn tăng tốc xấp xỉ 1 lần
C. Giới hạn tăng tốc không bị ràng buộc
D. Giới hạn tăng tốc xấp xỉ 10 lần
Đáp án đúng: D

Câu 22: Trong mô hình external-memory, đại lượng nào thường được đếm?
A. Số lần so sánh key bên trong bộ nhớ chính của CPU
B. Số phép toán số học thực hiện trong các thanh ghi CPU
C. Số lần truyền các block giữa bộ nhớ ngoài và RAM
D. Số byte của chương trình sau khi được biên dịch
Đáp án đúng: C

Câu 23: Muốn đo thực nghiệm độ tăng trưởng thuật toán đáng tin cậy, nên làm gì?
A. Đo một kích thước, lấy lần nhanh nhất rồi bỏ warm-up
B. Đo nhiều kích thước, chỉ lấy lần đầu và bỏ nhiễu
C. Đo một kích thước, tăng số thread rồi suy ra độ phức tạp
D. Đo nhiều kích thước, chạy lặp và kiểm soát warm-up/cache
Đáp án đúng: D

Câu 24: Khi chọn thuật toán cho dữ liệu rất lớn, cách đánh giá nào phù hợp nhất?
A. Chỉ xét số phép so sánh và bỏ chi phí I/O ở mọi quy mô
B. Đánh đổi thời gian, bộ nhớ và chi phí I/O theo quy mô
C. Chỉ xét độ phức tạp tệ nhất và bỏ giới hạn bộ nhớ
D. Chỉ xét benchmark nhỏ và áp dụng kết quả cho mọi quy mô
Đáp án đúng: B
