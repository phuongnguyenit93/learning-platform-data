# Cập nhật gói thất bại trong khi instance vẫn đang được sử dụng

Một service instance có thể vẫn phục vụ ứng dụng trong khi đội vận hành yêu cầu cập nhật gói dịch vụ: nâng phiên bản engine, áp dụng bản vá bảo mật, thay runtime package, cập nhật extension hoặc chuyển sang cấu hình provider mới. Thao tác này phức tạp hơn cập nhật metadata vì tài nguyên đang có consumer, connection, transaction và dữ liệu cần bảo vệ. Nếu provider từ chối update do instance đang được sử dụng, broker cần xác định chính xác điều kiện chặn, giữ nguyên trạng thái hiện tại và hướng dẫn một quy trình nâng cấp an toàn.

Trong SPRING_CLOUD_SERVICE_BROKER, cần phân biệt thay đổi service plan theo Open Service Broker API với nâng cấp package/version ở provider. Đổi plan là thay đổi cấu hình dịch vụ được nền tảng yêu cầu qua endpoint update; nâng package là thao tác kỹ thuật có thể xảy ra bên trong provider ngay cả khi plan không đổi. Cả hai có thể cùng xuất hiện trong một workflow, nhưng có precondition, rủi ro và cách rollback khác nhau.

## 1. Xác định chính xác loại update đang thất bại

Trước khi xử lý, hãy xác định request đang yêu cầu thay đổi gì. Từ “package” có thể chỉ nhiều loại artifact khác nhau.

| Loại thay đổi | Ví dụ | Thành phần chịu trách nhiệm |
|---|---|---|
| Service plan update | Chuyển từ plan standard sang plan production | Broker và OSB update workflow |
| Provider engine upgrade | PostgreSQL 15 lên PostgreSQL 16 | Provider adapter và dịch vụ hạ tầng |
| Security patch | Cập nhật minor/patch version của database engine | Provider maintenance workflow |
| Extension/package update | Nâng extension PostgreSQL hoặc plugin Redis | Provider hoặc engine quản lý package |
| Runtime image update | Thay image của workload do broker quản lý | Provider/container platform |
| Broker software deployment | Nâng phiên bản chính service broker | Đội triển khai broker; không phải update service instance |

Không nên xử lý tất cả các trường hợp như một PATCH plan. Ví dụ, plan standard có thể vẫn giữ nguyên nhưng provider cần nâng engine để vá CVE. Ngược lại, đổi plan có thể chỉ thay quota hoặc giới hạn mà không cần cài package mới.

## 2. Mô tả triệu chứng và ảnh hưởng

Một số triệu chứng thường gặp:

- OSB update trả lỗi vì provider báo instance đang có connection hoặc transaction hoạt động.
- Provider job chuyển sang FAILED do không thể dừng engine hoặc không lấy được maintenance lock.
- Update chạy quá lâu vì consumer không đóng session.
- Package mới cài được một phần nhưng service chưa thể khởi động lại.
- Provider từ chối nâng cấp do thiếu dung lượng, quota hoặc phiên bản nguồn không được hỗ trợ.
- Instance vẫn trả traffic nhưng broker ghi nhận operation failed.
- Một số binding tiếp tục kết nối được, một số binding lỗi do endpoint, protocol hoặc authentication thay đổi.
- Retry PATCH tạo nhiều job nâng cấp hoặc làm trạng thái instance khó xác định.

Trước khi thay đổi trạng thái, cần ghi lại instance ID, service ID, plan ID, request fingerprint, broker operation ID, provider job ID, provider resource ID, thời điểm lỗi và phiên bản package nguồn/đích. Không đưa password, token hoặc payload nhạy cảm vào ticket/log.

## 3. Kiểm tra instance có thực sự đang được sử dụng

Thông báo “instance is in use” không nhất thiết chỉ có nghĩa ứng dụng đang gửi request. Provider có thể coi nhiều loại hoạt động là consumer đang sử dụng tài nguyên.

