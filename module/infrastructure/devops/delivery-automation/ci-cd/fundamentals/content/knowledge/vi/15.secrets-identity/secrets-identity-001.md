# Lưu thông tin bí mật trong hệ thống chuyên dụng của môi trường

Ứng dụng và pipeline CI/CD thường cần thông tin nhạy cảm để xác thực hoặc truy cập tài nguyên: mật khẩu database, API token, private key, chứng thư, signing key và credential của registry. Nếu lưu các giá trị này trực tiếp trong source code, file cấu hình hoặc biến pipeline dùng chung, chúng dễ bị sao chép sang log, artifact, cache, bản backup hoặc môi trường không phù hợp.

Cách quản lý an toàn là lưu secret trong **hệ thống quản lý bí mật chuyên dụng (secret manager hoặc vault)**, gắn quyền truy cập với danh tính của workload và chỉ cấp giá trị cho đúng job hoặc ứng dụng tại thời điểm cần dùng. Mỗi môi trường cần có phạm vi bí mật, quyền và quy trình vòng đời riêng. Nhờ đó, nhóm có thể kiểm soát ai hoặc thành phần nào được đọc secret, theo dõi việc sử dụng, xoay vòng credential và thu hồi quyền khi có sự cố.

## 1. Phân biệt secret với cấu hình thông thường

Không phải mọi cấu hình đều là bí mật. Cần phân loại dữ liệu trước khi chọn nơi lưu và cách cấp phát.

| Loại dữ liệu | Ví dụ | Cách quản lý phù hợp |
|---|---|---|
| Cấu hình không nhạy cảm | Tên service, log level, timeout, feature flag công khai | File cấu hình, biến môi trường hoặc config store |
| Thông tin định danh tài nguyên | Host database, tên bucket, region, endpoint | Config store có kiểm soát theo môi trường |
| Secret | Password, API token, private key, signing key | Secret manager hoặc vault |
| Credential ngắn hạn | Token có TTL, database credential tạm thời | Cấp phát động từ secret manager hoặc identity provider |
| Chứng thư và khóa | TLS certificate, private key, key mã hóa | Hệ thống quản lý khóa/chứng thư hoặc secret manager phù hợp |

Một endpoint như `db.internal.example` có thể không phải secret, nhưng mật khẩu đi kèm thì có. Không nên gom mọi thứ vào một file mã hóa rồi xem toàn bộ file như một loại dữ liệu. Phân loại rõ giúp áp dụng quyền đọc, thời hạn lưu và cơ chế xoay vòng đúng với từng loại.

Secret có thể được lưu dưới dạng một giá trị đơn hoặc một tập dữ liệu có cấu trúc. Ví dụ, một secret kết nối database có thể chứa username và password; tuy nhiên, cần tránh lưu thêm thông tin không cần thiết. Nếu host, database name và port không nhạy cảm, có thể quản lý chúng trong cấu hình riêng.

## 2. Vì sao cần hệ thống quản lý bí mật chuyên dụng?

Lưu secret trong repository hoặc file cấu hình thường tạo ra nhiều bản sao khó kiểm soát. Ngay cả khi file được mã hóa hoặc giá trị đã bị xóa khỏi commit mới, secret có thể vẫn còn trong lịch sử Git, fork, bản clone, log và artifact cũ.

Secret manager cung cấp một điểm kiểm soát tập trung với các khả năng thường gặp:

- Lưu trữ secret có mã hóa khi truyền và khi lưu.
- Xác thực người dùng, service hoặc workload trước khi cho phép đọc.
- Phân quyền theo secret, namespace, project hoặc môi trường.
- Ghi audit log cho thao tác đọc, ghi, xoay vòng và thu hồi.
- Quản lý version và trạng thái secret.
- Tự động xoay vòng hoặc cấp credential có thời hạn.
- Tích hợp với KMS/HSM hoặc cơ chế bảo vệ khóa của nền tảng.
- Hỗ trợ thu hồi quyền và phản ứng khi có sự cố.

