# Secret không xuất hiện trong generated config

## 1. Vì sao generated config không được chứa secret?

Trong **SPRING_GRPC**, ứng dụng dùng Protocol Buffers để định nghĩa contract, sinh Java message/stub và triển khai gRPC client/server trong Spring. Quy trình build và deploy thường sinh thêm nhiều artifact: file cấu hình, manifest Kubernetes, Helm render output, Docker image, package, báo cáo build và metadata. Các artifact này có thể được lưu lâu dài, sao chép qua nhiều hệ thống hoặc chia sẻ cho người không cần quyền truy cập credential.

Nếu secret được ghi trực tiếp vào cấu hình sinh tự động, giá trị đó có thể xuất hiện trong:

- Git history, pull request, code review và bản sao repository.
- Generated YAML/JSON, file cấu hình theo profile và manifest đã render.
- Docker image layer, build cache và image registry.
- CI/CD log, command line, test report, artifact và cache.
- Spring configuration diagnostics, Actuator environment/configuration endpoint hoặc log debug.
- Generated Java source, protobuf descriptor, tài liệu API và ví dụ code.

**Nguyên tắc:** generated config chỉ chứa cấu hình không nhạy cảm và tham chiếu đến nơi cung cấp secret. Secret được cấp cho process ở runtime qua secret manager, secret volume hoặc cơ chế injection được kiểm soát. Không đưa giá trị bí mật vào bước code generation, build hay render template.

## 2. Phân biệt configuration và secret

Configuration mô tả ứng dụng phải hoạt động như thế nào. Secret chứng minh danh tính hoặc cấp quyền truy cập.

| Dữ liệu | Phân loại | Ví dụ |
|---|---|---|
| gRPC host, port, timeout mặc định | Configuration | `orders-grpc.backend.svc:9090` |
| Tên service, feature flag không nhạy cảm | Configuration | `inventory-v1`, `enable-reflection=false` |
| Kích thước message tối đa | Configuration | `4 MiB` |
| Đường dẫn đến secret volume | Secret reference | `/var/run/secrets/grpc/tls.key` |
| Password keystore/truststore có bảo vệ | Secret | Mật khẩu mở keystore |
| TLS private key | Secret | Private key của gRPC server |
| Bearer token/API key | Secret | Credential gọi downstream service |
| Database password | Secret | Mật khẩu kết nối repository |
| Signing/encryption key | Secret | Khóa ký token hoặc mã hóa dữ liệu |
| CA certificate công khai | Thường là configuration/trust material | Certificate public dùng xác minh chain |

Certificate public không phải private key. Tuy nhiên, thay đổi CA trust có thể làm thay đổi danh tính peer được chấp nhận, vì vậy trust bundle vẫn cần kiểm soát tính toàn vẹn và quyền sửa đổi.

Không coi mọi chuỗi có tên `password`, `token`, `key` là secret một cách máy móc; hãy phân loại theo khả năng cấp quyền hoặc giải mã dữ liệu. Ngược lại, không coi secret là an toàn chỉ vì nó được đặt trong YAML, JSON hoặc một biến có tên chung chung.

## 3. Generated config nên chứa reference

Ví dụ cấu hình ứng dụng có thể giữ tên service, port và đường dẫn file secret:

~~~yaml
spring:
  application:
    name: inventory-grpc

app:
  grpc:
    downstream:
      target: dns:///orders-grpc.backend.svc.cluster.local:9090
    tls:
      certificate-chain-file: /var/run/secrets/grpc/tls.crt
      private-key-file: /var/run/secrets/grpc/tls.key
      trust-bundle-file: /var/run/secrets/grpc/ca.crt
~~~

Các giá trị trong ví dụ là cấu hình và đường dẫn. Nội dung của `tls.key`, token và private credential được cung cấp ngoài file này. Những property `app.grpc.*` là property do ứng dụng định nghĩa; tên property TLS thực tế của Spring gRPC starter phụ thuộc phiên bản và cơ chế cấu hình đang dùng.

Một generated manifest hoặc template có thể tham chiếu Secret theo tên:

~~~yaml
volumes:
  - name: grpc-tls
    secret:
      secretName: inventory-grpc-tls

