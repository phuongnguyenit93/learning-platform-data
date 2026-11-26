Câu 01. Để phân tích chuỗi biểu thức SpEL như `person.name`, lớp nào phù hợp?
A. `BeanFactoryResolver` tạo Expression từ chuỗi
B. `StandardTypeConverter` tạo Expression từ chuỗi
C. `SpelExpressionParser` phân tích biểu thức SpEL
D. `StandardEvaluationContext` tạo Expression từ chuỗi
Đáp án đúng: C

Câu 02. Sau khi parser đã tạo `Expression` cho chuỗi `name`, API nào lấy giá trị trên đối tượng `person`?
A. `expression.setValue(person)` đọc thuộc tính từ root
B. `expression.getValue(person)` đọc thuộc tính từ root
C. `expression.parseExpression(person)` đọc thuộc tính root
D. `expression.getExpressionString(person)` đọc thuộc tính
Đáp án đúng: B

Câu 03. Muốn SpEL ghi giá trị mới vào thuộc tính `name` có setter, thao tác nào phù hợp?
A. `expression.getExpressionString(person)` cập nhật thuộc tính
B. `expression.getValue(person, "Minh")` cập nhật thuộc tính
C. `expression.setValue(person, "Minh")` cập nhật thuộc tính
D. `expression.isWritable(person, "Minh")` cập nhật thuộc tính
Đáp án đúng: C

Câu 04. Khi muốn đánh giá biểu thức với biến, root và cấu hình mở rộng, dùng context nào?
A. `StandardEvaluationContext` cấu hình biến và root
B. `BeanFactoryResolver` lưu biến và root của context
C. `SpelParserConfiguration` lưu bean root và biến
D. `TemplateParserContext` cấu hình biến và root SpEL
Đáp án đúng: A

Câu 05. Với dữ liệu nhập không tin cậy chỉ cần đọc property, nên chọn kiểu context nào?
A. `StandardEvaluationContext.forReadOnlyDataBinding().build()`
B. `SimpleEvaluationContext.forReadOnlyDataBinding().build()`
C. `TemplateParserContext.forReadOnlyDataBinding().build()`
D. `StandardTypeLocator.forReadOnlyDataBinding().build()`
Đáp án đúng: B

Câu 06. Trong `@Value`, cú pháp nào yêu cầu Spring đánh giá một biểu thức SpEL?
A. `@Value("@{2 + 3}")` tính toán biểu thức Spring
B. `@Value("${2 + 3}")` tính toán biểu thức Spring
C. `@Value("%{2 + 3}")` tính toán biểu thức Spring
D. `@Value("#{2 + 3}")` yêu cầu tính biểu thức SpEL
Đáp án đúng: D

Câu 07. Trong cấu hình Spring, cú pháp SpEL nào tham chiếu một bean tên `priceService`?
A. `@priceService` tham chiếu bean qua BeanResolver
B. `$priceService` tham chiếu bean qua BeanResolver
C. `T(priceService)` tham chiếu bean qua BeanResolver
D. `#priceService` tham chiếu bean qua BeanResolver
Đáp án đúng: A

Câu 08. Khi tự tạo `StandardEvaluationContext` ngoài cấu hình bean, muốn dùng `@service`, cần thiết lập gì?
A. `setTypeLocator(new BeanFactoryResolver(beanFactory))`
B. `setBeanResolver(new BeanFactoryResolver(beanFactory))`
C. `setTypeConverter(new BeanFactoryResolver(beanFactory))`
D. `setPropertyAccessors(new BeanFactoryResolver(beanFactory))`
Đáp án đúng: B

Câu 09. Đã gọi `context.setVariable("limit", 20)`, cú pháp SpEL nào lấy biến đó?
A. `T(limit)` đọc biến do EvaluationContext quản lý
B. `@limit` đọc biến do EvaluationContext quản lý
C. `$limit` đọc biến do EvaluationContext quản lý
D. `#limit` đọc biến do EvaluationContext quản lý
Đáp án đúng: D