Các hệ thống thường gặp gồm AWS Secrets Manager, Azure Key Vault, Google Secret Manager và HashiCorp Vault. Một số nền tảng CI/CD cũng có secret store riêng. Chúng có thể hữu ích cho secret chỉ dùng trong pipeline, nhưng không phải lúc nào cũng thay thế được hệ thống quản lý bí mật dùng chung cho workload đang chạy trong development, staging và production.

Cần xác định một nguồn quản lý chuẩn cho mỗi secret. Nếu cùng một credential được sao chép vào nhiều nơi, việc xoay vòng và thu hồi sẽ khó đồng bộ.

## 3. Phân tách secret theo môi trường

Development, test, staging và production có mục tiêu, dữ liệu và mức độ tin cậy khác nhau. Vì vậy, không nên dùng chung credential giữa các môi trường.

Ví dụ cấu trúc định danh trong secret manager:

~~~text
/app-name/
  dev/
    database/password
    payment/api-token
  test/
    database/password
    payment/api-token
  staging/
    database/password
    payment/api-token
  production/
    database/password
    payment/api-token
~~~

Đây là cách tổ chức khái niệm; secret manager có thể dùng project, vault, namespace, folder, path hoặc resource riêng. Mục tiêu là bảo đảm một workload development chỉ đọc được secret development và một job production chỉ đọc được secret production khi đáp ứng điều kiện được cấp quyền.

| Môi trường | Nguồn secret | Nguyên tắc |
|---|---|---|
| Development | Secret riêng cho cá nhân hoặc nhóm phát triển | Không chứa credential production |
| Test/CI | Credential dành riêng cho test và dịch vụ giả lập | Quyền ngắn hạn, dữ liệu tổng hợp |
| Staging | Secret của dịch vụ staging | Phù hợp cấu hình gần production nhưng tách biệt |
| Production | Vault hoặc secret manager production | Quyền tối thiểu, audit và approval chặt chẽ |

Không nên đặt production secret vào file `.env` rồi commit hoặc chia sẻ qua chat. File `.env` có thể hữu ích cho phát triển cục bộ nếu được tạo từ secret manager, nằm ngoài Git và có quyền file phù hợp; nhưng nó không phải kho lưu trữ trung tâm.

Tên secret có thể nhất quán giữa các môi trường, trong khi giá trị và quyền truy cập khác nhau. Điều này giúp ứng dụng dùng cùng một cấu hình logic mà không phải hardcode credential theo môi trường.

## 4. Tách secret theo ứng dụng và mục đích

Không nên cấp một tài khoản có quyền rộng cho nhiều ứng dụng chỉ để tiện cấu hình. Nếu một dịch vụ bị xâm nhập, credential dùng chung có thể mở đường đến các hệ thống khác.

Mỗi workload nên có danh tính và secret riêng theo mục đích:

- API service có credential đọc database của chính service.
- Job migration có quyền schema cần thiết trong khoảng thời gian chạy migration.
- Pipeline publish có quyền ghi vào đúng registry.
- Job deploy có quyền cập nhật đúng cluster hoặc namespace.
- Monitoring agent có token chỉ đọc metric hoặc endpoint được phép.

Ví dụ một ứng dụng có thể cần ba loại quyền độc lập:

| Thành phần | Quyền cần | Không nên được cấp |
|---|---|---|
| Runtime API | Đọc/ghi dữ liệu nghiệp vụ trong database | Quyền quản trị database |
| Migration job | Thay đổi schema trong cửa sổ triển khai | Quyền truy cập mọi database |
| CI build | Đọc dependency và tạo artifact | Production database password |

Tách credential giúp thu hẹp phạm vi ảnh hưởng khi secret bị lộ và giúp audit xác định thành phần nào đã sử dụng quyền nào.

## 5. Xác thực bằng danh tính workload

Cách cấp secret an toàn không nên phụ thuộc vào một mật khẩu tĩnh được lưu trong pipeline để truy cập secret manager. Nếu có thể, hãy để workload chứng minh danh tính bằng cơ chế định danh của nền tảng rồi nhận quyền ngắn hạn.