| Dấu hiệu | Cách kiểm tra | Tác động đến update |
|---|---|---|
| Active client connections | Connection count, session list, pool metrics | Có thể cần drain hoặc chờ session kết thúc |
| Long-running transaction | Transaction age, lock wait, query duration | Migration/restart có thể bị chặn hoặc gây rollback |
| Prepared statement/session state | Session metadata theo engine | Restart có thể làm consumer mất trạng thái phiên |
| Background jobs | Scheduler, replication, backup, vacuum, compaction | Có thể cần đợi job hoàn tất |
| Active bindings | Binding records và provider principals | Xác định consumer nào cần thông báo hoặc phối hợp |
| Shared service instance | Danh sách space/app đang dùng cùng instance | Không thể chỉ hỏi một nhóm consumer |
| Replication/failover | Replica lag, cluster membership, failover state | Upgrade cần thứ tự và quorum phù hợp |

Active binding không đồng nghĩa luôn có connection đang mở. Một ứng dụng có thể đã bind nhưng đang idle; ngược lại, consumer có thể kết nối bằng credential được chia sẻ ngoài binding mà broker không quan sát trực tiếp. Vì vậy cần kết hợp dữ liệu broker với telemetry của provider.

## 4. Phân biệt binding, connection và dependency

Broker thường lưu binding ID, principal ID và secret reference. Provider lại quan sát connection/session thực tế. Hai góc nhìn này bổ sung cho nhau:

- Binding cho biết consumer nào đã được cấp quyền sử dụng service.
- Connection cho biết client nào đang kết nối tại thời điểm kiểm tra.
- Transaction/job cho biết workload nào đang thực hiện thao tác có thể bị ảnh hưởng.
- Dependency map cho biết ứng dụng hoặc dịch vụ nào sẽ bị gián đoạn nếu instance restart.

Không tự động unbind mọi consumer để làm cho update thành công. Unbind có thể thu hồi credential và khiến ứng dụng mất khả năng kết nối, trong khi nguyên nhân thật chỉ là một transaction dài cần chờ hoàn tất.

## 5. Thu thập bằng chứng trước khi retry

Một lần update thất bại cần có đủ dữ liệu để phân loại. Thu thập:

1. Request OSB: method, endpoint, query, API version và các field đã chuẩn hóa; che dữ liệu nhạy cảm.
2. Broker operation: ID, state, attempt, request fingerprint và thời điểm bắt đầu/kết thúc.
3. Provider operation: job ID, raw status, error code và provider request ID.
4. Instance state: trạng thái broker lưu và trạng thái resource provider quan sát.
5. Consumer usage: active connections, transaction, binding và maintenance dependencies.
6. Package metadata: source version, target version, compatibility range và release notes.
7. Capacity: storage, memory, CPU, quota, replica lag và maintenance lock.
8. Timeline: thời điểm provider nhận update, bắt đầu maintenance, thất bại và có thể đã áp dụng một phần.

Nếu provider timeout sau khi đã nhận yêu cầu, kết quả là UNKNOWN cho đến khi tra cứu job/resource xác nhận. Không gửi lệnh update mới ngay chỉ vì broker chưa nhận được response.

## 6. Kiểm tra khả năng tương thích source và target package

Một update có thể thất bại vì phiên bản nguồn không nằm trong đường nâng cấp được hỗ trợ. Một số provider yêu cầu nâng tuần tự qua phiên bản trung gian hoặc chạy pre-upgrade migration.

Kiểm tra:

- Phiên bản engine hiện tại và target có nằm trong ma trận nâng cấp được provider hỗ trợ không.
- Có cần nâng minor version trước khi nâng major version không.
- Extension, plugin, driver hoặc stored procedure có tương thích không.
- Consumer dùng protocol/client version nào.
- Có thay đổi authentication, TLS, cipher, endpoint hoặc certificate không.
- Có thay đổi format dữ liệu hoặc system catalog không.
- Có yêu cầu snapshot/backup trước khi update không.
- Có thể downgrade package sau khi data format đã được migrate không.

Không suy luận rằng package version cao hơn luôn tương thích ngược. Major upgrade có thể thay đổi data directory, SQL behavior, wire protocol hoặc extension ABI. Cần kiểm tra release notes và ma trận tương thích của provider/engine trước khi cho phép update.

## 7. Kiểm tra điều kiện provider đang chặn update

Provider thường trả một mã lỗi hoặc precondition cụ thể. Hãy phân loại thay vì chỉ lưu một thông báo chung “instance in use”.

