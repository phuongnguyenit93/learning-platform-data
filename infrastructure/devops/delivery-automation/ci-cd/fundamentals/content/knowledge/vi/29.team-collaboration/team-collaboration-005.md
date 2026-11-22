# Quản lý quyền phê duyệt và quy trình xử lý khẩn cấp

Pipeline CI/CD có thể thay đổi mã nguồn, xuất bản artifact, cập nhật hạ tầng, migration database và triển khai production. Vì vậy, quyền chạy một workflow, quyền phê duyệt release và quyền thực hiện thao tác có tác động lớn cần được thiết kế rõ ràng. Nếu mọi developer đều có thể tự phê duyệt và triển khai production, quality gate chỉ còn là một bước hình thức. Nếu mọi thay đổi đều phải chờ một nhóm nhỏ phê duyệt, quy trình có thể trở thành nút thắt và khiến nhóm tìm cách đi vòng.

Quản lý quyền phê duyệt cần cân bằng giữa tốc độ giao phần mềm, trách nhiệm và mức rủi ro. Quy trình thông thường phải xác định ai được yêu cầu, ai được review, ai được phê duyệt và identity nào thực sự thực hiện deploy. Khi có sự cố cần xử lý ngay, quy trình khẩn cấp phải cho phép hành động có kiểm soát, giới hạn thời gian và phạm vi quyền, ghi lại đầy đủ bằng chứng rồi hậu kiểm.

## 1. Tách quyền yêu cầu, review, approval và thực thi

Một lần phát hành có nhiều hành động khác nhau. Không nên gộp tất cả vào một quyền “release”.

| Quyền | Trách nhiệm | Ví dụ |
|---|---|---|
| Request | Đề xuất release hoặc thay đổi môi trường | Developer tạo release request |
| Review | Đánh giá mã, test, security và tác động | Code owner review pull request |
| Approve | Cho phép chuyển qua một gate cụ thể | Release manager phê duyệt production |
| Execute | Thực hiện deploy hoặc migration | CI deployment identity |
| Operate | Theo dõi và xử lý sau triển khai | On-call engineer |
| Administer | Quản lý policy, runner, secret và quyền | Platform/security administrator |

Một người có thể giữ nhiều vai trò trong tổ chức nhỏ, nhưng policy cần nêu rõ khi nào phải tách người yêu cầu và người phê duyệt. Ví dụ, người tạo production deployment không nên tự phê duyệt chính lần triển khai đó nếu policy yêu cầu independent approval.

Approval cũng không nhất thiết là quyền thực thi. Người duyệt cho phép một deployment descriptor cụ thể được triển khai; CI identity mới là danh tính có quyền gọi cloud API hoặc cập nhật cluster. Cách tách này giúp tránh cấp credential production trực tiếp cho từng người.

## 2. Xây dựng RBAC theo vai trò và phạm vi tài nguyên

Role-Based Access Control (RBAC) gán quyền theo vai trò thay vì cấp quyền tùy ý cho từng cá nhân. Trong CI/CD, role cần gắn với phạm vi cụ thể như repository, project, environment, service hoặc loại hành động.

Ví dụ:

| Role | Quyền điển hình | Giới hạn |
|---|---|---|
| Developer | Tạo branch, pull request, chạy CI | Không có quyền deploy production |
| Code owner | Review thay đổi thuộc phạm vi sở hữu | Không tự động có quyền cấp secret |
| Release operator | Khởi chạy release đã đủ điều kiện | Không tự sửa approval policy |
| Production approver | Phê duyệt production deployment | Không mặc nhiên có quyền thay đổi artifact |
| Incident commander | Điều phối xử lý sự cố | Quyền break-glass theo thời hạn |
| Platform admin | Quản trị runner, environment và policy | Thao tác đặc quyền phải được audit |
| Deployment identity | Deploy vào target được cấp | Không dùng tương tác người dùng hoặc quyền quản trị toàn hệ thống |

Không cấp role rộng hơn nhu cầu. Một approver của service A không nhất thiết được duyệt release service B. Một deployment identity của staging không nên truy cập production chỉ vì cùng pipeline sử dụng.

Nên dùng group được quản lý tập trung, đồng bộ thành viên theo quy trình nhân sự và rà soát định kỳ. Tránh cấp quyền lâu dài trực tiếp cho tài khoản cá nhân nếu nền tảng hỗ trợ group hoặc role binding có thể kiểm toán.