Các cơ chế thường dùng:

- OIDC federation từ CI provider đến cloud provider.
- Workload Identity trên Kubernetes hoặc nền tảng cloud.
- Managed Identity của dịch vụ cloud.
- Service account gắn với workload.
- Certificate-based authentication hoặc cơ chế xác thực máy tương đương.

Luồng truy cập khái niệm:

~~~mermaid
sequenceDiagram
    participant W as CI job hoặc ứng dụng
    participant I as Identity provider
    participant S as Secret manager
    participant R as Tài nguyên đích

    W->>I: Yêu cầu token định danh
    I-->>W: Token có issuer, subject và audience
    W->>S: Xác thực token và yêu cầu secret
    S->>S: Kiểm tra policy và phạm vi quyền
    S-->>W: Secret hoặc credential ngắn hạn
    W->>R: Kết nối bằng credential được cấp
~~~

Secret manager cần xác minh issuer, subject, audience, thời hạn và các claim phù hợp với policy. Ví dụ, một workflow chỉ được truy cập secret production khi chạy từ repository, branch hoặc environment được cho phép. Không nên chỉ kiểm tra tên repository nếu bất kỳ branch hoặc workflow nào trong repository cũng có thể yêu cầu quyền production.

OIDC giúp tránh phải lưu cloud access key dài hạn trong CI. Tuy nhiên, token OIDC vẫn là credential có thời hạn và cần được giới hạn audience, subject và quyền mà nó có thể nhận.

## 6. Cấp quyền tối thiểu và kiểm soát truy cập

Một workload chỉ nên đọc đúng secret cần thiết, trong thời gian cần thiết. Phân quyền nên áp dụng theo nguyên tắc least privilege.

Cần xác định:

- **Principal:** người, service account, runner hoặc workload nào yêu cầu secret.
- **Resource:** secret hoặc nhóm secret được truy cập.
- **Action:** đọc, ghi, tạo version, rotate hoặc xóa.
- **Condition:** môi trường, branch, repository, namespace, thời gian hoặc trạng thái phê duyệt.
- **Scope:** một ứng dụng, một dịch vụ hoặc một tài nguyên cụ thể.

Ví dụ ma trận quyền:

| Danh tính | Secret development | Secret staging | Secret production |
|---|---|---|---|
| Developer local | Chỉ secret dev được cấp | Không mặc định | Không |
| CI pull request từ fork | Không có secret nhạy cảm | Không | Không |
| CI nhánh chính | Secret test cần thiết | Theo workflow và policy | Không mặc định |
| Release workflow đã được bảo vệ | Không cần quyền rộng | Có thể promotion | Chỉ khi thỏa policy |
| Production workload | Không | Không | Chỉ secret của workload đó |

Không dùng quyền quản trị secret manager cho mọi job. Quyền tạo hoặc xóa secret thường nhạy cảm hơn quyền đọc. Người vận hành có thể cần quyền quản lý, nhưng workload chỉ cần quyền đọc secret cụ thể.

Định kỳ rà soát danh tính không còn dùng, service account cũ, quyền wildcard và quyền truy cập được cấp tạm thời. Thu hồi quyền khi workload bị ngừng hoặc chuyển sang danh tính mới.

## 7. Tích hợp secret manager với pipeline CI/CD

Pipeline cần credential để publish artifact hoặc deploy, nhưng không nên lưu credential dài hạn trực tiếp trong YAML. Một mô hình tốt là CI dùng OIDC hoặc danh tính workload để xác thực với secret manager, sau đó chỉ lấy secret khi job cần.

Ví dụ khái niệm với GitHub Actions và AWS Secrets Manager:

~~~yaml
name: Deploy staging

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - uses: actions/checkout@v4

      - name: Obtain short-lived AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/ci-staging-deploy
          aws-region: ap-southeast-1

      - name: Fetch secret and deploy
        shell: bash
        run: |
          set +x
          secret="$(aws secretsmanager get-secret-value \
            --secret-id app/staging/deploy-token \
            --query SecretString \
            --output text)"

          echo "::add-mask::$secret"
          DEPLOY_TOKEN="$secret" ./scripts/deploy-staging.sh
