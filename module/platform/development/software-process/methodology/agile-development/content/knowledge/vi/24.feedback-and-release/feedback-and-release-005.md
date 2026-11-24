# Phản hồi và phát hành: Phát hành có kiểm soát bằng cờ tính năng và giới hạn phạm vi triển khai

Một nhóm đang phát triển nền tảng đăng ký workshop. Họ vừa viết xong màn hình trạng thái đăng ký mới: thay câu “Đã nhận yêu cầu” dễ gây hiểu nhầm bằng hai trạng thái rõ ràng **“Đang chờ xác nhận”** và **“Đã xác nhận chỗ”**. Các bài kiểm thử đạt, nhưng Product Owner lo rằng cách hiển thị mới có thể khiến một số học viên nghĩ mình bị từ chối. Developers muốn đưa mã lên production để kiểm tra sớm; nhóm vận hành không muốn bật đồng loạt cho toàn bộ người dùng rồi mới phát hiện sai lệch.

Có một cách làm hữu ích: **triển khai mã an toàn trước, nhưng chỉ cho một nhóm người dùng giới hạn nhìn thấy tính năng mới**, quan sát tín hiệu kỹ thuật và kết quả sử dụng, rồi mở rộng từng bước khi có đủ bằng chứng. Nếu xuất hiện vấn đề, nhóm cần có khả năng **ngừng hiển thị hoặc ngừng một hành vi mới** mà không phải luôn triển khai lại toàn bộ phiên bản phần mềm.

Đó là mục đích của **feature flags (cờ tính năng)** và **progressive delivery/controlled rollout (phát hành tăng dần có kiểm soát)**. Cờ tính năng là một cơ chế quyết định một nhánh hành vi có được kích hoạt trong bối cảnh cụ thể hay không. Giới hạn phạm vi triển khai (*limiting rollout scope / blast radius*) giúp giảm số người và hệ thống bị ảnh hưởng khi một giả định không đúng.

Tuy nhiên, **cờ tính năng không phải lá chắn bảo đảm an toàn tuyệt đối**. Nếu mã mới đã ghi dữ liệu sai, gửi thông báo sai hoặc phá tương thích schema, việc tắt cờ không tự phục hồi hậu quả. Một kế hoạch phát hành tốt kết hợp **Definition of Done, kiểm thử, tương thích ngược, quan sát, điều kiện dừng, cơ chế quay lui và trách nhiệm quyết định**.

Bài thuộc mô-đun **AGILE_DEVELOPMENT**: học Agile qua phản hồi sớm, giao phần mềm tăng dần, cải tiến liên tục, user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trọng tâm là **phát hành có kiểm soát bằng cờ tính năng và giới hạn phạm vi triển khai**, từ thiết kế đến vận hành và quyết định dựa trên bằng chứng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt rõ **build, deploy, release/exposure, rollout, rollback** và **kiểm chứng giá trị**.
2. Giải thích cơ chế feature flag, các loại cờ và lý do nên tách thời điểm đưa mã vào môi trường khỏi thời điểm người dùng được trải nghiệm.
3. Thiết kế cờ có **tên, owner, mặc định an toàn, phạm vi, vòng đời, điều kiện kích hoạt/tắt** và khả năng quan sát phù hợp.
4. So sánh **internal rollout, canary, percentage rollout, ring-based rollout, blue–green, dark launch, shadow traffic** và **A/B testing** theo mục đích.
5. Xác định phạm vi ảnh hưởng (*blast radius*), các rủi ro không thể chữa chỉ bằng tắt cờ và cách giảm rủi ro trước khi phát hành.
6. Lập kế hoạch mở dần tính năng qua các cohort với điều kiện **go / pause / rollback** dựa trên guardrails và dữ liệu đủ tin cậy.
7. Triển khai một nhánh cờ tính năng đơn giản và kiểm thử cả trạng thái **ON/OFF**, tính ổn định của cohort, đường dự phòng.
8. Hiểu **sticky assignment**, vấn đề tỷ lệ phân bổ, cache/propagation delay, fail-safe defaults, dữ liệu nhạy cảm và nhiều cờ phụ thuộc nhau.
9. Áp dụng **expand–migrate–contract**, tương thích ngược, idempotency và kế hoạch phục hồi đối với thay đổi dữ liệu hoặc tác dụng phụ bên ngoài.
10. Gắn việc phát hành kiểm soát với Product Goal, Sprint Review, backlog, DoD, Kanban flow, XP/CI và phản hồi người dùng.
11. Phân tích tình huống có lỗi trong một đợt rollout giới hạn, chọn hành động đúng và rút kinh nghiệm.
12. Tự tạo một **release plan, runbook và checklist** có thể sử dụng trong nhóm.

## 2. Tách triển khai phần mềm khỏi kích hoạt tính năng

### 2.1. Các mốc thường bị gọi chung là “release”

| Khái niệm | Câu hỏi | Ví dụ với màn hình trạng thái workshop |
| --- | --- | --- |
| **Build** | Mã và cấu hình đã được đóng gói thành phiên bản nào? | Build chứa cả giao diện cũ và mới |
| **Deploy** | Phiên bản nào đã được đưa vào môi trường chạy? | Ứng dụng có mã giao diện mới được triển khai lên production |
| **Enable** | Điều kiện nào khiến nhánh hành vi mới được kích hoạt? | Flag bật cho nhân viên thử nghiệm |
| **Release / expose** | Người dùng mục tiêu nào thực sự được tiếp xúc tính năng? | 5% học viên đủ điều kiện thấy trạng thái mới |
| **Rollout** | Phạm vi tiếp xúc được mở rộng/thu hẹp theo những giai đoạn nào? | 5% → 25% → 50% → 100%, có điểm kiểm tra |
| **Observe** | Điều gì xảy ra khi người dùng thật tương tác? | Tỷ lệ hiểu đúng, số lần hỏi lại, lỗi API |
| **Rollback / disable** | Nếu kết quả xấu, nhóm quay về trạng thái an toàn bằng cách nào? | Tắt flag nhánh giao diện mới hoặc rollback phiên bản nếu cần |

**Deploy thành công không đồng nghĩa release thành công.** Một phiên bản có thể đã chạy trên production nhưng tính năng vẫn tắt. Ngược lại, một cờ được bật không chứng minh người dùng đã nhìn thấy hoặc sử dụng tính năng: còn có điều kiện phân nhóm, quyền, đường dẫn và trạng thái thực tế.

### 2.2. Luồng phát hành có kiểm soát

~~~mermaid
flowchart TD
    A[User story và tiêu chí chấp nhận] --> B[Code, test, tích hợp, Definition of Done]
    B --> C[Deploy mã có flag mặc định phù hợp]
    C --> D[Kiểm tra đường cũ và điều kiện bật]
    D --> E[Bật cho cohort thử nghiệm nhỏ]
    E --> F[Quan sát guardrails, chất lượng và outcome]
    F --> G{Đủ bằng chứng để mở rộng?}
    G -->|Có| H[Tăng phạm vi exposure theo kế hoạch]
    G -->|Chưa rõ| I[Giữ nguyên, điều tra hoặc bổ sung dữ liệu]
    G -->|Không an toàn| J[Tạm dừng/tắt flag, xử lý sự cố]
    H --> F
    I --> F
    J --> K[Xác minh hệ thống và dữ liệu, sửa và học]
    K --> B
~~~

Sơ đồ là **một mô hình thực hành**, không phải một chuỗi sự kiện bắt buộc của Scrum. Một lỗi production nghiêm trọng phải được xử lý theo chính sách sự cố ngay, không chờ đủ các điểm duyệt của kế hoạch rollout.

### 2.3. Vì sao tách deploy và exposure có giá trị?

- **Giảm mức phơi nhiễm ban đầu:** chỉ một phần người dùng trải nghiệm hành vi mới khi còn điều chưa chắc.
- **Kiểm tra sản phẩm thật:** dễ nhìn tác động với người dùng, dữ liệu và vận hành trong phạm vi kiểm soát.
- **Cho phép triển khai thường xuyên:** mã có thể được tích hợp và phát hành kỹ thuật mà chưa bật toàn bộ hành vi nghiệp vụ.
- **Điều phối thời điểm ra mắt:** Product Owner và bên liên quan có thể chọn thời điểm exposure dựa trên giá trị và sẵn sàng hỗ trợ.
- **Hỗ trợ thử nghiệm:** so sánh hành vi cũ/mới khi có thiết kế đo lường hợp lệ.
- **Dừng nhanh một nhánh tính năng:** có thể hữu ích khi phát hiện lỗi trong phần được bật, nếu nhánh cũ còn an toàn.

Những lợi ích này có **chi phí thiết kế và vận hành**: nhiều nhánh mã, phức tạp kiểm thử, cấu hình và trạng thái bị lệch. Không phải thay đổi nhỏ nào cũng cần cờ tính năng.

## 3. Cờ tính năng là gì và không phải là gì?

**Feature flag** là một quyết định có thể được cấu hình hoặc đánh giá tại thời điểm chạy, dùng để chọn **hành vi có thể được thực hiện** dựa trên **tên cờ và ngữ cảnh** như môi trường, nhóm dùng thử, user/tenant hoặc điều kiện nghiệp vụ.

Ví dụ với giao diện:

~~~text
Nếu status-page-v2 = ON đối với người dùng hiện tại:
    Trình bày trạng thái đăng ký bằng giao diện mới
Ngược lại:
    Giữ cách hiển thị đã được xác minh trước đó
~~~

### 3.1. Các loại cờ có mục đích khác nhau

| Loại | Mục đích | Ví dụ | Vòng đời thường gặp |
| --- | --- | --- | --- |
| **Release flag** | Ẩn hoặc mở dần một tính năng mới | status-page-v2 | Thường tạm thời, xóa sau khi rollout ổn định |
| **Experiment flag** | Phân nhóm trải nghiệm để đo giả thuyết | copy-status-experiment | Gắn thời gian thử, quyết định kết thúc và làm sạch |
| **Operational / kill-switch flag** | Giảm tác động của một tính năng hoặc tích hợp khi lỗi | enable-bulk-email-send | Có thể tồn tại lâu hơn nếu là cơ chế vận hành có giá trị |
| **Permission/entitlement flag** | Bật khả năng theo gói/quyền/cấp độ khách hàng | enable-premium-report | Chỉ là một thành phần trong hệ thống kiểm soát quyền |
| **Migration/compatibility flag** | Hỗ trợ chuyển dần giữa hai cơ chế | use-new-notification-adapter | Tạm thời tới khi hoàn tất migration |
| **Prerequisite flag** | Một tính năng phụ thuộc tính năng nền đã bật | new-receipt requires new-checkout | Cần chính sách phụ thuộc minh bạch |

**Quan trọng:** cờ hiển thị hoặc một điều kiện phía client **không phải cơ chế phân quyền bảo mật**. Các thao tác có dữ liệu nhạy cảm hoặc chức năng giới hạn phải được **kiểm tra quyền phía server** theo chính sách độc lập với UI. Cờ entitlement có thể hỗ trợ lựa chọn sản phẩm, nhưng không thay thế authentication/authorization.

### 3.2. Cờ tính năng và cấu hình thông thường

Cấu hình như địa chỉ endpoint, timeout hoặc giới hạn bộ nhớ thường phục vụ vận hành. Cờ tính năng thường phục vụ **thay đổi hành vi, kiểm soát exposure và quản lý một lựa chọn theo đối tượng**. Ranh giới không tuyệt đối: một vài operational flag cũng là cấu hình động.

Hãy hỏi: “Thay đổi này có cần hai nhánh tồn tại cùng lúc và khả năng bật/tắt theo cohort, thời điểm hoặc mức rủi ro không?”. Nếu không, **một cấu hình rõ hoặc một thay đổi mã trực tiếp** có thể đơn giản và dễ bảo trì hơn.

### 3.3. Không phải mọi cờ đều an toàn để tắt

