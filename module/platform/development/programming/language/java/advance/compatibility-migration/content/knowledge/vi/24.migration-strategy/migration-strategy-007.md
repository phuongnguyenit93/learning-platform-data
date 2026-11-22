# Ghi rõ phạm vi, chủ sở hữu và thời hạn của biện pháp tạm thời

Trong **Java Advance Compatibility Migration**, không phải lúc nào một hệ thống cũng có thể sửa triệt để mọi vấn đề tương thích trước ngày triển khai. Một thư viện cũ có thể vẫn cần quyền reflective access của JDK; một adapter tạm phải dịch dữ liệu giữa dịch vụ `javax.*` và `jakarta.*`; một message consumer cần nhận hai phiên bản schema; hoặc một integration test phải tách riêng vì công cụ chưa hỗ trợ JDK đích.

Các biện pháp như vậy có thể giúp nhóm **giảm gián đoạn khi chuyển đổi**, nhưng cũng tạo ra nợ kỹ thuật và rủi ro vận hành. Nguy hiểm nhất không hẳn là workaround được viết ra, mà là workaround **không có phạm vi rõ, không ai sở hữu, không có ngày hết hạn và không có bằng chứng để gỡ bỏ**. Sau vài tháng, một flag có thể được copy sang tất cả service, một dependency cũ có thể bị pin mãi, một feature flag dần trở thành nhánh logic mặc định, hoặc một bài test bị skip không còn ai nhớ lý do.

Bài **Ghi rõ phạm vi, chủ sở hữu và thời hạn của biện pháp tạm thời**, thuộc chương **Chiến lược chuyển đổi**, trình bày cách biến những giải pháp tạm thành các ngoại lệ **được kiểm soát, có thể tìm kiếm, kiểm thử, thu hồi và đóng lại**. Nội dung bao gồm cách định nghĩa phạm vi, chỉ định trách nhiệm, xác lập deadline và exit criteria, lưu quyết định trong repository, kiểm soát qua CI, rà soát định kỳ, xử lý quá hạn và tháo bỏ workaround mà không gây regression.

## 1. Biện pháp tạm thời là gì?

**Biện pháp tạm thời** (temporary workaround, mitigation hoặc compatibility bridge) là một thay đổi giúp hệ thống tiếp tục hoạt động trong lúc nguyên nhân gốc chưa được xử lý hoặc trong lúc hai phiên bản cùng tồn tại. Nó có thời gian sử dụng được giới hạn bởi một **mốc ngày, điều kiện kỹ thuật, sự kiện triển khai hoặc kết hợp các yếu tố đó**.

Ví dụ trong Java migration:

- Thêm `--add-opens` cho đúng package để thư viện legacy còn dùng reflection trên JDK mới.
- Pin một thư viện vào bản được xác nhận hỗ trợ JDK đích, trong khi chờ nâng lên bản chính thức khác.
- Dùng adapter để dịch request/response hoặc event giữa protocol v1 và v2.
- Giữ hai đường đọc dữ liệu trong migration database theo mô hình expand–migrate–contract.
- Chưa bật một enum/status mới cho producer khi consumer cũ còn hoạt động.
- Tạm dùng Jakarta binary transformer với một JAR chưa có upstream Jakarta release.
- Giữ một feature flag cho phép rollback logic trong canary.
- Dùng mock/fake thay một integration không khả dụng trong CI, kèm test thật ở pipeline khác.
- Chạy một công cụ code generation cũ trong build container được cô lập khi nâng toolchain chưa hoàn tất.
- Tạm thời giới hạn traffic tới một endpoint hoặc cohort trong khi kiểm tra compatibility.

Không phải mọi giải pháp trung gian đều là workaround xấu. Một số **compatibility layer là thiết kế migration có chủ đích**. Vấn đề là chúng phải có vòng đời: khi bước migration kế tiếp hoàn thành, lớp trung gian cần được đánh giá để gỡ hoặc chuyển thành một contract dài hạn có quyết định thiết kế chính thức.

### 1.1. Temporary workaround khác hotfix, fallback và thiết kế vĩnh viễn

| Khái niệm | Mục đích chính | Có nhất thiết phải hết hạn? |
|---|---|---|
| Hotfix | Sửa lỗi khẩn cấp, có thể là giải pháp hoàn chỉnh | Không, nếu sửa đúng nguyên nhân gốc |
| Workaround tạm | Né hoặc giảm tác động khi chưa sửa nguyên nhân | **Có**: deadline và exit criteria |
| Compatibility adapter | Cho hai phiên bản/contract tương tác | Có nếu chỉ phục vụ migration; có thể dài hạn nếu là API được hỗ trợ |
| Feature flag chuyển đổi | Kiểm soát rollout/rollback một thay đổi | Thường có hạn loại bỏ sau khi ổn định |
| Fallback/resilience pattern | Chịu lỗi trong vận hành thường xuyên | Có thể là thiết kế vĩnh viễn nếu có contract rõ |
| Security exception | Chấp nhận có điều kiện một sai lệch so với policy | Phải có hạn, người phê duyệt và compensating controls |
| Technical debt | Khoản đánh đổi kỹ thuật chưa trả | Cần được quản lý; workaround tạm phải có lộ trình cụ thể hơn |

Nếu một cơ chế đã được chấp nhận là **thiết kế vĩnh viễn**, đừng tiếp tục gắn nhãn “tạm thời” vô hạn. Hãy chuyển thành quyết định kiến trúc với contract, owner, test, support policy và tài liệu bảo trì tương ứng.

## 2. Vì sao một workaround không có vòng đời gây nguy hiểm?

Một ví dụ nhỏ:

~~~text
Migration JDK 11 -> 17
   |
   +-- Thư viện A cần deep reflection
   |
   +-- Thêm --add-opens vào startup script
   |
   +-- Production trở lại bình thường
   |
   +-- Không ghi owner, lý do, thời hạn
   |
   +-- Startup option được copy sang 8 service
   |
   +-- Thư viện A sau này đã được nâng
   |
   +-- Flag vẫn nằm trong config và không ai biết có còn cần
~~~

Vấn đề tiềm ẩn:
- **Security:** mở quyền reflective access rộng hơn cần thiết.
- **Compatibility:** option có thể không còn tác dụng hoặc không được hỗ trợ ở JDK sau.
- **Debugging:** khó xác định một service có cố tình dùng flag hay copy nhầm.
- **Upgrades:** người nâng JDK tiếp theo không biết điều kiện bỏ flag.
- **Ownership:** khi người đề xuất chuyển nhóm, ngoại lệ thành “mồ côi”.
- **Auditing:** không thể chứng minh ngoại lệ đã được phê duyệt và theo dõi.
- **Testing:** không có bài kiểm chứng hệ thống còn hoạt động khi flag được bỏ.

Tương tự, một bộ chuyển `javax` → `jakarta` ở build pipeline có thể giúp deploy hôm nay nhưng khiến tổ chức bỏ qua việc thư viện gốc đã EOL hoặc có lỗ hổng chưa vá. Biện pháp tạm vì vậy phải được xem như **một nghĩa vụ phải hoàn thành**, không chỉ một commit.

## 3. Ba câu hỏi bắt buộc: phạm vi, chủ sở hữu, thời hạn

Mỗi biện pháp cần trả lời rõ ít nhất ba câu hỏi:

1. **Phạm vi (scope):** tác động đến service/module/runtime nào, trong môi trường nào, cho traffic/dữ liệu/phiên bản nào? Điều gì nằm ngoài phạm vi?
2. **Chủ sở hữu (owner):** ai chịu trách nhiệm theo dõi, đánh giá rủi ro, triển khai thay thế và tháo bỏ biện pháp?
3. **Thời hạn (expiry):** đến ngày nào hoặc sau sự kiện nào biện pháp phải được loại bỏ hay tái phê duyệt? Cách xác minh điều kiện đóng là gì?

Một bản ghi tốt cần bổ sung:
- **Lý do:** sự cố/gap nào làm biện pháp cần thiết.
- **Rủi ro:** nguy cơ bảo mật, tương thích, dữ liệu, hiệu năng, compliance.
- **Kiểm soát bù trừ:** giảm phạm vi, giám sát, phân quyền, fallback.
- **Tiêu chí thoát:** upstream fix/test/deployment nào cho phép gỡ.
- **Bằng chứng:** ticket, PR, logs, tests, release notes và deployment.
- **Kế hoạch rollback:** nếu gỡ workaround rồi gặp regression, làm gì.

### 3.1. Mẫu một câu dễ hiểu

Một biện pháp phải có thể được tóm tắt:

> Service Orders sử dụng tạm `--add-opens` **chỉ** trong JVM chạy integration test trên JDK 17–21, để chờ nâng thư viện phản chiếu LegacyMapper. Nhóm Platform/JVM sở hữu, hạn đánh giá là 2027-01-15 (ngày minh họa). Exit: nâng thư viện, xóa flag, chạy test trên hai JDK và xác nhận không có `InaccessibleObjectException`. Không áp dụng cho production JVM.

Câu trên hữu ích hơn:
 
> Tạm thêm JVM flag để sửa lỗi, xử lý sau.

