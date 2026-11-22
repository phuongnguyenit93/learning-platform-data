# Ghi nhận quyết định, giới hạn và tiêu chí nghiệm thu

Một thiết kế MVC có thể trông hợp lý trên sơ đồ nhưng vẫn khó triển khai nếu nhóm không ghi rõ vì sao chọn cách tổ chức đó, những giới hạn nào phải tuân thủ và điều kiện nào chứng minh thiết kế đã đáp ứng yêu cầu. Trong một dự án thực tế, người đọc cần hiểu không chỉ “Controller gọi Service rồi render View”, mà còn biết ranh giới dữ liệu nằm ở đâu, lỗi được xử lý thế nào, quyền được kiểm tra ở tầng nào, hiệu năng được đo theo mục tiêu nào và khi nào nhóm có thể chấp nhận kết quả.

Bài học thuộc chương **Đánh giá thiết kế** của module **MODEL_VIEW_CONTROLLER**. Nội dung tập trung vào việc ghi nhận quyết định kiến trúc, giới hạn kỹ thuật/nghiệp vụ và tiêu chí nghiệm thu có thể kiểm chứng cho một thiết kế MVC. Ví dụ xuyên suốt dùng chức năng quản lý sách trong ứng dụng web Java/Spring MVC. Người học sẽ lập bản ghi quyết định, so sánh phương án, xác định trade-off, viết acceptance criteria, liên kết tiêu chí với test và tổ chức buổi review sao cho kết luận có thể truy vết sau này.

## 1. Vì sao cần ghi nhận quyết định thiết kế?

Một sơ đồ thành phần chỉ mô tả một phần cấu trúc. Nó thường không giải thích:

- Vì sao Controller gọi application service thay vì repository trực tiếp.
- Vì sao form dùng Request DTO và trang chi tiết dùng ViewModel.
- Vì sao một số thao tác trả redirect còn API trả JSON.
- Vì sao ứng dụng chọn optimistic locking thay vì khóa pessimistic.
- Giới hạn nào đến từ framework, hệ thống cũ, ngân sách, dữ liệu hoặc hạ tầng.
- Điều kiện nào phải đạt trước khi nhóm chấp nhận triển khai.

Nếu quyết định chỉ tồn tại trong trí nhớ hoặc cuộc trò chuyện, nhóm dễ lặp lại tranh luận, hiểu sai ý định ban đầu hoặc vô tình đảo ngược một lựa chọn có lý do. Khi thành viên mới tham gia, họ không biết đâu là quy tắc có chủ đích và đâu là chi tiết tạm thời.

Một bản ghi thiết kế tốt giúp:

1. Giữ lại bối cảnh và vấn đề đã dẫn đến quyết định.
2. Làm rõ phương án đã cân nhắc và lý do chọn.
3. Nêu các đánh đổi, rủi ro và giới hạn được chấp nhận.
4. Chuyển yêu cầu thành tiêu chí có thể kiểm thử hoặc đo lường.
5. Giúp reviewer xác nhận thiết kế đáp ứng nhu cầu trước khi triển khai.
6. Tạo cơ sở xem xét lại quyết định khi bối cảnh thay đổi.

Ghi nhận quyết định không có nghĩa là phải viết tài liệu dài cho mọi thay đổi nhỏ. Hãy ghi lại những lựa chọn có ảnh hưởng đến ranh giới module, hợp đồng dữ liệu, bảo mật, khả năng vận hành, chi phí thay đổi hoặc nhiều nhóm phát triển.

## 2. Phân biệt quyết định, giới hạn và tiêu chí nghiệm thu

Ba khái niệm này có quan hệ nhưng trả lời những câu hỏi khác nhau.

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong MVC |
|---|---|---|
| Quyết định (decision) | Nhóm chọn cách nào và vì sao? | Controller gọi use case; không truy cập JPA repository trực tiếp |
| Giới hạn (constraint) | Điều gì bắt buộc hoặc không thể thay đổi trong phạm vi hiện tại? | API hiện tại phải giữ nguyên JSON contract v1 |
| Tiêu chí nghiệm thu (acceptance criterion) | Bằng chứng nào chứng minh giải pháp đạt yêu cầu? | Request sửa sách không thể thay đổi tenantId dù client gửi field đó |

### 2.1. Quyết định

Quyết định mô tả một lựa chọn có chủ đích. Nó nên nêu phương án được chọn, bối cảnh, các phương án đã cân nhắc và hệ quả.

Ví dụ:

> Chọn Controller mỏng, gọi application use case và nhận ViewModel/response DTO. Query và command được xử lý ở application layer; adapter persistence chịu trách nhiệm truy cập JPA.

Đây là một quyết định vì nó xác định ranh giới trách nhiệm và hướng phụ thuộc.

### 2.2. Giới hạn

Giới hạn là điều kiện mà thiết kế phải tôn trọng. Giới hạn có thể đến từ:

- Nghiệp vụ: ISBN phải duy nhất trong phạm vi một thư viện.
- Tương thích: API công khai không được đổi tên field trong phiên bản hiện tại.
- Kỹ thuật: hệ thống đang chạy trên Java/Spring phiên bản đã được phê duyệt.
- Hạ tầng: database dùng chung, không được tạo thêm dịch vụ vận hành.
- Bảo mật: mọi truy vấn sách phải giới hạn theo tenant hiện tại.
- Thời gian: đợt phát hành chỉ cho phép thay đổi trong một phạm vi nhất định.
- Tổ chức: nhóm vận hành chưa hỗ trợ một công nghệ mới.

