# Thảo luận ước lượng theo nhóm bằng Planning Poker

## 1. Vì sao ước lượng cần một cuộc thảo luận?

Trong phát triển phần mềm, hai người đọc cùng một user story có thể hình dung hai phạm vi khác nhau. Lập trình viên giao diện nghĩ chỉ cần thêm nút; người làm backend nghĩ phải sửa phân quyền; người kiểm thử nhớ đến tình huống gửi yêu cầu lặp; người vận hành biết rằng triển khai có thể ảnh hưởng dữ liệu cũ. Nếu một người kết luận “ba ngày là xong” ngay lập tức, nhóm có thể tưởng đã thống nhất dù **chưa thống nhất điều thực sự cần hoàn thành**.

**Planning Poker** là kỹ thuật ước lượng cộng tác: mỗi người suy nghĩ **độc lập**, mọi người tiết lộ lựa chọn cùng lúc, rồi thảo luận vì sao các lựa chọn khác nhau. Kết quả quan trọng nhất là **hiểu biết chung về phạm vi, độ phức tạp, công sức và bất định**. Một giá trị ước lượng có ích chỉ xuất hiện sau khi nhóm cùng hiểu story.

Ví dụ, nền tảng học trực tuyến cần story:

> Là học viên đã đăng nhập, tôi muốn tiếp tục học từ vị trí đang dở để không phải tìm lại bài học.

Một người chọn 3 điểm vì nghĩ chỉ cần điều hướng đến liên kết cũ. Người khác chọn 13 điểm vì nghĩ phải đồng bộ tiến độ video giữa nhiều thiết bị. Chênh lệch này không đơn giản là “ai chấm đúng”, mà là tín hiệu cho câu hỏi **“Vị trí đang dở” có nghĩa gì trong nghiệp vụ?** Nếu chỉ lấy trung bình các con số, nhóm sẽ bỏ lỡ câu hỏi quyết định phạm vi.

Trong Agile, việc thảo luận user story và Product Backlog hỗ trợ giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục. Planning Poker có thể dùng khi nhóm làm Scrum, Kanban hoặc một cách phối hợp khác. **Scrum không bắt buộc Planning Poker hay story point**; đây là kỹ thuật tùy chọn phục vụ trao đổi và lập kế hoạch.

> **Ý chính:** Planning Poker hữu ích vì giúp phát hiện khác biệt trong cách hiểu công việc, không phải vì bộ thẻ có khả năng dự đoán tương lai.

## 2. Planning Poker giúp gì và không làm được gì?

| Planning Poker hữu ích để | Planning Poker không tự bảo đảm |
| --- | --- |
| Làm rõ những điều còn mơ hồ trong user story và tiêu chí chấp nhận | Mọi yêu cầu đã đầy đủ hoặc không thay đổi |
| Bộc lộ rủi ro kỹ thuật, kiểm thử, tích hợp và phụ thuộc | Mọi rủi ro được phát hiện đúng và đủ |
| So sánh kích thước tương đối của hạng mục theo quy ước nhóm | Một điểm tương ứng số giờ/ngày cố định |
| Nhận biết story quá lớn hoặc cần nghiên cứu thêm | Con số ước lượng là sự thật khách quan |
| Tạo căn cứ giao tiếp khi lập kế hoạch và dự báo | Ngày bàn giao chắc chắn chỉ dựa trên điểm story |

Đừng dùng Planning Poker để thi xem ai đoán đúng, để xếp hạng nhân viên hoặc để quản lý áp một con số lên nhóm. **Điểm ước lượng không đo giá trị kinh doanh**: story 8 điểm chưa chắc đáng làm trước story 3 điểm. Giá trị, rủi ro, mức khẩn cấp và mục tiêu sản phẩm quyết định thứ tự ưu tiên.

Phân biệt bốn hoạt động:

1. **Làm rõ nhu cầu:** hiểu ai hưởng lợi, những hành vi nào phải đúng và phạm vi nào được chọn.
2. **Ước lượng:** đánh giá tương đối mức lớn/nhỏ hoặc độ bất định của hạng mục.
3. **Dự báo:** dùng dữ liệu quá khứ, năng lực, điều kiện hiện tại để suy xét khả năng hoàn tất nhiều hạng mục.
4. **Cam kết và lập kế hoạch:** lựa chọn mục tiêu, công việc và cách phối hợp phù hợp với trách nhiệm của nhóm.

Khi stakeholder hỏi “Story 5 điểm bao giờ xong?”, câu trả lời cần dựa trên lịch sử hoàn tất, WIP, phụ thuộc, năng lực và độ bất định. Không có quy tắc Agile “một story point bằng một ngày”.

## 3. Các lá bài và cách hiểu story point

