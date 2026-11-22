# Kiểm tra cấu hình trước khi chạy lên môi trường thật

## 1. Vì sao phải kiểm tra cấu hình pipeline trước khi triển khai?

Pipeline as Code đưa quy trình build, kiểm thử và triển khai vào các tệp cấu hình có thể quản lý bằng Git. Những tệp này cũng là mã nguồn: chúng có thể chứa lỗi cú pháp, tham chiếu sai, điều kiện thiếu, quyền quá rộng hoặc lệnh triển khai nguy hiểm. Một pipeline hợp lệ về cú pháp vẫn có thể tạo ra hành vi sai khi chạy.

Một thay đổi nhỏ trong cấu hình có thể ảnh hưởng đến toàn bộ môi trường. Ví dụ:

- Một điều kiện trigger sai khiến job triển khai production chạy trên pull request.
- Một quyền mặc định quá rộng cho phép job kiểm tra mã nguồn ghi vào repository hoặc thay đổi môi trường.
- Một giá trị cấu hình sai khiến ứng dụng kết nối nhầm database.
- Một manifest Kubernetes vô tình cấp quyền đặc quyền hoặc mount đường dẫn nhạy cảm.
- Một Terraform plan thay đổi tài nguyên ngoài phạm vi dự kiến.
- Một bước kiểm tra bị bỏ qua do điều kiện hoặc path filter không chính xác.
- Một tham chiếu secret sai khiến ứng dụng khởi động không thành công hoặc làm lộ dữ liệu trong log.

Vì vậy, kiểm tra cấu hình trước khi triển khai là một phần của CI/CD. Mục tiêu là phát hiện vấn đề khi thay đổi còn nằm trong phạm vi review, xác định rõ cấu hình nào được phép đi tiếp và giữ lại bằng chứng để truy vết.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, pipeline cần có khả năng kiểm tra tự động, quản lý artifact và môi trường, áp dụng cổng chất lượng, bảo vệ bí mật, xác minh sau triển khai và quay lui. Việc kiểm tra cấu hình kết nối các năng lực đó: nó giúp bảo đảm pipeline và cấu hình triển khai thực hiện đúng chính sách trước khi tác động đến hệ thống thật.

## 2. Kiểm tra cấu hình gồm nhiều lớp

Không nên xem việc parse được YAML là bằng chứng cấu hình an toàn. Một quy trình kiểm tra đầy đủ cần xem xét nhiều lớp.

| Lớp kiểm tra | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Cú pháp | Tệp có được phân tích đúng không? | YAML hợp lệ, không sai thụt lề hoặc cấu trúc |
| Schema | Các trường và kiểu dữ liệu có đúng hợp đồng không? | Workflow có khai báo đúng trường, Kubernetes manifest đúng API schema |
| Ngữ nghĩa | Các giá trị có hợp lý và tham chiếu có tồn tại không? | Job phụ thuộc đúng job, biến môi trường được khai báo, image có phiên bản |
| Bảo mật | Cấu hình có tạo quyền hoặc bề mặt tấn công quá lớn không? | Không lộ secret, quyền tối thiểu, không chạy container đặc quyền |
| Vận hành | Cấu hình có thể chạy ổn định và khôi phục không? | Có health check, timeout, resource limit và rollback plan |
| Chính sách | Thay đổi có đáp ứng tiêu chuẩn của tổ chức không? | Không triển khai production khi thiếu phê duyệt hoặc còn vi phạm bị chặn |

Các lớp này bổ sung cho nhau. Một file có thể hợp lệ về cú pháp và schema nhưng vẫn sai về ngữ nghĩa. Một manifest có thể chạy được nhưng vi phạm chính sách bảo mật. Một lần triển khai có thể thành công nhưng không có cơ chế xác minh hoặc khôi phục.

Một quy trình thực tế thường chạy kiểm tra rẻ và nhanh trước, sau đó mới đến kiểm tra cần môi trường hoặc quyền truy cập đặc biệt.

## 3. Xác định phạm vi cấu hình cần kiểm tra

Một hệ thống CI/CD thường có nhiều loại cấu hình, mỗi loại cần bộ kiểm tra phù hợp.

| Loại cấu hình | Nội dung thường gặp | Hướng kiểm tra |
|---|---|---|
| Pipeline workflow | Trigger, job, step, dependency, condition, permission | YAML parser, schema validator, linter, kiểm tra luồng |
| Build và test | Toolchain, dependency, cache, test task | Kiểm tra phiên bản, lockfile, build thử và test |
| Container | Dockerfile, base image, build argument, runtime user | Dockerfile linter, image scan, kiểm tra digest |
| Kubernetes | Deployment, Service, Ingress, ConfigMap, Secret reference | Schema validation, manifest lint, policy test |
| Helm hoặc Kustomize | Chart, values, overlay, template | Lint, render, schema và policy trên đầu ra |
| Infrastructure as Code | Terraform, Pulumi hoặc cấu hình hạ tầng tương tự | Format, validate, plan, policy as code |
| Cấu hình ứng dụng | Endpoint, feature flag, timeout, connection pool | Schema, giá trị bắt buộc, tương thích môi trường |
| Chính sách phát hành | Environment, approval, rollout, rollback | Kiểm tra quyền, điều kiện, policy và audit trail |

