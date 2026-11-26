Mảng hỗ trợ truy cập phần tử theo chỉ số i với độ phức tạp thời gian thường là gì?
A. O(n), do phải duyệt từ phần tử đầu đến i
B. O(log n), do chia đôi dải chỉ số liên tục
C. O(1), do tính được vị trí từ chỉ số i
D. O(n log n), do phải sắp xếp trước khi đọc
Đáp án đúng: C

Khi thêm phần tử vào cuối dynamic array, phát biểu nào chính xác?
A. Luôn O(1) ngay cả khi phải cấp lại mảng
B. Luôn O(log n) theo kích thước mảng hiện có
C. O(1) khấu hao; đôi lúc nới mảng tốn O(n)
D. Luôn O(n) ngay cả khi mảng vẫn còn chỗ
Đáp án đúng: C

Với singly linked list, đã có node trước vị trí chèn, thời gian chèn thường là gì?
A. O(n), vì phải tìm lại node bắt đầu từ head
B. O(log n), do các node được nối theo tầng
C. O(n log n), vì phải sắp xếp node trước khi nối
D. O(1), vì chỉ cần cập nhật vài liên kết cục bộ
Đáp án đúng: D

Truy cập phần tử thứ k của linked list thông thường tốn chi phí nào?
A. O(1), vì đã có địa chỉ trực tiếp tại k
B. O(n), vì phải đi từ node đầu đến k
C. O(log n), vì có thể chia đôi tập node
D. O(n log n), vì cần sắp xếp các node trước
Đáp án đúng: B

Stack phù hợp với tính năng undo vì nguyên tắc lấy phần tử nào?
A. FIFO, phần tử đưa vào sớm nhất lấy trước
B. Ưu tiên, phần tử có điểm cao nhất lấy trước
C. Theo chỉ số, phần tử ở vị trí nhỏ nhất lấy trước
D. LIFO, phần tử mới đưa vào được lấy ra trước
Đáp án đúng: D

Queue thông thường tuân theo FIFO sẽ phục vụ phần tử nào trước?
A. Phần tử vào hàng sớm nhất trong số mục đang chờ
B. Phần tử có ưu tiên cao nhất trong số mục đang chờ
C. Phần tử vào hàng mới nhất trong số mục đang chờ
D. Phần tử có giá trị nhỏ nhất trong số mục đang chờ
Đáp án đúng: A

Bảng băm với phân phối hash tốt có thời gian tìm kiếm trung bình nào?
A. O(n) vì luôn phải so sánh tuần tự toàn bộ khóa
B. O(1) khi mức tải và va chạm được kiểm soát
C. O(log n) vì luôn truy cập cây tìm kiếm cân bằng
D. O(n log n) vì cần sắp xếp lại mọi bucket
Đáp án đúng: B

Hai khóa khác nhau có cùng giá trị băm; bảng băm cần làm gì để tra cứu đúng?
A. Coi hai khóa là một vì giá trị băm giống nhau
B. Đối chiếu khóa thực để phân biệt các phần tử
C. Bỏ một khóa để bảo đảm mỗi hash chỉ xuất hiện một lần
D. Đổi thứ tự bucket mà không kiểm tra khóa gốc
Đáp án đúng: B

Trong BST chứa các khóa khác nhau, bất biến nào luôn đúng?
A. Khóa cây con trái luôn nhỏ hơn khóa tại nút
B. Mọi node lá luôn nằm ở cùng một mức sâu
C. Khóa tại gốc luôn nhỏ nhất trong toàn cây
D. Mỗi nút phải có đúng hai nút con hợp lệ
Đáp án đúng: A

BST không tự cân bằng bị lệch hoàn toàn, tra cứu xấu nhất có chi phí nào?
A. O(1), vì mỗi node đều có một địa chỉ bộ nhớ
B. O(n), vì chiều cao cây có thể tăng đến n
C. O(log n), vì mọi cây nhị phân luôn cân bằng
D. O(n log n), vì cần sắp xếp lại từng khóa
Đáp án đúng: B

Trong max-heap, phần tử nào được bảo đảm nằm ở nút gốc?
A. Phần tử có khóa lớn nhất trong heap
B. Phần tử mới thêm vào heap ở lần gần nhất
C. Phần tử có chỉ số chèn nhỏ nhất trong heap
D. Phần tử có độ sâu lớn nhất của cây heap
Đáp án đúng: A

Lấy phần tử lớn nhất khỏi binary max-heap thường có chi phí nào?
A. O(1), vì đã có sẵn phần tử tại nút gốc
B. O(n), vì phải duyệt lại toàn bộ các nút
C. O(log n), do hiệu chỉnh dọc chiều cao heap
D. O(n log n), vì sắp xếp lại tất cả phần tử
Đáp án đúng: C

Đối với đồ thị thưa, adjacency list có ưu thế bộ nhớ nào?
A. Dùng O(V²) ô cho mọi cặp đỉnh có thể có
B. Dùng O(E²) ô để lưu toàn bộ đỉnh và cạnh
C. Dùng O(log V) ô cho tất cả các đỉnh và cạnh
D. Dùng O(V+E) chỗ cho đỉnh và cạnh được lưu
Đáp án đúng: D

Trên đồ thị không trọng số, thuật toán nào tìm đường đi ít cạnh nhất từ nguồn?
A. BFS, vì duyệt các mức khoảng cách từ nguồn
B. DFS, vì luôn đi sâu trước khi thử nhánh còn lại
C. Prim, vì nối cạnh vào một cây có trọng số nhỏ
D. Kruskal, vì ưu tiên cạnh không gây chu trình
Đáp án đúng: A

Trong DFS đồ thị có hướng, dấu hiệu nào nhận biết một back edge tạo chu trình?
A. Gặp đỉnh đã hoàn tất từ nhánh duyệt trước
B. Gặp đỉnh có bậc ra lớn hơn bậc vào
C. Gặp đỉnh thuộc một thành phần liên thông
D. Gặp đỉnh còn trên ngăn xếp gọi DFS
Đáp án đúng: D

Bất biến của một cấu trúc dữ liệu nên được bảo toàn khi nào?
A. Chỉ sau khi khởi tạo object trong constructor
B. Chỉ sau khi chạy hết bộ kiểm thử hiệu năng
C. Trước và sau thao tác cập nhật dữ liệu
D. Chỉ khi số lượng phần tử chạm ngưỡng tối đa
Đáp án đúng: C
