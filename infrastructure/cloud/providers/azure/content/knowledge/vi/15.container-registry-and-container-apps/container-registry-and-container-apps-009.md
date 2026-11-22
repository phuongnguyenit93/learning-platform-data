# Revision, traffic splitting và rollback trên Container Apps

Một phiên bản mới của API có thể khởi động thành công nhưng gây lỗi khi phục vụ người dùng thật: thay đổi cách xác thực, gọi sai địa chỉ database, dùng thư viện chưa tương thích hoặc tăng độ trễ. Nếu đưa ngay toàn bộ lưu lượng sang phiên bản mới, sự cố có thể ảnh hưởng mọi khách hàng. **Azure Container Apps** cung cấp cơ chế **revision** và **traffic splitting** giúp vận hành nhiều phiên bản của cùng một container app, chuyển lưu lượng theo tỷ lệ và nhanh chóng đưa lưu lượng trở lại phiên bản đã được kiểm chứng khi cần.

Bài học thuộc chương **Container Registry và Container Apps** của module **CLOUD_PROVIDERS_AZURE**. Các quyết định về revision gắn trực tiếp với kiến trúc Azure rộng hơn: subscription và resource group để quản trị, Microsoft Entra ID và managed identity để lấy image/secret, mạng ảo và ingress để tiếp nhận traffic, Azure Monitor và Application Insights để đánh giá kết quả, cũng như chi phí của các replica đang chạy. Đây là bài hướng dẫn tự chứa về **phát hành phiên bản, chia lưu lượng và rollback an toàn**, không phải chỉ là cách đổi tag image.

Sau bài học, bạn có thể:

- Giải thích container app, environment, revision, replica, image tag/digest, activation và revision label.
- Phân biệt **single revision mode** và **multiple revision mode**.
- Nhận diện thay đổi nào tạo revision mới và thay đổi nào thuộc cấu hình cấp ứng dụng.
- Thiết kế đợt canary với trọng số 0% → 5% → 25% → 50% → 100%, có điều kiện dừng.
- Dùng Azure CLI kiểm tra revisions, thay image, kích hoạt revision, điều chỉnh traffic và rollback.
- Giải thích giới hạn của rollback đối với migration database, message schema, secret và dependency bên ngoài.
- Phân tích health, scale, route, logging, identity, bảo mật và chi phí khi vận hành nhiều revision.

## 1. Tư duy cốt lõi: không đồng nhất image, revision và replica

| Khái niệm | Diễn giải | Ví dụ |
|---|---|---|
| **Container image** | Artifact chứa application/runtime/dependencies được registry lưu; mỗi image manifest có digest xác định | `myregistry.azurecr.io/orders-api:1.2.0` |
| **Container app** | Tài nguyên Azure định nghĩa ứng dụng, ingress, cấu hình, template và danh sách revision | `ca-orders-api` |
| **Container Apps environment** | Ranh giới môi trường chạy, network/observability và các khả năng chung cho các app thuộc nó | `aca-env-prod` |
| **Revision** | Một snapshot bất biến của những thuộc tính **revision-scope**, được tạo khi thay đổi template phù hợp | `ca-orders-api--v120` |
| **Replica** | Instance chạy của **một revision**; số lượng có thể thay đổi theo scale rule | Revision v120 có 3 replica |
| **Active revision** | Revision được bật để có thể chạy/phục vụ theo routing và cấu hình | v119 và v120 cùng active |
| **Traffic weight** | Phần trăm lưu lượng ingress được phân tới revision đích | v119 90%, v120 10% |
| **Revision label** | Tên định tuyến trực tiếp tới một revision cụ thể khi có ingress hỗ trợ | `candidate` |

**Image ≠ revision:** cùng một image có thể được dùng cho nhiều revision khác nhau nếu các thiết lập thuộc template thay đổi. **Revision ≠ replica:** một revision có thể có nhiều replica và các replica có thể được tạo/hủy theo autoscale. **Active ≠ nhận lưu lượng:** trong multiple revision mode, một revision có thể active và có trọng số **0%**, tức chưa được chọn bởi tuyến traffic mặc định, dù vẫn có thể tiếp cận qua label URL hoặc đường trực tiếp khác nếu đã cấu hình.

### Ví dụ ba lần phát hành

~~~text
Container app: ca-orders-api

Revision ca-orders-api--v118
  Image: orders-api:1.1.8
  Active: false
  Default ingress weight: 0%

Revision ca-orders-api--v119
  Image: orders-api:1.1.9
  Active: true
  Default ingress weight: 90%
  Replicas: 3

Revision ca-orders-api--v120
  Image: orders-api:1.2.0
  Active: true
  Default ingress weight: 10%
  Replicas: 1-3 tùy chính sách scale
~~~

Tên revision, số replica và trọng số chỉ minh họa. Azure tạo tên revision theo quy tắc dịch vụ; có thể sử dụng suffix khi thao tác hỗ trợ. Không dùng tên phiên bản/tên revision như bằng chứng image đang chạy nếu chưa đối chiếu image reference và digest của deployment.

### Cấu trúc hệ thống

~~~mermaid
flowchart TB
    CLIENT[Client HTTPS] --> INGRESS[Container Apps ingress]
    INGRESS -->|90%| OLD[Revision v119 - stable]
    INGRESS -->|10%| NEW[Revision v120 - canary]
    OLD --> O1[Replica old-1]
    OLD --> O2[Replica old-2]
    OLD --> O3[Replica old-3]
    NEW --> N1[Replica new-1]
    NEW --> N2[Replica new-2]
    OLD --> DB[(Database dùng chung)]
    NEW --> DB
    OLD -. logs/metrics .-> MON[Azure Monitor / Log Analytics]
    NEW -. logs/metrics .-> MON
~~~

Trọng số áp dụng ở **lớp định tuyến revision**, không phải lời hứa cứ 100 HTTP requests thì chính xác 90 request sẽ vào bản cũ. Trong một khoảng thời gian hữu hạn, phân phối có sai số thống kê và còn chịu tác động của pattern kết nối, session/sticky behavior được hỗ trợ, retry và các đường truy cập trực tiếp khác. Vì vậy hãy đo actual request count theo revision và thời gian đủ đại diện.

## 2. Single revision mode và multiple revision mode

Azure Container Apps có **revision mode** quyết định cách các phiên bản mới được hoạt hóa và cùng tồn tại.

| Tiêu chí | Single revision mode | Multiple revision mode |
|---|---|---|
| Mục tiêu | Một phiên bản active cho lưu lượng tại một thời điểm theo mô hình dịch vụ | Có thể có nhiều revision active |
| Release | Nền tảng chuyển từ revision trước sang revision mới theo lifecycle tương ứng | Người vận hành quản lý revision active và traffic split |
| Canary 5%/95% | Không phải mô hình phù hợp | Có, với HTTP ingress và điều kiện hỗ trợ |
| Rollback | Phải xử lý đổi template/tạo lại phiên bản hoặc chuyển theo workflow được hỗ trợ | Có thể chuyển trọng số về revision cũ **nếu revision đó còn active/khả dụng** |
| Nhiều phiên bản cùng chạy | Không dùng để chủ động duy trì nhiều phiên bản active | Có thể giữ stable và candidate song song |
| Chi phí/capacity | Ít revision active hơn theo thiết kế | Có thể dùng nhiều replica từ nhiều revision cùng lúc |
| Phù hợp | Ứng dụng đơn giản, release theo một dòng phiên bản | Canary, A/B, gradual rollout, blue-green hoặc rollback nhanh bằng trọng số |

Trong **single revision mode**, nền tảng cố gắng điều phối chuyển đổi theo quy tắc lifecycle; không nên đồng nhất điều này với bảo đảm zero-downtime cho mọi ứng dụng. Nếu revision mới không khởi động, image pull lỗi, health không đạt hoặc app xử lý session state không đúng, kết quả còn phụ thuộc cấu hình và trạng thái hoạt động.

Trong **multiple revision mode**, cần chủ động quản trị **revision activation, traffic target, scale, label và chính sách dọn revision cũ**. Đừng giả định tạo image/revision mới tự động áp dụng đúng tỷ lệ canary: **luôn đọc lại cấu hình traffic ngay sau khi tạo revision** rồi đặt trọng số tường minh.

### Chọn mode theo chiến lược triển khai

~~~mermaid
flowchart TD
    START[Chuẩn bị release] --> Q1{Cần giữ old/new active đồng thời?}
    Q1 -->|Có| MULTI[Multiple revision mode]
    Q1 -->|Không| SINGLE[Single revision mode có thể phù hợp]
    MULTI --> Q2{Có HTTP ingress và cần chia traffic?}
    Q2 -->|Có| CANARY[Canary theo trọng số + telemetry]
    Q2 -->|Không| NOHTTP[Thiết kế rollout riêng cho queue/jobs/TCP]
    CANARY --> CHECK[Đo SLO và quyết định tiếp tục/rollback]
~~~

**Lưu ý:** traffic splitting theo trọng số mà bài này mô tả tập trung vào **HTTP ingress** của Container Apps. Không suy ra các kết nối TCP tùy ý, job chạy theo lịch hoặc message từ queue đều có cơ chế traffic splitting HTTP giống hệt. Với queue consumer, phải thiết kế số replica, consumer group, schema và khả năng xử lý song song theo mô hình messaging, không chỉ chỉnh tỷ lệ ingress.

## 3. Điều gì tạo revision mới?

Revision là snapshot bất biến của cấu hình **revision-scope** tại thời điểm tạo. Khi thay đổi thuộc tính thuộc template của container app, Azure tạo revision mới thay vì sửa nội dung của revision cũ.

### 3.1. Những thay đổi thường tạo revision

- **Container image** hoặc cấu hình container được đặt trong template.
- **Environment variables** thuộc template container (bao gồm các tham chiếu secret ở nơi được hỗ trợ).
- **CPU/memory resources** của container.
- **Scale rules**, min/max replicas và một số cấu hình scale thuộc template.
- **Init container, probe, command/args, volume mounts** hoặc các thuộc tính template khác khi được hỗ trợ.
- **Revision suffix** được chọn khi tạo revision mới theo API/CLI hỗ trợ.

Ví dụ bạn thay image từ `orders-api:1.1.9` sang `orders-api:1.2.0`. Container Apps tạo revision mới. Nếu đồng thời đổi `DATABASE_SCHEMA_MODE=v2` trong env var thuộc template, đó cũng là thay đổi revision-scope và sẽ được ghi vào revision mới.

### 3.2. Những thay đổi cấp container app

Một số cấu hình **application-scope** có thể được cập nhật mà **không tạo revision mới**, chẳng hạn cấu hình ingress/traffic allocation và tập secrets của ứng dụng, registry credentials hoặc revision mode theo khả năng dịch vụ. Cần phân biệt việc **đổi giá trị secret** với **đổi tham chiếu secret trong template**:

- Đổi secret trong collection cấp app thường không tự tạo revision mới.
- Replica đang chạy có thể không tự nhận giá trị secret mới ở thời điểm bạn thay đổi. Nếu secret được đưa vào environment variable lúc khởi động, thường cần restart/redeploy revision theo cách được hỗ trợ để dùng giá trị mới.
- Thay đổi **env var** (dù chỉ tên secret được tham chiếu) là thay đổi template và có thể tạo revision mới.

Không nên lưu mật khẩu production trực tiếp trong YAML/CLI history. Dùng managed identity, Key Vault và secret references theo thiết kế phù hợp; lập kế hoạch rotate secret cho cả stable lẫn canary.

### 3.3. Tại sao không chỉ đổi tag `latest`?

Một tag registry có thể bị chuyển sang digest mới mà tham chiếu image trong template **không đổi**. Việc push lại tag `latest` vào Azure Container Registry **không tự đảm bảo tạo revision mới**, cũng không bảo đảm mọi replica đang chạy đổi sang image mới tại cùng thời điểm.

**Cách vận hành an toàn:** build image với version/commit tag bất biến, ghi nhận **digest**, cập nhật template tới image được phê duyệt, rồi xác minh revision thực sự chạy artifact mong muốn. Khi cần rollback, quay lại revision/digest đã được kiểm thử, không dựa vào ý nghĩa mơ hồ của tag `latest`.

## 4. Lifecycle: active, inactive, replica và label

Một revision có trạng thái quản lý và trạng thái chạy riêng. Các khái niệm **active/inactive**, provisioning/running/failed và số replica không được coi là đồng nghĩa:

| Trạng thái/tình huống | Ý nghĩa | Hành động |
|---|---|---|
| Revision được tạo | Có snapshot cấu hình template | Xem tên, image, resource config |
| Active nhưng weight 0% | Có thể dùng để kiểm thử, không nhận lưu lượng từ tuyến chia trọng số mặc định | Kiểm tra health qua label URL nếu hỗ trợ |
| Active, weight > 0% | Là target cho HTTP ingress theo tỷ lệ | Theo dõi request/error metrics theo revision |
| Scale về 0 replica | Có thể là hành vi scale khi không có tải trong cấu hình hỗ trợ | Kiểm tra minReplicas, warm-up và cold start |
| Revision unhealthy/failed | Ứng dụng có thể không sẵn sàng | Đọc logs/probes; không đẩy thêm traffic |
| Inactive | Không phục vụ theo routing active thông thường | Có thể cần activate lại trước khi rollback |

**Inactive không phải là “đã xóa”.** Tuy nhiên, revision cũ có thể bị loại theo chính sách retention/giới hạn của dịch vụ, hoặc không còn pull được image nếu registry đã xóa digest. Vì thế **rollback nhanh chỉ khả thi khi revision cũ còn tồn tại, có image khả dụng, quyền registry và dependency tương thích**.

### Revision labels

Revision label cho phép truy cập **một revision được gắn nhãn** qua địa chỉ URL riêng theo khả năng ingress của Container Apps. Điều này hữu ích cho smoke test v120 trước khi cho khách hàng truy cập qua hostname chính.

Ví dụ logic:

~~~text
Hostname chính:  https://orders.example.com
  → stable 90%, candidate 10%

Label "candidate" (URL do Container Apps cung cấp)
  → gửi trực tiếp tới revision v120 để kiểm thử
~~~

Label **không phải** traffic weight. Gắn label cho một revision không mặc nhiên cho nó 10% lưu lượng từ hostname chính, và chuyển trọng số ở hostname chính không tự thay tên label.

**Bảo mật:** URL label không nên bị coi là một biện pháp cách ly hay bí mật. Nếu ingress có thể truy cập công khai, label endpoint cũng phải tuân theo xác thực, chính sách access và các biện pháp hạn chế phù hợp. Không bỏ qua authentication trong bản canary chỉ vì “đó là URL thử nghiệm”.

## 5. Traffic splitting: canary, blue-green và A/B

**Traffic splitting** là cách gán trọng số cho các revision được chọn ở ingress của container app. Với ingress HTTP và multiple revisions theo cấu hình hỗ trợ, tổng trọng số tuyến được định nghĩa phải là **100%**.

### 5.1. Progressive canary

| Giai đoạn | Stable | Candidate | Mục tiêu |
|---|---:|---:|---|
| Prepare | 100% | 0% | Tạo candidate, kiểm tra bằng label URL và smoke test |
| Canary nhỏ | 95% | 5% | Nhận tín hiệu từ ít người dùng, kiểm tra lỗi nghiêm trọng |
| Canary mở rộng | 75% | 25% | So sánh latency/error rate với stable |
| Phân phối rộng | 50% | 50% | Kiểm chứng tải và scale behavior ở mức lớn hơn |
| Promote | 0% | 100% | Chuyển production sang candidate đã chứng minh ổn định |
| Cleanup | 0% hoặc inactive | 100% | Giữ bản rollback đủ lâu trước khi dọn |

Đây là **một kế hoạch có kiểm soát**, không phải tự động thực thi khi tạo container app. Mỗi lần tăng tỷ lệ phải có thời gian quan sát, người phê duyệt và tiêu chí dừng.

### 5.2. Blue-green

Với blue-green, giữ `blue` (bản production) và `green` (bản ứng cử) chạy song song. Smoke test `green` qua endpoint riêng, rồi chuyển 100% traffic từ blue sang green nếu đạt. Có thể rollback bằng cách đưa trọng số trở lại blue nếu blue vẫn available và tương thích dữ liệu.

**Trade-off:** blue-green có thể tạo công suất chạy song song và tăng chi phí. Chuyển 100% tức thời cũng có thể gây lỗi nếu workload không đủ khả năng warm-up; nên kiểm tra số replica tối thiểu và khả năng truy cập dependency trước khi chuyển.

### 5.3. A/B testing

Traffic splitting theo revision có thể được dùng để đưa một phần lưu lượng tới hai phiên bản, nhưng **không phải công cụ A/B theo người dùng hoàn chỉnh**. Nếu cần cùng một user luôn vào biến thể A hoặc B, đo conversion theo cohort, kiểm soát consent hoặc loại trừ một nhóm người dùng cụ thể, cần thêm cơ chế định danh/feature flag ở application/gateway. Trọng số 50/50 của ingress **không tự đảm bảo** cùng một người luôn được phục vụ bởi cùng một revision.

### 5.4. Dùng feature flags thay revision trong trường hợp nào?

- **Revision** phù hợp để phát hành bộ image/config mới và chuyển traffic ở mức workload.
- **Feature flag** phù hợp khi một bản phát hành cần bật/tắt một chức năng cho nhóm user, không thay image và không phải thao tác infrastructure.
- Kết hợp được cả hai: release v120 với feature mặc định off, mở canary traffic, rồi tăng tỷ lệ feature khi đã có bằng chứng.

Không dùng feature flag để thay thế kiểm thử compatibility giữa các revision hoặc migration database; cả code cũ và mới vẫn phải chịu được schema/data đang dùng chung.

## 6. Tiêu chí an toàn trước khi tăng traffic

Một kế hoạch phát hành phải định nghĩa **ai quyết định, dựa trên bằng chứng nào**, không chỉ các con số 5/25/50/100.

### Những tín hiệu tối thiểu

| Nhóm tín hiệu | Chỉ số và câu hỏi | Phương pháp |
|---|---|---|
| Availability | Candidate có trả 2xx cho health/readiness không? | HTTP probe và synthetic checks theo revision |
| Errors | 5xx, timeout, exception của candidate có tăng không? | Logs/metrics phân tách revision |
| Latency | p95/p99 của candidate có vượt stable/SLO? | Application Insights/distributed tracing |
| Resources | CPU/memory, replicas, restarts, OOM | Container Apps metrics/logs |
| Dependencies | SQL/Storage/Key Vault/API đối tác có lỗi 403/429/5xx? | Dependency tracing và test có kiểm soát |
| Business | Thanh toán, tạo đơn hàng và các tác vụ quan trọng có đúng? | Synthetic transactions/canary business metrics |
| Security | Không có thay đổi quyền quá rộng, secret leak hoặc lỗi auth | Security scan, audit, RBAC kiểm tra |

Ví dụ **ngưỡng minh họa**, không phải chuẩn mặc định của Azure:

- Canary phải phục vụ tối thiểu một lượng request có ý nghĩa thống kê theo tải thực tế; khi lưu lượng thấp, nên có synthetic test thay vì kết luận từ 3 request thành công.
- Không tăng traffic nếu tỷ lệ 5xx của canary vượt ngưỡng SLO hoặc cao hơn stable theo mức đã định.
- Không tăng traffic nếu p95 latency xấu đi đáng kể, có lỗi dữ liệu hoặc bất kỳ lỗi nghiệp vụ mức nghiêm trọng cao.
- Tăng traffic chỉ khi người vận hành đã kiểm tra logs, latency, scaling và dependency trong khoảng thời gian được phê duyệt.

**Số lượng request mới là mẫu số**, không phải số replica. Một revision có 2 replica không đồng nghĩa nó nhận hai lần traffic của revision chỉ có 1 replica. Trọng số phân phối theo ingress, còn autoscale điều khiển năng lực xử lý của từng revision.

## 7. Chuẩn bị môi trường Azure cho revision rollout

Quy trình dưới đây minh họa **Azure CLI trong Bash**. Đây là các lệnh mẫu để người học thực hiện trên subscription lab được phép; **không có tài nguyên Azure thực nào được tạo khi viết bài học**. Các thao tác cập nhật revision/traffic thực tế làm thay đổi ứng dụng, vì vậy không chạy trên production nếu chưa có change approval.

### 7.1. Điều kiện trước khi bắt đầu

- Một Azure subscription và resource group được phép dùng cho lab.
- Container Apps environment và một **Container App có HTTP ingress** đã được tạo, có khả năng pull image từ registry.
- Danh tính người thao tác có quyền đọc/sửa container app, tạo revision, cập nhật ingress, theo phạm vi Azure RBAC được cấp.
- Application đã có một revision stable hoạt động, có test endpoint để đối chiếu phiên bản.
- Một image candidate được CI build, quét và push vào ACR hoặc registry đáng tin; tag/digest đã được ghi nhận.
- Container nghe đúng target port, trả health/readiness theo cách Container Apps hỗ trợ và có truy cập mạng/secret phù hợp.
- Có monitoring request count, error rate, p95/p99 và dependency failures theo revision.
- Có phương án rollback và kiểm soát database schema/message contract.

Ví dụ đặt các biến:

~~~bash
az login

