# Tích hợp thường xuyên cùng tiêu chí chất lượng chung

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **nhiều nhóm hoàn tất phần việc riêng không đồng nghĩa sản phẩm đã có Increment tích hợp, sử dụng được** và phân biệt merge, tích hợp, triển khai, phát hành.
2. Tổ chức **tích hợp thường xuyên** với các thay đổi nhỏ, hợp đồng API, kiểm thử tự động và cơ chế phản hồi nhanh.
3. Phân biệt **Acceptance Criteria, Definition of Done (DoD), chính sách tích hợp, điều kiện phát hành**; vận dụng DoD chung khi nhiều Scrum Team cùng làm một sản phẩm.
4. Nhận diện phụ thuộc xuyên nhóm về nghiệp vụ, API, schema, xác thực, môi trường, quyền quyết định và vận hành.
5. Áp dụng theo rủi ro các thực hành **Continuous Integration, contract testing, integration testing, kiểm thử end-to-end trọng yếu, tương thích ngược, migration và feature flags**.
6. Đo **work item age, cycle time, blocked time, lỗi tích hợp, rework và sức khỏe pipeline** để cải tiến toàn hệ thống, không xếp hạng cá nhân.
7. Thực hành xây dựng kế hoạch tích hợp nhiều nhóm với **bằng chứng Done, quyền sở hữu và guardrail an toàn** rõ ràng.

## 1. Khi mọi nhóm đều báo “Done” nhưng người dùng vẫn chưa sử dụng được

Một nền tảng học trực tuyến xây chức năng **“Tiếp tục học”** bằng ba nhóm:

- **Nhóm Trải nghiệm học viên:** Tạo nút và hành trình mở lại bài học.
- **Nhóm Tiến độ học:** Xây API đọc/ghi tiến độ và xử lý dữ liệu.
- **Nhóm Danh tính và quyền:** Xác thực tài khoản, kiểm tra quyền khóa học.

Cuối Sprint, cả ba nhóm đều có nhiều ticket “Done”. Tuy nhiên khi ghép:

- Giao diện mong trường dữ liệu khác với response API.
- API tin một mã tài khoản do client gửi lên thay vì danh tính xác thực.
- Hai thiết bị lưu tiến độ gần nhau làm kết quả bị ghi lùi.
- Môi trường test không có cấu hình phiên phù hợp.
- Chưa ai chạy được toàn bộ luồng mở bài với quyền thật của người học.

**Các phần hoàn thành cục bộ không tự tạo ra một khả năng sản phẩm hoàn chỉnh**. Người dùng cần cả UI, dữ liệu, quyền và trạng thái lỗi hoạt động cùng nhau.

> **Phối hợp nhiều nhóm có chất lượng không phải khiến mọi nhóm bận rộn, mà là giúp sản phẩm tạo được những phần tích hợp, sử dụng được và có giá trị một cách thường xuyên.**

Trong Agile, việc giao tăng dần và lấy phản hồi sớm chỉ có ý nghĩa khi phần được giao **thực sự kiểm chứng được qua các ranh giới cần thiết**. Nếu chờ đến cuối quý mới tích hợp, đội đã giữ bất định quá lâu.

## 2. Tích hợp thường xuyên thực sự nghĩa là gì?

**Tích hợp thường xuyên (frequent integration)** là đưa những thay đổi nhỏ vào trạng thái phối hợp được với sản phẩm hiện có, kiểm tra các hợp đồng và hành vi liên quan, nhận phản hồi khi sai lệch còn nhỏ và khắc phục trước khi chúng tích tụ.

**Continuous Integration (CI)** là thực hành kỹ thuật gần với mục tiêu đó: hợp nhất thay đổi thường xuyên vào codebase chung và tự động xây dựng/kiểm thử. Nhưng **một pipeline xanh không chứng minh mọi hành vi liên nhóm đều đúng**, nếu pipeline chưa có những bài test cần thiết.

### Phân biệt những trạng thái dễ nhầm

| Trạng thái | Đã xảy ra điều gì? | Chưa thể suy ra |
| --- | --- | --- |
| **Code đã merge** | Thay đổi vào dòng code tích hợp | API và UI đã tương thích hoặc test đã đủ |
| **Build xanh** | Code biên dịch/đóng gói được trong cấu hình kiểm tra | Phân quyền, nghiệp vụ hoặc dữ liệu an toàn |
| **Tích hợp hành vi** | Những thành phần cần thiết hoạt động cùng nhau ở kịch bản đã kiểm tra | Toàn bộ rủi ro và nhu cầu người dùng đã được bao phủ |
| **Increment đạt DoD** | Phần sản phẩm sử dụng được, đáp ứng chuẩn chất lượng chung | Đã phát hành tới người dùng |
| **Đã deploy** | Artifact được đưa tới môi trường đích | Tính năng đã được mở cho người dùng hoặc đạt outcome |
| **Đã release** | Khả năng sản phẩm được cung cấp cho đối tượng theo chính sách | Người dùng chắc chắn nhận được kết quả mong muốn |

Một request trả HTTP 200 chưa chứng minh học viên đã **mở đúng bài còn quyền**. Cần liên kết bằng chứng kỹ thuật với hành vi sản phẩm.

### Tích hợp không chỉ là việc của nhóm “Integration”

Nhóm nền tảng có thể sở hữu công cụ CI và môi trường. Tuy nhiên, nếu mọi nhóm giao code cho một nhóm khác chịu trách nhiệm “lắp ráp” cuối kỳ, điểm nghẽn chỉ chuyển thành **một hàng chờ mới**.

Các nhóm làm chức năng vẫn phải phối hợp về hợp đồng, chất lượng và trách nhiệm kiểm chứng. Không cần một người làm tất cả, nhưng **không được có một khoảng trống trách nhiệm** ở chỗ các thành phần gặp nhau.

## 3. Vì sao tích hợp sớm lại quan trọng?

| Rủi ro nếu tích hợp muộn | Cơ chế giảm rủi ro khi tích hợp sớm | Bằng chứng nên xem |
| --- | --- | --- |
| Contract giữa UI và API khác nhau | Kiểm tra schema, trạng thái lỗi và ngữ nghĩa trước khi code quá nhiều | Contract test, kiểm tra client–provider |
| Nhiều nhánh phát triển xa codebase chung | Tích hợp những thay đổi nhỏ, phát hiện xung đột sớm | Tuổi nhánh, thời gian khắc phục build |
| Schema dữ liệu không tương thích | Thử nhiều phiên bản và migration theo giai đoạn | Test cũ–mới, đối soát và khả năng khôi phục |
| Phân quyền không được thực thi tại API | Kiểm tra ranh giới thật cùng cơ chế danh tính | Integration/security test |
| Nhiều lỗi đến cuối Sprint mới thấy | Phản hồi test khi thay đổi còn nhỏ | Lỗi phát hiện muộn, rework, blocked time |
| Môi trường chỉ chạy được từng service | Tạo luồng tích hợp và kiểm tra dữ liệu cấu hình thường xuyên | Test liên nhóm, khả năng tái hiện lỗi |
| Các nhóm tối ưu số ticket riêng | Kiểm tra lát cắt sản phẩm thực sự dùng được | Increment đạt DoD, task success |

**Tích hợp sớm không tự sửa một yêu cầu sai.** Nếu các nhóm hiểu khác nhau về “bài gần nhất”, tích hợp tốt vẫn có thể tạo ra một giải pháp kỹ thuật đúng theo giả định sai. Cần làm rõ **giá trị và quy tắc nghiệp vụ** song song với tích hợp.

## 4. Scrum nhiều nhóm: một sản phẩm cần một nghĩa “Done”

Trong Scrum, nếu nhiều Scrum Team cùng làm trên **một sản phẩm**, các đội cùng tập trung vào sản phẩm đó và chia sẻ **Product Goal, Product Backlog, Product Owner**. Họ phải **cùng định nghĩa và tuân thủ một Definition of Done**.

**Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng của sản phẩm.

### Những nguyên tắc quan trọng

- Nếu tổ chức có tiêu chuẩn DoD, Scrum Team phải tuân thủ **ít nhất** tiêu chuẩn đó. Nếu tổ chức không có, Scrum Team cần định nghĩa DoD phù hợp sản phẩm.
- Nhiều Scrum Team cùng làm một sản phẩm phải có **DoD chung** để phần việc của các đội có thể kết hợp thành Increment.
- Product Backlog Item chưa đạt DoD **không được coi là một phần của Increment hoàn thành**.
- Một Sprint có thể tạo **nhiều Increment**; mỗi Increment bổ sung vào sản phẩm và phải được kiểm chứng để tất cả hoạt động cùng nhau.
- Sprint Review không phải cổng bắt buộc để release; Increment đạt DoD có thể được giao trước khi Sprint kết thúc nếu đủ điều kiện liên quan.

### Tại sao không nên đặt “Sprint tích hợp” ở cuối?

Nếu nhiều Sprint trước chỉ tạo code chưa thể sử dụng, việc gọi chúng là “Done” không phản ánh đúng trạng thái Increment. Đội cần xem lại cách chia lát cắt, phụ thuộc, kiểm thử và chính sách tích hợp để có **phần sản phẩm sử dụng được ngay trong quá trình phát triển**.

Không phải mọi chức năng lớn đều hoàn thành trong một Sprint; có thể chia thành các lát cắt nhỏ thực sự dùng được và đáp ứng DoD, hoặc minh bạch phần chưa hoàn thành.

