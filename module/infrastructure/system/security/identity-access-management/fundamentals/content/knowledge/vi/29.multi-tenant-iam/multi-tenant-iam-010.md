# Tenant onboarding: khởi tạo tenant và thiết lập IAM ban đầu

## 1. Onboarding tenant là thiết lập một ranh giới tin cậy mới

**Tenant onboarding** là quá trình đưa một tổ chức hoặc một nhóm khách hàng vào hệ thống đa tenant, từ yêu cầu đăng ký đến khi tenant có thể hoạt động với danh tính, quyền và cấu hình bảo mật ban đầu hợp lệ.

Trong phạm vi IAM, quá trình này không chỉ tạo một dòng dữ liệu trong bảng `tenant`. Nó phải trả lời được:

- Ai có quyền yêu cầu tạo tenant?
- Tenant mới có định danh và ranh giới dữ liệu nào?
- Ai được trở thành quản trị viên đầu tiên, dựa trên bằng chứng nào?
- Những vai trò, chính sách và thông tin xác thực nào được cấp?
- Khi nào người dùng và workload được phép sử dụng tài nguyên của tenant?
- Nếu một bước lỗi hoặc bị gọi lại, hệ thống duy trì trạng thái an toàn ra sao?

Ví dụ, Lan đăng ký một dịch vụ quản lý hợp đồng cho công ty An Bình. Một quy trình onboarding tốt không tự kết luận rằng bất kỳ người nào có email kết thúc bằng `@an-binh.example` đều được quản trị công ty. Nó cũng không cấp quyền quản trị nền tảng cho Lan chỉ vì Lan là người tạo tenant.

Kết quả cần đạt là một tenant được nhận diện ổn định, có người quản trị đã được ràng buộc đúng danh tính, có quyền tối thiểu cần thiết và có dấu vết kiểm toán cho toàn bộ quá trình.

## 2. Phân biệt tạo tenant, tạo tài khoản và gia nhập tenant

Ba thao tác này có quan hệ nhưng không tương đương:

| Thao tác | Đối tượng được tạo hoặc thay đổi | Quyền cần chứng minh |
| --- | --- | --- |
| Tạo tài khoản người dùng | Danh tính đăng nhập của một cá nhân | Người đó kiểm soát phương thức đăng nhập theo quy trình đăng ký |
| Tạo tenant | Một phạm vi khách hàng mới | Chủ thể được phép khởi tạo tenant theo mô hình sản phẩm |
| Gia nhập tenant | Quan hệ thành viên giữa một danh tính và tenant | Có lời mời, phê duyệt hoặc cơ chế cấp phát thành viên hợp lệ |

Lan có thể đã có tài khoản để tham gia một tenant khác trước khi đăng ký An Bình. Khi đó, onboarding An Bình tạo thêm tenant và quan hệ thành viên mới, không nhất thiết tạo thêm tài khoản người dùng.

Ngược lại, việc một người vừa xác minh email chỉ chứng minh điều kiện của bước xác minh email. Nó không tự chứng minh người đó đại diện hợp lệ cho một doanh nghiệp đã tồn tại trong hệ thống.

Mô hình dữ liệu nên biểu diễn rõ các khái niệm:

```text
User
  id
  authenticationIdentities

Tenant
  id
  displayName
  lifecycleState

Membership
  id
  tenantId
  userId
  state

RoleAssignment
  membershipId
  tenantId
  roleId
```

Quyền quản trị tenant được gắn với quan hệ thành viên trong tenant cụ thể. Nó không trở thành một thuộc tính quản trị toàn cục của `User`.

## 3. Chọn mô hình onboarding và mức bằng chứng phù hợp

### 3.1. Đăng ký tự phục vụ

Một người dùng đã xác thực được phép tạo một không gian làm việc mới. Người khởi tạo có thể trở thành quản trị viên đầu tiên của chính không gian đó theo chính sách sản phẩm.

Điều này không đồng nghĩa người khởi tạo được quyền tiếp quản một tenant đã tồn tại có cùng tên, hoặc được coi là đại diện đã xác minh của một tổ chức ngoài đời thực.

