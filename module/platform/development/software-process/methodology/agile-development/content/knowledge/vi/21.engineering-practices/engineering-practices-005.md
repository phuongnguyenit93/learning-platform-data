# ATDD và thống nhất tiêu chí nghiệm thu trước khi triển khai

## 1. ATDD giải quyết vấn đề gì trong phát triển phần mềm?

Một nhóm phát triển nền tảng học trực tuyến nhận user story: “Là học viên, tôi muốn đăng ký khóa học để bắt đầu học ngay”. Product Owner hiểu “đăng ký thành công” nghĩa là học viên đủ điều kiện được cấp quyền học; lập trình viên nghĩ API chỉ cần lưu một bản ghi; người kiểm thử dự kiến rằng mọi khóa đều phải qua bước xét duyệt. Nếu ba người không trao đổi trước khi triển khai, mỗi người có thể làm đúng theo cách hiểu của mình nhưng **sản phẩm chung lại sai nghiệp vụ**.

**Acceptance Test-Driven Development (ATDD, phát triển dẫn dắt bằng kiểm thử chấp nhận)** là cách cộng tác để các bên **thống nhất những ví dụ cụ thể về hành vi được chấp nhận trước khi triển khai**, sau đó dùng chúng định hướng phát triển và kiểm chứng kết quả. Các ví dụ có thể trở thành kiểm thử chấp nhận tự động hoặc được xác minh bằng phương thức phù hợp. ATDD không chỉ là chuyện “QA viết test sớm hơn”, mà là quá trình hình thành **hiểu biết chung** giữa người nghiệp vụ, người phát triển và người kiểm thử.

ATDD hỗ trợ mục tiêu của Agile Development: mô tả nhu cầu bằng user story, làm rõ Product Backlog, xây phần mềm tăng dần, nhận phản hồi sớm và cải tiến. Nó đặc biệt hữu ích khi:

- Một cụm từ nghiệp vụ có nhiều cách hiểu, như “đã ghi danh”, “đủ điều kiện”, “hoàn thành bài học”.
- Lỗi trong quy tắc phân quyền, dữ liệu hoặc thanh toán có tác động lớn.
- Nhiều người cùng làm các thành phần của một hành trình người dùng.
- Nhóm thường phát hiện yêu cầu thiếu hoặc phải sửa nhiều sau khi demo.
- Hạng mục cần có bằng chứng rõ ràng để biết khi nào hoàn thành, thay vì “trông có vẻ chạy”.

> **Nguyên tắc cốt lõi:** Trước khi xây giải pháp, hãy cùng trả lời **“Những ví dụ nào chứng minh hành vi này đáp ứng nhu cầu?”**. Kiểm thử sau đó biến hiểu biết chung thành phản hồi có thể lặp lại.

Một story đã qua ATDD vẫn có thể không tạo ra giá trị như kỳ vọng: tiêu chí chấp nhận chứng minh **đúng theo hành vi đã thống nhất**, không tự chứng minh **giả thuyết sản phẩm đã đúng**. Nhóm vẫn cần quan sát người dùng và đo outcome sau khi bàn giao.

## 2. Phân biệt tiêu chí nghiệm thu, kiểm thử chấp nhận và kết quả kinh doanh

Các thuật ngữ sau thường bị dùng thay thế nhau dù trả lời những câu hỏi khác nhau.

| Khái niệm | Câu hỏi chính | Ví dụ ở nền tảng học |
| --- | --- | --- |
| **Nhu cầu/user story** | Ai cần khả năng nào và vì sao? | Học viên muốn ghi danh khóa miễn phí để bắt đầu học |
| **Quy tắc nghiệp vụ** | Trong điều kiện nào hệ thống phải xử lý ra sao? | Khóa cần xét duyệt không cấp quyền trước khi được duyệt |
| **Acceptance criteria (tiêu chí chấp nhận/nghiệm thu)** | Điều kiện nào để story cụ thể được xem là đáp ứng yêu cầu? | Ghi danh hợp lệ tạo đúng một đăng ký hiệu lực, không đăng ký trùng |
| **Acceptance example/test** | Với dữ liệu và hành động cụ thể, kết quả kỳ vọng là gì? | Khi học viên gửi lại yêu cầu, hệ thống vẫn có một đăng ký hiệu lực |
| **Definition of Done (DoD)** | Increment phải đạt mức chất lượng chung nào? | Được tích hợp, kiểm thử phù hợp, bảo vệ dữ liệu, không còn lỗi chặn |
| **Outcome sản phẩm** | Người dùng có thực sự đạt lợi ích mong muốn? | Nhiều học viên đủ điều kiện ghi danh và mở bài đầu thành công hơn |
| **Release decision** | Có nên cung cấp Increment cho nhóm người dùng nào và lúc nào? | Bật chức năng cho một nhóm khóa học sau khi điều kiện vận hành đáp ứng |

**Acceptance criteria không thay thế DoD.** Một story có thể đáp ứng quy tắc “đăng ký không trùng” nhưng chưa qua kiểm tra phân quyền hoặc tích hợp bắt buộc thì vẫn chưa đạt tiêu chuẩn hoàn tất chung. Ngược lại, pipeline xanh không chứng minh rằng yêu cầu nghiệp vụ đã được diễn đạt đúng ngay từ đầu.

### “Nghiệm thu” trong ATDD không đồng nghĩa buổi ký duyệt cuối dự án

ATDD hướng đến **tiêu chuẩn được đồng thuận từ trước** và kiểm tra trong quá trình làm. Một tổ chức vẫn có thể cần User Acceptance Testing (UAT), đánh giá pháp lý hoặc phê duyệt vận hành theo hợp đồng; các hoạt động ấy không tự động được thay thế bởi ATDD. Điều quan trọng là tránh đợi đến UAT mới lần đầu phát hiện mọi người hiểu khác nhau về hành vi.

### Mức độ cụ thể tạo ra khác biệt

- Mơ hồ: “Học viên ghi danh thành công”.
- Tốt hơn: “Học viên đủ điều kiện có thể ghi danh khóa đang mở”.
- Có thể kiểm chứng: “Với khóa miễn phí đang mở, không cần xét duyệt, học viên đã đăng nhập và chưa có đăng ký hiệu lực: khi xác nhận ghi danh, hệ thống tạo đúng một đăng ký hiệu lực và cho phép truy cập bài học theo chính sách”.

Mức thứ ba cho biết **điều kiện ban đầu, hành động và kết quả quan sát được**. Từ đó, nhóm có thể hỏi về các trường hợp biên trước khi viết mã.

## 3. ATDD là hoạt động cộng tác, không phải trách nhiệm riêng của QA

Một kỹ thuật thực hành thường dùng là cuộc trao đổi **Three Amigos** – ba góc nhìn cần xuất hiện, không nhất thiết luôn là đúng ba cá nhân:

1. **Góc nhìn nghiệp vụ/sản phẩm:** vấn đề người dùng, giá trị mong muốn, quy tắc, ngoại lệ và thứ tự ưu tiên.
2. **Góc nhìn phát triển:** tính khả thi, thiết kế, dữ liệu, hệ thống liên quan, phụ thuộc và các rủi ro kỹ thuật.
3. **Góc nhìn kiểm thử/chất lượng:** những cách hệ thống có thể sai, dữ liệu biên, khả năng quan sát kết quả và bằng chứng cần có.

| Góc nhìn | Câu hỏi điển hình | Đóng góp vào ATDD |
| --- | --- | --- |
| **Product Owner/đại diện nghiệp vụ** | “Khi nào học viên được cấp quyền thật sự?” | Xác nhận quy tắc, giá trị, tình huống và các quyết định vượt phạm vi |
| **Developers** | “Nếu hai yêu cầu đến cùng lúc thì sao?” | Bộc lộ phụ thuộc, thiết kế kiểm chứng được, đề xuất chia lát |
| **Tester/người có tư duy chất lượng** | “Nếu đã đăng ký, mất mạng, khóa đã đóng hoặc không có quyền thì sao?” | Phát hiện trường hợp biên và rủi ro bị bỏ sót |

