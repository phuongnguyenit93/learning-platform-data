# Xác định trách nhiệm khôi phục pipeline khi kiểm tra thất bại

## Mục tiêu bài học

Pipeline CI/CD là một phần của quy trình phát triển và phát hành. Khi một kiểm tra thất bại, nhóm cần xác định nhanh đó là lỗi sản phẩm, lỗi kiểm thử, lỗi hạ tầng, lỗi cấu hình hay sự cố từ dịch vụ phụ thuộc. Nếu không có trách nhiệm rõ ràng, cảnh báo có thể bị bỏ qua, nhiều nhóm cùng điều tra một vấn đề, hoặc mọi người cho rằng nhóm khác sẽ khôi phục pipeline. Điều này kéo dài thời gian phản hồi và làm giảm niềm tin vào cổng chất lượng.

Trong chiến lược VALIDATION_TESTING_STRATEGY, trách nhiệm khôi phục pipeline cần được xác định trước khi sự cố xảy ra. Mỗi bước kiểm tra cần có chủ sở hữu, người tiếp nhận khi thất bại, quyền quyết định đối với việc chặn hoặc tiếp tục phát hành và quy trình bàn giao khi nguyên nhân nằm ngoài phạm vi của nhóm đang xử lý. Khôi phục pipeline không chỉ là làm cho trạng thái chuyển sang xanh; cần sửa nguyên nhân, xác minh lại các kiểm tra liên quan và lưu bằng chứng rằng quyết định tiếp tục là an toàn.

Sau bài học, người học có thể:

- Phân biệt trách nhiệm sở hữu pipeline, test, mã nguồn, hạ tầng và quyết định phát hành.
- Xác định người tiếp nhận và người chịu trách nhiệm cuối cùng cho từng loại kiểm tra.
- Phân loại lỗi pipeline và chọn quy trình triage phù hợp.
- Tổ chức quy trình khôi phục từ phát hiện, điều tra, xử lý đến xác minh.
- Xây dựng ma trận trách nhiệm, cơ chế escalation và runbook.
- Quyết định khi nào cần sửa lỗi, chạy lại, cách ly test hoặc tạm dừng pipeline.
- Ghi nhận rủi ro và quản lý ngoại lệ mà không làm mất tín hiệu chất lượng.
- Đo lường thời gian khôi phục và độ tin cậy của pipeline.

## 1. Vì sao cần xác định trách nhiệm khôi phục?

Một pipeline có thể bao gồm kiểm tra mã nguồn, build, unit test, contract test, integration test, security scan, kiểm thử giao diện, đóng gói artifact, triển khai và xác minh sau triển khai. Các bước này có thể do nhiều nhóm sở hữu hoặc phụ thuộc vào nhiều hệ thống dùng chung.

Khi một bước thất bại, người nhìn thấy cảnh báo đầu tiên không nhất thiết là người có đủ quyền hoặc kiến thức để sửa. Ví dụ:

- Unit test thất bại do thay đổi logic: nhóm sở hữu mã nguồn cần điều tra.
- Integration test không kết nối được database: nhóm nền tảng hoặc người sở hữu môi trường có thể cần xử lý.
- Contract verification thất bại sau khi API thay đổi: nhóm provider và consumer cần phối hợp.
- Security scan phát hiện lỗ hổng: nhóm sở hữu thành phần cần đánh giá, còn nhóm bảo mật hỗ trợ phân loại rủi ro.
- Runner hết dung lượng: nhóm vận hành CI cần khôi phục tài nguyên.
- Test giao diện thất bại vì selector lỗi thời: nhóm sở hữu test hoặc giao diện cần cập nhật.
- Deployment check không đạt: nhóm vận hành dịch vụ hoặc release owner cần đánh giá trạng thái triển khai.

Nếu không xác định ownership, nhóm có thể gặp các vấn đề:

- Không ai nhận xử lý cảnh báo vì trách nhiệm không rõ.
- Người sửa mã bị giao điều tra hạ tầng mà không có quyền truy cập.
- Nhóm nền tảng bị yêu cầu sửa assertion nghiệp vụ mà không hiểu mục tiêu test.
- Pipeline bị retry nhiều lần để che lỗi.
- Test bị tắt hoặc bỏ qua mà không có người chịu rủi ro.
- Một nhánh phát hành tiếp tục dù cổng kiểm tra quan trọng chưa đạt.
- Không có người xác nhận pipeline đã phục hồi đúng cách.

Trách nhiệm rõ ràng giúp rút ngắn thời gian tìm đúng người, giảm thời gian gián đoạn và bảo đảm mọi ngoại lệ có chủ sở hữu.

## 2. Các loại ownership trong CI/CD

Một pipeline không nhất thiết chỉ có một chủ sở hữu. Cần phân biệt trách nhiệm đối với dịch vụ pipeline, nội dung kiểm tra, thành phần được kiểm tra và quyết định phát hành.

### 2.1. Chủ sở hữu pipeline

Chủ sở hữu pipeline hoặc CI platform team chịu trách nhiệm về khả năng hoạt động của nền tảng chạy pipeline, chẳng hạn:

- Runner, agent, executor và môi trường build.
- Scheduler, queue và khả năng cấp phát tài nguyên.
- Credentials và tích hợp với kho mã, registry hoặc artifact store.
- Plugin, action, template và phiên bản công cụ dùng chung.
- Khả năng truy cập mạng và dịch vụ CI phụ trợ.
- Log, metric, trace và lưu trữ artifact.
- Tính sẵn sàng, backup và khôi phục cấu hình pipeline dùng chung.

