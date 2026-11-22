# Cảnh báo schema drift và version cũ

## 1. Vì sao phải giám sát schema drift và API version?

API contract mô tả cách client và service trao đổi dữ liệu: endpoint, method, parameter, request/response schema, error, authentication và semantics của operation. Trong thực tế, contract có thể thay đổi ở nhiều nơi: source code, OpenAPI/protobuf, gateway, service deployment, SDK hoặc client đã phát hành.

Schema drift xảy ra khi những thành phần này không còn hiểu cùng một cấu trúc hoặc ý nghĩa dữ liệu. Version cũ tiếp tục được sử dụng khi client vẫn gọi API đã deprecated, không còn được hỗ trợ hoặc có security policy đã lỗi thời.

Hai vấn đề này liên quan trực tiếp tới bảo mật API:

- Gateway validate theo schema cũ trong khi service xử lý field mới hoặc field nhạy cảm theo cách khác.
- Service bỏ một validation rule nhưng client cũ vẫn gửi giá trị mà hệ thống không còn kiểm soát đúng.
- Response thêm field nhạy cảm mà client hoặc gateway cũ không dự kiến.
- Enum hoặc trạng thái nghiệp vụ thay đổi khiến client cũ hiểu sai quyền hoặc kết quả.
- API version cũ không còn nhận bản vá authentication, authorization hoặc input validation.
- Một route cũ vẫn public dù đã được cho là retired.
- Client gửi version không hợp lệ hoặc giả mạo để đi vào nhánh xử lý yếu hơn.
- Event producer và consumer dùng schema khác nhau, khiến message được chấp nhận nhưng diễn giải sai.

Không thể phát hiện các vấn đề này chỉ bằng cách xem deploy có thành công hay không. Cần kết hợp contract diff trước deploy, telemetry sau deploy, inventory version, traffic thực tế và cảnh báo theo mức độ ảnh hưởng.

Mục tiêu là phát hiện sớm ba tình huống: contract đã lệch, client đang gặp lỗi do lệch contract, hoặc client vẫn phụ thuộc vào version cũ có rủi ro. Cảnh báo phải chỉ ra API/operation/version/consumer liên quan, mức ảnh hưởng và bước xử lý tiếp theo.

## 2. Phân biệt các loại drift

Không phải mọi khác biệt đều là schema drift có tác động như nhau. Phân loại giúp chọn tín hiệu và severity phù hợp:

| Loại drift | Ví dụ | Rủi ro |
|---|---|---|
| Request schema drift | Service yêu cầu field mới nhưng client cũ không gửi | Request lỗi hoặc client không dùng được chức năng |
| Response schema drift | Service đổi type hoặc bỏ field | Client parse sai hoặc mất dữ liệu |
| Unknown field drift | Client gửi field không còn được contract chấp nhận | Khác biệt parser, mass assignment hoặc dữ liệu bị bỏ qua |
| Enum/value drift | Service thêm hoặc đổi trạng thái | Client cũ rơi vào nhánh xử lý mặc định không an toàn |
| Semantic drift | Field giữ nguyên tên/type nhưng ý nghĩa thay đổi | Sai nghiệp vụ, sai quyền hoặc sai đơn vị |
| Validation drift | Gateway và service áp dụng rule khác nhau | Bypass validation hoặc request bị từ chối không nhất quán |
| Security contract drift | Scope, auth scheme hoặc object policy thay đổi | Quyền bị mở rộng hoặc client dùng credential sai |
| Routing/version drift | Gateway route v1 tới service v2 ngoài kế hoạch | Client nhận semantics không tương thích |
| Event schema drift | Producer và consumer dùng schema/version khác nhau | Event bị reject hoặc xử lý sai |
| Inventory drift | Route đang chạy nhưng không có contract/owner | Shadow API và bề mặt tấn công không được quản lý |

Nên tách **syntactic drift** (hình dạng dữ liệu khác) và **semantic drift** (ý nghĩa nghiệp vụ khác). Contract diff thường phát hiện syntactic change; semantic change cần review, test nghiệp vụ và telemetry.

## 3. Xác định nguồn chuẩn để đối chiếu

Không có một nguồn duy nhất mô tả đầy đủ API thực tế. Cần xác định nguồn chuẩn theo từng lớp:

| Nguồn | Dữ liệu chuẩn | Cần đối chiếu với |
|---|---|---|
| OpenAPI/protobuf/AsyncAPI | Contract được phê duyệt | Code, gateway, client SDK |
| Schema registry | Schema và compatibility rule của event/message | Producer, consumer, topic |
| API inventory | Owner, exposure, lifecycle, version | Gateway và runtime traffic |
| Gateway/ingress config | Route và policy đang triển khai | Contract, service deployment |
| Service deployment metadata | Build, commit, contract hash, version | Runtime request/response |
| Client registry/SDK release | Client app, supported API version | Traffic thực tế |
| Access log/metrics/traces | API và version thực sự được gọi | Lifecycle và contract registry |

Mỗi operation nên có định danh ổn định như service ID, route ID và operation ID. Không chỉ dựa vào raw URL vì path có thể chứa object ID hoặc route rewrite. Gắn thêm contract version/hash, deployed build và upstream version để có thể xác định drift bắt đầu từ thay đổi nào.

Nếu spec không có owner hoặc chưa biết spec nào được phê duyệt, không tự chọn một file bất kỳ làm nguồn chuẩn. Đánh dấu inventory chưa xác minh, gán owner và xử lý như một gap quản trị API.

## 4. Thiết lập baseline contract trước khi triển khai

Mỗi lần phát hành cần ghi nhận:

- Contract version và content hash.
- Service build/commit hoặc artifact version.
- Gateway route configuration version.
- Schema registry subject/version nếu có.
- API version được expose.
- Authentication/authorization policy version.
- Ngày phát hành và nhóm client được phép sử dụng.

Ví dụ deployment metadata:

~~~json
{
  "service": "order-api",
  "build": "2026.11.18.4",
  "contractVersion": "2.3.0",
  "contractHash": "sha256:8d1f...",
  "gatewayConfigVersion": "orders-edge-142",
  "apiVersions": ["v1", "v2"],
  "deployedAt": "2026-11-18T09:30:00Z"
}
~~~

Đây là metadata minh họa. Hash phải được tính từ canonical artifact hoặc file contract đã chuẩn hóa, tránh hash thay đổi chỉ vì thứ tự key/formatting không có ý nghĩa.

Sau deploy, runtime telemetry nên cho biết request nào đã đi qua route/build/contract version nào. Nếu deployed service và gateway đang dùng contract hash khác nhau ngoài kế hoạch, có thể phát cảnh báo drift ngay cả khi client chưa gặp lỗi.

## 5. Phát hiện breaking change trong CI/CD

Runtime monitoring phát hiện vấn đề sau khi traffic gặp phải. CI/CD cần chặn hoặc yêu cầu approval trước khi thay đổi contract có nguy cơ phá tương thích:

~~~text
Pull request
    |
    v
Parse current and proposed contract
    |
    v
Normalize operations and schemas
    |
    v
Classify compatibility changes
    |
    v
Check security policy and API inventory
    |
    v
Run provider and consumer contract tests
    |
    v
Require approval for breaking/security changes
    |
    v
Deploy canary and compare runtime telemetry
~~~

Các thay đổi cần được phân loại:

| Thay đổi | Tác động tương thích thường gặp | Hành động |
|---|---|---|
| Thêm optional request field | Thường tương thích với client cũ nếu server bỏ qua field không biết | Kiểm tra parser và unknown-field policy |
| Thêm required request field | Breaking với client không gửi field | Version mới hoặc migration có thời gian |
| Xóa request field đang dùng | Có thể làm client lỗi hoặc mất semantics | Đo usage, deprecate và migration |
| Thêm response field | Có thể phá client strict deserializer | Kiểm tra client behavior và SDK |
| Xóa response field | Breaking nếu client đang đọc field | Theo dõi usage và version mới |
| Đổi kiểu dữ liệu | Thường breaking | Version mới hoặc chuyển đổi tương thích |
| Thu hẹp enum | Client có thể nhận giá trị không còn hỗ trợ | Kiểm tra exhaustive handling |
| Thêm enum value | Client cũ có thể không hiểu giá trị mới | Yêu cầu client xử lý unknown value |
| Đổi format/constraint | Có thể làm client hoặc validator từ chối | Contract test và rollout |
| Đổi auth scope/issuer/audience | Thay đổi khả năng truy cập | Security review và migration |
| Đổi object/tenant semantics | Có thể gây truy cập sai dữ liệu | Security review bắt buộc |

