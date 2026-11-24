# Đưa bảo mật, hiệu năng, khả năng truy cập và vận hành vào công việc

## 1. Một tính năng “chạy được” vẫn có thể chưa đủ chất lượng

Một Scrum Team phát triển nền tảng học trực tuyến vừa hoàn tất chức năng **đăng ký buổi hướng dẫn**. Trên môi trường thử, học viên chọn buổi học, nhấn “Đăng ký” và thấy thông báo thành công. Các tiêu chí chức năng thông thường đã được kiểm tra; nhóm dự định phát hành.

Tuy nhiên, bốn vấn đề có thể xuất hiện khi người dùng thật bắt đầu sử dụng:

- **Bảo mật:** học viên thay mã đăng ký trong URL và xem được thông tin của người khác.
- **Hiệu năng:** vào giờ mở đăng ký, thời gian phản hồi tăng mạnh, người dùng nhấn nút nhiều lần và gửi yêu cầu trùng.
- **Khả năng truy cập (accessibility):** người dùng chỉ dùng bàn phím không thể đến nút xác nhận, còn thông báo lỗi không được công cụ đọc màn hình thông báo.
- **Khả năng vận hành (operability):** đội trực thấy máy chủ còn hoạt động nhưng không biết số đăng ký được ghi nhận sai, không có cảnh báo hay hướng dẫn giảm tác động.

Chúng không phải bốn “tính năng phụ” có thể tùy tiện bổ sung khi dự án rảnh rỗi. Chúng liên quan trực tiếp đến **khả năng người dùng hoàn thành công việc an toàn, hiệu quả và đáng tin cậy**.

**Chất lượng liên tục (continuous quality)** là cách đưa các kỳ vọng và hoạt động bảo đảm chất lượng vào **toàn bộ dòng phát triển sản phẩm**, từ tìm hiểu nhu cầu, sắp backlog và thiết kế cho đến lập trình, kiểm thử, tích hợp, phát hành, vận hành và cải tiến. Chất lượng không được gán cho riêng một công đoạn “QA cuối Sprint”.

Bài học thuộc chương **Chất lượng liên tục** của module **AGILE_DEVELOPMENT**. Module nhấn mạnh giá trị và nguyên tắc Agile, phản hồi sớm, giao sản phẩm tăng dần, cải tiến liên tục và thực hành user story, backlog, Scrum, Kanban, XP cùng đo lường dòng công việc. Ở đây, các thực hành đó được liên kết với bốn thuộc tính chất lượng **bảo mật, hiệu năng, khả năng truy cập và vận hành**, để mỗi Increment nhỏ vẫn có thể được sử dụng một cách đáng tin.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích vì sao các thuộc tính chất lượng là yêu cầu xuyên suốt, không phải “phần việc sau khi có tính năng”.
2. Đưa rủi ro về **security, performance, accessibility và operability** vào khám phá sản phẩm, refinement, Sprint Planning, Kanban và Definition of Done.
3. Viết tiêu chí chấp nhận và xây chiến lược kiểm chứng có bằng chứng cho từng thuộc tính.
4. Phân biệt kiểm thử sớm (**shift left**) với quan sát khi vận hành (**shift right**) và hiểu vì sao cần cả hai.
5. Thiết kế luồng phản hồi từ CI/CD, kiểm thử rủi ro, telemetry và sự cố production về Product Backlog.
6. Chọn cách đo và các cải tiến nhỏ mà không đánh đổi chất lượng lấy số ticket hoặc tốc độ triển khai.

## 2. Chất lượng không chỉ là “không có bug”

Một hệ thống có thể cho kết quả đúng với một bộ dữ liệu thử nhưng vẫn khó sử dụng, quá chậm, không an toàn hoặc không thể phục hồi khi xảy ra lỗi. Vì vậy, nên phân biệt:

| Khía cạnh | Câu hỏi | Ví dụ đăng ký buổi học |
|---|---|---|
| **Chức năng đúng** | Phần mềm có làm đúng điều người dùng cần? | Đăng ký thành công khi buổi còn chỗ và học viên hợp lệ. |
| **Bảo mật** | Thông tin và hành động có được bảo vệ trước truy cập, thay đổi hoặc lạm dụng trái phép? | Không đọc/hủy đăng ký thuộc tài khoản khác. |
| **Hiệu năng** | Hệ thống có đáp ứng tốc độ và tải cần thiết trong bối cảnh thực? | Nhiều học viên đăng ký đồng thời mà không quá chậm hoặc mất dữ liệu. |
| **Khả năng truy cập** | Người có khả năng, thiết bị và cách tương tác khác nhau có thực hiện được tác vụ? | Dùng bàn phím hoặc trình đọc màn hình vẫn có thể đăng ký. |
| **Khả năng vận hành** | Có thể quan sát, triển khai, hỗ trợ, khôi phục và duy trì dịch vụ? | Nhận biết lỗi ghi đăng ký, tìm nguyên nhân và giảm tác động. |
| **Giá trị sản phẩm** | Kết quả có thực sự hữu ích với người dùng/tổ chức? | Người học đặt được buổi hướng dẫn thuận tiện hơn, giảm nhu cầu hỗ trợ thủ công. |

Các yếu tố này liên quan nhưng **không thay thế nhau**. Một API phản hồi 50 mili giây không có nghĩa nó bảo mật; một giao diện đạt kiểm thử tự động không bảo đảm người dùng hiểu trạng thái; dashboard đẹp không chứng minh dữ liệu được lưu đúng.

### 2.1. “Non-functional requirements” không có nghĩa không cần kiểm chứng

Bảo mật, hiệu năng, khả năng truy cập và vận hành đôi khi được xếp dưới tên **yêu cầu phi chức năng (non-functional requirements — NFR)** hoặc **quality attributes**. Tên gọi đó có thể gây hiểu nhầm rằng chúng chỉ là đặc điểm tổng quát, không cần tiêu chí cụ thể.

Một yêu cầu như “hệ thống phải nhanh và thân thiện” quá mơ hồ để xác nhận hoàn thành. Hãy thay bằng mục tiêu và bằng chứng phù hợp, chẳng hạn:

- “Ở tải kiểm thử đại diện đã thống nhất, ít nhất 95% phản hồi của API xem buổi trống hoàn thành trong ngưỡng quy định.”
- “Học viên không thể lấy hoặc hủy bản ghi đăng ký của tài khoản khác bằng cách sửa tham số request.”
- “Toàn bộ luồng đăng ký chính có thể thao tác và nhận thông báo kết quả bằng bàn phím.”
- “Khi lỗi ghi đăng ký tăng, người trực nhận tín hiệu có thể hành động mà không cần đợi người dùng khiếu nại.”

Những câu trên vẫn cần **định nghĩa môi trường, tập người dùng, phạm vi đo, ngưỡng và cách chứng minh**. Một tiêu chí chỉ hữu ích khi những người liên quan hiểu cùng một nghĩa.

### 2.2. Chất lượng là điều kiện tạo giá trị tăng dần

Agile khuyến khích giao phần giá trị nhỏ và lấy phản hồi sớm. Nhưng **nhỏ về phạm vi không đồng nghĩa thấp về chất lượng**.

Ví dụ, nhóm có thể chỉ hỗ trợ đăng ký một loại buổi học trong Increment đầu tiên, chưa có danh sách chờ hoặc gợi ý cá nhân. Tuy nhiên, phần đăng ký đã mở phải bảo vệ dữ liệu, không xác nhận vượt số chỗ, có giao diện sử dụng được và có cơ chế vận hành tương xứng rủi ro.

**Giảm phạm vi là một chiến lược thích ứng. Hạ các kiểm soát thiết yếu để báo Done không phải chiến lược Agile an toàn.**

## 3. Tư duy “built-in quality”: chất lượng được xây vào công việc

**Built-in quality** nghĩa là việc kiểm soát chất lượng được đưa vào cách thiết kế, xây dựng và hoàn tất sản phẩm, không chỉ phụ thuộc vào một đội kiểm tra ở cuối.

Một vòng tạo giá trị có thể nhìn như sau:

~~~mermaid
flowchart TD
    A["Product Goal và vấn đề người dùng"] --> B["Làm rõ ví dụ, quality attributes và rủi ro"]
    B --> C["Chia lát giá trị, chọn tiêu chí kiểm chứng"]
    C --> D["Thiết kế và phát triển với phản hồi sớm"]
    D --> E["Kiểm tra chức năng, bảo mật, hiệu năng, truy cập, vận hành"]
    E --> F{"Đạt Definition of Done áp dụng?"}
    F -->|Chưa| G["Minh bạch thiếu sót và cải tiến"]
    G --> D
    F -->|Đạt| H["Increment dùng được; phát hành theo chính sách"]
    H --> I["Quan sát hành vi, SLI, sự cố và phản hồi người dùng"]
    I --> J["Điều chỉnh backlog, DoD và cách làm"]
    J --> B
~~~

Sơ đồ thể hiện những điểm kiểm tra quan trọng, **không phải quy trình bàn giao cứng**. Trao đổi nghiệp vụ, thử nguyên mẫu, lập trình, kiểm thử và tích hợp có thể diễn ra đồng thời hoặc lặp lại nhiều lần.

### 3.1. Shift left: phát hiện vấn đề từ sớm

**Shift left** là đưa các hoạt động phát hiện và ngăn ngừa lỗi về những điểm sớm hơn trong dòng phát triển.

Ví dụ:

- Đặt câu hỏi về quyền truy cập khi làm rõ user story, trước khi viết API.
- Phác thảo hành trình dùng bàn phím ngay lúc thiết kế giao diện.
- Ước lượng tải dự kiến và kiểm tra điểm nghẽn trước sự kiện mở đăng ký lớn.
- Thống nhất tín hiệu giám sát, cách xử lý lỗi và phương án an toàn trước khi triển khai.

Shift left **không có nghĩa mọi kiểm tra đều phải xong trong buổi refinement**, cũng không thay thế kiểm tra hệ thống thực.

### 3.2. Shift right: học trong môi trường vận hành thật

**Shift right** là tiếp tục quan sát và xác minh những thuộc tính quan trọng sau khi phần mềm đã đến môi trường sử dụng phù hợp:

- Độ trễ thật có khác điều kiện kiểm thử không?
- Người dùng hỗ trợ công nghệ tiếp cận có gặp trở ngại chưa dự kiến không?
- Có mẫu truy cập sai quyền hoặc lạm dụng mới không?
- Cảnh báo có giúp người trực phát hiện lỗi trước khi hậu quả lan rộng không?

Quan sát production cần tuân thủ bảo mật, quyền riêng tư và quy trình an toàn. **Không lấy người dùng thật làm đối tượng thử rủi ro chưa được kiểm soát chỉ vì muốn có phản hồi thực**.

### 3.3. Trách nhiệm chất lượng là liên chức năng

Những người hiểu nghiệp vụ, thiết kế trải nghiệm, kỹ thuật, kiểm thử, bảo mật, nền tảng và vận hành cần phối hợp ở những điểm phù hợp. Không phải mọi người phải có cùng chuyên môn; nhưng **không ai nên mặc định rằng vấn đề chất lượng mình nhận ra thuộc trách nhiệm duy nhất của “đội sau”**.

## 4. Đưa bốn thuộc tính vào vòng đời phát triển