Nhiều nhóm dùng dãy số gần Fibonacci như **0, 1, 2, 3, 5, 8, 13, 21**, hoặc **0, 1, 2, 3, 5, 8, 13, 20, 40, 100**. Khoảng cách lớn dần phản ánh việc phân biệt 13 với 14 “đơn vị” thường không có ích khi công việc lớn và bất định cao.

| Thẻ | Cách dùng thường gặp | Lưu ý |
| --- | --- | --- |
| **0** | Gần như không phát sinh công việc hoặc vấn đề đã được giải quyết | Không được bỏ qua kiểm thử/triển khai bắt buộc |
| **1–3** | Tương đối nhỏ so với mốc tham chiếu của nhóm | Vẫn phải đạt các tiêu chí chất lượng |
| **5–8** | Lớn hơn do có nhiều biến thể, tích hợp hoặc kiểm thử | Không quy đổi tự động sang ngày |
| **13 trở lên** | Lớn hoặc còn nhiều điều chưa rõ so với story quen thuộc | Cân nhắc chia nhỏ, làm rõ, tạo spike |
| **?** | Chưa có đủ thông tin để chọn một giá trị có ý nghĩa | Ghi câu hỏi cần xác nhận |
| **☕** | Cần nghỉ ngắn để duy trì chất lượng thảo luận | Không phải cách thay thế quyết định |

**Story point** thường là một cách biểu thị kích thước tương đối, cân nhắc công sức, độ phức tạp và bất định theo quy ước nhóm. Nó **không phải đơn vị đo chuẩn hóa**, không phải giờ công và không phải giá trị mang lại cho người dùng. Một nhóm khác có thể chọn dãy số, cỡ áo S/M/L hoặc thời gian lý tưởng. Cơ chế tiết lộ đồng thời và trao đổi giả định vẫn hữu ích khi dùng thước đo khác.

Ngưỡng “từ 13 điểm phải tách” nếu có chỉ là **chính sách nội bộ**. Trong thực tế, nhóm cần xem story có thể hoàn tất, kiểm thử và bàn giao trong nhịp phù hợp hay không; kích thước thẻ chỉ giúp tạo tín hiệu để trao đổi.

### Vì sao cần mốc tham chiếu?

Thay vì hỏi “Story này mất mấy ngày?”, nhóm so sánh với những story đã hoàn tất:

| Story tham chiếu của một nhóm giả định | Điểm nội bộ | Lý do |
| --- | ---: | --- |
| Hiển thị trạng thái đã ghi danh từ API có sẵn | 2 | Luồng đơn giản, ít biến thể |
| Xem danh sách các khóa của tôi với phân quyền hiện có | 3 | UI, API và kiểm thử cơ bản |
| Ghi danh một khóa miễn phí, tránh bản ghi trùng | 5 | Có xử lý ghi dữ liệu, quy tắc và retry |
| Tích hợp một phương thức thanh toán có hợp đồng rõ | 8 | Nhiều trạng thái, hệ thống ngoài, kiểm thử phức tạp |

Những con số này **chỉ minh họa** và phải được hiệu chỉnh theo công việc đã Done của nhóm thực tế. Mốc tham chiếu nên bao gồm toàn bộ mức chất lượng cần có. Khi kiến trúc hoặc thành phần nhóm thay đổi nhiều, cần xem lại cách dùng mốc; không trộn quy ước mới với dữ liệu cũ như cùng một thước đo.

## 4. Chuẩn bị trước buổi Planning Poker

Một buổi ước lượng không hiệu quả khi Product Backlog chỉ có tiêu đề “Làm quản lý học viên”. Mỗi người sẽ tự tưởng tượng một hệ thống khác nhau. Trước khi mở thẻ, nên có:

- **Ai và vì sao:** người hưởng lợi, vấn đề và kết quả cần đạt.
- **Phạm vi:** những biến thể nào thuộc story hiện tại, điều gì để sau.
- **Tiêu chí chấp nhận:** luồng chính, ngoại lệ quan trọng và cách biết đã làm đúng.
- **Definition of Done (DoD):** tiêu chuẩn chất lượng chung khi review, kiểm thử, tích hợp và vận hành.
- **Phụ thuộc:** dữ liệu, hệ thống, nhóm, quyết định nghiệp vụ hoặc nhà cung cấp bên ngoài.
- **Tham chiếu:** vài story quen thuộc đã hoàn tất với kích thước khác nhau.

Không cần viết đầy đủ đặc tả trước buổi họp. Một phần giá trị của Planning Poker là tìm được câu hỏi còn thiếu; nếu câu trả lời có thể làm thay đổi hẳn phạm vi, hãy làm rõ **trước khi ép nhóm gán số**.

### Ai nên tham gia?

