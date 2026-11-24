# Danh mục quy tắc nghiệp vụ (Business rule catalog)

Trong chương **Documentation** của module bảo vệ logic nghiệp vụ, **business rule catalog** là danh mục có cấu trúc mô tả những điều hệ thống phải cho phép, từ chối hoặc luôn giữ đúng khi thực hiện nghiệp vụ. Danh mục giúp đội sản phẩm, phát triển, kiểm thử và vận hành thống nhất được câu trả lời: **ai được làm gì, trên đối tượng nào, ở trạng thái nào, với dữ liệu nào và trong điều kiện nào?**

Một câu như “chỉ hoàn tiền khi hợp lệ” không đủ để chống lạm dụng. Người gọi có thể dùng đúng tài khoản nhưng sai đơn hàng, thay amount sau khi được duyệt, gọi thẳng bước thực hiện, gửi lại cùng yêu cầu hoặc khai thác hai worker chạy đồng thời. Catalog cần diễn đạt business invariants, quyền theo đối tượng, state machine, transaction và idempotency đủ rõ để các đường xử lý cùng thực thi được.

Bài học dùng hệ thống hoàn tiền có phê duyệt làm ví dụ tổng hợp. Các trạng thái, định danh, quyền và số tiền minh họa là lựa chọn của mô hình học tập; quy tắc thực tế phải được xác nhận với chủ thể nghiệp vụ có thẩm quyền. Mục tiêu của catalog là tạo hợp đồng kiểm tra được và có thể truy vết tới hiện thực, bằng chứng và kiểm thử.

## 1. Danh mục này giải quyết vấn đề gì?

### 1.1. Quy tắc phân tán tạo khoảng trống thực thi

Một hệ thống có thể đang giữ các phần của cùng quy tắc ở nhiều nơi:

- Giao diện ẩn nút hoàn tiền đối với nhân viên không có quyền.
- API kiểm tra role nhưng chưa kiểm tra đơn thuộc tenant nào.
- Worker chỉ thấy `APPROVED` mà không biết approval duyệt version nào.
- Database chống trùng một bản ghi nhưng không ngăn hai giao dịch ở provider.
- Test chỉ kiểm tra luồng hợp lệ, không có ca đổi amount hoặc chạy đồng thời.
- Runbook cho phép vận hành sửa trạng thái mà không nói điều kiện và quyền áp dụng.

Catalog gom **ý nghĩa chuẩn của quy tắc** vào một chỗ có quản lý, rồi chỉ ra những nơi phải thực thi nó. Việc ghi quy tắc vào tài liệu không tự làm hệ thống an toàn; giá trị xuất hiện khi có liên kết kiểm tra được giữa tài liệu và hành vi của mọi đường vào.

### 1.2. Phân biệt quy tắc với các loại tài liệu liên quan

| Thành phần | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Quy tắc nghiệp vụ | Điều gì phải đúng? | Nội dung hoàn tiền được thực hiện phải khớp snapshot đã duyệt |
| Tham số chính sách | Giá trị nào đang áp dụng trong phạm vi nào? | Hạn mức phê duyệt của nhóm, thời hạn approval |
| State machine | Những chuyển trạng thái nào được phép? | Chỉ từ `APPROVED` mới được chấp nhận thực hiện |
| Thiết kế kỹ thuật | Bảo vệ quy tắc bằng cách nào? | Kiểm tra version và giữ chỗ trong một database transaction |
| Hợp đồng API | Người gọi gửi/nhận gì? | Trường request, mã kết quả và cách tra cứu intent |
| Runbook | Người vận hành xử lý một tình huống thế nào? | Đối soát intent chưa xác định kết quả |
| Kiểm thử | Bằng chứng nào cho thấy hiện thực giữ quy tắc trong kịch bản cụ thể? | Đổi amount sau duyệt bị chặn mà không phát lệnh tiền |

Các tài liệu có thể tham chiếu nhau nhưng không thay thế nhau. Một endpoint trả `409` chưa mô tả được lý do nghiệp vụ; một unique constraint cũng chưa nói ai có quyền tạo nghiệp vụ đó.

## 2. Phân loại quy tắc trước khi viết

### 2.1. Các nhóm quy tắc thường cần có

| Nhóm | Dạng phát biểu | Ví dụ |
|---|---|---|
| Bất biến nghiệp vụ | Luôn phải giữ ở các trạng thái được công bố theo mô hình | Tổng đã hoàn và giữ chỗ không vượt hạn mức hoàn của đơn |
| Quyền theo đối tượng | Subject được phép với action trên resource trong phạm vi xác định | Nhân viên tenant A không thực hiện hoàn tiền đơn tenant B nếu không có quyền liên tenant được quy định |
| Tiền điều kiện | Phải đúng trước một bước cụ thể | Có approval còn hiệu lực cho đúng snapshot khi chấp nhận thực hiện |
| Chuyển trạng thái | Bước hiện tại cho phép đi tới đâu và với điều kiện gì | `APPROVED → EXECUTION_PENDING` sau khi giữ chỗ thành công |
| Tính bất biến của nội dung | Những trường nào không được đổi từ một mốc nhất định | Payload thực thi không đổi sau khi đã chấp nhận |
| Chống lặp | Cùng identity/yêu cầu được xử lý lại thế nào? | Cùng key và cùng payload trả về cùng intent đã chấp nhận |
| Ghi nhận và đối soát | Kết quả đã xảy ra cần được phản ánh thế nào? | Provider thành công phải được liên kết tới ghi nhận nội bộ tương ứng |
| Ngoại lệ có thẩm quyền | Khi nào được đi qua một quy trình xử lý khác? | Điều chỉnh một sai lệch qua nghiệp vụ riêng có phê duyệt và audit |

