# Chính sách giữ dữ liệu, sao lưu và xóa theo yêu cầu dịch vụ

Khi nền tảng yêu cầu thu hồi một service instance, service broker phải xử lý cả tài nguyên hạ tầng lẫn dữ liệu mà tài nguyên đó chứa. Xóa một database, cache hoặc object storage không đơn giản là gọi API delete của nhà cung cấp rồi đánh dấu instance đã hoàn tất. Broker cần biết dữ liệu nào phải xóa, dữ liệu nào được giữ theo hợp đồng, có cần sao lưu trước khi xóa hay không, bản sao lưu tồn tại trong bao lâu và làm thế nào để chứng minh yêu cầu xóa đã được thực hiện.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, chính sách giữ dữ liệu và xóa dữ liệu là một phần của vòng đời dịch vụ theo Open Service Broker API (OSB API). Chính sách cần được xác định theo service, plan, tenant và nghĩa vụ áp dụng; được thực thi nhất quán trong thao tác deprovision; đồng thời có thể kiểm tra, truy vết và phục hồi khi nhà cung cấp xử lý bất đồng bộ.

Bài học này trình bày cách xây dựng chính sách retention, backup và deletion; thiết kế quy trình thu hồi; xử lý bản sao lưu, replica, secret và metadata; cùng các nguyên tắc triển khai trong Spring Cloud Open Service Broker.

## 1. Deprovision là kết thúc vòng đời tài nguyên

Trong OSB API, nền tảng yêu cầu broker thu hồi một service instance thông qua thao tác deprovision. Với API v2, endpoint có dạng:

~~~http
DELETE /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}&accepts_incomplete=true
~~~

Nền tảng gửi định danh instance cùng thông tin service và plan theo hợp đồng. Broker tìm trạng thái instance, kiểm tra điều kiện thu hồi và điều phối việc xóa tài nguyên ở nhà cung cấp.

Một quy trình deprovision có thể bao gồm:

1. Xác nhận instance tồn tại và thuộc service, plan tương ứng.
2. Kiểm tra trạng thái hiện tại và các operation đang chạy.
3. Xác nhận các binding đã được xử lý theo quy trình của nền tảng và broker.
4. Đánh giá chính sách backup, retention, legal hold và yêu cầu xóa.
5. Thu hồi credentials, quyền truy cập và các tài nguyên phụ.
6. Xóa hoặc lên lịch xóa tài nguyên chính tại provider.
7. Xử lý snapshot, replica, backup và dữ liệu dẫn xuất theo chính sách.
8. Xác nhận kết quả, lưu bằng chứng vận hành và cập nhật trạng thái instance.

Deprovision không đồng nghĩa với việc chỉ xóa một bản ghi trong database của broker. Broker phải điều phối tài nguyên thực tế và theo dõi kết quả cho đến khi đạt trạng thái mà hợp đồng dịch vụ cam kết.

### Phân biệt unbind và deprovision

Unbind thu hồi một binding cụ thể, thường bao gồm user, credential, role hoặc quyền truy cập được cấp cho một ứng dụng. Deprovision thu hồi service instance và tài nguyên do instance đó quản lý.

Hai thao tác có liên quan nhưng khác phạm vi:

| Thao tác | Phạm vi | Ví dụ |
|---|---|---|
| Unbind | Một consumer/binding | Thu hồi user ứng dụng và credential của nó |
| Deprovision | Toàn bộ service instance | Xóa database và tài nguyên liên quan |
| Retention | Dữ liệu được giữ theo thời hạn/chính sách | Giữ snapshot mã hóa trong 7 ngày nếu hợp đồng cho phép |
| Purge | Xóa dữ liệu khỏi các nơi lưu giữ được quản lý | Xóa snapshot, replica và bản sao tạm theo lịch |

Nền tảng thường thực hiện unbind trước deprovision. Broker vẫn cần kiểm tra trạng thái binding trong kho dữ liệu của mình để tránh xóa instance khi còn quyền truy cập chưa được thu hồi. Chi tiết hành vi và mã lỗi phải tuân theo phiên bản OSB API cùng nền tảng tích hợp thực tế.

## 2. Xây dựng chính sách dữ liệu theo service và plan

