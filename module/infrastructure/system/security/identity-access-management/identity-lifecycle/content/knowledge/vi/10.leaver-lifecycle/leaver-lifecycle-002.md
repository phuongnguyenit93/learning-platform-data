# Sự kiện nghỉ việc trong Leaver lifecycle

## 1. Sự kiện nghỉ việc là gì?

Trong **Identity and Access Management (IAM)**, **sự kiện nghỉ việc** (*leaver event*) là tín hiệu nghiệp vụ có thẩm quyền cho biết quan hệ giữa một chủ thể và tổ chức sẽ kết thúc hoặc đã kết thúc. Khi được xác minh, sự kiện này kích hoạt quy trình xem xét và **thu hồi quyền truy cập đúng thời điểm**, gồm tài khoản, phiên đăng nhập, nhóm, quyền ứng dụng, credential và những đường truy cập không phụ thuộc đăng nhập SSO.

Ví dụ: nhân viên A kết thúc hợp đồng lúc 17:00 ngày 30/11. Hệ thống nhân sự gửi một sự kiện có mã nhân sự, loại thay đổi và thời điểm có hiệu lực. Bộ điều phối IAM tiếp nhận, xác minh nguồn, xác định tài khoản và quyền liên kết, đặt lịch hoặc thực hiện cắt truy cập, rồi đối soát kết quả tại các hệ thống đích.

Sự kiện nghỉ việc **không đồng nghĩa** với lệnh xóa người dùng. Đây là một **sự kiện nghiệp vụ**; IAM dùng nó để quyết định các hành động kỹ thuật theo chính sách và loại quan hệ. Không phải dữ liệu nào cũng cần xóa; hồ sơ, chứng cứ kiểm toán, dữ liệu nghiệp vụ và tài nguyên cần bàn giao có thể phải được lưu giữ hợp lệ.

Chủ đề này thuộc chương **Leaver lifecycle** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Trong mô hình **Joiner–Mover–Leaver (JML)**, Joiner tạo và cấp danh tính, Mover đổi quyền theo vai trò mới, còn Leaver chấm dứt khả năng truy cập không còn được ủy quyền. Luồng này liên quan chặt chẽ đến **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và kiểm soát quyền truy cập tồn dư**.

### Phân biệt ba thời điểm quan trọng

- **Sự kiện được ghi nhận:** HRIS hoặc nguồn hợp lệ biết quyết định nghỉ việc.
- **Sự kiện có hiệu lực:** thời điểm tổ chức yêu cầu chấm dứt hoặc hạn chế quyền truy cập theo chính sách.
- **Thu hồi thực tế hoàn tất:** các hệ thống liên quan xác nhận đã khóa, thu hồi hoặc xử lý đủ những đường truy cập thuộc phạm vi.

Ba mốc có thể khác nhau. Cần đo độ trễ từ **thời điểm đáng lẽ phải cắt quyền** đến khi **quyền thật sự bị cắt**, thay vì tính từ lúc một hệ thống gửi thông báo.

## 2. Vì sao Leaver phải bắt đầu từ sự kiện đáng tin cậy?

Không có tín hiệu Leaver chính xác, tài khoản có thể tồn tại rất lâu sau khi người dùng không còn làm việc. Ngược lại, tín hiệu sai có thể khiến người đang làm việc bị chặn đột ngột, gây gián đoạn hoạt động.

Các mục tiêu kiểm soát chính gồm:

| Mục tiêu | Nếu sự kiện bị thiếu hoặc sai | Kiểm soát cần thiết |
|---|---|---|
| **Đúng chủ thể** | Vô hiệu hóa nhầm người trùng họ tên, email cũ hoặc tài khoản tái sử dụng | Dùng định danh nội bộ bền vững và liên kết tài khoản đáng tin cậy |
| **Đúng quan hệ** | Nghỉ một hợp đồng nhưng bị cắt cả quan hệ hợp lệ khác | Phân biệt mã quan hệ, loại hợp đồng và phạm vi pháp nhân |
| **Đúng thời điểm** | Cắt quá sớm hoặc để quyền tiếp tục quá hạn | Có mốc hiệu lực rõ, múi giờ và chính sách khẩn cấp |
| **Đúng mức độ** | Chỉ khóa SSO nhưng vẫn còn tài khoản local, API token, VPN | Kiểm kê và kiểm tra từng đường truy cập |
| **Đúng trình tự** | Sự kiện cũ đến sau và tự kích hoạt lại người đã nghỉ | Version, idempotency, đối chiếu trạng thái nguồn hiện hành |
| **Có thể chứng minh** | Không biết hệ thống nào đã thu hồi hay còn lỗi | Log, kết quả từng connector, đối soát và chủ sở hữu ngoại lệ |
| **Đúng bảo mật dữ liệu** | Lộ lý do nghỉ việc hoặc dữ liệu nhạy cảm tới ứng dụng không cần biết | Tối thiểu hóa payload và phân quyền truy cập |

**Nguồn sự kiện phải được xác thực và có thẩm quyền.** Một email từ quản lý, một thay đổi lịch làm việc hay một ticket không xác minh không nên tự trở thành lệnh xóa danh tính trên toàn doanh nghiệp.

## 3. Nguồn phát sự kiện và phạm vi thẩm quyền

Nguồn có thẩm quyền (*authoritative source*) phụ thuộc loại chủ thể.

