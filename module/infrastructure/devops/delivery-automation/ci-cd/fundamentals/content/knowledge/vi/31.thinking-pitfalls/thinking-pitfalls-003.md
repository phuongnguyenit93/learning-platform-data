# Cho rằng build thành công chứng minh đủ điều kiện phát hành

Một pipeline báo build thành công thường có nghĩa mã nguồn đã vượt qua một tập bước như resolve dependency, compile và đóng gói. Kết quả đó là tín hiệu tích cực, nhưng chưa đủ để kết luận phần mềm an toàn, tương thích và sẵn sàng phục vụ người dùng. Artifact có thể build được nhưng vẫn chứa lỗi nghiệp vụ, lỗ hổng bảo mật, dependency không được phép, cấu hình sai, migration không tương thích hoặc chưa có phương án vận hành khi triển khai gặp sự cố.

Cần phân biệt **build success** với **release readiness**. Build success xác nhận một công đoạn tạo sản phẩm đã hoàn tất. Release readiness là kết luận dựa trên tập bằng chứng rộng hơn: artifact có nguồn gốc rõ ràng, kiểm thử đạt, policy chất lượng và bảo mật được đáp ứng, cấu hình tương thích, môi trường đích sẵn sàng, quyền triển khai hợp lệ và kế hoạch xác minh sau triển khai đã được chuẩn bị.

## 1. Build thành công thực sự chứng minh điều gì?

Một build thường thực hiện một số công việc:

- Checkout đúng revision của source code.
- Resolve dependency và plugin.
- Compile source code.
- Chạy một số bước generate code hoặc package.
- Đóng gói JAR, WAR, container image hoặc bundle.
- Có thể chạy unit test nếu build task được cấu hình như vậy.

Nếu pipeline chỉ chạy `mvn package -DskipTests`, kết quả thành công không chứng minh unit test đã chạy. Nếu pipeline chỉ tạo container image, nó chưa chứng minh ứng dụng khởi động được trong môi trường gần production. Nếu build dùng cache hoặc dependency không được khóa, hai lần build cùng source cũng có thể tạo ra kết quả khác nhau.

Vì vậy, cần đọc đúng phạm vi của build job thay vì dựa vào nhãn màu xanh trên giao diện CI.

| Kết quả | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Compile thành công | Source đã biên dịch với toolchain và dependency của lần chạy | Logic nghiệp vụ đúng |
| Package thành công | Build tool đã tạo gói theo cấu hình | Gói không chứa file thừa hoặc secret |
| Unit test pass | Các test đã chạy đạt | Mọi luồng tích hợp và hành vi production đều đúng |
| Image build pass | Container image đã được tạo | Image an toàn, nhỏ gọn hoặc chạy được trên target |
| Pipeline xanh | Các job được cấu hình là required đã đạt theo rule hiện tại | Policy release đầy đủ và không có gate nào bị bỏ qua |

Một pipeline có thể xanh vì test chưa được bật, scan không phải required check hoặc một bước lỗi bị cấu hình `continue-on-error`. Do đó, phải xem pipeline definition và release policy là một phần của bằng chứng.

## 2. Phân biệt build, verification và release readiness

Một quy trình giao phần mềm nên có nhiều lớp xác minh, mỗi lớp trả lời một câu hỏi khác nhau.

| Giai đoạn | Câu hỏi | Ví dụ bằng chứng |
|---|---|---|
| Build | Có tạo được artifact từ source không? | Compile log, package checksum |
| Test | Hành vi được kiểm tra có đạt không? | Unit, integration, contract, E2E report |
| Quality analysis | Code có đáp ứng chuẩn chất lượng không? | Static analysis, coverage, lint |
| Security verification | Artifact và dependency có đạt policy bảo mật không? | SAST, SCA, secret scan, image scan, SBOM |
| Artifact verification | Sản phẩm có đúng nguồn gốc và toàn vẹn không? | Digest, signature, provenance |
| Compatibility | Artifact, config, schema và runtime có tương thích không? | Schema validation, migration test, compatibility report |
| Release authorization | Thay đổi có được phép phát hành không? | Approval, change record, policy result |
| Deployment validation | Phiên bản mới có hoạt động tốt sau deploy không? | Smoke test, SLI, business checks |