Cần phân biệt giới hạn thật với giả định. “Hệ thống phải chạy trên database hiện có” có thể là constraint đã được xác nhận. “Có lẽ sau này sẽ chuyển database” chỉ là giả định nếu chưa có kế hoạch hoặc cam kết.

### 2.3. Tiêu chí nghiệm thu

Tiêu chí nghiệm thu mô tả điều kiện quan sát được để quyết định một yêu cầu đã hoàn thành. Một tiêu chí tốt phải đủ cụ thể để người triển khai, reviewer và tester có thể hiểu giống nhau.

Ví dụ chưa đủ rõ:

> Controller xử lý lỗi tốt.

Ví dụ có thể kiểm chứng:

> Khi người dùng gửi form cập nhật với tiêu đề rỗng, hệ thống render lại trang sửa sách, giữ các giá trị đã nhập, hiển thị lỗi gắn với trường tiêu đề và không gọi use case cập nhật.

Tiêu chí thứ hai có thể được kiểm tra bằng MVC test và quan sát response/model.

## 3. Bắt đầu review từ bối cảnh và phạm vi

Trước khi xem chi tiết class hoặc method, cần thống nhất phạm vi review. Một buổi review không có phạm vi rõ có thể biến thành cuộc thảo luận mọi thứ về kiến trúc, trong khi câu hỏi cần quyết định chỉ liên quan đến một luồng.

### 3.1. Ghi rõ vấn đề cần giải quyết

Ví dụ với chức năng quản lý sách:

- Thư viện cần cho phép thủ thư tìm kiếm, xem và cập nhật thông tin sách.
- Hiện tại Controller vừa binding form, truy vấn JPA, kiểm tra ISBN, cập nhật entity và tạo View.
- Các form khác nhau đang dùng chung một entity.
- Lỗi validation và lỗi nghiệp vụ được hiển thị không nhất quán.
- Một số trang phát sinh truy vấn lazy khi render.
- API dành cho đối tác đang serialize entity trực tiếp.

Mô tả vấn đề bằng hành vi và hậu quả. Tránh bắt đầu bằng kết luận như “phải dùng Clean Architecture” nếu chưa chỉ ra vấn đề mà quyết định đó giải quyết.

### 3.2. Chọn phạm vi

Có thể review một trong các phạm vi sau:

| Phạm vi | Nội dung cần xem |
|---|---|
| Một action | Route, input, validation, use case, response |
| Một nhóm chức năng | Danh sách, chi tiết, tạo, sửa, xóa |
| Một module | Controller, application service, domain, repository, View |
| Một hợp đồng | Request DTO, response DTO, ViewModel, lỗi API |
| Một thay đổi kiến trúc | Ranh giới phụ thuộc, transaction, tích hợp, migration |

Ghi rõ phần nào nằm ngoài review. Ví dụ, review luồng sửa sách có thể không đánh giá toàn bộ hệ thống phân quyền hoặc chiến lược backup database, nhưng phải nêu các dependency liên quan.

### 3.3. Thu thập bằng chứng

Không đánh giá chỉ dựa vào tên package hoặc sơ đồ do tác giả vẽ. Hãy thu thập bằng chứng phù hợp:

- Luồng request từ route đến response.
- Controller action và dependency mà nó sử dụng.
- Request/response DTO, ViewModel và domain model.
- Use case, repository port hoặc adapter persistence.
- Validation, exception handler và security configuration.
- Query SQL/JPA được sinh ra nếu review hiệu năng.
- Test hiện có và kết quả quan sát được.
- Log, trace, metric hoặc SLO nếu review vận hành.
- Ràng buộc API hoặc tài liệu tích hợp đã công bố.

Một kết luận nên dẫn đến bằng chứng cụ thể, chẳng hạn file/class, test, response mẫu hoặc metric. Nếu chưa có bằng chứng, ghi đó là câu hỏi mở hoặc giả định cần xác nhận.

## 4. Ghi quyết định bằng một cấu trúc ổn định

Một bản ghi quyết định kiến trúc (Architecture Decision Record — ADR) không cần theo một mẫu duy nhất, nhưng nên có các phần đủ để người khác hiểu và xem xét lại.

### 4.1. Các phần nên có

| Phần | Nội dung |
|---|---|
| ID và tiêu đề | Mã ổn định, tên ngắn mô tả lựa chọn |
| Trạng thái | Proposed, Accepted, Rejected, Superseded hoặc Deprecated |
| Ngày và người quyết định | Khi nào và ai chịu trách nhiệm |
| Bối cảnh | Vấn đề, mục tiêu, phạm vi và bằng chứng |
| Giới hạn/giả định | Điều kiện bắt buộc và điều chưa được xác nhận |
| Phương án | Các lựa chọn đã cân nhắc |
| Quyết định | Phương án được chọn |
| Lý do | Vì sao phù hợp với mục tiêu và constraint |
| Hệ quả | Lợi ích, chi phí, trade-off và rủi ro |
| Tiêu chí nghiệm thu | Điều kiện có thể kiểm chứng |
| Liên kết | Issue, PR, test, diagram hoặc ADR liên quan |

Không cần điền mọi trường nếu không phù hợp. Nhưng trạng thái và lý do của quyết định phải đủ rõ để không nhầm một đề xuất chưa duyệt với quy tắc đã được thống nhất.

### 4.2. Trạng thái quyết định

- **Proposed:** đang được đề xuất, chưa có hiệu lực.
- **Accepted:** đã được chấp nhận và là căn cứ triển khai.
- **Rejected:** đã xem xét nhưng không chọn.
- **Superseded:** đã được thay thế bởi quyết định khác.
- **Deprecated:** không còn khuyến nghị áp dụng, nhưng có thể còn tồn tại trong hệ thống.

