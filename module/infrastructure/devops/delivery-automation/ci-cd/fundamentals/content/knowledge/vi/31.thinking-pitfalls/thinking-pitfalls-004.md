# Dựng lại artifact riêng cho mỗi môi trường rồi coi là cùng bản đã kiểm thử

Một nhóm có thể build ứng dụng thành công trên development, sau đó chạy lại lệnh build với cấu hình staging, rồi build thêm lần nữa cho production. Các file đầu ra có thể cùng tên và cùng version, ví dụ order-service:2.8.0, nên mọi người nghĩ rằng đó là cùng một bản đã được kiểm thử. Nhưng nếu mỗi lần build dùng source state, dependency, toolchain, build argument hoặc generated file khác nhau, nội dung thực tế có thể khác.

Đây là một lỗi tư duy nguy hiểm trong CI/CD: **đồng nhất version label với danh tính của artifact**. Version string giúp con người nhận diện một release, nhưng không chứng minh hai file có cùng byte hoặc cùng nội dung. Một artifact được test ở staging không tự động là artifact đã được đưa lên production nếu pipeline đã build lại ở giữa.

Tư duy an toàn hơn là **Build Once, Promote Many**: build một artifact có danh tính bất biến, kiểm thử và xác minh artifact đó, sau đó promote chính artifact ấy qua các môi trường. Những khác biệt theo môi trường như endpoint, feature policy, resource limit và secret được cung cấp bằng cấu hình runtime hoặc deployment configuration có kiểm soát. Mỗi lần promote phải giữ được liên kết giữa source revision, artifact digest, test evidence, approval và môi trường đích.

## 1. Vì sao build lại theo môi trường tạo ra rủi ro?

Giả sử pipeline có ba bước:

1. Build order-service cho development và chạy unit test.
2. Build lại order-service với cấu hình staging và chạy integration test.
3. Build lại order-service với cấu hình production rồi deploy.

Ngay cả khi cả ba lần đều dùng version label 2.8.0, chúng không nhất thiết tạo cùng artifact. Khác biệt có thể đến từ:

- Source revision thay đổi giữa các lần build.
- Dependency được resolve lại và nhận version khác.
- Compiler, JDK, package manager hoặc base image thay đổi.
- Build profile loại bỏ hoặc thêm module.
- Environment variable làm thay đổi code được compile hoặc resource được đóng gói.
- Generated source, frontend bundle hoặc migration file được tạo từ dữ liệu khác.
- Timestamp, file order hoặc metadata được nhúng vào package.
- Build cache chứa đầu ra cũ hoặc không hợp lệ.
- Build script lấy dữ liệu từ network tại thời điểm chạy.

Hậu quả là test evidence chỉ chứng minh một artifact cụ thể đã hoạt động. Nó không chứng minh một artifact khác có cùng tên sẽ có hành vi tương tự.

## 2. Version label không phải artifact identity

Version label thường là metadata dễ đọc: 2.8.0, release-2026.11 hoặc build-1842. Hai lần build có thể mang cùng label nhưng khác nội dung. Ngược lại, cùng một nội dung có thể được gắn thêm alias hoặc tag khác nhau.

| Khái niệm | Mục đích | Có chứng minh nội dung giống nhau không? |
|---|---|---|
| Version string | Nhận diện phiên bản theo quy ước | Không |
| Git commit SHA | Nhận diện revision của source repository | Không chứng minh toàn bộ build input giống nhau |
| Artifact filename | Tên file trong repository | Không |
| Registry tag | Nhãn trỏ đến image/package | Không; tag có thể bị di chuyển nếu registry cho phép |
| Digest/checksum | Định danh nội dung theo hash | Có thể xác nhận byte/content theo thuật toán hash và phạm vi được hash |
| Signature | Xác nhận chữ ký của signer trên nội dung/statement | Không tự chứng minh artifact an toàn hoặc đã được test |
| Provenance | Mô tả nguồn và quy trình tạo artifact | Hỗ trợ truy vết, cần xác minh nguồn và policy |

Với OCI image, digest như sha256:... là định danh nội dung manifest hoặc index theo đối tượng được tham chiếu. Với file JAR, ZIP hoặc package, có thể dùng SHA-256 của chính file. Cần hiểu digest được tính trên đối tượng nào; digest của image index đa kiến trúc khác digest của image manifest cho một platform cụ thể.

