1. Một data contract đầy đủ cần mô tả những lớp cam kết nào?
A. Chỉ kiểu JSON mà thư viện serialization hỗ trợ
B. Cấu trúc, ngữ nghĩa, chất lượng và phiên bản
C. Chỉ cấu hình kết nối giữa producer và consumer
D. Chỉ tên bảng nguồn cùng lịch trình chạy pipeline
Đáp án đúng: B

2. Trong JSON Schema, `type` dùng để ràng buộc điều gì?
A. Độ dài tối đa của mọi chuỗi trong tài liệu
B. Kiểu giá trị JSON mà một field có thể nhận
C. Tên pattern mà giá trị chuỗi cần tuân theo
D. Thứ tự thuộc tính khi xuất đối tượng ra JSON
Đáp án đúng: B

3. Với JSON Schema, `required` áp dụng lên object có ý nghĩa gì?
A. Buộc có thuộc tính; null tùy điều kiện `type`
B. Bắt buộc thuộc tính luôn là chuỗi khác rỗng
C. Bắt buộc mọi thuộc tính chỉ nhận giá trị số
D. Bắt buộc các trường phải xuất hiện đúng thứ tự
Đáp án đúng: A

4. Khi đặt `additionalProperties: false`, validator sẽ làm gì?
A. Từ chối giá trị null của mọi thuộc tính trong object
B. Từ chối những mảng có số phần tử chưa khai báo
C. Từ chối thuộc tính ngoài những thuộc tính được phép
D. Từ chối giá trị số nằm ngoài miền `minimum`
Đáp án đúng: C

5. Keyword `enum` trong JSON Schema dùng để kiểm tra điều gì?
A. Chuỗi phù hợp biểu thức chính quy của schema
B. Giá trị thuộc một tập hợp được liệt kê trước
C. Số nằm trong khoảng giới hạn dưới và trên
D. Object có đủ các trường bắt buộc được khai báo
Đáp án đúng: B

6. Schema `type: ["string", "null"]` cho phép giá trị nào?
A. Một giá trị chuỗi không rỗng hoặc số nguyên
B. Một giá trị chuỗi hoặc JSON null cho thuộc tính
C. Một mảng các chuỗi được bao trong JSON object
D. Một đối tượng có property mang tên `null`
Đáp án đúng: B

7. Với số tiền không âm, keyword JSON Schema nào phù hợp để đặt cận dưới?
A. Dùng `minLength: 0` cho giá trị kiểu number
B. Dùng `minItems: 0` cho giá trị kiểu number
C. Dùng `minimum: 0` cho giá trị kiểu number
D. Dùng `minProperties: 0` cho giá trị number
Đáp án đúng: C

8. Để kiểm tra mã đơn hàng chuỗi theo regex, keyword nào phù hợp?
A. Dùng `minimum` với biểu thức chính quy cho chuỗi
B. Dùng `required` với biểu thức chính quy cho chuỗi
C. Dùng `pattern` với biểu thức chính quy cho chuỗi
D. Dùng `uniqueItems` với biểu thức chính quy chuỗi
Đáp án đúng: C

9. Trong JSON Schema, `oneOf` yêu cầu điều kiện nào?
A. Giá trị hợp lệ theo đúng một subschema trong danh sách
B. Giá trị hợp lệ theo ít nhất một subschema trong danh sách
C. Giá trị hợp lệ đồng thời theo mọi subschema trong danh sách
D. Giá trị không hợp lệ theo bất kỳ subschema nào trong danh sách
Đáp án đúng: A

10. Vai trò chính của `$ref` trong JSON Schema là gì?
A. Ép mọi property trong object phải có giá trị null
B. Đánh dấu những key phải được giữ đúng thứ tự
C. Tự động tăng phiên bản contract khi schema thay đổi
D. Tham chiếu một schema khác để dùng lại định nghĩa
Đáp án đúng: D

11. Field `amount` là số hợp lệ nhưng hai dịch vụ hiểu đơn vị khác nhau. Cần bổ sung gì?
A. Tăng số chữ số thập phân trong serializer JSON
B. Quy định đơn vị tiền và cách diễn giải giá trị số
C. Đổi tên type số thành string trong schema trao đổi
D. Thêm cache để hai dịch vụ cùng đọc một bản ghi
Đáp án đúng: B

12. Điều gì thường nằm ngoài phạm vi kiểm tra đơn lẻ của JSON Schema?
A. Xác minh property string đúng một biểu thức regex
B. Xác minh số không thấp hơn ngưỡng `minimum`
C. Xem ID tham chiếu có tồn tại trong nguồn khác
D. Xác minh object không chứa thuộc tính lạ
Đáp án đúng: C