Trong Scrum, Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả; Developers chịu trách nhiệm tạo Increment đạt Definition of Done. ATDD giúp những người này **hiểu cùng kết quả cần đạt**, nhưng không tạo một vai trò Scrum bắt buộc mới hay chuyển hết trách nhiệm chất lượng sang người kiểm thử.

### Người nghiệp vụ phải có quyền quyết định đúng phạm vi

Nếu câu hỏi “khóa này có cần duyệt hay không?” bị treo nhiều ngày, Developers có thể tự suy đoán hoặc bị chặn. Người đại diện nghiệp vụ cần sẵn sàng xác nhận các quy tắc trong phạm vi được ủy quyền, đồng thời có kênh hỏi người có thẩm quyền khi đụng đến chính sách pháp lý, tài chính hoặc sản phẩm.

Không nên biến Three Amigos thành nơi một người có chức danh cao áp đáp án còn những người khác chỉ nghe. Một nhận xét từ người kiểm thử về lỗi cấp quyền có thể quan trọng hơn sở thích trình bày màn hình của stakeholder.

### Đừng đợi họp định kỳ nếu có câu hỏi quan trọng

Three Amigos là **cách cộng tác**, không phải một cuộc họp Scrum có lịch cố định. Nhóm có thể tổ chức phiên ngắn khi refine một story, trao đổi ngay khi có phát hiện mới hoặc đưa một ví dụ trở lại để xác nhận. Mục đích là rút ngắn thời gian giữa **câu hỏi nghiệp vụ** và **quyết định có thể thực hiện**.

## 4. Từ user story đến ví dụ: quy trình ATDD có thể áp dụng

Một vòng ATDD thực dụng thường đi qua những bước sau. Thứ tự có thể lặp lại khi nhóm học thêm; không phải tài liệu phải hoàn tất một lần rồi đóng băng.

1. **Chọn một lát giá trị gần được thực hiện.** Xác định người dùng, vấn đề và mục tiêu; tránh bắt đầu bằng epic quá rộng.
2. **Khám phá các quy tắc và ví dụ.** Ba góc nhìn cùng nêu trường hợp thông thường, trường hợp biên, sai lệch và rủi ro.
3. **Làm rõ ranh giới phạm vi.** Điều gì thuộc story này, điều gì không, hệ thống nào có liên quan?
4. **Viết tiêu chí chấp nhận bằng ngôn ngữ chung.** Mô tả các kết quả quan sát được, không khóa chặt chi tiết lớp, database hoặc công nghệ UI.
5. **Biến ví dụ quan trọng thành kiểm thử.** Có thể tự động hóa ở tầng phù hợp; với phần cần quan sát của con người, xác định cách kiểm chứng thủ công có chủ đích.
6. **Quan sát kiểm thử chưa đạt trước khi triển khai hành vi.** Với kiểm thử tự động đã được xây, test cần thất bại vì hành vi chưa có hoặc chưa đúng, không vì lỗi cấu hình vô nghĩa.
7. **Xây giải pháp theo lát nhỏ, chạy kiểm thử lặp lại.** Kết hợp TDD ở cấp đơn vị nếu phù hợp; giữ bộ kiểm thử chấp nhận cung cấp phản hồi về hành vi.
8. **Kiểm tra DoD và Increment tích hợp.** Xác minh chất lượng chung, phân quyền, dữ liệu và điều kiện vận hành cần thiết.
9. **Trình diễn/trao đổi với người nghiệp vụ.** Kiểm tra ví dụ thực sự phản ánh cách sử dụng, không chỉ vì test suite đang xanh.
10. **Phát hành, quan sát và học hỏi khi phù hợp.** Dùng outcome để cập nhật Product Backlog và những tiêu chí của các lát tiếp theo.

~~~mermaid
flowchart TD
    A["User story + mục tiêu người dùng"] --> B["Three Amigos: khám phá quy tắc, rủi ro và ví dụ"]
    B --> C["Tiêu chí chấp nhận + ranh giới phạm vi"]
    C --> D["Kiểm thử chấp nhận cho các ví dụ quan trọng"]
    D --> E["Triển khai theo lát + TDD khi phù hợp"]
    E --> F["Kiểm tra tự động và tích hợp"]
    F --> G{"Đạt acceptance criteria và DoD?"}
    G -->|"Chưa"| H["Làm rõ sai lệch, sửa và chạy lại"]
    H --> E
    G -->|"Đạt"| I["Increment có thể sử dụng"]
    I --> J["Phản hồi người dùng, outcome và backlog"]
    J -. "Bằng chứng mới" .-> B
~~~

**Đầu ra có giá trị nhất của vòng khám phá** không nhất thiết là một file Gherkin dài. Đó có thể là quyết định: “Khóa cần xét duyệt không thuộc story đầu, vì chúng ta sẽ thử luồng ghi danh tự động trước”, cùng câu hỏi còn mở và tiêu chí rõ cho lát được chọn.

## 5. Ví dụ xuyên suốt: ghi danh vào khóa học miễn phí

### 5.1. Bối cảnh và giả định

Giả sử nền tảng học có hai loại khóa miễn phí:

- **Khóa không cần duyệt:** học viên đủ điều kiện ghi danh và được cấp quyền học ngay.
- **Khóa cần xét duyệt:** học viên gửi yêu cầu, chờ quyết định; chỉ được cấp quyền sau khi được duyệt hợp lệ.

Học viên đăng nhập bằng tài khoản riêng; hệ thống phải bảo vệ dữ liệu cá nhân, không tạo nhiều đăng ký hiệu lực trùng cho cùng một học viên và khóa. Đây là **quy tắc giả định cho bài học**. Trong sản phẩm thật, các bên phải xác nhận chính sách ghi danh, trạng thái quyền và cách xử lý yêu cầu bị từ chối.

Một epic ban đầu có thể là “Quản lý đăng ký học”. Nhóm chia thành những lát có giá trị:

| Lát | Hành vi người dùng có thể nhận | Những gì chưa làm trong lát này |
| --- | --- | --- |
| **Story A** | Ghi danh khóa miễn phí đang mở, không cần duyệt | Khóa có xét duyệt, thanh toán, gửi thông báo nâng cao |
| **Story B** | Gửi yêu cầu và xem trạng thái chờ duyệt | Công cụ duyệt nhiều cấp hoặc báo cáo nâng cao |
| **Story C** | Người có quyền duyệt xử lý yêu cầu; học viên được cấp quyền sau phê duyệt | Tự động hóa mọi chính sách ngoại lệ |
| **Story D** | Xem lịch sử ghi danh và trạng thái rõ ràng | Phân tích dữ liệu quy mô lớn |

ATDD giúp quyết định **lát nào đủ hiểu để làm**, tránh gộp toàn bộ epic thành một yêu cầu khó nghiệm thu. Những lát còn phụ thuộc nhau cần được lên kế hoạch để mỗi Increment thực sự tích hợp và dùng được trong phạm vi đã chọn.

### 5.2. User story được chọn

> Là học viên đã đăng nhập và đủ điều kiện, tôi muốn ghi danh một khóa miễn phí đang mở không cần duyệt để có thể truy cập bài đầu ngay mà không phải nhờ nhân viên hỗ trợ.

Mục tiêu gần là luồng **ghi danh và mở bài đầu** với trạng thái chính xác, không phải “xây màn hình đăng ký” hoặc “tạo endpoint”. Người nghiệp vụ xác nhận một số điều kiện:

- Học viên phải có danh tính được xác thực.
- Khóa còn nhận ghi danh và không yêu cầu xét duyệt.
- Một học viên chỉ có **tối đa một đăng ký hiệu lực** cho cùng khóa.
- Quyền truy cập bài học được cấp theo trạng thái đăng ký đã xác nhận.
- Người ngoài không được ghi danh thay người khác bằng cách sửa ID trong request.

Nhóm chưa quyết định có cần gửi email, cách xử lý hủy đăng ký hoặc thay đổi khóa sau khi ghi danh. Các vấn đề này được ghi là **ngoài phạm vi/chờ làm rõ**, không tự suy thành yêu cầu mới.

## 6. Buổi Three Amigos: hỏi gì trước khi lập trình?