Không nên kết luận hai artifact giống nhau chỉ vì cùng version, tag hoặc commit SHA. Hãy so sánh digest của đúng artifact được deploy.

## 3. Build Once, Promote Many là gì?

Build Once, Promote Many nghĩa là một release candidate được build thành artifact, sau đó cùng artifact đó được đưa qua các môi trường. Pipeline không tạo một binary mới cho staging hay production chỉ để thay đổi endpoint hoặc cấu hình môi trường.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A[Source commit] --> B[Build immutable artifact]
    B --> C[Calculate digest and publish]
    C --> D[Run tests against artifact]
    D --> E[Promote same digest to staging]
    E --> F[Verify and approve]
    F --> G[Promote same digest to production]
    G --> H[Verify runtime digest and health]
~~~

Artifact được tạo một lần trong pipeline release candidate. Các môi trường tham chiếu cùng digest; deployment configuration có thể khác theo môi trường nhưng được quản lý và review riêng. Nhờ đó, bằng chứng test ở staging gắn với chính nội dung sẽ được chạy ở production.

Build once không có nghĩa chỉ chạy một lệnh build trong toàn bộ vòng đời phần mềm. Developer có thể build local, CI có thể build cho nhiều commit hoặc target khác nhau. Nguyên tắc áp dụng cho **một release candidate**: artifact được chọn để phát hành phải là artifact đã được kiểm tra và promote nguyên vẹn.

## 4. Phân biệt artifact, release và deployment configuration

Một hệ thống release thường có nhiều thành phần:

- **Source:** code và revision được chọn.
- **Build input:** toolchain, dependency lock, build script, base image và tham số được phép.
- **Artifact:** binary, package, container image, frontend bundle hoặc file triển khai.
- **Release metadata:** version, commit SHA, digest, provenance, SBOM và test evidence.
- **Deployment configuration:** replica count, resource limit, route, endpoint, feature policy và cấu hình theo môi trường.
- **Secret:** credential hoặc key được cấp từ secret manager khi runtime/deploy cần.
- **Deployment record:** môi trường, thời điểm, actor, digest thực tế và kết quả xác minh.

Không nên nhúng mọi khác biệt môi trường vào artifact. Ví dụ, URL database production, password, endpoint staging và số replica không nên được compile thành các binary riêng nếu chúng có thể được cấu hình an toàn ở thời điểm triển khai.

Ngược lại, không phải mọi thứ đều là runtime configuration. Một số giá trị phải được compile hoặc bundle vào artifact, ví dụ target architecture, static frontend assets hoặc code generation. Nếu chúng làm thay đổi nội dung, cần coi mỗi biến thể là một artifact riêng, có digest và test evidence riêng.

## 5. Ví dụ: cùng một container image qua ba môi trường

Giả sử pipeline build image một lần và publish:

~~~text
registry.example.com/platform/order-service@sha256:7a91...c42e
~~~

Deployment ở các môi trường tham chiếu cùng digest:

| Environment | Image reference | Cấu hình khác nhau |
|---|---|---|
| Development | Cùng digest | Endpoint dev, replica 1, log debug phù hợp |
| Staging | Cùng digest | Endpoint staging, dữ liệu test, replica 2 |
| Production | Cùng digest | Endpoint production, replica theo tải, secret production |

Các giá trị cấu hình khác nhau không làm thay đổi image. Nếu staging và production cần binary khác nhau, nhóm cần xác định đó là hai target artifact có danh tính riêng, không gọi chúng là cùng một artifact.

Tag như order-service:2.8.0 có thể được dùng để hiển thị, nhưng deployment nên pin theo digest. Nếu tag bị ghi đè, digest vẫn xác định chính xác nội dung đã được kiểm thử.

## 6. Ví dụ với package JAR

Với ứng dụng Java, pipeline có thể build một JAR:

~~~bash
./gradlew clean test bootJar
sha256sum build/libs/order-service.jar
~~~

JAR được publish lên artifact repository cùng checksum, version và provenance. Các môi trường tải đúng package theo digest hoặc tọa độ bất biến, sau đó cấp cấu hình qua environment variable, mounted config hoặc secret manager.

