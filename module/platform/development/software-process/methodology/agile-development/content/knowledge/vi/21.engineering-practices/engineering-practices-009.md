# Phân biệt chuyển giao liên tục với triển khai liên tục

Nhóm phát triển một nền tảng học trực tuyến đã tự động chạy kiểm thử mỗi lần thay đổi mã. Sau ba tuần, mã của tính năng “Học tiếp” vẫn nằm ở môi trường thử nghiệm vì chưa ai dám đưa lên production. Một nhóm khác tự động đưa mọi thay đổi vượt qua pipeline lên production, nhưng không có cơ chế quan sát lỗi mất tiến độ hoặc tắt tính năng khi gặp sự cố. Cả hai nhóm đều nói: “Chúng tôi làm CD”. Thực ra họ đang nói về **những mức tự động hóa và năng lực giao phần mềm khác nhau**.

**Continuous Delivery (chuyển giao liên tục)** là năng lực giữ phần mềm ở **trạng thái có thể triển khai/phát hành một cách tin cậy theo yêu cầu**, nhờ tích hợp thường xuyên, tự động hóa kiểm chứng và một quy trình giao hàng có thể lặp lại. **Continuous Deployment (triển khai liên tục)** đi xa hơn: **mỗi thay đổi đạt các điều kiện của pipeline được tự động triển khai tới production**, không cần một bước phê duyệt triển khai thủ công thường lệ cho từng thay đổi. Cả hai đều dựa vào những nền tảng kỹ thuật như Continuous Integration (CI), kiểm thử, quản lý cấu hình và khả năng quan sát.

Hai thuật ngữ dễ bị viết tắt giống nhau là **CD**. Trong bài này, để tránh nhầm lẫn, chúng ta viết đầy đủ **Continuous Delivery** hoặc **Continuous Deployment** khi cần phân biệt. Ngoài ra, **deployment** không hoàn toàn đồng nghĩa với **release**: mã đã ở production có thể vẫn được giấu sau feature flag và chưa mở cho người dùng.

Bài thuộc chương **Thực hành kỹ thuật** của module **AGILE_DEVELOPMENT**. Hiểu đúng các khái niệm giúp nhóm thực hành Agile theo hướng **giao sản phẩm tăng dần, lấy phản hồi sớm, điều chỉnh backlog và cải tiến liên tục**. Năng lực này bổ trợ cho user story, Scrum, Kanban và Extreme Programming (XP), nhưng không thể thay thế việc xác định giá trị người dùng hay bảo vệ chất lượng.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **Continuous Integration (CI), Continuous Delivery, Continuous Deployment** bằng điều kiện đầu ra và quyền quyết định đưa thay đổi tới production.
2. Phân biệt **build, artifact, deploy, release, feature exposure, Increment và outcome**, tránh gọi mọi lần chạy pipeline là một bản phát hành có giá trị.
3. Thiết kế một pipeline cơ bản có **build, kiểm thử, kiểm tra bảo mật, tạo artifact, triển khai thử, xác nhận, triển khai production và giám sát**.
4. Giải thích vì sao Continuous Delivery **không đồng nghĩa mọi lần triển khai đều phải làm thủ công**, và Continuous Deployment **không đồng nghĩa bỏ mọi bước kiểm soát**.
5. Đánh giá các cơ chế **quality gate, policy gate, feature flag, canary, blue–green, rollback/roll-forward** theo rủi ro.
6. Xử lý ví dụ thay đổi dữ liệu, phân quyền và tương thích khi chuyển từ triển khai hiếm sang triển khai thường xuyên.
7. Kết hợp pipeline với Definition of Done, Sprint Goal, quản lý WIP và các thực hành XP.
8. Đề xuất lộ trình phát triển từ CI tới Continuous Delivery rồi cân nhắc Continuous Deployment, dùng số đo và bằng chứng thay vì chọn nhãn theo phong trào.

## 2. Ba khái niệm nền tảng: CI, Continuous Delivery và Continuous Deployment

| Khái niệm | Câu hỏi trọng tâm | Năng lực cốt lõi | Điều **không** thể suy ra |
| --- | --- | --- | --- |
| **Continuous Integration — CI** | Các thay đổi nhỏ đã được tích hợp và kiểm tra cùng nhau sớm chưa? | Developers tích hợp thường xuyên; build, kiểm thử tự động và tín hiệu lỗi có thể chạy nhanh | Build xanh chưa chứng minh sản phẩm sẵn sàng phát hành, không tự triển khai production |
| **Continuous Delivery — chuyển giao liên tục** | Nếu quyết định giao phiên bản hiện tại, chúng ta có thể triển khai một cách tin cậy không? | Pipeline tạo và kiểm tra một phiên bản sẵn sàng triển khai, quy trình đưa tới production được chuẩn hóa, có thể thực hiện **theo yêu cầu** | Không bắt buộc mỗi commit phải tự động đến production; cũng không bắt buộc có một người bấm nút thủ công trong mọi tình huống |
| **Continuous Deployment — triển khai liên tục** | Thay đổi đủ điều kiện có tự đi tới production không? | Sau các quality/policy gates, pipeline **tự động** triển khai các thay đổi hợp lệ tới production theo chính sách | Không đồng nghĩa bật tính năng cho mọi người, bỏ kiểm thử, bỏ bảo mật hay không thể dừng pipeline khi có rủi ro |

### Một cách nhận biết rất nhanh

- **CI:** “Chúng ta biết các thay đổi có tích hợp được và qua những kiểm tra đã thiết lập không?”
- **Continuous Delivery:** “Chúng ta có thể **chọn lúc** đưa một phiên bản đã được kiểm chứng tới môi trường đích một cách tin cậy không?”
- **Continuous Deployment:** “Với một thay đổi đã đủ điều kiện, **pipeline tự đưa** phiên bản đó tới production theo chính sách hay còn phải chờ quyết định triển khai thủ công thường lệ?”

**Mối quan hệ thực hành:**

~~~text
Tích hợp và kiểm tra sớm
          |
          v
Continuous Integration (CI)
          |
          v
Có thể đưa phiên bản đã kiểm chứng tới production theo yêu cầu
          |
          v
Continuous Delivery
          |
          v
Tự động đưa mọi thay đổi đủ điều kiện tới production
          |
          v
Continuous Deployment
~~~

Sơ đồ thể hiện **mức năng lực thường cần xây dựng**, không phải ba chứng chỉ hoặc ba giai đoạn tổ chức buộc mọi đội phải trải qua đúng cùng một lịch. Một hệ thống có thể đạt Continuous Delivery nhưng **chủ ý không tự động triển khai** vì có nghĩa vụ phối hợp phát hành hoặc kiểm soát rủi ro đặc thù.

### “Continuous” không có nghĩa “cứ 5 phút là production thay đổi”

“Continuous” nhấn mạnh **khả năng thực hiện thường xuyên và theo một luồng tự động hóa lặp lại**, không phải một con số thời gian áp dụng cho mọi sản phẩm. Có nhóm thay đổi vài lần một ngày; có nhóm ít thay đổi hơn nhưng vẫn có khả năng triển khai phiên bản đã kiểm chứng bất kỳ lúc nào cần. Nếu không có thay đổi nào được chấp nhận, Continuous Deployment không có lý do gì để triển khai một phiên bản mới.

## 3. Trình bày bằng một pipeline: khác biệt nằm ở điểm kích hoạt production

Giả sử mọi thay đổi được tích hợp vào nhánh chính đều đi qua cùng quy trình xác minh.

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ được tích hợp"] --> B["CI: build, unit tests,<br/>static checks"]
    B --> C["Kiểm tra tích hợp,<br/>bảo mật, chất lượng"]
    C --> D["Đóng gói artifact<br/>định danh và kiểm soát phiên bản"]
    D --> E["Triển khai môi trường thử<br/>và xác minh hệ thống"]
    E --> F{"Đạt mọi điều kiện<br/>giao hàng?"}
    F -->|Không| X["Dừng, báo lỗi,<br/>sửa và kiểm tra lại"]
    F -->|Có| G{"Chính sách triển khai production"}
    G -->|"Continuous Delivery: chọn thời điểm"| H["Kích hoạt theo yêu cầu<br/>hoặc lịch/quyết định phát hành"]
    G -->|"Continuous Deployment: tự động"| I["Tự triển khai tới production<br/>theo quality/policy gates"]
    H --> J["Triển khai production"]
    I --> J
    J --> K["Smoke checks, quan sát,<br/>bảo vệ và phản ứng sự cố"]
    K --> L["Release / bật feature<br/>nếu chính sách cho phép"]
    L --> M["Phản hồi người dùng<br/>và cập nhật ưu tiên"]
~~~

Sơ đồ cố ý tách **kích hoạt triển khai** khỏi **các bước kiểm chứng bắt buộc**. Ở cả hai nhánh, một thay đổi không đạt các điều kiện chất lượng hoặc rủi ro phải bị chặn/khắc phục theo chính sách; không có quy tắc Agile nào cho phép vượt kiểm thử phân quyền để “giữ nhịp”.

### Có thể tự động hóa mọi bước của Continuous Delivery không?

Có. Continuous Delivery thường có **pipeline tự động hóa đến mức sẵn sàng giao**, bao gồm cả thao tác triển khai. Điều khác biệt là **thời điểm đưa một thay đổi đủ điều kiện lên production có thể được chọn theo nhu cầu**. Chẳng hạn:

> Mọi commit được build và kiểm chứng tự động, có artifact đã định danh sẵn sàng đưa lên production. Product Owner và đội vận hành quyết định phát hành vào thời điểm thuận tiện; một lần kích hoạt pipeline sẽ triển khai tự động, không cần ai SSH vào server và chép file bằng tay.

Đó là Continuous Delivery, không vì có thao tác kích hoạt theo yêu cầu mà mất tính tự động hóa của quy trình triển khai.

### Continuous Deployment có thể có quality gate nghiêm ngặt không?

Có, và **nên có**. Pipeline có thể từ chối phiên bản nếu unit/integration tests hỏng, kiểm tra bảo mật không đạt, hợp đồng API bị phá vỡ hoặc canary metrics vượt giới hạn. “Không cần duyệt tay từng lần triển khai” không có nghĩa “không có quy tắc”. **Các quy tắc được thể hiện thành kiểm tra tự động và cơ chế phản ứng có trách nhiệm**.

## 4. Phân biệt build, artifact, deploy, release và outcome

Một nguồn nhầm lẫn lớn là dùng từ “phát hành” để mô tả mọi thao tác trong đường đi của mã.

| Sự kiện | Điều thực sự xảy ra | Ví dụ với “Học tiếp” | Chưa chứng minh điều gì? |
| --- | --- | --- | --- |
| **Build** | Biên dịch/đóng gói/chuẩn bị mã thành sản phẩm chạy được | Tạo tệp ứng dụng và container image | Chưa biết ứng dụng vận hành đúng ở production |
| **Artifact** | Bản phần mềm được định danh, có thể phân phối và kiểm chứng | Image mang digest xác định hoặc gói ứng dụng có phiên bản | Chưa có người dùng nhận tính năng |
| **Deploy** | Đưa artifact vào môi trường thực thi và cấu hình để chạy | Container mới chạy trên production với feature flag tắt | Tính năng có thể chưa được bật |
| **Release / feature exposure** | Cho phép người dùng hoặc nhóm người dùng sử dụng khả năng mới | Bật “Học tiếp” cho 5% học viên đủ điều kiện | Chưa chứng minh người dùng được lợi |
| **Increment sử dụng được** | Phần sản phẩm tích hợp đáp ứng tiêu chuẩn chất lượng để sử dụng | Luồng đọc, lưu tiến độ và phân quyền đạt Done | Chưa bảo đảm mục tiêu sản phẩm dài hạn |
| **Outcome** | Hành vi/kết quả thực tế thay đổi theo điều cần học | Học viên tìm lại đúng bài nhanh hơn và giảm lỗi mất tiến độ | Không nên suy chỉ từ việc deploy thành công |