Có hai kiểu khác nhau:

1. **Cờ chọn đường hiển thị:** bật giao diện mới, tắt trở về giao diện cũ, dữ liệu nền không thay đổi. Rủi ro quay lui thường thấp hơn.
2. **Cờ điều khiển hành vi có tác dụng phụ:** đổi cách xác nhận thanh toán, ghi dữ liệu, gửi email/SMS hoặc migrate schema. Việc tắt cờ có thể **không hoàn tác các tác dụng đã xảy ra**.

Nếu hành vi mới có thể gây tác dụng phụ không thể đảo ngược, nhóm phải thiết kế **transaction, idempotency, tương thích, phương án phục hồi và điều kiện an toàn** trước khi dựa vào kill switch.

## 4. Giới hạn phạm vi ảnh hưởng: blast radius

**Blast radius** là phạm vi người dùng, dữ liệu, hệ thống hoặc quy trình có thể bị ảnh hưởng khi một thay đổi gặp lỗi. Giới hạn phạm vi rollout nhằm giảm mức ảnh hưởng **trong lúc nhóm còn đang học từ production**.

### 4.1. Phạm vi không chỉ đo bằng tỷ lệ người dùng

Có thể giới hạn theo:
- **Người dùng:** nhân viên, nhóm tự nguyện thử, một tỷ lệ người dùng đủ điều kiện.
- **Tổ chức/tenant:** vài đơn vị khách hàng chấp nhận dùng thử.
- **Khu vực hoặc môi trường:** khu vực triển khai, cụm hạ tầng, nền tảng thiết bị.
- **Tác vụ/nghiệp vụ:** chỉ một loại workshop hoặc một luồng ít rủi ro.
- **Dữ liệu:** một tập dữ liệu không nhạy cảm hoặc môi trường thử an toàn.
- **Lưu lượng:** một phần request hoặc cơ chế shadow traffic có giới hạn.
- **Thời gian:** một cửa sổ quan sát có người trực hỗ trợ.
- **Chức năng con:** chỉ bật cải thiện hiển thị, chưa bật việc gửi thông báo chủ động.

Không nên chọn cohort “5%” nếu **5% đó vẫn chứa toàn bộ khách hàng có hậu quả kinh doanh lớn** hoặc nếu thay đổi là **một tác vụ ghi dữ liệu chung gây hại cho toàn hệ thống**.

### 4.2. Một khung đánh giá rủi ro đơn giản

~~~text
Mức tổn hại tiềm năng phụ thuộc vào:
- Mức độ nghiêm trọng của lỗi.
- Số người / hệ thống / dữ liệu có thể bị ảnh hưởng.
- Thời gian từ khi lỗi xuất hiện đến khi được phát hiện và giảm thiểu.
- Khả năng phục hồi, cách quay lui và tác dụng phụ đã phát sinh.
~~~

Đây không phải công thức xác suất đã được hiệu chuẩn. **Rollout nhỏ thường giảm phạm vi tiếp xúc trực tiếp**, nhưng không bảo đảm giảm rủi ro theo tỷ lệ tuyến tính. Một lỗi shared database hoặc queue dùng chung vẫn có thể ảnh hưởng người dùng ngoài cohort.

### 4.3. Ví dụ cụ thể

Một hệ thống có 20.000 học viên đủ điều kiện dùng tính năng trạng thái mới. Bật cho 5% theo định nghĩa cohort hiện tại tương đương **khoảng 1.000 học viên** có thể được phân vào nhánh mới.

Nhưng:
- Không phải cả 1.000 người đều mở màn hình trong thời gian quan sát.
- Chỉ số lỗi cần dùng **số người thực sự exposure hoặc số request phù hợp** làm mẫu số.
- Nếu phần hiển thị mới ghi lại một trường dữ liệu chia sẻ, những người không bật cờ vẫn có thể chịu hậu quả.
- Nếu cohort lấy theo tenant, một tenant lớn có thể chiếm phần lớn lưu lượng dù tỷ lệ tenant rất nhỏ.

**Giới hạn cohort là một lớp bảo vệ, không thay cho phân tích phụ thuộc và đường dữ liệu.**

## 5. Thiết kế một cờ tính năng có trách nhiệm

Đặt cờ bằng một tên dễ hiểu chưa đủ. Một cờ cần có **quyền sở hữu, chính sách đánh giá, đường dự phòng và kế hoạch kết thúc**.

### 5.1. Những trường cần thống nhất

| Trường | Nội dung | Ví dụ minh họa |
| --- | --- | --- |
| **Key** | Định danh duy nhất, ổn định | registration-status-v2 |
| **Mục đích** | Vấn đề hoặc hypothesis đang giải quyết | Giảm hiểu nhầm “đã nhận” là “đã có chỗ” |
| **Owner** | Ai chịu trách nhiệm quyết định mở rộng/tắt và làm sạch | Product Owner + technical owner theo vai trò |
| **Kiểu cờ** | Release, experiment, operational, migration… | Release flag |
| **Mặc định** | Khi chưa bật/không có cấu hình thì làm gì? | Nhánh trạng thái cũ đã kiểm chứng |
| **Điều kiện đủ** | Người dùng và môi trường nào có thể tiếp xúc? | Production, học viên thuộc cohort thử |
| **Ưu tiên quy tắc** | Khi có nhiều điều kiện, quy tắc nào thắng? | Emergency OFF > eligibility > percentage |
| **Bật/tắt khi nào** | Tiêu chí go/pause/stop | Có guardrails và dữ liệu đáng tin |
| **Giới hạn phụ thuộc** | Flag nào cần bật trước, dữ liệu nào cần tương thích? | Giao diện mới cần API trạng thái ổn định |
| **Quan sát** | Ghi exposure, lỗi, latency và kết quả theo cohort ra sao? | Metric có flag variant, không lộ PII |
| **Thời hạn** | Khi nào phải review và xóa flag? | Sau rollout ổn định và cleanup |
| **Đường quay lui** | Tắt cờ có đủ không? Cần rollback code/data? | Trở lại trình bày cũ, kiểm tra dữ liệu |
| **Runbook** | Ai có quyền thao tác và cách xác minh? | Quy trình pause/disable trong on-call |

### 5.2. Một luật đánh giá minh bạch

Ví dụ chính sách:

~~~text
Nếu môi trường không phải production:
    Theo cấu hình thử nghiệm riêng của môi trường
Ngược lại nếu emergency-disable = TRUE:
    Trả OFF cho tất cả
Ngược lại nếu người dùng không đủ điều kiện:
    Trả OFF
Ngược lại nếu thuộc nhóm internal-test đã cho phép:
    Trả ON
Ngược lại nếu nằm trong tỷ lệ rollout hiện tại:
    Trả ON
Ngược lại:
    Trả OFF
~~~

Chính sách này chỉ minh họa. Cần công bố **thứ tự ưu tiên giữa các quy tắc**, đặc biệt khi có internal override, tenant override, percentage và emergency-off. Không để hai người cùng đọc cờ nhưng hiểu điều kiện khác nhau.

### 5.3. Mặc định an toàn khi cấu hình không sẵn sàng

Các lựa chọn thường gặp:
- **Fail closed / OFF:** không bật nhánh mới khi không thể lấy cờ; phù hợp khi nhánh cũ còn an toàn và không gây hậu quả mới.
- **Dùng giá trị gần nhất đã xác minh:** có thể cần với ứng dụng không kết nối liên tục, nhưng phải chấp nhận thời gian cờ lan truyền.
- **Fail theo chính sách bảo vệ hệ thống:** với cờ liên quan bảo mật hoặc giới hạn rủi ro, quyết định không được chỉ dựa một boolean trong service bên ngoài.

**Không có mặc định OFF đúng cho mọi cờ.** Nếu một cờ dùng để chặn hoạt động độc hại mà thiếu cấu hình lại mở đường nguy hiểm, phải thiết kế chế độ an toàn thích hợp ngay từ đầu. Cũng không nên đặt logic phân quyền vào cờ UI rồi coi nó là rào chắn bảo mật.

### 5.4. Cờ có vòng đời, không phải cấu hình vĩnh viễn

Một release flag đã bật 100% và ổn định nhưng còn mã nhánh cũ trong nhiều năm sẽ:
- Tạo thêm số trường hợp phải test.
- Làm khó refactoring.
- Có thể khiến một lần đổi cấu hình bật lại mã cũ chưa còn tương thích.
- Tăng phức tạp khi onboarding và điều tra lỗi.
- Tạo nợ kỹ thuật cấu hình.

Cần **mốc review và kế hoạch xóa**: chỉ giữ operational/entitlement flags lâu dài khi chúng có mục đích rõ. Việc xóa cờ cũng là thay đổi mã cần test và rollout như một thay đổi có rủi ro phù hợp.

## 6. Những chiến lược mở dần tính năng

### 6.1. Các phương pháp không hoàn toàn tương đương

| Phương pháp | Cách hoạt động | Phù hợp khi | Lưu ý |
| --- | --- | --- | --- |
| **Internal/dogfood rollout** | Nhân viên hoặc nhóm nội bộ trải nghiệm trước | Kiểm tra luồng cơ bản, vận hành, hỗ trợ | Người nội bộ không đại diện mọi người dùng |
| **Allowlist / pilot cohort** | Chọn người hoặc tenant cụ thể | Cần hỗ trợ sát và thu phản hồi sâu | Có thể thiên lệch theo khách hàng tự nguyện |
| **Percentage rollout** | Bật cho một tỷ lệ đối tượng đủ điều kiện | Muốn tăng phơi nhiễm từng bước | Cần cohort ổn định và mẫu số rõ |
| **Ring-based rollout** | Mở theo vòng như nội bộ → thử nghiệm → khách hàng rộng | Mức rủi ro của từng nhóm khác nhau | Vòng đầu ít đại diện vòng sau |
| **Canary release** | Đưa thay đổi tới phạm vi nhỏ, quan sát so với hiện trạng | Kiểm tra rủi ro của thay đổi thực tế | Cần guardrails, khả năng tắt/rollback |
| **Blue–green deployment** | Duy trì hai môi trường triển khai và chuyển lưu lượng | Giảm gián đoạn khi đổi phiên bản | Không tự giải quyết schema/data migration |
| **Dark launch** | Đưa thành phần mới chạy ở hậu trường, chưa hiện trải nghiệm | Kiểm tra năng lực hoặc tính sẵn sàng | Có thể vẫn gây tải/tác dụng phụ nếu thiết kế kém |
| **Shadow traffic** | Bản sao request đi qua hệ thống mới nhưng không quyết định kết quả thật | So sánh xử lý và hiệu năng | Phải tránh ghi dữ liệu/tác dụng phụ thật, bảo vệ PII |
| **A/B experiment** | Phân nhóm để đo tác động nhân quả của hai biến thể theo thiết kế phù hợp | Có giả thuyết sản phẩm và đủ dữ liệu | Không đồng nghĩa chỉ với percentage rollout |

**Feature flag** là một công cụ hỗ trợ nhiều phương pháp, **không phải tên gọi thay thế cho canary, A/B hay blue–green**. Một thay đổi hạ tầng có thể canary bằng định tuyến traffic mà không có cờ trong mã ứng dụng. Một cờ A/B có thể cố định phân nhóm để đo outcome dù mã đã được deploy toàn bộ.

### 6.2. Rollout theo tỷ lệ có điều kiện

Ví dụ nhịp mở rộng **minh họa**:

| Giai đoạn | Phạm vi | Câu hỏi cần trả lời trước khi mở thêm |
| --- | --- | --- |
| **0. Đường cũ** | Flag OFF cho người dùng thật | Nhánh cũ, fallback và tính tương thích có còn hoạt động? |
| **1. Nội bộ** | Nhân viên hoặc tài khoản thử | Có lỗi nghiệp vụ, quyền hoặc dữ liệu rõ ràng không? |
| **2. Canary nhỏ** | 1% đủ điều kiện | Có lỗi nghiêm trọng, latency xấu hoặc hành vi bất thường? |
| **3. Mở thận trọng** | 5% | Có đủ lượt exposure và bằng chứng để đánh giá guardrails? |
| **4. Mở trung bình** | 25% | Phân nhóm mới có khác nhiều về thiết bị, tải, đối tượng? |
| **5. Mở rộng** | 50% | Có lỗi tích lũy, bão hòa hạ tầng hoặc tác dụng theo cohort không? |
| **6. Phổ biến** | 100% đủ điều kiện | Giá trị có đạt, hỗ trợ và vận hành đã sẵn sàng? |
| **7. Cleanup** | Bỏ nhánh cũ và flag tạm | Có test hồi quy, migration và người chịu trách nhiệm? |

**Không có quy định phải dùng chuỗi 1–5–25–50–100**. Một hệ thống ít người dùng có thể không thu đủ tín hiệu trong một giờ ở 1%. Một lỗi an toàn không cho phép chuyển lên 100% chỉ vì đã đến mốc lịch. Giai đoạn và thời gian quan sát phải căn cứ rủi ro, lưu lượng, điều kiện ra quyết định và người trực.

### 6.3. Rollout từng vòng và cohort sản phẩm

Nhóm có thể chọn:
- **Ring 0:** tài khoản thử/công cụ nội bộ, dữ liệu không nhạy cảm.
- **Ring 1:** khách hàng pilot có kênh hỗ trợ rõ.
- **Ring 2:** người dùng đủ điều kiện với tỷ lệ nhỏ.
- **Ring 3:** phần lớn người dùng.
- **Ring 4:** toàn bộ đối tượng phù hợp.

Ưu điểm của ring là kiểm soát **độ sẵn sàng hỗ trợ và mức độ rủi ro**. Nhược điểm: nhóm pilot thường có năng lực, thiết bị hoặc hành vi khác người dùng phổ thông. Phải xem liệu kết quả vòng trước có **áp dụng được** cho vòng sau hay không.

### 6.4. Không bật cho toàn bộ người dùng chỉ vì 100% mục tiêu

Khi lên 100%, nhóm vẫn phải:
- Kiểm tra những **phân khúc đặc biệt** chưa xuất hiện ở cohort trước.
- Xem backend, cache, queue và nhà cung cấp có đủ sức chịu lưu lượng mới.
- Sẵn sàng xử lý kịch bản người dùng đã ở nhánh mới quay về nhánh cũ.
- Kiểm tra hỗ trợ khách hàng và thông điệp sản phẩm.
- Theo dõi sau mở rộng, không ngừng quan sát ngay lúc đạt 100%.

**100% exposure không tự có nghĩa Product Goal đã đạt**; người dùng có thể tiếp xúc nhưng chưa sử dụng hoặc không nhận giá trị.

## 7. Phân nhóm ổn định và đánh giá cờ nhất quán

### 7.1. Tại sao phải có sticky assignment?

Giả sử người dùng A mở màn hình trạng thái lần đầu và thấy giao diện mới. Lần sau họ thấy giao diện cũ, dù không đổi tài khoản, vì hệ thống mỗi request tung số ngẫu nhiên mới để quyết định 5% rollout. Người dùng có thể bối rối; số liệu exposure và lỗi cũng khó diễn giải.

**Sticky assignment** là cách giữ người hoặc đơn vị phân nhóm ổn định theo một quy tắc, trong khoảng thử đã xác định. Thường sử dụng:
- Một **subject key** ổn định như user ID nội bộ hoặc tenant ID phù hợp.
- Một **salt/namespace** riêng cho cờ hoặc thử nghiệm.
- Một cơ chế phân bucket xác định, không thay ngẫu nhiên ở mỗi request.
- Chính sách rõ khi người dùng chưa đăng nhập, đổi tài khoản hoặc đổi tenant.

### 7.2. Mô hình bucket minh họa

~~~text
subjectKey = định danh ổn định theo phạm vi rollout
flagKey = "registration-status-v2"
salt = phiên bản/quy tắc phân nhóm được quản lý

bucket = stableHash(flagKey + salt + subjectKey)
         quy về số nguyên trong khoảng [0, 9999]

Bật nếu:
    subject đủ điều kiện
    AND bucket < percentage * 100
    AND không bị emergency-disable

Ví dụ:
    percentage = 5
    threshold = 500
    bucket 0..499 -> ON (xấp xỉ 5% với hàm phân phối tốt)
~~~

Đây là **pseudocode**, không phải thuật toán mật mã hoặc hàm hash được khuyến nghị cho production. Hệ thống thật cần đánh giá **khả năng phân phối, tính ổn định, chống lộ dữ liệu, điều kiện phân nhóm và tương thích giữa các phiên bản**.

### 7.3. Không thể coi kết quả chia bucket luôn đúng chính xác tỷ lệ

Một quy tắc đặt ngưỡng 5% thường mang tính **kỳ vọng trên tập đủ lớn**, không bảo đảm mọi nhóm 20 người có đúng một người ON. Với 20.000 người đủ điều kiện, số được chọn có thể gần 1.000 tùy phân phối; **số exposure thực tế** còn phụ thuộc việc người dùng có truy cập tính năng hay không.

Cần phân biệt:
- **Eligible:** thỏa điều kiện có thể tham gia.
- **Assigned:** được phân vào một biến thể theo quy tắc.
- **Exposed:** thực sự đi qua nhánh hành vi đó.
- **Engaged:** thực sự tương tác đủ để tính chỉ số hành vi.

Không dùng số eligible làm mẫu số mặc định cho mọi tỷ lệ lỗi hoặc outcome.

### 7.4. Tăng tỷ lệ rollout cần giữ tập đã bật nhất quán khi có thể

Với một hàm bucket và salt không đổi, tăng ngưỡng từ 5% lên 25% thường giữ nguyên 5% ban đầu và bổ sung đối tượng mới. Nếu thay salt, thuật toán hoặc subject key giữa đợt, một số người có thể bị chuyển nhánh ngoài ý muốn.

Đối với **A/B experiment** cần đo tác động, thay đổi allocation hoặc phân nhóm giữa chừng còn có thể làm phức tạp phân tích. Phải ghi rõ phiên bản quy tắc, thời gian và quần thể tham gia.

### 7.5. Đơn vị phân nhóm phải phù hợp tác động

Nếu một tenant có nhiều người dùng cùng thao tác trên dữ liệu dùng chung, việc phân theo **từng người** có thể khiến cùng một đơn hàng nhìn thấy bởi hai giao diện có hành vi không tương thích. Có khi phải phân theo **tenant, workspace hoặc tài khoản** để tránh trạng thái trộn.

Quy tắc chọn đơn vị:
1. Hành vi mới có tác động chia sẻ ở phạm vi nào?
2. Ai cần trải nghiệm nhất quán?
3. Cấu trúc dữ liệu có hỗ trợ hai nhánh đồng thời không?
4. Rủi ro thiên lệch khi phân theo tenant là gì?
5. Nếu một tổ chức lớn, một tenant có thể làm tăng lưu lượng được bật bao nhiêu?

### 7.6. Dữ liệu cá nhân không được biến thành metadata vô hạn

Nhật ký đánh giá cờ và sự kiện exposure có thể chứa dữ liệu nhạy cảm nếu nhóm ghi trực tiếp email, số điện thoại hoặc nội dung đăng ký. Hãy ưu tiên định danh nội bộ phù hợp, giới hạn retention, kiểm soát truy cập và chỉ thu các thuộc tính cần thiết.

**Không gửi dữ liệu cá nhân tới nhà cung cấp quản lý cờ bên ngoài nếu chưa có cơ sở, chính sách và đánh giá phù hợp.** Các yêu cầu pháp lý/quyền riêng tư phải được xác nhận theo tổ chức và nơi sản phẩm hoạt động.

## 8. Ví dụ Java: tách lựa chọn giao diện khỏi quy tắc nghiệp vụ

Cờ dễ thử nhất là cờ **chọn cách trình bày** trong khi các bất biến nghiệp vụ và quyền truy cập vẫn được bảo vệ độc lập. Ví dụ minh họa Java 17/JUnit 5 dưới đây không gửi thông báo, không cập nhật database và không thay đổi quyết định có chỗ.

### 8.1. Hợp đồng đánh giá cờ

~~~java
public interface FeatureFlags {
    boolean isEnabled(String flagKey, String subjectKey);
}
~~~

Lớp hiển thị trạng thái chỉ phụ thuộc vào hợp đồng này:

~~~java
import java.util.Objects;

public final class RegistrationStatusPresenter {
    private static final String FLAG = "registration-status-v2";
    private final FeatureFlags flags;

    public RegistrationStatusPresenter(FeatureFlags flags) {
        this.flags = Objects.requireNonNull(flags);
    }

    public String labelFor(String subjectKey, RegistrationStatus status) {
        Objects.requireNonNull(subjectKey);
        Objects.requireNonNull(status);

        // Quyền xem registration phải được kiểm tra bởi service/API
        // trước khi gọi presenter; đây không phải authorization logic.
        if (flags.isEnabled(FLAG, subjectKey)) {
            return switch (status) {
                case PENDING -> "Đang chờ xác nhận";
                case CONFIRMED -> "Đã xác nhận chỗ";
                case REJECTED -> "Không được xác nhận";
            };
        }

        return switch (status) {
            case PENDING -> "Đã tiếp nhận yêu cầu";
            case CONFIRMED -> "Đã có chỗ";
            case REJECTED -> "Yêu cầu không thành công";
        };
    }
}
~~~

Enum mô tả trạng thái trong cùng ví dụ:

~~~java
public enum RegistrationStatus {
    PENDING, CONFIRMED, REJECTED
}
~~~

Ý tưởng thiết kế:
- **RegistrationStatus** là trạng thái nghiệp vụ duy nhất; cờ chỉ thay đổi **cách trình bày**.
- Presenter không tự ghi dữ liệu, xác nhận chỗ, gửi SMS hay thay đổi quyền.
- Có thể tiêm evaluator giả trong test để kiểm tra hai nhánh.
- Mã nhánh cũ cần được xóa sau khi release flag hoàn thành vòng đời.
- Việc bảo vệ quyền xem một đăng ký là trách nhiệm độc lập phía server.

**Chú ý:** mã ví dụ giả định tính năng không cần fallback khi evaluator lỗi. Triển khai production phải xác định cách xử lý mất kết nối dịch vụ cờ, cache và giá trị mặc định theo chính sách; không để lỗi đánh giá cờ làm gián đoạn toàn bộ request nếu có thể thiết kế an toàn.

### 8.2. Kiểm thử cả ON và OFF

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class RegistrationStatusPresenterTest {

    @Test
    void presentsNewPendingLabelWhenFlagOn() {
        FeatureFlags flags = (key, subject) -> true;
        RegistrationStatusPresenter presenter =
            new RegistrationStatusPresenter(flags);

        assertEquals(
            "Đang chờ xác nhận",
            presenter.labelFor("user-100", RegistrationStatus.PENDING)
        );
    }

    @Test
    void preservesOldLabelWhenFlagOff() {
        FeatureFlags flags = (key, subject) -> false;
        RegistrationStatusPresenter presenter =
            new RegistrationStatusPresenter(flags);

        assertEquals(
            "Đã tiếp nhận yêu cầu",
            presenter.labelFor("user-100", RegistrationStatus.PENDING)
        );
    }

    @Test
    void confirmedRemainsConfirmedInBothBranches() {
        RegistrationStatusPresenter oldPresenter =
            new RegistrationStatusPresenter((key, subject) -> false);
        RegistrationStatusPresenter newPresenter =
            new RegistrationStatusPresenter((key, subject) -> true);

        assertEquals(
            "Đã có chỗ",
            oldPresenter.labelFor("user-100", RegistrationStatus.CONFIRMED)
        );
        assertEquals(
            "Đã xác nhận chỗ",
            newPresenter.labelFor("user-100", RegistrationStatus.CONFIRMED)
        );
    }
}
~~~