## 3. Áp dụng nguyên tắc least privilege và separation of duties

**Least privilege** yêu cầu mỗi người và mỗi job chỉ có quyền tối thiểu cần để hoàn thành nhiệm vụ. **Separation of duties (SoD)** tách các bước nhạy cảm giữa những vai trò khác nhau để giảm nguy cơ sai sót hoặc lạm dụng.

Một số quy tắc thường dùng:

- Developer có thể tạo pull request nhưng cần reviewer khác chấp thuận.
- Người tạo release request không tự phê duyệt production nếu policy cấm self-approval.
- Người duyệt không thể thay đổi artifact digest sau khi approval.
- Job build chỉ có quyền đọc source và ghi artifact vào registry được phép.
- Job deploy chỉ có quyền cập nhật service/environment được chỉ định.
- Quyền quản trị approval policy tách khỏi quyền chạy release.
- Secret production chỉ được cấp cho job sau khi các gate phù hợp đạt.

SoD không phải lúc nào cũng yêu cầu hai người cho mọi thao tác. Một thay đổi rủi ro thấp ở development có thể chỉ cần automated checks. Production, database migration phá vỡ tương thích hoặc thay đổi security policy có thể cần approval độc lập hoặc nhiều approver.

Policy cần dựa trên tác động, khả năng đảo ngược và phạm vi ảnh hưởng. Không biến approval thành một thao tác nhấn nút không có thông tin để đánh giá.

## 4. Xây dựng ma trận approval theo môi trường và mức rủi ro

Các môi trường có mức rủi ro khác nhau. Có thể xác định approval matrix làm chuẩn cho pipeline.

| Môi trường/thay đổi | Điều kiện tự động | Approval đề xuất |
|---|---|---|
| Local/dev | Build và test cơ bản | Không cần approval thủ công |
| Shared test | CI, integration test và scan đạt | Team owner khi có thay đổi ảnh hưởng môi trường chung |
| Staging | Artifact đã được xác minh, smoke test đạt | Release owner hoặc service owner theo policy |
| Production thông thường | Required checks, provenance, validation và release record đầy đủ | Approver độc lập hoặc nhóm được ủy quyền |
| Production rủi ro cao | Đánh giá migration, security, rollback và tác động nghiệp vụ | Hai người hoặc approval theo quorum |
| Emergency change | Incident được xác nhận, phạm vi tối thiểu và runbook phù hợp | Break-glass theo policy; hậu kiểm bắt buộc nếu không thể chờ |

Đây là mô hình tham khảo. Tổ chức cần xác định ngưỡng rủi ro và người có thẩm quyền cụ thể. Một hotfix nhỏ có thể cần ít bước hơn một thay đổi IAM, migration dữ liệu lớn hoặc thay đổi payment flow.

Approval matrix phải được thể hiện trong policy và cấu hình bảo vệ environment. Nếu chỉ ghi trong tài liệu nhưng pipeline không enforce, người chạy workflow có thể bỏ qua.

## 5. Approval phải gắn với một deployment request cụ thể

Người phê duyệt cần biết chính xác điều gì sẽ được triển khai. Một approval chung như “đồng ý release 2.8.1” có thể không đủ nếu tag hoặc cấu hình còn thay đổi được.

Deployment request nên xác định:

- Release ID và service.
- Artifact repository, version và digest.
- Source commit và build run.
- Provenance, signature và security scan result.
- Configuration version và checksum.
- Target environment, account, region, cluster và namespace.
- Database migration hoặc thay đổi hạ tầng liên quan.
- Deployment strategy, rollout size và timeout.
- Post-deployment guardrail và rollback/roll-forward plan.
- Người yêu cầu và thời điểm.

Sau approval, pipeline phải dùng đúng bộ đầu vào đã duyệt. Nếu digest, config version hoặc target thay đổi, approval cũ không còn đại diện cho request mới; cần xác minh lại và yêu cầu phê duyệt mới theo policy.

Có thể tạo fingerprint từ deployment descriptor đã chuẩn hóa. Pipeline ghi fingerprint vào approval record và so sánh trước khi thực thi. Cách này giúp phát hiện việc thay đổi âm thầm đầu vào sau khi được duyệt.

