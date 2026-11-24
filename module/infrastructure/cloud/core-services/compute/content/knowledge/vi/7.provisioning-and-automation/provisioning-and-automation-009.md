# Rollback và dọn tài nguyên khi quá trình triển khai thất bại

Triển khai hạ tầng hoặc ứng dụng trên đám mây thường gồm nhiều thao tác liên tiếp: tạo máy ảo, gắn ổ đĩa, cấu hình mạng, cấp quyền, cài phần mềm, cập nhật dịch vụ và chuyển lưu lượng người dùng. Chỉ cần một bước thất bại, hệ thống có thể ở trạng thái triển khai dở dang: một số tài nguyên đã được tạo, một số cấu hình đã thay đổi, trong khi ứng dụng chưa thể phục vụ.

**Rollback** đưa hệ thống về trạng thái ổn định đã biết hoặc áp dụng một thay đổi bù để khôi phục dịch vụ. **Dọn tài nguyên (cleanup)** xử lý những tài nguyên tạm, tài nguyên được tạo một phần hoặc tài nguyên không còn cần thiết sau lần triển khai thất bại. Hai việc này có liên quan nhưng có mục tiêu khác nhau: khôi phục dịch vụ cần ưu tiên tính đúng đắn và tính sẵn sàng; cleanup cần bảo vệ dữ liệu và tránh để lại tài nguyên gây chi phí hoặc rủi ro.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, rollback và cleanup là phần thiết yếu của cấp phát và tự động hóa. Chúng giúp pipeline xử lý lỗi có kiểm soát khi tạo máy ảo, cấu hình network, triển khai container, thay đổi image hoặc cập nhật nhóm máy. Một quy trình tốt phải biết tài nguyên nào được phép xóa, tài nguyên nào cần giữ, trạng thái nào cần khôi phục và cách xác minh hệ thống đã ổn định.

## 1. Rollback và cleanup giải quyết vấn đề gì?

Một triển khai có thể thất bại ở nhiều thời điểm:

- **Trước khi tạo tài nguyên:** kiểm tra cấu hình, quota, quyền hoặc tham số đầu vào không đạt.
- **Trong lúc cấp phát:** máy ảo đã tạo nhưng gắn disk thất bại; network interface tồn tại nhưng cấu hình bảo mật chưa hoàn tất.
- **Sau khi cấp phát:** agent không khởi động, image không tương thích, ứng dụng không qua health check.
- **Trong lúc chuyển lưu lượng:** một phần người dùng đã đi vào phiên bản mới nhưng lỗi tăng hoặc latency vượt SLO.
- **Sau khi triển khai:** phát hiện lỗi dữ liệu, cấu hình hoặc phụ thuộc không tương thích.

Nếu pipeline chỉ dừng ngay tại bước lỗi, tài nguyên đã tạo trước đó có thể còn tồn tại. Điều này dẫn đến:

- Chi phí máy ảo, disk, IP, load balancer hoặc địa chỉ NAT tiếp tục phát sinh.
- Tài nguyên chưa được quản lý hoặc không còn được tham chiếu trong state của công cụ IaC.
- Máy hoặc dịch vụ chạy một phần cấu hình, gây xung đột khi triển khai lại.
- Quyền truy cập, security group hoặc endpoint tạm thời vẫn mở.
- Dữ liệu bị ghi dở dang hoặc nhiều phiên bản cùng ghi vào một nơi.
- Nhóm vận hành không biết hệ thống hiện đang ở phiên bản nào.

Rollback tập trung vào khôi phục trạng thái hoạt động. Cleanup tập trung vào thu hồi những tài nguyên không còn cần. Có trường hợp phải rollback trước rồi mới cleanup; có trường hợp phải giữ nguyên tài nguyên lỗi để thu thập log, snapshot hoặc điều tra trước khi xóa.

## 2. Phân biệt rollback, roll forward và cleanup

Ba hành động thường bị gọi chung là rollback nhưng có ý nghĩa khác nhau:

| Hành động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Rollback | Quay về phiên bản hoặc cấu hình ổn định trước đó | Chuyển load balancer về nhóm máy cũ |
| Roll forward | Sửa lỗi bằng một phiên bản mới hơn | Phát hành bản vá sửa lỗi của release vừa triển khai |
| Cleanup | Thu hồi tài nguyên không còn cần sau lần triển khai | Xóa máy build tạm, disk thử nghiệm và IP tạm |

Không phải lỗi nào cũng nên rollback. Nếu thay đổi mới đã ghi dữ liệu theo định dạng mà phiên bản cũ không đọc được, rollback ứng dụng có thể khiến dịch vụ hỏng nặng hơn. Trong trường hợp đó, roll forward hoặc phục hồi dữ liệu theo quy trình có thể an toàn hơn.

Cleanup cũng không đồng nghĩa với xóa tất cả tài nguyên xuất hiện trong lần triển khai. Database, object storage, disk chứa dữ liệu người dùng, khóa mã hóa, log và tài nguyên dùng chung có thể cần tồn tại sau khi release thất bại.

## 3. Thiết kế quy trình xử lý thất bại

Pipeline nên xác định rõ trạng thái trước khi chạy, tài nguyên nào thuộc lần triển khai và hành động cần thực hiện khi từng giai đoạn thất bại.

~~~mermaid
flowchart TD
    A["Bắt đầu triển khai"] --> B["Kiểm tra đầu vào và quyền"]
    B --> C["Ghi nhận release ID và danh sách tài nguyên"]
    C --> D["Cấp phát và cấu hình"]
    D --> E["Kiểm thử health và chức năng"]
    E --> F{"Đạt điều kiện phát hành?"}
    F -- "Có" --> G["Chuyển lưu lượng / xác nhận release"]
    G --> H["Đánh dấu triển khai thành công"]
    F -- "Không" --> I["Đóng băng thay đổi và lưu bằng chứng"]
    I --> J["Khôi phục phiên bản hoặc cấu hình ổn định"]
    J --> K["Xác minh dịch vụ"]
    K --> L["Dọn tài nguyên tạm được phép xóa"]
    L --> M["Đối soát state và tài nguyên còn lại"]
    M --> N["Báo cáo kết quả và tài nguyên cần giữ"]
~~~

Một quy trình triển khai có kiểm soát thường gồm:

1. Tạo mã lần triển khai (release ID hoặc operation ID) duy nhất.
2. Ghi nhận phiên bản trước triển khai, cấu hình đích và tài nguyên dự kiến tạo hoặc thay đổi.
3. Thực hiện cấp phát theo từng giai đoạn; lưu ID tài nguyên sau mỗi thao tác thành công.
4. Kiểm tra health, readiness, smoke test và các SLO quan trọng.
5. Chỉ chuyển lưu lượng hoặc đánh dấu release thành công khi các điều kiện đạt.
6. Nếu thất bại, dừng các bước tiếp theo và ngăn pipeline khác thao tác xung đột.
7. Thu thập log, trạng thái, event và metadata cần cho điều tra.
8. Thực hiện rollback hoặc roll forward theo loại thay đổi.
9. Cleanup tài nguyên tạm thuộc đúng release và được chính sách cho phép.
10. Đối soát trạng thái thực tế với state của công cụ quản lý hạ tầng.

Mỗi giai đoạn nên có timeout, điều kiện thành công, điều kiện thất bại và cách tiếp tục khi thao tác bị gián đoạn. Một lệnh API trả về timeout không có nghĩa tài nguyên chắc chắn chưa được tạo; cần truy vấn trạng thái trước khi thử lại.

## 4. Ghi nhận quyền sở hữu tài nguyên

Cleanup an toàn bắt đầu từ khả năng xác định tài nguyên nào được tạo bởi lần triển khai nào. Nếu không có dấu vết sở hữu, một bước dọn dẹp tự động có thể xóa nhầm tài nguyên đang được workload khác sử dụng.

### 4.1. Gắn tag hoặc label

Nên gắn metadata thống nhất cho tài nguyên được tạo tự động:

| Tag/label | Mục đích | Ví dụ |
| --- | --- | --- |
| application | Xác định ứng dụng | checkout-api |
| environment | Xác định môi trường | staging |
| release-id | Liên kết tài nguyên với một lần triển khai | rel-20261122-042 |
| owner | Nhóm chịu trách nhiệm | platform-team |
| managed-by | Công cụ hoặc pipeline quản lý | ci-image-deploy |
| lifecycle | Quy tắc vòng đời | temporary |
| expires-at | Thời điểm cần xem xét/xóa | 2026-11-23T02:00:00Z |

Ví dụ metadata có thể được gắn lên VM, disk, NIC, security group, load balancer, snapshot và tài nguyên phụ trợ. Tên tag cụ thể phụ thuộc nền tảng; điều quan trọng là có một quy ước chung và pipeline thực sự áp dụng nó.

Không phải mọi tài nguyên đều hỗ trợ tag ngay khi tạo. Với tài nguyên đó, cần ghi ID vào manifest hoặc state của lần triển khai ngay sau khi API trả kết quả.

### 4.2. Manifest tài nguyên của một release

Manifest lưu danh sách tài nguyên đã tạo hoặc thay đổi, cùng hành động được phép khi thất bại. Ví dụ:

~~~yaml
release:
  id: rel-20261122-042
  application: checkout-api
  environment: staging
  previous_version: v2.8.1
  target_version: v2.9.0

resources:
  - id: vm-123
    type: virtual-machine
    action_on_failure: delete
    ownership: release
  - id: disk-456
    type: data-disk
    action_on_failure: retain
    ownership: shared-data
  - id: lb-backend-789
    type: load-balancer-backend
    action_on_failure: restore
    ownership: shared-service
~~~

Đây là ví dụ mô tả, không phải schema dùng chung cho mọi nhà cung cấp. Pipeline cần kiểm tra manifest trước khi cleanup và chỉ xóa tài nguyên có ownership phù hợp. Tài nguyên không xác định được chủ sở hữu nên được chuyển sang trạng thái cần điều tra, không tự động xóa.

## 5. Rollback theo chiến lược triển khai

Chiến lược rollback phụ thuộc cách phiên bản mới được đưa vào phục vụ.

### 5.1. Rolling deployment

Rolling deployment thay thế từng nhóm instance hoặc pod theo từng đợt. Nếu health check thất bại:

- Dừng rollout để không thay thế thêm instance đang ổn định.
- Giữ lại phiên bản cũ nếu nó vẫn còn hoạt động.
- Đưa các instance đã cập nhật về image hoặc cấu hình trước đó.
- Kiểm tra capacity để bảo đảm đủ máy khỏe phục vụ tải.
- Chỉ tiếp tục rollout sau khi lỗi được xử lý và kiểm thử lại.

Một rủi ro của rolling deployment là trong một khoảng thời gian, hai phiên bản cùng chạy. API, message format và schema dữ liệu cần tương thích ngược trong giai đoạn chuyển tiếp.

### 5.2. Blue-green deployment

Blue-green duy trì hai môi trường: blue đang phục vụ và green chứa phiên bản mới. Pipeline kiểm thử green trước khi chuyển lưu lượng.

Nếu green lỗi sau khi chuyển:

1. Chuyển route hoặc listener về blue.
2. Xác minh health và tỷ lệ lỗi trên blue.
3. Giữ green để thu thập log nếu cần.
4. Sau khi điều tra, xóa tài nguyên green tạm theo manifest.

Chiến lược này cho phép chuyển lại lưu lượng nhanh, nhưng cần đủ capacity để duy trì hai môi trường và phải xem xét các thay đổi dữ liệu đã phát sinh ở green.

### 5.3. Canary deployment

Canary chỉ chuyển một tỷ lệ nhỏ lưu lượng đến phiên bản mới. Nếu latency, lỗi hoặc metric nghiệp vụ vượt ngưỡng:

- Ngừng tăng tỷ lệ traffic.
- Chuyển toàn bộ traffic về phiên bản ổn định.
- Dừng hoặc thu nhỏ canary sau khi đã thu thập dữ liệu cần thiết.
- Kiểm tra queue, cache và dữ liệu do canary tạo ra.

Không nên chỉ dựa vào CPU hoặc health endpoint để quyết định rollback. Cần quan sát tỷ lệ lỗi, p95/p99, throughput, saturation và chỉ số nghiệp vụ.

### 5.4. Thay đổi hạ tầng bằng Infrastructure as Code

Với Terraform, CloudFormation hoặc công cụ IaC khác, một lần apply có thể tạo thành công một số tài nguyên trước khi một tài nguyên tiếp theo thất bại. State có thể đã được cập nhật một phần.

Quy trình xử lý nên:

1. Giữ lại output và log của lần apply.
2. Kiểm tra state và trạng thái thực tế trên provider.
3. Chạy plan/preview để xác định chênh lệch.
4. Xác định tài nguyên nào đã tạo, tài nguyên nào đang được dùng chung và tài nguyên nào cần giữ.
5. Sửa nguyên nhân rồi apply tiếp hoặc tạo kế hoạch cleanup có giới hạn.

Không xóa file state để cố làm lại từ đầu. State là dữ liệu quản lý liên kết giữa cấu hình và tài nguyên thật; xóa state có thể khiến công cụ mất khả năng nhận diện tài nguyên đang tồn tại. Không chạy destroy toàn bộ workspace chỉ vì một apply thất bại, nhất là khi workspace chứa tài nguyên dùng chung hoặc dữ liệu quan trọng.

## 6. Xử lý tài nguyên được tạo một phần

Thất bại giữa chừng là tình huống phổ biến trong hệ thống phân tán. Ví dụ, API tạo VM có thể đã hoàn tất ở provider nhưng client bị timeout trước khi nhận ID. Nếu pipeline gửi lại yêu cầu một cách mù quáng, nó có thể tạo thêm VM thứ hai.

### 6.1. Idempotency và truy vấn trạng thái

Một thao tác idempotent có thể được thực hiện lại mà không tạo thêm tác dụng phụ ngoài ý muốn. Khi API hỗ trợ idempotency key, hãy dùng release ID hoặc operation ID làm khóa duy nhất cho yêu cầu tạo tài nguyên.

Nếu API không hỗ trợ idempotency key:

- Dùng tên tài nguyên có quy ước chứa release ID.
- Truy vấn tài nguyên theo tag, tên hoặc operation ID trước khi thử lại.
- Kiểm tra trạng thái operation bất đồng bộ của provider.
- Ghi lại ID tài nguyên ngay khi có thể.
- Phân biệt timeout ở client với lỗi được provider xác nhận.

Không coi một lần gọi API bị timeout là thất bại chắc chắn. Hãy xác minh trạng thái thực tế trước khi retry hoặc cleanup.

### 6.2. Thao tác bất đồng bộ

Nhiều API cấp phát VM, disk hoặc load balancer trả về operation ID rồi tiếp tục xử lý ở nền. Pipeline cần poll hoặc nhận event cho đến khi operation ở trạng thái hoàn tất, thất bại hoặc hết thời gian cho phép.

Nếu pipeline bị hủy giữa lúc provider đang xử lý, một tiến trình đối soát sau đó cần tìm operation còn chạy và quyết định chờ, hủy hoặc cleanup theo chính sách. Không xóa tài nguyên phụ thuộc khi operation tạo tài nguyên chính vẫn đang thực hiện.

### 6.3. Cleanup theo thứ tự phụ thuộc

Tài nguyên thường có quan hệ phụ thuộc. Ví dụ, VM sử dụng NIC; NIC nằm trong subnet; disk gắn với VM; backend pool tham chiếu đến VM. Khi xóa, cần tháo liên kết và xử lý theo thứ tự ngược với lúc tạo.

Ví dụ thứ tự tổng quát:

1. Ngừng nhận traffic hoặc gỡ backend khỏi load balancer.
2. Drain request và dừng workload.
3. Tháo volume hoặc thiết bị phụ thuộc nếu cần.
4. Xóa VM hoặc container workload tạm.
5. Xóa NIC, disk tạm, địa chỉ và security rule chỉ thuộc release.
6. Xóa network hoặc nhóm tài nguyên tạm nếu không còn phụ thuộc.
7. Đối soát lại danh sách tài nguyên còn tồn tại.

Thứ tự chính xác phụ thuộc provider và loại tài nguyên. Nếu một tài nguyên vẫn được tham chiếu, provider có thể từ chối xóa; pipeline cần ghi lỗi và tiếp tục xử lý các tài nguyên độc lập khác thay vì bỏ dở toàn bộ cleanup.

## 7. Những tài nguyên không nên xóa tự động

Một số tài nguyên cần được giữ lại dù triển khai thất bại:

- Database chứa dữ liệu thật hoặc dữ liệu đã được người dùng cập nhật.
- Persistent disk chưa được xác nhận có backup hợp lệ.
- Object storage chứa file người dùng, artifact hoặc log điều tra.
- Snapshot và backup phục vụ khôi phục.
- KMS key hoặc secret được dùng bởi nhiều dịch vụ.
- VPC, subnet, route table, NAT, firewall hoặc security group dùng chung.
- Load balancer và DNS record đang phục vụ phiên bản ổn định.
- State file, manifest và metadata phục vụ đối soát.

Cleanup tự động nên áp dụng allowlist tài nguyên tạm và denylist tài nguyên quan trọng. Nếu không chắc chắn một disk hoặc bucket có dữ liệu cần giữ hay không, hãy chuyển sang trạng thái chờ xác nhận hoặc giữ lại theo chính sách.

### 7.1. Bảo vệ dữ liệu và thay đổi schema

Rollback ứng dụng không tự động rollback database. Một migration có thể thêm cột, đổi kiểu dữ liệu, xóa cột hoặc ghi dữ liệu theo định dạng mới. Phiên bản ứng dụng cũ có thể không tương thích với schema mới.

Chiến lược **expand-and-contract** giúp giảm rủi ro:

1. Mở rộng schema theo cách phiên bản cũ vẫn tương thích, chẳng hạn thêm cột mới cho phép null.
2. Triển khai phiên bản ứng dụng có thể đọc/ghi cả cấu trúc cũ và mới trong giai đoạn chuyển tiếp.
3. Backfill dữ liệu và xác minh tính nhất quán.
4. Chuyển ứng dụng sang cấu trúc mới.
5. Chỉ loại bỏ cấu trúc cũ sau khi không còn phiên bản nào sử dụng.

Với migration phá hủy hoặc không thể đảo ngược, cần backup, kiểm tra khả năng restore và kế hoạch roll forward trước khi triển khai. Không nên dùng rollback tự động để xóa dữ liệu vừa được ghi bởi phiên bản mới.

## 8. Rollback ứng dụng container và Kubernetes

Trong Kubernetes, một Deployment có thể lưu các revision và hỗ trợ quay về revision trước. Ví dụ:

~~~bash
kubectl rollout status deployment/checkout-api
kubectl rollout undo deployment/checkout-api
kubectl rollout history deployment/checkout-api
~~~

Các lệnh này minh họa rollback revision của Deployment. Chúng không tự động đảo ngược database migration, side effect bên ngoài, thay đổi ConfigMap/Secret độc lập, CRD hoặc dữ liệu trong PersistentVolume.

Với Helm, rollback release có thể khôi phục manifest của chart về revision trước theo cơ chế của Helm. Cần kiểm tra hook, Job migration, tài nguyên được giữ lại và các thay đổi bên ngoài chart. Không nên giả định một lệnh helm rollback sẽ hoàn tác mọi thao tác đã chạy trong hook.

Trước khi cleanup pod hoặc namespace thử nghiệm:

- Thu thập log, event, trạng thái pod và kết quả health check.
- Xác định PersistentVolumeClaim có chứa dữ liệu cần giữ không.
- Kiểm tra Service, Ingress, load balancer và secret có dùng chung không.
- Xóa workload tạm theo release label.
- Chỉ xóa PVC hoặc namespace khi chính sách lưu trữ cho phép.