Những test này bảo vệ **hợp đồng trình bày**; chúng chưa chứng minh người dùng hiểu đúng trạng thái, không có lỗi truy cập, hoặc hệ thống bảo vệ sức chứa. Cần những kiểm thử và phép quan sát khác tương ứng.

### 8.3. Kiểm thử luật rollout ngoài presenter

Nếu team tạo một evaluator tính tỷ lệ, nên kiểm:
- Với **0%**, tất cả đối tượng đủ điều kiện đều OFF.
- Với **100%**, tất cả đối tượng đủ điều kiện đều ON nếu không có override chặn.
- Cùng flag, subject, salt và cấu hình thì **quyết định ổn định**.
- Người không đủ điều kiện **luôn OFF**.
- **Emergency OFF** thắng mọi rule khác theo chính sách đã chọn.
- Tăng ngưỡng từ 5% lên 25% không làm những subject đã ON chuyển OFF nếu thuật toán/tập điều kiện không đổi.
- Dữ liệu thiếu, định danh rỗng hoặc evaluator lỗi được xử lý theo chính sách an toàn.
- Không lộ email/số điện thoại qua log đánh giá.

Không nên chỉ viết test “5% có 5 trong 100 ID ON” nếu thuật toán không cam kết chính xác điều đó. Kiểm thử thống kê và phân phối cần dựa mô hình hash thực, không ép mọi mẫu nhỏ đúng tuyệt đối.

### 8.4. Kiểm thử tổ hợp cờ bằng mức độ rủi ro

Nếu tính năng có ba cờ độc lập, số tổ hợp ON/OFF lý thuyết là **2³ = 8**. Với mười cờ, là **2¹⁰ = 1.024**. Vì vậy, **cờ tạm thời tích lũy tạo chi phí kiểm thử tăng nhanh**.

Cách giảm:
- Gộp hoặc làm rõ cờ trùng mục đích.
- Định nghĩa dependencies/prerequisites rõ.
- Test các tổ hợp **hợp lệ và có rủi ro cao**, không mặc định thử mọi tổ hợp không thể xuất hiện.
- Xóa release flags hết hạn.
- Ghi rõ môi trường và phiên bản cờ khi lỗi xảy ra.

Đây là lý do quan trọng không nên giữ mọi nhánh cũ vô thời hạn.

## 9. Điều kiện sẵn sàng trước khi bật cho người dùng thật

**Flag OFF khi deploy không cho phép bỏ qua tiêu chuẩn phát triển.** Code đã được triển khai có thể ảnh hưởng quá trình khởi tạo, dependency, schema, tài nguyên và pipeline dù chưa ai vào nhánh ON.

### 9.1. Các lớp readiness

| Lớp | Điều cần sẵn sàng | Ví dụ |
| --- | --- | --- |
| **Nghiệp vụ** | User story, acceptance criteria, Product Goal rõ | Trạng thái không bị hiểu sai nghĩa xác nhận |
| **Chất lượng code** | Review, unit/integration tests, DoD phù hợp | Cả hai nhánh ON/OFF chạy đúng |
| **Dữ liệu** | Tương thích schema, quy tắc ghi/đọc, migration an toàn | Giao diện cũ vẫn đọc được dữ liệu mới |
| **Bảo mật** | Quyền xem/sửa được bảo vệ độc lập | Không thể xem đăng ký của người khác |
| **Quan sát** | Metric, log, trace, phân nhóm và mẫu số đủ | Biết tỷ lệ lỗi ở ON so với OFF |
| **Vận hành** | Chủ sở hữu, quyền thao tác, runbook, giờ trực | Biết tắt cờ an toàn và kiểm chứng |
| **Phục hồi** | Fallback, rollback code/data, điều kiện dừng | Không phụ thuộc kill switch để sửa dữ liệu sai |
| **Hỗ trợ khách hàng** | Thông điệp và kênh tiếp nhận phản hồi | Nhân viên hỗ trợ biết hai giao diện đang tồn tại |

### 9.2. Kiểm tra cả nhánh cũ

Lỗi phổ biến: nhóm chỉ test ON vì “OFF là code cũ đã chạy từ trước”. Nhưng mã cũ có thể bị ảnh hưởng bởi:
- Dependency được nâng cấp.
- Schema/contract API thay đổi.
- Thay đổi shared component hoặc config.
- Chuyển tuyến traffic, cache và auth.
- Mã refactor dùng chung.

Vì vậy cần **regression tests cho OFF**, ít nhất ở những đường có rủi ro và tích hợp quan trọng. Một cờ mang lại rollback hữu ích **chỉ khi đường cũ còn hoạt động được**.

### 9.3. Tình huống không nên dùng rollout nhỏ như lý do phát hành

Đừng bật ngay cả cho 1% nếu:
- Biết có nguy cơ lộ dữ liệu cá nhân chưa được xử lý.
- Invariant quan trọng như không xác nhận vượt sức chứa chưa có cơ chế bảo vệ.
- Thiếu điều kiện pháp lý hoặc đồng ý cần thiết.
- Chưa có biện pháp giảm thiểu cho thay đổi không thể đảo ngược có hậu quả lớn.
- Phần mới có thể tác động toàn hệ thống dùng chung dù chỉ một người kích hoạt.
- Không có khả năng phát hiện hoặc giảm thiểu lỗi theo yêu cầu rủi ro.

**Canary không phải biện pháp để chấp nhận những lỗi đã biết là không thể chấp nhận.**

## 10. Đo lường trong rollout: guardrails, quality và outcome

### 10.1. Mỗi phép đo phải trả lời câu hỏi ra quyết định

Các phép đo thường chia thành ba nhóm:

| Nhóm | Ví dụ | Câu hỏi |
| --- | --- | --- |
| **Guardrails an toàn** | Lộ dữ liệu, xác nhận trùng, lỗi nghiêm trọng, vi phạm quyền | Có vấn đề phải dừng ngay không? |
| **Sức khỏe kỹ thuật** | HTTP error rate, latency p95/p99, timeout, CPU, queue lag, rollback | Có suy giảm chức năng hoặc năng lực vận hành không? |
| **Outcome người dùng** | Hiểu đúng trạng thái, tỷ lệ hoàn tất, số lần hỏi lại, thời gian thao tác | Thay đổi có giúp người dùng không? |

Cần **định nghĩa metric và nguồn dữ liệu trước rollout**. Một dashboard đẹp nhưng không biết mẫu số hoặc thời điểm exposure có thể dẫn tới quyết định sai.

### 10.2. Phân biệt counts và rates

Giả sử ở một khoảng quan sát giả định:

| Cohort | Request tới API | Lỗi ngoài các từ chối nghiệp vụ dự kiến | Error rate |
| --- | ---: | ---: | ---: |
| OFF | 9.000 | 45 | 0,5% |
| ON | 1.000 | 15 | 1,5% |

Theo định nghĩa ở bảng, tỷ lệ lỗi ON là **15 / 1.000 = 1,5%**, OFF là **45 / 9.000 = 0,5%**.

So sánh cho thấy **tín hiệu cần điều tra**: tỷ lệ ON cao hơn trong khoảng quan sát này. Không thể kết luận cờ **là nguyên nhân duy nhất**, vì cohort có thể khác về thiết bị, hành vi, lưu lượng hoặc thời điểm. Cần xem loại lỗi, dữ liệu nền, confidence và tác động thực.

Không nên chỉ nói “ON có 15 lỗi, OFF có 45 nên ON tốt hơn” mà bỏ mẫu số.

### 10.3. Đo outcome cần xác định exposure thật

Trong thử nghiệm trạng thái:
- Eligible: học viên có đăng ký được phép xem.
- Assigned ON: học viên được gán nhánh giao diện mới.
- Exposed ON: học viên thực sự mở trang và nhìn thấy trạng thái mới.
- Outcome: học viên hiểu đúng trạng thái hoặc không phải hỏi lại sau tương tác.

Nếu lấy tất cả assigned users làm mẫu số cho tỷ lệ hiểu đúng, những người **chưa từng mở màn hình** có thể làm phép đo bị sai lệch. Nhưng nếu chỉ phân tích người tự chọn mở màn hình, kết quả cũng có thể bị **selection bias**. Cần thiết kế phân tích theo câu hỏi: phân tích theo assignment (*intention-to-treat*) hay theo exposure, và ghi rõ giới hạn mỗi cách.

### 10.4. Ngưỡng stop/go cần có trước khi bật

Một kế hoạch có thể quy định:

- **Dừng ngay:** có bằng chứng lộ dữ liệu, xác nhận vượt sức chứa hoặc sai trạng thái nghiêm trọng.
- **Pause và điều tra:** error rate của ON tăng bất thường so với baseline trong khoảng đủ tin cậy; latency vượt ngưỡng hoặc phản hồi tiêu cực quan trọng.
- **Giữ nguyên:** dữ liệu chưa đủ đại diện, có tín hiệu nhiễu hoặc một phụ thuộc chưa được xác minh.
- **Mở rộng:** guardrails ổn, số lượt exposure đủ cho mục đích đánh giá, chất lượng đạt và không xuất hiện rủi ro mới.
- **Quay lui/giảm phạm vi:** quyết định dựa trên mức độ hậu quả và khả năng phục hồi, không chỉ một KPI.

Không có một ngưỡng error rate áp dụng cho mọi ứng dụng. Với dữ liệu xác nhận chỗ, **một vi phạm bất biến** có thể là lý do dừng ngay dù tỷ lệ rất nhỏ. Với thay đổi văn bản, đánh giá có thể dựa thêm vào mức hiểu đúng và phản hồi định tính.

### 10.5. Cẩn thận với thời gian và cỡ mẫu

Nếu 1% cohort tạo 3 lượt truy cập mỗi ngày, quan sát một giờ không đủ để kết luận nhánh mới an toàn ở quy mô lớn. Ngược lại, một sự cố nghiêm trọng cũng không cần chờ hàng nghìn request mới xử lý.

Thời gian quan sát cần xét:
- Lưu lượng và số **exposures thực**.
- Chu kỳ ngày/đêm, ngày trong tuần, mùa vụ.
- Kịch bản hiếm như retry, timeout, cuối đợt đăng ký.
- Năng lực hạ tầng khi mở rộng.
- Những nhóm người dùng chưa được tiếp xúc.
- Độ trễ thu thập metrics và log.
- Mức độ nghiêm trọng của rủi ro.

**Không khẳng định “đạt 95% confidence” nếu chưa có thiết kế thống kê phù hợp**. Phát hành an toàn và A/B test đo tác động có thể yêu cầu loại bằng chứng khác nhau.

## 11. Canary và A/B testing: cùng phân nhóm nhưng mục tiêu khác nhau

### 11.1. Canary chủ yếu hỏi về rủi ro phát hành

Trong canary, nhóm muốn biết: “Bản thay đổi có hoạt động an toàn trong một phạm vi nhỏ trước khi mở rộng không?”. Những chỉ số kỹ thuật, lỗi, độ trễ và dữ liệu rất quan trọng. Có thể dùng cohort đủ điều kiện và so với hệ thống cũ, nhưng không nhất thiết được thiết kế để suy luận nhân quả sản phẩm.

### 11.2. A/B experiment hỏi về tác động người dùng

Trong A/B testing, câu hỏi có thể là: “Thông báo ‘Đang chờ xác nhận’ có làm học viên hiểu đúng trạng thái hơn cách diễn đạt cũ không?”. Khi muốn suy luận tác động:
- Xác định hypothesis, outcome và guardrails trước khi thử.
- Phân nhóm sao cho các nhóm **có thể so sánh**.
- Giữ assignment ổn định trong thời gian cần thiết.
- Ghi đơn vị ngẫu nhiên hóa: người dùng hay tenant.
- Tránh **sample ratio mismatch**, thay đổi mẫu thiếu lý do hoặc tệp exposure không đầy đủ.
- Không chọn dừng sớm/chốt kết quả chỉ vì thấy một biểu đồ có vẻ đẹp.
- Phân biệt ý nghĩa thống kê với tác động thực và ràng buộc an toàn.