**Deploy ≠ release ≠ outcome.** Có thể deploy ứng dụng mới lên production trong khi tính năng còn tắt. Cũng có thể **release lại một tính năng bằng cách đổi feature flag** mà không cần deploy artifact mới. Việc dùng từ đúng giúp Scrum Team, Product Owner và vận hành không đánh đồng năng lực kỹ thuật với giá trị người dùng.

### Cần nêu rõ đối tượng của từ “liên tục”

- **Triển khai liên tục** nói tới **đường đi của thay đổi đủ điều kiện đến môi trường production**.
- **Phát hành tăng dần** nói tới **khả năng người dùng tiếp cận một phần sản phẩm**.
- **Phản hồi liên tục** nói tới **mức độ nhanh và đáng tin của thông tin giúp nhóm điều chỉnh**.

Chúng bổ trợ nhưng không thay thế nhau. Tự động deploy nhanh mà không quan sát người dùng chỉ giải quyết một phần của vòng học hỏi Agile.

## 5. “Luôn sẵn sàng triển khai” có nghĩa cụ thể là gì?

Continuous Delivery không chỉ là có một nút Deploy trong công cụ CI. Năng lực **always deployable** phụ thuộc vào việc nhóm tin cậy trạng thái sản phẩm và có thể thực hiện quy trình giao hàng **lặp lại, kiểm tra được, không dựa vào những bước bí mật trong đầu một người**.

Một số điều kiện thực tế:

1. **Các thay đổi được tích hợp sớm.** Không tồn tại nhiều nhánh sống lâu chênh lệch lớn khiến lúc ghép mã mới biết có lỗi.
2. **Build có thể lặp lại.** Dependency, cấu hình, công cụ và phiên bản đầu vào đủ rõ để tạo artifact đáng tin.
3. **Kiểm thử và xác minh phù hợp rủi ro.** Test unit, integration, contract, bảo mật, migration và các kiểm tra khác được bố trí hợp lý.
4. **Artifact có định danh rõ.** Biết phiên bản nào đã qua kiểm tra và đang chạy ở môi trường nào.
5. **Triển khai có thể lặp lại.** Pipeline, cấu hình môi trường, bí mật và thao tác hệ thống được quản lý có kiểm soát.
6. **Không giữ lỗi pipeline kéo dài.** Khi kiểm thử bắt buộc thất bại, nhóm sửa trước khi tiếp tục tích lũy nhiều thay đổi.
7. **Khả năng theo dõi và phản ứng.** Sau triển khai có health checks, tín hiệu lỗi và phương án xử lý khi điều xấu xảy ra.
8. **Những ràng buộc ngoài kỹ thuật được làm rõ.** Ví dụ chính sách thay đổi, quyền phê duyệt, hỗ trợ khách hàng và nghĩa vụ tuân thủ có thể được đáp ứng trong quy trình.

### “Mọi commit đều releasable” phải hiểu thế nào?

Mục tiêu là **mỗi phiên bản đủ điều kiện tại nhánh/chặng giao hàng đều có thể đưa ra khi được chọn**, không phải bất kỳ commit chưa được kiểm tra nào cũng an toàn. Một build hỏng, thiếu migration hoặc vi phạm chính sách bảo mật **không được coi là sẵn sàng**.

Nếu nhánh chính thường xuyên đỏ trong nhiều ngày, hoặc phải gom sửa lỗi thủ công vào “tuần đóng gói cuối tháng” mới deploy được, nhóm **chưa có một trạng thái Continuous Delivery đáng tin** dù pipeline có tên “CD”.

## 6. Continuous Integration là nền móng, không phải đích cuối

CI tập trung vào việc **gộp thay đổi nhỏ và nhận phản hồi kỹ thuật sớm**. Phát hiện lỗi ngay khi ngữ cảnh code còn mới thường rẻ hơn phát hiện sau nhiều ngày các nhánh thay đổi đã đi xa nhau.

### Một vòng CI thông thường

~~~mermaid
flowchart LR
    A["Thay đổi mã nhỏ"] --> B["Review / merge<br/>theo chính sách nhóm"]
    B --> C["Build + static checks"]
    C --> D["Unit & integration tests<br/>phù hợp từng chặng"]
    D --> E{"Pipeline đạt?"}
    E -->|Không| F["Sửa sớm, giữ nhánh chính đáng tin"]
    F --> A
    E -->|Có| G["Artifact và tín hiệu tích hợp"]
    G -. "Phản hồi tiếp theo" .-> A
~~~

**Tích hợp thường xuyên** là điểm quan trọng hơn việc đặt tên nhánh. Một nhóm có nhánh chính và các nhánh nhỏ tồn tại rất ngắn có thể thực hành tốt nếu tích hợp, kiểm tra nhanh. Một nhóm có pipeline tự động nhưng mỗi người làm trên nhánh dài hàng tháng và tích hợp trước phát hành vẫn chịu rủi ro tích hợp muộn.

### CI nên phản hồi điều gì?

| Nhóm kiểm tra | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Build và cấu trúc** | Thay đổi biên dịch và đóng gói được | Java project build thành artifact đúng phiên bản |
| **Unit tests** | Quy tắc nhỏ có hành vi đúng | Từ chối checkpoint không hợp lệ |
| **Static analysis / lint** | Phát hiện lỗi thường gặp, cấu trúc và quy chuẩn | Không đưa mã lỗi rõ ràng hoặc secret vào repository |
| **Contract/integration tests** | Các thành phần phối hợp đúng | UI/backend không hiểu sai API tiến độ |
| **Security checks phù hợp** | Phát hiện thư viện, mã hoặc cấu hình rủi ro | Kiểm tra dependency có lỗ hổng và chính sách quyền |
| **Artifact checks** | Tạo được bản để theo dõi và triển khai | Định danh phiên bản, checksum/digest, metadata xây dựng |

Không cần chạy mọi bài kiểm thử cực kỳ tốn thời gian tại mỗi thao tác gõ mã. Có thể tổ chức **nhiều chặng phản hồi**: kiểm tra nhanh ở commit, kiểm tra sâu trước khi cho phép phát hành và một số xác nhận sau triển khai. Nhưng **các kiểm tra bắt buộc không được bị bỏ chỉ vì pipeline cần xanh nhanh**.

### Một pipeline xanh có giới hạn gì?

Các bài kiểm tra chỉ xác nhận điều **được mô tả và có thể kiểm tra**. Nếu chưa có test “không trả tiến độ tài khoản khác”, CI vẫn có thể xanh dù lỗi phân quyền tồn tại. Vì vậy, chất lượng CI phụ thuộc **đúng câu hỏi, đúng dữ liệu thử và sự quan tâm tới rủi ro thực**.

## 7. Cấu trúc một pipeline chuyển giao liên tục

Continuous Delivery mở rộng vòng CI để nhóm có thể lấy artifact đã được kiểm tra và **triển khai tới môi trường đích tin cậy**.

### Pipeline tham khảo

| Chặng | Đầu vào | Điều kiện đi tiếp | Đầu ra |
| --- | --- | --- | --- |
| **1. Source / CI** | Thay đổi đã được tích hợp | Build, unit tests, kiểm tra mã và quy tắc cơ bản đạt | Bản thay đổi có tín hiệu chất lượng |
| **2. Package artifact** | Mã/nguồn đã đủ điều kiện | Artifact được định danh, kiểm soát dependency và nguồn gốc | Image/package có thể theo dõi |
| **3. Verify** | Artifact xác định | Integration, contract, bảo mật và kiểm tra cần thiết đạt | Bằng chứng artifact đủ điều kiện thử |
| **4. Stage/pre-production** | **Chính artifact đó**, cấu hình môi trường | Kiểm tra triển khai, migration, E2E/smoke và tính tương thích | Bản được xác nhận trước production |
| **5. Ready to deploy** | Artifact và bằng chứng kiểm tra | Các quality/policy gates đạt, rủi ro còn lại được nêu rõ | Phiên bản sẵn sàng triển khai theo yêu cầu |
| **6. Production deploy** | Lệnh kích hoạt hợp lệ theo chính sách | Thực hiện quy trình tự động, sức khỏe hệ thống phù hợp | Phiên bản chạy ở production |
| **7. Verify/monitor** | Phiên bản mới hoạt động | Smoke checks, giám sát, khả năng ứng phó | Tín hiệu xác nhận hoặc kích hoạt xử lý |

**Lưu ý:** “Stage” không cần giống production tuyệt đối ở mọi thứ, nhưng sự khác biệt về cấu hình, dữ liệu, mạng, tải và quyền có thể tạo rủi ro. Đối với thay đổi ảnh hưởng dữ liệu, cần kiểm tra tương thích **với cách môi trường đích thực sự hoạt động**.

### Ví dụ cấu hình dạng giả mã

~~~yaml
# MINH HỌA LOGIC, KHÔNG PHẢI CẤU HÌNH CHẠY TRỰC TIẾP
on_change_to_main:
  - run: build_and_unit_tests
  - run: integration_and_security_checks
  - run: package_artifact_once
  - run: deploy_same_artifact_to_staging
  - run: staging_smoke_and_contract_tests

on_authorized_release_request:
  - require: all_mandatory_gates_passed
  - run: deploy_approved_artifact_to_production
  - run: production_smoke_checks
  - run: monitor_and_respond
~~~

Đặc điểm của ví dụ là **mỗi thay đổi có một đường kiểm chứng tự động**, còn việc đưa lên production xảy ra **khi có yêu cầu hợp lệ**. Yêu cầu có thể phát ra bằng nút bấm, API, lịch công bố hay quy trình quản trị thay đổi đã định nghĩa. Không cần thao tác thủ công như copy file bằng SSH.

### Build một lần, thúc đẩy đúng artifact qua các môi trường

Một nguyên tắc thiết kế hữu ích là **build artifact một lần** và dùng cùng artifact đã xác minh để triển khai trên nhiều môi trường, thay vì tạo một bản nhị phân khác ở từng bước. Như vậy, bằng chứng từ staging gắn với đúng phiên bản sẽ chạy ở production.

Điều này không có nghĩa cấu hình production phải giống dữ liệu thử hoặc secrets đều được đóng vào artifact. **Artifact và cấu hình môi trường** cần có ranh giới rõ, được quản lý và kiểm chứng phù hợp; không để bí mật thật nằm trong source code hay image.

## 8. Continuous Deployment thay đổi điều gì?

Continuous Deployment sử dụng một hệ thống kiểm chứng và triển khai tương tự, nhưng **không chờ quyết định triển khai production thủ công thường lệ cho mỗi thay đổi đã đủ điều kiện**. Khi pipeline xác nhận một phiên bản phù hợp chính sách, phiên bản được triển khai tới production tự động.

### Một biến thể giả mã

~~~yaml
# MINH HỌA LOGIC CONTINUOUS DEPLOYMENT
on_change_to_main:
  - run: build_and_unit_tests
  - run: integration_and_security_checks
  - run: package_artifact_once
  - run: deploy_same_artifact_to_staging
  - run: staging_smoke_and_contract_tests
  - require: all_mandatory_gates_passed
  - run: automatically_deploy_to_production
  - run: production_smoke_checks
  - run: monitor_canary_and_stop_if_guardrails_fail
  - run: record_version_and_deployment_evidence
~~~