| Nhóm lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Active connection | Provider yêu cầu không còn session | Xác định client, lên lịch drain hoặc dùng rolling upgrade nếu hỗ trợ |
| Active transaction/lock | Có transaction dài hoặc DDL lock | Tìm owner, xác nhận an toàn rồi chờ hoặc xử lý transaction theo runbook |
| Maintenance already running | Có operation khác đang chiếm maintenance lock | Theo dõi operation hiện tại; không khởi chạy job thứ hai |
| Unsupported source version | Phiên bản hiện tại không thể nâng trực tiếp | Nâng theo các bước trung gian được hỗ trợ |
| Insufficient capacity | Thiếu disk, memory, quota hoặc replica | Tăng capacity hoặc giải phóng tài nguyên an toàn |
| Backup prerequisite | Chưa có snapshot/backup hợp lệ | Tạo và xác minh backup trước khi tiếp tục |
| Replication lag | Replica chưa đồng bộ | Đợi lag về ngưỡng an toàn hoặc xử lý replication theo provider |
| Extension incompatibility | Package phụ thuộc không tương thích | Cập nhật extension theo thứ tự hoặc giữ package hiện tại |
| Permission denied | Provider account thiếu quyền maintenance | Sửa role/service account theo least privilege |
| Provider transient failure | 429, 5xx hoặc timeout | Retry theo backoff sau khi kiểm tra side effect |

Lưu raw provider code trong trường nội bộ có kiểm soát để chẩn đoán; trả description an toàn và ổn định cho nền tảng OSB. Không trả nguyên stack trace hoặc thông tin account nhạy cảm.

## 8. Kiểm tra OSB update request và capability

OSB API dùng PATCH service instance để yêu cầu update. Broker cần kiểm tra service ID, plan ID nếu được thay đổi, parameters, context và previous_values theo request contract. Request có thể yêu cầu xử lý bất đồng bộ bằng accepts_incomplete=true.

Trước khi gọi provider:

- Xác minh service instance tồn tại và thuộc đúng tenant/owner context.
- Xác minh service/plan hỗ trợ loại update được yêu cầu.
- Kiểm tra capability plan_updateable khi thay đổi plan theo catalog contract.
- Validate parameters theo schema của plan đích.
- Dùng previous_values như thông tin trạng thái trước đó để kiểm tra transition khi được gửi.
- Kiểm tra instance không ở trạng thái provisioning, deprovisioning, deleting hoặc một update khác.
- Kiểm tra maintenance/package target có nằm trong policy cho phép.

Không coi plan_updateable là bằng chứng rằng mọi package upgrade đều được phép. Capability này liên quan đến việc cập nhật plan theo OSB; provider package upgrade có thể là maintenance workflow riêng được broker công bố và kiểm soát theo policy.

## 9. Phân biệt đổi plan và nâng package trong OSB

Hai hoạt động có thể cùng dùng logic update nội bộ nhưng không nên nhập nhằng:

| Đặc điểm | Đổi service plan | Nâng package/provider version |
|---|---|---|
| Mục tiêu | Thay quota, tier, feature hoặc SLA | Thay phiên bản engine/runtime/extension |
| Nguồn yêu cầu | Nền tảng gọi OSB PATCH | Operator, maintenance policy hoặc workflow update được broker hỗ trợ |
| Kiểm tra chính | plan_updateable, plan schema, transition rules | Compatibility, backup, maintenance window, active workload |
| Side effect | Thay cấu hình/quota; có thể cần resize | Có thể restart, migrate data hoặc failover |
| Rollback | Có thể chuyển về plan cũ nếu provider cho phép | Có thể không downgrade được sau data migration |
| Kết quả | Instance có plan mới | Instance chạy package version mới đã xác minh |

Nếu broker dùng OSB PATCH để thực hiện package upgrade theo maintenance_info hoặc parameters được định nghĩa, phải lưu target version và request context rõ ràng. Nếu package upgrade là tác vụ operator riêng, không giả mạo nó thành plan change hoặc tự tạo một request OSB từ dữ liệu không có authorization.

## 10. Khi instance đang có workload, chọn chiến lược nâng cấp nào?

