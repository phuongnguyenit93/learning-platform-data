# Thu hồi lặp lại, instance không còn tồn tại và phản hồi phù hợp

Deprovision là thao tác yêu cầu service broker thu hồi một service instance đã được cấp phát. Trong thực tế, request có thể được gửi nhiều lần: nền tảng timeout dù broker đã xóa tài nguyên, worker hoàn tất cleanup nhưng chết trước khi ghi trạng thái, hoặc người vận hành chạy lại thao tác sau khi không nhận được kết quả. Broker phải xử lý những lần gọi lặp sao cho không tạo lỗi giả, không xóa nhầm tài nguyên và không để nền tảng hiểu sai trạng thái instance.

Với module SPRING_CLOUD_SERVICE_BROKER, deprovision cần được thiết kế theo hướng idempotent. Cùng một yêu cầu thu hồi có thể được gửi lại mà kết quả cuối cùng vẫn là instance đã được thu hồi. Khi instance không còn tồn tại, broker cần nhận diện đây là trạng thái đã đạt được và trả phản hồi phù hợp với hợp đồng Open Service Broker API (OSB API). Khi thao tác chưa hoàn tất, broker phải lưu operation, tiếp tục cleanup an toàn và báo tiến độ theo cơ chế bất đồng bộ nếu được hỗ trợ.

## 1. Hợp đồng deprovision của OSB

Nền tảng gọi thao tác deprovision bằng HTTP DELETE trên service instance:

    DELETE /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}
    X-Broker-API-Version: 2.17
    Authorization: Basic ...

Các định danh có vai trò khác nhau:

| Giá trị | Ý nghĩa | Cách broker sử dụng |
|---|---|---|
| instance_id | Định danh instance trong broker | Tra cứu bản ghi và tài nguyên cần thu hồi |
| service_id | Service definition mà instance thuộc về | Đối chiếu với dữ liệu đã lưu |
| plan_id | Plan mà instance đã được tạo theo | Kiểm tra tính nhất quán và áp dụng cleanup phù hợp |
| accepts_incomplete | Cho biết nền tảng có chấp nhận thao tác bất đồng bộ hay không | Quyết định có thể trả accepted operation khi cleanup chưa xong |

Broker phải xác thực caller và kiểm tra các định danh trước khi xóa. Không dùng service_id hoặc plan_id từ query string làm nguồn duy nhất để chọn tài nguyên backend. Bản ghi instance đã lưu mới là nguồn có thẩm quyền về tenant, resource reference, plan hiện tại và các binding liên quan.

Các phản hồi thường gặp của deprovision:

| HTTP response | Ý nghĩa | Hành vi của nền tảng |
|---|---|---|
| 200 OK | Thu hồi đã hoàn tất đồng bộ | Có thể xem instance đã được deprovision |
| 202 Accepted | Broker đã nhận thao tác và đang xử lý bất đồng bộ | Nền tảng truy vấn last operation theo operation key |
| 410 Gone | Instance đã được thu hồi hoặc không còn tồn tại theo ngữ nghĩa deprovision của OSB | Nền tảng có thể xem instance đã biến mất và ngừng gửi lại yêu cầu thu hồi |

Phản hồi lỗi khác phải được ánh xạ theo phiên bản OSB và framework mà broker công bố hỗ trợ. Không trả 200 khi cleanup còn đang chạy; không trả 202 nếu broker không lưu operation đủ bền vững để tiếp tục sau khi tiến trình khởi động lại. Với instance đã biến mất, 410 Gone là tín hiệu giao thức hữu ích để nền tảng kết thúc vòng đời instance thay vì tiếp tục retry một tài nguyên không còn tồn tại.

## 2. Idempotency của thao tác thu hồi

Một thao tác là idempotent khi thực hiện một lần hay nhiều lần đều đưa hệ thống đến cùng trạng thái cuối. Với deprovision, trạng thái cuối mong muốn là:

- Tài nguyên thuộc instance đã được thu hồi hoặc được xác nhận là không còn tồn tại.
- Các binding và credential cần thu hồi đã được xử lý theo chính sách.
- Broker không còn xem instance là active.
- Reservation/quota được giải phóng đúng một lần về mặt hiệu lực.
- Các request lặp không tạo thêm lỗi hoặc tác dụng phụ nguy hiểm.

Idempotency không có nghĩa mọi lần gọi đều phải trả cùng một mã HTTP. Lần đầu có thể trả 202 vì cleanup đang chạy; lần gọi sau có thể trả 202 cùng operation đang hoạt động; sau khi hoàn tất, request lặp có thể nhận 410 Gone. Điều cần giữ nhất quán là trạng thái cuối và ý nghĩa mà nền tảng nhận được.

Ví dụ:

| Lần gọi | Trạng thái broker/backend | Hành vi phù hợp |
|---|---|---|
| DELETE lần đầu | Instance đang active, cleanup hoàn tất nhanh | Cleanup và trả 200 |
| DELETE lần đầu | Instance active, cleanup kéo dài | Lưu operation và trả 202 nếu request cho phép async |
| DELETE lặp khi operation đang chạy | Đã có operation deprovision cho instance | Không tạo operation xóa thứ hai; trả trạng thái operation đang chạy theo hợp đồng |
| DELETE sau khi cleanup hoàn tất | Instance đã được xác nhận không còn | Trả 410 Gone theo semantics deprovision |
| DELETE sau timeout nhưng backend đã xóa tài nguyên | State store chưa kịp cập nhật | Reconcile backend, hoàn tất state và trả kết quả phù hợp |

Nếu một request lặp được xử lý như một thao tác mới mà không kiểm tra trạng thái hiện tại, broker có thể gửi nhiều lệnh delete, giải phóng quota nhiều lần hoặc xóa nhầm tài nguyên được tạo lại với cùng tên.

## 3. Phân biệt instance không tồn tại và lỗi tra cứu tạm thời

Không phải mọi trường hợp repository không trả về bản ghi đều có cùng ý nghĩa. Broker cần phân biệt:

| Tình huống | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Instance đã deprovision và có tombstone | Broker biết instance đã được thu hồi | Trả 410 Gone |
| Instance chưa từng tồn tại trong phạm vi broker | Không có bản ghi hoặc dấu vết hợp lệ | Áp dụng semantics not-found của OSB, thường kết thúc deprovision theo trạng thái đã biến mất nếu xác định chắc chắn |
| Bản ghi tạm thời không đọc được | Database timeout, lỗi kết nối hoặc lỗi replica | Không kết luận instance đã biến mất; trả lỗi phụ thuộc phù hợp để nền tảng retry |
| Bản ghi có nhưng backend resource không tồn tại | Tài nguyên đã bị xóa ngoài broker hoặc cleanup trước đó thành công | Reconcile, đánh dấu đã thu hồi và trả kết quả deprovision phù hợp |
| Backend không truy cập được | Chưa xác định tài nguyên còn hay mất | Giữ operation/state để retry hoặc báo lỗi tạm thời |
| ID thuộc tenant/caller khác | Caller không có quyền trên instance | Từ chối theo chính sách authorization, không tiết lộ dữ liệu của tenant khác |

Điểm mấu chốt là không biến lỗi hạ tầng thành “instance không tồn tại”. Ví dụ, repository timeout không chứng minh bản ghi đã bị xóa; Kubernetes API trả 503 không chứng minh pod hoặc volume đã biến mất. Chỉ trả trạng thái đã thu hồi khi broker có đủ bằng chứng từ state store hoặc backend.

Nếu broker lưu tombstone, tombstone nên giữ tối thiểu instance ID, service ID, tenant scope cần thiết, operation ID cuối cùng, thời điểm hoàn tất và kết quả cleanup. Không cần giữ lại secret hoặc toàn bộ parameters. Tombstone giúp phân biệt một instance đã xóa với một ID hoàn toàn không được biết đến và hỗ trợ trả lời request lặp.

