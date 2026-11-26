Câu 1. Trong Spring Framework, `DataBinder` có vai trò chính nào khi tiếp nhận dữ liệu?
A. Tạo database transaction cho mọi lần cập nhật JavaBean.
B. Chuyển entity sang JSON rồi quyết định HTTP response status.
C. Ánh xạ property values vào đối tượng đích và ghi nhận lỗi binding.
D. Biên dịch các constraint Jakarta thành câu SQL kiểm tra.
Đáp án đúng: C

Câu 2. Đã tạo `DataBinder binder` cho một bean; thao tác nào nạp dữ liệu dạng property vào bean?
A. Gọi `binder.bind(new MutablePropertyValues(values))`.
B. Gọi `binder.validate(new MutablePropertyValues(values))`.
C. Gọi `binder.setValidator(new MutablePropertyValues(values))`.
D. Gọi `binder.getBindingResult().addAllErrors(values)`.
Đáp án đúng: A

Câu 3. Khi bind chuỗi `abc` vào property `age` kiểu `int`, nơi nào phản ánh lỗi chuyển kiểu?
A. Kiểm tra `BeanWrapper.getPropertyDescriptors()` để đọc lỗi.
B. Kiểm tra `ConversionService.canConvert()` để lấy FieldError.
C. Kiểm tra `MessageSource.getMessage()` để lấy exception SQL.
D. Kiểm tra `FieldError` trong `binder.getBindingResult()`.
Đáp án đúng: D

Câu 4. Muốn đọc và ghi property lồng nhau `address.city` theo quy tắc JavaBean, API nào phù hợp?
A. Dùng `BeanWrapper` với property path `address.city`.
B. Dùng `Validator` để cập nhật nested property vào target.
C. Dùng `BindingResult` để đổi field name thành JavaBean accessor.
D. Dùng `MessageCodesResolver` để ghi giá trị property con.
Đáp án đúng: A

Câu 5. Khi bean không có setter nhưng muốn bind trực tiếp field, `DataBinder` hỗ trợ cấu hình nào?
A. Gọi `setAutoGrowNestedPaths(false)` để bind trực tiếp field.
B. Gọi `setIgnoreUnknownFields(false)` để viết vào private field.
C. Gọi `initDirectFieldAccess()` thay cho truy cập property.
D. Gọi `setRequiredFields(...)` để không cần setter cho field.
Đáp án đúng: C

Câu 6. Form gửi thêm field `isAdmin`; để giới hạn property có thể bind, cấu hình nào thích hợp?
A. Gọi `WebDataBinder.setAllowedFields(...)` theo danh sách an toàn.
B. Gọi `WebDataBinder.setRequiredFields(...)` để chặn field lạ.
C. Gọi `WebDataBinder.setAutoGrowCollectionLimit(...)` để chặn.
D. Gọi `WebDataBinder.setIgnoreInvalidFields(true)` để cấm ghi.
Đáp án đúng: A

Câu 7. Sau khi DataBinder có danh sách allowed fields, muốn biết field nào đã bị bỏ qua, đọc ở đâu?
A. Gọi `BindingResult.getGlobalErrors()` để đọc field bị chặn.
B. Gọi `BindingResult.getSuppressedFields()` để kiểm tra.
C. Gọi `BindingResult.getErrorCount()` để lấy tên field bị chặn.
D. Gọi `BindingResult.getTarget()` để trả danh sách bị từ chối.
Đáp án đúng: B

Câu 8. Trong Spring MVC controller, cách nào tùy chỉnh `WebDataBinder` cho việc bind form?
A. Định nghĩa method `@ModelAttribute` để thay toàn bộ binder.
B. Định nghĩa method `@ResponseBody` để ghi cấu hình binder.
C. Định nghĩa method `@ExceptionHandler` để cấu hình allowed fields.
D. Định nghĩa method `@InitBinder` để đặt editor hoặc allowed fields.
Đáp án đúng: D

Câu 9. Để đổi giá trị nguồn `String` sang kiểu domain `Money`, interface nào dễ cài đặt nhất?
A. Cài đặt `Converter<String, Money>` với phương thức `convert`.
B. Cài đặt `BeanWrapper<String, Money>` với phương thức `parse`.
C. Cài đặt `Formatter<String, Money>` với phương thức `convert`.
D. Cài đặt `Validator<String, Money>` với phương thức `validate`.
Đáp án đúng: A

Câu 10. Muốn xác định liệu hệ thống chuyển được từ `String` sang `LocalDate`, API nào phù hợp?
A. Gọi `conversionService.bind(String.class, LocalDate.class)`.
B. Gọi `conversionService.supports(String.class, LocalDate.class)`.
C. Gọi `conversionService.parse(String.class, LocalDate.class)`.
D. Gọi `conversionService.canConvert(String.class, LocalDate.class)`.
Đáp án đúng: D