Nhóm này xử lý sự cố thuộc nền tảng CI. Họ không mặc nhiên sở hữu mọi lỗi test chỉ vì test chạy trong pipeline.

### 2.2. Chủ sở hữu test và bộ kiểm thử

Test owner hoặc nhóm QA/engineering chịu trách nhiệm về mục tiêu và độ tin cậy của kiểm tra:

- Test đang bảo vệ yêu cầu hoặc rủi ro nào.
- Dữ liệu, fixture, mock và môi trường cần thiết.
- Assertion và điều kiện đạt/trượt.
- Khả năng tái lập, tính độc lập và chẩn đoán.
- Sửa test khi yêu cầu hoặc giao diện thay đổi hợp lệ.
- Phân tích flaky test và duy trì bộ kiểm thử.
- Xác nhận test mới thực sự phát hiện lỗi cần bảo vệ.

Test owner cần phối hợp với nhóm phát triển khi kết quả phản ánh lỗi sản phẩm. Họ cũng cần phối hợp với CI owner nếu lỗi nằm ở cách thực thi hoặc tài nguyên chạy test.

### 2.3. Chủ sở hữu mã nguồn và thành phần

Component owner hoặc code owner chịu trách nhiệm về hành vi của thành phần:

- Phân tích lỗi sản phẩm do thay đổi mã.
- Sửa logic, cấu hình hoặc migration thuộc thành phần.
- Bảo đảm unit, component và integration test phù hợp.
- Đánh giá tác động tới consumer và dịch vụ phụ thuộc.
- Cung cấp hướng dẫn tái hiện và xác nhận bản sửa.
- Duy trì tương thích của API hoặc sự kiện thuộc phạm vi sở hữu.

Người tạo pull request thường là đầu mối ban đầu vì họ biết thay đổi vừa thực hiện. Tuy nhiên, trách nhiệm sửa lâu dài có thể thuộc nhóm sở hữu thành phần theo quy ước code ownership.

### 2.4. Chủ sở hữu môi trường và phụ thuộc

Nhóm platform, SRE, database, network hoặc nhóm tích hợp có thể chịu trách nhiệm về:

- Môi trường test, namespace, cluster và dịch vụ nền.
- Database, broker, cache, storage và kết nối.
- DNS, firewall, TLS, certificate và network policy.
- Secret, service identity và quyền truy cập.
- Hệ thống ngoài hoặc sandbox do nhóm quản lý.
- Giới hạn tài nguyên, quota và khả năng phục hồi.

Cần chỉ định rõ nhóm chịu trách nhiệm cho từng phụ thuộc quan trọng. Nếu một dịch vụ do nhà cung cấp ngoài vận hành, nhóm nội bộ vẫn cần có người điều phối sự cố và đánh giá tác động.

### 2.5. Chủ sở hữu quyết định phát hành

Release owner, product owner hoặc người được ủy quyền chịu trách nhiệm quyết định phát hành theo chính sách:

- Xác định các cổng kiểm tra bắt buộc.
- Đánh giá kết quả chưa đạt và rủi ro còn lại.
- Phê duyệt ngoại lệ trong phạm vi quyền hạn.
- Quyết định hoãn, tiếp tục, rollback hoặc giới hạn rollout.
- Bảo đảm người chịu rủi ro được thông báo.
- Ghi nhận quyết định và thời hạn của ngoại lệ.

Người điều phối release không tự sửa lỗi test hoặc hạ mức độ nghiêm trọng của phát hiện bảo mật. Họ chịu trách nhiệm quyết định dựa trên bằng chứng và ý kiến của đúng chủ sở hữu chuyên môn.

## 3. Nguyên tắc phân công trách nhiệm

Một mô hình trách nhiệm hiệu quả cần tuân theo một số nguyên tắc.

### 3.1. Một đầu mối chịu trách nhiệm cuối cùng cho mỗi phạm vi

Mỗi pipeline, stage hoặc nhóm kiểm tra cần có một owner chính. Có thể có nhiều người thực hiện, nhưng cần biết ai chịu trách nhiệm bảo đảm phạm vi đó được duy trì và sự cố được xử lý.

### 3.2. Người phát hiện không nhất thiết là người sửa

CI có thể phát hiện lỗi và tạo thông báo, nhưng không nên mặc định CI team phải sửa mọi lỗi. Người tiếp nhận cần phân loại và chuyển đúng owner theo loại lỗi.

### 3.3. Ownership theo thành phần và theo kiểm tra phải liên kết

Một integration test có thể được sở hữu bởi nhóm test platform, nhưng nó kiểm tra một API do nhóm dịch vụ khác phát triển. Khi test thất bại, test owner xác nhận oracle và khả năng tái hiện; component owner điều tra hành vi dịch vụ; CI owner kiểm tra môi trường chạy nếu có dấu hiệu hạ tầng.

### 3.4. Quyền quyết định phải tương xứng với trách nhiệm

Người có trách nhiệm khôi phục cần có quyền truy cập log, artifact, môi trường và công cụ cần thiết. Người phê duyệt ngoại lệ phải có thẩm quyền chấp nhận rủi ro. Không giao trách nhiệm cho một nhóm mà không cung cấp quyền hoặc kênh escalation.

### 3.5. Không dùng trạng thái xanh làm mục tiêu duy nhất