Câu 10. Khi đã đặt đối tượng root vào EvaluationContext, biến dựng sẵn nào trỏ tới root?
A. `#vars` tham chiếu root object trong biểu thức
B. `#bean` tham chiếu root object trong biểu thức
C. `#root` tham chiếu đến root object ban đầu
D. `#this` tham chiếu root object trong biểu thức
Đáp án đúng: C

Câu 11. Trong phép chọn phần tử của collection, `#this` thường biểu diễn gì?
A. Đối tượng root ban đầu bất kể vị trí đánh giá
B. Bean được tham chiếu gần nhất qua ký hiệu `@`
C. Đối tượng EvaluationContext được cung cấp từ parser
D. Phần tử hiện tại đang được biểu thức con đánh giá
Đáp án đúng: D

Câu 12. Cho root có `items` là List, cú pháp SpEL nào đọc tên của phần tử đầu tiên?
A. `items<#0>.name` truy cập chỉ số List từ 0
B. `items[0].name` truy cập chỉ số List từ 0
C. `items(0).name` truy cập chỉ số List từ 0
D. `items{0}.name` truy cập chỉ số List từ 0
Đáp án đúng: B

Câu 13. Cho root có Map `scores`, biểu thức SpEL nào lấy điểm của khóa `math`?
A. `scores['math']` đọc giá trị theo khóa Map
B. `scores{math}` truy cập giá trị theo khóa Map
C. `scores<#math>` truy cập giá trị theo khóa Map
D. `scores('math')` truy cập giá trị theo khóa Map
Đáp án đúng: A

Câu 14. Khi `customer` có thể null, toán tử SpEL nào giúp truy cập `address` an toàn?
A. `customer?.address` không lỗi nếu customer là null
B. `customer!.address` dùng safe-navigation operator
C. `customer?:address` dùng safe-navigation operator
D. `customer??address` dùng safe-navigation operator
Đáp án đúng: A

Câu 15. Nếu cả `customer` và `address` đều có thể null, cách truy cập `city` nào tránh null dereference?
A. `customer.address.city` bảo vệ cả hai bước truy cập
B. `customer?.address.city` bảo vệ cả hai bước truy cập
C. `customer?.address?.city` bảo vệ cả hai bước
D. `customer.address?.city` bảo vệ cả hai bước truy cập
Đáp án đúng: C

Câu 16. Với `nickname` có thể null, biểu thức SpEL nào thay bằng chuỗi dự phòng?
A. `nickname ? 'guest'` dùng toán tử Elvis
B. `nickname ?: 'guest'` dùng toán tử Elvis
C. `nickname || 'guest'` dùng toán tử Elvis
D. `nickname ?? 'guest'` dùng toán tử Elvis
Đáp án đúng: B

Câu 17. Muốn nhận `'adult'` nếu `age >= 18`, ngược lại `'minor'`, dùng biểu thức nào?
A. `age >= 18 ? 'adult' : 'minor'` dùng ba ngôi
B. `age >= 18 ?: 'adult' : 'minor'` dùng ba ngôi
C. `age >= 18 ?? 'adult' : 'minor'` dùng ba ngôi
D. `age >= 18 -> 'adult' : 'minor'` dùng ba ngôi
Đáp án đúng: A

Câu 18. Với List `users`, SpEL nào chọn tất cả phần tử có `active == true`?
A. `users.$[active]` trả các phần tử phù hợp điều kiện
B. `users.?[active]` lọc danh sách theo active
C. `users.![active]` trả các phần tử phù hợp điều kiện
D. `users.^[active]` trả các phần tử phù hợp điều kiện
Đáp án đúng: B

Câu 19. Với List `users`, biểu thức nào chọn phần tử đầu tiên có `age > 18`?
A. `users.![age > 18]` lấy phần tử khớp đầu tiên
B. `users.^[age > 18]` chọn phần tử đầu tiên khớp
C. `users.$[age > 18]` lấy phần tử khớp đầu tiên
D. `users.?[age > 18]` lấy phần tử khớp đầu tiên
Đáp án đúng: B

Câu 20. Với List `users`, biểu thức nào lấy phần tử cuối cùng có `active` đúng?
A. `users.?[active]` chọn phần tử khớp cuối cùng
B. `users.![active]` chọn phần tử khớp cuối cùng
C. `users.$[active]` lấy phần tử cuối cùng phù hợp
D. `users.^[active]` chọn phần tử khớp cuối cùng
Đáp án đúng: C