Nó nêu rõ phạm vi, owner, deadline và điều kiện kiểm chứng; người đọc biết ngay không được tự copy sang production.

## 4. Ghi phạm vi theo nhiều chiều

“Áp dụng cho dự án X” thường quá rộng. Trong hệ thống Java có nhiều runtime và environment, scope nên đủ cụ thể.

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| Repository/module | Workaround nằm ở module nào? | `orders-api`, `legacy-client` |
| Service | Process hay job nào bị tác động? | Orders web service, batch reconciliation |
| Environment | Dev, CI, staging, production? | Chỉ CI integration |
| JDK | Phiên bản/vendor nào? | JDK 17/21, HotSpot |
| Framework | Version nào? | Boot 3.2.x, Tomcat 10.1 |
| Dependency | JAR hoặc plugin nào cần workaround? | `legacy-mapper:2.4` |
| Operation | Endpoint/task nào? | Startup plugin load, async export |
| Traffic cohort | Ai nhận behavior khác? | Canary 5%, tenant thử nghiệm |
| Data scope | Schema/message/table nào? | Topic `order-events-v1` |
| Security boundary | Có mở quyền cho process/actor nào? | Package được opens cho unnamed modules |
| Deployment | Image/script/helm chart nào? | `charts/orders/values-staging.yaml` |
| Lifetime | Từ release nào đến mốc nào? | Bắt đầu 2026-11, hết hạn 2027-01 |

### 4.1. Scope bao gồm cả phần *không* được áp dụng

Ví dụ:
- “Chỉ cho `integrationTest`, **không** cho `test` thường và production”.
- “Chỉ tại topic chuyển tiếp `orders-v1-bridge`, **không** thay mọi producer”.
- “Chỉ cho tenant canary, **không** bật toàn hệ thống”.
- “Chỉ chuyển `javax.servlet` trong WAR này, **không** đổi `javax.xml.parsers` thuộc Java SE”.

Giới hạn âm (explicit exclusions) giúp tránh **scope creep**. Đội migration khác có thể nhận ra một workaround hữu ích rồi sao chép mà không hiểu điều kiện ban đầu.

### 4.2. Scope nên trỏ đến code/config thực tế

Không chỉ ghi mô tả bằng chữ. Ghi:
- File path/config key hoặc module/PR.
- Deployment manifests và service versions.
- Launch arguments tác động.
- Dependency coordinates và version range.
- Feature flag identifier.
- Schema/topic/endpoint nếu liên quan.

Vì file path có thể đổi, nên gắn cả **ID biện pháp và issue/PR link**; path hỗ trợ tìm nhanh còn ID giúp duy trì traceability qua refactor.

## 5. Chọn người chịu trách nhiệm rõ ràng

Một workaround không nên có owner là “team chung” hoặc “người nào rảnh”. Có thể phân vai như sau:

| Vai trò | Trách nhiệm |
|---|---|
| **Technical DRI** | Sở hữu implementation, theo dõi rủi ro và chuẩn bị removal PR |
| **Service owner** | Bảo đảm biện pháp không gây lỗi vận hành và phối hợp release |
| **Risk/security approver** | Chấp nhận ngoại lệ policy và compensating controls nếu cần |
| **Migration lead** | Theo dõi deadline, phụ thuộc giữa teams, điều phối removal |
| **Reviewers** | Kiểm tra scope và exit tests, không thay DRI |
| **Backup owner** | Duy trì trách nhiệm khi DRI vắng hoặc chuyển nhóm |

**DRI (Directly Responsible Individual)** cần là một người hoặc một vai trò trực tiếp có thể định danh qua hệ thống quản lý nhân sự/đội ngũ, kèm nhóm duy trì. Chỉ gắn một tên cá nhân mà không có team backup có thể dẫn tới mất owner khi người đó nghỉ hoặc chuyển dự án.

### 5.1. Quy tắc ownership thực hành

- Mỗi biện pháp có **một DRI chính** để tránh trách nhiệm bị chia mờ.
- Có **team sở hữu lâu dài** và người backup.
- Những ngoại lệ bảo mật phải có **phê duyệt từ vai trò có thẩm quyền**, không chỉ tác giả commit.
- Nếu workaround ảnh hưởng nhiều service, có **coordinating owner** và owner của từng service cụ thể.
- Khi người phụ trách chuyển nhóm, **chuyển owner trước ngày rời trách nhiệm**.
- Deadline phải nằm trong backlog/cadence của owner, không chỉ được viết trong một wiki ít ai đọc.

### 5.2. Ownership không đồng nghĩa người viết workaround

Người tạo hotfix ban đầu có thể là on-call engineer. Họ không nhất thiết là người có quyền thay thư viện, nâng framework hoặc quyết định security risk. Vì vậy cần phân biệt:
- **Implemented by:** ai tạo change.
- **Owned by:** ai chịu trách nhiệm duy trì/gỡ.
- **Approved by:** ai chấp nhận ngoại lệ.
- **Removal assignee:** ai làm PR thoát; thường là DRI hoặc người được giao cụ thể.

Nếu không ghi rõ, các nhóm dễ cho rằng “người đã thêm flag sẽ tự xóa sau”.

## 6. Ghi thời hạn: ngày, sự kiện và tiêu chí thoát

Một workaround chỉ có ngày hết hạn nhưng không có phương án thay thế dễ trở thành cảnh báo bị bỏ qua. Ngược lại, chỉ ghi “đợi thư viện mới” mà không có ngày review có thể kéo dài vô hạn.

Nên có **hai tầng thời hạn**:

1. **Ngày hết hạn/decision deadline:** đến ngày này phải gỡ hoặc có quyết định tái phê duyệt minh bạch.
2. **Exit criteria/trigger:** điều kiện kỹ thuật cho phép gỡ, chẳng hạn dependency được nâng và test pass khi không còn flag.

Ví dụ:

~~~text
createdAt: 2026-11-12
nextReviewAt: 2026-12-01
expiresAt: 2027-01-15
exitTrigger: "legacy-mapper >= 3.x đã được chấp nhận trong app"
exitTests:
  - "Không còn InaccessibleObjectException khi bỏ --add-opens"
  - "Integration test pass trên JDK 17 và JDK 21"
  - "Production canary không có regression"
~~~

Các ngày trên là **ví dụ**, không phải deadline của dự án thực.

### 6.1. Expiry không phải lời hứa framework ra bản vá đúng ngày

Một dependency upstream có thể trễ release. Khi đó:
- Chủ sở hữu phải review trước hạn.
- Đánh giá rủi ro hiện tại, mức ảnh hưởng và khả năng thay thế.
- Chọn phương án: thay thư viện, giới hạn scope, tạm ngưng rollout, tách workload, hoặc gia hạn có phê duyệt.
- Ghi **lý do gia hạn, ngày mới, người phê duyệt và thay đổi kiểm soát**.

Không tự đổi ngày hết hạn trong file mà không ghi lịch sử/approval. Nếu biện pháp không còn an toàn hoặc vi phạm policy không được gia hạn, phải escalate và có kế hoạch xử lý.

### 6.2. Dùng calendar date và timezone nhất quán

Với biện pháp được quản lý theo ngày:
- Dùng ISO 8601 như `2027-01-15`.
- Định nghĩa expiry có hiệu lực từ đầu hay cuối ngày, theo timezone nào, nếu tự động enforce.
- Nếu nhiều khu vực triển khai, ưu tiên timestamp có timezone offset hoặc UTC cho sự kiện tự động.
- Dùng deadline trước khi một runtime/dependency mất support, không đợi đến đúng ngày ngừng hỗ trợ.

Trong CI policy, một trường `expiresOn` mang date-only có thể quy định “quá hạn từ 00:00 UTC ngày sau ngày ghi”, hoặc một quy tắc khác. **Phải ghi rõ quy ước**, tránh mỗi script hiểu một kiểu.

### 6.3. Deadline không chỉ nằm ở file YAML

Cần có ít nhất một cơ chế nhắc/chặn:
- Issue với due date và owner.
- Migration board/dashboard.
- CI lint check hoặc báo cáo định kỳ.
- Lịch review ở sprint/release planning.
- Gate yêu cầu phê duyệt nếu gia hạn.

Một mục “TODO remove later” không có ticket và deadline **không đủ** để quản lý workaround.

## 7. Hồ sơ tối thiểu của một biện pháp tạm

Một temporary-measure register có thể lưu trong repository ở đường dẫn do nhóm quy định, ví dụ `migration/temporary-measures.yml`. Sau đây là **mẫu dữ liệu minh họa**, không phải schema của một công cụ tiêu chuẩn:

~~~yaml
schemaVersion: 1
measures:
  - id: "JAVA-MIG-042"
    title: "Giới hạn reflective access cho LegacyMapper"
    status: "active"
    reason: "LegacyMapper 2.4 sử dụng reflective access không tương thích JDK mới"
    category: "jvm-option"

    scope:
      repositories: ["orders-platform"]
      modules: ["orders-integration"]
      environments: ["ci", "staging"]
      jdks: ["17", "21"]
      runtimeProcesses: ["integration-test-jvm"]
      excludedEnvironments: ["production"]

    implementation:
      type: "jvm-argument"
      value: "--add-opens=java.base/java.lang=ALL-UNNAMED"
      codeLocations:
        - "orders-integration/build.gradle.kts"
      introducedBy: "PR-1234"

    ownership:
      technicalDri: "owner-in-team-directory"
      owningTeam: "platform-jvm"
      backupTeam: "orders"

    risk:
      severity: "medium"
      securityImpact: "Mở quyền deep reflection trong process test"
      compensatingControls:
        - "Không dùng trong production"
        - "Giữ dependency/test tool trong nguồn đã được phê duyệt"

    lifecycle:
      createdOn: "2026-11-12"
      nextReviewOn: "2026-12-01"
      expiresOn: "2027-01-15"
      removalTicket: "MIG-567"
      exitTrigger: "Nâng LegacyMapper lên bản không cần opens"
      exitEvidence:
        - "Chạy test không có --add-opens trên JDK 17 và JDK 21"
        - "Integration test pass"
      rollbackPlan: "Khôi phục flag chỉ trong test runner nếu test regression"

    approvals:
      - role: "migration-lead"
        reference: "APPROVAL-089"
~~~

Lợi ích:
- **Scope có cấu trúc** giúp script kiểm tra biện pháp không bị copy sai môi trường.
- **Ownership có tên** để tạo reminder.
- **Expiry có ngày** để tự phát hiện quá hạn.
- **Exit evidence** giúp code review gỡ bỏ có tiêu chuẩn cụ thể.
- **Implementation path** giúp truy vết flag hiện tại.
- **Approval reference** giúp audit giải thích tại sao ngoại lệ được chấp nhận.

Không đưa token, password, account secret hoặc dữ liệu cá nhân vào register. Nếu liên kết ticket/private incidents, áp quyền truy cập theo nhu cầu công việc.

### 7.1. Nơi nào là nguồn sự thật?

Có thể dùng:
- YAML/JSON trong repository.
- Issue tracker với custom fields.
- ADR (Architecture Decision Record).
- Service catalog hoặc risk exception system.
- Một bảng theo dõi migration được team duy trì.

Nên chọn **một nguồn sự thật chính** cho ID, owner, deadline và status, còn các nơi khác dẫn link đến nó. Nếu nhiều hệ cùng chứa bản sao, cần cơ chế đồng bộ để tránh deadline ở wiki khác deadline trong ticket.

Đối với project nhiều repository, có thể quản lý register tập trung nhưng vẫn gắn **ID trong code/config** để tìm nhanh. Ví dụ một comment:

~~~properties
# TEMP-MIGRATION JAVA-MIG-042; owner=platform-jvm; expires=2027-01-15
# Chỉ cho integration-test JVM, không đưa vào production.
org.example.testJvmOpens=--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

Đây chỉ là ví dụ metadata/comment, **không phải property Gradle chuẩn**; cách truyền option thực tế phải phụ thuộc test task/build script. Không dùng comment làm công cụ enforce duy nhất.

## 8. ADR cho một ngoại lệ quan trọng

Với workaround có ảnh hưởng rộng, chỉ một dòng trong register có thể chưa đủ. Dùng **Architecture Decision Record (ADR)** để ghi lý do và đánh đổi.

Một ADR nên có:

~~~text
ADR-017: Compatibility bridge cho Order Events v1/v2

Status: Accepted (temporary)
Context:
  - Producer mới tạo event v2
  - Consumer v1 vẫn còn trong thời gian hỗ trợ
Decision:
  - Adapter đọc cả v1 và v2 trong consumer mới
  - Producer không phát trường bắt buộc mới tới consumer v1
Scope:
  - Kafka topic orders-v1-migration
  - Orders/Billing trong staging và production
Owner:
  - Messaging DRI, cùng service owners Orders/Billing
Expiry:
  - 2027-02-28, review mỗi sprint
Exit:
  - Không còn consumer v1
  - Tất cả event cũ đã hết retention hoặc có replay path tương thích
  - Contract/integration tests pass khi bỏ adapter
Risks:
  - Duplicate handling, schema drift, replay
Controls:
  - Schema registry checks, idempotency, consumer lag alerts
Rollback:
  - Giữ producer v1 contract trong cửa sổ đã chốt
References:
  - PR, deployment, runbook, test evidence
~~~

ADR trả lời **vì sao tổ chức quyết định**; register giúp **quản lý hiện trạng và deadline**. Một ADR được duyệt không có nghĩa workaround tự được gia hạn vô thời hạn.

### 8.1. Decision log và audit trail

Khi đổi scope/expiry/owner, ghi:
- Ai đề xuất và ngày thay đổi.
- Vì sao cần đổi.
- Rủi ro phát sinh.
- Người phê duyệt.
- Sự kiện/issue liên quan.
- Kiểm soát mới.
- Exit criteria và deadline cập nhật.

Tránh rewrite lịch sử để nhìn như workaround đã được phê duyệt từ đầu. Với dữ liệu dạng Git, commit/PR history giúp audit, nhưng nếu phải tuân thủ quy định nghiêm hơn, dùng hệ thống exception tracking có quyền và retention phù hợp.

## 9. Quy trình phê duyệt trước khi kích hoạt

Một workaround tốt không nên có status `active` chỉ vì merge code đã xong. Cần có quyết định rằng nó đủ an toàn cho **phạm vi cụ thể**.

Luồng đề xuất:

~~~text
Phát hiện blocker migration
           |
           v
Đề xuất biện pháp tạm
           |
           v
Viết scope + owner + expiry + risk + exit criteria
           |
           v
Review kỹ thuật / Security / Operations (theo mức rủi ro)
           |
       +---+----+
       |        |
    Reject    Approve
       |        |
  Chọn cách    v
  khác       Deploy giới hạn
                |
                v
           Monitor + review
                |
          +-----+-------+
          |             |
       Remove        Extend?
          |             |
          v             v
       Verify       Reassess risk
          |         and approvals
          v
         Close
~~~

### 9.1. Tiêu chí chấp nhận ngoại lệ

Nên hỏi:
1. Blocker cụ thể là gì? Có log/reproducer không?
2. Có giải pháp sửa nguyên nhân gốc khả thi ngay không?
3. Workaround giảm tác động tới mức nào và làm mất bảo đảm nào?
4. Phạm vi có nhỏ nhất có thể không?
5. Có cách phát hiện khi workaround không còn hiệu lực hoặc gây lỗi không?
6. Có kế hoạch tháo bỏ và thời hạn thực tế không?
7. Có thể rollback deployment/behavior/data không?
8. Ai chấp nhận rủi ro còn lại?
9. Điều gì khiến biện pháp phải bị thu hồi sớm hơn expiry?

Nếu câu trả lời còn mơ hồ ở phần bảo mật/dữ liệu, không nên tự gắn status approved để “mở đường” cho rollout.

### 9.2. Có những workaround không nên được phê duyệt

Ví dụ các cách “tạm cho chạy” nhưng vi phạm an toàn:
- Tắt certificate validation hoặc hostname verification khi gọi production systems.
- Vô hiệu hóa authentication/authorization trên endpoint thật.
- Ghi secret vào Git/log để khắc phục config migration.
- Tắt kiểm tra chữ ký artifact hoặc bỏ supply-chain controls vô thời hạn.
- Cho phép deserialization dữ liệu không tin cậy mà không có policy/guard thích hợp.
- Chạy database destructive migration không có backup/recovery plan.
- Dùng unsupported JDK runtime có lỗ hổng nghiêm trọng cho production mà không có biện pháp xử lý được phê duyệt.

Đối với rủi ro bảo mật, **deadline không biến một hành vi nguy hiểm thành an toàn**. Có thể cần chặn release, cô lập hệ thống, nâng thư viện hoặc thay giao thức thay vì tạo ngoại lệ.

## 10. Các loại workaround thường gặp trong Java migration

### 10.1. JVM module access: --add-opens

Từ Java 9, JPMS đưa ra module boundaries. Ở các JDK hiện đại, strong encapsulation làm một số thư viện reflection legacy gặp `InaccessibleObjectException`.

Ví dụ một flag tạm:

~~~bash
java \
  --add-opens=java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

Nó cho phép deep reflective access đến package `java.lang` của module `java.base` từ các **unnamed modules** trong process đó. Quyền này có thể rộng hơn nhu cầu của một thư viện cụ thể; nếu ứng dụng dùng named modules, cơ chế chọn target module có thể khác.

**Không xem `--add-opens` là giải pháp gốc.** Nó không làm API bị xóa xuất hiện trở lại và không sửa mọi lỗi binary compatibility. Với production workload, phải review rủi ro khi mở internals, chọn package/target hẹp nhất khả thi và ưu tiên nâng thư viện.

Bản ghi cần chỉ rõ:
- Lỗi/root cause và dependency cần flag.
- Flag áp dụng cho process nào: Gradle daemon, test JVM hay application runtime?
- JDK versions nào cần flag.
- Env nào được phép.
- Owner của dependency upgrade.
- Exit: nâng library, bỏ flag, test lại runtime.
- Deadline và approval nếu mở trên production.

