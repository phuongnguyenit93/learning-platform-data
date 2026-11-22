# Câu hỏi phản biện theo các yêu cầu thay đổi

Đánh giá thiết kế MVC không chỉ là kiểm tra Controller có ngắn hay View có ít logic hay không. Một thiết kế cần được xem xét trong bối cảnh yêu cầu mới: thay đổi này làm thay đổi hành vi nào, đi qua những ranh giới nào, tác động đến dữ liệu và quyền truy cập ra sao, có phá vỡ hợp đồng hiện tại không và nhóm sẽ chứng minh tính đúng đắn bằng cách nào?

Một yêu cầu thay đổi có thể rất nhỏ ở giao diện nhưng ảnh hưởng sâu đến domain. Ví dụ, thêm nút “Đặt trước” vào trang sách có thể kéo theo trạng thái đặt trước, hàng đợi công bằng, thời hạn nhận sách, thông báo, khóa đồng thời và quyền của nhân viên thư viện. Nếu chỉ sửa View và Controller, hệ thống có thể hiển thị nút đúng nhưng xử lý sai khi hai độc giả cùng đặt một đầu sách.

Bài này cung cấp bộ câu hỏi phản biện để review các thay đổi trong ứng dụng **Model–View–Controller**. Người review lần theo request từ route đến Controller, Application Service, Domain Model, persistence và View; xem xét hợp đồng dữ liệu, form, lỗi, bảo mật, hiệu năng, kiểm thử và vận hành. Mục tiêu là tìm ra giả định chưa được xác nhận, rủi ro bị bỏ sót và bằng chứng cần có trước khi chấp nhận thiết kế.

## 1. Đánh giá thiết kế đang trả lời câu hỏi nào?

Một design review tốt trả lời bốn câu hỏi:

1. **Đúng yêu cầu:** Thiết kế có thực hiện đầy đủ hành vi mong muốn và các trường hợp biên không?
2. **Đúng ranh giới:** Trách nhiệm được đặt ở tầng có đủ thông tin và thẩm quyền để thực hiện không?
3. **An toàn khi thay đổi:** Hợp đồng, dữ liệu cũ, quyền truy cập và các luồng hiện tại có bị ảnh hưởng không?
4. **Có thể kiểm chứng và vận hành:** Nhóm có test, log, metric, migration và phương án triển khai phù hợp không?

MVC là cách tổ chức phần tiếp nhận tương tác, xử lý trạng thái/nghiệp vụ và trình bày. Một ứng dụng thực tế thường có thêm application service, repository, DTO, policy và hạ tầng. Review không nên ép mọi dự án dùng cùng số lớp; cần xác định trách nhiệm và dependency có rõ ràng hay không.

| Thành phần | Câu hỏi về trách nhiệm |
|---|---|
| Route/Router | URL và HTTP method có ánh xạ đúng đến thao tác không? |
| Controller | Có chuyển đổi HTTP input, gọi use case và chọn response không? |
| Form/Input Model | Chỉ nhận những trường client được phép gửi không? |
| Application Service | Có điều phối use case, transaction và các dependency cần thiết không? |
| Domain Model | Có bảo vệ trạng thái và bất biến nghiệp vụ không? |
| Repository/Infrastructure | Có truy vấn, lưu trữ, khóa và ánh xạ persistence đúng không? |
| Presentation Model/ViewModel | Có cung cấp dữ liệu đã chuẩn bị cho View không? |
| View/Template | Có tập trung trình bày và gửi tương tác theo hợp đồng không? |

Không phải mọi thao tác đều cần một service class, presenter hay repository riêng. Câu hỏi review là abstraction đó có bảo vệ một ranh giới có ý nghĩa hay chỉ chuyển tiếp lời gọi.

## 2. Bắt đầu bằng cách làm rõ yêu cầu thay đổi

Trước khi đọc code, hãy chuyển yêu cầu thành hành vi có thể kiểm chứng. Một câu như “thêm chức năng đặt trước sách” còn thiếu nhiều quyết định.

Hãy hỏi:

- Ai là actor: độc giả, thủ thư, quản trị viên hay hệ thống nền?
- Actor bắt đầu thao tác ở đâu: trang HTML, API, batch job hay message consumer?
- Điều kiện trước khi thao tác là gì?
- Kết quả thành công và thất bại được nhìn thấy như thế nào?
- Có trạng thái mới, chuyển trạng thái mới hoặc dữ liệu mới không?
- Có quy tắc về thời gian, thứ tự, giới hạn hoặc tính duy nhất không?
- Hành vi hiện tại nào phải tiếp tục hoạt động?
- Yêu cầu có ảnh hưởng đến dữ liệu lịch sử hoặc client đang dùng không?
- Khối lượng, độ trễ, tính sẵn sàng và mức nhất quán cần đạt là gì?
- Những giả định nào cần product owner hoặc domain expert xác nhận?

### 2.1. Tách yêu cầu thành tiêu chí chấp nhận

Ví dụ yêu cầu: “Độc giả có thể đặt trước đầu sách khi không còn bản sao sẵn sàng.”

Có thể chuyển thành các tiêu chí:

- Độc giả đã đăng nhập và đang hoạt động mới được đặt trước.
- Chỉ đặt trước đầu sách được phép lưu hành.
- Một độc giả không có hai yêu cầu đặt trước đang chờ cho cùng một đầu sách.
- Khi bản sao được trả, hệ thống phân bổ theo thứ tự hàng đợi.
- Yêu cầu được phân bổ có thời hạn nhận sách.
- Độc giả có thể hủy yêu cầu khi còn ở trạng thái phù hợp.
- Thông báo không được gửi nếu transaction phân bổ thất bại.
- Hai request đồng thời không được phân bổ cùng một bản sao.