SUBSCRIPTION_ID="<subscription-id-lab>"
RG="rg-aca-release-lab"
APP="ca-orders-demo"
REGISTRY="<registry-name>.azurecr.io"
REPOSITORY="orders-api"
STABLE_IMAGE="$REGISTRY/$REPOSITORY:1.1.9"
CANDIDATE_IMAGE="$REGISTRY/$REPOSITORY:1.2.0"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name}" -o table
~~~

Các giá trị `<...>` chỉ là placeholder. Bạn phải thay bằng subscription và registry thật. Không giả định app có tên `ca-orders-demo` đã tồn tại nếu chưa provision. Ở lab, nên tạo tài nguyên qua IaC/Portal hoặc quy trình chuẩn của nhóm; một cách tạo Container Apps environment và container app có trong CLI, nhưng phải lựa chọn image, ingress, CPU/memory, scale và registry auth theo môi trường của bạn trước khi áp dụng.

**Quan trọng về ACR private:** image pull là một bước độc lập với traffic splitting. Container app cần registry credential hoặc **managed identity được cấp quyền pull** theo ACR permission mode và đường mạng tới registry (kể cả private endpoint/DNS khi được áp dụng). Khi rollback revision cũ, image của revision đó cũng phải còn pull được khi tạo replica mới.

### 7.2. Kiểm tra tài nguyên hiện tại

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "{name:name, mode:properties.configuration.activeRevisionsMode, ingress:properties.configuration.ingress, latest:properties.latestRevisionName}" \
  --output json

az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --query "[].{name:name, active:properties.active, created:properties.createdTime, replicas:properties.replicas}" \
  --output table
~~~

Kết quả cần được xem **trước thay đổi**: revision nào đang được chọn bởi ingress, revision nào đã inactive, image và các biến cấu hình hiện tại là gì. Đọc thêm:

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.template" \
  --output json
~~~

Một danh sách `active=true` không đủ để kết luận revision đó đang nhận 10% traffic. Phải đọc bảng trọng số ingress thực tế. Khi hệ thống có nhiều revision dùng cùng tag image, xác minh digest/manifest do pipeline ghi nhận thay vì suy từ tên.

## 8. Chuyển sang multiple revisions và tạo candidate

### 8.1. Thiết lập revision mode

Với app lab đang chạy và đáp ứng điều kiện:

~~~bash
az containerapp revision set-mode \
  --name "$APP" \
  --resource-group "$RG" \
  --mode multiple

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.activeRevisionsMode" \
  --output tsv
~~~

Kỳ vọng giá trị mode tương ứng với `Multiple`. Hãy kiểm tra `az containerapp revision set-mode --help` theo phiên bản Azure CLI/`containerapp` extension. **Đổi mode là thay đổi vận hành**, cần xem lại lịch release và traffic; không đổi trên production rồi mặc định mọi revision cũ tự được khôi phục hoặc có trọng số như mong muốn.

### 8.2. Ghi nhận stable revision

Từ danh sách revision và traffic, chọn **đúng** revision đang nhận production traffic, ví dụ:

~~~bash
# Thay bằng revision có thật đã xác minh qua revision list.
STABLE_REV="ca-orders-demo--v119"

az containerapp revision show \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$STABLE_REV" \
  --output json
~~~

Đừng tự đoán stable revision bằng tên có timestamp lớn nhất. Một app có thể vừa tạo candidate thử nghiệm hoặc một revision mới đã lỗi; `latest` không đồng nghĩa `stable`. Trước release phải lưu stable revision, image/digest và bản sao cấu hình cần thiết để rollback.

### 8.3. Tạo revision bằng image mới

**Phòng ngừa traffic tự chuyển ngoài ý muốn:** trước khi tạo candidate, xác nhận routing production đang **ghim vào stable revision cụ thể**, không phụ thuộc biểu thức `latestRevision` có thể trỏ sang revision vừa được tạo. Trong lab, sau khi đã xác minh stable revision, có thể đặt explicit weight:

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100"

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Nếu không bảo đảm được trạng thái traffic trước/sau thao tác tạo revision, **không triển khai candidate trực tiếp vào production**: thử lại trên môi trường tương đương hoặc dùng quy trình IaC/pipeline quản lý traffic nguyên tử theo khả năng hỗ trợ. Một thay đổi image thuộc **revision-scope**:

~~~bash
az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --image "$CANDIDATE_IMAGE" \
  --revision-suffix "v120"
~~~

Tên revision suffix phải hợp lệ và duy nhất theo quy tắc của Container Apps. Suffix `v120` chỉ là ví dụ; nếu đã dùng rồi, chọn suffix khác. Lệnh update có thể tạo revision mới; **ngay sau đó phải kiểm tra trạng thái/traffic**, không cho rằng candidate đã có 0% hay 10% mặc định theo ý định người vận hành.

~~~bash
az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --output table

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Trong tài liệu này, giả sử candidate được tạo thành `ca-orders-demo--v120`. Bạn phải dùng **tên thật trả về từ Azure** và kiểm tra image candidate chính xác:

~~~bash
CANDIDATE_REV="ca-orders-demo--v120"

az containerapp revision show \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV" \
  --output json
~~~

Nếu candidate không healthy, image pull lỗi hoặc readiness thất bại, **không đẩy traffic**. Sửa nguyên nhân và tạo revision mới khi cần; đừng xóa stable revision trước khi đã xác minh phiên bản thay thế.

### 8.4. Kích hoạt candidate nếu đang inactive

Nếu candidate tồn tại nhưng inactive và muốn cho nó tham gia rollout:

~~~bash
az containerapp revision activate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV"
~~~

Activate giúp revision tham gia tập active, nhưng **chưa đủ để chứng minh app sẵn sàng**. Phải theo dõi provisioning/running status, replica startup, liveness/readiness và khả năng truy cập dependency trước khi điều phối request của khách hàng tới nó.

## 9. Thao tác traffic splitting bằng Azure CLI

Sau khi **hai revision đều active**, đặt trọng số một cách tường minh. Các ví dụ dùng lệnh `az containerapp ingress traffic set` cho HTTP ingress; tên/tham số có thể thay đổi theo phiên bản CLI/extension nên cần kiểm tra `--help` trước khi tự động hóa.

### 9.1. Chuẩn bị: 100% stable, 0% candidate

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100" "$CANDIDATE_REV=0"
~~~

Quan sát lại kết quả:

~~~bash
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Lưu ý: khi đặt cấu hình từ một trạng thái đã có nhiều rule, hãy xác nhận tập rule cuối **không còn một trọng số ngoài dự kiến** (ví dụ `latestRevision=true` từ một workflow khác). Tổng cấu hình phải hợp lệ và phản ánh đúng chủ đích. Trong production, không dựa vào exit code của một lệnh duy nhất; đọc lại traffic và kiểm tra request thật.

### 9.2. Mở canary 5%

~~~bash
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=95" "$CANDIDATE_REV=5"
~~~

**Ý nghĩa:** ingress phân phối lưu lượng tới stable/candidate theo tỷ trọng quy định. Nó **không** giới hạn candidate chỉ có 5% CPU, 5% replicas hoặc 5% số database connections. Mỗi revision autoscale theo template và các trigger được cấu hình cho nó.

Sau khi áp dụng, theo dõi request metrics **phân tách theo revision**. Không dùng một metric tổng 5xx của cả app để che tỷ lệ lỗi cao trên canary có traffic thấp.

### 9.3. Mở rộng 25%, 50% và promote

~~~bash
# Chỉ tiếp tục khi các SLO của giai đoạn trước đạt.
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=75" "$CANDIDATE_REV=25"

# Sau một khoảng quan sát phù hợp:
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=50" "$CANDIDATE_REV=50"

# Khi đã được phê duyệt:
az containerapp ingress traffic set \
  --name "$APP" -g "$RG" \
  --revision-weight "$STABLE_REV=0" "$CANDIDATE_REV=100"
~~~

Các dòng trên **không phải script tự động duy nhất để chạy liền một mạch**. Phải có kiểm thử, quan sát và phê duyệt giữa từng giai đoạn. Nếu thực hiện cả ba liên tiếp không có delay, bạn không còn rollout theo từng bước về mặt rủi ro.

### 9.4. Dùng label URL để kiểm thử candidate trước canary

Khi HTTP ingress và revision label được hỗ trợ, gắn label:

~~~bash
az containerapp revision label add \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV" \
  --label "candidate"
~~~

Sau đó lấy URL label từ thông tin ingress/label trả về bởi Azure Portal hoặc CLI tương ứng, rồi gọi `/health` và synthetic requests trên đúng label endpoint.

**Không tự bịa host từ tên app**: hostname thực tế, suffix label và cấu hình domain có thể phụ thuộc môi trường. Nhãn là một **đường kiểm thử trực tiếp** nhưng không tự làm candidate nhận 5% traffic chính. Các request dùng label URL cần được loại trừ/phân biệt khi phân tích tỷ lệ traffic thật theo cohort khách hàng.

### 9.5. Kiểm tra nhanh trạng thái sau mỗi bước

~~~bash
az containerapp revision list \
  -n "$APP" -g "$RG" \
  --query "[].{name:name,active:properties.active,replicas:properties.replicas}" \
  -o table

az containerapp show \
  -n "$APP" -g "$RG" \
  --query "properties.configuration.ingress.traffic" \
  -o json
~~~

Lưu lại cấu hình trước/sau vào change ticket hoặc pipeline logs **không chứa secret**. Nếu lệnh CLI có cú pháp/khả năng khác trong phiên bản công cụ thực tế, cập nhật runbook theo `az containerapp ingress traffic set --help` và thử ở lab trước.

## 10. Rollback: trả lưu lượng về bản ổn định

**Rollback revision bằng traffic weight** là cách nhanh đưa các **request mới đi qua ingress chính** trở lại revision stable trong multiple mode. Khả năng này đặc biệt hữu ích khi code mới lỗi nhưng stable vẫn active, còn đủ capacity và tương thích dependency/data.

### 10.1. Rollback khẩn cấp

Giả sử canary v120 đang nhận 25% và phát sinh 5xx cao:

~~~bash
# Hành động có tác động production: chỉ thực hiện theo runbook được phê duyệt.
az containerapp ingress traffic set \
  --name "$APP" \
  --resource-group "$RG" \
  --revision-weight "$STABLE_REV=100" "$CANDIDATE_REV=0"

# Đọc lại phân bổ hiệu lực.
az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json
~~~

Sau đó phải **kiểm chứng thực tế**:

1. Stable revision còn active, healthy và có đủ replicas để đón tải 100%.
2. HTTP 5xx, timeout và p95/p99 latency giảm theo ngưỡng mong đợi.
3. Giao dịch quan trọng như tạo đơn hàng, đọc dữ liệu và thanh toán hoạt động.
4. Không có job/queue consumer trên candidate còn ghi dữ liệu gây lỗi.
5. Không có dependency/configuration mới ở cấp app khiến stable cũng bị hỏng.

