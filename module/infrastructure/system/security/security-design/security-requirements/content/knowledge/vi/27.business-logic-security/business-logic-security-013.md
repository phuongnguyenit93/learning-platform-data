# Idempotent business operation — Đặc tả thao tác nghiệp vụ có tính lũy đẳng

## 1. Vì sao cần lũy đẳng ở cấp nghiệp vụ?

Một client gửi lệnh, không nhận được phản hồi rồi thử lại. Điều đó không cho biết lần đầu chưa chạy: máy chủ có thể đã commit nhưng mất kết nối trước khi trả kết quả.

Nếu mỗi lần gửi đều tạo tác dụng mới, một lỗi mạng có thể biến thành hai khoản thu, hai lần hoàn tiền, hai lượt sử dụng khuyến mãi hoặc hai công việc xuất dữ liệu. Idempotency — tính lũy đẳng — giúp các lần thực thi lại cùng một lệnh logic không tạo thêm tác dụng nghiệp vụ ngoài hợp đồng.

Trong module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, yêu cầu cần đi xa hơn câu “API phải hỗ trợ idempotency key”. Phải xác định:

- Thế nào là cùng một ý định nghiệp vụ?
- Phạm vi nhận diện lệnh gồm tenant, chủ thể và loại thao tác nào?
- Cùng khóa nhưng khác nội dung được xử lý ra sao?
- Các bản gửi đồng thời có thể cùng vượt qua kiểm tra chống lặp không?
- Sau crash, timeout hoặc mất phản hồi, trạng thái nào là đáng tin?
- Điều gì còn được bảo đảm sau khi hết thời gian lưu kết quả?
- Khi gọi bên ngoài, bằng chứng nào xác nhận tác dụng đã xảy ra hay chưa?

Bài học sử dụng ví dụ hoàn tiền một phần cho một giao dịch thanh toán. Các con số và chính sách là giả định minh họa, không phải giá trị áp dụng mặc định cho mọi hệ thống.

## 2. Hiểu đúng ý nghĩa của idempotency

### 2.1. Lũy đẳng gắn với cùng lệnh và cùng hợp đồng

Ở mức khái niệm, với một lệnh cố định C và trạng thái S:

```text
apply(C, apply(C, S)) có cùng tác dụng nghiệp vụ được phép
với apply(C, S)
```

Điều này không bắt buộc mọi response phải giống từng byte. Lần đầu có thể báo vừa tạo, lần sau báo kết quả đã tồn tại. Timestamp phản hồi hoặc dấu vết mỗi lần gọi cũng có thể khác, miễn không tạo thêm tác dụng nghiệp vụ bị cấm.

Cần xác định tác dụng nào thuộc cam kết. Hoàn tiền không được lặp, nhưng hệ thống vẫn có thể ghi một audit event cho mỗi lần client thử lại. Ngược lại, nếu một thông báo có ý nghĩa pháp lý hoặc nghiệp vụ không được phát nhiều lần, nó phải nằm trong phạm vi chống lặp tương ứng.

### 2.2. Idempotency không đồng nghĩa thao tác không có tác dụng

Một lệnh hoàn tiền có thể thay đổi số dư và trạng thái. Nó vẫn có tính lũy đẳng nếu retry cùng lệnh không tạo khoản hoàn thứ hai.

Tương tự, “tạo tài khoản” không tự nhiên lũy đẳng chỉ vì cùng email bị từ chối. Hợp đồng có thể cần trả lại đúng kết quả tạo trước đó, kiểm tra quyền đọc và phân biệt một lần thử mới với replay của lệnh cũ.

### 2.3. Các khái niệm gần nhau

| Khái niệm | Bảo đảm chính | Điều chưa tự bảo đảm |
| --- | --- | --- |
| Request deduplication | Nhận diện một số request trùng | Tác dụng nghiệp vụ không lặp trên mọi đường ghi |
| Idempotency key | Cung cấp định danh cho các lần gửi lại cùng lệnh | Khóa đúng phạm vi, được lưu bền và ràng buộc nội dung |
| Unique constraint | Ngăn trùng theo bộ cột được chọn | Bộ cột đó đã mô hình hóa đúng ý nghĩa nghiệp vụ |
| Optimistic concurrency | Phát hiện thay đổi phiên bản cạnh tranh | Hai lệnh khác ID không cùng tạo tác dụng bị cấm |
| Message deduplication | Nhận diện message đã xử lý | Hai message ID khác nhau không đại diện cùng thao tác logic |
| Rate limit | Giới hạn tốc độ hoặc tần suất gọi | Một vài lần gọi được phép vẫn có thể tạo tác dụng lặp |
| Xác thực/phân quyền | Đúng chủ thể và quyền | Retry không tạo thêm tác dụng |
| Chống phát lại bảo mật | Hạn chế dùng lại thông điệp ngoài điều kiện cho phép | Mọi retry hợp lệ đều được xử lý lũy đẳng |

Một idempotency key không phải credential, không phải quyền truy cập và cũng không mặc nhiên là cơ chế chống phát lại đầy đủ cho một giao thức.

## 3. Ví dụ xuyên suốt: hoàn tiền một phần

Giả sử thanh toán `payment-719` có số tiền có thể hoàn là 1.000.000 theo đơn vị lưu của hệ thống. Nhân viên muốn hoàn 200.000 cho một yêu cầu nghiệp vụ `refund-case-42`.

Các bất biến minh họa:

```text
Một refund_case được phép tạo một thao tác hoàn tiền logic theo chính sách.

Retry cùng thao tác không tạo thêm khoản hoàn.

Tổng đã hoàn + phần hoàn đang được giữ chỗ không vượt số tiền được phép hoàn.

Mỗi khoản hoàn phải thuộc đúng tenant, giao dịch và chủ thể được phân quyền.

Một kết quả chưa rõ từ bên thanh toán không được coi là chưa có tác dụng.
```

Nếu nghiệp vụ cho phép hoàn nhiều phần, hai khoản cùng 200.000 không nhất thiết là trùng. Chúng có thể là hai quyết định độc lập. Vì vậy, không dùng riêng số tiền và payment ID để suy ra cùng một ý định.

Ngược lại, client thay idempotency key không được tạo một khoản hoàn mới cho cùng `refund-case-42` nếu chính sách chỉ cho một thao tác. Đây là khác biệt giữa chống lặp ở lớp API và bất biến ở lớp nghiệp vụ.

### 3.1. Hai loại định danh cần phân biệt