Compatibility phụ thuộc hướng thay đổi và cách client deserialize. Ví dụ thêm field vào response thường được xem là additive, nhưng client dùng strict schema có thể từ chối. Không dùng nhãn backward-compatible của một công cụ làm bằng chứng duy nhất.

## 6. Phát hiện drift tại runtime

Khi request đi qua API, thu thập các tín hiệu có thể đối chiếu contract:

- Route ID, operation ID và API version đã resolve.
- Deployed build và contract hash.
- Kết quả request schema validation.
- Kết quả response contract validation theo sampling/canary.
- Unknown field hoặc enum value không được nhận diện.
- HTTP status/error code theo operation.
- Client app/version đã được xác minh hoặc phân loại.
- Upstream service/version.
- Authentication/authorization policy version.

Không cần lưu toàn bộ request/response body để phát hiện drift. Ưu tiên schema validator, parser instrumentation và structured event chỉ chứa field name, rule ID, schema version và request ID. Payload có thể chứa PII, token hoặc dữ liệu khách hàng.

Nếu response validation tốn chi phí, chạy đầy đủ trong staging/canary và sampling có kiểm soát ở production. Với field nhạy cảm hoặc security-critical, có thể kiểm tra metadata/shape mà không capture value.

## 7. Các metric hữu ích

Metric nên đo được tỷ lệ và xu hướng, không chỉ tổng số lỗi:

| Metric | Ý nghĩa | Phân nhóm nên có |
|---|---|---|
| api_requests_total | Lưu lượng API | service, route_id, api_version, status_class |
| request_schema_validation_failures_total | Request không khớp schema | route_id, schema_version, error_code |
| response_contract_violations_total | Response không khớp contract | route_id, contract_version, violation_type |
| unknown_field_total | Field lạ hoặc bị loại bỏ | route_id, field_category, schema_version |
| unknown_enum_value_total | Enum/value chưa được nhận diện | route_id, field_name, schema_version |
| api_deprecated_version_requests_total | Request tới version deprecated | service, route_id, api_version |
| api_unsupported_version_requests_total | Request tới version không hỗ trợ | service, route_id, api_version |
| api_version_client_mismatch_total | Client khai báo version không phù hợp route/SDK | client_family, route_id |
| gateway_contract_hash_mismatch | Gateway và service contract hash lệch | service, route_id |
| api_auth_policy_mismatch | Runtime policy không khớp policy được phê duyệt | service, route_id, policy_version |
| consumer_schema_rejection_total | Consumer từ chối event schema | topic, consumer_group, schema_version |

Các metric dạng counter cần được đọc theo rate hoặc tỷ lệ trên tổng request. Một con số tăng có thể chỉ phản ánh traffic tăng; tỷ lệ lỗi và mức độ ảnh hưởng mới giúp quyết định severity.

### 7.1 Tránh cardinality bùng nổ

Không dùng raw URL, user ID, email, object ID, token, request ID hoặc tenant ID không giới hạn làm metric label. Mỗi giá trị mới có thể tạo một time series riêng và làm hệ thống metrics quá tải.

Dùng route template/route ID, version, status class, error code có allowlist và nhóm client ổn định. Chi tiết theo consumer hoặc tenant cần điều tra nên nằm trong log/event có retention, access control và truy vấn phù hợp; chỉ dùng metric label nếu số lượng được giới hạn rõ.

Không đặt payload value hoặc tên field do attacker tùy ý gửi thành label. Chuẩn hóa field name theo contract registry hoặc gom vào category như unknown_field.

## 8. Theo dõi version cũ đang được sử dụng

Để biết version nào còn traffic, cần kết hợp:

- Version trong path, ví dụ /v1 hoặc /v2.
- Media type/version parameter nếu API version theo header.
- Contract/route ID đã được gateway resolve.
- Client application ID từ credential đã xác minh.
- SDK/app version từ metadata được đăng ký hoặc attestation phù hợp.
- Consumer/partner registry và lịch sử phát hành.

Không tin một header tự khai báo như X-API-Version hoặc User-Agent như bằng chứng xác thực. Client có thể sửa chúng. Chúng hữu ích cho phân tích tương thích, nhưng version thực thi phải được xác định từ route/contract đã match; client identity nên lấy từ credential hoặc registry.