Không chạy lại Gradle với profile production để tạo một JAR khác rồi chỉ giữ version giống staging. Nếu profile thay đổi code, resource hoặc dependency được đóng gói, đó là artifact khác và cần test riêng.

Nếu ứng dụng cần build profile để chọn module hoặc target khác nhau, hãy làm rõ profile đó là một phần của artifact identity. Không dùng nhãn version chung để che giấu các biến thể nội dung.

## 7. Cấu hình theo môi trường nên được quản lý thế nào?

Cấu hình môi trường thường gồm:

- Endpoint của service phụ thuộc.
- Tên database, schema hoặc queue.
- Replica count, CPU/memory limit và autoscaling.
- Log level và sampling.
- Feature flag hoặc rollout percentage.
- Timeout, retry limit và circuit breaker policy.
- Ingress, domain, route và network policy.
- Secret reference hoặc workload identity.

Các giá trị này có thể được quản lý trong deployment manifest, Helm values, Kustomize overlay, config service hoặc secret manager. Cần review, version hóa và kiểm soát quyền thay đổi.

Ví dụ Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: registry.example.com/platform/order-service@sha256:7a91c42e
          env:
            - name: APP_ENV
              value: staging
            - name: PAYMENT_API_URL
              valueFrom:
                configMapKeyRef:
                  name: order-service-config
                  key: payment-api-url
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: order-service-db
                  key: password
~~~

Digest và tên tài nguyên trong ví dụ là placeholder. Manifest chỉ minh họa cách giữ image reference cố định và đưa cấu hình/secret từ nguồn riêng. Trong production, secret cần được quản lý bằng cơ chế phù hợp với nền tảng, quyền đọc tối thiểu và rotation; không lưu password dạng rõ trong repository.

## 8. Không để cấu hình môi trường âm thầm thay đổi binary

Một số build system cho phép profile hoặc environment variable thay đổi source/resource được đóng gói. Ví dụ:

- Profile staging loại bỏ hoặc thêm module.
- Build flag tắt một security check ở development.
- Frontend build nhúng API URL vào bundle.
- Script copy một file config khác vào package trước khi archive.
- Build lấy feature definition hoặc schema từ endpoint ngoài.

Nếu các giá trị đó thay đổi nội dung artifact, pipeline đã tạo ra các artifact khác nhau. Điều này không nhất thiết sai, nhưng phải được nhận diện và kiểm soát như các target riêng.

Với frontend static bundle, API URL có thể được nhúng trong file JavaScript khi build. Có hai lựa chọn:

1. Tạo một bundle cho mỗi environment và kiểm thử từng bundle; khi đó mỗi bundle là artifact riêng.
2. Tạo bundle độc lập môi trường, tải runtime config an toàn khi ứng dụng khởi động; khi đó có thể promote cùng bundle.

Không khẳng định build once nếu thực tế build argument hoặc generated config làm thay đổi binary.

## 9. Dependency drift giữa các lần build

Ngay cả khi source SHA không đổi, dependency có thể thay đổi nếu build không khóa phiên bản. Ví dụ khai báo version range, tag latest hoặc package không immutable có thể resolve ra nội dung mới trong lần build sau.

Để giảm drift:

- Dùng lockfile hoặc dependency constraints phù hợp.
- Pin base image theo digest khi cần tính bất biến.
- Quản lý plugin/compiler/toolchain version.
- Dùng repository mirror có kiểm soát và retention.
- Không tải script tùy ý từ URL không pin trong build.
- Ghi resolved dependency/materials vào provenance.
- Giữ cache theo khóa gồm input quan trọng và không dùng cache như nguồn sự thật.

Cache giúp tăng tốc nhưng không chứng minh tính đúng đắn. Nếu cache key thiếu compiler version hoặc build argument, một output cũ có thể được dùng trong bối cảnh không tương thích. Khi nghi ngờ, cần có cách build sạch và so sánh kết quả.

## 10. Build reproducible khác với build once

Hai khái niệm liên quan nhưng không giống nhau:

- **Build Once, Promote Many:** không build lại artifact của cùng release candidate khi chuyển môi trường.
- **Reproducible Build:** cùng source và build inputs được kiểm soát có thể tạo ra output giống nhau theo tiêu chí đã định nghĩa.

