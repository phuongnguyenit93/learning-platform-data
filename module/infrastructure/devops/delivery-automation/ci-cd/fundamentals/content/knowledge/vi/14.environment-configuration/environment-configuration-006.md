# Nhận diện cấu hình lệch giữa mô tả mong muốn và trạng thái thực

## 1. Cấu hình lệch là gì?

Một hệ thống được vận hành dựa trên nhiều cấu hình: số lượng máy chủ hoặc replica, phiên bản container image, biến môi trường, quyền truy cập, quy tắc mạng, cấu hình database, giới hạn tài nguyên, feature flag và tham số của dịch vụ phụ thuộc. Nhóm thường mô tả những giá trị này trong mã nguồn, tệp cấu hình hoặc công cụ quản lý hạ tầng. Trạng thái đang chạy được hình thành sau khi pipeline triển khai và các thành phần trong môi trường tiếp tục hoạt động.

**Cấu hình lệch (configuration drift)** xảy ra khi trạng thái thực tế của hệ thống khác với trạng thái mà nhóm đã mô tả và phê duyệt. Ví dụ:

- Git khai báo ứng dụng chạy ba replica, nhưng cluster đang có hai replica do ai đó sửa trực tiếp.
- Terraform mô tả security group chỉ mở cổng từ mạng nội bộ, nhưng trên cloud cổng quản trị đã được mở cho Internet.
- Staging dùng image digest đã kiểm thử, còn production chạy một tag đã bị cập nhật sang nội dung khác.
- Biến môi trường PAYMENT_TIMEOUT trong cấu hình mong muốn là 3 giây, nhưng tiến trình đang chạy với giá trị 10 giây.
- Một tài khoản dịch vụ được cấp thêm quyền thủ công và không có thay đổi tương ứng trong repository.
- Một hotfix được thực hiện trực tiếp trên máy chủ nhưng không được đưa trở lại cấu hình được quản lý.

Cấu hình lệch không nhất thiết xuất hiện do thao tác sai. Nó có thể đến từ thay đổi khẩn cấp, thao tác thủ công, tự động mở rộng, cập nhật của nhà cung cấp cloud, controller, default của nền tảng hoặc cấu hình môi trường chưa được mô hình hóa đầy đủ.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, nhận diện và xử lý drift giúp bảo đảm môi trường triển khai phản ánh đúng phiên bản và cấu hình đã được kiểm tra. Nó kết nối quản lý cấu hình, pipeline as code, artifact, môi trường, cổng chất lượng, truy vết và khả năng khôi phục.

## 2. Desired state và actual state

Để phát hiện drift, trước hết phải xác định hai trạng thái đang được so sánh.

- **Desired state (trạng thái mong muốn):** trạng thái được mô tả trong nguồn cấu hình đã được phê duyệt, chẳng hạn Git, Terraform configuration, Helm chart, manifest Kubernetes hoặc hệ thống quản lý cấu hình.
- **Actual state (trạng thái thực):** trạng thái mà hệ thống hoặc nhà cung cấp đang báo cáo tại thời điểm quan sát, chẳng hạn tài nguyên cloud hiện tại, object trong cluster hoặc cấu hình tiến trình đang chạy.

Có thể hình dung:

~~~mermaid
flowchart TD
    A["Git / IaC / cấu hình được duyệt"] --> B["Desired state"]
    B --> C["Deploy hoặc reconcile"]
    C --> D["Môi trường thực"]
    D --> E["Actual state"]
    B --> F["Drift detection"]
    E --> F
    F --> G{"Có khác biệt?"}
    G -- "Không" --> H["Ghi nhận trạng thái đồng bộ"]
    G -- "Có" --> I["Phân loại và đánh giá tác động"]
    I --> J["Phê duyệt cách xử lý"]
    J --> K["Reconcile hoặc cập nhật cấu hình"]
    K --> D
~~~

Một so sánh có ý nghĩa cần cùng phạm vi và cùng thời điểm. Ví dụ, không thể so số replica cố định trong Git với số replica thực tế do autoscaler quản lý mà không tính đến chính sách autoscaling. Tương tự, không nên so cấu hình staging với cấu hình production nếu hai môi trường được phép có khác biệt.

### 2.1. Nguồn sự thật cần được xác định

Mỗi loại cấu hình cần có nguồn sự thật (source of truth) và chủ sở hữu:

