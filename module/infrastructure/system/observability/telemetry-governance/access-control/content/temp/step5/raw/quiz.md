1. Trong nền tảng observability, xác thực (authentication) trả lời câu hỏi nào?
A. Tài nguyên metrics, logs hay traces nào được yêu cầu đọc?
B. Danh tính người hoặc workload đang gửi yêu cầu là ai?
C. Thao tác có được phép trên tenant và dataset cụ thể?
D. Thời hạn lưu giữ dữ liệu nào áp dụng cho yêu cầu?
Đáp án đúng: B

2. Một dashboard dùng OIDC đăng nhập qua nhà cung cấp danh tính. OIDC chủ yếu hỗ trợ việc gì?
A. Lọc truy vấn PromQL theo tenant đang được chọn trên giao diện.
B. Mã hóa dữ liệu metrics khi lưu vào backend time-series.
C. Tự cấp quyền quản trị cho mọi tài khoản đăng nhập hợp lệ.
D. OIDC xác minh danh tính người dùng qua nhà cung cấp danh tính.
Đáp án đúng: D

3. Gateway nhận OTLP từ collector agent qua mTLS. Chứng thư client giúp xác định điều gì?
A. Danh sách metric mà workload được phép đọc từ backend.
B. Tenant của mọi span do workload gửi qua gateway.
C. Chứng thư xác định danh tính workload ở kết nối.
D. Mức độ nhạy cảm của log nằm trong payload OTLP.
Đáp án đúng: C

4. Sau khi gateway xác thực bearer token hợp lệ, bước nào vẫn cần thiết?
A. Tin mọi tenant_id có trong request vì token đã được xác minh.
B. Cho phép mọi API method vì token chứng minh người gọi hợp lệ.
C. Chỉ kiểm tra thời hạn token khi người dùng tải dashboard.
D. Vẫn kiểm quyền theo principal, action và resource.
Đáp án đúng: D

5. RBAC thường quyết định quyền truy cập dựa trên yếu tố nào?
A. Mọi thuộc tính của request như giờ, IP và nhãn tenant.
B. Giá trị metric hiện tại cùng severity của alert liên quan.
C. Tên dashboard và thứ tự các panel hiển thị trên trang.
D. Vai trò được gán cho principal và quyền của vai trò đó.
Đáp án đúng: D

6. ABAC phù hợp khi chính sách cần xét các thuộc tính nào?
A. Role tĩnh được gán lúc tạo tài khoản người dùng.
B. Principal, resource, action và context của yêu cầu.
C. Tên service và số lượng span trong trace đang xem.
D. Địa chỉ mạng của gateway gửi dữ liệu đến backend.
Đáp án đúng: B

7. Một service chỉ cần gửi telemetry vào collector, không cần truy vấn dữ liệu. Cấp quyền nào phù hợp?
A. Cấp quyền admin toàn backend để service tự tìm dữ liệu của mình.
B. Dùng chung tài khoản đọc/ghi với dashboard của nhóm vận hành.
C. Cho phép xóa mọi log cũ để agent quản lý dung lượng lưu trữ.
D. Chỉ cấp quyền ingest vào pipeline đã được chỉ định.
Đáp án đúng: D

8. Nhóm phát triển chỉ cần xem dashboard của service mình. Cấu hình nào theo least privilege?
A. Role editor trên toàn tổ chức để họ tự xử lý panel khi cần.
B. Role chỉ đọc và giới hạn dashboard theo service phụ trách.
C. Quyền quản trị kho traces để có thể tìm mọi request liên quan.
D. Tài khoản dùng chung có quyền sửa dashboard và xóa dữ liệu.
Đáp án đúng: B

9. API token được dùng để truy vấn metrics. Phạm vi quyền nào nên được chọn?
A. Scope admin toàn bộ telemetry để tránh lỗi thiếu quyền về sau.
B. Scope ingest logs vì mọi dữ liệu đều được lưu trong một kho.
C. Scope đọc metrics cần thiết cho tenant và service tương ứng.
D. Scope quản lý danh tính để token có thể cấp lại chính nó.
Đáp án đúng: C