| Định danh | Vai trò |
| --- | --- |
| Idempotency key | Liên kết các lần gửi lại một lệnh qua hợp đồng API |
| Business operation ID | Nhận diện thao tác nghiệp vụ cần được kiểm soát suốt vòng đời |
| Message/event ID | Nhận diện một đơn vị giao nhận trong hệ thống sự kiện |
| Provider reference | Liên kết với lần xử lý hoặc kết quả tại bên ngoài |
| Correlation ID | Hỗ trợ truy vết nhiều bước; không tự là khóa chống lặp |

Các định danh có thể được ánh xạ với nhau nhưng không được tùy ý thay thế. Một correlation ID mới cho mỗi retry không nên làm thay đổi operation ID.

### 3.2. Không suy ra ý định chỉ từ payload

Hai lệnh có payload giống nhau có thể là hai giao dịch hợp lệ khác nhau. Một lệnh có payload khác do trường thời gian gửi lại nhưng vẫn đại diện cùng ý định.

Yêu cầu phải xác định những thuộc tính làm nên ý nghĩa lệnh. Định danh do quy trình nghiệp vụ quản lý thường cần thiết khi phải ngăn client đổi khóa để vượt kiểm soát.

## 4. Đi từ mô hình đe dọa đến yêu cầu

| Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- |
| Client retry sau mất phản hồi | Hai khoản hoàn cho một ý định | Lưu kết quả bền vững, tra cứu và replay theo cùng lệnh |
| Hai request cùng khóa đến đồng thời | Cả hai cùng thấy chưa tồn tại | Quyết định chiếm quyền xử lý phải nguyên tử |
| Cùng khóa nhưng tăng số tiền | Thay nội dung lệnh đã được nhận | Ràng buộc khóa với fingerprint do máy chủ xác định |
| Đổi khóa nhưng giữ cùng refund case | Vượt giới hạn nghiệp vụ | Ràng buộc duy nhất hoặc guard theo operation ID |
| Tenant khác dùng khóa đoán được | Rò rỉ kết quả hoặc chiếm lệnh | Phạm vi khóa từ ngữ cảnh xác thực; phân quyền khi đọc kết quả |
| Token được làm mới làm đổi namespace | Retry bị xem là lệnh mới | Danh tính logic ổn định theo hợp đồng, không dựa vào token tạm thời |
| Worker chết sau tác dụng nhưng trước marker | Consumer chạy lại tác dụng | Marker và thay đổi cùng commit khi trong một kho dữ liệu |
| Lease hết hạn nhưng worker cũ còn chạy | Hai worker đồng thời tạo tác dụng | Không dùng hết lease làm bằng chứng tác vụ cũ đã dừng |
| Bên ngoài xử lý nhưng response mất | Gửi lệnh mới gây hoàn thêm | Trạng thái chưa rõ, định danh ổn định và đối soát |
| Xóa lịch sử chống lặp quá sớm | Replay cũ trở thành lệnh mới | Retention và bất biến nghiệp vụ không phụ thuộc riêng cache kết quả |
| Kho chống lặp mất truy cập | Hệ thống bỏ qua kiểm soát để tiếp tục | Chính sách suy giảm rõ; lệnh nhạy cảm không chạy mù |
| Tạo vô hạn khóa mới | Cạn bộ nhớ, lưu trữ hoặc metric | Giới hạn độ dài, lưu lượng và cardinality |

Idempotency phải chống được cả lỗi vô tình và hành vi cố ý khai thác retry. Tuy nhiên, nó không thay thế kiểm tra tổng hạn mức hoàn tiền hoặc quyền thao tác.

## 5. Hợp đồng idempotency key

### 5.1. Phạm vi khóa

Một namespace có thể được đặc tả như sau:

```text
scope = tenant_đã_xác_minh
      + danh_tính_logic_theo_hợp_đồng
      + loại_thao_tác

dedup_identity = scope + idempotency_key
```

Danh tính logic có thể là người dùng, ứng dụng khách hoặc dịch vụ theo chính sách. Cần quyết định rõ để một lần đổi access token không vô tình đổi lệnh, và một người khác không đọc được kết quả chỉ vì biết khóa.

Tenant và principal không được lấy từ các trường tùy ý trong payload. Nếu một hệ thống hỗ trợ ủy quyền hoặc hành động thay người khác, phải chỉ rõ actor, chủ thể được đại diện và phạm vi chống lặp tương ứng.

### 5.2. Tạo và tái sử dụng khóa

Client phải tạo khóa cho một ý định và dùng lại khóa đó khi retry. Không tạo khóa mới cho mỗi lần timeout.

Trong ví dụ, hợp đồng chấp nhận khóa ASCII theo schema được công bố, độ dài từ 16 đến 128 byte. Khóa nên được tạo bằng nguồn ngẫu nhiên thích hợp hoặc cơ chế bảo đảm duy nhất theo thiết kế; độ dài tự nó không chứng minh có đủ độ khó đoán.

Máy chủ vẫn phải xác thực và phân quyền. Khóa khó đoán giảm một số nguy cơ nhưng không phải lý do bỏ kiểm tra truy cập.

### 5.3. Thời điểm bắt đầu ghi nhận

Cần nêu loại lỗi nào được ghi thành kết quả của lệnh và loại lỗi nào xảy ra trước khi lệnh được chấp nhận.

Một chính sách minh họa:

- Lỗi định dạng hoặc không xác thực: không thực hiện nghiệp vụ; không cung cấp thông tin về khóa ngoài phạm vi.
- Lệnh đã được chấp nhận rồi bị từ chối bởi một quyết định nghiệp vụ cuối cùng: lưu kết quả từ chối nếu hợp đồng chọn cách đó.
- Lỗi tạm thời trước khi có tiếp nhận bền vững: client có thể retry cùng khóa.
- Đã tạo ý định bền vững nhưng chưa biết kết quả tác dụng: không tự xóa lệnh; chuyển sang chờ hoặc chưa rõ.

Không được tùy ý lưu mọi lỗi thành kết quả vĩnh viễn. Cũng không được xóa mọi lỗi để thử lại, vì lỗi phản hồi có thể xảy ra sau khi tác dụng đã được commit.

### 5.4. Phản hồi không bắt buộc giống từng byte

Cùng lệnh có thể trả một operation ID ổn định và kết quả nghiệp vụ nhất quán. Mã phản hồi hoặc thông tin “đã xử lý trước đó” phải theo hợp đồng API.

Nếu lưu response để replay, cần bảo vệ dữ liệu nhạy cảm và kiểm tra quyền hiện hành trước khi trả. Một response đã lưu không được trở thành đường vòng đọc dữ liệu sau khi quyền đã bị thu hồi.

## 6. Ràng buộc khóa với nội dung lệnh

### 6.1. Fingerprint do máy chủ xác định

