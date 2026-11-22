# Phân bổ bằng chứng cho hệ thống microservices và nhiều nhóm phát hành

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao hệ thống microservices cần phân bổ bằng chứng kiểm thử theo ranh giới service, hợp đồng và hành trình nghiệp vụ.
- Phân biệt bằng chứng ở cấp service, contract, integration, system/E2E và vận hành production.
- Xác định trách nhiệm tạo, review, lưu trữ và sử dụng bằng chứng giữa service owner, consumer team, platform team và release owner.
- Lựa chọn kiểm thử phù hợp với khả năng triển khai độc lập và tình trạng nhiều phiên bản cùng tồn tại.
- Thiết kế ma trận bằng chứng cho API đồng bộ, event bất đồng bộ, dữ liệu dùng chung và dependency bên ngoài.
- Đánh giá rủi ro tương thích giữa provider, consumer, schema, cấu hình và phiên bản triển khai.
- Xây dựng bộ bằng chứng phát hành có thể truy nguyên đến commit, artifact, cấu hình, môi trường và kết quả kiểm thử.
- Điều phối cổng chất lượng khi nhiều nhóm phát hành theo lịch khác nhau.
- Xử lý khoảng trống bằng chứng, test flaky, môi trường không đồng nhất và rủi ro chưa được kiểm chứng.
- Sử dụng telemetry sau phát hành để bổ sung bằng chứng và cải thiện chiến lược kiểm thử.

## 1. Vì sao cần phân bổ bằng chứng trong microservices?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, bằng chứng kiểm thử là thông tin có thể kiểm tra được, hỗ trợ kết luận rằng một yêu cầu, rủi ro hoặc thuộc tính chất lượng đã được xác minh trong điều kiện xác định. Bằng chứng có thể là kết quả test, báo cáo contract, dữ liệu đối soát, log, metric, trace, kết quả migration, kiểm tra bảo mật hoặc tín hiệu sau triển khai.

Trong hệ thống microservices, một hành trình nghiệp vụ thường đi qua nhiều service do các nhóm khác nhau sở hữu. Mỗi service có mã nguồn, dữ liệu, API, event, pipeline và nhịp phát hành riêng. Một thay đổi ở service A có thể ảnh hưởng đến consumer B, event handler C, báo cáo D và trải nghiệm người dùng cuối. Không một nhóm đơn lẻ có thể kiểm tra đầy đủ mọi chi tiết nội bộ của tất cả service, nhưng mỗi nhóm vẫn cần bằng chứng đủ mạnh để biết phần mình sở hữu hoạt động đúng và không phá vỡ hợp đồng với phần còn lại.

Ví dụ, hành trình đặt hàng có thể đi qua API Gateway, Order service, Pricing service, Payment service, Inventory service và Notification service. Order team có thể kiểm tra logic tạo đơn và trạng thái đơn; Payment team xác minh xử lý giao dịch và callback; Inventory team xác minh giữ hàng và giải phóng hàng; nhóm tích hợp xác minh event và luồng xuyên service. Một số kiểm tra cần chạy độc lập trong pipeline từng nhóm, một số cần chạy ở môi trường tích hợp và một số cần được quan sát sau khi phát hành.

Nếu mọi bằng chứng chỉ tập trung ở một bộ E2E lớn, pipeline có thể chậm, lỗi khó định vị và trách nhiệm không rõ. Nếu mỗi nhóm chỉ kiểm tra service của mình mà không có bằng chứng hợp đồng hoặc hành trình xuyên service, lỗi tích hợp có thể lọt. Vì vậy, cần phân bổ bằng chứng theo rủi ro và ranh giới trách nhiệm, đồng thời giữ liên kết giữa các lớp kiểm tra.

Phân bổ tốt giúp:

- Mỗi nhóm chịu trách nhiệm rõ về chất lượng service và hợp đồng do mình cung cấp hoặc tiêu thụ.
- Phát hiện lỗi sớm ở cấp phù hợp, giảm phụ thuộc vào E2E.
- Kiểm tra được tương thích khi provider và consumer phát hành độc lập.
- Tạo bộ bằng chứng phát hành có thể tổng hợp qua nhiều pipeline.
- Giảm việc chạy lại toàn bộ hệ thống cho mọi thay đổi nhỏ.
- Nhận diện phần chưa có bằng chứng và rủi ro còn lại trước khi phát hành.
- Duy trì khả năng truy nguyên từ yêu cầu đến test, artifact và phiên bản production.

## 2. Hiểu bằng chứng kiểm thử và đơn vị cần phân bổ

Bằng chứng không chỉ là dòng “test passed”. Một kết quả có giá trị cần cho biết đã kiểm tra điều gì, trong điều kiện nào, với phiên bản nào và giới hạn kết luận ra sao.

### 2.1. Thành phần của một bằng chứng có thể sử dụng

Một bản ghi bằng chứng nên có các thông tin phù hợp:

- **Mục tiêu**: yêu cầu, rủi ro, hợp đồng hoặc thuộc tính chất lượng cần xác minh.
- **Phạm vi**: service, API, event, hành trình, dữ liệu hoặc môi trường.
- **Phiên bản**: commit, build, artifact, schema và cấu hình liên quan.
- **Phương pháp**: loại test, công cụ, kịch bản hoặc phép đo.
- **Điều kiện**: dữ liệu, dependency, tải, feature flag và topology.
- **Kết quả**: Pass, Fail, Blocked, Skipped hoặc Inconclusive cùng thông tin chi tiết.
- **Nguồn**: report, log, trace, artifact hoặc liên kết đến hệ thống lưu trữ.
- **Thời điểm**: lúc chạy, thời hạn hiệu lực và cửa sổ quan sát nếu có.
- **Người sở hữu**: nhóm tạo bằng chứng và người review khi cần.
- **Giới hạn**: điều chưa được kiểm tra, mock/fake đã dùng và giả định còn tồn tại.

Một báo cáo chỉ có “142 tests passed” không cho biết những rủi ro nào được kiểm tra. Một báo cáo tốt hơn liên kết tập test với service, commit, hợp đồng, môi trường và các điều kiện thực thi.

### 2.2. Các đơn vị bằng chứng

