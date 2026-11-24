# Theo dõi lỗi lọt ra thực tế và sử dụng phản hồi để phòng ngừa

## 1. Chất lượng liên tục không kết thúc khi phần mềm được phát hành

Một Scrum Team phát triển nền tảng học trực tuyến vừa phát hành hành động **“Tiếp tục học”**. Các kiểm thử tự động đều xanh, Product Backlog Item đáp ứng Definition of Done (DoD) và một nhóm học viên thử thành công. Hai ngày sau, bộ phận hỗ trợ nhận phản hồi: học viên vừa hoàn thành bài trên điện thoại nhưng khi mở máy tính lại bị đưa về bài cũ. Trường hợp này không xuất hiện trong bộ dữ liệu kiểm thử ban đầu.

Nếu nhóm chỉ hỏi “Ai đã bỏ sót test?”, cuộc điều tra dễ dừng ở việc tìm người chịu trách nhiệm. Nếu chỉ sửa cache rồi đóng ticket, một lỗi tương tự có thể xuất hiện ở tính năng theo dõi tiến độ khác. **Chất lượng liên tục** đòi hỏi nhóm hiểu lỗi đã lọt qua những điểm kiểm tra nào, người dùng bị ảnh hưởng ra sao và cần cải thiện hệ thống phát triển như thế nào để giảm khả năng lặp lại.

**Lỗi lọt ra thực tế (escaped defect)** là khiếm khuyết của sản phẩm **được phát hiện sau khi phiên bản liên quan đã được đưa vào môi trường sử dụng thực tế**, thay vì được phát hiện và xử lý trước đó. Trong bài này, “thực tế” chủ yếu chỉ môi trường production hoặc môi trường đã phục vụ người dùng thật; phạm vi đo cụ thể phải được nhóm xác định nhất quán.

Không có hệ thống kiểm thử nào dự đoán được mọi dữ liệu, thao tác và điều kiện vận hành. Mục tiêu không phải hứa “zero bug” bằng mọi giá mà là:

- **Phát hiện sớm** những vấn đề có ảnh hưởng thực sự.
- **Giảm tác động** lên người dùng và dữ liệu trước khi mở rộng thiệt hại.
- **Khôi phục và sửa đúng** hành vi theo yêu cầu nghiệp vụ.
- **Học từ bằng chứng**, phân biệt nguyên nhân với suy đoán.
- **Phòng ngừa có trọng tâm** qua acceptance criteria, kiểm thử, thiết kế, DoD và cách vận hành.
- **Kiểm tra hiệu quả** của những cải tiến, thay vì chỉ đánh dấu action item hoàn tất.

Trong **AGILE_DEVELOPMENT**, phản hồi sau phát hành nối với việc giao Increment tăng dần, user story, Product Backlog, Scrum, Kanban, XP và đo lường dòng công việc. Lỗi trong production không nên được xem như “việc riêng của đội vận hành”; nó là thông tin cần quay trở lại **quyết định sản phẩm và hệ thống kỹ thuật**.

> **Nguyên tắc cốt lõi:** Đừng dừng ở câu hỏi “Làm sao sửa lỗi này?”. Hãy hỏi thêm: “Làm sao biết người dùng đã an toàn, vì sao hệ thống phát hiện muộn và điều gì cần thay đổi để lần sau nhận tín hiệu sớm hơn?”.

## 2. Phân biệt lỗi, sự cố, phản hồi và rủi ro

Nếu nhóm gộp mọi thông báo từ người dùng thành “bug”, dữ liệu chất lượng sẽ khó sử dụng. Một số báo cáo là khiếm khuyết thật, số khác là hành vi đúng nhưng khó hiểu, yêu cầu mới hoặc vấn đề hạ tầng.

| Khái niệm | Ý nghĩa | Ví dụ ở nền tảng học |
| --- | --- | --- |
| **Defect/bug** | Hành vi sản phẩm sai so với yêu cầu, hợp đồng hoặc thuộc tính chất lượng phải có | API cấp quyền mở bài dù học viên chưa được duyệt |
| **Escaped defect** | Defect được phát hiện khi phiên bản liên quan đã phục vụ môi trường thực tế theo phạm vi đo | Sau release, người dùng thấy tiến độ sai trên thiết bị thứ hai |
| **Incident/sự cố** | Sự gián đoạn hoặc suy giảm dịch vụ cần phản ứng vận hành; có thể do một hay nhiều lỗi, cấu hình hoặc phụ thuộc | Dịch vụ ghi danh liên tục trả lỗi trong giờ khai giảng |
| **Customer report** | Phản hồi/yêu cầu từ người dùng hoặc bộ phận hỗ trợ; chưa kết luận nguyên nhân | “Em không vào được bài học” |
| **Feature request** | Nhu cầu về hành vi mới, chưa nhất thiết là lỗi | Muốn có lịch nhắc học tùy chỉnh |
| **Usability problem** | Trải nghiệm gây hiểu nhầm hoặc cản trở dù hệ thống có thể đang chạy đúng đặc tả | Người học không phân biệt “Đã gửi yêu cầu” với “Đã ghi danh” |
| **Near miss** | Nguy cơ đã suýt gây hại nhưng được chặn trước khi ảnh hưởng thực tế | Canary phát hiện nguy cơ cấp quyền sai trước khi rollout rộng |
| **Known issue** | Vấn đề đã biết, có quyết định xử lý và phạm vi tác động được ghi nhận | Một báo cáo phụ chưa hỗ trợ múi giờ hiếm gặp |

**Một sự cố có thể tạo nhiều ticket**, và **một defect có thể gây ra nhiều sự cố hoặc hàng nghìn thông báo từ người dùng**. Khi đo lỗi lọt, cần phân biệt số khiếm khuyết riêng biệt, số lần xảy ra, số báo cáo và số người bị ảnh hưởng.

### Lỗi phát sinh từ đâu?

Defect có thể xuất hiện do:

- Quy tắc nghiệp vụ được hiểu sai hoặc thiếu ví dụ chấp nhận.
- Giả định về dữ liệu, thời gian, đồng thời hoặc quyền truy cập không đúng.
- Sai lệch hợp đồng giữa UI, API, database hoặc dịch vụ ngoài.
- Kiểm thử thiếu trường hợp biên, thiếu môi trường tương đương hoặc test flaky.
- Cấu hình, migration, feature flag hoặc triển khai sai.
- Thay đổi phụ thuộc ngoài, lưu lượng truy cập hoặc chính sách nghiệp vụ.

Không nên mặc định mọi lỗi production đều do **QA không tìm ra**. Chất lượng và cách phát hiện được tạo bởi **cả hệ thống phát triển và vận hành**.

## 3. Xác định ranh giới “lọt ra thực tế” trước khi đo

Một chỉ số chỉ có nghĩa khi mọi người hiểu **khi nào lỗi được tính là đã lọt**. Trước khi tổng hợp số liệu, nhóm cần thống nhất:

1. **Môi trường đích:** production phục vụ học viên thật, hay thêm các môi trường pilot có người dùng thật?
2. **Phiên bản hoặc cohort:** lỗi được gán cho release/Increment nào, kể cả khi phát hiện muộn?
3. **Thời điểm phát hiện:** khi tín hiệu đầu tiên xuất hiện, khi ticket được tạo hay khi đã xác nhận nguyên nhân?
4. **Đơn vị đếm:** khiếm khuyết duy nhất, incident hay lượt báo cáo?
5. **Cửa sổ quan sát:** ví dụ 14 hoặc 30 ngày sau release; lỗi phát hiện muộn hơn được xử lý ra sao?
6. **Phân loại:** lỗi mới do thay đổi hiện tại, lỗi tồn tại từ lâu, lỗi cấu hình hay vấn đề từ nhà cung cấp?
7. **Mức độ ảnh hưởng:** lỗi phân quyền nghiêm trọng không thể được đánh đồng với lỗi căn lề.

Ví dụ: một lỗi đồng bộ tiến độ được phát hiện 20 ngày sau khi phát hành phiên bản X. Nếu báo cáo đo lỗi của X chỉ theo dõi bảy ngày, lỗi đó **không nằm trong chỉ số của cửa sổ bảy ngày**, nhưng **vẫn phải được xử lý và ghi nhận**. Không được lợi dụng cửa sổ đo ngắn để che chất lượng thực tế.

### Đừng so sánh các nhóm dùng định nghĩa khác nhau

Nhóm A tính mọi lỗi phát hiện trong 30 ngày, nhóm B chỉ tính bug nghiêm trọng được khách hàng báo trong bảy ngày. Nếu A có nhiều lỗi hơn, điều đó **không đủ chứng minh** A kém chất lượng. Cần so sánh cùng ranh giới, độ phức tạp, lưu lượng, khả năng quan sát và mức độ nghiêm trọng; ngay cả khi vậy, số liệu nên phục vụ **cải tiến hệ thống** hơn là xếp hạng con người.