| Loại cấu hình | Nguồn mong muốn thường gặp | Trạng thái thực có thể quan sát |
|---|---|---|
| Hạ tầng cloud | Terraform, Pulumi hoặc IaC khác | API và tài nguyên do provider trả về |
| Kubernetes workload | Manifest, Helm, Kustomize, GitOps repository | Object trong API server và Pod đang chạy |
| Ứng dụng | Tệp cấu hình được version hóa, schema và environment overlay | Giá trị ứng dụng đã nạp lúc khởi động hoặc runtime |
| Quyền truy cập | IAM policy, RBAC, policy as code | Quyền thực tế được cấp |
| Container image | Release record và digest được phê duyệt | Image digest đang chạy |
| Feature flag | Hệ thống quản lý flag hoặc cấu hình được kiểm soát | Trạng thái flag đang áp dụng |
| Network và firewall | IaC hoặc policy tập trung | Rule thực tế trên cloud, host hoặc cluster |

Không nên có nhiều nguồn cùng được xem là có quyền quyết định cho một thuộc tính. Nếu Git và thao tác console đều được dùng để sửa cùng một tài nguyên mà không có quy tắc đồng bộ, drift sẽ lặp lại.

## 3. Drift khác với khác biệt môi trường có chủ đích

Không phải mọi khác biệt giữa hai môi trường đều là drift. Staging và production có thể cần cấu hình khác nhau vì tải, quyền, dữ liệu, endpoint và quy mô khác nhau.

Ví dụ:

- Staging có hai replica, production có sáu replica.
- Staging sử dụng dịch vụ thanh toán sandbox, production dùng endpoint thật.
- Production có mức log chi tiết thấp hơn để giảm rủi ro lộ dữ liệu.
- Production dùng quota và giới hạn tài nguyên cao hơn.
- Một feature flag được bật cho nhóm người dùng nhỏ trước khi mở rộng.

Những khác biệt này là hợp lệ khi được mô tả trong cấu hình hoặc policy có kiểm soát. Chúng trở thành drift khi trạng thái thực khác với cấu hình được phê duyệt cho chính môi trường đó.

Nên dùng overlay, biến đầu vào hoặc cấu hình riêng theo môi trường thay vì sửa trực tiếp trên máy chủ sau mỗi lần triển khai.

Ví dụ cấu trúc:

~~~text
config/
  base/
    application.yaml
  environments/
    dev.yaml
    staging.yaml
    production.yaml
~~~

base chứa giá trị dùng chung. Mỗi tệp môi trường chỉ định những khác biệt được phép. Pipeline cần xác định overlay nào được dùng cho môi trường đích và lưu lại định danh cấu hình đã render.

### 3.1. Runtime value có thể thay đổi hợp lệ

Một số giá trị do hệ thống điều khiển trong lúc chạy:

- Replica count được Horizontal Pod Autoscaler điều chỉnh.
- Địa chỉ IP hoặc node được cluster cấp động.
- Timestamp, resource version và status field do Kubernetes quản lý.
- Certificate được tự động gia hạn.
- Token ngắn hạn được xoay vòng.
- Leader hoặc primary instance thay đổi trong hệ thống phân tán.

Nếu bộ phát hiện drift so sánh mọi trường một cách máy móc, nó sẽ báo rất nhiều khác biệt không cần xử lý. Cần xác định trường nào do người vận hành quản lý, trường nào do controller quản lý và trường nào được bỏ qua theo chính sách.

## 4. Các loại cấu hình lệch thường gặp

Có thể phân loại drift theo nơi phát sinh và mức độ ảnh hưởng.

| Loại drift | Biểu hiện | Rủi ro thường gặp |
|---|---|---|
| Hạ tầng | Instance type, network, storage, security group khác IaC | Gián đoạn, chi phí hoặc mở rộng bề mặt tấn công |
| Workload | Image, replica, command, resource limit khác manifest | Chạy sai phiên bản hoặc không ổn định |
| Ứng dụng | Environment variable, feature flag, timeout thay đổi | Hành vi khác với kết quả kiểm thử |
| Bảo mật | IAM, RBAC, firewall hoặc secret policy bị thay đổi | Quyền vượt mức và lộ dữ liệu |
| Dependency/runtime | Phiên bản package, runtime hoặc agent khác dự kiến | Build và production không nhất quán |
| Dữ liệu và schema | Migration hoặc cấu trúc dữ liệu khác trạng thái mong muốn | Không tương thích khi deploy hoặc rollback |
| Quy trình | Thay đổi thủ công không có commit, ticket hoặc release record | Mất khả năng truy vết |