Một quy tắc có thể liên quan nhiều nhóm, nhưng nên có một khẳng định chính để dễ xác định đạt hay vi phạm. Tách “ai được duyệt” khỏi “approval duyệt nội dung nào”, rồi liên kết hai quy tắc, sẽ rõ hơn ghép mọi điều kiện thành một đoạn dài không có điểm kiểm tra riêng.

### 2.2. Đừng chỉ liệt kê các kiểm tra đầu vào

`amount > 0` là cần thiết nhưng chưa đủ để bảo vệ nghiệp vụ hoàn tiền. Catalog còn phải trả lời amount có nguồn nào, có đúng currency không, còn hạn mức không, có được duyệt không và đã tạo hiệu ứng trước đó chưa.

Tương tự, dữ liệu request chứa `tenantId`, `unitPrice` hoặc `approved=true` không làm chúng thành nguồn có thẩm quyền. Quy tắc phải chỉ rõ hệ thống đọc tenant của đối tượng, giá đã chấp nhận hoặc quyết định phê duyệt từ đâu và xử lý mâu thuẫn thế nào.

## 3. Cấu trúc một mục quy tắc có thể triển khai được

### 3.1. Những trường nên mô tả

| Trường | Nội dung cần viết |
|---|---|
| ID và tên | Định danh bền vững, tên thể hiện một khẳng định chính |
| Mục đích/rủi ro | Lạm dụng hoặc sai lệch mà quy tắc ngăn chặn |
| Phát biểu chuẩn | Điều kiện bắt buộc, tránh từ mơ hồ như “hợp lệ”, “thích hợp” khi chưa định nghĩa |
| Phạm vi | Tenant, loại đối tượng, action, kênh và ngoại lệ thực sự được phép |
| Dữ liệu có thẩm quyền | Nguồn của identity, amount, currency, quan hệ sở hữu, policy và approval |
| Mốc đánh giá | Lúc tạo, duyệt, chấp nhận thực hiện, phát lệnh hay ghi nhận kết quả |
| Điều kiện và kết quả | Khi đạt, không đạt hoặc chưa xác định thì làm gì; có hiệu ứng nào được phép xảy ra |
| Ranh giới đồng thời | Dữ liệu nào phải được kiểm tra/cập nhật nguyên tử; giả định với hệ thống ngoài |
| Điểm thực thi | API, service, worker, database hoặc công cụ vận hành phải giữ quy tắc |
| Bằng chứng | Trường dữ liệu và liên kết cần để kiểm tra quyết định/thay đổi |
| Kiểm thử | Ca hợp lệ, ca lạm dụng, replay, gián đoạn và cuộc đua liên quan |
| Quản lý thay đổi | Chủ thể nghiệp vụ, người bảo trì, version, mốc hiệu lực, trạng thái và quy tắc thay thế |

Không phải mọi mục đều cần một đoạn dài ở từng trường. Có thể tham chiếu định nghĩa dùng chung, miễn là người đọc biết chính xác định nghĩa nào và version nào được áp dụng. ID nên giữ ổn định khi tên hiển thị hoặc vị trí chương thay đổi; quy tắc bị thay thế cần giữ lịch sử thay vì xóa mọi dấu vết.

### 3.2. Viết phạm vi đủ hẹp để không diễn giải tùy ý

So sánh hai cách viết:

> Chỉ người có quyền được hoàn tiền.

> Khi chấp nhận `REFUND_EXECUTE`, danh tính hiệu lực phải có quyền thực hiện trên đơn thuộc tenant tương ứng; hệ thống xác định quan hệ này từ dữ liệu có thẩm quyền và chuỗi ủy quyền hợp lệ. Vi phạm làm từ chối chấp nhận, không tạo giữ chỗ hoặc công việc gửi lệnh từ yêu cầu ấy.

Cách thứ hai chỉ ra action, đối tượng, mốc kiểm tra, nguồn và hậu quả. Nếu có hỗ trợ thao tác liên tenant hoặc ủy quyền, phải dẫn tới quy tắc cụ thể cho phép nó; không dùng một cờ `admin` như ngoại lệ không giới hạn.

### 3.3. Phân biệt điều kiện không đạt với điều kiện chưa biết

Ví dụ timeout provider là chưa biết kết quả, khác provider xác nhận thất bại cuối cùng cho đúng intent. Không tìm thấy lịch sử role cũng khác có bằng chứng role bị cấm tại mốc cần xét.

Catalog cần mô tả hành vi với trạng thái chưa xác định: giữ reservation hay không, có được retry không, tra cứu theo identity nào, khi nào vào luồng ngoại lệ. Nếu chỉ có hai nhánh “thành công/thất bại”, đội triển khai dễ chọn một nhánh làm mất bất biến tiền hoặc cấp quyền quá mức.

## 4. Định nghĩa thuật ngữ và mô hình trước khi lập danh mục

### 4.1. Các identity không thể thay thế nhau

```text
tenant + order:         phạm vi và đối tượng nguồn
refund intent:         ý định hoàn tiền bền vững
contentVersion:        phiên bản nội dung nghiệp vụ cần duyệt
stateVersion:          phiên bản dùng bảo vệ cập nhật trạng thái/đồng thời
approval:              quyết định duyệt một snapshot xác định
attempt:               một lần thử xử lý ý định đã chấp nhận
idempotency key:       khóa chống lặp trong phạm vi thao tác đã quy định
provider transaction:  hiệu ứng bên ngoài, có phạm vi provider/merchant
posting group:        nhóm ghi nhận nội bộ cho một hiệu ứng nghiệp vụ
```

