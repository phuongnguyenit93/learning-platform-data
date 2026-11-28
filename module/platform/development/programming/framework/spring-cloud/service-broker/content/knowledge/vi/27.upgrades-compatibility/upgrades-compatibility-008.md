# Kiểm thử hồi quy, triển khai từng phần và kế hoạch khôi phục phiên bản

Nâng cấp một service broker không chỉ là thay image hoặc cập nhật thư viện Spring. Broker lưu trạng thái service instance, binding, operation và provider resource; đồng thời platform gọi broker qua hợp đồng Open Service Broker API (OSB API). Một phiên bản mới có thể chạy đúng với request mới nhưng làm hỏng operation đang xử lý, đọc sai dữ liệu cũ, thay đổi catalog theo cách platform không tương thích hoặc khiến worker cũ và worker mới xử lý cùng một message.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, việc nâng cấp cần bảo toàn nhiều ranh giới cùng lúc: OSB API, catalog và plan, database schema, message/outbox payload, provider API, credentials, cấu hình runtime và hành vi của Cloud Foundry hoặc Kubernetes. Spring Cloud Open Service Broker (SCOSB) cung cấp service abstraction và model giao tiếp; ứng dụng broker chịu trách nhiệm giữ tương thích giữa các phiên bản triển khai và dữ liệu nghiệp vụ.

Bài học này trình bày cách lập kế hoạch regression, đánh giá tương thích, triển khai rolling/canary/blue-green, thay đổi database theo expand-contract, bảo vệ operation đang chạy, quyết định rollback hay roll-forward và diễn tập phục hồi. Mục tiêu là phát hành từng phần mà vẫn giữ được khả năng provision, update, bind, unbind, deprovision và polling operation.

## 1. Vì sao nâng cấp broker có rủi ro riêng?

Một ứng dụng web thông thường có thể triển khai phiên bản mới rồi kiểm tra trang chủ. Broker có thêm side effect bên ngoài: một request có thể tạo database, cấp user, tạo bucket hoặc xóa namespace. Những thay đổi này không tự biến mất khi rollback ứng dụng.

Ví dụ:

1. Broker phiên bản A nhận provision request và lưu operation.
2. Worker phiên bản A gọi provider tạo database.
3. Provider tạo thành công nhưng response bị timeout.
4. Broker được nâng cấp lên phiên bản B.
5. Worker phiên bản B đọc lại operation chưa hoàn tất.
6. Nếu B hiểu sai payload hoặc state cũ, nó có thể tạo database thứ hai hoặc đánh dấu operation sai.

Do đó, một bản nâng cấp an toàn phải xét cả trạng thái đã tồn tại trước khi deploy và trạng thái có thể được tạo ra trong lúc rollout.

Các rủi ro chính:

- Platform tiếp tục gửi request theo OSB API version cũ.
- Catalog mới đổi service ID, plan ID hoặc capability mà platform đang dùng.
- Database migration không tương thích với replica cũ còn chạy.
- Worker phiên bản mới không đọc được message do phiên bản cũ phát ra.
- Worker cũ không hiểu event do phiên bản mới phát ra.
- Operation đang chạy bị xử lý lại hoặc không thể tiếp tục.
- Provider API hoặc credential format thay đổi.
- Rollback code nhưng database đã bị thay đổi không thể đọc ngược.
- Secret/key rotation làm phiên bản cũ mất khả năng giải mã dữ liệu.
- Hai phiên bản cùng chạy một tác vụ định kỳ hoặc cùng claim một operation.

Một deployment chỉ được xem là an toàn khi cả request path, worker path, dữ liệu và provider side effect đều có phương án tương thích.

## 2. Xác định các lớp tương thích trước khi lập kế hoạch

Hãy chia phạm vi nâng cấp thành các lớp. Mỗi lớp cần có câu hỏi kiểm thử và tiêu chí rollback riêng.

| Lớp | Thành phần | Câu hỏi cần trả lời |
|---|---|---|
| OSB contract | Endpoint, HTTP status, headers, request/response | Platform hiện tại có tiếp tục gọi được không? |
| Catalog | Service ID, plan ID, capability, schema | Consumer và platform có hiểu catalog mới không? |
| Database | Instance, binding, operation, outbox, migration | Code cũ và mới có cùng đọc/ghi được schema trong giai đoạn rollout không? |
| Message contract | Queue message, event, outbox payload | Worker cũ và mới có xử lý được payload của nhau không? |
| Provider adapter | Cloud/Kubernetes API, resource metadata | Phiên bản mới có tiếp tục quản lý resource cũ không? |
| Security | Secret reference, encryption key, token, certificate | Cả hai phiên bản có đọc được credential trong giai đoạn chuyển đổi không? |
| Runtime | JDK, Spring Boot, SCOSB, driver, configuration | Dependency và runtime có tương thích không? |
| Platform | Cloud Foundry, Kubernetes, ingress, health probe | Platform có deploy, route và theo dõi broker đúng cách không? |

Tạo một bảng thay đổi cho từng release:

| Thành phần | Phiên bản hiện tại | Phiên bản mới | Tác động | Bằng chứng |
|---|---|---|---|---|
| OSB API | Phiên bản đang hỗ trợ | Giữ hoặc bổ sung | Request contract | Contract test |
| Catalog | Snapshot hiện tại | Snapshot mới | Service/plan/capability | Catalog diff |
| Database | Schema N | Schema N+1 | Read/write compatibility | Migration test |
| Outbox event | Schema 1 | Schema 1 hoặc 2 | Worker compatibility | Consumer contract test |
| Provider API | API version A | API version A/B | Resource operations | Provider contract test |
| Spring/SCOSB | Dependency hiện tại | Dependency mới | Runtime và model | Integration test |