~~~

Ví dụ minh họa cơ chế liên kết OIDC với role và lấy secret. ARN, role trust policy, region, secret ID và quyền IAM phải được tạo theo môi trường thật. Role chỉ nên được phép đọc đúng secret cần dùng (và quyền giải mã qua KMS nếu secret dùng khóa do khách hàng quản lý). Secret được truyền vào tiến trình deploy trong cùng step, không ghi vào file environment dùng chung cho các bước sau. Cần pin action theo chính sách bảo mật của tổ chức; ví dụ dùng tag phiên bản để dễ đọc, còn môi trường yêu cầu kiểm soát chặt có thể pin commit SHA.

Không bật shell tracing khi xử lý secret. Không in giá trị ra stdout, không truyền secret trong URL hoặc tham số dòng lệnh và không đưa nó vào output của job nếu không cần. Lệnh add-mask giúp che giá trị trong log GitHub Actions sau khi được đăng ký, nhưng không thay thế việc ngăn secret đi vào log ngay từ đầu.

Nếu secret có thể chứa newline hoặc dữ liệu phức tạp, không nên ghi trực tiếp vào file environment theo cách đơn giản như ví dụ. Hãy dùng cơ chế truyền dữ liệu phù hợp, file tạm với quyền hạn chế hoặc action chuyên dụng, rồi xóa dữ liệu tạm sau khi dùng.

## 8. Cấp secret lúc runtime cho ứng dụng

Secret cần cho ứng dụng đang chạy nên được cấp trong runtime theo danh tính của workload. Pipeline có thể triển khai ứng dụng và policy, còn ứng dụng lấy credential khi khởi động hoặc khi cần kết nối.

Một số cách tích hợp:

- SDK/API của secret manager: ứng dụng gọi API bằng workload identity.
- Agent hoặc sidecar: agent lấy secret và cung cấp qua file hoặc local endpoint.
- CSI driver: mount secret vào pod dưới dạng volume.
- External Secrets Operator: đồng bộ secret từ hệ thống bên ngoài vào Kubernetes Secret.
- Managed platform integration: nền tảng cấp secret vào runtime theo cấu hình được bảo vệ.

Mỗi cách có trade-off. Ứng dụng gọi API trực tiếp có thể kiểm soát refresh tốt nhưng cần xử lý lỗi và cache an toàn. Mount file giúp ứng dụng dùng thư viện đọc file thông thường nhưng phải biết khi secret thay đổi. Đồng bộ thành Kubernetes Secret thuận tiện với ứng dụng hiện hữu nhưng tạo thêm bản sao secret trong cluster.

Không nên bake secret vào container image hoặc build argument. Image thường được lưu trong registry, cache và có thể được chia sẻ qua nhiều môi trường. Nếu credential nằm trong image layer, xóa file ở layer sau không đảm bảo giá trị đã biến mất khỏi layer trước.

## 9. Lưu secret trong Kubernetes đúng cách

Kubernetes Secret là tài nguyên dùng để cung cấp dữ liệu nhạy cảm cho workload. Tuy nhiên, giá trị trong trường data được biểu diễn bằng Base64; **Base64 không phải mã hóa**.

Khi dùng Kubernetes Secret, cần:

- Bật encryption at rest cho dữ liệu Secret trong etcd bằng cấu hình mã hóa phù hợp.
- Giới hạn RBAC để chỉ service account hoặc nhóm cần thiết mới đọc được Secret.
- Hạn chế quyền list/watch Secret vì chúng có thể cho phép đọc nhiều giá trị.
- Không cấp quyền truy cập API Kubernetes rộng cho container chỉ để lấy một secret.
- Tránh mount secret vào container không cần dùng.
- Không đưa Secret vào log, manifest công khai hoặc image.
- Kiểm soát backup etcd và quyền truy cập bản backup.
- Dùng external secret manager khi cần quản lý tập trung, rotation và audit xuyên nhiều cluster.

