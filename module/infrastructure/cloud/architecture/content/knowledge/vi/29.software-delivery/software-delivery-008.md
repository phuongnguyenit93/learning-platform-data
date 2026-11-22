# Tách chu kỳ triển khai của các dịch vụ phụ thuộc

## 1. Vì sao các dịch vụ phụ thuộc không nên buộc phát hành cùng lúc?

Trong hệ thống phân tán, một hành trình nghiệp vụ thường đi qua nhiều service: API gateway gọi Booking Service, Booking Service đọc Inventory và Pricing, phát event sang Payment/Notification, còn Search Indexer cập nhật read model. Mỗi service có mã nguồn, nhóm sở hữu, tốc độ thay đổi và rủi ro triển khai riêng.

Nếu mọi thay đổi phải phát hành cùng một đợt, một service nhỏ có thể bị chặn bởi lịch của nhiều nhóm khác. Release trở thành một “big bang”: nhiều artifact, migration, cấu hình và thay đổi hợp đồng cùng lên production; khi lỗi xảy ra, khó xác định thành phần gây lỗi và khó rollback an toàn. Một thay đổi schema có thể khiến consumer chưa được cập nhật ngừng hoạt động; ngược lại, consumer mới có thể gọi API mà provider cũ chưa hỗ trợ.

**Tách chu kỳ triển khai (decoupling deployment cycles)** là thiết kế service, hợp đồng giao tiếp, dữ liệu và quy trình phát hành để mỗi service có thể build, test, deploy và rollback theo nhịp riêng trong khi vẫn tương tác an toàn với các phiên bản khác đang chạy.

Mục tiêu không phải deploy độc lập bằng mọi giá. Mục tiêu là giảm phối hợp bắt buộc, giới hạn blast radius và giữ tương thích trong giai đoạn chuyển tiếp. Các service chỉ nên release cùng nhau khi có một ranh giới thay đổi thực sự không thể tách hoặc một invariant nghiệp vụ cần triển khai nguyên tử.

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định về API, event, database, compute và mô hình vận hành. Kiến trúc cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: Booking Service muốn thêm trường cancellationReason; Notification Service muốn hiển thị lý do hủy; Analytics Consumer cũng đọc event booking. Nếu đổi schema database và event cùng lúc rồi deploy mọi service theo một lịch, việc phát hành bị khóa chéo. Thiết kế tương thích cho phép provider mở rộng hợp đồng trước, consumer nâng cấp dần, rồi mới loại bỏ cách cũ.

## 2. Phân biệt build, release và deploy

| Hoạt động | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Build | Tạo artifact từ source và dependency | Container image có digest |
| Release | Cho phép một phiên bản trở thành ứng viên được sử dụng | Đánh dấu image v2.8 đã qua kiểm thử |
| Deploy | Đưa artifact/configuration vào một môi trường | Cập nhật workload trong production |
| Activate | Bật tính năng hoặc chuyển traffic tới phiên bản mới | Bật feature flag cho 5% tenant |
| Rollback | Quay lại phiên bản/cấu hình trước khi còn an toàn | Chuyển traffic về deployment cũ |

Một artifact có thể được build một lần, promote qua staging và production; deploy chưa chắc đồng nghĩa tính năng mới đã bật. Feature flag và routing policy cho phép tách thời điểm triển khai binary khỏi thời điểm kích hoạt hành vi.

### 2.1. Deploy độc lập không đồng nghĩa release không phối hợp

Hai service có thể deploy riêng nhưng vẫn tuân theo hợp đồng chung. Ví dụ provider thêm optional field mà consumer cũ bỏ qua; consumer mới được triển khai sau đó. Việc thay đổi contract vẫn cần owner, versioning, kiểm thử và kế hoạch loại bỏ field cũ.

Không cần một release train chung cho mọi thay đổi, nhưng cần quy trình điều phối cho breaking change, data migration, security emergency và thay đổi ảnh hưởng nhiều domain.

## 3. Mức độ phụ thuộc và khả năng deploy độc lập