Những người trực tiếp tạo increment và chịu trách nhiệm chất lượng cần có tiếng nói. Đó có thể là lập trình viên, người kiểm thử, chuyên gia trải nghiệm, dữ liệu hoặc vận hành tùy công việc và cấu trúc nhóm. Trong **Scrum**, Developers chịu trách nhiệm ước lượng/kích thước hóa Product Backlog Items; Product Owner làm rõ giá trị và phạm vi, Scrum Master có thể hỗ trợ sự phối hợp.

Người có quyền quản lý nên tránh công bố một con số trước và yêu cầu mọi người giải thích vì sao “không theo”. Với nhóm làm việc từ xa, có thể dùng công cụ số để chọn thẻ riêng và lật cùng lúc. Mục đích là nghe được các quan điểm khác nhau trước khi mọi người bị ảnh hưởng bởi lựa chọn đầu tiên.

### Quy ước cần thống nhất

Nhóm nên biết mình chấm theo **kích thước toàn bộ story đạt DoD** hay theo một đơn vị khác, có dùng thẻ hỏi chấm hay không, khi nào tách story, cách ghi giả định và giới hạn thời gian thảo luận cho một hạng mục. Các quy tắc này phục vụ phối hợp, không phải bộ quy định cứng áp cho mọi nhóm Agile.

## 5. Quy trình một vòng Planning Poker

Một quy trình thực hành có thể gồm tám bước:

1. **Giới thiệu story.** Product Owner hoặc người hiểu nghiệp vụ nêu nhu cầu, giá trị, điều kiện chính và phạm vi.
2. **Đặt câu hỏi.** Nhóm làm rõ hành vi, dữ liệu, phân quyền, kiểm thử, tích hợp và các giả định có thể ảnh hưởng kích thước.
3. **Chọn thẻ độc lập.** Mỗi người so sánh với mốc tham chiếu mà chưa nói điểm của mình.
4. **Lật thẻ cùng lúc.** Ghi nhận giá trị cao/thấp và độ phân tán.
5. **Nghe lý do chênh lệch.** Người chọn thấp và cao giải thích điều họ đã tính đến hoặc loại khỏi phạm vi.
6. **Cập nhật hiểu biết.** Làm rõ quy tắc, ghi rủi ro, điều chỉnh acceptance criteria hoặc đề xuất chia lát.
7. **Bỏ phiếu lại nếu cần.** Khi đã có hiểu biết mới, mọi người chấm lại theo cùng phạm vi.
8. **Ghi kết quả.** Lưu ước lượng mà nhóm chấp nhận cùng các giả định; nếu chưa đủ thông tin thì giữ trạng thái chưa ước lượng.

~~~mermaid
flowchart TD
    A["Story được ưu tiên"] --> B["Làm rõ giá trị, phạm vi, DoD"]
    B --> C["Chọn thẻ độc lập"]
    C --> D["Lật cùng lúc"]
    D --> E{"Chênh lệch cần thảo luận?"}
    E -->|"Không"| F["Ghi ước lượng + giả định"]
    E -->|"Có"| G["Nghe lý do thấp/cao"]
    G --> H{"Đã đủ rõ và đủ nhỏ?"}
    H -->|"Có"| C
    H -->|"Chưa"| I["Làm rõ / chia story / spike"]
    I --> J["Ước lượng lại sau khi có thông tin"]
~~~

**Người điều phối** có thể hỏi:

- “Bạn chọn 3 vì giả định đã có sẵn API hay đã có dữ liệu?”
- “Người chọn 13 đang tính đến tình huống nào mà cả nhóm bỏ sót?”
- “Nếu phần đồng bộ đa thiết bị không thuộc story này, kích thước thay đổi ra sao?”
- “Đã tính công việc kiểm thử, phân quyền và xử lý lỗi theo DoD chưa?”
- “Điều chưa biết có thể được trả lời bằng một cuộc trao đổi nghiệp vụ hay cần spike?”

Thảo luận nên tập trung vào **bằng chứng và giả định**, không công kích năng lực cá nhân. Người mới trong nhóm có thể nhầm cách tính, nhưng cũng có thể phát hiện điều nguy hiểm mà người quen hệ thống bỏ sót.

## 6. Ví dụ đầy đủ: story “Tiếp tục học”

### 6.1. Story ban đầu

> Là học viên đã có quyền học, tôi muốn nhấn “Tiếp tục học” để quay lại phần học phù hợp khi mở trang khóa.

Hệ thống đã có trang khóa học và lưu tiến độ cơ bản. Chưa rõ “tiếp tục” nghĩa là mở bài tiếp theo, tiếp tục đúng giây trong video hay đồng bộ trạng thái theo thời gian thực trên nhiều thiết bị.

### 6.2. Vòng bỏ phiếu đầu