Ví dụ mount Secret dưới dạng file:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-api
spec:
  serviceAccountName: order-api
  containers:
    - name: app
      image: example/order-api:1.2.0
      volumeMounts:
        - name: database-credentials
          mountPath: /var/run/secrets/database
          readOnly: true
  volumes:
    - name: database-credentials
      secret:
        secretName: order-api-database
        items:
          - key: username
            path: username
          - key: password
            path: password
~~~

Manifest này chỉ minh họa cách mount một Kubernetes Secret có sẵn. Nó không tạo ra secret an toàn tự động và không thay thế encryption at rest, RBAC hoặc quy trình lấy secret từ hệ thống chuyên dụng. Ứng dụng cần đọc file với quyền hạn chế và tránh in nội dung ra log.

## 10. Quản lý vòng đời: tạo, phân phối, xoay vòng và thu hồi

Secret có vòng đời riêng. Không nên xem credential đã tạo là dùng mãi cho đến khi có sự cố.

Một vòng đời thường gồm:

1. **Tạo:** sinh credential bằng công cụ hoặc hệ thống có kiểm soát, ưu tiên giá trị ngẫu nhiên đủ mạnh.
2. **Lưu:** ghi secret vào đúng vault, namespace hoặc project của môi trường.
3. **Cấp quyền:** gắn quyền đọc cho danh tính workload cụ thể.
4. **Sử dụng:** workload lấy secret trong thời gian cần thiết, không ghi lại vào nơi lưu trữ khác.
5. **Xoay vòng:** tạo version mới và chuyển workload sang version mới.
6. **Xác minh:** kiểm tra workload mới hoạt động với credential mới.
7. **Thu hồi:** vô hiệu hóa credential cũ sau khi các consumer đã chuyển đổi.
8. **Xóa:** xóa version hoặc secret theo retention và yêu cầu kiểm toán.

Rotation cần được thiết kế để tránh downtime. Với database password, có thể tạo credential mới, cập nhật quyền, chuyển workload sang credential mới, xác minh kết nối rồi mới thu hồi credential cũ. Nếu hệ thống chỉ cho phép một password tại một thời điểm, cần có quy trình chuyển đổi phù hợp hoặc dùng cơ chế credential tạm thời.

Không xoay vòng chỉ vì lịch nếu không có cách xác minh consumer đã nhận giá trị mới. Ngược lại, không trì hoãn vô hạn vì sợ ảnh hưởng dịch vụ. Hãy theo dõi tuổi secret, thời điểm rotate gần nhất, owner và danh sách consumer.

## 11. Ưu tiên credential ngắn hạn và secret động

Secret tĩnh thường tồn tại lâu, dễ bị sao chép và khó xác định nơi còn sử dụng. Khi nền tảng hỗ trợ, nên dùng credential có thời hạn ngắn hoặc được cấp phát động.

Ví dụ:

- Cloud role session credential có thời hạn.
- Database username/password do Vault cấp theo lease.
- Token API ngắn hạn được tạo qua identity federation.
- Certificate ngắn hạn do hệ thống PKI cấp.
- Token registry chỉ có quyền publish một repository và hết hạn sau release.

Secret động thường có các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| TTL/lease | Thời hạn sử dụng |
| Scope | Tài nguyên và hành động được phép |
| Renewal | Điều kiện gia hạn nếu workload còn cần |
| Revocation | Cách thu hồi trước khi hết hạn |
| Owner/identity | Workload hoặc danh tính nhận credential |
| Audit | Dấu vết cấp phát và sử dụng |

Workload cần xử lý trường hợp credential hết hạn: lấy mới, refresh connection pool hoặc tái xác thực. Không nên giả định credential ngắn hạn sẽ luôn tồn tại trong toàn bộ vòng đời process.

## 12. Xử lý secret trong log, shell, artifact và cache

Secret có thể rò rỉ ở nhiều vị trí ngoài repository:

- Log CI khi bật shell tracing hoặc in toàn bộ environment.
- Thông báo lỗi chứa URL có username/password.
- Command line arguments có thể xuất hiện trong process listing.
- Artifact chứa file cấu hình, dump hoặc test report.
- Cache chứa thư mục home, file credential hoặc token.
- Docker image layer hoặc build cache.
- Screenshot và video ghi lại form hoặc terminal.
- Crash dump hoặc heap dump chứa giá trị trong bộ nhớ.

Các quy tắc thực hành:

- Tắt `set -x` hoặc chế độ verbose khi xử lý secret.
- Không dùng `echo` hoặc debug print để kiểm tra secret.
- Không truyền secret trong URL, query string hoặc tham số dòng lệnh.
- Không cache thư mục chứa credential.
- Không upload file cấu hình nhạy cảm cùng report.
- Redact header Authorization, cookie và connection string trước khi lưu log.
- Hạn chế quyền đọc artifact và log.
- Dùng file tạm với quyền truy cập tối thiểu khi ứng dụng yêu cầu file.
- Xóa file tạm sau khi job kết thúc; nhớ rằng xóa file không thay thế thu hồi credential nếu giá trị đã bị lộ.

Masking của nền tảng chỉ là lớp bảo vệ bổ sung. Nó có thể không che được secret đã được biến đổi, chia nhỏ, encode hoặc ghi vào định dạng khác. Cách an toàn nhất là không đưa secret vào log.

## 13. Audit và theo dõi việc sử dụng secret

Secret manager cần ghi nhận đủ thông tin để trả lời ai đã truy cập secret nào, vào lúc nào và từ danh tính nào. Audit log thường cần có:

- Principal hoặc workload identity.
- Secret resource hoặc secret path.
- Hành động: read, create, update, rotate, disable hoặc delete.
- Thời điểm và kết quả thành công/thất bại.
- Nguồn yêu cầu, project, environment hoặc workload context nếu nền tảng cung cấp.
- Request ID hoặc correlation ID.

Audit log không nên ghi giá trị secret. Hãy đưa log vào hệ thống giám sát có quyền truy cập giới hạn và retention phù hợp. Có thể cảnh báo khi một danh tính đọc secret ngoài giờ hoặc ngoài môi trường thông thường, khi một service account đọc số lượng secret bất thường hoặc khi secret production được truy cập từ workflow không dự kiến.

Rà soát định kỳ:

- Secret không còn được workload nào sử dụng.
- Danh tính cũ vẫn còn quyền đọc.
- Secret có tuổi quá dài hoặc chưa có lịch rotation.
- Quyền wildcard hoặc quyền quản trị không cần thiết.
- Nhiều bản sao cùng một credential ở các hệ thống khác nhau.
- Audit log bị thiếu hoặc không được chuyển về nơi lưu tập trung.

## 14. Xử lý khi secret bị lộ hoặc secret manager không sẵn sàng

Nếu nghi ngờ secret bị lộ, cần xử lý theo thứ tự ưu tiên:

1. Xác định loại credential, tài nguyên và môi trường bị ảnh hưởng.
2. Thu hồi hoặc vô hiệu hóa credential có nguy cơ.
3. Tạo credential mới và cấp cho đúng workload.
4. Cập nhật consumer, xác minh hoạt động rồi loại bỏ bản cũ.
5. Kiểm tra audit log để xác định phạm vi truy cập.
6. Hạn chế hoặc xóa các bản sao chứa secret theo quy trình.
7. Ghi nhận nguyên nhân và sửa đường rò rỉ.

Không chỉ xóa secret khỏi file hiện tại. Nếu credential từng xuất hiện trong Git history, log hoặc artifact, phải xem nó đã bị lộ và xoay vòng. Xóa lịch sử không thay thế thu hồi credential.

Khi secret manager tạm thời không truy cập được, cách xử lý phụ thuộc loại workload:

- Workload đã có credential còn hiệu lực có thể tiếp tục trong giới hạn TTL và chính sách.
- Workload cần credential mới nên retry có giới hạn và báo lỗi rõ ràng.
- Không chuyển sang hardcode hoặc dùng một credential dự phòng không được quản lý.
- Job phát hành hoặc triển khai cần chặn khi không thể xác minh danh tính hoặc lấy secret bắt buộc.
- Ứng dụng production cần có chiến lược cache trong bộ nhớ an toàn và hành vi khi credential hết hạn, phù hợp yêu cầu availability.