Tiêu chí cần chỉ rõ điều kiện biên. “Thời hạn nhận sách 48 giờ” tính từ lúc bản sao được phân bổ, lúc gửi thông báo hay cuối ngày làm việc? Nếu hết hạn đúng thời điểm request đến, hệ thống xử lý theo múi giờ nào? Câu hỏi như vậy giúp tránh việc mỗi tầng diễn giải quy tắc theo một cách.

### 2.2. Phân biệt yêu cầu chức năng và yêu cầu chất lượng

| Nhóm | Ví dụ câu hỏi |
|---|---|
| Chức năng | Ai được đặt trước, hủy hoặc nhận sách? |
| Tính nhất quán | Hai request cùng tranh một bản sao thì kết quả nào hợp lệ? |
| Hiệu năng | Trang danh sách phải tải trong bao lâu với hàng đợi lớn? |
| Bảo mật | Người dùng có thể xem hoặc hủy yêu cầu của người khác không? |
| Khả năng tương thích | API/client cũ có tiếp tục hoạt động không? |
| Khả năng vận hành | Có thể theo dõi hàng đợi bị kẹt hoặc thông báo thất bại không? |
| Khả năng phục hồi | Nếu worker dừng sau khi phân bổ nhưng trước khi gửi thông báo thì sao? |

Không nên để các yêu cầu chất lượng xuất hiện lần đầu trong giai đoạn production. Chúng có thể quyết định lựa chọn transaction, index, queue hoặc hợp đồng API ngay từ đầu.

## 3. Lần theo đường đi của thay đổi trong MVC

Với mỗi yêu cầu, hãy vẽ đường đi từ điểm vào đến kết quả. Một luồng web điển hình:

~~~mermaid
flowchart TD
    A["Browser / API client"] --> B["Route + HTTP method"]
    B --> C["Authentication + endpoint policy"]
    C --> D["Controller"]
    D --> E["Bind + validate input contract"]
    E --> F["Application use case"]
    F --> G["Domain rules and state transition"]
    G --> H["Repository / transaction"]
    H --> I["Application result"]
    I --> J["Presentation mapper"]
    J --> K["ViewModel / Response DTO"]
    K --> L["HTML / JSON / redirect"]
~~~

Ở từng bước, đặt câu hỏi:

- Request mới đi vào route nào? HTTP method có phù hợp với hành vi không?
- Authentication và authorization diễn ra ở đâu?
- Dữ liệu được binding vào type nào?
- Validation nào chạy trước use case, validation nào thuộc nghiệp vụ?
- Controller gọi trực tiếp repository hay gọi application boundary?
- Quy tắc trạng thái được bảo vệ ở đâu?
- Transaction bắt đầu và kết thúc tại đâu?
- Kết quả được chuyển thành ViewModel hoặc Response DTO như thế nào?
- Lỗi đi theo đường nào để đến người dùng và log?

Sơ đồ thể hiện việc xác thực và policy ở cấp endpoint trước khi action chạy. Quyền trên một tài nguyên cụ thể thường cần được kiểm tra sau khi ứng dụng đã biết resource ID và ngữ cảnh use case; review phải xác minh bước kiểm tra đó tồn tại trong application/domain boundary phù hợp.

### 3.1. Dấu hiệu thay đổi đang đặt sai tầng

| Dấu hiệu | Câu hỏi phản biện |
|---|---|
| Controller thêm nhiều nhánh điều kiện nghiệp vụ | Các nhánh này có phải quy tắc use case/domain cần dùng chung không? |
| Template tự quyết định trạng thái được phép | Server có kiểm tra lại khi request được gửi trực tiếp không? |
| Entity được bind từ form | Client có thể gửi thêm thuộc tính nội bộ không? |
| Model gọi HTTP hoặc đọc request context | Domain có đang phụ thuộc vào giao thức web không? |
| Repository gửi email hoặc notification | Tác dụng phụ có gắn với transaction và retry đúng cách không? |
| Nhiều Controller lặp cùng quy tắc | Có một use case hoặc policy dùng chung không? |
| ViewModel được lưu như domain state | Dữ liệu trình bày có bị nhầm với dữ liệu nguồn không? |

Một dấu hiệu không tự động chứng minh thiết kế sai. Hãy kiểm tra tần suất, độ phức tạp, khả năng tái sử dụng và chi phí bảo trì trước khi yêu cầu tách lớp.

## 4. Bộ câu hỏi về trách nhiệm và ranh giới

### 4.1. Controller và application boundary

- Controller có đang điều phối HTTP hay đang quyết định quy tắc nghiệp vụ?
- Có nhiều endpoint cùng thực hiện một use case không?
- Cùng một thao tác có được gọi từ web, API, job hoặc message handler không?
- Nếu có nhiều điểm gọi, logic chung nằm ở đâu?
- Controller có biết chi tiết ORM hoặc transaction không cần thiết không?
- Có thể test use case mà không dựng MVC context không?
- Controller có xử lý đúng redirect, status code và response type không?

Ví dụ, nếu cả trang HTML và REST API đều cho phép mượn sách, hai Controller có thể có hai Form/Request DTO riêng nhưng nên gọi cùng use case. Nếu quy tắc mượn chỉ nằm trong một Controller, endpoint API mới có thể vô tình bỏ qua giới hạn số sách.