Không sửa nội dung ADR cũ để làm như quyết định mới luôn đúng. Khi bối cảnh thay đổi, tạo quyết định mới và liên kết đến bản ghi cũ để giữ lịch sử.

## 5. So sánh phương án trước khi quyết định

Một review có chất lượng không chỉ ghi phương án được chọn. Nó cần cho thấy những lựa chọn quan trọng đã được cân nhắc.

Ví dụ: Controller cần lấy dữ liệu chi tiết sách. Có ba phương án:

1. Controller gọi JPA repository và đưa entity vào View.
2. Controller gọi application service trả về ViewModel.
3. Controller gọi query service trả projection rồi mapper thành ViewModel.

| Tiêu chí | Entity trực tiếp | Application service trả ViewModel | Query projection + ViewModel |
|---|---|---|---|
| Độ đơn giản ban đầu | Cao | Trung bình | Trung bình |
| Coupling với ORM | Cao | Thấp nếu contract độc lập | Thấp |
| Kiểm soát field đầu ra | Phụ thuộc template/serializer | Rõ qua ViewModel | Rõ qua projection và ViewModel |
| Kiểm soát truy vấn | Dễ phát sinh lazy loading | Tùy cách service tải dữ liệu | Có thể chọn field/query rõ |
| Tái sử dụng với REST | Dễ lộ entity contract | Có thể dùng application result chung | Có thể dùng query result chung |
| Chi phí mapping | Thấp ban đầu | Có | Có thể có hai bước |
| Phù hợp | Prototype rất nhỏ, phạm vi kiểm soát | Phần lớn use case web | Màn hình đọc cần projection cụ thể |

Không có phương án tốt nhất cho mọi hệ thống. Quyết định phải gắn với constraint và mục tiêu. Nếu một màn hình chỉ có vài field và không có tích hợp khác, có thể chọn cách đơn giản hơn. Nếu API công khai, dữ liệu tenant hoặc entity graph phức tạp, hợp đồng DTO rõ ràng thường đáng với chi phí mapping.

### 5.1. Đánh giá trade-off thay vì dùng khẩu hiệu

Những câu như “DTO luôn tốt hơn” hoặc “Controller phải mỏng tuyệt đối” không thay thế phân tích. Hãy hỏi:

- Lợi ích nào đang được mua?
- Chi phí nào phát sinh?
- Ai sẽ chịu trách nhiệm bảo trì?
- Rủi ro nào được giảm và rủi ro nào xuất hiện?
- Khi nào cần xem xét lại lựa chọn?
- Có thể đo hoặc kiểm chứng giả định không?

Một quyết định có thể chấp nhận một ít mapping lặp lại để giảm coupling với persistence. Đây là trade-off có chủ đích, không phải sai sót.

## 6. Review trách nhiệm Model, View và Controller

Trong MVC, review cần kiểm tra trách nhiệm qua hành vi thực tế.

### 6.1. Controller

Kiểm tra:

- Route và HTTP method có phù hợp với thao tác đọc/ghi không?
- Controller có binding và validation ở mức giao thức không?
- Controller gọi use case/service thay vì tự viết nghiệp vụ và truy vấn không?
- Có xử lý redirect, status và View selection nhất quán không?
- Có dependency không cần thiết hoặc method quá nhiều trách nhiệm không?
- Có lưu state mutable trong field singleton không?
- Lỗi được chuyển thành response ở đúng ranh giới không?

Controller không nhất thiết phải chỉ có vài dòng. Nó có thể cần phối hợp binding, validation, model attributes và điều hướng. Vấn đề là logic nghiệp vụ và persistence có bị đặt sai nơi hay không.

### 6.2. Model và application/domain

Kiểm tra:

- Quy tắc nghiệp vụ có thể được gọi từ nhiều adapter không?
- Domain model có giữ các bất biến quan trọng không?
- Application service có điều phối use case và transaction rõ ràng không?
- Có phụ thuộc ngược vào HttpServletRequest, ModelAndView hoặc template engine không?
- Request DTO, response DTO, ViewModel và persistence entity có bị đồng nhất vô điều kiện không?
- Trạng thái có được thay đổi qua hành vi phù hợp không?

Không đồng nhất MVC Model của Spring (container chứa attribute để render) với domain model. Review cần chỉ rõ loại model đang được nói đến.

### 6.3. View

Kiểm tra:

- View chỉ nhận dữ liệu cần để trình bày không?
- Template có truy cập repository hoặc service trực tiếp không?
- Output có được escape đúng ngữ cảnh không?
- Form có label, error summary và thông báo rõ không?
- View có hiển thị trạng thái loading, empty, success và error không?
- Có hỗ trợ bàn phím, focus và responsive không?
- Nội dung có phụ thuộc locale hoặc timezone theo yêu cầu không?

View có thể chứa điều kiện trình bày. Nhưng quyết định quyền, quy tắc nghiệp vụ và truy vấn dữ liệu phải được bảo vệ ở server.

## 7. Review luồng request và hợp đồng dữ liệu

