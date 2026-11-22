# Quay lui mã nguồn, cấu hình và xử lý thay đổi dữ liệu khó đảo ngược

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Tích hợp và phát hành.  
> **Mục tiêu:** thiết kế cơ chế quay lui bản triển khai và cấu hình an toàn, nhận diện những thay đổi dữ liệu không thể quay ngược bằng cách chạy code cũ, đồng thời xác định khi nào cần khôi phục dữ liệu, sửa tiến (roll forward) hoặc thực hiện hành động bù trừ.

## 1. Bài toán: vì sao một lệnh “rollback” không đủ?

Hệ thống thương mại điện tử có **API Gateway**, **Order Service**, **Payment Service**, **Inventory Service**, **Notification Service** và database riêng cho từng service. Nhóm phát triển triển khai phiên bản Order mới:

- Order Service từ **v12** lên **v13**.
- Cờ tính năng **checkout.pricing-v2** từ OFF sang ON cho 20% người dùng.
- Database thêm cột, backfill lại giá trị và sau đó xóa một cột cũ.
- Order phát sự kiện có schema mới; Payment và Notification bắt đầu tiêu thụ.
- Một số khách hàng đã hoàn tất thanh toán qua đường code mới.

Sau khi phát hành, phát hiện lỗi tính tổng tiền. Nhóm vận hành quyết định đưa Order từ v13 trở về v12. Nhưng v12 có thể không hiểu cột hoặc event mới; các đơn đã tạo theo thuật toán v2 cũng không thể “chưa từng xảy ra”. Nếu chạy v12 lên schema không tương thích, dịch vụ có thể lỗi ngay khi khởi động hoặc đọc/ghi dữ liệu sai.

**Vấn đề cốt lõi:** rollback một bản triển khai chỉ đổi **code đang chạy**. Nó không tự hoàn tác cấu hình trong control plane, schema/data đã thay đổi, message đã phát, tiền đã thu, email đã gửi, cache đã sinh hoặc side effect ở hệ thống khác.

Trong microservices, khả năng quay lui là thuộc tính của **toàn bộ chuỗi thay đổi và trạng thái hệ thống**, không chỉ của artifact ứng dụng.

## 2. Những loại trạng thái cần phân biệt

| Thành phần | Ví dụ thay đổi | Có thể quay lui thế nào? | Rủi ro |
| --- | --- | --- | --- |
| **Mã ứng dụng** | Order v12 → v13 | Chuyển traffic về artifact v12 đã biết tốt | v12 có thể không tương thích dữ liệu/contract hiện tại |
| **Cấu hình runtime** | Timeout, endpoint, pool size | Trả về revision cấu hình đã xác minh | Snapshot lan chậm, không đồng nhất giữa pod |
| **Feature flag** | Bật pricing-v2 cho 20% | Chuyển cohort về legacy nếu đường cũ còn an toàn | Request đang xử lý và dữ liệu đã ghi không tự hoàn tác |
| **Secret/credential** | Xoay API key hoặc certificate | Khôi phục trạng thái tin cậy theo quy trình rotation | Key cũ có thể đã bị thu hồi hoặc lộ; không tùy tiện tái sử dụng |
| **Database schema** | Thêm/đổi/xóa cột | Migration bổ sung hoặc reverse migration có kiểm soát | Drop/rename có thể phá version cũ |
| **Database data** | Backfill, đổi meaning của field | Sửa tiến, phục hồi bản sao hoặc bù trừ theo nghiệp vụ | Cập nhật có thể làm mất thông tin không tái tạo được |
| **Message/event** | Phát OrderPaid phiên bản mới | Consumer tương thích hoặc phát event sửa/bù | Event đã được xử lý bởi nhiều hệ thống |
| **Tác vụ bên ngoài** | Charge thẻ, gửi email, gọi partner API | Compensation/đối soát nếu nghiệp vụ cho phép | Không thể “unsend” email hoặc xóa giao dịch đã settle chỉ bằng rollback |
| **Cache/search index** | Thay schema cache, index lại dữ liệu | Invalidate/rebuild theo version | Cache cũ/mới có thể làm đọc sai |
| **Hạ tầng** | Routing, ingress, service discovery | Phục hồi manifest/route revision | Traffic, session và connection không chuyển tức thì |

Khi lập kế hoạch phát hành, cần gắn nhãn **mức độ đảo ngược được** cho từng thay đổi. Nếu một thao tác có side effect không thể thu hồi, phải thiết kế cách phục hồi riêng trước khi bật cho người dùng.

## 3. Phân biệt rollback, roll forward, restore và compensation

### 3.1. Rollback

**Rollback** là đưa một thành phần trở lại phiên bản hoặc chính sách đã biết tốt. Ví dụ:

- Deployment dùng lại container image v12 thay vì v13.
- Config revision 103 trở về 102.
- Flag pricing-v2 chuyển OFF.
- Gateway route chuyển traffic về upstream version cũ.

Rollback phù hợp khi **trạng thái dùng chung vẫn tương thích** với phiên bản cũ và side effect chưa phá giả định của nó.

### 3.2. Roll forward

**Roll forward** là phát hành bản sửa mới, ví dụ v14, để khắc phục lỗi v13 trong khi vẫn giữ schema và dữ liệu đã được chuyển. Chọn hướng này khi:

- Dữ liệu mới không thể được đọc/ghi an toàn bằng bản cũ.
- Migration đã xóa hoặc chuyển đổi dữ liệu theo cách không thể đảo ngược.
- Các service khác đã phụ thuộc contract mới.
- Việc dùng code cũ làm tăng nguy cơ sai dữ liệu.
- Bản sửa giới hạn và có thể phát hành an toàn nhanh hơn việc đảo ngược nhiều lớp trạng thái.

Roll forward cũng có rủi ro triển khai mới; cần kiểm thử, quan sát và giới hạn blast radius như một release khác.

### 3.3. Restore và point-in-time recovery

**Restore** đưa dữ liệu về bản backup hoặc trạng thái tại một thời điểm được hỗ trợ. Với cơ sở dữ liệu, **point-in-time recovery (PITR)** có thể khôi phục đến mốc cụ thể nếu hệ thống lưu đủ snapshot và transaction log/WAL.

Restore dữ liệu production không đồng nghĩa rollback code: nó có thể làm mất tất cả giao dịch hợp lệ phát sinh sau mốc khôi phục và khiến các service khác vẫn giữ trạng thái mới. Vì vậy phục hồi cần tính đến **RPO**, **RTO**, đồng bộ giữa hệ thống và phương án replay/reconcile.

### 3.4. Compensation

**Compensation** là một hành động nghiệp vụ mới nhằm xử lý tác động của hành động trước đó, chứ không xóa lịch sử. Ví dụ:

- Đơn đã charge thành công nhưng không thể giao: thực hiện **refund** theo chính sách.
- Đã giữ hàng nhưng không thể thanh toán: **release reservation**.
- Đã phát thông báo sai: gửi thông báo điều chỉnh.
- Đã cập nhật ledger: tạo bút toán đảo/điều chỉnh có audit, không xóa bản ghi lịch sử.

Compensation phải có **idempotency**, quyền thực hiện, điều kiện trạng thái, khả năng đối soát và dấu vết audit. Không mặc định mọi hành động đều bù trừ được hoàn toàn; email đã đọc hoặc dữ liệu đã lộ là ví dụ không thể “thu hồi” bằng một thao tác kỹ thuật.

### 3.5. Bảng quyết định sơ bộ

| Tình huống | Hướng ưu tiên thường gặp | Điều kiện bắt buộc |
| --- | --- | --- |
| Code mới lỗi, schema/data chưa đổi | Rollback deployment | Artifact cũ còn tương thích |
| Config timeout mới làm tăng lỗi | Revert config revision | Có snapshot và propagation rõ |
| Flag tính năng phụ gây tăng tải | Tắt flag/kill switch | Nhánh OFF an toàn, update tới instance đủ nhanh |
| Schema mở rộng thêm cột nullable | Có thể rollback code | Code cũ vẫn chạy trên schema mở rộng |
| Đã drop cột mà code cũ cần | Roll forward hoặc sửa schema có kế hoạch | Không đưa code cũ lên nếu thiếu dữ liệu/cột |
| Đã ghi dữ liệu theo semantics mới | Roll forward + reconciliation | Bảo toàn các giao dịch đã cam kết |
| Payment đã charge sai | Dừng giao dịch mới + điều tra + compensation | Không retry mù hoặc sửa ledger trực tiếp |
| Database bị xóa dữ liệu hàng loạt | Đánh giá PITR/restore | Biết RPO/RTO, mất dữ liệu và quan hệ với service khác |
| Event schema mới làm consumer cũ lỗi | Dừng producer/route, sửa consumer hoặc phát contract tương thích | Xử lý queue tồn đọng và DLQ |