containers:
  - name: inventory
    volumeMounts:
      - name: grpc-tls
        mountPath: /var/run/secrets/grpc
        readOnly: true
~~~

Manifest cho biết secret object nào được mount và mount ở đâu. Giá trị private key không nằm trong manifest được render. Việc cấp quyền đọc Secret object phải được quản lý riêng bằng RBAC và policy của cluster.

## 4. Giữ secret ngoài source và generated source

Không ghi secret vào:

- `application.yml`, `application-*.yml`, `bootstrap.yml` hoặc file profile được commit.
- File `.env` được commit, `gradle.properties` dùng chung hoặc script build.
- Proto option, custom annotation, comment, descriptor hoặc sample request.
- Generated Java class, source template, code generator argument hoặc constant.
- Dockerfile, image `ENV`, `ARG` dùng để truyền credential hoặc build layer.
- Helm values được lưu trong repository nếu values chứa secret thật.

Protobuf contract chỉ mô tả dữ liệu nghiệp vụ và RPC. Nếu một RPC nhận access token hoặc credential trong metadata, không đưa token mẫu có hiệu lực vào `.proto`, generated stub, README hoặc test fixture. Dùng dữ liệu giả đã hết hiệu lực hoặc token được cấp riêng cho test.

Generated Java code phải có cùng nội dung bất kể môi trường dev, staging hay production. Nếu code generation cần một secret để tạo output, hãy xem lại thiết kế: thông thường generator chỉ cần schema, compiler option và version, không cần credential của runtime.

## 5. Inject secret lúc runtime

Có ba cách phổ biến:

1. **Secret manager API:** ứng dụng hoặc platform identity lấy secret từ dịch vụ quản lý secret khi khởi động hoặc khi cần.
2. **Mounted secret file:** platform mount private key, certificate hoặc password thành file với quyền đọc hạn chế.
3. **Environment variable:** runtime inject secret vào process environment; cách này dễ dùng nhưng cần kiểm soát dump process, diagnostics và quyền truy cập container.

Ưu tiên cơ chế phù hợp với loại secret và nền tảng triển khai. Private key thường thuận tiện khi được mount dưới dạng file hoặc cung cấp qua provider chuyên dụng. Token ngắn hạn có thể được cấp động qua workload identity hoặc credential provider.

Ví dụ Spring Boot có thể import config tree từ thư mục secret đã mount:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Các file trong thư mục có thể được expose thành property runtime theo tên file. Cấu hình này chỉ khai báo vị trí nguồn; giá trị secret nằm trong file được platform mount. Xác minh tên property, quyền file và cách binding của ứng dụng. Không bật endpoint hoặc log có thể dump toàn bộ environment/configuration mà không giới hạn quyền.

Với Spring gRPC, adapter hoặc TLS configuration đọc đường dẫn/credential ở runtime theo API được starter/version hỗ trợ. Không giả định mọi starter dùng cùng property để nạp certificate, private key hay truststore.

## 6. Kubernetes Secret và external secret provider

Kubernetes Secret object cho phép tách dữ liệu nhạy cảm khỏi ConfigMap và Deployment manifest thông thường. Tuy vậy, giá trị trong manifest tạo Secret thường được biểu diễn bằng Base64; Base64 không phải mã hóa.

Khi dùng Kubernetes Secret:

- Hạn chế RBAC: chỉ service account và operator cần thiết được đọc secret.
- Bật encryption at rest cho dữ liệu Secret trong etcd theo policy cluster.
- Không cấp quyền `list`/`watch` Secret rộng cho mọi workload.
- Mount secret read-only và giới hạn container/user có thể đọc.
- Không render giá trị secret vào Helm output, GitOps diff hoặc CI log.
- Xem xét external secret operator hoặc CSI driver để đồng bộ từ cloud secret manager/HSM.
- Theo dõi audit log khi secret được đọc hoặc thay đổi.

Ví dụ Deployment tham chiếu Secret:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-grpc
spec:
  template:
    spec:
      containers:
        - name: inventory
          image: registry.example/inventory-grpc:1.0.0
          volumeMounts:
            - name: grpc-tls
              mountPath: /var/run/secrets/grpc
              readOnly: true
      volumes:
        - name: grpc-tls
          secret:
            secretName: inventory-grpc-tls