**Rollback ingress traffic không giống “hủy mọi request đang chạy”.** Kết nối hiện hữu, request đang xử lý và session/sticky behavior có thể tiếp tục ảnh hưởng trong thời gian chuyển tiếp. Không giả định thay trọng số là cắt ngay tất cả side effects của phiên bản mới.

### 10.2. Nếu stable revision đang inactive

Trước khi đặt 100% về stable, xác nhận revision còn tồn tại và image có thể được pull. Khi cần và được hỗ trợ:

~~~bash
az containerapp revision activate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$STABLE_REV"
~~~

Đợi revision hoạt động đúng rồi mới đưa lưu lượng trở lại, hoặc có biện pháp cutover an toàn theo mức nghiêm trọng. Nếu revision cũ đã bị dọn khỏi hệ thống, cần **triển khai lại image/digest cũ thành revision mới**, không thể gọi activate với một revision không còn tồn tại.

### 10.3. Có nên deactivate revision lỗi ngay?

Sau khi đã chuyển trọng số về 0%, có thể xem xét:

~~~bash
az containerapp revision deactivate \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$CANDIDATE_REV"
~~~

**Không deactivate vội** nếu cần giữ candidate để lấy log, tái hiện lỗi hoặc kiểm tra điều kiện rollback; cũng không để revision lỗi active vô thời hạn nếu có đường truy cập qua label hoặc đang xử lý background work. Cần xem quy trình điều tra, quyền truy cập trực tiếp, năng lực trả phí và rủi ro bảo mật trước khi quyết định.

Deactivation không nhất thiết tương đương xóa image trong registry hay xóa bản ghi lịch sử. Nếu doanh nghiệp có yêu cầu bằng chứng, giữ manifest, logs, deployment event và change ticket ở nơi lưu trữ được phê duyệt.

### 10.4. Rollback bằng image cũ là lựa chọn thứ hai

Nếu không thể dùng revision stable cũ (đã bị xóa hoặc thay đổi không còn tương thích), bạn có thể dùng pipeline tạo một **revision mới** từ image digest đã kiểm chứng:

~~~bash
# Ví dụ dùng tag bất biến được pipeline quản lý.
ROLLBACK_IMAGE="$REGISTRY/$REPOSITORY:1.1.9"

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --image "$ROLLBACK_IMAGE"
~~~

Đây là **roll forward bằng artifact cũ**, không phải “khôi phục snapshot toàn bộ ứng dụng”. App-scope configuration, secrets, network và database có thể đã thay đổi từ lần phát hành trước. Phải kiểm tra tương thích và chính sách ingress sau khi tạo revision mới.

### 10.5. Quy trình quyết định rollback

~~~mermaid
flowchart TD
    ALERT[Canary lỗi vượt ngưỡng] --> STOP[Dừng tăng traffic / giữ pipeline]
    STOP --> Q1{Stable còn active và healthy?}
    Q1 -->|Có| ROUTE[Trả 100% traffic về stable]
    Q1 -->|Không| Q2{Stable revision tồn tại?}
    Q2 -->|Có| ACT[Activate + kiểm tra health]
    Q2 -->|Không| REP[Deploy lại artifact stable được kiểm chứng]
    ACT --> ROUTE
    REP --> ROUTE
    ROUTE --> CHECK[Đánh giá API, DB, queue và SLO]
    CHECK --> INCIDENT[Ghi incident, root cause, hành động phòng ngừa]
~~~

Sơ đồ là logic nghiệp vụ: nếu stable không đủ capacity hoặc schema dữ liệu đã phá vỡ tương thích, chuyển traffic đơn thuần có thể làm sự cố nặng hơn. Trong trường hợp đó cần dùng phương án DR/restore hoặc sửa hệ thống phụ thuộc trước khi nhận tải.

## 11. Rollback code không đồng nghĩa rollback dữ liệu

Điểm nguy hiểm nhất của canary là hai phiên bản **cùng sử dụng hệ thống dữ liệu chung** trong thời gian dài. Nếu phiên bản mới thay đổi dữ liệu theo cách cũ không hiểu được, chuyển ingress về phiên bản cũ có thể khiến lỗi tiếp tục.

### 11.1. Ví dụ migration không tương thích

Ứng dụng đơn hàng phiên bản v119 dùng schema:

~~~sql
-- Minh họa cấu trúc cũ
CREATE TABLE Orders (
    Id BIGINT PRIMARY KEY,
    CustomerId BIGINT NOT NULL,
    TotalAmount DECIMAL(18,2) NOT NULL
);
~~~

Phiên bản v120 muốn thay `TotalAmount` thành `TotalAmountMinorUnits`. Nếu migration xóa cột cũ ngay khi v120 khởi động, v119 còn nhận 90% traffic sẽ truy cập cột không còn tồn tại và thất bại. Rollback traffic về v119 cũng **không khôi phục cột đã xóa**.

**Chiến lược expand–migrate–contract:**

1. **Expand:** thêm cột/cấu trúc mới mà không phá hợp đồng cũ.
2. **Deploy v120 tương thích:** code mới có thể đọc/ghi một hoặc cả hai định dạng trong giai đoạn chuyển tiếp.
3. **Backfill:** chuyển dữ liệu cũ sang dạng mới bằng job có checkpoint và khả năng resume.
4. **Observe:** bảo đảm v119 và v120 cùng xử lý đúng khi chia traffic.
5. **Promote:** đưa 100% traffic sang v120, theo dõi đủ thời gian.
6. **Contract:** chỉ xóa cấu trúc cũ trong một thay đổi riêng sau khi rollback window đã kết thúc và kế hoạch restore được phê duyệt.

Không nên chạy migration phá hủy schema trong **startup command** của mỗi replica: nhiều replica/revision có thể cùng khởi động và chạy migration đồng thời. Tách migration thành một tác vụ được điều phối một lần, có lock/checkpoint và quyền riêng khi cần.

### 11.2. Những dependency khác cần tương thích

| Thành phần | Rủi ro khi chạy nhiều revision | Cách thiết kế |
|---|---|---|
| Azure SQL / PostgreSQL / Cosmos DB | Schema, index hoặc enum mới khiến code cũ lỗi | Migration tương thích ngược, test cả v119/v120 |
| Azure Service Bus / Event Hubs | Message payload thay đổi; consumer cũ không parse được | Versioned schema, tolerant readers, schema registry khi phù hợp |
| Azure Blob Storage | Tên object/metadata đổi hoặc file bị ghi lại | Định dạng có phiên bản, không phá key/metadata cũ ngay |
| Cache/Redis | Key namespace hoặc serialization thay đổi | Versioned keys, TTL và chiến lược cache invalidation |
| Key Vault | Secret đổi giá trị và các revision đọc khác thời điểm | Secret rotation có giai đoạn overlap, restart và xác minh |
| External API | Client version mới gây rate limit hoặc thay đổi idempotency | API contract tests, giới hạn đồng thời, retry có backoff |
| Feature flags | Một revision kỳ vọng flag khác revision còn lại | Định nghĩa scope/cohort, audit và rollback flag riêng |

Rollback dữ liệu có thể đòi backup/restore độc lập với rollback ứng dụng. Restore database toàn bộ còn có thể làm mất giao dịch hợp lệ sau thời điểm snapshot; phải phối hợp RPO/RTO và quyền phê duyệt. Không ra lệnh restore như phản xạ khi 5xx tăng nếu nguyên nhân chỉ là một bad deploy có thể giải quyết bằng traffic rollback.

### 11.3. Request side effects và tính idempotent

Ngay cả khi v120 chỉ nhận 5% HTTP requests, nó có thể gửi email, tạo thanh toán hoặc publish message. Nếu request thất bại ở client nhưng side effect đã xảy ra, retry qua v119 có thể xử lý lại. Cần:

- **Idempotency key** cho những thao tác như thanh toán/đặt hàng.
- Trạng thái giao dịch trong database hoặc event log giúp phân biệt đã xử lý/chưa xử lý.
- Outbox hoặc cơ chế đảm bảo gửi sự kiện phù hợp, tránh lỗi “DB commit nhưng event không gửi”.
- Hợp đồng message/schema mà cả hai revision cùng hiểu trong thời gian coexist.
- Kiểm soát cron/background processing: hai revision chạy song song có thể **xử lý cùng job** nếu ứng dụng không có phối hợp.

Traffic splitting điều chỉnh **ingress request routing**, không thay thế idempotency hoặc exactly-once business processing.

## 12. Scaling và health trong giai đoạn canary

Một revision vừa được tạo có thể bắt đầu với số replica thấp hoặc scale về zero theo rule. Nếu đưa ngay 50% traffic đến một revision chưa có đủ năng lực hoặc phải cold start, latency có thể tăng dù code đúng.

### 12.1. Mỗi revision có scale template

Các thuộc tính như `minReplicas`, `maxReplicas` và scale rules thuộc nhóm revision-scope theo mô hình Container Apps. Một chỉnh sửa scale template có thể tạo **revision mới**; vì vậy nên chọn chính sách scale cho candidate **trước** khi tăng traffic rồi xác minh tên revision mới.

Ví dụ:

| Revision | Ingress weight | minReplicas | maxReplicas | Ý nghĩa |
|---|---:|---:|---:|---|
| Stable v119 | 95% | 2 | 8 | Đủ năng lực cho phần lớn traffic |
| Candidate v120 | 5% | 1 | 4 | Giữ ít nhất một replica để giảm cold start khi kiểm thử |

Chỉ số trên là ví dụ, không phải quota mặc định. Trong môi trường có scale-to-zero, `minReplicas=0` có thể giảm chi phí nhưng tăng thời gian phục vụ request đầu; đánh giá với SLA và lượng traffic quan sát thật.

### 12.2. Startup, readiness, liveness

**Startup probe** giúp xử lý thời gian khởi tạo, **liveness** xác định có nên restart instance bị kẹt và **readiness** kiểm tra instance đủ điều kiện nhận lưu lượng. Cấu hình, kiểu probe và hỗ trợ phụ thuộc giao thức/ingress/runtime Container Apps.

Ví dụ ứng dụng có:

~~~text
/health/live  → 200 nếu tiến trình còn xử lý được
/health/ready → 200 nếu HTTP server và dependency thiết yếu sẵn sàng
/health/deep  → báo cáo chi tiết hơn cho monitoring có bảo vệ
~~~

Probe cần nhẹ, có timeout hợp lý, không cần token người dùng nếu dịch vụ nền tảng không gửi token và không tiết lộ secret. Đừng để readiness bắt buộc tất cả dịch vụ phụ — một lỗi chung có thể khiến mọi revision bị loại khỏi phục vụ, làm sự cố lớn hơn.

### 12.3. Phân biệt lỗi startup và lỗi canary

