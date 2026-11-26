Ứng dụng đặt hàng gọi API khách hàng để lấy customerId, name và loyaltyTier; provider đổi tên loyaltyTier thành membershipLevel mà không thông báo, khiến consumer tính ưu đãi bằng giá trị rỗng dù endpoint vẫn trả HTTP 200.
Nhóm backend thêm trường địa chỉ tùy chọn vào phản hồi hồ sơ; một consumer cũ từ chối JSON có khóa không được khai báo, khiến thay đổi tưởng như tương thích vẫn làm hỏng luồng đăng ký.
API sản phẩm đổi kiểu price từ số thập phân sang chuỗi đã định dạng theo tiền tệ; giao diện người dùng vẫn nhận JSON hợp lệ nhưng phép tính tổng giỏ hàng không còn thực hiện được.
Consumer thanh toán chỉ sử dụng paymentId và status từ một phản hồi nhiều trường; nhóm provider đang kiểm tra toàn bộ snapshot JSON nên một trường mô tả không liên quan thay đổi cũng làm hợp đồng thất bại.
Ứng dụng di động phiên bản cũ vẫn gửi request thiếu trường customerChannel; bản provider mới bắt trường này và từ chối nhiều yêu cầu tạo đơn khi nhóm backend phát hành trước lịch nâng cấp ứng dụng.
API đặt vé hứa trả danh sách chỗ còn trống dưới dạng mảng, kể cả khi không còn chỗ; một nhánh triển khai mới trả null và giao diện bị lỗi khi duyệt phần tử.
Provider chuyển HTTP status của thao tác tạo tài nguyên từ 201 sang 200 để thống nhất với endpoint khác; một consumer dựa vào 201 để kích hoạt bước gửi email xác nhận đã ngừng hoạt động.
Consumer quản lý kho kỳ vọng lỗi thiếu hàng trả HTTP 409 với mã INSUFFICIENT_STOCK; bản provider mới chỉ trả thông báo văn bản chung, khiến ứng dụng không nhận ra tình huống cần gợi ý giảm số lượng.
Hệ thống thương mại có nhiều consumer yêu cầu các trường khác nhau từ API đơn hàng; hợp đồng do một consumer viết được dùng làm chuẩn duy nhất và vô tình bỏ sót yêu cầu của consumer báo cáo.
Nhóm xuất bản OpenAPI cho dịch vụ khách hàng, nhưng implementation trả thêm enum trạng thái SUSPENDED chưa có trong tài liệu; client sinh mã từ schema cũ gặp lỗi khi giải mã phản hồi.
Một hợp đồng API đánh dấu trường totalAmount là bắt buộc nhưng provider chỉ trả trường đó khi đơn đã hoàn tất; dữ liệu test của provider toàn đơn đã thanh toán nên chưa phát hiện sự khác biệt.
Nhóm consumer viết kiểm thử dựa trên ví dụ JSON từ tài liệu nhưng không ràng buộc kiểu dữ liệu hoặc tính bắt buộc của trường; provider trả string thay số và bài test vẫn xanh.
Một consumer đặt lịch chỉ sử dụng date, startTime và timezone; provider chuyển startTime sang timestamp UTC nhưng không sửa hợp đồng khiến lịch hiển thị lệch giờ trên ứng dụng.
Provider API tìm kiếm đổi mặc định sortOrder từ tăng dần sang giảm dần; shape của request và response không thay đổi, nhưng consumer xuất báo cáo mặc định theo thứ tự cũ bị sai kết quả.
Ứng dụng ngân hàng gửi idempotencyKey khi tạo chuyển khoản; provider mới bỏ qua header này trong một đường xử lý và tạo giao dịch trùng khi mạng khiến consumer gửi lại.
Một hợp đồng yêu cầu trường accountId luôn là chuỗi chữ số, nhưng provider bắt đầu phát mã có cả chữ cái; consumer vẫn parse string thành công nhưng quy tắc kiểm tra định danh không còn phù hợp.
Nhóm triển khai GraphQL bổ sung giá trị enum CANCELED_BY_SYSTEM vào trạng thái đơn; ứng dụng khách viết nhánh xử lý đóng cho các giá trị cũ và lỗi với giá trị vừa thêm.
Dịch vụ báo cáo chuyển sang phân trang cursor, đồng thời bỏ tham số page đã công bố; các consumer theo lịch hằng đêm vẫn dùng page và nhận cùng trang dữ liệu nhiều lần.
Trong hệ thống nhiều tenant, consumer gửi tenantId trong header nhưng provider mới chuyển sang path; test tích hợp trong cùng repository đã sửa cả hai đầu nên không phát hiện việc client cũ bị từ chối.
Hệ thống giao hàng có consumer cần nhận event ShipmentDispatched với shipmentId và dispatchedAt; producer đổi tên event thành ShipmentSent mà payload không đổi nên bộ định tuyến bỏ qua thông điệp.
Producer gửi event OrderPlaced bằng schema mới có trường amount dạng chuỗi; consumer cũ vẫn nhận từ topic nhưng không giải mã được sự kiện trước khi xử lý hóa đơn.
Consumer tính điểm dựa trên trường currency trong event PaymentCompleted; producer bỏ trường này do cho rằng toàn bộ hệ thống chỉ dùng VND, trong khi một khu vực đã hỗ trợ ngoại tệ.
Một sự kiện CustomerUpdated chỉ gửi các trường đã thay đổi, nhưng consumer hiểu trường không xuất hiện là yêu cầu xóa giá trị; hợp đồng message chưa mô tả rõ ý nghĩa absent và null.
Đội dữ liệu đổi khóa tương quan của event từ orderId sang transactionId; bộ xử lý lưu trạng thái vẫn theo orderId nên các thông điệp đúng schema không còn được ghép vào cùng luồng.
Producer phát cùng một event nhiều lần khi không nhận ack; consumer hiện mặc định mỗi messageId chỉ xuất hiện một lần và tăng số dư hai lần trong tình huống retry.
Một event theo schema Avro thêm trường bắt buộc không có default; job replay dữ liệu cũ không thể đọc bản ghi đã lưu, dù các event mới chạy bình thường.
Nhóm sử dụng Protobuf xóa một field cũ rồi tái sử dụng số thứ tự field đó cho ý nghĩa khác; consumer chưa nâng cấp đọc dữ liệu mới thành thông tin sai mà không phát hiện.
Trong rolling deployment, hai phiên bản producer hoạt động cùng lúc trên một topic; consumer chỉ thử nghiệm với schema mới nhất nên thất bại khi gặp message phát từ pod cũ.
API của provider đã triển khai hỗ trợ cả phiên bản v1 và v2, nhưng pipeline contract chỉ chạy bài kiểm tra v2; một thay đổi vô tình làm hỏng v1 vẫn được phát hành.
Nhóm lưu hợp đồng của consumer trong repository riêng, còn provider dùng bản copy cũ trong CI; hai bên đều thấy test PASS nhưng hợp đồng vừa cập nhật chưa từng được provider xác minh.
Một team muốn cho phép provider triển khai khi không có consumer nào sử dụng trường deprecated; registry có nhiều bản hợp đồng nhưng thiếu thông tin consumer nào thực sự còn đang chạy ở production.
Nhóm backend đổi validation của trường phone từ có thể rỗng sang bắt buộc; provider verification chỉ dùng dữ liệu hợp lệ nên không bắt được yêu cầu của consumer cho phép lưu hồ sơ chưa có số điện thoại.
Consumer gọi API tạo đơn nhiều bước và kỳ vọng trường lỗi detail có thể vắng mặt; provider gửi detail=null ở một nhánh và bài contract test không phân biệt được hai hình thức.
Trong kiểm thử consumer-driven, một consumer khai báo kỳ vọng cố định vào mã định danh ngẫu nhiên do provider tạo; hợp đồng thất bại theo từng lần chạy dù kiểu dữ liệu và ý nghĩa trả về vẫn đúng.
Nhóm định nghĩa stub cho dịch vụ thanh toán nhưng provider thật yêu cầu header xác thực bổ sung; consumer test với stub thành công còn gọi provider ở môi trường tích hợp nhận HTTP 401.
Dịch vụ cung cấp API trạng thái lô hàng dùng mã tracking đã tồn tại trong cơ sở dữ liệu test; khi dữ liệu bị làm mới, bài xác minh provider thất bại dù hợp đồng đầu vào và đầu ra chưa thay đổi.
Nhóm tự động phát hành thư viện client từ hợp đồng OpenAPI; sau khi chỉnh sửa schema, binary client sinh mới không tương thích với ứng dụng đã compile từ bản trước.
Trong pipeline CI nhiều microservice, provider contract verification chạy sau deploy production thay vì trước publish artifact; một thay đổi phá hợp đồng đã tới người dùng trước khi cảnh báo được phát hiện.
Nhóm phát hành API có nhiều consumer nội bộ và đối tác; pull request chỉnh response đã PASS unit test nhưng thiếu thông tin phiên bản hợp đồng tương ứng để quyết định thứ tự triển khai an toàn.
Một service chuyển thông báo từ REST polling sang event streaming trong khi vẫn cam kết API REST cũ; nhóm chưa xác định kỳ vọng nào phải được giữ nguyên trong giai đoạn hai cách tích hợp cùng tồn tại.