### Khi không dùng Scrum đầy đủ

Một đội Kanban flow-first vẫn cần **chính sách Done và chất lượng chung** cho cùng sản phẩm/hợp đồng, dù không dùng thuật ngữ cam kết Scrum. Tích hợp thường xuyên không bắt buộc Sprint, nhưng luôn cần biết **khi nào phần mềm thực sự sẵn sàng**.

## 5. Acceptance Criteria, DoD, integration policy và release criteria

Những khái niệm này hỗ trợ nhau nhưng không dùng thay nhau:

| Khái niệm | Phạm vi | Ví dụ “Tiếp tục học” |
| --- | --- | --- |
| **Acceptance Criteria (AC)** | Hành vi của một item cụ thể | Nếu khóa mới nhất hết quyền thì không được mở trái quyền |
| **Definition of Done** | Chất lượng chung của Increment | Đã tích hợp, test/kiểm soát dữ liệu liên quan đạt, không vi phạm chuẩn sản phẩm |
| **Integration policy** | Điều kiện kỹ thuật và phối hợp khi đưa thay đổi vào dòng chung | Contract test, kiểm tra CI và review theo chính sách đạt |
| **Release criteria** | Điều kiện deployment/rollout tới người dùng | Migration, giám sát, khôi phục, phê duyệt theo nghĩa vụ sẵn sàng |
| **Product Goal/outcome** | Kết quả người dùng hoặc tổ chức hướng tới | Học viên học liên tục, không mất tiến độ và không xem dữ liệu sai tài khoản |

### Hai tình huống

**Tình huống A:** UI demo được, API trả bài nhưng integration test phân quyền thất bại. Không được gọi Increment này đạt DoD nếu quyền là tiêu chuẩn bắt buộc; hoàn tất code cục bộ không thay thế chất lượng.

**Tình huống B:** Increment đã đạt DoD nhưng chưa đến lịch migration dữ liệu hoặc phê duyệt release theo chính sách. Có thể **Done nhưng chưa release**. Không nên đồng nhất DoD với mọi quyết định kinh doanh về ngày phát hành.

## 6. Thiết kế một DoD chung có thể kiểm chứng

DoD tốt nêu **trạng thái và chất lượng cần có**, không chỉ những thao tác hình thức.

### Một DoD minh họa cho sản phẩm học tập

| Nhóm chất lượng | Tiêu chí áp dụng khi có liên quan | Bằng chứng có thể dùng |
| --- | --- | --- |
| **Nghiệp vụ** | Đạt AC, kể cả các ngoại lệ quan trọng | Acceptance tests và ví dụ được xác nhận |
| **Tích hợp** | Thay đổi hoạt động với những Increment hiện có và các contract cần hỗ trợ | Contract/integration tests, build |
| **Bảo mật** | Không truy cập trái quyền; danh tính từ nguồn xác thực có thẩm quyền | Security review/test theo rủi ro |
| **Dữ liệu** | Retry, concurrency và migration không làm hỏng dữ liệu trong trường hợp liên quan | Test giao dịch/đối soát |
| **Kỹ thuật** | Kiểm tra tự động và review bắt buộc đạt, không che lỗi quan trọng | CI, test reports, PR |
| **Vận hành** | Có khả năng theo dõi, ứng phó với lỗi khi thay đổi cần đến | Telemetry, runbook, smoke test |
| **Duy trì** | Những quyết định cần tái sử dụng đã được truyền đạt phù hợp | Test có nghĩa, tài liệu quyết định ngắn |

**Đây là DoD ví dụ, không phải mẫu bắt buộc từ Scrum Guide.** Đội phải chọn những tiêu chuẩn chất lượng từ sản phẩm, tổ chức, nghĩa vụ và rủi ro thực. “Khi có liên quan” không được dùng để bỏ kiểm tra bắt buộc.

### Một DoD chung không buộc mọi nhóm làm giống nhau

Nhóm UI có thể kiểm tra accessibility và ứng xử giao diện; nhóm API kiểm tra hợp đồng và dữ liệu; nhóm danh tính kiểm tra phân quyền. **Kỹ thuật khác nhau vẫn đóng góp vào cùng trạng thái Increment**.

Tránh hai cực đoan:

- **“Mỗi nhóm Done theo nghĩa riêng”** làm mất khả năng ghép thành Increment.
- **“Mọi nhóm phải chạy mọi thủ tục giống nhau”** có thể tạo gánh nặng mà không cải thiện rủi ro liên quan.

Một tiêu chí ví dụ “migration được kiểm chứng khi thay đổi schema” không buộc một story chỉ sửa nhãn phải diễn tập migration riêng.

## 7. Chia lát cắt theo giá trị thay vì chỉ chia tầng công nghệ

Phân công thuần theo thành phần dễ tạo nhiều hàng chờ:

~~~text
UI dựng toàn bộ giao diện -> API xong toàn bộ endpoint ->
Identity thêm quyền -> Test ghép ở cuối -> Release
~~~

Một hướng khác là chọn **lát cắt nhỏ xuyên qua các phần cần thiết**:

1. Tài khoản đã đăng nhập nhìn thấy entry point phù hợp.
2. Tài khoản chỉ có thể mở bài gần nhất **còn quyền**.
3. Khi không có dữ liệu hợp lệ, ứng dụng hiển thị đúng trạng thái.
4. Khi API lỗi hoặc lưu tiến độ thất bại, không báo trạng thái thành công sai.

### So sánh

| Cách chia thiên về thành phần | Cách chia hướng tích hợp |
| --- | --- |
| UI xong trước rồi chờ API | Chốt contract nhỏ giữa UI và API từ sớm |
| Backend trả nhiều endpoint trong một đợt | Mỗi endpoint quan trọng được kiểm tra cùng consumer |
| Quyền truy cập gắn vào sát release | Kiểm soát quyền đi cùng từng lát cắt |
| Test end-to-end khi tất cả nhóm đã xong | Kiểm tra sớm một đường đi nhỏ nhưng dùng được |
| Tối ưu số ticket Done từng nhóm | Ưu tiên Increment đạt DoD và phản hồi người dùng |

Không phải mọi phụ thuộc có thể biến mất. Lát cắt cần giữ ranh giới dữ liệu, hợp đồng, quyền chuyên môn và an toàn. **Chia nhỏ không đồng nghĩa chia thành những mẩu code chưa dùng được rồi gọi Done**.

## 8. Bản đồ phụ thuộc và quyền ra quyết định

Một số chậm trễ xảy ra vì câu hỏi **không có chủ thể được quyền trả lời**, chứ không chỉ thiếu người lập trình.

~~~mermaid
flowchart LR
    U["Học viên"] --> UI["Nhóm Trải nghiệm: UI"]
    UI --> API["Nhóm Tiến độ: API"]
    API --> ID["Nhóm Danh tính: quyền/phiên"]
    API --> DATA["Kho tiến độ"]
    UI --> OBS["Tín hiệu sử dụng"]
    API --> OPS["Vận hành và giám sát"]
    ID --> OPS
    DATA --> OPS
~~~

Đây là sơ đồ **phụ thuộc minh họa**, không bắt buộc hệ thống thật phải có các service hoặc đường gọi như vậy.

### Bảng quyết định

| Câu hỏi | Chủ thể có trách nhiệm đưa ra quyết định theo bối cảnh | Cần tham khảo |
| --- | --- | --- |
| “Bài gần nhất” có nghĩa gì? | Người có thẩm quyền sản phẩm, ví dụ Product Owner | Developer, tester, nghiên cứu người dùng |
| API trả gì khi không có bài hợp lệ? | Nhóm API phối hợp người quyết định nghiệp vụ | UI, tester, người quản lý contract |
| Nếu quyền học vừa bị thu hồi? | Người có thẩm quyền chính sách/bảo mật cùng đội thực hiện | UI, API, vận hành |
| Client cũ còn được hỗ trợ bao lâu? | Chủ thể quản lý sản phẩm/hợp đồng | Mobile, API, vận hành |
| Môi trường tích hợp ai duy trì? | Đơn vị nền tảng hoặc trách nhiệm kỹ thuật được giao | Các nhóm sử dụng |
| Khi nào Increment Done? | Các Scrum Team cùng sản phẩm định nghĩa và tuân thủ DoD chung | Chuyên môn chất lượng/bảo mật/vận hành phù hợp |
| Ai dừng rollout khi sự cố? | Vai trò được trao quyền theo chính sách ứng phó | Các nhóm dịch vụ liên quan |

Không phải mọi câu hỏi đều phải qua một kiến trúc sư, Scrum Master hoặc Product Owner. **Đúng quyền quyết định, đúng người tham gia, đúng thời điểm** giúp giảm hàng chờ và vẫn bảo vệ trách nhiệm.

## 9. Nhịp tích hợp thường xuyên thực tế

Không có một ngưỡng “mỗi developer phải merge N lần/ngày” bắt buộc trong Scrum hoặc Agile. Tần suất nên đủ để **hạn chế thay đổi lớn và phát hiện sai sớm**, theo độ tin cậy của công cụ và rủi ro sản phẩm.

### Chu trình từ ý định đến Increment

