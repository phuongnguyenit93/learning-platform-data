Bạn sẽ phân biệt refactoring với sửa lỗi, tối ưu hiệu năng và viết lại chức năng từ đầu như thế nào?
Bạn sẽ giải thích thế nào là hành vi quan sát được cần được bảo toàn trong một lần refactor Java ra sao?
Bạn sẽ nhận diện những code smell nào cho thấy một lớp đang ôm quá nhiều trách nhiệm như thế nào?
Bạn sẽ phân biệt code smell với một lỗi thiết kế đã được chứng minh gây khó bảo trì ra sao?
Bạn sẽ quyết định có nên refactor ngay hay trì hoãn khi đoạn mã ít thay đổi nhưng có nhiều dấu hiệu phức tạp như thế nào?
Bạn sẽ sử dụng lịch sử thay đổi và lỗi để chọn điểm nóng cần refactor trước ra sao?
Bạn sẽ xác định mức độ an toàn của một refactor khi chưa có đủ kiểm thử cho hành vi hiện tại như thế nào?
Bạn sẽ viết characterization test để ghi nhận hành vi của mã cũ, kể cả trường hợp hành vi đó chưa lý tưởng, ra sao?
Bạn sẽ chọn ranh giới kiểm thử nào để bảo vệ hành vi mà không ràng buộc test vào cấu trúc lớp hiện tại như thế nào?
Bạn sẽ chia một lần refactor lớn thành những thay đổi nhỏ, mỗi bước đều có thể kiểm chứng và hoàn nguyên, ra sao?
Bạn sẽ sử dụng chức năng đổi tên của IDE để cập nhật các tham chiếu đến lớp hoặc phương thức Java một cách an toàn như thế nào?
Bạn sẽ quyết định khi nào nên áp dụng Extract Method để giảm độ dài và làm rõ ý nghĩa của một khối mã ra sao?
Bạn sẽ nhận biết một phương thức vừa trích xuất có quá nhiều tham số và cần thiết kế lại ranh giới dữ liệu như thế nào?
Bạn sẽ phân biệt Extract Class với việc chỉ chuyển vài phương thức sang lớp tiện ích không có trách nhiệm rõ ràng ra sao?
Bạn sẽ dùng Move Method để đưa hành vi đến gần dữ liệu mà nó sử dụng nhiều nhất như thế nào?
Bạn sẽ xác định khi nào Inline Method giúp mã dễ đọc hơn thay vì tạo thêm các tầng lời gọi không cần thiết ra sao?
Bạn sẽ đánh giá việc Introduce Parameter Object có làm rõ nhóm tham số hay chỉ che giấu một danh sách tham số dài như thế nào?
Bạn sẽ thay thế magic number hoặc chuỗi điều khiển bằng tên và kiểu dữ liệu mang ý nghĩa nghiệp vụ ra sao?
Bạn sẽ xử lý Primitive Obsession bằng value object trong Java mà không tạo quá nhiều lớp nhỏ thiếu giá trị như thế nào?
Bạn sẽ phát hiện và hợp nhất mã trùng lặp khi hai nhánh có vẻ giống nhau nhưng khác một quy tắc nghiệp vụ quan trọng ra sao?
Bạn sẽ áp dụng Replace Conditional with Polymorphism khi các nhánh điều kiện thay đổi theo loại đối tượng như thế nào?
Bạn sẽ quyết định lúc nào nên dùng Strategy thay vì cây kế thừa sau khi tách một khối điều kiện lớn ra sao?
Bạn sẽ giảm Feature Envy khi một phương thức thường xuyên truy cập chi tiết của đối tượng khác như thế nào?
Bạn sẽ xác định cách cải thiện một lớp có quá nhiều biến trạng thái có thể thay đổi mà vẫn bảo toàn thứ tự thao tác ra sao?
Bạn sẽ dùng Encapsulate Field để ngăn các lớp khác thay đổi trạng thái trực tiếp mà không làm hỏng hợp đồng hiện có như thế nào?
Bạn sẽ giảm mức độ phụ thuộc giữa service và database khi một phương thức vừa xử lý nghiệp vụ vừa viết SQL ra sao?
Bạn sẽ xác định ranh giới interface phù hợp khi tách dependency, tránh tạo interface cho mọi lớp mà không có lý do như thế nào?
Bạn sẽ xử lý dependency cycle giữa hai package Java theo các bước nhỏ và dễ kiểm thử ra sao?
Bạn sẽ thay thế một singleton tự quản lý hoặc trạng thái toàn cục để kiểm thử được mà không làm thay đổi vòng đời đối tượng như thế nào?
Bạn sẽ dùng dependency injection như một kỹ thuật tạo điểm nối để refactor mã đang gọi trực tiếp dịch vụ bên ngoài ra sao?
Bạn sẽ kiểm soát thứ tự tác dụng phụ khi tách phương thức đang vừa ghi database vừa gửi thông báo như thế nào?
Bạn sẽ bảo vệ ranh giới transaction trong quá trình chuyển logic từ controller sang application service ra sao?
Bạn sẽ kiểm tra ảnh hưởng của refactor đến thứ tự ném ngoại lệ, mã lỗi và nội dung phản hồi mà consumer có thể quan sát như thế nào?
Bạn sẽ xử lý một refactor liên quan đến đồng bộ hóa và nhiều luồng mà các unit test tuần tự không phát hiện được lỗi ra sao?
Bạn sẽ lựa chọn bước cải tiến cấu trúc dữ liệu khi một collection đang bị sửa từ nhiều vị trí và dễ gây lỗi như thế nào?
Bạn sẽ đánh giá rủi ro của việc thay một cấu trúc mutable bằng immutable khi mã hiện tại dựa vào chia sẻ tham chiếu ra sao?
Bạn sẽ phối hợp các phép refactor với generics để tăng an toàn kiểu mà không làm thay đổi cách API được sử dụng như thế nào?
Bạn sẽ bảo đảm refactor không vô tình thay đổi định dạng dữ liệu lưu trữ hoặc serialization của đối tượng Java ra sao?
Bạn sẽ thiết kế chiến lược chuyển dần API cũ sang API mới khi nhiều module đang gọi phương thức cần refactor như thế nào?
Bạn sẽ sử dụng kỹ thuật branch by abstraction để thay triển khai từng phần mà không buộc dừng phát triển tính năng ra sao?
Bạn sẽ xác định khi nào nên sử dụng feature flag cho quá trình thay đổi cấu trúc và những rủi ro do hai nhánh cùng tồn tại như thế nào?
Bạn sẽ tổ chức một vòng thay đổi gồm refactor nhỏ, chạy test và commit riêng để dễ tìm nguyên nhân hồi quy ra sao?
Bạn sẽ phân biệt test fail do thay đổi hành vi thật với test fail vì test đã phụ thuộc quá sâu vào chi tiết triển khai như thế nào?
Bạn sẽ sử dụng phân tích tĩnh, kiểm thử kiến trúc và test hồi quy bổ trợ cho nhau trong refactoring ra sao?
Bạn sẽ xác định kiểm thử hiệu năng hoặc tải nào cần chạy nếu refactor thay cách duyệt collection hoặc truy vấn dữ liệu như thế nào?
Bạn sẽ dùng code review để người khác xác minh một thay đổi là refactor bảo toàn hành vi thay vì trộn sửa lỗi hoặc bổ sung tính năng ra sao?
Bạn sẽ xử lý xung đột giữa refactor diện rộng và các nhánh tính năng đang phát triển song song như thế nào?
Bạn sẽ quyết định điểm dừng của một đợt refactor dựa trên mức giảm phức tạp, chi phí và rủi ro còn lại ra sao?
Bạn sẽ đánh giá mức cải thiện bằng thời gian hiểu mã, mức độ kết dính, độ phụ thuộc và khả năng viết test như thế nào?
Bạn sẽ phân tích trường hợp một đoạn mã sau refactor ngắn hơn nhưng khó theo dõi luồng nghiệp vụ hơn như thế nào?
