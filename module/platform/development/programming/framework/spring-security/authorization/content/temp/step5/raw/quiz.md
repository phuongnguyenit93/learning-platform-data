Câu 1. Trong Spring Security, phân quyền (authorization) cần trả lời câu hỏi nào sau khi xác thực?
A. Password của principal có cần băm lại trước khi lưu.
B. Credential của principal có hợp lệ để đăng nhập hệ thống.
C. Quyền thực hiện thao tác với tài nguyên của principal.
D. Session của principal được tạo bằng cookie hay bearer token.
Đáp án đúng: C

Câu 2. Với `SimpleGrantedAuthority("invoice:read")`, phương thức `getAuthority()` trả về gì?
A. Đối tượng `Authentication` đang giữ principal hiện tại.
B. Chuỗi `invoice:read` để chính sách phân quyền so khớp.
C. Chuỗi `ROLE_invoice:read` do SimpleGrantedAuthority thêm.
D. Giá trị `true` nếu invoice đã được principal sở hữu.
Đáp án đúng: B

Câu 3. Khi chưa tùy biến role prefix, `hasRole("ADMIN")` thường kiểm tra authority nào?
A. `SCOPE_ADMIN` được cấp qua OAuth2 access token.
B. Kiểm tra `ROLE_ADMIN` trong danh sách GrantedAuthority.
C. `PERMISSION_ADMIN` được lưu trong database ACL.
D. `ADMIN` được gắn mà không có tiền tố role nào.
Đáp án đúng: B

Câu 4. Principal có `SimpleGrantedAuthority("report:export")`; biểu thức nào so khớp trực tiếp?
A. `hasAuthority('ROLE_report:export')` kiểm tra quyền đó.
B. `hasRole('SCOPE_report:export')` so khớp authority đã cấp.
C. `hasRole('report:export')` so khớp authority không tiền tố.
D. Dùng `hasAuthority('report:export')` so khớp chính xác.
Đáp án đúng: D

Câu 5. Khi đã cấu hình role hierarchy `ROLE_ADMIN > ROLE_USER`, người có `ROLE_ADMIN` sẽ ra sao?
A. Có thể thỏa kiểm tra yêu cầu `ROLE_USER` qua hierarchy.
B. Được cấp permission ACL cho toàn bộ object của ứng dụng.
C. Tự được xác thực lại bằng provider dành cho `ROLE_USER`.
D. Chỉ thỏa kiểm tra `ROLE_USER` khi thêm authority trực tiếp.
Đáp án đúng: A

Câu 6. Trong Spring Security hiện đại, `AuthorizationManager` chủ yếu đảm nhiệm việc gì?
A. Tạo password hash và phát sinh credential của principal.
B. Đăng ký servlet filter để tự xử lý từng HTTP response.
C. Đánh giá quyền truy cập dựa vào Authentication và ngữ cảnh.
D. Tạo access token mới cho tất cả request có authority.
Đáp án đúng: C

Câu 7. Muốn cấu hình quy tắc phân quyền theo HTTP route trong Spring Security 6, dùng cấu hình nào?
A. `http.authorizeRequests(...)` trên `UserDetailsService`.
B. `http.securityContext(...)` trên `PasswordEncoder`.
C. Dùng `http.authorizeHttpRequests(...)` trong cấu hình HTTP.
D. `http.authorizeMethods(...)` trên `AuthenticationProvider`.
Đáp án đúng: C

Câu 8. Hai `requestMatchers` cùng khớp một URL nhưng chính sách khác nhau; quy tắc nào thường được áp dụng?
A. Tất cả matcher đều phải đồng ý thì request mới được qua.
B. Quy tắc matcher có role cao nhất được ưu tiên ở cuối.
C. Quy tắc matcher có biểu thức dài nhất được ưu tiên dùng.
D. Matcher đầu tiên khớp request sẽ quyết định chính sách.
Đáp án đúng: D

Câu 9. Muốn giới hạn `POST /api/orders` cho quyền tạo, nhưng cho phép `GET` với quyền đọc, nên làm gì?
A. Chỉ kiểm tra `@RequestBody` có chứa field permission tạo.
B. Dùng matcher tách `HttpMethod.POST` và `HttpMethod.GET`.
C. Đặt cùng matcher theo URL rồi kiểm tra duy nhất role đọc.
D. Đăng ký `GET` trong authentication và `POST` trong session.
Đáp án đúng: B

Câu 10. Tại cuối cấu hình `authorizeHttpRequests`, câu lệnh nào hỗ trợ nguyên tắc mặc định từ chối?
A. Dùng `.anyRequest().denyAll()` sau các matcher cụ thể.
B. Dùng `.anyRequest().permitAll()` sau matcher cụ thể.
C. Dùng `.requestMatchers("/**").anonymous()` để chặn truy cập.
D. Dùng `.anyRequest().authenticated()` để cấm quyền chưa biết.
Đáp án đúng: A