Không bắt đầu rollout khi chưa biết lớp nào thay đổi và phiên bản nào còn phải cùng tồn tại.

## 3. Phân loại thay đổi tương thích và phá vỡ tương thích

Một thay đổi tương thích thường bổ sung hành vi mà consumer cũ có thể bỏ qua. Thay đổi phá vỡ tương thích làm cho consumer hoặc phiên bản broker cũ không còn hoạt động đúng.

| Thay đổi | Đánh giá thường gặp | Cách phát hành |
|---|---|---|
| Thêm field response tùy chọn mà client bỏ qua field lạ | Thường tương thích | Có thể phát hành additive |
| Thêm field request tùy chọn với default an toàn | Có thể tương thích | Kiểm thử client cũ và validation |
| Đổi tên field hoặc kiểu dữ liệu | Phá vỡ tương thích | Giai đoạn chuyển đổi hoặc API version mới |
| Xóa endpoint đang được platform sử dụng | Phá vỡ tương thích | Không xóa trước khi ngừng sử dụng có kiểm chứng |
| Đổi service ID hoặc plan ID | Có tác động lớn | Giữ ID cũ cho instance hiện hữu |
| Đổi ý nghĩa của plan ID hiện có | Phá vỡ tương thích về nghiệp vụ | Tạo plan ID mới |
| Bật capability mới trong catalog | Có thể làm platform gọi endpoint mới | Triển khai và kiểm thử endpoint trước |
| Tắt capability đang dùng | Có thể ảnh hưởng platform/consumer | Deprecation và migration có kế hoạch |
| Thêm cột nullable | Thường tương thích | Expand migration |
| Xóa/đổi tên cột ngay lập tức | Không tương thích với code cũ | Expand-contract qua nhiều release |
| Đổi event payload không có version | Rủi ro cao | Version hóa hoặc thay đổi additive |

Tính tương thích không chỉ phụ thuộc cú pháp. Một response vẫn là JSON hợp lệ nhưng đổi ý nghĩa của field, quota hoặc quyền binding có thể phá vỡ ứng dụng consumer.

Không tái sử dụng service ID hoặc plan ID cho một offering có ý nghĩa khác. Nếu cần thay đổi đáng kể behavior, tạo ID mới và giữ đường xử lý cho instance đã được provision theo ID cũ.

## 4. Giữ ổn định OSB API contract

Platform thường gọi broker theo endpoint OSB API và gửi header phiên bản API. Broker phải duy trì các phiên bản đã cam kết hỗ trợ trong thời gian platform cần chúng.

Trước khi nâng cấp:

- Ghi lại các API version broker đang hỗ trợ.
- Kiểm tra request headers từ platform hiện tại.
- Xác minh behavior khi thiếu header hoặc gửi version không hỗ trợ theo contract.
- So sánh status code, response body và error body trước/sau.
- Kiểm tra endpoint provision, update, deprovision, bind, unbind và last_operation.
- Kiểm tra endpoint retrieval nếu catalog công bố capability tương ứng.
- Không đổi semantics của operation chỉ vì nâng cấp Spring hoặc SCOSB.

Ví dụ request:

~~~http
PUT /v2/service_instances/instance-100?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: 2.17
~~~

Ví dụ contract test cần xác minh header và response theo phiên bản đang được platform sử dụng:

~~~java
@Test
void provisionContractRemainsCompatible() {
    webTestClient.put()
            .uri("/v2/service_instances/instance-100?accepts_incomplete=true")
            .header("X-Broker-API-Version", "2.17")
            .bodyValue(provisionRequest())
            .exchange()
            .expectStatus().isAccepted()
            .expectBody()
            .jsonPath("$.operation").isNotEmpty();
}
~~~

Đây là ví dụ minh họa; API version, authentication, fixture và expected status cần khớp contract thực tế. Nếu provision hoàn tất đồng bộ trong fixture thì test phải kỳ vọng response đồng bộ tương ứng. Không ép mọi request trả 202 chỉ để test đơn giản hơn.

## 5. Kiểm tra catalog và plan trước khi rollout

Catalog là contract mà platform dùng để khám phá service. Hãy lưu snapshot catalog trước và sau release rồi so sánh:

- Service ID và plan ID.
- Service name, description và metadata.
- bindable và plan_updateable.
- instances_retrievable và bindings_retrievable.
- allow_context_updates và các capability tùy chọn.
- requires như syslog drain, route forwarding hoặc volume mount.
- Parameter schemas cho provision, update và binding.
- Maintenance information và các thuộc tính plan có liên quan.

Ví dụ catalog snapshot:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "bindable": true,
      "plan_updateable": true,
      "plans": [
        {
          "id": "plan-standard",
          "name": "standard"
        }
      ]
    }
  ]
}
~~~

Khi release mới thêm capability, endpoint và provider adapter tương ứng phải sẵn sàng trước khi platform nhìn thấy capability đó. Ví dụ chỉ bật bindings_retrievable sau khi GET binding đã đọc đúng secret, kiểm tra quyền và trả response theo contract.

Khi cần ngừng một plan, không xóa logic xử lý instance cũ ngay. Platform có thể không cho tạo instance mới từ plan đó nhưng broker vẫn phải quản lý instance đã tồn tại, bao gồm bind, update theo policy và deprovision.

Một quy tắc hữu ích: **catalog mới không được yêu cầu hành vi mà code mới chưa triển khai, và code mới phải tiếp tục hiểu dữ liệu của các instance cũ**.

## 6. Kiểm thử hồi quy theo luồng nghiệp vụ