10. Một khách hàng gửi tenant_id=acme trong HTTP header khi ingest telemetry. Gateway nên xử lý ra sao?
A. Map tenant từ identity đã xác thực, không tin header.
B. Tin header vì client thường biết tenant mà họ đang sử dụng.
C. Chọn tenant từ trường service.name do ứng dụng tự khai báo.
D. Ghi nhận cả tenant header và bỏ qua danh tính kết nối.
Đáp án đúng: A

11. Vì sao không nên dùng tenant label do client tự gửi làm ranh giới bảo mật?
A. Client có thể giả mạo nhãn tenant để truy cập chéo.
B. Nhãn tenant làm tăng cardinality nên backend không thể lưu metrics.
C. Client thường gửi nhãn trước khi TLS handshake được hoàn tất.
D. Label không được hỗ trợ trong định dạng OTLP chuẩn.
Đáp án đúng: A

12. Backend observability dùng chung cho nhiều tenant. Điểm nào phải thực thi cách ly dữ liệu?
A. Ẩn dashboard khỏi menu là chưa đủ để cách ly dữ liệu.
B. Thêm tenant_id vào panel vẫn để client tự lọc kết quả.
C. Ở lớp truy vấn và lưu trữ phía server theo identity đã xác minh.
D. Namespace riêng ở collector chưa đủ khi query API còn dùng chung.
Đáp án đúng: C

13. Một query API nhận tenant context từ gateway. Cách ngăn truy vấn vượt tenant hiệu quả là gì?
A. Cho client tự thêm filter tenant_id vào câu truy vấn trước khi gửi.
B. Kiểm tra tenant trên giao diện sau khi backend trả toàn bộ kết quả.
C. Dựa vào tên dashboard để suy ra tenant được phép xem.
D. Ràng buộc tenant vào authorization và query scope phía server.
Đáp án đúng: D

14. Trong collector gateway nhiều tenant, credential của từng nguồn ingest nên được quản lý thế nào?
A. Ánh xạ danh tính đã xác thực sang tenant và pipeline được phép.
B. Dùng một token chung cho mọi tenant để giảm chi phí vận hành.
C. Tin resource attribute tenant do agent ghi vào payload OTLP.
D. Cấp quyền sửa routing cho mọi agent để chúng tự chọn tenant.
Đáp án đúng: A

15. Một collector nhận telemetry từ nhiều workload. Vì sao cần phân biệt quyền ingest và quyền quản trị pipeline?
A. Hai quyền giống nhau vì ingest luôn yêu cầu chỉnh pipeline.
B. Quản trị pipeline chỉ liên quan dashboard, không ảnh hưởng dữ liệu.
C. Workload gửi dữ liệu không nên tự thay đổi cấu hình collector.
D. Collector tự cô lập quyền dựa trên tên process gửi dữ liệu.
Đáp án đúng: C

16. mTLS giữa dashboard và query gateway cung cấp bảo đảm nào?
A. Mã hóa kênh và xác thực danh tính peer ở lớp kết nối.
B. Tự quyết định user nào được xem dashboard nào trong tổ chức.
C. Tự giới hạn tenant trong mọi câu truy vấn backend.
D. Tự ghi audit event cho mọi lần người dùng tải trang.
Đáp án đúng: A

17. Một workload Kubernetes cần danh tính máy để gửi traces. Cách cấp nào phù hợp?
A. Nhúng API key quản trị cố định vào image của container.
B. Dùng chung chứng thư của node cho mọi Pod trong cluster.
C. ServiceAccount gắn với workload identity và credential ngắn hạn.
D. Lấy tên namespace làm secret để xác thực với collector.
Đáp án đúng: C

18. Chứng thư workload gần hết hạn. Cách vận hành nào giảm gián đoạn và rủi ro?
A. Dùng một chứng thư dài hạn không cần thay đổi trong nhiều năm.
B. Chờ chứng thư hết hạn rồi cấp lại thủ công cho mọi Pod.
C. Tắt xác minh chứng thư khi gateway không nhận được cert mới.
D. Tự động xoay vòng chứng thư ngắn hạn trước khi hết hạn.
Đáp án đúng: D

19. API key của agent bị lộ. Phản ứng nào phù hợp?
A. Giữ key cũ đến kỳ rotation kế tiếp để tránh gián đoạn.
B. Chỉ đổi tên agent trên dashboard mà không thay credential.
C. Ẩn key khỏi log giao diện nhưng tiếp tục chấp nhận key đó.
D. Thu hồi key, cấp credential mới và rà soát lần sử dụng.
Đáp án đúng: D