Không phải mọi dự án đều cần cùng số lượng bước hoặc cùng mức kiểm soát. Một thư viện nội bộ, một ứng dụng web và một dịch vụ thanh toán có rủi ro khác nhau. Tuy nhiên, mỗi release cần có tiêu chí tối thiểu được xác định trước và không được suy ra chỉ từ kết quả build.

## 3. Xây dựng release criteria thay vì chỉ nhìn trạng thái pipeline

Release criteria là tập điều kiện cần đạt trước khi artifact được promotion hoặc triển khai. Tiêu chí cần cụ thể, có thể kiểm tra và gắn với rủi ro của sản phẩm.

Ví dụ một release có thể yêu cầu:

- Artifact được tạo từ commit đã được review và branch được bảo vệ.
- Required unit, integration và contract tests đều pass.
- Static analysis không còn blocker theo policy.
- Dependency và container scan không có finding vượt ngưỡng chặn.
- Secret scan không phát hiện credential bị commit.
- SBOM và provenance được tạo, lưu cùng release.
- Artifact digest khớp với kết quả build và registry.
- Config schema và database migration đã được kiểm thử.
- Target environment và capacity đáp ứng điều kiện triển khai.
- Approval đã hoàn tất nếu môi trường yêu cầu.
- Có rollout strategy, post-deploy checks và phương án phục hồi.

Mỗi điều kiện nên có trạng thái rõ ràng:

- **Pass:** đã kiểm tra và đạt.
- **Fail:** đã kiểm tra và không đạt.
- **Waived:** có ngoại lệ được phê duyệt, có lý do, owner và thời hạn.
- **Not applicable:** không áp dụng và có giải thích.
- **Unknown/Not run:** chưa có bằng chứng; không được tự coi là pass.

Nếu một required gate không chạy do runner lỗi hoặc report không được tạo, release chưa có đủ bằng chứng. Không biến trạng thái unknown thành success chỉ để tiếp tục pipeline.

## 4. Kiểm thử phải phù hợp với rủi ro và luồng sử dụng

Test pass có ý nghĩa khi test bao phủ các hành vi quan trọng và chạy trên cấu hình gần với điều kiện thực tế.

Các lớp kiểm thử thường gặp:

| Loại test | Phạm vi | Hạn chế cần hiểu |
|---|---|---|
| Unit test | Hàm, class hoặc module nhỏ | Không xác minh tích hợp thật |
| Component test | Một thành phần cùng dependency giả lập | Có thể khác hành vi của hệ thống thật |
| Integration test | Database, queue, cache hoặc service thật trong môi trường test | Có thể chưa bao phủ production topology |
| Contract test | Tương thích API/event giữa producer và consumer | Không chứng minh toàn bộ nghiệp vụ |
| End-to-end test | Luồng người dùng từ đầu đến cuối | Chậm, dễ flaky và thường chỉ bao phủ một phần |
| Performance/load test | Latency, throughput, saturation dưới tải | Kết quả phụ thuộc dữ liệu và cấu hình môi trường |
| Resilience test | Hành vi khi dependency lỗi hoặc timeout | Cần giới hạn phạm vi và môi trường an toàn |

Một test suite xanh không có nghĩa mọi hành vi đều đúng. Cần xác định các luồng nghiệp vụ có tác động lớn, ví dụ đăng nhập, thanh toán, tạo đơn, phân quyền và ghi dữ liệu. Với thay đổi có phạm vi hẹp, có thể dùng test liên quan cộng với regression suite phù hợp; với thay đổi nền tảng hoặc contract, phạm vi kiểm thử cần rộng hơn.

Không nên chạy test chỉ để có con số coverage. Coverage là tín hiệu về phần code được thực thi, không đo trực tiếp chất lượng assertion hoặc tính đầy đủ của scenario.

## 5. Quality gate phải phản ánh policy thật

Static analysis, lint, coverage và kiểm tra chất lượng có thể phát hiện lỗi trước khi phát hành. Nhưng một dashboard chất lượng không tự động trở thành release gate.

Cần xác định:

- Rule nào là blocker, rule nào chỉ cảnh báo.
- Ngưỡng áp dụng cho code mới hay toàn bộ codebase.
- Finding cũ được xử lý theo baseline nào.
- Ai được phép waiver và trong thời hạn bao lâu.
- Gate nào là bắt buộc cho production.
- Khi scanner không hoạt động thì release dừng hay có quy trình ngoại lệ.