Không phải mọi package update đều yêu cầu dừng toàn bộ consumer. Tùy khả năng provider, có thể chọn:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| In-place maintenance | Dừng/khởi động lại cùng instance để cập nhật package | Provider chỉ hỗ trợ một node hoặc workload chấp nhận downtime |
| Rolling upgrade | Nâng từng node/replica trong cluster | Có replication và topology hỗ trợ chuyển traffic |
| Blue-green replacement | Tạo instance/package mới, đồng bộ dữ liệu, chuyển endpoint rồi bỏ bản cũ | Cần giảm rủi ro và có thể chuyển traffic |
| Online patch | Cập nhật thành phần không yêu cầu restart toàn bộ | Provider/engine hỗ trợ rõ ràng |
| Deferred maintenance | Đánh dấu pending và chờ maintenance window | Workload đang bận hoặc khách hàng chọn lịch |

Broker không nên tự chọn chiến lược chỉ dựa trên số connection hiện tại. Cần biết provider có hỗ trợ rolling/online upgrade hay không, dữ liệu có thể migrate không và consumer có thể reconnect/retry không.

## 11. Quy trình drain consumer an toàn

Nếu provider yêu cầu không còn session, cần có kế hoạch drain:

1. Xác định tất cả binding/consumer có thể truy cập instance.
2. Thông báo maintenance window và thời gian dự kiến.
3. Kiểm tra ứng dụng hỗ trợ retry kết nối, graceful close và connection pool refresh.
4. Dừng nhận workload mới ở consumer hoặc chuyển traffic sang instance/replica khác.
5. Chờ request và transaction đang chạy hoàn tất.
6. Xác minh connection count giảm về ngưỡng provider yêu cầu.
7. Thực hiện update trong thời gian maintenance đã thống nhất.
8. Xác minh service endpoint, health và package version.
9. Cho consumer reconnect từng nhóm và theo dõi lỗi.
10. Khôi phục traffic đầy đủ sau khi kiểm tra thành công.

Không tự kill session hoặc terminate transaction nếu chưa hiểu tác động. Một transaction có thể đang commit dữ liệu quan trọng; chấm dứt cưỡng bức có thể gây rollback, retry hoặc lỗi ứng dụng.

## 12. Maintenance window và điều phối nhiều consumer

Nếu instance được dùng bởi nhiều ứng dụng hoặc nhiều space, một consumer có thể sẵn sàng nhưng consumer khác vẫn đang xử lý. Broker cần một maintenance policy có owner, thời gian và trạng thái rõ ràng.

Thông tin nên theo dõi:

- Maintenance request ID và target package version.
- Người/actor yêu cầu và phạm vi tenant.
- Danh sách consumer/binding bị ảnh hưởng.
- Maintenance window đã lên lịch.
- Thời gian drain bắt đầu và deadline.
- Trạng thái provider job và từng bước rollout.
- Kết quả verification và thời điểm mở traffic lại.

Nếu consumer không thể dừng trong cửa sổ đã chọn, cần quyết định hoãn, chuyển sang chiến lược rolling hoặc yêu cầu chủ sở hữu chấp nhận downtime. Không âm thầm tiếp tục update phá vỡ SLA của consumer.

## 13. Xử lý update bất đồng bộ

Package upgrade có thể kéo dài vì backup, migration, restart, failover và kiểm tra dữ liệu. Nếu thao tác được thực hiện qua OSB PATCH và nền tảng gửi accepts_incomplete=true, broker có thể trả 202 Accepted cùng operation ID sau khi đã lưu operation bền vững.

Luồng điển hình:

1. Nhận PATCH và xác thực request.
2. Tạo operation record cùng request fingerprint và target package version.
3. Kiểm tra instance/plan/capability và maintenance policy.
4. Lưu trạng thái ACCEPTED/QUEUED trước khi trả 202.
5. Worker kiểm tra consumer usage và provider preconditions.
6. Gọi provider update với idempotency key.
7. Lưu provider job ID và poll/callback.
8. Khi provider báo hoàn tất, xác minh package version, health, replication và data state.
9. Chuyển operation thành SUCCEEDED hoặc FAILED.
10. Trả trạng thái qua last_operation.

Nếu broker chỉ có thể xử lý async nhưng request không chấp nhận async, phải trả lỗi OSB phù hợp, thường là 422 với error AsyncRequired. Không trả 202 trước khi operation đã được lưu bền vững.

## 14. Theo dõi state machine của update