Câu 11. Nhiều enum cần dùng cùng cơ chế chuyển từ `String`; abstraction nào hợp lý?
A. Dùng `Converter<String, Object>` để ghi đè toàn bộ formatter.
B. Dùng `PropertyEditorRegistrar` để thực hiện group validation.
C. Dùng `MessageCodesResolver` để tạo converter mỗi enum.
D. Dùng `ConverterFactory<String, Enum>` cho nhóm kiểu đích.
Đáp án đúng: D

Câu 12. Với `Formatter<T>` của Spring, cặp phương thức nào phục vụ chuyển đổi có Locale?
A. Triển khai `bind(String)` và `getMessage(Locale)`.
B. Triển khai `convert(String)` và `supports(Class<?>)`.
C. Triển khai `parse(String, Locale)` và `print(T, Locale)`.
D. Triển khai `validate(T, Errors)` và `format(Locale)`.
Đáp án đúng: C

Câu 13. Form gửi chuỗi ngày `2026-11-26` cho field `LocalDate`; annotation nào phù hợp?
A. Dùng `@DateTimeFormat(iso = ISO.DATE)` trên field.
B. Dùng `@Temporal(TemporalType.DATE)` trên field.
C. Dùng `@NumberFormat(style = Style.NUMBER)` trên field.
D. Dùng `@Pattern(regexp = "yyyy-MM-dd")` trên field.
Đáp án đúng: A

Câu 14. Muốn bind giá tiền từ chuỗi với ký hiệu và dấu phân cách theo vùng, annotation nào hữu ích?
A. Dùng `@DateTimeFormat` phối hợp `Converter` theo ngày.
B. Dùng `@JsonFormat` để thay binding form thành JSON.
C. Dùng `@NumberFormat` phối hợp `Formatter` nhận biết Locale.
D. Dùng `@Digits` để format input theo Locale khi bind.
Đáp án đúng: C

Câu 15. Sau khi `binder.bind(...)`, muốn chạy các quy tắc kiểm tra từ Validator đã đăng ký, gọi gì?
A. Gọi `binder.close()` để mọi Validator chạy trước khi bind.
B. Gọi `binder.validate()` rồi kiểm tra `BindingResult`.
C. Gọi `binder.getTarget()` để Validator tự được kích hoạt.
D. Gọi `binder.setRequiredFields()` để chạy Jakarta Validation.
Đáp án đúng: B

Câu 16. Trong Spring `Validator`, `supports(Class<?>)` thường quyết định điều gì?
A. MessageSource nào được nạp theo Locale của request.
B. Đối tượng thuộc kiểu nào có thể được Validator xử lý.
C. Constraint nào của Jakarta được lưu thành SQL check.
D. Property nào được phép ghi khi DataBinder nhận input.
Đáp án đúng: B

Câu 17. Trong `Validator.validate(target, errors)`, khi `email` không hợp lệ, cách báo lỗi field nào đúng?
A. Gọi `errors.addAllErrors("email.invalid")` để tạo lỗi field.
B. Gọi `errors.reject("email", "email.invalid")` để tạo FieldError.
C. Gọi `errors.setFieldValue("email", "email.invalid")`.
D. Gọi `errors.rejectValue("email", "email.invalid")`.
Đáp án đúng: D

Câu 18. Một quy tắc kiểm tra đồng thời hai field và cần báo lỗi toàn object, nên dùng gì?
A. Gọi `errors.rejectValue("startDate", "date.range.invalid")` cho global error.
B. Gọi `errors.reject("date.range.invalid")` cho global error.
C. Gọi `errors.getFieldError("date.range.invalid")` để tạo lỗi.
D. Gọi `errors.pushNestedPath("date.range.invalid")` để tạo lỗi.
Đáp án đúng: B

Câu 19. Field `displayName` phải có ký tự không phải khoảng trắng; constraint nào đáp ứng?
A. Dùng `@NotNull` để từ chối cả chuỗi toàn dấu cách.
B. Dùng `@NotBlank` của Jakarta Bean Validation cho String.
C. Dùng `@Size(min = 0)` để từ chối chuỗi rỗng.
D. Dùng `@NotEmpty` để từ chối chuỗi gồm dấu cách.
Đáp án đúng: B

Câu 20. Với property String có giá trị `""`, nhận định nào đúng về constraint `@NotNull`?
A. `@NotNull` chỉ áp dụng cho Collection thay vì String.
B. `@NotNull` tự trim rồi chuyển String rỗng thành null.
C. `@NotNull` thất bại vì chuỗi không có ký tự nào.
D. `@NotNull` vẫn hợp lệ vì chuỗi rỗng không phải null.
Đáp án đúng: D

Câu 21. Để giới hạn số phần tử của `List<String>` trong khoảng 1 đến 5, nên dùng gì?
A. Đặt `@Min(1)` và `@Max(5)` lên field List.
B. Đặt `@Length(min = 1, max = 5)` lên field List.
C. Đặt `@Size(min = 1, max = 5)` lên field List.
D. Đặt `@Digits(integer = 5)` lên field List.
Đáp án đúng: C