#### Không copy flag từ test sang production

Một `--add-opens` trong `Test.jvmArgs` chỉ ảnh hưởng JVM test. Thêm vào `JAVA_TOOL_OPTIONS` toàn hệ thống/container có thể tác động mọi Java process và nới quyền không cần thiết. Scope phải phân biệt **build JVM, test fork và production JVM**.

### 10.2. Dependency pin hoặc fork tạm

Ví dụ một thư viện chưa hỗ trợ JDK 21, nên dự án:
- Pin vào bản đã xác minh hoạt động trên JDK mục tiêu.
- Tạm dùng fork nội bộ được vá để tương thích.
- Loại một transitive dependency xung đột.

Rủi ro:
- Bỏ lỡ security patches.
- Binary/API compatibility xấu đi với framework.
- Fork diverge khỏi upstream.
- License/SBOM/provenance không được quản lý.
- Test chỉ chạy trên một vendor/JDK build.

Record cần có coordinates, pinned version, CVE policy, upstream issue, owner, review cadence, exit version và test matrix. **Không pin version cũ vô thời hạn** chỉ vì build đang xanh.

### 10.3. Jakarta namespace transformation

Một legacy JAR còn `javax.servlet.*` có thể được chuyển tạm bằng Eclipse Transformer hoặc Apache Tomcat Jakarta migration tool khi chưa có bản Jakarta chính thức.

Scope cần nêu:
- Input JAR/WAR checksum và nguồn phát hành.
- Transformer version/rules.
- Output artifact hash.
- Target Jakarta EE/platform/container.
- Những class/resources thực sự được transform.
- Những package `javax.*` thuộc Java SE phải giữ nguyên.
- Thời hạn trước khi thay bằng upstream Jakarta artifact.

Exit: vendor release hoặc source rebuild theo Jakarta, xóa binary transform, chạy contract/integration tests trên container đích.

Không giả định việc đổi bytecode tự sửa reflection, XML, ServiceLoader, signature, serialization hoặc behavior. Nếu artifact gốc được ký, transformation làm thay đổi bytes và cần quy trình provenance/signature phù hợp.

### 10.4. Compatibility adapter và dual-read

Trong giai đoạn chạy v1/v2 song song, consumer mới có thể tạm đọc cả schema cũ và mới:

~~~text
Producer v1 --- event v1 ---+
                            |
                            v
                      Dual-version reader
                            |
                            v
                      Domain model mới
                            ^
                            |
Producer v2 --- event v2 ---+
~~~

Phạm vi cần nêu:
- Topic/event type/schema versions.
- Consumer groups và service versions.
- Retention/replay policy.
- Cách xử lý unknown enum/fields.
- Idempotency và duplicate messages.
- Business semantics khi mapping.
- Khi nào còn consumer cũ và khi nào bỏ adapter.

Exit không chỉ là “deploy producer v2 xong”. Cần chứng minh **không còn consumer v1 cần hỗ trợ**, event cũ đã được xử lý hoặc còn replay path an toàn, và rollback vẫn có kế hoạch nếu chuyển sang forward-only.

### 10.5. Feature flag phục vụ migration

Feature flag có thể dùng để bật logic mới theo tenant/cohort trong canary:

~~~yaml
features:
  use-new-json-parser: false
~~~

Nếu flag là tạm:
- ID và nơi cấu hình.
- Default ở từng environment.
- Owner và người được phép bật/tắt.
- Các trạng thái/contract mà hai nhánh tạo ra.
- Metrics và rollback path.
- Deadline loại nhánh code cũ.

Một cờ đã bật 100% traffic nhưng vẫn tồn tại hai năm có thể gây **complexity leak**: test phải bao phủ hai nhánh, dependency cũ không gỡ được và một người có thể bật nhầm behavior không còn hỗ trợ.

### 10.6. Test quarantine hoặc suppression

Một số test công cụ cũ chưa hỗ trợ JDK mới có thể cần tách pipeline hoặc tạm quarantine. Đây là ngoại lệ **rủi ro cao về chất lượng** vì nó làm giảm độ bao phủ của regression detection.

Bản ghi phải có:
- Danh sách test chính xác.
- Lỗi và điều kiện tái hiện.
- Phần chức năng không còn được kiểm tra.
- Bài kiểm chứng thay thế hoặc manual validation.
- Owner sửa công cụ/test.
- Deadline khôi phục test.
- CI report hiển thị test vẫn bị quarantine.

Không được ẩn test bị bỏ qua khỏi báo cáo rồi tuyên bố tất cả test pass. Một test bị vô hiệu hóa **không phải bằng chứng tương thích**.

### 10.7. JVM flags và agent policy

Trong nâng JDK 21+, một số framework test hoặc tooling có thể gặp warning dynamic Java agent loading theo JEP 451. Có trường hợp đội muốn bật tạm `-XX:+EnableDynamicAgentLoading` để tương thích, nhưng điều đó cần review rõ scope.

Khi test thật sự cần inline mocking, cấu hình **startup `-javaagent` tường minh cho JVM test** thường là hướng có chủ đích hơn tự cho phép dynamic attach. Một cấu hình `-javaagent` có thể là **thiết kế test bền vững**, không nhất thiết là workaround tạm. Đừng mặc định mọi JVM flag đều phải xóa; hãy phân loại theo mục đích, policy và lifecycle.

Đặc biệt, **đừng ghi một flag không còn được JDK hỗ trợ** như một cách “tương thích tạm”. Ví dụ `--illegal-access` không còn cơ chế hữu dụng để mở rộng quyền như trước ở các JDK hiện đại; cần xác minh flags chính xác theo release và sửa nguyên nhân.

## 11. Rủi ro cần đánh giá trước khi áp dụng

Một workaround có thể làm thay đổi:
- **Security posture:** module access, agent permissions, auth/TLS.
- **Data integrity:** schema dual-write, replay, idempotency.
- **Correctness:** parser fallback, enum mapping, timezone.
- **Reliability:** timeouts, retries, failure propagation.
- **Performance:** reflection, serialization, GC, memory.
- **Operations:** logging, metrics, manual steps, restart needs.
- **Maintainability:** thêm nhánh code/adapter, fork dependency.
- **Compliance/supply chain:** unsupported artifacts, source provenance, licensing.

Một ma trận định tính:

| Risk level | Ví dụ | Điều kiện quản lý |
|---|---|---|
| Low | Cờ cho một test noncritical ở CI, có test thay thế | Owner, deadline, CI warning |
| Medium | Dependency pin ở một internal service | Release review, SCA scan, test matrix |
| High | Adapter dữ liệu ảnh hưởng giao dịch tài chính | Phê duyệt owner nghiệp vụ, reconciliation, alert, rollback |
| Critical | Bỏ auth/TLS kiểm tra trên production | Không mặc định cho phép; cần giải pháp khác/phê duyệt theo policy cực kỳ chặt |

Đây chỉ là **phân loại minh họa**; tổ chức có thể có risk framework chi tiết hơn. Không hạ nhãn rủi ro chỉ để vượt gate.

### 11.1. Compensating controls là gì?

Là những cơ chế giảm rủi ro trong khi biện pháp tồn tại:
- Giới hạn chỉ ở CI/test environment.
- Chỉ một service/tenant/endpoint.
- Network isolation hoặc rate limit phù hợp.
- Alert khi fallback được kích hoạt.
- Kiểm tra version dependency mỗi release.
- Canary và rollback có điều kiện.
- Data reconciliation khi dual-write.
- Quyền approve có phân vai.
- Contract/integration tests thay cho check bị thiếu.

Compensating control **không thay thế** việc sửa nguyên nhân gốc; nó giữ rủi ro trong mức có thể chấp nhận trong một khoảng thời gian được phê duyệt.

## 12. Thiết kế lifecycle và trạng thái

Không nên chỉ có hai trạng thái “có/không”. Một lifecycle gợi ý:

~~~text
proposed -> under_review -> approved -> active
                                  |
                                  v
                           removal_planned
                                  |
                                  v
                              removed
                                  |
                                  v
                               closed
~~~

Trạng thái ngoại lệ:
- `rejected`: không được phép dùng.
- `revoked`: phải dừng sớm do rủi ro.
- `expired`: quá hạn, chưa được gia hạn hợp lệ.
- `extension_requested`: cần review/approval, không tự động được gia hạn.
- `blocked`: chưa thể gỡ vì một dependency chưa đáp ứng, phải có escalation.

### 12.1. Khác biệt giữa expired và removed

- **Expired**: deadline đã qua, nghĩa vụ chưa được đóng. Không được đánh dấu là hoàn thành.
- **Removed**: change đã được merge/deploy bỏ workaround.
- **Closed**: đã có bằng chứng trên các môi trường cần thiết rằng workaround không còn, exit tests pass, monitoring ổn định và register/ticket được cập nhật.

Chỉ xóa một dòng YAML khỏi register không chứng minh option đã biến mất ở Helm, systemd, Dockerfile, CI hoặc config service.

### 12.2. Quy tắc không bao giờ xóa dấu vết