Regression suite phải kiểm tra cả hành vi đang hoạt động và các trường hợp lỗi đã được khắc phục trong các release trước.

| Nhóm | Luồng cần kiểm thử | Điều cần giữ ổn định |
|---|---|---|
| Catalog | GET catalog | ID, plan và capability |
| Provision | Tạo instance mới | Validation, state, provider mapping |
| Provision retry | Gửi lại cùng instance request | Idempotency, không tạo resource trùng |
| Update | Đổi parameters hoặc plan | Policy và state transition |
| Deprovision | Xóa instance | Ownership và cleanup |
| Bind | Tạo credentials | Binding ID và secret reference |
| Get binding | Truy xuất nếu hỗ trợ | Authorization và response allowlist |
| Unbind | Thu hồi credentials | Không ảnh hưởng binding khác |
| Async operation | Poll last_operation | Operation ID và trạng thái |
| Recovery | Worker restart/retry | Checkpoint và reconciliation |
| Security | Tenant isolation | Không lộ secret hoặc resource khác |
| Provider failure | Timeout, throttling, 5xx | Retry và error classification |

Các ca regression cần chạy trên dữ liệu đại diện cho phiên bản trước, không chỉ dữ liệu mới tạo. Một test provision mới thành công không chứng minh broker mới đọc được service instance được tạo từ ba release trước.

Mỗi lỗi production đã khắc phục nên có test hồi quy gắn với mã lỗi hoặc issue ID. Nếu không có test, cùng lỗi có thể quay lại trong lần refactor tiếp theo.

## 7. Kiểm thử tương thích với dữ liệu và instance cũ

Tạo fixture từ schema và dữ liệu đại diện cho các phiên bản trước:

- Instance ở trạng thái READY.
- Instance đang PROVISIONING hoặc UPDATING.
- Instance có operation đang chờ provider.
- Binding ACTIVE và binding đã REVOKED.
- Secret reference ở version cũ.
- Instance dùng plan đã ngừng cung cấp cho request mới.
- Operation được ghi bởi event payload version cũ.
- Resource provider có metadata hoặc label cũ.

Kiểm tra phiên bản mới:

1. Đọc record cũ mà không mất field.
2. Hiển thị đúng instance và binding state.
3. Tiếp tục operation đang chạy.
4. Truy xuất đúng provider resource ID.
5. Đọc secret version cũ khi policy vẫn cho phép.
6. Deprovision instance cũ.
7. Không tự động chuyển đổi plan hoặc quyền chỉ vì code mới có default khác.

Nếu phải migrate dữ liệu, hãy xác định rõ record nào được chuyển đổi, record nào giữ nguyên và cách rollback. Migration cần idempotent hoặc có bảng/version marker để tránh chạy lặp gây thay đổi sai.

## 8. Database migration theo mô hình expand-contract

Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy. Vì vậy, migration phải giữ schema tương thích với cả hai phiên bản trong giai đoạn chuyển tiếp.

Mô hình **expand-contract** có ba giai đoạn:

1. **Expand:** thêm cấu trúc mới theo cách code cũ vẫn chạy được.
2. **Migrate:** triển khai code đọc/ghi tương thích, chuyển dữ liệu dần và xác minh.
3. **Contract:** chỉ xóa cấu trúc cũ sau khi mọi replica, worker và tác vụ cần nó đã ngừng sử dụng.

Ví dụ đổi cột provider reference:

~~~text
Release A:
  provider_resource_id

Release B - expand:
  provider_resource_id
  external_resource_ref

Release C - migrate:
  code ghi cả hai field
  code đọc external_resource_ref, fallback field cũ
  backfill dữ liệu cũ

Release D - contract:
  code không còn đọc field cũ
  xác minh mọi record đã có external_resource_ref
  xóa provider_resource_id trong release riêng
~~~

Không rename hoặc drop cột ngay trong cùng release thay code. Replica cũ có thể vẫn truy cập cột đó trong khi rollout chưa hoàn tất.

### Quy tắc migration an toàn

- Migration chỉ thêm cột nullable hoặc có default tương thích khi có thể.
- Tránh thêm NOT NULL vào bảng lớn nếu chưa backfill và kiểm tra.
- Tách DDL nặng khỏi transaction dài nếu database yêu cầu.
- Có lock hoặc migration job để nhiều replica không chạy cùng migration.
- Backfill theo batch, giới hạn tải và có checkpoint.
- Kiểm tra số record đã chuyển đổi.
- Chỉ contract sau khi xác nhận không còn code cũ.
- Không sửa migration đã chạy trên môi trường production; tạo migration mới để điều chỉnh.

## 9. Tương thích với operation, outbox và queue message

Broker có thể đang xử lý operation khi rollout bắt đầu. Worker cũ có thể nhận message mới, worker mới có thể nhận message cũ, và queue có thể giao lại message sau timeout.

Cần version hóa payload:

~~~json
{
  "event_type": "ProvisionRequested",
  "event_version": 1,
  "event_id": "evt-100",
  "operation_id": "op-100",
  "instance_id": "instance-100",
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard"
}
~~~

Nguyên tắc:

- Consumer bỏ qua field mới nếu không ảnh hưởng behavior và contract cho phép.
- Không đổi ý nghĩa field hiện có.
- Field mới cần default hoặc migration logic cho message cũ.
- Event schema có version rõ ràng.
- Producer không phát payload version mới trước khi mọi consumer cần xử lý đã hỗ trợ nó.
- Dead-letter queue phải giữ payload đủ để điều tra nhưng không chứa secret.
- Worker retry cùng operation phải giữ idempotency key ổn định.