Build once không tự bảo đảm reproducibility. Một build có thể chứa timestamp, file ordering hoặc dependency không pin nhưng vẫn được promote cùng digest qua các môi trường.

Reproducible build cũng không thay thế promotion. Nếu nhóm build lại production từ cùng source và kết quả tình cờ có cùng checksum, điều đó vẫn cần được chứng minh; không nên mặc định.

Reproducibility hữu ích để xác minh build process, điều tra supply chain và tái tạo artifact. Promotion bất biến bảo đảm môi trường sau nhận đúng artifact đã được kiểm thử.

## 11. Test đúng artifact sẽ được deploy

Một lỗi phổ biến là test source/build output trong workspace rồi tạo lại package ở job khác. Nếu package sau đó khác output đã test, bằng chứng không còn gắn với artifact được phát hành.

Pipeline nên:

1. Build artifact và tính digest.
2. Publish artifact vào repository bất biến.
3. Tải artifact bằng digest ở job test nếu test chạy trên artifact đã đóng gói.
4. Chạy integration/smoke/security checks trên đúng package/image đó.
5. Ghi test evidence cùng artifact digest.
6. Promote chính digest qua môi trường kế tiếp.

Unit test có thể chạy trong build job trước khi package hoàn tất. Nhưng các kiểm tra packaging, container runtime, migration bundle, startup, smoke và deployment cần xác minh đúng artifact cuối cùng khi có thể.

Nếu test chỉ chạy trên source tree mà không kiểm tra package đã đóng gói, có thể bỏ sót file thiếu, resource sai hoặc Docker layer không chứa nội dung cần thiết.

## 12. Artifact repository phải hỗ trợ tính bất biến

Artifact repository/registry là nơi lưu package và phân phối chúng cho các môi trường. Cần thiết kế để artifact đã được publish không bị thay thế âm thầm.

Các kiểm soát hữu ích:

- Immutable version hoặc không cho overwrite release coordinate.
- Digest/checksum được lưu và xác minh khi download.
- Quyền publish tách khỏi quyền read/promote.
- Retention giữ artifact trong thời gian cần rollback/audit.
- Audit log cho publish, delete, tag và permission change.
- Replication/mirror có kiểm tra integrity.
- Quarantine hoặc revoke khi artifact bị phát hiện có vấn đề.

Nếu registry cho phép tag mutable, pipeline cần deploy theo digest và có policy hạn chế ai được di chuyển tag release. Tag là alias thuận tiện cho con người; digest là reference xác định nội dung.

Không xóa artifact cũ ngay sau deploy thành công. Rollback, forensic investigation hoặc rebuild môi trường có thể cần chính artifact đó.

## 13. Promotion là thay đổi trạng thái tin cậy, không phải build mới

Promotion đưa artifact đã vượt qua một tập kiểm tra sang môi trường hoặc giai đoạn tin cậy cao hơn. Mỗi bước promotion nên ghi:

- Artifact digest và version label.
- Source commit và repository.
- Build provenance và signer identity.
- Test/scan evidence.
- Environment nguồn và đích.
- Policy gate và approval.
- Actor hoặc automation identity.
- Thời điểm và kết quả.

Promotion không làm thay đổi nội dung artifact. Nếu cần chỉnh sửa binary, thay package, repack image hoặc chèn file environment-specific, đó là một artifact mới và phải có digest/evidence mới.

Một release record có thể tham chiếu cùng digest nhưng có nhiều deployment record cho dev, staging và production. Mỗi deployment record có cấu hình, approval và kết quả xác minh riêng.

## 14. Ví dụ pipeline build một lần rồi promote

Ví dụ workflow khái niệm:

~~~mermaid
flowchart TD
    A[Commit merged] --> B[Build and test source]
    B --> C[Package artifact]
    C --> D[Calculate digest]
    D --> E[Publish immutable artifact]
    E --> F[Test packaged artifact]
    F --> G[Promote digest to development]
    G --> H[Promote same digest to staging]
    H --> I[Approval and policy checks]
    I --> J[Promote same digest to production]
    J --> K[Verify runtime digest and health]
~~~

Mỗi môi trường có thể có deployment configuration riêng. Nhưng artifact reference cần giữ nguyên. Nếu digest thay đổi, pipeline phải coi đó là artifact khác và chạy lại các gate phù hợp.