1. **Trước code lớn:** Chốt ví dụ nghiệp vụ, hợp đồng, quyền và trường hợp lỗi quan trọng.
2. **Thiết kế thay đổi nhỏ:** Chọn lát cắt có thể kiểm tra sớm, cân nhắc tương thích cũ–mới.
3. **Kiểm tra nhanh tại nguồn:** Unit tests, static checks, code review phù hợp.
4. **Tích hợp vào dòng code chung:** Chạy CI và các contract tests liên quan.
5. **Kiểm chứng nhiều thành phần:** Auth/API/DB/cache, phiên bản client, một vài hành trình end-to-end trọng yếu.
6. **Xác nhận DoD:** Bằng chứng chất lượng đủ để có Increment dùng được.
7. **Deploy/release nếu đủ điều kiện:** Theo kế hoạch rủi ro và quyền quyết định; quan sát phản hồi.

### Sơ đồ vòng phản hồi

~~~mermaid
flowchart TD
    A["AC + contract + rủi ro"] --> B["Thay đổi nhỏ và test"]
    B --> C["CI: build/kiểm tra nhanh"]
    C --> D{"Đạt?"}
    D -- "Không" --> B
    D -- "Có" --> E["Merge theo chính sách"]
    E --> F["Contract + integration tests"]
    F --> G{"Hoạt động cùng nhau?"}
    G -- "Không" --> H["Cùng khoanh vùng và sửa"]
    H --> B
    G -- "Có" --> I["Kiểm chứng DoD"]
    I --> J["Increment có thể sử dụng"]
    J --> K["Release khi đủ điều kiện"]
    K --> L["Phản hồi sản phẩm và vận hành"]
    L --> A
~~~

Sơ đồ không quy định mọi test bắt buộc chạy đúng một lần theo thứ tự. Có thể chạy contract tests trước merge và nhiều kiểm tra song song; mục tiêu là **phản hồi nhanh, đáng tin với đúng ranh giới rủi ro**.

## 10. Pipeline CI: từ đèn xanh tới bằng chứng đáng tin

| Lớp kiểm tra | Mục tiêu | Không thay được |
| --- | --- | --- |
| **Format/lint/static checks** | Bắt vấn đề đơn giản, nhất quán code | Hiểu hành vi và rủi ro dữ liệu |
| **Unit tests** | Kiểm tra quy tắc nhỏ, trường hợp biên | Auth/API/DB thực |
| **Build/package** | Biên dịch và đóng gói | Kiểm chứng người dùng thao tác đúng |
| **Contract tests** | Provider–consumer hiểu cùng request/response/enum/error | Toàn bộ tích hợp và dữ liệu thật |
| **Integration tests** | Tương tác qua ranh giới service/DB/cache | Mọi hành trình người dùng và mọi rủi ro |
| **Selected E2E tests** | Luồng quan trọng qua sản phẩm | Thay unit tests cho mọi trường hợp |
| **Security/data checks** | Giữ phân quyền, secret và toàn vẹn dữ liệu liên quan | Nghĩa vụ đánh giá/chính sách khác nếu áp dụng |
| **Deployment verification** | Smoke test, health, migration và telemetry phù hợp | Kết luận đạt outcome dài hạn |

### Pipeline khái niệm

~~~yaml
# Minh họa ý tưởng, không phải cú pháp CI chạy trực tiếp.
on_small_change:
  - build_and_lint
  - unit_tests
  - changed_contract_tests
  - relevant_security_checks
before_merge:
  - required_review
  - required_checks_green
after_integration:
  - integration_tests_on_representative_environment
  - selected_end_to_end_tests
before_release:
  - verify_definition_of_done
  - verify_migration_and_recovery_plan_when_needed
  - verify_observability_and_release_policy
~~~

### Khi pipeline đỏ

Đừng chỉ chạy lại cho đến khi hiện màu xanh. Cần:

- Phân biệt **lỗi sản phẩm, lệch contract, môi trường, test flaky hoặc cấu hình**.
- Ghi người phối hợp và mức rủi ro theo chính sách.
- Khắc phục thay đổi nhỏ khi còn dễ xác định phạm vi.
- Nếu test flaky phải tạm cách ly, ghi lý do, phương pháp kiểm chứng thay thế nếu cần, chủ sở hữu và mốc sửa; **không coi skipped test quan trọng là chất lượng đạt**.

**Pipeline xanh chỉ có giá trị theo độ đúng của những kiểm tra đang được thực hiện**.

## 11. Chiến lược nhánh: giảm kích thước lô thay đổi

Nhánh sống nhiều tuần có thể tích lũy sai lệch API và dữ liệu. Khi merge, việc sửa conflict lớn và phát hiện bug thường khó hơn.

| Cách | Có thể hữu ích khi | Cần bảo vệ |
| --- | --- | --- |
| **Nhánh ngắn, PR tập trung** | Muốn review nhanh và tích hợp thường xuyên | CI và reviewer có năng lực đáp ứng |
| **Trunk-based development** | Muốn giảm sai lệch nhánh, phản hồi tích hợp thường xuyên | Test đáng tin, xử lý main đỏ, kỹ thuật cho phần chưa mở |
| **Branch by abstraction** | Đổi implementation lớn nhưng muốn giữ giao diện ổn định | Đường cũ–mới hoạt động trong thời gian chuyển |
| **Feature flag** | Tách deploy code với bật tính năng | Test trạng thái quan trọng, quyền bật/tắt, cleanup |
| **Nhánh dài vì ràng buộc đặc biệt** | Có lý do kỹ thuật hoặc quản trị cụ thể | Kế hoạch đồng bộ, test và tích hợp trước lô lớn |

Scrum không bắt buộc dùng trunk-based hoặc một chiến lược branch cụ thể. Nguyên tắc có thể áp dụng rộng hơn là **thay đổi nhỏ, giảm khoảng cách với codebase chung và phản hồi sớm**.

### Feature flag không phải “miễn DoD”

Flag có thể che khả năng chưa công bố, nhưng không tự chứng minh **code an toàn hoặc Increment đã đáp ứng DoD**. Những cấu hình cần được hỗ trợ phải được kiểm tra, nhất là ranh giới quyền và dữ liệu. Flag UI không thể thay phân quyền ở server.

## 12. API contract: giao diện chung mang cả ngữ nghĩa nghiệp vụ

**API contract** không chỉ là tên field. Nó còn gồm request, response, trạng thái lỗi, quyền, trường tùy chọn, ý nghĩa thời gian, version và chính sách tương thích.

### Ví dụ hợp đồng minh họa

~~~text
GET /v1/me/resume-lesson
Authorization: phiên truy cập hợp lệ theo hệ thống

200 OK:
{
  "courseId": "course-x",
  "lessonId": "lesson-4",
  "progressVersion": 17
}

204 No Content:
  Không có bài học hợp lệ theo quy tắc nghiệp vụ.

401 Unauthorized:
  Thiếu phiên hợp lệ.

503 Service Unavailable:
  Không thể kiểm tra/đọc dữ liệu theo chính sách.
~~~

**Đây là hợp đồng giả định phục vụ bài học.** Tên endpoint, mã HTTP và cách diễn đạt trạng thái rỗng cần được các nhóm có thẩm quyền thống nhất trong sản phẩm thật.

### Câu hỏi phải làm rõ

1. “Gần nhất” là theo thời gian client hay thời gian máy chủ đã xác nhận?
2. Nếu cùng timestamp, có quy tắc tie-break không?
3. Nếu khóa vừa bị thu hồi quyền, kết quả phải ra sao?
4. Nếu quyền không xác minh được, có nhầm với “không có tiến độ” không?
5. Nếu API timeout, client có retry an toàn không?
6. Client cũ có hiểu unknown field hoặc enum value mới không?
7. Có nhiều tenant hoặc tài khoản trên một thiết bị không?
8. Provider và consumer có chạy contract test với **phiên bản được hỗ trợ** không?

### Vì sao chỉ dùng mock là chưa đủ?

UI có thể luôn mock response dùng trường “lessonId”, trong khi provider thật trả “lesson_id”. Test của từng nhóm riêng vẫn xanh. **Contract test được xác minh với provider và integration test qua ranh giới thật** có cơ hội phát hiện khác biệt sớm.

Mock vẫn hữu ích để phản hồi nhanh và giả lập lỗi, nhưng không thay thế bằng chứng từ hợp đồng mà các bên thực sự cùng tuân thủ.

## 13. Quản lý thay đổi hợp đồng tương thích ngược

**Backward compatibility** nghĩa là thay đổi mới tiếp tục phục vụ những phiên bản consumer cũ **đang được chính sách hỗ trợ**. Không nhất thiết phải hỗ trợ mọi phiên bản mãi mãi.

| Thay đổi | Rủi ro | Cách tiếp cận |
| --- | --- | --- |
| Thêm trường tùy chọn | Có thể tương thích nếu client bỏ qua trường lạ | Kiểm tra strict parser và consumer cũ |
| Đổi tên trường bắt buộc | Có nguy cơ phá vỡ | Chuyển tiếp hai trường hoặc versioning phù hợp |
| Đổi kiểu number thành string | Có thể làm parse lỗi | Test dữ liệu và hợp đồng ở cả hai phía |
| Đổi ý nghĩa trường nhưng giữ tên | Có thể sai nghiệp vụ dù JSON vẫn hợp lệ | Kiểm tra ví dụ hành vi và contract semantic |
| Thêm giá trị enum | Tùy cách xử lý unknown values | Định nghĩa fallback an toàn |
| Đổi mã lỗi/trạng thái rỗng | Có thể làm UI hiển thị sai | Test trường hợp lỗi và client cũ |
| Thêm yêu cầu xác thực | Cần bảo vệ an toàn nhưng có thể ảnh hưởng consumer | Lộ trình chuyển đổi và phê duyệt phù hợp |