Pipeline xanh chỉ có ý nghĩa khi các kiểm tra bắt buộc đã chạy và đạt, hoặc ngoại lệ đã được phê duyệt theo quy trình. Tắt test, bỏ qua stage hoặc retry đến khi pass có thể làm xanh giao diện nhưng không khôi phục bằng chứng chất lượng.

## 4. Ma trận trách nhiệm RACI

RACI giúp xác định ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai cần được thông báo.

- **R — Responsible:** trực tiếp thực hiện công việc.
- **A — Accountable:** chịu trách nhiệm cuối cùng và ra quyết định trong phạm vi được giao.
- **C — Consulted:** cung cấp chuyên môn hoặc được tham vấn.
- **I — Informed:** được thông báo về tiến độ và kết quả.

Ví dụ ma trận cho một tổ chức có nhóm phát triển, QA, CI platform, SRE và release owner:

| Hoạt động | Developer/Component Owner | Test Owner/QA | CI Platform | SRE/Dependency Owner | Release Owner |
|---|---|---|---|---|---|
| Phân loại lỗi logic trong mã | A/R | C | I | I | I |
| Phân tích assertion hoặc fixture sai | C | A/R | C | I | I |
| Khôi phục runner hoặc scheduler | I | C | A/R | C | I |
| Khôi phục database test hoặc broker | C | C | C | A/R | I |
| Sửa contract không tương thích | A/R hoặc phối hợp provider/consumer | R/C | I | I | I |
| Xử lý lỗ hổng bảo mật | R | C | C | C | A hoặc người có thẩm quyền bảo mật |
| Quyết định cách ly test | C | A/R | C | I | I nếu ảnh hưởng gate phát hành |
| Phê duyệt ngoại lệ release gate | C | C | C | C | A/R |
| Xác nhận pipeline đã phục hồi | R theo phạm vi | R theo phạm vi | R theo phạm vi | R theo phạm vi | A cho quyết định phát hành |
| Rà soát nguyên nhân lặp lại | R | R | R | R | A hoặc người điều phối được chỉ định |

Ma trận phải được điều chỉnh theo tổ chức. Không nên gán nhiều A cho cùng một hoạt động nếu không xác định rõ ai có quyền quyết định cuối cùng. Một sự cố có thể có nhiều nhóm R ở các phần việc khác nhau, nhưng cần một incident coordinator hoặc owner điều phối tổng thể.

## 5. Phân loại kiểm tra thất bại trước khi khôi phục

Không nên bắt đầu bằng cách chạy lại toàn bộ pipeline. Trước tiên cần xác định loại thất bại và phạm vi ảnh hưởng.

| Loại thất bại | Dấu hiệu thường gặp | Owner đầu tiên |
|---|---|---|
| Lỗi sản phẩm | Assertion phản ánh kết quả khác yêu cầu; có thể tái hiện trên build mới. | Component owner hoặc người tạo thay đổi. |
| Lỗi test | Fixture sai, assertion lỗi, selector lỗi thời hoặc giả định không còn đúng. | Test owner. |
| Flaky test | Cùng build và điều kiện gần tương đương nhưng kết quả lúc đạt lúc trượt. | Test owner phối hợp component/platform owner tùy nguyên nhân. |
| Lỗi runner/CI | Runner mất kết nối, queue treo, hết dung lượng, image build lỗi. | CI platform owner. |
| Lỗi môi trường | Database, broker, sandbox hoặc namespace không sẵn sàng. | Environment/dependency owner. |
| Lỗi cấu hình/secret | Thiếu biến môi trường, token hết hạn, certificate sai hoặc quyền không đủ. | Owner của cấu hình, identity hoặc secret tương ứng. |
| Lỗi công cụ hoặc scan | Phiên bản scanner, rule set hoặc plugin bị lỗi; kết quả không thể phân tích. | Tool/CI owner, phối hợp security owner nếu cần. |
| Lỗi ngoài hệ thống | Nhà cung cấp hoặc dịch vụ ngoài gián đoạn, rate limit hoặc thay đổi API. | Integration/dependency owner. |
| Hủy hoặc timeout do tài nguyên | Job bị kill, quá giới hạn CPU/memory hoặc timeout. | Owner tài nguyên hoặc CI platform, phối hợp component owner. |

Phân loại ban đầu là giả thuyết, có thể thay đổi khi có bằng chứng. Nếu chưa xác định được nguyên nhân, chỉ định một người điều phối để thu thập dữ liệu và chuyển việc; không để sự cố ở trạng thái “không rõ owner”.

## 6. Quy trình khôi phục pipeline

Một quy trình chung có thể áp dụng cho phần lớn sự cố:

~~~mermaid
flowchart TD
    A[Kiểm tra thất bại] --> B[Tạo thông báo và lưu bằng chứng]
    B --> C[Phân loại sơ bộ và xác định phạm vi]
    C --> D[Gán incident owner và component owner]
    D --> E[Điều tra nguyên nhân]
    E --> F{Đã xác định nguyên nhân?}
    F -->|Chưa| G[Thu thập thêm log, artifact và tái hiện]
    G --> E
    F -->|Rồi| H[Khắc phục hoặc áp dụng biện pháp giảm thiểu]
    H --> I[Chạy lại kiểm tra mục tiêu]
    I --> J{Đạt và bằng chứng đủ?}
    J -->|Không| E
    J -->|Có| K[Chạy các gate liên quan]
    K --> L{Rủi ro còn lại được xử lý?}
    L -->|Không| M[Giữ gate hoặc escalation]
    L -->|Có| N[Ghi nhận phục hồi và quyết định tiếp tục]