| Kiểu coupling | Dấu hiệu | Hệ quả khi deploy |
| --- | --- | --- |
| Compile-time coupling | Service dùng chung library/model được release đồng bộ | Thay đổi library có thể buộc rebuild nhiều consumer |
| API contract coupling | Consumer phụ thuộc endpoint, field hoặc semantics của provider | Breaking change làm consumer lỗi |
| Database coupling | Nhiều service đọc/ghi cùng schema hoặc bảng | Migration có thể buộc deploy đồng thời |
| Event/schema coupling | Consumer phụ thuộc event name, field hoặc ordering | Producer đổi event làm consumer parse sai |
| Runtime coupling | Service đồng bộ chờ service khác trong request path | Service chậm/lỗi lan sang caller |
| Release-process coupling | Một pipeline hoặc approval khóa nhiều service | Lịch phát hành và rollback phụ thuộc nhau |
| Organizational coupling | Một nhóm kiểm soát nhiều codebase/contract | Thay đổi nhỏ cần nhiều lần bàn giao |

Không phải coupling nào cũng xấu. Một số invariant cần transaction hoặc consistency mạnh. Nhưng coupling cần được nhận diện, định giá và quản lý có chủ đích thay vì để nó hình thành qua shared database, shared library hoặc quy trình release.

## 4. Thiết kế contract tương thích giữa các phiên bản

Khi provider và consumer chạy phiên bản khác nhau, hợp đồng phải hỗ trợ trạng thái chuyển tiếp. Một nguyên tắc phổ biến là **mở rộng trước, loại bỏ sau**:

1. Provider thêm khả năng mới theo cách tương thích.
2. Consumer được triển khai để hiểu cả dạng cũ và mới.
3. Chuyển dần traffic/data sang dạng mới.
4. Quan sát mức sử dụng hợp đồng cũ.
5. Sau khi không còn consumer cũ và hết thời gian hỗ trợ, mới xóa phần cũ.

### 4.1. Nguyên tắc thay đổi API an toàn

- Thêm field optional có default rõ thường an toàn hơn đổi field hiện có.
- Consumer nên bỏ qua field không nhận biết nếu contract cho phép.
- Không đổi ý nghĩa của field mà vẫn giữ tên và kiểu dữ liệu.
- Không làm field optional thành required trước khi mọi consumer gửi giá trị.
- Không đổi enum bằng cách thêm giá trị mà consumer cũ không xử lý được nếu họ dùng exhaustive matching.
- Không đổi đơn vị, timezone, rounding hoặc semantics ngầm mà không version hóa.
- Giữ error semantics và status code đủ ổn định.
- Có timeout, retry và idempotency contract cho thao tác ghi.

“Backward compatible” phải được đánh giá từ cả hai phía. Một thay đổi có thể tương thích với provider cũ nhưng không tương thích với consumer cũ, hoặc ngược lại.

### 4.2. Ví dụ API tiến hóa

Phiên bản cũ:

~~~json
{
  "bookingId": "b-102",
  "status": "CANCELLED"
}
~~~

Phiên bản mở rộng:

~~~json
{
  "bookingId": "b-102",
  "status": "CANCELLED",
  "cancellationReason": "GUEST_REQUEST"
}
~~~

Provider có thể thêm field optional mà consumer cũ bỏ qua. Consumer mới phải xử lý trường hợp field không có hoặc null trong thời gian chuyển đổi. Nếu field mới trở thành bắt buộc cho logic mới, cần bảo đảm provider đã phát field cho mọi response thuộc contract đó trước khi consumer dựa vào nó.

### 4.3. API versioning

Có thể version qua URL (/v1, /v2), header/media type hoặc schema version. Chọn cách phù hợp với platform và client lifecycle. Không tăng major version cho mọi field mới; cũng không giả vờ một thay đổi breaking là minor chỉ để tránh quản lý migration.

Mỗi version cần owner và compatibility policy; thời gian hỗ trợ/deprecation; metrics theo version/client; contract tests; kế hoạch migrate consumer; điều kiện retire version cũ và bằng chứng không còn traffic.

## 5. Event-driven contract và consumer độc lập