| Thành viên | Chọn | Lý do |
| --- | ---: | --- |
| Người làm UI | 3 | Chỉ thêm nút và điều hướng bằng API tiến độ sẵn có |
| Người làm backend | 8 | Cần quy tắc trạng thái hoàn tất và kiểm tra quyền học |
| Người kiểm thử | 13 | Lo đồng bộ hai thiết bị, lỗi mạng và xung đột tiến độ |
| Người tích hợp | 5 | Luồng chính đơn giản nhưng cần hồi quy và xử lý dữ liệu cũ |

Lấy trung bình rồi làm tròn không giải quyết vấn đề: **bốn người đang ước lượng bốn phiên bản khác nhau của cùng một câu mô tả**.

### 6.3. Cuộc trao đổi làm rõ

Nhóm hỏi Product Owner và người hiểu nghiệp vụ:

- **Bài cần mở là bài nào?** Bài sau bài đã hoàn thành cuối cùng theo quy tắc của khóa.
- **Có tiếp tục đúng giây trong video không?** Chưa nằm trong lát đầu.
- **Đồng bộ tiến độ đa thiết bị thì sao?** Chỉ dùng nguồn tiến độ đang lưu; nâng cấp đồng bộ chính xác là nhu cầu khác cần xem xét.
- **Nếu học viên đã học xong bài cuối?** Hiển thị trạng thái hoàn thành, không mở đường dẫn không tồn tại.
- **Nếu học viên không còn quyền truy cập?** Không cấp quyền dù có liên kết trực tiếp.
- **Dữ liệu cũ có trường hợp thiếu trạng thái?** Có; phải thống nhất fallback và kiểm thử.

Nhóm viết lại story và tiêu chí chấp nhận để giới hạn phạm vi:

> “Học viên có quyền truy cập và tiến độ hợp lệ có thể mở bài tiếp theo từ trang khóa; trường hợp chưa bắt đầu, đã hoàn tất và dữ liệu thiếu trạng thái được xử lý rõ. Chưa bao gồm đồng bộ vị trí xem video giữa các thiết bị.”

Đây là **thay đổi cách hiểu**, không phải thao túng điểm xuống thấp.

### 6.4. Vòng bỏ phiếu tiếp

Sau trao đổi, nhóm chọn lần lượt **5, 5, 8, 5**. Người chọn 8 nêu nguy cơ fallback cho dữ liệu cũ. Nhóm kiểm tra thêm trường hợp đó và điều chỉnh tiêu chí chấp nhận. Cuối cùng, giả sử cả nhóm **chấp nhận 5 điểm** theo mốc nội bộ, với ghi chú các giả định về dữ liệu tiến độ; hoặc vẫn có thể chọn 8 nếu rủi ro không giảm. **Không có quy tắc phải lấy số đông.**

Kết quả tốt của phiên không phải “đã tìm ra con số chính xác”. Đó là: phạm vi rõ ràng hơn, rủi ro được nêu đúng, khả năng chia story dễ hơn và ước lượng phản ánh **một hiểu biết chung**.

### 6.5. Acceptance criteria minh họa sau khi làm rõ

~~~gherkin
Feature: Tiếp tục học từ trang khóa

  Scenario: Học viên có bài tiếp theo
    Given học viên đã đăng nhập và có quyền truy cập khóa
    And có bài học đã hoàn thành theo quy tắc
    When học viên mở trang khóa
    Then hệ thống hiển thị hành động "Tiếp tục học"
    And hành động mở đúng bài tiếp theo được phép học

  Scenario: Học viên đã hoàn thành bài cuối
    Given học viên có quyền học và đã hoàn tất bài cuối
    When học viên mở trang khóa
    Then hệ thống hiển thị trạng thái hoàn thành
    And không dẫn đến bài học không tồn tại

  Scenario: Người dùng không có quyền học
    Given người dùng không có quyền truy cập khóa
    When người dùng yêu cầu mở liên kết trực tiếp đến bài
    Then hệ thống từ chối truy cập nội dung bị hạn chế
~~~

Các tiêu chí trên là ví dụ theo một quy tắc giả định. Trong dự án thật phải xác nhận khái niệm “hoàn thành bài” với người có thẩm quyền. Planning Poker có thể làm lộ điểm mơ hồ, nhưng **không được dùng để tự sáng tác chính sách nghiệp vụ**.

## 7. Khi chưa thể đồng thuận: làm rõ, chia nhỏ hoặc spike

Không đồng thuận ngay không phải thất bại. Ép số cho đủ biểu mẫu khi vấn đề cốt lõi chưa rõ mới làm ước lượng vô nghĩa.