Nếu cùng khóa có thể được dùng với nội dung khác, máy chủ cần nhận diện xung đột thay vì âm thầm dùng hoặc thực hiện nội dung mới.

Dữ liệu tạo fingerprint có thể gồm:

```text
loại thao tác
business operation ID
payment ID
số tiền và đồng tiền đã chuẩn hóa
đối tượng nhận liên quan
revision hoặc các thuộc tính quyết định ý nghĩa
phiên bản ngữ nghĩa của lệnh khi cần
```

Máy chủ tự tạo fingerprint từ dữ liệu được kiểm tra. Không tin fingerprint do client gửi là bằng chứng payload không đổi.

### 6.2. Chuẩn hóa phải theo schema

Cần quy định rõ:

- Kiểu số, đơn vị và cách biểu diễn.
- Trường nào bắt buộc, giá trị mặc định có ý nghĩa gì.
- Thứ tự phần tử nào có ý nghĩa và thứ tự nào không.
- Cách xử lý khoảng trắng hoặc ký tự theo từng loại trường.
- Những thuộc tính nào thuộc nội dung nghiệp vụ.
- Những thuộc tính nào chỉ là metadata từng lần gửi.

Không đưa trace ID hoặc timestamp phát sinh mỗi retry vào fingerprint nếu chúng không đổi ý nghĩa lệnh. Ngược lại, bỏ người nhận, revision hoặc đồng tiền khỏi fingerprint có thể làm hai lệnh khác nhau bị coi là một.

Không tự chuẩn hóa tên tài khoản, mã đối tượng hoặc Unicode theo cách làm nhập nhằng các giá trị vốn khác nhau. Việc sắp xếp khóa JSON cũng không đủ nếu schema còn có vấn đề về kiểu số hoặc giá trị mặc định.

### 6.3. Cùng khóa, khác nội dung

Một hành vi minh họa là trả lỗi xung đột theo hợp đồng, không thực hiện tác dụng mới và không sửa fingerprint cũ.

Xung đột cần có metric và dấu vết thích hợp, nhưng không ghi toàn bộ payload nhạy cảm. Fingerprint của dữ liệu ít khả năng hoặc có cấu trúc đoán được cũng không nên được xem là đã ẩn danh hoàn toàn.

## 7. Mô hình trạng thái xử lý

Một mô hình tối thiểu có thể sử dụng:

| Trạng thái | Ý nghĩa | Hành vi với retry cùng lệnh |
| --- | --- | --- |
| IN_PROGRESS | Có ý định bền vững hoặc đang có quyền xử lý theo mô hình đã chọn | Không tạo tác dụng mới; trả trạng thái hoặc chờ hữu hạn |
| SUCCEEDED | Kết quả nghiệp vụ theo hợp đồng đã được ghi nhận bền vững | Trả lại kết quả được phép đọc |
| REJECTED | Quyết định từ chối cuối cùng đã được ghi nhận cho lệnh này | Trả lại quyết định theo hợp đồng, không âm thầm đánh giá thành lệnh mới |
| UNKNOWN | Có khả năng tác dụng đã xảy ra nhưng chưa xác định được kết quả | Tra cứu/đối soát, không coi là chưa thực hiện |

Đây là mô hình minh họa, không phải tên trạng thái bắt buộc. Một hệ thống chỉ xử lý cục bộ có thể không cần lưu trạng thái UNKNOWN. Một hệ thống nhiều bước có thể cần thêm trạng thái cụ thể.

### 7.1. Từ chối cuối cùng khác lỗi tạm thời

Giả sử lệnh đã được chấp nhận rồi bị từ chối vì quyết định nghiệp vụ không cho hoàn. Nếu hợp đồng ghi nhận đây là kết quả cuối, retry cùng lệnh vẫn trả quyết định đó.

Nếu người có quyền muốn tạo một quyết định nghiệp vụ mới sau khi điều kiện thay đổi, phải qua quy trình mới với định danh và quyền phù hợp. Không đơn giản đổi khóa để làm sống lại một yêu cầu bị cấm.

Ngược lại, một sự cố mạng trước khi lệnh được tiếp nhận bền vững không nhất thiết tạo ra một quyết định REJECTED. Cần phân loại theo bằng chứng thực tế.

### 7.2. Hủy là một thao tác có kiểm soát

Không hủy công việc bằng cách xóa idempotency record. Việc xóa không hoàn tác tác dụng đã xảy ra và có thể cho phép replay thành lệnh mới.

Nếu cho hủy, cần một lệnh hủy có quyền, guard, định danh riêng và audit. Một thao tác đã gửi ra bên ngoài có thể không hủy được ngay; kết quả phải được biểu diễn trung thực.

### 7.3. Trạng thái cũ không được ghi đè kết quả mới

Worker hoặc callback đến muộn không được chuyển SUCCEEDED trở lại IN_PROGRESS hoặc REJECTED tùy ý. Cập nhật cần có điều kiện trạng thái, phiên bản hoặc cơ chế tương đương.

Một phản hồi lỗi từ lần thử trước không chứng minh lệnh cuối cùng đã thất bại nếu một lần xử lý khác hoặc việc đối soát đã xác nhận thành công.

## 8. Thực thi nguyên tử trong một kho dữ liệu

### 8.1. Mẫu kiểm tra rồi thực hiện có race

```text
Request A: chưa có khóa K → cho thực hiện
Request B: chưa có khóa K → cho thực hiện
A tạo khoản hoàn
B tạo khoản hoàn
A và B mới ghi dấu đã xử lý
```

Việc có bảng chống lặp không đủ nếu quyết định nhận quyền và tác dụng không được bảo vệ.

### 8.2. Ràng buộc duy nhất cho danh tính lệnh

Một cấu trúc khái niệm có thể gồm:

```text
idempotency_command:
    tenant_id
    principal_scope
    operation_type
    idempotency_key
    payload_fingerprint
    business_operation_id
    state
    result_reference
    created_at
    completed_at
    result_retention_until

UNIQUE(tenant_id, principal_scope, operation_type, idempotency_key)
```

Cần định nghĩa thêm ràng buộc theo business operation ID phù hợp chính sách. Unique constraint phải tồn tại ở nơi thực sự điều phối được các request cạnh tranh; một map trong bộ nhớ từng instance không bảo vệ toàn cụm.

### 8.3. Mẫu đồng bộ với tác dụng cục bộ

Khi tất cả thay đổi liên quan nằm trong một kho có transaction phù hợp, có thể đặt nhận diện lệnh, thay đổi nghiệp vụ và kết quả trong cùng đơn vị commit:

```text
authenticate_and_authorize(command)

begin transaction
    try claim dedup_identity bằng cơ chế nguyên tử
    nếu đã có:
        xác minh fingerprint và đọc kết quả theo chính sách
        không thực hiện tác dụng lần nữa
    nếu giành quyền xử lý:
        kiểm tra guard và giữ phần hạn mức hoàn
        tạo refund operation duy nhất theo chính sách
        thực hiện các thay đổi cục bộ cần thiết
        ghi kết quả, audit/ý định audit và sự kiện cần thiết
commit

trả kết quả sau khi điều kiện commit và độ bền đã đạt
```

Đây là mã giả. Hành vi đọc request đang cạnh tranh phụ thuộc transaction và mức cô lập. Nếu bản ghi của bên xử lý chưa commit, request khác có thể phải chờ hoặc gặp xung đột, không thể mặc định luôn đọc được một hàng IN_PROGRESS.

Thời gian chờ phải hữu hạn. Sau timeout chờ, không được bỏ khóa để chạy thêm một bản độc lập.

### 8.4. Marker và tác dụng phải gắn nhau

Nếu tạo khoản hoàn rồi mới ghi marker trong transaction khác, crash ở giữa tạo cửa sổ chạy lặp.

Nếu ghi SUCCEEDED trước khi tạo tác dụng, crash ở giữa có thể khiến retry bỏ qua công việc chưa từng hoàn tất.

Với tác dụng cục bộ, marker cuối và thay đổi nghiệp vụ phải cùng commit hoặc dùng cơ chế tương đương có bằng chứng. Đừng coi thứ tự gọi hai hàm là bảo đảm nguyên tử.

### 8.5. Tranh chấp hạn mức vẫn cần kiểm soát riêng

Hai lệnh khác operation ID có thể đều hợp lệ nhưng cùng vượt tổng tiền được hoàn. Idempotency không ngăn điều này vì chúng không phải cùng lệnh.

Phải bảo vệ bất biến:

```text
đã_hoàn + đang_giữ_chỗ + khoản_mới ≤ số_tiền_được_phép_hoàn
```

Cần kiểm tra và cập nhật hạn mức bằng cơ chế nhất quán phù hợp. Version từng refund không tự bảo vệ được tổng trên payment.

## 9. Worker, lease và xử lý bất đồng bộ

### 9.1. Tiếp nhận bền vững khác hoàn tất nghiệp vụ

Trong mô hình bất đồng bộ, bước tiếp nhận có thể commit IN_PROGRESS, business operation và ý định đưa việc vào hàng đợi trong một transaction cục bộ.

Client nhận operation ID để tra cứu. Phản hồi này không được trình bày là đã hoàn tiền xong.

Worker sau đó thực hiện guard, thay đổi và kết quả theo mô hình đã thiết kế. Nếu điều kiện nghiệp vụ hoặc quyền cần đánh giá lại tại thời điểm thực thi, hợp đồng phải nói rõ và worker phải làm thật.

### 9.2. Lease không thay thế chống lặp

Lease hoặc lock phân tán giúp phân công công việc, nhưng một worker có thể bị treo, mất mạng hoặc chạy chậm trong khi lease hết hạn. Worker mới có thể được giao việc khi worker cũ vẫn đang thực hiện.

Nếu cả hai đều có khả năng tạo tác dụng, cần bảo vệ tại nơi tác dụng được ghi nhận, chẳng hạn cập nhật có điều kiện, định danh duy nhất hoặc cơ chế kiểm soát chủ thực thi phù hợp.

Không kết luận “lease hết hạn nên công việc cũ chắc chắn chưa thực hiện”. Cũng không trả IN_PROGRESS về trạng thái cho phép chạy lại chỉ vì đã quá một timer.

### 9.3. Message lặp phải đi tới cùng operation

Một queue có thể giao lại cùng message. Producer cũng có thể tạo message ID mới cho cùng một business operation.

Consumer cần nhận diện theo ngữ nghĩa đúng. Với tác dụng trong cùng DB, ghi dấu đã xử lý và thay đổi cần gắn nguyên tử. Với bên ngoài, phải dùng chiến lược của phần tiếp theo.

### 9.4. Restart và takeover

Sau restart, worker phải đọc trạng thái bền vững, kết quả và dữ kiện đối soát. Không dùng bộ nhớ cũ hoặc kết quả “chưa thấy response” làm bằng chứng chưa có tác dụng.

Quy trình takeover phải có điều kiện, quyền, audit và phương án khi chủ cũ quay lại. Những công việc chưa rõ cần được quan sát và có người chịu trách nhiệm xử lý.

## 10. Tác dụng ở hệ thống bên ngoài

### 10.1. Transaction cục bộ không bao phủ bên cung cấp

Một marker trong DB không tự làm lời gọi hoàn tiền bên ngoài nguyên tử với DB.

Hai khoảng trống cần xét:

```text
Đánh dấu thành công trước → tiến trình chết, bên ngoài chưa được gọi.

Gọi bên ngoài trước → bên ngoài đã hoàn, tiến trình chết trước khi lưu kết quả.
```

Outbox có thể giúp lưu ý định gửi cùng commit với dữ liệu nội bộ, nhưng không tự loại giao nhận lặp hoặc tác dụng lặp ở hệ thống nhận.

### 10.2. Giữ định danh ổn định khi gọi lại

Nếu bên cung cấp hỗ trợ idempotency, dùng khóa hoặc operation reference ổn định theo hợp đồng của họ, gắn với đúng nội dung.

Cần xác định:

- Phạm vi khóa của bên cung cấp.
- Thời gian họ giữ kết quả chống lặp.
- Hành vi cùng khóa khác payload.
- Khả năng truy vấn trạng thái sau timeout.
- Cách đối chiếu callback với operation nội bộ.
- Hành vi khi retry vượt thời hạn bảo đảm của bên cung cấp.

Thời hạn idempotency nội bộ 24 giờ không tự kéo dài thời hạn bảo đảm của bên ngoài. Nếu bên ngoài chỉ bảo đảm ngắn hơn, không được retry mù ngoài khoảng đó rồi tuyên bố an toàn.

### 10.3. UNKNOWN cần đường đối soát

Nếu mất phản hồi sau khi bên ngoài có thể đã nhận lệnh, trạng thái cần thể hiện chưa rõ. Hệ thống có thể truy vấn theo reference, chờ callback được xác minh hoặc đối soát bằng kênh đã phê duyệt.

Không tự giải phóng phần tiền giữ chỗ rồi nhận một thao tác mới có thể hoàn thêm, khi khoản trước vẫn có thể thành công.

Khi không có cơ chế đủ để xác định hoặc chống lặp tác dụng ngoài, phải ghi nhận giới hạn thiết kế và quy trình xử lý. Không hứa “exactly once đầu cuối” chỉ vì đã dùng idempotency key ở API của mình.