Một experiment có thể dùng feature flags để phân phối biến thể; **không phải mọi percentage rollout là một A/B test đúng phương pháp**.

### 11.3. Một so sánh tình huống

| Câu hỏi | Canary | A/B experiment |
| --- | --- | --- |
| Trọng tâm | Bản thay đổi có gây sự cố/rủi ro bất thường không? | Biến thể có làm outcome thay đổi không? |
| Đơn vị quyết định | Mở rộng, giữ, tắt, sửa | Giữ biến thể nào, tác động có đáng kể không? |
| Metric ưu tiên | Guardrails, latency, lỗi, dữ liệu | Outcome định nghĩa trước và guardrails |
| Thiết kế cohort | Có thể chọn nhóm rủi ro thấp | Cần phân nhóm/phân tích giảm thiên lệch |
| Khi dừng | Có thể dừng ngay vì lỗi nghiêm trọng | Cũng dừng ngay vì an toàn; kết luận hiệu quả cần thiết kế phù hợp |
| Kết luận được phép | Không thấy rủi ro đã kiểm ở phạm vi thử | Có thể ước lượng tác động nếu giả định nghiên cứu hợp lệ |

### 11.4. Đừng thử nghiệm trên người dùng bằng cách vi phạm điều kiện an toàn

Có những hành vi không được đặt hai nhánh “an toàn vs không an toàn” để kiểm tra ai thích hơn. Không được cố tình để một cohort thiếu kiểm tra quyền, xác nhận vượt chỗ hoặc nhận thông báo sai nghiêm trọng để “đo tác động”.

**Guardrails không phải mục tiêu phụ được hy sinh cho kết quả A/B.**

## 12. Kill switch, rollback và phục hồi: khác nhau thế nào?

### 12.1. Kill switch làm gì?

**Kill switch** là khả năng **tắt nhanh một hành vi hoặc tích hợp đã được thiết kế để có thể ngừng an toàn**. Ví dụ có thể tắt chức năng gửi thông báo hàng loạt khi phát hiện gateway đang gửi trùng.

Cần biết:
- Cờ tắt ở đâu, ai có quyền thao tác?
- Mất bao lâu quyết định tắt lan tới các instance/client?
- Nhánh OFF có còn an toàn với dữ liệu tạo bởi nhánh ON không?
- Những request đang chạy dở hoặc job đã được xếp hàng có tiếp tục không?
- Tắt cờ có xử lý tất cả tác dụng phụ hay chỉ ngăn tác dụng mới?
- Có thể xác minh tắt thực sự hiệu lực qua metric và hành vi không?

### 12.2. Tắt cờ khác rollback code

| Hành động | Tác dụng chính | Không tự bảo đảm |
| --- | --- | --- |
| **Disable flag** | Ngừng exposure hoặc chọn lại nhánh cũ theo thiết kế | Hoàn tác ghi dữ liệu đã xảy ra; rút lại email đã gửi |
| **Reduce rollout** | Hạ tỷ lệ/cohort nhận nhánh mới | Loại bỏ ảnh hưởng chung ở database/queue |
| **Rollback binary** | Chạy lại phiên bản mã trước | Tương thích với schema/dữ liệu đã thay đổi |
| **Revert config** | Khôi phục một số cấu hình vận hành | Tự sửa lỗi nghiệp vụ hoặc dữ liệu |
| **Compensating action** | Thực hiện thao tác nghiệp vụ bù theo chính sách | Tự động khôi phục mọi hậu quả |
| **Data recovery** | Phục hồi hoặc sửa dữ liệu đã sai | Có thể phải giải quyết mất đồng bộ và sự kiện đã phát |
| **Forward fix** | Sửa và đưa phiên bản an toàn mới vào hệ thống | Có thể không phù hợp nếu hậu quả đang tiếp diễn |

Trong nhiều sự cố, nhóm cần **kết hợp nhiều hành động**. Quyết định phải dựa trên tác động thật và cách phục hồi phù hợp, không mặc định cứ tắt cờ là xong.

### 12.3. Cache và độ trễ lan truyền

Một hệ thống feature flag có thể cache quyết định tại:
- Server instance.
- Edge/CDN.
- SDK chạy trên client.
- Mobile app hoạt động ngoại tuyến.
- Worker xử lý job bất đồng bộ.

Nếu đổi OFF ở bảng điều khiển mà một worker vẫn giữ giá trị ON trong nhiều phút, **kill switch chưa có hiệu lực tức thì**.

Kế hoạch vận hành phải nêu:
1. Độ trễ lan truyền dự kiến và giới hạn chấp nhận.
2. Cách xác minh tại những thành phần quan trọng.
3. Quy tắc hành vi khi không nhận được cấu hình.
4. Có cần chặn traffic hoặc dừng worker độc lập trong sự cố nghiêm trọng không.
5. Làm sao xử lý job đã xếp hàng và thao tác đang thực hiện.

Không quảng bá “tắt tức thì” nếu công cụ/cơ chế hiện tại không bảo đảm điều đó.

### 12.4. Quy trình thao tác khi phát hiện lỗi

~~~text
1. Phát hiện tín hiệu và xác định mức tác động.
2. Bảo vệ người dùng và dữ liệu, kích hoạt incident policy khi cần.
3. Xác định cờ, cohort, phiên bản app và phụ thuộc liên quan.
4. Quyết định pause / giảm phạm vi / disable / rollback / phương án khác.
5. Thực hiện với quyền và cơ chế ghi nhận thay đổi phù hợp.
6. Kiểm tra flag đã lan truyền, traffic và tác dụng mới đã dừng chưa.
7. Xác minh dữ liệu, request đang chạy, queue, external side effects.
8. Ghi hậu quả còn lại, phục hồi và thông báo bên liên quan.
9. Làm rõ nguyên nhân, sửa, kiểm thử lại và tổ chức rollout mới.
10. Cập nhật runbook, guardrails và chính sách theo bài học.
~~~

**Khẩn cấp và an toàn được ưu tiên hơn lịch rollout.** Không chờ cuộc họp Sprint Review hoặc mốc canary tiếp theo để xử lý việc đang gây hại.

## 13. Database migration và tác dụng phụ: giới hạn thực tế của cờ tính năng

### 13.1. Đừng thiết kế hai nhánh trên hai schema không tương thích

Nếu nhánh ON cần một cột mới nhưng nhánh OFF chỉ hoạt động với schema cũ, việc deploy schema hoặc code không đúng thứ tự có thể phá cả fallback.

Một phương án phổ biến là **expand–migrate–contract**:

1. **Expand:** thêm schema/khả năng đọc ghi tương thích với phiên bản đang chạy.
2. **Migrate:** chuyển dữ liệu hoặc hành vi từng bước, có test và đo đạc.
3. **Contract:** bỏ schema/đường cũ sau khi toàn bộ client/service phụ thuộc đã chuyển và được xác minh.

Một cờ migration có thể điều khiển giai đoạn nào đọc đường mới. Nhưng **không phải migration nào cũng có thể rollback bằng cách tắt cờ**, nhất là khi dữ liệu đã đổi kiểu hoặc bị xóa.

### 13.2. Cách nhìn về tương thích trước/sau

| Trạng thái | Yêu cầu kiểm tra |
| --- | --- |
| **Code cũ + schema mới** | Phải còn đọc/ghi được trong giai đoạn chuyển khi dự kiến rollback |
| **Code mới + schema mới, flag OFF** | Nhánh cũ vẫn hoạt động đúng |
| **Code mới + schema mới, flag ON** | Nhánh mới hoạt động và không phá dữ liệu |
| **Code mới + flag OFF sau khi ON đã chạy** | Dữ liệu do nhánh mới tạo có được nhánh cũ xử lý an toàn? |
| **Worker hoặc client còn phiên bản cũ** | Contract và thông điệp có còn tương thích? |
| **Đã contract/xóa schema cũ** | Không hứa rollback binary cũ khi nó không còn tương thích |

Nếu không kiểm tra các trạng thái chuyển tiếp, nhóm có thể tưởng mình có đường quay lui nhưng thực tế chỉ có một nút OFF không còn hoạt động.

### 13.3. Cờ điều khiển gửi thông báo

Giả sử bật **new-sms-notification** cho 5% đăng ký. Khi code ON gửi SMS, tắt cờ:
- Có thể ngừng tạo **yêu cầu gửi mới** nếu code và queue tuân theo cờ.
- **Không thu hồi SMS đã gửi.**
- Không mặc định hủy những job đã xếp hàng từ trước.
- Không sửa được nội dung sai đã được người dùng đọc.
- Không tự giải quyết trường hợp gateway trả timeout nhưng đã gửi thành công.

Cần có **idempotency key, trạng thái gửi, chính sách retry, định nghĩa thời điểm quyết định có hiệu lực và cách xử lý yêu cầu đang tồn**. Rollout giới hạn số người trải nghiệm, nhưng các tác dụng bên ngoài vẫn cần được quản lý riêng.

### 13.4. Shadow traffic và dry-run không được gây tác dụng phụ thật

Nếu gửi bản sao request đăng ký sang service mới để so sánh, nhánh shadow:
- Không được tăng số chỗ của workshop thật.
- Không được gửi email/SMS cho học viên thật.
- Không được tạo hóa đơn hoặc ghi nhận nghiệp vụ trùng.
- Phải dùng dữ liệu và quyền theo chính sách an toàn.
- Cần ghi rõ việc dữ liệu phản hồi khác nhau vì snapshot hoặc thời điểm.

**“Chỉ là shadow” không đồng nghĩa vô hại** nếu người phát triển vô tình để request ghi dữ liệu production.

## 14. Những quyết định và trách nhiệm trong nhóm Agile

### 14.1. Trách nhiệm không phải một nút bật cho một cá nhân không có bối cảnh

| Trách nhiệm | Những điều thường cần quyết định/phối hợp |
| --- | --- |
| **Product Owner / product decision maker** | Giá trị người dùng, cohort phù hợp, tiêu chí outcome và thứ tự backlog |
| **Developers / engineering** | Thiết kế cờ, test, tương thích, hiệu năng, khả năng quay lui, điều kiện chất lượng |
| **SRE/Operations/On-call** | Observability, quyền thao tác, runbook, cảnh báo, đánh giá mức sự cố |
| **Security/Privacy** | Ràng buộc quyền, dữ liệu và đánh giá rủi ro theo chính sách |
| **Support/Customer Success** | Hướng dẫn, phản hồi người dùng và xử lý thắc mắc của cohort thử |
| **Scrum Master (nếu dùng Scrum)** | Giúp nhóm minh bạch và cải tiến việc phối hợp, không tự mặc định sở hữu quyết định sản phẩm/kỹ thuật |
| **Stakeholder liên quan** | Cung cấp bối cảnh, rủi ro và phản hồi theo phạm vi |

Tùy tổ chức, một người có thể kiêm nhiều vai trò; **quyền bật/tắt trong hệ thống phải được xác định rõ**. Khi có sự cố, không để sự không rõ ai quyết định gây chậm giảm thiểu ảnh hưởng.

### 14.2. Product Backlog cần phản ánh chi phí phát hành an toàn

Một PBI “thay màn hình trạng thái” có thể cần:
- Thay UI và acceptance tests.
- Tạo flag, khả năng default/fallback và test ON/OFF.
- Metrics exposure, lỗi và kết quả người dùng.
- Dashboard/runbook theo rủi ro.
- Kế hoạch rollout và hỗ trợ.
- Công việc cleanup flag sau khi ổn định.