Hệ thống vẫn cần kiểm soát điều kiện tạo tenant, hạn mức và hành vi lạm dụng. Các điều kiện này do phía server quyết định, không do client gửi cờ `approved=true`.

### 3.2. Onboarding do nền tảng phê duyệt

Nhân viên hoặc một quy trình có thẩm quyền kiểm tra yêu cầu trước khi tạo tenant hoặc trước khi kích hoạt. Việc phê duyệt cần có định danh người thực hiện, phạm vi quyết định và dấu vết kiểm toán.

Tài khoản hỗ trợ tạo tenant không vì vậy nên có quyền truy cập thường trực vào toàn bộ dữ liệu của tenant mới.

### 3.3. Onboarding qua lời mời

Nền tảng tạo tenant ở trạng thái chờ rồi mời một người cụ thể nhận quyền quản trị ban đầu.

Lời mời phải ràng buộc đến đúng tenant, đúng mục đích và đúng người nhận theo cơ chế nhận diện đã định. Người mở được đường dẫn vẫn cần hoàn tất các bước xác thực và xác minh tương ứng; không nên coi một đường dẫn bị chuyển tiếp là bằng chứng đầy đủ cho mọi quyền quản trị.

### 3.4. Cấp phát qua một hệ thống quản lý khác

Tenant có thể được tạo bởi một hệ thống đối tác hoặc quy trình tự động. Khi đó, phải xác thực bên gọi và kiểm tra phạm vi mà bên gọi được phép khởi tạo.

Quyền tạo tenant cho một nhóm khách hàng cụ thể không nên được diễn giải thành quyền tạo hoặc sửa mọi tenant trên nền tảng.

Các mô hình có thể kết hợp, nhưng tiêu chí chấp nhận bằng chứng và người chịu trách nhiệm cho từng quyết định phải rõ ràng.

## 4. Dùng một vòng đời có trạng thái tường minh

Một vòng đời minh họa:

```text
REQUESTED
    |
    v
VERIFIED
    |
    v
PROVISIONING
    |
    v
PENDING_ACTIVATION
    |
    v
ACTIVE
```

Ý nghĩa các trạng thái cần được định nghĩa trong hệ thống:

| Trạng thái | Ý nghĩa về IAM | Khả năng truy cập |
| --- | --- | --- |
| `REQUESTED` | Yêu cầu đã được tiếp nhận | Chỉ xem hoặc tiếp tục yêu cầu theo quyền của người khởi tạo |
| `VERIFIED` | Đã đủ bằng chứng cho mô hình onboarding được chọn | Chưa cho sử dụng nghiệp vụ bình thường |
| `PROVISIONING` | Đang tạo các thành phần và quyền ban đầu | Chỉ các thao tác cấp phát được kiểm soát |
| `PENDING_ACTIVATION` | Đang chờ các điều kiện kích hoạt còn lại | Chỉ các thao tác hoàn tất onboarding được cấp riêng |
| `ACTIVE` | Các điều kiện bắt buộc đã thỏa mãn | Được truy cập theo quyền thành viên và chính sách |

`VERIFIED` ở đây nghĩa là đạt tiêu chí onboarding của sản phẩm; không mặc nhiên có nghĩa đã xác minh tư cách pháp lý của doanh nghiệp.

Có thể bổ sung `FAILED`, `CANCELLED` hoặc `EXPIRED` theo thiết kế. Điều quan trọng là lỗi cấp phát không được tự đưa tenant về `ACTIVE`.

Endpoint nghiệp vụ phải kiểm tra trạng thái tenant ở nơi thích hợp. Một bản ghi tenant tồn tại nhưng chưa kích hoạt không được sử dụng chỉ vì người dùng biết ID của nó.

Trong thời gian chờ, hệ thống có thể cho người khởi tạo cấu hình SSO hoặc đăng ký MFA. Những khả năng này cần một phạm vi onboarding riêng, không phải bỏ qua toàn bộ kiểm tra quyền vì tenant chưa có quyền hoàn chỉnh.

## 5. Tạo định danh tenant và xử lý trùng lặp

### 5.1. ID nội bộ ổn định

Server cấp một tenant ID ổn định và dùng nó làm khóa cho quan hệ thành viên, chính sách, cấu hình và tài nguyên.

