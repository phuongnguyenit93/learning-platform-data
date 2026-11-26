Bạn sẽ mô tả các giai đoạn chính trong vòng đời khóa mật mã từ lúc tạo đến khi hủy như thế nào?
Bạn xây dựng chính sách quản lý khóa dựa trên phân loại dữ liệu, mục đích sử dụng và mức độ rủi ro ra sao?
Bạn xác định chủ sở hữu nghiệp vụ, người quản trị kỹ thuật và người phê duyệt cho từng loại khóa như thế nào?
Bạn lựa chọn thuật toán và kích thước khóa đối xứng dựa trên yêu cầu bảo mật, hiệu năng và thời gian sử dụng ra sao?
Bạn phân biệt mục đích sử dụng của khóa mã hóa đối xứng, khóa bất đối xứng và khóa dẫn xuất như thế nào?
Bạn quản lý riêng khóa dùng để mã hóa dữ liệu với khóa dùng để ký số hoặc xác thực ra sao?
Bạn đánh giá khi nào nên dùng khóa công khai và khóa riêng trong mô hình mã hóa bất đối xứng như thế nào?
Bạn thiết kế quy tắc không tái sử dụng cùng một khóa cho nhiều mục đích mật mã khác nhau ra sao?
Bạn xác định mức entropy và nguồn ngẫu nhiên cần thiết khi tạo khóa cho từng thuật toán như thế nào?
Bạn kiểm soát việc sinh khóa để tránh dùng PRNG yếu, seed dễ đoán hoặc nguồn entropy không đáng tin cậy ra sao?
Bạn lựa chọn nơi và thời điểm tạo khóa giữa ứng dụng, KMS và HSM dựa trên threat model nào?
Bạn thiết kế quy trình sinh khóa trong HSM để khóa riêng không phải xuất hiện dưới dạng plaintext bên ngoài thiết bị như thế nào?
Bạn xử lý thế nào khi khóa được tạo trên một môi trường nhưng cần phân phối an toàn tới nhiều dịch vụ hoặc vùng triển khai?
Bạn phân biệt key wrapping, key transport và key agreement trong quá trình phân phối khóa ra sao?
Bạn lựa chọn cơ chế trao đổi hoặc thiết lập khóa cho kết nối giữa các hệ thống như thế nào để tránh gửi khóa bí mật trực tiếp?
Bạn thiết kế phân cấp khóa gồm root key, key-encryption key và data-encryption key như thế nào?
Bạn giải thích envelope encryption và luồng mã hóa DEK bằng KEK trong một hệ thống lưu trữ dữ liệu ra sao?
Bạn quyết định khi nào nên tạo DEK mới theo từng bản ghi, đối tượng, tenant hoặc lô dữ liệu như thế nào?
Bạn đánh giá tác động của việc dùng chung một DEK cho nhiều đối tượng khi một khóa bị lộ ra sao?
Bạn thiết kế lưu trữ ciphertext, wrapped DEK, key identifier và metadata phiên bản như thế nào để có thể giải mã lâu dài?
Bạn bảo đảm ứng dụng không ghi plaintext key, secret hoặc dữ liệu nhạy cảm vào log, trace, crash dump hay file tạm như thế nào?
Bạn lựa chọn giữa KMS quản lý tập trung, HSM tự vận hành và giải pháp kết hợp dựa trên yêu cầu kiểm soát khóa nào?
Bạn phân biệt vai trò của KMS và HSM trong việc quản lý chính sách, thực thi thao tác mật mã và bảo vệ vật lý khóa ra sao?
Bạn đánh giá các ranh giới tin cậy khi ứng dụng gọi API KMS và khi thao tác mật mã diễn ra bên trong HSM như thế nào?
Bạn thiết kế quyền IAM cho thao tác tạo, đọc metadata, mã hóa, giải mã, ký, xoay vòng và hủy khóa theo least privilege ra sao?
Bạn làm thế nào để tách quyền quản trị key policy khỏi quyền sử dụng khóa trong ứng dụng?
Bạn áp dụng dual control hoặc split knowledge cho các thao tác nhạy cảm như khôi phục, xuất hoặc hủy khóa như thế nào?
Bạn lựa chọn mô hình quorum hoặc nhiều người phê duyệt cho thao tác quản trị khóa quan trọng dựa trên rủi ro nào?
Bạn ngăn một workload bị xâm nhập sử dụng KMS để giải mã hàng loạt dữ liệu ngoài phạm vi cần thiết như thế nào?
Bạn thiết kế giới hạn theo danh tính, tài nguyên, context và điều kiện môi trường cho từng yêu cầu KMS ra sao?
Bạn quản lý khóa riêng trong HSM hoặc thiết bị phần cứng khi cần backup, replication hay disaster recovery như thế nào?
Bạn đánh giá việc xuất khóa khỏi HSM trong trường hợp cần thiết và những biện pháp kiểm soát bổ sung nào cần có?
Bạn lựa chọn BYOK, HYOK hoặc khóa do nhà cung cấp KMS tạo dựa trên yêu cầu chủ quyền và trách nhiệm vận hành nào?
Bạn xác minh nguồn gốc, tính toàn vẹn và chuỗi bàn giao khi nhập khóa do tổ chức tự tạo vào KMS ra sao?
Bạn thiết kế key inventory để theo dõi chủ sở hữu, thuật toán, mục đích, vị trí, trạng thái và ngày hết hạn như thế nào?
Bạn xây dựng quy tắc đặt tên và gắn metadata cho khóa để tránh nhầm lẫn giữa môi trường, tenant và mục đích sử dụng ra sao?
Bạn xác định thời hạn sử dụng và chu kỳ rotation của khóa dựa trên loại khóa, mức phơi nhiễm và yêu cầu tuân thủ như thế nào?
Bạn phân biệt rotation định kỳ, rotation do nghi ngờ lộ khóa và thay thế khóa do thuật toán sắp lỗi thời ra sao?
Bạn thiết kế quy trình rotation để khóa mới bắt đầu mã hóa dữ liệu mới trong khi khóa cũ vẫn giải mã dữ liệu hiện hữu như thế nào?
Bạn xác định khi nào cần re-encrypt dữ liệu bằng khóa mới và khi nào chỉ cần rewrap DEK bằng KEK mới?
Bạn ước lượng chi phí, thời gian và ảnh hưởng hiệu năng khi re-encrypt một kho dữ liệu lớn như thế nào?
Bạn xử lý dữ liệu đang được ghi hoặc đọc trong lúc rotation diễn ra để tránh mất khả năng giải mã ra sao?
Bạn quản lý nhiều phiên bản khóa cùng tồn tại trong thời gian migration như thế nào để không nhầm key ID hoặc thuật toán?
Bạn thiết kế rollback cho một lần rotation thất bại như thế nào mà không đưa hệ thống trở lại dùng khóa đã bị nghi ngờ xâm phạm?
Bạn xác định điều kiện để ngừng hỗ trợ và xóa phiên bản khóa cũ sau khi dữ liệu đã được chuyển đổi đầy đủ ra sao?
Bạn quản lý chứng thư và khóa ký số khi cần thay khóa nhưng vẫn phải xác minh chữ ký được tạo trong quá khứ như thế nào?
Bạn phân biệt rotation khóa mã hóa dữ liệu với rotation khóa ký số, và các tác động khác nhau tới dữ liệu đã ký ra sao?
Bạn thiết kế quy trình thu hồi khóa khi có bằng chứng khóa bị lộ hoặc nhân sự có quyền truy cập rời tổ chức như thế nào?
Bạn đánh giá phạm vi ảnh hưởng của một khóa bị xâm phạm dựa trên dữ liệu, hệ thống, tenant và khoảng thời gian đã sử dụng khóa ra sao?
Bạn ứng phó thế nào khi khóa giải mã bị lộ nhưng ciphertext và bản sao lưu vẫn đang tồn tại ở nhiều vùng?
Bạn xử lý sự cố khi khóa ký bị lộ và các chữ ký giả có thể đã được phát hành như thế nào?
Bạn phân biệt vô hiệu hóa, thu hồi, lên lịch hủy và hủy vật lý khóa trong KMS/HSM ra sao?
Bạn xác minh việc hủy khóa đã hoàn tất và không còn bản sao có thể khôi phục trong backup hoặc replica như thế nào?
Bạn đánh giá hệ quả nghiệp vụ khi hủy nhầm khóa duy nhất có thể giải mã dữ liệu lưu trữ như thế nào?
Bạn thiết kế quy trình khôi phục khóa khi KMS hoặc HSM gặp sự cố mà vẫn giữ nguyên kiểm soát truy cập và dual control ra sao?
Bạn lựa chọn cách backup và escrow khóa như thế nào để cân bằng khả năng khôi phục với nguy cơ tạo thêm bản sao nhạy cảm?
Bạn kiểm thử khả năng restore khóa và giải mã dữ liệu trong diễn tập disaster recovery với tần suất nào?
Bạn bảo đảm khóa được backup ở dạng bảo vệ phù hợp và không xuất hiện dưới dạng plaintext trong kho backup như thế nào?
Bạn xử lý trường hợp KMS không khả dụng hoặc vượt quota trong khi ứng dụng cần thực hiện thao tác mã hóa quan trọng ra sao?
Bạn thiết kế cache kết quả hoặc material đã giải mã từ KMS như thế nào để giảm độ trễ mà không kéo dài quá mức thời gian phơi nhiễm khóa?
Bạn quản lý giới hạn request, retry, backoff và circuit breaker khi nhiều dịch vụ cùng phụ thuộc vào KMS ra sao?
Bạn xây dựng kiến trúc multi-region cho KMS và khóa như thế nào để hỗ trợ độ sẵn sàng mà vẫn kiểm soát việc sao chép khóa?
Bạn xử lý khác biệt chính sách và trạng thái phiên bản khóa giữa các vùng khi replication bị trễ hoặc gián đoạn ra sao?
Bạn thiết kế cách ly khóa giữa các tenant trong hệ thống dùng chung KMS như thế nào để tránh truy cập chéo?
Bạn quyết định dùng khóa riêng từng tenant hay khóa dùng chung có context ràng buộc dựa trên mô hình rủi ro nào?
Bạn kiểm tra tính toàn vẹn của encryption context hoặc associated data để ngăn ciphertext bị dùng sai tenant hoặc sai mục đích như thế nào?
Bạn sử dụng authenticated encryption và quản lý nonce hoặc IV như thế nào để tránh tái sử dụng giá trị gây suy yếu bảo mật?
Bạn đánh giá rủi ro khi một ứng dụng tự sinh nonce sai cách hoặc dùng lại nonce với cùng khóa như thế nào?
Bạn quản lý khóa dẫn xuất từ master key bằng KDF như thế nào để tách biệt mục đích và phạm vi sử dụng?
Bạn lựa chọn giữa lưu khóa dẫn xuất, dẫn xuất khi cần hoặc dùng key hierarchy trong hệ thống có nhiều dịch vụ ra sao?
Bạn xây dựng crypto-agility để thay thuật toán, kích thước khóa hoặc nhà cung cấp KMS khi tiêu chuẩn bảo mật thay đổi như thế nào?
Bạn đánh giá và lập kế hoạch chuyển đổi khi một thuật toán hoặc độ dài khóa sắp không còn được khuyến nghị sử dụng ra sao?
Bạn chuẩn bị lộ trình chuyển đổi sang thuật toán hậu lượng tử cho các hệ thống có dữ liệu cần bảo mật dài hạn như thế nào?
Bạn quản lý khóa trong các luồng TLS, code signing, token signing và mã hóa dữ liệu lưu trữ với chính sách riêng biệt ra sao?
Bạn thiết kế quy trình cấp phát và thu hồi quyền sử dụng khóa cho workload identity, service account và nhân sự như thế nào?
Bạn kiểm soát quyền truy cập khẩn cấp vào khóa trong tình huống sự cố production mà vẫn bảo đảm có phê duyệt và audit ra sao?
Bạn xây dựng audit trail cho thao tác tạo, sử dụng, rotation, export, disable, restore và destroy khóa như thế nào?
Bạn xác định log nào cần lưu để truy vết việc sử dụng khóa mà không ghi lại key material hoặc dữ liệu plaintext như thế nào?
Bạn phát hiện dấu hiệu bất thường như giải mã hàng loạt, truy cập ngoài giờ hoặc thao tác key policy trái phép bằng cách nào?
Bạn thiết kế cảnh báo cho khóa sắp hết hạn, chứng thư sắp hết hạn, rotation thất bại và backup chưa kiểm chứng ra sao?
Bạn kiểm toán định kỳ inventory, key policy, quyền IAM và các khóa không còn chủ sở hữu như thế nào?
Bạn xây dựng bằng chứng để chứng minh khóa được tạo, bảo vệ, xoay vòng, thu hồi và hủy theo chính sách đã phê duyệt ra sao?
Bạn đánh giá rủi ro khi nhà cung cấp KMS thay đổi vùng lưu trữ, quy trình vận hành hoặc điều khoản truy cập khóa như thế nào?
Bạn xây dựng kế hoạch thoát khỏi một nhà cung cấp KMS để tránh phụ thuộc định dạng, API hoặc cơ chế backup độc quyền ra sao?
Bạn xử lý thế nào khi dữ liệu phải lưu giữ lâu hơn vòng đời của khóa hiện tại hoặc nhà cung cấp ngừng hỗ trợ thuật toán đang dùng?
Bạn thiết kế quy trình rà soát và phê duyệt ngoại lệ khi một hệ thống không thể rotation hoặc hủy khóa đúng hạn như thế nào?
Bạn lựa chọn chỉ số và SLO nào để đo độ sẵn sàng, độ trễ, lỗi thao tác và mức tuân thủ vòng đời khóa của nền tảng quản lý khóa?
Bạn tổ chức diễn tập sự cố lộ khóa và khôi phục khóa như thế nào để xác minh cả quy trình kỹ thuật lẫn trách nhiệm con người?