| Thời điểm | Bảo mật | Hiệu năng | Truy cập | Vận hành |
|---|---|---|---|---|
| **Khám phá vấn đề** | Dữ liệu nào cần bảo vệ, ai có quyền? | Tác vụ nào có giới hạn thời gian quan trọng? | Ai có thể bị loại khỏi hành trình hiện tại? | Kết quả nào cần theo dõi khi đưa vào dùng? |
| **Refinement** | Abuse cases, dữ liệu nhạy cảm, ranh giới quyền. | Tải, số người đồng thời, mục tiêu độ trễ. | Bàn phím, nhãn, lỗi, tương phản, công cụ hỗ trợ. | Tín hiệu, cảnh báo, phương án lỗi và trách nhiệm. |
| **Thiết kế** | Phân quyền, xử lý dữ liệu, giảm bề mặt tấn công. | Kiến trúc, cache, giới hạn tài nguyên, đồng thời. | Luồng tương tác, thứ tự focus, nội dung dễ hiểu. | Tính quan sát, cấu hình, khả năng khôi phục. |
| **Phát triển** | Kiểm tra quyền ở nơi đáng tin, secrets an toàn. | Truy vấn, tài nguyên, xử lý tải. | HTML ngữ nghĩa, thao tác và thông báo trạng thái. | Log/metric/trace đúng mục đích, xử lý lỗi. |
| **Kiểm chứng** | Kiểm thử lạm dụng, phân quyền, phụ thuộc. | Load/stress/spike/soak test phù hợp. | Kiểm thử tự động, thủ công với bàn phím và công nghệ hỗ trợ. | Diễn tập triển khai, khôi phục, cảnh báo và runbook. |
| **Phát hành** | Chính sách quyền, kiểm soát thay đổi, phát hiện rủi ro. | Mở dần, theo dõi độ trễ và năng lực. | Giữ hành vi tiếp cận được trong phiên bản thực. | Người trực, rollback/kill switch, thông tin phiên bản. |
| **Vận hành & học hỏi** | Phát hiện lạm dụng, xử lý lỗ hổng. | SLI, xu hướng tải, dung lượng. | Phản hồi tiếp cận, lỗi mới trong hành trình. | Incident response, postmortem, phòng ngừa. |

Bảng là **bản đồ câu hỏi**, không có nghĩa mỗi hạng mục phải trải qua hàng chục thủ tục giống nhau. Nhóm chọn độ sâu thực hành dựa trên rủi ro, nhưng phải giữ các tiêu chuẩn bắt buộc.

## 5. Từ yêu cầu mơ hồ đến tiêu chí chất lượng kiểm chứng được

Khi người dùng nói “Trang đăng ký phải an toàn, nhanh và dễ dùng”, nhóm cần chuyển kỳ vọng thành **ví dụ và điều kiện có thể kiểm chứng**.

### 5.1. Story chức năng và yêu cầu xuyên suốt

User story minh họa:

> Là một học viên đã đăng nhập, tôi muốn đăng ký một buổi hướng dẫn còn chỗ để chắc chắn mình có thể tham gia mà không cần liên hệ bộ phận hỗ trợ.

Các tiêu chí chức năng:

1. Chỉ xác nhận khi buổi còn nhận đăng ký và học viên có quyền hợp lệ.
2. Khi không còn chỗ, hệ thống thông báo kết quả đúng thay vì báo thành công giả.
3. Một thao tác gửi lặp không tự tạo thêm hai đăng ký hợp lệ.
4. Học viên thấy thông tin buổi và trạng thái đăng ký cuối cùng.

Những tiêu chí bổ sung theo chất lượng:

| Thuộc tính | Tiêu chí minh họa | Phương pháp kiểm chứng |
|---|---|---|
| **Bảo mật** | Không thể xem/hủy đăng ký của tài khoản khác bằng sửa ID hoặc request. | Kiểm thử phân quyền theo vai trò, chủ thể và đối tượng. |
| **Hiệu năng** | Với tải và môi trường đã định nghĩa, 95% yêu cầu xem giờ trống hoàn thành trong ngưỡng mục tiêu. | Kiểm thử tải, theo dõi p95 và lỗi; so sánh với baseline. |
| **Truy cập** | Có thể thực hiện luồng đăng ký chính hoàn toàn bằng bàn phím, thông báo kết quả có thể nhận biết bằng công nghệ hỗ trợ. | Kiểm tra bàn phím, focus, nhãn và screen reader trong phạm vi mục tiêu. |
| **Vận hành** | Có tín hiệu phân biệt lỗi ghi đăng ký với yêu cầu bị từ chối hợp lệ và có người nhận cảnh báo. | Tạo kịch bản lỗi có kiểm soát, kiểm tra metric/cảnh báo và runbook. |

Các con số và phạm vi cần được quyết định theo bối cảnh thật. **Không nên sao chép một ngưỡng p95 hay một danh sách kiểm thử từ sản phẩm khác rồi coi là tiêu chuẩn mặc định.**

### 5.2. Acceptance criteria khác Definition of Done

- **Acceptance criteria** làm rõ điều kiện hành vi và kỳ vọng của **một hạng mục cụ thể**.
- **Definition of Done (DoD)** mô tả trạng thái chất lượng của **Increment** trong Scrum và là commitment của artifact đó.
- **Release criteria** hỗ trợ quyết định **mở Increment cho ai và khi nào**, với những điều kiện điều phối hoặc phát hành bổ sung.
- **SLO** biểu thị mục tiêu chất lượng của **dịch vụ trong một khoảng thời gian**, không tự thay thế DoD hoặc acceptance criteria.

Ví dụ, yêu cầu “học viên chỉ được hủy đăng ký của mình” là tiêu chí riêng. Yêu cầu toàn bộ thay đổi liên quan dữ liệu cá nhân phải được kiểm tra phân quyền là một chuẩn chất lượng có thể nằm trong DoD. Mục tiêu 99,9% yêu cầu hợp lệ được xử lý trong ngưỡng là SLO minh họa của dịch vụ.

### 5.3. Không dùng nhãn “phi chức năng” để trì hoãn

Một PBI có thể được chia thành các bước nhỏ, nhưng mỗi phần được gọi là Done phải đạt DoD áp dụng. Không nên đánh dấu Done rồi tạo một ticket “thêm bảo mật/khả năng truy cập sau” khi phần chưa đáp ứng điều kiện bắt buộc để được sử dụng.

Nếu phạm vi quá lớn, có thể **giảm số trường hợp hoặc nhóm người dùng được hỗ trợ** theo cách an toàn, không loại bỏ các kiểm soát thiết yếu của phạm vi còn lại.

## 6. Ưu tiên theo rủi ro thay vì kiểm tra mọi thứ giống nhau

Chất lượng liên tục không có nghĩa cứ thêm mọi công cụ quét, mọi kiểu kiểm thử và mọi buổi phê duyệt vào mỗi ticket. Cần cân nhắc **khả năng gây hại, phạm vi ảnh hưởng, độ bất định và khả năng phát hiện/khôi phục**.

### 6.1. Một cách phân loại rủi ro đơn giản

Khi refinement, với một thay đổi hãy hỏi:

1. **Nếu sai, hậu quả là gì?** Bất tiện nhỏ, mất khả năng dùng, thiệt hại tiền, lộ dữ liệu hay an toàn?
2. **Ai và bao nhiêu người có thể bị ảnh hưởng?** Nhóm thử nhỏ, toàn bộ người dùng, một nhóm dễ bị tổn thương?
3. **Điều gì chưa biết?** Phụ thuộc đối tác, tải, quyền, hành vi trình duyệt hoặc công nghệ hỗ trợ?
4. **Lỗi có dễ nhận ra và khôi phục không?** Có cảnh báo, bản ghi, rollback, đối soát hoặc phương án an toàn?
5. **Có yêu cầu bắt buộc nào không?** Tiêu chuẩn tổ chức, hợp đồng, pháp luật hoặc quy định ngành.

Có thể dùng bảng **tác động × độ bất định** để thảo luận ưu tiên kiểm chứng; không nên coi điểm số do nhóm tự đặt là phép tính xác suất chính xác.

| Tình huống | Tác động nếu sai | Hướng kiểm chứng |
|---|---|---|
| Đổi câu chữ phụ đề hướng dẫn | Có thể ảnh hưởng hiểu nội dung và khả năng tiếp cận. | Kiểm tra tính rõ ràng, ngữ nghĩa và những yêu cầu tiếp cận liên quan. |
| Đổi API đọc lịch cá nhân | Có nguy cơ lộ dữ liệu. | Kiểm tra phân quyền, dữ liệu trả về và trường hợp lạm dụng. |
| Tối ưu truy vấn xem buổi trống | Có thể ảnh hưởng tốc độ và đúng dữ liệu. | Đo baseline, thử tải phù hợp và kiểm thử hồi quy. |
| Thay cơ chế ghi đăng ký | Có thể tạo đăng ký trùng hoặc mất chỗ. | Kiểm thử đồng thời, tính nhất quán dữ liệu, lỗi/khôi phục. |
| Thay cấu hình cảnh báo production | Có thể khiến lỗi nghiêm trọng không được phát hiện. | Thử tín hiệu và đường thông báo trong điều kiện an toàn. |

### 6.2. Dành thời gian cho công việc khám phá

Khi chưa biết một kỹ thuật có đạt tải hoặc khả năng truy cập cần thiết không, một **spike/nghiên cứu có giới hạn** có thể tạo giá trị bằng việc trả lời câu hỏi cụ thể.

Ví dụ: “Trong hai ngày làm việc, dựng thử luồng đăng ký đồng thời với dữ liệu đại diện để xác định nút thắt và đề xuất phương án bảo đảm số chỗ.” Đầu ra là bằng chứng, giới hạn và quyết định tiếp theo; không được mặc định một prototype chưa kiểm chứng là Increment production.

## 7. Bảo mật: bắt đầu từ tài sản, quyền và kịch bản lạm dụng

**Security** không chỉ là quét mã tự động trước release. Cần hiểu **dữ liệu/hành động nào phải được bảo vệ, ai có quyền và những cách hệ thống có thể bị sử dụng sai**.

### 7.1. Mô hình hóa đe dọa ở mức vừa đủ

**Threat modeling** là hoạt động suy nghĩ có hệ thống về tài sản, thành phần, luồng dữ liệu, ranh giới tin cậy và những mối đe dọa có ý nghĩa.

Với luồng đăng ký buổi học:

- **Tài sản:** danh tính học viên, trạng thái đăng ký, thông tin liên hệ, quyền tham gia.
- **Chủ thể:** học viên, giảng viên, người vận hành, dịch vụ thông báo, người có ý định lạm dụng.
- **Ranh giới tin cậy:** trình duyệt ↔ API; API ↔ cơ sở dữ liệu; ứng dụng ↔ dịch vụ email/đối tác.
- **Hành động nhạy cảm:** xem đăng ký, tạo/hủy đăng ký, thay đổi quyền, tải danh sách người tham gia.
- **Hậu quả cần tránh:** đọc dữ liệu trái quyền, giả mạo yêu cầu, thay đổi trạng thái, lộ secrets, ghi log dữ liệu nhạy cảm.

Một buổi trao đổi ngắn có sơ đồ luồng dữ liệu và vài kịch bản lạm dụng cụ thể thường hữu ích hơn một checklist dài không liên quan.

### 7.2. Phân biệt xác thực và phân quyền

