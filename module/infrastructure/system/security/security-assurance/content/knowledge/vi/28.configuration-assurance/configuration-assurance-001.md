# Secure configuration: Thiết lập cấu hình an toàn và chứng minh hệ thống đang tuân thủ

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích **secure configuration** là gì, vì sao cấu hình an toàn cần được kiểm chứng liên tục trong chương trình **security assurance**.
- Xây dựng **security configuration baseline** theo rủi ro, loại hệ thống và môi trường; phân biệt trạng thái mong muốn với trạng thái đang chạy.
- Áp dụng các nguyên tắc hardening như *least privilege*, *least functionality*, *deny by default*, cấu hình bảo vệ dữ liệu, quản lý secrets và ghi nhật ký.
- Thiết kế quy trình kiểm soát thay đổi, kiểm thử cấu hình, phát hiện **configuration drift** và quản lý ngoại lệ có thời hạn.
- Tạo chuỗi bằng chứng từ yêu cầu bảo mật đến chính sách cấu hình, kết quả kiểm tra và hành động khắc phục.

## 2. Secure configuration là gì?

**Secure configuration** là việc lựa chọn, thiết lập, duy trì và kiểm chứng các giá trị cấu hình sao cho một thành phần chỉ cung cấp những chức năng cần thiết, thực thi quyền hạn phù hợp và đáp ứng các yêu cầu bảo mật đã xác định. Đối tượng có thể là hệ điều hành, cơ sở dữ liệu, API gateway, máy chủ web, danh tính dịch vụ, hạ tầng cloud, container, Kubernetes hoặc ứng dụng.

Ví dụ, một dịch vụ API cần truy cập cơ sở dữ liệu để đọc thông tin đơn hàng. Cấu hình an toàn có thể yêu cầu:

- Tài khoản cơ sở dữ liệu chỉ có quyền trên bảng và thao tác cần dùng.
- Kết nối đến cơ sở dữ liệu được mã hóa và xác thực danh tính máy chủ.
- Cổng quản trị và cơ sở dữ liệu không mở trực tiếp ra Internet.
- Secrets được cấp qua cơ chế quản lý bí mật; không ghi vào image, file cấu hình trong Git hoặc log.
- Audit log ghi lại các thay đổi cấu hình có tác động đến bảo mật.

Điểm khác biệt của **configuration assurance** là câu hỏi tiếp theo: **Có bằng chứng đáng tin cậy nào cho thấy các cấu hình ấy đã được triển khai, vẫn có hiệu lực và tiếp tục phù hợp với rủi ro hiện tại?**

Một tài liệu chuẩn cấu hình chỉ mô tả *ý định*. Manifest trong Git hoặc template IaC thể hiện *cấu hình mong muốn*. Kết quả kiểm tra trên tài nguyên thực tế mới giúp khẳng định *cấu hình hiệu lực tại thời điểm đo*. Ba lớp này có thể khác nhau do thao tác thủ công, lỗi triển khai, thay đổi của nhà cung cấp hoặc thành phần tự sửa cấu hình.

### Phân biệt các khái niệm

| Khái niệm | Ý nghĩa | Đầu ra thường gặp |
|---|---|---|
| **Secure defaults** | Giá trị mặc định hạn chế quyền và bề mặt tấn công | Không mở cổng quản trị; tắt tính năng debug |
| **Hardening** | Loại bỏ tính năng, quyền và cấu hình không cần thiết | Vô hiệu dịch vụ thừa; bỏ Linux capabilities |
| **Configuration baseline** | Bộ cấu hình tối thiểu được phê duyệt cho loại tài sản và môi trường cụ thể | Phiên bản baseline, rule ID, giá trị yêu cầu |
| **Configuration compliance** | Mức độ cấu hình thực tế thỏa các quy tắc được áp dụng | Kết quả PASS/FAIL, phạm vi và ngoại lệ |
| **Configuration drift** | Sai khác giữa trạng thái đang chạy và trạng thái đã phê duyệt | Bản ghi sai khác, nguyên nhân, lịch sử sửa |
| **Configuration assurance** | Hoạt động thu thập và đánh giá bằng chứng để tạo sự tin cậy vào trạng thái cấu hình | Kết luận có điều kiện, bằng chứng, tồn đọng |