### 10.4. Callback lặp và sai thứ tự

Một callback phải được xác minh nguồn và liên kết đúng operation, giao dịch gốc, số tiền, đồng tiền và trạng thái hiện hành.

Callback lặp không được cộng lại tiền đã hoàn. Callback cũ cũng không được làm lùi trạng thái đã xác nhận. Một callback có chữ ký đúng vẫn có thể thuộc một operation khác hoặc đến muộn; tính xác thực nguồn chưa đủ để bỏ qua kiểm tra nghiệp vụ.

## 11. Retention, cache và phục hồi

### 11.1. Tách thời gian lưu response khỏi thời gian giữ ràng buộc

Có thể chỉ lưu response đầy đủ 24 giờ, nhưng vẫn cần giữ liên kết khóa hoặc tombstone, operation ID và kết quả nghiệp vụ trong thời gian replay còn phải bị ngăn theo chính sách.

Tombstone là bản ghi tối thiểu cho biết định danh đã được dùng và cách tìm kết quả hoặc từ chối replay; nó không tự chứng minh kết quả nếu không còn liên kết đáng tin.

Không bắt buộc giữ mọi payload mãi mãi. Cần cân bằng khả năng chống lặp, quyền riêng tư, dung lượng và chính sách retention đã được xác định.

### 11.2. Không thể quên mọi bằng chứng rồi hứa nhận ra replay

Nếu xóa cả khóa, tombstone, operation ID và mọi ràng buộc nghiệp vụ liên quan, hệ thống có thể không phân biệt request cũ với request mới.

Hợp đồng phải nêu bảo đảm sau hết hạn, nguồn nhận diện còn lại và giới hạn của nó. Nếu chỉ bảo đảm trong một cửa sổ, phải nói rõ. Nếu nghiệp vụ cấm lặp lâu hơn, phải có một lớp ràng buộc bền vững tương ứng.

Không dùng thời gian hết hạn cache làm thời điểm tự động cho phép hoàn lại cùng refund case.

### 11.3. Cache không phải nguồn sự thật duy nhất

Cache có thể tăng tốc replay kết quả nhưng có thể mất, bị eviction hoặc khác nhau giữa instance. Với thao tác nhạy cảm, mất cache không được biến thành quyền tạo thêm tác dụng.

Quyết định thực hiện cần dựa trên nguồn chống lặp và trạng thái có thẩm quyền theo mô hình đã chọn. Nếu dùng một kho riêng, phải phân tích khoảng trống nguyên tử giữa kho đó và nơi có tác dụng nghiệp vụ.

### 11.4. Backup và restore phải giữ quan hệ

Khôi phục dữ liệu nghiệp vụ mà không khôi phục hoặc đối soát marker chống lặp có thể khiến lệnh cũ được chạy lại. Ngược lại, marker nói đã thành công trong khi nghiệp vụ bị phục hồi về trước commit có thể khiến công việc bị bỏ mất.

Kế hoạch phục hồi cần giữ điểm nhất quán hoặc có quy trình đối soát với nguồn đáng tin, đặc biệt với tác dụng đã xảy ra bên ngoài. Không tự replay toàn bộ queue sau restore mà chưa kiểm tra operation và kết quả thực tế.

## 12. Hành vi lỗi, phân quyền và quan sát

### 12.1. Hợp đồng phản hồi minh họa

| Điều kiện | Hành vi cần có |
| --- | --- |
| Cùng lệnh đã thành công | Trả kết quả hoặc reference ổn định trong quyền được phép |
| Cùng lệnh đang xử lý | Trả trạng thái đang xử lý hoặc chờ có giới hạn |
| Cùng khóa khác nội dung | Lỗi xung đột; không đổi lệnh cũ |
| Không có quyền hiện hành | Không lộ nội dung kết quả chỉ vì khóa đã tồn tại |
| Kho chống lặp không truy cập được | Không chạy mù thao tác nhạy cảm; trả lỗi tạm thời hoặc xử lý theo mô hình an toàn đã duyệt |
| Kết quả ngoài hệ thống chưa rõ | Trả trạng thái đối soát, không gọi đó là hoàn tất hoặc chưa từng thực hiện |
| Response đầy đủ đã hết hạn | Hành vi theo hợp đồng, dựa trên bằng chứng còn lại; không mặc định tạo tác dụng mới |

HTTP 202 hoặc 409 có thể phù hợp cho một số nhánh, nhưng mã cụ thể phải theo thiết kế API. Cần chú ý cả nội dung, quyền truy vấn và điều kiện retry, không chỉ mã HTTP.

### 12.2. Quyền phải được kiểm tra khi replay

Một lệnh hợp lệ được tạo hôm qua không tự cho phép người gọi hôm nay đọc lại dữ liệu nhạy cảm sau khi họ đã bị thu hồi quyền.

Tách quyết định “có được tạo thêm tác dụng không” khỏi quyết định “có được xem kết quả không”. Việc từ chối đọc kết quả không có nghĩa xóa operation hoặc cho phép thực hiện lại.

### 12.3. Các tín hiệu cần quan sát

- Số lệnh mới, số replay và số xung đột nội dung.
- Số operation IN_PROGRESS và tuổi của chúng.
- Số operation UNKNOWN, tuổi và thời gian đối soát.
- Tình trạng kho chống lặp, constraint và đường ghi kết quả.
- Số tác dụng thực tế theo business operation, không chỉ số request.
- Số lần takeover, worker cũ quay lại và sự kiện đến muộn.
- Kết quả kiểm tra sau cleanup hoặc restore.

Không dùng raw idempotency key, payload nhạy cảm hoặc định danh tùy ý làm nhãn metric không giới hạn. Dấu vết cần đủ liên kết nhưng phải có kiểm soát cardinality, truy cập và retention.

Bão retry cũng không được làm đầy log. Có thể tổng hợp metric và kiểm soát log từng lần, trong khi giữ audit nghiệp vụ bắt buộc theo chính sách.

## 13. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây áp dụng cho quy trình hoàn tiền đã mô tả. Phạm vi triển khai, nguồn dữ liệu và giới hạn bên cung cấp phải được thay bằng thông tin dự án trước khi nghiệm thu thực tế.