| Triệu chứng | Nguyên nhân hay gặp | Quyết định |
|---|---|---|
| Image pull failed | Sai tag/digest, thiếu quyền registry, DNS/private endpoint | Không cấp traffic; sửa registry auth/network |
| Replica pending hoặc crash loop | OOM, sai entrypoint/port, thiếu env/secret | Xem system/console logs, sửa image/template |
| Candidate healthy nhưng 5xx tăng | Lỗi business logic, dependency auth, schema | Rollback traffic, điều tra app/dependency |
| p95 cao trong vài phút đầu | Cold start, cache warm-up hoặc scale chưa theo tải | Giữ 0/5% cho đến khi warm-up và có số liệu |
| 429/503 khi tăng từ 5% lên 50% | Giới hạn scale hoặc API bên ngoài quá tải | Giảm traffic; kiểm tra throughput, quota, retries |
| Stable cũng lỗi sau khi v120 chạy | Migration/schema/secret/cấu hình chung | Điều tra shared dependency; rollback traffic có thể không đủ |

Để canary có ý nghĩa, traffic test phải sử dụng **phiên bản tương đương production** về cấu hình network/identity và dữ liệu phù hợp. Một canary có image đúng nhưng bị cấu hình môi trường thử nghiệm khác biệt có thể cho kết luận sai.

### 12.4. Scale không bảo đảm chia request chính xác

Traffic weight phân phối ở revision routing; KEDA/HTTP scaler quyết định replicas của từng revision theo metrics và quy tắc được cấu hình. Kết quả quan sát bị ảnh hưởng bởi:

- Scale-to-zero/cold start.
- Số replica tối thiểu, tối đa, thời gian scale.
- Keep-alive, session affinity và phân bố client nếu được bật/hỗ trợ.
- Thời gian xử lý request, retries và connections dài.
- Request tới label URL không đi qua trọng số hostname chính.
- Các tác vụ background tiêu thụ CPU/memory độc lập với HTTP traffic.

Do đó, không chỉ xem `trafficWeight=5` rồi kết luận candidate không thể gây quá tải database. Một số request candidate có thể nặng hơn hàng trăm lần hoặc mở nhiều kết nối dữ liệu hơn request stable.

## 13. Giám sát từng revision thay vì chỉ nhìn container app tổng

Muốn quyết định promote/rollback, phải so sánh **stable** với **candidate** trong cùng khoảng thời gian và loại request tương đương.

### 13.1. Cần gắn revision identity vào telemetry

Mọi request log nên có:

- UTC timestamp, request/correlation ID, route và response status.
- Thời gian xử lý, dependency calls, timeout/retry count.
- **Revision name hoặc deployment version** lấy từ metadata/environment được platform cung cấp hoặc pipeline injection theo cách hỗ trợ.
- Trace ID để nối ingress → API → database/message.
- Phiên bản schema và feature flags liên quan khi cần điều tra.

Không ghi access token, authorization header, connection string hoặc dữ liệu cá nhân nhạy cảm để chỉ phục vụ debug. Có thể gắn container app/revision resource ID vào resource logs hoặc custom dimensions theo phương án telemetry được hỗ trợ.

### 13.2. Azure Monitor và Log Analytics

Các nguồn thường được dùng:

| Nguồn | Phản ánh | Hạn chế |
|---|---|---|
| Container Apps system logs | Startup, replica, provisioning, platform events | Không thay thế business telemetry |
| Container console logs | Stdout/stderr của ứng dụng trong revision/replica | Cần cấu trúc và loại bỏ secret |
| Azure Monitor metrics | CPU, memory, replicas, requests/network theo metric và dimensions được hỗ trợ | Không phải mọi metric đều có dimension revision trong mọi bản triển khai |
| Application Insights/OpenTelemetry | Request, exception, dependency, distributed traces | Cần instrumentation và sampling phù hợp |
| Azure Activity Log | Ai thay đổi app config, ingress, RBAC trong control plane | Không cho thấy mọi request HTTP |
| Azure Container Registry diagnostics | Image push/pull và tình trạng registry theo logging được bật | Không giải thích lỗi ứng dụng nếu image pull đã thành công |

Không mặc định có Log Analytics workspace thì log application đã tới đúng bảng. Xác định nơi lưu telemetry, bật cấu hình phù hợp và kiểm tra bằng request test trước release. Khi viết KQL, chọn **bảng và tên trường từ workspace đang dùng**, không sao chép schema giữa custom App Insights và container console logs rồi giả định chúng giống nhau.

### 13.3. Ví dụ phân tích bằng KQL với custom request telemetry

Giả sử ứng dụng gửi request telemetry vào Application Insights và ghi thuộc tính `revision` trong custom dimensions. Tên bảng/trường sau chỉ là **mô hình phân tích minh họa** cho môi trường sử dụng bảng `AppRequests`:

~~~kusto
AppRequests
| where TimeGenerated > ago(30m)
| extend rev = tostring(Properties["revision"])
| where rev in ("ca-orders-demo--v119", "ca-orders-demo--v120")
| summarize
    requests = count(),
    failed = countif(Success == false),
    p95Ms = percentile(DurationMs, 95)
  by rev, bin(TimeGenerated, 5m)
| extend errorRate = iff(requests == 0, 0.0,
                         todouble(failed) / todouble(requests))
| order by TimeGenerated asc, rev asc
~~~

**Điều kiện:** bảng `AppRequests`, cột `Properties`, `DurationMs` và `Success` phải thực sự tồn tại theo SDK/exporter đang dùng; một số workspace có schema khác như `requests`/`customDimensions`. Trước khi đưa query vào alert, kiểm tra schema và bảo đảm property `revision` được ghi đúng. Ở mẫu này, `errorRate` là tỷ lệ request có `Success=false`, không nhất thiết bằng 5xx nếu logic telemetry khác.

### 13.4. Những alert nên cấu hình

1. 5xx/error rate của candidate cao hơn ngưỡng tuyệt đối hoặc cao hơn stable theo ngưỡng chấp nhận.
2. p95/p99 latency candidate tăng trên những route chính.
3. Replica restart/OOM hoặc revision provisioning failure.
4. 403/5xx tới Key Vault, database, Storage hoặc API đối tác tăng.
5. Request volume nhận được của candidate khác xa trọng số kỳ vọng sau khoảng quan sát hợp lý.
6. Thay đổi app-level secret/traffic hoặc quyền registry ngoài pipeline phê duyệt.
7. Một revision có traffic >0 nhưng không có healthy replicas.

Chọn alert có **owner**, runbook, thời gian quan sát, điều kiện nhiễu và cơ chế giữ/cắt rollout. Không chỉ gửi thông báo vào kênh chat rồi tự tăng trọng số theo đồng hồ.

## 14. Azure CLI để quan sát logs, status và phiên bản thật

Đối với app đã cấu hình:

~~~bash
# Danh sách revisions và trạng thái hoạt hóa
az containerapp revision list \
  -n "$APP" -g "$RG" -o table

# Xem chi tiết stable/candidate
az containerapp revision show \
  -n "$APP" -g "$RG" \
  --revision "$CANDIDATE_REV" \
  -o json

# Stream console logs nếu CLI/runtime hỗ trợ trong môi trường hiện tại.
az containerapp logs show \
  -n "$APP" -g "$RG" \
  --revision "$CANDIDATE_REV" \
  --type console \
  --tail 100

# System logs giúp tra cứu lỗi provisioning/startup.
az containerapp logs show \
  -n "$APP" -g "$RG" \
  --type system \
  --tail 100
~~~

Lưu ý rằng lệnh logs chỉ trả bản ghi trong giới hạn endpoint/retention đang sử dụng. Với sự cố production, sử dụng hệ thống thu thập log lâu dài phù hợp (Log Analytics, Application Insights hoặc công cụ khác được tích hợp), không dựa duy nhất vào `--tail 100`.

### Ghi nhận revision và image khi phát hành

Một bản ghi deployment có thể chứa:

~~~yaml
application: ca-orders-demo
environment: production
stableRevision: ca-orders-demo--v119
candidateRevision: ca-orders-demo--v120
stableImage: myregistry.azurecr.io/orders-api:1.1.9
candidateImage: myregistry.azurecr.io/orders-api:1.2.0
candidateDigest: sha256:<digest-from-registry>
trafficBefore: "100/0"
trafficAfter: "95/5"
decision: "hold pending observation"
changeTicket: "CHG-EXAMPLE"
~~~

Đây là **mẫu dữ liệu**, không phải file cần tạo thêm. Giữ trong hệ thống change/CI/CD của tổ chức. `candidateDigest` phải là digest **thực tế** lấy từ registry/build metadata; không dùng placeholder làm nguồn triển khai.

## 15. Bảo mật, identity và quyền khi có nhiều revision

Trong một container app, nhiều revision có thể cùng chạy nhưng điều đó **không mặc nhiên tạo một ranh giới bảo mật độc lập** giữa stable và canary. Chúng có thể dùng chung một số cấu hình cấp app, managed identity, secret collection, mạng và backend services.

### 15.1. Rủi ro phổ biến

- Candidate có code chưa được kiểm thử nhưng được cấp **cùng quyền database production** như stable.
- Pipeline build có quyền push/delete repository quá rộng; một image tag có thể bị ghi đè.
- Secret cấp app được rotate và ảnh hưởng cả revision stable lẫn candidate khi restart.
- Label endpoint công khai bị lộ và cho phép gọi code chưa kiểm chứng trực tiếp.
- Tạo ingress public mà không đặt auth/WAF/rate limiting cần thiết.
- Resource group có quyền Contributor rộng cho nhiều nhóm, dễ thay traffic ngoài quy trình.
- Log candidate ghi authorization header hoặc nội dung nhạy cảm.

### 15.2. Nguyên tắc kiểm soát

1. Dùng **managed identity** và Azure RBAC/ACR repository permission phù hợp cho image pull.
2. Áp dụng quyền **data plane** tối thiểu cho SQL, Storage, Key Vault; network private không thay thế auth.
3. Dùng immutable tag/digest và image scanning trong pipeline, lưu provenance khi yêu cầu.
4. Giới hạn ai được chạy `az containerapp update` và `az containerapp ingress traffic set` trên production.
5. Tách quyền build/push image khỏi quyền đổi traffic production.
6. Bảo vệ cả hostname chính lẫn label URLs bằng auth và ingress policy.
7. Kiểm tra secret refs, environment variables và quản lý rotation an toàn khi hai revision đồng thời active.
8. Dùng change approval/audit trên thao tác promote/rollback.

**Revision không phải một subscription/VNet riêng.** Nếu cần thử một phiên bản chưa tin cậy hoặc có rủi ro cao với production data, hãy dùng **container app/environment/subscription test** độc lập theo yêu cầu, không dựa vào weight 0% để coi revision đó bị cách ly hoàn toàn.

### 15.3. Đường mạng ingress và egress