Cần xác định rõ file nào là nguồn cấu hình, file nào được sinh ra và file nào là artifact triển khai. Ví dụ, Helm template tạo manifest cuối cùng từ chart và values. Nên kiểm tra cả chart nguồn lẫn manifest đã render, vì lỗi có thể xuất hiện sau khi ghép nhiều values hoặc template.

Tương tự, một pipeline có thể gọi reusable workflow hoặc script bên ngoài. Kiểm tra riêng file workflow gọi không đủ nếu chưa kiểm tra workflow được tái sử dụng, phiên bản action, script và dependency mà nó gọi.

## 4. Xây dựng chuỗi kiểm tra từ nhanh đến sâu

Một chuỗi kiểm tra hợp lý có thể đi theo thứ tự sau:

1. Parse cú pháp và format.
2. Kiểm tra schema của từng loại file.
3. Lint và kiểm tra ngữ nghĩa.
4. Kiểm tra bảo mật, secret và dependency.
5. Render hoặc mô phỏng đầu ra.
6. Kiểm tra policy trên cấu hình cuối cùng.
7. Thực hiện dry run hoặc plan trong môi trường kiểm soát.
8. Chỉ cho phép triển khai thật khi các cổng bắt buộc đạt.

~~~mermaid
flowchart TD
    A["Pull request thay đổi cấu hình"] --> B["Parse và format"]
    B --> C{"Cú pháp hợp lệ?"}
    C -- "Không" --> X["Báo lỗi, chặn hợp nhất"]
    C -- "Có" --> D["Schema và lint"]
    D --> E{"Cấu trúc và ngữ nghĩa đạt?"}
    E -- "Không" --> X
    E -- "Có" --> F["Secret, dependency và security scan"]
    F --> G{"Không có vi phạm bị chặn?"}
    G -- "Không" --> X
    G -- "Có" --> H["Render, plan hoặc dry run"]
    H --> I["Policy và review kết quả"]
    I --> J{"Đủ điều kiện phát hành?"}
    J -- "Không" --> X
    J -- "Có" --> K["Phê duyệt môi trường"]
    K --> L["Triển khai artifact đã xác định"]
    L --> M["Health check và xác minh sau triển khai"]
~~~

Không phải loại cấu hình nào cũng cần mọi bước. Ví dụ, thay đổi mô tả trong tài liệu không cần Terraform plan. Nhưng thay đổi quyền IAM hoặc manifest production cần kiểm tra sâu hơn một thay đổi label. Bộ kiểm tra nên được chọn theo loại file và mức độ ảnh hưởng.

## 5. Kiểm tra cú pháp, schema và ngữ nghĩa

### 5.1. Kiểm tra cú pháp

Parser xác nhận file có thể được đọc theo định dạng khai báo. Với YAML, lỗi thường gặp gồm:

- Thụt lề không nhất quán.
- Dùng tab ở vị trí yêu cầu space.
- Thiếu dấu hai chấm hoặc dấu nháy.
- Giá trị chứa ký tự đặc biệt nhưng không được quote đúng.
- Khóa trùng lặp khiến một giá trị bị ghi đè tùy parser.
- Dùng kiểu dữ liệu ngoài dự kiến, ví dụ chuỗi được hiểu thành boolean hoặc null.

Cần dùng parser phù hợp với định dạng và phiên bản đặc tả mà nền tảng thực sự hỗ trợ. YAML 1.1 và YAML 1.2 có khác biệt trong cách diễn giải một số giá trị như true, false, yes, no hoặc on, off. Vì vậy, không nên chỉ dựa vào một trình đọc YAML chung để kết luận workflow của nền tảng sẽ có cùng ý nghĩa.

Linter có thể kiểm tra format và phát hiện một số lỗi thường gặp. Tuy nhiên, linter không thay thế schema validator hoặc kiểm tra ngữ nghĩa.

### 5.2. Kiểm tra schema

Schema mô tả cấu trúc được phép của một loại cấu hình: trường nào bắt buộc, kiểu dữ liệu là gì, giá trị nào được chấp nhận và trường nào không hợp lệ.

Ví dụ:

- Workflow của nền tảng CI có schema riêng cho trigger, job, step và permission.
- Kubernetes có OpenAPI schema theo phiên bản API.
- Helm chart có thể khai báo schema cho values.
- Cấu hình ứng dụng có thể được kiểm tra bằng JSON Schema.
- Terraform provider định nghĩa kiểu và thuộc tính của resource.