### Quy trình chuyển đổi

1. Liệt kê consumer và version cần hỗ trợ, bao gồm mobile/đối tác.
2. Thống nhất ngữ nghĩa thay đổi, ngoại lệ, quyền và thời điểm chuyển.
3. Thay theo hướng tương thích khi khả thi.
4. Chạy contract tests với provider và các consumer được hỗ trợ.
5. Quan sát usage/version thích hợp để biết việc chuyển đổi đã diễn ra.
6. Chỉ loại bỏ đường cũ khi đủ điều kiện và đúng người có quyền quyết định.

Nếu không thể tương thích hoàn toàn, cần kế hoạch **versioning, phối hợp release, thông báo và biện pháp khôi phục**. Không được tự coi một thay đổi là an toàn vì API owner đã merge.

## 14. Schema dữ liệu: tích hợp tăng dần, không đánh cược vào rollback

Thay đổi schema có thể phá cả phiên bản code cũ và mới, đặc biệt khi nhiều nhóm deploy khác thời điểm.

### Chiến lược expand – migrate – contract

1. **Expand:** Thêm cấu trúc mới mà các phiên bản còn được hỗ trợ vẫn có thể hoạt động. Giữ đường đọc/ghi cũ khi cần và có kiểm soát.
2. **Migrate:** Chuyển hoặc đối soát dữ liệu theo từng bước; đo lỗi, kiểm tra tương thích và xử lý record bất thường.
3. **Contract:** Chỉ loại cấu trúc cũ sau khi consumer chuyển đổi, dữ liệu được xác nhận và có quyết định phù hợp.

### Ví dụ

API lưu tiến độ muốn thêm số phiên bản “progressVersion” để tránh cập nhật cũ ghi đè dữ liệu mới. Trong giai đoạn có client cũ chưa gửi version:

- Xác định quy tắc nghiệp vụ xử lý client cũ, không đoán last-write-wins luôn đúng.
- Thêm schema và hành vi trung gian theo chiến lược tương thích được chọn.
- Có test đọc/ghi với client cũ–mới và các tình huống retry/concurrency.
- Di chuyển dữ liệu có kiểm chứng và ghi nhận bất thường.
- Chỉ xóa đường cũ khi điều kiện hỗ trợ đã kết thúc.

### Guardrail bắt buộc theo rủi ro

- Có phương án **backup, kiểm thử phục hồi và đối soát** phù hợp.
- Không để migration làm lộ hoặc mất dữ liệu cá nhân.
- Không coi rollback code là cách hoàn tác mọi thay đổi dữ liệu.
- Không dùng dữ liệu thật ở môi trường thử ngoài quyền và chính sách.

Đây là **một chiến lược tham khảo**, không phải hướng dẫn chạy lệnh migration cho sản phẩm thật. Quyết định phụ thuộc loại kho dữ liệu, kiến trúc và nghĩa vụ.

## 15. Bảo mật xuyên ranh giới: nơi “mỗi nhóm đã test” vẫn có thể sai

Ba tình huống nguy hiểm:

1. UI gửi mã tài khoản do người dùng tùy chỉnh; API tin mã đó thay vì danh tính đã xác thực.
2. Dịch vụ tiến độ trả dữ liệu cho khóa học hết quyền vì giả định “nhóm UI sẽ ẩn nút”.
3. Response chậm của tài khoản A đến sau khi B đăng nhập trên cùng thiết bị và ghi vào cache của B.

### Một ma trận kiểm chứng an toàn

| Ranh giới | Điều cần bảo vệ | Bằng chứng phù hợp |
| --- | --- | --- |
| UI ↔ API | Không tin UI để phân quyền thay server | Gọi API trực tiếp với tài khoản khác |
| API ↔ Identity | Danh tính/phiên/quyền có ý nghĩa thống nhất | Test hết quyền, đổi phiên, session expiry |
| API ↔ DB/cache | Không trộn dữ liệu tài khoản hoặc tenant | Test cache isolation, retry, concurrency |
| Deployment ↔ vận hành | Không lộ token/bí mật trong log, có tín hiệu sự cố | Kiểm tra telemetry và runbook theo chính sách |

**Đội không được tự cho phép rủi ro dữ liệu nghiêm trọng chỉ để kịp ngày release.** Người có thẩm quyền bảo mật/chất lượng phải tham gia khi chính sách yêu cầu; AC và DoD cần bảo vệ những điều không thể thương lượng.

Nếu không xác minh được quyền, hành vi an toàn **không phải giả định người dùng được phép xem dữ liệu**. Cần thống nhất cách phản hồi để UI không biến lỗi dịch vụ thành trạng thái “chưa học bao giờ”.

## 16. Kiểm thử nhiều lớp cho hành vi xuyên nhóm

Chiến lược kiểm thử cần đưa **sai lệch đến đúng nơi có thể phát hiện sớm**. Không nên đẩy mọi tình huống vào một bộ end-to-end tests khổng lồ và chậm, cũng không nên chỉ chạy unit tests vì chúng dễ xanh.

### Ma trận từ rủi ro đến bằng chứng

| Rủi ro | Phản hồi sớm | Kiểm tra ở ranh giới thật | End-to-end hoặc sau phát hành |
| --- | --- | --- | --- |
| Chọn sai bài gần nhất | Unit test quy tắc thời gian, quyền | API + dữ liệu test có điều kiện | Mở đúng bài từ trang chủ |
| Tên trường/mã lỗi API lệch | Schema/contract check | Provider–consumer contract test | Smoke test phiên bản client liên quan |
| Đọc dữ liệu tài khoản khác | Unit test logic lọc đúng | Auth/API/cache security tests | A đăng xuất → B đăng nhập và truy cập trực tiếp |
| Lưu tiến độ bị lặp hoặc ghi lùi | Unit test idempotency/version rule | DB + retry/concurrency integration test | Thao tác đa thiết bị nếu cần |
| API đối tác timeout | Unit test xử lý trạng thái lỗi | Integration test timeout/fallback | UI không báo nhầm “không có dữ liệu” |
| Nút khó sử dụng | Test semantics, accessibility | UI kết nối contract thật | Usability test với nhóm người dùng phù hợp |
| Migration phá client cũ | Data/schema tests | Cũ–mới đồng thời | Quan sát phiên bản và cơ chế khôi phục |

### Tại sao không kiểm thử mọi thứ ở E2E?

Một E2E có thể bị ảnh hưởng bởi mạng, trình duyệt, môi trường, dữ liệu và sự phối hợp của nhiều service. Nếu một lỗi logic đơn giản cũng chỉ được phát hiện qua E2E dài, đội nhận phản hồi muộn, khó khoanh vùng và test dễ flaky.

**Lựa chọn có chủ đích:**

- **Unit tests:** Nhiều trường hợp logic nhỏ, nhanh và ổn định.
- **Contract tests:** Bảo vệ những lời hứa ở giao diện giữa consumer/provider.
- **Integration tests:** Kiểm tra giao dịch, xác thực, cache, dữ liệu và phụ thuộc thực.
- **Một số E2E tests trọng yếu:** Kiểm chứng hành trình người dùng qua sản phẩm.
- **Exploratory, performance, accessibility, security testing:** Dùng theo loại rủi ro cần khám phá/kiểm chứng.

Không có tỷ lệ bắt buộc kiểu “70% unit, 20% integration, 10% E2E” trong Scrum/Agile. Độ sâu phải phù hợp với rủi ro, tính tin cậy của test và thời gian phản hồi.

## 17. Môi trường tích hợp và dữ liệu thử: hạ tầng cho phối hợp

Tích hợp không thể thường xuyên nếu môi trường chung liên tục bị đổi cấu hình, dữ liệu thử bị nhóm khác xóa hoặc không ai biết phiên bản nào đang chạy.

### Những vấn đề thường gặp

- UI nghĩ đang gọi phiên bản API mới nhưng môi trường vẫn deploy phiên bản cũ.
- Người kiểm thử không thể tái hiện quyền học của hai tài khoản vì chỉ có một tài khoản test chung.
- Test của nhóm A tạo dữ liệu rồi nhóm B xóa dữ liệu giữa lúc chạy.
- Secret/token thật bị sao chép vào log debug trong môi trường thử.
- Một người duy nhất có quyền deploy môi trường, tạo hàng chờ và blocked time.
- CI thất bại ngẫu nhiên; developer phải rerun nhiều lần, khiến tín hiệu mất giá trị.

### Chính sách tối thiểu cần rõ

| Nội dung | Câu hỏi cần trả lời |
| --- | --- |
| **Phiên bản và cấu hình** | Biết được service, client, schema, flag nào đang chạy không? |
| **Quyền tự phục vụ** | Ai deploy/reset được, khi nào cần phối hợp, có môi trường tạm không? |
| **Dữ liệu** | Ai tạo/xóa, làm sao đảm bảo tính độc lập và ẩn danh hợp lệ? |
| **Secrets** | Môi trường thử có dùng tài khoản/khóa đúng chính sách không? |
| **Phiên bản hỗ trợ** | Đã kiểm tra client cũ–mới hoặc consumer ngoài chưa? |
| **Xử lý lỗi** | Lỗi test, môi trường, dữ liệu và sản phẩm được phân loại thế nào? |
| **Khôi phục** | Khi môi trường hỏng, ai chịu trách nhiệm và trong thời gian nào theo nhu cầu? |

