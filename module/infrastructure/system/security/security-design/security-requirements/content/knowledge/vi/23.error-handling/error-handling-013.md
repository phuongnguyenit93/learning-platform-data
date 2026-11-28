# Lỗi validation và business error

## 1. Xử lý lỗi là một phần của yêu cầu bảo mật

Một request có thể không thực hiện được vì nhiều lý do: dữ liệu thiếu trường, giá trị sai miền, người gọi không có quyền, trạng thái tài nguyên không cho phép hoặc hệ thống không xác định được kết quả. Những trường hợp này cần được phân loại để phản hồi đúng, duy trì trạng thái dữ liệu và hướng dẫn bước tiếp theo phù hợp.

Ví dụ, số chỗ đặt bằng -1 là vấn đề của dữ liệu yêu cầu. Một yêu cầu đặt một chỗ đúng định dạng nhưng phiên học đã đầy là một kết quả nghiệp vụ theo trạng thái hiện tại. Dịch vụ kiểm tra quyền bị timeout lại không chứng minh người gọi có quyền hoặc phiên học đã hết chỗ.

Trong module yêu cầu bảo mật, contract cần làm rõ:

- Điều kiện nào bị từ chối và thành phần nào thực hiện kiểm tra.
- Người gọi được biết thông tin gì về lỗi.
- Trạng thái nghiệp vụ có thay đổi hay không.
- Khi nào có thể sửa dữ liệu, tải lại trạng thái hoặc thử lại.
- Cách duy trì quy tắc khi có request đồng thời, retry hoặc lỗi hạ tầng.
- Bằng chứng nào đủ để nghiệm thu hành vi đó.

Tên “validation” và “business error” có thể được các nhóm dùng khác nhau. Bài này dùng một quy ước để thiết kế yêu cầu, không áp đặt mọi thư viện phải có cùng hệ thống exception.

Mục tiêu quan trọng là ranh giới tin cậy, ngữ nghĩa lỗi và trạng thái sau xử lý phải rõ. Không nên để tên một exception quyết định toàn bộ phản hồi công khai.

## 2. Quy ước phân loại lỗi

### 2.1. Validation gồm cấu trúc và ý nghĩa đầu vào

Validation kiểm tra dữ liệu theo contract đầu vào, ví dụ:

- Request có parse được theo định dạng đã chấp nhận không.
- Trường bắt buộc có mặt, đúng kiểu và đúng miền giá trị không.
- Chuỗi, số phần tử, độ sâu và kích thước có nằm trong giới hạn không.
- Các trường có quan hệ hợp lệ như ngày kết thúc không trước ngày bắt đầu không.
- Giá trị có thuộc enum hoặc tập định dạng được phép không.

Không giới hạn validation ở một regex hoặc annotation. Một quy tắc liên trường có thể cần logic riêng; parser cũng cần giới hạn trước khi một validator có cơ hội chạy.

### 2.2. Business error gắn với quy tắc và trạng thái nghiệp vụ

Trong bài, business error là kết quả được dự kiến khi một yêu cầu đã đủ để đánh giá nhưng không thể được chấp nhận theo quy tắc nghiệp vụ.

Ví dụ: phiên học đã đóng đăng ký, không đủ chỗ, bản ghi đã ở trạng thái không được hủy hoặc người đặt đã có một lượt đặt đang hoạt động theo policy.

Business error có thể xuất hiện sau validation ban đầu vì trạng thái thay đổi hoặc một thao tác đồng thời thắng trước. Nó không nhất thiết là lỗi lập trình.

### 2.3. Những nhóm không được đánh đồng

| Nhóm | Ví dụ | Hướng xử lý cần đặc tả |
|---|---|---|
| Lỗi định dạng hoặc framing | JSON không hợp lệ | Từ chối theo contract, không làm lộ parser internals |
| Validation giá trị | Số chỗ ngoài khoảng cho phép | Chỉ ra trường công khai và quy tắc có thể sửa |
| Authentication hoặc authorization | Thiếu credential, truy cập tenant khác | Áp dụng policy bảo mật, hạn chế tiết lộ tài nguyên |
| Business error | Không đủ chỗ tại thời điểm đặt | Phản hồi theo mã nghiệp vụ và trạng thái đã xác minh |
| Lỗi kỹ thuật | Database hoặc dependency không khả dụng | Không giả thành lỗi dữ liệu của client |
| Kết quả chưa xác định | Đã gửi thao tác nhưng mất phản hồi | Đối soát trước khi kết luận thất bại hoặc retry |

