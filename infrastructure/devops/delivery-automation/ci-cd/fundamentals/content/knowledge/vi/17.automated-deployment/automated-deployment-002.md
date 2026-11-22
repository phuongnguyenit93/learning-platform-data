# Tự động hóa cùng một quy trình triển khai cho các môi trường

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao dev, staging và production nên dùng cùng một quy trình triển khai có kiểm soát.
- Phân biệt artifact ứng dụng, cấu hình môi trường và hạ tầng đích.
- Thiết kế luồng build một lần rồi promote cùng artifact qua các môi trường.
- Tổ chức cấu hình theo môi trường bằng schema và overlay, đồng thời quản lý secret riêng.
- Tái sử dụng pipeline bằng template hoặc reusable workflow mà vẫn giữ được khả năng kiểm tra và tùy chỉnh.
- Áp dụng gate, quyền và phê duyệt phù hợp với từng môi trường.
- Kiểm soát thứ tự triển khai, concurrency, xác minh sau deploy và rollback.
- Truy vết artifact, config revision và kết quả triển khai xuyên suốt vòng đời phát hành.

## 1. Vì sao cần cùng một quy trình triển khai?

Nhiều đội ngũ bắt đầu với cách triển khai khác nhau cho từng môi trường. Developer chạy một script trên máy cá nhân để deploy dev; staging được cập nhật qua một workflow CI; production lại do người vận hành chạy lệnh hoặc chỉnh cấu hình thủ công.

Cách làm này có thể hoạt động trong giai đoạn đầu, nhưng càng nhiều môi trường thì khác biệt càng dễ tích tụ:

- Staging chạy một tập lệnh khác production.
- Thứ tự migration, restart hoặc health check không giống nhau.
- Một bước cấu hình chỉ được thực hiện thủ công ở production.
- Quyền và secret được cấp theo cách không nhất quán.
- Không thể biết staging đã kiểm thử đúng artifact nào.
- Khi có sự cố, rollback ở mỗi môi trường đòi hỏi thao tác khác nhau.

Nếu một lỗi chỉ xuất hiện ở production, đội ngũ khó xác định nguyên nhân đến từ mã nguồn, cấu hình, hạ tầng hay khác biệt quy trình triển khai.

Mục tiêu của tự động hóa đa môi trường là dùng **cùng một quy trình triển khai, cùng thứ tự bước và cùng hợp đồng đầu vào/đầu ra**, trong khi các giá trị và chính sách riêng của môi trường được khai báo rõ ràng.

Cùng quy trình không có nghĩa mọi môi trường phải có cùng hostname, credential, replica count hoặc quyền. Dev, staging và production có thể khác nhau về cấu hình, dữ liệu, tài nguyên và gate. Điều cần thống nhất là cách pipeline xác định artifact, kiểm tra điều kiện, áp dụng cấu hình, triển khai, xác minh và ghi nhận kết quả.

Một nguyên tắc quan trọng:

> Build một lần, kiểm tra và promote cùng artifact qua các môi trường bằng một quy trình có thể tái sử dụng; chỉ thay đổi cấu hình và chính sách môi trường theo cách được quản lý.

## 2. Xác định đơn vị được triển khai

Trước khi thiết kế workflow, cần thống nhất pipeline đang triển khai những thành phần nào. Một release có thể gồm nhiều phần:

| Thành phần | Ví dụ | Cách nhận diện |
|---|---|---|
| Application artifact | JAR, container image, package | Digest hoặc artifact ID bất biến |
| Deployment configuration | Helm values, manifest, task definition | Config revision hoặc fingerprint |
| Infrastructure | Cluster, database, network, service account | IaC revision và trạng thái hạ tầng |
| Database migration | Migration scripts hoặc migration bundle | Migration version |
| Runtime configuration | Feature flags, timeout, endpoint | Config service revision |
| Secret | API key, password, certificate | Secret reference và version metadata |