`contentVersion` và `stateVersion` không mặc định là cùng một trường. Tăng version do callback cập nhật trạng thái không nhất thiết làm thay đổi nội dung đã được duyệt. Nếu dự án dùng một version chung, catalog phải nêu cách ràng buộc approval để không vô hiệu hóa nhầm hoặc bỏ sót sửa nội dung.

`traceId` hỗ trợ quan sát nhưng không thay thế business identity: retry, callback và worker thường có trace khác nhau. Provider transaction ID cũng có thể chỉ duy nhất trong một merchant account, nên phạm vi là một phần của cách liên kết.

### 4.2. State machine minh họa

| Trạng thái | Ý nghĩa | Chuyển tiếp chính trong mô hình |
|---|---|---|
| `DRAFT` | Nội dung chưa được gửi duyệt | `SUBMITTED` hoặc `CANCELLED` |
| `SUBMITTED` | Đang chờ quyết định duyệt | `APPROVED`, sửa nội dung về `DRAFT`, hoặc `CANCELLED` |
| `APPROVED` | Có approval cho nội dung cụ thể | `EXECUTION_PENDING`, sửa nội dung về `DRAFT`, hoặc `CANCELLED` |
| `EXECUTION_PENDING` | Đã chấp nhận snapshot thực thi, đang giữ chỗ; kết quả cuối chưa được ghi nhận | `SUCCEEDED` hoặc `FAILED_FINAL` khi đủ bằng chứng theo hợp đồng |
| `SUCCEEDED` | Hiệu ứng thành công và ghi nhận nội bộ tương ứng đã được áp dụng | Không sửa lịch sử để trở về trạng thái trước thực thi |
| `FAILED_FINAL` | Đã xác nhận thất bại cuối cùng và xử lý giữ chỗ đúng hợp đồng | Không tái sử dụng trạng thái này để gửi một lệnh tiền mới tùy tiện |
| `CANCELLED` | Hủy trước lúc chấp nhận thực hiện theo mô hình này | Không phát lệnh hoàn từ hồ sơ đã hủy |

Mô hình gộp trường hợp đã gửi nhưng chưa rõ kết quả vào `EXECUTION_PENDING`; có thể thêm trạng thái chi tiết trong hệ thống thực. Cờ `REVIEW` hoặc work item ngoại lệ không làm mất trạng thái tài chính và số tiền đang giữ chỗ.

Sửa trường nghiệp vụ quan trọng trước khi thực thi làm tăng `contentVersion`, chuyển về `DRAFT` và khiến approval cũ không còn cấp phép cho nội dung mới. Sau khi chấp nhận thực hiện, payload bất biến; thay đổi hoặc sửa hậu quả phải qua quy trình riêng, không đổi amount trên lệnh đã chấp nhận.

### 4.3. Quyền và phê duyệt được xét ở thời điểm nào?

Trong ví dụ này, quyền người gọi, hiệu lực approval và ràng buộc snapshot được kiểm tra lúc **chấp nhận thực hiện**, cùng transaction bảo vệ reservation. Worker thực hiện snapshot đã chấp nhận; việc requester đổi role sau mốc ấy không tự viết lại quyết định cũ. Những hạn chế vận hành bắt buộc kiểm tra trước phát lệnh, nếu có, phải được ghi thành quy tắc riêng.

Đây là lựa chọn hợp đồng của mô hình, không phải mặc định cho mọi nghiệp vụ. Hệ thống yêu cầu thu hồi quyền phải ngăn lệnh chưa gửi cần mô tả rõ mốc hiệu lực, đường worker kiểm tra và cách xử lý cuộc đua với việc gửi ra ngoài. Không thể chỉ ghi “luôn kiểm tra quyền” rồi để mỗi thành phần tự chọn thời điểm khác nhau.

## 5. Danh mục mẫu cho nghiệp vụ hoàn tiền

### 5.1. Danh sách quy tắc và phạm vi chính

| ID | Phát biểu chính | Mốc áp dụng |
|---|---|---|
| `BLS-REF-001` | Action chỉ được thực hiện trên đối tượng mà danh tính hiệu lực có quyền trong phạm vi tenant/ủy quyền cho phép | Các action tạo, sửa, duyệt, chấp nhận thực hiện và xử lý ngoại lệ tương ứng |
| `BLS-REF-002` | Người duyệt đáp ứng quyền/hạn mức và phân tách nhiệm vụ của quy trình | Lúc duyệt snapshot |
| `BLS-REF-003` | Snapshot được chấp nhận thực thi khớp nội dung và version đã được duyệt còn hiệu lực | Lúc chấp nhận thực hiện |
| `BLS-REF-004` | Chấp nhận và ghi nhận hoàn tiền giữ đúng bất biến hạn mức của đơn | Các transaction thay đổi giữ chỗ và tổng đã hoàn |
| `BLS-REF-005` | Chỉ chuyển trạng thái theo state machine; payload đã chấp nhận không bị sửa | Mọi đường cập nhật trạng thái/nội dung |
| `BLS-REF-006` | Xử lý lặp không tạo thêm ý định hoặc hiệu ứng ngoài hợp đồng của cùng nghiệp vụ | API chấp nhận, worker, callback, retry và đối soát |
| `BLS-REF-007` | Kết quả được ghi nhận từ bằng chứng đúng identity và nội dung, không áp dụng lặp hoặc che sai lệch | Ghi nhận provider result, posting và xử lý ngoại lệ |

Đây là tập nhỏ để minh họa cấu trúc, chưa phải danh sách đầy đủ cho mọi hệ thống thanh toán. Các điều kiện chung như amount dương, currency hỗ trợ, nguồn thu còn hợp lệ và dữ liệu đầu vào có cấu trúc đúng cũng cần có định nghĩa và liên kết phù hợp trong catalog thực tế.