## 6. Cung cấp đủ thông tin để người duyệt ra quyết định

Approval có giá trị khi reviewer hiểu tác động và bằng chứng. Màn hình phê duyệt nên hiển thị hoặc liên kết tới:

- Nội dung thay đổi và pull request liên quan.
- Artifact digest và nguồn gốc build.
- Test, quality gate và security scan.
- Database migration và compatibility assessment.
- Environment và phạm vi tài nguyên bị tác động.
- Kết quả staging và post-deploy validation.
- Kế hoạch rollout, guardrail và rollback.
- Rủi ro đã biết, phụ thuộc và giới hạn.

Không yêu cầu người duyệt mở nhiều hệ thống rồi tự ghép thông tin bằng timestamp. Release record nên tổng hợp các bằng chứng cần thiết và liên kết tới report gốc.

Người duyệt cần có lựa chọn approve, reject hoặc request changes cùng lý do. Lý do từ chối nên được lưu để nhóm sửa đúng vấn đề, thay vì chỉ thấy một trạng thái “rejected”.

## 7. Bảo vệ environment trong GitHub Actions

GitHub Actions hỗ trợ environment protection rules. Có thể cấu hình required reviewers, wait timer và deployment branch/tag restrictions trong phần quản lý environment của repository hoặc organization, tùy gói và chính sách nền tảng.

Workflow có thể khai báo environment ở job deploy:

~~~yaml
name: Deploy production

on:
  workflow_dispatch:
    inputs:
      release_id:
        description: Approved release identifier
        required: true
        type: string

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Verify approved release descriptor
        env:
          RELEASE_ID: ${{ inputs.release_id }}
        run: ./scripts/verify-approved-release.sh "$RELEASE_ID"

      - name: Deploy
        env:
          RELEASE_ID: ${{ inputs.release_id }}
        run: ./scripts/deploy-release.sh "$RELEASE_ID"
~~~

Job tham chiếu environment `production` sẽ chịu các protection rules đã cấu hình cho environment đó. Ví dụ này không tự tạo required reviewers bằng YAML; cần cấu hình environment protection trong nền tảng và giới hạn ai có thể thay đổi cấu hình đó.

Nếu policy yêu cầu người phê duyệt độc lập, hãy bật tùy chọn ngăn người khởi chạy tự review (prevent self-review) khi nền tảng cung cấp. Đồng thời kiểm tra danh sách reviewer, quyền bypass và ai có thể sửa environment protection. Một workflow có khai báo `environment: production` nhưng environment không có protection rule phù hợp thì chưa tạo ra approval gate.

Script xác minh phải tra cứu release descriptor bất biến, kiểm tra approval gắn với đúng fingerprint và kiểm tra lại artifact/config/target trước khi deploy. Không tin release ID do người khởi chạy nhập nếu chưa xác minh nguồn và trạng thái.

Quyền `id-token: write` chỉ cần khi job dùng OIDC để nhận credential ngắn hạn từ cloud. Nếu không dùng OIDC, bỏ quyền này và dùng cơ chế identity phù hợp với quyền tối thiểu.

## 8. Bảo vệ nhánh và required checks

Approval ở production không thay thế review mã nguồn. Branch protection hoặc ruleset giúp bảo đảm thay đổi đi qua pull request, required status checks và code owner review trước khi merge.

Các kiểm soát có thể gồm:

- Bắt buộc pull request thay vì push trực tiếp lên branch bảo vệ.
- Yêu cầu số lượng approval phù hợp.
- Yêu cầu code owner review cho file nhạy cảm như workflow, IaC và policy.
- Dismiss approval cũ khi có commit mới theo policy.
- Bắt buộc required status checks từ workflow tin cậy.
- Giới hạn người có quyền bypass.
- Audit mọi thay đổi ruleset và branch protection.

Không dùng một job có thể bị bỏ qua làm required check. Cần bảo đảm tên check ổn định và kết quả gắn với commit đang được merge. Nếu workflow chạy trên code không tin cậy từ fork, không cấp secret production hoặc quyền ghi registry.

## 9. Approval theo nhiều cấp và quorum

Một số thay đổi cần nhiều góc nhìn: service owner hiểu logic nghiệp vụ, security reviewer hiểu quyền và dữ liệu, database owner hiểu migration, operations hiểu khả năng vận hành.