Giả sử phiên làm rõ tập trung vào Story A. Người tham gia có thể bắt đầu bằng cách cùng xem ba ví dụ: một học viên mới ghi danh thành công, học viên gửi yêu cầu lại vì mạng chậm và người không có quyền thử truy cập khóa.

| Câu hỏi khám phá | Vì sao cần hỏi? | Một quyết định minh họa |
| --- | --- | --- |
| “Đang mở” nghĩa là chưa đến hạn, còn chỗ hay cả hai? | Dễ tạo quy tắc khác nhau giữa UI và API | Khóa nhận ghi danh khi trạng thái OPEN và các ràng buộc đang có đều hợp lệ |
| Học viên đã ghi danh mà gửi lại thì sao? | Retry hoặc nhấn nhiều lần gây trùng dữ liệu | Không tạo đăng ký hiệu lực mới, trả trạng thái hiện có |
| Nếu hai yêu cầu đến cùng lúc? | Cách kiểm tra rồi ghi đơn giản có thể bị race condition | Bảo vệ bất biến ở tầng lưu trữ/transaction phù hợp |
| Có thể ghi danh thay tài khoản khác qua API không? | Rủi ro vượt quyền và lộ dữ liệu | Xác định người học từ ngữ cảnh xác thực, kiểm tra quyền ở máy chủ |
| Trạng thái nào tạo quyền mở bài đầu? | “Đã gửi yêu cầu” dễ bị hiểu thành “đã được chấp nhận” | Chỉ trạng thái ACTIVE mới cho truy cập trong ví dụ này |
| Khóa đã đóng ghi danh thì sao? | Happy path không đủ | Từ chối yêu cầu mới với phản hồi phù hợp |
| Nếu ghi dữ liệu thành công nhưng phản hồi mạng thất lạc? | Người dùng sẽ gửi lại, cần idempotency | Request lặp phải đọc được kết quả hiện hữu mà không sinh bản ghi mới |
| Hệ thống cần lưu dấu vết gì? | Hỗ trợ điều tra, vận hành, nghĩa vụ dữ liệu | Có tín hiệu chẩn đoán cần thiết, không ghi log token hoặc dữ liệu nhạy cảm |

### Phân biệt ba loại thông tin

**Sự thật đã xác nhận:** chính sách khóa miễn phí không cần duyệt cho phép học ngay sau khi ghi danh hợp lệ.

**Giả thuyết cần xác minh:** người học bỏ dở vì thông báo trạng thái không rõ.

**Quyết định thiết kế cần Developers nghiên cứu:** dùng unique constraint, transaction và cơ chế retry nào để bảo vệ chống trùng trong kiến trúc hiện tại.

ATDD giúp phát hiện cả ba loại thông tin, nhưng **không để cuộc họp thay thế kiểm chứng kỹ thuật hoặc nghiên cứu người dùng**.

## 7. Ví dụ tốt được viết như thế nào?

Một ví dụ chấp nhận nên trả lời ba câu hỏi dễ quan sát:

1. **Given – điều kiện ban đầu:** hệ thống/người dùng đang ở trạng thái nào?
2. **When – hành động hoặc sự kiện:** điều gì xảy ra?
3. **Then – kết quả kỳ vọng:** người dùng hoặc hệ thống có thể quan sát kết quả nào?

Không bắt buộc dùng Gherkin; bảng ví dụ hoặc lời văn cụ thể cũng có thể hiệu quả. **Gherkin** hữu ích khi nhóm muốn ghi các ví dụ bằng ngôn ngữ chung và có khả năng nối chúng với kiểm thử tự động.

### 7.1. Gherkin cho luồng ghi danh

~~~gherkin
Feature: Ghi danh khóa miễn phí không cần xét duyệt
  Là học viên đủ điều kiện
  Tôi muốn ghi danh khóa đang mở
  Để có thể bắt đầu học theo quyền được cấp

  Scenario: Ghi danh lần đầu thành công
    Given học viên đã đăng nhập và đủ điều kiện
    And khóa miễn phí đang mở và không cần xét duyệt
    And học viên chưa có đăng ký hiệu lực cho khóa
    When học viên gửi yêu cầu ghi danh cho khóa
    Then hệ thống có đúng một đăng ký hiệu lực cho học viên và khóa
    And học viên được cấp quyền học theo chính sách
    And trạng thái hiển thị là "Đã ghi danh"

  Scenario: Gửi lại yêu cầu khi đã có đăng ký hiệu lực
    Given học viên đã có một đăng ký hiệu lực cho khóa
    When học viên gửi lại yêu cầu ghi danh cùng khóa
    Then hệ thống không tạo thêm đăng ký hiệu lực
    And kết quả cho biết học viên đã ghi danh

  Scenario: Khóa đã đóng ghi danh
    Given học viên đã đăng nhập và chưa ghi danh khóa
    And khóa không còn nhận ghi danh
    When học viên gửi yêu cầu ghi danh
    Then hệ thống không tạo đăng ký hiệu lực mới
    And hiển thị kết quả từ chối phù hợp

  Scenario: Không được ghi danh thay tài khoản khác
    Given người dùng A đã đăng nhập
    And người dùng A không được phép quản lý đăng ký của người dùng B
    When người dùng A thử gửi yêu cầu ghi danh thay người dùng B
    Then hệ thống từ chối thao tác trái quyền
    And không tạo đăng ký hiệu lực cho người dùng B
~~~

Các tình huống trên mô tả **hành vi có thể kiểm chứng**, không quy định endpoint nào, dùng framework UI nào hoặc phải viết class gì. Những chi tiết kỹ thuật cần cho test tự động sẽ được xác định khi triển khai bộ kiểm thử ở cấp phù hợp.

### 7.2. Tránh cụ thể quá mức ở chi tiết không phải nghiệp vụ

Ví dụ kém ổn định:

> “Khi click nút CSS selector .button-blue:nth-child(2), React component gọi setState ba lần và database insert đúng vào bảng enrollment_v2.”

Ví dụ đó phụ thuộc mạnh vào cách lập trình. Nếu nhóm refactor giao diện hoặc lưu trữ mà hành vi người dùng không đổi, kiểm thử sẽ thất bại vô ích.

Ví dụ tốt hơn:

> “Khi học viên đủ điều kiện xác nhận ghi danh, hệ thống tạo một đăng ký hiệu lực duy nhất và cho phép mở bài học theo chính sách.”

Trong bài kiểm thử tự động, đôi khi phải dùng selector hoặc truy vấn cụ thể; **chi tiết triển khai nên nằm trong lớp hỗ trợ kiểm thử**, không chiếm chỗ của ngôn ngữ nghiệp vụ trong tiêu chí chấp nhận.

### 7.3. Một ví dụ không thay thế toàn bộ đặc tả

Gherkin giúp minh họa những quy tắc quan trọng nhưng không thể đảm bảo mọi trường hợp đã được nghĩ đến. Nếu dữ liệu học có thời hạn, có thanh toán hoặc điều kiện tiên quyết, các bên cần thêm ví dụ. Tốt hơn nên có **một số ví dụ được chọn có chủ đích** thay vì hàng trăm scenario trùng lặp tạo cảm giác đầy đủ giả.

## 8. Dùng bảng ví dụ để thấy các biến thể và trường hợp biên

Khi nhiều điều kiện kết hợp, bảng quyết định giúp các bên phát hiện những trường hợp thiếu trước khi mã hóa.

### Bảng quy tắc minh họa cho đăng ký khóa không cần duyệt

| Đã xác thực | Đủ điều kiện | Khóa nhận ghi danh | Đã có đăng ký ACTIVE | Kết quả mong muốn |
| --- | --- | --- | --- | --- |
| Không | — | Có | Không | Không ghi danh; yêu cầu xác thực theo chính sách |
| Có | Không | Có | Không | Từ chối theo lý do đủ điều kiện; không cấp quyền mới |
| Có | Có | Không | Không | Không tạo đăng ký mới |
| Có | Có | Có | Không | Tạo đúng một đăng ký hiệu lực; cấp quyền theo chính sách |
| Có | Có | Có | Có | Không tạo thêm đăng ký; trả trạng thái đã ghi danh |

