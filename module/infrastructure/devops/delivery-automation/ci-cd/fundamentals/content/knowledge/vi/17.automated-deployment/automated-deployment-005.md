# Kiểm tra điều kiện trước khi triển khai và quyền truy cập đích

Một pipeline có thể build và kiểm thử thành công nhưng vẫn chưa đủ điều kiện để triển khai. Artifact có thể sai phiên bản, môi trường đích đang mất ổn định, cấu hình chưa đầy đủ, schema chưa tương thích hoặc danh tính của job không có quyền thực hiện thao tác cần thiết. Nếu chỉ phát hiện những vấn đề này giữa lúc triển khai, hệ thống có thể rơi vào trạng thái dở dang hoặc gây gián đoạn dịch vụ.

Trước khi thay đổi môi trường, pipeline cần thực hiện một bước preflight để xác minh cả hai nhóm điều kiện: môi trường có sẵn sàng nhận thay đổi không và workload có đúng danh tính, quyền hạn để thay đổi môi trường đó không. Các kiểm tra phải gắn với artifact và target cụ thể, có kết quả rõ ràng, có thể truy vết và được thực hiện đủ gần thời điểm triển khai để tránh dùng kết quả đã cũ.

Bài học này thuộc phần triển khai tự động của CI/CD. Nó kết nối artifact đã được xác minh, cấu hình môi trường, danh tính workload và cơ chế bảo vệ môi trường thành một cổng quyết định trước khi deploy.

## 1. Vì sao cần pre-deployment gate?

Pre-deployment gate là tập hợp điều kiện phải đạt trước khi pipeline được phép bắt đầu thay đổi môi trường đích. Gate có thể kiểm tra tự động, yêu cầu phê duyệt của con người hoặc kết hợp cả hai.

Một số lỗi điển hình mà gate cần phát hiện:

- Artifact không thuộc commit hoặc release dự kiến.
- Digest hoặc chữ ký artifact không khớp với metadata tin cậy.
- Artifact chưa qua kiểm tra bắt buộc hoặc có lỗ hổng vượt ngưỡng chính sách.
- Môi trường đích đang có sự cố, quá tải hoặc trong thời gian bảo trì.
- Phiên bản runtime, database schema hoặc API không tương thích.
- Thiếu cấu hình bắt buộc hoặc secret cần thiết.
- Job đang nhắm nhầm cluster, namespace, account, region hoặc tenant.
- Danh tính deployer không có quyền cần thiết hoặc có quyền vượt quá phạm vi công việc.
- Một release khác đang thay đổi cùng tài nguyên.
- Chưa có approval hoặc change record theo chính sách.

Nếu gate chỉ kiểm tra một trạng thái tổng quát như "CI xanh", nó không chứng minh artifact và môi trường đích cụ thể đã sẵn sàng. Một pipeline cần biết chính xác nó sẽ triển khai artifact nào, vào đâu, bằng danh tính nào và với thao tác gì.

## 2. Phân biệt điều kiện triển khai và quyền truy cập

Hai nhóm kiểm tra có liên quan nhưng không thay thế nhau.

**Điều kiện triển khai** trả lời: "Có nên thực hiện thay đổi này vào lúc này không?" Ví dụ artifact đã được verify, môi trường khỏe, cấu hình hợp lệ, migration tương thích và approval đã đạt.

**Quyền truy cập đích** trả lời: "Danh tính của job có được phép thực hiện chính xác thao tác này trên tài nguyên đó không?" Ví dụ job có quyền cập nhật Deployment trong namespace staging nhưng không có quyền xóa Secret hoặc thay đổi namespace production.

Một môi trường có thể sẵn sàng nhưng job không có quyền deploy. Ngược lại, job có quyền deploy vẫn có thể bị gate từ chối vì môi trường đang trong maintenance hoặc artifact chưa đạt chất lượng.

Cần giữ cả hai điều kiện độc lập. Không dùng approval của con người để thay thế kiểm tra quyền máy, và không xem việc xác thực thành công là bằng chứng rằng release đã an toàn để triển khai.

## 3. Xác định rõ deployment request

Trước khi kiểm tra, pipeline cần có một deployment request đủ thông tin để mọi bước cùng đánh giá một mục tiêu thống nhất.

Một request thường bao gồm:

- Tên ứng dụng hoặc service.
- Môi trường đích: development, staging hoặc production.
- Cluster/account/region/namespace/tenant đích.
- Artifact name, version và digest.
- Source commit và build run đã tạo artifact.
- Phiên bản cấu hình hoặc manifest triển khai.
- Loại thao tác: deploy mới, cập nhật, migration, rollback hoặc scale.
- Danh tính workload dự kiến thực hiện.
- Change ID hoặc approval record nếu có.
- Deployment strategy và các giới hạn rollout.

Không nên lấy target từ một chuỗi tự do do người dùng nhập vào mà không xác thực. Một typo trong tên namespace hoặc account có thể khiến pipeline triển khai sang nơi không mong muốn. Hãy dùng lựa chọn được định nghĩa trước, allowlist hoặc mapping có kiểm soát từ environment sang target.