Sau khi gỡ, nên giữ bản ghi đóng hoặc audit reference có:
- Ngày tháo bỏ.
- PR/commit.
- Artifact/deployment version.
- Test evidence.
- Người xác nhận.
- Rủi ro còn lại nếu có.

Nếu hệ thống cần dọn active list, có thể chuyển vào `closed`/archive thay vì xóa hết lịch sử.

## 13. CI guardrail: biến deadline thành tín hiệu kỹ thuật

Viết ngày hết hạn trong README là chưa đủ nếu không ai xem. Có thể dùng CI để:
1. Kiểm tra mọi workaround active đều có ID, owner, scope, expiry, exit ticket.
2. Cảnh báo khi deadline sắp tới.
3. Chặn thêm workaround thiếu mandatory fields.
4. Phát hiện expired records theo policy.
5. Bắt buộc review nếu đổi ngày hoặc mở rộng scope.
6. Kiểm tra flags/dependencies trong code có tham chiếu ID.
7. Tạo report tự động cho migration lead.

### 13.1. Ví dụ JSON register và script kiểm tra expiry

Để minh họa kiểm tra bằng **Python standard library**, có thể dùng JSON thay vì YAML nếu pipeline không muốn cài YAML parser. Mẫu:

~~~json
{
  "schemaVersion": 1,
  "measures": [
    {
      "id": "JAVA-MIG-042",
      "status": "active",
      "owner": "platform-jvm",
      "scope": ["ci:orders-integration"],
      "expiresOn": "2027-01-15",
      "removalTicket": "MIG-567"
    }
  ]
}
~~~

Ví dụ script kiểm tra field và ngày quá hạn:

~~~python
import json
import sys
from datetime import date
from pathlib import Path

path = Path("migration/temporary-measures.json")
register = json.loads(path.read_text(encoding="utf-8"))

required = ("id", "owner", "scope", "expiresOn", "removalTicket")
today = date.today()
errors = []

for measure in register.get("measures", []):
    if measure.get("status") not in ("active", "approved"):
        continue

    missing = [
        key for key in required
        if not measure.get(key)
    ]
    if missing:
        errors.append(
            f"{measure.get('id', '<missing id>')}: "
            f"missing {', '.join(missing)}"
        )
        continue

    try:
        expires_on = date.fromisoformat(measure["expiresOn"])
    except (TypeError, ValueError):
        errors.append(f"{measure['id']}: invalid expiresOn")
        continue

    if today > expires_on:
        errors.append(
            f"{measure['id']}: expired on {expires_on}"
        )

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)

print("Temporary measures: mandatory fields and expiry OK")
~~~

Đây là **script minh họa**; nó đọc đúng một file JSON và dùng ngày local của runner. Với production CI, cần thống nhất timezone (ví dụ UTC), kiểm tra schema đầy đủ, xử lý file thiếu, ID trùng, scope hợp lệ và chính sách với `extension_requested` hoặc `expired`. Nếu dùng YAML, cần parser tương ứng và cùng validation rules.

### 13.2. Không nên dùng CI expiry gate thiếu escape hatch có kiểm soát

Nếu tất cả pipeline đều bị chặn chỉ vì một deadline về mặt lịch, đội có thể xóa record hoặc sửa ngày tùy tiện. Nên có quy trình:
- Mặc định fail hoặc cảnh báo theo mức rủi ro.
- Với hệ thống production-critical, cung cấp đường **time-boxed exception approval**.
- Mọi gia hạn có owner, reason, scope, approver, ngày mới.
- Log thay đổi và tạo ticket.
- Không cho phép silent bypass bằng cách xóa ID.

Mục đích của gate là **thúc đẩy quyết định có trách nhiệm**, không phải tạo động lực lách kiểm soát.

## 14. Static inventory trong repository và runtime

Một biện pháp tạm có thể xuất hiện ở:
- Source Java/Kotlin và test helpers.
- Gradle/Maven build scripts, compiler flags.
- Dockerfile và container entrypoint.
- Kubernetes manifests/Helm.
- Systemd unit hoặc service scripts.
- CI variables và pipeline templates.
- Remote config service.
- Feature flag platform.
- Java agent launch config.
- Deployment descriptors và XML.
- Infrastructure-as-code.