| Chủ thể | Nguồn có thể có thẩm quyền | Ví dụ sự kiện |
|---|---|---|
| Nhân viên chính thức | HRIS/hệ thống nhân sự được tổ chức công nhận | Chấm dứt hợp đồng lao động |
| Nhà thầu | Hệ thống hợp đồng hoặc quản lý nhà thầu | Hết hạn hợp đồng/đơn hàng |
| Đối tác | Hệ thống quản lý đối tác hoặc người bảo trợ được ủy quyền | Kết thúc hợp tác hoặc quyền bảo trợ |
| Nhân sự thời vụ | Hệ thống quản lý phân công và quan hệ làm việc | Kết thúc ca/đợt làm việc theo chính sách |
| Người dùng bên ngoài | Nguồn quản trị vòng đời khách hàng hoặc đối tượng truy cập | Chấm dứt tư cách tham gia dịch vụ |
| Service account/workload | Danh mục ứng dụng, vòng đời tài nguyên và owner kỹ thuật | Ngừng dịch vụ, thay owner, xóa môi trường |

Tổ chức cần xác định rõ **nguồn nào được phép phát tín hiệu chấm dứt cho từng loại quan hệ**. Có thể một người đồng thời là nhân viên và người dùng một dịch vụ khách hàng riêng: sự kiện nghỉ việc ở hệ thống HR **không mặc nhiên xóa mọi danh tính không cùng phạm vi**. Quyết định phụ thuộc quan hệ pháp lý, chính sách sử dụng dịch vụ và liên kết danh tính đã xác nhận.

### Kiểm tra trước khi chấp nhận

1. Nguồn phát có được xác thực qua API, chữ ký sự kiện, kênh nội bộ đáng tin hoặc phương thức tương đương không?
2. Nguồn có thẩm quyền đối với chủ thể và **quan hệ đang chấm dứt** không?
3. Định danh chủ thể có khớp bản ghi IAM gốc và quan hệ hiện hành không?
4. Có thể nhận biết sự kiện trùng, phiên bản cũ, sự kiện bị sửa hoặc bị hủy không?
5. Thời điểm hiệu lực và loại tình huống có đủ rõ để áp chính sách cắt quyền không?
6. Payload có tối thiểu hóa dữ liệu nhân sự nhạy cảm không?

Không dùng tên hiển thị hoặc email làm khóa liên kết duy nhất. Các thuộc tính này có thể thay đổi, bị trùng hoặc tái sử dụng, đặc biệt khi một người tái gia nhập.

## 4. Các loại sự kiện trong vòng đời nghỉ việc

Một quy trình Leaver hoàn chỉnh có thể cần nhiều sự kiện liên quan, không nên gom mọi thứ vào một nhãn “terminated”.

| Sự kiện nghiệp vụ | Ý nghĩa | Xử lý điển hình |
|---|---|---|
| **Termination scheduled** | Đã biết người sẽ rời đi ở thời điểm tương lai | Kiểm tra dữ liệu, lập lịch cắt quyền và bàn giao |
| **Termination effective** | Mốc chấm dứt theo chính sách đã đến | Thực thi chặn đăng nhập, thu hồi phiên/quyền |
| **Immediate termination** | Yêu cầu chấm dứt truy cập khẩn cấp | Ưu tiên cắt quyền ngay, sau đó xử lý các bước còn lại |
| **Contract expired** | Hợp đồng/ủy quyền hết hạn | Áp chính sách tự chấm dứt nếu không có gia hạn hợp lệ |
| **Termination date changed** | Ngày hoặc giờ nghỉ bị sửa | Hủy lịch cũ, cập nhật lịch mới; kiểm tra quyền đã thay đổi |
| **Termination canceled** | Quyết định nghỉ bị hủy trước khi có hiệu lực | Hủy tác vụ cắt quyền chưa thực thi; kiểm tra trạng thái nguồn |
| **Suspension** | Tạm đình chỉ truy cập, chưa kết thúc quan hệ | Tạm khóa theo chính sách, giữ thông tin cần phục hồi |
| **Rehire / new relationship** | Người cũ có quan hệ mới với tổ chức | Kiểm tra lại điều kiện Joiner; cấp quyền theo trạng thái mới |

**Suspension** cần được phân biệt với **Leaver**: nghỉ phép, khóa tạm do sự cố hoặc đình chỉ có thể cần ngăn truy cập nhưng không nhất thiết chấm dứt hoàn toàn danh tính. Việc *termination canceled* cũng không phải một lệnh tự động cấp lại mọi quyền đã mất; nếu cắt quyền đã thực thi, quá trình phục hồi phải được kiểm soát theo chính sách.

### Trường hợp thông báo sớm và cắt quyền sau

Sự kiện nghỉ trong tương lai có thể đến nhiều ngày trước ngày cuối cùng. IAM có thể dùng thời gian đó để kiểm kê quyền, xác định tài nguyên cần bàn giao, lên lịch và kiểm tra connector. **Không nên vô hiệu hóa ngay** nếu chính sách cho phép nhân sự tiếp tục làm việc đến mốc đã định. Ngược lại, nếu có yêu cầu chấm dứt khẩn cấp, không được chờ lịch cũ.

## 5. Dữ liệu tối thiểu của một Leaver event

Một sự kiện chất lượng tốt cần trả lời **ai, quan hệ nào, thay đổi gì, từ nguồn nào, hiệu lực lúc nào, và đây là phiên bản thứ mấy**. Ví dụ nội bộ sau **không phải schema chuẩn SCIM hoặc HRIS**:

~~~json
{
  "eventId": "hr-event-000824",
  "eventType": "TERMINATION_EFFECTIVE",
  "subjectId": "person-1042",
  "relationshipId": "employment-2024-1042",
  "source": "HRIS",
  "sourceRecordVersion": 32,
  "occurredAt": "2026-11-23T08:45:00+07:00",
  "effectiveAt": "2026-11-23T09:00:00+07:00",
  "receivedAt": "2026-11-23T08:45:03+07:00",
  "terminationMode": "STANDARD",
  "scope": {
    "organizationId": "org-vn",
    "relationshipType": "EMPLOYEE"
  },
  "correlationId": "iam-flow-65082"
}
~~~

Ý nghĩa các trường:

- **eventId:** nhận diện sự kiện để chống xử lý lặp, theo dõi khi replay và tương quan log.
- **subjectId:** khóa bền vững liên kết danh tính gốc trong IAM; không dùng tên/email thay thế.
- **relationshipId:** xác định **quan hệ cụ thể** đang chấm dứt; hữu ích khi một chủ thể có nhiều hợp đồng hoặc tư cách truy cập.
- **source:** hệ thống chịu trách nhiệm công bố trạng thái quan hệ.
- **sourceRecordVersion:** phiên bản đơn điệu trong phạm vi bản ghi nguồn, giúp tránh sự kiện cũ ghi đè sự kiện mới.
- **occurredAt:** thời gian nguồn ghi nhận sự kiện; khác thời gian có hiệu lực.
- **effectiveAt:** thời điểm chính sách yêu cầu cắt quyền.
- **receivedAt:** thời điểm IAM nhận được; hữu ích đo độ trễ truyền và xử lý.
- **terminationMode:** loại xử lý nghiệp vụ được phép, ví dụ theo lịch hay khẩn cấp. Không nên chứa lý do nhân sự bí mật.
- **scope:** phạm vi tổ chức/quan hệ; cần thống nhất với cách cấp quyền.
- **correlationId:** nối lệnh thu hồi, ticket, sự kiện IdP và kết quả ở ứng dụng đích.

**Không nên phát tán lý do nghỉ việc, thông tin kỷ luật, dữ liệu hợp đồng hoặc tài liệu cá nhân** tới mọi connector. Phần lớn hệ thống đích chỉ cần biết định danh tài khoản, hành động và thời điểm được phép.

### Ba mốc thời gian không thể thay thế nhau

Giả sử hợp đồng kết thúc lúc **17:00**, HRIS tạo sự kiện lúc **15:00**, IAM nhận lúc **15:01** và ứng dụng legacy xác nhận khóa lúc **17:08**. Nếu đánh giá SLA thu hồi, cần xác định **mốc phải cắt là 17:00** và có chậm **8 phút** tại ứng dụng legacy; không lấy 15:01 làm mốc bắt buộc hoàn thành trừ khi chính sách quy định khác.

Thời gian nên được lưu với **múi giờ hoặc dưới dạng instant chuẩn hóa**. “Ngày cuối cùng làm việc” không đủ rõ nếu không biết quyền dừng đầu ngày, cuối ngày hay một giờ cụ thể.

## 6. Từ sự kiện đến quyết định thu hồi

Leaver event là **đầu vào**, không phải toàn bộ quy trình. IAM hoặc hệ thống điều phối (*orchestrator*) cần đánh giá trạng thái nguồn và chính sách, sau đó phát hành **các lệnh kỹ thuật**.

~~~mermaid
flowchart TD
    H[HRIS / hợp đồng: Leaver event] --> V[Kiểm tra nguồn, định danh, quan hệ, phiên bản]
    V --> D{Sự kiện hợp lệ?}
    D -->|Không| E[Cách ly sự kiện, cảnh báo hoặc xác minh]
    D -->|Có| T{Đã đến thời điểm hiệu lực?}
    T -->|Chưa| S[Lập lịch, theo dõi thay đổi và chuẩn bị bàn giao]
    S --> T
    T -->|Rồi| O[IAM / IGA: chặn truy cập và điều phối]
    O --> I[IdP / Directory: vô hiệu hóa đăng nhập]
    O --> A[SCIM / API / thủ công: thu hồi account và quyền]
    O --> C[Phiên, refresh token, API key, SSH key, VPN, quyền đặc biệt]
    I --> R[Đối soát thực tế]
    A --> R
    C --> R
    R --> X{Đã đóng đủ phạm vi?}
    X -->|Chưa| F[Cảnh báo quyền tồn dư, ticket, retry và cô lập]
    F --> R
    X -->|Đạt| L[Chốt trạng thái, bằng chứng kiểm toán]
~~~

Quy trình có thể bất đồng bộ; một ứng dụng đích phản hồi muộn hoặc không có API cần xử lý thủ công. IAM nên theo dõi **trạng thái riêng của từng hệ thống**, không đánh dấu Leaver thành công toàn bộ chỉ vì một lệnh khóa IdP đã trả HTTP 200.

## 7. Sự kiện nghỉ việc theo lịch và nghỉ việc khẩn cấp

### 7.1. Theo lịch

Với một sự kiện có ngày hiệu lực trong tương lai, có thể chuẩn bị trước:

1. Xác minh nguồn, mã chủ thể, ngày hiệu lực và quan hệ cần kết thúc.
2. Kiểm kê danh mục tài khoản và quyền liên quan: IdP, thư mục, SSO, SaaS, cloud, VPN, PAM, Git, cơ sở dữ liệu, ứng dụng cũ, token và secret.
3. Liên hệ chủ dữ liệu/tài nguyên để bàn giao hợp lệ, xác định chuyển owner hay ngừng dịch vụ.
4. Đặt lịch thu hồi và cảnh báo thay đổi ngày nghỉ hoặc hủy quyết định.
5. Đến thời điểm hiệu lực, chặn các kênh truy cập theo chính sách và đối soát kết quả.
6. Thực hiện lưu giữ/xóa dữ liệu, kiểm toán và khóa các tài khoản phụ còn sót lại theo quy định.