- **Authentication (xác thực):** người hoặc hệ thống đang yêu cầu là ai?
- **Authorization (phân quyền):** chủ thể đã xác thực có được phép làm hành động này trên đối tượng này không?

Việc học viên đã đăng nhập **không chứng minh** họ được xem mọi bản ghi có ID hợp lệ. Một API như:

~~~text
GET /api/registrations/347
DELETE /api/registrations/347
~~~

phải kiểm tra quyền truy cập đối với **bản ghi cụ thể**, không chỉ kiểm tra token tồn tại. Những kiểm tra quan trọng cần thực hiện **ở phía máy chủ hoặc nơi có thẩm quyền đáng tin**, không dựa duy nhất vào việc ẩn nút ở giao diện.

### 7.3. Kịch bản Given–When–Then cho phân quyền

~~~gherkin
Feature: Chỉ truy cập đăng ký được phép

  Scenario: Học viên xem đăng ký của mình
    Given học viên A đã xác thực
    And đăng ký 347 thuộc học viên A
    When học viên A yêu cầu xem đăng ký 347
    Then hệ thống chỉ trả dữ liệu được phép của đăng ký đó

  Scenario: Học viên cố truy cập đăng ký của người khác
    Given học viên B đã xác thực
    And đăng ký 347 không thuộc học viên B
    When học viên B yêu cầu xem hoặc hủy đăng ký 347
    Then hệ thống từ chối thao tác trái quyền
    And không tiết lộ dữ liệu của đăng ký đó
~~~

Ví dụ chỉ minh họa hành vi mong muốn; cần thiết kế thông báo lỗi, ghi nhận sự kiện và chính sách phân quyền theo sản phẩm.

### 7.4. Các nguyên tắc kỹ thuật quan trọng

| Chủ đề | Thực hành cần cân nhắc | Rủi ro nếu bỏ qua |
|---|---|---|
| **Quyền tối thiểu** | Chỉ cấp quyền cần thiết cho người, dịch vụ và pipeline. | Một tài khoản bị lạm dụng có phạm vi ảnh hưởng rộng. |
| **Kiểm tra đầu vào và xử lý đầu ra** | Kiểm tra dữ liệu theo ngữ cảnh, dùng cơ chế truy vấn tham số hóa, mã hóa đầu ra phù hợp. | Injection, lỗi dữ liệu hoặc nội dung độc hại. |
| **Quản lý secrets** | Lưu bí mật ở cơ chế chuyên dụng, kiểm soát quyền, không đưa vào mã/log. | Lộ token, mật khẩu hoặc khóa truy cập. |
| **Bảo vệ dữ liệu** | Thu thập tối thiểu, kiểm soát truy cập, lưu giữ và xóa theo chính sách. | Lộ thông tin cá nhân, sử dụng dữ liệu vượt mục đích. |
| **Quản lý thành phần phụ thuộc** | Biết phiên bản đang dùng, theo dõi lỗ hổng và cập nhật có kiểm chứng. | Lỗ hổng hoặc lỗi do thư viện/chuỗi cung ứng. |
| **Bảo vệ hành động nhạy cảm** | Xác định ranh giới quyền, giới hạn lạm dụng, kiểm tra yêu cầu lặp. | Giả mạo, tự động hóa trái phép hoặc sửa trạng thái không hợp lệ. |
| **Ghi nhận sự kiện an toàn** | Thu tín hiệu đủ điều tra mà không lộ dữ liệu nhạy cảm. | Không phát hiện hoặc không tái dựng được sự cố. |

**Quét tự động là một nguồn phản hồi, không phải giấy chứng nhận không còn lỗ hổng.** Các vấn đề nghiệp vụ như “người học hủy được đăng ký của người khác” thường cần kiểm tra phân quyền theo dữ liệu và luồng thật.

## 8. Security testing trong CI/CD: dùng đúng công cụ, hiểu giới hạn

Nhiều nhóm tích hợp kiểm tra bảo mật vào pipeline. Các tên thường gặp:

| Loại kiểm tra | Mục đích chính | Không nên kỳ vọng |
|---|---|---|
| **SAST** (Static Application Security Testing) | Phân tích mã hoặc các biểu diễn tĩnh để tìm mẫu rủi ro. | Không chứng minh quyền truy cập và cấu hình thực luôn đúng. |
| **SCA** (Software Composition Analysis) | Phát hiện thành phần phụ thuộc và các cảnh báo/rủi ro liên quan. | Không xác định chắc thư viện có khai thác được trong ngữ cảnh ứng dụng hay không. |
| **DAST** (Dynamic Application Security Testing) | Kiểm tra hành vi bảo mật của ứng dụng đang chạy trong phạm vi cho phép. | Không tự bao phủ mọi trạng thái, quyền hay đường nghiệp vụ. |
| **Secret scanning** | Tìm dấu hiệu bí mật bị đưa vào mã/cấu hình. | Không thay thế cơ chế quản lý và luân chuyển secrets. |
| **IaC/container scanning** | Tìm cấu hình và thành phần hạ tầng có nguy cơ. | Không chứng minh hệ thống vận hành an toàn dưới mọi điều kiện. |
| **Kiểm thử abuse case/phân quyền** | Thử các tình huống truy cập và thay đổi dữ liệu trái quyền. | Không thể bảo đảm mọi kiểu tấn công tương lai đều đã được mô phỏng. |
| **Đánh giá chuyên môn/penetration test khi cần** | Khám phá những rủi ro khó phát hiện tự động. | Không thay thế thiết kế an toàn và cải tiến liên tục. |

### 8.1. Không biến mọi cảnh báo thành cùng một mức khẩn

Một cảnh báo phụ thuộc cần được xem trong **bối cảnh phiên bản, cách sử dụng, khả năng khai thác, mức ảnh hưởng, mức phơi lộ và biện pháp giảm thiểu**. Ngược lại, lỗ hổng đang bị khai thác hoặc một lỗi lộ dữ liệu đang diễn ra có thể cần ứng phó ngay, không chờ Sprint sau.

Nên xác định rõ ai đánh giá cảnh báo, thời gian phản ứng theo mức rủi ro, cách ghi ngoại lệ có thẩm quyền và cách xác minh bản sửa.

### 8.2. Công cụ không thay thế con người hiểu thiết kế

Một API có thể vượt qua SAST nhưng vẫn cho phép người đã đăng nhập xem dữ liệu của người khác vì thiếu kiểm tra quyền trên từng đối tượng. Người nghiệp vụ, người phát triển, kiểm thử và chuyên gia bảo mật phải **nói rõ bất biến và kịch bản lạm dụng**, sau đó chọn phép kiểm chứng có ý nghĩa.

## 9. Hiệu năng: đo thời gian người dùng chờ, không chỉ CPU

**Performance** liên quan cách hệ thống phản hồi và sử dụng tài nguyên dưới một điều kiện tải cụ thể. Các mục tiêu có thể bao gồm:

- **Latency:** thời gian xử lý một yêu cầu hoặc hoàn thành một tác vụ.
- **Throughput:** số yêu cầu/giao dịch được xử lý trong khoảng thời gian.
- **Concurrency:** số thao tác hoặc người dùng hoạt động đồng thời theo định nghĩa.
- **Resource utilization:** CPU, RAM, kết nối, I/O, hàng đợi và tài nguyên liên quan.
- **Capacity/scalability:** khả năng đáp ứng khi tải tăng và cách chi phí thay đổi theo tải.
- **Reliability under load:** tỷ lệ lỗi, timeout và tính đúng đắn dữ liệu trong điều kiện tải.

Một hệ thống có CPU thấp vẫn có thể chậm do khóa dữ liệu, hàng đợi, kết nối tới đối tác hoặc truy vấn chờ I/O. **Chỉ số hạ tầng cần được liên kết với trải nghiệm người dùng và tính đúng của nghiệp vụ.**

### 9.1. Trung bình có thể che giấu trải nghiệm xấu

Giả sử một API có thời gian phản hồi trung bình 200 ms nhưng một số yêu cầu mất vài giây. Người dùng gặp các yêu cầu chậm vẫn có trải nghiệm tệ. Vì vậy, ngoài giá trị trung bình, nhóm thường xem:

- **p50 (median):** khoảng 50% quan sát không vượt quá mức này.
- **p95:** khoảng 95% quan sát không vượt quá mức này.
- **p99:** khoảng 99% quan sát không vượt quá mức này.

Cần nêu rõ **tập yêu cầu, cửa sổ đo, cách lấy dữ liệu và độ tin cậy của mẫu**. Percentile tính từ các tập dữ liệu khác nhau không tự so sánh được. Không nên dùng một p95 tổng hợp để che giấu một nhóm người dùng hoặc endpoint có trải nghiệm rất tệ.

### 9.2. Một mục tiêu hiệu năng phải có bối cảnh tải

Thay vì “API phản hồi dưới 500 ms”, viết theo hướng:

> Ví dụ minh họa: với dữ liệu tương đương phạm vi triển khai đã thống nhất, luồng xem buổi trống đáp ứng p95 tối đa 800 ms trong thử nghiệm 300 người dùng đồng thời hoạt động theo kịch bản đã định, với tỷ lệ lỗi không vượt ngưỡng chấp nhận; các phép đo được ghi kèm cấu hình và môi trường thử.

**Các số 800 ms và 300 người dùng chỉ là giả định phục vụ học tập**, không phải ngưỡng chuẩn cho nền tảng học. Nhóm cần xác định workload, số người thực sự phát yêu cầu, phân phối tác vụ, thời gian chờ giữa các thao tác, tốc độ tăng tải, dữ liệu và mục tiêu thực.

### 9.3. Tải đồng thời còn liên quan tính nhất quán

Hai yêu cầu đăng ký cùng đọc thấy còn một chỗ có thể đều cố ghi thành công nếu hệ thống không có cơ chế bảo đảm bất biến. Một bài kiểm thử đo thời gian phản hồi có thể cho kết quả nhanh nhưng **không chứng minh hệ thống đã bảo toàn số chỗ**.

Với thao tác ghi trạng thái, nên kiểm tra cả:

- Tỷ lệ thành công và từ chối hợp lệ.
- Không vượt quá sức chứa khi có cạnh tranh.
- Không tạo bản ghi trùng ngoài quy tắc khi client retry.
- Trạng thái không xác định sau timeout được xử lý an toàn.
- Thông báo cho người dùng khớp với kết quả đã ghi nhận.

## 10. Các loại kiểm thử hiệu năng và cách đọc kết quả

| Loại | Mục đích | Câu hỏi thực tế |
|---|---|---|
| **Baseline** | Thiết lập mức hiện tại với workload đã biết. | Thay đổi mới có làm chậm luồng cũ không? |
| **Load test** | Đánh giá trong tải dự kiến và kịch bản sử dụng đại diện. | Dịch vụ có đáp ứng mục tiêu latency và lỗi ở tải cần phục vụ? |
| **Stress test** | Đẩy vượt giới hạn để hiểu điểm suy giảm và khả năng phục hồi. | Khi quá tải, hệ thống từ chối/giảm chất lượng theo cách an toàn không? |
| **Spike test** | Thử tải tăng hoặc giảm đột ngột. | Khi mở đăng ký lúc 8 giờ, hàng đợi và kết nối có ổn định không? |
| **Soak/endurance test** | Duy trì tải một thời gian để quan sát vấn đề tích lũy. | Có rò rỉ tài nguyên, tích tụ hàng đợi hoặc suy giảm sau nhiều giờ không? |
| **Scalability/capacity test** | Xem phản ứng của hệ thống khi tăng tải hoặc tài nguyên. | Thêm instance có giúp, hay điểm nghẽn nằm ở cơ sở dữ liệu? |