Đối với version trong URL, gateway có thể phân loại rõ v1/v2. Với version qua media type hoặc header, parser phải kiểm tra cú pháp và map tới version đã được hỗ trợ. Không cho client gửi version bất kỳ để kích hoạt code path cũ.

Theo dõi số request, số consumer duy nhất đã xác minh, số tenant bị ảnh hưởng, last-seen time và operation nào còn được gọi. Không chỉ nhìn tổng traffic vì một integration quan trọng có thể chiếm phần nhỏ nhưng vẫn là phụ thuộc bắt buộc.

## 9. Lifecycle của API version

Version nên có trạng thái rõ trong inventory:

| Trạng thái | Ý nghĩa | Monitoring cần làm |
|---|---|---|
| Draft | Đang phát triển, chưa expose | Không kỳ vọng public traffic |
| Active | Được hỗ trợ | Theo dõi SLO và contract |
| Deprecated | Đã thông báo ngừng khuyến nghị | Đo consumer còn dùng và cảnh báo owner |
| Sunset scheduled | Có ngày ngừng cụ thể | Theo dõi migration theo deadline |
| Retired | Đã ngừng hỗ trợ/expose | Cảnh báo mọi request mới hoặc route còn tồn tại |

Deprecation và retirement là hai thời điểm khác nhau. Một version deprecated có thể vẫn chạy trong thời gian chuyển đổi. Không chặn ngay khi gắn nhãn deprecated nếu chưa có kế hoạch migration và thông báo consumer.

Khi retire, phải xác minh gateway route, ingress, load balancer và upstream đều đã gỡ hoặc chặn version cũ. Nếu route cũ vẫn hoạt động nhưng inventory ghi retired, đây là drift có rủi ro bảo mật.

## 10. Cảnh báo theo mốc deprecation và sunset

Một kế hoạch deprecation nên ghi:

- Version/operation bị ảnh hưởng.
- Owner của API và owner từng consumer.
- Ngày công bố deprecation.
- Ngày sunset dự kiến.
- Thay thế bằng version/operation nào.
- Migration guide và khác biệt contract.
- Điều kiện gia hạn ngoại lệ.
- Người phê duyệt nếu còn consumer sau deadline.

Các mốc cảnh báo có thể gồm:

1. Khi version được đánh dấu deprecated: thông báo owner và consumer đã biết.
2. Trước sunset theo các mốc tổ chức chọn: nhắc consumer còn traffic.
3. Khi traffic tăng hoặc xuất hiện consumer mới trên version cũ: cảnh báo sớm.
4. Khi còn consumer trọng yếu gần deadline: escalation tới owner và product.
5. Sau sunset: mọi request mới là cảnh báo; route còn active phải được điều tra.

Thời gian cụ thể phụ thuộc hợp đồng với partner, chu kỳ phát hành client và mức rủi ro. Không áp dụng một lịch chung cho mọi API.

## 11. Phát hiện client version cũ và consumer không rõ danh tính

Client version khác API version. Ví dụ mobile app phiên bản cũ có thể vẫn gọi API v2; ngược lại, một client mới có thể còn gọi API v1 vì chưa migration.

Theo dõi riêng:

- API version/route được gọi.
- Client application hoặc partner identity đã xác minh.
- SDK/app release được đăng ký.
- Platform và environment nếu cần.
- Consumer owner và trạng thái migration.
- Last successful request và last failed request.

Nếu request không có client identity, vẫn ghi nhận traffic là unknown consumer. Không tự gán một user-agent thành danh tính. Một lượng traffic unknown tới version retired có thể là scan, client tự phát hoặc integration chưa đăng ký; cần phân tích thêm trước khi block.

Với mobile/desktop client, không thể giả định mọi người dùng nâng cấp ngay. Dùng remote configuration, minimum supported version hoặc forced upgrade chỉ khi sản phẩm có cơ chế và kế hoạch hỗ trợ. Server vẫn phải enforce version policy; UI cảnh báo không phải security control.

## 12. Cảnh báo semantic drift và security drift

Schema shape không thay đổi vẫn có thể phát sinh drift nguy hiểm:

- Field amount đổi đơn vị từ cents sang currency major unit.
- status giữ kiểu string nhưng thêm trạng thái có quyền cao hơn.
- ownerId giữ nguyên kiểu nhưng semantics đổi từ creator sang current owner.
- Field optional bắt đầu ảnh hưởng authorization khi có mặt.
- API giữ nguyên route nhưng bỏ kiểm tra tenant/object.
- Scope được đổi hoặc security requirement bị xóa ở một operation.
- Response bắt đầu chứa field internal hoặc PII.

Các trường hợp này cần tín hiệu ngoài schema validator:

- Authorization deny/allow rate thay đổi bất thường.
- Object access từ tenant khác tăng.
- Response field classification vi phạm policy.
- Business invariant hoặc state transition bị từ chối/tăng bất thường.
- Security policy hash khác bản đã phê duyệt.
- Audit cho thấy principal/tenant context không như dự kiến.

Security-critical contract change cần review thủ công và test negative. Không chỉ dựa vào việc metric schema violation bằng 0 để kết luận an toàn.

## 13. Schema drift trong API bất đồng bộ

Với message/event API, producer và consumer có thể deploy độc lập. Một schema mới có thể được producer phát ra trước khi consumer hỗ trợ, hoặc consumer mới nhận message cũ còn nằm trong retention/replay.

Theo dõi:

- Schema subject/version và compatibility mode.
- Producer workload và schema version đang publish.
- Consumer group và schema version được hỗ trợ.
- Serialization/deserialization failure.
- Unknown field/enum và dead-letter count.
- Retry, lag và tuổi message.
- Replay/backfill đang sử dụng schema nào.

Compatibility phải xét cả lịch sử message trong broker, không chỉ message mới. Consumer có thể đọc lại event nhiều ngày hoặc nhiều tháng tuổi. Nếu bỏ hỗ trợ schema cũ, cần kiểm tra retention, archive và replay workflow.

Với event evolution, ưu tiên thay đổi additive có semantics rõ, giữ khả năng đọc dữ liệu cũ và áp dụng schema compatibility rule phù hợp. Thay đổi auth context, tenant field hoặc meaning của event cần security/domain review.

## 14. Alert design: từ tín hiệu tới cảnh báo có thể hành động

Không biến mọi metric tăng thành page. Một alert tốt có:

- Điều kiện đo rõ.
- Ngưỡng hoặc baseline phù hợp.
- Thời gian duy trì để tránh spike ngắn.
- Severity dựa trên security/availability impact.
- Nhóm owner chịu trách nhiệm.
- Link dashboard, trace/log query và runbook.
- Hành động dự kiến hoặc tiêu chí escalation.

Ví dụ phân loại:

| Tình huống | Mức cảnh báo gợi ý | Hành động |
|---|---|---|
| Một vài request sai schema từ client thử nghiệm | Info/low | Ghi nhận, không page |
| Tỷ lệ validation failure tăng sau deploy | Warning | So sánh contract hash/build và rollback nếu cần |
| Gateway/service contract hash mismatch trên public route | High | Kiểm tra route và policy, dừng rollout |
| Response contract vi phạm có field nhạy cảm | Critical | Chặn exposure/rollback và điều tra dữ liệu đã trả |
| Client trọng yếu vẫn dùng version deprecated gần sunset | Warning | Liên hệ owner, xác nhận migration |
| Version retired vẫn nhận traffic | High | Xác minh route còn mở, block theo kế hoạch |
| API auth policy drift hoặc scope yếu đi | Critical | Security incident workflow |
| Consumer reject hàng loạt schema mới | High | Dừng producer rollout hoặc rollback schema |

Severity phải dựa vào impact và khả năng khai thác. Không page đội on-call chỉ vì một client gửi field lạ; nhưng một thay đổi làm lộ PII hoặc bỏ object authorization cần escalation ngay cả khi số request còn thấp.

## 15. Ngưỡng, tỷ lệ và cửa sổ đánh giá

Chọn ngưỡng theo baseline của từng API:

- Tỷ lệ schema validation failure trên tổng request hợp lệ.
- Tỷ lệ response contract violation theo route/version.
- Số consumer còn gọi version deprecated.
- Request volume tới version retired.
- Số operation có contract hash mismatch.
- Thời gian từ deploy đến khi xuất hiện drift.
- Consumer lag/DLQ tăng sau schema rollout.

Không đặt ngưỡng tuyệt đối giống nhau cho endpoint có 10 request/ngày và endpoint có hàng triệu request/giờ. Với volume thấp, dùng count và thời gian dài hơn; với volume cao, dùng tỷ lệ, burn rate hoặc baseline theo mùa.