**Khác biệt chính:** Bước từ “đủ điều kiện” tới “production deploy” được **tự động kích hoạt theo chính sách**, thay vì chờ lệnh phát hành thường lệ. Nhóm vẫn thiết kế cơ chế **tạm dừng pipeline, giới hạn phạm vi rollout, bảo vệ secret, kiểm tra an toàn và phục hồi khi có sự cố**.

### Nếu còn duyệt tay trước mọi deploy thì gọi thế nào?

Nếu **mỗi thay đổi** đều phải chờ một người xem và bấm duyệt **trước khi được triển khai production**, hệ thống thường được mô tả đúng hơn là **Continuous Delivery với bước phê duyệt triển khai**. Nó vẫn có thể là một quy trình tốt, đặc biệt khi nghĩa vụ quản trị chưa cho phép tự động.

Trong thực tế, có những **ngoại lệ**: hệ thống triển khai tự động hằng ngày nhưng tạm dừng khi xảy ra sự cố, trong change freeze hoặc khi kiểm tra không đạt. Một cơ chế tạm dừng **dựa trên chính sách và tình huống bất thường** không tự động phủ nhận toàn bộ năng lực Continuous Deployment của con đường thay đổi bình thường. Tuy nhiên, nếu hầu hết thay đổi phải phê duyệt tay thì không nên tự nhận “mọi thay đổi đủ điều kiện đều tự lên production”.

### Triển khai tự động không đồng nghĩa mọi feature bật ngay

Một phiên bản có thể được tự deploy sau khi đạt kiểm chứng, nhưng những chức năng còn thử nghiệm vẫn nằm sau feature flag và **chưa có người dùng thực sử dụng**. Điều đó phù hợp với Continuous Deployment: **hệ thống vận hành phiên bản mới**, còn **quyết định bật một hành vi sản phẩm** có thể độc lập và được điều phối theo rủi ro.

## 9. Quality gates và policy gates: tự động hóa kiểm soát, không bỏ kiểm soát

Muốn triển khai thường xuyên mà vẫn an toàn, nhóm cần rõ **những điều kiện nào phải đúng trước và sau mỗi lần thay đổi**.

| Gate | Câu hỏi | Cách thực hiện có thể phù hợp |
| --- | --- | --- |
| **Unit/contract/integration gate** | Quy tắc và giao diện giữa thành phần có đúng không? | Automated tests với dữ liệu và môi trường phù hợp |
| **Security gate** | Có cấu hình rủi ro, dependency nguy hiểm hoặc quyền truy cập sai không? | SAST/SCA, secret scan, kiểm tra quyền và các bài thử theo threat model |
| **Data/migration gate** | Schema và dữ liệu có tương thích với phiên bản đang chạy không? | Kiểm thử migration, contract, dữ liệu mẫu và khả năng phục hồi |
| **Infrastructure/config gate** | Hạ tầng có thay đổi đáng tin và có thể truy vết không? | IaC review, policy-as-code, kiểm tra cấu hình quyền |
| **Artifact/provenance gate** | Có biết bản nào được build, từ nguồn nào và đã kiểm tra gì? | Digest, metadata, ký artifact khi phù hợp, danh mục dependency |
| **Performance/reliability gate** | Phiên bản mới có gây suy giảm không? | Load tests chọn lọc, smoke checks, latency/error thresholds |
| **Operational gate** | Có đủ cách quan sát, cảnh báo và xử lý lỗi? | Readiness checks, canary analysis, circuit breaker/kill switch theo bối cảnh |
| **Compliance/governance gate** | Có đáp ứng chính sách tổ chức và nghĩa vụ pháp lý? | Lưu bằng chứng, segregation of duties, policy checks hoặc phê duyệt khi thật sự bắt buộc |

Không nên tuyên bố các công cụ SAST/SCA hoặc tỷ lệ coverage cao **bảo đảm tuyệt đối không có lỗi bảo mật**. Chúng là lớp phòng vệ trong hệ thống gồm thiết kế, review, kiểm thử, giám sát và phản ứng.

### Phê duyệt và Continuous Deployment có xung đột tuyệt đối không?

Không phải mọi hoạt động kiểm soát đều phải là **một người bấm duyệt trước mỗi deployment**. Tổ chức có thể phê duyệt **chính sách, điều kiện triển khai, hệ thống pipeline và quyền truy cập** từ trước; khi artifact đáp ứng các điều kiện đã được kiểm chứng, đường triển khai bình thường tự chạy. Các thay đổi rủi ro cao vẫn có thể cần cơ chế ngoại lệ.

Tuy nhiên, nếu quy định pháp lý hoặc hợp đồng **thực sự đòi phê duyệt riêng theo từng lần**, phải tôn trọng điều đó. Continuous Delivery có quy trình triển khai được tự động hóa nhưng có **cổng phê duyệt con người** có thể là lựa chọn đúng; không nên cố tự động hóa để đạt danh hiệu “Continuous Deployment”.

## 10. Vai trò của feature flags trong việc tách deploy và release

**Feature flag** là một cơ chế điều khiển cho phép bật/tắt khả năng sản phẩm mà không nhất thiết xây và triển khai lại code mỗi lần. Nó giúp nhóm đưa một phần mã chưa mở cho toàn bộ người dùng vào production, **nếu phần mã đó vẫn an toàn ở trạng thái tắt**.

~~~mermaid
flowchart LR
    A["Artifact đã được kiểm chứng"] --> B["Deploy production"]
    B --> C{"Feature flag"}
    C -->|Tắt| D["Luồng cũ tiếp tục<br/>hoạt động"]
    C -->|"Bật cho nhóm nhỏ"| E["Học viên thử nghiệm"]
    E --> F["Quan sát lỗi và phản hồi"]
    F -->|Phù hợp| G["Mở rộng phạm vi"]
    F -->|Rủi ro| H["Tắt tính năng / xử lý"]
~~~

### Các kiểu flag thường gặp

| Kiểu flag | Mục đích | Rủi ro cần quản lý |
| --- | --- | --- |
| **Release flag** | Bật một tính năng khi đã sẵn sàng với người dùng | Cấu hình sai làm mở chức năng chưa đủ điều kiện |
| **Experiment flag** | Chia đối tượng hợp lệ để so sánh trải nghiệm | Mẫu không phù hợp, đo lường gây sai hoặc làm lộ dữ liệu |
| **Operational kill switch** | Tắt một khả năng gây sự cố mà không cần chờ deploy | Phải kiểm chứng flag thật sự chặn đường lỗi và không làm mất dữ liệu |
| **Permission/entitlement control** | Điều khiển chức năng theo quyền | Không được thay kiểm soát phân quyền bắt buộc bằng một flag client-side dễ bị sửa |

### Ví dụ giả mã tính năng “Học tiếp”

~~~java
// Ví dụ minh họa: không dùng flag để thay kiểm soát quyền
public ContinueResult continueLearning(User user, Course course) {
    accessPolicy.requireAuthorized(user, course);

    if (!featureFlags.isEnabledFor("continue-learning", user.id())) {
        return ContinueResult.featureNotAvailable();
    }

    Checkpoint checkpoint = progressService.findValidCheckpoint(user, course);
    return navigationService.openAllowedLesson(user, course, checkpoint);
}
~~~

Thứ tự quan trọng: **feature flag kiểm soát khả năng hiển thị/phát hành**, còn **server phải kiểm tra quyền truy cập thật**. Flag tắt không thể bào chữa cho việc endpoint vẫn trả dữ liệu của tài khoản khác.

### Nợ kỹ thuật từ feature flags

Flags cần có **chủ sở hữu, ngày rà soát, trạng thái mặc định và kế hoạch loại bỏ**. Nếu để hàng trăm flag tồn tại lâu dài, tổ hợp bật/tắt khiến kiểm thử phức tạp và hành vi khó dự đoán. Cần kiểm tra những trạng thái có rủi ro thực, không chỉ test duy nhất khi flag bật.

## 11. Kiểm thử phù hợp với phát hành nhỏ

Năng lực Continuous Delivery/Deployment dựa vào **phản hồi nhanh nhưng đáng tin**. Nếu mỗi lần deploy phải kiểm tra tay toàn bộ hệ thống trong hai ngày, nhóm khó duy trì thay đổi nhỏ liên tục. Nhưng tự động hóa mọi thứ một cách vô chọn lọc cũng khiến pipeline chậm và dễ cảnh báo giả.

### Các lớp kiểm thử theo mục đích

| Lớp kiểm thử | Ví dụ với “Học tiếp” | Vị trí cân nhắc trong pipeline |
| --- | --- | --- |
| **Unit** | Chọn checkpoint hợp lệ, xử lý trạng thái bài | Phản hồi nhanh ở CI |
| **Component/contract** | API tiến độ giữ hợp đồng và không trả trường nhạy cảm sai | CI và chặng tích hợp |
| **Integration** | UI–API–storage xác nhận đọc/ghi đúng tài khoản | Trước khi đủ điều kiện deploy |
| **End-to-end** | Học viên hợp lệ mở đúng bài, hết quyền bị từ chối | Tập ca thiết yếu trước release/đủ điều kiện triển khai |
| **Security** | IDOR/đọc tiến độ sai tài khoản, secret và dependency | Tùy rủi ro: kiểm tra tự động thường xuyên và kiểm tra chuyên sâu bổ sung |
| **Data migration** | Chuyển checkpoint cũ sang cấu trúc mới không mất dữ liệu | Trước khi đổi schema/prod |
| **Performance/reliability** | API tiến độ đáp ứng tải dự kiến, timeout hợp lý | Kiểm tra có chọn lọc, staging hoặc canary |
| **Production smoke/health** | Ứng dụng lên đúng phiên bản, thao tác cơ bản không lỗi | Ngay sau deploy, kết hợp giám sát |
| **Exploratory/usability** | Người học có nhận ra và hiểu nút “Học tiếp” không? | Khi có bản thử phù hợp; bổ sung phản hồi sản phẩm |

Không tồn tại quy tắc “cứ có 100% unit test coverage là an toàn”. Coverage có thể cao mà thiếu kiểm thử phân quyền, dữ liệu cạnh tranh hoặc hành vi người dùng. Tương tự, tỷ lệ test xanh không có ý nghĩa nếu nhiều test flaky và nhóm thường xuyên bỏ qua chúng.

### Giữ pipeline nhanh mà không bỏ rủi ro

- Ưu tiên kiểm tra nhanh, đáng tin cho các lỗi thường gặp.
- Tách những suite tốn thời gian thành các chặng có mục tiêu và điều kiện rõ.
- Chạy kiểm thử chuyên sâu cho thay đổi liên quan dữ liệu, bảo mật hoặc tích hợp quan trọng.
- Giải quyết flaky tests hoặc cơ sở hạ tầng thử nghiệm thay vì vô hiệu hóa cả bộ test.
- Tự động thu bằng chứng để người chịu trách nhiệm có thể hiểu **phiên bản nào đã qua những điều kiện nào**.
- Khi rủi ro không thể kiểm chứng hoàn toàn trước production, sử dụng **giám sát, canary, giới hạn exposure và phương án ứng phó**.

**Tốc độ và chất lượng hỗ trợ nhau khi cách kiểm tra đúng**: thay đổi nhỏ dễ khoanh vùng lỗi, kiểm thử tốt giúp tự tin deploy và phản hồi sớm giúp giảm chi phí sửa.

## 12. Dữ liệu và database migration: phần khó của Continuous Deployment

Thay đổi mã có thể tự động, nhưng thay đổi dữ liệu và schema đôi khi ảnh hưởng **cả phiên bản đang chạy lẫn phiên bản mới**. Nếu thay tên cột ngay khi ứng dụng cũ vẫn đang phục vụ request, deployment rolling có thể hỏng giữa chừng.

### Mẫu expand–migrate–contract

Ví dụ ban đầu bảng tiến độ có cột **last_lesson_id**. Nhóm muốn chuyển sang cấu trúc **learning_checkpoint** phong phú hơn.