Tên hiển thị, tên miền và slug phục vụ đường dẫn có thể thay đổi. Chúng không nên là bằng chứng duy nhất để xác định quyền sở hữu tenant.

Ví dụ:

```text
tenantId: tenant-8f31
displayName: Công ty An Bình
slug: an-binh
state: PROVISIONING
```

Client có thể đề xuất tên hiển thị hoặc slug theo quy định sản phẩm. Nó không được tự chọn một ID đang thuộc tenant khác rồi yêu cầu hệ thống ghi đè hoặc thêm quyền quản trị.

### 5.2. Trùng tên không có nghĩa trùng quyền sở hữu

Hai tổ chức có thể có tên tương tự. Một yêu cầu đăng ký có cùng tên hoặc tên miền với một tenant hiện có không được tự động liên kết với tenant đó.

Nếu hệ thống phát hiện khả năng trùng, cần chuyển sang quy trình xác minh hoặc gia nhập tenant phù hợp. Tránh trả thông tin nhạy cảm về tenant hiện có chỉ để hỗ trợ kiểm tra tên.

### 5.3. Chống tạo lặp khi retry

Client có thể gửi lại yêu cầu vì mất mạng trong khi server đã tạo tenant. Một khóa idempotency giúp hệ thống nhận diện lại cùng một thao tác tạo.

Bản ghi idempotency cần có phạm vi, chẳng hạn người khởi tạo và loại thao tác; có cách đối chiếu nội dung yêu cầu; và được xử lý an toàn khi hai request chạy đồng thời.

```text
(actorId, operation, idempotencyKey)
    -> requestFingerprint
    -> onboardingRequestId
    -> tenantId
    -> resultState
```

Cùng khóa và cùng nội dung có thể trả về kết quả của yêu cầu trước. Cùng khóa nhưng nội dung không phù hợp cần bị từ chối theo hợp đồng API.

Không được để một người dùng dùng lại khóa của người khác để nhận thông tin tenant hoặc tiếp tục quy trình của người đó.

## 6. Xác lập quản trị viên đầu tiên mà không tạo cửa hậu

Đây là điểm đặc biệt của onboarding: tenant mới chưa có quản trị viên để cấp quyền cho quản trị viên đầu tiên.

Cách giải quyết là một **quyền khởi tạo được giới hạn**, do quy trình onboarding có thẩm quyền cấp. Nó không phải quy tắc “ai đến trước thì được làm admin”.

### 6.1. Ràng buộc người nhận quyền

Quy trình cần xác định người nhận quyền dựa trên mô hình đã chọn:

- Trong tự phục vụ: người khởi tạo đã xác thực và đáp ứng điều kiện tạo tenant.
- Trong mô hình lời mời: danh tính đã xác thực khớp với điều kiện nhận lời mời đã được phê duyệt.
- Trong mô hình có phê duyệt: người nhận quyền được ghi rõ trong quyết định hợp lệ.

Không lấy `ownerUserId`, `role=admin` hoặc `tenantId` do client gửi làm căn cứ duy nhất.

Nếu dùng danh tính liên kết, cần nhận diện đúng nhà phát hành và định danh chủ thể tại nhà phát hành đó. Việc một claim chứa email giống nhau chưa đủ để tùy ý hợp nhất với tài khoản có đặc quyền đã tồn tại.

### 6.2. Giới hạn quyền khởi tạo

Một quyền khởi tạo có thể được ràng buộc bởi:

```text
purpose = BOOTSTRAP_TENANT_OWNER
tenantId = tenant-8f31
onboardingRequestId = onboarding-251
intendedActor = user-73
expiresAt = ...
consumedAt = null
```

Nếu triển khai bằng token mời hoặc token nhận quyền, cần bảo vệ tính bí mật, giới hạn thời hạn, kiểm tra mục đích và ngăn dùng lại. Với token bí mật dạng ngẫu nhiên, có thể lưu giá trị kiểm chứng thay vì lưu nguyên token.

Một token chỉ hợp lệ để nhận quyền khởi tạo không được dùng làm access token cho API nghiệp vụ hoặc API quản trị nền tảng.

### 6.3. Ngăn cuộc đua nhận quyền