Câu 11. Một endpoint public dùng `.permitAll()` có nghĩa chính xác gì?
A. Cho phép qua authorization dù người dùng chưa đăng nhập.
B. Method security phía sau endpoint cũng bị tắt theo matcher.
C. SecurityFilterChain được bỏ qua nên CSRF và filter không chạy.
D. Chỉ tài khoản có quyền `ANONYMOUS` mới được truy cập endpoint.
Đáp án đúng: A

Câu 12. Khác biệt chính giữa `.authenticated()` và `.hasAuthority("orders:read")` là gì?
A. authenticated kiểm ACL từng Order còn hasAuthority chỉ kiểm URL.
B. authenticated yêu cầu đăng nhập; hasAuthority còn kiểm quyền.
C. hasAuthority yêu cầu đăng nhập nhưng bỏ qua authority cụ thể.
D. authenticated tự kiểm tra quyền `orders:read` của principal.
Đáp án đúng: B

Câu 13. Chính sách HTTP cần so khớp tenant từ URL với claim đáng tin cậy trong Authentication; nên dùng gì?
A. Dùng `PasswordEncoder` để so sánh tenant trong request path.
B. Dùng `GrantedAuthorityDefaults` để tự xác thực URL tenant.
C. Viết `AuthorizationManager` dùng auth và request context.
D. Chỉ định `requestMatchers` để so khớp mọi claim tại compile time.
Đáp án đúng: C

Câu 14. Một người dùng đã xác thực nhưng không có authority mà endpoint yêu cầu; HTTP status thường là gì?
A. 409 Conflict do quyền thiếu được hiểu là xung đột dữ liệu.
B. 401 Unauthorized ngay cả khi Authentication vẫn hợp lệ.
C. 404 Not Found do Spring tự giấu mọi endpoint bị từ chối.
D. 403 Forbidden khi policy từ chối người dùng đã xác thực.
Đáp án đúng: D

Câu 15. API dùng HTTP Basic, request chưa đăng nhập truy cập resource được bảo vệ; kết quả thường gặp?
A. Trả 401 với challenge từ entry point của HTTP Basic.
B. 403 do controller tự báo dù thiếu Authentication.
C. 200 nếu request không kèm `Authorization` header.
D. 302 sang trang login dù API chỉ có Basic authentication.
Đáp án đúng: A

Câu 16. Để bật annotation bảo vệ method bằng `@PreAuthorize`, cấu hình nào phù hợp?
A. Đặt `@EnableMethodSecurity` trong cấu hình security.
B. Đặt `@EnableTransactionManagement` trên service.
C. Đặt `@EnableWebSecurity` rồi bỏ qua method security.
D. Đặt `@EnableCaching` để Spring áp annotation phân quyền.
Đáp án đúng: A

Câu 17. Khi method gắn `@PreAuthorize("hasAuthority('invoice:write')")`, phép kiểm được thực hiện khi nào?
A. Chỉ khi request đi qua HTTP filter có cùng biểu thức.
B. Trước khi method chạy qua proxy của method security.
C. Sau khi method trả kết quả và transaction đã commit.
D. Trong lúc serialize kết quả method thành JSON response.
Đáp án đúng: B

Câu 18. Muốn kiểm quyền đọc order dựa vào cả principal và tham số `orderId`, biểu thức nào phù hợp?
A. `@PreAuthorize("@orderGuard.canRead(authentication, #orderId)")`.
B. `@PostFilter("@orderGuard.canRead(authentication, #orderId)")`.
C. `@Secured("@orderGuard.canRead(authentication, #orderId)")`.
D. `@RolesAllowed("@orderGuard.canRead(authentication, #orderId)")`.
Đáp án đúng: A

Câu 19. Muốn kiểm tra owner của đối tượng trả về sau khi service chạy, annotation nào phù hợp?
A. `@PreAuthorize` với điều kiện dựa trên `returnObject`.
B. `@Secured` với biểu thức so sánh `returnObject.owner`.
C. `@PreFilter` để đọc kết quả service bằng `returnObject`.
D. `@PostAuthorize` với điều kiện dựa trên `returnObject`.
Đáp án đúng: D

Câu 20. Với method nhận danh sách Order, `@PreFilter` giúp thực hiện điều gì?
A. Chuyển thông tin SecurityContext thành field của từng Order.
B. Kiểm tra kết quả trả về rồi loại Order không đủ quyền đọc.
C. Chuyển từng tham số thành entity mới trước khi chạy method.
D. Lọc phần tử collection đầu vào trước khi chạy method.
Đáp án đúng: D

Câu 21. Khi service trả collection lớn, điểm cần cân nhắc nếu dùng `@PostFilter` là gì?
A. Lọc sau khi method tạo collection nên tốn thêm chi phí.
B. PostFilter đổi SQL query để DB chỉ load object có quyền.
C. PostFilter ngăn method chạy với principal thiếu quyền trước.
D. PostFilter tự thêm tenant predicate vào repository query.
Đáp án đúng: A