**Dấu “—” nghĩa là điều kiện phía sau không cần xét trong trường hợp đó**, không phải dữ liệu tùy ý có thể bỏ kiểm tra an toàn. Trật tự kiểm tra cụ thể và thông tin lỗi được trả về cần tuân thủ chính sách tránh lộ dữ liệu.

Một bảng như vậy hữu ích vì nêu ra các câu hỏi:

- Nếu khóa đóng sau khi học viên đã ghi danh, **quyền học cũ** còn không?
- Nếu học viên không còn đủ điều kiện sau khi đã ACTIVE, có thu hồi quyền không?
- Nếu hệ thống nhận hai request đồng thời từ cùng học viên, có còn giữ bất biến không?
- Nếu một yêu cầu đang PENDING, gửi lại request nên trả PENDING hay tạo yêu cầu mới?

Những câu hỏi vượt phạm vi story hiện tại phải được **ghi rõ và chuyển đến người quyết định**, không tự gán ngầm một kết quả.

### Ví dụ bảng Scenario Outline để giảm trùng lặp

~~~gherkin
Scenario Outline: Không tạo đăng ký mới khi điều kiện ghi danh không thỏa
  Given học viên đã đăng nhập với trạng thái đủ điều kiện "<eligibility>"
  And khóa có trạng thái ghi danh "<course_status>"
  And học viên chưa có đăng ký cho khóa
  When học viên yêu cầu ghi danh
  Then hệ thống không tạo đăng ký hiệu lực nếu điều kiện không hợp lệ

  Examples:
    | eligibility | course_status |
    | NOT_ELIGIBLE | OPEN          |
    | ELIGIBLE     | CLOSED        |
~~~

Trong dự án thật, có thể viết kết quả kỳ vọng riêng cho từng hàng nếu lý do từ chối và thông báo khác nhau. Scenario Outline không phải mục tiêu tự thân; chỉ dùng khi bảng giúp người đọc **hiểu sự khác biệt**, không che giấu ý nghĩa.

## 9. Làm sao biết bộ tiêu chí chấp nhận đã “đủ tốt” để bắt đầu?

Không tồn tại danh sách bắt buộc áp cho mọi user story. Có thể dùng một số câu hỏi chất lượng trong refinement:

| Tiêu chí | Câu hỏi kiểm tra |
| --- | --- |
| **Gắn với giá trị** | Ví dụ có giúp xác nhận người dùng đạt điều họ cần không? |
| **Cụ thể** | Given/When/Then hoặc mô tả tương đương có thể hiểu mà không đoán? |
| **Có thể quan sát** | Kết quả có thể xác nhận qua UI, API, dữ liệu hoặc dấu vết hợp lệ? |
| **Có ranh giới** | Điều gì thuộc story và điều gì chưa được hứa làm? |
| **Bao phủ rủi ro chính** | Có luồng thành công, thất bại, dữ liệu biên, quyền và lỗi quan trọng? |
| **Không trói vào triển khai** | Refactor mã/đổi giao diện không làm mất ý nghĩa nghiệp vụ của ví dụ? |
| **Có người xác nhận** | Quy tắc nghiệp vụ do người có thẩm quyền làm rõ, không do test tự đặt? |
| **Có thể thực hiện** | Nhóm biết phần nào cần làm, phần nào cần spike hoặc phụ thuộc ngoài? |
| **Phù hợp DoD** | Không có giả định rằng test chấp nhận xanh là đủ bỏ kiểm thử chung? |

Nếu câu hỏi quan trọng còn chưa được trả lời, có thể giữ story ở trạng thái cần làm rõ hoặc thực hiện **spike có timebox** để giảm bất định. Không cần ép mọi ý tưởng ở xa phải có toàn bộ test trước khi Product Owner quyết định có đáng ưu tiên không.

### Phân biệt “đủ rõ” với “không còn bất định”

Đủ rõ để bắt đầu là **những người thực hiện hiểu phạm vi và cách xác nhận kết quả**, còn những rủi ro quan trọng đã được nhận diện ở mức chấp nhận được. Khi triển khai, nhóm vẫn có thể phát hiện điều mới và quay lại người nghiệp vụ.

ATDD không yêu cầu đóng băng yêu cầu. Ngược lại, nó giúp **những thay đổi trong hiểu biết được thể hiện rõ** bằng ví dụ mới hoặc tiêu chí điều chỉnh.

## 10. Chuyển ví dụ thành kiểm thử tự động có giá trị

Một ví dụ chấp nhận là **đặc tả hành vi có thể kiểm chứng**. Nó không bắt buộc phải chạy ở tầng giao diện để có giá trị. Tùy kiến trúc và rủi ro, có thể kiểm tra tại service, API, integration hoặc end-to-end.

| Tầng kiểm tra | Ví dụ dùng cho story ghi danh | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Unit test / TDD** | Quy tắc khóa đóng không cho ghi danh; trạng thái chuyển đúng | Rất nhanh, giúp thiết kế từng bước | Không chứng minh truy cập API hoặc transaction thật |
| **Service/component acceptance test** | Với đầu vào/đối tượng cụ thể, service trả trạng thái nghiệp vụ đúng | Phản hồi nhanh, gần ngôn ngữ nghiệp vụ | Có thể dùng fake, chưa thấy sai lệch hạ tầng |
| **API integration test** | Request ghi danh tạo đúng một đăng ký trong database và kiểm soát quyền | Kiểm tra hợp đồng và dữ liệu thật hơn | Tốn thời gian thiết lập môi trường |
| **Contract test** | Bên dùng API hiểu đúng trạng thái ACTIVE/PENDING/REJECTED | Giảm sai lệch giữa các nhóm | Không đủ để xác minh toàn bộ hành trình |
| **End-to-end UI test** | Học viên ghi danh rồi mở bài đầu qua giao diện | Kiểm chứng đường đi trọng yếu của người dùng | Thường chậm và nhạy thay đổi UI |
| **Kiểm tra bảo mật/đồng thời** | Không ghi danh thay tài khoản; hai request đồng thời không tạo trùng | Bảo vệ bất biến quan trọng | Cần dữ liệu và môi trường thích hợp |

### Chọn tầng thấp nhất vẫn cung cấp bằng chứng cần thiết

Nếu cần chứng minh thuật toán xác định bài tiếp theo đúng, unit test thường là đủ cho quy tắc thuần. Nếu cần chứng minh **không cấp quyền học sai khi gọi API trực tiếp**, một test chỉ ở lớp UI là chưa đủ. Nếu cần chứng minh hai request không tạo dữ liệu trùng, unit test với repository giả có thể bỏ sót transaction hoặc race condition.

ATDD không đồng nghĩa “tự động hóa mọi scenario qua trình duyệt”. Một số ít kiểm thử end-to-end cho luồng quan trọng, cùng những kiểm thử nhanh ở tầng thấp hoặc tích hợp phù hợp, thường cho phản hồi **nhanh và đáng tin hơn**.

### Khi nào chưa thể tự động hóa?

Một số ví dụ cần đánh giá con người, như “học viên có hiểu thông điệp chờ duyệt không?” hoặc một quyết định tuân thủ cần thẩm định chuyên môn. Nhóm vẫn có thể:

- Ghi rõ tiêu chí và cách quan sát/đánh giá.
- Xác định ai xác nhận và bằng chứng nào cần lưu.
- Tự động hóa phần có thể kiểm tra khách quan.
- Không gọi phần chưa được kiểm chứng là đã tự động hóa.

ATDD hướng đến **tính kiểm chứng và hiểu biết chung**, không phải tỷ lệ test tự động cao bằng mọi giá.

## 11. Minh họa một acceptance test ở cấp API

Giả sử hệ thống có giao diện HTTP cho chức năng ghi danh. Một kiểm thử chấp nhận ở tầng API có thể được mô tả theo **hợp đồng giả định**, không phụ thuộc framework cụ thể:

~~~text
Given:
  - Học viên A đã được xác thực
  - Khóa K là khóa miễn phí, đang mở, không cần duyệt
  - A chưa có đăng ký hiệu lực cho K

When:
  - A gửi yêu cầu ghi danh khóa K
  - A gửi lặp lại yêu cầu vì không chắc phản hồi lần đầu đã nhận

