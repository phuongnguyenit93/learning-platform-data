# Key management permission

## Mục tiêu bài học

Trong chương Application privilege của module Privileged Access Management (PAM), **key management permission** là tập quyền quyết định ai hoặc workload nào được sử dụng khóa mật mã, quản trị khóa và thay đổi các điều kiện cấp quyền đó. Đây là một dạng quyền đặc biệt của ứng dụng: một API giải mã, một tác vụ ký hoặc một thay đổi policy khóa đều có thể tạo tác động lớn dù người gọi không đăng nhập vào máy chủ bằng tài khoản quản trị.

Bài học tập trung vào thiết kế phân quyền và vận hành. Các tên hành động, policy và mã giả bên dưới là mô hình minh họa, không phải API hay cú pháp cấu hình của một sản phẩm KMS, HSM hoặc vault cụ thể.

Sau bài học, bạn có thể:

- Phân biệt quyền sử dụng khóa với quyền quản trị và quyền cấp lại quyền.
- Thiết kế quyền theo principal, hành động, khóa, môi trường và mục đích nghiệp vụ.
- Áp dụng least privilege, JIT, phân tách nhiệm vụ và dual control cho thao tác nhạy cảm.
- Tích hợp quyền khóa vào ứng dụng mà không biến backend thành một dịch vụ giải mã tùy ý.
- Xử lý rotation, thu hồi quyền, khôi phục và xóa khóa dựa trên phụ thuộc thực tế.
- Thu thập bằng chứng kiểm toán mà không đưa khóa hoặc dữ liệu rõ vào log.

## 1. Vì sao quyền với khóa là quyền đặc biệt?

Giả sử dữ liệu khách hàng được mã hóa trong cơ sở dữ liệu. Nhóm quản trị cơ sở dữ liệu không được đọc dữ liệu rõ. Nếu một thành viên của nhóm này có thể tự cấp quyền giải mã trên khóa bảo vệ dữ liệu, sự phân tách trên chỉ còn mang tính hình thức.

Tương tự, tài khoản vận hành có thể không được gọi API giải mã, nhưng lại được sửa policy của khóa để bổ sung chính nó vào danh sách được giải mã. Quyền sửa policy tạo ra đường leo thang quyền tương đương hoặc mạnh hơn quyền sử dụng khóa trực tiếp.

Vì vậy, phạm vi phân tích phải bao gồm ba lớp:

1. **Sử dụng khóa:** mã hóa, giải mã, ký, xác minh hoặc tạo vật liệu khóa phục vụ một luồng xử lý.
2. **Quản trị vòng đời:** tạo khóa, thay đổi trạng thái sử dụng, rotation, khôi phục và xóa.
3. **Quản trị thẩm quyền:** sửa policy, cấp grant, thay đổi nhóm được tin cậy hoặc đổi cấu hình định tuyến đến khóa.

Một workload được phép sử dụng khóa không mặc nhiên được quản trị khóa. Một người quản trị khóa cũng không nên mặc nhiên được sử dụng dữ liệu mà khóa bảo vệ.

### Khóa mật mã khác credential truy cập dịch vụ quản lý khóa

Credential có thể là token hoặc chứng nhận giúp workload xác thực tới KMS. Khóa mật mã là vật liệu dùng cho hoạt động mật mã. Hai đối tượng liên quan nhưng có vòng đời và quyền khác nhau:

- Đổi token truy cập KMS không đồng nghĩa đã thay khóa mã hóa dữ liệu.
- Rotation khóa mã hóa không tự động thu hồi credential bị lộ.
- Lưu credential KMS trong vault không bảo đảm policy KMS đã theo least privilege.
- Credential ngắn hạn vẫn nguy hiểm nếu nó được phép giải mã mọi khóa trong môi trường production.

PAM cần kiểm soát cả danh tính truy cập và khả năng thực hiện hành động sau khi danh tính đã được xác thực.

## 2. Phân loại quyền theo khả năng thực tế

Không nên đánh giá một quyền chỉ qua tên như “read”, “admin” hay “operator”. Hãy xác định hành động đó có thể tạo ra dữ liệu gì, thay đổi ai được truy cập và làm gián đoạn hệ thống nào.

| Nhóm hành động minh họa | Khả năng tạo ra | Rủi ro cần kiểm soát |
|---|---|---|
| Encrypt hoặc wrap | Mã hóa dữ liệu hoặc bọc một khóa khác | Lạm dụng tài nguyên; dùng sai khóa hoặc sai miền dữ liệu |
| Decrypt hoặc unwrap | Khôi phục dữ liệu rõ hoặc khóa ở lớp bên dưới | Đọc dữ liệu nhạy cảm; mở rộng phạm vi truy cập thực tế |
| Sign | Tạo chữ ký bằng khóa riêng | Ký giao dịch, token hoặc artifact trái thẩm quyền |
| Verify hoặc đọc public key | Kiểm tra chữ ký hoặc lấy thành phần công khai | Hiểu sai ý nghĩa tin cậy; dùng nhầm phiên bản hoặc mục đích khóa |
| Generate data key | Tạo khóa dữ liệu, có thể kèm bản rõ tùy giao diện | Làm lộ khả năng giải mã dữ liệu được bảo vệ bằng khóa đó |
| Create hoặc import | Tạo khóa, đưa vật liệu khóa vào hệ thống | Tạo khóa ngoài quy trình; sai nguồn gốc hoặc sai môi trường |
| Thay đổi policy hoặc grant | Thay đổi ai có thể dùng hay quản trị khóa | Tự cấp quyền; mở quyền xuyên nhóm, xuyên môi trường |
| Thay đổi alias hoặc cấu hình tham chiếu | Đổi khóa mà ứng dụng sẽ sử dụng | Chuyển luồng mã hóa hoặc ký sang khóa khác |
| Rotate hoặc thay phiên bản hoạt động | Thay đổi vật liệu dùng cho thao tác mới | Hiểu nhầm rằng dữ liệu cũ đã được chuyển đổi hoặc quyền cũ đã bị thu hồi |
| Disable | Dừng một số khả năng sử dụng khóa | Gây gián đoạn chức năng phụ thuộc |
| Lập lịch xóa hoặc xóa | Loại bỏ khả năng sử dụng khóa về sau | Mất khả năng khôi phục dữ liệu nếu không còn vật liệu cần thiết |
| Export, backup hoặc restore | Di chuyển hoặc phục hồi vật liệu và trạng thái khóa nếu hệ thống hỗ trợ | Tạo đường truy cập nằm ngoài kiểm soát trực tuyến |