**Lưu ý:** Một hệ thống “đạt 100% rule” vẫn có thể không an toàn nếu baseline thiếu yêu cầu, phép kiểm không bao phủ runtime hoặc người đánh giá không hiểu mô hình đe dọa.

## 3. Từ rủi ro đến baseline cấu hình

Baseline không nên là bản sao nguyên xi từ một checklist chung. Cần xác định đối tượng, rủi ro và ràng buộc vận hành trước khi đặt các giá trị cụ thể.

### 3.1. Xác định phạm vi và nguồn chuẩn

1. **Kiểm kê tài sản:** thành phần, chủ sở hữu, phiên bản, môi trường, vị trí triển khai, dữ liệu được xử lý và kết nối phụ thuộc.
2. **Phân loại rủi ro:** mức nhạy cảm dữ liệu, khả năng lộ Internet, quyền của thành phần và hậu quả nếu bị xâm nhập.
3. **Xác định yêu cầu:** yêu cầu từ threat model, chính sách nội bộ, hợp đồng, quy định áp dụng và quyết định chấp nhận rủi ro.
4. **Lựa chọn nguồn tham chiếu:** tài liệu hardening của nhà cung cấp, **CIS Benchmarks** tương ứng sản phẩm/phiên bản và các nhóm kiểm soát của **NIST SP 800-53** như CM-2 (baseline configuration), CM-3 (configuration change control), CM-6 (configuration settings), CM-7 (least functionality). Chỉ áp dụng những mục phù hợp hệ thống.
5. **Định nghĩa quy tắc kiểm chứng:** với mỗi yêu cầu, xác định giá trị mong muốn, cách đo thực tế, ngưỡng đạt, độ ưu tiên, chủ sở hữu, phiên bản và lý do ngoại lệ (nếu có).

Một baseline hữu ích phải trả lời được: *đang áp dụng cho tài sản nào, tại phiên bản nào, bằng tiêu chí nào, ai phê duyệt, ai chịu trách nhiệm và kiểm chứng khi nào?*

### 3.2. Các nhóm kiểm soát thường gặp

| Bề mặt cấu hình | Cấu hình cần xem xét | Nguy cơ khi cấu hình sai | Cách thu thập bằng chứng |
|---|---|---|---|
| Hệ điều hành/host | Dịch vụ khởi động, tài khoản đặc quyền, SSH/RDP, tường lửa, cập nhật | Xâm nhập qua dịch vụ thừa, leo thang quyền | Snapshot cấu hình, agent kiểm tra, kiểm kê phiên bản |
| Network/cloud | Inbound/outbound rules, public endpoint, phân đoạn mạng, quản trị từ xa | Lộ tài nguyên, lateral movement | Truy vấn cấu hình cloud API, ruleset thực tế, thử kết nối có kiểm soát |
| Identity/IAM | Vai trò, quyền API, service account, xác thực mạnh, token lifetime | Lạm dụng quyền, chiếm quyền quản trị | Phân tích effective permissions, audit IAM |
| Web/API | TLS, CORS, security headers, debug mode, giới hạn request | Rò rỉ dữ liệu, tấn công từ trình duyệt hoặc lạm dụng API | Kiểm tra response, TLS handshake, runtime config |
| Database/storage | Network exposure, encryption, audit, tài khoản kỹ thuật, backup | Rò rỉ hoặc sửa dữ liệu, mất khả năng phục hồi | Metadata tài nguyên, quyền hiệu lực, thử restore |
| Container/Kubernetes | Image, quyền container, seccomp, service account, admission policy | Container escape, truy cập API không cần thiết | Kiểm manifest, chính sách admission, truy vấn pod đang chạy |
| Secrets và logging | Nguồn cấp secrets, rotation, phân quyền xem log, retention | Lộ thông tin xác thực, thiếu điều tra sự cố | Secret metadata, access policy, log thay đổi và bằng chứng kiểm thử |

Không phải mọi quy tắc đều áp dụng như nhau: ví dụ, một batch job không cần inbound traffic, trong khi public API cần một endpoint được kiểm soát. Việc đóng toàn bộ lưu lượng có thể gây gián đoạn nếu bỏ qua luồng phụ thuộc hợp lệ.