Hãy chọn một luồng đại diện, ví dụ cập nhật sách:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Thủ thư
    participant Browser as Trình duyệt
    participant Controller as BookController
    participant UseCase as UpdateBookUseCase
    participant Domain as Book
    participant LoadPort as LoadBookPort
    participant SavePort as SaveBookPort
    participant Adapter as JPA Adapter
    participant DB as Database

    User->>Browser: Gửi form sửa sách
    Browser->>Controller: POST /books/{id}
    Controller->>Controller: Binding và validation
    Controller->>UseCase: update(command)
    UseCase->>LoadPort: Tải sách theo ID và tenant
    LoadPort->>Adapter: Gọi implementation
    Adapter->>DB: SELECT
    DB-->>Adapter: Dữ liệu sách
    Adapter-->>LoadPort: Persistence result
    LoadPort-->>UseCase: Book
    UseCase->>Domain: Áp dụng quy tắc
    UseCase->>SavePort: Lưu thay đổi
    SavePort->>Adapter: Gọi implementation
    Adapter->>DB: UPDATE
    DB-->>Adapter: Kết quả ghi
    Adapter-->>SavePort: Persistence result
    SavePort-->>UseCase: Hoàn tất
    UseCase-->>Controller: Kết quả use case
    Controller-->>Browser: Redirect hoặc lỗi
~~~

Sơ đồ cần phản ánh đúng thứ tự trong triển khai thực tế. Nếu domain được tải trước khi gọi repository save, thể hiện đúng điều đó; không dùng sơ đồ lý tưởng để che một dependency khác.

### 7.1. Kiểm tra hợp đồng input

- Field nào client được phép gửi?
- Field nào server tự xác định?
- Có giới hạn độ dài, kiểu và định dạng không?
- Validation cấu trúc và validation nghiệp vụ được phân biệt không?
- Có chống mass assignment không?
- Có kiểm tra tenant/ownership từ ngữ cảnh xác thực không?
- Có version hoặc idempotency key khi cần không?

### 7.2. Kiểm tra hợp đồng output

- View/API nhận đúng field cần thiết không?
- Có lộ tenant ID, audit field, internal note hoặc secret không?
- Entity graph có thể tạo vòng serialization không?
- Lazy relation có bị đọc trong lúc render không?
- API có giữ compatibility với client cũ không?
- Kiểu ngày giờ, tiền tệ và enum có được định nghĩa rõ không?

### 7.3. Kiểm tra lỗi như một phần của contract

Hợp đồng không chỉ mô tả response thành công. Nó cần nói rõ:

- Validation lỗi hiển thị field error hay object error.
- Not found, forbidden và conflict được ánh xạ thế nào.
- API dùng cấu trúc lỗi ổn định nào.
- Người dùng có giữ được dữ liệu form không.
- Retry có an toàn không.
- Thông tin nào được ghi log và thông tin nào tuyệt đối không được ghi.

## 8. Ghi nhận giới hạn và giả định

Giới hạn cần cụ thể và có nguồn gốc. Đừng viết “hệ thống phải nhanh” hoặc “bảo mật cao” vì không ai biết cách kiểm tra.

### 8.1. Nhóm giới hạn thường gặp

| Nhóm | Ví dụ | Cách kiểm chứng |
|---|---|---|
| Nghiệp vụ | ISBN duy nhất trong một thư viện | Domain test và unique constraint |
| API compatibility | Giữ JSON field của API v1 | Contract test |
| Security | Mọi query giới hạn theo tenant | Authorization test và query review |
| Performance | Danh sách có phân trang, không tải toàn bộ entity graph | Query count và load test |
| Availability | Không phụ thuộc dịch vụ email để hiển thị danh sách sách | Failure test |
| Accessibility | Form có label và lỗi gắn với trường | Accessibility test/manual review |
| Localization | Message và định dạng phụ thuộc locale | Locale test |
| Operations | Log phải có correlation ID, không ghi token | Log inspection test |
| Platform | Chạy trên Java/Spring phiên bản được hỗ trợ | Build pipeline |

### 8.2. Constraint, assumption và dependency

- **Constraint:** điều kiện đã được xác nhận và thiết kế phải tuân theo.
- **Assumption:** điều đang giả định đúng nhưng cần xác nhận hoặc theo dõi.
- **Dependency:** hệ thống, nhóm hoặc dịch vụ khác mà giải pháp cần.

Ví dụ:

| Loại | Nội dung | Chủ sở hữu/xác nhận |
|---|---|---|
| Constraint | API đối tác hiện tại phải giữ response v1 | Nhóm API |
| Assumption | Danh mục sách thay đổi ít trong ngày | Product/operations |
| Dependency | Dịch vụ xác thực cung cấp tenant context | Nhóm Identity |
| Constraint | Mọi thay đổi sách phải có audit record | Product/security |
| Assumption | Lưu lượng tìm kiếm chủ yếu là read | Quan sát metric |

Không biến giả định thành sự thật trong ADR. Ghi người cần xác nhận và thời điểm cần xem lại nếu giả định ảnh hưởng lớn đến thiết kế.

### 8.3. Giới hạn có thể thay đổi theo thời gian

Một constraint có thể được gỡ bỏ khi:

- Nâng cấp framework.
- Hoàn thành migration.
- Có dịch vụ hoặc hạ tầng mới.
- Thay đổi hợp đồng với client.
- Có dữ liệu hiệu năng mới.
- Quy trình bảo mật thay đổi.

Ghi điều kiện xem xét lại giúp tránh để quyết định cũ tồn tại mãi sau khi bối cảnh đã khác.

## 9. Viết tiêu chí nghiệm thu có thể kiểm chứng

Tiêu chí nghiệm thu chuyển mong đợi thành điều kiện pass/fail. Chúng nên được viết đủ cụ thể để developer biết cần xây dựng gì và tester biết cần xác minh gì.

### 9.1. Tiêu chí tốt có đặc điểm gì?

Một tiêu chí tốt:

- Có chủ thể hoặc điều kiện đầu vào rõ.
- Mô tả hành vi quan sát được.
- Xác định kết quả mong đợi.
- Có thể kiểm tra bằng test, inspection hoặc metric.
- Không phụ thuộc vào một chi tiết triển khai không cần thiết.
- Không chứa từ mơ hồ như “nhanh”, “đẹp”, “an toàn” nếu không có định nghĩa.