Then:
  - Cả hai lần đều có kết quả nghiệp vụ nhất quán
  - Trong dữ liệu chỉ có một đăng ký ACTIVE cho (A, K)
  - A có quyền mở bài đầu theo chính sách
  - Một học viên B khác không có thêm quyền hoặc dữ liệu từ thao tác này
~~~

### Bằng chứng kiểm thử cần thu thập

Trong bộ kiểm thử tự động, có thể kiểm tra:

1. **Phản hồi hợp đồng:** trạng thái HTTP và body mang ý nghĩa nghiệp vụ đã thống nhất. Không mặc định phải là một mã status nhất định nếu API chưa có hợp đồng.
2. **Bất biến dữ liệu:** truy vấn ở môi trường test xác nhận chỉ một đăng ký hiệu lực cho cặp học viên–khóa.
3. **Quyền truy cập:** học viên đủ điều kiện mở được nội dung; người không có quyền vẫn bị chặn.
4. **Thử lại và đồng thời:** trường hợp gửi lặp tuần tự **khác** trường hợp hai request tới đồng thời; nếu rủi ro quan trọng, cần kiểm tra cả hai.
5. **Khả năng lặp lại test:** fixture được tạo và dọn phù hợp, không dùng thông tin thật hoặc giả định thứ tự test khác.

Không nên để một test chỉ khẳng định “HTTP 200” rồi kết luận toàn bộ hành trình đã được nghiệm thu. Mã phản hồi xanh có thể đi kèm dữ liệu sai, quyền học không được cấp hoặc đăng ký trùng.

### Tách ngôn ngữ nghiệp vụ khỏi code điều khiển test

Trong các framework thực thi Gherkin, step definition có thể chuyển “khóa đang mở và không cần duyệt” thành thao tác chuẩn bị dữ liệu, “học viên ghi danh” thành lời gọi API và “có một đăng ký hiệu lực” thành assertion. Người nghiệp vụ cần đọc được các ví dụ mà không phải hiểu cách set up database.

Nhóm nên xây **lớp hỗ trợ kiểm thử** vừa đủ để tránh lặp code. Tuy nhiên, abstraction quá mức cũng có thể khiến test khó hiểu và tạo một “ngôn ngữ test” không còn gần với nghiệp vụ.

## 12. Dùng kiểm thử chấp nhận để dẫn dắt triển khai theo lát

Một vòng phát triển ATDD có thể diễn ra như sau:

1. Three Amigos thống nhất scenario “ghi danh khóa miễn phí đang mở”.
2. Nhóm tạo hoặc mô tả kiểm thử chấp nhận cho scenario; nếu tự động hóa trước, xác nhận test hiện **chưa đạt đúng vì thiếu hành vi**.
3. Developers dùng các vòng **Red–Green–Refactor của TDD** để xây quy tắc nhỏ hơn, như kiểm tra trạng thái khóa, trạng thái học viên và điều kiện trùng.
4. Tích hợp service, API và dữ liệu; chạy lại acceptance test.
5. Thêm scenario “gửi lại yêu cầu” và phát hiện tình huống cần idempotency.
6. Bổ sung kiểm tra quyền ở máy chủ và scenario truy cập trái quyền.
7. Chạy những kiểm thử chất lượng bắt buộc khác theo DoD.
8. Nhận phản hồi từ người nghiệp vụ và dữ liệu sử dụng trước khi mở rộng lát tiếp theo.

~~~mermaid
flowchart LR
    A["Ví dụ chấp nhận đã đồng thuận"] --> B["Acceptance test chưa đạt"]
    B --> C["TDD/unit tests cho quy tắc nhỏ"]
    C --> D["Triển khai và tích hợp"]
    D --> E["Acceptance test + DoD checks"]
    E --> F{"Hành vi và chất lượng đạt?"}
    F -->|"Chưa"| G["Phân tích lỗi/giả định và cập nhật"]
    G --> C
    F -->|"Đạt"| H["Increment dùng được + phản hồi"]
~~~

**Không phải lúc nào cần tự động hóa toàn bộ scenario trước khi viết dòng code đầu tiên.** Điều bắt buộc về mặt tư duy là **thống nhất cách nhận biết thành công trước khi triển khai**, rồi biến nó thành bằng chứng sớm nhất có thể. Đôi khi nhóm cần dựng một cấu trúc tối thiểu để có môi trường chạy test, hoặc dùng test thủ công có chủ đích trước khi có năng lực tự động hóa.

### Chỉ sửa test sau khi làm rõ quy tắc

Nếu acceptance test đỏ sau khi code được thay đổi, hãy kiểm tra:

- **Mã sai** so với hành vi đã thống nhất?
- **Test sai** vì hiểu sai hoặc có assertion không thuộc nghiệp vụ?
- **Yêu cầu đã thay đổi** và cần người có thẩm quyền xác nhận?
- **Môi trường test không ổn định** khiến thất bại không liên quan?

Không được sửa expected result chỉ để làm pipeline xanh khi chưa hiểu vì sao hợp đồng hành vi thay đổi.

## 13. Tích hợp ATDD vào CI và Definition of Done

Khi một nhóm áp dụng ATDD nhưng chỉ chạy test trên máy của người kiểm thử, phản hồi vẫn có thể đến muộn và kết quả dễ khác nhau giữa máy. **Continuous Integration (CI)** giúp kiểm tra lại những cam kết hành vi khi mã được tích hợp.

Một pipeline minh họa cho nền tảng học:

~~~mermaid
flowchart TD
    A["Thay đổi nhỏ được tích hợp"] --> B["Build + static checks"]
    B --> C["Unit tests"]
    C --> D["Service/API acceptance tests"]
    D --> E["Integration + contract + security checks phù hợp"]
    E --> F["Một số E2E/smoke tests trọng yếu"]
    F --> G["Artifact đáp ứng các kiểm tra kỹ thuật cần thiết"]
    G --> H["Các điều kiện DoD khác và quyết định rollout"]
    B -. "Thất bại" .-> X["Điều tra, sửa và chạy lại"]
    C -. "Thất bại" .-> X
    D -. "Thất bại" .-> X
    E -. "Thất bại" .-> X
    F -. "Thất bại" .-> X
    X --> A
~~~

Không có yêu cầu ATDD phải dùng một công cụ hoặc thứ tự pipeline duy nhất. Các kiểm thử **nhanh, ổn định** thường nên phản hồi sớm; những kiểm tra cần hạ tầng phức tạp phải được bố trí sao cho vẫn bảo vệ rủi ro quan trọng.

### Test chấp nhận tự động chưa phải toàn bộ Definition of Done

Một DoD có thể yêu cầu:

- Kết quả chấp nhận đúng theo những tiêu chí đã thống nhất.
- Mã được review và tích hợp vào phiên bản chung.
- Kiểm thử hồi quy, phân quyền và bảo mật phù hợp được thực hiện.
- Hợp đồng API và dữ liệu được duy trì nhất quán.
- Các kịch bản vận hành, quan sát lỗi, migration hoặc rollback liên quan đã được giải quyết.
- Không còn lỗi chặn theo chính sách chất lượng chung.

**Một PBI chỉ Done khi đáp ứng DoD của sản phẩm**, không phải chỉ vì một vài bài kiểm thử chấp nhận đạt. Trong Scrum, Increment có thể được phát hành trước Sprint Review khi các điều kiện phát hành đã đáp ứng; Sprint Review không phải cổng kiểm thử/duyệt chất lượng thay thế DoD.

### Test thất bại và test flaky

Test tự động chỉ giúp ích nếu được tin cậy. Khi pipeline đỏ, nhóm cần phân biệt sai hành vi với lỗi dữ liệu test, môi trường, thời gian và tương tranh ngẫu nhiên. Không âm thầm tắt kiểm thử bắt buộc vì nó gây trễ; hãy sửa nguồn bất ổn, giảm phụ thuộc, dùng dữ liệu tái lập và phản ánh rủi ro minh bạch.

## 14. ATDD, BDD, TDD và UAT khác nhau như thế nào?