Một kiểm tra “ID đúng định dạng” không chứng minh người gọi được thao tác trên đối tượng đó. Input validation cũng không thay thế query có tham số, output encoding hoặc các kiểm soát chuyên biệt theo nơi dữ liệu được sử dụng.

## 3. Đặc tả validation ở ranh giới tin cậy

### 3.1. Giới hạn trước và trong quá trình parse

Một request quá lớn hoặc lồng quá sâu có thể tiêu tốn tài nguyên trước khi kiểm tra schema hoàn tất. Cần giới hạn kích thước, độ sâu, số phần tử và cách parse phù hợp với loại endpoint.

OWASP nhấn mạnh việc áp dụng giới hạn request và parser trước các kiểm tra sau parse. Xem [OWASP Input Validation Cheat Sheet — Parse Safely, Then Validate](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html#parse-safely-then-validate).

Cần xác định giới hạn áp dụng cho dạng dữ liệu nào: byte nhận trên mạng, nội dung sau giải nén hoặc giá trị đã parse. Không chỉ kiểm tra header kích thước do client khai rồi bỏ qua lượng dữ liệu thực tế.

### 3.2. Schema và miền giá trị phải rõ

| Thuộc tính | Quyết định cần đặc tả |
|---|---|
| Bắt buộc | Khác nhau thế nào giữa thiếu trường, null và chuỗi rỗng? |
| Kiểu dữ liệu | Có chấp nhận chuỗi “3” thay cho số 3 không? |
| Số | Kiểu nguyên hay thập phân, miền giá trị, scale và xử lý tràn? |
| Chuỗi | Độ dài tính theo byte hay ký tự, có chuẩn hóa không? |
| Danh sách | Số phần tử tối đa, phần tử trùng và phần tử null xử lý ra sao? |
| Enum | Giá trị lạ bị từ chối hay ánh xạ theo quy tắc nào? |
| Trường không biết | Từ chối hay bỏ qua theo schema và phiên bản API? |
| Quan hệ liên trường | Điều kiện giữa các trường và lỗi trả về thuộc phạm vi nào? |

Nếu cần chuẩn hóa, hãy xác định phép biến đổi và thực hiện nhất quán trước khi đánh giá giá trị sẽ được sử dụng. Không tự trim hoặc đổi hoa thường mọi loại dữ liệu, đặc biệt với secret hoặc định danh có ngữ nghĩa phân biệt.

Không chuyển kiểu theo cách làm mất thông tin rồi mới kiểm tra. Ví dụ, một số rất lớn không được tràn thành giá trị nhỏ hợp lệ sau khi ép kiểu.

### 3.3. Máy chủ phải thực hiện kiểm tra cần thiết

Validation ở giao diện giúp người dùng sửa dữ liệu sớm. Các đường API, import, tác vụ nền hoặc message từ hệ thống khác vẫn cần kiểm tra theo ranh giới tin cậy và contract tương ứng.

Không dựa vào thuộc tính form hoặc kiểu DTO để kết luận mọi đầu vào đã an toàn. Cần kiểm tra cấu hình thực tế của parser, binder và validator.

Với trường do máy chủ quản lý như tenant, chủ sở hữu, giá hoặc trạng thái phê duyệt, phải xác định cách xử lý nếu client gửi thêm. Trong ví dụ của bài, schema chặt chẽ từ chối các trường ngoài danh sách cho phép; dữ liệu cấp quyền được lấy từ nguồn đáng tin.

## 4. Business error và quyền truy cập thông tin

### 4.1. Trình tự kiểm tra có ảnh hưởng bảo mật

Một luồng minh họa:

```text
Giới hạn request và nhận diện giao thức
    → xác thực theo endpoint
    → parse và kiểm tra schema
    → xác định đối tượng trong phạm vi được phép
    → kiểm tra quy tắc nghiệp vụ với trạng thái phù hợp
    → thực hiện thay đổi với cơ chế nhất quán
    → phản hồi theo kết quả đã xác minh
```

Thứ tự cụ thể phụ thuộc kiến trúc; các giới hạn bảo vệ parser cần được áp dụng đủ sớm. Điều phải giữ là kiểm tra dữ liệu không được thay thế authorization, còn chi tiết nghiệp vụ không được trả cho người chưa có quyền biết.

Ví dụ, người ngoài tenant không nên biết một phiên học riêng còn bao nhiêu chỗ thông qua sự khác nhau giữa “đã đầy”, “đã đóng” và “không tìm thấy”.

### 4.2. Lỗi có thể trở thành kênh dò thông tin

Một thông báo “email đã có tài khoản” có thể tiết lộ danh tính trong luồng không được phép. Một lỗi trùng mã nội bộ cũng có thể làm lộ cấu trúc hoặc dữ liệu của tổ chức khác.

Dự án cần chọn mức chi tiết theo trường hợp. Với người đã có quyền quản lý một tài nguyên, thông tin xung đột cụ thể có thể hữu ích. Với endpoint công khai nhạy cảm, phản hồi cần được thiết kế để hạn chế khả năng phân biệt ngoài quyền.

Cần xem cả status, mã lỗi, nội dung, header, kích thước và hành vi thời gian. Cùng một câu thông báo không tự bảo đảm không còn kênh phân biệt.

### 4.3. Không dùng dependency lỗi để suy ra quyết định nghiệp vụ

Nếu hệ thống không đọc được trạng thái lớp học, không được tự trả “lớp đã đầy” để đơn giản hóa client. Nếu không kiểm tra được quyền, không chuyển sang nhánh cho phép vì dữ liệu đầu vào đúng schema.

Thông điệp cần phân biệt điều kiện nghiệp vụ không đạt với việc chưa đủ bằng chứng để đánh giá. Nhóm vận hành cũng cần biết loại lỗi thật để không sửa nhầm dữ liệu người dùng.

## 5. Contract phản hồi API và thông điệp cho người dùng

### 5.1. Ánh xạ HTTP cần dựa trên ngữ nghĩa

Một mapping minh họa:

| Tình huống | Mã HTTP có thể chọn trong contract |
|---|---|
| JSON hoặc request không hợp lệ về cú pháp | 400 |
| Nội dung vượt giới hạn được chấp nhận | 413 |
| Định dạng nội dung không được hỗ trợ | 415 |
| Nội dung đúng cú pháp nhưng chỉ dẫn không xử lý được theo quy tắc đã định | 422 |
| Request xung đột với trạng thái tài nguyên hiện tại | 409 |
| Điều kiện trong request header như If-Match không đạt | 412 |
| Lỗi nội bộ không dự kiến hoặc dịch vụ không thể phục vụ | 500 hoặc mã 5xx phù hợp |

RFC 9110 định nghĩa ngữ nghĩa 400, 409, 412, 413, 415 và 422; đặc biệt 412 gắn với precondition trong header và 409 gắn với xung đột trạng thái. Xem [RFC 9110, mục 15.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5).

Không có quy tắc chung rằng mọi validation phải là 400 hoặc mọi business error phải là 409. Dự án cần chọn và tài liệu hóa theo tình huống, đồng thời giữ nhất quán giữa HTTP status thực tế và trường status nếu có trong body.

Authentication và authorization có contract riêng. Không đổi chúng thành lỗi field “ID không hợp lệ” nếu việc đó làm sai ngữ nghĩa hoặc làm mất kiểm soát bảo mật.

### 5.2. Dùng mã ổn định và chi tiết có thể sửa

Response nên giúp client nhận diện nhóm lỗi bằng mã hoặc loại lỗi ổn định. Thông điệp phục vụ con người có thể dịch, nhưng automation không nên phụ thuộc vào việc parse một câu tiếng Việt.

Với field công khai, có thể chỉ ra đường dẫn và quy tắc bị vi phạm. Không trả tên bảng, cột nội bộ, regex quá phức tạp, SQL hoặc stack trace.

Giá trị đầu vào bị từ chối không nhất thiết cần xuất hiện lại. Với mật khẩu, token hoặc dữ liệu nhạy cảm, việc phản chiếu giá trị có thể tạo thêm rò rỉ ở UI, log hoặc công cụ hỗ trợ.

### 5.3. Giới hạn danh sách lỗi

Tổng hợp nhiều lỗi field có thể giúp người dùng sửa một lần, nhưng cần giới hạn số lỗi và kích thước response. Không kiểm tra mọi điều kiện đắt tiền chỉ để tạo một danh sách đầy đủ ngoài nhu cầu.

Cần xác định lỗi liên trường hoặc nghiệp vụ được trả ở đâu. Không ép mọi business error vào một field tùy tiện khiến client hiểu rằng chỉ sửa field đó là sẽ thành công.

Nếu đã trả ít hơn tổng số lỗi vì giới hạn, có thể cung cấp dấu hiệu phù hợp theo schema. Không để danh sách lỗi trở thành cách liệt kê tài nguyên hoặc quy tắc ngoài quyền.

## 6. Ví dụ phản hồi validation và business error

### 6.1. Bối cảnh giả lập

Dịch vụ cho phép người dùng đặt chỗ trong một phiên học thuộc tenant mà họ được phép truy cập:

```json
{
  "sessionId": "session-example-12",
  "seatCount": 2,
  "note": "Nhóm học cuối tuần"
}
```

Trong ví dụ:

- seatCount phải là số nguyên từ 1 đến 4.
- note là trường tùy chọn, có giới hạn độ dài đã định.
- Mỗi người đặt chỉ có tối đa một reservation đang hoạt động trên cùng phiên trong tenant.
- Tenant và người đặt lấy từ ngữ cảnh máy chủ.
- Phiên phải mở đăng ký và còn đủ chỗ tại thời điểm thay đổi được chấp nhận.

Đây là quy tắc của ứng dụng minh họa, không phải tiêu chuẩn áp dụng cho mọi hệ thống.

### 6.2. Phản hồi cho seatCount ngoài miền

Giả sử JSON đúng cú pháp nhưng seatCount bằng 0. API trong ví dụ chọn 422:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
```

```json
{
  "type": "https://api.example.test/problems/validation-failed",
  "title": "Dữ liệu yêu cầu chưa hợp lệ",
  "status": 422,
  "detail": "Kiểm tra các trường được chỉ ra.",
  "instance": "urn:example:problem:request-83",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "pointer": "/seatCount",
      "code": "OUT_OF_RANGE",
      "message": "Số chỗ phải từ 1 đến 4."
    }
  ]
}
```

RFC 9457 cho phép các trường mở rộng trong Problem Details. `code`, `errors` và các trường bên trong mảng là contract do ví dụ định nghĩa, không phải bộ trường bắt buộc cho mọi API. Xem [RFC 9457, mục 3](https://www.rfc-editor.org/rfc/rfc9457.html#section-3).

Các URL và ID là giá trị giả lập. Instance hoặc request reference không tự cấp quyền xem bằng chứng nội bộ.

### 6.3. Phản hồi cho trạng thái hết chỗ

Nếu yêu cầu hợp lệ nhưng không đủ chỗ, sau khi đã kiểm tra quyền truy cập, API có thể chọn 409:

```json
{
  "type": "https://api.example.test/problems/session-capacity-conflict",
  "title": "Không thể đặt chỗ với trạng thái hiện tại",
  "status": 409,
  "detail": "Phiên học không còn đủ chỗ cho yêu cầu này.",
  "instance": "urn:example:problem:request-84",
  "code": "SESSION_CAPACITY_CONFLICT"
}
```

HTTP status thực tế của phản hồi này cũng là 409. Không trả chi tiết về người đã đặt hoặc tenant khác. Client có thể đề nghị tải lại trạng thái được phép hoặc chọn phiên khác, thay vì tự retry cùng request vô hạn.

## 7. Quy tắc nghiệp vụ phải được bảo vệ tại thời điểm thay đổi

### 7.1. Kiểm tra trước chưa đủ khi trạng thái có thể đổi

Giả sử phiên chỉ còn một chỗ. Hai request đều đọc thấy còn một chỗ rồi cùng tạo reservation. Mỗi request riêng lẻ đã “validate thành công”, nhưng kết quả tổng thể có thể vượt sức chứa.

Một yêu cầu kiểm chứng được cần mô tả invariant:

> Tổng số chỗ đã được giữ theo trạng thái có hiệu lực không vượt sức chứa; một yêu cầu bị từ chối không để lại thay đổi nghiệp vụ một phần ngoài contract.

Cơ chế thực thi có thể là khóa, cập nhật có điều kiện, kiểm soát phiên bản, isolation phù hợp hoặc thiết kế khác. Phải chọn theo nơi trạng thái được quản lý và kiểm thử tương tranh thực tế.

### 7.2. Transaction và ràng buộc tại kho dữ liệu

Một luồng minh họa cho trường hợp cùng database:

```text
begin transaction

    đọc và khóa phiên trong tenant được phép theo thiết kế
    xác minh trạng thái mở đăng ký
    xác minh còn đủ chỗ
    xác minh điều kiện reservation đang hoạt động

    cập nhật số chỗ
    tạo reservation
    ghi outbox cho thông báo sau commit nếu có