Ví dụ:

| Chưa đủ rõ | Có thể kiểm chứng |
|---|---|
| Tìm kiếm hoạt động tốt | Khi keyword hợp lệ được gửi, danh sách chỉ chứa sách khớp bộ lọc và phân trang theo size đã giới hạn |
| Form phải an toàn | Request cập nhật không thể thay đổi tenantId, ownerId hoặc published qua field bổ sung |
| Trang phải nhanh | Với dataset và tải đại diện đã thống nhất, p95 của GET /books không vượt SLO của module |
| Lỗi phải thân thiện | Khi ISBN trùng, form giữ input, gắn lỗi vào ISBN và không ghi dữ liệu |
| Phải có test | Các tiêu chí nghiệp vụ quan trọng có unit/integration/controller test tương ứng trong pipeline |

### 9.2. Dùng Given–When–Then

Cấu trúc Given–When–Then giúp tách bối cảnh, hành động và kết quả:

- **Given:** trạng thái ban đầu hoặc điều kiện.
- **When:** hành động được thực hiện.
- **Then:** kết quả có thể quan sát.

Ví dụ:

> Given thủ thư có quyền sửa sách và form đang chứa version hiện tại.  
> When thủ thư gửi form với tiêu đề hợp lệ và ISBN chưa được sử dụng.  
> Then hệ thống cập nhật sách, lưu audit record và redirect đến trang chi tiết.

Ví dụ lỗi:

> Given ISBN đã thuộc về một sách khác trong cùng thư viện.  
> When thủ thư gửi form cập nhật với ISBN đó.  
> Then hệ thống không thay đổi sách, giữ các giá trị form, hiển thị lỗi tại trường ISBN và trả lại trang sửa.

### 9.3. Tiêu chí chức năng và phi chức năng

| Loại | Ví dụ tiêu chí |
|---|---|
| Functional | Người có quyền có thể tạo, sửa, xem và tìm kiếm sách |
| Security | Người dùng tenant A không thể đọc hoặc sửa sách tenant B |
| Data integrity | ISBN không bị trùng trong phạm vi thư viện |
| Performance | Danh sách dùng pagination và query không tải toàn bộ quan hệ |
| Accessibility | Lỗi form được liên kết với input và có thể nhận biết bằng screen reader |
| Reliability | Timeout khi ghi không được retry mù gây tạo bản ghi trùng |
| Observability | Lỗi bất ngờ có correlation ID để truy vết |
| Compatibility | API v1 giữ cấu trúc response đã công bố |

Các ngưỡng định lượng như p95, throughput hoặc tỷ lệ lỗi phải lấy từ SLO, baseline hoặc yêu cầu đã thống nhất của dự án. Không tự đặt con số tùy ý chỉ để tiêu chí có vẻ cụ thể.

## 10. Ví dụ bản ghi quyết định cho chức năng quản lý sách

Giả sử nhóm đang thiết kế luồng sửa sách. Bản ghi sau minh họa cách kết nối bối cảnh, phương án, giới hạn và acceptance criteria.

~~~text
ADR-007: Tách ranh giới web, application và persistence cho chức năng sách

Trạng thái: Accepted
Phạm vi: Trang HTML quản lý sách và REST API cho đối tác

Bối cảnh:
BookController hiện truy cập BookJpaRepository trực tiếp,
bind form vào entity và trả entity cho template.
Điều này làm Controller phụ thuộc persistence,
có nguy cơ mass assignment và lazy loading khi render.

Mục tiêu:
- Giữ Controller tập trung vào HTTP và điều hướng.
- Bảo vệ quy tắc nghiệp vụ khi có nhiều adapter gọi use case.
- Kiểm soát dữ liệu được nhận và dữ liệu được công bố.
- Có thể kiểm thử use case mà không cần Spring MVC.

Giới hạn:
- Giữ route HTML hiện có trong đợt phát hành này.
- API đối tác tiếp tục giữ response v1.
- Mọi query phải áp dụng tenant scope.
- Database hiện tại tiếp tục là nguồn dữ liệu chính.

Phương án:
A. Controller gọi JPA repository và trả entity.
B. Controller gọi application service, nhận DTO/ViewModel.
C. Controller gọi query use case; query use case dùng port đọc projection,
   command create/update đi qua application use case.

Quyết định:
Chọn query use case cho list/detail; query use case gọi query port
được JPA adapter triển khai và trả projection. Command create/update
đi qua application use case. Controller chuyển request DTO thành command
và kết quả thành ViewModel. JPA adapter giữ chi tiết ORM.

Lý do:
- Query projection giới hạn field và giảm việc render kích hoạt lazy load.
- Command use case bảo vệ quy tắc và authorization.
- Hợp đồng ViewModel/API không phụ thuộc entity.

Hệ quả:
- Tăng số kiểu dữ liệu và mapping.
- Cần test projection và mapper.
- Khi đổi schema, adapter có thể cần cập nhật mapping.
- Controller và template ít phụ thuộc persistence hơn.

Rủi ro:
- Mapper bỏ sót field hiển thị.
- Query projection không cập nhật khi ViewModel thay đổi.
- Tenant scope bị quên trong query mới.

Tiêu chí nghiệm thu:
- Controller không inject BookJpaRepository.
- Form không bind trực tiếp BookEntity.
- Request cập nhật không thay đổi tenantId hoặc ownerId.
- Query list/detail chỉ trả field cần thiết.
- Test xác nhận tenant A không đọc được sách tenant B.
- Khi ISBN trùng, form giữ input và hiển thị lỗi đúng trường.
- API v1 giữ contract đã công bố.