## 15. Ví dụ GitHub Actions: build/publish một lần, deploy bằng digest

Workflow minh họa dưới đây tách job build khỏi các job deploy. Build job tạo image, push một lần và lưu digest thành artifact nhỏ; các job sau tải lại reference đó:

~~~yaml
name: Build and promote

on:
  push:
    branches: [main]

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build and push
        run: |
          docker build -t "ghcr.io/example/order-service:$GITHUB_SHA" .
          docker push "ghcr.io/example/order-service:$GITHUB_SHA"
          DIGEST="$(crane digest "ghcr.io/example/order-service:$GITHUB_SHA")"
          printf '%s\n' "ghcr.io/example/order-service@$DIGEST" > image-ref.txt
      - name: Upload image reference
        uses: actions/upload-artifact@v4
        with:
          name: image-reference
          path: image-ref.txt

  verify-image:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Verify packaged image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./verify-image.sh "$IMAGE_REF"

  deploy-staging:
    needs: verify-image
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Deploy tested image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./deploy.sh --environment staging --image "$IMAGE_REF"

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    steps:
      - name: Download image reference
        uses: actions/download-artifact@v4
        with:
          name: image-reference
      - name: Deploy the same image
        run: |
          IMAGE_REF="$(cat image-ref.txt)"
          ./deploy.sh --environment production --image "$IMAGE_REF"
~~~

Đây là ví dụ minh họa cần điều chỉnh theo registry, deployment tool và permission policy của repository. Runner phải được xác thực với registry bằng identity phù hợp; không hardcode credential. Trong production nên pin GitHub Actions theo commit SHA nếu policy yêu cầu. Job production cần approval/protection rule phù hợp.

Điểm quan trọng là job staging và production dùng cùng file image reference được tạo từ job build. Không gọi build trong từng job deploy. Nếu deploy script tự build hoặc mutate image, nguyên tắc promotion đã bị phá vỡ.

## 16. Ví dụ GitLab CI: artifact digest đi qua stages

GitLab pipeline có thể lưu digest thành dotenv artifact để job sau dùng lại:

~~~yaml
stages:
  - build
  - verify
  - staging
  - production

build-image:
  stage: build
  script:
    - docker build -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA" .
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA"
    - DIGEST="$(crane digest "$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA")"
    - echo "IMAGE_REF=$CI_REGISTRY_IMAGE@$DIGEST" > image.env
  artifacts:
    reports:
      dotenv: image.env

verify-image:
  stage: verify
  needs:
    - job: build-image
      artifacts: true
  script:
    - ./verify-image.sh "$IMAGE_REF"

deploy-staging:
  stage: staging
  needs:
    - job: verify-image
      artifacts: false
    - job: build-image
      artifacts: true
  script:
    - ./deploy.sh staging "$IMAGE_REF"

deploy-production:
  stage: production
  needs:
    - job: deploy-staging
      artifacts: false
    - job: build-image
      artifacts: true
  when: manual
  script:
    - ./deploy.sh production "$IMAGE_REF"
~~~

Ví dụ giả định Docker CLI, crane và script deploy đã được cài đặt, registry authentication được cấu hình và dotenv artifact được truyền đúng theo phiên bản GitLab đang dùng. Cần kiểm tra semantics của needs/artifacts, protected environment và manual approval trong cấu hình thực tế.

Không build lại image ở deploy-staging hoặc deploy-production. Các job này chỉ nhận reference đã được tạo ở build stage và xác minh trước đó.

## 17. Artifact cho nhiều nền tảng hoặc kiến trúc

Không phải lúc nào cũng có một binary duy nhất chạy trên mọi nền tảng. Một ứng dụng có thể cần:

- Linux x86_64 và Linux ARM64.
- Windows và Linux package.
- Container image đa kiến trúc.
- Debug/release build hoặc FIPS-compliant variant.
- Frontend bundle cho target runtime khác nhau.

Mỗi biến thể có thể là một artifact riêng với digest riêng. Build Once, Promote Many vẫn áp dụng cho từng target artifact: build biến thể cần thiết, test đúng biến thể, rồi promote digest tương ứng. Với OCI multi-platform image, có thể publish một image index trỏ đến các platform manifest; cần biết runtime sẽ resolve manifest nào và xác minh đúng digest/index.

