Bạn giải thích mục tiêu của tích hợp dữ liệu và phân biệt nó với di chuyển dữ liệu một lần như thế nào?
Khi nhận yêu cầu đồng bộ dữ liệu giữa hai hệ thống, bạn xác định nguồn dữ liệu chuẩn và phạm vi tích hợp ra sao?
Bạn sẽ thu thập những thông tin nào về nguồn, đích và nhu cầu sử dụng trước khi thiết kế một pipeline dữ liệu?
Bạn xác định yêu cầu về độ trễ, độ đầy đủ và tính nhất quán của dữ liệu từ nhu cầu nghiệp vụ như thế nào?
Bạn sẽ lập sơ đồ luồng dữ liệu từ hệ thống nguồn đến hệ thống đích để làm rõ trách nhiệm từng bước ra sao?
Bạn phân biệt data ingestion, transformation và data loading trong một pipeline bằng ví dụ nào?
Bạn lựa chọn giữa ETL và ELT dựa trên dung lượng dữ liệu, năng lực hệ thống đích và nhu cầu quản trị như thế nào?
Trong tình huống dữ liệu thô cần được lưu để kiểm toán và tái xử lý, bạn sẽ bố trí các lớp lưu trữ như thế nào?
Bạn quyết định dùng pipeline theo lô hay theo luồng khi hệ thống yêu cầu dữ liệu cập nhật gần thời gian thực ra sao?
Bạn so sánh batch, micro-batch và streaming liên tục về độ trễ, chi phí và độ phức tạp vận hành như thế nào?
Bạn chọn cách tích hợp qua API, truy vấn cơ sở dữ liệu hay đọc tệp xuất định kỳ theo những tiêu chí nào?
Khi kết nối đến một API có phân trang và giới hạn tốc độ, bạn thiết kế bước trích xuất thế nào để không bỏ sót dữ liệu?
Bạn quản lý thông tin kết nối, thông số cấu hình và bí mật xác thực cho nhiều môi trường chạy pipeline ra sao?
Bạn xử lý sự khác biệt về bộ mã ký tự, dấu phân cách và định dạng tệp khi đọc dữ liệu từ nhiều nguồn như thế nào?
Bạn sẽ phát hiện và xử lý bản ghi không hợp lệ trong tệp CSV hoặc JSON ngay tại bước ingestion ra sao?
Bạn phân biệt trích xuất toàn bộ với trích xuất tăng dần và xác định điều kiện chọn từng cách như thế nào?
Khi nguồn có cột updated_at, bạn thiết kế watermark để lấy dữ liệu tăng dần mà không mất bản ghi như thế nào?
Bạn xử lý trường hợp nhiều bản ghi có cùng mốc updated_at tại ranh giới hai lần đồng bộ ra sao?
Nếu đồng hồ của hệ thống nguồn và hệ thống đích lệch nhau, bạn sẽ bảo vệ tính đầy đủ của đồng bộ tăng dần bằng cách nào?
Bạn xây dựng chiến lược đồng bộ tăng dần khi hệ thống nguồn không cung cấp thời gian cập nhật đáng tin cậy như thế nào?
Bạn giải thích Change Data Capture (CDC) là gì và khi nào nên chọn CDC thay cho truy vấn định kỳ?
Bạn phân biệt CDC dựa trên transaction log, trigger và truy vấn chênh lệch theo những đánh đổi nào?
Bạn tổ chức bước chụp dữ liệu ban đầu và chuyển sang đọc CDC liên tục sao cho không tạo khoảng trống dữ liệu ra sao?
Khi nhận sự kiện insert, update và delete từ CDC, bạn ánh xạ chúng thành thay đổi tại hệ thống đích như thế nào?
Bạn xử lý các sự kiện CDC đến trùng lặp hoặc không đúng thứ tự để trạng thái cuối cùng vẫn chính xác ra sao?
Bạn phát hiện và phục hồi khi connector CDC bị mất vị trí đọc hoặc transaction log nguồn không còn đủ lịch sử như thế nào?
Bạn xử lý thay đổi schema của bảng nguồn trong lúc CDC đang chạy mà không làm hỏng pipeline như thế nào?
Bạn phân biệt event time, ingestion time và processing time trong việc xử lý dữ liệu sự kiện ra sao?
Bạn sẽ xử lý sự kiện đến muộn và sự kiện đến sai thứ tự trong pipeline streaming như thế nào?
Bạn giải thích vai trò của watermark trong xử lý cửa sổ thời gian khi dữ liệu streaming đến muộn ra sao?
Bạn chọn kích thước cửa sổ thời gian và chính sách cập nhật kết quả tổng hợp theo những yêu cầu nghiệp vụ nào?
Bạn thiết kế cơ chế backpressure khi nguồn phát sinh dữ liệu nhanh hơn khả năng xử lý của pipeline ra sao?
Bạn so sánh ngữ nghĩa xử lý at-most-once, at-least-once và exactly-once theo tác động lên dữ liệu đích như thế nào?
Bạn tạo khóa định danh và quy tắc loại trùng cho các bản ghi đến nhiều lần bằng cách nào?
Bạn thiết kế thao tác nạp dữ liệu idempotent để pipeline chạy lại không làm tăng số lượng bản ghi ngoài ý muốn ra sao?
Bạn sẽ sử dụng insert, upsert hay merge khi nạp dữ liệu biến động vào hệ thống đích, và vì sao?
Bạn xử lý xóa cứng và xóa mềm ở nguồn như thế nào để hệ thống đích phản ánh đúng trạng thái dữ liệu?
Bạn quyết định lúc nào cần lưu lịch sử thay đổi thay vì chỉ giữ giá trị mới nhất như thế nào?
Bạn sẽ thiết kế mô hình lưu lịch sử thuộc tính kiểu Slowly Changing Dimension Type 2 cho dữ liệu khách hàng ra sao?
Bạn giải quyết sự khác nhau về kiểu dữ liệu, độ chính xác số và quy ước null giữa hai hệ thống bằng cách nào?
Bạn chuẩn hóa dữ liệu ngày giờ và múi giờ như thế nào để báo cáo không bị lệch thời điểm?
Bạn xây dựng quy tắc mapping trường dữ liệu và giá trị mã danh mục giữa hệ thống nguồn và đích ra sao?
Khi một trường ở nguồn bị đổi tên hoặc đổi ý nghĩa, bạn quản lý phiên bản mapping và tác động đến dữ liệu cũ thế nào?
Bạn tổ chức bước biến đổi dữ liệu để có thể kiểm thử độc lập và tái sử dụng trong nhiều pipeline như thế nào?
Bạn kiểm soát thứ tự các phép biến đổi để tránh làm mất thông tin hoặc nhân đôi bản ghi ngoài ý muốn ra sao?
Bạn xác định những tiêu chí chất lượng dữ liệu nào cần được kiểm tra trước khi nạp vào hệ thống đích?
Bạn xây dựng kiểm tra tính đầy đủ, tính duy nhất, tính hợp lệ và tính nhất quán dữ liệu bằng các ví dụ nào?
Bạn xử lý trường hợp bản ghi tham chiếu đến khóa ngoại chưa xuất hiện ở hệ thống đích như thế nào?
Bạn sẽ đưa dữ liệu lỗi vào vùng cách ly hay dừng cả pipeline dựa trên mức độ ảnh hưởng nào?
Bạn thiết kế cách lưu lý do từ chối bản ghi và cơ chế sửa rồi nạp lại dữ liệu lỗi ra sao?
Bạn xây dựng data contract giữa đơn vị phát sinh dữ liệu và đơn vị tiêu thụ để giảm rủi ro thay đổi schema như thế nào?
Bạn phát hiện schema drift và thay đổi phân bố dữ liệu bất thường trước khi chúng gây sai lệch báo cáo bằng cách nào?
Bạn phân biệt kiểm tra chất lượng ở đầu vào, sau biến đổi và sau khi nạp dữ liệu dựa trên mục tiêu nào?
Bạn thực hiện đối soát số lượng bản ghi giữa nguồn và đích khi pipeline có lọc hoặc loại trùng như thế nào?
Bạn sử dụng checksum, tổng giá trị nghiệp vụ hoặc phân nhóm đối soát để tìm sai lệch dữ liệu ra sao?
Nếu tổng doanh thu của nguồn và đích khác nhau dù số dòng bằng nhau, bạn sẽ điều tra theo trình tự nào?
Bạn thiết kế đối soát theo từng khoảng thời gian hoặc từng partition để xác định phạm vi sai lệch như thế nào?
Bạn ghi nhận và theo dõi những bản ghi chưa đồng bộ được để việc đối soát không bỏ qua chúng ra sao?
Bạn thiết kế checkpoint hoặc lưu offset để pipeline có thể tiếp tục chính xác sau khi tiến trình bị gián đoạn như thế nào?
Bạn phân biệt retry, replay và backfill theo nguyên nhân và tác động lên dữ liệu đích ra sao?
Bạn quyết định phạm vi backfill khi phát hiện một quy tắc biến đổi đã sai trong nhiều ngày như thế nào?
Bạn chạy backfill song song với luồng đồng bộ đang hoạt động để tránh ghi đè dữ liệu mới bằng dữ liệu cũ ra sao?
Bạn thiết kế retry có giới hạn và hàng đợi lỗi để tránh kẹt pipeline vì một bản ghi không thể xử lý như thế nào?
Bạn xử lý tình huống đã ghi thành công vào đích nhưng tiến trình chết trước khi xác nhận checkpoint ra sao?
Bạn bảo đảm các bước nạp dữ liệu nhiều bảng giữ được tính nhất quán khi xảy ra lỗi giữa chừng như thế nào?
Bạn lựa chọn chiến lược tải hàng loạt, nạp theo partition hoặc nạp từng bản ghi dựa trên hiệu năng và tính đúng ra sao?
Bạn xác định cách chia partition và mức độ xử lý song song để tăng throughput mà không phá vỡ thứ tự dữ liệu như thế nào?
Bạn sẽ phát hiện và xử lý data skew khi một số partition lớn hơn phần còn lại rất nhiều ra sao?
Bạn đánh giá ảnh hưởng của chỉ mục, khóa và transaction trên hệ thống đích đến tốc độ nạp dữ liệu như thế nào?
Bạn thiết kế lịch chạy, phụ thuộc giữa các tác vụ và cơ chế ngăn chạy chồng trong công cụ orchestration ra sao?
Bạn sẽ xử lý một tác vụ thượng nguồn thất bại để các bước hạ nguồn không sử dụng dữ liệu chưa hoàn chỉnh như thế nào?
Bạn xác định SLA về thời điểm có dữ liệu và SLO về chất lượng pipeline dựa trên yêu cầu người sử dụng ra sao?
Bạn lựa chọn các chỉ số giám sát nào để theo dõi độ trễ, throughput, lỗi và độ mới của dữ liệu?
Bạn phân biệt độ trễ xử lý với độ trễ từ lúc phát sinh dữ liệu đến lúc có thể truy vấn ở đích như thế nào?
Bạn tổ chức log, metric và trace với định danh lần chạy để có thể truy vết một bản ghi lỗi xuyên suốt pipeline ra sao?
Bạn thiết kế cảnh báo thế nào để phát hiện pipeline ngừng cập nhật dù tiến trình vẫn đang chạy?
Bạn đặt ngưỡng cảnh báo về số lượng bản ghi lỗi hoặc sai lệch đối soát dựa trên mức độ rủi ro nghiệp vụ nào?
Khi tốc độ dữ liệu đầu vào tăng đột ngột, bạn sẽ xác định nút thắt ở nguồn, biến đổi hay hệ thống đích bằng cách nào?
Bạn xây dựng quy trình xử lý sự cố khi dữ liệu báo cáo bị sai do pipeline nhưng chưa rõ lỗi bắt đầu từ đâu ra sao?
Bạn bảo vệ dữ liệu cá nhân khi trích xuất, biến đổi, lưu tạm và nạp sang hệ thống khác như thế nào?
Bạn quản lý quyền truy cập tối thiểu cho tài khoản kết nối nguồn và đích để giảm rủi ro lộ dữ liệu ra sao?
Bạn quyết định cần mã hóa, che giấu hoặc loại bỏ trường dữ liệu nhạy cảm ở bước nào của pipeline như thế nào?
Bạn sẽ quy định thời gian lưu dữ liệu thô, dữ liệu lỗi và log vận hành dựa trên yêu cầu truy vết và bảo mật ra sao?
Bạn xây dựng kiểm thử đơn vị cho các phép biến đổi dữ liệu có quy tắc nghiệp vụ phức tạp như thế nào?
Bạn thiết kế kiểm thử tích hợp để xác nhận connector đọc đúng dữ liệu và bước nạp giữ đúng khóa, kiểu dữ liệu ra sao?
Bạn chuẩn bị bộ dữ liệu kiểm thử nào để phát hiện lỗi ở ranh giới watermark, bản ghi trùng và sự kiện đến muộn?
Bạn kiểm tra pipeline sau khi thay đổi schema nguồn hoặc nâng phiên bản connector bằng quy trình nào?
Nếu API nguồn thường xuyên trả lỗi giới hạn tốc độ và dữ liệu bị trễ, bạn sẽ điều chỉnh chiến lược ingestion ra sao?
Nếu phát hiện hệ thống đích thiếu một phần giao dịch sau đợt mất kết nối, bạn sẽ khôi phục và đối soát lại bằng cách nào?
Khi lựa chọn kiến trúc tích hợp dữ liệu cho hệ thống bán hàng có báo cáo ngày và cảnh báo thời gian thực, bạn sẽ kết hợp các cơ chế xử lý nào và đánh giá tính đúng của chúng ra sao?