Có thể thiết kế approval theo loại thay đổi:

| Thay đổi | Approver cần thiết |
|---|---|
| Sửa lỗi logic service | Service owner/reviewer |
| Thay đổi API contract | Service owner và consumer owner khi cần |
| Database migration lớn | Database owner và release owner |
| IAM/secret policy | Security hoặc platform owner |
| Hạ tầng production | Platform/operations owner |
| Emergency change | Incident commander và approver theo break-glass policy |

Quorum là số lượng hoặc tổ hợp vai trò cần thiết để approval có hiệu lực. Ví dụ, một release có thể cần một service owner và một production approver; thay đổi IAM có thể cần security approver bắt buộc.

Cần tránh quy tắc mơ hồ như “hai người bất kỳ”. Nếu cần hai người, xác định có phải hai nhóm khác nhau hay không, người tạo request có được tính không và approval có bị vô hiệu khi nội dung thay đổi không.

## 10. Quy trình approval thông thường

Một luồng production release có thể diễn ra như sau:

~~~mermaid
flowchart TD
    A[Release request] --> B[Validate descriptor]
    B --> C[Required CI and security gates]
    C --> D[Staging deployment]
    D --> E[Post-deploy validation]
    E --> F[Prepare approval evidence]
    F --> G{Authorized approver}
    G -- Reject --> H[Return for changes]
    G -- Approve --> I[Revalidate approved fingerprint]
    I --> J[Production deployment]
    J --> K[Post-deploy guardrails]
    K --> L[Close release record]
~~~

Mỗi bước cần trạng thái rõ: requested, validating, awaiting approval, approved, rejected, deploying, verified hoặc failed. Timeout hoặc thiếu bằng chứng không được tự chuyển sang approved.

Approval có thể hết hạn nếu request không được triển khai trong khoảng thời gian quy định, đặc biệt khi dependency, policy hoặc trạng thái môi trường đã thay đổi. Trước deploy, pipeline nên xác minh approval vẫn còn hiệu lực.

## 11. Quyền đặc biệt và break-glass là gì?

Break-glass là quy trình cấp quyền khẩn cấp để xử lý sự cố khi quy trình thông thường không đáp ứng thời gian phản ứng cần thiết. Ví dụ:

- Production đang ngừng phục vụ và cần rollback ngay.
- Secret hoặc certificate sắp hết hạn làm gián đoạn dịch vụ.
- Một lỗi bảo mật cần vô hiệu hóa endpoint hoặc thu hồi credential.
- Migration hoặc cấu hình gây mất khả năng phục hồi cần thao tác khẩn cấp.
- Pipeline approval service bị lỗi trong khi incident đã được xác nhận.

Break-glass không phải tài khoản dùng chung với mật khẩu lưu trong wiki. Đó là một cơ chế truy cập đặc quyền có danh tính, phạm vi, thời hạn, lý do và audit. Quyền khẩn cấp phải được cấp theo nguyên tắc tối thiểu và thu hồi sau khi nhiệm vụ hoàn tất.

Nếu hệ thống có thể dùng role tạm thời qua identity provider, ưu tiên Just-in-Time (JIT) access và credential ngắn hạn. Tránh giữ access key production dài hạn trong runner hoặc máy cá nhân.

## 12. Thiết kế quy trình break-glass có kiểm soát

Một quy trình tham khảo:

1. **Khai báo incident:** tạo incident ID, mức độ nghiêm trọng và người chỉ huy.
2. **Nêu hành động cần làm:** service, environment, resource và lý do khẩn cấp.
3. **Xác minh người yêu cầu:** MFA hoặc cơ chế xác thực mạnh theo policy.
4. **Cấp quyền JIT:** role tối thiểu, phạm vi tài nguyên cụ thể và TTL ngắn.
5. **Approval khẩn cấp:** một approver độc lập nếu có thể; nếu không, ghi lý do không thể chờ.
6. **Thực hiện hành động:** dùng runbook đã chuẩn bị, ghi command/action và kết quả.
7. **Giám sát:** kiểm tra service, metric, audit và tác động phụ.
8. **Thu hồi quyền:** hết TTL hoặc chủ động revoke ngay sau khi xong.
9. **Hậu kiểm:** reviewer độc lập kiểm tra hành động, dữ liệu và bằng chứng.
10. **Cập nhật runbook:** bổ sung nguyên nhân và biện pháp ngăn tái diễn.