~~~

### 6.1. Phát hiện và tạo incident

Khi kiểm tra thất bại, hệ thống hoặc người trực cần ghi nhận:

- Pipeline, stage và job ID.
- Repository, branch, commit và pull request hoặc release.
- Test hoặc rule thất bại.
- Thời điểm bắt đầu và kết thúc.
- Log, artifact, trace và kết quả lần chạy đầu.
- Các lần retry và kết quả từng lần.
- Môi trường, runner và phiên bản công cụ.
- Phạm vi bị chặn: một pull request, nhánh chính hay release.

Nếu thất bại ảnh hưởng nhánh chính hoặc release đang chờ, cần tạo incident hoặc ticket có mức ưu tiên tương ứng. Một lỗi đơn lẻ ở pull request không nhất thiết cần quy trình incident nghiêm trọng, nhưng vẫn cần owner xử lý.

### 6.2. Chỉ định owner và xác nhận tiếp nhận

Thông báo cần gửi đến nhóm sở hữu phù hợp, kèm đường dẫn trực tiếp tới log và hướng dẫn tái hiện. Owner cần xác nhận tiếp nhận trong thời gian phản hồi đã thống nhất.

Nếu không có phản hồi, dùng escalation path đã công bố: người trực, trưởng nhóm, owner dịch vụ hoặc incident coordinator. Không chỉ gửi thông báo vào một kênh chung rồi giả định có người theo dõi.

### 6.3. Triage và điều tra

Owner kiểm tra:

1. Thất bại có bắt đầu sau commit hoặc thay đổi cấu hình nào không?
2. Cùng test có thất bại ở local hoặc môi trường khác không?
3. Test có thể chạy lại độc lập với cùng dữ liệu không?
4. Runner và các phụ thuộc có health bình thường không?
5. Có thay đổi về phiên bản, secret, quyền hoặc network không?
6. Log cho thấy lỗi xảy ra ở ứng dụng, test harness hay nền tảng?
7. Các job khác có cùng lỗi hoặc chỉ một test/nhánh bị ảnh hưởng?

Cần giữ lại bằng chứng trước khi dọn môi trường. Không xóa namespace, container hoặc dữ liệu cần thiết cho việc điều tra cho đến khi đã lưu đủ thông tin.

### 6.4. Khắc phục và giảm thiểu

Tùy nguyên nhân, hành động có thể gồm:

- Sửa mã nguồn hoặc cấu hình sản phẩm.
- Sửa assertion, fixture hoặc test data.
- Khôi phục runner, queue hoặc dung lượng.
- Khôi phục database, broker hoặc sandbox.
- Cấp lại secret hoặc certificate theo quy trình.
- Roll back thay đổi công cụ CI gây lỗi.
- Cập nhật hợp đồng hoặc đồng bộ phiên bản provider/consumer.
- Cách ly tạm thời một test flaky theo quy trình được phê duyệt.
- Chặn phát hành và mở escalation nếu chưa thể khôi phục an toàn.

Biện pháp giảm thiểu cần có owner, thời hạn và rủi ro được ghi nhận. Ví dụ, tạm thời chuyển một test sang job riêng có thể giúp các kiểm tra khác tiếp tục chạy, nhưng không có nghĩa rủi ro của test đó đã được giải quyết.

### 6.5. Xác minh sau khắc phục

Không nên chỉ nhìn thấy pipeline chạy xanh sau một lần retry. Cần xác minh:

- Kiểm tra thất bại ban đầu đã đạt trong điều kiện phù hợp.
- Test có thể chạy lại độc lập hoặc theo suite theo yêu cầu.
- Các kiểm tra liên quan đến thay đổi đã chạy.
- Không có stage bắt buộc nào bị bỏ qua.
- Artifact được tạo từ đúng commit và cấu hình.
- Kết quả scan và các gate bảo mật vẫn hợp lệ.
- Rủi ro còn lại và ngoại lệ đã được phê duyệt nếu có.

Với lỗi hạ tầng, cần xác minh runner hoặc dịch vụ đã ổn định. Với lỗi sản phẩm, cần xác minh test phát hiện được lỗi trước sửa nếu có thể và pass trên bản sửa.

## 7. Trách nhiệm theo loại pipeline stage

Mỗi stage nên có owner chính, tiêu chí thành công và quy trình khi thất bại.

| Stage | Mục tiêu | Owner chính khi thất bại | Phối hợp |
|---|---|---|---|
| Checkout/source fetch | Lấy đúng mã nguồn và submodule. | CI platform hoặc SCM owner. | Developer nếu quyền repository sai. |
| Build/compile | Tạo artifact từ mã nguồn. | Component/build owner. | CI platform nếu runner hoặc toolchain lỗi. |
| Unit test | Xác minh logic đơn vị. | Component owner/test owner theo loại lỗi. | Developer của thay đổi. |
| Static analysis/lint | Kiểm tra quy tắc mã và chất lượng tĩnh. | Code owner hoặc quality/tool owner. | Security/architecture nếu rule cần giải thích. |
| Contract test | Xác minh giao tiếp consumer/provider. | Consumer/provider owner theo phía sai lệch. | Test owner và nhóm tích hợp. |
| Integration test | Xác minh các thành phần phối hợp. | Owner của thành phần hoặc môi trường liên quan. | QA, database, broker hoặc platform. |
| E2E/UAT automation | Xác minh hành trình người dùng. | Test owner và component owner. | UX/business owner khi kỳ vọng chưa rõ. |
| Security scan | Phát hiện rủi ro bảo mật. | Security owner cùng component owner. | CI/tool owner nếu scanner lỗi. |
| Package/artifact publish | Đóng gói và lưu artifact đúng. | Build/release platform owner. | Component owner nếu metadata hoặc package sai. |
| Deploy/smoke test | Triển khai và xác minh sau triển khai. | Service/release owner. | SRE, platform và component owner. |

