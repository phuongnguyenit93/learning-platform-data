1. SCIM 2.0 chủ yếu giải quyết nhu cầu nào trong quản lý danh tính?
A. Xác thực tương tác người dùng khi đăng nhập vào ứng dụng.
B. Mã hóa dữ liệu danh tính giữa các hệ thống qua mạng.
C. Đồng bộ bản ghi DNS và địa chỉ máy chủ trong tổ chức.
D. Provision, cập nhật và thu hồi User/Group ở ứng dụng đích.
Đáp án đúng: D

2. Trong mô hình SCIM phổ biến, Identity Provider và ứng dụng đích thường đảm nhiệm vai trò nào?
A. IdP là SCIM client; ứng dụng đích là SCIM Service Provider.
B. IdP là Service Provider; ứng dụng đích chỉ gửi webhook về IdP.
C. Cả hai đều là client và không bên nào cung cấp resource endpoint.
D. IdP chỉ xác thực TLS; ứng dụng đích tự đọc cơ sở dữ liệu HR.
Đáp án đúng: A

3. Khác biệt nào mô tả đúng SCIM Core Schema và SCIM Protocol?
A. Core Schema mô tả resource và attribute; Protocol quy định API và thao tác.
B. Core Schema định nghĩa HTTP status; Protocol định nghĩa thuộc tính User.
C. Core Schema chỉ dùng cho Group; Protocol chỉ dùng cho User.
D. Core Schema quản lý token; Protocol quy định thuật toán mã hóa.
Đáp án đúng: A

4. ServiceProviderConfig endpoint giúp SCIM client khám phá điều gì?
A. Danh sách User hiện có và mật khẩu của từng tài khoản.
B. Khả năng PATCH, Bulk, Filter, Sort và giới hạn liên quan.
C. Toàn bộ policy authorization được ứng dụng đích áp dụng.
D. Lịch sử mọi thay đổi thuộc tính từ khi tenant được tạo.
Đáp án đúng: B

5. Hai endpoint /Schemas và /ResourceTypes phục vụ mục đích nào?
A. Lấy danh sách phiên đăng nhập và token còn hiệu lực.
B. Cấp mới credential và xoay vòng secret cho SCIM client.
C. Khám phá schema và loại resource được hỗ trợ.
D. Liệt kê mọi thao tác Bulk đã hoàn tất trong tenant.
Đáp án đúng: C

6. Trong SCIM User resource, id và externalId khác nhau thế nào?
A. Cả hai đều do Service Provider tạo và không được client thay đổi.
B. id là email đăng nhập; externalId là mật khẩu đồng bộ từ HR.
C. externalId là khóa chính của database; id chỉ dùng để hiển thị.
D. Service Provider cấp id; client đặt externalId để đối chiếu.
Đáp án đúng: D

7. Một attribute được khai báo immutable trong schema có ý nghĩa gì?
A. Client có thể thay đổi giá trị ở mọi lần PATCH.
B. Attribute luôn bị loại khỏi response của Service Provider.
C. Có thể đặt lúc tạo; sau đó không được cập nhật.
D. Attribute chỉ có thể được cập nhật bởi người dùng cuối.
Đáp án đúng: C

8. Group resource trong SCIM biểu diễn membership như thế nào?
A. Dùng chuỗi tên nhóm phân tách bằng dấu phẩy trong displayName.
B. Dùng một role duy nhất được nhúng trong thuộc tính userName.
C. members là thuộc tính đa trị tham chiếu tới resource thành viên.
D. Dùng danh sách email không cần định danh resource đích.
Đáp án đúng: C

9. Quy tắc nào phù hợp với thuộc tính userName trong SCIM User?
A. userName duy nhất tại Service Provider; caseExact quy định so khớp.
B. userName bắt buộc là email và phải duy nhất trên toàn bộ Internet.
C. userName do client tự chọn nhưng Service Provider không được kiểm tra trùng.
D. userName có thể trùng nếu hai User thuộc các Group khác nhau.
Đáp án đúng: A