Bảng này định hướng xử lý, không thay thế runbook và kiểm tra trạng thái thực của hệ thống.

## 4. Đơn vị phát hành phải truy vết được

Muốn rollback, phải biết chính xác **đã phát hành cái gì**. Một release record nên liên kết:

- **Git commit SHA/tag** và version artifact.
- **Container image digest**, không chỉ tag dạng latest hoặc stable.
- **Application configuration revision** và flag ruleset version.
- **Database migration set/version**, cùng tiến độ backfill.
- **API/event contract versions** mà release hỗ trợ.
- **Infrastructure/Gateway/Ingress revision** nếu thay đổi tuyến.
- **Thời điểm triển khai**, môi trường, actor/change ticket và cohort.
- **Health/SLO trước và sau**, cùng quyết định tiếp tục hoặc dừng rollout.

Ví dụ manifest để vận hành tham khảo:

~~~yaml
releaseId: checkout-2026-11-12-r13
service: order-service
environment: production

application:
  gitCommit: "8c76fd4"
  image: "registry.example.com/order-service@sha256:<immutable-digest>"

configuration:
  revision: "order-config-103"

featureFlags:
  checkout.pricing-v2:
    ruleRevision: "pricing-rule-17"
    rolloutPercent: 20

data:
  schemaVersion: "V20261112_02"
  backfillJob: "order-money-backfill-20261112"
  backfillState: "completed"

contracts:
  outboundPayment: "payments-v2-compatible"
  emittedOrderEvent: 2

rollback:
  lastKnownGoodApplication: "order-service-v12"
  lastKnownGoodConfiguration: "order-config-102"
  legacyReadSupported: true
  schemaRollbackAllowed: false
~~~

Manifest **minh họa**, không phải cấu trúc chuẩn của công cụ cụ thể. Giá trị digest trong ví dụ là placeholder và không thể dùng để triển khai thật.

**Release không phải chỉ có một version.** Nó là một tập revision và trạng thái, đôi khi thay đổi ở nhiều thời điểm. Runbook phải xác định tổ hợp nào được phép chạy cùng nhau.

## 5. Chuẩn bị rollback trước khi phát hành

Rollback an toàn bắt đầu **trước** khi code mới được triển khai.

1. **Lưu artifact cũ:** image và config revision đã biết tốt phải còn tồn tại và được kiểm chứng.
2. **Đặt compatibility window:** version cũ có đọc/ghi được schema và message mới trong giai đoạn chuyển đổi?
3. **Thiết kế migration có thể mở rộng trước:** giữ field cũ cho đến khi mọi consumer đã rời bỏ.
4. **Định nghĩa rollback trigger:** tỷ lệ lỗi, latency, business invariant, số payment mismatch, backlog.
5. **Xác định ai quyết định:** owner, on-call, người duyệt thay đổi nhạy cảm, người thực thi và người đối soát.
6. **Biết thời gian hội tụ:** config/flag cập nhật đến tất cả instance mất bao lâu; routing drain mất bao lâu.
7. **Chuẩn bị backup/restore runbook:** biết giới hạn RPO/RTO và đã kiểm tra khả năng restore.
8. **Có lối xử lý dữ liệu đã ghi:** versioning, idempotency, audit, reconciliation và compensation.
9. **Kiểm thử kịch bản thất bại:** không chỉ kiểm tra đường triển khai thành công.
10. **Gắn cổng ra quyết định:** có thể tạm dừng phát hành, giữ một tỷ lệ nhỏ, tắt cờ hoặc roll forward.

Một tài liệu “rollback: chạy lệnh rollback deployment” là chưa đủ nếu release có migration dữ liệu và side effect.

## 6. Quay lui mã ứng dụng

### 6.1. Quay lui deployment khác với đảo commit Git

Trong CI/CD, binary/container image đã được build và xác minh là đơn vị triển khai. **Rollback runtime** thường là chuyển về image trước đã biết tốt, không cần viết lại lịch sử Git.

- **Runtime rollback:** thay revision của Kubernetes Deployment, image digest hoặc traffic routing.
- **Git revert:** tạo commit mới đảo thay đổi mã nguồn ở repository dùng chung; lịch sử vẫn tuyến tính và audit được.
- **Git reset/force push:** viết lại lịch sử branch, có thể phá công việc của người khác; không phải cách tiêu chuẩn để khôi phục production.
- **Build lại cùng tag:** không đảm bảo nhận đúng artifact cũ nếu dependency/build không tái lập được.

Trong repository dùng chung, ưu tiên **git revert** cho việc đảo một commit cần duy trì lịch sử, và để pipeline tạo artifact mới theo quy định. Khi xử lý sự cố đang xảy ra, runtime rollback thường cần thực hiện trước nếu an toàn.

### 6.2. Ví dụ Kubernetes Deployment

Một số lệnh có thể dùng khi Deployment đã có revision lịch sử:

~~~bash
# Xem các revision của Deployment.
kubectl rollout history deployment/order-service -n commerce

# Kiểm tra trạng thái rollout hiện tại.
kubectl rollout status deployment/order-service -n commerce

# Chuyển về revision trước nếu đã xác nhận tương thích dữ liệu/contract.
kubectl rollout undo deployment/order-service -n commerce

# Theo dõi sau khi quay lui.
kubectl rollout status deployment/order-service -n commerce
~~~

Các lệnh trên là ví dụ vận hành, chỉ nên thực hiện trong đúng cluster, namespace, quyền và runbook của tổ chức. **kubectl rollout undo** chỉ giúp đổi template revision của Deployment; nó không rollback database, message, feature flag, ConfigMap ngoài template hoặc side effect.

Kubernetes không giữ vô hạn mọi revision: **revisionHistoryLimit**, image registry retention và khả năng pull image ảnh hưởng rollback. Nếu các image cũ đã bị xóa, history manifest còn nhưng rollback vẫn có thể thất bại.

Với GitOps như Argo CD/Flux, thay đổi trực tiếp cluster có thể bị controller đồng bộ lại theo Git. Kế hoạch phục hồi phải xác định **source of truth** và cách cập nhật Git/desired state, tránh tình trạng vừa rollback xong lại tự quay về release lỗi.

### 6.3. Traffic shift/canary

Nếu triển khai song song v12 và v13, có thể:

1. Giữ v12 đang hoạt động.
2. Gửi 1–5% traffic sang v13.
3. Quan sát metrics theo variant.
4. Nếu lỗi, chuyển traffic v13 về 0.
5. Drain in-flight request và xử lý background job đã được v13 khởi chạy.
6. Điều tra dữ liệu/event v13 đã phát trước khi xóa deployment.

Việc hạ traffic về 0 không tự hủy request đã đến pod v13 hoặc message đã vào queue. Với trạng thái giao dịch, cần theo dõi đến khi đạt điểm kết thúc an toàn.

### 6.4. Khi không được rollback mã

Tránh đưa code cũ lên nếu:

- Code cũ không hiểu field/schema đã trở thành nguồn dữ liệu chính.
- Code cũ ghi đè hoặc bỏ mất dữ liệu mới khi cập nhật record.
- Event version cũ phá consumer mới hoặc không còn được chấp nhận.
- Logic quyền/bảo mật cũ có lỗ hổng nghiêm trọng vừa được vá.
- Secret/credential hoặc API partner đã thay đổi làm client cũ không thể kết nối.
- Transaction đã chuyển sang trạng thái mà state machine cũ không biểu diễn được.

Trong các trường hợp này, dùng **roll forward**, adapter tương thích hoặc chế độ tạm dừng thao tác nguy hiểm để bảo vệ dữ liệu.

## 7. Quay lui cấu hình runtime

Cấu hình có thể thay đổi hành vi mà không đổi image, ví dụ:

- Connection pool từ 40 lên 400 làm downstream database cạn connection.
- Timeout từ 1000 ms xuống 100 ms làm request bị timeout hàng loạt.
- Đổi endpoint sai region khiến dữ liệu đi sai cụm.
- Đổi retry policy gây **retry storm**.
- Bật circuit breaker/feature flag sai đối tượng.
- Thay cache TTL khiến client đọc dữ liệu cũ quá lâu.

Một cấu hình nên có **revision**, validation và audit:

~~~yaml
service: order-service
configRevision: 102
http:
  inventory:
    connectTimeoutMs: 250
    responseTimeoutMs: 1000
    maxConnections: 30
resilience:
  inventory:
    maxConcurrentCalls: 20
    retry:
      maxAttempts: 2
      baseDelayMs: 150
~~~

Đây là cấu trúc minh họa, không mặc định tương thích với Spring Boot properties của một module cụ thể.

### 7.1. Quy trình revert config

1. Xác định change gây lỗi và revision gần nhất đã biết tốt.
2. Kiểm tra **khác biệt cấu hình** giữa revision lỗi và revision tốt; không xóa các thay đổi độc lập mới hơn một cách vô tình.
3. Kiểm tra config cũ còn tương thích code và dependency hiện tại.
4. Áp revision hoặc patch đã được xác minh qua control plane.
5. Kiểm tra tất cả instance nhận revision mới; có thể cần restart/refresh theo cơ chế nền tảng.
6. Quan sát metrics/error rate và xác nhận incident được giảm.
7. Ghi audit và mở hành động khắc phục nguyên nhân gốc.

**Cấu hình có thể lan không đồng thời.** Một pod còn timeout 100 ms trong khi pod khác đã dùng 1000 ms; cần metric **activeConfigRevision**, **configAge** và chiến lược snapshot nhất quán.

### 7.2. Cấu hình, feature flag và secret không giống nhau

- **Config:** khôi phục giá trị hợp lệ có thể xử lý lỗi vận hành.
- **Feature flag:** thay đổi đối tượng chạy đường code, nhưng dữ liệu đã tạo dưới flag ON vẫn tồn tại.
- **Secret:** nếu credential cũ đã bị thu hồi hoặc nghi lộ, **không rollback sang secret cũ** chỉ để sửa kết nối. Phải sửa configuration/identity, phát hành credential an toàn và phối hợp rotation.

Không lưu secret trong version control hoặc public feature flag payload. Một config revision có thể chứa tham chiếu tới secret, nhưng secret manager sở hữu giá trị và vòng đời riêng.

## 8. Feature flag là công cụ cô lập, không phải nút “hoàn tác”

Một cách phát hành an toàn là triển khai code mới với flag **OFF**, xác minh service hoạt động, rồi bật cho cohort nhỏ.

Ví dụ:

~~~text
checkout.pricing-v2
  OFF -> tính giá bằng thuật toán cũ
  ON  -> tính giá bằng thuật toán mới

Rollout:
  internal testers -> 1% -> 5% -> 20% -> 100%
~~~

Khi lỗi, đưa cohort mới về OFF có thể dừng **yêu cầu tương lai** dùng logic mới. Nhưng các giao dịch đang xử lý cần giữ quyết định nhất quán.

### 8.1. Đóng băng quyết định cho một giao dịch

Nếu Order tính giá theo v2 rồi Payment lấy lại flag sau đó và quyết định v1, hai service có thể bất đồng về giá. Giải pháp là xác định và lưu **pricingPolicyVersion** tại thời điểm bắt đầu nghiệp vụ:

~~~json
{
  "orderId": "ORD-2026-112",
  "pricingPolicyVersion": "v2",
  "quotedTotalMinor": 150000,
  "currency": "VND",
  "status": "PAYMENT_PENDING"
}
~~~

Khi tắt flag, các đơn **đã được tạo** theo v2 vẫn được hoàn tất/đối soát bằng quote và version đã cam kết, hoặc chuyển sang trạng thái lỗi có kiểm soát. Không tính lại bằng v1 mà không có chính sách nghiệp vụ.

### 8.2. Kill switch phải được diễn tập

Kiểm tra:

- Ai có quyền tắt flag production?
- Control plane có sẵn khi sự cố mạng xảy ra?
- SDK update qua push/poll với độ trễ tối đa nào?
- Instance mới khởi động khi thiếu snapshot sẽ chọn hành vi gì?
- Request đang chạy và job nền có tôn trọng trạng thái cố định của giao dịch?
- Metric nào chứng minh traffic mới thật sự không còn chạy nhánh lỗi?

**Không** dùng cờ để tắt authentication, authorization, validation hoặc kiểm tra tính toàn vẹn dữ liệu chỉ nhằm khôi phục throughput.

## 9. Thay đổi database: nguyên tắc Expand–Migrate–Contract

Trong microservices, dịch vụ sở hữu database thường cần hỗ trợ **hai phiên bản ứng dụng đồng thời** trong rolling deploy. Một migration kiểu “rename cột rồi triển khai code mới” có thể phá code cũ trong khoảng chuyển tiếp.

**Expand–Migrate–Contract** giảm rủi ro:

1. **Expand:** thêm schema mới nhưng giữ schema cũ hoạt động.
2. **Deploy compatible code:** code đọc/ghi tương thích cả hai dạng trong giai đoạn chuyển tiếp.
3. **Migrate/backfill:** chuyển dữ liệu lịch sử với job có thể tiếp tục/chạy lại an toàn.
4. **Switch reads/writes:** bật đường mới theo cohort hoặc bước phát hành.
5. **Verify/observe:** kiểm tra tính nhất quán và những consumer còn dùng dạng cũ.
6. **Contract:** xóa schema/code cũ sau khi hết cửa sổ tương thích.

~~~mermaid
flowchart TD
    A[Schema cũ + App v1] --> B[Expand: thêm field mới]
    B --> C[Deploy app đọc cả hai]
    C --> D[Backfill và đồng bộ write path]
    D --> E[Chuyển read path sang field mới]
    E --> F{Mọi caller cũ đã rời đi?}
    F -->|Chưa| E
    F -->|Rồi| G[Contract: xóa field cũ]
~~~

**Điểm rollback thuận lợi nhất** là trước bước Contract. Lúc đó code cũ có thể vẫn chạy nếu các trường cũ luôn được giữ hợp lệ trong quá trình dual-read/dual-write. Sau khi xóa dữ liệu, khả năng quay lui phải được đánh giá lại từ đầu.

### 9.1. Ví dụ: đổi cách lưu số tiền

Ban đầu **orders.discount_amount** là kiểu decimal. Mục tiêu dùng **discount_amount_minor** kiểu bigint để lưu đơn vị nhỏ nhất (cent, đồng nhỏ nhất theo currency). Ví dụ PostgreSQL:

~~~sql
-- Bước Expand: thêm cột mới, chưa xóa cột cũ.
ALTER TABLE orders
ADD COLUMN discount_amount_minor BIGINT;
~~~

Backfill mẫu, giả sử hệ thống **chỉ dùng một đơn vị tiền có scale 2** trong dữ liệu ví dụ:

~~~sql
UPDATE orders
SET discount_amount_minor =
    ROUND(discount_amount * 100)::BIGINT
WHERE discount_amount_minor IS NULL
  AND discount_amount IS NOT NULL;
~~~

**Ví dụ này không áp dụng chung cho mọi currency.** VND thường không có phần thập phân theo đơn vị tiền được sử dụng, trong khi USD/EUR thường có hai chữ số thập phân. Ứng dụng thật phải dùng currency scale được định nghĩa và xử lý rounding rõ ràng; tốt hơn là xây migration theo contract tiền tệ của domain.

Trong sản xuất:

- Backfill theo **batch** có checkpoint để tránh khóa bảng dài.
- Dùng điều kiện cập nhật có thể chạy lại, bảo vệ row đã được writer mới ghi.
- Giải quyết race giữa backfill và concurrent writes.
- Xác định **source of truth** cho từng giai đoạn, không suy ra từ việc field có null đơn lẻ nếu có giá trị 0 hợp lệ.
- Đo lượng record chưa migrate và dữ liệu sai lệch.
- Bật read mới chỉ sau khi các bất biến được xác nhận.
- Không drop cột cũ khi còn code v1 hoặc job/consumer cần nó.