Ví dụ, lựa chọn production phải ánh xạ tới đúng account, cluster và namespace production. Không để script tự suy ra target từ tên branch hoặc một biến không được kiểm soát.

## 4. Nhóm điều kiện cần kiểm tra

Một preflight đầy đủ có thể được chia thành các nhóm sau:

| Nhóm | Câu hỏi | Ví dụ bằng chứng |
|---|---|---|
| Artifact | Đúng gói đã được phê duyệt chưa? | Version, digest, signature, provenance |
| Chất lượng | Các kiểm tra bắt buộc đã đạt chưa? | Test report, scan, quality gate |
| Môi trường | Target có sẵn sàng nhận thay đổi không? | Health, capacity, maintenance state |
| Tương thích | Phiên bản mới có tương thích với runtime và dependency không? | Runtime matrix, schema compatibility |
| Cấu hình | Các giá trị cần thiết đã có và hợp lệ chưa? | Config validation, secret reference |
| Phụ thuộc | Database, broker, network hoặc dịch vụ cần thiết có sẵn không? | Health/readiness và dependency checks |
| Quyền | Job có đúng quyền trên đúng target không? | Identity claims, IAM/RBAC check |
| Điều phối | Có release khác đang thao tác cùng target không? | Lock, deployment queue |
| Chính sách | Có approval, change window hoặc điều kiện compliance không? | Approval record, policy result |
| Phục hồi | Có phương án rollback hoặc forward-fix khả thi không? | Previous version, backup, rollback plan |

Không phải mọi ứng dụng đều cần mọi kiểm tra. Nhóm cần chọn theo loại hệ thống, mức độ ảnh hưởng và rủi ro của thay đổi. Nhưng các điều kiện bắt buộc cần được viết rõ để gate có thể quyết định nhất quán.

## 5. Xác minh artifact trước khi nhắm tới môi trường

Artifact được triển khai phải là artifact đã được tạo và kiểm tra trong pipeline. Không build lại một phiên bản khác ở bước deploy chỉ vì cần cấu hình khác cho production.

Các kiểm tra thường gồm:

- Version hoặc release identifier đúng với deployment request.
- Digest khớp với release metadata.
- Signature và provenance hợp lệ theo chính sách nếu được yêu cầu.
- Artifact được tạo từ repository và revision được phép.
- Các test bắt buộc, security scan và quality gate đã đạt.
- Artifact có đúng biến thể OS/architecture/runtime.
- Package hoặc image có thể tải được từ registry đích.

Với container image, nên tham chiếu digest thay vì chỉ dùng tag có thể thay đổi. Với JAR hoặc ZIP, kiểm tra checksum theo metadata tin cậy. Chỉ xác minh checksum tải cùng file từ một nguồn không tin cậy có thể không đủ nếu cả hai đều bị thay thế.

Gate nên ghi lại artifact digest đã kiểm tra và chuyển đúng định danh đó sang bước deploy. Nếu artifact thay đổi sau preflight, kết quả gate cũ không còn áp dụng.

## 6. Kiểm tra sức khỏe và trạng thái môi trường đích

Trước khi deploy, cần biết môi trường đích đang ở trạng thái nào. Một số kiểm tra phổ biến:

- Control plane hoặc API endpoint có truy cập được không?
- Service hiện tại có đang khỏe hay đang trong incident?
- Có đủ CPU, memory, disk, pod quota hoặc connection capacity không?
- Database và message broker có sẵn sàng không?
- Có đang chạy maintenance hoặc backup quan trọng không?
- Có deployment khác đang rollout hoặc migration không?
- Môi trường có đang ở trạng thái degraded cần giữ nguyên để điều tra không?

Health check nên dựa trên tín hiệu có ý nghĩa với quyết định triển khai. Một HTTP endpoint trả 200 không nhất thiết chứng minh database, queue hoặc downstream dependency đều khỏe. Nếu service đang có incident, thay đổi mới có thể làm khó việc xác định nguyên nhân hoặc tăng tải lên hệ thống.

Không nên dùng một ngưỡng capacity chung cho mọi ứng dụng. Cần xét request/limit, autoscaling, số replica, tài nguyên còn lại và khả năng chịu tải của dependency. Nếu rollout cần chạy đồng thời old và new replica, môi trường phải có đủ tài nguyên cho giai đoạn overlap đó.

## 7. Kiểm tra tương thích runtime và dependency

Một artifact hợp lệ vẫn có thể không chạy được trong môi trường đích nếu runtime hoặc dependency không tương thích.

Với ứng dụng Java, có thể cần kiểm tra:

- Phiên bản JRE/JDK được hỗ trợ.
- Phiên bản hệ điều hành và thư viện native.
- Database driver và phiên bản database.
- Schema hiện tại và schema sau migration.
- Các API hoặc message schema mà service khác đang sử dụng.
- CPU architecture và base image.
- Phiên bản sidecar, agent hoặc service mesh nếu có.