## 4. State machine cho deprovision

Một state machine rõ ràng giúp xử lý request lặp và phục hồi sau lỗi:

    ACTIVE
      -> DEPROVISION_REQUESTED
      -> DEPROVISIONING
      -> DEPROVISIONED

Các nhánh lỗi có thể được biểu diễn như sau:

    DEPROVISIONING
      -> DEPROVISION_RETRYABLE
      -> DEPROVISIONING

    DEPROVISIONING
      -> DEPROVISION_FAILED
      -> RECONCILING
      -> DEPROVISIONING hoặc DEPROVISIONED

Ý nghĩa trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| ACTIVE | Instance đang hoạt động và có thể nhận yêu cầu deprovision |
| DEPROVISION_REQUESTED | Broker đã ghi nhận yêu cầu, chưa bắt đầu cleanup |
| DEPROVISIONING | Worker hoặc tiến trình đồng bộ đang thu hồi tài nguyên |
| DEPROVISION_RETRYABLE | Gặp lỗi tạm thời, có thể tiếp tục |
| DEPROVISION_FAILED | Không thể hoàn tất tự động; cần phân loại hoặc can thiệp |
| RECONCILING | Đối chiếu trạng thái broker với backend sau lỗi hoặc timeout |
| DEPROVISIONED | Đã xác nhận tài nguyên được thu hồi hoặc không còn tồn tại |

Không nhất thiết phải dùng đúng tên trạng thái trên. Điều cần có là phân biệt “đang xóa”, “lỗi có thể thử lại”, “cần đối soát” và “đã xóa chắc chắn”. Nếu chỉ có một cờ boolean deleted, broker khó biết lần gọi lặp nên tiếp tục cleanup, trả operation hiện có hay kết thúc bằng 410.

## 5. Lưu operation trước khi thực hiện cleanup

Với cleanup bất đồng bộ, broker cần ghi nhận operation bền vững trước khi trả 202. Bản ghi operation nên chứa:

| Trường | Mục đích |
|---|---|
| operationId | Định danh duy nhất cho lần thu hồi được chấp nhận |
| instanceId | Instance cần thu hồi |
| operationType | DEPROVISION |
| status | PENDING, IN_PROGRESS, SUCCEEDED hoặc FAILED |
| attempt | Số lần worker đã thử |
| idempotencyKey | Khóa nhận diện request lặp nếu có |
| startedAt/completedAt | Thời điểm bắt đầu và hoàn tất |
| lastErrorCode | Mã lỗi đã chuẩn hóa, không lưu secret |
| version | Phiên bản bản ghi để kiểm soát cập nhật cạnh tranh |

Khi nhận DELETE đầu tiên, application service nên dùng transaction để:

1. Khóa hoặc kiểm tra version của instance.
2. Xác nhận không có operation vòng đời khác đang chạy.
3. Tạo operation deprovision.
4. Chuyển instance sang DEPROVISION_REQUESTED hoặc DEPROVISIONING.
5. Ghi outbox event để worker nhận việc.
6. Commit transaction.

Worker đọc outbox, nhận operation và thực hiện cleanup. Nếu broker chết sau khi commit nhưng trước khi gửi message, outbox vẫn còn để worker xử lý sau khi khởi động lại. Nếu broker trả 202 trước khi lưu operation, nền tảng có thể polling một operation key mà broker không thể tìm thấy.

## 6. Xử lý request lặp khi operation đang chạy

Khi một DELETE khác đến trong lúc instance đã ở DEPROVISION_REQUESTED hoặc DEPROVISIONING, broker cần tìm operation đang hoạt động thay vì tạo một operation mới.

Một quy tắc xử lý:

1. Tra cứu instance theo ID và xác định tenant/caller.
2. Nếu instance có operation deprovision đang hoạt động, trả lại kết quả chấp nhận/operation tương ứng theo khả năng của framework và hợp đồng OSB.
3. Không phát thêm lệnh cleanup song song cho cùng một resource reference.
4. Nếu operation đã hoàn tất và instance có tombstone, trả 410 Gone.
5. Nếu operation thất bại tạm thời, tiếp tục cùng operation hoặc tạo lần thử mới có liên kết với operation trước theo chính sách.