Ví dụ, coverage tổng thể 82% không chứng minh thay đổi mới được kiểm thử đủ. Có thể codebase có coverage cao nhưng phần logic vừa thêm không có test. Nên ưu tiên kiểm tra chất lượng trên code mới và các vùng rủi ro cao.

Một quality gate tốt trả về bằng chứng có thể truy vết tới commit và artifact. Không nên chỉ lưu một badge “Quality: Passed” mà thiếu report và phiên bản rule set đã sử dụng.

## 6. Build thành công không chứng minh an toàn bảo mật

Ứng dụng có thể compile và test pass nhưng vẫn chứa dependency có lỗ hổng, secret bị lộ hoặc cấu hình không an toàn.

Các lớp kiểm tra thường cần cân nhắc:

- **SAST:** phân tích source code để tìm mẫu lỗi bảo mật.
- **SCA:** kiểm tra dependency, license và lỗ hổng đã biết.
- **Secret scanning:** phát hiện token, private key hoặc credential trong repository và artifact.
- **Container/image scanning:** kiểm tra OS package, library và cấu hình image.
- **IaC scanning:** kiểm tra Terraform, Kubernetes manifest và cấu hình hạ tầng.
- **DAST/API testing:** kiểm tra ứng dụng đang chạy ở môi trường phù hợp.
- **SBOM:** ghi nhận thành phần phần mềm trong artifact.
- **Signature/provenance verification:** xác minh nguồn gốc và tính toàn vẹn.

Không phải mọi finding đều có mức độ giống nhau. Release policy nên xét severity, khả năng khai thác, mức độ phơi nhiễm, bản vá sẵn có và ngoại lệ được phê duyệt. Tuy nhiên, finding vượt ngưỡng blocker không được bỏ qua chỉ vì build thành công.

## 7. Xác minh artifact: đúng nội dung, đúng nguồn gốc

Build job có thể tạo ra artifact nhưng release pipeline cần biết chính xác artifact nào được đưa đi triển khai.

Với container image, nên tham chiếu bằng digest:

~~~text
registry.example.com/payments/api@sha256:...
~~~

Với package hoặc binary, lưu checksum và version bất biến trong release manifest.

Cần xác minh:

- Artifact được lấy từ registry/repository được tin cậy.
- Digest khớp với giá trị được ghi nhận sau build.
- Artifact được tạo từ repository, commit và workflow được cho phép.
- Signature hợp lệ nếu chính sách yêu cầu.
- Provenance chỉ ra builder, source revision và build process.
- Scan result và test evidence gắn với đúng digest.

Tag như `latest` hoặc một version có thể bị ghi đè không đủ để định danh nội dung. Nếu staging kiểm thử digest A nhưng production pull tag đã bị chuyển sang digest B, pipeline không còn promotion cùng một sản phẩm.

Nguyên tắc nên áp dụng là **build một lần, xác minh một lần, promote cùng artifact qua các môi trường**. Không build lại chỉ vì chuyển từ staging lên production.

## 8. Dependency và môi trường build cũng ảnh hưởng độ tin cậy

Build thành công chỉ phản ánh dependency và toolchain mà runner đã dùng ở thời điểm đó. Nếu dependency không được khóa, plugin được tải từ nguồn không kiểm soát hoặc runner dùng image thay đổi liên tục, kết quả build có thể khó tái lập.

Nên:

- Commit lockfile hoặc dependency constraints phù hợp với hệ sinh thái.
- Pin phiên bản compiler, build tool và action/plugin quan trọng.
- Dùng repository/registry dependency được quản lý.
- Kiểm tra checksum hoặc signature khi hệ sinh thái hỗ trợ.
- Kiểm soát cache và không để cache thay thế bước xác minh.
- Ghi lại build environment và toolchain version.
- Tạo SBOM và provenance cho artifact.

Cache giúp tăng tốc, nhưng cache không phải bằng chứng về tính toàn vẹn. Khi cache chứa dependency bị thay thế hoặc artifact cũ, build vẫn có thể hoàn tất với nội dung không mong muốn nếu không có kiểm tra tương ứng.

## 9. Cấu hình và secret có thể làm release thất bại dù artifact đúng

Cùng một artifact có thể hoạt động khác nhau tùy cấu hình môi trường. Một build xanh không chứng minh production config hợp lệ.

Trước release, cần xác minh:

- Config schema phù hợp với phiên bản ứng dụng.
- Endpoint và resource reference thuộc đúng môi trường.
- Feature flag có giá trị mặc định an toàn.
- Resource request, timeout và connection pool phù hợp.
- Secret reference tồn tại và workload identity có quyền đọc.
- Không có secret plaintext trong repository, image hoặc artifact.
- Config version/checksum là đúng bản đã review.

Không đưa giá trị secret vào release manifest. Chỉ lưu reference hoặc resource identifier; secret manager cấp giá trị theo identity và policy ở runtime.

Một config production có thể hợp lệ về cú pháp nhưng trỏ nhầm database staging hoặc một endpoint không tồn tại. Vì vậy, cần cả schema validation và kiểm tra ngữ nghĩa theo environment.

## 10. Database migration và khả năng tương thích

Artifact có thể build và test pass trên database mới tạo nhưng vẫn thất bại khi nâng cấp database production đang có dữ liệu.

Cần kiểm tra:

- Migration version và checksum.
- Fresh database migration.
- Upgrade test từ schema hiện tại.
- Backfill và dữ liệu NULL/duplicate.
- Lock, thời gian thực thi và dung lượng.
- Tương thích giữa phiên bản ứng dụng cũ và schema mới.
- Cách tiếp tục nếu migration bị gián đoạn.
- Roll-forward hoặc restore plan nếu thay đổi dữ liệu không thể đảo ngược.

Với rolling deployment, phiên bản cũ và mới có thể cùng chạy trong một khoảng thời gian. Chiến lược expand-and-contract giúp giữ tương thích: thêm cấu trúc mới, deploy code hỗ trợ cả hai, chuyển dữ liệu và consumer, rồi mới loại bỏ cấu trúc cũ trong một release sau.

Không coi migration thành công trên database test nhỏ là bằng chứng đầy đủ cho production. Cần đánh giá quy mô dữ liệu, loại DDL và hành vi của đúng database engine/version.

## 11. Environment readiness là một gate riêng

Một release đủ điều kiện về code vẫn có thể không triển khai được vì môi trường đích chưa sẵn sàng.

Trước khi deploy, cần kiểm tra:

- Target environment, account, region, cluster và namespace.
- Capacity, quota và tài nguyên dự kiến.
- Health của dependency như database, cache, queue và external provider.
- Network policy, DNS, certificate và ingress.
- Quyền deploy và workload identity.
- Cửa sổ thay đổi, concurrency lock và deployment đang chạy.
- Backup hoặc point-in-time recovery nếu thay đổi có rủi ro dữ liệu.
- Rollout strategy và khả năng quay lại.

Không dùng một credential có quyền rộng để thử deploy rồi mới biết target có đúng không. Target và authorization cần được xác minh trước khi thực hiện thay đổi có tác dụng phụ.

## 12. Release authorization và approval không thể suy ra từ build

Build job thường không biết ai có quyền phê duyệt production, thay đổi có thuộc cửa sổ triển khai hay không và approval có gắn với đúng artifact không.

Release pipeline cần xác minh:

- Required checks của commit đã đạt.
- Branch/tag và source repository thuộc policy.
- Artifact digest không đổi sau khi được kiểm thử.
- Approval gắn với release descriptor cụ thể.
- Người duyệt có role và scope phù hợp.
- Không có approval hết hạn hoặc bị vô hiệu sau khi input thay đổi.
- Environment protection rules đã được áp dụng.

Approval không nên là một nút nhấn chung chung. Người duyệt cần xem artifact digest, config version, target, migration, scan result, test evidence và phương án phục hồi.

Nếu artifact, config hoặc target thay đổi sau approval, cần xác minh lại và yêu cầu phê duyệt mới theo policy. Build xanh trước đó không làm cho một deployment request mới tự động được chấp thuận.

## 13. Release readiness cần bao gồm kế hoạch vận hành

Một artifact có thể được phát hành về mặt kỹ thuật nhưng chưa có cách quan sát hoặc phục hồi khi gặp lỗi. Trước release, cần chuẩn bị:

- Dashboard và alert cho các SLI quan trọng.
- Log, trace và correlation ID đủ để điều tra.
- Smoke test hoặc synthetic transaction.
- Guardrail cho error rate, latency và business metric.
- Rollout stages và thời gian quan sát.
- Kill switch hoặc feature flag nếu phù hợp.
- Rollback/roll-forward runbook.
- Người chịu trách nhiệm và kênh escalation.
- Cách xác minh sau phục hồi.