Event thường tồn tại lâu hơn một request HTTP: message có thể nằm trong broker, retry, replay hoặc được consumer mới đọc lại nhiều tháng sau. Vì vậy thay đổi schema event cần chú ý compatibility và evolution.

### 5.1. Thiết kế event ổn định

~~~json
{
  "eventId": "evt-901",
  "eventType": "BookingCancelled",
  "schemaVersion": 2,
  "occurredAt": "2026-11-18T05:30:00Z",
  "producer": "booking-service",
  "aggregateId": "b-102",
  "aggregateVersion": 42,
  "data": {
    "bookingId": "b-102",
    "cancellationReason": "GUEST_REQUEST"
  }
}
~~~

Envelope giúp consumer xử lý event identity, type, producer, version, timestamp và aggregate ordering. Schema version không tự bảo đảm compatibility; registry/validation và consumer test phải định nghĩa điều gì được phép thay đổi.

### 5.2. Producer và consumer không release cùng lúc

Producer mới có thể phát event v2 trong khi consumer cũ vẫn đang chạy. Có một số cách:

- Producer phát schema mở rộng mà consumer cũ có thể bỏ qua field mới.
- Producer dual-publish hai event version trong giai đoạn migration nếu cần.
- Consumer hỗ trợ đọc cả v1/v2 rồi triển khai dần.
- Dùng topic mới khi semantics hoặc partitioning thay đổi không tương thích.
- Chạy shadow consumer để so sánh kết quả trước cutover.

Dual-publish cần tránh xử lý trùng nghiệp vụ. Cùng một event logic được phát hai dạng phải có event ID/correlation và quy tắc dedup rõ.

### 5.3. Idempotency, ordering và replay

Consumer cần giả định message có thể được giao nhiều lần. Dùng event ID hoặc business operation key để deduplicate; ghi nhận offset/ack theo semantics broker; xử lý version để ngăn event cũ ghi đè trạng thái mới.

Không giả định mọi event toàn cục có thứ tự. Nếu cần thứ tự theo booking, partition/key theo aggregate hoặc dùng aggregateVersion và xử lý event gap. Replay cần xác định side effect nào được lặp, side effect nào phải dùng idempotency key.

## 6. Tách database schema khỏi lịch deploy của service

Shared database schema là một trong những nguồn coupling khó xử lý nhất. Nếu service A và B cùng đọc/ghi bảng, việc rename/drop column có thể buộc cả hai deploy cùng lúc.

### 6.1. Expand–migrate–contract

~~~mermaid
flowchart LR
    A["1. Expand<br/>Thêm schema mới"]
    B["2. Migrate<br/>Đọc/ghi tương thích, backfill"]
    C["3. Switch<br/>Consumer dùng schema mới"]
    D["4. Contract<br/>Xóa schema cũ sau xác minh"]
    A --> B --> C --> D
~~~

Ví dụ đổi guest_name thành primary_guest_name:

1. **Expand:** thêm primary_guest_name nullable, giữ guest_name.
2. **Compatibility:** application ghi cả hai cột hoặc dùng một lớp mapping; đọc cột mới rồi fallback cột cũ khi cần.
3. **Backfill:** copy dữ liệu cũ sang cột mới theo batch, checkpoint và kiểm tra số lượng/checksum.
4. **Switch:** deploy mọi reader sang cột mới; quan sát query/log để chắc không còn đọc cột cũ.
5. **Stop old writes:** sau khi mọi writer mới đã ổn định, dừng ghi cột cũ.
6. **Contract:** xóa cột cũ trong một release riêng sau thời gian xác minh.

### 6.2. Vì sao không rename/drop trong một bước?

Nếu database drop column trước khi một service cũ dừng đọc, service đó sẽ lỗi ngay. Nếu application mới đọc cột mới trước khi migration tạo cột, deployment sẽ thất bại. Giai đoạn expand giữ cả hai dạng để provider, consumer và schema có thể thay đổi theo nhịp riêng.

### 6.3. Migration cần idempotent và có khả năng tiếp tục

Backfill lớn nên chia batch, checkpoint, rate limit và có thể resume sau lỗi. Không chạy một transaction khổng lồ làm tăng lock, WAL hoặc replication lag. Kiểm tra count, null rate, uniqueness và business invariant trước khi switch.