### 3.3. Ví dụ chuyển rủi ro thành tiêu chí nghiệm thu

Giả sử dịch vụ `payments-api` chạy trên Kubernetes và xử lý dữ liệu thanh toán qua một API:

| Rủi ro / yêu cầu | Quy tắc baseline | Cách kiểm chứng | Mức xử lý |
|---|---|---|---|
Ứng dụng bị khai thác rồi lấy quyền cao hơn | Container không được tăng quyền, không chạy bằng root nếu không có lý do được duyệt | Policy scan manifest **và** kiểm tra pod đang chạy | Chặn phát hành khi vi phạm |
Lộ thông tin xác thực | Không lưu secrets trong image/Git/log; quyền truy cập secrets theo nhu cầu | Secret scanning, kiểm quyền, thử quy trình rotation | Chặn phát hành nếu lộ secret |
Kẻ tấn công di chuyển ngang | Chỉ cho phép những luồng cần thiết qua NetworkPolicy/firewall | Xét cấu hình hiệu lực và thử luồng được phép/bị chặn | Chặn phát hành đối với tuyến trọng yếu |
Thay đổi cấu hình ngoài quy trình | Mọi thay đổi sản xuất có chủ sở hữu và dấu vết phê duyệt | So trạng thái thực với Git/IaC, audit log | Cảnh báo và xử lý theo SLA |

Mức xử lý phải dựa trên hậu quả, khả năng khai thác và biện pháp bù trừ; không chỉ dựa vào số lượng rule thất bại.

## 4. Nguyên tắc thiết kế secure configuration

### 4.1. Giảm bề mặt tấn công

- **Deny by default:** từ chối kết nối, hành động hoặc danh tính chưa được cho phép rõ ràng. Mở ngoại lệ theo luồng nghiệp vụ cụ thể.
- **Least privilege:** tài khoản người dùng, workload và automation có đúng những quyền cần thiết trong thời gian cần thiết.
- **Least functionality:** tắt các giao thức cũ, endpoint debug, tài khoản mẫu và dịch vụ không còn dùng.
- **Separation of duties:** người sửa cấu hình nhạy cảm và người phê duyệt/đánh giá có vai trò rõ ràng.
- **Secure by default:** tạo môi trường mới từ mẫu đã được harden; tránh phụ thuộc vào thao tác nhớ làm sau triển khai.

### 4.2. Bảo vệ thông tin và khả năng quan sát

- Yêu cầu TLS phù hợp cho đường truyền nhạy cảm và xác minh danh tính peer; chỉ đánh dấu “bật TLS” là chưa đủ nếu chấp nhận certificate không hợp lệ.
- Mã hóa dữ liệu lưu trữ và kiểm soát quyền truy cập khóa; bảo vệ backup tương ứng với mức nhạy cảm của dữ liệu gốc.
- Quản lý bí mật bằng hệ thống chuyên dụng khi phù hợp, tránh hardcode; có quy trình thu hồi và xoay vòng khi rò rỉ.
- Cấu hình log ghi sự kiện truy cập, thay đổi quyền, thay đổi cấu hình và lỗi bảo mật cần điều tra, đồng thời **không ghi token, mật khẩu hoặc dữ liệu nhạy cảm** một cách không cần thiết.
- Phân biệt chế độ `development`, `staging` và `production`. Production thường cần cấu hình chặt hơn như tắt debug, bảo vệ dữ liệu thật, logging có kiểm soát và phê duyệt thay đổi.

### 4.3. Tính tái lập và tính kiểm chứng

Đưa cấu hình vào hệ thống có phiên bản (Configuration as Code / Infrastructure as Code), áp dụng peer review, policy-as-code và cơ chế triển khai có thể lặp lại. Với những giá trị không thể đưa vào Git, quản lý **tham chiếu** hoặc **metadata** của secret, không commit secret gốc.

Mỗi rule nên có ID ổn định, mô tả, nguồn lý do, điều kiện áp dụng và phép kiểm. Cấu hình đã được duyệt phải gắn với mã commit, phiên bản artifact, environment và thời điểm triển khai để truy vết.

## 5. Ví dụ thực hành: Hardening một Deployment Kubernetes