Không nên gom mọi thành phần vào một chuỗi version duy nhất nếu chúng có vòng đời khác nhau. Ví dụ, image có thể giữ nguyên trong khi cấu hình timeout được điều chỉnh. Ngược lại, một thay đổi schema database có thể yêu cầu phối hợp với nhiều phiên bản ứng dụng.

Một deployment request nên xác định tối thiểu:

- Artifact nào sẽ được triển khai.
- Môi trường đích.
- Config revision hoặc cách resolve cấu hình.
- Migration hoặc hạ tầng liên quan nếu có.
- Chiến lược triển khai.
- Các gate cần đạt.
- Danh tính thực hiện và quyền được cấp.
- Bằng chứng xác minh sau triển khai.

Đơn vị triển khai rõ ràng giúp pipeline có thể chạy lại, so sánh và truy vết mà không phụ thuộc vào thao tác thủ công của từng người.

## 3. Build một lần và promote cùng artifact

Một sai lầm thường gặp là build lại ứng dụng cho từng môi trường:

- Build image A cho dev.
- Build image B cho staging.
- Build image C cho production.

Dù cả ba lần build dùng cùng commit, nội dung artifact vẫn có thể khác do dependency, toolchain, thời điểm build, build argument hoặc dữ liệu môi trường. Khi staging đã kiểm thử image B nhưng production nhận image C, kết quả kiểm thử không còn chứng minh trực tiếp cho artifact được phát hành.

Mô hình nên dùng:

1. Build artifact từ commit đã xác định.
2. Tạo digest và metadata.
3. Chạy kiểm tra cần thiết.
4. Publish artifact vào registry tin cậy.
5. Triển khai đúng digest lên dev hoặc môi trường kiểm thử.
6. Sau khi gate đạt, promote cùng digest lên staging.
7. Sau phê duyệt và kiểm tra chính sách, promote cùng digest lên production.

~~~mermaid
flowchart LR
    A["Commit đã review"] --> B["Build một lần"]
    B --> C["Artifact + digest"]
    C --> D["Deploy dev"]
    D --> E{"Dev verify đạt?"}
    E -- "Có" --> F["Deploy staging"]
    E -- "Không" --> X["Dừng và điều tra"]
    F --> G{"Staging verify + gate đạt?"}
    G -- "Có" --> H["Deploy production"]
    G -- "Không" --> X
    H --> I["Post-deploy verify"]
~~~

Trong thực tế, verify là điều kiện chuyển tiếp giữa các môi trường, không phải một bước trang trí sau deploy. Mỗi lần promote phải xác định artifact digest và bằng chứng đã gắn với digest đó.

Không dùng tag mutable như **latest**, tên branch hoặc alias làm định danh cuối cùng cho production. Tag có thể giúp tìm artifact, nhưng pipeline nên resolve thành digest rồi sử dụng digest đó xuyên suốt quá trình promote.

Cũng không nên build lại chỉ để thay endpoint hoặc credential. Các giá trị theo môi trường nên được truyền qua cấu hình triển khai hoặc runtime configuration, tùy kiến trúc. Nếu một giá trị thực sự được đóng gói vào artifact ở build time, cần xác định rõ vì sao và chấp nhận rằng thay đổi giá trị đó sẽ cần artifact mới.

## 4. Cùng quy trình nhưng cấu hình riêng theo môi trường

Mỗi môi trường có thể có cấu hình riêng:

| Thuộc tính | Dev | Staging | Production |
|---|---|---|---|
| Mục đích | Phản hồi nhanh cho phát triển | Xác minh gần production | Phục vụ người dùng thật |
| Database | Dữ liệu phát triển | Dữ liệu test được quản lý | Dữ liệu thật, có backup và kiểm soát |
| Endpoint ngoài | Mock hoặc sandbox | Sandbox hoặc hệ thống tích hợp | Endpoint production |
| Replica | Ít, ưu tiên chi phí | Gần cấu hình production | Theo tải và SLO |
| Secret | Credential dev | Credential staging | Credential riêng, quyền tối thiểu |
| Approval | Thường tự động | Có thể cần gate | Theo release policy |
| Rollout | Nhanh, có thể reset | Kiểm soát chặt hơn | Canary, rolling hoặc blue-green theo rủi ro |