Một state machine nội bộ giúp phân biệt lỗi precondition với lỗi trong lúc nâng cấp:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> VALIDATING
    VALIDATING --> BLOCKED_IN_USE: consumer/transaction active
    BLOCKED_IN_USE --> VALIDATING: usage drained or window opened
    VALIDATING --> BACKUP
    BACKUP --> UPGRADING
    UPGRADING --> VERIFYING
    VERIFYING --> SUCCEEDED
    UPGRADING --> RECOVERING: provider failure/partial update
    VERIFYING --> RECOVERING: version or health mismatch
    RECOVERING --> FAILED: recovery cannot restore service
    RECOVERING --> VERIFYING: repair/retry succeeded
    VALIDATING --> FAILED: permanent precondition failure
~~~

State machine này là mô hình nội bộ gợi ý. OSB last_operation chỉ công bố các trạng thái giao thức như in progress, succeeded hoặc failed; không trả trực tiếp BLOCKED_IN_USE hay UPGRADING nếu đó không phải giá trị OSB hợp lệ. Description có thể giải thích rằng operation đang chờ maintenance window hoặc consumer drain.

Không để operation ở in progress vô thời hạn. Cần deadline, alert và chính sách kết luận khi provider job không còn truy vấn được.

## 15. Đọc và phân loại lỗi provider

Khi provider update thất bại, hãy lưu:

- Provider job ID và raw provider state.
- Error code ổn định của provider.
- Step thất bại: precheck, backup, package install, restart, migration, failover hay verification.
- Package source/target version.
- Resource health trước và sau lỗi.
- Operation có side effect một phần hay chưa.
- Provider có hỗ trợ retry, resume, rollback hoặc cancel không.

Ví dụ mapping lỗi nội bộ:

| Provider error | Broker classification | Hành động |
|---|---|---|
| ACTIVE_SESSIONS | BLOCKED_IN_USE | Drain hoặc lên lịch lại |
| TRANSACTION_TIMEOUT | RETRYABLE_AFTER_DRAIN | Kiểm tra transaction owner |
| VERSION_PATH_UNSUPPORTED | PERMANENT_PRECONDITION | Chọn đường nâng cấp trung gian |
| DISK_CAPACITY_LOW | CAPACITY_BLOCKED | Tăng dung lượng hoặc giải phóng an toàn |
| BACKUP_FAILED | SAFE_TO_RETRY_AFTER_REPAIR | Không bắt đầu package migration |
| PACKAGE_INSTALL_FAILED | PARTIAL_UPDATE_UNKNOWN | Kiểm tra package/resource state |
| RESTART_TIMEOUT | RECOVERING | Xác minh process và health provider |
| DATA_MIGRATION_FAILED | RECOVERY_REQUIRED | Dừng rollout và đánh giá backup/restore |
| RATE_LIMITED | TRANSIENT | Backoff và tôn trọng Retry-After |

Không chuyển mọi provider error thành cùng một exception 500. Broker cần phân loại lỗi có thể retry, lỗi chờ điều kiện, lỗi cấu hình vĩnh viễn và lỗi có thể đã thay đổi tài nguyên.

## 16. Nếu package đã được cài một phần

Đây là tình huống rủi ro cao. Provider có thể đã:

- Tải package mới nhưng chưa kích hoạt.
- Thay binary nhưng chưa restart engine.
- Restart một replica trong cluster nhưng replica khác chưa nâng.
- Chạy schema/data migration một phần.
- Chuyển primary sang node mới nhưng health check chưa ổn định.

Khi đó, broker không nên ghi nhận instance vẫn hoàn toàn ở phiên bản cũ hoặc đã hoàn toàn ở phiên bản mới nếu chưa xác minh. Đánh dấu trạng thái nội bộ cần recovery/reconciliation, ngăn một update mới cạnh tranh và truy vấn provider theo từng node/step.

Nếu provider hỗ trợ resume job, tiếp tục cùng job theo idempotency key. Nếu provider không hỗ trợ, dùng runbook recovery của provider. Không tự chạy lại package installer hoặc migration script nếu không biết bước trước đã commit đến đâu.

## 17. Rollback và forward recovery

Rollback package không phải lúc nào cũng an toàn. Một số engine không hỗ trợ downgrade sau khi data directory hoặc catalog đã được migrate. Vì vậy cần phân biệt:

- **Rollback application/client:** quay consumer về phiên bản driver hoặc application trước.
- **Rollback package:** cài lại engine/package cũ; chỉ làm nếu provider hỗ trợ và dữ liệu tương thích.
- **Restore from backup:** phục hồi dữ liệu từ snapshot/PITR; có thể mất các thay đổi sau thời điểm backup.
- **Forward recovery:** sửa lỗi ở phiên bản hiện tại, tiếp tục migration hoặc hoàn tất rollout.