Migration dữ liệu có side effect hoặc mất dữ liệu cần plan riêng; rollback application không tự đảo ngược data migration. Đôi khi cách an toàn là forward-fix thay vì cố chạy migration ngược.

## 7. Database ownership và tránh shared schema coupling

Một database server có thể phục vụ nhiều service, nhưng ownership logic phải rõ. Service sở hữu dữ liệu nên kiểm soát schema và API/event cho các consumer khác.

| Mô hình | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| Shared DB, shared schema | Vận hành hạ tầng đơn giản | Coupling rất cao; mọi nhóm có thể phụ thuộc bảng của nhau |
| Shared DB, schema riêng | Có namespace và quyền tách tốt hơn | Vẫn chia sẻ capacity/maintenance; join cross-schema gây coupling |
| Database riêng theo service | Ownership, migration và scale độc lập | Chi phí, backup, connection và vận hành tăng |
| Data store theo capability | Chọn loại lưu trữ theo access pattern | Consistency, replication và quan sát phức tạp |

Nếu service B cần dữ liệu của A, ưu tiên API/event hoặc read model được công bố thay vì query trực tiếp bảng nội bộ của A. Có thể tạo read replica/projection cho reporting thay vì cho analytics query chạy trên primary transaction database.

## 8. Contract testing và kiểm tra compatibility

Unit test của provider không chứng minh consumer sử dụng API đúng. Integration test toàn bộ hệ thống có thể đắt và khó chạy cho mọi pull request. Contract testing kiểm tra thỏa thuận giao tiếp giữa provider và consumer.

### 8.1. Consumer-driven contract

Consumer mô tả request/response hoặc message mà nó dựa vào. Provider kiểm tra implementation có đáp ứng contract đó không. Contract được version hóa và chạy ở CI để phát hiện breaking change trước deploy.

Quy trình:

1. Consumer ghi lại expectation thiết yếu, không khóa những chi tiết không dùng.
2. Contract được publish kèm consumer version.
3. Provider CI tải các contract được hỗ trợ và verify.
4. Kết quả được báo về compatibility matrix.
5. Provider không release thay đổi phá contract còn trong thời hạn hỗ trợ.
6. Khi consumer retire, contract tương ứng được ngừng theo quy trình.

### 8.2. Provider verification và compatibility matrix

| Provider | Consumer | Phiên bản consumer đang chạy | Contract result | Trạng thái |
| --- | --- | --- | --- | --- |
| Booking API v3 | Web app | v5 | Pass | Đang dùng |
| Booking API v3 | Notification worker | v2 | Pass | Đang dùng |
| Booking API v3 | Analytics consumer | v1 | Fail với schema candidate | Cần xử lý trước contract change |

Ma trận chỉ có ý nghĩa nếu được nối với phiên bản thật đang chạy, không chỉ version đã build. Inventory deployment giúp biết consumer nào vẫn tồn tại và cần hỗ trợ.

### 8.3. Contract không thay thế kiểm thử nghiệp vụ

Contract có thể pass dù semantics sai, ví dụ status vẫn là chuỗi nhưng ý nghĩa CONFIRMED thay đổi. Cần thêm test invariant, scenario test và kiểm tra dữ liệu end-to-end cho luồng quan trọng.

## 9. Feature flags và tách deploy khỏi activate

Feature flag cho phép đưa code mới vào production nhưng chỉ bật cho một nhóm người dùng/tenant hoặc điều kiện cụ thể.

Các cách dùng:

- Dark launch: code chạy nhưng chưa hiển thị kết quả cho người dùng.
- Canary: bật cho một tỷ lệ nhỏ traffic.
- Tenant allowlist: bật cho nhóm khách hàng đã được chọn.
- Kill switch: tắt nhanh một tính năng có vấn đề.
- Experiment: so sánh hành vi theo nhóm có kiểm soát.

Feature flag không sửa được contract breaking hoặc schema migration sai. Nếu code mới yêu cầu field chưa được tạo, bật cờ vẫn có thể gây lỗi. Flag cần owner, default an toàn, ngày hết hạn, audit và metric đánh giá.