Cấu hình nên được tổ chức theo một hợp đồng chung. Ví dụ, cả ba môi trường đều có database URL, request timeout, replica count và feature flags, nhưng giá trị khác nhau.

~~~text
deploy-config/
├── base/
│   └── service.yml
├── environments/
│   ├── dev/
│   │   └── values.yml
│   ├── staging/
│   │   └── values.yml
│   └── production/
│       └── values.yml
└── schema/
    └── deployment-config.schema.json
~~~

Thư mục base chứa cấu trúc và mặc định dùng chung. Các overlay chỉ khai báo khác biệt có chủ đích. Schema xác định trường nào bắt buộc, kiểu dữ liệu, miền giá trị và quy tắc hợp lệ.

Pipeline cần resolve cấu hình cuối cùng cho môi trường đích, validate và lưu revision hoặc fingerprint. Không nên giả định file overlay riêng lẻ là cấu hình thực tế nếu runtime còn nhận giá trị từ environment variables, config service hoặc secret manager.

Secret không nên nằm trong overlay dưới dạng plaintext. Cấu hình có thể chứa secret reference; pipeline hoặc workload identity lấy giá trị thực từ secret manager theo quyền được cấp.

## 5. Thiết kế deployment contract dùng chung

Một deployment contract mô tả đầu vào và kết quả mà quy trình triển khai hỗ trợ. Khi contract rõ, cùng một workflow có thể dùng cho nhiều môi trường mà không cần sao chép toàn bộ logic.

Ví dụ đầu vào:

| Trường | Ý nghĩa | Quy tắc |
|---|---|---|
| artifact_digest | Artifact cần triển khai | Bắt buộc, bất biến, tồn tại trong registry tin cậy |
| target_environment | Môi trường đích | Chỉ nhận môi trường trong allowlist |
| config_revision | Cấu hình được áp dụng | Revision hoặc fingerprint đã resolve |
| release_id | Định danh lần phát hành | Duy nhất, dùng để truy vết |
| deployment_strategy | Rolling, canary hoặc blue-green | Phải được môi trường hỗ trợ |
| change_reference | Ticket hoặc change record | Bắt buộc theo policy |
| dry_run | Xem trước thay đổi | Có thể bật mặc định cho thao tác rủi ro |

Kết quả triển khai nên có:

- Deployment ID và release ID.
- Artifact digest thực tế.
- Config revision thực tế.
- Environment ID.
- Thời điểm bắt đầu và hoàn tất.
- Kết quả từng gate và bước xác minh.
- Phiên bản trước và sau triển khai.
- Người hoặc workload thực hiện.
- Trạng thái cuối và liên kết log.

Contract giúp workflow có thể được gọi từ sự kiện tự động hoặc manual trigger mà vẫn dùng chung cách xác thực và ghi nhận.

## 6. Cấu trúc một quy trình triển khai đa môi trường

Một workflow có thể được chia thành các giai đoạn logic:

1. **Preflight:** xác minh request, quyền, môi trường và trạng thái hiện tại.
2. **Resolve:** lấy artifact theo digest, resolve cấu hình và dependency cần thiết.
3. **Validate:** kiểm tra schema, policy, tương thích và bằng chứng.
4. **Acquire:** lấy deployment lock hoặc quyền điều phối tài nguyên.
5. **Deploy:** áp dụng artifact và cấu hình theo chiến lược của môi trường.
6. **Verify:** kiểm tra phiên bản thực tế, health, smoke test và tín hiệu vận hành.
7. **Record:** lưu deployment evidence, release metadata và kết quả.
8. **Recover:** dừng rollout hoặc khôi phục khi điều kiện không đạt.