commit

chỉ trả thành công khi biết giao dịch đã commit theo contract
```

Đây là mã giả để giải thích trách nhiệm. Nó không tự giải quyết mọi race của authorization hoặc các dependency ngoài transaction; yêu cầu thực tế cần nêu điểm kiểm tra và độ mới trạng thái cho từng phần.

Ràng buộc unique, not-null, check hoặc quan hệ tham chiếu có thể bảo vệ các quy tắc mà database hỗ trợ. PostgreSQL mô tả cách constraint giới hạn giá trị và tính duy nhất tại kho dữ liệu. Xem [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).

Một kiểm tra “chưa tồn tại” ở ứng dụng không tự thay thế ràng buộc chống trùng phù hợp. Với quy tắc “một reservation đang hoạt động”, thiết kế phải biểu diễn đúng trạng thái và phạm vi tenant; không áp một unique không phù hợp rồi vô tình cấm cả lịch sử hoặc thao tác hợp lệ khác.

### 7.3. Ánh xạ lỗi constraint phải có kiểm soát

Một constraint đã biết có thể tương ứng với một xung đột nghiệp vụ đã định. Mapping cần dựa vào thông tin ổn định và được kiểm soát của hệ thống, không parse nguyên câu lỗi từ database để trả ra client.

Cần hoàn tất rollback theo cơ chế giao dịch trước khi trả một kết quả từ chối nếu transaction không còn hợp lệ. Không catch lỗi rồi tiếp tục ghi trong một transaction đã bị đánh dấu thất bại.

Không ánh xạ mọi exception database thành “đã tồn tại” hoặc “không đủ chỗ”. Mất kết nối, lỗi schema và lỗi quyền truy cập kho cần được phân loại kỹ thuật. Những lỗi chưa biết phải đi qua nhánh an toàn thay vì bị che thành một business error quen thuộc.

### 7.4. Tác động ngoài transaction

Email, webhook, request tới đối tác hoặc sự kiện đã phân phối có thể không rollback cùng database. Nếu lỗi validation hoặc business error xảy ra sau khi đã gửi, hệ thống có thể đã tạo tác động ngoài ý định.

Cần quyết định ranh giới commit, thứ tự thực hiện, outbox hoặc cơ chế điều phối thích hợp. Nếu sản phẩm chấp nhận trạng thái một phần, phải có trạng thái và quy trình xử lý riêng; không thông báo “không có thay đổi nào” khi điều đó không đúng.

## 8. Retry, idempotency và kết quả chưa xác định

### 8.1. Hướng dẫn theo loại lỗi

| Kết quả | Hành động phù hợp trong ví dụ | Điều không nên tự suy ra |
|---|---|---|
| Input ngoài miền | Sửa dữ liệu rồi gửi lại | Gửi lại cùng giá trị sẽ tự thành công |
| Xung đột trạng thái | Đọc lại trạng thái trong quyền hoặc chọn phương án khác | Lặp nhanh vô hạn là cách giải quyết |
| Precondition header không đạt | Lấy phiên bản mới và xử lý xung đột theo contract | Bỏ precondition để ghi đè mọi thay đổi |
| Không có quyền | Thực hiện quy trình cấp quyền hoặc xác thực hợp lệ nếu có | Thay ID hoặc tenant để tìm nhánh được cho phép |
| Dependency lỗi trước tác động đã xác minh | Theo policy retry có giới hạn | Mọi lỗi 5xx đều an toàn để phát lại |
| Đã gửi thao tác nhưng mất kết quả | Đối soát hoặc dùng idempotency theo contract | Tạo một thao tác mới để thay thế ngay |

Thời điểm nhận lỗi và trạng thái thực thi là hai thông tin khác nhau. Timeout sau commit không được diễn giải thành request chắc chắn chưa có tác động.

### 8.2. Contract idempotency cần rõ phạm vi

Với thao tác tạo reservation, dự án có thể dùng cơ chế idempotency. Cần xác định phạm vi theo người gọi, tenant và loại thao tác; cách ràng buộc key với ý định yêu cầu; thời hạn giữ; và kết quả nào được ghi nhận.

Nếu cùng key được gửi lại với nội dung khác, hệ thống phải xử lý theo một quy tắc rõ ràng, thay vì âm thầm thực hiện một lệnh mới. Thông báo xung đột không được phản chiếu toàn bộ nội dung cũ nếu ngoài nhu cầu hoặc quyền.

Cần kiểm tra request đồng thời dùng cùng key. “Có key trong header” chưa chứng minh không tạo tác động lặp nếu bước giữ key và thực hiện nghiệp vụ không được phối hợp đúng.

Đối với lỗi validation hoặc từ chối nghiệp vụ, contract phải nói việc sửa dữ liệu ảnh hưởng thế nào tới key cũ. Client cần biết khi nào đang sửa một ý định mới và khi nào đang đối soát kết quả của thao tác cũ chưa biết.

### 8.3. Không thay đổi quyết định bảo mật khi xử lý retry

Retry vẫn phải tuân thủ kiểm tra quyền, giới hạn tài nguyên và quy tắc hiện hành theo contract. Một lỗi trước đó không tạo ra quyền bỏ qua authorization hoặc constraint ở lần sau.

Nếu một quy trình dùng lại kết quả đã ghi nhận cho cùng thao tác, việc đọc kết quả đó cũng cần authorization. Không cho người có key hoặc request ID đọc reservation của chủ thể khác.

## 9. Tổ chức error model và logging

### 9.1. Chuẩn hóa ở ranh giới phù hợp

Một thiết kế có thể tách:

- Lỗi parse hoặc validation theo contract input.
- Kết quả nghiệp vụ được định danh rõ.
- Từ chối authentication và authorization.
- Lỗi kỹ thuật hoặc kết quả chưa xác định.
- Bộ ánh xạ sang response công khai, event operator và audit theo audience.

Không nhất thiết phải biểu diễn mọi business error bằng exception. Có thể dùng một kiểu kết quả có cấu trúc; điều quan trọng là caller không bỏ qua kết quả và trạng thái dữ liệu được bảo vệ.

Catch-all ở ranh giới là lớp bảo vệ cuối cho lỗi bất ngờ. Nó không thay thế việc phân loại các trường hợp đã biết hoặc được phép trả chi tiết.

### 9.2. Không để mapping làm sai thực tế

Một lỗi serialization khi tạo response có thể xảy ra sau commit. Nếu handler chỉ trả “validation failed” hoặc “không tạo reservation”, client sẽ hiểu sai kết quả.

Cần xác định handler biết gì về trạng thái giao dịch. Lỗi ở bước trả kết quả có thể cần reference để đối soát; không tự rollback một điều đã commit bằng cách đổi nội dung thông báo.

Tương tự, một response HTTP thành công với body chứa `error` có thể gây hiểu nhầm trong API đã chọn dùng HTTP status để phân biệt lỗi. Contract phải nhất quán với mô hình giao tiếp của dịch vụ.

### 9.3. Ghi đủ bằng chứng và hạn chế dữ liệu

Event vận hành có thể gồm mã lỗi, loại hành động, tenant reference được phép, request reference, nhóm kiểm tra và trạng thái tác vụ. Không cần ghi raw body hoặc mọi giá trị field bị từ chối.

Thông báo validator hoặc exception có thể chứa input, tên constraint, SQL hoặc chi tiết nội bộ. Phải áp dụng quy tắc trích xuất và biểu diễn theo audience trước khi gửi tới log, trace hoặc công cụ hỗ trợ.

Một lỗi nhập sai thông thường không tự là sự cố bảo mật cần gọi người trực. Các mẫu dò tài nguyên, thao tác vượt quyền hoặc lượng lỗi bất thường cần policy phát hiện riêng. Giữ được phân loại giúp tránh vừa che sự cố thật vừa tạo nhiễu vận hành.

## 10. Giới hạn tài nguyên và các luồng phức tạp

### 10.1. Kiểm tra đắt tiền cần có giới hạn

Regex có thể tốn thời gian với một số đầu vào. Kiểm tra tồn tại qua dependency, đọc nhiều đối tượng hoặc xác minh tệp cũng có thể tạo tải lớn.

Cần giới hạn kích thước trước kiểm tra đắt, số phần tử, số lời gọi ngoài, thời gian thực thi và tổng lỗi trả về. Việc một request cuối cùng bị trả 4xx không có nghĩa nó không thể làm cạn tài nguyên.

Kiểm tra tồn tại tài nguyên trong validation cũng phải tuân thủ phạm vi quyền. Không dùng một API validation công khai như công cụ truy vấn mọi ID trong hệ thống.

### 10.2. Bulk request và lỗi từng phần

Nếu API hỗ trợ nhiều phần tử, phải chọn contract: tất cả cùng thành công hoặc thất bại; hay trả kết quả từng mục với thay đổi một phần được quản lý.

Cần nêu authorization của từng mục, quan hệ giữa các mục, thứ tự, rollback, retry và hạn mức. Một mục sai quyền không được làm lộ chi tiết về tài nguyên ngoài phạm vi qua danh sách lỗi.

Nếu đã xử lý một số mục, response không được khiến client tưởng toàn lô chưa có tác động. Idempotency và đối soát cần đủ chi tiết để tránh tạo lại các mục đã thành công.

### 10.3. Nhiều kênh phải giữ cùng invariant

Giao diện web, API di động, import và worker có thể khác biểu diễn lỗi nhưng phải bảo vệ cùng quy tắc nghiệp vụ cốt lõi. Không chỉ sửa validator ở controller rồi để import ghi thẳng dữ liệu sai.

Khi một kênh được phép có ngoại lệ nghiệp vụ, ngoại lệ cần quyền và policy rõ. Không để tên “internal job” trở thành lý do mặc định bỏ qua kiểm tra.

## 11. Ví dụ yêu cầu đo được và ma trận kiểm chứng

### 11.1. Giả định của dịch vụ đặt chỗ

Dự án giả lập chọn:

- Chỉ chấp nhận JSON theo schema đã công bố; trường ngoài danh sách được từ chối.
- Body tối đa 64 KiB sau giải mã nội dung theo cấu hình endpoint; parser có giới hạn độ sâu 8 và số phần tử theo schema.
- seatCount là số nguyên 1–4; note tối đa 300 ký tự Unicode theo quy tắc đếm đã thống nhất.
- Tối đa 20 lỗi field được trả về; response lỗi không quá 8 KiB UTF-8.
- Kiểm tra đầu vào không hợp lệ không tạo reservation, giữ chỗ hoặc thông báo nghiệp vụ ngoài contract.
- Hai request đồng thời cho chỗ cuối không thể cùng tạo reservation vượt sức chứa.
- Mỗi loại lỗi công khai có mã ổn định, HTTP mapping, schema và chính sách tiết lộ được ghi trong danh mục.

**Các con số là giả định minh họa, không phải giới hạn bắt buộc từ OWASP hoặc HTTP.** Với nội dung nén, proxy và parser phải có giới hạn phù hợp để tránh tiêu tốn tài nguyên trước khi áp dụng giới hạn sau giải mã.

### 11.2. Ma trận yêu cầu và bằng chứng

| Mã | Rủi ro | Yêu cầu cụ thể | Bằng chứng nghiệm thu |
|---|---|---|---|
| VB-01 | Vượt kiểm tra bằng cách gọi API trực tiếp | Máy chủ áp dụng schema và miền giá trị trên mọi kênh thuộc phạm vi | Bỏ validation giao diện rồi gửi thiếu trường, sai kiểu và giá trị biên; không tạo thay đổi ngoài contract |
| VB-02 | Làm cạn tài nguyên trước validator | Giới hạn body, parser, số phần tử và kiểm tra đắt | Request quá 64 KiB, lồng quá sâu và danh sách quá lớn bị xử lý theo giới hạn tại đúng lớp |
| VB-03 | Cấp quyền qua dữ liệu client | Tenant, actor và trường quản trị không lấy làm căn cứ từ payload tự khai | Chèn owner, tenant hoặc trạng thái phê duyệt không mở rộng quyền; schema xử lý đúng policy |
| VB-04 | Dò tài nguyên qua business error | Kiểm tra phạm vi trước khi trả chi tiết nghiệp vụ | Người ngoài tenant không suy ra sức chứa, trạng thái hoặc người đặt qua response thuộc các ca đã đặc tả |
| VB-05 | Vượt sức chứa khi đồng thời | Kiểm tra và thay đổi phối hợp để giữ invariant | Hai người hợp lệ cùng đặt chỗ cuối: không quá một reservation thành công; số chỗ và trạng thái khớp |
| VB-06 | Tạo reservation trùng | Có cơ chế bảo vệ tính duy nhất phù hợp trạng thái và phạm vi | Nhiều request đồng thời cùng chủ thể và phiên không tạo quá số reservation hoạt động cho phép |
| VB-07 | Tác động một phần khi bị từ chối | Rollback hoặc trạng thái một phần đúng contract; tác động ngoài transaction được điều phối | Lỗi sau bước giữ chỗ không để lại dữ liệu sai; email hoặc event không khẳng định thành công chưa commit |
| VB-08 | Lỗi kỹ thuật bị che thành lỗi input | Chỉ map các trường hợp đã biết; lỗi khác đi qua nhánh kỹ thuật an toàn | Mất database, lỗi schema và timeout không bị trả thành “seatCount sai” hoặc “đã tồn tại” |
| VB-09 | Rò rỉ input và chi tiết nội bộ | Response và telemetry chỉ chứa trường được phép | Dữ liệu thử có secret, chuỗi HTML và SQL-like không được phản chiếu raw ở các kênh ngoài quyền |
| VB-10 | Client diễn giải sai lỗi | Mã lỗi, HTTP status và schema nhất quán; thông điệp dịch không đổi nghĩa máy | Kiểm tra các mapping, ngôn ngữ, lỗi fallback và code chưa biết mà không parse chuỗi mô tả |
| VB-11 | Retry gây tác động lặp | Idempotency và xử lý UNKNOWN có contract, authorization và đối soát | Mất phản hồi sau commit, gửi lại cùng key và gửi nội dung khác cùng key không tạo tác động ngoài quy tắc |
| VB-12 | Bulk hoặc import bỏ invariant | Các kênh giữ cùng quy tắc; lỗi từng phần thể hiện đúng tác động | Thử lỗi ở một mục trong bulk và đầu vào import; trạng thái, quyền và kết quả từng phần đúng contract |

Mỗi yêu cầu cần chỉ ra nơi thực thi trong kiến trúc, người sở hữu và bằng chứng phải lưu. Các phép kiểm tra phải quan sát cả response lẫn trạng thái nghiệp vụ.

### 11.3. Tiêu chí chấp nhận cho validation

```gherkin
Given nguoi dung duoc phep truy cap phien hoc
When request JSON dung cu phap co seatCount bang 0
Then API tra HTTP 422 theo contract cua vi du
And code la VALIDATION_FAILED
And loi field tro toi /seatCount voi code OUT_OF_RANGE
And khong tao reservation, giu cho hoac thong bao thanh cong
And response khong phan chieu raw payload
```

### 11.4. Tiêu chí chấp nhận cho đồng thời

```gherkin
Given phien hoc dang mo va chi con 1 cho
And hai nguoi dat khac nhau deu du quyen
When hai request hop le cung yeu cau 1 cho dong thoi
Then co toi da 1 reservation moi duoc commit
And request khong duoc chap nhan nhan ket qua xung dot theo contract
And suc chua khong bi am hoac vuot gioi han
And khong co tac dong thanh cong cho request da bi tu choi
```

Đây là tiêu chí để xây dựng kiểm thử cho dự án, không phải tuyên bố một hệ thống thực tế đã vượt qua các kiểm tra.

## 12. Quản lý thay đổi và các lỗi đặc tả phổ biến

### 12.1. Kiểm tra các đường biên có ý nghĩa

Dữ liệu thử nên bao phủ thiếu trường, null, rỗng, giá trị biên, tràn số, Unicode, phần tử trùng, trường lạ, quan hệ liên trường và kích thước vượt giới hạn.

Cần thêm các ca trạng thái đổi giữa đọc và ghi, request lặp, rollback, lỗi sau commit, dependency không khả dụng và người dùng ngoài quyền. Chỉ kiểm tra một request sai và một request đúng chưa xác minh được phần bảo mật quan trọng.

Khi quan sát log hoặc báo cáo kiểm thử, tránh lưu dữ liệu nhạy cảm thật. Có thể dùng giá trị giả lập có dấu hiệu nhận biết để kiểm tra rò rỉ theo phạm vi.

### 12.2. Validation và error contract phải đi theo phiên bản

Đổi miền giá trị, quy tắc chuẩn hóa, trường bắt buộc hoặc trạng thái nghiệp vụ có thể làm client hợp lệ trước đó bị từ chối. Cần đánh giá tương thích, cập nhật schema, tài liệu, thông điệp và phép kiểm tra.

Nếu thay transaction boundary, một lỗi từng có nghĩa “chưa có tác động” có thể xảy ra sau commit. Mapping lỗi và hướng dẫn retry phải được đánh giá lại theo thực tế mới.

Không giữ một mã cũ rồi đổi nghĩa âm thầm. Client cần có cách xử lý mã chưa biết an toàn mà không suy ra thành công hoặc tự phát lại một thao tác có tác động.

### 12.3. Những câu đặc tả cần viết rõ hơn

| Câu còn mơ hồ | Điều cần bổ sung |
|---|---|
| “Validate tất cả input” | Schema, miền giá trị, chuẩn hóa, giới hạn parser và ranh giới tin cậy |
| “Business error trả 400” | Ngữ nghĩa từng trường hợp, mã ổn định, status và hướng sửa hoặc đối soát |
| “ID hợp lệ thì xử lý” | Quyền trên đối tượng, tenant và điều kiện nghiệp vụ |
| “Kiểm tra còn chỗ trước khi ghi” | Cơ chế nhất quán và invariant dưới request đồng thời |
| “Catch lỗi database thành đã tồn tại” | Constraint đã biết, rollback và nhánh lỗi kỹ thuật chưa phân loại |
| “Không thành công thì thử lại” | Trạng thái tác động, idempotency và kết quả chưa xác định |
| “Trả đầy đủ lỗi field” | Giới hạn số lỗi, quyền biết thông tin và dữ liệu bị cấm phản chiếu |
| “Dữ liệu sai không ảnh hưởng hệ thống” | Tác động nghiệp vụ, tài nguyên parser, dependency, log và các bản sao |

Một đặc tả cho lỗi validation và business error cần nối được **contract đầu vào → quyền truy cập → quy tắc và trạng thái nghiệp vụ → bảo vệ tính nhất quán → phản hồi theo audience → retry và đối soát → bằng chứng kiểm thử**. Chuỗi này giúp hệ thống từ chối đúng điều kiện mà vẫn giữ dữ liệu và ranh giới bảo mật đúng như đã yêu cầu.