Câu 22. Field `age` dạng số nguyên phải từ 18 trở lên; constraint nào phù hợp?
A. Đặt `@Pattern(regexp = "18+")` lên field int.
B. Đặt `@NotEmpty` lên field tuổi để kiểm tra ngưỡng.
C. Đặt `@Min(18)` lên field tuổi của request DTO.
D. Đặt `@Size(min = 18)` lên field tuổi kiểu int.
Đáp án đúng: C

Câu 23. DTO `Order` có field `shippingAddress` là bean con; cách nào kiểm tra constraint của bean con?
A. Đặt `@Valid` trên `shippingAddress` và validate Order.
B. Đặt `@NotNull` trên field để tự kiểm tra mọi property con.
C. Đặt `@ConvertGroup` lên field mà không cần `@Valid`.
D. Đặt `@Validated` trên field để bật autoGrowNestedPaths.
Đáp án đúng: A

Câu 24. Cần áp constraint dành riêng nhóm `Update` khi validate DTO, dùng cơ chế nào?
A. Dùng `@InitBinder(Update.class)` để bật validation group.
B. Dùng `@Validated(Update.class)` trong điểm gọi validation.
C. Dùng `@Valid(Update.class)` để chỉ rõ validation group.
D. Dùng `@GroupSequence(Update.class)` thay thế method call.
Đáp án đúng: B

Câu 25. Cần kiểm tra `startDate <= endDate` trên cùng một DTO; cách mở rộng Jakarta Validation nào hợp lý?
A. Đặt `@Pattern` trên field date để so sánh bean cha.
B. Đặt `@NotNull` lên cả hai ngày để kiểm tra thứ tự.
C. Tạo class-level constraint cùng `ConstraintValidator` so hai field.
D. Đặt `@Min` trên startDate để đọc endDate ở runtime.
Đáp án đúng: C

Câu 26. Trong Spring MVC, `@ModelAttribute` binding chủ yếu lấy dữ liệu theo cơ chế nào?
A. Đọc response body từ service trước khi dựng model attribute.
B. Deserialize JSON body trực tiếp bằng Jackson cho mọi field.
C. Bind request parameters vào property của object đích.
D. Thực thi Jakarta Validation mà bỏ qua mọi bước binding.
Đáp án đúng: C

Câu 27. Với Spring MVC, `@Valid @RequestBody CreateUserRequest` chủ yếu kết hợp những bước nào?
A. Bỏ qua các constraint Jakarta vì RequestBody là JSON.
B. Chạy Validator trước khi body được deserialize.
C. Chạy DataBinder setter từ query string rồi tạo JSON response.
D. Giải mã HTTP body rồi chạy validation trên DTO.
Đáp án đúng: D

Câu 28. Trong MVC handler, muốn nhận lỗi validation của `@ModelAttribute` vào `BindingResult`, đặt tham số ở đâu?
A. Đặt `BindingResult` đầu tiên trước mọi tham số handler.
B. Đặt `BindingResult` ngay sau tham số model được validate.
C. Đặt `BindingResult` làm return type của controller method.
D. Đặt `BindingResult` sau `HttpServletResponse` của method.
Đáp án đúng: B

Câu 29. Trong Spring WebFlux, `@Valid @RequestBody Payload` có dữ liệu không hợp lệ và không xử lý lỗi tại chỗ, lỗi thường là gì?
A. `WebExchangeBindException` khi validation dữ liệu request thất bại.
B. `InvalidMediaTypeException` cho mọi lỗi Jakarta constraint.
C. `NoSuchBeanDefinitionException` vì thiếu HTTP body mapper.
D. `MethodArgumentNotValidException` của Spring MVC Servlet.
Đáp án đúng: A

Câu 30. Muốn phản hồi lỗi field có nội dung theo ngôn ngữ của request, hạ tầng nào phù hợp?
A. Dùng `DataBinder` tự dịch từng constraint thành HTTP header.
B. Dùng `MessageSource` resolve mã lỗi theo Locale request.
C. Dùng `BeanWrapper` nạp file dịch từ tên field của entity.
D. Dùng `ConversionService` định nghĩa ngôn ngữ của FieldError.
Đáp án đúng: B

Câu 31. API nhận JSON cập nhật user có field `role`; để ngăn mass assignment, cách nào hiệu quả?
A. Cho client gửi entity trực tiếp và ẩn `role` khỏi response.
B. Đặt `setAllowedFields` trên WebDataBinder rồi coi Jackson bị chặn.
C. Đặt `@NotNull` trên role để chặn thay đổi role trái phép.
D. Dùng request DTO giới hạn trường nhận và map rõ sang domain.
Đáp án đúng: D

Câu 32. Muốn kiểm thử binding và thông báo lỗi của MVC lẫn WebFlux, bộ công cụ nào phù hợp?
A. Dùng MockMvc và WebTestClient với input sai, assert lỗi.
B. Dùng JdbcTemplate và DataBinder chỉ test dữ liệu SQL.
C. Dùng JConsole kiểm tra annotation của DTO khi request lỗi.
D. Dùng BeanWrapper trên DTO rồi coi HTTP validation đã đúng.
Đáp án đúng: A