| Bước | Thay đổi | Điều kiện an toàn |
| --- | --- | --- |
| **Expand** | Thêm cấu trúc mới theo cách tương thích, không xóa cột cũ ngay | Phiên bản ứng dụng cũ vẫn đọc/ghi được trong giai đoạn chuyển tiếp |
| **Migrate / backfill** | Chuyển dữ liệu cũ sang cấu trúc mới, quan sát lỗi và độ đầy đủ | Chạy idempotent hoặc có cơ chế tiếp tục; không làm mất dữ liệu |
| **Transition** | Ứng dụng mới đọc/ghi theo chiến lược chuyển tiếp được kiểm chứng | Kiểm tra tính nhất quán, xử lý concurrent updates và rollback |
| **Contract** | Loại bỏ trường/đường cũ chỉ khi không còn thành phần phụ thuộc | Đảm bảo các phiên bản cũ đã ngừng sử dụng và dữ liệu đã ổn định |

**Không được tự động xóa cột cũ ngay trong deploy đầu** nếu hệ thống vẫn có phiên bản cũ hoặc job nền dùng cột đó. Một migration có thể cần nhiều đợt release, quan sát và điều kiện xác nhận rõ ràng.

### Hai câu hỏi đặc biệt quan trọng

1. **Nếu deploy mã mới thất bại, có thể quay về mã cũ mà không làm dữ liệu không tương thích không?**
2. **Nếu migration đã ghi/xóa dữ liệu thật, rollback code có hoàn tác đúng dữ liệu không?**

Với câu hỏi thứ hai, câu trả lời thường là **không tự động**. Rollback mã không phải phép quay ngược thời gian của dữ liệu. Cần kế hoạch **backup, tính tương thích, roll-forward, phục hồi có kiểm soát và kiểm chứng sau sự cố** tương ứng mức rủi ro.

### Gắn migration vào pipeline thế nào?

Thay vì một lệnh migration chạy tự do:

~~~text
Kiểm tra schema hiện tại
    → xác minh migration tương thích
    → chạy theo cơ chế an toàn/định danh version
    → đo lỗi và thời gian
    → kiểm tra dữ liệu mẫu và contract
    → cho phép phiên bản ứng dụng mới nhận tải
    → theo dõi sau triển khai
~~~

Quy trình thực tế có thể khác theo loại database và kiến trúc. Điều cần giữ là **tính lặp lại, truy vết, xác nhận dữ liệu và phương án khắc phục**.

## 13. Chiến lược đưa thay đổi vào production một cách an toàn

Continuous Deployment chỉ khả thi khi nhóm có cách **giới hạn hậu quả của một thay đổi sai**. Một số chiến lược triển khai có thể được dùng ở cả Continuous Delivery lẫn Continuous Deployment:

| Chiến lược | Ý tưởng | Điểm mạnh | Rủi ro/giới hạn |
| --- | --- | --- | --- |
| **Rolling update** | Thay dần từng instance | Không cần dừng toàn bộ hệ thống | Phiên bản cũ/mới cùng tồn tại, cần tương thích API/schema |
| **Blue–green** | Chuẩn bị môi trường mới, chuyển traffic khi đủ điều kiện | Dễ quay traffic về môi trường trước trong nhiều trường hợp | Database và shared state có thể khiến rollback không đơn giản; chi phí tài nguyên |
| **Canary** | Đưa phiên bản mới tới một phần traffic, quan sát rồi tăng dần | Giới hạn đối tượng bị ảnh hưởng, có thể phát hiện lỗi production sớm | Cần số liệu đáng tin và cơ chế dừng; canary quá nhỏ khó thấy lỗi hiếm |
| **Feature flag / progressive exposure** | Deploy sẵn nhưng bật khả năng mới theo nhóm | Tách deploy khỏi quyết định sản phẩm, có kill switch | Flag/permission có thể sai; chưa bảo vệ khỏi lỗi ảnh hưởng đường đi chung |
| **Rollback** | Trở lại artifact/config trước | Có thể giảm thời gian khôi phục khi nguyên nhân là mã | Dữ liệu hoặc thay đổi ngoài hệ thống không nhất thiết đảo ngược |
| **Roll-forward** | Đưa bản sửa tiếp theo để khắc phục | Phù hợp khi schema không thể quay lại đơn giản | Phải giữ khả năng sửa, kiểm thử và đưa bản mới an toàn |

### Canary có thể tự động hóa điều kiện mở rộng

~~~mermaid
flowchart TD
    A["Deploy canary tới phạm vi nhỏ"] --> B["Smoke checks + metrics"]
    B --> C{"Đạt guardrails<br/>đã thống nhất?"}
    C -->|Có| D["Tự tăng traffic theo bậc"]
    D --> E{"Đủ điều kiện mở rộng?"}
    E -->|Có| F["Hoàn tất rollout"]
    E -->|Không| G["Dừng/giảm traffic,<br/>thông báo và xử lý"]
    C -->|Không| G
    G --> H["Điều tra, khôi phục an toàn<br/>và học từ sự cố"]
~~~

Ví dụ một canary cho API tiến độ có thể xem **tỷ lệ lỗi, latency, số lần ghi checkpoint bất thường và tín hiệu sai dữ liệu**. Không được chỉ xem “CPU bình thường” rồi tuyên bố một thay đổi về tính đúng đắn dữ liệu đã an toàn.

### Khả năng dừng tự động quan trọng như khả năng triển khai tự động

Nếu pipeline có thể tự deploy nhưng **không thể ngắt rollout khi guardrails thất bại**, rủi ro có thể tăng nhanh. Điều kiện dừng phải được xác định **trước** khi đưa traffic mới, gồm cả người/nhóm phản ứng khi sự kiện xảy ra ngoài giờ hành chính.

**Đến đây cần phân biệt:** “Tự động triển khai” nói tới **cách thay đổi đủ điều kiện tới production**; “tự động phát hành rộng” là một quyết định khác và có thể diễn ra theo nhiều bậc với kiểm soát riêng.

## 14. Observability và vòng phản hồi sau triển khai

Trước triển khai, pipeline có thể xác minh logic dự kiến; sau triển khai, hệ thống phải trả lời **phiên bản mới có thực sự vận hành an toàn trong điều kiện production không?** Đây là lý do Continuous Delivery và Continuous Deployment cần năng lực quan sát, phản ứng và học từ sự cố.

### Ba góc nhìn cần tách

| Góc nhìn | Câu hỏi | Tín hiệu minh họa |
| --- | --- | --- |
| **Sức khỏe kỹ thuật** | Hệ thống còn cung cấp dịch vụ ổn định không? | Error rate, latency, saturation, availability, lỗi phụ thuộc |
| **Tính đúng đắn và an toàn** | Hành vi nghiệp vụ có đúng, có gây tổn hại không? | Sai chủ tài khoản, checkpoint bị ghi đè, số lần cập nhật thất bại, vi phạm chính sách |
| **Giá trị sản phẩm** | Người dùng có đạt mục tiêu dễ dàng hơn không? | Thời gian tìm lại bài, tỷ lệ mở đúng bài, hoàn thành tác vụ, phản hồi nghiên cứu |

Nếu một bản triển khai mới không tạo lỗi HTTP 500 nhưng **ghi sai tiến độ cho học viên**, dashboard hạ tầng có thể vẫn xanh trong khi sản phẩm đang gây hại. Do đó, những **business guardrails** quan trọng phải được thiết kế cùng kiểm thử và monitoring.

### Các nguồn tín hiệu

- **Metrics:** tỷ lệ lỗi, thời gian phản hồi, số tác vụ thành công/thất bại, bất thường theo phiên bản.
- **Structured logs:** thông tin đủ truy vết yêu cầu mà không lộ dữ liệu cá nhân nhạy cảm, token hoặc nội dung riêng tư.
- **Traces:** tìm thời gian và điểm lỗi trên chuỗi gọi UI–API–storage khi có nhiều dịch vụ.
- **Synthetic checks:** mô phỏng một hành trình an toàn để phát hiện dịch vụ không hoạt động.
- **Real user monitoring/feedback:** quan sát những trường hợp thực sự phát sinh và vấn đề người dùng gặp.
- **Deployment metadata:** phiên bản/digest, thời điểm, phạm vi rollout, flag state, migration và người/automation kích hoạt.

**Không phải càng nhiều log càng tốt.** Quan sát cần vừa đủ để hỗ trợ quyết định, có bảo vệ quyền riêng tư, thời hạn lưu phù hợp và kiểm soát truy cập theo vai trò.

### SLI, SLO và guardrails

Một **Service Level Indicator (SLI)** là cách đo đặc tính dịch vụ, ví dụ tỷ lệ yêu cầu truy xuất tiến độ hợp lệ thành công. **Service Level Objective (SLO)** đặt mục tiêu mức dịch vụ trong một cửa sổ thời gian. Nhóm có thể dùng ngưỡng vận hành để quyết định có tiếp tục rollout.

Ví dụ minh họa: “Nếu bản canary làm tỷ lệ lỗi checkpoint cao hơn ngưỡng đã thống nhất trong một cửa sổ có dữ liệu đủ đại diện, dừng mở rộng và điều tra”. Ngưỡng không nên chọn tùy tiện, nhất là khi traffic thấp gây nhiễu số liệu. Một SLO dịch vụ **không tự thay thế** tiêu chí đúng/sai tuyệt đối về phân quyền.

### Quy trình phản ứng sau deploy

~~~text
Triển khai artifact xác định
    |
    v
Health / smoke / business checks
    |
    +-- đạt điều kiện ---> tiếp tục rollout hoặc giữ trạng thái an toàn
    |
    '-- không đạt ------> dừng mở rộng, cảnh báo người chịu trách nhiệm
                           |
                           +--> tắt feature nếu an toàn
                           +--> rollback/roll-forward khi phù hợp
                           +--> kiểm tra dữ liệu và tác động người dùng
                           '--> hậu kiểm và đưa bài học về backlog
~~~

Một hệ thống có **đường đưa thay đổi lên production nhanh** nhưng không có **đường phát hiện và sửa tác động xấu nhanh** chưa phải một hệ thống giao hàng đáng tin cậy.

## 15. Bảo mật, chuỗi cung ứng và quyền triển khai

Tự động hóa mang lại khả năng lặp lại, nhưng cũng có thể làm lan truyền nhanh một artifact không đáng tin. Vì vậy, cần bảo vệ **nguồn mã, pipeline, artifact và môi trường production**.

| Lớp kiểm soát | Vấn đề cần tránh | Thực hành hữu ích |
| --- | --- | --- |
| **Source control** | Mã độc hoặc thay đổi trái phép vào nhánh phát hành | Quyền phù hợp, review/required checks, bảo vệ nhánh |
| **Pipeline credentials** | Token production bị lộ trong log hoặc repository | Secret manager, quyền tối thiểu, credential ngắn hạn khi có thể |
| **Dependencies** | Phụ thuộc bị thay đổi độc hại hoặc có lỗ hổng quan trọng | Lockfile/digest, SCA, giám sát cập nhật và đánh giá rủi ro |
| **Build provenance** | Không biết artifact được tạo từ mã nào | Metadata build, digest, ký/xác nhận nguồn gốc khi phù hợp |
| **Infrastructure** | Quyền và cài đặt khác giữa môi trường gây lỗi | IaC, review, policy-as-code, kiểm tra cấu hình |
| **Deploy authorization** | Ai cũng có thể thay đổi production không có dấu vết | RBAC, tài khoản dịch vụ được giới hạn, audit trail |
| **Runtime** | Phiên bản mới mở rộng quyền hoặc làm lộ dữ liệu | Runtime security, monitoring, kiểm tra quyền server-side |
| **Incident response** | Có lỗi nhưng không ai biết ai chịu trách nhiệm | On-call, runbook, rollback/roll-forward và liên lạc phù hợp |