Kiểm tra tương thích cần xem cả thay đổi ứng dụng lẫn trạng thái hiện tại của môi trường. Một migration chỉ thêm cột nullable có thể tương thích với phiên bản cũ; xóa hoặc đổi tên cột ngay trong cùng release có thể làm phiên bản cũ đang chạy lỗi trước khi rollout hoàn tất.

Ưu tiên chiến lược expand-and-contract cho thay đổi schema có nhiều phiên bản ứng dụng cùng tồn tại: thêm cấu trúc mới, triển khai code tương thích, chuyển dữ liệu và usage, sau đó mới loại bỏ cấu trúc cũ trong một release sau.

Nếu không thể chứng minh tương thích, gate nên dừng hoặc yêu cầu một kế hoạch migration riêng. Không giả định build thành công đồng nghĩa với runtime tương thích.

## 8. Kiểm tra cấu hình và secret reference

Cấu hình phải hợp lệ trước khi ứng dụng được cập nhật. Các kiểm tra có thể bao gồm:

- Biến bắt buộc đã được khai báo.
- Giá trị có đúng định dạng, enum và giới hạn.
- URL trỏ đúng service hoặc environment.
- Port và hostname có thể truy cập.
- ConfigMap hoặc configuration bundle tồn tại.
- Secret reference tồn tại và workload runtime có thể đọc.
- Feature flag và cấu hình rollout phù hợp.
- Không có giá trị mặc định nguy hiểm bị dùng nhầm ở production.

Pipeline deploy thường không cần đọc nội dung secret. Nó có thể kiểm tra reference, quyền truy cập hoặc trạng thái tồn tại theo cơ chế được phép mà không in secret ra log. Ứng dụng hoặc workload runtime mới là thành phần tiêu thụ secret khi chạy.

Cần tách quyền đọc secret khỏi quyền cập nhật deployment. Ví dụ, deployer có thể được phép cập nhật Deployment tham chiếu tới một Secret đã tồn tại mà không cần quyền đọc giá trị của Secret đó. Điều này giảm khả năng credential bị lộ qua job deploy.

Không ghi secret vào manifest đã lưu trong artifact nếu manifest đó được chia sẻ rộng. Dùng secret manager, workload identity hoặc cơ chế injection của nền tảng tại thời điểm chạy.

## 9. Kiểm tra dependency và điều kiện vận hành

Một deployment có thể cần nhiều hệ thống sẵn sàng trước khi bắt đầu:

- Database có thể nhận kết nối và migration có thể chạy an toàn.
- Message broker có đủ quota hoặc topic đã được tạo.
- Registry có thể phục vụ image/package.
- DNS, network policy, firewall và service endpoint cho phép kết nối.
- Secret manager có thể cấp credential cho workload runtime.
- Certificate còn hiệu lực và trust chain hợp lệ.
- Monitoring, logging và alerting có thể nhận tín hiệu từ phiên bản mới.

Không phải tất cả dependency đều phải được gọi từ runner. Một số kiểm tra cần thực hiện từ network hoặc identity của môi trường đích vì runner có thể có đường mạng và quyền khác ứng dụng. Ví dụ, runner tải được image không có nghĩa node trong cluster có quyền pull image đó.

Với dependency chỉ workload mới truy cập, cần kiểm tra bằng cơ chế phù hợp như pre-deployment probe, canary hoặc post-deployment verification. Tránh cấp thêm quyền production cho runner chỉ để kiểm tra một đường mạng mà workload runtime mới sử dụng.

## 10. Xác thực và phân quyền tại target

Khi truy cập môi trường đích, pipeline cần chứng minh danh tính và được cấp đúng quyền.

**Authentication** xác minh job là ai. Có thể dùng OIDC federation, workload identity, service account hoặc credential do nền tảng cấp.

**Authorization** quyết định danh tính đó được phép thực hiện thao tác nào trên tài nguyên nào. Ví dụ, role có thể cho phép cập nhật Deployment trong namespace staging nhưng không cho phép tạo RoleBinding hoặc đọc Secret.

Không nên dùng một kubeconfig, cloud access key hoặc service account có quyền quản trị cho mọi pipeline. Một danh tính build, một danh tính publish và một danh tính deploy có nhu cầu khác nhau. Tách chúng giúp giới hạn phạm vi ảnh hưởng khi một job bị xâm nhập hoặc cấu hình sai.

Cần xác minh target identity sau khi xác thực. Một token hợp lệ nhưng được ánh xạ nhầm sang account hoặc cluster khác vẫn có thể dẫn đến thao tác nguy hiểm. Trước khi deploy, pipeline nên kiểm tra account/project, cluster endpoint, namespace và environment label theo allowlist đã định.

## 11. Dùng credential ngắn hạn khi có thể

Nếu nền tảng CI và cloud hỗ trợ, ưu tiên workload identity federation/OIDC thay vì lưu access key dài hạn.

Luồng phổ biến:

1. Job yêu cầu ID token từ issuer của nền tảng CI.
2. Nhà cung cấp đích kiểm tra issuer, audience, subject và các claim.
3. Trust policy ánh xạ workload được phép sang role.
4. Job nhận access token ngắn hạn.
5. IAM policy giới hạn thao tác và tài nguyên.
6. Token hết hạn sau khoảng thời gian được cấp.