Cũng cần phân biệt drift cấu hình với drift phần mềm. Nếu một container đang chạy image digest khác release record, đó là sai lệch về phiên bản triển khai. Nếu image đúng nhưng environment variable sai, đó là drift cấu hình runtime. Cả hai đều có thể làm hành vi dịch vụ khác với điều đã kiểm thử.

## 5. Drift hình thành từ đâu?

### 5.1. Thay đổi thủ công ngoài pipeline

Quản trị viên có thể sửa tài nguyên qua cloud console, lệnh kubectl edit, SSH hoặc công cụ quản trị database. Những thao tác này có thể cần thiết khi xử lý sự cố, nhưng nếu không được ghi lại trong nguồn cấu hình, trạng thái sẽ lệch.

Cách giảm thiểu là giới hạn quyền sửa trực tiếp, dùng quy trình break-glass cho tình huống khẩn cấp và yêu cầu ghi lại thay đổi để đưa vào Git hoặc IaC sau khi dịch vụ ổn định.

### 5.2. Pipeline và IaC không bao phủ toàn bộ thuộc tính

Nếu một tài nguyên được tạo bằng IaC nhưng một số thuộc tính bị bỏ qua hoặc không được provider quản lý, người vận hành có thể sửa chúng mà công cụ không phát hiện.

Ví dụ, Terraform có thể quản lý network và instance nhưng không quản lý cấu hình bên trong ứng dụng. Khi đó, cần một công cụ hoặc cơ chế khác quản lý application configuration.

### 5.3. Tự động hóa khác cùng sửa một tài nguyên

Autoscaler, operator, controller, policy engine và người vận hành có thể cùng tác động đến một object. Nếu không xác định quyền sở hữu trường, các hệ thống có thể liên tục ghi đè lẫn nhau.

Cần xác định controller nào có quyền quản lý thuộc tính nào và dùng cơ chế field ownership hoặc cấu hình tương đương nếu nền tảng hỗ trợ.

### 5.4. Thay đổi mặc định hoặc phiên bản nền tảng

Nâng cấp Kubernetes, cloud provider, runtime hoặc module có thể thay đổi default, hành vi API hay giá trị được sinh tự động. Nếu cấu hình mong muốn không khai báo rõ các thuộc tính quan trọng, actual state có thể thay đổi theo phiên bản nền tảng.

Đối với thuộc tính có ảnh hưởng bảo mật hoặc vận hành, nên khai báo tường minh và kiểm tra khi nâng cấp.

### 5.5. Hotfix không được đồng bộ trở lại

Một hotfix trực tiếp có thể khôi phục dịch vụ nhanh. Nhưng nếu sau đó pipeline tiếp tục áp dụng cấu hình cũ, thay đổi khẩn cấp có thể bị ghi đè. Hoặc nếu hotfix không được đưa vào Git, drift vẫn tồn tại và tái xuất hiện ở lần tạo môi trường tiếp theo.

Sau khi xử lý sự cố, cần tạo thay đổi chính thức, review và cập nhật nguồn mong muốn.

## 6. Phát hiện drift bằng IaC

Infrastructure as Code cho phép mô tả tài nguyên hạ tầng bằng cấu hình có thể version hóa. Công cụ IaC có thể so sánh mô tả mong muốn với trạng thái tài nguyên mà provider quan sát được.

Với Terraform, cần hiểu vai trò của ba thành phần:

- **Configuration:** khai báo mong muốn trong các tệp cấu hình Terraform.
- **State:** ánh xạ resource trong cấu hình với đối tượng thực mà Terraform quản lý, cùng metadata cần thiết.
- **Remote infrastructure:** tài nguyên hiện đang tồn tại trên provider.

Trong một lần chạy terraform plan thông thường, Terraform refresh thông tin tài nguyên theo khả năng của provider rồi tính toán thay đổi cần thực hiện để đưa hệ thống về configuration. Nếu người khác thay đổi tài nguyên trực tiếp trên cloud, plan có thể hiển thị khác biệt đó.

### 6.1. Xem plan trước khi apply

Ví dụ:

~~~bash
terraform init
terraform plan -out=tfplan
terraform show tfplan
~~~

Plan cho biết công cụ dự kiến tạo, sửa, thay thế hoặc xóa tài nguyên. Cần xem kỹ các hành động destroy/replace, thay đổi IAM, security group, database, storage và public exposure.

Không nên tự động apply mọi plan chỉ vì lệnh chạy thành công. Plan cần được đánh giá theo môi trường, quyền và chính sách thay đổi.

### 6.2. Refresh-only mode

Terraform có chế độ refresh-only để xem hoặc cập nhật state theo trạng thái hiện tại của hạ tầng mà không yêu cầu thay đổi tài nguyên từ configuration.