Không nên dùng “đã có sự kiện nghỉ trong HRIS” để suy ra có thể tắt tài khoản ngay nếu người đó vẫn được phép làm việc trước mốc hiệu lực.

### 7.2. Khẩn cấp hoặc rủi ro cao

Với yêu cầu cắt quyền ngay do người có thẩm quyền kích hoạt, ưu tiên **đóng các đường truy cập rủi ro cao**: IdP, SSO mới, phiên, token, VPN, quyền PAM/admin, truy cập cloud và kết nối từ xa. Sau đó xử lý chi tiết bàn giao, dữ liệu, quyền thấp hơn, ticket legacy và lưu hồ sơ.

Trường hợp khẩn cấp cần đường xử lý có thẩm quyền rõ, xác thực yêu cầu, kiểm toán và cơ chế escalation. Một email giả mạo “sa thải nhân viên” không được tự kích hoạt quy trình khóa toàn tổ chức. Tuy nhiên, yêu cầu hợp lệ cần được thực hiện với tốc độ tương xứng rủi ro.

### 7.3. Chấm dứt và tạm đình chỉ

**Tạm đình chỉ** có thể là hành động bảo vệ trước khi có quyết định nghỉ việc. Trong mô hình dữ liệu, nên có trạng thái riêng để không làm mất khả năng khôi phục hợp lệ. Khi chuyển từ suspension sang Leaver, cần thu hồi các đường truy cập chưa bị khóa và chốt hồ sơ theo chính sách; không coi “đã suspended” là đủ bằng chứng Leaver hoàn tất.

## 8. Chống xử lý trùng, sai thứ tự và sự kiện đến muộn

Sự kiện từ HRIS, hàng đợi, webhook hoặc API thường được truyền theo kiểu **at-least-once**: một sự kiện có thể xuất hiện nhiều lần. Sự kiện cũng có thể đến trễ hoặc không đúng thứ tự.

### Các tình huống cần xử lý

| Tình huống | Cách tránh sai |
|---|---|
| Cùng eventId đến hai lần | Idempotency theo ID và trạng thái xử lý đã lưu |
| Scheduled event được sửa ngày | So sánh version và hủy/thay lịch cũ |
| Mover đến sau Leaver nhưng được tạo trước | Đối chiếu phiên bản và trạng thái nguồn hiện hành; không mở lại quyền |
| Leaver bị hủy trước effectiveAt | Thu hồi tác vụ scheduled và ghi nhận quyết định mới |
| Leaver bị hủy sau khi đã khóa | Cần quy trình phục hồi có xác minh; không tự cấp lại tất cả quyền |
| Event đến sau effectiveAt | Ưu tiên cắt ngay theo chính sách, ghi thời gian trễ và điều tra nếu cần |
| Sự kiện không rõ chủ thể | Cách ly để đối chiếu; không đoán bằng tên/email |
| Sự kiện có version thấp hơn trạng thái đã áp dụng | Không ghi đè trạng thái mới hơn, vẫn log để kiểm tra |
| Sự kiện tái gia nhập mới sau Leaver | Xác lập quan hệ mới, áp chính sách Joiner thay vì phục hồi quyền cũ |

### Giả mã xử lý một sự kiện

~~~text
function handleLeaverEvent(event):
    verifySourceSignatureAndAuthority(event)
    validateSchemaAndRequiredFields(event)

    if alreadyHandled(event.eventId):
        return ALREADY_PROCESSED

    identity = findByImmutableSubjectId(event.subjectId)
    relationship = findExactRelationship(identity, event.relationshipId)

    if identity is missing or relationship is missing:
        quarantine(event)
        return NEEDS_RECONCILIATION

    sourceState = readCurrentAuthoritativeRelationship(relationship)

    if event.sourceRecordVersion < sourceState.version:
        recordAsStale(event)
        return STALE_EVENT

    if sourceState.isActive and event.eventType == TERMINATION_EFFECTIVE:
        investigateSourceConflict(event, sourceState)
        return CONFLICT

    if event.eventType == TERMINATION_SCHEDULED:
        upsertTerminationSchedule(relationship, sourceState)
    else if event.eventType == TERMINATION_CANCELED:
        cancelPendingTerminationSchedule(relationship, sourceState)
    else if isTerminationDue(sourceState, currentTime()):
        startOrResumeDeprovisioning(relationship, sourceState)

    recordEventHandled(event.eventId)
    return ACCEPTED
~~~

Đây là **giả mã mô tả ý tưởng**; không đủ để triển khai như code bảo mật thực tế. Hệ thống thật cần giao dịch/khóa đồng thời, kiểm soát quyền, retry, nhật ký bất biến theo chính sách và quyết định rõ khi nguồn không khả dụng. Với sự kiện khẩn cấp đáng tin cậy, chính sách có thể yêu cầu **chặn trước rồi xác minh trạng thái sâu hơn**, không để mọi lần truy vấn HRIS lỗi làm trì hoãn chặn rủi ro cao.

**Idempotency** không chỉ là bỏ qua lần xử lý trùng ở đầu workflow. Mỗi hành động tại connector cũng cần an toàn khi được chạy lại, tránh cấp lại quyền hoặc xử lý nhầm đối tượng nếu job retry sau mất kết nối.