13. Trong Jakarta Validation, `@NotNull` kiểm tra điều gì?
A. Chuỗi khác rỗng và không chỉ chứa khoảng trắng
B. Collection phải có ít nhất một phần tử dữ liệu
C. Chuỗi phải khớp biểu thức chính quy cho trước
D. Cấm null nhưng vẫn nhận giá trị chuỗi rỗng
Đáp án đúng: D

14. Với input là tên người không được chỉ chứa dấu cách, annotation nào phù hợp?
A. Dùng `@NotBlank` để cấm chuỗi toàn khoảng trắng
B. Dùng `@NotNull` để từ chối mọi chuỗi chỉ có dấu cách
C. Dùng `@Size(min=1)` để từ chối mọi chuỗi toàn dấu cách
D. Dùng `@Positive` để từ chối mọi chuỗi không có chữ
Đáp án đúng: A

15. Để giới hạn độ dài chuỗi hoặc số phần tử collection trong Jakarta Validation, dùng gì?
A. `@Min` với ngưỡng `min` và `max` phù hợp
B. `@Digits` với ngưỡng `min` và `max` phù hợp
C. `@Size` với ngưỡng `min` và `max` phù hợp
D. `@Pattern` với ngưỡng `min` và `max` phù hợp
Đáp án đúng: C

16. Trong Jakarta Validation, `@Valid` trên field tham chiếu hỗ trợ điều gì?
A. Buộc mọi property của đối tượng con phải khác null
B. Tự động sửa các thuộc tính không hợp lệ trước ghi
C. Bỏ qua các constraint được khai báo ở lớp con
D. Kích hoạt validation lồng nhau cho đối tượng con
Đáp án đúng: D

17. Validation groups thường phục vụ nhu cầu nào trong một DTO dùng chung?
A. Ép mọi API phải dùng cùng một tập constraint mặc định
B. Chạy tự động mọi constraint theo thứ tự field của JSON
C. Vô hiệu hóa toàn bộ constraint khi request có phân trang
D. Áp các tập constraint khác nhau theo ngữ cảnh xử lý
Đáp án đúng: D

18. Ràng buộc `startDate <= endDate` phụ thuộc hai field, nên đặt kiểm tra ở đâu?
A. Constraint mức object hoặc quy tắc nghiệp vụ
B. Chỉ dùng `@NotNull` riêng lẻ trên cả hai field
C. Chỉ dùng `@Pattern` cho từng thuộc tính ngày
D. Chỉ dùng `required` để bắt buộc cả hai trường
Đáp án đúng: A

19. Trong consumer-driven contract testing, provider cần chứng minh điều gì?
A. Consumer tự động chấp nhận mọi response provider gửi
B. Provider có thể thay đổi mọi field mà không cần kiểm tra
C. Provider đáp ứng các tương tác mà consumer mong đợi
D. Consumer chỉ cần kiểm tra định dạng file log khi chạy
Đáp án đúng: C

20. Đối với message có nhiều phiên bản schema, bước bảo vệ consumer nào phù hợp?
A. Kiểm tra consumer còn đọc được payload sau thay đổi
B. Chỉ kiểm tra producer có gửi đúng số message mỗi giây
C. Chỉ kiểm tra queue có đủ dung lượng giữ message cũ
D. Chỉ kiểm tra thời gian chạy batch nhỏ hơn ngưỡng
Đáp án đúng: A

21. Thêm field tùy chọn vào response API thường ít gây vỡ tương thích khi nào?
A. Consumer bỏ qua field lạ, không lệ thuộc thứ tự
B. Consumer yêu cầu tất cả response có số field cố định
C. Consumer từ chối mọi thuộc tính chưa từng biết trước
D. Consumer parse response dựa trên vị trí key trong JSON
Đáp án đúng: A

22. Vì sao thêm một field bắt buộc vào request API có thể breaking?
A. Client cũ tự động bổ sung mọi field bắt buộc mới
B. Client cũ thiếu field mới khiến request không hợp lệ
C. Provider luôn có thể suy ra field mới từ URL request
D. JSON Schema mặc định bỏ qua mọi `required` chưa có
Đáp án đúng: B

23. Xóa một field response mà consumer đang sử dụng thường gây hệ quả gì?
A. Consumer tự động tìm thấy field tương đương trong DB
B. Provider bắt buộc tạo thêm schema ở runtime để bù
C. Pipeline tự khôi phục field từ lần chạy gần nhất
D. Consumer có thể lỗi vì dữ liệu cần thiết không còn
Đáp án đúng: D

24. Đưa data contract vào CI hiệu quả nhất bằng cách nào?
A. Chỉ xem độ lớn của payload và bỏ kiểm tra tương thích
B. Chỉ chạy formatter rồi tự tăng version mọi lần build
C. Chỉ lưu schema vào wiki mà không kiểm tra khi merge
D. Diff schema, chạy contract test và chặn breaking
Đáp án đúng: D