Trước khi update, xác định phương án phục hồi và kiểm tra backup có thể restore. Với migration không thể đảo ngược, ưu tiên forward recovery theo hướng dẫn provider thay vì cố downgrade.

Nếu provider update đã làm thay đổi dữ liệu, không dùng snapshot cũ một cách tự động vì có thể mất giao dịch hợp lệ phát sinh trong thời gian giữa backup và restore. Quyết định restore cần có owner, RPO/RTO và đánh giá mất dữ liệu rõ ràng.

## 18. Giữ broker state nhất quán với provider state

Broker cần lưu desired package version và observed package version riêng:

| Trường | Ý nghĩa |
|---|---|
| desired_package_version | Phiên bản mà operation yêu cầu |
| observed_package_version | Phiên bản provider xác nhận đang chạy |
| operation_id | OSB update operation |
| provider_job_id | Job provider thực hiện nâng cấp |
| update_phase | Bước hiện tại của workflow |
| maintenance_window | Cửa sổ bảo trì đã chọn |
| last_verified_at | Thời điểm kiểm tra version/health gần nhất |
| recovery_state | Trạng thái xử lý khi có lỗi một phần |

Không cập nhật observed_package_version chỉ dựa trên request đã được gửi. Chỉ cập nhật sau khi provider xác nhận và broker verify instance thực sự chạy target version. Nếu broker restart giữa chừng, worker mới đọc desired version và provider job ID để tiếp tục.

## 19. Reconciliation sau lỗi hoặc restart

Reconciliation so sánh trạng thái broker với tài nguyên thật:

1. Đọc operation chưa terminal và desired package version.
2. Truy vấn provider job bằng provider job ID.
3. Truy vấn instance/package version thực tế.
4. Kiểm tra cluster health, replica status, connection acceptance và migration state.
5. So sánh với target version và provider maintenance state.
6. Nếu job vẫn chạy, tiếp tục polling.
7. Nếu job thất bại trước khi có side effect, cho phép retry theo policy.
8. Nếu package đã thay đổi một phần, chuyển recovery workflow và ngăn update trùng.
9. Nếu provider đã hoàn tất nhưng broker chưa commit, hoàn tất operation dựa trên bằng chứng provider.
10. Ghi audit và metric cho kết quả reconciliation.

Không dùng trạng thái database broker làm bằng chứng duy nhất khi provider đã báo lỗi hoặc process từng bị crash. Provider resource state là nguồn quan sát cần thiết để xác định side effect thật.

## 20. Ví dụ kiểm tra precondition trong Spring

Tách việc kiểm tra sử dụng instance khỏi controller OSB:

~~~java
public Mono<UpdateDecision> validatePackageUpdate(
        ServiceInstance instance,
        PackageTarget target) {

    return usageClient.inspect(instance.providerResourceId())
            .flatMap(usage -> {
                if (!target.isSupportedFrom(instance.observedPackageVersion())) {
                    return Mono.just(UpdateDecision.rejected(
                            "Unsupported package upgrade path"));
                }

                if (usage.hasBlockingTransactions()) {
                    return Mono.just(UpdateDecision.waitForMaintenance(
                            "Active transactions must finish"));
                }

                if (usage.activeConnections() > target.maxConnectionsDuringUpgrade()) {
                    return Mono.just(UpdateDecision.waitForDrain(
                            "Too many active connections"));
                }

                return providerClient.checkUpgradePreconditions(
                                instance.providerResourceId(), target)
                        .map(PreconditionResult::toDecision);
            });
}
~~~

Đây là pseudocode minh họa. Các ngưỡng connection và điều kiện transaction phải đến từ provider capability hoặc policy đã được xác định, không tự đặt một giá trị chung cho mọi engine. Việc kiểm tra precondition cần có thời điểm hiệu lực; usage có thể thay đổi ngay sau khi kiểm tra, vì vậy provider vẫn phải thực hiện validation cuối cùng khi bắt đầu update.

## 21. Ví dụ xử lý update async

Application service có thể tạo operation trước rồi để worker chạy:

~~~java
public Mono<UpdateResult> requestUpdate(UpdateCommand command) {
    return instanceRepository.findForUpdate(command.instanceId())
            .switchIfEmpty(Mono.error(new InstanceNotFoundException()))
            .flatMap(instance -> operationRepository
                    .findActive(instance.id(), OperationType.UPDATE)
                    .switchIfEmpty(Mono.defer(() ->
                            operationRepository.createAccepted(
                                    instance.id(),
                                    command.requestFingerprint(),
                                    command.targetPackageVersion()))))
            .map(operation -> UpdateResult.accepted(operation.id()));
}
~~~

Đoạn code chỉ minh họa việc tạo/tra cứu operation; implementation cần unique constraint hoặc lock để hai request đồng thời không tạo hai update. OSB adapter chỉ trả 202 sau khi transaction ghi operation đã commit và request thực sự chấp nhận async.

Worker thực hiện:

~~~java
public Mono<Void> executePackageUpdate(UpdateOperation operation) {
    return providerClient.startOrResumeUpgrade(
                    operation.providerResourceId(),
                    operation.targetVersion(),
                    operation.idempotencyKey())
            .flatMap(job -> operationRepository.saveProviderJob(
                    operation.id(), job.id()))
            .then(providerPoller.awaitCompletion(operation.id()))
            .then(providerClient.verifyPackageVersion(
                    operation.providerResourceId(),
                    operation.targetVersion()))
            .flatMap(verification -> operationRepository.complete(
                    operation.id(), verification));
}
~~~

Trong thực tế, cần xử lý timeout sau provider accept, retry, lease, callback, error classification và recovery khi provider job đã tồn tại. Không giữ transaction database trong suốt thời gian poll provider.

## 22. Trả trạng thái OSB đúng với kết quả update

Nếu update chạy đồng bộ và hoàn tất, broker trả response update thành công theo OSB. Nếu được chấp nhận bất đồng bộ, trả 202 cùng operation ID. Nền tảng truy vấn last_operation; endpoint này trả HTTP 200 với state in progress, succeeded hoặc failed.

Một provider error do instance đang được sử dụng có thể được xử lý theo hai cách:

- Nếu điều kiện có thể tự hết và broker có thể tiếp tục theo policy, giữ operation async ở in progress, mô tả rằng đang chờ consumer drain/maintenance window.
- Nếu request không thể thực hiện và không có cơ chế chờ/retry được chấp nhận, kết thúc operation failed với description an toàn và hướng dẫn cụ thể.

Không để operation ở in progress vô hạn chỉ vì có connection hoạt động. Cần deadline, cancellation/recovery policy và cảnh báo. Không trả succeeded khi provider chỉ mới tiếp nhận update hoặc package chưa được xác minh.

## 23. Những việc không nên làm khi update thất bại

- Không retry PATCH liên tục khi chưa biết provider job cũ đã tạo side effect hay chưa.
- Không xóa binding chỉ để giảm active connection count.
- Không terminate transaction hoặc session mà không đánh giá tác động dữ liệu.
- Không cập nhật observed package version trước khi provider xác nhận.
- Không đánh dấu operation failed nếu provider vẫn đang thực hiện job mà broker chưa truy vấn được.
- Không rollback major engine package nếu provider không hỗ trợ downgrade.
- Không restore backup mà chưa xác định RPO và lượng dữ liệu có thể mất.
- Không mở maintenance window đồng thời cho nhiều update trên cùng instance.
- Không bỏ qua consumer ở shared space hoặc credential được sử dụng ngoài binding đã biết.
- Không log password, token, raw provider response chứa secret hoặc connection string đầy đủ.

## 24. Runbook chẩn đoán theo thứ tự

| Bước | Hành động | Kết quả cần đạt |
|---|---|---|
| 1. Identify | Xác định loại update, instance, source/target version | Không nhầm plan update với package upgrade |
| 2. Freeze duplicate | Chặn operation update cạnh tranh cho instance | Không tạo nhiều provider jobs |
| 3. Capture evidence | Lưu broker/provider operation IDs, error code và timeline | Có thể truy vết cùng một workflow |
| 4. Inspect usage | Kiểm tra binding, active connection, transaction và jobs | Biết chính xác điều kiện đang chặn |
| 5. Validate target | Kiểm tra compatibility, backup, capacity và version path | Biết update có thể tiếp tục an toàn không |
| 6. Choose window | Drain consumer hoặc chọn rolling/online/deferred strategy | Có kế hoạch giảm ảnh hưởng |
| 7. Resume/repair | Tiếp tục job, sửa precondition hoặc recovery theo provider | Không lặp side effect mù quáng |
| 8. Verify | Kiểm tra version, health, replication và consumer reconnect | Xác nhận service thực sự hoạt động |
| 9. Reconcile | Cập nhật broker observed state và terminal operation | Broker/provider state nhất quán |
| 10. Close incident | Ghi nguyên nhân, thời gian gián đoạn và hành động phòng ngừa | Có dữ liệu cải thiện quy trình |

