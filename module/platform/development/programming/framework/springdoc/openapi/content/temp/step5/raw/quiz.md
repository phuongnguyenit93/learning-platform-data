Câu 1. springdoc-openapi chủ yếu hỗ trợ tác vụ nào trong ứng dụng Spring Boot?
A. Phát hành token đăng nhập cho endpoint có khai báo bảo mật.
B. Sinh đặc tả OpenAPI từ mapping và metadata của Spring.
C. Thực thi kiểm tra mọi request theo JSON Schema trước controller.
D. Sinh client runtime rồi thay controller hiện tại của ứng dụng.
Đáp án đúng: B

Câu 2. Với Spring Boot 3 dùng Spring MVC và cần Swagger UI, dependency nào phù hợp?
A. Dùng `springdoc-openapi-starter-webflux-ui` với Spring MVC.
B. Dùng `springdoc-openapi-starter-webmvc-api` để có giao diện UI.
C. Dùng `springdoc-openapi-starter-webmvc-ui` với Spring MVC.
D. Dùng `springdoc-openapi-ui` cũ làm starter UI của phiên bản 2.x.
Đáp án đúng: C

Câu 3. Với Spring Boot 3 dùng WebFlux và muốn Swagger UI, starter nào phù hợp?
A. Dùng `springdoc-openapi-starter-webmvc-ui` cho WebFlux.
B. Dùng `springdoc-openapi-starter-webmvc-api` kèm giao diện UI.
C. Dùng `springdoc-openapi-starter-webflux-api` kèm giao diện UI.
D. Dùng `springdoc-openapi-starter-webflux-ui` cho WebFlux.
Đáp án đúng: D

Câu 4. Theo cấu hình mặc định, endpoint nào trả đặc tả OpenAPI dạng JSON?
A. `GET /actuator/openapi` trả đặc tả JSON theo mặc định.
B. `GET /v3/api-docs` trả tài liệu OpenAPI của ứng dụng.
C. `GET /v3/api-docs.yaml` trả đặc tả JSON theo mặc định.
D. `GET /swagger-ui.html` trả đặc tả JSON có cấu trúc.
Đáp án đúng: B

Câu 5. Muốn tải đặc tả OpenAPI dạng YAML ở cấu hình springdoc thông thường, gọi đâu?
A. `GET /v3/api-docs.yaml` để nhận đặc tả ở định dạng YAML.
B. `GET /swagger-ui.yaml` để tải YAML của endpoint đang chọn.
C. `GET /openapi.yml` từ controller mà springdoc tự đăng ký.
D. `GET /v3/api-docs.json` để nhận đặc tả định dạng YAML.
Đáp án đúng: A

Câu 6. Trong cấu hình thông thường, đường dẫn nào truy cập giao diện Swagger UI?
A. Truy cập `/actuator/health` để mở giao diện khám phá API.
B. Truy cập `/oauth2/authorize` để mở giao diện Swagger UI.
C. Truy cập `/swagger-ui.html` để mở giao diện khám phá API.
D. Truy cập `/v3/api-docs` để mở giao diện khám phá API.
Đáp án đúng: C

Câu 7. Muốn thêm summary và description cho một handler method, annotation nào phù hợp?
A. `@Schema` mô tả summary và description của HTTP route.
B. `@Parameter` mô tả toàn bộ response của operation.
C. `@Operation` mô tả nghiệp vụ của operation tương ứng.
D. `@Tag` thay thế summary của từng HTTP handler method.
Đáp án đúng: C

Câu 8. Muốn mô tả nhiều HTTP response 200, 400, 404 cho một operation, nên dùng gì?
A. `@Schema` gắn trên controller thay toàn bộ response codes.
B. `@Parameters` chứa các `@Parameter` ứng với status code.
C. `@Tag` liệt kê response status cho tất cả handler.
D. `@ApiResponses` chứa các `@ApiResponse` tương ứng.
Đáp án đúng: D

Câu 9. Muốn giải thích thuộc tính `price` trong DTO schema, annotation nào phù hợp?
A. `@Tag(description=...)` ghi chú kiểu dữ liệu của property.
B. `@ApiResponse(description=...)` gắn lên property của DTO.
C. `@Schema(description=...)` đặt trên field hoặc property.
D. `@Operation(description=...)` đặt trực tiếp lên field DTO.
Đáp án đúng: C

Câu 10. Muốn mô tả ý nghĩa một query parameter `page`, annotation nào phù hợp?
A. `@SecurityRequirement(name=...)` bổ sung metadata tham số.
B. `@Parameter(description=...)` bổ sung metadata tham số.
C. `@ApiResponse(name=...)` bổ sung metadata query parameter.
D. `@Schema(responseCode=...)` bổ sung metadata tham số.
Đáp án đúng: B

Câu 11. Hai annotation cùng tên `@RequestBody` của Spring MVC và OpenAPI khác nhau ở đâu?
A. Spring MVC mô tả response; annotation OpenAPI gọi validator.
B. Spring MVC quản lý security; annotation OpenAPI chọn converter.
C. Spring MVC bind body; annotation OpenAPI mô tả request body.
D. Spring MVC tạo schema; annotation OpenAPI bind body vào DTO.
Đáp án đúng: C