Break-glass nên có giới hạn thời gian và số lần sử dụng. Việc cấp quyền không nên tự động mở rộng thành quyền admin toàn cloud hoặc toàn bộ organization.

## 13. Khi nào có thể bỏ qua approval trước và hậu kiểm sau?

Có tình huống cần hành động nhanh hơn thời gian chờ approver. Policy có thể cho phép một nhóm on-call được thực hiện hành động đã định nghĩa trước, sau đó yêu cầu hậu kiểm độc lập.

Chỉ áp dụng cho phạm vi được nêu rõ:

- Loại incident đủ điều kiện.
- Người hoặc role được phép.
- Tập hành động được phép, ví dụ rollback về artifact đã xác minh hoặc tắt feature flag.
- Môi trường và service được phép.
- Giới hạn thời gian, số lần và mức tác động.
- Điều kiện phải thông báo và mở incident.
- Thời hạn hậu kiểm và người chịu trách nhiệm.

Không nên cho phép “bypass mọi approval khi có incident”. Một incident label do người khởi chạy tự nhập không đủ chứng minh quyền bỏ qua gate. Cần có incident record được xác thực hoặc policy do incident commander áp dụng.

Những hành động không thể đảo ngược như xóa dữ liệu, thay đổi IAM rộng hoặc restore database cần kiểm soát riêng. Nếu có thể, chuẩn bị phương án an toàn trước incident để giảm nhu cầu dùng quyền đặc biệt.

## 14. Quyền break-glass cần được giới hạn kỹ thuật

Policy chỉ có tác dụng khi hệ thống thực thi được giới hạn.

Các biện pháp:

- JIT role với TTL ngắn và scope theo account/project/resource.
- MFA hoặc strong authentication khi cấp quyền.
- Credential tạm thời, không dùng secret tĩnh dùng chung.
- Session recording hoặc command audit cho thao tác nhạy cảm nếu nền tảng hỗ trợ.
- Network boundary và runner được kiểm soát.
- Không cho phép quyền đặc biệt tồn tại lâu hơn incident.
- Cảnh báo khi break-glass được kích hoạt.
- Tự động thu hồi khi hết hạn.
- Bắt buộc hậu kiểm và xác nhận đã thu hồi.

Nếu dùng cloud IAM, có thể tạo role khẩn cấp riêng với policy hẹp. Role này không nên được cấp quyền thay đổi chính policy IAM hoặc xóa audit log. Người có quyền quản trị identity cần một quy trình kiểm soát riêng.

Không lưu credential khẩn cấp trong file pipeline, repository hoặc biến môi trường dùng chung. Nếu nền tảng có emergency access account, cần quản lý vault, rotation, kiểm tra định kỳ và audit mọi lần truy cập.

## 15. Ví dụ quy trình emergency rollback trong CI/CD

Có thể tạo workflow riêng cho rollback khẩn cấp, chỉ nhận release ID đã có trong release registry. Workflow không nên nhận image tag tùy ý rồi triển khai ngay.

Ví dụ khung GitHub Actions:

~~~yaml
name: Emergency rollback

on:
  workflow_dispatch:
    inputs:
      incident_id:
        description: Approved incident identifier
        required: true
        type: string
      release_id:
        description: Previously verified stable release
        required: true
        type: string

permissions:
  contents: read

jobs:
  emergency-rollback:
    runs-on: ubuntu-latest
    environment: production-emergency
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Verify incident and rollback target
        env:
          INCIDENT_ID: ${{ inputs.incident_id }}
          RELEASE_ID: ${{ inputs.release_id }}
        run: |
          ./scripts/verify-emergency-authorization.sh \
            "$INCIDENT_ID" "$RELEASE_ID"

      - name: Execute rollback
        env:
          INCIDENT_ID: ${{ inputs.incident_id }}
          RELEASE_ID: ${{ inputs.release_id }}
        run: |
          ./scripts/rollback-release.sh \
            --incident "$INCIDENT_ID" \
            --release "$RELEASE_ID"

      - name: Verify service recovery
        run: ./scripts/verify-production-health.sh
~~~