### Policy-as-code có ích thế nào?

Thay vì phụ thuộc hoàn toàn vào kiểm tra miệng, nhóm có thể mô tả những điều kiện kiểm tra được thành **quy tắc tự động**, chẳng hạn:

~~~text
IF artifact thiếu provenance bắt buộc:
    KHÔNG deploy.

IF kiểm thử phân quyền quan trọng thất bại:
    KHÔNG deploy.

IF migration không tương thích với phiên bản đang chạy:
    KHÔNG deploy.

IF canary vượt ngưỡng lỗi đã định nghĩa:
    DỪNG rollout và kích hoạt xử lý.
~~~

Không phải mọi đánh giá rủi ro có thể chuyển hoàn toàn thành mã. Threat modeling, đánh giá dữ liệu cá nhân, kiểm tra tuân thủ và những quyết định chính sách có thể vẫn cần con người ở **thời điểm thiết kế hoặc các mốc ngoại lệ**. Tự động hóa nên giúp con người tập trung vào đánh giá có giá trị, không hợp thức hóa việc bỏ kiểm soát.

### Tránh hai cực đoan

- **“Có Continuous Deployment thì không được có bảo vệ thủ công”:** Sai. Vẫn cần cơ chế dừng khẩn, quyền quản trị và ngoại lệ hợp lệ.
- **“Bảo mật phải duyệt bằng tay mọi bước mới an toàn”:** Không nhất thiết. Nhiều kiểm soát có thể được thực thi nhất quán hơn bằng tự động hóa và audit trail, miễn tổ chức đã đánh giá chính sách đúng.

## 16. Từ thay đổi nhỏ đến độ an toàn: kích thước lô và quản lý flow

Một deployment lớn chứa hàng trăm thay đổi khiến khi có sự cố, nhóm khó xác định nguyên nhân và rollback có thể ảnh hưởng nhiều chức năng. **Chia nhỏ thay đổi, tích hợp thường xuyên và giảm thời gian chờ** thường giúp phản hồi kỹ thuật dễ sử dụng hơn.

Tuy nhiên, **nhỏ không có nghĩa không rủi ro**: một thay đổi một dòng có thể làm lộ dữ liệu hoặc tính sai học phí. Rủi ro phụ thuộc mức ảnh hưởng, cách thiết kế, điều kiện kiểm tra và khả năng phục hồi — không chỉ số dòng mã.

### Dòng công việc thường có các nút thắt

~~~mermaid
flowchart LR
    A["Ý tưởng / Product Backlog"] --> B["Developing"]
    B --> C["Code review"]
    C --> D["Build & tests"]
    D --> E["Chờ môi trường / duyệt"]
    E --> F["Deploy"]
    F --> G["Quan sát & phản hồi"]
    C -. "WIP cao" .-> H["Chờ review kéo dài"]
    E -. "Bottleneck" .-> I["Hàng đợi release"]
~~~

Nhóm có CI rất nhanh nhưng **chờ hai tuần mới được deploy** chưa chắc nhận được phản hồi production sớm hơn. Continuous Delivery giúp giảm công việc thủ công và tăng **khả năng chọn mốc giao hàng**, còn Continuous Deployment giảm thêm độ trễ do quyết định triển khai thường lệ.

### Liên hệ Kanban

| Chỉ số flow | Dùng để hỏi điều gì? | Ví dụ |
| --- | --- | --- |
| **WIP** | Bao nhiêu thay đổi đang làm nhưng chưa đạt điểm kết thúc đã chọn? | Nhiều feature chưa Done cùng chờ kiểm thử |
| **Throughput** | Bao nhiêu work item thực sự hoàn tất trong một kỳ? | Số user story đạt Done trong tuần |
| **Cycle time** | Từ lúc bắt đầu đến Done của một item mất bao lâu? | Story “Học tiếp” mất 6 ngày làm việc |
| **Work item age** | Item đang dở nào đã kéo dài quá lâu? | Một yêu cầu chờ quyết định API 9 ngày |
| **Deployment waiting time** | Từ lúc artifact đủ điều kiện đến deploy production phải chờ bao lâu? | Phải đợi release committee 10 ngày |

**Không được đánh đồng throughput story với deployment frequency.** Một lần deploy có thể chứa nhiều story, và một story có thể liên quan nhiều deployments/flags. Cần định nghĩa đúng đơn vị để thấy chỗ nghẽn thật.

### Giới hạn WIP hỗ trợ giao hàng ra sao?

Nếu 12 story cùng đang Doing nhưng không có cái nào đạt Done, tự động hóa triển khai không giải quyết hết vấn đề. Nhóm có thể giảm số item mở mới, ưu tiên hoàn tất một lát cắt end-to-end và tháo chặn review/test. Khi lượng công việc đạt chuẩn để phát hành tăng ổn định, năng lực Continuous Delivery mới thực sự được sử dụng.

## 17. Đo năng lực giao thay đổi: đừng chỉ đếm số lần deploy

Các nghiên cứu và thực hành **DevOps/DORA** thường sử dụng những chỉ số về **tốc độ đưa thay đổi tới người dùng và độ ổn định khi thay đổi**. Tên bộ chỉ số có thể được mở rộng hoặc trình bày khác nhau theo thời điểm, vì vậy dưới đây là những khái niệm thực hành cần hiểu, không phải khẳng định mọi bộ đo đều chỉ có đúng bốn chỉ số.

| Chỉ số/nhóm | Định nghĩa thực hành | Điều cần tránh |
| --- | --- | --- |
| **Deployment frequency** | Tần suất thay đổi được triển khai production, theo định nghĩa tổ chức | Tăng số deploy bằng cách triển khai rỗng hoặc chẻ nhỏ giả tạo |
| **Change lead time** | Thời gian từ lúc thay đổi mã được ghi nhận theo điểm bắt đầu xác định tới production | Nhầm với lead time từ ý tưởng sản phẩm tới lúc người dùng nhận giá trị |
| **Change failure rate** | Tỷ lệ thay đổi production gây suy giảm cần khắc phục, theo định nghĩa sự cố | Dùng số lỗi thô để so sánh nhóm có độ rủi ro sản phẩm rất khác |
| **Failed-deployment recovery time** | Thời gian khôi phục dịch vụ sau một triển khai thất bại | Báo “rollback xong” khi dữ liệu người dùng vẫn bị hỏng |
| **Deployment rework / tỷ lệ phục hồi ngoài kế hoạch** | Công sức sửa/làm lại do thay đổi production | Chỉ đo số deploy mà không đo chi phí hậu quả |
| **Pipeline duration / reliability** | Thời gian và độ tin cậy của các chặng kiểm chứng | Bỏ test quan trọng để giảm thời gian chạy |
| **Product outcome** | Hành vi người dùng và kết quả giá trị sau release | Suy ra hiệu quả sản phẩm chỉ từ tốc độ giao mã |

### Ví dụ hai nhóm có cùng deployment frequency

**Nhóm A:** deploy mỗi ngày, thường xuyên gây lỗi đăng nhập và phải khôi phục thủ công nhiều giờ.

**Nhóm B:** deploy mỗi ngày, mỗi thay đổi nhỏ có kiểm thử và canary, lỗi hiếm và được phát hiện/phục hồi nhanh.

Cùng có một lần deploy mỗi ngày **không có nghĩa năng lực giao hàng tương đương**. Cần xem **độ ổn định, thời gian sửa sai, chất lượng dữ liệu và giá trị thực**.

### Đo những mốc khác nhau phải ghi rõ

- “Từ **commit đến production**” là một loại lead time kỹ thuật.
- “Từ **Product Backlog item được yêu cầu tới Increment Done**” là dòng công việc phát triển.
- “Từ **ý tưởng đến người dùng nhận được tính năng**” là thời gian tới giá trị.
- “Từ **release đến có đủ dữ liệu retention bảy ngày**” là độ trễ học về outcome.

Không nên gộp thành một chỉ số mà không thống nhất ranh giới. Một đội có change lead time rất ngắn nhưng mất nhiều tháng chọn đúng vấn đề người dùng vẫn còn cơ hội cải tiến lớn ở phần phát hiện sản phẩm.

## 18. Continuous Delivery và Continuous Deployment trong Scrum, Kanban, XP

Hai năng lực kỹ thuật này **không phải framework quản trị sản phẩm**. Chúng giúp tạo các Increment và nhận phản hồi với ít ma sát kỹ thuật hơn, còn mục tiêu và cách phối hợp được quyết định theo bối cảnh.

### Với Scrum

Scrum có **Sprint Goal, Product Backlog, Sprint Backlog, Increment** và các sự kiện kiểm tra/thích ứng. Scrum **không yêu cầu chỉ được triển khai vào cuối Sprint**.

- Developers có thể tích hợp, kiểm thử và tạo nhiều Increment đáp ứng Definition of Done trong một Sprint.
- Increment đủ điều kiện có thể được giao/phát hành **trước Sprint Review** nếu phù hợp.
- Sprint Review giúp Scrum Team và bên liên quan kiểm tra kết quả sản phẩm; không phải bước phê duyệt bắt buộc để mã được deploy.
- Continuous Delivery giúp Product Owner và Scrum Team có khả năng **chọn thời điểm giao giá trị** mà không phụ thuộc một kỳ phát hành cứng.
- Continuous Deployment có thể giúp từng thay đổi đạt chuẩn tự tới production, nhưng việc **bật tính năng** vẫn có thể theo Sprint Goal, chiến lược rollout và phản hồi người dùng.

**Definition of Done** bảo vệ tính chất Increment. Một PBI chưa đạt Done không được gọi thành Increment hoàn tất chỉ vì pipeline đã build được mã.

### Với Kanban

Kanban giúp quan sát thay đổi từ Ready đến Developing, Test, Deploy và Done, với **Definition of Workflow, WIP, SLE và các flow metrics**. Một hàng đợi “Ready to Deploy” dài cho thấy vấn đề có thể nằm ở khâu phát hành chứ không phải coding.

Nhóm theo Kanban có thể triển khai theo dòng liên tục mà không cần Sprint cố định. Nhưng muốn dự báo đáng tin, cần theo dõi biến thiên theo loại việc và phát hiện **work item age** trước khi những thay đổi bị kẹt quá lâu.

### Với Extreme Programming (XP)

Các thực hành **TDD/test-first, continuous integration, refactoring, pair programming, simple design và small releases** giảm chi phí thay đổi. CI/CD tạo hạ tầng thực thi để những nguyên tắc đó khả thi ở quy mô đội ngũ và production.

Không có TDD không đồng nghĩa không thể Continuous Delivery; nhưng **thiếu kỷ luật kiểm thử, tích hợp và thiết kế có thể khiến pipeline nhanh mà không đáng tin**. XP giúp giảm nhu cầu kiểm tra tay lặp đi lặp lại bằng những vòng phản hồi kỹ thuật nhỏ.

### Ba khía cạnh luôn cần đi cùng

| Khía cạnh | Câu hỏi | Thực hành liên quan |
| --- | --- | --- |
| **Giá trị và ưu tiên** | Chúng ta nên tạo khả năng gì cho ai? | Product Goal, user stories, backlog, nghiên cứu người dùng |
| **Năng lực giao kỹ thuật** | Làm thế nào đưa thay đổi đúng chuẩn tới production? | CI, Continuous Delivery/Deployment, XP, kiểm thử, rollout |
| **Dòng công việc và phản hồi** | Việc bị chặn ở đâu, người dùng đã phản hồi gì? | Kanban, flow metrics, monitoring, Sprint Review/retrospective |