Trust policy nên ràng buộc repository, branch/tag, workflow và environment nếu issuer cung cấp các claim đó. Không nên chỉ tin mọi job từ một tổ chức hoặc mọi branch trong repository nếu chỉ một release workflow được phép deploy production.

Token ngắn hạn vẫn có thể bị lạm dụng khi còn hiệu lực. Vì vậy, chỉ cấp token ở job cần dùng, giữ runner cô lập, không log token và không truyền token qua artifact/output. Nếu nền tảng chưa hỗ trợ federation, dùng credential trong secret store với quyền tối thiểu, owner và lịch xoay vòng rõ ràng.

## 12. Phân quyền theo môi trường và nhiệm vụ

Quyền deploy staging và production nên được tách riêng. Một job test không nên nhận quyền thay đổi production chỉ vì cùng nằm trong một workflow.

| Danh tính | Môi trường | Quyền |
|---|---|---|
| staging-deployer | Staging | Cập nhật ứng dụng trong namespace staging |
| production-deployer | Production | Cập nhật ứng dụng production sau approval |
| migration-runner | Database đích | Chạy migration được phê duyệt, phạm vi schema cụ thể |
| release-reader | Artifact registry | Đọc artifact theo digest |
| build-publisher | Artifact registry | Push artifact vào repository được chỉ định |

Nên cấp quyền tối thiểu theo action và resource. Không cấp cluster-admin, owner toàn cloud account hoặc quyền đọc mọi secret chỉ để làm cho pipeline chạy được.

Tách quyền cũng giúp audit rõ hơn: thao tác nào do deployer thực hiện, thao tác nào do migration runner thực hiện và thao tác nào do publisher thực hiện. Nếu một job cần nhiều quyền, cân nhắc tách thành các bước hoặc identity riêng thay vì gộp mọi quyền vào một role lớn.

## 13. Kiểm tra quyền Kubernetes trước khi triển khai

Với Kubernetes, lệnh kubectl auth can-i cho phép kiểm tra danh tính hiện tại có được phép thực hiện một verb trên resource trong namespace cụ thể hay không.

Ví dụ:

```bash
kubectl auth can-i create deployments --namespace staging
kubectl auth can-i patch deployments --namespace staging
kubectl auth can-i get deployments --namespace staging
kubectl auth can-i watch deployments --namespace staging
kubectl auth can-i get pods --namespace staging
```

Các lệnh này kiểm tra quyền của identity hiện tại. Chúng không tự xác minh rằng identity đang trỏ tới đúng cluster hoặc đúng account. Vì vậy, trước đó cần kiểm tra context, API endpoint và namespace theo cấu hình được phép.

Có thể kiểm tra danh tính và target bằng các lệnh chỉ đọc:

```bash
kubectl config current-context
kubectl cluster-info
kubectl get namespace staging
```

Không in toàn bộ kubeconfig hoặc token ra log. Lệnh kubectl config current-context chỉ hiển thị tên context; tên đó nên được so sánh với allowlist hoặc cấu hình target dự kiến. Tên context có thể tùy ý đặt, nên với yêu cầu cao cần xác minh thêm cluster endpoint hoặc cloud account thông qua công cụ quản trị tương ứng.

Nếu pipeline dùng Helm, Argo CD hoặc một deployment controller, quyền cần thiết có thể khác so với kubectl apply. Kiểm tra đúng API/resource mà công cụ thực sự sử dụng. Không mở rộng quyền sang Secrets hoặc các resource khác nếu không có nhu cầu đã được xác minh.

## 14. Ví dụ RBAC giới hạn deploy trong một namespace