Các phép thử có thể cần môi trường cô lập hoặc kiểm soát để **không gây tác động ngoài ý muốn** lên dịch vụ thật. Tải nhân tạo không được đẩy vào production nếu chưa được phép và chưa có kiểm soát an toàn.

### 10.1. Trước khi thử tải, cần biết điều gì?

1. **Workload:** người dùng làm gì, tần suất nào, đọc/ghi bao nhiêu?
2. **Dữ liệu:** kích thước, phân bố, trạng thái và phụ thuộc có đại diện cho kịch bản mong đợi không?
3. **Môi trường:** cấu hình ứng dụng, tài nguyên, cơ sở dữ liệu, mạng và đối tác giống hoặc khác production thế nào?
4. **Mục tiêu:** latency, error rate, throughput, tính đúng dữ liệu và mức sử dụng tài nguyên.
5. **Giới hạn an toàn:** môi trường thử có gây email/thanh toán thật, gửi dữ liệu nhạy cảm hoặc tác động tới người dùng không?
6. **Bằng chứng:** thu metric, log/trace, tài nguyên và kết quả nghiệp vụ ra sao?

Nếu môi trường thử khác production, kết quả cần **ghi giới hạn và tránh khẳng định quá mức**. Mục tiêu là giảm bất định, không dùng một bài kiểm thử bất kỳ để “chứng minh chịu mọi tải”.

### 10.2. Phát hiện nút thắt, không tối ưu tùy tiện

Ví dụ, response time tăng vì nhiều request chờ khóa cơ sở dữ liệu. Tăng số instance ứng dụng có thể làm nhiều request cạnh tranh hơn, khiến vấn đề tệ hơn. Nhóm cần xác định nút thắt từ dữ liệu, thử thay đổi nhỏ, đo lại và kiểm chứng không làm sai hành vi.

**Hiệu năng là thuộc tính hệ thống**, không phải chỉ là tốc độ của một hàm riêng.

## 11. Khả năng truy cập: để nhiều người có thể sử dụng sản phẩm

**Accessibility (a11y)** trong sản phẩm số là khả năng nội dung, giao diện và tương tác **có thể được cảm nhận, thao tác và hiểu** bởi những người có nhu cầu, khả năng hoặc công nghệ hỗ trợ khác nhau.

Vấn đề không chỉ giới hạn ở một nhóm người dùng cố định. Người dùng có thể sử dụng bàn phím thay vì chuột, dùng trình đọc màn hình, cần phóng to, có hạn chế thị lực hoặc thính lực, gặp khó khăn trong nhận thức hay chỉ tạm thời không thể dùng một tay.

Khả năng truy cập tốt thường cũng làm giao diện **rõ ràng, dễ dùng và ổn định hơn** cho nhiều người.

### 11.1. Bốn nguyên tắc POUR

Hướng dẫn **Web Content Accessibility Guidelines (WCAG)** tổ chức nhiều yêu cầu quanh bốn nguyên tắc:

| Nguyên tắc | Câu hỏi | Ví dụ đăng ký buổi học |
|---|---|---|
| **Perceivable — Có thể cảm nhận** | Người dùng có nhận được thông tin cần thiết qua cách phù hợp không? | Nhãn trường rõ, tương phản phù hợp, trạng thái không chỉ dựa vào màu. |
| **Operable — Có thể thao tác** | Người dùng có vận hành giao diện qua phương thức thích hợp? | Dùng Tab/Shift+Tab, Enter/Space theo đúng ngữ nghĩa; không mắc kẹt bàn phím. |
| **Understandable — Có thể hiểu** | Nội dung, điều hướng và phản hồi có rõ ràng, dự đoán được? | Lỗi “buổi đã đầy” chỉ rõ chuyện gì xảy ra và lựa chọn tiếp theo. |
| **Robust — Bền vững/tương thích** | Giao diện có được diễn giải đáng tin bởi trình duyệt và công nghệ hỗ trợ? | Dùng thành phần ngữ nghĩa, tên–vai trò–giá trị đúng cho control. |

Khi sản phẩm đặt mục tiêu tuân thủ WCAG (ví dụ **WCAG 2.2 mức AA**, nếu phù hợp yêu cầu tổ chức), cần xác định **phiên bản, mức và phạm vi**. Một checklist rút gọn trong bài học này **không đủ để tuyên bố toàn bộ sản phẩm đã đạt một mức tuân thủ WCAG**.

### 11.2. Accessibility không thể là bước “sửa màu” ở cuối

Nếu bản thiết kế ngay từ đầu dựa trên drag-and-drop không có phương thức thao tác khác, hoặc dùng các phần tử không có ngữ nghĩa để mô phỏng button, việc bổ sung khả năng truy cập ở cuối có thể tốn công sửa kiến trúc tương tác.

Cần đưa a11y vào:

- **Discovery:** ai đang gặp trở ngại, trong hoàn cảnh nào?
- **Thiết kế:** cấu trúc trang, nhãn, thứ tự điều hướng, tương phản và phản hồi lỗi.
- **Xây dựng:** dùng HTML semantic, control chuẩn, focus đúng, thông báo trạng thái.
- **Kiểm thử:** tự động hóa những quy tắc phát hiện được; kiểm tra thủ công và công nghệ hỗ trợ phù hợp.
- **Phản hồi thật:** xác minh người dùng có thể hoàn thành tác vụ, không chỉ từng control đạt yêu cầu riêng lẻ.

## 12. Kiểm tra accessibility theo hành trình người dùng

### 12.1. Những điểm thường dễ bị bỏ sót

| Vấn đề | Điều cần kiểm tra | Ví dụ |
|---|---|---|
| **Thao tác bàn phím** | Đi được tới mọi hành động quan trọng, thứ tự focus hợp lý, không keyboard trap. | Đăng ký và hủy mà không cần chuột. |
| **Focus hiển thị** | Vị trí focus có nhận biết được; khi mở/đóng modal hoặc có lỗi, focus được quản lý hợp lý. | Sau khi dialog đóng, focus trở lại điểm có nghĩa. |
| **Tên và vai trò điều khiển** | Input, button và các thành phần có tên dễ hiểu, role/state chính xác. | Nút “Đăng ký buổi 9 giờ” thay vì chỉ có biểu tượng. |
| **Lỗi biểu mẫu** | Nêu lỗi bằng văn bản, gắn lỗi với trường liên quan và hướng sửa. | “Vui lòng chọn buổi học” thay vì chỉ viền đỏ. |
| **Thông báo động** | Kết quả tác vụ có thể được công nghệ hỗ trợ nhận biết. | Thông báo “Đăng ký thành công” hoặc “Buổi đã đầy”. |
| **Tương phản và màu** | Văn bản, thành phần giao diện đáp ứng ngưỡng áp dụng; không chỉ dùng màu biểu đạt trạng thái. | Trạng thái “Đã hủy” có cả chữ, không chỉ chấm xám. |
| **Phóng to và bố cục** | Nội dung vẫn dùng được khi người dùng tăng kích thước, màn hình hẹp hoặc thay hướng hiển thị. | Không mất nút xác nhận ở mức zoom mục tiêu. |
| **Nội dung đa phương tiện** | Chú thích, mô tả hoặc phương án thay thế theo yêu cầu áp dụng. | Hướng dẫn video có phụ đề phù hợp. |
| **Thời gian và chuyển động** | Những giới hạn thời gian hoặc hoạt ảnh không làm người dùng bị loại khỏi tác vụ. | Session hết hạn được thông báo và có cách xử lý phù hợp. |
| **Ngôn ngữ dễ hiểu** | Thuật ngữ, chỉ dẫn, thông báo có nội dung và ngôn ngữ phù hợp. | “Chưa xác nhận đăng ký” thay vì mã lỗi nội bộ. |

Không nên suy ra rằng chỉ vì dùng một thư viện UI “hỗ trợ accessibility”, mọi trường hợp tích hợp và hành trình thực đều đạt yêu cầu.

### 12.2. Ví dụ HTML ngữ nghĩa

Ví dụ đơn giản về một biểu mẫu có nhãn rõ và vùng thông báo trạng thái:

~~~html
<form id="registration-form">
  <label for="session">Chọn buổi hướng dẫn</label>
  <select id="session" name="session" required>
    <option value="">-- Chọn một buổi --</option>
    <option value="session-1">Thứ Ba, 09:00</option>
    <option value="session-2">Thứ Năm, 14:00</option>
  </select>

  <button type="submit">Đăng ký buổi học</button>

  <p id="registration-status" role="status" aria-live="polite"></p>
</form>
~~~

Điều tốt ở ví dụ:

- Phần tử **label** liên kết tới **select**.
- Thành phần native hỗ trợ bàn phím và ngữ nghĩa sẵn có.
- **required** truyền thông tin về trường bắt buộc ở mức HTML.
- Vùng **role="status"** có thể dùng để thông báo kết quả không khẩn khi nội dung được cập nhật đúng.

**Ví dụ này chưa phải một form hoàn chỉnh hoặc đã chứng nhận accessible.** Cần bổ sung xử lý submit, trạng thái đang xử lý, lỗi liên kết với trường, focus khi cần, thông báo không thành công, quyền và bảo mật phía máy chủ, cùng kiểm tra trên công nghệ hỗ trợ mục tiêu. Với lỗi nghiêm trọng hoặc khi cần người dùng chủ động sửa, chỉ cập nhật một vùng live region có thể chưa đủ; cần đảm bảo thông tin lỗi được tìm và hiểu.

### 12.3. Kiểm thử tự động giúp gì, không giúp gì?

Các công cụ kiểm tra a11y tự động có thể phát hiện một số lỗi như thiếu nhãn form, thuộc tính ARIA không hợp lệ hoặc mức tương phản trong trường hợp có thể phân tích. Nhưng chúng thường **không đủ để xác minh**:

- Thứ tự focus có hợp lý với luồng sử dụng không.
- Người dùng hiểu thông báo lỗi và biết cách sửa không.
- Giao diện có thực hiện được toàn bộ bằng công nghệ hỗ trợ mục tiêu không.
- Nội dung thay đổi động được thông báo đúng thời điểm không.
- Hành trình hoàn chỉnh có loại trừ một nhóm người dùng không.

Cần kiểm tra thủ công và thử với những phương thức tương tác/công nghệ hỗ trợ phù hợp. Khi có điều kiện, **thu phản hồi trực tiếp từ người có nhu cầu tiếp cận** giúp tìm vấn đề mà checklist kỹ thuật khó phát hiện.

## 13. Khả năng vận hành: thiết kế để quan sát, hỗ trợ và khôi phục

**Operability** là khả năng dịch vụ được **triển khai, cấu hình, giám sát, hỗ trợ, điều tra, bảo trì và khôi phục** một cách phù hợp với đặc điểm sản phẩm.

Một tính năng trả dữ liệu đúng trong điều kiện tốt nhưng không ai biết nó đã bắt đầu ghi sai khi gặp lỗi mạng có thể rất khó vận hành. Từ đầu cần hỏi:

- Hành vi quan trọng cần quan sát là gì?
- Người trực biết sự cố đang ảnh hưởng người dùng ra sao?
- Có thể xác định phiên bản và thay đổi nào liên quan không?
- Khi một dịch vụ ngoài lỗi, hệ thống suy giảm thế nào và có đường phục hồi không?
- Có phương án giảm tác động khi chưa biết nguyên nhân chính xác không?
- Dữ liệu được sao lưu, khôi phục và đối soát theo yêu cầu như thế nào?

### 13.1. Metrics, logs và traces

| Tín hiệu | Công dụng | Ví dụ |
|---|---|---|
| **Metric** | Theo dõi xu hướng và cảnh báo theo thời gian. | Số yêu cầu đăng ký hợp lệ thành công/thất bại, p95, độ dài hàng đợi. |
| **Log** | Ghi sự kiện cần để chẩn đoán. | Yêu cầu bị từ chối do hết chỗ hay do lỗi ghi dữ liệu. |
| **Trace** | Kết nối hành trình của một yêu cầu qua các thành phần. | API → dịch vụ đăng ký → cơ sở dữ liệu → dịch vụ thông báo. |
| **Sự kiện nghiệp vụ** | Phản ánh trạng thái quan trọng của sản phẩm. | “Đăng ký đã được xác nhận”, “Yêu cầu gửi lặp đã được xử lý”. |
| **Phản hồi hỗ trợ** | Cho biết người dùng gặp vấn đề gì ngoài tín hiệu đo hiện có. | Học viên không biết trạng thái khi mạng bị ngắt. |

Không nên ghi thông tin cá nhân, token hoặc bí mật vào telemetry chỉ để dễ debug. Cần chính sách quyền truy cập, lưu giữ và ẩn/giảm dữ liệu nhạy cảm phù hợp.

### 13.2. Giám sát kỹ thuật và giám sát nghiệp vụ

Một máy chủ trả HTTP 200 chưa chứng minh đăng ký được ghi hợp lệ. Với luồng đăng ký, có thể cần:

- **Tỷ lệ yêu cầu hợp lệ được xử lý đúng**.
- **Số trường hợp hệ thống xác nhận vượt số chỗ**, kỳ vọng không xảy ra.
- **Số lỗi ghi dữ liệu**, timeout và thao tác retry.
- **Độ trễ theo endpoint và nhóm tác vụ**.
- **Số trạng thái chưa rõ** cần đối soát.
- **Số email xác nhận gửi khi chưa có đăng ký hợp lệ**, cần phát hiện và ngăn.

Chỉ số phải được định nghĩa chặt chẽ để tránh tính một yêu cầu bị từ chối **đúng vì hết chỗ** thành lỗi hệ thống.

### 13.3. Runbook và quyền hành động

Một **runbook** là hướng dẫn vận hành có cấu trúc cho tình huống đã biết, ví dụ:

1. Cách xác định sự cố và phạm vi ảnh hưởng.
2. Dashboard, log/trace và dữ liệu an toàn cần xem.
3. Ai có quyền vô hiệu hóa luồng đăng ký hoặc chuyển sang chế độ an toàn.
4. Điều kiện nào cho phép rollback hoặc khôi phục.
5. Cần kiểm tra dữ liệu và người dùng nào trước khi mở lại.
6. Khi nào phải tăng cấp cho chuyên gia bảo mật, dữ liệu hoặc sản phẩm.
7. Cách ghi nhận việc còn lại và hậu kiểm.

Runbook phải được kiểm tra và cập nhật. **Một tài liệu chưa từng diễn tập không tự chứng minh đội có khả năng phục hồi trong sự cố thật.**

## 14. SLI, SLO và những mục tiêu vận hành có ý nghĩa

Để biết chất lượng vận hành có phù hợp nhu cầu hay không, nhóm có thể dùng:

- **SLI (Service Level Indicator):** thước đo định lượng một khía cạnh chất lượng dịch vụ.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong một khoảng thời gian.
- **SLA (Service Level Agreement):** thỏa thuận mức dịch vụ có điều khoản và hệ quả cụ thể khi áp dụng.

Ví dụ SLI giả định cho luồng đăng ký:

~~~text
SLI đăng ký hợp lệ thành công (%) =
  Số yêu cầu đăng ký hợp lệ được xử lý đúng trong ngưỡng
  / Tổng số yêu cầu đăng ký hợp lệ thuộc phạm vi đo
  × 100

SLO minh họa:
  Ít nhất 99,9% trong một cửa sổ 30 ngày.
~~~

Phải làm rõ “yêu cầu hợp lệ”, kết quả “đúng”, cách xét retry và độ trễ, nguồn dữ liệu và trường hợp loại trừ. Những giá trị nêu trên **chỉ để minh họa phương pháp**, không phải lời khuyên rằng mọi hệ thống học trực tuyến nên dùng mục tiêu 99,9%.

### 14.1. Error budget không cho phép bỏ qua an toàn

Với một SLO theo tỷ lệ, phần không đạt được chấp nhận theo mục tiêu và cửa sổ đo đôi khi gọi là **error budget**. Nó giúp cân nhắc đầu tư vào thay đổi và độ tin cậy.

Tuy nhiên, nếu một lỗi làm lộ dữ liệu học viên, nhóm phải xử lý theo mức độ nghiêm trọng và nghĩa vụ liên quan **dù SLO vẫn đạt hoặc còn error budget**. SLO không thay thế kiểm soát bảo mật hay tính toàn vẹn dữ liệu.

### 14.2. Không phải mọi chỉ số đều cần cảnh báo đánh thức người trực

Cảnh báo có thể hành động nên dành cho nguy cơ cần phản ứng theo thời gian. Những chỉ số dài hạn về tối ưu hiệu năng, xu hướng a11y hoặc nợ kỹ thuật có thể được xem tại buổi phân tích định kỳ.

Nếu mọi dao động đều gửi cảnh báo khẩn, đội vận hành dễ kiệt sức và bỏ qua tín hiệu thực sự nguy hiểm.

## 15. Kết hợp bốn thuộc tính khi chúng có thể xung đột

Những lựa chọn thiết kế thường ảnh hưởng nhiều thuộc tính đồng thời:

| Thay đổi | Lợi ích có thể có | Rủi ro cần kiểm tra |
|---|---|---|
| Thêm bước xác thực nhạy cảm | Tăng bảo vệ thao tác quan trọng. | Tăng ma sát, thời gian, khó thao tác với công nghệ hỗ trợ nếu thiết kế kém. |
| Cache dữ liệu đăng ký | Giảm truy vấn và cải thiện tốc độ. | Trạng thái không còn chỗ bị cũ, nguy cơ lộ thông tin nếu cache không tách quyền. |
| Thêm logging chi tiết | Dễ điều tra sự cố. | Tăng chi phí/độ trễ và rủi ro ghi dữ liệu nhạy cảm. |
| Thêm hiệu ứng xác nhận | Giao diện có thể dễ nhận biết hơn. | Người nhạy cảm với chuyển động hoặc dùng thiết bị yếu có thể gặp khó. |
| Tự động retry khi timeout | Tăng khả năng vượt lỗi tạm thời. | Tạo giao dịch lặp nếu hệ thống không idempotent; tăng tải khi hệ thống đang suy giảm. |
| Mở rộng kiểm tra CI | Phát hiện rủi ro sớm hơn. | Pipeline chậm, flaky tests hoặc chi phí cao nếu không tối ưu. |

### 15.1. Không chọn một chỉ số làm “vua”

Tối ưu latency bằng cách bỏ kiểm tra phân quyền có thể làm API nhanh nhưng mất an toàn. Tăng kích thước nút và nhãn để hỗ trợ truy cập có thể thay đổi bố cục; cần thiết kế và kiểm tra lại, không coi đó là một “lỗi hiệu năng” hay “lỗi thẩm mỹ”.

Nhóm nên xác định **ràng buộc không được vi phạm** và những điểm có thể đánh đổi:

1. Tiêu chuẩn bảo mật, an toàn và nghĩa vụ bắt buộc.
2. Khả năng thực hiện tác vụ cốt lõi của người dùng.
3. Mục tiêu hiệu năng, độ tin cậy và trải nghiệm đã thống nhất.
4. Chi phí phát triển, vận hành và khả năng thay đổi trong tương lai.

Quyết định có thể được ghi lại với lý do, bằng chứng, giới hạn và thời điểm xem lại.

### 15.2. Giảm phạm vi để giữ chất lượng

Khi không đủ thời gian, thay vì bỏ kiểm thử quyền hay hỗ trợ bàn phím, nhóm có thể:

- Hỗ trợ đăng ký một loại buổi trước, chưa làm danh sách chờ.
- Chỉ mở ở phạm vi đã kiểm chứng và có cơ chế vận hành phù hợp.
- Hoãn tính năng gợi ý tự động chưa có bằng chứng giá trị.
- Tách thử nghiệm khám phá khỏi khả năng đã được công bố là dùng được.

**Phần nhỏ nhưng hoàn chỉnh** hữu ích hơn một loạt chức năng nửa vời tạo rủi ro cho người dùng.

## 16. Definition of Done cho chất lượng liên tục

Trong Scrum, DoD là **mô tả chính thức trạng thái của Increment khi đạt các tiêu chuẩn chất lượng bắt buộc của sản phẩm**. Nếu tổ chức đã có DoD tiêu chuẩn, nó là mức tối thiểu phải tuân theo. Nếu nhiều Scrum Team cùng làm một sản phẩm, họ cần **một DoD chung**.

### 16.1. Mẫu DoD cần điều chỉnh theo sản phẩm

~~~text
DEFINITION OF DONE - ví dụ cho một sản phẩm web có dữ liệu người dùng

Chỉ coi một PBI là Done khi, trong phạm vi điều kiện áp dụng:

[ ] Hành vi mong đợi và các tiêu chí chấp nhận liên quan đã được xác minh.
[ ] Thay đổi được tích hợp với sản phẩm hiện có, không làm hỏng luồng cũ.
[ ] Kiểm tra phân quyền và xử lý dữ liệu nhạy cảm áp dụng đã đạt.
[ ] Các kiểm tra phụ thuộc/secrets/cấu hình theo chính sách đã thực hiện.
[ ] Mục tiêu hiệu năng áp dụng và thử nghiệm rủi ro đã có bằng chứng.
[ ] Giao diện mới/thay đổi đáp ứng tiêu chí khả năng truy cập áp dụng.
[ ] Trạng thái lỗi, thông báo động, thao tác bàn phím được kiểm tra khi cần.
[ ] Metric/log/trace và cảnh báo thiết yếu đã có, không lộ dữ liệu nhạy cảm.
[ ] Điều kiện triển khai, tương thích, khôi phục và runbook cần thiết đã đạt.
[ ] Những tiêu chuẩn bắt buộc của tổ chức/sản phẩm đều được tuân thủ.
[ ] Increment tích hợp, thực sự usable trong phạm vi được tuyên bố.

Nếu chưa đạt một điều kiện bắt buộc:
  - Không gắn nhãn Done.
  - Nêu rõ điều kiện thiếu, rủi ro và người cần phối hợp.
  - Làm tiếp, hoặc thương lượng lại phạm vi theo đúng accountability.
~~~

Đây không phải định nghĩa chính thức có sẵn từ Scrum Guide. **Nhóm cần tạo tiêu chuẩn cụ thể, kiểm chứng được theo sản phẩm**, giữ những yêu cầu tổ chức bắt buộc và tránh checkbox hình thức.