Câu 21. Muốn biến List `users` thành List tên bằng SpEL, biểu thức nào phù hợp?
A. `users.$[name]` chiếu từng phần tử thành tên
B. `users.?[name]` chiếu từng phần tử thành tên
C. `users.^[name]` chiếu từng phần tử thành tên
D. `users.![name]` chiếu từng user sang tên của nó
Đáp án đúng: D

Câu 22. Trong phép lọc `users.?[age > #minAge]`, giá trị `#this` tham chiếu đến đâu?
A. Biến minAge lưu trong context trước khi chọn phần tử
B. Bean users được lookup ở ApplicationContext hiện tại
C. List users tổng thể được truyền làm root ban đầu
D. User đang được xét trong lần đánh giá điều kiện đó
Đáp án đúng: D

Câu 23. Muốn kiểm tra chuỗi mã chỉ chứa chữ số bằng regex trong SpEL, toán tử nào phù hợp?
A. `code matches '[0-9]+'` kiểm tra mẫu regex
B. `code contains '[0-9]+'` kiểm tra mẫu regex
C. `code like '[0-9]+'` kiểm tra mẫu regex
D. `code =~ '[0-9]+'` kiểm tra mẫu regex
Đáp án đúng: A

Câu 24. Trong SpEL, cú pháp nào gọi phương thức static `Math.max(2,5)` của Java?
A. `T(java.lang.Math).max(2,5)` tham chiếu type Java
B. `new java.lang.Math.max(2,5)` tham chiếu type Java
C. `@java.lang.Math.max(2,5)` tham chiếu type Java
D. `#java.lang.Math.max(2,5)` tham chiếu type Java
Đáp án đúng: A

Câu 25. Với StandardEvaluationContext phù hợp, cú pháp nào tạo đối tượng Date mới trong SpEL?
A. `@java.util.Date()` dùng constructor Java
B. `#java.util.Date()` dùng constructor Java
C. `T(java.util.Date)()` dùng constructor Java
D. `new java.util.Date()` gọi constructor Java
Đáp án đúng: D

Câu 26. Đã gọi `context.registerFunction("normalize", method)`, cú pháp nào gọi function trong SpEL?
A. `@normalize(name)` gọi function đã đăng ký
B. `#normalize(name)` gọi function đã đăng ký
C. `T(normalize)(name)` gọi function đã đăng ký
D. `$normalize(name)` gọi function đã đăng ký
Đáp án đúng: B

Câu 27. Với root có property `username`, cú pháp SpEL nào gọi method viết hoa của String?
A. `username@toUpperCase()` gọi method trên giá trị
B. `username::toUpperCase()` gọi method trên giá trị
C. `username.toUpperCase()` gọi method trên giá trị
D. `username->toUpperCase()` gọi method trên giá trị
Đáp án đúng: C

Câu 28. Biểu thức nào so sánh `age` nằm trong khoảng 18 đến 60, gồm hai đầu mút?
A. `age within {18, 60}` sử dụng SpEL between
B. `age range {18, 60}` sử dụng SpEL between
C. `age in {18, 60}` sử dụng SpEL between
D. `age between {18, 60}` dùng khoảng đóng
Đáp án đúng: D

Câu 29. Để kiểm tra `'abc'` có thuộc kiểu String bằng SpEL, cách nào hợp lệ?
A. `'abc' typeof T(java.lang.String)` kiểm tra kiểu
B. `'abc' is T(java.lang.String)` kiểm tra kiểu
C. `'abc' classof T(java.lang.String)` kiểm tra kiểu
D. `'abc' instanceof T(java.lang.String)` kiểm tra String
Đáp án đúng: D

Câu 30. Với `SpelParserConfiguration(true, true)`, hai cờ cấu hình bật tính năng nào?
A. Tự tăng tham chiếu null và collection khi truy cập
B. Bật logging SpEL và giới hạn thời gian thực thi
C. Bật compile tức thời và cache cho biểu thức được parse
D. Bật bean reference và gọi constructor theo tên rút gọn
Đáp án đúng: A