Không nên áp dụng một chính sách retention giống nhau cho mọi dịch vụ. Database giao dịch, cache tạm thời, object storage và message broker có đặc tính dữ liệu khác nhau.

Một chính sách cần trả lời rõ:

- Dữ liệu nào thuộc service instance?
- Khi deprovision, dữ liệu được xóa ngay, giữ trong một khoảng thời gian hay sao lưu trước?
- Backup có được tạo tự động hay chỉ khi người dùng yêu cầu?
- Backup được mã hóa bằng khóa nào và ai có quyền khôi phục?
- Thời hạn lưu backup và thời điểm purge là bao lâu?
- Có ngoại lệ do legal hold, điều tra sự cố hoặc nghĩa vụ lưu trữ không?
- Sau khi xóa, dữ liệu còn tồn tại trong replica, log, cache, export hoặc backup nào?
- Người dùng có thể yêu cầu xóa sớm hoặc tải bản sao trước khi thu hồi không?

Một policy nội bộ có thể mô tả như sau:

~~~yaml
retention:
  policy-id: postgres-standard-v2
  on-deprovision:
    backup-before-delete: true
    backup-required: false
    backup-retention-days: 7
    delete-primary-resource: true
    delete-replicas: true
    purge-temporary-exports: true
    revoke-bindings: true
    legal-hold-supported: true
  backup:
    encryption-required: true
    customer-managed-key: optional
    restore-after-deprovision: restricted
~~~

Đây là cấu hình minh họa cho ứng dụng broker, không phải schema chuẩn của OSB API. Tên trường, thời hạn và hành vi phải được điều chỉnh theo hợp đồng dịch vụ, chính sách tổ chức, nhà cung cấp và nghĩa vụ pháp lý áp dụng.

### Chính sách phải minh bạch với người sử dụng

Nếu plan giữ backup trong 7 ngày sau khi thu hồi, thông tin này cần được công bố trong tài liệu dịch vụ hoặc giao diện quản trị phù hợp. Người dùng cần biết:

- Backup có được tạo hay không.
- Backup giữ trong bao lâu.
- Có phát sinh chi phí lưu trữ không.
- Ai được phép yêu cầu restore.
- Khi nào dữ liệu được purge vĩnh viễn theo khả năng của provider.
- Dữ liệu nào có thể được giữ lại vì nghĩa vụ pháp lý hoặc vận hành.

Không nên âm thầm giữ bản sao dữ liệu vô thời hạn sau deprovision. Nếu có retention, cần có mục đích, thời hạn, quyền truy cập và cơ chế purge rõ ràng.

## 3. Phân loại dữ liệu trước khi xóa

Một service instance thường có nhiều loại dữ liệu nằm ở các hệ thống khác nhau. Muốn xóa đúng, broker cần lập danh mục dữ liệu và xác định nguồn chịu trách nhiệm.

| Nhóm dữ liệu | Ví dụ | Cách xử lý cần xem xét |
|---|---|---|
| Dữ liệu chính | Database rows, object, message | Xóa hoặc giữ theo policy đã công bố |
| Tài nguyên phụ | Volume, replica, shard, queue | Xóa cùng instance hoặc theo quy trình riêng |
| Binding và secret | Username, password, token, certificate | Thu hồi quyền và xóa secret theo policy |
| Backup và snapshot | Database dump, volume snapshot | Giữ theo retention hoặc purge |
| Dữ liệu tạm | Export, staging file, temporary volume | Xóa sau khi thao tác hoàn tất hoặc hết TTL |
| Metadata broker | Instance ID, plan, provider resource ID, operation | Giữ tối thiểu để audit và đối soát |
| Log và audit | Event, access log, operation history | Áp dụng retention riêng, tránh lưu payload nhạy cảm |
| Dữ liệu dẫn xuất | Cache, search index, analytics copy | Xác định chủ sở hữu và gửi yêu cầu xóa phù hợp |

Không phải tất cả dữ liệu trong bảng đều do broker trực tiếp lưu. Broker cần biết hệ thống nào sở hữu từng loại dữ liệu và adapter nào chịu trách nhiệm yêu cầu xóa.

### Tách dữ liệu nghiệp vụ khỏi metadata vận hành