| Cách tiếp cận/hoạt động | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **ATDD** | Các vai trò cùng định nghĩa điều kiện chấp nhận **trước khi triển khai**, dùng ví dụ dẫn dắt phát triển | Xác nhận trạng thái ghi danh và quyền học qua các scenario |
| **BDD** | Khám phá và diễn đạt hành vi bằng **ngôn ngữ chung**, thường dùng ví dụ/Gherkin | “Given học viên đang chờ duyệt, When mở bài, Then chưa được cấp quyền” |
| **TDD** | Dùng các vòng **Red–Green–Refactor** nhỏ để phát triển và thiết kế mã | Test quy tắc chuyển trạng thái ACTIVE trước khi viết logic |
| **UAT** | Người dùng/nghiệp vụ kiểm tra mức phù hợp với nhu cầu trong bối cảnh nghiệm thu xác định | Đại diện đào tạo thử luồng ghi danh trước một đợt ra mắt |
| **Exploratory testing** | Người kiểm thử chủ động tìm hiểu, quan sát và khám phá sai lệch chưa được liệt kê | Thử nhiều chuỗi thao tác khác thường khi mất mạng |

Các thực hành **không loại trừ nhau**. BDD có thể là phong cách cộng tác và mô tả ví dụ trong ATDD. TDD giúp xây từng phần mã đáp ứng những hành vi đó. UAT và exploratory testing có thể tìm ra điều nhóm chưa dự đoán; khi phát hiện một quy tắc mới, hãy đưa nó trở lại câu chuyện nghiệp vụ và bổ sung test phù hợp.

### ATDD không phải “mọi thứ phải được viết dưới dạng Gherkin”

Một bảng quyết định hoặc sơ đồ trạng thái có thể giúp hiểu nghiệp vụ tốt hơn hàng chục dòng Given–When–Then. Nhóm nên chọn cách mô tả dễ kiểm chứng, phù hợp với người đọc. Gherkin là **công cụ biểu đạt**, không phải mục đích của ATDD.

### ATDD không phải kiểm thử thay cho sự tin tưởng

Thỏa thuận về tiêu chí chấp nhận giúp giảm hiểu sai; nó không thay thế sự phối hợp thường xuyên. Nếu một tiêu chí mới xuất hiện trong khi triển khai, người có trách nhiệm cần làm rõ **lý do và tác động phạm vi**, chứ không dùng danh sách test cũ làm “hợp đồng không bao giờ được đổi”.

## 15. Quản lý thay đổi tiêu chí chấp nhận trong Agile

Agile khuyến khích thích ứng với phản hồi; ATDD cần **ghi rõ khi giả định thay đổi** để không tạo tranh cãi “đúng theo test cũ nhưng sai nhu cầu mới”.

### Một tình huống thay đổi có căn cứ

Ban đầu, story chỉ bao gồm khóa miễn phí không cần duyệt. Trong Sprint Review, giảng viên cho biết nhiều khóa học thực tế cần xét duyệt trước khi cấp quyền. Đây có thể là:

- **Một story mới** cho luồng chờ duyệt, nếu việc triển khai hiện tại đúng phạm vi đã thống nhất.
- **Một lỗi** nếu khóa cần duyệt đã được mô tả trong tiêu chí của story hiện tại nhưng hệ thống lại cấp quyền ngay.
- **Một thay đổi phạm vi** nếu tổ chức quyết định bổ sung quy tắc mới cho hạng mục đang thực hiện.

Không thể phân loại chỉ dựa vào câu “hệ thống chưa làm được”. Cần so với yêu cầu/tiêu chí đã có và quyết định sản phẩm.

### Cách cập nhật một tiêu chí

1. Nêu bằng chứng hoặc tình huống mới.
2. Xác định quy tắc nghiệp vụ nào đã thay đổi, ai có quyền xác nhận.
3. Đánh giá tác động đến phạm vi, thiết kế, dữ liệu, kiểm thử và kế hoạch.
4. Chọn chia story, thêm PBI, sửa bug hoặc điều chỉnh tiêu chí hiện tại.
5. Cập nhật ví dụ và các kiểm thử tương ứng, giữ lịch sử/quyết định nếu cần để hiểu vì sao thay đổi.
6. Truyền đạt cho người thực hiện và stakeholder có liên quan.

### “Đóng băng tiêu chí” có thể làm giảm khả năng học hỏi

Không nên dùng ATDD như lý do từ chối mọi phản hồi mới. Ngược lại, **không được liên tục thay đổi hành vi trong im lặng** mà không trao đổi tác động với người thực hiện. Cân bằng đúng là phạm vi minh bạch, thay đổi có căn cứ và giữ chất lượng.

## 16. Những phản mẫu làm ATDD mất giá trị

| Phản mẫu | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| **Chỉ QA viết acceptance tests sau khi lập trình xong** | Các giả định sai chỉ phát hiện cuối chu kỳ | Cùng khám phá quy tắc và ví dụ trước triển khai |
| **Tiêu chí chỉ nói “hoạt động đúng”** | Không thể xác nhận kết quả, mỗi người hiểu khác | Dùng trường hợp cụ thể và kết quả quan sát được |
| **Product Owner không tham gia làm rõ** | Test mô tả suy đoán của kỹ thuật | Có người nghiệp vụ hiểu và có quyền xác nhận |
| **Three Amigos biến thành cuộc họp báo cáo** | Không tìm được quy tắc và trường hợp biên | Đi vào ví dụ, quyết định và câu hỏi chưa rõ |
| **Chỉ kiểm tra happy path** | Lỗi quyền, retry, dữ liệu biên vẫn lọt | Khám phá trường hợp âm/rủi ro cao |
| **Viết toàn bộ acceptance tests qua UI** | Bộ test chậm/flaky, feedback đến muộn | Chọn tầng thực thi theo hành vi và rủi ro |
| **Kiểm thử bám chặt chi tiết class/database** | Refactor gây test đỏ dù hành vi không đổi | Mô tả hợp đồng nghiệp vụ, giấu chi tiết trong test helpers |
| **Mock mọi hệ thống ngoài** | Không nhận ra sai hợp đồng, transaction, race condition | Bổ sung integration/contract tests phù hợp |
| **Lấy test xanh thay DoD** | Increment chưa đủ chất lượng nhưng bị gọi Done | Kiểm tra cả tiêu chí chấp nhận và chất lượng chung |
| **Gherkin dài nhưng không ai đọc hiểu** | Đặc tả trở thành mã khó bảo trì | Giữ ngôn ngữ chung và ví dụ ngắn, có ý nghĩa |
| **Không phân biệt bản thử với sản phẩm dùng được** | Stakeholder nghĩ prototype đã sẵn sàng | Gắn nhãn rõ khả năng và điều kiện chưa đạt |
| **Sửa expected result chỉ để hết đỏ** | Che giấu lỗi hoặc thay đổi yêu cầu chưa được chấp nhận | Làm rõ nguyên nhân trước khi chỉnh test |
| **Mọi ý tưởng xa đều viết test chi tiết** | Lãng phí trước khi biết có cần đầu tư | Ưu tiên các PBI sắp làm và rủi ro cần học sớm |
| **Bỏ phản hồi người dùng vì test đã đủ** | Xây đúng đặc tả nhưng không tạo outcome | Kết hợp Sprint Review, quan sát và đo giá trị thật |
| **Dùng số test/coverage để xếp hạng cá nhân** | Tạo kiểm thử hình thức, giấu rủi ro | Dùng dữ liệu để cải thiện chất lượng hệ thống |

### Một kiểm thử dễ chạy không phải lúc nào cũng đáng tự động hóa

Nếu một hành vi chỉ được sử dụng một lần, còn thay đổi liên tục và khó quan sát bằng máy, automation có thể đắt hơn giá trị nhận được. Ngược lại, các quy tắc quyền, tiền bạc, tính toàn vẹn dữ liệu hay luồng giao dịch thường lặp lại và rủi ro cao nên có bằng chứng tự động phù hợp. Ưu tiên **độ tin cậy của phản hồi và mức bảo vệ rủi ro**, không phải đếm số test.

## 17. Kết hợp ATDD với Scrum, Kanban, XP và Lean

### Với Scrum: tăng minh bạch của Product Backlog và Increment