10. Khi POST tạo User thành công, phản hồi SCIM thường cần cung cấp điều gì?
A. HTTP 201, resource mới và Location phù hợp.
B. Chỉ trả HTTP 200 và không gửi định danh resource vừa tạo.
C. Trả HTTP 204 và yêu cầu client tự sinh giá trị id.
D. Trả HTTP 202 dù resource chưa được tạo hoặc lưu lại.
Đáp án đúng: A

11. PUT User khác PATCH User ở điểm nào?
A. PUT chỉ sửa attribute có trong body; PATCH thay toàn bộ resource.
B. PUT chỉ dùng để thêm Group membership; PATCH chỉ dùng để xóa User.
C. PUT thay resource; PATCH áp dụng operation chọn lọc.
D. PUT không thể cập nhật User đã tồn tại; PATCH luôn tạo resource mới.
Đáp án đúng: C

12. Cấu trúc SCIM PATCH request thường mô tả thay đổi bằng cách nào?
A. Dùng Operations gồm op, path và value khi cần.
B. Gửi nguyên resource mới cùng một cờ overwrite.
C. Dùng JSON Merge Patch với mọi quy tắc của HTTP PATCH.
D. Dùng trường SQL update và danh sách cột cần ghi.
Đáp án đúng: A

13. Nếu một operation trong SCIM PATCH thất bại, Service Provider nên xử lý thế nào?
A. PATCH atomic; không lưu thay đổi dở dang.
B. Áp dụng các operation trước đó rồi bỏ qua operation lỗi.
C. Bỏ qua lỗi và trả thành công nếu operation cuối cùng hợp lệ.
D. Chuyển PATCH thành PUT để xử lý phần còn lại.
Đáp án đúng: A

14. Muốn xóa một thành viên cụ thể khỏi Group mà giữ các thành viên khác, client nên làm gì?
A. DELETE toàn bộ Group rồi tạo lại với danh sách còn lại.
B. PATCH User với path displayName của Group.
C. PUT Group với members rỗng rồi thêm từng thành viên.
D. PATCH Group remove theo path lọc member cần xóa.
Đáp án đúng: D

15. Ý nghĩa nào phân biệt active=false và DELETE trên User resource?
A. Cả hai đều chỉ thay đổi mật khẩu và giữ nguyên resource.
B. active=false vô hiệu hóa; DELETE xóa resource.
C. DELETE chỉ ẩn User khỏi filter; active=false xóa vĩnh viễn bản ghi.
D. active=false chỉ hợp lệ với Group, không áp dụng cho User.
Đáp án đúng: B

16. SCIM filter thường hỗ trợ dạng biểu thức nào?
A. Có toán tử như eq, ne, co, sw, pr cùng biểu thức logic.
B. Dùng cú pháp SQL đầy đủ gồm JOIN, SELECT và subquery.
C. Chỉ hỗ trợ so khớp chuỗi chính xác bằng dấu bằng.
D. Chỉ nhận biểu thức regular expression do client tự định nghĩa.
Đáp án đúng: A

17. Filter chứa dấu nháy hoặc ký tự đặc biệt cần được xử lý thế nào?
A. Ghép trực tiếp giá trị vào URL để Service Provider tự sửa cú pháp.
B. Xóa mọi ký tự đặc biệt khỏi định danh trước khi gửi request.
C. Escape giá trị theo filter syntax rồi URL-encode query parameter.
D. Mã hóa toàn bộ filter bằng Base64 thay cho cú pháp SCIM.
Đáp án đúng: C

18. startIndex, count và totalResults có ý nghĩa nào trong pagination SCIM?
A. startIndex là offset bắt đầu từ 0; count là tổng số resource trong tenant.
B. startIndex là số trang; count là số trang còn lại; totalResults là page size.
C. startIndex từ 1; count là page size; totalResults là tổng kết quả.
D. startIndex là id resource; count là số thuộc tính; totalResults là phiên bản schema.
Đáp án đúng: C