20. Access token cho observability API nên được kiểm tra thuộc tính nào?
A. Kiểm issuer, audience, expiry và quyền/scope được cấp.
B. Tên file dashboard, số panel và độ dài query gửi lên.
C. Màu sắc giao diện và địa chỉ email trong phần mô tả.
D. Tốc độ ingest cùng số lượng log đã lưu trong backend.
Đáp án đúng: A

21. Một policy không có rule nào cho phép principal thực hiện thao tác. Mặc định an toàn nên là gì?
A. Cho phép truy cập nếu backend không tìm thấy rule tương ứng.
B. Từ chối yêu cầu cho tới khi quyền phù hợp được cấp rõ ràng.
C. Dùng quyền gần nhất của user khác trong cùng tenant.
D. Cho phép đọc metrics nhưng tự động chặn mọi logs và traces.
Đáp án đúng: B

22. Nhóm muốn quản lý policy bằng mã trong Git. Kiểm tra nào nên chạy trước khi triển khai?
A. Chỉ kiểm tra file YAML có thể mở bằng text editor.
B. Triển khai thẳng rồi xem người dùng có báo lỗi truy cập không.
C. So sánh kích thước file với phiên bản policy trước đó.
D. Validate policy và test quyền trước khi deploy.
Đáp án đúng: D

23. Khi thay đổi policy cấp quyền rộng hơn, quy trình review nào phù hợp?
A. Chủ dữ liệu và bảo mật cùng review thay đổi quyền.
B. Để người tạo policy tự duyệt và triển khai trực tiếp.
C. Bỏ lịch sử commit để tránh lộ thông tin về quyền nội bộ.
D. Chỉ kiểm tra syntax vì thay đổi quyền không ảnh hưởng runtime.
Đáp án đúng: A

24. Policy-as-code đã merge nhưng cấu hình đang chạy khác phiên bản Git. Cần xử lý thế nào?
A. Phát hiện drift rồi reconcile có kiểm soát.
B. Bỏ qua vì policy trong Git chỉ dùng để tham khảo khi audit.
C. Tự động mở toàn bộ quyền để hai phiên bản có thể tương thích.
D. Xóa audit log cũ rồi khởi động lại collector gateway.
Đáp án đúng: A

25. Một nhân viên chuyển nhóm và không còn phụ trách service cũ. Thao tác nào cần thực hiện?
A. Giữ quyền cũ để tránh dashboard hoặc alert bị gián đoạn.
B. Thu hồi role và credential không còn cần, cập nhật quyền theo vai trò mới.
C. Chỉ xóa tên nhân viên khỏi danh bạ nhưng không đổi IAM.
D. Cấp thêm quyền admin cho trưởng nhóm mới rồi để nguyên quyền cũ.
Đáp án đúng: B

26. Audit log cho lần thay đổi role nên ghi những thông tin nào?
A. Ghi actor, target, quyền đổi, thời điểm và outcome.
B. Password, private key và nội dung token của người thao tác.
C. Toàn bộ dữ liệu metrics đã xem trong phiên dashboard.
D. Chỉ tên role mới vì người thực hiện có thể suy ra sau này.
Đáp án đúng: A

27. Để audit log về truy cập observability có giá trị điều tra, nên bảo vệ ra sao?
A. Cho phép admin sửa log để xóa các lần truy cập nhầm.
B. Lưu actor/action/resource/outcome và hạn chế sửa xóa bản ghi.
C. Ghi audit vào cùng index mà principal được kiểm toán có quyền xóa.
D. Chỉ lưu số lần đăng nhập thành công, bỏ mọi lần bị từ chối.
Đáp án đúng: B

28. Một tài khoản service đọc hàng nghìn tenant trong thời gian ngắn. Kiểm soát nào giúp phát hiện?
A. Đối chiếu principal, tenant và hành vi truy vấn bất thường.
B. Tăng thời gian retention cho mọi metrics để dễ tìm hơn.
C. Ẩn dashboard của service account khỏi người dùng thông thường.
D. Giảm tần suất scrape để query API nhận ít dữ liệu hơn.
Đáp án đúng: A