Environment `production-emergency` cần có policy riêng về ai được sử dụng và cách cấp quyền. Nếu cấu hình environment yêu cầu approval trước, hãy xác định rõ nhóm on-call/incident commander và quy trình xử lý khi approver không sẵn sàng. Workflow trên chỉ là khung; script phải xác minh incident, quyền, release digest, config compatibility và database state.

Không coi input incident ID là bằng chứng authorization. Script cần xác minh incident tồn tại và người chạy có quyền cho loại hành động đó. Sau rollback, workflow phải ghi lại kết quả và mở hậu kiểm theo policy.

## 16. Phân biệt emergency rollback với sửa nóng (hotfix)

Rollback đưa hệ thống về một release đã được xác minh trước đó. Hotfix tạo một thay đổi mới để sửa nguyên nhân trong khi giữ lại các phần cần thiết của phiên bản hiện tại.

| Tiêu chí | Emergency rollback | Emergency hotfix |
|---|---|---|
| Mục tiêu | Khôi phục phiên bản ổn định trước | Sửa lỗi bằng artifact mới |
| Tốc độ | Có thể nhanh nếu target đã sẵn sàng | Cần build và kiểm thử tối thiểu |
| Rủi ro | Không tương thích schema/config hoặc mất thay đổi mới | Code mới chưa được kiểm thử đầy đủ |
| Bằng chứng | Release cũ, digest và compatibility | Commit, build provenance, test và scan |
| Phục hồi tiếp | Điều tra release lỗi và lập kế hoạch phát hành lại | Theo dõi hotfix và đưa vào nhánh phát triển chính |

Không phải lúc nào rollback cũng an toàn. Nếu database đã có migration phá vỡ tương thích hoặc dữ liệu đã được ghi theo schema mới, đưa image cũ trở lại có thể khiến ứng dụng không chạy. Khi đó, có thể cần roll-forward hoặc hotfix tương thích.

Hotfix không được bỏ qua hoàn toàn kiểm thử. Tối thiểu cần compile/build, test liên quan, scan cần thiết và xác minh artifact. Sau khi sự cố được kiểm soát, cần merge hoặc cherry-pick thay đổi về nhánh phát triển chuẩn để tránh code bị mất ở release tiếp theo.

## 17. Hậu kiểm sau khi dùng quyền khẩn cấp

Mọi lần break-glass cần một review độc lập sau khi hệ thống ổn định. Hậu kiểm không nhằm đổ lỗi cho người trực mà nhằm xác minh quyền đã được dùng đúng mục đích và giảm nguy cơ lặp lại.

Nội dung hậu kiểm:

- Incident ID, severity, thời điểm và người chỉ huy.
- Danh tính người yêu cầu, approver và deployment identity.
- Quyền được cấp, scope, TTL và thời điểm revoke.
- Artifact/config/target trước và sau hành động.
- Lệnh hoặc thao tác đã thực hiện và kết quả.
- Bằng chứng health check, SLI và business validation.
- Tác động đến dữ liệu, migration và dependency.
- Những approval hoặc gate đã bypass, lý do và policy cho phép.
- Thời gian phát hiện, phản ứng và phục hồi.
- Hành động khắc phục và owner/due date.

Nếu quyền chưa được thu hồi, cần xử lý ngay trước khi đóng incident. Nếu audit log thiếu hoặc có thao tác ngoài scope, xem xét như một sự kiện bảo mật cần điều tra.

## 18. Audit trail và tính toàn vẹn của approval

Approval và break-glass phải để lại bằng chứng có thể kiểm tra. Audit record nên lưu:

- Actor và role tại thời điểm hành động.
- Hành động được yêu cầu, phê duyệt hoặc thực thi.
- Release/incident ID.
- Fingerprint của deployment descriptor.
- Artifact digest và target.
- Thời điểm, kết quả và lý do.
- Approver identity và approval decision.
- Permission/role được cấp và thời gian hiệu lực.
- Break-glass activation, renewal và revocation.
- Link đến log, test report và post-deployment evidence.

Audit log cần được bảo vệ khỏi sửa hoặc xóa bởi chính identity thực hiện deployment. Có thể gửi audit event đến hệ thống tập trung có quyền ghi riêng và retention policy.

Không ghi secret hoặc dữ liệu cá nhân không cần thiết vào audit record. Correlation ID, release ID và resource identity thường đủ để nối các sự kiện.

## 19. Rà soát quyền định kỳ và xử lý thay đổi nhân sự