Xét một Deployment đơn giản của `payments-api`. Ví dụ sau tập trung vào một số kiểm soát ở mức workload; **digest image là giá trị minh họa** và phải thay bằng digest của image thật trước khi chạy:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payments-api
  template:
    metadata:
      labels:
        app: payments-api
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: registry.example.com/payments-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 64Mi
```

**Giải thích lựa chọn:**

- `runAsNonRoot` và `runAsUser` hạn chế việc chạy bằng root; image và quyền file bên trong phải tương thích với UID này.
- `allowPrivilegeEscalation: false`, loại bỏ Linux capabilities và `seccompProfile: RuntimeDefault` thu hẹp các đặc quyền của tiến trình. Không có biện pháp đơn lẻ nào bảo đảm cô lập hoàn toàn.
- `readOnlyRootFilesystem: true` hạn chế ghi vào filesystem của image; ứng dụng cần vùng ghi tạm được cấp cụ thể, như volume gắn tại `/tmp`. Giới hạn dung lượng và dọn dẹp phải phù hợp nhu cầu thực tế.
- `automountServiceAccountToken: false` tránh tự động gắn token Kubernetes API khi ứng dụng không cần gọi API này.
- Image cố định bằng digest làm giảm rủi ro tag bị đổi ngầm; cần kết hợp kiểm chứng nguồn image và quét lỗ hổng.
- `resources` đặt mức sử dụng tài nguyên dự kiến nhằm giảm tác động quá tải cục bộ; đây không phải thay thế cho rate limiting, quota cấp namespace hoặc chính sách chống DoS.

Ví dụ **chưa** thể hiện toàn bộ baseline sản xuất: cần thêm NetworkPolicy cho traffic, quy tắc RBAC/service account phù hợp, chính sách TLS ở ingress/mesh, secret management, logging và kiểm tra image. Nếu workload thực sự phải dùng token API Kubernetes thì không nên vô hiệu token một cách máy móc; cần service account có quyền tối thiểu và cơ chế cấp token phù hợp.

### 5.1. Kiểm tra trước triển khai

Trong pipeline CI, có thể tiến hành các bước kiểm tra độc lập:

```text
1. Lint/kiểm schema YAML và Kubernetes API version tương ứng cluster.
2. Kiểm policy: cấm privilege escalation, root không được phê duyệt,
   image không cố định phiên bản, secret hardcode, quyền quá rộng...
3. Quét image và dependency; xác minh provenance/signature nếu có yêu cầu.
4. Thử nghiệm triển khai vào môi trường kiểm thử và kiểm tra hành vi.
5. Ghi lại kết quả, commit SHA, digest image, phiên bản policy và người phê duyệt.
```

Ví dụ một policy nhỏ với **Conftest / Rego v1** từ chối container không đặt rõ `allowPrivilegeEscalation: false`:

```rego
package main

import rego.v1

deny contains msg if {
    some container in input.spec.template.spec.containers
    settings := object.get(container, "securityContext", {})
    object.get(settings, "allowPrivilegeEscalation", null) != false
    msg := sprintf("Container %q phải tắt privilege escalation", [container.name])
}
```

Lưu policy thành `policy/deployment.rego` và manifest thành `deployment.yaml` trong dự án thực hành, rồi chạy:

```bash
conftest test deployment.yaml --policy policy/
```

Rule này cố ý chỉ chứng minh **một điều kiện**. Baseline đầy đủ phải có các rule khác, kiểm thử policy bằng cả trường hợp đạt/không đạt và kiểm soát ngoại lệ được phê duyệt. Kết quả Conftest trên file YAML chưa chứng minh rằng cluster đang chạy đúng các giá trị đó.

### 5.2. Kiểm chứng cấu hình thực tế

Sau triển khai có kiểm soát, thu thập cấu hình hiệu lực và kết quả kiểm tra trên workload thực:

```bash
kubectl -n production get deployment payments-api -o yaml
kubectl -n production get pods -l app=payments-api -o yaml
```

Đối chiếu trường cấu hình liên quan từ Deployment và Pod với baseline đã phê duyệt; kiểm tra thêm admission policy, kết nối mạng và effective permissions. Hạn chế lưu nguyên bản đối tượng có chứa thông tin nhạy cảm trong kho bằng chứng. Việc kiểm chứng có thể phải chạy bằng tài khoản chỉ đọc có phạm vi thích hợp.

Để kết luận workload đang tuân thủ, cần xem **các pod hiện có và trạng thái thực tế**; chỉ nhìn vào file khai báo hoặc Deployment có thể bỏ sót những pod cũ còn chạy trong quá trình rolling update.

## 6. Vòng đời kiểm soát cấu hình

```text
Yêu cầu & threat model
          ↓