~~~mermaid
flowchart TD
    A["Deployment request"] --> B["Preflight: actor, target, state"]
    B --> C["Resolve artifact by digest"]
    C --> D["Resolve environment configuration"]
    D --> E["Validate policy and evidence"]
    E --> F{"Gate passed?"}
    F -- "No" --> X["Block and record reason"]
    F -- "Yes" --> G["Acquire environment lock"]
    G --> H["Deploy using environment strategy"]
    H --> I["Verify actual artifact and config"]
    I --> J{"Healthy?"}
    J -- "No" --> K["Stop rollout / recover"]
    J -- "Yes" --> L["Record release evidence"]
~~~

Các stage này không bắt buộc phải là các job riêng. Có thể dùng một job hoặc nhiều job tùy nền tảng. Điều quan trọng là ranh giới quyền, điều kiện chuyển bước và đầu ra có thể quan sát.

## 7. Tái sử dụng workflow thay vì sao chép cấu hình

Khi có nhiều môi trường hoặc nhiều dịch vụ, sao chép toàn bộ workflow rồi sửa vài dòng sẽ tạo ra drift. Sau một thời gian, dev có bước kiểm tra mới nhưng production chưa có; một workflow được vá lỗi còn các bản sao khác vẫn lỗi.

Có ba cách tái sử dụng phổ biến:

**Reusable workflow:** đóng gói một quy trình hoặc nhóm job có thể được gọi từ workflow khác. Phù hợp khi nhiều repository cần dùng cùng một chuỗi bước và hợp đồng đầu vào.

**Pipeline template:** cung cấp cấu trúc chuẩn để các dự án tạo workflow mới. Phù hợp khi tổ chức muốn thống nhất cách triển khai nhưng cho phép repository tùy chỉnh có kiểm soát.

**Composite action hoặc task module:** đóng gói một nhóm thao tác nhỏ như resolve artifact, validate manifest hoặc publish evidence. Phù hợp khi cần tái sử dụng logic ở cấp bước.

Nên tách phần dùng chung và phần theo môi trường:

- Logic chung: validate request, resolve digest, kiểm tra provenance, ghi audit.
- Cấu hình môi trường: endpoint, namespace, replica, resource quota.
- Policy môi trường: approval, change window, rollout threshold.
- Adapter triển khai: cách gọi Kubernetes, VM, serverless hoặc nền tảng khác.

Không nên tạo một template khổng lồ với hàng chục tham số không có ý nghĩa. Một template tốt có contract nhỏ, mặc định an toàn, version rõ ràng và tài liệu về extension point.

Khi cập nhật template, cần có quy trình nâng version. Không nên âm thầm thay đổi hành vi của mọi pipeline đang dùng một tham chiếu mutable. Với môi trường production, nên pin version template hoặc commit SHA và nâng cấp qua review.

## 8. Cấu hình theo môi trường không nên làm thay đổi logic bảo mật

Một workflow dùng chung có thể nhận tên môi trường làm đầu vào, nhưng không nên để người gọi tự chọn tùy ý rồi nhận quyền triển khai tương ứng.

Cần phân biệt:

- **Target selection:** yêu cầu triển khai đến môi trường nào.
- **Authorization:** actor hoặc workload có được phép thực hiện không.
- **Approval:** có cần người có thẩm quyền cho phép không.
- **Execution identity:** pipeline dùng danh tính nào để thay đổi tài nguyên.

Ví dụ developer có thể yêu cầu triển khai staging, nhưng không có quyền truy cập credential production. Production job chỉ nhận identity sau khi các gate và approval tương ứng đạt.

Các quy tắc nên áp dụng:

- Môi trường là giá trị enum hoặc ID được cấu hình, không phải URL tùy ý.
- Quyền được xác minh phía server hoặc nền tảng, không dựa vào input do người dùng tự khai.
- Secret được scope theo môi trường và job.
- Job production có identity riêng và quyền tối thiểu.
- Approval gắn với artifact, config revision và target cụ thể.
- Không cấp secret production cho job chạy mã từ pull request không tin cậy.

Một workflow tái sử dụng không nên trở thành cách để người có quyền thấp gọi gián tiếp quyền cao mà không qua policy.

## 9. Gate khác nhau nhưng quy trình vẫn thống nhất

Các môi trường có thể yêu cầu mức kiểm soát khác nhau. Dev có thể deploy tự động sau khi build; staging cần integration test; production cần phê duyệt, change window và theo dõi rollout.

Điều này không phá vỡ tính thống nhất của workflow. Cùng một quy trình có thể đọc policy theo môi trường và áp dụng gate phù hợp.

| Gate | Dev | Staging | Production |
|---|---|---|---|
| Artifact digest hợp lệ | Bắt buộc | Bắt buộc | Bắt buộc |
| Build/test evidence | Bắt buộc | Bắt buộc | Bắt buộc |
| Integration/smoke test | Tùy loại dịch vụ | Thường bắt buộc | Post-deploy hoặc pre-release theo thiết kế |
| Security policy | Baseline | Đầy đủ theo release policy | Đầy đủ và freshness phù hợp |
| Manual approval | Thường không | Theo chính sách | Theo chính sách/rủi ro |
| Change window | Không thường cần | Có thể cần | Có thể bắt buộc |
| Rollout observation | Health cơ bản | Kiểm tra tích hợp | Theo dõi tăng cường và ngưỡng dừng |

Không nên hard-code mọi khác biệt bằng nhiều nhánh logic khó hiểu. Có thể mô tả policy trong cấu hình có version, nhưng policy production phải được bảo vệ và kiểm tra độc lập.

Nếu một gate bắt buộc không thể xác minh, pipeline nên dừng hoặc chuyển sang trạng thái blocked theo chính sách. Không tự động bỏ qua gate chỉ vì dịch vụ kiểm tra đang lỗi.

## 10. Triển khai tuần tự, đồng thời và kiểm soát xung đột

Một release thường cần thứ tự rõ ràng: triển khai dev, xác minh, promote staging, xác minh, rồi mới production. Tuy nhiên, một số dự án có thể triển khai nhiều vùng hoặc nhiều dịch vụ song song.

Cần xác định dependency giữa các bước:

- Database migration có phải chạy trước ứng dụng không?
- API mới có tương thích với consumer cũ không?
- Có thể triển khai nhiều instance cùng lúc không?
- Có cần chờ canary đạt ngưỡng trước khi rollout toàn bộ không?
- Có một môi trường dùng chung mà nhiều pipeline cùng thay đổi không?

Dùng concurrency group hoặc deployment lock theo phạm vi tài nguyên thực sự xung đột. Khóa toàn bộ tổ chức có thể làm giảm throughput; khóa quá hẹp lại không ngăn được hai pipeline cùng sửa một database hoặc service.

Các lựa chọn:

- Queue để triển khai theo thứ tự.
- Lock theo environment hoặc service.
- Namespace riêng cho preview và test.
- Conditional update để chỉ triển khai nếu revision hiện tại vẫn như đã kiểm tra.
- Hủy hoặc đánh dấu stale những yêu cầu cũ khi release mới hơn đã thay thế, nếu policy cho phép.

Nếu pipeline bị hủy giữa chừng, cần xác định tài nguyên nào đã thay đổi và trạng thái hiện tại là gì. Không nên giả định cancellation đồng nghĩa với rollback.

## 11. Chọn chiến lược rollout theo năng lực môi trường

Cùng workflow có thể hỗ trợ nhiều chiến lược triển khai:

- **Rolling update:** thay instance từng phần; phù hợp khi phiên bản cũ và mới có thể cùng tồn tại.
- **Blue-green:** chuẩn bị môi trường hoặc nhóm instance mới rồi chuyển traffic; cần tài nguyên và cơ chế chuyển traffic.
- **Canary:** đưa phiên bản mới đến một phần lưu lượng hoặc nhóm người dùng, theo dõi rồi tăng dần.
- **Recreate:** dừng phiên bản cũ rồi triển khai phiên bản mới; đơn giản nhưng có thể gây downtime.

Không phải môi trường nào cũng hỗ trợ mọi chiến lược. Dev có thể dùng rolling đơn giản; staging có thể mô phỏng canary; production chọn chiến lược theo SLO, kiến trúc và khả năng phục hồi.

Pipeline nên nhận strategy đã được policy cho phép, kiểm tra năng lực môi trường và ghi lại chiến lược thực tế. Không nên cho phép input tùy ý chọn một chiến lược mà target không hỗ trợ.

## 12. Database migration và tương thích giữa phiên bản

Tự động triển khai cùng quy trình không có nghĩa migration luôn chạy theo cách giống hệt mọi release. Database thường có vòng đời và rủi ro riêng.

Một chiến lược an toàn là expand-and-contract:

1. Thêm schema mới theo cách tương thích với ứng dụng đang chạy.
2. Triển khai ứng dụng có thể đọc/ghi theo cấu trúc mới.
3. Chuyển dữ liệu hoặc luồng sử dụng theo kế hoạch.
4. Chỉ xóa cấu trúc cũ khi không còn phiên bản nào phụ thuộc.

Pipeline cần biết migration nào đã chạy, migration có idempotent không và ứng dụng cũ có thể hoạt động với schema mới hay không.

Không nên rollback ứng dụng một cách tự động nếu migration đã thực hiện thay đổi không thể đảo ngược. Khi đó có thể cần forward fix hoặc quy trình phục hồi dữ liệu riêng.

## 13. Xác minh sau triển khai phải dùng cùng tiêu chí cốt lõi

Mỗi môi trường nên có một bộ kiểm tra chung để xác minh:

- Service đã sẵn sàng.
- Artifact digest đang chạy đúng với digest được yêu cầu.
- Config revision đã áp dụng đúng.
- Endpoint hoặc chức năng quan trọng phản hồi.
- Dependency cần thiết có thể truy cập.
- Không có lỗi hoặc độ trễ vượt ngưỡng đã định.
- Migration và trạng thái dữ liệu phù hợp.

Một số kiểm tra có thể khác theo môi trường. Production có thể cần kiểm tra lưu lượng thật và tỷ lệ lỗi; staging có thể chạy integration suite đầy đủ; dev chỉ cần smoke test nhanh.

Kết quả cần được ghi dưới cùng một cấu trúc để có thể so sánh giữa môi trường. Nếu dev báo deploy thành công nhưng không có artifact digest hoặc config revision, bằng chứng đó không đủ để so sánh với staging và production.

## 14. Idempotency, retry và rollback

Một deployment workflow có thể được chạy lại do timeout, mất kết nối hoặc thao tác người dùng lặp. Vì vậy, các bước cần được thiết kế để chạy lại an toàn.

**Idempotency:** cùng một yêu cầu triển khai nếu được gửi lại không tạo ra trạng thái sai hoặc tài nguyên trùng. Có thể dùng release ID, deployment ID và state check để nhận diện lần chạy đã hoàn tất.

**Retry:** chỉ retry lỗi tạm thời có thể phục hồi, với số lần và backoff giới hạn. Không retry mù quáng migration hoặc thao tác phá hủy dữ liệu.

**Rollback:** quay về artifact/configuration đã biết là tốt nếu tương thích với schema và trạng thái hiện tại. Với thay đổi dữ liệu không thể đảo ngược, cần forward fix hoặc recovery plan riêng.