Nếu container app dùng internal ingress trong Container Apps environment có mạng riêng, phải kiểm tra DNS, VNet, route và cách client truy cập ingress. Nếu public ingress, cần TLS, identity/authorization và WAF/rate limiting theo kiến trúc. Cả stable lẫn candidate có thể gọi API bên ngoài qua cùng egress policy; việc tăng traffic có thể làm thay đổi connection count, SNAT pressure và yêu cầu allowlist của đối tác.

Không giả định traffic split HTTP sẽ tự chia traffic **outbound** đến database đúng 95/5 về số kết nối hoặc số truy vấn. Một request trên candidate có thể gọi database nhiều lần hơn stable.

## 16. Lab minh họa: nhận biết revision bằng HTTP response

Để hiểu traffic splitting bằng kết quả trực quan, có thể chạy một API demo trả về số phiên bản và đường dẫn request. Mẫu này **không chứa dữ liệu production** và được dùng chỉ để chứng minh routing, không để đo hiệu năng thật của hệ thống.

### 16.1. Ứng dụng Node.js tối giản

Tạo file `server.js` trong thư mục demo do bạn sở hữu:

~~~javascript
const http = require("node:http");

const port = Number(process.env.PORT || 8080);
const version = process.env.RELEASE_VERSION || "v1";

const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ready", version }));
    return;
  }

  if (req.url === "/") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      version,
      time: new Date().toISOString(),
      path: req.url
    }));
    return;
  }

  res.writeHead(404);
  res.end("not found");
});

server.listen(port, "0.0.0.0", () => {
  console.log("Demo running:", version, "port:", port);
});
~~~

Tạo file `Dockerfile`:

~~~dockerfile
# Base image minh họa; chọn version/digest được hỗ trợ và scan khi dùng thật.
FROM node:22-alpine
ENV NODE_ENV=production
ENV PORT=8080
WORKDIR /app
COPY --chown=node:node server.js /app/server.js
USER node
EXPOSE 8080
CMD ["node", "server.js"]
~~~

Lưu ý `EXPOSE 8080` chỉ là metadata của image; ứng dụng phải lắng nghe `0.0.0.0:8080` và Container App phải có `targetPort=8080` để ingress chuyển request đúng cổng.

Kiểm thử trên máy có Docker:

~~~bash
docker build -t aca-revision-demo:1.0.0 .
docker run --rm -p 8080:8080 \
  -e RELEASE_VERSION=v1 \
  aca-revision-demo:1.0.0

# Trên terminal khác
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Kỳ vọng response chứa `"version":"v1"` và health 200. Sau đó có thể build/push image tới ACR trong môi trường được phép, ví dụ:

~~~bash
# ACR và quyền push được chuẩn bị trước; không dùng admin key.
ACR_NAME="<lab-acr-name>"
IMAGE_REPO="aca-revision-demo"
IMAGE_TAG="1.0.0"

az acr build \
  --registry "$ACR_NAME" \
  --image "$IMAGE_REPO:$IMAGE_TAG" \
  .
~~~

Lệnh chỉ build/push một image demo. Nếu đã có Container App dùng image đó, **thay env var `RELEASE_VERSION` trong template** cũng có thể tạo revision mới để mô phỏng một release khác dù image không đổi. Nhưng điều này chỉ kiểm thử cơ chế revision/split, **không phải ví dụ thay thế cho quy trình build image v2 thực tế**. Trong hệ thống production, phiên bản code mới phải được build/scan và triển khai bằng digest/tag riêng.

### 16.2. Cách kiểm tra traffic 95/5 có đang hoạt động

Sau khi thiết lập 95/5 và bảo đảm cả hai revision chạy/healthy:

1. Gọi URL chính nhiều lần từ nguồn test được phép.
2. Ghi lại response version, HTTP status và thời gian.
3. Đếm số lần trả v119/v120.
4. Đối chiếu tỷ lệ quan sát với traffic config và logs theo revision.
5. Thử label URL của candidate để xác nhận có thể truy cập trực tiếp bản mới khi weight 0% (nếu ingress/label hỗ trợ).

Ví dụ chạy thử bằng Bash, với mục tiêu demo chứ **không phải kiểm thử tải production**:

~~~bash
FQDN="<container-app-fqdn>"

for i in $(seq 1 100); do
  curl --silent --show-error --max-time 10 "https://$FQDN/"
  printf '\\n'
done
~~~

Kết quả đếm được có thể không đúng chính xác 95/5 trong 100 request. Nếu tất cả request trả một phiên bản, kiểm tra traffic config, ingress hostname đúng, caching/proxy, sticky session hoặc quy tắc routing được hỗ trợ, số lượng request và log thực tế. Không vội kết luận Azure chia traffic sai chỉ từ một mẫu nhỏ hoặc client có cùng connection/session.

### 16.3. Bằng chứng cần lưu trong lab

| Thành phần | Bằng chứng |
|---|---|
| Image | Registry/repository, tag/digest và thời gian build |
| Stable revision | Tên, image, active status, health và weight |
| Candidate revision | Tên, image/env version, active status, health và weight |
| Test | URL được gọi, mã phản hồi, request count theo revision |
| Rollback | Cấu hình 100/0 sau rollback, request mới về stable |
| Logs | Request/console/system logs không chứa secret |

Không đưa request chứa thông tin cá nhân thật vào lab. Các dữ liệu demo phải có thể xóa an toàn theo chính sách và không tạo side effect với thanh toán, email, database production.

## 17. Tự động hóa canary release trong CI/CD

Chạy thủ công lệnh chỉnh weight giúp hiểu cơ chế, nhưng production cần một **đường phát hành có thể kiểm toán và dừng được**.

### 17.1. Pipeline tham chiếu

~~~mermaid
flowchart LR
    PR[Pull request] --> TEST[Unit/integration/security tests]
    TEST --> IMAGE[Build + scan + push image digest]
    IMAGE --> CREATE[Create candidate revision]
    CREATE --> SMOKE[Label URL smoke test]
    SMOKE --> W5[5% traffic]
    W5 --> GATE1{SLO pass?}
    GATE1 -->|Có| W25[25% traffic]
    GATE1 -->|Không| ROLLBACK[100% stable]
    W25 --> GATE2{SLO pass?}
    GATE2 -->|Có| W100[Promote 100% candidate]
    GATE2 -->|Không| ROLLBACK
    W100 --> MONITOR[Observe + giữ stable dự phòng]
~~~

Các bước `SLO pass?` phải được thực thi bởi bộ kiểm tra thực tế hoặc người phê duyệt theo quy trình. Mermaid trên **không phải một pipeline runnable** và không tự thực hiện rollback.

### 17.2. Nguyên tắc build và deploy

- CI build image một lần, gắn tag bất biến, lưu digest và SBOM/provenance nếu chính sách yêu cầu.
- CI/pipeline identity dùng **federated workload identity** hoặc credential được bảo vệ thay vì hardcode service principal secret dài hạn.
- Quyền push image (ACR) và quyền cập nhật Container App/traffic production được phân tách.
- Đặt concurrency lock hoặc deployment gate để tránh **hai pipeline cùng thay traffic** và ghi đè cấu hình của nhau.
- Đọc revision hiện tại rồi thay explicit weights; sau lệnh phải đọc lại API state.
- Trước tăng weight, bảo đảm candidate **active**, health đạt, không có lỗi image pull và dữ liệu tương thích.
- Ghi người/phần mềm phê duyệt, thời điểm, traffic before/after, metrics và kết quả rollback vào change record.
- Nếu metric không có dữ liệu hoặc hệ thống giám sát mất kết nối, **không mặc định đó là pass**.

### 17.3. Khi dùng IaC/Bicep/Terraform

Azure Resource Manager/Bicep/Terraform giúp định nghĩa Container App template và cấu hình ingress. Nhưng có một điểm vận hành quan trọng: **hai nguồn điều khiển cùng ghi traffic weights** có thể va chạm.

Ví dụ một pipeline canary đặt 95/5 bằng CLI, sau đó một lần deploy IaC với `traffic latestRevision 100%` có thể ghi đè kết quả canary. Vì thế:

1. Xác định nguồn sự thật cho **app template** và cho **traffic allocation**.
2. Nếu IaC quản lý cả ingress traffic, mọi thay đổi canary phải cập nhật state/config thích hợp hoặc dùng pipeline biết phối hợp.
3. Không chỉnh tay rồi để drift tồn tại lâu dài mà không giải thích.
4. Sau thay đổi secret/ingress/scale/revision, đọc lại active revisions và weights.
5. Không xóa các revision phục vụ rollback khi một apply IaC dọn cấu hình mà chưa được phê duyệt.

### 17.4. Tránh auto-promote khi monitoring chưa đủ dữ liệu

Một bước canary 5% có thể chỉ nhận vài request mỗi phút. Nếu pipeline chỉ đợi 30 giây rồi đọc error rate bằng 0, nó có thể promote một bản lỗi vì **mẫu số bằng 0**. Nên có:

- Minimum observation time.
- Minimum successful request count hoặc synthetic transaction count.
- Ngưỡng về tỷ lệ lỗi, timeout, latency và dependency failures.
- So sánh với baseline stable/cùng khoảng giờ để giảm nhiễu.
- Điều kiện giữ rollout khi thiếu dữ liệu, lỗi telemetry hoặc canary không nhận traffic như mong đợi.

Một rollback tự động cũng cần policy tránh dao động liên tục: nếu metric hơi tăng rồi lại giảm, pipeline không nên repeatedly chuyển 0/100 ↔ 100/0 mà không có cooldown hoặc điều kiện phê duyệt.

## 18. Chi phí và capacity của nhiều revision

Traffic canary có thể giảm **rủi ro thay đổi**, nhưng không có nghĩa chi phí luôn bằng một release single revision. Trong mô hình tính phí Container Apps, chi phí compute phụ thuộc plan/environment, vCPU/memory, số replica, trạng thái hoạt động, request và các thành phần dịch vụ theo cách tính hiện hành.

### 18.1. Vì sao hai revision active có thể tốn hơn một?

| Thành phần | Điều gì tăng? |
|---|---|
| Replica của stable + candidate | Nhiều bộ nhớ/CPU được cấp hoặc tiêu thụ hơn, nhất là khi `minReplicas` > 0 |
| Container image | Registry giữ nhiều image/digest để rollback |
| Log/trace | Ghi thêm theo version, có thể tăng ingestion và retention |
| Request double processing | Synthetic tests, retries, warm-up có thể tạo thêm traffic |
| Dependency connections | Hai version có connection pools/cache riêng |
| Networking | Private endpoint, NAT/firewall và egress theo kiến trúc |
| Con người/quy trình | Theo dõi canary, kiểm tra và vận hành nhiều lần |

Một revision active **0%** nhưng giữ `minReplicas=1` có thể vẫn sử dụng tài nguyên; ngược lại, scale-to-zero có thể giảm compute khi nhàn rỗi nhưng tạo cold start. Chọn theo SLO và pricing model đang dùng, không tối ưu chỉ dựa vào “số revision”.