### 5.2. Hai quy tắc không thể thay thế nhau

Một nhân viên có quyền với đơn vẫn không được dùng approval 40.000 VND để thực hiện 400.000 VND: `BLS-REF-001` không thay thế `BLS-REF-003`.

Một amount nằm trong hạn mức vẫn có thể thiếu phê duyệt: `BLS-REF-004` không thay thế `BLS-REF-003`. Một nhóm posting cân bằng cũng không chứng minh lệnh được cấp quyền đúng: `BLS-REF-007` không thay thế các quy tắc quyền và phê duyệt.

Liên kết giữa các quy tắc giúp thể hiện điều kiện phải đồng thời thỏa mãn, không biến một kiểm tra đạt thành lý do bỏ qua các kiểm tra còn lại.

## 6. Đặc tả sâu: ràng buộc nội dung được duyệt

### 6.1. `BLS-REF-003` ở dạng có cấu trúc

YAML sau là ví dụ nội dung tài liệu cho một quy tắc, không phải schema bắt buộc của mọi dự án:

```yaml
ruleId: BLS-REF-003
title: Snapshot thực thi phải khớp nội dung được duyệt
ruleVersion: 1
status: ACTIVE
businessOwner: Vai trò chịu trách nhiệm chính sách hoàn tiền
technicalOwner: Nhóm chịu trách nhiệm dịch vụ hoàn tiền
appliesTo:
  action: ACCEPT_REFUND_EXECUTION
  channels: [customer_api, admin_api, batch, internal_service]
evaluationPoint: Transaction chấp nhận thực hiện
authoritativeInputs:
  - Intent và contentVersion từ kho dữ liệu nghiệp vụ
  - Approval snapshot và lịch sử hủy/hiệu lực
  - Thời điểm đánh giá theo hợp đồng thời gian của dịch vụ
requiredConditions:
  - Approval thuộc đúng tenant và intent
  - Approval duyệt đúng contentVersion được chấp nhận
  - Order, nguồn thu, amount và currency khớp snapshot được duyệt
  - Approval còn hiệu lực và chưa bị hủy tại mốc đánh giá
onPass:
  - Cho phép tiếp tục các kiểm tra bắt buộc khác
onFail:
  - Từ chối chấp nhận thực hiện
  - Không tạo reservation hoặc outbox thực thi từ yêu cầu này
onUnknown:
  - Không chấp nhận thực hiện khi chưa xác minh được approval bắt buộc
concurrencyBoundary:
  - Kiểm tra version và chấp nhận snapshot theo cùng cơ chế transaction
  - Cuộc đua sửa hoặc hủy approval phải có thứ tự quyết định rõ ràng
evidence:
  - Intent identity và contentVersion
  - Approval identity và snapshot được duyệt
  - Quyết định kiểm tra và thời điểm đánh giá
  - Snapshot thực thi cùng reservation/outbox đã commit nếu được chấp nhận
tests:
  - TC-REF-003-A
  - TC-REF-003-B
  - TC-REF-003-C
```

Vai trò chủ sở hữu trong ví dụ cần được ánh xạ sang người/nhóm chịu trách nhiệm thực tế. Các ID test phải dẫn được tới kiểm thử đang có hoặc được đánh dấu là chưa hiện thực; một danh sách ID tự nó chưa chứng minh độ bao phủ.

### 6.2. Bảng ví dụ và phản ví dụ

| Approval | Yêu cầu chấp nhận | Kết quả của quy tắc |
|---|---|---|
| Intent v3, 40.000 VND, đúng order, còn hiệu lực | Cùng v3 và cùng nội dung | Đạt quy tắc này; vẫn phải kiểm tra quyền, hạn mức và trạng thái |
| Intent v3, 40.000 VND | Intent v4, 400.000 VND | Không đạt; không tạo reservation/outbox thực thi |
| Intent v3, 40.000 VND | 40.000 VND nhưng khác order hoặc nguồn thu | Không đạt dù amount bằng nhau |
| Intent v3, còn hiệu lực ở lần đọc cũ nhưng đã bị hủy trước mốc chấp nhận | Cùng nội dung | Không đạt theo thứ tự commit/kiểm tra được hợp đồng quy định |
| Không đọc được approval bắt buộc | Request khai `approved=true` | Chưa xác minh được; không dùng cờ từ request thay bằng chứng |

Không chỉ kiểm tra một fingerprint nếu chưa định nghĩa những trường nào tham gia và cách chuẩn hóa. Nếu dùng fingerprint cho snapshot, phải có quy tắc canonicalization, version và khả năng truy lại nội dung; fingerprint không tự chứng minh người duyệt có thẩm quyền.

## 7. Đặc tả hạn mức, transaction và idempotency

### 7.1. `BLS-REF-004`: hạn mức là quy tắc có phạm vi đồng thời

Gọi `R` là tổng hạn mức hoàn được phép của một đơn trong cùng currency, `F` là tổng đã ghi nhận hoàn thành công và `P` là tổng giữ chỗ cho các intent chưa có kết quả cuối:

```text
F >= 0
P >= 0
F + P <= R

Chấp nhận khoản mới A:
    A > 0
    F + P + A <= R
    P_mới = P + A

Ghi nhận thành công khoản A đang giữ chỗ:
    F_mới = F + A
    P_mới = P - A

Ghi nhận thất bại cuối cùng của khoản A:
    F_mới = F
    P_mới = P - A
```

Các phép cập nhật chỉ được áp dụng đúng một lần cho intent tương ứng trong thiết kế này. Dữ liệu đọc để xét hạn mức và thay đổi reservation phải có cơ chế transaction/đồng thời bảo vệ toàn bộ phạm vi đơn liên quan, không chỉ khóa riêng intent mới.