## 4. Những nguồn tín hiệu giúp nhận ra lỗi trước khi tác động lan rộng

Người dùng là nguồn phản hồi quý giá nhưng **không nên là hệ thống cảnh báo duy nhất**. Một số lỗi như mất dữ liệu, lộ quyền hoặc sai báo cáo có thể không được người dùng nhận thấy ngay.

| Nguồn phản hồi | Ví dụ tín hiệu | Giá trị và giới hạn |
| --- | --- | --- |
| **Báo cáo người dùng/hỗ trợ** | “Tiến độ học bị lùi về bài cũ” | Cho bối cảnh thực tế; có thể đến muộn hoặc thiếu bước tái hiện |
| **Application logs có cấu trúc** | Lỗi xử lý tiến độ với mã lỗi và phiên bản dịch vụ | Giúp truy vết; phải tránh log dữ liệu học viên nhạy cảm |
| **Metrics** | Tỷ lệ mở bài thất bại, số request ghi danh trùng, độ trễ API | Phát hiện xu hướng; không tự giải thích nguyên nhân |
| **Distributed tracing** | Lời gọi UI → API → dịch vụ tiến độ → database | Cho thấy chuỗi phụ thuộc; phải kiểm soát dữ liệu và độ mẫu |
| **Error reporting** | Ngoại lệ mới, stack trace và ảnh hưởng theo bản phát hành | Tìm lỗi runtime; thiếu ngoại lệ không đồng nghĩa đúng nghiệp vụ |
| **Synthetic checks** | Tài khoản thử định kỳ mở bài hợp lệ, thử truy cập trái quyền | Phát hiện một số đường đi biết trước; không thay người dùng thật |
| **Product analytics** | Tỷ lệ tiếp tục học giảm bất thường sau release | Có thể chỉ ra sai lệch hành vi, nhưng còn nhiều nguyên nhân khác |
| **Support/review cộng đồng** | Nhiều phản hồi cùng mô tả việc không vào được khóa | Phát hiện nhu cầu hoặc lỗi chưa có telemetry |
| **Canary/feature flag observation** | Sai lệch tăng ở nhóm dùng phiên bản mới | Giảm vùng ảnh hưởng khi rollout; cần so sánh có kiểm soát |
| **Kiểm tra bảo mật và cảnh báo truy cập** | Dấu hiệu truy cập trái phép hoặc hành vi bất thường | Có thể yêu cầu xử lý sự cố ngay, không chờ backlog |

### Nên theo dõi cái người dùng quan tâm

HTTP status 200 chưa chắc là thành công. API có thể trả 200 nhưng chọn sai bài hoặc tạo hai bản ghi đăng ký. Vì vậy, quan sát chất lượng nên có tín hiệu về **hành vi nghiệp vụ và bất biến dữ liệu**, không chỉ độ sẵn sàng máy chủ.

Ví dụ đối với luồng “Tiếp tục học”:

- Tỷ lệ yêu cầu mở bài tiếp theo **thành công và đúng quy tắc** trong các yêu cầu đủ điều kiện.
- Số lần hệ thống phát hiện tiến độ không hợp lệ hoặc trạng thái không thể đồng bộ.
- Số lượt truy cập bị chặn đúng vì không có quyền; lưu ý **nhiều yêu cầu bị từ chối đúng không phải lỗi**.
- Tỷ lệ người học hoàn tất bài đầu rồi tiếp tục bài thứ hai trong khoảng thời gian xác định.

Các metric cuối cùng cần làm rõ **mẫu số và cách thu thập**, nếu không sẽ dễ đưa đến kết luận sai.

## 5. Observability: theo dõi sức khỏe kỹ thuật và hành vi nghiệp vụ

**Observability** là khả năng suy ra trạng thái bên trong từ tín hiệu hệ thống, thường kết hợp **logs, metrics và traces**. Một hệ thống có nhiều dashboard chưa chắc có observability tốt nếu khi xảy ra lỗi vẫn không trả lời được câu hỏi “ai bị ảnh hưởng, từ lúc nào, thay đổi nào liên quan và phải hành động gì?”.

### 5.1. Logs: ghi để điều tra, không phải ghi tất cả

Một log hữu ích có thể chứa:

~~~text
event=progress_next_lesson_failed
service=learning-progress
release=2026.11.23-r2
correlation_id=<request-id-khong-chua-thong-tin-ca-nhan>
course_type=LINEAR
error_code=PROGRESS_VERSION_CONFLICT
device_context=WEB
~~~

Đây là **mẫu minh họa**, không phải định dạng bắt buộc. Correlation ID giúp nối các lời gọi liên quan; cần bảo đảm không sử dụng ID trực tiếp có thể làm lộ thông tin người dùng một cách không cần thiết. Không ghi mật khẩu, token, nội dung học riêng tư hoặc hồ sơ nhạy cảm vào log chỉ để dễ debug.

### 5.2. Metrics: phải có định nghĩa tử số và mẫu số

Ví dụ một tỷ lệ:

~~~text
Tỷ lệ yêu cầu tiếp tục học không thành công
  = Số yêu cầu đủ điều kiện thất bại do lỗi hệ thống
    / Tổng số yêu cầu tiếp tục học đủ điều kiện
~~~

Cần phân biệt thất bại kỹ thuật với việc người dùng không có quyền theo chính sách. Không cộng mọi 403 hợp lệ thành defect. Nếu một người gửi lại request năm lần, đo theo request có thể khác đo theo học viên duy nhất; tùy câu hỏi cần dùng **đơn vị đo phù hợp**.

### 5.3. Traces: thấy sai lệch qua nhiều thành phần

~~~mermaid
flowchart LR
    A["Học viên chọn Tiếp tục học"] --> B["Web/App"]
    B --> C["API gateway / authorization"]
    C --> D["Progress service"]
    D --> E["Cache"]
    D --> F["Database tiến độ"]
    E --> D
    F --> D
    D --> G["Kết quả bài tiếp theo"]
    G --> B
    B --> H["Telemetry + phản hồi"]
~~~

Nếu người dùng được đưa về bài cũ, trace có thể gợi ý progress service đọc dữ liệu cache cũ, trong khi database đã cập nhật. Tuy nhiên, trace **chỉ hỗ trợ giả thuyết nguyên nhân**; cần kiểm chứng quy tắc cache và dữ liệu thực tế trước khi kết luận.

### 5.4. SLI, SLO và cảnh báo theo tác động

Với dịch vụ quan trọng, nhóm có thể dùng:

- **SLI (Service Level Indicator):** chỉ báo đo được, như tỷ lệ yêu cầu hợp lệ thành công hoặc độ trễ.
- **SLO (Service Level Objective):** mục tiêu định lượng cho SLI trong một khoảng đo.
- **Error budget:** mức sai lệch được chấp nhận trong khuôn khổ một SLO, giúp cân đối thay đổi và độ tin cậy.

Ví dụ, mục tiêu “99,9% yêu cầu mở bài hợp lệ thành công trong 28 ngày” chỉ là **minh họa về cách viết SLO**, không phải tiêu chuẩn chung. Nếu chỉ đo HTTP 200 thì SLI có thể bỏ qua lỗi **mở sai bài**; cần bổ sung cách kiểm tra chất lượng nghiệp vụ khi khả thi.

Không nên cấu hình cảnh báo cho mọi log lỗi nhỏ. Cảnh báo cần **có khả năng hành động**, ưu tiên triệu chứng gây hại, rủi ro bảo mật/dữ liệu và xu hướng ảnh hưởng tới người dùng.

## 6. Từ phản hồi mơ hồ đến một defect có bằng chứng

Khi nhận phản hồi “Không học tiếp được”, chưa thể kết luận nguyên nhân. Nhóm cần một quy trình triage gọn nhưng đủ để không bỏ mất thông tin.

### Sáu bước phân loại ban đầu

1. **Tiếp nhận:** thời gian xảy ra, kênh phản hồi, phiên bản, thiết bị, tính năng và triệu chứng.
2. **Bảo vệ thông tin:** không yêu cầu gửi mật khẩu hoặc dữ liệu riêng tư; dùng kênh hỗ trợ an toàn nếu cần điều tra tài khoản.
3. **Đánh giá mức khẩn:** có mất dữ liệu, cấp sai quyền hoặc gián đoạn diện rộng không? Nếu có, kích hoạt quy trình sự cố.
4. **Đối chiếu với kỳ vọng:** acceptance criteria, chính sách nghiệp vụ và hành vi đã cam kết; chưa rõ thì hỏi người có thẩm quyền.
5. **Tìm cách tái hiện/bằng chứng:** dùng dữ liệu thử, logs, metrics, traces và trạng thái phù hợp; ghi những gì chưa biết.
6. **Tạo bản ghi có thể xử lý:** mô tả tác động, mức nghiêm trọng, cách tái hiện, release liên quan và chủ thể theo dõi.