Câu 12. Muốn mô tả JSON response HTTP 201 trả về `OrderDto`, cấu trúc nào phù hợp?
A. `@Parameter` 201 với `@Content` chứa `@Schema` của DTO.
B. `@SecurityRequirement` 201 với `@Content` của DTO.
C. `@Tag` 201 với `@Content` chứa `@Schema` của DTO.
D. `@ApiResponse` 201 với `@Content` chứa `@Schema` của DTO.
Đáp án đúng: D

Câu 13. Muốn khai báo ví dụ payload cho một media type trong tài liệu OpenAPI, dùng gì?
A. `@Parameter` trong `components.securitySchemes` của spec.
B. `@ExampleObject` trong phần `examples` của `@Content`.
C. `@Operation` trong danh sách `parameters` của `@Info`.
D. `@Schema` trong phần `responses` của `@Tag` annotation.
Đáp án đúng: B

Câu 14. Muốn nhóm các operations theo chủ đề nghiệp vụ hiển thị trong Swagger UI, dùng gì?
A. `@ApiResponse(name="Orders")` để nhóm các operation.
B. `@Tag(name="Orders")` để gắn nhãn nhóm operation.
C. `@OpenAPIDefinition(group="Orders")` để tạo tag.
D. `@Schema(name="Orders")` để nhóm các HTTP handler.
Đáp án đúng: B

Câu 15. Một endpoint nội bộ không nên xuất hiện trong đặc tả công khai; annotation nào giúp ẩn khỏi springdoc?
A. Gắn `@Hidden` lên handler để bỏ operation khỏi tài liệu.
B. Gắn `@ResponseStatus` lên handler để ẩn khỏi tài liệu.
C. Gắn `@Deprecated` lên handler để bỏ operation khỏi tài liệu.
D. Gắn `@Validated` lên handler để ẩn khỏi tài liệu.
Đáp án đúng: A

Câu 16. Endpoint thực tế trả 404 khi ID không tồn tại; nên tài liệu hóa trạng thái này thế nào?
A. Dùng `@ApiResponse(responseCode="404")` cho operation.
B. Dùng `@Schema(responseCode="404")` cho operation.
C. Dùng `@Parameter(responseCode="404")` cho operation.
D. Dùng `@Tag(responseCode="404")` cho operation.
Đáp án đúng: A

Câu 17. DTO có constraint Bean Validation `@NotNull`; ý nghĩa khi xem schema OpenAPI là gì?
A. `@NotNull` bắt Swagger UI gửi lỗi 400 thay cho server.
B. `@NotNull` kích hoạt xác thực HTTP ngay từ schema OpenAPI.
C. `@NotNull` làm springdoc tạo constraint trong SQL database.
D. `@NotNull` có thể được phản ánh vào schema do springdoc sinh.
Đáp án đúng: D

Câu 18. Handler trả về `ResponseEntity<?>` làm schema suy luận không rõ; cần mô tả kiểu body thế nào?
A. Dùng `@Tag(implementation=OrderDto.class)` tại controller.
B. Dùng `@Schema(implementation=OrderDto.class)` trong response.
C. Dùng `@Parameter(implementation=OrderDto.class)` cho HTTP 200.
D. Dùng `@SecurityScheme(implementation=OrderDto.class)` cho body.
Đáp án đúng: B

Câu 19. API nhận Bearer JWT, cách khai báo một security scheme trong tài liệu OpenAPI là gì?
A. Dùng `@SecurityRequirement(type=HTTP, scheme="bearer")` cho JWT.
B. Dùng `@Operation(type=HTTP, scheme="bearer")` cho JWT.
C. Dùng `@Schema(type=HTTP, scheme="bearer")` cho JWT.
D. Dùng `@SecurityScheme(type=HTTP, scheme="bearer")` cho JWT.
Đáp án đúng: D

Câu 20. Đã đăng ký security scheme tên `bearerAuth`; làm sao gắn nó vào một operation?
A. Gắn `@ApiResponse(name="bearerAuth")` lên response 401.
B. Gắn `@Schema(name="bearerAuth")` lên request body DTO.
C. Gắn `@SecurityRequirement(name="bearerAuth")` lên operation.
D. Gắn `@Tag(name="bearerAuth")` lên interface repository.
Đáp án đúng: C

Câu 21. Khi tài liệu có `@SecurityRequirement`, nhận định nào đúng về bảo vệ HTTP thực tế?
A. Requirement tự chặn role thiếu quyền khi Swagger UI gọi API.
B. Requirement xác thực chữ ký bearer token trước HTTP controller.
C. Requirement tự tạo SecurityFilterChain và bật JWT decoder.
D. Requirement mô tả bảo mật; Spring Security vẫn phải thực thi.
Đáp án đúng: D