Câu 22. Khi đã bật hỗ trợ annotation tương ứng, `@Secured("ROLE_MANAGER")` kiểm tra điều gì?
A. Kiểm tra authority `ROLE_MANAGER` của Authentication.
B. Request có header `ROLE_MANAGER` do client tự gửi.
C. JWT có claim `scope=ROLE_MANAGER` dù không map authority.
D. Principal có quyền ACL `MANAGER` trên object trả về.
Đáp án đúng: A

Câu 23. Một method có `@PreAuthorize` gọi method khác cũng có `@PreAuthorize` trong cùng bean qua `this`; rủi ro gì?
A. Spring tự sinh HTTP request nội bộ để kích hoạt filter mới.
B. Proxy áp quyền cả khi gọi method qua `this`.
C. Method được gọi sẽ thực thi sau transaction của method đầu.
D. Lời gọi qua `this` có thể bỏ qua advice của proxy.
Đáp án đúng: D

Câu 24. `GET /orders/{id}` chỉ kiểm tra `hasRole('USER')`; nguy cơ bảo mật chính nào còn tồn tại?
A. Authentication tự chuyển sang anonymous khi ID thay đổi.
B. URL được Spring mã hóa thành principal mới cho mỗi ID.
C. Role của user bị xóa sau khi truy cập resource đầu tiên.
D. IDOR: user có thể yêu cầu ID thuộc chủ sở hữu khác.
Đáp án đúng: D

Câu 25. Trong hệ thống đa tenant, nguồn nào thích hợp nhất để quyết định tenant hiện tại khi phân quyền?
A. Giá trị tenant mặc định lấy từ form người dùng gửi lên.
B. Query parameter `tenantId` mà client tự sửa trong request.
C. Tenant claim đã được xác minh và gắn vào Authentication.
D. Header `X-Tenant-Id` không xác thực từ client bên ngoài.
Đáp án đúng: C

Câu 26. API list invoices theo tenant cần ngăn dữ liệu tenant khác bị trả về; hướng nào phù hợp?
A. Đổi tên JSON field `tenantId` để client khó phát hiện.
B. Chỉ kiểm tra user đã đăng nhập trước khi gọi `findAll()`.
C. Ẩn invoice tenant khác ở giao diện sau khi tải.
D. Thêm tenant predicate vào query từ tenant đã xác thực.
Đáp án đúng: D

Câu 27. Một policy cho phép đọc Order khi người dùng là owner hoặc nhân viên hỗ trợ cùng tenant; nên thực thi ở đâu?
A. Trong client localStorage để lưu owner và tenant so sánh.
B. Kiểm tra owner, role và tenant tại service/domain layer.
C. Ẩn nút xem Order trên giao diện của người dùng.
D. Ở HTTP matcher chỉ theo role, không kiểm Order được yêu cầu.
Đáp án đúng: B

Câu 28. Trong Spring Security ACL, `ObjectIdentity` dùng để biểu diễn điều gì?
A. Định danh security filter chain đang xử lý một request.
B. Principal cùng danh sách authority hiện tại.
C. Kiểu domain cùng ID của object được ACL bảo vệ.
D. Định danh HTTP session mà user đang sử dụng để truy cập.
Đáp án đúng: C

Câu 29. Trong ACL, `Sid` được dùng để đại diện cho đối tượng nào?
A. Object được ACL bảo vệ theo `ObjectIdentity`.
B. Principal hoặc authority là chủ thể được cấp quyền.
C. Điểm truy cập HTTP sẽ ánh xạ thành một method security.
D. Thứ tự lần truy cập được ghi trong bảng audit event.
Đáp án đúng: B

Câu 30. Một `AccessControlEntry` (ACE) trong ACL thường chứa thông tin gì?
A. Danh sách các bean `AuthenticationManager` đang chạy.
B. SID, permission và trạng thái allow/deny cho object.
C. Mapping từ controller URL sang repository query SQL.
D. Password hash và thời hạn session của principal.
Đáp án đúng: B

Câu 31. Muốn method security kiểm tra permission `READ` trên Order theo ID và kiểu đối tượng, cơ chế nào phù hợp?
A. Dùng `hasAuthority(#id, 'Order', 'READ')` với authority.
B. Dùng `isAuthenticated(#id, 'Order', 'READ')` với auth.
C. Dùng `hasPermission(#id, 'Order', 'READ')` với evaluator.
D. Dùng `hasRole(#id, 'Order', 'READ')` với hierarchy.
Đáp án đúng: C

Câu 32. Khi test HTTP và method authorization, bộ trường hợp nào bảo vệ tốt khỏi hồi quy phân quyền?
A. Test controller trả JSON đúng định dạng mà không kiểm status.
B. Test đăng nhập thành công rồi suy ra mọi object được bảo vệ.
C. Test quyền hợp lệ, thiếu quyền và truy cập khác tenant.
D. Test role ADMIN hợp lệ rồi bỏ qua các principal khác.
Đáp án đúng: C