Một quy trình rollback nên dùng cùng deployment contract và lưu audit như deploy bình thường. Không nên tạo một script rollback tùy ý chỉ chạy trên production mà không có xác minh đầu vào.

## 15. Quan sát và truy vết phát hành qua nhiều môi trường

Để biết cùng artifact đã đi qua các môi trường như thế nào, cần liên kết các bản ghi bằng release ID hoặc correlation ID.

Mỗi lần deploy nên ghi:

- Release ID và deployment ID.
- Artifact digest và source commit.
- Workflow/template revision.
- Environment ID.
- Config revision/fingerprint.
- Migration version nếu có.
- Deployment strategy.
- Actor hoặc workload identity.
- Approval và policy result.
- Thời gian, trạng thái và kết quả verification.
- Phiên bản trước đó và thông tin rollback nếu có.

Nhờ vậy, đội ngũ có thể trả lời:

- Artifact nào đã chạy ở staging?
- Production đang chạy đúng digest đã kiểm thử không?
- Cấu hình nào khác giữa staging và production?
- Ai đã yêu cầu hoặc phê duyệt triển khai?
- Bước nào thất bại và môi trường có thay đổi một phần không?

Không ghi plaintext secret vào deployment record. Chỉ lưu reference/version metadata cần thiết.

## 16. Ví dụ workflow đa môi trường

YAML sau mô tả logic tổng quát, không phải cú pháp trực tiếp của một nền tảng CI/CD cụ thể:

~~~yaml
deployment:
  inputs:
    artifact_digest: required
    target_environment:
      allowed:
        - dev
        - staging
        - production
    release_id: required

  common_steps:
    - verify_artifact_digest
    - verify_provenance_and_evidence
    - resolve_environment_configuration
    - validate_configuration
    - evaluate_environment_policy
    - acquire_environment_lock
    - deploy_artifact_and_configuration
    - verify_running_digest_and_config
    - record_deployment_evidence

  environments:
    dev:
      approval: automatic
      strategy: rolling
      verification:
        - health_check
        - smoke_test

    staging:
      approval: policy_based
      strategy: rolling
      verification:
        - health_check
        - smoke_test
        - integration_tests

    production:
      approval: required_by_policy
      strategy: canary
      verification:
        - health_check
        - critical_journey
        - error_rate_threshold
        - latency_threshold
~~~

Điểm cần giữ là common_steps được dùng cho mọi môi trường. Phần environments chỉ khai báo policy, strategy và verification phù hợp. Trong hệ thống thực tế, các giá trị này cần được quản lý phiên bản và bảo vệ quyền sửa.

Không nên để một workflow chung tự suy ra production chỉ từ một chuỗi người dùng nhập. Nền tảng cần xác minh actor, environment protection và deployment identity trước khi cấp quyền.

## 17. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Mỗi môi trường có script riêng | Hành vi triển khai lệch nhau | Dùng một workflow và adapter có kiểm soát |
| Build lại cho staging và production | Artifact đã test có thể khác artifact release | Build một lần, promote cùng digest |
| Sao chép workflow rồi sửa tay | Các bản sao dần khác nhau | Dùng reusable workflow hoặc template có version |
| Dùng tag mutable | Không xác định chắc nội dung được deploy | Resolve và deploy bằng digest |
| Gộp secret mọi môi trường | Một job có thể truy cập credential quá rộng | Secret scope và identity riêng |
| Cho input tự chọn URL/cluster | Có thể deploy đến đích ngoài allowlist | Environment ID được cấu hình và authorize |
| Cùng một gate cho mọi môi trường | Quá lỏng ở production hoặc quá nặng ở dev | Policy theo môi trường trong cùng workflow |
| Không kiểm tra cấu hình đã resolve | Giá trị runtime có thể khác file nguồn | Validate resolved config và ghi fingerprint |
| Không có lock hoặc state check | Pipeline chạy đồng thời có thể ghi đè | Concurrency control theo tài nguyên |
| Chỉ kiểm tra deploy command thành công | Ứng dụng có thể không hoạt động | Post-deploy verification |
| Rollback không xét migration | Có thể làm ứng dụng không tương thích dữ liệu | Recovery plan theo schema và trạng thái |
| Không ghi release ID xuyên môi trường | Khó truy vết hành trình artifact | Dùng correlation/release ID chung |