Schema validation giúp phát hiện lỗi như gõ sai tên trường, đặt số vào trường cần chuỗi hoặc thiếu thuộc tính bắt buộc. Nhưng schema thường không chứng minh được rằng tham chiếu bên ngoài tồn tại hoặc giá trị phù hợp với môi trường.

### 5.3. Kiểm tra ngữ nghĩa

Ngữ nghĩa xem xét mối quan hệ giữa các thành phần và ý nghĩa của cấu hình.

Ví dụ với pipeline:

- Job có khai báo dependency đến một job không tồn tại không?
- Điều kiện có khiến job phát hành chạy khi chưa có artifact không?
- Một step có tham chiếu output của job khác đúng cách không?
- Trigger có chạy trên đúng loại sự kiện không?
- Có đường đi nào bỏ qua kiểm tra bắt buộc không?
- Một job triển khai có thể chạy song song với job tạo artifact không?

Ví dụ với cấu hình triển khai:

- Deployment có tham chiếu đúng Service không?
- Selector của Service có khớp label của Pod không?
- Volume mount có tham chiếu volume được khai báo không?
- Secret reference có tên và key hợp lệ không?
- Readiness probe có dùng đúng cổng và đường dẫn không?
- Resource request và limit có nằm trong phạm vi cho phép không?

Những lỗi này có thể không làm parser hoặc schema thất bại. Vì vậy, cần linter chuyên biệt, kiểm tra liên kết và test trên cấu hình đã render.

## 6. Kiểm tra workflow và logic pipeline

Workflow là mã điều khiển quá trình tự động. Cần xem xét cả cấu trúc lẫn đường đi thực thi.

### 6.1. Trigger và điều kiện chạy

Kiểm tra trigger để bảo đảm pipeline chạy đúng thời điểm và không mở đường triển khai ngoài ý muốn.

Một số điểm cần xác minh:

- Pull request chỉ kích hoạt job phù hợp với mã chưa được tin cậy.
- Push lên nhánh tích hợp chạy các kiểm tra cần thiết.
- Tag phát hành được xác minh theo quy ước.
- Job production chỉ chạy theo sự kiện và quyền được phép.
- Path filter không vô tình bỏ qua status check bắt buộc.
- Điều kiện nhánh, tag và event không mâu thuẫn nhau.
- Thay đổi từ fork không được cấp secret hoặc quyền triển khai.

Nên kiểm tra cả trường hợp dương tính và âm tính. Ví dụ: tag hợp lệ phải kích hoạt release workflow; tag sai định dạng phải bị từ chối. Pull request phải chạy kiểm tra nhưng không được triển khai production.

### 6.2. Dependency giữa job và step

Một pipeline có thể có nhiều job chạy song song. Cần xác nhận dependency đúng với thứ tự dữ liệu và điều kiện chất lượng.

Ví dụ, job deploy phải phụ thuộc vào job tạo artifact và kiểm tra artifact. Nếu chỉ phụ thuộc vào job test nhưng không phụ thuộc vào publish, pipeline có thể triển khai một artifact cũ hoặc không xác định.

Cũng cần kiểm tra các trường hợp:

- Job bị skip do condition nhưng job phía sau vẫn chạy.
- Job có thể tiếp tục sau lỗi do cấu hình cho phép.
- Output bị thiếu hoặc không được truyền qua dependency.
- Retry tạo ra artifact khác nhưng metadata không được cập nhật.
- Hai job triển khai đồng thời vào cùng một môi trường.

### 6.3. Timeout, retry và concurrency

Timeout giúp pipeline không chờ vô hạn khi dịch vụ phụ thuộc bị treo. Retry hữu ích với lỗi tạm thời, nhưng không nên lặp lại vô hạn hoặc che giấu lỗi cấu hình.

Cần phân biệt:

- Lỗi tạm thời của mạng hoặc registry có thể retry có giới hạn.
- Lỗi cú pháp, permission hoặc schema cần sửa cấu hình.
- Lỗi kiểm thử xác định cần được điều tra, không nên retry chỉ để có kết quả xanh.
- Job triển khai cần cơ chế khóa hoặc concurrency phù hợp để tránh hai phiên bản cùng ghi vào một môi trường.

Một lần retry phải giữ được khả năng truy vết. Nếu lần chạy lại tạo artifact mới, pipeline cần lưu định danh mới và không nhầm nó với artifact của lần chạy trước.

## 7. Kiểm tra cấu hình Kubernetes, Helm và container

Các manifest triển khai thường được tạo từ nhiều nguồn: template, values theo môi trường, overlay và biến được truyền lúc chạy. Kiểm tra tệp nguồn chưa đủ; cần kiểm tra đầu ra cuối cùng.

### 7.1. Render trước khi triển khai