| Đơn vị | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Service | Order service, Payment service | Logic và trạng thái nội bộ của service có đúng không? |
| Interface/contract | REST API, gRPC, event schema | Provider và consumer có hiểu cùng một hợp đồng không? |
| Dependency | Database, queue, cache, external API | Tương tác với dependency có đúng trong điều kiện liên quan không? |
| Hành trình nghiệp vụ | Đặt hàng, thanh toán, hoàn tiền | Các service phối hợp có tạo ra kết quả người dùng cần không? |
| Thuộc tính hệ thống | Latency, availability, security, recovery | Hệ thống có đáp ứng mục tiêu phi chức năng không? |
| Release unit | Một service, nhóm service hoặc sản phẩm | Bộ bằng chứng có đủ cho phiên bản và phạm vi phát hành không? |

### 2.3. Bằng chứng khác với coverage

Coverage cho biết phần mã hoặc yêu cầu nào đã được thực thi hay liên kết với test theo một định nghĩa cụ thể. Coverage không tự chứng minh assertion có đúng hoặc kết quả nghiệp vụ đã được xác minh. Một service có 90% line coverage vẫn có thể thiếu test cho tương thích API, retry, dữ liệu cũ hoặc tương tác với consumer.

Hãy dùng coverage như một tín hiệu để tìm khoảng trống, kết hợp với chất lượng assertion, rủi ro, hợp đồng và kết quả tích hợp. Không dùng một tỷ lệ coverage đơn lẻ làm bằng chứng duy nhất cho quyết định phát hành.

## 3. Các lớp bằng chứng trong kiến trúc microservices

Mỗi lớp trả lời một loại câu hỏi. Phân bổ hợp lý giúp kiểm tra nhanh ở nơi có thể và giữ kiểm tra xuyên hệ thống cho những rủi ro chỉ xuất hiện khi các thành phần phối hợp.

### 3.1. Bằng chứng cấp service

Service owner tạo bằng chứng cho logic và hành vi mà service kiểm soát:

- Unit test cho quy tắc nghiệp vụ, validation, mapping và chuyển trạng thái.
- Component test cho tương tác nội bộ trong service.
- Test với database adapter, repository hoặc transaction theo phạm vi.
- Test bảo mật cho authorization, tenant isolation và dữ liệu nhạy cảm.
- Test migration và tương thích dữ liệu do service sở hữu.
- Kiểm tra cấu hình, startup, health và hành vi khi dependency lỗi.

Bằng chứng cấp service nên chạy nhanh và gắn với commit hoặc artifact. Các test cần dependency thật có thể dùng container hoặc môi trường cô lập. Mục tiêu là xác minh trách nhiệm nội bộ của service mà không phải dựng toàn bộ hệ thống.

### 3.2. Bằng chứng contract

Contract test xác minh provider và consumer cùng tuân theo hợp đồng giao tiếp. Hợp đồng có thể bao gồm:

- HTTP method, path, header, status và schema.
- Kiểu dữ liệu, nullability, enum và trường bắt buộc/tùy chọn.
- Quy tắc xác thực, authorization và error response.
- gRPC method, message và status code.
- Event name, schema version, key và semantics.
- Quy tắc tương thích và deprecation.

Contract test đặc biệt quan trọng khi nhóm phát hành độc lập. Consumer có thể kiểm tra nhu cầu của mình với contract; provider xác minh implementation đáp ứng những contract đã được chấp nhận. Kết quả cần gắn với phiên bản contract và consumer/provider version.

Contract test không chứng minh mọi hành vi runtime, hiệu năng hay độ tin cậy của dependency thật. Nó là bằng chứng về giao diện và semantics đã mô tả, cần bổ sung integration test cho rủi ro ở tầng thực thi.

### 3.3. Bằng chứng integration

Integration test xác minh service tương tác với dependency hoặc service khác trong một môi trường có kiểm soát. Ví dụ:

- Order service ghi dữ liệu và phát event qua outbox.
- Payment adapter gọi sandbox provider và xử lý callback.
- Consumer đọc message từ broker và cập nhật trạng thái.
- Service sử dụng cache hoặc database theo cấu hình triển khai.

Nên chọn ranh giới có rủi ro thực tế và kiểm soát dữ liệu, phiên bản, quota. Không cần dựng mọi service thật cho mọi test; fake hoặc stub có thể phù hợp khi câu hỏi chỉ liên quan đến logic service. Khi cần xác minh giao thức, transaction hoặc serialization thật, phải có kiểm tra với dependency thực tương ứng.

### 3.4. Bằng chứng system/E2E

System hoặc E2E test xác minh hành trình quan trọng qua nhiều thành phần từ góc nhìn người dùng hoặc client tích hợp. Ví dụ tạo đơn, thanh toán, giữ hàng và nhận xác nhận.

Giữ E2E cho những rủi ro cần chứng minh sự phối hợp xuyên ranh giới. Bộ E2E nên tập trung vào hành trình quan trọng, trạng thái cuối và một số nhánh lỗi có hậu quả lớn. Nếu E2E thất bại, cần có correlation ID, log và trace để xác định service hoặc ranh giới gây lỗi.

### 3.5. Bằng chứng vận hành sau phát hành

Telemetry production cung cấp bằng chứng về điều kiện thực tế:

- SLI/SLO, latency, error rate và availability.
- Queue lag, retry, dead-letter và dependency health.
- Business metric như đơn hàng hoàn tất, thanh toán trùng hoặc đối soát lệch.
- Trace và log có cấu trúc.
- Canary analysis, synthetic monitoring và phản hồi người dùng.

Telemetry không thay thế kiểm thử trước phát hành. Nó giúp xác nhận giả định, phát hiện điều kiện chưa được mô phỏng và bổ sung dữ liệu cho chu kỳ kiểm thử tiếp theo.

### 3.6. Phân bổ theo rủi ro, không theo số lượng test cố định

Không cần mọi service có cùng tỷ lệ unit, contract, integration và E2E. Service tính toán thuần có thể cần nhiều unit test; service phát event cho nhiều consumer cần contract/schema test; service xử lý thanh toán có thể cần thêm integration, idempotency, reconciliation và security test. Phân bổ dựa trên ranh giới và hậu quả lỗi.

## 4. Xác định ranh giới trách nhiệm giữa các nhóm

Trong tổ chức có nhiều nhóm phát hành, bằng chứng cần có owner rõ. Trách nhiệm không nên bị bỏ trống ở ranh giới giữa provider và consumer.

### 4.1. Provider team

Nhóm sở hữu service cung cấp interface chịu trách nhiệm:

- Công bố và version hóa API/event contract.
- Kiểm tra implementation tuân theo contract.
- Duy trì compatibility policy và thông tin deprecation.
- Kiểm tra thay đổi schema, dữ liệu và hành vi lỗi.
- Cung cấp release notes, artifact và bằng chứng liên quan.
- Theo dõi lỗi phát sinh từ service và phản hồi cho consumer.