### 9.1. Flag lifecycle

1. Tạo flag với mục tiêu và owner.
2. Chọn default behavior an toàn.
3. Deploy code mới với flag tắt.
4. Kiểm tra health và telemetry.
5. Bật canary/allowlist.
6. Mở rộng dần theo SLO và business metric.
7. Khi ổn định, xóa nhánh code cũ và flag.

Flag tồn tại quá lâu làm tăng số nhánh trạng thái cần test và gây khó hiểu. Hãy xử lý flag như một tài sản có vòng đời, không phải cấu hình vĩnh viễn.

## 10. Chiến lược rollout để service có thể phát hành riêng

| Chiến lược | Cách làm | Khi phù hợp | Rủi ro cần quản lý |
| --- | --- | --- | --- |
| Rolling | Thay instance dần trong cùng deployment | Service stateless, version tương thích | Hai version cùng chạy; phải hỗ trợ overlap |
| Blue-green | Chuẩn bị environment mới rồi chuyển traffic | Cần chuyển đổi và rollback nhanh | Hai environment cùng tồn tại, data/schema phải tương thích |
| Canary | Chuyển một phần traffic tới phiên bản mới | Muốn kiểm tra production với blast radius nhỏ | Metric phải đủ đại diện, routing cần chính xác |
| Shadow | Gửi bản sao traffic tới phiên bản mới nhưng không dùng response | Kiểm tra behavior/performance | Không được lặp side effect hoặc truy cập dữ liệu ngoài ý muốn |
| Progressive delivery | Mở rộng theo bước dựa trên metric/policy | Nhiều service/region/tenant | Cần automation, guardrail và stop condition |

### 10.1. Health gate

Trước mỗi bước mở rộng cần kiểm tra error rate và latency theo route/version; saturation, restart, crash và readiness; dependency health, database errors và queue lag; business outcome như booking success hoặc payment unknown rate; security/audit signals; metric so sánh với baseline và control group khi có.

Health check process chỉ chứng minh process còn sống; readiness chỉ chứng minh instance có thể nhận một loại traffic theo logic đã định. Phải bổ sung synthetic/business check cho các hành trình quan trọng.

## 11. Rollback và forward-fix khi các service thay đổi độc lập

Rollback binary không luôn an toàn:

- Schema đã expand có thể vẫn được giữ lại, nhưng schema đã drop không thể phục hồi chỉ bằng rollback code.
- Event v2 đã phát có thể còn trong broker và consumer cũ phải hiểu hoặc được bridge.
- Dữ liệu đã chuyển đổi có thể không tương thích với code cũ.
- Side effect như email, payment hoặc external API không thể “undo” bằng cách deploy image cũ.
- Feature flag có thể tắt hành vi mới nhưng không đảo được dữ liệu đã ghi.

Vì vậy phải phân biệt application rollback, traffic rollback, flag rollback, data rollback và forward-fix. Mỗi release cần xác định rollback point, compatibility window và điều kiện chọn forward-fix. Không gọi mọi hành động khôi phục là rollback.

## 12. Quản lý release dependency và deployment order

Một số thay đổi vẫn có thứ tự. Ví dụ provider phải thêm field trước khi consumer gửi request chứa field đó. Thứ tự có thể được biểu diễn như một migration plan:

| Giai đoạn | Provider/API | Consumer | Database |
| --- | --- | --- | --- |
| 0. Current | v1 | v1 | Schema cũ |
| 1. Expand | v1 + hỗ trợ optional v2 field | v1 | Thêm cột mới |
| 2. Consumer rollout | v1 + v2-compatible | v2 hiểu cả hai dạng | Cả cột cũ/mới |
| 3. Switch | v2 default | v2 | Backfill và đọc schema mới |
| 4. Retire | Không còn v1 path | Mọi consumer đã chuyển | Xóa cột/event cũ sau thời gian hỗ trợ |