| Tình huống | Hành động hợp lý | Cần tránh |
| --- | --- | --- |
| Có người biết hạn chế của hệ thống cũ | Nghe giải thích và kiểm tra bằng chứng | Loại ý kiến vì “đa số chọn thấp” |
| Thiếu quy tắc nghiệp vụ có thể đổi phạm vi | Ghi câu hỏi, xác nhận với người có thẩm quyền | Tự suy rồi cam kết |
| Story quá lớn, gồm nhiều biến thể có giá trị | Chia theo hành vi người dùng hoặc trường hợp nghiệp vụ | Tách thành các story riêng “database/API/UI” |
| Rủi ro kỹ thuật chưa đo được | Thực hiện spike có câu hỏi và giới hạn | Chọn ước lượng rất lớn thay cho tìm hiểu |
| Chỉ còn khác biệt nhỏ về cách nhìn, phạm vi đã hiểu chung | Dùng quy tắc chấp nhận điểm của nhóm, kết thúc buổi | Cãi lâu về chênh lệch không ảnh hưởng quyết định |
| Chưa biết story có còn đáng làm | Quay lại ưu tiên và giả thuyết giá trị | Ước lượng chi tiết ý tưởng chưa có nhu cầu |

**Spike** là việc học hỏi có câu hỏi và timebox. Ví dụ: “Trong tối đa một ngày, thử khả năng nhận callback thanh toán gửi lặp của dịch vụ trên môi trường sandbox và viết khuyến nghị idempotency”. Đầu ra là **bằng chứng để quyết định**, chưa phải một tính năng production đã đạt Definition of Done.

Nếu có mã thử từ spike, chỉ đưa vào sản phẩm thật sau khi xem xét thiết kế, chất lượng, kiểm thử và yêu cầu an toàn. Khi spike hoàn tất, nhóm có thể ước lượng lại story theo thông tin mới.

### Đồng thuận không có nghĩa ai cũng phải chọn giống từ vòng đầu

Đồng thuận nghĩa là nhóm **hiểu cùng một phạm vi** và có thể chấp nhận giá trị như giả định lập kế hoạch. Không nên xem im lặng là đồng ý hoặc bắt người chọn điểm cao xin lỗi vì làm con số lớn hơn. Nhóm có thể thống nhất trước chính sách khi chênh lệch nhỏ, nhưng cần đặc biệt lắng nghe tiếng nói nêu nguy cơ về dữ liệu, bảo mật và chất lượng.

## 8. Ước lượng toàn bộ story, không chỉ công việc viết mã

Khi dùng story point cho story tạo ra increment, hãy ước lượng **công việc cần để đáp ứng tiêu chí chấp nhận và DoD**, gồm thiết kế cần thiết, lập trình, kiểm thử, tích hợp, review và yêu cầu vận hành liên quan.

Những câu hỏi nên kiểm tra:

- Luồng chính và tình huống biên đã được diễn đạt rõ?
- Có xác thực, phân quyền, bảo mật hoặc tính toàn vẹn dữ liệu cần xử lý?
- Có thay đổi schema, dữ liệu cũ hoặc cách triển khai nhiều phiên bản?
- Có tích hợp hệ thống ngoài, hợp đồng API và tình huống retry?
- Kiểm thử đơn vị, tích hợp và hồi quy cần ở mức nào?
- Có yêu cầu quan sát lỗi, triển khai giới hạn hoặc phương án khôi phục?
- Phụ thuộc vào nhóm khác có chắc chắn và có thể kiểm soát?
- Có một điều chưa biết đủ lớn để thay đổi hẳn phương án không?

Các thành viên không nên chỉ chấm điểm **phần việc của chuyên môn mình** rồi cộng cơ học điểm các task. Story tạo giá trị là kết quả hoàn chỉnh từ góc nhìn người dùng; việc tích hợp và kiểm thử giữa các phần cũng là công việc.

**Đừng thổi phồng điểm vì một cá nhân nghỉ phép hoặc bận việc khác.** Kích thước tương đối được hiểu theo cách làm bình thường của nhóm; năng lực hiện tại, việc đột xuất và lịch nghỉ được tính khi dự báo/lập kế hoạch. Nếu nhóm chọn một cách ước lượng khác, cần thống nhất định nghĩa để không trộn điểm với lịch.

Không được cắt bỏ yêu cầu bắt buộc về bảo mật, dữ liệu và an toàn chỉ để giảm số điểm. Có thể thu hẹp **biến thể nghiệp vụ** hoặc **nhóm người dùng thử**, nhưng increment vẫn phải đủ chất lượng khi bàn giao.

## 9. Sử dụng Planning Poker trong Scrum, Kanban và XP

### Scrum

Planning Poker thường xuất hiện khi **refine Product Backlog Items** hoặc chuẩn bị Sprint Planning. Refinement giúp làm rõ, chia nhỏ và ước lượng công việc; nó là **hoạt động liên tục**, không phải một sự kiện Scrum có timebox riêng được quy định bắt buộc.