| ID | Yêu cầu có thể kiểm chứng | Chủ sở hữu | Bằng chứng đạt |
| --- | --- | --- | --- |
| IDEM-01 | API phải xác định danh tính lệnh từ tenant, principal scope, loại thao tác và khóa theo hợp đồng; token làm mới không được vô tình biến retry thành lệnh mới. | Ứng dụng/bảo mật | Retry qua phiên/token hợp lệ mới vẫn ánh xạ đúng; tenant hoặc chủ thể khác không đọc/chiếm lệnh ngoài quyền. |
| IDEM-02 | Khóa phải tuân thủ schema, trong ví dụ dài 16–128 byte ASCII; máy chủ không dùng khóa làm quyền truy cập và phải kiểm soát lưu lượng tạo khóa. | Chủ API | Test khóa sai cấu trúc, quá dài, khóa đoán được và tải tạo khóa; không bỏ qua xác thực hoặc làm tài nguyên tăng không giới hạn. |
| IDEM-03 | Khóa phải ràng buộc fingerprint do máy chủ tính từ nội dung chuẩn; cùng khóa khác nội dung có ý nghĩa bị từ chối, không thay lệnh đã nhận. | Ứng dụng | Đổi số tiền, đồng tiền, payment ID hoặc operation ID bị phát hiện; thay metadata không có ý nghĩa được xử lý đúng hợp đồng. |
| IDEM-04 | Claim quyền xử lý cùng dedup identity phải nguyên tử trên toàn phạm vi triển khai; các request cạnh tranh không được cùng tạo tác dụng cục bộ bị cấm. | Dữ liệu/ứng dụng | Đồng bộ nhiều request ở điểm claim; chỉ một quyền thực thi được cấp hoặc chỉ một commit nghiệp vụ hợp lệ tồn tại theo thiết kế. |
| IDEM-05 | Với tác dụng cục bộ, thay đổi nghiệp vụ và marker/kết quả cuối phải cùng commit hoặc có cơ chế tương đương được chứng minh; không có cửa sổ crash tạo lặp hoặc bỏ mất việc. | Dữ liệu | Tiêm lỗi trước/sau từng điểm ghi và khởi động lại; đối chiếu marker với tác dụng thực tế. |
| IDEM-06 | Mỗi refund case trong ví dụ chỉ tạo một refund operation logic theo chính sách, kể cả dùng khóa API hoặc message ID khác; tổng tiền vẫn chịu hạn mức độc lập. | Nghiệp vụ/ứng dụng | Đổi khóa không vượt ràng buộc; hai case khác nhau vẫn không vượt tổng tiền được phép hoàn. |
| IDEM-07 | Phản hồi phải phân biệt đang xử lý, thành công, từ chối cuối cùng và chưa rõ; tiếp nhận bền vững không được trình bày như đã hoàn tiền xong. | Chủ API | Contract test so với trạng thái và kết quả nghiệp vụ thực tế tại từng mốc. |
| IDEM-08 | Kết quả replay được lưu tối thiểu 24 giờ trong ví dụ; cleanup không được làm mất ràng buộc chống lặp nghiệp vụ khi nó còn phải có hiệu lực. | Dữ liệu/chủ dịch vụ | Retry trước/sau thời hạn lưu response không tạo thêm tác dụng bị cấm; đối chiếu tombstone hoặc nguồn ràng buộc còn lại. |
| IDEM-09 | IN_PROGRESS hoặc UNKNOWN không được tự động cho thực hiện lại chỉ vì hết lease hoặc TTL; takeover phải tuân thủ guard và xử lý worker cũ còn chạy. | Nền tảng/ứng dụng | Làm lease hết hạn khi worker cũ còn hoạt động; không tạo tác dụng lặp, có dấu vết takeover. |
| IDEM-10 | Mọi lần gửi tới bên cung cấp phải liên kết một operation ổn định; timeout hoặc retry ngoài cửa sổ bảo đảm của họ phải đi qua chính sách tra cứu/đối soát đã duyệt. | Tích hợp | Giả lập bên ngoài nhận lệnh rồi mất response; không tạo lệnh mới tùy ý hoặc retry mù ngoài bảo đảm. |
| IDEM-11 | Callback và message lặp phải được xác minh, gắn đúng operation và kiểm tra trạng thái; không cộng lại tác dụng hoặc ghi đè kết quả cuối bằng dữ kiện cũ. | Tích hợp/ứng dụng | Test lặp, sai tham chiếu, sai dữ kiện và sai thứ tự; trạng thái và số tiền giữ đúng bất biến. |
| IDEM-12 | Replay kết quả phải kiểm tra quyền đọc hiện hành; lỗi kho chống lặp không được làm thao tác nhạy cảm bỏ qua kiểm soát. | Bảo mật | Thu hồi quyền rồi replay; mất kho chống lặp trong khi client retry; không lộ kết quả hoặc tạo tác dụng mới trái phép. |
| IDEM-13 | Phải có metric, audit và chủ xử lý cho operation treo/chưa rõ; log và nhãn metric không được tăng không giới hạn theo khóa do client tạo. | Vận hành | Quan sát tuổi operation, cảnh báo và dữ liệu audit; thử tải replay và khóa mới. |
| IDEM-14 | Mọi đường thực thi và kế hoạch restore phải giữ quan hệ operation–marker–tác dụng; thay đổi retention, nhà cung cấp hoặc queue phải đánh giá lại bảo đảm. | Chủ dịch vụ | Kiểm kê API, worker, batch, công cụ quản trị và diễn tập phục hồi; không replay mù sau restore. |

Các yêu cầu về cảnh báo cần có thời hạn cụ thể. Ví dụ, hệ thống có thể kiểm tra operation mỗi phút, coi IN_PROGRESS quá 5 phút là cần điều tra và gửi cảnh báo trong 2 phút từ lúc phát hiện. Đây chỉ là ngưỡng quan sát; nó không cho phép tự động chạy lại operation sau 5 phút.

UNKNOWN cần thời hạn đối soát và người xử lý phù hợp với bên cung cấp. Nếu thời gian xác nhận hợp lệ của họ dài hơn, phải đặc tả riêng thay vì dùng ngưỡng trên để kết luận thất bại.

### Mẫu đặc tả chi tiết

```text
ID: IDEM-05
Mục tiêu: crash không tạo thêm hoặc bỏ mất tác dụng hoàn tiền cục bộ
Rủi ro: R-IDEM-03 — tác dụng và dấu đã xử lý không cùng bền vững
Phạm vi: refund operation và dữ liệu hạn mức trong kho được chỉ định
Dữ kiện bắt buộc:
  - Dedup identity và fingerprint
  - Business operation ID theo chính sách
  - Thay đổi nghiệp vụ, reservation/hạn mức liên quan
  - Kết quả cuối và ý định sự kiện/audit cần thiết
Điều kiện:
  - Tập thay đổi bắt buộc cùng commit hoặc cùng không có hiệu lực
  - Crash rồi retry không tạo tác dụng cục bộ thứ hai
  - Không báo SUCCEEDED khi tác dụng bắt buộc chưa đạt
Ngoài phạm vi:
  - Không tự suy ra nguyên tử với dịch vụ ngoài
Chủ sở hữu: đội dữ liệu, phối hợp đội ứng dụng
Kiểm thử: T-IDEM-03, T-IDEM-04, T-IDEM-05
Bằng chứng: failpoint, marker, operation, số tiền và phản hồi
```