### 9.2. Dual-write không tự động an toàn

Nếu code viết hai trường bằng hai lệnh không cùng transaction, có thể cập nhật trường mới thành công nhưng trường cũ thất bại, dẫn đến bất đồng dữ liệu.

Với hai trường trong **cùng database transaction**, có thể cập nhật atomically:

~~~sql
UPDATE orders
SET discount_amount = :amount_major,
    discount_amount_minor = :amount_minor
WHERE id = :order_id;
~~~

Các placeholder có tên trong ví dụ cần được bind bằng framework truy vấn tham số hóa, không nối string trực tiếp.

Nếu dual-write qua **hai database khác nhau**, giao dịch ACID nội bộ không bao phủ cả hai. Cần thiết kế **outbox, idempotent consumer, reconciliation** hoặc một chiến lược phân tán phù hợp.

### 9.3. Rollback trong mỗi giai đoạn

| Giai đoạn | Code v1 có thể chạy? | Khó khăn quay lui |
| --- | --- | --- |
| Trước Expand | Có | Rollback code thông thường |
| Sau Expand, chưa backfill | Thường có | Cột mới không ảnh hưởng v1 nếu thay đổi additive |
| Sau Backfill, vẫn giữ và đồng bộ cột cũ | Có thể | Phải xác minh v1 đọc/ghi đúng |
| Sau chuyển read path mới, cột cũ vẫn đồng bộ | Có thể | Phải bảo đảm dữ liệu cho legacy còn đầy đủ |
| Sau Contract đã drop cột cũ | Thường không | Cần roll forward, recreate/backfill nếu có nguồn đầy đủ |
| Sau đổi semantics và xóa nguồn cũ | Có thể bất khả thi | Cần kế hoạch khôi phục/reconcile riêng |

“Recreate một cột bằng ALTER TABLE ADD COLUMN” **không khôi phục giá trị đã mất**. Schema quay lui và data quay lui là hai bài toán khác nhau.

## 10. Những thay đổi dữ liệu khó hoặc không thể đảo ngược

### 10.1. Xóa dữ liệu

**DELETE/TRUNCATE/DROP** có thể làm mất record, lịch sử hoặc schema. Undo migration không đảm bảo phục hồi. Nếu transaction chưa commit có thể rollback transaction; sau khi commit, cần backup, log hoặc dữ liệu gốc để tái tạo.

### 10.2. Biến đổi mất thông tin

Ví dụ gộp **firstName + lastName** thành một chuỗi, làm tròn số tiền sai scale, chuyển trạng thái chi tiết thành boolean, hash không lưu giá trị gốc hoặc nén nhiều enum thành một category chung.

Những phép biến đổi này thường **không có hàm nghịch đảo duy nhất**. Nếu cần khả năng khôi phục, lưu nguồn hoặc mapping/version đủ lâu trước khi loại bỏ.

### 10.3. Thay đổi định danh

Đổi primary key, orderId, tenantId hoặc cách phân vùng có thể ảnh hưởng foreign key, event, cache, URL public và hệ thống đối tác. Nếu id cũ đã được đưa ra ngoài, không thể đơn giản chạy lại migration để “quên” id mới.

### 10.4. Backfill sai

Một job sai có thể ghi đè hàng triệu dòng. Nếu chỉ có giá trị mới mà không có audit/before-image, khó phục hồi giá trị cũ. Cần đánh giá CDC database log, PITR hoặc snapshot trước batch, sau đó xác minh phạm vi ảnh hưởng.

### 10.5. Migration phi giao dịch

Một số DDL hoặc thao tác online index không chạy trong transaction thông thường tùy database và công cụ migration. Ví dụ PostgreSQL có giới hạn riêng với **CREATE INDEX CONCURRENTLY**. Nếu migration thất bại giữa chừng, có thể còn artifact/partial state cần cleanup theo runbook.

Không giả định mọi migration tool có thể tự động thực hiện **down migration** an toàn; “down script có tồn tại” không đồng nghĩa có thể khôi phục dữ liệu.

### 10.6. External side effect

Thanh toán, gửi email, cấp quyền ở provider bên ngoài, chuyển hàng và phát sự kiện là các hành động đã xảy ra ngoài database của service. Chỉ rollback DB cục bộ có thể làm mất liên kết với side effect, khiến các lần retry sau đó thực hiện trùng.

## 11. Khôi phục database và điểm cần bảo vệ

**Backup không có giá trị nếu chưa từng chứng minh được khả năng restore.** Một kế hoạch recovery phải xác định:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận theo thời gian.
- **RTO (Recovery Time Objective):** thời gian dịch vụ cần phục hồi.
- **Backup schedule/retention:** snapshot, incremental backup, transaction log/WAL.
- **Recovery boundary:** database, shard, tenant, bảng hay toàn cluster.
- **Encryption và quyền truy cập:** ai có thể đọc/restore backup, key khôi phục ở đâu.
- **Restore drill:** đã thử restore thật, so checksum và chạy integrity checks chưa.
- **Cross-service consistency:** Order, Payment, Inventory có cần đối soát sau restore không?
- **Replay/source of truth:** event log, outbox và CDC log có khả năng tái dựng phần dữ liệu sau điểm phục hồi không?

### 11.1. Vì sao khôi phục một database có thể làm hỏng nhiều service?

Giả sử Order DB được restore về 10:00 nhưng Payment DB vẫn có giao dịch thu tiền thành công lúc 10:05. Order sau restore không thấy đơn hàng tương ứng. Nếu retry một cách ngây thơ, có thể tạo đơn mới hoặc charge lần nữa.

Cần thiết kế reconciliation:

1. Xác định khoảng thời gian và transaction ID bị ảnh hưởng.
2. Đối chiếu dữ liệu Order với Payment ledger, Inventory reservation và outbox/event.
3. Tái dựng hoặc cập nhật trạng thái bằng idempotent recovery workflow.
4. Không phát lại mọi event một cách mù; kiểm tra consumer đã xử lý hay chưa.
5. Giữ audit về các chỉnh sửa và mất dữ liệu có chủ đích.

**Restore là hoạt động gây thay đổi diện rộng**. Chỉ thực hiện sau khi xác định phạm vi, mức mất dữ liệu và kế hoạch xử lý cross-service state; không dùng như phản xạ đầu tiên cho mọi lỗi ứng dụng.

## 12. Event-driven systems: không thể thu hồi message đã phát

Trong hệ microservices dùng Kafka/RabbitMQ/SQS, producer có thể phát sự kiện khi flag ON hoặc code mới đang chạy:

~~~json
{
  "eventId": "8d65dcfa-5471-4db4-8a44-c67b975613c9",
  "eventType": "OrderPaid",
  "schemaVersion": 2,
  "orderId": "ORD-115",
  "amountMinor": 150000,
  "currency": "VND",
  "pricingPolicyVersion": "v2"
}
~~~

Nếu code Order quay về phiên bản cũ, **sự kiện đã được xuất bản vẫn tồn tại** trong broker, consumer, DLQ hoặc hệ thống phân tích. Consumer có thể đang xử lý hoặc đã phát side effect tiếp theo.

Các điểm thiết kế:

- **Schema compatibility:** consumer cũ phải có thể bỏ qua field mới khi contract cho phép; đừng đổi nghĩa field cũ âm thầm.
- **Versioning:** dùng schemaVersion/contract version có mục đích rõ.
- **Idempotency:** cùng eventId xử lý lại không được tạo side effect trùng.
- **Ordering:** event đến muộn hoặc đảo thứ tự cần có state/version guard.
- **Outbox:** đảm bảo thay đổi database và thông tin event dự định phát nằm trong một transaction thích hợp.
- **DLQ:** lưu message không xử lý được; không vô hạn retry poison message.
- **Replay:** chỉ phát lại sau khi xác định semantics, consumer state và dedup window.
- **Compensating event:** nếu nghiệp vụ cần, phát sự kiện chỉnh sửa mới có tham chiếu đến giao dịch gốc.

### 12.1. Bù trừ bằng sự kiện mới

Không cố “xóa” một event OrderPaid khỏi lịch sử sau khi consumer đã đọc. Nếu payment cần hoàn lại, có thể phát **PaymentRefunded** hoặc **PaymentCorrectionRecorded** theo nghiệp vụ, gắn originalPaymentId, reason, idempotency key và audit. Bên nhận xử lý như một sự kiện mới.