Trong Scrum, **Developers chịu trách nhiệm kích thước/ước lượng PBI**, Product Owner hỗ trợ giải thích giá trị và phạm vi, Scrum Master có thể giúp nhóm làm việc hiệu quả. Chọn PBI cho Sprint cần dựa trên Sprint Goal, mức ưu tiên, năng lực và hiểu biết công việc, **không chỉ dựa trên cộng tổng điểm**.

Khi bắt đầu làm story, nhóm vẫn có thể phát hiện điều mới. Developers thích ứng Sprint Backlog khi cần hướng tới Sprint Goal; chất lượng theo DoD phải được giữ. Không nên coi “đã nhận 20 điểm” là lý do bỏ kiểm thử hoặc giảm tiêu chuẩn để báo cáo đúng số.

### Kanban

Nhóm dùng Kanban có thể áp dụng Planning Poker để làm rõ những hạng mục nhiều bất định, nhưng không bắt buộc chấm mọi ticket. Khi các hạng mục đủ nhỏ và nhất quán, dữ liệu **throughput, cycle time, WIP, work item age** có thể hỗ trợ dự báo trực tiếp. Quan trọng là chính sách luồng rõ, hạn chế việc đang làm dở và khả năng nhìn thấy blocker.

### XP

Thực hành kỹ thuật XP như kiểm thử tự động, tích hợp liên tục, refactoring và phối hợp sát giữa các thành viên giúp giảm bất định khi xây dựng. Từ đó, nhóm có thể hoàn tất story nhỏ và đổi hướng an toàn hơn khi có phản hồi người dùng. Kỹ thuật tốt không biến Planning Poker thành phép đo chính xác tuyệt đối; nó làm **việc giao phần mềm đã ước lượng đáng tin hơn**.

## 10. Từ ước lượng đến dự báo: hai phép tính khác nhau

Ước lượng story là một đánh giá tương đối. Dự báo lịch bàn giao phải xét **dữ liệu hoàn tất thực tế**, bối cảnh và mức bất định. Nếu nhóm dùng story point, một ví dụ có thể là:

| Sprint đã hoàn tất | Điểm của các story đạt DoD |
| --- | ---: |
| Sprint 1 | 18 |
| Sprint 2 | 22 |
| Sprint 3 | 16 |
| Sprint 4 | 20 |

Trung bình lịch sử bằng:

~~~text
(18 + 22 + 16 + 20) / 4 = 19 điểm mỗi Sprint
~~~

Nếu backlog gần có 57 điểm với cùng quy ước và phạm vi tương tự, phép chia sơ bộ:

~~~text
57 / 19 = 3 Sprint
~~~

**Ba Sprint chỉ là một dự báo thô trong ví dụ giả định**, không phải cam kết ngày hoàn thành. Số điểm thực tế có thể biến động vì độ lớn story, lỗi khẩn, phụ thuộc, thành viên nghỉ, yêu cầu mới hoặc thay đổi DoD. Dùng thêm dữ liệu dao động qua nhiều Sprint có thể đưa ra khoảng dự báo thực tế hơn; không tự gán mức xác suất tin cậy khi chưa có phương pháp và dữ liệu phù hợp.

Nếu story 8 điểm chỉ mới hoàn thành phần API mà chưa tích hợp và đạt DoD, không nên ghi nhận như một increment Done. Quy tắc đếm phải nhất quán để dữ liệu có ý nghĩa.

### Dự báo không dùng điểm

Một nhóm Kanban có throughput tương đối ổn định của các hạng mục nhỏ có thể dự báo bằng **số hạng mục hoàn tất theo thời gian**. Với dữ liệu đủ dài, phân phối throughput hoặc cycle time có thể dùng cho mô phỏng Monte Carlo hoặc dự báo theo phân vị, kèm các giả định rõ ràng. Planning Poker vẫn có ích để **làm rõ công việc khó**, dù nhóm không dùng story point cho dự báo.

### Những điều không được suy từ story point

- **Không có phép đổi cố định:** 5 điểm không tương đương 5 ngày.
- **Không có chuẩn so nhóm:** 20 điểm của nhóm A không “nhiều hơn” 15 điểm của nhóm B.
- **Không dùng để xếp hạng cá nhân:** năng suất không thể đo bằng số điểm do chính người làm chọn.
- **Không chứng minh giá trị sản phẩm:** hoàn tất nhiều điểm không có nghĩa học viên học tốt hơn.
- **Không thay thế dữ liệu chất lượng:** story Done phải đáp ứng DoD và kết quả người dùng.

## 11. Khi nào nên dùng Planning Poker, khi nào không cần?