## 9. Cleanup tự động và xử lý tài nguyên mồ côi

Tài nguyên mồ côi (orphan resource) là tài nguyên còn tồn tại nhưng không còn được pipeline, ứng dụng hoặc nhóm vận hành quản lý rõ ràng. Chúng có thể xuất hiện khi job bị hủy, runner mất kết nối hoặc thao tác cleanup thất bại.

Một cơ chế cleanup định kỳ có thể:

1. Tìm tài nguyên có tag managed-by và lifecycle=temporary.
2. Kiểm tra expires-at đã qua thời hạn cho phép.
3. Xác minh release tương ứng đã ở trạng thái failed, canceled hoặc completed.
4. Kiểm tra tài nguyên không còn được tham chiếu bởi workload đang hoạt động.
5. Ghi danh sách dự kiến xóa và lý do.
6. Thực hiện dry-run hoặc yêu cầu phê duyệt theo mức rủi ro.
7. Xóa tài nguyên theo thứ tự phụ thuộc.
8. Ghi kết quả, lỗi và tài nguyên cần xử lý thủ công.

Không nên xóa chỉ dựa trên tuổi tài nguyên. Một disk cũ có thể là backup cần lưu giữ; một IP lâu ngày không gắn có thể được dành cho đợt triển khai sắp tới. Tag, trạng thái release, dependency và chính sách retention cần được xét cùng nhau.

### 9.1. Ví dụ chính sách TTL

~~~yaml
cleanup_policy:
  selector:
    managed-by: ci-provisioner
    lifecycle: temporary
  require_release_state:
    - failed
    - canceled
  grace_period: 24h
  dry_run_by_default: true
  protected_resource_types:
    - database
    - persistent-volume
    - backup
    - kms-key
  require_owner_for_unknown_resources: true
~~~

Đây là cấu hình minh họa. TTL 24 giờ chỉ là ví dụ; thời gian giữ cần phù hợp với thời gian điều tra, lịch sử dụng và yêu cầu lưu trữ của tổ chức.

## 10. Pipeline mẫu có bước rollback và cleanup

Ví dụ dưới đây thể hiện cách tổ chức các bước trong pipeline. Tên lệnh là placeholder, cần thay bằng công cụ của tổ chức và provider.

~~~yaml
stages:
  - prepare
  - provision
  - deploy
  - verify
  - finalize

variables:
  RELEASE_ID: "rel-20261122-042"

prepare:
  stage: prepare
  script:
    - validate-inputs
    - record-previous-release
    - create-resource-manifest

provision:
  stage: provision
  script:
    - provision-resources --release "$RELEASE_ID"
    - record-resource-identifiers

deploy:
  stage: deploy
  script:
    - deploy-version
    - wait-for-readiness

verify:
  stage: verify
  script:
    - run-smoke-tests
    - check-error-rate-and-latency

finalize:
  stage: finalize
  script:
    - mark-release-successful
    - cleanup-superseded-temporary-resources
  when: on_success

rollback:
  stage: finalize
  script:
    - capture-failure-evidence
    - restore-previous-traffic-and-version
    - verify-service-health
    - cleanup-eligible-release-resources
    - reconcile-provider-state
  when: on_failure
~~~

Trong pipeline thật, rollback job cần chạy ngay cả khi một job ở giai đoạn trước thất bại. Cần cấu hình dependency và điều kiện thực thi phù hợp với CI/CD engine; một số hệ thống yêu cầu khai báo job always/when-always hoặc workflow riêng. Các lệnh cleanup phải đọc manifest, kiểm tra ownership và loại tài nguyên được phép xóa trước khi thực hiện.

Không nên đưa credential trực tiếp vào biến hoặc log của pipeline. Dùng secret store của CI/CD và danh tính workload với quyền tối thiểu. Quyền rollback có thể cần cập nhật route hoặc deployment; quyền cleanup chỉ nên được phép xóa loại tài nguyên tạm trong phạm vi release.