Hai request đồng thời có thể cùng thấy “tenant chưa có owner”. Nếu cả hai đều tự cấp quyền, tenant có thể có người quản trị ngoài dự kiến.

Kiểm tra trạng thái, tạo thành viên, gán vai trò khởi tạo và đánh dấu quyền đã sử dụng cần có cơ chế nhất quán phù hợp, như giao dịch cùng ràng buộc hoặc cập nhật có điều kiện.

Nếu chính sách chỉ cho một lần nhận quyền khởi tạo, phải bảo đảm chỉ một lần thành công. Điều này không có nghĩa tenant chỉ được phép có duy nhất một quản trị viên trong toàn bộ vòng đời; các quản trị viên bổ sung được cấp qua quy trình quản trị bình thường sau đó.

## 7. Cấp phát IAM theo nguyên tắc ít quyền nhất

Các thành phần ban đầu có thể gồm:

1. Bản ghi tenant và cấu hình bảo mật mặc định.
2. Quan hệ thành viên của quản trị viên đầu tiên.
3. Các vai trò tenant cần thiết.
4. Chính sách phân quyền cơ sở.
5. Phạm vi lưu trữ hoặc cấu hình phục vụ dữ liệu tenant.
6. Danh tính workload hoặc tích hợp nếu thực sự cần.
7. Cấu hình kiểm toán và cơ chế thông báo.

Không phải tenant nào cũng cần mọi thành phần ngay lập tức. Một tích hợp chưa được sử dụng không nên được cấp sẵn thông tin xác thực có quyền rộng chỉ để “tiện cho sau này”.

### 7.1. Tách quyền tenant với quyền nền tảng

Một bộ vai trò minh họa:

| Vai trò | Phạm vi | Khả năng ban đầu |
| --- | --- | --- |
| `tenant_owner` | Một tenant | Quản lý cấu hình và quản trị viên của tenant theo chính sách |
| `tenant_admin` | Một tenant | Quản lý thành viên hoặc tài nguyên được cho phép |
| `member` | Một tenant | Sử dụng nghiệp vụ theo quyền được giao |
| `platform_operator` | Phạm vi nền tảng đã được cấp | Vận hành nền tảng qua cơ chế riêng |

Không sao chép quyền nền tảng vào vai trò `tenant_owner`. Cũng không tự gán tất cả người dùng thuộc cùng tên miền vào vai trò quản trị viên.

### 7.2. Tài nguyên mới phải có chủ sở hữu đúng phạm vi

Vai trò tùy chỉnh, nhóm, API client và các bản ghi cấu hình được tạo khi onboarding cần gắn đúng tenant ID.

Khi dùng mẫu cấu hình, hãy tách cấu hình được phép dùng lại với dữ liệu riêng của tenant. Không sao chép API key, bí mật SSO, danh sách thành viên hay tài khoản hỗ trợ từ tenant mẫu.

### 7.3. Quyền của dịch vụ cấp phát

Dịch vụ onboarding thường có quyền tạo nhiều loại đối tượng. Đó là một danh tính workload có đặc quyền, cần giới hạn hành động và phạm vi sử dụng.

Dịch vụ phải kiểm tra yêu cầu đã được chấp nhận trước khi cấp phát. Không để một endpoint công khai kích hoạt tùy ý mọi năng lực mà tài khoản kỹ thuật của dịch vụ sở hữu.

## 8. Hoàn tất xác thực ban đầu: MFA, SSO và khôi phục

### 8.1. Đăng ký MFA cho tài khoản có đặc quyền

Nếu chính sách yêu cầu MFA cho quản trị viên, bước đăng ký cần hoàn tất trước khi cho phép các thao tác đặc quyền tương ứng.

Quy trình cần gắn việc đăng ký phương thức xác thực với đúng tài khoản đang được xác minh. Khi bật MFA, cần có phương án khôi phục được bảo vệ phù hợp để tránh biến mất thiết bị thành mất quyền quản trị vĩnh viễn.

Không gửi mật khẩu mặc định dùng chung cho mọi tenant. Nếu có bước kích hoạt tài khoản, thông tin dùng để kích hoạt cần giới hạn mục đích, thời hạn và khả năng dùng lại.