ATDD hỗ trợ Product Backlog refinement và trao đổi trước Sprint Planning: người liên quan cùng hiểu một lát giá trị, cách nghiệm thu và những điều chưa rõ. Trong Sprint, Developers có thể dùng acceptance tests để kiểm tra tiến triển tới Increment đáp ứng DoD. Sprint Review tạo cơ hội kiểm tra kết quả thực tế và điều chỉnh Product Backlog; Sprint Retrospective giúp cải thiện cách khám phá và tự động hóa kiểm thử.

**Scrum không bắt buộc ATDD, Gherkin hay Three Amigos như một sự kiện riêng.** Dùng chúng khi giúp thực hiện thực nghiệm và tạo chất lượng tốt hơn, không thay các accountability và commitments của Scrum.

### Với Kanban: giảm việc chờ làm rõ và làm lại

ATDD có thể giảm trường hợp một PBI đang làm bị chặn vì thiếu câu trả lời nghiệp vụ. Nhóm có thể theo dõi **work item age**, **cycle time**, **WIP** và **throughput** để nhận ra hạng mục nào mất nhiều thời gian vì chờ thống nhất tiêu chí hoặc sửa sai lệch.

Nhưng đừng coi việc viết rất nhiều test là lý do mở hàng loạt PBI cùng lúc. Một luồng lành mạnh cần các story được làm rõ đúng lúc, chia đủ nhỏ và hoàn tất trước khi bắt đầu quá nhiều việc.

### Với XP: kết hợp acceptance examples và TDD

ATDD hỗ trợ **đúng hành vi nghiệp vụ**; TDD hỗ trợ **thiết kế và kiểm tra các bước mã nhỏ**. Kiểm thử tự động, CI, refactoring và hợp tác kỹ thuật của XP giúp giữ vòng phản hồi nhanh. Chúng bổ trợ nhau: một acceptance test có thể đỏ trong khi Developers dần đưa nhiều unit tests sang xanh, sau đó xác nhận toàn bộ lát khi tích hợp.

### Với Lean: giảm lãng phí do hiểu sai yêu cầu

Một cuộc trao đổi 20–40 phút làm rõ quy tắc trước khi xây có thể tránh nhiều ngày làm lại về sau. Không cần biến mọi hạng mục thành một chuỗi workshop dài; hãy chọn **những câu hỏi có nguy cơ làm đổi thiết kế hoặc giá trị**, giảm handoff, chờ đợi và viết test không mang thêm bằng chứng.

## 18. Đo hiệu quả ATDD bằng điều gì?

Một tổ chức có thể kiểm tra liệu cách làm mới có giúp **ít hiểu sai hơn và bàn giao đáng tin hơn**. Cần đặt số liệu trong bối cảnh, không suy quan hệ nhân quả chỉ từ vài lần quan sát.

| Chỉ báo | Câu hỏi cần trả lời | Cảnh báo |
| --- | --- | --- |
| **Tỷ lệ story bị mở lại vì hiểu sai nghiệp vụ** | Các ví dụ sớm có làm giảm làm lại? | Cần định nghĩa nguyên nhân, không chỉ đếm ticket reopen |
| **Thời gian chờ quyết định nghiệp vụ** | Hạng mục đang mắc ở bước hỏi đáp bao lâu? | Đừng thưởng vì “không hỏi”, điều đó có thể làm tăng suy đoán |
| **Lỗi sau phát hành liên quan đến quy tắc chấp nhận** | Có loại lỗi nào đáng ra đã phát hiện qua ví dụ? | Phân tích mức nghiêm trọng, loại lỗi và điều kiện đo |
| **Độ trễ phản hồi CI** | Từ lúc thay đổi đến lúc biết hành vi bị vi phạm mất bao lâu? | Tốc độ nhanh không có ích nếu test thiếu tin cậy |
| **Flaky tests** | Có test thất bại ngẫu nhiên khiến nhóm không còn tin tín hiệu? | Không tắt kiểm thử bắt buộc để làm số đẹp |
| **Cycle time** | Story từ lúc bắt đầu đến khi đạt Done có giảm? | Phạm vi và kích thước story phải so sánh được |
| **Outcome người dùng** | Tỷ lệ ghi danh và mở bài đầu thành công có cải thiện? | Không nhầm test pass hoặc button click với giá trị thực |

### Ví dụ cách quan sát một cải tiến

Giả sử trước khi thử ATDD, nhiều story ghi danh chỉ phát hiện thiếu quy tắc trạng thái trong UAT cuối đợt. Nhóm quyết định trong ba chu kỳ gần tiếp theo, khi chọn một PBI quan trọng, sẽ cùng người nghiệp vụ viết các ví dụ trường hợp chính, sai quyền và retry trước khi triển khai.

Sau đó nhóm so sánh:

- Số hạng mục phải sửa vì **thiếu quy tắc**.
- Thời gian chờ xác nhận nghiệp vụ.
- Lỗi liên quan đến dữ liệu và phân quyền sau tích hợp/phát hành.
- Khả năng hoàn tất Increment và outcome của học viên.

Nếu lỗi giảm nhưng số story quá khác nhau về độ khó hoặc nhóm đồng thời nâng cấp pipeline, cần diễn giải thận trọng. Một cách làm tốt có thể là **giữ ATDD cho những hạng mục nhiều bất định**, điều chỉnh mức chi tiết cho việc đơn giản, thay vì bắt mọi ticket qua nghi thức giống nhau.

## 19. Bài thực hành: thống nhất nghiệm thu trước khi triển khai tính năng chờ duyệt

### 19.1. Bối cảnh

Nền tảng học trực tuyến sắp mở loại khóa cần người phụ trách duyệt ghi danh. User story ban đầu:

> “Là học viên đã gửi đăng ký vào khóa cần duyệt, tôi muốn biết trạng thái của yêu cầu để biết khi nào mình được phép bắt đầu học.”

Product Owner nói rằng người học không nên chờ trong mơ hồ. Developers dự kiến dùng ba trạng thái PENDING, ACTIVE, REJECTED. Người kiểm thử lo ngại học viên có thể dùng liên kết trực tiếp để mở bài khi vẫn chờ duyệt. Một số học viên từng gửi lại yêu cầu nhiều lần khi mạng chậm.

**Giả định trong bài tập:** các trạng thái trên là hợp lệ cho khóa cần duyệt, chỉ ACTIVE mới cho phép mở nội dung bị hạn chế, và người có quyền duyệt đã được xác định. Những điều này cần được xác nhận với nghiệp vụ thực tế.

### 19.2. Nhiệm vụ

1. Tổ chức một cuộc trao đổi Three Amigos: viết ít nhất **sáu câu hỏi** cần trả lời trước khi triển khai.
2. Phân biệt **quy tắc đã xác nhận, giả thuyết và quyết định kỹ thuật**.
3. Xác định **một lát story nhỏ** và những chức năng để sau.
4. Viết **ba đến năm scenario** cho trạng thái PENDING, ACTIVE, REJECTED, thiếu quyền và gửi lại yêu cầu.
5. Chọn **tầng kiểm thử thích hợp** cho từng scenario; giải thích tại sao test UI không đủ chứng minh quyền.
6. Nêu trường hợp nào cần một **integration test với database thực tế hoặc tương đương**.
7. Lập một **ma trận truy vết** từ tiêu chí chấp nhận đến bằng chứng kiểm thử.
8. Đề xuất một **chỉ số outcome** và hai **guardrail** sau phát hành.
9. Nếu trong Sprint người nghiệp vụ đổi quy tắc “PENDING có thể xem bài giới thiệu công khai”, bạn sẽ cập nhật ví dụ và phạm vi thế nào?

### 19.3. Lời giải tham khảo: câu hỏi làm rõ

- Ai được gửi yêu cầu ghi danh và khi nào khóa còn nhận yêu cầu?
- Ai có quyền duyệt/từ chối và dấu vết quyết định cần lưu là gì?
- Trong trạng thái PENDING, học viên được xem nội dung công khai nào?
- Hệ thống cấp quyền ngay lúc duyệt hay cần bước xác nhận bổ sung?
- Người học nhận thông báo trạng thái qua kênh nào; có nghĩa vụ gửi email không?
- Nếu yêu cầu gửi lặp hoặc đến đồng thời, có được tạo hai yêu cầu PENDING không?
- Khi REJECTED, người học được gửi lại yêu cầu không, sau bao lâu, ai quyết định?
- Nếu quyết định duyệt đến khi khóa đã đóng, xử lý theo quy tắc nào?