### Mẫu bug report đủ dùng

~~~text
Mã vấn đề: LEARN-ESC-027
Nguồn: hỗ trợ học viên + cảnh báo sai lệch tiến độ
Được phát hiện: <thời điểm, múi giờ>
Phiên bản nghi vấn: <release/feature-flag cohort>
Triệu chứng: Sau khi hoàn tất bài trên điện thoại,
            mở lại trên web bị điều hướng về bài cũ
Kết quả mong muốn: Trang khóa mở đúng bài tiếp theo
Điều kiện quan sát: Khóa tuyến tính, hai thiết bị, thay đổi tiến độ gần nhau
Tác động: <số người/khóa đã xác minh; phạm vi chưa biết>
Bằng chứng: <correlation ID, metric, test fixture đã ẩn dữ liệu>
Mức nghiêm trọng: <theo chính sách tổ chức>
Trạng thái: đang triage / đang khắc phục / đã xác minh
Câu hỏi mở: dữ liệu cache nào bị cũ, có ảnh hưởng quyền học không?
~~~

Một báo cáo như vậy vẫn có thể là **giả thuyết defect** cho đến khi nhóm xác nhận sai lệch. Không được đánh dấu “không tái hiện được” rồi đóng ngay khi logs và phản hồi cho thấy vấn đề có thể chỉ xuất hiện dưới tải hoặc điều kiện đồng thời.

### Khử trùng lặp để đo đúng

Ba học viên báo cùng một lỗi cache có thể là **một defect** với ba báo cáo và ba lần ảnh hưởng. Ngược lại, hai lỗi khác nhau có thể cùng cho ra thông báo “Không thể mở bài”. Hãy liên kết các báo cáo theo **nguyên nhân/hành vi sai được xác nhận**, không gộp chỉ vì thông báo giống nhau.

## 7. Triage: ưu tiên theo tác động, không theo độ ồn của ticket

**Severity (mức nghiêm trọng)** mô tả tác động của khiếm khuyết; **priority (mức ưu tiên xử lý)** còn cân nhắc tính khẩn cấp, phạm vi người dùng, thời gian, ràng buộc và lựa chọn khả thi. Hai khái niệm có liên quan nhưng không đồng nhất.

| Tình huống | Tác động cần xem | Hướng xử lý phù hợp |
| --- | --- | --- |
| Người ngoài xem được nội dung/hồ sơ không có quyền | Bảo mật và quyền riêng tư, có thể nghiêm trọng ngay cả khi ít người bị ảnh hưởng | Kích hoạt phản ứng bảo mật theo quy định, hạn chế tác động và điều tra khẩn |
| Tiến độ học của nhiều học viên bị ghi đè | Nguy cơ mất dữ liệu và giảm tin cậy | Khoanh vùng, ngăn ghi sai, đánh giá phục hồi dữ liệu |
| Ghi danh thất bại trong giờ khai giảng | Nhiều người không thể thực hiện luồng cốt lõi | Ứng phó sự cố, khôi phục khả năng phục vụ sớm |
| Một nhãn giao diện sai màu nhưng không gây hiểu nhầm | Tác động thấp, không chặn nghiệp vụ | Ghi nhận và ưu tiên cùng Product Backlog |
| Lỗi hiếm làm sai trạng thái thanh toán | Có thể gây thiệt hại tài chính dù số lượng ít | Ưu tiên theo hậu quả/rủi ro, không chỉ tần suất |
| Học viên không hiểu trạng thái đúng về mặt kỹ thuật | Cản trở sử dụng; có thể là usability issue | Làm rõ nhu cầu và đo mức ảnh hưởng trước khi chọn giải pháp |

**Không phải mọi defect đều cần hotfix trong đêm**, nhưng lỗi mất dữ liệu, truy cập trái quyền hoặc sự cố đang gây hại cần cơ chế xử lý ngay, không chờ tới Sprint Planning hoặc Sprint Review.

### Các câu hỏi triage quan trọng

- Ai bị ảnh hưởng: tất cả người học, một loại khóa, một cohort release hay chỉ một thiết bị?
- Chức năng cốt lõi có bị chặn hoàn toàn hay còn phương án an toàn khác?
- Có nguy cơ cấp sai quyền, mất tiền, mất dữ liệu hoặc vi phạm nghĩa vụ nào?
- Lỗi đã xảy ra hay chỉ có tín hiệu nguy cơ? Bằng chứng tin cậy đến đâu?
- Có thể **giới hạn ảnh hưởng** bằng rollback/feature flag/giảm rollout không?
- Giải pháp tạm thời có gây tác dụng phụ hoặc tăng gánh nặng cho hỗ trợ không?
- Cần ai phối hợp quyết định: Developers, vận hành, Product Owner, bảo mật hay người quản lý sự cố?

## 8. Vòng ứng phó khi lỗi gây sự cố thực tế

Khi một lỗi đang ảnh hưởng người dùng, cần tách **khôi phục dịch vụ** khỏi **phân tích nguyên nhân dài hạn**. Trước hết bảo vệ con người, dữ liệu và tính liên tục; sau khi ổn định mới đào sâu phòng ngừa.

~~~mermaid
flowchart TD
    A["Tín hiệu production: telemetry / người dùng"] --> B["Xác nhận triệu chứng và mức ảnh hưởng"]
    B --> C{"Có sự cố/rủi ro cần xử lý khẩn?"}
    C -->|"Có"| D["Kích hoạt phản ứng sự cố, phân vai và truyền thông"]
    D --> E["Giới hạn tác động: rollback / feature flag / cô lập"]
    E --> F["Khôi phục dịch vụ, xác minh dữ liệu và quyền"]
    C -->|"Không"| G["Triage defect và ưu tiên theo tác động"]
    F --> H["Sửa nguyên nhân, kiểm thử và rollout an toàn"]
    G --> H
    H --> I["Phân tích vì sao lỗi lọt qua các lớp bảo vệ"]
    I --> J["Action phòng ngừa: test, DoD, CI, thiết kế, monitoring"]
    J --> K["Đo lại production + xác nhận phòng ngừa có hiệu quả"]
    K --> L["Cập nhật backlog và cách làm việc"]
~~~

### 8.1. Containment – giới hạn tác động

Nếu rollout mới làm học viên mở sai bài, một feature flag hoặc quay lại phiên bản cũ **có thể** giảm ảnh hưởng. Tuy nhiên, nếu thay đổi đã ghi đè tiến độ hoặc migration dữ liệu không tương thích, rollback code **không tự sửa dữ liệu**. Cần đánh giá tính nhất quán, sao lưu, khôi phục và khả năng forward fix.

### 8.2. Recovery – khôi phục và kiểm chứng

Không nên kết luận “đã khôi phục” chỉ vì dashboard hết lỗi hoặc API trả 200. Với luồng tiếp tục học, cần kiểm tra:

- Người học hợp lệ mở được đúng bài theo quy tắc.
- Dữ liệu tiến độ cũ và mới có còn nhất quán.
- Người không có quyền vẫn bị chặn.
- Hệ thống không còn tiếp tục ghi trạng thái sai.
- Bộ phận hỗ trợ biết cách xử lý trường hợp người học đã bị ảnh hưởng.

### 8.3. Communication – truyền thông theo ảnh hưởng

Tùy mức độ và quy trình tổ chức, cần thông báo rõ triệu chứng, phạm vi đã xác minh, biện pháp giảm tác động, tình trạng khôi phục và khi nào sẽ cập nhật tiếp. **Không công bố nguyên nhân như sự thật khi điều tra còn dang dở**, cũng không giấu các giới hạn đã biết của dữ liệu.

Đối với sự cố quyền riêng tư/bảo mật, tuân thủ yêu cầu thông báo, lưu bằng chứng và phối hợp theo quy định liên quan. Không đưa dữ liệu cá nhân vào báo cáo rộng rãi chỉ để minh họa mức ảnh hưởng.

## 9. Đo lỗi lọt ra thực tế như thế nào cho có ý nghĩa?

Không có một “escape rate” duy nhất áp dụng đồng nhất cho mọi tổ chức. Cần **nói rõ công thức, phạm vi, thời gian và đơn vị đếm**.

### 9.1. Defect escape rate – một cách tính thường gặp

Nếu nhóm theo dõi các defect được phát hiện trước và sau phát hành cho cùng một tập thay đổi, có thể tính:

~~~text
Defect escape rate (%)
  = Số defect duy nhất phát hiện sau phát hành trong cửa sổ đo
    / (Số defect duy nhất phát hiện trước phát hành
       + Số defect duy nhất phát hiện sau phát hành trong cửa sổ đo)
    × 100%