Xem xét lại khi:
- Có yêu cầu chuyển nguồn dữ liệu.
- Lưu lượng hoặc SLO thay đổi đáng kể.
- API v2 được phê duyệt.
~~~

Đây là một ví dụ có chủ đích, không phải mẫu bắt buộc cho mọi dự án. Tên ID, người quyết định, ngày, link issue và bằng chứng phải được thay bằng thông tin thật của nhóm.

## 11. Từ tiêu chí nghiệm thu đến test và bằng chứng

Một tiêu chí chỉ có giá trị vận hành khi biết cách xác minh. Hãy liên kết tiêu chí với test hoặc hoạt động review.

| Acceptance criterion | Bằng chứng phù hợp | Phạm vi test/review |
|---|---|---|
| Controller không truy cập repository | Dependency inspection hoặc architecture test | Architecture |
| Request không cập nhật tenantId | Gửi field giả và kiểm tra dữ liệu sau request | Security/integration |
| ISBN duy nhất | Hai request cạnh tranh và unique constraint | Integration |
| Lỗi ISBN giữ form | Kiểm tra model, field error và input | MVC test |
| Query không phát sinh N+1 | SQL/query count trên dữ liệu đại diện | Persistence test |
| API v1 không đổi | Schema/contract test | API contract |
| Error message có thể đọc bằng screen reader | DOM/accessibility inspection | Accessibility |
| Log có correlation ID | Gây lỗi và kiểm tra log/trace | Observability |

Không phải mọi tiêu chí đều cần một unit test. Một số cần integration test, contract test, load test, security test hoặc review thủ công. Điều quan trọng là bằng chứng được xác định trước và có thể lặp lại.

### 11.1. Traceability

Có thể liên kết theo chuỗi:

~~~text
Yêu cầu
  -> Quyết định thiết kế
      -> Giới hạn/giả định
          -> Acceptance criterion
              -> Test hoặc bằng chứng
                  -> Kết quả review/release
~~~

Ví dụ, yêu cầu bảo vệ dữ liệu tenant dẫn đến quyết định lấy tenant từ security context và giới hạn query. Tiêu chí nghiệm thu yêu cầu tenant A không truy cập được sách tenant B. Test tích hợp gửi request với hai danh tính khác nhau và xác nhận kết quả.

Traceability giúp nhóm biết một yêu cầu được bảo vệ ở đâu và khi thay đổi cần cập nhật những test nào.

## 12. Đánh giá rủi ro và mức độ ưu tiên

Không phải mọi finding đều có mức độ nghiêm trọng giống nhau. Review cần đánh giá tác động, khả năng xảy ra, phạm vi ảnh hưởng và khả năng phát hiện.

Một cách phân loại đơn giản:

- **Critical:** có nguy cơ lộ dữ liệu nhạy cảm, truy cập trái phép diện rộng, mất dữ liệu hoặc làm hệ thống không thể vận hành.
- **High:** vi phạm ranh giới bảo mật quan trọng, sai dữ liệu nghiệp vụ hoặc lỗi ảnh hưởng nhiều luồng.
- **Medium:** coupling, hiệu năng hoặc khả năng bảo trì gây chi phí đáng kể nhưng có phạm vi kiểm soát.
- **Low:** vấn đề nhỏ về naming, tài liệu hoặc tính nhất quán chưa gây tác động lớn.
- **Note:** gợi ý hoặc quan sát chưa phải lỗi cần chặn.

Mức độ phải đi kèm bằng chứng và tác động. Không nâng mức chỉ vì reviewer không thích một phong cách code.

### 12.1. Ví dụ finding

| Finding | Mức độ | Bằng chứng | Hành động |
|---|---|---|---|
| API trả BookEntity có internalNote | Critical/High tùy dữ liệu | JSON response chứa field nội bộ | Chặn release, dùng response DTO |
| Controller gọi repository trực tiếp | Medium | Dependency trong constructor và query trong action | Chuyển query sang application/query service |
| Form lỗi làm mất danh sách tác giả | Medium | MVC test không có authors sau validation | Nạp lại options khi render form |
| Không có test cho empty state | Low/Medium | Test suite không bao phủ trạng thái rỗng | Bổ sung controller/view test |
| Tên method không nhất quán | Low | Các action cùng loại đặt tên khác nhau | Chuẩn hóa khi sửa khu vực |

Nếu phát hiện rủi ro bảo mật hoặc mất dữ liệu, cần đánh giá theo chính sách release của tổ chức. Không dùng điểm số tổng để che lấp một finding critical.

## 13. Quy trình tổ chức buổi design review

Một buổi review hiệu quả có thể chia thành các bước:

### Bước 1: Tác giả gửi trước tài liệu

Tài liệu nên có:

- Vấn đề và phạm vi.
- Sơ đồ luồng request.
- Các thành phần chính và dependency.
- Hợp đồng input/output.
- Quyết định đề xuất và phương án thay thế.
- Giới hạn, giả định và dependency.
- Acceptance criteria.
- Rủi ro và câu hỏi còn mở.

### Bước 2: Reviewer đọc độc lập

Reviewer ghi câu hỏi dựa trên bằng chứng. Họ nên phân biệt:

- Lỗi hoặc rủi ro phải xử lý.
- Câu hỏi cần làm rõ.
- Đề xuất cải thiện.
- Sở thích cá nhân không ảnh hưởng yêu cầu.

### Bước 3: Thảo luận theo mục tiêu

Bắt đầu từ yêu cầu và constraint, sau đó đi qua luồng, ranh giới, hợp đồng, rủi ro và tiêu chí. Không bắt đầu bằng tranh luận tên class hoặc style nếu chúng không ảnh hưởng quyết định.

