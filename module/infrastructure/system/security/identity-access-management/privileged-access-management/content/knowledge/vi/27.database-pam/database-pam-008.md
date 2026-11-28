# Database credential rotation

## Mục tiêu bài học

Trong chương Database PAM của module Privileged Access Management (PAM), **database credential rotation** là quá trình thay thế bằng chứng xác thực để truy cập cơ sở dữ liệu, chuyển các bên sử dụng sang giá trị mới và xử lý giá trị cũ theo một kế hoạch có thể kiểm chứng.

Đổi một mật khẩu ở database chưa hoàn tất công việc. Giá trị trong vault, cấu hình ứng dụng, connection pool, job nền và các phiên đang tồn tại có thể ở những trạng thái khác nhau.

Bài học tập trung vào mật khẩu của tài khoản database, đồng thời phân biệt với token ngắn hạn, certificate, quyền role và khóa mã hóa dữ liệu. PostgreSQL được dùng cho một số ví dụ kỹ thuật; các hệ quản trị và dịch vụ quản lý secret có thể có ngữ nghĩa khác.

Sau bài học, bạn có thể:

- Lập danh mục credential và những thành phần sử dụng nó.
- Chọn cách rotation một tài khoản, hai tài khoản hoặc credential động.
- Thiết kế quy trình có phiên bản, kiểm thử và đối soát khi lỗi.
- Tích hợp rotation với ứng dụng và connection pool.
- Phân biệt đổi credential, thu hồi quyền và kết thúc phiên.
- Thu thập bằng chứng đủ dùng mà không ghi secret vào log.

Các sơ đồ, trạng thái và mã giả là mô hình thiết kế. Chúng không phải cấu hình tích hợp sẵn của một sản phẩm và không tự được triển khai chỉ vì xuất hiện trong tài liệu.

## 1. Rotation thay đổi điều gì?

Một credential có thể được mô tả bằng:

```text
Credential = (
  principal,
  authentication_method,
  secret_or_proof,
  target,
  version,
  validity
)
```

Ví dụ, principal là một login của ứng dụng, phương thức xác thực là mật khẩu, target là một instance database và version là định danh phiên bản trong vault.

Cần phân biệt:

| Công việc | Điều được thay đổi |
|---|---|
| Password rotation | Giá trị mật khẩu hoặc verifier phục vụ xác thực |
| Token renewal hoặc phát hành token mới | Bằng chứng truy cập và thời hạn theo cơ chế token |
| Certificate rotation | Certificate, khóa riêng hoặc chuỗi tin cậy liên quan |
| Thu hồi role hoặc grant | Thẩm quyền thực hiện hành động |
| Kết thúc phiên | Khả năng tiếp tục dùng một kết nối đang tồn tại |
| Rotation khóa mã hóa dữ liệu | Vật liệu mật mã bảo vệ dữ liệu |

Các việc có thể cần phối hợp, nhưng không thay thế cho nhau.

Một credential mới vẫn có thể mang quyền quá rộng. Một credential cũ bị vô hiệu hóa cũng không làm dữ liệu đã bị sao chép trở nên bí mật trở lại.

### Mật khẩu database khác mật khẩu hệ điều hành