29. Log chứa email và access token được gửi qua collector. Biện pháp nào nên áp dụng?
A. Loại secret và PII trước khi lưu hoặc forward.
B. Chỉ đặt dashboard ở chế độ private để người ngoài không xem được.
C. Mã hóa ổ đĩa backend rồi giữ nguyên secret trong mọi log.
D. Đưa token vào resource attribute để dễ truy vết nguồn phát sinh.
Đáp án đúng: A

30. Một trace có baggage chứa customer email. Rủi ro nào cần quản trị?
A. Baggage chỉ nằm trong process tạo trace nên không rời máy.
B. Email được tự động băm khi trace context qua HTTP gateway.
C. Baggage có thể lan qua nhiều service và exporter, gây lộ PII.
D. Chỉ span ID mới có thể chứa dữ liệu nhạy cảm trong trace.
Đáp án đúng: C

31. Metrics có label user_email do ứng dụng tự thêm. Hệ quả nào đáng quan tâm?
A. Tự mã hóa mọi metric sample và làm giảm dung lượng lưu trữ.
B. Email label làm lộ PII và tăng cardinality của metrics.
C. Ngăn backend nhận traces vì metrics và traces dùng chung protocol.
D. Chỉ làm dashboard khó đọc, không ảnh hưởng quyền truy cập dữ liệu.
Đáp án đúng: B

32. Một dashboard được chia sẻ bằng link công khai có thể truy cập không cần đăng nhập. Cần xem xét gì?
A. Link chỉ chứa bố cục nên không thể truy cập dữ liệu backend.
B. Chỉ cần đổi tên dashboard để link cũ tự mất hiệu lực.
C. Dữ liệu chỉ đọc nên không cần kiểm soát người truy cập.
D. Link có thể làm lộ dữ liệu; cần xác thực và giới hạn quyền chia sẻ.
Đáp án đúng: D

33. API query và API ingest dùng cùng credential admin. Thiết kế tốt hơn là gì?
A. Giữ một credential để giảm số lượng secret cần rotation.
B. Cấp quyền ingest cho mọi user query để họ tự gửi telemetry.
C. Tách danh tính và scope theo chức năng đọc, ghi và quản trị.
D. Chỉ giới hạn IP client vì quyền trong token không cần phân biệt.
Đáp án đúng: C

34. Một query request có quyền đọc tenant A nhưng yêu cầu resource thuộc tenant B. Quyết định đúng là gì?
A. Trả dữ liệu B nhưng ẩn nhãn tenant trong response JSON.
B. Cho phép nếu người dùng biết chính xác tên metric cần đọc.
C. Từ chối theo phạm vi tenant đã gắn với principal.
D. Chuyển truy vấn sang quyền của collector đã nhận dữ liệu.
Đáp án đúng: C

35. Khi cần hỗ trợ khẩn cấp truy cập dữ liệu tenant, break-glass nên được quản lý thế nào?
A. Tạo tài khoản admin dùng chung không hết hạn cho đội trực.
B. Quyền tạm thời, lý do rõ, phê duyệt và audit sau sử dụng.
C. Tắt audit để thao tác khẩn cấp không bị chậm.
D. Cấp quyền vĩnh viễn rồi thu hồi nếu có người yêu cầu.
Đáp án đúng: B

36. Một credential máy đã bị thu hồi nhưng gateway vẫn chấp nhận request. Nên kiểm tra gì?
A. Tên service trong resource attribute và thứ tự exporter pipeline.
B. Màu sắc dashboard và số panel đang mở trong trình duyệt.
C. Cache hoặc đường phân phối trạng thái thu hồi và thời gian hiệu lực token.
D. Mức log của collector và số request đã được lấy mẫu.
Đáp án đúng: C

37. Một nền tảng có metrics, logs và traces với độ nhạy khác nhau. Chính sách truy cập nên thiết kế ra sao?
A. Cấp một quyền đọc chung vì mọi tín hiệu đều thuộc observability.
B. Phân quyền theo loại dữ liệu, tenant, hành động và mục đích sử dụng.
C. Chỉ phân quyền theo tên dashboard, không xét API hoặc backend.
D. Tách ba kho nhưng dùng chung tài khoản quản trị không kiểm toán.
Đáp án đúng: B