## 11. Theo dõi kết quả rollback và cleanup

Pipeline không nên đánh dấu thành công chỉ vì lệnh rollback hoặc delete trả về mã thoát bằng 0. Cần xác minh trạng thái thực tế.

| Nhóm kiểm tra | Chỉ số hoặc bằng chứng | Tiêu chí đạt |
| --- | --- | --- |
| Dịch vụ | Health check, tỷ lệ lỗi, p95/p99, throughput | Trở lại trong ngưỡng SLO |
| Phiên bản | Image ID, deployment revision, release ID | Phiên bản đang phục vụ đúng như dự kiến |
| Lưu lượng | Backend pool, route, DNS hoặc traffic split | Lưu lượng đi đến nhóm ổn định |
| Dữ liệu | Migration status, replication lag, integrity check | Không có sai lệch hoặc mất dữ liệu ngoài dự kiến |
| Tài nguyên | Danh sách VM, disk, NIC, IP, volume, load balancer | Tài nguyên tạm được xử lý; tài nguyên cần giữ còn tồn tại |
| State IaC | Plan, state và tài nguyên thực tế | Không còn chênh lệch chưa được giải thích |
| Bảo mật | IAM, firewall, secret và endpoint tạm | Quyền và đường truy cập tạm được thu hồi |
| Chi phí | Tài nguyên còn chạy và storage còn giữ | Không còn tài nguyên tạm phát sinh phí ngoài chính sách |

Nếu dịch vụ đã phục hồi nhưng cleanup còn lỗi, nên báo cáo hai kết quả riêng: **service recovery** và **resource cleanup**. Ví dụ, rollback thành công nhưng một disk tạm chưa xóa được do còn attachment. Pipeline có thể đánh dấu dịch vụ ổn định và tạo ticket/alert cho phần cleanup, thay vì tuyên bố toàn bộ công việc đã hoàn tất.

## 12. Xử lý khi chính rollback cũng thất bại

Rollback là một thao tác có thể thất bại. Phiên bản cũ có thể không còn đủ capacity, route có thể không cập nhật được, quyền của pipeline có thể hết hạn hoặc dữ liệu đã thay đổi khiến phiên bản trước không tương thích.

Nên chuẩn bị:

- **Fallback:** giữ traffic ở môi trường ổn định hoặc chuyển sang trang bảo trì khi không thể khôi phục ngay.
- **Retry có giới hạn:** chỉ retry thao tác idempotent, có backoff và kiểm tra trạng thái.
- **Escalation:** gửi cảnh báo đến người trực khi rollback vượt timeout hoặc không đạt health check.
- **Bằng chứng:** giữ log, event, manifest và snapshot cần thiết cho điều tra.
- **Runbook:** chỉ rõ ai có quyền quyết định roll forward, restore backup hoặc chuyển traffic.
- **Reconciliation:** chạy lại bước đối soát sau khi provider phục hồi hoặc quyền được khôi phục.

Với hệ thống phân tán, không phải mọi side effect đều có thể hoàn tác. Ví dụ, email đã gửi, giao dịch thanh toán đã xác nhận hoặc webhook đã gọi ra ngoài không thể bị xóa bằng cách rollback deployment. Ứng dụng cần dùng **compensating action** như hoàn tiền, gửi sự kiện điều chỉnh hoặc ghi nhận trạng thái cần xử lý. Các thao tác bù nên có ID giao dịch và cơ chế chống thực hiện lặp.

## 13. Ví dụ thực tế: triển khai nhóm máy ảo thất bại

Một pipeline tạo phiên bản mới cho dịch vụ Java bằng cách cấp ba VM, gắn disk, đăng ký backend vào load balancer và triển khai image mới. Hai VM khởi động thành công; VM thứ ba không boot được do image thiếu driver. Health check của nhóm không đạt nên pipeline dừng trước khi chuyển toàn bộ traffic.

Nhóm xử lý:

1. Đánh dấu release là failed và khóa các pipeline khác khỏi sửa cùng nhóm tài nguyên.
2. Lưu log boot, ID image, operation ID và trạng thái của ba VM.
3. Giữ nhóm backend cũ đang phục vụ người dùng.
4. Gỡ hai VM mới khỏi backend pool để không nhận traffic.
5. Xóa hai VM thử nghiệm thuộc release và NIC tương ứng sau khi xác minh chúng không chứa dữ liệu cần giữ.
6. Giữ disk chẩn đoán của VM lỗi trong thời gian điều tra, gắn tag để không bị cleanup tự động.
7. Đối soát manifest với tài nguyên thực tế; xác nhận load balancer, network và disk dùng chung vẫn tồn tại.
8. Sửa image, tạo release ID mới và chạy lại pipeline từ đầu với image đã kiểm thử.

Nếu nhóm xóa toàn bộ resource group hoặc network ngay khi thất bại, dịch vụ cũ có thể mất kết nối. Nếu xóa disk lỗi quá sớm, nhóm sẽ mất bằng chứng để tìm nguyên nhân boot failure. Phạm vi cleanup cần bám theo ownership và mục tiêu điều tra.

## 14. Checklist trước khi cho phép cleanup tự động

- [ ] Tài nguyên có tag hoặc manifest xác định đúng release và chủ sở hữu.
- [ ] Release đã ở trạng thái failed/canceled và không còn operation cấp phát đang chạy.
- [ ] Tài nguyên không được phiên bản ổn định hoặc workload khác tham chiếu.
- [ ] Dữ liệu cần giữ đã được xác định và có backup/checkpoint phù hợp.
- [ ] Tài nguyên thuộc loại được phép xóa theo allowlist.
- [ ] Thứ tự tháo dependency đã được xác định.
- [ ] Log, event và snapshot cần điều tra đã được lưu.
- [ ] Quyền cleanup bị giới hạn theo phạm vi release.
- [ ] Có dry-run, log kết quả và cơ chế retry/alert.
- [ ] Có bước đối soát để phát hiện tài nguyên mồ côi sau cleanup.

Checklist này nên được chuyển thành policy và kiểm tra tự động ở mức có thể. Các tài nguyên dữ liệu hoặc dùng chung cần cơ chế bảo vệ riêng và phê duyệt phù hợp.

## 15. Nguyên tắc vận hành

1. **Tách khôi phục dịch vụ khỏi dọn tài nguyên:** ưu tiên đưa hệ thống về trạng thái ổn định, sau đó cleanup theo chính sách.
2. **Theo dõi ownership:** dùng release ID, tag, label và manifest để nhận diện tài nguyên thuộc một lần triển khai.
3. **Thiết kế idempotent:** retry không được tạo thêm tài nguyên hoặc side effect ngoài ý muốn.
4. **Đối soát trước khi xóa:** kiểm tra trạng thái provider, dependency và state IaC.
5. **Bảo vệ dữ liệu:** không xóa database, persistent disk, backup hoặc tài nguyên dùng chung chỉ vì deployment thất bại.
6. **Dọn theo thứ tự phụ thuộc:** tháo traffic và workload trước, sau đó mới xử lý tài nguyên nền.
7. **Giữ bằng chứng:** lưu log, event, manifest và snapshot cần thiết trước cleanup.
8. **Xác minh kết quả:** kiểm tra health, phiên bản, dữ liệu, tài nguyên còn lại và chi phí.
9. **Chuẩn bị khi rollback thất bại:** có fallback, escalation và phương án roll forward hoặc compensating action.
10. **Theo dõi tài nguyên mồ côi:** dùng TTL có điều kiện, dry-run và chính sách retention để dọn an toàn.

Rollback và cleanup là hai phần của cùng một quy trình triển khai có khả năng phục hồi. Khi pipeline biết phiên bản ổn định cần khôi phục, biết tài nguyên nào thuộc release và biết dữ liệu nào phải giữ, một lần triển khai thất bại có thể được xử lý có kiểm soát. Điều đó giúp bảo vệ dịch vụ, hạn chế chi phí phát sinh và giữ hạ tầng đám mây ở trạng thái có thể quản lý.