~~~bash
terraform plan -refresh-only
~~~

Lệnh này giúp xem những thay đổi bên ngoài mà Terraform phát hiện và cách chúng sẽ được phản ánh vào state. Nếu cần cập nhật state sau khi review, có thể dùng:

~~~bash
terraform apply -refresh-only
~~~

Refresh-only cập nhật state để phản ánh actual state; nó không tự sửa hạ tầng trở lại configuration mong muốn. Nếu mục tiêu là khôi phục tài nguyên về desired state, cần xem normal plan và đánh giá các hành động mà Terraform đề xuất.

State có thể chứa dữ liệu nhạy cảm. Cần lưu state trong backend bảo vệ, giới hạn quyền truy cập, mã hóa và tránh in nội dung state hoặc plan có secret ra log công khai.

### 6.3. Plan không phát hiện mọi loại drift

Khả năng phát hiện phụ thuộc provider, resource schema, thuộc tính được quản lý và cách refresh hoạt động. Một số thay đổi không được provider quan sát hoặc không nằm trong phạm vi resource có thể không xuất hiện trong plan.

Do đó, IaC plan cần được kết hợp với kiểm tra cấu hình ứng dụng, policy, cloud security posture và giám sát runtime.

## 7. Phát hiện drift trong Kubernetes và GitOps

Trong Kubernetes, desired state thường nằm trong manifest, Helm chart hoặc Kustomize overlay. Actual state là object mà API server đang lưu và workload thực tế đang chạy.

Các hệ thống GitOps như Argo CD hoặc Flux liên tục so sánh trạng thái trong Git với cluster. Chúng có thể báo:

- **Synced:** trạng thái được quản lý đang khớp với desired state theo quy tắc so sánh.
- **OutOfSync:** có khác biệt cần xem xét.
- **Healthy/Degraded:** tình trạng hoạt động của resource hoặc workload theo health assessment.

Hai khái niệm đồng bộ và sức khỏe khác nhau. Một ứng dụng có thể đồng bộ cấu hình nhưng vẫn không healthy do lỗi ứng dụng. Ngược lại, một workload có thể đang phục vụ request nhưng bị OutOfSync vì ai đó đã thay đổi replica hoặc image thủ công.

### 7.1. Reconciliation

GitOps controller có thể chỉ báo drift hoặc tự động đưa cluster về desired state. Khi bật auto-sync/self-heal, một thay đổi thủ công có thể bị controller ghi đè ở chu kỳ reconcile tiếp theo.

Trước khi bật tự sửa, cần:

- Xác định rõ resource và namespace được controller quản lý.
- Loại trừ các trường do controller khác sở hữu.
- Kiểm tra cách xử lý secret và dữ liệu runtime.
- Có cơ chế review và audit thay đổi Git.
- Đảm bảo thao tác break-glass không bị xóa trước khi nhóm ghi nhận và đánh giá.

Không nên bật tự sửa rộng trên mọi tài nguyên khi chưa hiểu field ownership. Một controller có thể liên tục hoàn tác thay đổi hợp lệ của autoscaler hoặc operator khác nếu hai bên cùng quản lý một trường.

### 7.2. Kiểm tra manifest đã render

Với Helm hoặc Kustomize, nên so sánh đầu ra đã render theo đúng values/overlay của môi trường. Kiểm tra tệp template riêng lẻ có thể bỏ sót giá trị cuối cùng được tạo từ nhiều nguồn.

Cần lưu lại commit, chart version, values và image digest đã dùng để tạo manifest. Nhờ đó, khi cluster lệch, nhóm biết chính xác desired state nào đang được so sánh.

## 8. Phát hiện drift ở cấu hình ứng dụng runtime

Một ứng dụng có thể nhận cấu hình từ nhiều nguồn:

- Tệp cấu hình đóng gói trong artifact.
- Environment variable.
- Secret manager.
- ConfigMap hoặc mounted file.
- Tham số dòng lệnh.
- Hệ thống feature flag.
- Service discovery hoặc remote configuration.

Để phát hiện drift, cần xác định giá trị hiệu lực mà ứng dụng đang sử dụng và so sánh với giá trị mong muốn sau khi áp dụng overlay môi trường.

Ví dụ, cấu hình khai báo:

~~~yaml
service:
  timeout: 3s
  retry:
    maxAttempts: 2
  featureFlags:
    newCheckout: false
~~~

