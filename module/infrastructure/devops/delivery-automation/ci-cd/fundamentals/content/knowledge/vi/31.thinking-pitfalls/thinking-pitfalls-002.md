# Đồng nhất Continuous Delivery với Continuous Deployment

Trong CI/CD, hai thuật ngữ Continuous Delivery và Continuous Deployment thường được viết tắt cùng là CD. Vì cùng xuất hiện trong một pipeline và đều hướng đến việc đưa phần mềm đến production nhanh hơn, chúng dễ bị dùng thay thế cho nhau. Tuy nhiên, hai khái niệm mô tả hai mức tự động hóa khác nhau ở quyết định phát hành cuối cùng.

**Continuous Delivery** nghĩa là mọi thay đổi sau khi vượt qua pipeline đều ở trạng thái có thể phát hành an toàn. Việc triển khai lên production có thể tự động hoặc cần một quyết định/approval trước khi thực hiện. **Continuous Deployment** đi thêm một bước: mọi thay đổi vượt qua các điều kiện tự động đều được triển khai lên production mà không cần người phê duyệt từng lần phát hành.

Continuous Deployment là một cách triển khai Continuous Delivery ở mức tự động hóa cao hơn. Cả hai đều cần build có thể tái lập, kiểm thử tự động, quản lý artifact, kiểm soát cấu hình, khả năng quan sát và phương án phục hồi. Điểm phân biệt nằm ở chỗ ai hoặc điều gì quyết định mỗi thay đổi được đưa vào production.

## 1. Hai khái niệm và điểm khác nhau cốt lõi

### 1.1. Continuous Delivery

Continuous Delivery là năng lực giữ phần mềm luôn trong trạng thái sẵn sàng phát hành. Mỗi thay đổi đi qua các bước kiểm tra tự động, tạo artifact có thể triển khai và được xác minh trên những môi trường phù hợp. Khi pipeline hoàn tất, nhóm có thể phát hành phiên bản đó theo nhu cầu kinh doanh.

Một luồng Continuous Delivery thường có đặc điểm:

- Commit được build và kiểm thử tự động.
- Artifact được đóng gói, định danh và lưu trữ có truy vết.
- Artifact được triển khai tự động lên môi trường kiểm thử hoặc staging.
- Các quality gate và kiểm chứng sau triển khai được thực hiện.
- Production deployment có thể chờ approval, lịch phát hành hoặc quyết định vận hành.
- Khi được phê duyệt, chính artifact đã được kiểm chứng được promote lên production.

Approval ở production là một điểm kiểm soát phát hành. Nó không có nghĩa nhóm phải build lại, copy file thủ công hoặc chạy một bộ lệnh triển khai không được quản lý. Một hệ thống vẫn có thể là Continuous Delivery dù bước cuối cần người quyết định thời điểm release.

### 1.2. Continuous Deployment

Continuous Deployment tự động triển khai mọi thay đổi đã vượt qua các gate bắt buộc lên production. Không có bước con người phê duyệt riêng cho từng lần triển khai thông thường.

Một luồng Continuous Deployment thường có đặc điểm:

- Mọi commit đủ điều kiện được build và kiểm thử tự động.
- Artifact được triển khai qua các môi trường theo policy.
- Canary, progressive rollout hoặc cơ chế tương đương giới hạn phạm vi ảnh hưởng.
- Hệ thống tự đánh giá telemetry và quality gate.
- Khi mọi điều kiện đạt, rollout tiếp tục đến toàn bộ production.
- Khi điều kiện thất bại, rollout tự dừng, chuyển traffic hoặc kích hoạt biện pháp phục hồi theo policy.

Continuous Deployment không có nghĩa mọi commit bất kể chất lượng đều được đưa lên production. Thay đổi chỉ được triển khai khi pipeline chứng minh các điều kiện đã định nghĩa đều đạt. Một gate thất bại phải chặn rollout.

### 1.3. Bảng so sánh