Các hệ thống không cung cấp tất cả hành động giống nhau. Có loại khóa không cho export khóa riêng hoặc vật liệu khóa qua giao diện thông thường. Thiết kế quyền phải dựa vào khả năng mà sản phẩm thực sự cung cấp, thay vì giả định mọi khóa đều có thể tải xuống hoặc mọi thao tác backup đều tương đương export bản rõ.

### Quyền mã hóa và giải mã không đối xứng về tác động

Một dịch vụ thu thập dữ liệu có thể chỉ cần mã hóa để lưu trữ. Cấp thêm quyền giải mã “cho tiện” làm thay đổi ranh giới bảo mật: khi dịch vụ bị chiếm quyền, kẻ tấn công có thể đọc lại dữ liệu đã được bảo vệ.

Ngược lại, quyền mã hóa cũng không phải quyền vô hại. Một dịch vụ dùng sai khóa có thể tạo dữ liệu mà hệ thống đích không giải mã được. Vì vậy, mọi quyền vẫn cần giới hạn theo khóa, môi trường và chức năng.

Quyền ký cần được đánh giá riêng. Không nên suy luận rằng một dịch vụ có quyền giải mã thì cũng được ký, hoặc được ký một loại thông điệp thì được ký mọi dữ liệu đầu vào.

## 3. Hiểu đường đi của dữ liệu khi dùng envelope encryption

Trong một thiết kế envelope encryption, dữ liệu thường được mã hóa bằng một data key. Data key được bảo vệ bằng một khóa ở lớp quản lý khóa. Đây là mô hình để phân tích quyền; chi tiết thực hiện phụ thuộc giải pháp được chọn.

```text
Workload được xác thực
    |
    | yêu cầu được giới hạn theo key ID và ngữ cảnh
    v
Dịch vụ quản lý khóa
    |
    | cho phép mở data key đã được bọc
    v
Data key bản rõ trong vùng xử lý được phép
    |
    | giải mã đối tượng nghiệp vụ
    v
Dữ liệu rõ đến đúng người hoặc tác vụ đã được cấp quyền
```

Từ sơ đồ này có ba hệ quả.

**Thứ nhất, quyền unwrap một data key có thể trao khả năng đọc nhiều bản ghi.** Nếu nhiều đối tượng dùng chung data key, phạm vi ảnh hưởng không chỉ bằng một lần gọi KMS. Phải hiểu đơn vị bảo vệ của dữ liệu để xác định blast radius.

**Thứ hai, thu hồi quyền ở KMS không lấy lại được dữ liệu đã xuất ra.** Nó có thể ngăn những lần sử dụng khóa tiếp theo, nhưng không xóa bản rõ, data key hoặc kết quả ký mà principal đã nhận trước đó.

**Thứ ba, cache làm thay đổi thời gian thu hồi có hiệu lực đối với ứng dụng.** Nếu ứng dụng còn giữ data key bản rõ trong bộ nhớ, việc thu hồi quyền gọi KMS không nhất thiết chặn ngay các thao tác dùng cache. Cần giới hạn thời gian tồn tại, phạm vi cache và cách dừng workload trong quy trình ứng phó sự cố.

Không đưa data key bản rõ vào log, cấu hình, ticket, shell history hay tệp tạm để hỗ trợ vận hành. Nếu xuất hiện lỗi giải mã, thông tin cần điều tra là key ID, phiên bản liên quan, mã lỗi và correlation ID, không phải nội dung khóa.

## 4. Mô hình hóa một yêu cầu quyền khóa

Một mô hình đơn giản là:

```text
Yêu cầu = (
  principal,
  action,
  key_id,
  environment,
  application,
  business_scope,
  operation_id,
  conditions
)
```

Trong đó:

- **Principal** là danh tính con người hoặc workload đã được xác thực.
- **Action** là một hành động cụ thể như decrypt, sign hoặc sửa policy.
- **Key ID** là định danh khóa được kiểm soát, không chỉ một chuỗi do client tùy ý gửi.
- **Environment** phân biệt các ranh giới như phát triển, thử nghiệm và production.
- **Application** xác định dịch vụ nào đang sử dụng quyền.
- **Business scope** giới hạn tenant, tập dữ liệu, đối tượng hoặc loại giao dịch.
- **Operation ID** liên kết quyền với yêu cầu nghiệp vụ và bằng chứng thực thi.
- **Conditions** có thể gồm thời hạn, phương thức xác thực, trạng thái phê duyệt và nguồn truy cập được tin cậy.

Một quyết định cho phép chỉ đúng khi các thuộc tính quan trọng được xác minh từ nguồn có thẩm quyền. Không lấy tenant, role, trạng thái phê duyệt hoặc môi trường chỉ từ một header mà người gọi có thể sửa.

### Phải kiểm tra cả quyền ứng dụng và quyền trên khóa

Giả sử dịch vụ hồ sơ có quyền kỹ thuật giải mã dữ liệu của nhiều tenant. API của dịch vụ vẫn phải kiểm tra người gọi có được đọc hồ sơ cụ thể hay không.

```text
Người gọi được phép đọc hồ sơ X?
    |
    +-- Không --> Từ chối trước khi giải mã
    |
    +-- Có --> Workload có quyền dùng khóa bảo vệ X?
                  |
                  +-- Không --> Từ chối
                  |
                  +-- Có --> Giải mã trong luồng nghiệp vụ được phép
```