### 4.2. Domain Model và quy tắc nghiệp vụ

- Yêu cầu có thêm trạng thái hoặc chuyển trạng thái mới không?
- Có bất biến nào phải luôn đúng sau mọi thao tác?
- Quy tắc có cần áp dụng khi dữ liệu được thay đổi từ job hoặc API khác không?
- Domain object có đủ thông tin để bảo vệ quy tắc không?
- Quy tắc phụ thuộc thời gian, tiền tệ, lịch hoặc timezone nào?
- Có cần policy/domain service để biểu diễn quy tắc không?
- Có đang đưa logic hiển thị, HTTP hoặc persistence detail vào domain không?

Không phải mọi điều kiện đều cần nằm trong entity. Một quy tắc liên quan nhiều aggregate có thể thuộc domain service hoặc application service. Review cần xác định nơi có thẩm quyền thực thi quy tắc, không áp đặt một mẫu class duy nhất.

### 4.3. View và Presentation Model

- View có nhận đúng dữ liệu cần render không?
- Có logic format, phân quyền hiển thị hoặc truy vấn bị đặt trong template không?
- ViewModel có chứa dữ liệu nhạy cảm hoặc field không cần công khai không?
- Trạng thái hiển thị có được suy ra từ dữ liệu nguồn hay đang được lưu trùng lặp?
- Các nhãn, ngày tháng và số liệu có phụ thuộc locale/timezone không?
- Nếu giao diện đổi bố cục, có phải thay domain entity hoặc request contract không?
- Trạng thái lỗi và empty state có được biểu diễn rõ ràng không?

Ẩn nút trong View chỉ cải thiện trải nghiệm. Nó không thay thế authorization ở server.

## 5. Bộ câu hỏi về hợp đồng dữ liệu

Mỗi chiều dữ liệu có mục đích và vòng đời riêng. Khi review, cần xác định rõ Form/Input DTO, Command, Domain Model, Query DTO, Presentation Model và API Response DTO có đang bị dùng lẫn nhau không.

### 5.1. Hợp đồng đầu vào

- Client được phép gửi chính xác những trường nào?
- Có đang bind trực tiếp vào JPA/ORM entity không?
- Trường nào phải do server xác định như ownerId, role, tenantId hoặc createdAt?
- Có trường nào optional, nullable hoặc có default cần phân biệt không?
- Kiểu ngày/giờ có timezone rõ ràng không?
- Giá trị enum lạ hoặc field chưa biết được xử lý thế nào?
- Validation có giới hạn độ dài, range, format và kích thước payload không?
- Có nguy cơ mass assignment/overposting không?

Input Model nên biểu diễn quyền ghi của một thao tác. Không thêm trường vào form chỉ vì entity có thuộc tính đó.

### 5.2. Hợp đồng đầu ra

- Response có trả entity trực tiếp không?
- ViewModel/DTO có chứa mọi trường cần thiết và chỉ những trường được phép công khai không?
- Thay đổi field có phá vỡ client cũ không?
- Có phân biệt giá trị không có, giá trị rỗng và giá trị mặc định không?
- Có phân trang, sorting và filter ổn định không?
- API có cần versioning hoặc một giai đoạn tương thích không?
- Lỗi có mã ổn định để client xử lý không?

### 5.3. Hợp đồng giữa các tầng

Ví dụ thay đổi thêm ngày nhận sách vào phiếu mượn:

| Hợp đồng | Câu hỏi |
|---|---|
| Form Model | Người dùng có được nhập ngày nhận hay server tự đặt? |
| Application Command | Có cần truyền actor, branch hoặc policy context không? |
| Domain Model | Ngày nhận có làm thay đổi trạng thái không? |
| Persistence | Cột mới nullable hay cần backfill dữ liệu cũ? |
| Query DTO | Trang lịch sử có cần ngày nhận không? |
| ViewModel | Ngày hiển thị theo locale/timezone nào? |
| API Response | Client cũ có bỏ qua field mới an toàn không? |

Một thay đổi không nhất thiết phải tạo class mới cho mọi tầng. Hãy tách khi hợp đồng, quyền sở hữu, vòng đời hoặc cách sử dụng khác nhau.

## 6. Bộ câu hỏi về trạng thái và vòng đời

Yêu cầu mới thường thêm một trạng thái, một hành động hoặc một ngoại lệ vào quy trình hiện tại. Trước khi sửa enum hay thêm boolean, hãy mô tả state machine.

Hãy hỏi:

- Các trạng thái hiện có là gì?
- Trạng thái mới có ý nghĩa nghiệp vụ độc lập không?
- Từ trạng thái nào được chuyển sang trạng thái nào?
- Actor nào được phép thực hiện mỗi chuyển tiếp?
- Điều kiện trước và sau chuyển tiếp là gì?
- Có trạng thái kết thúc hay trạng thái có thể quay lại không?
- Có timeout, expiration hoặc scheduled transition không?
- Khi một tác vụ bị retry, chuyển tiếp có idempotent không?
- Có dữ liệu lịch sử để giải thích ai đã thay đổi trạng thái và khi nào không?
- Những luồng cũ có giả định chỉ tồn tại các trạng thái cũ không?