**Không nên ước lượng chỉ phần code giao diện rồi coi phần còn lại là việc miễn phí**. Cũng không nên thêm mọi hoạt động cho mọi PBI mà không cân nhắc rủi ro.

### 14.3. Scrum không bắt buộc chờ Sprint Review mới phát hành

Trong Scrum:
- Sprint Planning thống nhất Sprint Goal và lựa chọn công việc khả thi.
- Developers tạo Increment đạt **Definition of Done**.
- Increment **có thể được giao trước Sprint Review** khi đáp ứng điều kiện vận hành.
- Sprint Review kiểm tra kết quả và Product Goal cùng stakeholder để điều chỉnh Product Backlog.
- Sprint Retrospective xem chất lượng quyết định, quy trình và cải tiến.

**Sprint Review không phải cổng phê duyệt bắt buộc trước release**, và một cờ bật 5% không tự chứng minh Sprint Goal hoàn thành. Nhóm cần nhìn Increment, phản hồi và mục tiêu sản phẩm thực tế.

### 14.4. Kanban và đo dòng công việc

Trong Kanban, các việc liên quan đến rollout có thể được theo dõi:
- Tạo feature và test.
- Chuẩn bị guardrails.
- Mở canary và thu bằng chứng.
- Điều tra lỗi, pause hoặc rollout tiếp.
- Cleanup flag và đường cũ.

Cần định nghĩa **điểm bắt đầu/kết thúc** của từng loại work item, đặc biệt tránh nhầm “đã deploy” với “đã đạt kết quả phát hành”. WIP và work item age có thể chỉ ra quá nhiều cờ đang mở cùng lúc hoặc quá nhiều release bị treo chờ duyệt.

### 14.5. XP và kỹ thuật giảm rủi ro

- **TDD:** kiểm tra hành vi từng nhánh và các quy tắc an toàn quan trọng.
- **Continuous integration:** tích hợp đều, chạy unit/integration/contract tests.
- **Refactoring:** xóa cờ cũ và nhánh không còn giá trị dưới bảo vệ test.
- **Pair programming:** cùng suy nghĩ về cờ có tác dụng phụ và hành vi rollback.
- **Small releases:** thay đổi nhỏ để feedback và xác định nguyên nhân dễ hơn.
- **Simple design:** cờ chỉ ở ranh giới có ích, tránh framework phân nhánh phức tạp không cần thiết.
- **Sustainable pace:** không biến mỗi đợt rollout thành một đêm canh hệ thống do không có observability và runbook.

### 14.6. Lean và điểm quyết định phù hợp

Lean gợi ý **giảm cam kết khó đảo ngược khi còn thiếu bằng chứng**, nhưng chủ động học sớm. Release flag có thể giúp nhóm **chưa cam kết exposure toàn bộ** dù mã đã deploy. Tuy nhiên, thiết kế data migration hoặc ký hợp đồng nhà cung cấp thường cần quyết định sớm theo lead time và rủi ro.

Cờ tính năng chỉ hữu ích khi giúp **học với chi phí thấp hơn**, không phải để trì hoãn mọi trách nhiệm.

## 15. Tình huống xuyên suốt: triển khai giao diện trạng thái workshop v2

### 15.1. Product Goal và vấn đề thực

Một Scrum Team phát triển ứng dụng đăng ký workshop. Product Goal là:

> Học viên tự gửi yêu cầu, hiểu khi nào đã có chỗ, và không cần hỏi ban tổ chức chỉ để xác nhận trạng thái.

Hiện trạng:
- Trang dùng nhãn “Đã tiếp nhận yêu cầu” cho trạng thái đang chờ.
- Một số học viên tưởng đã được giữ chỗ.
- Nhân viên phải trả lời tin nhắn hỏi lại.
- Nhóm muốn thay nhãn, cách trình bày và cung cấp giải thích phù hợp.

**User story:**

> Là học viên đã đăng ký, tôi muốn phân biệt rõ “Đang chờ xác nhận” với “Đã xác nhận chỗ”, để biết khi nào cần chờ và khi nào đã có suất.

### 15.2. Phân tách hành vi và rủi ro

Nhóm chọn **không** thay đổi quy tắc xác nhận, transaction hay quyền dữ liệu trong lần rollout giao diện này. Nhánh v2 chỉ lấy trạng thái từ cùng backend đáng tin và trình bày khác đi.

Điều kiện bất biến:
1. Người dùng chỉ được xem đăng ký có quyền truy cập.
2. Trạng thái PENDING không bao giờ được hiển thị như đã xác nhận.
3. Giao diện v2 không tự kích hoạt gửi thông báo hoặc ghi xác nhận.
4. Nhánh v1 vẫn hoạt động khi OFF.
5. Có thể định danh cohort và nhận phản hồi đúng đối tượng.

Việc **giảm phạm vi thay đổi** khiến cờ có tác dụng kiểm soát thực hơn là bọc một thay đổi dữ liệu phức tạp trong một boolean.

### 15.3. Definition of Done và release readiness

Để coi Increment đã Done, nhóm kiểm:
- Các tình huống nghiệp vụ của v1 và v2.
- Test quyền và phản hồi API.
- Tính tương thích của cả hai nhánh với dữ liệu hiện tại.
- Trạng thái loading/error được giải thích đúng.
- Accessibility, văn bản dễ hiểu và phương thức kiểm tra phù hợp đối tượng.
- Không có tình huống được biết có thể xác nhận sai chỗ.
- Code tích hợp và chất lượng đáp ứng DoD.

Để **mở rollout** cần thêm:
- Owner, kế hoạch cohort và thông báo hỗ trợ.
- Metrics có phân loại exposed ON/OFF.
- Quyền thao tác flag, runbook và giới hạn propagation.
- Điều kiện pause/rollback.
- Kế hoạch quan sát đúng chu kỳ người dùng.

**Done về code** và **sẵn sàng phát hành rộng** là hai câu hỏi khác nhau, dù tổ chức có thể lồng một phần readiness vào DoD chung.

### 15.4. Thiết kế rollout

Một kế hoạch **giả định**:

| Bước | Phạm vi | Kiểm tra chính | Điều kiện để tiếp tục |
| --- | --- | --- | --- |
| 0 | OFF trên production sau deploy | V1 hoạt động bình thường, v2 chưa exposure | Không suy giảm bởi deploy |
| 1 | Nội bộ và tài khoản thử | Quyền, khả năng đọc, fallback, log | Không có lỗi quan trọng |
| 2 | 1% học viên đủ điều kiện | Lỗi, latency, trạng thái sai, phản hồi hỗ trợ | Guardrails đạt, exposure đủ |
| 3 | 5% | Nhiều thiết bị, trải nghiệm, phản hồi | Không có tác động đáng ngại |
| 4 | 25% | Tải và outcome người dùng | Có dữ liệu phù hợp |
| 5 | 50% | Tính ổn định ở các nhóm lớn | Sẵn sàng hỗ trợ và vận hành |
| 6 | 100% | Khả năng dùng rộng, theo dõi dài hơn | Không có dấu hiệu cần quay lui |
| 7 | Cleanup | Xóa nhánh v1 và cờ tạm | Regression và monitoring đạt |

Mốc thời gian không được cố định chỉ bằng đồng hồ; cần **số exposure, mức rủi ro và guardrail**. Nếu nhóm có ít người dùng trong ngày, phải kéo dài thời gian quan sát hợp lý.

### 15.5. Dữ liệu canary giả định

Tại đợt 5%, dữ liệu **hoàn toàn giả định** trong một khoảng quan sát:

| Tín hiệu | ON / v2 | OFF / v1 |
| --- | ---: | ---: |
| Người thực sự mở trạng thái | 120 | 1.900 |
| Lượt thử cho phép quan sát hiểu đúng | 30 | 30 |
| Người hiểu đúng trạng thái trong lượt thử | 26/30 | 18/30 |
| Lỗi API không mong đợi trên số request | 3/600 | 18/9.000 |
| Có sự kiện lộ dữ liệu / xác nhận sai được phát hiện | 0 | 0 |

Tỷ lệ trong các lượt dùng thử là **86,7%** (26/30) so với **60%** (18/30). Error rate từ bảng là **0,5%** (3/600) so với **0,2%** (18/9.000).

Cách đọc có trách nhiệm:
- Có **tín hiệu tích cực** về mức hiểu đúng trong hai nhóm thử nhỏ.
- Có **tín hiệu lỗi kỹ thuật ON cao hơn**, cần xem loại lỗi và phân bố.
- Không có sự kiện nghiêm trọng **được phát hiện trong khoảng quan sát** không đồng nghĩa chứng minh chưa từng hoặc không thể có lỗi.
- Nhóm thử có thể khác nhau; không khẳng định v2 là nguyên nhân duy nhất cải thiện.
- Cần hỏi tính đại diện và cách đo outcome trước khi dùng để quyết 100%.

Nhóm có thể **giữ nguyên ở 5% để điều tra lỗi**, thay vì mở rộng chỉ vì tỷ lệ hiểu đúng trông đẹp.

### 15.6. Một lỗi xuất hiện khi tăng lên 25%

Giả sử sau khi mở rộng, người dùng trên một trình duyệt cũ không nhìn thấy chú thích “đang chờ”, khiến họ nghĩ đăng ký đã thành công. Support nhận nhiều phản hồi trong một giờ.

Phản ứng:
1. Xác định lỗi thuộc nhánh ON, nhóm trình duyệt và mức ảnh hưởng.
2. Nếu có nguy cơ khiến người dùng ra quyết định sai nghiêm trọng, **pause rollout**, giảm phạm vi hoặc disable flag phù hợp ngay.
3. Kiểm tra tốc độ lan truyền OFF, browser cache, client session và số người đã tiếp xúc.
4. Thông báo bộ phận hỗ trợ theo mức cần thiết; tránh hứa người dùng đã có chỗ khi chưa xác nhận.
5. Tạo test tái hiện lỗi, sửa accessibility/compatibility và kiểm chứng trên môi trường thích hợp.
6. Chạy lại regression ON/OFF, mở canary thận trọng với guardrail cải thiện.
7. Ghi bài học trong Retrospective hoặc buổi xem xét dịch vụ.

Lưu ý, nếu nhánh v2 chỉ thay **cách trình bày**, tắt flag có khả năng giảm tiếp xúc mới. Nếu nhánh mới **đã ghi sai trạng thái vào database**, phải có bước sửa dữ liệu và kiểm tra tác dụng phụ riêng.

### 15.7. Đánh giá sau khi ổn định

Nếu một số vòng sau cho thấy:
- Không còn lỗi nghiêm trọng ở các nhóm đã thử.
- Người dùng hiểu đúng hơn trong phép đo phù hợp.
- Số lần phải hỏi lại giảm.
- Tỷ lệ lỗi/latency ở mức chấp nhận.
- Hỗ trợ và vận hành sẵn sàng.

thì nhóm có thể đưa ra quyết định **mở rộng exposure**. Sau khi 100% ổn định, họ tạo công việc **xóa release flag, nhánh v1 và test chỉ dành cho nhánh cũ**, đồng thời giữ các test hành vi quan trọng cho v2.

Đó mới là **kết thúc vòng đời release flag**, không phải mãi mãi giữ hai giao diện chỉ vì có thể.

## 16. Tình huống khác: cờ cho hành vi ghi dữ liệu có rủi ro cao

### 16.1. Đề xuất dùng flag cho quy tắc xác nhận chỗ mới

Một người đề xuất đổi cơ chế xác nhận:
- Nhánh cũ cập nhật bằng transaction.
- Nhánh mới gọi service khác để giữ chỗ.
- Flag ON cho 1% yêu cầu.

Nguy cơ: cả hai nhánh có thể cùng ghi vào dữ liệu chung, hoặc request được retry qua hai phiên bản khác nhau, khiến số chỗ bị xác nhận hai lần.