Sau khi xóa database, broker có thể vẫn cần giữ một tombstone hoặc bản ghi tối thiểu để:

- Nhận diện request deprovision được gửi lại.
- Tránh tạo lại tài nguyên khi xử lý retry cũ.
- Đối soát với provider khi kết quả xóa chưa rõ.
- Chứng minh operation đã hoàn tất.
- Phục vụ audit theo thời hạn được phép.

Tombstone không nên chứa dữ liệu nghiệp vụ hoặc credentials. Chỉ lưu các định danh, trạng thái, fingerprint, thời điểm và tham chiếu cần thiết theo chính sách retention của metadata.

## 4. Backup trước khi deprovision

Backup trước khi xóa có thể giúp khôi phục khi người dùng thu hồi nhầm hoặc cần di chuyển dữ liệu. Tuy nhiên, không phải mọi dịch vụ đều nên tự động backup trước khi deprovision.

Một số trường hợp backup có ích:

- Database lưu dữ liệu quan trọng và plan có chính sách recovery window.
- Người dùng đã đăng ký yêu cầu export trước khi thu hồi.
- Quy trình chuyển đổi nhà cung cấp cần snapshot nhất quán.
- Hợp đồng dịch vụ yêu cầu lưu bản sao trong một thời hạn cụ thể.

Một số trường hợp không nên tự động tạo backup:

- Cache hoặc dữ liệu tạm có thể tái tạo.
- Người dùng yêu cầu xóa dữ liệu ngay và không có nghĩa vụ giữ bản sao.
- Backup sẽ tạo bản sao dữ liệu nhạy cảm vượt phạm vi cho phép.
- Nhà cung cấp không hỗ trợ snapshot nhất quán hoặc không thể bảo vệ bản sao phù hợp.

Chính sách nên phân biệt **backup-before-delete** với **backup-required**. Một policy có thể cho phép tạo backup nếu người dùng chọn, nhưng không bắt buộc. Nếu backup là bắt buộc, deprovision chỉ được tiếp tục sau khi backup hoàn tất và được xác minh, trừ khi có quy trình ngoại lệ được phê duyệt.

### Backup cần có tính nhất quán

Với database, snapshot ở cấp volume chưa chắc tạo ra backup nhất quán về mặt ứng dụng. Có thể cần checkpoint, flush, transaction log hoặc cơ chế snapshot do database/provider hỗ trợ.

Với object storage, cần xác định tập object, version, multipart upload và metadata cần sao lưu.

Với message broker, cần cân nhắc queue, topic, offset, consumer state và retention của message. Sao lưu cấu hình broker không đồng nghĩa đã sao lưu toàn bộ message.

Backup record nên lưu:

| Thuộc tính | Mục đích |
|---|---|
| backupId | Định danh bản sao lưu |
| instanceId | Service instance nguồn |
| providerBackupId | ID snapshot/backup ở provider |
| createdAt | Thời điểm tạo |
| expiresAt | Thời điểm hết hạn |
| encryptionKeyRef | Tham chiếu khóa mã hóa |
| checksum/verification | Kết quả kiểm tra tính toàn vẹn |
| state | CREATING, AVAILABLE, FAILED, EXPIRED hoặc trạng thái nội bộ |
| retentionPolicyId | Chính sách quyết định thời hạn giữ |

Không lưu khóa mã hóa hoặc secret trực tiếp trong record backup. Chỉ lưu tham chiếu đến hệ thống quản lý khóa.

## 5. Retention, legal hold và quyền xóa

Retention là khoảng thời gian dữ liệu được giữ lại theo mục đích đã xác định. Legal hold là trạng thái tạm ngăn việc xóa một số dữ liệu do nghĩa vụ pháp lý hoặc yêu cầu bảo toàn chứng cứ.

Hai khái niệm này cần được mô hình hóa riêng:

- **Retention period**: thời hạn giữ thông thường, ví dụ backup hết hạn sau 7 ngày.
- **Legal hold**: ngoại lệ có phạm vi, lý do, người phê duyệt và thời điểm bắt đầu/kết thúc.
- **Deletion request**: yêu cầu xóa từ chủ thể hoặc người có quyền theo hợp đồng.
- **Purge schedule**: lịch xóa dữ liệu hết thời hạn.
- **Retention exception**: ngoại lệ có căn cứ, được kiểm soát và có ngày rà soát.