## 14. Ma trận kiểm thử nghiệm thu

Thực hiện trên môi trường kiểm soát với dữ liệu giả và bên ngoài giả lập hoặc sandbox. Test cạnh tranh cần điểm đồng bộ hoặc lịch thực thi quan sát được; chỉ tăng số request mà chưa gặp lỗi không đủ chứng minh tính nguyên tử.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-IDEM-01 | Gửi lại cùng lệnh và khóa sau khi đã có kết quả; làm mới token nhưng giữ danh tính logic. | Ánh xạ đúng lệnh; không thêm khoản hoàn; phản hồi theo hợp đồng và quyền hiện hành. | IDEM-01, 07, 12 |
| T-IDEM-02 | Cùng khóa nhưng đổi số tiền, đồng tiền, payment ID hoặc operation ID; riêng lượt khác chỉ đổi trace ID. | Phát hiện thay đổi ngữ nghĩa; xử lý metadata đúng schema; không đổi lệnh cũ. | IDEM-03 |
| T-IDEM-03 | Cho nhiều instance cùng tiếp cận điểm claim của một dedup identity. | Không có hai tác dụng cục bộ bị cấm; chờ/xung đột có giới hạn và có bằng chứng. | IDEM-04, 05 |
| T-IDEM-04 | Crash sau marker, sau thay đổi nghiệp vụ, sau kết quả và trước/sau commit theo từng lượt. | Sau recovery, marker khớp tác dụng; không bỏ mất việc hoặc thực hiện thêm ngoài chính sách. | IDEM-05 |
| T-IDEM-05 | Commit thành công nhưng cắt response; client retry cùng khóa. | Trả lại kết quả đã có hoặc đường tra cứu hợp lệ; không hoàn lần hai. | IDEM-05, 07, 08 |
| T-IDEM-06 | Dùng khóa khác hoặc message ID khác cho cùng refund case; cho hai case cạnh tranh tổng tiền còn lại. | Ràng buộc nghiệp vụ và hạn mức vẫn đúng, không chỉ dựa vào khóa API. | IDEM-06, 11 |
| T-IDEM-07 | Hết thời gian lưu response và chạy cleanup; retry operation cũ; giữ một operation UNKNOWN qua mốc TTL. | Không tạo tác dụng bị cấm; UNKNOWN không tự mất bảo vệ; hành vi sau hết hạn đúng hợp đồng. | IDEM-08, 09 |
| T-IDEM-08 | Cho lease hết hạn khi worker cũ đang bị chậm; worker mới tiếp quản rồi worker cũ tiếp tục. | Chỉ kết quả được phép được ghi nhận; tác dụng không nhân đôi; phát hiện hoặc kiểm soát chủ cũ theo thiết kế. | IDEM-09 |
| T-IDEM-09 | Bên ngoài nhận lệnh rồi mất response; thử lại gần và sau cửa sổ idempotency của họ. | Giữ operation/reference, chuyển đối soát khi cần; không gửi mù lệnh mới ngoài bảo đảm. | IDEM-10 |
| T-IDEM-10 | Callback lặp, sai operation, sai số tiền hoặc sai thứ tự. | Không cộng lại tiền hoàn, không ghi đè kết quả cuối bằng sự kiện không phù hợp. | IDEM-11 |
| T-IDEM-11 | Tenant/người dùng khác dùng cùng khóa; chủ cũ bị thu hồi quyền rồi replay. | Không lộ kết quả hoặc chiếm lệnh ngoài phạm vi; không xóa operation để cho phép thực hiện lại. | IDEM-01, 12 |
| T-IDEM-12 | Mất cache, ngắt kho chống lặp, dừng worker hoặc luồng đối soát trong các lượt riêng. | Không chạy mù; trạng thái và cảnh báo đúng; không tuyên bố đã hoàn tất khi thiếu bằng chứng. | IDEM-12, 13 |
| T-IDEM-13 | Tạo nhiều khóa mới, khóa quá dài, replay dồn dập và label tùy ý. | Giới hạn đầu vào/tài nguyên có hiệu lực; metric/log không tạo điểm cạn tài nguyên mới. | IDEM-02, 13 |
| T-IDEM-14 | Restore DB và queue theo kịch bản; có tác dụng ngoài đã xảy ra trước restore. | Đối soát operation–marker–tác dụng trước khi mở xử lý; không chạy lại queue mù. | IDEM-14 |

Bằng chứng cần có phiên bản ứng dụng, schema, chính sách scope/fingerprint, thời điểm failpoint, định danh liên kết, marker và tác dụng thực tế. Với bên ngoài, phải đối chiếu reference và kết quả đã xác minh.

Không kết luận đạt chỉ vì các response đều giống nhau. Hai response giống hệt vẫn có thể che hai tác dụng. Ngược lại, response khác mã nhưng cùng một operation và không tạo tác dụng mới có thể đúng hợp đồng.

## 15. Truy vết qua vòng đời phát triển

Chuỗi truy vết tối thiểu:

```text
Mục tiêu bảo mật và ý nghĩa thao tác
    → Rủi ro lặp, đổi nội dung hoặc mất kết quả
    → Định danh lệnh và bất biến nghiệp vụ
    → Yêu cầu IDEM-xx
    → Scope, fingerprint, trạng thái và ranh giới commit
    → Test T-IDEM-xx
    → Audit, metric, đối soát và phục hồi
```

| Mục tiêu | Rủi ro | Yêu cầu | Thiết kế/kiểm chứng |
| --- | --- | --- | --- |
| Không hoàn hai lần khi retry | Mất response hoặc race | IDEM-04, 05, 07 | Claim nguyên tử và kết quả bền vững; T-IDEM-03, 04, 05 |
| Không đổi ý nghĩa lệnh cũ | Cùng khóa khác số tiền/người nhận | IDEM-03 | Fingerprint từ schema có thẩm quyền; T-IDEM-02 |
| Không vượt bất biến bằng khóa mới | Nhiều khóa cho cùng refund case | IDEM-06 | Operation ID và guard nghiệp vụ; T-IDEM-06 |
| Không lộ kết quả qua replay | Biết khóa nhưng không có quyền | IDEM-01, 12 | Scope đáng tin và phân quyền hiện hành; T-IDEM-11 |
| Không lặp sau cleanup/restore | Quên marker nhưng tác dụng còn | IDEM-08, 14 | Retention nhiều lớp và đối soát; T-IDEM-07, 14 |
| Không gọi ngoài mù khi kết quả chưa rõ | Timeout sau khi bên ngoài đã nhận | IDEM-09, 10 | UNKNOWN, reference ổn định và đối soát; T-IDEM-08, 09 |