## 9. Event time, processing time và các mốc SLA

Trong hệ thống phân tán, cần tách:

- **Effective time:** thời điểm nghiệp vụ quy định quyền phải thay đổi.
- **Event creation time:** thời điểm nguồn phát biểu thay đổi.
- **Ingestion time:** thời điểm bộ điều phối nhận.
- **Dispatch time:** thời điểm yêu cầu thu hồi được phát sang IdP/connector.
- **Acknowledgment time:** thời điểm hệ thống đích xác nhận nhận lệnh.
- **Verification time:** thời điểm đối soát xác nhận quyền thực tế đã bị thu hồi.

Bảng minh họa:

| Mốc | Thời gian giả định | Ý nghĩa |
|---|---|---|
| HR xác nhận | 15:30 | Quyết định được nhập vào nguồn |
| IAM nhận | 15:30:05 | Hệ thống đã nhận event |
| EffectiveAt | 17:00 | Mốc quyền cần bị cắt |
| IdP disabled | 17:00:04 | Đăng nhập trung tâm bị khóa |
| SaaS SCIM acknowledged | 17:00:06 | Lệnh đã được ứng dụng chấp nhận |
| SaaS actual status confirmed | 17:01:20 | Đã xác minh account ở SaaS bị vô hiệu |
| Legacy app confirmed | 17:12 | App cũ được kiểm tra thủ công |

Thời gian hoàn tất theo scope phụ thuộc mốc **đã xác minh** của hệ thống cuối cùng; không nên tính chỉ dựa trên lúc dispatcher gửi lệnh. Những ngưỡng SLA/SLO cụ thể phải được tổ chức xác lập dựa theo rủi ro và yêu cầu vận hành.

### Khi HR cập nhật quá muộn

Giả sử nguồn nhân sự báo Leaver lúc 10:00 nhưng effectiveAt là 09:00. Không thể quay ngược thời gian để “thu hồi đúng 09:00”; cần khóa ngay các đường truy cập còn hiệu lực theo chính sách, ghi lại **thời gian chậm 60 phút hoặc hơn** và điều tra nguyên nhân đến muộn. Dữ liệu kiểm toán phải giữ nguyên mốc thực tế, không sửa mốc cắt quyền cho đẹp số liệu.

## 10. Leaver event đi qua IdP, SSO và SCIM như thế nào?

### IdP và SSO

**Identity Provider (IdP)** thường quản lý trạng thái đăng nhập trung tâm và các phương thức xác thực. Khi Leaver có hiệu lực, IAM có thể vô hiệu hóa đối tượng đăng nhập trong IdP, hạn chế phiên mới và kích hoạt thao tác thu hồi phiên/token theo năng lực của nền tảng.

Tuy nhiên, **Single Sign-On (SSO)** không đồng nghĩa mọi ứng dụng đã bị chặn. Một ứng dụng có thể còn:

- Phiên đăng nhập local đã được tạo trước đó.
- Refresh token hoặc API token riêng.
- Tài khoản độc lập không dùng SSO.
- Credential thiết bị, SSH key, khóa cloud hoặc certificate.
- Quyền đặc quyền qua nhóm, vai trò hoặc tài khoản chia sẻ.

Vì thế, kết quả **IdP disabled = true** chỉ là **một bằng chứng**, không phải kết luận Leaver hoàn tất.

### SCIM và connector

**SCIM** hỗ trợ đồng bộ người dùng/nhóm tới dịch vụ đích theo khả năng tích hợp. Một hành động phổ biến là cập nhật trạng thái người dùng, ví dụ đánh dấu inactive nếu dịch vụ hỗ trợ đúng thuộc tính. Các connector khác dùng API riêng, directory sync, ticket hoặc quy trình thủ công.

Trước khi ghi trạng thái hoàn tất, phải xác nhận **ngữ nghĩa của hệ thống đích**: lệnh vô hiệu hóa có cắt phiên ngay không, có còn API key không, các quyền trực tiếp có bị thu hồi không và cơ chế xóa tài khoản có ảnh hưởng dữ liệu cần giữ không.

Không tự động xóa tài khoản/nhóm trên mọi dịch vụ chỉ vì một sự kiện Leaver. Quy trình phù hợp có thể là **vô hiệu hóa trước, chuyển giao dữ liệu, lưu giữ theo chính sách và xóa khi đến hạn**.

### RBAC/ABAC và quyền tồn dư

- **RBAC:** xóa thành viên nhóm/role gắn với quan hệ chấm dứt; rà soát quyền cấp trực tiếp và quyền ngoại lệ.
- **ABAC:** thuộc tính lifecycle như trạng thái employment/contract phải được cập nhật từ nguồn có thẩm quyền và được policy engine dùng đúng lúc.
- **PAM:** thu hồi phiên đặc quyền, quyền nâng cao theo thời hạn, chứng thực quản trị và đường truy cập khẩn cấp có liên quan.
- **Tài khoản dịch vụ:** cần tách chủ thể máy khỏi owner nhân sự; chuyển owner, rà soát quyền và thay bí mật mà người rời đi có thể biết.

## 11. Điều gì phải được thu hồi khi sự kiện có hiệu lực?

Danh mục kiểm soát cần theo dõi phạm vi thực tế, không chỉ số lượng tài khoản:

| Lớp truy cập | Hành động phù hợp | Bằng chứng cần kiểm tra |
|---|---|---|
| IdP/directory | Vô hiệu hóa đăng nhập, nhóm/role, cơ chế khôi phục không còn hợp lệ | Trạng thái tài khoản và chính sách tại IdP |
| Ứng dụng SSO | Ngăn đăng nhập mới; xử lý session local nếu được hỗ trợ | Trạng thái phiên/account ở ứng dụng |
| SaaS qua SCIM/API | Deactivate account, thu hồi nhóm/quyền/credential riêng | Readback đối tượng và quyền thực tế |
| VPN, Wi-Fi, NAC | Thu hồi tài khoản, thiết bị, chứng chỉ hoặc chính sách kết nối liên quan | Kết nối đang hoạt động và khả năng xác thực lại |
| Cloud và quyền quản trị | Thu hồi IAM roles, access keys, phiên đặc quyền | Quyền và credential tại cloud/PAM |
| Git/DevOps | Thu hồi PAT, SSH keys, deploy credentials cá nhân | Danh sách token/keys và quyền dự án |
| Cơ sở dữ liệu/ứng dụng legacy | Khóa local user, direct grants, service access không hợp lệ | Tài khoản và grants tại đích |
| Bí mật chia sẻ | Luân chuyển secret mà người rời đi có thể biết | Version mới và hệ thống dùng đã cập nhật |
| Thiết bị đầu cuối | Thu hồi thiết bị, xóa token/phiên local, bàn giao đúng chính sách | Biên bản tài sản, tình trạng MDM/EDR |
| Dữ liệu và tài nguyên sở hữu | Chuyển owner của repo, mailbox, tác vụ, lịch, hệ thống tích hợp | Người sở hữu hợp lệ sau bàn giao |

Nếu một credential không thể thu hồi ngay, hệ thống cần đánh giá **biện pháp bù trừ**: cô lập mạng, chặn tại gateway, thay secret, vô hiệu hóa API endpoint hoặc giám sát tăng cường. Các biện pháp này phải được ghi nhận là kiểm soát tạm thời theo thẩm quyền, không coi là thu hồi hoàn tất khi chưa xác minh.

## 12. Xử lý các quan hệ đặc biệt và tình huống biên

### 12.1. Nhà thầu hết hạn nhưng không có HR termination

Đối tượng nhà thầu có thể không nằm trong quy trình nhân viên chính thức. Contract management cần phát sự kiện **expiration** hoặc hệ thống IAM tự áp thời hạn được chấp thuận. Nếu cần gia hạn, phải có một trạng thái/phiên bản hợp lệ trước hạn; không kéo dài quyền vô thời hạn chỉ vì không nhận được sự kiện mới.

### 12.2. Một người có hai quan hệ hợp lệ

Một chuyên gia có thể đồng thời là nhà thầu ở dự án A và cố vấn ở dự án B. Khi hợp đồng A kết thúc, IAM cần thu hồi quyền gắn với quan hệ A, đánh giá liệu danh tính đăng nhập chung còn được phép sử dụng cho B và không phá hỏng công việc hợp lệ. **relationshipId** và dấu vết nguồn cấp quyền là cơ sở phân định phạm vi.

### 12.3. Đang nghỉ tạm thời

Nghỉ phép dài ngày, đình chỉ hoặc tạm ngừng tham gia dự án không tự đồng nghĩa Leaver. Có thể cần trạng thái **suspended** và chính sách đăng nhập hạn chế. Nếu về sau có quyết định nghỉ thực sự, luồng Leaver phải chấm dứt những quyền và credential chưa được xử lý.

### 12.4. Sửa hoặc hủy quyết định nghỉ

Nếu nguồn HR sửa thời điểm **trước khi sự kiện có hiệu lực**, bộ điều phối cập nhật lịch và giải quyết các thông báo đã gửi. Nếu quyết định được hủy **sau khi đã chặn tài khoản**, không nên tự cấp lại mọi nhóm/role. Cần xác minh nguồn, quyết định khôi phục, so sánh quyền hiện hành và phê duyệt khi cần.

### 12.5. Rehire sau Leaver

Tái gia nhập là **một quan hệ mới cần đánh giá theo quy trình Joiner**, kể cả khi có thể tái sử dụng khóa danh tính gốc để giữ lịch sử. Các quyền từ công việc cũ, access token cũ và invitation cũ không được tự động hồi sinh.

### 12.6. Service account do người nghỉ sở hữu

Một người nghỉ việc có thể là chủ kỹ thuật của bot hoặc service account được nhiều hệ thống dùng. Xóa trực tiếp tất cả service account có owner là người nghỉ có thể gây sự cố. Cần **chuyển owner, rà soát phạm vi, luân chuyển secret, xử lý personal token** và chỉ chấm dứt workload nếu không còn nhu cầu.

### 12.7. Người dùng bị mất tích hoặc nguồn nhân sự thiếu thông tin

Khi tổ chức chưa có xác nhận Leaver, IAM có thể sử dụng cơ chế hạn sử dụng, access review, không hoạt động kéo dài hoặc cảnh báo để phát hiện rủi ro; **không tự biến mọi tín hiệu inactivity thành termination**. Cần chuyển tới nguồn có thẩm quyền để làm rõ.

## 13. Trạng thái của quy trình Leaver và tiêu chí hoàn tất

Nên tách trạng thái *sự kiện được chấp nhận* khỏi *workflow thu hồi*.