### Test flaky là vấn đề chất lượng của vòng phản hồi

Một test lúc xanh lúc đỏ không có lý do rõ sẽ khiến:

1. Developer bỏ qua tín hiệu nghiêm trọng.
2. PR chờ review/merge lâu hơn.
3. Nhóm có động cơ bỏ hoặc cách ly test vô thời hạn.
4. Thay đổi không thể tích hợp thường xuyên.

Đội cần đo, phân loại nguyên nhân, sửa race trong test, ổn định fixture/timing và có chính sách tạm cách ly **rõ ràng, có người chịu trách nhiệm**. Không được coi “chạy lại đến khi xanh” là kiểm chứng đáng tin.

## 18. Quản lý phụ thuộc trước khi chúng trở thành blocker

Một cuộc họp status nhiều người có thể giúp ai cũng biết “đang chờ API”, nhưng chưa tạo ra quyết định hoặc khả năng tiếp tục.

### Bản đồ phụ thuộc minh họa

| Phụ thuộc | Nhóm đang cần | Nhóm hoặc vai trò cung cấp | Định nghĩa sẵn sàng | Tín hiệu rủi ro |
| --- | --- | --- | --- | --- |
| Contract bài gần nhất | UI | Tiến độ học | Request/response/mã lỗi/quyền được chốt | Chưa rõ trạng thái rỗng |
| Quy tắc quyền học | UI + API | Danh tính/sản phẩm | Ví dụ hết quyền, đổi tài khoản, test | Hai cách hiểu khác nhau |
| Môi trường tích hợp | Các nhóm | Nền tảng/vận hành | Phiên bản, cấu hình, dữ liệu và quyền phù hợp | Test flaky, chờ deploy |
| Migration | API/client | Dữ liệu và vận hành | Kế hoạch tương thích, đối soát, khôi phục | Client cũ còn dùng |
| Telemetry release | Sản phẩm/vận hành | UI + API | Event có nghĩa, quyền riêng tư được giữ | Success ghi sai lúc request mới bắt đầu |

### Khi còn bất định

Đội có thể:

- Chọn một **lát cắt đủ rõ** để kiểm chứng độc lập.
- Viết ví dụ contract hoặc test trước, thay vì code theo giả định ngầm.
- Dùng mock/stub **dựa trên contract đã được xác nhận**, không tự chế response.
- Timebox một spike để trả lời câu hỏi kỹ thuật; đầu ra là bằng chứng và quyết định, **không tự gọi prototype chưa đạt DoD là Increment**.
- Làm rõ ai có quyền chốt và thời điểm cần phản hồi; ghi tác động nếu bị chậm.

### Theo dõi blocked đúng ý nghĩa

Một item được đánh dấu blocked khi có trở ngại cụ thể khiến nó không thể tiến theo chính sách đã thống nhất. Cần ghi:

- Item nào và ranh giới bị chặn.
- Nguyên nhân, thời điểm bắt đầu, người có thể gỡ hoặc quyết định.
- Phần nào có thể tiếp tục an toàn mà không tạo rework.
- Điều kiện kết thúc blocker và thời điểm xem lại.

**Thời gian blocked không tự bị trừ khỏi tuổi công việc (work item age)**; age của item chưa Done vẫn tăng. Khi có nhiều blocker cùng lúc, phải tính hợp các khoảng thời gian nếu muốn biết thời gian thực bị chặn, tránh cộng trùng.

## 19. Điều phối qua Scrum, Kanban và các vòng phản hồi

Các cơ chế phối hợp chỉ hữu ích khi giúp giải quyết **quyết định hoặc trở ngại thật**, không phải để tăng số cuộc họp.

### Khi nhiều Scrum Team cùng một sản phẩm

- **Product Goal, Product Backlog, Product Owner chung** giữ hướng giá trị nhất quán.
- **DoD chung** giúp Increment của các đội có cùng nghĩa chất lượng.
- **Refinement và Sprint Planning:** Làm rõ lát cắt, hợp đồng, rủi ro và thứ tự ưu tiên; chọn công việc có khả năng hoàn tất với DoD.
- **Daily Scrum của từng đội:** Developers kiểm tra tiến triển tới Sprint Goal và thích nghi Sprint Backlog; thông tin phụ thuộc có thể cần kênh phối hợp trực tiếp bổ sung.
- **Sprint Review:** Kiểm tra Increment và phản hồi sản phẩm, không chỉ báo % task hoàn thành từng đội.
- **Sprint Retrospective:** Cải tiến tích hợp, chất lượng, phối hợp và điểm nghẽn; vấn đề liên đội có thể cần cuộc trao đổi phù hợp.

### Scrum of Scrums

**Scrum of Scrums** có thể là một cách phối hợp nhiều nhóm, nhưng **không phải sự kiện bắt buộc trong Scrum Guide**. Nếu chỉ đọc bảng status cho quản lý, nó dễ trở thành chi phí phối hợp. Nếu giúp các nhóm giải quyết phụ thuộc, điều phối quyết định và điều chỉnh kế hoạch thì có thể có ích.

### Các hình thức thay thế hoặc bổ sung

| Cơ chế | Khi đáng dùng | Quyết định đầu ra |
| --- | --- | --- |
| **Contract huddle** ngắn | API/schema/quyền đang có cách hiểu khác | Ví dụ, owner, version và test cần có |
| **Integration huddle** | Pipeline chung đỏ hoặc một lát cắt bị chặn | Ai sửa gì, cách xác minh, thời điểm xem lại |
| **Kanban flow review** | Nhiều item già, blocked hoặc rework do phụ thuộc | Điều chỉnh WIP, ưu tiên hỗ trợ, chính sách luồng |
| **Community of Practice** | Nhiều nhóm gặp vấn đề CI/test giống nhau | Chia sẻ cơ chế và thử nghiệm có điều kiện |
| **Decision record/ADR** | Quyết định kỹ thuật khó đảo ngược, ảnh hưởng nhiều nhóm | Lý do, lựa chọn, hệ quả và mốc xem lại |
| **Post-incident review** | Sự cố xuyên nhóm | Bằng chứng, biện pháp an toàn và cải tiến không quy lỗi |

Không cần áp dụng tất cả. **Giảm thời gian chờ quyết định** quan trọng hơn số người tham dự hội nghị.

## 20. Đồng thuận giá trị và đồng thuận kỹ thuật khác nhau

Một sản phẩm nhiều nhóm cần đồng thuận ở hai lớp:

1. **Giá trị:** Product Goal, thứ tự backlog, phạm vi kết quả người dùng và tác động kinh doanh.
2. **Kỹ thuật/chất lượng:** Contract, CI, DoD, dữ liệu, phân quyền, tính tương thích, điều kiện vận hành.

### Khi nhu cầu phát hành nhanh xung đột rủi ro

Product Owner muốn thử nút “Tiếp tục học” sớm nhưng API chưa xác minh được quyền sau khi thay tài khoản. Hai phản ứng đều không phù hợp:

> “Kinh doanh gấp nên bỏ kiểm tra quyền.”

> “Phải xây hết mọi chức năng đồng bộ video tương lai rồi mới cho người dùng dùng.”

Nhóm có thể **thu hẹp lát cắt**: chỉ mở bài gần nhất của tài khoản đã xác thực, quyền được kiểm tra; chưa đồng bộ từng giây của video. Lát cắt ít chức năng hơn nhưng **vẫn dùng được và đạt chất lượng**.

### Trách nhiệm và quyền

Trong Scrum, Product Owner chịu trách nhiệm giá trị và Product Backlog; Developers có trách nhiệm xây Increment theo DoD và lập/điều chỉnh kế hoạch Sprint; Scrum Master hỗ trợ hiệu quả Scrum Team. Người có thẩm quyền về bảo mật, vận hành, pháp lý hoặc hợp đồng vẫn tham gia những quyết định thuộc phạm vi của họ.

**Đồng thuận không đồng nghĩa mọi quyết định đều phải có chữ ký của tất cả mọi người.** Cần ranh giới quyền rõ để bảo vệ chất lượng mà không tạo nút thắt phê duyệt vô ích.

## 21. Tích hợp thường xuyên không đồng nghĩa release liên tục

| Khái niệm | Trọng tâm | Điều kiện cần |
| --- | --- | --- |
| **Continuous Integration** | Hợp nhất và kiểm chứng thay đổi thường xuyên | CI, codebase tích hợp, phản hồi và sửa lỗi nhanh |
| **Continuous Delivery** | Giữ phần mềm ở trạng thái có thể phát hành theo chính sách | Tự động hóa, DoD, đóng gói, chất lượng và kiểm soát release |
| **Continuous Deployment** | Tự động deploy những thay đổi đủ điều kiện tới môi trường đích theo chính sách | Kiểm soát kỹ thuật/vận hành và quyết định tự động hợp lệ |
| **Release** | Mở khả năng tới một nhóm người dùng | Quyết định sản phẩm, giám sát, quyền và điều kiện phát hành |

Đội có thể CI nhiều lần trong ngày nhưng chỉ release sau khi đạt nghĩa vụ đối tác hoặc mốc bảo trì. Điều đó không phủ nhận lợi ích tích hợp thường xuyên.

### Feature flag

Flag giúp tách deploy với bật tính năng nhưng cần:

- Chủ sở hữu flag, phạm vi đối tượng, điều kiện bật/tắt và kế hoạch cleanup.
- Test những tổ hợp flag được hỗ trợ, đặc biệt các ranh giới quyền/dữ liệu.
- Giám sát lỗi khi mở rộng rollout.
- Không coi flag là giải pháp cho code đã biết có lỗi bảo mật hoặc chưa đạt DoD.

### Rollback không hoàn tác mọi dữ liệu

Rollback code có thể phục hồi một lỗi giao diện, nhưng **không tự khôi phục dữ liệu đã bị migration sai hoặc ghi lùi**. Khi schema và nhiều service deploy khác thời điểm, cần đánh giá khả năng khôi phục thật, không chỉ có nút deploy version cũ.

## 22. Observability và phản hồi sau tích hợp

Môi trường production có lưu lượng, dữ liệu, client version và hành vi mà môi trường test không hoàn toàn mô phỏng. Cần **quan sát có trách nhiệm** để phát hiện sai lệch còn lại.

| Tín hiệu | Giúp phát hiện | Giới hạn diễn giải |
| --- | --- | --- |
| **API error rate** | Request lỗi hoặc dịch vụ không sẵn sàng | HTTP 200 có thể vẫn sai nghiệp vụ |
| **Latency phân vị** | Người dùng chịu độ trễ ở đuôi phân bố | Cần tải, môi trường và mẫu phù hợp |
| **Contract/compatibility failures** | Provider hoặc client version không tương thích | Test cần phản ánh version đang hỗ trợ |
| **Lỗi quyền/dữ liệu** | Rủi ro bảo mật và toàn vẹn nghiêm trọng | Không ghi dữ liệu nhạy cảm vào log quá mức |
| **Task success/funnel** | Người dùng có thực sự mở bài đúng không | Event có thể thiếu/sai; phải giữ quyền riêng tư |
| **Incident/khôi phục** | Khả năng phản ứng với sự cố | Đếm incident phụ thuộc năng lực phát hiện |
| **Blocked time/rework** | Phần chờ hoặc làm lại do ranh giới nhóm | Cần định nghĩa và tập item nhất quán |

**Monitoring sau release không thay cho kiểm thử trước release**, đặc biệt với rủi ro phân quyền và mất dữ liệu. Đội cần biết ai có quyền dừng rollout, ai khắc phục, làm sao liên hệ các nhóm và cách đối soát.

## 23. Đo hiệu quả tích hợp: nhìn toàn luồng sản phẩm

### Các chỉ số nên xem cùng nhau

| Nhóm | Chỉ số/tín hiệu ví dụ | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Kích thước thay đổi** | Tuổi nhánh, kích thước PR, khoảng cách giữa lần tích hợp | Có đang tích tụ lô lớn khó kiểm chứng? |
| **Sức khỏe CI** | Thời gian pipeline, lỗi được phân loại, flaky, thời gian sửa build | Phản hồi có nhanh và đáng tin? |
| **Dòng công việc** | WIP, throughput, work item age, cycle time, blocked duration | Lát cắt xuyên nhóm có tiến tới Done ổn định? |
| **Chất lượng tích hợp** | Lỗi contract, rework do API/schema, lỗi phát hiện muộn | Sai lệch được phát hiện sớm hơn không? |
| **Chất lượng vận hành** | Incident, ảnh hưởng dữ liệu, thời gian khôi phục | Có đánh đổi tốc độ bằng rủi ro? |
| **Giá trị sản phẩm** | Task success, phản hồi định tính, outcome | Increment đã phục vụ nhu cầu thật? |
| **Bền vững** | Overtime, phụ thuộc chuyên gia, độ gián đoạn | Có phải cải tiến được duy trì mà không kiệt sức? |

### Phép tính chờ phụ thuộc liên nhóm

Giả sử bốn item **đã Done** có dữ liệu đo thống nhất:

| Item | Cycle time | Thời gian chờ phụ thuộc |
| --- | ---: | ---: |
| A | 6 ngày | 2 ngày |
| B | 8 ngày | 3 ngày |
| C | 4 ngày | 1 ngày |
| D | 10 ngày | 4 ngày |
| **Tổng** | **28 ngày-item** | **10 ngày-item** |

Với những khoảng chờ không bị tính chồng lấp:

\[
\text{Tỷ lệ thời gian chờ trong tập} = \frac{10}{28}\times100\% \approx 35{,}7\%
\]

Trung vị cycle time của 4, 6, 8, 10 ngày là:

\[
\frac{6+8}{2}=7\ \text{ngày}
\]

**Không được diễn giải “35,7% thời gian chờ” thành “35,7% năng suất nhân sự bị mất”**. Đây là tổng duration của item, không phải giờ công; chờ một phần phụ thuộc không có nghĩa tất cả thành viên đều nhàn rỗi.

Bốn item quá ít để dự báo ổn định. Cần xem item chưa Done, loại công việc, cách đo và thời gian quan sát dài hơn.

### Tránh tối ưu sai

- Số merge nhiều không tự nghĩa giá trị cao.
- Throughput tăng do chia ticket nhỏ không tự nghĩa người dùng được phục vụ tốt hơn.
- Pipeline nhanh hơn nhưng bỏ test quan trọng có thể tăng lỗi production.
- Cycle time giảm vì loại item đang già khỏi mẫu có thể tạo ảo giác cải tiến.
- Không xếp hạng developer/nhóm theo số PR hoặc số bug đã sửa.

## 24. Tình huống xuyên suốt: ba nhóm xây “Tiếp tục học”

### 24.1. Mục tiêu và lát cắt

**Product Goal:**

> “Học viên có thể tiếp tục việc học trên thiết bị thường dùng một cách đáng tin cậy, không mất tiến độ đã xác nhận và không nhìn thấy dữ liệu của tài khoản khác.”

Ba nhóm cùng thực hiện một lát cắt:

> “Học viên đã đăng nhập mở được đúng bài gần nhất còn quyền từ trang chủ; trường hợp không có bài và lỗi phụ thuộc được hiển thị đúng.”

Một **Sprint Goal** có thể là:

> “Cung cấp đường đi tích hợp và an toàn từ trang chủ đến bài hợp lệ gần nhất, với phản hồi rõ khi không thể tiếp tục.”

Sprint Goal là mục tiêu để chọn và thích nghi công việc trong Sprint, không phải ba danh sách task độc lập theo nhóm.

### 24.2. Hợp đồng được thống nhất sớm

Trước khi code lớn, các nhóm chốt:

- Danh tính được lấy từ ngữ cảnh xác thực có thẩm quyền phía server.
- Quy tắc “gần nhất” và tie-break theo nghiệp vụ đã xác nhận.
- Quyền khóa học có thể bị thu hồi và cần kiểm tra phù hợp.
- API phân biệt **không có bài hợp lệ** với **không thể đọc dữ liệu**.
- Client có trạng thái loading, lỗi, không có dữ liệu rõ ràng.
- Có test đổi tài khoản cùng thiết bị và response cũ đến muộn.
- DoD chung và bằng chứng tích hợp được các nhóm hiểu giống nhau.

### 24.3. Lộ trình tích hợp thay vì chờ cuối Sprint

| Mốc minh họa | Thay đổi nhỏ | Kiểm chứng |
| --- | --- | --- |
| Bước 1 | Chốt AC, contract và quyền | Các nhóm dùng cùng ví dụ nghiệp vụ |
| Bước 2 | API trả trạng thái rỗng và dữ liệu thử theo contract | Provider–consumer contract test, UI smoke |
| Bước 3 | API tích hợp quyền và DB | Integration tests về đúng tài khoản/khóa còn quyền |
| Bước 4 | UI mở bài hợp lệ, xử lý lỗi | Một E2E quan trọng, kiểm tra accessibility |
| Bước 5 | Kiểm tra concurrency/cache/telemetry | Test response cũ, CI, review và DoD |
| Sau khi đủ điều kiện | Release theo chính sách | Guardrail dữ liệu, giám sát và phản hồi |

Đây là thứ tự học tập **minh họa**, không phải cam kết thời gian cứng hoặc một kiến trúc bắt buộc.

### 24.4. Một lỗi được phát hiện trước khi Done

Integration test phát hiện:

> A đăng xuất, B đăng nhập cùng thiết bị, response đọc tiến độ cũ của A đến muộn và có thể cập nhật giao diện của B.

**Các nhóm phối hợp xử lý:**

1. Tạo test tái hiện với dữ liệu tổng hợp và bảo vệ thông tin nhạy cảm.
2. Phân tích ranh giới session/cache và điểm API phải thực thi quyền.
3. Điều chỉnh thiết kế theo chính sách; không chỉ ẩn nội dung ở UI để che dữ liệu sai.
4. Chạy lại các security/integration/E2E tests liên quan, bảo đảm pipeline đáng tin.
5. Ghi quyết định và test hồi quy để tránh lỗi tương tự.

Lỗi được phát hiện **sớm** là cơ hội học hỏi và bảo vệ người dùng. **Bỏ qua lỗi hoặc gọi Done khi test còn thất bại** mới là hành động làm mất ý nghĩa chất lượng.

### 24.5. Một nhóm code xong, Increment chưa xong

Nhóm UI có thể ghi nhận phần việc kỹ thuật đã bàn giao; nhưng nếu API vẫn trả dữ liệu trái quyền, **lát cắt sản phẩm chưa đạt DoD**.

Cần làm rõ:

- Phần kỹ thuật nào đã tích hợp và kiểm chứng?
- Rủi ro nào khiến lát cắt chưa dùng được?
- Có lát cắt khác độc lập đã đạt DoD để giao không?
- Product Owner và Developers cần điều chỉnh phạm vi/dự báo Sprint Goal thế nào?