Một stage có thể có nhiều loại lỗi. Ví dụ, integration test thất bại vì assertion sai thì test owner xử lý; thất bại vì database test không sẵn sàng thì environment owner xử lý. Tên stage không tự quyết định nguyên nhân.

## 8. Quy định thời gian phản hồi và escalation

Thời gian phản hồi cần dựa trên mức độ ảnh hưởng, không chỉ dựa trên loại test. Một pipeline của nhánh chính đang chặn nhiều nhóm có mức ưu tiên khác với một test không ổn định ở nhánh thử nghiệm.

### 8.1. Phân mức ảnh hưởng

| Mức | Ví dụ | Hướng phản hồi |
|---|---|---|
| P1 – Nghiêm trọng | Nhánh chính bị chặn, release quan trọng không thể tiếp tục, nghi ngờ lỗ hổng hoặc rủi ro dữ liệu. | Kích hoạt incident owner, thông báo nhóm liên quan và điều phối liên tục đến khi có phương án an toàn. |
| P2 – Cao | Một nhóm hoặc luồng phát hành quan trọng bị chặn, có ảnh hưởng rộng nhưng còn đường làm việc thay thế. | Gán owner ngay, theo dõi tiến độ và escalation nếu vượt thời gian phản hồi. |
| P3 – Trung bình | Một test hoặc pipeline nhánh tính năng thất bại, chưa ảnh hưởng rộng. | Tạo ticket, gán owner và xử lý theo SLA nhóm. |
| P4 – Thấp | Cảnh báo không chặn, lỗi báo cáo hoặc vấn đề tối ưu không ảnh hưởng kiểm soát. | Đưa vào backlog có ưu tiên và người phụ trách. |

Các mốc thời gian cụ thể phải được tổ chức thống nhất, chẳng hạn thời gian xác nhận tiếp nhận, thời gian cập nhật tiến độ và thời gian mục tiêu khôi phục. Không nên tự đặt một SLA chung cho mọi tổ chức mà không xét quy mô và mức độ quan trọng của hệ thống.

### 8.2. Escalation path

Một đường escalation nên nêu rõ:

1. Người nhận cảnh báo đầu tiên.
2. Owner của stage hoặc test.
3. Owner của thành phần hoặc phụ thuộc liên quan.
4. Incident coordinator khi nhiều nhóm cần phối hợp.
5. Trưởng nhóm hoặc service owner nếu không có phản hồi hoặc vượt thời gian.
6. Release owner hoặc người có thẩm quyền khi quyết định phát hành bị ảnh hưởng.

Escalation là cơ chế đưa quyết định và nguồn lực đến đúng cấp, không phải công cụ đổ lỗi. Cần ghi rõ điều kiện kích hoạt và thông tin phải bàn giao.

## 9. Quy tắc chạy lại, retry và cách ly

Chạy lại có thể giúp phân biệt lỗi tạm thời với lỗi có thể tái hiện, nhưng không được thay thế điều tra.

### 9.1. Khi nào nên chạy lại?

Có thể chạy lại khi:

- Có bằng chứng runner hoặc dịch vụ ngoài gặp sự cố tạm thời.
- Test được thiết kế có thể retry an toàn.
- Cần xác nhận một kết quả không ổn định.
- Môi trường vừa được khôi phục và cần xác minh.

Khi chạy lại, lưu cả kết quả lần đầu và lần sau. Nếu lần đầu thất bại nhưng lần sau đạt, cần phân loại là tín hiệu cần điều tra, không tự động coi là pass sạch.

### 9.2. Khi nào không nên retry tự động?

Không nên retry mù quáng khi:

- Test có thể tạo giao dịch hoặc tác dụng phụ không idempotent.
- Lỗi có thể là vi phạm bảo mật hoặc dữ liệu.
- Assertion thất bại rõ ràng do kết quả sản phẩm sai.
- Retry có thể che race condition hoặc flaky test.
- Nhà cung cấp đã áp dụng rate limit và retry làm tình trạng nặng hơn.
- Kết quả của lần đầu cần được giữ lại để điều tra.

### 9.3. Cách ly test có kiểm soát

Nếu test flaky đang gây nhiễu pipeline, có thể cách ly tạm thời nhưng cần:

- Mã test và lý do cách ly.
- Rủi ro mà test đang bảo vệ.
- Owner và thời hạn xử lý.
- Pipeline hoặc job riêng tiếp tục chạy test nếu có thể.
- Biện pháp kiểm soát thay thế trong thời gian cách ly.
- Điều kiện đưa test trở lại gate bắt buộc.
- Review và phê duyệt theo mức rủi ro.

Không được âm thầm xóa test, bỏ stage hoặc biến retry thành cách duy nhất để vượt gate.

## 10. Runbook cho sự cố pipeline

Runbook cần đủ cụ thể để người trực có thể xử lý bước đầu mà không phải hỏi lại toàn bộ thông tin.

### 10.1. Nội dung runbook tối thiểu