~~~

**Ví dụ minh họa:** phiên bản A có 24 defect được phát hiện trước release và 6 defect mới được xác nhận trong 14 ngày sau release. Tỷ lệ theo công thức và cửa sổ đã chọn là:

~~~text
6 / (24 + 6) × 100% = 20%
~~~

Điều này **không có nghĩa 20% tính năng bị lỗi**, **20% người dùng bị ảnh hưởng** hay **20% mọi lỗi có thể tồn tại trong hệ thống đã lọt**. Nó chỉ mô tả tỷ trọng những defect **được phát hiện và ghi nhận** trong tập và cửa sổ đo đó.

### 9.2. Các vấn đề khi so sánh tỷ lệ

- Một nhóm chủ động kiểm thử tốt có thể tìm **nhiều lỗi trước release**, làm tỷ lệ thấp hơn; cần xem cả mức nghiêm trọng và chất lượng thực tế.
- Nhóm vừa cải thiện observability có thể phát hiện **nhiều lỗi production hơn**, khiến tỷ lệ tăng dù khả năng phát hiện tốt hơn.
- Phiên bản phục vụ nhiều người dùng hơn có cơ hội phát hiện nhiều sai lệch hiếm hơn.
- Cửa sổ 7 ngày và 30 ngày không thể so sánh trực tiếp.
- Bug được phát hiện sau release có thể đã tồn tại từ lâu; cần quy tắc gán cohort rõ ràng.
- Một defect nghiêm trọng về bảo mật không thể được bù đắp bằng hàng chục lỗi giao diện nhỏ tìm thấy trước release.

Do đó, **escape rate nên là một tín hiệu**, không phải chỉ tiêu duy nhất để khen/phạt một Scrum Team.

### 9.3. Số defect và mức ảnh hưởng cần được xem cùng nhau

| Thước đo | Trả lời câu hỏi gì? | Cảnh báo |
| --- | --- | --- |
| **Escaped defects theo release/cohort** | Có bao nhiêu khiếm khuyết duy nhất được tìm sau khi đưa vào thực tế? | Phải thống nhất đơn vị đếm và cửa sổ |
| **Escaped defects theo severity** | Vấn đề nào thật sự nguy hiểm? | Severity cần tiêu chuẩn nhất quán |
| **Incident count** | Có bao nhiêu lần dịch vụ phải ứng phó? | Một defect có thể gây nhiều incident |
| **Affected users/requests** | Phạm vi người dùng/tác vụ bị tác động đến đâu? | Không nhân một người gửi lặp thành nhiều người duy nhất |
| **Detection latency** | Sau khi vấn đề bắt đầu, mất bao lâu mới nhận ra? | Cần biết mốc khởi đầu, đôi khi chỉ ước tính được |
| **Time to restore** | Mất bao lâu để khôi phục dịch vụ/tác động? | Khôi phục khác với hoàn tất sửa nguyên nhân |
| **Recurring defects** | Những lỗi cùng cơ chế có quay lại? | Nhìn nguyên nhân, không chỉ tên ticket |
| **Quality guardrails** | Khi giao nhanh hơn, an toàn và độ tin cậy có giảm? | Chỉ đo tốc độ sẽ khuyến khích bỏ qua kiểm thử |
| **Product outcome** | Người dùng có hoàn thành mục tiêu tốt hơn? | Sửa lỗi kỹ thuật chưa đủ bảo đảm sản phẩm hữu ích |

### 9.4. MTTD, MTTR và cách chọn mốc thời gian

**MTTD (Mean Time To Detect)** thường chỉ thời gian trung bình từ lúc sự cố bắt đầu xảy ra đến lúc được phát hiện. **MTTR** là chữ viết tắt dễ mơ hồ: nhiều tổ chức dùng cho *Mean Time To Restore*, *Recover*, *Repair* hoặc *Resolve*. Trước khi báo cáo, phải ghi rõ **điểm bắt đầu và điểm kết thúc**.

Ví dụ một sự cố:

~~~text
09:05  Tín hiệu lỗi đầu tiên xảy ra
09:27  Hệ thống cảnh báo; nhóm nhận biết vấn đề
09:40  Giới hạn rollout bằng feature flag
10:05  Hành trình chính được khôi phục và xác minh
Ngày hôm sau  Bản sửa nguyên nhân được kiểm thử và triển khai

Time to detect của sự cố này  = 22 phút (09:05 → 09:27)
Time to restore của sự cố này = 60 phút (09:05 → 10:05)
~~~

Các mốc chỉ là **minh họa**. Đây là **thời gian của một sự cố**, không phải MTTD/MTTR trung bình của đội. Nếu chưa biết lúc lỗi thực sự bắt đầu, cần ghi “ước tính” thay vì đưa ra số phút chính xác giả tạo. Việc khôi phục người dùng và xử lý toàn bộ nguyên nhân gốc có thể xảy ra ở những thời điểm khác nhau.

## 10. Ví dụ phân tích dữ liệu escape qua hai lần phát hành

Giả sử một sản phẩm ghi nhận defect **duy nhất** theo cùng định nghĩa và mỗi release có cửa sổ theo dõi 14 ngày:

| Chỉ báo | Release A | Release B |
| --- | ---: | ---: |
| Defect được phát hiện trước release | 24 | 30 |
| Defect được phát hiện sau release trong 14 ngày | 6 | 3 |
| Defect escape rate theo công thức đã chọn | 20% | 9,1% |
| Lỗi hậu phát hành severity cao | 1 | 1 |
| Người dùng bị ảnh hưởng được xác nhận | 42 | 15 |
| Thay đổi hệ thống | Giao diện tiến độ + API mới | Thêm đồng bộ thiết bị + cải thiện telemetry |

Nếu chỉ nhìn escape rate, có thể vội kết luận **Release B tốt gấp đôi Release A**. Nhưng bảng chưa cho biết:

- Tập người dùng và mức sử dụng hai bản có tương đương không?
- Defect sau release đã được gán đúng phiên bản chưa?
- Có bao nhiêu lỗi cũ chưa được phát hiện trong cửa sổ quan sát?
- Severity cao của hai release có cùng mức hậu quả không?
- Sau khi cải thiện telemetry, có thay đổi số lỗi được phát hiện tự động?
- Những thay đổi của Release B có khó hoặc rủi ro hơn không?

**Kết luận hợp lý hơn:** trong cửa sổ đo và cách phân loại đã nêu, tỷ lệ defect được phát hiện sau release giảm từ 20% xuống khoảng 9,1%. Đây là tín hiệu đáng điều tra thêm, **không tự chứng minh cải tiến đã gây ra sự giảm**.

### Đếm lỗi ít hơn không phải lúc nào cũng an toàn hơn

Ví dụ, Release A có sáu lỗi nhẹ về trình bày, còn Release B chỉ có một lỗi lọt nhưng cấp quyền sai cho người học. Phân tích chất lượng phải ưu tiên **tác động, mức rủi ro và người dùng bị ảnh hưởng**, không được để tổng số ticket che vấn đề nghiêm trọng.

## 11. Case study: lỗi tiến độ trên hai thiết bị lọt vào production

### 11.1. Bối cảnh, phạm vi và phát hiện

Nền tảng học triển khai thay đổi cho phép học viên tiếp tục từ bài đã hoàn thành gần nhất. Increment đã qua unit tests cho quy tắc chọn bài và kiểm thử UI trên một thiết bị. Sau release, bộ phận hỗ trợ nhận phản hồi: hoàn thành bài trên điện thoại, mở máy tính ngay sau đó đôi khi vẫn bị điều hướng về bài cũ.

Nhóm kiểm tra và **giả định trong ví dụ** xác nhận:

- Vấn đề chỉ xuất hiện ở một số chuỗi cập nhật giữa hai thiết bị.
- Database đã lưu tiến độ mới, nhưng một lớp cache trên web vẫn trả dữ liệu cũ.
- Không có bằng chứng người dùng không có quyền đã được cấp quyền trái phép; điều này vẫn cần kiểm tra riêng.
- Một lát rollout đã ảnh hưởng đến **42 trong 1.800 học viên đủ điều kiện được theo dõi**, tương đương khoảng **2,33%** của tập đó.

Tỷ lệ 2,33% chỉ áp dụng cho **tập 1.800 học viên có phạm vi theo dõi xác định**. Không được khẳng định toàn bộ học viên trên nền tảng đều bị ảnh hưởng đúng tỷ lệ ấy khi mẫu quan sát không đại diện hoặc telemetry thiếu.

### 11.2. Giới hạn tác động trước

Nhóm phản ứng theo chính sách sự cố:

1. Xác minh triệu chứng và khoanh vùng những release/cohort liên quan.
2. Nếu có phương án an toàn, giảm rollout hoặc tắt đường đọc cache mới.
3. Bảo đảm quá trình tiếp tục học sử dụng nguồn dữ liệu tin cậy, không tạo bản ghi tiến độ ngược.
4. Xác minh người học mở đúng bài tiếp theo và các kiểm tra quyền vẫn đạt.
5. Cung cấp thông tin đủ rõ cho hỗ trợ về những người dùng đã bị ảnh hưởng.
6. Sau khi ổn định, mới thực hiện bản sửa gốc và rollout có kiểm soát.

Với vấn đề tiến độ, cách “xóa toàn bộ cache” có thể khôi phục một số trường hợp nhưng cũng có thể tạo tải đột biến hoặc ảnh hưởng chức năng khác. Nhóm cần **đánh giá hệ quả của biện pháp giảm tác động**, không áp một lệnh vận hành bừa bãi.

### 11.3. Lần theo chuỗi sự kiện

~~~mermaid
sequenceDiagram
    participant M as Mobile
    participant P as Progress Service
    participant DB as Database
    participant C as Cache web
    participant W as Web
    M->>P: Hoàn thành bài 2
    P->>DB: Ghi tiến độ mới
    DB-->>P: Ghi thành công
    Note over P,C: Đường làm mới cache bị bỏ sót
    W->>P: Xin bài tiếp theo
    P->>C: Đọc snapshot tiến độ
    C-->>P: Tiến độ cũ: mới xong bài 1
    P-->>W: Bài 2 thay vì bài 3
~~~

Sơ đồ là **giả thuyết kỹ thuật minh họa**, không phải bằng chứng đã được kiểm chứng của một hệ thống có thật. Trong điều tra thực, phải đối chiếu timestamp, request correlation, dữ liệu cache và quy tắc nhất quán.

### 11.4. Điều gì cho thấy kiểm thử đã thiếu?

Bộ kiểm thử ban đầu bao phủ:

- Từ tiến độ 0/3 trả bài 1.
- Từ tiến độ 1/3 trả bài 2.
- Từ tiến độ 3/3 trả trạng thái hoàn thành.
- UI hiển thị đúng nhãn “Tiếp tục học” trong một phiên.

Nhưng **không có kiểm thử tích hợp cho hành trình cập nhật tiến độ ở thiết bị A rồi đọc tiến độ ở thiết bị B**. Unit test của thuật toán vẫn hoàn toàn đúng; sai lệch nằm ở **đồng bộ trạng thái và tính mới của dữ liệu qua các thành phần**.

### 11.5. Biện pháp phòng ngừa theo nhiều lớp

| Lớp | Điều chỉnh dựa trên bằng chứng |
| --- | --- |
| **Nghiệp vụ/acceptance criteria** | Làm rõ kỳ vọng về thời điểm tiến độ phải nhất quán giữa thiết bị |
| **Thiết kế** | Xác định nguồn dữ liệu có thẩm quyền, quy tắc làm mới cache và phiên bản tiến độ |
| **Kiểm thử tích hợp** | Thử ghi trên thiết bị A, đọc trên B sau các điều kiện đồng bộ đã cam kết |
| **Contract/API** | Đảm bảo service trả trạng thái/phiên bản dữ liệu dễ diễn giải nhất quán |
| **CI** | Chạy kiểm thử rủi ro này trong tập thích hợp, không để chỉ chạy thủ công sát release |
| **Observability** | Theo dõi tín hiệu tiến độ cũ hoặc phiên bản xung đột mà không log thông tin nhạy cảm |
| **Rollout** | Phân nhóm release và giám sát chỉ số tiến độ trước khi mở rộng |
| **DoD** | Ghi rõ tiêu chí chất lượng liên quan đồng bộ dữ liệu khi thay đổi khả năng tiến độ |

**Không phải đưa tất cả mọi lỗi từng xảy ra thành một checklist vô tận.** Cần chọn các **bất biến và loại rủi ro chung**: ví dụ “khi cập nhật tiến độ có nhiều bên sử dụng, phải xác minh đường ghi–đọc giữa những thành phần liên quan”.

## 12. Phân tích nguyên nhân mà không biến postmortem thành buổi quy lỗi

Sau khi dịch vụ đã ổn định, nhóm thực hiện **post-incident review/postmortem** nhằm hiểu cơ chế gây lỗi và điều kiện khiến lỗi không bị phát hiện sớm. Tư duy **blameless** không có nghĩa bỏ trách nhiệm; nó giúp người tham gia nói trung thực về giả định, hệ thống và những quyết định trong bối cảnh thực tế.

### 12.1. Chuỗi “5 Whys” – đặt câu hỏi, không suy đoán một nguyên nhân duy nhất

Ví dụ minh họa:

1. **Vì sao web mở bài cũ?** Vì service đọc tiến độ từ cache chưa được làm mới.
2. **Vì sao cache chưa được làm mới?** Đường cập nhật từ thiết bị di động không kích hoạt chính sách invalidation tương ứng.
3. **Vì sao đường cập nhật này bị bỏ sót?** Hợp đồng cập nhật tiến độ mới chỉ được kiểm tra qua đường cập nhật trên cùng phiên.
4. **Vì sao kiểm thử chỉ gồm một phiên?** Các ví dụ chấp nhận chưa đề cập luồng chuyển thiết bị và trạng thái dữ liệu cũ.
5. **Vì sao điều đó chưa được làm rõ?** Refinement tập trung vào UI, thiếu trao đổi ranh giới dữ liệu và các rủi ro về đồng bộ liên thành phần.

Đây là **chuỗi giả thuyết có thể cần bằng chứng**, không phải một “đáp án” đã được xác minh. Một sự cố thực có thể có **nhiều nguyên nhân đóng góp**, như thiết kế cache, cấu hình, thời điểm triển khai và thiếu metric; 5 Whys không bắt buộc luôn dừng chính xác ở câu hỏi thứ năm.

### 12.2. Tách nguyên nhân tạo lỗi và nguyên nhân lỗi lọt qua

| Câu hỏi | Ví dụ từ case study |
| --- | --- |
| **Cơ chế tạo lỗi (causal mechanism)** | Dữ liệu cache không đồng bộ với tiến độ mới trong điều kiện chuyển thiết bị |
| **Tại sao kiểm thử trước release không tìm ra?** | Thiếu trường hợp tích hợp giữa hai phiên/thiết bị; fixture chỉ có một luồng |
| **Tại sao phát hiện production không sớm hơn?** | Metric chỉ đo HTTP lỗi, không thấy trường hợp trả 200 nhưng mở sai bài |
| **Tại sao ảnh hưởng lan tới nhiều người?** | Rollout chưa có guardrail theo chất lượng tiến độ, tín hiệu hỗ trợ đến muộn |
| **Tại sao sửa lỗi có thể lâu?** | Log thiếu correlation và thiếu cách tái hiện dữ liệu cache an toàn |

Nếu chỉ “thêm một unit test”, nhóm có thể bỏ sót **cơ chế làm dữ liệu cũ**. Nếu chỉ bổ sung cảnh báo, nhóm có thể phát hiện nhanh hơn nhưng **lỗi vẫn tiếp tục xuất hiện**. Phòng ngừa tốt thường cần **giảm xác suất xảy ra và tăng khả năng phát hiện/giới hạn tác động**.

### 12.3. Một postmortem gọn nên lưu những gì?

~~~text
Mô tả sự cố và tác động đã xác minh:
Thời điểm bắt đầu/phát hiện/khôi phục, kèm độ bất định:
Phiên bản và nhóm người dùng ảnh hưởng:
Dòng thời gian quyết định và thông tin đã có khi đó:
Cơ chế gây sai lệch và bằng chứng:
Các yếu tố đóng góp từ yêu cầu, thiết kế, test, CI, vận hành:
Điều đã giúp phát hiện hoặc giảm ảnh hưởng:
Điều chưa biết và cách xác minh:
Biện pháp sửa ngay:
Biện pháp phòng ngừa có chủ sở hữu và điều kiện hoàn tất:
Chỉ số/guardrail và mốc xem lại sau cải tiến:
~~~

Báo cáo không cần dài hàng chục trang cho một lỗi nhẹ. Độ sâu phải tương xứng với **mức ảnh hưởng và khả năng học được điều có giá trị**.

## 13. Chuyển bài học thành biện pháp phòng ngừa cụ thể

Một lỗi lọt ra thực tế chỉ thật sự trở thành cơ hội học hỏi khi nhóm có **hành động thay đổi được cách hệ thống hoạt động**. “Cẩn thận hơn” hoặc “nhắc mọi người test kỹ hơn” không phải biện pháp đủ mạnh nếu vấn đề bắt nguồn từ thiếu hợp đồng, thiếu dữ liệu thử hoặc thiếu khả năng quan sát.