Không đánh tráo **hoàn thành component** với **hoàn thành Increment**.

### 24.6. Sau Sprint

Trong Sprint Review, đội cho thấy Increment và phản hồi thực tế, không chỉ tình trạng ticket của từng nhóm. Trong Retrospective, các nhóm xem **vì sao contract/cache chưa được thử sớm hơn**, có điểm nghẽn reviewer hay môi trường không, và cần thay đổi gì cho Sprint sau.

Đây là **thực nghiệm và cải tiến liên tục**, không chỉ là mở thêm cuộc họp báo cáo.

## 25. Tình huống thứ hai: mobile và API phát hành khác thời điểm

Mobile app có thể được người dùng giữ nhiều tuần trước khi cập nhật, trong khi backend deploy thường xuyên. Schema cũng phải chuyển đổi thận trọng để không phá dữ liệu.

### Các rủi ro

- API đổi field khiến mobile cũ không parse được.
- Schema mới làm API cũ không đọc/ghi được.
- Feature flag bật ở client nhưng backend chưa đáp ứng contract.
- Nhóm API không biết đối tác ngoài vẫn dùng version cũ.
- Rollback backend không phục hồi được dữ liệu migration sai.

### Phương án phối hợp có thể thử

1. Xác định các consumer và version đang **trong phạm vi hỗ trợ**.
2. Thay hợp đồng theo hướng tương thích khi khả thi, có kiểm thử cũ–mới.
3. Dùng chiến lược migration dữ liệu tăng dần và đối soát.
4. Đưa backend và client qua những mốc có thể kiểm chứng độc lập.
5. Chỉ bật khả năng mới khi đã đạt DoD và điều kiện release.
6. Theo dõi lỗi, phiên bản và tác động người dùng; có quyền dừng/mở rộng rollout rõ.
7. Dọn đường tương thích/feature flag cũ khi đã xác nhận không còn cần.

Không có một lịch phát hành bắt buộc cho mọi đội; vấn đề là **tương thích, chất lượng và quyền quyết định** phải tồn tại xuyên các nhịp khác nhau.

## 26. Kế hoạch thử nghiệm cải tiến tích hợp trong bốn tuần

### Tuần 1 — Làm rõ vấn đề và baseline

- Chọn một luồng người dùng đi qua nhiều nhóm.
- Vẽ start/finish và nơi item thường bị chặn.
- Thu dữ liệu ban đầu về integration failure, contract rework, work item age và pipeline flaky.
- So sánh DoD, quyền quyết định, dữ liệu và hợp đồng hiện tại.

**Đầu ra:** Bản đồ phụ thuộc và một giả thuyết đo được.

### Tuần 2 — Thử một thay đổi nhỏ

- Chốt ví dụ nghiệp vụ/contract trước khi code lớn.
- Viết contract test ở ranh giới thường sai.
- Chia thay đổi thành các lát cắt có thể kiểm chứng sớm.
- Tích hợp thường xuyên theo nhịp khả thi, giữ review và DoD.

**Đầu ra:** Một vài lát cắt nhỏ có bằng chứng vượt qua ranh giới nhóm.

### Tuần 3 — Quan sát và xử lý trở ngại

- Phân loại lỗi pipeline trước khi sửa hoặc tạm cách ly test.
- Khi item già hoặc blocked, ưu tiên gỡ phụ thuộc trước khi kéo thêm hàng loạt việc.
- Xem độ sẵn sàng của môi trường và dữ liệu test.
- Ghi tác dụng phụ, phản hồi developer, tester và vận hành.

**Đầu ra:** Dữ liệu quan sát, các điều chỉnh có căn cứ và guardrail.

### Tuần 4 — Đánh giá và quyết định

- So sánh loại item tương đồng và phân bố cycle time/blocked, không chỉ giá trị trung bình.
- Xem lỗi contract đã phát hiện sớm hơn chưa; test flaky và sự cố production thay đổi thế nào.
- Ghi những yếu tố cùng kỳ: API đối tác, năng lực reviewer, kỳ nghỉ, cách chia story.
- Chọn giữ, sửa, bỏ hoặc quan sát thêm; cập nhật thực hành tích hợp và tri thức chung.

**Đầu ra:** Kết luận có giới hạn, không phải bảng xếp hạng thành tích.

### Mẫu thử nghiệm

~~~text
VẤN ĐỀ:
  Story xuyên nhóm chỉ được thử với provider thật sau nhiều ngày.

GIẢ THUYẾT:
  Làm rõ contract sớm và kiểm chứng mỗi thay đổi có thể giảm
  thời gian chờ API và vòng làm lại khi tích hợp.

CAN THIỆP:
  Chốt request/response/error examples trước code lớn.
  Provider/consumer cùng duy trì contract test.
  Tích hợp những lát cắt nhỏ theo nhịp khả thi.

ĐO:
  Work item age, blocked duration do API,
  lỗi contract phát hiện trước/sau merge,
  cycle time và sức khỏe pipeline.

GUARDRAIL:
  DoD, phân quyền, tương thích phiên bản còn hỗ trợ,
  toàn vẹn dữ liệu, khả năng khôi phục, overtime.

QUYẾT ĐỊNH:
  Giữ / điều chỉnh / bỏ / thu thêm dữ liệu.
  Ghi yếu tố gây nhiễu, người quyết định và ngày xem lại.
~~~

## 27. Những sai lầm thường gặp

| Sai lầm | Vì sao có hại | Cách cải thiện |
| --- | --- | --- |
| **Mỗi nhóm code Done là PBI Done** | Chưa có Increment dùng được | Dùng DoD chung và kiểm chứng hành vi xuyên nhóm |
| **Có một Sprint tích hợp cuối kỳ** | Lỗi dồn muộn, khó sửa | Tích hợp từng lát cắt trong quá trình phát triển |
| **Pipeline xanh là bằng chứng chất lượng đầy đủ** | Bỏ qua quyền, dữ liệu, người dùng | Test theo rủi ro và DoD |
| **Contract là tài liệu không bao giờ cập nhật** | Provider/consumer âm thầm lệch | Kiểm chứng bằng test và quản lý phiên bản |
| **Mock thay thế mọi tích hợp thật** | Test xanh giả | Xác minh provider và chạy integration tests |
| **Phá client cũ vì backend đã deploy** | Người dùng/đối tác gặp lỗi | Tương thích và kế hoạch chuyển đổi |
| **Rollback code hoàn tác được migration** | Dữ liệu có thể không phục hồi | Đối soát, backup, kế hoạch restore |
| **Mọi thay đổi chờ một chuyên gia duyệt** | Hàng chờ tăng | Quyền quyết định và reviewer dự phòng |
| **Scrum of Scrums chỉ đọc status** | Họp nhiều nhưng blocker không gỡ | Chọn phụ thuộc và quyết định cần hành động |
| **Rerun CI đến khi xanh** | Che test flaky/lỗi thật | Phân loại và cải tiến test/môi trường |
| **Số merge/người là KPI tích hợp** | Tối ưu hoạt động thay vì giá trị | Đo flow, Increment, chất lượng và outcome |
| **Bỏ phân quyền để kịp deadline** | Rủi ro dữ liệu nghiêm trọng | Giữ chuẩn bắt buộc, thu hẹp phạm vi an toàn |
| **Feature flag khiến code lỗi thành Done** | Nhánh lỗi có thể bị bật | Kiểm chứng trạng thái cần hỗ trợ, DoD |
| **Mỗi Scrum Team cùng sản phẩm có DoD riêng** | Không có chuẩn Increment chung | Cùng định nghĩa và tuân thủ một DoD |
| **Dùng E2E cho mọi ca** | Pipeline chậm/flaky | Cân bằng unit, contract, integration và E2E |
| **Cộng blocked chồng lấp hai lần** | Phóng đại thời gian chờ thực | Hợp khoảng blocked theo item |
| **Gán lỗi tích hợp cho “nhóm phụ thuộc”** | Che nguyên nhân hệ thống | Dùng timeline và quyền quyết định để học hỏi |
| **Sao chép một pipeline cho mọi loại repository** | Test dư hoặc thiếu rủi ro | Chất lượng chung, thực hiện phù hợp bối cảnh |
| **Release trước, chưa rõ người xử lý sự cố** | Khôi phục chậm | Chủ sở hữu, telemetry, quyền dừng và runbook |

## 28. Bài tập thực hành

### Bài tập 1 — “Done” ở đâu?

Nhóm UI đã merge, API trả 200, Identity đã sửa quyền. Nhưng chưa có integration test và test truy cập chéo tài khoản đang thất bại.

**Yêu cầu:** Phân biệt Done kỹ thuật cục bộ và Increment đạt DoD; nêu hành động phải làm trước khi gọi lát cắt hoàn thành.

### Bài tập 2 — Tạo DoD chung

Hai Scrum Team cùng làm một nền tảng học trực tuyến, một nhóm làm UI, nhóm còn lại làm API/dữ liệu.

**Yêu cầu:** Đề xuất DoD chung gồm ít nhất sáu nhóm tiêu chí kiểm chứng được và hai điều kiện áp dụng khi thay đổi có rủi ro liên quan.

### Bài tập 3 — Quyền quyết định và phụ thuộc

Một story chưa rõ “bài gần nhất”, API chưa chốt mã lỗi và migration chờ người phê duyệt.