Ví dụ pseudocode:

    public Mono<DeprovisionDecision> requestDeprovision(
            String instanceId,
            CallerContext caller) {

        return repository.findById(instanceId)
                .flatMap(instance -> accessPolicy.verify(caller, instance)
                        .then(Mono.defer(() -> {
                            if (instance.status() == DEPROVISIONED) {
                                return Mono.just(DeprovisionDecision.gone());
                            }
                            if (instance.status() == DEPROVISIONING) {
                                return operationRepository
                                        .findActiveDeprovision(instanceId)
                                        .map(DeprovisionDecision::inProgress);
                            }
                            return startDeprovision(instance);
                        })))
                .switchIfEmpty(repository.findTombstone(instanceId)
                        .map(ignored -> DeprovisionDecision.gone())
                        .defaultIfEmpty(DeprovisionDecision.notFound()));
    }

Đây là pseudocode mô tả quyết định nghiệp vụ, không phải implementation hoàn chỉnh. Cần xử lý lỗi repository riêng để tránh switchIfEmpty bị hiểu nhầm thành lỗi truy cập database. Trong môi trường nhiều replica, việc đọc trạng thái rồi tạo operation phải được bảo vệ bằng transaction, unique constraint hoặc optimistic locking; kiểm tra trong bộ nhớ không đủ để ngăn hai request đồng thời.

## 7. Cleanup tài nguyên theo thứ tự và có thể chạy lại

Một service instance có thể sở hữu nhiều tài nguyên:

- Database hoặc cluster database.
- Volume và snapshot.
- Secret, user, role và credential.
- Network policy, firewall rule hoặc endpoint.
- Backup schedule và monitoring registration.
- Binding hoặc quyền truy cập của ứng dụng.

Cleanup nên được chia thành các bước có định danh ổn định. Ví dụ:

| Bước | Tác vụ | Điều kiện hoàn tất |
|---|---|---|
| 1 | Ngăn instance nhận operation mới | Instance được đánh dấu đang deprovision |
| 2 | Thu hồi binding/credential theo chính sách | Binding không còn quyền truy cập |
| 3 | Xóa workload hoặc database resource | Backend xác nhận tài nguyên không còn |
| 4 | Xóa volume/snapshot/network phụ thuộc nếu thuộc quyền sở hữu instance | Tài nguyên phụ thuộc đã được xử lý |
| 5 | Xóa hoặc thu hồi secret | Không còn credential có hiệu lực |
| 6 | Giải phóng quota/reservation | Usage được cập nhật đúng một lần |
| 7 | Ghi tombstone và hoàn tất operation | State store ghi nhận DEPROVISIONED |

Thứ tự thực tế phụ thuộc loại dịch vụ. Một số tài nguyên cần giữ snapshot trước khi xóa; một số credential phải bị thu hồi sớm để chặn truy cập trong lúc cleanup. Broker cần định nghĩa thứ tự theo dependency graph và chính sách lưu giữ dữ liệu.

Mỗi bước phải an toàn khi chạy lại. Nếu xóa secret lần đầu thành công nhưng worker timeout trước khi ghi checkpoint, lần thử sau cần coi “secret đã không còn” là kết quả đạt được. Không coi resource not found từ backend là lỗi nghiêm trọng nếu mục tiêu của bước là bảo đảm resource không tồn tại và broker xác minh đúng resource reference.

Không xóa tài nguyên chỉ dựa vào tên do client cung cấp. Dùng resource ID hoặc metadata ownership do broker tạo, ví dụ instance ID, broker ID và operation ID. Điều này tránh xóa nhầm tài nguyên dùng chung hoặc tài nguyên của instance khác có tên tương tự.

## 8. Xử lý lỗi một phần và reconcile