19. attributes và excludedAttributes được dùng để làm gì?
A. Thay đổi schema của resource trước khi Service Provider lưu.
B. Chọn thuộc tính làm khóa chính thay cho SCIM id.
C. Chỉ định operation PATCH sẽ chạy trên từng attribute.
D. Chọn thuộc tính cần nhận hoặc loại khỏi response.
Đáp án đúng: D

20. bulkId trong SCIM Bulk request hỗ trợ tình huống nào?
A. Mã hóa định danh User để không lộ trong audit log.
B. Tham chiếu tạm tới resource được tạo trong cùng Bulk request.
C. Đánh dấu toàn bộ Bulk request phải rollback nếu có lỗi.
D. Thay thế id của mọi resource đã tồn tại trong Service Provider.
Đáp án đúng: B

21. Nhận định nào đúng về tính atomic của SCIM Bulk request?
A. Mọi operation luôn nằm trong một transaction và cùng commit hoặc rollback.
B. Bulk chỉ được phép chứa các operation đọc resource.
C. Bulk có thể thành công một phần; client xử lý từng operation.
D. Service Provider luôn bỏ qua lỗi operation nếu request có bulkId.
Đáp án đúng: C

22. Tham số failOnErrors trong Bulk request có tác dụng gì?
A. Giới hạn tổng số User mà tenant được phép tạo.
B. Đặt ngưỡng lỗi; vượt ngưỡng thì dừng xử lý Bulk.
C. Yêu cầu rollback các operation đã thành công khi có lỗi đầu tiên.
D. Đặt số lần client được phép retry cùng một Bulk request.
Đáp án đúng: B

23. Một SCIM request bị từ chối do thuộc tính sai kiểu. Error response hữu ích nên chứa gì?
A. Chỉ một trang HTML mô tả lỗi chung cho người dùng cuối.
B. Nội dung resource đầy đủ cùng mọi credential đã gửi.
C. Stack trace nội bộ và câu lệnh truy vấn database.
D. SCIM Error gồm status, detail và scimType nếu có.
Đáp án đúng: D

24. Service Provider trả HTTP 409 với scimType uniqueness khi tạo User. Client nên làm gì?
A. Retry ngay cùng POST cho tới khi nhận HTTP 201.
B. Đối chiếu userName/externalId với User hiện có.
C. Tăng timeout vì lỗi uniqueness luôn là lỗi mạng tạm thời.
D. Chuyển request thành DELETE để giải phóng userName.
Đáp án đúng: B

25. ETag và If-Match giúp bảo vệ cập nhật SCIM như thế nào?
A. If-Match so ETag; lệch phiên bản thì từ chối ghi đè.
B. Tự động mã hóa request body trước khi gửi tới endpoint.
C. Đảm bảo mọi Bulk operation được commit như một transaction.
D. Cấp một externalId mới mỗi khi client cập nhật thuộc tính.
Đáp án đúng: A

26. Vì sao phân trang bằng startIndex/count có thể bỏ sót hoặc lặp User khi dữ liệu đang thay đổi?
A. Dữ liệu đổi làm vị trí resource dịch giữa các trang.
B. totalResults là số cố định và Service Provider không được cập nhật.
C. SCIM luôn khóa toàn bộ resource trong suốt mọi lần phân trang.
D. count chỉ áp dụng cho Group, không áp dụng cho User.
Đáp án đúng: A

27. Nhân viên mới có ngày bắt đầu trong tương lai. Cách provisioning nào hợp lý?
A. Cấp quyền đầy đủ ngay khi HR tạo hồ sơ và bỏ qua ngày bắt đầu.
B. Không tạo định danh cho tới khi nhân viên tự đăng nhập lần đầu.
C. Provision inactive trước; kích hoạt đúng ngày bắt đầu.
D. Tạo tài khoản rồi xóa ngay, sau đó tạo lại vào ngày bắt đầu.
Đáp án đúng: C