### 16.2. DoD áp dụng nhất quán, bằng chứng tương xứng rủi ro

Một thay đổi câu chữ có thể không cần chạy lại bài thử tải hàng giờ nếu nhóm có cơ sở chứng minh không ảnh hưởng hiệu năng. Nhưng nếu thay đổi một API đọc thông tin cá nhân, kiểm tra phân quyền là bắt buộc theo tiêu chuẩn đã chọn, dù mã chỉ sửa vài dòng.

Nguyên tắc là **chất lượng tối thiểu nhất quán, cách kiểm chứng phù hợp loại thay đổi**. Không tùy ý bỏ yêu cầu quan trọng vào cuối Sprint để làm đẹp tiến độ.

### 16.3. DoD phải được cải tiến bằng phản hồi

Nếu production phát hiện lỗi mà trước đó chưa có phép kiểm tra phù hợp, nhóm cần cân nhắc bổ sung một điều kiện hoặc kiểm chứng tương ứng, đồng thời không biến DoD thành danh sách vô hạn khó thực hiện.

Trong Retrospective, hãy hỏi:

- Sai lệch phát sinh từ khoảng trống nào của thiết kế hoặc kiểm thử?
- Cách kiểm tra nào có thể phát hiện sớm và đáng tin?
- Điều kiện nào nên thành tiêu chuẩn chung, điều kiện nào chỉ áp dụng cho hạng mục rủi ro tương ứng?
- Có cách tự động hóa hoặc đơn giản hóa bước kiểm tra không?

## 17. Kiến trúc pipeline kiểm chứng: nhanh, có chiều sâu và có thể tin

Một pipeline CI/CD có thể cung cấp nhiều vòng phản hồi theo tốc độ và phạm vi:

~~~mermaid
flowchart LR
    A["Thay đổi nhỏ"] --> B["Local: unit, lint, checks nhanh"]
    B --> C["CI: build, unit, SAST/SCA phù hợp"]
    C --> D["Contract, integration, a11y automation"]
    D --> E["Hiệu năng/rủi ro chuyên sâu khi thích hợp"]
    E --> F["Increment đạt DoD"]
    F --> G["Phát hành kiểm soát và quan sát"]
    G --> H["Phản hồi, sửa, cải tiến"]
    H --> A
~~~

Sơ đồ là mô hình gợi ý. Có thể chạy các loại kiểm tra song song hoặc theo rủi ro. Một số bài thử tải, đánh giá khả năng truy cập chuyên sâu hoặc kiểm tra bảo mật có thể yêu cầu môi trường và người có chuyên môn, không nhất thiết chạy sau từng commit.

### 17.1. Quality gate không nên chỉ là danh sách công cụ

Một **quality gate** là điều kiện phải đạt trước khi tiến sang một bước như hợp nhất mã hoặc mở phiên bản. Nó chỉ hữu ích khi phản ánh rủi ro thật và có đường xử lý khi không đạt.

Ví dụ:

| Gate | Bằng chứng mong muốn | Nếu không đạt |
|---|---|---|
| **Build/unit** | Thay đổi biên dịch và các quy tắc cốt lõi vẫn đạt. | Sửa/hoàn tác, không tích hợp thêm thay đổi gây khó điều tra. |
| **Tích hợp và hợp đồng** | API, schema và luồng quan trọng hoạt động tương thích. | Làm rõ khác biệt, cập nhật hợp đồng và kiểm chứng lại. |
| **Bảo mật** | Không còn rủi ro không chấp nhận theo chính sách. | Đánh giá, khắc phục hoặc xử lý ngoại lệ theo thẩm quyền và nghĩa vụ. |
| **Accessibility** | Các tiêu chí tiếp cận trong phạm vi thay đổi được xác minh. | Sửa hành vi/thiết kế hoặc giảm phạm vi an toàn. |
| **Performance** | Đạt mục tiêu đã định trong workload phù hợp. | Điều tra nút thắt, làm rõ giới hạn và kiểm tra lại. |
| **Operability/release** | Có phương án quan sát và ứng phó trước khi mở. | Chuẩn bị hoặc điều chỉnh kế hoạch phát hành. |

Không nên “bấm qua” một gate quan trọng chỉ vì deadline. Nếu có quy trình ngoại lệ bắt buộc của tổ chức, quyết định phải có **thẩm quyền, rủi ro được ghi rõ và không vi phạm nghĩa vụ không thể bỏ qua**.

### 17.2. Kiểm thử tự động có thể sai hoặc thiếu

Pipeline xanh chỉ cho biết các phép thử đã cấu hình vượt qua. Chất lượng có thể vẫn thiếu:

- Kịch bản phân quyền theo đối tượng chưa được viết.
- Phân phối tải thực khác dữ liệu giả lập.
- Thứ tự focus hoặc trải nghiệm screen reader chưa được kiểm thử.
- Cảnh báo chưa được thử bằng một tình huống lỗi có kiểm soát.

Ngược lại, flaky tests có thể làm tín hiệu kém tin. Cần quản lý độ tin cậy của bộ kiểm thử, không chạy lại liên tục cho đến khi có màu xanh.

## 18. Tình huống xuyên suốt: mở đăng ký buổi học cho nhiều người dùng

**Toàn bộ tình huống và con số trong phần này là giả định để minh họa**, không phải tiêu chuẩn thực nghiệm hoặc thiết kế production áp dụng cho mọi hệ thống.

### 18.1. Product Goal và phạm vi Sprint

Một nhóm phát triển nền tảng học lập trình có Product Goal:

> Học viên có thể tìm và đăng ký buổi hướng dẫn phù hợp một cách tự chủ, đáng tin cậy và không bị loại khỏi trải nghiệm do cách tương tác.

Sprint Goal:

> Cung cấp một luồng đăng ký một buổi còn chỗ, hoạt động an toàn và dùng được trong phạm vi thí điểm đã xác định.

Nhóm chưa đưa vào Sprint các tính năng danh sách chờ nhiều cấp, lịch cá nhân hóa hoặc thanh toán. Đó là quyết định **giảm phạm vi** để có thể kiểm chứng phần đầu với chất lượng phù hợp.

### 18.2. Bốn góc nhìn khi refinement

| Góc nhìn | Câu hỏi quan trọng | Ví dụ quyết định |
|---|---|---|
| **Bảo mật** | Ai được xem/đăng ký/hủy? ID có thể bị đoán và truy cập trái quyền không? | Kiểm tra quyền ở backend theo học viên và đăng ký cụ thể. |
| **Hiệu năng** | Bao nhiêu người truy cập đồng thời? Có thể tranh chấp chỗ cuối? | Thử tải đại diện; cơ chế bảo vệ bất biến số chỗ. |
| **Truy cập** | Người dùng bàn phím, screen reader hoặc phóng to có hoàn tất tác vụ? | Dùng control ngữ nghĩa, focus rõ, lỗi có văn bản và thông báo trạng thái. |
| **Vận hành** | Làm sao biết đăng ký sai, ai tắt luồng và kiểm tra lại? | Metric nghiệp vụ, cảnh báo hành động được, runbook giảm thiệt hại. |

Nhóm ghi lại những giả định chưa được chứng minh, chẳng hạn số người đăng ký đồng thời trong giờ cao điểm và loại công nghệ hỗ trợ ưu tiên kiểm thử.

### 18.3. Ví dụ các acceptance criteria

1. Học viên hợp lệ có thể đăng ký một buổi còn chỗ.
2. Học viên không thể thay đổi hoặc đọc đăng ký của người khác trái quyền.
3. Khi chỉ còn một chỗ, các yêu cầu đồng thời không được xác nhận nhiều hơn sức chứa.
4. Một yêu cầu gửi lặp không tạo thêm đăng ký hợp lệ trái quy tắc.
5. Khi kết quả ghi chưa chắc chắn, giao diện không được thông báo thành công giả.
6. Luồng chính có thể hoàn tất qua bàn phím và phản hồi trạng thái phù hợp với công nghệ hỗ trợ mục tiêu.
7. Tại tải thí điểm đã định nghĩa, các chỉ số hiệu năng/độ tin cậy đạt ngưỡng được thống nhất.
8. Khi lỗi ghi tăng, tín hiệu vận hành có thể phân biệt lỗi thật với trường hợp hết chỗ hợp lệ.

Các tiêu chí được xem xét cùng DoD chung, không thay thế tiêu chuẩn chất lượng tổ chức.

### 18.4. Phân chia lát công việc nhưng không chia rời trách nhiệm

Nhóm có thể phối hợp theo các lát:

| Lát công việc | Giá trị và điều kiện cần có |
|---|---|
| **Xem buổi trống** | Thông tin chính xác, có quyền phù hợp, thao tác qua bàn phím, đo độ trễ và lỗi tải dữ liệu. |
| **Xác nhận đăng ký** | Ghi dữ liệu nhất quán, không vượt sức chứa, thông báo đúng, kiểm tra cạnh tranh, giám sát kết quả. |
| **Xem trạng thái của tôi** | Không lộ dữ liệu người khác, nội dung trạng thái dễ hiểu, kiểm tra quyền, có tín hiệu lỗi đọc. |
| **Thông báo sau xác nhận** | Không gửi thông báo thành công trước khi có trạng thái được xác nhận đáng tin, kiểm tra gửi lặp. |

Các lát có thể tiến tới Done riêng khi thật sự hữu ích, tích hợp và đáp ứng DoD; không nên xem việc chỉ dựng một màn hình placeholder là Increment hoàn thành.

### 18.5. Một vòng phản hồi kỹ thuật

Trong lúc triển khai, unit test cho hàm “còn chỗ” đạt. Một kỹ sư đặt câu hỏi: “Điều gì xảy ra nếu hai học viên đều đọc thấy còn một chỗ rồi gửi cùng lúc?”

Nhóm thực hiện kiểm thử tích hợp với hai yêu cầu gần đồng thời và phát hiện cả hai được xác nhận. Đây là lỗi **bất biến nghiệp vụ và nhất quán dữ liệu**, không đơn thuần vấn đề tốc độ.

Nhóm cần thiết kế cơ chế ghi phù hợp như giao dịch/điều kiện cập nhật nguyên tử, bảo vệ yêu cầu lặp và kiểm tra lại. Giải pháp cụ thể tùy kiến trúc; **thêm một điều kiện kiểm tra trên frontend không đủ bảo vệ dữ liệu trong hệ thống đa người dùng**.

### 18.6. Một vòng phản hồi accessibility

Người kiểm thử chỉ dùng bàn phím phát hiện khi mở hộp thoại xác nhận, focus vẫn nằm phía sau. Người thử screen reader không nghe thông báo lỗi “Buổi đã đầy” được cập nhật động.

Nhóm sửa cách quản lý focus, thông báo trạng thái và nội dung lỗi, sau đó kiểm tra lại toàn bộ hành trình. Đây là vấn đề **khả năng hoàn tất tác vụ**, không chỉ thẩm mỹ giao diện.

Nếu thư viện giao diện không hỗ trợ hành vi đúng, có thể cần thay đổi thành phần hoặc cách tương tác; không nên cố vá bằng một số thuộc tính ARIA ngẫu nhiên mà không kiểm chứng.

### 18.7. Một vòng phản hồi hiệu năng

Thử nghiệm tải với workload giả định cho thấy p95 tăng mạnh khi nhiều người cùng xem giờ trống. Phân tích metric/trace phát hiện nhiều truy vấn lặp tới cơ sở dữ liệu.