**Event correction không giống đổi lịch sử**. Những consumer đã tạo dữ liệu phái sinh có thể cần rebuild projection hoặc áp một bản điều chỉnh.

### 12.2. Consumer rollback cũng có rủi ro

Nếu Notification consumer v2 đọc message schemaVersion=2, sau đó rollback về consumer v1 chỉ hiểu version=1, queue có thể bị kẹt. Cần kiểm tra khả năng đọc **message tồn đọng** trước khi rollback consumer.

Một chiến lược là triển khai consumer có khả năng đọc version cũ và mới trước khi producer bắt đầu phát version mới. Chỉ dọn code đọc version cũ sau khi các message tồn đọng và producer legacy không còn.

## 13. Transaction phân tán, Saga và compensation

Một workflow đặt hàng có nhiều bước:

~~~mermaid
sequenceDiagram
    participant O as Order
    participant I as Inventory
    participant P as Payment
    participant N as Notification
    O->>I: Reserve inventory
    I-->>O: Reservation confirmed
    O->>P: Charge payment
    P-->>O: Payment succeeded
    O->>N: Publish confirmation
    Note over O,N: Lỗi phiên bản mới được phát hiện
    O->>P: Refund if business policy requires
    O->>I: Release reservation if order is cancelled
    O->>N: Publish correction notice
~~~

Các lệnh refund/release ở phần dưới chỉ là **ví dụ compensation có điều kiện**. Không tự động refund mọi payment khi ứng dụng rollback; quyết định phải dựa trên tình trạng order và chính sách nghiệp vụ.

Trong Saga, mỗi bước có side effect riêng và có thể có một bước bù trừ tương ứng:

| Forward action | Compensation có thể có | Điều kiện cần xét |
| --- | --- | --- |
| Reserve inventory | Release reservation | Hàng chưa xuất kho, reservation còn hiệu lực |
| Charge card | Refund payment | Nhà cung cấp hỗ trợ, đúng giao dịch, tránh double refund |
| Create shipment | Cancel shipment | Chưa giao, đối tác xác nhận hủy thành công |
| Grant entitlement | Revoke entitlement | Tôn trọng trạng thái/điều khoản sử dụng |
| Send email | Send correction email | Không thể xóa email đã nhận |
| Publish event | Publish correction event | Consumer hiểu contract chỉnh sửa |

Cần thiết kế **compensation idempotent**, phát hiện partial success và có trạng thái **COMPENSATION_PENDING/FAILED** để vận hành xử lý. Không ẩn lỗi compensation phía sau một thông báo “rollback completed”.

### 13.1. Timeout không xác định kết quả

Nếu Order gọi Payment rồi timeout, không được kết luận Payment chưa charge. Khi khôi phục:

1. Truy vấn trạng thái bằng idempotency key/paymentId.
2. Xác định đã success, failed hay pending/unknown.
3. Chỉ retry theo policy đã kiểm soát.
4. Tránh tạo payment mới với idempotency key mới cho cùng business action khi kết quả cũ chưa rõ.
5. Ghi lại trạng thái và quyết định đối soát.

## 14. Tương thích API giữa các phiên bản service

Một deployment thường là **rolling**, nghĩa là nhiều version đồng thời phục vụ traffic. Rollback cũng tạo lại trạng thái mixed-version.

Ví dụ:

- Order v13 gửi **POST /payments** với trường **pricingPolicyVersion**.
- Payment v8 hiểu cả trường cũ và mới.
- Sau đó Payment v9 bắt buộc trường mới.
- Nếu rollback Order về v12 không gửi trường đó, Payment v9 có thể trả 400.

Để tránh:

1. Producer thêm field mới theo quy tắc optional/forward-compatible trước.
2. Consumer chấp nhận cả hai format trong giai đoạn chuyển tiếp.
3. Contract tests kiểm tra các cặp version đang chạy và sắp triển khai.
4. Khi rollout xong và hết thời hạn deprecation, mới bỏ đường cũ.
5. Với trường bắt buộc mới, thay đổi phải đi qua nhiều release có tương thích rõ.

**Consumer-Driven Contract Testing** hỗ trợ phát hiện breaking change ở API boundary. Tuy vậy, contract pass không chứng minh database và side effect đã an toàn khi rollback.

### 14.1. Ma trận version

| | Payment v8 | Payment v9 |
| --- | --- | --- |
| Order v12 | PASS | FAIL nếu Payment v9 bắt buộc field mới |
| Order v13 | PASS | PASS |

Nếu production đã ở Payment v9, rollback Order v13 → v12 **không an toàn** trừ khi Payment v9 được sửa để hỗ trợ v12, hoặc routing đảm bảo v12 chỉ gọi phiên bản tương thích.

Không chọn phiên bản chỉ vì “đã chạy ổn tuần trước” khi các dependency khác đã tiến lên.

## 15. Blue-green, canary và rolling release

| Chiến lược | Lợi ích khi phục hồi | Điều cần thận trọng |
| --- | --- | --- |
| **Rolling** | Có revision history, thay dần instance | Nhiều version dùng chung DB trong giai đoạn chuyển tiếp |
| **Blue-green** | Chuyển traffic giữa hai môi trường nhanh | DB, queue và side effect thường vẫn dùng chung |
| **Canary** | Giới hạn số request gặp code lỗi | Cohort nhỏ có thể vẫn thực hiện hành động không đảo ngược |
| **Feature flag** | Tắt đường tính năng nhanh khi code đã triển khai | Dữ liệu từ flag ON vẫn cần xử lý |
| **Traffic shadowing** | So sánh hành vi mới với traffic thực | Không được cho shadow path tạo payment/email/ghi dữ liệu thật |

**Blue-green không tự giải quyết rollback database** nếu cả blue và green dùng cùng một database. Với hệ thống có migration khó đảo ngược, cần tách giai đoạn schema và bảo đảm cả hai version cùng hoạt động trước khi chuyển traffic.

Canary đặc biệt hữu ích nếu có **business guardrail** chứ không chỉ HTTP 5xx. Một thuật toán giá sai có thể trả 200 rất nhanh; dashboard lỗi HTTP vẫn xanh trong khi doanh thu bị tính sai.

## 16. Quy trình ứng phó sự cố sau phát hành

Một runbook rõ ràng có thể tổ chức thành các pha:

### Pha A — Phát hiện và khoanh vùng

1. Xác định thời điểm bắt đầu lỗi, release/config/flag revision đã thay đổi.
2. Kiểm tra lỗi là **availability**, **performance**, **security**, **data correctness** hay **business side effect**.
3. Xác định phạm vi theo service, version, region, tenant, cohort và thời gian.
4. Đánh giá có giao dịch đang tiếp diễn, queue tồn đọng hoặc side effect chưa rõ kết quả.
5. Ghi lại dữ kiện cần thiết để điều tra trước khi thao tác thay đổi lớn; tránh làm mất audit.

### Pha B — Ngăn thiệt hại tiếp tục

1. Dừng mở rộng rollout hoặc hạ traffic canary.
2. Tắt feature flag nếu nhánh OFF thật sự an toàn.
3. Nếu có nguy cơ mất tiền/dữ liệu, hạn chế riêng endpoint hoặc workflow nguy hiểm theo runbook.
4. Không tự tắt cơ chế xác thực, kiểm tra quyền hoặc dữ liệu để “chạy tiếp”.
5. Bảo toàn dữ liệu đã ghi và trạng thái giao dịch đang pending.

### Pha C — Chọn phương án phục hồi

Phân loại:

- **Chỉ code/config lỗi, dữ liệu còn tương thích:** rollback runtime/config.
- **Schema/data đã tiến nhưng vẫn tương thích backward:** rollback code có giám sát.
- **Không còn tương thích:** roll forward, thêm adapter hoặc khôi phục khả năng đọc/ghi.
- **Dữ liệu đã mất hoặc biến đổi sai:** cân nhắc PITR/backup, repair job/reconciliation.
- **Side effect ngoài hệ thống:** compensation có kiểm soát.
- **Không rõ trạng thái:** giữ xử lý ở trạng thái pending/blocked phù hợp, thu thập thêm bằng chứng; không giả định thành công/thất bại.