Nhưng tiến trình thực tế có thể nhận SERVICE_TIMEOUT=10s từ environment variable. Nếu ứng dụng ưu tiên biến môi trường, giá trị hiệu lực là 10 giây. Chỉ kiểm tra file YAML sẽ không phát hiện khác biệt.

Một số cách tăng khả năng quan sát:

- Ứng dụng cung cấp endpoint hoặc lệnh hiển thị cấu hình hiệu lực đã loại bỏ secret.
- Ghi nhận config version hoặc checksum khi khởi động.
- Đưa version và environment vào log/metrics.
- Kiểm tra các biến bắt buộc và giá trị trong phạm vi cho phép.
- Theo dõi thay đổi feature flag và người thực hiện.
- Không ghi giá trị secret vào log hoặc endpoint chẩn đoán.

Cần phân biệt cấu hình đã nạp lúc khởi động với cấu hình đang được đọc động. Nếu ứng dụng chỉ đọc environment variable khi khởi động, thay đổi biến trên orchestrator có thể chưa có hiệu lực cho đến khi Pod được tạo lại.

## 9. So sánh có kiểm soát: chuẩn hóa và bỏ qua trường động

So sánh desired và actual không nên là phép so sánh văn bản đơn giản. Hai cấu hình có thể khác thứ tự trường hoặc định dạng nhưng mang cùng ý nghĩa. Ngược lại, hai file giống nhau có thể tạo ra hành vi khác do default hoặc biến được nạp từ nguồn khác.

Một quy trình so sánh tốt cần:

1. Parse dữ liệu về cấu trúc có kiểu.
2. Chuẩn hóa giá trị mặc định và thứ tự nếu phù hợp.
3. Áp dụng overlay của đúng môi trường.
4. Loại bỏ hoặc đánh dấu trường do controller quản lý.
5. Chuẩn hóa giá trị động như timestamp, IP được cấp tự động hoặc resource version.
6. So sánh những trường có ý nghĩa vận hành và bảo mật.
7. Xuất diff có ngữ cảnh, không chứa secret.

Không nên bỏ qua quá nhiều trường để giảm cảnh báo. Các trường bị ignore cần có lý do, chủ sở hữu và được review định kỳ. Nếu ignore image, securityContext hoặc serviceAccount một cách rộng rãi, bộ phát hiện drift có thể bỏ lỡ thay đổi quan trọng.

## 10. Phân loại drift theo mức độ và hành động

Không phải mọi drift đều cần tự động sửa. Cần phân loại trước khi chọn cách xử lý.

| Mức | Ví dụ | Hành động gợi ý |
|---|---|---|
| Nghiêm trọng | Mở cổng quản trị ra Internet, cấp quyền admin ngoài chính sách, image digest không được phê duyệt | Cảnh báo ưu tiên cao, chặn promotion hoặc cô lập theo runbook |
| Cao | Sai cấu hình database, thiếu mã hóa storage, sai phiên bản workload | Tạo incident/change request và yêu cầu xử lý sớm |
| Trung bình | Timeout, replica hoặc resource limit lệch ngoài phạm vi cho phép | Đưa vào backlog có thời hạn và người chịu trách nhiệm |
| Thấp | Label, annotation hoặc metadata không ảnh hưởng hành vi | Ghi nhận và xử lý trong đợt chuẩn hóa |
| Được phép | Replica do autoscaler thay đổi trong giới hạn | Không xem là vi phạm; tiếp tục quan sát theo policy |

Mức độ cần dựa trên tác động, khả năng khai thác, phạm vi ảnh hưởng và yêu cầu dịch vụ. Một thay đổi nhỏ về label có thể ít rủi ro, nhưng thay đổi tương tự trong một nhãn được dùng cho network policy có thể ảnh hưởng bảo mật.

### 10.1. Trạng thái không rõ không đồng nghĩa với đạt

Nếu API không truy cập được, provider trả lỗi hoặc công cụ không đủ quyền đọc, hệ thống chưa có bằng chứng rằng actual state khớp desired state.

Cần phân biệt:

- **PASS:** đã so sánh đủ phạm vi và không có drift bị chính sách chặn.
- **DRIFT_FOUND:** phát hiện khác biệt cần phân loại.
- **UNKNOWN/ERROR:** không thể kiểm tra hoặc thiếu dữ liệu.
- **EXEMPTED:** khác biệt đã được phê duyệt là có chủ đích và còn hiệu lực.

Không nên chuyển UNKNOWN thành PASS chỉ để pipeline không bị chặn. Chính sách có thể cho phép một số công việc không quan trọng tiếp tục khi hệ thống phát hiện lỗi, nhưng phải ghi nhận rõ trạng thái và không cấp nhầm bằng chứng tuân thủ.