Nếu đơn có `R = 100.000`, `F = 30.000`, `P = 40.000`, khả dụng là 30.000 VND. Hai worker không được cùng chấp nhận hai intent mới 20.000 chỉ vì mỗi worker đều từng đọc thấy còn 30.000. Catalog phải nêu kết quả bắt buộc: chỉ có thể chấp nhận lượng tiền phù hợp, và mọi attempt không được chấp nhận không tạo giữ chỗ hoặc lệnh tiền riêng.

Chuyển giữ chỗ sang đã hoàn trong cùng transaction local giữ tổng `F + P` không đổi. Nếu sổ hoặc reservation nằm ở dịch vụ khác, cần đặc tả giao thức chuyển tiếp, công việc bền vững và bất biến theo từng giai đoạn. Một transaction trong service không tự bao trùm provider hoặc dịch vụ sổ tiền.

Amount phải có biểu diễn chính xác và đơn vị/currency xác định. Không cộng lẫn currency hoặc dùng số thực dấu phẩy động để xét hạn mức. Quy tắc cũng phải xác định nguồn của `R` và những đường nào được phép thay đổi `R`, để một thao tác điều chỉnh hạn mức không vượt ra ngoài bảo vệ đồng thời.

Trường hợp provider đã tạo hiệu ứng ngoài hợp đồng cần được ghi nhận đúng sự thật và đưa vào ngoại lệ. Không bỏ giao dịch khỏi sổ hoặc sửa amount chỉ để công thức nội bộ trông vẫn đúng. Bất biến là điều hệ thống phải bảo vệ và phát hiện vi phạm, không phải lý do che bằng chứng về một vi phạm đã xảy ra.

### 7.2. `BLS-REF-006`: nói rõ cùng một yêu cầu nghĩa là gì

Một hợp đồng idempotency minh họa cho bước chấp nhận:

| Thành phần | Quy định trong ví dụ |
|---|---|
| Phạm vi key | Tenant + loại thao tác chấp nhận + idempotency key |
| Nội dung liên kết | Identity intent, contentVersion, order, nguồn thu, amount, currency và các trường ảnh hưởng quyết định đã định nghĩa |
| Cùng key, cùng nội dung | Trả/tra cứu cùng kết quả chấp nhận hoặc cùng intent theo hợp đồng; không tạo giữ chỗ mới |
| Cùng key, khác nội dung | Báo xung đột; không chấp nhận một intent hoặc payload thay thế âm thầm |
| Hai request đồng thời | Chỉ một quyết định chấp nhận cho phạm vi ấy được commit; request còn lại đọc kết quả hoặc nhận phản hồi theo hợp đồng |
| Tra cứu kết quả cũ | Vẫn kiểm tra quyền truy cập đối tượng; biết key không tự cho quyền xem dữ liệu |
| Thời hạn bảo vệ | Ghi rõ chính sách lưu key/danh tính và hành vi khi không còn đủ căn cứ chống trùng |

Không dùng order ID như khóa duy nhất của mọi khoản hoàn nếu nghiệp vụ cho phép nhiều khoản hoàn một phần. Cũng không coi một key mới là bằng chứng có một ý định nghiệp vụ mới được phép. `intentId` bền vững và quy tắc phê duyệt/hạn mức tiếp tục bảo vệ nghiệp vụ bên dưới lớp request.

Với provider, catalog phải tham chiếu đúng phạm vi và thời hạn idempotency của hợp đồng adapter. Giữ nguyên chuỗi key sau khi thời hạn bảo vệ đã hết không tự bảo đảm lệnh không tạo hiệu ứng mới. Khi kết quả cũ chưa xác định và thiếu điều kiện retry an toàn, mô hình phải giữ trạng thái chưa kết thúc, đối soát hoặc chuyển ngoại lệ thay vì tự phát lệnh thay thế.

### 7.3. `BLS-REF-007`: ghi nhận phải có căn cứ và chống lặp

Ghi nhận kết quả cần xác minh provider/merchant scope, business reference hoặc identity liên kết, amount, currency và trạng thái có ý nghĩa theo hợp đồng. Callback hợp lệ về nguồn không tự chứng minh nội dung khớp intent; một thông báo cũ không được kéo trạng thái thành công lùi về đang xử lý.

Khi ghi nhận thành công trong mô hình database local, nhóm posting nghiệp vụ, chuyển reservation và cập nhật trạng thái cần được bảo vệ theo transaction cùng ràng buộc identity. Một nhóm posting có thể có nhiều dòng debit/credit; không quy định sai rằng mỗi khoản hoàn luôn chỉ có một dòng sổ.

Nếu có hai giao dịch provider thành công cho một intent chỉ được phép một khoản hoàn, quy tắc phải yêu cầu nhận diện sai lệch đầy đủ. Không chỉ lấy giao dịch mới nhất hoặc xóa một dòng để làm báo cáo “khớp”. Điều chỉnh/bù trừ là nghiệp vụ riêng có quyền, lý do, audit và chống lặp của chính nó.

## 8. Ánh xạ quy tắc tới điểm thực thi

### 8.1. Một danh sách quy tắc cần nhiều điểm bảo vệ