### 8.2. Thiết lập SSO theo từng tenant

Khi An Bình dùng nhà cung cấp danh tính riêng, cấu hình liên kết phải được gắn với An Bình và chỉ được thay đổi bởi chủ thể có thẩm quyền.

Cần kiểm tra các thành phần của kết nối theo giao thức và thiết kế sử dụng, ví dụ nhà phát hành được chấp nhận, ứng dụng nhận thông tin xác thực và ánh xạ chủ thể. Tránh tin một địa chỉ cấu hình do client bất kỳ gửi vào rồi coi mọi danh tính từ nguồn đó là quản trị viên tenant.

Trước khi bắt buộc SSO cho toàn tenant, nên xác nhận kết nối hoạt động với danh tính quản trị dự kiến và có đường khôi phục được kiểm soát. Nếu áp dụng bắt buộc quá sớm, một cấu hình sai có thể khóa chính người quản trị khỏi tenant.

Đăng nhập SSO thành công cũng chưa tự tạo ra mọi quyền thành viên. Nếu cho phép cấp phát thành viên khi đăng nhập lần đầu, chính sách cần xác định ai được gia nhập và vai trò mặc định có phạm vi nào.

### 8.3. Xác minh tên miền có ý nghĩa giới hạn

Xác minh quyền kiểm soát tên miền có thể giúp cấu hình khám phá đăng nhập hoặc chính sách gia nhập. Nó không tự chứng minh danh tính từng người, không tự chuyển quyền sở hữu tenant cũ và không thay thế quyết định gán vai trò.

Nếu cho phép người dùng cùng tên miền tự gia nhập, cần xác định tenant đích, điều kiện áp dụng, vai trò ít quyền và cách thu hồi. Không dùng quy tắc mơ hồ “cùng tên miền thì là admin”.

## 9. Xử lý giao dịch, lỗi từng phần và khả năng tiếp tục

Onboarding có thể chạm đến nhiều hệ thống: cơ sở dữ liệu ứng dụng, kho danh tính, dịch vụ lưu trữ và nhà cung cấp email. Không nên giả định mọi thao tác đều nằm trong một giao dịch duy nhất.

### 9.1. Ghi nhận từng bước đã hoàn thành

Một bản ghi tiến trình có thể lưu:

```text
onboardingRequestId = onboarding-251
tenantId = tenant-8f31
state = PROVISIONING

steps:
  tenant_record = DONE
  default_roles = DONE
  owner_membership = DONE
  storage_namespace = RETRYABLE_FAILURE
  activation = NOT_STARTED
```

Khi tiếp tục, hệ thống dùng cùng tenant ID và nhận diện các bước đã hoàn thành. Không tạo tenant, owner hoặc API client mới ở mỗi lần retry.

Mỗi bước cần xác minh đối tượng đã tồn tại có thực sự thuộc yêu cầu này và đúng cấu hình mong đợi. “Đã có đối tượng cùng tên” không đủ để coi bước đó thành công.

### 9.2. Giữ tenant chưa hoạt động cho đến khi đủ điều kiện

Nếu cấu hình bảo mật bắt buộc chưa được tạo, tenant phải ở trạng thái chưa cho sử dụng bình thường.

Một email chào mừng không được là bằng chứng rằng toàn bộ quá trình đã thành công. Thông báo thất bại có thể được retry riêng; quyết định kích hoạt phải dựa trên trạng thái có thẩm quyền của quy trình.

### 9.3. Bù trừ và thu hồi tài nguyên cấp dở

Nếu không thể hoàn tất, quy trình có thể cần thu hồi quyền khởi tạo, vô hiệu hóa thông tin xác thực hoặc dọn tài nguyên đã tạo.

Chỉ được bù trừ những đối tượng được xác nhận do yêu cầu onboarding này tạo và còn thuộc phạm vi xử lý. Không xóa một tài khoản người dùng toàn cục chỉ vì tạo một tenant thất bại; tài khoản đó có thể đang tham gia tenant khác.

Thông tin audit cần được giữ theo chính sách ngay cả khi tài nguyên cấp dở được dọn. Một trạng thái thất bại phải có cách phân biệt lỗi có thể retry với lỗi cần xem xét thủ công.

