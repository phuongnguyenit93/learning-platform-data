Bạn sẽ phân biệt masking, redaction, tokenization, pseudonymization và anonymization theo mục tiêu bảo vệ cùng khả năng khôi phục dữ liệu như thế nào?
Bạn sẽ xây dựng threat model cho dữ liệu nhạy cảm bằng cách xác định chủ thể truy cập, kênh rò rỉ, mục đích xử lý và hậu quả tái nhận diện ra sao?
Bạn sẽ phân loại dữ liệu như PII, dữ liệu tài chính, định danh sức khỏe và bí mật xác thực để chọn mức che phù hợp như thế nào?
Bạn sẽ xác định ranh giới giữa dữ liệu được phép hiển thị, dữ liệu cần che một phần và dữ liệu phải loại bỏ hoàn toàn theo vai trò nào?
Bạn sẽ giải thích vì sao che dữ liệu ở giao diện không đủ nếu API, log hoặc database vẫn trả về giá trị gốc như thế nào?
Bạn sẽ thiết kế data inventory và data flow map để tìm nơi dữ liệu nhạy cảm được sao chép, biến đổi và lưu trữ ra sao?
Bạn sẽ lựa chọn chính sách masking theo mục đích sử dụng, độ nhạy cảm, môi trường và nghĩa vụ lưu giữ dữ liệu như thế nào?
Bạn sẽ phân biệt bảo vệ dữ liệu trong lúc hiển thị với bảo vệ dữ liệu khi lưu trữ hoặc truyền tải ra sao?
Bạn sẽ so sánh static data masking với dynamic data masking về thời điểm biến đổi, tính nhất quán và phạm vi áp dụng như thế nào?
Bạn sẽ lựa chọn masking tại nguồn, tầng truy vấn, API gateway hay ứng dụng theo ranh giới tin cậy nào?
Bạn sẽ thiết kế masking dựa trên ngữ cảnh để cùng một trường dữ liệu hiển thị khác nhau theo vai trò, mục đích và trạng thái xác minh như thế nào?
Bạn sẽ xác định quy tắc che theo trường dữ liệu thay vì áp dụng một mẫu chung cho mọi loại PII ra sao?
Bạn sẽ lựa chọn giữa che toàn bộ, che một phần, thay thế bằng giá trị giả và loại bỏ trường dữ liệu theo yêu cầu nghiệp vụ nào?
Bạn sẽ thiết kế quy tắc che số điện thoại, email, số định danh và số tài khoản để giữ đủ thông tin hỗ trợ nhưng giảm khả năng nhận diện như thế nào?
Bạn sẽ xử lý dữ liệu có độ dài thay đổi, ký tự Unicode và định dạng địa phương để masking không làm sai cấu trúc hoặc tiết lộ giá trị gốc ra sao?
Bạn sẽ phân biệt redaction trong log với masking có thể hiển thị một phần và xác định trường hợp nào phải xóa hẳn giá trị như thế nào?
Bạn sẽ thiết kế redaction trước khi dữ liệu được ghi xuống log hoặc trace để tránh bí mật xuất hiện tạm thời ở sink như thế nào?
Bạn sẽ phát hiện PII trong payload có cấu trúc và văn bản tự do khi tên trường hoặc định dạng dữ liệu không cố định ra sao?
Bạn sẽ lựa chọn regex, schema-aware redaction, parser hoặc bộ phát hiện dữ liệu nhạy cảm để giảm false positive và false negative như thế nào?
Bạn sẽ xử lý trường hợp một chuỗi chứa nhiều loại dữ liệu nhạy cảm hoặc nhiều định danh được nối trong cùng một thông điệp ra sao?
Bạn sẽ giải thích tokenization thay thế dữ liệu gốc bằng token không mang ý nghĩa và vai trò của token vault như thế nào?
Bạn sẽ phân biệt tokenization với encryption và hashing về khả năng khôi phục, quản lý khóa và nguy cơ lộ dữ liệu ra sao?
Bạn sẽ lựa chọn token ngẫu nhiên hay token xác định theo yêu cầu tra cứu, liên kết bản ghi và chống suy đoán như thế nào?
Bạn sẽ thiết kế token vault để ánh xạ token với dữ liệu gốc, giới hạn quyền detokenize và ghi audit ra sao?
Bạn sẽ ngăn token bị đoán hoặc dò tìm bằng entropy, namespace, rate limit và kiểm soát truy cập như thế nào?
Bạn sẽ xử lý token collision và bảo đảm tính duy nhất khi phát hành token trên nhiều node hoặc nhiều vùng như thế nào?
Bạn sẽ quyết định phạm vi tokenization theo từng trường, từng bản ghi, từng tenant hoặc toàn hệ thống dựa trên rủi ro nào?
Bạn sẽ duy trì tính nhất quán tham chiếu khi cùng một khách hàng xuất hiện trong nhiều bảng hoặc hệ thống nhưng được token hóa ở các pipeline khác nhau như thế nào?
Bạn sẽ thiết kế detokenization service để ứng dụng chỉ nhận dữ liệu gốc khi có quyền và mục đích hợp lệ ra sao?
Bạn sẽ đánh giá tác động của token vault outage đến truy vấn, thanh toán, hỗ trợ khách hàng và khả năng phục hồi như thế nào?
Bạn sẽ phân biệt pseudonymization với anonymization và giải thích vì sao dữ liệu giả danh vẫn có thể là dữ liệu cá nhân như thế nào?
Bạn sẽ đánh giá nguy cơ tái nhận diện khi dữ liệu đã loại bỏ tên nhưng vẫn giữ ngày sinh, mã bưu chính và giới tính ra sao?
Bạn sẽ giải thích linkage attack khi attacker kết hợp nhiều tập dữ liệu công khai để tái nhận diện bản ghi như thế nào?
Bạn sẽ áp dụng k-anonymity để giảm khả năng một bản ghi được phân biệt trong nhóm tương tự và nêu giới hạn của kỹ thuật này ra sao?
Bạn sẽ phân biệt l-diversity và t-closeness trong việc hạn chế suy luận thuộc tính nhạy cảm từ các nhóm đã ẩn danh như thế nào?
Bạn sẽ đánh giá vì sao tổng quát hóa và suppression có thể giảm rủi ro tái nhận diện nhưng làm giảm độ hữu ích của dữ liệu ra sao?
Bạn sẽ lựa chọn differential privacy cho thống kê hoặc phân tích tổng hợp khi cần giới hạn thông tin rò rỉ về một cá nhân như thế nào?
Bạn sẽ giải thích privacy budget và composition ảnh hưởng đến mức bảo vệ khi nhiều truy vấn thống kê được thực hiện ra sao?
Bạn sẽ phân biệt synthetic data với dữ liệu đã masking và đánh giá nguy cơ synthetic data ghi nhớ hoặc tiết lộ mẫu từ dữ liệu huấn luyện như thế nào?
Bạn sẽ kiểm chứng mức độ ẩn danh của một tập dữ liệu bằng cách thử linkage, uniqueness và membership inference ra sao?
Bạn sẽ thiết kế API response masking theo quyền truy cập trường để tránh excessive data exposure như thế nào?
Bạn sẽ bảo đảm field-level masking được áp dụng nhất quán trên REST, GraphQL, export endpoint và các phiên bản API ra sao?
Bạn sẽ xử lý dữ liệu nhạy cảm trong error response, validation message và exception detail để không lộ qua các nhánh lỗi như thế nào?
Bạn sẽ thiết kế quyền reveal dữ liệu gốc theo nguyên tắc least privilege và yêu cầu xác minh tăng cường cho thao tác nhạy cảm ra sao?
Bạn sẽ kiểm soát việc nhân viên hỗ trợ chỉ xem một phần dữ liệu khách hàng và cần lý do hoặc phê duyệt khi reveal toàn bộ như thế nào?
Bạn sẽ áp dụng masking ở giao diện web hoặc mobile để giảm hiển thị ngoài ý muốn mà không xem client-side masking là ranh giới bảo mật như thế nào?
Bạn sẽ xử lý dữ liệu nhạy cảm trong clipboard, browser cache, screenshot, file download và notification preview ra sao?
Bạn sẽ bảo vệ dữ liệu trong log bằng structured logging, field allowlist và redaction theo schema như thế nào?
Bạn sẽ ngăn secret hoặc PII xuất hiện trong trace attributes, span events và baggage khi request đi qua nhiều service như thế nào?
Bạn sẽ xử lý dữ liệu nhạy cảm trong metric labels để tránh lộ PII và tránh cardinality tăng không kiểm soát ra sao?
Bạn sẽ thiết kế log correlation bằng identifier giả danh để vẫn điều tra được một người dùng qua nhiều request mà không ghi định danh gốc như thế nào?
Bạn sẽ lựa chọn HMAC hoặc keyed hash cho pseudonymous identifier cần ổn định giữa các hệ thống và bảo vệ secret key ra sao?
Bạn sẽ đánh giá rủi ro khi hash email hoặc số điện thoại không salt vì không gian giá trị có thể dò ngược bằng dictionary như thế nào?
Bạn sẽ quản lý key rotation cho HMAC-based pseudonymization để duy trì liên kết dữ liệu cũ và mới mà vẫn giới hạn khả năng liên kết ngoài ý muốn ra sao?
Bạn sẽ áp dụng masking cho database view, column projection hoặc query layer để giới hạn dữ liệu mà analyst có thể đọc như thế nào?
Bạn sẽ phân biệt masking khi truy vấn với masking tĩnh trước khi sao chép dữ liệu sang môi trường analytics ra sao?
Bạn sẽ tạo dữ liệu giả cho development, testing và training sao cho giữ phân bố, quan hệ và ràng buộc nhưng không tái tạo hồ sơ cá nhân thật như thế nào?
Bạn sẽ bảo đảm foreign key, uniqueness và quan hệ tham chiếu vẫn nhất quán sau khi masking nhiều bảng liên quan như thế nào?
Bạn sẽ thiết kế masking cho dữ liệu streaming và event bus để dữ liệu nhạy cảm không đi vào topic hoặc consumer không được phép ra sao?
Bạn sẽ bảo vệ bản sao lưu, data lake, search index và warehouse khi dữ liệu đã được masking ở hệ thống nguồn nhưng còn bản sao cũ chưa xử lý như thế nào?
Bạn sẽ kiểm soát dữ liệu nhạy cảm trong file export, report, spreadsheet và tài liệu đính kèm trước khi chia sẻ ra ngoài ra sao?
Bạn sẽ lựa chọn xử lý dữ liệu gốc ở pipeline ingest hay ở consumer để tránh bản ghi nhạy cảm lan rộng trước khi được che như thế nào?
Bạn sẽ xác định cách xử lý dữ liệu không nhận diện được hoặc không parse được để không vô tình chuyển nguyên văn vào log hay output ra sao?
Bạn sẽ thiết kế policy versioning để thay đổi quy tắc masking không làm cùng một dữ liệu được hiển thị khác nhau ngoài dự kiến giữa các service như thế nào?
Bạn sẽ quản lý exception cho trường hợp cần hiển thị dữ liệu đầy đủ trong thời gian ngắn và bảo đảm mọi lần bypass đều được ghi nhận ra sao?
Bạn sẽ thiết kế audit log cho masking, redaction, tokenization và detokenization để biết ai đã truy cập hoặc reveal dữ liệu nào như thế nào?
Bạn sẽ phân biệt log kiểm toán thao tác reveal với log ứng dụng thông thường để audit không trở thành nơi rò rỉ dữ liệu gốc ra sao?
Bạn sẽ kiểm soát quyền truy cập token vault, mapping table và khóa pseudonymization độc lập với quyền đọc dữ liệu đã token hóa như thế nào?
Bạn sẽ đánh giá tác động hiệu năng của masking theo từng request, batch processing và truy vấn dữ liệu khối lượng lớn như thế nào?
Bạn sẽ tối ưu tokenization hoặc redaction ở lưu lượng cao bằng cache và batching mà không kéo dài thời gian tồn tại của dữ liệu gốc ra sao?
Bạn sẽ thiết kế kiểm thử để phát hiện PII còn sót trong API response, log, trace, metric, file export và error message như thế nào?
Bạn sẽ xây dựng test case cho masking theo role, tenant, field, locale và trạng thái xác minh để tránh lộ dữ liệu do nhánh xử lý bị bỏ sót ra sao?
Bạn sẽ kiểm thử tính nhất quán của token giữa các bảng, dịch vụ và pipeline sau retry, replay hoặc xử lý song song như thế nào?
Bạn sẽ đánh giá rủi ro tái nhận diện bằng cách kết hợp dữ liệu phụ trợ, phân tích uniqueness và kiểm thử red-team ra sao?
Nếu email được che ở giao diện nhưng API trả email đầy đủ trong một trường lồng nhau, bạn sẽ xác định và khắc phục điểm rò rỉ xuyên tầng như thế nào?
Nếu cùng một khách hàng nhận token khác nhau ở hai hệ thống và báo cáo không thể join dữ liệu, bạn sẽ thiết kế lại namespace hoặc mapping strategy ra sao?
Nếu analyst có thể tái nhận diện người dùng từ ngày sinh, khu vực và lịch sử giao dịch dù tên đã bị xóa, bạn sẽ đánh giá và giảm rủi ro như thế nào?
Nếu regex redaction bỏ sót số thẻ nằm trong JSON escape hoặc log nhiều dòng, bạn sẽ thay đổi pipeline và bộ kiểm thử ra sao?
Nếu nhân viên hỗ trợ cần reveal toàn bộ số định danh cho một trường hợp khẩn cấp, bạn sẽ thiết kế phê duyệt, thời hạn quyền và audit như thế nào?
Bạn sẽ xây dựng chiến lược data protection đầu cuối cho masking, redaction, tokenization và de-identification xuyên API, log, UI, database và môi trường thử nghiệm như thế nào?