| Khía cạnh | Continuous Delivery | Continuous Deployment |
|---|---|---|
| Mục tiêu | Mọi thay đổi luôn sẵn sàng phát hành | Mọi thay đổi đạt gate tự động được phát hành |
| Build và test | Tự động | Tự động |
| Artifact | Được tạo và truy vết | Được tạo và truy vết |
| Deploy lên staging | Thường tự động | Thường tự động |
| Quyết định production | Có thể cần approval hoặc lịch phát hành | Tự động theo policy |
| Vai trò con người | Có thể quyết định thời điểm release | Thiết kế policy, giám sát ngoại lệ và cải tiến hệ thống |
| Tốc độ đưa thay đổi đến production | Theo nhịp phát hành được chọn | Theo nhịp thay đổi vượt qua gate |
| Yêu cầu tự động hóa | Cao | Rất cao, bao gồm rollout và phục hồi |
| Phù hợp | Môi trường có cửa sổ phát hành hoặc approval bắt buộc | Dịch vụ có kiểm thử, telemetry và kiểm soát rủi ro trưởng thành |

Điểm phân biệt không phải là pipeline có tự động deploy lên staging hay không. Cả hai mô hình đều có thể tự động hóa phần lớn pipeline. Câu hỏi quyết định là: **mỗi thay đổi đạt gate có tự động được đưa vào production hay vẫn chờ một quyết định phát hành?**

## 2. Quan hệ giữa hai mô hình

Có thể xem Continuous Delivery là nền tảng, còn Continuous Deployment là mức tự động hóa production release dựa trên nền tảng đó.

~~~mermaid
flowchart TD
    A["Commit / merge"] --> B["Build và test tự động"]
    B --> C["Artifact bất biến, có truy vết"]
    C --> D["Deploy và kiểm chứng staging"]
    D --> E["Quality gate"]
    E --> F{"Gate đạt?"}
    F -- "Không" --> X["Dừng, điều tra và sửa"]
    F -- "Có" --> G{"Mô hình phát hành"}
    G -- "Continuous Delivery" --> H["Artifact sẵn sàng phát hành"]
    H --> I["Approval / lịch / quyết định release"]
    I --> J["Deploy production"]
    G -- "Continuous Deployment" --> K["Tự động rollout production"]
    J --> L["Post-deployment validation"]
    K --> L
    L --> M["Theo dõi và phục hồi theo policy"]
~~~

Cả hai mô hình đều cần một pipeline tạo ra bằng chứng rằng artifact đã được build và kiểm tra. Continuous Deployment chỉ có thể tự động ra quyết định production nếu các gate, ngưỡng, telemetry và hành động khi thất bại đã được định nghĩa đủ rõ.

Nếu một tổ chức chưa thể tự động quyết định production release, họ vẫn có thể đạt Continuous Delivery bằng cách bảo đảm phiên bản luôn sẵn sàng và bước approval chỉ quyết định thời điểm phát hành.

## 3. Phân biệt deploy và release

Một nguồn gây nhầm lẫn khác là dùng deploy và release như cùng một hành động.

- **Deploy** là đưa artifact hoặc phiên bản ứng dụng vào môi trường chạy, chẳng hạn production cluster.
- **Release** là làm cho năng lực hoặc thay đổi đó sẵn sàng với người dùng hoặc một nhóm người dùng cụ thể.

Một artifact có thể đã được deploy lên production nhưng feature vẫn tắt bằng feature flag. Khi bật flag, chức năng mới mới thực sự được release đến người dùng.

Điều này cho phép tách rủi ro kỹ thuật của việc triển khai khỏi quyết định kinh doanh về thời điểm cung cấp tính năng.

### 3.1. Feature flag giúp tách deploy khỏi release

Ví dụ, một thay đổi thêm luồng thanh toán mới có thể được deploy lên production nhưng chỉ bật cho nhân viên nội bộ hoặc 1% traffic. Nhóm có thể kiểm tra log, latency, error rate và hành vi nghiệp vụ trước khi mở rộng.

Feature flag cần có:

- Owner chịu trách nhiệm.
- Trạng thái mặc định an toàn.
- Phạm vi người dùng hoặc cohort rõ ràng.
- Cơ chế bật/tắt có audit.
- Thời hạn review và dọn flag cũ.
- Kiểm tra tương thích giữa code mới và code cũ.