### 4.2. Consumer team

Nhóm sử dụng interface chịu trách nhiệm:

- Mô tả nhu cầu thực tế của consumer trong contract.
- Kiểm tra client mapping, error handling, timeout và retry.
- Xác minh consumer xử lý trường mới, enum mới và trạng thái không biết theo chính sách.
- Duy trì test cho hành vi mà consumer yêu cầu.
- Theo dõi thay đổi provider có thể ảnh hưởng đến hành trình của mình.

Consumer không nên giả định provider luôn giữ nguyên implementation; provider cũng không nên giả định mọi consumer nâng cấp cùng lúc.

### 4.3. Platform/SRE team

Nhóm nền tảng hoặc vận hành thường chịu trách nhiệm về:

- Runner, môi trường tích hợp, service discovery và network.
- Observability, telemetry pipeline và dashboard dùng chung.
- Secret, identity, certificate và cơ chế truy cập môi trường.
- Năng lực, quota, autoscaling và độ tin cậy nền tảng.
- Công cụ điều phối bằng chứng hoặc quality gate cấp tổ chức.
- Runbook, incident coordination và khả năng phục hồi nền tảng.

Platform team không sở hữu mọi kết quả nghiệp vụ của service. Service owner vẫn phải xác minh hành vi và tín hiệu nghiệp vụ do service tạo ra.

### 4.4. Release owner hoặc release coordinator

Release owner tổng hợp trạng thái và xác nhận bộ bằng chứng cần thiết đã có:

- Phạm vi release và service version liên quan.
- Danh sách test bắt buộc cùng kết quả.
- Contract compatibility và migration status.
- Rủi ro còn lại, ngoại lệ và người chấp nhận.
- Kế hoạch rollout, monitoring và rollback.
- Xác nhận của các owner cần thiết theo chính sách.

Release owner không thay thế trách nhiệm chuyên môn của từng service owner. Vai trò này bảo đảm các mảnh bằng chứng được kết nối thành quyết định phát hành có thể giải thích.

### 4.5. Ma trận trách nhiệm tham khảo

| Hoạt động | Provider | Consumer | Platform/SRE | Release owner |
|---|---|---|---|---|
| Định nghĩa contract | A/R | C | I | I |
| Consumer expectation test | C | A/R | I | I |
| Provider contract verification | A/R | C | I | I |
| Service unit/component test | A/R | A/R cho service của mình | I | I |
| Môi trường tích hợp dùng chung | C | C | A/R | I |
| End-to-end hành trình liên nhóm | R theo service | R theo service | C | A |
| Tổng hợp bằng chứng release | R cung cấp | R cung cấp | C | A |
| Rollout/rollback service | A/R cho service của mình | C nếu bị ảnh hưởng | R theo nền tảng | A điều phối |

Trong bảng, A là người chịu trách nhiệm cuối cùng cho hoạt động, R là người thực hiện, C là người được tham vấn và I là người được thông báo. Tổ chức cần điều chỉnh vai trò theo mô hình quản trị thực tế; mỗi hoạt động nên có một người hoặc vai trò chịu trách nhiệm cuối cùng rõ ràng.

## 5. Phân bổ bằng chứng cho API đồng bộ

API đồng bộ như REST hoặc gRPC có provider trả response trực tiếp cho consumer. Rủi ro không chỉ nằm ở schema mà còn ở semantics, lỗi, timeout và hành vi phiên bản.

### 5.1. Những gì cần xác minh

- Method, route, request/response schema.
- Trường bắt buộc, nullable, default và enum.
- HTTP status hoặc gRPC status.
- Authentication, authorization và tenant scope.
- Error model, retryability và idempotency.
- Timeout, pagination, ordering và rate limit.
- Ngữ nghĩa dữ liệu: đơn vị, timezone, tiền tệ và trạng thái.
- Hành vi khi provider trả trường bổ sung hoặc giá trị chưa biết.

### 5.2. Bằng chứng từ provider

Provider team có thể cung cấp:

- Unit/component test cho logic xử lý request.
- Schema validation và provider contract verification.
- Integration test với database hoặc dependency quan trọng.
- Test authorization và error response.
- Test tương thích với contract đã công bố.
- Release note về thay đổi và deprecation.

### 5.3. Bằng chứng từ consumer

Consumer team có thể cung cấp:

- Consumer-driven contract hoặc test request/response expectation.
- Test mapping và xử lý response/error.
- Test timeout, retry và fallback ở phía consumer.
- Test khi provider trả enum hoặc trường mới theo quy tắc tương thích.
- Test hành trình của consumer với phiên bản provider được hỗ trợ.

### 5.4. Tương thích ngược và nhiều phiên bản

Trong rolling deployment, provider version mới và consumer version cũ có thể cùng tồn tại. Cần xác minh:

- Provider mới vẫn phục vụ consumer cũ trong thời gian chuyển tiếp.
- Consumer mới có thể làm việc với provider cũ nếu rollout theo thứ tự đó.
- Trường mới có default hoặc được triển khai theo cách không phá consumer.
- Trường/enum bị loại bỏ chỉ sau khi consumer cũ không còn sử dụng.
- API version và deprecation window được quản lý rõ.

Một contract test chạy với cặp version duy nhất chưa đủ nếu production có nhiều cặp version hợp lệ. Hãy xác định ma trận tương thích được hỗ trợ và chọn các cặp có rủi ro cao để kiểm tra.

## 6. Phân bổ bằng chứng cho event và message bất đồng bộ

Trong hệ thống event-driven, producer và consumer không nhất thiết chạy cùng thời điểm hoặc cùng phiên bản. Message có thể bị trễ, lặp, đảo thứ tự hoặc được replay sau nhiều ngày.

### 6.1. Những gì cần xác minh

- Event name, schema version và compatibility rules.
- Event key, partition key và ordering guarantee.
- Event ID, correlation ID và causation ID.
- Delivery semantics: at-most-once, at-least-once hoặc cơ chế cụ thể của nền tảng.
- Idempotency và xử lý duplicate.
- Retry, backoff, dead-letter và replay.
- Consumer offset, acknowledgement và trạng thái xử lý.
- Dữ liệu nhạy cảm và quyền truy cập vào topic.

### 6.2. Bằng chứng từ producer

- Unit/component test cho logic phát event.
- Schema validation trước khi publish.
- Integration test cho outbox hoặc transaction boundary.
- Test bảo đảm event chỉ phát khi thay đổi nghiệp vụ được commit theo thiết kế.
- Test event version và dữ liệu mặc định.