Nhóm thử tối ưu truy vấn hoặc cache phù hợp cho dữ liệu có thể đọc lại, sau đó đo:

- p50/p95/p99, tỷ lệ lỗi và throughput.
- Sử dụng kết nối và điểm nghẽn cơ sở dữ liệu.
- Dữ liệu xem còn chính xác không khi chỗ trống thay đổi.
- Cơ chế cache có nguy cơ làm lộ dữ liệu theo người dùng không.

**Cải thiện độ trễ không được làm sai số chỗ hoặc rò rỉ trạng thái đăng ký.**

### 18.8. Một vòng phản hồi vận hành

Trước khi mở thí điểm, nhóm tạo tình huống lỗi ghi có kiểm soát trên môi trường phù hợp. Alert ban đầu không kích hoạt vì chỉ đo HTTP 5xx, trong khi ứng dụng đang trả HTTP 200 kèm trạng thái nghiệp vụ thất bại.

Nhóm bổ sung metric nghiệp vụ và kiểm tra đường thông báo. Họ cũng xác định ai có quyền tạm tắt đăng ký mới nếu phát hiện ghi sai và cách kiểm tra dữ liệu trước khi mở lại.

**Một cảnh báo đã được cấu hình nhưng chưa được thử chưa phải bằng chứng năng lực vận hành.**

### 18.9. Quyết định release và phản hồi sau sử dụng

Khi Increment đạt DoD, nhóm có thể mở cho phạm vi thí điểm đã được phép với tín hiệu và người trực phù hợp. Sau đó quan sát:

- Học viên có hoàn tất đăng ký không?
- Có khiếu nại hoặc dấu hiệu truy cập trái quyền?
- p95 và tỷ lệ lỗi ở tải thật khác thử nghiệm ra sao?
- Người dùng sử dụng bàn phím/công nghệ hỗ trợ có gặp khó khăn mới?
- Đội trực có nhận được cảnh báo hữu ích hay bị nhiều nhiễu?

Product Owner và team dùng dữ liệu này để quyết định mở rộng, cải tiến hoặc thay đổi ưu tiên backlog. Không được gọi thí điểm thành công chỉ vì chưa có ai báo lỗi trong một mẫu quá nhỏ.

## 19. Đo lường chất lượng mà không tạo động cơ sai

Chất lượng liên tục cần nhiều tín hiệu kết hợp, vì một chỉ số đơn lẻ có thể che khuất rủi ro.

| Nhóm | Tín hiệu minh họa | Điều cần cảnh giác |
|---|---|---|
| **Bảo mật** | Rủi ro đã khắc phục, thời gian xử lý lỗ hổng nghiêm trọng, kết quả kiểm tra phân quyền. | Số cảnh báo thấp có thể do không quét, không báo hoặc không quan sát. |
| **Hiệu năng** | p95/p99 theo tác vụ, error rate, throughput, độ dài hàng đợi, capacity. | Trung bình chung hoặc môi trường thử không đại diện làm sai kết luận. |
| **Truy cập** | Vấn đề a11y theo mức ảnh hưởng, hành trình đã kiểm tra, phản hồi từ người dùng. | Đếm số lỗi tự động bằng 0 rồi tuyên bố giao diện đã hoàn toàn accessible. |
| **Vận hành** | SLI/SLO, sự cố, phát hiện và giảm tác động, cảnh báo hữu ích, mức tải trực. | Chỉ đo uptime máy chủ hoặc số alert gửi đi. |
| **Dòng công việc** | Cycle time, throughput, WIP, work item age, blocked time. | Tăng số story Done bằng cách giảm kiểm thử/DoD. |
| **Kết quả sản phẩm** | Tỷ lệ hoàn tất tác vụ, hỗ trợ thủ công, phản hồi và rủi ro thực tế. | Đánh đồng sự tương quan với nguyên nhân hoặc bỏ qua yếu tố ngoài phần mềm. |

### 19.1. Ví dụ dữ liệu giả định sau cải tiến

| Chỉ số trong phạm vi đo minh họa | Trước cải tiến | Sau cải tiến |
|---|---:|---:|
| p95 API xem buổi trống tại workload thử đã định (ms) | 1.500 | 720 |
| Lỗi tích hợp quan trọng phát hiện muộn trong một giai đoạn | 6 | 2 |
| Lỗi a11y cản trở luồng bàn phím trong phạm vi kiểm tra | 4 | 0 |
| Thời gian phát hiện sự cố ghi đăng ký trong bài diễn tập (phút) | 18 | 4 |
| Cycle time trung vị của PBI (ngày làm việc) | 12 | 9 |

**Các con số hoàn toàn giả định**, không phải nghiên cứu, chuẩn ngành hay dự báo cho dự án thật. Mức giảm lỗi a11y trong phạm vi kiểm tra không chứng minh toàn hệ thống hết rào cản; bài diễn tập không bảo đảm mọi sự cố thực sẽ được phát hiện trong bốn phút.

Trước khi kết luận cải tiến đã gây ra kết quả, nhóm phải xem kích thước hạng mục, tải, dữ liệu mẫu, thay đổi sản phẩm, năng lực và phương pháp đo.

### 19.2. Các chỉ số cần dẫn tới quyết định

Nếu p95 giảm nhưng tỷ lệ đăng ký thành công không tăng, cần xem liệu hiệu năng có phải vấn đề chính. Nếu lỗi tự động a11y bằng 0 nhưng người dùng không thể hoàn tất luồng, cần bổ sung kiểm chứng thủ công và trải nghiệm. Nếu cảnh báo nhanh nhưng người trực không có quyền giảm tác động, cần cải thiện trách nhiệm và runbook.

**Mục tiêu của số liệu là học hỏi và bảo vệ người dùng, không phải xây bảng xếp hạng cá nhân hay làm dashboard đẹp.**

## 20. Áp dụng trong Scrum, Kanban và XP

### 20.1. Scrum: đưa chất lượng vào Increment, không đẩy sang Sprint sau

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog, bao gồm việc cân nhắc rủi ro chất lượng.
- **Developers** chịu trách nhiệm tạo các khía cạnh của Increment dùng được và tuân thủ Definition of Done.
- **Scrum Master** chịu trách nhiệm về hiệu quả của Scrum Team và giúp tháo trở ngại trong cách áp dụng Scrum.
- **Cả Scrum Team** chịu trách nhiệm tạo Increment có giá trị, hữu ích trong mỗi Sprint.

Việc kiểm tra quyền, hiệu năng, khả năng truy cập hoặc vận hành cần thiết **không mặc nhiên là việc ngoài Sprint**. Nếu phần làm chưa đạt DoD thì chưa được coi Done. Developers và Product Owner có thể thương lượng **phạm vi** khi cần; không nên hạ tiêu chuẩn chất lượng để kịp hoàn thành mọi ticket.

**Sprint Review** có thể xem phản hồi người dùng và chất lượng thực; **Retrospective** giúp cải tiến kiểm thử, tích hợp, phối hợp với chuyên gia và phản ứng sự cố.

### 20.2. Kanban: nhìn thấy công việc chất lượng và giới hạn WIP

Kanban giúp hiển thị công việc sửa lỗi, cải tiến bảo mật, tối ưu hiệu năng, sửa accessibility và bổ sung observability trong cùng dòng tạo giá trị. Chính sách rõ có thể phân biệt:

- Việc khẩn do sự cố đang gây thiệt hại.
- Việc có hạn tuân thủ thật.
- Việc thông thường phục vụ Product Goal.
- Việc phòng ngừa và cải thiện năng lực dài hạn.

Giới hạn WIP và đo cycle time giúp tránh mở quá nhiều ticket “nâng chất lượng” nhưng ít việc thật sự được hoàn thành. Khi có sự cố nghiêm trọng, phải xử lý theo quy trình ứng phó cần thiết; **WIP limit không phải lý do trì hoãn nghĩa vụ bảo vệ người dùng**.

### 20.3. XP: phản hồi kỹ thuật nhanh, bảo toàn hành vi

Thực hành **TDD, pair programming, continuous integration, refactoring và small releases** có thể giúp phát hiện sai lệch và thay đổi an toàn hơn.

Tuy nhiên:

- Unit test của một hàm kiểm tra quyền không chứng minh toàn bộ API đã phân quyền đúng.
- CI xanh không chứng minh hiệu năng tại tải thực.
- Test a11y tự động xanh không thay thế kiểm thử hành trình với bàn phím/công nghệ hỗ trợ.
- Refactoring an toàn vẫn cần kiểm tra các rủi ro hệ thống liên quan.

XP là **nguồn thực hành kỹ thuật hữu ích**, không thay thế các mục tiêu và kiểm chứng sản phẩm/vận hành.

## 21. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Cách thay thế |
|---|---|---|
| “Chức năng xong rồi mới thêm bảo mật.” | Quyền và dữ liệu có thể phải thiết kế lại, lỗi bị phát hiện muộn. | Làm rõ tài sản, quyền, abuse case từ refinement. |
| “Security là trách nhiệm duy nhất của đội bảo mật.” | Kỹ sư không kiểm tra những rủi ro họ tạo ra. | Cộng tác liên chức năng, chuyên gia hỗ trợ đúng lúc, quyền rõ. |
| “SAST/SCA xanh nghĩa là không có lỗ hổng.” | Bỏ qua lỗi nghiệp vụ, phân quyền và cấu hình. | Kết hợp threat modeling và kiểm chứng theo rủi ro. |
| “Chỉ cần response time trung bình thấp.” | Người dùng ở phần đuôi phân phối vẫn gặp chậm nghiêm trọng. | Đo percentile, lỗi, workload và hành trình phù hợp. |
| “Tăng số server sẽ sửa mọi lỗi hiệu năng.” | Nút thắt DB/lock hoặc đối tác vẫn tồn tại. | Phân tích bằng metric/trace rồi thử giải pháp có kiểm chứng. |
| “Hiệu năng tốt có thể bỏ kiểm tra đồng thời.” | Hệ thống trả lời nhanh nhưng ghi sai dữ liệu. | Đo cả latency và tính đúng trạng thái. |
| “Accessibility chỉ là chỉnh màu và phông chữ.” | Bỏ lỗi bàn phím, focus, thông báo và ngữ nghĩa. | Thiết kế/kiểm thử theo hành trình và nguyên tắc POUR. |
| “Có thư viện UI accessible thì trang tự accessible.” | Tích hợp sai vẫn gây keyboard trap và lỗi thông báo. | Thử trải nghiệm thực với công nghệ hỗ trợ mục tiêu. |
| “Tool kiểm tra a11y báo 0 lỗi nghĩa là đạt WCAG.” | Bỏ sót vấn đề công cụ không nhận ra. | Xác định phạm vi/mức, kiểm tra thủ công và phản hồi thực. |
| “Vận hành chỉ là việc sau release.” | Không có giám sát, runbook, quyền phục hồi khi sự cố. | Xem operational readiness từ lúc thiết kế. |
| “HTTP 200 chứng minh giao dịch thành công.” | Che giấu lỗi nghiệp vụ và trạng thái không nhất quán. | Quan sát bất biến và outcome nghiệp vụ. |
| “Càng nhiều log càng dễ debug.” | Rò rỉ dữ liệu, tăng chi phí hoặc khó tìm tín hiệu. | Thu telemetry có mục đích, bảo vệ dữ liệu nhạy cảm. |
| “Có dashboard là vận hành sẵn sàng.” | Không có người nhận tín hiệu hoặc biết cách hành động. | Thử alert/runbook/khôi phục trong phạm vi an toàn. |
| “Chỉ cần thử tải trên dữ liệu mẫu cực nhỏ.” | Kết quả không đại diện, nút thắt thực vẫn ẩn. | Mô tả workload, dữ liệu và giới hạn phép đo. |
| “Hết Sprint thì giảm DoD để đánh dấu Done.” | Minh bạch và chất lượng bị phá vỡ. | Giảm phạm vi, minh bạch phần chưa Done, bảo toàn tiêu chuẩn. |
| “Mọi thay đổi phải qua một checklist khổng lồ giống nhau.” | Chậm phản hồi, kiểm tra hình thức, người dùng bỏ qua. | Dựa trên rủi ro và tiêu chuẩn bắt buộc, tự động hóa khi phù hợp. |
| “Đếm bug hoặc chỉ số chất lượng để xếp hạng cá nhân.” | Che giấu lỗi, tránh việc khó và giảm hỗ trợ nhau. | Dùng số liệu để cải tiến hệ thống làm việc. |
| “Một lần canary không lỗi chứng minh sản phẩm an toàn.” | Mẫu nhỏ và thời gian ngắn có thể bỏ sót vấn đề. | Kiểm soát rủi ro trước, quan sát và đánh giá theo phạm vi. |