Ví dụ một phiếu mượn có thể chuyển:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE
    ACTIVE --> RETURNED: Trả sách
    ACTIVE --> OVERDUE: Quá hạn
    OVERDUE --> RETURNED: Trả sách
    RETURNED --> [*]
~~~

Nếu thêm trạng thái LOST, cần hỏi phiếu mượn chuyển sang LOST hay bản sao chuyển sang LOST? Đây là hai khái niệm khác nhau. Trạng thái cần được đặt trên đúng đối tượng có vòng đời tương ứng.

Tránh lưu nhiều cờ boolean độc lập nếu chúng tạo ra tổ hợp không hợp lệ. Ví dụ isBorrowed=true và isLost=true có ý nghĩa gì? Một enum hoặc state machine thường diễn đạt rõ hơn khi các trạng thái loại trừ lẫn nhau.

## 7. Bộ câu hỏi về bảo mật và quyền truy cập

Mỗi yêu cầu mới cần được xem xét theo danh tính, quyền và phạm vi dữ liệu.

- Ai được phép gọi endpoint?
- Người dùng có quyền với chính tài nguyên được gửi ID không?
- Có kiểm tra quyền ở từng use case hay chỉ ẩn nút?
- ID từ URL, form hoặc query có thể bị thay để đọc dữ liệu người khác không?
- Có tenant/branch/owner boundary cần áp dụng trong query không?
- Role mới có làm thay đổi quyền của các actor hiện có không?
- Có dữ liệu nhạy cảm nào xuất hiện trong ViewModel, JSON, error message hoặc log không?
- Form dựa trên session cookie có CSRF protection không?
- Nội dung người dùng nhập có được output-encode khi render không?
- Có giới hạn tốc độ, kích thước upload hoặc số lần thử không?
- Audit log có ghi actor, target, action và kết quả mà không lộ bí mật không?

### 7.1. Phân biệt authentication và authorization

Authentication xác định ai đang gọi. Authorization xác định người đó có được phép thực hiện hành động trên tài nguyên cụ thể hay không.

Ví dụ, thủ thư có thể được quyền tạo phiếu mượn cho độc giả tại chi nhánh của mình. Chỉ kiểm tra role LIBRARIAN có thể chưa đủ; cần kiểm tra chi nhánh, trạng thái độc giả và phạm vi bản sao. Quyền truy cập phải được xác minh ở server trong từng thao tác.

### 7.2. Những rủi ro thường bị bỏ qua

| Rủi ro | Câu hỏi review |
|---|---|
| IDOR | Đổi loanId trong URL có thể xem phiếu mượn người khác không? |
| Mass assignment | Gửi thêm ownerId hoặc status có ghi đè được dữ liệu không? |
| CSRF | POST có bị bảo vệ khi dùng session cookie không? |
| XSS | Tên sách hoặc ghi chú do người dùng nhập có được encode không? |
| Privilege escalation | Role mới có quyền rộng hơn yêu cầu không? |
| Tenant leakage | Query có lọc đúng tenant/branch không? |
| Log exposure | Token, cookie hoặc dữ liệu cá nhân có bị ghi không? |

## 8. Bộ câu hỏi về dữ liệu, transaction và migration

Một yêu cầu thay đổi có thể tác động đến schema, dữ liệu cũ, truy vấn và tính nhất quán.

- Có bảng/cột/quan hệ mới không?
- Có thay đổi kiểu, nullability, enum hoặc constraint không?
- Dữ liệu cũ được chuyển đổi hoặc backfill như thế nào?
- Có thể triển khai phiên bản ứng dụng cũ và mới cùng lúc không?
- Migration có khóa bảng lớn hoặc kéo dài không?
- Có index cho query mới không?
- Có N+1 query hoặc full table scan không?
- Transaction bao quanh những thay đổi nào?
- Nếu bước cuối thất bại, dữ liệu nào phải rollback?
- Có tác dụng phụ bên ngoài transaction như email, SMS hoặc message broker không?
- Có cần outbox, idempotency key hoặc retry policy không?
- Có chiến lược backup/restore và rollback schema không?

### 8.1. Expand/contract cho thay đổi schema

Khi nhiều phiên bản ứng dụng cùng chạy trong quá trình deploy, migration phá vỡ tương thích có thể làm phiên bản cũ lỗi.

Một chiến lược thường dùng:

1. **Expand:** thêm cột hoặc bảng mới theo cách tương thích; chưa xóa cấu trúc cũ.
2. **Deploy:** triển khai code có thể đọc/ghi theo cách tương thích với schema cũ và mới.
3. **Backfill:** chuyển dữ liệu cũ theo batch có thể retry.
4. **Switch:** chuyển dần đọc sang trường mới và xác minh.
5. **Contract:** chỉ xóa trường/cấu trúc cũ sau khi không còn phiên bản hoặc consumer sử dụng.

Không phải mọi migration cần đủ năm giai đoạn. Với thay đổi nhỏ và ứng dụng có downtime được kiểm soát, có thể đơn giản hơn. Review cần căn cứ vào chiến lược deploy thực tế.

### 8.2. Transaction và tác dụng phụ

Nếu một use case cập nhật database rồi gửi email ngay trong transaction, email có thể đã được gửi dù transaction rollback. Nếu gửi email trước commit, người nhận có thể được thông báo về một thao tác chưa tồn tại.

Hãy hỏi:

- Thông báo có bắt buộc được gửi đúng một lần hay ít nhất một lần?
- Có thể gửi sau commit không?
- Nếu worker retry, có gửi trùng không?
- Có cần transactional outbox để lưu sự kiện cùng transaction không?
- Consumer có idempotent không?
- Có dead-letter queue và cơ chế replay không?