~~~

Deployment chỉ tham chiếu `inventory-grpc-tls`. Secret object được tạo/cấp bởi một quy trình có quyền riêng; không nhúng `tls.key` vào chính manifest Deployment.

## 7. Helm và generated manifest

Helm template thường sinh manifest theo environment. Template nên nhận **tên secret hoặc reference**, không nhận private key/password dạng literal.

Ví dụ:

~~~yaml
volumes:
  - name: grpc-tls
    secret:
      secretName: {{ .Values.grpc.tls.existingSecret | quote }}
~~~

`values.yaml` có thể chứa tên `existingSecret`, port, target và policy không nhạy cảm. Tránh khai báo `privateKey`, `clientSecret` hoặc `password` bằng giá trị thật trong values file nằm trong repository.

Kiểm tra cả output sau render. Một template an toàn vẫn có thể bị override bởi pipeline truyền secret value vào `--set`, `--set-string`, generated values file hoặc command line. Command line có thể được ghi vào shell history, process listing hoặc CI log.

Nếu cần tạo Secret object, hãy để secret manager/operator hoặc một bước deploy được bảo vệ tạo object từ nguồn secret. Không lưu output có credential vào artifact dùng chung. Generated manifest nên chứa tên resource, volume reference hoặc external secret reference.

## 8. Docker build và CI/CD không được đóng gói secret

Không dùng Docker build argument hoặc environment variable trong image build để truyền secret runtime:

~~~dockerfile
# Không làm theo cách này:
ARG GRPC_PRIVATE_KEY
ENV GRPC_PRIVATE_KEY=$GRPC_PRIVATE_KEY
~~~

Giá trị có thể bị lưu trong image metadata, layer, build cache hoặc hệ thống build. Docker build secret mount có thể dùng cho credential chỉ cần trong một bước build (ví dụ tải dependency từ registry riêng), nhưng không biến nó thành runtime secret và không được copy secret vào image.

Pipeline nên tách rõ:

| Giai đoạn | Dữ liệu được phép dùng |
|---|---|
| Compile/code generation | Source, proto schema, compiler/plugin version, dependency config không bí mật |
| Unit test | Fake credential hoặc test secret ngắn hạn, phạm vi hẹp |
| Build image | Binary/generated code và non-secret runtime config |
| Render deployment config | Secret name/reference, không render secret value |
| Deploy/runtime | Workload identity hoặc quyền đọc secret manager/secret volume |

Không in environment, toàn bộ command, rendered manifest có dữ liệu nhạy cảm hoặc secret object vào log. Hạn chế quyền đọc artifact, cache, test report và build log; thiết lập thời gian lưu giữ phù hợp.

## 9. Secret trong gRPC metadata và client credentials

Một client có thể gửi bearer token trong metadata:

~~~text
authorization: Bearer <access-token>
~~~

Token là secret runtime. Không hardcode token trong generated config, source code hoặc constructor của stub. Client nên lấy token từ credential provider có khả năng refresh, rồi gắn token vào call metadata theo cơ chế `CallCredentials` hoặc interceptor được thiết kế cho credential.

Luồng phù hợp:

1. Client xác định workload identity hoặc principal.
2. Credential provider lấy token ngắn hạn từ identity/secret service.
3. Call credentials gắn header authorization cho RPC.
4. Token được refresh theo expiry; lỗi refresh được xử lý có kiểm soát.
5. Logging/interceptor loại bỏ hoặc redact authorization metadata.

Không log toàn bộ metadata map. Metadata có thể chứa bearer token, session identifier, tenant context hoặc dữ liệu nội bộ. Chỉ log allowlist như method, correlation ID và status; redact các header nhạy cảm.

Không đưa token vào `Status` description, exception message hoặc trace attribute. Nếu cần xác minh authentication trong test, dùng token giả hoặc token ngắn hạn của test environment và không lưu vào snapshot/artifact.

## 10. Secret cho TLS và mTLS

gRPC TLS có thể cần các loại dữ liệu sau:

| Dữ liệu | Có phải secret? | Nơi cung cấp |
|---|---|---|
| Server private key | Có | Secret manager hoặc read-only secret volume |
| Client private key cho mTLS | Có | Secret manager/identity provider |
| Keystore password | Có | Secret provider |
| Client bearer token | Có, thường ngắn hạn | Workload identity/token provider |
| Server certificate | Thông thường không | Certificate store/secret volume |
| Public CA certificate | Không phải private secret | Trust bundle được quản lý |

Generated config chỉ nên giữ path, secret resource name hoặc reference đến credential provider. Private key và password phải được đọc ở runtime với quyền tối thiểu.

Nếu dùng PKCS12/JKS, keystore chứa private key và certificate chain; truststore chứa CA/certificate mà peer tin cậy. Không đặt store password trong generated YAML. Nếu dùng PEM, bảo vệ private key file và giới hạn quyền đọc. Certificate public vẫn cần được cập nhật đúng khi rotate để tránh gián đoạn TLS.

## 11. Tránh rò rỉ qua Spring diagnostics và logging

Ngay cả khi secret không nằm trong generated file, nó vẫn có thể rò rỉ sau khi được inject:

- Log `Environment`, `System.getenv()` hoặc `System.getProperties()`.
- Gọi `toString()` trên configuration object chứa password/token.
- Bật debug logging cho HTTP/gRPC metadata.
- Expose Actuator `env`, `configprops`, heap dump hoặc diagnostic endpoint cho người không có quyền.
- Đưa secret vào exception message hoặc validation error.
- Ghi private key/token vào tracing baggage hoặc span attribute.

Hãy:

- Không log object cấu hình có trường secret.
- Dùng `toString` đã redact hoặc loại secret khỏi DTO log.
- Giới hạn quyền và exposure của Actuator/diagnostics.
- Redact `authorization`, cookie, API key và metadata nhạy cảm.
- Giữ secret trong bộ nhớ trong thời gian cần thiết; tránh copy vào cache/log không kiểm soát.
- Không đưa secret vào metric label vì vừa rò dữ liệu vừa tạo cardinality cao.

## 12. Rotation và thu hồi secret

Secret không nên tồn tại mãi với cùng một giá trị. Thiết kế rotation trước khi có sự cố:

1. Tạo version secret mới trong secret manager.
2. Cập nhật trust/credential policy để giai đoạn chuyển tiếp chấp nhận identity cần thiết.
3. Cấp secret mới cho workload hoặc mount version mới.
4. Reload credential nếu ứng dụng/starter hỗ trợ; nếu không, rollout/restart theo quy trình an toàn.
5. Kiểm tra health và gọi thử RPC qua TLS/mTLS.
6. Thu hồi version cũ sau khi toàn bộ client/server đã chuyển.
7. Lưu audit record về thời điểm, actor và version được rotate, không lưu giá trị secret.

Với certificate rotation, tránh thu hồi CA cũ trước khi các client đã tin CA mới. Với bearer token, ưu tiên token ngắn hạn và refresh theo expiry. Không giả định Spring gRPC starter tự reload private key hoặc truststore khi file thay đổi; xác minh khả năng reload của phiên bản và transport đang dùng.

Generated config không cần thay đổi khi secret value rotate nếu reference vẫn ổn định. Đây là một lợi ích quan trọng của việc tách reference khỏi secret material.

## 13. Kiểm tra generated artifacts trước khi phát hành

Hãy kiểm tra output, không chỉ kiểm tra source template:

- Quét repository và diff để phát hiện private key header, token pattern, password hoặc credential đã biết.
- Render Helm/Kustomize/Terraform output vào nơi có kiểm soát rồi scan trước khi publish.
- Kiểm tra Docker image layer/metadata và build artifact.
- Kiểm tra CI log, test report, cache và generated documentation.
- Kiểm tra protobuf generated source, descriptor và source map nếu có.
- Kiểm tra `application-*.yml`, config bundle và profile được đóng gói trong JAR.

Secret scanner có thể tạo false positive hoặc bỏ sót credential mới. Kết hợp pattern scanning, entropy detection, allowlist có review và kiểm tra thủ công các vùng rủi ro. Không đưa secret thật vào test chỉ để kiểm tra scanner.

Ví dụ kiểm tra nhanh các file PEM private key trong workspace:

~~~bash
grep -R -n --exclude-dir=.git \
  -E 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' .
~~~