28. Khi nhân viên chuyển phòng ban, connector nên cập nhật thế nào?
A. Chỉ thay department và luôn giữ mọi Group cũ.
B. Tính lại Group từ nguồn chuẩn; gỡ membership do nguồn quản lý.
C. Xóa User rồi tạo tài khoản mới để tránh xung đột quyền.
D. Chuyển mọi Group của nhân viên thành role quản trị tạm thời.
Đáp án đúng: B

29. Khi nhận sự kiện Leaver, cách xử lý nào phản ánh đúng vòng đời và giới hạn SCIM?
A. Chỉ đổi email để người dùng không nhận được thông báo.
B. Chọn active=false hoặc DELETE theo retention; session revoke riêng.
C. Chỉ xóa Group membership và mặc định mọi session tự hết hiệu lực.
D. Giữ tài khoản active cho tới kỳ reconciliation hàng tháng.
Đáp án đúng: B

30. POST tạo User bị timeout nhưng server có thể đã lưu resource. Client nên làm gì trước khi gửi lại?
A. Gửi lại POST nhiều lần cho tới khi nhận response thành công.
B. Tạo externalId mới để tránh xung đột với request chưa rõ kết quả.
C. Tra cứu User bằng externalId trước khi retry.
D. Xóa toàn bộ User cùng userName để bảo đảm request có thể chạy lại.
Đáp án đúng: C

31. Nhận định nào đúng về idempotency trong SCIM?
A. SCIM định nghĩa một Idempotency-Key bắt buộc cho mọi endpoint.
B. POST luôn idempotent nên client có thể retry mà không cần đối chiếu.
C. PUT và PATCH luôn có cùng kết quả bất kể operation hoặc giá trị gửi.
D. SCIM không có idempotency key chung; dùng externalId và reconcile.
Đáp án đúng: D

32. Client nhận HTTP 429 khi provision nhiều User. Cách retry nào phù hợp?
A. Bỏ qua throttling và tăng concurrency để hoàn tất nhanh hơn.
B. Retry liên tục theo chu kỳ cố định để không bỏ lỡ request.
C. Chuyển request sang endpoint tenant khác để né giới hạn.
D. Tôn trọng Retry-After, backoff jitter và giới hạn concurrency.
Đáp án đúng: D

33. Biện pháp nào bảo vệ SCIM bearer token phù hợp?
A. Ghi token vào log để vận hành có thể kiểm tra khi lỗi.
B. Lưu token an toàn, giới hạn scope, dùng TLS và rotation.
C. Dùng chung một token quản trị cho mọi tenant và mọi connector.
D. Đặt token trong query string để proxy dễ chuyển tiếp.
Đáp án đúng: B

34. Connector phục vụ nhiều tenant cần kiểm soát nào để tránh provisioning chéo?
A. Dùng một mapping toàn cục và tự suy ra tenant từ email.
B. Dùng cùng bearer token nhưng đổi tên Group theo tenant.
C. Chỉ kiểm tra tenant khi tạo User, không cần kiểm tra khi PATCH.
D. Cô lập base URL, credential, mapping và job theo từng tenant.
Đáp án đúng: D

35. Nguyên tắc data minimization nên áp dụng với SCIM provisioning ra sao?
A. Đồng bộ mọi trường HR để ứng dụng đích tự chọn trường cần dùng.
B. Gửi trường cần thiết; che dữ liệu nhạy cảm trong log.
C. Sao chép cả hồ sơ cá nhân vào mọi ứng dụng để tránh thiếu thuộc tính.
D. Lưu request body và bearer token lâu dài để phục vụ kiểm toán.
Đáp án đúng: B

36. Audit trail cho provisioning cần ghi nhận điều gì để truy vết thay đổi?
A. Chỉ ghi tổng số request thành công theo ngày.
B. Chỉ lưu HTTP status mà không lưu resource hoặc nguồn yêu cầu.
C. Chỉ lưu tên connector để tránh ghi nhận danh tính actor.
D. Actor, resource, thay đổi, thời điểm, kết quả và ID truy vết.
Đáp án đúng: D