## 10. Minh họa luồng xử lý phía server

Mã giả dưới đây nhấn mạnh các điểm kiểm soát, không phải một API có thể triển khai nguyên trạng:

```text
function requestTenantOnboarding(credential, input, idempotencyKey):
    actor = authenticate(credential)
    requireCanRequestNewTenant(actor)

    request = reserveOrLoadRequest(
        actorId = actor.id,
        operation = "create-tenant",
        idempotencyKey = idempotencyKey,
        fingerprint = fingerprintOfAllowedInput(input)
    )

    requireSameRequesterAndCompatibleInput(request, actor, input)

    if request.completed:
        return safeResultForRequester(request, actor)

    verifyRequiredEvidence(request, actor)
    tenantId = reserveStableTenantId(request)

    provisionRequiredComponentsIdempotently(request, tenantId)
    return statusForRequester(request, actor)

function acceptInitialOwner(credential, bootstrapProof):
    actor = authenticate(credential)
    proof = validateBootstrapProof(bootstrapProof)

    requireProofPurpose(proof, "BOOTSTRAP_TENANT_OWNER")
    requireIntendedRecipient(proof, actor)
    requireAuthenticationConditions(actor, proof.tenantId)

    completeOwnerBootstrapConsistently(
        requestId = proof.onboardingRequestId,
        tenantId = proof.tenantId,
        actorId = actor.id,
        proofId = proof.id
    )

    return activationStatusVisibleTo(actor, proof.tenantId)

function activateTenant(requestId):
    request = loadTrustedOnboardingRequest(requestId)
    requireAllMandatoryProvisioningStepsSucceeded(request)
    requireInitialOwnerBindingCompleted(request)
    requireSecurityActivationConditionsSatisfied(request)

    changeStateConditionally(
        tenantId = request.tenantId,
        expectedState = "PENDING_ACTIVATION",
        newState = "ACTIVE"
    )

    recordActivationAndScheduleNotification(request)
```

Trong ví dụ này, `completeOwnerBootstrapConsistently` bao gồm kiểm tra quyền khởi tạo chưa bị sử dụng, trạng thái tenant phù hợp, thành viên và phép gán vai trò đúng tenant. Nếu thao tác trải qua nhiều hệ thống, cần một giao thức hoàn tất có trạng thái bền vững thay cho giả định về tính nguyên tử.

Việc đổi trạng thái cuối cũng phải tương thích với các bước trước đó. Một tiến trình đến muộn không được kích hoạt tenant đã bị hủy chỉ vì nó từng đọc được trạng thái chờ.

Các thông báo hoặc sự kiện sau kích hoạt nên được phát theo cơ chế có thể phục hồi khi tiến trình bị ngắt. Bên nhận sự kiện cần chịu được việc nhận lại cùng một sự kiện mà không cấp quyền thêm lần nữa.

## 11. Audit và quan sát quy trình

Nhật ký onboarding cần giúp trả lời ai đã yêu cầu, bằng chứng nào đã được chấp nhận, ai nhận quyền và tenant được kích hoạt khi nào.

Một sự kiện minh họa:

```json
{
  "eventType": "TENANT_INITIAL_OWNER_ASSIGNED",
  "onboardingRequestId": "onboarding-251",
  "tenantId": "tenant-8f31",
  "actorId": "user-73",
  "targetUserId": "user-73",
  "assignedRole": "tenant_owner",
  "result": "SUCCESS",
  "correlationId": "corr-92"
}
```

Với thao tác do nhân viên thực hiện thay khách hàng, `actorId` là người thao tác thật; `targetUserId` là người nhận quyền. Không ghi đè cả hai thành một danh tính rồi làm mất trách nhiệm giải trình.

Những sự kiện đáng theo dõi gồm tạo yêu cầu, phê duyệt, cấp phát thành phần, nhận quyền khởi tạo, thay đổi cấu hình xác thực và kích hoạt hoặc hủy tenant.

Không ghi token lời mời, bí mật client, mật khẩu hay mã khôi phục vào audit. Chỉ ghi định danh tham chiếu và thông tin cần thiết để điều tra.