### Bước 4: Ghi finding và người chịu trách nhiệm

Mỗi finding cần có:

- Mô tả và bằng chứng.
- Mức độ và tác động.
- Hành động cần thực hiện.
- Người chịu trách nhiệm.
- Thời hạn hoặc điều kiện đóng.
- Cách xác minh sau khi sửa.

### Bước 5: Đưa ra kết luận

Có thể dùng các kết quả:

- **Accepted:** thiết kế đáp ứng tiêu chí và có thể triển khai.
- **Accepted with actions:** chấp nhận nhưng phải hoàn tất các hành động được ghi rõ.
- **Needs revision:** cần cập nhật thiết kế và review lại.
- **Rejected:** phương án không đáp ứng constraint hoặc rủi ro không chấp nhận được.
- **Deferred:** chưa đủ thông tin hoặc dependency chưa sẵn sàng.

Không dùng “Approved” nếu vẫn còn blocker chưa có chủ sở hữu hoặc điều kiện đóng.

## 14. Quản lý finding và action item

Finding và action item không nên chỉ nằm trong biên bản họp. Chúng cần được theo dõi đến khi đóng.

Một action item tốt gồm:

| Trường | Ví dụ |
|---|---|
| ID | DR-024 |
| Finding | Form update bind trực tiếp entity |
| Mức độ | High |
| Hành động | Tạo UpdateBookRequest và map sang command |
| Owner | Người phụ trách module books |
| Due/condition | Trước khi merge thay đổi cập nhật sách |
| Evidence | MVC test chứng minh field tenant không thể bị sửa |
| Status | Open / In progress / Resolved / Accepted risk |

Nếu nhóm chấp nhận một rủi ro, ghi rõ ai chấp nhận, lý do, phạm vi và thời điểm xem xét lại. “Đã biết” không đồng nghĩa “đã được chấp nhận”.

## 15. Khi nào cần xem xét lại quyết định?

Một quyết định không phải chân lý vĩnh viễn. Nên xem xét lại khi:

- Constraint ban đầu thay đổi.
- Có dữ liệu production cho thấy giả định sai.
- SLO không đạt hoặc tải tăng đáng kể.
- Có yêu cầu API/client mới.
- Framework hoặc nền tảng được nâng cấp.
- Ranh giới module thay đổi.
- Một dependency ngoài bị thay thế.
- Rủi ro bảo mật mới xuất hiện.
- Chi phí mapping hoặc vận hành vượt lợi ích dự kiến.

Khi thay thế quyết định, tạo bản ghi mới liên kết đến quyết định cũ. Ghi rõ phần nào còn hiệu lực, phần nào bị superseded và migration cần thiết. Không xóa lịch sử vì nó giải thích tại sao hệ thống hiện tại có cấu trúc như vậy.

## 16. Mẫu ghi nhận quyết định và tiêu chí nghiệm thu

Có thể sao chép mẫu sau cho một thay đổi MVC:

~~~markdown
# DR-XXX: <Tên quyết định>

- Trạng thái: Proposed
- Ngày:
- Tác giả:
- Người quyết định:
- Phạm vi:

## Bối cảnh và vấn đề
Mô tả luồng hiện tại, vấn đề và tác động.

## Mục tiêu
- ...
- ...

## Ngoài phạm vi
- ...
- ...

## Giới hạn đã xác nhận
- ...
- ...

## Giả định cần xác nhận
- ...
- ...

## Phương án đã cân nhắc
### A. ...
Ưu điểm:
Nhược điểm:

### B. ...
Ưu điểm:
Nhược điểm:

## Quyết định
Mô tả phương án được chọn.

## Lý do
Liên kết quyết định với mục tiêu, constraint và bằng chứng.

## Hệ quả và trade-off
- Lợi ích:
- Chi phí:
- Rủi ro:
- Cách giảm rủi ro:

## Acceptance criteria
- [ ] Given ... When ... Then ...
- [ ] ...
- [ ] ...

## Bằng chứng xác minh
- Unit/integration/controller test:
- Contract/security/performance test:
- Review thủ công:
- Metric/log/trace:

## Finding và action item
| ID | Mức độ | Hành động | Owner | Điều kiện đóng | Trạng thái |
|---|---|---|---|---|---|

## Điều kiện xem xét lại
Nêu sự kiện hoặc ngưỡng khiến quyết định cần được đánh giá lại.

## Liên kết
- Issue:
- Pull request:
- Diagram:
- ADR liên quan:
~~~

Mẫu này là điểm bắt đầu. Hãy bỏ phần không liên quan thay vì điền nội dung hình thức để tài liệu dài hơn.

## 17. Những lỗi thường gặp khi ghi quyết định và review

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ ghi kết luận, không ghi bối cảnh | Người đọc không hiểu vì sao chọn | Ghi vấn đề và bằng chứng |
| Không so sánh phương án | Quyết định giống ý kiến cá nhân | Nêu lựa chọn thực tế và trade-off |
| Nhầm assumption với constraint | Thiết kế bị khóa bởi điều chưa xác nhận | Gắn loại và người xác nhận |
| Acceptance criteria mơ hồ | Không thể biết khi nào hoàn thành | Viết hành vi và kết quả quan sát được |
| Chỉ có unit test làm bằng chứng | Bỏ sót tích hợp, security và vận hành | Chọn test theo ranh giới |
| Review theo sở thích | Tranh luận kéo dài, ít giá trị | Gắn finding với yêu cầu/rủi ro |
| Không có owner cho finding | Vấn đề tồn tại sau buổi họp | Giao owner và điều kiện đóng |
| Chấp nhận rủi ro không ghi lại | Nhóm sau không biết rủi ro đã được cân nhắc | Ghi người chấp nhận và thời hạn |
| Sửa ADR cũ mà không lưu lịch sử | Mất lý do của quyết định trước | Tạo ADR mới và supersede |
| Chỉ review happy path | Bỏ qua lỗi, quyền và concurrency | Review cả luồng thất bại |
| Dùng ngưỡng hiệu năng tùy ý | Tiêu chí không gắn SLO thực tế | Dựa trên baseline và yêu cầu đã thống nhất |