Deprovision hiếm khi là một lệnh xóa đơn giản. Có thể database đã bị xóa nhưng volume vẫn còn; secret đã thu hồi nhưng network rule chưa xóa; backend trả timeout dù thao tác đã thành công.

Broker nên lưu checkpoint cho từng nhóm tài nguyên hoặc bước cleanup:

    {
      "instanceId": "instance-123",
      "operationId": "deprovision-op-456",
      "steps": {
        "revokeBindings": "SUCCEEDED",
        "deleteDatabase": "SUCCEEDED",
        "deleteVolume": "RETRYABLE",
        "deleteSecrets": "PENDING"
      }
    }

Đây là dữ liệu minh họa. State store thật nên dùng cấu trúc có kiểu và kiểm soát version. Khi worker chạy lại, nó chỉ tiếp tục bước chưa hoàn tất hoặc đối chiếu lại những bước có kết quả không chắc chắn.

Reconcile cần phân biệt:

- Backend xác nhận resource tồn tại: tiếp tục xóa.
- Backend xác nhận resource không tồn tại: đánh dấu bước cleanup thành công.
- Backend không truy cập được: giữ trạng thái retryable, không kết luận đã xóa.
- Backend trả lỗi quyền: dừng retry tự động nếu credential hoặc policy cần sửa.
- Backend trả lỗi xung đột: đọc lại trạng thái và xác định có thể tiếp tục hay cần can thiệp.

Không đánh dấu instance DEPROVISIONED chỉ vì database broker đã xóa bản ghi chính. Trạng thái hoàn tất cần dựa trên chính sách cleanup và bằng chứng rằng các tài nguyên thuộc phạm vi thu hồi đã được xử lý.

## 9. Idempotency ở infrastructure adapter

Application service có thể bảo đảm một operation đang hoạt động cho mỗi instance, nhưng adapter cũng cần chịu được retry. Một số kỹ thuật:

- Dùng resource ID ổn định để gọi delete; tránh tạo resource name mới mỗi lần thử.
- Trước khi xóa, tra cứu resource theo ownership metadata của broker.
- Coi phản hồi “not found” là thành công nếu xác định đúng resource đích và mục tiêu là bảo đảm resource không còn.
- Gửi idempotency key hoặc operation ID đến backend nếu API hỗ trợ.
- Lưu checkpoint sau từng bước có tác dụng phụ.
- Không retry vô hạn lỗi authorization, validation hoặc resource conflict không thể tự khắc phục.
- Dùng backoff và jitter cho lỗi tạm thời như rate limit hoặc service unavailable.

Ví dụ adapter giả định:

    public Mono<CleanupResult> deleteDatabase(
            String resourceId,
            String instanceId,
            String operationId) {

        return databaseClient.delete(resourceId, operationId)
                .thenReturn(CleanupResult.deleted())
                .onErrorResume(DatabaseNotFoundException.class,
                        error -> verifyOwnershipTombstone(resourceId, instanceId)
                                .thenReturn(CleanupResult.alreadyAbsent()));
    }

Adapter chỉ được coi not found là thành công sau khi xác minh resource ID thuộc instance đang xử lý. Nếu resource ID sai hoặc không thể xác minh quyền sở hữu, không được bỏ qua lỗi vì có nguy cơ xóa nhầm hoặc che giấu lỗi ánh xạ.

## 10. Phản hồi đồng bộ và bất đồng bộ

Nếu cleanup hoàn tất trong request và broker đã cập nhật state, có thể trả 200 OK. Nếu cleanup kéo dài và nền tảng gửi accepts_incomplete=true, broker có thể lưu operation và trả 202 Accepted kèm operation key theo hợp đồng OSB.

Nếu nền tảng không chấp nhận thao tác bất đồng bộ, broker không nên trả 202. Khi không thể hoàn tất trong chế độ đồng bộ, hãy trả lỗi phù hợp với quy tắc OSB/framework cho trường hợp thao tác cần async nhưng request không cho phép; không tự tạo response thành công giả.