Nếu không thể giữ backward compatibility, hãy triển khai consumer hỗ trợ cả version cũ và mới trước; sau đó mới chuyển producer; cuối cùng mới loại bỏ support version cũ sau thời gian retention và khi queue đã drain.

## 10. Bảo vệ operation đang chạy trong lúc nâng cấp

Trước rollout, lấy số liệu operation theo trạng thái:

- QUEUED.
- CLAIMED.
- IN_PROGRESS/PROVISIONING.
- WAITING_PROVIDER.
- RECONCILIATION_REQUIRED.
- SUCCEEDED hoặc FAILED.

Không nhất thiết phải chờ queue trống hoàn toàn, nhưng phải biết phiên bản mới có thể tiếp tục từng trạng thái hay không.

Một quy trình phù hợp:

1. Ngừng nhận operation mới nếu cần bảo trì có kiểm soát.
2. Để worker hiện tại hoàn tất hoặc lưu checkpoint.
3. Chuyển worker cũ sang ngừng claim message mới.
4. Triển khai worker mới đã hỗ trợ schema cũ.
5. Cho worker mới tiếp nhận operation chưa hoàn tất.
6. Theo dõi last_operation và provider state.
7. Chỉ đóng worker cũ khi lease và task của nó đã kết thúc hoặc hết hạn an toàn.

Không kill worker đang gọi provider mà không có cơ chế lease/reconciliation. Nếu response provider mất, worker mới phải tra cứu provider trước khi gọi lại create/update/delete.

Nếu request API vẫn được nhận trong rollout, operation store và outbox phải tương thích với cả hai phiên bản.

## 11. Triển khai rolling update

Rolling update thay dần các replica. Trên Kubernetes, Deployment có thể dùng maxSurge và maxUnavailable để kiểm soát số pod được thêm và số pod được phép unavailable trong quá trình rollout.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-broker
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: service-broker
  template:
    metadata:
      labels:
        app: service-broker
    spec:
      containers:
        - name: broker
          image: example/service-broker:2.4.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
          livenessProbe:
            httpGet:
              path: /livez
              port: http
~~~

Cấu hình này minh họa chiến lược giữ số replica khả dụng trong lúc thay pod. Giá trị thực tế cần xét quota cluster, startup time, readiness và khả năng database chịu thêm connection.

Rolling update phù hợp khi:

- Code mới và cũ tương thích với cùng schema.
- Queue payload tương thích trong cả hai chiều cần thiết.
- Provider adapter không làm thay đổi semantics của operation.
- Nhiều replica có thể cùng chạy mà không xử lý trùng side effect.
- Readiness loại pod mới khỏi traffic cho tới khi sẵn sàng.
- Graceful shutdown cho pod cũ đủ thời gian dừng nhận request và checkpoint worker.

Nếu code mới không thể chạy đồng thời với code cũ, rolling update không phải lựa chọn an toàn cho release đó.

## 12. Canary deployment và kiểm soát phạm vi ảnh hưởng

Canary đưa một phần nhỏ traffic tới phiên bản mới trước khi mở rộng. Với broker, có thể route một tỷ lệ request hoặc một nhóm platform/tenant thử nghiệm tới phiên bản mới, tùy khả năng routing và chính sách dữ liệu.

Quy trình:

1. Deploy một replica hoặc một deployment canary.
2. Kiểm tra health và catalog.
3. Route traffic test hoặc nhóm consumer nội bộ.
4. Theo dõi lỗi OSB, latency, operation failure và provider side effect.
5. So sánh với baseline phiên bản cũ.
6. Mở rộng traffic theo từng bước.
7. Dừng rollout nếu vượt ngưỡng lỗi hoặc có sai lệch state.

Không chỉ theo dõi HTTP 5xx. Một phiên bản mới có thể trả 2xx nhưng ghi sai plan, tạo duplicate resource hoặc làm operation stuck. Metric cần có:

- Tỷ lệ lỗi theo endpoint và phiên bản.
- P95/P99 latency.
- Số operation QUEUED/IN_PROGRESS và thời gian tồn đọng.
- Tỷ lệ operation FAILED/RECONCILIATION_REQUIRED.
- Provider AlreadyExists và timeout.
- Outbox/queue backlog.
- Database pool exhaustion.
- Tỷ lệ binding/revoke lỗi.
- Số instance state không nhất quán.

Canary phải dùng dữ liệu và provider account có phạm vi được kiểm soát. Không thử nghiệm destructive operation trên tenant production nếu chưa có kế hoạch bảo vệ.

## 13. Blue-green deployment

Blue-green duy trì hai môi trường triển khai:

- Blue là phiên bản đang phục vụ.
- Green là phiên bản mới được triển khai và kiểm tra trước khi chuyển traffic.

Sau khi green đạt readiness và kiểm thử smoke, router chuyển traffic sang green. Blue có thể được giữ lại trong thời gian ngắn để rollback.

Với broker, cần chú ý:

- Hai môi trường có thể cùng truy cập một database.
- Không để cả blue và green cùng chạy migration phá vỡ tương thích.
- Không để hai worker fleet cùng claim operation nếu không có lease/lock đúng.
- Không chạy scheduled reconciliation hai lần nếu job không idempotent.
- Không phát hai lần cùng event do cả hai outbox publisher cùng xử lý.
- Không chuyển traffic trước khi green hiểu được dữ liệu và message hiện tại.

Có thể chỉ chạy worker ở một fleet tại một thời điểm, hoặc dùng distributed lease/consumer group được thiết kế cho nhiều replica. Việc chuyển traffic HTTP không tự động chuyển ownership của background job.