Câu 31. Khi một chuỗi gồm chữ thường và `#{name}`, cách parse để giữ văn bản lẫn biểu thức là gì?
A. `TemplateParserContext` xử lý literal và SpEL chen giữa
B. Dùng `BeanFactoryResolver` làm ParserContext khi parse
C. Dùng `StandardTypeConverter` làm ParserContext khi parse
D. Dùng `StandardEvaluationContext` làm ParserContext khi parse
Đáp án đúng: A

Câu 32. Trong `TemplateParserContext` mặc định, ký hiệu nào bao biểu thức chen vào văn bản?
A. `${...}` là cặp delimiters của biểu thức template
B. `@{...}` là cặp delimiters của biểu thức template
C. `#{...}` đánh dấu phần SpEL trong template
D. `%{...}` là cặp delimiters của biểu thức template
Đáp án đúng: C

Câu 33. Khi parser nhận `parseExpression("price * 2")` mà không có ParserContext, chuỗi được hiểu gì?
A. Chuỗi sẽ chuyển thành `${...}` khi parse
B. Toàn chuỗi là template literal và không được tính
C. Cả chuỗi là biểu thức SpEL để được đánh giá
D. Chỉ phần trong `#{...}` mới được đưa vào parser
Đáp án đúng: C

Câu 34. Muốn áp dụng Spring ConversionService trong StandardEvaluationContext, nên tích hợp gì?
A. Cấu hình `StandardTypeLocator` dựa trên ConversionService
B. Cấu hình `TemplateParserContext` dựa trên ConversionService
C. Cấu hình `BeanFactoryResolver` dựa trên ConversionService
D. `StandardTypeConverter` tích hợp ConversionService
Đáp án đúng: D

Câu 35. Khi cần tham chiếu class `java.util.UUID` trong SpEL, cú pháp nào chỉ ra kiểu?
A. `@java.util.UUID` truy cập Java type reference
B. `#java.util.UUID` truy cập Java type reference
C. `T(java.util.UUID)` truy cập Java type reference
D. `new java.util.UUID` truy cập Java type reference
Đáp án đúng: C

Câu 36. `SpelCompilerMode.MIXED` thường vận hành như thế nào?
A. Interpret trước; compile rồi có thể quay lại interpret
B. Chỉ compile biểu thức được đánh dấu `@Value`
C. Bỏ qua interpreter và chỉ chạy biểu thức đã biên dịch
D. Chỉ parse template, không hỗ trợ property access
Đáp án đúng: A

Câu 37. `SpelCompilerMode.OFF` có ý nghĩa gì với quá trình đánh giá biểu thức?
A. Dùng compiler rồi fallback khi type thay đổi
B. Tắt evaluation cả cho biểu thức đã parse
C. Dùng interpreter thay vì kích hoạt compiler SpEL
D. Yêu cầu compile ngay khi parser đọc chuỗi đầu vào
Đáp án đúng: C

Câu 38. Nếu một biểu thức SpEL được dùng nhiều lần trong request pipeline, tối ưu nào phù hợp?
A. Tạo SpelExpressionParser mới trước mỗi lần getValue
B. Tạo EvaluationContext mới thay cho việc cache Expression
C. Bật constructor resolution mỗi request để giảm chi phí
D. Lưu và dùng lại Expression đã parse thay vì parse lặp
Đáp án đúng: D

Câu 39. Vì sao không nên dùng StandardEvaluationContext để đánh giá chuỗi SpEL tùy ý từ client?
A. Context kiểm tra ACL Spring Security trước mỗi biểu thức
B. Có thể gọi method, type và truy cập dữ liệu nhạy cảm
C. Context chỉ cho phép đọc property nên không thể gọi method
D. Context chỉ có static method nếu được bật compiler
Đáp án đúng: B

Câu 40. Nếu đầu vào người dùng chỉ chọn một số field cho phép, thiết kế nào giảm rủi ro nhất?
A. Cho phép type reference nhưng chặn các method write
B. Dùng allowlist field, không đánh giá SpEL tùy ý
C. Cho client tự gửi `T(...)` để hoàn thiện query
D. Dùng StandardEvaluationContext với chuỗi tùy chọn từ client
Đáp án đúng: B