## 18. Checklist tự động hóa triển khai đa môi trường

Trước khi dùng một workflow cho dev, staging và production, hãy kiểm tra:

- [ ] Có deployment contract xác định artifact, target, config và strategy.
- [ ] Artifact được build một lần và định danh bằng digest bất biến.
- [ ] Cùng artifact được promote qua các môi trường.
- [ ] Cấu hình chung và overlay theo môi trường được quản lý phiên bản.
- [ ] Secret được lấy theo môi trường và job, không lưu plaintext.
- [ ] Quy tắc precedence và resolved configuration được kiểm tra.
- [ ] Workflow logic dùng chung, có version và review.
- [ ] Mỗi môi trường có policy, approval và quyền phù hợp.
- [ ] Target selection được giới hạn bằng allowlist và authorization.
- [ ] Có concurrency lock hoặc queue cho tài nguyên xung đột.
- [ ] Migration và compatibility giữa phiên bản được xác định.
- [ ] Chiến lược rollout phù hợp với năng lực từng môi trường.
- [ ] Post-deploy verification xác nhận artifact và config thực tế.
- [ ] Retry, cancellation và rollback có hành vi xác định.
- [ ] Release ID liên kết bằng chứng xuyên các môi trường.
- [ ] Có owner, audit trail và cách xử lý deployment thất bại một phần.

## 19. Bài tập tự đánh giá

Một nhóm có ba môi trường dev, staging và production. Hiện tại, mỗi môi trường dùng một script triển khai riêng. Developer build một image cho staging, sau đó release manager build lại image từ cùng branch để đưa lên production. Các file cấu hình được sao chép thủ công; production có thêm một số biến môi trường chưa được lưu trong repository. Khi deploy thất bại, nhóm thường chạy lại script và không biết tài nguyên nào đã thay đổi.

Hãy thiết kế lại quy trình:

1. Artifact nào cần được build và lưu sau khi merge?
2. Làm thế nào để staging và production dùng cùng digest?
3. Cấu hình nào nên nằm trong base, overlay và secret manager?
4. Những bước nào cần được dùng chung trong reusable workflow?
5. Gate và quyền nào khác nhau giữa ba môi trường?
6. Làm thế nào xác minh cấu hình thực tế sau khi resolve?
7. Cần dùng lock hoặc queue ở đâu?
8. Migration và rollback cần kiểm soát thế nào?
9. Release record cần lưu thông tin gì để truy vết từ dev đến production?

Một thiết kế tốt phải mô tả được một luồng đầu cuối duy nhất, chỉ rõ phần nào thay đổi theo môi trường và chứng minh artifact đã kiểm thử chính là artifact được triển khai.

## Kết luận

Tự động hóa triển khai đa môi trường giúp giảm khác biệt giữa các cách phát hành và tạo ra một luồng có thể lặp lại, kiểm tra và truy vết. Cốt lõi là build một lần, promote cùng artifact bằng digest bất biến, resolve cấu hình riêng theo môi trường và áp dụng gate cùng quyền phù hợp.

Một workflow dùng chung vẫn có thể hỗ trợ chiến lược rollout, approval và kiểm tra khác nhau theo môi trường. Khi deployment contract rõ, cấu hình được quản lý phiên bản, concurrency được kiểm soát và trạng thái sau deploy được xác minh, đội ngũ có thể đưa cùng một phiên bản qua dev, staging và production với bằng chứng nhất quán và khả năng khôi phục có kiểm soát.