Với Helm, nhóm có thể chạy lint và render template thành manifest để xem tài nguyên thực tế được tạo ra. Với Kustomize, có thể build overlay để tạo đầu ra cuối cùng. Manifest đã render nên được lưu như một phần bằng chứng của lần kiểm tra hoặc được gắn với commit và artifact tương ứng.

Cần xác minh:

- Namespace và resource name đúng môi trường.
- Image tham chiếu đến phiên bản hoặc digest được phép.
- Service selector khớp với Pod label.
- Port và targetPort đúng với ứng dụng.
- ConfigMap và Secret reference tồn tại theo hợp đồng.
- Probe có timeout, period và threshold hợp lý.
- Resource request/limit phù hợp với tải và quota.
- Replica, rollout strategy và disruption policy đáp ứng yêu cầu sẵn sàng.

### 7.2. Kiểm tra bảo mật manifest

Một số cấu hình cần được policy kiểm soát:

- Container không chạy privileged nếu không có ngoại lệ được duyệt.
- Tránh chạy bằng root khi không cần thiết.
- Không mount hostPath hoặc socket nhạy cảm tùy tiện.
- Filesystem có thể đặt read-only nếu ứng dụng hỗ trợ.
- Linux capabilities chỉ được cấp khi cần.
- Service account không nhận quyền cluster-wide ngoài phạm vi công việc.
- Network policy giới hạn luồng giao tiếp cần thiết.
- Image đến từ registry được tin cậy và có định danh rõ ràng.
- Secret không được ghi trực tiếp vào manifest, repository hoặc log.

Policy có thể được áp dụng bằng công cụ như Conftest/OPA, Kyverno hoặc cơ chế admission policy của nền tảng. Cần kiểm tra trên manifest đã render, vì giá trị cuối cùng có thể được tạo bởi template hoặc override.

### 7.3. Kiểm tra container image

Dockerfile và image cần được kiểm tra riêng:

- Base image có nguồn tin cậy và phiên bản được kiểm soát.
- Dependency được pin theo chiến lược phù hợp.
- Build không nhúng secret vào layer hoặc build argument có thể bị lưu lại.
- Image không chứa tool hoặc package không cần thiết.
- Runtime user và quyền filesystem được giới hạn.
- Image được scan lỗ hổng và có SBOM khi quy trình yêu cầu.
- Artifact phát hành được tham chiếu bằng digest nếu cần bảo đảm tính bất biến.

Một image scan không thể chứng minh ứng dụng an toàn tuyệt đối. Kết quả cần được đánh giá theo mức độ nghiêm trọng, khả năng khai thác, phạm vi sử dụng và chính sách ngoại lệ.

## 8. Kiểm tra Infrastructure as Code trước khi thay đổi hạ tầng

Với Terraform, Pulumi hoặc công cụ tương tự, cấu hình có thể tạo hoặc thay đổi tài nguyên thật trên cloud. Cần phân biệt các mức kiểm tra.

| Mức | Ví dụ | Điều có thể phát hiện |
|---|---|---|
| Format | terraform fmt -check | Cách trình bày không nhất quán |
| Validate | terraform validate | Lỗi cấu trúc và cấu hình trong module |
| Static analysis | Linter hoặc IaC scanner | Một số cấu hình rủi ro và vi phạm thực hành |
| Plan | terraform plan | Tài nguyên dự kiến thêm, sửa hoặc xóa |
| Policy check | OPA/Conftest hoặc policy engine | Quy tắc tổ chức về vùng, quyền, mã hóa, mạng và chi phí |
| Review | Người có trách nhiệm xem plan | Tác động nghiệp vụ và rủi ro ngoài dự kiến |

Plan là bằng chứng quan trọng nhưng cần được đọc cẩn thận. Một thay đổi có thể thay thế resource, xóa dữ liệu hoặc mở rộng quyền. Nhóm nên chú ý các hành động destroy/replace, thay đổi IAM, security group, route, storage encryption, database và public exposure.

Một số nguyên tắc:

- Plan phải dùng đúng workspace, backend và biến của môi trường mục tiêu.
- Không đưa giá trị nhạy cảm từ plan vào log hoặc artifact công khai.
- Dùng quyền đọc hoặc quyền lập kế hoạch tối thiểu có thể; tách quyền apply.
- Lưu plan gắn với commit và thời điểm tạo.
- Nếu trạng thái hạ tầng thay đổi sau khi plan được tạo, cần tạo lại plan trước khi apply.
- Production apply cần approval và audit trail theo chính sách.
- Không tự động apply chỉ vì lệnh plan trả exit code thành công.

Lưu ý: plan có thể truy cập state và gọi data source hoặc API của provider. Vì vậy, dù chưa thay đổi tài nguyên, vẫn cần kiểm soát credential, quyền đọc và dữ liệu được ghi vào log.

## 9. Kiểm tra bí mật, quyền và chuỗi cung ứng

### 9.1. Phát hiện secret