### 6.3. Bằng chứng từ consumer

- Contract/schema test cho các version event được hỗ trợ.
- Test duplicate, retry, event trễ và sai thứ tự.
- Test replay và xử lý message cũ.
- Test idempotency và dead-letter handling.
- Test trạng thái cuối và side effect nghiệp vụ.

### 6.4. Bằng chứng tích hợp giữa producer và consumer

Với event quan trọng, cần có bằng chứng cho thấy producer phát event đúng và consumer xử lý được trong một môi trường tích hợp. Tuy nhiên, không nhất thiết mọi event đều cần E2E toàn hệ thống. Có thể dùng schema registry validation, consumer contract, broker integration và một số hành trình đại diện.

### 6.5. Quản lý backlog và phiên bản event

Consumer có thể phải xử lý event được tạo bởi phiên bản producer cũ sau khi producer đã nâng cấp. Do đó, kiểm thử cần dùng dữ liệu event lưu trữ hoặc fixture từ các schema version trước. Không chỉ test event mới nhất.

## 7. Bằng chứng cho dữ liệu và migration xuyên service

Microservices thường sở hữu database riêng, nhưng dữ liệu có thể được sao chép, đồng bộ hoặc tổng hợp qua event, ETL và read model. Thay đổi dữ liệu ở một service có thể làm ảnh hưởng consumer downstream.

### 7.1. Data ownership

Xác định service nào là nguồn có thẩm quyền (system of record) cho từng thực thể hoặc trường dữ liệu. Consumer nên sử dụng API/event được công bố thay vì đọc trực tiếp database nội bộ của service khác, trừ khi kiến trúc có quy định rõ.

### 7.2. Bằng chứng cần có

- Migration test với dữ liệu cũ và dữ liệu biên.
- Schema compatibility với phiên bản ứng dụng cũ/mới.
- Backfill completeness và correctness.
- Referential integrity và business invariants.
- Đối soát dữ liệu giữa nguồn và read model.
- Event replay hoặc rebuild projection nếu áp dụng.
- Backup/restore và khả năng rollback hoặc forward-fix.
- Kiểm tra quyền truy cập và phân tách tenant.

### 7.3. Thay đổi theo nhiều giai đoạn

Với schema change cần tương thích, có thể dùng expand-and-contract:

1. Expand cấu trúc mới theo cách phiên bản cũ vẫn hoạt động.
2. Deploy code có thể đọc/ghi cấu trúc mới và xử lý dữ liệu chuyển tiếp.
3. Backfill dữ liệu theo lô, đối soát và quan sát.
4. Chuyển consumer hoặc read model sang cấu trúc mới.
5. Contract và xóa cấu trúc cũ sau khi xác nhận không còn consumer sử dụng.

Mỗi bước cần bằng chứng riêng. Một migration script chạy thành công trên database rỗng không chứng minh dữ liệu production hiện hữu được chuyển đổi đúng hoặc ứng dụng cũ vẫn hoạt động.

## 8. Quản lý ma trận phiên bản và khả năng tương thích

Khi nhiều nhóm phát hành độc lập, hệ thống có thể tồn tại nhiều phiên bản service cùng lúc. Bộ bằng chứng cần phản ánh các tổ hợp version được phép.

### 8.1. Xác định version matrix

Ma trận có thể bao gồm:

- Provider version.
- Consumer version.
- API/event schema version.
- Database schema version.
- Client/mobile version.
- Feature flag và cấu hình rollout.
- Phiên bản dependency hoặc runtime quan trọng.

Không phải mọi tổ hợp đều cần hỗ trợ. Hãy định nghĩa các tổ hợp hợp lệ, tổ hợp chuyển tiếp và tổ hợp không được hỗ trợ. Điều này tránh test quá nhiều tổ hợp vô nghĩa hoặc bỏ sót tổ hợp thực sự tồn tại trong rollout.

### 8.2. Chọn tổ hợp cần kiểm tra

Ưu tiên:

- Phiên bản đang chạy phổ biến nhất.
- Phiên bản cũ vẫn còn trong thời hạn hỗ trợ.
- Provider mới với consumer cũ trong rolling deployment.
- Consumer mới với provider cũ nếu rollout có thể xảy ra theo thứ tự đó.
- Event backlog chứa schema cũ.
- Phiên bản có thay đổi breaking hoặc deprecation.
- Tổ hợp có rủi ro bảo mật hoặc dữ liệu cao.

Có thể dùng pairwise/combinatorial testing để giảm số tổ hợp, nhưng các đường tương thích có rủi ro cao cần được kiểm tra riêng.

### 8.3. Gắn bằng chứng với version cụ thể

Một kết quả contract test chỉ có ý nghĩa khi biết contract version, provider artifact và consumer expectation đã dùng. Một báo cáo E2E không có commit hoặc deployment identifier khó chứng minh release cụ thể nào đã được kiểm tra.

## 9. Bằng chứng cho hành trình nghiệp vụ xuyên service

Hành trình nghiệp vụ thường đi qua nhiều nhóm sở hữu. Cần chọn một số hành trình trọng yếu và chia trách nhiệm xác minh theo từng bước.

### 9.1. Phân rã hành trình

Ví dụ hành trình đặt hàng:

1. Client gửi yêu cầu tạo đơn.
2. Order service xác minh và tạo đơn ở trạng thái chờ.
3. Pricing service tính tổng tiền và khuyến mại.
4. Payment service tạo giao dịch và nhận kết quả.
5. Inventory service giữ hoặc trừ tồn kho.
6. Order service cập nhật trạng thái cuối.
7. Notification service gửi xác nhận.

Với mỗi bước, xác định input, output, state transition, event và owner. Bằng chứng cấp service xác minh từng bước; contract test xác minh ranh giới; integration test xác minh tương tác quan trọng; E2E xác minh kết quả mà người dùng cần.

### 9.2. Không đặt toàn bộ logic vào E2E

E2E nên kiểm tra các hành trình có giá trị cao, không nên lặp lại mọi biến thể logic đã được kiểm tra tốt ở cấp thấp. Nếu một phép tính phí có hàng chục trường hợp biên, unit/component test có thể kiểm tra chi tiết; E2E chỉ cần một số trường hợp đại diện để xác nhận các service truyền và sử dụng kết quả đúng.

### 9.3. Xác minh trạng thái cuối và side effect

Không chỉ kiểm tra response đầu tiên. Với hành trình bất đồng bộ, cần xác minh trạng thái cuối, dữ liệu đã ghi, event đã phát và side effect quan trọng. Ví dụ, response “đã tiếp nhận” không chứng minh đơn hàng đã thanh toán hoặc notification đã được gửi.