Một record legal hold có thể gồm:

~~~json
{
  "hold_id": "hold-2026-0042",
  "resource_id": "provider-resource-123",
  "scope": ["primary-data", "backup"],
  "reason_code": "legal-preservation",
  "approved_by": "compliance-role",
  "created_at": "2026-11-27T09:00:00Z",
  "review_at": "2027-01-27T09:00:00Z",
  "state": "ACTIVE"
}
~~~

Ví dụ chỉ minh họa metadata. Không nên đưa nội dung điều tra, dữ liệu cá nhân hoặc chi tiết nhạy cảm vào trường reason nếu mã lý do là đủ.

Legal hold phải có phạm vi cụ thể. Một hold trên backup không nhất thiết cần ngăn thu hồi network endpoint hoặc thu hồi credentials. Ngược lại, không được xóa bản sao thuộc phạm vi hold chỉ vì service instance đã bị deprovision.

Khi có deletion request, broker cần kiểm tra nghĩa vụ lưu giữ bắt buộc và chính sách hợp đồng. Nếu dữ liệu phải được giữ lại, cần giới hạn phạm vi và thời gian, ghi nhận lý do, thông báo theo quy trình và rà soát định kỳ. Không nên dùng legal hold như một cách giữ dữ liệu không thời hạn mà không có người chịu trách nhiệm.

## 6. Xóa mềm và xóa vật lý

Xóa mềm (soft delete) thường đánh dấu tài nguyên hoặc bản ghi là đã thu hồi, đồng thời giữ một số dữ liệu trong thời hạn cho phép. Xóa vật lý (hard delete/purge) loại bỏ dữ liệu khỏi nơi lưu trữ được quản lý theo khả năng của hệ thống.

Hai bước có thể được tách ra:

1. **Deprovision**: ngừng cung cấp service instance, thu hồi quyền truy cập và xóa hoặc vô hiệu hóa tài nguyên chính.
2. **Purge**: xóa backup, snapshot, replica, export và metadata hết hạn theo lịch retention.

Không nên coi soft delete là hoàn thành yêu cầu xóa nếu người dùng được hứa rằng dữ liệu sẽ bị xóa vĩnh viễn ngay. Ngược lại, nếu policy quy định một recovery window, cần giải thích rõ dữ liệu còn được giữ trong khoảng thời gian đó và ai có quyền khôi phục.

Một số provider không xóa vật lý ngay lập tức khi nhận API delete. Họ có thể đánh dấu resource là deleting, chờ background job hoặc giữ snapshot theo chính sách riêng. Broker phải phân biệt trạng thái yêu cầu đã được tiếp nhận với trạng thái dữ liệu đã được purge.

### Cryptographic erasure

Nếu dữ liệu được mã hóa bằng khóa riêng cho từng instance hoặc nhóm dữ liệu, việc hủy khóa có thể khiến dữ liệu còn trên storage không thể giải mã. Đây là một kỹ thuật hỗ trợ xóa dữ liệu, nhưng chỉ có ý nghĩa khi:

- Mọi bản sao cần xóa đều được mã hóa bằng khóa nằm trong phạm vi kiểm soát.
- Không tồn tại bản sao plaintext hoặc khóa phụ có thể khôi phục dữ liệu.
- Khóa không được backup hoặc nhân bản ngoài chính sách.
- Hệ thống quản lý khóa xác nhận thao tác hủy khóa.
- Quy trình có bằng chứng và audit trail.

Cryptographic erasure không thay thế việc xóa resource, metadata, bản sao plaintext và các bản sao do provider quản lý ngoài phạm vi khóa đó.

## 7. Xây dựng quy trình deprovision theo state machine

Xóa dữ liệu thường có nhiều bước và có thể chạy bất đồng bộ. Broker nên lưu tiến độ từng bước thay vì chỉ có một cờ deleted.

