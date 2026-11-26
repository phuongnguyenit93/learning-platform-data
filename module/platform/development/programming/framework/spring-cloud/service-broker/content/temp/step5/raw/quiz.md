Câu 01. Platform gọi endpoint nào của Open Service Broker API để đọc danh mục dịch vụ?
A. `GET /v2/service_bindings` liệt kê service và plan
B. `POST /v2/catalog` lấy danh mục service và plan hiện tại
C. `GET /v2/catalog` trả danh mục services và plans
D. `GET /v2/service_instances` trả về các service và plan
Đáp án đúng: C

Câu 02. Trong catalog của OSB API, quan hệ giữa service và plan được hiểu thế nào?
A. Một service biểu diễn loại dịch vụ, plan là gói cung cấp
B. Một plan là instance, service là mỗi lần thao tác update
C. Một plan biểu diễn loại dịch vụ, service là mỗi bản binding
D. Một service là binding, plan là từng resource đã cấp
Đáp án đúng: A

Câu 03. Vì sao `service_id` và `plan_id` trong catalog cần ổn định qua các lần phát hành?
A. Để nền tảng tự chuyển các instance sang plan mới
B. Để broker bỏ qua kiểm tra quyền khi nhận request cũ
C. Để broker xóa hết binding mỗi khi catalog được nạp
D. Giữ ID ổn định để platform nhận diện instance cũ
Đáp án đúng: D

Câu 04. Một service đặt thuộc tính `bindable=true`; ý nghĩa chính là gì?
A. `bindable` cho phép tạo binding đến service instance
B. Service hỗ trợ truy vấn trạng thái operation đã hoàn thành
C. Service hỗ trợ nhận custom parameters khi provisioning
D. Service hỗ trợ đổi plan của instance đang được cấp phát
Đáp án đúng: A

Câu 05. Trong catalog, thuộc tính `plan_updateable` của service cho biết điều gì?
A. Broker hỗ trợ phân trang danh sách plan theo tên service
B. Broker hỗ trợ yêu cầu chuyển service instance sang plan khác
C. Broker hỗ trợ tạo credential mới mỗi lần đọc catalog
D. Broker hỗ trợ mở kết nối tới instance qua service binding
Đáp án đúng: B

Câu 06. Header `X-Broker-API-Version` từ platform giúp broker biết thông tin nào?
A. Phiên bản ứng dụng backend vừa được broker cấp phát
B. Phiên bản service plan được chọn trong mỗi binding
C. Phiên bản credential sẽ được trả về ở endpoint binding
D. Phiên bản giao thức OSB API mà platform đang sử dụng
Đáp án đúng: D

Câu 07. Biện pháp nào phù hợp khi platform gọi broker API qua mạng?
A. Xác thực client của platform và dùng TLS bảo vệ kết nối
B. Chỉ kiểm nguồn IP mà không kiểm danh tính platform gọi
C. Lưu mật khẩu platform vào response body của catalog
D. Chỉ dùng service ID để xác thực yêu cầu provision mới
Đáp án đúng: A

Câu 08. Để Cloud Foundry có thể dùng một broker mới, bước tích hợp nào cần có?
A. Thay service catalog thành file deployment ở ứng dụng
B. Đăng ký tên database backend dưới dạng service instance
C. Gắn URL của broker vào service binding từng ứng dụng
D. Đăng ký URL broker và thông tin xác thực với platform
Đáp án đúng: D

Câu 09. Service instance ID gửi tới broker trong yêu cầu provision thường có đặc điểm nào?
A. Do broker sinh lại sau mỗi lần platform gửi retry
B. Do kế hoạch billing tạo mới trong mỗi lần update
C. Do platform cung cấp và giữ ổn định qua các lần retry
D. Do credential của binding quyết định khi user kết nối
Đáp án đúng: C

Câu 10. Request OSB API nào dùng để cấp phát một service instance có ID `inst-7`?
A. `PATCH /v2/service_instances/inst-7` yêu cầu provision
B. `GET /v2/service_instances/inst-7` yêu cầu provision
C. `POST /v2/service_instances/inst-7` yêu cầu provision
D. `PUT /v2/service_instances/inst-7` khởi tạo instance
Đáp án đúng: D