| Bối cảnh | Lựa chọn hữu ích |
| --- | --- |
| Story mới có nhiều quy tắc nghiệp vụ và tích hợp | Planning Poker để bộc lộ giả định |
| Story nhỏ lặp lại, giống mốc tham chiếu đã Done | Xác nhận nhanh hoặc cách định cỡ thường lệ |
| Epic quá lớn, chưa biết lát đầu nào có giá trị | Khám phá nhu cầu và story mapping trước |
| Chưa biết nguyên nhân lỗi sau phát hành | Triage/điều tra, có thể spike, rồi mới ước lượng sửa |
| Tích hợp nhà cung cấp mới chưa rõ hợp đồng | Spike để giảm rủi ro kỹ thuật |
| Nhóm có nhiều ticket nhỏ tương tự nhau và dữ liệu ổn định | Dùng throughput/cycle time cho dự báo |
| Stakeholder cần quyết định làm gì trước | Xem giá trị, mức khẩn cấp, rủi ro; điểm không thay thế ưu tiên |

Ước lượng chi tiết cả roadmap nhiều tháng khi các giả thuyết còn thay đổi có thể gây lãng phí. Nên ưu tiên làm rõ hạng mục **sắp có khả năng được thực hiện**, rồi cập nhật khi có phản hồi.

## 12. Phản mẫu phổ biến cần tránh

| Phản mẫu | Tác hại | Cách cải thiện |
| --- | --- | --- |
| Người quản lý công bố điểm trước | Neo suy nghĩ, giảm ý kiến độc lập | Chọn riêng rồi lật đồng thời |
| Lấy trung bình khi điểm chênh lệch | Che giấu giả định khác nhau | Nghe lý do thấp/cao, làm rõ và bỏ phiếu lại |
| Luôn chọn điểm cao nhất “cho chắc” | Điểm phình lên mà rủi ro chưa rõ | Nêu rủi ro, chia story hoặc spike |
| Ép mọi người chọn cùng điểm quản lý muốn | Tạo đồng thuận giả | Để nhóm tự đánh giá và cho phép chọn dấu hỏi |
| Chấm story chưa có tiêu chí chấp nhận | Mỗi người tưởng tượng một yêu cầu | Làm rõ nhu cầu và ranh giới trước |
| Chỉ tính thời gian lập trình | Bỏ sót tích hợp, kiểm thử, bảo mật | Xét toàn bộ công việc đạt DoD |
| Cộng điểm task thành điểm story | Đếm trùng và bỏ qua tích hợp | Ước lượng story hoàn chỉnh theo mốc tương đối |
| Coi spike là tính năng đã giao | Nhầm học hỏi với sản phẩm vận hành | Ghi rõ đầu ra nghiên cứu và công việc delivery tiếp theo |
| Dùng velocity thưởng/phạt | Khuyến khích thổi phồng điểm | Dùng số liệu để dự báo và cải tiến nội bộ |
| Tranh luận rất lâu về 5 hay 8 khi chưa rõ chính sách | Tốn thời gian nhưng không giảm rủi ro | Hỏi người có thẩm quyền, timebox rồi ước lượng lại |

Một môi trường Agile tốt cho phép người phát hiện rủi ro nói thẳng, ngay cả khi nó khiến ước lượng lớn hơn hoặc phải xem lại kế hoạch. Nếu số điểm càng thấp càng được khen, mọi người dễ che giấu việc khó; nếu điểm càng cao càng được coi là làm nhiều, mọi người dễ thổi phồng. Cả hai đều làm mất khả năng dự báo trung thực.

## 13. Bài thực hành: điều phối một vòng Planning Poker

**Tình huống:** Nền tảng học trực tuyến có story:

> “Là giảng viên phụ trách khóa, tôi muốn xem danh sách học viên chưa bắt đầu bài đầu để có thể hỗ trợ đúng lúc.”

Hệ thống lưu đăng ký và lượt mở bài, nhưng chưa có quy tắc rõ cho tài khoản đang chờ duyệt và trường hợp học viên đã mở bài nhưng chưa hoàn thành. Ba thành viên chọn các thẻ **3, 8, 13**.

### Nhiệm vụ cho người học

1. Nêu năm câu hỏi làm rõ trước khi chấm: ai được xem, “chưa bắt đầu” nghĩa gì, tính theo thời gian nào, học viên chờ ghi danh có nằm trong danh sách không, dữ liệu được cập nhật ra sao?
2. Đề xuất giả định khiến mỗi người chọn 3, 8 hoặc 13 thay vì chọn điểm trung bình.
3. Chọn một lát giá trị nhỏ đủ để giảng viên sử dụng, có phân quyền.
4. Viết ba tiêu chí chấp nhận cho luồng chính, dữ liệu thiếu và quyền xem.
5. Quyết định khi nào bỏ phiếu lại, khi nào tách story, khi nào cần spike.
6. Giải thích vì sao “Story 5 điểm chắc chắn xong trong 5 ngày” là kết luận không hợp lệ.