Không được coi việc grep không thấy flag trong repository là bằng chứng nó không chạy. Startup options có thể được inject bởi `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, Helm values, CI secrets hoặc orchestration platform.

### 14.1. Tìm các dấu hiệu phổ biến

Ví dụ lệnh tìm kiếm khi đội chủ động rà repository:

~~~bash
rg -n --hidden -g '!**/.git/**' \
  'TEMP-MIGRATION|JAVA-MIG-[0-9]+|TODO.*remove|--add-opens|--add-exports' .

rg -n --hidden -g '!**/.git/**' \
  'EnableDynamicAgentLoading|mock-maker-inline|skipTests|test\.enabled|feature\.' .
~~~

Kết quả cần phân loại, không xóa máy móc. `--add-opens` có thể là một phần toolchain được hỗ trợ dài hạn cho một use case có lý do rõ; một feature flag có thể là resilience feature vĩnh viễn. **Inventory phải dựa vào intent và policy**, không phải từ khóa đơn thuần.

### 14.2. So thực tế runtime với register

Một runbook có thể kiểm:
- JVM flags hiệu lực của process qua `jcmd <pid> VM.flags` khi quyền và môi trường hỗ trợ.
- `java -version` và container image digest.
- Kubernetes manifest đã render.
- Active feature flag configuration.
- Dependency tree của artifact đã phát hành.
- Tests và condition evaluation/actuator data nếu liên quan.

Không log raw env/secret để “chứng minh” config. Chỉ cần bằng chứng rằng option/key/version cụ thể còn tồn tại đúng scope.

## 15. Đánh dấu trong code nhưng không làm rối codebase

Một comment ngắn gần workaround nên có ID và mục đích. Ví dụ:

~~~java
public final class LegacyStatusAdapter {

    // TEMP-MIGRATION JAVA-MIG-057
    // Owner: messaging-platform; expiry: 2027-02-28
    // Chỉ dùng cho event v1 trong giai đoạn chạy song song.
    public String toNewStatus(String legacyStatus) {
        if ("WAITING".equals(legacyStatus)) {
            return "PENDING";
        }
        return legacyStatus;
    }
}
~~~

Một comment không đủ để chứng minh mapping này đúng về nghiệp vụ. Cần contract tests cho toàn bộ enum/status và kiểm tra consumer v1/v2. Nhưng ID giúp tìm code phải xóa sau này.

### 15.1. Không nhúng deadline làm thay đổi runtime đột ngột

Tránh code kiểu:

~~~java
if (LocalDate.now().isAfter(expiryDate)) {
    throw new RuntimeException("Workaround expired");
}
~~~

nếu việc đó có thể làm production dừng vào ngày hết hạn. Expiry nên ưu tiên được thực thi ở **governance/CI/release gates**, cùng cơ chế escalation. Nếu có yêu cầu security policy thật sự cần runtime expiry, phải thiết kế rõ việc fail-closed/fallback, có monitoring và người phê duyệt; không tự tạo time bomb trong service.

### 15.2. Không che logic mới bằng một nhánh cũ vô hạn

Với feature flag:

~~~java
if (flags.useNewSerializer()) {
    return newSerializer.encode(order);
}
return legacySerializer.encode(order);
~~~

Sau khi mọi consumer đã chuyển, các nhánh có thể được hợp nhất và flag được gỡ. Nếu giữ mãi, đội phải bảo trì hai đường dữ liệu, test cả hai và có nguy cơ bật nhầm legacy behavior sau này.

Exit criteria nên bao gồm:
- Tất cả consumer còn hỗ trợ đã chuyển.
- Event/data cũ có xử lý replay/backfill.
- Logic mới đã đủ ổn định.
- Removal PR xóa cả flag, code path, tests, config, docs.
- Không còn dependency chỉ phục vụ branch cũ.

## 16. Ghi rõ tiêu chí gỡ bỏ theo từng loại biện pháp

| Loại tạm | Tiêu chí thoát tối thiểu |
|---|---|
| `--add-opens` | Dependency được sửa/nâng; test pass không cần flag trên JDK target |
| Dependency pin | Upstream version được xác minh; security/API/ABI tests pass |
| Binary Jakarta transformer | Có upstream Jakarta artifact hoặc source rebuild; runtime/integration tests pass |
| Legacy API adapter | Không còn consumer cũ; schema/event replay plan hoàn tất |
| Dual-write | Dữ liệu đã reconcile; một source of truth; failure handling được chứng minh |
| Feature flag migration | Cohort 100% trên nhánh mới; rollback/data risk được giải; xóa branch cũ |
| Test quarantine | Test chạy lại hoặc thay bằng test tương đương có coverage được phê duyệt |
| GC/JVM tuning workaround | Performance benchmark trên runtime target cho thấy không còn cần |
| Agent dynamic-loading workaround | Startup agent/mock strategy được cấu hình đúng; test pass khi không dynamic attach |
| Temporary config alias | Không còn process nào đọc key cũ; env/Helm/config service đã chuyển |

### 16.1. Bằng chứng gỡ bỏ không phải “không còn lỗi trong 1 ngày”

Tùy workaround, cần các bằng chứng như:
- CI pass trên đúng JDK/framework matrix.
- Contract tests v1/v2 và integration tests.
- Bytecode/dependency checks.
- Runtime canary metrics.
- Security negative tests.
- Database reconciliation.
- No unsupported flags trong startup configs.
- Build artifact checksum và deployed version xác định.

Một kết luận “bỏ flag, test local pass” chưa đủ khi flag được áp cả production và bug chỉ xuất hiện dưới workload hiếm.

## 17. Kế hoạch tháo bỏ an toàn theo hai bước

Đối với workaround ảnh hưởng production, nên chia:

**Bước 1: Thử vô hiệu hóa có kiểm soát**
- Tạo môi trường/staging tương đương.
- Bỏ workaround hoặc bật nhánh mới cho canary.
- Chạy test, theo dõi logs/metrics và business invariants.
- Có đường rollback rõ.

**Bước 2: Xóa hoàn toàn**
- Bỏ code/flag/config/dependency/transformer.
- Xóa old compatibility paths và tests liên quan theo policy.
- Kiểm tra không còn reference runtime/build/deployment.
- Cập nhật register/ticket và tài liệu vận hành.
- Deploy đúng các môi trường nằm trong scope.
- Đóng biện pháp sau khi có evidence.

### 17.1. Tránh bỏ sớm khi còn consumer hoặc dữ liệu cũ

Nếu adapter phục vụ event v1, “không thấy traffic v1 hôm nay” chưa chứng minh nó không cần. Có thể còn:
- Dead-letter queue có event cũ.
- Consumer batch chạy hàng tuần.
- Mobile/partner client chưa nâng.
- Cache/session chứa schema cũ.
- Replay từ backup.
- Workflow retry có thời gian lưu dài.

Exit cần xét **retention, replay, support window và contract của consumer bên ngoài**.

### 17.2. Rollback removal có thể khác rollback app

Nếu bỏ adapter và đồng thời xóa schema cũ, rollback binary có thể không còn an toàn. Cần định nghĩa:
- Mốc trước/sau khi xóa dữ liệu cũ.
- Có backfill hoặc reverse adapter không.
- Khi nào change trở thành forward-only.
- Ai phê duyệt điểm không quay lại.
- Backup/restore/reconciliation plan khi cần.

Đừng lấy “có thể redeploy JAR cũ” làm bằng chứng toàn bộ hệ thống rollback được.

## 18. Theo dõi deadline và báo cáo cho người phụ trách

Mỗi sprint/release hoặc cadence phù hợp, migration lead nên có một bảng:

| ID | Biện pháp | DRI | Scope | Expiry | Trạng thái | Hành động tiếp |
|---|---|---|---|---|---|---|
| JAVA-MIG-042 | Opens cho LegacyMapper | Platform/JVM | CI test | 2027-01-15 | Active | Nâng thư viện |
| JAVA-MIG-057 | Event v1 bridge | Messaging | Orders/Billing | 2027-02-28 | Active | Đo consumer v1 còn lại |
| JAVA-MIG-061 | Pin ORM build plugin | Build infra | 2 modules | 2027-01-31 | Under review | Test plugin mới |
| JAVA-MIG-073 | Feature flag serializer | Orders | Canary | 2026-12-20 | Removal planned | Mở removal PR |

**Ngày và ID trên là ví dụ.** Dashboard cần link đến register/ticket thực, không làm nguồn dữ liệu thứ hai tự cập nhật thủ công.

### 18.1. Chỉ số quản trị hữu ích

- Số workaround active theo service/team/category.
- Số workaround quá hạn.
- Số ngoại lệ high-risk đang active.
- Thời gian tồn tại trung vị và lâu nhất.
- Số gia hạn/exception.
- Số workaround gỡ trong mỗi release.
- Số workaround không có DRI hoặc exit criteria.
- Tỷ lệ CI/ticket status nhất quán với runtime thực.

Không tối ưu số lượng theo cách khuyến khích xóa record ảo. **Giảm workaround phải đi kèm giảm rủi ro và gỡ implementation thật**.

### 18.2. Review cadence theo mức rủi ro

Ví dụ chính sách:
- High/critical: review mỗi release hoặc theo cadence security approval.
- Medium: review hàng sprint/tháng.
- Low: review theo chu kỳ release được phê duyệt.
- Upcoming expiry: nhắc trước một khoảng đủ để hoàn thành removal task.
- Overdue: escalate và ra quyết định cụ thể.

Không tự áp các mốc này như quy định bắt buộc của mọi tổ chức. Ngưỡng/cadence nên lấy từ risk policy và tốc độ release thực tế.

## 19. Gia hạn một workaround thế nào cho có trách nhiệm?

Một trường hợp thực tế: upstream thư viện hẹn phát hành bản Jakarta-compatible nhưng trễ, trong khi service phải duy trì hoạt động.

Đơn gia hạn nên trả lời:
1. Hạn cũ là khi nào?
2. Vì sao exit chưa đạt?
3. Scope hiện tại và rủi ro có đổi?
4. Có workaround thay thế ít rủi ro hơn không?
5. Có security/support deadline nào đang đến gần?
6. Cần gia hạn bao lâu và tại sao?
7. Kiểm soát bù trừ mới là gì?
8. Ai phê duyệt và khi nào review lại?
9. Có mốc trung gian nào chứng minh đang tiến triển?

### 19.1. Mẫu nội dung gia hạn

~~~text
Extension Request: JAVA-MIG-042
Previous expiry: 2027-01-15
Proposed expiry: 2027-02-15
Reason: Upstream release candidate còn lỗi trên JDK 21 test workload.
Scope: Chỉ CI integration-test; không đổi.
Risk delta: Không tăng quyền production.
Compensating controls: Pin test image và scan dependency.
Evidence: Upstream issue, failed CI run và compatibility report.
Owner: platform-jvm DRI
Approver: migration lead
Next checkpoint: 2027-01-31
Exit: Nâng library + bỏ --add-opens + test JDK matrix pass.
~~~

**Không biến extension thành cách hợp thức hóa trì hoãn vô hạn.** Nếu một ngoại lệ liên tục gia hạn, cần đánh giá lại thiết kế: thay thư viện, tách service, tăng hỗ trợ upstream hoặc chọn migration strategy khác.

## 20. Phân biệt workaround phù hợp với từng environment

Một vấn đề có thể có giải pháp tạm khác nhau theo environment:

| Environment | Ví dụ biện pháp | Ràng buộc |
|---|---|---|
| Local developer | Tạm chọn JDK cũ để chạy codegen | Không dùng artifact chưa xác minh ở production |
| CI | Startup agent cho test, quarantine test có kiểm soát | Không che test failures |
| Staging | Adapter/feature flag để thử contract mới | Representative workload/data |
| Production canary | Chỉ bật cho tenant/cohort giới hạn | Business metric alerts và rollback |
| Production general | Chỉ biện pháp đã được phê duyệt | Scope/time/risk rõ và kiểm soát chặt |

Một giải pháp chỉ được thử trong CI không tự động đủ điều kiện để đưa vào production. Ngược lại, workaround production cần được kiểm tra trên staging/CI để removal có bằng chứng.

### 20.1. Không để test-only JVM flag lẫn vào service launcher

Ví dụ test fork dùng `-javaagent` hoặc `--add-opens` để hỗ trợ mocking/legacy test framework. Những option này không nên được copy sang `JAVA_TOOL_OPTIONS` của production image chỉ vì chúng làm CI pass.

Ghi rõ:
- JVM nào cần flag.
- Tại task/process nào.
- Điều kiện khi nào nó cần xuất hiện.
- Config source chính xác.
- Cách xác minh nó **không** xuất hiện ngoài scope.

## 21. Tích hợp register với PR/release process

Một pull request thêm workaround nên có mẫu thông tin:

~~~text
Temporary Measure ID:
Migration blocker:
Why permanent fix cannot be done now:
Exact scope:
  - repository/module:
  - service/process:
  - JDK/framework versions:
  - environments:
  - excluded environments:
Technical DRI:
Owning team / backup:
Risk assessment:
Compensating controls:
Introduced by PR:
Created on:
Next review:
Expiry:
Exit trigger:
Removal ticket:
Tests/evidence:
Rollback plan:
Approvers:
~~~

### 21.1. Code review phải nhìn thấy đánh đổi

Reviewer nên xác nhận:
- Workaround thực sự giải quyết blocker đang nêu.
- Có giải pháp ít rủi ro hơn bị bỏ qua không.
- Scope có bị quá rộng?
- Deadline có hợp lý và gắn milestone?
- Owner có quyền và capacity thực hiện?
- Exit test có thể thực hiện trên JDK target?
- CI/monitoring có phát hiện regression?
- Có ảnh hưởng tới data/security/contract consumer cũ không?

Không đánh giá một patch chỉ dựa vào việc build xanh nếu nó thêm quyền rộng hoặc tắt test.

### 21.2. Release notes và runbook

Nếu workaround ảnh hưởng production behavior, release notes/runbook cần nêu:
- Option, flag hoặc adapter nào được bật.
- Phạm vi traffic và deployment.
- Known limitation.
- Signals to monitor.
- Rollback/cutoff conditions.
- DRI/on-call escalation.
- Link đến register ID/ADR.

Không nhất thiết đưa chi tiết bảo mật nhạy cảm vào release notes công khai; ghi ở tài liệu nội bộ có quyền kiểm soát.

## 22. Kết hợp workaround với kế hoạch migration nhiều giai đoạn

Ví dụ:

~~~text
Phase A: Inventory + baseline
   |
   v
Phase B: Temporary bridge được phê duyệt
   |
   v
Phase C: Deploy JDK mới qua canary
   |
   v
Phase D: Nâng dependencies, chuyển consumers/data
   |
   v
Phase E: Gỡ bridge, bỏ flags, xóa legacy paths
   |
   v
Phase F: Verify + close temporary measures
~~~

Một workaround không nên tồn tại bên ngoài kế hoạch này như một công việc “sẽ làm sau”. Gắn exit deadline của nó vào milestone cụ thể:
- Nâng dependency ở sprint nào.
- Consumer cũ hết support khi nào.
- Data migration/backfill xong khi nào.
- Contract tests nào phải pass.
- Feature flag cleanup vào release nào.

### 22.1. Critical path và phụ thuộc giữa teams

Giả sử bỏ event v1 bridge phụ thuộc:
- Billing nâng consumer.
- CRM partner xác nhận contract mới.
- Kafka retention/replay window đã xử lý.
- Orders ngừng phát schema cũ.

DRI của bridge không tự hoàn tất nếu các team khác chưa làm. Vì vậy record nên có **dependency tickets và owners**, đưa lên migration board để Prime/migration lead điều phối. Nhưng vẫn phải có một DRI chịu trách nhiệm **theo dõi và báo cáo tiến độ của biện pháp**.

## 23. Ví dụ thực tế 1: --add-opens phục vụ test trên JDK mới

**Bối cảnh:** khi nâng build/test sang JDK 21, một integration test dùng thư viện `LegacyMapper` ném `InaccessibleObjectException`. Đội chưa thể nâng thư viện trong cùng release.

**Phương án tạm:** truyền `--add-opens` chỉ cho integration test JVM.

### 23.1. Phạm vi

~~~text
Measure: JAVA-MIG-101
Repository: orders-platform
Module: integration-tests
JDK: 21 HotSpot
Environment: CI, staging test runner
Excluded: production, general developer launcher
Root cause: legacy reflection vào java.base/java.lang
Risk: mở reflective access trong test process
~~~

### 23.2. Chủ sở hữu và thời hạn

~~~text
DRI: JVM migration engineer (owner xác định theo directory)
Owning team: Platform
Removal ticket: MIG-1012
Review: mỗi sprint
Expiry: 2027-01-15 (minh họa)
Exit: upgrade LegacyMapper, xóa opens flag,
      chạy integration tests JDK 21 và xác nhận không còn exception
~~~

### 23.3. Cách triển khai và gỡ

Nếu dùng Gradle, flag phải nằm tại **task chạy JVM test** chứ không tự động ở production `JAVA_TOOL_OPTIONS`. Ví dụ vị trí đặt option (DSL minh họa):

~~~groovy
tasks.named('integrationTest', Test) {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

Một project thật cần khai báo task `integrationTest` và các configurations phù hợp. Khi upstream library được sửa:
1. Xóa dòng flag.
2. Chạy test matrix trên JDK target.
3. Kiểm soát log/exception.
4. Merge removal PR.
5. Xác minh artifact/deployment không còn option.
6. Đóng ticket và record.

### 23.4. Điều không nên làm

- Thêm flag vào tất cả JVM trên host.
- Dùng `--add-opens` như cách sửa API đã bị xóa.
- Copy flag sang production không review.
- Xóa test gây lỗi thay vì xử lý dependency.
- Gia hạn vô thời hạn vì “không còn ai nhớ lý do”.

## 24. Ví dụ thực tế 2: hỗ trợ tạm hai định dạng event

**Bối cảnh:** Orders producer mới đã sẵn sàng, nhưng Billing consumer cũ cần thêm một chu kỳ release. Hai bên không thể deploy cùng lúc.

**Phương án tạm:** consumer mới nhận cả event schema v1 và v2, producer giữ contract v1 cho consumer cũ trong support window.

### 24.1. Scope và rủi ro

~~~text
Measure: JAVA-MIG-118
Systems: Orders producer, Billing consumer
Topic: order-events
Schemas: v1, v2
Environments: staging, production
Traffic: all order events during coexistence window
Owner: Messaging platform DRI
Dependency: Billing consumer upgrade
Risks: schema drift, duplicate processing, out-of-order events
Controls: schema registry, idempotency, DLQ monitoring, contract tests
Expiry: 2027-02-28 (minh họa)
~~~

Không đủ khi chỉ nói “Bridge sẽ xóa sau khi v2 deploy”. Exit cần:
- Billing v1 đã ngừng xử lý production.
- Không còn batch/partner consumer cũ ngoài support window.
- Event v1 còn trong retention/DLQ được xử lý hoặc có replay path hợp lệ.
- Không còn traffic trên đường bridge, qua một measurement window được chấp nhận.
- Test sau khi xóa bridge chứng minh business invariants.
- Rollback policy không còn yêu cầu producer/consumer v1.

### 24.2. Dấu hiệu cần quan sát

- Số event v1/v2 được xử lý.
- Consumer lag và DLQ.
- Duplicate event IDs.
- Mapping failures/unknown enums.
- Reconciliation mismatches.
- Retry và timeout.
- Version client/service của consumer.

Chỉ khi các điều kiện được xác nhận, mới có thể xóa adapter và đóng measure.

## 25. Ví dụ thực tế 3: Jakarta artifact transformer tạm

**Bối cảnh:** một library internal còn `javax.servlet.*` trong compiled bytecode, trong khi ứng dụng mới chuyển sang Jakarta Servlet.

**Phương án tạm:** dùng binary transformer với rule set đã pin để tạo artifact tương thích namespace. Đây có thể là bước đệm trong khi team library sửa source.

Bản ghi cần mô tả:

~~~text
ID: JAVA-MIG-132
Input: legacy-filter-2.3.jar (checksum...)
Output: legacy-filter-2.3-jakarta-transformed.jar (checksum...)
Tool: Eclipse Transformer version pinned
Rules: Jakarta migration rule set pinned
Scope: only Orders WAR; not all shared libraries
JDK/Server: JDK 21, Jakarta Servlet container supported version
Owner: Shared Libraries DRI
Risk: reflection, ServiceLoader, XML, signatures, EOL library
Expiry: 2027-03-31 (minh họa)
Exit: official Jakarta release + contract/integration tests
~~~

Không dùng tên “-jakarta” để che rằng artifact là fork/transform chưa chính thức. Phải có provenance và scan dependency theo policy, đồng thời không tự tin rằng namespace đổi đồng nghĩa behavior tương thích.

## 26. Khi nào phải dừng migration thay vì thêm workaround?

Workaround chỉ phù hợp khi mức rủi ro còn lại chấp nhận được và có đường thoát. Nên xem xét **block rollout** nếu:

- Không có owner có năng lực/thẩm quyền gỡ.
- Không biết rõ phạm vi hoặc hệ thống bị tác động.
- Thay đổi bỏ qua kiểm soát bảo mật cốt lõi.
- Không có cách phát hiện data corruption hoặc duplicate transaction.
- Compatibility adapter có mapping nghiệp vụ mơ hồ.
- Một binary transformer không cho ra artifact có provenance đáng tin.
- Dependency unsupported đang chứa rủi ro security không thể giảm ở scope hiện tại.
- Việc gỡ workaround làm mất rollback path mà không có kế hoạch thay thế.
- Dữ liệu mới không thể được consumer cũ đọc nhưng vẫn dự kiến rollback về cũ.
- Ngày hết hạn liên tục lùi mà không có tiến bộ.

**Áp lực deadline không tự làm một workaround an toàn.** Cần thay kế hoạch migration: tách scope, nâng dependency trước, chấp nhận chuyển một phần hệ thống, hoặc điều chỉnh ngày release.

## 27. Mẫu báo cáo ngắn cho release review

Báo cáo một biện pháp nên trả lời:

~~~text
ID: JAVA-MIG-042
Status: active
What: Temporary --add-opens for LegacyMapper
Scope: orders-integration CI/staging test JVM, JDK 17/21
Owner: Platform/JVM DRI
Created: 2026-11-12
Next review: 2026-12-01
Expires: 2027-01-15
Current risk: medium; test-only reflective access
Latest evidence: JDK 21 integration tests pass with workaround
Exit blocker: upstream mapper version upgrade pending
Next action: validate candidate library without flag
Removal ticket: MIG-567
Decision needed: none / escalate if upstream misses milestone
~~~

Một báo cáo tốt **không trùng lặp toàn bộ ADR**, nhưng cho người ra quyết định thấy ngay scope, owner, deadline, rủi ro và hành động tiếp theo.

## 28. Những sai lầm thường gặp

- **Chỉ ghi “TODO remove” trong code:** không có owner/deadline/exit.
- **Chỉ ghi owner là tên team:** không có DRI chịu trách nhiệm.
- **Chỉ ghi ngày hết hạn:** không có tiêu chí kỹ thuật để tháo.
- **Chỉ ghi “khi upstream sửa”:** không có ngày review/escalation.
- **Gắn “temporary” cho thiết kế đã trở thành vĩnh viễn:** không ra quyết định kiến trúc chính thức.
- **Không giới hạn môi trường:** option test bị copy sang production.
- **Không ghi JDK/framework version:** workaround bị áp nhầm sau upgrade.
- **Dùng một flag JVM rộng cho mọi service:** tăng security exposure.
- **Gia hạn âm thầm bằng sửa YAML:** mất audit và risk approval.
- **Đóng ticket khi code được merge:** runtime/deployment có thể vẫn giữ workaround.
- **Dùng test quarantine mà không báo test bị skip:** tạo cảm giác CI xanh giả.
- **Pin dependency không có CVE/upstream review:** kéo dài rủi ro.
- **Gỡ adapter ngay khi traffic mới chiếm 100%:** có thể còn event replay/consumer cũ.
- **Xóa record sau khi đóng:** mất provenance và lý do quyết định.
- **Deadline được tính khác timezone giữa pipeline:** có thể chặn hoặc bỏ qua sai ngày.
- **Chỉ dùng grep mà không xem runtime effective flags:** configuration có thể đến từ nơi ngoài repo.
- **Dùng CI expiry gate không có quy trình xử lý ngoại lệ:** tạo áp lực xóa record/đổi ngày không kiểm soát.
- **Workaround làm giảm security nhưng chỉ review kỹ thuật:** thiếu risk approval.
- **Bỏ qua rollback/data compatibility:** gỡ workaround có thể làm hệ thống không quay về bản cũ.
- **Đo số workaround giảm mà không xác minh implementation đã gỡ:** dashboard đẹp nhưng rủi ro còn.
- **Đặt runtime “time bomb” theo ngày mà không thiết kế:** hết hạn có thể gây outage.
- **Không ghi compensating controls:** những rủi ro chưa xử lý không được giám sát.

## 29. Checklist chấp nhận biện pháp tạm thời

Trước khi bật một workaround:

- [ ] Có ID duy nhất và link đến issue/PR.
- [ ] Có lý do rõ và blocker migration có thể tái hiện.
- [ ] Đã cân nhắc phương án sửa nguyên nhân gốc hoặc ít rủi ro hơn.
- [ ] Scope ghi service/module/environment/runtime/JDK versions cụ thể.
- [ ] Có **explicit exclusions** để ngăn copy workaround quá phạm vi.
- [ ] Có một technical DRI, owning team và backup.
- [ ] Có risk/security approver khi ảnh hưởng policy.
- [ ] Có risk assessment về bảo mật, dữ liệu, độ tin cậy và vận hành.
- [ ] Có compensating controls phù hợp.
- [ ] Có created date, next review date và expiry date.
- [ ] Có exit trigger/criteria kiểm chứng được.
- [ ] Có removal task và dependency owners.
- [ ] Có rollback plan và cách phát hiện regression.
- [ ] Có cách quan sát workaround còn được dùng hay không.
- [ ] Có cơ chế CI/ticket/dashboard nhắc hoặc enforce deadline.
- [ ] Không chứa secret/PII trong register hoặc logs.
- [ ] Đã ghi rõ status và approval reference.

Trước khi đóng một workaround:

- [ ] Exit condition đã được đáp ứng hoặc thay bằng quyết định kiến trúc được phê duyệt.
- [ ] Đã bỏ đúng code, flag, config, dependency và nhánh legacy liên quan.
- [ ] Đã test khi không còn workaround trên JDK/framework target.
- [ ] Đã xác minh runtime effective config/deployment không còn workaround.
- [ ] Với schema/adapter, đã xét hết consumer cũ, retention/replay và rollback window.
- [ ] Đã có canary/integration/security/performance evidence theo rủi ro.
- [ ] Đã cập nhật runbook, docs và sample configs.
- [ ] Đã đóng ticket/register với removal commit/deployment version.
- [ ] Đã lưu audit trail thay vì xóa toàn bộ dấu vết.

## 30. Bài tập áp dụng cho một dự án Java migration

**Bối cảnh:** nhóm nâng dịch vụ Order từ JDK 11 lên JDK 21, đồng thời chuyển Spring Boot 2 sang 3. Có ba blocker:

1. Một thư viện dùng deep reflection cần mở package JDK trong test.
2. Một filter legacy chỉ có bản `javax.servlet`, chưa có Jakarta release.
3. Billing còn consumer đọc event v1.

**Yêu cầu:** thiết kế register cho ba temporary measures, không gộp tất cả thành một “Java 21 workaround”.

### 30.1. Gợi ý tách bản ghi

| ID | Biện pháp | Scope | DRI | Exit |
|---|---|---|---|---|
| JAVA-MIG-201 | `--add-opens` trong test JVM | Integration tests JDK 21, không production | Platform/JVM | Upgrade library và pass không flag |
| JAVA-MIG-202 | Transform/filter Jakarta tạm | Orders WAR/Tomcat target | Shared libraries | Có filter Jakarta chính thức |
| JAVA-MIG-203 | Event v1/v2 adapter | Orders/Billing message flow | Messaging | Billing consumer v1 retired + replay plan |

Mỗi measure có expiry, risk, approval, ticket và tests riêng, vì **chúng phụ thuộc những người khác nhau và có thể được gỡ ở những thời điểm khác nhau**.

### 30.2. Các câu hỏi để hoàn thiện bài tập

- Biện pháp nào cần security approval?
- Biện pháp nào ảnh hưởng production runtime?
- Nếu library filter có CVE mới, ai quyết định dừng transformer?
- Khi adapter event bị gỡ, những message trong DLQ/retention xử lý ra sao?
- Nếu JDK 21 test fail sau khi bỏ `--add-opens`, exit criteria nào chưa đạt?
- Có thể dùng CI để phát hiện flag test đã bị copy vào production config không?
- Nếu owner nghỉ việc trước hạn, quy trình chuyển giao trách nhiệm là gì?
- Workaround nào có thể cần gia hạn, và ai có thẩm quyền phê duyệt?

Bài tập không có một bộ deadline cố định cho mọi tổ chức; điểm cần chứng minh là **mỗi ngoại lệ có cấu trúc quyết định độc lập và vòng đời đóng được**.

## 31. Tài liệu tham khảo và nguồn vận dụng

- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): bối cảnh module encapsulation và lý do một số thư viện legacy cần được nâng.
- [Oracle Java Launcher Reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): tham số JVM như `--add-opens`, cần đối chiếu theo JDK release.
- [OpenJDK JEP 451 — Dynamic Agent Loading](https://openjdk.org/jeps/451): cân nhắc agent permissions và test infrastructure trên JDK 21+.
- [OpenRewrite](https://docs.openrewrite.org/): công cụ sửa source/dependency có cấu trúc để thay workaround bằng migration chính thức.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): binary transformation và giới hạn artifact migration.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration): chuyển một số web artifacts từ Java EE sang Jakarta.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API/platform target và compatibility của hệ sinh thái Jakarta.
- [Semantic Versioning](https://semver.org/): tư duy quản lý thay đổi API versions; không thay thế compatibility tests.
- [Google SRE Workbook — Eliminating Toil](https://sre.google/workbook/eliminating-toil/): bối cảnh quản lý công việc thủ công kéo dài và rủi ro vận hành.
- [Architecture Decision Records](https://adr.github.io/): hình thức ghi quyết định và hệ quả kiến trúc.

Các tài liệu này là nguồn định hướng, không biến register mẫu thành một tiêu chuẩn bắt buộc. Mỗi tổ chức cần áp dụng policy quản trị thay đổi, security, incident và release riêng. Khi tham khảo JVM/framework/tooling, luôn dùng tài liệu của **đúng version đã pin** trong dự án.

## 32. Kết luận

**Một biện pháp tạm thời chỉ an toàn trong migration khi nó có giới hạn và có người chịu trách nhiệm kết thúc.** Trước khi thêm một JVM flag, dependency pin, compatibility adapter, binary transformer hoặc feature flag, cần ghi **phạm vi chính xác, DRI, owner team, deadline, exit criteria, rủi ro, kiểm soát bù trừ và kế hoạch rollback**. Không có những thông tin đó, một cách giải quyết blocker hôm nay có thể trở thành dependency không ai hiểu vào năm sau.

Quy trình thực hành là **đề xuất → đánh giá rủi ro → phê duyệt → triển khai trong scope hẹp → giám sát/review → gỡ có kiểm chứng → lưu bằng chứng và đóng**. Dùng register/ADR, issue tracking và CI guardrails để các ngoại lệ không bị quên; dùng integration/contract/security tests để chứng minh việc tháo bỏ không phá compatibility. Khi mọi workaround đều có owner và thời hạn rõ, tổ chức có thể chuyển hệ thống Java từng bước mà không đánh đổi khả năng bảo trì, bảo mật và vận hành lâu dài.