| Đường xử lý | Trách nhiệm chính trong mô hình |
|---|---|
| Tạo/sửa intent | Xác minh quyền đối tượng; lấy dữ liệu có thẩm quyền; tăng contentVersion và vô hiệu hóa khả năng dùng approval cũ khi nội dung đổi |
| Duyệt | Kiểm tra quyền/hạn mức người duyệt, phân tách nhiệm vụ và snapshot được duyệt |
| Chấp nhận thực hiện | Kiểm tra quyền, approval, state, version, idempotency và giữ chỗ nguyên tử theo phạm vi |
| Worker gửi lệnh | Dùng payload đã chấp nhận; giữ identity/idempotency; áp dụng quy tắc hạn chế trước phát lệnh nếu hợp đồng có quy định |
| Callback/tra cứu kết quả | Xác thực nguồn phù hợp, liên kết đúng identity/nội dung; ghi nhận idempotent và không lùi trạng thái sai |
| Job đối soát | Tìm thiếu/mâu thuẫn, ghi nhận hiệu ứng đã xác nhận đúng quyền; không tự tạo ý định tiền mới |
| API quản trị/batch/công cụ vận hành | Giữ các điều kiện tương ứng hoặc đi qua quy trình ngoại lệ được đặc tả; không có đường bỏ qua chung |
| Database | Bảo vệ tính duy nhất, quan hệ và thay đổi nguyên tử theo thiết kế; không thay thế toàn bộ chính sách quyền nghiệp vụ |

Ẩn nút hoặc validate trên client chỉ hỗ trợ trải nghiệm. Quy tắc bắt buộc cần được giữ ở ranh giới phía hệ thống có thẩm quyền, bao gồm các đường không dùng giao diện.

Catalog nên dẫn tới component/command/schema constraint hoặc vùng mã có thể tìm được, thay vì nhúng một bản sao toàn bộ implementation. Nếu một component thay tên hoặc được tách service, cập nhật liên kết trong khi giữ nguyên ý nghĩa của rule ID.

### 8.2. Ghi rõ nhóm quy tắc cần một quyết định nguyên tử

Mã giả cho bước chấp nhận trong một database:

```text
BEGIN TRANSACTION
    kiểm_tra_quyền_và_phạm_vi_đối_tượng()
    đọc/khóa_hoặc_kiểm_tra_version_theo_phạm_vi_cần_bảo_vệ()
    xử_lý_key_idempotency_và_so_sánh_nội_dung_đã_chốt()
    xác_minh_state_và_snapshot_approval_còn_phù_hợp()
    kiểm_tra_hạn_mức_và_tạo_reservation_đúng_một_lần()
    chốt_payload_thực_thi_bất_biến()
    ghi_outbox_và_bằng_chứng_quyết_định_bền_vững()
COMMIT

worker chỉ xử lý công việc đã commit
```

Đây là ranh giới logic cần hiện thực hóa, không phải lời khẳng định rằng một loại khóa duy nhất phù hợp mọi schema. Khi approval bị hủy hoặc intent bị sửa đồng thời, hệ thống phải kiểm tra lại dữ liệu cần thiết tại thời điểm áp dụng quyết định; việc đã đọc đúng ở đầu request chưa đủ.

Đừng giữ transaction database mở qua cuộc gọi mạng chỉ để các bước trông tuần tự. Giao tiếp ngoài transaction cần giao thức riêng về dữ liệu bền vững, retry, kết quả chưa xác định và đối soát. Catalog phải ghi rõ phần nào nguyên tử local và phần nào cần hội tụ theo điều kiện đã nêu.

### 8.3. Bằng chứng giúp kiểm tra catalog có được thực thi không

Tùy quy tắc, cần nối được intent/contentVersion, approval snapshot, quyết định quyền/policy version, reservation/outbox đã commit, attempt, provider transaction và posting. Log `ALLOW` hoặc `SENT` không tự chứng minh toàn bộ chuỗi nghiệp vụ đúng.

Giữ riêng danh tính yêu cầu, người duyệt, worker và người xử lý ngoại lệ. Nếu cần ghi lại từ chối, đặc tả đường ghi bằng chứng không bị mất cùng transaction nghiệp vụ rollback. Thu thập đủ để kiểm tra quyết định, đồng thời giới hạn secret và dữ liệu cá nhân không cần thiết.

## 9. Chuyển catalog thành kiểm thử có oracle rõ ràng

### 9.1. Liên kết rule ID với ví dụ kiểm thử

| Test ID | Quy tắc chính | Tình huống và oracle |
|---|---|---|
| `TC-REF-001-A` | `BLS-REF-001` | Subject tenant B thao tác đơn tenant A ngoài mọi ủy quyền cho phép: bị chặn, không có thay đổi/hiệu ứng từ lần thử ấy |
| `TC-REF-002-A` | `BLS-REF-002` | Người tạo tự duyệt khi quy trình cấm: không tạo approval hợp lệ và không thể đi thẳng tới thực thi |
| `TC-REF-003-A` | `BLS-REF-003` | Approval đúng v3 và 40.000, các điều kiện khác thỏa mãn: chấp nhận đúng snapshot và giữ chỗ đúng |
| `TC-REF-003-B` | `BLS-REF-003` | Duyệt v3 40.000, sửa v4 400.000 rồi dùng approval cũ: từ chối chấp nhận, không tạo lệnh 400.000 |
| `TC-REF-003-C` | `BLS-REF-003`, `BLS-REF-005` | Sửa/hủy approval tranh chấp với chấp nhận: chỉ kết quả phù hợp thứ tự quyết định hợp lệ được commit |
| `TC-REF-004-A` | `BLS-REF-004` | Hai intent 20.000 tranh phần khả dụng 30.000: không chấp nhận cả hai; tổng hạn mức giữ đúng |
| `TC-REF-005-A` | `BLS-REF-005` | Sửa amount sau `EXECUTION_PENDING`: payload đã chấp nhận không đổi, không phát lệnh với amount mới |
| `TC-REF-006-A` | `BLS-REF-006` | Gửi lại cùng key/cùng payload: cùng intent, không tăng reservation hoặc số hiệu ứng trái hợp đồng |
| `TC-REF-006-B` | `BLS-REF-006` | Cùng key/khác payload: báo xung đột, không âm thầm sinh ý định thay thế |
| `TC-REF-007-A` | `BLS-REF-007` | Callback thành công giao hai lần và đảo với sự kiện cũ: một lần ghi nhận hiệu ứng, giữ chỗ được chuyển đúng, trạng thái không lùi |
| `TC-REF-007-B` | `BLS-REF-006`, `BLS-REF-007` | Provider thành công rồi mất phản hồi: đối soát đúng giao dịch cũ, không hoàn thêm |