Câu 11. Trong body yêu cầu provision, cặp trường nào xác định dịch vụ và gói muốn dùng?
A. `dashboard_url` và `credentials` chỉ định service cùng plan
B. `service_id` và `plan_id` chỉ định service cùng plan
C. `binding_id` và `instance_id` chỉ định service cùng plan
D. `operation` và `state` chỉ định service cùng plan
Đáp án đúng: B

Câu 12. Nếu broker tạo instance thành công ngay theo OSB API, mã HTTP nào thường phù hợp?
A. `202 Accepted` cho instance đã tạo đồng bộ thành công
B. `204 No Content` cho instance đã tạo đồng bộ thành công
C. `410 Gone` cho instance đã tạo đồng bộ thành công
D. `201 Created` cho instance được tạo đồng bộ thành công
Đáp án đúng: D

Câu 13. Khi provision chưa hoàn tất và broker xử lý bất đồng bộ, response nào phù hợp?
A. `202 Accepted` báo operation còn đang được xử lý
B. `204 No Content` báo operation còn đang được xử lý
C. `409 Conflict` báo operation còn đang được xử lý
D. `201 Created` báo operation còn đang được xử lý
Đáp án đúng: A

Câu 14. Khi platform cho phép xử lý provision bất đồng bộ, tham số nào thường được gửi?
A. `accepts_incomplete=true` cho biết client chấp nhận async
B. `instance_retrievable=true` cho biết client chấp nhận async
C. `plan_updateable=true` cho biết client chấp nhận async
D. `binding_id=true` cho biết client chấp nhận async
Đáp án đúng: A

Câu 15. Nếu broker chỉ provision bất đồng bộ nhưng platform không cho phép, phản hồi nào biểu thị yêu cầu async?
A. Trả `201` với lỗi `AsyncRequired` theo giao thức broker
B. Trả `422` với lỗi `AsyncRequired` theo giao thức broker
C. Trả `204` với lỗi `AsyncRequired` theo giao thức broker
D. Trả `410` với lỗi `AsyncRequired` theo giao thức broker
Đáp án đúng: B

Câu 16. Khi provision trả 202, endpoint nào giúp platform hỏi tiến độ instance?
A. `PATCH /v2/service_instances/{id}/last_operation`
B. `GET /v2/service_instances/{id}/last_operation`
C. `POST /v2/service_instances/{id}/last_operation`
D. `GET /v2/service_instances/{id}/service_bindings`
Đáp án đúng: B

Câu 17. Giá trị `operation` trả cùng tiến trình async có mục đích chính nào?
A. Làm service ID mới để thay thế danh mục catalog hiện tại
B. Làm plan ID mới áp dụng cho lần gọi provision tiếp theo
C. Token đối chiếu operation khi platform hỏi lại tiến độ
D. Làm binding credential cho client gọi backend dịch vụ
Đáp án đúng: C

Câu 18. Trạng thái nào thuộc phản hồi `last_operation` của OSB API?
A. `created`, `deleted` hoặc `bound` diễn tả tiến độ
B. `in progress`, `succeeded`, `failed` cho tiến độ
C. `new`, `running` hoặc `stopped` diễn tả tiến độ
D. `queued`, `accepted` hoặc `timeout` diễn tả tiến độ
Đáp án đúng: B

Câu 19. Platform retry cùng lệnh provision vì timeout mạng; broker nên xử lý thế nào?
A. Tạo credential binding mới dù không có thao tác bind
B. Chuyển method PUT thành POST sau lần retry đầu tiên
C. Tạo instance ID mới để tách hai lần gọi provision ra
D. So ID instance với dữ liệu cũ, tránh cấp phát trùng
Đáp án đúng: D

Câu 20. Nếu ID instance đã gắn với service/plan khác, broker nên tránh điều gì?
A. Không âm thầm ghi đè tài nguyên cũ bằng yêu cầu mới
B. Chỉ thay service catalog để hợp thức hóa instance cũ
C. Ghi đè instance ngay rồi trả status provisioning thành công
D. Tự đổi ID của instance đang tồn tại để dùng lại ID cũ
Đáp án đúng: A