- Tên pipeline, stage và mục đích kiểm tra.
- Owner chính, người thay thế và kênh liên hệ.
- Mức độ nghiêm trọng và điều kiện escalation.
- Link dashboard, log, artifact và lịch sử chạy.
- Cách xác định commit, branch, build và runner.
- Các bước kiểm tra health của dịch vụ phụ thuộc.
- Cách tái hiện test thất bại.
- Hướng dẫn khôi phục an toàn và xác minh sau khôi phục.
- Quy trình rollback hoặc dừng phát hành.
- Cách ghi nhận ngoại lệ và thời hạn.
- Các thao tác bị cấm hoặc cần phê duyệt.

### 10.2. Mẫu ghi nhận sự cố

~~~text
Incident ID:
Pipeline / Stage / Job:
Repository / Branch / Commit:
Thời điểm phát hiện:
Mức độ ảnh hưởng:
Kiểm tra thất bại:
Owner tiếp nhận:
Incident coordinator:
Loại lỗi sơ bộ:
Bằng chứng và liên kết log:
Phạm vi đang bị chặn:
Hành động đã thực hiện:
Kết quả chạy lại:
Nguyên nhân đã xác nhận:
Rủi ro còn lại:
Quyết định phát hành:
Người phê duyệt ngoại lệ (nếu có):
Thời điểm khôi phục:
Follow-up / hành động phòng ngừa:
~~~

### 10.3. Kiểm tra sau khôi phục

Runbook cần có tiêu chí đóng incident:

- Nguyên nhân đã được xác định hoặc có biện pháp giảm thiểu được chấp nhận.
- Pipeline và phụ thuộc hoạt động ổn định.
- Các kiểm tra bắt buộc đã chạy lại trên đúng commit.
- Không có gate bị bỏ qua ngoài ngoại lệ được phê duyệt.
- Artifact và kết quả gắn với đúng phiên bản.
- Release owner đã nhận thông tin và quyết định.
- Ticket theo dõi nguyên nhân gốc hoặc hành động dài hạn đã được tạo.

Nếu chỉ khôi phục tạm thời, incident không nên đóng như một vấn đề đã giải quyết hoàn toàn. Cần phân biệt trạng thái “dịch vụ đã hoạt động lại” với “nguyên nhân gốc đã được khắc phục”.

## 11. Ví dụ 1: Unit test thất bại sau thay đổi mã

Một pull request thay đổi quy tắc tính phí giao hàng. Unit test cho một vùng địa lý thất bại vì tổng phí thực tế khác mong đợi.

Quy trình:

1. CI tạo thông báo chứa test, commit và assertion thất bại.
2. Developer tạo thay đổi là đầu mối ban đầu và component owner tiếp nhận.
3. Test owner xác nhận fixture và kỳ vọng vẫn đúng với yêu cầu hiện hành.
4. Developer kiểm tra logic tính phí và phát hiện điều kiện miễn phí vận chuyển bị áp dụng sai.
5. Developer sửa mã và bổ sung hoặc cập nhật test cho điều kiện biên.
6. Chạy test thất bại, nhóm test liên quan và các kiểm tra hồi quy phù hợp.
7. CI ghi nhận kết quả trên commit mới; release gate chỉ tiếp tục khi các kiểm tra bắt buộc đạt.

Trong trường hợp này, CI platform không cần sửa runner vì pipeline đã thực thi đúng. Ownership thuộc nhóm mã nguồn và test owner phối hợp xác nhận oracle.

## 12. Ví dụ 2: Integration test thất bại vì môi trường

Pipeline integration test không thể kết nối database test. Nhiều job ở các repository khác nhau cùng thất bại với lỗi connection refused.

Quy trình:

1. CI platform hoặc người trực nhận thấy nhiều pipeline có cùng dấu hiệu.
2. Incident coordinator mở sự cố ảnh hưởng môi trường dùng chung.
3. Database/environment owner kiểm tra health, network, quota và trạng thái dịch vụ.
4. Test owner xác nhận lỗi xảy ra trước khi test thực hiện assertion nghiệp vụ.
5. Environment owner khôi phục database hoặc network policy.
6. Chạy smoke test kết nối và một integration test đại diện.
7. Chạy lại các job bị ảnh hưởng trên đúng commit; giữ log thất bại ban đầu.
8. Tạo follow-up để xử lý nguyên nhân như health check, autoscaling, quota hoặc cảnh báo.

Không nên yêu cầu từng developer sửa test của họ nếu nhiều pipeline cùng thất bại trước khi bắt đầu kiểm tra nghiệp vụ. Tín hiệu lỗi đồng loạt giúp xác định phạm vi môi trường dùng chung.

## 13. Ví dụ 3: Contract test thất bại do thay đổi API

Provider đổi tên một trường response nhưng chưa cập nhật consumer. Consumer contract verification thất bại.

Trách nhiệm cần chia theo hai phía:

- Consumer owner xác nhận trường nào thực sự được sử dụng và hợp đồng hiện tại còn đúng không.
- Provider owner xác định thay đổi API là chủ ý hay lỗi tương thích.
- Test owner kiểm tra contract và provider verification có phản ánh đúng tương tác không.
- Release owner quyết định hoãn phát hành nếu phiên bản mới không tương thích với consumer được hỗ trợ.

Nhóm có thể khôi phục bằng cách giữ trường cũ trong giai đoạn chuyển tiếp, cập nhật consumer theo kế hoạch hoặc phát hành phiên bản API mới. Không nên xóa contract hoặc bỏ qua verification chỉ để pipeline đạt.