Blue-green hữu ích khi cần chuyển traffic nhanh, nhưng không phải rollback toàn bộ hệ thống nếu green đã thay đổi database hoặc tạo side effect provider.

## 14. Feature flag cho thay đổi có rủi ro

Feature flag cho phép deploy code mới nhưng bật hành vi mới theo từng bước. Với broker, flag có thể kiểm soát:

- Dùng provider API adapter mới.
- Đọc field database mới.
- Ghi dual-write trong giai đoạn migration.
- Bật một capability catalog sau khi endpoint đã sẵn sàng.
- Chuyển một nhóm tenant sang provider region mới.
- Bật workflow reconciliation mới.
- Thay đổi chiến lược tạo binding credential.

Feature flag cần có owner, default, scope và ngày loại bỏ. Không để flag cũ tồn tại vô thời hạn vì code path tăng độ phức tạp.

Nếu flag ảnh hưởng catalog, cần cân nhắc catalog là metadata dùng chung cho platform. Không bật/tắt capability theo từng request nếu platform chỉ nhận một catalog chung mà không phân biệt tenant. Khi cần rollout theo tenant, có thể cần broker registration/catalog riêng hoặc cơ chế platform được hỗ trợ.

Flag không thay thế schema compatibility. Code mới phải an toàn ngay cả khi flag đang OFF và phiên bản cũ vẫn chạy.

## 15. Kế hoạch rollback phải xét database và provider

Rollback ứng dụng chỉ đổi code/image về phiên bản trước. Nó không tự động:

- Hoàn tác database migration.
- Xóa resource provider đã tạo.
- Khôi phục credentials đã rotate.
- Thu hồi message đã phát vào queue.
- Đảo ngược binding đã cấp cho consumer.
- Khôi phục operation đã chuyển trạng thái.
- Khôi phục catalog cache phía platform.

Vì vậy, cần phân loại rollback:

| Lớp | Khả năng rollback | Điều kiện |
|---|---|---|
| Application image | Thường dễ | Code cũ vẫn chạy với schema hiện tại |
| Configuration/feature flag | Thường dễ | Giá trị cũ còn hợp lệ |
| Database schema | Có thể khó | Migration có thiết kế downgrade hoặc schema vẫn tương thích |
| Queue/event payload | Khó nếu đã phát version mới | Consumer cũ đọc được payload hoặc có translator |
| Provider resource | Không tự rollback | Cần compensation có kiểm soát hoặc giữ resource |
| Credentials/key | Phụ thuộc rotation | Key cũ còn hợp lệ và có thể khôi phục |
| Catalog | Có thể cache ở platform | Cần xem platform refresh và semantics ID/plan |

Không chạy downgrade SQL tự động chỉ vì deploy mới thất bại. Nếu migration đã thêm cột và code cũ bỏ qua cột đó, có thể rollback application mà giữ schema mở rộng. Nếu migration đã xóa cột hoặc chuyển đổi dữ liệu mất thông tin, rollback code có thể không chạy được.

## 16. Khi nào rollback, khi nào roll-forward?

**Rollback** phù hợp khi phiên bản mới gây lỗi nghiêm trọng, phiên bản cũ còn tương thích với schema và message hiện tại, và việc quay lại không làm mất side effect đã tạo.

**Roll-forward** phù hợp khi migration không thể đảo ngược an toàn, event mới đã được phát, provider resource đã thay đổi hoặc phiên bản cũ không thể xử lý dữ liệu mới. Khi đó, sửa lỗi bằng một release tiếp theo thường an toàn hơn cố đưa hệ thống về trạng thái trước.

Ví dụ:

| Sự cố | Hướng xử lý thường phù hợp |
|---|---|
| HTTP handler mới trả 500, schema vẫn tương thích | Rollback application |
| Readiness path cấu hình sai | Sửa config hoặc rollback deployment |
| Migration thêm cột nullable, code cũ vẫn chạy | Có thể rollback application, giữ schema |
| Migration đã drop cột code cũ cần | Roll-forward hoặc phục hồi theo kế hoạch dữ liệu |
| Worker mới phát event version 2 mà worker cũ không đọc được | Dừng producer mới, triển khai consumer tương thích; không mù quáng rollback worker |
| Provider đã tạo resource | Reconcile/adopt hoặc compensation có kiểm soát |
| Credential đã rotate và key cũ bị revoke | Dùng quy trình credential recovery, không chỉ rollback image |
| Catalog đã công bố plan mới được consumer sử dụng | Giữ khả năng quản lý instance mới đó hoặc có migration plan |

Quyết định phải dựa trên bằng chứng operation, database và provider. Không rollback theo cảm tính khi chưa biết side effect nào đã xảy ra.

## 17. Thiết kế database để hỗ trợ rollback

Database cần duy trì tương thích trong ít nhất khoảng thời gian mà phiên bản cũ có thể được khôi phục.

Ví dụ thay đổi tên field:

~~~text
Release 1:
  credentials_secret_ref

Release 2 - expand:
  credentials_secret_ref
  secret_reference

Release 3 - migrate:
  ghi cả hai field
  đọc secret_reference, fallback credentials_secret_ref
  backfill record cũ

Release 4:
  mọi code đã chuyển sang secret_reference
  kiểm tra không còn consumer đọc field cũ

Release 5 - contract:
  xóa credentials_secret_ref
~~~

Nếu rollback về Release 1 trong lúc Release 2 đang chạy, Release 1 vẫn đọc được field cũ. Điều này chỉ đúng nếu Release 2 tiếp tục ghi field cũ cho tới khi giai đoạn rollback kết thúc.