## 25. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
|---|---|
| Instance không có consumer hoạt động | Update có thể bắt đầu khi các precondition khác đạt |
| Có connection idle nhưng provider cho phép online upgrade | Adapter không chặn sai dựa trên connection count đơn thuần |
| Có transaction dài bị provider chặn | Operation chờ hoặc failed theo policy, không kill transaction tự động |
| Có maintenance job khác | Không tạo update job cạnh tranh |
| Source version không được hỗ trợ | Từ chối trước provider side effect |
| Thiếu backup prerequisite | Không bắt đầu migration package |
| Provider timeout sau khi nhận job | Tra cứu job/idempotency key trước retry |
| Package cài một phần | State chuyển recovery/reconciliation, không báo success |
| Provider hoàn tất nhưng broker restart | Worker mới verify version và hoàn tất operation |
| Một consumer không reconnect được | Không đánh dấu rollout hoàn tất cho đến khi xử lý |
| Nhiều binding ở nhiều space | Tất cả consumer liên quan được tính vào maintenance plan |
| Update request lặp | Cùng operation được tiếp tục, không tạo job trùng |
| Rollback không được hỗ trợ | Dùng forward recovery hoặc restore theo phê duyệt |
| Plan update và package upgrade khác nhau | Mỗi luồng áp dụng đúng capability và policy |

## 26. Checklist phòng ngừa

- [ ] Phân biệt plan update, provider package upgrade và broker deployment.
- [ ] Lưu source version và desired target version.
- [ ] Có compatibility matrix và đường nâng cấp được hỗ trợ.
- [ ] Kiểm tra backup/restore trước thay đổi có rủi ro dữ liệu.
- [ ] Theo dõi binding, connection, transaction, replication và background job.
- [ ] Có maintenance window và quy trình thông báo consumer.
- [ ] Hỗ trợ rolling/online upgrade nếu provider cho phép.
- [ ] Có idempotency key, operation store và provider job mapping.
- [ ] Có timeout, retry policy và recovery cho partial update.
- [ ] Xác minh package version, health và consumer reconnect trước khi báo thành công.
- [ ] Có reconciliation sau restart hoặc provider timeout.
- [ ] Có audit, metric và cảnh báo cho operation bị chặn hoặc kéo dài.

## 27. Trình tự triển khai cho service broker

Để xử lý cập nhật gói khi instance đang được sử dụng, có thể triển khai theo trình tự:

1. Chuẩn hóa model update để phân biệt plan change với package maintenance.
2. Lưu owner, binding và consumer context để xác định phạm vi ảnh hưởng.
3. Tích hợp provider usage inspection cho connection, transaction, replication và maintenance state.
4. Kiểm tra compatibility, backup, capacity và maintenance policy trước side effect.
5. Thiết kế async operation có idempotency, provider job ID, checkpoint và deadline.
6. Hỗ trợ drain consumer hoặc chiến lược rolling/blue-green khi provider cho phép.
7. Xử lý partial update bằng recovery workflow, không tự downgrade khi chưa được hỗ trợ.
8. Verify observed package version và service health trước khi hoàn tất.
9. Đồng bộ broker state, OSB last_operation và provider state.
10. Kiểm thử active workload, timeout, retry, restart, partial migration và consumer reconnect.

Một lần cập nhật thất bại khi instance đang được dùng không nên dẫn đến retry mù quáng hoặc thu hồi quyền của consumer. Broker cần xác định loại update, hiểu chính xác provider đang bị chặn ở đâu, bảo vệ dữ liệu và connection hiện có, rồi tiếp tục trong maintenance window hoặc chiến lược nâng cấp phù hợp. Khi operation state, provider job và observed package version được lưu riêng và đối soát, broker có thể phục hồi có kiểm soát mà không báo thành công giả hoặc làm mất dấu tài nguyên đang phục vụ.