Secret scanning tìm các mẫu token, private key, password hoặc credential bị commit nhầm. Có thể kết hợp:

- Quét nội dung thay đổi trong pull request.
- Quét toàn repository và lịch sử khi cần.
- Quét artifact hoặc image nếu quy trình yêu cầu.
- Kiểm tra log và output để tránh secret bị in ra.
- Phát hiện cấu hình chứa giá trị credential thay vì tham chiếu secret manager.

Nếu phát hiện secret thật đã bị commit, xóa dòng khỏi commit mới chưa đủ. Cần thu hồi hoặc xoay vòng credential, đánh giá lịch sử và các bản sao có thể đã được tạo.

### 9.2. Kiểm tra quyền của pipeline

Pipeline có thể sở hữu quyền đọc repository, tạo release, ghi registry, truy cập cloud hoặc triển khai cluster. Quyền nên được cấp theo từng job và từng môi trường.

Các điểm cần kiểm tra:

- Job lint và test chỉ có quyền cần thiết để đọc mã.
- Job publish chỉ có quyền ghi vào đúng registry hoặc package.
- Job deploy chỉ có quyền vào đúng namespace hoặc tài nguyên được quản lý.
- Quyền production không được cấp cho pull request không đáng tin cậy.
- Credential có thời hạn ngắn được ưu tiên nếu nền tảng hỗ trợ.
- OIDC hoặc workload identity có thể giới hạn danh tính theo repository, branch, environment và workflow.
- Secret chỉ được cung cấp cho job cần dùng, không truyền qua output hoặc log.

### 9.3. Pin dependency của pipeline

Một pipeline có thể bị thay đổi hành vi nếu action, plugin, image hoặc script bên ngoài được tham chiếu bằng tag có thể di chuyển.

Để tăng tính ổn định:

- Pin action hoặc plugin quan trọng bằng commit SHA khi nền tảng hỗ trợ.
- Pin container image bằng digest cho các bước nhạy cảm.
- Kiểm soát phiên bản toolchain.
- Review thay đổi dependency pipeline.
- Cập nhật định kỳ theo quy trình có kiểm thử.
- Ghi lại phiên bản công cụ đã dùng để tạo artifact.

Pin phiên bản giúp tăng khả năng tái lập nhưng không tự bảo đảm dependency an toàn. Vẫn cần theo dõi lỗ hổng, nguồn phát hành và cập nhật theo chính sách.

## 10. Policy as Code: biến yêu cầu thành điều kiện kiểm tra

Policy as Code là cách biểu diễn quy tắc tổ chức bằng cấu hình hoặc mã có thể thực thi tự động. Ví dụ:

- Không cho phép workload production chạy privileged.
- Không cho phép storage quan trọng không mã hóa.
- Không mở cổng quản trị ra Internet.
- Không dùng image tag latest cho release.
- Mọi deployment production phải có approval.
- Mọi artifact phát hành phải có commit provenance.
- Resource phải có owner, environment và cost center theo quy ước.
- Không cho phép job production chạy từ pull request bên ngoài.

Policy cần có mức độ rõ ràng:

- **Block:** vi phạm khiến pipeline dừng.
- **Warn:** vi phạm được báo nhưng có thể đi tiếp trong phạm vi cho phép.
- **Exception:** cho phép ngoại lệ có lý do, người phê duyệt, phạm vi và thời hạn.

Không nên biến mọi cảnh báo thành lỗi chặn. Policy quá nghiêm hoặc thiếu bối cảnh sẽ tạo ra nhiều ngoại lệ thủ công. Ngược lại, policy chỉ cảnh báo với một rủi ro nghiêm trọng có thể khiến cổng chất lượng mất tác dụng.

Một ngoại lệ nên ghi lại:

1. Quy tắc nào được miễn.
2. Tài nguyên hoặc môi trường nào chịu ảnh hưởng.
3. Lý do và đánh giá rủi ro.
4. Người phê duyệt.
5. Biện pháp giảm thiểu.
6. Thời điểm hết hạn hoặc ngày đánh giá lại.

### 10.1. Ví dụ policy dạng mã giả

~~~yaml
policy:
  production:
    require_approval: true
    require_artifact_digest: true
    require_commit_provenance: true

  container:
    deny_privileged: true
    deny_latest_tag: true
    require_non_root: true

  infrastructure:
    require_encryption: true
    deny_public_admin_ports: true
    require_owner_tag: true

  secrets:
    deny_plaintext_credentials: true
    require_secret_reference: true
~~~

Đây là cấu trúc minh họa, không phải schema của một công cụ policy cụ thể. Khi triển khai, cần chuyển từng quy tắc thành policy có thể đánh giá, kiểm thử và giải thích.

## 11. Dry run, preview và kiểm thử trong môi trường kiểm soát

Sau static validation, một số thay đổi cần được mô phỏng để biết hệ thống sẽ thực hiện điều gì.