Một chiến lược khác là view hoặc compatibility layer trong repository để che giấu schema chuyển đổi. Dù chọn cách nào, phải test thực tế việc chạy code cũ trên schema mới.

## 18. Quản lý catalog và plan trong giai đoạn rollback

Catalog có thể được platform cache hoặc đọc theo chu kỳ. Sau khi deploy, platform có thể tiếp tục sử dụng metadata cũ một thời gian; sau rollback, platform có thể vẫn giữ metadata mới.

Vì vậy:

- Không xóa service ID/plan ID đã được cấp cho instance hiện hữu.
- Không thay đổi ý nghĩa plan ID đã phát hành.
- Không công bố capability trước khi implementation sẵn sàng.
- Giữ endpoint tương thích trong khoảng thời gian platform có thể cache catalog.
- Khi thêm plan mới, phiên bản cũ sau rollback vẫn phải biết cách xử lý instance của plan đó hoặc rollout cần được chặn trước khi consumer tạo instance mới.
- Khi bỏ plan, vẫn phải hỗ trợ lifecycle của instance hiện hữu theo chính sách.
- Lưu snapshot catalog của từng release để so sánh và điều tra.

Nếu platform đã tạo instance bằng plan mới trong lúc canary, rollback về code không biết plan đó có thể khiến instance không update hoặc deprovision được. Có thể cần giữ compatibility handler hoặc hoàn tất rollout thay vì rollback toàn bộ.

## 19. Provider API và credential compatibility

Provider adapter là lớp dễ bị ảnh hưởng khi nâng SDK, đổi API version hoặc thay cách xác thực.

Trước khi nâng cấp:

- Kiểm tra API version provider đang sử dụng.
- Kiểm tra response field mới/bị đổi kiểu.
- Kiểm tra error code và retry semantics.
- Kiểm tra pagination, throttling và timeout.
- Kiểm tra metadata/label/tag dùng để tìm resource cũ.
- Kiểm tra provider operation ID và polling.
- Kiểm tra credential format, token audience và scope.
- Giữ khả năng đọc metadata do phiên bản trước ghi ra.

Không đổi provider API version chỉ vì SDK mới dùng version mặc định mới. Pin API version khi provider hỗ trợ và kiểm thử contract adapter.

Nếu secret format thay đổi, dùng dual-read: đọc format mới trước, fallback format cũ; trong giai đoạn chuyển đổi có thể dual-write nếu cần. Chỉ xóa support format cũ sau khi toàn bộ secret đã migrate và có backup/key recovery.

## 20. Triển khai từng phần với Cloud Foundry và Kubernetes

Mỗi platform có cơ chế rollout riêng, nhưng nguyên tắc tương thích vẫn giống nhau.

### Kubernetes

- Dùng Deployment RollingUpdate với readiness probe đúng.
- Kiểm soát maxSurge và maxUnavailable.
- Dùng startupProbe cho ứng dụng khởi động lâu.
- Dùng preStop/graceful shutdown để ngừng nhận request và dừng claim job.
- Giữ terminationGracePeriodSeconds đủ cho request và checkpoint.
- Dùng Job riêng cho migration nếu cần.
- Tách worker deployment nếu muốn rollout request API và worker độc lập.
- Dùng canary controller hoặc traffic routing nếu cần phần trăm traffic.

### Cloud Foundry

- Xác minh hành vi rolling deployment và health check của platform đang dùng.
- Kiểm tra app instance mới đạt healthy trước khi chuyển traffic.
- Giữ compatibility với route và service binding hiện có.
- Dùng blue-green hoặc deployment plugin nếu phù hợp với môi trường.
- Không để hai app fleet cùng chạy job nền không có coordination.
- Kiểm tra broker registration và authentication không đổi ngoài kế hoạch.
- Sau rollout, xác minh platform vẫn gọi catalog và lifecycle endpoint.

Không giả định một lệnh deploy có semantics giống nhau ở mọi phiên bản Cloud Foundry hoặc Kubernetes. Dùng manifest và release procedure đã được kiểm thử trên platform mục tiêu.

## 21. Tiêu chí canary và điều kiện dừng rollout

Đặt ngưỡng trước khi deploy, tránh thay đổi tiêu chí sau khi thấy lỗi.

Ví dụ bảng gate:

| Chỉ số | Gate tiếp tục | Gate dừng |
|---|---|---|
| Readiness | Tất cả canary ready ổn định | Pod/app liên tục unready |
| HTTP 5xx | Không vượt baseline + ngưỡng cho phép | Tăng đột biến hoặc kéo dài |
| OSB request latency | Trong SLO | P95/P99 vượt ngưỡng |
| Provision failure | Không tăng bất thường | Lỗi validation/provider tăng không giải thích được |
| Operation stuck | Không tăng so với baseline | Queue/operation age tăng liên tục |
| Duplicate resource | Không phát sinh | Có duplicate hoặc ownership mismatch |
| Database pool | Còn headroom | Pending/timeout tăng |
| Provider error | Trong giới hạn | Throttling/timeout vượt budget |
| Secret access | Không có deny bất thường | Permission hoặc decrypt lỗi diện rộng |

Gate phải có owner theo dõi và hành động cụ thể. Nếu dừng rollout, ghi nhận release ID, thời điểm, metric và operation ID liên quan để điều tra.

## 22. Kế hoạch rollback từng bước

Một runbook rollback có thể gồm:

1. Dừng mở rộng canary hoặc rolling update.
2. Giữ nguyên log, metric, trace và release artifact.
3. Xác định request và operation đã đi qua phiên bản mới.
4. Kiểm tra database migration đã chạy tới version nào.
5. Kiểm tra event/outbox payload mới đã được publish chưa.
6. Kiểm tra provider resource và credential đã thay đổi chưa.
7. Quyết định rollback image/config hay roll-forward.
8. Nếu rollback image, xác nhận code cũ tương thích schema và message.
9. Nếu cần, tắt feature flag gây lỗi.
10. Chuyển traffic về phiên bản ổn định.
11. Giữ worker ở phiên bản có thể xử lý operation hiện tại.
12. Chạy reconciliation cho operation có kết quả không chắc chắn.
13. Xác minh catalog, provision, binding và last_operation.
14. Thông báo release state qua quy trình vận hành của tổ chức.
15. Ghi post-incident review và thêm regression test.

Không xóa queue, operation hoặc provider resource chỉ để làm dashboard xanh. Giữ bằng chứng và trạng thái để có thể khôi phục chính xác.

## 23. Backup và phục hồi dữ liệu

Rollback application khác với restore database. Chỉ restore backup khi dữ liệu bị hỏng hoặc cần phục hồi theo chiến lược disaster recovery.

Trước release:

- Xác minh backup gần nhất và thời gian restore dự kiến.
- Kiểm tra point-in-time recovery nếu database hỗ trợ.
- Lưu migration version và catalog snapshot.
- Bảo đảm encryption key và secret version cần thiết còn truy cập được.
- Xác định RPO/RTO cho broker state.
- Diễn tập restore trên môi trường cô lập.
- Đối chiếu database restored với provider resource thật trước khi mở traffic.

Nếu restore database về thời điểm trước khi provider resource được tạo, broker có thể mất mapping trong khi resource vẫn tồn tại. Cần reconciliation theo ownership marker và provider ID để gắn lại mapping. Không tạo lại resource chỉ vì database backup không có record.

## 24. Kiểm thử nâng cấp và rollback trong CI/CD

Một pipeline phù hợp nên có các giai đoạn:

~~~mermaid
flowchart TD
    A["Build candidate"] --> B["Unit and static checks"]
    B --> C["OSB contract and catalog diff"]
    C --> D["Database migration compatibility"]
    D --> E["Old/new worker message compatibility"]
    E --> F["Provider adapter contract"]
    F --> G["Regression on previous-version data"]
    G --> H["Deploy staging"]
    H --> I["Smoke and lifecycle tests"]
    I --> J["Rollback rehearsal"]
    J --> K["Canary production"]
    K --> L{"Release gates pass?"}
    L -->|Yes| M["Progressive rollout"]
    L -->|No| N["Stop rollout and rollback/roll-forward"]
    M --> O["Post-deploy verification"]
~~~

Các loại test cần có:

- Unit test cho validation, mapping và state transition.
- OSB contract test cho endpoint và API version.
- Catalog snapshot/diff test.
- Migration test từ schema release trước.
- Compatibility test chạy code cũ trên schema mới.
- Message compatibility test giữa worker cũ và mới.
- Integration test với database và queue thật hoặc Testcontainers.
- Provider contract test với mock server/sandbox.
- Regression test với instance/binding/operation fixture cũ.
- Canary smoke test cho catalog và lifecycle.
- Rollback rehearsal trên staging.
- Restore rehearsal nếu release có thay đổi dữ liệu quan trọng.

Một pipeline chỉ build và chạy unit test không chứng minh có thể rollback. Cần có bằng chứng phiên bản cũ khởi động và đọc được schema mới trong môi trường tương tự production.

## 25. Ví dụ kiểm tra catalog snapshot trong Spring

Có thể dùng WebTestClient để lấy catalog và so sánh các thuộc tính quan trọng. Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class CatalogCompatibilityTest {

    @Autowired
    WebTestClient client;

    @Test
    void existingServiceAndPlanIdsRemainAvailable() {
        client.get()
                .uri("/v2/catalog")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.services[?(@.id == 'svc-postgresql')].id")
                    .isNotEmpty()
                .jsonPath("$.services[?(@.id == 'svc-postgresql')].plans[?(@.id == 'plan-standard')].id")
                    .isNotEmpty();
    }
}
~~~

Đây là ví dụ minh họa. Trong test thực tế, fixture và service ID/plan ID phải lấy từ contract của broker. Có thể deserialize catalog thành model rồi so sánh theo ID để tránh phụ thuộc thứ tự mảng. Snapshot test nên cho phép thay đổi có chủ đích sau review, đồng thời phát hiện việc vô tình xóa capability hoặc plan.

## 26. Ví dụ kiểm tra migration tương thích ngược

Một test migration nên bắt đầu từ schema cũ và dữ liệu cũ:

1. Khởi động database ở schema N.
2. Nạp instance, binding và operation fixture của release trước.
3. Chạy migration lên schema N+1.
4. Khởi động ứng dụng phiên bản mới và xác minh đọc/ghi.
5. Dừng ứng dụng mới.
6. Khởi động ứng dụng phiên bản cũ trên schema N+1.
7. Xác minh các luồng cũ vẫn hoạt động.
8. Chạy backfill nếu có và xác minh dữ liệu.
9. Chỉ thử contract migration trong test riêng khi không còn code cũ.

Không nhất thiết mọi release phải chạy toàn bộ matrix trên mọi commit. Nhưng release có schema change phải có bằng chứng migration và rollback compatibility trước khi production rollout.

## 27. Ví dụ kiểm tra operation đang chạy qua phiên bản mới

Tạo fixture operation từ release cũ:

~~~json
{
  "operation_id": "provision-op-legacy",
  "instance_id": "instance-legacy",
  "operation_type": "PROVISION",
  "state": "WAITING_PROVIDER",
  "provider_operation_id": "provider-op-77",
  "event_version": 1
}
~~~