### Pha D — Thực thi có giới hạn

1. Thực hiện một bước có phạm vi rõ.
2. Chờ cơ chế propagation/rollout hội tụ theo thực tế.
3. Quan sát traffic, logs, metrics và bất biến nghiệp vụ.
4. Quyết định tiếp tục hay dừng theo ngưỡng đã định.
5. Ghi nhận thay đổi, thời điểm và người chịu trách nhiệm.

### Pha E — Phục hồi dữ liệu và kết thúc

1. Reconcile transaction/payment/reservation/event trong khoảng ảnh hưởng.
2. Chạy repair/compensation idempotent, lưu kết quả từng record.
3. Kiểm tra read model/cache/search index nhất quán.
4. Xác nhận hệ thống ổn định và backlog hợp lý.
5. Viết post-incident review, bổ sung guardrails và test cho lần sau.

**Tách “phục hồi tỷ lệ request thành công” khỏi “khôi phục tính đúng đắn của dữ liệu”.** API có thể đã trả 200 trở lại nhưng còn hàng nghìn đơn cần đối soát.

## 17. Runbook quyết định theo dấu hiệu cụ thể

| Dấu hiệu | Câu hỏi kiểm tra ngay | Bước phục hồi có thể chọn |
| --- | --- | --- |
| p95 latency tăng ngay sau thay timeout | Config revision nào khác? | Revert config đã biết tốt |
| 5xx tăng ở code v13, không có migration | Image v12 còn tương thích? | Rollback deployment |
| Giảm giá sai nhưng response vẫn 200 | Có bao nhiêu đơn bị tính sai? | Tắt rollout; đối soát/compensate |
| Code cũ crash vì thiếu cột | Schema nào bị drop? | Roll forward hoặc phục hồi schema/data có kế hoạch |
| Consumer DLQ tăng sau event v2 | Consumer còn hiểu schemaVersion=2? | Tạm dừng producer/replay, sửa consumer tương thích |
| DB data bị backfill sai | Có before-image/PITR không? | Dừng job, snapshot hiện tại, recovery/repair |
| Refund API timeout | Kết quả giao dịch có chắc chắn? | Query status, idempotency, reconciliation |
| Config flag cập nhật không đồng đều | Revision nào trên mỗi replica? | Sửa propagation, giữ rollout ổn định |
| Cache trả dữ liệu sai sau rollback | Cache keys/schema có version? | Invalidate/rebuild theo phiên bản |
| Một region lỗi sau release | Có routing và dữ liệu độc lập? | Hạ traffic hoặc cô lập region theo runbook |

Không biến bảng thành tự động hóa vô điều kiện. Mỗi thao tác phải dựa vào trạng thái thật và giới hạn của hệ thống.

## 18. Ví dụ code: giữ quyết định giao dịch khi thay đổi hành vi

Để minh họa, một checkout operation không nên đọc flag mới nhiều lần giữa lúc tính giá, lưu đơn và gửi payment:

~~~java
public record PricingDecision(
    String policyVersion,
    String configurationRevision
) {}

public record PricedOrder(
    String orderId,
    long totalMinor,
    String currency,
    PricingDecision decision
) {}

public interface PricingPolicySelector {
    PricingDecision decideFor(String authenticatedCustomerId);
}

public interface OrderPricingService {
    PricedOrder calculate(
        String authenticatedCustomerId,
        CheckoutRequest request,
        PricingDecision decision
    );
}
~~~

Service xác định decision một lần:

~~~java
public final class CheckoutCoordinator {
    private final PricingPolicySelector policySelector;
    private final OrderPricingService pricing;
    private final OrderRepository repository;
    private final PaymentWorkflow payment;

    public CheckoutCoordinator(
            PricingPolicySelector policySelector,
            OrderPricingService pricing,
            OrderRepository repository,
            PaymentWorkflow payment
    ) {
        this.policySelector = policySelector;
        this.pricing = pricing;
        this.repository = repository;
        this.payment = payment;
    }

    public CheckoutResult start(
            String authenticatedCustomerId,
            CheckoutRequest request,
            String idempotencyKey
    ) {
        // Cần validate idempotency key, ownership và request trước khi xử lý.
        PricingDecision decision =
            policySelector.decideFor(authenticatedCustomerId);

        PricedOrder priced =
            pricing.calculate(authenticatedCustomerId, request, decision);

        // Lưu quote, policy version và trạng thái giao dịch.
        // Repository phải xử lý idempotency atomically.
        OrderRecord record = repository.createOrLoadPending(
            authenticatedCustomerId,
            idempotencyKey,
            priced
        );

        // Workflow phải dùng chính quote/version đã lưu.
        // Timeout không được tự hiểu là Payment chưa xử lý.
        payment.ensurePayment(record);

        return new CheckoutResult(record.id(), record.status());
    }
}
~~~

Các interface **CheckoutRequest**, **OrderRepository**, **PaymentWorkflow**, **OrderRecord**, **CheckoutResult** là thành phần domain minh họa. Chương trình hoàn chỉnh cần transaction boundary, optimistic locking, idempotency, authorization và bảo vệ concurrency.

Một lưu ý triển khai: nếu **createOrLoadPending** trả record đã tồn tại do client retry, **payment.ensurePayment** phải sử dụng quote và decision được lưu trong record đó, không dùng kết quả tính mới từ request hiện tại. Vì vậy không được dựa vào giá trị **priced** mới khi thực hiện side effect cho order cũ.

Khi flag bị tắt trong lúc một đơn đang xử lý, policyVersion trên record giữ cho việc khôi phục và đối soát có ngữ cảnh chính xác.

## 19. Ví dụ kế hoạch sửa dữ liệu sai bằng job có checkpoint

Giả sử backfill đã ghi **discount_amount_minor** sai cho một tập order. Cách sửa không nên là một lệnh UPDATE toàn bảng chưa kiểm soát.

Một repair job có thể gồm:

1. Tạo **incident identifier** và xác định tiêu chí chọn record bị ảnh hưởng bằng dữ kiện.
2. Snapshot/export **record id, version và giá trị liên quan** trước khi sửa theo chính sách dữ liệu.
3. Tính **giá trị đúng** từ nguồn authoritative còn nguyên vẹn; nếu không đủ nguồn, đánh dấu cần xử lý thủ công.
4. Chạy **dry-run** để biết phạm vi và mức thay đổi, có phê duyệt theo mức rủi ro.
5. Repair theo batch nhỏ, dùng optimistic locking/CAS hoặc điều kiện version để không ghi đè record đã thay đổi sau khi scan.
6. Lưu idempotency/checkpoint: batch, record, before/after, outcome.
7. Theo dõi lỗi, backpressure và khả năng tạm dừng.
8. Đối soát total, payment, invoice và các projection.
9. Ghi audit và xác minh tập dữ liệu sau sửa.

SQL minh họa tránh ghi đè thay đổi mới:

~~~sql
UPDATE orders
SET discount_amount_minor = :corrected_value,
    version = version + 1
WHERE id = :order_id
  AND version = :expected_version;
~~~

Nếu số row affected là **0**, có thể record đã đổi version hoặc ID không tồn tại. Job phải phân loại/đọc lại và quyết định thay vì cố UPDATE mù.

**Không khẳng định tính đúng của :corrected_value chỉ vì câu SQL chạy thành công.** Giá trị phải đến từ logic nghiệp vụ và nguồn dữ liệu được xác minh. Với payment ledger, có thể cần ghi bút toán điều chỉnh thay vì ghi đè giá trị lịch sử.

## 20. Các bất biến dữ liệu giúp biết khi nào đã phục hồi

Metric HTTP là cần nhưng chưa đủ. Nên định nghĩa các **business invariants**, ví dụ:

- Một **paymentId** chỉ gắn với một business payment và trạng thái cuối cùng hợp lệ.
- **chargedAmount** khớp với **committed quote** hoặc có bản ghi điều chỉnh hợp lệ.
- Một reservation không tồn tại vô thời hạn sau khi order bị hủy.
- Một order không ở đồng thời hai trạng thái kết thúc mâu thuẫn.
- Event **OrderPaid** không được dùng để đánh dấu order chưa từng tạo là hợp lệ nếu không có quy trình tái dựng.
- Các ledger entries phải cân bằng theo mô hình tài chính của hệ thống.
- Một outbox event có thể phát lại nhưng consumer không tạo nghiệp vụ trùng.