PostgreSQL quản lý mật khẩu database riêng với mật khẩu người dùng hệ điều hành. Phương thức xác thực và cách lưu verifier cần tương thích với client sử dụng. [PostgreSQL: Password Authentication](https://www.postgresql.org/docs/current/auth-password.html)

Do đó, việc đổi một secret có tên “database password” trong kho cấu hình không chứng minh database đã chấp nhận giá trị đó. Phải xác minh ở đúng hệ thống đích.

## 2. Xác định mục tiêu trước khi chọn cách rotation

Có ít nhất ba tình huống khác nhau.

### Rotation định kỳ

Mục tiêu là thay credential theo chính sách của tổ chức, giảm thời gian một giá trị tồn tại và duy trì khả năng vận hành.

Có thể có một khoảng chuyển tiếp được kiểm soát nếu chiến lược hỗ trợ. Khoảng này cần có giới hạn và bằng chứng, không để trở thành việc giữ nhiều credential cũ vô thời hạn.

### Rotation sau nghi ngờ lộ credential

Mục tiêu ưu tiên là chặn khả năng sử dụng trái phép. Cần xem cả phiên còn sống, quyền đã được dùng, credential khác có thể đã bị đọc và thay đổi tạo quyền bền vững.

Không quay lại một mật khẩu đã bị nghi lộ chỉ để làm ứng dụng nhanh chóng hoạt động lại.

### Rotation do thay đổi cơ chế xác thực hoặc nền tảng

Ví dụ, chuyển cách lưu mật khẩu, thay driver hoặc đổi tích hợp vault. Một lần thử thành công bằng client quản trị chưa chứng minh mọi ứng dụng cũ đều tương thích.

Cần kiểm tra đúng đường xác thực của các consumer, bao gồm proxy, pool và endpoint mà chúng thật sự sử dụng.

### Không có một lịch duy nhất cho mọi tài khoản

Lịch rotation cần dựa trên chính sách, mức nhạy cảm, khả năng tự động hóa và đặc tính vận hành của từng loại credential. Quan trọng là có tiêu chí rõ và phát hiện khi rotation không hoàn tất, thay vì chỉ ghi nhận lịch đã chạy.

Tài khoản replication, backup, migration và runtime có phụ thuộc khác nhau. Không đưa tất cả vào cùng một quy trình mà chưa xác minh.

## 3. Kiểm kê credential và consumer

Trước khi đổi giá trị, cần biết ai đang dùng nó.

| Nhóm consumer | Phụ thuộc cần kiểm tra |
|---|---|
| Dịch vụ web hoặc API | Cách đọc secret, cache, pool và rollout |
| Job nền | Thời điểm chạy, thời gian tồn tại và cách lấy credential |
| Scheduler hoặc batch | Có thể không khởi động trong cửa sổ quan sát ngắn |
| Migration runner | Quyền đặc biệt và đường kích hoạt owner |
| Backup hoặc khôi phục | Credential của tác vụ và khả năng sử dụng khi sự cố |
| Monitoring | Kết nối giám sát có thể dùng riêng hoặc bị dùng chung ngoài ý định |
| BI hoặc công cụ hỗ trợ | Cấu hình local và credential được lưu bên ngoài vault |
| Proxy hoặc connection broker | Danh tính phía client và phía database có thể khác |
| Replication hoặc tích hợp dữ liệu | Kết nối dài hạn và tác động khi phải kết nối lại |

Một bản ghi quản trị nên có:

```text
credential_id
principal_id
database_target_id
authentication_method
secret_store_reference
current_version_reference
owner_team
consumer_set
rotation_strategy
retirement_deadline
session_handling_policy
last_verified_rotation
recovery_runbook_reference
```

Không lưu secret thật trong danh mục. Dùng tham chiếu được kiểm soát.

### Tài khoản dùng chung làm rotation khó hơn

Nếu năm ứng dụng dùng một login, một thay đổi có thể ảnh hưởng cả năm. Cũng khó xác định consumer nào chưa cập nhật và ai đã sử dụng giá trị bị lộ.

Tách danh tính theo chức năng và ranh giới cần thiết giúp giảm phạm vi ảnh hưởng. Tuy nhiên, phải quản lý vòng đời những danh tính mới; tạo thêm nhiều login mà không có chủ sở hữu cũng làm tăng quyền tồn đọng.

### Quyền đọc secret cũng cần least privilege

Không nên để mọi workload đọc một thư mục secret chứa cả runtime, migration và tài khoản điều khiển rotation.

Một consumer chỉ cần quyền đọc credential của chức năng mình. Bộ điều phối cần quyền riêng để quản lý phiên bản và thực hiện thay đổi, với giới hạn target rõ ràng.

## 4. Ba chiến lược chính

### 4.1. Thay mật khẩu cho một tài khoản

Principal giữ nguyên, giá trị xác thực thay đổi. Điểm khó là phối hợp thời điểm database và consumer chuyển sang giá trị mới.

Một connection pool còn kết nối đã xác thực có thể tiếp tục phục vụ trong khi các lần mở kết nối mới gặp lỗi. Vì vậy, health check dựa vào kết nối cũ dễ tạo kết luận sai.

### 4.2. Luân phiên hai danh tính

Có hai login, chẳng hạn app_a và app_b. Hệ thống chuẩn bị danh tính không đang làm đích chính, kiểm tra quyền và kết nối, rồi chuyển consumer.

Một mô hình tách quyền có thể là:

```text
app_a ----+
         |
         +--> runtime_permission_role --> đúng quyền dữ liệu cần thiết
         |
app_b ----+

schema_owner: chủ thể riêng, không phải app_a hoặc app_b
```

Mục tiêu là giữ quyền nghiệp vụ ổn định trong khi thay danh tính đăng nhập. Tuy nhiên, phải kiểm tra sự tương đương thực tế: RLS, cấu hình phiên, mapping, quota và logic dựa vào tên người dùng có thể tạo khác biệt.

### 4.3. Phát hành credential động

Một dịch vụ quản lý secret có thể tạo credential theo lease hoặc theo job. Consumer nhận một danh tính có thời hạn và xử lý renew hoặc thay thế theo cơ chế đó.

HashiCorp Vault phân biệt dynamic roles và static roles; static role ánh xạ tới một username database, còn dynamic role phục vụ phát hành credential theo cấu hình. Khả năng cụ thể phụ thuộc plugin và database. [HashiCorp Vault: Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)

Credential động vẫn cần quyền hẹp, xử lý phiên, thất bại thu hồi và dọn đối tượng. Không coi TTL trong hệ thống quản lý lease là bằng chứng mọi khả năng truy cập đã biến mất tức thời.

### So sánh theo yêu cầu vận hành

| Tiêu chí | Một tài khoản | Hai danh tính | Credential động |
|---|---|---|---|
| Số principal cố định | Ít | Thường có cặp được quản lý | Có thể phát sinh nhiều principal theo lease |
| Cửa sổ chuyển đổi | Cần phối hợp chặt | Có thể có overlap được kiểm soát | Theo vòng đời cấp và thay credential |
| Kiểm tra quyền | Principal giữ nguyên | Phải tránh lệch quyền giữa hai bên | Phải kiểm soát template và quyền mỗi lần cấp |
| Thu hồi | Giá trị cũ và phiên | Danh tính cũ, giá trị cũ và phiên | Lease, principal và phiên theo khả năng |
| Nguy cơ bị bỏ sót | Consumer giữ giá trị cũ | Một danh tính cũ tiếp tục dùng được | Principal hoặc lease không dọn được |

Các ô mô tả mục tiêu thiết kế, không bảo đảm mọi sản phẩm có cùng khả năng.

### Thành công của nhà cung cấp khác mục tiêu loại bỏ credential cũ

AWS Secrets Manager có chiến lược single user và alternating users. Trong alternating users, cả hai credential có thể vẫn hợp lệ sau rotation theo thiết kế của dịch vụ. [AWS Secrets Manager: Rotation Strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)

Vì vậy, không tuyên bố “rotation thành công nên mật khẩu cũ chắc chắn không dùng được”. Nếu kế hoạch yêu cầu loại bỏ credential cũ sau một deadline, cần một chiến lược hoặc bước retirement được hỗ trợ và kiểm chứng.

Không tự sửa tài khoản phụ của một cơ chế được nhà cung cấp quản lý khi chưa hiểu tác động tới vòng rotation tiếp theo.

## 5. Mô hình trạng thái cho một lần rotation

Mô hình dưới đây là đề xuất điều phối cho bài học:

```text
PLANNED
   |
   v
CANDIDATE_STORED
   |
   v
TARGET_UPDATED
   |
   v
CANDIDATE_VERIFIED
   |
   v
PUBLISHED
   |
   v
CONSUMERS_SWITCHING
   |
   v
SWITCH_VERIFIED
   |
   v
RETIREMENT_VERIFIED
```

Có thể có các trạng thái ngoại lệ:

```text
TARGET_STATE_UNKNOWN
PUBLISH_PENDING
CONSUMER_PENDING
RETIREMENT_PENDING
RECOVERY_REQUIRED
```

Không gộp mọi trạng thái vào một cờ rotated=true.

### Tách ba loại bằng chứng

1. Database chấp nhận credential ứng viên trên kết nối mới.
2. Consumer đã sử dụng phiên bản được công bố theo đúng đường vận hành.
3. Credential hoặc danh tính cũ được xử lý theo mục tiêu retirement.

Một lần test đăng nhập thành công chỉ chứng minh điểm thứ nhất trong phạm vi đường test. Nó không chứng minh hai điểm còn lại.

### Phiên bản và định danh thao tác

Một rotation cần có định danh ổn định:

```text
rotation_id
target_id
principal_id
candidate_version_id
expected_current_version_id
configuration_revision
controller_owner
started_at
deadline
```

Retry phải tiếp tục cùng một ứng viên hoặc đối soát trạng thái đã có, không sinh một mật khẩu ngẫu nhiên mới ở mỗi lần gọi lại.

AWS Secrets Manager cũng tách các bước tạo, đặt ở đích, thử và hoàn tất phiên bản. Đây là một ví dụ sản phẩm cho thấy việc tạo secret khác với hoàn tất rotation. [AWS Secrets Manager: Lambda Rotation Functions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_lambda-functions.html)

Không dùng nhãn phiên bản của một sản phẩm như tên trạng thái bắt buộc cho mọi hệ thống.

## 6. Quy trình rotation có thể đối soát

### Bước 1: Xác minh đích và thẩm quyền

Kiểm tra principal, endpoint, database và loại credential từ dữ liệu có thẩm quyền.

Không để nội dung secret do người khác sửa chuyển rotation agent sang một host hoặc user ngoài phạm vi. Agent có thể trở thành một thành phần bị lợi dụng để gửi credential hoặc thực hiện quản trị ở sai đích.

Quyền của rotation agent cần hạn chế theo chức năng. Nếu khả năng của database buộc dùng quyền rộng, phải ghi nhận phạm vi ảnh hưởng và bảo vệ agent tương xứng.

### Bước 2: Tạo và giữ ứng viên an toàn

Tạo giá trị bằng cơ chế sinh phù hợp của hệ thống. Lưu ứng viên dưới phiên bản pending hoặc trạng thái tương đương mà consumer thông thường chưa tự lấy làm current.

Cần kiểm tra giới hạn ký tự, độ dài và cách truyền tới driver. Không cắt ngắn hoặc sửa giá trị theo những quy tắc khác nhau ở vault và database.

Ứng viên đã lưu giúp phục hồi sau khi tiến trình bị dừng. Không ghi nó vào log để làm “bản backup”.

### Bước 3: Thay đổi tại database

Áp dụng ứng viên vào đúng principal theo plugin hoặc API được phép.

Nếu nhận timeout, trạng thái có thể chưa xác định: database có thể đã thay đổi nhưng agent không nhận phản hồi. Không kết luận thất bại hoàn toàn chỉ từ lỗi mạng.

Dùng journal và một kết nối kiểm chứng mới để xác định trạng thái, với retry có giới hạn và tránh gây khóa tài khoản.

### Bước 4: Kiểm chứng ứng viên

Mở kết nối mới qua đường xác thực thực tế. Xác minh đúng endpoint, database và principal, rồi thực hiện phép thử an toàn phản ánh quyền cần thiết.

SELECT 1 chỉ chứng minh một phiên có thể chạy biểu thức đơn giản. Nó không chứng minh quyền đọc bảng nghiệp vụ, ghi dữ liệu hoặc sử dụng schema đúng.

Nếu cần kiểm tra thao tác ghi, dùng dữ liệu thử hoặc cơ chế được thiết kế cho mục đích đó. Không phát sinh giao dịch nghiệp vụ thật chỉ để chứng minh credential hoạt động.

### Bước 5: Công bố phiên bản

Chỉ chuyển tham chiếu current sau khi đạt điều kiện của chiến lược. Việc công bố cần kiểm tra expected current để tránh rotation cũ ghi đè một rotation mới.

Một thao tác so sánh phiên bản trong cơ sở dữ liệu local không tự khóa những API ngoài hệ thống. Cần dùng khả năng cập nhật có điều kiện của kho secret nếu có, tuần tự hóa phù hợp và đối soát sau thay đổi.

### Bước 6: Chuyển consumer

Consumer lấy phiên bản mới, tạo kết nối mới và xác nhận khả năng vận hành. Theo dõi những consumer chậm, offline hoặc chỉ chạy định kỳ.

Nếu một job chưa chạy trong cửa sổ quan sát, không báo “mọi consumer đã chuyển” chỉ vì chưa thấy lỗi từ nó.

### Bước 7: Retirement và xác minh

Theo kế hoạch đã chọn, xử lý khả năng đăng nhập bằng credential cũ, danh tính cũ và phiên cũ. Đánh dấu phần chưa được xác minh thay vì đóng quy trình sớm.

Lưu bằng chứng không chứa secret: version ID, principal, test reference, consumer revision, thời điểm và kết quả.

## 7. Connection pool: điểm dễ tạo cảm giác rotation đã thành công

Một connection pool thường giữ các kết nối đã được xác thực. Thay giá trị secret mà ứng dụng đọc không tự làm mọi kết nối trong pool xác thực lại.

Cần phân biệt:

```text
Secret version trong vault
    khác
Credential mà pool dùng để mở kết nối mới
    khác
Các kết nối đã tồn tại trong pool
```

Trong rotation single user của AWS Secrets Manager, các kết nối database đang mở không bị ngắt chỉ vì rotation diễn ra. [AWS Secrets Manager: Single User Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)

Đối với các hệ thống khác, cần xác minh hành vi cụ thể thay vì giả định việc đổi mật khẩu tự kết thúc mọi phiên.

### Bốn điểm cần kiểm tra trong ứng dụng

1. Secret được đọc một lần khi khởi động hay có cập nhật?
2. Khi đọc được phiên bản mới, cấu hình mở kết nối mới có thay đổi không?
3. Kết nối cũ được drain, đóng hoặc giới hạn thời gian thế nào?
4. Giao dịch đang chạy được xử lý ra sao?

Một API setPassword hoặc cập nhật biến môi trường không nên được coi là bảo đảm chung cho mọi thư viện. Phải đọc và kiểm chứng đúng cơ chế của driver, pool và cách ứng dụng cấu hình nó.

### Mô hình thay thế pool theo thế hệ

Một thiết kế có thể tạo pool mới từ phiên bản đã được công bố, kiểm tra rồi chuyển luồng lấy kết nối. Đây là mã giả:

```text
function onCredentialVersionObserved(versionId):
    descriptor = loadTrustedCredentialDescriptor(versionId)
    require descriptor.targetId == configuredTargetId
    require descriptor.principal in approvedPrincipalSet

    expectedGeneration = poolRegistry.currentGeneration()
    candidatePool = buildPoolForVersion(descriptor)

    probeFreshAuthenticationAndRequiredAccess(candidatePool)

    switched = poolRegistry.compareAndSwitch(
        expectedGeneration,
        candidatePool,
        descriptor.versionId
    )

    if not switched:
        closePool(candidatePool)
        reconcileLatestVersion()
        return

    previousPool = poolRegistry.previousGeneration()
    stopNewBorrows(previousPool)
    drainWithinPolicy(previousPool)
    recordVersionMetadataOnly(descriptor.versionId)
```

Các hàm mô tả trách nhiệm, không phải API có sẵn của JDBC hoặc một pool cụ thể.

Việc so sánh thế hệ giúp tránh một sự kiện phiên bản cũ đến chậm thay lại pool mới. Nó không thay thế kiểm tra quyền và trạng thái credential ở database.

### Giới hạn tài nguyên trong lúc chuyển

Hai pool cùng tồn tại có thể làm tăng số kết nối. Kế hoạch phải tính tổng giới hạn, tốc độ tạo kết nối, tải xác thực và số instance.

Không để mọi instance đồng loạt mở toàn bộ pool tối đa ngay khi secret đổi. Có thể điều phối theo đợt hoặc dùng cơ chế giới hạn phù hợp.

Nếu một giao dịch dài không kết thúc trước deadline drain, phải có chính sách rõ. Không ngắt mù mọi kết nối chỉ để đưa một metric về không.

### Readiness phải dùng đúng bằng chứng

Một endpoint health trả thành công từ pool cũ không chứng minh phiên bản mới dùng được.

Nên theo dõi generation hoặc version ID mà consumer đang sử dụng và có phép kiểm tra kết nối mới phù hợp. Không ghi giá trị mật khẩu hoặc hash của mật khẩu vào metric để nhận diện phiên bản; dùng định danh phiên bản do hệ thống quản lý cung cấp.

## 8. Pseudocode điều phối rotation

Một controller có thể làm việc theo định danh thao tác:

```text
function rotate(rotationId):
    operation = loadApprovedRotationPlan(rotationId)
    require operation.target in allowedTargets
    require operation.principal in managedPrincipals(operation.target)

    lease = acquireControllerLease(operation.id)
    journal = loadOrCreateJournal(operation.id)

    candidate = loadOrCreateCandidateVersion(
        operationId = operation.id,
        expectedCurrent = operation.expectedCurrentVersion,
        secretReference = operation.secretReference
    )

    assertCandidateMatchesTrustedTarget(candidate, operation)

    reconcileTargetCredential(
        operationId = operation.id,
        candidate = candidate,
        strategy = operation.strategy
    )

    verification = verifyUsingFreshConnection(candidate, operation.testPlan)
    require verification.satisfiesRequiredChecks

    publishCandidateIfExpectedCurrentMatches(candidate, operation)

    observeConsumerTransition(operation)
    applyRetirementPlan(operation)
    reconcileEvidenceAndRemainingExceptions(operation)
```

Controller lease là một cơ chế điều phối, không tự bảo đảm API đang chạy của controller cũ đã bị hủy. Khi có cạnh tranh hoặc lease hết hạn, phải đánh giá khả năng cập nhật có điều kiện, fencing và đối soát tại các hệ thống đích.

### Giữ nguyên ứng viên khi retry

Nếu lần đầu đã đổi database sang candidate-V2 nhưng bị mất phản hồi, lần sau không nên sinh candidate-V3 rồi tiếp tục mà không biết V2 ở đâu.

Cần giữ journal và ứng viên dưới cùng operation ID, kiểm tra trạng thái trước khi chọn bước tiếp theo.

### Tách việc test và publish

Một ứng viên hợp lệ nhưng chưa publish là trạng thái có thể phục hồi. Một giá trị đã publish nhưng database chưa chấp nhận có thể gây lỗi diện rộng cho consumer.

Trong chiến lược một tài khoản, khoảng lệch giữa database và secret store vẫn phải được thiết kế và hạn chế. Không có một giao dịch phân tán tự động giữa hai hệ thống chỉ vì chúng được gọi trong cùng một hàm.

### Tránh kiểm thử sai principal hoặc sai target

Không kiểm tra bằng một credential quản trị khác rồi kết luận ứng viên của ứng dụng hoạt động.

Endpoint trong metadata phải được đối chiếu với target được quản lý. Nếu ứng dụng đi qua proxy, cần kiểm chứng cả đường ứng dụng thực sự dùng và phần xác thực phía database cần thiết. Một kết nối thành công qua cơ chế khác không chứng minh mật khẩu đang thử đã được chấp nhận.

## 9. Khôi phục khi các trạng thái không đồng bộ

| Tình huống | Việc cần xác định | Hướng xử lý theo kế hoạch |
|---|---|---|
| Candidate đã lưu, database chưa đổi | Candidate có đúng operation và target không | Tiếp tục đúng ứng viên hoặc hủy theo trạng thái quan sát |
| Database đã đổi, publish chưa xong | Candidate có kết nối mới thành công không | Phục hồi bước publish có kiểm soát, không tự sinh giá trị khác |
| Publish thành công, một consumer chưa chuyển | Consumer đang dùng version nào và có còn khả năng kết nối lại không | Điều phối cập nhật, cảnh báo và quản lý deadline |
| API đổi password timeout | Database đã áp dụng hay chưa | Đối soát bằng journal và test an toàn |
| Hai rotation cạnh tranh | Version nào là đích hiện hành hợp lệ | Chặn ghi đè từ thao tác cũ và xử lý đối tượng thừa |
| Vault mất kết nối | Consumer còn lease hoặc phiên hợp lệ nào | Theo chính sách cache, hết hạn và khả năng phục hồi |
| Failover sang endpoint khác | Trạng thái xác thực tại đích mới và đường ứng dụng | Kiểm chứng, không chỉ dùng kết quả ở primary cũ |
| Retirement lỗi | Credential, danh tính hoặc phiên nào còn có thể dùng | Giữ trạng thái pending và xử lý theo mức rủi ro |

Bảng là cách suy luận thiết kế, không thay thế runbook theo sản phẩm.

### Vì sao đổi con trỏ vault về phiên bản trước có thể làm hệ thống lỗi?

Trong chiến lược một mật khẩu cho một login, database có thể đã chấp nhận giá trị mới và không còn chấp nhận giá trị trước. Chuyển current trong vault về giá trị cũ không tự phục hồi trạng thái tại database.

Nếu chọn rollback, phải xác định cả trạng thái database, vault và consumer. Không chỉ “đổi lại nhãn”.

Đối với sự cố lộ credential, giá trị cũ có thể không còn được phép tái sử dụng. Khi đó cần một đường phục hồi dùng credential mới khác hoặc cơ chế ứng cứu phù hợp.

### Không biến retry thành bão xác thực

Lỗi xác thực lặp lại có thể gây tải, kích hoạt cơ chế khóa tài khoản hoặc làm che khuất nguyên nhân.

Cần giới hạn số lần thử, có backoff phù hợp và chỉ refresh secret khi có lý do. Không để mỗi request người dùng gặp lỗi database lại gọi vault liên tục.

Cũng không tự thử mọi phiên bản secret từng tồn tại. Việc đó mở rộng sử dụng dữ liệu cũ và làm khó đối soát.

## 10. Credential cũ và phiên cũ là hai đối tượng khác nhau

Một kế hoạch retirement cần nói rõ:

- Credential cũ có còn mở kết nối mới được không.
- Principal cũ có còn một phương thức xác thực khác không.
- Các phiên đã xác thực còn tồn tại tới khi nào.
- Những quyền hoặc credential khác có thể đã được tạo ra trong thời gian đó.

Một phép thử credential cũ thất bại do mạng bị chặn không chứng minh mật khẩu cũ đã bị vô hiệu hóa. Cần biết lỗi đến từ lớp nào và kiểm thử trên đường phù hợp.

### Hết hạn mật khẩu không phải hết hạn mọi cách truy cập

Trong PostgreSQL, VALID UNTIL giới hạn thời hạn mật khẩu, không phải tuổi thọ của role nói chung; nó không áp dụng theo cùng cách với phương thức xác thực không dùng mật khẩu. [PostgreSQL: CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html)

Vì vậy, không dùng một thuộc tính hết hạn mật khẩu làm bằng chứng rằng mọi certificate, liên kết danh tính hoặc phiên hiện hữu đều đã kết thúc.

### Quyền thay đổi password không phải mọi quyền quản trị

PostgreSQL có ALTER ROLE để quản lý thuộc tính role, trong đó có password; thẩm quyền thực hiện phụ thuộc loại thay đổi và role gọi lệnh. [PostgreSQL: ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html)

Rotation agent cần được thiết kế theo quyền thực tế mà hệ quản trị hỗ trợ. Không cấp superuser một cách mặc định chỉ vì agent “cần đổi mật khẩu”.

Nếu bắt buộc dùng một danh tính mạnh cho một tích hợp, phải tách nó khỏi runtime, bảo vệ đường sử dụng và xác định rõ phạm vi ảnh hưởng khi bị lộ.

### Kết thúc phiên cần kế hoạch an toàn

Trước khi kết thúc phiên, xác minh principal, đích và thời điểm kết nối. Tên ứng dụng do client đặt chỉ là thông tin hỗ trợ, không phải căn cứ tin cậy duy nhất.

Cần xem giao dịch, lock và tác vụ đang chạy. Kết thúc phiên có thể có tác động vận hành, còn thay credential không hoàn tác những thay đổi đã commit.

Khi ứng phó xâm nhập, yêu cầu chặn truy cập có thể cấp bách hơn việc drain êm. Quyết định phải theo kế hoạch sự cố và bằng chứng thực tế, không chờ tới lịch rotation tiếp theo.

## 11. Ví dụ PostgreSQL không đưa mật khẩu vào script

### Thay password trong thực hành tương tác

psql có lệnh meta password để nhập giá trị qua prompt, tránh đưa mật khẩu rõ vào lịch sử câu lệnh theo cách gõ trực tiếp một SQL chứa secret. [PostgreSQL: psql](https://www.postgresql.org/docs/current/app-psql.html)

Ví dụ trong phiên lab:

```text
\password lab_app_a
```

Lệnh yêu cầu quyền phù hợp. Trong hệ thống tự động, nên dùng plugin hoặc cơ chế truyền secret được thiết kế cho môi trường, thay vì nhét password vào chuỗi shell.

Không ghi hình, log terminal hoặc sao chép giá trị đã nhập vào ticket để làm bằng chứng. Bằng chứng là operation ID, principal, phiên bản và kết quả kiểm tra.

### Kiểm tra danh tính trên một kết nối mới

Sau khi mở đúng kết nối mới trong môi trường thử nghiệm:

```sql
SELECT
    current_database() AS database_name,
    session_user AS authenticated_role,
    current_user AS execution_role,
    pg_backend_pid() AS backend_pid;
```

Đối chiếu với target và principal mong muốn. Nếu middleware dùng một tài khoản phía database khác, kết quả phải được diễn giải theo kiến trúc đó.

### Quan sát các phiên liên quan

Một truy vấn minh họa, với quyền quan sát phù hợp:

```sql
SELECT
    datname,
    usename,
    application_name,
    pid,
    backend_start,
    state,
    xact_start
FROM pg_catalog.pg_stat_activity
WHERE datname = 'lab_app'
  AND usename IN ('lab_app_a', 'lab_app_b')
ORDER BY usename, backend_start;
```

pg_stat_activity cung cấp thông tin phiên như user đăng nhập, thời điểm backend bắt đầu và trạng thái. Quyền quan sát ảnh hưởng dữ liệu có thể thấy. [PostgreSQL: Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)

Không đưa query text vào báo cáo nếu không cần. Nó có thể chứa dữ liệu nhạy cảm.

### Giới hạn của việc quan sát username

Trong rotation một tài khoản, cả kết nối dùng mật khẩu cũ trước thời điểm đổi và kết nối mới có thể hiển thị cùng username.

Username không nói được phiên đã dùng secret version nào. Cần liên kết với generation pool, thời điểm kết nối và bằng chứng của consumer. Không cố suy ra version bằng cách ghi secret vào application_name.

Với hai danh tính, có thể phân biệt một phần bằng username, nhưng vẫn phải kiểm tra proxy, SET ROLE và mô hình ánh xạ đang dùng.

## 12. Tài khoản điều khiển rotation cũng phải được quản lý

Agent thường cần một đường xác thực để thay credential của tài khoản khác. Nếu đường này bị mất đồng bộ, các lần rotation tiếp theo có thể thất bại dù runtime vẫn hoạt động.

Cần kiểm kê riêng:

```text
Credential của consumer database
Credential của rotation agent
Credential để agent truy cập secret store
Khóa hoặc danh tính dùng để giải mã secret
Cấu hình target và quyền sửa cấu hình
```

Không gộp tất cả vào một secret mà cùng một job thay đổi thiếu điều phối.

Vault lưu ý credential quản trị database trong cấu hình engine cần dùng cơ chế rotation tương ứng; không quản lý cùng credential đó như một static role thông thường theo cách làm cấu hình engine mất hiệu lực. [HashiCorp Vault: Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)

Bài học thiết kế là xác định rõ bên nào là nguồn quản lý cho từng credential và cách các thành phần nhận giá trị mới. Không để hai controller độc lập cùng thay một principal mà không có ownership và đối soát.

### Bảo vệ agent theo phạm vi

- Chỉ cho phép target và principal đã đăng ký.
- Tách quyền đọc secret khỏi quyền thay policy hoặc cấu hình.
- Bảo vệ artifact, image và cấu hình của agent.
- Không log secret khi debug lỗi.
- Có đường khôi phục được kiểm thử.
- Lưu bằng chứng ai sửa cấu hình hoặc khởi động rotation.

Agent bị chiếm quyền có thể mở rộng ảnh hưởng tới nhiều credential mà nó quản lý. Phạm vi này phải được đánh giá như một nhóm quyền đặc biệt.

## 13. Bằng chứng kiểm toán và tiêu chí hoàn tất

Một quy trình không nên chỉ lưu last_rotated_at.

| Bằng chứng | Điều được chứng minh |
|---|---|
| Rotation ID và kế hoạch | Vì sao và trong phạm vi nào thực hiện |
| Candidate version ID | Ứng viên nào được quản lý |
| Kết quả cập nhật target | Bước thay đổi tại database đã được quan sát thế nào |
| Test kết nối mới | Credential được thử trên đường nào, bằng principal nào |
| Publish result | Phiên bản nào được công bố và thay phiên bản nào |
| Consumer acknowledgement | Consumer nào đã chuyển, còn phần nào chưa xác minh |
| Retirement result | Giá trị, principal và phiên cũ được xử lý tới đâu |
| Ngoại lệ | Điều gì chưa hoàn tất và ai chịu trách nhiệm |

Không cần lưu password hoặc verifier trong hồ sơ. Secret version ID và tham chiếu được bảo vệ là đủ để liên kết.

### Hoàn tất theo mục tiêu đã định

Nếu mục tiêu chỉ là chuyển consumer sang phiên bản mới trong một cơ chế alternating có overlap, trạng thái cần diễn đạt đúng phạm vi đó.

Nếu mục tiêu là loại bỏ khả năng dùng credential cũ sau deadline, chưa được đánh dấu retirement thành công khi nó còn đăng nhập được hoặc còn những phiên chưa xử lý theo chính sách.

Một báo cáo rõ có thể tách:

```text
CREDENTIAL_SWITCH=VERIFIED
OLD_AUTHENTICATION=DISABLED_VERIFIED
OLD_SESSIONS=HANDLED_PER_POLICY
CONSUMER_EXCEPTIONS=NONE
```

Nếu chưa chứng minh được một dòng, giữ trạng thái pending hoặc giới hạn kết luận. Không lấy việc lịch chạy không báo lỗi làm bằng chứng thay thế.

### Chỉ số hữu ích

- Tuổi của phiên bản hiện hành so với chính sách.
- Rotation đang chờ publish hoặc consumer transition.
- Số consumer chưa xác nhận chuyển.
- Số lỗi xác thực sau một lần công bố.
- Thời gian từ switch tới retirement được xác minh.
- Số credential hoặc principal cũ còn hiệu lực ngoài kế hoạch.
- Rotation agent hoặc lease thu hồi bị lỗi.

Các chỉ số phải đo trạng thái thực, không chỉ thời điểm cập nhật cơ sở dữ liệu của scheduler.

## 14. Tình huống: health check xanh nhưng restart làm dịch vụ lỗi

### Bối cảnh

Payment API đọc password một lần khi khởi động. Pool giữ các kết nối dài hạn. Hệ thống rotation đổi password ở database và cập nhật vault thành công.

Health check của dịch vụ dùng một kết nối đã có nên vẫn trả xanh. Sau đó một instance restart và đọc secret từ một cache cấu hình cũ. Nó không mở được kết nối.

### Nguyên nhân

Có ba trạng thái khác nhau:

1. Database chấp nhận giá trị mới.
2. Vault đã công bố version mới.
3. Consumer chưa chắc cập nhật cách mở kết nối.

Kết nối cũ che giấu việc consumer không sẵn sàng reconnect.

### Cách sửa thiết kế

- Theo dõi version hoặc generation trong consumer.
- Kiểm chứng kết nối mới trước và sau chuyển.
- Thiết kế refresh hoặc rollout phù hợp.
- Đối soát cả instance mới và instance đang hoạt động.
- Quản lý cache và deadline có thể quan sát.
- Không kết luận mọi consumer đã chuyển chỉ từ health check tổng hợp.

Nếu đang xử lý sự cố lộ password, không khôi phục password cũ để “làm xanh” dịch vụ. Dùng đường phục hồi với credential được phép và xử lý nguyên nhân consumer chậm.

## 15. Bài thực hành trong môi trường thử nghiệm

Dùng database riêng, dữ liệu giả và credential do môi trường lab quản lý. Không dùng secret production để thử rotation.

### Bước 1: Lập danh mục

Chọn một login runtime và ít nhất hai consumer giả, chẳng hạn một dịch vụ giữ pool và một job chạy định kỳ.

Ghi rõ cách đọc secret, cache, quyền dữ liệu, phiên hiện hữu và tiêu chí retirement.

### Bước 2: Chọn chiến lược

Xác định một tài khoản, hai danh tính hay credential động. Ghi khả năng thực tế của database và công cụ quản lý secret.

Nếu dùng hai danh tính, kiểm tra quyền và ngữ nghĩa ứng dụng của cả hai. Không chỉ clone một lần rồi quên cập nhật khi ACL thay đổi.

### Bước 3: Tách trạng thái

Mô phỏng các bước lưu candidate, cập nhật target, test, publish, chuyển consumer và retirement.

Không lưu candidate vào một file không được bảo vệ để thuận tiện thực hành. Dùng cơ chế secret của môi trường.

### Bước 4: Kiểm tra các tình huống

| Tình huống | Kết quả mong đợi |
|---|---|
| Credential mới mở kết nối mới đúng target | Thành công khi đủ quyền và đúng cơ chế xác thực |
| Health check lấy kết nối cũ | Không dùng làm bằng chứng duy nhất cho version mới |
| Consumer restart sau switch | Lấy được version được phép và kết nối đúng |
| Job định kỳ chưa chạy | Được ghi là chưa xác minh, không tự coi đã chuyển |
| Candidate không đúng principal hoặc endpoint | Rotation bị chặn trước khi tác động |
| API đổi password timeout | Đối soát, không sinh ứng viên mới thiếu kiểm soát |
| Database đã đổi nhưng publish lỗi | Khôi phục từ journal và candidate đúng operation |
| Một sự kiện version cũ đến chậm | Không ghi đè cấu hình pool mới |
| Hai rotation cùng principal | Được tuần tự hóa hoặc xử lý cạnh tranh theo thiết kế |
| Vault tạm không sẵn sàng | Hành vi cache, lease và phục hồi đúng chính sách |
| Consumer dùng phương thức xác thực khác | Không nhầm thành bằng chứng password đã được chấp nhận |
| Credential cũ bị thử sau retirement | Bị từ chối ở đúng lớp cần xác minh |
| Phiên cũ còn tồn tại | Được xử lý hoặc theo dõi theo chính sách riêng |
| Hai login có quyền lệch nhau | Kiểm tra phát hiện trước khi switch |
| Kết nối đang chạy giao dịch khi drain | Không bị xử lý mù ngoài kế hoạch |
| Failover tới target được phép | Kiểm chứng lại đường xác thực và consumer |
| Rollback version vault mà database đã đổi | Quy trình phát hiện lệch trạng thái |
| Tìm kiếm log thực hành | Có metadata đối soát, không có password hoặc token |

### Bước 5: Hoàn thiện hồ sơ

Hồ sơ nên có sơ đồ consumer, state machine, bằng chứng kết nối mới, kết quả chuyển pool, một lỗi giả lập và cách retirement được xác minh.

Nếu chưa có tích hợp thực tế, phân biệt phần mô hình với phần đã kiểm chứng. Không gọi một sơ đồ rotation là bằng chứng rằng credential cũ đã hết hiệu lực.

## 16. Những lỗi cần tránh

**Chỉ thay giá trị trong vault.** Database và consumer phải được chuyển theo đúng chiến lược, có kiểm chứng ở đích.

**Chỉ đổi password ở database.** Consumer giữ giá trị cũ có thể lỗi khi reconnect.

**Coi health check xanh là đã hoàn tất.** Kết nối cũ có thể vẫn hoạt động trong khi kết nối mới thất bại.

**Sinh một password khác ở mọi lần retry.** Giữ định danh thao tác, ứng viên và journal để đối soát.

**Rollback bằng một thao tác đổi nhãn.** Phải xét trạng thái database, consumer và việc giá trị cũ có còn được phép tái sử dụng không.

**Giữ hai login mà không kiểm tra quyền.** ACL, cấu hình phiên và logic danh tính có thể bị lệch.

**Coi TTL hoặc password expiry là dừng mọi phiên.** Xác thực mới, lease, role và phiên là các đối tượng cần kiểm soát riêng.

**Để nhiều controller cùng quản lý một principal.** Cần ownership, phiên bản và cơ chế tránh ghi đè.

**Ghi secret vào log để dễ debug.** Dùng version ID, operation ID và kết quả kiểm tra.

**Xem rotation là toàn bộ ứng phó lộ credential.** Cần điều tra phiên, quyền đã dùng, credential khác và thay đổi bền vững có thể đã phát sinh.

Database credential rotation đạt mục tiêu khi việc thay đổi có thể được theo dõi từ candidate tới database, consumer và retirement theo phạm vi đã định. PAM giúp quản lý danh tính, vault và thẩm quyền; thiết kế ứng dụng cùng kiểm chứng phiên mới quyết định việc chuyển đổi có hoạt động đúng và kết thúc được rủi ro của giá trị cũ hay không.