Feature flag không thay thế kiểm thử. Một code path bị tắt vẫn cần được build và test. Flag cũng không tự bảo đảm rollback an toàn nếu database schema hoặc dữ liệu đã thay đổi.

### 3.2. Dark launch và progressive exposure

Dark launch có thể triển khai code mới và cho hệ thống xử lý một phần traffic hoặc dữ liệu mà chưa hiển thị kết quả cho người dùng. Progressive exposure mở dần tính năng theo cohort, tenant hoặc tỷ lệ traffic.

Các kỹ thuật này có thể được dùng trong cả Continuous Delivery lẫn Continuous Deployment. Chúng là cách kiểm soát rủi ro khi deploy/release, không phải tiêu chí định nghĩa hai mô hình.

## 4. Pipeline điển hình của Continuous Delivery

Một pipeline Continuous Delivery có thể tự động hóa gần như toàn bộ quy trình đến trạng thái production-ready, nhưng vẫn giữ một quyết định phát hành có chủ đích.

Luồng tham khảo:

1. Git event kích hoạt pipeline.
2. Kiểm tra source, lint, unit test và security scan.
3. Build artifact một lần và gắn commit SHA, version, digest.
4. Lưu artifact vào registry hoặc artifact repository.
5. Deploy cùng artifact lên integration/staging.
6. Chạy integration test, contract test, smoke test và post-deployment validation.
7. Đánh giá quality gate và tạo release evidence.
8. Đánh dấu phiên bản là eligible hoặc ready for production.
9. Chờ approval, change window hoặc quyết định release theo policy.
10. Promote chính artifact đã xác minh lên production.
11. Kiểm tra sức khỏe sau deploy và lưu release record.

Approval nên nằm trên luồng triển khai có kiểm soát. Người phê duyệt cần nhìn thấy phiên bản, commit, artifact digest, test result, scan result, change summary và rollback plan. Approval không nên chỉ là một nút bấm không có ngữ cảnh.

### 4.1. Ví dụ pipeline Continuous Delivery

YAML dưới đây là cấu hình khái niệm, không gắn với schema của một CI provider cụ thể:

~~~yaml
stages:
  - validate
  - build
  - verify
  - stage
  - release_ready
  - production

validate:
  run:
    - lint
    - unit_test
    - dependency_scan

build:
  needs: [validate]
  run:
    - build_once
    - create_immutable_artifact
    - record_commit_and_digest

verify:
  needs: [build]
  run:
    - integration_test
    - contract_test
    - artifact_scan

staging:
  needs: [verify]
  run:
    - deploy_artifact_to_staging
    - smoke_test
    - post_deployment_checks

release_ready:
  needs: [staging]
  run:
    - publish_release_evidence
    - mark_artifact_production_ready

production:
  needs: [release_ready]
  approval: required
  run:
    - promote_same_artifact
    - verify_production
~~~

Trong mô hình này, build, test và staging deployment đều tự động. Approval chỉ quyết định có promote artifact đã kiểm chứng lên production hay không. Không nên build lại sau approval vì artifact mới có thể khác artifact đã được xác minh.

## 5. Pipeline điển hình của Continuous Deployment

Continuous Deployment sử dụng cùng nền tảng build và verification, nhưng production rollout được điều khiển bằng policy tự động.

Luồng tham khảo:

1. Git event kích hoạt pipeline.
2. Build, test, scan và tạo artifact bất biến.
3. Deploy lên môi trường kiểm chứng.
4. Chạy smoke test và kiểm tra post-deployment.
5. Đưa candidate vào canary với tỷ lệ traffic nhỏ.
6. So sánh error rate, latency, saturation và business metrics với baseline/control.
7. Nếu đủ dữ liệu và đạt gate, tăng tỷ lệ traffic.
8. Nếu vi phạm ngưỡng, dừng rollout và thực hiện hành động đã định.
9. Khi đạt toàn bộ điều kiện, hoàn tất production rollout.
10. Ghi nhận release marker, artifact digest và kết quả validation.

### 5.1. Ví dụ policy Continuous Deployment