### 18.2. Ví dụ dự toán công suất

Giả sử stable cần 6 replicas để phục vụ 1.200 request/giây ở hiệu năng đã đo. Candidate dùng code v120 tiêu thụ CPU cao hơn 30% mỗi request. Nếu đặt 50% traffic cho candidate nhưng `maxReplicas` thấp hoặc không tăng capacity, candidate có thể chậm/429/503 trong khi stable vẫn khỏe.

Cần đo:

- Số request mỗi giây và độ phức tạp từng request.
- CPU/memory mỗi replica, độ trễ startup và thời gian scale.
- max concurrent requests/scale rule theo cấu hình hỗ trợ.
- DB pool, cache và giới hạn API ngoài khi hai revision cùng chạy.
- Headroom khi rollback 100% traffic về stable.

**Khả năng rollback 100% về stable đòi stable còn đủ capacity**. Nếu bạn đã giảm stable xuống một replica để tiết kiệm chi phí ngay khi canary lên 50%, lúc rollback toàn bộ có thể tạo spike. Đây là trade-off giữa chi phí nhân đôi công suất và thời gian phục hồi.

### 18.3. Ngân sách và thời gian giữ stable

Sau promotion, nên có **retention window** cho stable revision/digest đủ dài để nhận diện regression trễ. Nhưng giữ mọi revision active vĩnh viễn làm tăng độ phức tạp/chi phí. Thiết kế:

1. Giữ bản stable trong thời gian rollback window phù hợp mức rủi ro.
2. Sau đó có thể deactivate khi đã xác minh candidate ổn định và dữ liệu tương thích.
3. Dọn image/revision theo retention policy, giữ những artifact phục vụ kiểm toán/DR theo nghĩa vụ.
4. Theo dõi Azure Cost Management, registry storage, Log Analytics và các tài nguyên mạng.
5. Gắn tags `owner`, `application`, `environment` và `costCenter` vào tài nguyên phù hợp.

**Budget alert là cảnh báo, không phải trần chi phí cứng**. Không thay đổi scale min/max hoặc xóa registry image chỉ dựa trên dự toán chưa kiểm chứng với SLO/rollback needs.

## 19. Troubleshooting revision, traffic và rollback

Đừng thay đồng thời image, ingress, secret, network và scale khi thấy lỗi; làm vậy mất khả năng xác định nguyên nhân. Hãy lần theo **artifact → revision → replica → ingress → dependency → telemetry**.

### 19.1. Bảng tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
|---|---|---|
| `az containerapp update` thành công nhưng không thấy revision mới | Template thực tế chưa thay đổi; tham chiếu image/tag giống cũ; API response được hiểu sai | Xem `revision list`, `properties.template` và image/digest |
| Candidate revision không chạy | Image pull denied/not found, sai CPU architecture, crash, thiếu secret hoặc port | System logs, revision show, console logs, registry quyền/mạng |
| Không thể gán nhiều revision 5/95 | App đang ở single mode, ingress/protocol không hỗ trợ, revision inactive hoặc weight không hợp lệ | Kiểm tra `activeRevisionsMode`, HTTP ingress, revision status và traffic |
| Revision active nhưng không có request | Weight 0%, hostname/route khác, scale-to-zero, request quá ít | Xem `ingress.traffic`, metrics theo revision và label |
| Gắn label nhưng URL không truy cập | Label chưa gắn đúng, ingress nội bộ, network/DNS/access policy, revision không healthy | Revision label, FQDN thực tế, DNS và auth |
| Candidate có 503 sau tăng 5% | Cold start, readiness, thiếu replica, CPU/memory hoặc dependency overload | Health/probe, replica count, scale rule và logs |
| Tỷ lệ response quan sát lệch nhiều 95/5 | Mẫu nhỏ, session/caching/retry, request test vào label, phân loại telemetry sai | Tăng mẫu, kiểm tra URL và log ingress theo revision |
| 5xx tăng trên cả stable và candidate | Database/schema/secret/network hoặc downstream API chung có lỗi | Cross-revision dependency traces và thay đổi gần nhất |
| Rollback weight 100% stable nhưng vẫn lỗi | Stable không healthy, migration không tương thích, app-scope config thay đổi | Verify stable health, database schema, secrets/ingress |
| Không activate được stable revision cũ | Revision đã bị dọn, image cũ bị xóa hoặc không có quyền pull | Revision list, ACR digest, role/mạng |
| Rollback không dừng hết side effect | Request/consumer cũ còn chạy, queue đã nhận message, transaction đã commit | In-flight work, idempotency, message dedup, stop/scale |
| Thay secret không thấy hiệu lực | Secret cấp app đổi nhưng replica/env vẫn dùng giá trị lúc khởi động | Kiểm tra secret refs, restart/redeploy an toàn, cả stable/candidate |
| Revision count và bill tăng | Giữ nhiều revision active/min replicas hoặc image retention dài | Dọn theo policy sau rollback window và xem Cost Management |

### 19.2. Quy trình điều tra có thể tái sử dụng

**Bước 1 — Xác nhận phạm vi.** Đúng subscription, resource group, container app, environment, revision và khung thời gian chưa?

~~~bash
az account show --query "{id:id,name:name}" -o table
az containerapp show -n "$APP" -g "$RG" \
  --query "{mode:properties.configuration.activeRevisionsMode,latest:properties.latestRevisionName,traffic:properties.configuration.ingress.traffic}" \
  -o json
~~~

**Bước 2 — Kiểm tra revision.** Candidate tồn tại/active/healthy? Image đúng? Có scale rules/probe/secret references không? Tải output qua `revision show` hoặc Portal, chú ý loại bỏ dữ liệu nhạy cảm trước khi chia sẻ.

**Bước 3 — Kiểm tra target traffic.** Tổng trọng số và mọi rule có đúng không? Có điều kiện `latestRevision` khác đang trỏ vào một bản bất ngờ? Label URL test có thuộc revision candidate đúng không?

**Bước 4 — Kiểm tra startup logs.** Tách lỗi registry pull, environment variable, readiness và runtime crash. Một revision có 0 healthy replicas không nên nhận thêm lưu lượng.

**Bước 5 — Kiểm tra đường phụ thuộc.** Khi image đã chạy và HTTP/health hoạt động nhưng API lỗi, xem database schema, message format, managed identity, RBAC, private DNS, network và downstream rate limits.

**Bước 6 — Kiểm tra SLO/traffic thật.** Phân tích request count, error rate, p95 và business metrics của stable/candidate trong cùng khoảng thời gian.

**Bước 7 — Giảm rủi ro.** Tạm dừng promote, trả 100% ingress về revision stable đã xác minh nếu phù hợp; giữ chứng cứ và phân tích root cause. Nếu vấn đề nằm ở dependency dùng chung, phải khắc phục/restore dependency theo runbook riêng.

### 19.3. Vì sao không nên “xóa candidate rồi tính sau”?

Việc deactivate/xóa revision quá sớm có thể làm mất môi trường để tái hiện lỗi, làm hỏng đường rollback còn phụ thuộc candidate và thay đổi hành vi background worker. Tốt hơn:

- Trước tiên giảm weight candidate về 0% và xác minh stable.
- Xem candidate có label endpoint, background jobs hoặc traffic nội bộ khác không.
- Thu log, revision template, image digest, sự kiện deployment và kết quả test.
- Sau khi có quyết định bảo mật/vận hành, mới deactivate hoặc dọn theo retention.

Nếu phiên bản candidate có lỗ hổng nghiêm trọng và còn được truy cập qua label URL, ưu tiên chặn/đình chỉ đường truy cập đó ngay theo runbook, thay vì chỉ đổi trọng số hostname chính.

## 20. Tình huống thực tế: rollout API thanh toán trên Azure

Một công ty vận hành hệ thống đặt hàng trong Azure Container Apps environment thuộc subscription production. API `ca-orders-api` sử dụng ACR private, managed identity để đọc Key Vault, Azure SQL database và Azure Service Bus cho các sự kiện xử lý đơn hàng. Đội phát triển chuẩn bị v120 có logic thanh toán mới. Yêu cầu: **không để lỗi thanh toán ảnh hưởng toàn bộ khách hàng**, có thể rollback nhanh, không xử lý trùng giao dịch.

### 20.1. Thiết kế bản phát hành

| Thành phần | Stable v119 | Candidate v120 |
|---|---|---|
| Image | `orders-api:1.1.9`, digest đã lưu | `orders-api:1.2.0`, build đã scan |
| Revision | `ca-orders-api--v119` | `ca-orders-api--v120` |
| Chế độ | Multiple revisions | Multiple revisions |
| Ingress ban đầu | 100% | 0% |
| Khi canary | 95% | 5% |
| Replica | min 2, max 8 theo tải đã đo | min 1, max 4 theo tải đã đo |
| Data | Azure SQL schema tương thích cả hai | Cùng database; không xóa cột cũ |
| Identity | Quyền data-plane tối thiểu | Quyền tối thiểu, không cấp vượt phạm vi |
| Quan sát | Request/error/latency theo revision | Tương tự + business success rate |

**Giả sử:** hệ thống có 10.000 requests/phút trong giờ cao điểm. Canary 5% sẽ nhận khoảng **500 requests/phút theo kỳ vọng dài hạn** nếu routing/loại request thực tế phù hợp; con số này không phải bảo đảm đúng từng phút và không nói lên số lượng transaction thành công. Để đánh giá thanh toán, nên đo số **thanh toán đủ điều kiện** và tỷ lệ thành công riêng, không chỉ tổng HTTP requests.

### 20.2. Trước khi mở 5%

1. Build/scan image v120; kiểm chứng digest và chữ ký/attestation khi chính sách yêu cầu.
2. Đánh giá migration SQL theo expand–migrate–contract; v119 vẫn đọc được dữ liệu.
3. Triển khai v120, kiểm tra ACR pull, image startup, health, identity, DNS và private SQL connectivity.
4. Gắn label `candidate` và test một giao dịch **sandbox** có idempotency key.
5. Xác nhận v119 healthy và có đủ capacity cho rollback 100%.
6. Khóa thay đổi traffic bởi một release pipeline duy nhất.
7. Chuẩn bị câu lệnh rollback 100/0 và người có quyền thực thi.

### 20.3. Mở canary rồi đánh giá

Gán traffic 95/5, theo dõi:

- HTTP error rate của từng revision và đặc biệt endpoint `POST /payments`.
- Tỷ lệ giao dịch hợp lệ, lỗi timeout với gateway thanh toán và số giao dịch bị retry.
- Độ trễ p95/p99 theo route.
- SQL deadlocks/connections và Service Bus dead-letter/retry.
- Container restarts/CPU/memory, response health và log có correlation ID.