Nếu chỉ tối ưu một khía cạnh, nhóm có thể **giao nhanh sản phẩm sai**, hoặc **chọn đúng giá trị nhưng không thể đưa đến người dùng kịp thời**.

## 19. Tình huống xuyên suốt: nền tảng học trực tuyến đi từ CI tới triển khai tự động

Đây là **case study giả định**; mốc thời gian, mức rollout và kết quả minh họa không phải số liệu của một dự án thật.

### 19.1. Nhu cầu sản phẩm

Người học muốn nhấn “Học tiếp” để quay về đúng bài đang dở. Product Owner chia chức năng thành các lát cắt:

| Lát cắt | Giá trị | Rủi ro cần kiểm chứng |
| --- | --- | --- |
| **S1** — Hiển thị bài đang dở trên cùng thiết bị | Giảm thời gian tìm lại bài | Truy xuất đúng tài khoản, dữ liệu checkpoint hợp lệ |
| **S2** — Tiếp tục trên thiết bị thứ hai | Người học chuyển thiết bị thuận tiện | Thứ tự và tính nhất quán của cập nhật |
| **S3** — Thông báo trạng thái khi mất mạng | Người học không bị hiểu lầm là đã lưu | Retry, dữ liệu trùng, xung đột và khôi phục |
| **S4** — Cải thiện hành vi khi khóa học hết quyền | Trải nghiệm rõ hơn khi bị chặn nội dung | Không được mở nội dung được bảo vệ |

**Quyền truy cập và dữ liệu đúng** là điều kiện xuyên suốt ngay từ S1, không phải được hoãn tới S4.

### 19.2. Giai đoạn đầu: CI có nhưng phát hành theo đợt lớn

Nhóm đã có:

- Build và unit tests tự động mỗi lần merge.
- Integration tests chạy không thường xuyên, nhiều bài phải kiểm tra bằng tay.
- Mỗi cuối tháng một người vận hành copy artifact vào server.
- Migration database được thực hiện bằng các bước ghi trong chat nội bộ.
- Sự cố được phát hiện khi khách hàng báo; chưa có chỉ số riêng cho lỗi checkpoint.

**Chẩn đoán:** CI mới bao phủ một phần; đường đến production **không tự động, khó lặp lại và có nhiều điểm phụ thuộc vào con người**. Chưa thể khẳng định có Continuous Delivery đáng tin, càng không phải Continuous Deployment.

### 19.3. Cải thiện để đạt Continuous Delivery

Nhóm chọn mục tiêu đầu: “Mỗi khi S1 đạt Definition of Done và các gate bắt buộc, có thể triển khai theo yêu cầu bằng quy trình có kiểm chứng”.

Các thay đổi:

1. Tự động kiểm thử phân quyền cho API checkpoint, bao gồm người dùng truy cập sai ID.
2. Thêm integration tests và smoke tests cho luồng học tiếp cơ bản.
3. Build một artifact có digest, lưu bản và metadata kiểm tra.
4. Tự động triển khai artifact đó tới staging và xác minh.
5. Đưa migration vào quy trình có version, kiểm tra tương thích khi old/new versions cùng chạy.
6. Chuẩn hóa việc deploy production bằng pipeline theo yêu cầu, không copy file thủ công.
7. Thêm monitoring tỷ lệ ghi checkpoint thất bại, số lần mở sai bài và cảnh báo bảo mật.
8. Ghi rõ người chịu trách nhiệm khi deploy lỗi và cách giảm tác động.

**Kết quả mong muốn:** Khi phát hành S1, nhóm không cần một tuần đóng gói riêng; phiên bản đã kiểm tra **sẵn sàng triển khai khi có quyết định hợp lệ**. Đây là năng lực Continuous Delivery. Chưa cần tự động đưa mọi thay đổi lên production.

### 19.4. Quyết định khi nào phát hành S1

Giả sử Product Owner muốn thử với một nhóm học viên đăng ký tự nguyện. Nhóm thực hiện:

~~~text
CI và toàn bộ gates bắt buộc: PASS
Artifact: định danh rõ, đã kiểm tra trên staging
Yêu cầu phát hành: được xác nhận
Pipeline: deploy artifact đã kiểm tra lên production
Feature flag: bật cho nhóm thử nghiệm theo chính sách
Monitoring: quan sát dữ liệu và lỗi
Kết quả: đo hành vi "Học tiếp", xử lý phản hồi
~~~

**Đã deploy** và **đã release cho nhóm thử** là hai mốc khác nhau; người phụ trách phải nắm cả hai.

### 19.5. Cân nhắc Continuous Deployment

Sau một số chu kỳ, nhóm quan sát rằng:

- Pipeline có độ tin cậy cao và test quan trọng được bảo trì tốt.
- Đa số thay đổi nhỏ không cần quyết định thời điểm riêng.
- Có hệ thống canary, smoke checks, health metrics và dừng rollout khi rủi ro.
- Quy trình bảo mật, truy vết và quyền triển khai đáp ứng chính sách.
- Có người chịu trách nhiệm vận hành và phương án sửa lỗi khi production thay đổi.

Nhóm có thể thử chuyển **một lớp thay đổi phù hợp** sang Continuous Deployment: sau khi mọi gate đạt, thay đổi tự lên production, ban đầu với exposure có kiểm soát. Với thay đổi **migration phá tương thích, dữ liệu nhạy cảm hoặc chính sách đòi kiểm tra thêm**, nhóm không giả định tự động hóa toàn bộ ngay.

**Bài học:** Continuous Deployment là **quyết định vận hành dựa trên năng lực kiểm soát rủi ro**, không chỉ bật một tùy chọn “auto deploy”.

### 19.6. Sự cố giả định: API trả sai checkpoint cho một số học viên

Trong một canary, nhóm thấy số lần “mở bài không phù hợp checkpoint” tăng. Tuy tỷ lệ HTTP error vẫn bình thường, đây là lỗi nghiệp vụ nghiêm trọng.

Quy trình phản ứng:

1. Dừng tăng traffic và không bật tính năng cho thêm người dùng.
2. Nếu flag có thể tắt an toàn, tắt luồng mới cho nhóm thử; nếu cần, rollback/roll-forward artifact.
3. Kiểm tra **dữ liệu tiến độ đã ghi** để xác định có bị mất/sai không; không giả định rollback code đã sửa dữ liệu.
4. Thông báo cho người chịu trách nhiệm sản phẩm/vận hành theo mức ảnh hưởng, hỗ trợ người dùng theo chính sách.
5. Tạo kiểm thử hồi quy và bổ sung business guardrail trước khi rollout lại.
6. Cập nhật Product Backlog, Sprint Backlog hoặc workflow theo cách nhóm đang vận hành.

**Tự động triển khai tốt phải đi cùng khả năng tự động nhận tín hiệu xấu và phản ứng có trách nhiệm.**

### 19.7. Phản hồi giá trị khác phản hồi kỹ thuật

Sau khi S1 hoạt động ổn định, nhóm có thể phát hiện học viên vẫn khó nhận ra nút. Điều đó không chứng minh pipeline kém: **pipeline có thể giao chính xác một trải nghiệm chưa phù hợp**. Product Owner và Developers cần quan sát người học, điều chỉnh story hoặc thiết kế.

Ngược lại, người dùng có thể thích trải nghiệm nhưng dữ liệu tiến độ bị sai; nhóm phải bảo vệ an toàn trước khi mở rộng. **Cả phản hồi kỹ thuật và phản hồi giá trị đều cần thiết cho Agile**.

## 20. Chọn Continuous Delivery hay Continuous Deployment theo bối cảnh

Không có bảng xếp hạng “Continuous Deployment luôn tốt hơn Continuous Delivery” phù hợp với mọi sản phẩm. Cần xác định **rủi ro, năng lực và mục tiêu phản hồi**.

| Bối cảnh | Hướng thường đáng cân nhắc | Câu hỏi cần làm rõ |
| --- | --- | --- |
| Nền tảng dịch vụ web có kiểm thử/quan sát tốt, thay đổi nhỏ | Continuous Deployment cho những thay đổi đủ điều kiện; exposure có thể tiến dần | Nếu bản mới gây lỗi, canary/flag/rollback có chặn nhanh không? |
| Hệ thống đang deploy tay hiếm, test thiếu | Xây Continuous Delivery đáng tin trước | Có thể tái tạo build, kiểm thử và deploy an toàn theo yêu cầu không? |
| Phần mềm nhúng cần cấp chứng nhận riêng hoặc quy trình bên ngoài | Continuous Delivery cho artifact đã kiểm chứng; phát hành theo nghĩa vụ | “Production” ở đây có nghĩa gì, và ai có quyền phát hành tới thiết bị? |
| Nền tảng xử lý dữ liệu nhạy cảm, migration phức tạp | Cơ chế phân lớp theo rủi ro; pipeline mạnh, có thể giữ gate người cho thay đổi đặc biệt | Những thay đổi nào có thể tự deploy, thay đổi nào đòi kiểm tra trước? |
| Ứng dụng có nhiều tính năng đang thí nghiệm | Deploy có thể tự động; release/exposure có chiến lược flag hoặc cohort | Mẫu người dùng, quan sát và cơ chế tắt có đáng tin không? |
| Nhóm sản phẩm nhỏ, ít người on-call | Continuous Delivery trước; đánh giá khả năng tự deploy ngoài giờ cẩn thận | Ai xử lý lỗi, pipeline có giới hạn thời gian triển khai và bảo vệ năng lực nhóm không? |

### Một khung quyết định sáu câu hỏi

1. **Thay đổi có thể được kiểm chứng tự động đến mức nào?** Những rủi ro nào chưa có tín hiệu?
2. **Hậu quả nếu sai là gì?** Chỉ ảnh hưởng giao diện hay có thể mất dữ liệu, tài chính, quyền riêng tư?
3. **Khả năng phát hiện và phục hồi ra sao?** Có giám sát, rollback/roll-forward, feature flag, backup cần thiết?
4. **Có nghĩa vụ phê duyệt thật sự không?** Pháp lý, hợp đồng, phối hợp đối tác, quản trị thay đổi?
5. **Môi trường và artifact có đủ nhất quán?** Có kiểm soát cấu hình, migration, dependency và quyền truy cập?
6. **Độ trễ chờ deploy có phải nút thắt chính?** Hay nhóm đang kẹt ở phân tích nhu cầu, kiểm thử hoặc WIP quá cao?

Nếu câu trả lời cho phần lớn câu hỏi còn mơ hồ, **đầu tư vào Continuous Delivery vững chắc và khả năng quan sát** có thể tạo nhiều giá trị hơn bật Continuous Deployment ngay.

## 21. Lộ trình triển khai từ CI đến khả năng giao hàng đáng tin

Dưới đây là **lộ trình gợi ý**, không phải các bước chứng nhận bắt buộc.

### Bước 1 — mô tả đường đi hiện tại

Theo dõi một thay đổi thật:

~~~text
Code change
  → review
  → integration
  → build
  → tests
  → artifact
  → staging
  → approval / release decision
  → production
  → user exposure
  → feedback
~~~

Ghi **điểm chờ, thao tác thủ công, trách nhiệm, điều kiện kiểm chứng, lỗi thường gặp và thời gian**. Không thể tối ưu nơi tắc nếu chưa thống nhất đường đi.

### Bước 2 — làm CI đáng tin

- Developers tích hợp thay đổi nhỏ, tránh branch sống quá lâu.
- Mọi thay đổi quan trọng có build và bộ kiểm tra nhanh đáng tin.
- Nhánh chính luôn được quan tâm sửa khi pipeline thất bại.
- Bổ sung kiểm thử theo rủi ro thực, không chỉ tăng coverage để đẹp báo cáo.
- Theo dõi và giải quyết flaky tests.