Không cần trả lời tất cả trong một story. Những câu có tác động lớn đến **quyền truy cập, dữ liệu và khả năng kiểm chứng** cần được xác nhận trước khi chọn phạm vi hoàn tất.

### 19.4. Một lát story và Gherkin gợi ý

**Lát đầu:** học viên đủ điều kiện gửi yêu cầu vào khóa cần duyệt, nhận trạng thái PENDING, xem được trạng thái của chính mình và **chưa được cấp quyền mở bài bị hạn chế**. Công cụ duyệt nâng cao, email tùy chỉnh và chính sách gửi lại sau REJECTED có thể là hạng mục khác nếu chưa được quyết định.

~~~gherkin
Feature: Theo dõi yêu cầu ghi danh khóa cần xét duyệt

  Scenario: Gửi yêu cầu mới thành công
    Given học viên đã đăng nhập và đủ điều kiện gửi yêu cầu
    And khóa đang mở và cần xét duyệt
    And học viên chưa có yêu cầu còn hiệu lực
    When học viên gửi yêu cầu ghi danh
    Then hệ thống ghi nhận một yêu cầu ở trạng thái PENDING
    And học viên xem được trạng thái của chính mình
    And chưa được cấp quyền mở bài bị hạn chế

  Scenario: Gửi lại khi đang chờ duyệt
    Given học viên có yêu cầu PENDING cho khóa
    When học viên gửi lại yêu cầu ghi danh cùng khóa
    Then hệ thống không tạo thêm yêu cầu PENDING trùng
    And trạng thái trả về vẫn là PENDING

  Scenario: Chưa được duyệt thì không được mở nội dung hạn chế
    Given học viên có yêu cầu PENDING cho khóa
    When học viên dùng liên kết trực tiếp yêu cầu mở bài hạn chế
    Then hệ thống từ chối cấp nội dung hạn chế

  Scenario: Người khác không được xem yêu cầu của học viên
    Given người dùng A đã đăng nhập và không được quản lý yêu cầu của B
    When người dùng A yêu cầu trạng thái đăng ký của B
    Then hệ thống từ chối truy cập dữ liệu không được phép
~~~

Đối với trạng thái ACTIVE/REJECTED, nhóm cần một story hoặc tiêu chí riêng để xác nhận **ai thay đổi trạng thái**, các điều kiện duyệt, khả năng xem bài và thông báo tương ứng. Không tự ghép luồng xét duyệt đầy đủ vào lát đầu nếu mục tiêu là tạo khả năng gửi và theo dõi yêu cầu.

### 19.5. Ma trận truy vết mẫu

| Hành vi/tiêu chí | Bằng chứng ưu tiên | Lý do |
| --- | --- | --- |
| Gửi yêu cầu hợp lệ tạo PENDING | API acceptance + database integration test | Xác nhận hợp đồng và trạng thái lưu |
| Gửi lặp không tạo PENDING trùng | Integration test; kiểm thử request đồng thời nếu rủi ro cao | Unit test với fake có thể không thấy race condition |
| PENDING không mở bài hạn chế | API/security integration test | Quyền phải được bảo vệ phía máy chủ |
| Học viên thấy trạng thái của mình | API test + một UI test luồng quan trọng | Xác nhận cả trạng thái và khả năng hiểu trên giao diện |
| Người A không xem dữ liệu B | Security/API test | Không dựa vào việc ẩn nút trên UI |
| Người có quyền duyệt chuyển sang ACTIVE | Chỉ thêm test khi quy tắc xét duyệt đã được chốt | Tránh tự suy đoán khi chưa có quyết định nghiệp vụ |

### 19.6. Xử lý phản hồi mới và đo giá trị

Nếu sau đó người nghiệp vụ xác nhận “PENDING vẫn được mở bài giới thiệu **công khai**”, phải phân biệt **bài công khai** với **nội dung hạn chế** và thêm ví dụ cho từng loại. Không được sửa test theo cách cho phép truy cập toàn bộ khóa chỉ vì có ngoại lệ cho bài giới thiệu.

**Outcome:** tỷ lệ học viên đủ điều kiện gửi yêu cầu thành công và hiểu được trạng thái/bước tiếp theo trong một khoảng quan sát, có cách đo phù hợp. **Guardrail:** không cấp quyền xem nội dung hạn chế khi chưa đủ điều kiện; không tạo yêu cầu/đăng ký trùng hoặc lộ trạng thái của người khác.

Một phiên ATDD thành công không cần giải quyết mọi kịch bản trong một lần. Nó cần giúp nhóm **đồng thuận phần sẽ xây, biết các câu hỏi chưa rõ và có ví dụ để xác nhận kết quả**.

## 20. Checklist ATDD trước khi bắt đầu và khi bàn giao

- [ ] User story nói rõ **người hưởng lợi, khả năng và giá trị cần tạo**?
- [ ] Người nghiệp vụ, Developers và góc nhìn kiểm thử đã **cùng trao đổi về những ví dụ quan trọng**?
- [ ] Người xác nhận nghiệp vụ có đủ hiểu biết/quyền quyết định hoặc có đường nâng cấp câu hỏi?
- [ ] Đã phân biệt **sự kiện, giả thuyết, ràng buộc và phương án kỹ thuật**?
- [ ] Phạm vi story được chia đủ nhỏ, có thể hoàn tất và kiểm chứng trong nhịp phù hợp?
- [ ] Acceptance criteria thể hiện **hành vi có thể quan sát**, không chỉ tên chức năng?
- [ ] Các trường hợp **thành công, thất bại, dữ liệu biên và rủi ro quyền/dữ liệu** được cân nhắc?
- [ ] Những điều **ngoài phạm vi hoặc chưa được quyết định** đã được ghi rõ?
- [ ] Các ví dụ có thể đọc bằng ngôn ngữ chung, không phụ thuộc quá sâu chi tiết class/UI?
- [ ] Có lựa chọn kiểm thử tự động/thủ công **phù hợp mức rủi ro và chi phí phản hồi**?
- [ ] Kiểm thử chấp nhận có thể cung cấp tín hiệu **sớm, ổn định, dễ chẩn đoán**?
- [ ] Những bất biến quan trọng về **transaction, đồng thời và quyền truy cập** được kiểm tra ở tầng thích hợp?
- [ ] Khi test đỏ, nhóm kiểm tra **mã sai, test sai, môi trường sai hay yêu cầu đổi** trước khi sửa expected?
- [ ] Test được tích hợp vào CI hoặc quy trình lặp lại phù hợp, không chỉ chạy thủ công trên máy riêng?
- [ ] Acceptance criteria được kết hợp với **Definition of Done**, không được xem là thay thế DoD?
- [ ] Khi thông tin mới xuất hiện, tiêu chí và backlog được **cập nhật minh bạch**?
- [ ] Không nhầm **test pass, UAT, release decision và outcome sản phẩm**?
- [ ] Nhóm dùng dữ liệu sai lệch/yêu cầu phải làm lại để cải tiến cách khám phá và kiểm thử?
- [ ] Các thực hành Scrum, Kanban, XP và Lean được dùng để **giao Increment đáng tin và học hỏi sớm**?

**Ghi nhớ:** ATDD đưa cuộc trao đổi về **“thế nào là hành vi được chấp nhận?”** lên trước việc triển khai. Bằng ví dụ cụ thể và sự cộng tác giữa nghiệp vụ, phát triển và kiểm thử, nhóm giảm hiểu sai, có cơ sở viết acceptance tests và nhận phản hồi tự động sớm. Kết hợp ATDD với **TDD, CI, Definition of Done và phản hồi người dùng** giúp Agile giao phần mềm tăng dần mà vẫn bảo vệ chất lượng, điều chỉnh yêu cầu có căn cứ và tập trung vào giá trị thực sự.