Ví dụ điều kiện minh họa:

~~~text
warning:
  schema_failure_ratio > 2%
  for 10 minutes
  and request_count >= minimum_sample

critical:
  sensitive_response_violation > 0
  for any confirmed occurrence

sunset:
  retired_version_request_count > 0
  after retirement deadline
~~~

Đây không phải ngưỡng mặc định cho mọi hệ thống. Mức 2%, cửa sổ 10 phút và minimum sample cần hiệu chỉnh bằng dữ liệu thực tế, SLO và mức độ nghiêm trọng.

## 16. Dashboard theo dõi contract và version

Dashboard nên giúp trả lời nhanh:

1. Version nào đang nhận traffic?
2. Consumer nào còn sử dụng version deprecated?
3. Schema failure bắt đầu sau deploy nào?
4. Gateway, service và schema registry có cùng version/hash không?
5. Operation nào có response drift hoặc unknown enum?
6. Có route retired nào vẫn public không?
7. Consumer group nào reject schema hoặc tăng DLQ?

Các panel hữu ích:

- Request rate theo route/version/status.
- Schema validation failure ratio theo route/version.
- Response contract violation theo service/build.
- Deprecated/retired version traffic theo thời gian.
- Consumer count và last-seen theo client registry.
- Contract hash mismatch theo deployment.
- Auth policy drift và security decision anomaly.
- Schema rejection, consumer lag, retry và DLQ.
- Sunset countdown và danh sách owner chưa migration.

Không đưa raw user ID, URL có object ID hoặc token vào dashboard label. Drill-down sang log/trace có quyền truy cập để xem chi tiết.

## 17. Log và trace để điều tra drift

Structured log cho mỗi request có thể ghi:

- Timestamp và request/correlation ID.
- Service, route ID, operation ID.
- API version được resolve.
- Client application ID đã xác minh hoặc unknown.
- Deployed build, contract hash và policy version.
- Request/response schema validation result.
- Error code và status class.
- Upstream service/version.
- Tenant classification hoặc tenant pseudonym nếu cần và được phép.

Trace có thể cho thấy gateway, service và dependency nào xử lý request, giúp xác định drift ở hop nào. Không capture toàn bộ body mặc định. Nếu cần sample payload để điều tra, phải redaction field nhạy cảm, giới hạn sampling, retention và quyền truy cập.

Khi log unknown field, ghi tên field theo allowlist/registry và số lượng; không ghi giá trị field. Một field lạ có thể chứa token hoặc PII.

## 18. Correlate drift với deployment

Khi metric lỗi tăng, câu hỏi đầu tiên thường là thay đổi nào vừa được rollout. Cần liên kết:

- Build/commit và deployment timestamp.
- Contract hash trước/sau.
- Gateway config version.
- Schema registry version.
- Client SDK release.
- Policy version.
- Canary percentage và rollout phase.

Nếu drift bắt đầu ngay sau khi gateway route chuyển upstream version mới, có thể khoanh vùng nhanh. Nếu chỉ một client app version gặp lỗi, tập trung vào SDK/parser của client. Nếu nhiều consumer reject cùng schema version, dừng producer rollout và kiểm tra compatibility.

Không tự động rollback chỉ vì metric tăng. Xác định change correlation, phạm vi ảnh hưởng và khả năng dữ liệu đã được ghi/publish. Với security regression, ưu tiên containment và rollback policy an toàn; với lỗi tương thích, có thể cần dual-read/dual-write hoặc adapter có thời hạn.

## 19. Runbook khi phát hiện schema drift

Khi alert schema drift:

1. Xác định service, route/operation, version và consumer bị ảnh hưởng.
2. Xác định contract hash, build và gateway config trước/sau thời điểm bắt đầu.
3. Phân biệt request drift, response drift, enum drift, semantic drift hay policy drift.
4. Xác định drift ảnh hưởng client nào, tenant nào và có field nhạy cảm hay không.
5. Kiểm tra raw payload chỉ khi thật cần, qua công cụ được kiểm soát và đã redaction.
6. Dừng canary/rollout nếu thay đổi mới là nguyên nhân có khả năng cao.
7. Nếu có exposure hoặc authorization regression, chặn route/field hoặc rollback ngay theo incident process.
8. Nếu là compatibility issue, khôi phục contract tương thích hoặc triển khai adapter/version mới.
9. Cập nhật contract registry và API inventory sau khi thống nhất nguồn chuẩn.
10. Thêm regression test và theo dõi metric tới khi trở lại baseline.