Các khái niệm sau có phạm vi khác nhau:

| Cách kiểm tra | Ý nghĩa | Giới hạn |
|---|---|---|
| Local render | Tạo đầu ra từ template và values mà không gọi môi trường thật | Không chứng minh API server hoặc cloud chấp nhận thay đổi |
| Dry run phía client | Mô phỏng hoặc kiểm tra cục bộ theo khả năng công cụ | Có thể thiếu thông tin từ môi trường đích |
| Server-side dry run | Gửi yêu cầu kiểm tra đến API server nhưng không lưu thay đổi nếu hệ thống hỗ trợ | Cần quyền truy cập; admission webhook và cluster version có thể ảnh hưởng kết quả |
| Infrastructure plan | Hiển thị thay đổi hạ tầng dự kiến | Phụ thuộc state, provider và dữ liệu đọc tại thời điểm plan |
| Ephemeral environment | Triển khai vào môi trường tạm có phạm vi giới hạn | Có chi phí, dữ liệu và dependency riêng; không hoàn toàn giống production |
| Staging deployment | Xác minh trên môi trường gần production | Có thể khác production về tải, quyền, dữ liệu và dịch vụ phụ thuộc |

Dry run không phải một bảo đảm tuyệt đối. Ví dụ, render Helm thành công không chứng minh cluster có đủ quota hoặc quyền. Terraform plan không chứng minh thao tác apply sẽ thành công nếu state thay đổi sau đó. Server-side dry run có thể phát hiện lỗi admission nhưng vẫn không kiểm chứng hành vi ứng dụng khi chạy.

Nên chọn mức mô phỏng theo rủi ro. Thay đổi tài liệu pipeline có thể chỉ cần parser và linter. Thay đổi policy network hoặc database cần plan, review và kiểm thử trong môi trường an toàn.

## 12. Thiết kế cổng trước production

Một cổng production tốt cần xác định bằng chứng nào phải có trước khi triển khai.

Ví dụ:

- Workflow và cấu hình được parse, validate và lint thành công.
- Các kiểm tra bảo mật bắt buộc đạt ngưỡng.
- Manifest hoặc IaC đã render và được policy kiểm tra.
- Artifact có digest, commit và provenance.
- Artifact đã được xác minh ở môi trường trước.
- Plan hoặc deployment preview không có thay đổi ngoài dự kiến.
- Có người hoặc danh tính được phép phê duyệt.
- Cấu hình và secret reference của môi trường đích đáp ứng hợp đồng.
- Có health check, rollout timeout và phương án khôi phục.

Cổng cần áp dụng trên đúng artifact và đúng cấu hình sẽ triển khai. Nếu sau khi kiểm tra, pipeline build lại image hoặc render lại manifest bằng đầu vào khác, bằng chứng trước đó có thể không còn tương ứng với nội dung phát hành.

Nên lưu các dữ liệu sau trong release record:

- Commit SHA.
- Artifact digest và registry.
- Pipeline run ID.
- Phiên bản toolchain.
- Kết quả test và scan.
- Policy version.
- Manifest hoặc plan đã được duyệt, nếu có.
- Người phê duyệt và thời điểm.
- Môi trường đích.
- Kết quả xác minh sau triển khai.

## 13. Ví dụ workflow kiểm tra trước khi deploy

Ví dụ dưới đây minh họa một workflow GitHub Actions để kiểm tra cấu hình Kubernetes và Helm trước khi cho phép bước triển khai. Các action và tool cần được cài đặt hoặc pin phiên bản theo chính sách của repository. Trong môi trường yêu cầu bảo đảm chuỗi cung ứng cao, nên pin action bằng commit SHA thay vì chỉ dùng tag minh họa.

~~~yaml
name: Validate deployment configuration

on:
  pull_request:
    paths:
      - ".github/workflows/**"
      - "deploy/**"
      - "policy/**"
  push:
    branches:
      - main
  workflow_dispatch:
    inputs:
      artifact_digest:
        description: Immutable digest of an already validated artifact
        required: true
        type: string

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Check workflow syntax
        run: actionlint

      - name: Lint YAML files
        run: yamllint .github/workflows deploy

      - name: Lint Helm chart
        run: helm lint deploy/chart

      - name: Render staging manifests
        run: |
          helm template application deploy/chart \
            --values deploy/values/staging.yaml \
            > rendered-staging.yaml

      - name: Validate Kubernetes schema
        run: kubeconform -strict -summary rendered-staging.yaml

      - name: Evaluate deployment policies
        run: conftest test rendered-staging.yaml --policy policy/

      - name: Scan configuration
        run: checkov -f rendered-staging.yaml

  deploy:
    needs: validate
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Deploy approved artifact
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: ./deploy/deploy-approved-artifact.sh --digest "$ARTIFACT_DIGEST"
~~~