~~~mermaid
stateDiagram-v2
    [*] --> Scheduled: Sự kiện nghỉ hợp lệ trong tương lai
    Scheduled --> Scheduled: Sửa ngày / cập nhật nguồn
    Scheduled --> Canceled: Quyết định bị hủy trước hiệu lực
    Scheduled --> Terminating: Đến effectiveAt
    [*] --> Terminating: Leaver khẩn cấp có thẩm quyền
    Terminating --> PartiallyClosed: Có hệ thống chưa xác minh xong
    PartiallyClosed --> Terminating: Retry / xử lý ngoại lệ
    Terminating --> VerifiedClosed: Tất cả đường truy cập trong scope đã xác minh
    PartiallyClosed --> VerifiedClosed: Đóng các sai lệch còn lại
    Canceled --> [*]
    VerifiedClosed --> [*]
~~~

**Một Leaver “đã thực thi” và “đã được xác minh hoàn tất” là hai trạng thái khác nhau.** Ví dụ khóa IdP thành công nhưng ứng dụng CRM legacy chưa có bằng chứng thu hồi thì workflow còn **PartiallyClosed** và phải có owner, deadline, escalation.

### Quy tắc xác nhận hoàn tất

Có thể xem xét đóng workflow khi:

1. Đúng chủ thể và quan hệ đã được xác nhận theo nguồn có thẩm quyền.
2. Thời điểm thu hồi và phạm vi hệ thống đích được ghi rõ.
3. Các đường truy cập thuộc phạm vi đã được vô hiệu hóa/thu hồi đúng chính sách hoặc có quyết định ngoại lệ được phê duyệt với trạng thái riêng, không ngụy tạo PASS.
4. Đã đối soát tài khoản, nhóm, phiên/token, quyền trực tiếp, credential máy và tài sản liên quan theo rủi ro.
5. Các ticket và bằng chứng kiểm toán có trạng thái rõ ràng; các phần chưa hoàn tất vẫn hiển thị và được theo dõi.

Một tổ chức có thể phân biệt **“đã khóa các đường truy cập trọng yếu”** với **“đã hoàn tất toàn bộ offboarding”**. Hai mốc này đều hữu ích nhưng không nên gộp thành một nhãn mơ hồ.

## 14. Kiểm toán sự kiện nghỉ việc

Nhật ký cần cho phép trả lời: **Ai phát quyết định? IAM nhận và tin quyết định đó vì sao? Khi nào quyền phải bị cắt? Hệ thống nào đã cắt lúc nào? Còn đường truy cập nào chưa đóng?**

| Nhóm bằng chứng | Thông tin nên có |
|---|---|
| **Nguồn sự kiện** | source, eventId, subjectId, relationshipId, version, loại và thời điểm hiệu lực |
| **Kiểm tra thẩm quyền** | Quy tắc xác minh nguồn, kết quả kiểm tra, phiên bản chính sách |
| **Điều phối** | Workflow ID, trạng thái và quyết định lịch/khẩn cấp/hủy |
| **Lệnh thực thi** | Connector, tài khoản đích, hành động, timestamp, kết quả API/ticket |
| **Đối soát** | Quyền trước/sau, trạng thái thực tế, timestamp xác minh, sai lệch |
| **Ngoại lệ** | Lý do kỹ thuật, rủi ro, chủ xử lý, biện pháp bù trừ, hạn giải quyết |
| **Bàn giao** | Quyền sở hữu tài nguyên, tài khoản dịch vụ, dữ liệu và thiết bị liên quan |

Tránh đưa lý do nghỉ việc nhạy cảm hoặc dữ liệu nhân sự vượt nhu cầu vào log/SIEM. Dữ liệu nghiệp vụ cần được bảo vệ theo quyền truy cập và thời hạn lưu giữ hợp lệ. Nếu có yêu cầu lưu giữ phục vụ kiểm toán hoặc tố tụng, xử lý riêng theo chính sách; **vô hiệu hóa quyền truy cập không đồng nghĩa xóa toàn bộ dữ liệu**.

## 15. Chỉ số vận hành cần theo dõi

| Chỉ số | Định nghĩa | Ý nghĩa |
|---|---|---|
| **Event-to-ingestion latency** | Thời gian từ lúc nguồn phát đến khi IAM nhận | Đánh giá kênh truyền sự kiện |
| **Effective-to-block latency** | Thời gian từ mốc phải cắt quyền đến khi đường truy cập trọng yếu được chặn | Đo rủi ro cắt quyền chậm |
| **End-to-end closure time** | Thời gian từ effectiveAt đến đối soát xong các hệ thống thuộc scope | Đánh giá hoàn tất thu hồi |
| **Stale event rate** | Số sự kiện phiên bản cũ, trễ hoặc sai trình tự | Phát hiện lỗi đồng bộ |
| **Duplicate event count** | Số sự kiện lặp được xử lý an toàn | Kiểm chứng idempotency |
| **Orphan account count** | Số tài khoản không còn liên kết quan hệ/owner hợp lệ | Phát hiện tài khoản mồ côi |
| **Residual entitlements** | Số quyền thực tế không còn được phép sau Leaver | Đo rủi ro quyền tồn dư |
| **Unresolved deprovision failures** | Số connector/ticket chưa thu hồi thành công | Ưu tiên xử lý lỗi và escalation |

Không đánh đồng **đã gửi yêu cầu** với **đã thực thi** hoặc **đã kiểm chứng**. Nếu ứng dụng chỉ trả acknowledgment mà không có readback, báo cáo cần nêu rõ mức bằng chứng và phương pháp bổ sung để xác nhận.

## 16. Tình huống minh họa xuyên suốt