## 18. Bài tập review thiết kế MVC

Giả sử nhóm nhận yêu cầu bổ sung chức năng sửa sách và API cho đối tác.

Thiết kế ban đầu có các đặc điểm:

- BookController nhận BookEntity từ form.
- Controller gọi BookJpaRepository trực tiếp.
- Template truy cập author.books để hiển thị thông tin.
- REST endpoint serialize entity.
- ISBN được kiểm tra bằng một truy vấn trước khi lưu.
- Không có version field trong form.
- Khi có lỗi, Controller bắt Exception và hiển thị thông báo chung.
- Test chỉ kiểm tra một luồng cập nhật thành công.

Hãy thực hiện các phần sau.

### Phần A — Xác định vấn đề

Ghi ít nhất sáu finding. Với mỗi finding, nêu:

- Bằng chứng trong luồng hoặc code.
- Tác động đến nghiệp vụ, bảo mật, hiệu năng hoặc khả năng bảo trì.
- Mức độ ưu tiên.
- Cách xác minh sau khi sửa.

### Phần B — So sánh phương án

Đề xuất ít nhất hai cách tổ chức Controller, application service và persistence. So sánh:

- Độ phức tạp.
- Dependency direction.
- Khả năng tái sử dụng use case.
- Kiểm soát dữ liệu đầu vào/đầu ra.
- Khả năng test.
- Chi phí migration.

### Phần C — Ghi quyết định

Tạo một ADR có:

- Bối cảnh và mục tiêu.
- Constraint và assumption.
- Phương án đã cân nhắc.
- Quyết định và lý do.
- Hệ quả và rủi ro.
- Điều kiện xem xét lại.

### Phần D — Viết acceptance criteria

Viết ít nhất tám tiêu chí, bao gồm:

1. Request không thể thay đổi tenant hoặc owner.
2. ISBN trùng không làm cập nhật dữ liệu.
3. Stale form được phát hiện.
4. Query không tải toàn bộ entity graph.
5. API chỉ công bố field được phép.
6. Lỗi validation giữ input và hiển thị đúng trường.
7. Tenant khác không truy cập được tài nguyên.
8. Có bằng chứng test cho luồng thành công và thất bại.

### Phần E — Lập kế hoạch review

Tạo action item có owner, điều kiện đóng và bằng chứng cho từng finding high/critical. Chọn kết quả review và giải thích vì sao.

## 19. Checklist trước khi chấp nhận thiết kế

### Bối cảnh và quyết định

- [ ] Vấn đề, phạm vi và mục tiêu được mô tả rõ.
- [ ] Có bằng chứng từ luồng thực tế hoặc yêu cầu.
- [ ] Phương án thay thế quan trọng đã được cân nhắc.
- [ ] Lý do chọn gắn với constraint và mục tiêu.
- [ ] Trade-off, rủi ro và điều kiện xem xét lại được ghi.

### Giới hạn và hợp đồng

- [ ] Constraint được phân biệt với assumption và dependency.
- [ ] Request DTO chỉ nhận field được phép.
- [ ] Response DTO/ViewModel công bố đúng dữ liệu cần thiết.
- [ ] API compatibility được bảo vệ.
- [ ] Tenant, authorization và dữ liệu nhạy cảm được kiểm soát.

### MVC và chất lượng

- [ ] Controller tập trung vào HTTP binding, điều phối và response.
- [ ] Application/domain giữ quy tắc nghiệp vụ.
- [ ] View không truy cập persistence trực tiếp.
- [ ] Validation, lỗi và trạng thái empty/success được xem xét.
- [ ] Transaction và concurrency có quyết định rõ.
- [ ] Performance, accessibility và localization có tiêu chí phù hợp.
- [ ] Logging và observability không làm lộ dữ liệu nhạy cảm.

### Nghiệm thu và review

- [ ] Acceptance criteria có thể kiểm chứng.
- [ ] Mỗi tiêu chí có test hoặc bằng chứng phù hợp.
- [ ] Finding có mức độ, owner và điều kiện đóng.
- [ ] Kết quả review được ghi rõ.
- [ ] Quyết định được lưu và liên kết với issue/test/PR.
- [ ] Rủi ro được chấp nhận có người chịu trách nhiệm và thời điểm xem lại.

## 20. Kết luận

Review thiết kế MVC không dừng ở việc xác nhận có Model, View và Controller. Nhóm cần hiểu bối cảnh, luồng request, hợp đồng dữ liệu, hướng phụ thuộc, giới hạn và rủi ro. Quyết định kiến trúc ghi lại lựa chọn cùng lý do; constraint làm rõ điều kiện phải tuân thủ; acceptance criteria biến mong đợi thành hành vi có thể kiểm chứng.

Khi mỗi finding có bằng chứng, mức độ, owner và điều kiện đóng, buổi review tạo ra kết quả có thể hành động. Khi quyết định được liên kết với test và được xem xét lại lúc bối cảnh thay đổi, tài liệu thiết kế trở thành công cụ hỗ trợ phát triển và vận hành, thay vì chỉ là biên bản được viết rồi bỏ quên.