KMS xác thực workload không thay thế được kiểm tra quyền sở hữu đối tượng trong ứng dụng. Nếu backend chỉ kiểm tra “token hợp lệ” rồi giải mã mọi ciphertext do client gửi, nó có thể trở thành một dịch vụ giải mã trái phạm vi nghiệp vụ.

Cũng không nên trao cho người dùng cuối credential KMS rộng để họ tự thực thi thao tác mà ứng dụng lẽ ra phải kiểm soát.

## 5. Thiết kế vai trò và phân tách nhiệm vụ

Ma trận dưới đây là điểm xuất phát cho một hệ thống giả định. Mỗi ô “giới hạn” phải được cụ thể hóa thành khóa, môi trường, hành động và điều kiện có thể kiểm chứng.

| Vai trò | Sử dụng mật mã | Quản trị vòng đời | Thay đổi quyền | Xem bằng chứng |
|---|---|---|---|---|
| Dịch vụ tiếp nhận dữ liệu | Encrypt theo khóa được giao | Không | Không | Chỉ telemetry cần thiết của chính nó |
| Dịch vụ đọc nghiệp vụ | Decrypt theo luồng được giao | Không | Không | Chỉ telemetry cần thiết của chính nó |
| Dịch vụ ký artifact | Sign theo miền thông điệp được giao | Không | Không | Sự kiện của luồng ký |
| Nhóm vận hành khóa | Không mặc định | Giới hạn theo runbook | Không tự cấp quyền sử dụng | Có giới hạn |
| Nhóm quản trị policy | Không mặc định | Không mặc định | Thay đổi có phê duyệt và kiểm soát leo thang | Có giới hạn |
| Người phê duyệt nghiệp vụ | Không | Không | Chỉ phê duyệt trong thẩm quyền | Bằng chứng liên quan |
| Kiểm toán viên | Không | Không | Không | Chỉ đọc dữ liệu kiểm toán được phép |
| Người ứng cứu khẩn cấp | Theo phiên JIT được phê duyệt | Theo sự cố | Theo quy trình khẩn cấp | Theo phạm vi sự cố |

Một role có quyền sửa policy và quyền tự gán role cho chính mình có thể phá vỡ ma trận này. Phải phân tích toàn bộ đường cấp quyền, bao gồm quản trị danh tính, pipeline triển khai policy và quyền thay đổi nhóm.

### Dual control phải tạo ra hai quyết định độc lập

Đối với việc mở quyền giải mã production, xóa khóa hoặc phục hồi vật liệu khóa, có thể yêu cầu hai bên độc lập tham gia. Cần kiểm tra:

- Người yêu cầu không tự phê duyệt yêu cầu của mình.
- Người phê duyệt có thẩm quyền với đúng khóa và mục đích.
- Hai tài khoản thực sự thuộc hai chủ thể độc lập trong mô hình kiểm soát.
- Phê duyệt gắn với chính xác hành động và tham số được thực thi.
- Thay đổi phạm vi sau khi phê duyệt làm mất hiệu lực phê duyệt cũ.
- Pipeline triển khai không có đường ghi trực tiếp bỏ qua phê duyệt.

Hai lần bấm nút bởi cùng một người hoặc hai role mà cùng một principal tự chuyển qua lại không tạo ra sự phân tách nhiệm vụ có ý nghĩa.

## 6. Các lớp policy và đường leo thang cần rà soát

Một triển khai có thể kết hợp policy danh tính, policy trên khóa, grant, role workload và ràng buộc môi trường. Quy tắc kết hợp phụ thuộc sản phẩm; không được mặc định rằng chỉ cần nhìn một policy là biết quyền hiệu lực.

Khi cấp quyền, hãy trả lời được:

1. Principal nào có thể xác thực hoặc chuyển sang role được cấp quyền?
2. Policy nào cho phép hành động trên khóa?
3. Grant hoặc cơ chế ủy quyền nào bổ sung quyền?
4. Ràng buộc nào giới hạn ngữ cảnh và nguồn yêu cầu?
5. Ai có thể sửa các lớp kiểm soát trên?
6. Bằng chứng nào chứng minh principal có hoặc không có quyền tại thời điểm thực thi?

### Các quyền gián tiếp thường bị bỏ sót

- **Sửa alias:** có thể làm ứng dụng mới ghi dữ liệu bằng một khóa khác.
- **Sửa tag dùng cho phân quyền:** có thể làm khóa hoặc principal rơi vào một tập quyền rộng hơn.
- **Tạo grant:** có thể mở đường sử dụng khóa mà không sửa policy chính.
- **Thay workload identity:** có thể giúp một dịch vụ khác nhận role đang được phép giải mã.
- **Sửa pipeline:** có thể triển khai mã thu thập dữ liệu rõ bằng chính quyền hợp lệ của ứng dụng.
- **Restore từ backup:** có thể khôi phục cả trạng thái cấp quyền cũ nếu quy trình không rà soát lại.

Các khả năng này không phải lúc nào cũng tồn tại hoặc có cùng ý nghĩa trong mọi sản phẩm. Điều cần làm là lập bản đồ những đường thực tế dẫn đến quyền sử dụng khóa, thay vì chỉ kiểm tra một danh sách role.

### Khóa production và khóa thử nghiệm

Không dùng quyền truy cập khóa production để giải quyết lỗi trong môi trường phát triển. Cần tách các ranh giới danh tính và policy phù hợp, sử dụng dữ liệu thử nghiệm và tránh cấp wildcard chỉ vì nhiều khóa có cùng tiền tố tên.

Tên khóa hoặc alias có chứa “prod” không tự tạo ra ranh giới. Ranh giới phải được thực thi bằng cấu hình quyền, tài khoản hoặc miền quản trị tương ứng.

## 7. JIT cho quyền sử dụng và quản trị khóa