## 14. Quyết định tiếp tục, chặn hoặc ngoại lệ

Không phải mọi thất bại đều có cùng tác động, nhưng mọi quyết định bỏ qua gate cần được quản lý.

### 14.1. Khi cần chặn

Nên giữ pipeline hoặc release gate khi:

- Có lỗi chức năng ảnh hưởng luồng cốt lõi.
- Có nguy cơ mất dữ liệu, giao dịch sai hoặc truy cập trái quyền.
- Kiểm tra bảo mật bắt buộc chưa đạt.
- Không xác định được độ tin cậy của artifact hoặc nguồn mã.
- Test quan trọng chưa chạy hoặc kết quả không hợp lệ.
- Môi trường triển khai chưa sẵn sàng hoặc không có khả năng rollback cần thiết.

### 14.2. Khi có thể xem xét ngoại lệ

Ngoại lệ chỉ nên được cân nhắc khi:

- Nguyên nhân đã được phân loại và bằng chứng cho thấy không phải lỗi sản phẩm thuộc phạm vi gate.
- Có biện pháp giảm thiểu và giới hạn tác động.
- Người có thẩm quyền chấp nhận rủi ro.
- Có người sở hữu, thời hạn và điều kiện hết hiệu lực.
- Có kiểm tra thay thế hoặc kế hoạch xác minh sau đó.
- Ngoại lệ được ghi nhận và truy vết.

Không nên cho phép ngoại lệ đối với rủi ro nghiêm trọng chỉ vì deadline. Nếu cần quyết định đặc biệt, phải có người có thẩm quyền và bằng chứng rõ ràng.

### 14.3. Hồ sơ ngoại lệ

~~~text
Gate / Test bị ảnh hưởng:
Lý do không đạt:
Nguyên nhân đã xác nhận:
Rủi ro nếu tiếp tục:
Phạm vi và thời hạn ngoại lệ:
Biện pháp giảm thiểu:
Kiểm tra thay thế:
Người chịu rủi ro:
Người phê duyệt:
Điều kiện hết hiệu lực:
Kế hoạch khắc phục:
~~~

Ngoại lệ nên hết hiệu lực theo thời gian hoặc theo sự kiện, ví dụ khi test được sửa, môi trường được khôi phục hoặc phiên bản phát hành tiếp theo bắt đầu. Không để ngoại lệ vô thời hạn trong cấu hình pipeline.

## 15. Giao tiếp và cập nhật trong lúc khôi phục

Khi pipeline ảnh hưởng nhiều nhóm, cập nhật ngắn và nhất quán giúp mọi người biết trạng thái và tránh làm trùng công việc.

Một bản cập nhật nên nêu:

- Phạm vi bị ảnh hưởng.
- Owner đang xử lý.
- Nguyên nhân đã biết và điều còn chưa rõ.
- Hành động tiếp theo.
- Quyết định tạm thời đối với gate hoặc release.
- Thời điểm cập nhật tiếp theo theo mức độ sự cố.

Tránh thông báo chỉ ghi “CI đỏ” hoặc “đang xem”. Cần chỉ rõ pipeline, commit, stage và người tiếp nhận. Khi bàn giao ca trực, ghi lại trạng thái, bằng chứng, lệnh đã chạy, thay đổi đã thực hiện và bước tiếp theo.

Giao tiếp nên tập trung vào sự kiện và bằng chứng, không quy kết cá nhân. Mục tiêu là khôi phục dịch vụ và cải thiện hệ thống để cùng loại sự cố ít lặp lại hơn.

## 16. Đo lường khả năng khôi phục pipeline

Một số chỉ số giúp đánh giá quy trình ownership và phục hồi:

| Chỉ số | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Mean time to acknowledge (MTTA) | Thời gian từ cảnh báo đến khi có owner xác nhận. | Đánh giá khả năng tiếp nhận và định tuyến. |
| Mean time to restore (MTTR) | Thời gian từ khi pipeline bị ảnh hưởng đến khi khôi phục theo tiêu chí đã định. | Đánh giá hiệu quả điều tra và xử lý. |
| Time to assign owner | Thời gian xác định nhóm/người chịu trách nhiệm. | Phát hiện khoảng trống ownership. |
| Failure classification accuracy | Tỷ lệ phân loại ban đầu phù hợp với nguyên nhân đã xác nhận. | Cải thiện triage và runbook. |
| Flaky rerun rate | Tỷ lệ thất bại ban đầu nhưng đạt khi chạy lại. | Nhận diện test không ổn định hoặc môi trường chập chờn. |
| Repeat incident rate | Tỷ lệ sự cố lặp lại cùng nguyên nhân. | Đánh giá hành động phòng ngừa. |
| Gate bypass/exception rate | Tỷ lệ pipeline có gate bị bỏ qua hoặc ngoại lệ. | Theo dõi rủi ro và chất lượng quản trị. |
| Pipeline availability | Tỷ lệ thời gian pipeline có thể thực thi các job cần thiết. | Đánh giá sức khỏe nền tảng CI. |

Cần định nghĩa rõ thời điểm bắt đầu và kết thúc của từng chỉ số. Ví dụ, MTTR có thể tính đến lúc runner hoạt động lại hoặc đến lúc tất cả kiểm tra bắt buộc trên commit bị ảnh hưởng đã hoàn tất; hai định nghĩa này đo hai kết quả khác nhau.