## 11. Xử lý drift: cập nhật desired state hay khôi phục actual state?

Khi phát hiện drift, có hai hướng xử lý chính:

**Cập nhật desired state:** nếu thay đổi thực tế là hợp lệ, có chủ đích và được phê duyệt, đưa thay đổi đó vào Git/IaC, review và triển khai theo pipeline. Đây là cách biến một hotfix thành cấu hình chính thức.

**Khôi phục actual state:** nếu thay đổi thực tế không được phép hoặc không mong muốn, đưa hệ thống trở lại cấu hình đã phê duyệt bằng pipeline hoặc controller. Cần xác minh tác động trước khi áp dụng.

Quy trình xử lý nên gồm:

1. Xác định tài nguyên, thuộc tính và môi trường bị lệch.
2. Thu thập diff, thời điểm phát hiện, người hoặc hệ thống có thể đã thay đổi.
3. Đánh giá tác động đến bảo mật, tính sẵn sàng, dữ liệu và người dùng.
4. Xác định thay đổi có chủ đích hay ngoài quy trình.
5. Chọn cập nhật desired state hoặc khôi phục actual state.
6. Tạo change request/pull request nếu cần và lấy phê duyệt phù hợp.
7. Áp dụng qua công cụ quản lý cấu hình.
8. Chạy lại drift detection và xác minh dịch vụ.
9. Ghi nguyên nhân và biện pháp ngăn tái diễn.

Không nên chạy apply hoặc bật self-heal một cách mù quáng ngay khi thấy drift. Một thay đổi thủ công có thể là hotfix đang ngăn sự cố lớn hơn; tự động hoàn tác trước khi hiểu bối cảnh có thể gây gián đoạn.

## 12. Ngăn drift tái diễn

Phát hiện drift là cần thiết nhưng chưa đủ. Cần giảm khả năng thay đổi ngoài nguồn sự thật.

### 12.1. Quản lý thay đổi qua Git

- Lưu IaC, manifest và cấu hình ứng dụng trong repository có review.
- Dùng pull request cho thay đổi quan trọng.
- Bảo vệ nhánh và yêu cầu status check.
- Lưu lịch sử phê duyệt và commit.
- Dùng module hoặc template dùng chung để giảm cấu hình tùy tiện.
- Không để tệp cấu hình production chỉ tồn tại trên máy cá nhân.

### 12.2. Giới hạn thay đổi trực tiếp

- Dùng RBAC/IAM để giới hạn quyền chỉnh sửa.
- Dùng quyền read-only cho vai trò chỉ quan sát.
- Tách quyền triển khai khỏi quyền quản trị toàn bộ tài nguyên.
- Dùng break-glass access cho tình huống khẩn cấp.
- Ghi log mọi thao tác thay đổi và rà soát sau sự cố.
- Thu hồi quyền tạm sau khi hoàn tất.

### 12.3. Tự động reconcile có kiểm soát

GitOps controller hoặc công cụ cấu hình có thể tự động đưa actual state về desired state. Trước khi bật, cần xác định phạm vi quản lý, field ownership, cửa sổ thay đổi và cơ chế rollback.

Đối với tài nguyên có stateful data hoặc thay đổi khó đảo ngược, có thể chỉ bật cảnh báo và yêu cầu người duyệt thay vì tự động sửa.

### 12.4. Kiểm tra định kỳ

Drift có thể xuất hiện sau khi pipeline đã hoàn tất. Do đó, chỉ chạy kiểm tra lúc deploy sẽ bỏ sót thay đổi xảy ra nhiều giờ hoặc nhiều ngày sau đó.

Có thể chạy kiểm tra:

- Trong pull request để kiểm tra cấu hình mong muốn.
- Trước khi apply hoặc deploy.
- Sau triển khai.
- Theo lịch định kỳ.
- Sau sự kiện bảo mật hoặc thay đổi quyền.
- Trước khi mở rộng rollout hoặc phát hành phiên bản mới.

Tần suất cần dựa trên rủi ro và khả năng của công cụ. Tài nguyên có quyền cao hoặc dữ liệu quan trọng nên được kiểm tra thường xuyên hơn.

## 13. Đưa drift detection vào CI/CD

Pipeline có thể sử dụng các bước khác nhau tùy loại môi trường:

~~~mermaid
flowchart TD
    A["Pull request thay đổi IaC hoặc manifest"] --> B["Format, validate và policy check"]
    B --> C["Plan / render / diff"]
    C --> D{"Kết quả có hợp lệ?"}
    D -- "Không" --> E["Chặn merge và trả báo cáo"]
    D -- "Có" --> F["Review và phê duyệt"]
    F --> G["Apply hoặc deploy"]
    G --> H["Post-deploy verification"]
    H --> I["Drift check theo lịch"]
    I --> J{"Actual khớp desired?"}
    J -- "Có" --> K["Ghi nhận PASS"]
    J -- "Không" --> L["Phân loại drift và tạo cảnh báo"]
    L --> M["Cập nhật desired hoặc reconcile"]
    M --> I
~~~

Một pipeline drift detection nên:

- Dùng đúng workspace, state backend, cluster context và environment.
- Có quyền đọc đủ để quan sát nhưng không có quyền ghi nếu chỉ kiểm tra.
- Không in secret hoặc state nhạy cảm ra log.
- Ghi commit, tool version, thời điểm và phạm vi kiểm tra.
- Phân biệt drift thực với trường động hoặc trường do controller quản lý.
- Trả trạng thái UNKNOWN khi không thể kiểm tra.
- Chỉ tự động sửa những loại drift đã được đánh giá và cho phép.

### 13.1. Tách detect khỏi remediate

Một thiết kế an toàn thường tách hai job:

- **Detect:** chỉ đọc actual state, tạo diff và báo cáo.
- **Remediate:** có quyền thay đổi, chạy sau khi được phê duyệt hoặc theo policy tự động đã xác định.

Sự tách biệt này giảm rủi ro một lỗi trong logic so sánh lập tức làm thay đổi production. Nó cũng giúp người vận hành xem được kế hoạch trước khi hệ thống thực hiện.

## 14. Ví dụ thực tế: drift của security group trên cloud

Giả sử Terraform mô tả security group chỉ cho phép kết nối HTTPS từ load balancer. Trong một lần điều tra, quản trị viên mở thêm cổng SSH từ mọi địa chỉ để truy cập máy chủ.

Sau thao tác này:

1. Actual state trên cloud khác với Terraform configuration.
2. Lần terraform plan tiếp theo phát hiện rule bổ sung.
3. Drift report cho biết cổng, nguồn truy cập và tài nguyên bị thay đổi.
4. Nhóm đánh giá liệu đây có phải thao tác break-glass được phê duyệt không.
5. Nếu thay đổi không còn cần thiết, nhóm loại bỏ rule ngoài chính sách qua IaC.
6. Nếu cần truy cập quản trị lâu dài, nhóm thiết kế lại qua VPN, bastion hoặc cơ chế truy cập được phê duyệt rồi cập nhật configuration.
7. Pipeline chạy plan, policy check và apply theo quy trình.
8. Một lần drift check sau đó xác nhận security group đã khớp với desired state.

Ví dụ này cho thấy drift detection vừa giúp phát hiện thay đổi ngoài quy trình, vừa tạo bằng chứng để cải thiện thiết kế truy cập.

## 15. Ví dụ thực tế: Kubernetes chạy sai image

Giả sử GitOps repository khai báo:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: checkout
          image: registry.example.invalid/checkout@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
~~~

Nhưng một người vận hành sửa deployment trực tiếp để dùng image tag latest. Cluster vẫn có thể chạy bình thường, nhưng trạng thái thực không còn tương ứng với release đã được review.

Cần xác minh:

- Image digest thực tế của Pod.
- Lịch sử thay đổi Deployment.
- Ai hoặc controller nào đã sửa object.
- Tag latest trỏ đến digest nào tại thời điểm pull.
- Image có provenance và kết quả scan hợp lệ không.

Nếu GitOps controller được cấu hình self-heal, nó có thể đưa image về digest đã khai báo. Sau đó cần xác minh Pod mới đã chạy đúng digest và health check đạt. Nếu thay đổi là một hotfix hợp lệ, nhóm cần đưa digest mới vào Git qua pull request và chạy lại các cổng chất lượng.

## 16. Ví dụ mã giả cho drift report

Một báo cáo drift nên tập trung vào thuộc tính cần xử lý, thay vì dump toàn bộ cấu hình.

~~~yaml
drift_report:
  environment: production
  checked_at: "2026-11-18T08:30:00Z"
  source_revision: "4f8c2a1"
  scope: "network/security-groups"

  summary:
    status: DRIFT_FOUND
    blocking_findings: 1
    advisory_findings: 1

  findings:
    - resource: "checkout-admin-sg"
      attribute: "ingress.ssh.source"
      desired: "10.20.0.0/16"
      actual: "0.0.0.0/0"
      severity: critical
      action: "review-and-remediate"

    - resource: "checkout-api"
      attribute: "replicas"
      desired: "managed-by-autoscaler"
      actual: 5
      severity: informational
      action: "ignore-by-approved-policy"
