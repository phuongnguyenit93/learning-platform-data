Một tổ chức có nhiều ứng dụng đích và muốn tự động đồng bộ danh tính từ hệ thống quản lý nhân sự; SCIM 2.0 giải quyết phần nào của bài toán provisioning và phần nào nằm ngoài phạm vi chuẩn?
SCIM khác với giao thức xác thực hoặc liên kết đăng nhập như SAML và OpenID Connect như thế nào trong kiến trúc quản lý danh tính?
Trong mô hình SCIM, Identity Provider và Service Provider thường giữ vai trò client và server ra sao, và dữ liệu đi theo chiều nào?
Khi một ứng dụng đích cung cấp SCIM endpoint, những năng lực nào cần được công bố để hệ thống nguồn biết cách tương tác an toàn và tương thích?
RFC về SCIM 2.0 phân chia trách nhiệm giữa core schema và protocol như thế nào, và vì sao cần hiểu cả hai khi tích hợp?
Một hệ thống cần thêm thuộc tính nhân sự ngoài User schema chuẩn; làm thế nào thiết kế schema extension có namespace ổn định và tránh xung đột?
Các thuộc tính SCIM có kiểu simple, complex và multi-valued ảnh hưởng việc ánh xạ dữ liệu nguồn sang JSON resource như thế nào?
Làm thế nào lựa chọn thuộc tính nào là required, readOnly, readWrite, immutable hoặc returned để hai phía không diễn giải sai quyền cập nhật?
Những khác biệt về caseExact, uniqueness và mutability của thuộc tính ảnh hưởng việc so khớp định danh ra sao?
Một hệ thống cần kiểm tra khả năng hỗ trợ filter, sort, patch, bulk và authentication của đối tác; nên khám phá ServiceProviderConfig và các endpoint discovery nào?
Schemas và ResourceTypes endpoint hỗ trợ client khám phá schema cùng loại resource được hỗ trợ như thế nào?
User resource trong SCIM cần những thuộc tính nào để định danh, liên hệ và biểu diễn trạng thái tài khoản?
Group resource biểu diễn nhóm và membership ra sao, và làm thế nào phân biệt nhóm provisioning với nhóm dùng cho authorization trong ứng dụng đích?
Một tổ chức có nhiều loại người dùng như nhân viên, nhà thầu và đối tác; làm thế nào biểu diễn khác biệt bằng schema extension hoặc thuộc tính chuẩn mà vẫn tương thích?
Thuộc tính userName cần đáp ứng yêu cầu uniqueness như thế nào, và điều gì xảy ra khi nguồn danh tính thay đổi username của một người?
SCIM id và externalId khác nhau về chủ thể cấp phát, phạm vi và mục đích đối chiếu như thế nào?
Làm thế nào duy trì mapping ổn định giữa identifier ở HR, IdP và nhiều ứng dụng đích khi email hoặc username có thể thay đổi?
Khi một người có nhiều email, số điện thoại hoặc địa chỉ, làm thế nào ánh xạ primary, type và giá trị multi-valued mà không làm mất dữ liệu?
Enterprise User extension có thể bổ sung thông tin tổ chức nào, và làm thế nào tránh phụ thuộc quá mức vào extension riêng của một nhà cung cấp?
Một client muốn tạo tài khoản mới; POST /Users cần xử lý thuộc tính bắt buộc, giá trị mặc định và phản hồi resource được tạo như thế nào?
Khi client gửi PUT để cập nhật User, ngữ nghĩa thay thế resource ảnh hưởng các thuộc tính không được gửi lên ra sao?
SCIM PATCH khác JSON Patch tổng quát như thế nào về cấu trúc request, operation và cách chỉ định path?
Làm thế nào lựa chọn giữa PATCH với op add, replace và remove khi cập nhật một thuộc tính đơn, thuộc tính multi-valued hoặc một phần của complex attribute?
Một client cần xóa một thành viên khỏi Group mà không thay đổi các thành viên khác; làm thế nào dùng PATCH path filter trên members?
Khi PATCH có nhiều Operations và một operation thất bại, Service Provider cần xử lý và phản hồi lỗi theo hợp đồng nào?
Làm thế nào xử lý PATCH không có path, path trỏ tới thuộc tính không tồn tại hoặc giá trị không đúng kiểu schema?
DELETE /Users khác với cập nhật active=false như thế nào về ngữ nghĩa vòng đời, khả năng khôi phục và kỳ vọng của ứng dụng đích?
Khi client gửi cùng một thay đổi nhiều lần do retry, làm thế nào thiết kế thao tác provisioning có tính idempotent ở mức nghiệp vụ?
SCIM filter syntax hỗ trợ những phép so sánh và biểu thức logic nào, và client cần xử lý khác biệt hỗ trợ filter giữa các Service Provider ra sao?
Làm thế nào xây dựng filter an toàn để tìm User theo externalId hoặc userName mà không tạo biểu thức sai cú pháp hay truy vấn quá rộng?
Khi filter chứa ký tự đặc biệt, dấu nháy hoặc Unicode, client cần escape và encode như thế nào để tránh lỗi hoặc injection?
Các tham số sortBy, sortOrder, startIndex và count được sử dụng như thế nào khi liệt kê resource?
Pagination dựa trên startIndex và count có những rủi ro gì khi tập dữ liệu thay đổi trong lúc client đang duyệt nhiều trang?
Làm thế nào phát hiện đã lấy đủ dữ liệu khi totalResults lớn hơn số resource trả về và response có count hoặc itemsPerPage khác kỳ vọng?
Tham số attributes và excludedAttributes giúp giới hạn dữ liệu trả về như thế nào, và cần cân nhắc gì khi chọn trường nhạy cảm?
Bulk endpoint giải quyết nhu cầu nào khi cần tạo hoặc cập nhật nhiều User và Group trong một đợt provisioning?
Một Bulk request có các operation tham chiếu resource được tạo trước đó bằng bulkId; Service Provider cần giải quyết tham chiếu tạm này như thế nào?
Bulk operation có bảo đảm transaction atomic cho toàn bộ request không, và client nên xử lý kết quả thành công một phần ra sao?
Tham số failOnErrors ảnh hưởng việc dừng xử lý Bulk request như thế nào, và client nên chọn ngưỡng dựa trên tiêu chí gì?
Làm thế nào kiểm tra giới hạn maxOperations và maxPayloadSize trước khi chia lô Bulk để tránh request bị từ chối?
Một ứng dụng đích trả lỗi SCIM với status, scimType và detail; client nên phân loại lỗi validation, uniqueness, authorization và lỗi tạm thời như thế nào?
Trong quy trình Joiner-Mover-Leaver, sự kiện nào nên kích hoạt tạo tài khoản, thay đổi quyền hoặc thu hồi quyền ở các ứng dụng đích?
Khi nhân viên mới được tuyển nhưng ngày bắt đầu làm việc ở tương lai, làm thế nào lập lịch provisioning để tránh cấp quyền quá sớm?
Một nhân viên chuyển phòng ban hoặc vị trí; làm thế nào xác định thuộc tính và group membership cần thêm, giữ lại hoặc loại bỏ?
Khi nhân viên rời tổ chức, làm thế nào phối hợp disable tài khoản, thu hồi session/token, xóa group membership và xử lý dữ liệu còn phải lưu giữ?
Vì sao việc xóa User ngay khi nhận sự kiện Leaver có thể không phù hợp, và khi nào nên dùng active=false trước khi xóa theo retention policy?
Làm thế nào xử lý nhân sự nghỉ rồi quay lại tổ chức mà không tạo danh tính trùng hoặc tái sử dụng nhầm account cũ?
Một tài khoản cần bị khóa khẩn cấp do rủi ro bảo mật; làm thế nào ưu tiên sự kiện deprovisioning so với các job đồng bộ định kỳ đang chờ?
Làm thế nào biểu diễn trạng thái suspended, inactive, pending và terminated khi SCIM core chỉ cung cấp tập thuộc tính chuẩn giới hạn?
Khi một nguồn danh tính có nhiều trạng thái HR khác nhau, làm thế nào chuẩn hóa chúng thành lifecycle state có ý nghĩa với từng ứng dụng đích?
Làm thế nào ánh xạ department, manager, costCenter, title và organization unit từ nguồn nhân sự sang schema SCIM mà không làm mất ngữ nghĩa?
Một người thuộc nhiều nhóm dựa trên phòng ban, dự án và vai trò; làm thế nào tính toán group membership và tránh ghi đè nhóm do người quản trị ứng dụng quản lý thủ công?
Khi Group membership được cập nhật đồng thời bởi SCIM client và administrator của ứng dụng đích, làm thế nào xử lý xung đột và xác định nguồn có thẩm quyền?
Những khác biệt nào giữa group, role và entitlement cần được làm rõ trước khi đồng bộ quyền truy cập qua SCIM?
Làm thế nào kiểm soát nested group hoặc membership gián tiếp khi Service Provider không hỗ trợ đầy đủ cấu trúc nhóm từ hệ thống nguồn?
Khi một entitlement đặc quyền được cấp thông qua group membership, làm thế nào bảo đảm việc gỡ thành viên được truyền tới ứng dụng đích kịp thời?
Làm thế nào xử lý trường hợp user đã tồn tại trong ứng dụng đích nhưng chưa có externalId hoặc mapping từ nguồn danh tính?
Khi email hoặc username bị thay đổi, làm thế nào tránh tạo user mới và liên kết nhầm tài khoản của hai cá nhân?
Một người có nhiều bản ghi nguồn do hợp nhất HR hoặc trùng nhân sự; quy tắc matching nào giúp hợp nhất định danh mà không chiếm nhầm tài khoản?
Làm thế nào thiết kế reconciliation định kỳ để phát hiện tài khoản mồ côi, thiếu thuộc tính, group membership sai hoặc thay đổi ngoài luồng SCIM?
Khi phát hiện drift giữa trạng thái mong muốn ở IdP và trạng thái thực tế ở Service Provider, làm thế nào quyết định sửa tự động hay đưa vào hàng chờ kiểm tra?
Client cần retry khi gặp timeout hoặc lỗi 5xx; làm thế nào dùng exponential backoff, jitter và giới hạn retry để tránh tạo tải tăng đột biến?
Khi request tạo User timeout nhưng server có thể đã commit resource, client làm thế nào tra cứu và đối chiếu trước khi gửi lại POST?
SCIM có định nghĩa idempotency key chung cho mọi request hay không, và client/server nên thiết kế cơ chế chống tạo trùng dựa trên identifier cùng trạng thái ra sao?
ETag và điều kiện If-Match có thể hỗ trợ phát hiện cập nhật đồng thời hoặc ghi đè phiên bản resource cũ như thế nào?
Khi client nhận 429 hoặc 503, làm thế nào sử dụng Retry-After và giới hạn concurrency để tôn trọng rate limit của Service Provider?
Một job provisioning phải phân trang hàng chục nghìn User nhưng bị gián đoạn giữa chừng; làm thế nào lưu checkpoint và tiếp tục mà không bỏ sót hoặc xử lý trùng?
Làm thế nào phân biệt lỗi cấu hình vĩnh viễn với lỗi mạng tạm thời để tránh retry vô hạn một request không thể thành công?
Khi nhiều worker đồng bộ cùng một User hoặc Group, làm thế nào phân vùng công việc và khóa xử lý để tránh race condition?
Những cơ chế xác thực nào phù hợp để bảo vệ SCIM endpoint, và làm thế nào giới hạn credential theo đúng client, tenant và hành động provisioning?
Vì sao SCIM traffic cần được bảo vệ bằng TLS, và trong trường hợp nào mutual TLS hoặc ràng buộc danh tính máy có thể tăng cường bảo vệ?
Làm thế nào quản lý bearer token hoặc client credential dùng cho provisioning, bao gồm lưu trữ, rotation, expiry và thu hồi khẩn cấp?
Một token provisioning bị lộ; làm thế nào giới hạn blast radius và xác định những tài khoản, nhóm hoặc thuộc tính có thể đã bị thay đổi?
Làm thế nào phân quyền tối thiểu để một client chỉ được tạo hoặc cập nhật loại resource cần thiết mà không có quyền quản trị toàn bộ ứng dụng?
Những biện pháp nào giúp bảo vệ SCIM endpoint trước enumeration, filter injection, payload quá lớn và lạm dụng Bulk API?
Làm thế nào giới hạn thuộc tính nhạy cảm được trả về từ User API và bảo đảm log không lưu token, dữ liệu cá nhân hoặc secret không cần thiết?
Audit log cần ghi nhận những trường nào để truy vết ai đã tạo, sửa, vô hiệu hóa hoặc xóa User và Group qua SCIM?
Làm thế nào liên kết audit event giữa yêu cầu từ IdP, request SCIM, resource đích và sự kiện thay đổi ở hệ thống downstream?
Khi provisioning thất bại một phần, làm thế nào hiển thị trạng thái cho vận hành và cho phép replay có kiểm soát sau khi khắc phục?
Một Service Provider ngừng hoạt động trong nhiều giờ; làm thế nào xếp hàng thay đổi, bảo đảm thứ tự lifecycle và phục hồi đồng bộ sau khi dịch vụ trở lại?
Làm thế nào phát hiện một tài khoản đã bị xóa hoặc disable ở IdP nhưng vẫn hoạt động ở một ứng dụng đích do mất sự kiện?
Những kiểm tra định kỳ nào giúp chứng minh quyền truy cập đã được thu hồi ở tất cả ứng dụng khi nhân sự rời tổ chức?
Làm thế nào thử nghiệm tương thích SCIM giữa nhiều nhà cung cấp có khác biệt về schema extension, filter support, PATCH và Bulk capability?
Khi nâng cấp schema hoặc thay đổi attribute mapping, làm thế nào triển khai tương thích ngược để tránh làm hỏng provisioning đang chạy?
Một tổ chức có nhiều tenant và nhiều nguồn danh tính; làm thế nào cô lập mapping, credential, group và reconciliation để tránh đồng bộ chéo tenant?
Những chỉ số nào giúp đánh giá độ tin cậy của provisioning, chẳng hạn độ trễ tạo tài khoản, tỷ lệ lỗi, drift và thời gian thu hồi quyền?
Làm thế nào xây dựng runbook và diễn tập khôi phục để bảo đảm provisioning và deprovisioning tiếp tục đúng khi IdP, network hoặc Service Provider gặp sự cố?
Thuộc tính schemas trong mỗi SCIM resource biểu thị các schema URN áp dụng như thế nào khi resource chứa cả core schema và extension schema?