Nếu không thể xác định phiên bản nào đang phục vụ traffic hoặc không có cách kiểm tra hành vi nghiệp vụ, nhóm khó kết luận release đã ổn định dù deploy controller báo hoàn tất.

## 14. Ví dụ: build pass nhưng release chưa đủ điều kiện

Giả sử một pull request cập nhật dịch vụ thanh toán:

| Kiểm tra | Kết quả | Đánh giá |
|---|---|---|
| Compile và package | Pass | Artifact được tạo |
| Unit test | Pass | Logic đã kiểm tra ở phạm vi unit |
| Integration test | Pass | Luồng database test hoạt động |
| SAST | Pass | Không có blocker theo rule set |
| SCA | Fail | Dependency có lỗ hổng vượt ngưỡng policy |
| Secret scan | Pass | Không phát hiện credential |
| Artifact provenance | Pass | Nguồn build xác minh được |
| Production config validation | Not run | Chưa có bằng chứng cấu hình |
| Migration upgrade test | Not run | Chưa xác minh schema hiện hữu |
| Approval | Pending | Chưa được phép deploy production |

Trong trường hợp này, build thành công nhưng release chưa đủ điều kiện. Pipeline cần chặn promotion vì SCA fail và các gate bắt buộc chưa có kết quả. Nhóm phải cập nhật dependency, chạy lại kiểm tra và hoàn tất các bước xác minh còn thiếu.

Không nên dùng việc unit test pass để miễn trừ security scan. Hai kiểm tra trả lời hai câu hỏi khác nhau.

## 15. Ví dụ pipeline có gate giữa build và deploy

Workflow minh họa dưới đây tách build, kiểm thử, security verification và production deployment. Các script đại diện cho công cụ đã được tổ chức cấu hình.