Không nên lưu secret vĩnh viễn trong file để phòng trường hợp secret manager ngừng hoạt động. Hãy thiết kế tính sẵn sàng, backup, replication và quy trình khôi phục cho chính hệ thống quản lý bí mật.

## 15. Ví dụ thiết kế hoàn chỉnh cho một dịch vụ

Giả sử một dịch vụ Java chạy trên Kubernetes và pipeline GitHub Actions triển khai lên staging rồi production.

- Developer chạy local với credential development riêng, lấy từ secret manager hoặc cơ chế đăng nhập cá nhân.
- Pull request chỉ chạy lint, unit test và integration test bằng dữ liệu giả lập; job không nhận secret production.
- Khi merge vào nhánh được bảo vệ, workflow dùng OIDC để nhận quyền truy cập role build/publish giới hạn.
- Release workflow được phê duyệt lấy credential deploy staging từ secret manager staging.
- Ứng dụng staging dùng workload identity để đọc database password và API token staging lúc runtime.
- Sau khi staging đạt quality gate, người có thẩm quyền phê duyệt promotion production.
- Production workload dùng identity riêng để đọc secret production.
- Credential có lịch rotation; audit log được giữ tập trung và cảnh báo truy cập bất thường.
- Khi rotate database password, nhóm chuyển consumer theo quy trình overlap hoặc credential version, xác minh kết nối rồi thu hồi bản cũ.

Trong mô hình này, pipeline không cần biết mọi secret của ứng dụng. Nó chỉ có quyền lấy credential cần cho hành động cụ thể của job; ứng dụng runtime tự lấy secret của nó bằng danh tính riêng. Việc tách này giảm phạm vi ảnh hưởng nếu pipeline hoặc một workload bị xâm nhập.

## 16. Checklist lưu trữ và sử dụng secret an toàn

Trước khi đưa secret vào CI/CD hoặc môi trường runtime, hãy kiểm tra:

- [ ] Secret được lưu trong secret manager hoặc vault chuyên dụng.
- [ ] Secret không nằm trong source code, file YAML công khai, image, cache hoặc artifact.
- [ ] Development, test, staging và production dùng secret riêng.
- [ ] Mỗi workload hoặc job có danh tính riêng và quyền tối thiểu.
- [ ] Ưu tiên OIDC, workload identity hoặc credential ngắn hạn thay cho access key dài hạn.
- [ ] Policy kiểm tra đúng repository, branch, environment, audience và workload.
- [ ] Secret chỉ được lấy ở bước cần dùng và không bị in ra log.
- [ ] Secret manager có mã hóa, audit, backup và kiểm soát quyền truy cập.
- [ ] Kubernetes Secret được bảo vệ bằng encryption at rest và RBAC phù hợp nếu sử dụng.
- [ ] Có quy trình rotation, xác minh consumer và thu hồi credential cũ.
- [ ] Có thể phát hiện secret hết hạn, không còn owner hoặc không còn được sử dụng.
- [ ] Log, report, screenshot, dump, cache và artifact được kiểm tra nguy cơ chứa secret.
- [ ] Có quy trình ứng phó khi secret bị lộ.
- [ ] Có hành vi fail closed phù hợp khi không lấy được secret bắt buộc.
- [ ] Audit log không chứa giá trị secret và có thể truy vết danh tính truy cập.

Lưu secret trong hệ thống chuyên dụng chỉ là bước đầu. Một thiết kế CI/CD an toàn cần nối secret với danh tính workload, quyền tối thiểu, phạm vi môi trường, vòng đời và audit. Khi credential được cấp đúng nơi, đúng lúc và có thể thu hồi, pipeline và ứng dụng có thể sử dụng tài nguyên cần thiết mà không phải phát tán bí mật qua mã nguồn hoặc các file build.