### 9.4. Bằng chứng cho failure path

Chọn các lỗi có thể lan truyền:

- Payment provider timeout hoặc từ chối.
- Inventory service không sẵn sàng.
- Event bị gửi lặp hoặc đến trễ.
- Một service deploy trong lúc request đang xử lý.
- Consumer bị restart khi đang nhận message.
- Một bước commit thành công nhưng acknowledgement thất bại.

Test failure path cần xác minh tính nhất quán, retry, compensation, trạng thái cuối và khả năng phục hồi, không chỉ xác nhận hệ thống trả mã lỗi.

## 10. Môi trường tích hợp và dữ liệu dùng chung

Môi trường tích hợp là nơi nhiều service và nhóm cùng kiểm tra tương tác. Nó thường có giá trị cao nhưng cũng dễ trở thành điểm nghẽn nếu không quản lý version, dữ liệu và quyền sử dụng.

### 10.1. Môi trường theo mục đích

Có thể phân tách:

- Môi trường service-local cho unit/component.
- Môi trường contract provider/consumer.
- Môi trường integration theo nhóm service.
- Môi trường staging hoặc pre-production cho hành trình đại diện.
- Môi trường performance/resilience riêng để tránh nhiễu.
- Sandbox hoặc môi trường đối tác theo giới hạn được phép.

Không cần một môi trường duy nhất cho mọi loại test. Mỗi môi trường cần mô tả service version, dependency, dữ liệu, quota và mức độ tương đồng với production.

### 10.2. Quản lý topology và version

Ghi lại service nào đang chạy phiên bản nào, cấu hình và feature flag nào đang bật. Khi test thất bại, nhóm cần biết đó là lỗi code, sai tổ hợp version hay môi trường đang ở trạng thái chuyển tiếp.

### 10.3. Dữ liệu kiểm thử

- Dùng dữ liệu riêng theo run, tenant hoặc namespace khi phù hợp.
- Tránh nhiều nhóm cập nhật cùng một thực thể.
- Quản lý seed và fixture theo version.
- Giữ event lịch sử cho consumer compatibility test.
- Có cleanup và ownership rõ.
- Không dùng dữ liệu production nhạy cảm ngoài chính sách.

### 10.4. Quản lý dependency dùng chung

Database, broker, identity provider và sandbox có quota hữu hạn. Cần phân bổ lịch, giới hạn concurrency và cơ chế cô lập. Nếu nhiều nhóm cùng triển khai migration hoặc thay đổi feature flag toàn cục, cần điều phối để tránh kết quả test không xác định.

### 10.5. Môi trường không đồng nhất

Nếu staging không giống production về phiên bản, topology, network policy hoặc dữ liệu, hãy ghi rõ giới hạn. Không dùng kết quả staging để khẳng định những thuộc tính chưa được mô phỏng, chẳng hạn failover đa vùng hoặc quota production.

## 11. Tổng hợp bằng chứng cho release độc lập

Nhiều nhóm có thể phát hành service ở thời điểm khác nhau. Mỗi release cần bằng chứng riêng và có thể cần xác nhận tương thích với các service đang chạy.

### 11.1. Release evidence package của một service

Một gói bằng chứng có thể bao gồm:

- Service name, owner, version, commit và artifact digest.
- Phạm vi thay đổi và impact analysis.
- Unit/component test result.
- Provider/consumer contract result.
- Integration test result.
- Security, performance hoặc migration evidence khi rủi ro yêu cầu.
- Dependency và schema version.
- Các test bị skip/blocked và lý do.
- Rủi ro còn lại, ngoại lệ và người phê duyệt.
- Rollout, monitoring và rollback plan.

### 11.2. Release manifest ở cấp sản phẩm

Khi phát hành nhiều service cùng nhau, release manifest có thể ghi:

| Service | Version/artifact | Contract/schema | Bằng chứng bắt buộc | Trạng thái |
|---|---|---|---|---|
| Order | Artifact digest và commit | Order API/event vN | Service, contract, integration, E2E | Pending/Pass/Fail |
| Payment | Artifact digest và commit | Payment API/event vN | Service, provider sandbox, idempotency, security | Pending/Pass/Fail |
| Inventory | Artifact digest và commit | Inventory event vN | Consumer contract, queue integration, data integrity | Pending/Pass/Fail |
| Notification | Artifact digest và commit | Notification event vN | Consumer contract, delivery/failure handling | Pending/Pass/Fail |

Đây là cấu trúc minh họa. Manifest thật cần tham chiếu artifact và báo cáo cụ thể thay vì chỉ ghi trạng thái thủ công.

### 11.3. Không gộp trạng thái khác nghĩa

Phải phân biệt:

- Pass: test bắt buộc đã chạy và đạt.
- Fail: test chạy và không đạt.
- Blocked: không thể chạy do điều kiện hoặc dependency.
- Skipped: được bỏ qua theo chính sách, có lý do.
- Inconclusive: kết quả không đủ để kết luận.
- Not applicable: không áp dụng theo phạm vi đã xác định.

Blocked hoặc Skipped không tự động tương đương Pass. Nếu release vẫn tiếp tục, cần ghi rõ rủi ro và người có thẩm quyền chấp nhận.

### 11.4. Hiệu lực của bằng chứng

Bằng chứng có thể mất hiệu lực khi code, contract, schema, cấu hình hoặc môi trường thay đổi. Cần xác định điều kiện làm hết hiệu lực và chạy lại các kiểm tra liên quan. Không tái sử dụng báo cáo cũ nếu artifact đã thay đổi mà không có cơ sở chứng minh tính tương đương.

## 12. Điều phối cổng chất lượng giữa nhiều nhóm

Cổng chất lượng cần tổng hợp các bằng chứng bắt buộc theo phạm vi release mà không tạo một điểm phê duyệt mơ hồ.

### 12.1. Cổng cấp service

Service owner xác nhận:

- Build/artifact được xác định rõ.
- Test bắt buộc của service đã chạy.
- Contract không phá vỡ consumer được hỗ trợ.
- Migration và cấu hình có bằng chứng phù hợp.
- Lỗi nghiêm trọng và rủi ro còn lại đã được xử lý hoặc chấp nhận.

### 12.2. Cổng cấp hành trình hoặc sản phẩm

Release owner xác nhận:

- Các service liên quan đã cung cấp evidence package.
- Các contract và version combination quan trọng tương thích.
- Hành trình nghiệp vụ trọng yếu có bằng chứng xuyên service.
- Môi trường và dữ liệu đủ đại diện cho mục tiêu release.
- Monitoring, rollout và rollback sẵn sàng.
- Các ngoại lệ được phê duyệt đúng thẩm quyền.

### 12.3. Điều kiện bắt buộc và điều kiện theo rủi ro

Không phải mọi test đều phải chạy trong mọi release. Có thể chia:

- Bắt buộc cho mọi commit hoặc service release.
- Bắt buộc khi thay đổi một contract, schema hoặc dependency cụ thể.
- Bắt buộc trước khi mở traffic rộng.
- Chạy định kỳ hoặc theo lịch.
- Chỉ áp dụng khi impact analysis xác định rủi ro.

Quy tắc cần được tự động hóa và version hóa khi có thể. Việc chọn test theo thay đổi phải có đường fallback khi dependency map hoặc metadata không đáng tin cậy.

### 12.4. Quản lý ngoại lệ

Nếu một bằng chứng bắt buộc bị thiếu hoặc không đạt, ngoại lệ cần nêu:

- Phần bằng chứng chưa có hoặc thất bại.
- Lý do và tác động có thể xảy ra.
- Biện pháp giảm thiểu tạm thời.
- Phạm vi người dùng/service bị ảnh hưởng.
- Người có thẩm quyền chấp nhận.
- Thời hạn và điều kiện xem xét lại.

Không dùng “đã trao đổi trong chat” làm hồ sơ chấp nhận rủi ro duy nhất. Quyết định cần được lưu ở nơi có thể truy nguyên.

## 13. Truy nguyên bằng chứng từ yêu cầu đến production

Một chuỗi truy nguyên hữu ích kết nối:

**Yêu cầu/rủi ro → service/contract → test hoặc phép đo → kết quả → artifact/version → release → telemetry sau triển khai.**

### 13.1. Định danh nhất quán

Sử dụng định danh ổn định cho:

- Requirement, risk hoặc acceptance criterion.
- Service, API, event và schema.
- Test case, test suite và test run.
- Commit, build, artifact và deployment.
- Release, incident và action item.

Định danh giúp liên kết báo cáo từ nhiều công cụ mà không cần sao chép nội dung.

### 13.2. Metadata cần gắn vào kết quả

- Git commit hoặc source revision.
- Artifact digest hoặc immutable build ID.
- Service version và contract/schema version.
- Environment và deployment identifier.
- Feature flag/configuration snapshot phù hợp.
- Test data version hoặc seed.
- Thời điểm chạy và tool version.
- Link đến log, trace, report và owner.

Không đưa secret hoặc dữ liệu cá nhân vào metadata. Nếu cần tham chiếu cấu hình nhạy cảm, dùng version hoặc identifier không tiết lộ giá trị.

### 13.3. Giữ lại bằng chứng có thời hạn phù hợp

Thời gian lưu phụ thuộc nhu cầu điều tra, audit, hợp đồng và chi phí. Bằng chứng phát hành quan trọng cần đủ lâu để điều tra lỗi sau triển khai hoặc tái dựng trạng thái release. Dữ liệu log chi tiết có thể có thời hạn khác với manifest và kết quả kiểm thử tổng hợp.

### 13.4. Bằng chứng không còn hợp lệ

Đánh dấu hoặc thay thế bằng chứng khi:

- Artifact được rebuild hoặc thay đổi digest.
- Contract/schema thay đổi.
- Cấu hình hoặc feature flag khác với lần test.
- Dependency hoặc môi trường đã thay phiên bản.
- Test bị sửa làm thay đổi assertion.
- Dữ liệu test không còn tái tạo được.

## 14. Xử lý khoảng trống và mâu thuẫn bằng chứng

Trong hệ thống nhiều nhóm, các báo cáo có thể không đồng nhất. Cần xử lý rõ thay vì lấy trạng thái thuận lợi nhất.

### 14.1. Consumer contract Pass nhưng E2E Fail

Có thể contract đúng nhưng cấu hình runtime, authentication, network, dữ liệu hoặc thứ tự sự kiện sai. Dùng trace và log để xác định ranh giới; không kết luận contract test vô ích hoặc E2E chắc chắn sai.

### 14.2. Provider test Pass nhưng consumer bị lỗi

Có thể provider chỉ kiểm tra contract mới, trong khi consumer cũ vẫn đang chạy. Xác minh version matrix và compatibility window. Cần kiểm tra cặp provider/consumer thực tế đang triển khai.

### 14.3. Integration test Blocked

Ghi rõ dependency hoặc môi trường nào không sẵn sàng. Nếu có thể, dùng contract hoặc component evidence để thu hẹp rủi ro, nhưng không xem chúng thay thế hoàn toàn integration evidence cần thiết. Quyết định tiếp tục cần dựa trên severity và chính sách release.

### 14.4. Test flaky giữa các lần chạy

Giữ lại kết quả lần đầu, môi trường, dữ liệu và trace. Xác định nguyên nhân do race condition, dữ liệu dùng chung, dependency, timing hoặc assertion không ổn định. Không xóa lịch sử bằng cách chỉ ghi kết quả retry cuối cùng.

### 14.5. Telemetry production mâu thuẫn với test

Test có thể chạy trong môi trường nhỏ hoặc dữ liệu khác; telemetry có thể bị sampling hoặc định nghĩa metric không chính xác. So sánh điều kiện, phạm vi và cách đo trước khi quyết định nguồn nào hỗ trợ kết luận nào.

### 14.6. Không có đủ bằng chứng

Phân loại phần thiếu:

- Chưa có test hoặc phép đo.
- Test có nhưng không chạy.
- Test chạy nhưng kết quả không đủ tin cậy.
- Không có môi trường hoặc dependency phù hợp.
- Không truy nguyên được version/config.
- Owner hoặc trách nhiệm chưa rõ.

Sau đó tạo hành động có owner và deadline. Không diễn giải “không có lỗi được báo” thành “đã chứng minh không có lỗi”.

## 15. Bảo mật và tính toàn vẹn của bằng chứng

Bằng chứng kiểm thử có thể chứa dữ liệu người dùng, thông tin kiến trúc, lỗ hổng hoặc secret. Việc chia sẻ liên nhóm cần bảo vệ dữ liệu và tránh thay đổi kết quả.