**Chỉ 1% traffic không giải quyết được bất biến dữ liệu.** Cần xác định:
- Điểm quyết định và nguồn dữ liệu có thẩm quyền.
- Cơ chế atomicity/concurrency.
- Idempotency key ổn định khi retry.
- Tính nhất quán giữa client, service và DB.
- Cách tránh hai nhánh ghi khác nhau trên cùng entity.
- Có thể shadow/dry-run không tạo tác dụng phụ hay không.
- Cách xác minh dữ liệu và phục hồi nếu chuyển lại nhánh cũ.

### 16.2. Kế hoạch kiểm chứng trước rollout

~~~text
Rủi ro:
Hai yêu cầu hoặc hai phiên bản cùng xác nhận suất cuối.

Bất biến:
confirmed_count không vượt capacity;
mỗi request key có tối đa một kết quả tạo xác nhận.

Kiểm tra trước khi ON:
- Integration test với database/cơ chế ghi phù hợp.
- Concurrency test nhiều request tranh một suất.
- Retry test qua timeout và request key giống nhau.
- Contract test hai phiên bản khi chạy song song.
- Migration rehearsal cho dữ liệu và trạng thái đã ghi.
- Cơ chế quan sát/khôi phục khi dữ liệu có vấn đề.

STOP:
Bất kỳ vi phạm bất biến hoặc quyền dữ liệu nghiêm trọng nào.

Fallback:
Chỉ dùng đường cũ nếu dữ liệu/contract còn tương thích;
nếu không phải có kế hoạch khôi phục khác.
~~~

Trong trường hợp rủi ro chưa được giải quyết, phương án phù hợp có thể là **không bật cho bất kỳ người dùng thật nào**. Cờ không làm một thay đổi nguy hiểm trở thành an toàn chỉ nhờ tỷ lệ thấp.

## 17. Những sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao gây hại | Cách điều chỉnh |
| --- | --- | --- |
| Gọi deploy là release | Không biết ai đã thực sự thấy hành vi mới | Ghi rõ build, deploy, exposure và rollout |
| Bật 100% ngay sau khi CI xanh | Không nhìn thấy vấn đề của người dùng hoặc vận hành trước khi ảnh hưởng rộng | Chọn rollout dựa trên rủi ro, có guardrails |
| Dùng 1% làm “bằng chứng chắc chắn an toàn” | Mẫu nhỏ và lỗi ở hạ tầng chia sẻ vẫn có thể ảnh hưởng rộng | Xác định phạm vi tác động thực, bổ sung test và đo |
| Đánh giá cờ bằng random mới ở mỗi request | Người dùng liên tục đổi biến thể, dữ liệu khó đọc | Dùng sticky assignment theo đơn vị phù hợp |
| Nhầm assigned với exposed | Mẫu số và suy luận outcome sai | Ghi đủ eligibility, assignment, exposure, engagement khi cần |
| Dùng client-side flag làm phân quyền | Người dùng có thể bypass giao diện để gọi API | Kiểm tra quyền độc lập phía server |
| Log email, số điện thoại vào flag events | Rủi ro dữ liệu và quyền riêng tư | Thu tối thiểu, dùng định danh phù hợp, kiểm soát truy cập |
| Tắt cờ được coi là undo mọi thứ | Dữ liệu đã ghi và thông báo đã gửi vẫn tồn tại | Chuẩn bị recovery, idempotency, compensation |
| Quên cache/worker đã giữ giá trị ON | Kill switch lan truyền chậm, tiếp tục gây hậu quả | Kiểm tra propagation, job đang chạy và runbook |
| Không test nhánh OFF | Fallback lỗi ngay lúc cần quay lui | Regression cho cả hai nhánh và schema liên quan |
| Không có metrics theo cohort | Không biết lỗi từ ON hay OFF | Gắn version, exposure và nguồn đo phù hợp |
| Chỉ nhìn số lỗi tuyệt đối | Cohort nhiều traffic trông xấu hơn dù rate thấp | Dùng mẫu số, phân loại lỗi và bối cảnh |
| Coi canary là A/B test chứng minh giá trị | Thiếu thiết kế phân nhóm/đo outcome | Chọn phương pháp theo câu hỏi |
| Mở rộng theo lịch cứng dù không có dữ liệu | Có thể đưa lỗi chưa được quan sát tới nhiều người | Đặt điều kiện go/pause/stop có căn cứ |
| Dùng feature flag cho mọi thay đổi nhỏ | Nợ cờ, chi phí test tổ hợp và khó bảo trì | Chỉ thêm khi giá trị kiểm soát vượt chi phí |
| Giữ release flags vĩnh viễn | Nhiều nhánh mã cũ, cấu hình khó kiểm | Đặt owner và hạn cleanup từ đầu |
| Thay đổi DB không tương thích | Nhánh cũ không còn hoạt động khi OFF | Expand–migrate–contract, test hai phiên bản |
| Dark launch/shadow tạo side effects | Có thể ghi dữ liệu hoặc gửi thông báo hai lần | Cô lập xử lý thử, kiểm tra quyền và dry-run |
| Không có người quyết stop/rollback | Giảm thiểu sự cố bị chậm | Rõ quyền, owner, runbook, cơ chế escalation |
| Tối ưu error rate mà bỏ Product Goal | Hệ thống kỹ thuật khỏe nhưng người dùng không nhận ích lợi | Đo outcome cùng quality và flow |
| Đánh giá thành công bằng số cờ đã bật | Khuyến khích mở nhiều tính năng không có giá trị | Tập trung vấn đề người dùng và hiệu quả phát hành |
| Bỏ Retrospective sau sự cố | Cùng lỗi lặp lại ở lần rollout sau | Ghi bài học, cải tiến kiểm tra và cơ chế dừng |

## 18. Bài thực hành: thiết kế phát hành có kiểm soát

### 18.1. Bối cảnh

Một Scrum Team đã phát triển **trang trạng thái đăng ký v2** cho 20.000 học viên có thể sử dụng. Trang cũ đang chạy, v2 làm rõ “chờ xác nhận” và “đã xác nhận”. Có một API chung cung cấp trạng thái. Nhóm muốn phát hành nhanh nhưng vẫn kiểm soát rủi ro.

Các dữ kiện cho bài tập **đều giả định**:
- 20.000 học viên đủ điều kiện.
- Flag v2 có mặc định OFF.
- Backend nghiệp vụ đã có test về quyền và tính đúng sức chứa.
- Đã có dashboard latency và lỗi nhưng chưa có metric exposure theo flag.
- Các trình duyệt di động cũ có thể diễn giải layout khác.
- Nhóm hỗ trợ có người trực trong hai ngày đầu thử nghiệm.

### 18.2. Nhiệm vụ A – Phân biệt mốc (10 phút)

Xếp các hành động theo **build, deploy, release/expose, observe, disable/rollback**:

1. Pipeline tạo artifact có cả nhánh giao diện cũ và mới.
2. Artifact được đưa lên production, flag vẫn OFF.
3. Nhân viên nội bộ bật cờ cho tài khoản thử.
4. 5% học viên đủ điều kiện được phân vào nhánh mới.
5. Dashboard ghi nhận lỗi và người dùng trả lời khảo sát.
6. Sau tín hiệu lỗi, nhóm OFF và kiểm tra đã lan truyền.
7. Nhóm chạy lại phiên bản trước vì lỗi ở shared dependency.

**Gợi ý:** bước 2 là deploy nhưng chưa cho học viên exposure; bước 4 là rollout/exposure; bước 6 là disable flag; bước 7 là rollback binary. Bước 3 là exposure nội bộ nhưng không phải mở rộng cho học viên phổ thông.

### 18.3. Nhiệm vụ B – Tính phạm vi cohort (10 phút)

Theo giả định tất cả 20.000 học viên đều đủ điều kiện và phân phối bucket đúng tỷ lệ **trên tập này**:

| Tỷ lệ rollout | Số học viên được phân nhánh ON theo phép tính kỳ vọng |
| --- | ---: |
| 1% | 200 |
| 5% | 1.000 |
| 25% | 5.000 |
| 50% | 10.000 |
| 100% | 20.000 |

Hãy giải thích:
1. Tại sao **1.000 assigned** không có nghĩa 1.000 người đã mở giao diện?
2. Tại sao 5% một tenant lớn có thể không tương đương 5% request?
3. Tại sao cần giữ người đã ON không bị OFF tùy tiện khi tăng tỷ lệ?
4. Trường hợp nào cần nhóm theo tenant thay vì người dùng?

**Gợi ý:** cohort là đối tượng được chọn; exposure cần sự kiện thực, và request volume phụ thuộc hành vi người dùng.

### 18.4. Nhiệm vụ C – Thiết kế flag spec (15 phút)

Tạo đặc tả:
- Key, owner, mục tiêu người dùng.
- Default OFF và điều kiện eligibility.
- Cohort, sticky assignment, đơn vị phân nhóm.
- Các bước 0% → nội bộ → 1% → 5% → 25% → 100%.
- Một guardrail nghiêm trọng và hai metric kỹ thuật.
- Một outcome về hiểu đúng trạng thái.
- Quyền tắt, thời gian lan truyền và cách kiểm tra.
- Hạn xem lại/xóa flag.
- Những nhánh code/test cần được giữ khi ON và OFF.

Phải nêu điều kiện **pause** khi tín hiệu không rõ, không chỉ hai lựa chọn go/rollback.

### 18.5. Nhiệm vụ D – Đọc dữ liệu rollout (15 phút)

Trong giai đoạn 5%, có dữ liệu giả định:

| Nhánh | Request | Lỗi không mong đợi | Người được quan sát hiểu đúng |
| --- | ---: | ---: | ---: |
| ON | 800 | 16 | 24/30 |
| OFF | 8.000 | 40 | 18/30 |

Tính:
1. Error rate ON = **16/800 = 2%**.
2. Error rate OFF = **40/8.000 = 0,5%**.
3. Tỷ lệ hiểu đúng ON = **24/30 = 80%**.
4. Tỷ lệ hiểu đúng OFF = **18/30 = 60%**.
5. Có nên mở thẳng 100% không?
6. Cần điều tra những loại lỗi, thiết bị và khác biệt giữa cohort nào?
7. Vì sao 24/30 không đủ để kết luận chắc chắn về mọi học viên?

**Gợi ý:** outcome có tín hiệu tích cực nhưng guardrail kỹ thuật xấu hơn; nhóm cần xác minh rủi ro, chất lượng dữ liệu và điều kiện stop/go trước khi mở thêm.

### 18.6. Nhiệm vụ E – Xử lý lỗi ở 25% (15 phút)

Giả sử sau khi mở lên 25%, một nhóm người dùng nhìn thấy **“Đã xác nhận”** trong khi backend thực sự lưu **PENDING** do một lỗi ánh xạ ở client.

Hãy đề xuất:
1. Hành động bảo vệ người dùng ngay.
2. Cách kiểm tra mức độ lan truyền của flag OFF trên mobile/web.
3. Cách xác minh dữ liệu nguồn chưa bị thay đổi.
4. Cách thông báo tới support và người dùng bị ảnh hưởng khi cần.
5. Test nào cần bổ sung để tái hiện.
6. Điều kiện nào cho phép thử bật lại với cohort nhỏ.
7. Hành động Retrospective nào giúp lỗi không tái diễn.

**Gợi ý:** dù backend không ghi sai, thông tin sai **vẫn có thể gây hậu quả thật**. Cần phản hồi về trải nghiệm và xác nhận tình trạng đăng ký đúng trước khi kết luận sự cố đã xử lý.

### 18.7. Nhiệm vụ F – Phân tích giới hạn kill switch (15 phút)

Một tính năng mới gửi SMS xác nhận sau giao dịch. Nhóm bật cho 1%, phát hiện một số người nhận SMS hai lần. Sau khi OFF, queue vẫn có job đã tạo trước đó.

