# Quyền truy cập, secrets và bảo vệ chuỗi cung ứng phần mềm

## Mục tiêu bài học

Trong chương **DevOps và CI/CD trên OCI** của module **CLOUD_PROVIDERS_ORACLE**, bài này giải thích cách giới hạn quyền của pipeline, sử dụng secrets đúng phạm vi và kiểm tra nguồn gốc của gói phần mềm trước khi triển khai.

Trong một tenancy OCI, pipeline có thể đọc Git, tải dependency, gọi Vault, đẩy image và cập nhật workload. Những khả năng đó nối trực tiếp quy trình phát triển với Compute, lưu trữ và cơ sở dữ liệu Oracle. Vì vậy, cần quản lý danh tính CI/CD chặt chẽ như danh tính vận hành hạ tầng.

Sau bài học, bạn có thể:

- Phân biệt người dùng, build pipeline, deployment pipeline và danh tính ứng dụng.
- Thiết kế IAM theo công việc, compartment, tài nguyên và mức độ tin cậy của mã.
- Cấp secret từ OCI Vault mà không ghi giá trị vào Git, log hoặc artifact.
- Bảo vệ mã nguồn, dependency, công cụ build, kho artifact và bước triển khai.
- Phân biệt checksum, chữ ký, SBOM, kết quả quét và provenance.
- Thiết kế các kiểm tra cho trường hợp phải cho phép và trường hợp phải từ chối.
- Xử lý lộ credential hoặc artifact nghi bị thay đổi mà vẫn giữ được bằng chứng điều tra.

Ví dụ xuyên suốt là một dịch vụ Java được build bằng Maven, phát hành JAR hoặc container image và triển khai lên môi trường lab. Các đoạn IAM, YAML và CLI là mẫu học tập; thay placeholder bằng đối tượng thật trong phạm vi lab trước khi sử dụng.

## 1. Chuỗi cung ứng phần mềm có những điểm cần bảo vệ nào?

Chuỗi cung ứng phần mềm bao gồm nhiều hơn repository chứa mã ứng dụng:

~~~mermaid
flowchart LR
    A["Tài khoản và thay đổi Git"] --> B["Mã ứng dụng và cấu hình pipeline"]
    B --> C["Dependency, plugin và toolchain"]
    C --> D["Build runner"]
    D --> E["JAR hoặc container image"]
    E --> F["Kho artifact"]
    F --> G["Kiểm tra chính sách triển khai"]
    G --> H["Workload OCI"]
    I["Vault và khóa ký"] --> D
    J["SBOM, provenance và báo cáo"] --> G
~~~

Một dependency hoặc Maven plugin có thể chạy mã trong build runner. Một người sửa được build spec có thể thay lệnh build. Một người ghi được vào repository artifact có thể thay gói mà bước triển khai sẽ tải. Do đó, chỉ bảo vệ nhánh `main` chưa đủ.

| Điểm tác động | Ví dụ | Hệ quả cần ngăn chặn |
| --- | --- | --- |
| Tài khoản Git | Tài khoản có quyền merge bị chiếm dụng | Mã không được review đi vào nhánh phát hành |
| Cấu hình pipeline | Thay lệnh test bằng lệnh luôn thành công | Artifact chưa đạt kiểm tra được phát hành |
| Dependency/plugin | Thêm thư viện hoặc plugin không được kiểm soát | Mã ngoài dự kiến chạy trong builder |
| Secret | Token bị ghi vào log hoặc image layer | Người đọc log/image sử dụng lại credential |
| Danh tính pipeline | Build được quyền quản lý production | Mã trong build tác động trực tiếp tài nguyên thật |
| Kho artifact | Tag bị trỏ sang image khác | Deploy nhầm nội dung dù tên phiên bản không đổi |
| Bằng chứng | Báo cáo do chính mã chưa tin cậy tự tạo | Bộ phận triển khai tin vào kết quả không xác thực |
| Chính sách triển khai | Cho phép bỏ kiểm tra chữ ký tùy ý | Gói ngoài quy trình đi vào production |

Tách hai mục tiêu: **ngăn hành động không được phép** và **chứng minh gói được triển khai là gói đã qua quy trình tin cậy**. IAM giải quyết một phần mục tiêu thứ nhất; nó không tự chứng minh nội dung artifact an toàn.

## 2. Phân chia danh tính theo công việc và mức độ tin cậy

### 2.1. Những danh tính thường xuất hiện

| Danh tính | Công việc hợp lý | Quyền không nên gộp mặc định |
| --- | --- | --- |
| Lập trình viên | Đẩy nhánh, tạo pull request, xem kết quả build | Quản trị secret production hoặc sửa quyền ký |
| Người quản trị CI/CD | Cấu hình pipeline và source connection | Tự do thay chính sách bảo mật ngoài trách nhiệm |
| Pipeline kiểm tra pull request | Biên dịch, chạy test trên mã đang được đề xuất | Đọc secret phát hành, ký gói hoặc triển khai production |
| Pipeline build phát hành | Build mã đã qua điều kiện tin cậy, xuất artifact | Quản trị IAM hoặc truy cập dữ liệu nghiệp vụ production |
| Danh tính ký/phát hành | Xác minh bằng chứng rồi ký hoặc đưa gói vào kho phát hành | Thực thi tùy ý script từ pull request |
| Deployment pipeline | Đọc gói được chấp nhận và cập nhật môi trường đích | Sửa mã nguồn hoặc thay danh sách khóa tin cậy |
| Danh tính ứng dụng | Đọc/ghi dịch vụ theo nhu cầu runtime | Dùng quyền của builder để truy cập cả tenancy |
| Người quản trị bảo mật | Quản lý chính sách, khóa, ngoại lệ và ứng cứu | Thay đổi không để lại bằng chứng |

“Pipeline kiểm tra PR” và “pipeline phát hành” là vai trò thiết kế. Phải triển khai chúng bằng cấu hình danh tính và quyền thực sự khác nhau, không chỉ đổi tên hai stage.