Transactional outbox là một lựa chọn khi cần đồng bộ ghi database với ý định phát sự kiện. Nó không tự bảo đảm consumer chỉ xử lý một lần; consumer vẫn cần xử lý trùng lặp an toàn.

## 9. Bộ câu hỏi về lỗi và hợp đồng HTTP

Thay đổi mới thường thêm nhánh lỗi. Cần xem lỗi được phát hiện ở đâu và biểu diễn thế nào.

| Loại lỗi | Ví dụ | Câu hỏi review |
|---|---|---|
| Binding | UUID sai định dạng | Có chỉ rõ lỗi trường và giữ input phù hợp không? |
| Input validation | Tiêu đề rỗng | Form/API trả lỗi theo hợp đồng nào? |
| Business rule | Bản sao không khả dụng | Có mã lỗi và thông báo phù hợp không? |
| Authorization | Không có quyền trên phiếu mượn | Có trả response an toàn, không tiết lộ dữ liệu không? |
| Not found | Sách không tồn tại | Có nhất quán với chính sách che giấu tài nguyên không? |
| Conflict | Trạng thái đã thay đổi | Có dùng status phù hợp và hướng dẫn retry không? |
| Infrastructure | Database timeout | Có log/trace nội bộ và response an toàn không? |

Hãy hỏi thêm:

- HTML form nên render lại hay redirect?
- Có dùng Post/Redirect/Get để tránh submit lại khi refresh không?
- Validation error có giữ lại giá trị người dùng nhập không?
- Dữ liệu phụ của trang có được nạp lại khi render lỗi không?
- API error có schema ổn định như Problem Details hoặc error DTO không?
- Retry có thể tạo thao tác trùng không?
- Exception nào được xem là nghiệp vụ dự kiến, exception nào là lỗi hệ thống?
- Stack trace và SQL có bị đưa ra response không?

Không nên bắt mọi exception thành cùng một response. Lỗi nghiệp vụ đã biết cần được ánh xạ rõ; lỗi không dự kiến cần được log và xử lý ở error boundary chung.

## 10. Bộ câu hỏi về hiệu năng và khả năng mở rộng

Một thay đổi có thể làm một trang chậm đi dù số dòng code tăng rất ít.

- Query mới có cần index không?
- Controller hoặc View có gây N+1 query không?
- Có tải toàn bộ danh sách thay vì phân trang không?
- Filter/sort có được thực thi ở database hay trong bộ nhớ?
- Kích thước Page Model/Response DTO có tăng đáng kể không?
- Có thể cache dữ liệu nào và invalidation dựa trên sự kiện gì?
- Cache có phân tách theo người dùng/tenant không?
- Có cần rate limit cho endpoint đắt tiền?
- Công việc dài có nên chuyển sang background job không?
- Lock có giữ quá lâu trong transaction không?
- Có metric để phát hiện lock wait, timeout và queue backlog không?

Nếu thêm tìm kiếm sách theo nhiều tiêu chí, hãy kiểm tra query plan với dữ liệu có quy mô thực tế. Một truy vấn đúng trên vài chục bản ghi có thể rất chậm khi có hàng triệu bản ghi.

Nếu chuyển thao tác sang bất đồng bộ, hãy làm rõ response trả về ngay, trạng thái job, polling/callback, retry và cách người dùng biết thao tác hoàn tất hay thất bại.

## 11. Bộ câu hỏi về kiểm thử và bằng chứng

Một design review không nên dừng ở “đã có test”. Cần hỏi test nào chứng minh ranh giới nào.

| Phạm vi | Bằng chứng cần xem |
|---|---|
| Domain unit test | Bất biến và chuyển trạng thái hợp lệ/không hợp lệ |
| Application test | Điều phối use case, transaction boundary và nhánh lỗi |
| Controller/MVC test | Routing, binding, validation, principal, redirect/response |
| View test | Dữ liệu và trạng thái hiển thị quan trọng |
| Repository integration test | Query, mapping, constraint và lock trên database phù hợp |
| Security test | Không truy cập chéo người dùng/tenant; CSRF và role |
| Concurrency test | Các request tranh chấp vẫn giữ bất biến |
| Contract test | Client và API tương thích |
| Migration test | Schema mới và backfill dữ liệu cũ |
| End-to-end test | Luồng quan trọng từ request đến kết quả quan sát được |

Hãy hỏi:

- Test có kiểm tra hành vi hay chỉ kiểm tra lời gọi mock?
- Có test trường hợp dữ liệu cũ không?
- Có test actor không có quyền không?
- Có test retry và request trùng không?
- Test transaction có vô tình chạy trong transaction bao ngoài không?
- Concurrency test có chạy trên database gần production không?
- Có test migration từ phiên bản schema đang được triển khai không?
- Có test regression cho endpoint và View hiện có bị ảnh hưởng không?

Không cần test mọi chi tiết nội bộ. Ưu tiên hành vi công khai, bất biến, hợp đồng và các ranh giới có rủi ro.

## 12. Bộ câu hỏi về triển khai và vận hành

Thiết kế chưa hoàn chỉnh nếu nhóm không biết triển khai, theo dõi và khôi phục khi có sự cố.