Sau khi deploy candidate:

- Worker mới phải đọc được record và event version cũ.
- Provider adapter phải truy vấn được provider operation ID cũ.
- Worker không được gửi create mới nếu resource đã tồn tại.
- Operation tiếp tục polling hoặc reconciliation.
- Khi provider xác nhận hoàn tất, broker lưu resource mapping và state.
- last_operation trả kết quả đúng cho platform.

Test này đặc biệt quan trọng khi nâng cấp worker, Reactor, queue client hoặc provider SDK.

## 28. Những sai lầm thường gặp

**Chỉ kiểm thử phiên bản mới trên database rỗng.** Điều này bỏ qua instance, binding và operation cũ. Hãy dùng fixture từ các release trước.

**Drop/rename column ngay khi deploy code mới.** Replica cũ có thể còn chạy và cần field đó. Dùng expand-contract.

**Thay plan ID nhưng không giữ instance cũ.** Broker có thể mất khả năng update hoặc deprovision instance đã tạo.

**Bật capability trước khi endpoint sẵn sàng.** Platform có thể gọi ngay sau khi refresh catalog.

**Rollback image mà không kiểm tra queue payload.** Worker cũ có thể không đọc được event mới.

**Chạy blue và green worker cùng lúc không có coordination.** Một operation có thể bị xử lý hai lần.

**Coi rollback là undo provider side effect.** Database và cloud resource không nằm trong cùng transaction.

**Restore database mà không đối chiếu provider.** Resource có thể còn tồn tại nhưng mapping đã mất.

**Rotate key mà không giữ compatibility.** Phiên bản cũ có thể không đọc được secret mới hoặc key cũ đã bị revoke.

**Không đặt gate canary.** Rollout tiếp tục dù operation failure và queue backlog đang tăng.

**Không diễn tập rollback.** Runbook có thể đúng trên giấy nhưng thất bại khi thực hiện.

## 29. Checklist phát hành

### Trước rollout

- Đã ghi release version, commit và image digest.
- Đã so sánh OSB API contract và catalog snapshot.
- Service ID và plan ID cũ vẫn được xử lý.
- Capability mới chỉ được công bố sau khi implementation sẵn sàng.
- Regression test chạy trên fixture dữ liệu cũ.
- Database migration theo expand-contract.
- Code cũ chạy được trên schema đã expand.
- Worker cũ và mới tương thích với event payload trong giai đoạn chuyển tiếp.
- Operation đang chạy có checkpoint và recovery.
- Provider adapter và credential format đã được kiểm thử.
- Backup và restore point đã xác minh.
- Rollback/roll-forward decision tree và owner đã rõ.
- Canary gate và ngưỡng dừng đã được thống nhất.

### Trong rollout

- Theo dõi readiness, liveness và startup.
- Kiểm tra catalog endpoint.
- Theo dõi 5xx, latency và OSB error response.
- Theo dõi provision/update/bind/unbind/deprovision.
- Theo dõi operation age, retry và reconciliation.
- Theo dõi provider timeout/AlreadyExists.
- Theo dõi database pool và queue backlog.
- Không để hai worker fleet xử lý trùng.
- Dừng rollout khi bất kỳ gate quan trọng nào thất bại.

### Sau rollout

- Xác minh mọi replica ở phiên bản dự kiến.
- Xác minh catalog snapshot và platform refresh.
- Kiểm tra operation trước/sau deploy đều tiến triển.
- Kiểm tra instance và binding cũ vẫn hoạt động.
- Kiểm tra provider resource mapping.
- Xác minh secret access và audit.
- Lưu release evidence, migration version và test report.
- Giữ schema cũ trong thời gian rollback window.
- Chỉ contract/drop dữ liệu cũ trong release riêng sau khi hết phụ thuộc.

## Kết luận

Kiểm thử hồi quy, triển khai từng phần và kế hoạch khôi phục phải được thiết kế cùng nhau. Service broker cần giữ tương thích với OSB API, catalog, plan, database, message payload, provider resource và credentials trong suốt thời gian phiên bản cũ và mới cùng tồn tại. Hãy dùng contract test và catalog diff để bảo vệ platform interface, expand-contract để bảo vệ database, version hóa event để bảo vệ worker, đồng thời dùng rolling/canary/blue-green với readiness và release gates phù hợp. Rollback ứng dụng không đảo ngược provider side effect hoặc migration phá hủy; khi trạng thái dữ liệu đã tiến lên, roll-forward và reconciliation có thể an toàn hơn. Một release chỉ sẵn sàng khi có regression evidence, kế hoạch chuyển đổi dữ liệu, tiêu chí dừng, phương án rollback/roll-forward và quy trình xác minh sau deploy.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — contract catalog và service instance/binding lifecycle.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — model và service abstraction của broker.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — RollingUpdate, rollout status và rollback deployment.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — startup, readiness và liveness.
- [Cloud Foundry — App Manifest](https://docs.cloudfoundry.org/devguide/deploy-apps/manifest-attributes.html) — cấu hình ứng dụng và deployment attributes.
- [Martin Fowler — Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) — chuyển đổi hệ thống theo từng phần.
- [Martin Fowler — Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) — quản lý feature flags.
- [Flyway Documentation](https://documentation.red-gate.com/flyway) — quản lý và version hóa database migration.
- [Liquibase Documentation](https://docs.liquibase.com/) — migration và quản lý thay đổi schema.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — phối hợp database transaction và message publication.
- [Testcontainers for Java](https://java.testcontainers.org/) — kiểm thử tích hợp với database và message broker.