Ví dụ dashboard phục hồi:

| Metric | Mục tiêu |
| --- | --- |
| Checkout 5xx rate theo version | Quay về ngưỡng SLO |
| Checkout p95 latency | Không vượt ngân sách độ trễ |
| Pricing mismatch count | Không phát sinh mismatch mới |
| Pending payments older than threshold | Giảm về mức hoạt động bình thường |
| Duplicate payment attempts | Không tăng vì retry |
| Event DLQ/backlog | Có kế hoạch drain, không tăng không kiểm soát |
| Config/schema revision per replica | Đồng nhất theo trạng thái mong muốn |
| Repair jobs remaining/failed | Có checkpoint và tiến triển rõ |
| Reconciliation exceptions | Được phân loại và đóng theo quy trình |

Khi đánh giá hồi phục, nên phân tách **new traffic** khỏi **incidents already created**. Có thể ngừng lỗi mới ngay nhưng còn nhiều đối tượng cũ cần xử lý.

## 21. Hồi quy không dễ phát hiện bằng 5xx

Một số release lỗi vẫn trả 200:

- Giá bị làm tròn sai một đơn vị nhỏ.
- Mã giảm giá áp sai thứ tự.
- Luồng authorization bỏ kiểm tra owner nhưng API vẫn nhanh.
- Notification gửi trùng.
- Dữ liệu tenant A bị ghi sang tenant B.
- Event được phát thiếu trường mà consumer ít được sử dụng đang cần.
- Một phân vùng dữ liệu không được backfill.
- Cache trả kết quả của policy cũ dù code mới đã chạy.

Vì vậy release gate phải có cả **technical metrics** và **domain assertions**. Với thay đổi nguy hiểm, chạy **shadow calculation** không side effect để so sánh kết quả trước khi bật đường ghi mới.

**Không chạy shadow payment thật hai lần**. Shadow nên là pure function, sandbox hoặc hệ thống so sánh không phát side effect ra thế giới bên ngoài.

## 22. Thiết kế CI/CD để giữ cửa sổ rollback

Một pipeline microservices có thể thực hiện:

~~~mermaid
flowchart TD
    C[Commit + Build immutable artifact] --> T[Unit + contract + migration tests]
    T --> E[Expand schema / compatible contracts]
    E --> D[Deploy app với flag OFF]
    D --> H[Health + smoke + business checks]
    H --> R[Canary / progressive rollout]
    R --> G{Guardrails đạt?}
    G -->|Không| S[Stop rollout + chọn rollback/roll forward]
    G -->|Có| F[Full rollout]
    F --> M[Backfill / stabilize / deprecate]
    M --> X[Contract cleanup sau compatibility window]
~~~

Cửa sổ rollback được bảo toàn bằng việc:

- Không drop schema cũ ngay trong cùng release triển khai code mới.
- Giữ phiên bản consumer đọc được contract cũ và mới.
- Duy trì image cũ đã biết tốt.
- Không dùng mutable image tags trong release record.
- Ghi version cấu hình và feature flags.
- Tách migration phá hủy khỏi rollout code.
- Test thao tác rollback trên môi trường có **dữ liệu sau migration**, không chỉ dữ liệu cũ.
- Dùng canary với metric theo version/cohort.
- Có cách dừng write path nguy hiểm khi xuất hiện sự cố.

Đối với migration phá hủy không thể tránh, cần kế hoạch đặc thù: maintenance window, backup đã diễn tập, guardrail, điểm không thể quay lui (point of no return), và hướng roll-forward/restore.

## 23. “Point of no return”: đánh dấu mốc không thể rollback

Một release có thể đi qua mốc mà từ đó code cũ không còn an toàn. Ví dụ:

1. Deploy Order v13 với schema cũ và mới còn cùng tồn tại.
2. Backfill dữ liệu.
3. Chuyển writer hoàn toàn sang schema mới.
4. Dừng đồng bộ field cũ.
5. Drop field cũ.
6. Ghi event mà consumer cũ không hiểu.

Mốc **(4)** hoặc **(5)** có thể là point of no return đối với rollback Order v12. Mốc cụ thể phụ thuộc code và contract thực.

Trước mốc đó phải có:

- **Owner/approval** cho bước phá hủy.
- Bằng chứng mọi instance/consumer cần hỗ trợ đã tương thích.
- Backup hoặc kế hoạch recovery đã kiểm tra.
- Test roll-forward và data repair cho failure mode chính.
- Thông tin rõ cho on-call rằng lệnh rollback cũ không còn hợp lệ.
- Monitoring và cách dừng thao tác ngay khi phát hiện bất biến sai.

Sau mốc đó, runbook **phải chuyển chiến lược**. Một tài liệu luôn ghi “rollback về version trước” dù schema đã xóa là lỗi vận hành nguy hiểm.

## 24. Các sai lầm thường gặp

1. **Rollback image rồi mặc định database quay lui:** image chỉ là code/runtime, không phải dữ liệu.
2. **Dùng down migration để chứng minh có thể phục hồi mọi thứ:** thao tác xóa/biến đổi mất thông tin không được tái tạo bởi DDL ngược.
3. **Giữ tag mutable latest:** không xác định chính xác artifact cũ nào đã hoạt động.
4. **Không lưu config/flag revision:** sau sự cố không biết runtime đã đánh giá rule nào.
5. **Rollback code cũ lên schema mới không tương thích:** dịch vụ crash hoặc âm thầm ghi sai.
6. **Xóa field trước khi mọi consumer migrate:** phá mobile client/worker cũ hoặc event tồn đọng.
7. **Đặt flag OFF và tuyên bố dữ liệu đã được phục hồi:** giao dịch đã commit vẫn còn.
8. **Rerun payment khi timeout mà không tra cứu trạng thái:** nguy cơ double charge.
9. **Restore một database mà không đối soát service khác:** state giữa Order/Payment/Inventory lệch nhau.
10. **Backfill toàn bảng trong một transaction lớn:** tăng lock, WAL, latency và rủi ro gián đoạn.
11. **Dual-write không atomic và thiếu reconciliation:** field mới/cũ lệch dữ liệu.
12. **Chạy repair job không có checkpoint/idempotency:** retry có thể nhân đôi lỗi.
13. **Không kiểm tra message backlog:** consumer rollback không đọc được event mới.
14. **Không để ý GitOps reconciler:** rollback trực tiếp cluster bị ghi đè bằng desired state lỗi.
15. **Chỉ quan sát 5xx, bỏ qua domain invariants:** lỗi tính tiền/tiết lộ dữ liệu không nhất thiết gây 5xx.
16. **Xóa backup quá sớm:** mất khả năng khôi phục sau khi phát hiện bug trễ.
17. **Phục hồi bằng cách tái dùng secret đã lộ:** gây rủi ro bảo mật nghiêm trọng.
18. **Gọi compensation nhưng thiếu audit:** không giải trình được tiền hoặc quyền đã thay đổi.
19. **Không xác định owner/approval:** nhiều nhóm thao tác mâu thuẫn trong sự cố.
20. **Quay về code có lỗ hổng đã được vá:** sửa lỗi triển khai có thể tái mở vấn đề bảo mật.

## 25. Ví dụ quyết định phục hồi: pricing v2 làm sai 2% đơn hàng

### Tình huống

- 09:00 — Order v13 được deploy, flag pricing-v2 OFF.
- 09:10 — Bật flag 5%; hệ thống có 1.000 request checkout.
- 09:20 — Tăng flag lên 20%.
- 09:25 — Dashboard phát hiện **pricing mismatch** dù 5xx bình thường.
- 09:30 — Có 80 đơn đã tạo theo v2; 30 đơn có payment thành công, 20 pending, 30 chưa gọi payment.
- Schema mới đã có field pricingPolicyVersion nhưng chưa xóa field legacy.

Con số và thời điểm chỉ là dữ liệu giả lập để học cách lập kế hoạch.

### Bước 1: Dừng mở rộng sự cố

Tắt pricing-v2 cho **checkout mới**, hoặc đưa tỷ lệ về 0 nếu nhánh legacy còn đúng. Dừng release rollout. Kiểm tra config revision đã lan đến mọi instance.

