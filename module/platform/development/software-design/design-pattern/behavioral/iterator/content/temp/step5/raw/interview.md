Bạn sẽ giải thích mục đích của mẫu Iterator khi muốn duyệt tập hợp mà không làm lộ cấu trúc lưu trữ bên trong như thế nào?
Bạn sẽ phân biệt vai trò của aggregate, iterator và mã sử dụng trong một ví dụ quản lý danh sách công việc ra sao?
Bạn sẽ xác định khi nào một lớp Java tự quản lý tập hợp nên triển khai Iterable như thế nào?
Bạn sẽ giải thích mối quan hệ giữa Iterable.iterator() và cú pháp for-each của Java ra sao?
Bạn sẽ thiết kế một Iterator có hasNext và next để duyệt từng phần tử theo thứ tự như thế nào?
Bạn sẽ xác định bất biến của vị trí con trỏ trước và sau mỗi lần gọi next trong một iterator ra sao?
Bạn sẽ xử lý lần gọi next khi không còn phần tử theo hợp đồng Iterator của Java như thế nào?
Bạn sẽ phân biệt cách hasNext kiểm tra sự tồn tại phần tử với cách next lấy phần tử và tiến con trỏ ra sao?
Bạn sẽ kiểm chứng rằng việc gọi hasNext nhiều lần không tự làm bỏ qua phần tử như thế nào?
Bạn sẽ thiết kế iterator cho một tập hợp rỗng để các phương thức trả hành vi nhất quán như thế nào?
Bạn sẽ tổ chức nhiều iterator độc lập cùng duyệt một collection mà không chia sẻ nhầm trạng thái vị trí ra sao?
Bạn sẽ xác định khi nào cần trả iterator mới thay vì tái sử dụng iterator đã duyệt một phần như thế nào?
Bạn sẽ thiết kế iterator cho cấu trúc cây khi muốn duyệt theo thứ tự tiền tự, trung tự hoặc hậu tự ra sao?
Bạn sẽ lựa chọn sử dụng stack tường minh hay đệ quy khi viết iterator cho cây rất sâu như thế nào?
Bạn sẽ biểu diễn iterator cho cấu trúc danh sách liên kết mà không yêu cầu client biết nút hoặc con trỏ nội bộ ra sao?
Bạn sẽ thiết kế một iterator lọc bỏ phần tử không hợp lệ mà vẫn giữ đúng hợp đồng hasNext và next như thế nào?
Bạn sẽ xây dựng iterator lười tính toán để chỉ tạo giá trị khi client thật sự yêu cầu ra sao?
Bạn sẽ nhận diện nguy cơ gọi hasNext kích hoạt I/O hoặc xử lý tốn kém và cách công bố hành vi đó như thế nào?
Bạn sẽ xác định cách duyệt một tập dữ liệu lớn từ cơ sở dữ liệu theo trang mà không tải toàn bộ vào bộ nhớ ra sao?
Bạn sẽ quản lý tài nguyên mạng hoặc file khi iterator đang đọc dở và người dùng ngừng duyệt như thế nào?
Bạn sẽ phân biệt Iterator chỉ duyệt một lần với một collection có thể tạo iterator mới cho nhiều lượt duyệt như thế nào?
Bạn sẽ lựa chọn khi nào trả Iterator và khi nào trả Iterable trong API công khai theo nhu cầu người gọi như thế nào?
Bạn sẽ so sánh Iterator với Stream API Java khi xử lý các bước lọc, biến đổi và tổng hợp dữ liệu ra sao?
Bạn sẽ phân biệt iterator tuần tự thông thường với Spliterator khi cần chia dữ liệu để xử lý song song như thế nào?
Bạn sẽ xác định tiêu chí để một iterator hỗ trợ phương thức remove và cách thông báo nếu thao tác không được hỗ trợ ra sao?
Bạn sẽ kiểm tra điều kiện gọi remove chỉ sau một lần next hợp lệ và tránh gọi remove lặp lại sai hợp đồng như thế nào?
Bạn sẽ thiết kế remove để xóa đúng phần tử vừa trả về mà vị trí duyệt tiếp theo vẫn chính xác ra sao?
Bạn sẽ phân tích nguy cơ sửa trực tiếp collection trong lúc đang duyệt bằng iterator không hỗ trợ thay đổi như thế nào?
Bạn sẽ giải thích điều kiện một iterator kiểu fail-fast có thể ném ConcurrentModificationException và giới hạn bảo đảm của nó ra sao?
Bạn sẽ phân biệt thay đổi cấu trúc collection với cập nhật giá trị phần tử khi xét tính hợp lệ của iterator như thế nào?
Bạn sẽ lựa chọn dùng snapshot iterator khi cần một lượt duyệt ổn định bất chấp thay đổi bên ngoài như thế nào?
Bạn sẽ cân nhắc chi phí sao chép bộ nhớ khi dùng snapshot iterator cho dữ liệu lớn ra sao?
Bạn sẽ phân biệt iterator fail-fast với iterator có tính nhất quán yếu trong các collection đồng thời của Java như thế nào?
Bạn sẽ xác định liệu iterator của một collection có thể được dùng an toàn bởi nhiều luồng hay không bằng những tiêu chí nào?
Bạn sẽ thiết kế cơ chế đồng bộ khi nhiều luồng cùng sửa collection trong lúc một luồng duyệt như thế nào?
Bạn sẽ đánh giá việc giữ khóa trong suốt lượt duyệt có thể làm giảm thông lượng hoặc gây deadlock ra sao?
Bạn sẽ quyết định khi nào dùng CopyOnWriteArrayList để ưu tiên đọc nhiều hơn ghi trong quá trình duyệt như thế nào?
Bạn sẽ giải thích cách ListIterator hỗ trợ di chuyển tiến và lùi khác với Iterator thông thường ra sao?
Bạn sẽ xử lý nextIndex và previousIndex khi ListIterator ở đầu hoặc cuối danh sách như thế nào?
Bạn sẽ kiểm soát ngữ nghĩa của add, set và remove khi cài đặt một ListIterator có thể sửa danh sách ra sao?
Bạn sẽ xây dựng iterator cho danh sách có phần tử null mà không nhầm null với tín hiệu hết phần tử như thế nào?
Bạn sẽ định nghĩa thứ tự duyệt của một cấu trúc không có thứ tự tự nhiên để người dùng API không đưa ra giả định sai ra sao?
Bạn sẽ cân nhắc cách xử lý khi một iterator duyệt vô hạn hoặc nguồn dữ liệu liên tục sinh phần tử như thế nào?
Bạn sẽ kiểm thử lượt duyệt một phần rồi tiếp tục để xác minh iterator không lặp hoặc bỏ sót phần tử ra sao?
Bạn sẽ thiết kế unit test cho hasNext, next và remove ở các vị trí biên bằng dữ liệu tối thiểu như thế nào?
Bạn sẽ xác minh hai iterator được tạo từ cùng aggregate có thể tiến độc lập và cho kết quả đúng ra sao?
Bạn sẽ kiểm thử iterator khi collection thay đổi giữa hai lần gọi next theo hợp đồng nhất quán đã chọn như thế nào?
Bạn sẽ thiết kế kiểm thử cho iterator đọc theo trang khi nguồn dữ liệu trả trang rỗng, lỗi hoặc thay đổi thứ tự ra sao?
Bạn sẽ phân biệt các lỗi do thuật toán duyệt với lỗi từ nguồn dữ liệu phía sau trong thông báo ngoại lệ như thế nào?
Bạn sẽ đánh giá khi nào việc tự xây dựng iterator làm hệ thống phức tạp hơn so với dùng collection hoặc API Java sẵn có ra sao?