Một luồng async:

    Platform -> Broker: DELETE service instance
    Broker -> State store: Ghi DEPROVISIONING + operation
    Broker -> Platform: 202 Accepted + operation key
    Worker -> Infrastructure: Thu hồi từng tài nguyên
    Infrastructure -> Worker: Kết quả từng bước
    Worker -> State store: Cập nhật checkpoint và operation
    Platform -> Broker: GET last_operation
    Broker -> Platform: IN_PROGRESS hoặc SUCCEEDED
    Worker -> State store: Ghi DEPROVISIONED + tombstone

Khi operation thành công, endpoint last operation trả trạng thái hoàn tất theo OSB. Request DELETE lặp sau đó có thể nhận 410 Gone. Không dùng response 202 cho một operation không có worker/reconciler chịu trách nhiệm tiếp tục.

## 11. Giải phóng quota và cập nhật trạng thái đúng một lần

Deprovision thường giải phóng quota hoặc reservation mà instance đang chiếm dụng. Nếu request lặp khiến broker trừ usage nhiều lần, quota của tenant có thể bị sai. Cần gắn việc giải phóng với operation hoặc một transition trạng thái có tính nguyên tử.

Một cách thực hiện:

1. Khi instance chuyển sang DEPROVISIONING, đánh dấu quota allocation đang chờ giải phóng.
2. Chỉ sau khi cleanup đạt điều kiện hoàn tất, chuyển allocation sang RELEASED.
3. Dùng unique key theo instance/allocation để thao tác release có thể chạy lặp mà không trừ usage lần thứ hai.
4. Cập nhật instance, operation, allocation và tombstone trong transaction phù hợp.
5. Nếu quota service độc lập, dùng outbox/inbox hoặc idempotency key để đồng bộ eventual consistency.

Không giải phóng quota ngay khi bắt đầu DELETE nếu backend có thể thất bại và instance vẫn còn tài nguyên. Nếu sản phẩm cần giữ quota trong lúc cleanup, state phải thể hiện rõ reservation đang được giải phóng. Sau khi xác nhận resource không còn, broker mới chốt usage về trạng thái đã giải phóng.

## 12. Giữ tombstone và chính sách lưu trữ

Tombstone là dấu vết tối thiểu cho biết một instance đã được thu hồi. Nó hỗ trợ xử lý request lặp, điều tra sự cố và tránh tạo lại operation không cần thiết.

Một tombstone có thể chứa:

- Instance ID và service ID.
- Tenant scope hoặc khóa tham chiếu đã được bảo vệ.
- Operation ID cuối cùng.
- Thời điểm deprovision hoàn tất.
- Kết quả cleanup và phiên bản trạng thái.

Không lưu password, token, private key hoặc toàn bộ parameters vào tombstone. Thời gian lưu tombstone cần cân bằng giữa khả năng nhận diện request lặp, yêu cầu kiểm toán và chính sách lưu trữ dữ liệu. Khi tombstone hết hạn, broker vẫn cần có cách xử lý an toàn nếu một DELETE cũ xuất hiện; không được suy ra resource ID backend chỉ từ instance ID tùy ý.

Nếu instance ID có thể được tái sử dụng, cần có generation hoặc internal resource identity để tombstone cũ không ảnh hưởng đến instance mới. Thực tế thường đơn giản hơn nếu instance ID được coi là duy nhất và không tái sử dụng trong suốt vòng đời hệ thống.

## 13. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp extension point cho deprovision trong service xử lý vòng đời instance, thường là ServiceInstanceService. Handler nhận request model của framework, chuyển thành command và trả kết quả theo kiểu response mà phiên bản thư viện yêu cầu.

Application service nên chịu trách nhiệm:

- Xác minh caller và quyền trên instance.
- Đối chiếu service ID, plan ID và tenant với bản ghi đã lưu.
- Phát hiện instance đã deprovision hoặc operation đang chạy.
- Tạo hoặc tìm operation idempotent.
- Điều phối cleanup và reconcile.
- Cập nhật state, quota allocation và tombstone.
- Chọn kết quả nghiệp vụ để OSB adapter ánh xạ thành 200, 202 hoặc 410 theo hợp đồng.