- Thay đổi có cần feature flag không?
- Có thể deploy code trước schema hoặc ngược lại không?
- Có cần rollout theo tenant, branch hoặc nhóm người dùng không?
- Metric nào cho biết tính năng đang hoạt động đúng?
- Log có correlation ID để truy vết không?
- Có cảnh báo cho lỗi hoặc backlog quan trọng không?
- Có thể tắt tính năng mà không làm hỏng dữ liệu đã tạo không?
- Nếu rollback ứng dụng, schema có còn tương thích không?
- Dữ liệu đã được ghi theo format mới có đọc được bằng phiên bản cũ không?
- Có runbook xử lý lỗi migration, queue hoặc transaction không?

Feature flag có ích khi cần bật dần hoặc tắt nhanh một chức năng. Nhưng flag không thay thế migration tương thích và không nên tồn tại vô thời hạn mà không có owner và kế hoạch loại bỏ.

## 13. Tình huống review mẫu: thêm hàng đợi đặt trước sách

Xét yêu cầu:

> Khi tất cả bản sao của một đầu sách đang được mượn, độc giả có thể đặt trước. Khi có bản sao được trả, hệ thống phân bổ cho người đứng đầu hàng đợi. Người nhận có 48 giờ để đến lấy.

Một review cần đi xa hơn việc thêm nút và một bảng Reservation.

### 13.1. Câu hỏi làm rõ trước khi thiết kế

- Hàng đợi được tạo theo đầu sách, từng ấn bản, từng chi nhánh hay từng bản sao?
- Độc giả có thể đặt trước nếu vẫn còn một bản sao ở chi nhánh khác không?
- Có giới hạn số đặt trước đang chờ trên mỗi độc giả không?
- Độc giả có thể có nhiều yêu cầu cho cùng một đầu sách không?
- Nhân viên có thể đặt trước thay độc giả không?
- Người đứng đầu hàng đợi được xác định theo thời điểm tạo hay có ưu tiên theo loại độc giả?
- Thời hạn 48 giờ bắt đầu từ lúc phân bổ hay lúc thông báo được gửi thành công?
- Nếu người đứng đầu không đến lấy, hệ thống chuyển cho người tiếp theo như thế nào?
- Độc giả có thể hủy khi đã được phân bổ không?
- Ngày nghỉ hoặc giờ đóng cửa có làm thay đổi thời hạn không?

Nếu chưa trả lời các câu hỏi này, việc chọn schema và state machine còn dựa trên giả định.

### 13.2. Câu hỏi về domain và state machine

Một Reservation có thể có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> WAITING
    WAITING --> READY_FOR_PICKUP: Được phân bổ bản sao
    WAITING --> CANCELLED: Độc giả hủy
    READY_FOR_PICKUP --> FULFILLED: Nhận sách
    READY_FOR_PICKUP --> EXPIRED: Hết hạn
    READY_FOR_PICKUP --> CANCELLED: Hủy theo chính sách
    FULFILLED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
~~~

Các câu hỏi:

- READY_FOR_PICKUP có giữ copyId cụ thể không?
- Khi phân bổ, BookCopy chuyển sang trạng thái nào?
- Reservation và Loan có được tạo cùng lúc hay Loan chỉ tạo khi độc giả nhận sách?
- Khi hết hạn, bản sao được trả lại hàng đợi ra sao?
- Có cần lưu thời điểm vào hàng đợi, phân bổ, thông báo và hết hạn không?
- Một reservation có thể được phân bổ lại không, hay cần tạo record mới?
- Có audit history để giải thích thứ tự hàng đợi không?

Không nên để View tự suy ra trạng thái từ việc copyId có null hay không. Trạng thái cần có ý nghĩa nghiệp vụ rõ và được bảo vệ trong use case/domain.

### 13.3. Câu hỏi về transaction và concurrency

- Hai bản sao được trả gần như cùng lúc thì hàng đợi được cập nhật ra sao?
- Hai worker có thể cùng phân bổ một bản sao cho hai reservation không?
- Hai request có thể tạo hai reservation đang chờ cho cùng một member và book không?
- Lock được lấy theo thứ tự nào?
- Có unique constraint bảo vệ điều kiện “một reservation đang chờ cho một member và book” không?
- Nếu notification thất bại sau khi phân bổ, reservation có còn READY_FOR_PICKUP không?
- Worker hết hạn có thể chạy lặp lại an toàn không?
- Có cần optimistic version hoặc pessimistic lock trên hàng đợi không?

Một transaction phân bổ có thể cần khóa bản sao, chọn reservation đầu tiên hợp lệ, chuyển reservation sang READY_FOR_PICKUP và gắn copyId. Notification được phát sau commit qua outbox hoặc cơ chế tương đương. Cần xác định database isolation và constraint thực tế; chỉ kiểm tra danh sách trong bộ nhớ không bảo vệ được hai worker đồng thời.

### 13.4. Câu hỏi về MVC và hợp đồng

- Form chỉ cần bookId hay người dùng được chọn chi nhánh?
- MemberId lấy từ principal hay được nhân viên truyền theo use case riêng?
- Trang sách hiển thị số người đang chờ hay vị trí chính xác của độc giả?
- Có lộ thông tin cá nhân của người khác trong hàng đợi không?
- API có trả trạng thái WAITING và READY_FOR_PICKUP không?
- Client cũ xử lý enum mới như thế nào?
- Validation error và business conflict được hiển thị ra sao?
- Có trang quản lý reservation cho nhân viên hay chỉ có thao tác phía độc giả?

### 13.5. Bằng chứng cần có trước khi duyệt