Các ID này là ví dụ thiết kế; catalog của dự án phải đánh dấu rõ test đã hiện thực, đã chạy hay còn thiếu. Không dùng một ô “có test” để thay thế bằng chứng kết quả của bộ kiểm thử liên quan.

### 9.2. Dùng điểm dừng kiểm soát cho test tranh chấp

Với `TC-REF-003-C`, cho đường A đọc approval v3 rồi dừng trước bước chấp nhận. Cho đường B cố sửa nội dung hoặc hủy approval, sau đó mới cho A tiếp tục. Kiểm tra version, thứ tự commit, reservation, payload outbox và lịch sử fake provider.

Trong mô hình sửa nội dung của bài này, các kết quả hợp lệ có thể là:

- B sửa trước và commit nội dung mới về `DRAFT`: A không dùng approval v3 để chấp nhận phiên bản mới.
- A chấp nhận trước với snapshot v3 40.000: B không sửa payload đã chấp nhận; nếu thực thi thì chỉ dùng snapshot 40.000.

Không được có kết quả A dùng approval v3 nhưng gửi amount của v4. Chờ một khoảng thời gian tùy ý mà không xác nhận các mốc dễ làm test không thực sự tạo cuộc đua cần chứng minh.

### 9.3. Oracle phải vượt ra ngoài mã phản hồi

Đối với ca bị từ chối, đọc dữ liệu đã commit, reservation, outbox và hiệu ứng provider liên quan để kiểm tra không có tác động bị che sau phản hồi lỗi. Với ca retry, đếm giao dịch thực sự thành công, không chỉ đếm số request hoặc số dòng log.

Với bất biến tiền, kiểm tra các mốc trước/sau transaction và trạng thái đã commit; không coi giá trị tạm chưa công bố bên trong transaction là trạng thái hệ thống cho phép quan sát. Với kết quả chưa xác định, kiểm tra an toàn trước và hội tụ sau khi provider/database/worker đáp ứng các giả định phục hồi được nêu rõ.

Tách test quy tắc thuần, test database/transaction, test restart và test hợp đồng adapter theo điều cần chứng minh. Một test hàm trả `false` không chứng minh mọi đường gọi đã chặn trước hiệu ứng tiền.

## 10. Version, hiệu lực và thay đổi quy tắc

### 10.1. Tách rule version, policy parameter và phiên bản phần mềm

| Loại phiên bản | Ví dụ | Lý do cần phân biệt |
|---|---|---|
| Quy tắc | Approval phải gắn với contentVersion, thay cho cách chỉ kiểm tra trạng thái | Thay đổi ý nghĩa điều kiện được phép |
| Tham số chính sách | Hạn mức người duyệt theo nhóm/currency hoặc thời hạn approval | Cùng một dạng quy tắc nhưng giá trị áp dụng khác |
| Schema/hợp đồng dữ liệu | Thêm nguồn thu vào snapshot được duyệt | Thay đổi cách biểu diễn và kiểm tra nội dung |
| Phần mềm | Release thực thi rule version tương ứng | Cho biết phiên bản triển khai nào giữ quy tắc nào |

Một con số hạn mức không có đơn vị, currency, phạm vi và mốc hiệu lực sẽ gây cách hiểu khác nhau. Nếu quy tắc dùng ngưỡng, ghi cả dấu so sánh, ví dụ `amount <= approvalLimit`, cách xử lý bằng ngưỡng và nguồn tham số. Khi không lấy được policy bắt buộc, phải có hành vi đã đặc tả, không tự lấy một giá trị mặc định dễ cấp quyền rộng hơn.

Catalog cũng có vòng đời tài liệu như dự thảo, có hiệu lực, đang được thay thế hoặc đã ngừng áp dụng. Các trạng thái ấy khác state machine của refund intent; đừng dùng chung tên trường mà bỏ định nghĩa.

### 10.2. Thay đổi không được âm thầm viết lại quá khứ

Trước khi áp dụng version mới, xác định:

1. Những action nào bắt đầu dùng quy tắc mới và tại mốc nào.
2. Intent, approval và payload đã chấp nhận trước đó tiếp tục theo hợp đồng nào.
3. Có cần duyệt lại, chuyển dữ liệu, bổ sung snapshot hoặc đưa hồ sơ vào ngoại lệ không.
4. Hai phiên bản worker/API cùng chạy trong thời gian triển khai có giữ được bất biến không.
5. Khi rollback phần mềm, schema và dữ liệu đã tạo theo hợp đồng mới được xử lý ra sao.

Ví dụ thêm currency hoặc nguồn thu vào nội dung phải được duyệt không có nghĩa có thể tự điền dữ liệu thiếu vào approval cũ rồi coi như người duyệt đã chấp thuận. Cần quyết định chuyển tiếp có thẩm quyền và bằng chứng, thay vì thay đổi snapshot lịch sử.

Lưu version/policy liên quan ở mốc cần tái hiện quyết định. Dùng quyền hiện tại hoặc catalog mới nhất để xét mọi hành động trong quá khứ có thể cho kết luận sai.