Deployment order nên được ghi thành dependency có điều kiện, không tạo một mega-pipeline bắt mọi service chạy cùng lúc. Có thể release provider trước, chờ compatibility signal, rồi consumer tự deploy khi sẵn sàng.

## 13. Release orchestration và ownership

Tách chu kỳ không loại bỏ governance; nó chuyển trọng tâm từ “ai phát hành cùng ai” sang “ai sở hữu contract, ai đảm bảo compatibility và ai xử lý khi consumer không nâng cấp”.

Mỗi service cần owner team/on-call; repository/artifact/version truy nguyên; API/event/schema contract có owner; SLO và deployment health metrics; release/deprecation policy; runbook và rollback/forward-fix strategy; inventory consumer và thời gian hỗ trợ phiên bản.

Platform team cung cấp pipeline, deployment controller, registry, observability và policy chung. Domain team chịu trách nhiệm hành vi contract và compatibility của service mình.

### 13.1. Consumer inventory

Provider cần biết ai đang gọi API hoặc consume event. Có thể kết hợp telemetry client identity, service catalog, event subscription registry và deployment inventory. Không dùng số request thấp trong vài ngày để kết luận consumer đã biến mất nếu consumer có thể chạy theo batch tháng.

Trước khi retire API/event version, thông báo owner, đo traffic theo client, cho thời gian migrate, cung cấp hướng dẫn và có quy trình escalation.

## 14. Security và supply chain trong phát hành độc lập

Tần suất phát hành cao làm tăng số lần thay đổi production; mỗi deployment cần giữ kiểm soát bảo mật:

- Build artifact từ source đã review và commit xác định.
- Pin dependency/base image và scan vulnerability.
- Ký/verify artifact hoặc provenance nếu hệ thống hỗ trợ.
- Dùng workload identity và quyền deploy theo service/environment.
- Tách quyền build, release approval và production deployment.
- Không để feature flag mở ra endpoint hoặc quyền vượt authorization policy.
- Bảo vệ secret, token, signing material và deployment credential.
- Audit ai bật flag, promote artifact hoặc thay routing.

Rollback về image cũ không đồng nghĩa image đó còn an toàn. Nếu bản cũ chứa lỗ hổng đang bị khai thác, cần forward-fix hoặc mitigation thay vì khôi phục phiên bản có rủi ro đã biết.

## 15. Observability và đánh giá chất lượng release

Mỗi release nên có deployment marker và version attribute để dashboard so sánh trước/sau:

| Nhóm | Metric/signal |
| --- | --- |
| Delivery | Lead time, deployment frequency, change failure rate, time to restore |
| Service health | Error rate, p95/p99 latency, availability, saturation |
| Contract | Provider verification, consumer compatibility, deprecated version traffic |
| Data | Migration progress, backfill lag, null/mismatch count, replication lag |
| Event | Consumer lag, DLQ, duplicate, schema validation failure |
| Business | Journey completion, booking success, payment unknown, cancellation outcome |
| Security | Vulnerability, policy violation, permission change, provenance |
| Rollout | Canary cohort, flag exposure, rollback/forward-fix events |

Không chỉ đo số lần deploy. Deployment frequency tăng nhưng change failure rate và recovery time cũng tăng có thể là dấu hiệu chất lượng release đi xuống. Phải xem các chỉ số delivery cùng reliability và business outcome.

## 16. Bài thực hành: tách release của Booking, Payment và Notification

**Bối cảnh giả định:** Booking Service, Payment Adapter và Notification Worker hiện được phát hành cùng một pipeline. Booking cần thêm cancellation reason; Payment cần thay đổi callback status; Notification muốn dùng field mới trong event. Các nhóm có lịch và owner khác nhau.

### Nhiệm vụ