## 22. Lộ trình áp dụng theo từng bước

Một nhóm chưa có hệ thống chất lượng hoàn chỉnh có thể bắt đầu từ những cải tiến nhỏ, có bằng chứng:

### Bước 1 — Chọn một hành trình quan trọng

Ví dụ “học viên đăng ký được buổi còn chỗ” thay vì cố tối ưu mọi endpoint. Xác định ai dùng, mục tiêu và hậu quả nếu sai.

### Bước 2 — Thảo luận đủ bốn thuộc tính

Ở refinement, hỏi một vài câu về quyền/dữ liệu, tải và tốc độ, tương tác bàn phím/công nghệ hỗ trợ, khả năng phát hiện/khôi phục lỗi. Ghi điều chưa biết và người có thể cung cấp bằng chứng.

### Bước 3 — Chuyển thành tiêu chí kiểm chứng

Chọn acceptance criteria, điều kiện DoD và mục tiêu dịch vụ phù hợp; không trộn lẫn tất cả vào một ticket mơ hồ “đảm bảo NFR”.

### Bước 4 — Tăng phản hồi kỹ thuật sớm

Thử thêm một kiểm tra quyền quan trọng, một integration test đồng thời, một kiểm tra a11y tự động kèm kiểm tra bàn phím và một chỉ số hiệu năng có workload rõ.

### Bước 5 — Chuẩn bị khả năng vận hành

Xác định tín hiệu nghiệp vụ và người nhận cảnh báo; thử một kịch bản lỗi có kiểm soát; làm rõ quyền tắt/mở an toàn và cách kiểm tra dữ liệu sau phục hồi.

### Bước 6 — Bàn giao phần nhỏ thực sự dùng được

Giảm phạm vi nếu cần; không bỏ các kiểm soát bắt buộc. Có thể phát hành theo nhóm thí điểm hợp lệ, với khả năng giám sát và xử lý tương ứng.

### Bước 7 — Quan sát kết quả và cải tiến

Xem lỗi thoát, latency, các rào cản a11y, tín hiệu vận hành và kết quả người dùng. Đưa phát hiện trở lại backlog, DoD hoặc cách làm. Thực hiện một cải tiến có người phụ trách và kiểm tra lại.

## 23. Bài tập thực hành

Một nhóm chuẩn bị thêm tính năng **hủy đăng ký buổi học** với yêu cầu:

- Học viên chỉ được hủy đăng ký của mình.
- Hủy thành công trả lại chỗ trống đúng một lần.
- Hai request hủy gần đồng thời không được trả chỗ hai lần.
- Người dùng nhận được trạng thái chính xác và có thể hoàn thành qua bàn phím.
- Bộ phận hỗ trợ phát hiện được lỗi hủy để xử lý theo quy trình.

### Bài tập 1 — Tìm bốn rủi ro trọng yếu

**Gợi ý phân tích:**

- Bảo mật: thay ID để hủy đăng ký người khác.
- Hiệu năng/tính nhất quán: tranh chấp khi thao tác gần đồng thời và gửi lặp.
- Truy cập: nút hủy hoặc dialog không dùng được qua bàn phím, thông báo động không được nhận biết.
- Vận hành: lỗi ghi được trả về như thành công và không có metric/cảnh báo.

### Bài tập 2 — Viết một acceptance criterion cho từng thuộc tính

**Gợi ý:**

1. Khi học viên A cố hủy đăng ký của B, yêu cầu bị từ chối và dữ liệu B không bị tiết lộ.
2. Khi hai yêu cầu hủy cùng một đăng ký hợp lệ gần đồng thời, số chỗ được trả lại tối đa một lần theo quy tắc.
3. Người chỉ dùng bàn phím có thể mở dialog, đọc hậu quả và xác nhận/hủy bỏ; focus được trả về vị trí phù hợp.
4. Khi cập nhật thất bại, người trực có thể phân biệt lỗi ghi với yêu cầu bị từ chối hợp lệ và có cách theo dõi xử lý.

### Bài tập 3 — Đề xuất phương án kiểm tra

**Gợi ý:** kiểm thử quyền phía máy chủ; integration test cho đồng thời/idempotency; kiểm tra bàn phím và công nghệ hỗ trợ mục tiêu; tạo lỗi có kiểm soát để kiểm tra metric/alert và phương án khôi phục. Nếu có mục tiêu latency, ghi workload và môi trường trước khi kết luận.

### Bài tập 4 — Đến cuối Sprint chưa đạt DoD thì sao?

**Gợi ý:** không coi hạng mục Done. Thảo luận với Product Owner để giữ Sprint Goal bằng cách hoàn tất lát nhỏ hơn nếu hữu ích và an toàn, hoặc đưa phần chưa hoàn thành trở lại Product Backlog. Không “tắt tạm” kiểm tra quyền, thông báo trạng thái hay tính nhất quán chỉ để tăng số ticket đóng.

### Bài tập 5 — Chọn cải tiến sau production

**Gợi ý:** nếu sự cố cho thấy thao tác lặp gây trả chỗ hai lần, ưu tiên cơ chế nhất quán, kiểm thử hồi quy và tín hiệu phát hiện. Nếu người dùng liên tục không tìm được nút hủy, bổ sung kiểm tra trải nghiệm và khả năng truy cập. Theo dõi tác động, không chỉ đếm số bài test mới.

## 24. Checklist cho Scrum Team hoặc đội dùng Kanban

### Khi làm rõ công việc

- [ ] Đã biết giá trị sản phẩm và người dùng của hạng mục chưa?
- [ ] Có phân loại dữ liệu nhạy cảm, quyền truy cập và nguy cơ lạm dụng không?
- [ ] Đã xác định tải, độ trễ hoặc hành trình nào cần mục tiêu hiệu năng chưa?
- [ ] Nhóm đã xét người dùng bàn phím, screen reader, phóng to và nhu cầu truy cập áp dụng chưa?
- [ ] Có hiểu các tín hiệu và phương án ứng phó quan trọng khi tính năng vận hành không?
- [ ] Các tiêu chí chấp nhận, DoD và SLO (nếu dùng) đã phân biệt rõ chưa?

### Khi phát triển và kiểm chứng

- [ ] Kiểm tra quyền ở nơi đáng tin, không chỉ ẩn điều khiển giao diện?
- [ ] Secrets và dữ liệu cá nhân được bảo vệ trong mã, test và log?
- [ ] Có kiểm thử các trường hợp lỗi, thao tác lặp, trạng thái đồng thời theo rủi ro?
- [ ] Kết quả thử tải có workload, môi trường, dữ liệu và mục tiêu rõ?
- [ ] Có xem latency percentile, lỗi và tính đúng dữ liệu, không chỉ CPU/trung bình?
- [ ] Luồng giao diện có thao tác được bằng bàn phím, focus đúng và thông báo lỗi dễ hiểu?
- [ ] Đã kết hợp kiểm tra a11y tự động với kiểm tra thủ công phù hợp?
- [ ] CI có tín hiệu đáng tin và những gate phản ánh tiêu chuẩn cần thiết?
- [ ] Các thành phần đã tích hợp và không phá hành vi hiện có theo DoD?

### Khi phát hành và vận hành

- [ ] Có phân biệt Increment Done, deploy, release và outcome?
- [ ] Có cơ chế mở/dừng, tương thích dữ liệu và phương án phục hồi phù hợp?
- [ ] Metric/log/trace không làm lộ thông tin nhạy cảm?
- [ ] Có tín hiệu phản ánh hành vi người dùng, không chỉ việc máy chủ trả lời?
- [ ] Cảnh báo quan trọng có người nhận và hành động cụ thể?
- [ ] Runbook hoặc quy trình ứng phó cần thiết đã được thử trong phạm vi an toàn?
- [ ] Có đường nhận phản hồi từ người dùng gặp rào cản khả năng truy cập?
- [ ] Lỗi/sự cố được đưa trở lại backlog và cải tiến DoD hoặc kiểm thử khi phù hợp?
- [ ] Công việc chất lượng được ưu tiên theo rủi ro, không luôn bị hoãn sau tính năng mới?
- [ ] Nhóm dùng số liệu để cải tiến, không để che lỗi hoặc quy trách nhiệm cá nhân đơn giản?

Checklist là **công cụ trao đổi và tự kiểm tra**, không phải bộ tiêu chí chứng nhận bảo mật, hiệu năng, WCAG hay an toàn vận hành. Mức kiểm chứng phải theo bối cảnh và tiêu chuẩn bắt buộc của tổ chức.

## 25. Kết luận

**Chất lượng liên tục** là đưa kỳ vọng về **bảo mật, hiệu năng, khả năng truy cập và vận hành** vào chính cách nhóm khám phá, thiết kế, xây dựng, kiểm chứng, bàn giao và cải tiến phần mềm. Bốn thuộc tính này ảnh hưởng trực tiếp đến việc người dùng có thể hoàn thành tác vụ một cách an toàn, thuận tiện và đáng tin hay không.

Các thực hành **shift left** giúp nhận diện rủi ro và sửa hiểu sai sớm; **shift right** tiếp tục cung cấp bằng chứng từ môi trường sử dụng thực. **Product Backlog, acceptance criteria, Definition of Done, CI/CD, kiểm thử theo rủi ro, quan sát production và phản hồi người dùng** liên kết thành một dòng học hỏi thay vì những khâu kiểm tra rời rạc.

Trong **AGILE_DEVELOPMENT**, Scrum có thể giúp giữ mục tiêu và cam kết chất lượng của Increment; Kanban làm minh bạch dòng công việc và rủi ro; XP tăng phản hồi kỹ thuật; DevOps/SRE hỗ trợ năng lực triển khai và vận hành. Không có một bộ công cụ duy nhất bảo đảm mọi thuộc tính chất lượng. Điều quan trọng là **mỗi phần giá trị được giao đều có bằng chứng chất lượng tương xứng rủi ro, có thể được sử dụng thực sự và giúp nhóm học để thay đổi an toàn hơn ở vòng tiếp theo**.