**Điều kiện kiểm tra:** Khi một thay đổi làm hỏng hành vi đã kiểm thử, nhóm nhận tín hiệu đủ sớm để xử lý trước khi tích lũy nhiều thay đổi khác.

### Bước 3 — tạo artifact và pipeline deploy lặp lại

- Artifact có version/digest và nguồn gốc xác định.
- Hạn chế tạo lại artifact khác nhau ở mỗi môi trường.
- Quản lý cấu hình và secrets tách khỏi artifact, theo quyền tối thiểu.
- Tự động triển khai staging, kiểm tra hợp đồng, migration và smoke.
- Chuẩn hóa production deploy, audit trail và quy trình phục hồi.

**Điều kiện kiểm tra:** Với artifact đã qua gate, nhóm có thể triển khai theo yêu cầu mà không cần thao tác bí mật và không phá các điều kiện chất lượng.

### Bước 4 — đạt Continuous Delivery

- Các thay đổi đủ điều kiện liên tục ở trạng thái có thể giao.
- Có đường triển khai production rõ và lặp lại.
- Quyết định thời điểm hoặc đối tượng release không buộc build lại ứng dụng.
- Biết cách xử lý khi môi trường, cấu hình hoặc dữ liệu lệch kỳ vọng.
- Có giám sát sau deploy và khả năng dừng phát hành.

**Điều kiện kiểm tra:** Nhóm không phải gom mã trong nhiều tuần để “ổn định trước release”; bản phù hợp có thể được triển khai khi được chọn, với rủi ro chấp nhận được.

### Bước 5 — thử Continuous Deployment có kiểm soát

1. Chọn loại thay đổi tương đối nhỏ, dễ quan sát và có mức rủi ro phù hợp.
2. Thể hiện các quality/policy gates thành điều kiện tự động.
3. Bật auto deploy trên đường thay đổi bình thường của loại đã chọn.
4. Áp canary/progressive rollout hoặc cơ chế bảo vệ phù hợp.
5. Theo dõi thời gian phát hiện, tỷ lệ lỗi, thời gian phục hồi và sức khỏe nhóm.
6. Giữ cơ chế **pause** và quay lại Continuous Delivery theo yêu cầu khi cần.

**Điều kiện kiểm tra:** Tần suất tăng nhưng chất lượng và năng lực phản ứng vẫn được bảo vệ; các bên hiểu cách triển khai tự động tương tác với chính sách release.

### Bước 6 — dùng phản hồi để cải tiến lâu dài

Thường xuyên xem xét:

- Pipeline đang mắc ở đâu?
- Gate nào cảnh báo giả, gate nào còn thiếu?
- Loại thay đổi nào gây lỗi production?
- Thay đổi nhỏ có tạo Increment dùng được và giá trị cho người dùng?
- Có cần điều chỉnh WIP, ownership, CI hoặc môi trường thử?
- Quy trình có bền vững với on-call và thời gian làm việc không?

**Mục tiêu không phải “đạt được CD rồi dừng” mà là một năng lực học hỏi và giao hàng có thể duy trì.**

## 22. Những phản mẫu thường gặp

### 22.1. Gọi CI xanh là Continuous Delivery

Một build thành công không có nghĩa có thể tự tin triển khai production. Cần quy trình đóng gói, xác minh artifact, cấu hình, migration, triển khai và ứng phó.

### 22.2. Gọi deploy mỗi tháng là Continuous Deployment chỉ vì chạy bằng script

Một script deploy theo yêu cầu có thể là bước tiến tốt cho Continuous Delivery. Nhưng nếu phải đợi phê duyệt tay thường lệ và một lịch cố định cho mọi thay đổi, nó **không phải mô hình tự động deploy mọi thay đổi đủ điều kiện**.

### 22.3. Nhầm Continuous Delivery với deploy hoàn toàn thủ công

Continuous Delivery **không yêu cầu copy file hay chạy lệnh tay**. Khả năng triển khai theo yêu cầu phải đáng tin và nên tự động hóa mạnh. Bước chọn thời điểm khác với cách thực hiện triển khai.

### 22.4. Tự động deploy nhưng không có khả năng dừng hoặc phục hồi

Đưa phiên bản sai đến production nhanh có thể làm rủi ro tăng. Cần observability, guardrails, ownership và phương án rollback/roll-forward thích hợp.

### 22.5. Cho rằng kiểm thử tự động chứng minh tuyệt đối an toàn

CI xanh chỉ có giá trị trong phạm vi ca thử và công cụ hiện có. Thiếu bài kiểm thử phân quyền, mất dữ liệu hoặc contract có thể khiến sản phẩm vẫn sai.

### 22.6. Chỉ tăng deployment frequency làm KPI

Đếm lần deploy mà bỏ qua change failure rate, thời gian phục hồi, chất lượng dữ liệu và outcome dẫn đến tối ưu sai. Không nên thưởng/phạt từng người bằng số deploy.

### 22.7. Build lại một artifact khác ở mỗi môi trường

Nếu production chạy bản nhị phân không trùng bản đã qua test staging, bằng chứng chất lượng bị suy yếu. Nên giữ artifact được định danh và promote cùng bản, với cấu hình được kiểm soát.

### 22.8. Để database migration phá tương thích trong một bước

Ứng dụng cũ/mới cùng chạy sẽ hỏng nếu schema bị thay đổi đột ngột. Dùng chiến lược tương thích, mở rộng rồi thu hẹp khi đủ điều kiện; hiểu giới hạn của rollback.

### 22.9. Lạm dụng feature flags

Flags không thay thế authorization server-side, không tự sửa lỗi dữ liệu và có thể tăng nợ kỹ thuật. Cần owner, kiểm thử trạng thái và kế hoạch loại bỏ.

### 22.10. Bỏ qua quy tắc dữ liệu vì release chỉ cho 1% người dùng

Một lỗi làm lộ dữ liệu hoặc ghi tiến độ sai vẫn gây hại cho nhóm 1%. Rollout hẹp giới hạn phạm vi tác động **nhưng không hợp thức hóa** việc bỏ kiểm tra bắt buộc.

### 22.11. Pipeline quá chậm rồi bỏ kiểm thử để nhanh lên

Đầu tư vào phân tầng phản hồi, dữ liệu thử, môi trường và sửa flaky tests trước khi cắt bỏ kiểm tra quan trọng. Tốc độ pipeline không phải mục tiêu duy nhất.

### 22.12. Giữ nhánh sống quá lâu

CI chỉ chạy khi merge sau ba tuần khiến phản hồi tích hợp muộn. Chia thay đổi nhỏ, tích hợp thường xuyên và dùng kỹ thuật bảo vệ hành vi chưa sẵn sàng.

### 22.13. Chỉ tối ưu bước deploy, bỏ qua nút thắt sản phẩm

Một nhóm có thể tự deploy trong vài phút nhưng mất hai tháng mới xác định được story đúng. Hãy đo end-to-end và cải tiến cách làm rõ nhu cầu, ưu tiên, tách story và kiểm tra giá trị.

### 22.14. Dùng “Agile” để bỏ trách nhiệm phê duyệt thật

Nếu có nghĩa vụ tuân thủ hoặc chính sách bắt buộc, cần đáp ứng và tìm cách thực hiện nhất quán. Không đánh đổi an toàn/pháp lý chỉ để đạt nhãn Continuous Deployment.

### 22.15. Triển khai ngoài giờ không có cơ chế hỗ trợ

Auto deploy vào thời điểm không có khả năng giám sát và xử lý có thể kéo dài hậu quả. Thiết kế chính sách triển khai theo mức rủi ro, phạm vi, tự động dừng và khả năng ứng trực thực tế.

### 22.16. Tưởng deploy thành công là người dùng đã nhận giá trị

Một tính năng có thể còn tắt hoặc không giải quyết vấn đề người dùng. Cần phân biệt deploy, release, adoption, outcome và phản hồi sau sản phẩm.

## 23. Bài thực hành: phân loại pipeline

Đọc bốn tình huống sau rồi xác định **CI, Continuous Delivery hay Continuous Deployment**, giải thích điều kiện quyết định. Chúng là tình huống minh họa, không phải mô tả các nhóm thực.

| Nhóm | Cách làm hiện tại | Phân loại phù hợp nhất |
| --- | --- | --- |
| **A** | Mỗi lần merge chạy build và unit tests, nhưng mỗi ba tháng gom mã rồi thao tác thủ công trên server | Có **CI ở phạm vi nhất định**; chưa đủ bằng chứng đạt Continuous Delivery |
| **B** | Build, test, scan, đóng gói, staging và production deploy tự động hóa; production chỉ được kích hoạt khi có yêu cầu phát hành hợp lệ | **Continuous Delivery** |
| **C** | Mọi thay đổi đạt quality/policy gates được tự động đưa tới production; theo dõi canary và dừng khi có lỗi | **Continuous Deployment** trên đường thay đổi đã mô tả |
| **D** | Auto deploy nhưng phải tắt toàn bộ test và không có monitoring vì pipeline thường xuyên thất bại | Có cơ chế **auto deploy**, nhưng **không phải hệ thống triển khai liên tục đáng tin cậy** |

### Câu hỏi thảo luận

1. Điều kiện nào khiến B và C khác nhau?
2. B có thể hoàn toàn không cần thao tác SSH thủ công không?
3. Nếu C dùng feature flag để chưa bật tính năng, nó có còn triển khai tự động không?
4. D cần sửa những gì trước khi tuyên bố năng lực này có thể sử dụng an toàn?
5. Nếu C có cơ chế dừng tự động khi xảy ra sự cố, vì sao điều đó không mâu thuẫn với auto deploy?

**Gợi ý:** Khác biệt cốt lõi của B và C là **điểm kích hoạt deploy production thường lệ**, không phải việc cả hai có tự động chạy test hay không. B vẫn có thể tự động hóa toàn bộ thao tác deploy; C có thể tách exposure bằng flag và vẫn kiểm soát rủi ro.

## 24. Bài tập áp dụng vào một hệ thống cụ thể

### Bài tập A — Vẽ pipeline từ trạng thái hiện tại

Giả sử nhóm đang làm tính năng “Học tiếp” có:

- Unit tests tự động khi merge.
- Tester tự chạy kiểm thử phân quyền trên staging.
- Mỗi hai tuần quản trị viên deploy bằng lệnh tay.
- Không có cảnh báo sai checkpoint.
- Có migration database chưa kiểm tra rollback.

Hãy vẽ luồng **từ commit đến phản hồi người học**, đánh dấu:

1. Bước nào đã có CI?
2. Những điểm nào còn phụ thuộc con người hoặc thiếu bằng chứng chất lượng?
3. Điều gì cần tự động hóa để đạt Continuous Delivery trước?
4. Những điều kiện nào phải có trước khi thử Continuous Deployment?
5. Những rủi ro nào không thể giải quyết chỉ bằng tự động hóa pipeline?

**Gợi ý:** Bảo mật, dữ liệu và monitoring phải nằm trong kế hoạch. Tự động deploy một artifact chưa được kiểm chứng đúng chỉ làm lỗi tới người dùng nhanh hơn.

### Bài tập B — Phân biệt deploy và release

Pipeline tự đưa mã của tính năng mới lên production sau khi kiểm thử đạt, nhưng feature flag vẫn tắt. Ba ngày sau, Product Owner cho bật tính năng với một nhóm học viên, không deploy thêm mã.

Trả lời:

1. Khi nào đã **deploy**?
2. Khi nào đã **release** cho nhóm dùng thử?
3. Đây có thể là Continuous Deployment không? Vì sao?
4. Khi nào mới có thể kết luận outcome sản phẩm?
5. Vì sao flag không được thay thế kiểm tra phân quyền ở backend?