Một state machine nội bộ có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> DEPROVISION_REQUESTED
    DEPROVISION_REQUESTED --> VALIDATING
    VALIDATING --> BLOCKED: binding/hold/policy conflict
    VALIDATING --> BACKUP_PENDING: backup required
    VALIDATING --> DELETE_PENDING: no backup required
    BACKUP_PENDING --> DELETE_PENDING: backup verified
    BACKUP_PENDING --> FAILED: backup failed
    DELETE_PENDING --> PROVIDER_DELETING
    PROVIDER_DELETING --> RESOURCE_DELETED: provider confirms
    PROVIDER_DELETING --> UNKNOWN: timeout/uncertain result
    UNKNOWN --> PROVIDER_DELETING: reconciliation
    RESOURCE_DELETED --> RETENTION_PENDING
    RETENTION_PENDING --> PURGE_PENDING: retention expired
    PURGE_PENDING --> COMPLETED: all required purge confirmed
    BLOCKED --> VALIDATING: condition resolved
~~~

Các trạng thái này là mô hình nội bộ, không phải enum bắt buộc của OSB API. Broker ánh xạ chúng sang phản hồi đồng bộ hoặc bất đồng bộ và trạng thái last operation theo hợp đồng.

### Các bước thực thi

**Bước 1: Khóa instance và tạo operation**

Tạo operation deprovision ổn định, lưu instance ID, request fingerprint, policy version và thời điểm bắt đầu. Ngăn update hoặc bind mới khi instance đang thu hồi.

**Bước 2: Kiểm tra binding và quyền truy cập**

Xác định binding còn tồn tại, thu hồi credential hoặc yêu cầu nền tảng hoàn tất unbind theo hợp đồng. Thu hồi quyền trực tiếp ở provider nếu policy yêu cầu.

**Bước 3: Đánh giá retention và backup**

Đọc policy áp dụng cho instance, kiểm tra legal hold và quyết định có cần tạo backup. Nếu backup bắt buộc, chờ provider xác nhận backup đã sẵn sàng và kiểm tra tính toàn vẹn.

**Bước 4: Xóa tài nguyên chính**

Gọi provider adapter để xóa resource. Nếu provider trả operation ID, lưu lại và theo dõi tiến độ. Nếu timeout, không giả định thao tác thất bại; chuyển sang trạng thái chưa xác định và reconcile.

**Bước 5: Xử lý dữ liệu phụ**

Xóa replica, volume, temporary export, credential, secret, cache và tài nguyên phụ theo dependency graph. Không xóa backup còn trong thời hạn retention hoặc thuộc legal hold.

**Bước 6: Ghi nhận kết quả và lên lịch purge**

Khi tài nguyên chính được xác nhận đã xóa, lưu tombstone, kết quả operation và lịch purge. Công việc purge backup và dữ liệu còn lại có thể chạy bằng worker riêng.

**Bước 7: Hoàn tất và lưu audit**

Khi các điều kiện deprovision theo hợp đồng hoàn tất, trả kết quả cho nền tảng. Lưu bằng chứng cần thiết trong thời hạn audit, không giữ dữ liệu nghiệp vụ đã bị yêu cầu xóa.

## 8. Xử lý bất đồng bộ trong deprovision

Provider có thể cần thời gian để xóa database lớn, giải phóng volume hoặc xóa snapshot. Nếu client OSB cho phép bất đồng bộ, broker có thể tiếp nhận yêu cầu, trả operation ID và cho nền tảng truy vấn last operation.

Một record operation có thể gồm:

| Thuộc tính | Mục đích |
|---|---|
| operationId | Định danh thao tác deprovision |
| instanceId | Instance đang thu hồi |
| policyVersion | Phiên bản retention/deletion policy áp dụng |
| currentStep | Bước đang thực hiện |
| providerOperationId | ID tác vụ xóa ở provider |
| backupId | Backup được tạo nếu policy yêu cầu |
| legalHoldState | Trạng thái hold tại thời điểm xử lý |
| state | Trạng thái tổng thể |
| startedAt, updatedAt | Thời điểm cập nhật |
| failureCode | Mã lỗi đã làm sạch |

Luồng bất đồng bộ:

1. Ghi instance ở trạng thái DEPROVISIONING và tạo operation.
2. Ghi event vào outbox trong cùng transaction.
3. Trả response async theo hợp đồng nếu request chấp nhận.
4. Worker xử lý từng bước theo policy.
5. Worker lưu checkpoint sau mỗi side effect.
6. Last operation trả trạng thái đang chạy, thành công hoặc thất bại.
7. Reconciliation tiếp quản operation bị treo hoặc có kết quả provider chưa rõ.