Không phải mọi lần giải mã nghiệp vụ đều cần một người phê duyệt. Một dịch vụ chạy liên tục thường cần quyền workload ổn định nhưng hẹp, gắn với chức năng của nó và được rà soát định kỳ. Ngược lại, thao tác đặc biệt của con người như giải mã phục vụ sự cố hoặc sửa policy production phù hợp với quyền JIT.

Một phiên cấp quyền JIT nên có:

| Thuộc tính | Ví dụ minh họa |
|---|---|
| Chủ thể | Người vận hành đã xác thực tăng cường |
| Mục đích | Điều tra một sự cố đã được ghi nhận |
| Hành động | Đọc kết quả giải mã của tập đối tượng đã chọn |
| Tài nguyên | Một key ID và danh sách đối tượng liên quan |
| Thời hạn | Khoảng thời gian ngắn do quy trình quy định |
| Giới hạn | Số đối tượng hoặc ngân sách thao tác phù hợp |
| Phê duyệt | Người có thẩm quyền nghiệp vụ và bảo mật theo mức rủi ro |
| Kết thúc | Tự hết hạn, thu hồi sớm và xác minh quyền hiệu lực |

Quyền hết hạn phải được kiểm tra tại thời điểm thực thi, không chỉ tại lúc mở màn hình. Đối với job chạy dài, cần quy định rõ khi nào nó phải xin lại quyền và cách dừng an toàn khi phạm vi cấp quyền không còn hợp lệ.

### Break-glass không đồng nghĩa phát hành khóa bản rõ

Quy trình khẩn cấp có thể cho phép một hành động khôi phục được kiểm soát mà không cung cấp vật liệu khóa cho người vận hành. Nên ưu tiên giao diện thao tác, role và runbook đã giới hạn thay vì mở shell quản trị rồi để người dùng tự gọi mọi API.

Đường khẩn cấp phải được diễn tập. Nếu việc truy cập PAM phụ thuộc vào chính hệ thống đang hỏng, cần có cơ chế dự phòng được thiết kế trước, xác thực độc lập phù hợp và khả năng đối soát bằng chứng sau khi khôi phục. Không biến việc mất một thành phần thành lý do bỏ toàn bộ kiểm soát.

## 8. Đưa quyền khóa vào luồng ứng dụng

Xét API xuất hồ sơ nhạy cảm trong một hệ thống nhiều tenant. Workload xuất dữ liệu có thể dùng khóa, nhưng người yêu cầu phải có quyền xuất đúng tập hồ sơ. Một phê duyệt xuất dữ liệu không được biến thành quyền gọi decrypt tùy ý.

Luồng hợp lý gồm:

1. Xác thực người yêu cầu và suy ra tenant từ ngữ cảnh tin cậy.
2. Tải đối tượng và xác minh quyền nghiệp vụ với từng đối tượng.
3. Xác định key ID từ metadata được bảo vệ của đối tượng.
4. Ràng buộc phê duyệt vào operation ID, tập đối tượng, hành động và đích nhận.
5. Kiểm tra quyền còn hiệu lực ngay trước mỗi đơn vị công việc nhạy cảm.
6. Gọi dịch vụ khóa bằng danh tính workload đã được giới hạn.
7. Chỉ chuyển kết quả tới đích được phê duyệt.
8. Ghi bằng chứng, xử lý retry và kết thúc quyền tạm thời nếu có.

Mã giả sau mô tả ranh giới kiểm soát, không phải thư viện mật mã có thể đưa vào production:

```text
function exportApprovedRecords(session, operationId):
    actor = authenticate(session)
    operation = loadOperation(operationId)

    require operation.requester == actor.id
    require operation.tenant == trustedTenant(actor)
    require operation.action == "EXPORT_RECORDS"

    plan = loadApprovedImmutablePlan(operation.planId)
    require plan.matches(operation)
    require plan.destination in allowedDestinations(actor, operation.tenant)

    lease = authorizeAndStartAtomically(
        operationId = operation.id,
        actor = actor,
        plan = plan,
        now = trustedClock()
    )

    for recordId in plan.recordIds:
        requireLeaseActive(lease, trustedClock())
        record = loadRecord(recordId)
        authorizeBusinessRead(actor, record)
        require record.tenant == plan.tenant

        keyRef = trustedKeyReference(record)
        require keyRef.id in plan.allowedKeyIds

        plaintext = decryptInsideWorkload(
            keyRef = keyRef,
            ciphertext = record.ciphertext,
            context = trustedEncryptionContext(record)
        )

        deliverToApprovedDestination(
            operationId = operation.id,
            recordId = record.id,
            destination = plan.destination,
            plaintext = plaintext
        )

        auditMetadataOnly(operation, record, keyRef, "DELIVERED")

    finishOperationAtomically(operation.id, lease)
```

Việc bắt đầu thao tác một cách nguyên tử nhằm tránh hai worker cùng tiêu thụ một quyền phê duyệt một lần. Tuy nhiên, nó không tự làm cho KMS, nơi lưu trạng thái job và đích nhận trở thành một giao dịch duy nhất.

Cần thiết kế thêm checkpoint và idempotency cho việc giao dữ liệu. Khi timeout sau khi đích nhận đã lưu kết quả, retry không được xuất thêm ngoài phạm vi đã duyệt. Nếu quyền hết hạn giữa job, dừng phần chưa xử lý và ghi trạng thái có thể đối soát; không giả định toàn bộ thao tác đã được rollback.

Trong triển khai thực, dữ liệu rõ và data key cần được giữ trong phạm vi xử lý nhỏ nhất, không bị ghi log, không bị giữ lại bởi cache hoặc chẩn đoán ngoài ý muốn. Khả năng xóa chắc chắn mọi bản sao trong bộ nhớ phụ thuộc runtime; không hứa rằng một lệnh gán biến hoặc thu gom bộ nhớ đã xóa hoàn toàn dữ liệu nhạy cảm.

## 9. Ràng buộc ngữ cảnh và tránh dùng khóa sai mục đích

Nhiều thiết kế hỗ trợ ngữ cảnh gắn với phép mã hóa hoặc điều kiện sử dụng khóa. Cần phân biệt:

- **Ngữ cảnh mật mã:** dữ liệu được liên kết với ciphertext để kiểm tra khi giải mã, tùy cơ chế được sử dụng.
- **Ngữ cảnh phân quyền:** thuộc tính mà policy dùng để quyết định cho phép hoặc từ chối.
- **Ngữ cảnh nghiệp vụ:** tenant, đối tượng, mục đích và thẩm quyền của người gọi.

Ba lớp có thể hỗ trợ nhau nhưng không tự thay thế cho nhau.

Ví dụ, một giá trị tenant gắn với ciphertext giúp phát hiện việc thay đổi ngữ cảnh nếu cơ chế mã hóa đã ràng buộc giá trị đó. Nó không chứng minh người gọi được đọc tenant ấy. Ứng dụng vẫn phải xác minh quyền và xây dựng ngữ cảnh từ metadata tin cậy.

Một mẫu cấu hình khái niệm:

```yaml
# Mô hình giảng dạy; không phải cấu hình triển khai của nhà cung cấp.
principal: workload:invoice-reader
action: decrypt
keyIds:
  - key:invoice-prod
conditions:
  environment: production
  application: invoice-service
  tenantSource: verified-identity-and-record
  purpose: read-authorized-invoice
delegation:
  allowPolicyChange: false
  allowGrantCreation: false
  allowKeyExport: false
```

Policy thực tế chỉ thực thi được những thuộc tính mà hệ thống hỗ trợ và xác minh được. Một KMS không biết “hóa đơn đã được người dùng cho phép đọc” chỉ vì ứng dụng gửi chuỗi purpose. Kiểm tra quyền nghiệp vụ phải nằm ở thành phần có đủ thông tin và không bị bỏ qua.

### Không đưa bí mật vào ngữ cảnh

Tên trường nghe như metadata không có nghĩa là nội dung được giữ bí mật. Các giá trị ngữ cảnh có thể xuất hiện trong log, truy vết hoặc dữ liệu vận hành.

Không dùng mật khẩu, token, dữ liệu cá nhân trực tiếp hoặc nội dung hồ sơ làm ngữ cảnh nếu không có thiết kế bảo vệ phù hợp. Sử dụng định danh tối thiểu và quy định rõ ai được đọc metadata.

### Tách mục đích của khóa

Nếu cùng một quyền ký cho phép phát hành cả artifact phần mềm lẫn thông điệp xác nhận giao dịch, việc kiểm soát nghiệp vụ sẽ khó hơn. Có thể tách khóa hoặc tách miền sử dụng, giao diện ký và policy để giảm phạm vi ảnh hưởng.

Dịch vụ ký không nên nhận một blob tùy ý rồi ký bằng bất kỳ key ID do client chọn. Nó cần xác minh loại thông điệp, cấu trúc, nguồn dữ liệu, mục đích sử dụng và quyền người gọi trước khi dùng khóa.

## 10. Quyền theo vòng đời khóa

### 10.1. Tạo và đưa khóa vào sử dụng

Trước khi cấp quyền cho workload, cần xác định:

- Chủ sở hữu chịu trách nhiệm về mục đích của khóa.
- Nhóm vận hành và nhóm phê duyệt thay đổi.
- Môi trường, ứng dụng và loại dữ liệu được phép sử dụng.
- Hành động mật mã cần thiết.
- Cách ứng dụng tham chiếu khóa và kiểm soát thay đổi tham chiếu.
- Nhu cầu phục hồi, thời gian giữ dữ liệu và bằng chứng cần lưu.

Không nên tạo khóa rồi cấp quyền toàn bộ cho một nhóm chung để “hoàn thiện policy sau”. Khoảng thời gian mở quyền ban đầu vẫn là một khoảng thời gian có rủi ro thực tế.

Nếu quy trình bootstrap bắt buộc có quyền rộng tạm thời, phải xác định principal chịu trách nhiệm, điều kiện kết thúc và bằng chứng xác minh quyền đã được thu hẹp trước khi nhận dữ liệu thật.

### 10.2. Rotation

Rotation thay đổi vật liệu khóa hoặc phiên bản được sử dụng cho các thao tác mới theo cơ chế của hệ thống. Nó không mặc nhiên:

- Viết lại mọi ciphertext cũ.
- Thu hồi quyền của principal đang được cho phép.
- Làm cho dữ liệu rõ đã bị lộ trở nên bí mật trở lại.
- Xóa các bản backup đang phụ thuộc khóa cũ.
- Cập nhật đúng mọi ứng dụng và mọi tham chiếu khóa.

Cần phân biệt ba công việc:

| Công việc | Câu hỏi cần trả lời |
|---|---|
| Rotation vật liệu hoặc phiên bản | Thao tác mới dùng vật liệu nào? |
| Chuyển dữ liệu hoặc bọc lại data key | Dữ liệu cũ còn phụ thuộc vật liệu nào? |
| Thu hồi thẩm quyền | Principal nào còn được gọi hành động nào? |

Trong envelope encryption, bọc lại data key và mã hóa lại toàn bộ dữ liệu là hai thao tác khác nhau. Việc nào phù hợp phụ thuộc mô hình khóa, nguyên nhân thay đổi và khả năng của hệ thống.

Một thay đổi định kỳ khác với xử lý nghi ngờ lộ vật liệu khóa. Không dùng cùng một checklist “đã rotate” để kết luận cả hai tình huống đã được xử lý.

### 10.3. Disable và thu hồi quyền

Thu hồi quyền của một principal nhằm ngăn chủ thể đó tiếp tục sử dụng khóa. Disable khóa có thể ảnh hưởng tất cả principal và mọi workload phụ thuộc. Hai thao tác không tương đương về phạm vi tác động.

Khi một workload bị chiếm quyền, cần cân nhắc theo bằng chứng:

1. Dừng hoặc cô lập nguồn thực thi bị xâm nhập.
2. Thu hồi credential, role, phiên truy cập và grant liên quan theo khả năng hệ thống.
3. Kiểm tra các đường tái cấp quyền mà principal hoặc bên điều khiển nó còn nắm giữ.
4. Đánh giá data key, dữ liệu rõ và kết quả ký đã có thể bị truy xuất.
5. Xác định có cần disable khóa, đổi khóa, chuyển dữ liệu hay thay cơ chế tin cậy hay không.
6. Xác minh từ các đường gọi thực tế rằng quyền đã bị chặn.

Không mặc định việc sửa một policy có hiệu lực đồng thời tại mọi cache, phiên và thành phần. Thời gian hội tụ, credential còn sống và vật liệu đã được lấy ra phải được đưa vào kế hoạch ứng phó.

### 10.4. Xóa khóa

Xóa khóa có thể làm mất khả năng khôi phục dữ liệu được bảo vệ nếu không còn vật liệu cần thiết ở bất kỳ nơi phục hồi hợp lệ nào. Đây là thao tác có thể gây hậu quả lâu dài và cần quyền riêng.

Trước khi xóa, cần đối soát:

- Dữ liệu trực tuyến còn phụ thuộc khóa.
- Backup, snapshot, bản lưu trữ và các bản sao được phép.
- Job chạy chậm hoặc thông điệp trong hàng đợi vẫn tham chiếu khóa cũ.
- Nhu cầu giải mã lịch sử hoặc xác minh chữ ký theo nghiệp vụ.
- Nghĩa vụ lưu giữ và quy trình phê duyệt của tổ chức.
- Khả năng hủy lịch xóa, phục hồi và giới hạn thời gian nếu sản phẩm hỗ trợ.

“Không có lưu lượng tuần qua” không đủ chứng minh khóa không còn phụ thuộc. Một bản sao lưu theo năm có thể chưa từng được truy cập trong khoảng đó.

Đối với chữ ký, khả năng xác minh lịch sử còn phụ thuộc việc lưu public key, định danh phiên bản và thông tin tin cậy cần thiết. Không đồng nhất việc ngừng ký mới với việc xóa mọi bằng chứng xác minh cũ.

### 10.5. Backup và restore

Nếu hệ thống hỗ trợ backup vật liệu khóa, cần kiểm soát quyền tạo, chuyển, lưu, phục hồi và phê duyệt bản backup. Vật liệu đã được bảo vệ trong backup vẫn phải chịu kiểm soát truy cập.

Diễn tập restore cần kiểm tra cả:

- Dữ liệu có thể được sử dụng lại đúng mục đích hay không.
- Policy và grant sau khôi phục có phù hợp trạng thái hiện tại hay không.
- Khóa có bị phục hồi vào môi trường hoặc miền quản trị sai hay không.
- Người thực hiện có thể tự tạo một bản sao ngoài kiểm soát hay không.

Khả năng khôi phục về mặt kỹ thuật không đồng nghĩa đã khôi phục đúng ranh giới quyền.

## 11. Bằng chứng kiểm toán cho hoạt động với khóa

Mục tiêu là trả lời được: ai hoặc workload nào đã làm gì, với khóa nào, theo thẩm quyền nào, vào lúc nào và kết quả ra sao.

| Dữ liệu bằng chứng | Ý nghĩa |
|---|---|
| Event ID và correlation ID | Liên kết quyết định ứng dụng, PAM, KMS và nơi nhận kết quả |
| Principal và workload identity | Xác định chủ thể yêu cầu và chủ thể thực thi |
| Hành động và key ID | Biết quyền cụ thể đã được sử dụng |
| Phiên bản khóa nếu có và được cung cấp | Truy ngược vật liệu liên quan đến thao tác |
| Tenant hoặc định danh phạm vi tối thiểu | Đối soát ranh giới nghiệp vụ mà không lộ nội dung |
| Operation ID, approval ID hoặc JIT session ID | Chứng minh căn cứ cấp quyền |
| Phiên bản policy hoặc định danh cấu hình | Điều tra quyền hiệu lực tại thời điểm xảy ra sự kiện |
| Thời điểm, kết quả và mã lỗi | Xác định được cho phép, bị từ chối hoặc thất bại kỹ thuật |
| Đích nhận kết quả đối với thao tác xuất | Kiểm tra dữ liệu có đi tới nơi đã được duyệt hay không |
| Chủ thể thay đổi policy và chi tiết thay đổi | Tìm đường mở rộng quyền trước sự kiện |

Không phải mọi hệ thống đều cung cấp toàn bộ trường. Thiết kế ứng dụng và nền tảng cần bổ sung metadata liên kết ở nơi thích hợp, đồng thời ghi rõ phần bằng chứng nào còn thiếu.

### Những nội dung không được ghi vào log

- Vật liệu khóa, data key bản rõ hoặc khóa riêng.
- Credential dùng để xác thực tới dịch vụ khóa.
- Dữ liệu rõ được giải mã.
- Toàn bộ payload nhạy cảm của yêu cầu ký hoặc xuất dữ liệu.
- Bản dump bộ nhớ hoặc exception có chứa dữ liệu nhạy cảm ngoài ý muốn.

Ngay cả ciphertext và định danh đối tượng cũng có thể là dữ liệu cần bảo vệ. Chỉ ghi những trường thực sự cần thiết, áp dụng quyền đọc và thời hạn lưu phù hợp.

### Cảnh báo nên gắn với hành vi có ý nghĩa

Một vài tín hiệu hữu ích:

- Principal quản trị policy tự xuất hiện trong tập được giải mã.
- Grant mới cấp cho một workload ngoài danh sách đã phê duyệt.
- Nhiều lần giải mã trên khóa production từ một danh tính vốn chỉ dùng ở thử nghiệm.
- Thay alias, sau đó lưu lượng ký hoặc mã hóa chuyển sang một khóa mới.
- Số lượng thao tác nhạy cảm tăng bất thường so với chức năng của workload.
- Yêu cầu xóa khóa khi vẫn còn phụ thuộc đã được đăng ký.
- Có thao tác khóa thành công nhưng không tìm thấy operation ID nghiệp vụ tương ứng.