- State transition test cho Reservation.
- Test quyền đặt trước và hủy.
- Test không tạo reservation trùng.
- Integration test cho phân bổ và hết hạn.
- Concurrency test cho hai worker cùng xử lý một bản sao.
- Test notification chỉ được phát sau commit và consumer xử lý trùng an toàn.
- Migration/backfill test nếu thêm bảng hoặc trạng thái.
- MVC test cho form, principal, lỗi và ViewModel.
- Metric cho số reservation chờ, số reservation hết hạn và thời gian chờ.

Từ một yêu cầu giao diện, review đã phát hiện các quyết định domain, dữ liệu, transaction, bảo mật và vận hành cần thống nhất.

## 14. Một số tình huống thay đổi khác và câu hỏi trọng tâm

| Yêu cầu thay đổi | Câu hỏi trọng tâm |
|---|---|
| Thêm trường ISBN vào form sách | Trường này là input hay dữ liệu chỉ đọc? Có unique constraint và backfill không? |
| Thêm role thủ thư | Quyền được áp dụng trên mọi endpoint và tài nguyên hay chỉ ẩn nút? |
| Thêm trạng thái LOST | Đặt trạng thái trên BookCopy hay Loan? Chuyển tiếp nào hợp lệ? |
| Thêm bộ lọc tìm kiếm | Query có index, phân trang và sort ổn định không? |
| Mở REST API cho use case hiện tại | API có gọi cùng application use case và có contract riêng không? |
| Gửi email sau khi mượn | Email gửi sau commit thế nào, retry và chống gửi trùng ra sao? |
| Hỗ trợ nhiều chi nhánh | Tenant/branch được lấy từ đâu và query có giới hạn phạm vi không? |
| Chuyển báo cáo sang background job | Trạng thái job, retry, timeout và quyền tải file được quản lý thế nào? |
| Đổi cách tính hạn trả | Timezone, ngày nghỉ, dữ liệu lịch sử và policy version được xử lý ra sao? |
| Xóa đầu sách | Có bản sao/phiếu mượn tham chiếu không? Xóa mềm hay archive? |

Bảng này là điểm bắt đầu. Với mỗi thay đổi, cần hỏi thêm về actor, trạng thái, hợp đồng, dữ liệu cũ, lỗi và bằng chứng kiểm thử.

## 15. So sánh các phương án thiết kế trước khi quyết định

Không phải mọi yêu cầu đều có một giải pháp duy nhất. Review nên làm rõ trade-off và lý do chọn.

| Phương án | Khi có thể phù hợp | Rủi ro cần hỏi |
|---|---|---|
| Thêm nhánh vào Controller hiện tại | Một biến thể HTTP nhỏ, không thêm quy tắc dùng chung | Controller có phình và lặp logic không? |
| Tách Application Service | Use case có transaction hoặc được nhiều adapter gọi | Service có thực sự sở hữu một hành vi hay chỉ chuyển tiếp? |
| Dùng Form DTO riêng | Input có quyền ghi khác entity hoặc có validation riêng | Mapping có rõ và được test không? |
| Dùng ViewModel riêng | View cần dữ liệu format/derived state | Có tạo mapping dư thừa hoặc state trùng lặp không? |
| Dùng optimistic locking | Xung đột ít, có thể xử lý retry/conflict | Client có nhận biết dữ liệu đã thay đổi không? |
| Dùng pessimistic locking | Tranh chấp cao hoặc cần tuần tự hóa thao tác | Lock wait, deadlock và thời gian transaction ra sao? |
| Gửi message bất đồng bộ | Tác vụ không cần hoàn thành trong request | Retry, idempotency và quan sát backlog thế nào? |
| Thực hiện đồng bộ | Tác vụ nhanh và cần kết quả ngay | Request latency và rollback khi downstream lỗi ra sao? |

Một quyết định tốt ghi rõ vì sao phương án được chọn phù hợp với tải, độ phức tạp và yêu cầu vận hành hiện tại. Tránh chọn pattern chỉ vì nó phổ biến.

## 16. Cách phân loại phát hiện trong design review

Để review có thể hành động, hãy phân loại phát hiện:

- **Blocker:** Thiết kế vi phạm bất biến, quyền truy cập, tính toàn vẹn dữ liệu hoặc không đáp ứng tiêu chí bắt buộc.
- **High risk:** Có khả năng gây lỗi production đáng kể, mất dữ liệu, downtime hoặc phá vỡ client.
- **Follow-up:** Có thể triển khai an toàn nhưng cần ghi nhận việc cải thiện hoặc đo lường.
- **Suggestion:** Cải thiện readability, naming hoặc cấu trúc mà không chặn thay đổi.

Ví dụ:

| Phát hiện | Mức | Lý do |
|---|---|---|
| Controller nhận memberId tùy ý từ form và không kiểm tra quyền | Blocker | Có thể thao tác dưới danh tính người khác |
| Hai worker có thể phân bổ cùng một bản sao | Blocker | Vi phạm bất biến tồn kho |
| Migration xóa cột cũ cùng lúc code mới deploy | High risk | Phiên bản cũ có thể lỗi khi rollout |
| Query trang lịch sử chưa có index nhưng tải hiện tại nhỏ | Follow-up | Cần đo với dữ liệu thực tế |
| Tên method chưa thể hiện rõ nghiệp vụ | Suggestion | Khó đọc nhưng không làm sai hành vi |