| Phát hiện trong điều tra | Biện pháp phòng ngừa | Bằng chứng hoàn tất |
| --- | --- | --- |
| Nghiệp vụ có hai cách hiểu về trạng thái ghi danh | Thống nhất ví dụ bằng ATDD/Three Amigos; bổ sung acceptance criteria | Quy tắc được xác nhận, kịch bản chính/âm có test |
| Thay đổi API phá client cũ | Contract test và chính sách tương thích phiên bản | Test cả bên cung cấp/tiêu thụ trong CI |
| Hai request đồng thời tạo trùng đăng ký | Ràng buộc dữ liệu và kiểm thử transaction/concurrency | Thử nhiều request đồng thời vẫn giữ bất biến |
| Sai quyền chỉ bị phát hiện bằng thao tác thủ công | Security/API tests cho tình huống truy cập trái quyền | Test chạy ổn định và bảo vệ endpoint thực |
| Cache chưa đồng bộ giữa thiết bị | Test tích hợp ghi–đọc đa phiên, theo dõi phiên bản dữ liệu | Kịch bản từng gây lỗi nay được phát hiện nếu tái xuất hiện |
| Lỗi bị ẩn vì API trả HTTP 200 | Business metrics/guardrail phản ánh kết quả có ý nghĩa | Dashboard/cảnh báo dựa trên sai lệch người dùng quan trọng |
| CI flaky khiến nhóm bỏ qua kết quả | Sửa môi trường/dữ liệu test và làm rõ chính sách xử lý đỏ | Mức flaky giảm, kết quả trở nên đáng tin |
| Release lớn khó khoanh vùng | Chia Increment nhỏ và canary/rollout có kiểm soát | Có cách phát hiện và dừng lan rộng thực tế |

### “Thêm test” cần chỉ ra test nào và vì sao

Một action item tốt:

> “Bổ sung kiểm thử tích hợp: cập nhật hoàn thành bài 2 trên thiết bị A, truy vấn bài tiếp theo từ phiên B theo hợp đồng đồng bộ; test phải thất bại khi chính sách làm mới cache bị vô hiệu hóa và chạy trong CI trước khi merge thay đổi vào service tiến độ.”

Một action item yếu:

> “QA tăng coverage lên 90%”.

Độ bao phủ mã có thể hữu ích, nhưng **không chỉ ra hành vi sản phẩm nào cần được bảo vệ**. Nên ưu tiên những thử nghiệm chứng minh một loại sai lệch thực sự có thể bị phát hiện.

### Gắn phòng ngừa với nơi làm việc hằng ngày

Biện pháp có thể đi vào:

- User story/acceptance criteria trong Product Backlog.
- Definition of Done và danh sách kiểm tra thay đổi theo rủi ro.
- Bộ kiểm thử hồi quy, CI, contract test hoặc test dữ liệu.
- Chính sách code review và thiết kế giao diện giữa các nhóm.
- Dashboard, cảnh báo, runbook và rollout.
- Refinement, Sprint Retrospective hoặc buổi cải tiến luồng Kanban.

**Đừng chỉ ghi action item vào biên bản rồi không theo dõi**. Mỗi hành động cần người phụ trách, tiêu chí chấp nhận và thời điểm xem lại.

## 14. Đưa phản hồi chất lượng vào Product Backlog và nhịp Agile

Khi sản phẩm đã phục vụ người dùng thật, lỗi và tín hiệu chất lượng cạnh tranh với các hạng mục tạo tính năng mới. Cần phân biệt **ứng phó khẩn cấp**, **sửa lỗi có thể lên kế hoạch** và **đầu tư phòng ngừa**.

### 14.1. Sự cố khẩn không chờ Sprint Planning

Nếu người dùng truy cập dữ liệu trái quyền hoặc dịch vụ không thể ghi danh trong giờ khai giảng, tổ chức cần hành động theo quy trình sự cố. Không nên viện cớ “Sprint này đã cam kết đủ story point” để trì hoãn bảo vệ dữ liệu và người dùng.

### 14.2. Bug và cải tiến phòng ngừa đi vào backlog như thế nào?

Với công việc không khẩn, Product Owner và Scrum Team xem:

- Mức ảnh hưởng và rủi ro nếu trì hoãn.
- Giá trị khi khắc phục hoặc loại bỏ một lớp lỗi tương tự.
- Mức bất định về nguyên nhân và khả năng kiểm chứng.
- Năng lực, phụ thuộc và chi phí cơ hội so với công việc sản phẩm.
- Những chuẩn chất lượng tổ chức bắt buộc phải đáp ứng.

Một defect có thể dẫn tới **bug fix**, **spike điều tra**, **PBI cải tiến kiểm thử/quan sát**, hoặc **thay đổi acceptance criteria**. Không nhất thiết mỗi incident luôn tạo một epic lớn.

### 14.3. Các sự kiện Scrum có vai trò khác nhau

| Hoạt động | Cách sử dụng phản hồi lỗi |
| --- | --- |
| **Product Backlog refinement** | Làm rõ bug, rủi ro, tiêu chí chấp nhận và biện pháp phòng ngừa |
| **Sprint Planning** | Lựa chọn công việc phù hợp Sprint Goal và năng lực, tính cả chất lượng cần thiết |
| **Daily Scrum** | Developers xem trở ngại, điều chỉnh kế hoạch tiến tới Sprint Goal; xử lý việc bất ngờ cần thiết |
| **Sprint Review** | Kiểm tra Increment, kết quả thật và thay đổi bối cảnh; xem Product Backlog cần thích ứng thế nào |
| **Sprint Retrospective** | Phân tích cách làm, công cụ, chất lượng và chọn cải tiến giúp lỗi ít lọt hơn |

**Sprint Review không phải phiên điều tra kỹ thuật chuyên sâu** về một root cause đã biết; stakeholder cần hiểu tác động lên giá trị và bước tiếp theo. **Retrospective không thay thế ứng phó sự cố**, nhất là với lỗi phải giải quyết ngay.

### 14.4. Kanban giúp nhìn sự tắc nghẽn do lỗi và làm lại

Nhóm có thể theo dõi **WIP, cycle time, throughput và work item age** để thấy bug đang nằm lâu ở bước nào: chờ xác nhận, chờ môi trường tích hợp, chờ review hay chờ triển khai. Một luồng lỗi có chính sách ưu tiên khẩn khác với luồng cải tiến thông thường có thể hữu ích, nhưng cần minh bạch để công việc khẩn không trở thành “lối tắt” cho mọi yêu cầu.

### 14.5. XP và Lean giúp biến học hỏi thành chất lượng

XP mang tới TDD, refactoring, tích hợp liên tục và phát triển theo bước nhỏ để sai lệch được phát hiện sớm. Lean nhấn mạnh giảm chờ đợi, làm lại và tối ưu **toàn dòng giá trị**; một nhóm viết code nhanh nhưng lỗi hậu phát hành tăng và thời gian khôi phục dài chưa chắc giao giá trị nhanh hơn.

## 15. Đánh giá hiệu quả phòng ngừa sau khi đã sửa

Đóng ticket “đã thêm test” mới là **hoàn tất hoạt động**, chưa chứng minh phòng ngừa có tác dụng. Cần xác định trước **điều gì sẽ được quan sát và trong bao lâu**.

### Một vòng học hỏi có thể kiểm chứng

1. **Đặt giả thuyết:** “Test tích hợp đa phiên sẽ phát hiện sai lệch cache trước release và giảm lỗi mở bài cũ sau phát hành”.
2. **Ghi đường cơ sở:** nhóm đang phát hiện bao nhiêu lỗi loại này ở đâu, với điều kiện và mức sử dụng nào.
3. **Thực hiện cải tiến:** thêm test, sửa thiết kế cache, xác nhận CI và cách rollout.
4. **Kiểm tra test có phát hiện lỗi:** thực hiện một biến đổi có kiểm soát trong môi trường thử để thấy test thực sự đỏ khi hành vi sai.
5. **Quan sát production:** lỗi cùng cơ chế có tái xuất hiện không, cảnh báo có phát hiện được không, người dùng có còn gặp vấn đề?
6. **Đối chiếu tác dụng phụ:** thời gian CI, test flaky, độ trễ API và tác động tới trải nghiệm học.
7. **Cập nhật cách làm:** giữ cải tiến có giá trị, điều chỉnh hoặc dừng phần gây chi phí mà không tăng bằng chứng.

### Ví dụ ma trận theo dõi hành động