Đây là ví dụ cấu trúc để thảo luận, không phải workflow production hoàn chỉnh. Sự kiện workflow_dispatch yêu cầu người vận hành cung cấp digest bất biến của artifact đã được xác minh; job deploy chỉ chạy khi thao tác được khởi chạy từ nhánh main. Environment production cần bật quy tắc bảo vệ và người duyệt phù hợp. Script triển khai phải xác minh digest, provenance và quyền trước khi thay đổi môi trường. Action checkout trong ví dụ dùng tag minh họa; repository có yêu cầu bảo đảm chuỗi cung ứng cao nên pin action bằng commit SHA. Ví dụ này cũng cho thấy kiểm tra logic điều kiện và đầu vào quan trọng ngang với kiểm tra cú pháp YAML.

Một cấu hình hoàn chỉnh hơn cần truyền artifact digest đã được tạo và xác minh từ pipeline phát hành, kiểm tra quyền và environment protection, đồng thời dùng script triển khai có kiểm soát. Không nên build lại artifact trong job production.

## 14. Kiểm thử chính bộ kiểm tra cấu hình

Validator cũng là mã và có thể sai. Nếu policy hoặc linter không được kiểm thử, pipeline có thể chặn thay đổi hợp lệ hoặc cho qua thay đổi nguy hiểm.

Có thể kiểm thử theo ba nhóm:

**Test dương tính**

- Một cấu hình hợp lệ phải vượt qua parser và schema.
- Một manifest có quyền tối thiểu phải vượt policy.
- Một artifact có digest và provenance hợp lệ phải được chấp nhận.
- Một deployment request đủ điều kiện phải đi qua cổng.

**Test âm tính**

- Cấu hình sai cú pháp phải thất bại.
- Secret dạng plaintext phải bị phát hiện.
- Container privileged phải bị policy chặn.
- Image tag latest phải bị từ chối nếu chính sách cấm.
- Deployment production thiếu approval phải không được chạy.
- Plan xóa database hoặc mở cổng quản trị ngoài dự kiến phải bị yêu cầu review hoặc chặn.

**Test ngoại lệ**

- Một ngoại lệ có người phê duyệt và chưa hết hạn được xử lý theo policy.
- Ngoại lệ hết hạn phải bị từ chối.
- Ngoại lệ chỉ áp dụng cho đúng tài nguyên và môi trường.
- Vi phạm nghiêm trọng không bị che bởi một ngoại lệ rộng.

Có thể lưu các mẫu cấu hình hợp lệ và không hợp lệ trong repository. Khi thay đổi policy, chạy lại toàn bộ bộ mẫu để bảo đảm quy tắc vẫn hoạt động đúng.

## 15. Xử lý kết quả kiểm tra và ngoại lệ

Một thông báo lỗi tốt cần giúp người sửa hiểu:

- File và vị trí có vấn đề.
- Quy tắc nào bị vi phạm.
- Vì sao quy tắc tồn tại.
- Cách sửa hoặc tài liệu liên quan.
- Có thể yêu cầu ngoại lệ không và ai có quyền phê duyệt.

Không nên chỉ trả về một thông báo chung như configuration invalid. Cũng không nên in toàn bộ environment, credential hoặc nội dung secret khi debug.

Khi kiểm tra thất bại:

1. Chặn bước phụ thuộc nếu vi phạm thuộc loại bắt buộc.
2. Giữ lại log và báo cáo đã được làm sạch.
3. Gắn kết quả với commit và pipeline run.
4. Cho phép chạy lại sau khi cấu hình được sửa.
5. Ghi nhận ngoại lệ theo quy trình nếu có lý do hợp lệ.
6. Theo dõi các lỗi lặp lại để cải thiện validator hoặc tài liệu.

Nếu một kiểm tra thường xuyên thất bại giả, cần xác định nguyên nhân và sửa validator. Việc thêm skip hoặc continue-on-error cho job quan trọng có thể làm mất tác dụng của quality gate.

## 16. Xác minh sau triển khai vẫn là bước bắt buộc

Một cấu hình vượt qua static validation và dry run vẫn có thể thất bại khi chạy thật do khác biệt về quyền, quota, trạng thái dịch vụ phụ thuộc, dữ liệu hoặc tải.

Sau triển khai, cần xác minh ít nhất:

- Deployment hoặc resource đã đạt trạng thái sẵn sàng.
- Health endpoint và smoke test hoạt động.
- Ứng dụng đọc được cấu hình và tham chiếu secret cần thiết.
- Tỷ lệ lỗi và độ trễ không tăng bất thường.
- Luồng nghiệp vụ quan trọng hoàn tất.
- Log, metrics và traces có đủ ngữ cảnh để truy vết phiên bản.
- Rollout dừng hoặc rollback khi điều kiện chính sách bị vi phạm.

Nếu triển khai theo canary, cần đặt ngưỡng và khoảng quan sát trước khi tăng lưu lượng. Nếu tín hiệu xấu đi, pipeline phải dừng promotion và kích hoạt quy trình khôi phục đã định nghĩa.

