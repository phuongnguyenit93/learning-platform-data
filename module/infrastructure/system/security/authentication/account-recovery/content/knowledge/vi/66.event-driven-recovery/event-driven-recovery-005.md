# Factor replaced event — Sự kiện thay thế yếu tố xác thực trong khôi phục tài khoản

## 1. Sự kiện này xác nhận điều gì?

Trong luồng khôi phục tài khoản, **Factor replaced event** mô tả một sự thật đã được dịch vụ sở hữu thông tin xác thực ghi nhận: một authenticator cũ đã bị thay thế bằng một authenticator mới theo điều kiện của quy trình khôi phục.

Ví dụ, người dùng mất điện thoại chứa ứng dụng TOTP. Sau khi hoàn thành phương thức khôi phục được cho phép và xác nhận thiết lập TOTP mới, dịch vụ credential vô hiệu hóa liên kết với authenticator cũ, kích hoạt liên kết mới và ghi nhận sự kiện thay thế. Các thành phần quản lý phiên, thông báo, audit và tiến độ có thể phản ứng với sự kiện đó.

Trong tên sự kiện, từ “factor” thường được dùng để chỉ một authenticator đã đăng ký. Cần phân biệt nó với **nhóm yếu tố xác thực** như điều người dùng biết hoặc thứ người dùng sở hữu. Thay TOTP cũ bằng TOTP mới không có nghĩa tài khoản vừa có thêm một nhóm yếu tố độc lập. Hợp đồng nghiệp vụ cần nói rõ nó thay thế credential nào, thay vì chỉ ghi “MFA đã đổi”.

Một hợp đồng minh họa có thể định nghĩa `FactorReplaced` như sau:

> Tại phiên bản tập credential được ghi trong event, dịch vụ có thẩm quyền đã commit việc chấm dứt khả năng dùng authenticator cũ theo mô hình của dịch vụ và kích hoạt authenticator mới đã được xác minh cho đúng tài khoản, đúng mục đích.

Phạm vi này không tự khẳng định mọi session đã bị thu hồi, mọi cache đã cập nhật, thông báo đã đến người dùng hay toàn bộ recovery case đã hoàn tất. Những kết quả đó cần trạng thái và bằng chứng thực thi riêng.

Nếu hệ thống cho phép giữ đồng thời cả hai authenticator trong một thời gian chuyển tiếp, cần đặt tên hoặc mô tả sự kiện phù hợp với trạng thái đó. Không dùng cùng một tên với nghĩa “yếu tố cũ đã hết quyền sử dụng” rồi lại cho phép yếu tố cũ tiếp tục xác thực mà không thể hiện ngoại lệ.

## 2. Phân biệt yêu cầu thay thế với sự kiện đã thay thế

| Thông điệp | Ý nghĩa | Điều chưa thể kết luận |
|---|---|---|
| `ReplaceFactor` | Lệnh đề nghị thực hiện thay thế | Lệnh có được chấp nhận và thực thi hay không |
| `FactorReplacementRequested` | Đã tiếp nhận một yêu cầu trong workflow | Bằng chứng khôi phục đã đủ hoặc yếu tố mới đã hoạt động |
| `FactorEnrollmentStarted` | Đã bắt đầu thiết lập authenticator mới | Người dùng đã chứng minh kiểm soát authenticator mới |
| `FactorReplaced` | Thay thế theo hợp đồng đã được commit tại dịch vụ sở hữu | Các hiệu ứng ở dịch vụ khác đã hoàn tất |
| `RecoveryCompleted` | Các điều kiện hoàn tất của recovery workflow đã được đáp ứng | Mọi loại phiên hoặc hệ thống bên ngoài đều nằm trong phạm vi bảo đảm nếu hợp đồng không nói rõ |

Một event `FactorReplaced` không phải lệnh để consumer tự tạo authenticator mới từ dữ liệu trong message. Nó cũng không phải bằng chứng độc lập để đăng nhập, tăng quyền hoặc bỏ qua MFA. Quyền thay thế phải được kiểm tra **trước** khi thực hiện thay đổi ở dịch vụ sở hữu credential.