| Hành động | Bằng chứng hoàn tất | Cách kiểm tra hiệu quả |
| --- | --- | --- |
| Thêm test đa thiết bị | CI chạy test với hai phiên và dữ liệu tiến độ phù hợp | Test đỏ khi cố tái tạo lỗi cache; không có hồi quy tương tự trong cửa sổ quan sát đã chọn |
| Cải thiện metric tiến độ | Metric có định nghĩa, nhãn và dashboard đúng | Lần thử sai lệch có kiểm soát tạo tín hiệu có thể hành động |
| Bổ sung chính sách cache | Có tài liệu ngắn và test tích hợp liên quan | Dữ liệu mới/phiên cũ đúng theo hợp đồng, không tăng lỗi đọc |
| Rollout theo cohort | Có thể giới hạn/bật lại an toàn | Khi thử nghiệm gặp lỗi, phạm vi ảnh hưởng được giữ trong giới hạn xác định |
| Cải tiến refinement | Story liên quan tiến độ có ví dụ đa thiết bị khi thích hợp | Giảm câu hỏi muộn/làm lại vì thiếu quy tắc, không tăng thời gian chờ quá mức |

Không thể dùng “không thấy bug tương tự trong một tuần” làm bằng chứng chắc chắn rằng bug đã bị loại vĩnh viễn, nhất là khi số người dùng hoặc số lần đi qua luồng nhỏ. Cần ghi giới hạn của quan sát và tiếp tục theo dõi ở mức phù hợp.

## 16. Bảo vệ dữ liệu người dùng khi thu thập và phân tích lỗi

Việc theo dõi production có thể vô tình tạo ra một rủi ro mới: **thu thập quá nhiều thông tin cá nhân để debug**. Với nền tảng học, dữ liệu có thể liên quan danh tính, tiến độ học, kết quả kiểm tra, quyền truy cập và thông tin thanh toán.

### Nguyên tắc triển khai

- **Tối thiểu hóa dữ liệu:** chỉ thu thông tin cần để xác định và xử lý lỗi.
- **Ẩn hoặc thay thế định danh:** dùng correlation ID không lộ danh tính, quản lý ánh xạ theo quyền phù hợp nếu thật sự cần.
- **Kiểm soát quyền xem log/traces:** không mở dữ liệu cho tất cả thành viên chỉ vì muốn xử lý nhanh.
- **Không log bí mật:** mật khẩu, token, cookie phiên, thông tin thanh toán nhạy cảm hoặc nội dung cá nhân không nên vào telemetry.
- **Dữ liệu test an toàn:** tái hiện bug bằng fixture giả lập, dữ liệu đã được xử lý hợp lệ; không sao chép nguyên dữ liệu học viên thật sang máy cá nhân.
- **Giới hạn lưu giữ:** áp dụng chính sách retention và xóa dữ liệu phù hợp với quy định/nhu cầu vận hành.
- **Truyền thông thận trọng:** báo tác động đã xác minh mà không tiết lộ hồ sơ cá nhân của người bị ảnh hưởng.

Một sự cố bảo mật hoặc lộ dữ liệu cần **quy trình xử lý chuyên biệt**, không chỉ một ticket bug bình thường. Các biện pháp phòng ngừa cũng cần được xem xét với người có chuyên môn và thẩm quyền liên quan.

## 17. Những phản mẫu làm phản hồi chất lượng mất giá trị

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Chỉ đếm số bug sau release** | Không thấy mức nghiêm trọng, số người bị ảnh hưởng hoặc lỗi bị bỏ sót | Kết hợp severity, phạm vi tác động, thời gian phát hiện/khôi phục |
| **Trộn số báo cáo với số defect duy nhất** | Một lỗi có nhiều báo cáo tạo số liệu phóng đại | Khử trùng lặp, liên kết incident và report theo nguyên nhân |
| **So escape rate của các cửa sổ khác nhau** | Kết luận sai về xu hướng | Thống nhất cohort, thời gian, đơn vị đếm |
| **Phạt đội tìm được nhiều lỗi production** | Người làm giảm báo cáo hoặc giấu vấn đề | Dùng chỉ số để học và cải tiến hệ thống |
| **Cho rằng test xanh là không còn lỗi** | Bỏ sót dữ liệu/điều kiện thực tế ngoài bộ test | Kết hợp test đa tầng và feedback sau phát hành |
| **Đổ lỗi cho một cá nhân/QA** | Người tham gia giấu thông tin và ít báo near miss | Postmortem dựa trên bằng chứng, trách nhiệm cải tiến rõ |
| **Sửa triệu chứng nhưng không tìm lớp bảo vệ bị thiếu** | Lỗi tái xuất hiện ở module khác | Tách cơ chế tạo lỗi, điểm escape và yếu tố phát hiện muộn |
| **Action item: “test kỹ hơn”** | Không biết ai làm gì, không kiểm chứng hiệu quả | Nêu kiểm tra cụ thể, chủ sở hữu, điều kiện hoàn tất |
| **Đưa mọi lỗi vào một checklist khổng lồ** | Chất lượng trở thành thủ tục, chi phí tăng nhưng test ít giá trị | Chọn bất biến và rủi ro có thể tái sử dụng |
| **Cảnh báo mọi lỗi nhỏ** | Alert fatigue, bỏ qua sự cố nghiêm trọng | Cảnh báo theo tác động, ngưỡng có thể hành động |
| **HTTP 200 được xem là thành công nghiệp vụ** | Không phát hiện trả bài sai, tạo đăng ký trùng | Thêm kiểm tra bất biến và business metrics phù hợp |
| **Rollback mà không kiểm tra dữ liệu** | Code đã lùi nhưng tiến độ/đăng ký vẫn sai | Có chiến lược kiểm tra và phục hồi dữ liệu |
| **Đóng incident khi hết cảnh báo** | Chưa chứng minh người dùng đã phục hồi | Kiểm tra hành trình, dữ liệu và phạm vi ảnh hưởng |
| **Luôn hotfix mọi lỗi ngay** | Tăng thay đổi vội, rủi ro lỗi mới | Triage theo tác động, ưu tiên hợp lý, bảo vệ kiểm thử bắt buộc |
| **Chỉ tập trung vào bug mà quên outcome** | Chất lượng kỹ thuật cải thiện nhưng sản phẩm vẫn khó dùng | Kết hợp phản hồi người dùng và Product Goal |
| **Thu dữ liệu nhạy cảm để tiện debug** | Tạo thêm rủi ro quyền riêng tư | Telemetry tối thiểu, dữ liệu thử an toàn, kiểm soát truy cập |
| **Không kiểm tra hành động phòng ngừa** | Báo cáo có rất nhiều việc “đã làm” nhưng vấn đề không giảm | Đặt giả thuyết và mốc đo hiệu quả sau thay đổi |

## 18. Bài thực hành: điều tra và phòng ngừa lỗi ghi danh trùng

### 18.1. Đề bài

Một nền tảng học cung cấp luồng ghi danh khóa miễn phí. Sau release, bộ phận hỗ trợ thấy một số học viên có **hai đăng ký hiệu lực** cho cùng khóa. Hai lần gửi yêu cầu có thể xảy ra rất gần nhau vì người học nhấn nút lần nữa khi mạng chậm.

Thông tin nhóm có:

1. Unit test của service xử lý “nếu đã ghi danh thì không ghi lại” đều xanh.
2. Kiểm thử chấp nhận chỉ gồm một lần gửi yêu cầu thành công.
3. Database chưa có ràng buộc đảm bảo duy nhất theo **học viên – khóa – trạng thái hiệu lực**.
4. Người dùng có thể gửi hai request đồng thời từ hai thiết bị.
5. Dashboard chỉ theo dõi HTTP 500, không theo dõi đăng ký trùng.
6. Trong một tuần, hỗ trợ nhận 18 báo cáo; sau khi đối chiếu phát hiện 12 học viên bị ảnh hưởng bởi cùng một cơ chế lỗi.
7. Nhóm chưa xác định liệu có dữ liệu sai từ những tuần trước hay không.

### 18.2. Câu hỏi

1. Đây là defect, escaped defect, incident hay feedback chưa xác minh? Điều gì cần xác nhận?
2. Số **18 báo cáo** có được tính là **18 defect** không? Vì sao?
3. Cần đánh giá tác động và xử lý khẩn đến mức nào? Có cần kiểm tra quyền học hoặc dữ liệu bị sai không?
4. Hãy mô tả **bốn bước** giảm tác động và khôi phục mà không làm mất dữ liệu hợp lệ.
5. Vì sao unit test “đã tồn tại thì không thêm” vẫn có thể xanh khi hai request đồng thời tạo trùng?
6. Đề xuất một kiểm thử hồi quy ở cấp **integration/database** cho concurrency.
7. Đề xuất ít nhất **ba biện pháp phòng ngừa** ở những lớp khác nhau.
8. Nêu **hai metric**, một guardrail và cách kiểm chứng phòng ngừa có tác dụng.
9. Viết một user story/bug PBI ngắn cùng acceptance criteria.
10. Giải thích phản hồi này nên đi vào **Sprint Review, Retrospective và Product Backlog** như thế nào.