Giả sử **Minh**, mã danh tính **person-1042**, là nhân viên trong tổ chức; Minh sử dụng IdP chung, CRM, Git, cloud và VPN. HRIS ghi nhận nghỉ theo lịch.

**Bước 1 — Ngày 25/11:** HRIS phát sự kiện **Termination scheduled** với effectiveAt là **30/11 lúc 17:00 (GMT+7)**. IAM xác minh nguồn và relationshipId, phát hiện không có quan hệ khác cần giữ đăng nhập công việc, tạo lịch và liệt kê hệ thống. Chủ dự án được thông báo cần bàn giao repository; người quản lý account tích hợp được yêu cầu chuyển owner trước ngày kết thúc.

**Bước 2 — Ngày 29/11:** HRIS sửa ngày nghỉ thành **01/12 lúc 17:00** với version mới. IAM đối chiếu bản ghi nguồn, hủy lịch cũ và lập lịch mới. Một queue chứa sự kiện cũ không được phép vô hiệu hóa tài khoản lúc 30/11 do hệ thống kiểm tra version/trạng thái hiện hành khi xử lý.

**Bước 3 — Ngày 01/12 lúc 17:00:** IAM bắt đầu Leaver: IdP bị vô hiệu hóa, quyền VPN và PAM được chặn, connector SCIM gửi lệnh deactivation đến CRM, ứng dụng Git thu hồi các token cá nhân. IAM đồng thời xử lý phiên đang tồn tại theo khả năng nền tảng và thu hồi secret mà Minh có thể đã biết.

**Bước 4 — Ngày 01/12 lúc 17:03:** IdP, VPN và Git xác nhận trạng thái thực tế, nhưng ứng dụng CRM legacy báo lỗi. Workflow ở trạng thái **PartiallyClosed**; một ticket được gán owner, có biện pháp hạn chế truy cập và theo dõi xử lý. Không gửi báo cáo “Leaver hoàn tất toàn bộ” chỉ vì đăng nhập IdP đã bị chặn.

**Bước 5 — Ngày 01/12 lúc 17:14:** Quản trị CRM xác minh tài khoản bị khóa và quyền trực tiếp đã được thu hồi. IAM đối soát lần cuối toàn bộ scope, ghi timestamp thật của mỗi hệ thống và đóng workflow theo chính sách. Dữ liệu của Minh được xử lý theo quy định lưu giữ, không tự xóa tất cả trong lúc cắt quyền.

**Bước 6 — Ba tháng sau:** Minh được tuyển lại. HRIS phát một quan hệ Joiner mới. IAM dùng danh tính gốc để giữ lịch sử nhưng **không phục hồi quyền CRM/Git cũ**; quyền mới được tính theo vai trò hiện tại và phê duyệt mới.

Tình huống này cho thấy **sự kiện nghỉ việc đáng tin cậy** chỉ là điểm bắt đầu. Chất lượng Leaver được đo bằng **thời điểm cắt quyền, trạng thái thực tế và khả năng phát hiện quyền tồn dư**.

## 17. Checklist thiết kế luồng sự kiện nghỉ việc

1. **Nguồn:** đã xác định nguồn có thẩm quyền cho nhân viên, nhà thầu, đối tác và chủ thể phi con người chưa?
2. **Danh tính:** có subjectId bền vững và relationshipId để tránh chặn nhầm người hoặc sai quan hệ không?
3. **Ngữ nghĩa:** có phân biệt nghỉ theo lịch, khẩn cấp, hết hạn, sửa ngày, hủy nghỉ và tạm đình chỉ không?
4. **Thời gian:** effectiveAt có đủ giờ/múi giờ và chính sách chặn tương ứng không? Có đo độ trễ thực tế không?
5. **Độ tin cậy:** hệ thống xử lý lặp, sự kiện cũ, trễ, đảo thứ tự, retry và bất đồng bộ an toàn không?
6. **Phạm vi:** có kiểm kê IdP/SSO, SCIM, ứng dụng local, cloud, VPN, PAM, Git, credential và token không?
7. **Quyết định quyền:** RBAC/ABAC và thuộc tính quan hệ đã được cập nhật đúng thời điểm chưa?
8. **Phi con người:** bot/service account liên quan có chủ sở hữu mới, phạm vi đúng và secret được xoay vòng khi cần không?
9. **Bằng chứng:** mỗi connector có kết quả xác nhận/trạng thái thực tế, thay vì chỉ lệnh gửi thành công không?
10. **Ngoại lệ:** lỗi thu hồi có owner, deadline, biện pháp bù trừ và cơ chế escalation không?
11. **Bảo mật dữ liệu:** payload và log có tối thiểu hóa thông tin nhân sự, bảo đảm lưu giữ và phân quyền không?
12. **Đóng vòng đời:** có tiêu chí rõ để phân biệt chặn truy cập trọng yếu và offboarding hoàn tất không?

### Ghi nhớ

**Sự kiện nghỉ việc là tín hiệu nghiệp vụ có thẩm quyền kích hoạt việc thay đổi quyền trong Leaver lifecycle.** Thiết kế đúng phải xác định chính xác chủ thể, quan hệ, thời điểm có hiệu lực, loại sự kiện và phiên bản nguồn; xử lý sự kiện trùng/trễ/đảo thứ tự; điều phối thu hồi ở IdP, SSO, SCIM và mọi hệ thống liên quan; cuối cùng **đối soát trạng thái quyền thực tế**. Đó là nền tảng để giảm quyền truy cập tồn dư, xử lý an toàn thay đổi trong JML và chứng minh việc chấm dứt quyền theo chính sách.
