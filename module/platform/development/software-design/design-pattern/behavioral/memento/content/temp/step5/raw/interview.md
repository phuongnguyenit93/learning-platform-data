Bạn giải thích mục đích của mẫu Memento khi cần chụp và khôi phục trạng thái đối tượng mà vẫn bảo toàn tính đóng gói như thế nào?
Bạn phân biệt trách nhiệm của Originator, Memento và Caretaker trong một quy trình lưu và khôi phục trạng thái ra sao?
Bạn dựa trên những tiêu chí nào để chọn Memento thay vì chỉ sao chép dữ liệu và lưu ở một nơi khác?
Bạn thiết kế ví dụ trình soạn thảo văn bản có thể undo để minh họa các đối tượng tham gia Memento ra sao?
Bạn lựa chọn những trường dữ liệu nào của Originator phải được chụp để khôi phục đầy đủ một trạng thái hợp lệ như thế nào?
Bạn giải thích vì sao Caretaker không nên hiểu hoặc chỉnh sửa cấu trúc nội bộ của snapshot như thế nào?
Bạn thiết kế giao diện Memento để Originator có thể khôi phục trạng thái nhưng Caretaker chỉ được lưu giữ và trao lại ra sao?
Bạn phân biệt snapshot bất biến với một đối tượng tham chiếu có thể bị thay đổi sau thời điểm lưu như thế nào?
Bạn xác định những hậu quả nào xảy ra nếu Memento giữ tham chiếu tới một danh sách mutable do Originator tiếp tục sửa đổi?
Bạn lựa chọn shallow copy hay deep copy khi trạng thái chứa nhiều đối tượng lồng nhau dựa trên tiêu chí nào?
Bạn bảo đảm các value object hoặc collection trong snapshot không thể bị thay đổi ngoài ý muốn như thế nào?
Bạn thiết kế thao tác createMemento và restore để trách nhiệm kiểm tra bất biến vẫn thuộc Originator ra sao?
Khi trạng thái chụp chứa dữ liệu tạm hoặc cache có thể tính lại, bạn quyết định loại trừ chúng bằng những tiêu chí nào?
Bạn phân biệt trạng thái có ý nghĩa nghiệp vụ với chi tiết hạ tầng không nên đưa vào Memento như thế nào?
Bạn tổ chức Caretaker lưu lịch sử nhiều Memento mà không phải biết ý nghĩa của các trường trạng thái ra sao?
Bạn dùng stack hoặc cấu trúc có con trỏ lịch sử để xây dựng thao tác undo và redo như thế nào?
Bạn xử lý lịch sử redo ra sao nếu người dùng undo vài bước rồi tạo một thay đổi mới?
Bạn xác định thời điểm tạo snapshot trước hay sau một thay đổi để undo luôn quay về trạng thái mong đợi như thế nào?
Bạn quyết định khi nào nhiều thao tác nhỏ nên được gom thành một bước undo duy nhất theo tiêu chí trải nghiệm người dùng nào?
Bạn bảo đảm undo một chuỗi thay đổi có phụ thuộc lẫn nhau không để Originator ở trạng thái trung gian sai như thế nào?
Bạn thiết kế xử lý khi không còn snapshot để undo hoặc không còn bước để redo mà không làm hỏng lịch sử ra sao?
Bạn xác định điều gì xảy ra với lịch sử khi người dùng nạp một tài liệu mới hoặc đặt lại phiên làm việc như thế nào?
Bạn thiết kế Memento cho đối tượng có trạng thái lớn để tránh giữ toàn bộ bản sao sau mỗi lần gõ phím như thế nào?
Bạn phân tích chi phí bộ nhớ theo kích thước trạng thái và số bước undo để lựa chọn giới hạn lịch sử ra sao?
Bạn lựa chọn snapshot toàn phần, snapshot gia tăng hoặc lưu phần chênh lệch dựa trên độ phức tạp khôi phục như thế nào?
Bạn xác định lúc nào nên tạo checkpoint đầy đủ nếu lịch sử chủ yếu được lưu bằng các thay đổi gia tăng ra sao?
Bạn cân nhắc cơ chế chia sẻ các phần dữ liệu bất biến giữa nhiều Memento để giảm cấp phát bộ nhớ như thế nào?
Bạn thiết kế chính sách loại bỏ những snapshot cũ khi vượt ngân sách bộ nhớ mà vẫn giữ trải nghiệm undo có thể dự đoán ra sao?
Bạn đánh giá ảnh hưởng của tần suất tạo Memento đến độ trễ giao diện và hoạt động thu gom rác như thế nào?
Bạn phân biệt việc lưu snapshot trong RAM với việc lưu xuống tệp hoặc cơ sở dữ liệu về mục tiêu khôi phục ra sao?
Bạn xử lý snapshot không tương thích sau khi cấu trúc trạng thái của Originator thay đổi giữa các phiên bản ứng dụng như thế nào?
Bạn bảo vệ thông tin bí mật nằm trong snapshot hoặc lịch sử undo nếu dữ liệu được lưu lâu dài như thế nào?
Bạn thiết kế việc xóa hoặc ẩn dữ liệu nhạy cảm trong lịch sử Memento khi người dùng yêu cầu không lưu lại dữ liệu đó ra sao?
Vì sao đối tượng chứa kết nối mạng, khóa hoặc luồng xử lý cần cách chụp trạng thái khác với việc sao chép toàn bộ đối tượng?
Bạn xác định cách khôi phục các tham chiếu phụ thuộc vào tài nguyên ngoài mà không cố gắng lưu nguyên đối tượng tài nguyên đó ra sao?
Bạn xử lý trạng thái của Originator khi việc khôi phục Memento thất bại ở giữa quá trình như thế nào?
Bạn kiểm tra tính tương thích và tính hợp lệ của một Memento trước khi áp dụng vào Originator ra sao?
Bạn lựa chọn cách đánh dấu phiên bản hoặc định danh nguồn gốc để ngăn khôi phục snapshot thuộc đối tượng khác như thế nào?
Bạn phân biệt tính nhất quán của snapshot với việc chỉ sao chép nhiều trường độc lập khi một đối tượng đang được cập nhật như thế nào?
Bạn thiết kế thao tác chụp snapshot an toàn nếu nhiều luồng có thể thay đổi Originator cùng lúc ra sao?
Bạn ngăn một thao tác undo từ luồng này ghi đè mất cập nhật đồng thời từ luồng khác bằng cơ chế nào?
Bạn đánh giá khi nào việc tạo Memento cần khóa và khi nào dùng trạng thái bất biến có thể giảm tranh chấp ra sao?
Bạn phân biệt Memento với Command pattern khi xây dựng undo dựa trên lưu trạng thái so với thực hiện thao tác nghịch đảo như thế nào?
Bạn so sánh Memento với event sourcing về mục tiêu ghi lịch sử, khả năng khôi phục và tính diễn giải của dữ liệu như thế nào?
Bạn chọn phối hợp Memento và Command trong tình huống nào để cân bằng hiệu quả bộ nhớ và tính chính xác của undo ra sao?
Bạn tổ chức kiểm thử round-trip để xác minh chụp snapshot, thay đổi trạng thái rồi restore trả về đúng trạng thái trước đó như thế nào?
Bạn kiểm thử tính bất biến của Memento khi Originator thay đổi nhiều lần sau khi chụp snapshot như thế nào?
Bạn xây dựng test cho chuỗi undo, redo và tạo nhánh lịch sử mới để phát hiện lỗi con trỏ hoặc thứ tự như thế nào?
Bạn kiểm chứng việc khôi phục luôn giữ các bất biến nghiệp vụ kể cả khi snapshot thiếu dữ liệu hoặc không hợp lệ ra sao?
Bạn đo lượng bộ nhớ tiêu thụ và thời gian chụp/khôi phục để lựa chọn chiến lược snapshot phù hợp như thế nào?
Bạn nhận diện khi nào logic lưu lịch sử đang làm Originator gánh trách nhiệm của Caretaker và đề xuất cách tách ra sao?
Bạn đánh giá độ phức tạp thêm vào từ Memento so với lợi ích khôi phục trạng thái trong ứng dụng ít có yêu cầu undo như thế nào?
Bạn thiết kế cách kiểm tra chức năng undo/redo sau refactor để bảo đảm người dùng nhận được cùng hành vi dù cấu trúc nội bộ đã thay đổi như thế nào?
Bạn lựa chọn những tín hiệu nào về tốc độ khôi phục, bộ nhớ và độ ổn định để quyết định cơ chế Memento cần được cải tiến?