1. Vẽ dependency graph API/event/database giữa ba service và chỉ ra coupling đang buộc deploy đồng thời.
2. Thiết kế API/event contract có version, optional field, default và unknown-field behavior.
3. Lập kế hoạch expand–migrate–contract cho database và event schema.
4. Viết contract test ở consumer và provider; tạo compatibility matrix theo phiên bản đang chạy.
5. Thiết kế rollout theo canary/rolling/blue-green và health gate.
6. Dùng feature flag để tách deploy binary khỏi activate behavior.
7. Định nghĩa idempotency, ordering, replay và xử lý event v1/v2 đồng thời.
8. Xác định điều kiện rollback application, flag, traffic và khi nào phải forward-fix.
9. Thiết kế deprecation policy và consumer inventory trước khi retire contract cũ.
10. Xác định deployment markers, SLO và business metrics để đánh giá release.
11. Viết ADR về ranh giới service ownership và trường hợp ngoại lệ vẫn cần coordinated release.

### Mẫu migration plan

| Bước | Provider | Consumer | Data/contract | Gate |
| --- | --- | --- | --- | --- |
| 1 | Thêm field optional | Giữ code cũ | Schema v1-compatible | Contract pass |
| 2 | Phát event có version/field mới | Consumer đọc cả cũ và mới | Dual-read hoặc compatible schema | Error/DLQ ổn định |
| 3 | Consumer chuyển sang field mới | Theo dõi consumer inventory | Backfill hoàn tất | Data parity pass |
| 4 | Ngừng ghi field cũ | Không còn đọc field cũ | Deprecated usage về 0 | Owner xác nhận |
| 5 | Xóa contract/schema cũ | Consumer cũ đã retire | Contract v2 | Rollback plan được phê duyệt |

### Tiêu chí hoàn thành

- Mỗi service có thể deploy riêng trong compatibility window.
- API/event contract được version hóa và test từ cả provider/consumer.
- Database migration giữ tương thích qua nhiều phiên bản chạy đồng thời.
- Consumer cũ không bị phá bởi provider mới trong thời gian hỗ trợ.
- Event có idempotency, ordering semantics và replay strategy.
- Rollout có canary/health gate/stop condition.
- Rollback và forward-fix được phân biệt rõ.
- Có consumer inventory, deprecation window và owner.
- Release metrics phản ánh cả service health và journey outcome.

## 17. Checklist Well-Architected trước khi tách chu kỳ deploy

- [ ] Đã xác định coupling compile-time, API, database, event, runtime và release process.
- [ ] Mỗi service có owner, artifact/version, SLO và deployment pipeline rõ.
- [ ] API contract có compatibility policy, versioning và deprecation lifecycle.
- [ ] Consumer xử lý optional/unknown field, null, enum và error semantics theo contract.
- [ ] Event có schema version, event ID, aggregate version và replay semantics.
- [ ] Consumer idempotent; ordering và duplicate delivery được xử lý.
- [ ] Database migration theo expand–migrate–contract, backfill có checkpoint và verify.
- [ ] Không drop/rename field khi còn consumer hoặc writer phiên bản cũ.
- [ ] Contract test chạy ở cả provider và consumer với compatibility matrix.
- [ ] Feature flag có owner, default, audit, expiry và cleanup.
- [ ] Rollout có canary/health gate và quan sát business outcome.
- [ ] Rollback application, traffic, flag và data có kế hoạch riêng; forward-fix được cân nhắc.
- [ ] Consumer inventory đủ để hỗ trợ deprecation và retire version cũ.
- [ ] Pipeline dùng artifact bất biến, workload identity và least privilege.
- [ ] Dashboard có deployment marker, contract error, SLO và business metric.
- [ ] Tần suất deploy không làm giảm reliability hoặc tăng change failure rate ngoài ngưỡng.
- [ ] Có tiêu chí rõ cho thay đổi nào vẫn cần coordinated release.
- [ ] ADR ghi rõ đánh đổi reliability, security, performance, cost và operations.

**Điểm cốt lõi:** các service có thể phát hành theo nhịp riêng khi hợp đồng và dữ liệu hỗ trợ nhiều phiên bản trong giai đoạn chuyển tiếp. API/event evolution, expand–migrate–contract, contract testing, consumer inventory và progressive rollout tạo ra khoảng tương thích để provider và consumer không cần deploy cùng lúc. Khi rollback, forward-fix, ownership và telemetry được thiết kế rõ, tổ chức có thể tăng tốc phát hành mà vẫn kiểm soát blast radius và bảo vệ hành trình nghiệp vụ.