## 20. Runbook khi version cũ vẫn có traffic

Khi version deprecated/retired còn request:

1. Xác nhận version thực tế từ route đã resolve, không chỉ từ header tự khai báo.
2. Xác định client application/partner bằng credential hoặc registry.
3. Kiểm tra owner, tenant và operation còn được gọi.
4. Phân biệt client hợp lệ, integration chưa đăng ký, scan hoặc traffic bất thường.
5. Liên hệ owner qua kênh vận hành đã thống nhất và cung cấp migration path.
6. Đặt deadline hoặc ngoại lệ có người phê duyệt, lý do và ngày hết hạn.
7. Theo dõi last-seen và traffic trend của từng consumer.
8. Trước khi block, xác minh không còn dependency trọng yếu và có rollback plan.
9. Sau retirement, block route ở gateway và direct upstream path.
10. Cảnh báo mọi request mới, cập nhật inventory và giữ audit evidence.

Không block một partner production chỉ dựa trên User-Agent hoặc một metric aggregate. Cần xác minh client identity và hợp đồng hỗ trợ.

## 21. Bảo vệ dữ liệu telemetry

Telemetry của API có thể chứa dữ liệu nhạy cảm. Monitoring an toàn phải:

- Không ghi access token, API key, cookie, password hoặc signed URL.
- Không ghi request/response body đầy đủ theo mặc định.
- Không dùng tenant/user/object ID làm metric label không giới hạn.
- Pseudonymize client/tenant identifier khi có thể.
- Phân quyền dashboard, log query và trace.
- Đặt retention theo mục đích vận hành và điều tra.
- Mã hóa dữ liệu telemetry khi truyền và lưu.
- Audit truy cập vào dữ liệu monitoring nhạy cảm.
- Tách metric tổng hợp khỏi forensic record chi tiết.

Không hạ privacy để tăng độ chi tiết của alert. Có thể phát hiện drift bằng schema version, field name, error code và count mà không cần thu thập giá trị thực của payload.

## 22. Kiểm thử monitoring và alert

Monitoring rule cần được kiểm thử như code:

| Test | Cách tạo tín hiệu | Kết quả mong đợi |
|---|---|---|
| Request schema drift | Client gửi field/type không khớp schema | Counter tăng đúng route/version |
| Response drift | Canary service trả response sai contract | Violation được phát hiện |
| Enum drift | Trả enum value mới cho client cũ | Unknown enum signal tăng |
| Gateway mismatch | Triển khai contract hash lệch có kiểm soát | Alert contract mismatch |
| Deprecated version | Gọi API version đã deprecated | Metric/version inventory cập nhật |
| Retired version | Gọi route sau sunset trong staging | Alert retired traffic |
| Client identity | Gọi thiếu credential hoặc dùng client ID giả | Không gán thành consumer đã xác minh |
| Low traffic | Tạo một lỗi trên endpoint ít request | Không gây page sai do tỷ lệ nhỏ mẫu |
| High volume | Tạo lỗi kéo dài trên endpoint nhiều traffic | Alert trong thời gian mục tiêu |
| Sensitive field exposure | Canary response có field bị cấm | Critical alert và containment path |
| Event schema | Producer phát schema không tương thích | Registry/consumer rejection được phát hiện |
| Alert routing | Trigger alert trong test environment | Đúng owner, severity, runbook |
| Recovery | Khôi phục contract/version | Alert clear theo điều kiện recovery |

Kiểm tra cả false positive và false negative. Một alert không bao giờ trigger có thể do rule sai hoặc metric không được emit; alert trigger liên tục có thể bị người vận hành bỏ qua.

## 23. Các lỗi thiết kế thường gặp