- Chỉ thu thập dữ liệu cần thiết cho mục tiêu kiểm thử.
- Dùng dữ liệu tổng hợp hoặc đã xử lý khi có thể.
- Redact token, password, key, cookie và payload nhạy cảm.
- Phân quyền xem báo cáo security, log và trace chi tiết.
- Lưu bằng chứng ở nơi có audit và chính sách retention.
- Dùng artifact immutable hoặc checksum khi cần bảo đảm tính toàn vẹn.
- Phân biệt dữ liệu gốc với bản sao đã xử lý.
- Không dùng chung credential giữa các nhóm để tạo thuận tiện.
- Ghi lại nguồn và phép biến đổi của dữ liệu bằng chứng.

Với kiểm thử bảo mật, một báo cáo có thể tiết lộ lỗ hổng chưa được khắc phục. Chỉ chia sẻ chi tiết cho người cần biết và dùng kênh xử lý phù hợp.

## 16. Ví dụ xuyên suốt: phát hành độc lập các service trong hành trình đặt hàng

Giả sử một tổ chức có bốn nhóm sở hữu Order, Payment, Inventory và Notification. Mỗi nhóm phát hành service độc lập, nhưng sản phẩm cần duy trì hành trình đặt hàng xuyên suốt.

### 16.1. Phạm vi thay đổi

Payment team thay đổi API để thêm trạng thái `PENDING` và phát event `PaymentCompleted` sau khi provider xác nhận. Order team có thể chưa phát hành phiên bản mới ngay; Inventory team tiêu thụ event `OrderConfirmed`; Notification team tiêu thụ event `PaymentCompleted`.

### 16.2. Rủi ro cần kiểm tra

- Order service cũ có hiểu trạng thái pending hay không.
- Event mới có tương thích với consumer hiện tại không.
- Event có thể bị phát lặp hoặc đến trễ không.
- Inventory có giữ hàng trước khi thanh toán hoàn tất không.
- Notification có gửi xác nhận quá sớm không.
- Release theo thứ tự khác nhau có tạo trạng thái không hợp lệ không.

### 16.3. Phân bổ bằng chứng

| Nhóm | Bằng chứng cấp nhóm | Bằng chứng tại ranh giới |
|---|---|---|
| Payment | Unit/component cho trạng thái, retry và idempotency | Provider contract, event schema, sandbox integration. |
| Order | Unit/component cho state transition và xử lý pending | Consumer contract cho Payment API/event; integration với order store. |
| Inventory | Unit/component cho reserve/release | Consumer contract cho event OrderConfirmed; duplicate/replay test. |
| Notification | Unit/component cho nội dung và điều kiện gửi | Consumer contract cho PaymentCompleted; delivery/failure handling. |
| Platform/SRE | Health, broker, trace, quota và môi trường | Integration topology, observability và rollback capability. |
| Release owner | Tổng hợp version matrix và trạng thái evidence | E2E hành trình đặt hàng, canary và quyết định phát hành. |

### 16.4. Thứ tự rollout có kiểm soát

1. Công bố event schema mới theo quy tắc tương thích.
2. Triển khai consumer có khả năng xử lý cả event cũ và mới.
3. Xác minh contract và consumer integration.
4. Triển khai Payment provider/adapter mới với feature flag hoặc canary.
5. Quan sát event delivery, trạng thái order, reserve inventory và notification.
6. Chạy E2E hành trình đại diện trên tổ hợp version thực tế.
7. Mở rộng rollout khi quality gate đạt và không có tín hiệu bất thường.

Thứ tự cụ thể phụ thuộc semantics của contract và khả năng tương thích. Nếu consumer không thể xử lý event mới trước provider, cần điều chỉnh kế hoạch hoặc cung cấp versioning/translation phù hợp.

### 16.5. Bộ bằng chứng phát hành

Release package cần gắn commit và artifact digest của từng service, contract/schema version, kết quả test bắt buộc, tổ hợp version đã xác minh, migration status, rủi ro còn lại và kế hoạch theo dõi. Khi một service phát hành riêng, package của service đó cần xác nhận compatibility với các phiên bản đang được hỗ trợ, không chỉ với phiên bản mới nhất trên staging.

## 17. Chỉ số đánh giá hiệu quả phân bổ bằng chứng

Đo lường giúp xác định bằng chứng đang được tạo đúng nơi và đúng thời điểm hay không.

### 17.1. Độ phủ theo ranh giới

- Tỷ lệ API/event quan trọng có contract test.
- Tỷ lệ service có test cho hành vi và trạng thái trọng yếu.
- Tỷ lệ hành trình nghiệp vụ quan trọng có E2E hoặc bằng chứng xuyên service tương ứng.
- Tỷ lệ migration có kiểm tra dữ liệu cũ và đối soát.
- Tỷ lệ rủi ro có bằng chứng được liên kết.

### 17.2. Chất lượng và tính kịp thời

- Thời gian từ commit đến khi có bằng chứng service/contract.
- Thời gian tổng hợp release evidence package.
- Tỷ lệ test flaky, blocked hoặc không có kết quả.
- Tỷ lệ bằng chứng không truy nguyên được artifact/version.
- Số lỗi tương thích phát hiện sau phát hành.
- Thời gian định vị service hoặc contract gây lỗi.

### 17.3. Hiệu quả phối hợp

- Số lần release bị chờ vì thiếu owner hoặc bằng chứng.
- Tỷ lệ consumer được thông báo về breaking/deprecation change.
- Tỷ lệ ngoại lệ có owner, thời hạn và phê duyệt.
- Tỷ lệ hành động sau incident được xác minh.
- Số lần môi trường tích hợp bị xung đột hoặc không đồng nhất.

### 17.4. Diễn giải cẩn trọng

Tỷ lệ contract test cao không tự chứng minh runtime ổn định; số E2E thấp không nhất thiết là thiếu nếu các rủi ro đã được kiểm tra ở cấp phù hợp. Mục tiêu không phải tối đa hóa số test hay số báo cáo, mà là có đủ bằng chứng chất lượng, đúng phạm vi và chi phí hợp lý.

## 18. Những sai lầm thường gặp