Không cố ép một artifact cho mọi target nếu runtime thực sự cần binary khác. Điều cần tránh là build lại cùng target theo môi trường rồi coi kết quả khác nhau là một bản.

## 18. Cấu hình thay đổi sau khi build có cần test lại không?

Artifact có thể bất biến nhưng cấu hình deployment vẫn thay đổi. Vì vậy, “cùng artifact” không có nghĩa “mọi deployment hoàn toàn giống nhau”.

Cần phân biệt:

- **Artifact validation:** package/image có đúng nội dung, chạy được và vượt qua các test tương ứng không?
- **Configuration validation:** cấu hình môi trường có hợp lệ, đầy đủ và tương thích với artifact không?
- **Deployment validation:** hệ thống đích có triển khai đúng digest và trạng thái mong muốn không?
- **Runtime verification:** service có hoạt động đúng dưới cấu hình và traffic thực tế không?

Nếu thay đổi config chỉ điều chỉnh replica hoặc endpoint đã được kiểm chứng, có thể chỉ cần validation tương ứng. Nếu config bật một code path mới, thay đổi authorization, timeout hoặc database behavior, cần test thêm theo rủi ro. Nếu config thay đổi nội dung artifact thì đó không còn là config runtime độc lập.

Hãy version hóa deployment configuration và lưu digest/commit của config cùng deployment record. Khi cần tái hiện release, phải biết cả artifact lẫn cấu hình đã áp dụng.

## 19. Secret phải được cấp lúc deploy/runtime

Secret không nên được bake vào artifact. Nếu password hoặc private key được đóng gói vào image/JAR, mọi môi trường dùng artifact đó đều có thể nhận secret, và secret khó rotation hoặc revoke.

Nên:

- Lấy secret từ secret manager hoặc workload identity khi deploy/runtime.
- Cấp quyền theo service và environment.
- Dùng credential ngắn hạn nếu nền tảng hỗ trợ.
- Không lưu secret trong build argument, image layer hoặc artifact metadata.
- Không ghi secret vào log, test report hoặc release notes.
- Có quy trình rotation và xác minh sau rotation.

Build job thường không cần quyền đọc secret production. Deploy job production mới nhận identity và quyền tối thiểu cần thiết sau approval. Tách quyền build khỏi quyền deploy giúp giảm ảnh hưởng nếu một dependency hoặc pull request không tin cậy bị khai thác.

## 20. Provenance và SBOM gắn với artifact nào?

Provenance mô tả artifact được tạo từ source và build process nào. SBOM liệt kê thành phần/phụ thuộc có trong artifact. Test report và scan report cũng cần gắn với đúng artifact.

Một release evidence set nên tham chiếu:

- Artifact digest.
- Source repository và commit SHA.
- Builder/workflow identity.
- Build parameters và materials quan trọng.
- Toolchain/base image/dependency version.
- Provenance/attestation và signature.
- SBOM digest hoặc reference.
- Test/scan result và thời điểm thực thi.
- Policy decision và approval.

Nếu build lại cho production, provenance và SBOM có thể khác dù source commit giống nhau. Nếu scan report được tạo cho digest A nhưng deploy digest B, report A không chứng minh B đã được scan.

Hãy xác minh chữ ký, signer identity và provenance theo trust policy. Một artifact có chữ ký hợp lệ vẫn có thể chứa lỗ hổng; chữ ký chứng minh nguồn ký theo key/identity, còn policy và security scan đánh giá các thuộc tính khác.

## 21. Promotion gate cần kiểm tra điều gì?

Trước khi promote sang môi trường có rủi ro cao hơn, pipeline có thể kiểm tra:

- Digest hiện tại khớp digest đã được build và test.
- Artifact tồn tại trong registry tin cậy và chưa bị quarantine/revoke.
- Signature và provenance hợp lệ theo policy.
- Test evidence thuộc đúng digest.
- SBOM/scan evidence đáp ứng freshness và severity policy.
- Deployment configuration đã được review và validate.
- Approval gắn với đúng release identity.
- Environment readiness và change window phù hợp.
- Migration/API compatibility và rollback plan đã sẵn sàng.