~~~yaml
name: Release candidate

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      digest: ${{ steps.publish.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Build and package
        run: ./mvnw --batch-mode verify

      - name: Build and publish immutable artifact
        id: publish
        run: |
          digest="$(./scripts/publish-artifact.sh)"
          [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]]
          echo "digest=$digest" >> "$GITHUB_OUTPUT"

  verify:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
    steps:
      - uses: actions/checkout@v4
      - name: Verify artifact, provenance and security policy
        env:
          ARTIFACT_DIGEST: ${{ needs.build.outputs.digest }}
        run: ./scripts/verify-release-candidate.sh "$ARTIFACT_DIGEST"

  deploy-production:
    needs: [build, verify]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - name: Deploy verified artifact
        env:
          ARTIFACT_DIGEST: ${{ needs.build.outputs.digest }}
        run: ./scripts/deploy-by-digest.sh "$ARTIFACT_DIGEST"
~~~

Đây là khung minh họa, không tự tạo đầy đủ quality gate. Quyền `packages: write` ở job build dành cho trường hợp publish lên GitHub Packages; nếu registry bên ngoài dùng OIDC thì cấp `id-token: write` ở job cần xác thực và policy tương ứng. Job verify chỉ có quyền đọc package. Script publish cần tạo/lưu artifact, SBOM và provenance theo quy trình của tổ chức; script verify cần xác minh test/security/provenance/config/migration evidence theo policy và trả exit code khác 0 khi required gate không đạt. Environment production phải được cấu hình protection rules riêng; khai báo tên environment trong YAML không tự tạo reviewer hoặc approval.

Ví dụ cũng giả định publish script chỉ trả digest đã được registry xác nhận. Trong thực tế nên tách test trước publish nếu cần, tạo SBOM/provenance, ký artifact và lưu report. Job deploy phải dùng đúng digest đã được verify, không resolve lại tag di động.

## 16. Promotion qua môi trường không nên build lại

Một cách phát hành đáng tin cậy là promotion cùng artifact qua các môi trường:

1. Build artifact từ commit đã review.
2. Chạy test và security checks.
3. Publish artifact bất biến, ghi digest và provenance.
4. Deploy digest đó lên staging.
5. Chạy smoke, integration và post-deployment validation.
6. Thu thập approval và release evidence.
7. Promote cùng digest lên production.
8. Theo dõi guardrail sau deploy.

Config và secret reference có thể khác theo môi trường; artifact digest nên giữ nguyên. Nếu build lại khi lên production, kết quả không còn là chính artifact đã được kiểm thử ở staging.

Release manifest có thể lưu:

~~~yaml
releaseId: payments-2.8.1
sourceCommit: a1b2c3d4
artifact:
  repository: registry.example.com/payments/api
  digest: sha256:0123456789abcdef...
  provenance: attestations/payments-2.8.1
verification:
  unitTests: passed
  integrationTests: passed
  securityPolicy: passed
  configValidation: passed
target:
  environment: staging
~~~

Manifest này là ví dụ; các trạng thái cần được tạo từ kết quả thật của hệ thống kiểm tra, không nhập tay. Không đưa secret vào manifest. Khi promotion sang production, cập nhật target/deployment record theo cơ chế bất biến hoặc version hóa phù hợp.

## 17. Xử lý waiver và ngoại lệ một cách minh bạch

Có tình huống một gate chưa đạt nhưng tổ chức quyết định chấp nhận rủi ro có giới hạn, ví dụ finding đã được đánh giá là false positive hoặc chưa có bản vá thay thế. Ngoại lệ phải được ghi nhận, không được che bằng cách biến scanner thành pass.

Một waiver nên có:

- Gate và finding được miễn.
- Phạm vi artifact/version/environment.
- Lý do và bằng chứng đánh giá.
- Risk owner và approver.
- Biện pháp giảm thiểu.
- Thời điểm hết hạn.
- Ticket khắc phục và người phụ trách.

Waiver không nên áp dụng rộng cho mọi release hoặc vô thời hạn. Khi artifact digest thay đổi, finding được sửa hoặc waiver hết hạn, policy cần được đánh giá lại.

Một số điều kiện có thể không được phép waiver, tùy yêu cầu pháp lý và bảo mật. Cần phân biệt ngoại lệ được tổ chức phê duyệt với thao tác bỏ qua gate không có audit.

## 18. Ghi nhận release evidence để truy vết

Mỗi lần phát hành cần có một tập bằng chứng liên kết được source, build, artifact, verification và deployment.

Thông tin tối thiểu:

- Repository, commit SHA và pull request.
- Build run ID, toolchain và thời điểm.
- Artifact coordinate, digest và provenance.
- Test reports và phiên bản test suite.
- Quality/security policy result.
- SBOM và signature verification nếu áp dụng.
- Config version/checksum và migration version.
- Target environment và deployment revision.
- Approval record và waiver nếu có.
- Post-deployment validation và kết quả cuối.

Không lưu secret hoặc dữ liệu cá nhân không cần thiết trong release evidence. Dùng ID, digest và link tới report có quyền truy cập phù hợp.

Khi có sự cố, release evidence giúp trả lời: artifact nào đã chạy, được build từ commit nào, qua gate nào, ai phê duyệt và cấu hình nào đã được dùng. Nếu chỉ có trạng thái build xanh, nhóm không đủ thông tin để tái hiện hoặc điều tra lần phát hành.

## 19. Checklist xác định release readiness

Trước khi promotion hoặc deploy production, hãy kiểm tra:

- [ ] Build thành công từ source revision đã được xác định.
- [ ] Required tests đã chạy và có report.
- [ ] Quality gates áp dụng cho code mới và vùng rủi ro cao.
- [ ] Security scan đạt policy hoặc có waiver hợp lệ.
- [ ] Secret scan không phát hiện credential bị lộ.
- [ ] SBOM, signature và provenance có khi policy yêu cầu.
- [ ] Artifact digest được xác minh và không bị thay đổi.
- [ ] Dependency/toolchain được quản lý và có thể truy vết.
- [ ] Config schema, endpoint và secret references hợp lệ theo môi trường.
- [ ] Database migration đã được kiểm thử trên schema phù hợp.
- [ ] Target, capacity, dependency và quyền triển khai đã sẵn sàng.
- [ ] Approval gắn với đúng artifact, config và target.
- [ ] Có rollout strategy, observability, guardrail và phương án phục hồi.
- [ ] Post-deployment validation có tiêu chí pass/fail rõ.
- [ ] Release evidence được lưu và có thể truy xuất.

Build success là một điều kiện quan trọng để tạo artifact, nhưng release readiness cần nhiều bằng chứng hơn. Khi pipeline tách rõ build, verification, authorization, deployment và post-deployment validation, nhóm không phải đoán rằng một dấu tick xanh đồng nghĩa với an toàn. Mỗi release được promotion vì đã đáp ứng các điều kiện đã định nghĩa và có thể truy vết, giải thích hoặc phục hồi khi cần.