Nếu client không chấp nhận async mà provider không thể hoàn thành đồng bộ, broker cần trả lỗi theo quy tắc OSB API tương ứng. Không trả thành công chỉ vì đã đưa lệnh xóa vào queue.

## 9. Idempotency và phục hồi khi xóa bị gián đoạn

Nền tảng có thể gửi lại DELETE do timeout hoặc mất response. Deprovision cần idempotent: cùng instance và cùng yêu cầu thu hồi không được tạo nhiều side effect nguy hiểm.

Các quy tắc nên áp dụng:

- Cùng instance đang DEPROVISIONING: trả lại operation hiện có.
- Instance đã được thu hồi: xử lý lặp theo ngữ nghĩa idempotent của OSB API và trạng thái broker.
- Instance không tồn tại nhưng provider resource còn: chạy reconciliation theo external reference nếu có đủ bằng chứng sở hữu.
- Cùng instance ID nhưng request không tương thích với bản ghi hiện tại: không xóa một tài nguyên khác.
- Provider timeout sau lệnh delete: tra cứu trạng thái resource hoặc operation trước khi gửi lại.
- Backup đã tạo nhưng xóa resource thất bại: giữ backup theo policy và tiếp tục xử lý hoặc dọn dẹp khi kết quả cuối cùng được xác định.

Không dùng việc xóa bản ghi instance nội bộ làm dấu hiệu duy nhất rằng resource đã bị xóa. Giữ tombstone đủ lâu để nhận diện retry và tránh tạo lại tài nguyên do request cũ.

### Transactional outbox và dependency graph

Nếu xóa cần nhiều bước, broker có thể lưu các task theo dependency:

~~~mermaid
flowchart TD
    Start["Deprovision operation"] --> Revoke["Thu hồi binding/credentials"]
    Revoke --> Backup{"Backup bắt buộc?"}
    Backup -->|Có| Snapshot["Tạo và xác minh backup"]
    Backup -->|Không| Delete["Xóa tài nguyên chính"]
    Snapshot --> Delete
    Delete --> Replica["Xóa replica và volume phụ"]
    Replica --> Secret["Xóa secret và temporary export"]
    Secret --> Retention["Đặt lịch purge backup theo policy"]
    Retention --> Audit["Ghi audit và hoàn tất operation"]
~~~

Mỗi bước cần có trạng thái, retry policy và idempotency key riêng. Một bước hoàn tất không nên bị chạy lại theo cách tạo thêm backup hoặc xóa nhầm tài nguyên của instance khác.

## 10. Bảo vệ backup, secret và dữ liệu còn giữ lại

Dữ liệu được giữ lại sau deprovision vẫn cần bảo vệ như dữ liệu đang hoạt động.

- Mã hóa backup khi truyền và khi lưu.
- Giới hạn quyền restore theo tenant, service role và quy trình phê duyệt.
- Dùng khóa riêng hoặc phạm vi khóa phù hợp để tránh truy cập chéo tenant.
- Ghi audit cho thao tác tạo, đọc, restore, export và purge backup.
- Không lưu password hoặc secret trong backup metadata, log hay operation error.
- Đặt TTL và lifecycle rule cho object storage chứa backup.
- Kiểm tra quyền truy cập của provider support account và service account.
- Xóa credential cũ và thu hồi token sau khi binding hoặc instance bị thu hồi.
- Bảo đảm bản backup được khôi phục thử nghiệm theo lịch nếu đó là cam kết của dịch vụ.

Nếu người dùng yêu cầu xóa dữ liệu, broker cần kiểm tra cả backup và bản sao. Xóa bản chính nhưng để bản export không kiểm soát hoặc bản snapshot tồn tại vô thời hạn sẽ không đáp ứng chính sách đã công bố.

## 11. Ví dụ mô hình hóa DeprovisionPolicy trong Java

Một model nội bộ có thể biểu diễn các lựa chọn retention:

~~~java
public record DeprovisionPolicy(
    boolean createBackupBeforeDelete,
    boolean backupRequired,
    Duration backupRetention,
    boolean deleteReplicas,
    boolean revokeBindings,
    boolean purgeTemporaryExports,
    boolean legalHoldSupported
) {
    public DeprovisionPolicy {
        if (backupRequired && !createBackupBeforeDelete) {
            throw new IllegalArgumentException(
                "Required backup must be enabled");
        }

        if (backupRetention != null
                && backupRetention.isNegative()) {
            throw new IllegalArgumentException(
                "Backup retention cannot be negative");
        }
    }
}
~~~

Model này minh họa cấu hình policy, không phải kiểu dữ liệu có sẵn trong Spring Cloud Open Service Broker. Trong hệ thống thật, cần kiểm tra quyền chỉnh sửa policy, đơn vị thời gian, giá trị mặc định, thời điểm bắt đầu retention và cách xử lý policy version cũ.

Một service điều phối có thể có cấu trúc:

~~~java
@Service
public class DeprovisionCoordinator {

    private final InstanceRepository instances;
    private final DeprovisionPolicyRepository policies;
    private final BackupService backups;
    private final ProviderAdapter provider;
    private final OperationRepository operations;
    private final LegalHoldService legalHolds;

    public DeprovisionCoordinator(
            InstanceRepository instances,
            DeprovisionPolicyRepository policies,
            BackupService backups,
            ProviderAdapter provider,
            OperationRepository operations,
            LegalHoldService legalHolds) {
        this.instances = instances;
        this.policies = policies;
        this.backups = backups;
        this.provider = provider;
        this.operations = operations;
        this.legalHolds = legalHolds;
    }

    public Mono<DeprovisionResult> deprovision(
            String instanceId,
            boolean asyncAccepted) {

        return instances.findForUpdate(instanceId)
            .switchIfEmpty(Mono.error(
                new ServiceInstanceNotFoundException(instanceId)))
            .flatMap(instance ->
                policies.findFor(instance)
                    .flatMap(policy ->
                        legalHolds.check(instance)
                            .flatMap(hold ->
                                validateBindingsAndPolicy(instance, hold)
                                    .then(startOperation(
                                        instance, policy, asyncAccepted))
                            )
                    )
            );
    }

    private Mono<Void> validateBindingsAndPolicy(
            ServiceInstance instance,
            LegalHold hold) {
        if (hold.blocksResourceDeletion()) {
            return Mono.error(
                new DeprovisionBlockedByLegalHoldException());
        }
        return bindingService.ensureBindingsRevoked(instance);
    }

    private Mono<DeprovisionResult> startOperation(
            ServiceInstance instance,
            DeprovisionPolicy policy,
            boolean asyncAccepted) {
        // Reserve instance, persist operation/outbox,
        // then execute or enqueue the workflow.
        return operations.startDeprovision(
            instance, policy, asyncAccepted);
    }
}
~~~

Đây là skeleton minh họa ranh giới trách nhiệm; repository, service và exception là abstraction của ứng dụng. Phần kiểm tra legal hold trong ví dụ chỉ minh họa một policy có thể chặn xóa tài nguyên. Trong thực tế, hold có thể chỉ áp dụng cho dữ liệu hoặc backup cụ thể; broker cần đánh giá phạm vi hold trước khi quyết định bước nào được phép tiếp tục.

Không giữ database transaction mở trong khi tạo backup hoặc gọi provider. Hãy reserve instance và ghi operation/outbox trong transaction ngắn, sau đó để worker xử lý các bước dài.

## 12. Kiểm thử chính sách retention và deletion

Kiểm thử cần chứng minh dữ liệu được giữ hoặc xóa đúng policy, đồng thời thao tác deprovision có thể retry và phục hồi.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Plan không yêu cầu backup | Không tạo backup ngoài chính sách |
| Backup tùy chọn được bật | Tạo backup theo lựa chọn và policy |
| Backup bắt buộc thất bại | Không xóa resource chính nếu policy yêu cầu backup trước |
| Backup thành công | Lưu backup ID, thời hạn và trạng thái xác minh |
| Legal hold chặn resource | Không thực hiện bước xóa nằm trong phạm vi hold |
| Legal hold chỉ áp dụng backup | Xử lý các tài nguyên ngoài phạm vi hold theo policy |
| Unbind chưa hoàn tất | Không thu hồi instance theo cách để lại credential hoạt động |
| Provider delete timeout | Giữ trạng thái chưa xác định và reconcile |
| Retry cùng deprovision | Trả operation hiện có hoặc kết quả đã hoàn tất |
| Backup hết retention | Tạo purge task và xác nhận kết quả |
| Replica hoặc export còn sót | Reconciliation phát hiện và xử lý |
| Broker restart giữa quy trình | Worker tiếp tục từ checkpoint bền vững |
| Tenant A yêu cầu restore | Không thể truy cập backup của tenant B |
| Purge hoàn tất | Chỉ giữ metadata audit được phép theo retention |