~~~yaml
deployment:
  mode: continuous
  artifact:
    immutable: true
    require_digest: true

  pre_production:
    required:
      - unit_tests
      - integration_tests
      - security_scan
      - staging_smoke_test

  production:
    strategy: canary
    stages:
      - traffic_percent: 5
        observation_window: 5m
      - traffic_percent: 25
        observation_window: 10m
      - traffic_percent: 50
        observation_window: 10m
      - traffic_percent: 100

    gates:
      require_minimum_samples: true
      max_error_rate: service_policy
      max_latency_regression: service_policy
      business_success_rate: service_policy

    on_inconclusive: hold
    on_failure: stop_and_apply_recovery_policy
~~~

Các ngưỡng trong ví dụ phải được định nghĩa theo SLO và đặc điểm từng dịch vụ. Trạng thái thiếu dữ liệu không được tự động coi là pass. Hệ thống có thể giữ nguyên tỷ lệ traffic, thử lại phép đo hoặc yêu cầu điều tra theo policy.

Continuous Deployment không có nghĩa production phải nhận 100% traffic ngay sau một lần deploy. Canary và progressive rollout vẫn là triển khai tự động; chúng chỉ chia quá trình thành các bước có điều kiện.

## 6. Approval không đồng nghĩa với kiểm soát chất lượng

Một nhầm lẫn thường gặp là cho rằng Continuous Delivery có approval nên an toàn hơn Continuous Deployment. Approval chỉ có giá trị khi người duyệt nhận được bằng chứng và có tiêu chí quyết định rõ.

Một người bấm approve không thể thay thế:

- Automated test.
- Security và compliance scan.
- Artifact provenance.
- Deployment validation.
- Monitoring và alert.
- Rollback hoặc recovery plan.
- Quy trình quản lý thay đổi có truy vết.

Ngược lại, Continuous Deployment không loại bỏ trách nhiệm quản trị. Các kiểm soát có thể được mã hóa thành policy, required checks, quyền triển khai, audit log và guardrail tự động.

### 6.1. Khi nào approval có ý nghĩa?

Approval có thể cần thiết khi:

- Có cửa sổ thay đổi được quy định.
- Release cần phối hợp nhiều hệ thống hoặc nhóm vận hành.
- Có yêu cầu kiểm soát pháp lý, hợp đồng hoặc phân tách nhiệm vụ.
- Thay đổi tác động lớn hoặc có rủi ro chưa thể tự động đánh giá.
- Cần quyết định kinh doanh về thời điểm bật tính năng.

Approval nên gắn với release candidate cụ thể. Nếu commit hoặc artifact digest thay đổi sau khi phê duyệt, approval cũ không nên tự động áp dụng cho artifact mới.

### 6.2. Khi nào nên tự động hóa quyết định?

Có thể tự động hóa production deployment khi:

- Quality gate có độ tin cậy và được duy trì.
- Artifact và cấu hình có thể truy vết.
- Rollout có thể giới hạn blast radius.
- Telemetry đủ để phát hiện suy giảm.
- Hệ thống có hành động dừng/rollback hoặc forward recovery rõ ràng.
- Thay đổi dữ liệu và schema có chiến lược tương thích.
- Quyền production được giới hạn theo workload identity và policy.

Nếu một điều kiện quan trọng chưa có, hãy cải thiện điều kiện đó trước khi tự động hóa quyết định có rủi ro cao.

## 7. Quality gate trong cả hai mô hình

Quality gate là điều kiện để pipeline được tiếp tục. Cả Continuous Delivery và Continuous Deployment đều cần gate; khác biệt là gate cuối có thể dẫn đến trạng thái production-ready để chờ quyết định, hoặc tự động mở đường cho production rollout.

Các nhóm gate thường gặp:

| Nhóm | Ví dụ kiểm tra |
|---|---|
| Source quality | Lint, format, static analysis |
| Functional | Unit, integration, contract và end-to-end tests |
| Security | Dependency scan, secret scan, image scan, SAST |
| Artifact | Digest, signature, provenance và metadata |
| Compatibility | API/schema compatibility, database migration |
| Operational | Readiness, health, smoke test, capacity |
| Post-deployment | Error rate, latency, saturation, business metrics |

Gate cần có trạng thái rõ ràng:

- **PASS**: đủ dữ liệu và mọi điều kiện bắt buộc đạt.
- **FAIL**: có điều kiện vi phạm.
- **INCONCLUSIVE**: chưa đủ dữ liệu hoặc hệ thống quan sát không đáng tin.

Không biến **INCONCLUSIVE** thành **PASS** chỉ để pipeline tiếp tục. Với Continuous Deployment, trạng thái này thường phải giữ rollout, giới hạn traffic hoặc dừng theo policy.

## 8. Progressive delivery, canary và blue-green

Progressive delivery là cách phát hành theo từng bước, dùng tín hiệu thực tế để quyết định mở rộng. Nó có thể hỗ trợ cả hai mô hình.

### 8.1. Canary

Canary đưa một tỷ lệ nhỏ traffic đến phiên bản mới trước. Hệ thống so sánh candidate với control và chỉ tăng traffic khi các guardrail đạt.

Canary đặc biệt hữu ích cho Continuous Deployment vì cho phép tự động quyết định theo telemetry. Tuy nhiên, canary chỉ hiệu quả khi traffic đủ đại diện, metric được phân tách theo version và cửa sổ quan sát phù hợp.

### 8.2. Blue-green

Blue-green duy trì hai môi trường hoặc hai tập workload. Phiên bản mới được deploy vào green, kiểm tra xong rồi chuyển traffic từ blue sang green.

Blue-green có thể được dùng trong Continuous Delivery với approval trước khi chuyển traffic, hoặc Continuous Deployment với điều kiện chuyển traffic hoàn toàn tự động.

### 8.3. Feature flag

Feature flag tách việc deploy code khỏi việc bật tính năng. Nó có thể cho phép code được deploy tự động nhưng release cho người dùng được điều khiển riêng.

Cần nhớ rằng feature flag tạo thêm trạng thái cần quản lý. Flag cũ, tổ hợp flag không được test hoặc trạng thái mặc định sai có thể tạo lỗi khó tái hiện.

## 9. Rollback và phục hồi không phải đặc quyền của một mô hình

Cả hai mô hình đều cần khả năng phục hồi. Continuous Deployment làm nhu cầu tự động phát hiện và xử lý nhanh trở nên rõ ràng hơn, nhưng Continuous Delivery cũng cần rollback hoặc forward fix đáng tin cậy.

Trước khi rollout, cần xác định:

- Artifact phiên bản trước còn sẵn sàng không?
- Cấu hình trước có thể khôi phục không?
- Database schema có tương thích ngược không?
- Event/message contract có tương thích với consumer cũ không?
- Feature flag có thể tắt an toàn không?
- Traffic có thể chuyển lại mà không mất dữ liệu không?
- Sau rollback có readiness, smoke và business validation không?

### 9.1. Rollback và roll-forward

Rollback quay lại phiên bản trước. Roll-forward triển khai một bản sửa mới để khắc phục lỗi. Với migration dữ liệu không thể đảo ngược, roll-forward có thể an toàn hơn rollback code cũ.

Không coi lệnh rollback trả mã 0 là bằng chứng hệ thống đã phục hồi. Cần xác minh version/digest đang chạy, traffic routing, health và business metrics.

### 9.2. Automatic recovery trong Continuous Deployment

Policy có thể tự động:

- Dừng tăng traffic khi gate fail.
- Chuyển traffic về stable version.
- Tắt feature flag có vấn đề.
- Giữ rollout khi thiếu dữ liệu.
- Tạo incident hoặc yêu cầu người vận hành khi không thể phục hồi an toàn.

Tự động recovery phải có giới hạn và audit. Một vòng rollback/redeploy lặp vô hạn có thể gây thêm gián đoạn. Nên có retry budget, giới hạn số lần tự phục hồi và trạng thái cuối rõ ràng.

## 10. Quản trị thay đổi và phân quyền

Continuous Delivery thường có một điểm quyết định production rõ ràng. Continuous Deployment chuyển nhiều quyết định thường ngày sang policy tự động, vì vậy quyền và trách nhiệm cần được thiết kế ngay trong pipeline.

Các nguyên tắc:

- Dùng workload identity hoặc short-lived credential cho pipeline.
- Tách quyền build, publish artifact và deploy production.
- Không cấp quyền production cho job chạy từ pull request không tin cậy.
- Bảo vệ policy required checks và deployment environment.
- Ghi audit cho approval, policy decision và deployment action.
- Gắn commit, artifact digest, config revision và release ID.
- Phân biệt người thay đổi source, người quản lý policy và quyền vận hành ngoại lệ.
- Có quy trình break-glass được kiểm soát và ghi nhận.

Approval thủ công không thay thế phân quyền. Ngay cả khi có approval, pipeline vẫn phải kiểm tra người duyệt có quyền phù hợp và approval áp dụng đúng artifact.

## 11. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
|---|---|
| Continuous Delivery và Continuous Deployment là một | Delivery giữ phần mềm luôn sẵn sàng phát hành; Deployment tự động đưa thay đổi đạt gate lên production |
| Continuous Delivery luôn phải deploy production thủ công | Production có thể deploy tự động sau approval hoặc lịch phát hành; điểm quyết định vẫn do người/policy bên ngoài tự động hóa hoàn toàn |
| Continuous Deployment là deploy mọi commit bất kể kết quả | Chỉ thay đổi đạt gate mới được tự động rollout |
| Có approval thì pipeline đã an toàn | Approval không thay thế test, scan, telemetry và recovery |
| Không có approval nghĩa là không có governance | Governance có thể được thực thi bằng policy, quyền và audit tự động |
| Deploy production đồng nghĩa người dùng đã thấy tính năng | Feature flag và progressive exposure có thể giữ tính năng tắt hoặc giới hạn cohort |
| Canary chỉ dành cho Continuous Deployment | Canary cũng có thể là bước kiểm chứng trước approval trong Continuous Delivery |
| Continuous Deployment không cần con người | Con người vẫn thiết kế policy, xử lý ngoại lệ, điều tra incident và quyết định thay đổi rủi ro cao |
| Rollback luôn đơn giản | Schema, dữ liệu và side effect có thể khiến rollback không an toàn |
| Tự động hóa nhiều hơn luôn tốt hơn | Chỉ tự động hóa quyết định khi có dữ liệu, guardrail và recovery phù hợp |

Một cách kiểm tra nhanh: nếu production release thông thường vẫn chờ một người phê duyệt từng lần, quy trình đó là Continuous Delivery. Nếu thay đổi đạt các gate tự động được triển khai production theo policy mà không chờ approval từng lần, đó là Continuous Deployment.

## 12. Chọn mô hình phù hợp với bối cảnh

Không cần mọi dịch vụ trong một tổ chức dùng cùng một mô hình. Mức tự động hóa có thể khác theo rủi ro, yêu cầu pháp lý, kiến trúc và năng lực vận hành.

| Bối cảnh | Mô hình thường phù hợp | Lý do |
|---|---|---|
| Sản phẩm web có test và telemetry trưởng thành | Continuous Deployment | Có thể phát hành thay đổi nhỏ thường xuyên với guardrail tự động |
| Hệ thống có change window cố định | Continuous Delivery | Artifact luôn sẵn sàng nhưng production cần đúng lịch |
| Dịch vụ tài chính hoặc hệ thống có approval bắt buộc | Continuous Delivery với policy/approval | Tách chuẩn bị kỹ thuật khỏi quyết định kiểm soát |
| Internal service có blast radius nhỏ | Có thể tiến tới Continuous Deployment | Dễ thử nghiệm rollout và recovery tự động |
| Hệ thống legacy thiếu test tự động | Bắt đầu từ Continuous Delivery | Cần cải thiện độ tin cậy trước khi tự động hóa production |
| Thay đổi schema hoặc migration rủi ro cao | Continuous Delivery hoặc deployment có gate chuyên biệt | Cần kiểm tra tương thích và kế hoạch dữ liệu |

### 12.1. Đánh giá mức sẵn sàng

Trước khi chuyển từ Continuous Delivery sang Continuous Deployment, hãy đánh giá:

- Test tự động có phát hiện regression quan trọng không?
- Build có tạo artifact bất biến và truy vết được không?
- Có thể deploy cùng artifact qua nhiều môi trường không?
- Có health check, smoke test và business validation không?
- Telemetry có phân biệt version/canary và đủ mẫu không?
- Có SLO, guardrail và ngưỡng dừng rollout không?
- Có rollback/roll-forward đã diễn tập không?
- Database và API có chiến lược tương thích khi nhiều phiên bản cùng chạy không?
- Policy production và quyền của pipeline có được bảo vệ không?
- Incident response có thể xử lý các trường hợp policy tự động không giải quyết được không?

Nếu thiếu nhiều điều kiện, hãy củng cố Continuous Delivery trước. Trạng thái production-ready có giá trị ngay cả khi tổ chức chưa tự động triển khai mọi thay đổi.

## 13. Các chỉ số cần theo dõi

Để đánh giá hiệu quả của hai mô hình, cần theo dõi cả tốc độ phát hành và chất lượng vận hành.

| Chỉ số | Ý nghĩa |
|---|---|
| Deployment frequency | Tần suất triển khai production |
| Lead time for changes | Thời gian từ commit đến production |
| Change failure rate | Tỷ lệ triển khai gây suy giảm hoặc cần xử lý |
| Time to restore service | Thời gian khôi phục dịch vụ sau sự cố |
| Release-ready age | Thời gian artifact đã sẵn sàng nhưng chưa được phát hành |
| Approval wait time | Thời gian chờ quyết định release trong Continuous Delivery |
| Automated rollout success | Tỷ lệ rollout tự động hoàn tất theo policy |
| Rollback/roll-forward rate | Tần suất phải phục hồi sau release |
| Gate failure rate | Tỷ lệ thay đổi bị chặn ở từng quality gate |

Continuous Deployment thường làm tăng deployment frequency, nhưng deployment frequency cao tự nó không chứng minh chất lượng tốt. Cần đọc cùng change failure rate, thời gian khôi phục và tác động nghiệp vụ.

Trong Continuous Delivery, release-ready age hoặc approval wait time có thể cho thấy pipeline đã chuẩn bị nhanh nhưng tổ chức mất nhiều thời gian ở quyết định phát hành. Đây có thể là lựa chọn có chủ đích hoặc một điểm nghẽn cần cải thiện.

## 14. Lộ trình chuyển từ Continuous Delivery sang Continuous Deployment

Chuyển đổi nên diễn ra theo năng lực, không chỉ bằng cách xóa approval step.

1. Chuẩn hóa build và test để mọi commit có kết quả đáng tin.
2. Tạo artifact bất biến và lưu digest, provenance, commit SHA.
3. Tự động deploy artifact lên staging và kiểm chứng sau deploy.
4. Chuẩn hóa quality gate, SLO và business guardrail.
5. Diễn tập rollback/roll-forward và xác minh dữ liệu sau phục hồi.
6. Áp dụng feature flag để tách deploy khỏi release khi phù hợp.
7. Thử canary với một dịch vụ có blast radius nhỏ.
8. Tự động hóa quyết định tăng traffic khi đủ mẫu và đạt gate.
9. Đặt policy hold/stop cho dữ liệu thiếu hoặc tín hiệu bất thường.
10. Mở rộng sang dịch vụ khác sau khi xem xét change failure rate và thời gian phục hồi.
11. Giữ approval cho thay đổi ngoại lệ hoặc rủi ro cao theo policy.
12. Đánh giá định kỳ false positive, false negative và hiệu quả của gate.

Có thể giữ Continuous Delivery cho một số hệ thống và dùng Continuous Deployment cho hệ thống khác. Mục tiêu là chọn mức tự động hóa phù hợp với rủi ro và năng lực vận hành của từng dịch vụ.

## 15. Tình huống mẫu: một commit, hai cách phát hành

Giả sử nhóm phát triển thêm API xem lịch sử đơn hàng.

**Theo Continuous Delivery:**

1. Commit được merge và pipeline chạy lint, unit test, integration test và security scan.
2. Artifact được build một lần, gắn digest và lưu vào registry.
3. Artifact được deploy lên staging, chạy smoke test và contract test.
4. Pipeline đánh dấu release candidate là production-ready.
5. Product/operations chọn thời điểm release và approval theo change policy.
6. Pipeline promote đúng artifact digest lên production.
7. Hệ thống xác minh health và lưu release record.