Có thể quan sát số yêu cầu bị treo, bước retry nhiều lần, lần nhận quyền bị từ chối hoặc nhiều yêu cầu cùng nhắm đến một tên miền. Chỉ số vận hành cần đi cùng quyền xem phù hợp để dashboard không trở thành nơi lộ thông tin khách hàng.

## 12. Kiểm thử các điều kiện trước và sau kích hoạt

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Người chưa được phép gọi API tạo tenant | Không khởi tạo tenant hoặc quyền quản trị |
| Cùng một yêu cầu được gửi lại với cùng khóa idempotency | Không tạo thêm tenant hoặc cấp thêm quyền |
| Cùng khóa nhưng nội dung khác | Bị từ chối theo hợp đồng |
| Hai yêu cầu nhận cùng một quyền khởi tạo chạy đồng thời | Chỉ kết quả được quy trình cho phép mới được xác lập |
| Người khác sử dụng lời mời không dành cho mình | Không nhận quyền quản trị |
| Token khởi tạo đã hết hạn hoặc bị thu hồi | Không tạo hoặc nâng quyền thành viên |
| Client gửi vai trò quản trị nền tảng trong payload | Không được cấp quyền ngoài chính sách |
| Một bước cấp phát bắt buộc thất bại | Tenant chưa được đưa vào hoạt động |
| Tiến trình bị ngắt rồi chạy lại | Tiếp tục đúng yêu cầu và tenant đã đặt trước |
| Người dùng tham gia tenant khác gặp onboarding thất bại | Danh tính và quyền ở tenant khác vẫn được bảo toàn |
| Tenant đang chờ bị truy cập qua API nghiệp vụ | Không được sử dụng nghiệp vụ bình thường |
| Cấu hình SSO chưa xác minh nhưng yêu cầu bật bắt buộc | Không bỏ qua điều kiện kích hoạt đã định |
| Tiến trình cũ cố kích hoạt tenant đã hủy | Không chuyển tenant sang trạng thái hoạt động |
| Thông báo hoặc sự kiện được gửi lại | Không tạo thêm thành viên hay quyền |

Ngoài trạng thái response, cần kiểm tra những đối tượng thực tế đã được tạo, quyền đã gán, bí mật đã phát hành và trạng thái audit. Một request trả lỗi nhưng đã để lại một quản trị viên ngoài dự kiến vẫn là lỗi onboarding.

## 13. Tình huống áp dụng: An Bình mở tenant mới

Giả sử sản phẩm cho phép tự phục vụ, nhưng yêu cầu quản trị viên có MFA trước khi kích hoạt:

1. Lan đăng nhập bằng một tài khoản đã được xác minh theo quy trình của sản phẩm.
2. Server kiểm tra Lan được phép tạo tenant và tiếp nhận yêu cầu có khóa idempotency.
3. Server đặt trước `tenant-8f31`, tạo cấu hình mặc định và vai trò có phạm vi tenant.
4. Quy trình ràng buộc quyền nhận quản trị ban đầu với Lan và yêu cầu onboarding này.
5. Lan hoàn tất MFA rồi nhận vai trò `tenant_owner` trong `tenant-8f31`.
6. Quy trình xác nhận mọi thành phần bắt buộc đã sẵn sàng, chuyển tenant sang `ACTIVE` và ghi audit.
7. Lan mời người dùng khác hoặc thiết lập SSO bằng các quyền quản trị tenant thông thường.

Nếu Lan mất kết nối sau bước nhận quyền, lần gọi lại phải nhận ra kết quả đã hoàn tất theo cơ chế retry hợp lệ, không tạo owner mới hoặc mở lại quyền khởi tạo đã tiêu thụ.

Nếu An Bình muốn bắt buộc SSO về sau, đó là một thay đổi cấu hình cần kiểm tra riêng; việc tạo tenant thành công không chứng minh kết nối SSO mới đã hoạt động.

Một tenant sẵn sàng sử dụng khi ranh giới định danh, người quản trị đầu tiên, quyền tối thiểu và điều kiện xác thực đã được thiết lập nhất quán. Trạng thái hoạt động phải phản ánh những bằng chứng đó, thay vì chỉ phản ánh rằng lệnh tạo bản ghi tenant đã chạy xong.