1. **Chỉ kiểm tra OpenAPI trong CI:** không phát hiện route hoặc runtime contract đã drift.
2. **Chỉ nhìn 4xx tổng:** không biết lỗi thuộc schema, version, auth hay client cụ thể.
3. **Tin User-Agent/X-API-Version:** client có thể giả mạo metadata.
4. **Dùng raw URL làm metric label:** cardinality tăng và có thể lộ object ID.
5. **Không lưu contract hash:** khó biết service và gateway đang dùng spec nào.
6. **Xem mọi additive change là an toàn:** strict client hoặc semantic change vẫn có thể lỗi.
7. **Không theo dõi consumer identity:** biết v1 còn traffic nhưng không biết ai cần migration.
8. **Block version cũ ngay khi deprecated:** làm hỏng integration chưa có kế hoạch chuyển.
9. **Không retire direct upstream path:** gateway đã gỡ nhưng service vẫn public.
10. **Không giữ lịch sử schema cho event:** replay message cũ thất bại.
11. **Chỉ cảnh báo theo số lượng:** không xét tỷ lệ, baseline, sample size và impact.
12. **Page cho mọi unknown field:** gây alert fatigue và che tín hiệu quan trọng.
13. **Không phân biệt syntactic và semantic drift:** schema validator pass nhưng nghiệp vụ đã đổi.
14. **Capture payload để debug mặc định:** telemetry trở thành nơi chứa PII/secret.
15. **Không có owner/runbook:** cảnh báo được gửi nhưng không ai biết phải xử lý gì.

## 24. Quy trình thiết kế cảnh báo schema drift và version cũ

Với mỗi API hoặc event contract:

1. Đăng ký owner, operation, exposure, lifecycle và version được hỗ trợ.
2. Lưu contract/schema version, canonical hash và deployment metadata.
3. Chạy semantic contract diff và compatibility test trong CI.
4. Xác định breaking/security change cần approval.
5. Emit runtime metric cho request/response validation, unknown field/enum và contract mismatch.
6. Gắn route ID, API version, build và policy version vào telemetry.
7. Xác định client identity từ credential/registry; đánh dấu unknown nếu chưa xác minh.
8. Theo dõi consumer còn dùng version deprecated theo last-seen, volume và owner.
9. Thiết lập deprecation/sunset milestone và ngoại lệ có thời hạn.
10. Đặt alert theo impact, tỷ lệ, sample size, duration và security severity.
11. Tạo dashboard/runbook có owner, link log/trace và hành động cụ thể.
12. Kiểm thử alert, routing, recovery và privacy trước production.
13. Khi drift xảy ra, correlate với deploy, containment/rollback hoặc migration.
14. Khi retired, xác minh gateway, ingress, load balancer và direct upstream đều đóng.
15. Review inventory, consumer registry và policy định kỳ.

## 25. Checklist rà soát

- [ ] Có contract/schema registry và API inventory với owner, version và lifecycle.
- [ ] Lưu contract hash, gateway config version, service build và policy version.
- [ ] CI phân loại breaking change, security change và semantic change.
- [ ] Có provider/consumer contract test và schema compatibility test.
- [ ] Runtime đo request validation failure và response contract violation.
- [ ] Có tín hiệu unknown field, enum, route và policy mismatch.
- [ ] Version được xác định từ route/contract đã resolve; header/User-Agent chỉ là metadata bổ sung.
- [ ] Client/partner identity được xác minh trước khi gán owner cho traffic version cũ.
- [ ] Có metric last-seen, request volume và consumer còn dùng deprecated version.
- [ ] Có deprecation/sunset date, migration guide và ngoại lệ có owner.
- [ ] Route retired vẫn được kiểm tra ở gateway, ingress, load balancer và upstream.
- [ ] Alert có severity, threshold, sample size, duration, owner và runbook.
- [ ] Dashboard cho biết version, operation, consumer và deployment liên quan.
- [ ] Correlation log/trace không capture secret hoặc payload nhạy cảm mặc định.
- [ ] Metric label có cardinality giới hạn; không chứa raw ID hoặc URL.
- [ ] Có test false positive/negative, alert routing và recovery.
- [ ] Có runbook cho schema drift, security drift và version cũ còn traffic.
- [ ] Telemetry có access control, encryption, retention và audit.

Schema drift và version cũ là dấu hiệu cho thấy contract, deployment và consumer không còn đồng bộ. Kết hợp contract diff trước deploy, runtime validation signals, inventory version, client identity đã xác minh và alert theo mức ảnh hưởng giúp phát hiện lỗi tương thích trước khi lan rộng, đồng thời nhận ra API cũ còn mở hoặc đã mất các kiểm soát bảo mật cần thiết.