Baseline được phê duyệt và có phiên bản
          ↓
Mẫu cấu hình / IaC / Policy-as-code
          ↓
Code review → Kiểm thử tĩnh → Thử nghiệm
          ↓
Triển khai có ghi nhận thay đổi
          ↓
Kiểm tra trạng thái thực + phát hiện drift
          ↓
Sửa sai lệch / xử lý ngoại lệ / cập nhật baseline
          ↺
```

### Giai đoạn thiết kế

Kỹ sư nền tảng và security xác định baseline ứng với các lớp tài sản. Quy tắc phải có điều kiện áp dụng rõ ràng, chẳng hạn “mọi database production chứa dữ liệu nhạy cảm phải không có public access” thay vì “mọi database phải nằm trong cùng một subnet”.

### Giai đoạn thay đổi và triển khai

Mọi thay đổi có ảnh hưởng bảo mật phải có người yêu cầu, bản ghi đánh giá tác động, cơ chế phê duyệt phù hợp, liên kết với commit và phương án khôi phục. Pipeline thực thi các kiểm tra tự động trước khi cho phép phát hành. Các thay đổi khẩn cấp có thể đi theo quy trình rút gọn được định nghĩa sẵn nhưng vẫn cần truy vết và đánh giá hậu kiểm.

### Giai đoạn vận hành

Định kỳ thu thập trạng thái thực qua API, agent, truy vấn hệ thống và kiểm thử có kiểm soát; so với baseline *đang áp dụng cho chính phiên bản tài sản đó*. Phát hiện drift cần phân biệt:

- **Drift không được phép:** người vận hành mở một cổng trên production ngoài IaC, tăng quyền IAM hoặc tắt logging.
- **Drift có chủ đích:** thay đổi khẩn cấp được phê duyệt, phải cập nhật nguồn cấu hình, bằng chứng và thời hạn.
- **Khác biệt hợp lệ:** giá trị runtime do orchestrator sinh ra như pod IP hoặc số replica tự điều chỉnh trong giới hạn. Không nên lấy mọi sai khác văn bản làm vi phạm bảo mật.

Khi phát hiện sai lệch có tác động, tiến hành xác minh, đánh giá ưu tiên, khôi phục cấu hình an toàn hoặc thực hiện biện pháp bù trừ, rồi kiểm tra lại trạng thái thực. Tự động sửa cấu hình chỉ phù hợp với những trường hợp đã đánh giá tác động và có biện pháp tránh gián đoạn dịch vụ.

## 7. Configuration assurance: Tổ chức bằng chứng

Hoạt động assurance nên được thiết kế theo chuỗi:

**Yêu cầu bảo mật → Rủi ro → Control → Giá trị cấu hình → Phép kiểm → Bằng chứng → Kết luận → Hành động.**

Ví dụ cấu trúc một bản ghi kiểm tra:

```yaml
asset: payments-api
environment: production
baseline_id: K8S-WORKLOAD-2026-01
control_id: CFG-K8S-003
requirement: "Container không được tăng quyền"
expected: "allowPrivilegeEscalation = false"
observed: false
result: PASS
checked_at: "2026-11-28T03:00:00Z"
source: "Kubernetes API - Pod runtime configuration"
artifact_digest: "sha256:<hash-bang-chung>"
owner: platform-security
```

Đây là **dạng bản ghi minh họa**, không phải kết quả kiểm tra thực tế. Trong hệ thống thực, cần lưu thêm định danh đối tượng duy nhất, phiên bản bộ rule/công cụ và đường dẫn đến bằng chứng được kiểm soát truy cập. Thời gian phải thể hiện chính xác thời điểm quan sát; kết quả `PASS` chỉ áp dụng cho đối tượng và thời điểm được đo.

### Đánh giá độ tin cậy của bằng chứng

| Câu hỏi | Tiêu chí cần đạt |
|---|---|
| **Đúng đối tượng?** | Có asset ID, namespace/account, môi trường, phiên bản/instance |
| **Đúng tiêu chí?** | Rule ID và baseline version được phê duyệt, điều kiện áp dụng rõ ràng |
| **Đúng thời điểm?** | Timestamp và chu kỳ kiểm tra thích hợp với tốc độ thay đổi |
| **Đúng nguồn?** | Nguồn dữ liệu phản ánh cấu hình thực hoặc trạng thái hiệu lực, không chỉ bản thiết kế |
| **Có thể lặp lại?** | Lưu phiên bản công cụ, tham số/phạm vi quét và phương pháp kiểm tra |
| **Có thể tin cậy?** | Quyền ghi/sửa bằng chứng bị giới hạn, có log và checksum/chữ ký khi cần |
| **Có xử lý kết quả?** | FAIL có người nhận, deadline, bằng chứng khắc phục và kiểm tra lại |

Trường hợp kiểm tra không chạy được, mất quyền truy cập, công cụ lỗi hoặc tài sản chưa được quét phải được ghi là **UNKNOWN / NOT ASSESSED**. Không gộp các trường hợp này thành PASS.

### Ba kiểu kết quả cần phân biệt

1. **Design compliance:** template, IaC, policy đã mô tả cấu hình đúng.
2. **Deployment compliance:** artifact đã triển khai tương ứng phiên bản được duyệt.
3. **Runtime compliance:** thành phần đang chạy và chính sách hiệu lực đáp ứng baseline khi kiểm tra.

Assurance vững hơn khi cả ba được liên kết bằng ID của thay đổi, artifact, đối tượng triển khai và bằng chứng runtime.

## 8. Ngoại lệ, sai lệch và rủi ro còn lại

Một quy tắc baseline có thể xung đột với yêu cầu vận hành hợp lệ. Ví dụ, phần mềm cũ cần ghi vào một thư mục mặc định của image, khiến `readOnlyRootFilesystem` chưa áp dụng ngay được. Không nên âm thầm bỏ rule hoặc ghi “đạt” cho trường hợp này.

Một **ngoại lệ có quản trị** thường cần: tài sản và rule liên quan, lý do kỹ thuật, đánh giá rủi ro, biện pháp bù trừ, người chịu trách nhiệm, người chấp nhận rủi ro có thẩm quyền, thời điểm hết hạn và kế hoạch xử lý. Đến hạn phải đánh giá lại hoặc đóng ngoại lệ.

Ví dụ:

| Trường | Giá trị minh họa |
|---|---|
| Asset / rule | `legacy-batch` / `CFG-K8S-004` |
| Lý do | Ứng dụng bắt buộc ghi vào filesystem |
| Rủi ro | Tăng khả năng thay đổi file khi tiến trình bị chiếm quyền |
| Bù trừ | Giới hạn mạng, bỏ capabilities, chỉ cấp quyền ghi tại thư mục cần dùng |
| Hướng khắc phục | Chuyển vùng ghi sang volume riêng, kiểm thử image mới |
| Quyết định | Phê duyệt tạm thời, có chủ sở hữu và ngày hết hạn |

Ngoại lệ hết hạn, thiếu người phê duyệt hoặc không còn biện pháp bù trừ phù hợp phải quay lại hàng đợi xử lý rủi ro. Cần phân biệt **chấp nhận rủi ro** với **xác nhận cấu hình đã an toàn**: hai kết luận này không đồng nghĩa.

## 9. Đo lường hiệu quả và những sai lầm thường gặp

Đo lường cần phản ánh cả **độ bao phủ** lẫn **kết quả**. Các chỉ số có thể gồm:

| Chỉ số | Cách diễn giải đúng |
|---|---|
| Baseline coverage | Tỷ lệ tài sản trong phạm vi có baseline phù hợp, có phiên bản |
| Assessment coverage | Tỷ lệ tài sản phải kiểm tra đã được kiểm tra thành công trong chu kỳ |
| Compliance rate | Tỷ lệ rule **áp dụng và đã được kiểm tra** đạt yêu cầu; báo kèm số rule không đánh giá được và ngoại lệ |
| Drift detection latency | Khoảng thời gian từ khi phát sinh sai lệch đến lúc được phát hiện |
| Remediation time | Thời gian từ phát hiện đến xác minh sửa xong, phân theo mức rủi ro |
| Exception aging | Số ngoại lệ còn mở, quá hạn và mức độ ảnh hưởng |

Ví dụ: 90/100 rule đã kiểm tra đạt, 10 rule chưa được đánh giá; không thể kết luận tuân thủ 90% toàn hệ thống nếu còn nhiều tài sản chưa quét. Mẫu số, phạm vi và thời điểm phải được công khai trong báo cáo.

Những lỗi thường gây đánh giá sai:

- **Chỉ quét cấu hình tại build time:** drift xuất hiện sau triển khai không được phát hiện.
- **Áp dụng benchmark máy móc:** loại trừ sai hoặc hardening gây đứt luồng nghiệp vụ; cần đánh giá điều kiện áp dụng và kiểm thử hồi quy.
- **Chỉ dựa vào màn hình dashboard:** không lưu rule version, dữ liệu nguồn hoặc bằng chứng đủ để tái lập kết luận.
- **Bỏ qua quyền hiệu lực:** vai trò IAM trông có vẻ tối thiểu nhưng quyền kế thừa, resource policy hoặc nhóm khác khiến truy cập thực tế rộng hơn.
- **Cấu hình log quá rộng:** vô tình thu thập token và dữ liệu nhạy cảm hoặc làm tăng khả năng truy cập trái phép.
- **Bỏ qua tài sản mới và tài sản ngừng hoạt động:** số liệu tuân thủ bị đẹp giả do phạm vi kiểm kê sai.
- **Tự sửa mọi sai lệch:** automation khôi phục trạng thái vô tình phá hỏng một thay đổi khẩn cấp hợp lệ hoặc gây outage.

## 10. Bài tập vận dụng

**Tình huống:** Một nhóm vận hành API trên cloud phát hiện ba việc: cổng quản trị được mở tạm cho tất cả IP, Deployment production đang dùng tag image `latest` và dịch vụ ghi token vào debug log.

Hãy lập bảng gồm **rủi ro, rule baseline, phương thức kiểm tra trước triển khai, bằng chứng runtime, mức ưu tiên, phương án xử lý và người chịu trách nhiệm** cho từng vấn đề.

**Gợi ý tự đánh giá:**

1. Cổng quản trị có rule chặn truy cập không phù hợp và kiểm tra hiệu lực firewall/security group; ưu tiên thu hẹp ngay phạm vi truy cập, điều tra thời gian đã mở.
2. Tag `latest` được thay bằng digest đã kiểm chứng; kiểm tra image thực đang chạy và bảo vệ pipeline khỏi artifact chưa phê duyệt.
3. Token trong log được coi là có khả năng lộ thông tin xác thực: ngừng ghi, hạn chế quyền đọc log, thu hồi/xoay vòng token có thể đã lộ, kiểm tra phạm vi ảnh hưởng và tạo test chống tái diễn.

Một lời giải đạt yêu cầu phải có cả **kiểm soát phòng ngừa** và **bằng chứng sau triển khai**, có người xử lý và tiêu chí đóng phát hiện. Không được coi việc sửa manifest là bằng chứng duy nhất rằng sự cố đã được khắc phục trên môi trường production.

## 11. Ghi nhớ cốt lõi

Secure configuration là sự kết hợp của **baseline phù hợp rủi ro**, **cấu hình được quản lý như mã**, **kiểm tra ở nhiều giai đoạn** và **bằng chứng runtime còn hiệu lực**. Trong dịch vụ `SECURITY_SECURITY_ASSURANCE`, nội dung này gắn trực tiếp với mục tiêu xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, security controls đến kiểm thử, audit và khắc phục phát hiện.

Một kết luận assurance hữu ích phải nói rõ **đã đánh giá tài sản nào, theo baseline nào, vào thời điểm nào, kết quả ra sao và rủi ro còn lại là gì**. Nhờ vậy, cấu hình an toàn trở thành hoạt động liên tục của cả phát triển lẫn vận hành, thay vì một đợt hardening duy nhất lúc cài đặt.