### Bước 2: Đánh giá tính tương thích

Vì schema chỉ được mở rộng và field cũ vẫn đồng bộ, Order v12 **có thể** rollback nếu xác minh code v12 hiểu tất cả record hiện có và không phá transaction đang xử lý. Không mặc định chỉ vì schema additive là an toàn tuyệt đối.

Nếu logic v13 có lỗi cục bộ dễ vá, có thể chọn v14 roll-forward sau khi đảm bảo không tạo sai tiền mới.

### Bước 3: Phân loại 80 đơn

- **30 đơn đã charge:** so quote/charge và trạng thái; nếu sai tiền, xử lý điều chỉnh/refund theo chính sách, không xóa record.
- **20 đơn pending:** truy vấn trạng thái payment bằng idempotency key; tránh charge lại mù.
- **30 đơn chưa gọi payment:** có thể tạm giữ rồi reprice theo quy trình yêu cầu xác nhận giá, hoặc hủy an toàn tùy contract với khách hàng.

### Bước 4: Repair/reconcile

Lưu policyVersion, giá trị trước/sau, paymentId, trạng thái refund/adjustment và incident ID. Chạy repair theo từng nhóm có idempotency, checkpoint và khả năng dừng.

### Bước 5: Xác nhận phục hồi

Kiểm tra:

- Request mới không còn đi pricing-v2 lỗi.
- Số đơn mismatch mới không tăng.
- Tất cả 80 đơn đã được phân loại và có trạng thái xử lý rõ.
- Không phát sinh double charge.
- Backlog và event consumers không còn lỗi schema.
- Các khoản sửa/hoàn tiền được đối soát và audit.

Đây là ví dụ quan trọng: **phục hồi code/config có thể nhanh; hoàn thành phục hồi dữ liệu nghiệp vụ có thể là một công việc riêng cần bằng chứng.**

## 26. Bảng kiểm trước khi phê duyệt release

### Mã nguồn và deployment

- [ ] Image/commit bất biến và biết bản last-known-good.
- [ ] Rollback target còn được lưu và có thể chạy.
- [ ] Các service/version trong rolling deployment tương thích.
- [ ] Có metric theo version, region, cohort.
- [ ] Đã định nghĩa trigger dừng rollout.
- [ ] Đã thử smoke test với bản cũ trên schema mới.

### Cấu hình và feature flags

- [ ] Có revision, diff và audit.
- [ ] Có quyền thay đổi phù hợp và lối xử lý khẩn cấp.
- [ ] Default/fallback được kiểm tra theo tính đúng đắn nghiệp vụ.
- [ ] Propagation delay và config staleness đo được.
- [ ] Không dùng flag để bypass authorization hoặc validation.
- [ ] Secret rotation có runbook riêng.

### Schema và dữ liệu

- [ ] Migration tuân thủ expand–migrate–contract khi cần mixed-version.
- [ ] Không drop field trước khi consumer cũ rời đi.
- [ ] Backfill có checkpoint, batch size, concurrency guard và idempotency.
- [ ] Có data invariant/reconciliation query.
- [ ] Backup/restore và RPO/RTO được kiểm chứng.
- [ ] Đã xác định point of no return.
- [ ] Phương án roll-forward/repair được chuẩn bị cho bước khó đảo ngược.

### Giao tiếp và side effect

- [ ] HTTP/gRPC/event contract versions tương thích.
- [ ] Event/message backlog và retry policy được xét khi rollback.
- [ ] Payment/refund/reservation có idempotency và cách tra cứu trạng thái.
- [ ] Compensation đã thiết kế cho side effect tương ứng.
- [ ] Không dùng shadow request để tạo external side effect thật.
- [ ] Có audit và owner cho reconciliation sau sự cố.

## 27. Câu hỏi tự kiểm tra

**1. Khi nào quay lui Docker image là đủ?**  
Khi lỗi chỉ nằm ở mã ứng dụng hoặc cấu hình kèm image và phiên bản cũ vẫn tương thích với database, API, event và side effect hiện tại. Vẫn cần theo dõi request đang chạy và sức khỏe sau rollback.

**2. Tại sao Git revert không có nghĩa production đã rollback?**  
Git revert tạo commit mới trong repository. Production chỉ thay đổi khi pipeline build/deploy bản tương ứng; database và hệ thống bên ngoài vẫn giữ trạng thái đã xảy ra.

**3. Nếu một migration xóa cột đã chạy thành công, có thể tạo lại cột đó rồi coi là rollback không?**  
Không. Tạo lại schema không tái tạo giá trị đã xóa. Cần nguồn dữ liệu còn nguyên, backup/PITR hoặc repair có chứng cứ.

**4. Vì sao code v12 có thể không chạy trên schema v13?**  
Vì v13 có thể đã drop/rename field, đổi constraint, format hoặc semantics mà v12 dựa vào. Rollback phải xét **compatibility matrix**.

**5. Feature flag OFF có tự refund các đơn tính sai không?**  
Không. Flag chỉ ảnh hưởng quyết định chọn code cho những request tiếp theo; các giao dịch cũ cần đối soát và compensation riêng.

**6. Khi một lời gọi Payment timeout, có nên thử lại ngay bằng paymentId mới?**  
Không. Timeout không chứng minh Payment chưa thực hiện thao tác. Phải tra cứu trạng thái, dùng idempotency và policy retry an toàn.

**7. Roll forward khác rollback thế nào?**  
Rollback đưa một thành phần về revision trước. Roll forward phát hành bản sửa mới phù hợp với dữ liệu/contract hiện tại khi quay về bản cũ không an toàn hoặc không khả thi.

**8. RPO và RTO khác nhau ra sao?**  
RPO là mức mất dữ liệu tối đa có thể chấp nhận; RTO là thời gian phục hồi mục tiêu. Cả hai cần được xác định dựa trên yêu cầu nghiệp vụ và khả năng thực tế.

**9. Tại sao restore Order DB có thể làm lệch Payment DB?**  
Vì mỗi service có trạng thái độc lập. Order được đưa về một thời điểm cũ trong khi Payment vẫn có các giao dịch mới, nên phải reconcile xuyên service.

**10. Khi nào nên dùng expand–migrate–contract?**  
Khi nhiều phiên bản app/consumer có thể chạy cùng lúc hoặc thay đổi schema không tương thích trực tiếp. Chiến lược giữ cửa sổ tương thích trước khi xóa đường cũ.

**11. Điều gì chứng minh sự cố đã kết thúc nếu 5xx về bình thường?**  
Phải kiểm tra thêm business invariants, dữ liệu đã ghi, payment/refund, message backlog và các record bị ảnh hưởng đã được phân loại/xử lý.

**12. Vì sao một down migration có thể nguy hiểm?**  
Vì phép nghịch đảo schema không khôi phục thông tin đã mất và có thể phá dữ liệu mới. Cần xem đúng thao tác, nguồn dữ liệu và phiên bản code hiện tại.

## 28. Tài liệu tham khảo

- Kubernetes — Updating a Deployment và rollout history: https://kubernetes.io/docs/concepts/workloads/controllers/deployment/
- Kubernetes — kubectl rollout: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/
- PostgreSQL — Backup and Restore: https://www.postgresql.org/docs/current/backup.html
- PostgreSQL — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- Martin Fowler — Evolutionary Database Design: https://martinfowler.com/articles/evodb.html
- Martin Fowler — Feature Toggles: https://martinfowler.com/articles/feature-toggles.html
- Microsoft — Compensating Transaction Pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction
- Microsoft — Saga distributed transactions pattern: https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/saga/saga
- AWS Builders' Library — Ensuring rollback safety during deployments: https://aws.amazon.com/builders-library/ensuring-rollback-safety-during-deployments/
- Flyway — Versioned migrations: https://documentation.red-gate.com/fd/versioned-migrations-273973333.html
- Pact — Contract testing in microservices: https://docs.pact.io/

**Ghi nhớ:** Quay lui mã và cấu hình là thao tác thay đổi **revision đang chạy**. Dữ liệu và side effect đã phát sinh có vòng đời riêng. Hệ microservices có khả năng phục hồi khi mỗi release chủ động giữ cửa sổ tương thích, biết điểm không thể quay ngược và có phương án roll-forward, restore, reconciliation hoặc compensation phù hợp với nghiệp vụ.