Giải thích:
- Vì sao OFF không thu hồi SMS đã gửi?
- Phải xử lý job đang queue và request đang xử lý thế nào?
- Cần idempotency ở những ranh giới nào?
- Khi gateway trả timeout, có được mặc định retry vô hạn không?
- Cần quan sát trạng thái gửi và điều kiện dừng gì?
- Điều gì khác giữa disable flag, rollback binary và hành động bù nghiệp vụ?

**Gợi ý:** cờ ngăn các hành vi mới theo thiết kế, không xóa tác dụng đã xảy ra. Chọn phương án phục hồi theo contract gateway và dữ liệu thực.

### 18.8. Nhiệm vụ G – Kiểm thử hai nhánh (15 phút)

Với lớp RegistrationStatusPresenter ở phần 8, hãy:
1. Viết test v2 ON với PENDING.
2. Viết test v1 OFF với PENDING.
3. Kiểm test với CONFIRMED và REJECTED ở cả hai nhánh.
4. Kiểm quyền người dùng ở **service/API**, không chỉ presenter.
5. Kiểm một trường hợp cấu hình thiếu hoặc evaluator lỗi theo chính sách phù hợp.
6. Ghi điều unit tests **không chứng minh** (sự hiểu đúng của học viên, tương thích trình duyệt, data transaction).
7. Đề xuất một integration test và một user test bổ sung.

### 18.9. Nhiệm vụ H – Thiết kế cleanup (10 phút)

Sau ba tuần ổn định ở 100%, nhóm muốn xóa v1 và release flag. Hãy liệt kê:
- Các điều kiện chứng minh v2 đã sẵn sàng là đường duy nhất.
- Những client/worker còn cũ có thể phụ thuộc nhánh v1 không?
- Những test nào cần giữ cho hành vi v2?
- Những test/cấu hình nào liên quan riêng nhánh cũ có thể xóa?
- Có cần migration dữ liệu/contract không?
- Cách deploy, quan sát và rollback **thay đổi xóa cờ**.
- Khi nào cập nhật tài liệu và xóa dashboard/metric không còn cần thiết.

### 18.10. Tiêu chí tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Tách deploy/release** | Gọi mọi bước là release | Phân biệt deploy, exposure, rollback | Liên kết đúng DoD, readiness, Product Goal |
| **Thiết kế cờ** | Chỉ có boolean | Có owner, default, cohort, fallback | Có sticky assignment, expiry, phụ thuộc, quan sát |
| **Rollout kiểm soát** | Bật 100% hoặc chọn tỷ lệ tùy ý | Có các vòng và điều kiện kiểm tra | Xét blast radius, sample, ring, đa tenant và rollback |
| **Guardrails** | Chỉ nhìn số người dùng | Có metric kỹ thuật, outcome và điều kiện dừng | Đọc đúng mẫu số, bias, quyền và hậu quả phi tuyến |
| **Phục hồi** | Tin OFF sẽ undo mọi thứ | Phân biệt OFF/rollback/data effects | Có kế hoạch job, data, idempotency, cache và phục hồi |
| **Chất lượng** | Bỏ test vì có cờ | Test ON/OFF và DoD | Tương thích migration, kiểm tra bảo mật, CI và cleanup |
| **Agile** | Chỉ đo “đã bật bao nhiêu %” | Dùng phản hồi để điều chỉnh backlog | Tối ưu giá trị, dòng công việc và sự bền vững |

## 19. Mẫu dùng ngay trong nhóm

### 19.1. Feature flag specification

~~~text
Flag key:
Mục đích / user story / Product Goal:
Loại flag: release / experiment / ops / entitlement / migration:
Ngày tạo / owner sản phẩm / owner kỹ thuật:
Môi trường được phép:
Trạng thái mặc định:
Nhánh ON và OFF khác nhau ở đâu:
Eligibility và đơn vị cohort:
Sticky assignment, salt, rule version:
Emergency override và ưu tiên quy tắc:
Phụ thuộc vào flags/API/schema khác:
Tác dụng phụ có thể phát sinh:
Quy tắc đánh giá khi config mất kết nối:
Các test ON/OFF, integration/security/contract:
Metrics: eligible, assigned, exposed, outcome:
Guardrails và ngưỡng stop/pause:
Quyền thao tác, giới hạn propagation:
Rollback code/data hoặc compensation:
Ngày bắt buộc review/xóa:
Liên kết PR, runbook, dashboard và kế hoạch rollout:
~~~

### 19.2. Progressive rollout plan

~~~text
Release / phiên bản ứng dụng:
Product Goal và giả thuyết:
Nhóm người dùng đủ điều kiện:
Rủi ro nghiệp vụ và kỹ thuật chính:
Definition of Done và readiness:
Các tầng: internal / 1% / 5% / 25% / 50% / 100%:
Thời gian quan sát tối thiểu theo dữ liệu:
Các sự kiện exposure cần ghi:
Guardrail nghiêm trọng:
Error/latency/quality metrics:
Outcome người dùng:
Điều kiện GO:
Điều kiện PAUSE:
Điều kiện STOP / DISABLE:
Người phê duyệt mở rộng:
Người chịu trách nhiệm trực:
Cách xác minh quyết định có hiệu lực:
Hướng dẫn hỗ trợ, thông báo người dùng nếu cần:
Ngày kiểm tra và tài liệu kết quả:
~~~

Các phần trăm ở trên **chỉ là gợi ý cấu trúc**, nhóm có thể thay bằng cohort/ring và tỷ lệ khác tùy rủi ro.

### 19.3. Runbook disable và rollback

~~~text
Tình huống kích hoạt:
Mức độ và người dùng bị ảnh hưởng:
Flag key, rule version, current rollout:
Ứng dụng, service, client và worker liên quan:
Ai có quyền thao tác:
Lệnh/thao tác disable hoặc giảm rollout:
Thời gian lan truyền dự kiến:
Cách kiểm tra trên từng thành phần:
Job/in-flight requests cần xử lý:
Dữ liệu/tác dụng phụ đã xảy ra:
Cần rollback binary không:
Schema và dữ liệu có tương thích không:
Có cần compensation hoặc data recovery:
Dashboard/alert sau khi thực hiện:
Cách báo người liên quan:
Tiêu chí ổn định để đóng incident:
Bài học, test bổ sung và owner hành động:
~~~

### 19.4. Sổ theo dõi vòng đời flag

~~~text
Flag:
Owner:
Ngày tạo:
Mục đích còn tồn tại? Có/Không:
Tỷ lệ/cohort đang ON:
Đã đạt 100%/kết thúc experiment chưa:
Rủi ro nếu xóa:
Code client/server còn sử dụng:
Tài liệu/metrics/test cần giữ:
Kế hoạch loại bỏ nhánh cũ:
Issue và deadline cleanup:
Ngày thực hiện:
Kết quả kiểm tra sau cleanup:
~~~

### 19.5. Mẫu quyết định GO / PAUSE / STOP

~~~text
Mốc rollout:
Phiên bản và khoảng dữ liệu:
Eligible / Assigned / Exposed:
Nhóm ON/OFF có thể so sánh đến đâu:
Error rate và latency:
Sự cố/guardrail:
Outcome và phản hồi định tính:
Đủ dữ liệu chưa, giới hạn mẫu là gì:
Tác động phụ thuộc/backend/shared data:
Quyết định: GO / PAUSE / STOP:
Lý do và bất định còn lại:
Hành động, owner, thời điểm xem lại:
Nếu rollback: kiểm chứng và phục hồi bổ sung:
~~~

Các mẫu là **công cụ học và điều hành**, không phải hồ sơ bắt buộc của Scrum hoặc một tiêu chuẩn áp dụng cho tất cả tổ chức. Điều quan trọng là nhóm **có thể hành động dựa trên thông tin đó khi cần**.

## 20. Checklist phát hành có kiểm soát

**Trước khi deploy và enable:**

- [ ] Vấn đề người dùng và mục tiêu phát hành được diễn đạt rõ.
- [ ] Phân biệt deploy mã với kích hoạt tính năng cho người dùng.
- [ ] Đã đánh giá blast radius cả ở người dùng, dữ liệu, hạ tầng và side effects.
- [ ] Ràng buộc bảo mật, quyền truy cập và bất biến dữ liệu được bảo vệ độc lập với flag.
- [ ] Nhánh ON/OFF đã được kiểm thử theo rủi ro; fallback không bị bỏ mặc.
- [ ] Database/API/worker có tính tương thích cần thiết khi các phiên bản cùng tồn tại.
- [ ] Chưa có lỗi nghiêm trọng đã biết không thể chấp nhận khi dù chỉ 1% người dùng tiếp xúc.
- [ ] Cờ có key, owner, mặc định an toàn, điều kiện phân nhóm và hạn xem lại.
- [ ] Phương pháp sticky assignment phù hợp đơn vị người dùng/tenant và dữ liệu.
- [ ] Người vận hành hiểu mất kết nối cấu hình sẽ dẫn tới hành vi nào.

**Trong rollout:**

- [ ] Mỗi giai đoạn có mục đích, phạm vi và tiêu chí mở rộng rõ.
- [ ] Số eligible, assigned và exposed được phân biệt khi đo.
- [ ] Guardrails về dữ liệu/quyền và chỉ số lỗi/latency có khả năng quan sát.
- [ ] Outcome người dùng được đo với giả thuyết và giới hạn dữ liệu minh bạch.
- [ ] Ngưỡng GO, PAUSE, STOP được xác định trước và có quyền quyết định rõ.
- [ ] Thời gian quan sát đủ cho lưu lượng, chu kỳ nghiệp vụ và rủi ro thực tế.
- [ ] Không coi canary là A/B experiment có giá trị suy luận nhân quả nếu chưa thiết kế đúng.
- [ ] Khi có dấu hiệu gây hại, nhóm xử lý theo mức độ khẩn thay vì chờ mốc rollout.
- [ ] Support, on-call và stakeholder liên quan biết cohort nào đang trải nghiệm gì.
- [ ] Quyết định mở rộng/giữ/tắt được ghi cùng dữ liệu và bất định.

**Phục hồi và vòng đời:**

- [ ] Có runbook giảm phạm vi/tắt cờ và biết độ trễ lan truyền.
- [ ] Việc tắt cờ được xác minh ở client, service và worker phù hợp.
- [ ] Các job đang chạy, email/SMS đã gửi và dữ liệu đã ghi được xem xét riêng.
- [ ] Không đánh đồng disable flag với rollback binary hay phục hồi database.
- [ ] Migration có kế hoạch expand–migrate–contract hoặc quy trình tương thích phù hợp.
- [ ] Cờ tạm có owner và deadline cleanup; các nhánh cũ được xóa khi đủ điều kiện.
- [ ] Test hành vi quan trọng vẫn được giữ khi xóa feature flag.
- [ ] Nhóm xem lại nguyên nhân sự cố và cải tiến điều kiện phát hành.
- [ ] Việc phát hành được đánh giá bằng **chất lượng, khả năng giao và giá trị người dùng**, không chỉ % rollout.

**Kết luận:** **Phát hành có kiểm soát** giúp nhóm đưa thay đổi tới người dùng theo từng phạm vi có thể quan sát, học từ dữ liệu thật và giảm mức ảnh hưởng khi một giả định sai. **Feature flags** giúp tách deploy khỏi exposure, nhưng giá trị chỉ xuất hiện khi kết hợp **cohort nhất quán, guardrails, testing, monitoring, rollback và vòng đời cleanup**. Những tác dụng không thể đảo ngược — dữ liệu sai, quyền bị vi phạm, thông báo đã gửi — cần biện pháp bảo vệ riêng. Khi gắn hoạt động này với Product Goal, backlog, Definition of Done, Scrum, Kanban và XP, nhóm có thể **giao phần mềm sớm, nhận phản hồi liên tục và mở rộng mức sử dụng có trách nhiệm mà không đánh đổi chất lượng**.