Quyền phê duyệt dễ lỗi thời khi nhân sự thay đổi, team chuyển ownership hoặc một dự án ngừng hoạt động.

Nên có quy trình:

- Review thành viên approver group theo chu kỳ.
- Thu hồi quyền khi nhân sự rời nhóm hoặc đổi vai trò.
- Xóa quyền tạm sau release/incident.
- Kiểm tra service account và token không còn sử dụng.
- Rà soát người có quyền bypass branch protection hoặc environment protection.
- Kiểm tra người có thể sửa workflow và policy approval.
- Đánh giá quyền của external contributor và bot.
- Kiểm tra account khẩn cấp và cơ chế recovery định kỳ.

Mỗi role cần owner chịu trách nhiệm xác nhận danh sách thành viên. Không để group production approver tồn tại mà không ai chịu trách nhiệm.

## 20. Kiểm thử quy trình approval và break-glass

Quy trình quyền cần được kiểm thử trước khi phụ thuộc vào nó trong incident thật.

Các tình huống nên kiểm tra:

| Tình huống | Kết quả mong đợi |
|---|---|
| Người không có quyền approve | Không thể thông qua gate |
| Người tạo deployment tự approve | Bị chặn nếu policy cấm self-approval |
| Artifact digest đổi sau approval | Approval không còn hợp lệ |
| Target environment đổi sau approval | Yêu cầu xác minh/approval lại |
| Required check thất bại | Không thể deploy production |
| Approver không phản hồi | Request hết hạn hoặc escalation theo policy |
| Break-glass role hết TTL | Không thể tiếp tục thao tác |
| Người dùng rời nhóm | Quyền được thu hồi |
| Emergency rollback dùng release không xác minh | Bị chặn |
| Hậu kiểm chưa hoàn tất | Incident/recovery record chưa được đóng theo policy |

Có thể chạy diễn tập game day: giả lập production deploy lỗi, approver không sẵn sàng, cấp quyền JIT, rollback và hậu kiểm. Mục tiêu là xác minh cả thời gian phản ứng lẫn khả năng truy vết.

Không thử break-glass bằng credential production thật trong môi trường không được kiểm soát. Dùng staging hoặc sandbox có policy tương tự.

## 21. Checklist quản lý approval và xử lý khẩn cấp

Trước khi đưa quy trình phát hành vào vận hành, hãy kiểm tra:

- [ ] Quyền request, review, approve, execute và operate được phân biệt.
- [ ] RBAC có phạm vi theo repository, service và environment.
- [ ] Least privilege và separation of duties được áp dụng theo mức rủi ro.
- [ ] Approval matrix quy định rõ người/nhóm duyệt từng loại thay đổi.
- [ ] Approval gắn với release descriptor, artifact digest, config và target cụ thể.
- [ ] Thay đổi đầu vào sau approval buộc xác minh hoặc approve lại.
- [ ] Approver có đủ test, scan, migration và rollback evidence.
- [ ] Branch protection và required checks được enforce.
- [ ] Self-approval và bypass được kiểm soát.
- [ ] Environment protection có reviewer, wait timer và branch restriction phù hợp.
- [ ] Break-glass có incident ID, lý do, scope, TTL và identity rõ ràng.
- [ ] Quyền khẩn cấp dùng JIT/credential ngắn hạn và có MFA theo policy.
- [ ] Hành động emergency được audit và giám sát.
- [ ] Quyền được revoke ngay sau khi hoàn tất hoặc hết TTL.
- [ ] Có hậu kiểm độc lập và thời hạn hoàn thành.
- [ ] Rollback target đã được xác minh và tương thích schema/config.
- [ ] Có kiểm thử và diễn tập quy trình approval/break-glass.
- [ ] Approver group và quyền bypass được rà soát định kỳ.

Quản lý approval tốt giúp quyết định phát hành có người chịu trách nhiệm và có bằng chứng. Quy trình break-glass tốt giúp đội vận hành phản ứng nhanh khi có sự cố mà vẫn giữ được giới hạn quyền, dấu vết và hậu kiểm. Khi approval gắn với đúng bộ đầu vào và quyền khẩn cấp chỉ tồn tại trong phạm vi cần thiết, CI/CD có thể vừa giao phần mềm nhanh vừa duy trì khả năng kiểm soát production.