Ngoài unit test cho policy evaluator, cần kiểm thử tích hợp với provider sandbox hoặc test double có thể mô phỏng backup, delete, timeout và eventual consistency. Kiểm tra số lần gọi provider, trạng thái operation, thời hạn backup, quyền truy cập và audit event.

Một bài kiểm thử restore định kỳ có thể xác nhận backup thực sự dùng được. Backup có trạng thái AVAILABLE nhưng không thể restore sẽ không đáp ứng mục đích recovery.

## 13. Những lỗi thường gặp

**Xóa bản ghi broker trước khi xóa tài nguyên provider.** Nếu provider từ chối hoặc timeout, broker mất thông tin để tiếp tục thu hồi. Hãy giữ trạng thái và tombstone cho đến khi xác định được kết quả.

**Tạo backup tự động cho mọi service.** Cache, dữ liệu tạm hoặc yêu cầu xóa ngay có thể không phù hợp với việc tạo bản sao. Hãy dựa vào policy của service/plan và yêu cầu đã được công bố.

**Giữ backup không có thời hạn.** Backup cần retention, quyền truy cập, chi phí và purge schedule rõ ràng.

**Cho rằng xóa primary resource là đã xóa toàn bộ dữ liệu.** Replica, snapshot, export, log, cache và secret có thể còn tồn tại. Cần inventory và dependency graph.

**Coi timeout là xóa thất bại.** Provider có thể đã xóa tài nguyên nhưng response bị mất. Reconcile trước khi gửi lại lệnh hoặc hoàn tất operation.

**Dùng legal hold để chặn mọi thao tác.** Hold có phạm vi. Thu hồi credential hoặc network access có thể vẫn cần thiết dù một bản backup phải được giữ lại.

**Xóa secret mà không thu hồi quyền ở provider.** Xóa secret trong kho của broker không tự vô hiệu hóa credential đã được provider cấp. Phải revoke hoặc disable quyền ở nguồn.

**Báo hoàn tất trước khi dữ liệu được xử lý theo cam kết.** Phân biệt việc tiếp nhận deprovision, việc xóa resource chính và việc purge backup theo retention. Response OSB và tài liệu dịch vụ phải phản ánh đúng phạm vi hoàn tất.

## 14. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, handler deprovision nên chuyển request sang một coordinator quản lý policy và state machine. Policy được xác định theo service/plan và phiên bản áp dụng cho instance; không nên đọc một cấu hình mới rồi áp ngược vào instance cũ nếu điều đó làm thay đổi cam kết retention đã có.

Lưu operation, policy version, backup reference, legal hold state và checkpoint một cách bền vững. Tách provider adapter cho backup, delete, revoke credential và purge. Dùng outbox/worker cho các bước dài, idempotency cho retry và reconciliation khi provider trả kết quả chưa rõ. Giữ tombstone và audit metadata tối thiểu trong thời hạn được phép để nhận diện request lặp và chứng minh trạng thái xử lý.

Catalog mô tả khả năng dịch vụ, nhưng chính sách giữ và xóa dữ liệu cần được tài liệu hóa trong mô tả plan và hợp đồng dịch vụ phù hợp. Khi deprovision, broker phải thực hiện đúng chính sách đã công bố: thu hồi quyền truy cập, xử lý tài nguyên chính, quản lý backup và xóa dữ liệu phụ theo thời hạn. Một quy trình rõ ràng giúp nền tảng biết khi nào instance đã được thu hồi và giúp người sử dụng hiểu dữ liệu của họ được giữ, khôi phục hoặc xóa như thế nào.