Mức độ cần dựa trên tác động, khả năng xảy ra và phạm vi ảnh hưởng. Không biến mọi sở thích về code style thành blocker.

## 17. Mẫu ghi nhận một quyết định review

Có thể dùng mẫu ngắn sau trong pull request hoặc tài liệu thiết kế:

~~~text
Change request:
- Mã/tên:
- Actor và hành vi mới:
- Tiêu chí chấp nhận:
- Hành vi hiện tại phải giữ:

Affected flow:
- Route/Controller:
- Input contract:
- Application use case:
- Domain state/rules:
- Repository/schema:
- ViewModel/response:

Review questions:
- Responsibility/boundary:
- Contract compatibility:
- State and concurrency:
- Authentication/authorization:
- Transaction and migration:
- Errors and HTTP behavior:
- Performance:
- Tests:
- Observability and rollout:

Decisions:
- Accepted:
- Changed:
- Deferred:
- Rejected:

Risks and evidence:
- Blockers:
- High risks:
- Required tests:
- Migration/deployment evidence:
- Owner and follow-up date:
~~~

Mẫu này giúp người viết và reviewer nói về cùng một phạm vi. Không cần điền mọi dòng nếu thay đổi nhỏ; hãy đánh dấu “không áp dụng” khi đã xem xét và có lý do.

## 18. Checklist ngắn trước khi chấp nhận thay đổi

### Yêu cầu và phạm vi
- [ ] Actor, hành vi và tiêu chí chấp nhận đã rõ.
- [ ] Trường hợp biên, lỗi và yêu cầu chất lượng đã được xác định.
- [ ] Giả định chưa được xác nhận đã có owner.

### Kiến trúc MVC
- [ ] Route và HTTP method phù hợp.
- [ ] Controller giữ trách nhiệm HTTP.
- [ ] Application/domain bảo vệ use case và bất biến.
- [ ] View nhận dữ liệu trình bày phù hợp.
- [ ] Không có dependency ngược từ domain sang HTTP/View.

### Hợp đồng và dữ liệu
- [ ] Input chỉ chứa trường client được phép gửi.
- [ ] Response không lộ entity hoặc dữ liệu nội bộ.
- [ ] Tương thích client/API đã được xem xét.
- [ ] Migration, backfill, index và constraint đã được đánh giá.
- [ ] Transaction và concurrency có chiến lược rõ.

### Bảo mật và lỗi
- [ ] Authentication và authorization được kiểm tra ở server.
- [ ] CSRF/XSS/IDOR/mass assignment đã được xem xét.
- [ ] Lỗi validation, business và infrastructure có response phù hợp.
- [ ] Log không chứa bí mật hoặc dữ liệu không cần thiết.

### Kiểm thử và vận hành
- [ ] Có test cho bất biến và use case.
- [ ] Có MVC/security test cho endpoint thay đổi.
- [ ] Có integration/concurrency test khi dữ liệu tranh chấp.
- [ ] Có migration và regression test phù hợp.
- [ ] Có metric/log/trace và phương án rollout/rollback cần thiết.

Checklist không phải thủ tục ký duyệt máy móc. Mỗi mục cần một kết luận dựa trên rủi ro thực tế của thay đổi.

## 19. Những phản biện không hữu ích

Một số nhận xét nghe có vẻ nghiêm khắc nhưng không giúp cải thiện thiết kế:

- “Controller phải dưới 20 dòng.” Độ dài không chứng minh trách nhiệm đã đúng.
- “Mọi entity phải có Repository.” Abstraction cần xuất phát từ nhu cầu truy cập dữ liệu và ranh giới.
- “Phải dùng CQRS cho mọi màn hình.” Read/write separation có chi phí; chỉ dùng khi khác biệt đủ lớn.
- “Không được có logic trong Model.” Domain behavior thường cần nằm gần trạng thái mà nó bảo vệ.
- “Chỉ cần unit test.” Các vấn đề SQL, transaction, security filter và concurrency cần test đúng môi trường.
- “Đã ẩn nút nên người dùng không thể gọi.” Client có thể gửi HTTP request trực tiếp.
- “Migration chạy được trên máy tôi.” Cần xét dữ liệu lớn, khóa, phiên bản đang chạy và rollback.
- “Mock repository trả đúng kết quả nên query đúng.” Mock không chạy SQL, constraint hoặc lock.

Phản biện tốt phải chỉ ra tình huống có thể thất bại, tầng chịu trách nhiệm, tác động và bằng chứng để xác minh.

## 20. Kết luận

Câu hỏi phản biện trong design review cần bắt đầu từ yêu cầu thay đổi và lần theo toàn bộ luồng MVC. Hãy làm rõ actor, tiêu chí chấp nhận và yêu cầu chất lượng; xác định route, Controller, hợp đồng input/output, application use case, domain state, repository và ViewModel bị ảnh hưởng; sau đó xem xét quyền truy cập, transaction, migration, lỗi, hiệu năng, kiểm thử và vận hành.

Một review có giá trị không chỉ nói “thiết kế này chưa tốt”. Nó chỉ ra giả định nào chưa rõ, bất biến nào có thể bị phá vỡ, client hoặc dữ liệu nào bị ảnh hưởng, và bằng chứng nào cần có để chấp nhận thay đổi. Khi quyết định được ghi rõ cùng rủi ro và người chịu trách nhiệm, nhóm có thể thay đổi ứng dụng MVC một cách có kiểm soát mà không biến mỗi yêu cầu mới thành một lần viết lại kiến trúc.