Câu 22. Muốn khai báo tên và version của API trong metadata OpenAPI, nên dùng gì?
A. Dùng `@Schema(info=@Info(title=...,version=...))`.
B. Dùng `@Tag(info=@Info(title=...,version=...))`.
C. Dùng `@ApiResponse(info=@Info(title=...,version=...))`.
D. Dùng `@OpenAPIDefinition(info=@Info(title=...,version=...))`.
Đáp án đúng: D

Câu 23. Muốn tùy biến OpenAPI bằng Java config thay vì annotation ở controller, giải pháp nào phù hợp?
A. Khai báo bean `OpenAPI` để cấu hình metadata và servers.
B. Khai báo bean `PasswordEncoder` để thêm servers vào spec.
C. Khai báo bean `HttpMessageConverter` để thay tài liệu paths.
D. Khai báo bean `DispatcherServlet` để sửa OpenAPI Info.
Đáp án đúng: A

Câu 24. Muốn tạo tài liệu riêng cho đường dẫn `/admin/**`, nên cấu hình springdoc thế nào?
A. Dùng `@SecurityRequirement` để lọc operation theo path.
B. Dùng `GroupedOpenApi` với `pathsToMatch("/admin/**")`.
C. Dùng `OpenAPI.info(...)` với `pathsToMatch("/admin/**")`.
D. Dùng `SwaggerUiConfigProperties` để lọc controller theo path.
Đáp án đúng: B

Câu 25. Khi một group tên `admin` đã được khai báo, endpoint tài liệu JSON tương ứng thường là gì?
A. `GET /actuator/admin/api-docs` trả tài liệu JSON của group.
B. `GET /v3/api-docs?tag=admin` trả tài liệu JSON của group.
C. `GET /v3/api-docs/admin` trả tài liệu JSON của group.
D. `GET /swagger-ui/admin` trả tài liệu JSON của group.
Đáp án đúng: C

Câu 26. Trong builder `GroupedOpenApi`, bộ lọc nào dùng để chọn controller theo package?
A. `pathsToMatch(...)` chọn package Java của controller.
B. `addOpenApiMethodFilter(...)` chọn package bằng group name.
C. `packagesToScan(...)` chọn package áp dụng cho group.
D. `group(...)` chọn package theo cùng tên nhóm tài liệu.
Đáp án đúng: C

Câu 27. Muốn tắt riêng Swagger UI nhưng vẫn cung cấp OpenAPI JSON, cấu hình nào phù hợp?
A. Đặt `springdoc.swagger-ui.enabled=false` để tắt riêng UI.
B. Đặt `springdoc.api-docs.enabled=false` để tắt riêng UI.
C. Đặt `springdoc.packages-to-scan=false` để tắt riêng UI.
D. Đặt `springdoc.swagger-ui.path=false` để tắt riêng UI.
Đáp án đúng: A

Câu 28. Muốn đổi đường dẫn phục vụ tài liệu OpenAPI JSON mặc định, cấu hình nào phù hợp?
A. Đổi thuộc tính `springdoc.api-docs.version` trong cấu hình.
B. Đổi thuộc tính `springdoc.swagger-ui.path` trong cấu hình.
C. Đổi thuộc tính `springdoc.swagger-ui.operationsSorter` trong cấu hình.
D. Đổi thuộc tính `springdoc.api-docs.path` trong cấu hình.
Đáp án đúng: D

Câu 29. Tại sao không nên xem nút Try it out của Swagger UI là bằng chứng API được bảo vệ?
A. Swagger UI gửi HTTP request; bảo vệ API phải do server đảm nhận.
B. Swagger UI thay resource server xác thực người dùng và quyền.
C. Swagger UI tạo JWT hợp lệ từ mọi security scheme đã mô tả.
D. Swagger UI xác minh quyền truy cập rồi mới gọi controller.
Đáp án đúng: A

Câu 30. Để phát hiện schema tài liệu lệch so với response runtime, kiểm thử nào hữu ích?
A. Đối chiếu response thực với schema/spec sinh từ `/v3/api-docs`.
B. Kiểm tra số annotation `@Operation` bằng số HTTP routes.
C. Kiểm tra controller compile và bỏ qua response thực tế.
D. Kiểm tra trang Swagger UI load thành công là đủ xác thực schema.
Đáp án đúng: A

Câu 31. Khi thay đổi API đã công bố, mục nào nên được xem là breaking change trong hợp đồng?
A. Thêm ví dụ minh họa response mà không đổi schema.
B. Xóa field client dùng hoặc đổi kiểu dữ liệu của response.
C. Sửa phần mô tả operation nhưng không đổi HTTP response.
D. Đổi thứ tự tag trên Swagger UI mà không thay endpoint.
Đáp án đúng: B

Câu 32. Muốn phát hành OpenAPI JSON/YAML qua CI một cách đáng tin cậy, bước nào nên thêm?
A. Xuất, validate và so diff spec qua CI trước khi phát hành.
B. Chạy Swagger UI mà không kiểm tra nội dung schema xuất ra.
C. Sao chép HTML Swagger UI thành bản tài liệu chuẩn trong CI.
D. Chỉnh spec thủ công tại production sau mỗi lần deploy.
Đáp án đúng: A