### Một phương án tham khảo

**Làm rõ:** Tạm giả định “chưa bắt đầu” là học viên **đã ghi danh có hiệu lực nhưng chưa có sự kiện mở bài đầu**. Cần xác nhận với người hiểu nghiệp vụ; học viên đã mở nhưng chưa hoàn thành có thể không thuộc nhóm “chưa bắt đầu”. Giảng viên chỉ được xem học viên của khóa mình được phân công.

**Lý do chênh lệch:** Người chọn 3 cho rằng chỉ lọc dữ liệu có sẵn; người chọn 8 tính thêm phân quyền và quy tắc chờ duyệt; người chọn 13 giả định cần đồng bộ nhiều hệ thống và gửi nhắc học tự động. Nhóm cần phân biệt phạm vi trước khi chọn điểm.

**Lát đầu:** Giảng viên đã đăng nhập và có quyền quản lý khóa xem được các học viên ghi danh hiệu lực nhưng chưa mở bài đầu tính tại thời điểm truy vấn. Chức năng gửi nhắc tự động, biểu đồ xu hướng và phân tích dự đoán để sau.

**Tiêu chí chấp nhận minh họa:**

~~~gherkin
Feature: Danh sách học viên chưa bắt đầu bài đầu

  Scenario: Giảng viên có quyền xem khóa
    Given giảng viên đã đăng nhập và phụ trách khóa
    And có học viên ghi danh hiệu lực nhưng chưa mở bài đầu
    When giảng viên mở danh sách chưa bắt đầu
    Then hệ thống liệt kê các học viên đủ điều kiện theo quy tắc

  Scenario: Học viên chưa có sự kiện mở bài
    Given học viên đã ghi danh hợp lệ và chưa có sự kiện mở bài đầu
    When hệ thống tạo danh sách
    Then trạng thái được diễn giải theo quy tắc "chưa bắt đầu" đã thống nhất

  Scenario: Người không có quyền
    Given người dùng không có quyền quản lý khóa
    When người dùng yêu cầu danh sách học viên của khóa
    Then hệ thống từ chối truy cập thông tin học viên
~~~

Khi các câu hỏi đã được trả lời và mọi người chấm **cùng phạm vi**, nhóm bỏ phiếu lại. Nếu phần nhắc học tự động lớn, tách thành story khác. Nếu chưa biết độ tin cậy của sự kiện mở bài, cân nhắc spike để kiểm tra dữ liệu; không tự gọi nghiên cứu đó là increment đã hoàn thành.

**Về thời hạn:** 5 điểm phản ánh kích thước tương đối theo mốc của nhóm. Dự báo ngày hoàn thành còn cần lịch sử delivery, năng lực hiện tại, WIP, phụ thuộc, rủi ro và DoD.

## 14. Checklist cho nhóm trước khi kết thúc phiên

- [ ] Story có **người hưởng lợi, giá trị, phạm vi và tiêu chí chấp nhận** đủ rõ để cùng thảo luận?
- [ ] Nhóm thống nhất **đơn vị/ý nghĩa thẻ** và có mốc tham chiếu phù hợp?
- [ ] Người trực tiếp thực hiện và bảo đảm chất lượng đều có cơ hội đóng góp?
- [ ] Thẻ được chọn **độc lập** rồi **lật đồng thời**?
- [ ] Chênh lệch được dùng để tìm **giả định, rủi ro và phụ thuộc**, không để phán xét?
- [ ] Nhóm biết khi nào cần **hỏi thêm, chia story, tạo spike hoặc chưa ước lượng**?
- [ ] Ước lượng đã bao gồm công việc cần đạt **acceptance criteria và Definition of Done**?
- [ ] Kết quả được ghi cùng **giả định quan trọng và giới hạn hiểu biết**?
- [ ] Điểm được dùng để hỗ trợ dự báo có điều kiện, **không chuyển thành số ngày cố định**?
- [ ] Không dùng story point/velocity để so sánh năng suất cá nhân hoặc các nhóm khác?
- [ ] Sau khi bàn giao, nhóm có dùng dữ liệu thực tế để cải thiện cách chia story, làm rõ và dự báo?

**Ghi nhớ:** Planning Poker tạo giá trị ở **cuộc thảo luận xung quanh các lá bài**. Khi một story được hiểu cùng cách, nhóm có thể chọn ước lượng tương đối có ích, nhận diện phần cần chia nhỏ và tránh cam kết dựa trên giả định giấu kín. Kết hợp kỹ thuật này với phản hồi người dùng, số liệu luồng công việc và thực hành Scrum, Kanban, XP giúp Agile **bàn giao giá trị tăng dần, dự báo thận trọng và cải tiến liên tục**.