Gate phải fail closed khi bằng chứng bắt buộc thiếu, không truy xuất được hoặc không khớp. Không tự động coi “scanner không phản hồi” là “không có lỗ hổng”.

## 22. Staging không giống production, nhưng artifact phải giống

Staging có thể khác production về quy mô, dữ liệu, network, dependency và quyền. Không thể giả định một smoke test staging chứng minh production chắc chắn hoạt động.

Để tăng độ tin cậy:

- Dùng cùng artifact digest.
- Giữ cấu hình và topology gần production trong phạm vi cần thiết.
- Dùng dữ liệu synthetic hoặc đã được bảo vệ.
- Kiểm thử contract với dependency và version thực tế.
- Kiểm tra resource/scale behavior bằng test phù hợp.
- Validate production configuration trước khi deploy.
- Dùng canary/progressive rollout và post-deploy verification ở production.

Khác biệt môi trường nên được ghi nhận và quản lý. Nếu production có database engine hoặc extension khác staging, cần test compatibility ở môi trường đại diện hoặc có bằng chứng riêng. Build once không loại bỏ nhu cầu kiểm thử môi trường.

## 23. Rollback cần dùng artifact đã lưu, không build lại version cũ

Khi cần rollback, lấy artifact digest của release trước đó từ release/deployment record. Không build lại source branch cũ rồi giả định kết quả giống package trước.

Rollback cần xem xét:

- Artifact cũ còn trong registry và digest còn xác minh được không?
- Config cũ có được lưu/version hóa không?
- Database migration có backward compatible không?
- Event/message mới có thể được consumer cũ xử lý không?
- Secret hoặc certificate đã rotation có tương thích với version cũ không?
- Feature flag có cần tắt hoặc đổi không?
- Rollback có tạo side effect hoặc mất dữ liệu không?

Rollback artifact và rollback config là hai thao tác riêng. Có thể phải deploy digest cũ với config mới tương thích, hoặc khôi phục config cũ cùng artifact cũ. Cần runbook và test cho các tổ hợp đó.

Không phải mọi release đều có thể rollback an toàn. Khi schema/data đã thay đổi theo hướng không đảo ngược, có thể cần roll forward hoặc recovery plan thay vì chỉ đổi image digest.

## 24. Promotion qua nhiều môi trường và approval

Mỗi môi trường có thể có gate riêng:

| Stage | Bằng chứng/điều kiện | Hành động |
|---|---|---|
| Build | Source revision, build log, digest, provenance | Publish immutable artifact |
| Test | Unit/integration/contract/security checks trên đúng artifact | Đánh dấu candidate đủ điều kiện |
| Development | Deploy digest, smoke test, config validation | Xác minh behavior cơ bản |
| Staging | Integration/E2E, migration rehearsal, load/compatibility checks | Chuẩn bị release |
| Production | Approval, policy, environment readiness | Promote cùng digest |
| Post-deploy | Runtime digest, health, error/latency và business checks | Tiếp tục, pause hoặc rollback |

Approval nên tham chiếu release ID và digest. Nếu artifact thay đổi, approval cũ không tự động áp dụng cho nội dung mới. Nếu chỉ config thay đổi, policy cần xác định có cần approval lại hay không tùy mức rủi ro.

## 25. GitOps và desired state cũng phải pin digest

Trong GitOps, repository cấu hình mô tả desired state của môi trường. Nếu manifest chỉ tham chiếu mutable tag như latest, controller có thể kéo nội dung khác vào thời điểm reconcile mà không có commit config mới.

Nên cập nhật manifest bằng digest hoặc tag bất biến theo policy. Pull request thay đổi desired state cần liên kết release record, artifact digest và approval. GitOps controller sau đó reconcile đúng reference đã review.

Nếu dùng automation để bump image reference, bot cần kiểm tra artifact evidence trước khi mở hoặc merge thay đổi. Không coi việc tag được tạo là bằng chứng artifact đã qua test.

## 26. Những ngoại lệ hợp lệ và cách xử lý

Có trường hợp cần build khác nhau theo môi trường hoặc target. Điều quan trọng là không gọi nhầm chúng là cùng artifact:

- **Frontend build nhúng API endpoint:** tạo bundle riêng cho từng environment và test từng bundle, hoặc chuyển endpoint sang runtime config để dùng chung bundle.
- **Platform-specific binary:** build riêng cho từng OS/architecture; mỗi biến thể có digest và evidence riêng.
- **FIPS/compliance build:** build variant riêng với toolchain/base image được kiểm soát và policy riêng.
- **Customer-specific package:** nếu package khác nội dung theo tenant, phải quản lý như artifact variant và kiểm thử/ghi provenance tương ứng.
- **Code generation theo schema:** schema đầu vào là build material; thay đổi schema tạo artifact mới.

Một ngoại lệ hợp lệ phải có lý do, target identity, build input rõ và test evidence. Không nên dùng “production cần khác” làm lý do chung chung để build lại mọi thứ.

## 27. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Build riêng dev/staging/prod nhưng dùng cùng version | Không biết binary nào thực sự được test | Build một candidate, promote theo digest |
| Deploy bằng mutable tag | Tag có thể trỏ sang image khác | Pin digest |
| Build lại ở job deploy | Artifact không còn là output đã test | Deploy đúng artifact reference từ build job |
| Dùng commit SHA làm bằng chứng byte giống nhau | Dependency/tool/config có thể khác | Ghi digest và provenance |
| Bake secret vào image/JAR | Secret lan qua mọi môi trường và khó rotation | Secret manager/workload identity |
| Bake endpoint môi trường vào code mà không quản lý variant | Tạo artifact khác nhưng tưởng cùng bản | Runtime config hoặc variant identity rõ |
| Test source nhưng không test package cuối | Bỏ sót packaging/layer/resource lỗi | Test đúng artifact đã publish |
| Promote thiếu scan/provenance | Không chứng minh artifact đạt policy | Gate trên digest và evidence |
| Build lại để rollback | Có thể tạo byte khác với release trước | Lấy artifact digest đã lưu |
| Không giữ artifact cũ | Không thể rollback/reproduce | Retention theo rollback/audit window |
| Coi staging giống production tuyệt đối | Bỏ qua khác biệt topology/config/data | Kiểm thử khác biệt và progressive rollout |
| Không lưu deployment config version | Không tái hiện được release | Version hóa config và ghi deployment record |

## 28. Checklist trước khi promote artifact

- [ ] Release candidate có source commit SHA rõ ràng.
- [ ] Build input/toolchain/dependency quan trọng được kiểm soát.
- [ ] Artifact được publish vào repository tin cậy.
- [ ] Artifact có digest và không bị overwrite.
- [ ] Test evidence tham chiếu đúng digest.
- [ ] Signature/provenance/SBOM được xác minh theo policy.
- [ ] Mỗi môi trường tham chiếu cùng digest cho cùng target artifact.
- [ ] Deployment configuration được version hóa và validate riêng.
- [ ] Secret được cấp qua cơ chế runtime/deploy an toàn.
- [ ] Approval gắn với đúng release identity và digest.
- [ ] Runtime sau deploy được xác minh digest thực tế.
- [ ] Rollback artifact/config và data compatibility có kế hoạch.
- [ ] Artifact và evidence được giữ theo retention policy.
- [ ] Mọi ngoại lệ build variant có target identity và test evidence riêng.

## 29. Kết luận

Dựng lại artifact riêng cho từng môi trường rồi coi chúng là cùng bản đã kiểm thử là một ngộ nhận vì version label và commit SHA không chứng minh nội dung package giống nhau. Build input, dependency, toolchain, build profile và generated file có thể làm thay đổi artifact giữa các lần chạy.

Với một release candidate, hãy build artifact, tính digest, publish bất biến, kiểm thử đúng artifact cuối cùng và promote chính digest đó qua các môi trường. Cấu hình môi trường và secret được quản lý riêng, có version, quyền và validation phù hợp. Provenance, SBOM, signature, test evidence, approval và deployment record đều phải liên kết với cùng artifact identity.

Build Once, Promote Many giúp giảm khác biệt không được kiểm soát giữa staging và production, tăng khả năng truy vết và làm rollback đáng tin cậy hơn. Khi cần tạo variant theo platform hoặc yêu cầu đặc biệt, hãy coi mỗi variant là một artifact riêng và kiểm thử đúng nội dung sẽ được triển khai.