Một cảnh báo cần kèm người chịu trách nhiệm và cách điều tra. Chỉ tạo log mà không liên kết với quy trình xử lý sẽ khó phát hiện việc lạm dụng quyền hợp lệ.

## 12. Tình huống thực tế: xuất dữ liệu hỗ trợ điều tra

### Bối cảnh

Hệ thống quản lý hóa đơn có ba thành phần:

- Invoice writer chỉ mã hóa dữ liệu mới bằng khóa được giao.
- Invoice reader giải mã trong luồng đọc hóa đơn sau kiểm tra quyền nghiệp vụ.
- Support export xử lý các yêu cầu xuất có phê duyệt phục vụ điều tra.

Một nhân viên hỗ trợ cần xuất ba hóa đơn thuộc một tenant để kiểm tra lỗi. Người này không được cấp credential KMS và không được chọn key ID tùy ý.

### Thiết kế quyền

Invoice writer không có quyền decrypt. Invoice reader không có quyền sửa policy, tạo grant hoặc xóa khóa. Support export có danh tính workload riêng, chỉ hoạt động với các khóa thuộc phạm vi đã thiết kế và phải kiểm tra yêu cầu được duyệt trước khi gọi phép giải mã.

Người hỗ trợ tạo yêu cầu ghi rõ ba định danh hóa đơn, mục đích và đích nhận kết quả. Người có thẩm quyền phê duyệt kế hoạch bất biến. Một lần thay đổi danh sách hóa đơn hoặc đích nhận phải tạo kế hoạch mới và xin lại phê duyệt.

Mã hóa luồng vận chuyển hoặc lưu file xuất không thay thế việc kiểm tra đích nhận. Nếu file mã hóa được gửi cho người không được phép có khóa giải mã file, ranh giới quyền vẫn bị phá vỡ.

### Cách đối soát

Sau khi job hoàn thành, bằng chứng phải chỉ ra:

1. Chính xác ba hóa đơn đã được cho phép.
2. Những hành động sử dụng khóa tương ứng với operation ID.
3. Đích nhận kết quả khớp với kế hoạch được phê duyệt.
4. Job không xử lý thêm đối tượng khi retry.
5. Quyền tạm thời đã kết thúc nếu có cấp JIT.

Không yêu cầu log chứa nội dung hóa đơn để chứng minh các điểm này.

### Khi workload bị chiếm quyền

Nếu support export bị chiếm quyền, các kiểm tra trong chính process có thể bị vô hiệu hóa. Đây là lý do không chỉ dựa vào kiểm tra ứng dụng: cần giới hạn quyền KMS của workload, cô lập môi trường thực thi và giảm quyền mạng, triển khai, đọc dữ liệu nguồn theo chức năng.

Nếu một workload vẫn có thể đọc mọi ciphertext và giải mã bằng mọi khóa, phạm vi ảnh hưởng còn rộng dù API của nó được thiết kế đẹp. Phải nhìn cả khả năng của danh tính nền tảng khi mã ứng dụng không còn đáng tin.

## 13. Bài thực hành thiết kế quyền trong môi trường thử nghiệm

Mục tiêu của bài thực hành là kiểm chứng ranh giới quyền, không phải thử xóa khóa thật hoặc sao chép vật liệu khóa production. Dùng dữ liệu giả và các danh tính thử nghiệm được cô lập.

### Bước 1: Lập danh mục

Tạo một bản thiết kế gồm các đối tượng giả:

```text
Khóa:
  key:invoice-test
  key:unrelated-test

Principal:
  workload:writer-test
  workload:reader-test
  workload:export-test
  human:operator-test
  human:approver-test

Đối tượng nghiệp vụ:
  invoice-A thuộc tenant-A
  invoice-B thuộc tenant-B

Quyền dự kiến:
  writer-test: encrypt với key:invoice-test
  reader-test: decrypt với key:invoice-test qua luồng đọc hợp lệ
  export-test: decrypt trong một operation đã được duyệt
  operator-test: thao tác vận hành cụ thể theo runbook
  approver-test: phê duyệt nhưng không tự thực thi giải mã
```

Chọn một cơ chế quản lý khóa phù hợp với môi trường sẵn có, rồi ánh xạ từng quyền khái niệm sang khả năng thực tế của cơ chế đó. Không sao chép cấu hình minh họa như một policy chạy được.

### Bước 2: Xác định kiểm soát ở từng lớp

Với mỗi quyền, ghi rõ ai kiểm tra:

- Nền tảng danh tính kiểm tra workload hoặc con người.
- Dịch vụ khóa kiểm tra hành động trên key ID.
- Ứng dụng kiểm tra tenant và đối tượng.
- Quy trình phê duyệt kiểm tra mục đích và phạm vi.
- Hệ thống job kiểm tra thời hạn, idempotency và trạng thái thực thi.
- Hệ thống bằng chứng liên kết các sự kiện.

Một thuộc tính không có thành phần nào kiểm tra là một lỗ hổng thiết kế, dù nó đã xuất hiện trong tài liệu.

### Bước 3: Kiểm chứng các tình huống