Câu 21. Request OSB API nào dùng để cập nhật một instance đang tồn tại?
A. `PUT /v2/service_instances/{id}` gửi yêu cầu update
B. `PATCH /v2/service_instances/{id}` gửi yêu cầu update
C. `DELETE /v2/service_instances/{id}` gửi yêu cầu update
D. `GET /v2/service_instances/{id}` gửi yêu cầu update
Đáp án đúng: B

Câu 22. Khi broker hỗ trợ chuyển instance sang plan khác, request update thường truyền gì?
A. `binding_id` mới để tạo plan cho instance đang chạy
B. `operation` mới thay cho giá trị plan đã chọn trước
C. `plan_id` đích trong body của yêu cầu PATCH instance
D. `service_id` mới thay toàn bộ định danh của instance
Đáp án đúng: C

Câu 23. Một operation update đang xử lý nền có lỗi; broker cần bảo đảm điều gì?
A. Kết quả update tự đổi thành provision instance mới
B. Plan mới được coi thành công trước khi backend cập nhật
C. Token operation được dùng thay credential của binding
D. Báo trạng thái failed khi platform hỏi last_operation
Đáp án đúng: D

Câu 24. Request OSB API nào dùng để thu hồi service instance ID `inst-7`?
A. `PATCH /v2/service_instances/inst-7` yêu cầu deprovision
B. `PUT /v2/service_instances/inst-7` yêu cầu deprovision
C. `GET /v2/service_instances/inst-7` yêu cầu deprovision
D. `DELETE /v2/service_instances/inst-7` để deprovision
Đáp án đúng: D

Câu 25. Trong request deprovision, query nào giúp broker đối chiếu instance được thu hồi?
A. `service_id` và `plan_id` của instance cần được xóa
B. `operation` và `dashboard_url` của instance cần được xóa
C. `catalog` và `state` của instance cần được xóa
D. `binding_id` và `credentials` của instance cần được xóa
Đáp án đúng: A

Câu 26. Đường dẫn và method nào tạo một service binding với ID `bind-3`?
A. `GET /v2/service_instances/{id}/service_bindings/bind-3`
B. `PUT /v2/service_instances/{id}/service_bindings/bind-3`
C. `PATCH /v2/service_instances/{id}/service_bindings/bind-3`
D. `POST /v2/service_instances/{id}/service_bindings/bind-3`
Đáp án đúng: B

Câu 27. Binding response thường cung cấp dữ liệu nào cho ứng dụng dùng dịch vụ?
A. Danh sách các service plan của broker hiện tại
B. Thông tin JWT để platform xác thực lại broker client
C. Connection info hoặc credentials để kết nối tài nguyên
D. Toàn bộ trạng thái operation của các instance khác
Đáp án đúng: C

Câu 28. Điểm phân biệt giữa provision và bind trong mô hình OSB là gì?
A. Provision tạo instance; bind cấp quyền truy cập instance
B. Provision chỉ hỏi trạng thái; bind xóa instance và plan
C. Provision đổi plan; bind xác thực broker với platform
D. Provision cấp credential; bind đăng ký service trong catalog
Đáp án đúng: A

Câu 29. Platform gửi lại cùng request binding ID do timeout; broker nên làm gì?
A. Đổi service plan để mỗi binding tương ứng plan mới
B. Giữ tính idempotent để không tạo credential lặp vô ích
C. Tạo thêm binding mới với ID phụ trong mỗi lần retry
D. Tạo lại service instance trước khi so khớp binding ID
Đáp án đúng: B

Câu 30. Request nào xóa một service binding mà vẫn phân biệt với xóa instance?
A. `DELETE /v2/service_instances/{id}` xóa binding cụ thể
B. `PATCH /v2/service_instances/{id}` xóa binding cụ thể
C. `DELETE /v2/service_instances/{id}/service_bindings/{bid}`
D. `GET /v2/service_instances/{id}/last_operation` xóa binding
Đáp án đúng: C