Thay đổi schema fingerprint, namespace, identity provider, retention, queue hoặc nhà cung cấp có thể làm đổi bảo đảm, dù endpoint giữ nguyên.

Khi thay phiên bản, cần có chính sách cho khóa và lệnh cũ: chúng tiếp tục được nhận diện theo ngữ nghĩa nào, kết quả cũ có đọc được không, và migration có bảo toàn ràng buộc nghiệp vụ không.

Ngoại lệ phải có phạm vi, thời hạn, rủi ro còn lại, biện pháp bù và người phê duyệt. Không bỏ worker hoặc công cụ quản trị khỏi phạm vi chỉ vì chúng không đi qua API công khai.

## 16. Những lỗi đặc tả thường gặp

| Cách viết hoặc triển khai | Vì sao chưa đủ | Cách cải thiện |
| --- | --- | --- |
| “Có header Idempotency-Key là xong.” | Không nói scope, độ bền, cạnh tranh và nội dung | Đặc tả đầy đủ hợp đồng và đường thực thi |
| “Cùng payload là cùng lệnh.” | Hai ý định độc lập có thể giống dữ liệu | Dùng định danh ý định nghiệp vụ phù hợp |
| “Có key mới thì được chạy mới.” | Có thể cùng một nghiệp vụ bị cấm lặp | Ràng buộc operation ID và hạn mức độc lập |
| “SELECT chưa có rồi INSERT sau.” | Hai request cùng thấy chưa có | Claim nguyên tử trong phạm vi toàn hệ thống cần bảo vệ |
| “Lock hết hạn là retry an toàn.” | Worker cũ có thể còn tạo tác dụng | Guard ở nơi ghi tác dụng và takeover có kiểm soát |
| “Timeout nghĩa là chưa chạy.” | Có thể đã commit hoặc bên ngoài đã nhận | Tra cứu kết quả và biểu diễn UNKNOWN khi cần |
| “Lưu key trong cache là đủ.” | Cache có thể mất hoặc eviction | Nguồn bền vững và ranh giới nhất quán phù hợp |
| “TTL hết thì xóa để chạy lại.” | Lịch sử nghiệp vụ vẫn có thể cấm lặp | Tách response retention khỏi ràng buộc chống lặp |
| “Biết key thì trả response cũ.” | Có thể lộ dữ liệu sau thu hồi quyền | Kiểm tra quyền đọc hiện hành và scope |
| “Outbox bảo đảm exactly once đầu cuối.” | Bên nhận và tác dụng ngoài có thể lặp | Định danh ổn định, consumer phù hợp và đối soát |
| “Hai response như nhau chứng minh lũy đẳng.” | Tác dụng bên dưới có thể đã nhân đôi | Đo tác dụng nghiệp vụ thực tế |
| “Restore xong thì chạy lại toàn bộ queue.” | Marker và tác dụng ngoài có thể khác điểm phục hồi | Đối soát trước khi tiếp tục xử lý |

## 17. Bài tập áp dụng

Một nền tảng cho phép tạo đơn hàng, thu tiền và hoàn tiền một phần. Mobile app tự tạo khóa mới mỗi lần timeout. Worker lưu marker trong cache sau khi gọi bên thanh toán. Cache có TTL 30 phút; bên thanh toán có hợp đồng idempotency riêng chưa được đội phát triển kiểm tra.

Hãy thực hiện:

1. Nêu ít nhất năm kịch bản có thể tạo tác dụng lặp hoặc bỏ mất công việc.
2. Xác định idempotency key, business operation ID và provider reference cho từng loại thao tác.
3. Thiết kế scope và fingerprint; giải thích trường nào có ý nghĩa nghiệp vụ.
4. Viết sáu yêu cầu có ID, phạm vi, điều kiện đạt, thời hạn lưu và chủ sở hữu.
5. Đề xuất mô hình trạng thái cho đã tiếp nhận, đang xử lý, thành công, từ chối và chưa rõ.
6. Thiết kế test đồng thời, crash, mất response, hết TTL và callback lặp.
7. Nêu cách bảo vệ quyền khi trả kết quả replay và cách xử lý lúc kho chống lặp mất.
8. Chỉ ra điều cần xác minh với bên thanh toán trước khi cam kết không tạo khoản thu/hoàn lặp.
9. Đề xuất cách restore dữ liệu và queue mà không chạy lại tác dụng bên ngoài đã xảy ra.

Đáp án tốt cần chứng minh một retry ánh xạ vào đúng ý định, dữ kiện chống lặp còn tồn tại trong khoảng cần bảo vệ và tác dụng thực tế không bị nhân đôi khi có lỗi.

## 18. Checklist chấp nhận yêu cầu

- Cùng lệnh logic đã được phân biệt với cùng payload và cùng message chưa?
- Scope có tenant và danh tính đáng tin, ổn định theo hợp đồng không?
- Khóa có schema, giới hạn và quy tắc tái sử dụng rõ ràng không?
- Fingerprint có do máy chủ tạo và bao phủ đầy đủ nội dung có ý nghĩa không?
- Cùng khóa khác nội dung có bị xử lý xung đột mà không đổi lệnh cũ không?
- Claim và ghi tác dụng cục bộ có được bảo vệ nguyên tử không?
- Bất biến nghiệp vụ và hạn mức có còn hiệu lực khi client đổi khóa không?
- IN_PROGRESS, kết quả cuối và UNKNOWN có ngữ nghĩa rõ không?
- Timeout, hết lease hoặc TTL có tránh bị hiểu nhầm là chưa có tác dụng không?
- Response retention có được tách khỏi vòng đời chống lặp nghiệp vụ không?
- Bên ngoài có định danh ổn định, cửa sổ bảo đảm và đường đối soát được kiểm chứng không?
- Replay kết quả có kiểm tra quyền hiện hành không?
- Metric, audit và cảnh báo có quan sát tác dụng mà không gây cardinality vô hạn không?
- Cleanup, migration và restore có bảo toàn quan hệ marker–operation–tác dụng không?
- Test có kiểm tra số tác dụng thực tế trên mọi đường thực thi không?

Thao tác nghiệp vụ có tính lũy đẳng khi các lần gửi lại được ràng buộc vào đúng ý định, quyền thực thi và kết quả được quản lý bền vững, còn trạng thái chưa rõ luôn có đường kiểm chứng thay vì bị biến thành một lệnh mới.