Rollback cần dùng artifact đã lưu và xác minh tính tương thích dữ liệu. Với thay đổi database hoặc schema, có thể cần roll-forward hoặc biện pháp phục hồi dữ liệu thay vì chỉ triển khai lại phiên bản cũ.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ parse YAML rồi cho triển khai | Bỏ sót lỗi schema, logic và bảo mật | Thêm schema, semantic, security và policy validation |
| Kiểm tra file nguồn nhưng không kiểm tra output render | Giá trị ghép từ template có thể sai | Render theo từng môi trường rồi kiểm tra đầu ra |
| Dùng secret production trong pull request | Mã chưa tin cậy có thể đọc hoặc làm lộ secret | Tách job, giới hạn permission và dùng credential theo môi trường |
| Dùng tag latest cho image phát hành | Nội dung image có thể thay đổi mà cấu hình không đổi | Pin version hoặc digest |
| Terraform plan tự động apply ngay | Thay đổi hạ tầng có thể vượt review | Tách plan, policy, approval và apply |
| Dry run được xem là bảo đảm tuyệt đối | Bỏ qua khác biệt của môi trường thật | Kết hợp plan, staging, post-deploy verification |
| Policy chỉ có thông báo chung | Người sửa khó biết cách khắc phục | Trả lỗi có quy tắc, vị trí và hướng dẫn |
| Cho phép skip mọi kiểm tra khi khẩn cấp | Ngoại lệ trở thành đường đi mặc định | Quy định ngoại lệ có phạm vi, người duyệt và thời hạn |
| Log toàn bộ biến môi trường khi debug | Có thể lộ token và credential | Redact dữ liệu nhạy cảm, chỉ log thông tin cần thiết |
| Không kiểm thử validator | Policy có thể chặn sai hoặc bỏ lọt lỗi | Duy trì test dương tính, âm tính và ngoại lệ |

## 18. Checklist trước khi cho phép cấu hình đi vào production

**Cấu trúc và ngữ nghĩa**

- [ ] Parser đọc được toàn bộ file.
- [ ] Schema phù hợp với phiên bản nền tảng.
- [ ] Linter không có lỗi bắt buộc.
- [ ] Tham chiếu job, output, file, resource và dependency hợp lệ.
- [ ] Trigger và condition đã được kiểm tra ở cả trường hợp cho phép và từ chối.

**Bảo mật và quyền**

- [ ] Không có secret plaintext trong repository hoặc output.
- [ ] Job chỉ có quyền tối thiểu.
- [ ] Mã từ fork hoặc nguồn chưa tin cậy không nhận credential nhạy cảm.
- [ ] Action, plugin, image và toolchain quan trọng được pin hoặc kiểm soát phiên bản.
- [ ] Policy bảo mật được chạy trên cấu hình đã render.

**Triển khai và hạ tầng**

- [ ] Manifest, Helm chart hoặc IaC đã được render/plan.
- [ ] Cấu hình môi trường đích được xác minh.
- [ ] Thay đổi destroy/replace hoặc mở quyền đã được review.
- [ ] Artifact có digest và provenance.
- [ ] Có approval cho môi trường production theo chính sách.
- [ ] Không build lại artifact đã được xác minh.

**Vận hành và khôi phục**

- [ ] Có timeout, health check và smoke test.
- [ ] Có điều kiện dừng rollout.
- [ ] Có artifact trước đó hoặc phương án khôi phục.
- [ ] Có log và release record đủ truy vết.
- [ ] Có người chịu trách nhiệm xử lý cảnh báo và ngoại lệ.

Checklist này cần được điều chỉnh theo loại dịch vụ và mức độ ảnh hưởng. Một thay đổi cấu hình tài liệu có thể không cần cùng mức kiểm soát với thay đổi quyền cloud hoặc database production.

## 19. Kết luận

Kiểm tra cấu hình trước khi triển khai cần đi xa hơn việc xác nhận tệp YAML có cú pháp hợp lệ. Pipeline as Code phải được kiểm tra về schema, ngữ nghĩa, bảo mật, quyền, chính sách và tác động vận hành. Với cấu hình tạo ra hạ tầng hoặc tài nguyên triển khai, cần render hoặc plan để review đầu ra thực tế trước khi thay đổi môi trường.

Một luồng đáng tin cậy kết hợp kiểm tra tĩnh, policy as code, mô phỏng có kiểm soát, phê duyệt đúng quyền và xác minh sau triển khai. Mỗi kết quả cần gắn với commit, artifact và phiên bản policy để có thể giải thích vì sao thay đổi được phép đi tiếp. Nhờ vậy, pipeline trở thành cổng chất lượng có bằng chứng, giúp phát hành nhanh nhưng vẫn kiểm soát được tác động lên môi trường thật.