Lệnh này chỉ là một tín hiệu ban đầu; không phát hiện được mọi token/password và có thể tìm thấy fixture giả. Dùng secret scanning phù hợp trong CI và bảo đảm output scan không in nguyên giá trị phát hiện.

## 14. Xử lý khi secret đã lọt vào generated config

Xóa dòng secret khỏi file hiện tại chưa đủ. Credential có thể còn trong Git history, image layer, CI log, artifact hoặc cache.

Quy trình xử lý:

1. Xác định loại credential, phạm vi quyền và nơi đã xuất hiện.
2. Revoke/rotate secret ngay theo mức độ rủi ro; không chờ dọn repository xong.
3. Kiểm tra audit log để xác định truy cập bất thường.
4. Xóa hoặc thay thế artifact bị lộ theo quy trình quản lý repository/registry/CI.
5. Nếu cần rewrite Git history, phối hợp chủ repository và thông báo người dùng phải cập nhật clone; history rewrite không thu hồi credential.
6. Bổ sung scan/pre-commit/CI rule và sửa pipeline để chỉ truyền secret reference.
7. Ghi nhận incident và xác minh secret mới không xuất hiện trong generated output.

Không gửi secret đã lộ vào chat, ticket hoặc báo cáo để “minh họa”. Chỉ ghi loại secret, vị trí, thời điểm, phạm vi và trạng thái rotate/revoke.

## 15. Checklist thiết kế generated config an toàn

| Câu hỏi | Kết quả mong muốn |
|---|---|
| File generated có chứa password/token/private key không? | Không |
| Template/values có chứa secret literal không? | Không |
| Generated config có dùng secret reference/path không? | Có |
| Secret được cấp lúc runtime từ nguồn có kiểm soát không? | Có |
| Workload chỉ có quyền đọc secret cần thiết không? | Có |
| Kubernetes Secret có encryption at rest và RBAC phù hợp không? | Có |
| Docker image/build cache có chứa secret không? | Không |
| CI log/artifact/test report đã được bảo vệ và scan chưa? | Có |
| gRPC metadata và TLS key material có bị log không? | Không |
| Có quy trình rotate/revoke và kiểm tra sau rotate không? | Có |
| Actuator/config diagnostics có thể expose secret không? | Không |

## 16. Lỗi thường gặp

| Cách làm sai | Hậu quả | Cách làm đúng |
|---|---|---|
| Ghi token vào `application-prod.yml` | Secret bị lưu trong source/artifact | Dùng secret reference và runtime injection |
| Đưa private key vào Helm values | Rendered manifest hoặc CI log có thể lộ key | Chỉ tham chiếu Secret resource/external provider |
| Dùng Base64 như thể là mã hóa | Ai đọc được manifest có thể decode giá trị | Bảo vệ Secret bằng RBAC và encryption at rest |
| Truyền secret qua Docker `ARG`/`ENV` khi build | Secret có thể nằm trong layer/cache/metadata | Dùng build secret cho nhu cầu build; runtime secret cấp lúc chạy |
| Gắn bearer token cố định trong interceptor | Khó rotate, dễ lộ và token hết hạn | Dùng credential provider/CallCredentials |
| Log toàn bộ gRPC metadata | Authorization token có thể xuất hiện trong log | Allowlist và redact header nhạy cảm |
| Tin rằng xóa file đã lộ là đủ | Git history, image và log vẫn còn credential | Revoke/rotate rồi dọn mọi bản sao |
| Giả định starter tự reload key | Workload có thể tiếp tục dùng certificate cũ | Xác minh reload support hoặc rollout có kiểm soát |

**Ghi nhớ:** Generated config là artifact có thể được lưu, chia sẻ và phát hành, vì vậy chỉ nên chứa cấu hình không nhạy cảm cùng secret reference. Giữ token, password và private key ngoài source, generated code, Helm output, Docker image và CI artifact. Cấp secret lúc runtime bằng secret manager, mounted file hoặc identity provider; giới hạn quyền đọc, redact log, scan output và chuẩn bị rotation/revocation. Với Spring gRPC, bảo vệ riêng bearer metadata và TLS/mTLS key material, đồng thời xác minh cấu hình theo đúng starter/version đang chạy.