Một ServiceAccount dành cho deploy staging có thể được cấp quyền cập nhật Deployment và đọc trạng thái rollout trong namespace staging. Ví dụ:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: staging-deployer
  namespace: staging
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: staging-deployment-writer
  namespace: staging
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["apps"]
    resources: ["replicasets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: staging-deployer-binding
  namespace: staging
subjects:
  - kind: ServiceAccount
    name: staging-deployer
    namespace: staging
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: staging-deployment-writer
```

Đây là ví dụ tối thiểu cho một luồng triển khai Deployment thông thường. Tùy công cụ, pipeline có thể cần quyền bổ sung cho resource cụ thể như Services, Ingress hoặc ConfigMaps. Chỉ thêm quyền sau khi xác định rõ thao tác thực tế. Không cấp quyền đọc nội dung Secret nếu deployer chỉ cần tham chiếu tới Secret đã tồn tại.

Role có phạm vi namespace, khác với ClusterRole có thể áp dụng trên nhiều namespace hoặc toàn cluster. Với production, nên dùng identity và binding riêng; không tái sử dụng ServiceAccount staging.

Nếu CI chạy ngoài cluster, cách xác thực vào Kubernetes phụ thuộc nền tảng cloud hoặc cơ chế OIDC/authentication của cluster. ServiceAccount trong ví dụ mô tả đối tượng RBAC ở phía cluster; không có nghĩa phải lưu token ServiceAccount dài hạn trong CI. Ưu tiên cơ chế cấp token ngắn hạn và không tạo token tĩnh không cần thiết.

## 15. Thực hiện server-side dry-run và kiểm tra manifest

Trước khi áp dụng manifest thật, có thể yêu cầu API server kiểm tra cấu trúc và admission policy bằng server-side dry-run.

Ví dụ:

```bash
kubectl apply --dry-run=server -f k8s/
```

Server-side dry-run gửi request tới API server nhưng không lưu thay đổi. Nó có thể phát hiện schema không hợp lệ, field không được hỗ trợ, lỗi admission hoặc một số vấn đề về quyền.

Dry-run không chứng minh rollout sẽ thành công. Nó không bảo đảm image pull được, container khởi động được, readiness probe đạt hoặc dependency runtime sẵn sàng. Một số admission webhook cũng phải khai báo khả năng hỗ trợ dry-run đúng cách. Kết quả dry-run chỉ là một phần của preflight.

Có thể bổ sung kiểm tra manifest tĩnh trước khi gọi API server:

- Validate YAML/JSON và schema.
- Kiểm tra namespace và resource name nằm trong allowlist.
- Kiểm tra image được tham chiếu bằng digest.
- Kiểm tra security context, resource request/limit và health probe.
- Kiểm tra policy về privileged container, hostPath hoặc capability.
- Kiểm tra không có secret literal trong manifest.
- Kiểm tra version API tương thích với cluster.

Không dùng một lệnh dry-run trên một context chưa được xác minh. Nếu kubeconfig trỏ nhầm cluster, request vẫn có thể được gửi tới API server không mong muốn. Target identity và context cần được xác nhận trước.

## 16. Kiểm tra approval và change window

Một số môi trường yêu cầu phê duyệt trước khi thay đổi, đặc biệt production hoặc hệ thống có thời gian vận hành nhạy cảm.

Approval có thể xác nhận:

- Thay đổi đã được review và có owner chịu trách nhiệm.
- Artifact và digest được đề xuất là đúng.
- Kế hoạch triển khai, theo dõi và rollback đã sẵn sàng.
- Thời điểm triển khai nằm trong change window.
- Các đội phụ thuộc đã được thông báo hoặc chuẩn bị.
- Rủi ro và tác động đã được đánh giá.

Approval không thay thế các kiểm tra tự động. Người phê duyệt không thể nhìn vào một trạng thái CI passed chung rồi suy ra target đang khỏe hoặc job có quyền đúng. Hệ thống nên hiển thị artifact, target, change ID và bằng chứng gate để người duyệt quyết định trên đúng deployment request.

Không nên yêu cầu approval cho mọi thao tác nhỏ nếu chính sách không cần. Nhưng nếu approval là điều kiện bắt buộc, pipeline phải kiểm tra trạng thái phê duyệt thực tế chứ không chỉ dựa vào một biến do job tự đặt.

Change window cũng cần được kiểm tra gần thời điểm deploy. Một job được duyệt lúc 9 giờ có thể bắt đầu lúc 11 giờ sau khi cửa sổ triển khai kết thúc hoặc incident mới xuất hiện. Điều kiện thời gian nên được xác minh lại trước bước thay đổi.

## 17. Kiểm tra concurrency và tránh hai release cùng sửa target

Hai pipeline có thể cùng lúc triển khai một môi trường. Nếu cả hai preflight đều thấy target sẵn sàng rồi đồng thời cập nhật, một release có thể ghi đè trạng thái của release còn lại.

Cần cơ chế điều phối như:

- Deployment queue hoặc concurrency group theo target.
- Lock có lease và thời hạn.
- Environment-level deployment serialization.
- Kiểm tra revision hiện tại trước khi cập nhật.
- Hủy hoặc chặn release cũ theo quy tắc đã công bố.

Lock cần có timeout và cơ chế giải phóng khi job thất bại hoặc runner bị mất. Không giữ lock vô thời hạn. Nếu dùng lease, job cần gia hạn khi vẫn thực hiện công việc và hệ thống cần xử lý trường hợp lease hết hạn trong khi job cũ vẫn chạy.

Không chỉ khóa theo tên workflow. Hai workflow khác nhau có thể cùng thay đổi một cluster hoặc database. Khóa nên phản ánh tài nguyên thực sự có nguy cơ tranh chấp: ứng dụng, namespace, database schema hoặc environment.

## 18. Kiểm tra lại điều kiện ngay trước khi thay đổi

Preflight có thể trở nên lỗi thời giữa lúc kiểm tra và lúc deploy. Ví dụ:

- Capacity giảm do workload khác tăng tải.
- Một incident mới được mở.
- Một release khác thay đổi resource version.
- Credential hết hạn.
- Approval bị thu hồi.
- Change window kết thúc.
- Image tag bị thay đổi nếu pipeline không pin digest.

Đây là vấn đề time-of-check to time-of-use (TOCTOU): trạng thái đã kiểm tra có thể khác trạng thái tại thời điểm sử dụng.

Cách giảm rủi ro:

1. Kiểm tra sớm các điều kiện tốn thời gian như artifact, compatibility và policy.
2. Lấy lock hoặc vào deployment queue trước khi thay đổi target.
3. Kiểm tra lại các điều kiện có thể thay đổi nhanh: target, approval, health, capacity, credential và current revision.
4. Sử dụng version/digest bất biến cho artifact.
5. Thực hiện thao tác có điều kiện hoặc dùng API hỗ trợ optimistic concurrency.
6. Nếu trạng thái thay đổi, dừng và đánh giá lại thay vì cố tiếp tục bằng kết quả cũ.

Preflight không thể khóa mọi yếu tố của môi trường. Mục tiêu là giảm khoảng cách giữa kiểm tra và thay đổi, đồng thời dùng cơ chế concurrency và versioning để tránh ghi đè trạng thái không mong muốn.

## 19. Gate nên có kết quả rõ ràng

Một gate không nên chỉ trả về một log dài mà không có kết luận máy đọc được. Có thể phân loại:

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| PASS | Mọi điều kiện bắt buộc đạt | Có thể tiếp tục nếu các kiểm tra sát thời điểm deploy vẫn hợp lệ |
| DENY | Vi phạm chính sách hoặc thiếu quyền | Dừng; cần sửa quyền hoặc policy theo quy trình |
| BLOCKED | Thiếu approval, change window hoặc dependency tạm thời | Chờ điều kiện được đáp ứng rồi kiểm tra lại |
| INCONCLUSIVE | Không thể xác minh do lỗi hạ tầng hoặc nguồn dữ liệu | Không deploy; khắc phục hệ thống kiểm tra và chạy lại |
| WAIVED | Có ngoại lệ được phê duyệt theo quy trình | Chỉ tiếp tục trong phạm vi và thời hạn waiver |

Không gộp lỗi hạ tầng thành PASS. Nếu API server không truy cập được, pipeline chưa chứng minh rằng quyền và target hợp lệ. Nếu approval service bị lỗi, gate chưa có bằng chứng phê duyệt.

Waiver cần có owner, lý do, phạm vi, thời hạn và người phê duyệt. Không nên cho phép một biến SKIP_PREFLIGHT=true tự bỏ qua toàn bộ gate, đặc biệt với production. Nếu có break-glass, cần audit và rà soát sau sự kiện.

## 20. Ví dụ pipeline preflight trước deploy

Một job có thể mô tả các điều kiện theo thứ tự sau:

```yaml
jobs:
  preflight:
    steps:
      - name: Verify release metadata
        run: verify artifact version, digest and provenance

      - name: Resolve target
        run: validate account, cluster and namespace against allowlist

      - name: Authenticate
        run: obtain short-lived deployment identity

      - name: Check target permissions
        run: verify required actions on the target namespace

      - name: Check environment health
        run: query health, capacity and active deployment state

      - name: Validate configuration
        run: validate configuration and required secret references

      - name: Validate manifests
        run: run schema and policy checks

      - name: Server-side dry-run
        run: submit manifests with server-side dry-run

      - name: Check approval and change window
        run: verify approval and current deployment window

  deploy:
    needs: [preflight]
    steps:
      - name: Recheck mutable conditions
        run: revalidate target, approval and current revision

      - name: Deploy verified artifact
        run: deploy the exact artifact digest
```

Các lệnh trong ví dụ là mô tả khái niệm, cần thay bằng action hoặc command của nền tảng CI và công cụ triển khai thực tế. Một số nền tảng yêu cầu approval ở cấp environment trước khi job được cấp credential; khi đó approval có thể đứng trước bước lấy identity. Điều quan trọng là approval, target validation và quyền truy cập được gắn với cùng deployment request.

Nếu preflight và deploy chạy trên hai job hoặc hai runner khác nhau, không dựa vào filesystem hoặc credential tạm của job đầu. Job deploy cần nhận artifact identity và kết quả gate có thể xác minh, rồi tự lấy credential của nó theo quyền được cấp.

## 21. Ví dụ tình huống: deploy production nhưng nhầm cluster

Một nhóm có hai cluster staging và production. Cả hai đều có namespace tên orders. Một runner lưu kubeconfig với context mặc định là staging. Pipeline được kích hoạt để deploy production nhưng script chỉ gọi kubectl apply mà không kiểm tra context.

Kết quả có thể là release được áp dụng vào staging trong khi pipeline báo deploy thành công. Nếu context mặc định thay đổi hoặc kubeconfig được cập nhật, cùng lệnh đó có thể tác động nhầm production.

Một preflight tốt sẽ:

1. Resolve environment production thành cluster endpoint và namespace đã khai báo.
2. Xác minh danh tính workload đã được federation cho production role.
3. Xác minh context hoặc cloud account thực tế khớp target dự kiến.
4. Kiểm tra quyền cần thiết trên namespace production.
5. Thực hiện server-side dry-run trên đúng API server.
6. Xác minh artifact digest và approval.
7. Lấy concurrency lock theo production target.
8. Kiểm tra lại target và current revision.
9. Deploy đúng digest đã được kiểm tra.
10. Ghi target identity, digest và deployment revision vào evidence.

Kết quả của từng bước phải được ghi rõ. Nếu target không khớp, gate dừng ngay cả khi danh tính có quyền truy cập cluster đó. Quyền tồn tại không có nghĩa target là nơi được yêu cầu.

## 22. Xử lý lỗi preflight và retry

Không phải mọi lỗi đều có cách xử lý giống nhau.

| Lỗi | Phân loại | Cách xử lý |
|---|---|---|
| Digest không khớp | Artifact/trust failure | Từ chối artifact và điều tra nguồn |
| Thiếu quyền patch Deployment | Authorization failure | Sửa role theo nguyên tắc quyền tối thiểu |
| Sai cluster hoặc namespace | Target mismatch | Dừng và sửa mapping/trigger |
| API server không truy cập được | Infrastructure error | Khôi phục kết nối rồi chạy lại preflight |
| Thiếu approval | Policy blocked | Chờ phê duyệt hợp lệ |
| Ngoài change window | Time policy blocked | Chờ cửa sổ cho phép |
| Thiếu capacity | Environment not ready | Giải phóng/tăng tài nguyên hoặc đổi thời điểm |
| Migration không tương thích | Compatibility failure | Thiết kế migration hoặc release theo giai đoạn |
| Credential hết hạn | Authentication failure | Lấy credential mới nếu identity vẫn hợp lệ |
| Release khác đang giữ lock | Concurrency blocked | Chờ queue hoặc xử lý release đang chạy |

Chỉ retry lỗi có khả năng hồi phục như timeout tạm thời, API server gián đoạn hoặc credential hết hạn khi điều kiện trust vẫn hợp lệ. Không retry liên tục khi thiếu quyền, sai target hoặc vi phạm policy.

Trước khi retry, xác định thao tác trước đã làm thay đổi môi trường hay chưa. Nếu deploy đã bắt đầu, cần kiểm tra current revision và trạng thái rollout trước khi chạy lại. Retry không được tạo thêm migration hoặc thao tác có tác dụng phụ ngoài dự kiến.

## 23. Ghi lại bằng chứng của gate

Mỗi lần preflight cần tạo một record có thể truy vết. Record nên gắn với deployment request cụ thể, không chỉ với workflow run.

Thông tin hữu ích:

- Application/service và release identifier.
- Artifact version và digest.
- Source commit và build run.
- Target account, cluster, namespace, region hoặc tenant.
- Deployment identity và role được sử dụng.
- Các điều kiện đã kiểm tra và kết quả từng điều kiện.
- Thời điểm kiểm tra và thời điểm deploy bắt đầu.
- Approval/change ID và người phê duyệt nếu có.
- Manifest/configuration revision.
- Lock hoặc deployment queue ID.
- Kết quả dry-run và policy validation.
- Current revision trước deploy và revision sau deploy.

Không ghi token, password hoặc giá trị secret vào evidence. Ghi principal identifier, role, secret reference hoặc version theo chính sách. Nếu log có chứa cấu hình nhạy cảm, cần che hoặc loại bỏ trước khi lưu.

Evidence giúp điều tra vì sao pipeline cho phép deploy, job nào thực hiện thao tác và artifact nào được dùng. Nó cũng giúp phân biệt lỗi của release với lỗi của môi trường hoặc quyền truy cập.

## 24. Những anti-pattern thường gặp

| Cách làm chưa tốt | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ kiểm tra CI xanh | Không biết artifact và target cụ thể có hợp lệ không | Gate theo deployment request và digest |
| Dùng context mặc định của kubectl | Có thể deploy nhầm cluster | Xác minh target và context rõ ràng |
| Dùng một credential admin cho mọi môi trường | Tăng phạm vi ảnh hưởng | Identity riêng và quyền tối thiểu |
| Approval thay cho authorization | Người duyệt không thể cấp quyền máy | Kiểm tra approval và RBAC/IAM độc lập |
| Job có quyền đọc mọi Secret | Dễ lộ dữ liệu nhạy cảm | Tách quyền deploy và secret consumption |
| Dry-run được coi là bằng chứng rollout thành công | Không phát hiện lỗi image, startup hoặc dependency | Kết hợp smoke/readiness sau deploy |
| Preflight chạy quá sớm | Kết quả lỗi thời trước khi sử dụng | Recheck điều kiện mutable ngay trước deploy |
| Không khóa deployment đồng thời | Hai release có thể ghi đè nhau | Queue hoặc lock theo target |
| Retry mọi lỗi | Che giấu sai cấu hình và lỗi policy | Phân loại lỗi và giới hạn retry |
| Bỏ qua gate bằng biến tùy ý | Mất kiểm soát production | Waiver có owner, scope, expiry và audit |
| Log toàn bộ kubeconfig/token | Rò rỉ credential | Chỉ ghi identity và metadata không nhạy cảm |
| Không lưu target và digest trong record | Khó điều tra triển khai nhầm | Gắn evidence với target và artifact identity |

## 25. Lộ trình triển khai preflight trong dự án

Có thể triển khai theo từng bước:

1. **Xác định target:** liệt kê environment, account, cluster, namespace và tài nguyên pipeline được phép thay đổi.
2. **Xác định deployment request:** chuẩn hóa service, artifact digest, target, action và release ID.
3. **Lập danh sách gate:** phân loại artifact, chất lượng, môi trường, tương thích, cấu hình, approval và quyền.
4. **Thiết kế workload identity:** tách danh tính theo nhiệm vụ và môi trường; ưu tiên credential ngắn hạn.
5. **Thiết lập RBAC/IAM:** cấp đúng action và resource, kiểm tra bằng principal thực tế.
6. **Tự động hóa validation:** kiểm tra manifest, config, schema, health và capacity.
7. **Thêm dry-run:** xác minh API/admission và quyền trên đúng target.
8. **Thêm concurrency control:** khóa hoặc xếp hàng theo tài nguyên có thể tranh chấp.
9. **Recheck sát thời điểm deploy:** xác minh lại các điều kiện có thể thay đổi.
10. **Lưu evidence:** gắn kết quả với artifact digest, target, identity và approval.
11. **Diễn tập lỗi:** thử sai target, thiếu quyền, credential hết hạn, môi trường unhealthy và release cạnh tranh.

Bắt đầu với staging để kiểm chứng quy trình. Khi gate ổn định, áp dụng cho production với điều kiện approval, change window và identity riêng. Không nên đưa một bộ kiểm tra chưa được thử nghiệm vào production rồi mới tìm hiểu cách nó hoạt động.

## 26. Đo hiệu quả của pre-deployment gate

Gate tốt giúp ngăn triển khai sai và giảm sự cố do điều kiện môi trường hoặc quyền truy cập. Có thể theo dõi:

- Số lần gate chặn đúng artifact hoặc target không hợp lệ.
- Số deployment thất bại do thiếu quyền hoặc sai target.
- Tỷ lệ preflight bị lỗi hạ tầng hoặc không thể kết luận.
- Thời gian từ preflight đến deploy thực tế.
- Số lần phải recheck vì trạng thái môi trường thay đổi.
- Số xung đột deployment được ngăn bởi queue/lock.
- Tỷ lệ deployment có đầy đủ evidence và approval.
- Số lần sử dụng waiver và thời gian waiver còn hiệu lực.
- Tỷ lệ rollback hoặc incident liên quan đến điều kiện không được kiểm tra.

Không nên tối ưu bằng cách bỏ gate quan trọng chỉ để rút ngắn thời gian pipeline. Hãy làm các kiểm tra nhanh chạy sớm, chạy song song các bước độc lập và chỉ thực hiện kiểm tra phụ thuộc target sau khi target đã được xác định. Gate cần cân bằng tốc độ phản hồi với mức đảm bảo cần thiết.

## 27. Checklist trước khi cho phép triển khai

- [ ] Deployment request xác định rõ service, artifact, target và thao tác.
- [ ] Artifact version/digest khớp với release metadata tin cậy.
- [ ] Test, scan và quality gate bắt buộc đã đạt.
- [ ] Target account, cluster, namespace hoặc tenant đã được xác minh.
- [ ] Môi trường đích khỏe và đủ capacity cho rollout.
- [ ] Runtime, schema và dependency tương thích với phiên bản mới.
- [ ] Cấu hình hợp lệ và secret reference cần thiết tồn tại.
- [ ] Dependency runtime có thể truy cập theo thiết kế.
- [ ] Workload identity được xác thực đúng issuer/audience/subject.
- [ ] IAM/RBAC chỉ cấp quyền cần thiết trên đúng tài nguyên.
- [ ] Job deploy không có quyền đọc secret hoặc quản trị ngoài nhu cầu.
- [ ] Manifest đã qua validation và dry-run phù hợp.
- [ ] Approval và change window còn hiệu lực.
- [ ] Không có deployment khác đang tranh chấp target.
- [ ] Điều kiện mutable được kiểm tra lại ngay trước thao tác.
- [ ] Có kế hoạch rollback hoặc phục hồi phù hợp.
- [ ] Evidence ghi lại artifact digest, target, identity và kết quả gate.
- [ ] Token, password và secret không xuất hiện trong log.

## Kết luận

Kiểm tra điều kiện trước khi triển khai là bước quyết định liệu một artifact cụ thể có thể được đưa vào một target cụ thể ở thời điểm hiện tại hay không. Gate cần xác minh artifact, chất lượng, sức khỏe và capacity của môi trường, tính tương thích, cấu hình, dependency, approval và trạng thái concurrency.

Quyền truy cập đích cần được kiểm tra riêng bằng danh tính workload và policy của hệ thống đích. Xác thực chứng minh job là ai; phân quyền giới hạn job được làm gì và trên tài nguyên nào. Khi dùng identity ngắn hạn, RBAC/IAM tối thiểu, target allowlist, dry-run, recheck sát thời điểm deploy và evidence có thể truy vết, pipeline giảm nguy cơ triển khai nhầm, vượt quyền hoặc thay đổi môi trường khi chưa sẵn sàng.