### 18.3. Hướng giải tham khảo

**Phân loại:** nếu hệ thống đã phát hành và quy tắc “không có hai đăng ký hiệu lực cho cùng học viên và khóa” là yêu cầu đã xác nhận, hành vi này là **escaped defect**. Nó có thể gây incident nếu mức ảnh hưởng hoặc rủi ro vận hành đủ lớn theo chính sách. Cần điều tra xem có quyền học bị cấp sai, báo cáo học phí/khóa bị tính sai hay dữ liệu cần phục hồi không.

**Số lượng:** 18 báo cáo không đồng nghĩa 18 defect. Với giả định đã xác nhận cùng cơ chế tạo trùng, có thể ghi **một defect nguyên nhân**, **12 học viên ảnh hưởng đã xác nhận**, **18 báo cáo**. Cần tiếp tục xem liệu có thêm cơ chế lỗi khác hay người dùng chưa được phát hiện.

**Giảm tác động:** tạm thời giới hạn đường xử lý gây trùng nếu có phương án an toàn; đánh giá dữ liệu bị ảnh hưởng; ngăn tạo thêm đăng ký sai bằng giải pháp phù hợp; khôi phục/tổ chức sửa dữ liệu có kiểm tra quyền và lưu dấu vết cần thiết. **Không xóa bừa các hàng trùng** vì chúng có thể liên kết tới tiến độ, giao dịch hoặc lịch sử quyền.

**Nguyên nhân khả dĩ:** hai transaction cùng thấy “chưa có đăng ký” rồi cùng insert. Việc unit test mô phỏng tuần tự không bảo vệ tính nguyên tử của thao tác tại database.

**Kiểm thử phòng ngừa:** dùng môi trường tích hợp với database phù hợp, gửi hai yêu cầu đồng thời cho cùng học viên/khóa, sau khi hoàn tất xác minh **chỉ một đăng ký hiệu lực**, quyền học nhất quán và cả hai phản hồi phù hợp hợp đồng. Kiểm tra thêm gửi lặp tuần tự và tình huống retry khi phản hồi mạng thất lạc.

**Biện pháp nhiều lớp:**

- Làm rõ acceptance criteria cho retry và concurrency.
- Thiết kế cơ chế **unique constraint/transaction/idempotency** theo mô hình dữ liệu phù hợp; không chỉ dựa vào bước đọc rồi ghi.
- Bổ sung integration test trong CI cho bất biến chống trùng.
- Theo dõi số trường hợp phát hiện đăng ký trùng và lỗi quy tắc quyền như **guardrail vận hành**.
- Áp dụng rollout có kiểm soát cho thay đổi rủi ro cao.

### 18.4. Ví dụ acceptance criteria bằng Gherkin

~~~gherkin
Feature: Không tạo đăng ký hiệu lực trùng

  Scenario: Gửi yêu cầu ghi danh lần đầu
    Given học viên đã đăng nhập và đủ điều kiện
    And khóa miễn phí đang mở và không cần duyệt
    And chưa có đăng ký hiệu lực cho học viên và khóa
    When học viên xác nhận ghi danh
    Then hệ thống có đúng một đăng ký hiệu lực
    And học viên nhận quyền học theo chính sách

  Scenario: Gửi hai yêu cầu đồng thời
    Given học viên đã đăng nhập và đủ điều kiện
    And khóa miễn phí đang mở và không cần duyệt
    And chưa có đăng ký hiệu lực cho học viên và khóa
    When hai yêu cầu ghi danh cùng học viên và khóa được gửi đồng thời
    Then hệ thống có đúng một đăng ký hiệu lực sau khi xử lý
    And các phản hồi nhất quán với hợp đồng API
    And không cấp quyền học trùng hoặc trái phép

  Scenario: Gửi lại khi đã có đăng ký hiệu lực
    Given học viên đã có đăng ký hiệu lực cho khóa
    When học viên gửi lại yêu cầu ghi danh
    Then hệ thống không tạo thêm đăng ký hiệu lực
    And trả về trạng thái hiện có phù hợp
~~~

### 18.5. Bằng chứng theo dõi sau cải tiến

| Điều muốn biết | Tín hiệu và cách kiểm chứng |
| --- | --- |
| Defect đã được sửa đúng? | Integration test concurrency và retry chạy đạt, có kiểm tra bất biến ở database |
| Lỗi còn xảy ra trong production? | Theo dõi đăng ký hiệu lực trùng được xác nhận trong cửa sổ và tập người dùng xác định |
| Sự cố có dễ phát hiện hơn? | Cảnh báo khi bất biến bị vi phạm trong phép thử kiểm soát hoặc tín hiệu vận hành thực |
| Người dùng có được phục vụ an toàn? | Không cấp quyền sai; không mất tiến độ hoặc dữ liệu đăng ký hợp lệ |
| Cách làm đã cải thiện? | Story tương tự có ví dụ retry/concurrency và test tích hợp theo rủi ro, không chỉ tăng số test |

**Trong Scrum:** Product Owner cân nhắc sửa lỗi và phòng ngừa trong Product Backlog; Scrum Team thông tin tác động tới giá trị tại Sprint Review; Developers dùng Retrospective để cải thiện test, CI và cách phối hợp. Nếu vấn đề đang gây mất dữ liệu hoặc vi phạm quyền, xử lý sự cố ngay **không chờ sự kiện Scrum định kỳ**.

## 19. Checklist theo dõi lỗi lọt và sử dụng phản hồi để phòng ngừa

- [ ] Đã thống nhất **môi trường, phiên bản, cửa sổ và đơn vị đếm** để gọi một defect là escaped?
- [ ] Đã phân biệt **bug, incident, customer report, usability issue và feature request**?
- [ ] Báo cáo trùng được liên kết thay vì đếm thành nhiều defect khác nhau?
- [ ] Có cách phát hiện từ **người dùng, telemetry kỹ thuật và business metrics**?
- [ ] Log/trace đủ hỗ trợ điều tra nhưng **không lộ dữ liệu cá nhân hoặc token**?
- [ ] Những vấn đề mất dữ liệu, sai quyền và gián đoạn nghiêm trọng được **ứng phó ngay** theo quy trình thích hợp?
- [ ] Severity, priority và phạm vi ảnh hưởng được đánh giá bằng **tác động**, không chỉ số lượt báo?
- [ ] Đã xác định khi nào cần containment, rollback, feature flag hoặc khôi phục dữ liệu?
- [ ] Sau khôi phục có xác minh **hành trình người dùng, quyền và dữ liệu** chứ không chỉ HTTP 200?
- [ ] Phép đo escape rate có **tử số, mẫu số, cohort và cửa sổ rõ ràng**?
- [ ] Có xem thêm **severity, affected users, thời gian phát hiện/khôi phục và outcome**?
- [ ] MTTD/MTTR được định nghĩa mốc thời gian và không so sánh số liệu không tương đương?
- [ ] Postmortem tập trung **bằng chứng và hệ thống**, không chỉ tìm người có lỗi?
- [ ] Đã phân biệt **cơ chế tạo defect** và **vì sao các lớp phòng vệ không phát hiện sớm**?
- [ ] Biện pháp phòng ngừa gắn với **quy tắc nghiệp vụ, test, thiết kế, CI, DoD hoặc monitoring** cụ thể?
- [ ] Mỗi action item có người phụ trách, điều kiện hoàn tất và **mốc kiểm tra hiệu quả**?
- [ ] Các bug không khẩn và công việc phòng ngừa được cân nhắc minh bạch trong **Product Backlog**?
- [ ] Scrum, Kanban, XP và Lean được sử dụng để cải thiện phản hồi và giảm làm lại, không để tăng áp lực xếp hạng cá nhân?
- [ ] Khi kỹ thuật đã sửa xong, nhóm vẫn quan sát **người dùng có đạt giá trị và guardrail có an toàn**?
- [ ] Bài học được chia sẻ phù hợp cho các nhóm có cùng loại rủi ro, thay vì chỉ nằm trong biên bản sự cố?

**Ghi nhớ:** Lỗi lọt ra thực tế là tín hiệu quan trọng về **khoảng cách giữa giả định, kiểm thử, môi trường tích hợp và hành vi người dùng thật**. Chất lượng liên tục không dừng ở việc sửa một bug hay giảm một tỷ lệ. Nhóm cần **phát hiện sớm, giảm thiệt hại, xác minh hành vi, hiểu cơ chế gây lỗi và bổ sung lớp phòng ngừa có thể kiểm chứng**. Khi phản hồi production quay về user story, Product Backlog, DoD, TDD/ATDD, CI, Scrum và đo lường dòng công việc, Agile mới có thể giao Increment tăng dần mà vẫn học hỏi và bảo vệ giá trị sản phẩm lâu dài.