### 10.3. Phát hiện độ lệch giữa tài liệu và hiện thực

Một thay đổi nghiệp vụ nên chỉ ra rule ID bị tác động, phát biểu mới, điểm thực thi thay đổi, dữ liệu/bằng chứng cần bổ sung và test xác minh. Khi catalog nói một quy tắc áp dụng cho batch nhưng batch không có đường thực thi tương ứng, đó là khoảng trống cần xử lý.

Có thể dùng kiểm tra tự động để phát hiện rule ID không còn liên kết, test tham chiếu quy tắc đã ngừng áp dụng hoặc thay đổi schema chưa cập nhật mô tả. Việc một chuỗi ID xuất hiện trong mã chỉ chứng minh có tham chiếu, chưa chứng minh quy tắc được thực thi đúng. Sinh tài liệu từ code cũng không thay thế xác nhận ý nghĩa nghiệp vụ bởi chủ thể có thẩm quyền.

## 11. Những cách viết dễ tạo lỗ hổng diễn giải

| Cách viết thiếu rõ ràng | Vấn đề | Cách làm rõ |
|---|---|---|
| “Chỉ admin được thực hiện” | Không rõ loại quyền, đối tượng, tenant và mốc xét | Nêu action, resource, phạm vi ủy quyền, dữ liệu quyền và thời điểm đánh giá |
| “Phải được phê duyệt” | Không biết approval duyệt amount/version nào | Liệt kê trường ràng buộc và cách sửa nội dung làm mất hiệu lực approval |
| “Không hoàn quá số đã thanh toán” | Chưa xử lý tiền đã hoàn, giữ chỗ, currency và tranh chấp | Định nghĩa `R`, `F`, `P`, nguồn dữ liệu và transaction theo phạm vi |
| “Không cho gửi trùng” | Không rõ trùng request, intent hay hiệu ứng provider | Định nghĩa identity, key scope, payload, thời hạn và hành vi replay |
| “Lỗi thì rollback” | Database không rollback được tiền đã đi ra bên ngoài | Chỉ rõ ranh giới local, trạng thái chưa xác định, đối soát và bù trừ |
| “Thông tin phải chính xác” | Không có nguồn thẩm quyền hoặc điều kiện đối chiếu | Chỉ rõ từng trường lấy từ đâu và xử lý mâu thuẫn thế nào |
| “Có ngoại lệ cho vận hành” | Có thể trở thành đường bỏ qua mọi kiểm soát | Đặc tả action ngoại lệ, quyền, phê duyệt, giới hạn và bằng chứng riêng |
| “Đã có test bảo mật” | Không biết ca nào kiểm tra rule nào và hiệu ứng nào | Liên kết test ID, oracle, phạm vi hiện thực và kết quả chạy |

Một số lỗi tổ chức khác cũng làm catalog nhanh mất giá trị: sao chép cùng quy tắc sang nhiều trang nhưng không có nguồn chuẩn; trộn yêu cầu bắt buộc với ý tưởng chưa được duyệt; chỉ ghi happy path; bỏ API quản trị/worker; xóa quy tắc cũ khiến không tái hiện được quyết định lịch sử.

Catalog nên có cách đánh dấu giả định và câu hỏi chưa chốt. Đừng biến giả định chưa được xác nhận thành phát biểu bắt buộc, hoặc ghi “sẽ bổ sung sau” rồi coi tất cả điểm thực thi đã hoàn tất.

## 12. Bài thực hành: lập catalog cho một luồng có thể bị lạm dụng

Chọn luồng hoàn tiền ở bài này hoặc một luồng sửa giá/duyệt đơn/cấp quyền có trạng thái rõ. Thực hiện lần lượt:

1. Liệt kê action, subject, resource, tenant, nguồn dữ liệu có thẩm quyền và các identity cần giữ qua retry/restart.
2. Vẽ hoặc lập bảng state machine; chỉ rõ mốc payload được chấp nhận và trường nào còn được phép sửa.
3. Viết các quy tắc riêng cho quyền đối tượng, thẩm quyền duyệt, nội dung được duyệt, hạn mức, chuyển trạng thái, chống lặp và ghi nhận kết quả.
4. Với mỗi quy tắc, ghi ID, mục đích, phát biểu chuẩn, phạm vi, mốc đánh giá, nguồn dữ liệu và hành vi khi không đạt/chưa xác định.
5. Chọn ít nhất một quy tắc có cuộc đua; mô tả dữ liệu nào phải bảo vệ chung và các kết quả hợp lệ khi hai thao tác đồng thời.
6. Ánh xạ quy tắc tới API, worker, database, batch và công cụ vận hành liên quan; nêu rõ chỗ chưa có bảo vệ.
7. Viết bảng test gồm ca hợp lệ, đổi nội dung sau duyệt, sai tenant, bỏ bước, request trùng, provider timeout và callback lặp.
8. Mô tả bằng chứng để người rà soát nối quyết định với snapshot, hiệu ứng tiền và ghi nhận nội bộ mà không cần tin vào một log tổng hợp.
9. Giả lập thay đổi policy khi còn intent đang xử lý; nêu version nào áp dụng cho quyết định nào và điều kiện chuyển tiếp.

Sản phẩm cần có catalog quy tắc, thuật ngữ/state machine dùng chung và ma trận truy vết tới điểm thực thi, bằng chứng, kiểm thử. Một người đọc phải chọn được bất kỳ quy tắc nào và trả lời: **nó bảo vệ điều gì, đánh giá trên dữ liệu nào tại mốc nào, được giữ ở đâu, thất bại thì xảy ra gì và bằng cách nào chứng minh hiện thực đang tuân theo**.