**Gợi ý:** Deploy và release là hai mốc. Quyết định exposure độc lập không tự làm mất khả năng auto deploy. Outcome phải được kiểm tra bằng dữ liệu và quan sát phù hợp.

### Bài tập C — Thiết kế quality gates

Đối với một API xử lý tiến độ học tập, hãy đề xuất:

| Rủi ro | Bằng chứng nên có trước production | Tín hiệu sau production |
| --- | --- | --- |
| Trả dữ liệu tài khoản khác | ... | ... |
| Retry gây ghi đè tiến độ | ... | ... |
| Migration làm mất checkpoint | ... | ... |
| API quá chậm vào giờ cao điểm | ... | ... |
| Người dùng không nhận ra nút Học tiếp | ... | ... |

**Gợi ý:** Không phải tất cả vấn đề có thể kiểm tra hoàn toàn trước deploy. Chất lượng nghiệp vụ và vận hành cần test phù hợp; khả dụng sản phẩm cần thử với người dùng và theo dõi phản hồi thực tế.

### Bài tập D — Lựa chọn chiến lược triển khai

Một thay đổi API mới tương thích với ứng dụng cũ, có feature flag và metrics đáng tin. Một thay đổi khác xóa cột database đang dùng bởi nhiều dịch vụ.

1. Thay đổi nào phù hợp thử canary/auto deploy trước?
2. Thay đổi nào cần thiết kế expand–migrate–contract?
3. Điều gì xảy ra nếu rolling update khiến old/new versions cùng chạy?
4. Vì sao rollback code có thể không cứu được dữ liệu?
5. Quyết định gì phải được đưa vào backlog trước khi release?

**Gợi ý:** Đừng dùng cùng một cơ chế “auto deploy ngay” cho mọi loại thay đổi nếu rủi ro và điều kiện tương thích khác nhau.

### Bài tập E — Đo hiệu quả sau khi tự động hóa

Trước cải tiến, thay đổi mất trung bình 12 ngày từ merge tới deploy vì đợi phát hành; sau cải tiến, phần lớn thay đổi đủ điều kiện tới production trong cùng ngày. Tuy nhiên, lỗi production cũng tăng.

Hãy đề xuất ít nhất **ba phép đo** và **hai hành động** để kiểm tra liệu quá trình đã cải thiện thật hay chưa. Tách thời gian chờ, chất lượng và tác động người dùng.

**Gợi ý:** Xem change lead time, deployment frequency, change failure rate, thời gian phục hồi, work item age, chỉ số lỗi nghiệp vụ và phản hồi người dùng. Hành động có thể là điều chỉnh gate, canary, test, phạm vi auto deploy hoặc giảm WIP.

### Bài tập F — Thực hành cùng Scrum và Kanban

Một Scrum Team chọn Sprint Goal “Học viên tiếp tục đúng bài đang dở”. Trong Sprint, Developers tạo hai Increment đã Done, nhưng lịch phát hành chỉ có ở cuối tháng. Bảng Kanban nội bộ cho thấy nhiều thẻ chờ ở “Ready to Deploy”.

Hãy trả lời:

1. Scrum có bắt buộc chờ Sprint Review mới deploy không?
2. Continuous Delivery có thể giải quyết điểm nghẽn nào?
3. Nếu có auto deploy, Product Owner còn quyết định điều gì về feature exposure?
4. Chỉ số Kanban nào giúp đo hàng đợi phát hành?
5. XP có thể giúp tăng độ tin cậy của thay đổi ra sao?

**Gợi ý:** Kết hợp các thực hành có chủ đích: Scrum giữ Sprint Goal và Done; Kanban cho thấy điểm nghẽn; XP giúp kiểm thử/tích hợp; pipeline giúp đưa phần mềm đúng chuẩn tới production khi phù hợp.

## 25. Workshop mô phỏng: chọn mô hình CD và chính sách rollout

Đây là **workshop 60–75 phút** dành cho học viên hoặc Scrum Team, không phải sự kiện bắt buộc trong Scrum hay DevOps.

| Bước | Thời lượng gợi ý | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Chọn một thay đổi** | 10 phút | Chọn user story nhỏ có hành vi và rủi ro rõ | Mục tiêu và phạm vi tính năng |
| **2. Vẽ đường giao hàng hiện tại** | 10 phút | Liệt kê commit, CI, artifact, test, stage, deploy, release | Bản đồ hệ thống và điểm chờ |
| **3. Thiết kế Continuous Delivery** | 15 phút | Chọn gates, artifact, deploy theo yêu cầu, monitoring | Pipeline có thể đưa bản đạt chuẩn lên production |
| **4. Đánh giá Continuous Deployment** | 10 phút | Xem loại thay đổi, risk gates, canary, flag và chính sách dừng | Quyết định có/không auto deploy và lý do |
| **5. Kịch bản sự cố** | 10 phút | Giả lập lỗi dữ liệu hoặc latency trong canary | Phương án dừng/khôi phục và chủ sở hữu |
| **6. Đo lường và học hỏi** | 10–20 phút | Chọn chỉ số speed, stability và value | Cách kiểm tra tác động sau vài chu kỳ |

### Tiêu chí đánh giá kết quả workshop

- Pipeline có **đường đi của đúng artifact** và những gate cần thiết không?
- Có phân biệt **điểm chọn thời gian deploy** với **cơ chế triển khai tự động** không?
- Có cơ chế **phát hiện, dừng và khôi phục** khi rủi ro xảy ra không?
- Phạm vi rollout có phù hợp rủi ro và quyền truy cập người dùng không?
- Có cách lấy phản hồi sản phẩm sau khi người dùng thật được trải nghiệm không?
- Các số đo có giúp ra quyết định thay vì chỉ tạo báo cáo nhiều đồ thị không?

Một kết quả tốt có thể là **chọn Continuous Delivery thay cho Continuous Deployment** nếu lý do dựa trên bằng chứng và rủi ro được trình bày rõ. Không chấm điểm dựa trên “tự động hóa càng nhiều càng tốt”.

## 26. Checklist trước khi tuyên bố Continuous Delivery

- [ ] Developers tích hợp thay đổi đủ thường xuyên để phát hiện lỗi sớm.
- [ ] CI có build, kiểm thử và tín hiệu lỗi đáng tin; nhánh chính không đỏ kéo dài.
- [ ] Các yêu cầu chất lượng và bảo mật quan trọng có gate hoặc bằng chứng rõ.
- [ ] Artifact được định danh; biết bản nào đã kiểm tra và bản nào đang chạy.
- [ ] Pipeline có thể triển khai **đúng artifact đó** tới môi trường đích theo yêu cầu.
- [ ] Secrets và cấu hình được quản lý ngoài source/artifact theo chính sách phù hợp.
- [ ] Các thay đổi database có chiến lược tương thích và phục hồi.
- [ ] Triển khai không phụ thuộc những thao tác thủ công không được ghi lại.
- [ ] Có health/smoke checks, monitoring và người chịu trách nhiệm sau deploy.
- [ ] Có cách giải quyết lỗi triển khai hoặc sự cố dữ liệu; không giả định rollback code là đủ.
- [ ] Quyền và chính sách phê duyệt được làm rõ và có bằng chứng tuân thủ khi cần.
- [ ] Phiên bản đạt các điều kiện bắt buộc có thể được **giao khi được chọn**, không phải chờ nhiều tuần đóng gói.
- [ ] Phân biệt **deploy, release và outcome**, không báo giá trị giả từ một build xanh.

## 27. Checklist trước khi bổ sung Continuous Deployment

- [ ] Continuous Delivery đã đủ ổn định trong bối cảnh đang xét.
- [ ] Đã định nghĩa chính xác loại thay đổi nào được auto deploy và loại nào cần ngoại lệ.
- [ ] Quality/policy gates cho đường auto deploy được kiểm tra và tin cậy.
- [ ] Mỗi phiên bản đủ điều kiện trên đường bình thường **tự được triển khai** production, không chờ duyệt tay từng lần.
- [ ] Pipeline có cơ chế pause, stop hoặc chặn rollout khi điều kiện không còn phù hợp.
- [ ] Rủi ro dữ liệu, bảo mật, tính tương thích và quyền hạn được quản lý trước khi tự triển khai.
- [ ] Có canary/rolling/blue–green/flags khi phù hợp, với guardrails có căn cứ.
- [ ] Monitoring đo cả **sức khỏe kỹ thuật lẫn tính đúng đắn nghiệp vụ**.
- [ ] Có người/chức năng đáp ứng được khi auto deploy gây sự cố trong khung giờ vận hành.
- [ ] Cơ chế rollback/roll-forward và khôi phục dữ liệu được kiểm chứng theo rủi ro.
- [ ] Feature exposure được điều khiển riêng khi cần, không mở toàn bộ tính năng chỉ vì mã đã ở production.
- [ ] Đã có số đo về tốc độ, tỷ lệ lỗi, thời gian phục hồi và kết quả người dùng.
- [ ] Khi có tác động xấu, tổ chức sẵn sàng giảm nhịp hoặc quay lại deploy theo yêu cầu thay vì giữ một danh hiệu.

## 28. Tài liệu đọc tiếp và kết luận

- Jez Humble và David Farley, *Continuous Delivery: Reliable Software Releases through Build, Test, and Deployment Automation* (2010): nền tảng về deployment pipeline, khả năng phát hành theo yêu cầu, kiểm thử và tự động hóa.
- [Martin Fowler — Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html): tư duy tích hợp thay đổi thường xuyên và nhận phản hồi sớm.
- [Martin Fowler — Continuous Delivery](https://martinfowler.com/bliki/ContinuousDelivery.html): giải thích năng lực phần mềm luôn sẵn sàng phát hành.
- [DORA — DevOps Research and Assessment](https://dora.dev/): nghiên cứu và các chỉ số đánh giá năng lực giao thay đổi, độ ổn định và cải tiến.
- [Google SRE Books](https://sre.google/books/): reliability, SLO, monitoring, incident response và vận hành dịch vụ.
- [The Scrum Guide](https://scrumguides.org/): Increment, Definition of Done, Sprint Goal và các sự kiện kiểm tra/thích ứng; Scrum không bắt buộc chỉ phát hành cuối Sprint.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, cycle time, work item age và cách cải tiến luồng.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): test-first, continuous integration, refactoring và small releases.
- [Agile Manifesto](https://agilemanifesto.org/): các giá trị ưu tiên phần mềm hoạt động, cộng tác, phản hồi và thích ứng với thay đổi.

**Kết luận:** **Continuous Integration** giúp thay đổi nhỏ được tích hợp và kiểm tra sớm. **Continuous Delivery** giúp một phiên bản đã kiểm chứng **luôn có thể triển khai tin cậy theo yêu cầu**. **Continuous Deployment** tự động đưa **mọi thay đổi đủ điều kiện** trên đường triển khai bình thường tới production mà không cần phê duyệt triển khai thủ công thường lệ từng lần. Cả hai mô hình giao hàng đều phải bảo vệ **chất lượng, bảo mật, dữ liệu, khả năng quan sát và ứng phó sự cố**.

Đích đến của Agile **không phải số lần deploy cao nhất**. Đó là khả năng **đưa phần mềm có ích tới người dùng sớm, đo phản hồi đáng tin, thay đổi backlog và cải tiến kỹ thuật liên tục**. Một nhóm chọn Continuous Delivery có kiểm soát nhưng giao giá trị thường xuyên và an toàn có thể phù hợp hơn nhóm tự deploy mọi thứ nhưng không biết khi nào sản phẩm gây hại. Hãy chọn chính sách triển khai phù hợp rủi ro, đo kết quả thực và xây năng lực để luôn có thể thay đổi khi học được điều mới.