- **Để một nhóm chịu trách nhiệm cho toàn bộ chất lượng xuyên service**: làm mất ownership tại ranh giới. Hãy phân chia trách nhiệm provider, consumer và release owner.
- **Chỉ kiểm thử bên trong từng service**: bỏ sót lỗi contract và phối hợp. Hãy bổ sung contract, integration và hành trình trọng yếu.
- **Dùng E2E làm bằng chứng duy nhất**: chậm và khó định vị lỗi. Hãy phân bổ test ở cấp phù hợp.
- **Cho rằng contract Pass nghĩa là tích hợp hoàn chỉnh**: bỏ sót runtime, cấu hình, network và dữ liệu. Hãy bổ sung integration evidence khi cần.
- **Chỉ kiểm tra version mới nhất**: bỏ sót consumer cũ hoặc event backlog. Hãy xác định version matrix được hỗ trợ.
- **Không gắn kết quả với artifact**: không biết chính xác code nào đã được kiểm tra. Hãy dùng commit, digest và deployment ID.
- **Gộp Blocked/Skipped thành Pass**: tạo cảm giác an toàn giả. Hãy giữ trạng thái riêng và quản lý ngoại lệ.
- **Giả định staging giống production**: bỏ qua khác biệt topology, quota và dữ liệu. Hãy ghi giới hạn và bổ sung bằng chứng vận hành phù hợp.
- **Không có owner cho contract**: thay đổi không được thông báo hoặc xác minh. Hãy xác định provider và consumer owner.
- **Phát hành đồng thời mà không điều phối schema**: tạo version incompatibility. Hãy dùng compatibility policy và rollout theo giai đoạn.
- **Chia sẻ log/trace không kiểm soát**: làm lộ dữ liệu hoặc secret. Hãy redaction và phân quyền.
- **Tái sử dụng bằng chứng cũ sau khi artifact đổi**: kết luận không còn đúng với release. Hãy xác định điều kiện hết hiệu lực.
- **Chỉ nhìn số lượng test**: không biết rủi ro nào được bảo vệ. Hãy liên kết test với yêu cầu, contract và impact analysis.
- **Không dùng telemetry sau phát hành**: mất cơ hội xác minh giả định trong điều kiện thật. Hãy đóng vòng với monitoring và phản hồi người dùng.

## 19. Hồ sơ phân bổ và tổng hợp bằng chứng

Một hồ sơ chung giúp các nhóm trao đổi theo cùng cấu trúc.

| Trường | Nội dung cần ghi |
|---|---|
| Evidence ID | Định danh bằng chứng. |
| Requirement/Risk ID | Yêu cầu hoặc rủi ro được xác minh. |
| Service/Interface | Service, API, event hoặc hành trình liên quan. |
| Owner | Nhóm tạo và chịu trách nhiệm về bằng chứng. |
| Provider/Consumer | Các bên giao tiếp qua contract nếu áp dụng. |
| Version | Commit, artifact digest, schema và dependency version. |
| Test level | Unit, component, contract, integration, E2E hoặc operational. |
| Environment | Topology, cấu hình, dữ liệu và dependency. |
| Result | Pass, Fail, Blocked, Skipped, Inconclusive hoặc N/A. |
| Artifact | Report, log, trace, metric snapshot hoặc reconciliation. |
| Limitation | Mock/fake, version chưa kiểm tra và giả định còn lại. |
| Validity | Điều kiện hết hiệu lực và thời hạn sử dụng. |
| Approval/Exception | Reviewer, người chấp nhận rủi ro và thời hạn. |

## 20. Quy trình phân bổ bằng chứng cho nhiều nhóm phát hành

Nhóm có thể áp dụng trình tự sau:

1. **Lập bản đồ service và hành trình**: xác định owner, API, event, data flow và dependency.
2. **Xác định yêu cầu và rủi ro**: nêu hành vi, thuộc tính chất lượng và hậu quả cần bảo vệ.
3. **Chọn lớp bằng chứng**: phân bổ service, contract, integration, E2E, migration và operational evidence.
4. **Phân công provider/consumer**: xác định ai định nghĩa, kiểm tra và duy trì từng contract.
5. **Lập version matrix**: xác định tổ hợp provider, consumer, schema và database cần hỗ trợ.
6. **Chuẩn bị môi trường và dữ liệu**: version hóa topology, fixture, quota và quyền truy cập.
7. **Tạo evidence package theo service**: gắn kết quả với commit, artifact, cấu hình và giới hạn.
8. **Tổng hợp ở cấp release**: kiểm tra hành trình, compatibility, migration, rollout và ngoại lệ.
9. **Ra quyết định có truy vết**: giữ rõ Pass/Fail/Blocked/Skipped và người chấp nhận rủi ro.
10. **Theo dõi sau phát hành**: dùng telemetry và phản hồi để xác minh giả định, bổ sung test và cập nhật ma trận.

## 21. Tự kiểm tra

Trước khi chấp nhận bộ bằng chứng cho một release microservices, hãy tự hỏi:

- Các service, API, event, data flow và owner liên quan đã được xác định chưa?
- Mỗi service có bằng chứng cho logic và trạng thái mà nó sở hữu chưa?
- Provider và consumer đã xác minh contract theo đúng version chưa?
- Có kiểm tra runtime integration cho các ranh giới rủi ro cao không?
- Hành trình nghiệp vụ trọng yếu có bằng chứng xuyên service và trạng thái cuối không?
- Version matrix có phản ánh rolling deployment và consumer cũ không?
- Migration, event backlog và dữ liệu lịch sử đã được xem xét chưa?
- Mỗi kết quả có gắn commit, artifact digest, schema, config và môi trường không?
- Blocked, Skipped và Inconclusive có được giữ riêng và giải thích không?
- Bằng chứng có owner, thời hạn hiệu lực và điều kiện hết hiệu lực không?
- Các ngoại lệ có người chấp nhận, biện pháp giảm thiểu và ngày xem xét lại không?
- Release owner có thể truy nguyên từ yêu cầu/rủi ro đến test, artifact và deployment không?
- Có kế hoạch monitoring, canary, rollback và phản hồi sau phát hành không?
- Dữ liệu và báo cáo có được bảo vệ theo chính sách không?

## Kết luận

Trong microservices và tổ chức có nhiều nhóm phát hành, bằng chứng kiểm thử cần được phân bổ theo service ownership, hợp đồng giao tiếp, dependency và hành trình nghiệp vụ. Mỗi nhóm xác minh phần mình sở hữu; provider và consumer cùng bảo vệ contract; platform hỗ trợ môi trường và observability; release owner tổng hợp bằng chứng theo đúng tổ hợp phiên bản và phạm vi phát hành. Kết quả phải gắn với commit, artifact, schema, cấu hình và điều kiện thực thi, đồng thời giữ rõ phần chưa được kiểm tra hoặc chưa đủ kết luận. Khi kết hợp test cấp service, contract, integration, E2E có chọn lọc và telemetry sau triển khai, tổ chức có thể phát hành độc lập với tốc độ phù hợp mà vẫn duy trì khả năng truy nguyên và kiểm soát rủi ro xuyên hệ thống.