Nếu v120 trả nhiều 500 ở `POST /payments` nhưng `GET /health` vẫn trả 200, **health-only monitor sẽ không phát hiện chất lượng nghiệp vụ giảm**. Cần business telemetry hoặc synthetic payment test để ra quyết định.

### 20.4. Khi canary lỗi

Giả sử sau năm phút error rate thanh toán của v120 là 7%, trong khi v119 dưới 0,5%, vượt ngưỡng dừng đã phê duyệt:

1. Giữ pipeline; không tăng 25%.
2. Trả `v119=100%` và `v120=0%` trên ingress.
3. Xác minh stable xử lý request mới; so tỷ lệ lỗi và SQL health sau thay đổi.
4. Kiểm tra các payment request v120 đã gửi tới đối tác: đối chiếu **idempotency key**, callback và trạng thái giao dịch để tránh gửi trùng.
5. Nếu v120 có background consumer, xử lý riêng việc dừng/pause theo quy trình messaging.
6. Lưu image digest, trace, logs và change record; không xóa bằng chứng.
7. Điều tra nguyên nhân, xây test ngăn tái diễn rồi phát hành **revision mới** đã sửa.

Nếu v120 đã thực thi migration phá cấu trúc cũ, bước 2 **không bảo đảm khôi phục dịch vụ**. Phải có kế hoạch sửa schema hoặc phục hồi dữ liệu tương ứng, tránh restore database mà không đánh giá giao dịch hợp lệ đã phát sinh.

## 21. Bài thực hành tự đánh giá

**Đề bài:** Một API giao hàng đang có stable revision `shipment-api--v5` (image tag `5.0.0`) và candidate `shipment-api--v6` (image tag `6.0.0`), đều active. Ứng dụng dùng ingress HTTP và Azure SQL chung. Nhóm vận hành muốn thử 10% traffic phiên bản mới, tăng dần lên 100%, có thể rollback bằng một thao tác và không làm mất đơn vận chuyển.

Hãy hoàn thành những phần sau:

1. Vẽ sơ đồ Container App, HTTP ingress, stable/candidate revisions, replicas, Azure SQL và hệ thống giám sát.
2. Giải thích sự khác nhau giữa container image, revision, active revision, replica và revision label.
3. Xác nhận đang ở **Multiple revision mode**; mô tả cách kiểm tra bằng Azure CLI.
4. Liệt kê thay đổi nào tạo revision mới: image, environment variable, scale rule, ingress traffic, secret value, CPU/memory.
5. Viết lệnh đặt traffic **90% v5 / 10% v6**, rồi đọc lại `properties.configuration.ingress.traffic`.
6. Mô tả cách test riêng v6 khi weight 0% mà không mở traffic đại trà, dùng label URL khi được hỗ trợ.
7. Đề xuất ít nhất sáu metric/log phải phân tích riêng theo revision trước khi tăng traffic.
8. Giả sử một phút chỉ có 20 request, hãy giải thích vì sao tỷ lệ quan sát 85/15 chưa chứng minh routing sai.
9. Thiết kế lộ trình 10% → 25% → 50% → 100% với **thời gian theo dõi** và tiêu chí tự dừng ở mỗi bước.
10. Viết lệnh rollback 100% về v5 và các kiểm tra sau rollback.
11. Nếu v6 đã đổi schema Azure SQL theo cách v5 không đọc được, điều gì xảy ra khi rollback? Đề xuất migration an toàn.
12. Mô tả cách xử lý duplicate Service Bus messages khi cả v5 và v6 xử lý cùng một loại sự kiện.
13. So sánh chi phí/độ trễ khi giữ `minReplicas=1` cho candidate với scale-to-zero.
14. Nêu nguy cơ nếu secret cấp app bị rotate giữa rollout nhưng stable revision không được restart.
15. Lập checklist quyền Azure RBAC, ACR pull, data access và audit cần có để pipeline được phép chỉnh traffic.
16. Thiết kế kế hoạch dọn revision/image sau rollback window mà không làm mất artifact cần cho DR.

### Khung lệnh dự kiến

~~~bash
RG="rg-shipping-lab"
APP="shipment-api"
OLD="shipment-api--v5"
NEW="shipment-api--v6"

az containerapp revision set-mode -n "$APP" -g "$RG" --mode multiple
az containerapp revision list -n "$APP" -g "$RG" -o table

# Sau khi xác nhận cả hai revision active và healthy:
az containerapp ingress traffic set \
  -n "$APP" -g "$RG" \
  --revision-weight "$OLD=90" "$NEW=10"

# Kiểm tra cấu hình traffic:
az containerapp show -n "$APP" -g "$RG" \
  --query "properties.configuration.ingress.traffic" -o json

# Rollback (khi OLD vẫn còn active/healthy):
az containerapp ingress traffic set \
  -n "$APP" -g "$RG" \
  --revision-weight "$OLD=100" "$NEW=0"
~~~

Mọi tên trong đoạn trên là **mẫu**, không phải lệnh chạy cho production thực tế. Cần xác minh tên revision trong tài nguyên Azure trước khi dùng. Việc đặt 100% về old revision là **rollback ingress**, không hoàn tác SQL schema, message processing, secret hoặc những thay đổi cấu hình cấp app.

### Tiêu chí hoàn thành

Bài tập đạt khi người học giải thích được: phiên bản nào đang thực sự nhận traffic, cần những điều kiện gì trước promote, làm sao đo 5xx/latency riêng từng revision, khi nào rollback bằng trọng số đủ để khôi phục, khi nào phải dùng kế hoạch phục hồi dữ liệu, và vì sao không được deactivate/xóa stable trước khi hết rollback window.

## 22. Checklist trước – trong – sau canary

### Trước release

- [ ] Đã xác định subscription/resource group/Container App đúng và người chịu trách nhiệm.
- [ ] Image đã build, scan, gắn version tag bất biến và ghi digest.
- [ ] Managed identity/registry permissions, private DNS/network, secret refs đã được xác minh.
- [ ] Migration database/message schema tương thích stable + candidate trong giai đoạn coexist.
- [ ] App chạy Multiple revision mode và có HTTP ingress hỗ trợ traffic split.
- [ ] Stable revision active/healthy, đủ capacity phục vụ 100% khi rollback.
- [ ] Candidate image chạy đúng, health/readiness và label smoke test đạt.
- [ ] Có telemetry theo revision và đủ lượng dữ liệu/độ tin cậy để ra quyết định.
- [ ] Có người/pipeline có quyền rollback và change ticket/approval.

### Trong rollout

- [ ] Đặt trọng số một cách tường minh, đọc lại `ingress.traffic`.
- [ ] Đối chiếu revision name và tag/digest trước mỗi lần tăng trọng số.
- [ ] Theo dõi request count, error rate, p95/p99, restart, CPU/memory và dependency metrics.
- [ ] Kiểm tra giao dịch nghiệp vụ thật hoặc synthetic tương ứng.
- [ ] Không tăng traffic nếu candidate có vấn đề hoặc telemetry mất dữ liệu.
- [ ] Giữ các bước canary đủ lâu; không chạy một script 5/25/50/100 liên tục.
- [ ] Có phương án giảm ngay về stable nếu ngưỡng sự cố bị vượt.

### Sau promotion hoặc rollback

- [ ] Đọc lại traffic config; xác nhận phiên bản nhận request mới thực tế.
- [ ] Xác minh health, SLO và tất cả dependency quan trọng.
- [ ] Kiểm tra side effects/background consumer và duplicate business operations.
- [ ] Ghi log change, người quyết định, nguyên nhân và kết quả.
- [ ] Giữ stable revision và image digest đủ thời gian rollback window.
- [ ] Chỉ deactivate/dọn revision sau khi kiểm tra không còn label/internal path cần dùng.
- [ ] Rà soát chi phí replicas, Log Analytics, image retention và network.

## 23. Dọn dẹp lab có kiểm soát

Trong lab, hãy **chỉ dọn những revision và tài nguyên thật sự do bạn tạo**. Không xóa Container Apps environment, ACR hoặc resource group nếu chúng chứa ứng dụng của nhóm khác.

Trước khi dọn, đọc:

~~~bash
az account show --query "{id:id,name:name}" -o table

az containerapp revision list \
  --name "$APP" \
  --resource-group "$RG" \
  --output table

az containerapp show \
  --name "$APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.traffic" \
  --output json

az resource list \
  --resource-group "$RG" \
  --output table
~~~

Nếu cần dừng một revision demo còn active sau khi weight đã về 0%:

~~~bash
# Chỉ dùng với revision THỬ NGHIỆM và sau khi xác minh không còn traffic.
# az containerapp revision deactivate \
#   --name "$APP" --resource-group "$RG" \
#   --revision "$CANDIDATE_REV"
~~~

Không xóa image cũ trong ACR khi vẫn cần cho rollback, replay/audit hoặc disaster recovery. Các lệnh xóa Container App, environment hoặc resource group cần xác định phạm vi và được phê duyệt riêng; **không dùng lệnh xóa hàng loạt tự động chỉ để “làm sạch revision”**.

## 24. Ghi nhớ

- **Revision** là snapshot bất biến của các thuộc tính template được Container Apps quản lý; **replica** là instance đang chạy của một revision. Image tag không phải revision và có thể không đại diện duy nhất cho digest.
- **Single revision mode** thích hợp luồng phát hành đơn giản; **Multiple revision mode** cho phép nhiều revision active và kiểm soát **HTTP ingress traffic** theo trọng số.
- **Traffic splitting** cần trọng số minh bạch, revision healthy và giám sát theo revision. Tỷ lệ traffic không quyết định trực tiếp số replica hoặc số truy vấn database.
- **Revision label** là đường truy cập tới một revision khi ingress hỗ trợ, không thay thế weight và cũng không phải ranh giới bảo mật.
- **Rollback nhanh** thường là trả 100% ingress về stable revision khi bản đó còn active/khả dụng, đủ capacity và tương thích dữ liệu.
- **Rollback code không rollback database/schema, secrets, queue messages hoặc side effects.** Thiết kế tương thích ngược, idempotency và backup/DR trước khi release.
- **Quan sát và bảo mật** là điều kiện bắt buộc: image digest/registry auth, startup/health, SLO theo revision, Azure RBAC, private networking và change audit.
- **Chi phí** phụ thuộc nhiều replica active, scale rules, logs, registry và network; giữ stable đủ lâu để rollback nhưng không để revision cũ chạy vô hạn không mục đích.

Mục tiêu của canary không phải “đưa đúng 5% lưu lượng vào bản mới”, mà là **thu thập đủ bằng chứng để tăng tỷ lệ an toàn hoặc đưa lưu lượng về bản ổn định trước khi ảnh hưởng lan rộng**. Một release được coi là hoàn tất chỉ khi chất lượng dịch vụ, khả năng rollback và dữ liệu dùng chung đều đã được kiểm chứng.
