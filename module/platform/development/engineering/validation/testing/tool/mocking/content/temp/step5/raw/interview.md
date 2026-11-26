Bạn phân biệt test double, stub, fake, mock và spy dựa trên vai trò của chúng trong một unit test Java như thế nào?
Trong trường hợp cần kiểm tra kết quả tính toán thuần túy, bạn cân nhắc bỏ mock và dùng đối tượng thật theo tiêu chí nào?
Bạn xác định đâu là cộng tác viên nên cô lập khi kiểm thử một service Java có repository, clock và HTTP client?
Việc mock quá nhiều lớp nội bộ có thể làm mất bằng chứng về hành vi nghiệp vụ như thế nào?
Bạn dùng Mockito để tạo một mock và định nghĩa giá trị trả về của một method có tham số như thế nào?
Bạn phân biệt stubbing dùng thenReturn và thenAnswer khi phản hồi phụ thuộc vào tham số đầu vào ra sao?
Bạn thiết lập các phản hồi liên tiếp của mock khi cùng một method được gọi nhiều lần để kiểm tra tình huống nào?
Bạn mô phỏng một dependency ném exception bằng Mockito để kiểm tra chính sách xử lý lỗi của lớp đang test ra sao?
Với method trả về void, bạn kiểm soát tác động hoặc exception bằng Mockito như thế nào?
Bạn lựa chọn any, eq và các argument matcher khác dựa trên mức chính xác cần kiểm chứng như thế nào?
Vì sao trộn matcher với giá trị literal không đúng quy tắc có thể làm một phép stubbing trong Mockito thất bại?
Bạn phân tích khi nào dùng matcher quá rộng như any có thể khiến test bỏ lọt một tham số nghiệp vụ sai?
Bạn thiết kế matcher tùy chỉnh để diễn đạt một điều kiện nghiệp vụ rõ ràng mà không lặp lại logic implementation như thế nào?
Bạn dùng @Mock, @InjectMocks và MockitoExtension trong JUnit Jupiter để chuẩn bị các cộng tác viên như thế nào?
Bạn nhận diện giới hạn của việc tự động tiêm mock vào đối tượng đang test và quyết định khi nào khởi tạo thủ công ra sao?
Bạn xác định vòng đời và phạm vi chia sẻ mock giữa các test để ngăn trạng thái stubbing hoặc interaction rò rỉ như thế nào?
Bạn thiết kế test khi repository trả Optional.empty để xác minh service thực hiện đúng nhánh lỗi ra sao?
Bạn tạo fake repository trong bộ nhớ thay vì mock repository cho tình huống nào và kiểm tra tính trung thực của fake ra sao?
Bạn lựa chọn mock HTTP client hay fake server khi muốn kiểm tra chính xác serialization và hợp đồng mạng như thế nào?
Bạn quyết định khi nào nên xác minh trạng thái cuối cùng và khi nào việc verify lời gọi cộng tác viên mới chứng minh được hành vi?
Bạn dùng verify với số lần gọi cụ thể để kiểm tra hành vi quan trọng mà không khóa chặt cấu trúc nội bộ như thế nào?
Bạn kiểm tra rằng service không ghi dữ liệu sau khi validation thất bại bằng Mockito ra sao?
Bạn phân biệt verifyNoInteractions và verifyNoMoreInteractions về loại cam kết mà mỗi assertion tạo ra như thế nào?
Một refactor thay đổi số lần gọi method nhưng vẫn giữ nguyên kết quả nghiệp vụ có thể làm test dùng verify bị vỡ ra sao?
Bạn lựa chọn ArgumentCaptor khi cần kiểm tra nội dung sự kiện được phát qua collaborator như thế nào?
Bạn so sánh ArgumentCaptor với argThat khi cần kiểm tra một đối số chứa nhiều trường có liên hệ ra sao?
Bạn tổ chức assertion sau khi capture argument để báo sai lệch rõ ràng trên từng trường nghiệp vụ như thế nào?
Bạn sử dụng InOrder để kiểm tra thứ tự tương tác có ý nghĩa nghiệp vụ trong những tình huống nào?
Bạn tránh dùng InOrder đối với các lời gọi độc lập có thể đổi thứ tự hợp lệ như thế nào?
Bạn phân biệt mock với spy khi làm việc với đối tượng có hành vi thực và trạng thái thay đổi ra sao?
Vì sao dùng when trên spy có thể gọi method thật trước khi stubbing, và bạn xử lý trường hợp này như thế nào?
Bạn lựa chọn doReturn hoặc doThrow với spy dựa trên rủi ro tác động phụ của method thật ra sao?
Bạn xử lý test cho một collaborator có method final hoặc static mà không biến unit test thành phụ thuộc vào cấu trúc mã ra sao?
Bạn dùng mocking phạm vi tĩnh khi thật sự cần và bảo đảm đóng phạm vi đó để tránh ảnh hưởng test khác như thế nào?
Bạn thay thế gọi đồng hồ hệ thống hoặc sinh UUID trực tiếp bằng dependency có thể tiêm vào nhằm giảm nhu cầu mock phức tạp ra sao?
Bạn lựa chọn stub xác định hay fake có trạng thái khi cần kiểm thử chuỗi thao tác đọc, sửa và lưu như thế nào?
Bạn đánh giá rủi ro một fake hoạt động khác database thật và quyết định trường hợp nào cần integration test bổ sung ra sao?
Bạn phát hiện những stubbing không được sử dụng và xử lý cảnh báo strict stubbing như thế nào?
Bạn quyết định khi nào nên dùng lenient stubbing, đồng thời tránh biến nó thành cách che giấu cấu hình test thừa ra sao?
Bạn thiết kế mock cho nhiều nhánh điều kiện sao cho mỗi test chỉ định cấu hình đủ để giải thích hành vi đang kiểm chứng như thế nào?
Bạn kiểm tra khi một collaborator trả null hoặc dữ liệu sai định dạng, service phản ứng đúng hợp đồng bằng cách nào?
Bạn điều khiển CompletableFuture hoặc callback từ một dependency giả lập để kiểm thử thành công và thất bại bất đồng bộ ra sao?
Bạn xác minh một callback chỉ được thực hiện sau sự kiện mong đợi mà không phụ thuộc vào Thread.sleep cố định như thế nào?
Bạn xử lý timeout của dependency bằng fake clock hoặc executor có thể điều khiển để kiểm thử nhanh và ổn định như thế nào?
Bạn kiểm tra rằng retry chỉ áp dụng cho lỗi tạm thời mà không gửi lặp yêu cầu không idempotent bằng mock ra sao?
Bạn mô phỏng đối tác trả nhiều phản hồi theo thứ tự để kiểm chứng chính sách retry và giới hạn số lần như thế nào?
Bạn ghi lại và phân tích lời gọi tới mock khi test thất bại để phân biệt sai tham số với sai số lần gọi ra sao?
Bạn so sánh việc reset mock với tạo mock mới để duy trì tính độc lập giữa các test theo tiêu chí nào?
Bạn nhận diện test phụ thuộc vào thứ tự thực thi bởi mock dùng chung qua những dấu hiệu nào?
Bạn thiết kế unit test cho logic gửi sự kiện để chỉ kiểm tra nội dung và điều kiện gửi mà không lặp lại toàn bộ cách cài đặt như thế nào?
Bạn dùng mock để kiểm tra nhánh bù trừ khi một bước xử lý thất bại và tránh xác minh quá nhiều lời gọi phụ như thế nào?
Bạn cân nhắc tách một class có quá nhiều dependency thành các thành phần nhỏ khi việc stubbing trở nên phức tạp ra sao?
Bạn đánh giá chất lượng một unit test dùng Mockito khi bài test xanh nhưng không bắt được một lỗi hành vi cố ý chèn vào như thế nào?
Bạn lập quy ước chung về cách dùng matcher, captor, spy và verify để code review ngăn các test dễ vỡ như thế nào?