**Yêu cầu:** Lập bảng câu hỏi, vai trò có quyền quyết định, nhóm phải tham gia, phương án tiếp tục an toàn và bằng chứng cần có.

### Bài tập 4 — Contract API nhỏ

Thiết kế endpoint trả bài gần nhất còn quyền cho tài khoản đã xác thực.

**Yêu cầu:** Mô tả request, thành công, không có bài, chưa xác thực, phụ thuộc lỗi; xác định những điểm là giả định nghiệp vụ cần xác nhận.

### Bài tập 5 — Không phá consumer cũ

API v1 dùng trường “lessonId”, v2 muốn đổi thành “lesson_id” khi mobile cũ chưa cập nhật.

**Yêu cầu:** Thiết kế lộ trình tương thích, contract tests cho hai phiên bản và điều kiện ngừng support trường cũ.

### Bài tập 6 — Migration có dữ liệu nhạy cảm

Tiến độ học được bổ sung số phiên bản; client cũ chưa gửi trường này.

**Yêu cầu:** Trình bày expand–migrate–contract, test cần có, điều kiện an toàn, cách đối soát và vì sao rollback code không chắc phục hồi dữ liệu.

### Bài tập 7 — Pipeline CI theo rủi ro

Unit tests xanh nhưng Auth–API–DB hay lỗi; CI chạy chậm và có một test flaky.

**Yêu cầu:** Thiết kế các lớp kiểm tra, xử lý flaky, ngưỡng quyết định tích hợp/release và trách nhiệm của các nhóm.

### Bài tập 8 — Response cũ đến muộn

A đăng xuất, B đăng nhập cùng thiết bị; response cũ về tiến độ A đến muộn.

**Yêu cầu:** Viết ba trường hợp kiểm thử: logic, tích hợp Auth/API/cache và E2E. Chỉ rõ điều không được xảy ra.

### Bài tập 9 — Tính thời gian chờ

Bốn item đã Done có cycle time **6, 8, 4, 10 ngày**; thời gian chờ liên nhóm lần lượt **2, 3, 1, 4 ngày**, không chồng lấp.

**Yêu cầu:** Tính tỷ lệ chờ theo tổng duration và median cycle time; giải thích giới hạn diễn giải.

**Gợi ý đáp án:** **10/28 ≈ 35,7%**, median **7 ngày**. Không suy ra tỷ lệ thời gian nhân sự không làm việc.

### Bài tập 10 — Họp liên nhóm nào đáng giữ?

Năm nhóm họp Scrum of Scrums 60 phút mỗi ngày, phần lớn là đọc ticket và không giải quyết phụ thuộc.

**Yêu cầu:** Đề xuất nội dung, thành phần và nhịp hợp lý hơn; nêu khi nào dùng contract huddle hoặc kênh bất đồng bộ.

### Bài tập 11 — Feature flag và DoD

Code sau flag mặc định tắt, nhưng test phân quyền ở nhánh bật đang thất bại. Có người đề nghị gọi Done vì “chưa ai bật”.

**Yêu cầu:** Đánh giá theo DoD, rủi ro và điều kiện release, không dùng flag để bỏ qua chất lượng.

### Bài tập 12 — Thử nghiệm bốn tuần

Đội thường bị chặn vì API contract đổi giữa Sprint. Họ muốn chốt ví dụ trước code, chạy contract test sớm và chia PR nhỏ.

**Yêu cầu:** Xây giả thuyết, baseline, can thiệp, metric, guardrail, người quyết định và thời gian xem lại; chỉ ra yếu tố gây nhiễu.

### Bài tập 13 — Đổi phiên bản nhiều nhịp release

Backend đã triển khai v2; 30% ứng dụng mobile còn dùng v1. Đội muốn xóa trường cũ.

**Yêu cầu:** Hỏi những thông tin cần xác minh và đề xuất lộ trình để không làm hỏng client đang được hỗ trợ.

### Bài tập 14 — Post-incident review

Một số học viên không mở được bài sau release vì client cũ hiểu mã “204 No Content” thành lỗi; pipeline chỉ test client mới.

**Yêu cầu:** Mô tả nguyên nhân hệ thống không quy lỗi cá nhân; đề xuất cập nhật test, ma trận version, telemetry và trách nhiệm.

### Bài tập 15 — Tích hợp tốt nhưng người dùng không sử dụng

Contract tests xanh, Increment đạt DoD, release thành công; nhưng nút “Tiếp tục học” ít được dùng.

**Yêu cầu:** Phân biệt chất lượng/integration với outcome sản phẩm; đề xuất một nghiên cứu định tính và funnel có mẫu số rõ, giữ quyền riêng tư.

## 29. Checklist tích hợp thường xuyên cùng chất lượng chung

- [ ] Mục tiêu sản phẩm và **lát cắt hành vi** đã rõ, không chỉ task kỹ thuật riêng nhóm?
- [ ] Nếu nhiều Scrum Team cùng một sản phẩm, đã chia sẻ **Product Goal, Product Backlog, Product Owner và DoD**?
- [ ] Đã phân biệt AC, DoD, chính sách tích hợp và điều kiện release?
- [ ] Các nhóm hiểu **start/finish, quyền quyết định và phụ thuộc**?
- [ ] API contract có request/response, lỗi, ngữ nghĩa, quyền và version?
- [ ] Contract được kiểm chứng với provider/consumer, không chỉ mock riêng?
- [ ] Thay đổi được chia thành những phần nhỏ có thể tích hợp thường xuyên?
- [ ] Pipeline CI có kiểm tra nhanh đáng tin và các lớp test theo rủi ro?
- [ ] Lỗi pipeline được phân loại, không rerun đến xanh rồi bỏ qua?
- [ ] Có kiểm thử dữ liệu và quyền xuyên nhóm khi thay đổi liên quan?
- [ ] Môi trường test có version, cấu hình và dữ liệu rõ, không dùng bí mật ngoài quyền?
- [ ] Consumer cũ và mới được kiểm tra theo chính sách hỗ trợ?
- [ ] Schema migration có đánh giá tương thích, đối soát và khôi phục?
- [ ] Các item blocked có nguyên nhân, người phối hợp và thời điểm xem lại?
- [ ] Các buổi họp liên nhóm dẫn tới quyết định và gỡ trở ngại thực?
- [ ] Khi test liên nhóm thất bại, các bên hợp tác sửa thay vì đẩy lỗi?
- [ ] Feature flag không dùng thay phân quyền hoặc DoD?
- [ ] Increment chỉ được gọi Done khi **đã tích hợp, sử dụng được và đạt DoD**?
- [ ] Đã phân biệt merge, deploy, release và outcome?
- [ ] Có telemetry, phương án ứng phó và quyền dừng/mở rộng rollout?
- [ ] Chỉ số flow/CI/rework/chất lượng có mốc đo, kỳ và mẫu số rõ?
- [ ] Có quan sát item chưa Done và rủi ro người dùng, không chỉ số PR merge?
- [ ] Thử nghiệm cải tiến có giả thuyết, guardrail và quyết định sau thử?
- [ ] Kết quả được chia sẻ để các nhóm học hỏi, không xếp hạng cá nhân?

Checklist để **bảo vệ Increment và chất lượng**, không buộc mọi thay đổi chạy mọi loại test hay mời tất cả mọi người vào mọi cuộc họp.

## 30. Tổng kết

- **Tích hợp thường xuyên** đưa những thay đổi nhỏ qua kiểm chứng chung, phát hiện lệch hợp đồng, dữ liệu, quyền và hành vi khi lỗi còn dễ sửa. Merge code hoặc build xanh chưa đủ.
- **Một Increment cần một nghĩa Done chung.** Khi nhiều Scrum Team cùng một sản phẩm, họ chia sẻ Product Goal, Product Backlog, Product Owner và phải cùng định nghĩa/tuân thủ một Definition of Done.
- **AC, DoD, integration policy và release criteria** khác vai trò nhưng phải bổ sung nhau để tránh “Done cục bộ”.
- **API contract, version và schema** cần chiến lược tương thích và kiểm thử tăng dần; migration dữ liệu không thể được xem như đổi code thông thường.
- **Kiểm thử xuyên nhóm phải bảo vệ những ranh giới có rủi ro:** danh tính, quyền, cache, retry, concurrency, client cũ–mới và hành vi người dùng.
- **CI, contract/integration tests, TDD, review và phản hồi sớm** giúp giảm rework; pipeline và môi trường đáng tin là điều kiện để phối hợp nhanh.
- **Điều phối nên tập trung vào phụ thuộc và quyền quyết định**, không nhân bản những buổi họp chỉ đọc status. Scrum, Kanban và XP cung cấp các thực hành bổ sung theo bối cảnh.
- **Đo cả dòng công việc, chất lượng và giá trị:** Work item age, blocked time, cycle time, lỗi tích hợp, sự cố và trải nghiệm người dùng. Không lấy số merge làm thước đo năng suất cá nhân.
- **Phát hành an toàn** cần DoD, kiểm soát phiên bản, quyền riêng tư, telemetry và khả năng phản ứng; feature flag không cho phép bỏ tiêu chuẩn bắt buộc.

Khi nhiều nhóm cùng nói **“phần của tôi đã Done”**, hãy hỏi: **“Những phần ấy đã hoạt động cùng nhau, đáp ứng một tiêu chuẩn chất lượng chung và tạo ra một Increment mà người dùng thực sự có thể sử dụng chưa?”**