### 2.2. Resource principal và dynamic group trên OCI

OCI DevOps sử dụng resource principal để pipeline làm việc với các dịch vụ OCI. Dynamic group xác định các tài nguyên được nhận policy tương ứng. Các loại tài nguyên và ví dụ matching rule được Oracle mô tả trong [DevOps IAM Policies](https://docs.oracle.com/en-us/iaas/Content/devops/using/devops_iampolicies.htm).

Ví dụ matching rule cho **một build pipeline phát hành cụ thể**:

~~~text
ALL {
  resource.type = 'devopsbuildpipeline',
  resource.id = 'ocid1.devopsbuildpipeline.oc1..REPLACE_TRUSTED_PIPELINE'
}
~~~

Đặt tên dynamic group là `JavaReleaseBuild`. Mẫu này giúp tránh việc mọi build pipeline trong compartment tự động nhận quyền của pipeline phát hành.

Một dynamic group khác có thể dành cho deployment pipeline, dùng loại tài nguyên `devopsdeploypipeline` và OCID tương ứng. Không gom build, deploy và các tài nguyên không liên quan vào cùng nhóm chỉ để giảm số policy.

OCI ghi nhận CLI/SDK trên build runner có sẵn cơ chế xác thực bằng resource principal của build pipeline. Vì thế, **không khai báo secret trong YAML chưa đủ để ngăn build đọc secret**: mã trong build vẫn có thể gọi API nếu principal còn được IAM cho phép. Xem [Build Runner Runtime Details](https://docs.oracle.com/en-us/iaas/Content/devops/using/runtime_details.htm).

### 2.3. Stage khác nhau không tự tạo ranh giới quyền

Nếu hai bước chạy dưới cùng danh tính có quyền đọc secret hoặc ký gói, việc đặt một bước tên “Verify” trước bước “Sign” không tự thu hồi quyền của bước trước.

Thiết kế đề xuất:

~~~mermaid
flowchart TD
    A["PR hoặc mã chưa được chấp nhận"] --> B["Pipeline kiểm tra: quyền thấp"]
    B --> C["Kết quả kiểm tra cho review"]
    C --> D["Mã được merge qua quy tắc bảo vệ"]
    D --> E["Pipeline phát hành: nguồn và cấu hình được kiểm soát"]
    E --> F["Artifact và bằng chứng gắn với digest"]
    F --> G["Danh tính phát hành kiểm tra điều kiện rồi ký"]
    G --> H["Deployment xác minh digest, signer và chính sách"]
~~~

Nếu dùng hệ thống ký riêng, không cho nó nhận một digest tùy ý rồi ký vô điều kiện. Nó phải kiểm tra artifact đến từ nguồn/build được phép, đạt kiểm tra và có bằng chứng phù hợp. Nếu không, việc tách khóa ra khỏi builder chỉ chuyển vị trí của một công cụ ký dễ bị lạm dụng.

## 3. Viết IAM theo tài nguyên cụ thể

### 3.1. Đọc một policy theo bốn câu hỏi

Một statement cần chỉ rõ:

| Câu hỏi | Thành phần OCI |
| --- | --- |
| Ai được phép? | Group, dynamic group hoặc principal phù hợp |
| Được làm gì? | Verb và resource type |
| Tại đâu? | Tenancy hoặc compartment |
| Với điều kiện nào? | Biến điều kiện mà loại tài nguyên/API hỗ trợ |

Các verb `inspect`, `read`, `use`, `manage` không có cùng ý nghĩa chi tiết cho mọi dịch vụ. Đọc bảng permission/API của resource type thay vì suy rằng `use` luôn chỉ có một tác dụng nhỏ.

### 3.2. Chỉ cấp đọc nội dung secret cần dùng

Giả sử secret token đọc Maven repository nằm trong compartment `BuildSecrets`. Ví dụ policy cho dynamic group của pipeline phát hành:

~~~text
Allow dynamic-group JavaReleaseBuild to read secret-bundles in compartment BuildSecrets where target.secret.id = 'ocid1.vaultsecret.oc1..REPLACE_MAVEN_TOKEN_SECRET'
~~~

Thay tên nhóm, compartment và OCID. Với tenancy dùng định danh group theo identity domain, sử dụng cách ghi tên domain/group phù hợp với cấu hình IAM của tenancy.

`secret-bundles` liên quan đến việc lấy nội dung secret. Đọc metadata secret không đồng nghĩa đọc được giá trị; ngược lại, cấp `manage secret-family` chỉ để tải nội dung là quá rộng. Các resource type, API và điều kiện `target.secret.id` được mô tả trong [Vault, Key Management và Secret Management Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/keypolicyreference.htm).

Statement trên chỉ minh họa quyền đọc một secret; nó không phải bộ policy hoàn chỉnh cho Git, build, registry và triển khai. Nếu dùng external connection, còn phải đáp ứng policy của tích hợp đó.

IAM cấp quyền theo các statement cho phép đang có hiệu lực. Thêm một statement giới hạn theo secret không làm mất một statement rộng đã cấp trước đó. Muốn thu hẹp quyền, phải tìm và xử lý các đường cấp quyền rộng liên quan.

### 3.3. Xác định phạm vi tài nguyên hạ tầng

Ví dụ thiết kế compartment:

~~~text
Tenancy
├── DevOpsLab       # Project và pipeline
├── BuildSecrets    # Credential dành cho build/phát hành
├── ReleaseStore    # Artifact được phát hành
├── AppDev          # Tài nguyên chạy thử
└── AppProd         # Tài nguyên production
~~~

Compartment không tự tạo cách ly mạng và không tự cấm truy cập chéo. Quyền IAM, VCN, routing, luật mạng và quyền ở dịch vụ đích vẫn cần được cấu hình.

Build Java không cần quyền quản lý Compute, volume hoặc Database nếu chỉ biên dịch và chạy test cục bộ. Nếu integration test cần tài nguyên test, cấp riêng phạm vi đó. Không dùng credential quản trị database production để chạy test cho mọi PR.

Với triển khai OKE, quyền gọi API OCI và Kubernetes RBAC là các lớp khác nhau. Với Oracle Database, OCI IAM quản lý tài nguyên dịch vụ không tự thay thế quyền SQL của tài khoản ứng dụng trong database.

### 3.4. Kiểm tra cả quyền gián tiếp

Người có thể sửa pipeline có thể thay lệnh chạy dưới danh tính pipeline. Người sửa dynamic group có thể thay các tài nguyên nhận policy. Người sửa chính sách xác minh có thể thay signer được tin cậy.

Vì vậy, đánh giá đồng thời quyền:

- Sửa pipeline, stage, build source và trigger.
- Sửa script, POM, plugin và cấu hình build.
- Sửa IAM policy và matching rule.
- Sửa secret, phiên bản secret, source connection và kho artifact.
- Sửa khóa ký, chính sách xác minh và cơ chế ngoại lệ.

Một danh tính không trực tiếp đọc secret vẫn có thể gây rủi ro tương đương nếu được sửa cấu hình để chạy mã dưới danh tính có quyền đọc secret.

## 4. Bảo vệ mã nguồn và cấu hình CI/CD

Áp dụng review cho cả mã ứng dụng và các file điều khiển thực thi: `build_spec.yaml`, script shell, POM, parent POM, cấu hình Maven/Gradle, Dockerfile và manifest triển khai.

Với OCI Code Repository, cấu hình approval rules, merge checks và branch protection phù hợp. Oracle có tùy chọn merge qua pull request và kiểm tra trạng thái build; hành vi cụ thể được mô tả tại [Code Repository Settings](https://docs.oracle.com/en-us/iaas/Content/devops/using/reposettings.htm).

Các quy tắc tổ chức cần làm rõ:

- Ai được thay điều kiện merge và danh sách người phê duyệt?
- Build result phải gắn với commit nào?
- Commit mới sau review có cần kiểm tra hoặc review lại không?
- Ai được thay đường dẫn build spec, nguồn Git hoặc tham số chạy?
- Thay đổi security gate, khóa tin cậy và quyền phát hành được review như thế nào?

Không dùng tên branch do người gửi PR cung cấp làm bằng chứng duy nhất rằng mã đáng tin cậy. Trigger và pipeline phát hành cần xác nhận đúng repository, revision và điều kiện nguồn được tổ chức chấp nhận.

Nếu chạy mã từ fork/PR chưa tin cậy, sử dụng danh tính có quyền thấp, không có secret phát hành và không có quyền ký. Cache hoặc workspace từ luồng đó cũng không được tự động đưa sang luồng có đặc quyền.

Các rủi ro do cấu hình pipeline bị thay đổi và secret trong CI/CD được phân tích tại [OWASP CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html). Trong bài này, việc tách danh tính và nguồn tin cậy là thiết kế đề xuất để hạn chế phạm vi tác động.

## 5. Quản lý secrets theo vòng đời

### 5.1. Secret khác với cấu hình thông thường

| Loại dữ liệu | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Cấu hình không bí mật | Region, tên môi trường, cổng HTTP | Có thể quản lý bằng cấu hình phiên bản |
| Định danh tài nguyên | Compartment OCID, secret OCID | Không phải giá trị secret; vẫn hạn chế chia sẻ metadata không cần thiết |
| Credential bên ngoài | Git PAT, token Maven repository | Lưu ở nơi quản lý secret, giới hạn quyền và thời hạn |
| Credential database | Password ứng dụng, credential migration | Tách theo môi trường và mục đích |
| Private key | OCI API signing key, SSH key | Tránh phân phối dài hạn vào runner khi có cơ chế danh tính phù hợp |
| Khóa ký artifact | Khóa dùng xác nhận gói phát hành | Phân tách quyền ký và quyền quản trị |

Mật khẩu đã mã hóa ở nơi lưu vẫn có thể lộ khi được sử dụng. Base64 là biểu diễn dữ liệu, không phải mã hóa bảo mật. Che giá trị trên giao diện cũng không ngăn plugin trong cùng process lấy giá trị đó.

Không coi pipeline parameter, biến thường trong YAML hoặc `exportedVariables` là kho secret. Không đưa password production vào JAR, `application.properties` được đóng gói hoặc image để ứng dụng “có sẵn cấu hình”.

### 5.2. Cấp secret từ OCI Vault cho build tin cậy

Giả sử dự án Maven đã có repository riêng với ID `corporate-maven`. Tài khoản `build-reader` chỉ có quyền đọc dependency cần thiết. Token được lưu trong Vault; pipeline phát hành có quyền đọc đúng secret theo IAM.

Build spec minh họa:

~~~yaml
version: 0.1
component: build
timeoutInSeconds: 1800
shell: bash
failImmediatelyOnError: true

env:
  vaultVariables:
    PRIVATE_MAVEN_TOKEN: "ocid1.vaultsecret.oc1..REPLACE_MAVEN_TOKEN_SECRET"

steps:
  - type: Command
    name: Verify trusted Java source with private dependencies
    timeoutInSeconds: 1200
    command: |
      set -euo pipefail
      set +x
      cd "${OCI_PRIMARY_SOURCE_DIR}"
      : "${PRIVATE_MAVEN_TOKEN:?Private Maven token is unavailable}"
      umask 077
      settings_path="$(mktemp)"
      trap 'rm -f "$settings_path"' EXIT

      cat > "$settings_path" <<'MAVEN_SETTINGS'
      <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
        <servers>
          <server>
            <id>corporate-maven</id>
            <username>build-reader</username>
            <password>${env.PRIVATE_MAVEN_TOKEN}</password>
          </server>
        </servers>
      </settings>
      MAVEN_SETTINGS

      mvn --batch-mode --no-transfer-progress \
        --settings "$settings_path" clean verify
~~~

Thay OCID, tài khoản và cấu hình repository bằng đối tượng lab thật. POM hoặc cấu hình mirror phải sử dụng ID khớp với `corporate-maven`. Đoạn trên minh họa cung cấp credential; nó không tự tạo repository và không bao gồm bước phát hành.

Theo [OCI Build Specification](https://docs.oracle.com/en-us/iaas/Content/devops/using/build_specs.htm), `vaultVariables` tham chiếu secret OCID và đưa nội dung secret vào biến môi trường của mọi step trong build spec. Vault và build pipeline phải thuộc cùng tenancy, với policy truy cập phù hợp.

Các điểm đáng chú ý:

- Secret thật không nằm trong YAML.
- `set +x` tránh shell trace in giá trị khi mở rộng lệnh.
- Kiểm tra biến chỉ báo thiếu credential, không in credential.
- Delimiter heredoc nằm trong dấu nháy đơn, nên Bash giữ nguyên `${env.PRIVATE_MAVEN_TOKEN}` trong settings.
- Maven đọc giá trị biến môi trường khi xử lý settings.
- `umask 077` hạn chế quyền file tạm; `trap` dọn file khi shell đi qua xử lý EXIT.
- Token không được chuyển thành đối số `-Dpassword=...` hoặc output artifact.

Cách nội suy `${env.NAME}` trong settings theo [Maven Settings Reference](https://maven.apache.org/settings.html).

Dù settings không chứa token đã mở rộng, Maven, plugin và process con vẫn có thể đọc biến môi trường. Vì vậy, mẫu chỉ dành cho nguồn và công cụ build được kiểm soát. Dọn file hoặc unset biến sau đó không thu hồi được dữ liệu mà process đã đọc.

### 5.3. Những vị trí thường vô tình giữ secret

| Vị trí | Ví dụ cần tránh |
| --- | --- |
| Log | `printenv`, `env`, shell trace, debug HTTP headers |
| Git | PAT trong URL remote, mật khẩu trong settings hoặc fixture |
| Artifact | File `.env`, wallet, credential trong thư mục đóng gói |
| Image layer | Sao chép secret rồi xóa ở layer sau |
| Cache | Cache cả thư mục cấu hình chứa credential |
| Báo cáo test | Connection string có password |
| Dữ liệu chẩn đoán | Heap dump, core dump hoặc file debug mang token |
| Tham số tiến trình | Credential trong dòng lệnh có thể bị quan sát |

Công cụ che log có thể không nhận diện dạng đã biến đổi, chia nhỏ hoặc mã hóa của một giá trị. Không dùng masking làm lý do cho phép mã chưa tin cậy chạy với secret.

`.gitignore` chỉ tránh theo dõi file chưa được Git quản lý; nó không phát hiện credential trong một file hợp lệ và không xóa lịch sử cũ.

### 5.4. Xoay vòng phải đồng bộ với hệ thống đích

Một quy trình xoay token hoặc password gồm:

1. Xác định consumer, thời hạn, người sở hữu và khả năng hỗ trợ hai credential cùng lúc.
2. Tạo credential mới tại hệ thống đích hoặc bằng cơ chế rotation được hỗ trợ.
3. Lưu phiên bản mới trong Vault, thử với consumer lab/canary.
4. Chuyển consumer sang giá trị mới và xác nhận build/workload mới dùng được.
5. Thu hồi credential cũ tại hệ thống đích.
6. Theo dõi lỗi xác thực và giữ bằng chứng thay đổi.

Vault có các trạng thái phiên bản như current, pending và previous. Phiên bản mới tải lên không nên bị nhầm với phiên bản consumer đang dùng. Oracle giải thích tác động của việc chuyển phiên bản tại [Managing Secrets](https://docs.oracle.com/en-us/iaas/Content/secret-management/Concepts/manage-secrets.htm).

Đổi giá trị trong Vault không tự đổi password trong Oracle Database hay thu hồi PAT trên Git server. Process đang chạy cũng không tự quên token đã nhận. Kiểm chứng rotation bằng consumer mới và xác nhận credential cũ không còn được chấp nhận theo kế hoạch.

Khi secret bị lộ, ưu tiên thu hồi hoặc vô hiệu hóa giá trị đã lộ. Chỉ xóa log hoặc đổi phiên bản Vault trong khi credential cũ vẫn hiệu lực chưa xử lý xong rủi ro.

## 6. Bảo vệ dependency, plugin và môi trường build

### 6.1. Đầu vào không chỉ có thư viện ứng dụng

Đầu vào của bản build Java gồm:

- Dependency trực tiếp và gián tiếp.
- Parent POM, BOM và Maven plugin.
- Maven/Gradle distribution, wrapper và JDK.
- Script tải về khi build.
- Base image và package trong image.
- Công cụ quét, công cụ ký và cấu hình của chúng.

Pin phiên bản các thành phần quan trọng, review thay đổi và sử dụng nguồn tải được kiểm soát. Với container, base image theo digest giúp xác định nội dung cụ thể; vẫn cần kế hoạch cập nhật khi có bản sửa lỗi.

Tránh tải script từ URL thay đổi theo thời gian rồi lập tức chạy mà không kiểm tra nguồn và nội dung. Một checksum tải cùng script từ nơi đã bị kiểm soát bởi kẻ tấn công không tạo bằng chứng độc lập.

Với Maven repository nội bộ, quản lý namespace/tọa độ package, quyền publish và mirror cho cả dependency lẫn plugin. Tên package hoặc phiên bản “trông đúng” chưa chứng minh nguồn phát hành.

### 6.2. Cache và workspace cũng là đầu vào

Cache từ luồng PR có thể chứa dữ liệu bị sửa để tác động đến build phát hành. Phân tách cache theo mức độ tin cậy và quyền ghi, không chỉ theo tên khóa cache.

Runner được tạo lại giúp giảm dữ liệu tồn dư, nhưng không bảo đảm dependency hoặc build spec đáng tin. Mạng riêng cũng không làm mã trong runner trở nên an toàn.

Giới hạn egress theo nguồn cần thiết, kiểm soát proxy và xác thực TLS. Đường truy cập tới Maven repository bên ngoài và tới dịch vụ OCI là các cấu hình mạng khác nhau; Service Gateway không thay cho kết nối tới mọi dịch vụ Internet.

### 6.3. Quét đúng dữ liệu và đúng thời điểm

| Kiểm tra | Mục tiêu | Không thay thế được |
| --- | --- | --- |
| Secret scanning | Tìm credential có thể lọt vào mã/artifact | Thu hồi credential đã lộ |
| Static analysis | Tìm mẫu lỗi trong mã | Kiểm tra nguồn dependency |
| Dependency analysis | Nhận diện thư viện, phiên bản và lỗ hổng đã biết | Đánh giá mọi hành vi độc hại |
| Container scanning | Kiểm tra package/lớp image theo khả năng công cụ | Xác minh signer và nguồn build |
| Malware/policy scan | Phát hiện nội dung hoặc vi phạm cụ thể | Bảo đảm không có mọi dạng tấn công |
| Chữ ký/provenance | Xác thực gói và nguồn phát hành được chấp nhận | Chứng minh không còn lỗi bảo mật |

Gate cần chỉ rõ phạm vi, cơ sở dữ liệu, thời điểm quét, ngưỡng, cách xử lý lỗi công cụ và ngoại lệ có thời hạn. Không chuyển “không quét được” thành “không có lỗ hổng”.

Với lỗ hổng đã biết, cân nhắc mức độ nghiêm trọng, đường khai thác trong ứng dụng, bản sửa và biện pháp giảm thiểu. Ngoại lệ cần gắn với artifact/version, người chịu trách nhiệm và ngày hết hạn.

**Kiểm tra vòng đời dịch vụ OCI trước khi chọn công cụ.** Theo thông báo Oracle đối chiếu ngày 21/11/2026, ADM có kế hoạch ngừng cung cấp như dịch vụ OCI công khai; ngày EOL cuối cùng chưa xác nhận và không sớm hơn 31/12/2026, đồng thời hạn chế onboarding khách hàng ngoài mới được lên kế hoạch từ 10/10/2026. Không mặc định tenancy mới có thể bật ADM theo hướng dẫn cũ. Chọn công cụ phân tích dependency còn được hỗ trợ và lập kế hoạch chuyển đổi cho tích hợp hiện hữu. Nguồn: [Oracle Service Change Announcements](https://docs.oracle.com/en-us/iaas/Content/servicechanges.htm).

## 7. Nhận diện artifact và bằng chứng đi kèm

### 7.1. Phân biệt các loại bằng chứng

| Thành phần | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- |
| Tag hoặc phiên bản | Nhóm gọi bản phát hành là gì? | Có thể bị thay nội dung nếu kho cho phép |
| Digest/checksum | Nội dung byte nào đang được nói tới? | Không tự xác nhận ai tạo nội dung |
| Chữ ký | Chủ thể kiểm soát khóa nào xác nhận nội dung? | Khóa hoặc quy trình ký có thể bị lạm dụng |
| SBOM | Gói có những thành phần nào? | Không chứng minh mọi thành phần an toàn |
| Provenance | Gói được tạo từ nguồn, đầu vào và builder nào? | Phải tin được nơi tạo và tính toàn vẹn bằng chứng |
| Báo cáo test/scan | Kiểm tra gì chạy trên đối tượng nào? | Có thể sai đối tượng hoặc bị làm giả |

Lưu JAR trong Artifact Registry và image trong Container Registry theo quy trình phiên bản của nhóm. Đối chiếu digest sau khi nhận gói, không chỉ đối chiếu tên file.

Hai file `app.jar` có thể khác nội dung. Tag `release-1.4` cũng có thể trỏ tới image khác nếu bị thay. Với triển khai cần tính xác định, dùng digest và lưu liên hệ với phiên bản nghiệp vụ.

### 7.2. SBOM và provenance phục vụ mục đích khác nhau

SBOM theo định dạng công cụ hỗ trợ, như CycloneDX hoặc SPDX, giúp tra cứu thành phần. Provenance mô tả quá trình và nguồn tạo artifact. Khái niệm này được trình bày tại [SLSA Provenance](https://slsa.dev/spec/v1.2/provenance).

Nhóm cần giữ liên hệ ít nhất:

~~~text
Artifact digest
    ├── Repository và revision thực sự được build
    ├── Định danh builder/pipeline và build run
    ├── Cấu hình build cùng đầu vào quan trọng
    ├── SBOM của đúng sản phẩm
    ├── Kết quả test/scan của đúng digest
    └── Chữ ký/attestation từ chủ thể được tin cậy
~~~

Dùng revision của primary source thực sự được build; commit kích hoạt trigger có thể thuộc repository khác. Khi có nhiều nguồn hoặc dependency ngoài Git, lưu cả đầu vào liên quan.

Một file JSON tự ghi commit rồi đặt tên `provenance.json` chưa đủ chứng minh tính xác thực. Nếu mã chưa tin cậy được sửa file đó và ký bằng cùng quyền đang giữ, thông tin vẫn có thể sai.

SLSA là mô hình đánh giá cụ thể; chỉ dùng OCI Managed Build hoặc tạo metadata không đồng nghĩa đạt một cấp SLSA. Phải đánh giá builder, cách tạo bằng chứng, cách cách ly và cách xác minh.

### 7.3. Chuyển đúng sản phẩm đã được kiểm tra

Sau khi tạo gói, test/scan và ký phải gắn với đúng nội dung sẽ triển khai. Nếu bước sau sửa JAR, đổi base image hoặc build lại, digest mới cần được đánh giá theo quy trình tương ứng.

Giữ artifact đủ lâu cho rollback và điều tra. Kiểm soát quyền ghi đè/xóa, tách staging artifact chưa được chấp nhận khỏi artifact phát hành khi cần.

Chữ ký image không tự ký riêng JAR bên ngoài image hoặc mọi báo cáo đính kèm. Nếu cần bảo vệ báo cáo/SBOM/provenance, liên kết chúng với digest và xác thực bằng attestation hoặc chữ ký phù hợp.

## 8. Ký và xác minh container image trên OCI

### 8.1. Phân biệt quyền push, ký và tin cậy

Ba khả năng phải được xem xét riêng:

1. Ghi image vào repository.
2. Sử dụng khóa để tạo chữ ký cho image.
3. Thay chính sách xác định khóa nào được deployment tin cậy.

Người có quyền push không nên tự động có quyền ký phát hành. Người có quyền ký cũng không nên tự thêm khóa mới vào chính sách triển khai mà không qua quy trình.

OCI Container Registry hỗ trợ chữ ký image với khóa bất đối xứng RSA trong OCI Vault. Chữ ký gắn với image cụ thể trong registry; không dùng khóa AES để ký theo cơ chế này. Xem [Signing Images for Security](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrysigningimages_topic.htm).

Giữ khóa trong dịch vụ quản lý khóa giúp giảm việc phân phối private key ra file. Tuy nhiên, nếu builder được gọi thao tác ký không giới hạn, mã chiếm quyền builder vẫn có thể yêu cầu ký nội dung ngoài ý muốn. Bảo vệ quyền gọi ký và điều kiện ký quan trọng như bảo vệ khóa.

### 8.2. Khung lệnh ký image đã được kiểm tra

Giả sử image đã được push, digest đã được đối chiếu với sản phẩm qua kiểm tra và image OCID tương ứng đã được xác định. Các biến sau là định danh, không phải private key:

| Biến Bash | Giá trị cần cung cấp |
| --- | --- |
| `REGISTRY_COMPARTMENT_OCID` | Compartment chứa repository image |
| `SIGNING_KEY_OCID` | Khóa RSA được dùng cho phát hành |
| `SIGNING_KEY_VERSION_OCID` | Phiên bản khóa phù hợp |
| `IMAGE_OCID` | OCID của đúng image đã được kiểm tra |

Chạy dưới danh tính được giao phát hành, có quyền registry và quyền ký bằng khóa được phép:

~~~bash
oci artifacts container image-signature sign-upload \
  --compartment-id "$REGISTRY_COMPARTMENT_OCID" \
  --kms-key-id "$SIGNING_KEY_OCID" \
  --kms-key-version-id "$SIGNING_KEY_VERSION_OCID" \
  --signing-algorithm SHA_256_RSA_PKCS_PSS \
  --image-id "$IMAGE_OCID" \
  --description "Java release from approved build"
~~~

Tham số và thuật toán được hỗ trợ theo [OCI CLI: sign-upload](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/image-signature/sign-upload.html).

Không ký “image mới nhất” bằng cách chỉ tìm theo tag sau một khoảng chờ. Resolve image OCID từ image/digest đã chấp nhận và xác nhận lại trước khi ký.

Dòng mô tả không thay cho bằng chứng review hoặc provenance. Nó là metadata người gọi cung cấp.

### 8.3. Xác minh bằng khóa do chính sách tin cậy chỉ định

Deployment cần lấy danh sách khóa tin cậy từ cấu hình được bảo vệ, không lấy khóa do artifact tự khai báo rồi tin ngay khóa đó.

Khung lệnh:

~~~bash
oci artifacts container image-signature get-verify \
  --compartment-id "$REGISTRY_COMPARTMENT_OCID" \
  --repo-name "java/orders-api" \
  --image-digest "$EXPECTED_IMAGE_DIGEST" \
  --trusted-keys "$TRUSTED_KEY_OCID" \
  --compartment-id-in-subtree false
~~~

`EXPECTED_IMAGE_DIGEST` phải là digest đầy đủ của image dự định triển khai; `TRUSTED_KEY_OCID` đến từ chính sách của môi trường đích. Nguồn cú pháp: [OCI CLI: get-verify](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/artifacts/container/image-signature/get-verify.html).

Đây là thao tác xác minh chữ ký, chưa phải toàn bộ gate triển khai. Tích hợp phải kiểm tra kết quả xác minh thành công theo giao diện thực tế của phiên bản CLI/API, cùng điều kiện signer và digest. Không chỉ dựa vào việc lệnh trả JSON, không bị lỗi HTTP hoặc output chứa chữ “signature”.

Với JAR nằm trong generic Artifact Registry, cần cơ chế ký/xác minh phù hợp cho file hoặc attestation. Các lệnh `container image-signature` trên không áp dụng trực tiếp cho mọi file JAR.

### 8.4. Thực thi chính sách trên OKE

OKE có image verification policy cho image OCIR được ký bằng khóa Vault. Khi bật, cấu hình ít nhất một khóa tin cậy và tham chiếu image bằng digest trong manifest. Chính sách này không tự bao phủ mọi registry bên ngoài. Nguồn: [Enforcing Signed Images on OKE](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contengenforcingsignedimagesfromocir.htm).

Ví dụ trường image, cần thay hostname, namespace và toàn bộ digest:

~~~yaml
spec:
  containers:
    - name: orders-api
      image: "<region>.ocir.io/<namespace>/java/orders-api@sha256:<full-digest>"
~~~

Đây chỉ là đoạn manifest minh họa, chưa phải Deployment hoàn chỉnh.

Nếu bật policy nhưng để danh sách khóa rỗng, không đạt mục tiêu hạn chế signer. Nếu có nhiều khóa, một chữ ký phù hợp có thể đủ; không mặc định cần mọi khóa cùng ký. OKE còn có cơ chế break-glass cần được quản trị và theo dõi.

Tổ chức cần kiểm tra cả quyền sửa policy, quyền tạo workload và khả năng dùng ngoại lệ. Chữ ký hợp lệ không chứng minh image không có lỗ hổng; tiếp tục kiểm tra scan, provenance và điều kiện phát hành.

## 9. Thiết kế gate có thể kiểm chứng

Một gate triển khai có thể được diễn tả bằng quy tắc nghiệp vụ:

~~~text
Cho phép triển khai khi đồng thời:
  - digest tải về khớp digest đã được chấp nhận;
  - artifact đến từ repository/nguồn phát hành được phép;
  - chữ ký hoặc attestation được xác minh;
  - signer/builder nằm trong tập tin cậy;
  - bằng chứng nguồn, test và scan thuộc đúng artifact;
  - ngoại lệ, nếu có, còn hiệu lực và đúng phạm vi;
  - cấu hình môi trường đích và danh tính triển khai hợp lệ.
~~~

Đây là logic thiết kế, không phải một block YAML mà OCI tự hiểu. Cần triển khai bằng các khả năng CI/CD, công cụ xác minh hoặc admission policy phù hợp.

Mỗi điều kiện nên có trường hợp thử được phép và trường hợp thử bị từ chối:

| Điều kiện | Trường hợp đạt | Trường hợp phải từ chối |
| --- | --- | --- |
| IAM đọc secret | Pipeline A đọc secret lab A | A đọc secret lab B ngoài phạm vi |
| Nguồn tin cậy | Build đúng revision được chấp nhận | Artifact từ nguồn khác nhưng cùng tên |
| Toàn vẹn | Digest khớp gói đã kiểm tra | Gói khác byte hoặc tag trỏ sang image khác |
| Chữ ký | Đúng signer được môi trường tin cậy | Không ký hoặc dùng khóa ngoài chính sách |
| Kết quả quét | Có báo cáo đúng artifact, đạt ngưỡng | Thiếu báo cáo hoặc công cụ quét lỗi |
| Phân tách danh tính | PR chỉ chạy test quyền thấp | PR tự gọi API lấy secret phát hành |
| Ngoại lệ | Đúng artifact, thời hạn và người chịu trách nhiệm | Ngoại lệ hết hạn hoặc áp dụng toàn bộ gói |
| Quyền sửa gate | Đúng nhóm được giao | Người chỉ được deploy tự đổi signer tin cậy |

Thiết kế phải cho biết khi Vault, registry hoặc công cụ xác minh không truy cập được thì xử lý ra sao. Với phát hành production, không tự chuyển lỗi xác minh thành cho phép. Nếu có quy trình khẩn cấp, quy trình đó cần phạm vi hẹp, người chịu trách nhiệm, bằng chứng và thời hạn.

Hạn chế xung đột giữa bảo mật và tính sẵn sàng bằng cách chuẩn bị trước artifact tốt đã ký, đường truy cập registry/khóa, quyền pull và phương án rollback. Không chờ đến sự cố mới phát hiện bản rollback phụ thuộc một khóa đã bị xóa.

## 10. Giám sát và ứng cứu sự cố

### 10.1. Bằng chứng cần liên kết

Lưu các định danh không chứa giá trị secret:

- Repository, revision và pull request liên quan.
- Project, pipeline, build run và deployment ID.
- Danh tính thực thi và phạm vi tài nguyên.
- Artifact digest, phiên bản kho và image OCID nếu có.
- Secret OCID/phiên bản được ghi nhận theo khả năng tích hợp.
- Key OCID, key version và kết quả xác minh.
- Kết quả test/scan, ngoại lệ và người chấp nhận thay đổi.

Đối chiếu build/deployment logs với OCI Audit và sự kiện dịch vụ liên quan. Thiết lập theo dõi cho thay đổi IAM, cấu hình pipeline, source connection, quyền registry, chính sách xác minh và thao tác bất thường với secret/khóa.

Metadata cũng có thể tiết lộ kiến trúc hoặc tên hệ thống; giới hạn người đọc phù hợp. Không đưa plaintext credential vào bằng chứng chỉ để tiện điều tra.

### 10.2. Khi nghi ngờ secret đã lộ

Trình tự xử lý gợi ý:

1. Xác định credential nào bị ảnh hưởng và hệ thống nào còn chấp nhận nó.
2. Dừng luồng có khả năng tiếp tục phát tán, xử lý build đang chạy và cô lập runner theo khả năng nền tảng.
3. Thu hồi hoặc vô hiệu hóa credential, điều chỉnh quyền principal nếu cần.
4. Giữ bằng chứng có kiểm soát; hạn chế truy cập log/artifact chứa dữ liệu nhạy cảm.
5. Cấp credential mới theo phạm vi hẹp và xác minh consumer mới.
6. Xác định thao tác đã xảy ra trong khoảng thời gian bị ảnh hưởng.
7. Sửa đường rò rỉ trước khi bật lại luồng.

Không mặc định sửa policy đã làm mọi process đang chạy mất ngay dữ liệu hoặc token đã nhận. Xác minh hiệu quả thực tế của việc thu hồi và xử lý process còn hoạt động.

Nếu secret đã vào Git, xóa ở commit mới chưa xóa các bản clone và lịch sử. Việc thu hồi credential và xử lý dữ liệu lưu lại là hai công việc cần phối hợp.

### 10.3. Khi nghi ngờ artifact hoặc builder bị thay đổi

Tạm dừng promotion của gói liên quan, xác định digest và phạm vi build bị ảnh hưởng. Bảo toàn log, source revision, provenance, metadata và bản artifact cần điều tra.

Nếu khóa ký bị lạm dụng, chỉ ký lại toàn bộ gói bằng khóa mới có thể tiếp tục hợp thức hóa gói xấu. Trước hết xác định sản phẩm nào đủ tin cậy, thay chính sách signer có kiểm soát và build lại từ nguồn đã được xác minh khi cần.

Khi rollback, chọn artifact có nguồn gốc và tính toàn vẹn được chấp nhận, đồng thời kiểm tra tương thích với schema/database hiện tại. Một JAR cũ không tự đảo ngược migration hoặc khôi phục dữ liệu đã thay đổi.

### 10.4. Kiểm soát chi phí và dữ liệu giữ lại

Pipeline có thể gây chi phí do build lặp, scan image lớn, tạo môi trường test và lưu log/artifact quá lâu. Giới hạn trigger, tài nguyên runner, timeout và tài nguyên test theo phạm vi công việc.

Đặt thời hạn lưu nhưng giữ đủ artifact và bằng chứng cho điều tra/rollback. Không xóa khóa hoặc secret còn phục vụ workload chỉ để giảm số tài nguyên lab; phải xác minh consumer và phụ thuộc trước khi dọn.

## 11. Thực hành trong compartment lab

Bài thực hành nên dùng secret giả lập, repository thử và image không chứa dữ liệu nghiệp vụ. Không cần dùng credential production để chứng minh cơ chế phân quyền.

### Bước 1: Lập ma trận danh tính

Tạo hoặc chọn các danh tính riêng cho kiểm tra PR, phát hành và triển khai. Ghi lại pipeline OCID, dynamic group, policy và người có quyền sửa chúng.

Kết quả cần có là một bảng thể hiện ai đọc secret nào, ghi kho nào, ký bằng khóa nào và tác động môi trường nào. Tìm cả quyền gián tiếp từ các policy rộng.

### Bước 2: Thử IAM với hai secret lab

Chuẩn bị secret lab A và B có nội dung giả lập. Chỉ cho pipeline phát hành đọc A. Kiểm tra thao tác hợp lệ và thao tác bị từ chối, ghi kết quả mà không in nội dung.

Đồng thời kiểm tra pipeline PR không đọc được A ngay cả khi không dùng `vaultVariables` mà gọi API qua principal của nó. Nếu thao tác này thành công, sửa quyền IAM; không chỉ xóa biến môi trường.

### Bước 3: Cấp secret cho một build tin cậy

Áp dụng mẫu Vault/Maven cho repository lab nếu có private dependency repository. Nếu không có, giữ phần Maven làm mẫu cấu hình và kiểm tra cơ chế cấp secret bằng consumer lab không in giá trị.

Xác nhận secret không xuất hiện trong Git, log, thư mục output, cache được chia sẻ và sản phẩm đóng gói. Với secret scanner, dùng mẫu kiểm thử mà công cụ hỗ trợ thay vì đưa credential thật vào mã.

### Bước 4: Giữ danh tính artifact

Build và kiểm tra một JAR hoặc image; ghi digest, nguồn, build run và kết quả test. Giữ SBOM/báo cáo nếu đã cấu hình công cụ tương ứng.

Thay một bản sao artifact trong lab hoặc chọn image khác rồi xác nhận kiểm tra digest phát hiện sai khác. Không sửa kho dùng chung hoặc gói đang phục vụ workload thật để tạo tình huống thử.

### Bước 5: Kiểm tra chữ ký và chính sách

Với image OCIR, ký đúng image bằng khóa lab, xác minh bằng khóa tin cậy và thử trường hợp image chưa ký hoặc signer khác.

Nếu có cụm OKE lab, bật policy với khóa đã chọn và kiểm tra chấp nhận/từ chối trên workload thử. Nếu không có cụm, vẫn hoàn thành phần registry/CLI và ghi rõ chưa kiểm chứng enforcement trên cluster.

### Bước 6: Thử rotation và đóng phòng thực hành

Xoay secret lab, chạy consumer mới và xác nhận credential cũ bị thu hồi tại nơi xác thực. Nếu chỉ dùng chuỗi giả lập trong Vault, ghi rõ mới kiểm tra chuyển phiên bản, chưa chứng minh thu hồi credential của một dịch vụ bên ngoài.

Lưu bằng chứng không có nội dung secret. Thu hồi token thử, dọn pipeline/registry/workload lab không còn dùng và xử lý khóa theo phụ thuộc đã xác nhận.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Đã lưu trong Vault nên mọi build đều được dùng” | Chỉ consumer cần thiết, có mức tin cậy phù hợp mới được nhận quyền |
| “Không khai báo biến là không đọc được secret” | Principal có IAM phù hợp vẫn có thể gọi API lấy secret |
| “Stage sau mới ký nên stage trước không có quyền ký” | Cần kiểm tra danh tính/quyền thực tế của từng phần |
| “PR đã chạy test nên mã đáng tin” | Test và điều kiện review/nguồn phát hành giải quyết các mục tiêu khác nhau |
| “Image có chữ ký là không có lỗ hổng” | Chữ ký xác thực sự liên hệ với signer, không chứng minh mọi hành vi an toàn |
| “Checksum đặt cạnh JAR là đủ chống thay thế” | Cần nguồn tin cậy cho digest hoặc bằng chứng xác thực |
| “SBOM là provenance” | SBOM mô tả thành phần; provenance mô tả nguồn và quá trình tạo |
| “Build ở OCI là tự đạt SLSA” | Cần đánh giá các yêu cầu cụ thể của mô hình |
| “Xóa secret khỏi Git là đã thu hồi” | Credential có thể vẫn dùng được tại hệ thống đích |
| “Có backup artifact là rollback được” | Còn phụ thuộc quyền, khóa xác minh, runtime và trạng thái dữ liệu |

Một chuỗi CI/CD được kiểm soát cần gắn **danh tính đúng quyền**, **secret đúng consumer** và **artifact đúng nguồn gốc**. Khi mở rộng từ ứng dụng Java lab sang Compute, lưu trữ và cơ sở dữ liệu Oracle, tiếp tục kiểm chứng cả quyền được phép, quyền bị từ chối, khả năng truy vết và khả năng phục hồi.