OWASP coi thay đổi yếu tố MFA là thao tác có rủi ro cao, khuyến nghị xác thực lại phù hợp, kiểm tra rủi ro và thông báo qua kênh ngoài luồng. Khi người dùng đã mất yếu tố hiện có, cần áp dụng phương thức khôi phục tương ứng thay vì coi một session đang mở là bằng chứng đủ. [OWASP: Changing MFA Factors](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#changing-mfa-factors)

NIST mô tả việc vô hiệu hóa authenticator là loại bỏ liên kết của nó với tài khoản, đồng thời phân biệt các sự kiện vòng đời như đăng ký, khôi phục và thông báo. Cách đặt event của ứng dụng cần phản ánh đúng thay đổi thật của liên kết đó. [NIST: Invalidation và Account Notifications](https://pages.nist.gov/800-63-4/sp800-63b.html#invalidation)

## 3. Điều kiện để phát `FactorReplaced`

### 3.1. Dịch vụ sở hữu credential xác nhận thay đổi

Producer có thẩm quyền thường là credential service hoặc identity service thực sự ghi trạng thái authenticator. Recovery service có thể điều phối và yêu cầu thay thế; support service có thể hỗ trợ rà soát. Hai thành phần đó không nên tự phát sự kiện thành công chỉ vì đã gửi một lệnh hoặc nhận được phản hồi “đã tiếp nhận”.

Trước khi commit, dịch vụ sở hữu cần kiểm tra những điều kiện phù hợp với thiết kế, chẳng hạn:

- Đúng tài khoản và tenant; authenticator cũ thuộc tài khoản đó.
- Quyền thực hiện thay thế đến từ ngữ cảnh được xác thực và có phạm vi đúng.
- Bằng chứng hoặc quyết định khôi phục còn hiệu lực, chưa bị thu hồi và phù hợp với hành động này.
- Authenticator mới đã hoàn thành bước xác minh cần thiết và chưa bị gắn sai tài khoản.
- Chính sách cho phép loại authenticator mới, kể cả yêu cầu tránh hạ mức bảo vệ.
- Phiên bản credential hiện tại khớp điều kiện cạnh tranh của thao tác.
- Một quyền dùng một lần không thể được sử dụng để thực hiện hai thay đổi ngoài ý định.

Đây là các điều kiện của lệnh thay thế, không phải các cờ mà producer chỉ sao chép từ request. Trường `verified: true` do client hoặc một hệ thống ticket gửi lên không tự chứng minh các điều kiện đã đạt.

### 3.2. Đúng ý nghĩa cho TOTP, passkey và thiết bị

Với TOTP, việc tạo seed mới hoặc hiển thị mã QR mới chỉ là bắt đầu thiết lập. Sự kiện thay thế cần dựa trên trạng thái đăng ký đã được xác nhận theo quy trình, không phát ngay khi người dùng nhìn thấy QR. Seed cũ và seed mới không xuất hiện trong event.

Với passkey, cần hoàn thành bước đăng ký và kiểm tra kết quả theo cơ chế xác thực sử dụng. Khôi phục quyền truy cập rồi đăng ký passkey mới khác với “khôi phục private key cũ”. Sự kiện chỉ tham chiếu credential mà máy chủ quản lý và thay đổi liên kết tương ứng.

Một passkey đồng bộ có thể hiện diện trên nhiều thiết bị. Vì vậy, `factorId` không mặc nhiên là ID của một điện thoại vật lý. Nếu thu hồi credential đó, phạm vi ảnh hưởng cần được hiểu theo credential, không suy diễn rằng chỉ một bản sao trên thiết bị bị mất đã bị xóa.

Nếu người dùng chỉ thêm một phương thức dự phòng mà vẫn giữ yếu tố cũ hoạt động, đó thường là sự kiện đăng ký thêm. Nếu chỉ vô hiệu hóa yếu tố bị lộ mà chưa có yếu tố mới, đó là sự kiện thu hồi. Không dùng `FactorReplaced` để che đi các khác biệt ảnh hưởng đến consumer.

## 4. Gắn thay đổi credential và event bằng một ranh giới giao dịch

Hai lỗi nguy hiểm của cách ghi kép trực tiếp là:

1. Phát event trước rồi giao dịch credential rollback: các consumer tin rằng việc thay thế đã xảy ra dù dữ liệu chuẩn chưa đổi.
2. Commit credential rồi tiến trình chết trước khi phát event: thông báo, kiểm soát phiên hoặc tiến độ không nhận được thay đổi cần xử lý.

**Transactional outbox** giải quyết khoảng trống này bằng cách lưu bản ghi event cùng giao dịch cục bộ với thay đổi nghiệp vụ. Relay chỉ phát các bản ghi đã commit. Relay vẫn có thể phát trùng, nên cần consumer xử lý idempotent. [AWS: Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

```mermaid
sequenceDiagram
    participant R as Recovery service
    participant C as Credential service
    participant D as Credential DB và outbox
    participant P as Outbox relay
    participant B as Event broker
    participant K as Consumer
    R->>C: ReplaceFactor với quyền và operation ID
    C->>C: Kiểm tra bằng chứng, phạm vi và phiên bản
    C->>D: BEGIN; thay credential; lưu event
    D-->>C: COMMIT
    C-->>R: Thay thế đã được ghi nhận
    P->>D: Đọc event đã commit
    P->>B: Phát FactorReplaced
    B->>K: Giao event, có thể giao lại
    K->>K: Kiểm tra nguồn và lưu xử lý bền vững
    K-->>B: Xác nhận theo cơ chế broker
```

Mã giả tại dịch vụ sở hữu credential:

```text
replaceFactor(authenticatedContext, command):
    authenticate caller and require access to the target operation

    begin local transaction
    lock credential aggregate for tenant and account

    if a completed operation exists for the scoped operation ID:
        require the command matches the original operation
        return the recorded result without performing a new replacement

    validate current authorization and recovery conditions
    require expected credential-set version matches
    require the replacement authenticator is verified and eligible
    require the old authenticator belongs to this account

    consume the locally managed one-use replacement permission
    revoke the old authenticator binding
    activate the new authenticator binding
    increment credential-set version

    store operation result
    insert FactorReplaced into the outbox
    commit local transaction
    return recorded result
```

Mã giả giả định quyền dùng một lần được quản lý trong cùng ranh giới giao dịch hoặc đã được chuyển thành quyền cục bộ bằng một giao thức có bảo đảm rõ ràng. Nếu quyền nằm ở recovery DB khác, không thể gọi một API kiểm tra rồi tuyên bố toàn bộ thao tác đã nguyên tử. Cần thiết kế phối hợp việc giữ chỗ, tiêu thụ quyền và kết quả thay thế để retry không tái sử dụng quyền.

Operation ID cũng cần ràng buộc với tenant, tài khoản, loại thao tác và nội dung tương ứng. Việc trả kết quả cũ là tra cứu một thay đổi đã xảy ra; nó không cho phép chạy lại thay đổi chỉ vì quyết định khôi phục trước đây từng hợp lệ.

## 5. Thiết kế hợp đồng event rõ ràng và tối thiểu dữ liệu

### 5.1. Một envelope minh họa

Có thể dùng CloudEvents làm envelope chung và định nghĩa payload nghiệp vụ của ứng dụng:

```json
{
  "specversion": "1.0",
  "id": "evt-factor-replaced-941",
  "source": "urn:learning:credential-service",
  "type": "com.learning.security.factor.replaced.v1",
  "subject": "tenants/tenant-08/accounts/account-482",
  "time": "2026-11-24T07:15:00Z",
  "datacontenttype": "application/json",
  "data": {
    "tenantId": "tenant-08",
    "accountId": "account-482",
    "recoveryCaseId": "recovery-731",
    "replacementOperationId": "replace-219",
    "credentialSetVersion": 18,
    "previousFactor": {
      "factorId": "factor-old-17",
      "type": "TOTP",
      "bindingState": "REVOKED"
    },
    "replacementFactor": {
      "factorId": "factor-new-39",
      "type": "TOTP",
      "bindingState": "ACTIVE"
    },
    "reasonCode": "LOST_AUTHENTICATOR",
    "authorizationDecisionRef": "decision-314",
    "securityActionPlanRef": "plan-512"
  }
}
```

Tên, ID và phiên bản là ví dụ thiết kế. CloudEvents chuẩn hóa envelope; các trường trong `data` vẫn cần hợp đồng riêng của hệ thống. Theo đặc tả, cặp `source` và `id` xác định một event duy nhất; khi giao lại cùng event, consumer có thể dùng cặp này để nhận diện bản trùng. `specversion: "1.0"` là phiên bản envelope, không phải phiên bản payload `v1`. [CloudEvents 1.0.2: Context Attributes](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md#context-attributes)

### 5.2. Ý nghĩa của các định danh

| Trường | Dùng để làm gì | Không được dùng thay cho |
|---|---|---|
| `source` + `id` | Nhận diện cùng event khi được giao lại | Kết quả xác thực danh tính producer chỉ dựa trên chuỗi tự khai |
| `replacementOperationId` | Liên kết sự kiện với một thao tác thay thế nghiệp vụ | Bearer token hoặc quyền chạy lại thao tác |
| `recoveryCaseId` | Truy nguyên workflow khôi phục liên quan | Bằng chứng rằng mọi bước của case đã hoàn tất |
| `credentialSetVersion` | Phiên bản tăng dần của tập credential tại dịch vụ sở hữu | Phiên bản toàn cục của mọi session và mọi microservice |
| `previousFactor.factorId` | Xác định binding cũ trong phạm vi tài khoản | Seed, private key hay định danh duy nhất của thiết bị vật lý |
| `replacementFactor.factorId` | Xác định binding mới đã được commit | Dữ liệu để consumer tự tái tạo authenticator |
| `authorizationDecisionRef` | Truy nguyên quyết định cho phép thay thế | Quyền truy cập không cần kiểm tra thêm |
| `securityActionPlanRef` | Tham chiếu kế hoạch xử lý hậu quả bảo mật | Xác nhận các hành động trong kế hoạch đã thực thi |

Trong hợp đồng một-cũ-một-mới này, hai factor ID phải khác nhau và thuộc đúng tài khoản. Nếu nghiệp vụ thay nhiều credential cùng lúc, cần hợp đồng biểu diễn rõ tập thay đổi và tính nguyên tử; không tự nhét danh sách vào một field vốn mang nghĩa một đối tượng.

`time` biểu thị thời điểm xảy ra theo hợp đồng producer, không phải thời điểm broker giao hoặc consumer xử lý. Timestamp không tạo ra thứ tự toàn cục đáng tin giữa các dịch vụ. Có thể cần lưu thêm thời điểm nhận và xử lý để đo độ trễ, nhưng không đổi nghĩa của thời điểm sự kiện gốc.

### 5.3. Dữ liệu không cần đi qua event bus

Không đưa vào payload các dữ liệu như seed TOTP, QR provisioning, OTP, mã khôi phục, token đặt lại mật khẩu, cookie, refresh token hoặc private key. Consumer cần biết trạng thái thay đổi và tham chiếu nghiệp vụ, không cần cầm bí mật xác thực.

Email, số điện thoại và tài liệu định danh cũng không nên xuất hiện đầy đủ nếu consumer không cần. Có thể dùng reference đến dữ liệu được quản lý với quyền truy cập riêng. Reference, account ID và thông tin thời điểm vẫn có thể là dữ liệu nhạy cảm; không xem chúng là dữ liệu công khai chỉ vì không chứa mật khẩu.

Không dùng ghi chú tự do của nhân viên làm trường bắt buộc trong event tích hợp. `reasonCode` có tập giá trị được kiểm soát thường dễ bảo vệ và diễn giải hơn một đoạn hội thoại chứa thông tin cá nhân.

## 6. Mỗi consumer thực hiện một trách nhiệm cụ thể

| Consumer | Phản ứng phù hợp | Giới hạn cần giữ |
|---|---|---|
| Recovery workflow | Ghi nhận bước thay credential đã thành công cho đúng operation | Không đóng case khi các điều kiện hoàn tất khác còn thiếu |
| Session hoặc security coordinator | Thực hiện hoặc điều phối kế hoạch kiểm soát phiên | Không coi việc nhận event là bằng chứng mọi phiên đã bị thu hồi |
| Notification service | Tạo thông báo thay đổi yếu tố qua kênh được phép | Không lấy địa chỉ tùy ý từ client làm đích nhận quyền khôi phục |
| Audit và phát hiện rủi ro | Ghi nhận thay đổi, tương quan với dấu hiệu tấn công | Không phát hành quyền đăng nhập từ một bản ghi audit |
| Bản chiếu cho support hoặc giao diện | Hiển thị tiến độ và lịch sử được phép xem | Không dùng bản chiếu làm nguồn chuẩn để xác thực authenticator |

Một event có thể kích hoạt nhiều hiệu ứng độc lập. Cần xác định hiệu ứng nào bắt buộc để recovery được coi là hoàn tất, hiệu ứng nào có thể tiếp tục xử lý sau và hành vi khi một hiệu ứng bị chậm.

Các consumer không nên tự suy đoán một kế hoạch bảo mật khác nhau từ cùng một mã lý do. Nếu hệ thống cần một kế hoạch thống nhất, thành phần có thẩm quyền tạo kế hoạch có phạm vi và phiên bản rõ ràng; event tham chiếu kế hoạch đó. Consumer thực thi phần được giao và báo kết quả theo cùng operation.

## 7. Xử lý trùng lặp ở cả event và hiệu ứng nghiệp vụ

### 7.1. Relay có thể phát cùng event nhiều lần

Relay có thể đã phát thành công nhưng chết trước khi lưu checkpoint. Khi chạy lại, nó phát lại bản ghi outbox. Cần giữ nguyên event ID cho cùng bản ghi, thay vì sinh ID mới ở mỗi lần publish.

Consumer có thể quản lý inbox với ràng buộc duy nhất theo:

```text
(logicalConsumer, eventSource, eventId)
```

`logicalConsumer` là danh tính ổn định của chức năng xử lý, không phải ID của một pod tạm thời. Nếu mỗi lần triển khai đổi khóa deduplication, các bản giao lại có thể bị xử lý như hoàn toàn mới.

Trong cùng giao dịch cục bộ, consumer ghi nhận đã tiếp nhận event và lưu công việc cần thực hiện. Chỉ xác nhận message theo cơ chế broker sau khi dữ liệu cần thiết đã được lưu bền vững.

### 7.2. Inbox không tự làm API bên ngoài trở nên nguyên tử

Một cách xử lý thông thường có thể là:

```text
handleFactorReplaced(event):
    validate envelope, supported schema, producer provenance and tenant

    begin local transaction
    if this logical consumer has already accepted source + event ID:
        commit and acknowledge delivery
        return

    derive the permitted effect from the bound security action plan
    persist a work item with a unique business-effect key
    persist any required outgoing command in a local outbox
    record inbox status as ACCEPTED
    commit local transaction

    acknowledge delivery
```

`ACCEPTED` nghĩa là công việc đã được nhận bền vững. Một worker riêng vẫn phải thực hiện công việc, lưu kết quả và retry theo trạng thái. Không được hiểu dòng inbox đó là thông báo đã gửi hoặc session đã bị thu hồi.

Nếu gọi API ngoài trong giao dịch rồi ghi inbox, vẫn có khoảng trống: API có thể đã thành công nhưng giao dịch cục bộ rollback. Khi retry, API bị gọi lại. Cần idempotency ở API nhận hoặc một giao thức thực thi hiệu ứng có cùng khóa nghiệp vụ và khả năng đối soát kết quả.

Ví dụ, khóa hiệu ứng có thể gắn với:

```text
(tenantId, replacementOperationId, effectType, effectScope)
```

Khóa này bổ sung cho event ID. Nó giúp phát hiện cùng một hiệu ứng bị yêu cầu lại qua cơ chế sửa lỗi, hai phiên bản event hoặc nhiều đường tích hợp. Phạm vi khóa phải được định nghĩa đủ để không gộp nhầm hai hành động hợp lệ.

Với gửi thông báo, việc nhà cung cấp nhận request rồi mất phản hồi có thể khiến hệ thống không biết đã gửi hay chưa. Không hứa “gửi đúng một lần” nếu nhà cung cấp và giao thức không bảo đảm điều đó. Thiết kế cần hạn chế trùng, có đối soát khi khả thi và nội dung thông báo chịu được trường hợp gửi lại.

### 7.3. Thời gian giữ deduplication phải khớp khả năng replay

Nếu broker giữ event lâu hơn inbox giữ khóa đã xử lý, một bản replay cũ có thể tạo lại hiệu ứng. Vì vậy, chính sách retention, khôi phục từ backup và replay cần được thiết kế cùng nhau.

Một số hiệu ứng có thể cần hồ sơ operation hoặc khóa nghiệp vụ bền vững hơn vòng đời inbox. Không xóa mọi dấu vết xử lý chỉ vì message đã được xác nhận ở broker.

## 8. Thứ tự, phiên bản và replay không có cùng ý nghĩa

### 8.1. Giữ thứ tự theo tài khoản khi hạ tầng hỗ trợ

Một routing key minh họa là cặp tenant và account. Với broker hỗ trợ thứ tự trong từng partition hoặc queue tương ứng, việc giữ các thay đổi cùng tài khoản trên một luồng giúp consumer xử lý dễ hơn. Relay và cơ chế retry cũng phải giữ được giả định đó; chọn key giống nhau riêng lẻ chưa đủ bảo đảm toàn bộ pipeline.

Routing key chỉ là quyết định vận chuyển, không phải cơ chế phân quyền tenant. Consumer vẫn cần kiểm tra message thuộc phạm vi mà nó được phép xử lý.

### 8.2. Không bỏ mọi event có phiên bản thấp hơn một mốc chung

Giả sử có hai thay đổi độc lập của cùng tài khoản:

```text
credentialSetVersion 18: thay factor A thành factor B
credentialSetVersion 19: thay factor C thành factor D
```

Nếu event 19 đến trước, một consumer cập nhật `lastVersion = 19` rồi bỏ event 18 có thể quên xử lý hậu quả của việc thay A. Đó là lỗi khi payload là **delta**, tức chỉ mô tả phần thay đổi, thay vì ảnh chụp đầy đủ của toàn bộ trạng thái.

Cần phân biệt:

- Bản chiếu toàn bộ trạng thái có thể áp dụng quy tắc phiên bản nếu hợp đồng thực sự cung cấp đủ thông tin để thay thế bản cũ.
- Các hiệu ứng bắt buộc cho từng operation cần được theo dõi theo operation, không bị xóa chỉ vì đã thấy một phiên bản lớn hơn.
- Nếu thiếu ngữ cảnh, consumer đối chiếu dữ liệu chuẩn hoặc chờ xử lý theo chiến lược đã định nghĩa; không tự đoán authenticator nào còn hoạt động.

Khoảng nhảy của `credentialSetVersion` cũng chưa chắc chứng minh mất event. Phiên bản có thể tăng vì loại thay đổi khác mà consumer không đăng ký nhận. Hợp đồng luồng phải nói rõ phiên bản nào có tính liên tục cho subscriber cụ thể.

### 8.3. Replay không được kích hoạt lại credential hoặc gây thu hồi sai phạm vi

Một bản `FactorReplaced` từ tháng trước là sự thật lịch sử, không phải chỉ thị kích hoạt lại factor mới của tháng trước. Factor đó có thể đã bị thay tiếp hoặc thu hồi. Consumer dựng bản chiếu cần có chiến lược tái tạo trạng thái đúng và không ghi đè dữ liệu hiện tại bằng giả định cũ.

Replay cũng không nên biến thành “thu hồi mọi session đang tồn tại lúc nhận message”. Nếu người dùng đã có phiên hợp lệ mới sau khôi phục, một event cũ đến muộn có thể vô tình thu hồi phiên đó.

Kế hoạch kiểm soát phiên cần gắn với phạm vi gốc, chẳng hạn một thế hệ phiên hoặc tập phiên do dịch vụ có thẩm quyền xác định. Consumer tra cứu và thực hiện đúng kế hoạch. Nếu rủi ro mới đòi hỏi thu hồi rộng hơn, đó là quyết định bảo mật mới có truy nguyên riêng, không phải âm thầm đổi nghĩa của event cũ.

Thông báo gửi lại một sự kiện cũ cũng phải tránh tạo cảm giác thay đổi vừa xảy ra. Nội dung và quy tắc replay cần phân biệt thông báo lần đầu, gửi lại do lỗi và dựng lại bản chiếu mà không gửi thông báo.

## 9. Khoảng trễ sự kiện và kiểm soát session

Thay authenticator không tự làm mất hiệu lực các session đã được cấp trước đó. Kẻ có cookie hoặc refresh token còn hợp lệ có thể tiếp tục truy cập nếu hệ thống chưa áp dụng chính sách thu hồi tương ứng.

Một chuỗi thời gian cần được phân tích rõ:

```text
t0: credential service commit thay thế
t1: relay phát FactorReplaced
t2: consumer nhận được event
t3: session service thực hiện hành động được yêu cầu
t4: các điểm kiểm tra truy cập quan sát được hiệu lực thu hồi
```

Khoảng từ `t0` đến `t4` không biến mất chỉ vì message được giao nhanh trong thử nghiệm. Nếu yêu cầu an toàn là chặn một nhóm phiên ngay trong quá trình thay thế, cần một cơ chế thực thi đáp ứng yêu cầu đó: ví dụ trạng thái hạn chế được kiểm tra tại điểm truy cập, kiểm tra thế hệ phiên từ nguồn đủ mới hoặc một bước đồng bộ bắt buộc trong quy trình.

Mỗi lựa chọn cần nêu rõ phạm vi, độ mới của cache và hành vi khi nguồn kiểm tra không truy cập được. Tăng một số phiên bản trong credential DB nhưng các resource service không kiểm tra số đó sẽ không tạo ra hiệu lực thu hồi.

Tương tự, xóa refresh token có thể chặn việc cấp access token mới nhưng chưa làm access token tự chứa đang còn hạn mất hiệu lực ngay. Workflow phải hiểu cơ chế token và session thực tế trước khi ghi nhận hoàn tất.

Có thể hiển thị tiến độ theo các kết quả riêng:

- Authenticator đã được thay thế.
- Kế hoạch kiểm soát phiên đang xử lý hoặc đã đạt điều kiện cần thiết.
- Thông báo đã được tiếp nhận để gửi hoặc đã có kết quả chuyển phát phù hợp.
- Các điều kiện hoàn tất của recovery case đã được đáp ứng.

Các trạng thái này giúp người dùng và nhân viên hỗ trợ hiểu đúng kết quả. Không tự cấp một phiên đăng nhập toàn quyền chỉ vì consumer nhìn thấy `FactorReplaced`; việc phát hành phiên phải theo luồng xác thực hoặc khôi phục được cho phép.

## 10. Tin cậy producer và bảo vệ luồng sự kiện

### 10.1. Tên sự kiện không xác thực nguồn

Một message mang `source: "urn:learning:credential-service"` vẫn có thể là dữ liệu giả nếu bất kỳ ứng dụng nào cũng có quyền ghi vào topic. Producer cần danh tính workload, quyền publish giới hạn và kênh truyền được bảo vệ; consumer cần xác định nguồn được phép tạo loại event này.

Khi sự kiện đi qua trung gian hoặc ranh giới tổ chức, có thể cần cơ chế kiểm chứng nguồn và toàn vẹn phù hợp với mô hình tin cậy. Chữ ký, nếu sử dụng, vẫn cần quy tắc về khóa, bên phát, nơi nhận và thời gian áp dụng; xác minh chữ ký riêng lẻ không biến một event thành quyền thay credential.

Không cấp cho support service hoặc frontend quyền publish sự kiện thành công vào cùng luồng của credential owner. Tách quyền gửi command, phát sự kiện kết quả và đọc dữ liệu theo đúng trách nhiệm.

### 10.2. Kiểm tra trước khi tạo hiệu ứng

Consumer nên kiểm tra envelope, loại event, phiên bản hỗ trợ, kích thước, cấu trúc payload, tenant, tính nhất quán của các reference và nguồn được tin cậy. Nếu `subject` và `data.accountId` mô tả hai tài khoản khác nhau, cần từ chối hoặc cách ly theo quy trình, không tùy ý chọn một trường rồi tiếp tục.

Reference đến action plan nên được giải quyết qua giao diện và định dạng được cho phép. Không nhận một URL tùy ý trong message rồi gọi theo, vì điều đó có thể tạo đường truy cập tới đích ngoài dự kiến.

Schema hợp lệ mới chứng minh dữ liệu có cấu trúc đúng. Nó chưa chứng minh operation thực sự tồn tại, người dùng đã được xác minh hay message đến từ producer được cho phép.

### 10.3. Hạn chế bản sao trong log, DLQ và hệ thống phân tích

Event có thể xuất hiện ở nhiều nơi: broker, kho lưu lịch sử, dead-letter queue, trace, dashboard và môi trường dựng bản chiếu. Chính sách truy cập và retention cần bao phủ các bản sao đó.

Không log toàn bộ payload mặc định nếu chỉ cần event ID, operation ID, loại event và kết quả xử lý. Khi chuyển sang DLQ, giữ đủ dữ liệu để điều tra và phát lại có kiểm soát, đồng thời bảo vệ DLQ như một phần của hệ thống dữ liệu bảo mật.

## 11. Retry, cách ly lỗi và đối soát

| Tình huống | Hành vi cần thiết |
|---|---|
| Giao dịch credential rollback | Không tồn tại event thành công có thể được relay phát từ giao dịch đó |
| Commit thành công rồi producer chết | Outbox còn đủ thông tin để phát event sau khi phục hồi |
| Broker nhận event nhưng relay chưa lưu checkpoint | Cho phép phát lại cùng event; consumer chống xử lý trùng |
| Consumer chết sau khi commit local nhưng trước khi ACK | Giao lại không tạo thêm hiệu ứng nghiệp vụ ngoài ý định |
| API session timeout sau khi nhận lệnh | Tra cứu bằng operation hoặc khóa idempotency; không mặc định thất bại rồi tạo lệnh rộng hơn |
| Schema chưa được hỗ trợ | Cách ly hoặc dừng nhánh xử lý theo chính sách; không bỏ qua một hiệu ứng bảo mật bắt buộc mà không báo lỗi |
| Một consumer chậm trong thời gian dài | Theo dõi độ trễ và tiến độ operation; recovery không được đóng sai điều kiện |
| Event cũ được replay | Không tái kích hoạt factor cũ, không tạo lại quyền khôi phục và không thu hồi sai phạm vi phiên mới |
| Thông báo gửi thất bại | Retry có giới hạn và giám sát; không tự phục hồi authenticator cũ để bù lỗi gửi |

Retry nên phân biệt lỗi tạm thời với lỗi dữ liệu hoặc phân quyền. Retry vô hạn một message sai cấu trúc không giúp hoàn tất quy trình và có thể chặn các message khác.

Khi một hiệu ứng bắt buộc nằm trong DLQ, việc chuyển message sang DLQ không đồng nghĩa công việc bảo mật đã được giải quyết. Cần owner xử lý, trạng thái còn thiếu và đường đối soát rõ ràng.

Đối soát có thể kiểm tra các operation đã commit nhưng chưa có kết quả xử lý cần thiết, outbox chưa được chuyển đi hoặc action plan còn dở. Việc sửa lỗi không nên sinh một event “thành công” giả để ép dashboard xanh. Nếu phát lại cùng sự kiện thì giữ nhận diện của sự kiện; nếu tạo hành động khắc phục mới thì cần định danh, quyền và quan hệ truy nguyên riêng.

Một lỗi ở notification hay bản chiếu không phải lý do tự bật lại authenticator đã bị thu hồi. Bù trừ trong nghiệp vụ bảo mật phải xét rủi ro; không áp dụng máy móc quy tắc đảo ngược mọi bước trước đó.

## 12. Thay đổi schema và kiểm chứng triển khai

Khi mở rộng event, có thể thêm trường tùy chọn với ý nghĩa rõ ràng và quy tắc mặc định an toàn. Không đổi nghĩa `ACTIVE` từ “đã có thể sử dụng” sang “đang chờ xác minh” mà giữ nguyên phiên bản hợp đồng.

Nếu triển khai song song hai phiên bản event cho cùng một operation, cần ngăn hai consumer hoặc hai nhánh xử lý tạo trùng hiệu ứng. Quan hệ theo operation và khóa hiệu ứng nghiệp vụ giúp bảo vệ ngoài cơ chế deduplication theo event ID. Không dựa vào việc hai message có tên gần giống nhau để tự nhận ra chúng mô tả cùng thay đổi.

Các tình huống kiểm thử quan trọng cho một sản phẩm triển khai bài học:

| Kiểm thử | Điều cần chứng minh |
|---|---|
| TOTP mới chưa được xác nhận | Không phát `FactorReplaced` với nghĩa đã kích hoạt |
| Lệnh dùng sai tenant hoặc sai account | Không thay credential và không ghi event thành công |
| Hai request cùng dùng một quyền thay thế | Chỉ có kết quả được phép; không dùng quyền một lần để tạo hai thay đổi |
| Hai request cạnh tranh trên cùng phiên bản credential | Có xử lý xung đột hoặc tuần tự hóa phù hợp với hợp đồng |
| Rollback sau khi đã ghi outbox trong transaction | Không có event từ giao dịch rollback được phát như sự thật đã commit |
| Giao cùng event nhiều lần | Inbox và hiệu ứng nghiệp vụ không bị nhân đôi ngoài ý định |
| Event 19 đến trước event 18 của hai delta khác nhau | Không bỏ mất hiệu ứng bắt buộc của operation trước |
| Replay sau khi factor mới lại bị thay tiếp | Không khôi phục trạng thái authenticator đã lỗi thời |
| Replay sau khi người dùng có session mới hợp lệ | Hành động session vẫn đúng phạm vi của kế hoạch gốc |
| Consumer nhận event giả từ producer không được phép | Không tạo thông báo hoặc hành động bảo mật từ nguồn đó |
| Event có reference và tenant mâu thuẫn | Bị từ chối hoặc cách ly, có dấu vết điều tra phù hợp |
| Một hiệu ứng bắt buộc chưa hoàn tất | Recovery workflow phản ánh đúng trạng thái còn chờ |
| Event được lưu ở log và DLQ | Không xuất hiện seed, OTP, token khôi phục hoặc bí mật phiên |

Về vận hành, có thể đo độ tuổi bản ghi outbox chưa phát, thời gian từ commit đến consumer, số bản giao trùng, số hiệu ứng đang retry, số operation chưa hoàn tất và số message bị cách ly. Các phép đo nên liên kết được bằng event ID và operation ID mà không cần ghi bí mật.

Một `FactorReplaced` có ích khi nó mô tả chính xác một thay đổi đã commit và cho phép các dịch vụ thực hiện trách nhiệm tiếp theo có kiểm soát. Sự an toàn của luồng khôi phục còn phụ thuộc việc thay thế được cho phép đúng cách, hiệu ứng được thực thi đúng phạm vi và kết quả hoàn tất phản ánh những bảo đảm thật của hệ thống.