| Tình huống | Kết quả mong đợi |
|---|---|
| Writer mã hóa dữ liệu thử bằng khóa được giao | Cho phép |
| Writer gọi decrypt | Từ chối |
| Reader dùng khóa không liên quan | Từ chối |
| Người dùng tenant-A đọc invoice-B | Ứng dụng từ chối trước khi gọi giải mã |
| Client sửa header tenant để khớp invoice-B | Không thay đổi quyền hiệu lực |
| Export chạy đúng kế hoạch và còn hạn | Cho phép trong phạm vi kế hoạch |
| Export thêm một hóa đơn sau phê duyệt | Từ chối hoặc yêu cầu phê duyệt mới |
| Export thay đích nhận | Từ chối hoặc yêu cầu phê duyệt mới |
| Hai worker cùng bắt đầu một operation một lần | Không tạo hai lần thực thi ngoài thiết kế |
| Job retry sau khi đã giao một phần dữ liệu | Không giao trùng hoặc vượt phạm vi đã duyệt |
| Người vận hành tự cấp grant để giải mã | Bị chặn bởi phân tách quyền |
| Quyền JIT hết hạn trước thao tác nhạy cảm tiếp theo | Dừng thao tác đó và ghi bằng chứng |
| Thu hồi quyền workload rồi gọi lại qua đường thực tế | Bị chặn sau khi các cơ chế thu hồi liên quan có hiệu lực |
| Tìm kiếm log của các lần chạy | Có metadata đối soát, không có khóa hoặc dữ liệu rõ |

Đối với trường hợp thu hồi, cần ghi thời điểm thay đổi, các phiên hoặc cache còn hiệu lực và thời điểm thử lại. Nếu vẫn thành công, phân biệt một đường cấp quyền còn sót với độ trễ hoặc vật liệu đã cache; không kết luận ngay dựa vào một dòng policy.

### Bước 4: Hoàn thiện bằng chứng

Kết quả thực hành nên có:

- Ma trận principal, hành động, khóa và phạm vi.
- Danh sách các đường có thể cấp lại quyền.
- Một operation thành công và một số trường hợp bị từ chối có correlation ID.
- Cách thu hồi và xác minh quyền.
- Danh sách phụ thuộc trước rotation, disable hoặc xóa.
- Những giới hạn mà môi trường thử nghiệm chưa chứng minh được.

Không cần đưa secret, data key hay dữ liệu rõ vào báo cáo để làm bằng chứng.

## 14. Lỗi thường gặp và cách sửa thiết kế

### Cấp quyền toàn bộ vì ứng dụng dùng nhiều khóa

Một wildcard giải quyết nhanh vấn đề cấu hình nhưng mở rộng blast radius. Thay vào đó, xác định tập khóa mà từng chức năng cần dùng, cơ chế cập nhật tập đó và quyền của người được sửa cơ chế cập nhật.

Khi thật sự cần quyền theo thuộc tính, phải bảo vệ cả thuộc tính và chủ thể có thể thay đổi thuộc tính. Một policy dựa vào tag không an toàn hơn nếu workload tự gắn tag để mở quyền cho nó.

### Cho rằng quản trị khóa không thể đọc dữ liệu

Nếu người quản trị có thể sửa mọi policy, tự gán quyền hoặc phục hồi khóa vào nơi khác, họ có thể có khả năng tiếp cận dữ liệu gián tiếp. Cần hạn chế đường tự cấp quyền và đặt các thay đổi nhạy cảm dưới kiểm soát độc lập.

### Dùng chung danh tính giữa writer và reader

Danh tính chung làm mất khả năng cấp quyền mã hóa mà không cấp giải mã, đồng thời giảm khả năng quy trách nhiệm. Tách danh tính theo chức năng khi cần tách quyền và vận hành vòng đời riêng.

### Cho rằng HSM tự giải quyết phân quyền ứng dụng

Một cơ chế bảo vệ khóa có thể giúp giữ vật liệu khóa trong ranh giới được quản lý. Nó không tự biết người dùng cuối có được đọc hóa đơn hoặc ký giao dịch cụ thể hay không.

Nếu principal hợp lệ được quyền yêu cầu phép toán nhạy cảm quá rộng, việc khóa không bị export vẫn chưa ngăn được lạm dụng chức năng.

### Đồng nhất rotation với thu hồi và xử lý lộ dữ liệu

Rotation có thể là một bước, nhưng còn phải xem quyền principal, phiên truy cập, dữ liệu đã giải mã, vật liệu đã cache và phụ thuộc khóa cũ. Biên bản ứng phó phải ghi kết quả của từng việc, không chỉ một dấu “đã rotate”.

### Xóa khóa để ngăn một người truy cập

Nếu mục tiêu là chặn một principal, hãy đánh giá thu hồi quyền và dừng nguồn truy cập trước. Xóa khóa có thể làm tất cả workload mất khả năng xử lý dữ liệu và không lấy lại được bản rõ đã bị sao chép.

### Log toàn bộ request để dễ điều tra

Request có thể chứa dữ liệu nhạy cảm, token hoặc vật liệu khóa. Thiết kế log theo danh sách trường được phép ghi, có che giấu dữ liệu và kiểm soát quyền đọc. Kiểm tra cả lỗi và đường debug, không chỉ đường thành công.

## 15. Các câu hỏi cần trả lời trước khi cấp quyền

Trước một thay đổi quyền với khóa, người thiết kế nên trả lời được:

1. Principal cần đúng phép toán nào và vì chức năng gì?
2. Quyền áp dụng với key ID, môi trường và tập dữ liệu nào?
3. Dữ liệu rõ hoặc kết quả ký sẽ đi tới đâu?
4. Ai kiểm tra quyền nghiệp vụ mà dịch vụ khóa không thể biết?
5. Principal có đường tự sửa policy, tạo grant hoặc thay danh tính để mở rộng quyền không?
6. Quyền là quyền workload thường xuyên hay quyền thao tác của con người cần JIT?
7. Khi thu hồi, còn phiên, cache hoặc vật liệu nào có thể tiếp tục được sử dụng?
8. Ai phê duyệt thay đổi vòng đời và ai xác minh phụ thuộc?
9. Bằng chứng có đủ để đối soát nhưng không làm lộ secret không?
10. Khi một workload bị chiếm quyền, ranh giới bên ngoài process còn giới hạn được phạm vi ảnh hưởng thế nào?

Một thiết kế key management permission tốt làm rõ được cả quyền trực tiếp lẫn đường cấp lại quyền. Nó gắn thao tác mật mã với mục đích ứng dụng, giới hạn thẩm quyền theo phạm vi cần thiết và duy trì bằng chứng xuyên suốt vòng đời khóa.