Câu 31. Nếu service plan không hỗ trợ binding, broker nên phản ứng thế nào với yêu cầu bind?
A. Tự chuyển service sang plan mới hỗ trợ binding
B. Chấp nhận bind rồi bỏ qua bước tạo quyền tài nguyên
C. Từ chối bind phù hợp thay vì trả credential giả
D. Trả credential của instance khác có plan tương ứng
Đáp án đúng: C

Câu 32. Trong request bind, `bind_resource` có thể giúp broker nhận dạng gì?
A. Credential được trả về trong binding response cũ
B. Ứng dụng hoặc route cần kết nối với service instance
C. Phiên bản protocol OSB API đang dùng cho catalog
D. Trạng thái hoàn tất của thao tác provision trước
Đáp án đúng: B

Câu 33. Khi broker trả credentials chứa secret, cách xử lý nào phù hợp?
A. Đưa secret vào audit log để hỗ trợ điều tra binding
B. Đặt secret vào public catalog để consumer tìm lại
C. Gắn secret vào operation ID để tiện debug lần retry
D. Giới hạn truy cập secret và tránh ghi plaintext ra log
Đáp án đúng: D

Câu 34. `parameters` tùy chọn trong yêu cầu provision nên được broker xử lý thế nào?
A. Thay các tham số bằng credentials của binding cũ
B. Validate theo schema và policy của service/plan
C. Giữ parameters trong catalog thay vì ở instance
D. Áp dụng nguyên vẹn mà không kiểm giá trị đầu vào
Đáp án đúng: B

Câu 35. Trường `context` từ platform có ích gì khi cấp phát nhiều tenant?
A. Làm token trả từ last_operation sau lượt provision
B. Thay thế bước xác thực API của platform khi gọi broker
C. Đưa org/space để phân vùng tenant của instance
D. Đảm bảo service plan được phép dùng mà không cần quyền
Đáp án đúng: C

Câu 36. Để operation bất đồng bộ sống sót sau broker restart, thiết kế state nào phù hợp?
A. Lưu trạng thái và operation ID bền vững trước khi báo nhận
B. Chỉ lưu offset xử lý vào biến static trong broker process
C. Đánh dấu succeeded trước rồi để worker tự tạo resource
D. Chỉ đếm request trong memory mà không lưu instance ID
Đáp án đúng: A

Câu 37. Khi client yêu cầu thu hồi instance của tenant khác, broker cần bảo vệ gì?
A. Đổi quyền truy cập thành giá trị từ request parameters
B. Chỉ xét tên service trong catalog để quyết định xóa
C. Đối chiếu quyền và sở hữu instance trước khi thu hồi
D. Tin vào instance ID mà bỏ qua quyền của bên gọi
Đáp án đúng: C

Câu 38. Khi vận hành broker, nhóm telemetry nào hữu ích cho điều tra lỗi provisioning?
A. Chỉ số độ dài client secret đang được lưu trong memory
B. Chỉ số kích thước service catalog qua các bản deploy
C. Chỉ tên resource group trong hệ thống build artifact
D. Thời gian, lỗi, operation ID và trạng thái instance
Đáp án đúng: D

Câu 39. Khi service broker đăng ký với Cloud Foundry, service catalog có vai trò gì?
A. Để nền tảng hiển thị dịch vụ/plan cho người dùng chọn
B. Để nền tảng truy vấn trực tiếp database của từng dịch vụ
C. Để mỗi application tự định nghĩa plan trong runtime
D. Để từng binding trả lại danh mục service thay vì secret
Đáp án đúng: A

Câu 40. Kubernetes muốn dùng broker theo OSB API; cách tích hợp nào phù hợp?
A. Pod gọi trực tiếp database và bỏ giao thức broker HTTP
B. Ingress tự tạo service binding từ mỗi request bên ngoài
C. Client/controller tích hợp gọi OSB API tới broker
D. Kubernetes tự gọi OSB endpoints khi tạo Pod không cấu hình
Đáp án đúng: C