Không nên tối ưu MTTR bằng cách đóng incident sớm hoặc bỏ qua test. Kết quả cần được đọc cùng tỷ lệ lỗi lọt qua, số lần tái diễn và mức độ đầy đủ của bằng chứng.

## 17. Cải tiến sau sự cố

Sau khi pipeline được khôi phục, sự cố có ảnh hưởng đáng kể hoặc lặp lại cần được xem xét để ngăn tái diễn.

Một buổi review sau sự cố nên trả lời:

- Điều gì đã xảy ra và ảnh hưởng đến ai?
- Hệ thống phát hiện sự cố nhanh đến đâu?
- Cảnh báo có đến đúng owner không?
- Bằng chứng và runbook có đủ không?
- Có khoảng trống quyền truy cập hoặc quyền quyết định không?
- Vì sao nguyên nhân không được phát hiện sớm hơn?
- Biện pháp nào sẽ giảm khả năng xảy ra hoặc giảm tác động?
- Ai chịu trách nhiệm và thời hạn hoàn thành?

Hành động phòng ngừa có thể gồm:

- Thêm health check hoặc cảnh báo cho runner và dịch vụ phụ thuộc.
- Tự động định tuyến lỗi theo stage, test tag hoặc owner metadata.
- Cải thiện log và lưu artifact khi job thất bại.
- Bổ sung test hồi quy cho lỗi đã xác nhận.
- Cải thiện cô lập dữ liệu và môi trường.
- Tài liệu hóa cách khôi phục và kiểm tra quyền truy cập.
- Thêm cơ chế circuit breaker hoặc giới hạn retry khi phù hợp.
- Điều chỉnh lịch trực, escalation và phân công dự phòng.

Không nên chỉ ghi “cần cẩn thận hơn”. Hành động cần cụ thể, có owner, thời hạn và tiêu chí xác nhận hoàn tất.

## 18. Những sai lầm thường gặp

- **Cho rằng CI team sở hữu mọi lỗi pipeline:** nhiều lỗi thuộc mã nguồn, test, môi trường hoặc phụ thuộc.
- **Không chỉ định owner cho từng stage:** cảnh báo bị bỏ lại trong kênh chung.
- **Chỉ định nhiều người chịu trách nhiệm cuối cùng:** không rõ ai có quyền quyết định.
- **Retry đến khi pass:** che lỗi và làm mất bằng chứng ban đầu.
- **Tắt test để mở khóa release:** tạo khoảng trống kiểm soát không có người chấp nhận rủi ro.
- **Đóng incident khi runner hoạt động lại:** có thể còn test bắt buộc chưa chạy hoặc nguyên nhân chưa được kiểm soát.
- **Không lưu log và artifact:** mất bằng chứng để tái hiện.
- **Không có người thay thế khi owner vắng mặt:** sự cố chờ đến khi người duy nhất quay lại.
- **Escalation không có điều kiện:** thông báo quá nhiều hoặc không đến đúng cấp.
- **Không quản lý ngoại lệ có thời hạn:** bỏ qua gate trở thành trạng thái mặc định.
- **Đổ lỗi cá nhân:** làm giảm khả năng báo cáo sớm và học hỏi từ sự cố.
- **Không theo dõi hành động phòng ngừa:** cùng loại lỗi tiếp tục lặp lại.

## 19. Checklist xác định trách nhiệm khôi phục

- [ ] Mỗi pipeline và stage có owner chính và người thay thế.
- [ ] Test quan trọng có test owner và liên kết với yêu cầu/rủi ro.
- [ ] Thành phần, môi trường và phụ thuộc có owner được công bố.
- [ ] Release gate có người có thẩm quyền quyết định tiếp tục hoặc chặn.
- [ ] Ma trận RACI không mơ hồ về trách nhiệm cuối cùng.
- [ ] Cảnh báo chứa pipeline, stage, commit, job và liên kết bằng chứng.
- [ ] Có quy trình phân loại lỗi và gán incident owner.
- [ ] Có SLA phản hồi, escalation path và cơ chế bàn giao.
- [ ] Runbook mô tả bước điều tra, khôi phục và xác minh.
- [ ] Retry giữ lại kết quả lần đầu và không che lỗi.
- [ ] Quarantine hoặc bypass có owner, lý do, thời hạn và phê duyệt.
- [ ] Sau khắc phục, các gate bắt buộc được chạy lại trên đúng phiên bản.
- [ ] Incident có tiêu chí đóng và hành động phòng ngừa.
- [ ] Có đo lường MTTA, MTTR, lỗi lặp lại và tỷ lệ ngoại lệ.
- [ ] Trách nhiệm được rà soát khi kiến trúc, nhóm hoặc pipeline thay đổi.

## Kết luận

Khôi phục pipeline khi kiểm tra thất bại cần ownership rõ theo nền tảng CI, test, thành phần, môi trường và quyết định phát hành. Mỗi stage phải có đầu mối tiếp nhận, người chịu trách nhiệm cuối cùng, đường escalation và runbook phù hợp. Khi sự cố xảy ra, nhóm cần lưu bằng chứng, phân loại nguyên nhân, giao đúng owner, khắc phục và xác minh lại các gate bắt buộc trước khi tiếp tục. Retry, quarantine và ngoại lệ chỉ là biện pháp có kiểm soát, có thời hạn và có người chấp nhận rủi ro. Đo lường thời gian tiếp nhận, thời gian khôi phục và tỷ lệ sự cố lặp lại giúp cải thiện quy trình, tăng độ tin cậy của CI/CD và giảm gián đoạn phát triển.