Không đặt toàn bộ logic cleanup trong controller hoặc trực tiếp trong method handler. Cách đó khiến retry, worker và thao tác vận hành khó dùng chung logic. Cũng không để infrastructure adapter tự tạo HTTP response OSB; adapter chỉ trả kết quả kỹ thuật đã chuẩn hóa.

## 14. Kiểm thử deprovision lặp và phản hồi

Các test cần bao phủ cả kết quả giao thức và trạng thái backend:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| DELETE instance active, cleanup hoàn tất đồng bộ | Trả 200 và state chuyển DEPROVISIONED |
| DELETE instance active, cleanup cần async và request cho phép | Trả 202, operation được lưu bền vững |
| DELETE lặp trong khi operation đang chạy | Không tạo operation cleanup song song |
| DELETE sau khi instance đã deprovision | Trả 410 Gone theo semantics OSB |
| Backend đã xóa resource nhưng worker timeout | Retry/reconcile xác nhận resource vắng mặt và tiếp tục |
| Repository timeout | Không kết luận instance đã bị xóa |
| Backend API unavailable | Operation được giữ để retry hoặc trả lỗi tạm thời phù hợp |
| Một bước cleanup thành công, bước tiếp theo thất bại | Checkpoint giữ kết quả; retry không lặp tác dụng phụ nguy hiểm |
| Quota release được gửi hai lần | Usage chỉ được giải phóng một lần về mặt hiệu lực |
| Hai DELETE đồng thời | Chỉ một operation deprovision hoạt động cho instance |
| Instance ID thuộc tenant khác | Không tiết lộ thông tin và không xóa tài nguyên |
| Tombstone đã tồn tại | Request lặp được nhận diện mà không gọi backend delete mới |

Nên dùng integration test với repository thật hoặc database test để kiểm tra unique constraint, optimistic locking và transaction. Adapter test cần mô phỏng cả phản hồi delete thành công, not found, timeout sau khi backend đã xóa và lỗi quyền. Contract test xác nhận response HTTP và body operation key đúng phiên bản OSB.

## 15. Những sai lầm thường gặp

- Trả 404 hoặc 500 cho mọi lần DELETE lặp dù instance đã được thu hồi.
- Trả 200 ngay khi mới ghi nhận yêu cầu, trong khi cleanup chưa hoàn tất.
- Trả 202 nhưng không lưu operation bền vững.
- Tạo một operation mới cho mỗi request lặp.
- Coi database timeout hoặc backend unavailable là bằng chứng instance không tồn tại.
- Xóa bản ghi broker trước khi có đủ thông tin để thu hồi resource backend.
- Coi mọi lỗi not found từ adapter là thành công mà không xác minh ownership.
- Giải phóng quota nhiều lần hoặc quá sớm.
- Không giữ tombstone nên không phân biệt được instance đã xóa với ID chưa từng tồn tại.
- Cho phép hai worker xóa cùng tài nguyên mà không có khóa hoặc checkpoint.

## Kết luận

Thu hồi lặp lại là tình huống bình thường trong hệ thống phân tán vì request và response có thể bị mất, timeout hoặc được retry. Service broker cần làm cho deprovision idempotent từ application service đến từng infrastructure adapter: nhận diện operation đang chạy, xác minh tài nguyên thực tế, coi resource đã vắng mặt là trạng thái đạt được khi ownership được xác nhận và giải phóng quota đúng một lần. Với OSB, 200 biểu thị cleanup đồng bộ đã hoàn tất, 202 biểu thị operation bất đồng bộ đã được lưu và tiếp nhận, còn 410 Gone cho biết instance đã không còn và nền tảng có thể kết thúc việc thu hồi. State machine, checkpoint, tombstone và reconcile giúp broker duy trì trạng thái nhất quán ngay cả khi nhiều request DELETE đến cùng lúc hoặc worker gặp lỗi giữa chừng.