~~~

Báo cáo không nên chứa secret, private key, token hoặc toàn bộ state. Giá trị actual cần được làm sạch nếu có dữ liệu nhạy cảm. Với thuộc tính được autoscaler quản lý, policy cần thể hiện rõ phạm vi và lý do không xem là vi phạm.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra drift lúc deploy | Drift phát sinh sau triển khai không được phát hiện | Chạy kiểm tra định kỳ và sau thay đổi nhạy cảm |
| Coi mọi khác biệt là lỗi | Nhiều cảnh báo giả do giá trị động hoặc controller | Chuẩn hóa và khai báo field ownership |
| Tự động apply mọi drift | Có thể hoàn tác hotfix hoặc gây downtime | Phân loại, review và tách detect/remediate |
| Sửa trực tiếp production nhưng không cập nhật Git | Drift tái xuất hiện ở lần deploy sau | Đồng bộ thay đổi về source of truth |
| Dùng nhiều nguồn sự thật | Các công cụ ghi đè lẫn nhau | Chỉ định owner cho từng loại cấu hình |
| Bỏ qua lỗi kiểm tra vì thiếu quyền | Trạng thái UNKNOWN bị hiểu nhầm thành PASS | Phân biệt lỗi quan sát với kết quả đạt |
| So sánh staging với production | Khác biệt hợp lệ bị báo nhầm | So sánh actual với desired của chính môi trường |
| In toàn bộ state hoặc runtime config | Có thể lộ secret | Redact và chỉ xuất diff cần thiết |
| Bỏ qua thay đổi của IAM/network | Tăng rủi ro bảo mật âm thầm | Đặt mức nghiêm trọng và cảnh báo riêng |
| Không ghi nhận ngoại lệ | Không biết drift nào được chấp nhận và đến khi nào | Có owner, lý do và thời hạn cho exception |

## 18. Checklist quản lý cấu hình lệch

**Nguồn mong muốn**

- [ ] Mỗi loại cấu hình có source of truth và owner rõ ràng.
- [ ] Desired state được lưu trong Git hoặc hệ thống quản lý có version.
- [ ] Khác biệt theo môi trường được khai báo tường minh.
- [ ] Trường động và trường do controller quản lý được xác định.

**Phát hiện**

- [ ] Có công cụ so sánh desired state với actual state.
- [ ] Kiểm tra bao phủ hạ tầng, workload và cấu hình runtime phù hợp.
- [ ] Có kiểm tra trong pipeline và theo lịch.
- [ ] Báo cáo gắn với commit, môi trường và thời điểm.
- [ ] Trạng thái không thể kiểm tra được ghi là UNKNOWN/ERROR.

**Xử lý**

- [ ] Drift được phân loại theo tác động.
- [ ] Có quy trình cập nhật desired state hoặc khôi phục actual state.
- [ ] Detect và remediate được phân quyền phù hợp.
- [ ] Thay đổi khẩn cấp có break-glass và review sau đó.
- [ ] Có xác minh sau khi xử lý và ghi nhận nguyên nhân.

**Bảo mật và vận hành**

- [ ] Quyền sửa trực tiếp được giới hạn và audit.
- [ ] State, secret và runtime config không bị lộ trong log.
- [ ] Có chính sách exception với owner và thời hạn.
- [ ] Có cảnh báo cho drift liên quan IAM, network và image.
- [ ] Có cách ngăn controller hoặc automation ghi đè lẫn nhau.

## 19. Kết luận

Cấu hình lệch là khoảng cách giữa trạng thái được phê duyệt và trạng thái hệ thống đang thực thi. Muốn nhận diện đúng, nhóm phải xác định nguồn sự thật, phân biệt khác biệt có chủ đích với drift, hiểu những trường do controller hoặc hệ thống tự động quản lý và so sánh đúng phạm vi môi trường.

IaC plan, GitOps diff, runtime configuration checks và kiểm tra định kỳ cung cấp các góc nhìn bổ sung. Khi phát hiện khác biệt, nhóm cần phân loại tác động rồi quyết định cập nhật desired state hay khôi phục actual state. Việc tách phát hiện khỏi tự động sửa, lưu bằng chứng và đưa hotfix trở lại nguồn cấu hình giúp môi trường duy trì tính nhất quán, truy vết và khả năng khôi phục trong toàn bộ vòng đời CI/CD.