**Theo Continuous Deployment:**

1. Commit được merge và pipeline chạy cùng bộ kiểm tra bắt buộc.
2. Artifact được build một lần và lưu với digest.
3. Artifact được deploy lên staging và xác minh.
4. Production rollout bắt đầu ở canary 5%.
5. Hệ thống so sánh error rate, p95 latency và business signals với control.
6. Nếu đủ mẫu và đạt gate, traffic tăng qua 25%, 50% rồi 100%.
7. Nếu lỗi vượt ngưỡng, rollout dừng và recovery policy chuyển traffic về phiên bản ổn định.
8. Nếu toàn bộ gate đạt, release được ghi nhận tự động.

Hai cách có thể dùng cùng artifact, cùng test và cùng chiến lược canary. Khác biệt là Continuous Delivery giữ một quyết định phát hành production; Continuous Deployment để policy tự động đưa thay đổi đạt gate lên production.

## 16. Lộ trình thực hành

Có thể thực hành trên một dịch vụ mẫu theo các bước:

1. **Mô tả quy trình hiện tại:** liệt kê trigger, build, test, artifact, staging và production decision.
2. **Phân loại mô hình:** xác định production release đang cần approval từng lần hay tự động theo policy.
3. **Tách deploy và release:** thêm một feature flag đơn giản trong môi trường thử nghiệm.
4. **Tạo pipeline Delivery:** tự động build, test, deploy staging, lưu artifact và chờ approval production.
5. **Kiểm tra artifact identity:** bảo đảm artifact được promote có cùng digest với artifact đã kiểm thử.
6. **Định nghĩa gate:** chọn test, scan, smoke, SLO và business guardrail.
7. **Diễn tập approval:** xác minh approval gắn với đúng release candidate và có audit.
8. **Diễn tập canary:** triển khai candidate cho một phần traffic và so sánh với control.
9. **Mô phỏng gate fail:** xác nhận pipeline dừng hoặc giữ rollout theo policy.
10. **Diễn tập phục hồi:** rollback hoặc roll-forward, sau đó chạy readiness và business validation.
11. **Tự động hóa quyết định:** chỉ trong môi trường thử nghiệm, bỏ approval thường lệ khi mọi điều kiện tự động đã được xác minh.
12. **So sánh hai mô hình:** ghi deployment frequency, lead time, approval wait, change failure rate và time to restore.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Giải thích đúng Continuous Delivery và Continuous Deployment.
- Xác định được điểm quyết định production trong mỗi mô hình.
- Phân biệt deploy với release và giải thích vai trò feature flag.
- Thiết kế được pipeline Continuous Delivery có artifact bất biến và approval có bằng chứng.
- Thiết kế được production rollout tự động theo quality gate.
- Biết dùng canary/progressive delivery trong cả hai mô hình.
- Xử lý trạng thái pass, fail và inconclusive.
- Có phương án rollback/roll-forward và xác minh sau phục hồi.
- Đánh giá được mức sẵn sàng trước khi bỏ approval thường lệ.
- Chọn mô hình theo rủi ro và yêu cầu vận hành.
- Đo được hiệu quả bằng deployment frequency, lead time, change failure rate và time to restore.

## Kết luận

Continuous Delivery và Continuous Deployment cùng hướng đến việc đưa thay đổi đến người dùng với vòng phản hồi ngắn và chất lượng có thể kiểm soát. Continuous Delivery bảo đảm mọi thay đổi luôn sẵn sàng phát hành; production release có thể chờ approval, lịch hoặc quyết định theo policy. Continuous Deployment tự động đưa mọi thay đổi vượt qua gate lên production.

Hai mô hình có thể dùng chung build, test, artifact, staging, canary, feature flag và monitoring. Khác biệt nằm ở quyết định production release, không nằm ở việc pipeline có tự động hóa hay không. Muốn tiến tới Continuous Deployment, tổ chức cần có artifact truy vết được, quality gate đáng tin, telemetry đủ dữ liệu, rollout giới hạn blast radius và khả năng phục hồi đã được diễn tập. Chọn đúng mô hình giúp cân bằng tốc độ, rủi ro và yêu cầu quản trị của từng dịch vụ.

